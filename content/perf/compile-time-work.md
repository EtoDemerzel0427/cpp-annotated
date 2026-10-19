---
title: 把计算挪到编译期
summary: 查找表、常量参数和分支什么时候值得在编译期算好，结果落在二进制的哪里，运行期省下多少，编译时间和体积又多付出多少。
status: draft
order: 80
group: 代码
since: c++11
papers: P1383R2, P1967R14
related: expr.const.defns, dcl.constinit, basic.start.static, intro.abstract, intro.object, stmt.if, expr.new, cpp.embed, implimits, topics/compile-time-programming, perf/compiler-optimizations, perf/reading-assembly, perf/measuring, perf/allocation, perf/choosing-containers
tags: 性能, constexpr, consteval, constinit, 查找表, 模板, 编译时间, embed
updated: 2026-10-19
---

!!! tldr
    - 编译期建好的查找表放在只读数据段里，启动时不花时间、第一次使用时也不用检查；但查表本身和运行期建的表一样快，省下的只是一次性的建表开销。
    - `constexpr` 只表示可以在编译期求值；要保证在编译期完成，用 `constexpr` 变量、`constinit` 或 `consteval` 函数接住结果。不写 `constexpr` 的小计算，优化器多半也会自己折叠。
    - 把运行期的小整数变成模板实参（必要时用 `switch` 分派到几个实例），本机上让 3×3 到 8×8 的矩阵乘法快了 2.4 到 3 倍；`if constexpr` 能把循环里的标志判断整个删掉。
    - 代价是编译时间和体积：本机 Clang 23 的常量求值器建一张 65536 项的正弦表要 2.5 秒 CPU 时间，同样的数据写成字面量只要 0.09 秒；每多一个模板实例，代码段就多一份。
    - 大块二进制数据用 `#embed` 嵌入，本机 1 MiB 数据的编译时间从 0.51 秒降到 0.04 秒。

本页的数字都是本机实测：Apple M2 Pro，macOS，Homebrew Clang 23.1.3 + libc++，arm64，`-O2`。测量时机器负载很高，所以只比较同一程序里先后测得的相对结果，编译时间取 5 次中最小的 user CPU 时间。换一台机器、换一个编译器，数字都会变；要看的是测量方法和结论的方向。怎样搭测量环境见 [[perf/measuring|测量]]，怎样读汇编见 [[perf/reading-assembly|读汇编]]。

## 测量用的小工具

后面的运行期数字都来自同一个计时函数：

```cpp title="bench.h" ok
#include <algorithm>
#include <chrono>
#include <vector>

// 让编译器认为 v 被读取了，不能把计算删掉
template <class T> inline void escape(T const& v) {
  asm volatile("" : : "r"(&v) : "memory");
}

template <class F>
double bench_ns(F f, int reps = 51, long iters = 1000) {
  for (long i = 0; i < iters; ++i) f();     // 预热
  std::vector<double> t;
  for (int r = 0; r < reps; ++r) {
    auto t0 = std::chrono::steady_clock::now();
    for (long i = 0; i < iters; ++i) f();
    auto t1 = std::chrono::steady_clock::now();
    t.push_back(std::chrono::duration<double, std::nano>(
                    t1 - t0).count() / iters);
  }
  std::nth_element(t.begin(), t.begin() + reps / 2, t.end());
  return t[reps / 2];                        // 中位数
}
```

`escape` 是一条空的内联汇编。它声明自己读取了 `v` 的地址并可能读写任意内存（`"memory"`），优化器看不透它，只好真的把 `v` 算出来。没有它，被测的结果没人用，按 as-if 规则（[[g:as-if-rule]]，[[intro.abstract#1]]）整段计算都可以删掉。每个测量重复 51 轮取中位数，单轮的时间短，被系统调度打断的轮次会落在两端，不影响中位数。

## 查找表的三种建法

一个表驱动的 CRC-32 需要一张 256 项的表。表可以在三个时刻建好：

```cpp
using Table = std::array<std::uint32_t, 256>;

constexpr Table make_table() {
  Table t{};
  for (std::uint32_t i = 0; i < 256; ++i) {
    std::uint32_t c = i;
    for (int k = 0; k < 8; ++k)
      c = (c & 1) ? 0xEDB88320u ^ (c >> 1) : c >> 1;
    t[i] = c;
  }
  return t;
}
Table make_table_rt();    // 同样的函数体，没有 constexpr

constexpr Table kTable = make_table();   // A：编译期
Table gTable = make_table_rt();          // B：启动时
const Table& lazy_table() {              // C：第一次使用时
  static const Table t = make_table_rt();
  return t;
}
```

A 是 `constexpr` 变量，它的初始化器必须是常量表达式，并且是显然常量求值的（[[g:manifestly-constant-evaluated|manifestly constant-evaluated]]，[[expr.const.defns#1]]），编译器只能在翻译期把表算好。B 是**动态初始化**（dynamic initialization）：初始化器不是常量表达式，在 `main` 之前由启动代码执行（[[basic.start.static#2]]）。C 是块作用域的静态变量，第一次执行到这条声明时才初始化，之后每次调用都要先检查它是否已经初始化。

### 表落在哪里

编译后用 `nm -m` 看三个变量所在的段：

```text
$ clang++ -std=c++2c -O2 crc.cpp -o crc && nm -m crc | grep -i table
0000000100007660 (__TEXT,__const) non-external __ZL6kTable
000000010000c080 (__DATA,__common) external _gTable
000000010000c480 (__DATA,__bss) non-external __ZZ10lazy_tablevE1t
000000010000c880 (__DATA,__bss) non-external __ZGVZ10lazy_tablevE1t
```

`kTable` 在 `__TEXT,__const`，也就是只读数据，1024 个字节原样写在可执行文件里，加载时直接映射进内存。`gTable` 和 C 的表在零初始化的可写段里，文件里不占空间，运行时由代码填写。最后一行 `__ZGV…` 是 C 的守卫变量（guard variable），记录表是否已经建好。Linux 上的 ELF 对应的是 `.rodata` 和 `.bss`；用 `--target=x86_64-linux-gnu` 编译后 `llvm-objdump -t` 能看到 `kTable` 在 `.rodata`。

B 的建表代码放在 `__GLOBAL__sub_I_crc.cpp` 函数里，它的地址登记在 `__mod_init_func` 段中，`dyld` 在 `main` 之前逐个调用。C 的每次调用都先执行下面两条指令：

```text
ldaprb  w8, [x8]          ; 读守卫变量（acquire 语义）
tbz     w8, #0, LBB4_2    ; 未初始化则跳去建表
```

### 测出来的差别

| 测量（本机，`-O2`，中位数） | A 编译期 | B 启动时 | C 首次使用 |
|---|---|---|---|
| CRC-32，16 字节 | 12.2 ns | 12.2 ns | 12.7 ns |
| CRC-32，4096 字节 | 9.96 µs | 9.96 µs | 9.97 µs |
| 4096 项正弦表，单次查表 | 0.92 ns | 0.92 ns | 0.92 ns |
| 4096 项正弦表，建表一次（`std::sin`） | 0 | 16.5 µs | 16.5 µs |

查表的速度没有区别。三张表的内容相同，热起来以后都在 L1 缓存里；C 多出的守卫检查是一次几乎总在缓存里的加载和一条总是预测正确的分支，只在 16 字节这种很短的输入上看得出约 0.5 ns。

省下的是建表本身。4096 次 `std::sin` 在本机要 16.5 µs，B 在每次进程启动时付一次，C 在第一次调用时付一次。对长期运行的服务这微不足道；对一天启动几万次的命令行工具、或者有几十张这样的表的程序，它就是启动时间的一部分。

!!! note "优化器替换了 CRC 循环"
    CRC 表本身的建表时间测不出来：Clang 23 在 `-O2` 下认出了逐位计算 CRC 的内层循环，把它换成了查一张编译器自己生成的 256 项表（汇编里的 `l_.crctable`，生成它的是 LoopIdiomRecognize 这一遍优化）。于是 B 的启动代码只剩下一个向量化的查表循环，建表一次不到 0.1 µs。这是 Clang 的实现细节，换一个编译器或版本就不一定发生。正弦表用的是 `std::sin`，优化器无法替换，建表时间才是真实的。

### 只读表的另一个好处

只读数据段里的页面由操作系统按需从可执行文件映射进来，多个进程运行同一个程序时共享同一份物理内存。B 和 C 的表是每个进程自己写出来的私有页面。此外，A 不存在初始化顺序的问题：常量初始化发生在任何动态初始化之前（[[basic.start.static#2]]），别的全局变量的初始化器读 `kTable` 时，它一定已经是最终的值。而 B 这样的动态初始化跨翻译单元时顺序未指定，这就是[[g:static-initialization-order-fiasco|静态初始化顺序问题]]。

代价是文件变大：4096 个 `double` 的 `constexpr` 表让 `__TEXT,__const` 增加了 32 KB，B 的同样大小的表只占零初始化段，不占文件空间。

## 不写 constexpr，优化器也会折叠

`constexpr` 不是编译期计算的前提。下面的函数都没有 `constexpr`：

```cpp ok
int sum_to(int n) {
  int s = 0;
  for (int i = 0; i < n; ++i) s += i * i;
  return s;
}
int use() { return sum_to(100); }

double poly(double x) { return 1 + x * (2 + x * 3); }
double use2() { return poly(0.5); }
```

`-O2` 下 `use` 的汇编是两条拼出常数 328350 的 `mov`，`use2` 是一条 `fmov d0, #2.75`，函数调用和循环都不见了。x86-64 上也一样（`movl $328350, %eax`）。优化器内联了函数，在中间表示上把常量一路传播下去。这是 as-if 规则允许的，详见 [[perf/compiler-optimizations|编译器优化]]。

标准还专门允许实现把动态初始化改成静态初始化，只要结果和副作用都看不出区别（[[basic.start.static#3]]）。不过实际做不做由编译器决定。上一节的 `gTable` 完全可以在编译期算出来，Clang 23 仍然生成了启动代码。优化器的折叠有预算限制，展开、内联、传播到一定规模就会停下来。小表达式可以交给优化器；大的表、需要保证的结果，要自己用语言规则锁定。

## 用 consteval 和 constinit 保证编译期

`constexpr` 函数只表示可以在常量表达式中调用，调用发生在运行期语境时，编译器可以照常生成调用。这一点在[[topics/compile-time-programming|编译期编程]]专题里有完整的讨论。性能上值得注意的是不开优化的调试构建：

```cpp ok
#include <cstdint>
#include <string_view>

constexpr std::uint32_t crc_of(std::string_view s) {
  std::uint32_t c = 0xFFFFFFFFu;
  for (unsigned char ch : s) {
    c ^= ch;
    for (int k = 0; k < 8; ++k)
      c = (c & 1) ? 0xEDB88320u ^ (c >> 1) : c >> 1;
  }
  return ~c;
}
consteval std::uint32_t crc_ce(std::string_view s) {
  return crc_of(s);
}

bool is_len_a(std::uint32_t h) { return h == crc_of("Content-Length"); }
bool is_len_b(std::uint32_t h) { return h == crc_ce("Content-Length"); }
```

`-O2` 下两个函数都是和常数 `0xd87452f2` 比较。`-O0` 下 `is_len_a` 真的构造 `string_view` 并调用 `crc_of`，逐位算完 14 个字符；`is_len_b` 仍然只是一次比较。`consteval` 函数的每次调用都是**立即调用**（immediate invocation），属于显然常量求值，和优化级别无关。

对于有静态存储期的变量，还有一个选择：

```cpp
constexpr Table t1 = make_table();     // 只读，编译期
constinit Table t2 = make_table();     // 可写，编译期
```

`constinit` 要求变量有静态初始化，否则程序非良构（[[dcl.constinit#2]]），但不让变量变成 `const`。本机上 `t2` 落在可写的 `__DATA,__data` 段（ELF 上是 `.data`），文件里同样存着 1 KB 的初值，启动时不运行代码。把 `make_table()` 换成非 `constexpr` 的 `make_table_rt()`，`constexpr` 和 `constinit` 两种写法都会编译失败，不会悄悄退化成启动时建表。

### 非 static 的 constexpr 局部变量

```cpp
void consume(const Table&);   // 另一个翻译单元

void by_ref() {
  constexpr Table t = make_table();
  consume(t);
}
void by_ref_static() {
  static constexpr Table t = make_table();
  consume(t);
}
```

两个函数只差一个 `static`。`by_ref` 的汇编里，每次调用都在栈上开 1024 字节，从只读常量 `memcpy` 一份表，再把栈上的地址传出去。本机上 `by_ref` 每次调用 13.5 ns，`by_ref_static` 0.92 ns。

原因是 `by_ref` 里的 `t` 是自动存储期的对象，每次调用都创建一个新对象。如果 `consume` 递归地调用 `by_ref`，两个 `t` 同时存活，按 [[intro.object#10]] 它们必须有不同的地址，编译器不能让它们都指向同一份只读数据。地址不逃逸时（例如只用 `t[i]` 取值），Clang 能看出没人观察地址，直接读只读常量，不做复制。需要传引用或指针出去的 `constexpr` 局部表，写成 `static constexpr`。

## 把常量带进热点代码：模板实参

编译期能做的不只是算出数据。把运行期的一个小整数变成模板实参，编译器就能针对这个值生成代码。

```cpp
void mul_rt(const float* a, const float* b, float* c, int n) {
  for (int i = 0; i < n; ++i)
    for (int j = 0; j < n; ++j) {
      float s = 0;
      for (int k = 0; k < n; ++k)
        s += a[i * n + k] * b[k * n + j];
      c[i * n + j] = s;
    }
}

template <int N>
void mul_ct(const float* a, const float* b, float* c) {
  /* 同样的三重循环，n 换成 N */
}

void mul_dispatch(const float* a, const float* b, float* c, int n) {
  switch (n) {
    case 2: return mul_ct<2>(a, b, c);
    case 3: return mul_ct<3>(a, b, c);
    case 4: return mul_ct<4>(a, b, c);
    case 8: return mul_ct<8>(a, b, c);
    default: return mul_rt(a, b, c, n);
  }
}
```

`n` 在运行期才知道（测试里由 `argc` 推出），`mul_dispatch` 用一个 `switch` 把常见的尺寸分派给专门的实例，其余的走通用版本。

| `n`（本机，`-O2`） | `mul_rt` | `mul_dispatch` | 比值 |
|---|---|---|---|
| 3 | 15.0 ns | 5.0 ns | 3.0 |
| 4 | 30.7 ns | 10.4 ns | 2.9 |
| 8 | 201 ns | 83.3 ns | 2.4 |

汇编说明了差别。`mul_rt` 最内层是一个三条有用指令（两次加载、一次 `fmadd`）加三条循环控制指令的循环，每个点积串成一条 `fmadd` 依赖链。`mul_ct<4>` 里 `j` 和 `k` 两层循环被完全展开，所有地址都是寄存器加立即数偏移，四个点积的 `fmadd` 链在直线代码里彼此独立，乱序执行可以同时推进。`mul_ct<8>` 也是如此，内部是 64 条展开的 `fmadd`。

`switch` 本身的代价是一次比较和跳转。只有当 `n` 的分布集中在少数几个值上时，这种分派才划算；每个 `case` 都会实例化一份代码，见后面的体积一节。

### if constexpr 删掉循环里的判断

```cpp ok
#include <cstddef>

void scale_rt(float* p, std::size_t n, float k, bool clamp) {
  for (std::size_t i = 0; i < n; ++i) {
    float v = p[i] * k;
    if (clamp) v = v > 1.0f ? 1.0f : v;
    p[i] = v;
  }
}
template <bool Clamp>
void scale_ct(float* p, std::size_t n, float k) {
  for (std::size_t i = 0; i < n; ++i) {
    float v = p[i] * k;
    if constexpr (Clamp) v = v > 1.0f ? 1.0f : v;
    p[i] = v;
  }
}
```

`if constexpr` 的条件是常量，没有选中的分支是**弃置语句**（discarded statement，[[stmt.if#2]]），在模板实例化时不会被实例化。`scale_ct<false>` 里根本没有比较。

`scale_rt` 里的 `clamp` 在循环中不变，编译器本可以把循环拆成两份（称为 loop unswitching）。本机 Clang 23 在 `-O2` 下没有这样做，而是把判断转成按位选择，留在向量化后的循环体里，每轮还要重新计算一次掩码。处理 4096 个 `float`：

| 本机，`-O2` | `scale_rt` | `scale_ct` |
|---|---|---|
| 不截断 | 487 ns | 197 ns |
| 截断 | 487 ns | 264 ns |

这类收益取决于编译器愿不愿意自己拆循环，换一个编译器或优化级别结论可能不同。确认的办法总是看汇编。

## 固定大小：std::array 与 std::vector

大小在编译期已知时，`std::array<float, 16>` 是一个 64 字节的对象，直接放在栈上；`std::vector<float>(16)` 是 24 字节的三个指针，元素在堆上。

```cpp
float sum(const float* p, int n);   // 不内联

float with_vector(const float* in) {
  std::vector<float> t(16);
  for (int i = 0; i < 16; ++i) t[i] = in[i] * in[i];
  return sum(t.data(), 16);
}
float with_array(const float* in) {
  std::array<float, 16> t;
  for (int i = 0; i < 16; ++i) t[i] = in[i] * in[i];
  return sum(t.data(), 16);
}
```

本机上 `with_vector` 每次调用 26.7 ns，`with_array` 3.37 ns，差别几乎都是 `operator new` 和 `operator delete`（汇编里的 `bl __Znwm`、`bl __ZdlPvm`）。

但如果把 `sum` 换成在函数内直接求和，缓冲区的地址不再逃逸，两个版本都是 2.33 ns：Clang 删掉了这次堆分配。标准允许实现省略对可替换全局分配函数的调用（[[expr.new#14]]），只是什么时候省略由编译器决定，不能依赖。分配的代价见 [[perf/allocation|内存分配]]，容器的选择见 [[perf/choosing-containers|选择容器]]。

## 代价一：编译时间

编译期计算的开销从运行期挪到了每一次编译。Clang 的常量求值器是一个解释器，比编译后的机器码慢得多。把正弦表的项数调大：

```cpp
// sintab.h：泰勒级数求 sin，每项 19 次迭代
constexpr double csin(double x);
template <std::size_t N>
constexpr std::array<double, N> make_sin_table();

// big.cpp
constexpr auto kSin = make_sin_table<TABN>();
```

N 到 16384 时，默认设置下编译失败：

```text
error: constexpr variable 'kSin' must be initialized by a constant expression
note: constexpr evaluation hit maximum step limit; possible infinite loop?
```

常量求值超出实现的限制时，表达式就不是核心常量表达式（[[expr.const.core#2.7]]），`constexpr` 变量的初始化因此非良构。标准的附录 [[implimits]] 只给出建议的最小值，比如一个核心常量表达式中求值 1 048 576 个完整表达式；这个附录不具规范效力，实际限制由实现决定。本机上 Clang 23 的默认限制和显式写 `-fconstexpr-steps=1048576` 的行为完全相同，一个简单的累加循环大约每次迭代计一步。调大限制用 `-fconstexpr-steps=<n>`（Clang）；GCC 对应的选项是 `-fconstexpr-ops-limit` 和 `-fconstexpr-loop-limit`。

放开限制后的编译时间（user CPU 秒，5 次取最小，只含 `<array>` 的空文件为 0.06 秒）：

| 表的项数 | 常量求值器 | 实验性字节码求值器 | 写成字面量 |
|---|---|---|---|
| 1024 | 0.09 | 0.08 | |
| 4096 | 0.19 | 0.15 | |
| 16384 | 0.65 | 0.47 | |
| 65536 | 2.54 | 1.69 | 0.09 |

最后一列是用 Python 预先算好 65536 个 `double`、以 `#include` 进一个初始化列表的版本，编译只要 0.09 秒，生成的目标文件与 `constexpr` 版本一样大（都是 512 KB 的数据）。中间一列是 Clang 的 `-fexperimental-new-constant-interpreter`，它产生的目标文件与默认求值器逐字节相同，但这个选项仍是实验性的。

要知道时间花在哪里，用 `-ftime-trace`。它在输出文件旁边写一个 Chrome 跟踪格式的 JSON 文件，可以拖进 `chrome://tracing` 或 Perfetto 查看，也可以直接读里面以 `Total` 开头的汇总事件。N = 16384 时本机的汇总：

```text
1190.5 ms  Total ExecuteCompiler
1183.6 ms  Total Frontend
1121.2 ms  Total EvaluateAsInitializer      ← kSin 的初始化器
   3.9 ms  Total Backend
```

几乎全部时间都在前端求值 `kSin` 的初始化器，优化和生成代码只用了几毫秒。

这笔开销在每个包含这段代码的翻译单元里都要付。表的定义放在头文件里、被几十个 `.cpp` 包含时，最好把表移到一个 `.cpp` 里，头文件只声明。超过几千项、计算又不简单的表，用构建脚本生成字面量通常更合算。

## 代价二：代码体积

每个模板实参都会生成一份独立的函数。用 `std::integer_sequence` 一次实例化 `mul_ct<1>` 到 `mul_ct<MAXN>`，放进一张函数指针表：

```cpp
using Fn = void (*)(const float*, const float*, float*);
template <int... I>
constexpr std::array<Fn, sizeof...(I)>
make_dispatch(std::integer_sequence<int, I...>) {
  return {&mul_ct<I + 1>...};
}
constexpr auto kDispatch =
    make_dispatch(std::make_integer_sequence<int, MAXN>{});
```

用 `size -m` 读目标文件的 `__text` 段：

| `MAXN` | `__text`（字节） | 编译（user 秒） |
|---|---|---|
| 1 | 260 | 0.07 |
| 8 | 2 940 | 0.09 |
| 16 | 5 136 | 0.12 |
| 32 | 10 756 | 0.15 |
| 64 | 13 828 | 0.19 |

小尺寸的实例被完全展开，单个就有几百字节；尺寸大了编译器不再完全展开，每个实例的增长变慢。体积本身不直接等于变慢，但如果热路径轮流调用很多个实例，它们会互相挤占指令缓存。只为真正常见的值生成实例，其余的交给通用版本。

## 大块数据：#embed {{c++26}}

把一个二进制文件变成数组，传统做法是用 `xxd -i` 之类的工具生成一个巨大的初始化列表。C++26 的 `#embed`（[[P1967R14]]）让预处理器直接读文件：

<div class="compare" markdown="1">

```cpp
constexpr unsigned char kBlob[] = {
#include "blob.inc"   // 0x3a, 0x91, …
};
```

```cpp
constexpr unsigned char kBlob[] = {
#embed "blob.bin"
};
```

</div>

按标准，`#embed` 被替换为一串以逗号分隔的 `int` 类型整数字面量（[[cpp.embed#11]]），语义上和左边一样。区别在实现：编译器不必真的生成并解析几百万个记号。1 MiB 的随机数据，本机上左边的文本文件有 6 MB，编译用 0.51 秒 user 时间、最大内存 250 MB；右边 0.04 秒、124 MB。两个目标文件大小相同。

Clang 23 在 `-std=c++2c` 下接受 `#embed`，但加上 `-pedantic` 会警告 `#embed is a Clang extension`，也没有定义特性测试宏 `__cpp_pp_embed`（当前草案规定它为 `202606L`）。也就是说，截至写作时 Clang 23 把它当作扩展提供，还没有作为 C++26 特性完整实现。

## 怎样选

| 情况 | 做法 |
|---|---|
| 表小、算法简单 | `constexpr` 变量（命名空间作用域，或 `static constexpr` 局部变量） |
| 需要在编译期算好但之后要修改 | `constinit` |
| 某个函数绝不能在运行期执行 | `consteval` |
| 表很大或计算很重 | 构建时生成字面量，或用 `#embed` 嵌入数据文件 |
| 依赖只能在运行期得到的信息（CPU 特性、配置） | 启动时建表，或首次使用时建表 |
| 热点函数的某个参数只取少数几个值 | 模板实参 + `switch` 分派，保留通用版本 |
| 循环里有不变的布尔开关 | 模板参数 + `if constexpr`，先看汇编确认编译器没有自己拆循环 |

## 常见陷阱

!!! pitfall "以为 constexpr 函数一定在编译期执行"
    `int x = f(42);` 里的 `f` 即使是 `constexpr`，这次调用也可以在运行期执行，尤其是在 `-O0` 的调试构建里。要保证在编译期，用 `constexpr` 或 `constinit` 变量接住结果，或者把函数声明为 `consteval`。

!!! pitfall "以为编译期的表查起来更快"
    表一旦在缓存里，读哪一份都一样快。编译期建表省下的是建表那一次的时间、首次使用的检查和初始化顺序问题，不是每次查表的时间。

!!! pitfall "局部的 constexpr 大数组"
    非 `static` 的 `constexpr` 局部数组，一旦地址被传出去，每次调用都要在栈上复制一份。加上 `static`。

!!! pitfall "constexpr 表放在被到处包含的头文件里"
    每个翻译单元都要重新求值一遍。一个 `.cpp` 里的 0.6 秒，乘上几十个翻译单元就是构建时间的一大块。

## 思考题

!!! question "1. 只读还是可写"
    `constinit const Table t = make_table();` 和 `constexpr Table t = make_table();` 有什么区别？在命名空间作用域里，哪一个能用在常量表达式里？

<details markdown="1">
<summary>答案</summary>

两者都要求常量初始化，变量都是 `const` 的，都会放进只读数据。区别在于能否用在常量表达式里：`constexpr` 变量总是可在常量表达式中使用的；`constinit const` 的变量是 `const` 的类类型对象而非整型或枚举类型，不是 `constexpr`，所以不能用在常量表达式里，例如 `static_assert(t[0] == 0)` 会被拒绝。运行期的性能没有区别。见 [[dcl.constinit]] 和 [[expr.const.init]]。
</details>

!!! question "2. 启动时建表被优化掉了吗"
    `Table gTable = make_table_rt();` 是动态初始化。编译器有没有可能完全不生成启动代码，直接把表写进数据段？标准允许吗？

<details markdown="1">
<summary>答案</summary>

允许。[[basic.start.static#3]] 允许实现把动态初始化当作静态初始化来做，只要这样做不改变其他静态变量在初始化前看到的值，并且得到的值与动态初始化相同。本机 Clang 23 在 `-O2` 下没有这样做，仍然生成了 `__GLOBAL__sub_I_crc.cpp`。所以这只是允许，不是保证；需要保证就用 `constexpr` 或 `constinit`。
</details>

!!! question "3. 为什么不把所有尺寸都实例化"
    `mul_dispatch` 只为 2、3、4、8 生成专门的版本。既然 `mul_ct<N>` 快近 3 倍，为什么不为 1 到 64 全部实例化？

<details markdown="1">
<summary>答案</summary>

每个实例都是一份独立的代码。本机上实例化 1 到 64 让代码段从 260 字节涨到约 13.8 KB，编译时间也增加。更重要的是，如果运行时的尺寸分布很散，很多实例都会被轮流调用，它们会互相挤出指令缓存，分派也可能从一次比较变成查表加间接调用。只为测量中真正频繁出现的尺寸生成实例。
</details>

<details class="fine" markdown="1"><summary>测量命令</summary>

运行期测量：`clang++ -std=c++2c -O2 -Wall -Wextra -pedantic x.cpp -o x && ./x`，每个程序运行 5 次，取最好的一次的中位数。编译时间：`/usr/bin/time -p clang++ -std=c++2c -O2 -c x.cpp -o /dev/null` 的 `user` 一栏，5 次取最小。段和符号：`nm -m`、`size -m`（macOS），`llvm-objdump -t`（ELF）。汇编：`clang++ -std=c++2c -O2 -S`，x86-64 加 `--target=x86_64-linux-gnu`。常量求值的跟踪：`-ftime-trace`。

`std::sin` 在当前草案里已经是 `constexpr` 函数（C++26，[[P1383R2]]），但本机的 libc++ 还没有实现，所以正弦表用了自己写的泰勒级数 `csin`；它与 `std::sin` 在 4096 个采样点上的最大差为 7×10⁻¹⁶。
</details>
