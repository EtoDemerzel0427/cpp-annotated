---
title: Text processing library
summary: "A guide to Clause 28: what numeric conversions, locales, encoding identification, formatting, regular expressions and the C string utilities each cover; the difference between the literal encoding and the execution environment's encoding; and the trend of new facilities being locale-independent by default."
updated: 2026-10-19
---

!!! tldr
    - Clause 28 collects the libraries that deal with text content: `<charconv>`, `<locale>`, `<text_encoding>`, `<format>`, `<regex>` and the C string utilities.
    - A program has at least two encodings: the literal encoding, fixed at compile time, and the execution environment's encoding, determined at run time by the C locale; the two can be entirely unrelated.
    - Locale-dependent C functions (`isalpha`, `mbrtowc`, `printf`) interpret bytes according to the encoding of the current C locale, not the encoding the compiler used for literals.
    - Text facilities added since C++17 are locale-independent by default: `to_chars`, `std::format`, C++26's `to_string(double)`; they localize only when explicitly asked.

## What the clause contains [text.general]

[text.general] has just one table (Table 89), listing six subclauses:

| Subclause | Header | Notes on this site | Contents |
|---|---|---|---|
| [[charconv]] | `<charconv>` | [[charconv\|Primitive numeric conversions]] | Locale-independent, non-throwing, non-allocating conversions between numbers and text |
| [[localization]] | `<locale>`, `<clocale>` | [[localization\|locales and facets]], [[locale.categories\|standard facets]], [[c.locales\|C library locales]] | C++98's localization framework: a locale is a set of facets indexed by type |
| [[text.encoding]] | `<text_encoding>` | [[text.encoding\|Text encoding identification]] | {{c++26}} query the literal encoding and the execution environment's encoding |
| [[format]] | `<format>` | [[format\|the formatting library]], [[format.string\|format strings]], [[format.formatter\|formatters]] | Type-safe `std::format` with compile-time checking of format strings |
| [[re]] | `<regex>` | [[re\|regular expressions]], [[re.alg\|matching and results]] | C++11's `std::regex` |
| [[text.c.strings]] | `<cctype>`, `<cwctype>`, `<cwchar>`, `<cuchar>`, `<cstdlib>` | [[text.c.strings\|C string utilities]] | C library character classification, and conversion between multibyte and wide characters |

`format`'s default output for numbers is defined in terms of `to_chars`, and `format`'s `L` option obtains the thousands separator through the locale's `numpunct` facet. So these parts are not independent; `charconv` is the lowest layer.

## Two encodings

### The literal encoding: fixed at compile time

```cpp run title="two-encodings.cpp" impl
#include <cstdio>
#include <text_encoding>

int main() {
    constexpr auto lit = std::text_encoding::literal();   // fixed at compile time
    static_assert(lit == std::text_encoding::UTF8);       // Clang/GCC default; MSVC needs /utf-8
    static_assert(sizeof("中") == 4);                      // 3 UTF-8 code units + '\0'

    // at run time: depends on the process environment (on POSIX, the encoding of the "" locale)
    std::printf("environment: %s\n", std::text_encoding::environment().name());
}
```

In our tests (Clang 23 + libc++, `LANG` unset) this prints `environment: US-ASCII`; with `LANG=zh_CN.GB18030` it prints `GB18030`. In both cases the literal encoding is UTF-8.

[[lex.charset#4]] says that the characters in character and string literals are encoded as one or more [[g:code-unit|code units]] (integer values of some character type), and the encoding used is the **literal encoding** ([[g:literal-encoding|literal encoding]]) of that kind of literal. Ordinary literals without a prefix use the **ordinary literal encoding**; literals with the `L` prefix use the **wide literal encoding**.

[[lex.charset#5]] gives only a few guarantees: each character of the [[g:basic-literal-character-set|basic literal character set]] is encoded as a single non-negative code unit, the null character as 0, and the digits `'0'` to `'9'` have consecutive values. The rest is implementation-defined. Literals with the `u8`, `u` and `U` prefixes are fixed as UTF-8, UTF-16 and UTF-32.

The literal encoding is fixed at compile time and baked into the object file. Clang and GCC default to UTF-8, changeable with `-fexec-charset=`; MSVC follows the system code page by default and uses UTF-8 only with `/utf-8`. This terminology was sorted out in C++23 by [[P2314R4]]; before that the standard used the vague term "execution character set".

### The execution environment's encoding: changes at run time with the locale

When library functions interpret a `char` sequence, they use a different encoding. [[character.seq.general#1.2]] defines the **execution character set** ([[g:execution-character-set|execution character set]]): a superset of the basic literal character set whose encoding is locale-specific, that is, it can change at run time via `setlocale` or `std::locale::global` (¶1.1).

!!! std
    The encodings of the execution character sets can be unrelated to any literal encoding.

The encoding of the execution character sets can have nothing to do with any literal encoding.

When `mbrtowc`, `isalpha`, `printf("%ls")` or `std::codecvt<wchar_t, char, mbstate_t>` interpret bytes, they go by the encoding of the current C locale. If a program compiled with a UTF-8 literal encoding runs under `LANG=C`, the three bytes of `"中"` may look to the C library like three unrelated single-byte characters, or like an invalid sequence (see the example in [[text.c.strings]]). When the two encodings disagree, passing literals as-is to locale-dependent C functions produces garbage.

C++26's `std::text_encoding` ([[text.encoding]], [[P1885R12]]) lets a program query both encodings within the standard for the first time: `literal()` is `consteval` and returns the literal encoding; `environment()` returns the environment's encoding at run time.

!!! impl "libc++ and macOS availability annotations"
    libc++ implements `text_encoding::environment()` in the shared library and marks it with an availability macro as provided only from LLVM 23. On macOS, linking against the system libc++, calling it gives the error `'environment' is unavailable`. The examples on this site were verified with `-D_LIBCPP_DISABLE_AVAILABILITY`, linking against the libc++ that ships with Homebrew LLVM. `literal()` is implemented entirely in the header and is unaffected.

## New facilities are locale-independent by default

C++98's localization model localizes by default: every iostream formatting operation consults the locale imbued in the stream, and C's `printf` and `strtod` consult the global C locale. This causes three problems:

1. Unpredictable results: if any library calls `setlocale(LC_ALL, "")`, a JSON serializer may output `1,5` instead of `1.5`.
2. Slowness: every formatting operation goes through virtual calls and facet lookup.
3. Thread unsafety: `setlocale` races with dozens of C library functions ([[c.locales]]).

Text facilities added since C++17 reverse this: they are locale-independent by default and localize only when explicitly asked:

```cpp run title="locale-independence.cpp" impl
#include <charconv>
#include <cstdio>
#include <format>
#include <locale>
#include <string>

int main() {
    std::locale::global(std::locale("de_DE.UTF-8"));   // has a name, so it also calls setlocale(LC_ALL, ...)
    char buf[32];
    std::snprintf(buf, sizeof buf, "%.1f", 1.5);
    std::printf("printf     : %s\n", buf);                       // 1,5: follows the C locale
    auto r = std::to_chars(buf, buf + sizeof buf, 1.5);
    std::printf("to_chars   : %.*s\n", int(r.ptr - buf), buf);   // 1.5: always "C"
    std::printf("format {}  : %s\n", std::format("{}", 1.5).c_str());            // 1.5
    std::printf("format {:L}: %s\n", std::format("{:L}", 1234567.5).c_str());   // 1.234.567,5
    std::printf("to_string  : %s\n", std::to_string(1.5).c_str());
}
```

| Facility | Default behavior | How to localize |
|---|---|---|
| `to_chars`/`from_chars` (C++17, [[P0067R5]]) | always as the `"C"` locale | not possible |
| `std::format` (C++20, [[P0645R10]]) | locale-independent | write `L` in the format spec; a `std::locale` argument can also be passed ([[format.string.std#17]]) |
| `std::print` (C++23) | same as `format` | same |
| `to_string(double)` | defined as `format("{}", val)` since C++26 ([[P2587R3]]) | not possible |

In our tests the last line prints `1,500000`. The draft's [[string.conversions]] already specifies that floating-point `to_string` returns `format("{}", val)`, which should print `1.5`; at the time of writing libc++ still implements it with `sprintf("%f")` under the old rule, so the result varies with the C locale.

Locales have not been deprecated. `std::locale`, facets and iostream localization are still part of the specification, and `{:L}` uses the `numpunct` facet behind the scenes. What changed is the default: localization is turned on explicitly where it is needed, and everywhere else you get deterministic, round-trippable output.

On the other hand, C++26 removed the `<codecvt>` header (`codecvt_utf8` and so on) along with `wstring_convert` and `wbuffer_convert` ([[diff.cpp23.depr]]). The standard currently has no Unicode transcoding facility to replace them; `text_encoding` only identifies encodings and does not convert.

## Questions

!!! question "Question 1"
    In a program compiled with a UTF-8 literal encoding, what is wrong with `std::isalpha('é')`?

<details markdown="1">
<summary>Answer</summary>

In UTF-8, `'é'` needs two code units and does not fit in one `char`. Per [[lex.ccon]], such an ordinary character literal is {{ill-formed}}; Clang reports `character too large for enclosing character literal type`.

Rewriting it as `std::isalpha(s[0])` (with `s` being `"é"`) is not right either. `s[0]` is `0xC3`, which is negative on platforms where `char` is signed, and passing it to `<cctype>`'s `isalpha` is {{ub}}, because the C standard requires the argument to be representable as `unsigned char` or equal to `EOF`. Even after converting to `unsigned char` first, the result depends on the encoding of the current C locale ([[character.seq.general#1.2]]), not on the literal encoding.
</details>

!!! question "Question 2"
    Why can `text_encoding::literal()` be `consteval`, while `environment()` is not even `constexpr`?

<details markdown="1">
<summary>Answer</summary>

The literal encoding is an implementation-defined property fixed at translation time ([[lex.charset#5]]), so the compiler knows it at compile time. Clang tells the standard library through the predefined macro `__clang_literal_encoding__`.

The execution environment's encoding depends on the process environment at run time, which cannot be known at compile time. [[text.encoding.members#14]] says that on POSIX it is the encoding of the `""` locale; Note 2 explains that it is not affected by `setlocale` and reflects the environment, not the current C locale.
</details>

## Summary

| Encoding | When fixed | Decided by | Source |
|---|---|---|---|
| Ordinary and wide literal encodings | compile time | the implementation (compiler options) | [[lex.charset#4]] |
| `u8`, `u`, `U` literal encodings | compile time | fixed as UTF-8/16/32 | [[lex.charset#5]] |
| Execution character set encoding | run time, mutable | the current C locale | [[character.seq.general#1.2]] |
| Environment encoding | run time | the process environment (on POSIX, the `""` locale) | [[text.encoding.members#14]] |
| Encoding of a given `std::locale` | run time | that locale object | [[locale.members#7]] |
