---
title: Character sets and universal-character-names
summary: Characters in source code are Unicode characters (the translation character set); the values a literal becomes at run time are determined by the literal encoding; the universal-character-names \u, \U, \u{} and \N{} can write any character in ASCII.
updated: 2026-10-19
---

!!! tldr
    - Every character in the source is an element of the translation character set, which is exactly the set of Unicode scalar values. After phase 1, the compiler sees only Unicode.
    - What values a literal has at run time is determined by the literal encoding: `u8`, `u` and `U` are fixed as UTF-8, UTF-16 and UTF-32; no prefix and `L` are implementation-defined.
    - For implementation-defined encodings the standard guarantees only a few things: each basic character takes one non-negative code unit, the null character is 0, and the digits `0`–`9` are contiguous. `'A' == 65` is not among them.
    - Universal-character-names come in four forms, `\u03B1`, `\U000003B1`, `\u{3B1}` and `\N{GREEK SMALL LETTER ALPHA}`; outside literals they cannot be used to write ASCII characters or control characters.
    - Surrogate code points are not scalar values, so an emoji written as split UTF-16 halves, like `\uD83D\uDE00`, is ill-formed.

## Characters in the source and bytes at run time

```cpp run title="two-sides.cpp" ok
const char*     a = "é";     // the bytes at run time are determined by the ordinary literal encoding
const char8_t*  b = u8"é";   // always UTF-8: 0xC3 0xA9
const char32_t* c = U"é";    // always UTF-32: 0xE9
static_assert(sizeof(u8"é") == 3 && sizeof(U"é") == 2 * sizeof(char32_t));
int main() {}
```

The same `é` becomes three different sets of values in the three literals. Two independent questions are involved: how the compiler understands this character in the source, and what values the literal is stored as in the program. [[lex.char]] separates them with two sets of concepts: on the source side the translation character set, on the run-time side the literal encoding.

This subclause was entirely rewritten in C++23 ([[P2314R4]]). The earlier standard had a tangle of concepts such as the basic source character set, the execution character set and the extended source character set, and non-ASCII characters in the source had to be replaced by universal-character-names in phase 1 before being processed. None of that exists any more.

## The translation character set ([[lex.charset]] ¶1)

¶1 The elements of the [[g:translation-character-set|translation character set]] are:

- ¶1.1 each abstract character in Unicode that is assigned a code point;
- ¶1.2 a distinct character for each Unicode scalar value not assigned to an abstract character.

Note 1 reviews the Unicode terminology. A **code point** is an integer in the range 0 to 0x10FFFF; a **surrogate code point** is one in 0xD800 to 0xDFFF, which UTF-16 uses in pairs to represent characters above 0xFFFF; a **scalar value** is any code point that is not a surrogate code point.

So the translation character set corresponds one-to-one with the Unicode scalar values. ¶1.2 lets code points with no assigned character be written too, so that C++'s rules need not change when Unicode adds characters. Surrogate code points are not included; they are only an encoding device of UTF-16, not characters.

Phase 1 ([[lex.phases]]) decodes a UTF-8 source file into scalar values and maps them to the translation character set; files in other encodings are mapped in an implementation-defined manner. From then on, the source is a sequence of Unicode characters.

## The basic character set (¶2)

¶2 The [[g:basic-character-set|basic character set]] is 99 characters of the translation character set:

- 4 control characters: character tabulation U+0009, line tabulation U+000B, form feed U+000C, line feed U+000A;
- space U+0020;
- 52 letters `A`–`Z`, `a`–`z`, and 10 digits `0`–`9`;
- 32 punctuation characters: `!` `"` `#` `$` `%` `&` `'` `(` `)` `*` `+` `,` `-` `.` `/` `:` `;` `<` `=` `>` `?` `@` `[` `\` `]` `^` `_` `` ` `` `{` `|` `}` `~`.

That is, the 95 printable ASCII characters plus 4 whitespace control characters. Note 2 says that the Unicode names in the table only identify which character is meant; the numeric value of the code point has no other significance here. The standard does not require the value of `'A'` to be 65.

{{c++26}} `$`, `@` and `` ` `` were added in C++26 ([[P2558R2]]); the C++23 basic character set had only 96 characters. No grammar uses these three characters yet; the effect of adding them is elsewhere: outside literals they can no longer be written with universal-character-names (see ¶1 below), and every literal encoding must encode them as a single code unit (¶5).

## The basic literal character set (¶3)

¶3 The [[g:basic-literal-character-set|basic literal character set]] is the basic character set plus 4 more control characters: null U+0000, alert U+0007, backspace U+0008 and carriage return U+000D.

Literals can write these 4 characters with the escape sequences `\0`, `\a`, `\b` and `\r`, so every encoding must be able to represent them. They are not in the basic character set because they should not appear in source outside literals (carriage return has already been normalized to new-line in phase 1).

## Code units and literal encodings (¶4)

¶4 A [[g:code-unit|code unit]] is an integer value of a character type ([[basic.fundamental]]). The characters in a character literal or string literal are encoded into one or more code units in the way determined by the encoding prefix ([[lex.ccon]], [[lex.string]]); this is called the [[g:literal-encoding|literal encoding]] of that literal. Multicharacter literals `'ab'` and character literals that cannot be encoded are excluded.

| Prefix | Literal encoding | Code unit type |
|---|---|---|
| none | ordinary literal encoding | `char` |
| `L` | wide literal encoding | `wchar_t` |
| `u8` | UTF-8 | `char8_t` |
| `u` | UTF-16 | `char16_t` |
| `U` | UTF-32 | `char32_t` |

The literal encoding operates at compile time: it determines which bytes the compiler writes into the object file for `"é"`. The encoding a program uses to process text at run time is a different matter: it is locale-dependent and called the encoding of the execution character set ([[character.seq]]), and the two need not be the same. GCC's `-fexec-charset=` and MSVC's `/execution-charset:` change the ordinary literal encoding, not the program's run-time locale.

## What an encoding must satisfy (¶5)

¶5 The literal encodings, and the locale-dependent encoding of the execution character set, must all satisfy:

1. each character of the basic literal character set is encoded as a single code unit with a non-negative value, distinct from all others;
2. the null character is encoded as 0, and no code unit of any other character is 0;
3. the values of the digits `0`–`9` each increase by one.

Beyond that, the ordinary and wide literal encodings are implementation-defined. Note 3 adds that characters outside the basic literal character set may be encoded as several code units, and that one of those code units may have the same value as some basic character. Shift-JIS is like that: the second byte of some kanji is 0x5C, the same as `\`.

```cpp run title="digits.cpp" ok
constexpr int digit_value(char c) { return c - '0'; }   // portable: digits are always contiguous
static_assert(digit_value('7') == 7);
// 'z' - 'a' == 25 is not guaranteed: letters are not contiguous in EBCDIC
int main() {}
```

It follows that:

- `c - '0'` is portable; `c - 'a'` is not. In EBCDIC there are gaps between `i` and `j`.
- The encoding of an ordinary string literal never produces an unexpected 0 byte, so `strlen` works on any ordinary string literal that contains no `\0` escape.
- Even when `char` is signed, the values of basic characters are non-negative, and `'A'` is always positive. If `'é'` can be represented in one `char` (in Latin-1, for example), its value may be negative.

The last sentence of ¶5 requires UTF-8, UTF-16 and UTF-32 literals to encode each character with the corresponding Unicode encoding form. So the contents of `u8`, `u` and `U` literals are portable, and those of unprefixed and `L` literals are not.

!!! impl
    | Compiler | Ordinary literal encoding (default) | Wide literal encoding | `wchar_t` |
    |---|---|---|---|
    | GCC, Clang (Linux, macOS) | UTF-8 | UTF-32 | 32 bits |
    | MSVC | Current code page (UTF-8 with `/utf-8`) | UTF-16 | 16 bits |

    MSVC's wide literal encoding is UTF-16, so `L'😀'` needs two code units and does not fit in one `wchar_t`; under [[lex.ccon#3]] it is ill-formed.

## Universal-character-names ([[lex.universal.char]])

A [[g:universal-character-name|universal-character-name]] (UCN) writes any one character in pure ASCII. There are four forms:

| Form | Example | Introduced |
|---|---|---|
| `\u` + 4 hex digits | `\u03B1` | C++98 |
| `\U` + 8 hex digits | `\U0001F600` | C++98 |
| `\u{` any number of digits `}` | `\u{1F600}`, `\u{3b1}` | C++23 ([[P2290R3]]) |
| `\N{` character name `}` | `\N{GREEK SMALL LETTER ALPHA}` | C++23 ([[P2071R2]]) |

`\u{...}` is called the delimited form; its number of digits is not fixed, which removes the nuisance of `\u` needing exactly 4 digits and `\U` exactly 8. `\N{...}` lets people write characters by their readable names.

```cpp run title="ucn.cpp" ok
int \u03B1 = 1;                        // identifier α
int \U000003B2 = 2;                    // identifier β
int \u{3B3} = 3;                       // identifier γ (C++23)
int \N{GREEK SMALL LETTER DELTA} = 4;  // identifier δ (C++23)
static_assert(u8"\u{1F600}"[0] == 0xF0);                       // first UTF-8 byte of 😀
static_assert(sizeof(u"\U0001F600") == 3 * sizeof(char16_t));  // surrogate pair + terminating 0
int main() { return α + β + γ + δ - 10; }  // a UCN is fully equivalent to writing the character
```

Phase 3 ([[lex.phases]]) recognizes universal-character-names while splitting tokens and replaces each with the character it designates, so `int \u03B1;` and `int α;` declare the same identifier. Character literals, string literals, raw strings and header names are excepted: a universal-character-name in a literal is handled by the encoding only when the literal is evaluated ([[lex.ccon#3]], [[lex.string#10]]).

### No basic characters outside literals (¶1)

```cpp title="ucn-basic.cpp" error
int \u0041 = 1;            // error: U+0041 'A' is a basic character
int \u0024x = 2;           // error: '$' is a basic character since C++26
int \u0009t = 3;            // error: control character
const char* p = "\u0041";   // OK: allowed inside a literal
```

¶1 If a universal-character-name outside the c-char-sequence or s-char-sequence of a character or string literal (including user-defined literals) designates a control character or a character in the basic character set, the program is ill-formed.

This rule rules out a class of meaningless questions: if `\u0041` were allowed to mean `A` outside literals, would `\u0023define` count as a preprocessing directive, and would the `i\u006Et` in `i\u006Et x;` count as the keyword `int`? Forbidding it outright is simplest. The basic character set is exactly all the characters C++ syntax uses; other characters have no special meaning in the grammar, and writing them with universal-character-names does not change how tokens are split, so there is no need to forbid them; whether they may appear in identifiers is left to [[lex.name]].

Note 1 says that a sequence of characters in a raw string that looks like a universal-character-name is not one: the content of `R"(\u0041)"` is 6 characters.

### The value must be a scalar value (¶2)

¶2 The forms `\u`, `\U` and `\u{}` designate the character whose scalar value equals the hexadecimal number in them. If that number is not a Unicode scalar value, that is, if it is a surrogate code point or greater than 0x10FFFF, the program is ill-formed.

```cpp title="ucn-range.cpp" error
char32_t a = U'\uD800';                 // error: a surrogate code point is not a scalar value
char32_t b = U'\U00110000';             // error: beyond 0x10FFFF
const char16_t* e = u"\uD83D\uDE00";    // error: 😀 cannot be put together from two surrogate code points
const char16_t* f = u"\U0001F600";      // OK: the compiler produces the surrogate pair itself
```

Java and JavaScript allow 😀 to be written as `\uD83D\uDE00`, because their `\u` designates a UTF-16 code unit. A C++ universal-character-name designates a character, so you can only write `\U0001F600` or `\u{1F600}`, and the surrogate pair is produced by the compiler when it encodes `u"..."`. When a lone surrogate code unit really is needed, use the numeric escape `u"\xD800"`, which gives the value of a code unit directly rather than a character ([[lex.string#10]]).

### Names must match exactly (¶3)

¶3 `\N{...}` designates the character in the Unicode Standard whose name, or one of whose aliases, is equal to the content of the braces; if there is none, the program is ill-formed. Note 2 says the aliases are listed in NameAliases.txt in the Unicode Character Database, and no name or alias has leading or trailing spaces.

Equal here means equal character by character: case is not ignored, nor are extra spaces or hyphens. The loose matching rule Unicode itself recommends for name lookup (UAX44-LM2) does not apply.

```cpp run title="named.cpp" ok
static_assert(U'\N{LATIN CAPITAL LETTER A}' == U'A');
static_assert(U'\N{LINE FEED}' == U'\n');  // U+000A has no formal name; LINE FEED is an alias
static_assert(U'\N{LF}' == U'\n');         // abbreviation aliases work too
// U'\N{latin capital letter a}'           // error: case does not match
// U'\N{LATIN CAPITAL LETTER  A}'          // error: one extra space
int main() {}
```

Control characters have no formal name in Unicode, only aliases, so `\N{LINE FEED}` works only because aliases count too. To support `\N{...}`, a compiler has to carry a complete table of Unicode names. For a misspelled name Clang reports is not a valid Unicode character name, and suggests similar names when it can.

## History and evolution

!!! history
    - C++98 introduced `\u` and `\U`. The model of the time was that phase 1 replaced every non-basic character in the source with a universal-character-name before processing, which did not match what real compilers did at all. Universal-character-names in literals could not designate basic characters either.
    - C++11 allowed universal-character-names in literals to designate basic and control characters, while still forbidding it outside literals; it added the `u8`, `u` and `U` prefixes.
    - C++23 rewrote the character set model, introducing the translation character set and literal encodings ([[P2314R4]]); added `\N{}` ([[P2071R2]]) and `\u{}`, `\x{}`, `\o{}` ([[P2290R3]]; for the last two see [[lex.ccon]]); and required support for UTF-8 source files ([[P2295R6]]).
    - C++26 added `$`, `@` and `` ` `` to the basic character set ([[P2558R2]]); forming a universal-character-name by line splicing went from UB to valid ([[P2621R2]]).

## Common misconceptions

!!! pitfall "The literal encoding is the encoding of the source file"
    A source file saved in GBK with UTF-8 as the ordinary literal encoding is entirely possible: phase 1 decodes the GBK into Unicode, and encoding the literals produces UTF-8 again. Garbled text usually comes from the opposite direction: the source file is UTF-8, but MSVC reads it in the GBK code page. The problem is in the decoding of phase 1, not in the literal encoding.

!!! pitfall "`'A' == 65` is guaranteed by the standard"
    The standard only guarantees that digits are contiguous and that the null character is 0. On an EBCDIC implementation (such as IBM's compiler on z/OS), `'A'` has the value 0xC1. Only `u8'A'`, `u'A'` and `U'A'` are guaranteed to be 0x41.

!!! pitfall "Using a universal-character-name to get around a keyword"
    Writing `\u0069f` outside a literal, hoping for an identifier distinct from `if`, just makes the program ill-formed.

## Questions

!!! question "Question"
    Each line below is placed on its own at namespace scope. Is it well-formed?

    ```cpp
    int \u00C0 = 1;            // (a)
    int \u0040x = 2;           // (b)
    const char* s = "\u0040";  // (c)
    int \u{1F600} = 3;         // (d)
    auto r = R"(\u004)";       // (e)
    ```

<details markdown="1">
<summary>Answer</summary>

- (a) Well-formed: U+00C0 `À` is not a basic character, has the XID_Start property, can be the first character of an identifier, and is already in NFC (see [[lex.name]]).
- (b) Ill-formed: `@` is a basic character since C++26, and a universal-character-name outside a literal cannot designate it (¶1).
- (c) Well-formed: a universal-character-name in a literal can designate a basic character.
- (d) Ill-formed: 😀 does not have the XID_Start property and cannot appear in an identifier ([[lex.name]]).
- (e) Well-formed: there are no universal-character-names in a raw string; `\u004` is just 5 ordinary characters and is not an error for having too few digits.
</details>
