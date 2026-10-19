---
title: iostream 基类：ios_base、basic_ios 与 fpos
summary: 所有流共有的状态：eofbit、failbit、badbit 各在什么时候置位，operator bool 只看 fail()；异常掩码与 exceptions() 立即抛出；格式标志与 setf 的两个重载；copyfmt、xalloc/iword/pword 与回调；basic_ios::init 的初始值；fpos 与无效位置 -1。
status: done
covers: *
related: input.output, iostream.objects, stream.buffers, input.streams, output.streams, iostream.format, syserr, bitmask.types, localization, iostreams.requirements
tags: 标准库, iostream, 状态位, 格式标志, 异常
updated: 2026-10-19
---

!!! tldr
    - `eofbit` 表示某次输入撞到了末尾，`failbit` 表示没有得到期望的值，`badbit` 表示流已经损坏。三者相互独立：读 `"42"` 成功后 `eof()` 为真，流仍然为真。
    - `if (in)` 和 `while (in >> x)` 测试的是 `!fail()`，不看 `eofbit`；`good()` 要求三个位都没有置位。
    - 打开异常掩码后，`clear`、`setstate` 会在状态命中掩码时抛出 `ios_base::failure`；`exceptions(m)` 对已有的状态会立即抛出。
    - 格式标志除宽度外一直生效。单参数的 `setf(hex)` 不清除同组的 `dec`，要用 `setf(hex, basefield)` 或操纵符 `std::hex`。
    - `copyfmt` 复制格式不复制状态，`xalloc`/`iword`/`pword` 让自定义格式附着在流上；`tellg()` 失败返回的 `pos_type(-1)` 再传给流的成员是未定义行为。

## `ios_base` 与 `basic_ios`

每个流对象的状态分放在两个基类里。

`ios_base` 是普通的类，不是模板，保存与字符类型无关的状态：格式标志、宽度、精度、`locale`、供程序私用的存储（`iword`/`pword`）、回调列表。它还定义了四个嵌套类型 `fmtflags`、`iostate`、`openmode`、`seekdir`。

`basic_ios<charT, traits>` 派生自 `ios_base`，加上与字符类型有关的状态：错误状态位、异常掩码、填充字符（类型是 `charT`）、绑定的输出流 `tie()`，以及指向流缓冲区的 `rdbuf()`。

与 `charT` 无关的部分放进非模板的基类，`std::hex` 这类操纵符就只需写一份：它的签名是 `ios_base& hex(ios_base&)`，对 `cout` 和 `wcout` 都适用。

`fmtflags`、`iostate`、`openmode` 是**位掩码类型**（[[g:bitmask-type]]，[[bitmask.types]]）：每个常量代表一个或一组位，可以用 `|`、`&`、`^`、`~` 组合。具体是整数还是枚举由实现决定，概要里写作 `T1`、`T2`、`T3`，所以不要假设 `fmtflags` 就是 `int`。

## 错误状态

### 三个状态位 [ios.iostate]

```cpp run ok
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
  probe("42");           // x=42 good=0 eof=1 fail=0 bool=1   成功，但撞到了末尾
  probe("abc");          // x=0  good=0 eof=0 fail=1 bool=0   转换失败，x 被置 0
  probe("");             // x=-1 good=0 eof=1 fail=1 bool=0   sentry 就失败了，x 不变
  probe("99999999999");  // x=2147483647 good=0 eof=1 fail=1  溢出：failbit，x 取最大值
}
```

注释是本机的输出。逐行看：

- `"42"`：为了确认数字已经结束，`num_get` 必须再读一个字符，结果读到了末尾，于是置 `eofbit`。值成功得到，不置 `failbit`，所以 `if (in >> x)` 为真。
- `"abc"`：转换失败时 `num_get` 把值置为 0（[[facet.num.get.virtuals]]）。
- `""`：格式化输入的 sentry 在跳过空白时就撞到了末尾，置 `failbit | eofbit`（[[istream.sentry#2]]），根本没有调用 `num_get`，所以 `x` 保持 `-1`。
- 溢出：`operator>>(int&)` 先读成 `long` 再检查范围，超出时置 `failbit`，存入 `numeric_limits<int>::max()`（[[istream.formatted.arithmetic#3]]）。本机的 `long` 是 64 位，`99999999999` 能读进 `long`，在这一步被截断。

¶1 `iostate` 有三个元素（表 138），¶2 另有常量 `goodbit`，值为零：

| 元素 | 标准的定义 | 典型的触发场景 |
|---|---|---|
| `badbit` | 输入或输出序列失去完整性，例如读文件时发生不可恢复的错误 | 流缓冲区抛出异常；`rdbuf()` 为空 |
| `eofbit` | 某个输入操作到达了输入序列的末尾 | 提取时流缓冲区报告没有更多字符 |
| `failbit` | 输入操作没能读到期望的字符，或输出操作没能生成期望的字符 | 数值格式错误、溢出、一个字符都没提取到、`seekg` 失败 |

### 查询和设置状态 [iostate.flags]

| 函数 | 规定 |
|---|---|
| `explicit operator bool()` | ¶1 返回 `!fail()` |
| `operator!()` | ¶2 返回 `fail()` |
| `rdstate()` | ¶3 当前错误状态 |
| `clear(state = goodbit)` | ¶4–¶5 把状态设为 `state`，见下一节 |
| `setstate(state)` | ¶6 调用 `clear(rdstate() | state)` |
| `good()` | ¶7 `rdstate() == 0` |
| `eof()` | ¶8 `eofbit` 已置位 |
| `fail()` | ¶9 `failbit` 或 `badbit` 已置位 |
| `bad()` | ¶10 `badbit` 已置位 |

这张表有三处不对称，都要记住。

1. `operator bool` 不看 `eofbit`，它就是 `!fail()`。读 `"42"` 成功后 `eof()` 为真，流仍然为真。所以 `while (in >> x)` 是正确的读循环，`while (!in.eof())` 是错误的（[[input.output]]）。
2. `fail()` 也包含 `badbit`，脚注说这是历史惯例。`fail()` 为真，不说明 `failbit` 一定置位了。
3. `good()` 不等于 `operator bool`。`eof` 状态下 `good()` 为假，`operator bool` 为真。

### 异常掩码

默认情况下，流出错只设置状态位，不抛异常。`exceptions(m)` 设置一个**异常掩码**：此后状态一旦包含 `m` 中的位，就抛出 `ios_base::failure`。

```cpp
void clear(iostate state = goodbit);
```

¶4 如果 `(state | (rdbuf() ? goodbit : badbit)) & exceptions()` 为 0，直接返回；否则抛出 `ios_base::failure`，构造它的实参由实现定义。¶5 后条件：`rdbuf()` 非空时 `rdstate() == state`，否则 `rdstate() == (state | badbit)`。所以流缓冲区为空的流，`clear()` 之后仍然处于 `badbit` 状态。

主流实现都是先写入新状态，再判断是否抛出，所以在 `catch` 里看到的已经是新状态。

¶12 `exceptions(except)` 设置掩码后调用 `clear(rdstate())`，¶13 后条件是 `exceptions() == except`。这意味着如果流此刻已经处于某个被掩码选中的状态，`exceptions(m)` 会立即抛出：

```cpp run ok
#include <iostream>
#include <sstream>

int main() {
  std::istringstream in("abc");
  int x;
  in >> x;                                    // 失败：failbit，默认不抛
  try {
    in.exceptions(std::ios_base::failbit);    // 调用 clear(rdstate())：立即抛出
  } catch (const std::ios_base::failure& e) {
    std::cout << (e.code() == std::io_errc::stream) << ' '
              << e.code().category().name() << '\n';    // 1 iostream
  }
}
```

!!! pitfall "打开 `failbit` 异常后，读循环会在末尾抛出"
    `in.exceptions(std::ios_base::failbit)` 之后，`while (in >> x)` 读到末尾的那一次提取会置 `failbit | eofbit`，于是抛出异常，而不是让循环条件变假。想用异常报告真正的错误，通常只打开 `badbit`，或者在 `catch` 里检查 `eof()`，把读到末尾和格式错误区分开。

    ```cpp run ok
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

### `ios_base::failure` 与错误码 [ios.failure]、[error.reporting]

```cpp
class ios_base::failure : public system_error {
public:
  explicit failure(const string& msg, const error_code& ec = io_errc::stream);
  explicit failure(const char* msg, const error_code& ec = io_errc::stream);
};
```

[ios.failure] ¶1 `failure` 是 iostream 库为报告流缓冲区操作中的错误而抛出的所有异常的基类。C++11 起它派生自 `system_error`（此前派生自 `exception`），所以 `catch (const std::system_error&)` 也能捕获它，并且可以用 `e.code()` 区分原因。实现也可以把它定义成某个功能等价的类的别名。

¶2 抛出时，实现应当给出能说明具体原因的 `ec`。注 2 举例：来自操作系统的错误一般是 `system_category()` 的错误码，来自流库内部的一般是 `error_code(io_errc::stream, iostream_category())`。

[error.reporting] 定义了这套错误码：

```cpp
enum class io_errc { stream = 1 };
template<> struct is_error_code_enum<io_errc> : true_type {};
error_code      make_error_code(io_errc e) noexcept;       // ¶1
error_condition make_error_condition(io_errc e) noexcept;  // ¶2
const error_category& iostream_category() noexcept;        // ¶3–¶4
```

¶4 `iostream_category()` 的 `name()` 返回 `"iostream"`。因为 `is_error_code_enum<io_errc>` 为真，`io_errc::stream` 可以隐式转换为 `error_code`，`failure` 构造函数的默认实参 `ec = io_errc::stream` 正是靠这一点编译通过的（[[syserr]]）。

## 格式状态

### 格式标志 [ios.fmtflags]

¶1 `fmtflags` 的元素及置位时的效果（表 136）：

| 元素 | 置位时的效果 |
|---|---|
| `boolalpha` | `bool` 按字母形式（`true`/`false`）插入和提取 |
| `dec` / `oct` / `hex` | 整数按十、八、十六进制读写 |
| `fixed` / `scientific` | 浮点数按定点或科学记法输出 |
| `left` / `right` / `internal` | 填充字符放在右侧、左侧，或内部的指定位置（如符号与数字之间） |
| `showbase` | 整数输出带进制前缀（`0`、`0x`） |
| `showpoint` | 浮点数输出总是带小数点 |
| `showpos` | 非负数输出带 `+` |
| `skipws` | 某些输入操作之前跳过前导空白 |
| `unitbuf` | 每次输出操作之后刷新 |
| `uppercase` | 输出中的某些小写字母换成大写（`0X`、`1E+10`、十六进制数字） |

¶2 表 137 定义了三个组合常量：`adjustfield = left | right | internal`，`basefield = dec | oct | hex`，`floatfield = scientific | fixed`。同一组里的位在语义上互斥，但它们是独立的位，这是 `setf` 有两个重载的原因。

### `setf` 的两个重载 [fmtflags.state]

```cpp run ok
#include <iostream>

int main() {
  std::cout.setf(std::ios_base::hex);                          // dec 仍然置位
  std::cout << 255 << '\n';                                    // 255
  std::cout.setf(std::ios_base::hex, std::ios_base::basefield);
  std::cout << 255 << '\n';                                    // ff
}
```

¶4 单参数的 `setf(f)` 只是把 `f` 或上去。流初始就有 `dec`，于是 `basefield` 里同时有 `dec` 和 `hex`。`num_put` 判断进制时，比较的是 `flags() & basefield` 是否等于 `oct` 或 `hex`（[[facet.num.put.virtuals]]），两个位同时置位时都不相等，于是落回十进制。

¶6 双参数的 `setf(f, mask)` 先清除 `mask` 中的所有位，再置位 `f & mask`。操纵符 `std::hex` 内部调用的就是这个版本（[[basefield.manip]]），所以用操纵符不会遇到这个问题。

其余的格式状态函数：

| 函数 | 效果 | 返回 |
|---|---|---|
| `flags()` / `flags(f)` | 读取 / 全部替换为 `f` | 当前值 / 旧值 |
| `unsetf(mask)` | 清除 `mask` 中的位 | 无 |
| `precision()` / `precision(p)` | 某些输出转换的精度 | 当前值 / 旧值 |
| `width()` / `width(w)` | 某些输出转换的最小字段宽度 | 当前值 / 旧值 |

精度的含义随 `floatfield` 而变：默认记法下是有效数字的位数，`fixed` 或 `scientific` 下是小数点后的位数。初始值是 6。

```cpp run ok
#include <iostream>

int main() {
  std::cout.precision(3);
  std::cout << 1234.5678 << ' ';                    // 1.23e+03（3 位有效数字）
  std::cout << std::fixed << 1234.5678 << ' ';      // 1234.568
  std::cout << std::scientific << 1234.5678 << '\n';// 1.235e+03
}
```

### 操纵符 [std.ios.manip]

四个子条款 [fmtflags.manip]、[adjustfield.manip]、[basefield.manip]、[floatfield.manip] 的规定很机械：每个操纵符 `m(str)` 调用 `str.setf(...)` 或 `str.unsetf(...)`，然后返回 `str`。

| 操纵符 | 效果 |
|---|---|
| `boolalpha` / `noboolalpha`、`showbase` / `noshowbase`、`showpoint` / `noshowpoint`、`showpos` / `noshowpos`、`skipws` / `noskipws`、`uppercase` / `nouppercase`、`unitbuf` / `nounitbuf` | `setf(flag)` / `unsetf(flag)` |
| `internal`、`left`、`right` | `setf(flag, adjustfield)` |
| `dec`、`hex`、`oct` | `setf(flag, basefield)` |
| `fixed`、`scientific` | `setf(flag, floatfield)` |
| `hexfloat` | `setf(fixed | scientific, floatfield)` |
| `defaultfloat` | `unsetf(floatfield)` |

能写成 `cout << hex`，是因为 `basic_ostream` 有一个接受 `ios_base& (*)(ios_base&)` 的 `operator<<`（[[ostream.inserters]]）。

每个子条款的 ¶1 都说这些函数是指定可寻址函数（designated addressable function，[[namespace.std]]），所以 `&std::hex` 是良构、可移植的，可以存进函数指针。绝大多数标准库函数不允许取地址。

[floatfield.manip] ¶8 的注说明，`ios_base::hex` 不能用来指定十六进制浮点格式，因为它不属于 `floatfield`。十六进制浮点用 `fixed` 和 `scientific` 两位同时置位来表示：

```cpp run ok
#include <iostream>

int main() {
  std::cout << std::hexfloat << 1.0 << '\n';      // 0x1p+0
  std::cout << std::defaultfloat << std::hex;
  std::cout << 1.5 << ' ' << 255 << '\n';         // 1.5 ff：hex 只影响整数
}
```

### locale [ios.base.locales]

¶1 `imbue(loc)` 以 `(*fn)(imbue_event, *this, idx)` 调用每个已注册的回调，调用时 `getloc()` 已经返回新的 locale。¶2 后条件是 `getloc() == loc`，¶3 返回旧值。

¶4 如果从未 imbue 过，`getloc()` 返回流构造时全局 C++ locale `locale()` 的副本。所以之后再调用 `std::locale::global(...)`，不会影响已经存在的流，包括 `cout`。

`basic_ios::imbue` 除了调用 `ios_base::imbue`，还会在 `rdbuf()` 非空时调用 `rdbuf()->pubimbue(loc)`（[[basic.ios.members#9]]）；`ios_base::imbue` 不会通知流缓冲区。

## `basic_ios` [ios]

### 初始状态与 `init` [basic.ios.cons]

¶1 `explicit basic_ios(basic_streambuf* sb)` 调用 `init(sb)`。¶4 `init(sb)` 的后条件见表 142：

| 成员 | `init` 之后的值 |
|---|---|
| `rdbuf()` | `sb` |
| `tie()` | 空 |
| `rdstate()` | `sb` 非空则为 `goodbit`，否则为 `badbit` |
| `exceptions()` | `goodbit`，即不抛任何异常 |
| `flags()` | `skipws | dec` |
| `width()` | 0 |
| `precision()` | 6 |
| `fill()` | `widen(' ')` |
| `getloc()` | `locale()` 的副本 |
| `iarray` / `parray` | 空指针 |

¶2 受保护的默认构造函数 `basic_ios()` 不初始化任何成员。必须在第一次使用或析构之前（以先到者为准）调用 `init`，否则行为未定义。[[ios.base.cons#1]] 对 `ios_base()` 有同样的规定。

为什么要这样两步构造？`basic_ios` 是 `basic_istream`、`basic_ostream` 的虚基类，虚基类由最终派生类构造（[[iostream.objects]]）。各个中间类调用什么也不做的默认构造函数，再由自己的构造函数调用 `init`。

¶3 析构函数不销毁 `rdbuf()`。流不拥有它的流缓冲区，同一个流缓冲区可以被几个流共用，例如 `std::ostream log(std::cout.rdbuf());`。`ifstream` 析构时文件会关闭，是因为它把一个 `basic_filebuf` 作为自己的数据成员持有，这个成员随它析构，而 `~basic_filebuf` 调用 `close()`（[[filebuf.cons#5]]）。

### 成员函数 [basic.ios.members]

```cpp run ok
#include <iostream>

int main() {
  std::ostream os(nullptr);              // init(nullptr)：rdstate() == badbit
  std::cout << os.bad() << ' ';          // 1
  os.clear();                            // rdbuf() 为空：clear 之后 badbit 仍在
  std::cout << os.bad() << ' ';          // 1
  os.rdbuf(std::cout.rdbuf());           // rdbuf(sb) 内部调用 clear()
  std::cout << os.bad() << '\n';         // 0
  os << "now writes to stdout\n";
}
```

¶6 `rdbuf(sb)` 会调用 `clear()`，¶7 后条件是 `rdbuf() == sb`。传入空指针时，`clear()` 因为 `rdbuf()` 为空而把状态设为 `badbit`。

¶1 `tie()` 返回与本流**绑定**（tie）的输出流（[[g:tied-stream]]）：本流的每次输入输出之前，sentry 先刷新这个流。¶2 设置时的前置条件是，从 `tiestr->tie()` 出发沿绑定链走下去不能回到 `tiestr`。绑定不能成环，否则刷新会无限递归。

¶9 `imbue(loc)` 见上一节。¶11–¶12 `narrow`、`widen` 委托给 `use_facet<ctype<char_type>>(getloc())`。¶13–¶15 `fill` 读写填充字符，它的类型是 `charT`，所以在 `basic_ios` 里而不在 `ios_base` 里。

### `copyfmt`（¶16–¶19）

`copyfmt(rhs)` 复制格式，不复制状态和连接。常见的用途是保存和恢复格式：

```cpp run ok
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

¶16 如果 `this == addressof(rhs)`，什么也不做；否则依次：

1. ¶16.1 以 `erase_event` 调用 `*this` 的每个回调，让它们释放 `pword` 指向的资源；
2. ¶16.2 把 `rhs` 的成员赋给 `*this`，但 `rdstate()`、`rdbuf()`、`exceptions()` 保持不变；`iword`/`pword` 数组复制的是内容而不是指针；如果新存入的指针指向 `rhs` 之外、会随 `rhs` 销毁的对象，就改为指向新构造的副本；
3. ¶16.3 以 `copyfmt_event` 调用从 `rhs` 复制来的每个回调。¶17 的注说明，这第二轮回调让程序有机会把复制来的 `pword` 置空、深拷贝它指向的对象，或者增加引用计数；
4. ¶16.4 最后调用 `exceptions(rhs.exceptions())`。

异常掩码放到最后单独设置，是因为 `exceptions(m)` 可能立即抛出。放在最后，抛出时其他格式已经复制完毕。¶18 的表 143 总结了结果：`rdbuf()` 和 `rdstate()` 不变，`tie`、`exceptions`、`flags`、`width`、`precision`、`fill`、`getloc` 都等于 `rhs` 的。

### `move`、`swap`、`set_rdbuf`（¶20–¶25）

这三个受保护的成员供派生的流类实现移动操作：

- ¶20 `move(rhs)`：`*this` 得到 `rhs` 原来的状态，但 `rdbuf()` 为空。`rhs` 处于有效但未指定的状态，只是 `rhs.rdbuf()` 不变、`rhs.tie()` 为空。
- ¶21 `swap(rhs)`：交换状态，但双方的 `rdbuf()` 都不变。
- ¶22–¶25 `set_rdbuf(sb)`：前置条件是 `sb` 非空；关联 `sb` 但不调用 `clear()`，这一点与公有的 `rdbuf(sb)` 不同；不抛异常。

`rdbuf` 不跟着移动，是因为 `ifstream`、`stringstream` 这类流把流缓冲区作为自己的数据成员。移动时流缓冲区由派生类自己移动，然后用 `set_rdbuf` 指向新对象里的那个流缓冲区（[[file.streams]]、[[string.streams]]）。如果 `basic_ios::move` 照搬指针，新的流就会指向旧对象里的缓冲区。

## 自定义格式状态

### `xalloc`、`iword`、`pword` [ios.base.storage]

这组函数让用户定义的格式状态也能像 `std::hex` 一样附着在流上：

```cpp run ok
#include <iostream>
#include <sstream>

const int style_slot = std::ios_base::xalloc();   // 进程内唯一的下标

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

¶1 `static int xalloc()` 返回一个全局唯一的新下标。¶2 多个线程并发调用它不构成数据竞争。

¶3–¶5 `long& iword(int idx)` 的前置条件是 `idx` 来自 `xalloc()`。它按需扩展内部的 `long` 数组，新元素初始化为 0，返回 `idx` 处元素的引用。¶6–¶8 `void*& pword(int idx)` 相同，只是数组元素是指针，初始化为空指针。

返回的引用在对这个流对象做任何其他操作之后就失效了，但值本身保留：下次用同一个下标调用，得到的是同一个值，直到下一次 `copyfmt`。所以每次都重新调用 `iword(slot)`，不要保存它返回的引用。

如果扩展数组失败（例如分配不到内存），而 `*this` 是某个 `basic_ios` 对象的基类子对象，效果等同于对那个对象调用 `setstate(badbit)`，并返回一个值为 0 的有效引用。

`pword` 存的是 `void*`。如果它指向一个归流所有的堆对象，就要配合下面的回调处理释放和深拷贝，否则 `copyfmt` 之后两个流持有同一个指针，析构时无法确定由谁释放。

### 回调 [ios.base.callback]

```cpp
enum event { erase_event, imbue_event, copyfmt_event };
using event_callback = void (*)(event, ios_base&, int idx);
void register_callback(event_callback fn, int idx);
```

¶1 前置条件：`fn` 不抛异常。

¶2 注册 `(fn, idx)`，此后在 `imbue()`、`copyfmt()`、`~ios_base()` 期间以 `idx` 调用 `fn`。事件发生时，按注册的相反顺序调用；在某个回调执行期间注册的新回调，要到下一次事件才会被调用。

¶3 相同的 `(fn, idx)` 不会合并，注册两次就调用两次。

[ios.base.cons] ¶2 `~ios_base()` 先以 `erase_event` 调用每个回调，此时在回调里调用 `ios_base` 的成员函数，结果是确定的；然后释放 `iword`/`pword` 占用的内存。

## 打开模式与定位

### `openmode` 和 `seekdir` [ios.openmode]、[ios.seekdir]

| `openmode` 元素 | 效果 |
|---|---|
| `app` | 每次写之前定位到末尾 |
| `ate` | 打开后立即定位到末尾 |
| `binary` | 以二进制模式（而不是文本模式）读写 |
| `in` / `out` | 为输入 / 输出打开 |
| `noreplace` {{c++23}} | 以独占模式打开：文件已存在则失败 |
| `trunc` | 打开时截断已有内容 |

这些组合如何对应到 `fopen` 的模式串，见 [[file.streams]]；对字符串流和 span 流，`in`、`out`、`ate` 决定 get 区和 put 区怎样初始化（[[string.streams]]）。

`seekdir` 是枚举类型（[[enumerated.types]]），有三个值：`beg` 相对开头，`cur` 相对当前位置，`end` 相对当前的末尾。

### `fpos` [fpos]

```cpp
template<class stateT> class fpos {
public:
  stateT state() const;
  void state(stateT);
private:
  stateT st;          // 仅用于说明
};
```

`fpos` 表示文件中的位置：一个能与 `streamoff` 互相转换的偏移量，加上一个转换状态 `st`，`char` 流的转换状态是 `mbstate_t`。在状态相关的多字节编码里，同一个字节偏移处的字节怎样解释，取决于此前的移位状态；回到某个位置时，必须连同状态一起恢复。

[fpos.operations] ¶1 的表 141 规定了 `fpos` 必须支持的运算。用 `P` 表示 `fpos` 的特化，`O` 表示 `streamoff`：

| 表达式 | 含义 |
|---|---|
| `P(o)`、`P p(o)`、`P p = o` | 从偏移量构造，状态值初始化 |
| `P()`、`P p;` | 等于 `P(0)` |
| `O(p)` | 转换回偏移量，`P(O(p)) == p` |
| `p == q`、`p != q` | 比较 |
| `p + o`、`p += o`、`p - o`、`p -= o`、`o + p` | 位置加减偏移 |
| `p - q` | 两个位置的距离，类型是 `streamoff` |

¶1 还要求 `stateT` 满足 *Cpp17DefaultConstructible*、*Cpp17CopyConstructible*、*Cpp17CopyAssignable*、*Cpp17Destructible*。`stateT` 的复制构造、复制赋值、析构是平凡的，`fpos` 的对应成员也是平凡的。

¶2 返回 `traits::pos_type` 的流操作用 `P(O(-1))` 作为无效值报告错误。把这个值再传给任何接受 `pos_type` 的 `istream`、`ostream` 或 `streambuf` 成员，行为未定义。所以 `seekg(tellg())` 在 `tellg()` 失败时是未定义行为，使用之前要先检查：

```cpp run ok
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

## 标准流对象相关的成员

`ios_base::Init`（[ios.init]）的构造保证 `<iostream>` 中的八个标准流对象已经构造，析构函数在没有其他 `Init` 对象存活时刷新输出流。静态成员 `sync_with_stdio`（[ios.members.static]）控制标准流是否与 C 的 stdio 同步。两者都只与标准流对象有关，详见 [[iostream.objects]]。

## 思考题

!!! question "思考题 1"
    下面的 `if` 会进入哪个分支？
    ```cpp
    std::istringstream in("7");
    int x;
    in >> x;
    if (in.good()) { /* A */ } else if (in) { /* B */ } else { /* C */ }
    ```

<details markdown="1">
<summary>答案</summary>

进入 B。读 `7` 时为了确认数字已经结束，`num_get` 读到了末尾，置 `eofbit`，所以 `good()` 为假（[[iostate.flags#7]]）。提取本身成功了，`failbit` 没有置位，`operator bool` 即 `!fail()` 为真（[[iostate.flags#1]]）。
</details>

!!! question "思考题 2"
    `a` 处于 `failbit` 状态，`b.exceptions() == failbit`。调用 `a.copyfmt(b)` 会发生什么？

<details markdown="1">
<summary>答案</summary>

`copyfmt` 不复制 `rdstate()`，`a` 仍处于 `failbit` 状态。它的最后一步调用 `exceptions(rhs.exceptions())`（[[basic.ios.members#16.4]]），后者调用 `clear(rdstate())`，发现 `failbit & exceptions()` 非零，于是抛出 `ios_base::failure`。此时 `flags`、`fill`、`iword` 等都已经复制完毕。
</details>

## 小结

| 主题 | 要点 |
|---|---|
| 两个类 | `ios_base` 保存与 `charT` 无关的状态；`basic_ios` 加上状态位、`fill`、`tie`、`rdbuf` |
| 状态位 | `eofbit` 撞到了末尾，`failbit` 没得到期望的值，`badbit` 流已损坏；`operator bool` 即 `!fail()` |
| 异常 | `clear`、`setstate`、`exceptions(m)` 都可能抛出；`exceptions(m)` 对已有的状态立即抛出 |
| 格式 | 除宽度外的格式状态一直生效；`setf(f)` 不清除同组的位，要用 `setf(f, mask)` 或操纵符 |
| 自定义格式 | `xalloc` 加 `iword`/`pword`；`copyfmt` 复制数组内容并触发回调 |
| `init` | `goodbit`（流缓冲区为空则 `badbit`）、`skipws | dec`、精度 6、填充空格、无 tie、不抛异常 |
| `fpos` | 偏移量加转换状态；`pos_type(-1)` 表示错误，再传给流的成员是 {{ub}} |

<details class="fine" markdown="1"><summary>其余条文</summary>

[ios.syn]：`<ios>` 包含 `<iosfwd>`，声明 `streamoff`/`streamsize`（[[iostreams.requirements]]）、`fpos`、`ios_base`、`basic_ios`、全部 `ios_base&(ios_base&)` 形式的操纵符，以及 `io_errc`、`is_error_code_enum<io_errc>`、`make_error_code`、`make_error_condition`、`iostream_category`。

[ios.base.general] ¶1 列出 `ios_base` 定义的成员类型：`failure`、`Init`、三个位掩码类型和枚举类型 `seekdir`。¶2 说它维护三类数据：反映流缓冲区完整性的状态信息、影响如何解析输入和生成输出的控制信息、程序私用的附加信息。¶3 的注为了说明，用 `index`、`iarray`、`parray` 三个成员描述第三类，`xalloc`、`iword`、`pword` 就是用它们定义的。

[ios.failure] ¶1 的注 1：`ios_base::failure` 是另一个类的别名时，那个类需要提供嵌套的 `failure` 类型，以模拟注入类名。¶3–¶4：两个构造函数都用 `msg` 和 `ec` 构造基类。

[ios.base.storage] ¶9：之后对同一对象再调用 `pword`，之前的返回值可能失效。脚注 239 说明，实现可以把两个数组都做成稀疏结构，每个带一个单元素缓存。

[fpos.members] ¶1–¶2：`state(s)` 把 `s` 赋给 `st`，`state()` 返回 `st` 的当前值。

[error.reporting] ¶1–¶2：`make_error_code(e)`、`make_error_condition(e)` 分别返回以 `static_cast<int>(e)` 和 `iostream_category()` 构造的 `error_code`、`error_condition`。¶4 的其余部分：这个类别对象的 `default_error_condition` 和 `equivalent` 按 `error_category` 的规定工作。

</details>
