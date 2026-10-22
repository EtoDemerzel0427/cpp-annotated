---
title: Random number distributions
summary: "The 20 standard distributions: their algorithms are implementation-defined, so results are not reproducible across implementations; the intervals and preconditions of the two uniform distributions; the parameters, defaults and preconditions of the others; the three weighted sampling distributions; and common misuses."
updated: 2026-10-19
---

!!! tldr
    - The standard specifies only which probability distribution each distribution's results follow; the transformation algorithm is implementation-defined. With the same engine and the same seed, a different standard library may give different results.
    - `uniform_int_distribution(a, b)` is the closed interval [a, b], with every value exactly equally likely; default construction gives [0, `max()`], not [0, 1].
    - `uniform_real_distribution(a, b)` is nominally the half-open interval [a, b), but in practice it may return b.
    - The preconditions of most distributions are strict inequalities; for example, the normal distribution requires σ > 0. Violating a precondition is UB; it does not degrade to a constant.
    - `discrete_distribution` draws indices by weight; the weights must be non-negative and finite, with a positive sum.

## Same seed, different faces

```cpp run title="dist-not-portable.cpp" impl
#include <cstdio>
#include <random>

int main() {
  std::mt19937 g(42);            // engine: identical everywhere
  std::uniform_int_distribution<int> die(1, 6);
  for (int i = 0; i < 8; ++i) std::printf("%d ", die(g));
  // libc++ in our tests prints: 4 5 3 5 5 2 3 3
  // other standard libraries may print a different sequence
}
```

The output of `mt19937(42)` is specified; its first two values are 1608637542 and 3421126067 on any implementation ([[rand.eng]]). But [rand.dist.general] ¶3 says the algorithms for producing each distribution are implementation-defined. A normal distribution can use Box–Muller, the Marsaglia polar method or the Ziggurat algorithm; uniform integers can use different rejection sampling strategies. They consume engine output in different amounts and ways, so naturally the results differ.

So when you need cross-platform reproducibility, you can only use the engine's raw output and write the distribution transformation yourself. Tests should not assert that some seed rolls some face either.

The common interface of distributions, such as `param_type`, `reset()` and `d(g, p)`, is specified in [[rand.req]] ([[g:random-number-distribution]]). This page covers what is specific to each distribution: probability function, parameters, preconditions.

## Uniform integer distribution ([rand.dist.uni.int])

¶1 `uniform_int_distribution<IntType>` produces integers a ≤ i ≤ b with P(i | a, b) = 1/(b − a + 1).

- The interval is closed. `uniform_int_distribution<int>(1, 6)` produces 1 through 6, including 6.
- The probabilities are exactly equal. As long as the engine is uniform, implementations must eliminate the modulo bias of `rand() % n`, usually by rejection sampling: redraw when the engine value falls in the tail that does not divide evenly ([[rand]]).
- Default construction is equivalent to `(0)`, and the default argument of `b` is `numeric_limits<IntType>::max()`, so the default gives [0, `max()`].
- ¶2 The precondition is a ≤ b. `uniform_int_distribution<int>(6, 1)` is UB; the bounds are not swapped automatically.
- The full range works too: `uniform_int_distribution<long long>(LLONG_MIN, LLONG_MAX)` is valid. Here b − a + 1 is mathematically 2⁶⁴, which `long long` cannot represent, but computations in [rand] are done over the mathematical reals ([[rand]]), and implementations must handle it correctly.
- `IntType` cannot be `char` or `bool`, but can be `signed char` or `unsigned char` ([[rand.req]]).

## Uniform real distribution ([rand.dist.uni.real])

¶1 `uniform_real_distribution<RealType>` produces numbers a ≤ x < b with probability density p(x | a, b) = 1/(b − a). A note points out this means the density is undefined when a == b.

- The interval is nominally half-open, [a, b), unlike the closed interval of the integer version.
- Default construction is equivalent to `(0.0)`, with `b` defaulting to 1.0, that is, [0, 1).
- ¶2 The preconditions are a ≤ b and b − a ≤ `numeric_limits<RealType>::max()`. So `uniform_real_distribution<double>(-DBL_MAX, DBL_MAX)` is UB, because the length of the interval is not representable.
- a == b satisfies the preconditions, but the standard does not say what is returned in that case. libc++ in our tests returns 2.0 for `(2.0, 2.0)`; don't rely on it.

!!! pitfall "The half-open interval is not always half-open"
    Implementations usually compute a + (b − a)·u, with u from `generate_canonical`. Even if u < 1, rounding in the multiplication and addition can make the result equal b. On top of that, libc++'s `generate_canonical` itself may return 1.0 ([[rand.util]]), so `uniform_real_distribution` does occasionally return b in practice. Code sensitive to b, such as multiplying the result by n to use as an array index, should clamp the result itself.

## The other parameterized distributions

Apart from the two uniform distributions and the three sampling distributions, the remaining 15 distributions are grouped by mathematical family into three subclauses: Bernoulli [rand.dist.bern], Poisson [rand.dist.pois] and normal [rand.dist.norm]. Each distribution's specification has the same structure: ¶1 gives the probability function, then the class synopsis, ¶2 the constructor's preconditions, and the following paragraphs the parameter accessors.

The default parameters in the table below are those the default constructor is equivalent to; violating a precondition is UB in every case.

| Distribution | Result type | Parameters (defaults) | Range | Preconditions |
|---|---|---|---|---|
| `bernoulli_distribution` | `bool` | p = 0.5 | {false, true} | 0 ≤ p ≤ 1 |
| `binomial_distribution` | `IntType` | t = 1, p = 0.5 | 0 ≤ i ≤ t | 0 ≤ p ≤ 1, 0 ≤ t |
| `geometric_distribution` | `IntType` | p = 0.5 | i ≥ 0 | 0 < p < 1 |
| `negative_binomial_distribution` | `IntType` | k = 1, p = 0.5 | i ≥ 0 | 0 < p ≤ 1, 0 < k |
| `poisson_distribution` | `IntType` | mean = 1.0 | i ≥ 0 | 0 < mean |
| `exponential_distribution` | `RealType` | λ = 1.0 | x > 0 | 0 < λ |
| `gamma_distribution` | `RealType` | α = 1.0, β = 1.0 | x > 0 | 0 < α, 0 < β |
| `weibull_distribution` | `RealType` | a = 1.0, b = 1.0 | x ≥ 0 | 0 < a, 0 < b |
| `extreme_value_distribution` | `RealType` | a = 0.0, b = 1.0 | reals | 0 < b |
| `normal_distribution` | `RealType` | μ = 0.0, σ = 1.0 | reals | 0 < σ |
| `lognormal_distribution` | `RealType` | m = 0.0, s = 1.0 | x > 0 | 0 < s |
| `chi_squared_distribution` | `RealType` | n = 1.0 | x > 0 | 0 < n |
| `cauchy_distribution` | `RealType` | a = 0.0, b = 1.0 | reals | 0 < b |
| `fisher_f_distribution` | `RealType` | m = 1.0, n = 1.0 | x ≥ 0 | 0 < m, 0 < n |
| `student_t_distribution` | `RealType` | n = 1.0 | reals | 0 < n |

Some easy-to-get-wrong points:

- `bernoulli_distribution` is not a template; its result is always `bool` and its parameter p is a `double`. The probability or mean parameters of the binomial, geometric, negative binomial and Poisson distributions are also `double`, unrelated to `IntType`.
- The geometric distribution counts from 0: P(i | p) = p·(1 − p)ⁱ, where i is the number of failures before the first success, not the trial on which the first success occurs. The example below verifies that the mean is (1 − p)/p, not 1/p.
- The negative binomial distribution's precondition allows p = 1, but a note says the probability function is undefined when p == 1. This is another case where the precondition is met but the standard does not say what the result is.
- The normal distribution's σ must be strictly greater than 0. `normal_distribution<double>(mu, 0.0)` is UB, not "always returns mu"; if you need the degenerate case, special-case it yourself.
- The m and s of `lognormal_distribution(m, s)` are the mean and standard deviation of the logarithm, not of the distribution itself. The a and b of `extreme_value_distribution` are location and scale; footnote 225 notes it is also known as the Gumbel distribution.
- The normal distribution, and the lognormal, χ², t and F distributions based on it, typically compute two values at once and cache one, so `reset()` actually matters (see the question in [[rand]]).

```cpp run title="geometric-count.cpp" ok
#include <random>

int main() {
  std::mt19937 g(1);
  std::geometric_distribution<int> fails(0.25);   // success probability 1/4
  int sum = 0;
  for (int i = 0; i < 100000; ++i) sum += fails(g);
  double mean = sum / 100000.0;     // expected (1 − p)/p = 3
  return (mean > 2.9 && mean < 3.1) ? 0 : 1;
}
```

## Weighted sampling ([rand.dist.samp])

### discrete_distribution ([rand.dist.samp.discrete])

```cpp run title="discrete.cpp" ok
#include <random>
#include <vector>

int main() {
  // P(0) = 1/4, P(1) = 0, P(2) = 3/4
  std::discrete_distribution<int> w{1.0, 0.0, 3.0};
  std::vector<double> p = w.probabilities();   // {0.25, 0, 0.75}
  std::mt19937 g(7);
  int c[3] = {};
  for (int i = 0; i < 100000; ++i) ++c[w(g)];
  return (c[1] == 0 && p[2] == 0.75) ? 0 : 1;  // index 1 never appears
}
```

¶1 `discrete_distribution` produces integers 0 ≤ i < n with P(i) = pᵢ. ¶2 Unless otherwise specified, pₖ = wₖ / S, where the **weights** wₖ must be non-negative, not NaN and not infinity, with sum S > 0. Violating these requirements is UB.

There are four ways to construct it:

- ¶3 Default construction: n = 1, p₀ = 1. A note says such an object always returns 0.
- ¶4–¶6 An iterator range `(firstW, lastW)`: the value type must be convertible to `double`; an empty range is equivalent to default construction.
- ¶7 `initializer_list<double>`: same as above; the example uses this form.
- ¶8–¶11 `(nw, xmin, xmax, fw)`: divides [xmin, xmax] into n equal parts and takes each part's weight as the value of `fw` at its midpoint. The precondition is that each part's width δ = (xmax − xmin)/n > 0; `fw` is called at most n times.

¶12 `probabilities()` returns the normalized pₖ.

`discrete_distribution` accepts `initializer_list<double>`, so `discrete_distribution<int> d{3};` is a distribution with a single weight 3 that always returns 0. Meanwhile `uniform_int_distribution<int> d{3};` calls the `(a, b)` constructor and gives [3, `INT_MAX`]. The same braces, entirely different meanings.

### piecewise_constant_distribution ([rand.dist.samp.pconst])

¶1 `piecewise_constant_distribution` produces numbers b₀ ≤ x < bₙ, uniformly distributed within each subinterval [bᵢ, bᵢ₊₁) with density ρᵢ. ¶2 The interval boundaries must be strictly increasing; ρₖ = wₖ / (S·(bₖ₊₁ − bₖ)), with the same weight requirements as `discrete_distribution`.

- ¶3 Default construction: a single interval [0, 1), that is, the uniform distribution on [0, 1).
- ¶4–¶6 `(firstB, lastB, firstW)`: fewer than two boundaries degrades to the default; otherwise n + 1 boundaries correspond to at least n weights, with any extras ignored. Only a starting iterator is given for the weights, and their length is determined by the boundaries; supply too few and it reads out of bounds.
- ¶7–¶9 `(initializer_list<RealType> bl, fw)`: the weights are the values of `fw` at the midpoint of each subinterval.
- ¶10–¶13 `(nw, xmin, xmax, fw)`: equal subdivision, with weights taken from `fw` at the midpoints.
- ¶14–¶15 `intervals()` and `densities()` return the boundaries and densities.

### piecewise_linear_distribution ([rand.dist.samp.plinear])

Its structure parallels the piecewise constant distribution. The difference is that the density is linearly interpolated within each subinterval: n + 1 boundaries correspond to n + 1 weights, the density at each boundary is the corresponding normalized weight, and it varies linearly in between. Accordingly, the upper bound on calls to `fw` in each constructor is n + 1. Given density values at a number of sample points, you get a polyline approximation of any continuous density.

## Common misuses

!!! pitfall "Creating a new distribution object on every call"
    `int roll(G& g) { return std::uniform_int_distribution<int>(1, 6)(g); }` is correct; distribution objects are light and cheap to construct. But writing it this way for a distribution with internal state (such as the normal distribution) throws away the cached second value, wasting half the engine output. When you need different parameters, use `d(g, param_type(...))` ([[rand.req]]).

!!! pitfall "Passing the engine by value"
    `int roll(std::mt19937 g)` copies about 2.5 KB of state each time, and the caller's engine never advances, so every call gives the same result. Pass engines by reference.

!!! pitfall "Writing tests against distribution output"
    A test asserting that seed 42 rolls a 4 will fail after switching compilers or upgrading the standard library. Either assert only statistical properties, or assert the engine's output directly; [[rand.eng]] gives the values the standard specifies.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[rand.dist.general]: ¶1 the types obtained by instantiation meet the distribution requirements; ¶2 copying, the stream operators and the equality operators are not listed in the synopses; ¶4 the probability functions are 0 everywhere outside the stated domain.

¶3 *Remarks* of each distribution say which parameter each constructor argument corresponds to, and the *Returns* paragraphs after it specify that accessors (such as `a()`, `mean()`, `stddev()`) return the parameter values given at construction.

</details>
