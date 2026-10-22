---
title: Shift operators
summary: "The two operands of << and >> are each promoted, and the result type is that of the left operand; a negative shift count or one not less than the width is undefined behavior; since C++20 left shift is defined modulo 2^N and right shift rounds toward negative infinity; since C++17 the left operand is evaluated first."
updated: 2026-10-19
---

!!! tldr
    - The two operands of `<<` and `>>` each undergo integral promotion, not the usual arithmetic conversions; the result type is the type of the promoted left operand, so `1 << 40LL` is still `int`.
    - A shift count that is negative, or not less than the width of the left operand, is undefined behavior. For a 64-bit mask, write `1LL << n` or `std::uint64_t{1} << n`.
    - Since C++20, a left shift is always defined as long as the count is valid: the result is the value congruent to E1×2<sup>E2</sup> modulo 2<sup>N</sup>, and left-shifting a negative number is no longer UB.
    - Right shift rounds toward negative infinity, and signed values are shifted arithmetically, so `-7 >> 1 == -4` while `-7 / 2 == -3`.
    - Since C++17 the left operand is evaluated before the right operand, so `std::cout << f() << g()` calls `f` first.

## The result type is the left operand's (¶1)

```cpp run title="shift-types.cpp" ok
#include <type_traits>

static_assert(std::is_same_v<decltype(1 << 2LL), int>);      // the right operand doesn't affect the result type
static_assert(std::is_same_v<decltype(char(1) << 2), int>);  // char is promoted to int
static_assert(std::is_same_v<decltype(1u << 2), unsigned>);
static_assert(std::is_same_v<decltype(1LL << 2), long long>);
static_assert((char(1) << 20) == (1 << 20));                 // promote first, then shift

int main() {}
```

¶1 `<<` and `>>` group left-to-right. The operands must be prvalues of integral or unscoped enumeration type, and each side undergoes integral promotion ([[conv.prom]]) on its own, which turns types narrower than `int` into `int`. The result type is the type of the promoted left operand.

This differs from `+` and `*`. Those operators perform the usual arithmetic conversions ([[expr.arith.conv]]), bringing both sides to a common type. A shift count is just a distance; there is no reason for `1 << 3LL` to become `long long`.

### An out-of-range count is UB

!!! std
    The behavior is undefined if the right operand is negative, or greater than or equal to the width of the promoted left operand.

If the right operand is negative, or greater than or equal to the width of the promoted left operand, the behavior is undefined. The **width** is the number of bits in the value representation, excluding padding bits ([[basic.fundamental]]); a 32-bit `int` has width 32.

<div class="compare" markdown="1">

```cpp ok
static_assert((1LL << 32)
              == 4294967296LL);
static_assert((1u << 31)
              == 2147483648u);
```

```cpp error
constexpr long long c = 1 << 32;
// error: 1 is int, count 32 is out of range;
// assigning the result to long long doesn't help
```

</div>

The right-hand side is the most common mistake: wanting a 64-bit mask but writing `1 << n`. The left operand `1` has type `int`, so the result type is `int` too, and no target type of the assignment changes that. The following forms are UB as well and are rejected in constant expressions:

```cpp title="shift-count-ub.cpp" error
constexpr int a = 1 << 32;      // error: count equals the width of int
constexpr int b = 1 << 40LL;    // error: the result is still int, 40 ≥ 32
constexpr int d = 1 << -1;      // error: negative count
```

!!! impl "Why no fixed result is specified"
    Hardware handles excessive counts differently, and whichever result the standard picked, other platforms would pay extra for it:

    - The variable-shift instructions on x86-64 and AArch64 take the count modulo the width, so at run time `1 << 32` gives 1. That is what we observed on arm64.
    - Register shifts on 32-bit ARM use the low 8 bits of the count; a count of 32 shifts all bits out, giving 0.
    - SIMD instructions such as SSE2's `psllq` give 0 when the count is too large.

    So on one and the same machine, the scalar and vectorized versions of the same line `x << n` may even give different results. With it being UB, the compiler can emit a single shift instruction. `-fsanitize=shift-exponent` (included in `-fsanitize=undefined`) reports "shift exponent 32 is too large for 32-bit type 'int'" at run time.

## The value of a left shift (¶2)

```cpp run title="shift-left-cxx20.cpp" ok
#include <climits>

static_assert((-1 << 31) == INT_MIN);    // UB in C++17
static_assert((3 << 31) == INT_MIN);     // UB in C++17
static_assert((INT_MAX << 1) == -2);
static_assert((-8 << 1) == -16);

int main() {}
```

¶2 The value of `E1 << E2` is the unique value congruent to E1×2<sup>E2</sup> modulo 2<sup>N</sup>, where *N* is the width of the result type. Note 1 puts it another way: `E1` is left-shifted `E2` bit positions, and vacated bits are zero-filled.

For unsigned types this is the familiar discarding of high bits. For signed types it is equivalent to shifting the two's complement bit pattern left, discarding the high bits, and reinterpreting the result as two's complement. Left-shifting negative numbers, shifting into the sign bit, and shifting out significant bits are all defined; only the count itself is restricted by paragraph 1.

A left shift is not among the arithmetic expressions of [[expr.pre#4]], so the general rule that a mathematically unrepresentable result is UB does not apply. This also means `x << 1` and `x * 2` are not equivalent: `INT_MAX * 2` is UB, and `INT_MAX << 1` is −2.

!!! history "The changes to left shift"
    - The C++98/03 wording only described the result for unsigned types.
    - C++11 said: if `E1` is signed and non-negative, and E1×2<sup>E2</sup> is representable in the result type, that is the result; otherwise UB. So `1 << 31` was UB too.
    - C++14 relaxed this: if the value is representable in the corresponding unsigned type, it is converted to the result type. From then on `1 << 31` and `INT_MAX << 1` were defined, while left-shifting a negative number was still UB.
    - C++20's [[P0907R4]] specified two's complement for signed integers, and the wording paper [[P1236R1]] rewrote left shift into today's modulo-2<sup>N</sup> definition.

    Compiling the example above with `-std=c++17`, Clang explains the first two assertions with "left shift of negative value -1" and "signed left shift discards bits" respectively.

## The value of a right shift (¶3)

```cpp run title="shift-right.cpp" ok
static_assert((-7 >> 1) == -4);   // toward negative infinity: floor(-3.5) = -4
static_assert((-7 / 2)  == -3);   // integer division toward zero: trunc(-3.5) = -3
static_assert((-1 >> 31) == -1);  // vacated high bits are filled with the sign bit
static_assert(( 7 >> 1) ==  3);

int main() {}
```

¶3 The value of `E1 >> E2` is E1/2<sup>E2</sup>, rounded toward negative infinity. Note 2 points out that for signed types this is an **arithmetic right shift**: the vacated high bits are filled with the sign bit.

Integer division truncates toward zero ([[expr.mul#4]]), so for a negative odd number, shifting right by one and dividing by 2 differ by 1. The compiler cannot compile a signed `x / 2` directly into `x >> 1`; it has to add 1 to negative numbers before shifting. If `x` is known to be non-negative, using an unsigned type saves those few instructions.

Before C++20, the result of right-shifting a negative number was implementation-defined, and an implementation could choose a logical right shift (zero-filling the high bits). Mainstream compilers have always used arithmetic right shift; C++20 merely wrote it into the standard.

## Evaluation order (¶4)

¶4 `E1` is sequenced before `E2`. This rule was added in C++17 by [[P0145R3]]. Built-in shifts rarely have side effects; the real beneficiary is overloaded `operator<<`: [[over.match.oper]] says that when an overloaded operator is invoked with operator syntax, the operands are evaluated in the order of the corresponding built-in operator.

```cpp run title="shift-iostream-order.cpp" ok
#include <iostream>

int counter = 0;
int next() { return ++counter; }

int main() {
    std::cout << next() << ' ' << next() << '\n';   // guaranteed to print 1 2
    int i = 0;
    std::cout << i++ << ' ' << i++ << '\n';         // guaranteed to print 0 1
}
```

In C++14, `std::cout << next() << next()` amounts to the nested call `operator<<(operator<<(cout, next()), next())`, the order of the two `next()` calls is unspecified, and some implementations print `2 1`; the `i++` line is outright UB.

This guarantee holds only for operator syntax. Written explicitly as `operator<<(operator<<(std::cout, f()), g())` it is an ordinary function call, and the order among the arguments is still unspecified ([[expr.call]]). See [[topics/order-of-evaluation]] for more.

## Precedence

Shifts have lower precedence than `+` and `-`, and higher than the relational operators and `&`, `^`, `|`:

```cpp run title="shift-precedence.cpp" ok
int main() {
    int n = 2;
    int a = 1 << n + 1;      // 1 << (n + 1) == 8, not (1 << n) + 1
    int b = (1 << n) + 1;    // 5
    unsigned flags = 0b1010;
    bool c = flags & 1 << 3; // flags & (1 << 3)
    return (a == 8 && b == 5 && c) ? 0 : 1;
}
```

Clang gives a `-Wshift-op-parentheses` warning for `1 << n + 1`, suggesting parentheses.

## Common misconceptions

!!! pitfall "`x << n` equals `x * 2^n`"
    They differ on overflow: since C++20 a left shift is defined modulo 2<sup>N</sup>, while multiplication overflow is UB.

!!! pitfall "Right shift equals division by 2^n"
    Right shift rounds toward negative infinity and division truncates toward zero; for negative odd numbers the results differ by 1.

!!! pitfall "Writing a rotation as `(x << n) | (x >> (32 - n))`"
    When `n == 0`, `x >> 32` is UB. Since C++20, use `std::rotl` and `std::rotr` from `<bit>`, which are defined for any count.

## Questions

!!! question "Question 1"
    Assume a 32-bit `int`. What are the type and value of `unsigned short s = 0xFFFF; auto r = s << 16;`? Is there a difference between C++17 and C++20?

<details markdown="1">
<summary>Answer</summary>

`s` is promoted to `int` with value 65535, and the result type is `int`. The mathematical value 65535 × 2<sup>16</sup> = 0xFFFF0000 exceeds `INT_MAX`.

- C++20: the result is the `int` value congruent to it modulo 2<sup>32</sup>, i.e. −65536; defined.
- C++17: `E1` is non-negative and 0xFFFF0000 is representable in `unsigned int`, so the result is that value converted to `int`. That conversion was implementation-defined at the time, giving −65536 on two's complement machines.
- For `s << 17`, the mathematical value exceeds the range of `unsigned int`: UB in C++17; defined in C++20, with value −131072.
</details>

!!! question "Question 2"
    Is `bool b = true; auto r = b << 31;` defined?

<details markdown="1">
<summary>Answer</summary>

`bool` is an integral type and is promoted to `int` with value 1; the result type is `int`. The count 31 is less than 32, so it is valid. In C++20 the result is the `int` congruent to 2<sup>31</sup> modulo 2<sup>32</sup>, i.e. `INT_MIN`; defined. Under the original C++11 wording, shifting into the sign bit was UB.
</details>

## Summary

| Aspect | Rule | Paragraph |
|---|---|---|
| Conversions and result type | Each side promoted on its own; result type = type of the promoted left operand | ¶1 |
| Count negative or ≥ width | {{ub}} | ¶1 |
| Left shift | Congruent to E1×2<sup>E2</sup> modulo 2<sup>N</sup> (left-shifting negative numbers defined since C++20) | ¶2 |
| Right shift | E1/2<sup>E2</sup> rounded toward negative infinity, i.e. arithmetic right shift | ¶3 |
| Evaluation order | `E1` before `E2` (since C++17), also for overloaded `<<` | ¶4 |
