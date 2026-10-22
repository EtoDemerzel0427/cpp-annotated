---
title: String literals
summary: "The type and length of string literals, raw strings, concatenation of adjacent strings, the string literal object produced by evaluation (static storage duration, unspecified identity, not modifiable) and its contents, and C++26's unevaluated strings that only the compiler reads."
updated: 2026-10-19
---

!!! tldr
    - The type of `"abc"` is `const char[4]`; the array length is the number of encoded code units plus the terminating null character, not the number of characters.
    - A raw string `R"(...)"` has no escapes; new-lines and backslashes are kept as is, and a delimiter lets the content contain `)"`.
    - Adjacent string literals are concatenated and may have at most one kind of encoding prefix; the escape sequences of each piece are interpreted separately, so `"\x41" "BC"` is `"ABC"`.
    - Evaluating a string literal yields an array object with static storage duration. Whether two evaluations yield the same object is unspecified, and modifying it is undefined behavior.
    - C++26 unevaluated strings are used for `static_assert` messages, `[[deprecated]]` reasons, `extern "C"` and the like; they cannot have a prefix or contain numeric escapes.

String literals share encoding prefixes and escape sequences with character literals ([[lex.ccon]]); the meaning of the prefixes, the kinds of escape sequences, and the concept of a **code unit** (an integer value of some character type, such as one byte of UTF-8) are all covered on that page.

## Type and length (¶1, ¶6)

```cpp run title="string-n.cpp" ok
static_assert(sizeof("abc") == 4);         // a, b, c, null character
static_assert(sizeof(u8"\u00E9") == 3);    // é takes 2 code units in UTF-8
static_assert(sizeof(u"\U0001F600") == 3 * sizeof(char16_t));  // surrogate pair
static_assert(sizeof(U"\U0001F600") == 2 * sizeof(char32_t));
int main() {}
```

¶1 The type of a string literal is an array of n const characters, with the character type determined by the prefix. n is the number of encoded code units resulting from evaluating the literal, including the terminating null character.

| Prefix | Kind | Type | Associated encoding |
|---|---|---|---|
| none | ordinary string literal | `const char[n]` | ordinary literal encoding |
| `L` | wide string literal | `const wchar_t[n]` | wide literal encoding |
| `u8` | UTF-8 string literal | `const char8_t[n]` | UTF-8 |
| `u` | UTF-16 string literal | `const char16_t[n]` | UTF-16 |
| `U` | UTF-32 string literal | `const char32_t[n]` | UTF-32 |

¶6 Ordinary string literals and UTF-8 string literals are together called **narrow string literals**.

The array elements are const. In C, the type of a string literal is `char[n]`, though modifying it is equally undefined behavior. C++ made them const so that a string literal is not passed to an overload that might modify its argument ([[diff.lex]]). C++98 kept, for C compatibility, an implicit conversion from string literals to `char*` and marked it deprecated; C++11 removed it.

```cpp title="string-const.cpp" error
char* p = "abc";          // error (since C++11): const char[4] cannot be converted to char*
const char* q = u8"abc";  // error (since C++20): a u8 string is const char8_t[4]
```

For the first line Clang 23 gives only a `-Wwritable-strings` warning and continues compiling. A warning is a diagnostic too, so this conforms to the standard ([[intro.compliance]]). The second line is an error.

When `u8"..."` was introduced in C++11 its type was `const char[n]`, indistinguishable from an ordinary string. C++20 introduced `char8_t` ([[P0482R6]]) and its type became `const char8_t[n]`, so code like `std::string s = u8"text";` no longer compiles ([[diff.cpp17.lex]]).

## Raw strings (¶2–¶5)

```cpp run title="raw.cpp" ok
#include <cstring>
#include <cassert>
int main() {
  const char* re = R"(\d+\.\d+)";      // no need to write every \ as \\
  assert(std::strcmp(re, "\\d+\\.\\d+") == 0);
  const char* s = R"x(a)"b)x";         // the content contains )", so use the delimiter x
  assert(std::strcmp(s, "a)\"b") == 0);
}
```

¶2 A string literal whose prefix contains `R` is a **raw string literal**. Its form is `R"delimiter(content)delimiter"`; the closing delimiter must be the same as the opening one, and the delimiter has at most 16 characters and may be empty.

The content of a raw string is kept as is:

- there are no escape sequences; `\` is a backslash;
- universal-character-names are not recognized either; `\u0041` is 6 characters;
- it can span lines, and a new-line in the source is a new-line in the content (Note 2 in ¶4);
- the line splicing of translation phase 2 (deleting a backslash followed by a new-line at the end of a line) is reverted in raw strings ([[lex.pptoken#5]]), so a trailing `\` and the new-line are both kept.

The delimiter lets the content contain `)"`. The string ends only at `)delimiter"`, so choose a delimiter that does not occur in the content. Note 1 in ¶3 gives the example `R"delimiter((a|b))delimiter"`, which is equivalent to `"(a|b)"`.

```cpp run title="raw-newline.cpp" ok
#include <cstring>
#include <cassert>
int main() {
  const char* p = R"(a\
b
c)";
  // the backslash and the new-line are both kept: line splicing is reverted
  assert(std::strcmp(p, "a\\\nb\nc") == 0);
}
```

This example is from Note 2 in ¶4, assuming no whitespace at the start of the continuation lines. Every character in a raw string counts as content, indentation included; C++ has no mechanism for stripping common indentation.

Example 1 in ¶5 shows how the delimiter determines the end:

```cpp run title="raw-tricky.cpp" ok
#include <cstring>
#include <cassert>
int main() {
  const char* q = R"a(
)\
a"
)a";
  assert(std::strcmp(q, "\n)\\\na\"\n") == 0);
}
```

The delimiter is `a`, so the closing sequence is `)a"`. On the second line, `)` is followed by `\`, not `a"`; the `a"` on the third line is separated from it by a backslash and a new-line, which are real characters since line splicing was reverted, so that is not `)a"` either. Only on the last line does the string end.

A delimiter cannot contain spaces, parentheses, backslashes, horizontal tabs, vertical tabs, form feeds or new-lines:

```cpp title="raw-bad.cpp" error
const char* a = R"a b(x)a b";   // error: a space cannot be part of a delimiter
const char* b =
  R"12345678901234567(x)12345678901234567";  // error: more than 16 characters
```

## Concatenation (¶7–¶8)

### The common encoding prefix (¶7)

```cpp run title="concat-prefix.cpp" ok
#include <type_traits>
static_assert(std::is_same_v<decltype(u"a" "b"), const char16_t(&)[3]>);
static_assert(std::is_same_v<decltype("a" u8"b"), const char8_t(&)[3]>);
static_assert(std::is_same_v<decltype(LR"(a)" "b"), const wchar_t(&)[3]>);
int main() {}
```

¶7 At most one kind of encoding prefix may appear in a sequence of adjacent string literals, and it is the **common encoding prefix** of the sequence. Note 3 explains that whether a literal is raw does not affect the common prefix. So an unprefixed string can be concatenated with a string of any prefix, and the result takes that prefix; concatenating two different prefixes is ill-formed.

```cpp title="concat-conflict.cpp" error
auto c = L"a" U"b";    // error: two different encoding prefixes
auto d = u8"a" u"b";   // error
```

Concatenation takes place in translation phase 5 ([[lex.phases]]): the common prefix is determined first, every string literal is treated as having that prefix, and then they are concatenated. So the é in `"é" u"x"` is encoded in UTF-16, not first encoded into bytes with the ordinary literal encoding.

From C++11 to C++20, concatenating different prefixes was conditionally-supported, and none of the mainstream implementations supported it. [[P2201R1]] in C++23 made it ill-formed ([[diff.cpp20.lex]]).

### Each piece is interpreted on its own (¶8)

```cpp run title="concat-structure.cpp" ok
static_assert(sizeof("\xA" "B") == 3);       // '\xA', 'B', null character; not '\xAB'
static_assert(sizeof(R"(\u00)" "41") == 7);  // \ u 0 0 4 1 and the null character; not 'A'
int main() {}
```

¶8 During concatenation, the lexical structure and grouping of the contents of the individual string literals is retained. Concatenation does not join the source text and re-analyze it; it puts the already-analyzed characters and escape sequences of each piece end to end.

So before C++23 had `\x{...}`, `"\x41" "BC"` was the standard way to cut a hexadecimal escape short. The same holds with macros: after `#define ESC "\x1B"`, `ESC "c"` is ESC followed by the letter c.

For concatenation of user-defined string literals see [[lex.ext#8]].

## The string literal object (¶9)

¶9 Evaluating a string literal results in a **string literal object** with static storage duration ([[basic.stc]]).

The wording separates the token in the source from the object in memory: `"abc"` itself is just a token, and each evaluation of it yields an lvalue designating some array object ([[expr.prim.literal]]).

### Identity is unspecified

Note 4 explains that string literal objects are **potentially non-unique objects** ([[intro.object#9]]): whether successive evaluations of the same string literal yield the same or a different object is unspecified.

```cpp run title="string-identity.cpp" unspecified
#include <cstdio>
int main() {
  const char* a = "hello";
  const char* b = "hello";
  std::printf("%d\n", a == b);   // 1 or 0, unspecified; prints 1 in our tests
}
```

A compiler may let strings with the same content share storage, and may make `"bc"` the tail of `"abc"`. [[intro.object#10]] also allows two distinct potentially non-unique objects to have the same address, an exception to the general rule that distinct objects have distinct addresses.

Because the identity is indeterminate, a pointer to a string literal object cannot be a template argument ([[temp.arg.nontype]]); otherwise there would be no way to tell whether `X<"abc">` in two translation units is the same specialization. C++26's `std::define_static_string` ([[meta.define.static]]) returns a pointer to a template parameter object, which can be used as a template argument, and is one alternative.

### Modifying it is undefined behavior

Note 5 reminds us that the effect of attempting to modify a string literal object is undefined. The normative basis is that modifying a const object is undefined behavior ([[dcl.type.cv]]). In practice string literals are usually placed in a read-only section, and modifying one crashes the program.

```cpp title="string-modify.cpp" ub
int main() {
  char* p = const_cast<char*>("abc");
  p[0] = 'x';   // UB: modifies a string literal object
}
```

In our tests, the program terminates with SIGBUS.

## The contents of the object (¶10)

¶10 The string literal object is initialized with the sequence of code units corresponding to its parts, followed by a terminating null character. The parts are obtained by the following rules.

### Consecutive characters are encoded as a whole (¶10.1)

¶10.1 Each sequence of consecutive ordinary characters, simple escapes and universal-character-names is encoded as a whole, as a sequence of characters, with the associated encoding. If some character cannot be represented in the associated encoding, the program is ill-formed; Note 6 points out that Unicode encoding forms can represent all characters.

Unlike character literals, there is no requirement here that each character occupy only one code unit. So `u8"é"` is valid and `u8'é'` is ill-formed.

Encoding as a whole also matters for **stateful encodings**, which switch character sets with special byte sequences, such as ISO-2022-JP. The standard recommends that an implementation encode each sequence starting in the state the previous one ended in; Note 7 points out that the result may then differ from encoding each character independently.

### Each numeric escape is one code unit (¶10.2)

¶10.2 Each numeric escape contributes exactly one code unit. The rules for the value are the same as for character literals ([[lex.ccon]] ¶3.2): within the range of the element type, it is the value itself; with no prefix or the `L` prefix, within the range of the corresponding unsigned type, it wraps modulo; otherwise it is ill-formed.

With this rule, any code unit can be placed in a string, including sequences that are themselves invalid in UTF-8 or UTF-16 strings:

```cpp run title="numeric-in-string.cpp" ok
static_assert(sizeof(u8"\xFF") == 2);   // one code unit with value 0xFF
static_assert(u"\xD800"[0] == 0xD800);  // a lone surrogate; written as \uD800 it would be ill-formed
int main() {}
```

¶10.3 Each conditional escape contributes an implementation-defined sequence of code units.

## Unevaluated strings ([[lex.string.uneval]]) {{c++26}}

Some strings are only for the compiler and never appear in the program's data, such as the message of a `static_assert`. C++26 changed the grammar at these positions to **unevaluated strings**. Grammatically an unevaluated string is just a string literal, but the rules differ:

```cpp title="uneval.cpp" error
static_assert(true, "\u00e9 \n ok");  // OK: universal-character-names and simple escapes are allowed
static_assert(true, u8"x");           // error: no encoding prefix allowed
static_assert(true, "\x41");          // error: no numeric escapes allowed
[[deprecated(L"w")]] void f();        // error: no encoding prefix allowed
extern "\x43" void g();               // error: even though \x43 is 'C'
```

¶1 An unevaluated string shall have no encoding prefix. ¶2 Each universal-character-name and simple escape in it is replaced by the member of the translation character set it denotes (that is, a Unicode character at the source level); an unevaluated string containing a numeric escape or conditional escape is ill-formed. ¶3 It is never evaluated, and its interpretation depends on the context in which it appears.

Unevaluated strings are used in these positions:

| Context | Example | Where the rule is |
|---|---|---|
| `static_assert` message | `static_assert(N > 0, "N must be positive");` | [[dcl.pre]] |
| `[[deprecated]]` and `[[nodiscard]]` reasons | `[[deprecated("use g")]]` | [[dcl.attr.deprecated]], [[dcl.attr.nodiscard]] |
| Reason for a deleted function | `void f() = delete("reason");` | [[dcl.fct.def.delete]] |
| Language linkage | `extern "C"` | [[dcl.link]] |
| Literal operators | `operator "" _x` (deprecated form) | [[over.literal]] |

The rationale is that these strings need no encoding. A message should be shown to the user as the characters in the source, not first converted to bytes with the ordinary literal encoding (which might be GBK or EBCDIC) and then interpreted back by the compiler. An encoding prefix would change nothing and only suggest some meaning. A numeric escape such as `"\xC3\xA9"` corresponds to é only under some encoding, and corresponds to no character at all where nothing is encoded.

A C++26 `static_assert` message can also be a constant expression, as long as it has `.size()` and `.data()` ([[dcl.pre#12]]). Only when the message is grammatically a string literal is it treated as an unevaluated string.

Unevaluated strings were introduced by [[P2361R6]]. Before that, these positions used ordinary string literals, and prefixes and numeric escapes were grammatically allowed. Under `-std=c++23`, Clang 23 gives only a `-Winvalid-unevaluated-string` warning for a prefixed message, and reports numeric escapes as errors in every mode.

## Common misconceptions

!!! pitfall "Identical string literals have the same address"
    Comparing two string literals with `==`, or using `const char*` as a map key, both depend on unspecified behavior. In practice compilers usually merge identical strings, but the standard does not guarantee it.

!!! pitfall "`sizeof` gives the number of characters"
    `sizeof(u8"é")` is 3: two code units plus the null character. The array length counts encoded code units.

## Questions

!!! question "Question 1"
    What is `sizeof(u8"a" "\u00e9" R"(\n)")`?

<details markdown="1">
<summary>Answer</summary>

The common prefix is `u8`. The three pieces contribute: `a`, one code unit; é, two code units in UTF-8; the `\` and `n` in the raw string, two characters, two code units. With the null character, that is 1 + 2 + 2 + 1 = 6, with type `const char8_t[6]`, so `sizeof` is 6.
</details>

!!! question "Question 2"
    What might the following program print?

    ```cpp
    #include <cstdio>
    const char* f() { return "abc"; }
    int main() { std::printf("%d\n", f() == f()); }
    ```

<details markdown="1">
<summary>Answer</summary>

`1` or `0`. Whether two evaluations of the same string literal yield the same object is unspecified (Note 4 in ¶9). In practice compilers print `1`, Clang 23 included, but the standard does not guarantee it. This is unspecified behavior rather than undefined behavior: the program is well-formed, with two possible results.
</details>
