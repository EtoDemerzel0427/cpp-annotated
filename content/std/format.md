---
title: 格式化库
summary: std::format 家族的总体架构——编译期检查的 basic_format_string（consteval 构造函数）、类型擦除的实参存储 basic_format_arg/basic_format_args、format/vformat/format_to/format_to_n/formatted_size 的精确语义、format_error 的错误报告，以及 pair/tuple 的 formatter
status: draft
covers: format.syn, format.err.report, format.fmt.string, format.functions, format.arguments, format.arg, format.arg.store, format.args, format.tuple, format.error
papers: P0645R10, P2216R3, P2418R2, P2508R1, P2286R8, P2637R3, P2905R2, P2918R2
related: format.string, format.formatter, charconv, print.fun, expr.const.imm, dcl.constexpr, expr.const.core, variant
tags: 标准库, format, 格式化, consteval, 类型擦除
updated: 2026-10-18
---

`<format>`（C++20，[[P0645R10]]）要同时解决 `printf` 与 `iostream` 各自的老毛病：

- `printf` 简洁、快，但**类型不安全**——`%d` 配 `long` 是 {{ub}}，而且不能扩展到用户类型；
- `iostream` 类型安全、可扩展，但啰嗦、有状态（`std::hex` 会“粘”在流上）、慢、难以本地化（格式片段被切碎在多个 `<<` 之间）。

`std::format` 的答案是：Python 风格的格式串 + 可特化的 `formatter<T>` + **编译期**格式串检查 + 类型擦除的运行期核心。理解这套库，关键是看清它的两层结构：

```text
format(fmt, args...)            ← 模板外壳：编译期检查 fmt，把 args 打包
   └─ vformat(fmt.get(), make_format_args(args...))
         └─ 非模板（对每种 Context 只有一份）的运行期解释器：
              逐个替换字段 → basic_format_arg::visit → formatter<T>::parse/format
```

外壳负责类型安全和诊断，内核负责避免为每一组实参类型实例化一整份格式化代码（代码膨胀）。

本页覆盖格式化库的骨架；格式串语法见 [[format.string]]，formatter 机制与范围格式化见 [[format.formatter]]。`std::print`/`std::println` 不在本节，而在 [input.output] 的 [[print.fun]]。

| 子条款 | 内容 | 本站页面 |
|---|---|---|
| [format.syn] | 头文件概要 | 本页 |
| [format.string] | 格式串语法、标准格式说明 | [[format.string]] |
| [format.err.report] | 错误报告 | 本页 |
| [format.fmt.string] | `basic_format_string` | 本页 |
| [format.functions] | `format`、`vformat`、`format_to`、`format_to_n`、`formatted_size` | 本页 |
| [format.formatter] | formatter 要求、`formattable`、标准特化、转义、两个 context | [[format.formatter]] |
| [format.range] | 范围格式化 | [[format.formatter]] |
| [format.arguments] | `basic_format_arg`、*format-arg-store*、`basic_format_args` | 本页 |
| [format.tuple] | `pair`/`tuple` 的 formatter | 本页 |
| [format.error] | `format_error` | 本页 |

## 概要（[format.syn]）

概要里值得留意的几处：

- 每个格式化函数都有 `char`/`wchar_t` 两套，以及带 `const locale&` 的版本。**不带 locale 的版本是 `constexpr` 的，带 locale 的不是**——`std::locale` 本身不能在常量求值中使用。（`format` 函数族成为 `constexpr` 是 C++23 之后加入草案的措辞；见下文 [format.functions] ¶1。）
- `format_string<Args...>` 是 `basic_format_string<char, type_identity_t<Args>...>`。`type_identity_t` 把 `Args` 放进**非推导语境**（[[temp.deduct.type]]），保证 `Args` 只从后面的实参推导，格式串参数只负责“接受一个字符串字面量并检查它”。
- *dynamic-format-string* 与 `dynamic_format(string_view)`：显式跳过编译期检查的逃生口，见下文。
- ¶1：`format_to_n_result<Out>` 只有 `out`、`size` 两个成员，没有基类——可以结构化绑定。

## 编译期检查：`basic_format_string`（[format.fmt.string]）

```cpp
template<class charT, class... Args>
struct basic_format_string {
  template<class T> consteval basic_format_string(const T& s);
  constexpr basic_format_string(dynamic-format-string<charT> s) noexcept;
  constexpr basic_string_view<charT> get() const noexcept;
};
```

¶1：构造函数模板受约束——`const T&` 必须能转换为 `basic_string_view<charT>`。¶2：用 `s` 初始化内部的 `str`。真正的魔法在 ¶3：

!!! std
    A call to this function is not a core constant expression ([expr.const.core]) unless there exist args of types `Args` such that *str* is a format string for args.

把这句话和核心语言规则拼起来：

1. 构造函数是 `consteval` 的，即**立即函数**（[[g:immediate-function]]，[[dcl.constexpr]]）。
2. 对立即函数的调用（不在立即函数语境中时）是**立即调用**（[[g:immediate-invocation]]），按 [[expr.const.imm]] 它必须是常量表达式，否则程序**非良构**。
3. ¶3 说：格式串对 `Args` 不合法时，这个调用**不是**核心常量表达式。
4. 所以：`std::format("{:d}", "str")` 是**编译错误**，而且是标准强制要求的诊断，不是 QoI。

实现上，libc++ 的构造函数体（`__format/format_functions.h`）在常量求值中把整个格式串跑一遍解析器，并对每个实参调用其 formatter 的 `parse`；一旦发现错误就调用非 `constexpr` 的 `__throw_format_error`，从而使求值不是常量表达式。所以诊断信息里会出现类似 "non-constexpr function '__throw_format_error' cannot be used in a constant expression" 的 note，后面跟着人类可读的错误原因。

```cpp run title="compile-time-check.cpp" error
#include <format>

int main() {
    auto a = std::format("{} {}", 1);        // error: 实参不够
    auto b = std::format("{:d}", "str");     // error: 字符串不接受 d
    auto c = std::format("{0} {}", 1, 2);    // error: 自动与手动编号混用
}
```

!!! note "推论：自定义 formatter 的 `parse` 必须是 `constexpr`"
    编译期检查会调用每个实参的 `formatter<T>::parse`。如果你的 `parse` 不是 `constexpr` 的，那么任何使用该类型的 `std::format("...")` 调用都无法成为常量表达式——直接编译失败。详见 [[format.formatter]]。

### 运行期格式串：`dynamic_format` {{c++26}}

格式串只在运行期才知道（例如来自翻译文件）时，`std::format(s, args...)` 不能编译：`s` 不是常量表达式。C++20/23 的做法是改调 `std::vformat(s, std::make_format_args(args...))`。

C++26 期间 [[P2918R2]] 增加了一个更直接的写法，最初命名为 `std::runtime_format`；当前草案中它已更名为 **`std::dynamic_format`**。它返回一个仅用于说明的 *dynamic-format-string*，`basic_format_string` 有一个接受它的**非 consteval** 构造函数，于是检查推迟到运行期，失败时抛 `format_error`。

*dynamic-format-string* 的复制构造与复制赋值都是 deleted 的：你只能把 `dynamic_format(...)` 的纯右值直接传给格式化函数（C++17 起纯右值不需要复制，见 [[g:prvalue]]），无法把它存进变量再使用——它持有的是 `string_view`，这样可以减少悬垂的机会。

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
        // 检查推迟到运行期：抛异常
    }
}
```

!!! impl
    libc++ 23 提供的是 `std::dynamic_format`（`__format/format_functions.h` 中的 `__dynamic_format_string`），**没有** `std::runtime_format` 这个名字。仍在使用旧名的代码需要改写。

## 错误报告（[format.err.report]）

¶1 的三句话：

1. 传入的 `fmt` 对 `args` 不是格式串时，格式化函数抛 `format_error`。——对 `format_string` 版本来说这种情况在编译期就被拦下了，所以这一句实际作用于 `vformat` 系列和 `dynamic_format`。但有些错误**只能**在运行期发现，例如动态宽度 `{:{}}` 的实参是负数（[[format.string.std#10]]），或者 `{:c}` 的整数值超出 `charT` 范围。
2. formatter 特化和迭代器操作抛出的异常原样传播。
3. 分配失败按 [[res.on.exception.handling]] 报告（即 `bad_alloc`）。

## 格式化函数（[format.functions]）

¶1：调用这些函数**只有在**所用到的每个 formatter 特化都是 *constexpr-enabled*（[[g:constexpr-enabled-specialization]]）时才可能是常量子表达式。标准把整数、`bool`、字符、字符串、`nullptr_t` 的 formatter 定为 constexpr-enabled，但**浮点和 `void*` 不是**——编译期格式化浮点数需要编译期的 `to_chars`，而浮点 `to_chars` 不是 `constexpr` 的（[[charconv]]）。

!!! impl
    截至本文编写时，libc++ 23 的 `std::format` **不是** `constexpr` 的；`static_assert(std::format("{}", 42) == "42")` 无法通过。`__cpp_lib_format` 在 libc++ 中仍是 `202110L`。

### `format` 与 `vformat`（¶3–¶8）

`format(fmt, args...)` 等价于 `vformat(fmt.str, make_format_args(args...))`。¶7：返回包含格式化结果的字符串；若给了 `loc`，则用于 locale 相关格式（即 `L` 选项，[[format.string.std#17]]）。**不给 `loc` 时不会读全局 locale**——除非格式说明里写了 `L`，此时用 `std::locale()`（[format.context] ¶7）。

### `format_to` 与 `vformat_to`（¶9–¶18）

输出写到迭代器 `out`。¶14 *Constraints*：`Out` 满足 `output_iterator<const charT&>`；¶15 *Preconditions*：`Out` **建模**该概念（满足语法要求是 Constraints，语义要求是 Preconditions，见 [[library]] 中对两类元素的区分）。¶16–¶17：写入 `[out, out + N)` 并返回 `out + N`。

`format_to` 不知道目标缓冲区多大——`format_to(buf, ...)` 写一个原生数组时溢出就是 {{ub}}。

### `format_to_n`（¶19–¶24）

¶19：设 `N = formatted_size(fmt, args...)`（完整输出的长度），`M = clamp(n, 0, N)`。¶22：只写**前 `M` 个**字符；¶23：返回 `{out + M, N}`。

所以 `result.size` 是**完整**长度而不是实际写入的长度——拿它和 `n` 比较即可得知是否被截断。负的 `n` 被 `clamp` 当作 0。

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

    assert(std::formatted_size("{:>10}", 1) == 10);      // 只算长度，不输出

    std::string s;
    std::format_to(std::back_inserter(s), "{}+{}", 1, 2);
    assert(s == "1+2");
}
```

¶21、¶26：`format_to_n` 与 `formatted_size` 额外要求每个实参的 formatter 满足 *BasicFormatter* 要求（[[format.formatter]]）。

## 实参：类型擦除的核心（[format.arguments]）

### `basic_format_arg`：14 选 1 的 variant（[format.arg]）

`basic_format_arg<Context>` 在说明中是一个

```cpp
variant<monostate, bool, char-type,
        int, unsigned int, long long int, unsigned long long int,
        float, double, long double,
        const char-type*, basic_string_view<char-type>,
        const void*, handle>
```

任意实参都被**归一化**到这 14 种之一，这正是运行期内核只需写一份的原因。¶6 给出了映射规则，其中几条值得记住：

| 实参类型 `TD` | 存为 |
|---|---|
| `bool`、`char-type` | 原样 |
| `char`（而 `char-type` 是 `wchar_t`） | `static_cast<wchar_t>(static_cast<unsigned char>(v))`（¶6.2，先转无符号，避免负值符号扩展） |
| 不比 `int` 宽的有符号整数（`short`、`signed char`……） | `int` |
| 不比 `unsigned` 宽的无符号整数 | `unsigned int` |
| 更宽的整数 | `long long` / `unsigned long long` |
| **标准**浮点类型 | 原样 |
| `basic_string`/`basic_string_view`（字符类型匹配） | `basic_string_view` |
| `char-type*` / `const char-type*` | `const char-type*` |
| `void*`、`nullptr_t` 等 | `const void*` |
| 其他一切（用户类型、扩展浮点类型、比 `long long` 更宽的整数……） | `handle` |

注意 ¶6.3–¶6.6 说的是“signed/unsigned integer type”，它在 [[basic.fundamental]] 中**包括扩展整数类型**；比 `long long` 还宽的扩展整数不满足任何一条，于是落入 `handle`——前提是有可用的 formatter。注 1：成员指针没有标准 formatter，所以直接格式化成员指针非良构。

¶5 *Preconditions*：若实参衰变为 `char-type*` 或 `const char-type*`，它必须指向以空字符结尾的字符串（NTCTS）。传一个未终止的 `char` 数组的指针是 {{ub}}。

`handle`（¶10–¶14）是用户类型的类型擦除：保存对象地址和一个函数指针，该函数在运行期构造 `formatter<TD>`、调用 `parse` 再调用 `format`。¶11–¶13 规定：若 `const TD` 可格式化，就以 `const` 方式传给 `format`，否则以非 `const` 方式传——这是 [[P2418R2]] 为了支持“只能非 const 迭代的视图”（如 `filter_view`）而引入的规则。

访问方式：C++26 起用成员函数 `arg.visit(vis)`（[[P2637R3]]，使用显式对象形参 `this basic_format_arg arg`，见 [[dcl.fct]]）；旧的自由函数 `visit_format_arg` 被移入附录 [[depr.format]]。

### *format-arg-store* 与 `make_format_args`（[format.arg.store]）

`make_format_args(Args&... fmt_args)` 返回一个仅用于说明的 *format-arg-store*，内部是 `array<basic_format_arg<Context>, sizeof...(Args)>`。

注意形参是 **`Args&`**——左值引用。这是 [[P2905R2]] 的改动（作为对 C++23 的缺陷报告）：之前它接受转发引用，`std::make_format_args(42)` 能编译，但返回的 store 里引用了一个在完整表达式结束时就销毁的临时量，把它存进变量再用就悬垂了。现在传右值直接非良构：

```cpp run title="make-format-args.cpp" error
#include <format>

int main() {
    auto s = std::vformat("{}", std::make_format_args(42));   // error: 不能绑定右值
}
```

### `basic_format_args`：类型擦除的视图（[format.args]）

`basic_format_args<Context>` 只存 `size_` 和指向 store 数组的指针，**不拥有**实参。¶4：`get(i)` 在越界时返回默认构造的（`monostate`）`basic_format_arg`，而不是 UB——`explicit operator bool` 可用来检测。

¶2 *Recommended practice* 建议对少量实参优化表示，比如把类型标签单独打包。libc++ 就是这么做的：`__format/format_arg_store.h` 中的 `__packed_format_arg_store` 在实参个数不超过一定数量时，把每个实参的类型标签用几个比特压进一个 64 位整数，值另存一个数组；超过上限才退回存完整的 `basic_format_arg` 数组。

```cpp run title="format-args.cpp" ok
#include <cassert>
#include <format>
#include <type_traits>

int main() {
    short sh = 3;
    const char* s = "hi";
    auto store = std::make_format_args(sh, s);
    std::format_args args = store;                          // 非拥有的视图
    assert(args.get(0) && args.get(1) && !args.get(2));    // 越界得到空的 arg
    bool is_int = args.get(0).visit([](auto v) { return std::is_same_v<decltype(v), int>; });
    assert(is_int);                                         // short 被归一化为 int
    assert(std::vformat("{}-{}", args) == "3-hi");
}
```

## `pair` 与 `tuple` 的 formatter（[format.tuple]）{{c++23}}

¶1：标准库为 `pair<Ts...>` 与 `tuple<Ts...>` 提供 formatter（要求每个 `Ts` 都 `formattable`）。默认输出 `(a, b, c)`；每个元素用其自身的 formatter 解析**空**的格式说明，并在可能时调用 `set_debug_format()`（¶7），所以字符串元素带引号转义：`(1, "s", 2.5)`。

¶2 的 *tuple-format-spec* 只有 `[fill-and-align][width][type]`，`type` 为：

- `m`：仅当恰有两个元素时可用，等价于 `set_separator(": ")` 加 `set_brackets({}, {})`，即 `1: 2`——这正是 map 的元素格式；
- `n`：去掉括号，`1, 2`。

**无法**为单个元素指定格式说明（不像范围有 `{::spec}`）。若需要，就得自己写 formatter 或先手动拆开。

`enable_nonlocking_formatter_optimization<pair-or-tuple<Ts...>>` 是各元素该值的合取。

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

## `format_error`（[format.error]）

`format_error` 派生自 `runtime_error`；构造函数是 `constexpr` 的（这样常量求值中的格式化代码也可以 `throw format_error(...)`——C++26 允许在常量求值中抛出并捕获异常）。¶2–¶3 的后置条件：`what()` 与传入串内容相同。

## 与 `std::print` 的关系

`std::print`/`std::println`（C++23）定义在 [[print.fun]]，它们用同一套格式串和 formatter，区别只在输出目的地与编码处理：当普通字面量编码是 UTF-8 时，输出到终端走 `vprint_unicode`，以便在 Windows 控制台上正确显示 Unicode。C++26 还为它引入了“不加锁”的快速路径，由 `enable_nonlocking_formatter_optimization` 控制（见 [[format.formatter]]）。

## 常见误区

!!! pitfall "保存 `basic_format_args` 或 `make_format_args` 的结果"
    `basic_format_args` 只是视图，*format-arg-store* 里存的 `string_view`/`handle` 也只是引用。不要把它们存到比实参活得更久的地方。

!!! pitfall "用 `format_to` 写定长缓冲区"
    `format_to` 没有长度参数。写入定长缓冲区请用 `format_to_n`，并用返回的 `size` 判断是否截断。

!!! pitfall "以为 `std::format` 默认按全局 locale 输出"
    恰恰相反：不写 `L` 时与 locale 无关。`std::format("{}", 1234.5)` 在德语 locale 下也输出 `1234.5`；只有 `{:L}` 才使用 locale。

## 历史

- C++20：[[P0645R10]] 引入 `<format>`（基于 {fmt} 库）。
- [[P2216R3]]（作为对 C++20 的缺陷报告）：引入 `basic_format_string` 的 consteval 编译期检查，并去掉了 `format_to` 对任意迭代器的代码膨胀。
- [[P2418R2]]（C++20 DR）：支持非 `const` 可格式化类型。
- C++23：[[P2508R1]] 公开 `basic_format_string`（此前是仅用于说明的类型），并加了 `get()`；[[P2286R8]] 引入范围、`pair`/`tuple` 格式化与 `?` 调试格式。
- C++26：[[P2637R3]] 成员 `visit`；[[P2905R2]] `make_format_args` 只接受左值；[[P2918R2]] 运行期格式串（后更名为 `dynamic_format`）。
- C++23 之后：格式化函数被加上 `constexpr`，并引入 constexpr-enabled 特化的概念。

## 思考题

!!! question "1"
    `std::format(fmt_sv, 1)`（`fmt_sv` 是 `constexpr std::string_view` 局部变量）能编译吗？如果去掉 `constexpr` 呢？

<details markdown="1">
<summary>展开查看答案与解析</summary>

有 `constexpr` 时可以：构造函数是立即调用，实参 `fmt_sv` 是常量表达式，构造函数体中读取它没问题（按 [[expr.const]]，`constexpr` 变量在常量表达式中可用）。去掉 `constexpr` 后，`fmt_sv` 的值不能在常量求值中读取，立即调用不是常量表达式 → 非良构。clang 会报 "call to consteval function ... is not a constant expression"。修法是改用 `std::dynamic_format(fmt_sv)` 或 `vformat`。
</details>

!!! question "2"
    为什么 `format_string<Args...>` 要写成 `basic_format_string<char, type_identity_t<Args>...>`，直接写 `basic_format_string<char, Args...>` 会怎样？

<details markdown="1">
<summary>展开查看答案与解析</summary>

`format(format_string<Args...> fmt, Args&&... args)` 中，若第一个形参也参与推导 `Args`，那么推导会尝试从字符串字面量的类型（`const char[N]`）去匹配 `basic_format_string<char, Args...>`——这当然失败，进而整个推导失败（推导时不考虑隐式转换，见 [[temp.deduct.call]]）。`type_identity_t` 让该形参成为非推导语境，`Args` 只从 `args` 推导，然后字符串字面量再经由 consteval 转换构造函数隐式转换为 `basic_format_string`。
</details>

## 小结

| 设施 | 要点 |
|---|---|
| `basic_format_string` | consteval 构造；格式串不合法 → 立即调用非常量表达式 → 编译错误 |
| `dynamic_format` | C++26；跳过编译期检查，运行期抛 `format_error`；原名 `runtime_format` |
| `format` / `vformat` | 外壳 → 类型擦除内核；不给 `L` 不看 locale |
| `format_to_n` | 写 `min(n, N)` 个字符，返回 `{out + M, N}`（`N` 是完整长度） |
| `basic_format_arg` | 14 选 1 的 variant；短整数提升为 `int`；用户类型 → `handle` |
| `make_format_args` | 只接受左值（P2905R2） |
| `basic_format_args` | 非拥有视图；越界 `get` 返回空 arg |
| tuple formatter | `(a, b)`；`m` 得 `a: b`，`n` 去括号；元素自动调试格式 |
| `format_error` | 派生自 `runtime_error`；构造函数 `constexpr` |
