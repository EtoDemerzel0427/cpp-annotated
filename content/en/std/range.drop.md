---
title: Drop and drop_while views
summary: "views::drop skips the first n elements and views::drop_while skips the prefix that satisfies a predicate; drop returns a view of the same kind as its input where it can, and both cache begin() when necessary, so they often have no const begin()."
updated: 2026-10-19
---

!!! tldr
    - `views::drop(n)` skips the first n elements; if there are fewer than n, the result is an empty range, with no overrun.
    - When the input is a `span`, `string_view`, `iota_view`, `subrange`, `repeat_view` or `empty_view`, `drop` returns a view of the same kind directly.
    - Finding the new start takes n steps, so `drop_view` caches the result of `begin()` when the underlying range is not random access and sized; it then has no const `begin()`.
    - The start of `drop_while` has to be found by testing the predicate element by element; it always caches and can never be traversed as const.
    - If the underlying container is modified after caching, the start the view remembered is not updated.

```cpp run ok
#include <cstdio>
#include <ranges>
#include <string_view>

int main() {
  for (int i : std::views::iota(0, 10) | std::views::drop(5))
    std::printf("%d ", i);                                    // 5 6 7 8 9
  auto s = std::string_view("   hello") |
           std::views::drop_while([](char c) { return c == ' '; });
  for (char c : s) std::putchar(c);                           // hello
  std::puts("");
}
```

`drop` and `drop_while` mirror `take` and `take_while` in [[range.take]]: `take` cuts off the tail, `drop` cuts off the head. Cutting off the head means the position of the new first element has to be computed, which leads to the main question of this page: should the result of `begin()` be cached?

## `views::drop`: skipping the first n [range.drop.overview]

¶1 `drop_view` produces a view excluding the first N elements of the underlying view; if the underlying view has fewer than N elements, the result is an empty range. ¶3 Example 1 skips 5 of `iota(0) | take(10)` and prints `5 6 7 8 9`.

¶2 As with `take`, `drop` first checks whether it can return a view of the same kind as its input directly ([[P1739R4]]). Let `T` be the type of `E` with references and cv-qualifiers removed and `D` its difference type. If `F` is not convertible to `D` it is ill-formed; otherwise the checks are, in order:

| Paragraph | `T` is | Result |
|---|---|---|
| ¶2.1 | a specialization of `empty_view` | a copy of `E` (`F` is still evaluated) |
| ¶2.2 | a specialization of `optional` that models `view` {{c++26}} | a copy of `E` if `F` is 0, otherwise an empty `T()` |
| ¶2.3 | a random access, sized `span`, `basic_string_view` or `iota_view`, or a `subrange` that does not store its size | a view of the same kind over `[begin + min(distance(E), F), end)` |
| ¶2.4 | a random access, sized `subrange` that stores its size | as above, with the new size passed in |
| ¶2.5 | `repeat_view` | if bounded, repeats `min(distance(E), F)` fewer times; if unbounded, returns a copy of `E` as is |
| ¶2.6 | anything else | `drop_view(E, F)` |

In ¶2.3 the result for `span` is a dynamic-extent `span<element_type>`; in the other cases the result type is `T` itself. ¶2.4 targets a `subrange` whose iterator and sentinel cannot be subtracted and which therefore stores its size separately in the object (see [[range.subrange]]); the new size has to be computed along with it. The unbounded case of ¶2.5 is the most intuitive: infinitely many `x` with the first n removed is still infinitely many `x`.

```cpp run ok
#include <ranges>
#include <string_view>

using namespace std::literals;
auto sv = "hello"sv | std::views::drop(1);
static_assert(std::same_as<decltype(sv), std::string_view>);

auto rp = std::views::repeat(7) | std::views::drop(3);
static_assert(std::same_as<decltype(rp), decltype(std::views::repeat(7))>);

int main() {}
```

## Why `drop_view` caches begin() [range.drop.view]

`drop_view` stores the underlying view and the count n. ¶1 The constructor requires `n >= 0`, and ¶2 stores both in members. `end()` is just the underlying `end()`, and `size()` is the underlying size minus n, at least 0.

¶3 `begin()` returns `ranges::next(ranges::begin(base_), n, ranges::end(base_))`, i.e. it walks n steps from the start and stops at the end. For a `vector` this is one addition; for a `list` it really has to walk n steps.

The `range` concept requires `begin()` to be amortized constant time ([[range.range]]). ¶4 therefore specifies: when `drop_view` is a forward range, the first `begin()` overload caches its result in the view, and later calls return the cached value directly. Note 1 gives the consequence of not caching: wrapping a `reverse_view` around a `drop_view` would make traversal quadratic, because the outer view calls `begin()` repeatedly.

Caching modifies the view object, so it can only happen in a non-const `begin()`. The constraints on the two overloads are therefore:

- `begin() const` exists only when `const V` is random access and sized; walking n steps is then O(1) and no caching is needed;
- the non-const `begin()` is used in all other cases and caches as needed.

<div class="compare" markdown="1">

```cpp run ok
#include <ranges>
#include <vector>
std::vector<int> v{1, 2, 3, 4, 5};
using DV = decltype(v | std::views::drop(2));
// random access and sized: can be traversed as const
static_assert(std::ranges::range<const DV>);
int main() {}
```

```cpp run ok
#include <list>
#include <ranges>
std::list<int> l{1, 2, 3, 4, 5};
using DL = decltype(l | std::views::drop(2));
// needs caching: no const begin()
static_assert(!std::ranges::range<const DL>);
int main() {}
```

</div>

What is cached is an underlying iterator, which does not point into the `drop_view` itself, so `drop_view` is a [[g:borrowed-range|borrowed range]] when the underlying range is. The cache is a [[range.nonprop.cache|non-propagating-cache]]: copying the view does not copy the cache, and the new object recomputes it.

!!! impl "libc++"
    libc++ stores the cache only when `forward_range<V> && !(random_access_range<V> && sized_range<V>)`. Input ranges are not cached: `begin()` on an input range can be called only once, so the amortized constant requirement is trivially met.

## `views::drop_while`: skipping the prefix that satisfies a condition [range.drop.while]

¶1 Given a unary predicate `pred` and a view `r`, `drop_while_view` produces `[find_if_not(r, pred), end(r))`. ¶2 `views::drop_while(E, F)` is equivalent to `drop_while_view(E, F)`, with no special cases. [range.drop.while.overview] ¶3 Example 1 uses it to skip leading spaces and tabs in a string.

[range.drop.while.view] ¶4 `begin()` returns `find_if_not(base_, cref(*pred_))`; the precondition in ¶3 is that the predicate is present (it can be absent only in the corner case where an assignment threw). ¶5 As with `drop_view`, when the view is a forward range the result of the first call is cached, again to avoid quadratic complexity when a `reverse_view` is wrapped around it.

Unlike `drop_view`, even when the underlying range is a `vector`, how many elements to skip can only be known by calling the predicate one element at a time. So `drop_while_view` has only a non-const `begin()` and can never be traversed as const.

```cpp run ok
#include <cstdio>
#include <ranges>
#include <string_view>

int main() {
  auto dw = std::string_view("   hi") |
            std::views::drop_while([](char c) { return c == ' '; });
  static_assert(!std::ranges::range<const decltype(dw)>);
  for (char c : dw | std::views::reverse) std::putchar(c);   // ih
  std::puts("");
}
```

The iterator and the end of `drop_while_view` both come directly from the underlying range, so its iterator category and whether it is a common range are the same as the underlying range's. Its end does not call the predicate, so it is a borrowed range when the underlying range is. This is the opposite of `take_while`, whose sentinel calls the predicate and is therefore not borrowed.

## Common misconceptions

!!! pitfall "Modifying the underlying range after caching"
    ```cpp
    std::list<int> lst{1, 2, 3};
    auto d = lst | std::views::drop(1);
    d.begin();             // cached: points to element 2
    lst.push_front(0);     // lst is now 0 1 2 3
    // d still starts at element 2, not at the new second element 1
    ```
    The same goes for `drop_while`: it caches the position of the first element that fails the predicate, and does not recompute if earlier elements are modified afterwards. This is the same caching problem as in [[range.filter]].

!!! pitfall "Creating the view consumes no input; the first begin() does"
    `views::istream<int>(in) | views::drop(3)` reads nothing by itself. On the first call to `begin()`, `istream_view` reads the first value and `drop` then advances 3 times, taking 4 values from the stream in total; the 4th is the first element of the result.

## Summary

| | `drop(n)` | `drop_while(p)` |
|---|---|---|
| Special cases returning the same kind of view | `empty`, `optional`, `span`, `string_view`, `iota`, `subrange`, `repeat` | none |
| Caches `begin()` | for forward ranges, when the underlying range is not random access + sized | always, for forward ranges |
| Traversable as const | when `const V` is random access and sized | never |
| sized range | when the underlying range is | no |
| borrowed range | when the underlying range is | when the underlying range is |
