---
title: Usual arithmetic conversions
summary: How binary arithmetic, comparison, bitwise and conditional operators bring two arithmetic or enumeration operands to a common type.
updated: 2026-10-19
---

!!! tldr
    - Before two arithmetic or enumeration operands take part in `+`, `<`, `&`, `?:` and so on, they are converted to a common type by a fixed five-step algorithm; that type is usually also the result type.
    - If there is a floating-point operand, the integer is always converted to floating point, even if precision is lost; of two floating-point types, the one with the higher rank wins.
    - If both are integers, integral promotions come first; when the signs differ and the unsigned type's rank is not lower than the signed type's, the result is the unsigned type, so `-1 < 0u` is false.
    - Narrow unsigned types (`unsigned short`, `uint16_t`) are first promoted to signed `int`, so even their multiplication can overflow as signed.
    - Since C++26, operations between different enumerations, and between an enumeration and a floating-point type, are ill-formed; a scoped enumeration can only be used with an operand of the same type.

```cpp run ok
#include <cstdio>
int main() {
  std::printf("%d\n", -1 < 0u);   // 0
  std::printf("%d\n", -1 < 0L);   // 1
}
```

`-1 < 0u` is false. Before the comparison, both operands are converted to the same type; the common type of `int` and `unsigned int` is `unsigned int`, so `-1` becomes `UINT_MAX`. The rules that decide this common type are called the **usual arithmetic conversions** ([[g:usual-arithmetic-conversions|usual arithmetic conversions]]).

## Which operators use it

| Operator | Subclause | Notes |
|---|---|---|
| `*` `/` `%` | [[expr.mul]] | |
| `+` `-` | [[expr.add]] | Not when one side is a pointer |
| `<` `>` `<=` `>=` `==` `!=` | [[expr.rel]], [[expr.eq]] | The result is `bool`; the common type is used only for the comparison |
| `<=>` | [[expr.spaceship]] | Also forbids narrowing (except integer to floating point) |
| `&` `^` `\|` | [[expr.bit.and]] etc. | |
| `?:` | [[expr.cond]] | When the second and third operands both have arithmetic or enumeration type |
| `+=` and other compound assignments | [[expr.assign]] | Evaluated as `E1 = E1 op E2` |

The shift operators `<<` and `>>` don't use it: each operand undergoes integral promotion separately, and the result type is the type of the promoted left operand ([[expr.shift]]). Unary operators only apply integral promotions, and the logical operators contextually convert their operands to `bool`.

## The five-step algorithm

¶1 The algorithm checks five cases in order; the first one that applies determines the result.

### Step 1: read the values

¶1.1 First the lvalue-to-rvalue conversion ([[conv.lval]]) is applied to both operands; the remaining steps only deal with the resulting prvalues.

### Step 2: scoped enumerations

¶1.2 If either operand has scoped enumeration type (`enum class`, [[dcl.enum]]), no conversion is performed; the other operand must have the same type, otherwise the expression is ill-formed.

```cpp error
enum class Color { red, green };
bool c1 = Color::red == Color::green;  // OK: same type
bool c2 = Color::red == 0;             // error: different types
auto c3 = Color::red + Color::red;     // error: + doesn't accept scoped enumerations
```

`c3` passes this step, but [[expr.add]] itself requires arithmetic or unscoped enumeration operands, so it is still ill-formed.

### Step 3: an enumeration with another enumeration or a floating-point type {{c++26}}

¶1.3 If one operand has enumeration type and the other has a different enumeration type or a floating-point type, the expression is ill-formed.

```cpp error
enum A { a1 };
enum B { b1 };

auto x1 = a1 + b1;         // error: different enumeration types
bool x2 = a1 == b1;        // error: comparisons too
auto x3 = a1 | b1;         // error: bitwise operators too
auto x4 = a1 + 1.0;        // error: enumeration and floating point
auto x5 = true ? a1 : b1;  // error: the conditional operator too

auto ok1 = a1 + 1;         // OK: enumeration and integer
auto ok2 = a1 | a1;        // OK: same enumeration type, result is int
auto ok3 = +a1 + +b1;      // OK: unary + promotes to int first
```

An operation between two unrelated enumerations is almost always a mistake, such as OR-ing file modes with permission bits; mixing an enumeration with floating point has no sensible meaning either. When you really need it, state the intent with unary `+` or `static_cast<int>`.

Two operands of the same enumeration type, and an enumeration combined with an integer, are unaffected, so code that uses unscoped enumerations as bit flags (`flags | FLAG_A`) still compiles.

!!! history "From deprecation to removal"
    Up to C++17 these operations were all valid: the enumeration was first promoted and then converted by the integer rules. C++20 deprecated them through [[P1120R0]], and Clang warns with `-Wdeprecated-enum-enum-conversion`, `-Wdeprecated-enum-float-conversion` etc. under `-std=c++20`. C++26 removed them through [[P2864R2]] ({{removed:C++26}}); Clang 23 rejects everything in the example above under `-std=c++2c`.

### Step 4: a floating-point operand

¶1.4 If either operand has floating-point type:

- ¶1.4.1 If both have the same type, no further conversion is needed.
- ¶1.4.2 If one is not a floating-point type (an integer or unscoped enumeration), it is converted to the floating-point type of the other operand.
- ¶1.4.3 If the two **floating-point conversion ranks** ([[conv.rank#2]]) differ and are ordered, the one with the lower rank is converted to the type with the higher rank.
- ¶1.4.4 If the ranks are equal, the one with the lower **subrank** ([[conv.rank#3]]) is converted to the type with the higher subrank.
- ¶1.4.5 If the ranks are unordered, the expression is ill-formed.

With only `float`, `double` and `long double`, this rule just moves to the wider type. The last three bullets were written in C++23 when extended floating-point types were added ([[P1467R9]]): floating-point ranks are ordered by inclusion of value sets, and two types whose value sets don't contain each other have unordered ranks.

| Operands | Result type | Basis |
|---|---|---|
| `float` + `double` | `double` | Rank |
| `int` + `float` | `float` | ¶1.4.2, regardless of whether the `int` value is exactly representable |
| `std::float16_t` + `float` | `float` | The value set of float16 is a proper subset of float's |
| `std::float32_t` + `float` (same value set) | `std::float32_t` | Equal rank; `std::floatN_t` has the higher subrank |
| `std::float64_t` + `double` (same value set) | `std::float64_t` | Same as above |
| `std::bfloat16_t` + `std::float16_t` | Ill-formed | One has more range, the other more precision; the ranks are unordered |

```cpp
#include <stdfloat>
auto a = std::float16_t(1) + 1.0f;                  // float
auto b = std::float32_t(1) + 1.0f;                  // std::float32_t
auto c = std::bfloat16_t(1) + std::float16_t(1);    // error: ranks are unordered
```

This example has no verdict mark: the libc++ in our tests doesn't provide `<stdfloat>` yet, so it couldn't be verified locally; the conclusions come straight from [[conv.rank]] and the wording of this subclause.

!!! pitfall "`int` + `float` loses precision"
    ¶1.4.2 converts the integer to the floating-point type unconditionally: `16777217 + 0.0f` equals `16777216.0f`, because `float` has only 24 significant bits. Mixing `long long` with `float` loses even more.

### Step 5: two integers

¶1.5 The remaining case is that both operands are integers or unscoped enumerations. First, **integral promotion** ([[conv.prom]]) is applied to each operand, giving `T1` and `T2`. A footnote to this item points out that after promotion, `bool`, `char8_t`, `char16_t`, `char32_t`, `wchar_t` and enumerations have all become some integer type. Then the common type `C` is determined in this order:

- ¶1.5.1 If `T1` and `T2` are the same, `C` is that type.
- ¶1.5.2 If both are signed or both are unsigned, `C` is the one with the greater rank ([[conv.rank#1]]).
- ¶1.5.3 If one is signed (call it `S`) and one is unsigned (call it `U`):
    - ¶1.5.3.1 if the rank of `U` is not lower than that of `S`, `C` is `U`;
    - ¶1.5.3.2 otherwise, if `S` can represent all the values of `U`, `C` is `S`;
    - ¶1.5.3.3 otherwise, `C` is the unsigned type corresponding to `S`.

```text
        promote → T1, T2
                │
      same? ── yes ──→ C = T1
                │no
 same sign? ── yes ──→ C = higher rank
                │no (S and U)
rank(U) ≥ rank(S)? ── yes ──→ C = U
                │no
S represents all of U? ── yes ──→ C = S
                │no
                └──→ C = unsigned S
```

Integer widths are implementation-defined, so some results depend on the platform. The table below assumes LP64 (64-bit Linux and macOS: `int` is 32 bits, `long` and `long long` are 64 bits):

| Operands | After promotion | Rule | Result type |
|---|---|---|---|
| `short` + `short` | `int`, `int` | ¶1.5.1 | `int` |
| `unsigned short` + `int` | `int`, `int` | ¶1.5.1 | `int` |
| `char` + `bool` | `int`, `int` | ¶1.5.1 | `int` |
| `int` + `long` | unchanged | ¶1.5.2 | `long` |
| `int` + `unsigned` | unchanged | ¶1.5.3.1 | `unsigned` |
| `long` + `unsigned` | unchanged | ¶1.5.3.2: a 64-bit `long` can represent every 32-bit `unsigned` | `long` |
| `long` + `unsigned long` | unchanged | ¶1.5.3.1: equal rank | `unsigned long` |
| `long long` + `unsigned long` | unchanged | ¶1.5.3.3 | `unsigned long long` |

```cpp ok
#include <type_traits>
template<class A, class B> using R = decltype(A{} + B{});
static_assert(std::is_same_v<R<short, short>, int>);
static_assert(std::is_same_v<R<unsigned short, int>, int>);
static_assert(std::is_same_v<R<int, unsigned>, unsigned>);
static_assert(std::is_same_v<R<unsigned long, long long>, unsigned long long>);
#if __SIZEOF_LONG__ == 8 && __SIZEOF_INT__ == 4
static_assert(std::is_same_v<R<long, unsigned>, long>);   // LP64: ¶1.5.3.2
#endif
```

¶1.5.3.3 is used in only one situation: the signed type has the higher rank but can't hold all the values of the unsigned type. `long long` and `unsigned long` on LP64 are exactly that. The rank of `unsigned long` equals that of `long`, which is lower than `long long`, so ¶1.5.3.1 doesn't apply; both are 64 bits, so `long long` can't hold every `unsigned long` value and ¶1.5.3.2 doesn't apply either. The result is a third type, `unsigned long long`.

## Mixing signed and unsigned

¶1.5.3.1 is one of the most bug-prone rules in C and C++: when the ranks are equal, the signed type is converted to the unsigned type.

```cpp run title="sign.cpp" ok
#include <cstdio>
#include <utility>
#include <vector>

int main() {
  std::printf("%d\n", -1 < 0u);                 // 0
  std::printf("%d\n", -1L < 0u);                // 1 on LP64, 0 on LLP64
  std::printf("%d\n", -1 < (unsigned short)0);  // 1

  std::vector<int> v;
  std::printf("%zu\n", v.size() - 1);           // 18446744073709551615

  std::printf("%d\n", std::cmp_less(-1, 0u));   // 1
}
```

The second line depends on the platform. On LP64 `long` is 64 bits and can represent every `unsigned`, so by ¶1.5.3.2 the comparison happens in `long`; on Windows' LLP64 `long` is only 32 bits, so by ¶1.5.3.1 the comparison happens in `unsigned long`, and the result is 0.

The third line shows that narrow unsigned types are actually safe here: `unsigned short` is first promoted to signed `int`, and the comparison happens in `int`.

The fourth line is a common problem with container indices. `size()` returns an unsigned type; when `v` is empty, `v.size() - 1` wraps around to the maximum value, and `for (int i = 0; i < v.size() - 1; ++i)` keeps looping until it accesses out of bounds.

GCC's and Clang's `-Wsign-compare` catches most mixed-sign comparisons (GCC enables it in `-Wall` for C++, Clang in `-Wextra`), and `-Wsign-conversion` covers more implicit conversions. C++20's `<utility>` provides `std::cmp_less`, `std::cmp_equal` and friends, which compare integers of different signedness by their mathematical values; `std::in_range<T>(x)` checks whether `x` is representable in `T`.

!!! pitfall "Narrow unsigned types can overflow as signed"
    After `unsigned short a = 65535, b = 65535;`, computing `a * b` first promotes both operands to `int`, and the product 4294836225 exceeds the range of a 32-bit `int`: that is signed overflow, which is undefined behavior ([[expr.pre]]). UBSan reports `signed integer overflow`. The same goes for `uint16_t`. Safe forms are `1u * a * b` or `static_cast<unsigned>(a) * b`.

### Three-way comparison rejects mixed signs

After the usual arithmetic conversions, `<=>` additionally requires that the conversion is not narrowing (except integer to floating point), otherwise it is ill-formed ([[expr.spaceship]]). `int` to `unsigned` is narrowing, so a mixed-sign three-way comparison is simply an error:

```cpp error
#include <compare>
auto f(int i, unsigned u)        { return i <=> u; }  // error: int → unsigned is narrowing
auto g(unsigned short a, int b)  { return a <=> b; }  // OK: both are int after promotion
auto h(long long a, unsigned b)  { return a <=> b; }  // OK: unsigned → long long is not narrowing
```

!!! impl
    The usual arithmetic conversions are decided entirely at compile time and produce no runtime checks. What they affect is which instructions are generated: overflow of `int` is UB while `unsigned` wraps, so when an `int` is used as a loop index the compiler can widen it straight to a 64-bit address offset; with `unsigned` it must preserve the 32-bit wraparound semantics, which sometimes costs extra zero-extension instructions.

## History

!!! history
    The integer rules are inherited from C. ANSI C chose between two promotion schemes, unsigned-preserving and value-preserving, and picked the latter, which is why `unsigned short` promotes to `int` rather than `unsigned int`. When C++11 added `long long`, the rules were restated in terms of integer conversion rank ([[conv.rank]]) to accommodate extended integer types. C++20 deprecated arithmetic between different enumerations and between enumerations and floating point, and made `<=>` reject narrowing; C++23 added extended floating-point types and floating-point subranks; C++26 removed the deprecated enumeration operations.

## Questions

!!! question "1. On an LP64 platform, what is the type of `unsigned long` plus `long long`?"

<details markdown="1">
<summary>Answer</summary>

`unsigned long long`. Promotion leaves the types unchanged, the signs differ, `U` is `unsigned long`, and `S` is `long long`. The rank of `unsigned long` equals that of `long`, which is lower than `long long`, so ¶1.5.3.1 doesn't apply; a 64-bit `long long` can't represent all values of a 64-bit `unsigned long`, so ¶1.5.3.2 doesn't apply either. By ¶1.5.3.3, the result is the unsigned type corresponding to `long long`.
</details>

!!! question "2. Given `enum E { a }; enum F { b };`, `a == b` is ill-formed in C++26. What about `a == +b` and `static_cast<E>(b) == a`?"

<details markdown="1">
<summary>Answer</summary>

Both are well-formed. Unary `+` applies integral promotion to `b`, so `+b` is an `int`, and `a == +b` combines an enumeration with an integer, which doesn't trigger ¶1.3. In `static_cast<E>(b) == a` both operands have the same enumeration type, which doesn't trigger ¶1.3 either; both are promoted to `int` and then compared.
</details>

!!! question "3. In `char c = 'a'; auto d = c + c;`, what is the type of `d`? Does the signedness of `char` affect this type?"

<details markdown="1">
<summary>Answer</summary>

`d` is an `int`. As long as `int` is wider than `char`, `int` can represent all values of `char` whether or not `char` is signed, so by [[conv.prom#2]] it is always promoted to `int`, and ¶1.5.1 gives `int`. The signedness of `char` only affects the value (whether `'\xff'` is -1 or 255), not the type.
</details>
