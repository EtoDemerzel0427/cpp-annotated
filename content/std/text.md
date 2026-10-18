---
title: 文本处理库
summary: 第 28 章导读——charconv、localization、text_encoding、format、regex 与 C 字符串工具各管什么；“字面量编码”（编译期）与“执行环境编码”（运行期、随 locale 变化）的根本区别；以及新设施一律与 locale 解耦、只在显式要求时才本地化的演进趋势
status: draft
covers: text.general
papers: P2314R4, P1885R12, P0067R5, P0645R10, P2587R3
related: lex.charset, character.seq, charconv, format, localization, text.encoding, re, text.c.strings, c.locales
tags: 标准库, 文本, 编码, locale, 导读
updated: 2026-10-18
---

第 28 章 [text] 是标准库里与“字符串里的内容”打交道的部分：数字与文本的互转、格式化、区域设置（locale）、正则表达式、编码识别，以及从 C 继承来的字符分类和多字节转换函数。它在 C++23 才成为独立的一章——之前这些组件分散在 [utilities]（charconv、format）、[localization]（自成一章）、[re]（自成一章）和 [strings]（C 字符串工具）里。

[text.general] 本身只有一段和一张表（表 89），列出了六个子条款：

| 子条款 | 头文件 | 本站笔记 | 一句话 |
|---|---|---|---|
| [[charconv]] | `<charconv>` | [[charconv\|基础数值转换]] | 与 locale 无关、不抛异常、不分配的数值⇄文本转换 |
| [[localization]] | `<locale>`、`<clocale>` | [[localization\|locale 与 facet]]、[[locale.categories\|标准 facet]]、[[c.locales\|C 库 locale]] | 1998 年的本地化框架：locale 是一组按类型索引的 facet |
| [[text.encoding]] | `<text_encoding>` | [[text.encoding\|文本编码识别]] | {{c++26}} 查询字面量编码与执行环境编码 |
| [[format]] | `<format>` | [[format\|格式化库]]、[[format.string\|格式串]]、[[format.formatter\|formatter]] | 类型安全、编译期检查格式串的 `std::format` |
| [[re]] | `<regex>` | [[re\|正则表达式]]、[[re.alg\|匹配与结果]] | C++11 的 `std::regex` |
| [[text.c.strings]] | `<cctype>`、`<cwctype>`、`<cwchar>`、`<cuchar>`、`<cstdlib>` | [[text.c.strings\|C 字符串工具]] | C 库的字符分类与多字节/宽字符转换 |

读懂这一章，最重要的前置概念不在本章，而在 [[lex.charset]] 与 [[character.seq]]：**编码到底是编译期决定的，还是运行期决定的？**

## 两种编码：字面量编码 vs 执行环境编码

C++ 程序里的“文本”至少牵涉两种互不相干的编码，标准对它们的措辞也截然不同。

### 字面量编码——编译期、由实现定义

[[lex.charset#4]] 定义：字符字面量和字符串字面量里的字符被编码成一个或多个 [[g:code-unit]]，所用的编码称为该字面量的 [[g:literal-encoding|literal encoding]]。普通字面量（无前缀）用 **ordinary literal encoding**，`L` 前缀用 **wide literal encoding**。¶5 只给了很少的保证——[[g:basic-literal-character-set]] 的每个字符编成单个非负 code unit、`'\0'` 编成 0、数字 `'0'`–`'9'` 连续——其余“由实现定义”。`u8`/`u`/`U` 前缀的字面量则必须是 UTF-8/UTF-16/UTF-32。

关键在于：字面量编码在**编译时**就固定下来，烧进了目标文件。Clang 和 GCC 默认用 UTF-8（可用 `-fexec-charset=` 修改），MSVC 默认跟随系统代码页，`/utf-8` 才改为 UTF-8。这套术语由 [[P2314R4]] 在 C++23 中整理；在那之前标准用的是含义模糊的“execution character set”。

### 执行环境编码——运行期、locale-specific

[[character.seq.general#1.2]] 则定义了库使用的 [[g:execution-character-set]]：它是基本字面量字符集的超集，**其编码是 locale-specific 的**——也就是说，会随 `setlocale` 或 `std::locale::global` 在运行时改变（¶1.1）。该段的注 1 直截了当：

!!! std
    The encodings of the execution character sets can be unrelated to any literal encoding.

执行字符集的编码可以与任何字面量编码都毫无关系。

`mbrtowc`、`isalpha`、`printf("%ls")`、`std::codecvt<wchar_t, char, mbstate_t>` 这些函数解读 `char` 序列时，依据的是**当前 C locale 的编码**，而不是编译器把字面量编成了什么。一个用 UTF-8 字面量编码编译的程序，在 `LANG=C` 的环境下运行，`"中"` 的三个字节在 C 库眼里可能是三个毫不相关的单字节字符，也可能是非法序列（见 [[text.c.strings]] 的例子）。

{{c++26}} 的 `std::text_encoding`（[[text.encoding]]，[[P1885R12]]）第一次让程序能**查询**这两者：`text_encoding::literal()` 是 `consteval` 的，返回字面量编码；`text_encoding::environment()` 在运行期返回执行环境的编码。

```cpp run title="two-encodings.cpp" impl
#include <cstdio>
#include <text_encoding>

int main() {
    constexpr auto lit = std::text_encoding::literal();   // 编译期就确定
    static_assert(lit == std::text_encoding::UTF8);       // clang/gcc 默认；MSVC 需 /utf-8
    static_assert(sizeof("中") == 4);                      // 3 个 UTF-8 code unit + '\0'

    // 运行期：取决于进程环境（POSIX 上是 "" locale 对应的编码）
    std::printf("environment: %s\n", std::text_encoding::environment().name());
}
```

在本机（clang 23 + libc++，`LANG` 未设置）运行输出 `environment: US-ASCII`，设置 `LANG=zh_CN.GB18030` 后输出 `GB18030`——而字面量编码始终是 UTF-8。两者不一致时，把字面量原样交给依赖 locale 的 C 库函数，就会得到乱码。

!!! impl "libc++ 与 macOS 的可用性"
    libc++ 的 `text_encoding::environment()` 实现在动态库中，被可用性宏 `_LIBCPP_AVAILABILITY_TEXT_ENCODING_ENVIRONMENT` 标为 LLVM 23 才引入；在 macOS 上用系统自带的 libc++ 动态库时，调用它会直接报 “'environment' is unavailable”。本站的例子是用 `-D_LIBCPP_DISABLE_AVAILABILITY` 并链接 Homebrew LLVM 自带的 libc++ 验证的。`literal()` 是纯头文件实现，不受影响。

## 演进趋势：新设施与 locale 解耦

C++98 的本地化模型（[[localization]]）是“**默认就本地化**”：iostream 的每个格式化操作都去查流上 imbue 的 locale，C 的 `printf`/`strtod` 查全局 C locale。这带来三个工程问题：

1. **结果不可预测**：库或插件里一句 `setlocale(LC_ALL, "")` 就能让 JSON 序列化器输出 `1,5` 而不是 `1.5`。
2. **慢**：每次格式化都要经过虚函数和 facet 查找。
3. **线程不安全**：`setlocale` 与几十个 C 库函数之间存在数据竞争（[[c.locales]]）。

C++17 之后新增的文本设施一律反过来——**默认与 locale 无关，只有显式要求时才本地化**：

| 设施 | 默认行为 | 如何本地化 |
|---|---|---|
| `to_chars`/`from_chars`（C++17，[[P0067R5]]） | 永远是 `"C"` locale 语义 | 不能 |
| `std::format`（C++20，[[P0645R10]]） | 与 locale 无关 | 格式说明里写 `L`，并可传入 `std::locale` 实参（[[format.string.std]]） |
| `std::print`（C++23） | 同 `format`；输出到终端时按 Unicode 处理 | 同上 |
| `to_string(double)` | C++26 起定义为 `format("{}", val)`（[[P2587R3]]），不再随 C locale 变化 | 不能 |
| `text_encoding::literal()`（C++26） | 编译期常量 | — |

```cpp run title="locale-independence.cpp" impl
#include <charconv>
#include <cstdio>
#include <format>
#include <locale>
#include <string>

int main() {
    std::locale::global(std::locale("de_DE.UTF-8"));   // 有名字，所以也会 setlocale(LC_ALL, ...)
    char buf[32];
    std::snprintf(buf, sizeof buf, "%.1f", 1.5);
    std::printf("printf     : %s\n", buf);                       // 1,5   ← 跟随 C locale
    auto r = std::to_chars(buf, buf + sizeof buf, 1.5);
    std::printf("to_chars   : %.*s\n", int(r.ptr - buf), buf);   // 1.5   ← 永远 "C"
    std::printf("format {}  : %s\n", std::format("{}", 1.5).c_str());            // 1.5
    std::printf("format {:L}: %s\n", std::format("{:L}", 1234567.5).c_str());   // 1.234.567,5
    std::printf("to_string  : %s\n", std::to_string(1.5).c_str());
}
```

本机输出中 `to_string` 一行是 `1,500000`：草案 [[string.conversions]] 已规定浮点 `to_string` 返回 `format("{}", val)`（应为 `1.5`），但截至本文编写时 libc++ 仍按旧规则（`sprintf("%f")`，受 C locale 影响）实现。

!!! note "这不是说 locale 被废弃了"
    `std::locale`、facet 和 iostream 的本地化仍是规范的一部分，也仍是 `{:L}` 背后的实现机制（`format` 用的正是 `numpunct` facet）。变化在于默认值：**需要本地化的地方显式开启，其余地方得到确定的、可往返的输出。** 另一方面，C++26 删除了 `<codecvt>` 头文件（`codecvt_utf8` 等）以及 `wstring_convert`/`wbuffer_convert`（[[diff.cpp23.depr]]），标准目前**没有**替代的 Unicode 转码设施。

## 各子条款的定位

- **[[charconv]]**：最底层的积木。`format` 对算术类型的默认输出就是“as if `to_chars`”定义的。
- **[[localization]]** / **[[locale.categories]]** / **[[c.locales]]**：locale 对象模型、12 类标准 facet、以及 `<clocale>` 的 `setlocale` 与数据竞争。
- **[[text.encoding]]**：只**识别**编码（IANA 注册表的名字和 MIB 号），不做任何转码。
- **[[format]]**：本章篇幅最大的部分，本站拆为 [[format]]（架构与函数）、[[format.string]]（格式串语法）、[[format.formatter]]（定制与范围格式化）三页。
- **[[re]]** / **[[re.alg]]**：C++11 的正则库。接口设计完整，但主流实现性能普遍不佳，且 ABI 冻结使其难以改进。
- **[[text.c.strings]]**：`<cctype>` 等 C 头文件的“内容与 C 相同”声明，以及多字节转换函数的数据竞争说明。

## 思考题

<details markdown="1">
<summary>1. 用 UTF-8 字面量编码编译的程序里，`std::isalpha('é')` 有什么问题？</summary>

`'é'` 在 UTF-8 下需要两个 code unit，不是单个 `char` 能表示的；按 [[lex.ccon]]，不能编码为单个 code unit 的普通字符字面量是{{ill-formed}}（Clang 报错 “character too large for enclosing character literal type”）。退一步，即使写成 `std::isalpha(s[0])`（`s` 是 `"é"`），`s[0]` 是 `0xC3`，在 `char` 有符号的平台上是负值，传给 `<cctype>` 的 `isalpha` 是 {{ub}}（C 标准要求实参可表示为 `unsigned char` 或等于 `EOF`），且即使转成 `unsigned char`，结果也取决于**当前 C locale 的编码**（[[character.seq.general#1.2]]），而不是字面量编码。
</details>

<details markdown="1">
<summary>2. 为什么 `text_encoding::literal()` 可以是 `consteval`，而 `environment()` 连 `constexpr` 都不是？</summary>

字面量编码是翻译期决定的实现定义属性（[[lex.charset#5]]），编译器在编译时就知道（Clang 通过预定义宏 `__clang_literal_encoding__` 暴露给库）。执行环境编码是 locale-specific 的（[[character.seq.general#1.1]]），取决于程序运行时的进程环境，编译期无从知晓。[[text.encoding.members#14]] 规定 `environment()` 在 POSIX 上返回 `""` locale 的编码，并且注 2 说明它**不受** `setlocale` 影响——它反映的是环境，不是当前的 C locale。
</details>

## 小结

| 概念 | 何时确定 | 由谁决定 | 标准出处 |
|---|---|---|---|
| ordinary/wide literal encoding | 编译期 | 实现（编译器选项） | [[lex.charset#4]] |
| `u8`/`u`/`U` 字面量编码 | 编译期 | 固定为 UTF-8/16/32 | [[lex.charset#5]] |
| 执行字符集编码 | 运行期，可变 | 当前 C locale | [[character.seq.general#1.2]] |
| 环境编码 | 运行期 | 进程环境（POSIX: `""` locale） | [[text.encoding.members#14]] |
| locale 对象的编码 | 运行期 | 该 `std::locale` | [[locale.members#7]] |
