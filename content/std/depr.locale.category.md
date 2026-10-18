---
title: 弃用的库特性（二）：本地化、格式化、时间、文件系统与 iostream（D.20–D.23、D.25–D.26）
summary: Annex D 中与文本和 I/O 有关的弃用：UTF-16/32 ↔ UTF-8 的 codecvt 刻面、visit_format_arg、asctime/ctime、filesystem::u8path、返回 std::string 的 path::string()/generic_string()、以及 signed char / unsigned char 的流提取和插入。每项给出规范内容、弃用原因、替代写法与 libc++ 实测。
status: draft
covers: depr.format, depr.format.syn, depr.format.arg, depr.ctime, depr.filesystems, depr.fs.path.factory, depr.fs.path.obs, depr.istream.extractors, depr.ostream.inserters
related: depr, locale.categories, format, ctime.syn, fs.class.path, input.streams, output.streams, text.encoding
tags: 附录, 弃用, 标准库, 文本, Unicode
updated: 2026-10-18
---

这一页是 [[depr]] 的库部分之二。这几项弃用有一个共同的背景：C++ 正在把"字符串的编码"这件事从隐式约定变成显式类型。`char8_t` 的引入（C++20）、`std::format` 对 Unicode 的处理、`<text_encoding>`（C++26），都在推动同一个方向：一个 `std::string` 里到底是什么编码，应当由接口说清楚，而不是靠"当前 locale"或"平台惯例"去猜。被弃用的设施，大多是在这个问题上含糊其辞的旧接口。

实测环境：Clang 23.1.3 + libc++。

## D.20 弃用的 locale 类别刻面 {#depr.locale.category}

**¶1–¶2**：`ctype` locale 类别包含以下刻面，如同它们列在 [[locale.categories]] 的表中一样：

- `codecvt<char16_t, char, mbstate_t>`、`codecvt<char32_t, char, mbstate_t>`
- `codecvt<char16_t, char8_t, mbstate_t>`、`codecvt<char32_t, char8_t, mbstate_t>`
- 以及对应的四个 `codecvt_byname`。

**¶3**：`char16_t` 版本在 UTF-16 与 UTF-8 之间转换，`char32_t` 版本在 UTF-32 与 UTF-8 之间转换。

**为什么弃用**：`codecvt<char16_t, char, …>` 把 `char` 序列**硬性规定为 UTF-8**，这与 `char` 在其余地方表示"执行字符集/本地编码"的含义冲突。C++20 引入 `char8_t` 时，把这两个 `char` 版本列为弃用，并加入了 `char8_t` 版本作为替代；当前草案中 `char8_t` 版本也在弃用之列。根本原因是 `codecvt` 这套接口本身（基于 `mbstate_t`、需要从 `locale` 中取出、错误处理笨拙）已经不适合承担 Unicode 转换的任务，`<codecvt>` 头文件已在 C++26 中删除（见 [[diff.cpp23]]）。

```cpp
#include <locale>
auto& a = std::use_facet<std::codecvt<char16_t, char, std::mbstate_t>>(std::locale());      // 弃用
auto& b = std::use_facet<std::codecvt<char16_t, char8_t, std::mbstate_t>>(std::locale());   // 弃用
```

**libc++ 实测**（`-std=c++20` 起）：

```text
warning: 'codecvt<char16_t, char, __mbstate_t>' is deprecated [-Wdeprecated-declarations]
warning: 'codecvt<char16_t, char8_t, __mbstate_t>' is deprecated [-Wdeprecated-declarations]
```

**替代**：标准库目前没有通用的 Unicode 编码转换设施。实践中用第三方库（ICU、simdutf 等），或者自己写 UTF-8/16/32 的转换（这三者之间的转换只是位运算，几十行代码）。

## D.21 弃用的格式化 {#depr.format}

### D.21.1 `<format>` 概要 {#depr.format.syn}

**¶1**：`<format>` 额外声明

```cpp
template<class Visitor, class Context>
  decltype(auto) visit_format_arg(Visitor&& vis, basic_format_arg<Context> arg);
```

### D.21.2 格式化实参 {#depr.format.arg}

**¶1** *Effects*：等价于 `return visit(std::forward<Visitor>(vis), arg.value_);`，其中 `value_` 是 `basic_format_arg` 内部的仅用于阐述的 `variant` 成员。

**为什么弃用**：C++26 给 `basic_format_arg` 加了成员函数 `visit`，同时支持返回类型被显式指定的 `visit<R>`，与 `std::variant` 的 `visit` 成员（同样是 C++26 新增）保持一致。自由函数 `visit_format_arg` 因此变得多余。

```cpp
#include <format>
void f(std::format_args a) {
  std::visit_format_arg([](auto) {}, a.get(0));   // 弃用
  a.get(0).visit([](auto) {});                    // 替代（C++26）
}
```

**libc++ 实测**：`-std=c++2c` 下警告 `'visit_format_arg<(lambda at …), std::format_context>' is deprecated [-Wdeprecated-declarations]`；`-std=c++20` 下没有警告。

## D.22 弃用的时间格式化 {#depr.ctime}

**¶1**：`<ctime>` 额外声明 `char* asctime(const tm* timeptr);` 和 `char* ctime(const time_t* timer);`。

**¶2**：`asctime` 和 `ctime` **不要求避免数据竞争**（[[res.on.data.races]]）。

这两个函数返回指向静态缓冲区的指针，多线程同时调用就会互相覆盖；`asctime` 在年份超过四位数等情况下还会溢出那个固定大小的缓冲区。C23 把它们标为弃用，C++ 跟进，把它们从正文的 `<ctime>`（[[ctime.syn]]）移到了这里，并明确声明它们不受标准库"不得引入数据竞争"一般要求的保护。

```cpp
#include <ctime>
std::time_t t = 0;
char* s = std::ctime(&t);   // 弃用；返回的指针指向共享的静态缓冲区
```

**libc++ 实测**：`-std=c++2c` 下没有警告。

**替代**：`std::format("{:%c}", std::chrono::system_clock::now())`（[[time.format]]），或 C 的 `strftime`。

## D.23 弃用的文件系统设施 {#depr.filesystems}

### D.23.1 `path` 工厂函数 `u8path` {#depr.fs.path.factory}

**¶1–¶5**：`<filesystem>` 额外提供

```cpp
template<class Source>       path u8path(const Source& source);
template<class InputIterator> path u8path(InputIterator first, InputIterator last);
```

*Mandates*：`Source` / `InputIterator` 的值类型是 `char` 或 `char8_t`。*Preconditions*：输入是 UTF-8 编码的。*Returns*：如果 `path::value_type` 是 `char` 且本地窄编码就是 UTF-8，直接构造；否则先转换为 `string_type`（Windows 上是 UTF-16）或经 `u32string` 中转。Unicode 转换的具体方式未指定。

**为什么弃用**：C++17 中 `std::string` 无法表达"我是 UTF-8"，只好用一个专门的工厂函数 `u8path` 来说明编码。C++20 有了 `char8_t` 和 `std::u8string`，`path` 的构造函数可以通过实参类型识别编码：`path(u8"名字")` 或 `path(std::u8string_view{…})` 就是 UTF-8。¶6 的注也指出，`u8path` 的例子"代表的是历史用法"，现在更推荐直接把 `std::u8string` 传给 `path` 的构造函数，这与 `path` 处理其他编码的方式一致。

```cpp
#include <filesystem>
auto p1 = std::filesystem::u8path("abc");   // 弃用
auto p2 = std::filesystem::path(u8"abc");   // 替代
```

**libc++ 实测**：`-std=c++20` 起警告 `'u8path<char[4], 0>' is deprecated [-Wdeprecated-declarations]`。

**替代难点**：如果手里是一个存着 UTF-8 的 `std::string`（例如从网络或数据库读来的），要先把它变成 `char8_t` 序列：`std::u8string(s.begin(), s.end())`。这是 `char8_t` 方案里一个公认的不便之处。

### D.23.2 返回 `std::string` 的格式观察函数 {#depr.fs.path.obs}

**¶1–¶3**：`path` 额外声明两个成员：

```cpp
std::string string() const;           // Returns: native_encoded_string()
std::string generic_string() const;   // Returns: generic_native_encoded_string()
```

这是当前草案中较新的改动：正文的 `path` 新增了 `native_encoded_string()`、`display_string()` 及其 `generic_` 版本（[[fs.class.path]]），而非模板的 `string()` / `generic_string()` 被移到 Annex D。正文中仍保留了模板版本 `string<EcharT, traits, Allocator>(const Allocator&)`，但它的 `EcharT` 没有默认值，无法推导，所以不写模板实参的 `p.string()` 调用的是**这里被弃用的那个非模板版本**。

**为什么弃用**：`p.string()` 这个名字没有说明返回的是什么编码。在 POSIX 上它返回原始字节（文件名不一定是合法 UTF-8），在 Windows 上它把 UTF-16 转换成当前代码页（可能丢字符）。新接口把两种需求分开：

- `native_encoded_string()`：按本地窄编码转换的字符串，用于交给操作系统或 C API；
- `display_string()`：等于 `std::format("{}", path)`，结果适合交给格式化和 `print` 函数，用于显示。

```cpp
#include <filesystem>
std::string s(const std::filesystem::path& p) {
  return p.string();   // 当前草案：弃用
}
```

**libc++ 实测**：`p.string()` 在 `-std=c++2c` 下没有警告，libc++ 尚未实现新接口。

**替代**：按用途选 `p.native_encoded_string()` 或 `p.display_string()`；需要无损获得文件名时，用 `p.native()`（类型是 `path::string_type`）或 `p.u8string()`。

## D.25 `signed char` / `unsigned char` 的提取 {#depr.istream.extractors}

**¶1–¶3**：`<istream>` 额外提供 `basic_istream<char, traits>` 对 `unsigned char&` 和 `signed char&` 的 `operator>>`：作为格式化输入函数，提取一个字符存入 `c`；没有可用字符时设置 `failbit`。

**¶4–¶9**：以及对 `unsigned char (&)[N]` 和 `signed char (&)[N]` 的 `operator>>`：提取字符直到存满 `n - 1` 个（`n` 是 `width()` 与 `N` 中较小的那个，`width()` 为 0 时取 `N`）、遇到文件尾或遇到空白字符，然后存入一个空字节并调用 `width(0)`；一个字符都没提取到时设置 `failbit`。

## D.26 `signed char` / `unsigned char` 的插入 {#depr.ostream.inserters}

**¶1–¶3**：`<ostream>` 额外提供 `basic_ostream<char, traits>` 对 `signed char` 和 `unsigned char` 的 `operator<<`，等价于 `return out << static_cast<char>(c);`。

**¶4–¶5**：以及对 `const signed char*` 和 `const unsigned char*` 的 `operator<<`，等价于 `return out << reinterpret_cast<const char*>(s);`。

### 为什么弃用这两组

这两组重载是 C++98 留下的，它们把 `signed char` 和 `unsigned char` 当作**字符**处理。但在现代代码中，这两个类型几乎总是作为**小整数**使用：`std::int8_t` 和 `std::uint8_t` 在所有主流平台上就是它们的 typedef。于是有了这个经典陷阱：

```cpp
#include <cstdint>
#include <iostream>
int main() {
  std::uint8_t v = 65;
  std::cout << v << '\n';    // 打印 "A"，而不是 "65"
  std::uint8_t n;
  std::cin >> n;             // 输入 "42" 只读走 '4'，n == 52
}
```

libc++ 上实测：`std::cout << v` 打印 `A`；从 `"42"` 读入后 `int(n)` 是 52；而 `std::format("{}", v)` 输出 `65`，`std::format` 一开始就把这两个类型当作整数格式化。

弃用这些重载，是为将来改变它们的行为（或删除它们，让调用落到整数的重载上）做准备。在此之前，代码应当把意图写清楚：要字符就转换为 `char`，要数值就提升为 `int`。

**libc++ 实测**：`std::cin >> sc` 和 `std::cout << (const unsigned char*)buf` 在 `-std=c++2c -Wdeprecated` 下都没有警告，libc++ 尚未标记。

**替代**：

- 当字符输出：`out << static_cast<char>(c)`；
- 当数值输出：`out << +c` 或 `out << int(c)`，`std::format("{}", c)` 对 `signed char`/`unsigned char` 本来就输出数值；
- 输入数值：读进 `int` 再检查范围后转换。

## 小结

| 条款 | 特性 | libc++ 警告 |
|---|---|---|
| D.20 | `codecvt<char16_t/char32_t, char/char8_t>` | 有（C++20 起） |
| D.21 | `visit_format_arg` | 有（C++26 模式） |
| D.22 | `asctime`、`ctime` | 无 |
| D.23.1 | `u8path` | 有（C++20 起） |
| D.23.2 | 非模板 `path::string()` / `generic_string()` | 无（新接口未实现） |
| D.25 | `>>` 到 `signed char` / `unsigned char` | 无 |
| D.26 | `<<` `signed char` / `unsigned char` | 无 |
