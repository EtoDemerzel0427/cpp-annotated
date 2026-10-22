---
title: Ranges library
summary: "A guide to Clause 25: a range is an iterator plus a sentinel, customization point objects such as ranges::begin provide access, a family of concepts describes capabilities, and views and adaptors compose lazily. The recurring themes are lazy evaluation, begin() caching and dangling."
updated: 2026-10-19
---

!!! tldr
    - A range is not a base class but a concept: a type from which `ranges::begin` yields an iterator and `ranges::end` yields a sentinel. The sentinel only has to be comparable with the iterator; its type can differ.
    - `ranges::begin`, `ranges::size` and friends are customization point objects: they look for an implementation in a fixed order and check the result type.
    - A view is a range that is cheap to copy and move; adaptors return views without computing anything, and elements are computed one at a time during iteration.
    - Views usually do not own their elements. The standard blocks some dangling with `dangling`, `owning_view` and similar tools, but a stored view can still dangle or give stale results.
    - The libc++ we test with still lacks `views::as_const`, `views::chunk`, `views::slide`, `<generator>` and more; the affected examples are marked on each page.

## The problem the ranges library solves

The C++98 algorithm interface is a pair of iterators, e.g. `std::sort(v.begin(), v.end())`. This has three problems:

1. The two iterators can come from different containers, and the compiler cannot tell;
2. The begin and end must have the same type, so to express "until `'\0'`" or an infinite sequence you must first count the length or fabricate a fake end iterator;
3. Nothing composes: to filter, then transform, then take the first 3, you either write a loop by hand or build intermediate containers.

The C++20 ranges library ([[P0896R4]]) answers all three:

```cpp run ok
#include <cstdio>
#include <ranges>
#include <vector>

int main() {
  std::vector<int> v{1, 2, 3, 4, 5, 6, 7, 8};
  auto r = v | std::views::filter([](int x) { return x % 2 == 0; })
             | std::views::transform([](int x) { return x * x; })
             | std::views::take(3);
  for (int x : r) std::printf("%d ", x);   // 4 16 36
  std::puts("");
}
```

The line that constructs `r` accesses no element. Each step of the `for` loop, `take` asks `transform` for an element, `transform` asks `filter` for one, and `filter` advances over `v` until it meets an even number.

This clause forms one whole with the iterators library of Clause 24 ([[iterators]], [[iterator.concepts]]) and the `std::ranges::` algorithms of Clause 26: the iterator concepts say how you can move, this clause says what a traversable sequence is, and the algorithms put both to use.

## Structure of the clause [ranges.general]

¶1–¶2 This clause describes components for dealing with ranges of elements; Table 84 divides them into six subclauses. Ordered by level of abstraction:

| Level | Subclause | Contents |
|---|---|---|
| Access | [[range.access]] | customization point objects `ranges::begin`, `end`, `size`, `data`, `empty`, etc. |
| Requirements | [[range.req]] | concepts such as `range`, `sized_range`, `view`, `borrowed_range` |
| Utilities | [[range.utility]] | `view_interface`, `subrange`, `dangling`, `ranges::to` |
| Sources | [[range.factories]] | views made from nothing: `empty`, `single`, `iota`, `repeat`, `istream` |
| Composition | [[range.adaptors]] | `filter`, `transform`, `take`, `join`, `zip` and others, plus the pipe operator |
| Coroutines | [[coro.generator]] | `std::generator`, an input range written as a coroutine, in `<generator>` |

Except for the last, all these components are in `<ranges>`.

## The core abstraction: iterator plus sentinel

`range` is a concept ([[range.range]]):

```cpp
template<class T>
  concept range = requires(T& t) {
    ranges::begin(t);
    ranges::end(t);
  };
```

`ranges::begin` yields an iterator and `ranges::end` yields a **sentinel**. The sentinel only needs to be equality-comparable with the iterator, and its type can differ from the iterator's ([[iterator.concept.sentinel]]). This solves problem 2 above: the end of a C string can be an empty class that checks `*p == '\0'` when compared with a `char*`; the end of an infinite sequence can be `unreachable_sentinel_t`, which compares unequal to every iterator.

On top of this, a chain of refining concepts describes what a range can do. `input_range`, `forward_range`, `bidirectional_range`, `random_access_range` and `contiguous_range` get progressively stronger, matching iterator strength. A few others are orthogonal: a `sized_range` can compute its length in constant time, a `common_range` has the same type for begin and end, a `borrowed_range`'s iterators do not become invalid together with the range object, and a `view` is cheap to copy and move. See [[range.req]].

## Three design threads

### Customization point objects

`ranges::begin(r)` is not a function but a **customization point object** ([[g:customization-point-object]]): a function object that tries arrays, a member `begin()`, and a `begin()` found by argument-dependent lookup in a fixed order, and checks that the result is an iterator ([[range.access]]).

Generic C++17 code had to write the two-step `using std::begin; begin(x);`, and forgetting the `using` broke arrays. A customization point object keeps the selection logic in one place, so whether a type is a range can be decided precisely by a concept, and a failure just means the concept is not satisfied rather than a hard error.

### Views: lazy, cheap, composable

A **view** is a range whose move is constant time and whose destruction cost does not depend on the number of elements ([[range.view]]), such as `string_view`, `span`, and the result of every adaptor. An adaptor ([[range.adaptors]]) takes a range and returns a view, doing no computation itself. The pipe `|` in the example above chains such adaptors together.

### Lifetime: borrowing and dangling

Views usually do not own their elements, and a view outliving the underlying data is the most common kind of bug in this clause. The standard has three layers of protection at the type level:

- For an rvalue non-borrowed range, algorithms return `ranges::dangling` instead of an iterator that would dangle ([[range.dangling]]);
- `views::all` produces a `ref_view` referring to an lvalue, and an `owning_view` for an rvalue container, moving the container into the view ([[range.all]]);
- `viewable_range` rejects things that cannot safely be turned into a view, such as a const rvalue container.

These only catch errors within a single expression. Storing a view, returning it from a function, or continuing to use it after modifying the underlying container can still dangle or invalidate it. The individual view pages keep coming back to this.

### Caching begin()

[[range.range#2]] requires `ranges::begin` to be amortized constant time. `filter_view` needs a linear search to find its first element, so the standard has it cache the result on the first call to `begin()`. `drop_view`, `drop_while_view`, `reverse_view`, `split_view`, `chunk_by_view` and `slide_view` do the same in some cases. The caching has two surprising consequences:

- `begin()` on these views is generally not a const member function, because it writes the cache. So when the underlying range is a forward range, a const `filter_view` is not a `range`, and `void f(const auto& r)` cannot accept it;
- After the first call to `begin()`, modifying the underlying data can make the view give stale results.

See [[range.filter]] and [[range.drop]].

```cpp run ok
#include <ranges>
#include <span>
#include <vector>

using std::ranges::borrowed_range;
static_assert(borrowed_range<std::span<int>>);
static_assert(borrowed_range<std::ranges::iota_view<int, int>>);
static_assert(!borrowed_range<std::vector<int>>);

using F = decltype(std::declval<std::vector<int>&>()
                   | std::views::filter([](int) { return true; }));
// filter_view's iterator points back to the view itself (it needs the predicate stored there)
static_assert(!borrowed_range<F>);
static_assert(!std::ranges::range<const F>);   // begin() is not a const member
int main() {}
```

## Header `<ranges>` [ranges.syn]

A few things in the synopsis are worth noting:

- **Mostly available in freestanding implementations.** The synopsis begins with the mark mostly freestanding. `basic_istream_view`, `views::istream` and `elements_of` are marked hosted; `view_interface` is partially freestanding because its `at()` throws `out_of_range`.
- **Customization point objects live in `inline namespace unspecified`.** Variables such as `ranges::begin` may have the same name as hidden friends of view iterators (e.g. `iter_move`); the inline namespace avoids the conflict of a variable and a function with the same name in one namespace. See [[customization.point.object]] for the rationale.
- **Which views are borrowed ranges.** The synopsis specializes `enable_borrowed_range` one by one: `subrange`, `empty_view`, `iota_view` and `ref_view` are always borrowed ranges; `owning_view`, `take_view`, `drop_view`, `common_view`, `reverse_view`, `elements_view`, `zip_view` and others depend on the underlying view. Those not on the list, such as `filter_view` and `transform_view`, are not borrowed ranges, because their iterators have to go back into the view object to get the predicate or function.
- **Signed and unsigned versions of integer-class types.** ¶1 defines *`make-unsigned-like-t<X>`* and *`to-unsigned-like(x)`*, and ¶2 defines *`make-signed-like-t<X>`*: when `X` is an integer type they are just `make_unsigned_t` and `make_signed_t`; when `X` is an integer-class type (a class type that behaves like an integer, [[iterator.concept.winc]]) they are the corresponding type of the same width. `ranges::size` returning unsigned and `ranges::ssize` returning signed are defined in terms of them.
- **`from_range_t` and `from_range`.** The tag used since C++23 when constructing a container from a range ([[P1206R7]]); `ranges::to` prefers it.

## Evolution

!!! history
    - C++20 ([[P0896R4]]) introduced the concepts, the customization point objects, `subrange`, `dangling`, `view_interface`, and the basic factories and adaptors `iota`, `filter`, `transform`, `take`, `drop`, `join`, `split`, `reverse`, `elements` and others. Several later papers went back and changed C++20 as defect reports; the most important introduced `owning_view` and redefined views ([[P2415R2]]), so that rvalue containers can go into a pipeline too.
    - C++23 added `ranges::to` ([[P1206R7]]), user-defined pipeable adaptors ([[P2387R3]]), the adaptors `zip`, `chunk`, `slide`, `join_with`, `enumerate`, `as_const` and others, and `std::generator`.
    - C++26 added `concat`, `views::indices`, `cache_latest`, `as_input` and `ranges::reserve_hint`, and made `optional` a range of at most one element.

## Implementation status in our tests

The examples on this site are checked with Clang 23 and libc++. At the time of writing, libc++ does not yet provide `views::as_const`, `views::chunk`, `views::slide`, `views::cartesian_product`, `views::cache_latest`, `views::as_input`, `ranges::reserve_hint` or `<generator>`; `ranges::cbegin` does not yet return a constant iterator, and `optional` is not yet a `range`. Examples involving these facilities are marked on their pages as not run locally.

## Reading order

1. [[range.access]] and [[range.req]]: how a range is defined precisely by customization point objects and concepts;
2. [[range.view]] and [[range.all]]: the semantic requirements on views, `ref_view` and `owning_view`;
3. [[range.adaptors]]: the rules for adaptor objects, closure objects and the pipe `|`;
4. Key views: [[range.filter]], [[range.transform]], [[range.join]], [[range.split]], [[range.zip]];
5. Utilities: [[range.subrange]], [[range.dangling]], [[range.utility.conv]].
