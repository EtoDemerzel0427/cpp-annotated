---
title: Bitsets
summary: "std::bitset<N> is a bit sequence whose length is fixed at compile time: how bit positions map to integers and strings, the proxy class reference, which exceptions the constructors and accessors throw and when, and constexpr support since C++23."
updated: 2026-10-19
---

!!! tldr
    - Bit `pos` corresponds to `1 << pos` in an integer, so bit 0 is the least significant bit; when converting to and from strings, the rightmost character is bit 0.
    - Construction from an integer keeps the low bits, and construction from an overlong string keeps the leftmost characters: the two truncate in opposite directions.
    - `test`, `set(pos)`, `reset(pos)` and `flip(pos)` throw `out_of_range` when out of range; `operator[]` never throws when out of range, terminating in a hardened implementation and being UB otherwise.
    - Non-const `operator[]` returns a proxy object, `reference`; writing any bit through it counts, for data race purposes, as writing the whole bitset.
    - Since C++23 almost every member can be used in constant evaluation, except the stream operators and `hash`; a shift by N or more gives zero rather than UB.

```cpp run ok
#include <bitset>
#include <cstdio>

int main() {
  std::bitset<8> b("00010110");      // the rightmost character is bit 0
  std::printf("%d %d %lu\n", (int)b[1], (int)b[0], b.to_ulong());
  // 1 0 22
  std::bitset<4> t(0b1111'0101ULL);  // only the low 4 bits are kept
  std::printf("%s\n", t.to_string().c_str());   // 0101
}
```

`std::bitset<N>` is a sequence of N flag bits, with N as the template argument. It can read and write by position, apply AND, OR, NOT and shifts to the whole set, count the set bits, and convert to and from integers and strings like `"0101"`.

The number of bits is fixed at compile time, so it has no allocator, never grows, and has a fixed object size, usually N bits rounded up to a whole number of machine words. This is the fundamental difference from `std::vector<bool>` ([[vector.bool]]).

This page uses a few headings from the library clauses ([[structure.specifications]]): *Throws* lists the exceptions a function throws; if *Constraints* are not satisfied, the function does not participate in overload resolution; if *Hardened preconditions* are violated, a hardened implementation must terminate the program, and in other implementations it is UB.

## The header [bitset.syn]

¶1 `<bitset>` defines the class template `bitset` and several related functions. The synopsis includes `<string>` and `<iosfwd>`, because `to_string` returns a `basic_string` and the stream operators use `basic_istream` and `basic_ostream`. So `<bitset>` is not a lightweight header, and it is not among the parts a freestanding implementation must provide (compare [[bit]]).

The non-member `&`, `|` and `^` are all `constexpr` and `noexcept`; the stream operators are neither.

## Numbering of bits [template.bitset.general]

¶1 `bitset<N>` stores a sequence of N bits.

¶2 Each bit has the value 0 (reset) or 1 (set). Changing a 0 to 1 or a 1 to 0 is called **toggling**, the word used to describe both `flip` and `^=`. Each bit has a non-negative position `pos`:

!!! std
    When converting between an object of type `bitset<N>` and a value of some integral type, bit position `pos` corresponds to the *bit value* `1 << pos`.

When converting to and from integers, position `pos` corresponds to the bit value `1 << pos`, and the integer corresponding to several bits is the sum of their bit values. So bit 0 is the least significant bit and bit N−1 the most significant. This is a numeric correspondence, unrelated to byte order or memory layout; the standard does not specify how `bitset` stores its bits internally.

When converting to and from strings ([bitset.cons] ¶4, [bitset.members] ¶41), the last character corresponds to bit 0 and positions increase to the left, consistent with how binary numbers are written: `"0110"` means 6, with `b[1]` and `b[2]` being 1.

So the index of `b[i]` counts from the low end, while the characters of `to_string()` count from the high end. Treating the `i`th character of `to_string()` as `b[i]` is the most common mistake.

## Construction [bitset.cons]

### From an integer (¶1–2)

¶1 The default constructor clears all bits.

¶2 `bitset(unsigned long long val)` copies in the low M bits of `val`, where M is the smaller of N and the number of bits in the value representation ([[g:value-representation]], [[basic.types]]) of `unsigned long long`. If N is larger, the remaining bits are cleared; if N is smaller, the high bits are simply discarded without reporting any error.

This constructor is not explicit, so any integer converts implicitly to a `bitset`. `std::bitset<8> b = -1;` is valid: `-1` is first converted to `ULLONG_MAX`, then the low 8 bits are taken, giving all 8 bits set.

### From a string (¶3–9)

The three string constructors are all explicit:

1. `bitset(const basic_string<charT, traits, Allocator>& str, pos = 0, n = npos, zero = '0', one = '1')`
2. `bitset(basic_string_view<charT, traits> str, pos = 0, n = npos, zero = '0', one = '1')` {{c++26}} ([[P2697R1]])
3. `bitset(const charT* str, n = npos, zero = '0', one = '1')`

<div class="compare" markdown="1">

```cpp run ok
#include <bitset>
std::bitset<8> a = 5;
// OK: the integer constructor is not explicit
int main() {}
```

```cpp run error
#include <bitset>
std::bitset<8> b = "101";
// error: the string constructor is explicit
```

</div>

The first two share one set of rules:

- ¶3 The effective length `rlen` is the smaller of `n` and `str.size() - pos`; only the first M bits are initialized, where M is the smaller of N and `rlen`.
- ¶4 For the characters starting at `pos`, a character equal to `zero` maps to 0 and anything else to 1. The character at position `pos + M - 1` corresponds to bit 0, and characters further left correspond to successively higher bits.
- ¶5 If M is less than N, the remaining bits are cleared.
- ¶6 Characters are compared with `traits::eq`.
- ¶7 If `pos > str.size()`, `out_of_range` is thrown; if any of the `rlen` characters is neither `zero` nor `one`, `invalid_argument` is thrown.

¶4 says anything not equal to `zero` is a 1, but ¶7 already guarantees that these `rlen` characters can only be `zero` or `one`, so no other character is taken as a 1.

¶7 checks all `rlen` characters, while ¶3 only uses the first M. When the string is longer than N, the leftmost N characters are used and the extra characters on the right are discarded, but they must still be valid. So `bitset<8>("1111000011")` gives `11110000`, not `11000011` with the low 8 bits kept; this is the opposite truncation direction from integer construction.

¶8–¶9 The *Constraints* of the `const charT*` version require `charT` not to be an array type, and to be trivially copyable, standard-layout and trivially default-constructible, that is, a character-like type. Its effect is specified as first constructing a `basic_string_view` and then delegating to constructor 2.

```cpp run ok
#include <bitset>
#include <cstdio>
#include <stdexcept>
#include <string>
#include <string_view>

int main() {
  std::bitset<8> s(std::string_view("xx101"), 2);  // starting at pos = 2
  std::printf("%s\n", s.to_string().c_str());      // 00000101
  std::bitset<8> trunc("1111000011");              // takes the leftmost 8 characters
  std::printf("%s\n", trunc.to_string().c_str());  // 11110000
  try { std::bitset<8> bad("10201"); }
  catch (const std::invalid_argument&) { std::puts("invalid_argument"); }
  try { std::bitset<8> bad(std::string("101"), 4); }
  catch (const std::out_of_range&) { std::puts("out_of_range"); }
}
```

### Three kinds of errors ([template.bitset.general] ¶13)

¶13 The functions in this subclause can report three kinds of errors, each corresponding to an exception: *invalid-argument* to `invalid_argument`, *out-of-range* to `out_of_range`, and *overflow* to `overflow_error`. The *Throws* elements of the individual functions use these three exceptions.

## The proxy class `reference` [template.bitset.general]

```cpp run ok
#include <bitset>
#include <cassert>
#include <type_traits>

int main() {
  std::bitset<8> b;
  auto r = b[3];   // bitset<8>::reference, not bool
  static_assert(!std::is_same_v<decltype(r), bool>);
  r = true;        // modifies b
  assert(b.test(3));

  b[0] = true;
  swap(b[0], b[1]);   // ADL finds reference's friend swap
  assert(!b[0] && b[1]);
}
```

The smallest addressable unit in C++ is the byte ([[intro.memory]]), and there is no reference to a single bit, so non-const `operator[]` cannot return `bool&`. It returns a **proxy object** ([[g:proxy-reference]]) of type `bitset<N>::reference`, which typically records internally which word the bit is in and the corresponding mask. ¶3 says it is a class that simulates a reference to a single bit.

Its members correspond to the operations a reference should have:

| Operation | Paragraph | Effect |
|---|---|---|
| copy construction | ¶4 | the new proxy refers to the same bit |
| destruction | ¶5 | does nothing |
| `operator=(bool)`, `operator=(const reference&)`, `operator=(bool) const` | ¶6–7 | sets or clears according to `bool(x)`, returns `*this`; the second supports `b[i] = b[j]` |
| `operator bool()` | ¶8 | reads the bit |
| `operator~()` | ¶9 | returns `!bool(*this)`, of type `bool`, without modifying the bit |
| three friend `swap`s | ¶10 | swap the bits referred to by two proxies, or by a proxy and a `bool&` |
| `flip()` | ¶11–12 | equivalent to `*this = !*this` |

The const-qualified assignment operator modifies the bit the proxy refers to, not the proxy itself, just as `int* const p` still allows `*p = 1`. With it, a `const reference` can also be assigned to; `vector<bool>::reference` has the same member.

`reference` has no default constructor: a proxy only makes sense when it refers to some bit. `swap` is a friend and can only be found by argument-dependent lookup ([[basic.lookup.argdep]]), so you must write the unqualified `swap(b[0], b[1])`. The general `std::swap` in the standard requires lvalues and does not accept prvalues such as `b[0]`; libc++ additionally provides a `swap` for proxies in namespace `std`, so `std::swap(b[0], b[1])` also compiles on libc++, but this is not guaranteed by the standard.

!!! pitfall "`auto` deduces the proxy, not `bool`"
    In `auto r = b[3];`, `r` has type `bitset<8>::reference`, and a later `r = true` modifies `b`. If `b` is destroyed before `r`, `r` dangles. When you need an independent boolean value, write `bool r = b[3];` or `auto r = b.test(3);`. `vector<bool>` has the same problem.

## Member functions [bitset.members]

### Whole-set bitwise operations and shifts (¶1–12)

¶1–¶6 `&=`, `|=` and `^=` operate bit by bit. ¶7–¶10 `<<=` takes the new value at position I from the old I − pos, and `>>=` from I + pos, filling with 0 where that is out of range. ¶11–¶12 `<<` and `>>` copy first and then perform the compound assignment. These functions are all `noexcept`.

Unlike shifts of built-in integers ([[expr.shift]]), a shift by N or more is not UB. ¶7.1 and ¶9.1 directly specify that the new value is 0 in that case, so `b << 1000` is valid and gives all zeros, whereas for a 32-bit `unsigned`, `1u << 32` is undefined behavior.

### `set`, `reset`, `flip` (¶13–29)

The versions without arguments act on all bits and are `noexcept`. The versions taking `pos` throw `out_of_range` when `pos` is not a valid position (¶17, ¶22, ¶29), and so are not marked `noexcept`. ¶23–¶24 `operator~()` returns a copy with all bits toggled.

### `operator[]` and `test` (¶30–36, ¶46–47)

| Access | Out of range |
|---|---|
| `b.test(pos)` | throws `out_of_range` (¶47) |
| `b.set(pos)`, `b.reset(pos)`, `b.flip(pos)` | throws `out_of_range` |
| `b[pos]` | terminates the program in a hardened implementation, {{ub}} otherwise |

¶30 and ¶33: the hardened precondition of both `operator[]`s is `pos < size()`, and ¶32 and ¶35 further specify that they throw no exceptions. So out-of-range `operator[]` never throws; its relationship to `test` is like that between `vector`'s `operator[]` and `at`. libc++ checks this condition when hardening is enabled.

¶31 The const version returns `bool`. ¶34 The proxy returned by the non-const version satisfies `(*this)[pos] == this->test(pos)`, and `(*this)[pos] = val` is equivalent to `this->set(pos, val)`.

!!! lawyer "Writing one bit is writing the whole bitset (¶36)"
    For the purpose of determining data races ([[intro.multithread]]), any read or write through the proxy returned by `operator[]` may access or modify the entire `bitset`. So two threads that write `b[0]` and `b[1]` of the same bitset respectively have a data race even though the positions differ, and the behavior is undefined. The reason is that modifying one bit requires a read-modify-write of the whole word. Different elements of a `vector<T>` can be modified concurrently, but `vector<bool>` is likewise an exception ([[container.requirements.dataraces]]).

### Converting to integers and strings (¶37–42)

¶37–¶40 `to_ulong()` and `to_ullong()` return the integer value defined in ¶2. If that value cannot be represented in the target type, `overflow_error` is thrown. The criterion is the value, not N: for a `bitset<100>`, `to_ullong()` returns normally as long as all bits above bit 63 are 0.

```cpp run ok
#include <bitset>
#include <cstdio>
#include <stdexcept>

int main() {
  std::bitset<100> small(42);
  std::printf("%llu\n", small.to_ullong());   // 42
  std::bitset<100> big;
  big.set(70);
  try { (void)big.to_ullong(); }
  catch (const std::overflow_error&) { std::puts("overflow_error"); }
}
```

¶41–¶42 `to_string(zero, one)` constructs a string of length exactly N, in which the character at position N−1 corresponds to bit 0. The direction matches the string constructors, so `bitset<N>(b.to_string()) == b` always holds.

### Queries (¶43–50)

¶43 `count()` returns the number of set bits, ¶44 `size()` returns N, ¶45 `operator==` compares bit by bit, and ¶46 `test(pos)` reads one bit. ¶48–¶50 `all()`, `any()` and `none()` are `count() == size()`, `count() != 0` and `count() == 0` respectively.

`operator!=` is not in the synopsis; since C++20 it is provided by the rewritten candidates of `==` ([[over.match.oper]]). `bitset` has no `operator<` and no iterators, so it cannot be used directly as a key of `std::set`, nor in a range-based `for`.

`bitset<0>` is valid: `size()` is 0, `all()` and `none()` are both true, and `to_ullong()` returns 0.

## Hashing and non-member operators

[bitset.hash] ¶1 `hash<bitset<N>>` is an enabled specialization ([[unord.hash]]), so `bitset` can be used directly as a key of `unordered_set` and `unordered_map`. The standard does not specify what the hash value is.

[bitset.operators] ¶1–¶3 `&`, `|` and `^` copy `lhs` and then perform the compound assignment. They are function templates whose two parameters are both `bitset<N>`. Template argument deduction does not consider user-defined conversions ([[temp.deduct.call]]), so `b & 1` cannot deduce N and does not compile; write `b & std::bitset<8>(1)` instead.

¶4–¶7 `operator>>` is a formatted input function that extracts at most N characters. It stops at end-of-file or when the next character is neither `widen('0')` nor `widen('1')`, and that character is not extracted. Then it does `x = bitset<N>(str)`. If N is greater than 0 but no characters at all were read, it sets `failbit`.

¶8 `operator<<` outputs the result of `to_string`, with `'0'` and `'1'` widened using the `ctype` of the stream's locale.

## Use in constant evaluation

Since C++11, the default constructor, the integer constructor, const `operator[]` and `size()` have been `constexpr`. C++23's [[P2417R2]] made the rest of the members `constexpr`, including string construction, `to_string`, `to_ulong` and the operations of the proxy `reference`; the feature-test macro `__cpp_lib_constexpr_bitset` is `202207L`. The only things still not `constexpr` are the stream operators and `hash`.

```cpp run ok
#include <bitset>

constexpr std::bitset<16> make() {
  std::bitset<16> b("1010");   // usable in constant evaluation since C++23
  b[15] = true;                // proxy assignment
  b <<= 1;                     // bit 15 is shifted out
  return b.flip(0);
}
static_assert(make().to_ulong() == 0b10101);
static_assert(std::bitset<8>(-1).count() == 8);

int main() {}
```

A path that throws an exception cannot appear in a constant expression ([[expr.const]]), so invalid input is caught at compile time:

```cpp run error
#include <bitset>
constexpr std::bitset<8> bad("1012");
// error: the constructor would throw invalid_argument; not a constant expression
```

!!! impl "The libc++ implementation"
    libc++ keeps the storage in a private base class `__bitset<words, N>`, with `size_t` as a word, and specializes the cases of 0 words and 1 word. On 64-bit platforms, `bitset<64>` is just one `size_t`, and every operation is a single integer instruction. The proxy `reference` shares the template `__bit_reference` with `vector<bool>`, so the two behave almost identically. `hash` returns the stored word directly in the single-word case and XORs the words together in the multi-word case.

## `bitset` versus `vector<bool>`

| | `bitset<N>` | `vector<bool>` ([[vector.bool]]) |
|---|---|---|
| Number of bits | a compile-time constant | determined at run time, can grow |
| Storage | inside the object, no allocation | on the heap via the allocator |
| Constant evaluation | almost everything since C++23 | since C++20 (allocations must be freed before evaluation ends) |
| Iterators | none | yes (proxy iterators) |
| Whole-set bitwise operations | `&`, `|`, `^`, `~`, `<<`, `>>` | only `flip()` |
| Conversion to/from integers and strings | yes | no |
| Out-of-range access | `test` throws, `[]` has a hardened precondition | `at` throws, `[]` has a hardened precondition |

Use `bitset` when the number of bits is fixed and you need whole-set operations or conversion to integers; use `vector<bool>` when the number of bits is only known at run time.

## Questions

!!! question "Question 1"
    What are the values of `std::bitset<4>("101100")` and `std::bitset<4>(0b101100)`? Why are they different?

<details markdown="1">
<summary>Answer</summary>

The string version: `rlen = 6`, M = min(4, 6) = 4, and the first 4 characters `"1011"` are used, with the last of them corresponding to bit 0, so the result is `1011` ([bitset.cons] ¶3–4).

The integer version: the low 4 bits of `val` are taken (¶2), and the low 4 bits of `0b101100` are `1100`.

String truncation keeps the characters at the left end, that is, the high end; integer truncation keeps the low bits. The directions are opposite.
</details>

!!! question "Question 2"
    Two threads execute `b[0] = true;` and `b.set(1);` respectively, where `b` is the same `std::bitset<64>`. Is there a data race?

<details markdown="1">
<summary>Answer</summary>

Yes. [bitset.members] ¶36 specifies that a write through the proxy may modify the entire bitset, and `set(1)` also modifies `b`; there is no synchronization between them, so by [[intro.multithread]] this is a data race and the behavior is undefined. If the two threads wrote to two different `bitset` objects, there would be no conflict.
</details>

!!! question "Question 3"
    Why does `b & std::bitset<8>(1)` compile but `b & 1` not?

<details markdown="1">
<summary>Answer</summary>

The non-member `operator&` is declared as `template<size_t N> bitset<N> operator&(const bitset<N>&, const bitset<N>&)`. For `b & 1`, the second argument `int` cannot deduce N, and deduction does not consider the implicit conversion through the integer constructor ([[temp.deduct.call]]), so the template is not viable; there are no other candidates, and the program is ill-formed. When both sides are `bitset<8>`, deduction succeeds.
</details>
