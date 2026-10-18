---
title: 基础数值转换
summary: <charconv> 的 to_chars/from_chars——与 locale 无关、不抛异常、写入调用者给定缓冲区的数值⇄文本转换；浮点 to_chars 的“最短往返”保证、chars_format 的含义、from_chars 的 ptr/ec 语义，以及 C++23 constexpr 整数重载与 C++26 的 explicit operator bool
status: draft
covers: *, charconv.syn, charconv.to.chars, charconv.from.chars
papers: P0067R5, P2291R3, P2497R0
related: format, format.string, basic.fundamental, bitmask.types, round.style, library
tags: 标准库, charconv, to_chars, from_chars, 浮点
updated: 2026-10-18
---

`<charconv>` 是标准库里**最底层**的数值⇄文本转换设施。它刻意比 `printf`/`strtod`/`iostream`/`to_string` 都“笨”：

- 只认 `"C"` locale，不看全局 locale，不读 `errno`；
- 结果写进**调用者提供**的 `[first, last)`，接口上不需要分配内存；
- 所有函数都写着 *Throws*: Nothing，失败通过返回值里的 `errc` 报告；
- 整数版本全部是 freestanding 的，C++23 起还是 `constexpr` 的。

它的价值在于：这是标准里**唯一**给出浮点“最短往返”（shortest round-trip）保证的接口，[[format]] 对算术类型的默认输出就是“as if 调用 `to_chars`”定义的（见 [[format.string.std#20]]）。本节当前位于 [text] 第 28 章（旧标准中在 [utilities] 的 [utility.to.chars]/[utility.from.chars]）。

| 子条款 | 内容 |
|---|---|
| [charconv.syn] | 概要：`chars_format`、`to_chars_result`/`from_chars_result`、各重载 |
| [charconv.to.chars] | `to_chars`：数值 → 文本 |
| [charconv.from.chars] | `from_chars`：文本 → 数值 |

## 概要：占位类型、`chars_format` 与结果类型（[charconv.syn]）

¶1 规定概要里的两个占位名：*integer-type* 意味着为 `char` 以及**所有**有符号/无符号整数类型各提供一个重载；*floating-point-type* 意味着为所有 cv 非限定浮点类型（包括扩展浮点类型，见 [[basic.fundamental]]）各提供一个重载。注意 `bool` 不是 *integer-type* 的成员——概要里专门有一个 `to_chars(char*, char*, bool, int = 10) = delete;`，防止 `bool` 经整型提升悄悄选中 `int` 重载。

¶2：`chars_format` 是**位掩码类型**（[[bitmask.types]]），元素为 `scientific`、`fixed`、`hex`，而 `general` 被定义为 `fixed | scientific`。这个定义在 `from_chars` 里有实际意义：解析时按“设置了哪些位”来决定指数部分是否必需/允许（见下文 ¶6）。

¶3 规定 `to_chars_result`/`from_chars_result` **只有**概要里写出的成员：`ptr`、`ec`、默认化的 `operator==`，以及 {{c++26}} 新增的

```cpp
constexpr explicit operator bool() const noexcept { return ec == errc{}; }
```

“没有别的成员、没有基类”这一句不是废话：它保证这两个类型是聚合，可以用结构化绑定 `auto [p, ec] = ...` 解构（[[dcl.struct.bind]]），也禁止实现偷偷塞进额外状态。`explicit operator bool` 由 [[P2497R0]] 引入，让 `if (auto r = std::from_chars(...))` 成为惯用法；因为是 `explicit` 的，`bool ok = r;` 仍然非良构，只能在**按语境转换为 bool**（[[g:contextually-converted-to-bool]]）的地方使用。

## `to_chars`：数值 → 文本（[charconv.to.chars]）

### 公共约定（¶1）

!!! std
    If the member `ec` of the return value is such that the value is equal to the value of a value-initialized `errc`, the conversion was successful and the member `ptr` is the one-past-the-end pointer of the characters written.

成功时 `ec == errc{}`（值为 0，**不是**任何具名枚举值），`ptr` 指向写入内容的尾后。失败只有一种：`ec == errc::value_too_large`，`ptr == last`，**且 `[first, last)` 的内容未指明**——缓冲区可能已被写了一半。`to_chars` **不写终止 `'\0'`**，需要的话自己补。

`[first, last)` "is required to be a valid range" 是前置条件，违反即 {{ub}}。

### 浮点的最短往返保证（¶2）

这是整节最有分量的一段：

!!! std
    The functions that take a floating-point value but not a precision parameter ensure that the string representation consists of the smallest number of characters such that there is at least one digit before the radix point (if present) and parsing the representation using the corresponding `from_chars` function recovers `value` exactly.

拆开看有三层：

1. **往返**：同一实现上，用对应的 `from_chars` 读回，得到的值与原值**按位相等**（注 1 特别提醒：跨实现不保证）。
2. **最短**：在所有满足 1 的写法中，取**字符数最少**的。`0.1` 输出 `"0.1"` 而不是 `printf("%.17g")` 的 `0.10000000000000001`。
3. **决胜规则**：若有多个同样短的候选，取**与实参值差最小**的；还平手，则按 `round_to_nearest`（[[round.style]]）决定。

“至少一位小数点前数字”这个限制排除了 `.5` 这种更短的写法。注意这里的“最短”是在**选定的格式**（下文的 f/e 选择或 `fmt` 指定）之内比较的。

这个保证之所以重要：在此之前，想要“既短又能精确往返”只能用 `%.17g`（不短）或者自己实现 Grisu/Ryu 之类的算法。主流实现（libc++、MSVC STL）都基于 Ryu 系列算法实现。

```cpp run title="roundtrip.cpp" ok
#include <cassert>
#include <charconv>
#include <string_view>

int main() {
    char buf[64];
    for (double v : {0.1, 1.0 / 3, 1e23, 5e-324}) {
        auto [end, ec] = std::to_chars(buf, buf + sizeof buf, v);
        assert(ec == std::errc{});
        double back = 0;
        auto r = std::from_chars(buf, end, back);
        assert(r && r.ptr == end && back == v);   // 同一实现上精确往返
    }
    auto r = std::to_chars(buf, buf + sizeof buf, 0.1);
    assert(std::string_view(buf, r.ptr) == "0.1");  // 最短：不是 0.10000000000000001
}
```

### 三种格式选择（¶3、¶7、¶10、¶13）

¶3 给出 `chars_format` 到 `printf` 转换说明符的映射：`fixed` → `%f`，`scientific` → `%e`，`hex` → `%a`（**但结果不带 `0x` 前缀**），`general` → `%g`。所有转换都"in the style of `printf` in the "C" locale"——小数点永远是 `.`，不受 `std::locale::global` 影响。

| 重载 | 格式 | 精度 |
|---|---|---|
| `to_chars(f, l, v)`（¶7） | 由数值大小在 `f` 与 `e` 之间选择 | 最短往返 |
| `to_chars(f, l, v, fmt)`（¶10） | 按 `fmt` | 最短往返（在该格式内） |
| `to_chars(f, l, v, fmt, precision)`（¶13） | 按 `fmt` | 按给定精度，和 `printf` 一样 |

¶7 对不带 `fmt` 的版本给出了一个**按数量级**的规则：设 `T` 为浮点类型，若 `|value|` 落在 `[l, u)` 内则用 `f`，否则用 `e`。其中 `l` 是不小于 10⁻⁴ 的最小可表示值，`u` 是不大于 `radix^(digits+1)` 并向下取整到 10 的幂的值。对 `double`（`digits == 53`），2⁵⁴ ≈ 1.8×10¹⁶，于是 `u = 1e16`：区间大致是 `[1e-4, 1e16)`。

!!! impl "libc++ 23 的实际行为与 ¶7 不一致"
    C++17 原始措辞对这个重载的规定是“在 `f` 与 `e` 中选**更短**的那个，平手取 `f`”。草案后来改成了上面的数量级区间规则，但截至本文编写时 libc++（以及与之同源的 MSVC STL 实现）仍然按旧规则输出。本机 clang 23 + libc++ 实测：

    | 值 | ¶7 规定 | libc++ 23 输出 |
    |---|---|---|
    | `1e4` | `10000` | `10000` |
    | `1e5` | `100000` | `1e+05`（更短） |
    | `1e15` | `1000000000000000` | `1e+15` |
    | `1e-4` | `0.0001` | `1e-04` |

    这也直接影响 `std::format("{}", 1e5)`——[[format.string.std#24]] 规定无类型、无精度的浮点等价于 `to_chars(first, last, value)`，所以 libc++ 输出 `1e+05`。需要稳定格式时请显式写 `chars_format::fixed` 或 `{:f}`。另外，libc++ 的浮点 `to_chars` 实现在动态库里而不是头文件里（头文件 `__charconv/to_chars_floating_point.h` 只有声明），并受可用性宏 `_LIBCPP_AVAILABILITY_HAS_TO_CHARS_FLOATING_POINT` 控制，在较老的 macOS 部署目标上不可用。

### 整数版本（¶4–¶6）

- ¶4 *Preconditions*：`base` 在 2 到 36 之间。违反是 {{ub}}（这不是硬化前置条件）。
- ¶5：输出没有多余前导零；10–35 用**小写** `a`–`z`；负数以 `'-'` 开头。**没有** `+` 号，**没有** `0x`/`0b` 前缀。
- 自 C++23 起整数重载是 `constexpr` 的（[[P2291R3]]），也是 freestanding 的。

```cpp run title="to-chars-int.cpp" ok
#include <cassert>
#include <charconv>
#include <string_view>

constexpr std::string_view hex(unsigned v, char (&buf)[16]) {
    auto r = std::to_chars(buf, buf + 16, v, 16);
    return {buf, r.ptr};
}

int main() {
    char buf[16];
    assert(hex(255, buf) == "ff");                       // 小写，无前缀
    auto r = std::to_chars(buf, buf + 3, 12345);         // 缓冲区不够
    assert(r.ec == std::errc::value_too_large && r.ptr == buf + 3);
    static_assert([] { char b[16]; return hex(48879, b) == "beef"; }());   // C++23 起可在常量求值中使用
}
```

## `from_chars`：文本 → 数值（[charconv.from.chars]）

### 结果三分法（¶1）

`from_chars` 在 `[first, last)` 开头**匹配一个模式**，结果分三种情况：

| 情形 | `value` | `ptr` | `ec` |
|---|---|---|---|
| 没有任何字符匹配 | **不修改** | `first` | `errc::invalid_argument` |
| 匹配成功但值超出类型范围 | **不修改** | 第一个不匹配字符（或 `last`） | `errc::result_out_of_range` |
| 匹配成功且值可表示 | 设为解析值（按 `round_to_nearest` 舍入） | 第一个不匹配字符（或 `last`） | `errc{}` |

要点：

- **不跳过前导空白**——这和 `strtol` 不同。`" 42"` 直接 `invalid_argument`。
- **只读前缀**：`"42abc"` 成功读出 42，`ptr` 指向 `'a'`。要求“整串都是数字”时必须自己检查 `ptr == last`。
- 失败时 `value` 保持原值，这一点 `strtol` 做不到（它返回 0 或 `LONG_MAX`）。
- 注 1：如果模式允许可选符号，但符号后面没有数字（如 `"-"`），视为**没有字符匹配**。

### 整数模式（¶3）

模式是 `strtol` 在 `"C"` locale 下针对给定基数的主题序列，但有三处收紧：

1. 基数为 2 时不允许 `0b`/`0B` 前缀，基数为 16 时不允许 `0x`/`0X` 前缀；
2. 唯一允许的符号是 `'-'`，**不接受 `'+'`**；
3. 而且 `'-'` 只在 `value` 为有符号类型时允许——对 `unsigned` 解析 `"-1"` 是 `invalid_argument`，而不是像 `strtoul` 那样回绕成最大值。

```cpp run title="from-chars-int.cpp" ok
#include <cassert>
#include <charconv>
#include <string_view>

int main() {
    auto parse = [](std::string_view s, auto& v, int base = 10) {
        return std::from_chars(s.data(), s.data() + s.size(), v, base);
    };
    int v = 7;
    auto r1 = parse("+12", v);
    assert(r1.ec == std::errc::invalid_argument && v == 7);    // '+' 不被接受，v 不变

    auto r2 = parse("99999999999 tail", v);
    assert(r2.ec == std::errc::result_out_of_range && v == 7); // 越界：v 不变
    assert(*r2.ptr == ' ');                                    // 但 ptr 仍越过了全部数字

    auto r3 = parse("0x1f", v, 16);
    assert(r3 && v == 0 && *r3.ptr == 'x');                   // 不认 0x：只读到 "0"

    unsigned u = 5;
    auto r4 = parse("-1", u);
    assert(r4.ec == std::errc::invalid_argument && u == 5);    // 无符号类型不接受 '-'
}
```

### 浮点模式（¶6）

模式是 `strtod` 的主题序列，但：

- ¶6.1：`'+'` 只能出现在指数部分；
- ¶6.2：`fmt` 含 `scientific` 但不含 `fixed` 时，指数部分**必须**出现；
- ¶6.3：`fmt` 含 `fixed` 但不含 `scientific` 时，指数部分**不得**出现（遇到 `e` 就停）；
- ¶6.4：`fmt` 为 `hex` 时，**假定**已有 `0x` 前缀——于是字符串里真的写了 `0x` 反而解析成 `0`，剩下 `x123`（标准例 1）。

`inf`、`nan` 等仍按 `strtod` 的规则接受。¶6 的最后一句说结果是“最接近字符串所表示值的至多两个浮点值之一”，配合 ¶1 的 `round_to_nearest`，就是 IEEE 意义下的正确舍入。

```cpp run title="from-chars-fp.cpp" ok
#include <cassert>
#include <charconv>
#include <string_view>

int main() {
    double d = -1;
    auto parse = [&](std::string_view s, std::chars_format f = std::chars_format::general) {
        return std::from_chars(s.data(), s.data() + s.size(), d, f);
    };
    assert(parse("0x123", std::chars_format::hex) && d == 0);   // 只读了 "0"
    assert(parse("1ff", std::chars_format::hex) && d == 511);   // 不写 0x 才对
    auto r = parse("1e5", std::chars_format::fixed);
    assert(r && d == 1 && *r.ptr == 'e');                       // fixed：不吃指数
    assert(parse("15", std::chars_format::scientific).ec == std::errc::invalid_argument);
    assert(parse("1e999").ec == std::errc::result_out_of_range);
}
```

!!! impl "libc++ 的支持情况"
    - 浮点 `from_chars` 只提供 `float` 与 `double`（`__charconv/from_chars_floating_point.h`）；`long double` 重载在 libc++ 23 中被声明为 deleted，调用会报 "call to deleted function"。
    - `<version>` 中 `__cpp_lib_to_chars` 在 libc++ 23 里**没有定义**（被注释掉），正是因为浮点支持不完整；`__cpp_lib_constexpr_charconv` 已定义为 `202207L`。
    - C++26 的 `explicit operator bool` 已实现（`__charconv/to_chars_result.h`、`from_chars_result.h`）。

## 常见误区

!!! pitfall "把 `to_chars` 的输出当 C 字符串"
    `to_chars` 不写 `'\0'`。`printf("%s", buf)` 之前必须 `*r.ptr = '\0'`，并确保缓冲区留出这一字节。

!!! pitfall "检查 `ec` 却忘了检查 `ptr`"
    `from_chars("12abc")` 是**成功**的。如果语义上要求整串都是数字，必须再判断 `r.ptr == last`。

!!! pitfall "以为“往返”跨平台成立"
    ¶2 注 1 明说：往返只在**同一实现**的 `to_chars`/`from_chars` 之间保证。不同实现输出的最短串理论上可以不同（尤其是 ¶7 的 f/e 选择，上文已经看到 libc++ 就与草案不同）。序列化协议若需要跨平台逐字节一致，应显式指定 `fmt`，最好再指定精度。

## 历史

- C++17：[[P0067R5]] 引入 `<charconv>`，当时位于 [utilities]。
- C++20 期间：浮点 `to_chars` 由主流实现陆续落地（MSVC 最早，libc++ 借用了其 Ryu 实现）。
- C++23：[[P2291R3]] 使整数 `to_chars`/`from_chars` 成为 `constexpr`。后来草案重组，本节移入 [text] 第 28 章。
- C++26：[[P2497R0]] 为两个结果类型加上 `explicit operator bool`。当前草案中整数版本标为 freestanding，浮点版本标为 freestanding-deleted（独立实现可以把它们定义为 deleted）。

## 思考题

!!! question "1"
    `std::to_chars(buf, end, -0.0)` 输出什么？`std::format("{:+}", -0.0)` 又输出什么？

<details markdown="1">
<summary>展开查看答案与解析</summary>

`to_chars` 按 `printf` 风格转换，`-0.0` 输出 `"-0"`（负零的符号被保留）。[[format.string.std#5]] 的表 105 专门说明：`+` 选项只在**非负且非负零**的数前插入 `+`，负数与负零的 `to_chars` 输出已含符号，不再处理——所以结果是 `"-0"`，不是 `"+-0"`。
</details>

!!! question "2"
    为什么 `from_chars` 在越界时选择“`value` 不变、`ptr` 照样前进”，而不是像 `strtol` 那样写入 `LONG_MAX`？

<details markdown="1">
<summary>展开查看答案与解析</summary>

¶1 的设计让调用者可以区分三件事：有没有数字（`ptr == first`）、数字在哪里结束（`ptr`）、值能否表示（`ec`）。`ptr` 前进让解析器能跳过这个超长数字继续往后扫描；`value` 不变则避免了 `strtol` 那种“返回值既是合法值又是错误标记”的歧义——`LONG_MAX` 本身就可能是合法输入。
</details>

## 小结

| 方面 | 规则 |
|---|---|
| locale | 永远按 `"C"` locale |
| 异常 | *Throws*: Nothing；错误走 `errc` |
| `to_chars` 失败 | `value_too_large`，`ptr == last`，缓冲区内容未指明 |
| 浮点无精度 | 最短往返；平手取最接近者，再按 round-to-nearest |
| 浮点无 `fmt` | ¶7：`[1e-4, u)` 用 `f`，否则 `e`（libc++ 仍用“取较短”旧规则） |
| `from_chars` 无匹配 | `invalid_argument`，`ptr == first`，`value` 不变 |
| `from_chars` 越界 | `result_out_of_range`，`ptr` 越过匹配部分，`value` 不变 |
| 整数模式 | 无前导空白、无 `+`、无 `0x`/`0b`，无符号类型不接受 `-` |
| `hex` 浮点 | 读写都不带 `0x` |
| C++23 / C++26 | 整数版本 `constexpr`；结果类型 `explicit operator bool` |
