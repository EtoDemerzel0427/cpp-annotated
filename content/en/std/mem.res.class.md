---
title: memory_resource
summary: "The abstract base class of all pmr memory resources: public non-virtual functions forward to private virtual ones; allocate implicitly creates objects; deallocation must pass the same size and alignment as allocation; is_equal says whether two resources can deallocate each other's memory."
updated: 2026-10-19
---

!!! tldr
    - A custom resource only needs to derive from `memory_resource` and override three private virtual functions: `do_allocate`, `do_deallocate` and `do_is_equal`.
    - Besides forwarding to `do_allocate`, the public `allocate` implicitly creates objects in the allocated region, so the result can be used directly, like the return value of `malloc`.
    - `deallocate` must receive the same size and alignment as the allocation, which lets a resource keep no metadata at all.
    - `do_allocate` must throw an exception on failure; it may not return a null pointer.
    - Two resources are equal when memory allocated by one can be deallocated by the other.

## A custom resource

```cpp run title="tracing-resource.cpp" ok
#include <memory_resource>
#include <vector>
#include <string>
#include <cstdio>
#include <cstddef>

class tracing_resource : public std::pmr::memory_resource {
  std::pmr::memory_resource* up_;
  void* do_allocate(std::size_t n, std::size_t a) override {
    std::printf("  allocate(%zu, %zu)\n", n, a);
    return up_->allocate(n, a);
  }
  void do_deallocate(void* p, std::size_t n,
                     std::size_t a) override {
    std::printf("  deallocate(%zu, %zu)\n", n, a);
    up_->deallocate(p, n, a);
  }
  bool do_is_equal(const memory_resource& o)
      const noexcept override {
    return this == &o;
  }
public:
  explicit tracing_resource(std::pmr::memory_resource* up =
                                std::pmr::get_default_resource())
      : up_(up) {}
};

int main() {
  std::byte buf[256];
  tracing_resource tr;                       // prints every request to upstream
  std::pmr::monotonic_buffer_resource mono(buf, sizeof buf, &tr);
  std::pmr::vector<std::pmr::string> v(&mono);
  std::puts("push_back x3:");
  for (int i = 0; i < 3; ++i)
    v.emplace_back("a string long enough to need the heap");
  std::puts("scope end:");
}
```

Output with Clang 23 and libc++:

```text
push_back x3:
  allocate(544, 8)
scope end:
  deallocate(544, 8)
```

Three insertions plus each of the three strings' own buffers asked `tr` for memory only once. The `pmr::string`s also allocate from `mono`, as a result of the uses-allocator construction done by `polymorphic_allocator::construct` ([[allocator.uses]]). After the 256 bytes on the stack were used up, the monotonic resource asked upstream for a 544-byte block, and when `mono` is destroyed at the end of the scope it gives it back in one go. The value 544 depends on libc++'s growth policy and bookkeeping overhead for the monotonic resource, and is implementation-specific.

`tracing_resource` overrides only three private virtual functions, yet `vector` and `string` call the public `allocate` and `deallocate`. The structure is explained below.

## Public interface and private virtual functions [mem.res.class.general]

¶1 `memory_resource` is an abstract interface to an unbounded set of classes, each encapsulating a memory resource.

```cpp
class memory_resource {
  static constexpr size_t max_align = alignof(max_align_t);   // exposition only
public:
  memory_resource() = default;
  memory_resource(const memory_resource&) = default;
  virtual ~memory_resource();
  memory_resource& operator=(const memory_resource&) = default;

  void* allocate(size_t bytes, size_t alignment = max_align);
  void deallocate(void* p, size_t bytes, size_t alignment = max_align);
  bool is_equal(const memory_resource& other) const noexcept;

private:
  virtual void* do_allocate(size_t bytes, size_t alignment) = 0;
  virtual void do_deallocate(void* p, size_t bytes, size_t alignment) = 0;
  virtual bool do_is_equal(const memory_resource& other) const noexcept = 0;
};
```

This is the **non-virtual interface** (NVI) pattern: the public functions are not virtual, and they forward to private pure virtual functions. A derived class can override a private virtual function of its base, because overriding has nothing to do with access control ([[class.virtual]]); it just cannot call it directly. This way the base class can attach semantics uniformly in its public functions without derived classes being able to bypass them; the implicit object creation attached to `allocate` is an example.

The base class itself is copyable, but the concrete resource classes provided by the standard (the pool resources and the monotonic resource) all delete copying.

## Public member functions [mem.res.public]

!!! std "[mem.res.public]/2"
    *Effects*: Allocates storage by calling `do_allocate(bytes, alignment)` and implicitly creates objects within the allocated region of storage.

¶2 `allocate` allocates storage by calling `do_allocate`, and **implicitly creates objects** ([[g:implicitly-create-objects]]) in the allocated region: if some objects of implicit-lifetime types would give the program defined behavior, those objects come into existence at that moment ([[intro.object]]). ¶3 It returns a pointer to a suitable created object among them. ¶4 It throws what `do_allocate` throws.

This semantics comes from C++20's [[P0593R6]]. A derived class's `do_allocate` only needs to return a block of raw memory, which may come from a stack buffer or from a pool; the base class guarantees that the pointer the caller gets can be used directly to hold implicit-lifetime types such as an `int` array, just like a `malloc` result.

¶5 `deallocate` is equivalent to `do_deallocate(p, bytes, alignment)`, and ¶6 `is_equal` is equivalent to `return do_is_equal(other);`.

## Obligations of derived classes [mem.res.private]

### do_allocate (¶1–¶3)

¶1 The precondition is that `alignment` is a power of two. ¶2 The derived class must return allocated storage ([[basic.stc.dynamic.allocation]]) of at least `bytes` in size, aligned to `alignment`. ¶3 If it cannot, it must throw an appropriate exception. Returning a null pointer is not a valid way to indicate failure.

### do_deallocate (¶4–¶6)

!!! std "[mem.res.private]/4"
    *Preconditions*: `p` was returned from a prior call to `allocate(bytes, alignment)` on a memory resource equal to `*this`, and the storage at `p` has not yet been deallocated.

¶4 `p` must come from a previous call to `allocate` on a resource equal to `*this`, with the same `bytes` and `alignment`, and must not have been deallocated yet. Violating this is UB.

Both size and alignment must match the allocation, so a resource need not record the size in front of each block: the pool resources use `bytes` directly to find the right pool ([[mem.res.pool]]). `std::allocator::deallocate` also requires the size to match; `memory_resource` additionally requires the alignment to match. ¶5 The derived class disposes of the storage, and ¶6 must not throw.

### do_is_equal (¶7)

¶7 The derived class must return `true` if memory allocated from `*this` can be deallocated from `other` and vice versa, and `false` otherwise. Note 1 reminds that the most-derived type of `other` may differ from that of `*this`; an implementation in a derived class `D` can immediately return `false` if `dynamic_cast<const D*>(&other) == nullptr`.

For most stateful resources, being able to deallocate each other's memory means being the same object; the standard pool resources and the monotonic resource both return `this == &other`.

## Equality [mem.res.eq]

¶1 `operator==(a, b)` returns `&a == &b || a.is_equal(b)`, comparing addresses first to save a virtual call. The equality of `polymorphic_allocator` ultimately comes down to this ([[mem.poly.allocator.class]]). Whether a container can hand over its internal buffer directly on move assignment and swap depends on whether the two resources are equal ([[allocator.traits]]).

## Questions

!!! question "Question"
    A resource's `do_allocate` allocates every request with 16-byte alignment, ignoring the `alignment` parameter. What goes wrong with `allocate(64, 64)`?

<details markdown="1">
<summary>Answer</summary>

¶2 requires the returned storage to be aligned to `alignment`, so this `do_allocate` violates the derived class's obligations. The caller will place an object requiring 64-byte alignment at an address that is only 16-byte aligned, which is undefined behavior and may crash outright in code using aligned SIMD instructions. The correct approach is to satisfy any power-of-two alignment, or throw an exception for alignments that cannot be satisfied (¶3).
</details>

## Summary

- The public non-virtual `allocate`, `deallocate` and `is_equal` forward to the private pure virtual `do_*`.
- `allocate` implicitly creates objects (C++20), so the result can be used directly, like the return value of `malloc`.
- `do_allocate` must throw on failure; `do_deallocate` requires the same size and alignment as the allocation, from an equal resource.
- `is_equal` means "can deallocate each other's memory"; `operator==` compares addresses first.
