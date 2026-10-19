---
title: C 库区域设置
summary: <clocale> 的 setlocale 与 localeconv 同 C 的 <locale.h>；setlocale 可能与自身以及 printf、strtod、isalpha、mbtowc 等 45 个依赖 locale 的 C 函数发生数据竞争。
status: done
covers: *
related: localization, text, text.c.strings, res.on.data.races, character.seq, text.encoding
tags: 标准库, locale, C 库, 数据竞争
updated: 2026-10-19
---

!!! tldr
    - `<clocale>` 与 C 的 `<locale.h>` 内容相同；程序启动时 C locale 是 `"C"`，C++ 运行时不会替你调用 `setlocale(LC_ALL, "")`。
    - `setlocale` 可能与另一次 `setlocale` 调用，或与 `fprintf`、`isalpha`、`strtod` 等 45 个函数发生数据竞争，而数据竞争是未定义行为。
    - 多线程程序只应在启动其他线程之前设置 C locale，之后不再修改。
    - `std::locale::global` 在实参有名字时会调用 `setlocale`；反方向不成立，`setlocale` 不影响 C++ 的全局 locale。

## `<clocale>` [clocale.syn]

¶1 `<clocale>` 声明 `struct lconv`、`setlocale`、`localeconv` 以及宏 `LC_ALL`、`LC_COLLATE`、`LC_CTYPE`、`LC_MONETARY`、`LC_NUMERIC`、`LC_TIME`，内容和含义都与 C 标准库的 `<locale.h>` 相同。

C locale 是 [[character.seq.general#1.1]] 所说的 locale-specific 属性的来源：执行字符集的编码、`printf` 的小数点字符、`isalpha` 的结果都随它变化。程序启动时它是 `"C"`，直到某处调用了 `setlocale`。

它与 C++ 的 locale 只有单向联系。`std::locale::global(loc)` 在 `loc` 有名字时调用 `setlocale(LC_ALL, loc.name().c_str())`；直接调用 `setlocale` 不会改变 `std::locale()` 的返回值（见 [[localization]]）。C++26 的 `text_encoding::environment()` 也不受 `setlocale` 影响，它报告的是进程环境的编码（[[text.encoding]]）。

`localeconv()` 返回一个指向静态 `lconv` 对象的指针，之后调用 `setlocale` 或 `localeconv` 可能覆盖它的内容。

## 数据竞争 [clocale.data.races]

!!! std
    Calls to the function `setlocale` may introduce a data race with other calls to `setlocale` or with calls to the functions listed in Table 103.

¶1 `setlocale` 可能与其他 `setlocale` 调用，以及表 103 中的函数发生数据竞争（[[res.on.data.races]]）。表 103 共 45 个函数：

| 类别 | 函数 |
|---|---|
| 格式化 I/O | `fprintf` `fscanf` |
| 字符分类与转换 | `isalnum` `isalpha` `isblank` `iscntrl` `isdigit` `isgraph` `islower` `isprint` `ispunct` `isspace` `isupper` `isxdigit` `tolower` `toupper` |
| 宽字符分类与转换 | `iswalnum` `iswalpha` `iswblank` `iswcntrl` `iswctype` `iswdigit` `iswgraph` `iswlower` `iswprint` `iswpunct` `iswspace` `iswupper` `iswxdigit` `towlower` `towupper` |
| 多字节转换 | `mblen` `mbstowcs` `mbtowc` `wcstombs` `wctomb` |
| 排序 | `strcoll` `strxfrm` `wcscoll` `wcsxfrm` |
| 数值转换 | `strtod` `wcstod` |
| 其他 | `localeconv` `setlocale` `strerror` |

表中只列了 `fprintf` 和 `fscanf`，但 `printf`、`snprintf`、`sscanf` 等在 C 标准里都是借它们定义的，同样依赖 locale。

数据竞争是 {{ub}}（[[intro.races]]）。所以只要别的线程可能正在调用 `printf`、`isalpha`、`strtod` 之类的函数，任何线程都不能调用 `setlocale`。稳妥的做法是在 `main` 开头、启动其他线程之前设置一次 locale，之后不再修改。

需要按线程或按对象区分 locale 时，标准 C++ 的做法是把 `std::locale` imbue 到各自的流上，或者改用与 locale 无关的 [[charconv]] 和 [[format]]。POSIX 另有 `newlocale`、`uselocale`、`strtod_l` 等接口，但它们不属于 C++ 标准。

!!! impl "C++ 全局 locale 也有同样的问题"
    [locale.general] ¶9 允许实现在整个程序中只提供一个全局 `std::locale`，并且不要求实现避免它上面的数据竞争。libc++ 和 libstdc++ 都是这样，所以 `std::locale::global` 同样只应在单线程阶段调用，何况它对有名字的 locale 还会调用 `setlocale`。
