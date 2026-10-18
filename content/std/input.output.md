---
title: 输入/输出库
summary: 第 31 章导读——iostream 的三层结构（ios_base/basic_ios 管状态与格式，basic_streambuf 管缓冲与传输，istream/ostream 管解析与生成）、本章各头文件的分工、与 <format>/<print>、<cstdio>、<filesystem> 的关系，以及读本章前要先建立的几个心智模型
status: done
covers: input.output.general
related: iostreams.requirements, iostream.objects, iostreams.base, stream.buffers, iostream.format, string.streams, span.streams, file.streams, syncstream, filesystems, c.files, format, stream.iterators, localization
tags: 标准库, iostream, I/O, 导读
updated: 2026-10-18
---

第 31 章 [input.output] 是标准库里历史最长的一块：`iostream` 的设计可以追溯到 C++ 标准化之前，它的很多“怪癖”（`eof()` 的含义、`std::hex` 会一直生效、`>>` 默认跳过空白、`endl` 会刷新）都不是 bug，而是这套设计的直接后果。读懂本章的关键，是先看清它的**分层**，再去读每一层的契约。

¶1 只说本章描述 C++ 程序执行输入/输出操作的组件。¶2 的表 135 列出子条款与头文件：

| 子条款 | 内容 | 头文件 | 本站笔记 |
|---|---|---|---|
| [iostreams.requirements] | 对 `charT`/`traits` 的限制、`streamoff`/`streamsize`、线程安全 | — | [[iostreams.requirements]] |
| [iostream.forward] | 所有流类模板的前置声明与 `typedef` | `<iosfwd>` | [[iostream.objects]] |
| [iostream.objects] | `cin`/`cout`/`cerr`/`clog` 及宽字符版本 | `<iostream>` | [[iostream.objects]] |
| [iostreams.base] | `ios_base`、`basic_ios`、`fpos`、状态位、格式标志、`io_errc` | `<ios>` | [[iostreams.base]] |
| [stream.buffers] | `basic_streambuf`：get/put 区与虚函数协议 | `<streambuf>` | [[stream.buffers]] |
| [iostream.format] | `basic_istream`/`basic_ostream`/`basic_iostream`、操纵符、`print` | `<istream>`、`<ostream>`、`<iomanip>`、`<print>` | [[iostream.format]]、[[input.streams]]、[[output.streams]] |
| [string.streams] | 以 `basic_string` 为存储的流 | `<sstream>` | [[string.streams]] |
| [span.streams] | 以 `span<charT>` 为存储的流（C++23） | `<spanstream>` | [[span.streams]] |
| [file.streams] | 文件流 `basic_filebuf`/`fstream` | `<fstream>` | [[file.streams]] |
| [syncstream] | 多线程下不交错的输出 `osyncstream`（C++20） | `<syncstream>` | [[syncstream]] |
| [filesystems] | `std::filesystem`：路径、目录遍历、文件操作 | `<filesystem>` | [[filesystems]]、[[fs.class.path]]、[[fs.class.directory.iterator]]、[[fs.op.funcs]] |
| [c.files] | C 的 `<stdio.h>`、`<inttypes.h>` | `<cstdio>`、`<cinttypes>` | [[c.files]] |

注意：¶2 的正文只列举到“文件流”，表里却多了 span 流、同步流、文件系统和 C 库——正文是旧措辞，表 135 才是完整清单。另外，流迭代器（`istream_iterator`、`istreambuf_iterator` 等）虽然只对流有意义，却规定在迭代器章的 [[stream.iterators]]；格式化本身（`std::format`、格式串语法、`formatter`）在 [[format]]；`locale`、`num_get`/`num_put`、`codecvt` 在本地化章 [[localization]]。

## iostream 的三层结构

把一次 `std::cout << 42` 拆开看，它经过三个各司其职的对象：

```text
 用户代码:      cout << 42;          cin >> x;
                    │                    │
  ┌─────────────────┴────────────────────┴──────────────────┐
  │ basic_ostream / basic_istream      （[iostream.format]）  │  解析与生成：
  │   operator<< / >>、put/write、get/read/getline            │  sentry、num_put/num_get、
  │   每个 I/O 函数先构造 sentry                              │  setstate(状态位)
  ├──────────────────────────────────────────────────────────┤
  │ basic_ios<charT,traits> : ios_base   （[iostreams.base]）  │  状态与格式：
  │   rdstate()/exceptions()  flags()/width()/precision()     │  iostate、fmtflags、
  │   fill()  tie()  getloc()  rdbuf() ───────────┐           │  locale、tie
  ├───────────────────────────────────────────────┼──────────┤
  │ basic_streambuf<charT,traits>  （[stream.buffers]）   ◀──┘ │  缓冲与传输：
  │   get 区 [eback, gptr, egptr)  put 区 [pbase, pptr, epptr) │  underflow/overflow/
  │   派生：filebuf / stringbuf / spanbuf / syncbuf           │  sync/seekoff…
  └──────────────────────────────────────────────────────────┘
                    │
          文件 / FILE* / string / span / 另一个 streambuf
```

- **流缓冲区**（[[g:stream-buffer]]）是唯一真正碰到“外部”的那一层：它决定字符从哪来、到哪去、何时搬运。换一个 streambuf，同一个 `ostream` 就可以写文件、写字符串、写网络。
- **`basic_ios`**（以及它的基类 `ios_base`）只是一包状态：错误状态位、异常掩码、格式标志、宽度、精度、填充字符、`locale`、`tie` 指针、指向 streambuf 的指针。它是 `basic_istream` 和 `basic_ostream` 的**虚基类**（[[iostream.forward.overview#1]]），所以 `basic_iostream` 里只有一份。
- **`basic_istream`/`basic_ostream`** 负责“字符序列 ↔ 值”的转换：数值转换委托给 `locale` 中的 `num_get`/`num_put`，它们通过 `istreambuf_iterator`/`ostreambuf_iterator` **绕过流、直接操作 streambuf**（[[input.streams]]、[[output.streams]]）。

于是“流”这个词在标准里有两种含义，读条文时要分清：**流对象**（`basic_ios` 的派生类，有状态位）和**流缓冲区**（`basic_streambuf` 的派生类，有缓冲指针）。`cout.flush()` 是流对象的成员，它的效果是调用 `rdbuf()->pubsync()`。

## 读本章前的几个心智模型

1. **状态位是“粘”的，且记录的是“已经发生的事”。** `eofbit` 表示某次输入操作**撞到了**序列末尾，而不是“下一次读会失败”。所以 `while (!in.eof())` 是错的；正确的循环以提取本身为条件：`while (in >> x)`。详见 [[iostreams.base]] 与 [[input.streams]]。
2. **格式标志也是“粘”的，宽度例外。** `std::hex`、`std::fixed`、`std::setfill` 一直生效，直到被改掉；只有 `width` 会被大多数格式化输出函数在用完后清零（[[output.streams]]）。
3. **每个 I/O 函数都先构造 sentry**（[[g:sentry]]）：它检查 `good()`、刷新 `tie()` 绑定的流、（输入时）跳过空白。理解了 sentry，就理解了为什么 `cin >> x` 之前 `cout` 的提示一定会出现，为什么流处于 `eof` 状态时连 `tellg()` 都会失败。
4. **标准流默认与 C 的 stdio 同步。** `cout` 与 `printf` 可以随意交错，代价是可能逐字符地经过 `FILE*`；`sync_with_stdio(false)` 解除这一保证（[[iostream.objects]]）。
5. **iostream 不是线程安全的**——除了少数例外。并发访问同一个流对象或 streambuf 是数据竞争（[[iostreams.requirements]]），例外是同步状态下的标准流对象，以及专门为此设计的 `osyncstream`（[[syncstream]]）。

## 与 `<format>`/`<print>` 和 `<cstdio>` 的关系

C++20 的 `std::format` 和 C++23 的 `std::print` 并没有取代 iostream 的**传输**层，只取代了它的**格式化**层：

- `std::print(FILE*, ...)`（[[print.fun]]）直接写 C 流；
- `std::print(std::ostream&, ...)`（[[ostream.formatted.print]]）先用 `vformat` 生成字符串，再通过 `ostream` 的 sentry 和 streambuf 写出，**不受**流的 `width`/`flags` 影响，但使用流的 `locale`（仅当格式串里出现 `L` 选项时）。

格式串语法与 `formatter` 的规则在 [[format]]、[[format.string]]、[[format.formatter]]，本章不重复。

`<cstdio>` 的内容与 C 标准库的 `<stdio.h>` 相同（[[c.files]]），只增加了 C++ 视角的几条规定：写文件的函数调用返回是可观察检查点（observable checkpoint），`%p` 的 `fscanf` 结果如何选指针值，以及 `tmpnam(nullptr)` 的数据竞争。

## `<filesystem>`：本章的另一半

[filesystems] 与 iostream 几乎没有交集：它不读写文件内容，而是处理**路径**（纯字面运算的 `path`）和**文件系统中的对象**（目录遍历、状态查询、复制、删除）。它的条文风格也不同——大量以 POSIX 为参照（“as if by POSIX stat”），每个可能失败的操作都有抛异常和 `error_code&` 两套重载，并明确规定文件系统竞争导致未定义行为。从 [[filesystems]] 开始读。

## 小结

| 想了解 | 去读 |
|---|---|
| `eof`/`fail`/`bad` 的精确含义、异常掩码、格式标志、`xalloc` | [[iostreams.base]] |
| 自己写 streambuf：`underflow`/`overflow`/`sync` 的契约 | [[stream.buffers]] |
| `>>`、`getline`、`read`、`ignore`、sentry 的逐步行为 | [[input.streams]] |
| `<<`、宽度与填充、`endl` 与刷新、`print(ostream&)` | [[output.streams]] |
| `setw`/`setprecision`/`quoted`/`put_time`、`std::print` | [[iostream.format]] |
| `cout` 什么时候构造、静态初始化顺序、`sync_with_stdio` | [[iostream.objects]] |
| 多线程写 `cout` | [[iostreams.requirements]]、[[syncstream]] |
| 内存中的流 | [[string.streams]]、[[span.streams]] |
| 文件流、打开模式、`native_handle` | [[file.streams]] |
| 路径、目录遍历、文件操作与 TOCTOU | [[filesystems]] 及其子页 |
