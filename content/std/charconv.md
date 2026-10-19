---
title: 基础数值转换
summary: <charconv> 的 to_chars 与 from_chars：与 locale 无关、不抛异常、写入调用者缓冲区的数值与文本互转，包括浮点的最短往返保证和 from_chars 的三种结果。
status: done
covers: *, charconv.syn, charconv.to.chars, charconv.from.chars
papers: P0067R5, P2291R3, P2497R0
related: format, format.string, basic.fundamental, bitmask.types, round.style, text
tags: 标准库, charconv, to_chars, from_chars, 浮点
updated: 2026-10-19
---

!!! tldr
    - `to_chars` 和 `from_chars` 永远按 `"C"` locale 工作，不抛异常，不分配内存，结果写进调用者给的缓冲区；`to_chars` 不写结尾的 `'\0'`。
    - 不指定精度时，浮点 `to_chars` 输出能被 `from_chars` 精确读回的最短字符串，例如 `0.1` 输出 `"0.1"`。
    - `from_chars` 不跳过前导空白，不接受 `+` 和 `0x` 前缀，只读开头能匹配的部分；失败或越界时不修改目标变量。
    - 整数版本从 C++23 起是 `constexpr`；C++26 起两个结果类型可以直接放进 `if` 判断成败。

## 为什么需要 `<charconv>`

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

在 `<charconv>` 之前，把 `double` 写成文本再读回来有几种办法，各有缺陷：`printf("%.17g")` 能往返但不短，`0.1` 会变成 `0.10000000000000001`；`printf`、`strtod`、iostream 都受 locale 影响，德语环境下小数点会变成逗号；`to_string` 要分配内存。

`to_chars`/`from_chars`（C++17，[[P0067R5]]）是标准库里最底层的转换设施。它们只认 `"C"` locale，失败通过返回值报告，接口不涉及内存分配。[[format]] 对算术类型的默认输出也是借 `to_chars` 定义的（[[format.string.std#20]]）。

## 结果类型和 `chars_format` [charconv.syn]

两个函数都返回一个简单的结构体：

```cpp
struct to_chars_result {              // from_chars_result 相同，只是 ptr 为 const char*
  char* ptr;
  errc ec;
  friend bool operator==(const to_chars_result&, const to_chars_result&) = default;
  constexpr explicit operator bool() const noexcept { return ec == errc{}; }   // C++26
};
```

¶3 这两个类型只有上面列出的成员，没有基类。所以它们是聚合，可以用结构化绑定 `auto [p, ec] = ...` 拆开。C++26 的 [[P2497R0]] 加上了 `explicit operator bool`，于是可以写 `if (auto r = std::from_chars(...))`。它是 `explicit` 的，`bool ok = r;` 仍然非良构，只能用在[[g:contextually-converted-to-bool|按语境转换为 bool]] 的地方，例如 `if` 的条件。

¶1 概要里的 *integer-type* 表示实现为 `char` 和所有有符号、无符号整数类型各提供一个重载；*floating-point-type* 表示为所有 cv 非限定的浮点类型各提供一个，包括扩展浮点类型（[[basic.fundamental]]）。`bool` 不在其中，概要专门把 `to_chars(char*, char*, bool, int = 10)` 声明为 deleted，防止 `bool` 经整型提升悄悄选中 `int` 的重载。

¶2 `chars_format` 是一个位掩码类型（[[bitmask.types]]），元素为 `scientific`、`fixed`、`hex`；概要还定义了 `general = fixed | scientific`。解析时 `from_chars` 按设置了哪些位决定指数部分是否必须出现（见下文）。

## 数值到文本：`to_chars` [charconv.to.chars]

### 成功与失败（¶1）

¶1 成功时 `ec` 等于值初始化的 `errc`，也就是 `errc{}`（值为 0，不是任何具名枚举值），`ptr` 指向写入内容的尾后。失败只有一种情况：缓冲区不够，此时 `ec == errc::value_too_large`，`ptr == last`，而 `[first, last)` 的内容是未指定的，可能已经写了一半。

`to_chars` 不写结尾的 `'\0'`。`[first, last)` 必须是有效范围，否则是 {{ub}}。

### 整数（¶4–¶6）

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

¶4 前置条件是 `base` 在 2 到 36 之间，违反它是 {{ub}}。

¶5 输出没有多余的前导零；10 到 35 的数字用小写字母 `a` 到 `z` 表示；负数以 `'-'` 开头。输出不带 `+` 号，也不带 `0x`、`0b` 之类的前缀。

整数重载从 C++23 起是 `constexpr` 的（[[P2291R3]]），所以上例可以在 `static_assert` 里使用。

### 浮点的最短往返（¶2）

!!! std
    The functions that take a floating-point value but not a precision parameter ensure that the string representation consists of the smallest number of characters such that there is at least one digit before the radix point (if present) and parsing the representation using the corresponding `from_chars` function recovers `value` exactly.

¶2 不带精度参数的浮点 `to_chars` 有三层保证：

1. 往返：用对应的 `from_chars` 读回，得到的值与原值完全相等。注 1 提醒，这只在同一个实现的 `to_chars` 和 `from_chars` 之间保证。
2. 最短：在所有能往返的写法中取字符最少的。小数点前至少要有一位数字，所以 `.5` 不算候选。
3. 平局：同样短的候选有多个时，取与原值相差最小的；还相同，就按 `round_to_nearest`（[[round.style]]）舍入。

这里的最短是在选定的格式之内比较的，格式由下一节的规则或 `fmt` 实参决定。主流实现用 Ryu 一类的算法实现这个保证。

### 浮点格式的选择（¶3、¶7、¶10、¶13）

¶3 带 `chars_format` 参数的重载按 `fmt` 选择 `printf` 的转换说明符：`fixed` 对应 `%f`，`scientific` 对应 `%e`，`hex` 对应 `%a`（但结果不带 `0x` 前缀），`general` 对应 `%g`。所有转换都按 `"C"` locale 的 `printf` 风格进行，小数点永远是 `.`。

| 重载 | 格式 | 精度 |
|---|---|---|
| `to_chars(f, l, v)`（¶7） | 按数量级在 `%f` 与 `%e` 之间选 | 最短往返 |
| `to_chars(f, l, v, fmt)`（¶10） | 按 `fmt` | 最短往返（在该格式内） |
| `to_chars(f, l, v, fmt, precision)`（¶13） | 按 `fmt` | 按给定精度，与 `printf` 相同 |

¶7 不带 `fmt` 的重载按数量级选择：`|value|` 落在 `[l, u)` 内用 `%f`，否则用 `%e`。`l` 是不小于 10⁻⁴ 的最小可表示值；`u` 是不大于 `radix^(digits+1)` 的最大值再向下取到 10 的幂。对 `double`，`digits` 是 53，2⁵⁴ 约为 1.8×10¹⁶，所以区间大约是 `[1e-4, 1e16)`。

!!! impl "libc++ 仍按 C++17 的规则选择格式"
    C++17 原来的措辞是在 `%f` 和 `%e` 中选更短的那个，一样长时选 `%f`。草案后来改成了上面的数量级规则，但本机 Clang 23 + libc++ 仍按旧规则输出：

    | 值 | ¶7 规定 | libc++ 输出 |
    |---|---|---|
    | `1e4` | `10000` | `10000` |
    | `1e5` | `100000` | `1e+05` |
    | `1e15` | `1000000000000000` | `1e+15` |
    | `1e-4` | `0.0001` | `1e-04` |

    这也影响 `std::format("{}", 1e5)`：[[format.string.std#24]] 规定不带类型和精度的浮点输出等价于 `to_chars(first, last, value)`，所以 libc++ 输出 `1e+05`。需要稳定的格式时，显式写 `chars_format::fixed` 或 `{:f}`。

## 文本到数值：`from_chars` [charconv.from.chars]

### 三种结果（¶1）

¶1 `from_chars` 在 `[first, last)` 的开头匹配一个模式，结果分三种：

| 情形 | `value` | `ptr` | `ec` |
|---|---|---|---|
| 没有字符匹配 | 不修改 | `first` | `errc::invalid_argument` |
| 匹配成功，但值超出类型范围 | 不修改 | 第一个不匹配的字符（或 `last`） | `errc::result_out_of_range` |
| 匹配成功，值可以表示 | 设为解析结果（按 `round_to_nearest` 舍入） | 第一个不匹配的字符（或 `last`） | `errc{}` |

与 `strtol` 相比有几处不同。`from_chars` 不跳过前导空白，`" 42"` 直接得到 `invalid_argument`。它只读开头能匹配的部分，`"42abc"` 成功读出 42，`ptr` 指向 `'a'`，要求整个字符串都是数字时必须自己检查 `ptr == last`。失败时 `value` 保持原值，而 `strtol` 会返回 0 或 `LONG_MAX`。

注 1 补充：模式允许可选符号、但符号后面没有数字时（如 `"-"`），视为没有字符匹配。

### 整数的模式（¶3）

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

¶3 整数的模式是 `strtol` 在 `"C"` locale 下针对给定基数接受的形式，但收紧了三处：

1. 基数为 2 时不允许 `0b`/`0B` 前缀，基数为 16 时不允许 `0x`/`0X` 前缀；
2. 唯一允许的符号是 `'-'`，不接受 `'+'`；
3. 只有 `value` 是有符号类型时才允许 `'-'`。对 `unsigned` 解析 `"-1"` 得到 `invalid_argument`，不会像 `strtoul` 那样回绕成最大值。

### 浮点的模式（¶6）

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

¶6 浮点的模式是 `strtod` 接受的形式，但有四处修改：

- ¶6.1 `'+'` 只能出现在指数部分；
- ¶6.2 `fmt` 设置了 `scientific` 而没有 `fixed` 时，指数部分必须出现；
- ¶6.3 `fmt` 设置了 `fixed` 而没有 `scientific` 时，不能有指数部分，遇到 `e` 就停止；
- ¶6.4 `fmt` 为 `hex` 时，假定已经有 `0x` 前缀。所以字符串里真的写了 `0x`，反而只解析出 `0`，剩下 `x123`（标准例 1）。

`inf`、`nan` 仍按 `strtod` 的规则接受。¶6 最后一句说，结果是与字符串所表示的值最接近的至多两个浮点值之一；配合 ¶1 的 `round_to_nearest`，就是 IEEE 意义下的正确舍入。

!!! impl "libc++ 的支持情况"
    - 浮点 `from_chars` 只实现了 `float` 和 `double`。`long double` 的重载被声明为 deleted，调用会报 `call to deleted function 'from_chars'`。
    - 因为浮点支持不完整，libc++ 没有定义 `__cpp_lib_to_chars`；`__cpp_lib_constexpr_charconv` 已定义为 `202207L`。
    - 浮点 `to_chars` 和 `from_chars` 实现在动态库里，受可用性宏控制，较老的 macOS 部署目标上不可用。

## 历史

!!! history
    - C++17：[[P0067R5]] 引入 `<charconv>`，当时位于 [utilities]。
    - C++23：[[P2291R3]] 使整数的 `to_chars`/`from_chars` 成为 `constexpr`。之后草案重组，本节移入第 28 章 [text]。
    - C++26：[[P2497R0]] 给两个结果类型加上 `explicit operator bool`。草案中整数版本标为 freestanding，浮点版本标为 freestanding-deleted，即独立实现可以把它们定义为 deleted。

## 常见误解

!!! pitfall "把 `to_chars` 的输出当作 C 字符串"
    `to_chars` 不写 `'\0'`。要用 `printf("%s", buf)` 打印，必须先执行 `*r.ptr = '\0'`，并且给缓冲区多留一个字节。

!!! pitfall "只检查 `ec`，不检查 `ptr`"
    `from_chars` 解析 `"12abc"` 是成功的。语义上要求整个字符串都是数字时，还要判断 `r.ptr == last`。

!!! pitfall "以为往返保证跨平台成立"
    ¶2 的注 1 说明，往返只在同一个实现的 `to_chars` 与 `from_chars` 之间保证。不同实现输出的最短串可以不同，¶7 的格式选择上 libc++ 就与草案不一致。序列化协议需要跨平台逐字节一致时，应显式指定 `fmt`，最好也指定精度。

## 思考题

!!! question "思考题 1"
    `std::to_chars(buf, end, -0.0)` 输出什么？`std::format("{:+}", -0.0)` 呢？

<details markdown="1">
<summary>答案</summary>

`to_chars` 按 `printf` 风格转换，负零的符号会保留，输出 `"-0"`。

[[format.string.std#5]] 的表 105 规定，`+` 选项只在非负且不是负零的数前面插入 `+`；负数和负零的 `to_chars` 输出已经带符号，不再处理。所以结果是 `"-0"`，不是 `"+-0"`。本机 libc++ 的输出与此一致。
</details>

!!! question "思考题 2"
    为什么 `from_chars` 越界时让 `value` 保持不变、`ptr` 照样前进，而不像 `strtol` 那样写入 `LONG_MAX`？

<details markdown="1">
<summary>答案</summary>

¶1 让调用者能区分三件事：有没有数字（`ptr == first`），数字在哪里结束（`ptr`），值能否表示（`ec`）。`ptr` 前进，解析器就能跳过这个过长的数字继续往后扫描。`value` 不变，就避免了 `strtol` 的歧义：`LONG_MAX` 既可能是错误标记，也可能是合法输入。
</details>

## 小结

| 方面 | 规则 |
|---|---|
| locale | 永远按 `"C"` locale |
| 异常 | 都不抛异常，错误通过 `errc` 报告 |
| `to_chars` 失败 | `value_too_large`，`ptr == last`，缓冲区内容未指定 |
| 浮点、无精度 | 最短往返；平局取最接近者，再按 round-to-nearest |
| 浮点、无 `fmt` | ¶7：`[1e-4, u)` 用 `%f`，否则 `%e`（libc++ 仍按取较短的旧规则） |
| `from_chars` 无匹配 | `invalid_argument`，`ptr == first`，`value` 不变 |
| `from_chars` 越界 | `result_out_of_range`，`ptr` 越过匹配部分，`value` 不变 |
| 整数模式 | 无前导空白、无 `+`、无 `0x`/`0b`，无符号类型不接受 `-` |
| `hex` 浮点 | 读写都不带 `0x` |
| C++23 / C++26 | 整数版本 `constexpr`；结果类型有 `explicit operator bool` |
