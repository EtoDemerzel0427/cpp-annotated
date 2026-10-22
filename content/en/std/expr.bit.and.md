---
title: Bitwise AND, exclusive OR and inclusive OR operators
summary: "& ^ | accept integral types and unscoped enumerations, apply the usual arithmetic conversions, then operate bit by bit on the two's complement representation, and are defined for every input; they bind less tightly than ==, do not short-circuit, and their two operands are unsequenced."
updated: 2026-10-19
---

!!! tldr
    - The operands of `&`, `^` and `|` must have integral or unscoped enumeration type; the usual arithmetic conversions are applied first, then the operation is done bit by bit on the two's complement representation. The result is always representable, and there is no undefined behavior.
    - Integral promotion makes bitwise operations on `bool`, `char` and `uint8_t` yield `int`, so `~std::uint8_t{0xF0}` is −241, not `0x0F`.
    - These three operators have lower precedence than `==`: `x & 1 == 0` is `x & (1 == 0)`.
    - They don't short-circuit: both operands are evaluated, and they are unsequenced; when `&` replaces `&&`, the right side cannot rely on a check on the left.
    - Bitwise operations on unscoped enumerations yield integers; since C++26, bitwise operations between different enumeration types are ill-formed.

[[expr.bit.and]] (`&`), [[expr.xor]] (`^`) and [[expr.or]] (`|`) have the same structure, with a single paragraph each.

## Bitwise operation ([[expr.bit.and#1]], [[expr.xor#1]], [[expr.or#1]])

```cpp run title="bitwise-values.cpp" ok
static_assert((0b1100 & 0b1010) == 0b1000);
static_assert((0b1100 ^ 0b1010) == 0b0110);
static_assert((0b1100 | 0b1010) == 0b1110);
static_assert((-1 & 0xFF) == 255);    // every bit of -1 is 1
static_assert((~0 ^ 5) == -6);        // ~0 is -1, and ^ flips every bit of 5
static_assert((-8 | 3) == -5);        // ...11111000 | 00000011 = ...11111011

int main() {}
```

¶1 All three operators group left-to-right; the operands must have integral or unscoped enumeration type and first undergo the usual arithmetic conversions ([[expr.arith.conv]]), which bring both sides to the same type. Let the converted operands be *x* and *y* and the result *r*, and let *x<sub>i</sub>*, *y<sub>i</sub>* and *r<sub>i</sub>* be the coefficients of bit *i* in their base-2 representations:

| Operator | *r<sub>i</sub>* is 1 when |
|---|---|
| `&` | both *x<sub>i</sub>* and *y<sub>i</sub>* are 1 |
| `^` | exactly one of *x<sub>i</sub>* and *y<sub>i</sub>* is 1 |
| `\|` | at least one of *x<sub>i</sub>* and *y<sub>i</sub>* is 1 |

The **base-2 representation** is defined in [[basic.fundamental]]: for a signed integer of width *N*, every value *x* is written uniquely as Σ *x<sub>i</sub>* 2<sup>i</sup>, where the highest bit has weight −2<sup>N−1</sup>. That is two's complement, so every bit of `-1` is 1.

This definition depends only on values, not on how the object is stored in memory. Every bit of the result is 0 or 1, so the result is always representable in the result type, and these three operators are defined for every input.

!!! history "Before C++20, bitwise operations on negative numbers depended on the representation"
    In C++17 and earlier, signed integers could use two's complement, ones' complement or sign-magnitude representation, and bitwise operations acted on the representation of the value. So `-1 & 0xFF` was 255 on a two's complement machine, 254 on a ones' complement machine, and 1 on a sign-magnitude machine. C++20's [[P0907R4]] (Signed Integers are Two's Complement) made two's complement the only representation, and the wording paper [[P1236R1]] rewrote these three subclauses into a definition based on base-2 coefficients.

### Integral promotion changes the result type

The first step of the usual arithmetic conversions is integral promotion ([[conv.prom]]): types narrower than `int` become `int` first. So bitwise operations on `bool`, `char` and `short` all yield `int`:

```cpp run title="bitwise-types.cpp" ok
#include <type_traits>
#include <cstdint>

static_assert(std::is_same_v<decltype(true & false), int>);
static_assert(std::is_same_v<decltype(std::uint8_t{1} | std::uint8_t{2}), int>);

int main() {
    std::uint8_t a = 0xF0;
    auto b = ~a;                 // int, value -241, not 0x0F
    std::uint8_t c = ~a;         // 0x0F only after truncation
    return (b == -241 && c == 0x0F) ? 0 : 1;
}
```

Unary `~` doesn't belong to this subclause (see [[expr.unary.op]]), but it often appears together with these bitwise operators and runs into the same integral promotion issue.

## Lower precedence than `==`

```cpp run title="bitwise-precedence.cpp" ok
bool is_even_wrong(int x) { return x & 1 == 0; }    // x & (1 == 0), i.e. x & 0, always false
bool is_even_right(int x) { return (x & 1) == 0; }

int main() { return (!is_even_wrong(4) && is_even_right(4)) ? 0 : 1; }
```

Early C had no `&&` or `||`; `&` and `|` doubled as logical AND and OR, so their precedence was placed below the comparison operators, letting `a == b & c == d` read as a logical operation. `&&` and `||` were added later, but to stay compatible with existing code, the precedence of `&` and `|` was never changed.

The complete order is: `==` and `!=` bind tighter than `&`, `&` tighter than `^`, `^` tighter than `|`, and `|` tighter than `&&`. `-Wparentheses`, included in `-Wall`, warns about the code above: "& has lower precedence than ==; == will be evaluated first".

## No short-circuiting, unsequenced operands

Unlike `&&` and `||` ([[expr.log.and]]), `&`, `^` and `|` always evaluate both operands, and the standard imposes no order between them: their evaluations are **unsequenced** ([[intro.execution#10]]). Two modifications of the same variable that are unsequenced relative to each other are UB:

```cpp title="bitwise-unsequenced.cpp" ub
int main() {
    int i = 0;
    int r = (i = 1) | (i = 2);   // UB: the two modifications of i are unsequenced
    return r;
}
```

People sometimes deliberately combine two `bool`s with `&`: there is no branch, which may be faster for hard-to-predict conditions, at the cost of evaluating both sides. If the right side relies on a check on the left, this rewrite goes wrong:

<div class="compare" markdown="1">

```cpp ok
struct S { int x; };
bool ok(S* p) {
  return p != nullptr
      && p->x > 0;
}
```

```cpp ub
struct S { int x; };
bool ok(S* p) {
  return (p != nullptr)
       & (p->x > 0);
}
// still dereferences p when it is null: UB
```

</div>

## Enumerations as flags

Unscoped enumerations can be used directly in bitwise operations; after integral promotion the result is an integer, no longer of the enumeration type, and storing it back into an enumeration variable needs an explicit conversion. Bitwise operations between different enumeration types were deprecated in C++20 and made ill-formed in C++26 by [[P2864R2]]:

```cpp title="bitwise-enum.cpp" error
enum Perm { read = 1, write = 2, exec = 4 };
enum Mode { text = 8 };

Perm p1 = read | write;                       // error: the result is int, which doesn't convert back to Perm implicitly
Perm p2 = static_cast<Perm>(read | write);    // OK
auto x  = read | text;                        // error: different enumeration types (since C++26)
```

Scoped enumerations (`enum class`) cannot be used directly in bitwise operations; you have to overload `operator|` and the others yourself. That is exactly the point of the design: which combinations make sense is for the type's author to declare explicitly. `std::byte` ([[cstddef.syn]]) is a scoped enumeration that provides only bitwise operations.

`&`, `^` and `|` also have the alternative tokens `bitand`, `xor` and `bitor`, and the compound assignments have `and_eq`, `xor_eq` and `or_eq` ([[lex.digraph]]); they are exactly equivalent to the primary tokens.

!!! impl
    The three operators map directly to the `and`, `eor`/`xor` and `orr`/`or` instructions, all single-cycle operations on mainstream architectures. Optimizers make wide use of their algebraic properties, for example `x & (x - 1)` clearing the lowest set bit and `x ^ x` being 0. C++20's `<bit>` (`std::popcount`, `std::countr_zero`, `std::has_single_bit` and so on) offers portable interfaces for common bit tricks that can map to dedicated instructions.

## Common misconceptions

!!! pitfall "`x & mask == 0`"
    `==` binds first; write `(x & mask) == 0`.

!!! pitfall "`~u8` is still 8 bits"
    `~std::uint8_t{0xF0}` is the `int` value −241, and comparing it with another `uint8_t` gives surprising results.

!!! pitfall "Before C++20, bitwise operations on negative numbers had determined results"
    In C++17 and earlier they depended on the representation of signed integers; it just made no practical difference because mainstream platforms all used two's complement.

## Questions

!!! question "Question"
    Is `int a = 3, b = 5; a ^= b ^= a ^= b;` defined in C++14 and in C++17? What is the result?

<details markdown="1">
<summary>Answer</summary>

This is the one-line XOR swap. The issue is the evaluation order of compound assignment ([[expr.assign]]), not `^` itself.

C++14: the outermost `a ^= (...)` reads `a`, and the `a ^= b` inside the right operand modifies `a`, with no ordering between the two, so it is UB. Clang warns "unsequenced modification and access to 'a'" under `-std=c++14`.

Since C++17, [[P0145R3]] specifies that the right operand of an assignment is sequenced before the left operand. So execution proceeds from the innermost: `a = 3^5 = 6`, `b = 5^6 = 3`, `a = 6^3 = 5`. The result is `a == 5` and `b == 3`; defined. In real code you should of course write `std::swap(a, b)`.
</details>

## Summary

| Aspect | `&` `^` `\|` |
|---|---|
| Operands | Integral or unscoped enumeration, with the usual arithmetic conversions |
| Semantics | Bit by bit on the base-2 (two's complement) representation; independent of representation since C++20 |
| UB | None; the result is always representable |
| Evaluation | Both sides evaluated, unsequenced, no short-circuiting |
| Precedence | Lower than `==` and `!=`; `&` tighter than `^` tighter than `\|` tighter than `&&` |
| Enumerations | Same unscoped enumeration allowed, result is an integer; mixing different enumerations ill-formed since C++26 |
