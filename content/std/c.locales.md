---
title: C 库区域设置
summary: <clocale> 的 setlocale/localeconv 与 C 的 <locale.h> 相同；setlocale 会与自身以及 printf、strtod、isalpha、mbtowc 等数十个依赖 locale 的 C 函数发生数据竞争；与 std::locale::global 的单向联动
status: draft
covers: *
related: localization, text, text.c.strings, res.on.data.races, character.seq, text.encoding
tags: 标准库, locale, C 库, 数据竞争
updated: 2026-10-18
---

[c.locales] 只有两个子条款，但它回答了一个在多线程程序里至关重要的问题：**`setlocale` 什么时候能安全调用？**

## `<clocale>` 概要（[clocale.syn]）

概要声明 `struct lconv`、`setlocale(int category, const char* locale)`、`localeconv()`，以及宏 `NULL`、`LC_ALL`、`LC_COLLATE`、`LC_CTYPE`、`LC_MONETARY`、`LC_NUMERIC`、`LC_TIME`。¶1：内容与含义与 C 标准库头文件 `<locale.h>` 相同（引用 ISO/IEC 9899:2024 7.11）。

几个与 C++ 交互的要点：

- C 程序启动时的 C locale 是 `"C"`，直到某处调用 `setlocale`。C++ 程序同样如此——**C++ 运行时不会替你调用 `setlocale(LC_ALL, "")`**。
- C locale 是 [[character.seq.general#1.1]] 所说的 *locale-specific* 属性的来源：执行字符集的编码、小数点字符、`isalpha` 的结果都随它变化。
- `std::locale::global(loc)` 在 `loc` 有名字时会调用 `setlocale(LC_ALL, loc.name().c_str())`；反方向则不成立——`setlocale` 不会改变 C++ 全局 locale（见 [[localization]] 中的 [locale.statics]）。
- `localeconv()` 返回指向静态 `lconv` 对象的指针，后续调用 `setlocale` 或 `localeconv` 可能覆盖它。
- `text_encoding::environment()` **不受** `setlocale` 影响（[[text.encoding]]）——它报告的是环境，不是当前 C locale。

## 数据竞争（[clocale.data.races]）

!!! std
    Calls to the function `setlocale` may introduce a data race with other calls to `setlocale` or with calls to the functions listed in Table 103.

`setlocale` 可能与其他 `setlocale` 调用，以及表 103 中的函数发生数据竞争（[[res.on.data.races]]）。表 103 列出的函数有：

| 类别 | 函数 |
|---|---|
| 格式化 I/O | `fprintf`、`fscanf` |
| 字符分类/转换 | `isalnum` `isalpha` `isblank` `iscntrl` `isdigit` `isgraph` `islower` `isprint` `ispunct` `isspace` `isupper` `isxdigit` `tolower` `toupper` |
| 宽字符分类/转换 | `iswalnum` `iswalpha` `iswblank` `iswcntrl` `iswctype` `iswdigit` `iswgraph` `iswlower` `iswprint` `iswpunct` `iswspace` `iswupper` `iswxdigit` `towlower` `towupper` |
| 多字节转换 | `mblen` `mbstowcs` `mbtowc` `wcstombs` `wctomb` |
| 排序 | `strcoll` `strxfrm` `wcscoll` `wcsxfrm` |
| 数值 | `strtod` `wcstod` |
| 其他 | `localeconv` `setlocale` `strerror` |

数据竞争就是 {{ub}}（[[intro.races]]）。换言之：**只要有其他线程可能在调用 `printf`、`isalpha`、`strtod`……，任何线程都不能调用 `setlocale`。** 工程上唯一稳妥的做法是在 `main` 开头、启动任何线程之前设置一次 locale，之后不再修改。

注意表中列的是 `fprintf`/`fscanf`，而 `printf`、`snprintf`、`sscanf` 等在 C 标准里都是以它们为蓝本定义的，同样依赖 locale。

!!! tip "需要线程局部的 locale 怎么办"
    C++ 标准里，不依赖 C locale 的做法是：用 `std::locale` 对象并 imbue 到流上（每个流独立），或用与 locale 无关的 [[charconv]] / [[format]]。POSIX 另外提供了 `newlocale`/`uselocale`/`strtod_l` 这类线程局部或显式 locale 参数的接口，但它们不属于 C++ 标准。

!!! impl "C++ 全局 locale 也有同样的问题"
    [locale.general]/9 允许实现只提供一个进程级全局 `std::locale`，并且不要求实现避免其上的数据竞争。libc++ 与 libstdc++ 都是进程级的，因此 `std::locale::global` 同样只应在单线程阶段调用——何况它对有名字的 locale 还会调用 `setlocale`。

## 小结

- `<clocale>` = C 的 `<locale.h>`；C++ 程序启动时 C locale 为 `"C"`。
- `setlocale` 与表 103 所列的 45 个函数（含 `setlocale` 自身）之间存在潜在数据竞争；多线程程序里只应在启动线程前调用。
- `locale::global(有名字的 locale)` → `setlocale`；`setlocale` 不会反向影响 `std::locale()`。
