---
title: Character literals
summary: "The five prefixes of character literals and their types, the three kinds of escape sequences, how the value is determined (the encoded result must be exactly one code unit), and multicharacter literals."
updated: 2026-10-19
---

!!! tldr
    - The prefix determines the type: `'a'` is `char`, `L'a'` is `wchar_t`, `u8'a'` is `char8_t`, `u'a'` is `char16_t`, `U'a'` is `char32_t`. In C, `'a'` is an `int`; in C++ it is not.
    - A character must encode to exactly one code unit, otherwise the literal is ill-formed: under UTF-8, `'é'` and `u8'é'` are both invalid, while `U'😀'` is valid.
    - `'é'` writes a character, which the compiler encodes; `'\xE9'` writes the value of a code unit, which is not encoded.
    - An octal escape has at most three digits, and `\x` swallows every hexadecimal digit after it; C++23's `\x{...}` and `\o{...}` give explicit bounds.
    - A multicharacter literal such as `'ab'` has type `int`, is conditionally-supported, has an implementation-defined value, and cannot have a prefix.

Character literals and string literals ([[lex.string]]) share the two mechanisms of encoding prefixes and escape sequences, so this page is also the foundation for understanding string literals. Two terms are used often below, both defined in [[lex.charset]]: a **code unit** is an integer value of some character type, for example one byte of UTF-8; the **literal encoding** is the encoding the compiler uses to convert the characters in the source into a sequence of code units, and the one used for ordinary literals is called the **ordinary literal encoding**, UTF-8 by default in GCC and Clang.

## Prefixes and types (¶2)

```cpp run title="ccon-types.cpp" ok
#include <type_traits>
static_assert(std::is_same_v<decltype('a'), char>);       // int in C
static_assert(std::is_same_v<decltype(L'a'), wchar_t>);
static_assert(std::is_same_v<decltype(u8'a'), char8_t>);  // char in C++17
static_assert(std::is_same_v<decltype(u'a'), char16_t>);
static_assert(std::is_same_v<decltype(U'a'), char32_t>);
int main() {}
```

¶2 The kind, type and associated character encoding of a character literal are determined by its encoding prefix and the content between the quotes:

| Prefix | Kind | Type | Associated encoding |
|---|---|---|---|
| none | ordinary character literal | `char` | ordinary literal encoding |
| none (several characters) | multicharacter literal | `int` | ordinary literal encoding |
| `L` | wide character literal | `wchar_t` | wide literal encoding |
| `u8` | UTF-8 character literal | `char8_t` | UTF-8 |
| `u` | UTF-16 character literal | `char16_t` | UTF-16 |
| `U` | UTF-32 character literal | `char32_t` | UTF-32 |

In C the type of `'a'` is `int`; C++ changed it to `char`. The reason [[diff.lex]] gives is overloading: given `f(int)` and `f(char)`, `f('x')` should pick the latter. The cost is that `sizeof('x')` differs between the two languages.

`u8'x'` was `char` in C++17 and is `char8_t` since C++20 ([[P0482R6]], [[diff.cpp17.lex]]). With a distinct type, overloads and templates can tell UTF-8 data apart from text stored in the ordinary literal encoding.

## Escape sequences

Each item between the quotes is either an ordinary character, an escape sequence, or a universal-character-name (such as `\u00E9`, see [[lex.universal.char]]). Escape sequences come in three kinds with different meanings:

| Kind | Examples | What it represents |
|---|---|---|
| simple escape | `\n` `\t` `\\` `\'` `\"` `\?` `\a` `\b` `\f` `\r` `\v` | a character, encoded with the literal encoding |
| numeric escape | `\0` `\101` `\o{101}` `\x41` `\x{41}` | the value of a code unit, not encoded |
| conditional escape | `\e` `\q` `\8` | conditionally-supported, implementation-defined value |

The key is to distinguish characters from code unit values. `'é'` represents the character é, which the compiler needs two bytes to encode in UTF-8, so it is ill-formed (see ¶3.1 below). `'\xE9'` represents only a code unit with the value 0xE9; no encoding is involved, so it is valid.

### Length of numeric escapes

An octal escape is `\` followed by one to three octal digits, at most three: `"\1012"` is `\101` (that is, `A`) followed by the character `2`. `\0` is also just an octal escape, with no special status.

A hexadecimal escape `\x` has no length limit and swallows every hexadecimal digit after it. `"\x41BC"` is a single escape with value 0x41BC, out of range for `char`, and ill-formed.

C++23 added the braced forms `\o{...}` and `\x{...}` ([[P2290R3]]), whose bounds are set by the braces: `"\x{41}BC"` is simply `"ABC"`. Before that, the only way to cut an escape short was to split the string into two adjacent literals, since the escape sequences of each are interpreted separately ([[lex.string]]).

```cpp run title="escapes.cpp" ok
static_assert('\101' == 'A' && '\o{101}' == 'A' && '\x{41}' == 'A');
static_assert('\0' == 0 && '\012' == '\n');  // \012 is octal 12, i.e. 10
static_assert(sizeof("\1012") == 3);         // A, 2, null character
static_assert(sizeof("\x{41}BC") == 4);      // A, B, C, null character
static_assert(sizeof("\x41" "BC") == 4);     // the pre-C++23 way
int main() {}
```

### Simple escapes (¶4)

¶4 The characters represented by simple escapes are: `\n` new-line (U+000A), `\t` horizontal tab, `\v` vertical tab, `\b` backspace, `\r` carriage return, `\f` form feed, `\a` alert, `\\` backslash, `\?` question mark, `\'` single quote and `\"` double quote.

Note 1 explains that `\?` is kept for compatibility with C++14 and C. It was originally used to avoid trigraphs: in C++14 `??/` was replaced by `\`, so to write two question marks followed by a slash you had to write `?\?/`. Since C++17 removed trigraphs, `\?` is just `?`.

A single quote in a string and a double quote in a character literal need not be escaped (`"'"` and `'"'` are both valid), but escaping them is not wrong either.

### Conditional escapes

`\` followed by a basic character that has not been given a meaning, such as `\e`, `\q` or `\8`, forms a **conditional escape**. It is conditionally-supported (an implementation may not support it, but must diagnose it if it does not), with an implementation-defined value.

`N`, `o`, `u`, `U` and `x` cannot form conditional escapes, because they introduce `\N{...}`, `\o{...}`, `\u`, `\U` and `\x` respectively. So a `'\N'` without the following `{` is ill-formed, not conditionally-supported. `8` and `9` are not octal digits, so `\8` is a conditional escape.

Clang 23 treats `\e` as ESC (0x1B) and gives a "use of non-standard escape character" warning under `-pedantic`. For `\q` and `\8` it gives a `-Wunknown-escape-sequence` warning and takes the character itself.

## The value (¶3)

¶3 The value of a multicharacter literal is implementation-defined; the value of any other character literal is determined by one of the following three cases.

### A single character: the encoded code unit (¶3.1)

¶3.1 If the content between the quotes is a single ordinary character, simple escape or universal-character-name, the value is that character's code unit in the associated encoding. If the associated encoding cannot represent the character, or needs more than one code unit for it, the program is ill-formed.

```cpp title="ccon-encode.cpp" error
char8_t  a = u8'é';   // error: the UTF-8 encoding of é needs two code units
char16_t b = u'😀';   // error: U+1F600 needs two code units in UTF-16
char     c = 'é';     // error: same as above when the ordinary literal encoding is UTF-8
char32_t d = U'😀';   // OK: UTF-32 is always one code unit
```

This rule guarantees that a character literal really does represent one character. For characters outside the BMP use `U'...'`; for the UTF-8 byte sequence of é use the string `u8"é"`. For the first three lines Clang 23 reports "character too large for enclosing character literal type".

### Numeric escapes: the given value, wrapped if necessary (¶3.2)

¶3.2 If the content between the quotes is a single numeric escape, let v be the integer represented by the digits in the escape:

- ¶3.2.2 If v is within the range of values of the literal's type, the value is v.
- ¶3.2.3 Otherwise, if the literal has no prefix or the prefix `L`, and v is within the range of the unsigned type corresponding to that type, the value is the value of that type congruent to v modulo 2^N (where N is the width of the type).
- ¶3.2.4 Otherwise, the program is ill-formed.

¶3.2.3 is for signed `char` and `wchar_t`. When `char` is signed, the v of `'\xFF'` is 255, outside [−128, 127] but within the range of `unsigned char`, so the value is −1. That is exactly what writing `'\xFF'` intends: a byte with all bits set. `char8_t`, `char16_t` and `char32_t` are all unsigned types and never need this rule.

```cpp run title="numeric-escape.cpp" ok
static_assert(u8'\xFF' == 0xFF);  // char8_t is unsigned, v is in range
static_assert(u'\xFFFF' == 0xFFFF);
// the signedness of wchar_t varies by platform
static_assert(L'\xFFFFFFFF' == -1 || L'\xFFFFFFFF' == 0xFFFFFFFF);
int main() {}
```

```cpp title="numeric-escape-bad.cpp" error
char     a = '\x100';     // error: outside the range of unsigned char
char8_t  b = u8'\x100';   // error: outside char8_t; the u8 prefix does not wrap
char16_t c = u'\x10000';  // error: outside char16_t
```

In C++20 and earlier, the value of an out-of-range numeric escape was implementation-defined. [[P2029R4]] in C++23 gave the precise rules above, and also specified that a numeric escape occupies exactly one code unit in a string.

### Conditional escapes (¶3.3)

¶3.3 A character literal consisting of a single conditional escape is conditionally-supported, with an implementation-defined value.

### Values in the preprocessor

The beginning of ¶3 also specifies that in translation phase 4 (preprocessing), the value of a character literal is determined using the range of representable values of its type in phase 7 (compilation). So the value of a character literal in `#if` is the same as in ordinary code, and so is the signedness of `char`:

```cpp run title="pp-char.cpp" impl
#if '\xFF' < 0
static_assert('\xFF' == -1);   // signed char: x86-64, Apple arm64
#else
static_assert('\xFF' == 255);  // unsigned char: AArch64 Linux, or -funsigned-char
#endif
int main() {}
```

Whether `char` is signed is implementation-defined ([[basic.fundamental]]). On x86 and x86-64, GCC, Clang and MSVC all make it signed; the AArch64 Linux ABI specifies unsigned; Apple arm64 makes it signed. GCC and Clang can switch with `-fsigned-char` and `-funsigned-char`.

## Multicharacter literals (¶1)

¶1 A literal with more than one character or escape between the quotes is called a **multicharacter literal**. It cannot have an encoding prefix; each of its items must be encodable as a single code unit in the ordinary literal encoding; and it is conditionally-supported. By ¶2 and ¶3, its type is `int` and its value is implementation-defined.

```cpp run title="multichar.cpp" impl
static_assert(sizeof('abcd') == sizeof(int));
static_assert('ab' == ('a' * 256 + 'b'));  // GCC, Clang: the first character is in the high-order position
int main() {}
```

Multicharacter literals are an old C tradition; classic Mac OS, for example, identified file types with four-character codes like `'TEXT'`. Their values are not portable, and Clang gives a `-Wmultichar` warning by default. `u'ab'`, `L'ab'`, and `'aé'` under UTF-8 are all ill-formed.

!!! history "C++23 removed wide multicharacter literals"
    In C++20, `L'ab'` was conditionally-supported with an implementation-defined value, and implementations disagreed: some took the first character, some the last. [[P2362R3]] judged it to have no portable use and made it ill-formed. The same paper also specified that characters not representable in the literal encoding are no longer conditionally-supported but simply ill-formed.

!!! lawyer "A leftover term: non-encodable character literal"
    [[lex.charset#4]] still says that characters in a character literal "other than a multicharacter or non-encodable character literal" are encoded with the literal encoding. The current [[lex.ccon]] no longer defines that term, and such literals have been ill-formed outright since C++23 (¶3.1), so the phrase refers to nothing well-formed; it is wording left behind by the revision.

## Implementation view

!!! impl
    - Wide characters: on Windows `wchar_t` is 16 bits and the wide literal encoding is UTF-16, so `L'😀'` is ill-formed; on Linux and macOS `wchar_t` is 32 bits and `L'😀'` is valid.
    - The ordinary literal encoding is implementation-defined. Without `/utf-8`, MSVC usually uses the system code page, such as Windows-1252, where `'é'` is a single byte and therefore valid; GCC and Clang use UTF-8 by default, where `'é'` is ill-formed. Portable code should use `u8`, `u` or `U` literals for non-ASCII characters.
    - Clang 23's diagnostics: for an out-of-range numeric escape, "hex escape sequence out of range" or "octal escape sequence out of range"; for `u'ab'`, "Unicode character literals may not contain multiple characters".

## Common misconceptions

!!! pitfall "Text can follow `\x1B` directly"
    `\x` swallows every hexadecimal digit after it. In `"\x1Bcolor"` the escape is `\x1Bc`, whose value 0x1BC is out of range for `char`, and compilation fails. With `U"\x1Bcafe"` it is more insidious: 0x1BCAFE fits in `char32_t`, so the string has only one character, and there is no diagnostic at all. Write `"\x{1B}color"` (C++23) or `"\x1B" "color"`.

!!! pitfall "`'\0'` is an escape dedicated to the null character"
    It is just a one-digit octal escape. So `"\012"` is a new-line (octal 12 is 10), not a null character followed by `12`.

## Questions

!!! question "Question 1"
    On x86-64 Linux (`char` is signed and the ordinary literal encoding is UTF-8), what are the types and values of the following literals? If one is ill-formed, why?

    ```cpp
    '\377'    '\u00FF'    u8'\377'    L'\xFFFFFFFFF'
    ```

<details markdown="1">
<summary>Answer</summary>

- `'\377'`: an octal numeric escape with v = 255, outside the range of `char` but within that of `unsigned char`, and with no prefix, so by ¶3.2.3 it wraps to −1, with type `char`.
- `'\u00FF'`: a universal-character-name for the character ÿ, whose UTF-8 encoding is the two code units C3 BF, so it is ill-formed by ¶3.1. `'\N{LATIN SMALL LETTER Y WITH DIAERESIS}'` is the same character and equally ill-formed.
- `u8'\377'`: a numeric escape with v = 255, within the range of `char8_t`, so the value is 255 with type `char8_t`. It represents a code unit with value 0xFF, not the character ÿ; a lone 0xFF is not even a valid byte in UTF-8.
- `L'\xFFFFFFFFF'`: v needs 36 bits, beyond the unsigned type corresponding to a 32-bit `wchar_t`, so it is ill-formed by ¶3.2.4.
</details>

!!! question "Question 2"
    Why does the wrapping rule of ¶3.2.3 apply only to the unprefixed and `L` forms?

<details markdown="1">
<summary>Answer</summary>

Only `char` and `wchar_t` can be signed types. `char8_t`, `char16_t` and `char32_t` are all unsigned, so exceeding the range of the type and exceeding the range of the corresponding unsigned type are the same thing, with no middle ground that needs wrapping. The wrapping rule exists so that the idiom of writing a byte bitwise, as in `'\xFF'`, has the definite value −1 on a signed `char`.
</details>
