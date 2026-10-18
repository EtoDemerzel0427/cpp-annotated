---
title: 格式串
summary: 格式串的语法——替换字段 {arg-id:format-spec}、{{ }} 转义、自动与手动编号不可混用；标准格式说明 [[fill]align][sign][#][0][width][.precision][L][type] 各选项的精确含义、字段宽度按终端列数估算、嵌套替换字段实现动态宽度/精度，以及哪些错误在编译期被发现
status: draft
covers: *, format.string.general, format.string.std
related: format, format.formatter, charconv, format.fmt.string, time.format, locale.numpunct
tags: 标准库, format, 格式串, Unicode
updated: 2026-10-18
---

格式串是 `std::format` 的“小语言”。它分两层：外层语法由 [format.string.general] 统一规定（哪里是替换字段、如何编号），而每个替换字段冒号后面的 *format-spec* **由对应实参类型的 formatter 自行解释**。[format.string.std] 规定的是标准库为算术、字符、字符串和指针类型采用的那一种解释——*std-format-spec*。chrono 类型用另一套（[[time.format]]），范围和 tuple 也各有一套（[[format.formatter]]、[[format]]）。

“什么是合法的格式串”这个问题之所以重要，是因为答案决定了**编译期**是否报错：`format_string` 的 consteval 构造函数会对格式串做完整检查（[[format.fmt.string]]）。

## 外层语法（[format.string.general]）

### 三种成分（¶1）

格式串由三种东西组成：

- **替换字段**（[[g:replacement-field]]）：`{` *arg-id*(可选) *format-specifier*(可选) `}`，其中 *format-specifier* 是 `:` 加 *format-spec*；
- **转义序列**：`{{` 输出 `{`，`}}` 输出 `}`；
- 其他字符：原样复制。

于是单独的 `{` 或 `}` 都不合法。*format-spec* 的语法写的是“由该实参类型的 formatter 特化规定；不能以 `}` 开头”。

*arg-id* 是 `0` 或不以 0 开头的正整数——`{01}` 不合法。

### 编号：全自动或全手动（¶2、¶4）

¶2：*arg-id* 指出用哪个实参；若 `args` 中没有这个下标，这个串**就不是针对 `args` 的格式串**。注意这个措辞——标准没有说“抛异常”或“非良构”，而是说它“不是格式串”，然后由 [[format.fmt.string]]（编译期）或 [[format.err.report]]（运行期抛 `format_error`）决定后果。

!!! std
    If some *arg-id*s are omitted and some are present, the string is not a format string.

¶4：全部省略时自动使用 0、1、2……（[[g:automatic-indexing]]）；“全部”**包括嵌套在 *format-spec* 里的**（例如动态宽度 `{:{}}`）。混用则不是格式串。实参可以多于被引用的数量——多余的实参被忽略，不是错误；手动编号允许重复引用同一个实参。

```cpp run title="indexing.cpp" ok
#include <cassert>
#include <format>

int main() {
    assert(std::format("{0}-{{", 8) == "8-{");
    assert(std::format("{1} to {0}", "a", "b") == "b to a");
    assert(std::format("{0}{0}{0}", "ha") == "hahaha");   // 手动编号可重复
    assert(std::format("{}", 1, 2, 3) == "1");             // 多余实参被忽略
}
```

```cpp run title="mixing.cpp" error
#include <format>

int main() {
    auto s2 = std::format("{0} to {}", "a", "b");   // error: 混用
    auto s3 = std::format("{} {}", 1);              // error: 实参不够
    auto s4 = std::format("{:{1}}", 1, 5);          // error: 外层自动、内层手动，也算混用
    auto s5 = std::format("}");                     // error: 单独的 }
}
```

运行期，编号状态由 `basic_format_parse_context` 维护：`next_arg_id()` 在已处于手动模式时抛 `format_error`，`check_arg_id()` 在已处于自动模式时抛（[[format.formatter]] 中 [format.parse.ctx] ¶8–¶13）。

### *format-spec* 由类型决定（¶5）

如果 *format-spec* 不符合该实参类型的格式说明，串**不是格式串**。例 3 列了三种解释：算术、指针、字符串类型用 *std-format-spec*；chrono 类型用 *chrono-format-spec*；用户特化由其 `parse` 成员决定。这意味着 `"{:%H}"` 对 `int` 是错的，对 `chrono::seconds` 是对的——**同一个格式串是否合法取决于实参类型**，这正是 `basic_format_string<charT, Args...>` 必须携带 `Args` 的原因。

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

**顺序是固定的**。`{:+#}` 合法，`{:#+}` 不合法——sign 必须在 `#` 之前；`{:5+}` 也不合法——`5` 被当作 width，其后的 `+` 无处安放。但要小心 fill：`{:5>}` 是**合法**的，第二个字符 `>` 是对齐符号，于是 `5` 被解释为填充字符（见下文 ¶3 注 3）。

### 字段宽度：按终端列数（¶2、¶12–¶14）

¶2 定义了几个量：*最小字段宽度*（width 选项的值）、*估计字段宽度*（输出本身占几列）、*填充宽度* = max(0, 最小 − 估计)。

宽度的单位不是字节也不是码元，而是**终端列数**（[[g:field-width]]）。¶13：对 UTF-8/16/32 序列，实现**应当**以每个扩展字素簇（UAX #29）**首码点**的宽度之和作为字段宽度；以下码点宽度为 2：East_Asian_Width 为 W 或 F 的码点（汉字、全角字符）、易经卦象符号、两个 emoji 区块；其余为 1。¶14：非 UTF 编码下宽度未指明。

所以 `std::format("{:>4}", "中")` 输出两个空格加“中”，而不是三个空格。

### 填充与对齐（¶3–¶4）

¶3：*fill* 是除 `{`、`}` 外的任意**一个**字符（UTF 编码下是一个 Unicode 标量值，可以是 emoji）。注 3 点出了解析规则：fill 存在与否看**第二个字符**是不是对齐符号。

¶4 的表 104：

| 选项 | 含义 | 是谁的默认 |
|---|---|---|
| `<` | 左对齐，在后面补 n 个填充字符 | 非算术非指针类型、`charT`、`bool`（未指定整数表示类型时） |
| `>` | 右对齐 | 算术类型（`charT`、`bool` 除外）、指针、或指定了整数表示类型时 |
| `^` | 居中：前补 ⌊n/2⌋，后补 ⌈n/2⌉ | — |

注 4：填充字符**一律按宽度 1 计**。用宽度为 2 的 emoji 做 fill，输出会对不齐——标准例子 `{:🤡^6}` 正是演示这一点。

### 符号（¶5–¶6）

只对算术类型（`charT`、`bool` 除外）或指定了整数表示类型时有效。`+`：非负数前加 `+`（但负零本来就带 `-`）；`-`：默认；空格：非负数前加空格。¶6：对 inf 和 NaN 同样适用（`{:+}` 输出 `+inf`、`+nan`）。

### `#` 替代形式（¶7）

整数：在符号之后插入基数前缀（`0b`、`0`、`0x`，见下文表 107）。浮点：总是输出小数点；对 `g`/`G` 还保留尾随零。

### `0` 补零（¶8）

对算术类型（`charT`/`bool` 除外）、指针、或整数表示类型有效。在符号和前缀**之后**补 `0`；但**若同时给了对齐选项，`0` 不起作用**；对 inf/NaN 也不起作用。

```cpp run title="sign-zero.cpp" ok
#include <cassert>
#include <format>
#include <limits>

int main() {
    assert(std::format("{:+06d}", 42) == "+00042");
    assert(std::format("{:#06x}", 0xa) == "0x000a");     // 0 补在前缀之后
    assert(std::format("{:<06}", -42) == "-42   ");      // 有对齐时 0 无效
    double inf = std::numeric_limits<double>::infinity();
    assert(std::format("{:06}", inf) == "   inf");       // inf 不补零
    assert(std::format("{0:},{0:+},{0: }", 1) == "1,+1, 1");
}
```

### 宽度与精度，以及嵌套替换字段（¶9–¶11、¶15–¶16）

¶9：没有 width 时最小宽度为 0。¶11：width 写成正整数时就是十进制值——注意 width 语法是 *positive-integer*，`{:0}` 中的 `0` 会被解析成“补零”选项而不是宽度。

¶10 是动态宽度/精度的规定：

!!! std
    If `{ arg-id(opt) }` is used in a *width* or *precision* option, the value of the corresponding formatting argument is used as the value of the option. The option is valid only if the corresponding formatting argument is of standard signed or unsigned integer type.

两个关键限制：

1. 该实参必须是**标准**有符号/无符号整数类型——`bool`、`char`、`double` 都不行。这在编译期就能检查（实参类型已知），libc++ 报 "Replacement argument isn't a standard signed or unsigned integer type"。
2. 值为负时抛 `format_error`——这**只能**在运行期发现。

¶15：precision 对浮点表示精度，对字符串表示“**按字段宽度计**最多保留多长的前缀”（不是按字符数）。对整数、`bool`、字符、指针给 precision 不合法。

```cpp run title="dynamic-width.cpp" ok
#include <cassert>
#include <format>

int main() {
    assert(std::format("{:>{}.{}f}", 3.14159, 10, 2) == "      3.14");   // 全自动编号
    assert(std::format("{0:>{1}}", 7, 4) == "   7");                    // 全手动编号
    assert(std::format("{:.3}", "abcdef") == "abc");                    // 字符串精度 = 截断
    try {
        (void)std::format("{:{}}", 1, -3);    // 负宽度：只有运行期才知道
    } catch (const std::format_error&) {
        return 0;
    }
    return 1;
}
```

### `L`：locale 相关形式（¶17）

`L` 只对算术类型有效。整数：按 locale 的 `numpunct` 插入千位分隔符；浮点：分隔符加小数点；`bool`：用 `truename`/`falsename`。¶17 还有一句重要的话：**指定了 `L` 时，对该 formatter 的 `format` 调用不是常量子表达式**——locale 无法在编译期使用。

不写 `L`，输出与 locale 完全无关。这是 `std::format` 与 `printf`（受 `setlocale` 影响）的根本区别。

### `type`：表示类型（¶18–¶25）

¶20 先给出一个总纲：许多表示类型的含义是“as if 调用 `to_chars`”（[[charconv]]），再把输出复制到格式化上下文（`wchar_t` 时先转码）。所以 `std::format` 继承了 `to_chars` 的所有性质：与 locale 无关、浮点默认最短往返。

| 实参 | 可用 type | 默认 |
|---|---|---|
| 字符串（表 106） | `s`；`?` 转义 | `s` |
| 整数（表 107） | `b B c d o x X` | `d` |
| `charT`（表 108） | `c`；`b B d o x X`（按无符号值）；`?` | `c` |
| `bool`（表 109） | `s`；`b B d o x X`（按 `unsigned char` 值） | `s` |
| 浮点（表 110） | `a A e E f F g G` | 见下 |
| 指针、`nullptr_t`（表 111） | `p P` | `p` |

几处细节：

- 整数 `c`：把值转换为 `charT` 输出；超出 `charT` 可表示范围时抛 `format_error`（运行期）。
- 整数 `o` 的前缀是 `0`，但**仅当值非零**时。
- 浮点 `e`/`f`/`g` 不给精度时默认精度 **6**，和 `printf` 一致；而**不写 type 也不写精度**时，等价于 `to_chars(first, last, value)`——最短往返。所以 `{}` 和 `{:g}` 对 `0.1` 都是 `0.1`，但对 `1234567.0` 前者是 `1234567`，后者是 `1.23457e+06`。
- 小写类型输出 `inf`/`nan`，大写输出 `INF`/`NAN`。
- 指针：`0x` 加 `to_chars(reinterpret_cast<uintptr_t>(value), 16)`；`nullptr` 输出 `0x0`。只有 `void*`/`const void*`/`nullptr_t` 有标准 formatter——`int*` 必须先转成 `void*`。
- `?`（C++23）：输出转义形式，规则见 [[format.formatter]] 中的 [format.string.escaped]。

```cpp run title="types.cpp" ok
#include <cassert>
#include <format>

int main() {
    assert(std::format("{0:b} {0:d} {0:o} {0:x}", 42) == "101010 42 52 2a");
    assert(std::format("{0:#x} {0:#X}", 42) == "0x2a 0X2A");
    assert(std::format("{:#o}", 0) == "0");               // 0 的八进制没有前缀
    assert(std::format("{:c}", 65) == "A");
    assert(std::format("{:d}", 'A') == "65");
    assert(std::format("{:6}", true) == "true  ");        // bool 默认左对齐
    assert(std::format("{:d}", true) == "1");
    assert(std::format("{}", 0.1) == "0.1");              // 最短往返
    assert(std::format("{:g}", 1234567.0) == "1.23457e+06");
    assert(std::format("{}", 1234567.0) == "1234567");
    assert(std::format("{}", nullptr) == "0x0");
    assert(std::format("{:?}", "a\tb") == "\"a\\tb\"");
}
```

!!! impl "libc++ 与 `{}` 浮点输出"
    由于 libc++ 的 `to_chars(value)` 仍按 C++17 的“f/e 取较短”规则选择格式（详见 [[charconv]]），libc++ 23 中 `std::format("{}", 1e5)` 输出 `1e+05`，而按当前草案应为 `100000`。

## 哪些错误在编译期被发现

编译期检查等于“在常量求值中把格式串完整解析一遍，并对每个替换字段调用对应 formatter 的 `parse`”。因此能在编译期发现的是**只依赖格式串和实参类型**的错误：

| 错误 | 何时发现 |
|---|---|
| 未配对的 `{`/`}`、`arg-id` 越界、自动/手动混用 | 编译期 |
| *format-spec* 与类型不匹配（`{:d}` 配字符串、`{:.2}` 配整数、`{:%H}` 配 `int`） | 编译期 |
| 动态宽度/精度实参不是标准整数类型 | 编译期（[format.parse.ctx] 的 `check_dynamic_spec`，见 [[format.formatter]]） |
| 动态宽度/精度为负 | 运行期，抛 `format_error` |
| `{:c}` 的整数超出 `charT` 范围 | 运行期，抛 `format_error` |
| 用户 formatter 的 `parse` 抛 `format_error` | 编译期（若 `parse` 是 `constexpr` 的） |
| 格式串本身是运行期值（`vformat`、`dynamic_format`） | 全部推迟到运行期 |

## 常见误区

!!! pitfall "`{:0}` 不是“宽度为 0”"
    width 的语法是 *positive-integer*，`0` 只能被解析为补零标志。`{:05}` 是“补零，宽度 5”，`{:0}` 是“补零，无宽度”。

!!! pitfall "字符串 precision 按列宽截断"
    `std::format("{:.1}", "中文")` 的结果是空串：“中”宽度为 2，超过精度 1，于是连一个字符都不保留。

!!! pitfall "混用编号在动态宽度里很隐蔽"
    `std::format("{:{1}}", x, w)` 和 `std::format("{0:{}}", x, w)` 都是混用，都不合法。要么写 `{:{}}`，要么写 `{0:{1}}`。

## 思考题

!!! question "1"
    `std::format("{:}", 42)` 合法吗？`std::format("{:>}", 42)` 呢？

<details markdown="1">
<summary>展开查看答案与解析</summary>

都合法。*format-specifier* 是 `:` 加 *format-spec*，而 *std-format-spec* 的每个成分都是可选的，所以空的 *format-spec* 合法，`{:}` 等价于 `{}`。`{:>}` 只有对齐没有宽度：最小字段宽度为 0（¶9），填充宽度为 0，对齐不产生效果——标准例子 `format("{:*<}", "12")` 得 `"12"` 就是这种情况。
</details>

!!! question "2"
    `std::format("{:{}}", 1, true)` 为什么在编译期就被拒绝，而 `std::format("{:{}}", 1, -1)` 不会？

<details markdown="1">
<summary>展开查看答案与解析</summary>

¶10 要求动态宽度对应的实参是**标准**有符号/无符号整数类型；`bool` 不是（[[basic.fundamental]] 把 `bool` 单列为整型而非有符号/无符号整数类型）。这一条件只取决于实参类型，在编译期解析时由 `check_dynamic_spec_integral` 检查——[format.parse.ctx] ¶15 规定类型不符时该调用不是核心常量表达式，于是 consteval 构造失败。而“值为负”取决于运行期的值，只能在 `format` 时抛 `format_error`。
</details>

## 小结

| 规则 | 出处 |
|---|---|
| `{{`/`}}` 转义，单独的 `{`/`}` 非法 | ¶1 |
| 自动编号必须全自动（含嵌套），否则不是格式串 | ¶4 |
| *format-spec* 的含义由实参类型的 formatter 决定 | ¶5 |
| 选项顺序固定：fill-align, sign, #, 0, width, .precision, L, type | std ¶1 |
| 宽度按终端列数；宽字符/emoji 计 2 | std ¶2、¶13 |
| 有对齐时 `0` 无效；inf/nan 不补零 | std ¶8 |
| 动态宽度/精度：实参须为标准整数类型，负值运行期抛异常 | std ¶10 |
| 字符串 precision 按列宽截断 | std ¶15 |
| 不写 `L` 则与 locale 无关；`L` 使 format 不是常量子表达式 | std ¶17 |
| 默认浮点输出 = `to_chars(value)`，最短往返 | std ¶24 |
