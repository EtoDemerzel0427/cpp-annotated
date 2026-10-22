---
title: Integer literals
summary: "The four bases of integer literals, digit separators and the u/l/ll/z suffixes, and how the type is determined: the first type in the candidate list that can represent the value, where decimal and non-decimal literals have different candidate lists."
updated: 2026-10-19
---

!!! tldr
    - Integer literals can be written in binary, octal, decimal or hexadecimal; a multi-digit number starting with `0` is octal, so `010 == 8` and `09` is ill-formed.
    - The type of a literal is the first type in the candidate list for its suffix that can represent its value.
    - A decimal literal without `u` always has a signed type; the candidates for hexadecimal, octal and binary literals alternate between signed and unsigned, so `0x80000000` is `unsigned int`.
    - `-2147483648` is the negation of `2147483648` and its type is not `int`, so `INT_MIN` has to be written `(-2147483647 - 1)`.
    - The C++23 suffix `uz` gives `std::size_t`, and `z` gives its corresponding signed type.

## Four ways to write them

```cpp run title="icon-forms.cpp" ok
static_assert(12 == 014 && 12 == 0XC && 12 == 0b1100);
static_assert(1048576 == 1'048'576 && 1048576 == 0x10'0000
           && 1048576 == 0'004'000'000);   // the last one is octal
static_assert(1'0'0 == 100);               // any grouping is allowed
static_assert(0 == 00 && 010 == 8);
int main() {}
```

The prefix determines the base: `0b` or `0B` is binary, `0x` or `0X` is hexadecimal, a leading `0` is octal, and a leading nonzero digit is decimal. Since a decimal literal must begin with a nonzero digit, a lone `0` is grammatically an octal literal, though this has no practical effect at all.

A single quote `'` can be inserted between digits as a **digit separator**; its position and the grouping are unrestricted, but it can only appear between two digits.

¶1 The value of a literal is the digit sequence interpreted as an integer in its base, with the lexically first digit being the most significant; prefixes and separators do not affect the value. ¶2 The hexadecimal digits `a`–`f` (or `A`–`F`) have the values 10 through 15. What results is an integer in the mathematical sense, with no type yet, so overflow does not arise.

```cpp title="icon-bad.cpp" error
int a = 09;      // error: there is no 9 in octal
int b = 0x'1;    // error: ' cannot immediately follow the prefix
int c = 0b;      // error: 0b must be followed by at least one binary digit
int d = 1lL;     // error: both letters of ll must have the same case
int e = 1zl;     // error: z cannot be combined with l
```

There are four suffix letters: `u` for unsigned, `l` for long, `ll` for long long, and `z` for the size_t family. `u` can be combined with one of the other three in either order, and cases can be mixed (`1Ul` and `1lU` are both valid), but both letters of `ll` must have the same case.

## The type of a literal (¶3)

¶3 The type of an integer literal is the first type in the list in the table below, corresponding to its suffix, in which its value can be represented.

| Suffix | Decimal literal | Binary, octal or hexadecimal literal |
|---|---|---|
| none | `int`, `long`, `long long` | `int`, `unsigned int`, `long`, `unsigned long`, `long long`, `unsigned long long` |
| `u` | `unsigned int`, `unsigned long`, `unsigned long long` | same as left |
| `l` | `long`, `long long` | `long`, `unsigned long`, `long long`, `unsigned long long` |
| `u` + `l` | `unsigned long`, `unsigned long long` | same as left |
| `ll` | `long long` | `long long`, `unsigned long long` |
| `u` + `ll` | `unsigned long long` | same as left |
| `z` | the signed type corresponding to `std::size_t` | the signed type corresponding to `std::size_t`, `std::size_t` |
| `u` + `z` | `std::size_t` | same as left |

The difference between the columns: the candidates for a decimal literal without `u` are all signed types, while the candidates for non-decimal literals alternate between signed and unsigned.

This design reflects the different uses of the two notations. Decimal usually expresses a quantity and should stay signed. Hexadecimal, octal and binary usually express bit patterns, such as masks and flags. The intent of `0xFFFFFFFF` is 32 ones, and making it `unsigned int` matches that intent exactly; insisting on a signed type and putting it in `long` would be less appropriate.

The examples below assume an LP64 platform (64-bit Linux and macOS: `int` is 32 bits, `long` and `long long` are both 64 bits):

```cpp run title="icon-types.cpp" ok
#include <type_traits>
#include <cstddef>
template<class T, class U>
constexpr bool same = std::is_same_v<T, U>;
static_assert(same<decltype(2147483647), int>);
static_assert(same<decltype(2147483648), long>);       // decimal: unsigned is not tried
static_assert(same<decltype(0x7FFFFFFF), int>);
static_assert(same<decltype(0x80000000), unsigned>);   // hexadecimal: unsigned int is tried first
static_assert(same<decltype(0x100000000), long>);
static_assert(same<decltype(0x8000000000000000), unsigned long>);
static_assert(same<decltype(4294967296u), unsigned long>);
int main() {}
```

The same number written another way can have a different type, and the result of a comparison changes with it:

```cpp run title="sign-flip.cpp" ok
static_assert(-1 < 2147483648);      // comparison between longs: true
static_assert(!(-1 < 0x80000000));   // -1 converted to unsigned int is 4294967295: false
int main() {}
```

### Why `-2147483648` is not an `int`

Literals have no minus sign ([[lex.literal]]); `-2147483648` is the negation of the literal `2147483648`.

1. `2147483648` is outside the range of a 32-bit `int`, and the next candidate for an unsuffixed decimal literal is `long`.
2. On an LP64 platform `long` is 64 bits, so the literal is a `long`, and negating it gives −2147483648 of type `long`. On 64-bit Windows `long` is only 32 bits, and the result is `long long`.
3. C89's decimal candidate list was `int`, `long`, `unsigned long`. On a platform with 32-bit `long`, `2147483648` would fall into `unsigned long`, and negating it would still give the positive number 2147483648.

So `<climits>` typically defines `INT_MIN` as `(-2147483647 - 1)`: the difference of two `int`s, whose result is an `int`.

```cpp run title="neg-literal.cpp" ok
#include <climits>
#include <type_traits>
static_assert(!std::is_same_v<decltype(-2147483648), int>);
static_assert(std::is_same_v<decltype(INT_MIN), int>);
int main() {}
```

C++98's decimal candidate list was only `int` and `long`, with undefined behavior beyond `long`. C++11 added `long long` for compatibility with C99, making the list `int`, `long`, `long long`. [[diff.cpp03.lex]] records a consequence of this change: certain literals larger than `long` could change from an unsigned integer type to `long long`.

### The `z` suffix {{c++23}}

The `uz` (or `zu`) suffix gives `std::size_t`, and `z` gives the signed integer type corresponding to `std::size_t`, which on mainstream platforms is `std::ptrdiff_t` ([[P0330R8]]). It solves the problem of the type of loop variables:

```cpp run title="uz.cpp" ok
#include <vector>
int main() {
  std::vector<int> v{1, 2, 3};
  for (auto i = 0uz; i < v.size(); ++i) {}  // i is std::size_t
  // auto i = 0 would make i an int,
  // triggering -Wsign-compare when compared with v.size()
}
```

`std::size_t` itself is a type alias in the standard library ([[support.types.layout]]), referenced directly by the lexical rules here, so the exact type of such literals depends on the implementation's choice of `size_t`.

## Literals that do not fit (¶4)

¶4 If the value of a literal is outside the range of every type in its candidate list, and some **extended integer type** (an additional integer type provided by the implementation, see [[basic.fundamental]]) can represent it, the literal may have that extended integer type. If all the types in the list are signed, the extended type is signed; if all are unsigned, it is unsigned; if the list has both, it may be either. Literals with a `z` suffix are excluded from this rule.

If not even an extended integer type can represent it, the program is ill-formed. Note 2 points out specifically that a literal with a `z` suffix is ill-formed if it does not fit in `std::size_t`.

```cpp title="icon-too-big.cpp" error
auto a = 18446744073709551616;  // error: beyond 64 bits
auto b = 9223372036854775808;   // unsuffixed decimal, does not fit in long long: ill-formed
```

!!! impl "Current implementations"
    None of the mainstream implementations treats `__int128` as an extended integer type in the standard's sense; otherwise `std::intmax_t` would have to grow to 128 bits, breaking the existing ABI. So the extended-integer-type branch of ¶4 never actually occurs.

    For `a`, Clang 23 reports the error "integer literal is too large to be represented in any integer type". For `b`, it gives only a `-Wimplicitly-unsigned-literal` warning and continues compiling with the literal as `unsigned long long`. Per the standard `b` is ill-formed, but the warning already satisfies the diagnostic requirement, and continuing to compile afterwards is an extension ([[intro.compliance]]).

    For the same reason, `LLONG_MIN` cannot be written `-9223372036854775808`; `<climits>` uses `(-LLONG_MAX - 1)`.

## History and evolution

!!! history
    | Version | Change |
    |---|---|
    | C++98 | Octal, decimal and hexadecimal; suffixes `u` and `l`; undefined behavior when an unsuffixed decimal value exceeds `long` |
    | C++11 | `long long` and the `ll` suffix; the unsuffixed decimal list contains only signed types; the extended integer type rule |
    | C++14 | Binary literals `0b` ([[N3472]]); the digit separator `'` ([[N3781]]) |
    | C++23 | The `z` and `uz` suffixes ([[P0330R8]]) |

    The digit separator did not use `_`, common in other languages, because suffixes beginning with `_` already belonged to user-defined literals: `1_000` would be parsed as the literal `1` with the suffix `_000`. The price of choosing `'` is that the splitting of macro arguments changes in a few cases; [[diff.cpp11.lex]] gives an example.

## Common misconceptions

!!! pitfall "Leading zeros are just formatting"
    `int month = 08;` is ill-formed, and `int code = 010;` has the value 8. Take special care when copying numbers from spreadsheets or configuration files.

!!! pitfall "Hexadecimal and decimal spellings have the same type"
    `0xFFFFFFFF` is `unsigned int`, while `4294967295` is `long` on LP64. With three overloads `f(int)`, `f(unsigned)` and `f(long)`, they pick different functions, and comparisons with negative numbers give opposite results.

!!! pitfall "`1 << 40` gives 2⁴⁰"
    `1` is an `int`, and shifting by at least the width of `int` is undefined behavior ([[expr.shift]]). For a 64-bit result, write `1ull << 40` or `std::uint64_t{1} << 40`.

## Questions

!!! question "Question 1"
    On an LP64 platform, what are the types of `0xFFFFFFFFFFFFFFFF`, `18446744073709551615u` and `-0x1`?

<details markdown="1">
<summary>Answer</summary>

- `0xFFFFFFFFFFFFFFFF`: non-decimal with no suffix; `int`, `unsigned int` and `long` cannot hold it, `unsigned long` just can, so it is `unsigned long`.
- `18446744073709551615u`: `u` suffix; `unsigned int` cannot hold it, `unsigned long` can, so it is `unsigned long`.
- `-0x1`: `0x1` is an `int`, and negating it still gives an `int`, with value −1.
</details>

!!! question "Question 2"
    Why does the extended integer type rule of ¶4 not apply to literals with a `z` suffix?

<details markdown="1">
<summary>Answer</summary>

The whole point of `z` and `uz` is to get `size_t` or its signed counterpart. If a value that is too large silently switched to a wider extended type, `auto i = ...uz;` would no longer be a `size_t`, and the suffix would lose its meaning. So the standard makes it ill-formed outright (Note 2).
</details>
