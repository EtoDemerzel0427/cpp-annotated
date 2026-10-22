---
title: Take and take_while views
summary: "views::take takes the first n elements, views::take_while takes the prefix before the predicate first fails; take returns a view of the same kind as its input where it can, take_view picks its iterator based on what the underlying range can do, and both consume one extra element from input ranges."
updated: 2026-10-19
---

!!! tldr
    - `views::take(n)` produces the first n elements; if the underlying range has fewer than n, it gives all of them and never goes out of bounds.
    - When the input is a `span`, `string_view`, `subrange`, `iota_view`, `repeat_view` or `empty_view`, `take` returns a view of the same kind directly instead of wrapping it in a `take_view`.
    - `take_view` uses the underlying iterator when the underlying range is both sized and random access, and the result is a common range; otherwise it uses `counted_iterator`, and the result is not a common range.
    - The end of `views::take_while(pred)` is hidden in its sentinel, and every comparison with the end calls the predicate once; it is never sized and never common.
    - On input ranges such as `istream`, both take one extra value from the stream.

```cpp run ok
#include <cstdio>
#include <ranges>

int main() {
  for (int i : std::views::iota(1) | std::views::take(3))
    std::printf("%d ", i);                              // 1 2 3
  for (int i : std::views::iota(1) | std::views::take_while([](int x) { return x * x < 30; }))
    std::printf("%d ", i);                              // 1 2 3 4 5
  std::puts("");
}
```

`iota(1)` is an infinite sequence. `take` truncates by count and `take_while` truncates by condition; these are the two standard ways to make an infinite sequence usable. Both are [[g:range-adaptor-object|range adaptor objects]]: you can write `views::take(r, n)` or `r | views::take(n)`.

## `views::take`: the first n elements [range.take.overview]

¶1 `take_view` produces a view of the first N elements of another view, or all the elements if that view has fewer than N. So `v | views::take(10)` is safe even when `v` has only 5 elements; the result simply has 5 elements.

¶3 The standard's Example 1 is this most basic usage: take the first 5 of `0..9` and print `0 1 2 3 4`.

### Keep the original type when possible (¶2)

```cpp run ok
#include <ranges>
#include <span>
#include <vector>

std::vector<int> v{1, 2, 3, 4, 5};

auto s = std::span(v) | std::views::take(3);
static_assert(std::same_as<decltype(s), std::span<int>>);

auto io = std::views::iota(0, 10) | std::views::take(3);
static_assert(std::same_as<decltype(io), std::ranges::iota_view<int, int>>);

auto t = v | std::views::take(3);
static_assert(std::same_as<decltype(t),
    std::ranges::take_view<std::ranges::ref_view<std::vector<int>>>>);

int main() {}
```

Taking the first 3 of a `span` gives a `span` again, which can be passed directly to functions that only accept `span`, and avoids types nested layer upon layer like `take_view<take_view<...>>`. That does not work for a `vector`, which only yields a `take_view`; if you want a `span`, write `std::span(v)` first.

¶2 The exact rules are as follows. Let `T` be the type of `E` with references and cv-qualifiers removed, and `D` its difference type (`range_difference_t`). If `F` is not convertible to `D`, `views::take(E, F)` is ill-formed; otherwise it is expression-equivalent ([[g:expression-equivalent]]) to the first applicable form in the table:

| Paragraph | `T` is | Result |
|---|---|---|
| ¶2.1 | a specialization of `empty_view` | a copy of `E` (`F` is still evaluated) |
| ¶2.2 | a specialization of `optional` that models `view` {{c++26}} | an empty `T()` if `F` is 0, otherwise a copy of `E` |
| ¶2.3 | a random access, sized `span`, `basic_string_view` or `subrange` | a view of the same kind over `[begin, begin + min(distance(E), F))` |
| ¶2.4 | a random access, sized `iota_view` | a shorter `iota_view` |
| ¶2.5 | `repeat_view` | a `repeat` of `min(distance(E), F)` times if bounded, `F` times if unbounded |
| ¶2.6 | anything else | `take_view(E, F)` |

In ¶2.3 the result for `span` is a dynamic-extent `span<element_type>`, and for `subrange` it is `subrange<iterator_t<T>>`. These special cases come from [[P1739R4]]; the `optional` row comes from [[P3168R2]], which made `optional` a view. At the time of writing, the libc++ we test with does not yet support `optional` as a view.

The rules only look at what `T` itself is, not whether it can be converted to a `span`. Also, ¶2.5 makes `views::repeat(7) | views::take(3)` directly a bounded `repeat_view` that repeats 3 times.

## How `take_view` finds its end [range.take.view]

When a `take_view` really has to be constructed, it stores just two things: the underlying view `base_` and the count `count_`. ¶1 The constructor requires `count >= 0`, and ¶2 stores both in members.

`begin()` and `end()` choose one of three approaches according to what the underlying view can do:

| Underlying view | `begin()` | `end()` | Common range? |
|---|---|---|---|
| sized and random access | the underlying iterator | `begin + min(size, n)` | yes |
| otherwise, but the length can be computed up front | `counted_iterator` with count `min(length, n)` | `default_sentinel` | no |
| length unknown | `counted_iterator` with count `n` | `take_view::sentinel` | no |

[[counted.iterator|`counted_iterator`]] bundles an iterator with a remaining count; each `++` advances the underlying iterator and decrements the count. The second row covers two cases: the underlying range is a sized range (`std::list`), or the underlying sentinel and iterator can be subtracted. Then the count has already been clamped to at most the actual length, reaching zero means the end, and so the end only needs a `default_sentinel`.

Only when the length cannot be known in advance is the dedicated sentinel `take_view::sentinel` needed ([range.take.sentinel] ¶4). It stores the underlying end, and when compared with a `counted_iterator`, either the count reaching zero or the underlying range reaching its end counts as the end.

```cpp run ok
#include <cstdio>
#include <list>
#include <ranges>
#include <vector>

int main() {
  std::vector<int> v{1, 2, 3, 4, 5};
  auto t = v | std::views::take(10);          // only 5 elements, no overrun
  static_assert(std::ranges::random_access_range<decltype(t)>);
  static_assert(std::ranges::common_range<decltype(t)>);

  std::list<int> l{1, 2, 3};
  auto tl = l | std::views::take(2);          // counted_iterator + default_sentinel
  static_assert(!std::ranges::common_range<decltype(tl)>);

  std::printf("%zu %zu\n", t.size(), tl.size());   // 5 2
}
```

The other properties of `take_view` follow the underlying view: it is a sized range when the underlying range is, with `size()` returning `min(underlying size, n)`; it is a [[g:borrowed-range|borrowed range]] when the underlying range is; and `begin()` does no caching, so it can be traversed as const whenever the underlying range can.

Since C++26, `take_view` always has `reserve_hint()` (used by `ranges::to` in [[range.utility.conv]] to reserve capacity). When the underlying length is unknown, `n` itself is an upper bound, so even `views::iota(0) | views::take(1000) | ranges::to<std::vector>()` can reserve 1000 elements up front.

!!! pitfall "Reading one extra element on input ranges"
    `counted_iterator`'s `++` advances the underlying iterator first and then decrements the count. After the n-th element has been taken, the loop's final `++` still advances the underlying range. For an `istream_view`, that means reading one more value from the stream:

    ```cpp run ok
    #include <cstdio>
    #include <ranges>
    #include <sstream>

    int main() {
      std::istringstream in{"1 2 3 4 5"};
      for (int x : std::views::istream<int>(in) | std::views::take(3))
        std::printf("%d ", x);
      int next = 0;
      in >> next;
      std::printf("| next=%d\n", next);   // next=5: 4 has already been read by take
    }
    ```

    When reading from a pipe or network, this loses a message. When you need to consume exactly n elements, use a count-driven algorithm (such as `ranges::copy_n`) or a hand-written loop.

## `views::take_while`: the prefix that satisfies a condition [range.take.while]

¶1 Given a unary predicate `pred` and a view `r`, `take_while_view` produces the range `[begin(r), find_if_not(r, pred))`, i.e. from the start up to the first element that does not satisfy `pred`. ¶2 `views::take_while(E, F)` is equivalent to `take_while_view(E, F)`, with no special cases.

### The end is in the sentinel [range.take.while.view]

`take_while_view`'s `begin()` is just the underlying `begin()`, and its iterator is the underlying iterator. When to stop is decided entirely by the sentinel. [range.take.while.sentinel] ¶3 specifies that comparing an iterator `x` with the sentinel gives:

```cpp
return y.end_ == x || !invoke(*y.pred_, *x);
```

Several properties follow:

- Every comparison with the end calls the predicate once. A range-based `for` compares once per iteration, so the predicate is called at least once per element.
- Without traversing you cannot know where it stops, so it is never a sized range and never a common range.
- The sentinel stores a pointer to the predicate inside the view, so it is not a borrowed range.
- The view calls the predicate as `const Pred` (the constraint is `indirect_unary_predicate<const Pred, ...>`), so `mutable` lambdas cannot be used.

```cpp run ok
#include <ranges>
#include <vector>

int main() {
  std::vector<int> v{1, 2, 3, 4, 5};
  auto tw = v | std::views::take_while([](int x) { return x < 3; });
  static_assert(!std::ranges::common_range<decltype(tw)>);
  static_assert(!std::ranges::sized_range<decltype(tw)>);
}
```

When an older interface needs a pair of iterators of the same type, go through `views::common` first ([[range.common]]).

### It also reads one extra (¶3)

[range.take.while.overview] ¶3 Example 1 takes all numbers less than 5 from `"0 1 2 3 4 5 6 7 8 9"` and prints `0 1 2 3 4`. A subsequent `input >> i` then reads 6, because 5 has already been read out to be tested by the predicate.

The reason differs from `take`'s extra read: `take_while` has to see the first element that fails the condition before it knows to stop, and by then that element has left the stream.

```cpp run ok
#include <iostream>
#include <ranges>
#include <sstream>

int main() {
  auto input = std::istringstream{"0 1 2 3 4 5 6 7 8 9"};
  auto small = [](const auto x) noexcept { return x < 5; };
  for (const auto i : std::views::istream<int>(input) | std::views::take_while(small))
    std::cout << i << ' ';                    // 0 1 2 3 4
  auto i = 0;
  input >> i;
  std::cout << i << '\n';                     // 6
}
```

## Summary

| | `take(n)` | `take_while(p)` |
|---|---|---|
| Special cases returning the same kind of view | `empty`, `optional`, `span`, `string_view`, `subrange`, `iota`, `repeat` | none |
| Iterator | underlying iterator or `counted_iterator` | underlying iterator |
| sized range | when the underlying range is | no |
| common range | when the underlying range is sized and random access | no |
| borrowed range | when the underlying range is | no |
| On input ranges | advances the underlying range one extra time | reads out the first element that fails the condition |

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[range.take.sentinel] ¶1–3: the sentinel's constructor stores the underlying end; `sentinel<false>` converts to `sentinel<true>`; `base()` returns the stored underlying end.

[range.take.while.view] ¶1–2: the constructor stores the underlying view and the predicate; `pred()` returns a reference to the predicate. [range.take.while.sentinel] ¶1–2 are the sentinel's two constructors.

Both views provide deduction guides, `take_view(R&&, range_difference_t<R>)` and `take_while_view(R&&, Pred)`, which wrap `R` into a view via `views::all_t`.

</details>
