---
title: Binary search and partitions
summary: "The real precondition of lower_bound, upper_bound, equal_range and binary_search is that the sequence is partitioned with respect to the search key, not that it is sorted; the two argument orders of a comparator in heterogeneous comparisons; and the partition algorithms, along with partition_point as the most general form of binary search."
updated: 2026-10-19
---

!!! tldr
    - Binary search only requires the sequence to be partitioned with respect to the search key: all elements less than the key come first. The sequence need not be sorted overall, and the comparator need not be a strict weak ordering.
    - `lower_bound` calls `comp(element, key)` and `upper_bound` calls `comp(key, element)`. A heterogeneous comparator must provide both argument orders.
    - The number of comparisons is always logarithmic; on non-random-access iterators like those of `std::list`, the number of iterator steps is still linear.
    - `binary_search` tests equivalence, not equality, and does not tell you the position.
    - `partition_point` is the most general form of binary search, suited to bisecting on a monotonic condition.

## A sequence that is not sorted but can be bisected

```cpp run title="partitioned.cpp" ok
#include <algorithm>
#include <cassert>
#include <vector>

int main() {
    std::vector<int> p{2, 1, 3, 9, 5, 7};   // not sorted
    auto it = std::lower_bound(p.begin(), p.end(), 4);
    assert(*it == 9);
}
```

Textbooks say binary search requires a sorted array, but this call is valid. `{2, 1, 3, 9, 5, 7}` is not sorted, yet with respect to the condition `e < 4` it is already split into two parts: the first three elements are less than 4 and the last three are not. `lower_bound` is looking for exactly that dividing line, and that is all it needs.

## General ([alg.binary.search.general] ¶1)

!!! std
    All of the algorithms in [alg.binary.search] are versions of binary search and assume that the sequence being searched is partitioned with respect to an expression formed by binding the search key to an argument of the comparison function.

¶1 The precondition of binary search is: bind the search key to one argument of the comparison function to obtain a condition on elements, and the sequence is partitioned with respect to that condition. Partitioned ([[g:partitioned-with-respect-to]]) is defined in [[alg.sorting#7]]: the elements for which the condition is true all come first.

The second half of ¶1 is about complexity. For any iterators, the number of comparisons is logarithmic. For random access iterators, the number of steps through the data structure is also logarithmic; for non-random-access iterators, the number of steps is linear. So `std::lower_bound` on a `std::list` is valid and makes O(log N) comparisons, but takes O(N) time overall. When comparisons are expensive (long strings, say), this can still beat a linear search.

[[alg.sorting#3]] requires the comparator to be a strict weak ordering, but explicitly excludes binary search. Binary search needs only the partitioning property above.

## `lower_bound` and `upper_bound` ([lower.bound], [upper.bound])

The precondition of [lower.bound] ¶2 is that the elements `e` are partitioned with respect to `comp(proj(e), value)`, i.e. all elements less than `value` come first. ¶3 It returns the furthest position `i` such that every element of `[first, i)` is less than `value`. That is, the first position not less than `value`.

The precondition of [upper.bound] ¶2 is that the elements are partitioned with respect to `!comp(value, proj(e))`, i.e. all elements not greater than `value` come first. ¶3 It returns the first position greater than `value`.

¶4 of both specifies at most log₂(last − first) + O(1) comparisons and projections.

!!! warning "The two functions call `comp` with opposite argument orders"
    `lower_bound` calls `comp(element, value)`; `upper_bound` calls `comp(value, element)`. The general rule is that the comparator's first argument comes from the first sequence ([[algorithms.requirements#7]]), and `upper_bound` is an exception. When writing a heterogeneous comparator, provide both signatures, because `equal_range` and `binary_search` use both.

```cpp run title="lower_upper.cpp" ok
#include <algorithm>
#include <cassert>
#include <string>
#include <vector>

struct Rec { int key; std::string val; };

// lower_bound calls comp(elem, k), upper_bound calls comp(k, elem)
struct ByKey {
    bool operator()(const Rec& r, int k) const {
        return r.key < k;
    }
    bool operator()(int k, const Rec& r) const {
        return k < r.key;
    }
};

int main() {
    std::vector<Rec> rs{{1, "a"}, {3, "b"}, {3, "c"}, {7, "d"}};
    auto lo = std::lower_bound(rs.begin(), rs.end(), 3, ByKey{});
    auto hi = std::upper_bound(rs.begin(), rs.end(), 3, ByKey{});
    assert(hi - lo == 2);

    // ranges version: project elements to int, so the comparator only compares ints
    auto [b, e] = std::ranges::equal_range(rs, 3, {}, &Rec::key);
    assert(b == lo && e == hi);
}
```

The `ranges` versions constrain the comparator with `indirect_strict_weak_order<const T*, projected<I, Proj>>`, requiring both `(key, element)` and `(element, key)` orders to be callable. This is stricter than the classic version: the classic `lower_bound` uses only one order. Fortunately, with projections ([[g:projection]]) you can usually map elements to the same type as the key and need no heterogeneous comparator at all.

## `equal_range` and `binary_search` ([equal.range], [binary.search])

¶2 of both requires the sequence to be partitioned with respect to both `comp(e, value)` and `!comp(value, e)`. The versions in `std` additionally require that `comp(e, value)` implies `!comp(value, e)`, i.e. the comparator must not report both less-than and greater-than for the same element and key; otherwise there would be no such thing as the range of elements equivalent to the key.

[equal.range] ¶3 returns `{lower_bound(...), upper_bound(...)}`, and ¶4 makes at most 2·log₂N + O(1) comparisons.

[binary.search] ¶3 returns only a `bool`: whether there is an element equivalent to `value`, i.e. one satisfying `!comp(*i, value) && !comp(value, *i)`. It does not tell you the position. When you need the position, get `it` from `lower_bound` and then check `it != last && !comp(value, *it)`.

!!! pitfall "`binary_search` finds an equivalent element"
    `binary_search` tests `!(a < b) && !(b < a)` and never calls `operator==`. Searching for `"abc"` in a sequence of strings compared by length returns `true` as long as `"xyz"` is present.

!!! tip "Use member functions for associative containers"
    Member functions such as `std::set::lower_bound` search down the tree directly in logarithmic time. Calling the free function `std::lower_bound` on a `set` or `map` uses bidirectional iterators, and the number of steps degrades to linear. A transparent comparator (such as `std::less<>`) with the member functions also allows heterogeneous lookup; see [[associative.reqmts]].

## Partition algorithms ([alg.partitions])

### `is_partitioned` (¶1–¶3)

¶2 tests whether the sequence is partitioned with respect to `pred` (after projection). ¶3 At most N predicate applications. An empty range is partitioned.

### `partition` and `stable_partition` (¶4–¶13)

¶6 `partition` moves the elements that satisfy the predicate to the front and returns the partition point (the `ranges` version returns `{partition point, last}`). It is not stable. The complexity in ¶8 depends on the iterator category: exactly N predicate applications; at most N/2 swaps for bidirectional iterators (scanning from both ends inward), at most N swaps for forward iterators (scanning in one direction); O(N log N) swaps for the parallel version.

¶11 `stable_partition` does the same while preserving the relative order within both groups. ¶13 At most N log₂N swaps, and only O(N) if there is enough extra memory. As with `stable_sort`, the complexity depends on whether a temporary buffer can be allocated; it is likewise provided only in hosted implementations, and is `constexpr` since C++26 ([[P2562R1]]).

### `partition_copy` (¶14–¶22)

¶20 copies the elements that satisfy the condition to `out_true` and the rest to `out_false`. ¶19 The input and outputs must not overlap. ¶21 The classic version returns `pair{out_true + Q, out_false + V}`; the `ranges` version returns `{input end, out_true + Q, out_false + V}`.

¶15–¶17 are written for the parallel `ranges` overloads. These overloads give an end for each of the two output ranges, and the algorithm stops when either output is full. ¶17 defines where it stops: just before the first element that does not fit.

### `partition_point` (¶23–¶26)

¶24 The precondition is that the sequence is partitioned. ¶25 It returns the partition point `mid`. ¶26 O(log N) predicate applications.

`partition_point` is the most general form of binary search. `lower_bound(first, last, value, comp)` is equivalent to `partition_point(first, last, [&](const auto& e) { return comp(e, value); })`. When the search condition does not take the form of a key plus a comparator, such as finding the first `x` with `f(x) >= target` (for monotonic `f`), using `partition_point` directly is clearest:

```cpp run title="partition_point.cpp" ok
#include <algorithm>
#include <cassert>
#include <ranges>

int main() {
    // find the smallest n with n*n >= 1000: bisect over an iota view
    auto r = std::views::iota(0, 1000);
    auto it = std::ranges::partition_point(
        r, [](int n) { return n * n < 1000; });
    assert(*it == 32);
}
```

## Questions

!!! question "Question 1"
    Is calling `std::lower_bound(v.begin(), v.end(), 5)` on a `vector<int>` sorted in descending order undefined behavior?

<details markdown="1">
<summary>Answer</summary>

In general, yes. The precondition requires all elements less than 5 to come first, but in a descending sequence they all come last. Unless all elements are less than 5 or none are, the precondition is not met, it is {{ub}}, and in practice the wrong position is returned. The right approach is to pass `std::greater<>()`; the precondition then becomes that all elements greater than 5 come first, which a descending sequence satisfies.
</details>

!!! question "Question 2"
    Why does [[alg.sorting#3]] exclude binary search from the strict weak ordering requirement?

<details markdown="1">
<summary>Answer</summary>

Binary search only cares that one fixed key splits the sequence into two parts; the partitioning property is enough. Relaxing the requirement makes more useful searches valid. For example, searching a sorted sequence of strings by prefix: define `comp(e, prefix)` as `e` truncated to the length of `prefix` being less than `prefix`. For a fixed `prefix`, this splits the sequence into two parts, but as a relation between strings it is not necessarily a strict weak ordering.
</details>

## Summary

| Algorithm | Precondition: partitioned with respect to | Returns | Comparisons |
|---|---|---|---|
| `lower_bound` | `comp(e, value)` | first position not less than `value` | log₂N + O(1) |
| `upper_bound` | `!comp(value, e)` | first position greater than `value` | log₂N + O(1) |
| `equal_range` | both of the above, and `comp(e, v)` implies `!comp(v, e)` | `{lower, upper}` | 2 log₂N + O(1) |
| `binary_search` | same as above | `bool`, by equivalence | log₂N + O(1) |
| `partition_point` | `pred` | the partition point | O(log N) |
| `partition` | none | the partition point | N predicate applications; not stable |
| `stable_partition` | none | the partition point | stable; N log N or O(N) swaps |
