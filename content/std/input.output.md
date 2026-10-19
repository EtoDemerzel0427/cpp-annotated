---
title: 输入/输出库
summary: 第 31 章导读：iostream 由状态层、格式化层和缓冲层组成；各子条款和头文件的分工；它与 <format>/<print>、<cstdio>、<filesystem> 的关系。
status: done
covers: input.output.general
related: iostreams.requirements, iostream.objects, iostreams.base, stream.buffers, iostream.format, string.streams, span.streams, file.streams, syncstream, filesystems, c.files, format, stream.iterators, localization
tags: 标准库, iostream, I/O, 导读
updated: 2026-10-19
---

!!! tldr
    - 一个 iostream 流由三层组成：`basic_streambuf` 负责缓冲和搬运字符，`ios_base`/`basic_ios` 保存状态和格式，`basic_istream`/`basic_ostream` 在值和字符之间转换。
    - 换掉流缓冲区，同一个 `ostream` 就能写字符串、文件或终端；格式状态留在流对象上。
    - 状态位记录已经发生的事，`eofbit` 表示某次读取撞到了末尾，所以读循环要以提取本身为条件。
    - `std::format`、`std::print` 取代的是格式化层，字符仍然经由流缓冲区或 C 的 `FILE*` 写出。
    - `<filesystem>` 也在这一章，但它处理路径和目录，不读写文件内容。

## 三层结构

```cpp run ok
#include <iostream>
#include <sstream>

int main() {
  std::stringbuf sb;               // 缓冲层：字符存进 string
  std::ostream out(&sb);           // 格式化层和状态层
  out << std::hex << 255;
  std::cout << sb.str() << '\n';   // ff

  out.rdbuf(std::cout.rdbuf());    // 换成 stdout 的缓冲区
  out << 255 << '\n';              // ff：hex 还在 out 上
}
```

`out` 本身不知道字符最终去了哪里。它把 255 按十六进制变成字符 `ff`，交给自己指向的流缓冲区；换了缓冲区，输出目的地就变了，而 `hex` 这个格式标志仍然留在 `out` 上。

一次 `cout << 42` 依次经过三层：

```text
 用户代码:      cout << 42;          cin >> x;
                    │                    │
  ┌─────────────────┴────────────────────┴───────────────┐
  │ basic_ostream / basic_istream     [iostream.format]   │  值 ↔ 字符：
  │   operator<< / >>、put/write、get/read/getline        │  sentry、num_put/num_get
  ├───────────────────────────────────────────────────────┤
  │ basic_ios<charT,traits> : ios_base   [iostreams.base] │  状态与格式：
  │   rdstate()/exceptions()  flags()/width()/precision() │  iostate、fmtflags、
  │   fill()  tie()  getloc()  rdbuf() ─────────┐         │  locale、tie
  ├─────────────────────────────────────────────┼─────────┤
  │ basic_streambuf<charT,traits> [stream.buffers] ◀──┘   │  缓冲与搬运：
  │   get 区、put 区                                       │  underflow/overflow/sync
  │   派生：filebuf / stringbuf / spanbuf / syncbuf        │
  └───────────────────────────────────────────────────────┘
                    │
          文件 / FILE* / string / span / 另一个 streambuf
```

**流缓冲区**（[[g:stream-buffer]]，`basic_streambuf` 的派生类）是唯一接触外部的一层：它决定字符从哪里来、到哪里去、什么时候搬运。自定义一个 streambuf，就能让所有现成的 `<<`、`>>` 写到网络或压缩文件里，见 [[stream.buffers]]。

`basic_ios` 和它的基类 `ios_base` 只是一组状态：错误状态位、异常掩码、格式标志、宽度、精度、填充字符、`locale`、`tie` 指针，以及指向流缓冲区的指针。`basic_ios` 是 `basic_istream` 和 `basic_ostream` 的虚基类，所以同时继承两者的 `basic_iostream` 里只有一份状态（[[iostream.objects]]）。详见 [[iostreams.base]]。

`basic_istream`/`basic_ostream` 负责值和字符之间的转换。数值转换委托给 `locale` 里的 `num_get`/`num_put` facet，它们直接操作流缓冲区（[[input.streams]]、[[output.streams]]）。

所以标准里的"流"有两种对象，读条文时要分清：流对象有状态位，流缓冲区有缓冲指针。`cout.flush()` 是流对象的成员，它的效果是调用 `rdbuf()->pubsync()`。

## 几条贯穿全章的规则

```cpp run ok
#include <iostream>
#include <sstream>

int main() {
  std::istringstream in("1 2 3\n");
  int x, n = 0;
  while (!in.eof()) {   // 错误的循环条件
    in >> x;
    ++n;
  }
  std::cout << n << '\n';   // 4：最后一次提取失败了
}
```

读完 `3` 之后，流停在换行符前面，`eofbit` 还没有置位，于是循环又执行了一次。这次提取跳过换行、撞到末尾，失败了，`x` 不变，计数却加了一。

1. 状态位一旦置位就保持，直到被清除，而且记录的是已经发生的事：`eofbit` 表示某次输入撞到了序列末尾，不预言下一次读取。正确的写法是 `while (in >> x)`，见 [[iostreams.base]]。
2. 格式标志也一直生效，`std::hex`、`std::fixed`、`std::setfill` 直到被改掉为止。例外是宽度：大多数格式化输出用完它就把它清零（[[output.streams]]）。
3. 每个输入输出函数先构造一个 **sentry** 对象（[[g:sentry]]）。它检查流状态、刷新绑定（tie）的输出流，格式化输入时还跳过前导空白。`cin >> x` 之前 `cout` 的提示一定会显示，就是 sentry 刷新了 `cout`。
4. 标准流对象默认与 C 的 stdio 同步，`cout` 和 `printf` 的输出可以任意交错。`sync_with_stdio(false)` 放弃这一保证（[[iostream.objects]]）。
5. 多个线程并发访问同一个流对象或流缓冲区是数据竞争。例外是处于同步状态的标准流对象，以及为此设计的 `osyncstream`（[[iostreams.requirements]]、[[syncstream]]）。

## 子条款与头文件（¶1–¶2）

¶1 第 31 章描述 C++ 程序做输入输出用的组件。¶2 的表 135 列出子条款和对应的头文件：

| 子条款 | 内容 | 头文件 | 本站笔记 |
|---|---|---|---|
| [iostreams.requirements] | 对 `charT`、`traits` 的限制，`streamoff`/`streamsize`，线程安全 | | [[iostreams.requirements]] |
| [iostream.forward] | 所有流类模板的前置声明和别名 | `<iosfwd>` | [[iostream.objects]] |
| [iostream.objects] | `cin`/`cout`/`cerr`/`clog` 及宽字符版本 | `<iostream>` | [[iostream.objects]] |
| [iostreams.base] | `ios_base`、`basic_ios`、`fpos`、状态位、格式标志 | `<ios>` | [[iostreams.base]] |
| [stream.buffers] | `basic_streambuf` | `<streambuf>` | [[stream.buffers]] |
| [iostream.format] | 输入输出流、操纵符、`print` | `<istream>`、`<ostream>`、`<iomanip>`、`<print>` | [[iostream.format]]、[[input.streams]]、[[output.streams]] |
| [string.streams] | 以 `basic_string` 为存储的流 | `<sstream>` | [[string.streams]] |
| [span.streams] | 以 `span<charT>` 为存储的流 {{c++23}} | `<spanstream>` | [[span.streams]] |
| [file.streams] | 文件流 | `<fstream>` | [[file.streams]] |
| [syncstream] | 多线程下不交错的输出 {{c++20}} | `<syncstream>` | [[syncstream]] |
| [filesystems] | 路径、目录遍历、文件操作 | `<filesystem>` | [[filesystems]] |
| [c.files] | C 的文件函数 | `<cstdio>`、`<cinttypes>` | [[c.files]] |

几样与流有关的东西不在本章。`istream_iterator`、`istreambuf_iterator` 等流迭代器在迭代器一章的 [[stream.iterators]]；`std::format` 和格式串语法在 [[format]]；`locale`、`num_get`/`num_put`、`codecvt` 在本地化一章 [[localization]]。

## 与 `<format>`/`<print>`、`<cstdio>` 的关系

C++20 的 `std::format` 和 C++23 的 `std::print` 只取代了 iostream 的格式化层，字符的传输仍然走原来的路径：

- `std::print(FILE*, ...)`（[[print.fun]]）直接写 C 流；
- `std::print(std::ostream&, ...)`（[[ostream.formatted.print]]）先用 `vformat` 生成字符串，再经由流的 sentry 和流缓冲区写出。流的 `width`、`flags` 不影响结果；流的 `locale` 只在格式串使用 `L` 选项时起作用。

`<cstdio>` 的内容与 C 的 `<stdio.h>` 相同（[[c.files]]）。C++ 只补充了三条：把数据交付给宿主环境写入文件的函数调用返回时是一个可观察检查点（[[intro.compliance]]）；`fscanf` 的 `%p` 读到的值对应多个指针值时，结果在其中未指定地选一个；以空指针调用 `tmpnam` 可能与其他这样的调用发生数据竞争。

## `<filesystem>`

[filesystems] 与 iostream 几乎没有交集。它不读写文件内容，只处理路径（`path` 上的运算都是纯字符串运算）和文件系统中的对象（目录遍历、状态查询、复制、删除）。条文大量以 POSIX 为参照，每个可能失败的操作都有抛异常和接受 `error_code&` 两套重载，并且规定了文件系统竞争导致未定义行为。从 [[filesystems]] 开始读。

## 小结

| 想了解 | 去读 |
|---|---|
| `eof`/`fail`/`bad` 的精确含义、异常掩码、格式标志、`xalloc` | [[iostreams.base]] |
| 自己写 streambuf：`underflow`/`overflow`/`sync` 的契约 | [[stream.buffers]] |
| `>>`、`getline`、`read`、`ignore`、sentry 的逐步行为 | [[input.streams]] |
| `<<`、宽度与填充、`endl` 与刷新、`print(ostream&)` | [[output.streams]] |
| `setw`/`setprecision`/`quoted`/`put_time`、`std::print` | [[iostream.format]] |
| `cout` 什么时候构造、`sync_with_stdio` | [[iostream.objects]] |
| 多线程写 `cout` | [[iostreams.requirements]]、[[syncstream]] |
| 内存中的流 | [[string.streams]]、[[span.streams]] |
| 文件流、打开模式、`native_handle` | [[file.streams]] |
| 路径、目录遍历、文件操作 | [[filesystems]] 及其子页 |

<details class="fine" markdown="1"><summary>其余条文</summary>

¶2 的正文只列举到文件流为止，没有提 span 流、同步流、文件系统和 C 库文件；表 135 是完整的清单。

</details>
