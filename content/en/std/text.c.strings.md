---
title: Null-terminated sequence utilities
summary: "<cctype>, <cwctype>, <cwchar>, <cuchar> and the multibyte/wide character conversion functions: the same as the C standard library apart from a few C++-specific differences; the pitfalls inherited from C include negative arguments to isalpha, multibyte conversion that follows the C locale, and data races from shared internal state."
updated: 2026-10-19
---

!!! tldr
    - These headers have the same contents as the corresponding C23 headers. There are only two kinds of differences: `wchar_t`, `char8_t` and others that are keywords in C++ are not declared as types; and functions like `wcschr` have both `const` and non-`const` overloads.
    - The arguments to `std::isalpha` and friends must be representable as `unsigned char` or equal `EOF`. When `char` is signed, non-ASCII bytes are negative, and passing them directly is UB; convert to `unsigned char` first.
    - Conversion between multibyte and wide characters goes by the current C locale, regardless of the encoding of literals in the source code.
    - In multithreaded code, use the restartable functions with `r` in their names and pass your own `mbstate_t`. `mbtowc`, `wctomb` and calls passing a null pointer share internal state and may race.

[text.c.strings] collects the C standard library headers that deal with characters and null-terminated character sequences. The wording is mostly a single sentence: the contents and meaning are the same as some C standard library header (referencing ISO/IEC 9899:2024, that is, C23).

| Subclause | Header | Corresponding C header | C++-specific differences |
|---|---|---|---|
| [cctype.syn] | `<cctype>` | `<ctype.h>` | none |
| [cwctype.syn] | `<cwctype>` | `<wctype.h>` | none |
| [cwchar.syn] | `<cwchar>` | `<wchar.h>` | `wchar_t` not declared; `wcschr` and others have different signatures; some declarations are freestanding |
| [cuchar.syn] | `<cuchar>` | `<uchar.h>` | `char8_t`, `char16_t`, `char32_t` not declared |
| [c.mb.wcs] | `<cstdlib>`, `<cwchar>`, `<cuchar>` | — | notes on data races |

## `<cctype>` and `<cwctype>`

```cpp run title="isalpha.cpp" ok
#include <cctype>
#include <string>

int main() {
  std::string s = "café";
  int k = 0;
  for (char c : s)
    if (std::isalpha(static_cast<unsigned char>(c))) ++k;
  // writing std::isalpha(c): the UTF-8 bytes of 'é' are negative when char is signed, UB
  return k;
}
```

`<cctype>` declares the classification functions from `isalnum` to `isxdigit` and `tolower` and `toupper`; `<cwctype>` declares the corresponding wide-character versions such as `iswalpha`, plus `wint_t`, `wctrans_t`, `wctype_t` and the macro `WEOF`. [cctype.syn] ¶1 and [cwctype.syn] ¶1 say their contents are the same as C's `<ctype.h>` and `<wctype.h>`.

The C standard says the `int` argument to these functions must be representable as `unsigned char` or equal `EOF`; otherwise the behavior is undefined. In the mainstream ABIs on x86, `char` is signed, and all non-ASCII bytes of UTF-8 text are negative, so `static_cast<unsigned char>` comes first. The example above returns 3 in the `"C"` locale in our tests; neither byte of `é` counts as a letter. `std::isalpha(c, loc)` from `<locale>` ([[localization]]) does this conversion internally and does not have the problem.

The results of these functions depend on the locale ([[character.seq.general#1.1]]): `isalpha(0xE9)` is false in the `"C"` locale and may be true in some Latin-1 locale. They are also all listed in the table in [[c.locales]]; calling them concurrently with `setlocale` may race.

## `<cwchar>` and `<cuchar>`

`<cwchar>` declares the wide string functions (`wcslen`, `wcscpy`, `wcstol` and so on), wide character I/O (`fwprintf`, `getwc` and so on) and the conversion functions of the next section, and defines the macro `__STDC_VERSION_WCHAR_H__` as `202311L`. Of these, `size_t`, `mbstate_t`, `wint_t`, most of the wide string functions that do not involve locales, and macros such as `NULL` and `WCHAR_MAX` are marked freestanding.

[cwchar.syn] ¶1 The contents are the same as C's `<wchar.h>`, except that the type `wchar_t` is not declared. In C++ `wchar_t` is a keyword and a fundamental type ([[basic.fundamental]]); in C it is a typedef.

[cwchar.syn] ¶2 `wcschr`, `wcspbrk`, `wcsrchr`, `wcsstr` and `wmemchr` have different signatures in C++ with the same behavior ([[library.c]]). C has only one version, taking `const wchar_t*` and returning `wchar_t*`; C++ provides `const` and non-`const` overloads to preserve const-correctness.

[cuchar.syn] ¶1 `<cuchar>` is the same as C's `<uchar.h>`, except that it does not declare `char8_t`, `char16_t` or `char32_t`, which are all keywords in C++. It declares `mbrtoc8`, `c8rtomb`, `mbrtoc16`, `c16rtomb`, `mbrtoc32` and `c32rtomb`.

!!! impl "libc++'s `<cuchar>` on macOS"
    libc++ brings in these functions with `using ::mbrtoc32;` marked `_LIBCPP_USING_IF_EXISTS`. When the underlying C library does not provide a function, the using-declaration is left unresolved and only errors when used. In our tests (macOS SDK + libc++), calling `std::mbrtoc32` gives "reference to unresolved using declaration": the header can be included, but the function is unusable. This is the state of the library, not a rule of the standard.

## Multibyte and wide character conversion ([c.mb.wcs])

```cpp run title="mbrtowc-locale.cpp" impl
#include <cassert>
#include <clocale>
#include <cstdio>
#include <cstring>
#include <cwchar>

int main() {
  const char* s = "中";              // literal encoding UTF-8: E4 B8 AD
  wchar_t wc = 0;
  std::mbstate_t st{};

  std::setlocale(LC_ALL, "C");       // the default locale at program startup
  std::size_t n = std::mbrtowc(&wc, s, std::strlen(s), &st);
  std::printf("C locale: n=%zu\n", n);   // implementation-defined; 1 on macOS

  std::setlocale(LC_ALL, "en_US.UTF-8");
  st = {};
  n = std::mbrtowc(&wc, s, std::strlen(s), &st);
  assert(n == 3 && wc == L'\x4E2D');     // decoded correctly only after switching to a UTF-8 locale
}
```

When these functions interpret a multibyte sequence, they go by `LC_CTYPE` of the current C locale, not by the encoding of literals in the source code ([[lex.charset]]). The example above treats the first byte as one character in the `"C"` locale; only after switching to a UTF-8 locale are the same three bytes decoded as U+4E2D. The split between the literal encoding and the execution environment's encoding described in [[text]] shows up most directly here.

¶1 These functions are declared by `<cstdlib>`, `<cuchar>` and `<cwchar>`. ¶2, ¶3 and ¶5 say their semantics are all the same as in the C standard library. They fall into three groups by where the conversion state is kept:

| Group | Functions | Conversion state | Data races |
|---|---|---|---|
| ¶2 | `mbsinit`, `mblen`, `mbstowcs`, `wcstombs` | — | no additional note |
| ¶3–¶4 | `mbtowc`, `wctomb` | static state inside the function | may race with other calls to the same function |
| ¶5–¶6 restartable | `mbrlen`, `mbrtowc`, `wcrtomb`, `mbrtoc8`, `c8rtomb`, `mbrtoc16`, `c16rtomb`, `mbrtoc32`, `c32rtomb`, `mbsrtowcs`, `wcsrtombs` | an `mbstate_t` supplied by the caller | only when passed a null pointer, may race with other null-pointer calls to the same function |

The data race notes in ¶4 and ¶6 refer to [[res.on.data.races]]. Multithreaded code should use the restartable versions with `r` and supply its own `mbstate_t` object. Passing a null pointer amounts to falling back to the function's shared internal static state.
