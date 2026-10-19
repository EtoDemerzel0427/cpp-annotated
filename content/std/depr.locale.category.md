---
title: 弃用的库特性（二）：本地化、格式化、时间、文件系统与 iostream（D.20–D.23、D.25–D.26）
summary: Annex D 中与文本和 I/O 有关的弃用：UTF-16/32 与 UTF-8 互转的 codecvt 刻面、visit_format_arg、asctime 和 ctime、filesystem::u8path、返回 std::string 的 path::string()，以及 signed char 和 unsigned char 的流输入输出。
status: done
covers: depr.format, depr.format.syn, depr.format.arg, depr.ctime, depr.filesystems, depr.fs.path.factory, depr.fs.path.obs, depr.istream.extractors, depr.ostream.inserters
papers: P0482R6, LWG3767, P2871R3, P2637R3, P2319R5
related: depr, locale.categories, format, ctime.syn, fs.class.path, input.streams, output.streams, text.encoding
tags: 附录, 弃用, 标准库, 文本, Unicode
updated: 2026-10-19
---

!!! tldr
    - 这几项弃用的共同原因是：旧接口没有说清一个 `char` 字符串里是什么编码，新接口用类型（`char8_t`、`std::u8string`）或函数名把它说清。
    - `codecvt<char16_t, char, mbstate_t>` 等刻面把 `char` 硬性当作 UTF-8，已被弃用；标准库目前没有通用的替代品。
    - `std::uint8_t` 通常就是 `unsigned char`，`std::cout << v` 把它当字符输出。为此弃用了 `signed char` 和 `unsigned char` 的 `<<`、`>>` 重载，`std::format` 则一直把它们当整数。
    - `asctime`、`ctime` 返回指向共享静态缓冲区的指针，不保证线程安全；改用 `std::format` 和 `<chrono>`。
    - `u8path` 由 `path(std::u8string)` 取代；不写模板实参的 `path::string()` 也已弃用，按用途改用 `native_encoded_string()` 或 `display_string()`。

**弃用**（deprecated）的特性仍然是规范性的，只是已被确定为将来可能删除的候选；实现可以给这些名字加上 `[[deprecated]]`（[[depr.general#2]]）。本页的实测环境是 Clang 23.1.3 和 libc++。

## D.20 弃用的 locale 类别刻面 {#depr.locale.category}

```cpp
#include <locale>
using F = std::codecvt<char16_t, char, std::mbstate_t>;
auto& a = std::use_facet<F>(std::locale());  // 弃用
```

¶1–¶2 `ctype` locale 类别额外包含四个 `codecvt` 刻面和对应的四个 `codecvt_byname`：`char16_t` 和 `char32_t` 各与 `char`、`char8_t` 配对。**刻面**（facet）是 locale 中负责一类功能的对象，这里负责字符编码转换。

¶3 `char16_t` 的两个特化在 UTF-16 与 UTF-8 之间转换，`char32_t` 的两个在 UTF-32 与 UTF-8 之间转换。

`codecvt<char16_t, char, mbstate_t>` 把 `char` 序列硬性规定为 UTF-8，这和 `char` 在其他地方表示本地编码的含义冲突。C++20 引入 `char8_t` 时弃用了 `char` 的两个版本，换成 `char8_t` 版本（[[P0482R6]]）。后来 `char8_t` 版本也被认为不该加进 locale，同样被弃用（[[LWG3767]]）。整个 `codecvt` 接口基于 `mbstate_t`、需要从 locale 中取出、错误处理笨拙，不适合做 Unicode 转换。C++26 已经删除了 `<codecvt>` 头文件（[[P2871R3]]）。

libc++ 从 `-std=c++20` 起对 `char` 版本和 `char8_t` 版本都发出 `-Wdeprecated-declarations` 警告。

标准库目前没有通用的 Unicode 编码转换设施。实践中用第三方库（ICU、simdutf 等），或者自己写 UTF-8、UTF-16、UTF-32 之间的转换，它们只涉及位运算。

## D.21 `visit_format_arg` {#depr.format}

```cpp
#include <format>
void f(std::format_args a) {
  std::visit_format_arg([](auto) {}, a.get(0));  // 弃用
  a.get(0).visit([](auto) {});                   // C++26
}
```

### D.21.1 `<format>` 概要 {#depr.format.syn}

¶1 `<format>` 额外声明函数模板 `visit_format_arg(Visitor&& vis, basic_format_arg<Context> arg)`。

### D.21.2 格式化实参 {#depr.format.arg}

¶1 它的效果等价于 `return visit(std::forward<Visitor>(vis), arg.value_);`，其中 `value_` 是 `basic_format_arg` 内部仅用于说明的 `variant` 成员。

C++26 给 `basic_format_arg` 加了成员函数 `visit`，以及可以显式指定返回类型的 `visit<R>`，与同样新增的 `std::variant::visit` 成员保持一致（[[P2637R3]]）。自由函数 `visit_format_arg` 因此变得多余。

libc++ 在 `-std=c++2c` 下发出警告；`-std=c++20` 下没有警告，那时也还没有成员 `visit`。

## D.22 `asctime` 与 `ctime` {#depr.ctime}

```cpp
#include <ctime>
std::time_t t = 0;
char* s = std::ctime(&t);  // 弃用：s 指向共享的静态缓冲区
```

¶1 `<ctime>` 额外声明 `char* asctime(const tm* timeptr);` 和 `char* ctime(const time_t* timer);`。

¶2 这两个函数不要求避免数据竞争。标准库函数一般必须保证并发调用不会引入数据竞争（[[res.on.data.races]]），这里明确免除了这项保证。

它们返回指向静态缓冲区的指针，多个线程同时调用会互相覆盖结果；`asctime` 在年份超过四位数时还会溢出那个固定大小的缓冲区。C23 弃用了它们，C++ 随之把它们从正文的 `<ctime>`（[[ctime.syn]]）移到了这里。

libc++ 对它们不给警告。替代写法是 `std::format("{:%c}", std::chrono::system_clock::now())`（[[time.format]]），或者 C 的 `strftime`。

## D.23 弃用的文件系统设施 {#depr.filesystems}

### D.23.1 工厂函数 `u8path` {#depr.fs.path.factory}

```cpp
#include <filesystem>
auto p1 = std::filesystem::u8path("abc");  // 弃用
auto p2 = std::filesystem::path(u8"abc");  // 替代
```

¶1–¶2 `<filesystem>` 额外提供两个函数模板 `u8path(const Source&)` 和 `u8path(InputIterator, InputIterator)`，实参的值类型必须是 `char` 或 `char8_t`。¶3 前置条件是输入为 UTF-8 编码。

¶4 返回值的构造方式取决于平台：如果 `path::value_type` 是 `char` 且本地窄编码就是 UTF-8，直接构造 `path`；如果 `value_type` 是 `wchar_t` 且宽编码是 UTF-16（Windows），或者 `value_type` 是 `char16_t`、`char32_t`，先转换成 `path::string_type`；否则先转换成 `u32string`。¶5 规定 Unicode 转换的具体方式未指定。

C++17 中 `std::string` 无法表达这里是 UTF-8，只好用一个专门的工厂函数来说明编码。C++20 有了 `char8_t` 和 `std::u8string`，`path` 的构造函数可以从实参类型认出 UTF-8。¶6 的注说明，例子中的写法代表历史用法，现在更推荐把 `std::u8string` 直接传给 `path` 的构造函数。

libc++ 从 `-std=c++20` 起警告。手里是一个存着 UTF-8 的 `std::string` 时（例如从网络或数据库读来的），需要先转成 `char8_t` 序列：`std::u8string(s.begin(), s.end())`。这是 `char8_t` 方案公认的一处不便。

### D.23.2 返回 `std::string` 的格式观察函数 {#depr.fs.path.obs}

```cpp
#include <filesystem>
std::string s(const std::filesystem::path& p) {
  return p.string();  // 弃用
}
```

¶1 `path` 额外声明两个非模板成员 `std::string string() const;` 和 `std::string generic_string() const;`。¶2 前者返回 `native_encoded_string()`，¶3 后者返回 `generic_native_encoded_string()`。

正文的 `path`（[[fs.class.path]]）新增了 `native_encoded_string()`、`display_string()` 及其 `generic_` 版本，原来的非模板 `string()` 被移到这里（见 [[P2319R5]]）。正文仍保留模板版本 `string<EcharT, traits, Allocator>(const Allocator&)`，但它的 `EcharT` 没有默认值，也无法推导，所以不写模板实参的 `p.string()` 调用的正是这里被弃用的非模板版本。

`string()` 这个名字没有说明返回的是什么编码。在 POSIX 上它返回原始字节，文件名不一定是合法的 UTF-8；在 Windows 上它把 UTF-16 转换成当前代码页，可能丢字符。新接口按用途区分：

- `native_encoded_string()` 按本地窄编码转换，用于交给操作系统或 C API；
- `display_string()` 等于 `std::format("{}", path)`，用于显示，结果适合交给格式化和 `print` 函数。

libc++ 尚未实现新接口，`p.string()` 没有警告。要无损地取得文件名，用 `p.native()`（类型是 `path::string_type`）或 `p.u8string()`。

## D.25 和 D.26 `signed char`、`unsigned char` 的流输入输出

```cpp run ok
#include <cstdint>
#include <format>
#include <iostream>
#include <sstream>
int main() {
  std::uint8_t v = 65;
  std::cout << v << '\n';                   // 打印 A，不是 65
  std::cout << std::format("{}", v) << '\n';  // 打印 65
  std::istringstream in("42");
  std::uint8_t n;
  in >> n;                                  // 只读走字符 '4'
  std::cout << int(n) << '\n';              // 打印 52
}
```

`std::int8_t` 和 `std::uint8_t` 在主流平台上就是 `signed char` 和 `unsigned char` 的别名，而流把这两个类型当作字符处理。程序员想输出数值 65，得到的却是字母 `A`；想读入数值 42，读到的是字符 `'4'`，也就是 52。上例在 libc++ 上的输出正是 `A`、`65`、`52`。`std::format` 一开始就把这两个类型当整数格式化。

弃用这些重载，是为将来改变它们的行为或删除它们做准备。在那之前，代码应当写清意图：要字符就转换为 `char`，要数值就提升为 `int`（`+c` 或 `int(c)`）；读入数值时先读进 `int`，检查范围后再转换。

### D.25 提取 {#depr.istream.extractors}

¶1–¶3 `<istream>` 额外为 `basic_istream<char, traits>` 提供读入 `unsigned char&` 和 `signed char&` 的 `operator>>`。它是一个格式化输入函数，提取一个字符存入 `c`；没有可用字符时设置 `failbit`。

¶4–¶9 另外两个重载读入 `unsigned char (&)[N]` 和 `signed char (&)[N]`。设 `n` 为 `width()` 与 `N` 中较小的那个（`width()` 不大于 0 时取 `N`）。函数提取字符，直到存满 `n - 1` 个、遇到文件尾或遇到空白字符为止，然后存入一个空字节并调用 `width(0)`。一个字符都没有提取到时设置 `failbit`。

### D.26 插入 {#depr.ostream.inserters}

¶1–¶3 `<ostream>` 额外为 `basic_ostream<char, traits>` 提供输出 `signed char` 和 `unsigned char` 的 `operator<<`，等价于 `return out << static_cast<char>(c);`。

¶4–¶5 输出 `const signed char*` 和 `const unsigned char*` 的 `operator<<` 等价于 `return out << reinterpret_cast<const char*>(s);`，也就是当作空字符结尾的字符串输出。

libc++ 尚未给这两组重载加弃用标记，`-Wdeprecated` 下也没有警告。

## 小结

| 条款 | 特性 | 替代 | libc++ 警告 |
|---|---|---|---|
| D.20 | `codecvt<char16_t/char32_t, char/char8_t>` | 第三方库或手写转换 | C++20 起 |
| D.21 | `visit_format_arg` | `basic_format_arg::visit` | C++26 模式 |
| D.22 | `asctime`、`ctime` | `std::format` 加 `<chrono>`，`strftime` | 无 |
| D.23.1 | `u8path` | `path(std::u8string)` | C++20 起 |
| D.23.2 | 非模板 `path::string()`、`generic_string()` | `native_encoded_string()`、`display_string()` | 无（新接口未实现） |
| D.25、D.26 | `signed char`、`unsigned char` 的 `>>`、`<<` | 显式转换为 `char` 或 `int` | 无 |
