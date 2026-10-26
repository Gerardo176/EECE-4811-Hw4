"""Deterministic request traces.

A trace is a list of operations, generated once and replayed against every
policy so all three allocators see exactly the same requests:

    ("a", obj_id, size)   allocate `size` bytes for object obj_id
    ("f", obj_id)         free object obj_id

Trace shape is controlled by:
  size_fn(rng, t)  request size; t in [0, 1) is progress through the trace,
                   so sizes can change over time (phase shifts).
  target           live payload the program "wants", as a fraction of the
                   heap (heap pressure). May be a function of t (ramp).
  swing            hysteresis: once live bytes reach `target` the program
                   frees until it drops to `target - swing`. 0 gives finely
                   interleaved alloc/free; large values give bursty phases of
                   mass allocation followed by mass deallocation.
  p_alloc          while in the allocating phase, probability that an op is
                   an allocation (otherwise a random free). Controls how much
                   frees are mixed into allocation phases.
  immortal         fraction of objects that are never freed (long-lived data
                   pinning parts of the heap), until they reach
                   immortal_cap * heap bytes so the heap is not simply filled.

Which object is freed is chosen uniformly at random among live objects, which
gives a realistic mix of short- and long-lived objects.
"""
import math
import random


def uniform(lo, hi):
    return lambda rng, t: rng.randint(lo, hi)


def log_uniform(lo, hi):
    a, b = math.log(lo), math.log(hi)
    return lambda rng, t: int(math.exp(rng.uniform(a, b)))


def bimodal(small, large, p_large):
    return lambda rng, t: (large if rng.random() < p_large else small)(rng, t)


def phase_shift(first, second):
    return lambda rng, t: (first if t < 0.5 else second)(rng, t)


def make_trace(n_ops, size_fn, heap_size, target=0.7, swing=0.0, p_alloc=0.8,
               immortal=0.0, immortal_cap=0.3, seed=0):
    rng = random.Random(seed)
    target_fn = target if callable(target) else (lambda t: target)
    ops = []
    freeable = []          # ids that may be freed
    sizes = {}
    live = 0
    pinned = 0
    allocating = True
    next_id = 0
    for i in range(n_ops):
        t = i / n_ops
        hi = target_fn(t) * heap_size
        lo = hi - swing * heap_size
        if allocating and live >= hi:
            allocating = False
        elif not allocating and live <= lo:
            allocating = True

        do_alloc = allocating and (not freeable or rng.random() < p_alloc)
        if not freeable:
            do_alloc = True
        if do_alloc:
            size = max(1, size_fn(rng, t))
            ops.append(("a", next_id, size))
            sizes[next_id] = size
            live += size
            if (rng.random() < immortal
                    and pinned + size <= immortal_cap * heap_size):
                pinned += size
            else:
                freeable.append(next_id)
            next_id += 1
        else:
            j = rng.randrange(len(freeable))
            freeable[j], freeable[-1] = freeable[-1], freeable[j]
            oid = freeable.pop()
            ops.append(("f", oid))
            live -= sizes.pop(oid)
    return ops
