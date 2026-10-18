---
title: 输出流 basic_ostream
summary: basic_ostream 的全部规则——sentry 构造时刷新 tie、析构时在 unitbuf 下 pubsync（栈展开期间不刷新），格式化输出的填充规则（只有 width 在用后清零），算术插入器借 num_put 生成、失败置 badbit，hex 下负数按无符号输出，字符与字符串插入器（const char* 不得为空、char8_t/char16_t/char32_t/wchar_t 的重载被删除），print/println 写 ostream 的特殊错误规则，put/write/flush、endl/ends/flush 与 emit_on_flush 系列，以及右值流插入
status: done
covers: *
related: iostream.format, iostreams.base, stream.buffers, input.streams, syncstream, format, facet.num.put.virtuals, depr.ostream.inserters, iostream.objects
tags: 标准库, iostream, ostream, 输出, sentry, endl
updated: 2026-10-18
---

[output.streams] 规定 `<ostream>` 中的 `basic_ostream`、标准输出操纵符、右值插入以及写 `ostream` 的 `print`。结构与 [[input.streams]] 对称：一个 sentry、一段"格式化输出的公共要求"、一段"非格式化输出的公共要求"，再加各个具体函数。

## 概述（[output.streams.general]、[ostream.general]）

[output.streams.general] ¶1：`<ostream>` 定义一个类模板和若干函数模板，控制向流缓冲区的输出，并提供向流右值插入的函数模板。

[ostream.general] ¶1：参数类型为 *extended-floating-point-type* 的函数，实现要为每个无 cv 限定的扩展浮点类型提供重载 {{c++23}}。

```cpp
template<class charT, class traits = char_traits<charT>>
class basic_ostream : virtual public basic_ios<charT, traits> {
public:
  explicit basic_ostream(basic_streambuf<char_type, traits>* sb);
  virtual ~basic_ostream();
  class sentry;

  // 格式化输出（插入器）
  basic_ostream& operator<<(basic_ostream& (*pf)(basic_ostream&));     // 操纵符
  basic_ostream& operator<<(basic_ios<charT, traits>& (*pf)(basic_ios<charT, traits>&));
  basic_ostream& operator<<(ios_base& (*pf)(ios_base&));
  basic_ostream& operator<<(bool / short / ... / long double / extended-floating-point-type);
  basic_ostream& operator<<(const void* p);
  basic_ostream& operator<<(const volatile void* p);                    // C++23
  basic_ostream& operator<<(nullptr_t);                                 // C++17
  basic_ostream& operator<<(basic_streambuf<char_type, traits>* sb);

  // 非格式化输出
  basic_ostream& put(char_type c);
  basic_ostream& write(const char_type* s, streamsize n);
  basic_ostream& flush();

  pos_type tellp();
  basic_ostream& seekp(pos_type);
  basic_ostream& seekp(off_type, ios_base::seekdir);
protected:
  basic_ostream(basic_ostream&& rhs);
  basic_ostream& operator=(basic_ostream&& rhs);
  void swap(basic_ostream& rhs);
};
// 非成员字符插入器：charT、char、const charT*、const char*；
// 以及一组 = delete 的重载（见下文）
```

¶2–¶3：成员分为**格式化输出函数**（又称**插入器**，[[g:formatted-output-function]]）和**非格式化输出函数**。两组都通过等价于调用 `rdbuf()->sputc(int_type)` 的动作生成（"插入"）字符；它们可以使用 `basic_ostream` 的其他公有成员，但**除了 `overflow()`、`xsputn()`、`sync()` 之外不得调用 `rdbuf()` 的任何虚成员**——这是自定义输出 streambuf 只需实现这三个虚函数的依据（[[stream.buffers]]）。

¶4：若这些被调用的函数抛出异常，除非另有说明，输出函数置 `badbit`；若 `badbit` 在 `exceptions()` 中，则不完成动作直接重新抛出，否则不抛任何东西、按被调函数"返回了失败"继续处理。

¶5（注）：被删除的 `operator<<` 重载用于防止把字符格式化成整数、把字符串格式化成指针。

## 构造、赋值、析构（[ostream.cons]、[ostream.assign]）

- `explicit basic_ostream(sb)`：¶1 `basic_ios::init(sb)`；¶2 后条件 `rdbuf() == sb`。
- 移动构造（受保护）：¶3 默认构造基类，再调用 `basic_ios::move(rhs)`。
- 析构函数：¶4 不对 `rdbuf()` 做任何操作——**析构 `ostream` 不会刷新**；刷新由拥有 streambuf 的一方负责（如 `~basic_filebuf` 调用 `close()`）。
- `operator=(&&)` 等价于 `swap(rhs)`；`swap` 调用 `basic_ios::swap(rhs)`。

## sentry（[ostream.sentry]）

```cpp
class basic_ostream<charT, traits>::sentry {
  bool ok_;   // 说明专用
public:
  explicit sentry(basic_ostream& os);
  ~sentry();
  explicit operator bool() const { return ok_; }
  sentry(const sentry&) = delete;
  sentry& operator=(const sentry&) = delete;
};
```

- ¶2 构造函数：若 `os.good()` 非零，为输出做准备；若 `os.tie()` 非空，调用 `os.tie()->flush()`（脚注：如果函数能判断不需要同步，这次调用不一定发生）。
- ¶3：准备完成后，`ok_` 等于 `os.good()`；准备期间可能调用 `setstate(failbit)`。
- ¶4 **析构函数**：若 `(os.flags() & ios_base::unitbuf) && !uncaught_exceptions() && os.good()` 为真，调用 `os.rdbuf()->pubsync()`；若它返回 −1 或以异常退出，在 `os.rdstate()` 中置 `badbit` 但**不传播异常**。

与输入 sentry 的区别：输出 sentry 在流不 `good()` 时**不**追加 `failbit`，只是让 `ok_` 为假。

析构函数里的 `!uncaught_exceptions()` 条件很关键：如果插入器因为异常而退出（例如用户类型的 `operator<<` 抛了），sentry 在栈展开期间析构，此时不刷新——避免在处理一个异常的过程中因为刷新失败而引出第二个问题。`unitbuf`（`cerr` 默认开启）的"每次输出后刷新"就是靠这个析构函数实现的。

## 定位（[ostream.seeks]）

¶1：每个 seek 成员先构造 sentry，返回前销毁它。

- `tellp()`：¶2 若 `fail()` 为真返回 `pos_type(-1)`，否则返回 `rdbuf()->pubseekoff(0, cur, out)`。
- `seekp(pos)` / `seekp(off, dir)`：¶3–¶6 若 `fail()` 不为真，调用 `rdbuf()->pubseekpos(pos, out)` / `pubseekoff(off, dir, out)`；失败时 `setstate(failbit)`。

## 格式化输出的公共要求（[ostream.formatted.reqmts]）

¶1：每个格式化输出函数先构造 sentry；若它转换为 `true`，就尽力生成所请求的输出。**生成失败时调用 `setstate(failbit)`**（可能抛异常）。若输出过程中抛出异常，在 `*this` 的错误状态中置 `badbit`（脚注：这样做本身不会导致抛出 `ios_base::failure`），若 `(exceptions() & badbit) != 0` 则重新抛出。无论是否有异常，sentry 都在离开函数前销毁；没有异常时返回 `*this`。¶2：各个函数的描述只讲如何输出，不再提 sentry。

¶3 **填充规则**：格式化输出函数确定填充时，给定字符序列 `seq`，若其长度小于 `os.width()`，就添加足够多的 `os.fill()` 使长度达到 `width()`；若 `(flags() & adjustfield) == left`，填充字符放在序列**之后**，否则放在**之前**。

注意 ¶3 只区分"left"和"其他"。`internal`（在符号/前缀与数字之间填充）只对数值有意义，由 `num_put` 实现（[[facet.num.put.virtuals]]），不在这一段里。

**`width` 为什么会被清零？** 公共要求里没有提到 `width(0)`；是各个具体插入器在各自的描述里规定"调用 `width(0)`"——字符和字符串插入器（[[ostream.inserters.character]]）、`quoted`、以及 `num_put::do_put`。所以 `setw` 只影响下一次插入，而 `fill`、`flags` 一直有效。

```cpp title="width-once.cpp" ok
#include <iomanip>
#include <iostream>
#include <sstream>

int main() {
  std::ostringstream os;
  os << std::setw(6) << 1 << 2;                  // width 只作用于第一个
  std::cout << '[' << os.str() << "]\n";         // [     12]
  std::cout << '[' << std::setw(5) << 'x' << "][" << std::left << std::setw(5) << "ab" << "]\n";
  // [    x][ab   ]
  std::cout << std::right << std::setfill('0') << std::internal << std::setw(7) << -42 << '\n';
  // -000042
}
```

### 自定义插入器与 `setw`

如果用户的 `operator<<` 由多次插入拼成，`setw` 只会作用于其中第一次。要让宽度作用于整个值，先格式化成字符串再一次插入：

```cpp title="money-inserter.cpp" ok
#include <iomanip>
#include <iostream>
#include <sstream>

struct Money { long cents; };

std::ostream& operator<<(std::ostream& os, Money m) {
  std::ostringstream tmp;                        // 在临时流里拼好
  tmp << m.cents / 100 << '.' << std::setw(2) << std::setfill('0') << m.cents % 100;
  return os << tmp.str();                        // 一次插入：width 作用于整体
}

int main() {
  std::cout << '[' << std::setw(8) << Money{1234} << "]\n";   // [   12.34]
}
```

## 算术插入器（[ostream.inserters.arithmetic]）

¶1：`num_get`/`num_put` 负责依赖 locale 的数值解析与格式化；这些插入器用流 imbue 的 locale 进行格式化。对 `bool`、`long`、`unsigned long`、`long long`、`unsigned long long`、`double`、`long double`、`const void*`，转换如同：

```cpp
bool failed = use_facet<num_put<charT, ostreambuf_iterator<charT, traits>>>(
  getloc()).put(*this, *this, fill(), val).failed();
```

其他类型先转换再调用：

| `val` 的类型 | 传给 `num_put` 的值 |
|---|---|
| `short` | `basefield` 是 `oct` 或 `hex` 时为 `long(static_cast<unsigned short>(val))`，否则 `long(val)` |
| `int` | `basefield` 是 `oct` 或 `hex` 时为 `long(static_cast<unsigned int>(val))`，否则 `long(val)` |
| `unsigned short`、`unsigned int` | `static_cast<unsigned long>(val)` |
| `float` | `static_cast<double>(val)` |

这就是 `std::cout << std::hex << -1` 打印 `ffffffff` 而不是 `-1` 的原因：十六进制/八进制时，`int` 先被转成同宽度的无符号数。

```cpp title="hex-negative.cpp" ok
#include <iostream>

int main() {
  std::cout << std::hex << -1 << ' ' << static_cast<short>(-1) << '\n';   // ffffffff ffff
}
```

¶2：第一个实参是 `ostreambuf_iterator`，**绕过 ostream、直接写 streambuf**；第二个实参是 `ios_base` 子对象的引用，提供宽度等格式规格和用于获取其他 facet 的 locale。**若 `failed` 为真，调用 `setstate(badbit)`**——注意是 `badbit` 而不是公共要求里的 `failbit`：`ostreambuf_iterator::failed()` 为真意味着底层 `sputc` 返回了 `eof()`，即 streambuf 写不进去了。

- `operator<<(const volatile void* p)` {{c++23}}：¶4 等价于 `operator<<(const_cast<const void*>(p))`。C++23 之前没有这个重载，`volatile int*` 只能隐式转换为 `bool`，于是打印 `1`：

```cpp title="volatile-pointer.cpp" ok
#include <iostream>

int main() {
  volatile int vi = 0;
  std::cout << &vi << '\n';   // C++23 起打印地址；在 -std=c++20 下本机 libc++ 打印 1
}
```

- 扩展浮点类型（¶5）：转换等级不高于 `double` 的转换为 `double`，不高于 `long double` 的转换为 `long double`；更高的则调用是有条件支持的、语义由实现定义。

## 其他插入器（[ostream.inserters]）

- 三个操纵符重载（¶1–¶6）：**不是**格式化输出函数，只调用 `pf(*this)`。脚注举例 `endl(basic_ostream&)` 和 `dec(ios_base&)`。
- `operator<<(basic_streambuf* sb)`（¶7–¶10）：表现为**非格式化**输出函数。`sb` 为空则 `setstate(badbit)`。否则从 `sb` 获取字符插入 `*this`，直到：输入序列到达文件尾；插入失败（该字符不被提取）；从 `sb` 获取字符时发生异常。一个字符都没插入则调用 `setstate(failbit)`；若是提取时发生异常，置 `failbit`，且 `failbit` 在 `exceptions()` 中时重新抛出捕获的异常。
- `operator<<(nullptr_t)` {{c++17}}：¶11 等价于 `return *this << s;`，其中 `s` 是实现定义的 NTCTS。本机 libc++ 打印 `nullptr`。

`out << in.rdbuf()` 是"把一个流剩余的全部内容复制到另一个流"的惯用法，比逐行读写快得多：

```cpp title="copy-rdbuf.cpp" ok
#include <iostream>
#include <sstream>

int main() {
  std::istringstream in("line1\nline2\n");
  std::ostringstream out;
  out << in.rdbuf();
  std::cout << out.str().size() << '\n';   // 12

  std::istringstream empty("");
  std::ostringstream o2;
  o2 << empty.rdbuf();                     // 一个字符都没插入 → failbit
  std::cout << o2.fail() << '\n';          // 1
}
```

## 字符与字符串插入器（[ostream.inserters.character]）

### 单个字符（¶1–¶2）

```cpp
template<class charT, class traits> basic_ostream<charT, traits>& operator<<(basic_ostream<charT, traits>&, charT);
template<class charT, class traits> basic_ostream<charT, traits>& operator<<(basic_ostream<charT, traits>&, char);
template<class traits>              basic_ostream<char, traits>&  operator<<(basic_ostream<char, traits>&, char);
```

作为格式化输出函数：构造序列 `seq`——若 `c` 是 `char` 而流的字符类型不是 `char`，`seq` 是 `out.widen(c)`，否则就是 `c`；按 ¶3 的规则填充；插入；调用 `width(0)`。

### 字符串（¶3–¶5）

`const charT*`、`const char*` 两组重载：¶3 **前置条件：`s` 不是空指针**；¶4 构造 `n` 个字符的序列（每个用 `out.widen()` 加宽），`n` 由 `traits::length(s)`（或宽流接受 `const char*` 时由 `char_traits<char>::length(s)`）求得；填充；插入；`width(0)`。

```cpp title="null-cstring.cpp" ub
#include <iostream>

int main() {
  const char* p = nullptr;
  std::cout << p << '\n';    // UB：违反前置条件，本机 libc++ 下段错误
}
```

### 被删除的重载

```cpp
// basic_ostream<char, traits>&  <<  wchar_t / char8_t / char16_t / char32_t            = delete;
// basic_ostream<char, traits>&  <<  const wchar_t* / const char8_t* / const char16_t* / const char32_t* = delete;
// basic_ostream<wchar_t, traits>& << char8_t / char16_t / char32_t 及其指针            = delete;
```

C++20 之前，`std::cout << u8"text"` 选中 `const char*` 重载（`u8` 字面量当时是 `const char[]`），而 `std::cout << u'X'` 会把字符**提升为整数**打印、`std::cout << u"text"` 打印**指针值**。C++20 引入 `char8_t` 后，这些调用全部变成非良构（[[diff.cpp17.input.output]]）：

```cpp title="deleted-inserters.cpp" error
#include <iostream>

int main() {
  std::cout << u8"text";   // error: 选中了被删除的重载
  std::cout << L'x';       // error: 同上
  std::cout << u"text";    // error: 同上
}
```

### 已弃用：`signed char`/`unsigned char` {{deprecated}}

`operator<<(basic_ostream<char, traits>&, signed char)` / `unsigned char` 及其指针版本已移入附录 D（[[depr.ostream.inserters]]），效果分别等价于 `out << static_cast<char>(c)` 和 `out << reinterpret_cast<const char*>(s)`。这是 C++23 之后的新措辞。它们就是 `std::int8_t`/`std::uint8_t` 被打印成字符的原因：

```cpp title="int8-print.cpp" ok
#include <cstdint>
#include <iostream>

int main() {
  std::int8_t a = 65;
  std::uint8_t b = 66;
  std::cout << a << ' ' << +a << ' ' << b << '\n';   // A 65 B：一元 + 先做整型提升
}
```

## `print`/`println` 写 `ostream`（[ostream.formatted.print]）

```cpp
template<class... Args> void print(ostream& os, format_string<Args...> fmt, Args&&... args);
template<class... Args> void println(ostream& os, format_string<Args...> fmt, Args&&... args);
void println(ostream& os);
void vprint_unicode(ostream& os, string_view fmt, format_args args);
void vprint_nonunicode(ostream& os, string_view fmt, format_args args);
```

注意参数是 `ostream&`，即只支持 `char` 流。

- `print(os, ...)`：¶1 普通字面量编码是 UTF-8 时等价于 `vprint_unicode(os, fmt.str, make_format_args(args...))`，否则用 `vprint_nonunicode`。
- `println(os, fmt, args...)`：¶2 等价于 `print(os, "{}\n", format(os.getloc(), fmt, std::forward<Args>(args)...))`——先格式化成字符串，再整体加换行输出。
- `println(os)`：¶3 等价于 `print(os, "\n")`。
- `vprint_unicode` / `vprint_nonunicode`：¶4 表现为 `os` 的格式化输出函数，**但有两处例外**：
    - ¶4.1 输出失败按下面的规定报告；
    - ¶4.2 `vformat` 抛出的任何异常**原样传播**，不管 `os.exceptions()` 是什么，也**不**在 `os` 的错误状态里置 `badbit`。
  
  构造 sentry 之后，以 `string out = vformat(os.getloc(), fmt, args);` 初始化一个自动变量。¶4.3：若是 `vprint_unicode` 且 `os` 指向只能通过原生 Unicode API 显示 Unicode 的终端（以实现定义的方式判断），先刷新 `os`，再用原生 API 写出 `out`；`out` 含无效码元则 {{ub}}；然后建立一个可观察检查点。¶4.4：否则把 `[out.begin(), out.end())` 插入 `os`。写终端或插入失败时调用 `os.setstate(badbit)`（可能抛 `ios_base::failure`）。
- ¶5 *Recommended practice*：需要转码时用 U+FFFD 替换无效码元。

几个推论：

1. **流的格式状态不影响 `print`**：`width`、`flags`、`fill`、`precision` 都不参与；格式完全由格式串决定。只有 locale 参与（仅对带 `L` 选项的替换域）。
2. **`print` 不会把 `width` 清零。** 规定里没有调用 `width(0)`，所以此前设置的 `setw` 会留给下一次 `<<`。
3. **格式错误与 I/O 错误分开报告**：`format_error` 直接抛出，流状态不变；I/O 失败走流的 `badbit`/异常掩码机制。

```cpp title="print-ostream.cpp" ok
#include <format>
#include <iomanip>
#include <iostream>
#include <ostream>
#include <sstream>

int main() {
  std::ostringstream os;
  os << std::setw(10) << std::hex;            // 对 print 没有影响
  std::print(os, "{}|{:x}", 255, 255);
  std::cout << '[' << os.str() << "]\n";      // [255|ff]
  std::cout << os.width() << '\n';            // 10：print 没有清零 width

  os.exceptions(std::ios_base::badbit);
  try {
    std::print(os, std::dynamic_format("{:d}"), "str");   // 运行期格式错误
  } catch (const std::format_error&) {
    std::cout << "format_error, bad=" << os.bad() << '\n'; // bad=0
  }
}
```

## 非格式化输出（[ostream.unformatted]）

¶1：每个非格式化输出函数先构造 sentry；若为真就尽力生成输出。输出过程中抛异常则置 `badbit`（不因此抛 `failure`），掩码中有 `badbit` 时重新抛出。最后销毁 sentry，没有异常时返回规定的值。

- `put(c)`：¶2–¶4 插入字符 `c`（脚注：不对 `signed char`/`unsigned char` 重载）；**不能插入时调用 `setstate(badbit)`**。
- `write(s, n)`：¶5–¶6 从 `s` 取字符插入，直到插入了 `n` 个，或插入失败——此时 `setstate(badbit)`。
- `flush()`：¶7–¶8 若 `rdbuf()` 非空，构造 sentry；sentry 为真则调用 `rdbuf()->pubsync()`，返回 −1 时 `setstate(badbit)`；sentry 为假则什么也不做。

非格式化输出不做填充、不看 `width`，`put` 和 `write` 也不调用 `widen`——它们写的就是 `char_type`。

## 标准输出操纵符（[ostream.manip]）

¶1：下列函数模板的每个实例化都是指定可寻址函数。

| 操纵符 | 效果 |
|---|---|
| `endl` | ¶2 `os.put(os.widen('\n'))`，然后 `os.flush()` |
| `ends` | ¶4 `os.put(charT())`：插入一个空字符 |
| `flush` | ¶6 `os.flush()` |
| `emit_on_flush` | ¶8 若 `os.rdbuf()` 是 `basic_syncbuf<charT, traits, Allocator>*`，调用 `set_emit_on_sync(true)`；否则无效果 |
| `noemit_on_flush` | ¶10 同上，`set_emit_on_sync(false)` |
| `flush_emit` | ¶12 先 `os.flush()`；然后若 `rdbuf()` 是 `basic_syncbuf*`，作为非格式化输出函数构造 sentry 后调用 `buf->emit()`，返回 `false` 时 `setstate(badbit)` |

¶8 的注提到一个实现难题："`rdbuf()` 是不是某个 `basic_syncbuf<charT, traits, Allocator>*`"需要知道 `Allocator`，而它无法从 `os` 推导；实现可以给 `basic_syncbuf` 引入一个不依赖分配器的中间基类来管理 *emit-on-sync* 标志，然后用 `dynamic_cast` 判断。后三个操纵符的用途见 [[syncstream]]。

!!! pitfall "`endl` 不是“换行”，是“换行并刷新”"
    对写文件或管道的流，每行一次 `flush` 意味着每行一次 `sync()`，通常就是一次系统调用。大量输出时用 `'\n'` 代替 `std::endl`，可以让 streambuf 攒满缓冲区再写。需要刷新的地方（如进度提示、崩溃前的最后日志）再显式 `flush`。对于交互式输入前的提示，`cin` 与 `cout` 的绑定（[[iostream.objects]]）已经保证了刷新，也不需要 `endl`。

## 右值流插入（[ostream.rvalue]）

```cpp
template<class Ostream, class T>
  Ostream&& operator<<(Ostream&& os, const T& x);
```

¶1 *Constraints*：`os << x` 作为不求值操作数良构，且 `Ostream` 公开且无歧义地派生自 `ios_base`。¶2–¶3：如同 `os << x;`，返回 `std::move(os)`。

它让 `std::ostringstream() << "x" << 42` 这样的表达式可以对临时对象工作，并保持派生类型——所以可以写 `(std::ostringstream() << "id=" << 42).str()`。

## 思考题

<details markdown="1">
<summary>1. 一个用户类型的 <code>operator&lt;&lt;</code> 中途抛异常，<code>cerr</code>（unitbuf）此前已写入的部分会被刷新吗？</summary>

sentry 的析构函数只在 `!uncaught_exceptions()` 时调用 `pubsync()`（[[ostream.sentry#4]]），栈展开期间析构的 sentry 不刷新。已写入的字符留在 streambuf 里，等下一次刷新。若用户的 `operator<<` 内部调用的标准插入器各自构造并正常销毁了 sentry，那些子操作结束时已经各自刷新过了。
</details>

<details markdown="1">
<summary>2. <code>std::cout &lt;&lt; std::setw(5); std::print(std::cout, "x"); std::cout &lt;&lt; 'y';</code> 输出什么？</summary>

`x    y`——`print` 不使用也不清零 `width`（[[ostream.formatted.print#4]] 只把格式化结果原样插入），于是 `width(5)` 留给了后面的 `'y'`，后者被填充为 4 个空格加 `y`。
</details>

<details markdown="1">
<summary>3. 为什么算术插入器失败置 <code>badbit</code>，而公共要求说生成失败置 <code>failbit</code>？</summary>

公共要求 ¶1 说的是"生成失败"的一般情形；算术插入器的具体规定（[[ostream.inserters.arithmetic#2]]）明确写了 `failed` 为真时 `setstate(badbit)`。`failed()` 为真的唯一原因是 `ostreambuf_iterator` 写入时 `sputc` 返回了 `eof()`——streambuf 拒绝接收字符，这是 I/O 层的问题，而不是"无法把值格式化成字符"，所以归为 `badbit`。`put`、`write` 失败同样置 `badbit`。
</details>

## 小结

| 函数 | sentry | 填充 / `width(0)` | 失败时 |
|---|---|---|---|
| 算术 `<<` | 是 | `num_put` 负责 | `badbit` |
| 字符、字符串 `<<` | 是 | 是 / 是 | — （`const char*` 为空是 UB） |
| `<< streambuf*` | 是（非格式化） | 否 | 无字符 → `failbit`；`sb` 为空 → `badbit` |
| 操纵符 `<<` | 否 | — | — |
| `put`、`write` | 是 | 否 | `badbit` |
| `flush` | 是 | — | `pubsync` 返回 −1 → `badbit` |
| `print(os, ...)` | 是 | 否 / **否** | 格式错误抛 `format_error`（不置位）；I/O 失败 `badbit` |
| sentry 析构 | — | — | `unitbuf` 且无未捕获异常时 `pubsync`，失败置 `badbit` 不抛 |
