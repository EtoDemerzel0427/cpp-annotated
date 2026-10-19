---
title: 输出流 basic_ostream
summary: basic_ostream 怎样写出：sentry 在输出前刷新绑定的流、在输出后按 unitbuf 刷新，格式化输出的填充与 width 清零，数值插入器为什么失败置 badbit、hex 下负数为什么按无符号输出，被删除的字符插入器，print 写 ostream 的特殊规则，以及 put、write、flush 和 endl 等操纵符。
status: done
covers: *
related: iostream.format, iostreams.base, stream.buffers, input.streams, syncstream, format, facet.num.put.virtuals, depr.ostream.inserters, iostream.objects
tags: 标准库, iostream, ostream, 输出, sentry, endl
updated: 2026-10-19
---

!!! tldr
    - 每次输出都先构造 sentry：它刷新绑定的流；析构时如果开了 `unitbuf`（`cerr` 默认开着）就刷新本流，但栈展开期间不刷新。
    - 格式化输出按 `width()` 和 `fill()` 填充；`width` 用一次就被插入器清零，`fill`、`flags` 一直有效。
    - 数值由 `num_put` 生成。`hex`、`oct` 下 `int` 先转成同宽的无符号数，所以 `cout << hex << -1` 打印 `ffffffff`。写不进流缓冲区时置 `badbit`。
    - `cout << u8"x"`、`cout << L'x'` 等会选中被删除的重载，C++20 起是编译错误；`int8_t`、`uint8_t` 按字符打印；`const char*` 为空是 UB。
    - `std::print(os, ...)` 不看也不清零流的 `width`、`flags`；格式错误直接抛 `format_error`，不改变流状态。`endl` 是换行加刷新，大量输出时用 `'\n'`。

## 宽度只管一次

```cpp title="width-once.cpp" run ok
#include <iomanip>
#include <iostream>
#include <sstream>

int main() {
  std::ostringstream os;
  os << std::setw(6) << 1 << 2;            // width 只作用于第一个
  std::cout << '[' << os.str() << "]\n";   // [     12]
  std::cout << '[' << std::setw(5) << 'x' << "]["
            << std::left << std::setw(5) << "ab" << "]\n";
  // [    x][ab   ]
  std::cout << std::right << std::setfill('0') << std::internal
            << std::setw(7) << -42 << '\n';   // -000042
}
```

`setw(6)` 只让 `1` 被填充，紧接着的 `2` 照常输出；`left`、`setfill` 设置后则一直有效。要弄清这种差别，需要看格式化输出的公共规则。

## sentry：输出前后的固定步骤 [ostream.sentry]

`basic_ostream` 也有一个嵌套类 **sentry**（[[g:sentry]]），每个输出函数开始时构造它，结束时销毁它。

```cpp
class basic_ostream<charT, traits>::sentry {
  bool ok_;   // 仅用于说明
public:
  explicit sentry(basic_ostream& os);
  ~sentry();
  explicit operator bool() const { return ok_; }
  sentry(const sentry&) = delete;
  sentry& operator=(const sentry&) = delete;
};
```

¶2 构造函数：如果 `os.good()` 为真，就为输出做准备，其中包括：`os.tie()` 非空时调用 `os.tie()->flush()`。脚注说明，能判断不需要同步时可以省掉这次刷新。¶3 准备完成后 `ok_` 等于 `os.good()`。

与输入流的 sentry 不同，流不处于 good 状态时，输出 sentry 不会追加 `failbit`，只是让 `ok_` 为假。

¶4 析构函数：如果 `(os.flags() & ios_base::unitbuf) && !uncaught_exceptions() && os.good()` 为真，调用 `os.rdbuf()->pubsync()`。它返回 −1 或者抛出异常时，给流置 `badbit`，但不让异常传出去。

`unitbuf` 标志表示每次输出后都刷新，`cerr` 默认开着它，这个刷新就是在 sentry 的析构函数里完成的。条件中的 `!uncaught_exceptions()` 表示：如果输出函数正因为异常而退出（例如用户类型的 `operator<<` 抛了异常），sentry 在栈展开中析构，此时不刷新，避免在处理一个异常时再引出新的错误。

## 格式化输出 [ostream.formatted.reqmts]

`basic_ostream` 的成员分成两组（[[ostream.general#3]]）：[[g:formatted-output-function|格式化输出函数]]，又叫**插入器**（inserter），以及非格式化输出函数。两组都通过等价于 `rdbuf()->sputc()` 的动作写出字符。

[[ostream.general#3]] 还规定，它们除了 `overflow()`、`xsputn()`、`sync()` 之外不得调用流缓冲区的其他虚函数。所以自定义的输出流缓冲区只要实现好这三个，就能配合所有插入器（[[stream.buffers]]）。

¶1 格式化输出函数先构造 sentry，它为真时尽力生成输出：

- 生成失败时调用 `setstate(failbit)`，可能抛出异常。
- 输出中抛出异常时，给流置 `badbit`（这一步本身不会引发 `ios_base::failure`）；`exceptions()` 包含 `badbit` 时重新抛出这个异常。
- 不论有没有异常，离开函数前都销毁 sentry；没有异常时返回 `*this`。

[[ostream.general#4]] 补充了一条总规则：输出函数调用的其他函数抛出异常时，除非另有说明，置 `badbit`；`exceptions()` 包含 `badbit` 时立即重新抛出，否则当作被调用的函数返回了失败继续处理。

### 填充（¶3）

¶3 格式化输出函数确定填充时，如果字符序列的长度小于 `os.width()`，就补上若干个 `os.fill()`，使长度达到 `width()`。`adjustfield` 是 `left` 时填充字符放在后面，否则放在前面。

这一段只区分 `left` 和其他。`internal`（在符号或 `0x` 前缀与数字之间填充，如上例的 `-000042`）只对数值有意义，由 `num_put` 实现（[[facet.num.put.virtuals]]）。

公共规则里没有提到把宽度清零。是各个插入器在自己的规定里调用 `width(0)`：字符和字符串插入器、`quoted`，以及数值格式化用的 `num_put::do_put`。这就是 `setw` 只影响下一次插入，而 `fill`、`flags` 一直有效的原因。

### 自定义插入器与 `setw`

用户写的 `operator<<` 如果由多次插入拼成，`setw` 只会作用于第一次。要让宽度作用于整个值，先在一个临时流里格式化成字符串，再一次插入：

```cpp title="money-inserter.cpp" run ok
#include <iomanip>
#include <iostream>
#include <sstream>

struct Money { long cents; };

std::ostream& operator<<(std::ostream& os, Money m) {
  std::ostringstream tmp;                   // 在临时流里拼好
  tmp << m.cents / 100 << '.'
      << std::setw(2) << std::setfill('0') << m.cents % 100;
  return os << tmp.str();                   // 一次插入：width 作用于整体
}

int main() {
  std::cout << '[' << std::setw(8) << Money{1234} << "]\n";   // [   12.34]
}
```

## 数值插入器 [ostream.inserters.arithmetic]

```cpp title="hex-negative.cpp" run ok
#include <iostream>

int main() {
  std::cout << std::hex << -1 << ' '
            << static_cast<short>(-1) << '\n';   // ffffffff ffff
}
```

¶1 数值插入器用流的 locale 中的 `num_put` 生成字符。对 `bool`、`long`、`unsigned long`、`long long`、`unsigned long long`、`double`、`long double`、`const void*`，效果如同：

```cpp
bool failed = use_facet<num_put<charT, ostreambuf_iterator<charT, traits>>>(
  getloc()).put(*this, *this, fill(), val).failed();
```

其他类型先转换，再交给 `num_put`：

| `val` 的类型 | 传给 `num_put` 的值 |
|---|---|
| `short` | 进制是 `oct` 或 `hex` 时为 `long(static_cast<unsigned short>(val))`，否则 `long(val)` |
| `int` | 进制是 `oct` 或 `hex` 时为 `long(static_cast<unsigned int>(val))`，否则 `long(val)` |
| `unsigned short`、`unsigned int` | `static_cast<unsigned long>(val)` |
| `float` | `static_cast<double>(val)` |

所以在十六进制、八进制下，`int` 和 `short` 先转成同宽的无符号数，`-1` 就打印成 `ffffffff`、`ffff`，而不是 `-1`。

¶2 第一个实参是 `ostreambuf_iterator`，它绕过 `ostream`，直接写流缓冲区。`failed` 为真时调用 `setstate(badbit)`。这里置的是 `badbit` 而不是公共规则里的 `failbit`：`failed()` 为真意味着某次 `sputc` 返回了 `eof()`，也就是流缓冲区不再接收字符，这是 I/O 层的问题。

¶4 {{c++23}} `operator<<(const volatile void* p)` 等价于 `operator<<(const_cast<const void*>(p))`。C++23 之前没有这个重载，`volatile int*` 不能转换为 `const void*`，只能转换为 `bool`，于是打印 `1`：

```cpp title="volatile-pointer.cpp" run ok
#include <iostream>

int main() {
  volatile int vi = 0;
  std::cout << &vi << '\n';   // C++23 起打印地址；本机 -std=c++20 下打印 1
}
```

¶5 {{c++23}} 扩展浮点类型转成 `double` 或 `long double` 再输出；比 `long double` 还宽时，这个插入器是有条件支持的。

## 其他插入器 [ostream.inserters]

¶1–¶6 接受函数指针的三个 `operator<<` 不是格式化输出函数，只调用 `pf(*this)`。`endl`、`hex` 这类操纵符就是通过它们起作用的。

¶7–¶9 `out << sb`（`sb` 是 `basic_streambuf*`）表现为非格式化输出函数。`sb` 为空时置 `badbit`。否则从 `sb` 取字符插入 `*this`，直到 `sb` 到达流尾、插入失败，或从 `sb` 取字符时抛出异常。一个字符都没插入时置 `failbit`；取字符时抛出了异常也置 `failbit`，`exceptions()` 包含 `failbit` 时重新抛出。

`out << in.rdbuf()` 是把一个流的剩余内容整个复制到另一个流的惯用写法：

```cpp title="copy-rdbuf.cpp" run ok
#include <iostream>
#include <sstream>

int main() {
  std::istringstream in("line1\nline2\n");
  std::ostringstream out;
  out << in.rdbuf();
  std::cout << out.str().size() << '\n';   // 12

  std::istringstream empty("");
  std::ostringstream o2;
  o2 << empty.rdbuf();                     // 一个字符都没插入
  std::cout << o2.fail() << '\n';          // 1：failbit
}
```

¶11 {{c++17}} `out << nullptr` 输出一个由实现定义的字符串，本机 libc++ 输出 `nullptr`。

## 字符与字符串 [ostream.inserters.character]

¶1 单个字符的插入器是格式化输出函数：字符是 `char` 而流的字符类型不是 `char` 时，先用 `out.widen(c)` 加宽；然后按宽度填充、插入，最后调用 `width(0)`。

¶3–¶4 `const charT*`、`const char*` 的插入器先用 `traits::length(s)`（宽流接受 `const char*` 时用 `char_traits<char>::length(s)`）求出长度，逐个加宽，然后同样填充、插入、`width(0)`。前提是 `s` 不是空指针：

```cpp title="null-cstring.cpp" ub
#include <iostream>

int main() {
  const char* p = nullptr;
  std::cout << p << '\n';    // UB：违反前提，本机 libc++ 下段错误
}
```

### 被删除的重载

```cpp title="deleted-inserters.cpp" error
#include <iostream>

int main() {
  std::cout << u8"text";   // error: 选中被删除的重载
  std::cout << L'x';       // error: 同上
  std::cout << u"text";    // error: 同上
}
```

`char` 流对 `wchar_t`、`char8_t`、`char16_t`、`char32_t` 及其指针的插入器，以及 `wchar_t` 流对 `char8_t`、`char16_t`、`char32_t` 及其指针的插入器，都声明为 `= delete`。¶5 的注说明了目的：防止把字符按整数打印，把字符串按指针值打印。

C++20 之前，`std::cout << u'X'` 把字符提升为整数打印，`std::cout << u"text"` 打印的是指针值，而 `u8"text"` 当时的类型是 `const char[]`，可以正常打印。C++20 引入 `char8_t` 后，这些写法全部变成非良构（[[diff.cpp17.input.output]]）。

!!! pitfall "`int8_t`、`uint8_t` 按字符打印"
    ```cpp title="int8-print.cpp" run ok
    #include <cstdint>
    #include <iostream>

    int main() {
      std::int8_t a = 65;
      std::uint8_t b = 66;
      std::cout << a << ' ' << +a << ' ' << b << '\n';   // A 65 B
    }
    ```

    它们通常是 `signed char`、`unsigned char` 的别名，选中的插入器等价于 `out << static_cast<char>(c)`。一元 `+` 先做整型提升，得到 `int`，才按数字打印。当前草案把 `signed char`、`unsigned char` 及其指针的插入器移到了附录 D（[[depr.ostream.inserters]]），这是 C++23 之后的新措辞 {{deprecated}}。

## `print` 写 `ostream` [ostream.formatted.print]

```cpp title="print-ostream.cpp" run ok
#include <format>
#include <iomanip>
#include <iostream>
#include <ostream>
#include <sstream>

int main() {
  std::ostringstream os;
  os << std::setw(10) << std::hex;          // 对 print 没有影响
  std::print(os, "{}|{:x}", 255, 255);
  std::cout << '[' << os.str() << "]\n";    // [255|ff]
  std::cout << os.width() << '\n';          // 10：print 没有清零 width

  os.exceptions(std::ios_base::badbit);
  try {
    std::print(os, std::dynamic_format("{:d}"), "str");  // 运行期格式错误
  } catch (const std::format_error&) {
    std::cout << "format_error, bad=" << os.bad() << '\n'; // bad=0
  }
}
```

`<ostream>` 中的 `print`、`println` 只接受 `ostream&`，也就是 `char` 流。

- ¶1 `print(os, fmt, args...)`：普通字面量编码是 UTF-8 时调用 `vprint_unicode`，否则调用 `vprint_nonunicode`。
- ¶2 `println(os, fmt, args...)` 等价于 `print(os, "{}\n", format(os.getloc(), fmt, args...))`，先格式化成字符串，再加换行一起输出。¶3 `println(os)` 只输出换行。

¶4 `vprint_unicode(os, ...)` 和 `vprint_nonunicode(os, ...)` 表现为格式化输出函数，但有两处例外：

- ¶4.1 输出失败按下面的规定报告；
- ¶4.2 `vformat` 抛出的异常原样传出，不管 `os.exceptions()` 是什么，也不在 `os` 上置 `badbit`。

构造 sentry 之后，函数先执行 `string out = vformat(os.getloc(), fmt, args);`。¶4.3 如果是 `vprint_unicode`，且 `os` 指向只能通过原生 Unicode API 显示 Unicode 的终端（如何判断由实现定义），就先刷新 `os`，再用原生 API 写出 `out`；`out` 含无效码元时 {{ub}}；然后建立一个可观察检查点。¶4.4 否则把 `out` 的字符插入 `os`。写终端或插入失败时调用 `os.setstate(badbit)`。¶5 建议实现在转码时把无效码元替换为 U+FFFD。

由此可以得到三个结论：

1. 流的格式状态不影响 `print`。`width`、`flags`、`fill`、`precision` 都不参与，格式完全由格式串决定；只有 locale 参与，而且只对带 `L` 选项的替换域起作用。
2. `print` 不会把 `width` 清零。规定里没有调用 `width(0)`，之前设置的 `setw` 会留给下一次 `<<`。
3. 格式错误与 I/O 错误分开报告。`format_error` 直接抛出，流状态不变；I/O 失败走流的 `badbit` 和异常掩码。

写 `FILE*` 的版本见 [[iostream.format]]。

## 非格式化输出 [ostream.unformatted]

¶1 非格式化输出函数也先构造 sentry，为真时尽力生成输出。输出中抛出异常时置 `badbit`，`exceptions()` 包含 `badbit` 时重新抛出。它们不填充，不看 `width`，也不调用 `widen`。

- ¶2–¶3 `put(c)` 插入字符 `c`，不能插入时置 `badbit`。
- ¶5 `write(s, n)` 从 `s` 依次插入字符，直到插入了 `n` 个；某次插入失败时置 `badbit`。
- ¶7 `flush()`：`rdbuf()` 非空时构造 sentry，sentry 为真就调用 `rdbuf()->pubsync()`，它返回 −1 时置 `badbit`。

`put`、`write` 没有针对 `signed char`、`unsigned char` 的重载，脚注特意指出了这一点。

## 定位 [ostream.seeks]

¶1 定位函数也先构造 sentry。¶2 `tellp()` 在 `fail()` 为真时返回 `pos_type(-1)`，否则返回 `rdbuf()->pubseekoff(0, cur, out)`。¶3–¶6 `seekp(pos)`、`seekp(off, dir)` 在 `fail()` 为假时调用 `pubseekpos` 或 `pubseekoff`，失败时置 `failbit`。

## 输出操纵符 [ostream.manip]

| 操纵符 | 效果 |
|---|---|
| `endl` | ¶2 `os.put(os.widen('\n'))`，然后 `os.flush()` |
| `ends` | ¶4 `os.put(charT())`，插入一个空字符 |
| `flush` | ¶6 `os.flush()` |
| `emit_on_flush` | ¶8 `os.rdbuf()` 是 `basic_syncbuf` 时调用 `set_emit_on_sync(true)`，否则无效果 |
| `noemit_on_flush` | ¶10 同上，调用 `set_emit_on_sync(false)` |
| `flush_emit` | ¶12 先 `os.flush()`；`os.rdbuf()` 是 `basic_syncbuf` 时，再作为非格式化输出函数调用它的 `emit()`，返回 `false` 时置 `badbit` |

后三个操纵符的用途见 [[syncstream]]。判断 `rdbuf()` 是不是 `basic_syncbuf<charT, traits, Allocator>*` 需要知道 `Allocator`，而它无法从 `os` 推导出来。¶8 的注建议实现给 `basic_syncbuf` 加一个与分配器无关的中间基类，由它管理这个标志。

¶1 这些操纵符的每个实例化都是指定可寻址函数，程序可以取它们的地址。

!!! pitfall "`endl` 是换行加刷新"
    对写文件或管道的流，每行一次 `flush` 意味着每行一次 `sync()`，通常就是一次系统调用。大量输出时用 `'\n'` 代替 `std::endl`，让流缓冲区攒满再写，需要刷新的地方（进度提示、崩溃前的最后日志）再显式 `flush`。交互式输入前的提示也不需要 `endl`：`cin` 绑定了 `cout`，读输入前会自动刷新（[[iostream.objects]]）。

## 右值流插入 [ostream.rvalue]

```cpp
template<class Ostream, class T>
  Ostream&& operator<<(Ostream&& os, const T& x);
```

¶1 约束：`os << x` 良构，且 `Ostream` 公开、无歧义地派生自 `ios_base`。¶2–¶3 效果是执行 `os << x`，再返回 `std::move(os)`。

它让非成员的插入器（字符串、字符、用户类型）也能用于临时流对象，并且保留派生类型，所以可以写 `(std::ostringstream() << "id=" << 42).str()`。

## 构造与析构 [ostream.cons]

¶1–¶2 `basic_ostream(sb)` 用 `basic_ios::init(sb)` 初始化基类，之后 `rdbuf() == sb`。¶3 受保护的移动构造函数只移动 `basic_ios` 的状态；[ostream.assign] 中的移动赋值等价于 `swap`。

¶4 析构函数不对 `rdbuf()` 做任何操作，所以销毁一个 `ostream` 不会刷新。刷新由拥有流缓冲区的一方负责，例如 `~basic_filebuf` 调用 `close()`。

## 思考题

!!! question "思考题 1"
    用户类型的 `operator<<` 中途抛出异常，写到 `cerr`（开着 `unitbuf`）的那部分会被刷新吗？

<details markdown="1">
<summary>答案</summary>

外层的 sentry 只在 `!uncaught_exceptions()` 时才调用 `pubsync()`（[[ostream.sentry#4]]），它在栈展开中析构，不会刷新。不过，用户的 `operator<<` 内部调用的标准插入器各自构造并正常销毁了 sentry，那些插入器结束时已经各自刷新过，所以已经写出的部分通常已经刷新。
</details>

!!! question "思考题 2"
    `std::cout << std::setw(5); std::print(std::cout, "x"); std::cout << 'y';` 输出什么？

<details markdown="1">
<summary>答案</summary>

输出 `x    y`。`print` 不使用也不清零 `width`（[[ostream.formatted.print#4]] 只把格式化结果原样插入），宽度 5 留给了后面的 `'y'`，它被填充成 4 个空格加 `y`。
</details>

!!! question "思考题 3"
    数值插入器失败时置 `badbit`，而公共规则说生成失败置 `failbit`。两者矛盾吗？

<details markdown="1">
<summary>答案</summary>

不矛盾。公共规则是一般情形，数值插入器的规定（[[ostream.inserters.arithmetic#2]]）明确写了 `failed` 为真时置 `badbit`。`failed()` 为真只有一个原因：`ostreambuf_iterator` 写入时 `sputc` 返回了 `eof()`，即流缓冲区不再接收字符。这是 I/O 层的问题，不是无法把值格式化成字符，所以归为 `badbit`。`put`、`write` 失败同样置 `badbit`。
</details>

## 小结

| 函数 | sentry | 填充 / 清零 `width` | 失败时 |
|---|---|---|---|
| 数值 `<<` | 是 | 由 `num_put` 负责 | `badbit` |
| 字符、字符串 `<<` | 是 | 是 / 是 | `const char*` 为空是 UB |
| `<< streambuf*` | 是（非格式化） | 否 | 一个字符都没插入：`failbit`；`sb` 为空：`badbit` |
| 操纵符 `<<` | 否 | 否 | |
| `put`、`write` | 是 | 否 | `badbit` |
| `flush` | 是 | 否 | `pubsync` 返回 −1：`badbit` |
| `print(os, ...)` | 是 | 否 / 否 | 格式错误抛 `format_error`，不置位；I/O 失败置 `badbit` |
| sentry 析构 | | | `unitbuf` 且无未捕获异常时 `pubsync`，失败置 `badbit`，不抛出 |
