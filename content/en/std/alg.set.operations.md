---
title: Merge and set operations on sorted structures
summary: "The stability of merge and inplace_merge and which equivalent element is output first; how many copies includes, set_union, set_intersection, set_difference and set_symmetric_difference output with duplicates, and from which sequence; the upper bounds on comparisons; and how the parallel versions with an output bound report how far the inputs were consumed."
updated: 2026-10-19
---

!!! tldr
    - The algorithms on this page all require their inputs to be sorted with respect to the comparator used, and the output range must not overlap either input; they are all stable.
    - When `merge` meets equivalent elements, it outputs the one from the first sequence first, which is exactly why merge sort is stable.
    - With duplicates, if a value occurs m times in one input and n times in the other, union outputs max(m, n) copies, intersection min(m, n), difference max(m − n, 0), and symmetric difference |m − n|.
    - The elements output by intersection always come from the first sequence, which is visible for elements that are equivalent but not equal.
    - The set operations make at most 2(N1 + N2) − 1 comparisons.

## An example

```cpp run title="setops.cpp" ok
#include <algorithm>
#include <cassert>
#include <iterator>
#include <vector>

int main() {
    std::vector<int> a{1, 1, 2, 4}, b{1, 3, 4, 4};
    std::vector<int> u, i, d, s, m;
    auto out = [](auto& v) { return std::back_inserter(v); };
    std::set_union(a.begin(), a.end(), b.begin(), b.end(), out(u));
    std::set_intersection(a.begin(), a.end(),
                          b.begin(), b.end(), out(i));
    std::set_difference(a.begin(), a.end(),
                        b.begin(), b.end(), out(d));
    std::set_symmetric_difference(a.begin(), a.end(),
                                  b.begin(), b.end(), out(s));
    std::merge(a.begin(), a.end(), b.begin(), b.end(), out(m));
    assert((u == std::vector{1, 1, 2, 3, 4, 4}));  // max(m, n) copies
    assert((i == std::vector{1, 4}));              // min(m, n) copies
    assert((d == std::vector{1, 2}));              // max(m - n, 0) copies
    assert((s == std::vector{1, 2, 3, 4}));        // |m - n| copies
    assert(m.size() == a.size() + b.size());       // merge does not deduplicate
    assert(std::includes(a.begin(), a.end(), i.begin(), i.end()));
}
```

`1` occurs twice in `a` and once in `b`, so the union has two `1`s, the intersection one, and the difference one. `merge` just combines two sorted sequences into one, without any deduplication.

These algorithms all process two sorted sequences in linear time, with two shared preconditions: each input is sorted with respect to the comparator (and its own projection), and violating this is undefined behavior; and the output range does not overlap either input.

## `merge` and `inplace_merge` ([alg.merge])

¶3 The effects of `merge` have three layers:

1. Copy the first K elements of the first sequence and the first N − K elements of the second sequence to the output. Without an output bound, that is all the elements;
2. Elements that come earlier in the same input are output first;
3. For `e1` from the first sequence and `e2` from the second, `e2` is output before `e1` if and only if `comp(e2, e1)` is true.

Item 3 says: when two elements are equivalent, the one from the first sequence is output first. That is the precise meaning of `merge`'s stability. The general definition of stable in [[algorithm.stable]] only concerns order within a single sequence; `merge` has two inputs, so the order across sequences has to be specified separately. Merge sort is stable precisely because elements of the left half always come before equivalent elements of the right half.

¶5 The non-parallel version makes at most N − 1 comparisons, the parallel version O(N). ¶4 The `ranges` version returns `{first1 + K, first2 + N - K, result + N}`, telling the caller how far each of the two inputs was consumed.

The K in ¶1 is there for the parallel `ranges` overloads with an output bound. When the output space is insufficient, K is the number of elements of the first sequence that get copied: the smallest K such that at least N − K elements of the second sequence are strictly less than the element at position K of the first sequence. Note 1 says that `first1 + K` points just past the last element copied.

¶9 `inplace_merge(first, middle, last)` merges two adjacent sorted runs `[first, middle)` and `[middle, last)` in place into one sorted run. ¶11 At most N − 1 comparisons if enough extra memory is available, otherwise O(N log N); ¶12 it is stable. Like `stable_sort`, it tries to allocate a temporary buffer, is provided only in hosted implementations, and is `constexpr` since C++26 ([[P2562R1]]).

## Semantics with duplicates ([alg.set.operations.general])

¶1 These set operations also work on sequences containing multiple equivalent elements, i.e. multisets ([[multiset]]). They generalize as follows: the union contains each element the maximum number of times it occurs, the intersection the minimum number of times, and so on.

Suppose some equivalence class has m elements in the first sequence and n in the second. ¶3 of each algorithm specifies how many copies are output and where they come from:

| Algorithm | Number output | Taken from |
|---|---|---|
| `set_union` | max(m, n) | first all m from the first sequence, then the last max(n − m, 0) from the second |
| `set_intersection` | min(m, n) | the first min(m, n) from the first sequence |
| `set_difference` | max(m − n, 0) | the last max(m − n, 0) from the first sequence |
| `set_symmetric_difference` | \|m − n\| | the last m − n from the first sequence if m > n, the last n − m from the second if m < n |

When elements are equivalent but not equal, which sequence they come from is observable. For example, if two sequences of records are compared by `key` and their `value`s differ, `set_intersection` always outputs the records from the first sequence.

¶6 All four set operations that produce output are stable. ¶5 They make at most 2·((last1 − first1) + (last2 − first2)) − 1 comparisons, and apply each projection no more than that many times. The factor 2 comes from deciding equivalence, which takes two comparisons: `comp(a, b)` and `comp(b, a)`.

## `includes` ([includes])

¶3 `includes` returns `true` if the second sequence is a **subsequence** of the first. Note 1 explains that a subsequence is a sequence obtained from the original by removing some elements (possibly none, possibly all) while keeping the order of the rest.

For sequences with duplicates, this means each equivalence class may not occur more times in the second sequence than in the first. So `includes({1, 2}, {1, 1})` is `false`.

## With an output bound: skipped elements

The return values of the classic versions are simple: the `std` versions return the output end, and the `ranges` versions return the ends of both inputs and of the output. C++26's parallel `ranges` overloads also accept the end of the output range, and the algorithm stops early when the output is full. A caller who wants to continue processing the remaining input then needs to know how far each input was consumed.

For this, ¶3 of each algorithm introduces **skipped** elements: input elements that were not copied but have been processed. The return value has the form `{first1 + A, first2 + B, ...}`, where A and B are the numbers of elements copied or skipped in each input. For example:

- `set_union`: when k elements of an equivalence class are copied from the first sequence, the corresponding first min(k, n) elements of the second sequence count as skipped; they are already represented by the elements from the first sequence;
- `set_intersection`: the first k elements of the second sequence corresponding to the k copied elements of the first count as skipped; in addition, uncopied elements less than the min(M, N + 1)-th element of the intersection count as skipped (M is the length of the full intersection, N the number actually output).

This is also why the return type of `set_difference` differs: the classic `ranges` version returns `in_out_result`, not reporting the position in the second input; the parallel bounded version returns `set_difference_truncated_result`; see [[algorithms.results]].

## Questions

!!! question "Question 1"
    Both `vector`s have been sorted in descending order with `std::greater<>()`, and then `std::set_union(a.begin(), a.end(), b.begin(), b.end(), out)` is called without a comparator. What happens?

<details markdown="1">
<summary>Answer</summary>

The precondition requires the inputs to be sorted with respect to the comparator used. Without a comparator, `less{}` is used, and descending sequences do not meet that condition: it is {{ub}}, and in practice the output is neither sorted nor the correct union. You must pass the same `std::greater<>()` used for sorting.
</details>

!!! question "Question 2"
    If `std::includes(a.begin(), a.end(), b.begin(), b.end())` is true, does that mean `set_difference(b, a)` is empty?

<details markdown="1">
<summary>Answer</summary>

Yes. `includes` being true means that for each equivalence class, the count n in `b` does not exceed the count m in `a`, so `set_difference(b, a)` outputs max(n − m, 0) = 0 copies of each class.
</details>

## Summary

- The inputs must be sorted with respect to the same comparator; the output must not overlap the inputs; all the algorithms are stable.
- `merge`: among equivalent elements, the first sequence's are output first; N − 1 comparisons. `inplace_merge` makes N − 1 or O(N log N) comparisons depending on whether memory can be allocated.
- Duplicates: union max, intersection min, difference max(m − n, 0), symmetric difference |m − n|; intersection takes elements from the first sequence.
- The set operations make at most 2(N1 + N2) − 1 comparisons.
- The parallel versions with an output bound report how far each input was consumed through the number of elements copied or skipped.
