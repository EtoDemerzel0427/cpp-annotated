---
title: 格式化与操纵符
summary: [iostream.format] 导读与 <istream>/<ostream>/<iomanip>/<print> 的概要；带参数的操纵符 setw/setprecision/setfill/setbase/setiosflags/resetiosflags 的精确效果（setbase 非 8/10/16 时清空 basefield、输入时按前缀识别进制）、get_money/put_money/get_time/put_time、quoted 的往返语义，以及 std::print/println 写 FILE* 的规则（UTF-8 字面量编码、终端的原生 Unicode API、锁与 *_buffered 版本）
status: done
covers: istream.syn, ostream.syn, iomanip.syn, print.syn, std.manip, ext.manip, quoted.manip, print.fun
related: input.streams, output.streams, iostreams.base, format, format.string, format.formatter, c.files, locale.categories, fs.class.path
tags: 标准库, iostream, 操纵符, iomanip, print
updated: 2026-10-18
---

[iostream.format] 是本章最大的一节，规定了 `basic_istream`、`basic_ostream`、`basic_iostream` 以及所有操纵符和 `std::print`。本站把它拆成三页：

- 本页：四个头文件的概要、[std.manip]/[ext.manip]/[quoted.manip] 中带参数的操纵符、[print.fun] 中写 `FILE*` 的 `print`/`println`；
- [[input.streams]]：`basic_istream`、sentry、格式化与非格式化输入、`ws`、右值提取、`basic_iostream`；
- [[output.streams]]：`basic_ostream`、sentry、插入器、`put`/`write`/`flush`、`endl` 等操纵符、写 `ostream` 的 `print`。

无参数的格式操纵符（`hex`、`fixed`、`boolalpha`……）在 [[iostreams.base]]。

## 四个头文件的概要

### `<istream>`（[istream.syn]）

声明 `basic_istream`（别名 `istream`、`wistream`）、`basic_iostream`（`iostream`、`wiostream`）、操纵符 `ws`，以及右值流提取 `template<class Istream, class T> Istream&& operator>>(Istream&& is, T&& x)`。

### `<ostream>`（[ostream.syn]）

声明 `basic_ostream`（`ostream`、`wostream`）；操纵符 `endl`、`ends`、`flush`，以及为 [[syncstream]] 服务的 `emit_on_flush`、`noemit_on_flush`、`flush_emit`；右值流插入 `template<class Ostream, class T> Ostream&& operator<<(Ostream&& os, const T& x)`；以及**只针对 `ostream`（即 `char`）**的 `print`、`println`、`vprint_unicode`、`vprint_nonunicode`（[[ostream.formatted.print]]）。

### `<iomanip>`（[iomanip.syn]）

声明带参数的操纵符：`resetiosflags`、`setiosflags`、`setbase`、`setfill`、`setprecision`、`setw`（[std.manip]），`get_money`、`put_money`、`get_time`、`put_time`（[ext.manip]），以及四个 `quoted` 重载（[quoted.manip]）。它们的返回类型都是**未指定**的。

### `<print>`（[print.syn]）

```cpp
template<class... Args> void print(format_string<Args...> fmt, Args&&... args);
template<class... Args> void print(FILE* stream, format_string<Args...> fmt, Args&&... args);
template<class... Args> void println(format_string<Args...> fmt, Args&&... args);
void println();
template<class... Args> void println(FILE* stream, format_string<Args...> fmt, Args&&... args);
void println(FILE* stream);

void vprint_unicode(string_view fmt, format_args args);
void vprint_unicode(FILE* stream, string_view fmt, format_args args);
void vprint_unicode_buffered(FILE* stream, string_view fmt, format_args args);
void vprint_nonunicode(string_view fmt, format_args args);
void vprint_nonunicode(FILE* stream, string_view fmt, format_args args);
void vprint_nonunicode_buffered(FILE* stream, string_view fmt, format_args args);
```

`<print>` 只依赖 C 的 `FILE*`，不需要 iostream。

## 标准操纵符（[std.manip]）

¶1：`<iomanip>` 定义的这些函数支持修改 `ios_base` 及其派生类所维护信息的提取器和插入器。每个函数的 *Returns* 都是同一个模式：返回一个未指定类型的对象，使得 `out << m` 或 `in >> m` 的行为**如同**调用了某个函数 `f(out, ...)` / `f(in, ...)`，表达式的类型和值是 `out` / `in` 本身。

| 操纵符 | `f` 做什么 | 输出 | 输入 |
|---|---|---|---|
| `resetiosflags(mask)` | ¶2 `str.setf(fmtflags(0), mask)`，即清除 `mask` | ✓ | ✓ |
| `setiosflags(mask)` | ¶3 `str.setf(mask)` | ✓ | ✓ |
| `setbase(base)` | ¶4 `base` 为 8/10/16 时设为 `oct`/`dec`/`hex`，**否则清空** `basefield` | ✓ | ✓ |
| `setfill(c)` | ¶5 `str.fill(c)`，要求 `c` 的类型就是流的 `charT` | ✓ | ✗ |
| `setprecision(n)` | ¶6 `str.precision(n)` | ✓ | ✓ |
| `setw(n)` | ¶7 `str.width(n)` | ✓ | ✓ |

几个容易忽略的点：

- **`setbase` 的"其他值"不是报错，而是清空 `basefield`。** 输出时 `basefield` 为 0 就按十进制；输入时 `basefield` 为 0 则 `num_get` 按 C 的 `strtol(..., 0)` 规则**根据前缀自动识别进制**（`0x` 十六进制、`0` 八进制，[[facet.num.get.virtuals]]）。这是 iostream 中唯一能做前缀识别的方式。
- **`setw` 对输入也有效**：它限制提取到字符数组（[[istream.extractors]]）和 `std::string`（[[string.io]]）的最大字符数，并且用一次就被清零。
- **`setfill` 只用于输出**，而且字符类型必须与流匹配：`std::wcout << std::setfill('*')` 在 libc++ 上直接编译失败（`'*'` 是 `char`，标准只规定了 `c` 的类型为 `charT` 的情形）。
- 脚注说明 `cin >> resetiosflags(ios_base::skipws)` 与 `cin >> noskipws` 效果相同。

```cpp title="setbase-zero.cpp" ok
#include <iomanip>
#include <iostream>
#include <sstream>

int main() {
  std::istringstream in("0x1A 017 42");
  int a, b, c;
  in >> std::setbase(0) >> a >> b >> c;      // basefield 清零：按前缀识别进制
  std::cout << a << ' ' << b << ' ' << c << '\n';   // 26 15 42
  std::cout << std::setbase(2) << 5 << '\n';        // 5：2 不被支持，basefield 清零 → 十进制
}
```

```cpp title="setw-input.cpp" ok
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>

int main() {
  std::istringstream in("abcdefgh");
  std::string a, b;
  in >> std::setw(3) >> a >> b;     // setw 只作用于下一次提取
  std::cout << a << ' ' << b << '\n';   // abc defgh
}
```

!!! note "返回类型未指定意味着什么"
    `auto m = std::setw(5);` 是合法的，但你不能写出 `m` 的类型，也不能假设它可以与 `<<`/`>>` 之外的东西组合。实现通常返回一个保存参数的小结构体，并为它重载 `operator<<`/`operator>>`。对 `setfill` 来说，这个结构体是 `charT` 的模板，于是 `charT` 不匹配时重载决议直接失败（上面 `wcout` 的例子）。

## 扩展操纵符：货币与时间（[ext.manip]）

¶1：这些函数支持对货币和时间值的解析与格式化，全部委托给 `locale` 的相应 facet（[[locale.categories]]），并通过 `istreambuf_iterator`/`ostreambuf_iterator` 直接操作 streambuf。

| 操纵符 | 要求 | 等效操作 | 失败时 |
|---|---|---|---|
| `get_money(mon, intl)` | ¶2 *Mandates*：`moneyT` 是 `long double` 或 `basic_string` 特化 | ¶3–¶4 作为格式化输入函数，调用 `money_get::get` | `setstate(err)` |
| `put_money(mon, intl)` | ¶5 同上 | ¶6 作为格式化输出函数，调用 `money_put::put` | `setstate(badbit)` |
| `get_time(tmb, fmt)` | ¶7 *Preconditions*：`tmb` 指向有效的 `tm`，`fmt` 是有效范围 | ¶8 调用 `time_get::get(..., fmt, fmt + length)` | `setstate(err)` |
| `put_time(tmb, fmt)` | ¶9 同上 | ¶10 调用 `time_put::put(...)` | `setstate(badbit)` |

`intl` 为真时使用国际货币格式（如 `USD `），为假时用本地符号（如 `$`）。`fmt` 是 `strftime`/`strptime` 风格的格式串。

```cpp title="get-put-time.cpp" ok
#include <ctime>
#include <iomanip>
#include <iostream>
#include <sstream>

int main() {
  std::tm t{};
  std::istringstream in("2026-10-18 09:30");
  in >> std::get_time(&t, "%Y-%m-%d %H:%M");
  if (!in) { std::cout << "parse failed\n"; return 1; }
  std::cout << std::put_time(&t, "%d/%m/%Y %H:%M") << '\n';   // 18/10/2026 09:30
}
```

对于新代码，时间值的格式化更推荐 `<chrono>` 与 `std::format` 的组合（[[time]]）：类型安全、不依赖 `tm`。

## `quoted`（[quoted.manip]）

¶1（注）：`quoted` 用于带引号字符串的插入与提取（如 XML、CSV），保证含空格的字符串插入后再提取能**原样还原**。

**输出**（¶2，三个只读重载：`const charT*`、`const basic_string&`、`basic_string_view`）：表达式 `out << quoted(s, delim, escape)` 作为格式化输出函数，构造字符序列 `seq`：

1. `delim`（默认 `"`）；
2. `s` 的每个字符——若它等于 `escape`（默认 `\`）或 `delim`，先输出一个 `escape`；
3. `delim`。

然后对**整个** `seq` 按 [[ostream.formatted.reqmts]] 做填充，即 `setw` 作用于加上引号后的整体，最后调用 `width(0)`。

**输入**（¶3，只有 `basic_string&` 重载）：`in >> quoted(s, delim, escape)`：

- ¶3.1.1：若提取的第一个字符等于 `delim`：关闭 `skipws`；`s.clear()`；逐个提取字符追加到 `s`，直到遇到**未转义**的 `delim` 或流失败，其中遇到 `escape` 就丢弃它、把下一个字符原样追加；丢弃结尾的 `delim`；恢复 `skipws` 原值。
- ¶3.1.2：否则，等价于 `in >> s`——也就是说，不带引号的输入按普通字符串提取。
- 第一个字符是用 `operator>>(basic_istream&, charT&)` 提取的，所以前导空白照常被跳过。

```cpp title="quoted-roundtrip.cpp" ok
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>

int main() {
  std::stringstream ss;
  std::string in = R"(say "hi" \ bye)";
  ss << std::quoted(in);
  std::cout << ss.str() << '\n';         // "say \"hi\" \\ bye"

  std::string out;
  ss >> std::quoted(out);
  std::cout << (out == in) << '\n';      // 1：往返后完全还原

  std::stringstream plain;
  plain << in;
  std::string w;
  plain >> w;
  std::cout << w << '\n';                // say：普通 >> 只读到第一个空白
}
```

`std::filesystem::path` 的 `operator<<` 和 `operator>>` 就是用 `quoted` 定义的（[[fs.class.path]]），所以 `std::cout << path` 会打印出带引号的路径。

## `print`/`println` 写 C 流（[print.fun]）

### 转发关系（¶1–¶8、¶13–¶14）

- `print(fmt, args...)` → `print(stdout, fmt, args...)`（¶1）；`println(fmt, args...)` → `println(stdout, ...)`（¶3）；`println()` → `println(stdout)`（¶4）。
- `println(stream, fmt, args...)`（¶5）：等价于 `print(stream, dynamic_format(string(fmt.get()) + '\n'), args...)`——在格式串末尾加一个换行，作为整体输出。`println(stream)`（¶6）等价于 `print(stream, "\n")`。
- `print(stream, fmt, args...)`（¶2）：设 `locksafe` 为 `(enable_nonlocking_formatter_optimization<remove_cvref_t<Args>> && ...)`。若**普通字面量编码**（[[lex.charset]]）是 UTF-8，调用 `locksafe ? vprint_unicode(...) : vprint_unicode_buffered(...)`；否则调用对应的 `nonunicode` 版本。
- `vprint_unicode_buffered(stream, fmt, args)`（¶8）：先 `string out = vformat(fmt, args);`，再 `vprint_unicode(stream, "{}", make_format_args(out))`。`nonunicode` 版同理（¶14）。

`locksafe` 与 `*_buffered` 的分工：`vprint_unicode(FILE*, ...)` 在**持有流的锁**期间完成格式化和写出；若某个实参的 `formatter` 可能做耗时操作或自己去打印（导致死锁），就应先在锁外把结果格式化成字符串，再加锁写出——这正是 `*_buffered` 的作用。`enable_nonlocking_formatter_optimization` 默认对用户类型为 `false`，规则详见 [[format.formatter]]。

### `vprint_unicode(FILE*, ...)`（¶9–¶12）

- ¶9 前置条件：`stream` 是指向输出 C 流的有效指针。
- ¶10 *Effects*：**锁住** `stream`。设 `out` 为按 `fmt` 格式化 `args` 得到的字符表示：
    - ¶10.1 若 `stream` 指向一个**只能通过原生 Unicode API 显示 Unicode 的终端**，则先刷新 `stream`，再用原生 Unicode API 写出 `out`；若 `out` 含有无效码元，行为未定义 {{ub}}。然后建立一个可观察检查点（observable checkpoint，[[intro.abstract#5]]）{{c++26}}。
    - ¶10.2 否则把 `out` 原样写入 `stream`。
    - 函数退出时无条件解锁。注：在 Windows 上，原生 Unicode API 是 `WriteConsoleW`，判断"指向终端"的方法是 `GetConsoleMode(_get_osfhandle(_fileno(stream)), ...)` 返回非零。
- ¶11 *Throws*：`vformat` 抛出的任何异常（[[format.err.report]]）；写终端或流失败时抛 `system_error`；可能抛 `bad_alloc`。
- ¶12 *Recommended practice*：调用原生 API 需要转码时，应按 Unicode 标准把无效码元替换为 U+FFFD。

`vprint_nonunicode(FILE*, ...)`（¶15–¶17）：在持有 `stream` 锁的情况下把格式化结果写入 `stream`，不做任何终端检测或转码；异常规定相同。

为什么要区分？在 POSIX 上终端就是字节流，UTF-8 字节直接写出就能正确显示，两者没有区别。在 Windows 控制台上，按字节写 UTF-8 会按当前代码页解释、显示乱码；`vprint_unicode` 检测到控制台后改用 `WriteConsoleW` 输出 UTF-16。这就是 `std::print("你好\n")` 在 Windows 控制台上能正确显示、而 `printf`/`cout` 不能的原因。

```cpp title="print-file.cpp" ok
#include <cstdio>
#include <print>

int main() {
  std::print("{} {}\n", "to", "stdout");
  std::println(stderr, "error code {:#x}", 255);           // error code 0xff
  std::println();                                           // 只输出换行
  std::println("{:>6.2f}|{:<4}|{:^5}|", 3.14159, 'x', true); //   3.14|x   |true |
}
```

!!! note "与 `printf`、`cout` 的对比"
    - **错误报告**：`print` 写失败时**抛 `system_error`**；`printf` 返回负值，`cout` 置 `badbit`。
    - **格式检查**：`print` 的格式串在编译期检查（[[format]]）；`printf` 的不匹配是 {{ub}}，只有编译器警告。
    - **原子性**：`print(stdout, ...)` 在持锁期间一次写出整个结果，多线程下一次调用的输出不会被别的 `print`/`printf` 拆开；`cout << a << b` 是多次独立调用。
    - **与 `cout` 混用**：`print` 写的是 `stdout`。在默认同步状态下与 `cout` 的顺序一致；`sync_with_stdio(false)` 之后两者顺序无保证（[[iostream.objects]]）。

!!! impl "libc++ 的现状"
    本机 libc++（Clang 23）提供 `std::print`/`println`（`__cpp_lib_print` 为 `202207L`），在非 Windows 平台上 `vprint_unicode` 直接转发给 `fwrite`。`<print>` 中**没有**声明 `vprint_unicode_buffered`/`vprint_nonunicode_buffered`，也就是还没有实现 C++26 引入的 `locksafe` 分派；`print(ostream&, ...)` 见 [[output.streams]]。

## 思考题

<details markdown="1">
<summary>1. <code>std::cout &lt;&lt; std::setw(10) &lt;&lt; std::quoted("a b");</code> 输出几个字符？引号算不算在宽度里？</summary>

10 个。[[quoted.manip#2]] 规定先构造包含两端 `delim` 和转义字符的完整序列 `seq`（这里是 `"a b"`，5 个字符），**再**对整个 `seq` 按 `width()` 填充，所以输出 5 个填充字符加 `"a b"`。
</details>

<details markdown="1">
<summary>2. <code>std::istringstream("  \"x y\" z") &gt;&gt; std::quoted(s)</code> 之后 <code>s</code> 是什么？流里还剩什么？</summary>

`s == "x y"`，流里剩下 `" z"`。第一个字符通过 `operator>>(istream&, char&)` 提取，它是格式化输入函数，会先跳过前导空白，得到 `"`；于是进入带引号模式，读到未转义的 `"` 为止并丢弃它（[[quoted.manip#3]]）。
</details>

## 小结

- 带参数操纵符的返回类型未指定，效果都是"如同调用某个 `f(stream, arg)`"；除 `width` 外，它们设置的状态都会一直保持。
- `setbase(x)` 中 `x` 不是 8/10/16 会清空 `basefield`：输出十进制、输入按前缀识别。
- `quoted` 让含空格和引号的字符串可以安全往返；`setw` 作用于加上引号后的整体。
- `std::print` 写 `FILE*`：编译期检查格式串、失败抛 `system_error`、持锁一次写出；字面量编码为 UTF-8 时在 Windows 控制台上改用原生 Unicode API。
