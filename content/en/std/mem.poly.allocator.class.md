---
title: polymorphic_allocator
summary: "The allocator type used by pmr, which stores only a memory_resource*; the deleted copy assignment, all-false propagation traits and fallback to the default resource when a container is copied together guarantee that a container uses one resource for its whole life; construct does uses-allocator construction so the resource reaches the elements; plus the byte-level and object-level allocation interfaces."
updated: 2026-10-19
---

!!! tldr
    - `polymorphic_allocator` stores only a `memory_resource*` and is implicitly constructible from `memory_resource*`, which is why `pmr::vector<int> v(&arena);` works.
    - A container binds to a resource at construction and never changes it afterwards: the allocator is not copy-assignable, and all its propagation traits are false.
    - Copying a `pmr` container gives the copy the default resource, not the original container's resource; to get the same resource, pass it explicitly.
    - `construct` does uses-allocator construction, so each string in a `pmr::vector<pmr::string>` allocates from the same resource.
    - Interfaces such as `allocate_bytes`, `new_object` and `delete_object` let `polymorphic_allocator<>` be used directly as a `new` and `delete` bound to a memory resource.

```cpp run title="polymorphic-allocator.cpp" ok
#include <memory_resource>
#include <string>
#include <type_traits>
#include <cassert>

using PA = std::pmr::polymorphic_allocator<>;    // Tp defaults to std::byte
static_assert(std::is_same_v<PA::value_type, std::byte>);
static_assert(!std::is_copy_assignable_v<PA>);
static_assert(!std::allocator_traits<PA>::propagate_on_container_move_assignment::value);
static_assert(!std::allocator_traits<PA>::is_always_equal::value);

int main() {
  std::pmr::monotonic_buffer_resource mr;
  PA a(&mr);
  auto* s = a.new_object<std::pmr::string>(
      "pmr strings get the allocator too, via construct");
  assert(s->get_allocator().resource() == &mr);   // the string uses mr too
  a.delete_object(s);
  void* raw = a.allocate_bytes(100, 64);
  a.deallocate_bytes(raw, 100, 64);
  assert(PA(&mr) == std::pmr::polymorphic_allocator<int>(&mr));
  assert(a == &mr);                               // compared after implicit conversion
}
```

## General [mem.poly.allocator.class.general]

¶1 When the template argument is a cv-unqualified object type, specializations of `polymorphic_allocator` meet *Cpp17Allocator*, so they can be used with any standard container. Instances of the same specialization constructed with different resources can have entirely different allocation behavior: objects using the same static allocator type behave at run time as if they used different allocator types. ¶2 Under the same conditions it meets the allocator completeness requirements ([[allocator.requirements.completeness]]), so it can be used for a `pmr::vector` whose element type is not yet complete.

The only exposition-only data member is `memory_resource* memory_rsrc`. The default argument of the template parameter `Tp` is `byte` (C++20, [[P0339R6]]), so `polymorphic_allocator<>` can be used with `allocate_bytes` and `new_object` below without rebinding for each type.

## One resource for a container's whole life

Several seemingly scattered rules of `polymorphic_allocator` together express one design principle: a container binds to a resource at construction and keeps it unchanged from then on.

1. Copy assignment is deleted: `operator=(const polymorphic_allocator&) = delete`. An allocator object cannot be changed to point to another resource.
2. All propagation traits are false: the class defines no `propagate_on_container_*`, so `allocator_traits` takes the default `false_type`; `is_always_equal` defaults to `is_empty`, which is false for a class that stores a pointer. So containers do not replace the allocator on assignment or swap ([[allocator.traits]]).
3. Copying a container falls back to the default resource: ¶18 `select_on_container_copy_construction()` returns `polymorphic_allocator()`, and ¶19 Note 4 states that the memory resource is not propagated.

```cpp run title="copy-uses-default.cpp" ok
#include <memory_resource>
#include <vector>
#include <cassert>
int main() {
  std::pmr::monotonic_buffer_resource arena;
  std::pmr::vector<int> v({1, 2, 3}, &arena);
  std::pmr::vector<int> copy = v;
  assert(copy.get_allocator().resource() == std::pmr::get_default_resource());
  std::pmr::vector<int> same(v, v.get_allocator());
  assert(same.get_allocator().resource() == &arena);
}
```

Rule 3 is the most surprising: `copy` uses the default resource, not `v`'s. A resource is usually tied to some scope, such as an arena on the stack or the lifetime of a request, while a copy may live longer or be passed elsewhere; inheriting the resource automatically would easily lead to dangling. When you want the same resource, pass it explicitly as `same` does.

Two more consequences follow: move-assigning between two `pmr` containers using different resources degrades to element-wise moves; swapping them is UB ([[allocator.traits]]).

## Constructors [mem.poly.allocator.ctor]

- ¶1 The default constructor sets `memory_rsrc` to `get_default_resource()`, reading the default resource at the moment of construction ([[mem.res]]).
- ¶2–¶5 `polymorphic_allocator(memory_resource* r)`: the precondition is that `r` is non-null; it throws nothing. ¶5 Note 1 points out that it provides an implicit conversion from `memory_resource*`; `pmr::vector<int> v(&arena);` can be written directly precisely because this constructor is not `explicit`.
- ¶6 Converting construction from `polymorphic_allocator<U>` copies the resource pointer. This is what containers use when rebinding the allocator to their internal node types.

## Member functions [mem.poly.allocator.mem]

### Allocation by type

¶1 `allocate(n)`: throws `bad_array_new_length` if `numeric_limits<size_t>::max() / sizeof(Tp) < n`, otherwise returns the result of `memory_rsrc->allocate(n * sizeof(Tp), alignof(Tp))`.

¶2–¶4 `deallocate(p, n)`: the precondition is that `p` was allocated by a resource `x` equal to `*memory_rsrc` with `x.allocate(n * sizeof(Tp), alignof(Tp))`; the effect is `memory_rsrc->deallocate(p, n * sizeof(Tp), alignof(Tp))`; it throws nothing.

### Byte-level and object-level interfaces

This set of interfaces was added in C++20:

| Function | Equivalent to |
|---|---|
| `allocate_bytes(nbytes, alignment = alignof(max_align_t))` (¶5–¶6) | `memory_rsrc->allocate(nbytes, alignment)` |
| `deallocate_bytes(p, nbytes, alignment)` (¶7) | `memory_rsrc->deallocate(p, nbytes, alignment)` |
| `allocate_object<T>(n = 1)` (¶8–¶9) | Overflow check, then `allocate_bytes(n*sizeof(T), alignof(T))` |
| `deallocate_object(p, n = 1)` (¶10) | `deallocate_bytes(p, n*sizeof(T), alignof(T))` |
| `new_object<T>(args...)` (¶11–¶12) | `allocate_object<T>()` then `construct`; if construction throws, deallocate and rethrow |
| `delete_object(p)` (¶13) | `destroy(p)` then `deallocate_object(p)` |

¶6 Note 1 explains that `allocate_bytes` returns `void*` rather than `byte*` so that it can be converted to any type with `static_cast<U*>`. The notes in ¶9 and ¶12 point out that the `T` of `allocate_object` and `new_object` cannot be deduced and must be given explicitly.

`delete_object` deallocates using the size of the static type `T`. Calling `delete_object` on a derived object through a base class pointer passes the wrong size to the resource, violating the precondition of `do_deallocate` ([[mem.res.class]]), even if the base class has a virtual destructor.

### construct and destroy (¶14–¶17)

¶14–¶16 `construct(p, args...)` performs uses-allocator construction of `T` with `*this` as the allocator and `args...` as the constructor arguments ([[allocator.uses]]): if `T` accepts an allocator, `*this` (converted to the allocator type `T` needs) is passed to the constructor as well. The *Mandates* requires this construction to be well-formed; it throws nothing unless `T`'s constructor throws.

This is the key to passing the resource down level by level. When a `pmr::vector<pmr::string>` constructs elements, `allocator_traits::construct` ends up here, and the `pmr::string` constructor receives the same resource. That is also why the string constructed by `new_object<std::pmr::string>` in the example above uses `mr`.

¶17 `destroy(p)` is equivalent to `p->~T()`. C++23 once deprecated it ([[LWG3036]]) on the grounds that the default behavior of `allocator_traits::destroy` is the same; C++26's [[P2875R4]] undid the deprecation, because the specification of `delete_object` uses it.

### Others

¶18–¶19 `select_on_container_copy_construction()` returns a default-constructed `polymorphic_allocator()`; see above. ¶20 `resource()` returns `memory_rsrc`.

## Equality [mem.poly.allocator.eq]

¶1 `a == b` returns `*a.resource() == *b.resource()`, comparing whether the two resources are equal (the same object, or `is_equal` is true; see [[mem.res.class]]), not just whether the pointers are equal.

The class also has a hidden friend `operator==(const polymorphic_allocator&, const polymorphic_allocator&)`. The namespace-scope template version cannot deduce its template arguments from a `memory_resource*`; with this friend, comparisons like `a == &mr` that need an implicit conversion on one side also compile ([[LWG3683]]).

## Questions

!!! question "Question 1"
    Why does `polymorphic_allocator` delete copy assignment but keep copy construction?

<details markdown="1">
<summary>Answer</summary>

Copy construction is a basic requirement of the allocator model: a container copies its own allocator from the one the user gives it, and converting construction is also needed when rebinding to node types. Copy assignment corresponds to replacing the allocator when a container is assigned to, while the principle of `pmr` is that a container uses the resource from its construction for its whole life. With POCCA false, containers never assign allocators anyway; deleting copy assignment prevents, at the type level, user code from modifying an allocator already bound to a container.
</details>

!!! question "Question 2"
    After `std::pmr::vector<std::pmr::vector<int>> outer(&arena);`, where does the inner vector constructed by `outer.emplace_back();` allocate from? What about `outer.push_back(std::pmr::vector<int>{1, 2, 3});`?

<details markdown="1">
<summary>Answer</summary>

In both cases the inner vector uses `arena`; in our tests the `get_allocator().resource()` of both equals `&arena`. `emplace_back()` goes through `construct`'s uses-allocator construction, so the inner vector gets `arena`. The argument of `push_back` is a temporary vector using the default resource, and `construct` builds the new element with the allocator-extended move constructor `vector(vector&&, const allocator_type&)`; since the two resources are not equal, the elements are moved one by one into a new buffer allocated from `arena`, instead of taking over the temporary's buffer.
</details>

## Summary

- Internally there is only a `memory_resource*`, implicitly constructible from `memory_resource*`; the default constructor reads the default resource at construction.
- Deleted copy assignment, all-false propagation traits, and fallback to the default resource on container copy: the resource follows the container object, not the container's value.
- `construct` does uses-allocator construction, so the resource reaches the elements.
- Since C++20 there are `allocate_bytes`, `allocate_object`, `new_object` and related interfaces, and `Tp` defaults to `byte`.
- Equality compares whether the resources are equal, not just the pointers.
