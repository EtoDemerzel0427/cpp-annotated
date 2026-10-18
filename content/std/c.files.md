---
title: C 库文件：<cstdio> 与 <cinttypes>
summary: <cstdio> 与 C 的 <stdio.h> 相同（现以 C23 为基准），C++ 只追加三条规定——写文件的函数调用返回是可观察检查点（C++26）、fscanf 的 %p 在多个指针值可选时如何选、tmpnam(nullptr) 可能数据竞争；printf 族格式不匹配是 UB、snprintf 求长度、FILE 与 iostream/print 的关系；<cinttypes> 的 PRI/SCN 宏何时定义、intmax_t 为扩展整数类型时追加的 abs/div 重载
status: done
covers: *
related: input.output, iostream.objects, iostreams.requirements, file.streams, print.fun, format, intro.abstract, basic.compound, support.c.headers, cstdint.syn
tags: 标准库, C 库, cstdio, printf, cinttypes
updated: 2026-10-18
---

[c.files] 收录 C 标准库中与 I/O 有关的两个头文件。和其他 `<cxxx>` 头文件一样，标准不重新描述它们，而是说"内容与含义同 C 标准库的对应头文件"，再列出少数 C++ 特有的补充。读这一节的重点是那几条补充，以及 C 的 I/O 函数与 C++ 其余部分（iostream、`std::print`、对象模型）之间的接口。

## `<cstdio>`（[cstdio.syn]）

### 概要

```cpp
#define __STDC_VERSION_STDIO_H__ 202311L
namespace std {
  using size_t = see [support.types.layout];
  using FILE = see below;
  using fpos_t = see below;
}
#define NULL / _IOFBF / _IOLBF / _IONBF / BUFSIZ / EOF / FOPEN_MAX / FILENAME_MAX
#define _PRINTF_NAN_LEN_MAX / L_tmpnam / SEEK_CUR / SEEK_END / SEEK_SET / TMP_MAX
#define stderr / stdin / stdout
namespace std {
  // 文件操作：remove rename tmpfile tmpnam
  // 文件访问：fclose fflush fopen freopen setbuf setvbuf
  // 格式化 I/O：fprintf fscanf printf scanf snprintf sprintf sscanf
  //            vfprintf vfscanf vprintf vscanf vsnprintf vsprintf vsscanf
  // 字符 I/O：fgetc fgets fputc fputs getc getchar putc putchar puts ungetc
  // 直接 I/O：fread fwrite
  // 文件定位：fgetpos fseek fsetpos ftell rewind
  // 错误处理：clearerr feof ferror perror
}
```

¶1：`<cstdio>` 的内容与含义与 C 标准库头文件 `<stdio.h>` 相同。条文末尾的 "See also" 引用的是 ISO/IEC 9899:2024（C23）的 7.23 节——当前草案以 C23 为 C 标准库的基准，所以出现了 C23 新增的 `__STDC_VERSION_STDIO_H__` 和 `_PRINTF_NAN_LEN_MAX`。

几个"不在列表里"的名字同样值得注意：

- **`gets` 不存在。** C11 删除了它（无法防止缓冲区溢出），C++14 随之删除。
- 宽字符 I/O（`fwprintf`、`fgetwc` 等）在 `<cwchar>`，不在这里。
- 与 C 相同，`stdin`/`stdout`/`stderr` 是**宏**，不是 `std` 中的变量，所以不能写 `std::stdout`。

### C++ 追加的规定

**¶2 可观察检查点** {{c++26}}：每个**把数据交付给宿主环境、以便写入文件**的函数调用（C 7.23.3）的**返回**，是一个可观察检查点（observable checkpoint，[[intro.abstract#5]]）。

这条规定配合 C++26 对未定义行为的新表述：实现只需产生执行的"已定义前缀"的可观察行为（[[intro.abstract#6]]）——某个 UB 操作之前、且 happens-before 某个可观察检查点的操作，其可观察行为必须保留。于是，`fprintf` 返回之后程序才出现 UB，`fprintf` 交付的数据不会因为"UB 可以时间旅行"而被优化器抹掉。

```cpp title="checkpoint.cpp" ub
#include <cstdio>

int main(int argc, char**) {
  std::fputs("before\n", stderr);   // stderr 无缓冲：数据已交付，返回处是可观察检查点
  int* p = nullptr;
  if (argc > 0) return *p;          // UB：但 "before" 的输出已在已定义前缀中，必须出现
}
```

但要注意"**交付给宿主环境**"这个限定：写进 `FILE` 自己缓冲区里、尚未 `fflush` 的数据还没有交付。对 `stdout`（连到管道或文件时通常是全缓冲），`printf("before\n")` 返回时数据很可能还在进程内存里，后面的 UB（比如崩溃）仍然会让它丢失。需要保证可见，就 `fflush` 或写 `stderr`。[[intro.abstract#8]] 的注也提醒：并非所有宿主环境都能在程序终止前访问文件内容。

**¶3 `%p` 与指针来源**：`fscanf`（及等价函数）的 `%p` 转换读到的输入项可以由**多个**指针值产生时（[[basic.compound]]——例如一个对象末尾之后的地址与另一个对象的地址数值相同），得到的指针是那些"能让程序具有已定义行为"的值中**未指定**的一个；不存在这样的值时，行为未定义。这是 C++ 对象模型中"指针不只是地址"在 C 库边界上的体现：从文本还原出来的指针，需要被赋予一个合适的来源（provenance）。

**¶4 `tmpnam` 的数据竞争**：以空指针调用 `tmpnam` 可能与其他以空指针调用 `tmpnam` 的调用产生数据竞争（[[res.on.data.races]]）——它返回的是一个内部静态缓冲区。（更根本的问题是 `tmpnam` 本身有 TOCTOU 竞争：生成名字与创建文件之间别人可能抢先创建；应改用 `tmpfile`，或用 `fopen(..., "wx")` 独占创建。）

### `printf` 族：类型不安全

`printf` 的格式串与实参在类型上不匹配是**未定义行为**（C 标准对 `fprintf` 的规定：实参不是相应转换说明所要求的正确类型时，行为未定义）。编译器能在格式串为字面量时给出警告，但这不是诊断要求：

```cpp title="printf-mismatch.cpp" ub
#include <cstdio>

int main() {
  long n = 1L << 40;
  std::printf("%d\n", n);   // UB：%d 期望 int；Clang 给出 -Wformat 警告
}
```

对比 `std::print("{}\n", n)`：格式串在编译期检查，类型由模板推导，不存在这类 UB（[[format]]、[[print.fun]]）。

可移植地打印定宽整数要用 `<cinttypes>` 的宏；求格式化结果的长度用 `snprintf(nullptr, 0, ...)`：

```cpp title="cstdio-portable.cpp" ok
#include <cinttypes>
#include <cstdio>
#include <memory>

int main() {
  std::int64_t big = 1234567890123;
  std::printf("%" PRId64 " %" PRIx64 "\n", big, big);       // 1234567890123 11f71fb04cb

  int need = std::snprintf(nullptr, 0, "%d-%s", 42, "answer");   // 只求长度：9
  auto buf = std::make_unique<char[]>(need + 1);
  std::snprintf(buf.get(), need + 1, "%d-%s", 42, "answer");
  std::puts(buf.get());                                       // 42-answer

  std::FILE* f = std::fopen("cf.tmp", "wx");                  // "x"：独占创建（C11 起）
  std::printf("first: %s\n", f ? "ok" : "failed");            // ok
  if (f) std::fclose(f);
  std::FILE* g = std::fopen("cf.tmp", "wx");
  std::printf("second: %s\n", g ? "ok" : "failed");           // failed：文件已存在
  if (g) std::fclose(g);
  std::remove("cf.tmp");
}
```

### 与 C++ 其余部分的接口

- **标准流对象**：`cin`/`cout`/`cerr`/`clog` 关联到 `stdin`/`stdout`/`stderr`，默认与它们同步，可以任意交错使用（[[iostream.objects]]）。
- **`basic_filebuf`**：规格完全以 `fopen`/`fseek`/`fsetpos`/`fflush`/`fclose` 描述，读写限制与 `FILE` 相同（[[file.streams]]）。`openmode` 到 `fopen` 模式串的映射（含 C++23 `noreplace` 对应的 `"x"`）见那里的表 146。
- **`std::print`**：直接写 `FILE*`，在持有流锁的情况下输出（[[print.fun]]）。
- **线程安全**：[[iostreams.threadsafety]] 规定并发访问同一个 C 库流"除非另有规定"可能构成数据竞争。对标准 C 流，[[iostream.objects.overview#7]] 明确规定不构成数据竞争；对一般的 `FILE*`，C 标准本身规定每个流有一把锁、库函数如同在操作期间持有它（C 7.23.2），实践中各个 `printf` 调用之间不会出现数据竞争，但多次调用之间的输出会交错。
- **宽窄定向**：一个 `FILE` 第一次被宽字符或窄字符函数使用后就有了"定向"，之后混用另一种是未定义行为（C 7.23.2）；`cout` 与 `wcout` 都写 `stdout`，因此同样受此约束（[[iostream.objects.overview#6]]）。

## `<cinttypes>`（[cinttypes.syn]）

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
#define __STDC_VERSION_INTTYPES_H__ 202311L
// PRI{d,i,o,u,x,X,b,B}{N,LEASTN,FASTN,MAX,PTR}
// SCN{d,i,o,u,x,b}{N,LEASTN,FASTN,MAX,PTR}
```

¶1：内容与含义同 C 的 `<inttypes.h>`，但有两处变化：

- ¶1.1：包含的是 `<cstdint>`（[[cstdint.syn]]）而不是 `<stdint.h>`；
- ¶1.2：**当且仅当** `intmax_t` 是**扩展整数类型**（[[basic.fundamental]]）时，追加 `constexpr intmax_t abs(intmax_t)` 和 `constexpr imaxdiv_t div(intmax_t, intmax_t)`，语义分别同 `imaxabs` 与 `imaxdiv`。

为什么是"当且仅当"？若 `intmax_t` 是 `long long` 这样的标准整数类型，`<cstdlib>` 里已经有 `abs(long long)` 和 `div(long long, long long)`，再声明一次就重复了；只有当 `intmax_t` 是实现扩展的、比 `long long` 更宽的类型时，才需要补上这两个重载，让 `std::abs(x)` 对任何整数类型都可用。

¶2 规定宏何时被定义：

- 每个 `PRI` 宏**当且仅当**实现定义了 [[cstdint.syn]] 中对应的 *typedef-name* 时才定义（例如没有 `int24_t` 就没有 `PRId24`）；
- 每个 `SCN` 宏**当且仅当**对应的 *typedef-name* 被定义、**且** `fscanf` 有适合该类型的长度修饰符时才定义；
- 每个 `PRIB` 宏当且仅当 `fprintf` 支持 C23 的 `B` 转换说明符（大写二进制前缀）时才定义。`PRIb`（小写 `b`）随 C23 成为 `printf` 的标准转换。

```cpp title="pri-macros.cpp" ok
#include <cinttypes>
#include <cstdio>

int main() {
  std::uint32_t mask = 0xF0F0;
  std::printf("%08" PRIX32 "\n", mask);            // 0000F0F0
  std::uintptr_t addr = reinterpret_cast<std::uintptr_t>(&mask);
  std::printf("%s\n", addr != 0 ? "has address" : "null");
#ifdef PRIb32
  std::printf("%" PRIb32 "\n", mask);              // C23 的二进制输出（若实现支持）
#endif
}
```

`strtoimax`/`strtoumax` 与 `strtol` 同族，错误通过 `errno` 和 `endptr` 报告；C++ 代码中更推荐 `std::from_chars`（[[charconv]]）：不依赖 locale、不设置 `errno`、能精确报告错误位置。

## 思考题

<details markdown="1">
<summary>1. 程序先 <code>printf("step 1\n")</code>，随后发生空指针解引用而崩溃。终端（行缓冲）上看到了 "step 1"，重定向到文件时却没有。这与 C++26 的可观察检查点矛盾吗？</summary>

不矛盾。[[cstdio.syn#2]] 说的是"把数据**交付给宿主环境**的函数调用返回"才是检查点。终端上 `stdout` 是行缓冲的，`printf` 遇到换行就把数据交给了操作系统；重定向到文件时 `stdout` 是全缓冲的，`printf` 只是把数据写进进程内的缓冲区，并没有交付，因而不构成检查点。崩溃时缓冲区随进程消失。要可靠记录，用 `stderr`（无缓冲）或在关键点 `fflush(stdout)`。
</details>

<details markdown="1">
<summary>2. <code>&lt;cinttypes&gt;</code> 在某个平台上定义了 <code>PRId64</code> 却没有定义 <code>SCNd64</code>，这符合标准吗？</summary>

符合，只要 `fscanf` 没有适合 `int64_t` 的长度修饰符（[[cinttypes.syn#2]]）。`PRI` 宏只依赖类型是否存在（`printf` 的默认实参提升使得输出总能找到合适的说明符），`SCN` 宏还额外要求 `scanf` 能把结果直接存入该类型的对象。
</details>

## 小结

- `<cstdio>`、`<cinttypes>` 的内容同 C（当前以 C23 为基准）；没有 `gets`；`stdin` 等是宏。
- C++ 追加：写文件的调用返回是可观察检查点（C++26，但缓冲在 `FILE` 内的数据尚未交付）；`%p` 读出的指针在多个候选中未指定地选一个有定义行为的；`tmpnam(nullptr)` 可能数据竞争。
- `printf` 族格式不匹配是 UB；优先使用 `std::print`/`std::format`，或至少用 `PRI` 宏和 `snprintf`。
- `<cinttypes>` 的 `abs`/`div(intmax_t)` 只在 `intmax_t` 是扩展整数类型时出现；`PRI`/`SCN`/`PRIB` 宏按类型和 `printf`/`scanf` 的能力条件定义。
