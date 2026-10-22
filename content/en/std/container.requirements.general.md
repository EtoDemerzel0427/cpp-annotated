---
title: "General container requirements: containers, reversible containers, optional operations and allocator-aware containers"
summary: "The four sets of requirements shared by every standard container: member types and the complexity of basic operations, the semantics of ==, <=> and swap, how allocators propagate on copy, move, assignment and swap, the definitions of Cpp17CopyInsertable and related terms, and what a contiguous container is."
updated: 2026-10-19
---

!!! tldr
    - Except for `array` and `inplace_vector`, a container's move constructor and `swap` are constant time, so they can only hand over internal buffers, never move elements one by one.
    - A copy-constructed container gets its allocator from `select_on_container_copy_construction`; a move-constructed one moves the source's allocator. After that the allocator is replaced only by assignment or `swap`, and only when the corresponding propagate trait is true. So a copy of a `pmr` container is, by default, not in the original memory pool.
    - When the allocator does not propagate on `swap` and the two allocators are unequal, `a.swap(b)` is UB.
    - Terms like *Cpp17CopyInsertable* mean "can be constructed through the allocator's `construct`", which is not the same thing as `is_copy_constructible`. They appear in *Preconditions*, so the copy constructor of `vector<unique_ptr<int>>` is still declared and fails only when called.
    - `vector<int> v(5, 3)` gives five 3s, because integral types do not qualify as input iterators.

## Four sets of requirements ([container.intro.reqmts])

This subclause defines four sets of named requirements, which the other container clauses reference as "meets the ... requirements":

| Subclause | Requirements | Met by |
|---|---|---|
| [container.reqmts] | Container | Every container in this chapter, with local exceptions for `forward_list`, `hive` and the unordered containers |
| [container.rev.reqmts] | Reversible container | Containers whose iterators are bidirectional or random access |
| [container.opt.reqmts] | Optional operation `<=>` | Sequence containers and ordered associative containers |
| [container.alloc.reqmts] | Allocator-aware container | Every container except `array` and `inplace_vector`, plus `basic_string`, `basic_stacktrace` and `match_results` |

An allocator only supplies storage; elements have to be created one by one with `construct` ([[allocator.requirements]], [[allocator.traits]]). This subclause specifies how containers use the allocator.

¶1 [container.intro.reqmts] fixes the notation for the whole subclause: `X` is a container class and `T` its element type; `a` is a value of `X`, while `b` and `c` may be `const X`; `i` and `j` are `X::iterator`s; `v` is an lvalue of `X` or an rvalue of `const X`, that is, something that will be copied; `s` and `t` are non-`const` lvalues; `rv` is a non-`const` rvalue, that is, something that will be moved from. So the expression `X u(v)` denotes copy construction and `X u(rv)` move construction.

¶2 defines the exposition-only concept `container-compatible-range<R, T>`: `R` is an `input_range` and its reference type is convertible to `T`. The `from_range_t` constructors, `insert_range`, `append_range` and friends introduced in C++23 are all constrained by it. This is one of the few genuine concept constraints in the chapter; when it is not satisfied, the overload is not viable ([[over.match]]).

## Container requirements [container.reqmts]

¶1 A type `X` meets the container requirements if the following types, statements and expressions are well-formed and have the specified semantics.

### Member types (¶2–¶9)

| Expression | Result | Key points |
|---|---|---|
| `X::value_type` | `T` | ¶3 Precondition: `T` is erasable from `X` (*Cpp17Erasable*, see below); otherwise the container cannot even be destroyed |
| `X::reference`, `X::const_reference` | `T&`, `const T&` | `vector<bool>` does not meet this; see [[vector.bool]] |
| `X::iterator` | A forward iterator with value type `T`, convertible to `const_iterator` | ¶6 |
| `X::const_iterator` | A constant forward iterator | ¶7 |
| `X::difference_type` | A signed integer type, the same as the difference type of both iterators | ¶8 |
| `X::size_type` | An unsigned integer type that can represent any non-negative value of `difference_type` | ¶9 |

### Construction, assignment and destruction (¶10–¶26)

- ¶10–¶11 `X u;`: postcondition `u.empty()`, constant complexity.
- ¶12–¶14 `X u(v);`: the precondition is that `T` is copy-insertable (*Cpp17CopyInsertable*); postcondition `u == v`; linear complexity.
- ¶15–¶16 `X u(rv);`: `u` is equal to the value `rv` had before this construction. The complexity is linear for `array` and `inplace_vector` and constant for all other standard containers. Constant complexity means the implementation can only take over `rv`'s internal buffer, not move elements one by one.
- ¶20–¶22 `t = rv`: each existing element of `t` is either move assigned to or destroyed. The postcondition holds only if `t` and `rv` are not the same object, so `v = std::move(v)` is not guaranteed to keep the original value. By the library's general rule [[lib.types.movedfrom#2]], a standard library type is left in a valid but unspecified state after self-move-assignment.
- ¶24–¶26 `a.~X()`: destroys every element and deallocates all obtained memory; linear complexity.

### Iterators and comparison (¶27–¶47, ¶63)

- ¶27–¶38 `begin()` and `end()` return `const_iterator` for a `const X`; `cbegin()` is defined as `const_cast<X const&>(b).begin()`. All are constant complexity.
- ¶39–¶41 `i <=> j` is constrained on `X::iterator` meeting the random access iterator requirements; the result type is `strong_ordering`.
- ¶63 In expressions such as `i == j`, `i < j`, `i - j` and `i <=> j`, either side may be replaced by a `const_iterator` referring to the same element with no change in semantics.

!!! std
    c == b — Preconditions: T meets the Cpp17EqualityComparable requirements. ... Complexity: Constant if c.size() != b.size(), linear otherwise.

¶42–¶46 `c == b` returns `equal(c.begin(), c.end(), b.begin(), b.end())`. When the sizes differ, it must return `false` in constant time. ¶47 `c != b` is equivalent to `!(c == b)`; since C++20 it is provided automatically by rewritten candidates.

¶46 also has a *Remarks* sentence: `==` is an equivalence relation. That places an implicit requirement on the element type: *Cpp17EqualityComparable* ([[utility.arg.requirements]]) requires `==` to be reflexive, symmetric and transitive. A NaN `double` is not equal to itself, so on values that include NaN the precondition of ¶42 does not hold, and the standard makes no special case for floating point. In practice every implementation simply calls `==` element by element, and a `vector<double>` containing NaN is not equal to itself, as one would expect. In generic code, do not assume a container's `==` is an equivalence relation for every element type.

### `swap`, `size`, `empty` (¶48–¶62)

- ¶48–¶51 `t.swap(s)` and `swap(t, s)` are linear for `array` and `inplace_vector` and constant for other containers. The non-member `swap(t, s)` is equivalent to `t.swap(s)`.
- ¶52–¶55 `c.size()` returns `distance(c.begin(), c.end())`, constant complexity. `forward_list` is the only container that does not provide it.
- ¶56–¶58 `c.max_size()` returns the number of elements in the largest possible container.
- ¶59–¶62 `c.empty()` returns `c.begin() == c.end()`, constant complexity.

### Where the allocator comes from (¶64)

```cpp title="pmr-propagation.cpp" run ok
#include <memory_resource>
#include <vector>
#include <cassert>

int main() {
  std::pmr::monotonic_buffer_resource arena;
  std::pmr::vector<int> a({1, 2, 3}, &arena);

  std::pmr::vector<int> b = a;                 // copy construction: select_on_container_copy_construction
  assert(b.get_allocator().resource() == std::pmr::get_default_resource());

  std::pmr::vector<int> c(a, &arena);          // to stay in arena, pass it explicitly
  assert(c.get_allocator().resource() == &arena);

  std::pmr::vector<int> d = std::move(a);      // move construction: the allocator moves along
  assert(d.get_allocator().resource() == &arena);
}
```

The copy `b` is not in `arena`, and ¶64 is why. ¶64 specifies, in order, where a container's allocator comes from and when it gets replaced:

1. Unless otherwise specified, all containers in this chapter obtain memory through an allocator. Note 2 adds that containers and iterators refer to allocated elements only through the allocator's pointer type (`allocator_traits<A>::pointer` or its rebind). This lets fancy pointers (for example, offset-based pointers into shared memory) work with standard containers.
2. Copy constructors obtain the new container's allocator by calling `allocator_traits<A>::select_on_container_copy_construction` on the source container's allocator.
3. Move constructors obtain the new allocator by move construction from the source container's allocator, and that move shall not exit via an exception.
4. All other constructors take a `const allocator_type&` argument. Note 3 points out that if such a constructor uses the argument's default value, the allocator type must support value-initialization.
5. A copy of this allocator is used for all memory allocation and element construction throughout the container's lifetime, until it is replaced. Replacement can only happen through assignment or `swap`, and only when the corresponding trait is `true`: copy assignment consults `propagate_on_container_copy_assignment` (POCCA), move assignment `propagate_on_container_move_assignment` (POCMA), and swap `propagate_on_container_swap` (POCS).
6. `get_allocator()` returns a copy of the allocator used to construct the container or, if it has been replaced, a copy of the most recent replacement.

All three propagate traits of `std::pmr::polymorphic_allocator` are `false`, and its `select_on_container_copy_construction` returns a default-constructed allocator, which uses the default memory resource. So in the example, `b`'s allocator uses the default resource while `d`'s still uses `arena`.

!!! pitfall "A copy of a pmr container is not in the original memory pool"
    `std::pmr::vector<T> copy = pooled;` produces a copy that uses the default memory resource, not `pooled`'s. This is deliberate: it prevents a longer-lived copy from pointing into a short-lived pool. But it often leads people to believe a whole subsystem allocates from the pool when it actually does not.

### The exact semantics of `swap` (¶65)

```cpp title="swap-unequal-alloc.cpp" run ub
#include <memory_resource>
#include <vector>

int main() {
  std::pmr::monotonic_buffer_resource r1, r2;
  std::pmr::vector<int> a({1, 2, 3}, &r1);
  std::pmr::vector<int> b({4, 5}, &r2);
  a.swap(b);   // UB: POCS is false and a.get_allocator() != b.get_allocator()
}
```

!!! std
    Otherwise, the allocators shall not be swapped, and the behavior is undefined unless a.get_allocator() == b.get_allocator().

¶65 If POCS is `false`, the allocators are not swapped, and then the two allocators must be equal, otherwise the behavior is undefined. The reason is that after the swap `a` holds a buffer allocated by `r2` but can only deallocate it with `r1`'s allocator.

Compiled with `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_DEBUG` in our tests, libc++ reports *vector::swap: Either propagate_on_container_swap must be true or the allocators must compare equal* and terminates the program. Without hardening it swaps the buffers anyway, and the problem surfaces only when the memory is deallocated.

¶65 also specifies:

- Except for `array` and `inplace_vector`, `a.swap(b)` exchanges the values of the two containers without invoking any move, copy or swap operation on individual elements.
- `Compare`, `Pred` and `Hash` objects must be swappable (*Cpp17Swappable*) and are swapped as described in [[swappable.requirements]] (that is, through the `swap` found by ADL).
- When POCS is `true`, the allocators are swapped in the same way.
- An iterator referring to an element in one container before the swap refers to the same element in the other container afterwards. Whether `a.end()` before the swap equals `b.end()` after it is unspecified.

### Default exception guarantees and invalidation (¶66–¶67)

¶66 lists six default guarantees: single-element insertion and `push_*`/`emplace_*` have no effect if they throw; `erase`, `clear` and `pop_*` do not throw; copying a returned iterator does not throw; `swap` does not throw; `swap` does not invalidate iterators to elements. [[associative.reqmts]], [[unord.req]], [[deque]], [[inplace.vector]] and [[vector]] each specify exceptions.

¶67 is the master switch for invalidation: unless otherwise specified, invoking a container member function or passing a container to a library function does not invalidate iterators or change the values of elements.

For tables combining these two paragraphs with the rules of each container, see [[container.requirements]].

### Contiguous containers (¶68)

!!! std
    A contiguous container is a container whose member types iterator and const_iterator meet the Cpp17RandomAccessIterator requirements and model contiguous_iterator.

¶68 A **contiguous container** is a container whose `iterator` and `const_iterator` meet the *Cpp17RandomAccessIterator* requirements and model `contiguous_iterator`. The definition is given in terms of iterators, not memory layout. The contiguous containers in the standard are `array`, `vector` (when the element is not `bool`), `inplace_vector`, and `basic_string` from Chapter 27. All of them convert directly to `span` ([[views.contiguous]]).

```cpp title="contiguous.cpp" run ok
#include <vector>
#include <deque>
#include <list>
#include <iterator>

static_assert( std::contiguous_iterator<std::vector<int>::iterator>);
static_assert(!std::contiguous_iterator<std::vector<bool>::iterator>);
static_assert(!std::contiguous_iterator<std::deque<int>::iterator>);
static_assert( std::random_access_iterator<std::deque<int>::iterator>);
static_assert( std::bidirectional_iterator<std::list<int>::iterator>);

int main() {
  std::vector<int> v(5, 3);     // two ints: picks (size_type n, const T& value), not an iterator range
  return v.size() == 5 ? 0 : 1;
}
```

### Integers do not qualify as iterators (¶69)

The final `vector<int> v(5, 3)` in the example has two arguments of the same type. The template constructor `vector(InputIterator, InputIterator)` can deduce `InputIterator = int`, and it is a better match than `vector(size_type, const T&)`, which needs a conversion from `int` to `size_type`.

¶69 says that the behavior of certain container member functions and deduction guides depends on whether a type qualifies as an input iterator or an allocator. The extent to which an implementation determines that a type cannot be an input iterator is unspecified, but at minimum integral types do not qualify. Likewise, a type `A` must meet at least two conditions to qualify as an allocator: `A::value_type` is valid and denotes a type, and `declval<A&>().allocate(size_t{})` is well-formed as an unevaluated operand.

Paragraph 69 of [[sequence.reqmts]] adds that a type that does not qualify makes the corresponding constructors and member functions not participate in overload resolution. So `vector<int> v(5, 3)` picks the `(n, value)` version. C++98 handled the problem another way: when `InputIterator` was an integral type, the template version behaved as if it called the `(n, value)` version.

## Reversible containers [container.rev.reqmts]

¶1 A type `X` meets the reversible container requirements if it meets the container requirements, its iterator belongs to the bidirectional or random access category, and it provides:

- ¶2–¶3 `reverse_iterator`, which is `std::reverse_iterator<iterator>`, and likewise `const_reverse_iterator`;
- ¶4–¶15 `rbegin()` returning `reverse_iterator(end())`, `rend()` returning `reverse_iterator(begin())`, and `crbegin()` and `crend()` defined with `const_cast`; all constant complexity.

`forward_list` and the unordered containers are not reversible containers; `hive` is.

## Optional operation `<=>` [container.opt.reqmts]

```cpp title="partial-ordering.cpp" run ok
#include <vector>
#include <compare>
#include <cassert>
#include <cmath>

int main() {
  std::vector<double> a{1.0, NAN}, b{1.0, 2.0};
  auto r = a <=> b;                         // synth-three-way-result<double>, i.e. partial_ordering
  static_assert(std::is_same_v<decltype(r), std::partial_ordering>);
  assert(r == std::partial_ordering::unordered);
  assert(!(a < b) && !(b < a) && a != b);   // incomparable
}
```

¶1 The following operations are provided only by some containers. When the iterators passed to `lexicographical_compare_three_way` meet the constexpr iterator requirements, these operations are `constexpr` functions.

- ¶2 The result type of `a <=> b` is `synth-three-way-result<value_type>`.
- ¶3 Precondition: either `T` models `three_way_comparable`, or `<` is defined for values of (possibly `const`) `T` and is a total ordering relationship.
- ¶4–¶5 Returns `lexicographical_compare_three_way(a.begin(), a.end(), b.begin(), b.end(), synth-three-way)` ([[alg.three.way]]); linear complexity.

So `<=>` on `vector<double>` has result type `partial_ordering` and yields `unordered` on NaN, which is well-defined because `double` models `three_way_comparable`. Putting a type that only provides a non-total `operator<` into a container and comparing, on the other hand, violates the precondition.

The unordered containers and `hive` do not provide `<=>`; `hive` does not even provide `==` and `!=` ([[hive]]).

## Allocator-aware containers [container.alloc.reqmts]

¶1 All containers in Chapter 23 except `array` and `inplace_vector`, together with `basic_stacktrace`, `basic_string` ([[basic.string]]) and `match_results`, meet the additional requirements of allocator-aware containers.

### *Cpp17CopyInsertable* and related terms (¶2)

These terms appear in almost every *Preconditions* in Chapter 23. Let `A` be an allocator type such that `X`'s `allocator_type` is `allocator_traits<A>::rebind_alloc<T>`, `m` an lvalue of type `A`, and `p` a `T*`:

| Term | Definition: the following expression is well-formed, and ... |
|---|---|
| `T` is default-insertable into `X` (*Cpp17DefaultInsertable*) | `allocator_traits<A>::construct(m, p)` |
| An element is default-inserted | It is initialized by the expression above. For `std::allocator` that is value-initialization `::new(p) T()`; a custom allocator can switch it to default-initialization and skip the zeroing |
| Move-insertable (*Cpp17MoveInsertable*) | `construct(m, p, rv)`, after which `*p` is equivalent to the value `rv` had. Note 1: `rv` remains a valid object in an unspecified state |
| Copy-insertable (*Cpp17CopyInsertable*) | Move-insertable first, plus `construct(m, p, v)`, with `v` unchanged and equivalent to `*p` |
| Emplace-constructible (*Cpp17EmplaceConstructible*) from `args` | `construct(m, p, args)` |
| Erasable (*Cpp17Erasable*) from `X` | `allocator_traits<A>::destroy(m, p)` |

All of these terms are defined through the allocator, so they are not the same thing as type traits like `is_copy_constructible`. A `T` that cannot itself be copy constructed is still copy-insertable as long as the allocator's `construct` can make a `T` from a `const T&`, and vice versa.

If `X` is not allocator-aware (`array`, `inplace_vector`) or is a specialization of `basic_string`, the terms are defined as if `A` were `allocator<T>`. No allocator object needs to be created in that case, and no user specialization of `allocator<T>` is instantiated.

Note 2 explains that a container calls `construct(m, p, args)` with `m == get_allocator()`. The default behavior of `std::allocator` is `::new((void*)p) T(args)` (since C++20 actually through `construct_at`), but specialized allocators can choose a different definition. `scoped_allocator_adaptor` uses exactly this to pass itself down to nested containers ([[allocator.uses]]).

### Additional expressions (¶3–¶32)

| Expression | Preconditions | Postconditions or effects | Complexity |
|---|---|---|---|
| `X::allocator_type` | ¶5 *Mandates*: `allocator_type::value_type` is the same as `X::value_type` | | |
| `c.get_allocator()` | | | Constant |
| `X u;` | `A` is default-constructible | `u.empty()`, `u.get_allocator() == A()` | Constant |
| `X u(m);` | | `u.empty()`, `u.get_allocator() == m` | Constant |
| `X u(t, m);` | Copy-insertable | `u == t`, `u.get_allocator() == m` | Linear |
| `X u(rv);` | | Elements and allocator both come from `rv` | Constant |
| `X u(rv, m);` | Move-insertable | `u` owns `rv`'s former elements or copies of them, `u.get_allocator() == m` | Constant if `m == rv.get_allocator()`, otherwise linear |
| `a = t` | Copy-insertable and copy-assignable | `a == t` | Linear |
| `a = rv` | When POCMA is `false`: move-insertable and move-assignable (¶26) | Existing elements are move assigned to or destroyed | Linear |
| `a.swap(b)` | | Exchanges the contents | Constant |

¶5's *Mandates* was added in C++20. Previously `vector<int, allocator<long>>` worked on some implementations (they rebound internally); now it must be diagnosed:

```cpp title="alloc-mandates.cpp" error
#include <vector>
#include <memory>
std::vector<int, std::allocator<long>> v;   // error: allocator_type::value_type must be the same as value_type
```

¶26's precondition is conditional: when POCMA is `false`, the two allocators may be unequal, and `a` cannot take over `rv`'s buffer because it could not deallocate that memory with its own allocator; it has to move the elements one by one. Only in that case are `T` required to be move-insertable and move-assignable. This is why move assignment of `pmr` containers degrades to linear time when the memory resources differ:

```cpp title="pmr-move-assign.cpp" run ok
#include <memory_resource>
#include <vector>
#include <cstdio>

int main() {
  std::pmr::monotonic_buffer_resource r1, r2;
  std::pmr::vector<int> a({1, 2, 3}, &r1);
  std::pmr::vector<int> b(&r2);

  const int* old = a.data();
  b = std::move(a);   // polymorphic_allocator does not propagate on move assignment, and r1 != r2
  std::printf("%s\n", b.data() == old ? "stole buffer" : "element-wise move");
  std::printf("%s\n", b.get_allocator().resource() == &r2 ? "b keeps r2" : "?");
}
```

With libc++ (Clang 23) this prints `element-wise move` and `b keeps r2`. It also explains the containers' `noexcept` specifications: `vector`'s move assignment is declared `noexcept(POCMA || is_always_equal)` ([[vector]]).

## History and evolution

| Version | Change |
|---|---|
| C++98 | Container requirements given as tables; implementations allowed to assume that allocator instances of the same type always compare equal |
| C++11 | `allocator_traits`, POCCA, POCMA, POCS and `select_on_container_copy_construction`; *Cpp17CopyInsertable* and related terms; constant-time move construction; constant-time `size()` |
| C++17 | Node handles; `is_always_equal` enters the containers' `noexcept` specifications |
| C++20 | `<=>` replaces `<` and the other comparison operators, and the optional operation switches to `synth-three-way`; an allocator `value_type` mismatch becomes a *Mandates* |
| C++23 | `container-compatible-range` and the `from_range` family |
| C++26 | `inplace_vector` and `hive` added; besides `array`, there is now another container whose move construction and `swap` are linear |

## Questions

!!! question "Question 1"
    Are the elements of `std::list<std::unique_ptr<int>>` copy-insertable? Is `list`'s copy constructor still declared?

<details markdown="1">
<summary>Answer</summary>

They are not copy-insertable: `allocator_traits<allocator<...>>::construct(m, p, v)` is ill-formed for a `const unique_ptr&`. But `list`'s copy constructor is still declared, and `std::is_copy_constructible_v<std::list<std::unique_ptr<int>>>` is `true`. The reason is that paragraph 12 of [container.reqmts] states copy-insertability as a *Preconditions*, not a *Constraints*. Actually calling the copy constructor fails during instantiation; this is a hard error that SFINAE cannot detect. So in generic code, `std::vector<move-only type>` looks copyable. Compare `std::optional` and similar types, which use *Constraints* to propagate copyability precisely.
</details>

!!! question "Question 2"
    Two `std::vector<int, MyAlloc>` objects, where `MyAlloc` is stateful, POCS is `false` and the two instances are unequal. Is `std::swap(a, b)` (not the member `swap`) also UB?

<details markdown="1">
<summary>Answer</summary>

Yes. The non-member `swap` of `vector` is equivalent to `x.swap(y)` (paragraph 51 of [container.reqmts]). A qualified call like `std::swap(a, b)` also finds this overload in namespace `std`; it is more specialized than the generic `std::swap` template ([[temp.func.order]]) and is selected. So, just like the member `swap`, it falls under ¶65: unequal allocators mean UB. To exchange contents when the allocators are unequal, write one move construction plus two move assignments yourself. That path is well-defined for unequal allocators, at the cost of linear time and possibly allocating.
</details>

## Summary

- Container requirements: member types; constant-time move construction (except `array` and `inplace_vector`); constant-time `==` when sizes differ; constant-time `size()`; `swap` does not touch elements.
- Allocators: copy construction uses `select_on_container_copy_construction`, move construction moves the allocator and must not throw, other constructors take one explicitly; afterwards it is replaced by assignment or swap only when POCCA, POCMA or POCS is true.
- When POCS is false and the allocators are unequal, `swap` is UB.
- *Cpp17CopyInsertable* and related terms ask whether construction through `allocator_traits::construct` works; they are written as *Preconditions*, so failing them is an instantiation error or UB, not a non-viable overload.
- Contiguous containers are defined by their iterators: `array`, `vector` (not `bool`), `inplace_vector`, `basic_string`.
