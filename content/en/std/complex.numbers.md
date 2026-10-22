---
title: Complex numbers
summary: "std::complex<T> is defined only for floating-point types; its guarantee of layout compatibility with T[2]; when converting construction is explicit; the main points of the operations, value functions and transcendental functions; UB when a result is mathematically undefined; and C++26's tuple interface and constexpr."
updated: 2026-10-19
---

!!! tldr
    - `complex<T>` is defined only for cv-unqualified floating-point types; `complex<int>` has unspecified effects. The floating-point specializations are trivially copyable literal types.
    - The standard guarantees that a `complex<T>` can be accessed as a `T[2]`, and an array of `complex<T>` as an interleaved array of `T`, for interoperability with C and numeric libraries.
    - Whenever the result of any complex function is mathematically undefined or unrepresentable, the behavior is UB, including division by zero and overflow. This is stricter than built-in floating-point arithmetic.
    - The converting constructor from higher to lower precision is `explicit`; mixed-type operations like `z * 2` do not compile, so write `z * 2.0`.
    - `norm(z)` is the squared magnitude, not the magnitude; since C++26, `get<0>(z)` and structured bindings give references to the real and imaginary parts.

## Basic usage

```cpp run title="complex-basics.cpp" ok
#include <complex>
#include <type_traits>
using namespace std::complex_literals;

static_assert(std::is_trivially_copyable_v<std::complex<double>>);
constexpr std::complex<double> z{3, 4};
// (3+4i)² + (3−4i) = −7+24i + 3−4i
constexpr auto w = z * z + std::conj(z);   // constant-evaluable since C++20
static_assert(w.real() == -4 && w.imag() == 20);
static_assert(std::norm(z) == 25);          // squared magnitude

auto a = 1.0 + 2i;     // complex<double>
auto b = 1.0f + 2if;   // complex<float>
static_assert(std::is_same_v<decltype(b), std::complex<float>>);

int main() {}
```

`complex<T>` stores the real and imaginary parts in Cartesian form, read with `real()` and `imag()` ([complex] ¶1). Arithmetic has been `constexpr` since C++20. The suffixes `i`, `il` and `if` construct `complex<double>`, `complex<long double>` and `complex<float>` with zero real part; they live in the inline namespace `std::literals::complex_literals` ([complex.literals]).

`if` is a keyword yet works as a suffix because `2if` as a whole is a single preprocessing token (a user-defined literal, [[lex.ext]]); the `if` inside it is never treated as a keyword.

## Permitted element types ([complex.numbers.general] ¶2)

¶2 Instantiating the primary `complex` template with a type that is not a cv-unqualified floating-point type has unspecified effects {{unspec}}. Unspecified means an implementation may let it compile: with libc++ in our tests, multiplication of `complex<int>` compiles, but nothing is specified about the results of `abs`, `exp` and the like on integer components; don't use it.

Floating-point types include extended floating-point types ([[basic.extended.fp]]), such as `std::float16_t`. Before C++23 the standard had only three explicit specializations, for `float`, `double` and `long double`; [[P1467R9]] changed this to all floating-point types and rewrote the rules for the converting constructor (see below).

¶2 also specifies that the floating-point specializations are trivially copyable literal types ([[basic.types.general]]): they can be `memcpy`'d and `bit_cast`, and constructed and operated on in constant expressions.

## Undefined result means UB (¶3)

!!! std
    If the result of a function is not mathematically defined or not in the range of representable values for its type, the behavior is undefined.

This rule applies to every function in `<complex>`, including `operator/`. Built-in floating-point arithmetic has an exemption: [[expr.pre#4]] says it is not UB when the result is an infinity or NaN that the type has, so on IEEE floating point `1e308 * 10.0` giving +inf is well-defined. `complex` has no such exemption.

So `complex<double>(1, 0) / complex<double>(0, 0)` is UB in the standard's sense, even though libc++ in our tests actually returns `(inf,nan)`. The specification of `complex` predates C99's Annex G (IEEE semantics for complex numbers), and the standard has never required it to handle infinities and NaNs by IEEE rules. Portable code must check for itself wherever a divisor may be zero or a magnitude may overflow.

## Layout compatibility with T[2] (¶4)

```cpp run title="complex-layout.cpp" ok
#include <complex>
#include <cstdio>
#include <vector>

// a C-style interface taking complex numbers as an interleaved double array
void scale(double* p, std::size_t n, double k) {
  for (std::size_t j = 0; j < 2 * n; ++j) p[j] *= k;
}

int main() {
  std::vector<std::complex<double>> v{{1, 2}, {3, 4}};
  scale(reinterpret_cast<double*>(v.data()), v.size(), 10);
  auto& parts = reinterpret_cast<double(&)[2]>(v[1]);
  parts[1] = -1;                                    // modify the imaginary part
  std::printf("(%g,%g) (%g,%g)\n", v[0].real(), v[0].imag(),
              v[1].real(), v[1].imag());           // (10,20) (30,-1)
}
```

Under the core language this code would fail two tests. One is the type aliasing rule: [[basic.lval]] allows access to an object only through its dynamic type, the corresponding signed/unsigned type, or `char`, `unsigned char` and `std::byte`, and `double` is not among them. The other is that pointer arithmetic may only stay within one array ([[expr.add]]). Besides, the standard does not specify whether the private members of `complex` are `T re, im;` or `T v[2];`.

¶4 has the library directly guarantee that these expressions are defined. If `z` is an lvalue of type `cv complex<T>`:

- ¶4.1 `reinterpret_cast<cv T(&)[2]>(z)` is well-formed;
- ¶4.2 its `[0]` designates the real part of `z`;
- ¶4.3 its `[1]` designates the imaginary part of `z`.

Moreover, if `a` is an expression of type `cv complex<T>*` and `a[i]` is well-defined:

- ¶4.4 `reinterpret_cast<cv T*>(a)[2 * i]` designates the real part of `a[i]`;
- ¶4.5 `reinterpret_cast<cv T*>(a)[2 * i + 1]` designates the imaginary part of `a[i]`.

This is for interoperability with C's `double _Complex` (which C specifies to have the same layout as `double[2]`) and with libraries like FFTW and LAPACK that pass complex numbers as interleaved arrays.

!!! lawyer "The limits of the guarantee"
    ¶4 only guarantees that these expressions designate the real and imaginary parts. It does not say that `complex<T>` is a standard-layout type, nor directly that `sizeof(complex<T>) == 2 * sizeof(T)`, although ¶4.4–4.5 imply there is no padding between adjacent elements. The reverse direction is not covered: `reinterpret_cast` a block of `double`s to `complex<double>*` and call member functions, and there is no `complex` object there, violating [[basic.life]].

## Construction and members ([complex.members], [complex.member.ops])

The constructor `complex(const T& re = T(), const T& im = T())` is not `explicit`, so `complex<double> z = 1.5;` is valid and means 1.5 + 0i.

The converting constructor is `template<class X> constexpr explicit(see below) complex(const complex<X>&)`. ¶3 says the expression inside `explicit` is `false` if and only if the floating-point conversion rank ([[conv.rank]], [[g:floating-point-conversion-rank]]) of `T` is greater than or equal to that of `X`. That is, only the directions that lose no precision (`float → double`, `double → long double`, and between types of equal rank) are implicit.

```cpp title="complex-conversion.cpp" error
#include <complex>

std::complex<float>  f{1.0f, 2.0f};
std::complex<double> d = f;   // OK: double's rank is not lower than float's
std::complex<float>  g{d};    // OK: direct-initialization can use the explicit constructor
std::complex<float>  h = d;   // error: copy-initialization does not consider explicit constructors
```

This differs from built-in types: `float x = 1.0;` is a valid implicit conversion and counts as narrowing only in list-initialization. `complex` writes "rank-lowering conversions must be explicit" into the type itself.

`real()` and `imag()` return values, not references (¶4, ¶6); `real(T)` and `imag(T)` assign (¶5, ¶7). So `&z.real()` takes the address of a prvalue and is ill-formed. Before C++26, the only ways to modify a component in place were these two setters or the array view of ¶4.

Compound assignment ([complex.member.ops]): `+=` and `-=` with a scalar affect only the real part (¶1, ¶3); `*=` and `/=` with a scalar affect the whole complex number (¶5, ¶7). Compound assignments with `complex<X>` are all templates, allowing mixed precision.

## Non-member operations ([complex.ops])

The binary `+ - * /` each have three overloads: `complex op complex`, `complex op T` and `T op complex`, all defined as copying the left operand and then doing the compound assignment (¶2, ¶4–¶6).

!!! pitfall "Mixed-type operations are not promoted automatically"
    The overloads look like `template<class T> complex<T> operator*(const complex<T>&, const T&)`, so `T` must be deduced consistently from both arguments. `std::complex<double> z; z * 2;` fails deduction, because `2` is an `int`, conflicting with `double`; you must write `z * 2.0`. Likewise `1 + 2i` does not compile; write `1.0 + 2i`. `complex<float> * double` does not work either.

Only two `operator==` are declared, `complex == complex` and `complex == T` (¶7–¶8); `!=` and `T == complex` come from C++20 rewritten candidates ([[over.match.oper]]). There are no ordering operators at all.

Stream insertion (¶14) uses the format `(re,im)`. It first writes into an `ostringstream` that copies the format flags, locale and precision, then outputs the whole thing, so `setw` applies to the entire `(re,im)`. The note in ¶15 cautions that in a locale using a comma as the decimal point, `(1,5,2)` is ambiguous; adding `showpoint` resolves it. Stream extraction (¶10) accepts three forms: `u`, `(u)` and `(u,v)`.

## Value functions ([complex.value.ops])

| Function | Returns | Notes |
|---|---|---|
| `real`, `imag` | real part, imaginary part | ¶1–¶2 |
| `abs` | magnitude | ¶3 |
| `arg` | phase angle, i.e. `atan2(imag(x), real(x))` | ¶4 |
| `norm` | squared magnitude | ¶5 |
| `conj` | conjugate | ¶6 |
| `proj` | projection onto the Riemann sphere | ¶7–¶8; same as C's `cproj`: every infinity maps to (+∞, ±0) |
| `polar(rho, theta)` | the complex number with magnitude `rho` and phase angle `theta` | ¶9 precondition: `rho` is non-negative and not NaN, `theta` is finite |

`norm` is often mistaken for the magnitude. Using it to compare sizes while avoiding a square root is right; using it as a length is wrong. `std::polar(-1.0, 0.0)` violates the precondition and is UB; it does not give −1 + 0i.

[cmplx.over] ¶1–¶2 provide additional overloads of `arg`, `norm`, `conj`, `proj`, `imag` and `real` taking real numbers: a floating-point argument of type `T` behaves as if converted to `complex<T>` first, and an integer argument as if converted to `complex<double>` first. So `std::real(3)` returns the `double` 3.0, and `std::conj(2.5f)` returns a `complex<float>`. `abs` is not among them; `std::abs(3)` is the integer version from `<cstdlib>`.

## Transcendental functions ([complex.transcendentals])

The *Remarks* of `acos`, `asin`, `atan`, `acosh`, `asinh` and `atanh` all say they behave the same as C's `cacos` and friends (the even paragraphs of ¶2–¶12); the notes on `log` and `sqrt` say the intent is the same as C's `clog` and `csqrt`. Branch cuts and the handling of special values are thus inherited from C's Annex G.

- ¶16–¶17 `log`: `imag(log(x))` is always in [−π, π], with the branch cut along the negative real axis. Both ends of the interval are closed because of signed zero: the imaginary part of `log(complex(-1, +0.0))` is +π, and that of `log(complex(-1, -0.0))` is −π.
- ¶18 `log10` is defined as `log(x) / log(10)`.
- ¶20 `pow` is defined as `exp(y * log(x))`; the value of `pow(0, 0)` is implementation-defined {{impl}}; libc++ in our tests gives `(nan,nan)`.
- ¶24–¶25 The result of `sqrt` is in the right half-plane, with the branch cut along the negative real axis, again with the sign of zero distinguishing the two sides.

```cpp run title="branch-cut.cpp" ok
#include <complex>
#include <cstdio>

int main() {
  std::complex<double> above(-1.0, +0.0), below(-1.0, -0.0);
  auto a = std::log(above), b = std::log(below);
  std::printf("%g %g\n", a.imag(), b.imag());   // 3.14159 -3.14159
  auto s = std::sqrt(above), t = std::sqrt(below);
  std::printf("%g %g\n", s.imag(), t.imag());   // 1 -1
}
```

!!! impl "libc++'s sqrt"
    With libc++ in our tests, the real part of `std::sqrt(complex<double>(-1, 0))` is `6.12323e-17` rather than 0. It computes `polar(sqrt(abs(x)), arg(x) / 2)`, and `cos(π/2)` is not exactly zero in floating point. "Same as `csqrt`" is only the intent stated in a note, with no normative force, so this is not a violation, but it shows you should not compare the results of complex functions exactly.

[cmplx.over] ¶3 provides mixed-type overloads for `pow`: when one argument is `complex<T1>` and the other is `T2` or `complex<T2>`, both are converted to `complex<common_type_t<T1, T3>>`, where `T3` is `double` if `T2` is an integer type and `T2` otherwise. If `common_type_t<T1, T3>` is ill-formed, the program is ill-formed.

```cpp run title="pow-promotion.cpp" ok
#include <complex>
#include <type_traits>

std::complex<float> z{1, 2};
// integer arguments take part in promotion as double
static_assert(std::is_same_v<decltype(std::pow(z, 2)),
                             std::complex<double>>);
static_assert(std::is_same_v<decltype(std::pow(z, 2.0f)),
                             std::complex<float>>);
static_assert(std::is_same_v<decltype(std::real(1)), double>);

int main() {}
```

So the result of `std::pow(complex<float>, 2)` is `complex<double>`. To stay at `float` precision, write `pow(z, 2.0f)`, or simply `z * z`.

In the current draft's synopsis, all value functions and transcendental functions are `constexpr`, an extension from [[P1383R2]] {{c++26}}. libc++ in our tests has not caught up: `norm`, `conj` and the four arithmetic operations can be constant-evaluated (as they could since C++20), but `abs`, `arg` and `exp` cannot.

## Tuple interface ([complex.tuple]) {{c++26}}

```cpp run title="complex-tuple.cpp" ok
#include <complex>
#include <tuple>

int main() {
  std::complex<double> z{1, 2};
  auto& [re, im] = z;     // bind to the real and imaginary parts
  im = -im;               // conjugate in place
  std::get<0>(z) *= 3;
  return z == std::complex<double>(3, -2) ? 0 : 1;
}
```

[[P2819R2]] added the tuple protocol to `complex`. ¶1 `tuple_size<complex<T>>` is 2 and `tuple_element<I, complex<T>>::type` is `T`, requiring `I < 2`. ¶2–¶3 `get<I>(z)` has four overloads returning a reference to the real part (`I == 0`) or the imaginary part, and is `noexcept`.

So `complex` satisfies [[tuple.like]] and can be used with structured bindings ([[dcl.struct.bind]]), and `get<0>(z) = 5;` becomes a valid way to modify the real part in place. Previously only the `reinterpret_cast` of ¶4 could do that; `get` can be seen as the type-safe counterpart of that layout guarantee.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[complex.numbers.general] ¶1: the header `<complex>` defines a class template and many functions for manipulating complex numbers.

[complex.member.ops] ¶9–¶18: assignment from `complex<X>`, and the four compound assignments with `complex<X>`, each returning `*this`.

[complex.ops]: unary `+` returns `complex<T>(lhs)`, and unary `-` returns `complex<T>(-lhs.real(), -lhs.imag())` (¶1, ¶3). On bad input, stream extraction calls `is.setstate(ios_base::failbit)` (¶11), and the whole extraction is performed as a series of simpler extractions (¶13).

[complex.literals] ¶2–¶4: each suffix has two overloads, `long double` and `unsigned long long`, so both `2i` and `2.5i` work. Literal suffixes not beginning with an underscore are reserved for the standard library ([[usrlit.suffix]]).

</details>

## Questions

!!! question "Question 1"
    Does `std::complex<double> z; double* p = &z.real();` compile? In C++23 and C++26, how do you validly get a pointer to the real part?

<details markdown="1">
<summary>Answer</summary>

No. `real()` returns a `double` value, and `&z.real()` takes the address of a prvalue, which is ill-formed.

C++23: use the guarantee in [complex.numbers.general] ¶4.2 and write `&reinterpret_cast<double(&)[2]>(z)[0]`.

C++26: write `&std::get<0>(z)`; [complex.tuple] ¶3 says it returns a reference to the real part.
</details>

!!! question "Question 2"
    Assume `double` is IEEE binary64. What is the behavior of `std::complex<double>(1, 0) / std::complex<double>(0, 0)`? Of `1.0 / 0.0`? Of `std::complex<double>(1e308, 0) * 10.0`?

<details markdown="1">
<summary>Answer</summary>

The first: the result is mathematically undefined, so per [complex.numbers.general] ¶3 it is UB.

The second: built-in division; [[expr.mul]] says it is UB when the second operand is zero, and the note in [[expr.pre#4]] also points out that for types conforming to ISO/IEC 60559, division by zero is the only UB case of arithmetic expressions.

The third: the result is outside the representable range of `double`, so per ¶3 it is UB. If the same overflow happened in the built-in operation `1e308 * 10.0`, the result would be +inf, which is well-defined.
</details>
