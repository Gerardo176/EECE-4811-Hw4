# EECE-4811-Hw4

Q1. 

**Job** |	**Response** | 	**Turnaround**

A 		|	0 |	200

B |	200 |	400

C |	400 |	600

**Avg** |	200 |	400

Q2. 

**Job |	Response |	Turnaround**

A (100) |	0 |	100

B (200) |	100 |	300

C (300) |	300 |	600

**Avg** |	133.33 |	333.33

Q3. 

**Policy |	Avg response (200×3) |	Avg turnaround (200×3) |	Avg response (100/200/300) |	Avg turnaround (100/200/300)**

FIFO |	200 |	400 |	133.33 |	333.33

SJF |	200 |	400 |	133.33 |	333.33

RR (q=1) |	1 |	599 |	1 |	465.67

Q4. 

SJF matches FIFO whenever FIFO’s order is already shortest-job-first. Which happens in the following two cases:

When all jobs have the same length and the jobs arrive in non-decreasing order of length.

Q5. 

Under SJF, each earlier job runs to completion, so a job waits for the full length of every earlier job.

Under RR, each earlier job runs for min(q, its length) before the next one starts.

So the two are equal when:

The quantum is at least as long as every job except the last one to start and RR’s order matches SJF’s order. This means equal-length jobs, or jobs that arrive sorted shortest-first.

Code instructions/results:


A simulated allocator over a fixed 1 MiB heap, with three placement policies compared on identical request traces.

allocator.py       allocator (free list, splitting, coalescing, 3 policies)

workloads.py       deterministic trace generator

benchmark.py       replays each trace against each policy, collects metrics

test_allocator.py  correctness tests

results/           results.md (all tables) and results.csv (raw numbers)

Run with python3 test_allocator.py, then python3 benchmark.py --seeds 5 (about 1 minute; --quick gives a smoke test).

**Design**

A block is only an (address, size) pair; no real bytes are stored.

Blocks: 8-byte header plus payload, 8-byte aligned, 16 bytes minimum.

Free list: kept in address order.

Allocation: the policy picks a free block. If at least 16 bytes would be left over, the block is split and the remainder stays free. Otherwise the whole block is used and the slack counts as internal fragmentation.

Free: the block is coalesced immediately with free neighbours on both sides. Boundary tags find them in O(1).

Policies differ only in the search. First Fit stops at the first block that fits. Best Fit scans for the smallest block that fits, stopping early on an exact fit. Worst Fit scans for the largest block.
The tests check that blocks tile the heap exactly, that no two free blocks are adjacent, and that each policy picks the expected block.

**Method**

Performance metrics:

free blocks examined per malloc, average and maximum (independent of the machine);

wall time per allocation;

free-list length.

Memory metrics:

external fragmentation, 1 - largest_free / total_free (0 means all free memory is in one block);

internal fragmentation;

fail % (share of requests that could not be served);

load at first failure (live data / heap when the first request fails).

Fairness: each trace is generated once per seed and replayed against all three policies on the same heap. Results are the mean of 5 seeds, 20k ops each, unless swept.

**Trace generator knobs:**

request size distribution;

target load (how full the program keeps the heap);

swing (after reaching the target, free down to target - swing: 0 means fine-grained interleaving, large values mean bursty phases);

a fraction of never-freed objects.

Each free picks a random live object.

Workload |	Why it is useful

W1 small uniform 16–256 B |	Long free list. Shows search cost, and First Fit's small fragments ("splinters") at the front of the heap.

W2 large uniform 1–32 KiB |	Short list. Shows whether large holes survive.

W3 log-uniform 16 B–16 KiB |	Realistic heavy-tailed mix; the baseline.

W4 bimodal (90% tiny, 10% 8–32 KiB) |	Tiny requests compete with big ones. Punishes splitting big blocks.

W5 long-lived (20% pinned, up to 30% of heap) |	Permanent objects block coalescing.

W6 phase shift (small, then large) |	Can old small-object holes serve larger requests?

W7 ramp, load 30%→100% |	Load at first failure measures how much of the heap is usable.

Sweeps | Max request size (64 B–32 KiB), target load (0.3–0.85), swing (0–0.6), number of ops (2k–100k).

**Results**

Full tables are in results/results.md. F/B/W = First/Best/Worst Fit.

Workload |	Steps/alloc F / B / W	| Ext. frag F / B / W |	Fail % F / B / W

W1 small uniform |	282 / 162 / 1150 |	0.14 / 0.05 / 0.75 |	0 / 0 / 1.7

W2 large uniform |	11 / 22 / 22 |	0.64 / 0.54 / 0.90 |	0.01 / 0 / 3.6

W3 log-uniform |	51 / 74 / 141 |	0.58 / 0.65 / 0.98 |	0 / 0 / 5.1

W4 bimodal |	33 / 46 / 165 |	0.63 / 0.70 / 0.95 |	0 / 0.02 / 2.3

W5 long-lived |	54 / 71 / 169 |	0.58 / 0.52 / 0.98 |	0 / 0 / 8.4

W6 phase shift |	150 / 134 / 477 |	0.43 / 0.40 / 0.74 |	1.2 / 1.1 / 2.7

W7 ramp to 100% |	49 / 69 / 135 |	0.54 / 0.55 / 0.98 |	0.5 / 0.5 / 4.5

Max size 32 KiB |	13 / 24 / 23 |	0.75 / 0.64 / 0.90 |	0.27 / 0.03 / 6.3

In W7, the load at first failure is 0.82 / 0.82 / 0.46. Internal fragmentation is nearly the same for every policy (about 23% for 16–64 B requests, 0.5% for log-uniform). It comes from headers and alignment, not from placement.

**Analysis**

Worst Fit loses on both measures. It always scans the whole list, and its list is the longest, so it is the slowest everywhere: 4× Best Fit on W1. Carving every request, even a 16-byte one, from the largest hole wears big holes down into medium ones. Its external fragmentation is 0.95–0.99. It fails even at 50% target load, and in the ramp it runs out at 46% heap use against 82% for the others.

First Fit is usually fastest. On mixed or large sizes it stops early and does 30–50% less searching than Best Fit. With many small requests this flips. Small leftover pieces build up at the front of the heap, so First Fit's list grows to 713 blocks against Best Fit's 282, and its searches get longer than Best Fit's.

Best Fit uses memory best. Tight fits keep large blocks intact. It has the lowest external fragmentation for small and uniform sizes, no failures in W2, and about 10× fewer failures than First Fit with 32 KiB requests. Its full scans are partly offset by a shorter list and by early exits on exact fits, which are common with small repeated sizes. On heavy-tailed workloads, First and Best Fit are about even on memory.

Effect of each knob:

Request size sets the free-list length, and so the search cost.

Heap pressure raises search cost for every policy (First Fit: 25 → 63 steps from load 0.3 to 0.85). It exposes Worst Fit first. Near a full heap, First and Best Fit first fail at the same load.

Burstiness: mass frees coalesce into big regions. Going from swing 0 to 0.6 halves the free list, cuts search cost about 2.5×, and removes First and Best Fit's failures. Finely interleaved alloc/free is the hardest case.

Number of requests: cost rises until about 10k ops, then levels off (First Fit: 135 vs 139 steps at 50k vs 100k). Cost depends on how fragmented the heap is, not on how many requests came before.

**Search cost |	Fragmentation |	Use it when**

First Fit |	lowest for mixed or large sizes |	moderate |	speed and simplicity matter

Best Fit |	full scan, but a shorter list |	lowest |	memory is tight

Worst Fit |	full scan of the longest list |	highest; fails at about half load |	almost never

Caveat: these costs assume a single linear list. A size-ordered structure (tree or segregated size classes) makes Best and Worst Fit O(log n). That removes Best Fit's main cost but not Worst Fit's fragmentation, which comes from the policy itself.
