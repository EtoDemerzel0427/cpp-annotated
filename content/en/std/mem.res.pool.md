---
title: Pool resource classes
summary: "synchronized_pool_resource and unsynchronized_pool_resource: split into pools by block size, replenish an exhausted pool with ever larger chunks from upstream, pass oversized requests straight to upstream; the two pool_options parameters are only hints; all memory is returned on destruction."
updated: 2026-10-19
---

!!! tldr
    - Pool resources reuse freed blocks, which suits repeated allocation and deallocation of similarly sized objects, such as in node-based containers.
    - Each pool serves one block size, and a request goes to the smallest pool that can hold it; an exhausted pool gets another chunk from upstream, with chunk sizes growing geometrically; requests larger than the largest block size go straight to upstream.
    - The two `pool_options` parameters are only hints; `options()` returns the values actually in effect.
    - On destruction or `release()`, all memory is returned to upstream, whether or not it was `deallocate`d.
    - `synchronized_pool_resource` can be used by several threads at once; `unsynchronized_pool_resource` has no synchronization overhead.

## How pool resources work [mem.res.pool.overview]

¶1 `synchronized_pool_resource` and `unsynchronized_pool_resource` are together called the **pool resource classes** ([[g:pool-resource-classes]]). They are general-purpose memory resources with the following properties:

- ¶1.2 A pool resource consists of a collection of **pools**, each serving one block size. Each pool manages a collection of **chunks**, which are divided into uniformly sized **blocks**; `do_allocate` returns blocks. `do_allocate(size, alignment)` is dispatched to the smallest pool whose block size is at least `size`.
- ¶1.3 When a pool is exhausted, it is replenished with another chunk allocated from the **upstream allocator** supplied at construction. Each replenishment grows the chunk size geometrically. Note 1 points out that allocating in chunks makes consecutive allocations more likely to be close together in memory.
- ¶1.4 Requests larger than the largest block size of any pool are fulfilled directly by upstream.
- ¶1.5 A `pool_options` can be passed to the constructor to tune the largest block size and the maximum chunk size.
- ¶1.1 When the resource is destroyed it releases all the memory it allocated, even if some blocks were never `deallocate`d.

```text
request 24 bytes → 32-byte pool → free block in the free list? → yes: return it
                                        ↓ no
                     get a larger chunk from upstream, cut it into 32-byte blocks
request 2 MiB    → larger than the largest block size → upstream->allocate directly
```

¶2 `synchronized_pool_resource` may be accessed from multiple threads without external synchronization, and may use thread-specific pools to reduce synchronization costs. `unsynchronized_pool_resource` cannot be accessed from multiple threads simultaneously, so single-threaded programs pay no synchronization cost at all.

!!! impl "libc++"
    libc++'s `synchronized_pool_resource` wraps an `unsynchronized_pool_resource` with a `std::mutex` and locks it on every allocation and deallocation; it does not use the thread-specific pools the standard permits. Under high concurrency it can become a contention hotspot; consider one `unsynchronized_pool_resource` per thread.

## pool_options [mem.res.pool.options]

```cpp
struct pool_options {
  size_t max_blocks_per_chunk = 0;
  size_t largest_required_pool_block = 0;
};
```

¶2 `max_blocks_per_chunk` is the maximum number of blocks allocated from upstream at once when replenishing a pool. If it is zero or exceeds an implementation-defined limit, that limit is used. Implementations may use a smaller value, and may use different values for different pools.

¶3 `largest_required_pool_block` is the largest allocation size that is required to be fulfilled by the pooling mechanism; requests for a single block larger than this threshold go straight to upstream. If it is zero or exceeds an implementation-defined limit, that limit is used. Implementations may choose a larger pass-through threshold.

Both values are only hints. [mem.res.pool.mem] ¶3 specifies that `options()` returns the values that actually control the pooling behavior: zeros are replaced by implementation-defined defaults, and sizes may be rounded to an unspecified granularity.

```cpp run title="pool-options.cpp" impl
#include <memory_resource>
#include <cstdio>
int main() {
  std::pmr::pool_options o{.max_blocks_per_chunk = 0,
                           .largest_required_pool_block = 100};
  std::pmr::unsynchronized_pool_resource pool(o);
  auto got = pool.options();
  std::printf("max_blocks_per_chunk=%zu largest_required_pool_block=%zu\n",
              got.max_blocks_per_chunk, got.largest_required_pool_block);
}
```

With libc++ in our tests it prints `max_blocks_per_chunk=1048576 largest_required_pool_block=128`: zero is replaced by the limit 2^20, and 100 is rounded up to 128. Without options, libc++'s `largest_required_pool_block` is 1048576, i.e. 1 MiB.

## Construction and destruction [mem.res.pool.ctor]

¶1 The precondition of the constructor `(const pool_options& opts, memory_resource* upstream)` is that `upstream` is the address of a valid memory resource. ¶2 The pool resource obtains memory from `upstream` whenever its own data structures cannot satisfy a request. It holds a copy of `upstream` but does not own the resource it points to, so the upstream must outlive the pool resource. Note 1 states the design intent: in most cases, calls to `upstream->allocate()` should be substantially fewer than calls to `this->allocate()`.

¶3 The constructor throws nothing unless `upstream->allocate()` throws; it is unspecified if, or under what conditions, it calls `upstream->allocate()`, so an implementation may preallocate or defer until the first allocation.

The other three constructors all delegate to this one, with `get_default_resource()` as the default upstream and `pool_options()` as the default options. Copy construction and copy assignment are deleted. ¶4 The destructor calls `release()`.

## Member functions [mem.res.pool.mem]

¶1 `release()` calls `upstream_resource()->deallocate()` as needed to release all allocated memory. Note 1 stresses that memory is returned to upstream even if some blocks have not been `deallocate`d. So a pool resource can also be used as an arena released all at once.

¶2 `upstream_resource()` returns the upstream passed at construction; ¶3 `options()` is covered above.

¶4–¶6 `do_allocate(bytes, alignment)`: if the selected pool cannot satisfy the request from its own data structures, it calls `upstream_resource()->allocate()` to get more memory; if `bytes` is larger than the largest pool can handle, it allocates directly from upstream. The returned storage is at least `bytes` bytes, with size and alignment meeting the requirements [[mem.res.class]] places on derived classes. It throws nothing unless upstream throws.

¶7–¶8 `do_deallocate` returns the memory to the pool. It is unspecified if, or under what circumstances, this results in a call to `upstream_resource()->deallocate()`. Implementations usually just put the block back on a free list, returning immediately only large blocks that were allocated directly from upstream. It throws nothing.

`do_deallocate` uses the `bytes` passed back by the caller to find the pool the block belongs to, so pool resources rely on the precondition in [[mem.res.class]] that the size must match the allocation. Passing the wrong size is UB; the typical consequence is that the block ends up in the wrong pool, and later allocations return memory of the wrong size.

¶9 `do_is_equal` returns `this == &other`.

## Which resource to choose

| Scenario | Choice |
|---|---|
| A batch of objects created together and destroyed together, rarely freed individually | [[mem.res.monotonic.buffer]] |
| Many similarly sized objects repeatedly allocated and freed, single-threaded | `unsynchronized_pool_resource` |
| Same, but shared by several threads | `synchronized_pool_resource`, or one `unsynchronized_pool_resource` per thread |
| Block reuse plus very fast upstream allocation | `unsynchronized_pool_resource` with a `monotonic_buffer_resource` as upstream |

## Summary

- Pools are tiered by block size, each tier replenished with geometrically growing chunks; oversized requests go straight to upstream.
- The two values of `pool_options` are only hints, and `options()` reports the values in effect.
- Destruction and `release()` return all memory; `deallocate` usually just puts the block back on a free list.
- `synchronized_pool_resource` is thread-safe (libc++ implements it with one mutex); `unsynchronized_pool_resource` has no synchronization overhead.
