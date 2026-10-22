---
title: Class template inplace_vector
summary: "C++26's inplace_vector: a variable-size contiguous container whose capacity is a compile-time constant and whose elements live inside the object; once full, the ordinary interface throws bad_alloc, the try_ family returns an empty optional, and the unchecked_ family trades a precondition for zero checks."
updated: 2026-10-19
---

!!! tldr
    - The elements of `inplace_vector<T, N>` live inside the object; the capacity N is fixed and the size varies between 0 and N. It never allocates heap memory and is not an allocator-aware container.
    - Operations that would make the size exceed N throw `bad_alloc`; `try_push_back` returns an empty `optional` when full; `unchecked_push_back` requires the caller to guarantee there is room.
    - If copying, moving and destroying `T` are trivial, the corresponding operations of `inplace_vector<T, N>` are trivial too; when N is 0 it is an empty trivial type.
    - Because the elements are inside the object, move construction and `swap` are both linear time, unlike `vector`, which only exchanges pointers.
    - Members that may throw are deleted in a freestanding implementation; the `try_` and `unchecked_` families remain.

`std::inplace_vector<T, N>` ({{c++26}}, [[P0843R14]]) sits between `array` and `vector`: like `array`, its capacity is a compile-time constant and its storage is inside the object; like `vector`, its size can change. It suits situations where an upper bound is known and heap allocation is unwanted, such as real-time code, embedded environments, and temporary buffers on hot paths.

!!! warning "The examples have not been compiled locally"
    The libc++ that ships with Clang 23 does not provide `<inplace_vector>` yet (`__cpp_lib_inplace_vector` is still commented out in `<version>`), and we had no GCC available. So the examples here carry no verdict; use the godbolt button to run them on a standard library that implements it.

## What happens once it is full

```cpp title="inplace-vector.cpp" run
#include <inplace_vector>
#include <cassert>

int main() {
  std::inplace_vector<int, 2> v;
  v.push_back(1);
  int& r = v.emplace_back(2);       // returns a reference to the new element
  assert(r == 2 && v.size() == v.capacity());

  auto opt = v.try_push_back(3);    // full: no exception, returns an empty optional
  assert(!opt && v.size() == 2);

  try { v.push_back(3); }           // full: throws bad_alloc (¶4)
  catch (const std::bad_alloc&) {}

  static_assert(std::inplace_vector<int, 2>::capacity() == 2);
}
```

[inplace.vector.modifiers] provides three sets of interfaces for insertion at the end, corresponding to three ways of handling errors:

| Interface | When full | Returns | Source |
|---|---|---|---|
| `push_back`, `emplace_back` | Throws `bad_alloc` | `reference`, i.e. `back()` | ¶4–¶7 |
| `try_push_back`, `try_emplace_back` | No effect | `optional<reference>`, `nullopt` when full | ¶8–¶14 |
| `unchecked_push_back`, `unchecked_emplace_back` | Violates the precondition `size() < capacity()`, {{ub}} | `reference` | ¶15–¶18 |

The first set reports errors with exceptions and is the default choice; the second uses return values and suits environments with exceptions disabled; the third suits callers who have already confirmed there is room and do not want to pay for another check.

A few details:

- `push_back` returns a reference, whereas `vector::push_back` returns `void`.
- The `try_` family returns `optional<reference>`, using C++26's `optional<T&>`. ¶12 says it throws nothing other than exceptions thrown by the initialization of the new element.
- ¶10 `try_emplace_back` direct-non-list-initializes the new element with the arguments, that is, `T(args...)` rather than `T{args...}`.
- ¶16, ¶18 The `unchecked_` family is defined as `*try_emplace_back(…)` and `*try_push_back(…)`; when there is no room, that dereferences an empty `optional`.

## Overview ([inplace.vector.overview])

¶1 An `inplace_vector` is a contiguous container with fixed capacity whose elements are stored within the `inplace_vector` object itself.

¶2 It meets the requirements of a container, reversible container, contiguous container and sequence container, and does not provide `push_front`, `prepend_range`, `pop_front` or `emplace_front`. Allocator-aware container is not on this list: [[container.alloc.reqmts#1]] excludes it together with `array`.

¶3 For any N, the iterators meet the constexpr iterator requirements.

!!! std
    Any member function of inplace_vector<T, N> that would cause the size to exceed N throws an exception of type bad_alloc.

¶4 Running out of capacity is treated as an allocation failure and throws `bad_alloc`, the same exception type as when a `vector` runs out of memory, so the same generic code has the same error path for both.

### Triviality propagates from T (¶5)

¶5 Let `IV` denote `inplace_vector<T, N>`. If N is 0, `IV` is a trivially copyable empty class and trivially default constructible. If N is greater than 0:

- ¶5.1–¶5.2 if `T`'s copy constructor (move constructor) is trivial, so is `IV`'s copy constructor (move constructor);
- ¶5.3 if `T` is trivially destructible, so is `IV`; on top of that, if `T`'s copy constructor and copy assignment are both trivial, `IV`'s copy assignment is trivial, and likewise for move assignment.

So `inplace_vector<int, 16>` is trivially copyable: it can be `memcpy`ed and placed wholesale into shared memory or a network packet. For N greater than 0 the standard does not guarantee trivial default construction, because default construction must set the size to 0.

In implementations, the storage is typically an array of elements inside a union (so default construction does not construct all N elements), plus a size counter.

## Construction and capacity ([inplace.vector.cons], [inplace.vector.capacity])

The constructors match the general entries in [[sequence.reqmts]], just without an allocator parameter: `inplace_vector(n)`, `(n, value)`, iterator range, `from_range` and initializer list (¶1–¶11).

¶9 `from_range` construction has a compile-time check:

!!! std
    *Mandates*: If ranges::size(rg) is a constant expression, then ranges::size(rg) ≤ N.

Putting a `std::array<int, 5>` into an `inplace_vector<int, 4>` is rejected at compile time. A range whose size is known only at run time and exceeds the capacity throws `bad_alloc` per ¶4.

[inplace.vector.capacity] specifies:

- ¶1 `capacity()` and `max_size()` are both `static constexpr` functions returning N.
- ¶2–¶7 If `resize(sz)` or `resize(sz, c)` throws, there is no effect on `*this`.
- ¶8–¶9 `reserve(n)` is `static constexpr` and does nothing, except throwing `bad_alloc` if `n > capacity()`.
- ¶10 `shrink_to_fit()` is a `static constexpr noexcept` no-op.

`reserve` and `shrink_to_fit` are kept so that `inplace_vector` can directly replace `vector` in generic code.

[inplace.vector.data] ¶1–¶2 `data()` is specified as for `vector`: `[data(), data() + size())` is a valid range, `data() == addressof(front())` when non-empty, constant time.

## Insertion in the middle, erasure and swap ([inplace.vector.modifiers])

### When insertion throws, the prefix is unchanged (¶1–¶3)

¶1 First n is defined: for `append_range` it is `size()` before the call, and for the other insertion functions the number of elements before the insertion point.

¶2 The complexity is linear in the number of elements inserted plus the distance from the insertion point to the end.

¶3 If the exception is not thrown by `T`'s copy constructor, move constructor, copy assignment or move assignment, nor by an operation of an input iterator, there is no effect. Otherwise, after the exception `size() >= n` and the first n elements are unmodified.

This guarantee is more specific than for insertion in the middle of a `vector`: the prefix before the insertion point is always intact, but the container may hold some of the elements that were already inserted. For example, when `append_range` exceeds the capacity, it may already have appended some elements before throwing `bad_alloc`.

### Erasure and swap (¶19–¶23)

¶19–¶21 The rules for `erase` and `pop_back` are the same as for `vector`: iterators and references at and after the erasure point are invalidated; nothing is thrown except by `T`'s assignment; the number of destructor calls equals the number of elements erased, and the number of assignments the number of elements after the erasure point.

¶22–¶23 `swap(x)` has the exception specification `noexcept(N == 0 || (is_nothrow_swappable_v<T> && is_nothrow_move_constructible_v<T>))`. The precondition is that `T` is move-constructible and the first `min(size(), x.size())` elements on the two sides are pairwise swappable.

With the elements inside the object, swapping can only proceed element by element: the overlapping part is `swap`ped element by element, and the surplus part is move-constructed onto the other side and the originals destroyed. So `swap` and move construction are both linear time, and [[container.reqmts#16]] and [[container.reqmts#50]] list `inplace_vector` together with `array` as exceptions.

### Iterator invalidation on insertion

[inplace.vector.modifiers] gives invalidation rules for erasure (¶19) but none for insertion. The general rule of [[container.reqmts#67]] is that, unless otherwise specified, container member functions shall not invalidate iterators or change the values of elements.

Insertion in the middle necessarily changes the values of elements after the insertion point, so the effect of insertion itself (insert before p) can be taken as "otherwise specified". A reasonable reading: the storage is inside the object and never reallocated, so iterators and references before the insertion point are unaffected; iterators at and after the insertion point still refer to valid storage but no longer to the original elements. In practice you can reason about it as a `vector` that never reallocates.

## erase and erase_if ([inplace.vector.erasure])

¶1–¶2 The non-member functions `erase(c, value)` and `erase_if(c, pred)` are equivalent to the remove-erase idiom and return the number of elements erased (`size_t`).

## freestanding

The `<inplace_vector>` header synopsis is marked mostly freestanding. In the class synopsis, the members that may throw `bad_alloc` for lack of capacity, including `push_back`, `emplace_back`, `insert`, `append_range`, `resize`, `reserve`, the constructors that take elements and `assign`, as well as `at`, which throws `out_of_range`, are all marked *freestanding-deleted* ([[freestanding.item]]) and are deleted in a freestanding implementation. The `try_` and `unchecked_` families, `erase`, `pop_back` and the non-throwing element accessors all remain.

So in an environment without exception support, the recommended way to use `inplace_vector` is `try_push_back` plus checking the return value.

## How to choose

- A known, modest upper bound and no heap allocation wanted: `inplace_vector`.
- A size that never changes: `array`.
- No upper bound, or a very large one: `vector`. The `sizeof` of an `inplace_vector` is at least `N * sizeof(T)`, and putting one on the stack can overflow it.

## Summary

| Aspect | Rule |
|---|---|
| Storage | Inside the object; the capacity N is `static constexpr`; not an allocator-aware container |
| Exceeding capacity | The ordinary interface throws `bad_alloc`; `try_` returns `nullopt`; `unchecked_` violates a precondition |
| Triviality | An empty trivial type when N is 0; otherwise copy, move and destruction are trivial whenever they are for `T` |
| `reserve`, `shrink_to_fit` | `static` functions, essentially no-ops |
| Move, `swap` | Linear time |
| Insertion that throws | Elements before the insertion point remain unchanged |
