---
title: Pitfalls of integer and floating-point arithmetic
summary: How built-in arithmetic quietly changes the types of its operands before computing, which out-of-range results wrap and which are UB, what the standard guarantees about floating point, and the library tools since C++20 for getting arithmetic right.
tags: integers, floating point, conversions, overflow, UB, topic
updated: 2026-10-19
---

!!! tldr
    - Before an operation, integers narrower than `int` are first promoted to `int`; when the two operands have different types, the usual arithmetic conversions then bring them to a common type. Mixing signed and unsigned usually ends up unsigned.
    - Conversion between integer types always wraps modulo 2<sup>N</sup> (including signed targets since C++20), while signed arithmetic overflow is UB, and the optimizer uses that to delete the overflow checks you wrote.
    - Division truncates toward zero. `INT_MIN / -1`, division by zero, and a shift count that is negative or not less than the width are all UB; since C++20 left-shifting a negative number is defined.
    - When converting floating point to integer, a value that doesn't fit after truncation is UB, and `(unsigned)-1.0` counts. NaN compares unequal to everything, and `-0.0 == 0.0`.
    - When you need correct comparison, saturation or overflow detection, use `std::cmp_less`, `std::in_range`, `std::saturating_add` and `ckd_add` instead of assembling expressions yourself.

## Two surprises

```cpp run title="surprise.cpp" ok
#include <cstdio>
#include <vector>
int main() {
  std::vector<int> v;                  // empty
  if (v.size() - 1 >= 0)               // always true
    std::puts("size() - 1 >= 0");
  std::printf("%zu\n", v.size() - 1);  // 18446744073709551615
  std::printf("%d\n", -1 < 1u);        // 0
}
```

The type of `v.size()` is `std::size_t`, an unsigned type. `0 - 1` in an unsigned type wraps modulo 2<sup>64</sup> to the maximum value, and an unsigned value is always `>= 0`. In `-1 < 1u`, `int` and `unsigned int` have to be brought to the same type before they can be compared; the result is `unsigned int`, and `-1` becomes 4294967295.

Both lines are well-formed code with well-defined behavior; the results just don't match mathematical intuition. Clang 23 with `-Wall -Wextra` warns about neither line: the diagnostic for an always-true `>= 0` (`-Wtautological-unsigned-zero-compare`) has to be enabled separately, and `-Wsign-compare` does not fire for constant operands.

To read code like this you need to know what happens, in order, when a built-in arithmetic expression is evaluated:

1. Each narrow integer operand undergoes integral promotion;
2. The two operands get a common type through the usual arithmetic conversions;
3. The operation is performed in the common type, and the result may overflow;
4. When the result is assigned to a variable or passed to a function, another conversion happens.

The sections below follow this order.

## Integral promotion: narrow integers become `int` first

```cpp run title="promote.cpp" ok
#include <cstdint>
#include <cstdio>
#include <type_traits>
int main() {
  std::uint8_t a = 200, b = 100;
  auto s = a + b;                       // int, value 300
  static_assert(std::is_same_v<decltype(s), int>);
  static_assert(std::is_same_v<decltype(+'x'), int>);
  static_assert(std::is_same_v<decltype(true + true), int>);
  static_assert(std::is_same_v<decltype(-a), int>);

  std::uint8_t x = 0;
  std::printf("%d\n", ~x == 0xFF);                  // 0: ~x is an int with value -1
  std::printf("%d\n", (std::uint8_t)~x == 0xFF);    // 1
  std::printf("%d\n", s);                           // 300
}
```

Built-in arithmetic operators do not operate on types narrower than `int`. When an integer type's [[g:integer-conversion-rank|integer conversion rank]] (the next section gives the full table) is lower than that of `int`, a prvalue of it is first converted to `int`; if `int` cannot hold all of its values, it is converted to `unsigned int` instead ([[conv.prom#2]]). This step is called [[g:integral-promotion|integral promotion]]. `bool` is promoted to `int`, with `false` becoming 0 and `true` becoming 1 ([[conv.prom#7]]).

So `uint8_t + uint8_t` yields an `int` and does not wrap at 255. `~x` also promotes first and then complements, giving 32 one-bits, the `int` value -1, which is not equal to `0xFF` (the `int` 255).

Promotion happens on the operands of every binary operator that uses the usual arithmetic conversions, the unary `+ - ~`, and the shift operators. One consequence causes the most trouble: narrow unsigned types become signed `int`.

```cpp run title="ushort.cpp" ub
#include <cstdint>
#include <cstdio>
std::uint16_t mul(std::uint16_t a, std::uint16_t b) {
  return a * b;                // both sides are promoted to int
}
int main() {
  std::printf("%u\n", mul(65535, 65535));   // UB: int overflow
}
```

Both operands are unsigned, yet the multiplication happens in `int`. 65535 × 65535 = 4294836225 exceeds the maximum of a 32-bit `int`; this is signed overflow. UBSan reports:

```text
ushort.cpp:4:12: runtime error: signed integer overflow: 65535 * 65535 cannot be represented in type 'int'
```

Writing `1u * a * b`, or `static_cast<unsigned>(a)` first, keeps the operation in an unsigned type.

The remaining cases briefly; details are on the [[conv.prom]] page:

- `char16_t`, `char32_t`, `wchar_t` and `char8_t` are promoted to the first type that can hold all values of their underlying type, trying `int`, `unsigned int`, `long`, ... in order ([[conv.prom#6]]).
- An unscoped enumeration whose underlying type is not fixed is promoted to the first type that can represent all its enumerator values, trying `int`, `unsigned int`, `long`, ... in order ([[conv.prom#3]]).
- A bit-field is promoted according to its own width ([[conv.prom#5]]): all values of `unsigned x : 4` fit in `int`, so it is promoted to `int`, and `s.x - 1` can be negative.

```cpp ok
#include <type_traits>
struct S { unsigned small : 4; unsigned long long big : 40; };
constexpr S s{};
static_assert(std::is_same_v<decltype(s.small + 0), int>);  // bit-field promoted to int
static_assert(s.small - 1 < 0);                             // 0 - 1 == -1
static_assert(std::is_same_v<decltype(s.big + 0), unsigned long long>);
constexpr unsigned u = 0;
static_assert(u - 1 > 0);                                   // plain unsigned: wraps
```

!!! pitfall "The signedness of `char` is implementation-defined"
    `char`, `signed char` and `unsigned char` are three distinct types, and the underlying type of `char` is one of the latter two, chosen by the implementation ([[basic.fundamental#7]]). On macOS arm64 `char` is signed: `char c = '\xE9';` has the value -23, and `c == 0xE9` is always false (Clang reports `-Wtautological-constant-out-of-range-compare`). When targeting aarch64 Linux, Clang predefines `__CHAR_UNSIGNED__`, and the same code gives 233. Use `unsigned char` or `std::byte` for byte data.

## Usual arithmetic conversions: a common type for two operands

When the two operands of `+ - * / % < == & | ^ ?:` and similar operators have different types, they are first converted to a common type, and the result usually has that type as well. These rules are called the [[g:usual-arithmetic-conversions|usual arithmetic conversions]] ([[expr.arith.conv]]). For two integer operands, both sides first undergo integral promotion, giving `T1` and `T2`, and then the following are checked in order ([[expr.arith.conv#1.5]]):

1. If `T1` and `T2` are the same, use it;
2. If both are signed or both unsigned, use the one with higher rank;
3. If one is signed (call it `S`) and the other unsigned (call it `U`):
    - If the rank of `U` is not lower than that of `S`, use `U`;
    - Otherwise, if `S` can represent all values of `U`, use `S`;
    - Otherwise, use the unsigned type corresponding to `S`.

Rank is defined by [[conv.rank#1]]. It depends only on the type; it is related to bit width but not the same thing:

| Rank (high to low) | Signed | Unsigned | LP64 width |
|---|---|---|---|
| 5 | `long long` | `unsigned long long` | 64 |
| 4 | `long` | `unsigned long` | 64 |
| 3 | `int` | `unsigned int` | 32 |
| 2 | `short` | `unsigned short` | 16 |
| 1 | `signed char` | `unsigned char` | 8 |
| Lowest | `bool` | | |

A character type has the same rank as its underlying type; at equal width, standard integer types rank higher than extended integer types. LP64 in the table is the data model of 64-bit Linux and macOS, where `long` and `long long` have the same width but different ranks.

When signed and unsigned are mixed, all three branches of step 3 occur, and the result depends on the platform:

```cpp ok
#include <type_traits>
using std::is_same_v;
static_assert(is_same_v<decltype(1 + 1u), unsigned>);
static_assert(is_same_v<decltype(1L + 1u), long>);                 // LP64
static_assert(is_same_v<decltype(1LL + 1UL), unsigned long long>); // LP64
static_assert(is_same_v<decltype((short)1 + (unsigned short)1), int>);
static_assert(-1L < 1u);       // common type long: true
static_assert(!(-1LL < 1UL));  // common type unsigned long long: false
static_assert(is_same_v<decltype(1 + 1.0f), float>);
static_assert(16777217 + 0.0f == 16777216.0f);
```

- `long` and `unsigned int`: `long` has higher rank and can hold all values of `unsigned int`, so the result is `long`, and `-1L < 1u` is true. On Windows, where `long` is only 32 bits, `long` cannot hold all values of `unsigned int`, the result becomes `unsigned long`, and the same comparison is false.
- `long long` and `unsigned long`: `long long` has higher rank, but on LP64 both are 64 bits, so it cannot hold them all, and the result is `unsigned long long`, a type neither operand was written in.

With a floating-point operand the rules are much simpler: the integer is always converted to the floating-point type, even if precision is lost ([[expr.arith.conv#1.4.2]]). `16777217 + 0.0f` equals `16777216.0f`, because `float` has only 24 significant bits. With two floating-point types, the one with higher rank wins; the rules for extended floating-point types come later.

The full algorithm, the rules for enumeration operands (since C++26, operations between different enumerations are ill-formed), and more platform differences are on the [[expr.arith.conv]] page.

## Integral conversions: always modular

```cpp run title="modular.cpp" ok
#include <cstdint>
#include <cstdio>
int main() {
  int big = 200, neg = -1;
  std::int8_t  a = big;             // 200 - 256 = -56
  std::uint8_t b = neg;             // -1 + 256 = 255
  unsigned     c = neg;             // 4294967295
  std::int32_t d = 3'000'000'000LL; // 3e9 - 2^32 = -1294967296
  std::printf("%d %d %u %d\n", a, b, c, d);
}
```

When an integer is converted to another integer type, the result is the unique value of the destination type that is congruent to the source value modulo 2<sup>N</sup>, where N is the [[g:integer-width|width]] of the destination type (the number of bits in its value representation) ([[conv.integral#3]]). For two's complement this simply keeps the low N bits.

Since C++20 this rule also applies to signed destination types. Before C++20, converting to a signed type a value that did not fit gave an implementation-defined result; [[P0907R4]] and [[P1236R1]] specified that signed integers use two's complement representation ([[basic.fundamental#3]]), and conversion was accordingly defined as modular.

Integral conversions have no UB, but they often aren't what you want. Clang gives `-Wconstant-conversion` for constants (such as `d` above); for variables you need the `-Wconversion` family of warnings. At run time, `-fsanitize=implicit-conversion` catches implicit conversions that change the value. What it checks is not UB, so it is not part of `-fsanitize=undefined`:

```text
modular.cpp:5:20: runtime error: implicit conversion from type 'int' of value 200 (32-bit, signed) to type 'std::int8_t' (aka 'signed char') changed the value to -56 (8-bit, signed)
```

## Overflow: UB for signed, wraparound for unsigned

The two kinds of integer are treated completely differently when they go out of range:

- Arithmetic on unsigned types is performed modulo 2<sup>N</sup>; there is no overflow ([[basic.fundamental#2]]).
- For arithmetic on signed types, if the mathematical result is outside the range of representable values of the type, the behavior is undefined ([[expr.pre#4]]).

C++20 mandated two's complement representation, yet signed overflow is still UB, and this was deliberate. The compiler may assume overflow does not happen and simplify accordingly:

```cpp title="ovf.cpp"
bool next_is_bigger(int x)          { return x + 1 > x; }
bool next_is_bigger_u(unsigned x)   { return x + 1 > x; }
int  times2_div2(int x)             { return x * 2 / 2; }
unsigned times2_div2_u(unsigned x)  { return x * 2 / 2; }
```

Clang 23 targeting x86-64 at `-O2` produces:

```text
_Z14next_is_biggeri:          # int: returns true directly
        movb    $1, %al
        retq
_Z16next_is_bigger_uj:        # unsigned: false when x == UINT_MAX
        cmpl    $-1, %edi
        setne   %al
        retq
_Z11times2_div2i:             # int: returns x directly
        movl    %edi, %eax
        retq
_Z13times2_div2_uj:           # unsigned: must drop the top bit lost to wraparound
        movl    %edi, %eax
        andl    $2147483647, %eax
        retq
```

In the `int` versions, `x + 1 > x` is simplified to `true` and `x * 2 / 2` to `x`, because only executions without overflow are defined. The `unsigned` versions must keep the wraparound semantics and have a real comparison and a mask. With `-fwrapv` (which makes signed overflow wrap as two's complement), `next_is_bigger` becomes a comparison equivalent to `x != INT_MAX`.

Such simplifications can make the same program give different results at different optimization levels:

```cpp run title="ovfrun.cpp" ub
#include <climits>
#include <cstdio>
int main(int argc, char**) {
  int x = INT_MAX - 1 + argc;   // INT_MAX, known only at run time
  std::printf("%d\n", x + 1 > x);
}
```

In our tests `-O0` prints 0 (the hardware addition wraps to `INT_MIN`) and `-O2` prints 1. UBSan reports `signed integer overflow: 2147483647 + 1 cannot be represented in type 'int'`. So an overflow check that first computes `x + 1` and then tests whether it got smaller does not work; compare before the operation, or use `ckd_add`, described later.

Floating-point types are also subject to [[expr.pre#4]], but types conforming to IEEE 754 have ±∞ and NaN, so an overflowed result is still a value of the type and is not UB. Per Note 4 in [[expr.pre]], the only UB left for arithmetic expressions in that case is division by zero, covered later.

## Division, remainder and shifts

### Division truncates toward zero

```cpp run title="div.cpp" ok
#include <cstdio>
int floor_div(int a, int b) {           // rounds toward negative infinity
  int q = a / b, r = a % b;
  return (r != 0 && (r < 0) != (b < 0)) ? q - 1 : q;
}
int main() {
  std::printf("%d %d\n", 7 / 2, 7 % 2);       // 3 1
  std::printf("%d %d\n", -7 / 2, -7 % 2);     // -3 -1
  std::printf("%d %d\n", 7 / -2, 7 % -2);     // -3 1
  std::printf("%d %d\n", -7 >> 1, floor_div(-7, 2));  // -4 -4
  int n = -3;
  std::printf("%d\n", n % 2 == 1);            // 0: a negative odd number % 2 is -1
}
```

Integer division yields the algebraic quotient with any fractional part discarded, that is, truncation toward zero; `%` is defined by the identity `(a/b)*b + a%b == a` ([[expr.mul#4]]). Together, the remainder is either zero or has the same sign as the dividend. To test for odd, write `n % 2 != 0`; if you need floor division or a non-negative modulus, correct it yourself as `floor_div` above does.

[[expr.mul#4]] also specifies two kinds of UB: a zero divisor, and a quotient that cannot be represented in the result type. For two's complement `int` the latter has only one case, `INT_MIN / -1`, and `INT_MIN % -1` is UB as well. On arm64 in our tests, `INT_MIN / -1` gives `INT_MIN` with no error; x86-64's `idiv` instruction raises a hardware exception for it, which shows up as `SIGFPE` on Linux. More details are on the [[expr.mul]] page.

### Shifts

```cpp run title="shift.cpp" ok
#include <cstdint>
#include <cstdio>
int main() {
  std::printf("%d\n", 1 << 31);          // defined since C++20: -2147483648
  std::printf("%d\n", -1 << 3);          // defined since C++20: -8
  std::printf("%d\n", -9 >> 1);          // -5: rounds toward negative infinity
  std::uint8_t b = 0x81;
  std::printf("%d\n", b << 8);           // 33024: b is promoted to int first
}
```

Shifts do not use the usual arithmetic conversions: each operand undergoes integral promotion on its own, and the result has the type of the promoted left operand ([[expr.shift#1]]). So shifting a `uint8_t` left by 8 loses no bits; `1 << 40` is a shift of an `int` with a count exceeding the width, which is UB, and must be written `1LL << 40`.

Since C++20 the value of a shift is defined entirely mathematically ([[expr.shift#2]], [[expr.shift#3]]):

- `E1 << E2` is the value congruent to E1×2<sup>E2</sup> modulo 2<sup>N</sup>, where N is the width of the result type. So `1 << 31` equals `INT_MIN` and `-1 << 3` equals -8, both defined.
- `E1 >> E2` is E1/2<sup>E2</sup> rounded toward negative infinity, which for negative numbers is an arithmetic right shift.

Before that, left-shifting a negative number was UB and right-shifting one gave an implementation-defined result. Clang 23 still warns `-Wshift-negative-value` for `-1 << 3` under `-std=c++17`, and no longer under `-std=c++2c`.

The remaining UB concerns only the shift count: the right operand is negative, or not less than the width of the promoted left operand ([[expr.shift#1]]).

```cpp run title="shiftub.cpp" ub
#include <cstdint>
#include <cstdio>
int main(int argc, char**) {
  int n = 31 + argc;                     // 32
  std::uint32_t one = 1;
  std::printf("%u\n", one << n);         // UB: shift count equals the width
  std::printf("%d\n", 1 >> -argc);       // UB: negative shift count
}
```

```text
shiftub.cpp:6:27: runtime error: shift exponent 32 is too large for 32-bit type 'std::uint32_t' (aka 'unsigned int')
shiftub.cpp:7:25: runtime error: shift exponent -1 is negative
```

Without UBSan, the first line printed 1 instead of 0 in our tests: the shift instructions on both arm64 and x86-64 use only the low 5 bits of the count, so `1u << 32` actually executes as `1u << 0`. That is why such shifts are UB. When shifting by a variable amount, check `n < 32` first, or use `std::rotl` and `std::rotr` from `<bit>`, which are defined for any count.

## Brace initialization rejects narrowing

```cpp error
#include <cstdint>
#include <vector>
void f(double d, int i, long long ll) {
  int a = d;                    // OK: implicit truncation
  int b{d};                     // error: floating point to integer
  float c{d};                   // error: double to float, d is not a constant
  float c2{0.1};                // OK: constant, finite and no overflow (rounds)
  std::int8_t e{i};             // error: int to int8_t
  std::int8_t e2{100};          // OK: constant and fits
  std::int8_t e3{200};          // error: constant but doesn't fit
  unsigned u{-1};               // error
  double g{ll};                 // error: integer to floating point
  double g2{1LL << 53};         // OK: constant, round-trips exactly
  std::vector<int> v{1, 2, d};  // error: list elements are checked too
}
```

The conversions in the previous sections happen silently in `=` initialization, assignment and function argument passing. List-initialization (`T x{...}`, `T x = {...}`) is the exception: if any element requires a [[g:narrowing-conversion|narrowing conversion]], the program is ill-formed ([[dcl.init.list#3.9]]).

Narrowing conversions are defined in [[dcl.init.list#7]]; roughly, they are implicit conversions that may lose information:

| Conversion | When it is narrowing |
|---|---|
| Floating point → integer | Always |
| Floating point → lower-ranked floating point | The source is not a constant expression, or the constant's conversion overflows |
| Integer → floating point | The source is not a constant expression, or the constant's value does not round-trip exactly |
| Integer → integer that can't hold all values | The source is not a constant expression, or the constant's value after promotion does not fit |
| Pointer → `bool` | Always |

The exception for constants looks at the actual value: `int8_t e2{100}` is valid, `int8_t e3{200}` is ill-formed. `float c2{0.1}` is valid because the constant conversion only rounds and does not overflow.

For a truncation like `int a = d;`, Clang 23 gives no warning at all under `-Wall -Wextra`; you need `-Wconversion` (specifically its `-Wfloat-conversion`) for a diagnostic. Using brace initialization for arithmetic variables in new code turns this class of mistakes into compile errors.

## Safe alternatives

All the problems above have solutions in the standard library. What they have in common is that they compute with mathematical values rather than following C's conversion rules:

```cpp run title="safe.cpp" ok
#include <climits>
#include <cstdint>
#include <cstdio>
#include <numeric>
#include <stdckdint.h>
#include <utility>
int main() {
  std::printf("%d %d\n", -1 < 1u, std::cmp_less(-1, 1u));  // 0 1
  std::printf("%d %d\n", std::in_range<std::uint8_t>(300),
                         std::in_range<std::uint8_t>(255)); // 0 1

  std::printf("%d\n", std::saturating_add(INT_MAX, 1));     // 2147483647
  std::printf("%u\n", std::saturating_sub(2u, 5u));         // 0
  std::printf("%d\n", std::saturating_cast<std::int8_t>(300)); // 127

  int r;
  if (ckd_mul(&r, 65535, 65535))   // returns true on overflow
    std::puts("overflow");
}
```

| Tool | Header | Version | Purpose |
|---|---|---|---|
| `std::cmp_equal`, `cmp_less` and 4 more | `<utility>` | C++20 | Compare two integers by mathematical value, unaffected by signedness ([[utility.intcmp]]) |
| `std::in_range<R>(t)` | `<utility>` | C++20 | Whether the value of `t` is representable in `R` |
| `std::saturating_add`, `_sub`, `_mul`, `_div` | `<numeric>` | C++26 | Clamp to the maximum or minimum on overflow ([[numeric.sat.func]]) |
| `std::saturating_cast<R>(t)` | `<numeric>` | C++26 | Integer conversion that clamps when out of range ([[numeric.sat.cast]]) |
| `ckd_add`, `ckd_sub`, `ckd_mul` | `<stdckdint.h>` | C++26 | Compute the mathematical value, store the result modulo, return whether it overflowed ([[numerics.c.ckdint]]) |

A few easily overlooked details:

- The comparison functions come from [[P0586R2]]. They accept only signed or unsigned integer types; character types such as `char`, `bool` and `char8_t` are not allowed ([[utility.intcmp#11]]), and `std::cmp_less('a', 1)` fails to compile.
- The saturation functions come from [[P0543R3]]. The paper named them `add_sat`, `saturate_cast` and so on; the current draft renamed them to `saturating_add`, `saturating_cast`, and libc++ in our tests also provides the new names. Both parameters have the same type and no integral promotion happens: `saturating_add<std::int8_t>(100, 100)` is 127. See the [[numeric.sat]] page.
- `ckd_add` and friends are the C++ counterparts of C23's type-generic macros. The names are in the global namespace, and the types of the three operands are independent of one another, with no usual arithmetic conversions. See the [[numerics.c]] page.

## `size_t`, `ptrdiff_t` and `ssize`

The standard library uses `std::size_t` (unsigned) for sizes and `std::ptrdiff_t` (signed) for the difference between two pointers or iterators. Mixing them leads back to the opening problem:

```cpp
for (std::size_t i = v.size() - 1; i >= 0; --i) { }  // infinite loop: i >= 0 is always true
for (int i = 0; i < v.size(); ++i) { }               // -Wsign-compare
```

Clang 23 with `-Wall -Wextra` gives `-Wsign-compare` only for the second line; the infinite loop on the first line gets no warning. Two common fixes:

```cpp run title="ssize.cpp" ok
#include <cstddef>
#include <cstdio>
#include <iterator>
#include <type_traits>
#include <vector>
int main() {
  std::vector<int> v{1, 2, 3};
  static_assert(std::is_same_v<decltype(std::ssize(v)), std::ptrdiff_t>);
  static_assert(std::is_same_v<decltype(3uz), std::size_t>);

  for (auto i = std::ssize(v) - 1; i >= 0; --i)   // reverse order, i is signed
    std::printf("%d ", v[i]);
  for (std::size_t i = v.size(); i-- > 0; )        // unsigned: compare, then decrement
    std::printf("%d ", v[i]);
  std::puts("");
  for (auto i = 0uz; i < v.size(); ++i) { }        // uz: same type as size()
}
```

- C++20's `std::ssize(c)` ([[P1227R2]]) returns a signed size whose type is the wider of `ptrdiff_t` and the signed type corresponding to `c.size()`.
- C++23's literal suffixes `uz` and `z` ([[P0330R8]]) give `std::size_t` and its corresponding signed type, so `auto i = 0uz` no longer mixes signedness when compared with `size()`.

## Floating point: what the standard guarantees

The standard asks very little of floating point. The value sets of `float`, `double` and `long double` are nested in that order, with precision non-decreasing; beyond that, their representation and the precision of operations are implementation-defined ([[basic.fundamental#12]]). The standard does not require IEEE 754 (written ISO/IEC 60559 in the standard).

Nearly all real platforms use IEEE 754. A program can check `std::numeric_limits<T>::is_iec559` ([[numeric.limits.members#53]]); when it is `true`, `has_infinity`, `has_quiet_NaN` and so on must also be `true`. Code that relies on IEEE semantics can add a one-line `static_assert`:

```cpp run title="fp.cpp" ok
#include <bit>
#include <cfloat>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <limits>
int main() {
  static_assert(std::numeric_limits<double>::is_iec559);
  std::printf("%d\n", FLT_EVAL_METHOD);                       // 0
  std::printf("%#x\n", std::bit_cast<std::uint32_t>(1.0f));   // 0x3f800000
  std::printf("%#x\n", std::bit_cast<std::uint32_t>(-0.0f));  // 0x80000000

  double nz = -0.0;
  std::printf("%d %d\n", nz == 0.0, std::signbit(nz));        // 1 1

  double nan = std::numeric_limits<double>::quiet_NaN();
  std::printf("%d %d %d %d\n", nan == nan, nan != nan,
              nan < 1.0, nan >= 1.0);                          // 0 1 0 0
  std::printf("%.17g\n", 0.1 + 0.2);                           // 0.30000000000000004
}
```

`std::bit_cast<To>(from)` (C++20, [[P0476R2]]) reinterprets the bits of an object as another trivially copyable type of the same size ([[bit.cast]]), and is the correct way to inspect a floating-point representation; reading a member of another type through `reinterpret_cast` or a `union` is UB, see [[topics/type-punning]]. The output above shows that the IEEE binary32 encoding of `1.0f` is 0x3f800000 and that `-0.0f` has only the sign bit set.

### Excess precision and `FLT_EVAL_METHOD`

[[expr.pre#6]] allows floating-point operands and intermediate results to be represented with greater precision and range than the type requires, without changing the type; only casts and assignments must drop the extra precision. This exists for the 80-bit registers of x87. `FLT_EVAL_METHOD` in `<cfloat>` ([[cfloat.syn]]) reports what the implementation does: 0 means computing in the precision of the type itself. It is 0 on arm64 in our tests; modern x86-64 uses SSE2 by default and is usually 0 too; 32-bit x86 using x87 is usually 2, and the same expression can give different results on the two platforms.

Fusing `a * b + c` into a single FMA instruction also changes the rounded result. Clang controls this with `-ffp-contract=`; see the [[expr.pre]] page.

## NaN and -0.0

Two special values of IEEE 754 mean floating-point comparison is no longer a total order:

- NaN is unordered with every value, including itself: `==`, `<` and `>=` are all false, and only `!=` is true. `x != x` is the traditional NaN test; `std::isnan(x)` is clearer.
- `-0.0 == 0.0` is true, but the bits differ: `std::signbit` tells them apart, and under IEEE `1.0 / x` gives different infinities for them.

This property of NaN breaks the preconditions of standard algorithms. `std::sort` requires the comparison to be a strict weak ordering; sorting a sequence of `double` containing NaN with `<` violates that precondition, and the behavior is undefined. To sort arbitrary floating-point values, use C++20's `std::strong_order`, which gives IEEE 754's totalOrder: `-0.0` sorts before `0.0`, and NaNs go to the ends:

```cpp run title="total-order.cpp" ok
#include <algorithm>
#include <cmath>
#include <compare>
#include <cstdio>
#include <vector>
int main() {
  std::vector<double> v{3.0, NAN, 1.0, -0.0, 0.0, -INFINITY};
  std::ranges::sort(v, [](double a, double b) {
    return std::strong_order(a, b) < 0;
  });
  for (double d : v) std::printf("%g ", d);   // -inf -0 0 1 3 nan
}
```

!!! pitfall "Division by zero is UB even under IEEE 754"
    [[expr.mul#4]] says a zero divisor is UB, with no distinction between integer and floating point. IEEE 754 says `1.0 / 0.0` gives +∞, but by the standard it is still UB; Note 4 in [[expr.pre]] states explicitly that for IEEE types this is the only UB for arithmetic expressions. In our tests it gives `inf` at run time, `-fsanitize=undefined` does not report it, and only `-fsanitize=float-divide-by-zero` reports `division by zero`; `constexpr double x = 1.0 / 0.0;` is rejected. When you need infinity, use `std::numeric_limits<double>::infinity()`.

## Conversions between floating point and integers

Conversions between integer types always wrap, but floating point to integer does not:

```cpp run title="f2i.cpp" ub
#include <cstdio>
int main(int argc, char**) {
  double big = 3e9 * argc;
  double neg = -1.0 * argc;
  std::printf("%d\n", (int)big);        // UB: 3e9 exceeds int
  std::printf("%u\n", (unsigned)neg);   // UB: -1 is outside unsigned
  std::printf("%d\n", (int)-2.7);       // -2: truncates toward zero, OK
}
```

When a floating-point value is converted to an integer, the fractional part is truncated first; if the truncated value cannot be represented in the destination type, the behavior is undefined ([[conv.fpint#1]]). `(unsigned)-1.0` is included: -1 is not in the range of `unsigned`, and there is no wrapping as there is for integral conversions. Values that are in range after truncation are fine: `(unsigned)-0.5` truncates to 0 and is valid.

On arm64 without sanitizers, our tests print 2147483647 and 0, because the `fcvtzs` and `fcvtzu` instructions saturate; x86-64's `cvttsd2si` gives 0x80000000 for out-of-range values. Making the rule UB lets compilers use the hardware instructions directly. `-fsanitize=float-cast-overflow` (included in `undefined`) reports:

```text
f2i.cpp:5:28: runtime error: 3e+09 is outside the range of representable values of type 'int'
f2i.cpp:6:33: runtime error: -1 is outside the range of representable values of type 'unsigned int'
```

In the other direction, when an integer is converted to floating point and the value is in range but not exactly representable, the result is one of the two adjacent representable values, chosen in an implementation-defined way ([[conv.fpint#2]]). `float f = 16777217;` gives 16777216 or 16777218; the usual round-to-nearest gives the former. Conversions between floating-point types from higher to lower precision follow the same rule ([[conv.double#2]]). The remaining details of these conversions are on the [[conv]] page.

## `-ffast-math`

`-ffast-math` makes the compiler give up several IEEE 754 guarantees in exchange for freedom to reorder and vectorize. Its component `-ffinite-math-only` lets the compiler assume there are no NaNs or infinities, with the consequence that code checking for NaN stops working:

```cpp title="fast.cpp"
#include <cmath>
bool is_nan(double x)  { return std::isnan(x); }
bool self_ne(double x) { return x != x; }
```

With Clang 23 and `-O2 -ffast-math`, both functions compile to simply returning 0, even when passed a NaN, and with no warning at all. Another component, `-fassociative-math`, allows floating-point additions to be reordered by associativity, so a sum can change with optimization.

The option applies to the whole translation unit and changes predefined macros such as `__FAST_MATH__`. Use it only when you are sure the code does not rely on NaN, infinities, signed zero and exact rounding; code that needs to check its input for NaN belongs in a file compiled without it.

## Floating point at compile time

Constant evaluation does not allow UB ([[expr.const.core#2.8]]), and this rule turns all the out-of-range cases above into compile errors: division by zero, `INT_MIN / -1`, signed overflow, out-of-range shifts, and out-of-range floating-to-integer conversion.

Floating point has one additional rule. In the current draft, [[expr.const.core#2.9]] says the following three kinds of arithmetic expression are not core constant expressions, even though they have well-defined results under IEEE 754:

- All operands are finite, but the result is not (overflow to ∞);
- An operand is a signaling NaN;
- No operand is a NaN, but the result is (such as `inf - inf`).

In other words, existing infinities and quiet NaNs can take part in operations and propagate at compile time, but they cannot be produced from nothing.

```cpp
#include <limits>
using L = std::numeric_limits<double>;
constexpr double inf  = L::infinity();       // OK
constexpr double nan  = L::quiet_NaN();      // OK
constexpr double inf2 = inf * 2;             // OK: the operand is already infinite
constexpr double nan2 = nan + 1;             // OK: propagates NaN (Clang rejects)
constexpr double tiny = L::min() / L::max(); // OK: underflow rounds to 0
constexpr double oflo = L::max() * 2;        // error: finite operands give ∞ (Clang accepts)
constexpr double bad  = inf - inf;           // error: NaN from non-NaN operands
constexpr int    trunc = (int)1e10;          // error: doesn't fit after conversion, UB
static_assert(0.1 + 0.2 != 0.3);             // OK: rounding to double at compile time too
```

This snippet carries no verdict marker because Clang 23 differs from the current draft in two places: it rejects `nan2`, treating every operation that produces a NaN as non-constant; and it accepts `oflo`, letting constant evaluation overflow to ∞. The other lines behave as the draft says. This rule is fairly recent wording; don't rely on these edge cases when writing compile-time floating-point code.

Compile-time floating-point operations round to the precision of the type itself, so `0.1 + 0.2 != 0.3` holds at compile time as well. But if there is excess precision at run time or `-ffast-math` is on, the same expression can give different results at compile time and at run time.

## Extended floating-point types {{c++23}}

C++23's [[P1467R9]] allows implementations to provide [[g:extended-floating-point-type|extended floating-point types]], and specifies standard names in `<stdfloat>` for the common formats ([[basic.extended.fp]]): `std::float16_t`, `std::float32_t`, `std::float64_t` and `std::float128_t` correspond to IEEE binary16/32/64/128, and `std::bfloat16_t` is the format with 8 bits of precision commonly used in machine learning. All of them are optional and are detected with macros such as `__STDCPP_FLOAT16_T__`.

The conversion and arithmetic rules for these types are built on the [[g:floating-point-conversion-rank|floating-point conversion rank]] ([[conv.rank#2]]): a type whose value set is a proper subset of another's has lower rank; types with the same value set have equal rank and are distinguished by subrank, with `std::floatN_t` having a higher subrank than a standard type of equal rank ([[conv.rank#3]]). It follows that:

- Implicit conversion is only allowed to a type whose rank is not lower than the source's ([[conv.double#1]]). Standard types are an exception for C compatibility: `double` can still be implicitly converted to `float`.
- With two floating-point operands, the higher rank wins; with equal rank, the higher subrank wins; if the ranks are unordered, the program is ill-formed ([[expr.arith.conv#1.4]]).

```cpp
#include <stdfloat>
std::float16_t a = 1.0f16;                           // OK
std::float16_t b = 1.0;                              // error: double → float16_t lowers the rank
std::float16_t c = static_cast<std::float16_t>(1.0); // OK: explicit conversion
auto d = std::float16_t(1) + 1.0f;                   // float
auto e = std::float32_t(1) + 1.0f;                   // std::float32_t: equal rank, higher subrank
auto f = std::bfloat16_t(1) + std::float16_t(1);     // error: ranks unordered
```

This snippet carries no verdict marker: libc++ in our tests does not provide `<stdfloat>`, and Clang does not define `__STDCPP_FLOAT16_T__` and the like, so it could not be verified locally; the conclusions come directly from the clauses cited above. `bfloat16` has a larger range and lower precision than binary16, so neither value set contains the other, and their ranks are unordered.

!!! impl "Clang's `_Float16` is not an extended floating-point type"
    Clang 23 supports C's `_Float16` but does not define it as an extended floating-point type in the standard's sense (Note 8 in [[basic.fundamental#12]] permits this). It does not follow the rules above: `_Float16 h = 1.0;` compiles, and the type of `h + 1.0f` is `float`.

## Common misconceptions

!!! pitfall "Using unsigned types for quantities that can't be negative is safer"
    Unsigned types don't overflow, but `a - b` silently wraps to a huge positive number when `a < b`, `i >= 0` is always true, and in a comparison with a signed value the other side gets converted too. Using signed types for indices and counts, and converting only when interacting with `size()`, is less error-prone; use unsigned types only when you need bit operations and modular semantics.

!!! pitfall "`-fwrapv` makes signed overflow legal"
    `-fwrapv` makes Clang and GCC wrap as two's complement, but by the standard the program still has UB, and it will break with another compiler or without the option. It is suitable as a safety net for existing code, not as a substitute for correct overflow checks.

!!! pitfall "The result of `std::abs` is always non-negative"
    The integer versions of `std::abs` keep the semantics of the C library ([[c.math.abs#2]]): if the result cannot be represented, the behavior is undefined, so `std::abs(INT_MIN)` is UB.

## Questions

!!! question "Question 1"
    Let `unsigned short a = 1; int b = -2;`. What is the value of `a + b > 0`? What if the type of `a` is changed to `unsigned int`?

<details markdown="1">
<summary>Answer</summary>

In the first case it is false. `unsigned short` is first promoted to `int` ([[conv.prom#2]]), both sides are `int`, `1 + (-2) == -1`, and `-1 > 0` is false.

With `unsigned int` it is true. `unsigned int` and `int` have the same rank, so by [[expr.arith.conv#1.5.3.1]] the common type is `unsigned int`; `b` converts to 4294967294, the sum is 4294967295, which is greater than 0. The result of the same expression depends on whether the operand is narrower than `int`.
</details>

!!! question "Question 2"
    Is `std::int8_t x = 127; ++x;` UB? What about `int x = INT_MAX; ++x;`?

<details markdown="1">
<summary>Answer</summary>

The first is not UB. `++x` is equivalent to `x += 1`, that is, `x = x + 1`: `x` is first promoted to `int`, and `127 + 1 == 128` does not overflow in `int`; on assignment, 128 is converted back to `int8_t`, which by [[conv.integral#3]] wraps to -128. Since C++20 this result is fully specified.

The second is UB. The addition happens in `int`, and the mathematical result 2<sup>31</sup> cannot be represented in `int` ([[expr.pre#4]]).
</details>

!!! question "Question 3"
    `double d = 4294967295.0;`. Which of `(unsigned)d` and `(int)d` is defined? What about `(unsigned)(long long)d`?

<details markdown="1">
<summary>Answer</summary>

`(unsigned)d` is defined and gives 4294967295, which is within the range of a 32-bit `unsigned`. `(int)d` is UB: the truncated value is outside the range of `int` ([[conv.fpint#1]]).

`(unsigned)(long long)d` is defined: the floating-to-`long long` conversion is in range, and what follows is a conversion between integer types, which always wraps. Converting first to a sufficiently wide integer and then narrowing is a common way to avoid the floating-to-integer UB, provided the first step is in range.
</details>

## Summary

| Situation | Verdict | Basis |
|---|---|---|
| Narrow integers in arithmetic | Promoted to `int` first (which may cause signed overflow) | [[conv.prom]] |
| Mixing signed and unsigned | Usually converted to unsigned; result depends on the platform | [[expr.arith.conv]] |
| Out-of-range integral conversion | Wraps; defined since C++20 | [[conv.integral]] |
| Signed arithmetic overflow | {{ub}} | [[expr.pre#4]] |
| Unsigned arithmetic out of range | Wraps modulo 2<sup>N</sup> | [[basic.fundamental#2]] |
| Division by zero, `INT_MIN / -1` | {{ub}} (floating-point division by zero too) | [[expr.mul#4]] |
| Shift count negative or not less than the width | {{ub}} | [[expr.shift#1]] |
| Left- or right-shifting a negative number | Defined since C++20 | [[expr.shift]] |
| Narrowing in brace initialization | {{ill-formed}} | [[dcl.init.list#3.9]] |
| Out-of-range floating-to-integer conversion | {{ub}} | [[conv.fpint#1]] |
| Integer-to-floating conversion not exactly representable | One of the adjacent values, {{impl}} | [[conv.fpint#2]] |
| Producing ∞ or NaN from nothing during constant evaluation | Not a constant expression | [[expr.const.core#2.9]] |
