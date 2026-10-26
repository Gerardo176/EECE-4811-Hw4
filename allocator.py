"""Simulated free-list memory allocator over a fixed-size heap.

Memory is simulated: a block is just (address, size). Nothing is actually
stored in the heap; we only track which address ranges are allocated or free.

Design
------
* Every block (free or allocated) carries an 8-byte header holding its size
  and an allocated bit. Payload pointers returned to the caller point just
  past the header.
* Block sizes are multiples of 8 and at least MIN_BLOCK bytes (enough for a
  header plus the free-list links a real implementation would store inside a
  free block).
* The free list is kept in *address order*. This is the classic textbook
  layout: it makes First Fit an address-ordered first fit, and keeps the
  list deterministic so all three policies are compared on the same
  structure. Only the *search* differs between policies.
* Boundary tags: free blocks are indexed by start address and end address,
  so on free() both physical neighbours can be found in O(1) and merged
  (immediate coalescing).
* Splitting: if the chosen block is larger than needed and the remainder is
  at least MIN_BLOCK, the block is split; the low part is allocated and the
  remainder stays on the free list. Otherwise the whole block is handed out
  and the slack becomes internal fragmentation.
"""
from bisect import bisect_left

ALIGN = 8
HEADER = 8
MIN_BLOCK = 16

POLICIES = ("first", "best", "worst")


def align_up(n, a=ALIGN):
    return (n + a - 1) & ~(a - 1)


class Stats:
    __slots__ = ("allocs", "failed", "frag_failed", "frees", "search_steps",
                 "max_search", "free_steps", "splits", "coalesces")

    def __init__(self):
        self.allocs = 0          # successful allocations
        self.failed = 0          # allocation requests that could not be served
        self.frag_failed = 0     # ...even though total free space was enough
        self.frees = 0
        self.search_steps = 0    # free blocks examined across all malloc calls
        self.max_search = 0      # worst single malloc search
        self.free_steps = 0      # comparisons to insert into the ordered list
        self.splits = 0
        self.coalesces = 0


class FreeListAllocator:
    def __init__(self, heap_size, policy="first"):
        if policy not in POLICIES:
            raise ValueError(f"unknown policy {policy!r}")
        self.policy = policy
        self.heap_size = heap_size - heap_size % ALIGN
        # Address-ordered free list as two parallel arrays.
        self.addrs = [0]
        self.sizes = [self.heap_size]
        # Boundary tags for free blocks.
        self.free_by_start = {0: self.heap_size}
        self.free_by_end = {self.heap_size: 0}
        # Allocated blocks: block address -> (block size, requested bytes).
        self.used = {}
        self.used_bytes = 0      # sum of allocated block sizes
        self.payload_bytes = 0   # sum of requested sizes of live allocations
        self.stats = Stats()

    # ---------------------------------------------------------------- search
    def _find(self, need):
        """Return (index into free list or -1, number of blocks examined)."""
        sizes = self.sizes
        if self.policy == "first":
            for i, s in enumerate(sizes):
                if s >= need:
                    return i, i + 1
            return -1, len(sizes)

        best = -1
        if self.policy == "best":
            best_size = None
            for i, s in enumerate(sizes):
                if s >= need and (best_size is None or s < best_size):
                    best, best_size = i, s
                    if s == need:            # exact fit cannot be beaten
                        return i, i + 1
            return best, len(sizes)

        # worst fit: must look at every block
        best_size = need - 1
        for i, s in enumerate(sizes):
            if s > best_size:
                best, best_size = i, s
        return best, len(sizes)

    # ------------------------------------------------------------ malloc/free
    def malloc(self, n):
        """Allocate n bytes. Returns a payload address or None on failure."""
        if n <= 0:
            raise ValueError("size must be positive")
        need = max(MIN_BLOCK, align_up(n + HEADER))
        st = self.stats
        idx, steps = self._find(need)
        st.search_steps += steps
        if steps > st.max_search:
            st.max_search = steps

        if idx < 0:
            st.failed += 1
            if self.heap_size - self.used_bytes >= need:
                st.frag_failed += 1
            return None

        addr, size = self.addrs[idx], self.sizes[idx]
        del self.free_by_start[addr]
        del self.free_by_end[addr + size]
        rem = size - need
        if rem >= MIN_BLOCK:
            # Split: keep the high part free. It occupies the same position in
            # the address-ordered list, so update in place.
            st.splits += 1
            new_addr = addr + need
            self.addrs[idx] = new_addr
            self.sizes[idx] = rem
            self.free_by_start[new_addr] = rem
            self.free_by_end[new_addr + rem] = new_addr
            size = need
        else:
            del self.addrs[idx]
            del self.sizes[idx]

        self.used[addr] = (size, n)
        self.used_bytes += size
        self.payload_bytes += n
        st.allocs += 1
        return addr + HEADER

    def free(self, ptr):
        addr = ptr - HEADER
        try:
            size, n = self.used.pop(addr)
        except KeyError:
            raise ValueError(f"invalid or double free of {ptr}") from None
        self.used_bytes -= size
        self.payload_bytes -= n
        st = self.stats
        st.frees += 1

        # Coalesce with the physically next block.
        nxt = addr + size
        nsize = self.free_by_start.get(nxt)
        if nsize is not None:
            st.coalesces += 1
            self._remove_free(nxt, nsize)
            size += nsize
        # Coalesce with the physically previous block.
        prev = self.free_by_end.get(addr)
        if prev is not None:
            st.coalesces += 1
            psize = self.free_by_start[prev]
            self._remove_free(prev, psize)
            addr, size = prev, size + psize

        i = bisect_left(self.addrs, addr)
        st.free_steps += max(1, len(self.addrs).bit_length())
        self.addrs.insert(i, addr)
        self.sizes.insert(i, size)
        self.free_by_start[addr] = size
        self.free_by_end[addr + size] = addr

    def _remove_free(self, addr, size):
        i = bisect_left(self.addrs, addr)
        del self.addrs[i]
        del self.sizes[i]
        del self.free_by_start[addr]
        del self.free_by_end[addr + size]

    # --------------------------------------------------------------- metrics
    @property
    def free_bytes(self):
        return self.heap_size - self.used_bytes

    @property
    def free_blocks(self):
        return len(self.addrs)

    def largest_free(self):
        return max(self.sizes) if self.sizes else 0

    def external_fragmentation(self):
        """1 - largest_free / total_free (0 = all free space is contiguous)."""
        free = self.free_bytes
        return 0.0 if free == 0 else 1.0 - self.largest_free() / free

    def internal_fragmentation(self):
        """Fraction of allocated block bytes not requested by the caller
        (headers, alignment padding, unsplit remainders)."""
        if self.used_bytes == 0:
            return 0.0
        return 1.0 - self.payload_bytes / self.used_bytes

    # ------------------------------------------------------------- debugging
    def check_invariants(self):
        blocks = [(a, s, False) for a, s in zip(self.addrs, self.sizes)]
        blocks += [(a, s, True) for a, (s, _) in self.used.items()]
        blocks.sort()
        pos, prev_free = 0, False
        for a, s, used in blocks:
            assert a == pos, f"gap or overlap at {pos} (next block at {a})"
            assert s >= MIN_BLOCK and s % ALIGN == 0, f"bad size {s} at {a}"
            assert used or not prev_free, f"uncoalesced free blocks at {a}"
            prev_free = not used
            pos += s
        assert pos == self.heap_size, "blocks do not tile the heap"
        assert self.addrs == sorted(self.addrs), "free list not address-ordered"
        assert self.free_by_start == dict(zip(self.addrs, self.sizes))
        assert self.free_by_end == {a + s: a for a, s in zip(self.addrs, self.sizes)}
        assert self.used_bytes == sum(s for s, _ in self.used.values())
