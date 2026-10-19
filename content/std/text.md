---
title: 文本处理库
summary: 第 28 章导读：数值转换、locale、编码识别、格式化、正则和 C 字符串工具各管什么；字面量编码与执行环境编码的区别；新设施默认与 locale 无关的设计趋势。
status: done
covers: text.general
papers: P2314R4, P1885R12, P0067R5, P0645R10, P2587R3
related: lex.charset, character.seq, charconv, format, localization, text.encoding, re, text.c.strings, c.locales
tags: 标准库, 文本, 编码, locale, 导读
updated: 2026-10-19
---

!!! tldr
    - 第 28 章收录处理文本内容的库：`<charconv>`、`<locale>`、`<text_encoding>`、`<format>`、`<regex>` 和 C 的字符串工具。
    - 程序里至少有两种编码：字面量编码在编译时确定，执行环境编码在运行时由 C locale 决定，两者可以毫无关系。
    - 依赖 locale 的 C 函数（`isalpha`、`mbrtowc`、`printf`）按当前 C locale 的编码解读字节，而不是按编译器给字面量用的编码。
    - C++17 以后加入的文本设施默认与 locale 无关：`to_chars`、`std::format`、C++26 的 `to_string(double)`，只有显式要求时才本地化。

## 本章的组成 [text.general]

[text.general] 只有一张表（表 89），列出六个子条款：

| 子条款 | 头文件 | 本站笔记 | 内容 |
|---|---|---|---|
| [[charconv]] | `<charconv>` | [[charconv\|基础数值转换]] | 与 locale 无关、不抛异常、不分配内存的数值与文本互转 |
| [[localization]] | `<locale>`、`<clocale>` | [[localization\|locale 与 facet]]、[[locale.categories\|标准 facet]]、[[c.locales\|C 库 locale]] | C++98 的本地化框架：一个 locale 是一组按类型索引的 facet |
| [[text.encoding]] | `<text_encoding>` | [[text.encoding\|文本编码识别]] | {{c++26}} 查询字面量编码和执行环境编码 |
| [[format]] | `<format>` | [[format\|格式化库]]、[[format.string\|格式串]]、[[format.formatter\|formatter]] | 类型安全、编译期检查格式串的 `std::format` |
| [[re]] | `<regex>` | [[re\|正则表达式]]、[[re.alg\|匹配与结果]] | C++11 的 `std::regex` |
| [[text.c.strings]] | `<cctype>`、`<cwctype>`、`<cwchar>`、`<cuchar>`、`<cstdlib>` | [[text.c.strings\|C 字符串工具]] | C 库的字符分类，以及多字节与宽字符的转换 |

`format` 对数值的默认输出是借 `to_chars` 定义的；`format` 的 `L` 选项又通过 locale 的 `numpunct` facet 取得千位分隔符。所以这几部分并不独立，`charconv` 是最底层。

## 两种编码

### 字面量编码：编译时确定

```cpp run title="two-encodings.cpp" impl
#include <cstdio>
#include <text_encoding>

int main() {
    constexpr auto lit = std::text_encoding::literal();   // 编译期就确定
    static_assert(lit == std::text_encoding::UTF8);       // Clang/GCC 默认；MSVC 需 /utf-8
    static_assert(sizeof("中") == 4);                      // 3 个 UTF-8 code unit + '\0'

    // 运行期：取决于进程环境（POSIX 上是 "" locale 对应的编码）
    std::printf("environment: %s\n", std::text_encoding::environment().name());
}
```

本机（Clang 23 + libc++，未设置 `LANG`）运行输出 `environment: US-ASCII`；设置 `LANG=zh_CN.GB18030` 后输出 `GB18030`。两种情况下字面量编码都是 UTF-8。

[[lex.charset#4]] 规定，字符字面量和字符串字面量中的字符被编码成一个或多个 [[g:code-unit|code unit]]（编码单元，某个字符类型的整数值），所用的编码叫这种字面量的**字面量编码**（[[g:literal-encoding|literal encoding]]）。无前缀的普通字面量用**普通字面量编码**，`L` 前缀的用**宽字面量编码**。

[[lex.charset#5]] 只给了少量保证：[[g:basic-literal-character-set|基本字面量字符集]]中的每个字符编成单个非负的 code unit，空字符编成 0，数字 `'0'` 到 `'9'` 的值连续。其余由实现定义。`u8`、`u`、`U` 前缀的字面量则固定为 UTF-8、UTF-16、UTF-32。

字面量编码在编译时确定，写进了目标文件。Clang 和 GCC 默认用 UTF-8，可以用 `-fexec-charset=` 修改；MSVC 默认跟随系统代码页，加 `/utf-8` 才是 UTF-8。这套术语是 C++23 的 [[P2314R4]] 整理出来的，此前标准用的是含义模糊的 execution character set。

### 执行环境编码：运行时随 locale 变化

库函数解读 `char` 序列时用的是另一套编码。[[character.seq.general#1.2]] 定义了**执行字符集**（[[g:execution-character-set|execution character set]]）：它是基本字面量字符集的超集，编码是 locale-specific 的，也就是会随 `setlocale` 或 `std::locale::global` 在运行时改变（¶1.1）。

!!! std
    The encodings of the execution character sets can be unrelated to any literal encoding.

执行字符集的编码可以与任何字面量编码都没有关系。

`mbrtowc`、`isalpha`、`printf("%ls")`、`std::codecvt<wchar_t, char, mbstate_t>` 解读字节时，依据的是当前 C locale 的编码。一个以 UTF-8 字面量编码编译的程序在 `LANG=C` 下运行时，`"中"` 的三个字节在 C 库看来可能是三个无关的单字节字符，也可能是非法序列（见 [[text.c.strings]] 的例子）。两种编码不一致时，把字面量原样交给依赖 locale 的 C 函数就会得到乱码。

C++26 的 `std::text_encoding`（[[text.encoding]]，[[P1885R12]]）让程序第一次能在标准范围内查询这两种编码：`literal()` 是 `consteval` 的，返回字面量编码；`environment()` 在运行时返回环境的编码。

!!! impl "libc++ 与 macOS 的可用性标注"
    libc++ 的 `text_encoding::environment()` 实现在动态库里，并用可用性宏标注为 LLVM 23 才提供。在 macOS 上链接系统自带的 libc++ 时，调用它会报错 `'environment' is unavailable`。本站的例子是加 `-D_LIBCPP_DISABLE_AVAILABILITY` 并链接 Homebrew LLVM 自带的 libc++ 验证的。`literal()` 只在头文件里实现，不受影响。

## 新设施默认与 locale 无关

C++98 的本地化模型默认本地化：iostream 的每次格式化都查询流上 imbue 的 locale，C 的 `printf`、`strtod` 查询全局 C locale。这带来三个问题：

1. 结果不可预测：任何一个库调用 `setlocale(LC_ALL, "")`，JSON 序列化器就可能输出 `1,5` 而不是 `1.5`。
2. 慢：每次格式化都要经过虚函数调用和 facet 查找。
3. 线程不安全：`setlocale` 与几十个 C 库函数之间存在数据竞争（[[c.locales]]）。

C++17 之后新增的文本设施反过来，默认与 locale 无关，只在显式要求时本地化：

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
    std::printf("printf     : %s\n", buf);                       // 1,5：跟随 C locale
    auto r = std::to_chars(buf, buf + sizeof buf, 1.5);
    std::printf("to_chars   : %.*s\n", int(r.ptr - buf), buf);   // 1.5：永远是 "C"
    std::printf("format {}  : %s\n", std::format("{}", 1.5).c_str());            // 1.5
    std::printf("format {:L}: %s\n", std::format("{:L}", 1234567.5).c_str());   // 1.234.567,5
    std::printf("to_string  : %s\n", std::to_string(1.5).c_str());
}
```

| 设施 | 默认行为 | 如何本地化 |
|---|---|---|
| `to_chars`/`from_chars`（C++17，[[P0067R5]]） | 永远按 `"C"` locale | 不能 |
| `std::format`（C++20，[[P0645R10]]） | 与 locale 无关 | 格式说明里写 `L`，可另传 `std::locale` 实参（[[format.string.std#17]]） |
| `std::print`（C++23） | 同 `format` | 同上 |
| `to_string(double)` | C++26 起定义为 `format("{}", val)`（[[P2587R3]]） | 不能 |

本机最后一行输出 `1,500000`。草案的 [[string.conversions]] 已规定浮点 `to_string` 返回 `format("{}", val)`，应输出 `1.5`；截至写作时 libc++ 仍按旧规则用 `sprintf("%f")` 实现，结果随 C locale 变化。

locale 并没有被废弃。`std::locale`、facet 和 iostream 的本地化仍是规范的一部分，`{:L}` 背后用的也是 `numpunct` facet。变化在于默认值：需要本地化的地方显式开启，其余地方得到确定、可往返的输出。

另一方面，C++26 删除了 `<codecvt>` 头文件（`codecvt_utf8` 等）以及 `wstring_convert`、`wbuffer_convert`（[[diff.cpp23.depr]]）。标准目前没有替代它们的 Unicode 转码设施，`text_encoding` 只识别编码，不做转换。

## 思考题

!!! question "思考题 1"
    以 UTF-8 字面量编码编译的程序里，`std::isalpha('é')` 有什么问题？

<details markdown="1">
<summary>答案</summary>

`'é'` 在 UTF-8 下需要两个 code unit，放不进一个 `char`。按 [[lex.ccon]]，这样的普通字符字面量是{{ill-formed}}，Clang 报错 `character too large for enclosing character literal type`。

改写成 `std::isalpha(s[0])`（`s` 是 `"é"`）也不对。`s[0]` 是 `0xC3`，在 `char` 有符号的平台上是负值，传给 `<cctype>` 的 `isalpha` 是 {{ub}}，因为 C 标准要求实参能用 `unsigned char` 表示或等于 `EOF`。即使先转成 `unsigned char`，结果也取决于当前 C locale 的编码（[[character.seq.general#1.2]]），与字面量编码无关。
</details>

!!! question "思考题 2"
    为什么 `text_encoding::literal()` 可以是 `consteval`，而 `environment()` 连 `constexpr` 都不是？

<details markdown="1">
<summary>答案</summary>

字面量编码是翻译时确定的实现定义属性（[[lex.charset#5]]），编译器在编译时就知道。Clang 通过预定义宏 `__clang_literal_encoding__` 把它告诉标准库。

执行环境的编码取决于程序运行时的进程环境，编译时无从知道。[[text.encoding.members#14]] 规定在 POSIX 上它是 `""` locale 的编码；注 2 说明它不受 `setlocale` 影响，反映的是环境，而不是当前的 C locale。
</details>

## 小结

| 编码 | 何时确定 | 由谁决定 | 出处 |
|---|---|---|---|
| 普通、宽字面量编码 | 编译时 | 实现（编译选项） | [[lex.charset#4]] |
| `u8`、`u`、`U` 字面量编码 | 编译时 | 固定为 UTF-8/16/32 | [[lex.charset#5]] |
| 执行字符集编码 | 运行时，可变 | 当前 C locale | [[character.seq.general#1.2]] |
| 环境编码 | 运行时 | 进程环境（POSIX 上是 `""` locale） | [[text.encoding.members#14]] |
| 某个 `std::locale` 的编码 | 运行时 | 该 locale 对象 | [[locale.members#7]] |
