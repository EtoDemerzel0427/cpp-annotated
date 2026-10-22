---
title: Generalized numeric operations
summary: "The sequence algorithms of <numeric>: accumulate folds strictly left to right with an accumulator whose type is that of the initial value; reduce and the scan family are defined by GENERALIZED_SUM, which allows regrouping and reordering and hence parallelism, but gives nondeterministic results for floating-point and non-commutative operations; plus inner_product, transform_reduce, partial_sum, adjacent_difference and iota."
updated: 2026-10-19
---

!!! tldr
    - `accumulate` computes strictly left to right, and the accumulator's type is the type of the initial value: `accumulate(..., 0)` on a `vector<double>` truncates every step to `int`.
    - `reduce` allows arbitrary grouping and arbitrary order, so it can run in parallel; when the operation is not associative or not commutative (including floating-point addition), the result is nondeterministic.
    - The scan family allows only regrouping, not reordering, so it requires only associativity, not commutativity.
    - `exclusive_scan`'s `init` is mandatory and comes before `binary_op`; `inclusive_scan`'s `init` is optional and comes after `binary_op`.
    - The parallel version of `adjacent_difference` does not allow in-place computation; the non-parallel version does.

## `accumulate` and `reduce` compute different results

```cpp run title="reduce_fp.cpp" flags="-std=c++2c -O2 -fexperimental-library" impl
#include <cstdio>
#include <execution>
#include <numeric>
#include <vector>

int main() {
    std::vector<float> v(10'000'000, 0.1f);
    float a = std::accumulate(v.begin(), v.end(), 0.0f);
    float r = std::reduce(std::execution::par_unseq,
                          v.begin(), v.end(), 0.0f);
    std::printf("accumulate=%.1f reduce=%.1f\n", a, r);
}
```

In our tests it prints `accumulate=1087937.0 reduce=1000374.1`; the mathematically exact value is 1000000.

`accumulate` adds one element at a time from left to right; the accumulator soon becomes far larger than 0.1f, and the rounding error of each addition accumulates in the same direction. `reduce` sums the range in separate blocks and then combines the partial sums, so its error is much smaller. Both results conform: `accumulate` specifies its order of computation, while the standard makes no promise about the exact result of `reduce`.

The sequence algorithms of `<numeric>` fall into two groups:

- `accumulate`, `inner_product`, `partial_sum` and `adjacent_difference`, present since C++98, plus C++11's `iota`: computed strictly left to right, with no parallel versions;
- `reduce`, `transform_reduce`, `inclusive_scan`, `exclusive_scan` and their transform versions, added in C++17 together with the parallel algorithms ([[P0024R2]]): defined by the generalized sums below, which allow regrouping and reordering, so they can run in parallel.

The difference between the two groups is semantic, not just speed.

## The two generalized sums ([numerics.defns])

¶1 *GENERALIZED_NONCOMMUTATIVE_SUM*(op, a1, …, aN) is defined as a1 when N is 1; otherwise it is

op(*GENERALIZED_NONCOMMUTATIVE_SUM*(op, a1, …, aK), *GENERALIZED_NONCOMMUTATIVE_SUM*(op, aM, …, aN))

for any K satisfying 1 < K + 1 = M ≤ N. That is, the order of the elements is preserved, but parentheses can be placed arbitrarily. `(a1 op a2) op a3` and `a1 op (a2 op a3)` are both valid results, equal only if `op` is associative.

¶2 *GENERALIZED_SUM*(op, a1, …, aN) is *GENERALIZED_NONCOMMUTATIVE_SUM* applied to any permutation of a1, …, aN. The order can be shuffled too, and the result is unique only if `op` is both associative and commutative.

These two definitions are the basis for parallelization. Cutting the range into blocks, summing each block independently and then combining requires regrouping; when vectorizing, putting a1, a5, a9 and so on into the same SIMD lane requires reordering.

## `accumulate` ([accumulate])

¶2 `accumulate` initializes the accumulator `acc` with `init`, and then for each `i` in order performs `acc = std::move(acc) + *i` or `acc = binary_op(std::move(acc), *i)`.

This has two consequences. First, the accumulator's type is `T`, the type of `init`. `std::accumulate(v.begin(), v.end(), 0)` on a `vector<double>` truncates the sum to `int` at every step, a very common numerical bug. C++23's `ranges::fold_left` instead lets the type be determined by the result of the operation; see [[alg.nonmodifying]].

Second, the order of computation is completely determined, so any `binary_op` has a deterministic result, including subtraction, string concatenation and floating-point addition.

The `std::move(acc)` was added in C++20 ([[P0616R0]]). Before that, it was written `acc = acc + *i`, and concatenating `std::string`s with `accumulate` copied the whole accumulator at every step, for O(N²) total cost. With the `move`, `operator+(string&&, const string&)` can reuse the left operand's buffer.

¶1 requires `T` to be copy constructible and copy assignable, and `binary_op` not to modify elements nor invalidate iterators in the closed range `[first, last]`. The closed range is intentional: even `last` must not be invalidated; Note 1 in [numeric.ops.general] says the mixing of closed and half-open ranges in this subclause is intentional. Footnote 185 explains that by always requiring an initial value, `accumulate` avoids the question of what the reduction of an empty sequence is.

## `reduce` ([reduce])

¶7 `reduce` returns *GENERALIZED_SUM*(binary_op, init, *i, …). `init` takes part in the reordering too and may appear in any position.

¶1–¶4 are several simplified overloads. Without `init`, `init` is the value-initialized element type, `iterator_traits<I>::value_type{}`, so `reduce(v.begin(), v.end())` on a `vector<double>` gives a `double`, avoiding `accumulate`'s truncation problem. Without `binary_op`, `plus<>()` is used.

¶5 *Mandates* require all four combinations `binary_op(init, *first)`, `binary_op(*first, init)`, `binary_op(init, init)` and `binary_op(*first, *first)` to be convertible to `T`. This is the syntactic consequence of allowing arbitrary reordering: inside `reduce`, two elements may be added, or two partial sums. `accumulate` needs only the one form `binary_op(T, element)`.

!!! std
    The difference between `reduce` and `accumulate` is that `reduce` applies `binary_op` in an unspecified order, which yields a nondeterministic result for non-associative or non-commutative `binary_op` such as floating-point addition.

¶9 Note 1 is the key point of this subclause. For an operation like subtraction, the result of `reduce` is nondeterministic: not undefined behavior, but not guaranteed to equal the result of `accumulate`, nor to be the same from run to run. Floating-point addition is commutative but not associative, so it is nondeterministic as well, as the opening example shows.

¶8 The complexity is O(N) applications of `binary_op`, not exactly N, because combining partial sums of blocks takes a few extra operations.

!!! tip "Which one to use"
    - Associative and commutative operations (integer addition, `max`, bitwise or): `reduce` and `accumulate` give the same result, and `reduce` can run in parallel;
    - Floating-point sums: both have rounding error; `reduce` is usually more accurate but not reproducible; when you need reproducibility, use `accumulate` (or Kahan summation);
    - Non-commutative operations (string concatenation, matrix multiplication): use `accumulate` or `ranges::fold_left`; if the operation is associative, the scan family can also run it in parallel.

## `inner_product` and `transform_reduce` ([inner.product], [transform.reduce])

[inner.product] ¶2 `inner_product(first1, last1, first2, init)` computes strictly left to right `acc = std::move(acc) + (*i1) * (*i2)`, or `acc = binary_op1(std::move(acc), binary_op2(*i1, *i2))`.

`transform_reduce` is its reorderable version, in two forms:

- Two ranges: [transform.reduce] ¶5 returns *GENERALIZED_SUM*(binary_op1, init, binary_op2(*i, *(first2 + (i − first1))), …). The two default operations are `plus<>()` and `multiplies<>()`, i.e. an inner product;
- One range: ¶9 returns *GENERALIZED_SUM*(binary_op, init, unary_op(*i), …), i.e. map then reduce. ¶11 Note 1 points out that `unary_op` is not applied to `init`.

The *Mandates* in ¶3 and ¶7 require, as with `reduce`, that all four combinations be convertible to `T`.

## Prefix sums: `partial_sum` and the scan family

| Algorithm | K-th output | Computed by | Parallel version |
|---|---|---|---|
| `partial_sum` | x0 + … + xK, with the input element type as accumulator | strictly left to right | none |
| `inclusive_scan` | [init +] x0 + … + xK | *GENERALIZED_NONCOMMUTATIVE_SUM* | yes |
| `exclusive_scan` | init + x0 + … + x(K−1) | same as above | yes |
| `transform_inclusive_scan`, `transform_exclusive_scan` | the above sums over `unary_op(xi)` | same as above | yes |

The scans use the order-preserving generalized sum, which allows only regrouping. So the scans only require `binary_op` to be associative, not commutative. Operations like matrix multiplication and string concatenation, which are associative but not commutative, can be parallelized with a scan but not with `reduce`. The notes in [inclusive.scan] ¶10 and [exclusive.scan] ¶9 warn that when `binary_op` is not mathematically associative, the result may be nondeterministic.

`exclusive_scan(first, last, result, init, binary_op)` must be given `init`, and the 0th output is `init`. In `inclusive_scan(first, last, result, binary_op, init)`, `init` is optional and comes after `binary_op`, the opposite of `exclusive_scan`. If `inclusive_scan(first, last, result, init)` were allowed, it could not be distinguished from `inclusive_scan(first, last, result, binary_op)`.

[partial.sum] ¶3 `partial_sum` has no `init`, and its accumulator's type is the input element type, not the output element type. A prefix sum over a `vector<char>` overflows in `char`.

All of these algorithms allow `result == first`, i.e. in-place computation (the *Remarks* of each subclause). The transform versions likewise do not apply `unary_op` to `init`.

```cpp run title="scan.cpp" ok
#include <cassert>
#include <numeric>
#include <vector>

int main() {
    std::vector<int> v{1, 2, 3, 4};
    std::vector<int> ex(4), in(4);
    std::exclusive_scan(v.begin(), v.end(), ex.begin(), 0);
    std::inclusive_scan(v.begin(), v.end(), in.begin());
    assert((ex == std::vector{0, 1, 3, 6}));   // the i-th sum excludes the i-th element
    assert((in == std::vector{1, 3, 6, 10}));  // the i-th sum includes the i-th element

    // the default operations are plus and multiplies, i.e. an inner product
    int dot = std::transform_reduce(v.begin(), v.end(), v.begin(), 0);
    assert(dot == 30);
}
```

## `adjacent_difference` ([adjacent.difference])

`adjacent_difference` first outputs `*first`, and then at each position outputs `binary_op(*i, *(i − 1))`. The default operation is `minus<>`; note that it is the current element minus the previous one.

The non-parallel and parallel versions are specified differently:

- ¶4 The non-parallel version keeps an accumulator `acc` holding the previous input value. At each step it creates `val = *i`, outputs `binary_op(val, std::move(acc))`, and then move-assigns `val` to `acc`. Since the previous value is already in `acc`, ¶8 allows `result == first`;
- ¶5 The parallel version computes `*(result + d) = binary_op(*(first + d), *(first + (d − 1)))` directly, each position independently. Writing in place would change values other positions need to read, so ¶8 requires that the input and output ranges not overlap.

The semantics of a parallel algorithm are generally the same as its non-parallel counterpart ([[algorithms.parallel.overloads#2]]); this is an "otherwise specified" example.

## `iota` and `ranges::iota` ([numeric.iota])

¶2 `iota(first, last, value)` assigns `value`, `++value`, `++value`, … in turn. ¶1 *Mandates* only require `T` to be convertible to the element type and `++val` to be well-formed, so `T` can also be an iterator: `iota(its.begin(), its.end(), v.begin())` produces a set of iterators to each element of `v`.

¶4 `ranges::iota` (C++23) returns `{last, value}`, handing the incremented `value` back to the caller, convenient for filling the next segment. It assigns using `as_const(value)`.

`iota` has been `constexpr` since C++20; [[P1645R1]] made these algorithms in `<numeric>` `constexpr`. None of the parallel versions are `constexpr`.

## Questions

!!! question "Question 1"
    Is calling `std::reduce(v.begin(), v.end(), std::string{}, std::plus<>())` on a `vector<std::string>` valid? Is the result deterministic?

<details markdown="1">
<summary>Answer</summary>

It is valid; all four combinations required by *Mandates* are convertible to `std::string`. But string concatenation is not commutative, while *GENERALIZED_SUM* allows any permutation, so the result is nondeterministic: the strings may be concatenated in any order. When you need in-order concatenation, use `accumulate` or `ranges::fold_left`. Concatenation is associative, so when you need parallelism while keeping the order, you can take the last output of `inclusive_scan`.
</details>

!!! question "Question 2"
    Why does `inclusive_scan` require the input element type `U` to be move constructible without `init`, but `T` to be move constructible with `init`?

<details markdown="1">
<summary>Answer</summary>

Because the type of the partial sums differs. Without `init`, the partial sums start from `*first` and have type `U`; with `init`, they start from `init` and have type `T` ([inclusive.scan] ¶3–¶5). The implementation needs to move partial sums internally, for example when combining the prefixes of blocks, so the type carrying the partial sums must be move constructible.
</details>

## Summary

| Algorithm | Defined by | For a deterministic result, the operation must be | Parallel version |
|---|---|---|---|
| `accumulate`, `inner_product`, `partial_sum` | strictly left to right | no requirement | none |
| `reduce`, `transform_reduce` | *GENERALIZED_SUM* | associative and commutative | yes |
| `inclusive_scan`, `exclusive_scan` and transform versions | *GENERALIZED_NONCOMMUTATIVE_SUM* | associative | yes |
| `adjacent_difference` | pairwise `op(current, previous)` | no requirement | yes, not in place |
| `iota` | repeated `++value` | n/a | none |
