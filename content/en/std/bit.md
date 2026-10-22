---
title: Bit manipulation
summary: "The <bit> header: bit_cast to look at an object's bits legally, byteswap to reverse byte order, and the power-of-2, shift, rotate, counting and bit permutation functions that accept only unsigned integers, plus the endian enumeration."
updated: 2026-10-19
---

!!! tldr
    - To look at the bits of a `float` as a `uint32_t`, `reinterpret_cast` and unions are both UB; `std::bit_cast` is the legal way, and it works at compile time.
    - `bit_cast` requires the two types to have the same size and both be trivially copyable. Padding bits of the source landing in a result of non-byte type are UB; landing in `unsigned char` or `std::byte` they are merely indeterminate values.
    - The power-of-2, rotate, counting and bit permutation functions accept only unsigned integer types; `bool`, `char` and signed integers all get "no matching function".
    - These functions are defined for input 0 and for any shift amount, which is their main difference from `__builtin_clz` and the built-in shift operators. The only exception is that the result of `bit_ceil` must fit.
    - On a mixed-endian platform `std::endian::native` equals neither `little` nor `big`, so that case must be ruled out when testing byte order.

The whole `<bit>` header is freestanding (the first-line comment of [bit.syn] says `// all freestanding`): it needs no memory allocation, exceptions or I/O, and can be used in kernels and embedded code. Almost all of its functions are `constexpr` and `noexcept`.

## Looking at an object's bits with `bit_cast` [bit.cast]

### Three old ways of type punning

Low-level code often needs to treat the bits of a `float` as an integer, for example to parse floating-point formats, compute hashes or serialize. Before C++20 there were three common ways, and only the third was legal:

| Approach | Verdict |
|---|---|
| `*reinterpret_cast<uint32_t*>(&f)` | {{ub}}: a `float` object cannot be accessed through a glvalue of type `uint32_t` ([[basic.lval#11]]); this violates the strict aliasing rule |
| `union { float f; uint32_t u; }`, write `f` and read `u` | {{ub}}: reads an inactive member ([[class.union]]). GCC and Clang support it as an extension, but reject it in constant evaluation |
| `std::memcpy(&u, &f, 4)` | legal: the object representation of a trivially copyable type can be copied into another object of the same type ([[basic.types]]) |

```cpp run title="type-punning-ub.cpp" ub
#include <cstdint>
#include <cstdio>
float f = 1.0f;
int main() {
    std::uint32_t u = *reinterpret_cast<std::uint32_t*>(&f);   // UB: strict aliasing
    std::printf("%x\n", u);       // prints 3f800000 in our tests, but with no guarantee
}
```

The `memcpy` approach is correct, but it needs a destination object to exist first (so the destination type must be default-constructible), and it cannot be used in constant evaluation. C++20's `bit_cast` ([[P0476R2]]) wraps "copy into a new object" into a `constexpr` function that returns the value:

```cpp run title="bit-cast-basic.cpp" ok
#include <array>
#include <bit>
#include <cstdint>
#include <cstdio>
#include <cstring>

constexpr std::uint32_t bits_of(float f) { return std::bit_cast<std::uint32_t>(f); }
static_assert(bits_of(1.0f) == 0x3f80'0000);
static_assert(std::bit_cast<float>(0x4049'0fdbu) > 3.14f);

struct RGBA { std::uint8_t r, g, b, a; };
static_assert(std::bit_cast<std::array<std::uint8_t, 4>>(RGBA{1, 2, 3, 4})[2] == 3);

std::uint32_t via_memcpy(float f) {            // the standard approach before C++20
    std::uint32_t u;
    std::memcpy(&u, &f, sizeof u);
    return u;
}

int main() {
    float f = -0.0f;
    std::printf("%08x %08x\n", std::bit_cast<std::uint32_t>(f), via_memcpy(f));  // 80000000 80000000
}
```

### Constraints: same size, both trivially copyable (¶1)

¶1 `bit_cast<To>(from)` has three constraints: `sizeof(To) == sizeof(From)`, and `To` and `From` are both **trivially copyable types** ([[g:trivially-copyable-type]], [[class.prop]]), that is, types that can be copied byte by byte. These are *Constraints*: when they are not met, `bit_cast` does not participate in overload resolution, and the error is "no matching function".

The sizes must be equal; `bit_cast` neither truncates nor pads. To get the low 32 bits of a `double`, first `bit_cast<uint64_t>` and then shift. `To` need not be default-constructible, which is an improvement over `memcpy`.

```cpp run title="bit-cast-size.cpp" error
#include <bit>
auto d = std::bit_cast<long>(1);   // error: sizeof(long) != sizeof(int), no matching function
```

A `constexpr` `bit_cast` cannot be written in pure library code: constant evaluation allows neither `reinterpret_cast` nor `memcpy` between objects of different types. So all three major implementations rely on a compiler builtin; libc++'s function body is just one line, `return __builtin_bit_cast(_ToType, __from);`.

### Where each bit of the result comes from (¶3)

¶3 specifies the return value: a new `To` object, each bit of whose **value representation** ([[g:value-representation]], the bits that take part in representing the value) equals the corresponding bit of the **object representation** ([[g:object-representation]], all the bytes the object occupies, including padding) of `from`. Note the asymmetry: what is read is all the bits of the source object, and what is written is the value bits of the destination. The destination's own padding bits are unspecified.

¶3 also specifies that `bit_cast` implicitly creates nested objects within the result ([[intro.object]], [[g:implicitly-create-objects]]). For example, when `To` contains a union member, which member is active is chosen by the rules of implicit object creation so as to give the program defined behavior.

Some bits in the source object have no definite value themselves, and once ¶3 carries them into the result they fall into two kinds:

- A bit of the result is **indeterminate** if it corresponds to a padding bit of `from`, or if the smallest object containing the corresponding bit is not within its lifetime or has an indeterminate value ([[basic.indet]]).
- A bit is **erroneous** if the smallest object containing the corresponding bit has an **erroneous value** ([[g:erroneous-value]]). Since C++26, uninitialized automatic variables have erroneous values, and reading them is erroneous behavior rather than UB ([[P2795R5]]).

For each such bit, take the smallest object u in the result that contains it:

- ¶3.1 If u is of type `unsigned char`, `std::byte`, or `char` whose underlying type is `unsigned char`, u merely has an indeterminate or erroneous value; it is not UB. This is consistent with [[basic.indet]], which allows indeterminate values to be carried around in byte types.
- ¶3.2 Otherwise, if the bit is indeterminate, the behavior is undefined.
- ¶3.3 Otherwise (the bit is erroneous), the behavior is erroneous ({{erroneous}}).

The most common indeterminate bits come from struct padding. `struct P { char c; int i; };` has 3 padding bytes after `c` on common ABIs:

```cpp run title="bit-cast-padding.cpp" error
#include <array>
#include <bit>
#include <cstdint>

struct P { char c; int i; };      // 3 bytes of padding after c on typical ABIs
static_assert(sizeof(P) == 8);

constexpr int first_byte() {
    auto bytes = std::bit_cast<std::array<unsigned char, sizeof(P)>>(P{1, 2});
    return bytes[0];              // OK: the byte for c has a definite value
}
static_assert(first_byte() == 1);

constexpr int padding_byte() {
    auto bytes = std::bit_cast<std::array<unsigned char, sizeof(P)>>(P{1, 2});
    return bytes[1];              // a padding byte has an indeterminate value; reading it is not a constant expression
}
static_assert(padding_byte() == 0);                          // error

constexpr auto u = std::bit_cast<std::uint64_t>(P{1, 2});    // error: ¶3.2, UB
```

Converting to `array<unsigned char, 8>` is itself legal: the 3 elements corresponding to padding each have an indeterminate value, which is fine as long as they are not read. Converting to `uint64_t` puts 24 indeterminate bits into a single `uint64_t`, which is UB per ¶3.2. Constant evaluation checks these rules strictly; Clang 23's note on the last line is *indeterminate value can only initialize an object of type 'unsigned char' or 'std::byte'*.

The legal `bit_cast<array<unsigned char, 8>>(P{1, 2})` cannot be used to initialize a `constexpr` variable either, because the result of a constant expression cannot contain indeterminate values ([[expr.const]]). That is why it is placed in a local variable of a `constexpr` function above.

### When it can be evaluated at compile time (¶2)

```cpp run title="bit-cast-constexpr.cpp" error
#include <bit>
#include <cstdint>

struct S { int* p; };
union U { int i; float f; };
int g;

constexpr auto a = std::bit_cast<std::uintptr_t>(&g);          // error: From is a pointer type
constexpr auto b = std::bit_cast<std::uintptr_t>(S{nullptr});  // error: S has a pointer member
constexpr auto c = std::bit_cast<int>(U{1});                   // error: From is a union
```

All three lines are valid at run time; they just cannot be evaluated at compile time. ¶2 uses a *Constant When* element ([[structure.specifications]]) to specify that, for the call to be a constant subexpression, neither `To` nor `From` may have a **constexpr-unknown representation** ([[g:constexpr-unknown-representation]]). Per [[expr.const.core#1]], the following types have a constexpr-unknown representation: unions, `std::meta::info`, pointers and pointers to members, volatile-qualified types, classes with non-static data members of reference type, and types some base class or non-static member of which has a constexpr-unknown representation.

The reasons differ. A pointer inside the constant evaluator is a symbolic value of the form "some object plus an offset", with no definite address bits, and the same goes for reference members. For a union, the active member determines which bits are value bits, and the evaluator cannot process it bit by bit. Volatile accesses cannot appear in constant expressions in the first place. `std::meta::info` is a compiler-internal reflection handle with no bit representation.

!!! pitfall "bit_cast is not another spelling of reinterpret_cast"
    `bit_cast` always returns a new object by value and never produces an alias of the original object. `bit_cast<Header>(buffer)` requires `buffer` itself to be an object of size `sizeof(Header)` (such as a `std::array<std::byte, N>`). Pass in a pointer and what gets reinterpreted is the 8 bytes of the pointer itself. To use an existing block of memory as a `T` object, use `std::start_lifetime_as` ([[obj.lifetime]]).

## Reversing byte order: `byteswap` [bit.byteswap] {{c++23}}

¶1–¶4 `byteswap(value)` returns an object whose object representation is the object representation of `value` with its bytes in reverse order ([[P1272R4]]).

Its constraints differ from the other numeric functions on this page: the *Constraints* is that `T` models `integral`, so signed integers and `char` can be used; there is also a *Mandates*: `T` has no padding bits ([[basic.types]]), since otherwise reversing could move padding bits into value bits. Violating the *Mandates* is ill-formed and requires a diagnostic.

Because the specification is at the level of the object representation, the result for signed numbers is fully determined too: `byteswap(int16_t{0x0102}) == 0x0201`. On single-byte types it is the identity function. Together with `endian`, it is the complete toolkit for network byte order conversion:

```cpp
if constexpr (std::endian::native == std::endian::little) x = std::byteswap(x);
```

{{impl}} libc++ makes an exception for `bool` (a source comment says existing implementations all accept it, and an identity transformation on a single byte moves no bits); other types are dispatched by size to `__builtin_bswap16/32/64/128`, which compile to a single `bswap` (x86) or `rev` (ARM) instruction.

## Numeric functions that accept only unsigned integers

Except for `bit_cast`, `byteswap`, `shl` and `shr`, the *Constraints* of every function on this page is "`T` is an unsigned integer type" ([[basic.fundamental]], [[g:unsigned-integer-type]]). `bool`, `char`, `char8_t`, `wchar_t`, signed integers and enumerations are not among them:

```cpp run title="bit-unsigned-only.cpp" error
#include <bit>
auto a = std::popcount(-1);              // error: int is not an unsigned integer type
auto b = std::has_single_bit(true);      // error: bool is not an unsigned integer type
auto c = std::rotl('a', 1);              // error: neither is char
```

Excluding signed types is intentional. For signed numbers, the top bit is the sign bit, and the answer to questions like "how many leading zeros" depends on the representation; whereas the value of an unsigned integer corresponds one-to-one with its binary digits, so these functions operate only on values and are independent of memory layout.

### Integral powers of 2 [bit.pow.two]

These four functions were introduced by [[P0556R3]], and [[P1956R1]] renamed the original `ispow2`, `ceil2`, `floor2` and `log2p1` to the current names, emphasizing that they are bit operations rather than mathematical functions.

| Function | Paragraphs | Returns | When `x == 0` |
|---|---|---|---|
| `has_single_bit(x)` | ¶1–2 | whether `x` is an integral power of 2, i.e. has exactly one bit set | `false` |
| `bit_ceil(x)` | ¶3–8 | the smallest power of 2 not less than `x` | `1` |
| `bit_floor(x)` | ¶9–10 | the largest power of 2 not greater than `x` | `0` |
| `bit_width(x)` | ¶11–12 | the number of bits needed to represent `x`, i.e. 1 + ⌊log₂x⌋ | `0` |

`bit_width(x)` equals `numeric_limits<T>::digits - countl_zero(x)`.

`bit_ceil` is the only one that can fail: `bit_ceil(uint8_t{129})` should be 256, which does not fit in a `uint8_t`.

!!! std
    Preconditions: N is representable as a value of type T.

    Remarks: A function call expression that violates the precondition in the Preconditions: element is not a core constant expression.

¶5 Violating this precondition at run time is {{ub}}. ¶8 specifies that during constant evaluation, a call that violates the precondition is not a core constant expression, so the compiler must report an error, and `static_assert(bit_ceil(...))` will not quietly get a wrong answer.

```cpp run title="bit-ceil.cpp" error
#include <bit>
#include <cstdint>

static_assert(std::bit_ceil(5u) == 8u);
static_assert(std::bit_ceil(0u) == 1u);            // bit_ceil of 0 is 1
static_assert(std::bit_floor(0u) == 0u);
static_assert(std::bit_width(0u) == 0 && std::bit_width(8u) == 4);
static_assert(std::bit_ceil(std::uint8_t{128}) == 128);
constexpr auto x = std::bit_ceil(std::uint8_t{129});  // error: 256 cannot be represented as uint8_t
```

That is why `bit_ceil` is not marked `noexcept`, while `bit_floor` is. The standard library's convention is that functions with preconditions (narrow contracts) are not marked `noexcept`, leaving implementations room to check violations by throwing. Implementations may add `noexcept` themselves, and libc++ does so for `bit_ceil`. In our tests, libc++ in non-hardened mode returns 1 for `bit_ceil(0x80000001u)`, with no check at all.

### Rotation: `rotl`, `rotr` [bit.rotate]

¶1–¶7 Let N be the number of bits of `T` and r be `s % N`. `rotl(x, s)` returns `x` when r is 0, `(x << r) | (x >> (N - r))` when r is positive, and `rotr(x, -r)` when r is negative. `rotr` is symmetric ([[P0553R4]]).

- `s` is an `int` and may be negative; a negative left rotation is a right rotation. `%` truncates toward zero ([[expr.mul]]), so `-33 % 32 == -1` and `rotl(x, -33) == rotr(x, 1)`.
- `s` may be arbitrarily large. After the modulo, the shift amount is always within (−N, N), and no shift is done when r is 0, avoiding the UB of `x >> N` ([[expr.shift]]).

```cpp run title="bit-ops.cpp" ok
#include <bit>
#include <cstdint>

static_assert(std::rotl(std::uint8_t{0b1000'0001}, 1)  == 0b0000'0011);
static_assert(std::rotl(std::uint8_t{0b1000'0001}, -1) == 0b1100'0000);  // negative = opposite direction
static_assert(std::rotr(std::uint8_t{0b0000'0011}, 9)  == 0b1000'0001);  // 9 % 8 == 1
static_assert(std::rotl(1u, -33) == std::rotr(1u, 1));                    // -33 % 32 == -1
static_assert(std::countl_zero(std::uint16_t{1}) == 15);
static_assert(std::countr_zero(0u) == 32 && std::countl_one(~0u) == 32);
static_assert(std::popcount(0xF0F0u) == 8);
static_assert(std::has_single_bit(64u) && !std::has_single_bit(0u));
static_assert(std::byteswap(std::uint32_t{0x12345678}) == 0x78563412);
static_assert(std::byteswap(std::int16_t{0x0102}) == 0x0201);            // byteswap accepts signed numbers

int main() {}
```

### Counting [bit.count]

Also introduced by [[P0553R4]]. N is the number of bits of `T`, and the return type is always `int`:

| Function | Paragraphs | Returns |
|---|---|---|
| `countl_zero(x)` | ¶2–3 | the number of consecutive 0 bits starting from the most significant bit; N when `x == 0` |
| `countl_one(x)` | ¶4–5 | the number of consecutive 1 bits starting from the most significant bit; N when `x` is the maximum value |
| `countr_zero(x)` | ¶6–7 | the number of consecutive 0 bits starting from the least significant bit; N when `x == 0` |
| `countr_one(x)` | ¶8–9 | the number of consecutive 1 bits starting from the least significant bit; N when `x` is the maximum value |
| `popcount(x)` | ¶10–11 | the number of bits with value 1 |

The "N" cases in the table are written in four notes; notes are not normative, but these results follow directly from the *Returns*. Being defined for input 0 is the biggest difference from `__builtin_clz` and `__builtin_ctz`: the latter two have undefined results for 0, and x86's `BSR` and `BSF` instructions do not give a definite result for 0 either. The standard functions either use instructions like `LZCNT` and `TZCNT` that return the bit width for 0, or take one extra branch.

### Shifts: `shl`, `shr` [bit.shift]

This pair of functions was added to the working draft recently, and libc++ in our tests does not implement them yet. They address the problem of the built-in shift operators ([[expr.shift]]): a negative shift amount, or one not less than the bit width, is {{ub}}.

¶1 First the mathematical result r is computed in a hypothetical integer type of sufficient range, then converted back to `T` with `static_cast<T>(r)`, that is, modulo 2ⁿ ([[conv.integral]]). ¶3 `shl(x, s)` returns x×2ˢ rounded toward negative infinity, and ¶5 `shr(x, s)` returns x×2⁻ˢ rounded toward negative infinity. The constraints in ¶2 and ¶4 are that `T` and `S` are signed or unsigned integer types; unlike the other functions in this section, they accept signed numbers.

So a negative `s` naturally becomes a shift in the opposite direction. When `s` exceeds the bit width, the result of `shl` is 0 after the modulo; `shr` gives 0 for non-negative numbers and −1 for negative ones, equivalent to an arithmetic right shift. Neither function has a precondition.

### Bit permutations [bit.permute]

These four functions were added to the working draft recently ([[P3104]]); libc++ in our tests does not provide them yet, and there is no corresponding feature-test macro. ¶1 defines notation: N is the number of bits, αₙ is the nth bit of α counting from the low end, and σ(α, n) is the number of 1 bits among the lowest n bits of α.

| Function | Paragraphs | Meaning | Corresponding instruction |
|---|---|---|---|
| `bit_reverse(x)` | ¶2–4 | reverses the bit order, moving bit n to bit N−1−n; reversing twice gives the original value | ARM `RBIT` |
| `bit_repeat(x, l)` | ¶5–10 | uses the lowest `l` bits of `x` as a pattern and repeats it to fill N bits; `bit_repeat(uint32_t{0xc}, 4) == 0xcccccccc` | none |
| `bit_compress(x, m)` | ¶11–13 | gathers the bits of `x` where `m` is 1, in order, into the low end | x86 BMI2 `PEXT` |
| `bit_expand(x, m)` | ¶14–16 | the inverse operation, placing the low bits of `x` in order at the positions where `m` is 1 | x86 BMI2 `PDEP` |

The formula in ¶12 is compress(x, m) = Σ mₙ·xₙ·2^σ(m,n): only bits with mₙ = 1 take part, and each is placed at bit σ(m, n), that is, the number of 1 bits in m below it. Example 2 gives `bit_compress(0bABCD, 0b0101) == 0b00BD`, and Example 3 gives `bit_expand(0bABCD, 0b0101) == 0b0C0D`.

`bit_repeat` has the precondition `l > 0` (¶6), and, as with `bit_ceil`, a call that violates it is not a core constant expression (¶9). An `l` not less than N is no problem: in the formula n mod l = n, and the result is just `x`.

Until the standard library implements them, a portable version can be written by hand following the formula in ¶12:

```cpp run title="bit-compress-manual.cpp" ok
#include <bit>
#include <cstdint>

// PEXT semantics, implemented following the formula in [bit.permute]/12
constexpr std::uint32_t compress(std::uint32_t x, std::uint32_t m) {
    std::uint32_t r = 0;
    for (int k = 0; m != 0; m &= m - 1, ++k)        // take the lowest 1 of m in turn; k is σ(m, n)
        r |= ((x >> std::countr_zero(m)) & 1u) << k;
    return r;
}
static_assert(compress(0b1010, 0b0101) == 0b00);   // B=0, D=0
static_assert(compress(0b1011, 0b0101) == 0b01);   // B=0, D=1
static_assert(compress(0xABCD'1234, 0x0000'FF00) == 0x12);

int main() {}
```

## Endianness [bit.endian]

¶1 **Big-endian** ([[g:big-endian]]) puts the most significant byte first, and **little-endian** ([[g:little-endian]]) puts the least significant byte first. This subclause describes the endianness of scalar types in the execution environment ([[P0463R1]]).

`enum class endian { little, big, native };` All three enumerators are "see below", and ¶2 only specifies the relationships among them:

- If all scalar types have size 1 byte (for example on some DSPs where `CHAR_BIT == 32` and `sizeof(long) == 1`), the three values are equal, and the endianness question does not arise.
- Otherwise `little != big`. If all scalar types are big-endian, `native == big`; if all are little-endian, `native == little`.
- Otherwise the platform is **mixed-endian** ([[g:mixed-endian]]), and `native` equals neither `big` nor `little`.

Mixed endianness really exists: the PDP-11's 32-bit integers are two little-endian 16-bit words arranged in big-endian order; in some ARM floating-point formats, the two halves of a `double` are in a different word order from integers. "All scalar types" includes floating-point types and pointers; as long as the byte order of one of them differs from the others, `native` cannot equal `little` or `big`.

So do not write `native == little ? ... : ...` and assume that if it is not little-endian it must be big-endian. The right approach is to rule out the third case first:

```cpp run title="endian.cpp" ok
#include <bit>
#include <cstdint>

constexpr std::uint32_t to_big(std::uint32_t x) {
    static_assert(std::endian::native == std::endian::big ||
                  std::endian::native == std::endian::little,
                  "mixed-endian platform not supported");
    if constexpr (std::endian::native == std::endian::little) return std::byteswap(x);
    else return x;
}
static_assert(to_big(0x01020304) == 0x04030201 || std::endian::native == std::endian::big);

int main() {}
```

An ordinary `static_assert` is used here, rather than `static_assert(false)` in a third `if constexpr` branch. In a non-template function, a discarded branch is still checked, and `static_assert(false)` would fail outright ([[stmt.if]]).

{{impl}} libc++ gives `little` and `big` two arbitrary distinct values, `0xDEAD` and `0xFACE`; `native` takes one of them according to the target platform, or else a third value, `0xCAFE`. libc++ does not support the case where all scalars are 1 byte.

## History and evolution

!!! history
    - C++20: `bit_cast` ([[P0476R2]]), `endian` ([[P0463R1]], originally in `<type_traits>`, later moved to `<bit>`), rotations and counting ([[P0553R4]]), and the power-of-2 functions ([[P0556R3]], renamed by [[P1956R1]]).
    - C++23: `byteswap` ([[P1272R4]]).
    - C++26: with the introduction of erroneous behavior ([[P2795R5]]), ¶3 of `bit_cast` gained the rules for erroneous bits. `<stdbit.h>` came into C++ as a C23 header ([[stdbit.h.syn]]).
    - New wording after C++23: the compile-time restrictions on `bit_cast` switched to the core language's notion of constexpr-unknown representation, stated as *Constant When*; `shl`, `shr` and the bit permutation functions were added ([[P3104]]).

## Common misconceptions

!!! pitfall "Reading after `reinterpret_cast` has always given the right result, so it is fine"
    A program with UB can happen to produce the expected output. The optimizer relies on the strict aliasing rule to assume that a `float*` and a `uint32_t*` do not point to the same object, and a slight change to the code may make it read a stale value. With Clang 23 at `-O2`, all three approaches, `bit_cast`, `memcpy` and `reinterpret_cast`, compile to the same single `fmov` instruction, so there is no performance reason to use the UB approach.

!!! pitfall "`countl_zero(0)` is undefined just like `__builtin_clz(0)`"
    The standard functions are defined for 0 and return the bit width N. Only the compiler builtins are undefined for 0.

## Questions

!!! question "Question 1"
    `struct A { std::uint16_t a; std::uint8_t b; };` (with `sizeof` 4). What is the run-time behavior of `std::bit_cast<std::uint32_t>(A{1, 2})`? And of `std::bit_cast<std::array<std::byte, 4>>(A{1, 2})`? And of then reading element `[3]` of the latter?

<details markdown="1">
<summary>Answer</summary>

The last byte of `A` is padding and not part of `A`'s value representation. Per [bit.cast] ¶3, the corresponding 8 bits of the `uint32_t` result are indeterminate; the smallest object containing them is the whole `uint32_t`, which is not a byte type, so per ¶3.2 the behavior is undefined.

When converting to `array<std::byte, 4>`, the smallest object containing the indeterminate bits is the 4th `std::byte` element, which per ¶3.1 merely has an indeterminate value, so the `bit_cast` itself is fine. Reading `[3]` afterwards gives an indeterminate value; per [[basic.indet]], only a few cases, such as using it to initialize another `unsigned char` or `std::byte` object, are not UB; using it in a comparison or arithmetic is UB.
</details>

!!! question "Question 2"
    On a platform where `char`, `short`, `int` and `long` are all little-endian, but the two 32-bit halves of a `double` are arranged in big-endian order, what does `std::endian::native` equal?

<details markdown="1">
<summary>Answer</summary>

Neither `endian::little` nor `endian::big` (the last sentence of [bit.endian] ¶2), because not all scalar types are little-endian. `double` is a scalar type ([[basic.types]]), and its byte order counts too. `little != big` still holds here, because not all scalar types are only 1 byte.
</details>

## Summary

| Function | Type requirements | Preconditions and special rules |
|---|---|---|
| `bit_cast<To>(from)` | equal sizes, both trivially copyable | indeterminate bits in a non-byte object are UB, erroneous bits are EB; compile-time evaluation only if neither side has a constexpr-unknown representation |
| `byteswap` | `integral` (including signed); no padding bits | none |
| `has_single_bit`, `bit_floor`, `bit_width` | unsigned integer | none; `x == 0` is defined |
| `bit_ceil` | unsigned integer | the result must be representable; violation is UB, and an error in constant evaluation |
| `shl`, `shr` | signed or unsigned integer | none; negative or huge shift amounts are defined; not implemented in libc++ |
| `rotl`, `rotr` | unsigned integer | none; `s` may be negative and arbitrarily large |
| `countl_*`, `countr_*`, `popcount` | unsigned integer | none; for `x == 0`, `countl_zero` and `countr_zero` return the bit width |
| `bit_reverse`, `bit_compress`, `bit_expand` | unsigned integer | none; not implemented in libc++ |
| `bit_repeat` | unsigned integer | `l > 0`, an error in constant evaluation when violated; not implemented in libc++ |
| `endian` | | all three values equal when all scalars are 1 byte; on mixed-endian platforms `native` equals neither of the other two |
