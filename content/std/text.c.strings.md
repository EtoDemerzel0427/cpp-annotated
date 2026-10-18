---
title: 空终止序列工具
summary: <cctype>、<cwctype>、<cwchar>、<cuchar> 与 <cstdlib> 中的多字节/宽字符转换函数——内容与 C 标准库相同，但有几处 C++ 特有差异（不声明 wchar_t/char8_t 等类型、wcschr 等的 const 重载、部分 freestanding）；isalpha(char) 的负值 UB、多字节转换随 C locale 变化，以及 mbtowc 与空 mbstate_t* 的数据竞争
status: draft
covers: *
related: text, c.locales, character.seq, library.c, res.on.data.races, localization, lex.charset
tags: 标准库, C 库, 多字节, 宽字符, UB
updated: 2026-10-18
---

[text.c.strings] 收纳 C 标准库中处理“字符”与“以空字符结尾的字符序列”的头文件。它们的条文几乎都是一句话：“内容与含义与 C 标准库头文件 `<xxx.h>` 相同”，引用的是 ISO/IEC 9899:2024（C23）。真正值得注意的是这句话**之外**的几处差异，以及从 C 继承来的那些陷阱。

| 子条款 | 头文件 | 对应 C 头文件 | C++ 特有差异 |
|---|---|---|---|
| [cctype.syn] | `<cctype>` | `<ctype.h>` | 无 |
| [cwctype.syn] | `<cwctype>` | `<wctype.h>` | 无 |
| [cwchar.syn] | `<cwchar>` | `<wchar.h>` | 不声明 `wchar_t`；`wcschr` 等有不同签名；部分 freestanding |
| [cuchar.syn] | `<cuchar>` | `<uchar.h>` | 不声明 `char8_t`、`char16_t`、`char32_t` |
| [c.mb.wcs] | `<cstdlib>`、`<cwchar>`、`<cuchar>` | — | 数据竞争说明 |

## `<cctype>` 与 `<cwctype>`（[cctype.syn]、[cwctype.syn]）

`<cctype>` 声明 `isalnum` … `isxdigit`、`tolower`、`toupper`；`<cwctype>` 声明 `wint_t`、`wctrans_t`、`wctype_t`、宏 `WEOF` 及 `iswalpha` 等宽字符版本。¶1：内容与 C 的 `<ctype.h>`、`<wctype.h>` 相同。

!!! ub "`std::isalpha(c)` 的负值陷阱"
    C 标准规定这些函数的 `int` 实参必须可表示为 `unsigned char` 或等于 `EOF`，否则行为未定义。在 `char` 为有符号类型的平台上（x86 上的主流 ABI 都是），UTF-8 文本中的非 ASCII 字节是负值：
    ```cpp
    std::string s = "café";
    for (char c : s)
        if (std::isalpha(c)) {}                            // UB: 'é' 的字节为负值
    for (char c : s)
        if (std::isalpha(static_cast<unsigned char>(c))) {} // OK
    ```
    `<locale>` 中的模板版本 `std::isalpha(c, loc)`（[[localization]]）和 `ctype<char>::is` 内部会先转为 `unsigned char`，没有这个问题。

这些函数的结果是 *locale-specific* 的（[[character.seq.general#1.1]]）：`isalpha(0xE9)` 在 `"C"` locale 下为假，在某个 Latin-1 locale 下可能为真。它们也都在 [[c.locales]] 表 103 中，与 `setlocale` 存在潜在数据竞争。

## `<cwchar>`（[cwchar.syn]）

概要定义 `__STDC_VERSION_WCHAR_H__` 为 `202311L`（与 C23 对齐），声明 `size_t`、`mbstate_t`、`wint_t`、`tm`、宽字符串函数（`wcslen`、`wcscpy`、`wcstol`…）、宽字符 I/O（`fwprintf`、`getwc`…）、以及 [c.mb.wcs] 中的转换函数；`size_t`、`mbstate_t`、`wint_t` 和宏 `NULL`、`WCHAR_MAX`、`WCHAR_MIN`、`WEOF`、`WCHAR_WIDTH` 标注为 freestanding。

¶1：内容与 C 的 `<wchar.h>` 相同，但**不声明类型 `wchar_t`**——在 C++ 中 `wchar_t` 是关键字和基本类型（[[basic.fundamental]]），在 C 中则是 typedef。

¶2（注 1）：`wcschr`、`wcspbrk`、`wcsrchr`、`wcsstr`、`wmemchr` 在 C++ 中签名不同（[[library.c]]）——C++ 提供 `const wchar_t*` 与 `wchar_t*` 两个重载，保持 const 正确性，而 C 只有一个“接受 `const` 却返回非 `const`”的版本；行为相同。

## `<cuchar>`（[cuchar.syn]）

概要定义 `__STDC_VERSION_UCHAR_H__` 为 `202311L`，声明 `mbstate_t`、`size_t` 和 `mbrtoc8`/`c8rtomb`/`mbrtoc16`/`c16rtomb`/`mbrtoc32`/`c32rtomb`。¶1：与 C 的 `<uchar.h>` 相同，但**不声明 `char8_t`、`char16_t`、`char32_t`**——它们在 C++ 中都是关键字。

!!! impl "libc++ 在 macOS 上的 `<cuchar>`"
    libc++ 的 `<cuchar>` 用 `using ::mbrtoc32 _LIBCPP_USING_IF_EXISTS;` 的方式引入这些函数：底层 C 库不提供时，`using` 声明“悬空”，直到真正使用才报错。本机（macOS SDK + libc++ 23）调用 `std::mbrtoc32` 会得到 “reference to unresolved using declaration”——头文件存在、能 `#include`，但函数不可用。这是库的可移植性现状，不是标准的规定。

## 多字节/宽字符转换函数（[c.mb.wcs]）

¶1（注 1）：这些函数由 `<cstdlib>`、`<cuchar>`、`<cwchar>` 声明。¶2、¶3、¶5：语义都与 C 标准库相同。它们分三组，差别在于**转换状态存放在哪里**：

| 组 | 函数 | 转换状态 | 数据竞争（Remarks） |
|---|---|---|---|
| 无状态参数（¶2） | `mbsinit`、`mblen`、`mbstowcs`、`wcstombs` | — / 内部 | — |
| 隐藏内部状态（¶3–¶4） | `mbtowc`、`wctomb` | 函数内部的静态状态 | 与**同一函数**的其他调用可能竞争 |
| 可重启（`r`，¶5–¶6） | `mbrlen`、`mbrtowc`、`wcrtomb`、`mbrtoc8`、`c8rtomb`、`mbrtoc16`、`c16rtomb`、`mbrtoc32`、`c32rtomb`、`mbsrtowcs`、`wcsrtombs` | 调用者提供的 `mbstate_t*` | 仅当 `mbstate_t*` 为**空指针**时，与同一函数的其他空指针调用可能竞争 |

结论：多线程代码应使用带 `r` 的可重启版本，并**自己提供** `mbstate_t` 对象；传空指针等于退回到函数内部的共享静态状态。

所有这些函数解读多字节序列时依据的都是**当前 C locale 的 `LC_CTYPE`**，而不是源代码的字面量编码（[[lex.charset]]）——这正是 [[text]] 所说两种编码的分歧在实践中暴露的地方：

```cpp run title="mbrtowc-locale.cpp" impl
#include <cassert>
#include <clocale>
#include <cstdio>
#include <cstring>
#include <cwchar>

int main() {
    const char* s = "中";                       // 字面量编码 UTF-8：3 个字节 E4 B8 AD
    wchar_t wc = 0;
    std::mbstate_t st{};

    std::setlocale(LC_ALL, "C");                // 程序启动时的默认 locale
    std::size_t n = std::mbrtowc(&wc, s, std::strlen(s), &st);
    std::printf("C locale: n=%zu\n", n);        // 由实现定义；macOS 上为 1（把 0xE4 当作一个字符）

    std::setlocale(LC_ALL, "en_US.UTF-8");      // 执行字符集编码改为 UTF-8
    st = {};
    n = std::mbrtowc(&wc, s, std::strlen(s), &st);
    assert(n == 3 && wc == L'\x4E2D');          // 同样的字节，换了 locale 才正确解码
}
```

在 `"C"` locale 下，非 ASCII 字节如何解释由实现决定；只有切换到 UTF-8 locale 后，同样的三个字节才被解码为一个宽字符 U+4E2D。

## 小结

- 这些头文件“与 C 相同”，差异仅在于 C++ 中已是关键字的类型不再声明，以及 `wcschr` 等的 const 重载。
- `<cctype>` 函数的实参必须可表示为 `unsigned char` 或为 `EOF`，否则 {{ub}}；先 `static_cast<unsigned char>`。
- 多字节转换跟随**当前 C locale**，与字面量编码无关。
- 多线程中使用带 `r` 的可重启函数并传入自己的 `mbstate_t`；`mbtowc`/`wctomb` 及空 `mbstate_t*` 会共享内部状态。
