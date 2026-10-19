---
title: 流缓冲区 basic_streambuf
summary: iostream 中真正搬运字符的一层：输入、输出缓冲区各由三个指针描述，公有接口在缓冲区够用时只做指针运算，不够用时才调用 underflow、overflow 等虚函数；以及如何正确地写一个自定义 streambuf。
status: done
covers: *
related: input.output, iostreams.base, input.streams, output.streams, string.streams, span.streams, file.streams, syncstream, stream.iterators, iostreams.requirements
tags: 标准库, iostream, streambuf, 缓冲, 虚函数
updated: 2026-10-19
---

!!! tldr
    - `istream`、`ostream` 只负责把字符解析成值、把值格式化成字符；字符从哪来、到哪去，由它们持有的 `basic_streambuf` 决定。
    - 输入缓冲区（get 区）和输出缓冲区（put 区）各由三个指针描述。缓冲区里有数据或空位时，读写一个字符只是一次指针运算；缓冲区耗尽时才调用虚函数。
    - 自定义输出 streambuf 最少覆写 `overflow`，设置了 put 区还要覆写 `sync`；自定义输入 streambuf 覆写 `underflow`，并用 `setg` 把读到的数据放进 get 区。
    - `underflow` 返回下一个字符但不消费它；`overflow(c)` 交出攒下的字符再接收 `c`，`c` 为 `eof()` 时只刷新。成功时要返回 `traits_type::not_eof(c)`。
    - 基类的析构函数不刷新，复制只复制指针，定位函数默认一律失败；这些都要由派生类自己处理。

## 一个最小的 streambuf

```cpp title="counting-buf.cpp" run ok
#include <iostream>
#include <streambuf>

struct counting_buf : std::streambuf {
  std::size_t count = 0, newlines = 0;
protected:
  int_type overflow(int_type c) override {
    if (!traits_type::eq_int_type(c, traits_type::eof())) {
      ++count;
      if (traits_type::to_char_type(c) == '\n') ++newlines;
    }
    return traits_type::not_eof(c);     // 成功：返回非 eof 值
  }
};

int main() {
  counting_buf cb;
  std::ostream os(&cb);
  os << "pi = " << 3.14159 << '\n' << 42 << '\n';
  std::cout << cb.count << " chars, " << cb.newlines << " lines\n";
  // 16 chars, 2 lines
}
```

`os << 3.14159` 的格式化（数字转字符、精度、locale）全部在 `ostream` 里完成，生成的字符逐个交给 `cb`。`counting_buf` 只覆写了一个虚函数 `overflow`，就得到了一个能配合所有标准插入器的输出目标。

这就是 iostream 的分层：`basic_ostream`、`basic_istream` 处理格式，**流缓冲区**（stream buffer）处理字符的来源和去向。文件、字符串、内存块、同步输出各有一个派生类：[[file.streams]] 的 `basic_filebuf`、[[string.streams]] 的 `basic_stringbuf`、[[span.streams]] 的 `basic_spanbuf`、[[syncstream]] 的 `basic_syncbuf`。理解了基类的契约，这些派生类的条文就只是在说它们各自怎样覆写虚函数。

头文件 `<streambuf>` 声明 `basic_streambuf` 以及别名 `streambuf`、`wstreambuf`（[streambuf.syn]）。

## 三个指针 [streambuf.reqts]

¶2 每个 `basic_streambuf` 控制一个输入序列和一个输出序列。每个序列由三个指针描述，它们非空时指向同一个 `charT` 数组。这个数组是缓冲区，任一时刻保存着外部序列的一段：

- **起始指针**（beginning pointer）：数组的最低地址；
- **下一指针**（next pointer）：下一次读或写的位置；
- **结束指针**（end pointer）：数组末尾之后的第一个位置。

输入序列的三个指针是 `eback()`、`gptr()`、`egptr()`，它们围出的区域叫 [[g:get-area|get 区]]。输出序列的三个指针是 `pbase()`、`pptr()`、`epptr()`，围出 [[g:put-area|put 区]]。

```text
 get 区：  eback()         gptr()                  egptr()
             │ 已读，可回退  │       待读                │
             ▼               ▼                         ▼
           [ a  b  c  d  e  f  g  h  i  j  k  l ]

 put 区：  pbase()           pptr()                epptr()
             │ 已写，尚未交出  │        空位            │
             ▼                 ▼                       ▼
           [ H  e  l  l  o  ,  _  _  _  _  _  _  _ ]
```

¶3 任何时刻都必须满足的约束：

- ¶3.1 下一指针非空时，另外两个指针也非空，且指向同一数组；下一指针为空时，三个都为空。
- ¶3.2 输出序列中 `pptr() < epptr()` 时，**写位置**（write position）可用，下一个字符可以直接存到 `*pptr()`。
- ¶3.3 输入序列中 `eback() < gptr()` 时，**回退位置**（putback position）可用，`gptr()[-1]` 有确定的值，回退一个字符就是把 `gptr()` 往回移。
- ¶3.4 输入序列中 `gptr() < egptr()` 时，**读位置**（read position）可用，`*gptr()` 就是下一个要读的字符。

¶1 列举了流缓冲区可以施加的限制：输入序列可以不可读，输出序列可以不可写，可以关联外部文件，可以限制回退和改变流位置。也就是说，`basic_streambuf` 的接口给出的是能力的上限，派生类只实现自己需要的部分，基类的虚函数默认都返回失败。

## 公有接口：先走指针，不够再调虚函数 [streambuf.general]

`istream`、`ostream` 只调用 `basic_streambuf` 的公有成员。这些成员都不是虚函数；它们先检查读写位置是否可用，可用就直接操作指针，不可用才调用对应的受保护虚函数。

| 公有成员 | 位置可用时 | 否则调用 |
|---|---|---|
| `sgetc()` | 返回 `*gptr()`，不移动 | `underflow()` |
| `sbumpc()` | 返回 `*gptr()`，`gptr()` 加一 | `uflow()` |
| `snextc()` | 先 `sbumpc()`，不是 `eof()` 就再 `sgetc()` | 经由前两者 |
| `in_avail()` | 返回 `egptr() - gptr()` | `showmanyc()` |
| `sputbackc(c)` | `c == gptr()[-1]` 时 `gptr()` 减一 | `pbackfail(c)` |
| `sungetc()` | `gptr()` 减一 | `pbackfail()` |
| `sputc(c)` | 存到 `*pptr()`，`pptr()` 加一 | `overflow(c)` |
| `sgetn(s, n)`、`sputn(s, n)` | 总是调用 `xsgetn`、`xsputn` | |
| `pubsync()`、`pubsetbuf`、`pubseekoff`、`pubseekpos`、`pubimbue` | 总是调用 `sync`、`setbuf`、`seekoff`、`seekpos`、`imbue` | |

`sgetc` 是看一眼（peek），`sbumpc` 是读走，`snextc` 是跳过当前字符再看下一个（[[streambuf.pub.get]]）。

回退一个与原来相同的字符永远可以在缓冲区内完成，不需要虚函数（[[streambuf.pub.pback]]）。回退一个不同的字符要由派生类的 `pbackfail` 决定是否允许修改缓冲区；`basic_stringbuf` 只在以可写模式打开时允许。

受保护的非虚成员供派生类管理缓冲区：`eback`、`gptr`、`egptr`、`gbump`、`setg` 管理 get 区，`pbase`、`pptr`、`epptr`、`pbump`、`setp` 管理 put 区。

这种公有非虚函数调用受保护虚函数的结构使得大多数字符的读写不经过虚调用，派生类只需在缓冲区边界上介入。

## 写一个输出 streambuf：`overflow` 与 `sync`

上面的 `counting_buf` 没有设置 put 区，`pptr()` 始终为空，所以每个字符都经过一次 `overflow` 虚调用。实际的实现应当用 `setp` 提供一块缓冲区，让大部分字符走 `sputc` 的快速路径。下面的例子把字符转成大写后转交给另一个 streambuf：

```cpp title="upper-buf.cpp" run ok
#include <cctype>
#include <iostream>
#include <streambuf>

class upper_buf : public std::streambuf {
  std::streambuf* dest_;
  char buf_[8];

  bool drain() {                         // 把 [pbase, pptr) 交给 dest_
    for (char* p = pbase(); p != pptr(); ++p) {
      unsigned char u = static_cast<unsigned char>(*p);
      char up = static_cast<char>(std::toupper(u));
      if (dest_->sputc(up) == traits_type::eof()) return false;
    }
    setp(buf_, buf_ + sizeof buf_);      // 全部消费：pptr 回到 pbase
    return true;
  }

protected:
  int_type overflow(int_type c) override {   // put 区满时由 sputc 调用
    if (!drain()) return traits_type::eof();
    if (!traits_type::eq_int_type(c, traits_type::eof())) {
      *pptr() = traits_type::to_char_type(c);
      pbump(1);
    }
    return traits_type::not_eof(c);
  }
  int sync() override {                      // flush() → pubsync() → sync()
    return drain() && dest_->pubsync() == 0 ? 0 : -1;
  }

public:
  explicit upper_buf(std::streambuf* d) : dest_(d) {
    setp(buf_, buf_ + sizeof buf_);
  }
  ~upper_buf() override { sync(); }      // 基类析构函数不刷新
};

int main() {
  upper_buf ub(std::cout.rdbuf());
  std::ostream os(&ub);
  os << "hello, streambuf " << 42 << '\n';   // HELLO, STREAMBUF 42
  os.flush();
}
```

### `overflow` 的契约 [streambuf.virt.put]

¶3 `overflow(c)` 面对的**待处理序列**是 put 区里已写的字符 `[pbase(), pptr())`，后面再接上 `c`（`c` 为 `eof()` 时不接）。它的职责是把这个序列的某个开头部分交给外部序列，这叫做**消费**（consume）。

¶4 每个覆写版本都要遵守：

- ¶4.2 设没被消费的字符有 `r` 个。`r` 非零时，要让 `pptr() - pbase() == r`，且从 `pbase()` 开始的 `r` 个字符就是这些剩余字符。`r` 为零时，要么把 `pbase()` 置空，要么让 `pbase()` 和 `pptr()` 相等。`upper_buf` 用 `setp` 把 `pptr()` 放回开头，满足后一种情况。
- ¶4.3 向外部追加字符失败，或者无法按上面的规则设置指针时，函数可以失败。
- ¶4.1 消费一个字符对外部序列有什么效果，标准为自己的派生类都作了规定，对程序定义的类不作要求。

¶5 失败时返回 `eof()` 或抛出异常，成功时返回任何不等于 `eof()` 的值。脚注建议的写法是返回 `c`，但 `c` 本身是 `eof()` 时返回 `traits::not_eof(c)`，`traits_type::not_eof(c)` 一次涵盖了两种情况。¶6 基类版本直接返回 `eof()`。¶7 `sputc` 和 `sputn` 在 put 区放不下时调用它。

`c == eof()` 的调用表示只刷新，没有新字符。`basic_filebuf::close()` 就是用 `overflow(eof())` 把缓冲区写出去的。

### `sync` 与 `xsputn` [streambuf.virt.buffer]

¶7 `sync()` 把缓冲区与外部序列同步：`pbase()` 非空时，把 `[pbase(), pptr())` 写到外部序列，然后可以重置指针。¶8 失败返回 −1，什么算失败由派生类决定；¶9 基类版本返回 0。`ostream::flush()` 经由 `pubsync()` 调用它，返回 −1 时给流置 `badbit`（[[ostream.unformatted]]）。

`xsputn(s, n)` 的效果（[[streambuf.virt.put#1]]）如同反复调用 `sputc`，写满 `n` 个或某次 `sputc` 会返回 `eof()` 时停止，返回写出的个数。put 区满时它是调用 `overflow()` 还是用别的方式达到同样效果，标准没有规定。本机 libc++ 的基类版本在 put 区有空位时整块复制，满了就对下一个字符调用 `overflow(c)`。

`upper_buf` 体现了三条要点：

1. `overflow` 消费全部字符后用 `setp` 把 `pptr()` 放回 `pbase()`，满足第 4.2 项。
2. `sync` 先交出缓冲内容，再刷新下游，任何一步失败都返回 −1。
3. 析构函数自己调用 `sync()`，因为 `~basic_streambuf` 什么也不做。这一步要放在派生类的析构函数里，此时派生部分还活着；留给更上层的基类就太晚了。

!!! lawyer "格式化输出只会用到三个虚函数"
    [[ostream.general#3]] 规定，`basic_ostream` 的输出函数除了 `overflow()`、`xsputn()`、`sync()` 之外，不得调用 `rdbuf()` 的任何虚成员。所以自定义输出 streambuf 只要这三个行为正确（`xsputn` 用基类的也可以），就能配合所有标准插入器；`seekoff` 只在用户调用 `seekp`、`tellp` 时才会被用到。

## 写一个输入 streambuf：`underflow`

```cpp title="gen-buf.cpp" run ok
#include <iostream>
#include <streambuf>
#include <string>

// 每次 underflow 生成一行 "line N\n"，共 3 行
class gen_buf : public std::streambuf {
  std::string cur_;
  int n_ = 0;
protected:
  int_type underflow() override {
    if (gptr() < egptr())                    // get 区还有字符
      return traits_type::to_int_type(*gptr());
    if (n_ == 3) return traits_type::eof();
    cur_ = "line " + std::to_string(++n_) + "\n";
    setg(cur_.data(), cur_.data(), cur_.data() + cur_.size());
    return traits_type::to_int_type(*gptr());  // 返回但不消费
  }
};

int main() {
  gen_buf gb;
  std::istream in(&gb);
  for (std::string s; std::getline(in, s); )
    std::cout << '[' << s << "]\n";
  std::cout << "eof=" << in.eof() << " fail=" << in.fail() << '\n';
  // [line 1] [line 2] [line 3]（各占一行），然后 eof=1 fail=1
}
```

### `underflow` 的契约 [streambuf.virt.get]

条文先定义了三个序列：

- ¶7 [[g:pending-sequence|待处理序列]]（pending sequence）：get 区里还没读的字符 `[gptr(), egptr())`，后面再接上从外部序列读入的某段字符（可以为空）。
- ¶8 **结果字符**（result character）：待处理序列非空时是它的第一个字符，否则是将要从外部读到的下一个字符。
- ¶9 **备份序列**（backup sequence）：已经读过的字符 `[eback(), gptr())`。

¶10 `underflow` 要设置 `gptr()` 和 `egptr()`，使待处理序列非空时 `[gptr(), egptr())` 正好是待处理序列；为空时 `gptr()` 为空或等于 `egptr()`。¶12 返回结果字符，但读位置不越过它；待处理序列为空时返回 `eof()` 表示失败。¶13 基类版本返回 `eof()`。

换句话说，`underflow` 的职责是把 get 区重新填满，并返回下一个字符但不消费它。第 14 段说明，公有成员只在 `gptr()` 为空或 `gptr() >= egptr()` 时才调用它。

¶11 对 `[eback(), gptr())` 的内容不作约束，但描述了通常的备份条件：这段内容应当与备份序列的末尾一致。也就是说，重新填充时最好保留最近读过的几个字符，让回退能在缓冲区内完成。`gen_buf` 每次都把 get 区换成新的一行，不满足这个条件，后果在下文的回退一节里可以看到。

### `uflow`：通常不必覆写

¶15 `uflow` 的约束与 `underflow` 相同，只是结果字符要从待处理序列移到备份序列，也就是被消费掉。¶16 基类版本调用 `underflow()`，失败就返回 `eof()`，否则返回 `*gptr()` 并让 `gptr()` 加一。

所以只要 `underflow` 正确设置了 get 区，就不需要覆写 `uflow`。只有不使用 get 区、每次直接从设备读一个字符的实现才必须覆写它，因为基类版本会在 `underflow` 返回后读取 `*gptr()`。

### `showmanyc` 与 `xsgetn`

¶1 `showmanyc()` 返回可用字符数的估计值，或 −1。返回正数时，在至少提取那么多字符之前 `underflow()` 不会返回 `eof()`；返回 −1 时，`underflow()` 和 `uflow()` 一定会失败，脚注说明意图是立即失败。¶2 基类版本返回 0，意思是不知道。脚注特意说明它的名字读作 es-how-many-see，不是 show-manic。`in_avail()` 和 `istream::readsome` 依赖它（[[input.streams]]）。

¶4–¶5 `xsgetn(s, n)` 如同反复调用 `sbumpc()`，最多存 `n` 个字符到 `s`，返回实际存入的个数。脚注说派生类可以覆写它和 `xsputn`，提供更高效的实现，例如文件流在用户缓冲区足够大时绕过 get 区直接读写。

## 回退：`pbackfail` [streambuf.virt.pback]

¶1 `pbackfail(c)` 的待处理序列与 `underflow` 相同，只是先作调整：`c` 是 `eof()` 时，先把输入序列后退一个字符；`c` 不是 `eof()` 时，把 `c` 放在最前面。外部序列是否真的后退或被修改，标准没有规定。

¶3–¶4 返回 `eof()` 表示失败，其他值表示成功。¶5 基类版本返回 `eof()`。¶6 公有函数只在缓冲区内无法回退时调用它：`gptr()` 为空、`gptr() == eback()`，或者 `c` 与 `gptr()[-1]` 不同。

用上面的 `gen_buf` 可以看到回退的边界：

```cpp title="putback-boundary.cpp" run ok
#include <iostream>
#include <streambuf>
#include <string>

class gen_buf : public std::streambuf {        // 同上例
  std::string cur_;
  int n_ = 0;
protected:
  int_type underflow() override {
    if (gptr() < egptr())
      return traits_type::to_int_type(*gptr());
    if (n_ == 3) return traits_type::eof();
    cur_ = "line " + std::to_string(++n_) + "\n";
    setg(cur_.data(), cur_.data(), cur_.data() + cur_.size());
    return traits_type::to_int_type(*gptr());
  }
};

int main() {
  gen_buf gb;
  std::istream in(&gb);
  std::string s;
  std::getline(in, s);  // 消费 "line 1\n"，get 区用完
  in.get();             // underflow 换上 "line 2\n"，读走 'l'
  in.unget();           // gptr() > eback()：缓冲区内回退
  std::cout << in.bad() << ' ';   // 0
  in.unget();           // gptr() == eback() → pbackfail() → eof
  std::cout << in.bad() << '\n';  // 1：istream::unget 置 badbit
}
```

C 的 `ungetc` 保证至少能回退一个字符，`basic_streambuf` 没有这种保证。能回退多少，取决于派生类在 `underflow` 里保留了多少备份序列。

## 其他虚函数

### `imbue` 与 `setbuf` [streambuf.virt.locales] [streambuf.virt.buffer]

`imbue(loc)` 在 locale 改变时通知派生类，基类版本什么也不做。两次调用之间，派生类可以缓存从 locale 和 facet 得到的结果。`basic_filebuf` 覆写它来切换字符编码转换用的 `codecvt`。

`setbuf(s, n)` 以各派生类分别规定的方式影响缓冲，基类版本什么也不做，返回 `this`。例如 `basic_filebuf` 在 I/O 之前调用 `setbuf(0, 0)` 会使流不带缓冲，`basic_spanbuf` 的 `setbuf` 换掉底层的内存块。

### 定位：默认失败

[streambuf.virt.buffer] 的 `seekoff`、`seekpos` 改变流位置，基类版本返回 `pos_type(off_type(-1))`，也就是失败。所以一个只覆写了 `overflow` 的 streambuf 上，`tellp()` 总是返回 −1。

## 构造、复制与指针操作

### 构造与析构 [streambuf.cons]

¶1 默认构造函数把所有指针置空，并把 `getloc()` 初始化为构造时全局 locale 的副本。默认构造函数是受保护的，脚注说明目的是保证只能构造派生类的对象。

¶2 `getloc()` 初始化之后，从它得到的结果可以一直缓存到下一次 `imbue`。

¶3 复制构造函数和复制赋值（[[streambuf.assign]]）都是受保护的，后条件是六个指针和 `getloc()` 都与 `rhs` 相同。这是浅复制：新对象的指针指向 `rhs` 的缓冲区。派生类如果有自己的缓冲区，必须在自己的复制或移动操作里重新调用 `setg`、`setp`，否则两个对象会共享同一块内存。`swap` 交换全部数据成员。

¶4 析构函数没有任何效果，不会刷新缓冲区。刷新是派生类析构函数的事，例如 `~basic_filebuf` 调用 `close()`。

### locale 与指针操作 [streambuf.locales] [streambuf.get.area] [streambuf.put.area]

`pubimbue(loc)` 调用 `imbue(loc)` 并返回旧的 locale。在 `imbue` 内部调用 `getloc()` 得到的仍是旧值，所以派生类可以在 `imbue` 里比较新旧两个 locale。

`setg(gbeg, gnext, gend)` 要求三个区间都有效，之后三个指针等于实参。`setp(pbeg, pend)` 只有两个参数，之后 `pbase()` 和 `pptr()` 都等于 `pbeg`。也就是说 `setp` 总是把写位置放回开头；要在重设后保留已写入的内容，接着调用 `pbump(n)`。

!!! pitfall "`gbump`、`pbump` 的参数是 `int`"
    缓冲区超过 `INT_MAX` 个字符时，一次 `pbump(n)` 无法前进到末尾：`streamsize` 转成 `int` 后会被截断。处理超大缓冲区的派生类要分多次调用。本机 libc++ 的 `xsgetn` 实现就是以 `INT_MAX` 为上限分块调用 `gbump` 的。

## 思考题

!!! question "思考题 1"
    一个 streambuf 只覆写了 `underflow`，没有调用 `setg`，每次直接从设备读一个字符并返回。这样实现有什么问题？

<details markdown="1">
<summary>答案</summary>

`underflow` 必须返回结果字符而不消费它，并让 `[gptr(), egptr())` 等于待处理序列（[[streambuf.virt.get#10]]）。不设置 get 区就做不到不消费：下一次 `sgetc()` 又会调用 `underflow()`，读走设备上的下一个字符，于是连续两次 `peek()` 得到不同的值。

更严重的是，基类的 `uflow()` 在 `underflow()` 成功后会读取 `*gptr()` 并让它加一（第 16 段），而此时 `gptr()` 是空指针，这是 {{ub}}。这类不带缓冲的实现必须同时覆写 `uflow`，并在 `underflow` 里用一个单字符缓冲区保存已读未消费的字符。
</details>

!!! question "思考题 2"
    `overflow(eof())` 返回什么才算成功？直接 `return c;` 有什么问题？

<details markdown="1">
<summary>答案</summary>

返回任何不等于 `eof()` 的值都算成功（[[streambuf.virt.put#5]]）。`c` 是 `eof()` 时直接 `return c;` 会被调用者当作失败。惯用写法 `return traits_type::not_eof(c);` 在 `c` 是普通字符时原样返回，在 `c` 是 `eof()` 时返回某个非 `eof` 值。
</details>

!!! question "思考题 3"
    `in_avail()` 返回 0，是否意味着到了流尾？

<details markdown="1">
<summary>答案</summary>

不是。读位置不可用时 `in_avail()` 返回 `showmanyc()`，而基类的 `showmanyc()` 返回 0，意思是不知道（[[streambuf.virt.get#2]]）。只有 −1 才表示后续读取一定失败。所以 `readsome` 读到 0 个字符可能只是缓冲区暂时为空。
</details>

## 小结

| 方向 | 快速路径（非虚） | 慢速路径（虚） | 派生类最少要覆写 |
|---|---|---|---|
| 读 | `sgetc`、`sbumpc` 读 `*gptr()` | `underflow`（看）、`uflow`（读走） | `underflow` 并用 `setg`；不带缓冲时再加 `uflow` |
| 回退 | `sputbackc`、`sungetc` 让 `gptr()` 减一 | `pbackfail` | 可选 |
| 写 | `sputc` 写 `*pptr()` | `overflow` | `overflow`；用了 `setp` 还要 `sync` |
| 批量 | | `xsgetn`、`xsputn` | 可选，用于性能 |
| 定位 | | `seekoff`、`seekpos`（默认失败） | 需要 `seekg`、`tellp` 时 |
