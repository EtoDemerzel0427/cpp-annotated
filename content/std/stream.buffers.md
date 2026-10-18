---
title: 流缓冲区 basic_streambuf
summary: iostream 真正做 I/O 的一层——输入/输出序列各由三个指针描述（eback/gptr/egptr、pbase/pptr/epptr），公有非虚接口（sgetc/sbumpc/sputc/sputn…）在缓冲区够用时只做指针运算、不够用时才调用受保护的虚函数（underflow/uflow/overflow/pbackfail/sync/seekoff…）；逐一讲清每个虚函数的契约（待处理序列、结果字符、备份序列、"消费"字符），以及如何正确地写一个自定义 streambuf
status: done
covers: *
related: input.output, iostreams.base, input.streams, output.streams, string.streams, span.streams, file.streams, syncstream, stream.iterators, iostreams.requirements
tags: 标准库, iostream, streambuf, 缓冲, 虚函数
updated: 2026-10-18
---

`basic_streambuf` 是 iostream 中唯一真正与"外部世界"打交道的类。`istream`/`ostream` 负责把字符解析成值、把值格式化成字符；至于字符从哪来、到哪去、什么时候真正搬运，全由 streambuf 决定。理解这一层，才能写自己的流（日志重定向、压缩、网络、内存映射），也才能读懂 [[string.streams]]、[[file.streams]]、[[span.streams]]、[[syncstream]] 中那些"覆写的虚函数"条文。

它的设计目标是**每个字符的开销接近一次指针运算**：只要缓冲区里还有数据（或空位），读写一个字符只是 `*gptr()++` 或 `*pptr()++`；只有缓冲区耗尽时才进行一次虚函数调用。

## `<streambuf>`（[streambuf.syn]）

声明 `basic_streambuf` 及别名 `streambuf`、`wstreambuf`。¶1：该头文件定义控制**字符**序列输入和输出的类型。

## 流缓冲区的要求（[streambuf.reqts]）

### 可能的约束（¶1）

流缓冲区可以对它控制的序列施加各种限制：输入序列可能不可读（¶1.1），输出序列可能不可写（¶1.2）；序列可以与其他表示（如外部文件）关联（¶1.3）；可以支持直接对关联序列的读写（¶1.4）；可以限制程序如何读、写、回退字符或改变流位置（¶1.5）。换句话说，`basic_streambuf` 的接口是"能力的上限"，具体派生类可以只实现其中一部分——默认的虚函数实现基本都是"失败"。

### 三个指针（¶2–¶3）

¶2：每个序列（输入、输出各一个）由三个指针描述；它们若非空，都指向**同一个** `charT` 数组对象，这个数组在任意时刻表示序列的一个（子）序列：

- **起始指针**（beginning pointer）`xbeg`：数组的最低地址；
- **下一指针**（next pointer）`xnext`：当前读或写的候选位置；
- **结束指针**（end pointer）`xend`：数组末尾之后的第一个位置。

输入序列的三个指针是 `eback()`、`gptr()`、`egptr()`（构成 **get 区**，[[g:get-area]]）；输出序列的是 `pbase()`、`pptr()`、`epptr()`（构成 **put 区**，[[g:put-area]]）。

```text
 get 区：  eback()        gptr()                  egptr()
             │  已读（可回退） │   待读（读位置可用）    │
             ▼               ▼                       ▼
           [ a  b  c  d  e  f  g  h  i  j  k  l ]
             └ putback 位置 ┘└──── read 位置 ─────┘

 put 区：  pbase()            pptr()               epptr()
             │  已写、尚未交出  │     空位（写位置可用） │
             ▼                 ▼                     ▼
           [ H  e  l  l  o  ,  _  _  _  _  _  _  _ ]
```

¶3 规定任何时刻都必须满足的语义约束：

- ¶3.1：`xnext` 非空时，`xbeg` 和 `xend` 也必须是指向同一数组的非空指针；`xnext` 为空时，另外两个也必须为空。
- ¶3.2：对输出序列，若 `xnext` 非空且 `xnext < xend`，则**写位置**可用，`*xnext` 可被赋值为下一个要写入的元素。
- ¶3.3：对输入序列，若 `xnext` 非空且 `xbeg < xnext`，则**回退位置**（putback position）可用，`xnext[-1]` 必须有确定的值，是回退一个字符时要存放的位置。
- ¶3.4：对输入序列，若 `xnext` 非空且 `xnext < xend`，则**读位置**可用，`*xnext` 必须有确定的值，是下一个要读的元素。

## `basic_streambuf` 的整体结构（[streambuf.general]）

¶1：`basic_streambuf` 作为各种**流缓冲区**的基类，每个对象控制两个字符序列：一个**输入序列**、一个**输出序列**。它的接口采用"公有非虚函数调用受保护虚函数"的模式（NVI）：

| 公有（非虚） | 对应的受保护虚函数 | 何时调用虚函数 |
|---|---|---|
| `pubimbue(loc)` | `imbue(loc)` | 总是 |
| `pubsetbuf(s, n)` | `setbuf(s, n)` | 总是 |
| `pubseekoff(off, way, which)` | `seekoff(...)` | 总是 |
| `pubseekpos(sp, which)` | `seekpos(...)` | 总是 |
| `pubsync()` | `sync()` | 总是 |
| `in_avail()` | `showmanyc()` | 读位置不可用时 |
| `sgetc()` | `underflow()` | 读位置不可用时 |
| `sbumpc()` | `uflow()` | 读位置不可用时 |
| `snextc()` | 经 `sbumpc()`/`sgetc()` | — |
| `sgetn(s, n)` | `xsgetn(s, n)` | 总是 |
| `sputbackc(c)` | `pbackfail(c)` | 回退位置不可用或 `c` 与 `gptr()[-1]` 不同时 |
| `sungetc()` | `pbackfail()` | 回退位置不可用时 |
| `sputc(c)` | `overflow(c)` | 写位置不可用时 |
| `sputn(s, n)` | `xsputn(s, n)` | 总是 |

受保护的非虚成员（`eback`/`gptr`/`egptr`/`gbump`/`setg`、`pbase`/`pptr`/`epptr`/`pbump`/`setp`）供派生类管理缓冲区；`istream`/`ostream` 只使用公有接口。

## 构造、复制、析构（[streambuf.cons]、[streambuf.assign]）

- 默认构造函数（受保护，脚注说明目的：保证只有派生类对象能被构造）：¶1 所有指针置空，`getloc()` 初始化为构造时全局 locale `locale()` 的副本。¶2：一旦 `getloc()` 初始化，调用 locale 成员函数及所得 facet 成员的结果可以**安全缓存**，直到下一次调用 `imbue`。
- 复制构造函数（受保护）：¶3 后条件是六个指针和 `getloc()` 都与 `rhs` 相同——这是**浅复制**：新对象的指针指向 `rhs` 的缓冲区。派生类若有自己的缓冲区，必须在自己的复制/移动构造函数里重新 `setg`/`setp`，否则两个对象会共享同一块内存。
- `operator=`（受保护）：[streambuf.assign] ¶1 同样复制六个指针和 locale。`swap`：¶3 交换数据成员。
- 析构函数：¶4 无效果（不刷新！刷新是派生类析构函数的事，如 `~basic_filebuf` 调用 `close()`）。

## 公有成员函数（[streambuf.members]）

### locale（[streambuf.locales]）

- `pubimbue(loc)`：¶1 调用 `imbue(loc)`；¶2 后条件 `loc == getloc()`；¶3 返回旧值。
- `getloc()`：¶4 若调用过 `pubimbue`，返回最后一次传入的 locale，否则返回构造时的全局 locale；若在 `pubimbue` 调用期间（即从 `imbue()` 内部）调用，返回**旧值**——派生类在 `imbue(loc)` 里可以通过 `getloc()` 拿到旧 locale、通过参数拿到新 locale 进行比较。

### 缓冲区管理与定位（[streambuf.buffer]）

`pubsetbuf`、`pubseekoff`、`pubseekpos`、`pubsync`（¶1–¶4）分别直接返回对应虚函数的结果。

### get 区（[streambuf.pub.get]）

| 函数 | 读位置可用时 | 不可用时 |
|---|---|---|
| `in_avail()` | ¶1 `egptr() - gptr()` | `showmanyc()` |
| `sgetc()` | ¶5 `to_int_type(*gptr())`，**不移动** | `underflow()` |
| `sbumpc()` | ¶4 `to_int_type(*gptr())`，然后 `gptr()` 加一 | `uflow()` |
| `snextc()` | ¶2–¶3 先 `sbumpc()`；若它返回 `eof()` 则返回 `eof()`，否则返回 `sgetc()` | |
| `sgetn(s, n)` | ¶6 `xsgetn(s, n)` | |

`sgetc` 是"看一眼"（peek），`sbumpc` 是"读走"（get），`snextc` 是"跳过当前、看下一个"。

### 回退（[streambuf.pub.pback]）

- `sputbackc(c)`：¶1 若回退位置不可用，或 `traits::eq(c, gptr()[-1])` 为假，返回 `pbackfail(to_int_type(c))`；否则 `gptr()` 减一并返回 `to_int_type(*gptr())`。
- `sungetc()`：¶2 若回退位置不可用，返回 `pbackfail()`；否则 `gptr()` 减一并返回该字符。

所以"回退一个与原来相同的字符"在缓冲区内永远成功，不需要虚函数；回退一个**不同**的字符则要看派生类的 `pbackfail` 是否允许修改缓冲区（`stringbuf` 只在可写模式下允许，见 [[string.streams]]）。

### put 区（[streambuf.pub.put]）

- `sputc(c)`：¶1 若写位置不可用，返回 `overflow(to_int_type(c))`；否则把 `c` 存到 `*pptr()`、`pptr()` 加一，返回 `to_int_type(c)`。
- `sputn(s, n)`：¶2 返回 `xsputn(s, n)`。

## 受保护的指针访问（[streambuf.get.area]、[streambuf.put.area]）

| get 区 | put 区 | 含义 |
|---|---|---|
| `eback()` | `pbase()` | 起始指针 |
| `gptr()` | `pptr()` | 下一指针 |
| `egptr()` | `epptr()` | 结束指针 |
| `gbump(int n)` | `pbump(int n)` | 下一指针加 `n` |
| `setg(gbeg, gnext, gend)` | `setp(pbeg, pend)` | 重设整个区 |

- `setg`：¶5 前置条件是 `[gbeg, gnext)`、`[gbeg, gend)`、`[gnext, gend)` 都是有效范围；¶6 后条件三个指针等于实参。
- `setp`：¶5 前置条件 `[pbeg, pend)` 是有效范围；¶6 后条件 `pbase() == pbeg`、**`pptr() == pbeg`**、`epptr() == pend`。注意 `setp` 没有"next"参数，总是把写位置放回开头；要在设置后保留已写入的内容，得接着调用 `pbump(n)`。

!!! pitfall "`gbump`/`pbump` 的参数是 `int`"
    缓冲区大于 `INT_MAX` 个字符时，一次 `pbump(n)` 无法前进到末尾——参数类型是 `int`，大于 `INT_MAX` 的 `streamsize` 转换后会变成负数或被截断。派生类处理超大缓冲区时要分多次调用。本机 libc++ 的 `xsgetn` 实现里就能看到按 `INT_MAX` 分块调用 `gbump` 的代码。

## 虚函数的契约（[streambuf.virtuals]）

每个虚函数的条文都分为 *Effects*（派生类覆写时应达到的效果）和 *Default behavior*（基类版本做什么）。基类版本几乎都是"什么也不做"或"返回失败"，因为它不知道外部序列是什么。

### `imbue`（[streambuf.virt.locales]）

¶1 改变基于 locale 的转换；¶2 让派生类在 locale 改变时得到通知，两次调用之间可以安全缓存 locale 和 facet 成员的结果；¶3 默认什么也不做。`basic_filebuf` 覆写它来切换 `codecvt`。

### `setbuf`、`seekoff`、`seekpos`、`sync`（[streambuf.virt.buffer]）

- `setbuf(s, n)`：¶1 以各派生类分别规定的方式影响缓冲；¶2 默认什么也不做，返回 `this`。`stringbuf` 的 `setbuf` 是实现定义的（`setbuf(0, 0)` 无效果），`filebuf` 的 `setbuf(0, 0)` 在 I/O 之前调用会使流无缓冲，`spanbuf` 的 `setbuf` 换掉底层 span。
- `seekoff`/`seekpos`：¶3–¶6 以派生类规定的方式改变流位置；默认返回 `pos_type(off_type(-1))`（失败）。所以一个只覆写了 `overflow` 的 streambuf 上，`tellp()` 总是返回 −1。
- `sync()`：¶7 把控制的序列与数组同步——若 `pbase()` 非空，把 `[pbase(), pptr())` 写到受控序列，然后可以重置指针；¶8 失败返回 −1（何为失败由派生类决定）；¶9 默认返回 0。`ostream::flush()` 最终调用的就是它。

### get 区：`showmanyc`、`xsgetn`、`underflow`、`uflow`（[streambuf.virt.get]）

**`showmanyc()`**（脚注：读作 "es-how-many-see"，不是 "show-manic"）：¶1 返回序列中可用字符数的**估计**，或 −1。若返回正数，后续调用 `underflow()` 在至少提取了那么多字符之前不会返回 `eof()`；若返回 −1，`underflow()`/`uflow()` 将会失败（脚注：意图是它们会"立即"返回失败，而不仅仅是最终失败）。¶2 默认返回 0，即"不知道"。`istream::readsome` 依赖它（[[input.streams]]）。

**`xsgetn(s, n)`**：¶4 如同反复调用 `sbumpc()`，把至多 `n` 个字符存入 `s`，在存满 `n` 个或 `sbumpc()` 将返回 `eof()` 时停止；¶5 返回存入的个数。脚注：派生类可以覆写它提供更高效的实现（例如对文件直接读入用户缓冲区，绕过 get 区）。

**`underflow()`** 是输入方向的核心。条文先定义三个概念：

- ¶7 **待处理序列**（pending sequence，[[g:pending-sequence]]）：若 `gptr()` 为空则为空序列，否则是 `[gptr(), egptr())` 中的字符，**再接上**从输入序列读入的某个（可能为空的）字符序列。
- ¶8 **结果字符**（result character）：待处理序列非空时是它的第一个字符，否则是将从输入序列读到的下一个字符。
- ¶9 **备份序列**（backup sequence）：`eback()` 为空时为空，否则是 `[eback(), gptr())` 中的字符。

¶10 *Effects*：设置 `gptr()` 和 `egptr()`，使得若待处理序列非空，则 `egptr()` 非空且 `[gptr(), egptr())` 正是待处理序列；否则 `gptr()` 为空或 `gptr() == egptr()`。¶11：对 `eback()` 与 `gptr()` 之间的内容不作约束，但"通常的备份条件"是这段内容与备份序列的末尾（或整个备份序列）一致——换句话说，`underflow` 应尽量保留最近读过的字符，让回退可以在缓冲区内完成。

¶12 *Returns*：结果字符的 `to_int_type(c)`，**不越过它**；待处理序列为空时返回 `eof()` 表示失败。¶13 默认返回 `eof()`。¶14：`basic_streambuf` 的公有成员只在 `gptr()` 为空或 `gptr() >= egptr()` 时调用它。

翻成白话：**`underflow` 的职责是"把 get 区重新填满，并返回下一个字符但不消费它"**。

**`uflow()`**：¶15 约束与 `underflow` 相同，只是结果字符要从待处理序列**移到**备份序列（即被消费），且转移前待处理序列不为空。¶16 默认行为：调用 `underflow()`，若返回 `eof()` 则返回 `eof()`；否则返回 `*gptr()` 并使 `gptr()` 加一。所以只要派生类正确实现了 `underflow` 并设置了 get 区，就**不需要**覆写 `uflow`。只有不使用 get 区缓冲的派生类（每次直接从外部读一个字符）才必须覆写 `uflow`，否则默认版本在 `underflow` 返回后对 `*gptr()` 的读取没有意义。

### 回退：`pbackfail`（[streambuf.virt.pback]）

¶1：待处理序列的定义同 `underflow`，但若 `c` 是 `eof()`，先把输入序列后退一个字符再确定待处理序列；若 `c` 不是 `eof()`，则把 `c` 加在前面——是否真的后退或修改输入序列是**未指定**的。¶2：返回时 `gptr()`、`eback()`、`pptr()` 的约束与 `underflow` 相同。¶3–¶4：返回 `eof()` 表示失败（可能因为无法后退，或无法使指针满足约束），其他值表示成功；`pbackfail()` **只在回退真正失败时**才被调用。¶5 默认返回 `eof()`。¶6：公有函数只在 `gptr()` 为空、`gptr() == eback()`、或 `c` 与 `gptr()[-1]` 不同时调用它；其他调用者也必须满足这个约束。

### put 区：`xsputn`、`overflow`（[streambuf.virt.put]）

**`xsputn(s, n)`**：¶1 如同反复调用 `sputc(c)`，写出至多 `n` 个字符，在写满 `n` 个或 `sputc` 将返回 `eof()` 时停止。**`pptr() == epptr()` 时是否调用 `overflow()`，还是用其他方式达到同样效果，是未指定的。** ¶2 返回写出的个数。本机 libc++ 的默认实现是：put 区有空位就整块 `copy`，满了就对下一个字符调用 `overflow(c)`。

**`overflow(c)`** 是输出方向的核心：

- ¶3 *Effects*：**消费**待处理序列的某个初始子序列。这里的待处理序列是：`pbase()` 为空时为空，否则是从 `pbase()` 开始的 `pptr() - pbase()` 个字符；再接上 `c`（若 `c` 不是 `eof()`）。
- ¶4 每个覆写版本都必须遵守：
    - ¶4.1 "消费一个字符"对关联输出序列的效果是有规定的（脚注：对本章的每个派生类都给出了规定；对程序定义的类没有要求）；
    - ¶4.2 设未消费的字符数为 `r`：若 `r` 非零，则设置 `pbase()` 和 `pptr()` 使得 `pptr() - pbase() == r`，且从 `pbase()` 开始的 `r` 个字符就是那些未消费的字符；若 `r` 为零（全部消费），则要么把 `pbase()` 置空，要么把 `pbase()` 和 `pptr()` 设为同一个非空值；
    - ¶4.3 向关联输出序列追加字符失败，或无法按上述规则设置指针时，函数可以失败。
- ¶5 失败时返回 `eof()` **或抛异常**；成功时返回非 `eof()` 的值（脚注：通常返回 `c`，但 `c` 为 `eof()` 时返回 `traits::not_eof(c)`）。
- ¶6 默认返回 `eof()`。
- ¶7：`sputc()` 和 `sputn()` 在 put 区放不下实参字符序列时调用它。

翻成白话：**`overflow(c)` 的职责是"把 put 区里攒着的字符（加上 `c`）交出去，腾出空间"**；`c == eof()` 的调用表示"只刷新，没有新字符"，这正是 `filebuf::close()` 用 `overflow(eof())` 刷新缓冲区的原因。

## 写一个自定义 streambuf

### 最小的输出 streambuf：只覆写 `overflow`

不调用 `setp`，put 区始终为空，于是**每个**字符都会经过 `overflow`。简单，但每个字符一次虚调用：

```cpp title="counting-buf.cpp" ok
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
  std::cout << cb.count << " chars, " << cb.newlines << " lines\n";   // 16 chars, 2 lines
}
```

### 带缓冲的输出 streambuf：`overflow` + `sync`

真正的实现应当设置 put 区，让大部分字符走 `sputc` 的快速路径。下面的 streambuf 把字符转成大写后转交给另一个 streambuf（"过滤器"模式）：

```cpp title="upper-buf.cpp" ok
#include <cctype>
#include <iostream>
#include <streambuf>

class upper_buf : public std::streambuf {
  std::streambuf* dest_;
  char buf_[8];

  bool drain() {                                   // 把 [pbase, pptr) 交给 dest_
    for (char* p = pbase(); p != pptr(); ++p)
      if (dest_->sputc(static_cast<char>(std::toupper(static_cast<unsigned char>(*p))))
          == traits_type::eof())
        return false;
    setp(buf_, buf_ + sizeof buf_);                // 全部消费：pptr 回到 pbase
    return true;
  }

protected:
  int_type overflow(int_type c) override {         // put 区满（或无 put 区）时由 sputc 调用
    if (!drain()) return traits_type::eof();
    if (!traits_type::eq_int_type(c, traits_type::eof())) {
      *pptr() = traits_type::to_char_type(c);
      pbump(1);
    }
    return traits_type::not_eof(c);
  }
  int sync() override {                            // flush() → pubsync() → sync()
    return drain() && dest_->pubsync() == 0 ? 0 : -1;
  }

public:
  explicit upper_buf(std::streambuf* d) : dest_(d) { setp(buf_, buf_ + sizeof buf_); }
  ~upper_buf() override { sync(); }                // 基类析构函数不刷新，派生类要自己做
};

int main() {
  upper_buf ub(std::cout.rdbuf());
  std::ostream os(&ub);
  os << "hello, streambuf " << 42 << '\n';         // HELLO, STREAMBUF 42
  os.flush();
}
```

要点：

1. `overflow` 满足 ¶4.2——全部消费后把 `pptr()` 设回 `pbase()`（通过 `setp`）。
2. `sync` 先交出缓冲内容，再刷新下游；任何一步失败返回 −1，`ostream::flush()` 会据此置 `badbit`（[[ostream.unformatted]]）。
3. 析构函数自己调用 `sync()`：`~basic_streambuf` 什么也不做（[[streambuf.cons#4]]）。注意在析构函数里调用的是本类的 `sync`——此时派生部分还活着；若把这一步留给更深的基类就晚了。

### 输入 streambuf：覆写 `underflow`

```cpp title="gen-buf.cpp" ok
#include <iostream>
#include <streambuf>
#include <string>

// 每次 underflow 生成一行 "line N\n"，共 3 行
class gen_buf : public std::streambuf {
  std::string cur_;
  int n_ = 0;
protected:
  int_type underflow() override {
    if (gptr() < egptr()) return traits_type::to_int_type(*gptr());  // 防御：get 区未空
    if (n_ == 3) return traits_type::eof();
    cur_ = "line " + std::to_string(++n_) + "\n";
    setg(cur_.data(), cur_.data(), cur_.data() + cur_.size());
    return traits_type::to_int_type(*gptr());     // 返回下一个字符，但不消费
  }
};

int main() {
  gen_buf gb;
  std::istream in(&gb);
  for (std::string s; std::getline(in, s); ) std::cout << '[' << s << "]\n";
  std::cout << "eof=" << in.eof() << " fail=" << in.fail() << '\n';   // eof=1 fail=1
}
```

不需要覆写 `uflow`：默认版本调用 `underflow()` 后读 `*gptr()` 并 `gbump(1)`，正好适用于设置了 get 区的实现。

这个实现每次重新填充时都把 get 区换成新的一行，**不保留**上一行的字符——不满足 ¶11 的"通常的备份条件"。后果是：回退只能在当前行内进行。

```cpp title="putback-boundary.cpp" ok
#include <iostream>
#include <streambuf>
#include <string>

class gen_buf : public std::streambuf {            // 同上例
  std::string cur_;
  int n_ = 0;
protected:
  int_type underflow() override {
    if (gptr() < egptr()) return traits_type::to_int_type(*gptr());
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
  std::getline(in, s);          // 消费 "line 1\n"，get 区已用完
  in.get();                     // 触发 underflow，get 区换成 "line 2\n"，读走 'l'
  in.unget();                   // OK：gptr() > eback()，在缓冲区内回退
  std::cout << in.bad() << ' '; // 0
  in.unget();                   // gptr() == eback() → pbackfail() → 默认返回 eof
  std::cout << in.bad() << '\n';// 1：istream::unget 置 badbit
}
```

C 的 `ungetc` 保证至少能回退一个字符；`basic_streambuf` 层面没有这种保证，能回退多少完全取决于派生类如何保留备份序列。

!!! tip "什么时候需要覆写 `xsgetn`/`xsputn`"
    默认实现正确但逐块经过 get/put 区。若外部设备支持大块读写（文件、socket），覆写它们可以在用户缓冲区足够大时直接读写、绕过中间拷贝——`basic_filebuf` 的实现通常就是这样做的。覆写时要记得维护 get/put 区指针的一致性。

!!! lawyer "格式化输出只能调用三个虚函数"
    [[ostream.general#3]] 规定：`basic_ostream` 的输出函数除了 `overflow()`、`xsputn()`、`sync()` 之外，**不得**调用 `rdbuf()` 的任何虚成员。所以自定义输出 streambuf 只要正确实现这三个（`xsputn` 用默认的也行），就能与所有标准插入器配合；`seekoff` 只在用户调用 `seekp`/`tellp` 时才会被用到。

## 思考题

<details markdown="1">
<summary>1. 一个 streambuf 只覆写了 <code>underflow</code>，没有调用 <code>setg</code>，每次直接从设备读一个字符并返回。这样实现有什么问题？</summary>

`underflow` 的契约要求返回结果字符**而不消费它**，并且要让 `[gptr(), egptr())` 等于待处理序列（[[streambuf.virt.get#10]]）。不设置 get 区就无法"不消费"——下一次 `sgetc()` 又会调用 `underflow()`，读走设备上的下一个字符，于是 `peek()` 两次得到不同的值。更严重的是默认的 `uflow()` 在 `underflow()` 成功后会读取 `*gptr()` 并 `gbump(1)`（¶16），而 `gptr()` 是空指针——{{ub}}。这类"无缓冲"实现必须同时覆写 `uflow`（读并消费一个字符），并在 `underflow` 里用一个单字符缓冲区保存已读未消费的字符。
</details>

<details markdown="1">
<summary>2. <code>overflow(eof())</code> 返回什么才算成功？</summary>

返回任何**不等于** `eof()` 的值（[[streambuf.virt.put#5]]）。惯用写法是 `return traits_type::not_eof(c);`——当 `c` 是 `eof()` 时，`not_eof` 返回某个非 `eof` 值；当 `c` 是普通字符时原样返回。直接 `return c;` 在 `c == eof()` 时会被误判为失败。
</details>

<details markdown="1">
<summary>3. 为什么 <code>in_avail()</code> 返回 0 并不意味着到了流尾？</summary>

`in_avail()` 在读位置不可用时返回 `showmanyc()`，而 `showmanyc()` 的默认值就是 0，表示"不知道"（[[streambuf.virt.get#2]]）。只有返回 −1 才表示后续读取一定失败。所以 `readsome` 读到 0 个字符可能只是缓冲区暂时为空。
</details>

## 小结

| 方向 | 快速路径（非虚） | 慢速路径（虚） | 派生类最少要覆写 |
|---|---|---|---|
| 读 | `sgetc`/`sbumpc`：`*gptr()` | `underflow`（看）/`uflow`（读走） | `underflow` + `setg`（或无缓冲时 `underflow` + `uflow`） |
| 回退 | `sputbackc`/`sungetc`：`--gptr()` | `pbackfail` | 可选 |
| 写 | `sputc`：`*pptr()++` | `overflow` | `overflow`（加 `setp` 则还要 `sync`） |
| 批量 | — | `xsgetn`/`xsputn` | 可选，用于性能 |
| 定位 | — | `seekoff`/`seekpos`（默认失败） | 需要 `seekg`/`tellp` 时 |
| 刷新 | — | `sync`（默认返回 0） | 有 put 区时 |
