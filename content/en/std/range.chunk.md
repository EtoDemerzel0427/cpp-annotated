---
title: Chunk, slide, chunk_by and stride views
summary: "C++23's four grouping and striding views: chunk(n) cuts into non-overlapping blocks, slide(n) gives overlapping windows, chunk_by(pred) splits by the relation between adjacent elements, and stride(n) takes every n-th element; n must be positive, and several of these views cache begin() or end() when necessary."
updated: 2026-10-19
---

!!! tldr
    - For `1 2 3 4 5`: `chunk(2)` gives `[1,2] [3,4] [5]`, `slide(2)` gives `[1,2] [2,3] [3,4] [4,5]`, `stride(2)` gives `1 3 5`.
    - `chunk_by(pred)` calls `pred` on each pair of adjacent elements and splits where the result is `false`; `chunk_by(less_equal{})` cuts a sequence into non-decreasing runs.
    - The n of `chunk`, `slide` and `stride` must be greater than 0, otherwise the behavior is undefined.
    - On input ranges, `chunk` keeps the read position in the view and can be traversed only once; advancing before finishing a block skips the rest of its elements.
    - `stride` remembers how many steps the last move fell short by, so reverse traversal lands on the same elements as forward traversal.

| View | Result | Input `1 2 3 4 5` |
|---|---|---|
| `chunk(2)` | non-overlapping blocks; the last may be partial | `[1,2] [3,4] [5]` |
| `slide(2)` | overlapping windows; empty if fewer than n elements | `[1,2] [2,3] [3,4] [4,5]` |
| `chunk_by(less{})` | adjacent elements stay in the same run while the predicate is `true` | `[1,2,3,4,5]` |
| `stride(2)` | the first of every n | `1 3 5` |

`chunk` and `slide` come from [[P2442R1]], `chunk_by` from [[P2443R1]], and `stride` from [[P1899R3]].

!!! impl "Implementation status"
    At the time of writing, the libc++ we test with provides `views::chunk_by` and `views::stride` but not yet `views::chunk` or `views::slide` (`__cpp_lib_ranges_chunk` and `__cpp_lib_ranges_slide` in `<version>` are commented out). The `chunk` code below follows the standard's text and has not been compiled.

## `views::chunk`: non-overlapping blocks [range.chunk]

```cpp
#include <cstdio>
#include <ranges>
#include <vector>

int main() {
  std::vector<int> v{1, 2, 3, 4, 5};
  for (auto blk : v | std::views::chunk(2)) {
    std::printf("[");
    for (int x : blk) std::printf("%d", x);
    std::printf("]");
  }
  std::puts("");                              // [12][34][5]
}
```

[range.chunk.overview] ¶1 `chunk_view` takes a view and a number N and produces a range of views that are N-sized non-overlapping successive chunks of the elements of the original view, in order; the last chunk may have fewer than N elements. ¶2 `views::chunk(E, N)` is equivalent to `chunk_view(E, N)`. The constructor's precondition is `n > 0`, so `chunk(0)` is {{ub}}.

The standard gives `chunk_view` two definitions: one for when the underlying range is only an input range, and another for when it is a forward range.

### Input ranges: the state lives in the view [range.chunk.view.input]

A single-pass sequence has only one read position, so two iterators cannot stop at different places. This version therefore stores both the current position `current_` (a [[range.nonprop.cache|non-propagating-cache]]) and the number of elements left in the current chunk, `remainder_`, in the view object; the outer iterator ([range.chunk.outer.iter]) and the inner iterator ([range.chunk.inner.iter]) each store only a pointer to the view. ¶3 `begin()` sets `current_` to the underlying start and `remainder_` to n.

Several properties follow:

- It can be traversed only once and has no const `begin()`.
- The `value_type` of the outer iterator ([range.chunk.outer.value]) represents the current chunk; traversing it just continues reading from the stream.
- If the outer iterator is advanced before a chunk has been fully read, the outer iterator first reads off the remaining elements of that chunk, so that the next chunk starts at the right position.

### Forward ranges: each chunk is a slice of the underlying range [range.chunk.view.fwd]

When the underlying range is a forward range, the iterator ([range.chunk.fwd.iter]) itself stores the start of the current chunk `current_`, the underlying end `end_`, the chunk length n, and how many elements the last chunk is short by, `missing_`; the latter is used to align reverse traversal.

Dereferencing returns `views::take(subrange(current_, end_), n)`. By the rules in [[range.take]], when the underlying range is random access and sized, this is simply a `subrange`, random access and with `size()`. The iterator category is the same as the underlying range's, up to random access; `iterator_category` is always `input_iterator_tag`, because dereferencing yields a prvalue.

In both definitions, `size()` is the underlying size divided by n, rounded up. `chunk_view` is a [[g:borrowed-range|borrowed range]] when the underlying range is a forward range and a borrowed range.

## `views::slide`: overlapping windows [range.slide]

¶1 The M-th element of `slide_view` is a view over the M-th through (M+N−1)-th elements of the original view; if the original view has fewer than N elements, the result is empty. ¶2 `views::slide(E, N)` is equivalent to `slide_view(E, N)`. [range.slide.view] ¶1 The precondition is `n > 0`.

Compared with `adjacent<N>` in [[range.zip]], the window length of `slide` is given at run time, and its elements are subranges rather than tuples: [range.slide.iterator] ¶6 dereferencing returns `views::counted(current_, n)` ([[range.common]]), which is a `span` when the underlying range is contiguous. The underlying range must be a forward range.

### Caching the start or the end

A window iterator often needs to know where the last element of its window is. The standard uses three exposition-only concepts to decide how to handle this:

| Concept | Condition | Approach |
|---|---|---|
| *slide-caches-nothing* | underlying range is random access and sized | `begin()` and `end()` can both be computed in O(1); no caching; const traversal possible |
| *slide-caches-last* | not the above; underlying range is bidirectional and common | ¶6 `end()` finds the start of the last window with `ranges::prev(end, n - 1)`; ¶7 `end()` is cached |
| *slide-caches-first* | otherwise | the iterator also remembers the last element of the current window; ¶3 `begin()` first walks n−1 steps; ¶4 `begin()` is cached |

The last two cases both modify the view object, so there is no const traversal. `slide_view`'s borrowedness is the same as the underlying range's. ¶9 `size()` is the underlying size minus n plus 1, at least 0.

## `views::chunk_by`: splitting by adjacent relation [range.chunk.by]

¶1 `chunk_by_view` takes a view and a predicate, and splits the view between each pair of adjacent elements for which the predicate returns `false`. ¶2 `views::chunk_by(E, F)` is equivalent to `chunk_by_view(E, F)`.

```cpp run ok
#include <cstdio>
#include <functional>
#include <ranges>
#include <vector>

int main() {
  std::vector<int> v{1, 2, 2, 3, 0, 4, 5, 2};
  for (auto run : v | std::views::chunk_by(std::ranges::less_equal{})) {
    std::printf("[");
    for (int x : run) std::printf("%d", x);
    std::printf("]");
  }
  std::puts("");                                // [1223][045][2]
}
```

The predicate is binary and compares two adjacent elements, not the current element and the first element of the run. The example splits between `3, 0` and between `5, 2`, because neither `3 <= 0` nor `5 <= 2` holds.

- The underlying range must be a forward range; the element type is `subrange<iterator_t<V>>`; the iterator ([range.chunk.by.iter]) stores the start of the current run and the start of the next run, and is at most bidirectional.
- [range.chunk.by.view] ¶8 The start of the next run is found by `adjacent_find(current, end, not_fn(pred))` advanced one more step. ¶4 `begin()` must first find the end of the first run, so ¶5 caches the result, and there is no const `begin()`.
- `chunk_by_view` is not a borrowed range.

How it differs from [[range.split]]: `split` cuts at a fixed delimiter and discards the delimiter itself; `chunk_by` cuts by the relation between adjacent elements and discards nothing.

## `views::stride`: every n-th element [range.stride]

¶1 `stride_view` traverses the underlying sequence advancing n elements at a time instead of 1. ¶2 `views::stride(E, N)` is equivalent to `stride_view(E, N)`. [range.stride.view] ¶1 The precondition is `n > 0`.

```cpp run ok
#include <cstdio>
#include <ranges>

int main() {
  auto input = std::views::iota(0, 12) | std::views::stride(3);
  for (int x : input) std::printf("%d ", x);                         // 0 3 6 9
  for (int x : input | std::views::reverse) std::printf("%d ", x);   // 9 6 3 0
  for (int x : std::views::iota(0, 10) | std::views::stride(3) | std::views::reverse)
    std::printf("%d ", x);                                           // 9 6 3 0
  std::puts("");
}
```

The first two lines are Example 1 in [range.stride.overview] ¶3. In the third line the underlying range is `0..9`, and stepping back by 3 from 9 also happens to give `9 6 3 0`; the key point is that reverse traversal starts not at the last underlying element but at the element forward traversal last reached.

To achieve this, besides the current position, the underlying end and the stride, the iterator ([range.stride.iterator]) stores `missing_`: `++` advances with `ranges::advance(current_, n, end_)`, stops at the end, and records how many steps it fell short by. `--` first makes up the missing steps and then steps back by the stride, so the positions in reverse traversal match forward traversal exactly.

The iterator category of `stride_view` is the same as the underlying range's, up to random access; ¶4 `size()` is the underlying size divided by n, rounded up; there is no caching; borrowedness is the same as the underlying range's.

## Summary

| View | Underlying requirement | Elements | Caching | Borrowed range |
|---|---|---|---|---|
| `chunk(n)` | input or forward | a chunk; `take(subrange, n)` for forward | the input version keeps its state in the view | when the underlying range is forward and borrowed |
| `slide(n)` | forward | `views::counted(it, n)` | depends on the underlying range: none, `begin()`, or `end()` | when the underlying range is |
| `chunk_by(p)` | forward | `subrange` | caches `begin()` | no |
| `stride(n)` | input | the underlying elements | none | when the underlying range is |

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[range.chunk.view.input] ¶2, [range.chunk.view.fwd] ¶2, [range.slide.view] ¶2, [range.stride.view] ¶2: the constructors store the underlying view and n. [range.chunk.view.input] ¶4 `end()` returns `default_sentinel`. Each view's `reserve_hint()` uses the same formula as its `size()`.

[range.chunk.by.view] ¶1–3, ¶7, ¶9–¶10: the constructor, `pred()`, the precondition that the predicate is present, and *find-prev*, which searches backwards for the start of the previous run. The sentinel in [range.slide.sentinel] is used only when the underlying range belongs to *slide-caches-first* and is not a common range ([range.slide.view] ¶6.4). [range.stride.view] ¶3 `stride()` returns the stride.

</details>
