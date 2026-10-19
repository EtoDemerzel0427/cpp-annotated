---
title: 怎样测量才可信
summary: 写一个结果可信的微基准：为什么朴素的计时循环会测出 0 纳秒，选哪个时钟，DoNotOptimize 和 ClobberMemory 的内联汇编怎样挡住优化器，预热、重复和中位数，macOS 上的噪声来源，常见陷阱，怎样公平地比较两个版本，以及本节其余各页共用的小框架 bench.hpp。
status: draft
order: 10
group: 测量
since: c++11
related: intro.abstract, time.clock, dcl.asm, dcl.type.cv, topics/undefined-behavior, toolchain/compilation-pipeline, perf/profiling, perf/reading-assembly, perf/memory-hierarchy, perf/branches
tags: 性能, 基准测试, 测量, as-if, 内联汇编, 统计
updated: 2026-10-19
---

!!! tldr
    - 编译器只需保留程序的可观察行为（[[intro.abstract]]）。结果没人用的计算会被删除，常量输入会被提前算好，不变的表达式会被提出循环。测出的数字小得离谱时，先看汇编。
    - 计时用 `steady_clock`。本机它的实际步长是 41 ns，一次 `now()` 要十几纳秒，所以一个样本要连续调用被测代码很多次，持续到毫秒级。
    - `do_not_optimize` 和 `clobber_memory` 是不生成任何指令的内联汇编，靠操作数约束让编译器相信某个值被读取、被改写，内存被读写。它们只约束编译器，不影响 CPU。
    - 先预热再记录，多次重复后看中位数和分布。均值会被少数被抢占、被调度到能效核上的样本拉高。
    - 比较两个版本时，把它们放在同一个程序里交替测量，并先做一次 A/A 测试量出噪声有多大；差异小于噪声就不能下结论。

本节所有数字都来自同一台机器：Apple M2 Pro（8 个性能核、4 个能效核），macOS，Homebrew Clang 23.1.3 + libc++，arm64，除非特别说明都用 `clang++ -std=c++2c -O2` 编译。它们是本机的观察结果，换一台机器、换一个编译器版本，数字都会变，方法不变。写作期间这台机器上还有许多其他进程在跑（12 个核心上 load average 在 30 到 100 之间）。绝对数字因此偏慢、偏散，可信的是同一进程里背靠背测得的比值和汇编；表里的小差异不要过度解读。这样的环境也正好让噪声更容易看见。

## 0 纳秒的基准

```cpp title="naive.cpp" run ok
#include <chrono>
#include <cstdio>

long sum_to(long n) {
  long s = 0;
  for (long i = 0; i < n; ++i) s += i * i;
  return s;
}

int main() {
  auto t0 = std::chrono::steady_clock::now();
  for (int r = 0; r < 1000; ++r)
    sum_to(1'000'000);                  // 结果被丢弃
  auto t1 = std::chrono::steady_clock::now();
  auto ns = std::chrono::duration_cast<std::chrono::nanoseconds>(t1 - t0);
  std::printf("%lld ns per call\n", (long long)(ns.count() / 1000));
}
```

本机 `-O0` 输出 `928503 ns per call`，`-O2` 输出 `0 ns per call`。`-O2` 下 `main` 的汇编里，两次 `now()` 紧挨着：

```text
bl   __ZNSt3__16chrono12steady_clock3nowEv
mov  x19, x0
bl   __ZNSt3__16chrono12steady_clock3nowEv
sub  x8, x0, x19          ; t1 - t0，中间什么也没有
```

1000 次调用全部消失了。这是允许的。标准只要求实现模拟抽象机的**可观察行为**（observable behavior，[[intro.abstract#1]]）：volatile 访问、写进文件的数据、交互设备上的输入输出顺序（[[intro.abstract#8]]）。执行时间不在其中。`sum_to` 没有副作用，返回值又被丢弃，删掉它从可观察行为上看不出区别。这条原则叫 [[g:as-if-rule|as-if 规则]]，详细的论述见 [[intro.abstract]]。

删除还不是全部。即使把结果用上，`sum_to` 本身也已经没有循环了：

```text
__Z6sum_tol:
  subs  x8, x0, #1
  b.lt  LBB0_2
  sub   x9, x0, #2
  umulh x10, x8, x9
  mul   x8, x8, x9
  ...                     ; 十几条乘法和移位，没有回跳
  ret
```

Clang 认出了平方和的归纳模式，把循环换成了闭式公式 (n−1)·n·(2n−1)/6。后面用框架把删除挡住以后，本机测得 `sum_to(1'000'000)` 每次 1.53 ns。一百万次迭代不可能在 1.5 ns 里做完，这个数字测的是公式，不是循环。

所以第一条习惯是做一次量级检查：把测得的时间折算成每次迭代、每个元素或每个时钟周期，和硬件的能力比一比。量级不对，就去看汇编（见 [[perf/reading-assembly|读汇编]]）。

## 选哪个时钟

`<chrono>` 有三个可以用来计时的时钟（[[time.clock]]）：

- `system_clock` 表示墙上时间，可以被管理员或 NTP 调整，可能往回跳（[[time.clock.system#1]]）；
- `steady_clock` 的时刻永不减少，并以稳定的速率前进，不能被调整（[[time.clock.steady#1]]）；
- `high_resolution_clock` 是计次周期最短的时钟，可以只是前两者之一的别名（[[time.clock.hires#1]]）。

!!! std
    Objects of class `steady_clock` represent clocks for which values of `time_point` never decrease as physical time advances ... That is, the clock may not be adjusted.

`period` 只说明计数的单位，不说明时钟实际多久跳一次。下面的程序测量相邻两次 `now()` 之间最小的非零差值（实际步长），以及一次 `now()` 本身的开销：

```cpp title="clocks.cpp" run ok
#include <chrono>
#include <cstdio>
using namespace std::chrono;

template <class C>
void probe(const char* name) {
  long long step = -1;                  // 最小的非零差值
  for (int i = 0; i < 1'000'000; ++i) {
    auto a = C::now(), b = C::now();
    while (b == a) b = C::now();
    long long d = duration_cast<nanoseconds>(b - a).count();
    if (step < 0 || d < step) step = d;
  }
  constexpr int N = 10'000'000;         // 一次 now() 的平均开销
  auto t0 = steady_clock::now();
  typename C::rep acc = 0;
  for (int i = 0; i < N; ++i) acc += C::now().time_since_epoch().count();
  double cost = duration<double, std::nano>(steady_clock::now() - t0).count() / N;
  std::printf("%-22s period %lld/%lld  steady %d  step %lld ns  now() %.1f ns  [%d]\n",
              name, (long long)C::period::num, (long long)C::period::den,
              C::is_steady, step, cost, int(acc & 1));
}

int main() {
  probe<steady_clock>("steady_clock");
  probe<system_clock>("system_clock");
  probe<high_resolution_clock>("high_resolution_clock");
}
```

本机三次运行，步长每次相同；`now()` 的开销在机器较空闲时约 16 ns，负载很重时测得更高：

| 时钟 | `period` | `is_steady` | 实测步长 | 一次 `now()` |
|---|---|---|---|---|
| `steady_clock` | 1/10⁹ s | 1 | 41 ns | 16–22 ns |
| `system_clock` | 1/10⁶ s | 0 | 1000 ns | 17–43 ns |
| `high_resolution_clock` | 1/10⁹ s | 1 | 41 ns | 16–39 ns |

libc++ 里 `high_resolution_clock` 就是 `steady_clock` 的别名（`std::is_same_v` 为真）。`steady_clock` 虽然以纳秒计数，实际 41 ns 才跳一次，这与 `sysctl hw.tbfrequency` 报告的 24 MHz 系统计数器一致（1/24 MHz ≈ 41.7 ns）。

结论有三条。测量耗时用 `steady_clock`，它不会因为校时而跳变；`high_resolution_clock` 在别的实现上可能是 `system_clock`，没有可移植的用处。单次调用短于几百纳秒的代码不能单独计时，因为步长和 `now()` 自身的开销都在几十纳秒。要让一个样本连续调用被测代码 n 次再除以 n，并让一个样本持续 1 ms 左右，这时 41 ns 的步长只占 0.004%。

## 挡住优化器

要让被测代码不被删除、不被折叠、不被提出循环，同时又不给它增加额外的开销，常用的办法是 Google Benchmark 的 `DoNotOptimize` 和 `ClobberMemory`。它们的核心各只有一行内联汇编：

```cpp
template <class T>
inline void do_not_optimize(T& v) {
  asm volatile("" : "+r"(v) : : "memory");
}
inline void clobber_memory() {
  asm volatile("" : : : "memory");
}
```

这是 GCC 的扩展内联汇编语法，Clang 也支持。C++ 标准只规定 `asm` 声明是有条件支持的，内容的含义由实现定义（[[dcl.asm#1]]），所以这两个函数不可移植，MSVC 的 x64 编译器就不接受内联汇编。逐项看：

| 写法 | 含义 | 对优化器的效果 |
|---|---|---|
| `""` | 汇编模板为空 | 不生成任何指令，没有运行期开销 |
| `volatile` | 这条 asm 有编译器看不到的副作用 | 不能因为输出没人用而删掉它，也不能把它提出循环 |
| `"+r"(v)` | 输出兼输入操作数，放在寄存器里 | asm 之前，`v` 的值必须真的算出来；asm 之后，`v` 被视为一个未知的新值 |
| `"+m"(v)` | 同上，但操作数在内存里 | 用于放不进寄存器的对象，比如数组、结构体 |
| `"memory"` | 破坏列表：asm 可能读写任意内存 | asm 之前，挂起的写入必须真的写进内存；之后，内存中的值要重新读 |

框架里的版本按类型选择 `"+r"` 或 `"+m"`，另有一个接受 `const T&` 的重载，只用输入操作数 `"m"`，用来接住临时值，完整代码见[文末](#harness)。

### 它挡住了什么

```cpp title="dno.cpp"
#include "bench.hpp"

int square(int x) { return x * x; }

void discard(int x) { int r = square(x); (void)r; }
void keep(int x) { int r = square(x); bench::do_not_optimize(r); }
void keep_const() { int r = square(12); bench::do_not_optimize(r); }
```

本机 `-O2` 的汇编：

```text
__Z7discardi:            ; 结果没人用：什么都不剩
  ret
__Z4keepi:               ; 乘法留下了，asm 本身是空的
  mul  w8, w0, w0
  ; InlineAsm Start
  ; InlineAsm End
  ret
__Z10keep_constv:        ; 输入是常量：编译期已经算好
  mov  w8, #144
  ret
```

`do_not_optimize` 只保证结果被算出来，不保证它是在运行期算出来的。`keep_const` 留下的只是常量 144。要测 `square` 本身，还得让输入对编译器不透明，也就是在调用前对输入也调用一次 `do_not_optimize`。

### 不变的计算会被提出循环

框架把被测代码放在一个循环里重复 n 次。如果每次迭代的输入都一样，计算就会被提出循环：

<div class="compare" markdown="1">

```cpp
void hoisted(long a, long b, long n) {
  for (long i = 0; i < n; ++i) {
    long r = a / b;
    bench::do_not_optimize(r);
  }
}
```

```cpp
void opaque(long a, long b, long n) {
  for (long i = 0; i < n; ++i) {
    bench::do_not_optimize(a);
    bench::do_not_optimize(b);
    long r = a / b;
    bench::do_not_optimize(r);
  }
}
```

</div>

<div class="compare" markdown="1">

```text
  sdiv  x8, x0, x1     ; 循环外
LBB0_2:
  mov   x9, x8
  ; InlineAsm Start
  subs  x2, x2, #1
  b.ne  LBB0_2
```

```text
LBB1_1:
  ; InlineAsm Start
  ; InlineAsm Start
  sdiv  x8, x0, x1     ; 循环内
  ; InlineAsm Start
  subs  x2, x2, #1
  b.ne  LBB1_1
```

</div>

左边的除法只做一次，循环里只剩空的 asm 和计数。用框架测量，左边每次 0.31 ns，右边 0.61 ns。0.31 ns 大约是一个时钟周期，正是这个空循环本身的开销。

右边测到的也只是除法的吞吐量：各次迭代的除法互不依赖，可以重叠执行。如果要测延迟，需要让下一次的输入依赖上一次的结果（例如 `a = a / b + c`），本机这样测得每次约 2.8 ns。微基准测的是吞吐量还是延迟，取决于这种依赖关系，写之前要想清楚自己要哪一个。

### 没人读的写入会被删除

```cpp
bench::run("fill", [] {
  int buf[1024];
  std::fill(buf, buf + 1024, 7);
});
bench::run("fill, kept", [] {
  int buf[1024];
  std::fill(buf, buf + 1024, 7);
  bench::do_not_optimize(buf);       // "+m" 加 "memory"
});
```

本机前者 0.00 ns，后者 41.8 ns。`buf` 写完就销毁，没有人读，这些写入是死存储，可以整个删掉。`do_not_optimize(buf)` 声明 asm 会读这块内存，写入就必须先完成。只想说任何内存都可能被读到而不涉及具体变量时，用 `clobber_memory()`，例如被测代码写的是一个外部缓冲区。

### 其他办法

把结果写进一个 volatile 变量也能防止删除，而且不需要内联汇编：

```cpp
volatile int sink;
bench::run("volatile sink", [&] {
  sink = std::accumulate(v.begin(), v.end(), 0);
});
```

通过 volatile glvalue 的访问是可观察行为，必须严格按抽象机执行（[[intro.execution#7]]、[[intro.abstract#8]]），所以每次的结果都得算出来写进去。本机对 4096 个 `int` 求和，这样测得约 143 ns，用 `do_not_optimize` 约 145 ns，两者相当。它的局限是只能保护输出：输入是常量时照样会被折叠，而且每次多一次真实的存储。

!!! pitfall "noinline 不是屏障"
    把被测函数标成 `[[gnu::noinline]]` 只能阻止内联，不能阻止删除。本机 Clang 对 `[[gnu::noinline]] long sum_to(long)`，`void caller() { sum_to(1'000'000); }` 生成的仍然只有一条 `ret`：编译器分析出 `sum_to` 没有副作用，删掉了调用。跨过函数边界的常量传播也照样会发生。

!!! note "计时调用本身能挡住重排吗"
    `steady_clock::now()` 对编译器是一个不透明的外部调用。纯寄存器上的计算不访问内存，按 as-if 规则可以被移到两次 `now()` 之外。本机用 Clang 测试一个两次 `now()` 之间的整数循环，它没有这样做，但这不是保证。框架在计时区间之内对结果调用带 `"memory"` 的 `do_not_optimize`，asm 和 `now()` 都可能访问内存，编译器不能交换它们的顺序。

## 预热：第一次总是慢的

同一段代码，第一次执行和之后的执行，面对的机器状态不同：

- **缺页**：新分配的内存在第一次写入时才由操作系统映射物理页，每一页触发一次缺页异常。本机的页大小是 16 KiB；
- **缓存**：数据和指令第一次要从更慢的层级取来；
- **分支预测器**：要先见过几次分支，才能预测得准；
- **CPU 频率与调度**：核心可能处于低频，线程也可能先落在能效核上。

```cpp title="first.cpp"
#include "bench.hpp"
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <memory>
#include <numeric>
#include <sys/resource.h>
#include <vector>
using clk = std::chrono::steady_clock;

long page_faults() {
  rusage r;
  getrusage(RUSAGE_SELF, &r);
  return r.ru_minflt + r.ru_majflt;
}
double us_since(clk::time_point t0) {
  return std::chrono::duration<double, std::micro>(clk::now() - t0).count();
}

int main() {
  bench::prefer_performance_cores();
  constexpr std::size_t n = 8 << 20;             // 8M 个 int = 32 MiB
  std::unique_ptr<int[]> p(new int[n]);          // 未初始化：页还没映射
  for (int pass = 1; pass <= 3; ++pass) {
    long f0 = page_faults();
    auto t0 = clk::now();
    std::fill(p.get(), p.get() + n, pass);
    double us = us_since(t0);
    bench::do_not_optimize(p[n / 2]);
    std::printf("fill pass %d: %7.0f us, %ld page faults\n",
                pass, us, page_faults() - f0);
  }
  std::vector<int> v(1 << 18, 1);                // 1 MiB，已经写过一遍
  for (int call = 1; call <= 5; ++call) {
    auto t0 = clk::now();
    int s = std::accumulate(v.begin(), v.end(), 0);
    bench::do_not_optimize(s);
    std::printf("sum call %d: %5.1f us\n", call, us_since(t0));
  }
}
```

本机三次运行的范围：

| | 第 1 次 | 第 2 次 | 第 3 次及以后 |
|---|---|---|---|
| 填充 32 MiB | 2.7–3.0 ms，2048 次缺页 | 0.95–1.25 ms，0 次缺页 | 0.55–0.59 ms |
| 对 1 MiB 求和 | 18.5–20.6 µs | 12.3–12.6 µs | 12.2 µs |

2048 次缺页正好是 32 MiB ÷ 16 KiB。第一遍填充比稳定状态慢五倍左右，其中大部分是缺页。第二遍已经没有缺页，却仍比第三遍慢一倍左右，本机没有查清原因；缓冲区换成 64 MiB 时，第二遍有时比第一遍还慢。不管原因是什么，只测一次就会把这些一次性开销算进去。

框架的做法是先调用几轮、丢弃结果，再开始记录。要注意预热也会掩盖真实情况：如果实际程序里这段代码只执行一次，或者每次面对的都是冷数据，测稳定状态就回答错了问题。要测的是哪一种，取决于你想回答的问题。

## 重复与统计

预热之后，同一段代码的耗时仍然不是一个固定的数。下面对 4096 个 `int` 求和，每个样本连续调用 64 次（约 10 µs），记录 3000 个样本：

```cpp title="dist.cpp"
#include "bench.hpp"
#include <algorithm>
#include <cstdio>
#include <limits>
#include <numeric>
#include <vector>

int main() {
  bench::prefer_performance_cores();
  std::vector<int> v(4096, 1);
  auto f = [&] {
    int s = std::accumulate(v.begin(), v.end(), 0);
    bench::do_not_optimize(s);
  };
  std::vector<double> t;
  for (int i = 0; i < 3000; ++i) t.push_back(bench::sample(f, 64));
  double mean = std::accumulate(t.begin(), t.end(), 0.0) / t.size();
  std::sort(t.begin(), t.end());
  auto q = [&](double p) { return t[std::size_t(p * (t.size() - 1))]; };
  std::printf("min %.1f  median %.1f  p90 %.1f  p99 %.1f  max %.1f  mean %.1f\n",
              q(0), q(.5), q(.9), q(.99), q(1), mean);
  double inf = std::numeric_limits<double>::infinity();
  double edges[] = {0, 150, 160, 200, 290, 330, 1000, inf};
  for (int b = 0; b + 1 < 8; ++b)
    std::printf("[%4.0f, %4.0f)  %ld\n", edges[b], edges[b + 1],
                std::count_if(t.begin(), t.end(), [&](double x) {
                  return x >= edges[b] && x < edges[b + 1]; }));
}
```

本机一次运行的结果（单位 ns/次）：

| 区间 | 样本数 |
|---|---|
| [0, 150) | 2558 |
| [150, 160) | 200 |
| [160, 200) | 4 |
| [200, 290) | 0 |
| [290, 330) | 208 |
| [330, 1000) | 24 |
| [1000, ∞) | 6 |

min 143.9，中位数 145.8，p90 153.0，p99 315.8，max 6033.2，**均值 164.1**。另外两次运行，中位数分别是 145.2 和 145.2，均值是 165.7 和 164.9，落在 [290, 330) 的样本分别有 360 和 349 个。

分布不是一个钟形，而是一个窄峰加一条长尾，尾巴里还有第二个峰。第二个峰在 300 ns 附近，差不多正好是主峰的两倍，下一节会看到这是线程被放到了能效核上。最大的样本是主峰的 40 倍，这样的样本通常是线程在样本中途被抢占。

在这样的分布上，均值没有代表性：它比九成以上的样本都大，而且取决于这次运行恰好遇到了多少次干扰。几个统计量各有用处：

| 统计量 | 回答的问题 | 弱点 |
|---|---|---|
| 中位数 | 典型的一次有多快 | 对尾部不敏感 |
| 最小值 | 没有任何干扰时能多快 | 只反映最好情况，可能是偶然 |
| p90、p99、最大值 | 尾部有多重 | 需要很多样本才稳定 |
| 均值 | 总耗时 ÷ 次数 | 被少数离群值拉偏 |

框架报告中位数，同时给出最小值和最大值作为离散程度的提示。比较两个版本时看中位数；最小值和中位数差得很远、最大值比中位数大几倍时，说明这次测量受到了严重干扰，应该重跑，而不是相信任何一个数。实际程序关心延迟尾部时（例如每帧、每个请求的耗时），要专门测尾部，不能只看中位数。

## macOS 上的噪声来源

### 性能核与能效核

M2 Pro 有 8 个性能核和 4 个能效核（`sysctl hw.perflevel0.logicalcpu hw.perflevel1.logicalcpu` 输出 8 和 4）。同一段代码在两种核心上的速度可以差一倍以上。Linux 上可以用 `taskset` 把进程绑到指定的核心，macOS 没有提供这种接口，只能通过服务质量等级（QoS）影响调度器的选择：

```cpp title="qos.cpp"
#include "bench.hpp"
#include <cstring>
#include <numeric>
#include <pthread.h>
#include <vector>

int main(int argc, char** argv) {
  bool bg = argc > 1 && std::strcmp(argv[1], "background") == 0;
  pthread_set_qos_class_self_np(
      bg ? QOS_CLASS_BACKGROUND : QOS_CLASS_USER_INTERACTIVE, 0);
  std::vector<int> v(4096, 1);
  bench::run(bg ? "background" : "user-interactive", [&] {
    int s = std::accumulate(v.begin(), v.end(), 0);
    bench::do_not_optimize(s);
  });
}
```

本机交替运行三次：`user-interactive` 的中位数是 146.0–146.6 ns；`background` 的中位数是 579–751 ns，最小值 302–322 ns。按 Apple 的说明，在 Apple 芯片上 `QOS_CLASS_BACKGROUND` 的线程只被调度到能效核。本机测得的最小值约为性能核的两倍，与此一致，也正对应上一节分布里的第二个峰；中位数更高，是因为机器繁忙时能效核也被其他进程占着。

框架的 `prefer_performance_cores()` 把线程设为 `QOS_CLASS_USER_INTERACTIVE`。它只是提示，不是绑定：上一节的分布就是在这个设置下测的，系统繁忙时三次运行里仍有 7%–12% 的样本落在 300 ns 附近。

### 其他干扰

- **后台负载**：其他进程会抢占 CPU、共享缓存和内存带宽。测量时关掉不必要的程序，并在报告里注明负载（`uptime`）。本页的数字是在 load average 30 以上测的，中位数仍然稳定，尾部明显变重。
- **温度**：长时间满载可能触发降频，表现为样本随时间缓慢变慢。本机没有单独测量这一点；检查办法是按时间顺序画出样本，看有没有趋势。
- **电源**：笔记本使用电池、开启低电量模式时，频率上限可能不同。

## 微基准的常见陷阱

前面已经看到其中几种，这里归在一起：

| 陷阱 | 表现 | 本机数据 | 对策 |
|---|---|---|---|
| 结果没人用 | 整段代码被删除 | 0 ns 的基准 | `do_not_optimize(结果)` |
| 常量输入 | 编译期就算完了 | `keep_const` 只剩 `mov w8, #144` | `do_not_optimize(输入)` |
| 不变的计算 | 被提出重复循环 | `a / b` 0.31 ns | 每次迭代都让输入不透明 |
| 测到了循环开销 | 被测代码太短，空循环占了大头 | 空循环约 0.31 ns/次 | 被测代码至少要比它大一两个数量级 |
| 数据总在缓存里 | 比真实场景快 | 见下文 | 按真实的数据量和访问模式测 |
| 输入每次都一样 | 分支预测器记住了答案 | 见下文 | 准备足够多份不同的输入 |

框架在中位数低于 0.1 ns 时会打印一个提示。本机测 `[] {}` 这样的空函数会得到 0.00 ns 和这个提示，只放一个 `clobber_memory()` 时是 0.31 ns，也就是空循环本身。

### 数据量

对 `int` 数组顺序求和，本机测得每个元素的耗时：数组 16 KiB 时 0.036 ns，1 MiB 时 0.045 ns，64 MiB 时约 0.08 ns。同样的代码，数据从一级缓存换到主存，每个元素慢了一倍多；如果访问是随机的，差距会大得多。基准里用一个小数组反复测，测到的是缓存全命中的情况。真实程序的数据量是多少、是不是刚被别的代码挤出缓存，要按实际情况准备，细节见 [[perf/memory-hierarchy|内存层级]]。

### 分支预测器会记住输入

```cpp title="bp.cpp"
#include "bench.hpp"
#include <algorithm>
#include <random>
#include <vector>

[[gnu::noinline]] int count_small(const unsigned char* p, int n) {
  int c = 0;
  for (int i = 0; i < n; ++i)
    if (p[i] < 128) { ++c; asm volatile(""); }  // 阻止编译器改成无分支代码
  return c;
}

int main() {
  bench::prefer_performance_cores();
  constexpr int N = 4096, K = 64;
  std::mt19937 rng(42);
  std::vector<unsigned char> data(N * K);
  for (auto& x : data) x = rng() & 0xff;
  bench::run("same 4 KiB each time", [&] {
    int c = count_small(data.data(), N);
    bench::do_not_optimize(c);
  });
  int k = 0;
  bench::run("rotate 64 buffers", [&] {
    int c = count_small(data.data() + N * k, N);
    k = (k + 1) % K;
    bench::do_not_optimize(c);
  });
  for (int j = 0; j < K; ++j)
    std::sort(data.begin() + N * j, data.begin() + N * (j + 1));
  bench::run("rotate 64 sorted", [&] {
    int c = count_small(data.data() + N * k, N);
    k = (k + 1) % K;
    bench::do_not_optimize(c);
  });
}
```

数据是随机字节，分支各有一半的机会走向两边。本机两次运行：

| 输入 | 中位数 |
|---|---|
| 同一份 4 KiB 随机数据反复用 | 2.62–2.63 µs |
| 64 份不同的随机数据轮流用 | 12.7 µs |
| 64 份排过序的数据轮流用 | 1.45 µs |

同一份数据被重复了成千上万次，预测器学会了这 4096 个分支的走向，测得的时间只有真实随机情况的五分之一。轮流使用 64 份数据（共 256 KiB）就学不会了。第三行说明差距不来自缓存：同样轮流使用 64 份数据，排过序后分支容易预测，就很快。分支预测本身见 [[perf/branches|分支]]。

## 公平地比较两个版本

优化的目的通常是回答"B 比 A 快吗"。要让这个比较公平：

1. **同一个程序、同样的编译选项、同样的输入**。两个版本放进同一个可执行文件，用同样的数据测。
2. **交替测量**。先测完 A 再测 B，B 就会受到 A 留下的缓存状态、频率变化、后台负载变化的影响。交替采样能让两边受到的漂移大致相同。框架的 `compare` 按 ABBA 的顺序交替，连先后顺序带来的偏差也抵消掉。
3. **先做 A/A 测试**。把同一个版本当成 A 和 B 各测一次。两者的差异就是这套测量的噪声底线，真实比较中小于这个数的差异不能说明任何问题。
4. **多跑几个进程**。同一个进程里的样本互相并不独立（同样的内存布局、同样的代码地址）。把整个程序跑几遍，看结论是否每次都成立。

```cpp title="aa.cpp"
#include "bench.hpp"
#include <numeric>
#include <vector>

[[gnu::noinline]] int sum_a(const std::vector<int>& v) {
  return std::accumulate(v.begin(), v.end(), 0);
}
[[gnu::noinline]] int sum_b(const std::vector<int>& v) {
  return std::accumulate(v.begin(), v.end(), 0);
}

int main() {
  bench::prefer_performance_cores();
  std::vector<int> v(4096, 1);
  auto a = [&] { int s = sum_a(v); bench::do_not_optimize(s); };
  auto b = [&] { int s = sum_b(v); bench::do_not_optimize(s); };
  bench::run("A", a);                    // 先后测量
  bench::run("B", b);
  bench::compare(a, b);                  // 交替测量
}
```

两个函数的代码完全相同（`nm` 显示它们是两个不同的符号，没有被合并）。本机运行六次：先后测量时，B 与 A 的中位数之比在 0.995 到 1.022 之间，最大的一次是 149.97 ns 对 153.26 ns，相差 2.2%；交替测量时 B/A 在 0.999 到 1.005 之间。

在这台机器、这个负载下，交替测量的噪声底线约为 0.5%，先后测量约为 2%。一个号称快了 1.5% 的优化，先后测量根本无法和噪声区分。差距在几个百分点以内时，还要警惕代码布局的影响：仅仅因为函数的地址或对齐变了，同样的指令也可能快慢不同。

## 现成的工具

本机没有安装 Google Benchmark，也没有 nanobench（`brew list` 里都没有），所以本节用自己写的小框架演示概念。两者的思路和上面一致：

- **Google Benchmark**：被测代码写在 `for (auto _ : state)` 循环里，库自动选择迭代次数；`benchmark::DoNotOptimize` 和 `benchmark::ClobberMemory` 就是上面那两行内联汇编的完整版本。`--benchmark_repetitions=N` 把整个测量重复 N 次，报告均值、中位数和标准差；近年的版本还提供预热时间和随机交替执行的选项。
- **nanobench**：单个头文件，`ankerl::nanobench::Bench().run("name", [&] { ... })`，用 `ankerl::nanobench::doNotOptimizeAway` 保护结果。它报告中位数和 `err%`（相对中位数的偏差），在 Linux 上还能读取硬件性能计数器，给出每次的指令数、周期数和分支预测失败率。

真正的项目应该用这些库，它们处理了很多这里省略的细节。理解了上面的机制，才能看懂它们的输出，也能在结果不对劲时知道去哪里查。

测量回答的是多快，不回答为什么。要知道时间花在哪里，用 [[perf/profiling|性能剖析]]。

## 可复用的框架：bench.hpp {#harness}

本节其余各页的例子都用这个头文件。它需要 C++20 和 GCC/Clang 的内联汇编语法。

```cpp title="bench.hpp" impl
// bench.hpp：一个够用的微基准框架（C++20，GCC/Clang 的内联汇编语法）
#pragma once
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <type_traits>
#include <utility>
#include <vector>
#if defined(__APPLE__)
#include <pthread.h>
#endif

namespace bench {

// 让编译器相信：v 的值被读取了，又可能被改掉了；任何内存都可能被读写。
template <class T>
inline void do_not_optimize(T& v) {
  if constexpr (std::is_trivially_copyable_v<T> && sizeof(T) <= sizeof(void*))
    asm volatile("" : "+r"(v) : : "memory");
  else
    asm volatile("" : "+m"(v) : : "memory");
}
template <class T>
inline void do_not_optimize(const T& v) {
  asm volatile("" : : "m"(v) : "memory");
}
// 只声明"任何内存都可能被读写"，不涉及具体变量。
inline void clobber_memory() { asm volatile("" : : : "memory"); }

struct stats { double min, median, max; };   // 单位：ns/次

// 一个样本：连续调用 f() n 次，返回平均每次的纳秒数。
template <class F>
double sample(F& f, long n) {
  auto t0 = std::chrono::steady_clock::now();
  for (long i = 0; i < n; ++i) f();
  auto t1 = std::chrono::steady_clock::now();
  return std::chrono::duration<double, std::nano>(t1 - t0).count() / n;
}

// 选一个 n，使一个样本至少持续约 1 ms（时钟步长的两万多倍）。
template <class F>
long calibrate(F& f) {
  long n = 1;
  while (n < (1L << 30) && sample(f, n) * n < 1e6) n *= 2;
  return n;
}

inline stats summarize(std::vector<double> t) {
  std::sort(t.begin(), t.end());
  return {t.front(), t[t.size() / 2], t.back()};
}

template <class F>
stats run(const char* name, F f, int samples = 31) {
  long n = calibrate(f);
  for (int i = 0; i < 3; ++i) sample(f, n);           // 预热，结果丢弃
  std::vector<double> t;
  for (int i = 0; i < samples; ++i) t.push_back(sample(f, n));
  stats s = summarize(t);
  std::printf("%-20s median %9.2f ns  min %9.2f  max %9.2f%s\n",
              name, s.median, s.min, s.max,
              s.median < 0.1 ? "  <- 被优化掉了？" : "");
  return s;
}

// 交替测量 a 和 b（ABBA 顺序），两边受到的漂移和干扰尽量相同。
template <class A, class B>
std::pair<stats, stats> compare(A a, B b, int rounds = 31) {
  long n = std::max(calibrate(a), calibrate(b));
  for (int i = 0; i < 3; ++i) { sample(a, n); sample(b, n); }
  std::vector<double> ta, tb;
  for (int i = 0; i < rounds; ++i) {
    if (i % 2 == 0) { ta.push_back(sample(a, n)); tb.push_back(sample(b, n)); }
    else            { tb.push_back(sample(b, n)); ta.push_back(sample(a, n)); }
  }
  stats sa = summarize(ta), sb = summarize(tb);
  std::printf("A median %.2f ns, B median %.2f ns, B/A = %.3f\n",
              sa.median, sb.median, sb.median / sa.median);
  return {sa, sb};
}

// macOS 不能把线程绑到指定核心；最高的 QoS 让调度器优先使用性能核。
inline void prefer_performance_cores() {
#if defined(__APPLE__)
  pthread_set_qos_class_self_np(QOS_CLASS_USER_INTERACTIVE, 0);
#endif
}

}  // namespace bench
```

典型用法：

```cpp title="use.cpp"
#include "bench.hpp"
#include <numeric>
#include <vector>

int main() {
  bench::prefer_performance_cores();
  std::vector<int> v(4096, 1);
  bench::run("sum 4096 ints", [&] {
    int s = std::accumulate(v.begin(), v.end(), 0);
    bench::do_not_optimize(s);
  });
}
```

```bash
clang++ -std=c++2c -O2 use.cpp -o use && ./use
```

本机一次输出 `sum 4096 ints  median 146.57 ns  min 145.54  max 331.79`。几点约定：

- 每个样本持续约 1 ms，默认记录 31 个样本，前面先丢弃 3 个预热样本；
- 报告中位数，用最小值、最大值提示离散程度；
- 被测的 lambda 里自己负责对输入和结果调用 `do_not_optimize`，框架不替你决定哪些值应该不透明；
- 被测代码每次调用之间如果有状态（例如轮流使用多份输入），状态放在 lambda 捕获的变量里，它的开销也会被算进去。

## 思考题

!!! question "常量输入"
    `long n = 1'000; bench::run("x", [&] { bench::do_not_optimize(sum_to(n)); });` 测到的是什么？

<details markdown="1">
<summary>答案</summary>

`sum_to(n)` 是临时值，选中 `const T&` 的重载。`n` 是一个从未被改过的局部变量，编译器知道它等于 1000，于是 `sum_to(1000)` 在编译期就算成了常量 332833500。本机 `-O2` 下 asm 前面只剩一条 `mov` 和一条把常量存到栈上的 `str`，测得 0.31 ns，也就是空循环的开销。要测运行期的计算，得先对 `n` 调用一次 `do_not_optimize`；即使这样，测到的也是闭式公式，见第一节。依据是 as-if 规则（[[intro.abstract#1]]）：在编译期还是运行期计算，不是可观察行为。
</details>

!!! question "为什么不给每次调用单独计时"
    对一次 150 ns 的调用，在前后各调一次 `steady_clock::now()`，记录 10000 个这样的差值再取中位数，有什么问题？

<details markdown="1">
<summary>答案</summary>

本机 `steady_clock` 的步长是 41 ns，测得的值只能是 41.7 ns 的整数倍附近，150 ns 会被量化成 125 或 167 左右，单个差值的误差可达 15% 以上。每次 `now()` 本身又要十几到几十纳秒，还会打断流水线。连续调用几千次再除以次数，可以把这两部分摊到几乎为零。代价是看不到单次调用的分布；真要测单次延迟，需要更精细的计时手段，并扣除计时本身的开销。
</details>

!!! question "1.5% 的提升"
    新版本 B 先后测量比 A 快了 1.5%，A/A 测试中先后测量的差异最大 2%，交替测量的差异最大 0.5%。该怎么做？

<details markdown="1">
<summary>答案</summary>

现在还不能下结论，1.5% 在先后测量的噪声范围内。改用交替测量（`bench::compare`），并把整个程序跑多遍。如果每一遍 B/A 都稳定在 0.985 左右，明显超出 0.5% 的噪声，才能说 B 确实快了约 1.5%。之后还要确认这个差异来自代码本身而不是布局：例如交换两个函数在源文件里的顺序再测一遍。
</details>
