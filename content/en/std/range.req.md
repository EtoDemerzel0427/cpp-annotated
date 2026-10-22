---
title: Range requirements
summary: "Definitions of the concepts range, borrowed_range, sized_range, common_range, viewable_range, constant_range and others, and their semantic requirements on complexity, borrowing and length."
updated: 2026-10-19
---

!!! tldr
    - `range<T>` only asks whether `ranges::begin` and `ranges::end` can be called on an lvalue of type `T`; semantically it also requires both calls to be amortized constant time and not to modify the range. That complexity requirement is why `filter_view` and other views cache `begin()`.
    - `borrowed_range` means iterators obtained from an object do not become invalid together with the object: lvalue references are always borrowed, and `string_view`, `span`, `subrange` and others declare themselves borrowed via `enable_borrowed_range`.
    - `sized_range` requires `ranges::size` to be constant time and equal to the actual number of elements; a type whose `size()` cannot meet this opts out with `disable_sized_range`.
    - `viewable_range` describes the arguments `views::all` can handle safely: lvalues, movable rvalue containers and views, but not const rvalues or rvalue `initializer_list`s.
    - The compiler does not check the semantic parts of these concepts. If a type satisfies only the syntax but not the semantics, handing it to the standard library gives no guarantees.

## The concept family [range.req.general]

¶1 Ranges let a program handle the elements of all kinds of data structures uniformly: `ranges::begin` returns an iterator and `ranges::end` returns a matching sentinel ([[range.access]]). ¶2–¶3 define a family of refinements on top of `range`:

```text
range ─┬─ approximately_sized_range ── sized_range
       ├─ input_range ── forward_range ── bidirectional_range
       │     ── random_access_range ── contiguous_range
       ├─ output_range<R, T>
       ├─ common_range      begin/end have the same type
       ├─ borrowed_range    iterators outlive the object
       ├─ view              see [range.view]
       ├─ viewable_range    can safely become a view
       └─ constant_range    elements cannot be modified
```

Each concept has a syntactic part (a `requires` expression, checked by the compiler) and a semantic part (conditions the standard writes with "models only if", not checked by the compiler). A type **satisfies** a concept when the syntactic part holds; it **models** a concept when both the syntax and the semantics hold ([[res.on.requirements]]). `view` has more to it and is covered separately in [[range.view]].

```cpp run ok
#include <initializer_list>
#include <ranges>
#include <span>
#include <string>
#include <string_view>
#include <vector>
namespace r = std::ranges;
using V = std::vector<int>;
static_assert(r::range<V>);              // even though ranges::begin(V{}) is ill-formed
static_assert(r::view<std::string_view> && r::view<std::span<int>>);
static_assert(!r::view<V>);              // copying is O(N)
static_assert(r::borrowed_range<std::string_view>);
static_assert(r::borrowed_range<V&>);
static_assert(!r::borrowed_range<V> && !r::borrowed_range<std::string>);
static_assert(r::viewable_range<V> && r::viewable_range<V&>);
static_assert(!r::viewable_range<const V>);  // a const rvalue cannot be moved
static_assert(!r::viewable_range<std::initializer_list<int>>);
static_assert(std::same_as<std::views::all_t<V&>, r::ref_view<V>>);
static_assert(std::same_as<std::views::all_t<V>, r::owning_view<V>>);
static_assert(!r::borrowed_range<r::owning_view<V>>);
static_assert(!std::copyable<r::owning_view<V>>);  // move-only
static_assert(r::contiguous_range<const V>);
static_assert(!r::contiguous_range<std::vector<bool>>);
static_assert(r::common_range<V>);
static_assert(!r::common_range<decltype(std::views::iota(0))>);
int main() {}
```

## range [range.range]

¶1 `range` requires a type to provide an iterator and a sentinel denoting its elements:

```cpp
template<class T>
  concept range = requires(T& t) {
    ranges::begin(t);   // sometimes equality-preserving (see below)
    ranges::end(t);
  };
```

Note the parameter is `T& t`: the syntactic check is always done on an lvalue. So `range<vector<int>>` is `true` even though `ranges::begin(vector<int>{})` is ill-formed. `range` asks whether an object of this type can be traversed; whether an rvalue can be handed directly to `begin` is answered by `borrowed_range` below.

¶2 For an expression `t` such that `decltype((t))` is `T&`, `T` models `range` only if also:

- 2.1 `[ranges::begin(t), ranges::end(t))` denotes a range ([[iterator.requirements.general]]);
- 2.2 both `ranges::begin(t)` and `ranges::end(t)` are amortized constant time and do not modify the range;
- 2.3 if the type of `begin` models `forward_iterator`, `ranges::begin(t)` is **equality-preserving**: equal inputs give equal results ([[concepts.equality]]).

!!! std
    both ranges::begin(t) and ranges::end(t) are amortized constant time and non-modifying

2.2 is the origin of the caching design throughout the clause. `filter_view::begin()` has to search linearly for the first element satisfying the predicate; to be amortized constant time it can only search on the first call and then cache the result ([[range.filter]]). "Non-modifying" means not changing the sequence of elements the range denotes; writing a cache inside the view does not count.

¶3 Note 1 explains 2.3: for a forward range, repeated calls to `begin` and `end` give equal results, so the same range can be passed to several algorithms or traversed several times. Input ranges have no such requirement; a second call to `begin` may give a different value or may not even be well-defined. `std::generator` is an example: its `begin()` requires the coroutine to still be suspended at its initial suspend point, and a second call violates the precondition ([[coro.generator]]).

## borrowed_range (¶4–¶7)

```cpp
template<class T>
  concept borrowed_range =
    range<T> &&
    (is_lvalue_reference_v<T> ||
     enable_borrowed_range<remove_cvref_t<T>>);
```

¶4 Let `U` be `T` with any rvalue reference removed. Given a variable `u` of type `U`, `T` models `borrowed_range` only if the validity of iterators obtained from `u` is not tied to the lifetime of that variable. Concretely:

- Lvalue reference types are always borrowed: `u` is a reference, and the end of the reference does not affect the referred-to object;
- `string_view`, `span`, `subrange` and `ref_view` are borrowed, since their iterators point into someone else's storage; so are `iota_view` and `empty_view`, whose iterators carry their own value or point to nothing at all;
- `vector` and `string` are not borrowed; their iterators dangle once the object is destroyed;
- `filter_view` and `transform_view` are not borrowed; their iterators hold a pointer to the view object itself, because they need the predicate or function stored there.

¶5 Note 2: so a function whose parameter type models `borrowed_range` can safely return iterators obtained from that parameter. `borrowed_iterator_t` in [[range.dangling]] uses exactly this to decide whether an algorithm returns a real iterator or `dangling`.

¶6 Users may specialize `enable_borrowed_range` for cv-unqualified program-defined types ([[namespace.std]]); such a specialization must be usable in constant expressions and have type `const bool`. ¶7 Example 1 shows that each specialization of `subrange` models `borrowed_range` by specializing `enable_borrowed_range` to `true`.

!!! pitfall "Specializing `enable_borrowed_range` is a promise"
    The compiler does not check whether the type really meets ¶4. If you specialize it to `true` for a type that holds a `std::vector`, `ranges::find(make_it(), x)` will return an iterator into a destroyed temporary. That is {{ub}}, and every protection in the standard library has been bypassed.

!!! history "Conditionally borrowed"
    In the original C++20 only a few views were borrowed. [[P2017R1]], as a defect report, made views that merely forward the underlying iterators, such as `take_view`, `drop_view` and `reverse_view`, borrowed whenever the underlying range is borrowed. The full list is in the header synopsis section of [[ranges]].

## Length: sized_range and approximately_sized_range

### sized_range [range.sized]

```cpp
template<class T>
  concept sized_range =
    approximately_sized_range<T> &&
    requires(T& t) { ranges::size(t); };
```

¶1 A `sized_range` can compute its number of elements in amortized constant time. ¶2 Given an lvalue `t` of type `remove_reference_t<T>`, `T` models `sized_range` only if also:

- 2.1 `ranges::size(t)` is amortized constant time, does not modify `t`, and equals `ranges::distance(ranges::begin(t), ranges::end(t))`;
- 2.2 if the iterator is a forward iterator, `ranges::size(t)` is well-defined whether called before or after `begin`. Note 1 adds that for a non-forward `sized_range`, `size` may be well-defined only before the first call to `begin`.

¶3 Users may specialize `disable_sized_range` for program-defined types. ¶4 Note 2 explains its purpose: to let types that satisfy but do not model `sized_range` work with the standard library. The classic example is a linked list whose `size()` member is linear time. Once it is specialized to `true`, `ranges::size` skips the member and non-member `size` and uses `end - begin` instead, or is simply unavailable ([[range.access]]).

### approximately_sized_range [range.approximately.sized] {{c++26}}

```cpp
template<class T>
  concept approximately_sized_range =
    range<T> && requires(T& t) { ranges::reserve_hint(t); };
```

¶1 It only requires that an estimate of the number of elements can be given in amortized constant time. ¶2 `ranges::reserve_hint(t)` does not modify `t`, its value is non-negative and representable in `range_difference_t<T>`, and when the iterator is a forward iterator it is well-defined whether or not `begin` has been called.

The estimate need not equal the actual count; `ranges::to` and others use it to `reserve` in advance. C++26 makes `sized_range` refine `approximately_sized_range`; when `size` is available, `reserve_hint` equals `size`, so every existing `sized_range` is unaffected.

## Other refinements [range.refinements]

### By iterator strength (¶1–¶3)

```cpp
template<class R, class T>
  concept output_range =
    range<R> && output_iterator<iterator_t<R>, T>;
template<class T>
  concept input_range =
    range<T> && input_iterator<iterator_t<T>>;
// forward_range, bidirectional_range, random_access_range refine step by step in the same way
template<class T>
  concept contiguous_range =
    random_access_range<T> && contiguous_iterator<iterator_t<T>> &&
    requires(T& t) {
      { ranges::data(t) } -> same_as<add_pointer_t<range_reference_t<T>>>;
    };
```

¶2 `contiguous_range` additionally requires `ranges::data` to be usable, with a result type of exactly `add_pointer_t<range_reference_t<T>>`. `data()` on a `const vector<int>` returns `const int*`, matching the reference type `const int&`. The reference type of `vector<bool>` is a proxy class, so it is not a contiguous range. ¶3 Semantically, `to_address(ranges::begin(t)) == ranges::data(t)` is required.

### common_range (¶4)

```cpp
template<class T>
  concept common_range =
    range<T> && same_as<iterator_t<T>, sentinel_t<T>>;
```

¶4 Example 1 points out that the standard containers are all common ranges. Many views are not, e.g. `take_while`, an unbounded `iota` and `istream`. Older interfaces such as the iterator-pair constructors of containers and C++17 algorithms need begin and end of the same type; convert with `views::common` first ([[range.common]]).

### viewable_range (¶5–¶6)

```cpp
template<class T>
  concept viewable_range =
    range<T> &&
    ((view<remove_cvref_t<T>> &&
      constructible_from<remove_cvref_t<T>, T>) ||
     (!view<remove_cvref_t<T>> &&
      (is_lvalue_reference_v<T> ||
       (movable<remove_reference_t<T>> &&
        !is-initializer-list<T>))));
```

¶6 A `viewable_range` is a range that can be safely converted into a view, which corresponds exactly to the arguments `views::all` accepts ([[range.all]]). *`is-initializer-list<R>`*, defined in ¶5, is `true` when `remove_cvref_t<R>` is a specialization of `initializer_list`.

| Argument | Viewable? | Result of `views::all` |
|---|---|---|
| a view constructible from the argument | yes | a copy of the view itself |
| a non-view lvalue, e.g. `vector<int>&` | yes | `ref_view` |
| a non-view movable rvalue, e.g. `vector<int>&&` | yes | `owning_view`, with the container moved in |
| `const vector<int>&&` | no | cannot move from a const rvalue |
| an rvalue `initializer_list<int>` | no | it only borrows a temporary array; storing it in an `owning_view` would inevitably dangle |
| an lvalue of a move-only view | no | cannot be copied |

### constant_range (¶7)

```cpp
template<class T>
  concept constant_range =
    input_range<T> && constant-iterator<iterator_t<T>>;
```

¶7 The elements of a `constant_range` cannot be modified through its iterators; it was introduced in C++23 by [[P2278R4]]. *`constant-iterator`* requires that adding const does not change the iterator's reference type ([[const.iterators]]). `const vector<int>` is a constant range; `span<int>` is not, because `span`'s constness does not propagate to its elements. `views::as_const` turns the latter into the former ([[range.as.const]]).

### sized-random-access-range (¶8)

¶8 states that the exposition-only *`sized-random-access-range`* is just `random_access_range<T> && sized_range<T>`. Note 1 says it is used to constrain some of the parallel algorithms with an execution policy in Clause 26: splitting work in parallel needs random access and also needs the length up front.

## Questions

!!! question "Question 1"
    When the underlying range is a `vector`, why is `range<const std::ranges::filter_view<...>>` `false`? Does this violate the non-modifying requirement of [range.range] ¶2.2?

<details markdown="1">
<summary>Answer</summary>

`filter_view`'s `begin()` caches its result, and a const version is provided only when the underlying range is input-only (not forward) ([[range.filter]]). When the underlying range is a `vector`, the `t` in `requires(T& t) { ranges::begin(t); }` is a `const filter_view&`, which cannot call the non-const `begin()`, so `range` is not satisfied.

This does not violate ¶2.2. The cache does not change the sequence of elements the range denotes; "non-modifying" refers to that observable sequence, not every byte in the object.
</details>

!!! question "Question 2"
    `get_ref()` returns a reference to some global `vector<int>`. Does `std::ranges::find(get_ref(), 0)` return `dangling`?

<details markdown="1">
<summary>Answer</summary>

No. The argument type is `vector<int>&`, and lvalue references are always borrowed, so the algorithm returns a real iterator. Only rvalues of non-borrowed ranges, such as a `vector` returned by value, get `dangling`. Whether that global `vector` is still alive is the programmer's own responsibility.
</details>
