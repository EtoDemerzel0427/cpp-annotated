---
title: 输入流 basic_istream
summary: basic_istream 怎样读入：每次输入前 sentry 做的准备，格式化输入（>>）与非格式化输入（get、getline、read 等）各自的规则与错误状态，数值解析失败和越界时得到什么，以及 eof 循环、>> 后接 getline、读 uint8_t 等常见陷阱。
status: done
covers: *
related: iostream.format, iostreams.base, stream.buffers, output.streams, string.io, facet.num.get.virtuals, stream.iterators, depr.istream.extractors
tags: 标准库, iostream, istream, 输入, sentry
updated: 2026-10-19
---

!!! tldr
    - 每次输入都先构造一个 sentry：流不处于 good 状态就追加 `failbit` 并放弃；否则先刷新绑定的输出流（`cin` 绑定 `cout`），格式化输入还要跳过前导空白。
    - 格式化输入（`>>`）跳过空白、按 locale 解析，失败位先记在局部错误状态里，最后一次写回流。非格式化输入（`get`、`getline`、`read` 等）不跳空白，读了几个字符记在 `gcount()` 里。
    - 数值解析交给 `num_get`：格式不对时得到 0，越界时得到该类型的最大值或最小值，两种情况都置 `failbit`。
    - 循环读取要写 `while (in >> x)`，不要写 `while (!in.eof())`。在 `>>` 之后调用 `getline` 前，用 `std::ws` 吃掉残留的换行。
    - 回退（`putback`、`unget`）失败置的是 `badbit`；`tellg` 在 `eofbit` 已置位时返回 −1，`seekg` 则会先清掉 `eofbit`。

## 为什么 `while (!in.eof())` 是错的

```cpp title="eof-loop.cpp" run ok
#include <iostream>
#include <sstream>

int main() {
  std::istringstream a("1 2 3\n");
  int x, sum = 0, n = 0;
  while (!a.eof()) {           // 错误的循环条件
    a >> x;
    sum += x; ++n;
  }
  std::cout << "wrong: n=" << n << " sum=" << sum << '\n';  // n=4 sum=9

  std::istringstream b("1 2 3\n");
  sum = n = 0;
  while (b >> x) { sum += x; ++n; }   // 以提取本身的成败为条件
  std::cout << "right: n=" << n << " sum=" << sum << '\n';  // n=3 sum=6
}
```

读完 `3` 时，后面还有一个 `'\n'`。`num_get` 遇到它就停止解析，没有撞到流尾，所以 `eof()` 仍为假。第四次 `>>` 先跳过 `'\n'`，然后才撞到流尾，于是置 `failbit` 和 `eofbit`，`x` 保持 3 不变，循环体又加了一次 3。

`eofbit` 只表示某次读取撞到了流尾，不能预告下一次读取会不会成功。要弄清楚每一步发生了什么，需要先看每次输入前的准备工作。

## sentry：每次输入前的准备 [istream.sentry]

**sentry** 是 `basic_istream` 的嵌套类，负责每次输入前后的固定步骤。每个输入函数开始时都构造一个 sentry 对象，再检查它转换成 `bool` 的结果，决定是否继续读取。

```cpp
class basic_istream<charT, traits>::sentry {
  bool ok_;                       // 仅用于说明
public:
  explicit sentry(basic_istream& is, bool noskipws = false);
  ~sentry();
  explicit operator bool() const { return ok_; }
  sentry(const sentry&) = delete;
  sentry& operator=(const sentry&) = delete;
};
```

¶2 构造函数按顺序做三件事：

1. 如果 `is.good()` 为假，调用 `is.setstate(failbit)`，准备结束。也就是说，流已经处于任何错误状态时，哪怕只是置了 `eofbit`，下一次输入都会追加 `failbit`。
2. 否则，如果 `is.tie()` 非空，调用 `is.tie()->flush()`。`cin` 默认绑定 `cout`，所以读输入前，屏幕上的提示一定已经输出（[[iostream.objects]]）。被绑定流的 put 区为空时可以省掉这次刷新；实现还可以把它推迟到真正需要从设备读数据，也就是调用 `underflow()` 的时候。
3. 如果参数 `noskipws` 为假，且流的 `skipws` 标志开着，就逐个提取并丢弃空白字符。读到流尾时调用 `setstate(failbit | eofbit)`。

¶3–¶4 判断一个字符是否是空白，用的是流当前 locale 中的 `ctype` facet，如同 `use_facet<ctype<charT>>(is.getloc()).is(ctype.space, c)`。

¶5 准备完成后，`is.good()` 为真则 `ok_` 为真，否则为假。¶6 析构函数没有效果，¶7 `operator bool` 返回 `ok_`。

第 3 步解释了一个常见现象：输入只剩空白时，`>>` 会同时置 `eofbit` 和 `failbit`。空白在 sentry 里被吃掉，然后撞到流尾，解析根本没有开始。

## 格式化输入：`>>` [istream.formatted.reqmts]

`istream` 的函数分成两组（[istream.general] ¶3）：[[g:formatted-input-function|格式化输入函数]]，又叫**提取器**（extractor），以及[[g:unformatted-input-function|非格式化输入函数]]。两组都通过 `rdbuf()->sbumpc()` 或 `rdbuf()->sgetc()` 从流缓冲区取字符（[[stream.buffers]]）。

¶1 每个格式化输入函数按同样的步骤执行：

1. 创建一个 `iostate` 类型的**局部错误状态**，初始为 `goodbit`。
2. 以 `noskipws = false` 构造 sentry。sentry 的构造抛出异常或转换为 `false` 时，不尝试读取，直接返回。
3. 尽力读取所需的输入。`sbumpc()` 或 `sgetc()` 返回 `eof()` 时，在局部错误状态里置 `eofbit`，停止读取。
4. 读取中抛出异常时，在局部错误状态里置 `badbit`，把它写进流；如果 `exceptions()` 包含 `badbit`，重新抛出这个异常，否则吞掉它。
5. 读取结束后调用 `setstate`，把局部错误状态写进流。这一步可能按 `exceptions()` 抛出 `ios_base::failure`。

错误位先攒起来，最后一次写回，所以至多因为状态位抛一次异常，而且抛出时流的状态已经完整，例如 `eofbit` 和 `failbit` 同时可见。

`std::getline(istream&, string&)` 和 `operator>>(istream&, string&)` 不在这一节，而在 [[string.io]]，它们分别按这里的规则表现为非格式化和格式化输入函数。

### 用 sentry 写自定义提取器

直接读流缓冲区的自定义 `operator>>` 应当自己构造 sentry，这样就有了与标准提取器一致的行为：跳过空白、刷新绑定的流、检查状态。错误位同样最后一次写回：

```cpp title="hex-extractor.cpp" run ok
#include <cctype>
#include <iostream>
#include <sstream>

struct Hex { unsigned value = 0; };

std::istream& operator>>(std::istream& in, Hex& h) {
  std::istream::sentry s(in);            // 跳过空白、刷新 tie、检查状态
  if (!s) return in;
  std::ios_base::iostate err = std::ios_base::goodbit;   // 局部错误状态
  auto* sb = in.rdbuf();
  if (sb->sbumpc() != '0' || sb->sbumpc() != 'x')
    err |= std::ios_base::failbit;
  unsigned v = 0;
  int digits = 0;
  for (;;) {
    auto c = sb->sgetc();
    if (c == std::char_traits<char>::eof()) { err |= std::ios_base::eofbit; break; }
    if (!std::isxdigit(c)) break;
    v = v * 16 + (std::isdigit(c) ? c - '0' : std::tolower(c) - 'a' + 10);
    ++digits;
    sb->sbumpc();
  }
  if (digits == 0) err |= std::ios_base::failbit;
  else h.value = v;
  in.setstate(err);                      // 一次写回，可能抛异常
  return in;
}

int main() {
  std::istringstream in("  0x1F 0xzz");
  Hex a, b;
  in >> a;
  std::cout << a.value << " ok=" << bool(in) << '\n';   // 31 ok=1
  in >> b;
  std::cout << "second ok=" << bool(in) << '\n';         // second ok=0
}
```

更简单的做法通常是在已有的提取器上组合，例如先 `in >> str` 再解析 `str`，sentry 就由内层的提取器负责。

## 读数值 [istream.formatted.arithmetic]

```cpp title="overflow-clamp.cpp" run ok
#include <iostream>
#include <sstream>

int main() {
  std::istringstream in("99999999999 abc");
  int x = 0, y = 5;
  in >> x;
  std::cout << x << ' ' << in.fail() << '\n';   // 2147483647 1
  in.clear();
  in >> y;
  std::cout << y << ' ' << in.fail() << '\n';   // 0 1
}
```

¶1 `long`、`unsigned`、浮点、`bool`、`void*` 等类型的提取器在 sentry 之后，如同执行：

```cpp
using numget = num_get<charT, istreambuf_iterator<charT, traits>>;
use_facet<numget>(loc).get(*this, 0, *this, state, val);
```

其中 `loc` 是流的 locale，`state` 是局部错误状态。第一个实参构造出的 `istreambuf_iterator` 绕过 `istream`，直接读流缓冲区。

所以数值怎样解析、何时失败、失败时得到什么，都由 `num_get` 决定（[[facet.num.get.virtuals]]）：

- 一个可用的字符都没有，例如读到 `abc`：`val` 置 0，置 `failbit`。
- 超出目标类型的范围：`val` 置为该类型的最大值或最小值，置 `failbit`。
- 无符号类型读到负号：`num_get` 按 `strtoull` 的规则解析，负号表示对结果取反。本机 libc++ 把 `"-1"` 读进 `unsigned` 得到 `4294967295`，不置 `failbit`。
- `bool`：没有 `boolalpha` 时只接受 `0` 和 `1`；有 `boolalpha` 时接受 locale 中 `numpunct` 的 `truename()` 和 `falsename()`，默认是 `true`、`false`。

¶2–¶3 `num_get` 没有接受 `short&` 和 `int&` 的重载，所以这两个提取器先读成 `long`，再检查范围：越界时置 `failbit`，结果取该类型的最小值或最大值。

¶4–¶6 {{c++23}} 扩展浮点类型（如 `std::float16_t`，[[basic.fundamental]]）的提取器先读成一个不比它窄的标准浮点类型，再检查范围、转换。扩展类型比 `long double` 还宽时，这个提取器是有条件支持的。注 2 提醒，转换中可能发生两次舍入，需要最高精度时用 `from_chars`（[[charconv]]）。

!!! pitfall "`std::uint8_t` 读入的是字符"
    ```cpp title="uint8-read.cpp" run ok
    #include <cstdint>
    #include <iostream>
    #include <sstream>

    int main() {
      std::istringstream in("7");
      std::uint8_t c;
      in >> c;                        // 读入的是字符 '7'
      std::cout << int(c) << '\n';    // 55，而不是 7
    }
    ```

    `std::uint8_t` 通常是 `unsigned char` 的别名，`>>` 选中的是读一个字符的重载。当前草案把 `signed char`、`unsigned char` 的提取器移到了附录 D（[[depr.istream.extractors]]），这是 C++23 之后的新措辞 {{deprecated}}，目的是让这类代码将来得到诊断。本机 libc++ 截至写作时还没有对它发出弃用警告。要读数字，先读进 `int` 再转换。

## 其他提取器 [istream.extractors]

### 操纵符（¶1–¶6）

¶1–¶6 接受函数指针的三个 `operator>>` 不是格式化输入函数：不构造 sentry，只调用 `pf(*this)`。所以流处于失败状态时，`in >> std::hex` 照样生效。脚注举的例子是 `ws` 和 `dec`。

### 字符数组（¶7–¶11）

```cpp title="char-array.cpp" error
#include <iomanip>
#include <iostream>

int main() {
  char q[100];
  std::cin >> std::setw(20) >> q;   // OK
  char* p = new char[100];
  std::cin >> std::setw(20) >> p;   // error: C++20 起没有接受 char* 的重载
}
```

¶7 这个提取器的参数是数组引用 `charT (&s)[N]`。`width()` 大于 0 时最多存 `n = min(width(), N)` 个字符（包括结尾的空字符），否则 `n = N`。¶8 提取持续到存了 `n - 1` 个字符、到达流尾，或者下一个字符是空白。¶9 然后存一个空字符，调用 `width(0)`。¶10 一个字符都没提取到时置 `failbit`。

C++20 之前参数是 `charT*`，函数无法知道缓冲区多大，只能靠 `setw` 防止溢出，忘了写就是缓冲区溢出。现在 `N` 从类型推导出来，溢出不再可能；代价是 `char*` 不能再用 `>>` 读（[[diff.cpp17.input.output]]）。

### 单个字符（¶12–¶13）

¶12 `in >> c` 是格式化输入函数，所以会跳过空白。有可用字符就提取并存入 `c`，否则置 `failbit`。想读包括空白在内的下一个字符，用 `in.get(c)`，或者先 `in >> std::noskipws`。

### 读进另一个流缓冲区（¶14–¶16）

¶14 `in >> sb`（`sb` 是 `basic_streambuf*`）表现为非格式化输入函数。`sb` 为空时置 `failbit`。否则把字符从 `*this` 搬到 `sb` 的输出序列，直到流尾、插入失败（这个字符不被提取）或者发生异常（异常被捕获）。¶15 一个字符都没插入时置 `failbit`。

## 非格式化输入 [istream.unformatted]

### 公共步骤（¶1）

¶1 非格式化输入函数与格式化输入函数的步骤基本相同，区别是：

- sentry 以 `noskipws = true` 构造，所以不跳过空白，但仍然检查流状态、刷新绑定的流。
- sentry 失败时，提取计数置 0；接受字符数组的函数还要在数组第一个位置存一个空字符。
- 没有异常时，把提取的字符数存进一个成员，就是 `gcount()` 的返回值。

¶2–¶3 `gcount()` 返回最后一次非格式化输入成员函数提取的字符数，无法表示时返回 `numeric_limits<streamsize>::max()`。格式化输入（`>>`）不更新它。

### `get`（¶4–¶17）

| 调用 | 行为 | 失败 |
|---|---|---|
| `get()` | ¶4–¶5 提取一个字符并返回；没有字符时返回 `eof()` | 没有字符时置 `failbit` |
| `get(c)` | ¶6 提取一个字符存入 `c` | 同上 |
| `get(s, n, delim)` | ¶8–¶9 提取并存储，直到存了 `n - 1` 个、到达流尾，或下一个字符是 `delim`（不提取它）；`n > 0` 时总会补一个空字符 | 一个都没存时置 `failbit` |
| `get(s, n)` | ¶11 即 `get(s, n, widen('\n'))` | |
| `get(sb, delim)` | ¶13–¶14 把字符插入流缓冲区 `sb`，停止条件同上，另加插入失败和异常（异常被捕获，不重新抛出） | 一个都没插入时置 `failbit` |
| `get(sb)` | ¶16 即 `get(sb, widen('\n'))` | |

`get(s, n)` 与 `getline(s, n)` 的区别在于，`get` 把分隔符留在流里。连续两次 `get(buf, n)` 读两行时，第二次一开始就遇到上次留下的 `'\n'`，一个字符也存不了，于是置 `failbit`。

### `getline`（¶18–¶24）

```cpp title="getline-array.cpp" run ok
#include <iostream>
#include <sstream>

int main() {
  std::istringstream in("abcd\nabcdefgh\n");
  char buf[5];
  in.getline(buf, sizeof buf);    // "abcd" 正好 4 个字符
  std::cout << buf << " gcount=" << in.gcount()
            << " fail=" << in.fail() << '\n';   // abcd gcount=5 fail=0
  in.getline(buf, sizeof buf);    // 行太长：存 4 个字符后置 failbit
  std::cout << buf << " gcount=" << in.gcount()
            << " fail=" << in.fail() << '\n';   // abcd gcount=4 fail=1
}
```

¶18 `getline(s, n, delim)` 提取字符存入 `s`，按下面的顺序检查停止条件（¶19）：

1. 到达流尾；
2. 下一个字符是 `delim`：提取它但不存储，所以它计入 `gcount()`；
3. 已经存了 `n - 1` 个字符：调用 `setstate(failbit)`。

先检查分隔符、后检查长度，所以正好填满缓冲区的一行不会置 `failbit`。脚注说明这与历史上 AT&T 实现的行为不同。¶20 一个字符都没提取时才置 `failbit`，所以空行不会置 `failbit`，因为换行符被提取了。¶21 `n > 0` 时总会补一个空字符。

¶23 标准的例子用 `while (cin.getline(buf, size) || cin.gcount())` 逐行读取。`|| cin.gcount()` 让被截断的长行（置了 `failbit`，但提取了字符）也进入循环体，在体内用 `cin.clear(cin.rdstate() & ~ios_base::failbit)` 清掉 `failbit`，继续读这一行的剩余部分。`eof()` 为真表示最后一行没有换行符。

### `ignore`（¶25–¶28）

¶25 `ignore(n = 1, delim = eof())` 提取并丢弃字符，直到提取了 `n` 个、到达流尾（置 `eofbit`），或者遇到 `delim`（提取它）。`n` 等于 `numeric_limits<streamsize>::max()` 时不限个数。`delim` 是 `eof()` 时，只有前两个条件会生效。

¶27–¶28 {{c++26}} 新增 `ignore(n, char_type delim)`，只对 `char` 流提供，等价于 `ignore(n, traits::to_int_type(delim))`。

旧签名的第二个参数是 `int_type`。在 `char` 有符号的平台上，`'\xA1'` 转成 `int` 是 −95，而流里的字符经 `to_int_type` 得到 161，两者永远不相等，`ignore` 会一路读到流尾。新重载修正了这个问题（[[diff.cpp23.io]]）：

```cpp title="ignore-char.cpp" run ok
#include <iostream>
#include <sstream>
#include <string>

int main() {
  std::istringstream in("\xF0\x9F\xA4\xA1 Clown Face");
  in.ignore(100, '\xA1');            // 停在 '\xA1' 之后
  std::string rest;
  std::getline(in, rest);
  std::cout << '[' << rest << "]\n"; // [ Clown Face]
}
```

附录 C 同时指出，第二个实参既不是 `int` 也不是 `char` 的调用，例如 `in.ignore(100, -1L)`，现在有歧义，变成非良构。本机 libc++ 已经提供这个重载，并在所有语言模式下都启用。

### `peek`、`read`、`readsome`（¶29–¶34）

¶29–¶30 `peek()` 读取但不提取当前字符。流不处于 good 状态时返回 `eof()`，否则返回 `rdbuf()->sgetc()`。

¶31 `read(s, n)` 提取字符存入 `s`，直到存满 `n` 个或到达流尾。到达流尾时调用 `setstate(failbit | eofbit)`，也就是说读不满 `n` 个就算失败，实际读到的个数用 `gcount()` 取得。

```cpp title="read-short.cpp" run ok
#include <iostream>
#include <sstream>

int main() {
  std::istringstream r("xyz");
  char out[8];
  r.read(out, 8);       // 只有 3 个字符
  std::cout << "gcount=" << r.gcount() << " eof=" << r.eof()
            << " fail=" << r.fail() << '\n';   // gcount=3 eof=1 fail=1
}
```

¶33–¶34 `readsome(s, n)` 只读已经在缓冲区里的字符，从不等待设备。`rdbuf()->in_avail()` 为 −1 时置 `eofbit`，不提取；为 0 时不提取；大于 0 时提取 `min(in_avail(), n)` 个。返回提取的个数。对 `showmanyc()` 保持默认实现的流缓冲区，get 区为空时它总是返回 0（[[stream.buffers]]）。

### `putback`、`unget`、`sync`（¶35–¶39）

¶35、¶37 `putback(c)` 和 `unget()` 先清掉 `eofbit`，再构造 sentry；流不处于 good 状态时置 `failbit` 并返回。否则调用 `rdbuf()->sputbackc(c)` 或 `sungetc()`，`rdbuf()` 为空或者它们返回 `eof()` 时置 `badbit`。注意置的是 `badbit` 而不是 `failbit`。它们不提取字符，所以之后的 `gcount()` 是 0。

¶39 `sync()` 不影响 `gcount()`。`rdbuf()` 为空时返回 −1；否则调用 `rdbuf()->pubsync()`，它返回 −1 时置 `badbit` 并返回 −1，否则返回 0。对输入流，`sync` 的具体效果由流缓冲区决定，例如 `basic_filebuf` 的效果由实现定义（[[file.streams]]）。

### `tellg`、`seekg`（¶40–¶45）

¶40–¶41 `tellg()` 不影响 `gcount()`。构造 sentry 之后，`fail()` 为真时返回 `pos_type(-1)`，否则返回 `rdbuf()->pubseekoff(0, cur, in)`。

¶42–¶45 `seekg(pos)` 和 `seekg(off, dir)` 先清掉 `eofbit`，构造 sentry 之后，如果 `fail()` 为假，调用 `rdbuf()->pubseekpos(pos, in)` 或 `pubseekoff(off, dir, in)`，失败时置 `failbit`。

`seekg` 先清 `eofbit`，`tellg` 不清，这个不对称很容易踩到。在 `eofbit` 已置位时调用 `tellg()`，sentry 看到流不 good，追加 `failbit`，于是返回 −1：

```cpp title="tellg-at-eof.cpp" run ok
#include <iostream>
#include <sstream>
#include <string>

int main() {
  std::istringstream in("hello");
  std::string s;
  in >> s;                          // 成功，但撞到流尾：eofbit
  std::cout << in.fail() << ' ';    // 0
  std::cout << in.tellg() << ' ';   // -1：sentry 追加了 failbit
  std::cout << in.fail() << '\n';   // 1
  in.clear();
  in.seekg(0);
  in >> s;
  std::cout << s << '\n';           // hello
}
```

## `ws`：跳过空白 [istream.manip]

```cpp title="getline-after-extract.cpp" run ok
#include <iostream>
#include <sstream>
#include <string>

int main() {
  std::istringstream in("42\nAlice Smith\n");
  int age;
  std::string name;
  in >> age;
  std::getline(in, name);              // 读到 42 后面剩下的空行
  std::cout << '[' << name << "]\n";   // []

  std::istringstream in2("42\nAlice Smith\n");
  in2 >> age;
  std::getline(in2 >> std::ws, name);  // 先吃掉空白
  std::cout << '[' << name << "]\n";   // [Alice Smith]
}
```

`>>` 读完 `42` 后停在换行符前面，紧接着的 `getline` 读到的是这个换行符之前的空串。

¶2 `ws` 表现为非格式化输入函数，但不影响 `gcount()`。构造 sentry 之后，只要下一个字符是空白就提取它，判断标准与 sentry 相同。因为没有更多字符而停止时，它只置 `eofbit`，不置 `failbit`。对比 `>>`：它跳空白时撞到流尾会同时置两个位。¶1 `ws` 是指定可寻址函数，程序可以取它的地址。

## 读失败之后

置了 `failbit` 之后，所有输入操作的 sentry 都会立即失败，流看起来就像卡住了。要从坏输入中恢复，必须先 `clear()`，再丢掉导致失败的字符：

```cpp title="recover.cpp" run ok
#include <iostream>
#include <limits>
#include <sstream>

int main() {
  std::istringstream in("12 abc 34\n56");
  int x, sum = 0;
  while (true) {
    if (in >> x) { sum += x; continue; }
    if (in.eof()) break;                // 真正读完了
    in.clear();                         // 清掉 failbit
    in.ignore(std::numeric_limits<std::streamsize>::max(), ' ');  // 丢掉坏词
  }
  std::cout << sum << '\n';   // 102
}
```

## 右值流提取 [istream.rvalue]

```cpp
template<class Istream, class T>
  Istream&& operator>>(Istream&& is, T&& x);
```

¶1 约束：`is >> std::forward<T>(x)` 良构，且 `Istream` 公开、无歧义地派生自 `ios_base`。¶2 效果是执行 `is >> std::forward<T>(x)`，再返回 `std::move(is)`。

成员形式的 `>>`（读 `int` 等）本来就能在临时对象上调用，但读 `std::string`、`char` 的 `>>` 是非成员函数，第一个参数是左值引用，不能绑定到临时对象。这个重载让 `std::istringstream("abc") >> s` 也能编译。它返回 `Istream&&` 而不是 `basic_istream&`，保留了派生类型，所以 C++20 起可以直接在结果上调用 `istringstream` 自己的成员。

## 构造与 `basic_iostream`

[istream.cons] ¶1–¶2 `basic_istream(sb)` 用 `basic_ios::init(sb)` 初始化基类，之后 `gcount() == 0`。¶4 析构函数不对 `rdbuf()` 做任何操作。

¶3 移动构造函数和 [istream.assign] 中的移动赋值、`swap` 都是受保护的，它们移动或交换 `basic_ios` 的状态和 `gcount()`，但不涉及流缓冲区。`basic_istream` 只持有指向流缓冲区的指针；拥有缓冲区的是 `ifstream`、`istringstream` 这类派生类，由它们提供公有的移动操作，并在其中调用 `set_rdbuf`（[[iostreams.base]]）。

[iostreamclass] `basic_iostream` 同时派生自 `basic_istream` 和 `basic_ostream`，两者共享同一个流缓冲区。[iostream.cons] ¶1–¶2 构造函数用同一个 `sb` 初始化两个基类，之后 `rdbuf() == sb`、`gcount() == 0`。`basic_ios` 是虚基类，只有一份。[iostream.dest] 析构函数同样不对 `rdbuf()` 做任何操作。

## 思考题

!!! question "思考题 1"
    输入是两个空格。对 `int x`，`in >> x` 之后流是什么状态？换成 `in.get()` 呢？换成 `in >> std::ws` 呢？

<details markdown="1">
<summary>答案</summary>

`in >> x`：sentry 跳过两个空格后撞到流尾，置 `failbit | eofbit`（[[istream.sentry#2]]），`x` 不变。

`in.get()`：sentry 以 `noskipws = true` 构造，不跳空白，读走第一个空格并返回 `' '`，流状态仍是 good。

`in >> std::ws`：吃掉两个空格后没有更多字符，只置 `eofbit`，不置 `failbit`（[[istream.manip#2]]），所以 `operator bool` 仍为真。
</details>

!!! question "思考题 2"
    文件末尾剩下不足 `n` 个字节时，`while (in.read(buf, n)) process(buf, n);` 会怎样？

<details markdown="1">
<summary>答案</summary>

会丢掉最后一块数据。`read` 读不满 `n` 个时调用 `setstate(failbit | eofbit)`（[[istream.unformatted#31]]），循环条件为假，已经读进 `buf` 的最后几个字节没有被处理。可以改成 `while (in.read(buf, n) || in.gcount()) process(buf, in.gcount());`，思路与标准中 `getline` 的例子相同。
</details>

!!! question "思考题 3"
    `in.putback('x')` 失败时置哪个位？之后 `if (in)` 为真还是假？

<details markdown="1">
<summary>答案</summary>

置 `badbit`（[[istream.unformatted#35]]），而不是表示没读到期望输入的 `failbit`。`fail()` 在 `badbit` 或 `failbit` 置位时都为真，所以 `if (in)` 为假。要继续使用这个流，必须先 `clear()`。
</details>

## 小结

| 类别 | sentry 的 `noskipws` | 跳过空白 | 更新 `gcount` | 典型失败 |
|---|---|---|---|---|
| 格式化 `>>`（数值、字符、数组） | `false` | 是（`skipws` 时） | 否 | 格式错误、越界：`failbit`；只剩空白：`failbit` 和 `eofbit` |
| 操纵符 `>>` | 不构造 | 否 | 否 | |
| `get`、`getline`、`read`、`ignore` | `true` | 否 | 是 | 一个字符都没得到：`failbit`；`read` 读不满：`failbit` 和 `eofbit` |
| `putback`、`unget` | `true`，先清 `eofbit` | 否 | 置 0 | 回退失败：`badbit` |
| `tellg` | `true`，不清 `eofbit` | 否 | 不影响 | 流不 good：追加 `failbit`，返回 −1 |
| `seekg` | `true`，先清 `eofbit` | 否 | 不影响 | 定位失败：`failbit` |
| `ws` | `true` | 是 | 不影响 | 到流尾只置 `eofbit` |
