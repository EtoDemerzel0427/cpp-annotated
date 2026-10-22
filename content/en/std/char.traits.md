---
title: Character traits
summary: "basic_string, string_view and iostreams compare and copy characters and represent end-of-file through a traits class; this page covers what traits must provide, what the five standard specializations specify, and how to write your own traits."
updated: 2026-10-19
---

!!! tldr
    - `basic_string`, `basic_string_view` and iostreams do not apply `==`, `<` or `memcpy` to characters directly; they call static members of the second template parameter, `traits`.
    - `char_traits<char>` compares characters as `unsigned char`, so `std::string` ordering agrees with `memcmp` and does not depend on whether `char` is signed.
    - `int_type` must hold every character plus one end-of-file value, `eof()`. Storing the result of `get()` in a `char` and then comparing it with `EOF` is a classic mistake; for `char16_t` and `char32_t`, `int_type` actually cannot hold that on mainstream platforms.
    - The optional traits member `comparison_category` determines the result type of `<=>`; it defaults to `weak_ordering`.
    - A custom comparison rule needs a traits class of your own that consistently overrides every comparison member; you may not specialize `std::char_traits` for types like `unsigned char`.

## What traits are [char.traits.general]

The full type of `std::string` is `std::basic_string<char, std::char_traits<char>, std::allocator<char>>`. The second template parameter is the **character traits** ([[g:character-traits]]): a class with only type members and static functions that tells the string how to compare two characters, how to compute the length of a zero-terminated sequence, how to copy in bulk, and what value represents end-of-file.

Putting these operations into a separate class has three benefits:

1. The comparison rule becomes part of the type. With the same `char`, a different traits gives you a case-insensitive string (see below), without passing a comparator to every call.
2. Bulk operations can be implemented directly with C library primitives. In the standard specializations, `length` is `strlen`, `compare` is `memcmp`, `copy` is `memcpy`.
3. iostreams need a type with one more value than the characters to represent end-of-file, namely `int_type`. That need has nothing to do with characters themselves, and traits is the natural place for it.

¶1 This subclause defines the requirements on traits classes and provides the class template `char_traits` with its five specializations: `char`, `char8_t`, `char16_t`, `char32_t`, `wchar_t`.

¶2 The templates in [[string.classes]], [[string.view]] and the iostreams of Clause 31 all take this set of types and functions from the template parameter `traits`.

¶3 A character type `C` and its traits class `X` are passed as a pair, as `charT` and `traits`, to these templates. If `X::char_type` is not `C`, the program is ill-formed. libc++ checks this with a `static_assert`:

```cpp error
#include <string>
std::basic_string<wchar_t, std::char_traits<char>> s;
// error: traits_type::char_type must be the same type as CharT
```

## What a traits class must provide [char.traits.require]

¶1 Table 87 lists the expressions a traits class `X` must support. There, `c` and `d` are characters, `p` and `q` are `const C*`, `s` is `C*`, `n` is `size_t`, `e` and `f` are `X::int_type`, and `r` is an lvalue of type `C`. Right after it comes a blanket requirement on all the expressions:

!!! std
    No expression which is part of the character traits requirements specified in [char.traits.require] shall exit via an exception.

So no traits operation may throw. In the standard specializations, functions like `compare`, `length` and `copy` are not marked `noexcept` (the library convention is not to mark functions that have preconditions), but they are not allowed to throw either. The strong exception guarantee of `basic_string` ([[basic.string]]) relies on this.

The expressions in the table fall into four groups.

**Type members**: `char_type` must be `C`; `int_type` is discussed below; `off_type` and `pos_type` are for stream positioning ([[iostreams.limits.pos]]); `state_type` is the state type for multibyte conversion.

**Single characters**, all constant complexity:

| Expression | Semantics |
|---|---|
| `X::eq(c, d)` | whether `c` is to be treated as equal to `d` |
| `X::lt(c, d)` | whether `c` is to be treated as less than `d` |
| `X::assign(r, d)` | `r = d` |

The wording says "is to be treated as": the traits decide the comparison rule themselves. This is where custom comparison is implemented.

**Character sequences**, all linear complexity:

| Expression | Semantics | Corresponding C function |
|---|---|---|
| `X::compare(p, q, n)` | compares the first `n` characters one by one with `eq` and `lt`, returns negative, 0 or positive | `memcmp` |
| `X::length(p)` | the first `i` for which `eq(p[i], C())` | `strlen` |
| `X::find(p, n, c)` | the first position in `[p, p+n)` equal to `c`, or a null pointer if none | `memchr` |
| `X::move(s, p, n)` | `assign` one by one; the ranges may overlap | `memmove` |
| `X::copy(s, p, n)` | `assign` one by one; precondition: the ranges do not overlap | `memcpy` |
| `X::assign(s, n, c)` | sets all `n` positions to `c` | `memset` |

`compare` looks only at the first `n` characters and does not stop at a null character; only `length` cares about null characters. Overlapping ranges in `copy` is the only source of {{ub}} in this group, the same rule as for `memcpy` ([[c.strings]]).

**`int_type`-related**, all constant complexity:

| Expression | Semantics |
|---|---|
| `X::eof()` | a value not equal (as judged by `eq_int_type`) to `to_int_type(c)` for any character |
| `X::not_eof(e)` | returns `e` if it is not `eof()`, otherwise some value that is not `eof()` |
| `X::to_char_type(e)` | the character `e` corresponds to, if any; otherwise an unspecified value |
| `X::to_int_type(c)` | maps a character to `int_type` |
| `X::eq_int_type(e, f)` | agrees with `eq` for values mapped from characters; true if both are `eof()`, false if only one is |

¶2 `<string>` declares the primary template `template<class charT> struct char_traits;` only as a basis for explicit specializations; the primary template itself has no definition. For the consequences, see `basic_string<unsigned char>` below.

## char compares as unsigned char [char.traits.specializations]

```cpp run ok
#include <string>
#include <cassert>

int main() {
  // '\xff' is greater than 'a' whether or not char is signed
  static_assert(!std::char_traits<char>::lt('\xff', 'a'));
  assert(std::string("\xff") > std::string("a"));
}
```

Whether `char` is signed is implementation-defined ([[basic.fundamental]]): signed on x86-64 and Apple arm64, unsigned on Linux AArch64. If `lt` compared `char` directly, the result of `"\xff" < "a"` would vary by platform.

!!! std
    The two-argument members `eq` and `lt` are defined identically to the built-in operators `==` and `<` for type `unsigned char`.

This rule in [char.traits.specializations.char] ¶2 makes `std::string` ordering platform-independent and consistent with C's `memcmp` and `strcmp` (the C standard specifies that they compare as `unsigned char`). ¶1 says that `state_type` is `mbstate_t` from `<cwchar>`.

For the other four specializations (`char8_t`, `char16_t`, `char32_t`, `wchar_t`), ¶1 of each says `assign`, `eq` and `lt` are the same as the built-in `=`, `==` and `<`; no special treatment is needed.

All five specializations are defined in `<string>`, all members are `constexpr`, the single-character and `int_type` operations are `noexcept`, and all of them define `comparison_category = strong_ordering`:

| Specialization | `int_type` | `eof()` | `pos_type` |
|---|---|---|---|
| `char_traits<char>` | `int` | `EOF` | `streampos` |
| `char_traits<char8_t>` | `unsigned int` | implementation-defined, not a valid UTF-8 code unit | `u8streampos` |
| `char_traits<char16_t>` | `uint_least16_t` | implementation-defined, not a valid UTF-16 code unit | `u16streampos` |
| `char_traits<char32_t>` | `uint_least32_t` | implementation-defined, not a Unicode code point | `u32streampos` |
| `char_traits<wchar_t>` | `wint_t` | `WEOF` | `wstreampos` |

## int_type and end-of-file [char.traits.typedefs]

¶1 `int_type` must be able to represent every value converted from a character, plus one end-of-file value, `eof()`. For `char_traits<char>`, `int_type` is `int` and `eof()` returns `EOF` ([char.traits.specializations.char] ¶3), which is −1 on almost every implementation. To avoid clashing with −1, `to_int_type('\xff')` must yield 255; implementations do this by converting to `unsigned char` first and then to `int`.

`istream::get()` returns exactly an `int_type`. Storing it in a `char` first and then comparing with `EOF` goes wrong:

```cpp run ok
#include <sstream>
#include <iostream>

int main() {
  std::istringstream in1("\xff" "abc"), in2("\xff" "abc");
  int n1 = 0, n2 = 0;

  char c;                                              // wrong
  while ((c = static_cast<char>(in1.get())) != EOF) ++n1;

  using T = std::char_traits<char>;
  for (T::int_type i; !T::eq_int_type(i = in2.get(), T::eof()); )
    ++n2;                                              // right

  std::cout << n1 << ' ' << n2 << '\n';                // with signed char: 0 4
}
```

When `get()` reads the byte 0xFF it returns 255; stored in a signed `char` that becomes −1, which is then promoted to `int` and compared with `EOF`, so the very first byte is taken for end-of-file. The code has no undefined behavior (since C++20 integer conversions are modulo 2^N); the logic is simply wrong. The right way is to keep the result of `get()` in an `int_type` the whole time and convert it to a character only after checking that it is not `eof()`.

`char_traits<char>` follows C's `getc`/`EOF` convention, which is why it uses a signed `int`. `char8_t` is a type new in C++20 ([[P0482R6]]) with no such baggage: its `int_type` is `unsigned int`, and `eof()` just has to be some value outside 0–255.

!!! lawyer "eof() does not fit for char16_t and char32_t"
    `char_traits<char16_t>::int_type` is `uint_least16_t`, which on mainstream platforms is 16 bits, the same as `char16_t`. Every `int_type` value corresponds to a `char16_t` value, so there is no value unequal to every `to_int_type(c)`, and Table 87's requirement on `eof()` cannot be met. `char32_t` with a 32-bit `uint_least32_t` is in the same situation.

    Implementations can only pick a value that is unlikely to appear. With libc++ in our tests, `eof()` for `char16_t` is 0xFFFF (U+FFFF is a Unicode noncharacter), and for `char32_t` it is 0xFFFFFFFF:

    ```cpp run ok
    #include <string>
    #include <cstdio>
    int main() {
      using T = std::char_traits<char16_t>;
      std::printf("%d\n", T::eq_int_type(T::to_int_type(u'\xFFFF'), T::eof()));   // prints 1 in our tests
    }
    ```

    Footnote 189 anticipates this: if `eof()` can be held in `char_type`, some iostreams operations can give surprising results. A `basic_istream<char16_t>` that reads the code unit 0xFFFF will think it has reached end-of-file. In practice few people use `char16_t` streams, and the standard library does not provide `istream`/`ostream` aliases for them.

¶2 `state_type` must be default constructible, copyable and destructible. All five standard specializations use `mbstate_t`, the conversion state of C's `mbrtowc` family ([[c.strings]], [[text.c.strings]]). `basic_string` and `basic_string_view` never use `state_type`, `off_type` or `pos_type`; those serve only `basic_filebuf` and `codecvt`.

## comparison_category determines the result of <=>

`comparison_category` is not in Table 87; it is an optional member. The `<=>` of `basic_string_view` looks it up ([[string.view.comparison#2]]):

- if it exists, it is the result type of `<=>`; it must be a comparison category type, otherwise the program is ill-formed;
- if it does not, the result type is `weak_ordering`.

`basic_string` comparisons forward to `basic_string_view`, with the same rule. All five standard specializations give `strong_ordering`.

The default is `weak_ordering` for the sake of custom traits. `strong_ordering` promises that equal values are substitutable ([[cmp.categories]]), and the most common use of custom traits is case-insensitive comparison, where `"Hello"` and `"HELLO"` are equal but not substitutable.

## Custom traits: a case-insensitive string

Only the four comparison-related members need changing: `eq`, `lt`, `compare`, `find`. The rest (`length`, `copy`, `move`, `assign`, `eof` and so on) can be inherited from `std::char_traits<char>`.

```cpp run ok title="ci_string.cpp"
#include <string>
#include <string_view>
#include <cctype>
#include <compare>
#include <iostream>
#include <type_traits>

struct ci_traits : std::char_traits<char> {
  static char up(char c) {
    return static_cast<char>(std::toupper(static_cast<unsigned char>(c)));
  }
  static bool eq(char a, char b) { return up(a) == up(b); }
  static bool lt(char a, char b) {
    return static_cast<unsigned char>(up(a)) < static_cast<unsigned char>(up(b));
  }
  static int compare(const char* p, const char* q, std::size_t n) {
    for (std::size_t i = 0; i != n; ++i) {
      if (lt(p[i], q[i])) return -1;
      if (lt(q[i], p[i])) return 1;
    }
    return 0;
  }
  static const char* find(const char* p, std::size_t n, const char& c) {
    for (; n != 0; --n, ++p)
      if (eq(*p, c)) return p;
    return nullptr;
  }
  using comparison_category = std::weak_ordering;   // equal does not mean substitutable
};

using ci_string = std::basic_string<char, ci_traits>;

int main() {
  ci_string s = "Hello World";
  std::cout << (s == "HELLO world") << ' '
            << (s.find("WORLD") != ci_string::npos) << '\n';      // 1 1
  static_assert(std::is_same_v<decltype(s <=> s), std::weak_ordering>);
  std::cout << std::string_view(s.data(), s.size()) << '\n';     // switch back to the default traits for output
}
```

Some things to watch when writing custom traits:

- Override the comparison members together. The members of `char_traits<char>` are static functions, not virtual ones; when `basic_string` calls `traits::compare` it finds the same-named version in the derived class, and anything not overridden comes from the base. Override `eq` but not `compare`, and `==` is still case-sensitive; see Question 2.
- The argument to `std::toupper` must be representable as `unsigned char` or equal `EOF`; passing a negative `char` is {{ub}}, hence the conversion to `unsigned char` first.
- `std::cout << s` does not compile: `operator<<` requires the stream's traits to match the string's, which would need a `basic_ostream<char, ci_traits>`. The example converts to a `string_view` with the default traits before output.
- `ci_string` and `std::string` are different types; `std::string b = s;` is ill-formed, and you have to write `std::string(s.data(), s.size())`. This inconvenience is why few people use custom traits today; case-insensitive comparison is usually written as a comparison function or a transparent comparator.
- The members here are not `constexpr`, so `ci_string` cannot be used in constant evaluation.

## Why there is no basic_string<unsigned char>

```cpp error
#include <string>
std::basic_string<unsigned char> s;
// error: implicit instantiation of undefined template 'std::char_traits<unsigned char>'
```

`basic_string<unsigned char>` needs `std::char_traits<unsigned char>`, but the primary template is only declared ([char.traits.require] ¶2) and the standard does not provide that specialization. A program cannot add it either: [[namespace.std]] permits adding a specialization to `std` only when it depends on a program-defined type, and `unsigned char` is not program-defined. The same goes for `std::byte` and `int`.

The only legal approach is to write your own traits class and pass it as the second template argument. Early versions of libc++ provided a definition of the primary template for arbitrary types as an extension, later removed.

## History

!!! history
    - Since C++17, the members of the standard specializations are all `constexpr` ([[P0426R1]]), so `std::string_view` can compare and search during constant evaluation.
    - C++20 added `char8_t` and `char_traits<char8_t>` ([[P0482R6]]).
    - C++20 added `comparison_category`, and the string comparison operators became `==` and `<=>` ([[P1614R2]]).

## Questions

!!! question "Question 1"
    Does the comparison `std::string("a\0b", 3) == std::string("a\0c", 3)` stop at the `'\0'`?

<details markdown="1">
<summary>Answer</summary>

No; the result is `false`. `basic_string` comparison ends up calling `traits::compare(p, q, n)`, where `n` is the smaller of the two lengths ([[string.view.ops#12]]). In Table 87, `compare` just compares one by one with `eq` and `lt` and knows nothing of null characters, so it concludes `'b' < 'c'` at the third character. It is C functions like `strcmp` that stop at `'\0'`.
</details>

!!! question "Question 2"
    A custom traits overrides only `eq` and `lt`, not `compare`. Which kind of equality does `s1 == s2` use?

<details markdown="1">
<summary>Answer</summary>

The inherited `char_traits<char>::compare`, which is case-sensitive. The `==` of `basic_string_view` is defined as `compare(rhs) == 0` ([[string.view.comparison#1]]), and `compare` calls `traits::compare` ([[string.view.ops#12]]); `eq` is never used directly. But `find(charT)` uses `traits::find` and `starts_with(charT)` uses `traits::eq`, so the same string type ends up with two standards of equality.

Table 87 requires the results of `compare` to be determined by `eq` and `lt`, so such a traits class does not meet the requirements. Per [[res.on.functions#1]], when a standard library template is instantiated with a type that does not meet its requirements, the standard places no requirements on the result, which amounts to {{ub}}.
</details>

!!! question "Question 3"
    What does `char_traits<char>::to_char_type(char_traits<char>::eof())` return?

<details markdown="1">
<summary>Answer</summary>

Table 87 says that when `e` corresponds to no character, `to_char_type(e)` returns an unspecified value. `eof()` corresponds to no character by definition, so the result is unspecified. libc++ simply converts −1 to `char`, giving `'\xff'`. So once converted to `char`, `eof()` and the character 0xFF are indistinguishable, and the check must be done with `eq_int_type` before converting.
</details>
