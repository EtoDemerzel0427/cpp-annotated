---
title: Conversion ranks
summary: "Integer conversion rank, floating-point conversion rank and subrank: an ordering of the arithmetic types used by integral promotion, the usual arithmetic conversions, implicit floating-point conversions, narrowing and overload resolution."
updated: 2026-10-19
---

!!! tldr
    - Ranks produce no behavior by themselves. They are an ordering used by other rules: integral promotion, the usual arithmetic conversions, implicit floating-point conversions, narrowing and overload resolution all decide by rank.
    - [[g:integer-conversion-rank|Integer conversion rank]] is not width. `long` and `long long` are both 64 bits on LP64, but `long long` has the higher rank, so `1LL + 1UL` has type `unsigned long long`.
    - An unsigned type has the same rank as its corresponding signed type; character types have the rank of their underlying types; `bool` is lowest.
    - [[g:floating-point-conversion-rank|Floating-point conversion rank]] is a partial order: a type has a higher rank only if its set of values is a proper superset of the other's. `std::bfloat16_t` and `std::float16_t` have unordered ranks, and mixed arithmetic between them is ill-formed.
    - Floating-point types of equal rank are further ordered by [[g:floating-point-conversion-subrank|subrank]], with `std::floatN_t` preferred over a standard type of equal rank, so `1.0f + 1.0f32` has type `std::float32_t`.

## Why ranks are needed

```cpp run ok
#include <type_traits>
// LP64 (64-bit Linux, macOS)
static_assert(sizeof(long) == 8 && sizeof(long long) == 8);
static_assert(std::is_same_v<decltype(1LL + 1UL), unsigned long long>);
int main() {}
```

Adding two 64-bit operands yields a third type. The usual arithmetic conversions ([[expr.arith.conv]]), which decide the result type, need to know which type is "bigger", but this can't be decided by `sizeof`: there can be more than one type of the same width, and floating-point types may not even be comparable (one has more range, the other more precision). The order this subclause gives the arithmetic types consists of the **integer conversion rank**, the **floating-point conversion rank** and the **floating-point conversion subrank**.

Rules that use ranks:

| Rule | How it uses rank |
|---|---|
| [[conv.prom]] integral promotion | integer types of rank lower than `int` are promoted to `int` or `unsigned int` |
| [[expr.arith.conv]] usual arithmetic conversions | both operands are converted to the higher-ranked one; mixed signed and unsigned compare rank and representability |
| [[conv.double]] floating-point conversions | implicit conversion only to a floating-point type of rank not lower than the source, except among the standard floating-point types |
| [[dcl.init.list#7]] narrowing | converting to a floating-point type whose rank is neither greater than nor equal to the source's is narrowing |
| [[over.ics.rank#4.3]] overload resolution | a conversion between floating-point types of equal rank is better than other conversions |

## Integer conversion rank (¶1)

¶1 Every integer type has an integer conversion rank, determined by nine rules:

- ¶1.1 No two signed integer types have the same rank, even if they have the same representation.
- ¶1.2 The rank of a signed integer type is greater than that of any signed integer type with a smaller width.
- ¶1.3 `long long` > `long` > `int` > `short` > `signed char`.
- ¶1.4 The rank of an unsigned integer type equals the rank of the corresponding signed type.
- ¶1.5 The rank of a standard integer type is greater than that of an extended integer type of the same width.
- ¶1.6 The rank of `bool` is less than that of all other integer types.
- ¶1.7 The ranks of the character types (`char`, `wchar_t`, `char8_t`, `char16_t`, `char32_t`) equal the ranks of their underlying types ([[basic.fundamental]]).
- ¶1.8 The relative rank of two extended signed integer types of the same width is implementation-defined, but still subject to the other rules.
- ¶1.9 Rank is transitive.

¶1.1 ensures signed types are totally ordered, so the usual arithmetic conversions can always pick one. ¶1.3 fixes the order of the five standard signed types regardless of width, so `long` and `long long` of the same width still have distinct ranks. ¶1.5 ensures that when an implementation adds an extended integer type, the types of existing expressions don't change. Note 1 explains that integer conversion ranks are used for integral promotion and the usual arithmetic conversions.

Some consequences:

- `char` has the same rank as one of `signed char` and `unsigned char`, yet the three remain distinct types. This doesn't violate ¶1.1, because `char` is not a signed integer type.
- The underlying types of `char16_t` and `char32_t` are `uint_least16_t` and `uint_least32_t`, usually `unsigned short` and `unsigned int`, and their ranks are the same as those types'.
- ¶1.2 and ¶1.3 together require the widths of the standard signed types to be non-decreasing; otherwise the two rules would contradict each other.

## How rank determines the type of integer arithmetic

[[expr.arith.conv#1.5]], for two integer operands, first performs integral promotion to get types T1 and T2, then:

1. if T1 and T2 are the same, that is the result type;
2. if both are signed or both unsigned, take the higher-ranked one;
3. otherwise let U be the unsigned one and S the signed one:
    - if U's rank is not lower than S's, the result is U;
    - otherwise, if S can represent all values of U, the result is S;
    - otherwise, the result is the unsigned type corresponding to S.

Step 3 looks at both rank and width, which is where platform differences come from:

```cpp run ok
#include <type_traits>

// the following assertions hold on LP64 (64-bit Linux, macOS)
static_assert(sizeof(long) == 8 && sizeof(int) == 4);

static_assert(std::is_same_v<decltype(1 + 1U),   unsigned>);   // equal rank: take U
static_assert(std::is_same_v<decltype(1L + 1U),  long>);       // long is higher and can represent every unsigned
static_assert(std::is_same_v<decltype(1LL + 1UL), unsigned long long>);
// unsigned long has lower rank than long long, and long long cannot represent
// all values of a 64-bit unsigned long, so the result is the unsigned type corresponding to long long

static_assert(std::is_same_v<decltype('a' + 'b'),  int>);      // char promotes to int
static_assert(std::is_same_v<decltype(true + true), int>);     // bool promotes to int
static_assert(std::is_same_v<decltype(u'a' + 1),  int>);       // char16_t promotes to int
static_assert(std::is_same_v<decltype(U'a' + 1),  unsigned>);  // char32_t promotes to unsigned
static_assert(std::is_same_v<decltype((unsigned short)1 + (unsigned short)1), int>);

int main() {}
```

On LLP64 (64-bit Windows, where `long` is 32 bits), `1L + 1U` yields `unsigned long`, because a 32-bit `long` cannot represent all values of `unsigned int`.

Signed and unsigned have equal rank (¶1.4) so that step 3 preserves values as far as possible: when `long` is wider than `unsigned int`, `long` can hold every `unsigned int` value, and the result stays signed. This is the value-preserving scheme inherited from C89.

Integral promotion is also bounded by rank. [[conv.prom#2]] specifies that, apart from `bool` and several character types, an integer type of rank lower than `int` is promoted to `int` (if `int` can represent all its values) and otherwise to `unsigned int`. `char8_t`, `char16_t`, `char32_t` and `wchar_t` are promoted by [[conv.prom#6]] to the first type that can represent all values of their underlying type, and `bool` is promoted to `int` by [[conv.prom#7]].

## Floating-point conversion rank (¶2)

Before C++23 there were only three floating-point types, and `float < double < long double` was written directly into the usual arithmetic conversions. C++23's [[P1467R9]] introduced extended floating-point types ([[basic.extended.fp]]), such as `std::float16_t` and `std::bfloat16_t`, which required a rule that handles any number of floating-point types.

¶2 Every floating-point type has a floating-point conversion rank:

- ¶2.1 If the set of values of one floating-point type is a proper subset of the set of values of `T`, `T` has the higher rank.
- ¶2.2 `long double` > `double` > `float`.
- ¶2.3 Two extended floating-point types with the same set of values have equal ranks.
- ¶2.4 An extended floating-point type with the same set of values as exactly one standard floating-point type has a rank equal to that standard type.
- ¶2.5 An extended floating-point type with the same set of values as more than one standard floating-point type has a rank equal to `double`.

Unlike integer rank, floating-point rank is a partial order. Note 3 points out that when the value sets of two types are not subsets of each other, their ranks are unordered; this happens when one has more range and less precision. `std::bfloat16_t` (8 exponent bits, 8 significand bits) and `std::float16_t` (5 exponent bits, 11 significand bits) are such a pair.

Assuming `float` and `double` are IEEE binary32 and binary64, and all extended types are available:

| Type | x86-64 Linux (80-bit `long double`) | Windows, Apple arm64 (`long double` same as `double`) |
|---|---|---|
| `std::bfloat16_t`, `std::float16_t` | lower than `float`, unordered with each other | same as left |
| `std::float32_t` | equal to `float` (¶2.4) | same as left |
| `std::float64_t` | equal to `double` (¶2.4) | equal to `double` (¶2.5: it has the same value set as both `double` and `long double`) |
| `long double` | higher than `double` | still higher than `double` (¶2.2, even with the same value set) |
| `std::float128_t` | higher than `long double` | higher than `long double` |

Note 2 points out a difference from C: on platforms where `long double`, `double` and `std::float64_t` all have the same value set, C treats the analogous `_Float64` differently (ISO/IEC 9899:2024 H.4.3).

## Floating-point conversion subrank (¶3)

Floating-point types of equal rank still need an order; otherwise the type of `float + std::float32_t` could not be decided.

¶3 Floating-point types of equal rank are ordered by floating-point conversion subrank, which is a total order among types of the same rank. The subranks of `std::float16_t`, `std::float32_t`, `std::float64_t` and `std::float128_t` are greater than that of any standard floating-point type of equal rank; otherwise the order of subranks is implementation-defined.

The extended types are preferred because a programmer who explicitly wrote `std::float32_t` usually wants a result of a definite format. If mixed arithmetic fell back to `float`, the format could no longer be seen from the type. `std::bfloat16_t` is not on this list; its value set differs from every standard floating-point type, so it never has equal rank with them.

¶4 is a note: floating-point conversion ranks and subranks are used in the usual arithmetic conversions.

## How floating-point rank determines the type of arithmetic

[[expr.arith.conv#1.4]] specifies for floating-point operands: if the types are the same, no conversion; if one is not a floating-point type, convert to the floating-point one; if the ranks are ordered and unequal, convert to the higher rank; if the ranks are equal, convert to the higher subrank; if the ranks are unordered, the program is ill-formed.

```cpp
#include <stdfloat>
#include <type_traits>

// assuming float/double are binary32/binary64 and all the following types are available
static_assert(std::is_same_v<decltype(1.0f + 1.0f16), float>);            // float16_t has lower rank
static_assert(std::is_same_v<decltype(1.0f + 1.0f32), std::float32_t>);   // equal rank, float32_t has the higher subrank
static_assert(std::is_same_v<decltype(1.0 + 1.0f64), std::float64_t>);    // same as above
static_assert(std::is_same_v<decltype(1.0L + 1.0f64), long double>);      // long double has the higher rank
auto x = 1.0bf16 + 1.0f16;   // error: unordered ranks
```

Clang 23 with libc++ does not provide `<stdfloat>` yet; this code is worked out from the standard and carries no verdict. For the three standard floating-point types, these rules give exactly the same results as C++20.

### Implicit conversion, narrowing, overloading

- [[conv.double#1]]: a floating-point prvalue can be implicitly converted to a floating-point type of rank not lower than the source's; among the standard floating-point types, conversion in any direction is allowed. So `float f = d;` (where `d` is a `double`) is still valid, while `std::float32_t g = d;` is ill-formed.
- [[dcl.init.list#7.2]]: a conversion from a floating-point type `T` to a floating-point type whose rank is neither greater than nor equal to `T`'s is narrowing (except where the result is a constant expression, the value is finite, there is no overflow, and so on). Unordered ranks count as narrowing too.
- [[over.ics.rank#4.3]]: a conversion between `FP1` and an `FP2` of equal rank is better than a conversion between `FP1` and another arithmetic type. The standard's example:

```cpp
int f(std::float32_t);
int f(std::float64_t);
int f(long long);
float x;
std::float16_t y;
int i = f(x);   // calls f(std::float32_t): float and float32_t have equal rank
int j = f(y);   // error: ambiguous; no candidate has the same rank as float16_t
```

All three conversions are merely of Conversion rank in [[over.ics.scs]]. Without ¶4.3, `f(x)` would be ambiguous too; with it, the conversion between floating-point types of equal rank wins. `f(y)` has no candidate of equal rank, so this tie-breaker does not apply, and it remains ambiguous.

!!! impl
    - GCC and Clang give `__int128` a rank higher than `long long`, so `__int128 + unsigned long long` has type `__int128`.
    - Clang's `_Float16` and `__bf16` are not implemented as C++23 extended floating-point types: in the libc++ we tested, `std::is_floating_point_v<_Float16>` is `false`. Mixed arithmetic with them follows Clang's own rules and cannot be used to check this subclause.

!!! history "History"
    - C++98 had no integer conversion rank; the usual arithmetic conversions listed types one by one (if either operand is `long double`… otherwise if either is `double`…).
    - When C++11 added `long long` and extended integer types, it imported integer conversion rank from C99 and rephrased the usual arithmetic conversions in terms of rank.
    - C++23's [[P1467R9]] introduced floating-point conversion rank and subrank, replacing the hard-coded `float < double < long double`; the usual arithmetic conversions gained the rule that unordered ranks are ill-formed, and floating-point conversions, narrowing and overload resolution were revised accordingly.

## Common misconceptions

!!! pitfall "Adding two 64-bit types yields one of them"
    `long long + unsigned long` is `unsigned long long` on LP64. Code that depends on the result type (template dispatch, `auto` variables, `printf` format specifiers) should use `std::common_type_t` or explicit conversions.

!!! pitfall "Mixing `long` and `unsigned` behaves the same on every platform"
    On LP64, `long + unsigned` is `long`; on LLP64 it is `unsigned long`. The latter makes `-1L < 1U` false, because `-1L` is converted to the maximum value of `unsigned long`. GCC and Clang's `-Wsign-compare` warns about such comparisons, and since C++20 functions like `std::cmp_less` can be used instead ([[utility.intcmp]]).

!!! pitfall "`std::float32_t` can be initialized from a `double` like `float`"
    `std::float32_t x = 0.1;` is ill-formed; write `0.1f32`. `float x = 0.1;` is valid because implicit conversion in any direction is kept among the standard floating-point types.

## Questions

!!! question "1. An implementation provides a 64-bit extended signed integer type `__ext64`, and `long long` is also 64 bits. What is the type of `__ext64 + unsigned long long`?"

<details markdown="1">
<summary>Answer</summary>

`unsigned long long`. By ¶1.5, a standard integer type has a higher rank than an extended integer type of the same width, so `unsigned long long` outranks `__ext64`. By [[expr.arith.conv#1.5.3.1]], when the unsigned operand's rank is not lower than the signed one's, the result is the unsigned type.
</details>

!!! question "2. Why does ¶2.5 give `std::float64_t` the rank of `double` rather than `long double`?"

<details markdown="1">
<summary>Answer</summary>

The standard gives no reason. A plausible explanation is to keep the behavior of `std::float64_t` the same across platforms. On x86-64 Linux, `float64_t` has the same rank as `double` by ¶2.4, below `long double`. If, on platforms where `long double` is the same as `double`, it took the rank of `long double`, then `float64_t + long double` would yield `float64_t` (higher subrank), unlike `long double` on Linux. With the rank of `double`, `float64_t` has the same rank as `double` and is below `long double` on both platforms.
</details>

!!! question "3. `char` has the same rank as `signed char`; what is the type of `char + signed char`?"

<details markdown="1">
<summary>Answer</summary>

`int`. Both operands have ranks below `int`, and `int` can represent all their values, so after integral promotion both are `int`, and by [[expr.arith.conv#1.5.1]] the result is `int`. Whether they have equal rank is irrelevant here; integer rank mostly matters among `int` and higher types.
</details>
