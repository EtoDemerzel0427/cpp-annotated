---
title: Memory resources (std::pmr)
summary: "<memory_resource> takes the choice of where memory comes from out of the container's type and hands it to a run-time resource object; the two global resources new_delete_resource and null_memory_resource; the default resource pointer."
updated: 2026-10-19
---

!!! tldr
    - C++11 allocators are part of the type, so `vector<int, A>` and `vector<int>` are different types; `std::pmr` instead has all containers use one allocator type and chooses the memory resource at run time.
    - `new_delete_resource()` forwards to `::operator new` and `::operator delete`; every allocation from `null_memory_resource()` throws `bad_alloc`, which makes it a good upstream for forbidding heap use.
    - The default resource pointer starts as `new_delete_resource()`; allocators read it when they are constructed, and later changes do not affect allocators already constructed.
    - Allocators do not own resources. A resource must outlive every object allocated with it, or the behavior is undefined.

## Static allocators and run-time resources

The C++11 allocator model is static: the allocation strategy is part of the container type. `vector<int, ArenaAlloc<int>>` and `vector<int>` are two types, and a function taking `const vector<int>&` cannot accept the former. To make a library function support another allocation strategy, the only option is to turn it into a template.

C++17's `<memory_resource>` (namespace `std::pmr`, where pmr stands for polymorphic memory resource) takes a different approach:

- `memory_resource` in [[mem.res.class]] is an abstract base class that uses virtual functions to represent something that can allocate bytes;
- `polymorphic_allocator<T>` in [[mem.poly.allocator.class]] is a fixed allocator type that stores only a `memory_resource*` and forwards every allocation to it.

So `pmr::vector<int>`, i.e. `vector<int, pmr::polymorphic_allocator<int>>`, is a single type, and the allocation strategy is determined at run time by the resource passed in at construction. The cost is one more virtual function call per allocation and one more pointer of space in the allocator.

## The header [mem.res.syn]

`<memory_resource>` declares in `std::pmr`:

| Component | Page |
|---|---|
| `memory_resource` and its `operator==` | [[mem.res.class]] |
| `polymorphic_allocator<Tp = byte>` and its `operator==` | [[mem.poly.allocator.class]] |
| `new_delete_resource`, `null_memory_resource`, `set_default_resource`, `get_default_resource` | Below |
| `pool_options`, `synchronized_pool_resource`, `unsynchronized_pool_resource` | [[mem.res.pool]] |
| `monotonic_buffer_resource` | [[mem.res.monotonic.buffer]] |

The container headers also provide aliases in `std::pmr`, such as `pmr::vector<T>`, `pmr::string` and `pmr::map<K, V>`; `<memory>` has `pmr::indirect<T>` and `pmr::polymorphic<T>` ([[memory]]).

## The two global resources [mem.res.global]

¶1 `new_delete_resource()` returns a pointer to an object with static storage duration, of a type derived from `memory_resource`, that allocates and deallocates memory with `::operator new` and `::operator delete`. Every call returns the same value. For the return value `p` and any resource `r`, `p->is_equal(r)` returns `&r == p`, i.e. it is equal only to itself.

¶2 `null_memory_resource()` returns a resource with static storage duration whose `allocate()` always throws `bad_alloc` and whose `deallocate()` does nothing. It too returns the same value every time and is equal only to itself.

Its most common use is as an upstream resource, turning "no heap allowed" into a constraint enforced at run time:

```cpp run title="null-upstream.cpp" ok
#include <memory_resource>
#include <vector>
#include <cstdio>
#include <new>
int main() {
  std::byte buf[64];
  std::pmr::monotonic_buffer_resource mono(
      buf, sizeof buf, std::pmr::null_memory_resource());
  std::pmr::vector<int> v(&mono);
  try {
    for (int i = 0; i < 100; ++i) v.push_back(i);
  } catch (const std::bad_alloc&) {
    std::printf("bad_alloc after %zu elements\n", v.size());
  }
}
```

In our tests it prints `bad_alloc after 8 elements`. The `vector` successively requests buffers for 1, 2, 4 and 8 `int`s, 60 bytes in total; the monotonic resource does not reclaim old buffers ([[mem.res.monotonic.buffer]]), so when the next request for 64 bytes comes, the stack buffer is not enough, the request goes upstream, and the upstream throws `bad_alloc` instead of quietly falling back to the heap. This is useful in real-time code and in tests.

## The default resource pointer [mem.res.global]

¶3 The **default memory resource pointer** ([[g:default-memory-resource-pointer]]) points to a memory resource that certain facilities use when no resource is explicitly provided through the interface. Its initial value is the return value of `new_delete_resource()`. Its main users are default-constructed `polymorphic_allocator`s, and the pool and monotonic resources when no upstream argument is given.

- ¶4–¶5 `set_default_resource(r)`: if `r` is non-null, sets the default resource pointer to `r`, otherwise to `new_delete_resource()`; returns the previous value.
- ¶7 `get_default_resource()` returns the current value.
- ¶6 Calling these two functions does not introduce data races; a call to `set_default_resource` synchronizes with subsequent calls to `set_default_resource` and `get_default_resource` ([[intro.races]]). Implementations usually use an atomic pointer.

```cpp run title="default-resource.cpp" ok
#include <memory_resource>
#include <vector>
#include <cassert>
int main() {
  std::pmr::monotonic_buffer_resource arena;
  std::pmr::vector<int> d;                       // the default resource is read here
  std::pmr::set_default_resource(&arena);
  std::pmr::vector<int> e;
  assert(d.get_allocator().resource() == std::pmr::new_delete_resource());
  assert(e.get_allocator().resource() == &arena);
  std::pmr::set_default_resource(nullptr);       // restores new_delete_resource()
}
```

The default resource is read and saved at the moment the allocator is constructed, so `d` is not affected by the later `set_default_resource`.

!!! pitfall "Treating the default resource as a scoped tool"
    The default resource is global mutable state. In a multithreaded program, setting it to some thread-local arena makes other threads allocate from that arena without knowing it; once the arena is destroyed, the memory of those objects becomes invalid. `set_default_resource` is best set once at the start of `main`, for example to a resource that reports an error on every allocation, to catch unexpected heap allocations.

## A resource must outlive its users

`polymorphic_allocator` stores only a raw pointer and does not own the resource. The resource must outlive every allocator using it, and every object allocated with those allocators. This is the most common UB when using `pmr`:

```cpp run title="resource-lifetime.cpp" ub
#include <memory_resource>
#include <vector>
#include <optional>
int main() {
  std::optional<std::pmr::vector<int>> v;
  {
    std::pmr::unsynchronized_pool_resource pool;
    v.emplace({1, 2, 3}, &pool);           // elements are allocated from pool
  }                                        // pool is destroyed
  v.reset();                               // UB: deallocating through the destroyed pool
}
```

In our tests ASan reports `stack-use-after-scope`: the `pool.deallocate()` called by the `vector`'s destructor accesses a stack object that has already been destroyed. Within one scope, declaring the resource before the containers that use it gives the right order, since objects declared later are destroyed first.

## Summary

- `pmr` moves the allocation strategy from the type to a run-time object: one `pmr::vector<T>` type works with any resource.
- `new_delete_resource` forwards to `::operator new` and `::operator delete`; `null_memory_resource` always throws `bad_alloc` and makes a good upstream for forbidding heap use.
- The default resource pointer starts as `new_delete_resource()`, can be read and written without data races, and is read by allocators at construction.
- A resource is not owned by its allocators and must outlive all of its users.
