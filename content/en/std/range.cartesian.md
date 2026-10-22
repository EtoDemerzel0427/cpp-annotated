---
title: Cartesian product view
summary: "C++23's views::cartesian_product lays out all combinations of several ranges as one flat view, in the same order as nested loops; the first range can be merely an input range, the rest must be forward ranges; the type of size() is implementation-defined, and the product must fit in it."
updated: 2026-10-19
---

!!! tldr
    - `views::cartesian_product(A, B, C)` yields every combination `(a, b, c)` in turn, with the last range varying fastest, in the same order as three nested loops.
    - Each element is a `tuple` holding references to the components; the result can be followed by adaptors such as `filter` and `take`, or handed to algorithms.
    - The first range can be merely an input range; the rest must be forward ranges, because each inner loop has to start over on every round.
    - If any range other than the first is empty, the whole result is empty; with no arguments at all, the result is a view containing a single empty tuple.
    - The types of `size()` and `difference_type` are implementation-defined, and the product of all the range sizes must be representable in them.

```cpp
#include <cstdio>
#include <ranges>
#include <vector>

int main() {
  std::vector<int> xs{1, 2};
  std::vector<char> ys{'a', 'b', 'c'};
  for (auto [x, y] : std::views::cartesian_product(xs, ys))
    std::printf("%d%c ", x, y);               // 1a 1b 1c 2a 2b 2c
  std::puts("");

  // find all (i, j) with i*i + j*j == 25
  auto sq = std::views::cartesian_product(std::views::iota(0, 6), std::views::iota(0, 6))
          | std::views::filter([](auto t) { auto [i, j] = t; return i * i + j * j == 25; });
  for (auto [i, j] : sq) std::printf("(%d,%d)", i, j);   // (0,5)(3,4)(4,3)(5,0)
  std::puts("");
}
```

The first loop above is equivalent to `for (int x : xs) for (char y : ys) ...`. Once written as a range, a nested loop can be connected to other adaptors; the second example uses `filter` to select combinations this way. This view comes from C++23's [[P2374R4]].

!!! impl "Implementation status"
    At the time of writing, the libc++ we test with does not yet provide `views::cartesian_product`. The code on this page follows the standard's text and has not been compiled.

## `views::cartesian_product` [range.cartesian.overview]

¶1 `cartesian_product_view` takes a non-zero number of ranges and produces the n-ary cartesian product of them, each element being a tuple. ¶2 `views::cartesian_product` is a [[customization.point.object|customization point object]]:

- ¶2.1 With no arguments, the result is `views::single(tuple())`. By mathematical convention, the cartesian product of zero sets contains one element, the empty tuple, just as the empty product equals 1.
- ¶2.2 Otherwise it is `cartesian_product_view<views::all_t<decltype((Es))>...>(Es...)`.

¶3 Example 1 computes `cartesian_product(v, v, v)` for `v = {0, 1, 2}`, yielding `0 0 0`, `0 0 1`, `0 0 2`, `0 1 0`, …, i.e. lexicographic order.

## The iterator is like a multi-digit counter [range.cartesian.view]

```cpp
template<input_range First, forward_range... Vs>
  requires (view<First> && ... && view<Vs>)
class cartesian_product_view;
```

The iterator stores a tuple of iterators, one into each range. `++` starts from the last component: it advances one step, and if it reaches the end, it is reset to the start of its range and the previous component advances one step. This is the same process as adding 1 to a multi-digit number and carrying on overflow.

This also explains the requirements on the template parameters: every range except the first is reset to its start on a carry, which amounts to traversing it again, so it must be a forward range; the first range is walked only once, so an input range suffices.

### Conditions for each capability

| Capability | Condition (exposition-only concepts) | Reason |
|---|---|---|
| random access | all random access, and all but the first sized | `it += n` has to split n by the length of each dimension, which requires knowing those lengths |
| bidirectional | all bidirectional, and all but the first either common or random access and sized | on a borrow, `--` has to jump to the last element of an inner dimension, so its end iterator must be obtainable |
| common range | the first range is common, or random access and sized | the end iterator is built from the first range's end iterator |
| sized | all sized | the size is the product of the dimension sizes |

`cartesian_product_view` is not a borrowed range. When all the ranges can be traversed as const, so can it (¶3).

### The end and empty ranges (¶4–¶6)

In the common-range case, ¶5 `end()` returns an iterator whose first component is the end of the first range and whose other components are at their respective starts. That is exactly the state after the final carry overflows.

But if some range other than the first is empty, the whole product is empty, and `end()` must then equal `begin()`. ¶4.2 defines *is-empty* for this: in that case the first component also takes the start rather than the end.

When the result is not a common range, ¶6 `end()` returns `default_sentinel`. [range.cartesian.iterator] ¶23 specifies that an iterator equals this sentinel when any of its components has reached the end of its range, which also covers the case of an empty inner range.

### The type of size() (¶7–¶11)

Multiplying three ranges of size 2³² already exceeds the range of a 64-bit integer. So ¶7 specifies that the return type of `size()` is an implementation-defined unsigned integer-like type (which may be a class type wider than `size_t`, see [[iterator.concept.winc]]). ¶8 recommends the smallest type that can hold the product of the maximum sizes of all the ranges. ¶9–¶11 return the product p of the range sizes, with the precondition that p is representable in the return type.

Likewise, the iterator's `difference_type` is an implementation-defined signed integer-like type ([range.cartesian.iterator] ¶2–¶3). Random access operations require the distance, converted according to the length of each dimension, to be representable in it (¶7).

## Summary

- The order is the same as nested loops, with the last range varying fastest; the first range can be an input range, the rest must be forward ranges.
- Random access, bidirectional, common and sized each have their own conditions; at heart they all need the length or the end of every dimension but the first.
- If any non-first dimension is empty, the whole is empty; with no arguments you get `single(tuple())`.
- The type of `size()` is implementation-defined, and the product must fit in it.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[range.cartesian.view] ¶1–¶3: the constructor stores all the ranges; `begin()` is made up of the starts of all the ranges.

[range.cartesian.iterator] ¶1 specifies the iterator category; ¶4–¶5 are *next* and *prev*, used for carrying and borrowing; ¶6–¶8 are *distance-from*, which computes the distance between two positions; ¶9–¶10 are the constructors; the remaining paragraphs specify increment and decrement, `+=` (¶15–¶19, constant complexity), comparison, subtraction, `iter_move` and `iter_swap`.

</details>
