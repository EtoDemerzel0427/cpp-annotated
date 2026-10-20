---
title: 多线程下的性能：争用与伪共享
summary: 为什么加线程反而会变慢：缓存行在核心之间来回搬运造成的伪共享，所有线程更新同一个原子变量的争用，各种内存序在 arm64 上生成什么指令、各花多少时间，互斥量、自旋锁与原子操作的取舍，shared_ptr 复制时的引用计数争用，以及开线程与线程池的开销，全部在 M2 Pro 上用 1 到 12 个线程实测。
status: draft
order: 55
group: 内存
since: c++11
papers: P0154R1, P3111R8
related: hardware.interference, intro.memory, intro.races, atomics.order, atomics.types.int, thread.mutex.requirements.mutex.general, futures.async, util.smartptr.shared, topics/memory-model, topics/ownership-and-smart-pointers, perf/measuring, perf/memory-hierarchy, perf/reading-assembly, perf/allocation
tags: 性能, 并发, 伪共享, 缓存行, 原子操作, 内存序, 互斥量, 线程池
updated: 2026-10-19
---

!!! tldr
    - 多个核心写同一个缓存行时，这一行要在核心之间来回搬运。即使各线程写的是不同的变量（伪共享），本机 8 个线程也会比单线程慢 7 倍；把每个变量对齐到 `std::hardware_destructive_interference_size`（本机 libc++ 为 128）就能消除。
    - 所有线程对同一个原子变量 `fetch_add`，加线程只会让总吞吐下降；各线程先在局部变量里累加、最后汇总一次，才会随线程数扩展。
    - 在 arm64 上，relaxed 的 `fetch_add` 是 `ldadd`，`acq_rel` 和 `seq_cst` 都是 `ldaddal`，本机无争用时前者约 2 ns、后者约 4 ns。内存序还限制编译器：acquire 读之后的普通变量不能留在寄存器里。
    - 短临界区在争用下，本机 `std::mutex` 比朴素自旋锁稳定得多；能用一个原子操作完成的，原子操作最快。
    - 复制 `shared_ptr` 是两次原子读-改-写；多个线程复制同一个 `shared_ptr` 就是在争用同一个计数器。新建一个线程本机要 10 µs 以上，线程池交出一个任务并等它完成要几微秒。

## 本机和测量方法

下面的数字都来自一台 Apple M2 Pro，macOS，Homebrew Clang 23 + libc++，`-std=c++2c -O2`。先看这台机器有几个核心、缓存行多大：

```text
$ sysctl hw.perflevel0.physicalcpu hw.perflevel1.physicalcpu hw.cachelinesize
hw.perflevel0.physicalcpu: 8
hw.perflevel1.physicalcpu: 4
hw.cachelinesize: 128
```

也就是 8 个性能核（P 核）、4 个能效核（E 核），缓存行 128 字节。**缓存行**（cache line）是缓存与内存、缓存与缓存之间搬运数据的最小单位，下面的大部分现象都由它决定。缓存层次本身见 [[perf/memory-hierarchy|内存层次]]。

计时用 [[perf/measuring#harness|bench.hpp]]，它提供 `do_not_optimize`（一条不生成指令的内联汇编，让编译器以为某个值被读取过，从而不删除计算它的代码）和 `prefer_performance_cores`（把线程的 QoS 设为最高，让调度器优先选 P 核；macOS 不能把线程绑到指定核心）。多线程的测量再加两个函数：

```cpp title="mt.hpp"
// mt.hpp：在 bench.hpp 之上加多线程计时
#pragma once
#include "bench.hpp"
#include <atomic>
#include <thread>

namespace bench {

// 开 n 个线程，等它们全部就位后同时放行，各自执行 body(i)；
// 返回从放行到最后一个线程结束的纳秒数。线程创建不计入。
template <class F>
double run_threads(int n, F body) {
  std::atomic<int> ready{0};
  std::atomic<bool> go{false};
  std::vector<std::jthread> ts;
  for (int i = 0; i < n; ++i)
    ts.emplace_back([&, i] {
      prefer_performance_cores();
      ready.fetch_add(1);
      while (!go.load(std::memory_order::acquire)) {}
      body(i);
    });
  while (ready.load() != n) {}
  auto t0 = std::chrono::steady_clock::now();
  go.store(true, std::memory_order::release);
  for (auto& t : ts) t.join();
  auto t1 = std::chrono::steady_clock::now();
  return std::chrono::duration<double, std::nano>(t1 - t0).count();
}

// f() 返回一次测量的结果；预热一次，再测 reps 次，取统计量
template <class F>
stats repeat(F f, int reps = 11) {
  f();
  std::vector<double> t;
  for (int r = 0; r < reps; ++r) t.push_back(f());
  return summarize(t);
}

}  // namespace bench
```

`run_threads` 先让所有线程就位再同时放行，这样计时不包含创建线程的时间，也不会出现第一个线程已经跑完、最后一个还没启动的情况。所有线程结束的时刻由 `join` 确定，线程的结束与 `join` 的返回同步，线程里的写入对主线程可见（[[thread.thread.member#4]]）。

!!! warning "这些数字是在繁忙的机器上测的"
    写作时这台机器同时在跑大量其他进程，`uptime` 显示的 load average 在 90 到 100 之间，远超 12 个核心。多线程的墙钟时间对这种干扰最敏感：线程被其他进程抢占时，最后一个线程结束得更晚。所以下面每张表都取 11 次运行中的最小值（干扰只会让时间变长），并且只应该看同一张表里的相对差别。绝对数字，尤其是 8 和 12 个线程的那几行，在空闲的机器上会不同；在别的 CPU 上更会不同。

### 理想情况：没有任何共享

先测一个没有任何共享数据的任务，作为后面各张表的参照。总工作量固定（2 亿次乘加），平分给 t 个线程：

```cpp title="scaling.cpp"
#include "mt.hpp"

constexpr long K = 200'000'000;

int main() {
  bench::prefer_performance_cores();
  double base = 0;
  std::printf("threads  wall_ms  speedup\n");
  for (int t : {1, 2, 4, 6, 8, 10, 12}) {
    auto s = bench::repeat([t] {
      return bench::run_threads(t, [t](int i) {
        unsigned long x = i + 1;
        for (long k = 0; k < K / t; ++k)       // 一条乘加依赖链
          x = x * 6364136223846793005ul + 1442695040888963407ul;
        bench::do_not_optimize(x);
      });
    });
    if (t == 1) base = s.min;
    std::printf("%7d %8.1f %8.2f\n", t, s.min / 1e6, base / s.min);
  }
}
```

| 线程数 | 1 | 2 | 4 | 6 | 8 | 10 | 12 |
|---|---|---|---|---|---|---|---|
| 墙钟时间（ms） | 197.5 | 102.7 | 52.5 | 36.9 | 28.7 | 23.3 | 23.8 |
| 加速比 | 1.00 | 1.92 | 3.77 | 5.35 | 6.89 | 8.47 | 8.31 |

到 8 个线程为止接近线性。再往上加的线程只能落到 E 核上，或者与其他进程分时，增益明显变小。后面各张表凡是比这条曲线差的地方，原因都在线程之间的共享上。

## 伪共享

### 各写各的，却互相拖慢

每个线程有一个自己的计数器，只有它自己写。三种布局：计数器紧挨着放，每个占 8 字节；每个对齐到 64 字节；每个对齐到 128 字节。

```cpp title="falseshare.cpp"
#include "mt.hpp"
#include <new>

constexpr long N = 20'000'000;          // 每个线程的自增次数

struct Packed { std::atomic<long> v; };
template <std::size_t A>
struct alignas(A) Padded { std::atomic<long> v; };
constexpr auto D = std::hardware_destructive_interference_size;

template <class Slot>
double ns_per_inc(int threads) {
  static Slot slots[16];
  return bench::repeat([&] {
    return bench::run_threads(threads, [&](int i) {
      auto* p = &slots[i].v;
      bench::do_not_optimize(p);         // 三种布局生成相同的寻址指令
      for (long k = 0; k < N; ++k)       // 只有本线程写 *p：读、加一、写回
        p->store(p->load(std::memory_order::relaxed) + 1,
                 std::memory_order::relaxed);
    }) / N;
  }).min;
}

int main() {
  bench::prefer_performance_cores();
  std::printf("threads  packed  pad64  pad128  (ns per increment)\n");
  for (int t : {1, 2, 4, 8, 12})
    std::printf("%7d %7.2f %6.2f %7.2f\n", t, ns_per_inc<Packed>(t),
                ns_per_inc<Padded<64>>(t), ns_per_inc<Padded<D>>(t));
}
```

计数器用 relaxed 原子变量，只是为了让每次自增都真的读写内存（普通 `long` 会被编译器放进寄存器，循环折叠成一次加法）。每个计数器只有一个线程写，先读后写不会丢增量。表中的数字是墙钟时间除以每个线程的次数，也就是每个线程做一次自增平均花的时间；如果线程之间没有干扰，这一列应该不随线程数变化。

| 线程数 | 挨着放（8 字节） | 对齐到 64 | 对齐到 128 |
|---|---|---|---|
| 1 | 0.31 ns | 0.32 ns | 0.31 ns |
| 2 | 1.59 | 0.74 | 0.33 |
| 4 | 1.87 | 0.66 | 0.60 |
| 8 | 2.24 | 0.95 | 0.72 |
| 12 | 3.02 | 1.05 | 0.62 |

单线程时三种布局一样快，0.31 ns 大约是一个时钟周期。两个线程时，挨着放的版本慢了 5 倍，而对齐到 128 字节的版本几乎不受影响。对齐到 64 字节只解决了一半：本机的缓存行是 128 字节，相邻两个 64 字节的槽仍然在同一行里。对齐到 128 的版本在 4 个以上线程时也变慢，本机这一部分与繁忙的机器有关（线程被抢占时最后一个结束得晚），需要在空闲机器上复测。

### 为什么

多核 CPU 用**缓存一致性协议**（cache coherence protocol）让各个核心的缓存看起来像一份内存。具体协议因 CPU 而异，但共同的规则是：一个核心要写某个缓存行，必须先独占它，其他核心缓存里的副本要作废。于是两个核心交替写同一行时，这一行就在两个核心之间来回搬运，每次写都可能要等一次核心间的传输，而不是在自己的 L1 里一个周期完成。

这里的两个线程写的是不同的变量，在 C++ 的意义上没有任何冲突。标准把每个标量对象算作一个独立的[[g:memory-location|内存位置]]，并且明说两个线程访问不同的内存位置互不干扰（[[intro.memory#3]]），所以这段代码没有[[g:data-race|数据竞争]]，结果也完全正确。干扰只发生在硬件层面：一致性协议以缓存行为单位工作，它不知道一行里有几个 C++ 对象。这种逻辑上不共享、物理上共享同一缓存行造成的减速，叫做**伪共享**（false sharing）。

### `hardware_destructive_interference_size`

C++17 起，`<new>` 提供两个常量（[[P0154R1]]，[[hardware.interference]]）。`hardware_destructive_interference_size` 是两个被并发访问的对象之间推荐的最小偏移，正是为了避免上面的情况（[[hardware.interference#1]]）：

!!! std
    This number is the minimum recommended offset between two concurrently-accessed objects to avoid additional performance degradation due to contention introduced by the implementation.

    两个被并发访问的对象至少隔开这么多字节，才能避免实现（缓存行）带来的额外争用。

它的值由实现定义。libc++ 直接用编译器预定义的宏 `__GCC_DESTRUCTIVE_SIZE` 和 `__GCC_CONSTRUCTIVE_SIZE`，本机 Clang 23 对不同目标给出的值如下（`clang++ --target=… -dM -E -x c++ /dev/null`）：

| 目标 | destructive | constructive |
|---|---|---|
| `arm64-apple-darwin`（本机） | 128 | 64 |
| `aarch64-linux-gnu` | 256 | 64 |
| `x86_64-linux-gnu`、`x86_64-apple-darwin` | 64 | 64 |

本机的 128 与 `hw.cachelinesize` 一致。注意它是编译期常量，取决于编译时的目标和选项，不是运行时查询到的硬件参数：在 x86-64 上编译、用 Rosetta 2 在 M2 上运行的程序看到的是 64。把它写进头文件里的 `alignas` 会让类的布局随编译选项变化，这个 ABI 风险见 [[support.dynamic]] 页的说明。

用法是给每个需要隔开的对象加 `alignas`：

<div class="compare" markdown="1">

```cpp
struct Stats {               // 伪共享
  std::atomic<long> hits;    // 线程 A 写
  std::atomic<long> misses;  // 线程 B 写
};
```

```cpp
struct Stats {
  alignas(std::hardware_destructive_interference_size)
    std::atomic<long> hits;
  alignas(std::hardware_destructive_interference_size)
    std::atomic<long> misses;
};
```

</div>

右边的 `Stats` 在本机占 256 字节。对齐超过 `__STDCPP_DEFAULT_NEW_ALIGNMENT__` 的类型用 `new` 或 `std::vector` 分配时，C++17 起会调用带 `std::align_val_t` 的分配函数，对齐有保证（[[expr.new]]）。

!!! pitfall "伪共享藏在哪里"
    除了显式的计数器数组，常见的还有：`std::vector<long> per_thread(n)` 这样按线程下标划分的结果数组；一个结构体里被不同线程写的两个字段；一把锁和它保护的、被另一个线程频繁读的数据；以及小对象分配。分配器通常把连续申请的小块放在相邻地址，后面 `shared_ptr` 一节就有一个实测的例子。

## 同一个原子变量上的争用

伪共享是不必要的共享；如果所有线程真的要更新同一个变量，争用就无法靠对齐消除。最常见的例子是统计计数：

```cpp title="counter.cpp"
#include "mt.hpp"

constexpr long K = 10'000'000;           // 每个线程计数 K 次
std::atomic<long> total{0};

template <std::memory_order MO>
void shared_counter(int) {
  for (long k = 0; k < K; ++k) total.fetch_add(1, MO);
}

void local_then_reduce(int) {
  long local = 0;
  for (long k = 0; k < K; ++k) {
    ++local;
    bench::do_not_optimize(local);       // 不让编译器把循环折叠成 local = K
  }
  total.fetch_add(local, std::memory_order::relaxed);
}

int main() {
  bench::prefer_performance_cores();
  std::printf("threads  relaxed  seq_cst   local  (ns per increment)\n");
  for (int t : {1, 2, 4, 8, 12}) {
    auto per = [t](auto f) {
      return bench::repeat([&] { return bench::run_threads(t, f); }).min /
             (double(K) * t);            // 墙钟时间 / 总次数
    };
    double a = per(shared_counter<std::memory_order::relaxed>);
    double b = per(shared_counter<std::memory_order::seq_cst>);
    double c = per(local_then_reduce);
    std::printf("%7d %8.2f %8.2f %7.3f\n", t, a, b, c);
  }
}
```

这张表的数字是墙钟时间除以所有线程的总次数，也就是整体上平均多久完成一次计数。理想情况下线程数翻倍，这个数字减半。

| 线程数 | 共享，relaxed | 共享，seq_cst | 各自累加再汇总 |
|---|---|---|---|
| 1 | 2.08 ns | 4.04 ns | 0.309 ns |
| 2 | 3.34 | 10.97 | 0.164 |
| 4 | 7.12 | 14.46 | 0.079 |
| 8 | 10.49 | 13.81 | 0.050 |
| 12 | 11.19 | 15.66 | 0.051 |

共享计数器的总吞吐随线程数下降：8 个线程完成同样多的计数，比 1 个线程慢 5 倍。每次 `fetch_add` 都要独占这个缓存行，所有线程的更新实际上排成一队，一次只有一个核心能做；排队之外还要付出缓存行在核心之间搬运的时间。各自累加的版本则与上一节的理想曲线一致，到 8 个线程为止接近线性，最后的 12 次 `fetch_add` 可以忽略不计。

正确性上，各线程只在结束时把局部和加进 `total`，主线程在 `join` 之后读取，`join` 提供了同步，用 relaxed 就够了。为什么 relaxed 的读-改-写不会丢增量，见 [[topics/memory-model|内存模型实战]]中 relaxed 计数器一节。

如果确实需要一个实时的全局计数，常见的折中是分片：准备若干个按缓存行对齐的计数器，每个线程按自己的编号更新其中一个，读的时候把它们加起来。读到的和不是某一时刻的精确快照，但每个分片的争用小得多。

!!! note "C++26 的 `store_add`"
    C++26 给整数和浮点原子类型加了 `store_add`、`store_sub` 等不返回旧值的操作（[[P3111R8]]），标准称之为[[g:atomic-modify-write-operation|原子修改-写操作]]（[[atomics.order#12]]）。它们的同步要求比 `fetch_add` 弱：标准的注解说明，意图是让实现可以使用不受 acquire 栅栏排序的硬件机制。截至写作时本机 libc++ 还没有实现 `store_add`。

## 内存序的代价

`memory_order` 的语义见 [[topics/memory-model|内存模型实战]]，这里只看它在本机生成什么指令、花多少时间。

### 生成的指令

```cpp title="mo.cpp"
#include <atomic>
std::atomic<long> c;
void add_relaxed() { c.fetch_add(1, std::memory_order::relaxed); }
void add_seq_cst() { c.fetch_add(1); }                 // 默认 seq_cst
void store_relaxed(long v) { c.store(v, std::memory_order::relaxed); }
void store_seq_cst(long v) { c.store(v); }
long load_acquire() { return c.load(std::memory_order::acquire); }
long load_seq_cst() { return c.load(); }
```

本机 `clang++ -std=c++2c -O2 -S` 生成的关键指令，以及 `--target=x86_64-linux-gnu` 和 `--target=aarch64-linux-gnu` 的对照（交叉编译时没有对应的标准库头文件，用的是等价的 `__atomic_*` 内建函数）：

| 操作 | arm64 macOS（`-mcpu=apple-m1`） | x86-64 | aarch64 Linux（默认 ARMv8.0） |
|---|---|---|---|
| `fetch_add` relaxed | `ldadd` | `lock inc` | `ldxr` / `stxr` 循环 |
| `fetch_add` acq_rel、seq_cst | `ldaddal` | `lock inc` | `ldaxr` / `stlxr` 循环 |
| `store` relaxed | `str` | `mov` | `str` |
| `store` seq_cst | `stlr` | `xchg` | `stlr` |
| `load` acquire | `ldapr` | `mov` | |
| `load` seq_cst | `ldar` | `mov` | `ldar` |

几点值得注意：

- arm64 的 `ldadd` 一族是 ARMv8.1 的 LSE 原子指令，一条指令完成读-加-写。名字后缀 `a` 表示带 acquire 语义，`l` 表示带 release 语义，`al` 两者都有。Apple 芯片都支持 LSE，所以 Clang 对 `arm64-apple-darwin` 默认生成它们。
- 面向通用 ARMv8.0 编译时没有 LSE，只能用 `ldxr`/`stxr`（独占加载、独占存储）写成失败重试的循环；加 `-march=armv8.1-a` 后变成 `ldadd`/`ldaddal`，加 `-moutline-atomics` 则变成对 `__aarch64_ldadd8_relax` 等辅助函数的调用，由它们在运行时选择指令。在 Linux 服务器上，同一份源码的原子操作代价可能因编译选项而不同。
- x86-64 上所有读-改-写指令都带 `lock` 前缀，本身就是完整的屏障，relaxed 和 seq_cst 的 `fetch_add` 是同一条指令；只有 seq_cst 的 `store` 不同（`xchg` 而不是 `mov`）。在 x86 上测出 relaxed 和 seq_cst 一样快，不能推广到 ARM。
- arm64 的 acquire 读用 `ldapr`（ARMv8.3 的 RCpc 指令），seq_cst 读用 `ldar`。区别在于 `ldar` 不能越过它前面的 `stlr`，这正是 seq_cst 要禁止的 store buffering。

### 测出来的时间

单线程、无争用，同一个循环体换不同的内存序，用 bench.hpp 的 `run` 测：

```cpp title="memorder.cpp"
#include "mt.hpp"
using std::memory_order;
constexpr auto R = memory_order::relaxed, Acq = memory_order::acquire,
               Rel = memory_order::release, AR = memory_order::acq_rel,
               SC = memory_order::seq_cst;

std::atomic<long> a{0}, b{0};
long k = 0, s = 0;

int main() {
  bench::prefer_performance_cores();
  bench::run("fetch_add relaxed", [] { a.fetch_add(1, R); });
  bench::run("fetch_add acq_rel", [] { a.fetch_add(1, AR); });
  bench::run("fetch_add seq_cst", [] { a.fetch_add(1, SC); });
  bench::run("store relaxed", [] { a.store(++k, R); });
  bench::run("store seq_cst", [] { a.store(++k, SC); });
  bench::run("load relaxed", [] { s += a.load(R); });
  bench::run("load acquire", [] { s += a.load(Acq); });
  bench::run("load seq_cst", [] { s += a.load(SC); });
  bench::run("store Rel, load Acq", [] { a.store(++k, Rel); s += b.load(Acq); });
  bench::run("store SC, load SC", [] { a.store(++k, SC); s += b.load(SC); });
  bench::do_not_optimize(s);
}
```

| 操作 | 指令 | 每次（31 个样本的最小值 / 中位数） |
|---|---|---|
| `fetch_add` relaxed | `ldadd` | 1.94 / 2.04 ns |
| `fetch_add` acq_rel | `ldaddal` | 3.99 / 4.04 ns |
| `fetch_add` seq_cst | `ldaddal` | 3.99 / 4.04 ns |
| `store` relaxed | `str` | 0.31 / 0.32 ns |
| `store` seq_cst | `stlr` | 0.31 / 0.52 ns |
| `load` relaxed | `ldr` | 0.11 / 0.13 ns |
| `load` acquire | `ldapr` | 1.15 / 1.36 ns |
| `load` seq_cst | `ldar` | 1.15 / 2.62 ns |
| `store` release 后 `load` acquire（不同变量） | `stlr` + `ldapr` | 0.46 / 0.47 ns |
| `store` seq_cst 后 `load` seq_cst（不同变量） | `stlr` + `ldar` | 0.46 / 0.46 ns |

读-改-写操作的差别最清楚：同样的循环、同样只有一条原子指令，`ldaddal` 比 `ldadd` 慢一倍。在本机的这个测试里，带 release 的 `stlr` 与普通 `str` 没有分别；`stlr` 后接 `ldar` 本来是 seq_cst 比 acquire/release 多出的代价所在，本机也没有测出差别。这些结论只对这颗芯片、这种无争用的循环成立。

relaxed 读和 acquire 读相差 10 倍，但大部分差别不在指令本身。看两个循环的汇编：

<div class="compare" markdown="1">

```text
; s += a.load(relaxed)
; s 留在寄存器里，循环展开 4 次
LBB0_3:
  ldr  x16, [x11, _a@PAGEOFF]
  add  x9, x9, x16
  ldr  x16, [x11, _a@PAGEOFF]
  add  x12, x12, x16
  ...
```

```text
; s += a.load(acquire)
; 每次都从内存读写 s
LBB1_2:
  ldapr x10, [x8]
  ldr   x11, [x9, _s@PAGEOFF]
  add   x10, x11, x10
  str   x10, [x9, _s@PAGEOFF]
  subs  x0, x0, #1
  b.ne  LBB1_2
```

</div>

acquire 读之后的读写不能被移到它前面（[[intro.races]] 中 happens before 的定义由此而来）。另一个线程可能在 release 之前修改了 `s`，然后由这次 acquire 读同步过来，所以编译器不能把 `s` 缓存在寄存器里跨越 acquire 读，每次迭代都要真的读写内存。内存序首先是对编译器的约束，其次才是对 CPU 的约束；它的代价常常体现在被禁止的优化上。

### 有争用时

上一节的计数器表里，共享 `seq_cst` 计数器在 2 个以上线程时比 relaxed 慢 1.3 到 3 倍，幅度大于无争用时的 2 倍。对于只做统计、不用来发布其他数据的计数器，relaxed 既正确又最便宜；默认的 `seq_cst` 是为了让推理最简单，不是因为计数需要它。

## 互斥量、自旋锁与原子操作

同一个计数器，三种保护方式：`std::mutex`；一个 test-and-test-and-set 自旋锁（先用 `exchange` 抢锁，抢不到就只读等待，直到锁看起来空闲再抢）；直接用原子 `fetch_add`。

```cpp title="locks.cpp"
#include "mt.hpp"
#include <mutex>

constexpr long K = 2'000'000;            // 每个线程加 K 次

class Spinlock {                         // test-and-test-and-set
  std::atomic<bool> locked_{false};
public:
  void lock() {
    while (locked_.exchange(true, std::memory_order::acquire))
      while (locked_.load(std::memory_order::relaxed)) {}
  }
  void unlock() { locked_.store(false, std::memory_order::release); }
};

long plain = 0;
std::mutex m;
Spinlock spin;
std::atomic<long> a{0};

int main() {
  bench::prefer_performance_cores();
  std::printf("threads   mutex    spin  atomic  (ns per increment)\n");
  for (int t : {1, 2, 4, 8, 12}) {
    auto per = [t](auto f) {
      return bench::repeat([&] { return bench::run_threads(t, f); }).min /
             (double(K) * t);
    };
    double x = per([](int) {
      for (long k = 0; k < K; ++k) { std::lock_guard g(m); ++plain; }
    });
    double y = per([](int) {
      for (long k = 0; k < K; ++k) { std::lock_guard g(spin); ++plain; }
    });
    double z = per([](int) {
      for (long k = 0; k < K; ++k) a.fetch_add(1, std::memory_order::relaxed);
    });
    std::printf("%7d %7.1f %7.1f %7.1f\n", t, x, y, z);
  }
}
```

`Spinlock` 有 `lock` 和 `unlock`，满足 *BasicLockable*，可以直接交给 `std::lock_guard`。`unlock` 的 release 写与下一次成功的 acquire `exchange` 同步，所以 `plain` 的读写之间都有 happens before；用 `-fsanitize=thread` 运行这个程序（把 `K` 改小），TSan 没有报告。`std::mutex` 的 `unlock` 与之后的 `lock` 同步由标准保证（[[thread.mutex.requirements.mutex.general#8]]）。

表中是墙钟时间除以总次数：

| 线程数 | `std::mutex` | 自旋锁 | 原子 `fetch_add` |
|---|---|---|---|
| 1 | 6.1 ns | 4.9 ns | 2.1 ns |
| 2 | 11.3 | 20.3 | 4.3 |
| 4 | 22.7 | 24.8 | 9.8 |
| 8 | 18.8 | 71.2 | 9.9 |
| 12 | 18.9 | 126.0 | 20.1 |

- 没有争用时，自旋锁比 `std::mutex` 稍快：加锁和解锁各是一条原子指令，`std::mutex` 在 libc++ 里是 `pthread_mutex_t` 的包装，要经过一次函数调用和更多检查。
- 有争用时，自旋锁随线程数迅速变差。等待的线程都在读同一个缓存行，锁一释放，所有等待者同时 `exchange`，这一行又被争抢一轮。更糟的是，持有锁的线程如果被操作系统换下（线程数超过空闲核心数时这很常见，测量时机器就处于这种状态），其他线程只能空转一整个时间片。
- `std::mutex` 在争用时会让等待的线程睡眠，由内核唤醒，8 和 12 个线程时没有继续变差。它的每次操作比自旋锁贵，但不会因为抢占而崩溃。
- 临界区只是一个整数加法时，原子操作最快，但它同样受第一节所说的单个缓存行争用限制，12 个线程时并不比 1 个线程快。

在一次负载稍低时的重复运行中，`std::mutex` 一列是 6.1、7.6、13.8、15.3、15.8 ns，自旋锁在 8 和 12 个线程时是 174 和 281 ns，结论相同，自旋锁的数字波动最大。

真正的结论在最后一点：这三种方式都没有让计数随线程数扩展。临界区越短、越频繁，锁的开销占比越大；要扩展，得像上一节那样减少共享本身，而不是换一把更快的锁。自己写自旋锁在用户态程序里很少划算，除非能确定临界区极短且线程数不超过核心数。

## `shared_ptr` 的复制

`shared_ptr` 的引用计数由实现用原子操作维护，多个线程各自复制、销毁指向同一对象的 `shared_ptr` 是安全的（[[util.smartptr.shared.general#5]]，三个层次的线程安全见 [[topics/ownership-and-smart-pointers|所有权与智能指针]]）。安全的代价就是原子操作。本机 libc++ 复制再销毁一个 `shared_ptr` 的循环体编译成：

```text
ldr   x8, [x20, #8]          ; 控制块指针
ldr   q0, [x20]              ; 复制两个指针
str   q0, [sp, #16]
cbz   x8, ...
add   x8, x8, #8             ; 共享计数的地址
ldadd x24, x8, [x8]          ; 复制：计数 + 1，relaxed
...
ldaddal x23, x8, [x8]        ; 析构：计数 - 1，acq_rel（x23 = -1）
cbnz  x8, ...                ; 减到 0 时才销毁对象
```

复制一次 `ldadd`，销毁一次 `ldaddal`。如果多个线程复制的是指向同一对象的 `shared_ptr`，它们就在争用同一个控制块里的计数器，情形与上一节的共享计数器完全相同。

```cpp title="sp.cpp"
#include "mt.hpp"
#include <memory>

constexpr long K = 5'000'000;

struct Config { int value = 42; };
struct alignas(128) PaddedConfig { int value = 42; };

template <class P>
void copy_loop(const P& src) {
  for (long k = 0; k < K; ++k) {
    P copy = src;                        // 计数加一
    bench::do_not_optimize(copy);
  }                                      // 析构：计数减一
}

int main() {
  bench::prefer_performance_cores();
  auto shared = std::make_shared<Config>();
  std::shared_ptr<Config> own[16];
  std::shared_ptr<PaddedConfig> own_padded[16];
  for (auto& p : own) p = std::make_shared<Config>();
  for (auto& p : own_padded) p = std::make_shared<PaddedConfig>();
  std::printf("own[0..3]: %p %p %p %p\n", (void*)own[0].get(),
              (void*)own[1].get(), (void*)own[2].get(), (void*)own[3].get());

  std::printf("threads  same  own  own_padded  by_ref  (ns per copy)\n");
  for (int t : {1, 2, 4, 8, 12}) {
    auto per = [t](auto f) {
      return bench::repeat([&] { return bench::run_threads(t, f); }).min /
             (double(K) * t);
    };
    double a = per([&](int) { copy_loop(shared); });
    double b = per([&](int i) { copy_loop(own[i]); });
    double c = per([&](int i) { copy_loop(own_padded[i]); });
    double d = per([&](int) {
      for (long k = 0; k < K; ++k) {
        const auto& ref = shared;        // 不复制，只借用
        bench::do_not_optimize(ref->value);
      }
    });
    std::printf("%7d %6.2f %5.2f %11.2f %7.2f\n", t, a, b, c, d);
  }
}
```

| 线程数 | 同一个对象 | 各自的对象 | 各自的对象，对齐到 128 | 不复制，用引用 |
|---|---|---|---|---|
| 1 | 5.11 ns | 5.38 ns | 5.13 ns | 1.39 ns |
| 2 | 13.45 | 2.58 | 2.71 | 0.81 |
| 4 | 17.01 | 1.40 | 1.61 | 0.70 |
| 8 | 24.15 | 8.75 | 0.90 | 0.38 |
| 12 | 31.23 | 4.54 | 0.81 | 0.31 |

（墙钟时间除以总次数。）

第一列是预期中的争用：一次复制加销毁在单线程时约 5 ns，8 个线程时整体吞吐反而降到单线程的约五分之一。

第二列是一个不那么明显的伪共享。每个线程复制的是自己的 `shared_ptr`，对象各不相同，但 8 个线程时仍然比对齐的版本慢近 10 倍。程序打印的地址说明了原因：

```text
own[0..3]: 0x101585d78 0x101585d98 0x101585b78 0x101585b98
```

`make_shared<Config>` 把控制块和 `Config` 放在一次 32 字节的分配里，连续的几次分配被分配器放在相邻地址，相隔 32 字节，四个控制块挤在同一个 128 字节的缓存行里。第三列让对象对齐到 128 字节，控制块和对象一起被隔开，伪共享随之消失。

第四列表明，大多数时候根本不需要复制。只在当前调用期间使用对象的函数，形参写成 `const T&` 或 `T*`，或者 `const shared_ptr<T>&`，不碰引用计数；只有要延长对象寿命、把所有权存起来的地方才按值接收 `shared_ptr`。这条参数传递规则的完整讨论见 [[topics/ownership-and-smart-pointers|所有权与智能指针]]。

## 开线程与线程池

最后一个容易被忽视的开销是线程本身。下面比较四种执行 2000 个微小任务的方式：每个任务新建一个 `std::jthread` 并立即 `join`；每个任务调用一次 `std::async(std::launch::async, …)` 并 `get()`；交给一个预先创建好的 8 线程池，交一个、等它做完再交下一个；一次把 2000 个任务全交给池，最后等一次。

```cpp title="pool.cpp"
#include "mt.hpp"
#include <condition_variable>
#include <deque>
#include <functional>
#include <future>
#include <mutex>

class Pool {
  std::mutex m_;
  std::condition_variable cv_;
  std::deque<std::function<void()>> q_;
  bool stop_ = false;
  std::vector<std::jthread> workers_;
public:
  explicit Pool(int n) {
    for (int i = 0; i < n; ++i)
      workers_.emplace_back([this] {
        bench::prefer_performance_cores();
        for (;;) {
          std::function<void()> job;
          {
            std::unique_lock lk(m_);
            cv_.wait(lk, [this] { return stop_ || !q_.empty(); });
            if (q_.empty()) return;          // stop_ 且队列已空
            job = std::move(q_.front());
            q_.pop_front();
          }
          job();
        }
      });
  }
  void submit(std::function<void()> f) {
    { std::lock_guard lk(m_); q_.push_back(std::move(f)); }
    cv_.notify_one();
  }
  ~Pool() {
    { std::lock_guard lk(m_); stop_ = true; }
    cv_.notify_all();
  }                                          // workers_ 析构时 join
};

constexpr int Tasks = 2000;
std::atomic<int> done{0};

double ns_per_task(auto f) {
  return bench::repeat([&] {
    auto t0 = std::chrono::steady_clock::now();
    f();
    auto t1 = std::chrono::steady_clock::now();
    return std::chrono::duration<double, std::nano>(t1 - t0).count() / Tasks;
  }).min;
}

int main() {
  bench::prefer_performance_cores();
  auto tiny = [] { done.fetch_add(1, std::memory_order::relaxed); };

  double create = ns_per_task([&] {        // 开线程、跑、join，一个接一个
    for (int i = 0; i < Tasks; ++i) std::jthread(tiny).join();
  });
  double async = ns_per_task([&] {
    for (int i = 0; i < Tasks; ++i) std::async(std::launch::async, tiny).get();
  });
  Pool pool(8);
  double pooled = ns_per_task([&] {        // 交给池，等它做完再交下一个
    for (int i = 0; i < Tasks; ++i) {
      std::atomic<bool> f{false};
      pool.submit([&] { tiny(); f.store(true, std::memory_order::release);
                        f.notify_one(); });
      f.wait(false, std::memory_order::acquire);
    }
  });
  double batch = ns_per_task([&] {         // 一次交出全部任务，最后等一次
    int start = done.load();
    for (int i = 0; i < Tasks; ++i) pool.submit(tiny);
    while (done.load() - start < Tasks) std::this_thread::yield();
  });
  std::printf("thread create+join  %8.0f ns\n", create);
  std::printf("std::async + get    %8.0f ns\n", async);
  std::printf("pool round trip     %8.0f ns\n", pooled);
  std::printf("pool batch          %8.0f ns\n", batch);
}
```

| 方式 | 每个任务（每次运行取 11 轮的最小值，5 次运行的范围） |
|---|---|
| 新建 `std::jthread` 再 `join` | 13–22 µs |
| `std::async(launch::async)` 再 `get` | 11–23 µs |
| 线程池，交一个等一个 | 3.1–6.4 µs |
| 线程池，一次交出全部 | 0.06–1.3 µs |

这张表对机器的负载最敏感，5 次运行之间的差别比任何一张表都大，只能看数量级。

新建一个线程要向内核申请线程、分配栈、调度它运行，`join` 还要等它被调度、结束、通知回来，本机合计在 10 到 20 多微秒之间，相当于几千次无争用的原子操作。`std::async` 与之在同一量级，因为 libc++ 对 `launch::async` 的实现就是每次新建一个线程再 `detach`（标准要求它表现得如同在一个由 `thread` 对象表示的新线程中运行，[[futures.async#3]]）。

线程池省掉了创建，剩下的是交接：入队、唤醒一个睡眠的工作线程、完成后唤醒提交者。交一个等一个时，每个任务要经历两次跨线程唤醒，约 3 到 6 µs。一次交出全部任务时唤醒的开销被摊薄，工作线程醒着就会连续从队列里取任务，快的时候每个任务只要几十纳秒，剩下的主要是工作线程和提交者对队列那把锁的争用；机器繁忙、工作线程被换下时，则升到 1 µs 左右。所以任务至少要比这些开销大一两个数量级，并行才划算；更小的工作应当合并成块再分发。

## 常见错误

!!! pitfall "按线程下标划分的结果数组"
    `std::vector<long> sum(nthreads)` 再让线程 i 在循环里反复写 `sum[i]`，是最常见的伪共享。要么在局部变量里累加、最后写一次，要么让每个元素对齐到 `hardware_destructive_interference_size`。

!!! pitfall "以为 64 字节对齐就够了"
    很多代码按 x86 的习惯写死 `alignas(64)`。本机测得两个线程时 64 字节对齐的版本仍比 128 字节对齐的慢一倍多（0.74 ns 对 0.33 ns）。在 Apple 芯片上用 128，或者直接用 `std::hardware_destructive_interference_size`。

!!! pitfall "在 x86 上测内存序"
    x86 上 relaxed 与 seq_cst 的 `fetch_add` 是同一条 `lock` 指令，测不出差别。在 ARM 上它们是 `ldadd` 和 `ldaddal`，本机相差一倍。内存序的选择要按标准的语义来定，性能要在目标平台上测。

!!! pitfall "用加锁的方式让计数扩展"
    换成更快的锁、换成原子操作，都只是改变排队的速度。所有线程都要更新同一个缓存行，这本身就是扩展的上限。

## 思考题

!!! question "1"
    把 `falseshare.cpp` 里的 `std::atomic<long>` 换成普通 `long`，自增写成 `++slots[i].v`，`-O2` 编译后三种布局的速度还会不同吗？这样改是否引入了数据竞争？

<details markdown="1">
<summary>答案</summary>

不会引入数据竞争：每个 `long` 是独立的内存位置，只有一个线程访问它，与其他线程的访问不冲突（[[intro.memory#3]]、[[intro.races#2]]），主线程读之前有 `join` 同步。

速度也不再不同。没有数据竞争意味着编译器可以假设别的线程不会碰这个 `long`，于是按 as-if 规则（[[intro.abstract#1]]）合并这些访问。本机 Clang 23 `-O2` 把整个循环编译成一次 `ldr`、一次 `add x9, x9, x1`（加上次数 N）和一次 `str`。没有反复的内存写，也就没有缓存行的来回搬运。正因为如此，测伪共享时要用 relaxed 原子操作或 `volatile` 迫使每次自增都访问内存。实际程序中伪共享通常出现在编译器无法这样合并的地方：循环里有函数调用、写入的地址每次不同，或者本来就是原子变量。
</details>

!!! question "2"
    一个服务器把请求计数存在全局的 `std::atomic<long> requests`，每个请求处理线程 `requests++`。改成 `requests.fetch_add(1, std::memory_order::relaxed)` 能解决多核上的扩展问题吗？

<details markdown="1">
<summary>答案</summary>

能减少一部分开销，解决不了扩展问题。`requests++` 等价于 `fetch_add(1)`，即 seq_cst（[[atomics.types.memop#2]]），在 arm64 上是 `ldaddal`，改成 relaxed 后是 `ldadd`，本机单线程从约 4 ns 降到约 2 ns。但无论哪种内存序，每次加法都要独占同一个缓存行，`counter.cpp` 的表里 relaxed 的共享计数器在 8 个线程时总吞吐仍只有单线程的五分之一。要扩展，需要分片计数或线程局部累加、定期汇总。
</details>

## 小结

| 现象 | 原因 | 本机实测 | 做法 |
|---|---|---|---|
| 各写各的变量也变慢 | 伪共享：同一缓存行在核心间搬运 | 2 线程慢 5 倍 | 对齐到 `hardware_destructive_interference_size`（本机 128） |
| 共享计数器越加线程越慢 | 所有更新排队独占一个缓存行 | 8 线程总吞吐为单线程的 1/5 | 线程局部累加再汇总；分片 |
| seq_cst 读-改-写更慢 | arm64 上 `ldaddal` 对 `ldadd` | 4 ns 对 2 ns | 只统计时用 relaxed |
| acquire 读之后的代码变慢 | 编译器不能跨越它缓存变量 | 循环慢 10 倍 | 把 acquire 读移出热循环 |
| 自旋锁在争用下崩溃 | 等待者争抢缓存行；持锁线程被抢占 | 12 线程时比 mutex 慢 6 倍多 | 用 `std::mutex`；减少共享 |
| 复制 `shared_ptr` 不扩展 | 复制和销毁各一次原子读-改-写 | 8 线程时 24 ns 一次 | 借用时传引用；相邻控制块也会伪共享 |
| 小任务并行反而慢 | 新建线程 10 µs 以上，池交接几微秒 | | 用线程池，合并成大块任务 |
