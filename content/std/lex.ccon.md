---
title: 字符字面量
summary: 字符字面量的五种前缀和对应类型、三类转义序列、值怎样确定（编码后必须恰好占一个 code unit），以及多字符字面量。
status: done
papers: P2029R4, P2290R3, P2362R3, P0482R6
related: lex.charset, lex.universal.char, lex.string, basic.fundamental, cpp.cond
tags: 字面量, 字符, 转义序列, Unicode
updated: 2026-10-19
---

!!! tldr
    - 前缀决定类型：`'a'` 是 `char`，`L'a'` 是 `wchar_t`，`u8'a'` 是 `char8_t`，`u'a'` 是 `char16_t`，`U'a'` 是 `char32_t`。C 里的 `'a'` 是 `int`，C++ 里不是。
    - 一个字符编码后必须恰好占一个 code unit，否则非良构：在 UTF-8 下 `'é'` 和 `u8'é'` 都不合法，`U'😀'` 合法。
    - `'é'` 写的是一个字符，由编译器去编码；`'\xE9'` 写的是一个 code unit 的值，不经过编码。
    - 八进制转义最多三位，`\x` 会吞掉后面所有的十六进制数字；C++23 的 `\x{...}`、`\o{...}` 给出明确的边界。
    - `'ab'` 这样的多字符字面量类型是 `int`，有条件支持，值由实现定义，不能带前缀。

字符字面量和字符串字面量（[[lex.string]]）共用编码前缀和转义序列两套机制，所以本页的内容也是理解字符串字面量的基础。下文常用两个词，都在 [[lex.charset]] 中定义：**code unit** 是某个字符类型的一个整数值，例如 UTF-8 的一个字节；**字面量编码**（literal encoding）是编译器把源码中的字符转换成 code unit 序列时使用的编码，普通字面量用的那一种叫**普通字面量编码**，GCC 和 Clang 默认是 UTF-8。

## 前缀与类型（¶2）

```cpp run title="ccon-types.cpp" ok
#include <type_traits>
static_assert(std::is_same_v<decltype('a'), char>);       // C 中是 int
static_assert(std::is_same_v<decltype(L'a'), wchar_t>);
static_assert(std::is_same_v<decltype(u8'a'), char8_t>);  // C++17 中是 char
static_assert(std::is_same_v<decltype(u'a'), char16_t>);
static_assert(std::is_same_v<decltype(U'a'), char32_t>);
int main() {}
```

¶2 字符字面量的种类、类型和关联的字符编码由编码前缀和引号内的内容决定：

| 前缀 | 种类 | 类型 | 关联编码 |
|---|---|---|---|
| 无 | 普通字符字面量 | `char` | 普通字面量编码 |
| 无（多个字符） | 多字符字面量 | `int` | 普通字面量编码 |
| `L` | 宽字符字面量 | `wchar_t` | 宽字面量编码 |
| `u8` | UTF-8 字符字面量 | `char8_t` | UTF-8 |
| `u` | UTF-16 字符字面量 | `char16_t` | UTF-16 |
| `U` | UTF-32 字符字面量 | `char32_t` | UTF-32 |

C 中 `'a'` 的类型是 `int`，C++ 改成了 `char`。[[diff.lex]] 给出的理由是重载：有 `f(int)` 和 `f(char)` 时，`f('x')` 应当选后者。代价是 `sizeof('x')` 在两种语言里不同。

`u8'x'` 在 C++17 中是 `char`，C++20 起是 `char8_t`（[[P0482R6]]、[[diff.cpp17.lex]]）。有了独立的类型，重载和模板就能区分 UTF-8 数据与按普通字面量编码存储的文本。

## 转义序列

引号里的每一项要么是一个普通字符，要么是一个转义序列，要么是一个通用字符名（`\u00E9` 这类，见 [[lex.universal.char]]）。转义序列分三类，含义不同：

| 类别 | 例子 | 表示什么 |
|---|---|---|
| 简单转义 | `\n` `\t` `\\` `\'` `\"` `\?` `\a` `\b` `\f` `\r` `\v` | 一个字符，按字面量编码编码 |
| 数值转义 | `\0` `\101` `\o{101}` `\x41` `\x{41}` | 一个 code unit 的值，不经过编码 |
| 条件转义 | `\e` `\q` `\8` | 有条件支持，值由实现定义 |

关键是区分字符和 code unit 的值。`'é'` 表示字符 é，编译器按 UTF-8 编码它时需要两个字节，所以非良构（见下文 ¶3.1）。`'\xE9'` 只表示一个值为 0xE9 的 code unit，不涉及编码，所以合法。

### 数值转义的长度

八进制转义是 `\` 后跟一到三个八进制数字，最多三位：`"\1012"` 是 `\101`（即 `A`）后跟字符 `2`。`\0` 也只是一个八进制转义，没有特殊地位。

十六进制转义 `\x` 没有长度上限，会吞掉后面所有的十六进制数字。`"\x41BC"` 是一个值为 0x41BC 的转义，对 `char` 来说超出范围，非良构。

C++23 加入了带花括号的形式 `\o{...}` 和 `\x{...}`（[[P2290R3]]），边界由花括号决定：`"\x{41}BC"` 就是 `"ABC"`。在此之前，只能把字符串拆成两段相邻的字面量来截断转义，因为每一段的转义序列各自解释（[[lex.string]]）。

```cpp run title="escapes.cpp" ok
static_assert('\101' == 'A' && '\o{101}' == 'A' && '\x{41}' == 'A');
static_assert('\0' == 0 && '\012' == '\n');  // \012 是八进制 12，即 10
static_assert(sizeof("\1012") == 3);         // A、2、空字符
static_assert(sizeof("\x{41}BC") == 4);      // A、B、C、空字符
static_assert(sizeof("\x41" "BC") == 4);     // C++23 之前的写法
int main() {}
```

### 简单转义（¶4）

¶4 简单转义表示的字符是：`\n` 换行（U+000A）、`\t` 水平制表、`\v` 垂直制表、`\b` 退格、`\r` 回车、`\f` 换页、`\a` 响铃、`\\` 反斜杠、`\?` 问号、`\'` 单引号、`\"` 双引号。

注 1 说明，`\?` 是为了与 C++14 和 C 兼容而保留的。它原本用来避开三字符组：C++14 中 `??/` 会被替换成 `\`，要写出两个问号加斜杠，就得写 `?\?/`。C++17 删除三字符组以后，`\?` 就只是 `?`。

字符串里的单引号和字符字面量里的双引号都不必转义（`"'"`、`'"'` 都合法），但转义了也没错。

### 条件转义

`\` 后跟一个没有被赋予含义的基本字符，例如 `\e`、`\q`、`\8`，构成**条件转义**。它是有条件支持的（实现可以不支持，但不支持时必须诊断），值由实现定义。

`N`、`o`、`u`、`U`、`x` 不能构成条件转义，因为它们分别引出 `\N{...}`、`\o{...}`、`\u`、`\U`、`\x`。所以 `'\N'` 后面缺少 `{` 时是非良构的，而不是有条件支持。`8` 和 `9` 不是八进制数字，所以 `\8` 是条件转义。

本机 Clang 23 把 `\e` 当作 ESC（0x1B），在 `-pedantic` 下给出 "use of non-standard escape character" 警告。对 `\q`、`\8`，它给出 `-Wunknown-escape-sequence` 警告，取字符本身。

## 值（¶3）

¶3 多字符字面量的值由实现定义，其他字符字面量的值按下面三种情况确定。

### 单个字符：编码后的 code unit（¶3.1）

¶3.1 如果引号里是单个普通字符、简单转义或通用字符名，值就是这个字符在关联编码中的 code unit。如果关联编码无法表示这个字符，或者需要不止一个 code unit，程序非良构。

```cpp title="ccon-encode.cpp" error
char8_t  a = u8'é';   // error: é 的 UTF-8 编码需要两个 code unit
char16_t b = u'😀';   // error: U+1F600 在 UTF-16 中需要两个 code unit
char     c = 'é';     // error: 普通字面量编码为 UTF-8 时，同上
char32_t d = U'😀';   // OK：UTF-32 总是一个 code unit
```

这条规则保证一个字符字面量确实表示一个字符。需要表示 BMP 以外的字符时用 `U'...'`；需要 é 的 UTF-8 字节序列时用字符串 `u8"é"`。本机 Clang 23 对前三行报 "character too large for enclosing character literal type"。

### 数值转义：给定的值，必要时回绕（¶3.2）

¶3.2 如果引号里是单个数值转义，设 v 为转义中数字表示的整数：

- ¶3.2.2 v 在字面量类型的取值范围内，值就是 v。
- ¶3.2.3 否则，如果没有前缀或前缀是 `L`，并且 v 在该类型对应的无符号类型的范围内，值是该类型中与 v 模 2^N 同余的那个值（N 是类型的位宽）。
- ¶3.2.4 否则，程序非良构。

¶3.2.3 是为有符号的 `char` 和 `wchar_t` 准备的。`char` 有符号时，`'\xFF'` 的 v 是 255，超出了 [−128, 127]，但没有超出 `unsigned char` 的范围，于是值为 −1。这正是写 `'\xFF'` 的本意：一个所有位都为 1 的字节。`char8_t`、`char16_t`、`char32_t` 都是无符号类型，用不到这条规则。

```cpp run title="numeric-escape.cpp" ok
static_assert(u8'\xFF' == 0xFF);  // char8_t 无符号，v 在范围内
static_assert(u'\xFFFF' == 0xFFFF);
// wchar_t 的符号性因平台而异
static_assert(L'\xFFFFFFFF' == -1 || L'\xFFFFFFFF' == 0xFFFFFFFF);
int main() {}
```

```cpp title="numeric-escape-bad.cpp" error
char     a = '\x100';     // error: 超出 unsigned char 的范围
char8_t  b = u8'\x100';   // error: 超出 char8_t，u8 前缀不回绕
char16_t c = u'\x10000';  // error: 超出 char16_t
```

C++20 及以前，超出范围的数值转义的值由实现定义。C++23 的 [[P2029R4]] 给出了上面的精确规则，同时规定数值转义在字符串中只占一个 code unit。

### 条件转义（¶3.3）

¶3.3 由单个条件转义构成的字符字面量有条件支持，值由实现定义。

### 预处理器里的值

¶3 开头还规定，在翻译阶段 4（预处理），字符字面量的值按它的类型在阶段 7（编译）的取值范围来确定。所以 `#if` 里字符字面量的值与普通代码中一致，`char` 的符号性也一样：

```cpp run title="pp-char.cpp" impl
#if '\xFF' < 0
static_assert('\xFF' == -1);   // char 有符号：x86-64、Apple arm64
#else
static_assert('\xFF' == 255);  // char 无符号：AArch64 Linux，或 -funsigned-char
#endif
int main() {}
```

`char` 是否有符号由实现定义（[[basic.fundamental]]）。x86 和 x86-64 上 GCC、Clang、MSVC 都把它定为有符号；AArch64 Linux 的 ABI 规定无符号；Apple arm64 则是有符号。GCC 和 Clang 可以用 `-fsigned-char`、`-funsigned-char` 切换。

## 多字符字面量（¶1）

¶1 引号里有不止一个字符或转义的字面量叫做**多字符字面量**（multicharacter literal）。它不能带编码前缀；其中每一项都必须能在普通字面量编码中编码为单个 code unit；它是有条件支持的。按 ¶2 和 ¶3，它的类型是 `int`，值由实现定义。

```cpp run title="multichar.cpp" impl
static_assert(sizeof('abcd') == sizeof(int));
static_assert('ab' == ('a' * 256 + 'b'));  // GCC、Clang：第一个字符在高位
int main() {}
```

多字符字面量来自 C 的老传统，例如经典 Mac OS 用 `'TEXT'` 这样的四字符代码标识文件类型。它的值不可移植，Clang 默认给出 `-Wmultichar` 警告。`u'ab'`、`L'ab'` 和 UTF-8 下的 `'aé'` 都非良构。

!!! history "C++23 删除了宽多字符字面量"
    C++20 中，`L'ab'` 是有条件支持的，值由实现定义，各实现的结果互不相同，有的取第一个字符，有的取最后一个。[[P2362R3]] 认为它没有可移植的用途，改为非良构。同一篇提案还规定，字面量编码中无法表示的字符不再是有条件支持，而是直接非良构。

!!! lawyer "遗留的术语：不可编码的字符字面量"
    [[lex.charset#4]] 仍然写着"多字符字面量或 non-encodable character literal 以外的字符字面量"中的字符要按字面量编码编码。当前的 [[lex.ccon]] 已经不再定义这个术语，这种字面量自 C++23 起直接非良构（¶3.1），所以这个短语不指代任何良构的东西，是修订后留下的措辞。

## 实现视角

!!! impl
    - 宽字符：Windows 上 `wchar_t` 是 16 位，宽字面量编码是 UTF-16，所以 `L'😀'` 非良构；Linux 和 macOS 上 `wchar_t` 是 32 位，`L'😀'` 合法。
    - 普通字面量编码由实现定义。MSVC 不加 `/utf-8` 时通常使用系统代码页，例如 Windows-1252，`'é'` 在其中是单字节，因而合法；GCC 和 Clang 默认使用 UTF-8，`'é'` 非良构。可移植代码中的非 ASCII 字符应当用 `u8`、`u`、`U` 字面量。
    - 本机 Clang 23 的诊断：数值转义超出范围时报 "hex escape sequence out of range" 或 "octal escape sequence out of range"；对 `u'ab'` 报 "Unicode character literals may not contain multiple characters"。

## 常见误解

!!! pitfall "`\x1B` 后面可以直接跟文字"
    `\x` 会吞掉后面所有的十六进制数字。`"\x1Bcolor"` 里的转义是 `\x1Bc`，值 0x1BC 超出 `char` 的范围，编译失败。换成 `U"\x1Bcafe"` 就更隐蔽：0x1BCAFE 放得进 `char32_t`，于是字符串只有一个字符，而且没有任何诊断。应写成 `"\x{1B}color"`（C++23）或 `"\x1B" "color"`。

!!! pitfall "`'\0'` 是一个专门表示空字符的转义"
    它只是一位数的八进制转义。所以 `"\012"` 是换行符（八进制 12 等于 10），而不是空字符后跟 `12`。

## 思考题

!!! question "思考题 1"
    在 x86-64 Linux 上（`char` 有符号，普通字面量编码为 UTF-8），下列字面量的类型和值是什么？如果非良构，原因是什么？

    ```cpp
    '\377'    '\u00FF'    u8'\377'    L'\xFFFFFFFFF'
    ```

<details markdown="1">
<summary>答案</summary>

- `'\377'`：八进制数值转义，v = 255，超出 `char` 范围但在 `unsigned char` 范围内，且没有前缀，按 ¶3.2.3 回绕为 −1，类型 `char`。
- `'\u00FF'`：通用字符名，表示字符 ÿ，UTF-8 编码为 C3 BF 两个 code unit，按 ¶3.1 非良构。`'\N{LATIN SMALL LETTER Y WITH DIAERESIS}'` 是同一个字符，同样非良构。
- `u8'\377'`：数值转义，v = 255 在 `char8_t` 范围内，值为 255，类型 `char8_t`。它表示一个值为 0xFF 的 code unit，不是字符 ÿ；单独的 0xFF 在 UTF-8 中也不是合法的字节。
- `L'\xFFFFFFFFF'`：v 需要 36 位，超出 32 位 `wchar_t` 对应的无符号类型，按 ¶3.2.4 非良构。
</details>

!!! question "思考题 2"
    为什么 ¶3.2.3 的回绕规则只适用于无前缀和 `L` 前缀？

<details markdown="1">
<summary>答案</summary>

只有 `char` 和 `wchar_t` 可能是有符号类型。`char8_t`、`char16_t`、`char32_t` 都是无符号的，超出类型范围和超出对应无符号类型的范围是一回事，没有需要回绕的中间地带。回绕规则的用途是让 `'\xFF'` 这种按位写出一个字节的惯用法在有符号 `char` 上有确定的值 −1。
</details>
