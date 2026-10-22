---
title: Fundamental types
summary: "The built-in types: widths and two's complement representation of integer types, character types, bool, floating-point types and the optional extended floating-point types, void, std::nullptr_t and std::meta::info."
updated: 2026-10-19
---

!!! tldr
    - Since C++20, integers are always represented in two's complement, and conversions between signed and unsigned have determinate results; but signed arithmetic overflow is still UB, while unsigned arithmetic wraps modulo 2^N.
    - The widths of integer types are implementation-defined, with only lower bounds from the standard: `int` is at least 16 bits and `long` at least 32 bits. `long` is 64 bits on 64-bit Linux and 32 bits on 64-bit Windows.
    - `char`, `signed char` and `unsigned char` are three distinct types; whether `char` is signed depends on the platform.
    - Floating-point types are barely constrained: IEEE 754 is not required; only that every `float` value is a `double` value and every `double` value is a `long double` value. Extended floating-point types such as `std::float32_t` are optional, and are distinct types from `float`.
    - Even if two fundamental types have exactly the same representation (like `int` and `long` on Windows), they are still distinct types.

**Fundamental types** are the types built into the language and not constructed from other types: integers, characters, `bool`, floating-point, `void`, `std::nullptr_t`, and `std::meta::info`, new in C++26 (¶19). This page covers 6.9.3 [[basic.fundamental]], and 6.9.4 [[basic.extended.fp]], which specifies optional floating-point types like `std::float16_t`.

Other integer-related rules are in conversion ranks [[conv.rank]], integral promotions [[conv.prom]], the usual arithmetic conversions [[expr.arith.conv]] and integral conversions [[conv.integral]]; the range of each type can be queried with `<limits>` ([[numeric.limits]]).

## Integer types

### Five signed integer types (¶1, ¶4)

¶1 There are five **standard signed integer types**: `signed char`, `short int`, `int`, `long int` and `long long int`. Each type in the list provides at least as much storage as those preceding it. An implementation may also provide **extended signed integer types**. Together they are the **signed integer types**.

The range of representable values of a signed integer type is −2^(N−1) to 2^(N−1)−1, where N is called the **width** of the type. This is exactly the two's complement range. Before C++20 the standard also allowed ones' complement and sign-magnitude, whose ranges are symmetric and which have a negative zero.

¶4 The width of each standard signed integer type shall not be less than the value in Table 14; beyond that it is up to the implementation. The table below also lists actual widths under common data models:

| Type | Minimum width | ILP32 (32-bit systems) | LP64 (64-bit Linux, macOS) | LLP64 (64-bit Windows) |
|---|---|---|---|---|
| `signed char` | 8 | 8 | 8 | 8 |
| `short` | 16 | 16 | 16 | 16 |
| `int` | 16 | 32 | 32 | 32 |
| `long` | 32 | 32 | 64 | 32 |
| `long long` | 64 | 64 | 64 | 64 |
| pointers | — | 32 | 64 | 64 |

The lower bound for `int` is 16 bits, not 32. When an exact width is needed, use types like `std::int32_t` from `<cstdint>` ([[cstdint.syn]]). The difference in `long` between LP64 and LLP64 is the most common source of trouble in cross-platform code.

!!! lawyer "Is width monotonic too?"
    ¶1 only says storage (`sizeof`) does not decrease; it does not directly say width does not decrease. But [[conv.rank#1.2]] says a signed type of smaller width has lower rank, and [[conv.rank#1.3]] says `long long`, `long`, `int`, `short` and `signed char` have successively lower ranks. If an implementation made `int` wider than `long`, the first rule would give `int` a higher rank than `long`, contradicting the second. So monotonic width is a consequence of these two rules together.

### Unsigned types and modular arithmetic (¶2)

¶2 For each signed integer type there is a corresponding, distinct unsigned integer type: `unsigned char`, `unsigned short`, `unsigned int`, `unsigned long` and `unsigned long long`, and each extended signed integer type has a corresponding extended unsigned integer type. An unsigned type has the same width N as its corresponding signed type, its range is 0 to 2^N−1, and arithmetic is performed modulo 2^N.

```cpp run ub
#include <climits>

int main() {
  unsigned u = UINT_MAX;
  u = u + 1;            // OK: modulo 2^N, the result is 0
  int i = INT_MAX;
  i = i + 1;            // UB: signed overflow
  return u + i;
}
```

Note 1 points out the asymmetry: unsigned arithmetic does not overflow, the result is always reduced modulo; signed overflow is undefined behavior ([[expr.pre]]). C++20's move to two's complement did not change this. The UB is kept because compilers rely on it for optimizations, such as assuming that `i + 1 > i` always holds for a loop variable. Running the program above with `-fsanitize=undefined`, UBSan reports `signed integer overflow`.

### Signed and unsigned share their representation (¶3, ¶5)

¶3 An unsigned type has the same object representation, value representation and alignment requirement as its corresponding signed type. For each value `x` of the signed type, the value of the corresponding unsigned type that is congruent to `x` modulo 2^N has the same value of the corresponding bits in its value representation. For example, signed `-1` has the same representation as the largest value of the corresponding unsigned type. A footnote explains that this is two's complement.

¶5 formalizes this with the **base-2 representation**: the base-2 representation of an unsigned value x is x = x₀·2⁰ + x₁·2¹ + … + x_{N−1}·2^(N−1), with each coefficient 0 or 1; the base-2 representation of a signed value is that of the congruent value of the corresponding unsigned type. Functions in `<bit>` such as `std::popcount` and `std::countl_zero` are defined in terms of this representation.

With the shared representation, plus [[conv.integral#3]] (the result of an integral conversion is the value congruent modulo 2^N), conversions between signed and unsigned no longer have any implementation-defined part:

```cpp run ok
#include <cassert>

int main() {
  int x = -1;
  unsigned u = x;                       // 4294967295 (when unsigned is 32 bits)
  assert(u == ~0u);
  assert(static_cast<int>(u) == -1);    // since C++20: the congruent value, no longer implementation-defined
  assert((-8 >> 1) == -4);              // since C++20: right shift of a negative number is arithmetic
}
```

The rule for the last line is in [[expr.shift]]. [[basic.lval#11]] allows reading an `int` object through a glvalue of type `unsigned int`, and what is read is exactly the congruent value.

### Padding bits (¶4)

¶4 also specifies that the value representation of an integer type consists of exactly N bits. Any additional bits in the object representation are padding bits ([[basic.types.general#2]]), and each value of the padding bits is just another representation of the same value. Note 2 stresses that the values of padding bits are unspecified but do not cause traps. This differs from C, which allows trap representations for integers.

### Standard and extended integer types (¶5)

¶5 The standard signed and standard unsigned integer types are collectively the **standard integer types**, and the two extended kinds are collectively the **extended integer types**.

!!! impl "`__int128` is not an extended integer type"
    GCC and Clang provide `__int128` and `unsigned __int128` on 64-bit targets, but generally do not treat them as extended integer types in the standard's sense. One reason is that `intmax_t` must be able to represent the values of every signed integer type; admitting a 128-bit extended integer type would mean making `intmax_t` 128 bits, which would break existing ABIs. Library trait results are not uniform: with the libc++ we tested, `std::is_integral_v<__int128>` is `true`; with libstdc++ the result depends on whether GNU extension mode is enabled. `_BitInt(N)` is likewise only an extension in C++.

## Underlying types (¶6)

¶6 If a fundamental type is specified to have a signed or unsigned integer type as its **underlying type**, the two types have the same object representation, value representation, alignment requirements and range of representable values, and each value has the same representation in both types.

`char`, `wchar_t`, `char8_t`, `char16_t` and `char32_t` below are all defined by this pattern: they are distinct types whose representation is exactly that of some integer type. The underlying type of an enumeration ([[dcl.enum]]) is the same concept.

## Character types (¶7–¶9)

### `char` is a third type (¶7)

```cpp run ok
#include <climits>
#include <cstdio>
#include <type_traits>

void f(char)          { std::puts("char"); }
void f(signed char)   { std::puts("signed char"); }
void f(unsigned char) { std::puts("unsigned char"); }

static_assert(!std::is_same_v<char, signed char>);
static_assert(!std::is_same_v<char, unsigned char>);

int main() {
  f('a');                            // char
  f(static_cast<signed char>(1));    // signed char
  f(static_cast<unsigned char>(1));  // unsigned char
  std::printf("char is %s\n", CHAR_MIN < 0 ? "signed" : "unsigned");
}
```

¶7 `char` is a distinct type whose underlying type is chosen by the implementation between `signed char` and `unsigned char`. Whichever is chosen, `char` is not that type; overload resolution and template specialization distinguish all three. In our tests (arm64 macOS) it prints `char is signed`.

`char`, `signed char` and `unsigned char` are collectively the **ordinary character types**, and together with `char8_t` they are the [[g:narrow-character-type|narrow character types]]. For narrow character types, each possible bit pattern of the object representation represents a distinct value: there are no padding bits and no invalid bit patterns, so they can safely carry arbitrary bytes. Note 5 adds that a bit-field of narrow character type whose width is larger than the width of that type still has padding bits.

!!! impl "Signedness of `char`"
    In the mainstream x86 and x86-64 ABIs `char` is signed; in the Linux ABIs for AArch64, AArch32, PowerPC and RISC-V `char` is unsigned. Apple arm64 is an exception, with signed `char`. GCC and Clang can change this with `-funsigned-char` or `-fsigned-char`, and MSVC with `/J`, but this changes ABI semantics and the whole program must agree. Code like `c < 0` to detect non-ASCII bytes is not portable.

### `wchar_t` (¶8)

¶8 `wchar_t` is a distinct type whose underlying type is an implementation-defined integer type. On Windows it is a 16-bit `unsigned short` holding UTF-16 code units; on x86-64 Linux and macOS it is a 32-bit `int`, and on AArch64 Linux a 32-bit `unsigned int`.

### `char8_t`, `char16_t`, `char32_t` (¶9)

¶9 The underlying type of `char8_t` is `unsigned char`; the underlying types of `char16_t` and `char32_t` are `std::uint_least16_t` and `std::uint_least32_t` respectively ([[cstdint.syn]]).

`char8_t` was added in C++20 ([[P0482R6]]), giving `u8` literals a dedicated type. This was an incompatible change: in C++17 `u8"x"` has type `const char[2]`; since C++20 it is `const char8_t[2]`.

```cpp run error
const char*    a = u8"x";   // error (since C++20): const char8_t[2] cannot convert to const char*
const char8_t* b = u8"x";   // OK
```

`char8_t` is a narrow character type but not an ordinary character type. [[basic.lval#11]] allows only `char`, `unsigned char` and `std::byte` to access the bytes of arbitrary objects, not `char8_t`. This is another benefit of introducing it: compilers can assume a `char8_t*` does not alias objects of other types and optimize more aggressively.

## `bool` (¶10)

¶10 `bool` is a distinct type with the same object representation, value representation and alignment requirements as an implementation-defined unsigned integer type. The only values of `bool` are `true` and `false`. Note 6 says there are no `signed bool`, `unsigned bool`, `short bool` or `long bool`.

If the value representation of `bool` is the same as `unsigned char`'s, it has 8 bits and 256 bit patterns, only two of which correspond to `bool` values. Putting the byte `0x02` into a `bool` with `memcpy` and then reading it is UB; see [[basic.types.trivial]] for an example. `sizeof(bool)` is implementation-defined; it is 1 on mainstream platforms.

`bool` is an integral type, takes part in integral promotion (promoted to `int`, [[conv.prom]]), and has a rank lower than all other integer types ([[conv.rank#1.6]]). C++17 removed `++` on `bool`; `--` was never allowed.

## Integral types: the hierarchy of terms (¶11)

¶11 `char`, `wchar_t`, `char8_t`, `char16_t` and `char32_t` are collectively the **character types**. The character types, `bool`, the signed and unsigned integer types, and cv-qualified versions of these are collectively the **integral types**, also called **integer types**. Note 7 points out that enumerations are not integral types, but unscoped enumerations can be promoted to integral types ([[conv.prom]]).

These names overlap and are easy to confuse:

| Term | Includes |
|---|---|
| signed integer types | `signed char` `short` `int` `long` `long long`, plus extended types |
| unsigned integer types | `unsigned char` through `unsigned long long`, plus extended types |
| standard integer types | the standard types of the two rows above, not including `char`, `bool`, `wchar_t`, etc. |
| character types | `char` `wchar_t` `char8_t` `char16_t` `char32_t` |
| ordinary character types | `char` `signed char` `unsigned char` |
| narrow character types | the ordinary character types and `char8_t` |
| integral types (integer types) | character types, `bool`, signed and unsigned integer types, and cv versions |

So `signed char` is a signed integer type and an ordinary character type, but not a character type; `char` is a character type and an ordinary character type, but neither a signed nor an unsigned integer type, even if its underlying type is `signed char`. The distinction has practical consequences in [[expr.arith.conv]] and [[conv.prom]].

## Floating-point types (¶12–¶14)

¶12 `float`, `double` and `long double` are three distinct types. `double` provides at least as much precision as `float`, and `long double` at least as much as `double`; the set of values of `float` is a subset of the set of values of `double`, which in turn is a subset of that of `long double`. These three types and their cv-qualified versions are collectively the **standard floating-point types**.

An implementation may also provide other types that represent floating-point values and define them as [[g:extended-floating-point-type|extended floating-point types]]. The standard and extended floating-point types are collectively the [[g:floating-point-type|floating-point types]].

Note 8 reminds us that types provided by an implementation but not defined as extended floating-point types are not floating-point types, and the standard places no requirements on them. Clang 23's `_Float16` is such a type: it supports arithmetic, but libc++'s `std::is_floating_point_v<_Float16>` is `false`.

Except as specified in [[basic.extended.fp]], the object and value representations and the accuracy of operations of floating-point types are implementation-defined. C++ does not require IEEE 754 (ISO/IEC 60559); this can be queried with `std::numeric_limits<T>::is_iec559`.

!!! impl "Implementations of `long double`"
    - x86-64 Linux: x87 80-bit extended precision, with `sizeof` 16, of which 48 bits are padding.
    - Windows (MSVC) and Apple arm64: the same as `double`, 64 bits. In our tests `__SIZEOF_LONG_DOUBLE__` is 8.
    - AArch64 Linux and some PowerPC: 128-bit quadruple precision (binary128, usually implemented in software) or double-double.

    `long double` is the least portable arithmetic type. When quadruple precision is needed, use `std::float128_t` (if the implementation provides it).

¶13 The **range of representable values** of a floating-point type is at least from the most negative finite value to the most positive finite value. If the type can represent negative infinity, the range extends to all negative real numbers; if it can represent positive infinity, to all positive real numbers. Note 9 points out that a type conforming to ISO/IEC 60559 has both infinities, so all real numbers (not including the infinities and NaN themselves) are within its range.

This rule determines when floating-point arithmetic is UB. [[expr.pre#4]] specifies that if the mathematical result of an arithmetic expression is neither in the range of representable values nor an infinity or NaN of the type, the behavior is undefined. For IEEE types every real result is in range, so `FLT_MAX * 2.0f` is not UB; the result is positive infinity. Per note 4 of [[expr.pre]], the only arithmetic operation that can cause UB on such types is division by zero. On floating-point formats without infinities, overflow is still UB.

¶14 The integral and floating-point types are collectively the **arithmetic types**.

## `void` (¶15)

¶15 cv `void` is an incomplete type that cannot be completed, with an empty set of values. So there are no `void` objects, arrays of `void` or `void&`, but there is `void*` ([[basic.compound]]).

Expressions of type `void` can still appear in some places, listed in note 11:

```cpp run ok
void v() {}
void w() { return v(); }       // the operand of return can be a void expression

template<class F> auto call(F f) { return f(); }   // works when F returns void too

int main() {
  (void)0;                     // explicit conversion to void
  static_cast<void>(42);
  int k = (v(), 1);            // an operand of a comma expression
  true ? v() : w();            // both branches of ?: are void
  decltype(v())* p = nullptr;  // decltype(v()) is void
  (void)p; (void)k;
  call(v);
}
```

Beyond these, a `void` expression can also be an expression statement, a parenthesized expression, a requirement in a *requires-expression*, and the operand of `typeid` or `noexcept`.

Allowing `return v();` is by design: forwarding wrappers like `call` need no special case for functions returning `void`.

## `std::nullptr_t` (¶16)

```cpp run ok
#include <cstddef>
#include <cstdio>

void f(int)   { std::puts("int"); }
void f(char*) { std::puts("char*"); }

static_assert(sizeof(std::nullptr_t) == sizeof(void*));

int main() {
  f(nullptr);              // char*: nullptr cannot convert to int
  std::nullptr_t n;        // uninitialized
  char* p = n;             // OK: reading n does not access its storage
  f(p);
}
```

¶16 cv `std::nullptr_t` is a distinct type. A prvalue of type `std::nullptr_t` is a **null pointer constant**, which can be converted to any pointer and pointer-to-member type ([[conv.ptr]], [[conv.mem]]). Its size and alignment requirement are the same as `void*`'s.

Note 12 points out that its value representation can consist of no bits at all, because the type has only one value. So [[conv.lval#3.1]] specifies that an lvalue-to-rvalue conversion on a glvalue of type `nullptr_t` yields a null pointer constant directly, without accessing the object. The example above reads the uninitialized `n`, and is perfectly valid.

`f(nullptr)` calls `f(char*)` because `nullptr` cannot convert to `int`. With `f(NULL)`, the result depends on the definition of `NULL`: it may call `f(int)`, or be ambiguous.

`nullptr_t` is a scalar type but not a pointer type: `std::is_pointer_v<std::nullptr_t>` is `false`, and it has its own primary category, `std::is_null_pointer`.

## `std::meta::info` {{c++26}} (¶17–¶18)

```cpp
#include <meta>

struct S { int mem; };
constexpr std::meta::info r1 = ^^S;         // represents a type
constexpr std::meta::info r2 = ^^S::mem;    // represents a class member
constexpr std::meta::info r0{};             // the null reflection
static_assert(r1 != r2 && r0 == std::meta::info{});
```

Clang 23 does not yet implement static reflection, so this code has not been verified by compiling.

¶17 A value of type `std::meta::info` is called a **reflection**. Reflections come from C++26 static reflection ([[P2996R13]]): an expression like `^^S` produces a reflection that represents the construct `S`. There is a unique **null reflection**; every other reflection represents one of: a value of scalar type, an object with static storage duration, a variable, a structured binding, a function, a function parameter, an enumerator, an annotation, a type alias, a type, a class member, an unnamed bit-field, a class template, a function template, a variable template, an alias template, a concept, a namespace alias, a namespace, a direct base class relationship, or a data member description.

¶18 is a recommended practice: implementations should not represent other constructs specified in the standard as values of `std::meta::info`, such as *using-declarators*, partial specializations, attributes, placeholder types, statements and expressions. Note 14 explains that future standards may specify semantics for them, and supporting them on one's own now could conflict with the standard later.

`std::meta::info` is a fundamental type and also a scalar type ([[basic.types.general#7]]), so it can be the type of a non-type template parameter. Its primary category trait is `std::is_reflection` ([[meta.unary.cat]]).

## Same representation, still distinct types (¶19)

```cpp run error
void g(long*);
int main() {
  int i = 0;
  g(&i);       // error: int* cannot convert to long*, even though both have the same representation
}
```

¶19 The types described in this subclause are called fundamental types. Note 15 points out that even if an implementation gives two fundamental types the same value representation, they are still distinct types. On LLP64, `int` and `long` are both 32-bit two's complement, but `int*` does not implicitly convert to `long*`, `f(int)` and `f(long)` are two overloads, and `int` and `long` are not layout-compatible ([[basic.types.general#9]]).

## Optional extended floating-point types ([[basic.extended.fp]]) {{c++23}}

C++23's [[P1467R9]] specified standard names for common floating-point formats. If an implementation supports an extended floating-point type with the corresponding properties, it must declare the corresponding type alias in `<stdfloat>`, define the corresponding macro ([[cpp.predefined]]), and support the corresponding literal suffix ([[lex.fcon]]). ¶1–¶5 each specify one:

| Alias (`<stdfloat>`) | ISO/IEC 60559 format | Total bits | Precision | Exponent bits | Macro | Suffix |
|---|---|---|---|---|---|---|
| `std::float16_t` | binary16 | 16 | 11 | 5 | `__STDCPP_FLOAT16_T__` | `f16` `F16` |
| `std::float32_t` | binary32 | 32 | 24 | 8 | `__STDCPP_FLOAT32_T__` | `f32` `F32` |
| `std::float64_t` | binary64 | 64 | 53 | 11 | `__STDCPP_FLOAT64_T__` | `f64` `F64` |
| `std::float128_t` | binary128 | 128 | 113 | 15 | `__STDCPP_FLOAT128_T__` | `f128` `F128` |
| `std::bfloat16_t` | no name | 16 | 8 | 8 | `__STDCPP_BFLOAT16_T__` | `bf16` `BF16` |

The note in ¶6 explains that the precision includes the implicit leading 1 bit of the significand, so the significand field actually occupies one bit less than the precision. bfloat16 is a format popularized by machine-learning hardware; it has the same exponent bits as `float` and hence the same range, but only 8 bits of precision; ISO/IEC 60559 gives no name to this set of parameters.

¶7 recommends that other names an implementation provides outside `<stdfloat>` be compatible with C's `_Float16`, `_Float32`, `_Float64` and `_Float128`.

Three things to watch for when using them:

1. All of these types are optional; code should detect them with the macros first, as in `#ifdef __STDCPP_FLOAT16_T__`.
2. They are extended floating-point types, not aliases of `float` or `double`. Even if `std::float32_t` has exactly the same format as `float`, they are distinct types. [[conv.rank#2]] gives them equal conversion rank with `float32_t` having the greater subrank, so mixed arithmetic between `float32_t` and `float` yields `float32_t`.
3. They cannot be implicitly converted to a type of lower rank. [[conv.double#1]] allows a floating-point value to be implicitly converted only to a floating-point type whose rank is greater than or equal to that of the source; among the standard floating-point types, any direction is allowed for compatibility. So `std::float16_t h = 1.0;` is ill-formed, since `1.0` is a `double`; write `1.0f16` or convert explicitly.

```cpp
#include <stdfloat>
#ifdef __STDCPP_FLOAT16_T__
std::float16_t a = 1.0f16;                            // OK
std::float16_t b = 1.0;                               // error: double → float16_t lowers the rank
std::float16_t c = static_cast<std::float16_t>(1.0);  // OK
#endif
```

Clang 23 with libc++ does not provide `<stdfloat>`, so this code has not been verified by compiling in our tests; GCC with libstdc++ already implements these types.

## History

!!! history
    - C++98: integers could use two's complement, ones' complement or sign-magnitude; there was no `long long`; `wchar_t` was already a distinct type (in C it is a typedef).
    - C++11: added `long long`, extended integer types, `char16_t`, `char32_t` and `std::nullptr_t`.
    - C++17: removed `++` on `bool`. Added `std::byte`, which is `enum class byte : unsigned char {}`, not a fundamental type.
    - C++20: signed integers are always two's complement ([[P0907R4]], with wording by [[P1236R1]]), including exact ranges, no trap representations, signed/unsigned conversions yielding congruent values, and arithmetic right shift of negative numbers; signed overflow is still UB. Added `char8_t` ([[P0482R6]]), which changed the type of `u8` literals.
    - C++23: extended floating-point types and `<stdfloat>` ([[P1467R9]]), with floating-point conversion ranks redefined.
    - C++26: `std::meta::info` ([[P2996R13]]).

## Common misconceptions

!!! pitfall "`char` is `signed char`"
    The result of `std::is_signed_v<char>` depends on the platform, but `char` is always a third, distinct type. If you write overloads or specializations only for `signed char` and `unsigned char`, passing a `char` may select an unexpected conversion or even be ambiguous.

!!! pitfall "`std::uint8_t` prints as a number"
    `std::int8_t` and `std::uint8_t` are almost always aliases of `signed char` and `unsigned char`, so `std::cout << std::uint8_t(65)` prints `A`, not `65`.

!!! pitfall "Two's complement means signed overflow wraps"
    C++20 specified only the representation and conversions, not the result of arithmetic overflow; `INT_MAX + 1` is still UB. When wrapping is needed, convert to an unsigned type, do the arithmetic, and convert back; converting back yields the determinate congruent value.

!!! pitfall "`std::float32_t` is `float`"
    Even with exactly the same format, they are distinct types, and overload resolution, template specialization and `std::format` all distinguish them. Mixed arithmetic between them yields `float32_t`.

## Questions

!!! question "1. Can an implementation make `signed char` 9 bits wide and `int` 18 bits wide? What about `unsigned char`?"

<details markdown="1">
<summary>Answer</summary>

Yes. Table 14 gives only lower bounds (`signed char` at least 8 bits, `int` at least 16 bits); the rest is up to the implementation (¶4). An unsigned type has the same width as its corresponding signed type (¶2), so `unsigned char` is also 9 bits, and `CHAR_BIT == 9`. ¶7 requires every bit pattern of a narrow character type to represent a distinct value, so all 9 bits are value bits with no padding. There really were machines with 36-bit words and 9-bit bytes.
</details>

!!! question "2. `std::nullptr_t n; void* p = n;` reads an uninitialized variable; why is it not UB? What about `int i; int j = i;`?"

<details markdown="1">
<summary>Answer</summary>

Per [[conv.lval#3.1]], when the glvalue has type cv `std::nullptr_t`, the result of the lvalue-to-rvalue conversion is a null pointer constant directly, without accessing the object, so whether the object's value is determinate does not matter (note 12 in ¶16: the value representation can consist of no bits).

`int i; int j = i;` reads the value of a variable with automatic storage duration. Since C++26 this is **erroneous behavior** ([[basic.indet]]): the standard deems it an error, but the result is a determinate erroneous value chosen by the implementation, and the implementation may also diagnose it or terminate the program. In C++23 and earlier it was UB.
</details>

!!! question "3. When the underlying type of `char` is `signed char`, is `char` a signed integer type? What is `std::is_signed_v<char>`?"

<details markdown="1">
<summary>Answer</summary>

No. The signed integer types of ¶1 are only the five standard types and the extended types; `char` is not among them; it is a character type, an ordinary character type and an integral type. But `std::is_signed<T>` is defined as `T` being an arithmetic type with `T(-1) < T(0)` ([[meta.unary.prop]]), so in this case `std::is_signed_v<char>` is `true`. The names of traits do not map one-to-one onto the standard's terms.
</details>
