---
title: "Sorting and related operations: general rules and sorting"
summary: "What conditions the comparator comp must meet (a strict weak ordering) and what happens in a real standard library when it does not; the exact meaning of sorted, partitioned and equivalent; and the guarantees and complexity of sort, stable_sort, partial_sort, nth_element and the other sorting algorithms."
updated: 2026-10-19
---

!!! tldr
    - Apart from binary search, every algorithm in [alg.sorting] requires the comparator to induce a strict weak ordering on the values actually compared; otherwise the behavior is undefined.
    - `<=`, `<` with NaNs, and comparisons with a tolerance are not strict weak orderings. With libc++, sorting 100 equal elements with `<=` reads out of bounds; enabling hardening turns that into a deterministic termination.
    - Sorted only forbids inversions and allows equal elements; equivalent means `!comp(a, b) && !comp(b, a)`, unrelated to `operator==`.
    - `sort` is unstable and O(N log N) in the worst case; `stable_sort` is stable, with complexity depending on whether extra memory can be allocated; `nth_element` only guarantees linear time on average.

## What happens when you sort with `<=`

```cpp run title="bad_comp.cpp" flags="-std=c++2c -O1 -fsanitize=address" ub
#include <algorithm>
#include <cstdio>
#include <vector>

int main() {
    std::vector<int> v(100, 7);              // 100 equal elements
    std::sort(v.begin(), v.end(),
              [](int a, int b) { return a <= b; });
    std::printf("done %d\n", v[0]);
}
```

Writing the comparator as `a <= b` looks like it merely allows equality, but this code is undefined behavior. Results with Clang 23 + libc++ in our tests:

| Build | Result |
|---|---|
| `-O1` | the process crashes with `SIGBUS` |
| `-O1 -fsanitize=address` | AddressSanitizer reports `heap-buffer-overflow`, with the out-of-bounds read in `std::__introsort` |
| with `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_FAST` | the bounds check traps and the process terminates with `SIGTRAP`, no message |
| with `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_DEBUG` | reports `Would read out of bounds, does your comparator satisfy the strict-weak ordering requirement?` and aborts |

With fewer than 24 elements, libc++ switches to insertion sort, where `<=` only causes extra moves and the program looks fine. Whether the same bug shows up depends on the input size, which makes this kind of error hard to find by testing.

The out-of-bounds read comes from the partition loop of quicksort. To save a bounds check, the loop relies on a deduction: "there is an element at the end of the range that is not less than the pivot, so `while (comp(*++i, pivot))` is bound to stop before leaving the range." That deduction holds only if `comp(x, x)` is false. With `<=`, every element equal to the pivot makes the condition true, and the loop walks off the array.

## The comparator `Compare` ([alg.sorting.general] ¶1–¶3)

¶1 All the algorithms defined directly in `std` in this subclause have two versions, one taking a comparator and one using `operator<`. ¶3 specifies that the latter is equivalent to replacing `comp(*i, *j)` with `*i < *j`.

¶2 The comparator type `Compare` must meet the requirements of `BinaryPredicate` ([[algorithms.requirements#7]]): the result of the call is usable as a `bool`, and the call does not modify elements through its arguments. Its return value, converted to `bool`, is `true` if the first argument is less than the second, and `false` otherwise.

"Less than" here is only a name. When `std::greater<>` is passed as `comp`, "less than" means numerically greater, and the sort is descending. Every "sorted" and "smallest" in this clause is relative to `comp`.

!!! std
    For algorithms other than those described in [alg.binary.search], `comp` shall induce a strict weak ordering on the values.

This is the last sentence of ¶3, and it is exactly what the opening `<=` example violates. Binary search is excluded; it needs only the weaker partitioning property, see [[alg.binary.search]].

## Strict weak ordering (¶4)

¶4 A **strict weak ordering** ([[g:strict-weak-ordering]]) consists of three conditions. First define `equiv(a, b)` as `!comp(a, b) && !comp(b, a)`, i.e. neither is less than the other. Then require:

- irreflexivity: `comp(x, x)` is false for all `x`. This is what "strict" means;
- ¶4.1 `comp` is transitive: `comp(a, b) && comp(b, c)` implies `comp(a, c)`;
- ¶4.2 `equiv` is transitive: `equiv(a, b) && equiv(b, c)` implies `equiv(a, c)`.

Note 1 points out that under these conditions `equiv` is an equivalence relation, and `comp` induces a strict total ordering on the equivalence classes. In other words, a strict weak ordering divides the elements into equivalence classes and lines the classes up in a row. "Weak" means it is weaker than a total order (distinct elements may be equivalent) yet stronger than a partial order (equivalence must be transitive).

Asymmetry (`comp(a, b)` implies `!comp(b, a)`) is not listed separately, because it follows from irreflexivity and transitivity.

The requirement concerns only the values the algorithm actually compares. Sorting a `vector<double>` without NaNs using `<` is perfectly valid; with NaNs it is not.

`ranges::sort` constrains the comparator with the concept `sortable<I, Comp, Proj>`, which includes `strict_weak_order` ([[concepts.compare]]). But a concept can only check whether the call is syntactically possible; whether the comparator is semantically a strict weak ordering cannot be checked by the compiler, and violating it is still {{ub}}.

### Common wrong comparators

| Comparator | Which condition it violates |
|---|---|
| `a <= b` | irreflexivity: `comp(x, x)` is true |
| `a < b` with NaNs | `equiv` is not transitive: `1` is equivalent to NaN, NaN is equivalent to `2`, but `1 < 2` |
| `abs(a - b) > eps && a < b` (tolerance comparison) | `equiv` is not transitive: `0` ≡ `0.6eps` ≡ `1.2eps`, but `0` is less than `1.2eps` |
| `a.x < b.x \|\| a.y < b.y` | asymmetry fails: `{1, 2}` and `{2, 1}` are each less than the other |
| result depends on random numbers or external state | not a deterministic relation at all |

The correct way to compare several fields is `std::tie(a.x, a.y) < std::tie(b.x, b.y)`, or a defaulted `operator<=>` ([[class.spaceship]]).

### NaN: no overrun, but not sorted either

```cpp run title="nan_sort.cpp" flags="-std=c++2c -O1 -D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_DEBUG" ub
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <vector>

int main() {
    std::vector<double> v{3, NAN, 1, 2, NAN, 0, 5, 4};
    std::sort(v.begin(), v.end(),
              [](double a, double b) { return a < b; });
    for (double d : v) std::printf("%g ", d);
    std::puts("");
}
```

Without hardening, it prints `3 nan 1 2 nan 0 4 5` in our tests, clearly not sorted. The debug hardening mode spot-checks the result after sorting, reports `Your comparator is not a valid strict-weak ordering` and aborts.

!!! tip "The right way to sort floating-point numbers"
    Use `std::ranges::sort(v, std::strong_order)` (C++20, [[cmp]]). For floating-point numbers, `strong_order` uses IEEE 754's totalOrder, in which ±0 and all the NaNs have definite positions. Alternatively, remove the NaNs first with `std::erase_if(v, [](double d) { return std::isnan(d); })`.

## Sorted, partitioned and equivalent (¶5–¶8)

¶5 A sequence is **sorted with respect to `comp` and `proj`** ([[g:sorted-with-respect-to]]) if for every position `i` in the sequence and every non-negative integer `n` (such that `i + n` is still in the sequence),

```cpp
bool(invoke(comp, invoke(proj, *(i + n)), invoke(proj, *i)))
```

is `false`. Here `proj` is a **projection** ([[g:projection]]): a function applied to elements before comparing them, such as fetching a member. The definition says that later elements are not less than earlier ones. Equality is allowed; only inversions are forbidden. ¶6 Sorted with respect to `comp` alone means the projection is `identity{}`.

¶7 A sequence `[start, finish)` is **partitioned with respect to an expression `f(e)`** ([[g:partitioned-with-respect-to]]) if there is an integer `n` such that `f(*(start + i))` is true if and only if `i < n`. That is, all elements for which `f` is true come first. The preconditions of binary search are stated in terms of this.

¶8 The equivalence used in describing concepts such as stability is the equivalence induced by the strict weak ordering, `!(a < b) && !(b < a)`, not necessarily `operator==`. What `stable_sort` preserves is the relative order of equivalent elements.

## `sort` ([sort])

¶2 For the versions in `std`, the iterators must meet *Cpp17ValueSwappable*, and the element type must be move constructible and move assignable. The `ranges` versions use the concept `sortable<I, Comp, Proj>` instead ([[alg.req.sortable]]).

¶3 `sort` sorts the range with respect to `comp` and `proj`. It is not stable: the relative order of equivalent elements is unspecified.

¶5 The complexity is O(N log N) comparisons and projections, a worst-case requirement. C++98 only required N log N on average, which plain quicksort satisfied; after C++11 tightened this, implementations generally switched to introsort: quicksort first, switching to heapsort when recursion gets too deep.

!!! impl "libc++'s `std::sort`"
    libc++'s `__introsort` (`<__algorithm/sort.h>`) is a pdqsort-style introsort. Below 24 elements it uses insertion sort; above 128 elements it picks the pivot with Tukey's ninther, otherwise median-of-three; for contiguous arithmetic types with `less`/`greater` it uses a branchless bitset partition; when the recursion depth budget runs out it switches to heapsort, guaranteeing O(N log N) in the worst case. During constant evaluation (`sort` has been `constexpr` since C++20) it uses heapsort directly.
    
    With the macro `_LIBCPP_DEBUG_RANDOMIZE_UNSPECIFIED_STABILITY` defined, libc++ randomly shuffles the input before sorting, to expose code that depends on the order of equivalent elements.

With projections, the `ranges` versions can sort by a member directly, without writing a lambda:

```cpp run title="sort_proj.cpp" ok
#include <algorithm>
#include <array>
#include <cassert>
#include <string>
#include <vector>

struct Person { std::string name; int age; };

constexpr bool test_constexpr() {
    std::array a{5, 3, 4, 1, 2};
    std::ranges::stable_sort(a);              // constexpr since C++26
    return std::ranges::is_sorted(a);
}
static_assert(test_constexpr());

int main() {
    std::vector<Person> ps{{"carol", 30}, {"alice", 25},
                           {"bob", 30}, {"dave", 25}};
    std::ranges::stable_sort(ps, {}, &Person::age);   // compare by age
    // stable: people of the same age keep their original relative order
    assert(ps[0].name == "alice" && ps[1].name == "dave");
    assert(ps[2].name == "carol" && ps[3].name == "bob");
}
```

## `stable_sort` ([stable.sort])

¶6 `stable_sort` is **stable** ([[algorithm.stable]]): equivalent elements keep their original relative order.

¶5 Its complexity has two tiers: N log N comparisons if enough extra memory is available (merge sort); otherwise at most N log² N (in-place merging). The standard rarely writes resource availability into a complexity requirement. In practice `stable_sort` tries to allocate a temporary buffer, and if allocation fails it does not throw but falls back to the slower in-place algorithm. That is also why it is marked `// hosted` in the synopsis, and [[g:freestanding-implementation|freestanding implementations]] need not provide it.

Since C++26, `stable_sort`, `stable_partition` and `inplace_merge` are all `constexpr` ([[P2562R1]]); the `static_assert` in the example above passes with libc++ in our tests.

## `partial_sort` and `partial_sort_copy` ([partial.sort], [partial.sort.copy])

¶3 `partial_sort(first, middle, last)` places the `middle - first` smallest elements of the whole range, sorted, into `[first, middle)`, leaving the rest in `[middle, last)` in unspecified order. ¶5 Approximately `(last - first) * log(middle - first)` comparisons. The classic implementation builds a heap on `[first, middle)`, scans the remaining elements, and finally sorts the heap. It suits taking the top k.

`partial_sort_copy` copies the N smallest elements, sorted, into the output range, where N is the smaller of the input length and the output length. The input needs only input iterators; the output needs random access iterators.

¶4 is a consistency requirement written for the two-projection `ranges` version: after an input value is written into the output range, comparing it via `proj2` must give the same result as comparing the original value via `proj1`. Otherwise "select the smallest elements by `proj1`" and "make the output sorted by `proj2`" would not line up.

## `is_sorted` and `is_sorted_until` ([is.sorted])

¶8 `is_sorted_until` returns the last `i` such that `[first, i)` is sorted. `is_sorted` is defined as `is_sorted_until(...) == last`. ¶9 Both are linear.

## `nth_element` ([alg.nth.element])

¶3 After `nth_element(first, nth, last)`:

1. the element at `nth` is exactly the element that would be in that position if the whole range were sorted (unless `nth == last`);
2. for any `i` in `[first, nth)` and `j` in `[nth, last)`, `comp(*j, *i)` is false, i.e. no element of the first part is greater than any element of the second part.

The order within each part is unspecified. `nth == last` is a valid call; it just has no effect you can rely on.

¶5 The non-parallel version is only required to be linear on average, not in the worst case. Worst-case linear time needs an algorithm like median-of-medians; libc++'s `__nth_element` is an iterative quickselect with no worst-case linear guarantee. The parallel version requires O(N) predicate applications and O(N log N) swaps.

```cpp run title="nth.cpp" ok
#include <algorithm>
#include <cassert>
#include <vector>

int main() {
    std::vector<int> v{9, 8, 7, 6, 5, 4, 3, 2, 1};
    // find the median
    std::nth_element(v.begin(), v.begin() + 4, v.end());
    assert(v[4] == 5);
    assert(std::all_of(v.begin(), v.begin() + 4,
                       [](int x) { return x <= 5; }));
    // top 3
    std::partial_sort(v.begin(), v.begin() + 3, v.end());
    assert(v[0] == 1 && v[1] == 2 && v[2] == 3);
}
```

## Questions

!!! question "Question 1"
    Can `[](const std::string& a, const std::string& b) { return a.size() < b.size(); }` be used as a comparator for `std::sort`?

<details markdown="1">
<summary>Answer</summary>

Yes. It is a strict weak ordering: the equivalence classes are strings of the same length, and the classes are totally ordered by length; it is irreflexive, and both `comp` and `equiv` are transitive. But `sort` is not stable, so the order among strings of the same length is unspecified; use `stable_sort` when the original order must be kept.
</details>

!!! question "Question 2"
    When the comparator of `std::sort` throws, what state is the range left in? Is it still a permutation of the original elements?

<details markdown="1">
<summary>Answer</summary>

The standard gives no guarantee at all, so you cannot assume the elements were merely rearranged. With libc++ in our tests, sorting `{5, 3, 8, 1, 9, 2, 7, 4, 6, 0}` with the 4th comparison throwing gives `3 5 8 8 9 2 7 4 6 0`: `8` appears twice and `1` is gone. The reason is that insertion sort moves the current element into a temporary and then shifts the preceding elements back one by one; when a comparison throws midway, the temporary is destroyed and the vacated slot is left holding a duplicate.

When the comparator throws in a parallel version, the consequence is determined by the execution policy ([[algorithms.parallel.exceptions]]); for the execution policies provided by the standard library, the result is a call to `std::terminate` ([[execpol]]).
</details>

!!! question "Question 3"
    Why does the standard write just O(N log N) for `sort`, but approximately `(last - first) * log(middle - first)` for `partial_sort`?

<details markdown="1">
<summary>Answer</summary>

The complexity of `sort` is an asymptotic requirement that leaves implementations free to choose an algorithm. The wording for `partial_sort` is inherited from C++98's heap-based reference implementation; "approximately" signals an approximate characterization of the number of comparisons, not an exact upper bound. Both count only comparisons and projections, not swaps.
</details>

## Summary

| Algorithm | Stable | Comparisons | Notes |
|---|---|---|---|
| `sort` | no | O(N log N), worst case | libc++ uses a pdqsort-style introsort |
| `stable_sort` | yes | N log N (with memory) or N log² N | may allocate memory; `constexpr` since C++26 |
| `partial_sort` | no | about N log k | top k |
| `partial_sort_copy` | no | about N log k | input may be single-pass iterators |
| `nth_element` | no | linear on average | selection, finding the median |
| `is_sorted`, `is_sorted_until` | n/a | linear | |
