---
title: Multiplicative operators
summary: "Which operands * / % accept and what type the result has; integer division truncates toward zero and the remainder has the sign of the dividend; why division by zero and INT_MIN / -1 are undefined behavior."
updated: 2026-10-19
---

!!! tldr
    - `*`, `/` and `%` group left-to-right; the operands first undergo the usual arithmetic conversions, and the resulting common type is the type of the result. `%` accepts only integers and unscoped enumerations.
    - Multiplying two `unsigned short` values is actually an `int` multiplication; if the product is out of range for `int`, the behavior is undefined.
    - Integer division truncates toward zero, `-7 / 2 == -3`; the remainder has the same sign as the dividend, `-7 % 2 == -1`.
    - A zero divisor is undefined behavior, for floating-point division too.
    - When the quotient is not representable, both `/` and `%` are undefined behavior, so `INT_MIN / -1` and `INT_MIN % -1` are both UB.

## Grouping (¶1)

¶1 `*`, `/` and `%` have the same precedence and group left-to-right: `a / b * c` is `(a / b) * c`. Integer arithmetic truncates, so the order changes the result:

```cpp run title="mul-assoc.cpp" ok
int main() {
    int a = 7, b = 2, c = 3;
    int x = a / b * c;     // (7 / 2) * 3 = 3 * 3 = 9
    int y = a * c / b;     // (7 * 3) / 2 = 21 / 2 = 10
    return (x == 9 && y == 10) ? 0 : 1;
}
```

Multiplying first keeps more precision, but the intermediate result is more likely to overflow. The compiler won't reorder for you, because integer multiplication and division are not associative, and reordering could also change whether overflow happens.

The operands of a multiplicative expression are *pm-expression*s, i.e. pointer-to-member expressions ([[expr.mptr.oper]]), so `a * s.*pm` is `a * (s.*pm)`.

## Operands and result type (¶2)

```cpp title="mul-types.cpp" error
enum class Color { red, green };
enum E1 { e1 };
enum E2 { e2 };

auto a = 5.0 % 2;           // error: % does not accept floating-point
auto b = Color::red * 2;    // error: scoped enumerations don't take part in arithmetic
auto c = e1 * e2;           // error: two different enumeration types
auto d = e1 * 2.0;          // error: enumeration mixed with floating-point
auto e = e1 * 2;            // OK: e1 is first promoted to int
```

¶2 The operands of `*` and `/` must have arithmetic or unscoped enumeration type; the operands of `%` must have integral or unscoped enumeration type, and a floating-point remainder needs `std::fmod`. The operands first undergo the **usual arithmetic conversions** ([[expr.arith.conv]]), which bring both sides to the same type, and that type is the type of the result.

The `c` and `d` lines were only deprecated in C++20/23; C++26 made them ill-formed through [[P2864R2]] ([[diff.cpp23.expr]]).

### Overflow caused by integral promotion

The first step of the usual arithmetic conversions is **integral promotion** ([[conv.prom]]): a type narrower than `int`, such as `char`, `short`, `unsigned short` or `bool`, is first converted to `int` as long as `int` can represent all its values. So multiplying two `unsigned short` values performs a signed `int` multiplication:

```cpp run title="mul-promotion-ub.cpp" ub flags="-std=c++2c -O0 -fsanitize=undefined"
int main() {
    unsigned short a = 65535;
    unsigned short b = 65535;
    unsigned r = a * b;   // UB: a and b are promoted to int, and 65535 * 65535 exceeds a 32-bit int
    return r == 0;
}
```

Whoever wrote this thinks it is unsigned arithmetic that wraps around modulo, but it is actually signed overflow. UBSan reports `signed integer overflow: 65535 * 65535 cannot be represented in type 'int'`. The fix is to convert one operand first: `unsigned(a) * b`. `uint16_t` and `uint8_t` have the same problem on platforms with a 32-bit `int`.

## Multiplication and overflow (¶3)

¶3 only says that the binary `*` indicates multiplication. What happens when the result is out of range is specified once for all in [[expr.pre#4]]: `*`, `/`, `%`, `+` and `-` are all **arithmetic expressions**, and if the mathematical result is neither in the range of representable values of the result type nor a ±∞ or NaN that the type has, the behavior is undefined.

- Signed integers: out of range means {{ub}}. C++20 specifies that signed integers use two's complement representation, but it defines only the representation and conversions; arithmetic overflow is still UB.
- Unsigned integers: arithmetic is performed modulo 2<sup>N</sup>, the result is always in range, and it never overflows ([[basic.fundamental]]).
- Floating-point types conforming to IEC 60559 (i.e. IEEE 754): overflow yields ±∞, a value the type has, so it is defined. However, an expression that produces an infinity or NaN from finite operands is not a core constant expression ([[expr.const.core]]).

## Division and remainder (¶4)

### Division by zero

!!! std
    If the second operand of / or % is zero, the behavior is undefined.

This holds for floating-point as well. Note 4 of [[expr.pre#4]] points out that for IEC 60559 types, division by zero is the only undefined behavior of arithmetic expressions. At run time you usually get the ∞ or NaN produced by the hardware, but in constant evaluation any UB makes the expression no longer a constant expression:

```cpp title="mul-div-zero-const.cpp" error
constexpr double x = 1.0 / 0.0;   // error: not a constant expression (division by zero)
constexpr int    y = 5 % 0;       // error: not a constant expression (division by zero)
```

`-fsanitize=undefined` does not check floating-point division by zero by default; you have to add `-fsanitize=float-divide-by-zero`. The standard says it is UB, implementations give it a result according to IEEE, and the sanitizer's default reflects the latter.

### Truncation toward zero and the sign of the remainder

¶4 For integral operands, `/` yields the algebraic quotient with any fractional part discarded; a footnote calls this **truncation toward zero** ([[g:truncation-toward-zero]]): `-7 / 2` is `-3`, not `-4` as with rounding down.

¶4 then defines `%` by an identity: if the quotient `a/b` is representable in the type of the result, `(a/b)*b + a%b == a`. From truncation toward zero and this identity it follows that the remainder is either zero or has the same sign as the dividend `a`, regardless of the sign of the divisor:

```cpp run title="mul-sign.cpp" ok
static_assert( 7 /  2 ==  3 &&  7 %  2 ==  1);
static_assert(-7 /  2 == -3 && -7 %  2 == -1);   // remainder is negative with the dividend
static_assert( 7 / -2 == -3 &&  7 % -2 ==  1);   // the divisor's sign doesn't affect the remainder
static_assert(-7 / -2 ==  3 && -7 % -2 == -1);

int main() {}
```

So testing for odd numbers with `x % 2 == 1` fails for negative odd numbers; write `x % 2 != 0`. If you need a non-negative modulus, for example for a ring-buffer index, correct it yourself: `((a % n) + n) % n`.

C++ doesn't make the remainder take the divisor's sign as Python does because division instructions such as x86 `idiv` and ARM `sdiv` truncate toward zero. The language maps directly to the hardware, so signed division takes a single instruction.

!!! history "Before C++11"
    C++98/03 only required the remainder to be non-negative when both operands were non-negative; otherwise the sign of the remainder was implementation-defined, and a footnote recommended truncation toward zero. C99 made truncation toward zero a requirement, and C++11 followed. Almost all hardware at the time truncated toward zero, so the change didn't affect real code.

### Quotient not representable: `INT_MIN / -1`

¶4 finally says that if the quotient is not representable, the behavior of both `a/b` and `a%b` is undefined. For a two's complement `int`, this happens in only one case: `INT_MIN / -1`, whose mathematical result 2<sup>31</sup> is one more than `INT_MAX`.

```cpp title="mul-intmin.cpp" error
#include <climits>

constexpr int q = INT_MIN / -1;   // error: not a constant expression (quotient not representable)
constexpr int r = INT_MIN % -1;   // error: not a constant expression (also UB)
```

The mathematical value of `INT_MIN % -1` is 0, perfectly representable, yet it is UB too, and the reason is the hardware. x86 `idiv` computes the quotient and the remainder together, and when the quotient overflows it raises the same exception as division by zero. If the standard required `INT_MIN % -1 == 0`, compilers would have to insert a branch before every divisor that might be `-1`; with it being UB, a single `idiv` is enough.

!!! impl
    - x86/x86-64: `idiv` raises #DE when the divisor is 0 or the quotient overflows; on Linux this shows up as `SIGFPE` with the message "Floating point exception", even though no floating-point is involved.
    - AArch64: `sdiv` does not trap; division by zero gives 0, and `INT_MIN / -1` gives `INT_MIN`. The same UB program doesn't crash on ARM but gives a wrong result instead.
    - Division by a constant: the compiler rewrites `x / 10` as a multiplication by a constant followed by a shift, because multiplication is much faster than division. Signed division by a power of two cannot be done directly with an arithmetic right shift (the right shift rounds toward negative infinity, see [[expr.shift]]); negative numbers first get 2<sup>k</sup> − 1 added before shifting, so `x / 2` on an `int` takes a few more instructions than on an `unsigned`.
    - UBSan: `signed-integer-overflow` and `integer-divide-by-zero` are included in `undefined`; `float-divide-by-zero` has to be enabled separately.

## Common misconceptions

!!! pitfall "`%` is the mathematical modulo operation"
    C++'s `%` is a truncating remainder, and the result follows the sign of the dividend. `-1 % 5 == -1`, not 4.

!!! pitfall "Two's complement in C++20 made signed overflow defined"
    C++20 specifies the representation and conversions of signed integers. Arithmetic overflow is still UB, and so is `INT_MIN / -1`.

!!! pitfall "Floating-point division by zero always gives ∞"
    That is a rule of IEEE 754, not of C++. For IEC 60559 types, overflow to ∞ is defined, but division by zero is still UB; where a constant expression is required, it makes the program ill-formed.

## Questions

!!! question "Question 1"
    Assume a 32-bit `int`. After `long long x = INT_MIN;`, is `x / -1` defined? What about `INT_MIN / -1LL`? And `INT_MIN / -1u`?

<details markdown="1">
<summary>Answer</summary>

- `x / -1`: `-1` becomes `long long` through the usual arithmetic conversions, and the quotient 2<sup>31</sup> is representable in `long long`; it is defined, and the result is 2147483648.
- `INT_MIN / -1LL`: likewise, `INT_MIN` is converted to `long long`; defined.
- `INT_MIN / -1u`: `-1u` is an `unsigned int` with value 4294967295; the usual arithmetic conversions turn `INT_MIN` into the `unsigned int` 2147483648, and unsigned division gives 0. Defined, but probably not what was intended.
</details>

!!! question "Question 2"
    Does `short a = -32768; short b = -1; short c = a / b;` have undefined behavior?

<details markdown="1">
<summary>Answer</summary>

The division itself doesn't. `a` and `b` are first promoted to `int`, and `-32768 / -1` gives the `int` 32768, which is representable. Converting 32768 back to `short` afterwards is an integral conversion; since C++20 its result is defined modulo as -32768 ([[conv.integral]]), so that isn't UB either.
</details>

## Summary

| Case | Result | Basis |
|---|---|---|
| `%` on floating-point; scoped enumeration in arithmetic | {{ill-formed}} | ¶2 |
| Different enumerations, or enumeration mixed with floating-point | {{ill-formed}} (C++26; deprecated before) | ¶2, [[expr.arith.conv]] |
| Zero divisor (integer or floating-point) | {{ub}} | ¶4 |
| Integer division | Truncates toward zero | ¶4 |
| Sign of the remainder | Same as the dividend | ¶4 |
| `INT_MIN / -1`, `INT_MIN % -1` | {{ub}} | ¶4 |
| Signed multiplication overflow | {{ub}} | [[expr.pre#4]] |
| IEC 60559 floating-point overflow | ±∞, defined, but not a constant expression | [[expr.pre#4]] |
| Unsigned multiplication | Modulo 2<sup>N</sup> | [[basic.fundamental]] |
