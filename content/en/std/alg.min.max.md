---
title: Minimum and maximum, clamp, lexicographical comparison and permutations
summary: "The dangling caused by min, max and minmax returning references, and which argument each returns when they are equivalent; the min_element family and the precondition of clamp; lexicographical_compare and its three-way version; and how next_permutation and prev_permutation wrap around to the first permutation after the last."
updated: 2026-10-19
---

!!! tldr
    - The two-argument `min`, `max` and `minmax`, and `clamp`, return references to their arguments; when the arguments are temporaries, the result dangles after the full-expression ends.
    - When the two arguments are equivalent, `min` and `max` both return the first; `minmax(a, b)` returns `{a, b}`, so its max is the second argument.
    - `max_element` returns the leftmost largest element; `minmax_element` returns the rightmost largest element.
    - `clamp(v, lo, hi)` requires `lo` not to be greater than `hi`; otherwise the behavior is undefined.
    - After the last permutation, `next_permutation` turns the sequence back into ascending order and returns `false`.

## `min`, `max`, `minmax` ([alg.min.max] ¶1–¶24)

### Returning references: temporaries dangle

```cpp run title="min_dangle.cpp" flags="-std=c++2c -O0 -fsanitize=address" ub
#include <algorithm>
#include <cstdio>
#include <string>

int main() {
    const std::string& r =
        std::min(std::string("apple"), std::string("banana"));
    std::printf("%s\n", r.c_str());   // UB: r is bound to a destroyed temporary
}
```

The two-argument `min` and `max` return `const T&`, and `minmax` returns `pair<const T&, const T&>`, all referring to the arguments themselves. When the arguments are temporaries, they are destroyed at the end of the full-expression, and the references dangle with them ([[class.temporary]]). Binding a `const T&` to a reference returned by a function does not extend the lifetime of those two temporaries.

Clang 23 gives a `-Wdangling` warning for this code, because libc++ annotates these functions with `[[clang::lifetimebound]]`; at run time AddressSanitizer reports `stack-use-after-scope`. Writing `auto r = std::min(...)`, which copies the result, fixes it. The two-argument versions of `ranges::min` and `ranges::max` also return `const T&` and have the same problem.

### Which one is returned when equivalent

- ¶2 `min` returns the first argument when the two are equivalent;
- ¶10 `max` also returns the first argument when the two are equivalent;
- ¶18 `minmax(a, b)` returns `{b, a}` if `b` is less than `a`, and `{a, b}` otherwise.

So when the two arguments are equivalent, `minmax(a, b).second` is `b`, while `max(a, b)` is `a`. The result of `minmax` is exactly the result of stably sorting `{a, b}`: equivalent elements keep their original order. The rule that `max` returns the first argument dates back to C++98 and can no longer be changed.

### Range versions: return values, and the range must not be empty

The versions that take a set of values, such as `min(initializer_list<T>)` and `ranges::min(r)`, return a value rather than a reference, of type `T` or `range_value_t<R>`. ¶5 requires the range to be non-empty (`ranges::distance(r) > 0`); violating this is {{ub}}.

When there are several equivalent extreme values, ¶6 and ¶14 specify that `min` and `max` both return a copy of the leftmost one, and ¶22 specifies that `minmax` returns the leftmost smallest and the rightmost largest.

### Explicit template arguments are allowed

The *Remarks* in ¶4, ¶8 and the other paragraphs specify that `T` may be explicitly specified when calling these overloads in `std`. In general, explicitly specifying template arguments for standard algorithms is unspecified ([[algorithms.requirements#15]]); this is an explicitly stated exception.

The typical use is arguments of different types: in `std::max(1, 2L)` the deductions of `T` conflict and compilation fails; `std::max<long>(1, 2L)` is valid.

## `min_element`, `max_element`, `minmax_element` (¶25–¶32)

These three functions return iterators, returning `last` for an empty range (`minmax_element` returns `{first, first}`).

- ¶26 `min_element` returns the first smallest element;
- ¶29 `max_element` returns the first largest element;
- ¶31 `minmax_element` returns the first smallest element and the last largest element. Footnote 183 points out specifically that this difference from `max_element` is intentional, for the same reason as `minmax`: it matches the first and last elements after a stable sort.

¶32 `minmax_element` makes at most max(⌊3(N − 1)/2⌋, 0) comparisons. It processes elements in pairs: the two elements of each pair are compared with each other once, then the smaller is compared with the current minimum and the larger with the current maximum. Calling `min_element` and `max_element` separately takes 2(N − 1).

```cpp run title="minmax.cpp" ok
#include <algorithm>
#include <cassert>
#include <vector>

int main() {
    std::vector<int> v{3, 1, 5, 1, 5};
    auto mx = std::max_element(v.begin(), v.end());
    auto [mn, mx2] = std::minmax_element(v.begin(), v.end());
    assert(mx - v.begin() == 2);    // max_element: leftmost maximum
    assert(mx2 - v.begin() == 4);   // minmax_element: rightmost maximum
    assert(mn - v.begin() == 1);    // leftmost minimum

    long m = std::max<long>(1, 2L); // explicit template argument: explicitly allowed by the standard
    assert(m == 2);
}
```

## `clamp` ([alg.clamp]) {{c++17}}

`clamp(v, lo, hi)` limits `v` to `[lo, hi]`; it was introduced by [[P0025R1]].

¶2 The precondition is that `comp(hi, lo)` is false, i.e. `lo` is not greater than `hi`. `clamp(v, 10, 0)` is {{ub}}; it does not return one of the bounds.

¶3 Returns `lo` if `v` is less than `lo`, `hi` if `hi` is less than `v`, and `v` otherwise. The return is again `const T&`, with the same risk of dangling. ¶5 At most two comparisons.

¶4 Note 1 says `T` can be a floating-point type as long as NaNs are avoided. NaN makes `<` no longer a strict weak ordering.

## Lexicographical comparison ([alg.lex.comparison])

`lexicographical_compare` tests whether the first sequence is lexicographically less than the second. ¶3 gives the definition of lexicographical order:

- if the two sequences have the same length and all corresponding elements are equivalent, neither is less than the other;
- if one sequence is a proper prefix of the other, the shorter is less;
- otherwise the result is decided by the first pair of non-equivalent elements.

¶5 Note 1 adds that an empty sequence is less than any non-empty sequence, but not less than an empty one.

¶2 At most 2·min(N1, N2) comparisons. Each pair of elements is compared at most twice: `comp(a, b)` tests less-than and `comp(b, a)` tests greater-than. The sample implementation in ¶4 is written exactly that way.

## Three-way lexicographical comparison ([alg.three.way]) {{c++20}}

`lexicographical_compare_three_way(b1, e1, b2, e2, comp)` gives one of three results, less, equal or greater, in one go:

- ¶2 *Mandates*: `decltype(comp(*b1, *b2))` must be a comparison category type ([[cmp.categories]]); otherwise compilation fails;
- ¶3 returns the first result for which `comp(*(b1 + i), *(b2 + i)) != 0`; if all corresponding elements are equal, it returns `(e1 - b1) <=> (e2 - b2)`, i.e. compares the lengths;
- ¶4 at most N applications of `comp`, where N is the smaller of the two lengths.

Each pair of elements is compared only once, which is where it saves over `lexicographical_compare`. ¶5 The version without `comp` uses `compare_three_way()`. The `operator<=>` of the standard containers is also defined with it, except that the comparator is the exposition-only *synth-three-way*: when the element type has no `<=>`, it falls back to synthesizing a three-way result from `<`; see [[container.opt.reqmts]].

```cpp run title="lex.cpp" ok
#include <algorithm>
#include <cassert>
#include <compare>
#include <vector>

int main() {
    std::vector a{1, 2, 3}, b{1, 2};
    assert(!std::lexicographical_compare(a.begin(), a.end(),
                                         b.begin(), b.end()));
    auto c = std::lexicographical_compare_three_way(
        a.begin(), a.end(), b.begin(), b.end());
    assert(c == std::strong_ordering::greater);   // b is a proper prefix of a
}
```

## Permutation generators ([alg.permutation.generators])

¶3 `next_permutation` transforms the sequence into the next permutation in lexicographical order with respect to `comp`. If there is no next permutation, i.e. the sequence is already in descending order, it transforms the sequence into the first permutation, i.e. ascending order, and returns `false`. ¶8 `prev_permutation` is symmetric, wrapping around to descending order. ¶5, ¶10 At most (last − first)/2 swaps, and only bidirectional iterators are needed.

With this design, when the classic `do { ... } while (std::next_permutation(...))` loop ends, the sequence is back in ascending order. To enumerate all permutations, you must start from ascending order; otherwise only the permutations after the current one are enumerated. When the sequence contains duplicates, `next_permutation` generates only distinct permutations, because it advances in lexicographical order. The `ranges` version returns an `in_found_result`, i.e. `{last, whether one was found}`.

```cpp run title="perm.cpp" ok
#include <algorithm>
#include <cassert>
#include <vector>

int main() {
    std::vector p{1, 2, 3};
    int n = 1;
    while (std::next_permutation(p.begin(), p.end())) ++n;
    assert(n == 6);
    assert((p == std::vector{1, 2, 3}));   // back to ascending order when it returns false

    std::vector q{1, 1, 2};
    int k = 1;
    while (std::next_permutation(q.begin(), q.end())) ++k;
    assert(k == 3);                        // duplicates: only 3 distinct permutations
}
```

## Questions

!!! question "Question 1"
    `f()` and `g()` return `int`. Is it safe to use `lo` and `hi` after `const auto& [lo, hi] = std::minmax(f(), g());`?

<details markdown="1">
<summary>Answer</summary>

No. `minmax` returns `pair<const int&, const int&>`, whose two references point to two temporary `int`s. The `const auto&` of the structured binding extends only the lifetime of the `pair` temporary, not of the two `int` temporaries it refers to. After the full-expression ends, `lo` and `hi` both dangle.

You can write `auto [lo, hi] = std::minmax({f(), g()});`: the `initializer_list` version returns `pair<int, int>`, holding values. Or store the results of `f()` and `g()` in variables first.
</details>

!!! question "Question 2"
    What happens in `std::clamp(x, 0.0, 1.0)` when `x` is NaN?

<details markdown="1">
<summary>Answer</summary>

The precondition of ¶2, that `comp(hi, lo)` is false, is met, since `1.0 < 0.0` is false. But `clamp` belongs to [alg.sorting], and [[alg.sorting#3]] requires the comparator to induce a strict weak ordering on the values actually compared. NaN is equivalent to both `0.0` and `1.0`, while `0.0 < 1.0`, so equivalence is not transitive, and by the standard this is {{ub}}. That is what the note in ¶4 about avoiding NaNs refers to.

Real implementations compare as written in ¶3: `x < 0.0` and `1.0 < x` are both false, so `x`, i.e. NaN, is returned. That is the result with libc++ in our tests, but it is not guaranteed by the standard.
</details>

## Summary

| Function | Returns | When equivalent | Watch out |
|---|---|---|---|
| `min(a, b)`, `max(a, b)` | `const T&` | both return the first | dangles when arguments are temporaries |
| `minmax(a, b)` | `pair<const T&, const T&>` | `{a, b}`, max is `b` | same as above |
| `min(il)`, `max(il)` | value | the leftmost one | an empty range is UB |
| `max_element`, `minmax_element` | iterator | leftmost maximum, rightmost maximum | an empty range returns `last` |
| `clamp` | `const T&` | n/a | `hi < lo` is UB; avoid NaN |
| `lexicographical_compare` | `bool` | n/a | ≤ 2·min(N1, N2) comparisons |
| `lexicographical_compare_three_way` | comparison category | n/a | ≤ min(N1, N2) applications |
| `next_permutation` | `bool` | n/a | wraps to ascending order and returns `false` |
