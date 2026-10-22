---
title: Mathematical functions for floating-point types
summary: "<cmath> follows C's <math.h> but uses overloads instead of f/l suffixes and specifies promotion rules for mixed arguments; it adds three-argument hypot, lerp and the mathematical special functions; C++23/26 make most functions constexpr; math errors are reported the C way and are not UB, while integer abs(INT_MIN) is UB."
updated: 2026-10-19
---

!!! tldr
    - `std::sqrt` and friends have an overload for every floating-point type; with mixed argument types, integer arguments count as `double`, so `std::pow(x, 2)` with a `float` returns `double`.
    - C++23 and C++26 make the vast majority of `<cmath>` functions `constexpr`, but a call that raises a floating-point exception other than `FE_INEXACT` (such as `sqrt(-1.0)`) is not a constant expression.
    - Domain errors, pole errors and range errors are not UB: depending on `math_errhandling`, `errno` is set or a floating-point exception is raised, and the return value is specified too. Code relying on `errno` is not portable.
    - Integer `std::abs(INT_MIN)` is UB; applying `std::abs` to an unsigned type that cannot be promoted to `int` is ill-formed.
    - `std::lerp(a, b, 1)` is guaranteed to equal `b` exactly, and the result is monotonic in t, which the naive formula `a + t*(b-a)` cannot achieve.

## One function name, many floating-point types ([cmath.syn])

```cpp run title="cmath-promotion.cpp" ok
#include <cmath>
#include <type_traits>
using std::is_same_v;

static_assert(is_same_v<decltype(std::sqrt(2)), double>);
static_assert(is_same_v<decltype(std::pow(1.0f, 2)), double>);
static_assert(is_same_v<decltype(std::pow(1.0f, 2.0f)), float>);
static_assert(is_same_v<decltype(std::fmax(1.0f, 2.0L)), long double>);
static_assert(is_same_v<decltype(std::abs(3)), int>);
```

C distinguishes types by suffix: `sqrtf`, `sqrt`, `sqrtl`. C++ keeps those names and also gives `std::sqrt` an overload for every floating-point type. The second line above often surprises people: when `x` is a `float`, the result of `std::pow(x, 2)` is `double`.

¶1 The contents of `<cmath>` are a subset of C's `<math.h>`; only the declarations listed in the synopsis are present. It additionally provides three-argument `hypot`, `lerp` and the mathematical special functions ([sf.cmath]). Note 1 says some functions have extra overloads in C++ but behave the same as in C.

The synopsis writes function signatures with the placeholder *floating-point-type*. The next two paragraphs specify how this placeholder expands into real overloads.

¶2 For each function with at least one parameter of *floating-point-type*, the implementation provides an overload for each cv-unqualified floating-point type ([[basic.fundamental]]), with every placeholder in the signature replaced by that type. Floating-point types include `float`, `double`, `long double`, and also extended floating-point types the implementation supports ([[basic.extended.fp]], such as `std::float16_t`); the latter were added by C++23's [[P1467R9]].

¶3 Except for `abs`, implementations also provide enough additional overloads to handle mismatched argument types. As long as the arguments corresponding to *floating-point-type* parameters all have arithmetic type, they are all converted to the floating-point type among them with the greatest floating-point conversion rank ([[g:floating-point-conversion-rank]], [[conv.rank]]) and greatest subrank, with integer arguments treated as having the same rank as `double` for this purpose.

The rule of treating integers as `double` comes from C's `<tgmath.h>`. `abs` is excluded, so `std::abs(3)` selects the integer version and returns `int`.

If no type with both the greatest rank and the greatest subrank exists, none of the overloads the implementation provides is usable. This can only happen between extended floating-point types: the value sets of `std::float16_t` and `std::bfloat16_t` do not contain each other, so their conversion ranks are unordered, and `std::pow(std::float16_t(1), std::bfloat16_t(2))` is ill-formed. libc++ in our tests has no `<stdfloat>`, so this could not be tested.

¶4 If the argument corresponding to the *floating-point-type* parameter of `nexttoward` has an extended floating-point type, the call is ill-formed. The second parameter of `nexttoward` is always `long double`, and the relationship between extended floating-point types and `long double` varies by platform, so the standard simply gives it no semantics.

## When it can be called at compile time

```cpp title="constexpr-cmath.cpp" error
#include <cmath>

constexpr double a = std::sqrt(2.0);    // OK (C++26): raises only FE_INEXACT
constexpr double b = std::sqrt(-1.0);   // error: raises FE_INVALID
constexpr double c = std::log(0.0);     // error: raises FE_DIVBYZERO
constexpr double d = std::floor(2.5);   // OK (C++23)
```

In the current draft, almost every function in the synopsis is marked `constexpr`. The exceptions are `nearbyint`, `rint`, `lrint` and `llrint`, whose results depend on the current rounding mode; `nan`, which parses a string; and all the mathematical special functions. This happened in two steps:

- C++23's [[P0533R9]] made the functions that need no approximation algorithms `constexpr`: `abs`, `fabs`, `floor`, `ceil`, `trunc`, `round`, `fmod`, `frexp`, `ldexp`, `fmin`, `fmax`, `copysign`, the classification and comparison functions, and so on.
- C++26's {{c++26}} [[P1383R2]] extended this to functions needing approximation, such as `sin`, `exp`, `log`, `pow`, `sqrt` and `hypot`.

`constexpr` does not mean every call is a constant expression. [[library.c#3]] says a call to a C standard library function that raises a floating-point exception other than `FE_INEXACT` is a [[g:non-constant-library-call|non-constant library call]], and the enclosing expression is not a core constant expression. Semantics during constant evaluation follow C's Annex F. Note 2 gives an equivalent formulation: on implementations where `math_errhandling & MATH_ERRNO` is true, these are exactly the calls that would set `errno`.

!!! impl "Not yet implemented in libc++"
    libc++ in our tests forwards these functions directly to the platform C library's non-`constexpr` functions, and `__cpp_lib_constexpr_cmath` is commented out in its `<version>`. So all four lines of the example above error in our tests, even `std::floor(2.5)` and `std::fabs(-2.5)`.

## Math errors are not UB

```cpp run title="math-errhandling.cpp" impl
#include <cerrno>
#include <cfenv>
#include <cmath>
#include <cstdio>

int main() {
  std::printf("ERRNO=%d ERREXCEPT=%d\n",
              (math_errhandling & MATH_ERRNO) != 0,
              (math_errhandling & MATH_ERREXCEPT) != 0);
  errno = 0;
  std::feclearexcept(FE_ALL_EXCEPT);
  volatile double m = -1.0;
  double r = std::sqrt(m);
  std::printf("%g errno=%d FE_INVALID=%d\n",
              r, errno, std::fetestexcept(FE_INVALID) != 0);
}
```

In our tests (macOS) the output is `ERRNO=0 ERREXCEPT=1` and `nan errno=0 FE_INVALID=1`: this platform reports errors only through floating-point exceptions and never sets `errno`. On glibc both mechanisms are usually enabled.

Error handling in `<cmath>` follows C entirely, with three kinds of errors:

- domain error: an argument is outside the function's domain, such as `sqrt(-1)`;
- pole error: the result mathematically goes to infinity, such as `log(0)`;
- range error: the result is too large or too small to represent.

On an error, if `math_errhandling & MATH_ERRNO` is true the function sets `errno` to `EDOM` or `ERANGE`; if `math_errhandling & MATH_ERREXCEPT` is true it raises the corresponding floating-point exception ([[cfenv]]). Which one or both an implementation supports is up to the implementation. The return value is specified as well; for example `sqrt(-1)` returns NaN. This differs from `<complex>`, where a mathematically undefined result is undefined behavior ([[complex.numbers]]).

## Absolute values ([c.math.abs])

¶1 Note 1 says both `<cstdlib>` and `<cmath>` declare the functions in this subclause.

¶2 The `int`, `long` and `long long` versions of `abs` have the semantics of C's `abs`, `labs` and `llabs` respectively. C says the behavior is undefined when the result is not representable, so:

```cpp run title="abs-int-min.cpp" ub
#include <climits>
#include <cstdlib>

int main(int argc, char**) {
  int v = INT_MIN + (argc - 1);   // INT_MIN, known only at run time
  return std::abs(v) > 0;         // UB: -INT_MIN is not representable
}
```

Running with `-fsanitize=undefined` reports `negation of -2147483648 cannot be represented in type 'int'`. On two's complement machines the typical result is `abs(INT_MIN) == INT_MIN`, a negative absolute value. For a safe version, convert to an unsigned type before negating, or use C++26 saturation arithmetic ([[numeric.sat]]).

¶3 If `abs` is called with an argument of type `X` for which `is_unsigned_v<X>` is true and `X` cannot be converted to `int` by integral promotion ([[conv.prom]]), the program is ill-formed. Note 2 says arguments that promote to `int` are allowed for C compatibility.

<div class="compare" markdown="1">

```cpp ok
#include <cstdlib>
unsigned short s = 1;
// promoted to int: well-formed
// Clang warns -Wabsolute-value
int a = std::abs(s);
```

```cpp error
#include <cstdlib>
unsigned u = 1;
// unsigned cannot be promoted to int
long b = std::abs(u);
```

</div>

This rule catches a common mistake: writing `std::abs(a - b)` when `a` and `b` are `size_t`. The difference has already wrapped around to a huge unsigned number, and taking its absolute value is meaningless. Clang in our tests reports `call to 'abs' is ambiguous` for the right-hand example.

¶4 The floating-point version `abs(floating-point-type)` returns the absolute value. In the synopsis the integer versions are marked freestanding and the floating-point versions *freestanding-deleted* ([[g:freestanding-deleted-function]]).

## Linear interpolation: lerp ([c.math.lerp])

```cpp run title="lerp.cpp" ok
#include <cmath>
#include <cstdio>

int main() {
  double a = 1e17, b = 3.0;
  double naive = a + 1.0 * (b - a);   // b - a rounds to -1e17, giving 0
  double r = std::lerp(a, b, 1.0);    // guaranteed to equal b exactly
  std::printf("%g %g\n", naive, r);   // 0 3
}
```

`lerp(a, b, t)` was introduced by C++20's [[P0811R3]] and is `noexcept`. ¶1 It returns a + t(b − a). The real value is in the *Remarks* of ¶2: with r the return value, when `isfinite(a) && isfinite(b)`,

- ¶2.1 r == a when `t == 0`;
- ¶2.2 r == b when `t == 1`, exactly;
- ¶2.3 r is finite when 0 ≤ t ≤ 1;
- ¶2.4 r == a when t is finite and a == b;
- ¶2.5 r is not NaN when t is finite, or when t is not NaN and b − a ≠ 0.

¶2 finally requires monotonicity: for any t₁ and t₂, the product of CMP(lerp(a,b,t₂), lerp(a,b,t₁)), CMP(t₂, t₁) and CMP(b, a) is non-negative, where CMP returns 1, −1 or 0. Intuitively, as t increases the result only moves in the direction from a to b and never backtracks.

The example above shows the naive formula `a + t * (b - a)` does not satisfy ¶2.2. The other naive formula, `(1 - t) * a + t * b`, guarantees exact endpoints but is not monotonic, and may not return a when a == b. Meeting all these properties at once requires case analysis on the range of t and the signs of a and b, which is the reason for putting it in the standard library.

## Three-dimensional hypot and classification functions

[c.math.hypot3] ¶1 `hypot(x, y, z)` returns √(x² + y² + z²); it was added by C++17's [[P0030R1]]. Computing `x*x + y*y + z*z` directly, the intermediate result overflows when x is around 1e200, even though the final result is perfectly representable; good implementations avoid such unnecessary overflow and underflow. The standard specifies only the mathematical meaning of the return value, not its accuracy.

[c.math.fpclass] ¶1 `fpclassify`, `isfinite`, `isinf`, `isnan`, `isnormal`, `signbit`, and the comparison functions `isgreater`, `isgreaterequal`, `isless`, `islessequal`, `islessgreater` and `isunordered` behave the same as the C macros of the same names. In C++ they are functions, with overloads per floating-point type and the additional overloads of ¶3, so you can write `std::isnan` and pass integers too. The comparison functions differ from built-in `>` and friends in that they do not raise `FE_INVALID` on NaN.

## Mathematical special functions ([sf.cmath])

C++17's [[P0226R1]] merged the earlier special functions technical report ISO/IEC 29124 into the standard. There are 21 families in all, each with a *floating-point-type* version and `f` and `l` suffixed versions:

| Category | Functions | Domain (summary) |
|---|---|---|
| orthogonal polynomials | `assoc_laguerre`, `assoc_legendre`, `hermite`, `laguerre`, `legendre` | Laguerre: x ≥ 0; Legendre: \|x\| ≤ 1 |
| beta, exponential integral, zeta | `beta`, `expint`, `riemann_zeta` | `beta`: x > 0, y > 0 |
| elliptic integrals | `comp_ellint_1/2/3`, `ellint_1/2/3` | \|k\| ≤ 1 |
| cylindrical Bessel functions | `cyl_bessel_i`, `cyl_bessel_j`, `cyl_bessel_k`, `cyl_neumann` | x ≥ 0 |
| spherical functions | `sph_bessel`, `sph_neumann`, `sph_legendre` | x ≥ 0; \|m\| ≤ ℓ |

### Uniform error rules ([sf.cmath.general])

¶1 If any argument is NaN, the function returns NaN but does not report a domain error. Otherwise, the function reports a domain error only when:

- ¶1.1 the *Returns* explicitly gives a domain and an argument falls outside it;
- ¶1.2 the corresponding mathematical function value has a non-zero imaginary part;
- ¶1.3 the corresponding mathematical function is mathematically undefined. A footnote says "defined" means explicitly defined for that set of arguments, or the limit exists and does not depend on the direction of approach.

¶2 Unless otherwise specified, each function is defined for all finite values and for positive and negative infinity.

Reporting a domain error here is in the C sense: per `math_errhandling`, setting `errno = EDOM` or raising `FE_INVALID`, not UB.

### High-order parameters are implementation-defined

The *Remarks* of many special functions say that the effect of a call with an integer order parameter of 128 or more is implementation-defined ({{impl}}). Examples are [sf.cmath.assoc.laguerre] ¶3 (n ≥ 128 or m ≥ 128), [sf.cmath.cyl.bessel.j] ¶3 (ν ≥ 128) and [sf.cmath.legendre] ¶3 (ℓ ≥ 128). These functions are hard to compute accurately at high orders, and the standard chose not to impose requirements.

### Watch the formula conventions

Each function's *Returns* gives a formula. Different textbooks may define the same function differing by a sign factor, so check when porting formulas:

- [sf.cmath.hermite] uses the physicists' Hermite polynomials Hₙ(x) = (−1)ⁿ e^(x²) dⁿ/dxⁿ e^(−x²).
- The Pₗᵐ(x) = (1 − x²)^(m/2) dᵐ/dxᵐ Pₗ(x) of [sf.cmath.assoc.legendre] does not include (−1)ᵐ (the Condon–Shortley phase), while the spherical harmonics of [sf.cmath.sph.legendre] do.
- The Lₙᵐ(x) of [sf.cmath.assoc.laguerre] is (−1)ᵐ dᵐ/dxᵐ Lₙ₊ₘ(x).

!!! impl "The state of libc++"
    libc++ in our tests implements only `hermite` (`std::hermite(3, 2.0)` returns 40). `riemann_zeta`, `cyl_bessel_j` and the rest do not exist; `std::riemann_zeta(2.0)` reports `no member named 'riemann_zeta' in namespace 'std'`. libstdc++ and the MSVC STL provide all the special functions.

## fma and floating-point contraction

`fma(x, y, z)` in the synopsis computes x·y + z with a single rounding at the end. It can expose errors that rounding swallows in ordinary expressions:

```cpp run title="fma.cpp" ok
#include <cmath>
#include <cstdio>

int main() {
  double p = 0.1 * 10.0 - 1.0;            // 0.1*10.0 rounds to 1.0, result 0
  double q = std::fma(0.1, 10.0, -1.0);   // rounded only once: 2^-54
  std::printf("%a %a\n", p, q);           // 0x0p+0 0x1p-54
}
```

Conversely, the compiler may automatically contract `a * b + c` into a single fma instruction. On arm64 in our tests, with `a * b + c` written in a function evaluated on run-time values, Clang by default (`-ffp-contract=on`) gives `0x1p-54`, and only with `-ffp-contract=off` gives `0x0p+0`. C controls this contraction with the `FP_CONTRACT` pragma; in C++, what permits it is [[expr.pre#6]]: floating-point operands and the results of floating-point expressions may be represented with greater precision and range than the type requires.

So the same floating-point expression may round differently under different compiler options. When you need bit-for-bit reproducibility, either write `fma` explicitly or turn contraction off.

## Questions

!!! question "Question 1"
    Is `std::abs(-2147483648)` (a literal, with 32-bit `int`) UB?

<details markdown="1">
<summary>Answer</summary>

No. `2147483648` cannot be represented as `int`, so per [[lex.icon]] its type is `long` (or `long long` if `long` is only 32 bits). Negating it gives −2147483648 as a `long` (or `long long`), so the corresponding `abs` overload is selected, and the result 2147483648 is representable in that type. Only a genuine `int` value `INT_MIN` triggers UB.
</details>

!!! question "Question 2"
    Is `std::isnan(1)` well-formed? What does it return?

<details markdown="1">
<summary>Answer</summary>

Well-formed. `isnan` has a *floating-point-type* parameter and is not `abs`, so the additional overloads of [cmath.syn] ¶3 treat the integer argument as `double`, equivalent to `isnan(1.0)`, which returns `false`.
</details>
