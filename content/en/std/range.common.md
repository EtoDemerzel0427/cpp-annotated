---
title: Common and counted views
summary: "views::common turns a view whose iterator and sentinel types differ into one whose begin and end have the same type, for old interfaces that only accept a pair of iterators; views::counted(it, n) turns an iterator and a count into a range, returning a span, a subrange, or a subrange built on counted_iterator depending on what the iterator can do."
updated: 2026-10-19
---

!!! tldr
    - A C++20 range can mark its end with a sentinel of a different type from the iterator, while old interfaces like `std::accumulate` require `first` and `last` to have the same type; `views::common` does the conversion.
    - If the view is already a common range, `views::common` does no wrapping; if it is random access and sized, the end is just computed as an iterator; otherwise it wraps with `common_iterator`, and the iterator category drops to forward at most.
    - Views whose iterators are move-only and not copyable (like `istream_view`) cannot use `views::common`.
    - `views::counted(it, n)` does not check n: fewer than n elements after `it` is undefined behavior, unlike `views::take`, which truncates.

```cpp run ok
#include <cstdio>
#include <list>
#include <numeric>
#include <ranges>

int main() {
  std::list<int> l{1, 2, 3, 4};
  auto t = l | std::views::take(3);          // iterator and end have different types
  auto c = t | std::views::common;           // begin and end have the same type
  int sum = std::accumulate(c.begin(), c.end(), 0);
  std::printf("%d\n", sum);                  // 6
}
```

`std::accumulate(t.begin(), t.end(), 0)` does not compile: `t.begin()` is a `counted_iterator` and `t.end()` is a `default_sentinel_t`, so template argument deduction yields two different types. `views::common` makes them the same type, and then the old interface works. `views::counted` goes the other way: it turns an old-style iterator plus count into a range.

## `views::common` [range.common]

¶1 `common_view` takes a view whose iterator and sentinel have different types and turns it into a view of the same elements whose iterator and sentinel have the same type, i.e. a [[g:common-range|common range]]. ¶2 Note 1 explains its purpose: calling old algorithms that require the iterator and sentinel types to be the same. ¶4 Example 1 is exactly that use:

```cpp
template<forward_range R>
void my_algo(R&& r) {
  auto&& common = views::common(r);
  auto cnt = count(common.begin(), common.end());   // old-style count, requires the same type
}
```

¶3 `views::common(E)` is equivalent to:

- ¶3.1 `views::all(E)` if `E` is already a common range, with no wrapping;
- ¶3.2 otherwise `common_view{E}`.

### Two ways of converting [range.common.view]

`common_view`'s `begin()` and `end()` choose according to what the underlying view can do:

- When the underlying view is random access and sized, `begin()` is just the underlying iterator and `end()` is `begin + distance`. The end is computed as an iterator, and the iterator category stays random access.
- Otherwise, both begin and end are wrapped in `common_iterator<I, S>` ([[iterators.common]]). Internally it is a `variant<I, S>` that can hold either an iterator or a sentinel, and comparison handles the cases separately.

`common_iterator` provides no `--`, so it is at most a forward iterator. `list | take(3)` was a bidirectional range; after `views::common` it becomes a forward range.

The constraints of `common_view` require the underlying iterator to be copyable (`copyable<iterator_t<V>>`), because `common_iterator` requires that. The iterator of `istream_view` is move-only, so `views::istream<int>(in) | views::common` fails to compile.

```cpp run ok
#include <list>
#include <ranges>
#include <vector>

int main() {
  std::list<int> l{1, 2, 3, 4};
  auto t = l | std::views::take(3);
  auto c = t | std::views::common;
  static_assert(std::ranges::bidirectional_range<decltype(t)>);
  static_assert(std::ranges::common_range<decltype(c)>);
  static_assert(!std::ranges::bidirectional_range<decltype(c)>);   // lowered to forward

  std::vector<int> v{1, 2, 3};
  auto same = v | std::views::common;        // already common: just views::all
  static_assert(std::same_as<decltype(same), std::ranges::ref_view<std::vector<int>>>);
}
```

`size()` and `reserve_hint()` are forwarded to the underlying view. When the underlying view is a [[g:borrowed-range|borrowed range]], so is `common_view`.

!!! tip "views::common is needed less and less"
    Since C++23, containers can be constructed with `from_range`, `ranges::to` picks a suitable approach on its own ([[range.utility.conv]]), and all the algorithms in `std::ranges` accept an iterator plus a sentinel. What remains for `views::common` is mainly interaction with third-party libraries or old APIs.

## `views::counted`: an iterator plus a count [range.counted]

¶1 A counted view presents the elements of the **counted range** `i + [0, n)`, i.e. the n elements starting at iterator `i` ([[iterator.requirements.general]]), where n is non-negative.

¶2 `views::counted` is a [[customization.point.object|customization point object]], not a range adaptor, and has no pipe form. Let `T` be the decayed type of `E` and `D` its difference type. If `F` is not convertible to `D` it is ill-formed; Note 1 points out that this results in substitution failure in the immediate context of a template. Otherwise `views::counted(E, F)` is equivalent to:

| Paragraph | `T` is | Result |
|---|---|---|
| ¶2.1 | a contiguous iterator | `span(to_address(E), n)`, dynamic extent |
| ¶2.2 | a random access iterator | `subrange(E, E + n)` |
| ¶2.3 | anything else | `subrange(counted_iterator(E, n), default_sentinel)` |

```cpp run ok
#include <iterator>
#include <list>
#include <ranges>
#include <span>
#include <vector>

int main() {
  std::vector<int> v{1, 2, 3, 4, 5};
  auto c1 = std::views::counted(v.begin() + 1, 3);
  static_assert(std::same_as<decltype(c1), std::span<int>>);

  std::list<int> l{1, 2, 3};
  auto c2 = std::views::counted(l.begin(), 2);
  static_assert(std::same_as<decltype(c2),
      std::ranges::subrange<std::counted_iterator<std::list<int>::iterator>,
                            std::default_sentinel_t>>);
  return (c1[0] == 2 && std::ranges::distance(c2) == 2) ? 0 : 1;
}
```

Things to watch out for:

- n is not checked. `i + [0, n)` must be a valid counted range, or the behavior is undefined. `views::counted(v.begin(), 100)` on a `vector` of 5 elements is {{ub}}; `views::take(100)`, by contrast, truncates to the actual length.
- The result is always a borrowed range (both `span` and `subrange` are); it only refers to the storage `E` points into and does not own the elements.
- The result of ¶2.3 is a sized range (`counted_iterator` and `default_sentinel` can be subtracted), but not a common range.

## Summary

| | `views::common` | `views::counted` |
|---|---|---|
| Kind | range adaptor object, usable with the pipe | customization point object, no pipe |
| Input | a view | an iterator and a count |
| Output | `views::all`, a `common_view` that keeps the original iterator, or a `common_view` built on `common_iterator` | a `span`, a `subrange`, or a `subrange` built on `counted_iterator` |
| Checks | the iterator must be copyable | the count is not checked; it is a precondition |

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[range.common.view] ¶1: the constructor stores the underlying view. The deduction guide `common_view(R&&)` wraps `R` into a view via `views::all_t`.

</details>
