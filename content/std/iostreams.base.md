---
title: iostream 基类：ios_base、basic_ios 与 fpos
summary: 流对象的"状态层"——fmtflags/iostate/openmode/seekdir 四个位掩码与枚举的精确含义，eofbit/failbit/badbit 各在什么时候置位、operator bool 只看 fail()，clear/setstate/exceptions 的抛出规则（exceptions() 会立即抛），setf 带不带 mask 的区别，xalloc/iword/pword 与回调，copyfmt 的逐步语义，basic_ios::init 的初始值，fpos 的要求与 -1 无效位置，以及 io_errc / iostream_category
status: done
covers: *
related: input.output, iostream.objects, stream.buffers, input.streams, output.streams, iostream.format, syserr, bitmask.types, localization, iostreams.requirements
tags: 标准库, iostream, 状态位, 格式标志, 异常
updated: 2026-10-18
---

[iostreams.base] 定义的是**所有流共有的状态**。它分成两个类：

- `ios_base`：**非模板**类，保存与字符类型无关的状态——格式标志、宽度、精度、`locale`、私有存储（`iword`/`pword`）、回调列表，以及四个嵌套类型 `fmtflags`、`iostate`、`openmode`、`seekdir`。
- `basic_ios<charT, traits>`：派生自 `ios_base`，加上与字符类型有关的状态——错误状态位、异常掩码、填充字符（`charT`）、`tie` 指针、`rdbuf` 指针。

把与 `charT` 无关的部分放进非模板基类，是为了让 `std::hex` 这类操纵符只需写一次：它们的签名是 `ios_base& hex(ios_base&)`，对 `cout` 和 `wcout` 都适用。

## `<ios>` 概要（[ios.syn]）

`<ios>` 包含 `<iosfwd>`，声明 `streamoff`/`streamsize`（[[iostreams.requirements]]）、`fpos`、`ios_base`、`basic_ios`、全部 `ios_base&(ios_base&)` 形式的操纵符（`boolalpha`…`defaultfloat`），以及错误报告设施 `io_errc`、`is_error_code_enum<io_errc>`、`make_error_code`、`make_error_condition`、`iostream_category`。

## `ios_base` 概述（[ios.base.general]）

¶1：`ios_base` 定义 `failure`（派生自 `system_error` 的类，或其同义词）、`Init`、三个位掩码类型 `fmtflags`、`iostate`、`openmode`，以及枚举类型 `seekdir`。所谓位掩码类型（bitmask type，[[bitmask.types]]），是指可以用 `|`、`&`、`^`、`~` 组合、每个常量代表一个或一组位的类型；具体是整数还是枚举由实现决定（概要里写作 `T1`…`T4`），所以**不要**假设 `fmtflags` 是 `int`。

¶2：它维护三类数据——反映流缓冲区完整性的**状态信息**、影响如何解析输入和生成输出的**控制信息**，以及程序为私有用途存放的**附加信息**。¶3（注）用说明专用成员 `index`、`iarray`、`parray` 描述第三类（见下文 `xalloc`）。

### `ios_base::failure`（[ios.failure]）

```cpp
class ios_base::failure : public system_error {
public:
  explicit failure(const string& msg, const error_code& ec = io_errc::stream);
  explicit failure(const char* msg, const error_code& ec = io_errc::stream);
};
```

¶1：实现可以把 `ios_base::failure` 定义为某个具有等价功能的类的同义词（注：这时那个类需要提供嵌套的 `failure` 来模拟注入类名）。它是 iostream 库为报告"流缓冲区操作中检测到的错误"而抛出的所有异常的基类。¶2：抛出时实现**应当**给出能识别具体原因的 `ec`：来自操作系统的错误一般是 `system_category()` 的错误码，来自流库内部的一般是 `error_code(io_errc::stream, iostream_category())`。

C++11 起 `failure` 派生自 `system_error`（之前派生自 `exception`），所以 `catch (const std::system_error&)` 也能捕获它，并且可以用 `e.code()` 区分原因。

## 四个嵌套类型（[ios.types]）

### `fmtflags`：格式标志（[ios.fmtflags]）

| 元素 | 置位时的效果 |
|---|---|
| `boolalpha` | `bool` 按字母形式（`true`/`false`）插入和提取 |
| `dec` / `oct` / `hex` | 整数按十/八/十六进制转换（输入和输出） |
| `fixed` / `scientific` | 浮点输出用定点 / 科学记法 |
| `left` / `right` / `internal` | 填充字符放在右侧 / 左侧 / 内部指定位置（如符号与数字之间） |
| `showbase` | 整数输出带进制前缀（`0`、`0x`） |
| `showpoint` | 浮点输出总是带小数点 |
| `showpos` | 非负数输出带 `+` |
| `skipws` | 某些输入操作前跳过前导空白 |
| `unitbuf` | 每次输出操作后刷新 |
| `uppercase` | 输出中某些小写字母换成大写（`0X`、`1E+10`、十六进制数字） |

表 137 定义三个**组合常量**：`adjustfield = left | right | internal`，`basefield = dec | oct | hex`，`floatfield = scientific | fixed`。同一组里的位语义上互斥，但它们是**独立的位**——这正是 `setf` 有两个重载的原因（见下文）。

### `iostate`：错误状态（[ios.iostate]）

表 138 只有三个元素和一个常量 `goodbit`（值为零）：

| 元素 | 标准的定义 | 典型触发 |
|---|---|---|
| `badbit` | 输入或输出序列失去完整性（如从文件读时发生不可恢复的读错误） | streambuf 抛异常、`overflow` 失败导致 `put`/`write` 失败、`rdbuf()` 为空 |
| `eofbit` | 某个输入操作**到达了**输入序列的末尾 | 提取时 `sgetc()`/`sbumpc()` 返回 `eof()` |
| `failbit` | 输入操作没能读到期望的字符，或输出操作没能生成期望的字符 | 数值格式错误、溢出、一个字符都没提取到、`seekg` 失败 |

关键在于 `eofbit` 与 `failbit` 是**独立**的：

```cpp title="state-bits.cpp" ok
#include <iostream>
#include <sstream>

void probe(const char* input) {
  std::istringstream in(input);
  int x = -1;
  in >> x;
  std::cout << '"' << input << "\"\t x=" << x
            << " good=" << in.good() << " eof=" << in.eof()
            << " fail=" << in.fail() << " bool=" << static_cast<bool>(in) << '\n';
}

int main() {
  probe("42 ");          // x=42 good=1 eof=0 fail=0 bool=1
  probe("42");           // x=42 good=0 eof=1 fail=0 bool=1   成功，但撞到了流尾
  probe("abc");          // x=0  good=0 eof=0 fail=1 bool=0   转换失败，x 被置 0
  probe("");             // x=-1 good=0 eof=1 fail=1 bool=0   sentry 就失败了，x 不变
  probe("99999999999");  // x=2147483647 good=0 eof=1 fail=1  溢出：failbit，x 取最大值
}
```

几点值得逐一解释：

- `"42"`：`num_get` 为了确认数字已经结束，必须再读一个字符，结果读到了流尾，于是置 `eofbit`；但值成功得到，所以**不**置 `failbit`。这一次提取是成功的，`if (in >> x)` 为真。
- `"abc"`：转换失败时 `num_get` 把值置为 0（[[facet.num.get.virtuals]]）。
- `""`：`sentry` 在跳过空白时就撞到流尾，置 `failbit | eofbit`（[[istream.sentry#2]]），根本没调用 `num_get`，所以 `x` 保持 −1。
- 溢出：`operator>>(int&)` 先读成 `long` 再判断范围，超出时置 `failbit` 并存入 `numeric_limits<int>::max()`（[[istream.formatted.arithmetic#3]]）；本机 `long` 是 64 位，所以 `99999999999` 能读进 `long`、再在这一步被截断。

### `openmode`：打开模式（[ios.openmode]）

| 元素 | 效果 |
|---|---|
| `app` | 每次写之前定位到末尾 |
| `ate` | 打开后立即定位到末尾 |
| `binary` | 以二进制模式（而不是文本模式）进行 I/O |
| `in` / `out` | 为输入 / 输出打开 |
| `noreplace` {{c++23}} | 以独占模式打开（文件已存在则失败） |
| `trunc` | 打开时截断已有内容 |

这些组合如何映射到 `fopen` 的模式串，见 [[file.streams]] 的表 146；对 string/span 流，`in`/`out`/`ate` 决定 get/put 区如何初始化（[[string.streams]]）。

### `seekdir`（[ios.seekdir]）

枚举类型（[[enumerated.types]]），三个值：`beg`（相对开头）、`cur`（相对当前位置）、`end`（相对**当前**末尾）。

### `ios_base::Init`（[ios.init]）

¶1：构造它保证 `<iostream>` 中八个标准流对象已被构造。¶2：构造函数在它们尚未构造时构造之；¶3：析构函数在没有其他 `Init` 实例存活时刷新 `cout`、`cerr`、`clog`、`wcout`、`wcerr`、`wclog`。它与静态初始化顺序的关系见 [[iostream.objects]]。

## 格式状态函数（[fmtflags.state]）

| 函数 | 效果 | 返回 |
|---|---|---|
| `flags()` | — | 当前格式标志 |
| `flags(f)` | 全部替换为 `f` | 旧值 |
| `setf(f)` | **置位** `f`（按位或） | 旧值 |
| `setf(f, mask)` | 先清除 `mask` 中的所有位，再置位 `f & mask` | 旧值 |
| `unsetf(mask)` | 清除 `mask` | — |
| `precision()` / `precision(p)` | 某些输出转换的精度 | 旧值 |
| `width()` / `width(w)` | 某些输出转换的**最小**字段宽度 | 旧值 |

单参数 `setf` 只是"或"上去，不会清除同组的其他位，这是一个经典陷阱：

```cpp title="setf-mask.cpp" ok
#include <iostream>

int main() {
  std::cout.setf(std::ios_base::hex);                          // dec 仍然置位
  std::cout << 255 << '\n';                                    // 255：basefield == dec|hex，不等于 hex
  std::cout.setf(std::ios_base::hex, std::ios_base::basefield);
  std::cout << 255 << '\n';                                    // ff
}
```

`num_put` 判断进制的方式是比较 `flags() & basefield` **是否等于** `oct` 或 `hex`（[[facet.num.put.virtuals]]）；两个位同时置位时两者都不等于，于是落回十进制。操纵符 `std::hex` 内部调用的正是带 mask 的版本（[[basefield.manip]]），所以用操纵符不会踩到这个坑。

`precision` 的含义随 `floatfield` 而变：默认记法下是**有效数字**位数，`fixed`/`scientific` 下是**小数点后**的位数。初始值 6。

```cpp title="precision.cpp" ok
#include <iostream>

int main() {
  std::cout.precision(3);
  std::cout << 1234.5678 << ' ';                    // 1.23e+03（3 位有效数字）
  std::cout << std::fixed << 1234.5678 << ' ';      // 1234.568
  std::cout << std::scientific << 1234.5678 << '\n';// 1.235e+03
}
```

## locale（[ios.base.locales]）

- `imbue(loc)`：¶1 以 `(*fn)(imbue_event, *this, idx)` 调用每个已注册的回调，调用时 `getloc()` 已经返回新值；¶2 后条件 `loc == getloc()`；¶3 返回旧值。
- `getloc()`：¶4 若从未 imbue 过，返回构造时的全局 C++ locale `locale()` 的副本；否则返回 imbue 进来的 locale。

注意"构造时"：之后再调用 `std::locale::global(...)` 不会影响已经存在的流对象，包括 `cout`。

`basic_ios::imbue` 还会把 locale 传给 `rdbuf()->pubimbue(loc)`（[[basic.ios.members#9]]），而 `ios_base::imbue` 不会。

## `sync_with_stdio`（[ios.members.static]）

声明为 `ios_base` 的静态成员，但只关系到标准流对象，详见 [[iostream.objects]]。

## 私有存储：`xalloc`、`iword`、`pword`（[ios.base.storage]）

这组函数让**用户自定义的格式状态**也能像 `std::hex` 一样附着在流上：

- `static int xalloc()`：¶1 返回 `index++`，即一个全局唯一的新下标；¶2 多线程并发调用不构成数据竞争。
- `long& iword(int idx)` / `void*& pword(int idx)`：¶3/¶6 前置条件是 `idx` 来自 `xalloc()`；¶4/¶7 按需扩展数组（新元素初始化为 0 / 空指针），返回元素的引用。**返回的引用在对该对象做任何其他操作后失效**，但值本身被保留——下次用同一下标调用会得到同一个值（直到 `copyfmt`）。分配失败时，若 `*this` 是某个 `basic_ios` 的基类子对象，效果等价于 `setstate(badbit)`，并返回一个值为 0 的有效引用。¶9：之后对同一对象再调用 `pword` 可能使之前的返回值失效。

```cpp title="iword-manip.cpp" ok
#include <iostream>
#include <sstream>

const int style_slot = std::ios_base::xalloc();   // 进程范围内唯一的下标

struct Point { int x, y; };

std::ostream& angle_style(std::ostream& os) { os.iword(style_slot) = 1; return os; }

std::ostream& operator<<(std::ostream& os, Point p) {
  if (os.iword(style_slot) == 1) return os << '<' << p.x << ';' << p.y << '>';
  return os << '(' << p.x << ", " << p.y << ')';
}

int main() {
  std::ostringstream a, b;
  a << angle_style << Point{1, 2};
  b << Point{1, 2};                 // b 的槽位仍是 0
  std::cout << a.str() << ' ' << b.str() << '\n';   // <1;2> (1, 2)
  b.copyfmt(a);                     // copyfmt 复制 iword 数组的内容
  b << ' ' << Point{3, 4};
  std::cout << b.str() << '\n';     // (1, 2) <3;4>
}
```

`pword` 存的是 `void*`，如果它指向流"拥有"的堆对象，就要配合回调处理释放与深拷贝，否则 `copyfmt` 之后两个流共享同一指针、析构时都不知道该谁释放。

## 回调（[ios.base.callback]）与构造/析构（[ios.base.cons]）

```cpp
enum event { erase_event, imbue_event, copyfmt_event };
using event_callback = void (*)(event, ios_base&, int idx);
void register_callback(event_callback fn, int idx);
```

- ¶1 前置条件：`fn` 不抛异常。
- ¶2：注册 `(fn, idx)`，在 `imbue()`、`copyfmt()`、`~ios_base()` 期间以 `idx` 调用 `fn`。事件发生时按**注册的相反顺序**调用；在某个回调执行期间注册的新回调，要到下一次事件才会被调用。
- ¶3：相同的 `(fn, idx)` 不会合并——注册两次就调用两次。

`ios_base()`：¶1 构造后所有成员的值都是**不确定的**；必须在首次使用或析构之前（以先到者为准）调用 `basic_ios::init`，否则行为未定义 {{ub}}。这是 `ios_base` 的默认构造函数是 `protected` 的原因——只有知道如何调用 `init` 的派生类才能构造它。

`~ios_base()`：¶2 以 `erase_event` 调用每个回调（此时在回调中调用 `ios_base` 的成员函数结果是确定的），然后释放所获得的内存（`iarray`/`parray`）。

## `fpos`：流位置（[fpos]）

```cpp
template<class stateT> class fpos {
public:
  stateT state() const;
  void state(stateT);
private:
  stateT st;          // 说明专用
};
```

`fpos` 表示**文件位置**：一个能与 `streamoff` 互相转换的偏移量，再加上一个转换状态 `st`（对 `char` 流是 `mbstate_t`）。为什么位置里要带一个状态？因为在状态相关的多字节编码（如某些 Shift 编码）中，同一个字节偏移处的"含义"取决于此前的移位状态；`seekpos` 回到某个位置时必须连同状态一起恢复。

[fpos.operations] ¶1 的表 141 规定了 `fpos` 必须支持的运算。用 `P` 表示 `fpos` 特化、`O` 表示 `streamoff`：

| 表达式 | 含义 |
|---|---|
| `P(o)`、`P p(o)`、`P p = o` | 从偏移量构造，状态值初始化 |
| `P()`、`P p;` | 等于 `P(0)` |
| `O(p)` | 转换回偏移量；`P(O(p)) == p` |
| `p == q`、`p != q` | 比较 |
| `p + o`、`p += o`、`p - o`、`p -= o`、`o + p` | 位置 ± 偏移 |
| `p - q` | 两个位置的距离（`streamoff`） |

¶1 还规定：`stateT` 须满足 *Cpp17DefaultConstructible* 等要求；`stateT` 平凡可复制构造/赋值/析构时，`fpos` 的对应特殊成员也是平凡的。

¶2：返回 `traits::pos_type` 的流操作用 `P(O(-1))` 表示**无效值**，以报告错误；把这个值再传给任何接受 `pos_type` 的 `istream`/`ostream`/`streambuf` 成员，行为未定义 {{ub}}。所以 `seekg(tellg())` 这种写法在 `tellg()` 失败时是 UB——应先检查返回值。

```cpp title="tellg-check.cpp" ok
#include <iostream>
#include <sstream>

int main() {
  std::istringstream in("abc");
  auto pos = in.tellg();
  if (pos == std::streampos(-1)) return 1;   // 先检查，再使用
  in.get();
  in.seekg(pos);
  std::cout << static_cast<char>(in.get()) << '\n';   // a
}
```

## `basic_ios`（[ios]）

### 概述（[ios.overview]）

`basic_ios<charT, traits>` 派生自 `ios_base`，增加：

- 类型别名：`char_type`、`int_type`、`pos_type`、`off_type`、`traits_type`；
- 状态函数：`operator bool`、`operator!`、`rdstate`、`clear`、`setstate`、`good`、`eof`、`fail`、`bad`、`exceptions`；
- 成员：`tie`、`rdbuf`、`copyfmt`、`fill`、`imbue`、`narrow`、`widen`；
- 受保护的：默认构造函数、`init`、`move`、`swap`、`set_rdbuf`——这些是给派生类（各种流）实现构造与移动用的。

复制构造和复制赋值被删除：流不可复制（但派生的具体流类可移动）。

### 构造与 `init`（[basic.ios.cons]）

- ¶1 `explicit basic_ios(basic_streambuf* sb)`：调用 `init(sb)`。
- ¶2 `basic_ios()`（受保护）：成员保持未初始化；必须在首次使用或析构前调用 `init`，否则 {{ub}}。虚继承下最终派生类负责构造虚基类，而流的各个中间类都想初始化它——所以中间类调用默认构造函数，再由自己调用 `init`。
- ¶3 析构函数**不销毁** `rdbuf()`：流不拥有它的 streambuf（`ifstream` 等是把 `filebuf` 作为自己的成员持有，而不是通过 `basic_ios` 拥有）。
- ¶4 `init(sb)` 的后条件（表 142）：

| 成员 | `init` 之后的值 |
|---|---|
| `rdbuf()` | `sb` |
| `tie()` | 空 |
| `rdstate()` | `sb` 非空则 `goodbit`，否则 `badbit` |
| `exceptions()` | `goodbit`（不抛任何异常） |
| `flags()` | `skipws | dec` |
| `width()` | 0 |
| `precision()` | 6 |
| `fill()` | `widen(' ')` |
| `getloc()` | `locale()` 的副本 |
| `iarray` / `parray` | 空指针 |

### 成员函数（[basic.ios.members]）

- **`tie`**：¶1 返回与本流**绑定**的输出序列（[[g:tied-stream]]）。¶2 设置时的前置条件：从 `tiestr->tie()` 出发沿绑定链走不能回到 `tiestr`——即不允许成环，否则 sentry 刷新时会无限递归。
- **`rdbuf(sb)`**：¶6 **会调用 `clear()`**，¶7 后条件 `sb == rdbuf()`。传入空指针时，`clear()` 会因为 `rdbuf()` 为空而把状态设成 `badbit`。
- **`imbue(loc)`**：¶9 调用 `ios_base::imbue(loc)`，若 `rdbuf()` 非空再调用 `rdbuf()->pubimbue(loc)`。
- **`narrow`/`widen`**：¶11–¶12 委托给 `use_facet<ctype<char_type>>(getloc())`。
- **`fill`**：¶13–¶15 填充字符（`charT` 类型，所以在 `basic_ios` 而不在 `ios_base`）。

```cpp title="rdbuf-null.cpp" ok
#include <iostream>

int main() {
  std::ostream os(nullptr);              // init(nullptr)：rdstate() == badbit
  std::cout << os.bad() << ' ';          // 1
  os.clear();                            // rdbuf() 为空：clear 后 badbit 仍在
  std::cout << os.bad() << ' ';          // 1
  os.rdbuf(std::cout.rdbuf());           // rdbuf(sb) 内部调用 clear()
  std::cout << os.bad() << '\n';         // 0
  os << "now writes to stdout\n";
}
```

### `copyfmt`（¶16–¶19）

`copyfmt(rhs)` 复制"格式"而不复制"状态"和"连接"。若 `this == addressof(rhs)` 什么也不做；否则按顺序：

1. ¶16.1 以 `erase_event` 调用 `*this` 的每个回调（让它们释放 `pword` 指向的资源）；
2. ¶16.2 把 `rhs` 的成员赋给 `*this`，但 **`rdstate()`、`rdbuf()`、`exceptions()` 保持不变**；`iword`/`pword` 数组复制的是**内容**而不是指针；若新存入的指针指向 `rhs` 外部、会随 `rhs` 销毁的对象，则改为指向新构造的副本；
3. ¶16.3 以 `copyfmt_event` 调用从 `rhs` 复制来的每个回调——¶17（注）这第二轮回调让程序有机会把复制来的 `pword` 置空、深拷贝其所指对象或增加引用计数；
4. ¶16.4 最后调用 `exceptions(rhs.exceptions())`。

为什么异常掩码要放到最后单独设置？因为 `exceptions(m)` 会立刻检查当前状态并可能抛异常（下一节）；放在最后保证抛异常时其他格式已经复制完毕。表 143 总结：除 `rdbuf()`、`rdstate()` 不变外，`tie`、`exceptions`、`flags`、`width`、`precision`、`fill`、`getloc` 都等于 `rhs` 的。

一个常见用法是"保存/恢复格式"：

```cpp title="save-format.cpp" ok
#include <iomanip>
#include <iostream>

int main() {
  std::ios saved(nullptr);
  saved.copyfmt(std::cout);                        // 保存
  std::cout << std::hex << std::showbase << std::setfill('*') << std::setw(8) << 255 << '\n';
  std::cout.copyfmt(saved);                        // 恢复
  std::cout << std::setw(8) << 255 << '\n';        // "     255"
}
```

### `move`、`swap`、`set_rdbuf`（¶20–¶25）

这三个受保护成员是给派生流类实现移动语义用的：

- `move(rhs)`：`*this` 得到 `rhs` 原来的状态，**但 `rdbuf()` 为空**；`rhs` 处于有效但未指定的状态，只是 `rhs.rdbuf()` 不变、`rhs.tie()` 为空。
- `swap(rhs)`：交换状态，**但双方的 `rdbuf()` 不变**。
- `set_rdbuf(sb)`：前置条件 `sb != nullptr`；关联 `sb` 但**不调用 `clear()`**（与公有的 `rdbuf(sb)` 不同），不抛异常。

为什么 `rdbuf` 不跟着走？因为 `ifstream` 这类流把 `filebuf` 作为自己的数据成员；移动时 `filebuf` 由派生类自己移动，然后用 `set_rdbuf` 指向**新对象内的** `filebuf`（[[file.streams]]、[[string.streams]] 的移动构造函数都是这样写的）。若 `basic_ios::move` 照搬指针，新流就会指向旧对象里的 buf。

## 状态函数（[iostate.flags]）

| 函数 | 规定 |
|---|---|
| `explicit operator bool()` | ¶1 `!fail()` |
| `operator!()` | ¶2 `fail()` |
| `rdstate()` | ¶3 当前错误状态 |
| `clear(state = goodbit)` | ¶4–¶5 见下 |
| `setstate(state)` | ¶6 `clear(rdstate() | state)` |
| `good()` | ¶7 `rdstate() == 0` |
| `eof()` | ¶8 `eofbit` 置位 |
| `fail()` | ¶9 `failbit` **或** `badbit` 置位 |
| `bad()` | ¶10 `badbit` 置位 |
| `exceptions()` | ¶11 决定哪些状态位会导致抛异常的掩码 |
| `exceptions(except)` | ¶12 调用 `clear(rdstate())`；¶13 后条件 `except == exceptions()` |

注意三处不对称：

1. **`operator bool` 不看 `eofbit`。** 它就是 `!fail()`。`"42"` 读成功后 `eof()` 为真但流仍为"真"——这正是 `while (in >> x)` 正确、`while (!in.eof())` 错误的原因（[[input.streams]]）。
2. **`fail()` 也包含 `badbit`。** 脚注说这是"历史惯例"。所以 `fail()` 为真不代表 `failbit` 一定置位。
3. **`good()` 不是 `operator bool`。** `good()` 要求三个位都为 0，`eof` 状态下 `good()` 为假而 `operator bool` 为真。

### `clear` 与异常（¶4–¶5）

```cpp
void clear(iostate state = goodbit);
```

¶4：若 `(state | (rdbuf() ? goodbit : badbit)) & exceptions()` 为 0，直接返回；否则抛出 `ios_base::failure`（构造实参由实现定义）。¶5：后条件——`rdbuf()` 非空时 `state == rdstate()`，否则 `rdstate() == (state | badbit)`。

¶4 只说"若…返回，否则抛出"，¶5 的后条件则描述状态被设成什么。主流实现都是**先写入状态，再判断是否抛**，所以在 `catch` 里看到的流状态已经是新状态（下面的 `exceptions-loop.cpp` 在 `catch` 中读到 `eof() == 1`）。

由此推出一个常让人意外的行为：**`exceptions(m)` 会立即抛异常**——如果当前状态里已经有 `m` 中的位：

```cpp title="exceptions-immediate.cpp" ok
#include <iostream>
#include <sstream>

int main() {
  std::istringstream in("abc");
  int x;
  in >> x;                                    // 失败：failbit，默认不抛
  try {
    in.exceptions(std::ios_base::failbit);    // 等价于 clear(rdstate())：立即抛
  } catch (const std::ios_base::failure& e) {
    std::cout << (e.code() == std::io_errc::stream) << ' '
              << e.code().category().name() << '\n';    // 1 iostream
  }
}
```

!!! pitfall "打开 `failbit` 异常会让读循环在结尾抛出"
    `in.exceptions(std::ios_base::failbit)` 之后，`while (in >> x)` 读到流尾的那一次提取会置 `failbit | eofbit`，于是**抛出**而不是让循环条件变假。想用异常报告真正的错误（格式错误、I/O 错误），通常只打开 `badbit`，或者把 `failbit` 异常与"读到流尾"区分开来处理。

    ```cpp title="exceptions-loop.cpp" ok
    #include <iostream>
    #include <sstream>

    int main() {
      std::istringstream in("1 2 3");
      in.exceptions(std::ios_base::failbit);
      int x, sum = 0;
      try {
        while (in >> x) sum += x;
      } catch (const std::ios_base::failure&) {
        std::cout << "threw at end, sum=" << sum << " eof=" << in.eof() << '\n';  // sum=6 eof=1
      }
    }
    ```

## `ios_base` 操纵符（[std.ios.manip]）

四个子条款（[fmtflags.manip]、[adjustfield.manip]、[basefield.manip]、[floatfield.manip]）的规定完全机械：每个操纵符 `m(str)` 调用 `str.setf(...)` 或 `str.unsetf(...)` 并返回 `str`。

| 操纵符 | 效果 |
|---|---|
| `boolalpha` / `noboolalpha`、`showbase` / `noshowbase`、`showpoint` / `noshowpoint`、`showpos` / `noshowpos`、`skipws` / `noskipws`、`uppercase` / `nouppercase`、`unitbuf` / `nounitbuf` | `setf(flag)` / `unsetf(flag)` |
| `internal`、`left`、`right` | `setf(flag, adjustfield)` |
| `dec`、`hex`、`oct` | `setf(flag, basefield)` |
| `fixed`、`scientific` | `setf(flag, floatfield)` |
| `hexfloat` | `setf(fixed | scientific, floatfield)` |
| `defaultfloat` | `unsetf(floatfield)` |

几个细节：

- 每个子条款的 ¶1 都说这些函数是**指定可寻址函数**（designated addressable function，[[namespace.std]]）——所以 `&std::hex` 是良构且可移植的，可以存进函数指针；绝大多数标准库函数不允许取地址。
- [floatfield.manip] ¶8（注）：`ios_base::hex` 不能用来指定十六进制浮点格式，因为它不属于 `floatfield`。`hexfloat` 是用 `fixed | scientific` **两位同时置位**来编码的。
- 它们之所以能写成 `cout << hex`，是因为 `basic_ostream` 有一个接受 `ios_base& (*)(ios_base&)` 的 `operator<<`（[[ostream.inserters]]）。

```cpp title="hexfloat.cpp" ok
#include <iostream>

int main() {
  std::cout << std::hexfloat << 1.0 << '\n';      // 0x1p+0
  std::cout << std::defaultfloat << std::hex;
  std::cout << 1.5 << ' ' << 255 << '\n';         // 1.5 ff：hex 只影响整数
}
```

## 错误报告（[error.reporting]）

```cpp
enum class io_errc { stream = 1 };
template<> struct is_error_code_enum<io_errc> : true_type {};
error_code      make_error_code(io_errc e) noexcept;       // ¶1 error_code(int(e), iostream_category())
error_condition make_error_condition(io_errc e) noexcept;  // ¶2
const error_category& iostream_category() noexcept;        // ¶3–¶4
```

¶4：`iostream_category()` 的 `name()` 返回 `"iostream"`，`default_error_condition` 与 `equivalent` 的行为同 `error_category` 的默认规定（[[syserr]]）。由于 `is_error_code_enum<io_errc>` 为真，`io_errc::stream` 可以隐式转换为 `error_code`——这就是 `failure` 构造函数默认实参 `ec = io_errc::stream` 能编译的原因。

## 思考题

<details markdown="1">
<summary>1. 下面的 <code>if</code> 会进入哪个分支？<code>std::istringstream in("7"); int x; in &gt;&gt; x; if (in.good()) ... else if (in) ... else ...</code></summary>

进入 `else if (in)`。读 `7` 时为了确认数字结束，`num_get` 读到了流尾，置 `eofbit`，所以 `good()` 为假；但提取成功，`failbit` 未置位，`operator bool`（即 `!fail()`）为真（[[iostate.flags#1]]、[[iostate.flags#7]]）。
</details>

<details markdown="1">
<summary>2. <code>a.copyfmt(b)</code> 之后，<code>a</code> 处于 <code>failbit</code> 状态而 <code>b.exceptions() == failbit</code>。会发生什么？</summary>

`copyfmt` 不复制 `rdstate()`，所以 `a` 仍处于 `failbit` 状态；它最后一步调用 `exceptions(rhs.exceptions())`（[[basic.ios.members#16]] ¶16.4），后者调用 `clear(rdstate())`，发现 `failbit & exceptions()` 非零，于是抛出 `ios_base::failure`。此时 `flags`、`fill`、`iword` 等已经复制完毕。
</details>

<details markdown="1">
<summary>3. 为什么 <code>basic_ios</code> 的析构函数不 <code>delete rdbuf()</code>，而 <code>ifstream</code> 析构时文件却会被关闭？</summary>

[[basic.ios.cons#3]] 规定 `~basic_ios` 不销毁 `rdbuf()`——流与 streambuf 是"使用"关系，同一个 streambuf 可以被多个流共享（例如 `std::ostream log(std::cout.rdbuf());`）。`ifstream` 则把一个 `basic_filebuf` 作为**自己的数据成员**（说明专用的 `sb`），这个成员随 `ifstream` 析构，而 `~basic_filebuf` 调用 `close()`（[[filebuf.cons#5]]）。
</details>

## 小结

| 主题 | 要点 |
|---|---|
| 两层 | `ios_base`（与 `charT` 无关）＋ `basic_ios`（状态位、`fill`、`tie`、`rdbuf`） |
| 状态位 | `eofbit`＝撞到了末尾；`failbit`＝没得到期望的值；`badbit`＝流已损坏；`operator bool`＝`!fail()` |
| 异常 | `clear`/`setstate`/`exceptions(m)` 都可能抛；`exceptions(m)` 会对已有状态立即抛 |
| 格式 | 除 `width` 外的格式状态都是"粘"的；`setf(f)` 不清同组位，要用 `setf(f, mask)` 或操纵符 |
| 私有存储 | `xalloc` + `iword`/`pword` 让自定义格式附着在流上；`copyfmt` 复制内容并触发回调 |
| `init` | 状态 `goodbit`（buf 为空则 `badbit`）、`skipws|dec`、精度 6、填充空格、无 tie、无异常 |
| `fpos` | 偏移量＋转换状态；`pos_type(-1)` 是错误值，传回给流成员是 UB |
