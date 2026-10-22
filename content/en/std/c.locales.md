---
title: C library locales
summary: "setlocale and localeconv in <clocale> are the same as C's <locale.h>; setlocale may race with itself and with 45 locale-dependent C functions such as printf, strtod, isalpha and mbtowc."
updated: 2026-10-19
---

!!! tldr
    - `<clocale>` has the same contents as C's `<locale.h>`; at program startup the C locale is `"C"`, and the C++ runtime does not call `setlocale(LC_ALL, "")` for you.
    - `setlocale` may race with another call to `setlocale`, or with 45 functions such as `fprintf`, `isalpha` and `strtod`, and a data race is undefined behavior.
    - A multithreaded program should set the C locale only before starting other threads, and not change it afterwards.
    - `std::locale::global` calls `setlocale` when its argument has a name; the reverse does not hold, and `setlocale` does not affect C++'s global locale.

## `<clocale>` [clocale.syn]

¶1 `<clocale>` declares `struct lconv`, `setlocale`, `localeconv` and the macros `LC_ALL`, `LC_COLLATE`, `LC_CTYPE`, `LC_MONETARY`, `LC_NUMERIC` and `LC_TIME`, with the same contents and meaning as the C standard library's `<locale.h>`.

The C locale is the source of the locale-specific properties mentioned in [[character.seq.general#1.1]]: the encoding of the execution character set, the decimal point character of `printf`, and the results of `isalpha` all vary with it. At program startup it is `"C"`, until something calls `setlocale`.

Its connection with C++ locales goes only one way. `std::locale::global(loc)` calls `setlocale(LC_ALL, loc.name().c_str())` when `loc` has a name; calling `setlocale` directly does not change what `std::locale()` returns (see [[localization]]). C++26's `text_encoding::environment()` is not affected by `setlocale` either; it reports the encoding of the process environment ([[text.encoding]]).

`localeconv()` returns a pointer to a static `lconv` object whose contents later calls to `setlocale` or `localeconv` may overwrite.

## Data races [clocale.data.races]

!!! std
    Calls to the function `setlocale` may introduce a data race with other calls to `setlocale` or with calls to the functions listed in Table 103.

¶1 `setlocale` may race with other calls to `setlocale` and with the functions in Table 103 ([[res.on.data.races]]). Table 103 has 45 functions in all:

| Kind | Functions |
|---|---|
| Formatted I/O | `fprintf` `fscanf` |
| Character classification and conversion | `isalnum` `isalpha` `isblank` `iscntrl` `isdigit` `isgraph` `islower` `isprint` `ispunct` `isspace` `isupper` `isxdigit` `tolower` `toupper` |
| Wide character classification and conversion | `iswalnum` `iswalpha` `iswblank` `iswcntrl` `iswctype` `iswdigit` `iswgraph` `iswlower` `iswprint` `iswpunct` `iswspace` `iswupper` `iswxdigit` `towlower` `towupper` |
| Multibyte conversion | `mblen` `mbstowcs` `mbtowc` `wcstombs` `wctomb` |
| Collation | `strcoll` `strxfrm` `wcscoll` `wcsxfrm` |
| Numeric conversion | `strtod` `wcstod` |
| Other | `localeconv` `setlocale` `strerror` |

The table lists only `fprintf` and `fscanf`, but `printf`, `snprintf`, `sscanf` and the like are defined in terms of them in the C standard and depend on the locale in the same way.

A data race is {{ub}} ([[intro.races]]). So as long as another thread might be calling a function like `printf`, `isalpha` or `strtod`, no thread may call `setlocale`. The safe approach is to set the locale once at the start of `main`, before starting other threads, and not change it afterwards.

When locales need to differ per thread or per object, the standard C++ way is to imbue a `std::locale` into each stream, or to switch to the locale-independent [[charconv]] and [[format]]. POSIX also has interfaces such as `newlocale`, `uselocale` and `strtod_l`, but they are not part of the C++ standard.

!!! impl "The C++ global locale has the same problem"
    [locale.general] ¶9 allows an implementation to provide only one global `std::locale` for the whole program and does not require it to avoid data races on it. libc++ and libstdc++ both work this way, so `std::locale::global` should likewise be called only during the single-threaded phase, especially since for a named locale it also calls `setlocale`.
