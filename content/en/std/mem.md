---
title: Memory management library
summary: "A guide to Chapter 20: what <memory>, <memory_resource> and <scoped_allocator> each cover, how they build on the core language's object model, and what Constraints, Mandates, Preconditions and the other elements of a library clause mean."
updated: 2026-10-19
---

!!! tldr
    - Chapter 20 is the library interface to the object model: the allocator protocol, functions that explicitly begin object lifetimes, smart pointers and memory resources all live here.
    - When reading a library clause, first tell the elements apart: an unmet *Constraints* removes the function from overload resolution, an unmet *Mandates* makes the program ill-formed, and an unmet *Preconditions* is undefined behavior.
    - C++26 hardened preconditions are checked in a hardened implementation and terminate the program; in other implementations violating one is still undefined behavior. Only a few functions in this chapter use them.
    - The `malloc` family and memory resources implicitly create objects; `std::allocator<T>::allocate` begins only the lifetime of the array object, and the elements have to be constructed one by one.
    - Some declarations in `<memory>` have their normative wording outside this chapter: the specialized memory algorithms are in the algorithms chapter, `atomic<shared_ptr>` in the atomic operations chapter.

Chapter 20 [mem] is the library chapter closest to the core language. The core language specifies in [[intro.object]], [[basic.life]], [[basic.stc.dynamic]] and [[expr.new]] when objects exist, where storage comes from and what `new` and `delete` do; this chapter wraps those rules into composable library components.

## Map of the chapter [mem.general]

¶1 The chapter describes components for memory management. Table 50 in ¶2 maps subclauses to headers:

| Subclause | Contents | Header | Notes on this site |
|---|---|---|---|
| [memory] | Pointer traits, alignment, explicit lifetime management, the allocator protocol, the default allocator, `addressof`, C's `malloc` family | `<cstdlib>`, `<memory>` | [[memory]], [[pointer.traits]], [[ptr.align]], [[obj.lifetime]], [[allocator.uses]], [[allocator.traits]], [[default.allocator]] |
| [smartptr] | `unique_ptr`, `shared_ptr`, `weak_ptr`, `out_ptr` / `inout_ptr` | `<memory>` | [[smartptr]], [[unique.ptr]], [[util.sharedptr]] |
| [ptrtag] {{c++29}} | `pointer_tag_pair`: storing a small integer in a pointer's unused bits | `<memory>` | [[ptrtag]] |
| [mem.composite.types] {{c++26}} | `indirect`, `polymorphic` | `<memory>` | [[mem.composite.types]], [[indirect]], [[polymorphic]] |
| [mem.res] | `memory_resource`, `polymorphic_allocator`, pool resources, the monotonic buffer resource | `<memory_resource>` | [[mem.res]] |
| [allocator.adaptor] | `scoped_allocator_adaptor` | `<scoped_allocator>` | [[allocator.adaptor]] |

A few things are declared in `<memory>` but specified elsewhere:

- the specialized memory algorithms such as `uninitialized_copy`, `construct_at` and `destroy_at` are in [[specialized.algorithms]] in the algorithms chapter; their relation to placement new is covered in [[memory]];
- `atomic<shared_ptr<T>>` is in [[util.smartptr.atomic]] in the atomic operations chapter;
- `operator new` / `operator delete`, `std::launder` and `bad_alloc` are in `<new>`, part of the language support library [[support.dynamic]].

## Reading library clauses: what violating each requirement means

Library clauses rarely specify behavior with a plain "shall"; instead each function gets a list of elements with italic labels ([[structure.specifications]]). Violating different elements has completely different consequences:

| Element | When not met | Example from this chapter |
|---|---|---|
| *Constraints* | The function does not participate in overload resolution, as if it did not exist | The converting constructor of `unique_ptr<T[]>` requires the source pointer to be an array version too, with a compatible element type |
| *Mandates* | The program is ill-formed and must be diagnosed, usually by a `static_assert` | `default_delete<T>::operator()` requires `T` to be a complete type |
| *Preconditions* | Undefined behavior | `unique_ptr::operator*` requires `get() != nullptr` |
| *Hardened preconditions* {{c++26}} | Checked as a contract in a hardened implementation ([[g:hardened-implementation]]), terminating on violation; undefined behavior otherwise | `shared_ptr<T[]>::operator[]` requires `i >= 0`, and also `i < N` when `T` is `U[N]` |
| *Constant When* | The call is not a constant subexpression | `pointer_bits_available` requires the alignment to be a power of 2 |

The difference between *Constraints* and *Mandates* is most visible in generic code:

<div class="compare" markdown="1">

```cpp run ok
#include <memory>
#include <type_traits>
struct B {};
struct D : B {};
using UB = std::unique_ptr<B[]>;
using UD = std::unique_ptr<D[]>;
// Constraints not met: the constructor is not a candidate
static_assert(
  !std::is_constructible_v<UB, UD>);
int main() {}
```

```cpp run error
#include <memory>
#include <type_traits>
struct Inc;   // incomplete type
using Del = std::default_delete<Inc>;
// trait detection cannot see Mandates
static_assert(
  std::is_invocable_v<Del, Inc*>);
void f(Inc* p) {
  Del{}(p);  // error: T must be complete
}
int main() {}
```

</div>

On the left, *Constraints* removes the constructor from the candidate set, and `is_constructible` truthfully answers `false`. On the right, *Mandates* does not affect whether the function is callable; `is_invocable` answers `true`, and the error appears in the function body only when it is actually called.

Undefined behavior from violating a library precondition has the same standing as undefined behavior in the core language ([[intro.abstract]]). Dereferencing an empty `unique_ptr` is like `*static_cast<int*>(nullptr)`: the optimizer may assume it does not happen. C++26 standard library hardening turned only some preconditions into hardened preconditions: in this chapter `shared_ptr<T[]>::operator[]` is one, `unique_ptr::operator*` and `operator->` are not.

## Interfaces between this chapter and the core language

- Implicit object creation: `malloc`, `calloc`, `realloc` and `memory_resource::allocate` all implicitly create objects in the returned storage and return a pointer to a suitable object ([[intro.object]], [[g:implicitly-create-objects]]). `start_lifetime_as` does the same on existing storage without copying bytes ([[obj.lifetime]]).
- Lifetime: `allocator<T>::allocate` begins only the lifetime of the array object, not of any element ([[default.allocator]]). Elements must be constructed one by one through `allocator_traits::construct`, which by default is `construct_at`, i.e. placement new.
- Delete-expressions: the effect of `default_delete` is to call `delete` on the pointer, so the undefined behavior in [[expr.delete]] for incomplete types, non-virtual destructors and mismatched `delete` / `delete[]` carries over unchanged.
- Data races: the thread-safety guarantees of `shared_ptr` are stated in terms of the conflicts and data races of [[intro.races]] ([[util.smartptr.shared]]).

## Evolution of the chapter

| Version | Main changes |
|---|---|
| C++98 | `std::allocator`, `auto_ptr`, `raw_storage_iterator`, `get_temporary_buffer` |
| C++11 | `unique_ptr`, `shared_ptr`, `weak_ptr`, `allocator_traits`, `pointer_traits`, `scoped_allocator_adaptor`, `align`, `addressof`; `auto_ptr` deprecated |
| C++14 | `make_unique` |
| C++17 | `<memory_resource>`, `shared_ptr<T[]>`; `auto_ptr` removed |
| C++20 | `to_address`, `assume_aligned`, array `make_shared`, `*_for_overwrite`, `constexpr` `allocator` and `construct_at`, `atomic<shared_ptr>` |
| C++23 | `start_lifetime_as`, `out_ptr` / `inout_ptr`, `allocate_at_least`, `constexpr unique_ptr` |
| C++26 | `indirect` / `polymorphic` ([[P3019R14]]), `is_sufficiently_aligned`, `owner_hash` / `owner_equal` ([[P1901R2]]), `constexpr shared_ptr` ([[P3037R6]]), removal of the `allocator::is_always_equal` member ([[P2868R3]]) |
| After C++26 | `pointer_tag_pair` ([[P3125R6]]) |
