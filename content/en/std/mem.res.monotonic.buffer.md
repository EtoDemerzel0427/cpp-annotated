---
title: monotonic_buffer_resource
summary: "The standard library's arena allocator: allocation just bumps a pointer within a buffer, deallocation does nothing, and the memory goes back to the upstream resource all at once on release() or destruction."
updated: 2026-10-19
---

!!! tldr
    - Allocation in `monotonic_buffer_resource` moves a pointer forward within the current buffer, and `deallocate` does nothing.
    - When the buffer runs out, it asks the upstream resource for a larger new buffer, growing by an implementation-defined factor.
    - Memory is returned to upstream only as a whole, on `release()` or destruction; after `release()` it starts again from the initial buffer given at construction.
    - It suits scenarios such as handling one request or one frame, where a batch of objects is built and then discarded as a whole, and does not suit long-lived containers with repeated insertions and deletions.

## Usage: an allocator cleared every frame

```cpp title="monotonic-loop.cpp" run ok
#include <memory_resource>
#include <vector>
#include <string>
#include <cstdio>

int main() {
    std::byte buf[4096];
    std::pmr::monotonic_buffer_resource arena(
        buf, sizeof buf, std::pmr::null_memory_resource());
    for (int frame = 0; frame < 3; ++frame) {
        {
            std::pmr::vector<std::pmr::string> names(&arena);
            for (int i = 0; i < 5; ++i)
                names.emplace_back("some name that is not short at all");
        }                       // names is destroyed first (every deallocate is a no-op)
        arena.release();        // then reset as a whole: the next frame allocates from the start of buf again
        std::printf("frame %d ok\n", frame);
    }
}
```

In each frame, the `vector` and each `string` carve their memory out of `buf` on the stack, and the whole loop never touches the heap. The upstream is `null_memory_resource()` (a resource whose every allocation throws `bad_alloc`), so if any frame exceeds 4096 bytes, the program throws instead of quietly falling back to the heap.

The order matters: all users must be destroyed before `release()` is called. Otherwise the pointers they hold would point into memory that has been reclaimed and then handed out to someone else.

This kind of allocator is usually called an **arena allocator** or bump allocator. [mem.res.monotonic.buffer.general] ¶1 states its purpose: a special-purpose resource designed for very fast allocations, in situations where memory is used to build up a few objects and then released all at once when the resource object is destroyed.

## Internal model

The standard describes its state with three exposition-only data members:

```cpp
memory_resource* upstream_rsrc;    // upstream: asked for a new block when the buffer runs out
void*            current_buffer;   // the buffer currently being carved up
size_t           next_buffer_size; // how much to ask upstream for next time
```

Allocation finds a block meeting the alignment requirement in the remaining space of `current_buffer` and moves the pointer forward (for how alignment adjustment is done, see `std::align` in [[ptr.align]]). If it does not fit, it asks upstream for a new buffer. Deallocation does nothing.

## Construction and destruction [mem.res.monotonic.buffer.ctor]

Besides the three main constructors, the class has three versions that omit `upstream`, using `get_default_resource()` as the upstream. Copy construction and copy assignment are deleted: a resource object has identity and cannot be copied.

¶1 The first group of constructors is `(upstream)` and `(initial_size, upstream)`. The precondition is that `upstream` is the address of a valid resource and, if given, `initial_size` is greater than zero.

¶2 They set `current_buffer` to null and `next_buffer_size` to at least `initial_size`, or to an implementation-defined size if none is given. No memory is allocated at construction; upstream is asked only on the first `allocate`.

¶3 The second group is `(buffer, buffer_size, upstream)`, which starts with memory supplied by the caller. The precondition requires `buffer_size` to be no larger than the actual number of bytes in `buffer`.

¶4 It sets `current_buffer` to `buffer` and `next_buffer_size` to `buffer_size` (but at least 1), then multiplies it by an implementation-defined **growth factor**, which need not be an integer. So the first block requested from upstream is already larger than the initial buffer.

¶5 The destructor calls `release()`.

## Members [mem.res.monotonic.buffer.mem]

### Allocation (¶4–¶6)

¶4 If the remaining space in `current_buffer` can fit the required size and alignment, it allocates from there. Otherwise it sets `current_buffer = upstream_rsrc->allocate(n, m)`, where `n` is not less than `max(bytes, next_buffer_size)` and `m` is not less than `alignment`; it then multiplies `next_buffer_size` by the growth factor and allocates from the new buffer.

The space left over in the old buffer is abandoned and never revisited.

¶5 The returned storage meets the size and alignment requirements that [[mem.res.class]] places on all derived resources. ¶6 It throws only if upstream's `allocate` throws.

### Deallocation (¶7–¶9)

¶7–¶8 `do_deallocate` has no effect and throws nothing. ¶9 So the memory used by this resource only grows until it is destroyed; that is what monotonic in the name means.

### `release()` (¶1–¶2)

¶1 `release()` calls `upstream_rsrc->deallocate()` as needed to give back all memory obtained from upstream, and resets `current_buffer` and `next_buffer_size` to their initial values at construction.

If a user buffer was given at construction, `current_buffer` points back to it. The example at the top relies on exactly this to get zero heap allocations per frame.

¶2 Note 1 stresses that `release()` returns memory to upstream even if some blocks allocated from `*this` have not been deallocated. The resource does not track which blocks are still in use; that is the caller's responsibility.

### Others (¶3, ¶10)

¶3 `upstream_resource()` returns `upstream_rsrc`. ¶10 `do_is_equal` returns true only if the two are the same object, so memory allocated from one monotonic resource cannot be deallocated by another.

## When not to use it

`deallocate` doing nothing is a problem for data structures that keep growing and shrinking:

- When a `vector` grows, the old buffer is not reclaimed. With 2× growth, `push_back` N times occupies about 2N elements' worth of space in total.
- A long-lived `map` or `list` with frequent insertions and deletions grows without bound.

For such scenarios use a pool resource ([[mem.res.pool]]), or stack a pool resource on top of the monotonic one, for example `unsynchronized_pool_resource pool(&arena);`. The pool reuses freed blocks, and the monotonic resource obtains memory quickly in bulk.

!!! impl "What libc++ does"
    In Clang 23 with libc++, the growth factor is 2. At the end of each block obtained from upstream sits a 32-byte bookkeeping structure that records the list pointer and other information, and `release()` walks this list to give the blocks back one by one.

    Observed with an upstream resource that prints requests: starting from a 256-byte user buffer, the first two requests to upstream are 544 and 1056 bytes (512 and 1024 plus the bookkeeping structure); a default-constructed resource treats the initial size as 1024 and first requests 2080 bytes. After `release()`, the next small allocation goes back to the user buffer with no request to upstream.

## Summary

| Operation | Behavior |
|---|---|
| Allocation | Bump the pointer in the current buffer; if it does not fit, ask upstream for a larger block |
| Deallocation | Does nothing |
| `release()` / destruction | Gives all memory from upstream back and returns to the state at construction |
| Initial buffer | Can be supplied by the caller (such as a stack array) and is reused after `release()` |
