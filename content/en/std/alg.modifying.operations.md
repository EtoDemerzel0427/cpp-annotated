---
title: Mutating sequence operations
summary: "Algorithms that write elements: the overlap rules of copy and move and their _backward versions, when transform may work in place, why remove and unique only move elements and do not change the container's size, the return value of rotate, the randomness of sample and shuffle, shift_left and shift_right, and the return values of C++26's bounded-output overloads."
updated: 2026-10-19
---

!!! tldr
    - `copy` only requires `result` not to be in `[first, last)`: an overlapping copy that moves elements left is valid; moving right needs `copy_backward`.
    - `transform` allows `result` to equal exactly the start of the input, i.e. an in-place transform; a partial overlap at an offset is undefined behavior.
    - `remove` and `unique` only move the kept elements to the front and return the new logical end, without changing the container's size; the elements at the tail are in a valid but unspecified state and must be removed with `erase`.
    - `unique` only collapses adjacent duplicates; to deduplicate globally, sort first.
    - `shuffle` and `sample` use only the random number generator passed in, but the standard does not specify the algorithm, so the same seed gives different results on different standard libraries.

The algorithms in this subclause write: either into another output range (`copy`, `transform`, the various `_copy`s), or by rearranging the original range in place (`remove`, `unique`, `reverse`, `rotate`, `shuffle`, `shift_left`). Compared with the read-only algorithms, their wording adds three kinds of requirements:

1. **Writable**: *Mandates* say "`*first` is writable to `result`" ([[iterator.requirements.general]]); if not, compilation fails;
2. **Overlap**: *Preconditions* say `result` is not in some range, or that two ranges do not overlap; violating them is {{ub}};
3. **Element types**: the classic versions that rearrange in place require *Cpp17MoveAssignable*, *Cpp17ValueSwappable* and so on, while the `ranges` versions express this with concepts such as `permutable` ([[alg.req]]).

## Copying and moving [alg.copy], [alg.move]

```cpp run title="overlap.cpp" ok
#include <algorithm>
#include <cassert>
#include <vector>

int main() {
  // shift right by two: the ranges overlap, so use copy_backward, passing the end of the destination
  std::vector<int> v{1, 2, 3, 4, 5, 0, 0};
  std::copy_backward(v.begin(), v.begin() + 5, v.end());
  assert((v == std::vector<int>{1, 2, 1, 2, 3, 4, 5}));

  // shift left by two: result is not in [first, last), so copy can handle it
  std::vector<int> w{0, 0, 1, 2, 3};
  std::copy(w.begin() + 2, w.end(), w.begin());
  assert((w == std::vector<int>{1, 2, 3, 2, 3}));
}
```

### The overlap rule of `copy`

The precondition of [alg.copy] ¶2 is that `result` is not in `[first, last)`. That is not the same as the two ranges not overlapping:

- Moving left, with `result` before `first`, the ranges may overlap. ¶3 specifies performing `*(result + n) = *(first + n)` in order starting from `first`, so each element is read before it is overwritten.
- Moving right with overlap, `result` falls within `(first, last)`, which is {{ub}}: by the semantics of assigning one by one going forward, later elements would be overwritten before they are read.

Moving right needs `copy_backward` (¶26–¶30). Its third argument is the end of the destination range; it copies backward from `last - 1`, and the precondition becomes, symmetrically, that `result` is not in `(first, last]`. Footnote 180 says that `copy_backward` should be used instead of `copy` when `last` is in the range `[result - N, result)`.

¶4 The classic version returns `result + N`; the `ranges` version returns `{last, result + N}`, also giving the caller back how far the input got ([[algorithms.results]]).

!!! impl "Why an overlapping `copy` often happens to work"
    For contiguous ranges of trivially copyable elements, libc++ and libstdc++ replace `copy` and `move` with `memmove`, which handles any overlap. So an overlapping right-shifting copy of a `vector<int>` often gives the right result. With a non-trivial element type or non-contiguous iterators, the implementation assigns one by one and reads values that have already been overwritten. By the standard, such a call is undefined behavior in every case.

### `copy_n` and `copy_if`

`copy_n` (¶12–¶18) copies `max(0, n)` elements; a negative `n` is treated as 0.

`copy_if` (¶19–¶25) copies only the elements that satisfy the predicate. ¶21 requires the input and output ranges not to overlap at all, stricter than `copy`, because output positions no longer correspond one-to-one with input positions. ¶25 It is **stable** ([[algorithm.stable]]): the copied elements keep their original relative order.

### `move` and `move_backward`

[alg.move] has exactly the same structure as `copy`, except that the right-hand side of the assignment is *E*(n) from ¶1: `std::move(*(first + n))` for the classic version and `ranges::iter_move(first + n)` for the `ranges` version. The latter is a customization point that moves correctly even for proxy iterators like those of `views::zip`. `move_backward` corresponds to `copy_backward`. Moved-from source elements are in a valid but unspecified state ([[lib.types.movedfrom]]).

### C++26's bounded output

C++26's parallel `ranges` overloads generally accept an output bound: `result_last`, or an output range `result_r`. The wording uniformly writes "Let `result_last` be `result + (last - first)` for the overloads with no parameter `result_last` or `result_r`", and then lets N be `min(last - first, result_last - result)`: versions without a bound treat the bound as exactly enough.

When the output is full the algorithm stops, and the return value then has to tell the caller how far the input was processed. ¶23.3 specifies that `copy_if` then returns `{j, result_last}`, where `j` is the first element that satisfies the condition but was not copied, so the caller can continue from there.

## Swapping [alg.swap]

`swap_ranges` swaps the elements of two ranges pairwise. ¶2 The two ranges must not overlap, and the classic version also requires the elements to be swappable pairwise ([[swappable.requirements]]). ¶3 The classic version calls `swap` unqualified, so ADL can find a user-defined `swap`; the `ranges` version uses `ranges::iter_swap`. ¶1 The classic three-iterator version lets `last2` be `first2 + (last1 - first1)`, assuming, like three-iterator `equal`, that the second range is long enough.

¶7 The effect of `iter_swap(a, b)` is as if by `swap(*a, *b)`.

## `transform` [alg.transform]

```cpp
std::transform(v.begin(), v.end(), v.begin(), f);      // OK: in-place transform
std::transform(v.begin(), v.end(), v.begin() + 1, f);  // UB: offset by one
```

¶3 `transform` assigns to each position of the output range the result of applying `op` to the corresponding input elements. The precondition in ¶2 requires that `op` and `binary_op` not invalidate iterators or subranges, nor modify elements in the closed ranges `[first1, first1 + N]`, `[first2, first2 + N]` and `[result, result + N]`. Footnote 182 explains that the closed ranges are intentional: the past-the-end position counts too, so `op` cannot `push_back` into a `vector` and invalidate `end()`.

The *Remarks* in ¶6 explicitly allow `result` to equal `first1` or `first2`, i.e. an in-place transform. Only exact equality is allowed. With `result == first1 + 1`, writing `*(result + i)` modifies an element of the input range that has not been read yet, violating ¶2.

¶5 `transform` applies `op` exactly N times, and states specifically that this requirement also applies to the parallel overloads, rather than being relaxed to O(N) per [[algorithms.parallel.overloads#3]].

## `replace`, `fill`, `generate`

- [alg.replace] `replace` and `replace_if` replace the elements that satisfy the condition with `new_value`; ¶2 requires `new_value` to be writable to `first`. ¶4 The classic version returns `void`, the `ranges` version returns `last`. For the `replace_copy` family, ¶9 requires the ranges not to overlap.
- [alg.fill] `fill_n` writes `max(0, n)` elements and ¶4 returns `first + N`. C++03's `fill_n` returned `void`; C++11 changed it to return an iterator.
- [alg.generate] `generate` calls `gen()` exactly N times (¶5). ¶6 In the parallel version `gen` may modify objects through its arguments, an exception to [[algorithms.parallel.user]], because generators are almost always stateful. The order in which the parallel version calls `gen()` is unspecified.

## `remove`: moving, not deleting [alg.remove]

```cpp run title="remove.cpp" ok
#include <algorithm>
#include <cassert>
#include <string>
#include <vector>

int main() {
  std::vector<std::string> v{"a", "x", "b", "x", "c"};
  auto it = std::remove(v.begin(), v.end(), "x");  // only moves elements; size unchanged
  assert(v.size() == 5 && it - v.begin() == 3);
  v.erase(it, v.end());                            // the erase-remove idiom
  assert((v == std::vector<std::string>{"a", "b", "c"}));

  std::vector<int> w{1, 2, 2, 3, 2};
  auto n = std::erase(w, 2);                       // C++20: in one step
  assert(n == 3 && (w == std::vector<int>{1, 3}));

  auto sub = std::ranges::remove(w, 3);            // returns {j, last}
  w.erase(sub.begin(), sub.end());
  assert(w == std::vector<int>{1});
}
```

¶3 says `remove` "eliminates" the elements that satisfy the condition, but it only has a pair of iterators and cannot change the size of the container. What it actually does is move the elements to be kept forward one by one, and ¶4 returns the new logical end `j`. ¶6 It is stable.

!!! std
    Each element in the range `[ret, last)`, where `ret` is the returned value, has a valid but unspecified state, because the algorithms can eliminate elements by moving from elements that were originally in that range.

Note 1 in ¶7 explains the state of the tail `[ret, last)`: the implementation moves elements with move assignment (¶2 requires *Cpp17MoveAssignable*), so the tail may hold moved-from empty objects, or still the original values. You may assign to them or destroy them; do not rely on their values.

¶4.2 The `ranges` version returns `{j, last}`, which is exactly the part to erase, so it can be passed directly to `erase`. Since C++20, the standard containers also have the non-member functions `std::erase` and `std::erase_if`, which do erase-remove in one step ([[sequence.reqmts]]).

!!! pitfall "`remove(v.begin(), v.end(), v[0])`"
    `value` is passed as a `const T&`. When it refers to an element of the sequence, `remove` may overwrite it while moving elements, after which comparisons use the wrong value; the standard provides no guarantee for this aliasing case. With libc++ in our tests, running `v.erase(std::remove(v.begin(), v.end(), v[0]), v.end())` on `{1, 2, 1, 3, 2}` gives `{2, 1, 3}` rather than `{2, 3, 2}`; `std::erase(w, w[0])` gives the same result. Make a copy first, `auto x = v[0];`, and pass that.

`remove_copy` and `remove_copy_if` (¶8–¶15) copy the elements that do not satisfy the condition into the output range; ¶11 requires the ranges not to overlap, and ¶15 they are stable too.

## `unique`: collapsing only adjacent elements [alg.unique]

```cpp run title="unique.cpp" ok
#include <algorithm>
#include <cassert>
#include <vector>

int main() {
  std::vector<int> v{1, 1, 2, 1, 1, 3};
  v.erase(std::unique(v.begin(), v.end()), v.end());
  assert((v == std::vector<int>{1, 2, 1, 3}));   // only adjacent duplicates are collapsed

  std::vector<int> w{3, 1, 3, 2, 1};
  std::ranges::sort(w);                           // global deduplication: sort first
  auto [first, last] = std::ranges::unique(w);
  w.erase(first, last);
  assert((w == std::vector<int>{1, 2, 3}));
}
```

In ¶1, *E*(i) is `pred(*(i - 1), *i)`: each element is compared only with the one before it. So `unique` removes consecutive duplicates, and global deduplication requires sorting first. Like `remove`, it returns the new logical end, and the `ranges` version returns the `subrange` to erase (¶4).

¶2 requires `pred` to be an equivalence relation. Using a predicate like `[](int a, int b) { return b - a == 1; }` to remove consecutively increasing elements is {{ub}}: the actual result depends on whether the implementation compares a new element with the last kept element or with the previous element of the original sequence. ¶5 For a non-empty range, the predicate is applied exactly `N - 1` times.

¶9.2.2 of `unique_copy` splits its requirements on the element type into three cases, all because the algorithm must be able to read the previous element:

- The input uses forward iterators: the input can be re-read, so there is no extra requirement;
- Otherwise, if the output uses forward iterators with the same value type: the already-written element can be read back, so only copy assignability of the value type is required;
- Otherwise: the input can be traversed only once, so the algorithm must keep its own copy of the previous element, which requires the value type to be copy constructible and copy assignable.

## `reverse` and `rotate`

[alg.reverse] ¶4 `reverse` performs exactly `(last - first) / 2` swaps. `reverse_copy` requires the ranges not to overlap and performs exactly N assignments. C++26's bounded version (¶10–¶14) copies only the last N elements when the output cannot hold everything, i.e. those that come first after reversal, and returns `{last, NEW_FIRST, result + N}`.

[alg.rotate] ¶2 places the element at position `first + i` into position `first + (i + (last - middle)) % (last - first)`. Note 1 says this is a **left rotation**: the element at `middle` becomes the new first element.

¶3 The classic version returns `first + (last - middle)`, the new position of the original first element (C++03 returned `void`); the `ranges` version returns `{first + (last - middle), last}`. This return value is useful; for example, moving a block of elements to another place in the sequence can be done with two `rotate`s. ¶4 At most `last - first` swaps. Implementations may choose different algorithms by iterator category: block swaps for forward iterators, three reversals for bidirectional iterators, and cycle permutation by greatest common divisor for random access iterators.

## Randomness: `sample` and `shuffle`

```cpp run title="sample.cpp" ok
#include <algorithm>
#include <cassert>
#include <iterator>
#include <random>
#include <vector>

int main() {
  std::vector<int> pop{1, 2, 3, 4, 5, 6, 7, 8, 9, 10};
  std::vector<int> out;
  std::mt19937 g(42);
  std::sample(pop.begin(), pop.end(), std::back_inserter(out), 3, g);
  assert(out.size() == 3);
  assert(std::ranges::is_sorted(out));   // the population uses forward iterators: stable

  std::ranges::shuffle(pop, g);
  assert(std::ranges::is_permutation(pop, std::vector{1, 2, 3, 4, 5, 6, 7, 8, 9, 10}));
}
```

[alg.random.sample] ¶3 `sample` selects `min(last - first, n)` elements from the population such that each possible sample has equal probability of appearance. Note 1 mentions two techniques: selection sampling and reservoir sampling. The iterator requirement in ¶2.3 is one of two alternatives:

- the population uses forward iterators, so selection sampling can be used, producing output in order;
- otherwise the output must use random access iterators, so reservoir sampling can be used, with output positions overwritten at random.

¶6.1 `sample` is stable if and only if the population uses forward iterators; the sample then keeps the relative order it had in the population.

[alg.random.shuffle] ¶2 `shuffle` makes each possible permutation equally likely, and ¶4 performs exactly `(last - first) - 1` swaps, i.e. a Fisher–Yates shuffle. ¶5 specifies that to the extent the implementation uses random numbers, `g` is the only source of randomness; it may not call `rand()` on the side. `random_shuffle`, removed in C++17, had no such guarantee: its two-argument version used an implementation-chosen source of randomness, usually `rand()`. Both algorithms require `g` to meet the uniform random bit generator requirements ([[rand.req.urng]]).

The standard specifies only the distribution of the results, not the algorithm, so the same seed gives different samples and permutations on different standard libraries. If you need cross-platform reproducibility, you have to implement the shuffle yourself.

## `shift_left` and `shift_right` [alg.shift] {{c++20}}

C++20's [[P0769R2]] introduced these two algorithms. ¶2 `shift_left(first, last, n)` moves the element at `first + n + i` to `first + i`; when `n == 0` or `n >= last - first` it does nothing. ¶3 It returns the new logical end. Unlike `rotate`, the elements pushed out do not wrap around; the last n positions are left holding moved-from elements.

`shift_right` goes the other way, and ¶7 returns the new logical beginning. ¶5 The classic version requires the iterators to meet *Cpp17BidirectionalIterator* or the elements to be swappable: with only forward iterators, elements cannot be moved from back to front, and it can only be implemented with swaps. ¶6 Only the non-parallel version with bidirectional iterators specifies moving elements from back to front in order.

## Questions

!!! question "Question 1"
    `std::copy(v.begin(), v.end() - 1, v.begin() + 1)` on a `vector<int>` appears to give the right result with libc++. Why is it still undefined behavior?

<details markdown="1">
<summary>Answer</summary>

`result` is `v.begin() + 1`, which lies within `[first, last)`, violating [alg.copy] ¶2. For contiguous, trivially copyable ranges like `int`, libc++ uses `memmove`, which handles overlap, so the result looks right. But the standard specifies assignment one by one from front to back, and by that semantics the second element would be overwritten before it is read. The correct form is `std::copy_backward(v.begin(), v.end() - 1, v.end())`, or `std::shift_right(v.begin(), v.end(), 1)`.
</details>

!!! question "Question 2"
    What happens if you read the `std::string` elements in `[ret, last)` immediately after `std::remove_if`?

<details markdown="1">
<summary>Answer</summary>

The behavior is well-defined: the elements are in a valid state, and member functions without preconditions like `size()` can be called on them. But their values are unspecified: they may be moved-from empty strings, the original values, or the old value of some kept element. Do not rely on them.
</details>

## Summary

| Algorithm | Overlap rule | Stable | Key points |
|---|---|---|---|
| `copy`, `move` | `result` not in `[first, last)`; may overlap moving left | | use the `_backward` versions to overlap moving right |
| `copy_if`, `remove_copy`, `unique_copy` | must not overlap | yes | bounded versions return where to continue |
| `transform` | `result` may only equal the start of an input | | `op` must not modify elements in the closed ranges |
| `remove`, `unique` | in place | yes | size unchanged; tail valid but unspecified; `unique` looks only at adjacent elements |
| `rotate` | in place | | left rotation; returns the new position of the original first element |
| `sample` | `out` not in `[first, last)` | when the population uses forward iterators | equal probability; `g` is the only source of randomness |
| `shuffle` | in place | | N − 1 swaps; results vary by implementation |
| `shift_left`, `shift_right` | in place | | elements do not wrap around; returns the new logical end point |
