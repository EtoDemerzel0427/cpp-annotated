---
title: 字符字面量
summary: 五种编码前缀对应的字符字面量种类与类型，转义序列（简单、八进制、十六进制、分隔形式 \o{} \x{}、条件转义），多字符字面量，以及值的确定规则——C++23 起不可编码的字符非良构。
status: draft
papers: P2029R4, P2290R3, P2362R3
related: lex.charset, lex.universal.char, lex.string, basic.fundamental, cpp.cond
tags: 字面量, 字符, 转义序列, Unicode
updated: 2026-10-17
---

[[lex.ccon]] 规定字符字面量。它和 [[lex.string]] 共享"编码前缀"与"转义序列"两套机制，所以本页也是理解字符串字面量的基础。C++23 对本节做了三处重要修订：数值转义的语义（[[P2029R4]]）、分隔形式的转义（[[P2290R3]]）、以及删除"不可编码"的和宽字符的多字符字面量（[[P2362R3]]）。

## 文法

```
character-literal:
    encoding-prefix(opt) ' c-char-sequence '
encoding-prefix: one of
    u8  u  U  L
c-char:
    basic-c-char
    escape-sequence
    universal-character-name
basic-c-char:
    翻译字符集中除 '、\、换行 以外的任何成员

escape-sequence:
    simple-escape-sequence
    numeric-escape-sequence
    conditional-escape-sequence
simple-escape-sequence:
    \ simple-escape-sequence-char
simple-escape-sequence-char: one of
    '  "  ?  \  a  b  f  n  r  t  v
numeric-escape-sequence:
    octal-escape-sequence
    hexadecimal-escape-sequence
octal-escape-sequence:
    \ octal-digit
    \ octal-digit octal-digit
    \ octal-digit octal-digit octal-digit
    \o{ simple-octal-digit-sequence }
hexadecimal-escape-sequence:
    \x simple-hexadecimal-digit-sequence
    \x{ simple-hexadecimal-digit-sequence }
conditional-escape-sequence:
    \ conditional-escape-sequence-char
conditional-escape-sequence-char:
    基本字符集中不是 octal-digit、simple-escape-sequence-char，
    也不是 N、o、u、U、x 的任何成员
```

转义序列分三类，各有不同的语义：

| 类别 | 例 | 含义 |
|---|---|---|
| 简单转义 | `\n` `\t` `\\` `\'` `\"` `\?` `\a` `\b` `\f` `\r` `\v` | 表示一个**字符**（表 10），按字面量编码编码 |
| 数值转义 | `\0` `\101` `\o{101}` `\x41` `\x{41}` | 直接给出一个 **code unit 的值** |
| 条件转义 | `\q` `\e` `\8` `\%` | 有条件支持，值由实现定义 |
| （UCN） | `\u00E9` `\U0001F600` `\u{E9}` `\N{EURO SIGN}` | 表示一个**字符**，按字面量编码编码（[[lex.universal.char]]） |

"字符"与"code unit 值"的区别是关键：`'\u00E9'` 说的是"字符 é"，编译器负责把它编码；`'\xE9'` 说的是"值为 0xE9 的 code unit"，不经过任何编码。在 UTF-8 普通字面量编码下，前者因需要两个 code unit 而非良构，后者合法。

### 转义序列的长度

- 八进制转义**最多 3 位**：`"\1012"` 是 `'A'`（`\101`）后跟 `'2'`。
- 十六进制转义 `\x` **贪婪，长度不限**：`"\x41BC"` 是**一个**值为 0x41BC 的转义，对 `char` 来说超出范围，非良构。
- C++23 的分隔形式 `\o{...}`、`\x{...}` 明确了边界，解决了上述两个问题：`"\x{41}BC"` 是 `"ABC"`。在 C++23 之前，只能用字符串拼接来截断：`"\x41" "BC"`（拼接时各段的转义序列独立解释，见 [[lex.string#8]]）。

```cpp run title="escapes.cpp" ok
static_assert('\101' == 'A' && '\o{101}' == 'A' && '\x{41}' == 'A');
static_assert('\0' == 0);                   // \0 是一个八进制转义
static_assert(sizeof("\1012") == 3);        // "\101" "2"：A、2、NUL
static_assert(sizeof("\x{41}BC") == 4);     // A、B、C、NUL
static_assert(sizeof("\x41" "BC") == 4);    // C++23 前的写法
static_assert('\?' == '?');
int main() {}
```

```cpp title="hex-greedy.cpp" error
char a = "\x41BC"[0];   // error：\x41BC 是一个十六进制转义，0x41BC 超出 char 的范围
```

### 条件转义

`\` 后跟任何**没有被赋予含义的**基本字符（如 `\q`、`\e`、`\8`、`\%`）构成条件转义序列：有条件支持，值（或在字符串中的 code unit 序列）由实现定义。最常见的实际用法是 GCC/Clang 的 `\e`（ESC，0x1B），Clang 在 `-pedantic` 下对它警告"use of non-standard escape character"；对 `\q` 这种无意义的转义，Clang 警告"unknown escape sequence"并取字符本身。

注意 `N`、`o`、`u`、`U`、`x` 被排除在条件转义之外：它们分别开始 `\N{}`、`\o{}`、`\u`、`\U`、`\x` 序列，写错时（如 `\N` 后没有 `{`）就是非良构，而不是"有条件支持"。`8`、`9` 不是八进制数字，所以 `\8` 是条件转义而不是数值转义。

## ¶1：多字符字面量

¶1 [[g:multicharacter-literal|**多字符字面量**]]（multicharacter literal）是 *c-char-sequence* 含有**多于一个** *c-char* 的字符字面量。

- 多字符字面量**不得有编码前缀**：`u'ab'`、`L'ab'` 非良构。
- 若其中某个 *c-char* 不能在普通字面量编码中编码为**单个** code unit，程序非良构：`'aé'`（UTF-8 编码下）非良构。
- 多字符字面量是**有条件支持**的。

其类型为 `int`，值由实现定义（¶2、¶3）。

```cpp run title="multichar.cpp" impl
static_assert(sizeof('abcd') == sizeof(int));
static_assert('ab' == ('a' * 256 + 'b'));   // GCC/Clang 的做法：按大端顺序拼接
int main() {}
```

多字符字面量来自 C 的古老传统（如 Mac OS 经典的四字符代码 `'TEXT'`）。它的值不可移植：Clang 和 GCC 以"第一个字符在最高位"的方式拼接，但标准不作保证。Clang 默认给出 `-Wmultichar` 警告。

!!! history "C++23：删除宽字符的多字符字面量"
    C++20 中，`L'ab'` 这样的宽多字符字面量是有条件支持的，值由实现定义；不同实现给出的值完全不同（有的取第一个字符，有的取最后一个）。[[P2362R3]] 认为它们没有可移植的用途，将其改为非良构；同时规定在字面量编码中**无法表示**的字符（"不可编码的字符字面量"）也非良构，而不再是"有条件支持、值由实现定义"。

## ¶2：种类与类型

¶2 字符字面量的种类、类型及其关联的字符编码（[[lex.charset]]）由编码前缀和 *c-char-sequence* 决定（表 9）：

| 前缀 | 种类 | 类型 | 关联编码 | 例 |
|---|---|---|---|---|
| 无 | **普通字符字面量**（ordinary character literal） | `char` | 普通字面量编码 | `'v'` |
| 无 | 多字符字面量 | `int` | 普通字面量编码 | `'abcd'` |
| `L` | **宽字符字面量** | `wchar_t` | 宽字面量编码 | `L'w'` |
| `u8` | **UTF-8 字符字面量** | `char8_t` | UTF-8 | `u8'x'` |
| `u` | **UTF-16 字符字面量** | `char16_t` | UTF-16 | `u'y'` |
| `U` | **UTF-32 字符字面量** | `char32_t` | UTF-32 | `U'z'` |

```cpp run title="ccon-types.cpp" ok
#include <type_traits>
static_assert(std::is_same_v<decltype('a'), char>);       // C 中是 int！
static_assert(std::is_same_v<decltype(L'a'), wchar_t>);
static_assert(std::is_same_v<decltype(u8'a'), char8_t>);  // C++20 起；C++17 中是 char
static_assert(std::is_same_v<decltype(u'a'), char16_t>);
static_assert(std::is_same_v<decltype(U'a'), char32_t>);
int main() {}
```

两处与其他语言/版本的差异：

- **C 中 `'a'` 的类型是 `int`**，C++ 中是 `char`。[[diff.lex]] 解释了理由：让 `f('x')` 在 `f(int)` 与 `f(char)` 之间选中后者。后果是 `sizeof('x')` 在 C 和 C++ 中不同。
- **`u8'x'` 在 C++17 中是 `char`，C++20 起是 `char8_t`**（[[diff.cpp17.lex]]，[[P0482R6]]），以便重载和模板能区分"UTF-8 编码的数据"和"普通字符"。

## ¶3：值

¶3 首先，一条关于**预处理器**的规定：在阶段 4，字符字面量的值用其类型在阶段 7 的取值范围来确定。于是 `#if` 中字符字面量的值与普通代码中一致——包括 `char` 的符号性：

```cpp run title="pp-char.cpp" impl
#if '\xFF' < 0
static_assert('\xFF' == -1);   // char 有符号的平台（x86-64、AArch64 Linux/macOS 默认）
#else
static_assert('\xFF' == 255);  // char 无符号的平台（如 AArch64 Linux 上的 GCC 默认、或 -funsigned-char）
#endif
int main() {}
```

（`char` 是否有符号由实现定义，[[basic.fundamental]]。AArch64 Linux 的 ABI 规定 `char` 无符号，而 Apple 的 arm64 平台把 `char` 定为有符号。）

多字符字面量的值由实现定义。其他字符字面量的值如下：

### ¶3.1　单个字符：编码后的 code unit

*c-char-sequence* 是单个 *basic-c-char*、*simple-escape-sequence* 或 *universal-character-name* 时，值是该字符在关联编码中编码后的 code unit 值。如果该字符在关联编码中**没有表示**，或**不能编码为单个 code unit**，程序非良构。

```cpp title="ccon-encode.cpp" error
char8_t  a = u8'é';    // error：é 的 UTF-8 编码需要两个 code unit
char16_t b = u'😀';    // error：U+1F600 的 UTF-16 编码需要代理对
char     c = 'é';      // error（普通字面量编码为 UTF-8 时）：同样需要两个 code unit
char32_t d = U'😀';    // OK：UTF-32 总是单个 code unit
```

最后一行之外全部非良构。这条规则让"字符字面量"真正表示一个字符：要表示非 BMP 字符请用 `U'...'`，要表示 UTF-8 多字节序列请用字符串 `u8"é"`。

### ¶3.2　数值转义：值，必要时取模

*c-char-sequence* 是单个 *numeric-escape-sequence* 时：

- ¶3.2.1　设 v 为八进制或十六进制数字表示的整数值。
- ¶3.2.2　若 v 不超出字面量类型的取值范围，值就是 v。
- ¶3.2.3　否则，若编码前缀**缺省或为 `L`**，且 v 不超出该类型的**底层类型对应的无符号类型**的范围，则值是该类型 T 中与 v 模 2^N 同余的唯一值（N 是 T 的宽度）。
- ¶3.2.4　否则，程序非良构。

¶3.2.3 专为有符号的 `char`/`wchar_t` 而设：`'\xFF'` 在 `char` 有符号时 v = 255 超出 [−128, 127]，但不超出 `unsigned char` 的范围，于是值为 −1——这是程序员写 `'\xFF'` 时的真实意图（"所有位为 1 的字节"）。`u8`/`u`/`U` 前缀的类型都是无符号的，不需要这条回绕规则。

```cpp run title="numeric-escape.cpp" ok
static_assert(u8'\xFF' == 0xFF);    // char8_t 无符号，v 在范围内
static_assert(u'\xFFFF' == 0xFFFF);
static_assert(L'\xFFFFFFFF' == -1 || L'\xFFFFFFFF' == 0xFFFFFFFF);  // wchar_t 符号性因平台而异
int main() {}
```

```cpp title="numeric-escape-bad.cpp" error
char     a = '\x100';      // error：0x100 超出 unsigned char 的范围
char8_t  b = u8'\x100';    // error：超出 char8_t，且 u8 前缀不回绕
char16_t c = u'\x10000';   // error
```

!!! history
    C++20 及以前，超出范围的数值转义的值是**实现定义**的，八进制与十六进制的措辞还不一致。[[P2029R4]]（C++23）统一了规则并给出了上面的精确语义；它同时规定数值转义在字符串中只贡献**一个** code unit，见 [[lex.string#10]]。

### ¶3.3　条件转义

单个 *conditional-escape-sequence* 的字符字面量是有条件支持的，值由实现定义。

## ¶4：简单转义序列表

¶4 简单转义序列表示的字符见表 10：

| 字符 | 转义 | 字符 | 转义 |
|---|---|---|---|
| U+000A 换行 | `\n` | U+000C 换页 | `\f` |
| U+0009 水平制表 | `\t` | U+0007 响铃 | `\a` |
| U+000B 垂直制表 | `\v` | U+005C 反斜杠 | `\\` |
| U+0008 退格 | `\b` | U+003F 问号 | `\?` |
| U+000D 回车 | `\r` | U+0027 单引号 | `\'` |
| | | U+0022 双引号 | `\"` |

注 1：问号的转义序列是为了与 C++14 和 C 兼容。它存在的唯一理由是三字符组：在 C++14 中 `"??/"` 是 `"\"`，要写出两个问号接斜杠必须写 `"?\?/"`。三字符组删除后，`\?` 只是 `?`。

`\'` 在字符串中不是必需的（`"'"` 合法），`\"` 在字符字面量中不是必需的（`'"'` 合法），但两种写法在两处都有效。

!!! lawyer "悬空的术语“不可编码的字符字面量”"
    [[lex.charset#4]] 说"多字符字面量或**不可编码的字符字面量**（non-encodable character literal）以外的字符字面量"中的字符按字面量编码被编码。但当前的 [[lex.ccon]] 已经不再定义"不可编码的字符字面量"——C++23 起这种字面量直接非良构（¶3.1）。所以这个短语在当前草案中不指代任何良构的东西，属于修订遗留的措辞，没有规范效果。

## 实现视角

!!! impl
    - **`char` 的符号性**：x86/x86-64 上 GCC、Clang、MSVC 都把 `char` 定为有符号；AArch64 Linux（及多数 ARM/PowerPC Linux）上为无符号；Apple arm64 为有符号。GCC/Clang 可用 `-fsigned-char`/`-funsigned-char` 改变。
    - **宽字符**：Windows 上 `wchar_t` 是 16 位、UTF-16 编码，所以 `L'😀'` 非良构；Linux/macOS 上是 32 位 UTF-32，`L'😀'` 合法。
    - **诊断**：Clang 对 ¶3.1 违规报"character too large for enclosing character literal type"，对数值转义超范围报"hex escape sequence out of range"/"octal escape sequence out of range"，对 `u'ab'` 报"Unicode character literals may not contain multiple characters"。

## 陷阱

!!! pitfall "`'é'` 在不同编译器设置下行为不同"
    普通字面量编码由实现定义：MSVC 在 Latin-1 类代码页下 `'é'` 是单字节，合法；GCC/Clang 默认 UTF-8，非良构。可移植代码中非 ASCII 字符请用 `u8`/`u`/`U` 字面量。

!!! pitfall "`\x` 吞掉后面的十六进制字母"
    `"\x1Bcolor"` 不是 ESC + `color`，而是 `\x1Bc` + `olor`（`c` 是十六进制数字）。写 `"\x{1B}color"`（C++23）或 `"\x1B" "color"`。

!!! pitfall "以为 `'\0'` 是一个特殊转义"
    它只是八进制转义 `\` + `0`。所以 `"\012"` 是换行（八进制 12 = 10），不是 NUL 后跟 `12`。

## 思考题

!!! question "思考题 1"
    在 x86-64 Linux（`char` 有符号、普通字面量编码 UTF-8）上，下列字面量的类型与值是什么，或者为何非良构？

    ```cpp
    '\377'    '\u00FF'    u8'\377'    '\N{LATIN SMALL LETTER Y WITH DIAERESIS}'    L'\xFFFFFFFFF'
    ```

<details markdown="1">
<summary>答案</summary>

- `'\377'`：八进制数值转义，v = 255，超出 `signed char` 范围但在 `unsigned char` 范围内，前缀缺省 ⇒ 回绕为 −1，类型 `char`。
- `'\u00FF'`：UCN，字符 ÿ；UTF-8 编码为 C3 BF 两个 code unit ⇒ 非良构（¶3.1）。
- `u8'\377'`：数值转义，v = 255 在 `char8_t` 范围内 ⇒ 值 255，类型 `char8_t`。注意它不是"字符 ÿ"，只是一个值为 0xFF 的 code unit（在 UTF-8 中不是有效的单独字节）。
- `'\N{LATIN SMALL LETTER Y WITH DIAERESIS}'`：同 `'\u00FF'`，非良构。
- `L'\xFFFFFFFFF'`：v = 0xFFFFFFFFF 需要 36 位，超出 32 位 `wchar_t` 对应的无符号类型 ⇒ 非良构（¶3.2.4）。
</details>

!!! question "思考题 2"
    为什么 ¶3.2.3 的"回绕"只对无前缀和 `L` 前缀适用？

<details markdown="1">
<summary>答案</summary>

只有 `char` 和 `wchar_t` 可能是有符号类型。`char8_t`、`char16_t`、`char32_t` 都是无符号的，其"底层类型对应的无符号类型"就是其底层类型本身，"超出类型范围"与"超出无符号范围"是同一回事，不存在需要回绕的中间地带。回绕规则的目的正是让 `'\xFF'` 这类"按位写一个字节"的惯用法在有符号 `char` 上得到明确的值（−1），而不是实现定义。
</details>

## 小结

!!! summary
    - 五种前缀：无（`char`）、`L`（`wchar_t`）、`u8`（`char8_t`，C++20）、`u`（`char16_t`）、`U`（`char32_t`）；多字符字面量为 `int`，有条件支持，不能带前缀。
    - 字符（基本字符、简单转义、UCN）按关联编码编码，必须恰好一个 code unit，否则非良构（C++23）。
    - 数值转义直接给出 code unit 值；超出范围时，无前缀/`L` 可按模 2^N 回绕，否则非良构。
    - 八进制转义最多 3 位，`\x` 不限位数；C++23 的 `\o{}`、`\x{}` 给出明确边界。
    - 条件转义（`\e` 等）有条件支持，值由实现定义。
    - C 中 `'a'` 是 `int`，C++ 中是 `char`。
