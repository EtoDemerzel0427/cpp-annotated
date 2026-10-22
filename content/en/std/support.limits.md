---
title: Implementation properties
summary: "Querying properties of the implementation at compile time: the exact meaning of each numeric_limits member, the C macros in <climits> and <cfloat>, and the library feature-test macros in <version>."
updated: 2026-10-19
---

!!! tldr
    - For floating-point types, `numeric_limits<T>::min()` is the smallest positive normalized value, not the most negative value; for the most negative finite value use `lowest()`.
    - For a type without a specialization, `numeric_limits` doesn't give an error; every member is 0 or `false`. Generic code should check `is_specialized` first.
    - `digits10` is the number of decimal digits that survive being written in and read back out; `max_digits10` is the number of digits needed for a binary value to survive being printed and read back.
    - In `<climits>`, the type of `SHRT_MAX` and `UCHAR_MAX` is the promoted `int`; these macros can be used in `#if`, which is their main advantage over `numeric_limits`.
    - The `__cpp_lib_*` macros are defined by the library; include `<version>` or the corresponding header before checking them, and compare with `>=`.

[[basic.fundamental]] leaves many properties to the implementation: how wide `int` is, whether `char` is signed, what format `long double` uses. ¶1 ([support.limits.general]) `<limits>`, `<climits>` and `<cfloat>` let programs query these properties at compile time; `<version>` reports which features the standard library itself implements.

## `min()` isn't the minimum

```cpp run title="min-vs-lowest.cpp" ok
#include <algorithm>
#include <limits>
#include <vector>

double max_of(const std::vector<double>& v) {
    // wrong: min() is a tiny positive number
    // double m = std::numeric_limits<double>::min();
    double m = std::numeric_limits<double>::lowest();
    for (double x : v) m = std::max(m, x);
    return m;
}

int main() { return max_of({-3.0, -1.5, -7.0}) == -1.5 ? 0 : 1; }
```

With `min()` as the initial value, an all-negative input gives a positive number around 2.2e-308. Integers and floating-point types have inconsistent semantics here:

| Member | Integer types | Floating-point types |
|---|---|---|
| `min()` | The minimum value, such as `INT_MIN` | The smallest positive normalized value, such as `DBL_MIN` |
| `max()` | The maximum value | The largest finite value |
| `lowest()` | Same as `min()` | The most negative finite value, usually `-max()` |

[numeric.limits.members] ¶2–¶3 say `min()` is the minimum finite value, but for floating-point types with subnormal numbers (values closer to 0 than the smallest normalized number) it returns the minimum positive normalized value. Footnote 150 says it is equivalent to C's `FLT_MIN` and `DBL_MIN`; the inconsistency is inherited from C.

`lowest()` in ¶7 was added in C++11: a finite value x such that there is no other finite value y with y < x. Footnote 152 explains why it isn't simply written as `-max()`: not every floating-point representation has a most negative value exactly equal to the negated maximum.

## General rules of `numeric_limits` ([numeric.limits.general])

The primary template provides a default value for each member:

```cpp
template<class T> class numeric_limits {
public:
  static constexpr bool is_specialized = false;
  static constexpr T min() noexcept { return T(); }
  static constexpr T max() noexcept { return T(); }
  static constexpr int  digits = 0;
  // ... the other members are likewise 0, false or T()
};
```

¶3 The data members and member function return values of the primary template are value-initialized. Note 1 points out that this means querying `numeric_limits` for a type without a specialization gives no error, just 0 or `false`.

```cpp run title="limits-primary.cpp" ok
#include <cstddef>
#include <limits>

template<class T>
constexpr T saturating_max() {
    static_assert(std::numeric_limits<T>::is_specialized,
                  "need numeric_limits<T>");
    return std::numeric_limits<T>::max();
}

static_assert(!std::numeric_limits<std::byte>::is_specialized);
static_assert(std::numeric_limits<std::byte>::max() == std::byte{0});
static_assert(std::numeric_limits<const volatile int>::max()
              == std::numeric_limits<int>::max());
// constexpr auto b = saturating_max<std::byte>();  // error: static_assert fails

int main() { return saturating_max<unsigned char>() == 255 ? 0 : 1; }
```

`std::byte` is an enumeration, not an arithmetic type, so `numeric_limits<std::byte>::max()` quietly returns `byte{0}`. Other rules:

- ¶2 All `static constexpr` members shall be usable in constant expressions.
- ¶4 Every arithmetic type shall have a specialization with `is_specialized` `true`. This includes `bool`, as well as extended integer types and extended floating-point types ([[basic.extended.fp]]).
- ¶5 The specialization for *cv* `T` has the same member values as `T`; the third `static_assert` in the example verifies this.
- ¶6 Non-arithmetic standard types, such as `complex<T>`, shall not have specializations.

A program can specialize `numeric_limits` for its own types: [[namespace.std]] allows specializations of standard library class templates that depend on program-defined types. Big-integer and fixed-point libraries usually do this.

## Meaning of each member ([numeric.limits.members])

¶1 Each member function in this subclause is signal-safe ([[support.signal]]) and can be called in a signal handler.

Each member notes the conditions under which it is meaningful; for example, `epsilon()` is meaningful only for floating-point types. [numeric.special] ¶1 says every specialization must provide every member, with values that aren't meaningful set to 0 or `false`, so `epsilon()` for an integer type is 0.

### Precision: `digits`, `digits10`, `max_digits10` (¶9–¶15)

- `digits`: the number of `radix` digits that can be represented without change. For integer types it is the number of non-sign bits: 31 for `int`, 32 for `unsigned`, 1 for `bool`. For floating-point types it is the number of digits in the significand, including the implicit leading bit: 24 for `float`, 53 for `double`.
- `digits10`: the number of decimal digits that can be represented without change; any decimal number with that many digits can be stored and retrieved unchanged. For `int` it is 9: any 9-digit integer fits, but not every 10-digit integer does. For `double` it is 15.
- `max_digits10`: the number of decimal digits required to ensure that values which differ are always printed differently; meaningful only for floating-point types (9 for `float`, 17 for `double`). This many digits are needed to serialize a floating-point number to text and parse it back to exactly the same value.

```cpp run title="digits.cpp" ok
#include <limits>

using L = std::numeric_limits<double>;
static_assert(L::digits == 53 && L::digits10 == 15
              && L::max_digits10 == 17);
static_assert(std::numeric_limits<int>::digits == 31);
static_assert(std::numeric_limits<unsigned>::digits == 32);
static_assert(std::numeric_limits<bool>::digits == 1);
static_assert(std::numeric_limits<int>::digits10 == 9);

int main() {}
```

This example assumes `double` is IEEE 754 binary64 and `int` is 32 bits. That is so on all mainstream platforms, but the standard doesn't guarantee it.

### Classification: `is_signed`, `is_integer`, `is_exact`, `radix` (¶16–¶24)

- `is_signed` and `is_integer` mean what they say. `numeric_limits<char>::is_signed` answers the implementation-defined question of whether `char` is signed: `true` on x86-64 Linux and Apple platforms, `false` on AArch64 Linux.
- `is_exact`: uses exact representations. ¶20 points out that all integer types are exact, but not all exact types are integers, for example rational and fixed-point representations.
- `radix`: for floating-point types, the base of the exponent, usually 2; for integer types, the base of the representation.

### Floating-point characteristics: `epsilon` through `max_exponent10` (¶25–¶35)

- `epsilon()`: the difference between 1 and the least representable value greater than 1 (2⁻⁵² for `double`). It is only the spacing between adjacent values near 1; near 1e10, the difference between adjacent `double`s is far larger than `epsilon()`.
- `round_error()`: a measure of the maximum rounding error. Usually 0.5 with round-to-nearest.
- `min_exponent`, `max_exponent`: the minimum and maximum integers e such that radix raised to the power e − 1 is a normalized and a finite value, respectively. For `double` they are −1021 and 1024, while the exponent range of normalized numbers is [−1022, 1023]. The minus one is for consistency with C's `DBL_MIN_EXP` and `DBL_MAX_EXP`, since C writes the significand in the form 0.1xxx.
- `min_exponent10`, `max_exponent10`: the decimal counterparts.

### Infinity and NaN (¶36–¶52)

- `has_infinity`, `has_quiet_NaN`, `has_signaling_NaN`: whether the type has these special values. When `is_iec559` is `true`, they must all be `true`.
- `infinity()`, `quiet_NaN()`, `signaling_NaN()`: the corresponding values, meaningful when the corresponding `has_*` is `true`.
- `denorm_min()`: the minimum positive subnormal value; if the type doesn't support subnormal numbers, the minimum positive normalized value.

!!! note "Where did `has_denorm` go?"
    Before C++23 there were also two members `has_denorm` and `has_denorm_loss`. [[P2614R2]] deprecated them in C++23, and they now live in Annex [[depr.numeric.limits.has.denorm]]. Whether subnormal numbers are supported can often be switched at run time (for example, the FTZ/DAZ modes on x86), which a compile-time constant can't describe faithfully.

### IEEE conformance and boundedness (¶53–¶56)

- `is_iec559`: `true` if and only if the type adheres to ISO/IEC 60559 (i.e. IEEE 754). Note 1 points out that `std::float16_t`, `float32_t`, `float64_t` and `float128_t`, if they exist, are all `true`.
- `is_bounded`: the set of representable values is finite. Note 2 points out that all fundamental types are bounded; only arbitrary-precision types would be `false`.

!!! lawyer "`is_iec559` doesn't guarantee the optimizer respects IEEE semantics"
    `is_iec559` only says the type's representation and arithmetic follow IEEE 754. When compiling with `-ffast-math`, the compiler assumes there are no NaNs or infinities, and `std::isnan(x)` may be folded straight to `false`, while `numeric_limits<double>::is_iec559` is still `true`. Such compiler options are outside the scope of the standard.

### Overflow and traps: `is_modulo`, `traps`, `tinyness_before` (¶57–¶63)

¶57 A type is a modulo type if, when the true result of `+`, `-` or `*` falls outside `[min(), max()]`, the value returned differs from the true value by an integer multiple of `max() - min() + 1`, i.e. it wraps around on overflow. `is_modulo` is `true` for unsigned types, because [[basic.fundamental]] specifies that unsigned arithmetic is performed modulo 2ⁿ.

¶58 Example 1 explains that `is_modulo` is `false` for signed integer types, unless the implementation, as an extension, defines signed overflow to wrap. Signed overflow is undefined behavior in the core language ([[expr.pre]]), and this simply reflects that.

¶60 `traps`: there exists a value at the start of the program that would trap (trigger a hardware exception) if used in arithmetic. The typical example for integer types is division by zero. ¶62 `tinyness_before`: tininess is detected before rounding. IEEE 754 allows either point of detection, depending on the hardware.

!!! impl "The values of `traps` and `tinyness_before` in libc++"
    libc++ sets `traps` for integer types according to the target: on x86 and WebAssembly it is `true` for types not subject to integral promotion (`int` and wider), because integer division by zero raises SIGFPE on those platforms; on AArch64 and others it is `false`, since integer division by zero there gives 0. For floating-point types, `tinyness_before` is `true` on ARM and AArch64 and `false` elsewhere. So on Apple Silicon `numeric_limits<int>::traps` is `false` and `numeric_limits<double>::tinyness_before` is `true`, and on x86-64 Linux it is exactly the other way round.

### `round_style` (¶64–¶65)

The rounding style of the type, of the enumeration type `float_round_style` ([round.style]), corresponding to C's `FLT_ROUNDS` (footnote 164). Specializations for integer types shall be `round_toward_zero`, because integer division truncates toward zero ([[expr.mul]]).

| Enumerator | Value | Meaning |
|---|---|---|
| `round_indeterminate` | −1 | Indeterminable |
| `round_toward_zero` | 0 | Rounds toward zero |
| `round_to_nearest` | 1 | Rounds to the nearest representable value |
| `round_toward_infinity` | 2 | Rounds toward positive infinity |
| `round_toward_neg_infinity` | 3 | Rounds toward negative infinity |

`round_style` is a compile-time constant describing the default rounding style. It doesn't change when the program changes the rounding direction at run time with `fesetround` from `<cfenv>`.

## Specializations specified by the standard ([numeric.special])

¶2 gives an example specialization for `float`, with for instance `digits = 24` and `epsilon() = 1.19209290E-07F`. This is only an example, not a requirement.

¶3 is normative: `numeric_limits<bool>` shall be provided exactly as defined there. It has `digits = 1`, `digits10 = 0` (one binary digit can't represent even one decimal digit) and `is_modulo = false`. `bool` doesn't wrap: `true + true` is first promoted to `int`, giving 2, which converted back to `bool` is still `true`.

!!! impl "`__int128` has a specialization too"
    libc++ provides `numeric_limits` specializations for `__int128` and `unsigned __int128`. GCC and Clang don't document `__int128` as an extended integer type in the standard's sense, so this specialization is an extension. A past obstacle was that `intmax_t` had to be able to represent the values of all extended integer types, so adding a 128-bit type would mean widening `intmax_t` and breaking the ABI; the current draft has relaxed this requirement ([[support.arith.types]]).

## `<climits>` and `<cfloat>` ([climits.syn], [cfloat.syn])

Both headers must be provided by freestanding implementations too, and the macros are defined as in C's `<limits.h>` and `<float.h>`. The only exception is that `<climits>` doesn't define C23's `BITINT_MAXWIDTH`, since C++ has no `_BitInt`.

[climits.syn] Note 1 points out that, except for the `*_WIDTH` macros, `CHAR_BIT` and `MB_LEN_MAX`, a macro describing an integer type `T` has the promoted type of `T` ([[conv.prom]]). So the type of both `SHRT_MAX` and `UCHAR_MAX` is `int`:

```cpp run title="climits-type.cpp" ok
#include <climits>
#include <type_traits>

static_assert(std::is_same_v<decltype(SHRT_MAX), int>);
static_assert(std::is_same_v<decltype(UCHAR_MAX), int>);
static_assert(std::is_same_v<decltype(UINT_MAX), unsigned>);
static_assert(std::is_same_v<decltype(LONG_MAX), long>);

int main() {}
```

!!! pitfall "Why `INT_MIN` isn't written as `-2147483648`"
    With a 32-bit `int`, `-2147483648` isn't a literal but the negation of the literal `2147483648`. `2147483648` is out of range for `int`, so by [[lex.icon]] its type is `long` or `long long`, and so the whole expression doesn't have type `int`. Implementations usually define `INT_MIN` as `(-INT_MAX - 1)`.

C23 added width macros such as `INT_WIDTH` and `LONG_WIDTH` to `<climits>`, and `FLT_TRUE_MIN` (i.e. `denorm_min()`), `INFINITY`, `NAN` and others to `<cfloat>`. These macros can be used in preprocessor conditions such as `#if INT_MAX > 0x7FFF`; in templates and `constexpr` code, `numeric_limits` is more convenient.

| `numeric_limits` member | Corresponding C macros |
|---|---|
| `min()`, `max()` | `INT_MIN`, `INT_MAX`, `DBL_MIN`, `DBL_MAX` and so on |
| `digits` (floating-point) | `FLT_MANT_DIG`, `DBL_MANT_DIG`, `LDBL_MANT_DIG` |
| `digits10` (floating-point) | `FLT_DIG`, `DBL_DIG`, `LDBL_DIG` |
| `max_digits10` | `FLT_DECIMAL_DIG`, `DBL_DECIMAL_DIG` |
| `radix` | `FLT_RADIX` |
| `epsilon()` | `FLT_EPSILON`, `DBL_EPSILON`, `LDBL_EPSILON` |
| `min_exponent`, `max_exponent` | `DBL_MIN_EXP`, `DBL_MAX_EXP` and so on |
| `min_exponent10`, `max_exponent10` | `DBL_MIN_10_EXP`, `DBL_MAX_10_EXP` and so on |
| `round_style` | `FLT_ROUNDS` |

## Library feature-test macros ([version.syn])

¶1 `<version>` supplies information about the standard library implementation; its bulk is more than three hundred `__cpp_lib_*` macros. ¶2 Besides being defined in `<version>`, each macro is also defined in the headers listed in its synopsis comment; for example, `__cpp_lib_three_way_comparison` is also defined in `<compare>`.

The value of each macro is an integer of the form `yyyymmL`, roughly the year and month the feature entered the working draft. Note 1 reminds us that a future standard may increase the value when a feature is extended, so compare with `>=`:

```cpp run title="feature-test.cpp" ok
#include <version>

#if defined(__cpp_lib_three_way_comparison) \
    && __cpp_lib_three_way_comparison >= 201907L
#  include <compare>
constexpr bool has_spaceship_lib = true;
#else
constexpr bool has_spaceship_lib = false;
#endif

int main() { return has_spaceship_lib ? 0 : 1; }
```

Language feature-test macros (`__cpp_concepts` and so on) are predefined by the compiler ([[cpp.predefined]]) and need no header. `__cpp_lib_*` macros are defined by the library, so you must include `<version>` or the corresponding header first, otherwise the check always finds them undefined.

A few macros have special rules:

- ¶3 A set of `__cpp_lib_hardened_*` macros (such as `__cpp_lib_hardened_vector`) are defined only in a hardened implementation ([[g:hardened-implementation]]). ¶7 recommends that non-hardened implementations not define them.
- ¶4 `__cpp_lib_freestanding_operator_new` is `202306L` if all the default versions of the replaceable global allocation functions meet the requirements of a hosted implementation, and 0 otherwise ([[new.delete]]). This lets a freestanding implementation provide an `operator new` that always fails.
- ¶5 `__cpp_lib_replaceable_contract_violation_handler` is `202603L` if the contract-violation handler is replaceable, and 0 otherwise ([[basic.contract.handler]]).
- ¶6 It is recommended that freestanding implementations define a macro only if the corresponding facility is fully provided.

## Questions

!!! question "Questions"
    1. What is `std::numeric_limits<long double>::digits` on Apple Silicon? On x86-64 Linux?
    2. Does `std::numeric_limits<int&>::max()` compile?
    3. Someone writes `if (std::abs(a - b) < std::numeric_limits<double>::epsilon())` to test whether two floating-point numbers are equal. What is wrong with it?

<details markdown="1">
<summary>Answer</summary>

1. On Apple Silicon, `long double` is the same as `double`, and `digits` is 53; on x86-64 Linux, `long double` is the x87 80-bit extended precision format, and `digits` is 64. [[basic.fundamental]] only requires `long double` to have at least the precision of `double`; the exact format is up to the implementation.
2. No. There is no specialization for `int&`, so the primary template is used, and its `max()` is written `return T();`, which can't value-initialize a reference type. Member functions of a class template are instantiated only when used, so merely writing `numeric_limits<int&>` is fine; calling `max()` is the error. Clang 23 reports "reference to type 'int' requires an initializer".
3. `epsilon()` is the spacing between adjacent `double`s near 1 (¶25). For numbers much larger than 1, the difference between adjacent values is far larger than `epsilon()`, so the condition degenerates into exact equality; for numbers much smaller than 1, it is far too lenient. The tolerance should scale with the magnitude of the values, or compare by ULP distance instead.
</details>
