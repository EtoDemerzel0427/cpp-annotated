---
title: C 库文件：<cstdio> 与 <cinttypes>
summary: <cstdio> 和 <cinttypes> 的内容同 C23 的对应头文件；C++ 只追加了几条规定：写文件的调用返回是可观察检查点，fscanf 的 %p 如何选指针，tmpnam(nullptr) 可能数据竞争，以及 intmax_t 为扩展整数类型时的 abs/div 重载。
status: done
covers: *
related: input.output, iostream.objects, file.streams, print.fun, format, intro.abstract, basic.compound, support.c.headers, cstdint.syn
tags: 标准库, C 库, cstdio, printf, cinttypes
updated: 2026-10-19
---

!!! tldr
    - `<cstdio>` 和 `<cinttypes>` 的内容与 C 标准库的 `<stdio.h>`、`<inttypes.h>` 相同，当前草案以 C23 为准；C++ 里没有 `gets`。
    - C++26 起，把数据交付给宿主环境的写文件调用，其返回是可观察检查点；还留在 `FILE` 缓冲区里的数据不算交付。
    - `printf` 族的格式说明与实参类型不符是 UB；`std::print` 在编译期检查格式，没有这个问题。
    - `PRI`/`SCN` 宏只在对应的定宽类型存在时才定义，`SCN` 宏还要求 `scanf` 有合适的长度修饰符。

## `<cstdio>` [cstdio.syn]

¶1 `<cstdio>` 的内容与含义同 C 的 `<stdio.h>`。条文引用的是 ISO/IEC 9899:2024（C23）7.23 节，所以概要里有 C23 新增的 `__STDC_VERSION_STDIO_H__` 和 `_PRINTF_NAN_LEN_MAX`。

概要列出的函数分为文件操作（`remove`、`rename`、`tmpfile`、`tmpnam`）、文件访问（`fopen`、`fclose`、`fflush`、`setvbuf` 等）、格式化 I/O（`printf`、`scanf` 两族）、字符 I/O、直接 I/O（`fread`、`fwrite`）、文件定位和错误处理。有几处要注意：

- 没有 `gets`。它无法防止缓冲区溢出，C11 删除了它，C++14 随之删除。
- 宽字符 I/O（`fwprintf`、`fgetwc` 等）在 `<cwchar>`。
- `stdin`、`stdout`、`stderr` 是宏，不是 `std` 中的变量，不能写 `std::stdout`。

### 写文件的调用返回是可观察检查点（¶2）{{c++26}}

```cpp title="checkpoint.cpp" ub
#include <cstdio>
int main(int argc, char**) {
  std::fputs("before\n", stderr);  // stderr 无缓冲
  int* p = nullptr;
  if (argc > 0) return *p;         // UB: 空指针解引用
}
```

C++23 及以前，一次执行只要含有 UB，标准对整个执行都不作要求，连 UB 之前的输出也不保证出现。C++26 给出了边界：实现必须产生 UB 之前、最后一个**可观察检查点**（observable checkpoint）之前的全部可观察行为（[[intro.abstract#5]]、[[intro.abstract#6]]）。

¶2 规定，每个把数据交付给宿主环境、以便写入文件的函数调用，其返回是一个可观察检查点。上例中 `stderr` 无缓冲，`fputs` 返回时数据已经交给了操作系统，所以 "before" 必须出现。

关键在交付二字。写进 `FILE` 自己缓冲区、还没刷新的数据没有交付。`stdout` 连到管道或文件时通常是全缓冲的，`printf("before\n")` 返回时数据可能还在进程内存里，之后的 UB 仍然可以让它丢失。需要保证时，调用 `fflush`，或写 `stderr`。[[intro.abstract#8]] 的注 4 还提醒，并非所有宿主环境都能在程序终止前访问文件内容。

### `%p` 读回的指针（¶3）

¶3 `fscanf` 的 `%p` 把文本转换回指针。同一个地址可能对应多个指针值，例如一个数组末尾之后的地址，数值上可能恰好等于紧挨着的另一个对象的地址（[[basic.compound]]）。这时得到的指针是所有能让程序具有已定义行为的候选值中未指定的一个；一个都没有时，行为未定义。

这条规定的背景是：在 C++ 的对象模型里，指针不只是一个地址，它还指向（或越过）某个特定的对象。从文本还原出来的指针，需要确定它属于哪个对象。

### `tmpnam` 的数据竞争（¶4）

¶4 以空指针调用 `tmpnam` 时，它把结果写进一个内部静态缓冲区，所以可能与其他以空指针调用 `tmpnam` 的调用产生数据竞争（[[res.on.data.races]]）。

`tmpnam` 还有一个更根本的问题：生成名字和创建文件之间，别的进程可能抢先创建同名文件。应改用 `tmpfile`，或者用 `fopen(name, "wx")` 独占地创建文件，见下面的例子。

### `printf` 族不检查类型

```cpp title="printf-mismatch.cpp" ub
#include <cstdio>
int main() {
  long long n = 1LL << 40;
  std::printf("%d\n", n);  // UB: %d 期望 int
}
```

C 标准规定，实参不是转换说明要求的类型时，行为未定义。格式串是字面量时，Clang 会给出 `-Wformat` 警告，但标准不要求诊断。本机运行打印 `0`。

`std::print("{}\n", n)` 在编译期检查格式串，参数类型由模板推导，不存在这类 UB（[[format]]、[[print.fun]]）。仍要用 `printf` 时，定宽整数用 `<cinttypes>` 的宏；需要知道格式化结果的长度，就先调用 `snprintf(nullptr, 0, ...)`：

```cpp run title="cstdio-portable.cpp" ok
#include <cinttypes>
#include <cstdio>
#include <memory>

int main() {
  std::int64_t big = 1234567890123;
  std::printf("%" PRId64 " %" PRIx64 "\n", big, big);
  // 1234567890123 11f71fb04cb

  int need = std::snprintf(nullptr, 0, "%d-%s", 42, "answer");  // 9
  auto buf = std::make_unique<char[]>(need + 1);
  std::snprintf(buf.get(), need + 1, "%d-%s", 42, "answer");
  std::puts(buf.get());                                         // 42-answer

  std::FILE* f = std::fopen("cf.tmp", "wx");  // "x": 已存在则失败
  std::printf("first: %s\n", f ? "ok" : "failed");   // ok
  if (f) std::fclose(f);
  std::FILE* g = std::fopen("cf.tmp", "wx");
  std::printf("second: %s\n", g ? "ok" : "failed");  // failed
  if (g) std::fclose(g);
  std::remove("cf.tmp");
}
```

### 与 C++ 其余部分的关系

- `cin`、`cout`、`cerr`、`clog` 分别关联到 `stdin`、`stdout`、`stderr`，默认与它们同步，可以交错使用（[[iostream.objects]]）。
- `basic_filebuf` 的规格完全用 `fopen`、`fseek`、`fflush`、`fclose` 等描述（[[file.streams]]）。`openmode` 到 `fopen` 模式串的对应关系见 [[filebuf.members]] 的表 146，C++23 的 `noreplace` 对应 `"x"`。
- 多个线程并发使用标准 C 流（`stdin` 等）不构成数据竞争，但字符可能交错（[[iostream.objects.overview#7]]）。
- 一个 `FILE` 第一次被宽字符或窄字符函数使用后就确定了方向，之后混用另一种的后果按 C 标准处理；`cout` 和 `wcout` 都写 `stdout`，同样受此约束（[[iostream.objects.overview#6]]）。

## `<cinttypes>` [cinttypes.syn]

```cpp
#include <cstdint>
namespace std {
  using imaxdiv_t = see below;
  constexpr intmax_t imaxabs(intmax_t j);
  constexpr imaxdiv_t imaxdiv(intmax_t numer, intmax_t denom);
  intmax_t  strtoimax(const char* nptr, char** endptr, int base);
  uintmax_t strtoumax(const char* nptr, char** endptr, int base);
  intmax_t  wcstoimax(const wchar_t* nptr, wchar_t** endptr, int base);
  uintmax_t wcstoumax(const wchar_t* nptr, wchar_t** endptr, int base);
  constexpr intmax_t abs(intmax_t);              // 可选，见下
  constexpr imaxdiv_t div(intmax_t, intmax_t);   // 可选，见下
}
// 宏：PRI{d,i,o,u,x,X,b,B}N、SCN{d,i,o,u,x,b}N 等，
// N 为 8、16、32、64、LEAST8、FAST8、…、MAX、PTR
```

¶1 内容与含义同 C 的 `<inttypes.h>`，有两处变化：

- ¶1.1 它包含 `<cstdint>`（[[cstdint.syn]]），而不是 `<stdint.h>`；
- ¶1.2 当且仅当 `intmax_t` 是**扩展整数类型**（实现自己提供、不属于 `signed char` 到 `long long` 这五种标准类型的有符号整数类型，[[basic.fundamental]]）时，追加 `abs(intmax_t)` 和 `div(intmax_t, intmax_t)`，语义同 `imaxabs` 和 `imaxdiv`。

为什么是当且仅当？如果 `intmax_t` 就是 `long long`，`<cstdlib>` 里已经有 `abs(long long)` 和 `div(long long, long long)`，再声明一次就重复了。只有 `intmax_t` 比所有标准整数类型都宽时，才需要补上这两个重载，让 `std::abs(x)` 对任何整数类型都能用。

¶2 宏的定义条件：

- `PRI` 宏当且仅当 [[cstdint.syn]] 中对应的类型名存在时才定义，例如没有 `int24_t` 就没有 `PRId24`；
- `SCN` 宏除了要求类型存在，还要求 `fscanf` 有适合该类型的长度修饰符；
- `PRIB` 宏（二进制输出的大写形式，配合 `#` 标志时前缀为 `0B`）当且仅当 `fprintf` 支持 `B` 转换说明符时才定义。

```cpp run title="pri-macros.cpp" ok
#include <cinttypes>
#include <cstdio>

int main() {
  std::uint32_t mask = 0xF0F0;
  std::printf("%08" PRIX32 "\n", mask);  // 0000F0F0
#ifdef PRIb32
  std::printf("%" PRIb32 "\n", mask);    // C23 的二进制输出
#endif
}
```

本机（macOS libc）没有定义 `PRIb32`，所以第二行没有输出。

`strtoimax`、`strtoumax` 和 `strtol` 同族，错误通过 `errno` 和 `endptr` 报告。C++ 代码里更推荐 `std::from_chars`（[[charconv]]）：它不依赖 locale、不设置 `errno`，能准确报告在哪里停止解析。

## 思考题

!!! question "思考题"
    某个平台的 `<cinttypes>` 定义了 `PRId64`，却没有定义 `SCNd64`。这符合标准吗？

<details markdown="1">
<summary>答案</summary>

符合，前提是这个平台的 `fscanf` 没有适合 `int64_t` 的长度修饰符（[[cinttypes.syn#2]]）。两边的需求不对称。以 `int8_t` 为例：它作为可变实参会提升为 `int`，`printf` 用 `%d` 就能输出；`scanf` 却要把结果写进一个 1 字节的对象，必须有 `hh` 这样精确匹配的长度修饰符（C89 还没有 `hh`）。所以 `SCN` 宏多了一个条件。
</details>
