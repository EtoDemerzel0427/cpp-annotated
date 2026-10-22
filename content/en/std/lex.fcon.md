---
title: Floating-point literals
summary: "How decimal and hexadecimal floating-point literals are written, how the suffix determines the type, and how the value is computed: one of the two adjacent values when it cannot be represented exactly, ill-formed only when out of range, and the range of IEEE types includes all real numbers."
updated: 2026-10-19
---

!!! tldr
    - A decimal floating-point literal must have a decimal point or an exponent: `1.f` is a `float`, `1f` is ill-formed.
    - A hexadecimal floating-point literal `0x1.8p1` must have a `p` exponent; its value is the significand times a power of 2, which can write any binary floating-point value exactly.
    - The type is determined by the suffix alone: no suffix is `double`, `f` is `float`, `l` is `long double`; C++23's `f16`, `f32`, `f64`, `f128` and `bf16` give extended floating-point types and are conditionally-supported.
    - When the value cannot be represented exactly, the adjacent larger or smaller representable value is chosen, in an implementation-defined manner.
    - IEEE floating-point types have infinity, so per the standard their range includes all real numbers; `1e400` is therefore well-formed, with the value +∞ or `DBL_MAX`.

## Two notations

```cpp run title="fcon-forms.cpp" ok
static_assert(1. == 1.0 && .5 == 0.5 && 1e10 == 10000000000.0);
static_assert(0x1.8p1 == 3.0);    // 1.5 × 2¹
static_assert(0x.8p0 == 0.5);     // 0.5 × 2⁰
static_assert(0x1p10 == 1024.0);  // the exponent is decimal 10
static_assert(1e1'0 == 1e10);     // digit separators can be used in the exponent too
int main() {}
```

A **decimal floating-point literal** must have at least one of a decimal point or an exponent part (`e` or `E` followed by an optional sign and decimal digits), so `1.`, `.5` and `1e10` are floating-point literals, while `1` is an integer literal.

A **hexadecimal floating-point literal** begins with `0x`, has a hexadecimal significand, and must be followed by a binary exponent introduced by `p` or `P`. The exponent is always written in decimal and denotes a power of 2: `0x1p10` is 1 × 2¹⁰.

The `p` exponent is required to avoid ambiguity. If it could be omitted, the `f` in `0x1.8f` could be either a hexadecimal digit or the `float` suffix. With `p`, the exponent can only consist of decimal digits, so the suffix cannot be confused with it.

```cpp title="fcon-bad.cpp" error
auto a = 1f;      // error: this is the integer literal 1 with the invalid suffix f
auto b = 0x1.8;   // error: a hexadecimal floating-point literal must have a p exponent
auto c = 1e;      // error: the exponent has no digits
auto d = 1.0lf;   // error: there is no lf suffix
```

The digit separator `'` can be used in both the significand and the exponent. The suffixes are `f`, `l`, and C++23's extended floating-point suffixes; the latter must be all lowercase or all uppercase, such as `bf16` or `BF16`, with no `Bf16`.

## The type (¶1)

¶1 The type of a floating-point literal is determined by its suffix:

| Suffix | Type |
|---|---|
| none | `double` |
| `f`, `F` | `float` |
| `l`, `L` | `long double` |
| `f16`, `F16` | `std::float16_t` {{c++23}} |
| `f32`, `F32` | `std::float32_t` {{c++23}} |
| `f64`, `F64` | `std::float64_t` {{c++23}} |
| `f128`, `F128` | `std::float128_t` {{c++23}} |
| `bf16`, `BF16` | `std::bfloat16_t` {{c++23}} |

```cpp run title="fcon-types.cpp" ok
#include <type_traits>
static_assert(std::is_same_v<decltype(1.0), double>);
static_assert(std::is_same_v<decltype(1.0f), float>);
static_assert(std::is_same_v<decltype(1.0L), long double>);
int main() {}
```

Note 1 explains that the last five suffixes are conditionally-supported: they are available only if the implementation provides the corresponding extended floating-point types ([[basic.extended.fp]]).

`std::float32_t` is not `float`. Even when both have the IEEE binary32 format, `std::float32_t` is still a different type, with different conversion rank rules ([[conv.rank]]). So `1.0f32` and `1.0f` have different types.

!!! impl "Current implementations"
    GCC implements these types and suffixes and provides `<stdfloat>`; which types exist depends on the target platform. Clang 23 + libc++ accepts the `f16` suffix, but the resulting type is Clang's built-in `_Float16`; `f32`, `f64`, `f128` and `bf16` are all rejected; there is no `<stdfloat>`, and macros such as `__STDCPP_FLOAT16_T__` are not defined. Per the standard, this amounts to not supporting these conditionally-supported features, which is allowed.

## The value (¶2–¶3)

### The scaled value (¶2)

¶2 The value of a literal is obtained in two steps. The first computes an exact real number:

- the **significand** is the part of the literal's digits and decimal point before the exponent, interpreted as a real number s in decimal or hexadecimal; digit separators do not affect the value;
- the exponent e is the integer obtained by interpreting the exponent part in decimal, or 0 if there is no exponent part;
- the **scaled value** is s × 10^e for a decimal literal and s × 2^e for a hexadecimal literal.

```cpp run title="fcon-value.cpp" ok
// 0xC.68 = 12 + 6/16 + 8/256 = 12.40625; times 2² gives 49.625
static_assert(49.625 == 0xC.68p+2);
static_assert(1.602'176'565e-19 == 1.602176565e-19);
int main() {}
```

### Mapping to the type (¶3)

¶3 The second step maps the scaled value to a value of the type. If the scaled value is outside the range of representable values of the type, the program is ill-formed. Otherwise, if it can be represented exactly, that is the value; if not, the value is the adjacent larger or smaller value, chosen in an implementation-defined manner.

The standard does not require rounding to nearest. In practice GCC and Clang both convert literals at compile time with IEEE 754 round-to-nearest, ties-to-even, regardless of the run-time rounding mode.

```cpp run title="fcon-round.cpp" impl
// 0.1, 0.2 and 0.3 cannot be represented exactly;
// on an implementation with IEEE double and round-to-nearest, this holds
static_assert(0.1 + 0.2 != 0.3);
int main() {}
```

### The range includes all real numbers

What counts as out of range is specified by [[basic.fundamental#13]]. The range of representable values of a floating-point type is at least from the smallest finite value to the largest finite value; if the type can represent positive infinity, the range extends to all positive real numbers, and likewise on the negative side. IEEE 754 formats all have infinity, so every real number is within range:

- For IEEE `double`, `1e400` is within range, not ill-formed. It cannot be represented exactly, so it takes +∞ or `DBL_MAX`, implementation-defined.
- The value of `1e-400` is 0 or the smallest positive subnormal number, also implementation-defined.
- Only for a floating-point format without infinity is an overly large literal ill-formed.

```cpp run title="fcon-range.cpp" impl
#include <limits>
constexpr double big = 1e400;   // +∞ or DBL_MAX; Clang gives +∞ with a warning
static_assert(big == std::numeric_limits<double>::infinity()
           || big == std::numeric_limits<double>::max());
int main() {}
```

For `1e400`, Clang 23 gives the `-Wliteral-range` warning "magnitude of floating-point constant too large for type 'double'". This is only a warning; the program is well-formed. The standard's Example 2 says the same: assuming `std::float32_t` is supported, the value of `1e1000000000f32` is either the largest finite value or positive infinity.

### Why hexadecimal floating-point literals are needed

Decimal `0.1` is 1/10, which cannot be represented exactly in binary floating point, so the result depends on rounding. The scaled value of a hexadecimal literal is s × 2^e, which can be represented exactly as long as the significand has no more digits than the type's precision.

So it can write specific values exactly: `0x1p-1074` is the smallest positive subnormal `double`, and `0x1.fffffffffffffp+1023` is `DBL_MAX`. Implementations and tests of math libraries often need this notation. C99 already had hexadecimal floating-point literals; C++ added them only in C++17 with [[P0245R1]].

### Double rounding

`float f = 0.1;` first rounds 1/10 to `double`, then converts that `double` to `float` ([[conv.double]]). `0.1f` rounds 1/10 to `float` in one step. Two roundings can cross a tie point, so for a very few values the two results differ. When an exact `float` value is needed, write the `f` suffix directly.

## History and evolution

!!! history
    | Version | Change |
    |---|---|
    | C++98 | Decimal floating-point literals; the `f` and `l` suffixes |
    | C++14 | Digit separators |
    | C++17 | Hexadecimal floating-point literals ([[P0245R1]]); `p+` and `p-` can appear in preprocessing numbers ([[diff.cpp14.lex]]) |
    | C++23 | Extended floating-point types and the suffixes `f16`, `f32`, `f64`, `f128`, `bf16` ([[P1467R9]]) |

## Common misconceptions

!!! pitfall "`1f` is a float"
    It is not valid at all. Write `1.f`, `1.0f` or `1e0f`.

!!! pitfall "`1e400` is ill-formed"
    On IEEE platforms it is well-formed, with the value +∞ or `DBL_MAX`. To express infinity, `std::numeric_limits<double>::infinity()` states the intent more clearly.

!!! pitfall "The `f32` suffix gives `float`"
    `1.0f32` has type `std::float32_t`, a different type from `float`; after `auto x = 1.0f32;`, `x` cannot be bound to a `float&`.

## Questions

!!! question "Question"
    Which of the following are well-formed floating-point literals? What is the type of each?

    ```cpp
    0x1p-1074      1e-400f      0x1.0p      .e1      1.e+5L      0xAp1F
    ```

<details markdown="1">
<summary>Answer</summary>

- `0x1p-1074`: well-formed, `double`, with value 2⁻¹⁰⁷⁴, the smallest positive subnormal IEEE `double`, exactly representable.
- `1e-400f`: well-formed, `float`. The scaled value is within range, between 0 and the smallest positive subnormal number; the value is one of the two, implementation-defined. Clang gives a `-Wliteral-range` warning.
- `0x1.0p`: ill-formed; the binary exponent has no digits.
- `.e1`: not a floating-point literal; `.` must be followed by a digit. It is split into `.` and the identifier `e1`.
- `1.e+5L`: well-formed, `long double`, with value 100000.
- `0xAp1F`: well-formed, `float`, with value 10 × 2¹ = 20. The `F` is not taken as a hexadecimal digit, because the exponent after `p` can only consist of decimal digits.
</details>
