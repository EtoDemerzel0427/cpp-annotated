---
title: seed_seq and generate_canonical
summary: "How the standard seed sequence seed_seq handles its input (each value taken modulo 2³²) and produces seeds; how generate_canonical turns integers into floating-point numbers in [0, 1), and the returns-1.0 problem the new specification fixes."
updated: 2026-10-19
---

!!! tldr
    - `seed_seq` stores each input value modulo 2³², so the high 32 bits of a 64-bit seed are simply discarded.
    - The mixing algorithm of `seed_seq::generate` is specified step by step, reproducible across implementations, and depends only on the input at construction.
    - `seed_seq` cannot be copied, and the engine constructors that accept it require a non-const lvalue.
    - The current specification of `generate_canonical` first obtains a uniform integer by rejection sampling, then divides by a power of 2, so the result is strictly less than 1.
    - The old specification divided in floating point and could round to 1.0; libc++ in our tests still uses the old algorithm.

## seed_seq ([rand.util.seedseq])

`seed_seq` is the standard-provided **seed sequence** ([[g:seed-sequence]]): it stores a sequence of integers and, when needed, stirs them into any number of 32-bit values used to initialize an engine's state ([[rand.req]]). For usage, see the seeding section of [[rand]].

### Input taken modulo 2³² (¶1–¶6)

```cpp run title="seed-seq-truncate.cpp" ok
#include <cassert>
#include <cstdint>
#include <iterator>
#include <random>
#include <vector>

int main() {
  std::seed_seq a{std::uint64_t{0x1'0000'0001}}, b{1u};
  std::vector<std::uint32_t> pa, pb;
  a.param(std::back_inserter(pa));
  b.param(std::back_inserter(pb));
  assert(pa == pb);              // both {1}
  std::mt19937 g1(a), g2(b);
  assert(g1 == g2);              // the engine states are the same too
}
```

In the synopsis, `seed_seq` has a single exposition-only data member `vector<result_type> v`, with `result_type` being `uint_least32_t`. ¶1 After default construction `v` is empty. ¶6 The iterator constructor does `v.push_back((*s) mod 2³²)` for each input element, so in the example above only 1 is left of `0x1'0000'0001`. To use a 64-bit seed, split it into two 32-bit values yourself.

The two constructors check the element type differently. ¶2 The `initializer_list<T>` version uses *Constraints* to require `T` to be an integer type; ¶4 the iterator version uses *Mandates* to require the value type to be an integer type. When *Constraints* are not met, the overload drops out of overload resolution; when *Mandates* are not met, the program is ill-formed once that overload is selected.

<div class="compare" markdown="1">

```cpp error
#include <random>
// no viable constructor:
// initializer_list<double> does not satisfy the constraint
std::seed_seq s{1.5};
```

```cpp error
#include <random>
#include <vector>
std::vector<double> d{1.5};
// the iterator version is selected, then violates Mandates
std::seed_seq s(d.begin(), d.end());
```

</div>

Both are compile errors. The difference is that the former can be detected silently by something like `std::is_constructible`, and the latter cannot: `is_constructible_v<seed_seq, double*, double*>` is true.

### The algorithm of generate (¶7–¶9)

¶9 specifies the algorithm of `generate(begin, end)` step by step. With s = `v.size()` and n = `end - begin`, and all arithmetic modulo 2³²:

1. set the whole output range to `0x8b8b8b8b`, and choose two offsets p and q based on the size of n;
2. a first mixing pass, injecting the elements of `v` one by one, for max(s + 1, n) steps;
3. a second mixing pass of n more steps.

This algorithm shares its origin with the `init_by_array` initialization routine given by the authors of the Mersenne Twister. It reads only `v` and does not depend on previous calls, so calling `generate` repeatedly on the same `seed_seq` gives the same result. The general seed sequence requirements allow dependence on call history ([[rand.req]]), so generic code should not rely on this.

¶7 requires the value type of the destination iterator to be an unsigned integer type able to hold 32 bits.

!!! note "Limitations of seed_seq"
    `generate` is a fixed deterministic function mapping s 32-bit inputs to n 32-bit outputs. When n is large (`mt19937` needs 624), the standard does not require this mapping to be injective, and analyses have pointed out that at some sizes it indeed is not: different inputs may give the same engine state, and some states can never be reached. For simulations, games and the like this does not matter, but the job of `seed_seq` is only to spread a small amount of entropy evenly; it is not a high-quality hash.

### Saving and rebuilding (¶11–¶15)

`size()` returns the number of 32-bit units `param()` will write, that is, `v.size()`. `param(dest)` is as if `copy(v.begin(), v.end(), dest)`. Constructing a new `seed_seq` from the written sequence yields an equivalent object; the example above uses `param` to compare two seed sequences.

The copy constructor and copy assignment of `seed_seq` are deleted.

## generate_canonical ([rand.util.canonical])

```cpp
template<class RealType, size_t digits, class URBG>
  RealType generate_canonical(URBG& g);
```

It takes enough bits from `g` to produce a `RealType` value in [0, 1) that is as uniform as possible. Floating-point distributions such as `uniform_real_distribution` are usually built on it. The current specification comes from [[P0952R2]] and differs from the original C++11 specification.

### The current specification (¶1–¶5)

¶1 first defines several quantities:

- r = `numeric_limits<RealType>::radix`, usually 2;
- R = `g.max() - g.min() + 1`, the size of the URBG's range;
- d = min(`digits`, `numeric_limits<RealType>::digits`). Footnote 224 explains this avoids producing random bits that `RealType` cannot hold;
- k is the smallest integer such that Rᵏ ≥ rᵈ;
- x = ⌊Rᵏ / rᵈ⌋.

An **attempt** calls `g()` k times to get g₀, …, gₖ₋₁ and computes S = Σ (gᵢ − g.min())·Rⁱ.

¶2 Attempts are repeated until S < x·rᵈ. A note points out that when R is a power of r, exactly one attempt is needed. ¶3 The return value is ⌊S / x⌋ / rᵈ, and a note says the result c satisfies 0 ≤ c < 1. ¶5 Each attempt calls `g` exactly k times.

Intuitively, S is a uniform integer in [0, Rᵏ). Accepting only S in [0, x·rᵈ) and then dividing by x gives a uniform integer in [0, rᵈ). The final division by rᵈ is exact for binary floating point, changing only the exponent. So the result is one of rᵈ equally spaced values, each with exactly the same probability, and the largest is only 1 − r⁻ᵈ.

### Why the old specification could return 1.0

The C++11 specification computed S in `RealType` and returned S / Rᵏ. An integer like Rᵏ − 1 is not exactly representable in `float` and rounds to Rᵏ, so when S is near its maximum, S / Rᵏ rounds to 1.0. This broke the [0, 1) promise the old specification itself gave in a note. The problem was reported in [[LWG2524]].

libc++ in our tests still uses the old algorithm. A URBG that always returns its maximum triggers it:

```cpp run title="canonical-one.cpp" impl
#include <cstdint>
#include <cstdio>
#include <random>

struct MaxGen {
  using result_type = std::uint32_t;
  static constexpr result_type min() { return 0; }
  static constexpr result_type max() { return UINT32_MAX; }
  result_type operator()() { return max(); }
};

int main() {
  MaxGen g;
  float c = std::generate_canonical<float, 32>(g);
  std::printf("%.9g\n", c);   // libc++ prints 1; the current specification requires 0.99999994
}
```

Working it out by hand under the current specification: r = 2, R = 2³², d = min(32, 24) = 24, k = 1, x = ⌊2³² / 2²⁴⌋ = 256. S = 2³² − 1 < 256·2²⁴, so the first attempt is accepted; the result is ⌊(2³² − 1)/256⌋ / 2²⁴ = (2²⁴ − 1)/2²⁴ ≈ 0.99999994, which is less than 1.

A real `mt19937` outputs its maximum with probability only 2⁻³², but large simulations making billions of calls are common, and downstream code like `log(1 - u)` fails precisely at u = 1. This is also one of the reasons `uniform_real_distribution(a, b)` occasionally returns b ([[rand.dist]]).

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[rand.util.seedseq]: ¶5 the iterator constructor requires input iterators; ¶8 `generate` requires mutable random access iterators; ¶10 and ¶16 throw only when iterator operations throw; ¶12 `size()` is constant time; ¶13–¶14 `param` requires values of `result_type` to be writable to `dest`, which is an output iterator.

[rand.util.canonical]: ¶4 throws whatever `g` throws. ¶6 note: when `g` is uniform the result is as uniform as possible, which makes this a useful step in transforming URBG output into distribution results. ¶7 note: when R is a power of r, implementations need not use arithmetic types wider than the output to compute S.

</details>
