import argparse
import csv
import os
import statistics
import time

from allocator import FreeListAllocator, POLICIES
from workloads import (bimodal, log_uniform, make_trace, phase_shift,
                       uniform)

HEAP = 1 << 20          # 1 MiB simulated heap, same for every run
N_OPS = 20_000
SAMPLE_EVERY = 100      # ops between fragmentation samples


def replay(trace, policy, heap=HEAP):
    a = FreeListAllocator(heap, policy)
    ptrs = {}
    ext, nfree = [], []
    first_fail_load = None
    peak_load = 0.0
    alloc_ns = 0
    for i, op in enumerate(trace):
        if op[0] == "a":
            t0 = time.perf_counter_ns()
            p = a.malloc(op[2])
            alloc_ns += time.perf_counter_ns() - t0
            ptrs[op[1]] = p
            if p is None and first_fail_load is None:
                first_fail_load = a.payload_bytes / heap
            peak_load = max(peak_load, a.payload_bytes / heap)
        else:
            p = ptrs.pop(op[1])
            if p is not None:           # skip frees of failed allocations
                a.free(p)
        if i % SAMPLE_EVERY == 0 and i >= len(trace) // 10:   # skip warm-up
            ext.append(a.external_fragmentation())
            nfree.append(a.free_blocks)
    st = a.stats
    reqs = st.allocs + st.failed
    return {
        "steps_per_alloc": st.search_steps / reqs,
        "max_steps": st.max_search,
        "ns_per_alloc": alloc_ns / reqs,
        "free_blocks": statistics.mean(nfree),
        "ext_frag": statistics.mean(ext),
        "int_frag": a.internal_fragmentation(),
        "fail_pct": 100 * st.failed / reqs,
        "frag_fail_pct": 100 * st.frag_failed / reqs,
        "load_at_first_fail": first_fail_load,
        "peak_load": peak_load,
        "splits": st.splits,
        "coalesces": st.coalesces,
    }


# name -> make_trace kwargs (n_ops/heap/seed filled in later)
WORKLOADS = {
    "W1 small uniform 16-256B": dict(size_fn=uniform(16, 256)),
    "W2 large uniform 1-32KiB": dict(size_fn=uniform(1024, 32768)),
    "W3 log-uniform 16B-16KiB": dict(size_fn=log_uniform(16, 16384)),
    "W4 bimodal 90% tiny / 10% 8-32KiB": dict(
        size_fn=bimodal(uniform(16, 128), uniform(8192, 32768), 0.10)),
    "W5 long-lived (20% pinned, <=30% heap)": dict(
        size_fn=log_uniform(16, 16384), immortal=0.20),
    "W6 phase shift small->large": dict(
        size_fn=phase_shift(uniform(16, 256), uniform(2048, 16384))),
    "W7 ramp to 100% load": dict(
        size_fn=log_uniform(16, 16384), target=lambda t: 0.3 + 0.7 * t),
}

SWEEPS = {
    # Request size: max size varies, everything else fixed.
    "size": ("max request size",
             [(m, dict(size_fn=uniform(16, m), target=0.75))
              for m in (64, 512, 4096, 32768)]),
    # Heap pressure: how full the program keeps the heap.
    "pressure": ("target load",
                 [(f"{p:.2f}", dict(size_fn=log_uniform(16, 16384), target=p))
                  for p in (0.3, 0.5, 0.7, 0.85)]),
    # Alloc/free frequency: fine-grained interleaving vs bursty phases.
    "burst": ("swing (burstiness)",
              [(s, dict(size_fn=log_uniform(16, 16384), target=0.85, swing=s,
                        p_alloc=1.0))
               for s in (0.0, 0.1, 0.3, 0.6)]),
    # Total number of requests.
    "ops": ("number of ops",
            [(n, dict(size_fn=log_uniform(16, 4096), target=0.75, n_ops=n))
             for n in (2_000, 10_000, 50_000, 100_000)]),
}

COLUMNS = [
    ("steps_per_alloc", "search steps/alloc", "{:.1f}"),
    ("max_steps", "max steps", "{:.0f}"),
    ("ns_per_alloc", "ns/alloc", "{:.0f}"),
    ("free_blocks", "avg free blocks", "{:.1f}"),
    ("ext_frag", "ext. frag", "{:.3f}"),
    ("int_frag", "int. frag", "{:.3f}"),
    ("fail_pct", "fail %", "{:.2f}"),
    ("failed_runs", "runs w/ a failure", "{}"),
    ("load_at_first_fail", "load @1st fail", "{:.3f}"),
]


def run_config(kwargs, seeds):
    kwargs = dict(kwargs)
    n_ops = kwargs.pop("n_ops", N_OPS)
    per_policy = {p: [] for p in POLICIES}
    for seed in range(seeds):
        trace = make_trace(n_ops, heap_size=HEAP, seed=seed, **kwargs)
        for p in POLICIES:
            per_policy[p].append(replay(trace, p))
    out = {}
    for p, runs in per_policy.items():
        agg = {}
        for k in runs[0]:
            vals = [r[k] for r in runs if r[k] is not None]
            # load_at_first_fail is None when a run never failed
            agg[k] = statistics.mean(vals) if vals else None
        agg["failed_runs"] = f"{sum(r['load_at_first_fail'] is not None for r in runs)}/{len(runs)}"
        out[p] = agg
    return out


def fmt(fmt_str, v):
    return "never" if v is None else fmt_str.format(v)


def md_table(rows, label):
    head = [label, "policy"] + [c[1] for c in COLUMNS]
    lines = ["| " + " | ".join(head) + " |",
             "|" + "---|" * len(head)]
    for name, res in rows:
        for p in POLICIES:
            cells = [str(name) if p == "first" else "", p]
            cells += [fmt(f, res[p][k]) for k, _, f in COLUMNS]
            lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--quick", action="store_true",
                    help="1 seed, fewer ops (smoke test)")
    args = ap.parse_args()
    global N_OPS
    if args.quick:
        args.seeds, N_OPS = 1, 4000

    os.makedirs("results", exist_ok=True)
    md = [f"# Results\n\nHeap = {HEAP} bytes, {N_OPS} ops per trace "
          f"(unless swept), mean of {args.seeds} seeds. Same traces for all "
          "policies.\n"]
    csv_rows = []

    def record(section, name, res):
        for p in POLICIES:
            csv_rows.append({"section": section, "config": name, "policy": p,
                             **res[p]})

    rows = []
    for name, kw in WORKLOADS.items():
        t0 = time.time()
        res = run_config(kw, args.seeds)
        print(f"{name:40s} {time.time() - t0:6.1f}s")
        rows.append((name, res))
        record("workloads", name, res)
    md.append("## Workloads\n\n" + md_table(rows, "workload"))

    for sname, (label, configs) in SWEEPS.items():
        rows = []
        for val, kw in configs:
            if args.quick and kw.get("n_ops", 0) > 10_000:
                continue
            t0 = time.time()
            res = run_config(kw, args.seeds)
            print(f"sweep {sname}={val!s:10s} {time.time() - t0:6.1f}s")
            rows.append((val, res))
            record(sname, val, res)
        md.append(f"## Sweep: {label}\n\n" + md_table(rows, label))

    with open("results/results.md", "w") as f:
        f.write("\n\n".join(md) + "\n")
    with open("results/results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(csv_rows[0]))
        w.writeheader()
        w.writerows(csv_rows)
    print("wrote results/results.md and results/results.csv")


if __name__ == "__main__":
    main()
