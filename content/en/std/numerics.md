---
title: Numerics library
summary: "A guide to Clause 29: where complex numbers, random numbers, valarray, <cmath>, mathematical constants, linear algebra and std::simd live, the recurring kinds of rule consequences in this clause, and the state of libc++ in our tests."
updated: 2026-10-19
---

!!! tldr
    - Clause 29 collects types and functions built around mathematical objects: complex numbers, random numbers, `valarray`, `<cmath>`, mathematical constants, `<linalg>` and `<simd>`. `<numeric>` algorithms such as `accumulate`, `reduce` and `gcd` are in the algorithms clause, not here.
    - When the result of a `<complex>` function is mathematically undefined or unrepresentable, the behavior is UB; `<cmath>` uses C's error reporting mechanism instead, which is not UB.
    - The algorithms of random number distributions are implementation-defined, so the same seed can give different sequences on different standard libraries; the algorithms of engines are fully specified.
    - `<random>` expresses requirements through template parameter names: parameters named `IntType`, `RealType` and so on accept only types in specified sets, otherwise the program is ill-formed.
    - libc++ in our tests does not yet have `<linalg>`, `<simd>` or `philox_engine`, and the `constexpr` extensions to `<cmath>` are not implemented.

## Map of the clause ([numerics.general])

¶1–¶2 This clause describes components for **seminumerical** operations, that is, types and functions about mathematical objects themselves, not general algorithms over sequences. Table 125 lists the subclauses:

| Subclause | Contents | Header | Notes on this site |
|---|---|---|---|
| [numeric.requirements] | requirements on the element types of `complex` and `valarray` | — | [[numeric.requirements]] |
| [cfenv] | the floating-point environment: exception flags, rounding modes | `<cfenv>` | [[cfenv]] |
| [complex.numbers] | `complex<T>`, transcendental functions, literal suffixes | `<complex>` | [[complex.numbers]] |
| [rand] | engines, engine adaptors, distributions, `random_device`, `seed_seq` | `<random>` | [[rand]] |
| [numarray] | `valarray` and the four slice proxies | `<valarray>` | [[numarray]] |
| [c.math] | `<cmath>` functions, integer `abs`, `lerp`, mathematical special functions | `<cmath>`, `<cstdlib>` | [[c.math]] |
| [numbers] | mathematical constants such as `std::numbers::pi` | `<numbers>` | [[numbers]] |
| [linalg] | BLAS-style algorithms based on `mdspan` {{c++26}} | `<linalg>` | [[linalg]] |
| [simd] | data-parallel types `basic_vec`, `basic_mask` {{c++26}} | `<simd>` | [[simd]] |

After the table there is one more subclause, [[numerics.c]]: C23's `<stdckdint.h>`, with the overflow-checked `ckd_add`, `ckd_sub` and `ckd_mul`.

The introduction in ¶2 still mentions generalized numeric algorithms, but `accumulate`, `reduce`, `inclusive_scan`, `gcd`, `midpoint`, saturation arithmetic and so on long ago moved to [[numeric.ops]] and [[numeric.sat]] in the algorithms clause. Look for them there.

Some facilities are often mistakenly thought to be in this clause:

| Facility | Actual location |
|---|---|
| `numeric_limits`, `<cfloat>`, `<climits>` | the language support library, [[support.limits]] |
| `<stdfloat>` aliases such as `float16_t` | [[support.arith.types]]; the types themselves are in [[basic.extended.fp]] |
| `<bit>` (`popcount`, `bit_cast` and so on) | the utilities library, [[bit]] |
| `to_chars`, `from_chars` | text processing, [[charconv]] |
| `shuffle`, `sample`, `ranges::generate_random` | the algorithms clause, [[alg.random.shuffle]], [[alg.random.sample]], [[alg.rand.generate]] |
| `mdspan` itself | the containers clause, [[views.multidim]] |

## Recurring kinds of rule consequences in this clause

The numerics library borrows heavily from mathematical notation and often specifies a consequence directly for mathematical failure. The following patterns recur across the pages.

### Results undefined or unrepresentable

```cpp
auto z = std::log(std::complex<double>(0, 0));
// <complex>: ln 0 is mathematically undefined; UB per ¶3
double d = std::log(0.0);
// <cmath>: pole error, returns -HUGE_VAL
// and reports via math_errhandling; not UB
```

[complex.numbers.general] ¶3 in [[complex.numbers]] says that if the result of a complex function is mathematically undefined or outside the representable range of its type, the behavior is undefined. This is stricter than the core language. Per [[expr.pre#4]], a built-in arithmetic expression is UB only when the mathematical result is neither representable nor an infinity or NaN the type has, so for IEEE floating-point types only division by zero remains UB among the built-in operations. `<complex>` has no such exemption. libc++ in our tests actually follows the C Annex G conventions and returns `(-inf, 0)` for the example above, but the standard does not guarantee it.

`<cmath>` keeps C's `math_errhandling` mechanism for reporting domain and range errors (see [[c.math]]), which is not UB. But integer `std::abs(INT_MIN)` is still UB, because that is how C specifies `abs`.

### Implementation-defined algorithms

```cpp
std::mt19937 eng(42);
std::uniform_int_distribution<int> d(1, 6);
int x = d(eng);   // different standard libraries may give different x
```

[rand.dist.general] ¶3 in [[rand.dist]] says that how each distribution produces the target distribution from uniform random bits is implementation-defined. So with the same engine and the same seed, `uniform_int_distribution` can give different results on libc++, libstdc++ and the MSVC STL.

Engines are the opposite: the algorithm of `mt19937` is fully specified, and [[rand.predef]] even specifies the value that the 10000th invocation of a default-constructed engine must produce. To reproduce a random sequence across platforms, you can rely only on the engine's output and must write the transformation from bits to the distribution yourself. Which engine `default_random_engine` is, and where `random_device` gets its entropy, are also implementation-defined.

### Template parameter names carry requirements

[rand.req.genl] ¶1 says that template parameters in `<random>` named `RealType`, `IntType`, `UIntType`, `URBG`, `Sseq` and `Engine` automatically carry corresponding requirements. For the first three, an argument outside the allowed set of types makes the program ill-formed. For example, `IntType` accepts only the standard integer types, extended integer types with width between that of `char` and `long long`, and other integer types the implementation chooses to include. `char` and `bool` are not standard integer types and can be used only if the implementation includes them; libc++ in our tests rejects `uniform_int_distribution<char>` with a `static_assert`.

[[linalg]] uses the same technique ([linalg.algs.reqs]): parameters named `Triangle`, `DiagonalStorage` and `ExecutionPolicy` each have constraints. When reading these function signatures, the parameter names themselves are part of the requirements.

### Mandates, Constraints and Preconditions

As in other library clauses, when *Mandates* are not met the program is ill-formed and must be diagnosed; when *Constraints* are not met the overload drops out of overload resolution with no diagnostic; when *Preconditions* are not met the behavior is UB ([[structure.specifications]]). A few spots in this clause deserve attention:

- instantiating a primary template like `std::numbers::pi_v<int>` makes the program ill-formed ([math.constants] ¶3);
- instantiating `complex<int>` has unspecified effects: it is not guaranteed to work, and no diagnostic is required ([[numeric.requirements]]);
- the bounds check of `valarray::operator[]` is a hardened precondition {{c++26}}; under a hardened implementation, out-of-bounds access is checked and terminates ([[g:hardened-precondition]]);
- `<linalg>` uses *Mandates* to check that static extents are compatible and *Preconditions* to constrain dynamic extents.

## Implementation status (Clang 23 + libc++)

| Facility | Status |
|---|---|
| basic `<complex>` functionality, literals | implemented; C++26 structured binding support also implemented |
| C++23/26 `constexpr` extensions to `<complex>` and `<cmath>` | not implemented: `std::floor` and others are rejected in constant expressions |
| the classic engines and distributions of `<random>` | implemented; `default_random_engine` is `minstd_rand` |
| `philox_engine`, `ranges::generate_random` {{c++26}} | not implemented |
| the new specification of `generate_canonical` | not adopted; still the old algorithm, which can return 1.0 (see [[rand.util]]) |
| `<valarray>` | implemented, using expression templates |
| mathematical special functions | only `hermite`; no `riemann_zeta`, `cyl_bessel_j` and so on |
| `<linalg>`, `<simd>` {{c++26}} | neither header exists |
| `<stdckdint.h>` | provided by Clang's own C header; the `ckd_*` are macros, not the function templates the standard requires |
