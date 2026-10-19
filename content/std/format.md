---
title: 格式化库
summary: std::format 家族的整体结构：编译期检查格式串的 basic_format_string、format/vformat/format_to/format_to_n/formatted_size 的语义、类型擦除的实参 basic_format_arg 与 basic_format_args、错误报告，以及 pair/tuple 的 formatter。
status: done
covers: format.syn, format.err.report, format.fmt.string, format.functions, format.arguments, format.arg, format.arg.store, format.args, format.tuple, format.error
papers: P0645R10, P2216R3, P2418R2, P2508R1, P2286R8, P2637R3, P2905R2, P2918R2
related: format.string, format.formatter, charconv, print.fun, expr.const.imm, dcl.constexpr, expr.const.core, text
tags: 标准库, format, 格式化, consteval, 类型擦除
updated: 2026-10-19
---

!!! tldr
    - `std::format("{} {}", a, b)` 的格式串在编译期检查：格式串与实参类型不匹配时程序非良构，编译器必须报错。
    - 格式串只在运行时才知道时，用 C++26 的 `std::dynamic_format(s)` 或 `std::vformat`，错误改为抛出 `format_error`。
    - `format` 是一层模板外壳，真正干活的是对所有实参类型共用的 `vformat`；实参先被归一化成 14 种类型之一，用户类型通过 `handle` 擦除类型。
    - 不写 `L` 选项时，格式化与 locale 无关。
    - `format_to_n` 只写前 `n` 个字符，但返回的 `size` 是完整输出的长度，可以据此判断是否被截断。

## 两层结构

`<format>`（C++20，[[P0645R10]]）要同时避开 `printf` 和 iostream 的缺点。`printf` 简洁、快，但类型不安全，`%d` 配 `long` 是 {{ub}}，也不能扩展到用户类型。iostream 类型安全、可扩展，但写起来啰嗦，`std::hex` 这类状态会留在流上，格式片段也被拆散在多个 `<<` 之间，难以翻译。

`std::format` 采用 Python 风格的格式串，每个类型通过特化 `formatter<T>` 定义自己的输出方式，并分成两层：

```text
format(fmt, args...)            ← 模板外壳：编译期检查 fmt，把 args 打包
   └─ vformat(fmt.get(), make_format_args(args...))
         └─ 非模板的运行期解释器（每种 Context 只有一份）：
              逐个处理替换字段 → basic_format_arg::visit → formatter<T>::parse/format
```

外壳负责类型安全和编译期诊断；内核对所有实参类型共用一份代码，避免为每组实参类型都实例化一整套格式化逻辑。

格式串的语法见 [[format.string]]，formatter 的写法和范围格式化见 [[format.formatter]]。`std::print`、`std::println` 在第 31 章的 [[print.fun]]，使用同一套格式串和 formatter，区别在于输出目的地和编码处理。

## 编译期检查格式串 [format.fmt.string]

```cpp run title="compile-time-check.cpp" error
#include <format>

int main() {
    auto a = std::format("{} {}", 1);        // error: 实参不够
    auto b = std::format("{:d}", "str");     // error: 字符串不接受 d
    auto c = std::format("{0} {}", 1, 2);    // error: 自动与手动编号混用
}
```

这三行都在编译时被拒绝。`format` 的第一个形参类型是 `format_string<Args...>`，也就是：

```cpp
template<class charT, class... Args>
struct basic_format_string {
  template<class T> consteval basic_format_string(const T& s);
  constexpr basic_format_string(dynamic-format-string<charT> s) noexcept;
  constexpr basic_string_view<charT> get() const noexcept;
};
```

¶1 构造函数模板要求 `const T&` 能转换为 `basic_string_view<charT>`；¶2 它用 `s` 初始化内部的 `str`。关键在 ¶3：

!!! std
    A call to this function is not a core constant expression ([expr.const.core]) unless there exist args of types `Args` such that *str* is a format string for args.

这句话和核心语言的规则合起来，就得到编译期检查：

1. 构造函数是 `consteval` 的，即[[g:immediate-function|立即函数]]（[[dcl.constexpr]]）。
2. 在立即函数语境之外调用立即函数，是一次[[g:immediate-invocation|立即调用]]。按 [[expr.const.imm]]，立即调用必须是常量表达式，否则程序非良构。
3. ¶3 规定，格式串对 `Args` 不合法时，这次调用不是核心常量表达式。
4. 所以 `std::format("{:d}", "str")` 是标准要求诊断的编译错误，而不仅仅是编译器的额外检查。

libc++ 的构造函数在常量求值中把整个格式串解析一遍，并对每个实参调用其 formatter 的 `parse`；发现错误就调用一个非 `constexpr` 的函数，使求值不再是常量表达式。所以 Clang 的诊断是 `call to consteval function ... is not a constant expression`，后面的 note 里有 `non-constexpr function '__throw_format_error' cannot be used in a constant expression`。

由此也可以推出：自定义 formatter 的 `parse` 必须是 `constexpr` 的，否则任何格式化该类型的 `std::format` 调用都无法成为常量表达式，直接编译失败（见 [[format.formatter]]）。

`format_string<Args...>` 被定义为 `basic_format_string<char, type_identity_t<Args>...>`。`type_identity_t` 把这个形参变成非推导语境（[[temp.deduct.type]]），`Args` 只从后面的实参推导；之后字符串字面量再经由 consteval 构造函数隐式转换过来。

### 运行时才知道的格式串：`dynamic_format` {{c++26}}

```cpp run title="dynamic-format.cpp" ok
#include <cassert>
#include <format>
#include <string>

int main() {
    std::string fmt = "{} + {} = {}";            // 运行期才知道的格式串
    assert(std::format(std::dynamic_format(fmt), 1, 2, 3) == "1 + 2 = 3");

    try {
        (void)std::format(std::dynamic_format("{:d}"), "str");
        assert(false);
    } catch (const std::format_error&) {
        // 检查推迟到运行期：抛出异常
    }
}
```

格式串来自翻译文件之类的运行时数据时，`std::format(s, args...)` 无法编译，因为 `s` 不是常量表达式。C++20 和 C++23 的做法是改用 `std::vformat(s, std::make_format_args(args...))`。

C++26 的 [[P2918R2]] 提供了更直接的写法。它最初叫 `std::runtime_format`，当前草案中名为 `std::dynamic_format`。它返回一个仅用于说明的 *dynamic-format-string* 对象，`basic_format_string` 有一个接受它的非 `consteval` 构造函数，于是检查推迟到运行时，失败时抛出 `format_error`。

*dynamic-format-string* 的复制构造和复制赋值都是 deleted 的。它只保存一个 `string_view`，禁止复制后就只能把 `dynamic_format(...)` 的结果直接传给格式化函数，不能存进变量以后再用，减少了悬垂的机会。本机 libc++ 提供 `std::dynamic_format`，没有 `std::runtime_format`。

## 格式化函数 [format.functions]

```cpp run title="format-to-n.cpp" ok
#include <cassert>
#include <format>
#include <iterator>
#include <string>
#include <string_view>

int main() {
    char buf[4];
    auto [out, size] = std::format_to_n(buf, sizeof buf, "{}", 123456);
    assert(size == 6);                                   // 完整长度
    assert(out == buf + 4);                              // 只写了 4 个
    assert(std::string_view(buf, out) == "1234");

    assert(std::formatted_size("{:>10}", 1) == 10);      // 只计算长度，不输出

    std::string s;
    std::format_to(std::back_inserter(s), "{}+{}", 1, 2);
    assert(s == "1+2");
}
```

每个格式化函数都有 `char` 和 `wchar_t` 两套，以及带 `const locale&` 参数的版本。

### `format` 与 `vformat`（¶3–¶8）

¶3 `format(fmt, args...)` 等价于 `vformat(fmt.str, make_format_args(args...))`。¶7 `vformat` 返回格式化结果；如果给了 `loc`，就用它做 locale 相关的格式化，即 `L` 选项（[[format.string.std#17]]）。

不给 `loc` 时，只有格式说明里写了 `L`，才会使用全局 locale `std::locale()`（[[format.context#7]]）。所以 `std::format("{}", 1234.5)` 在德语 locale 下也输出 `1234.5`。

### `format_to` 与 `vformat_to`（¶9–¶18）

¶13–¶17 输出写到迭代器 `out` 开始的 `[out, out + N)`，返回 `out + N`，`N` 是输出的字符数。¶14 是约束：`Out` 满足 `output_iterator<const charT&>` 的语法要求；¶15 是前置条件：`Out` 还要符合该概念的语义要求。

`format_to` 不知道目标有多大。用它写一个定长数组，输出过长就是 {{ub}}。

### `format_to_n` 与 `formatted_size`（¶19–¶28）

¶19 设 `N` 是完整输出的长度（即 `formatted_size(fmt, args...)`），`M = clamp(n, 0, N)`。¶22 只写前 `M` 个字符；¶23 返回 `{out + M, N}`。所以返回的 `size` 是完整长度，与 `n` 比较就知道是否被截断；负的 `n` 被当作 0。

¶27 `formatted_size` 只返回长度，不输出任何字符。¶21、¶26 要求每个实参的 formatter 满足 *BasicFormatter* 要求（[[format.formatter]]）。

### 编译期格式化（¶1）

¶1 这些函数的调用只有在用到的每个 formatter 特化都是 [[g:constexpr-enabled-specialization|constexpr-enabled]] 时，才可能是常量子表达式。不带 `locale` 参数的版本在概要中都声明为 `constexpr`；带 `locale` 的不是，因为 `std::locale` 不能在常量求值中使用。这是 C++23 之后加入草案的措辞。

!!! impl
    截至写作时，libc++ 的 `std::format` 还不是 `constexpr` 的，`static_assert(std::format("{}", 42) == "42")` 无法通过；`__cpp_lib_format` 仍是 `202110L`。

## 错误报告 [format.err.report]

¶1 规定了三件事：

1. 传入的 `fmt` 对 `args` 不是合法格式串时，格式化函数抛出 `format_error`。对 `format_string` 版本，大多数这类错误在编译时已经被拦下，所以这一句主要作用于 `vformat` 系列和 `dynamic_format`。但有些错误只能在运行时发现，例如动态宽度 `{:{}}` 的实参是负数（[[format.string.std#10]]）。
2. formatter 特化和迭代器操作抛出的异常原样传播。
3. 分配失败按 [[res.on.exception.handling]] 报告，即抛出 `bad_alloc`。

[format.error] `format_error` 派生自 `runtime_error`，两个构造函数都是 `constexpr` 的，¶2–¶3 规定 `what()` 的内容与传入的字符串相同。

## 实参的类型擦除 [format.arguments]

```cpp run title="format-args.cpp" ok
#include <cassert>
#include <format>
#include <type_traits>

int main() {
    short sh = 3;
    const char* s = "hi";
    auto store = std::make_format_args(sh, s);
    std::format_args args = store;                          // 不拥有实参的视图
    assert(args.get(0) && args.get(1) && !args.get(2));    // 越界得到空的 arg
    bool is_int = args.get(0).visit([](auto v) { return std::is_same_v<decltype(v), int>; });
    assert(is_int);                                         // short 被归一化为 int
    assert(std::vformat("{}-{}", args) == "3-hi");
}
```

### `basic_format_arg`：14 种类型之一 [format.arg]

`basic_format_arg<Context>` 在说明中就是一个

```cpp
variant<monostate, bool, char-type,
        int, unsigned int, long long int, unsigned long long int,
        float, double, long double,
        const char-type*, basic_string_view<char-type>,
        const void*, handle>
```

任何实参都先被归一化成这 14 种之一，运行期内核因此只需要一份。¶6 给出映射规则（`TD` 是去掉 `const` 后的实参类型）：

| 实参类型 `TD` | 存为 |
|---|---|
| `bool`、`char-type` | 原样（¶6.1） |
| `char`，而 `char-type` 是 `wchar_t` | `static_cast<wchar_t>(static_cast<unsigned char>(v))`，先转无符号，避免负值符号扩展（¶6.2） |
| 不比 `int` 宽的有符号整数（`short`、`signed char` 等） | `int`（¶6.3） |
| 不比 `unsigned int` 宽的无符号整数 | `unsigned int`（¶6.4） |
| 更宽的整数 | `long long` 或 `unsigned long long`（¶6.5–¶6.6） |
| 标准浮点类型 | 原样（¶6.7） |
| 字符类型匹配的 `basic_string`、`basic_string_view` | `basic_string_view`（¶6.8） |
| 退化后为 `char-type*` 或 `const char-type*` | `const char-type*`（¶6.9） |
| `void*`、`nullptr_t` 等 | `const void*`（¶6.10） |
| 其他所有类型（用户类型、扩展浮点类型、比 `long long` 更宽的整数……） | `handle`（¶6.11） |

¶6.3–¶6.6 说的有符号、无符号整数类型包括扩展整数类型（[[basic.fundamental]]）。比 `long long` 还宽的扩展整数不符合其中任何一条，落入 `handle`。¶4 要求实参类型可以用 `Context` 格式化，即有可用的 formatter；注 1 指出，成员指针没有标准 formatter，直接格式化成员指针是非良构的。

¶5 前置条件：如果实参退化为 `char-type*` 或 `const char-type*`，它必须指向以空字符结尾的字符串。传一个没有结尾空字符的 `char` 数组是 {{ub}}。

¶10–¶14 `handle` 擦除用户类型：保存对象的地址和一个函数指针，该函数在运行时构造 `formatter<TD>`，先调用 `parse`，再调用 `format`。¶11–¶13 规定，如果 `const TD` 可以格式化，就以 `const` 方式传给 `format`，否则以非 `const` 方式传。这是 [[P2418R2]] 为支持只能以非 `const` 方式迭代的视图（如 `filter_view`）而加入的。

¶8–¶9 访问存储的值用成员函数 `arg.visit(vis)`，它是 C++26 的 [[P2637R3]] 加入的，用显式对象形参 `this basic_format_arg arg` 声明（[[dcl.fct]]）。旧的自由函数 `visit_format_arg` 已移入附录 [[depr.format]]。¶3、¶7 默认构造的 `basic_format_arg` 存 `monostate`，它的 `explicit operator bool` 为假。

### `make_format_args` 只接受左值 [format.arg.store]

¶3 `make_format_args(Args&... fmt_args)` 返回一个仅用于说明的 *format-arg-store*，内部是 `array<basic_format_arg<Context>, sizeof...(Args)>`。

形参是左值引用 `Args&`，这是 [[P2905R2]] 的修改，作为缺陷报告也适用于 C++23。之前它接受转发引用，`std::make_format_args(42)` 能编译，但返回的 store 引用了一个在完整表达式结束时就销毁的临时量，存进变量再用就悬垂了。现在传右值直接非良构：

```cpp run title="make-format-args.cpp" error
#include <format>

int main() {
    auto s = std::vformat("{}", std::make_format_args(42));   // error: 不能绑定右值
}
```

### `basic_format_args`：不拥有实参的视图 [format.args]

¶3 `basic_format_args<Context>` 只保存实参个数和指向 store 数组的指针，不拥有实参。¶4 `get(i)` 越界时返回默认构造的 `basic_format_arg`，而不是 {{ub}}，可以用 `explicit operator bool` 检测。

¶2 建议实现针对少量实参优化表示，例如把各实参的类型标签单独打包。libc++ 就是这样做的：实参不多时，它把每个实参的类型标签用几个比特压进一个 64 位整数，值另存一个数组；超过上限才改存完整的 `basic_format_arg` 数组。

## `pair` 与 `tuple` 的 formatter [format.tuple]

```cpp run title="tuple-format.cpp" ok
#include <cassert>
#include <format>
#include <string>
#include <tuple>
#include <utility>

int main() {
    assert(std::format("{}", std::tuple{1, "s", 2.5}) == "(1, \"s\", 2.5)");
    assert(std::format("{:m}", std::pair{1, 2}) == "1: 2");
    assert(std::format("{:n}", std::pair{1, 2}) == "1, 2");
    assert(std::format("{:*^10}", std::pair{1, 2}) == "**(1, 2)**");
}
```

¶1 C++23 起，只要每个元素类型都可以格式化，标准库就为 `pair` 和 `tuple` 提供 formatter（[[P2286R8]]）。默认输出 `(a, b, c)`。¶7 每个元素用自己的 formatter 解析一个空的格式说明，并在可能时调用 `set_debug_format()`，所以字符串元素会带引号并转义，如 `(1, "s", 2.5)`。

¶2–¶4 *tuple-format-spec* 只有 `[fill-and-align][width][type]` 三部分，`type` 有两个取值（表 116）：

- `m`：只能用于恰好两个元素的情况，等价于 `set_separator(": ")` 加 `set_brackets({}, {})`，输出 `1: 2`，这正是 map 元素的格式；
- `n`：去掉括号，输出 `1, 2`。

无法为单个元素指定格式说明，这一点不像范围的 `{::spec}`。需要时只能自己写 formatter，或者先把元素拆开。

`enable_nonlocking_formatter_optimization` 对 `pair`、`tuple` 的值是各元素对应值的合取（见 [[format.formatter]]）。

<details class="fine" markdown="1"><summary>其余条文</summary>

[format.syn] 是 `<format>` 的概要。¶1 规定 `format_to_n_result<Out>` 只有 `out` 和 `size` 两个成员，没有基类，可以用结构化绑定拆开。

[format.functions] ¶2 说明，描述中对某些迭代器类别使用的 `+` 运算按 [algorithms.requirements] 的约定理解。¶4–¶6、¶10–¶12 是 `wchar_t` 和带 `locale` 的重载，等价关系与 `char` 版本相同。

[format.arg] ¶1–¶2 `basic_format_arg` 供用户定义的 formatter 访问实参；程序为它添加特化是 {{ub}}。

[format.arg.store] ¶2 要求每个实参的 formatter 满足 *BasicFormatter*；¶4 `make_wformat_args` 等价于 `make_format_args<wformat_context>`。

[format.tuple] ¶5–¶6、¶8–¶11 规定 `set_separator`、`set_brackets` 的效果以及 `format` 依次输出左括号、以分隔符隔开的各元素、右括号。

</details>

## 历史

!!! history
    - C++20：[[P0645R10]] 引入 `<format>`，基于 {fmt} 库。
    - [[P2216R3]]（作为对 C++20 的缺陷报告）：加入 `basic_format_string` 的 consteval 编译期检查，并减少了 `format_to` 对不同迭代器类型的代码膨胀。
    - [[P2418R2]]（对 C++20 的缺陷报告）：支持只能以非 `const` 方式格式化的类型。
    - C++23：[[P2508R1]] 公开 `basic_format_string`（此前仅用于说明）并加入 `get()`；[[P2286R8]] 加入范围、`pair`/`tuple` 格式化和 `?` 调试格式。
    - C++26：[[P2637R3]] 成员函数 `visit`；[[P2905R2]] `make_format_args` 只接受左值；[[P2918R2]] 运行时格式串，后更名为 `dynamic_format`。
    - C++23 之后的草案给格式化函数加上了 `constexpr`，并引入 constexpr-enabled 特化的概念。

## 常见误解

!!! pitfall "保存 `basic_format_args` 或 `make_format_args` 的结果"
    `basic_format_args` 只是视图，*format-arg-store* 里的 `string_view` 和 `handle` 也只是引用。不要把它们保存到比实参活得更久的地方。

!!! pitfall "用 `format_to` 写定长缓冲区"
    `format_to` 没有长度参数。写入定长缓冲区要用 `format_to_n`，并用返回的 `size` 判断是否截断。

!!! pitfall "以为 `std::format` 默认按全局 locale 输出"
    正好相反：不写 `L` 时与 locale 无关，只有 `{:L}` 才使用 locale。

## 思考题

!!! question "思考题 1"
    `std::format(fmt_sv, 1)` 中 `fmt_sv` 是一个 `constexpr std::string_view` 局部变量，能编译吗？去掉 `constexpr` 呢？

<details markdown="1">
<summary>答案</summary>

有 `constexpr` 时可以。构造 `format_string` 是一次立即调用，`fmt_sv` 是 `constexpr` 变量，它的值可以在常量求值中读取（[[expr.const]]），检查也能通过。

去掉 `constexpr` 后，`fmt_sv` 的值不能在常量求值中读取，立即调用不是常量表达式，程序非良构。Clang 报 `call to consteval function ... is not a constant expression`。改用 `std::dynamic_format(fmt_sv)` 或 `vformat` 即可。
</details>

!!! question "思考题 2"
    为什么 `format_string<Args...>` 要写成 `basic_format_string<char, type_identity_t<Args>...>`，直接写 `basic_format_string<char, Args...>` 会怎样？

<details markdown="1">
<summary>答案</summary>

`format(format_string<Args...> fmt, Args&&... args)` 中，如果第一个形参也参与推导 `Args`，推导就要拿字符串字面量的类型 `const char[N]` 去匹配 `basic_format_string<char, Args...>`。这必然失败，而推导时不考虑隐式转换（[[temp.deduct.call]]），整个推导因此失败。

`type_identity_t` 让这个形参成为非推导语境，`Args` 只从 `args` 推导；推导完成后，字符串字面量再通过 consteval 构造函数隐式转换为 `basic_format_string`。
</details>

## 小结

| 设施 | 要点 |
|---|---|
| `basic_format_string` | consteval 构造；格式串不合法时立即调用不是常量表达式，编译失败 |
| `dynamic_format` | C++26；推迟到运行时检查，失败抛 `format_error`；原名 `runtime_format` |
| `format` / `vformat` | 模板外壳加类型擦除的内核；不写 `L` 不使用 locale |
| `format_to_n` | 写 `min(n, N)` 个字符，返回 `{out + M, N}`，`N` 是完整长度 |
| `basic_format_arg` | 14 种类型之一；短整数归一化为 `int`；用户类型存为 `handle` |
| `make_format_args` | 只接受左值（[[P2905R2]]） |
| `basic_format_args` | 不拥有实参的视图；越界的 `get` 返回空的 arg |
| tuple formatter | 输出 `(a, b)`；`m` 得到 `a: b`，`n` 去掉括号；字符串元素自动用调试格式 |
| `format_error` | 派生自 `runtime_error`，构造函数是 `constexpr` |
