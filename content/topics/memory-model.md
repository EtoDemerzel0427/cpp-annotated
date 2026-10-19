---
title: 内存模型实战
summary: 从一段坏掉的消息传递代码出发，用 sequenced before、synchronizes with、happens before 和修改顺序推理多线程程序，配合 ThreadSanitizer 和在 Apple Silicon 上实测的 litmus 结果，讲清 acquire/release、relaxed、seq_cst、栅栏和标准库同步设施各自保证什么。
status: draft
order: 70
since: c++11
papers: P0982R1, P3475R2
related: intro.multithread, intro.races, intro.progress, atomics.order, atomics.fences, atomics.wait, atomics.lockfree, depr.atomics, thread.mutex.requirements, thread.once, thread.coord, topics/undefined-behavior, history/threads-and-memory-model
tags: 内存模型, 并发, 原子操作, 数据竞争, TSan, 专题
updated: 2026-10-19
---

!!! tldr
    - 两个线程访问同一内存位置，至少一个是写、至少一个不是原子操作、两者之间又没有 happens before，就是数据竞争，整个程序的行为未定义。
    - happens before 只有两种来源：同一线程内的 sequenced before，和线程间的 synchronizes with。后者只在 acquire 一方实际读到 release 一方写入的值时才出现。
    - relaxed 原子操作不会造成数据竞争，但不在线程之间传递任何其他数据的可见性；读-改-写操作总是读最新值，所以 relaxed 计数器不丢增量。
    - acquire/release 管不了先写后读的顺序（store buffering），这需要两边都用 `seq_cst`，或在中间放 `seq_cst` 栅栏。
    - 在 x86 上测不出问题不代表代码正确：同一个 relaxed 消息传递程序，在 Apple Silicon 上每百万次出错上万次，在 Rosetta 2 下运行的 x86-64 版本一次也没有。

## 一段坏掉的消息传递

一个线程准备好数据，再举起一个标志；另一个线程等标志，再读数据。这种模式叫**消息传递**（message passing，MP）。最直接的写法如下：

```cpp run title="mp-plain.cpp" ub
#include <chrono>
#include <cstdio>
#include <thread>
int data = 0;
bool ready = false;
int main() {
  std::thread producer([] {
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    data = 42;
    ready = true;            // 普通写
  });
  std::thread consumer([] {
    while (!ready) {}        // 与 ready = true 构成数据竞争
    std::printf("%d\n", data);
  });
  producer.join(); consumer.join();
}
```

本机 Clang 23 用 `-O0` 编译时输出 `42`，用 `-O2` 编译时输出 `0`。看 `-O2` 的 AArch64 汇编，consumer 里根本没有读 `ready` 的指令，循环被整个删掉了，直接读 `data` 并打印。

编译器的推理是这样的：如果别的线程能在这个循环运行时修改 `ready`，那就是数据竞争，程序本来就没有定义的行为，所以它可以假设 `ready` 在循环中不变，只读一次。读到 `true`，循环什么也不做；读到 `false`，循环就是一个永远不做任何事的死循环，而 [[intro.progress#1]] 允许实现假设每个线程最终会终止，或者执行 I/O、volatile 访问、原子或同步操作之类的动作（常量条件的平凡死循环除外）。两种情况都不需要循环，于是删掉。

用 ThreadSanitizer（TSan，`-fsanitize=thread`）运行，它报告的是 `ready` 上的竞争：

```text
$ clang++ -std=c++2c -g -gdwarf-4 -O0 -fsanitize=thread mp-plain.cpp && ./a.out
WARNING: ThreadSanitizer: data race (pid=38557)
  Write of size 1 at 0x00010295c0dc by thread T1:
    #0 main::$_0::operator()() const mp-plain.cpp:10
  Previous read of size 1 at 0x00010295c0dc by thread T2:
    #0 main::$_1::operator()() const mp-plain.cpp:13
  As if synchronized via sleep:
    #0 nanosleep <null>
  Location is global 'ready' at 0x00010295c0dc
```

`As if synchronized via sleep` 提示 `sleep_for` 让两次访问在时间上错开了，但 TSan 照样报告，因为 `sleep_for` 不提供任何同步（[[thread.thread.this#8]] 写明 *Synchronization: None*）。TSan 检查的是下文定义的 happens before 关系，不是时间上的先后。

### 把标志改成 relaxed 原子

```cpp run title="mp-relaxed-flag.cpp" ub
#include <atomic>
#include <cstdio>
#include <thread>
int data = 0;
std::atomic<bool> ready{false};
int main() {
  std::thread producer([] {
    data = 42;
    ready.store(true, std::memory_order::relaxed);
  });
  std::thread consumer([] {
    while (!ready.load(std::memory_order::relaxed)) {}
    std::printf("%d\n", data);   // 与 data = 42 构成数据竞争
  });
  producer.join(); consumer.join();
}
```

`ready` 上的竞争消失了，原子对象上的访问不构成数据竞争。循环也不会被删掉，原子读每次都要真的执行。但 TSan 每次运行都报告 `data` 上的竞争：第 13 行的读与第 8 行的写。relaxed 原子操作只保证 `ready` 本身，不让 `data = 42` 对 consumer 可见。

### 把数据也改成原子

如果 `data` 也是 `std::atomic<int>`，所有访问都 relaxed，程序就没有数据竞争，行为是确定的：consumer 读到的 `data` 可以是 0，也可以是 42，两者都是合法结果。下文的 litmus 测试在 Apple Silicon 上实测，每一百万次中出现几千到几万次看到标志却读到 0 的情形。

### 正确的写法

```cpp run title="mp.cpp" ok
#include <atomic>
#include <cstdio>
#include <thread>
int data = 0;
std::atomic<bool> ready{false};
int main() {
  std::thread producer([] {
    data = 42;                                          // A
    ready.store(true, std::memory_order::release);      // B
  });
  std::thread consumer([] {
    while (!ready.load(std::memory_order::acquire)) {}  // C：读到 B 写的 true
    std::printf("%d\n", data);                          // D
  });
  producer.join(); consumer.join();
}
```

只改了两个内存序参数，TSan 不再报告，D 一定读到 42。下面几节说明为什么。

## 数据竞争的定义

两个求值**冲突**，是指它们访问同一个[[g:memory-location|内存位置]]，并且至少一个是修改（[[intro.races#2]]）。内存位置是一个标量对象，或一串相邻的非零宽位域（[[intro.memory]]）；`struct { char a; char b; }` 的两个成员是两个内存位置，两个线程分别写它们不冲突。

[[intro.races#17]] 给出定义：一次执行中有两个冲突的动作，它们可能并发（在不同线程中），至少一个不是原子操作，并且谁也不 happens before 谁，这次执行就含有[[g:data-race|数据竞争]]，行为未定义。

三个条件各自对应一种修复办法：

| 条件 | 打破它的办法 |
|---|---|
| 冲突 | 让线程访问不同的内存位置，或者都只读 |
| 至少一个不是原子操作 | 把对象改成 `std::atomic` 或用 `std::atomic_ref` 访问 |
| 没有 happens before | 用同步建立先后：互斥量、acquire/release、`join` 等 |

第一节的 relaxed 版本用第二种办法修好了 `ready`，但 `data` 仍然满足全部三个条件。正确版本用的是第三种。

数据竞争定为 UB，而不是规定成读到某个旧值，是为了让编译器保留单线程的优化：把变量放进寄存器、合并读、删掉看起来没用的循环。[[intro.races#17]] 的注 18 说明，没有数据竞争的程序看不出这些变换。代价是，有数据竞争的程序可能出现上面 `-O2` 那样的结果。UB 的一般后果见 [[topics/undefined-behavior]]。

## 一步一步搭出 happens before

判断两个访问之间有没有 happens before，要把一次执行画成一张图，节点是求值，边有两种。

### 第一种边：sequenced before

同一个线程内，[[g:sequenced-before|sequenced before]] 规定求值的先后（[[intro.execution#8]]）。最常用的一条是：一个完整表达式的所有计算和副作用，都 sequenced before 下一个完整表达式（[[intro.execution#9]]）。所以在 `mp.cpp` 里，A sequenced before B，C sequenced before D。

这是语言层面的顺序，与指令实际的执行顺序无关。编译器和处理器可以重排 A 和 B，只要单线程看不出区别。

### 第二种边：synchronizes with

线程之间的边叫 [[g:synchronizes-with|synchronizes with]]，只能由特定的库操作产生（[[intro.races#6]]）。原子操作上的规则是 [[atomics.order#2]]：release 操作 A 与 acquire 操作 B 同步，条件是两者作用于同一个原子对象，并且 B 读到了 A 写入的值（或者 A 之后的读-改-写写入的值，见下文的 release sequence）。

`store` 用 `release`、`acq_rel` 或 `seq_cst` 时是 release 操作；`load` 用 `acquire`、`acq_rel` 或 `seq_cst` 时是 acquire 操作（[[atomics.order#1]]）。`relaxed` 两者都不是。

三个条件缺一不可。尤其是最后一个：同步发生在一次执行中具体的两个操作之间，而不是两行代码之间。如果 C 读到的是初值 `false`，那次读与 B 没有任何关系。所以 acquire 读几乎总是出现在检查值的循环或分支里。

### 合起来：happens before

[[intro.races#7]] 把 [[g:happens-before|happens before]] 定义为这两种边的传递闭包：A happens before B，当且仅当 A sequenced before B，或 A 与 B 同步，或者存在 X，使 A happens before X 且 X happens before B。

```text
producer                     consumer
  A: data = 42
     │ sequenced before
  B: ready.store(true, release) ──synchronizes with──▶ C: ready.load(acquire) 读到 true
                                                          │ sequenced before
                                                       D: 读 data
```

沿箭头从 A 走到 D，所以 A happens before D。两个冲突的访问之间有了 happens before，不构成数据竞争。

### 读到哪个值

没有数据竞争之后，还要知道 D 读到什么。对非原子对象，[[intro.races#9]] 规定读到**可见副作用**的值：happens before 这次读、并且中间没有被另一个 happens before 这次读的写覆盖的那个写。A 是唯一满足条件的写，所以 D 读到 42。

原子对象不一样。[[intro.races#10]] 只要求原子读读到某个不 happens after 它的写，可以从多个候选中选一个，具体受下一节的一致性规则约束。这就是 relaxed 版本中 consumer 可以读到旧值 0 的原因。

!!! note "strongly happens before"
    标准还定义了一个更强的关系 [[g:strongly-happens-before|strongly happens before]]（[[intro.races#8]]）。它排除了经过 acquire/release 同步得到、而 seq_cst 的全序不必尊重的那部分 happens before。日常推理用 happens before 就够了；它出现在 `seq_cst` 的定义和 `latch`、`barrier`、信号量的同步条款中，细节见 [[intro.multithread]]。

## 修改顺序与一致性

每个原子对象 M 的所有修改构成一个全序，叫 M 的[[g:modification-order|修改顺序]]（[[intro.races#4]]）。所有线程看到的都是同一个顺序，但不同对象各有各的修改顺序，不要求能拼成一个全局的顺序。

[[intro.races#11]]–[[intro.races#14]] 的四条一致性规则把 happens before 和修改顺序绑在一起。归结起来就是：在同一个原子对象上，一个线程不会先看到新值、再看到旧值；happens before 在前的写，在修改顺序中也在前。即使全部用 relaxed，这些规则也成立。各条的精确表述和例子见 [[intro.multithread]]。

### relaxed 计数器

读-改-写操作（`fetch_add`、`exchange`、`compare_exchange_*` 等）还有一条额外的保证：它总是读修改顺序中紧挨在自己之前的那个值（[[atomics.order#11]]）。先 `load` 再 `store` 是两次独立的原子操作，没有这条保证：

```cpp run title="counter.cpp" ok
#include <atomic>
#include <cstdio>
#include <thread>
#include <vector>
std::atomic<long> a{0}, b{0};
int main() {
  {
    std::vector<std::jthread> ts;
    for (int t = 0; t < 4; ++t)
      ts.emplace_back([] {
        for (int i = 0; i < 1'000'000; ++i) {
          a.store(a.load(std::memory_order::relaxed) + 1,
                  std::memory_order::relaxed);      // 读和写是两次原子操作
          b.fetch_add(1, std::memory_order::relaxed);  // 一次读-改-写
        }
      });
  }                                                 // jthread 析构时 join
  std::printf("a = %ld\nb = %ld\n", a.load(), b.load());
}
```

本机三次运行，`a` 分别是 2542693、2388766、1246778，`b` 每次都是 4000000。`a` 丢掉的增量不是数据竞争，所以 TSan 对这个程序没有任何报告；这是逻辑错误，只能靠读-改-写避免。

`b` 用 relaxed 就够了，因为计数器本身不用来发布其他数据。主线程在 `join` 之后读最终值，`join` 提供了同步。

## 在真机上数结果

用标准推出一个结果是否允许之后，可以用 **litmus 测试**看硬件实际给出什么：把两个线程的几行代码运行很多次，统计每种结果出现的次数。下面的程序同时包含 MP 和下一节的 store buffering（SB）测试，用宏选择测试和内存序：

```cpp run title="litmus.cpp"
#include <atomic>
#include <cstdio>
#include <thread>
using std::memory_order;
#ifndef ST
#define ST relaxed                    // 写用的内存序
#endif
#ifndef LD
#define LD relaxed                    // 读用的内存序
#endif
constexpr auto st = memory_order::ST, ld = memory_order::LD;
constexpr int N = 1'000'000;

std::atomic<int> xs[N], ys[N];        // 每轮用一对新变量，初值都是 0
int r1[N], r2[N];
std::atomic<int> round{-1}, done{0};

#ifdef SB  // 存储缓冲：各写一个变量，再读另一个
void t0(int i) { xs[i].store(1, st); r1[i] = ys[i].load(ld); }
void t1(int i) { ys[i].store(1, st); r2[i] = xs[i].load(ld); }
bool weird(int i) { return r1[i] == 0 && r2[i] == 0; }
#else      // 消息传递：先写 x 再写 y；先读 y 再读 x
void t0(int i) { xs[i].store(1, st); ys[i].store(1, st); }
void t1(int i) { r1[i] = ys[i].load(ld); r2[i] = xs[i].load(ld); }
bool weird(int i) { return r1[i] == 1 && r2[i] == 0; }
#endif

void worker(void (*body)(int)) {
  for (int i = 0; i < N; ++i) {
    while (round.load(memory_order::acquire) != i) {}
    body(i);
    done.fetch_add(1, memory_order::release);
  }
}

int main() {
  std::thread a(worker, t0), b(worker, t1);
  for (int i = 0; i < N; ++i) {
    round.store(i, memory_order::release);
    while (done.load(memory_order::acquire) != 2 * (i + 1)) {}
  }
  a.join(); b.join();
  int count = 0;
  for (int i = 0; i < N; ++i) count += weird(i);
  std::printf("%d / %d\n", count, N);
}
```

这个程序本身没有数据竞争。每轮由主线程用 `round` 放行两个工作线程，工作线程做完后 `fetch_add` 一次 `done`。`r1[i]`、`r2[i]` 是普通变量，主线程能安全地读，是因为两次 `fetch_add` 都是读-改-写：第一次开头的 release sequence 被第二次延续，主线程的 acquire 读到最终值，就与两个工作线程都同步了（release sequence 见下文）。

用 `clang++ -O2 -DSB -DST=seq_cst -DLD=seq_cst` 这样的命令编译。下表是 Apple M2 Pro 上每种组合运行三次的结果，数字是每一百万轮中出现奇怪结果（MP 中 `r1 == 1 && r2 == 0`，SB 中 `r1 == r2 == 0`）的次数。x86-64 一列是用 Apple Clang 21 加 `-arch x86_64` 编译、由 Rosetta 2 转译运行的同一份代码：

| 测试 | 写 | 读 | arm64（Clang 23） | x86-64（Rosetta 2） |
|---|---|---|---|---|
| MP | `relaxed` | `relaxed` | 7956 ～ 42891 | 0 |
| MP | `release` | `relaxed` | 482 ～ 793 | 0 |
| MP | `relaxed` | `acquire` | 40 ～ 145 | 0 |
| MP | `release` | `acquire` | 0 | 0 |
| SB | `relaxed` | `relaxed` | 约 47 万 ～ 51 万 | 约 26 万 ～ 35 万 |
| SB | `release` | `acquire` | 约 35 万 ～ 38 万 | 约 24 万 ～ 38 万 |
| SB | `seq_cst` | `acquire` | 约 34 万 ～ 36 万 | 0 |
| SB | `release` | `seq_cst` | 0 | 约 33 万 ～ 38 万 |
| SB | `seq_cst` | `seq_cst` | 0 | 0 |

次数随机器负载变化，量级是稳定的。结果为 0 只说明这台机器上没出现，不说明标准禁止，下面两节逐行解释。

## acquire/release：消息传递需要两端

表中 MP 的四行对应同一个问题：t1 看到了 `y == 1`，能否保证也看到 `x == 1`？

- 两端都 relaxed：没有同步，标准允许 `r1 == 1 && r2 == 0`。arm64 上的汇编是两条 `str` 和两条 `ldr`，顺序与源码一致，奇怪结果来自处理器：AArch64 允许两次写以不同的顺序对其他核可见，也允许两次读乱序执行。
- 只有一端加强：写端 `release` 编译为 `stlr`，读端仍是 `ldr`，读可以乱序，问题依旧；反过来也一样。标准层面，同步需要 release 写和 acquire 读配对，缺一端就没有 synchronizes with。
- 两端配对：`stlr` 加 `ldapr`。y 的写是 release，y 的读是 acquire 且读到了 1，两者同步，x 的写 happens before x 的读，按一致性规则必须读到 1。

release 的含义是它之前的读写不能挪到它之后，acquire 的含义是它之后的读写不能挪到它之前。这是从实现角度的近似描述，标准里的定义只有上一节的同步边。用同步边推理更可靠，尤其是涉及三个以上线程时：

```cpp run title="chain.cpp" ub
#include <atomic>
#include <cstdio>
#include <thread>
int data = 0;
std::atomic<int> a{0}, b{0};
int main() {
  std::jthread t1([] { data = 42; a.store(1, std::memory_order::release); });
  std::jthread t2([] {
    while (a.load(std::memory_order::acquire) == 0) {}
    b.store(1, std::memory_order::relaxed);    // 应当是 release
  });
  std::jthread t3([] {
    while (b.load(std::memory_order::acquire) == 0) {}
    std::printf("%d\n", data);   // UB：与 data = 42 之间没有 happens before
  });
}
```

t1 与 t2 同步，但 t2 写 `b` 用的是 relaxed，t2 与 t3 之间没有同步边，链条在这里断了。TSan 每次都报告 `data` 上的竞争；把 `b.store` 改成 `release` 后不再报告。happens before 可以传递，但每一段都要有边。

## seq_cst：单一全序与 store buffering

SB 测试中两个线程各写一个变量、再读另一个：

```cpp
// x、y 初值为 0
// t0：                      // t1：
x.store(1);                  y.store(1);
r1 = y.load();               r2 = x.load();
```

把四个操作随意交错，总有一个 store 先执行，`r1 == r2 == 0` 不可能出现。但硬件上每个核都有存储缓冲区（store buffer）：store 先放进缓冲区，之后才对其他核可见，而后面的 load 不必等它。两个核的 load 都读到对方还没提交的旧值，就得到 `0, 0`。

### 为什么 acquire/release 不够

release 只约束它之前的操作，acquire 只约束它之后的操作。`store(release)` 后接 `load(acquire)`，正好落在两者都不管的缺口里。从同步边的角度看也一样：两个 load 都读到初值，没有读到任何 release 写，一条同步边都没有，标准对 `r1`、`r2` 没有任何限制。表中 `release` / `acquire` 一行在两种架构上都出现了几十万次。

### seq_cst 多了什么

所有 `seq_cst` 操作处于一个单一全序 S 中，S 与每个原子对象的修改顺序一致（[[atomics.order#4]]）。四个操作都是 seq_cst 时，假设两个 load 都读到 0：y 的 load 读到 y 的初值，它在 S 中必须排在 `y.store(1)` 之前；x 的 load 同理排在 `x.store(1)` 之前；而每个线程内 store 又排在 load 之前，S 中形成一个环，矛盾。所以 `0, 0` 被禁止。完整的推导见 [[intro.multithread]] 的存储缓冲一节。

### 只有一端是 seq_cst

表中最有意思的是中间两行：

- 写 `seq_cst`、读 `acquire`：x86-64 上 0 次，arm64 上几十万次。
- 写 `release`、读 `seq_cst`：arm64 上 0 次，x86-64 上几十万次。

这两种组合标准都允许 `0, 0`：只有 seq_cst 操作进入 S，另一半不受 S 约束（[[atomics.order#7]] 的注 4 说，用了任何较弱的内存序，顺序一致性的保证就失效了）。两种硬件各自恰好挡住了其中一种：

| 操作 | x86-64 | AArch64 |
|---|---|---|
| store `release` | `mov` | `stlr` |
| store `seq_cst` | `xchg` | `stlr` |
| load `acquire` | `mov` | `ldapr` |
| load `seq_cst` | `mov` | `ldar` |

x86-64 把 seq_cst 的代价放在 store 上，`xchg` 会等存储缓冲区清空；AArch64 把代价放在 load 上，`ldar` 不会越过同一线程更早的 `stlr`，而 `ldapr` 会。所以只在一端写 seq_cst 的代码，在一种平台上测试总是通过，换到另一种平台就出错。需要先写后读顺序的算法（Dekker、Peterson、SB 形式的握手），两端都要用 `seq_cst`。

## 栅栏

栅栏（fence）把同步从具体的原子操作上拆下来：`std::atomic_thread_fence(release)` 放在一次 relaxed 写之前，`atomic_thread_fence(acquire)` 放在一次 relaxed 读之后，只要读读到了那次写的值，两个栅栏就同步（[[atomics.fences#2]]）。栅栏与原子操作也可以混合配对（[[atomics.fences#3]]、[[atomics.fences#4]]）。一个 acquire 栅栏可以为它前面的多次 relaxed 读一起提供 acquire 语义，用法见 [[atomics.fences]]。

SB 测试也可以用栅栏修复，但栅栏必须是 `seq_cst`：

<div class="compare" markdown="1">

```cpp
// 不够：标准允许 r1 == r2 == 0
x.store(1, relaxed);
atomic_thread_fence(acq_rel);
r1 = y.load(relaxed);
```

```cpp
// 够了：0, 0 被禁止
x.store(1, relaxed);
atomic_thread_fence(seq_cst);
r1 = y.load(relaxed);
```

</div>

`acq_rel` 栅栏同样有上一节的缺口，而且这里的 load 没读到对方的写，栅栏之间也没有同步边。`seq_cst` 栅栏进入全序 S，[[atomics.order#4]] 的 ¶4.4 让两个栅栏在 S 中的先后约束两边的 relaxed 操作，推出与上一节一样的矛盾。

实测结果又一次因平台而异。`acq_rel` 栅栏版本在 x86-64（Rosetta 2）上每百万次出现三十多万次 `0, 0`，在 arm64 上一次也没有，因为本机 Clang 23 把 `acq_rel` 栅栏和 `seq_cst` 栅栏都编译成 `dmb ish`，而 x86-64 上 `acq_rel` 栅栏不生成任何指令。`seq_cst` 栅栏版本在两边都是 0 次。

## release sequence 与读-改-写：引用计数

多个线程共享一个对象，每个线程用完后把引用计数减一，减到零的线程负责销毁。销毁者要读其他线程在释放引用之前写入的数据：

```cpp run title="refcount.cpp" ok
#include <atomic>
#include <cstdio>
#include <thread>
#include <vector>
struct Obj {
  std::atomic<int> refs{4};
  int log[4] = {};
};
void release_ref(Obj* p, int id) {
  p->log[id] = id + 1;                               // 释放引用前写对象
  if (p->refs.fetch_sub(1, std::memory_order::acq_rel) == 1) {
    int sum = 0;
    for (int v : p->log) sum += v;                   // 读其他线程的写
    std::printf("sum = %d\n", sum);
    delete p;
  }
}
int main() {
  Obj* p = new Obj;
  std::vector<std::jthread> ts;
  for (int i = 0; i < 4; ++i) ts.emplace_back(release_ref, p, i);
}
```

最后一个线程只与读到的那个值的写入者直接相邻，它怎么与另外两个更早的线程同步？靠 [[g:release-sequence|release sequence]]（[[intro.races#5]]）：以 release 操作 A 开头、在修改顺序中紧随其后的一串读-改-写，都算 A 的 release sequence。acquire 读读到这串中任何一个值，都与 A 同步（[[atomics.order#2]]）。四次 `fetch_sub` 都是读-改-写，每一次都开启一个 release sequence，并被后面的 `fetch_sub` 延续，所以最后那次的 acquire 一半与前面每一次都同步。

本机 TSan 对这个版本没有报告。把内存序改成 `release` 或 `relaxed`，减到零的那次读不再是 acquire，TSan 每次都报告 `log` 上的竞争。

常见的另一种写法是 `fetch_sub(1, release)`，减到零之后再执行 `atomic_thread_fence(acquire)`，只在最后一次付出 acquire 的代价，按 [[atomics.fences#4]] 同样正确。本机 Clang 23 的 TSan 不理解独立的栅栏，会把这种写法误报为数据竞争。

只有读-改-写能延续 release sequence。C++20 之前，同一线程在 A 之后的普通原子写也能延续它，[[P0982R1]] 去掉了这一点，[[intro.multithread]] 的思考题 1 给出了受影响的代码。

## consume 去哪了

`memory_order::consume` 原本想用数据依赖代替 acquire：读到一个指针后，只有通过这个指针的访问才被排序，在 ARM、POWER 上可以省掉屏障。编译器无法在优化中可靠地保持源码层面的依赖，于是都把它当 `acquire` 实现。C++26 的 [[P3475R2]] 把它移到附录 D（[[depr.atomics.order#1]]），含义与 `acquire` 相同 {{deprecated}}。新代码直接写 `acquire`。来龙去脉见 [[history/threads-and-memory-model]]。

## lock-free、wait 与 notify

无锁（lock-free）说的是进度保证，不是内存序。`std::atomic<T>` 对任何可平凡复制的 `T` 都可用，硬件没有足够宽的原子指令时，实现会用锁模拟，这样的操作可能阻塞（[[atomics.lockfree#4]]）。但它的内存序语义与无锁实现完全一样，上面的推理方法照样适用。是否无锁影响的是能否在信号处理函数里使用、能否跨进程共享（[[atomics.lockfree]]），以及 [[intro.progress#2]] 的进度保证。

`wait` 和 `notify` 让等待一方不必空转。同步仍然来自写和读：

```cpp run title="wait.cpp" ok
#include <atomic>
#include <cstdio>
#include <thread>
int data = 0;
std::atomic<bool> ready{false};
int main() {
  std::jthread consumer([] {
    ready.wait(false, std::memory_order::acquire);   // 值仍是 false 就阻塞
    std::printf("%d\n", data);
  });
  data = 42;
  ready.store(true, std::memory_order::release);   // 同步来自这次写和 wait 内部的读
  ready.notify_one();                              // 只负责唤醒
}
```

`wait(old, order)` 的效果是反复以 `order` 执行 `load`，值与 `old` 不同就返回，相同就阻塞（[[atomics.types.operations#31]]）。返回前的那次 acquire `load` 读到了 release `store` 的值，同步就是这样建立的。`notify_one` 没有内存序参数，也不带来任何可见性。把两处内存序都改成 relaxed，TSan 每次都报告 `data` 上的竞争。唤醒规则的细节见 [[atomics.wait]]。

## 标准库设施提供的同步

大多数代码不直接写内存序，而是用标准库的同步设施。它们的条款里都有 *Synchronization* 一项，说明自己往 happens before 图里加了哪些边：

| 设施 | 加的边 | 条款 |
|---|---|---|
| `std::thread`、`std::jthread` 构造 | 构造函数完成 → 新线程函数开始 | [[thread.thread.constr#7]]、[[thread.jthread.cons#7]] |
| `join()` | 线程结束 → `join` 返回 | [[thread.thread.member#4]] |
| 互斥量 | 每次 `unlock` → 之后获得所有权的 `lock` | [[thread.mutex.requirements.mutex.general#8]]、[[thread.mutex.requirements.mutex.general#24]] |
| `try_lock` | 只有返回 `true` 时才同步 | [[thread.mutex.requirements.mutex.general#16]] |
| `std::call_once` | 执行了函数的那次调用 → 所有其他调用的返回 | [[thread.once.callonce#3]] |
| `std::promise`/`std::future` | 设置结果 → 等待函数成功返回 | [[futures.state#9]] |
| `std::latch` | 每次 `count_down` strongly happens before 被解除阻塞的调用的返回 | [[thread.latch#9]] |
| `std::barrier` | 完成步骤的结束 strongly happens before 被解除阻塞的调用的返回 | [[thread.barrier.class#3]] |
| `std::counting_semaphore` | `release` strongly happens before 观察到其结果的 `try_acquire` | [[thread.sema.cnt#10]] |
| `sleep_for`、`yield` | 无 | [[thread.thread.this]] |

条件变量没有单独的同步条款，它的同步来自配套的互斥量：`wait` 返回前重新获得锁，与通知方之前的 `unlock` 同步。函数内的静态局部变量初始化，[[stmt.dcl#3]] 规定并发进入的线程要等初始化完成，实践中可以当作完成初始化与等待者之间有同步。

有了这张表，很多问题不用碰内存序就能回答：

```cpp run title="latch.cpp" ok
#include <cstdio>
#include <latch>
#include <thread>
#include <vector>
int main() {
  constexpr int n = 4;
  int results[n] = {};                     // 普通数组，没有原子
  std::latch done(n);
  std::vector<std::jthread> ts;
  for (int i = 0; i < n; ++i)
    ts.emplace_back([&, i] {
      results[i] = i * i;                  // 各写各的元素
      done.count_down();
    });
  done.wait();
  int sum = 0;
  for (int r : results) sum += r;
  std::printf("%d\n", sum);
}
```

每个工作线程写 `results[i]` sequenced before 自己的 `count_down`，`count_down` strongly happens before `wait` 的返回，`wait` 返回 sequenced before 主线程读数组。工作线程之间写的是不同元素，属于不同的内存位置，不冲突。

<details class="fine" markdown="1"><summary>latch 条文的一处字面空隙</summary>

[[thread.latch#9]] 的措辞是 `count_down` strongly happens before 被解除阻塞的调用（calls that are unblocked）的返回。如果主线程调用 `wait` 时计数已经是 0，按 [[thread.latch#13]]，`wait` 直接返回，并没有被解除阻塞，条文的字面没有覆盖这种情况。显然的意图是两种情况都同步；本机 libc++ 的 `wait` 无论哪种情况都以 acquire 读计数器，`count_down` 是 release 的 `fetch_sub`，所以实际行为没有问题。

</details>

## 常见错误

!!! pitfall "volatile 当作原子"
    ```cpp
    volatile long hits = 0;
    // 两个线程各执行一百万次：
    hits = hits + 1;   // UB：数据竞争
    ```
    本机两次运行的结果是 1053997 和 1509420，TSan 报告数据竞争。`volatile` 只保证每次访问都真的执行（[[intro.abstract]]），不提供原子性，也不建立 happens before。把它用在消息传递上也不行：把 litmus 测试中的 `xs`、`ys` 换成 `volatile int`，arm64 上每百万轮仍出现一到两万次奇怪结果。`volatile` 唯一的线程相关用途是同一线程内与信号处理函数通信的 `volatile std::sig_atomic_t`（[[intro.races#18]]）。

!!! pitfall "双重检查锁定用错内存序"
    ```cpp
    std::atomic<Config*> instance{nullptr};
    std::mutex m;
    Config* get() {
      Config* p = instance.load(std::memory_order::acquire);  // 不能是 relaxed
      if (p == nullptr) {
        std::lock_guard lock(m);
        p = instance.load(std::memory_order::relaxed);  // 锁内，relaxed 即可
        if (p == nullptr) {
          p = new Config;
          instance.store(p, std::memory_order::release);    // 不能是 relaxed
        }
      }
      return p;
    }
    ```
    锁外的第一次检查读到非空指针时，没有经过互斥量，只能靠 release 写和 acquire 读同步，才能看到 `Config` 构造函数写入的成员。两处都改成 relaxed 后，本机 TSan 每次都报告构造函数中的写与另一个线程读 `port` 之间的竞争。更简单的做法是函数内的静态局部变量或 `std::call_once`，它们的同步由实现负责。

!!! pitfall "relaxed 标志加普通数据"
    第一节的 `mp-relaxed-flag.cpp` 就是这种错误。读到新值不等于看到写入者之前的写，[[intro.races#6]] 的注 5 明确说了这一点。标志用来发布数据时，写端用 `release`，读端用 `acquire`。

!!! pitfall "在 x86 上测试通过就认为正确"
    x86-64 的硬件内存模型是全存储序（TSO），只允许后面的 load 越过前面的 store，所以 relaxed 的 MP 在 Rosetta 2 下一百万次都是 0。同一份源码编译成 arm64，每百万次出错上万次。另一方面，x86 上 acquire/release 的 load 和 store 都只是普通的 `mov`，编译器仍可以在编译期按标准允许的范围重排 relaxed 操作，所以即使只面向 x86，按 C++ 内存模型写代码也是必要的。上面 SB 测试的两行也说明，arm64 同样会掩盖一些 x86 上暴露的错误。最可靠的是按标准推理，再用 TSan 和多种平台的测试检查。

!!! pitfall "用 sleep 等待另一个线程"
    `sleep_for` 和 `yield` 都不提供同步（[[thread.thread.this#8]]）。第一节的 TSan 报告中，`As if synchronized via sleep` 正是在提示这个问题。

## 思考题

!!! question "1. 下面的代码用 seq_cst 写、acquire 读实现两个线程的握手，能保证 r1、r2 不同时为 0 吗？"
    ```cpp
    // t0：                                 // t1：
    x.store(1, memory_order::seq_cst);      y.store(1, memory_order::seq_cst);
    r1 = y.load(memory_order::acquire);     r2 = x.load(memory_order::acquire);
    ```

<details markdown="1">
<summary>答案</summary>

不能。全序 S 只包含 seq_cst 操作，两个 acquire load 不在 S 中，[[atomics.order#4]] 推不出矛盾，标准允许 `0, 0`。在 x86-64 上，seq_cst store 编译为 `xchg`，会清空存储缓冲区，所以测不出问题；在 arm64 上，store 是 `stlr`，acquire load 是 `ldapr`，后者可以越过前者，上文的实测中每百万次出现约 35 万次。两个 load 也要改成 seq_cst。
</details>

!!! question "2. 一个线程 `x.store(1, relaxed)`，另一个线程 `x.load(relaxed)` 读到了 1。之后第二个线程再 relaxed 读一次 x，可能读到 0 吗？"

<details markdown="1">
<summary>答案</summary>

不能。两次读在同一线程中，前一次 sequenced before 后一次，所以 happens before 后一次。按读-读一致性（[[intro.races#12]]），后一次读到的值必须等于前一次读到的值，或在修改顺序中更晚。修改顺序是 0、1，读到 1 之后不会再读到 0。一致性规则对 relaxed 操作同样成立。
</details>

!!! question "3. 用 `std::mutex` 保护的代码里，可以把共享的 `int` 换成 relaxed 原子吗？反过来，两个线程分别在加锁和不加锁的情况下访问同一个 `int` 呢？"

<details markdown="1">
<summary>答案</summary>

第一种可以，但没有必要。每次 `unlock` 与之后的 `lock` 同步（[[thread.mutex.requirements.mutex.general#8]]），所有在锁内的访问之间都有 happens before，普通 `int` 已经没有数据竞争。

第二种是数据竞争。互斥量只在两个线程都加锁时才提供同步边；一个线程不加锁就访问，它的访问与另一个线程锁内的写之间没有 happens before。只有一方加锁，等于没有加锁。
</details>

## 小结

| 需要 | 做法 |
|---|---|
| 在线程之间传递普通数据 | 互斥量、`join`、`latch`、`future` 等库设施；自己实现时用 release 写配 acquire 读 |
| 只统计一个数，不用它发布其他数据 | relaxed 的读-改-写（`fetch_add`） |
| 先写自己的标志、再读对方的标志 | 两端都用 `seq_cst`，或在中间放 `seq_cst` 栅栏 |
| 一次同步覆盖多个 relaxed 操作 | release 栅栏 / acquire 栅栏 |
| 引用计数归零后销毁对象 | `fetch_sub(acq_rel)`，或 `release` 加归零后的 acquire 栅栏 |
| 等待一个值变化而不空转 | `wait(old, acquire)` 配 release 写和 `notify` |
| 检查自己的推理 | 按 happens before 画图；TSan 查数据竞争；在多种架构上跑 litmus 测试 |
