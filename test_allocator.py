"""Correctness tests. Run with: python3 test_allocator.py"""
import random

from allocator import FreeListAllocator, HEADER, MIN_BLOCK, POLICIES


def test_split_and_coalesce():
    for p in POLICIES:
        a = FreeListAllocator(1024, p)
        x = a.malloc(100)            # block of 112 bytes
        y = a.malloc(100)
        z = a.malloc(100)
        assert a.free_blocks == 1 and a.stats.splits == 3
        a.free(y)                    # hole in the middle
        assert a.free_blocks == 2
        a.free(x)                    # merges with y's hole
        assert a.free_blocks == 2 and a.stats.coalesces == 1
        a.free(z)                    # merges both sides -> single block
        assert a.free_blocks == 1 and a.largest_free() == 1024
        a.check_invariants()


def test_policy_choice():
    # Free blocks of 200, 64 and 400 bytes, separated by allocated blocks.
    results = {}
    for p in POLICIES:
        a = FreeListAllocator(1024, p)
        b = [a.malloc(s - HEADER) for s in (200, 32, 64, 32, 400, 32)]
        a.malloc(1024 - 760 - HEADER)  # fill the tail exactly
        for i in (0, 2, 4):
            a.free(b[i])
        assert [s for s in a.sizes] == [200, 64, 400]
        results[p] = a.malloc(56 - HEADER) - HEADER
    assert results == {"first": 0, "best": 232, "worst": 328}


def test_no_split_when_remainder_too_small():
    a = FreeListAllocator(64, "first")
    p = a.malloc(64 - HEADER - (MIN_BLOCK - 8))   # leaves 8 bytes < MIN_BLOCK
    assert a.free_blocks == 0 and a.used[p - HEADER][0] == 64
    assert a.malloc(1) is None and a.stats.failed == 1


def test_random_stress():
    for p in POLICIES:
        rng = random.Random(42)
        a = FreeListAllocator(1 << 16, p)
        live = []
        for i in range(5000):
            if live and rng.random() < 0.45:
                a.free(live.pop(rng.randrange(len(live))))
            else:
                ptr = a.malloc(rng.randint(1, 2000))
                if ptr is not None:
                    live.append(ptr)
            if i % 50 == 0:
                a.check_invariants()
        for ptr in live:
            a.free(ptr)
        a.check_invariants()
        assert a.free_blocks == 1 and a.used_bytes == 0


def test_double_free_rejected():
    a = FreeListAllocator(256, "best")
    p = a.malloc(10)
    a.free(p)
    try:
        a.free(p)
    except ValueError:
        return
    raise AssertionError("double free not detected")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
