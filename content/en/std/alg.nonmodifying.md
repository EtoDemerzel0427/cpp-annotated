---
title: Non-modifying sequence operations
summary: "Algorithms that only read elements: the quantifiers all_of and friends, contains, for_each, the find family, count, mismatch and equal, is_permutation, the search family, starts_with and ends_with, and the fold family. The focus is on results for empty ranges, promises about how often predicates are called, the out-of-bounds risk of three-iterator equal, and the type difference between fold_left and accumulate."
updated: 2026-10-19
---

!!! tldr
    - These algorithms only read elements and call predicates, and per [[algorithms.requirements#3]] they must not write elements either, so several threads can call them on the same sequence at once.
    - The complexity clauses are promises: `find` calls the predicate at most N times and stops when it finds a match; `count` calls it exactly N times.
    - `std::equal(first1, last1, first2)` assumes the second sequence is at least as long; if it is shorter, it reads out of bounds, which is undefined behavior. Use four iterators or `ranges::equal`.
    - On an empty range, `all_of` and `none_of` return `true` and `any_of` returns `false`; with an empty pattern, `search` returns `first1` and `find_end` returns `last1`.
    - The result type of `ranges::fold_left` is determined by the return type of the binary operation; the accumulator type of `std::accumulate` is the type of the initial value, so accumulating `double`s from `0` truncates.

## The uniform style of the wording

Each subclause begins by defining a condition with "Let *E* be", so that all versions share one description. Taking [alg.find] ¶1 as the example:

| Version | *E* |
|---|---|
| `std::find` | `*i == value` |
| `std::find_if` | `pred(*i) != false` |
| `ranges::find` | `bool(invoke(proj, *i) == value)` |
| `ranges::find_if` | `bool(invoke(pred, invoke(proj, *i)))` |

The pattern: the classic versions write `*i == value` or `pred(*i)` directly; the `ranges` versions first apply the projection to the element, then call the predicate with `invoke`, usually wrapped in `bool(...)`. This is not repeated below.

## Quantifiers: `all_of`, `any_of`, `none_of`

The wording of *Returns* in ¶2 of [alg.all.of], [alg.any.of] and [alg.none.of] decides the result for an empty range:

- `all_of`: returns `false` if *E* is false for some `i`, otherwise `true`. An empty range returns `true`.
- `any_of`: returns `true` if *E* is true for some `i`, otherwise `false`. An empty range returns `false`.
- `none_of`: returns `false` if *E* is true for some `i`, otherwise `true`. An empty range returns `true`.

¶3 All three apply the predicate and projection at most `last - first` times, stopping once the result is determined.

### `ranges::contains` and `contains_subrange` {{c++23}}

[alg.contains] has only `ranges` versions ([[P2302R4]]). ¶1 `contains` returns `ranges::find(std::move(first), last, value, proj) != last`. ¶3 `contains_subrange` returns `first2 == last2 || !ranges::search(...).empty()`, so an empty subsequence is always contained. Since C++26 both have parallel overloads (¶2, ¶4).

## `for_each` and `for_each_n` [alg.foreach]

`for_each` is one of the few algorithms that give the function object back to the caller. The non-parallel `std::for_each` specifies:

- ¶1 `Function` meets *Cpp17MoveConstructible*. Note 1 points out specifically that it need not be copyable, so a lambda capturing a `std::unique_ptr` can be passed;
- ¶2 applies `f` to each element in order, from `first` to `last - 1`. Note 2: if the iterator is mutable, `f` may modify the element through the dereferenced result;
- ¶3 returns `f`, which can be used to bring back accumulated state; ¶5 the return value of `f` is ignored.

[[algorithms.requirements]] says algorithms may copy function objects freely; ¶3 is an explicit exception.

How the other versions differ:

| Version | Paragraphs | Requirement on `f` | Returns | Order |
|---|---|---|---|---|
| `std::for_each` | ¶1–¶5 | move constructible | `f` | in order |
| parallel `std::for_each` | ¶6–¶10 | copy constructible | `void` | not guaranteed |
| `ranges::for_each` | ¶11–¶15 | models `copy_constructible` (Note 6) | `{last, std::move(f)}` | in order |
| parallel `ranges::for_each` {{c++26}} | ¶16–¶19 | same as above | `last` | not guaranteed |

The parallel versions do not return the function object; the reason given in Note 4 is that parallelization often does not permit efficient state accumulation. Their *Remarks* also specify that implementations may not copy elements as other parallel algorithms may ([[algorithms.parallel.exec#3]]), and that `f` may modify objects through its arguments (¶19.3).

`for_each_n` (¶20–¶38) does the same for `[first, first + n)`. ¶20 requires `Size` to be convertible to an integral type, and ¶21 requires `n >= 0`. ¶23 It returns `first + n` rather than the function object; `ranges::for_each_n` returns both (¶32).

## Searching

### `find`, `find_if`, `find_if_not` [alg.find]

¶2 returns the first iterator for which *E* is true, or `last` if there is none. ¶3 applies the predicate at most `last - first` times.

The value parameter `T` of `find` has a default template argument:

```cpp
template<class InputIterator, class T = iterator_traits<InputIterator>::value_type>
  constexpr InputIterator find(InputIterator first, InputIterator last, const T& value);
```

This comes from C++26's [[P2248R8]]. When the argument is a braced list, `T` cannot be deduced from it, and the default argument falls back to the element's value type. So for `std::vector<std::pair<int, int>> v`, you can write `std::find(v.begin(), v.end(), {3, 4})`. The default argument of the `ranges` versions is `projected_value_t<I, Proj>`. `count`, `replace`, `fill`, `remove`, `search_n`, `lower_bound` and the other algorithms that take a value all gained the same default argument.

!!! impl "libc++ has not implemented P2248"
    With Clang 23 + libc++ in our tests, both `std::find(v.begin(), v.end(), {3, 4})` and `std::ranges::find(v, {3, 4})` report couldn't infer template argument '_Tp'.

### The `ranges::find_last` family {{c++23}}

[alg.find.last], introduced by [[P1223R5]], has three members: `find_last`, `find_last_if` and `find_last_if_not`. ¶2 returns `{i, last}`, where `i` is the last iterator for which *E* is true; if there is none, it returns `{last, last}`.

It returns a `subrange` rather than one iterator: to find the last match, the algorithm must walk to the end, and having already computed the iterator for the end, it returns that too (see [[algorithms.results]]). It requires `forward_iterator`: the algorithm has to remember the position of the last match so far while continuing forward, which a single-pass input iterator cannot do.

### `find_end` and `find_first_of`

`find_end` in [alg.find.end] searches `[first1, last1)` for the last occurrence of the subsequence `[first2, last2)`; the name is easy to misread, but it really finds the last occurrence. ¶1.3 When the subsequence is empty, longer than the main sequence, or not found, the result is `last1`. The `ranges` version returns a `subrange`.

`find_first_of` in [alg.find.first.of] returns the first position in `[first1, last1)` that matches any element of `[first2, last2)`, like C's `strpbrk`. The first sequence can use input iterators, but the second must use forward iterators, because the second sequence is scanned from the start for every element. ¶4 At most `(last1 - first1) * (last2 - first2)` comparisons are made.

### `adjacent_find` [alg.adjacent.find]

¶2 returns the first `i` for which `*i == *(i + 1)` (or `pred(*i, *(i + 1))`) holds, or `last` if there is none.

The complexity in ¶3 is stated precisely: the non-parallel version applies the predicate exactly `min((i - first) + 1, (last - first) - 1)` times, where `i` is the return value. An implementation may not make even one more comparison. The projection is applied no more than twice as many times as the predicate, because each comparison projects two elements and the standard does not require implementations to cache projection results.

## `count` and `count_if` [alg.count]

¶2 returns the number of iterators for which *E* holds. ¶3 The predicate is applied exactly `last - first` times: unlike `find`, `count` cannot stop early. The return type is the iterator's difference type, `iterator_traits<I>::difference_type` for the classic version and `iter_difference_t<I>` for the `ranges` version, not `size_t`.

## `mismatch` and `equal`

```cpp run title="equal3.cpp" flags="-std=c++2c -O0 -fsanitize=address" ub
#include <algorithm>
#include <cstdio>
#include <vector>

int main() {
  std::vector<int> a{1, 2, 3, 4};
  std::vector<int> b{1, 2};
  bool e = std::equal(a.begin(), a.end(), b.begin());  // UB: assumes b has at least 4 elements
  std::printf("%d\n", e);
}
```

Run with `-fsanitize=address` in our tests, it reports heap-buffer-overflow.

Both algorithms have classic three-iterator and four-iterator forms. When only `first2` is given, [alg.equal] ¶1.1 and [alg.mismatch] ¶1 let `last2` be `first2 + (last1 - first1)`, i.e. they assume the second sequence is at least as long as the first. When the second sequence is shorter, `[first2, last2)` is not a valid range, and the algorithm reads past its end.

C++14 added the four-iterator forms:

- [alg.mismatch] ¶3 takes `N = min(last1 - first1, last2 - first2)` and compares only the shorter length. ¶4 returns the first pair of mismatching iterators, as a `pair` for the classic version and a `mismatch_result` for the `ranges` version;
- [alg.equal] ¶2 compares the lengths first and returns `false` if they differ.

`ranges::equal` and `ranges::mismatch` have only the four-iterator (or two-range) form. Change the example above to `std::equal(a.begin(), a.end(), b.begin(), b.end())` or `std::ranges::equal(a, b)`.

The complexity in [alg.equal] ¶3 is both an optimization license and a promise: when the lengths of both sequences can be computed in constant time (the classic version requires *Cpp17RandomAccessIterator*, the `ranges` version `sized_sentinel_for` or `sized_range`) and they differ, the predicate is not applied at all; otherwise it is applied at most `min(N1, N2)` times.

## `is_permutation` [alg.is.permutation]

¶4 decides whether the second sequence can be rearranged to equal the first. ¶2 requires the value types of the two iterators to be the same. ¶3 requires the comparison to be an **equivalence relation**: reflexive, symmetric and transitive. That is weaker than a strict weak ordering, but it is still a semantic requirement the compiler cannot check, and violating it is {{ub}}.

Complexity per ¶5: when the lengths can be compared in constant time and differ, the predicate is not applied; when the two sequences are equal element by element, it is applied exactly N times; otherwise worst case O(N²). The algorithm can only test equality, not order, so it cannot sort first and compare linearly; that is where the quadratic complexity comes from. When you need it faster, sort yourself and use `equal`, or count with a hash table.

## Subsequence search

### `search` and `search_n` [alg.search]

¶1 `search` finds the first occurrence of a subsequence. When the subsequence is empty it returns `first1`, exactly the opposite of `find_end`, which returns `last1`; when not found it returns `last1`. ¶2 At most `(last1 - first1) * (last2 - first2)` comparisons, the upper bound of the naive algorithm. ¶3 The `ranges` version returns `subrange{i, i + (last2 - first2)}`.

¶5–¶10 `search_n` finds `count` consecutive elements equal to `value`. ¶5 requires `Size` to be convertible to an integral type, and ¶8 allows at most `last - first` comparisons.

¶11 C++17 added overloads taking a searcher: `search(first, last, searcher)` is equivalent to `return searcher(first, last).first;`. Together with `boyer_moore_searcher` and `boyer_moore_horspool_searcher` from `<functional>` ([[func.search]]), searching for long patterns can be much faster. ¶12 `Searcher` need not be copy constructible, because a searcher may hold a large preprocessed table.

### `starts_with` and `ends_with` {{c++23}}

Both have only `ranges` versions ([[P1659R3]]).

[alg.starts.with] ¶1 `starts_with` returns `ranges::mismatch(...).in2 == last2`, i.e. the second sequence was matched completely.

[alg.ends.with] ¶1–¶2 `ends_with` first computes the lengths N1 and N2 of the two sequences. If N1 < N2 it returns `false`; otherwise it calls `ranges::equal` on the last N2 elements of the first sequence. Because the lengths must be known first, the iterator version requires `forward_iterator` or `sized_sentinel_for` for each sequence: either the length can be computed in constant time, or it can be counted first and then revisited. ¶6 The range version skips the first N1 − N2 elements with `views::drop`.

## The fold family [alg.fold] {{c++23}}

```cpp run title="fold.cpp" ok
#include <algorithm>
#include <cassert>
#include <functional>
#include <numeric>
#include <type_traits>
#include <vector>

int main() {
  std::vector<double> v{0.5, 0.5, 0.5};
  auto a = std::accumulate(v.begin(), v.end(), 0);       // the accumulator is int
  auto f = std::ranges::fold_left(v, 0, std::plus<>());  // result type decided by plus
  static_assert(std::is_same_v<decltype(a), int>);
  static_assert(std::is_same_v<decltype(f), double>);
  assert(a == 0 && f == 1.5);

  std::vector<int> w{1, 2, 3};
  auto l = std::ranges::fold_left(w, 0, std::minus<>());   // ((0-1)-2)-3
  auto r = std::ranges::fold_right(w, 0, std::minus<>());  // 1-(2-(3-0))
  assert(l == -6 && r == 2);

  std::vector<int> empty;
  auto e = std::ranges::fold_left_first(empty, std::plus<>());
  assert(!e);   // empty range: an empty optional
}
```

The accumulator type of `std::accumulate` is the type of the initial value. Write the initial value as `0` and the accumulator is `int`; every intermediate `double` result is truncated, and the final result is 0.

C++23's [[P2322R6]] provides a replacement for `accumulate` for ranges. ¶6 specifies that the accumulator type `U` of `fold_left_with_iter` is `decay_t<invoke_result_t<F&, T, iter_reference_t<I>>>`, determined by the return type of the binary operation rather than by the type of the initial value. `fold_left` and the other functions are all defined in terms of it.

| Function | Computes | Returns |
|---|---|---|
| `fold_left(r, init, f)` | `f(f(f(init, x1), x2), x3)` | `U` |
| `fold_left_first(r, f)` | with the first element as the initial value | `optional<U>` |
| `fold_right(r, init, f)` | `f(x1, f(x2, f(x3, init)))` | `U` |
| `fold_right_last(r, f)` | with the last element as the initial value | `optional<U>` |
| `fold_left_with_iter`, `fold_left_first_with_iter` | as above, also returning the end iterator | `in_value_result` |

Other points:

- `fold_right` requires `bidirectional_iterator`; the implementation in ¶3 walks back from `last`;
- `fold_left` and `fold_right` do not return an iterator; use the `*_with_iter` versions when you need the end;
- none of them has a projection parameter; use `views::transform` first when needed;
- they specify strict left or right associativity and have no parallel versions. For a parallel reduction, use `std::reduce` ([[numeric.ops]]).

## Questions

!!! question "Question 1"
    What observable difference is there between `std::find_if(first, last, pred) != last` and `std::count_if(first, last, pred) > 0`?

<details markdown="1">
<summary>Answer</summary>

`find_if` applies the predicate at most N times and stops at the first hit; `count_if` applies it exactly N times and must go to the end. The two differ when the predicate has side effects (such as logging) or is expensive. With input iterators, after `find_if` stops, the remaining elements have not been read.
</details>

!!! question "Question 2"
    What is wrong with `std::is_permutation(a.begin(), a.end(), b.begin(), b.end(), [](double x, double y) { return std::abs(x - y) < 0.1; })`?

<details markdown="1">
<summary>Answer</summary>

"Differs by less than 0.1" is not transitive: 0.0 is close to 0.08 and 0.08 is close to 0.16, but 0.0 is not close to 0.16. So it is not an equivalence relation; this violates the precondition in [alg.is.permutation] ¶3 and is undefined behavior, and the result may depend on the order in which the implementation compares internally.
</details>

!!! question "Question 3"
    Why does `ranges::find_last` require `forward_iterator` while `ranges::find` only requires `input_iterator`?

<details markdown="1">
<summary>Answer</summary>

`find_last` must scan to the end to know which match is the last one, and on the way it has to keep the current candidate iterator. With an input iterator, once the original iterator is incremented the saved copy becomes invalid, since it can only be traversed once. So at least a multi-pass forward iterator is needed.
</details>

## Summary

| Algorithm | Promise | Watch out |
|---|---|---|
| `all_of`/`any_of`/`none_of` | at most N times, may stop early | empty range: `true`/`false`/`true` |
| `for_each` | called in order; returns `f`; `f` may be move-only | parallel versions do not return `f` and do not guarantee order |
| `find` family | at most N times; returns the first | C++26 supports braced value arguments; libc++ has not implemented it yet |
| `find_last` | returns a `subrange` | needs forward iterators |
| `count` | exactly N times | returns the difference type |
| three-iterator `mismatch`/`equal` | | out of bounds when the second sequence is shorter, UB |
| `is_permutation` | worst case O(N²) | the predicate must be an equivalence relation |
| `search` / `find_end` | | empty pattern returns `first1` / `last1` |
| `fold_left` | result type decided by the operation | no projection, no parallel version |
