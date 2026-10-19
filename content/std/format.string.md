---
title: 格式串
summary: std::format 格式串的语法：替换字段与转义、自动编号与手动编号不能混用；标准格式说明 [[fill]align][sign][#][0][width][.precision][L][type] 中每个选项的含义；宽度按终端列数计算；哪些错误在编译期发现、哪些到运行期才抛出异常。
status: draft
covers: *, format.string.general, format.string.std
related: format, format.formatter, charconv, format.fmt.string, time.format, locale.numpunct
tags: 标准库, format, 格式串, Unicode
updated: 2026-10-19
---

!!! tldr
    - 格式串由替换字段 `{arg-id:format-spec}`、转义 `{{` `}}` 和普通字符组成。替换字段要么全部省略编号，要么全部写出编号，包括嵌套在宽度和精度里的字段。
    - 冒号后面的 format-spec 由实参类型的 formatter 解释，所以同一个格式串是否合法取决于实参类型。只依赖格式串和实参类型的错误都在编译期报告。
    - 标准格式说明的选项顺序固定：填充与对齐、符号、`#`、`0`、宽度、精度、`L`、类型。
    - 宽度按终端列数计算，汉字和多数 emoji 算 2 列；字符串的精度也按列数截断。
    - 不写 `L` 时输出与 locale 无关；浮点数默认输出能精确读回的最短形式。

格式串是 `std::format` 的小语言，分两层。外层语法由 [format.string.general] 统一规定：哪里是替换字段，怎样编号。每个替换字段冒号后面的部分由对应实参类型的 formatter 自己解释。[format.string.std] 规定的是标准库为算术、字符、字符串和指针类型采用的那一种解释，叫做 *std-format-spec*。chrono 类型另有一套（[[time.format]]），范围和 tuple 的格式说明见 [[format.formatter]]。

调用 `std::format("...", args...)` 时，格式串会在编译期被完整检查（[[format.fmt.string]]）。所以什么是合法的格式串，决定了一个错误是编译失败还是运行期异常。

## 外层语法（[format.string.general]）

### 替换字段与转义（¶1–¶3）

```cpp run title="indexing.cpp" ok
#include <cassert>
#include <format>

int main() {
  assert(std::format("{0}-{{", 8) == "8-{");
  assert(std::format("{1} to {0}", "a", "b") == "b to a");
  assert(std::format("{0}{0}{0}", "ha") == "hahaha");  // 手动编号可以重复
  assert(std::format("{}", 1, 2, 3) == "1");           // 多余的实参被忽略
}
```

¶1 格式串由三种成分组成：

- **替换字段**（[[g:replacement-field]]）：`{`、可选的 *arg-id*、可选的 `:` 加 *format-spec*、`}`；
- **转义序列**：`{{` 输出 `{`，`}}` 输出 `}`；
- 其他字符，原样复制到输出。

所以单独的 `{` 或 `}` 都不合法。*arg-id* 是 `0` 或不以 0 开头的正整数，`{01}` 不合法。*format-spec* 的语法由实参类型的 formatter 规定，唯一的限制是不能以 `}` 开头。

¶2 *arg-id* 指出用哪个实参。如果没有这个下标的实参，这个串就不是针对这些实参的格式串。标准用不是格式串这种说法，后果由使用它的地方决定：编译期检查时程序非良构（[[format.fmt.string]]），运行期的 `vformat` 则抛出 `format_error`（[[format.err.report]]）。

### 全自动或全手动编号（¶4）

¶4 如果所有 *arg-id* 都省略，就依次使用 0、1、2……，这叫**自动编号**（[[g:automatic-indexing]]）。这里的所有包括嵌套在 *format-spec* 里的字段，例如动态宽度 `{:{}}`。

!!! std
    If some *arg-id*s are omitted and some are present, the string is not a format string.

实参可以比被引用的多，多余的实参被忽略，不是错误。手动编号可以多次引用同一个实参。

```cpp run title="mixing.cpp" error
#include <format>

int main() {
  auto s2 = std::format("{0} to {}", "a", "b");  // error: 混用
  auto s3 = std::format("{} {}", 1);             // error: 实参不够
  auto s4 = std::format("{:{1}}", 1, 5);         // error: 外层自动、内层手动
  auto s5 = std::format("}");                    // error: 单独的 }
}
```

`s4` 这种混用藏在动态宽度里，容易忽略。`{0:{}}` 同样是混用。要么写 `{:{}}`，要么写 `{0:{1}}`。

运行期的编号状态由 `basic_format_parse_context` 维护：已处于手动模式时调用 `next_arg_id()` 抛出 `format_error`，已处于自动模式时调用 `check_arg_id()` 也抛出（[format.parse.ctx] ¶8–¶13，见 [[format.formatter]]）。

### format-spec 由类型决定（¶5）

¶5 如果 *format-spec* 不符合实参类型的格式说明，这个串就不是格式串。例 3 列出三种解释：算术、指针、字符串类型用 *std-format-spec*；chrono 类型用 *chrono-format-spec*；用户特化的 formatter 由它的 `parse` 成员决定。

所以 `"{:%H}"` 对 `int` 不合法，对 `chrono::seconds` 合法。同一个格式串是否合法取决于实参类型，这就是 `format_string<Args...>` 必须带上实参类型的原因。

## 标准格式说明（[format.string.std]）

### 语法（¶1）

```text
std-format-spec:  fill-and-align(opt) sign(opt) #(opt) 0(opt) width(opt) precision(opt) L(opt) type(opt)
fill-and-align:   fill(opt) align          align: < > ^
sign:             + - 空格
width:            正整数 | { arg-id(opt) }
precision:        . 非负整数 | . { arg-id(opt) }
type:             a A b B c d e E f F g G o p P s x X ?
```

选项的顺序是固定的。`{:+#}` 合法，`{:#+}` 不合法，因为符号必须在 `#` 之前。`{:5+}` 也不合法：`5` 被当作宽度，后面的 `+` 没有位置可放。

每个成分都是可选的，所以 `{:}` 合法，等价于 `{}`。

### 宽度按终端列数计算（¶2、¶9、¶11–¶14）

¶2 宽度的单位是**字段宽度单位**（[[g:field-width]]），即在终端上显示所需的列数，不是字节数，也不是码元数。¶2 还定义了三个量：

- **最小字段宽度**：width 选项的值，没有 width 时为 0（¶9）；
- **估计字段宽度**：格式化结果本身占几列；
- **填充宽度**：0 与（最小字段宽度 − 估计字段宽度）中较大的那个。

¶11 width 写成正整数时就是它的十进制值。width 的语法是正整数，所以 `{:0}` 里的 `0` 只能解析成补零选项，不是宽度为 0。

¶12–¶13 对 UTF-8、UTF-16、UTF-32 序列，实现应当按 UAX #29 把文本分成扩展字素簇，取每个簇第一个码点的宽度相加。宽度为 2 的码点有：East_Asian_Width 为 W 或 F 的码点（汉字、全角字符），易经卦象符号（U+4DC0–U+4DFF），以及两个 emoji 区块（U+1F300–U+1F5FF、U+1F900–U+1F9FF）；其余码点宽度为 1。¶14 其他编码下的宽度未指明。

所以 `std::format("{:>4}", "中")` 输出两个空格加"中"，不是三个空格。

### 填充与对齐（¶3–¶4）

¶3 **填充字符**是 *fill* 选项给出的字符，没有 *fill* 时是空格。*fill* 可以是除 `{`、`}` 之外的任意一个字符，UTF 编码下是一个 Unicode 标量值，可以是 emoji。注 3 说明了解析规则：看 *std-format-spec* 的第二个字符是不是对齐符号，是的话第一个字符就是 fill。所以 `{:5>3}` 中 `5` 是填充字符，`1` 格式化为 `551`。

¶4 表 104 规定了三种对齐：

| 选项 | 含义 | 默认用于 |
|---|---|---|
| `<` | 左对齐，在后面补 n 个填充字符 | 非算术、非指针类型，以及 `charT`、`bool`（未指定整数表示类型时） |
| `>` | 右对齐，在前面补 | 算术类型（`charT`、`bool` 除外）、指针，或指定了整数表示类型时 |
| `^` | 居中，前面补 ⌊n/2⌋，后面补 ⌈n/2⌉ | — |

表中的 n 是填充宽度。注 4 指出，填充字符一律按宽度 1 计算。用宽度为 2 的 emoji 做填充字符会对不齐：标准例子 `format("{:🤡^6}", "x")` 的结果是 `🤡🤡x🤡🤡🤡`，在终端上占 11 列。

### 符号、`#` 与 `0`（¶5–¶8）

```cpp run title="sign-zero.cpp" ok
#include <cassert>
#include <format>
#include <limits>

int main() {
  assert(std::format("{:+06d}", 42) == "+00042");
  assert(std::format("{:#06x}", 0xa) == "0x000a");   // 0 补在前缀之后
  assert(std::format("{:<06}", -42) == "-42   ");    // 有对齐时 0 无效
  double inf = std::numeric_limits<double>::infinity();
  assert(std::format("{:06}", inf) == "   inf");     // inf 不补零
  assert(std::format("{0:},{0:+},{0: }", 1) == "1,+1, 1");
}
```

¶5 符号选项只对算术类型（`charT`、`bool` 除外）有效，或者指定了整数表示类型时有效。`+` 在非负数前加 `+`；`-` 是默认，只给负数加符号；空格在非负数前加一个空格。负数和负零本来就带 `-`。¶6 符号选项对无穷和 NaN 同样适用，`{:+}` 输出 `+inf`、`+nan`。

¶7 `#` 选择**替代形式**。整数在符号之后插入基数前缀，见下文表 107。浮点数的有限值总是输出小数点；对 `g`、`G` 还保留尾随的零。

¶8 `0` 选项对算术类型（`charT`、`bool` 除外）、指针有效，或者指定了整数表示类型时有效。它在符号和基数前缀之后补 `0`，补足填充宽度。同时给了对齐选项时，`0` 不起作用；值是无穷或 NaN 时也不起作用。

### 精度与动态宽度（¶10、¶15–¶16）

```cpp run title="dynamic-width.cpp" ok
#include <cassert>
#include <format>

int main() {
  assert(std::format("{:>{}.{}f}", 3.14159, 10, 2) == "      3.14");  // 全自动编号
  assert(std::format("{0:>{1}}", 7, 4) == "   7");                   // 全手动编号
  assert(std::format("{:.3}", "abcdef") == "abc");                   // 字符串精度：截断
  try {
    (void)std::format("{:{}}", 1, -3);   // 负宽度：运行期才知道
  } catch (const std::format_error&) {
    return 0;
  }
  return 1;
}
```

¶15 精度只对浮点和字符串类型有效。对浮点数，它是表示类型使用的精度。对字符串，它表示保留的最长前缀，前缀的字段宽度不超过精度值。对整数、`bool`、字符、指针给精度是不合法的。

字符串精度按列数截断：`std::format("{:.1}", "中文")` 的结果是空串，因为"中"的宽度是 2，超过了精度 1。

¶10 宽度或精度写成 `{arg-id(opt)}` 时，使用对应实参的值：

!!! std
    The option is valid only if the corresponding formatting argument is of standard signed or unsigned integer type. If its value is negative, an exception of type format_error is thrown.

这里有两个限制，发现的时机不同：

1. 实参必须是标准有符号或无符号整数类型。`bool`、`char`、`double` 都不行。这只取决于类型，在编译期就能检查；libc++ 报 "Replacement argument isn't a standard signed or unsigned integer type"。
2. 值为负时抛出 `format_error`。这取决于运行期的值，只能在运行期发现。

### `L`：locale 相关形式（¶17）

¶17 `L` 选项选择**locale 相关形式**，只对算术类型有效。整数按 locale 的 `numpunct` 插入千位分隔符；浮点数插入千位分隔符和小数点；`bool` 输出 `truename` 或 `falsename`。指定了 `L` 时，对该 formatter 调用 `format` 不是常量子表达式，因为 locale 不能在编译期使用。

不写 `L` 时，输出与 locale 完全无关。这是 `std::format` 和受 `setlocale` 影响的 `printf` 的根本区别。

### 表示类型（¶18–¶25）

```cpp run title="types.cpp" ok
#include <cassert>
#include <format>

int main() {
  assert(std::format("{0:b} {0:d} {0:o} {0:x}", 42) == "101010 42 52 2a");
  assert(std::format("{0:#x} {0:#X}", 42) == "0x2a 0X2A");
  assert(std::format("{:#o}", 0) == "0");          // 0 的八进制没有前缀
  assert(std::format("{:c}", 65) == "A");
  assert(std::format("{:d}", 'A') == "65");
  assert(std::format("{:6}", true) == "true  ");   // bool 默认左对齐
  assert(std::format("{:d}", true) == "1");
  assert(std::format("{}", 0.1) == "0.1");         // 最短往返
  assert(std::format("{:g}", 1234567.0) == "1.23457e+06");
  assert(std::format("{}", 1234567.0) == "1234567");
  assert(std::format("{}", nullptr) == "0x0");
  assert(std::format("{:?}", "a\tb") == "\"a\\tb\"");
}
```

¶20 许多表示类型的含义规定为如同调用 `to_chars`（[[charconv]]），再把结果复制到输出；`charT` 是 `wchar_t` 时先转码。所以 `std::format` 继承了 `to_chars` 的性质：与 locale 无关，浮点数默认输出最短往返形式。

| 实参 | 可用的 type | 默认 |
|---|---|---|
| 字符串（表 106） | `s`；`?` 输出转义形式 | `s` |
| 整数（表 107） | `b B c d o x X` | `d` |
| `charT`（表 108） | `c`；`b B d o x X`（按对应的无符号值）；`?` | `c` |
| `bool`（表 109） | `s`；`b B d o x X`（按 `unsigned char` 值） | `s` |
| 浮点（表 110） | `a A e E f F g G` | 见下 |
| 指针、`nullptr_t`（表 111） | `p P` | `p` |

需要留意的细节：

- 整数的 `c` 把值转换为 `charT` 输出，值超出 `charT` 的范围时在运行期抛出 `format_error`。
- 整数 `o` 的前缀是 `0`，但只在值不为 0 时才有。
- 浮点的 `e`、`f`、`g` 不写精度时，精度默认是 6，与 `printf` 一致。type 和精度都不写时，等价于 `to_chars(first, last, value)`，输出最短往返形式。所以 `1234567.0` 用 `{}` 输出 `1234567`，用 `{:g}` 输出 `1.23457e+06`。
- 小写的表示类型输出 `inf`、`nan`，大写的输出 `INF`、`NAN`。
- 指针输出 `0x` 加上 `reinterpret_cast<uintptr_t>(value)` 的十六进制，`nullptr` 输出 `0x0`。只有 `void*`、`const void*`、`nullptr_t` 有标准 formatter，`int*` 要先转换成 `void*`。
- `?`（C++23）输出转义形式，规则见 [[format.formatter]] 中的 [format.string.escaped]。

!!! impl "libc++ 的 `{}` 浮点输出"
    按当前草案，不带格式的 `to_chars` 在绝对值位于 [1e-4, 1e15)（对 `double`）时使用定点形式，所以 `std::format("{}", 1e5)` 应输出 `100000`。本机 libc++ 输出 `1e+05`，它的 `to_chars` 仍按 C++17 的规则在定点和科学记数法之间取较短者（见 [[charconv]]）。

## 哪些错误在编译期发现

编译期检查相当于在常量求值中把格式串完整解析一遍，并对每个替换字段调用对应 formatter 的 `parse`。所以只依赖格式串和实参类型的错误都在编译期发现：

| 错误 | 何时发现 |
|---|---|
| 不配对的 `{`、`}`，*arg-id* 越界，自动与手动编号混用 | 编译期 |
| *format-spec* 与类型不符（字符串配 `{:d}`、整数配 `{:.2}`、`int` 配 `{:%H}`） | 编译期 |
| 动态宽度或精度的实参不是标准整数类型 | 编译期（[format.parse.ctx] ¶15） |
| 动态宽度或精度为负 | 运行期，抛出 `format_error` |
| 整数用 `{:c}` 输出时超出 `charT` 范围 | 运行期，抛出 `format_error` |
| 用户 formatter 的 `parse` 抛出 `format_error` | 编译期（`parse` 是 `constexpr` 时） |
| 格式串是运行期的值（`vformat`、`dynamic_format`） | 全部推迟到运行期 |

## 思考题

!!! question "思考题 1"
    `std::format("{:>}", 42)` 合法吗？结果是什么？

<details markdown="1">
<summary>答案</summary>

合法，结果是 `"42"`。只有对齐没有宽度时，最小字段宽度为 0（¶9），填充宽度也为 0，对齐不产生任何效果。标准例子 `format("{:*<}", "12")` 的结果 `"12"` 就是这种情况。
</details>

!!! question "思考题 2"
    为什么 `std::format("{:{}}", 1, true)` 在编译期就被拒绝，而 `std::format("{:{}}", 1, -1)` 不会？

<details markdown="1">
<summary>答案</summary>

¶10 要求动态宽度对应的实参是标准有符号或无符号整数类型。`bool` 是整型，但不属于这两类（[[basic.fundamental]]）。这个条件只取决于实参类型，编译期解析时由 `check_dynamic_spec_integral` 检查；[format.parse.ctx] ¶15 规定类型不符时这个调用不是核心常量表达式，于是格式串的 consteval 构造失败。值为负取决于运行期的值，只能在 `format` 执行时抛出 `format_error`。
</details>

## 小结

| 规则 | 出处 |
|---|---|
| `{{`、`}}` 是转义，单独的 `{`、`}` 不合法 | ¶1 |
| 编号要么全自动（包括嵌套字段），要么全手动 | ¶4 |
| *format-spec* 的含义由实参类型的 formatter 决定 | ¶5 |
| 选项顺序固定：填充对齐、符号、`#`、`0`、宽度、精度、`L`、类型 | [format.string.std] ¶1 |
| 宽度按终端列数，宽字符和多数 emoji 计 2 | ¶2、¶13 |
| 有对齐选项时 `0` 无效；无穷和 NaN 不补零 | ¶8 |
| 动态宽度、精度的实参必须是标准整数类型，负值在运行期抛出异常 | ¶10 |
| 字符串精度按列数截断 | ¶15 |
| 不写 `L` 时与 locale 无关；写 `L` 时 `format` 不是常量子表达式 | ¶17 |
| 默认浮点输出等价于 `to_chars(value)`，最短往返 | ¶24 |
