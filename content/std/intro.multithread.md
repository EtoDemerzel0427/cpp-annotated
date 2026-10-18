---
title: 多线程执行与数据竞争
summary: C++ 内存模型的形式定义：线程、冲突、修改顺序、release sequence、synchronizes-with、happens-before、四条一致性规则，以及"数据竞争即 UB"
status: draft
covers: intro.multithread.general, intro.races
papers: P0668R5, P0982R1
related: intro.execution, intro.progress, intro.memory, atomics.order, atomics.fences, thread.mutex.requirements
tags: 内存模型, 并发, 原子操作, UB
updated: 2026-10-17
---

这一节是 C++ **内存模型**（memory model）的核心。它不是在描述硬件，而是定义一组**关系**——sequenced before、synchronizes with、happens before、modification order、coherence——然后用这些关系回答两个问题：

1. 一次读取**可能**读到哪些写入的值？（第 9–16 段）
2. 什么样的程序有**数据竞争**，从而整个程序行为未定义？（第 17 段）

所有原子操作的 `memory_order` 语义（[[atomics.order]]）、互斥量的语义（[[thread.mutex.requirements]]）、栅栏（[[atomics.fences]]）都是往这些关系里"添边"。不理解本节，就只能背"acquire 配 release"的口诀；理解了本节，就能对任何一个并发程序画出关系图，指着段落说它为什么正确。

读前需要：[[intro.execution]]（sequenced before 的定义）和 [[intro.memory]]（**内存位置** memory location：一个标量对象，或一串相邻的非零宽位域）。

!!! note "本页结构"
    6.10.2 由三个三级条款组成：[[intro.multithread.general]]（线程的概念）、[[intro.races]]（数据竞争，本页主体）、[[intro.progress]]（前进保证，单独成页）。本页的段落号 ¶N 默认指 [[intro.races]]，指 general 的段落时会写明。

## 线程（intro.multithread.general）

[[intro.multithread.general#1]] **执行线程**（thread of execution，简称线程）是程序中的单一控制流：从某个顶层函数的初始调用开始，递归地包括该线程随后执行的每一次函数调用。注 1：一个线程创建另一个线程时，新线程顶层函数的初始调用**由新线程执行**，不由创建者执行。

几个要点：

- 每个线程都**可能**使用程序中的每个对象和函数。脚注补充：自动或线程存储期的对象与某个特定线程关联，其他线程只能通过指针或引用**间接**访问它。
- 宿主实现（hosted）中程序可以有多个线程并发运行；**独立实现**（freestanding）中是否支持多线程由实现定义 {{impl}}。
- 程序的执行由其所有线程的执行组成。注 2：通常可以把执行看作所有线程的**交错**（interleaving），但某些原子操作允许出现**与任何简单交错都不一致**的执行——这就是 relaxed/acquire/release 原子操作的"怪异"结果的来源，下文详述。

[[intro.multithread.general#2]] 不是由 `std::raise` 触发的信号处理函数，由哪个线程执行是未指定的 {{unspec}}。

## 一次读取能看到什么（¶1）

¶1 一个线程 T 在某一点能看到的对象值，是对象的初值、T 自己写入的值、或其他线程写入的值——"按下面的规则"。注 1 坦承：有些情况下结果是未定义行为；本节大部分内容是为了支持精细控制可见性的原子操作，但它也**隐含地**支持一个更简单的视角——只用互斥量和 `seq_cst` 原子量的程序，可以当成简单交错来理解（注 18 的 SC-DRF 定理）。

## 冲突（¶2）

¶2 两个求值**冲突**（conflict），当其中一个

- ¶2.1 修改（[[defns.access]]）某个内存位置，或
- ¶2.2 在某内存位置开始或结束对象的生命周期，

而另一个

- ¶2.3 读或修改同一内存位置，或
- ¶2.4 在与该位置重叠的存储中开始或结束对象的生命周期。

注 2：**即使修改没有改变任何位**，也算冲突。`x = x;` 与另一线程的读取是冲突的。

"内存位置"的粒度决定了什么算冲突：

```cpp run title="memloc.cpp" ok
#include <thread>
struct S {
  char a;
  int b : 5;
  int c : 11, : 0, d : 8;   // 零宽位域把 c 与 d 分到不同内存位置
  struct { int ee : 8; } e;
};
S s;
int main() {
  // a、(b 与 c)、d、e.ee 是四个不同的内存位置
  std::thread t1([] { s.a = 1; s.d = 2; });
  std::thread t2([] { s.b = 3; s.e.ee = 4; });   // 与 t1 不冲突：没有数据竞争
  t1.join(); t2.join();
}
```

但若 t1 写 `s.b`、t2 写 `s.c`，二者在同一内存位置（相邻非零宽位域），即使是"不同的成员"也构成冲突——没有同步就是数据竞争。这个例子改编自 [[intro.memory]] 的标准例。

## 同步操作（¶3）

¶3 标准库把一些原子操作（[[atomics]]）和互斥量操作（[[thread]]）标记为**同步操作**（synchronization operation），它们负责让一个线程的赋值对另一个线程可见。分类：

| 种类 | 有关联内存位置？ | 例子 |
|---|---|---|
| acquire 操作 | 是 | `load(acquire)`、`mutex::lock()` |
| release 操作 | 是 | `store(release)`、`mutex::unlock()` |
| acquire + release | 是 | `fetch_add(acq_rel)`、`exchange(seq_cst)` |
| 栅栏（fence） | **否** | `atomic_thread_fence(acquire/release/acq_rel/seq_cst)` |
| relaxed 原子操作 | 是 | `load(relaxed)` —— **不是**同步操作，但也不参与数据竞争 |
| 原子读-改-写（RMW） | 是 | `fetch_add`、`compare_exchange_*`、`exchange` —— 有特殊性质 |

注 3：获取互斥量是在构成互斥量的位置上执行 acquire 操作，释放互斥量执行 release 操作。非正式地说，在 A 上执行 release 操作，会迫使该线程**之前**对**其他**内存位置的副作用，对随后在 A 上执行 acquire 操作的线程可见。

## 修改顺序（¶4）

¶4 对每个原子对象 M，**所有修改**构成一个全序，称为 M 的**修改顺序**（modification order）。注 4：每个原子对象各有一个；**不要求**它们能合并成所有对象的单一全序——一般而言不可能，因为不同线程可能以不一致的顺序观察到对不同对象的修改（见下文 IRIW）。

直觉：修改顺序对应硬件的**缓存一致性**——对同一缓存行的写入在一致性协议中总有一个先后。不同地址之间则没有这样的全局顺序。

## release sequence（¶5）

¶5 以原子对象 M 上的 release 操作 A 为首的 **release sequence**，是 M 的修改顺序中一个**极大的连续子序列**：第一个是 A，之后每个都是原子**读-改-写**操作。

它解决的问题：一个线程 `store(release)`，若干线程随后 `fetch_add(relaxed)`，最后某个线程 `load(acquire)` 读到的是某次 `fetch_add` 写入的值——它与最初的 release 还同步吗？答案是同步：只要读到的值来自以 A 为首的 release sequence 中的任何副作用，就与 A 同步（[[atomics.order#2]]）。这正是引用计数、"最后一个完成者"模式依赖的保证。

```cpp run title="release-seq.cpp" ok
#include <atomic>
#include <cassert>
#include <thread>
int payload = 0;
std::atomic<int> flag{0};
int main() {
  std::thread prod([] {
    payload = 42;
    flag.store(1, std::memory_order::release);       // A：release sequence 之首
  });
  std::thread mid([] {
    int expected = 1;
    while (!flag.compare_exchange_weak(expected, 2, std::memory_order::relaxed))
      expected = 1;                                   // RMW：加入 A 的 release sequence
  });
  std::thread cons([] {
    while (flag.load(std::memory_order::acquire) != 2) {}   // 读到 RMW 写的 2
    assert(payload == 42);   // OK：仍与 A 同步
  });
  prod.join(); mid.join(); cons.join();
}
```

!!! history "C++20 削弱了 release sequence"
    C++11 的定义里，release sequence 还包括**同一线程**在 A 之后执行的（非 RMW 的）原子写。这条几乎没人使用，却给实现和形式化带来负担，C++20 通过 [[P0982R1]] 将其删除。现在只有 RMW 能延续 release sequence。

## synchronizes with（¶6）

¶6 某些库调用会与另一线程执行的库调用**同步**（synchronize with）。例如原子的 store-release 与读到该 store 值的 load-acquire 同步。精确条件在库条款中：

- 原子操作：[[atomics.order#2]]——release 操作 A 与"对同一对象执行 acquire 操作并从 A 为首的 release sequence 中取值"的操作同步；
- 栅栏：[[atomics.fences]] ¶2–¶4——release 栅栏与 acquire 栅栏、栅栏与原子操作之间的同步；
- 互斥量：同一个 mutex 上的所有操作构成单一全序，每次加锁"读到"上一次解锁"写入的值"（注 6），所以 unlock 与下一次 lock 同步；
- 线程：`std::thread` 构造函数的完成与新线程函数的开始同步，线程结束与 `join` 返回同步（[[thread.thread.constr]]、[[thread.thread.member]]）。

注 5：除特别指定的情形外，"读到一个更新的值"**不一定**意味着可见性。relaxed load 读到了 release store 写的值？不同步。这样规定是因为强制同步会妨碍高效实现。

## happens before（¶7）

¶7 求值 A [[g:happens-before|**happens before**]] 求值 B，当且仅当

- ¶7.1 A sequenced before B，或
- ¶7.2 A synchronizes with B，或
- ¶7.3 存在 X，A happens before X 且 X happens before B。

换句话说，happens before 是"线程内顺序"与"跨线程同步边"的并集的**传递闭包**。注 7：求值不会 happens before 自己（关系是非自反的，因此也无环）。

```
线程 1                              线程 2
data = 42;           (A)
   │ sequenced before
   ▼
ready.store(true, release); (B) ── synchronizes with ──▶ ready.load(acquire) == true (C)
                                                            │ sequenced before
                                                            ▼
                                                         assert(data == 42);  (D)

A → B → C → D：A happens before D
```

!!! history "consume 与 dependency-ordered before 的消失"
    C++11 到 C++23 的 happens before 定义要复杂得多：有 **carries a dependency**、**dependency-ordered before**、**inter-thread happens before**，C++20 又加了 **simply happens before**。这些都是为 `memory_order::consume` 服务的——它想让"数据依赖"代替 acquire 栅栏，在 ARM/POWER 上省掉一条屏障指令。
    但"依赖"在源码层面极难跟踪（编译器优化会消除依赖），所有主流编译器实际上都把 consume 当 acquire 实现。C++26 草案中，consume 相关的关系已从本节删除，`memory_order::consume` 被移入附录 D（[[depr.atomics.order]]）{{deprecated}}，语义与 `acquire` 相同。于是 happens before 回归为上面三行的简单定义（C++20/23 中"simply happens before"的内容）。
    这一变化来自 P3475（"Defang and deprecate memory_order::consume"）。注 3 中仍残留了"consume or acquire"的措辞。

## strongly happens before（¶8）

¶8 A **strongly happens before** D，若

- ¶8.1 A sequenced before D，或
- ¶8.2 A synchronizes with D，**且 A 和 D 都是顺序一致（seq_cst）的原子操作**，或
- ¶8.3 存在 B、C：A sequenced before B，B happens before C，C sequenced before D，或
- ¶8.4 存在 B：A strongly happens before B，B strongly happens before D。

注 8：非正式地说，若 A strongly happens before B，则 A **在所有上下文中**都看起来先于 B 求值。

为什么需要两个"happens before"？因为 [[atomics.order#4]] 要求所有 `seq_cst` 操作构成单一全序 S，并要求 S 与 strongly happens before 一致——但**不**要求 S 与 happens before 一致（[[atomics.order#6]] 注 3）。原因是在 POWER 等架构上，把 acquire/release 与 seq_cst 混用时，常用的映射方案（leading-sync / trailing-sync）无法保证 S 与包含 acquire/release 同步边的 happens before 一致。C++20 的 [[P0668R5]] 承认了这一现实，重新定义了 strongly happens before（这个术语在 C++17 中已为描述初始化顺序而出现），让它成为"真正能被 S 尊重的那部分 happens before"，并让 S 只需与它一致。

对比 ¶8.2 与 ¶7.2：通过 acquire/release 同步得到的边，只在**两端都是 seq_cst** 时才直接计入"强"关系；¶8.3 允许中间夹一段普通 happens before，但两头必须是 sequenced before。

本节之外，strongly happens before 被用于：静态初始化先于动态初始化（[[basic.start.static#2]]）、非局部变量初始化的顺序（[[basic.start.dynamic#3]]）、终止时析构的顺序（[[basic.start.term]]）——这些地方要求的是"在任何观察者看来都成立"的顺序。

## 非原子对象的值：可见副作用（¶9）

¶9 标量对象或位域 M 上的副作用 A，相对于 M 的值计算 B 是**可见副作用**（visible side effect），若

- ¶9.1 A happens before B，且
- ¶9.2 不存在 M 上的另一个副作用 X，使 A happens before X 且 X happens before B。

**非原子**标量对象 M 被 B 求得的值，就是可见副作用 A 存入的值。

注 9：若对非原子对象可见的副作用有歧义（例如两个写都 happens before 读，但二者之间没有 happens before——这本身就是数据竞争），行为未指定或未定义。注 10：这条规则说明普通对象的操作**不会被可见地重排**——在没有数据竞争的程序里根本观察不到重排；这是让"数据竞争"的定义与"简单交错执行中的竞争"相对应所必需的。

## 原子对象的值（¶10）

¶10 原子对象 M 被 B 求得的值，是**某个未指定的**修改 M 的副作用 A 存入的值，其中 B 不 happens before A。

与 ¶9 对比：非原子读只能读"那一个"可见副作用；原子读可以读修改顺序中的多个候选之一——不一定是"最新的"。注 11：候选集合被下面的一致性规则进一步约束。

## 四条一致性规则（¶11–¶16）

对单个原子对象 M，happens before 与修改顺序之间必须相容：

| 段落 | 名称 | 若… | 则… |
|---|---|---|---|
| ¶11 | 写-写一致性（write-write coherence） | 修改 A happens before 修改 B | A 在 M 的修改顺序中早于 B |
| ¶12 | 读-读一致性（read-read coherence） | 读 A happens before 读 B，A 读到 X 写的值 | B 读到 X 或修改顺序中 X 之后的值 |
| ¶13 | 读-写一致性（read-write coherence） | 读 A happens before 修改 B | A 读到的值来自修改顺序中 B 之前的某个副作用 |
| ¶14 | 写-读一致性（write-read coherence） | 修改 X happens before 读 B | B 读到 X 或修改顺序中 X 之后的值 |

¶15 注 16：这四条实际上**禁止编译器对同一对象的原子操作重排**，即使两个都是 relaxed load——它把大多数硬件提供的缓存一致性保证带到了 C++ 层面。

```cpp run title="corr.cpp" ok
#include <atomic>
#include <cassert>
#include <thread>
std::atomic<int> x{0};
int main() {
  std::thread w([] { x.store(1, std::memory_order::relaxed); x.store(2, std::memory_order::relaxed); });
  std::thread r([] {
    int a = x.load(std::memory_order::relaxed);
    int b = x.load(std::memory_order::relaxed);
    assert(!(a == 2 && b == 1));   // 读-读一致性：读到 2 之后不可能再读到更早的 1
    assert(!(a > 0 && b == 0));    // 同理：0 是初始化，在修改顺序最前
  });
  w.join(); r.join();
}
```

¶16 注 17 讨论了一个看似循环的定义：原子 load 读到的值取决于 happens before，而 happens before（通过同步边）又取决于 load 读到了什么值。标准的意图是：**存在**一种"每个 load 读哪个写"的对应关系，连同适当选择的修改顺序和由此导出的 happens before，满足上述所有约束——这就是一次合法执行。这正是形式化工具（如 herd7、CDSChecker）所采用的"候选执行 + 一致性检查"的思路。

## 数据竞争（¶17）

¶17 两个动作**潜在并发**（potentially concurrent），若

- ¶17.1 它们由不同线程执行，或
- ¶17.2 它们无序、至少一个由信号处理函数执行，且二者不是由同一次信号处理函数调用执行的。

程序的一次执行包含[[g:data-race|**数据竞争**]]（data race），若它包含两个潜在并发的冲突动作，至少一个不是原子的，且**二者之间没有 happens before**（信号处理函数的特例见 ¶18 除外）。任何数据竞争都导致未定义行为 {{ub}}。

!!! std
    The execution of a program contains a data race if it contains two potentially concurrent conflicting actions, at least one of which is not atomic, and neither happens before the other […]

三个要点：

1. **两个都是原子操作就不会有数据竞争**，即便都是 relaxed。relaxed 只是不提供同步，不会导致 UB。
2. 判断标准是**某次执行**是否包含竞争。若程序的某个合法执行包含数据竞争，则对该输入整个程序 UB——包括竞争"发生"之前的部分（参见 [[intro.abstract]] 中"已定义前缀"的规定：数据竞争造成的 UB 发生在所有参与的线程上）。
3. 只有"冲突"才算——两个都只读不算。

```cpp run title="race.cpp" ub
#include <thread>
int counter = 0;
int main() {
  std::thread t([] { ++counter; });
  ++counter;          // UB：与 t 中的 ++counter 冲突、潜在并发、无 happens before
  t.join();
  return counter;
}
```

用 `-fsanitize=thread` 编译运行，ThreadSanitizer 会报告 "data race"。修复方法是把 `counter` 改为 `std::atomic<int>`，或用 mutex 保护。

!!! summary "注 18：SC-DRF"
    只用 mutex 和 `memory_order::seq_cst` 原子操作消除所有数据竞争、且不使用其他同步操作的程序，其行为如同各线程的操作被**简单交错**执行，每次读取都取交错中该对象最后一次写入的值——即**顺序一致性**（sequential consistency）。这个"无数据竞争则顺序一致"（SC for DRF）保证是 C++ 内存模型的设计基石：普通程序员只需保证无数据竞争；编译器则可以自由进行大多数单线程变换，因为任何能观察到变换差异的程序都有数据竞争、因而是 UB。

## 经典 litmus 测试

下面用标准的关系分析几个经典并发小程序。初值都为 0。

### MP（消息传递）

```cpp run title="mp.cpp" ok
#include <atomic>
#include <cassert>
#include <thread>
int data = 0;
std::atomic<bool> ready{false};
int main() {
  std::thread t1([] {
    data = 42;                                         // A
    ready.store(true, std::memory_order::release);     // B
  });
  std::thread t2([] {
    while (!ready.load(std::memory_order::acquire)) {} // C
    assert(data == 42);                                // D
  });
  t1.join(); t2.join();
}
```

分析：C 读到 B 写的 `true`，B 是 release、C 是 acquire → B synchronizes with C（[[atomics.order#2]]）。A sb B、C sb D，于是 A happens before D（¶7）。A 对 D 是可见副作用（¶9），D 读到 42；而且 A 与 D 之间有 happens before，**不构成数据竞争**。

若把 B、C 都改成 `relaxed`：没有 synchronizes-with，A 与 D 冲突、潜在并发、无 happens before → **数据竞争，UB**。不只是"可能读到 0"，而是整个程序没有定义的行为。

### SB（存储缓冲）

```cpp run title="sb.cpp"
#include <atomic>
#include <thread>
std::atomic<int> x{0}, y{0};
int r1, r2;
int main() {
  std::thread a([] { x.store(1, std::memory_order::relaxed); r1 = y.load(std::memory_order::relaxed); });
  std::thread b([] { y.store(1, std::memory_order::relaxed); r2 = x.load(std::memory_order::relaxed); });
  a.join(); b.join();
  // r1 == 0 && r2 == 0 是允许的结果
}
```

为什么 `r1 == r2 == 0` 合法？两个 load 都读初值，检查一致性：x 的修改顺序是 {初始化 0, store 1}，`r2 = x.load` 不 happens after `x.store(1)`（没有同步边），所以 ¶14 写-读一致性不强迫它读到 1；y 同理。没有违反任何规则。即使把四个操作都改成 acquire/release，结论也不变——release store 后面的 acquire load 可以"提前"（硬件上就是 store buffer）。在一台 AArch64 机器上用 relaxed 循环跑两万次，实测出现了几十次 `0, 0`。

**只有**四个操作都是 `seq_cst` 时，该结果被禁止：所有 seq_cst 操作在全序 S 中，不妨设 `x.store` 在 S 中先于 `y.store`……推下去总有一个 load 在 S 中排在对方 store 之后，按 [[atomics.order#4]]/¶5 的注它必须读到 1。这是 seq_cst 比 acq_rel 多出来的东西，也是它在 x86 上需要 `mfence`/`xchg` 的原因。

### IRIW（独立写的独立读）

```cpp run title="iriw.cpp"
#include <atomic>
#include <thread>
std::atomic<int> x{0}, y{0};
int r1, r2, r3, r4;
int main() {
  std::thread w1([] { x.store(1, std::memory_order::release); });
  std::thread w2([] { y.store(1, std::memory_order::release); });
  std::thread rA([] { r1 = x.load(std::memory_order::acquire); r2 = y.load(std::memory_order::acquire); });
  std::thread rB([] { r3 = y.load(std::memory_order::acquire); r4 = x.load(std::memory_order::acquire); });
  w1.join(); w2.join(); rA.join(); rB.join();
  // r1==1, r2==0, r3==1, r4==0 在 acquire/release 下是允许的
}
```

rA 看到"x 先于 y"，rB 看到"y 先于 x"——两个读线程对两次**独立**写的顺序意见不一。在 acquire/release 下这是允许的，正对应注 4："不要求各对象的修改顺序能合并成单一全序"。POWER 等非"多拷贝原子"（non-multi-copy-atomic）的架构上可以实际观察到。改用 `seq_cst` 后，S 给出了所有 seq_cst 操作的单一全序，这种分歧被禁止。

### 栅栏版的 MP

```cpp run title="fence-mp.cpp" ok
#include <atomic>
#include <cassert>
#include <thread>
int data = 0;
std::atomic<bool> ready{false};
int main() {
  std::thread t1([] {
    data = 42;
    std::atomic_thread_fence(std::memory_order::release);   // 栅栏 A
    ready.store(true, std::memory_order::relaxed);          // X
  });
  std::thread t2([] {
    while (!ready.load(std::memory_order::relaxed)) {}      // Y
    std::atomic_thread_fence(std::memory_order::acquire);   // 栅栏 B
    assert(data == 42);
  });
  t1.join(); t2.join();
}
```

[[atomics.fences#2]]：A sb X，X 修改 `ready`，Y 读到 X 的值，Y sb B → release 栅栏 A synchronizes with acquire 栅栏 B。于是 `data = 42` happens before 断言。栅栏让"同步"与"携带数据的原子变量"解耦：一个栅栏可以为多个 relaxed 操作服务。

!!! note "C++26：原子 modify-write 操作"
    [[atomics.fences#2]] 中 Y 不能是**原子 modify-write 操作**（[[atomics.order#12]]）——这是 C++26 新增的一类 RMW（如整数原子的 `store_add`、`store_max` 等"只写不返回"的归约操作），其意图是用不受 acquire 栅栏排序的硬件机制（例如远端原子）实现。它们不能作为栅栏同步中的"读端"，也不算 [[intro.progress]] 中的执行步骤。

## 信号处理函数与 sig_atomic_t（¶18）

¶18 对同一个（非位域）`volatile std::sig_atomic_t` 对象的两次访问，若都发生在同一线程中，即使其中一个或多个在信号处理函数里，也**不**构成数据竞争。并且：对每次信号处理函数调用，被打断线程的求值可以划分为两组 A、B，B 中的求值都不 happens before A 中的求值；对这类 volatile `sig_atomic_t` 对象的求值，所取的值如同 A 全部发生在处理函数执行之前、处理函数又发生在 B 全部之前。

换句话说：信号"插入"在被打断线程的某个点上，对 `volatile sig_atomic_t` 而言看起来是原子的插入。这是从 C 继承的老机制；现代代码也可以用无锁的 `std::atomic` 与 `atomic_signal_fence`（[[atomics.fences#6]]）。

```cpp run title="sig.cpp" ok
#include <csignal>
#include <cstdio>
volatile std::sig_atomic_t got = 0;
extern "C" void on_sig(int) { got = 1; }   // OK：同线程内的 volatile sig_atomic_t 访问
int main() {
  std::signal(SIGINT, on_sig);
  std::raise(SIGINT);       // 处理函数在 raise 内执行（[intro.execution]/15）
  std::printf("%d\n", static_cast<int>(got));
}
```

## 编译器不得引入数据竞争（¶19–¶20）

¶19 注 19：标准**一般禁止**编译器引入"抽象机不会执行的、对可能共享的内存位置的赋值"——因为这样的赋值可能覆盖另一线程的写入，而抽象机的执行中原本没有数据竞争。这包括：

- **写相邻成员**：对 `struct { char a; char b; }` 的 `a` 赋值，不能实现为"读 4 字节、改 1 字节、写回 4 字节"，否则会冲掉另一线程对 `b` 的写入。这就是为什么 C++11 内存模型要求 `char` 粒度的独立写入（老 Alpha 处理器没有字节存储指令，曾是现实问题）。只有位域共享内存位置时编译器才可以这样做——那时标准本来就规定它们冲突。
- **把条件写变成无条件写**：
  ```cpp
  if (cond) x = 1;      // 不能被优化为 tmp = x; x = 1; if (!cond) x = tmp;
  ```
  后者在 `cond` 为假时引入了对 x 的写入，可能与其他线程竞争。
- **寄存器提升**：循环中有条件地修改全局变量时，不能把它提升到寄存器并在循环后无条件写回。

注 19 还提到：若相关原子对象可能互为别名，重排原子 load 一般也被禁止，因为可能违反一致性规则。

¶20 注 20：引入**推测性读**（speculative read）则通常是可以的。严格说它可能引入数据竞争，但对于目标机器上"竞争读只是读到某个值"的实现而言是安全的；只有在不容忍竞争、或有硬件竞争检测的假想机器上才不合法。

## 实现视角

!!! impl "常见映射"
    | C++ 操作 | x86-64 | AArch64 |
    |---|---|---|
    | load relaxed / acquire | `mov` | `ldr` / `ldar`（或 `ldapr`） |
    | store relaxed / release | `mov` | `str` / `stlr` |
    | store seq_cst | `xchg`（或 `mov` + `mfence`） | `stlr` |
    | load seq_cst | `mov` | `ldar` |
    | fetch_add | `lock xadd` | `ldaddal` 等（LSE），或 LL/SC 循环 |
    | fence acquire / release | 无指令（仅编译器屏障） | `dmb ishld` / `dmb ish` |
    | fence seq_cst | `mfence` | `dmb ish` |

    x86 是 TSO（全存储序）：只允许 store→load 重排，所以 acquire/release 免费，只有 seq_cst store 要付代价——SB 测试的 `0,0` 正是 TSO 下唯一可见的"怪异"结果。ARMv8 是"其他多拷贝原子"（other-multi-copy-atomic），IRIW 的分歧在 ARMv8 上不会出现，但标准仍允许它，因为 POWER 上会出现。

!!! impl "ThreadSanitizer"
    TSan（`-fsanitize=thread`，GCC 与 Clang 都支持）在运行时用向量时钟近似 happens before 关系，检测¶17 意义上的数据竞争。它只能发现**实际执行到**的竞争，且对栅栏（`atomic_thread_fence`）的支持有限，可能对正确的栅栏同步代码报出误报——本页的"栅栏版 MP"例子在 Clang 23 的 TSan 下就会被误报为数据竞争。

## 历史与演进

!!! history "从 pthreads 到形式化内存模型"
    - **C++98/03**：标准中没有"线程"的概念，多线程程序的语义完全由 POSIX 等平台规范给出，而这些规范在编译器优化面前漏洞百出（Hans Boehm 的论文《Threads Cannot Be Implemented as a Library》系统阐述了这个问题）。
    - **C++11**：引入本节，建立基于 happens before 的内存模型与 `std::atomic`。C 11 同时采用了几乎相同的模型。
    - 之后的修订中，对"无中生有"（out-of-thin-air）值的规定改成了建议性条款（今在 [[atomics.order#8]]）——如何精确地形式化禁止它，至今仍是开放的研究问题。
    - **C++17**：`memory_order_consume` 被标注为"暂时不鼓励使用"。
    - **C++20**：[[P0668R5]] 修订 seq_cst 语义，重新定义 strongly happens before 并引入 simply happens before；[[P0982R1]] 削弱 release sequence；`memory_order` 变为作用域枚举（同时保留 `memory_order_acquire` 等常量）。
    - **C++26**：consume 及依赖排序相关的定义被移除，consume 进入附录 D；happens before 简化为现在的三行定义。新增原子 modify-write 操作。

## 陷阱

!!! pitfall "volatile 不是同步"
    `volatile` 只保证每次访问都真的发生（[[intro.abstract]] 的可观察行为），不提供原子性，也不建立 happens before。两个线程无同步地访问同一个 `volatile int` **依然是数据竞争**（¶17 只对同一线程内的 `volatile sig_atomic_t` 开了口子）。MSVC 在 `/volatile:ms` 下给 volatile 附加了 acquire/release 语义，这是扩展，不是标准。

!!! pitfall "\"良性\"数据竞争不存在"
    `if (!initialized) { init(); initialized = true; }` 这类"反正只是读到旧值也没关系"的竞争在标准下是 UB。编译器可以假设无竞争而做出意想不到的变换（如把读合并、把写拆开）。需要时用 `std::atomic<bool>` 配合合适的内存序。

!!! pitfall "relaxed 读到新值 ≠ 看到之前的写"
    注 5 说得很明白：读到一个"更新的值"不意味着可见性。用 relaxed 标志位发布非原子数据，是数据竞争。

## 思考题

!!! question "1. 下面程序有数据竞争吗？"
    ```cpp
    int data = 0;
    std::atomic<int> f{0};
    // 线程 1
    data = 1;
    f.store(1, std::memory_order::release);
    f.store(2, std::memory_order::relaxed);
    // 线程 2
    if (f.load(std::memory_order::acquire) == 2) { int r = data; }
    ```

<details markdown="1">
<summary>答案</summary>

有（当线程 2 读到 2 时）。按当前定义（C++20 起），release sequence 只由 release 操作 A 之后的**RMW**组成；`f.store(2, relaxed)` 不是 RMW，所以它不在以 `f.store(1, release)` 为首的 release sequence 中。线程 2 读到 2，与线程 1 没有 synchronizes-with，`data = 1` 与 `int r = data` 之间没有 happens before → 数据竞争，UB。在 C++11/14/17 中，同线程的后续 store 属于 release sequence，这段代码是正确的——这正是 [[P0982R1]] 改变的地方。修复：把第二个 store 也改为 release。
</details>

!!! question "2. 两个线程同时对同一个 `std::atomic<int>` 做 `x.store(1, relaxed)` 和 `x.load(relaxed)`，有 UB 吗？读到什么？"

<details markdown="1">
<summary>答案</summary>

没有 UB：¶17 要求"至少一个不是原子的"才构成数据竞争。load 读到修改顺序中的某个值（¶10）：0 或 1 都可能，取决于执行。
</details>

!!! question "3. 为什么 ¶8.2 要求两端都是 seq_cst，而不是只要是 synchronizes-with 就算 strongly happens before？"

<details markdown="1">
<summary>答案</summary>

因为全序 S 必须与 strongly happens before 一致（[[atomics.order#4]]）。在 POWER 等架构上，seq_cst 与 acquire/release 混用时，主流的指令映射不能保证一条 release→acquire 的同步边在 S 中被尊重。若把所有同步边都算进来，标准就会要求比硬件映射能提供的更强的保证，导致 seq_cst 需要更昂贵的实现。所以只有两端都是 seq_cst 的同步边才直接计入；其他情况要求"sequenced before + happens before + sequenced before"的夹心结构（¶8.3）。
</details>

## 小结

| 概念 | 一句话 | 段落 |
|---|---|---|
| 冲突 | 同一内存位置，至少一个写（或生命周期开始/结束） | ¶2 |
| 修改顺序 | 每个原子对象上所有修改的全序 | ¶4 |
| release sequence | release 操作及其后连续的 RMW | ¶5 |
| synchronizes with | release ↔ 读到其 release sequence 中的值的 acquire（及栅栏、mutex、线程） | ¶6 |
| happens before | (sequenced before ∪ synchronizes with)⁺ | ¶7 |
| strongly happens before | 能被 seq_cst 全序尊重的那部分 happens before | ¶8 |
| 可见副作用 | 非原子读读到"最后一个 happens before 它的写" | ¶9 |
| 原子读 | 读修改顺序中某个不 happens after 它的值，受四条一致性约束 | ¶10–¶14 |
| 数据竞争 | 潜在并发、冲突、至少一个非原子、无 happens before → UB | ¶17 |
| SC-DRF | 无数据竞争、只用 mutex 与 seq_cst → 顺序一致 | 注 18 |
