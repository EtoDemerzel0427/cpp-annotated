---
title: 空终止序列工具
summary: <cctype>、<cwctype>、<cwchar>、<cuchar> 和多字节与宽字符转换函数：内容与 C 标准库相同，只有几处 C++ 特有的差异；从 C 继承的陷阱包括 isalpha 的负值实参、跟随 C locale 的多字节转换，以及共享内部状态造成的数据竞争。
status: done
covers: *
related: text, c.locales, character.seq, library.c, res.on.data.races, localization, lex.charset
tags: 标准库, C 库, 多字节, 宽字符, UB
updated: 2026-10-19
---

!!! tldr
    - 这几个头文件的内容与 C23 的对应头文件相同。差异只有两类：C++ 中已是关键字的 `wchar_t`、`char8_t` 等不再声明为类型；`wcschr` 等函数有 `const` 和非 `const` 两个重载。
    - `std::isalpha` 等函数的实参必须能表示为 `unsigned char` 或等于 `EOF`。`char` 是有符号类型时，非 ASCII 字节是负值，直接传入是 UB，要先转换为 `unsigned char`。
    - 多字节与宽字符的转换依据当前 C locale，与源代码中字面量的编码无关。
    - 多线程中应使用带 `r` 的可重启函数，并传入自己的 `mbstate_t`。`mbtowc`、`wctomb` 和传空指针的调用共享内部状态，可能产生数据竞争。

[text.c.strings] 收纳 C 标准库中处理字符和空终止字符序列的头文件。条文大多只有一句：内容与含义与 C 标准库的某个头文件相同（引用 ISO/IEC 9899:2024，即 C23）。

| 子条款 | 头文件 | 对应 C 头文件 | C++ 特有差异 |
|---|---|---|---|
| [cctype.syn] | `<cctype>` | `<ctype.h>` | 无 |
| [cwctype.syn] | `<cwctype>` | `<wctype.h>` | 无 |
| [cwchar.syn] | `<cwchar>` | `<wchar.h>` | 不声明 `wchar_t`；`wcschr` 等签名不同；部分声明是 freestanding |
| [cuchar.syn] | `<cuchar>` | `<uchar.h>` | 不声明 `char8_t`、`char16_t`、`char32_t` |
| [c.mb.wcs] | `<cstdlib>`、`<cwchar>`、`<cuchar>` | — | 数据竞争的说明 |

## `<cctype>` 与 `<cwctype>`

```cpp run title="isalpha.cpp" ok
#include <cctype>
#include <string>

int main() {
  std::string s = "café";
  int k = 0;
  for (char c : s)
    if (std::isalpha(static_cast<unsigned char>(c))) ++k;
  // 写成 std::isalpha(c)：'é' 的 UTF-8 字节在 char 有符号时为负值，UB
  return k;
}
```

`<cctype>` 声明 `isalnum` 到 `isxdigit` 的分类函数和 `tolower`、`toupper`；`<cwctype>` 声明对应的宽字符版本 `iswalpha` 等，以及 `wint_t`、`wctrans_t`、`wctype_t` 和宏 `WEOF`。[cctype.syn] ¶1 和 [cwctype.syn] ¶1 规定，它们的内容与 C 的 `<ctype.h>`、`<wctype.h>` 相同。

C 标准规定，这些函数的 `int` 实参必须能表示为 `unsigned char`，或者等于 `EOF`，否则行为未定义。x86 上的主流 ABI 中 `char` 是有符号类型，UTF-8 文本的非 ASCII 字节都是负值，所以要先 `static_cast<unsigned char>`。上例在本机 `"C"` locale 下返回 3，`é` 的两个字节都不算字母。`<locale>` 中的 `std::isalpha(c, loc)`（[[localization]]）内部会先做这个转换，没有这个问题。

这些函数的结果依赖于 locale（[[character.seq.general#1.1]]）：`isalpha(0xE9)` 在 `"C"` locale 下为假，在某个 Latin-1 locale 下可能为真。它们也都列在 [[c.locales]] 的表中，与 `setlocale` 并发调用可能产生数据竞争。

## `<cwchar>` 与 `<cuchar>`

`<cwchar>` 声明宽字符串函数（`wcslen`、`wcscpy`、`wcstol` 等）、宽字符 I/O（`fwprintf`、`getwc` 等）和下一节的转换函数，并把宏 `__STDC_VERSION_WCHAR_H__` 定义为 `202311L`。其中 `size_t`、`mbstate_t`、`wint_t`、大部分不涉及 locale 的宽字符串函数，以及 `NULL`、`WCHAR_MAX` 等宏标为 freestanding。

[cwchar.syn] ¶1 内容与 C 的 `<wchar.h>` 相同，但不声明类型 `wchar_t`。C++ 中 `wchar_t` 是关键字和基本类型（[[basic.fundamental]]），C 中它是 typedef。

[cwchar.syn] ¶2 `wcschr`、`wcspbrk`、`wcsrchr`、`wcsstr`、`wmemchr` 在 C++ 中签名不同，行为相同（[[library.c]]）。C 只有一个接受 `const wchar_t*` 却返回 `wchar_t*` 的版本；C++ 提供 `const` 和非 `const` 两个重载，保持 const 正确性。

[cuchar.syn] ¶1 `<cuchar>` 与 C 的 `<uchar.h>` 相同，但不声明 `char8_t`、`char16_t`、`char32_t`，它们在 C++ 中都是关键字。它声明 `mbrtoc8`、`c8rtomb`、`mbrtoc16`、`c16rtomb`、`mbrtoc32`、`c32rtomb`。

!!! impl "libc++ 在 macOS 上的 `<cuchar>`"
    libc++ 用带 `_LIBCPP_USING_IF_EXISTS` 的 `using ::mbrtoc32;` 引入这些函数。底层 C 库不提供某个函数时，这个 using 声明悬空，直到使用时才报错。本机（macOS SDK + libc++）调用 `std::mbrtoc32` 得到 "reference to unresolved using declaration"：头文件可以包含，函数却不可用。这是库的现状，不是标准的规定。

## 多字节与宽字符转换（[c.mb.wcs]）

```cpp run title="mbrtowc-locale.cpp" impl
#include <cassert>
#include <clocale>
#include <cstdio>
#include <cstring>
#include <cwchar>

int main() {
  const char* s = "中";              // 字面量编码 UTF-8：E4 B8 AD
  wchar_t wc = 0;
  std::mbstate_t st{};

  std::setlocale(LC_ALL, "C");       // 程序启动时的默认 locale
  std::size_t n = std::mbrtowc(&wc, s, std::strlen(s), &st);
  std::printf("C locale: n=%zu\n", n);   // 实现定义；macOS 上为 1

  std::setlocale(LC_ALL, "en_US.UTF-8");
  st = {};
  n = std::mbrtowc(&wc, s, std::strlen(s), &st);
  assert(n == 3 && wc == L'\x4E2D');     // 换成 UTF-8 locale 才正确解码
}
```

这些函数解读多字节序列时，依据的是当前 C locale 的 `LC_CTYPE`，而不是源代码中字面量的编码（[[lex.charset]]）。上例在 `"C"` locale 下把第一个字节当作一个字符；切换到 UTF-8 locale 后，同样的三个字节才被解码为 U+4E2D。[[text]] 所说的字面量编码与执行环境编码的分歧，在这里表现得最直接。

¶1 这些函数由 `<cstdlib>`、`<cuchar>`、`<cwchar>` 声明。¶2、¶3、¶5 规定它们的语义都与 C 标准库相同。它们按转换状态存放的位置分为三组：

| 组 | 函数 | 转换状态 | 数据竞争 |
|---|---|---|---|
| ¶2 | `mbsinit`、`mblen`、`mbstowcs`、`wcstombs` | — | 无额外说明 |
| ¶3–¶4 | `mbtowc`、`wctomb` | 函数内部的静态状态 | 与同一函数的其他调用可能竞争 |
| ¶5–¶6 可重启 | `mbrlen`、`mbrtowc`、`wcrtomb`、`mbrtoc8`、`c8rtomb`、`mbrtoc16`、`c16rtomb`、`mbrtoc32`、`c32rtomb`、`mbsrtowcs`、`wcsrtombs` | 调用者提供的 `mbstate_t` | 只有传空指针时，与同一函数其他传空指针的调用可能竞争 |

¶4 和 ¶6 的数据竞争说明引用 [[res.on.data.races]]。多线程代码应使用带 `r` 的可重启版本，并自己提供 `mbstate_t` 对象。传空指针相当于退回到函数内部共享的静态状态。
