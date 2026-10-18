---
title: 输入流 basic_istream
summary: basic_istream 的全部规则——sentry 构造时做的三件事（检查 good、刷新 tie、跳过空白），格式化输入的"局部错误状态"模型，算术提取器如何借 num_get 解析并在溢出时截断为极值，字符数组提取只接受数组（C++20），非格式化输入 get/getline/read/readsome/ignore/peek/putback/unget/sync/tellg/seekg 的逐条语义与 gcount，ws 操纵符，右值流提取，basic_iostream；以及 eof 循环、>> 后接 getline、int8_t、错误恢复等常见陷阱
status: done
covers: *
related: iostream.format, iostreams.base, stream.buffers, output.streams, string.io, facet.num.get.virtuals, stream.iterators, depr.istream.extractors
tags: 标准库, iostream, istream, 输入, sentry
updated: 2026-10-18
---

[input.streams] 规定 `<istream>` 中的 `basic_istream`、`ws` 操纵符、右值提取，以及同时派生自输入和输出流的 `basic_iostream`。这一节的条文冗长，但几乎都由两个"公共要求"驱动：[istream.formatted.reqmts]（格式化输入）和 [istream.unformatted] ¶1（非格式化输入）。先把这两段读懂，每个具体函数只是在它们上面加几条特殊规则。

## 概述（[input.streams.general]、[istream.general]）

[input.streams.general] ¶1：`<istream>` 定义两个类模板（`basic_istream`、`basic_iostream`）和一个函数模板（`ws`），以及一个从流右值提取的函数模板。

[istream.general] ¶1：用占位符 *extended-floating-point-type* 声明的函数，实现要为**每个**无 cv 限定的扩展浮点类型（[[basic.fundamental]]，如 `std::float16_t`）提供重载 {{c++23}}。

概要要点：

```cpp
template<class charT, class traits = char_traits<charT>>
class basic_istream : virtual public basic_ios<charT, traits> {
public:
  explicit basic_istream(basic_streambuf<charT, traits>* sb);
  virtual ~basic_istream();
  class sentry;

  // 格式化输入（提取器）
  basic_istream& operator>>(basic_istream& (*pf)(basic_istream&));      // 操纵符
  basic_istream& operator>>(basic_ios<charT, traits>& (*pf)(basic_ios<charT, traits>&));
  basic_istream& operator>>(ios_base& (*pf)(ios_base&));
  basic_istream& operator>>(bool& / short& / ... / long double& / extended-floating-point-type&);
  basic_istream& operator>>(void*& p);
  basic_istream& operator>>(basic_streambuf<char_type, traits>* sb);

  // 非格式化输入
  streamsize gcount() const;
  int_type get();   basic_istream& get(char_type& c);
  basic_istream& get(char_type* s, streamsize n [, char_type delim]);
  basic_istream& get(basic_streambuf<char_type, traits>& sb [, char_type delim]);
  basic_istream& getline(char_type* s, streamsize n [, char_type delim]);
  basic_istream& ignore(streamsize n = 1, int_type delim = traits::eof());
  basic_istream& ignore(streamsize n, char_type delim);                 // C++26
  int_type peek();
  basic_istream& read(char_type* s, streamsize n);
  streamsize readsome(char_type* s, streamsize n);
  basic_istream& putback(char_type c);
  basic_istream& unget();
  int sync();
  pos_type tellg();
  basic_istream& seekg(pos_type);
  basic_istream& seekg(off_type, ios_base::seekdir);
protected:
  basic_istream(basic_istream&& rhs);                 // 复制被删除
  basic_istream& operator=(basic_istream&& rhs);
  void swap(basic_istream& rhs);
};
// 非成员：operator>>(istream&, charT&)、operator>>(istream&, charT(&)[N])
```

¶2–¶3：成员分为两组——**格式化输入函数**（formatted input functions，又称**提取器**，[[g:formatted-input-function]]）和**非格式化输入函数**（[[g:unformatted-input-function]]）。两组都被描述为通过 `rdbuf()->sbumpc()` 或 `rdbuf()->sgetc()` 获取（"提取"）字符，可以使用 `istream` 的其他公有成员。

注意 `std::getline(istream&, string&)` 和 `operator>>(istream&, string&)` **不在**这里，而在字符串章的 [[string.io]]；它们按这里的规则"表现为"非格式化/格式化输入函数。

## 构造、赋值、析构（[istream.cons]、[istream.assign]）

- `explicit basic_istream(sb)`：¶1 用 `basic_ios::init(sb)` 初始化基类；¶2 后条件 `gcount() == 0`。
- 移动构造（受保护）：¶3 默认构造基类，复制 `rhs` 的 `gcount()`，调用 `basic_ios::move(rhs)`，再把 `rhs` 的 `gcount` 置 0。
- 析构函数：¶4 不对 `rdbuf()` 做任何操作。
- `operator=(&&)`：[istream.assign] ¶1 等价于 `swap(rhs)`；`swap`：¶3 调用 `basic_ios::swap(rhs)` 并交换 `gcount()`。

移动操作是**受保护**的：`basic_istream` 本身是"接口 + 状态"，真正拥有 streambuf 的是派生类（`ifstream`、`istringstream`），由它们提供公有的移动构造并在其中调用 `set_rdbuf`（[[iostreams.base]]）。

## sentry：每次输入的前置工作（[istream.sentry]）

```cpp
class basic_istream<charT, traits>::sentry {
  bool ok_;                       // 说明专用
public:
  explicit sentry(basic_istream& is, bool noskipws = false);
  ~sentry();
  explicit operator bool() const { return ok_; }
  sentry(const sentry&) = delete;
  sentry& operator=(const sentry&) = delete;
};
```

¶1：`sentry`（[[g:sentry]]）负责异常安全的前缀和后缀操作。构造函数（¶2）按顺序：

1. 若 `is.good()` 为假，调用 `is.setstate(failbit)`，结束。——**流已经处于任何错误状态（包括仅仅是 `eofbit`）时，下一次输入操作会追加 `failbit`。**
2. 否则准备输入。首先，若 `is.tie()` 非空，调用 `is.tie()->flush()`，使输出序列与关联的外部 C 流同步。例外：被绑定流的 put 区为空时可以省略；实现还可以把这次刷新**推迟**到 `is.rdbuf()->underflow()` 被调用时，若直到 sentry 析构都没有发生这样的调用，刷新可以完全省略（脚注：这只可能在库自己的函数里做到）。
3. 若 `noskipws` 为假且 `is.flags() & skipws` 非零，逐个提取并丢弃空白字符。若 `sbumpc()` 或 `sgetc()` 返回 `eof()`，调用 `setstate(failbit | eofbit)`。

¶3–¶4：判断空白使用 `is` 当前的 locale，如同 `use_facet<ctype<charT>>(is.getloc()).is(ctype.space, c)`。¶5：所有准备完成后，若 `is.good()` 为真则 `ok_` 为真，否则为假；准备期间可能调用 `setstate(failbit)`（可能抛异常）。脚注：构造函数和析构函数还可以做额外的、依赖实现的操作（例如对流加锁）。

¶6：析构函数无效果。¶7：`operator bool` 返回 `ok_`。

第 3 步解释了一个反直觉的现象：**输入只剩空白时，`>>` 会同时置 `eofbit` 和 `failbit`**——空白在 sentry 里被吃掉，然后撞到流尾，根本没机会开始解析。

### 用 sentry 写自定义提取器

自定义 `operator>>` 如果直接读 streambuf，就应当自己构造 sentry，以获得与标准提取器一致的行为（跳过空白、`tie` 刷新、状态检查），并在最后一次性 `setstate`：

```cpp title="hex-extractor.cpp" ok
#include <cctype>
#include <iostream>
#include <sstream>

struct Hex { unsigned value = 0; };

std::istream& operator>>(std::istream& in, Hex& h) {
  std::istream::sentry s(in);                   // 跳过前导空白、刷新 tie、检查状态
  if (!s) return in;
  std::ios_base::iostate err = std::ios_base::goodbit;   // 局部错误状态
  auto* sb = in.rdbuf();
  if (sb->sbumpc() != '0' || sb->sbumpc() != 'x') err |= std::ios_base::failbit;
  unsigned v = 0; int digits = 0;
  for (;;) {
    auto c = sb->sgetc();
    if (c == std::char_traits<char>::eof()) { err |= std::ios_base::eofbit; break; }
    if (!std::isxdigit(c)) break;
    v = v * 16 + (std::isdigit(c) ? c - '0' : std::tolower(c) - 'a' + 10);
    ++digits; sb->sbumpc();
  }
  if (digits == 0) err |= std::ios_base::failbit;
  else h.value = v;
  in.setstate(err);                             // 一次性写回（可能抛异常）
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

更简单的做法通常是**基于已有提取器组合**（先 `in >> str` 再解析），那样 sentry 由内层提取器负责。

## 格式化输入的公共要求（[istream.formatted.reqmts]）

¶1 是理解所有 `>>` 的钥匙，按步骤拆开：

1. 构造一个 `iostate` 类型的**局部错误状态**，初始为 `goodbit`。
2. 以 `noskipws = false` 构造 sentry。若 sentry 构造抛异常或转换为 `false`，函数不尝试获取任何输入，直接返回。
3. 否则尽力获取输入。若 `sbumpc()` 或 `sgetc()` 返回 `eof()`，在局部错误状态中置 `eofbit` 并停止。
4. 若输入过程中抛出异常：在局部错误状态中置 `badbit`，把 `*this` 的错误状态设为局部错误状态，若 `(exceptions() & badbit) != 0` 则**重新抛出**（否则吞掉）。
5. 提取完成后调用 `setstate(局部错误状态)`——这可能抛异常。
6. 无论如何销毁 sentry；没有异常时返回 `*this`。

"局部错误状态"的意义在于：状态位被**攒起来最后一次写入**，所以至多因状态位抛一次异常，而且抛异常时流的状态已经完整（例如 `eofbit` 与 `failbit` 同时可见）。

## 算术提取器（[istream.formatted.arithmetic]）

¶1：`unsigned short`、`unsigned int`、`long`、`unsigned long`、`long long`、`unsigned long long`、`float`、`double`、`long double`、`bool`、`void*` 的提取器作为格式化输入函数工作；sentry 构造之后，转换如同：

```cpp
using numget = num_get<charT, istreambuf_iterator<charT, traits>>;
use_facet<numget>(loc).get(*this, 0, *this, state, val);
```

其中 `loc` 是流的 locale，`state` 是局部错误状态。注：第一个实参构造了一个 `istreambuf_iterator`，**绕过 istream、直接读 streambuf**；`locale` 借助这个迭代器类型作为与 istream 的接口，不必直接依赖 istream。

所以数值如何解析、何时置 `failbit`、失败时 `val` 得到什么值，都由 `num_get` 决定（[[facet.num.get.virtuals]]）：

- 格式不对（一个可用字符都没有）：`val` 置 0，`failbit`；
- 超出目标类型范围：`val` 置为该类型的最大值或最小值，`failbit`；
- 无符号类型读到负号：`num_get` 按 `strtoull` 的规则解析，负号表示对结果取反。本机 libc++ 上 `"-1"` 读进 `unsigned`、`unsigned short`、`unsigned long long` 分别得到各自的最大值，**不**置 `failbit`；
- `bool`：没有 `boolalpha` 时只接受 `0` 和 `1`，有 `boolalpha` 时接受 `numpunct` 的 `truename()`/`falsename()`。

`short` 与 `int` 没有对应的 `num_get::get` 重载，于是 ¶2–¶3 规定先读成 `long`，再检查范围：

```cpp
long lval;
use_facet<numget>(loc).get(*this, 0, *this, state, lval);
if (lval < numeric_limits<int>::min()) {
  state |= ios_base::failbit;  val = numeric_limits<int>::min();
} else if (numeric_limits<int>::max() < lval) {
  state |= ios_base::failbit;  val = numeric_limits<int>::max();
} else
  val = static_cast<int>(lval);
```

扩展浮点类型（¶4–¶6）{{c++23}}：若其转换等级大于 `long double`，调用该运算符是**有条件支持**的，语义由实现定义；否则选一个等级不低于它的标准浮点类型 `FP`（`float`、`double` 或 `long double` 中最小的那个），读成 `FP`，再按与上面相同的方式检查范围、转换。注 2：若扩展类型的等级不等于任何标准类型，可能发生两次舍入而不精确；需要最高精度时用 `from_chars`（[[charconv]]）。

```cpp title="overflow-clamp.cpp" ok
#include <iostream>
#include <sstream>

int main() {
  std::istringstream in("99999999999");
  int x = 0;
  in >> x;
  std::cout << x << ' ' << in.fail() << '\n';   // 2147483647 1
}
```

## 其他提取器（[istream.extractors]）

### 操纵符（¶1–¶6）

三个接受函数指针的 `operator>>` **不是**格式化输入函数：不构造 sentry，只调用 `pf(*this)`。所以 `in >> std::hex` 在流处于失败状态时照样生效。脚注举例：`ws(basic_istream&)` 和 `dec(ios_base&)`。

### 字符数组：`operator>>(istream&, charT(&)[N])`（¶7–¶11）

作为格式化输入函数：sentry 之后提取字符存入 `s`。若 `width() > 0`，最多存 `n = min(size_t(width()), N)` 个（包括结尾的空字符），否则 `n = N`。提取持续到以下任一发生：存了 `n - 1` 个字符；输入序列到达文件尾；下一个字符是空白（按流的 locale）。然后存一个 `charT()`，调用 `width(0)`；一个字符都没提取到则置 `failbit`。

C++20 之前这个重载接受的是 `charT*`，无法知道缓冲区大小，只能靠 `setw` 防止溢出——忘了 `setw` 就是缓冲区溢出。现在参数是数组引用，`N` 从类型推导，溢出在类型层面被杜绝；代价是 `char*` 不再能用 `>>` 读（[[diff.cpp17.input.output]]）：

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

### 单个字符：`operator>>(istream&, charT&)`（¶12–¶13）

作为格式化输入函数（所以**会跳过空白**）：若有可用字符就提取并存入 `c`，否则置 `failbit`。想读包括空白在内的下一个字符，用 `get(c)` 或 `>> std::noskipws`。

### 读入 streambuf：`operator>>(basic_streambuf*)`（¶14–¶16）

表现为**非格式化**输入函数。`sb` 为空则 `setstate(failbit)`。否则从 `*this` 提取字符插入 `sb` 的输出序列，直到：输入到达文件尾；插入失败（该字符不被提取）；发生异常（异常被捕获）。一个字符都没插入则置 `failbit`。

### 已弃用：`signed char`/`unsigned char` 的提取 {{deprecated}}

当前草案把 `operator>>(basic_istream<char, traits>&, unsigned char&)`、`signed char&` 以及对应的数组版本移到了附录 D（[[depr.istream.extractors]]），这是 C++23 之后的新措辞。它们的行为与 `char` 版本相同——**读一个字符，而不是一个数**。这正是 `std::uint8_t`（通常是 `unsigned char` 的别名）读数字时的著名陷阱：

```cpp title="uint8-read.cpp" ok
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

弃用的目的就是让这类代码将来得到诊断。本机 libc++ 截至写作时还没有对这些重载发出弃用警告。

## 非格式化输入（[istream.unformatted]）

### 公共要求（¶1）

每个非格式化输入函数：构造局部错误状态（初始 `goodbit`）；以 **`noskipws = true`** 构造 sentry——所以**不跳过空白**，但仍然检查 `good()` 并刷新 `tie`。若 sentry 失败，不获取任何输入；无论哪种情况，**提取计数都被置 0**，并且接受非零大小字符数组的函数还要在数组第一个位置存一个空字符。

其余与格式化输入相同：`eof()` → `eofbit` 并停止；异常 → `badbit`，按掩码决定是否重新抛出；没有异常时把提取的字符数存进一个成员对象（即 `gcount()` 的返回值）；最后 `setstate` 一次。

### `gcount`（¶2–¶3）

返回**最后一次**非格式化输入成员函数提取的字符数；它本身不是非格式化输入函数。无法表示时返回 `numeric_limits<streamsize>::max()`。注意：格式化输入（`>>`）**不更新** `gcount`；`peek`、`putback`、`unget`、`sync`、`tellg`、`seekg` 也不计数（后几个明确规定"不影响 `gcount()`"，`putback`/`unget` 的注说下一次 `gcount()` 返回 0）。

### `get` 的各个重载（¶4–¶17）

| 调用 | 行为 | 失败条件 |
|---|---|---|
| `int_type get()` | ¶4–¶5 提取一个字符并返回；无字符可读返回 `eof()` | 无字符 → `failbit` |
| `get(char_type& c)` | ¶6–¶7 提取一个字符存入 `c` | 无字符 → `failbit` |
| `get(s, n, delim)` | ¶8–¶10 提取并存储，直到：`n < 1` 或已存 `n - 1` 个；文件尾；下一个字符等于 `delim`（**不提取**它）。`n > 0` 时总会存结尾空字符 | 一个都没存 → `failbit` |
| `get(s, n)` | ¶11 `get(s, n, widen('\n'))` | |
| `get(sb, delim)` | ¶13–¶15 提取并插入 `sb`，直到文件尾、插入失败、下一个字符等于 `delim`（不提取）或发生异常（被捕获但不重新抛出） | 一个都没插入 → `failbit` |
| `get(sb)` | ¶16 `get(sb, widen('\n'))` | |

`get(s, n)` 与 `getline(s, n)` 的关键区别是：`get` **把分隔符留在流里**。连续两次 `get(buf, n)` 读两行，第二次会立刻遇到上次留下的 `'\n'`，一个字符都存不了，于是置 `failbit`。

### `getline`（¶18–¶24）

`getline(s, n, delim)` 提取字符存入 `s`，直到以下之一发生（**按顺序检查**，¶19）：

1. 输入序列到达文件尾；
2. 下一个字符等于 `delim`——它被**提取但不存储**（脚注：因为被提取了，所以计入 `gcount()`）；
3. `n < 1` 或已存了 `n - 1` 个字符——此时调用 `setstate(failbit)`。

脚注解释顺序的意义：先检查分隔符、再检查长度，于是**恰好填满缓冲区的一行**不会置 `failbit`；这与历史上 AT&T 实现的行为不同。¶20：一个字符都没**提取**才置 `failbit`——脚注强调，所以**空行不会**置 `failbit`（换行符被提取了）。¶21：`n > 0` 时总会在下一个位置存空字符。

```cpp title="getline-array.cpp" ok
#include <iostream>
#include <sstream>

int main() {
  std::istringstream in("abcd\nabcdefgh\n");
  char buf[5];
  in.getline(buf, sizeof buf);    // "abcd" 恰好 4 个字符：成功，gcount 含换行
  std::cout << buf << " gcount=" << in.gcount() << " fail=" << in.fail() << '\n';  // abcd gcount=5 fail=0
  in.getline(buf, sizeof buf);    // 行太长：存 4 个字符后置 failbit
  std::cout << buf << " gcount=" << in.gcount() << " fail=" << in.fail() << '\n';  // abcd gcount=4 fail=1
}
```

标准在 ¶23 给了一个完整的逐行读取例子：用 `while (cin.getline(buffer, size, '\n') || cin.gcount())` 作循环条件——`|| gcount()` 让"太长被截断的行"（`failbit` 但提取了字符）也进入循环体，在体内用 `cin.clear(cin.rdstate() & ~ios_base::failbit)` 清掉 `failbit` 继续读剩余部分；`eof()` 为真表示最后一行没有换行符。

### `ignore`（¶25–¶28）

`ignore(n = 1, delim = eof())`：提取并丢弃字符，直到：`n != numeric_limits<streamsize>::max()` 且已提取 `n` 个；文件尾（调用 `setstate(eofbit)`）；下一个字符 `c` 满足 `eq_int_type(to_int_type(c), delim)`（**提取**它）。注：`delim` 是 `eof()` 时最后一个条件永远不会发生。`n` 等于 `numeric_limits<streamsize>::max()` 表示**不限个数**。

`ignore(n, char_type delim)` {{c++26}}：¶27 *Constraints*：`char_type` 是 `char`；¶28 等价于 `ignore(n, traits::to_int_type(delim))`。

为什么要加这个重载？旧的签名第二个参数是 `int_type`，传入 `char` 时发生整型提升：在 `char` 有符号的平台上，`'\xA1'` 提升为负数 −95，而流里的字符经 `to_int_type` 得到的是 161，永远不相等，于是 `ignore` 一路读到文件尾。[[diff.cpp23.io]] 记录了这一变化：

```cpp title="ignore-char.cpp" ok
#include <iostream>
#include <sstream>
#include <string>

int main() {
  std::istringstream in("\xF0\x9F\xA4\xA1 Clown Face");
  in.ignore(100, '\xA1');            // C++26：char 重载，正确停在 '\xA1' 之后
  std::string rest;
  std::getline(in, rest);
  std::cout << '[' << rest << "]\n"; // [ Clown Face]
}
```

附录 C 同时指出副作用：第二个实参既不是 `int` 也不是 `char` 的调用（如 `in.ignore(100, -1L)`）现在有歧义，变成非良构。本机 libc++ 已提供这个重载，并把它作为缺陷修复应用到所有语言模式。

### `peek`、`read`、`readsome`（¶29–¶34）

- `peek()`：¶29–¶30 构造 sentry 后读但不提取当前字符；`good()` 为假时返回 `eof()`，否则返回 `rdbuf()->sgetc()`。
- `read(s, n)`：¶31–¶32 构造 sentry 后，若 `!good()` 调用 `setstate(failbit)` 并返回；否则提取字符存入 `s`，直到存满 `n` 个，或到达文件尾——此时调用 `setstate(failbit | eofbit)`。**短读是失败**：读不满 `n` 个就置 `failbit`，实际读到的个数用 `gcount()` 取得。
- `readsome(s, n)`：¶33–¶34 只读**已经可用**的字符：若 `rdbuf()->in_avail() == -1`，置 `eofbit`、不提取；为 0 则不提取；大于 0 则提取 `min(in_avail(), n)` 个。返回提取的个数。它从不阻塞等待设备，但正因如此，对于默认 `showmanyc()` 返回 0 的 streambuf，它在 get 区为空时总是返回 0。

```cpp title="read-short.cpp" ok
#include <iostream>
#include <sstream>

int main() {
  std::istringstream r("xyz");
  char out[8];
  r.read(out, 8);       // 只有 3 个字符
  std::cout << "gcount=" << r.gcount() << " eof=" << r.eof() << " fail=" << r.fail() << '\n';
  // gcount=3 eof=1 fail=1
}
```

### `putback`、`unget`、`sync`（¶35–¶39）

- `putback(c)`、`unget()`：¶35、¶37 表现为非格式化输入函数，**但先清除 `eofbit`**。sentry 之后若 `!good()` 则 `setstate(failbit)` 返回；否则调用 `rdbuf()->sputbackc(c)` / `sungetc()`；`rdbuf()` 为空或它们返回 `eof()` 时调用 `setstate(badbit)`。注意失败置的是 **`badbit`**——回退失败被视为流完整性的问题。注：它们不提取字符，下一次 `gcount()` 返回 0。
- `sync()`：¶39 不计数；sentry 之后，`rdbuf()` 为空返回 −1；否则调用 `rdbuf()->pubsync()`，返回 −1 时置 `badbit` 并返回 −1，否则返回 0。对输入流，`sync` 的含义由 streambuf 决定：`filebuf` 的 get 区 `sync` 效果由实现定义（[[file.streams]]）。

### `tellg`、`seekg`（¶40–¶45）

- `tellg()`：¶40–¶41 表现为非格式化输入函数（不计数）。构造 sentry 之后，若 `fail()` 为真，返回 `pos_type(-1)`；否则返回 `rdbuf()->pubseekoff(0, cur, in)`。
- `seekg(pos)` / `seekg(off, dir)`：¶42–¶45 **先清除 `eofbit`**，不计数；构造 sentry 之后若 `fail()` 不为真，调用 `rdbuf()->pubseekpos(pos, in)` / `pubseekoff(off, dir, in)`；失败时 `setstate(failbit)`。

`tellg` 与 `seekg` 的不对称是一个真实的坑：`seekg` 先清 `eofbit` 再构造 sentry，而 `tellg` 不清。所以**在 `eof()` 状态下调用 `tellg()`，sentry 会因 `good()` 为假而追加 `failbit`，返回 −1**：

```cpp title="tellg-at-eof.cpp" ok
#include <iostream>
#include <sstream>
#include <string>

int main() {
  std::istringstream in("hello");
  std::string s;
  in >> s;                                    // 成功，但撞到流尾：eofbit
  std::cout << in.fail() << ' ';              // 0
  std::cout << in.tellg() << ' ';             // -1：sentry 见到 !good()，置 failbit
  std::cout << in.fail() << '\n';             // 1
  in.clear();
  in.seekg(0);                                // seekg 自己会先清 eofbit
  in >> s;
  std::cout << s << '\n';                     // hello
}
```

## `ws` 操纵符（[istream.manip]）

¶1：`ws` 的每个实例化都是指定可寻址函数。¶2：表现为非格式化输入函数（不计数），构造 sentry 后只要下一个字符是空白就提取（判断标准同 sentry）。**因为没有更多字符而停止时，置 `eofbit` 但不置 `failbit`**——与 `>>` 跳空白撞到流尾时置 `failbit | eofbit` 形成对比。

`ws` 最常见的用途是在 `>>` 之后、`getline` 之前吃掉残留的换行：

```cpp title="getline-after-extract.cpp" ok
#include <iostream>
#include <sstream>
#include <string>

int main() {
  std::istringstream in("42\nAlice Smith\n");
  int age; std::string name;
  in >> age;
  std::getline(in, name);              // 读到的是 42 后面剩下的空行
  std::cout << '[' << name << "]\n";   // []

  std::istringstream in2("42\nAlice Smith\n");
  in2 >> age;
  std::getline(in2 >> std::ws, name);  // 先吃掉空白
  std::cout << '[' << name << "]\n";   // [Alice Smith]
}
```

## 右值流提取（[istream.rvalue]）

```cpp
template<class Istream, class T>
  Istream&& operator>>(Istream&& is, T&& x);
```

¶1 *Constraints*：`is >> std::forward<T>(x)` 作为不求值操作数良构，且 `Istream` 公开且无歧义地派生自 `ios_base`。¶2：等价于 `is >> std::forward<T>(x); return std::move(is);`。

它让临时流对象可以直接使用：`std::istringstream("17") >> v;`。返回 `Istream&&`（而不是 `basic_istream&`）是 C++20 的改进，使得 `std::istringstream("1 2") >> a >> b` 链式调用时仍然保持派生类型。

## `basic_iostream`（[iostreamclass]）

```cpp
template<class charT, class traits = char_traits<charT>>
class basic_iostream : public basic_istream<charT, traits>,
                       public basic_ostream<charT, traits> { ... };
```

- ¶1（[iostreamclass.general]）：继承读写由同一个流缓冲区控制的序列的函数。
- [iostream.cons] ¶1–¶2：`basic_iostream(sb)` 以 `basic_istream(sb)` 和 `basic_ostream(sb)` 初始化两个基类，后条件 `rdbuf() == sb`、`gcount() == 0`。由于 `basic_ios` 是虚基类，它由 `basic_iostream`（作为最终派生类时）初始化一次。¶3：移动构造以 `std::move(rhs)` 构造 `basic_istream` 基类——`basic_ostream` 基类没有额外状态需要移动。
- [iostream.dest] ¶1：析构函数不对 `rdbuf()` 做任何操作。
- [iostream.assign]：移动赋值等价于 `swap(rhs)`，`swap` 调用 `basic_istream::swap(rhs)`。

## 陷阱汇总

### `while (!in.eof())`

```cpp title="eof-loop.cpp" ok
#include <iostream>
#include <sstream>

int main() {
  std::istringstream a("1 2 3\n");
  int x, sum = 0, n = 0;
  while (!a.eof()) {           // 错误：eof 只有在"撞到"流尾之后才置位
    a >> x;
    sum += x; ++n;
  }
  std::cout << "wrong: n=" << n << " sum=" << sum << '\n';   // n=4 sum=9

  std::istringstream b("1 2 3\n");
  sum = n = 0;
  while (b >> x) { sum += x; ++n; }   // 正确：以提取本身的成败为条件
  std::cout << "right: n=" << n << " sum=" << sum << '\n';   // n=3 sum=6
}
```

读完 `3` 时后面还有 `'\n'`，`num_get` 遇到它就停止，没有撞到流尾，`eof()` 仍为假。第四次 `>>` 在 sentry 里跳过 `'\n'` 后撞到流尾，置 `failbit | eofbit`，`x` 保持 3（sentry 失败，根本没有转换），于是多加了一次 3。

### 读失败后流"卡死"

一旦置了 `failbit`，之后所有输入操作的 sentry 都会立刻失败。从坏输入中恢复必须先 `clear()`，再丢弃导致失败的字符：

```cpp title="recover.cpp" ok
#include <iostream>
#include <limits>
#include <sstream>

int main() {
  std::istringstream in("12 abc 34\n56");
  int x, sum = 0;
  while (true) {
    if (in >> x) { sum += x; continue; }
    if (in.eof()) break;                        // 真正读完了
    in.clear();                                 // 清掉 failbit
    in.ignore(std::numeric_limits<std::streamsize>::max(), ' ');   // 丢弃坏词
  }
  std::cout << sum << '\n';   // 102
}
```

### 一次性复制整个流

`out << in.rdbuf()` 是把一个流的剩余内容整体复制到另一个流的惯用法（插入器版本见 [[output.streams]]）；注意源为空时它会给**输出流**置 `failbit`。

## 思考题

<details markdown="1">
<summary>1. 输入是 <code>"  "</code>（两个空格）。<code>in &gt;&gt; x</code>（<code>int x</code>）之后状态是什么？<code>in.get()</code> 呢？<code>in &gt;&gt; std::ws</code> 呢？</summary>

- `in >> x`：sentry 跳过两个空格后撞到流尾，置 `failbit | eofbit`（[[istream.sentry#2]]），`x` 不变。
- `in.get()`：sentry 以 `noskipws = true` 构造，不跳空白，读走第一个空格并返回 `' '`，状态 `good`。
- `in >> std::ws`：吃掉两个空格后没有更多字符，置 `eofbit` 但**不**置 `failbit`（[[istream.manip#2]]），`operator bool` 仍为真。
</details>

<details markdown="1">
<summary>2. 为什么 <code>in.read(buf, n)</code> 读到文件末尾的不足 <code>n</code> 个字节时，循环 <code>while (in.read(buf, n)) process(buf, n);</code> 会丢数据？</summary>

`read` 短读时调用 `setstate(failbit | eofbit)`（[[istream.unformatted#31]]），于是循环条件为假，最后那一块虽然已经读进了 `buf`，却没有被处理。正确写法是在循环外再处理一次 `in.gcount()` 个字节：`while (in.read(buf, n) || in.gcount()) process(buf, in.gcount());`——与标准 ¶23 例子中 `getline` 的写法同一思路。
</details>

<details markdown="1">
<summary>3. <code>in.putback('x')</code> 失败时置的是哪个位？为什么不是 <code>failbit</code>？</summary>

`badbit`（[[istream.unformatted#35]]）。`failbit` 表示"没能读到期望的字符"，是可恢复的输入问题；回退失败意味着 streambuf 无法维持它的指针约束，流已经不能保证后续读取的正确性，属于完整性问题。这也意味着 `operator bool` 为假（`fail()` 包括 `badbit`），而且 `clear()` 之后再读，读到的位置也可能不是你以为的那里。
</details>

## 小结

| 类别 | sentry 的 `noskipws` | 跳过空白 | 计入 `gcount` | 典型失败 |
|---|---|---|---|---|
| 格式化（`>>` 数值、字符、数组） | `false` | 是（`skipws` 时） | 否 | 格式错误 / 溢出 → `failbit`；只剩空白 → `failbit|eofbit` |
| 操纵符 `>>` | 不构造 | — | — | — |
| `get`/`getline`/`read`/`ignore` | `true` | 否 | 是 | 一个字符都没得到 → `failbit`；`read` 短读 → `failbit|eofbit` |
| `putback`/`unget` | `true`，先清 `eofbit` | 否 | 置 0 | 回退失败 → `badbit` |
| `tellg` | `true`，**不**清 `eofbit` | 否 | 不影响 | 流不 `good()` → 追加 `failbit`，返回 −1 |
| `seekg` | `true`，先清 `eofbit` | 否 | 不影响 | 定位失败 → `failbit` |
| `ws` | `true` | 是 | 不影响 | 到尾只置 `eofbit` |
