---
title: 格式化与操纵符
summary: <iomanip> 中带参数的操纵符（setw、setprecision、setfill、setbase、setiosflags、resetiosflags、get_time、put_money、quoted 等）的精确效果，以及 std::print、std::println 怎样写 C 的 FILE* 流。
status: done
covers: istream.syn, ostream.syn, iomanip.syn, print.syn, std.manip, ext.manip, quoted.manip, print.fun
related: input.streams, output.streams, iostreams.base, format, format.string, format.formatter, c.files, locale.categories, fs.class.path
tags: 标准库, iostream, 操纵符, iomanip, print
updated: 2026-10-19
---

!!! tldr
    - `out << std::setw(n)` 如同调用 `out.width(n)`。带参数操纵符的返回类型未指定，效果都是对流调用一个设置函数，返回流本身。
    - 这些设置一直有效，只有宽度例外：插入器用完一次就把它清零。`setw` 对字符串输入也有效，限制读入的字符数。
    - `setbase` 只认 8、10、16，其他值会清空进制标志：输出按十进制，输入按 `0x`、`0` 前缀自动识别进制。
    - `quoted` 给字符串加引号并转义，保证含空格、引号的字符串插入后能原样读回；`setw` 作用于加上引号后的整体。
    - `std::print(FILE*, ...)` 在编译期检查格式串，写失败时抛 `system_error`，持有流的锁一次写出；字面量编码是 UTF-8 时，在 Windows 控制台上改用原生 Unicode API。

标准的 [iostream.format] 一节规定了 `basic_istream`、`basic_ostream`、所有操纵符和 `std::print`。本站把它拆成三页：本页讲 `<iomanip>` 的操纵符和写 `FILE*` 的 `print`；`basic_istream` 见 [[input.streams]]，`basic_ostream`、`endl` 和写 `ostream` 的 `print` 见 [[output.streams]]。不带参数的操纵符（`hex`、`fixed`、`boolalpha` 等）在 [[iostreams.base]]。

## 带参数的操纵符 [std.manip]

```cpp title="setbase-zero.cpp" run ok
#include <iomanip>
#include <iostream>
#include <sstream>

int main() {
  std::istringstream in("0x1A 017 42");
  int a, b, c;
  in >> std::setbase(0) >> a >> b >> c;   // 按前缀识别进制
  std::cout << a << ' ' << b << ' ' << c << '\n';  // 26 15 42
  std::cout << std::setbase(2) << 5 << '\n';       // 5：按十进制
}
```

`setbase(0)` 和 `setbase(2)` 都不报错。¶4 规定 `setbase(base)` 的效果如同：

```cpp
str.setf(base ==  8 ? ios_base::oct :
         base == 10 ? ios_base::dec :
         base == 16 ? ios_base::hex :
         ios_base::fmtflags(0), ios_base::basefield);
```

也就是说 8、10、16 以外的值会把进制标志 `basefield` 全部清零。输出时 `basefield` 为 0 就按十进制。输入时 `basefield` 为 0，`num_get` 会像 C 的 `strtol(s, end, 0)` 一样按前缀识别进制：`0x` 是十六进制，`0` 开头是八进制（[[facet.num.get.virtuals]]）。`resetiosflags(std::ios_base::basefield)` 有同样的效果。

### 六个操纵符的统一模式

¶1 `<iomanip>` 中的这组函数都返回一个类型未指定的对象 `m`。`out << m` 的行为如同调用某个函数 `f(out, 参数)`，表达式的类型和值都是 `out` 本身；`in >> m` 同理。

| 操纵符 | `f` 做什么 | 用于输出 | 用于输入 |
|---|---|---|---|
| `resetiosflags(mask)` | ¶2 `str.setf(fmtflags(0), mask)`，清除 `mask` 中的标志 | 可以 | 可以 |
| `setiosflags(mask)` | ¶3 `str.setf(mask)` | 可以 | 可以 |
| `setbase(base)` | ¶4 见上 | 可以 | 可以 |
| `setfill(c)` | ¶5 `str.fill(c)`，`c` 的类型必须是流的字符类型 | 可以 | 不可以 |
| `setprecision(n)` | ¶6 `str.precision(n)` | 可以 | 可以 |
| `setw(n)` | ¶7 `str.width(n)` | 可以 | 可以 |

脚注举例说，`cin >> resetiosflags(ios_base::skipws)` 与 `cin >> noskipws` 效果相同。

这些设置都会一直保持，直到被再次修改。唯一的例外是宽度：字符串、字符和数值的插入器每用一次就调用 `width(0)`，所以 `setw` 只作用于下一次插入（[[output.streams]]）。

### `setw` 也能用于输入

```cpp title="setw-input.cpp" run ok
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

对输入流，宽度限制读入 `std::string`（[[string.io]]）和字符数组（[[input.streams]]）的最大字符数，用过一次同样被清零。

### 返回类型未指定意味着什么

`auto m = std::setw(5);` 是合法的，但写不出 `m` 的类型，也不能假设它能与 `<<`、`>>` 以外的东西组合。实现通常返回一个保存参数的小结构体，并为它重载 `<<`、`>>`。

`setfill` 的结构体是字符类型的模板，所以字符类型不匹配时重载决议直接失败：

```cpp title="setfill-wide.cpp"
#include <iomanip>
#include <iostream>

int main() {
  std::wcout << std::setfill('*');   // libc++ 报错：'*' 是 char
  std::wcout << std::setfill(L'*');  // OK
}
```

¶5 只规定了 `c` 的类型就是流的 `charT` 时的效果，对第一行没有规定任何行为。本机 libc++ 对它报 invalid operands，写出 `L'*'` 才是可移植的写法。

## 货币与时间 [ext.manip]

```cpp title="get-put-time.cpp" run ok
#include <ctime>
#include <iomanip>
#include <iostream>
#include <sstream>

int main() {
  std::tm t{};
  std::istringstream in("2026-10-18 09:30");
  in >> std::get_time(&t, "%Y-%m-%d %H:%M");
  if (!in) { std::cout << "parse failed\n"; return 1; }
  std::cout << std::put_time(&t, "%d/%m/%Y %H:%M") << '\n';
  // 18/10/2026 09:30
}
```

¶1 这四个操纵符解析和格式化货币值与时间值。它们把工作全部交给流的 locale 中对应的 facet（[[locale.categories]]），并通过 `istreambuf_iterator`、`ostreambuf_iterator` 直接读写流缓冲区。

| 操纵符 | 前提 | 效果 | 失败时 |
|---|---|---|---|
| `get_money(mon, intl)` | ¶2 `mon` 的类型是 `long double` 或某个 `basic_string` | ¶3–¶4 作为格式化输入函数，调用 `money_get::get` | 置 `get` 报告的错误位 |
| `put_money(mon, intl)` | ¶5 同上 | ¶6 作为格式化输出函数，调用 `money_put::put` | 置 `badbit` |
| `get_time(tmb, fmt)` | ¶7 `tmb` 指向有效的 `tm`，`fmt` 是以空字符结尾的格式串 | ¶8 调用 `time_get::get` | 置 `get` 报告的错误位 |
| `put_time(tmb, fmt)` | ¶9 同上 | ¶10 调用 `time_put::put` | 置 `badbit` |

`intl` 为真时用国际货币格式（如 `USD `），为假时用本地符号（如 `$`）。`fmt` 是 `strftime` 风格的格式串。新代码格式化时间更推荐 `<chrono>` 配合 `std::format`（[[time]]），它们类型安全，也不依赖 `tm`。

## `quoted`：字符串的往返 [quoted.manip]

```cpp title="quoted-roundtrip.cpp" run ok
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>

int main() {
  std::string in = R"(say "hi" \ bye)";

  std::stringstream plain;
  plain << in;
  std::string w;
  plain >> w;
  std::cout << w << '\n';            // say：>> 读到空白就停

  std::stringstream ss;
  ss << std::quoted(in);
  std::cout << ss.str() << '\n';     // "say \"hi\" \\ bye"
  std::string out;
  ss >> std::quoted(out);
  std::cout << (out == in) << '\n';  // 1：原样还原
}
```

普通的 `>>` 遇到空白就停止，所以含空格的字符串写进流再读回来会被截断。¶1 的注说明，`quoted` 就是为这种往返设计的，例如读写 XML、CSV 中带引号的字段。

### 输出（¶2）

¶2 `out << quoted(s, delim, escape)` 是一个格式化输出函数。`delim` 默认是 `"`，`escape` 默认是 `\`。它先构造字符序列 `seq`：

1. 一个 `delim`；
2. `s` 的每个字符，如果这个字符等于 `escape` 或 `delim`，前面先加一个 `escape`；
3. 一个 `delim`。

然后对整个 `seq` 按流的宽度填充，再调用 `width(0)`。所以 `setw` 作用于加上引号和转义之后的整体。接受 `const charT*`、`const basic_string&`、`basic_string_view` 的三个重载都可以用于输出。

### 输入（¶3）

¶3 只有接受非 const `basic_string&` 的重载能用于输入。`in >> quoted(s, delim, escape)` 先用 `in >> c` 提取一个字符，这一步照常跳过前导空白。

- ¶3.1.1 如果这个字符是 `delim`：暂时关闭 `skipws`，清空 `s`；逐个提取字符追加到 `s`，直到遇到没有转义的 `delim` 或流失败；遇到 `escape` 时丢掉它，把下一个字符原样追加；最后丢掉结尾的 `delim`，恢复 `skipws`。
- ¶3.1.2 否则等价于 `in >> s`，不带引号的输入按普通字符串读取。

`std::filesystem::path` 的 `<<` 和 `>>` 就是用 `quoted` 定义的（[[fs.class.path]]），所以 `std::cout << path` 会打印带引号的路径。

## `print` 与 `println` 写 C 流 [print.fun]

```cpp title="print-file.cpp" run ok
#include <cstdio>
#include <print>

int main() {
  std::print("{} {}\n", "to", "stdout");
  std::println(stderr, "error code {:#x}", 255);   // error code 0xff
  std::println();                                   // 只输出换行
  std::println("{:>6.2f}|{:<4}|{:^5}|", 3.14159, 'x', true);
  //   3.14|x   |true |
}
```

`<print>` 只依赖 C 的 `FILE*`，不需要 iostream。格式串的语法与 `std::format` 相同（[[format.string]]）。

### 各个函数之间的关系

- ¶1、¶3、¶4 不带 `FILE*` 的版本都写到 `stdout`。
- ¶5 `println(stream, fmt, args...)` 等价于在格式串末尾加一个 `'\n'` 再调用 `print`，换行与内容一起输出。¶6 `println(stream)` 只输出一个换行。
- ¶2 `print(stream, fmt, args...)` 在普通字面量编码（[[lex.charset]]）是 UTF-8 时调用 `vprint_unicode` 系列，否则调用 `vprint_nonunicode` 系列。

¶2 中还有一个选择：设 `locksafe` 为所有实参类型的 `enable_nonlocking_formatter_optimization` 的合取。`locksafe` 为真时直接调用 `vprint_unicode(stream, ...)`；否则调用 `vprint_unicode_buffered`。

¶8 `vprint_unicode_buffered` 先在不持锁的情况下 `vformat` 成一个 `string`，再把这个字符串交给 `vprint_unicode` 写出。区分这两条路径是因为 `vprint_unicode` 在持有流的锁期间格式化。如果某个实参的 `formatter` 很慢，或者自己也去写同一个流，持锁格式化会拖慢其他线程甚至死锁。`enable_nonlocking_formatter_optimization` 对用户类型默认为 `false`，所以用户类型默认走先格式化后加锁的路径（[[format.formatter]]）。¶14 `vprint_nonunicode_buffered` 同理。

### `vprint_unicode` 与 Windows 控制台（¶9–¶12）

¶9 前提是 `stream` 指向一个输出用的 C 流。

¶10 函数先锁住 `stream`，然后按 `fmt` 格式化 `args` 得到 `out`：

- ¶10.1 如果 `stream` 指向一个只能通过原生 Unicode API 显示 Unicode 的终端，先刷新 `stream`，再用原生 API 写出 `out`。`out` 含有无效码元时行为未定义 {{ub}}。写完后建立一个 [[g:observable-checkpoint|可观察检查点]]（[[intro.abstract]]）{{c++26}}。
- ¶10.2 否则把 `out` 原样写入 `stream`。

函数退出时无条件解锁。注 1 说明，在 Windows 上原生 Unicode API 是 `WriteConsoleW`，判断是否指向终端的方法是 `GetConsoleMode(_get_osfhandle(_fileno(stream)), ...)` 返回非零。

在 POSIX 系统上终端就是字节流，UTF-8 字节直接写出就能正确显示，两条路径没有区别。Windows 控制台则按当前代码页解释字节；代码页不是 UTF-8 时，直接写 UTF-8 字节会显示成乱码。`vprint_unicode` 检测到控制台后改用 `WriteConsoleW` 写 UTF-16，所以 `std::print("你好\n")` 在这种控制台上也能正确显示，`printf` 和 `cout` 则不能。

¶11 `vformat` 抛出的异常照常传出（[[format.err.report]]）；写终端或流失败时抛 `system_error`；还可能抛 `bad_alloc`。¶12 建议实现在转码时把无效码元替换为 U+FFFD。

¶15–¶17 `vprint_nonunicode(stream, ...)` 在持有锁时把格式化结果写入 `stream`，不检测终端，也不转码。异常规定相同。

### 与 `printf`、`cout` 的区别

- 错误报告：`print` 写失败时抛 `system_error`；`printf` 返回负值，`cout` 置 `badbit`。
- 格式检查：`print` 的格式串在编译期检查（[[format]]）；`printf` 的格式与实参不匹配是 {{ub}}，只能靠编译器警告发现。
- 原子性：`print(stdout, ...)` 持有流的锁写出整个结果，其他线程通过同一个 `FILE*` 的输出不会插进中间；`cout << a << b` 是多次独立调用。
- 与 `cout` 混用：`print` 写的是 `stdout`。在默认的同步状态下，它与 `cout` 的输出顺序一致；`sync_with_stdio(false)` 之后顺序没有保证（[[iostream.objects]]）。

!!! impl "libc++ 的现状"
    本机 libc++（Clang 23）提供 `std::print`、`std::println`，但 `__cpp_lib_print` 仍是 `202207L`，当前草案是 `202406L`。`<print>` 中没有 `vprint_unicode_buffered`、`vprint_nonunicode_buffered`，也就是还没有实现 `locksafe` 分派。在非 Windows 平台上，它的 `vprint_unicode` 直接写字节。

## 头文件一览 [istream.syn] [ostream.syn] [iomanip.syn] [print.syn]

- `<istream>` 声明 `basic_istream`（别名 `istream`、`wistream`）、`basic_iostream`（`iostream`、`wiostream`）、操纵符 `ws` 和右值流提取，见 [[input.streams]]。
- `<ostream>` 声明 `basic_ostream`（`ostream`、`wostream`）、操纵符 `endl`、`ends`、`flush`、为 [[syncstream]] 服务的 `emit_on_flush`、`noemit_on_flush`、`flush_emit`、右值流插入，以及只接受 `ostream&`（即 `char` 流）的 `print`、`println`、`vprint_unicode`、`vprint_nonunicode`，见 [[output.streams]]。
- `<iomanip>` 声明本页讲的全部带参数操纵符，返回类型都是未指定的。
- `<print>` 声明写 `FILE*` 的 `print`、`println` 和六个 `vprint_*` 函数。

## 思考题

!!! question "思考题 1"
    `std::cout << std::setw(10) << std::quoted("a b");` 输出几个字符？引号算不算在宽度里？

<details markdown="1">
<summary>答案</summary>

10 个。[[quoted.manip#2]] 规定先构造包含两端引号和转义字符的完整序列 `seq`，这里是 `"a b"`，共 5 个字符，再对整个 `seq` 按宽度填充。所以输出 5 个空格加 `"a b"`。
</details>

!!! question "思考题 2"
    `std::istringstream("  \"x y\" z") >> std::quoted(s)` 之后 `s` 是什么？流里还剩什么？

<details markdown="1">
<summary>答案</summary>

`s` 是 `x y`，流里剩下 ` z`。第一个字符用 `operator>>(istream&, char&)` 提取，这是格式化输入函数，会先跳过前导空白，得到 `"`。于是进入带引号模式，读到没有转义的 `"` 为止，并丢掉它（[[quoted.manip#3]]）。
</details>
