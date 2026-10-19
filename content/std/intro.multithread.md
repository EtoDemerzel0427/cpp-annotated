---
title: 多线程执行与数据竞争
summary: C++ 内存模型的形式定义：线程、冲突、修改顺序、release sequence、synchronizes with、happens before、四条一致性规则，以及数据竞争为什么是未定义行为。
status: done
covers: intro.multithread.general, intro.races
papers: P0668R5, P0982R1, P3475R2, P3111R8
related: intro.execution, intro.progress, intro.memory, atomics.order, atomics.fences, thread.mutex.requirements
tags: 内存模型, 并发, 原子操作, UB
updated: 2026-10-19
---

!!! tldr
    - 两个线程访问同一内存位置、至少一个是写、至少一个不是原子操作，并且两者之间没有 happens before 关系，这就是数据竞争，整个程序的行为未定义。
    - happens before 由线程内的 sequenced before 和线程间的 synchronizes with 组成。release 写与读到它的 acquire 读同步，互斥量的 unlock 与下一次 lock 同步。
    - 每个原子对象的所有修改有一个全序（修改顺序），四条一致性规则禁止同一个原子对象上的读写出现倒退。不同对象的修改顺序不必能合成一个全序。
    - 只用互斥量和 seq_cst 原子操作、没有数据竞争的程序，行为如同各线程操作的简单交错。用了 acquire/release 或 relaxed，就会出现交错解释不了的结果。
    - volatile 不是同步手段。唯一的例外是同一线程内对 `volatile std::sig_atomic_t` 的访问与信号处理函数之间。

## 一个数据竞争

```cpp run title="race.cpp" ub
#include <thread>
int counter = 0;
int main() {
  std::thread t([] { ++counter; });
  ++counter;          // UB：与 t 中的 ++counter 构成数据竞争
  t.join();
  return counter;
}
```

用 `-fsanitize=thread` 编译运行，ThreadSanitizer 报告 data race。把 `counter` 改成 `std::atomic<int>`，或者用互斥量保护，程序就正确了。

判断这段代码为什么是 UB、改了之后为什么正确，要用到 [intro.races] 定义的一组关系。这些关系描述的不是硬件，而是抽象机允许的执行。原子操作的内存序（[[atomics.order]]）、互斥量（[[thread.mutex.requirements]]）和栅栏（[[atomics.fences]]）的语义，都是往这些关系里添加边。

前置知识：[[intro.execution]] 定义的 sequenced before（同一线程内的先后），以及[[intro.memory|内存位置]]（一个标量对象，或一串相邻的非零宽位域）。

## 线程 [intro.multithread.general]

[[intro.multithread.general#1]] **执行线程**（thread of execution，简称线程）是程序里的一条控制流，从某个顶层函数的初次调用开始，递归地包括这个线程随后执行的每一次函数调用。注 1 说明，一个线程创建另一个线程时，新线程顶层函数的初次调用由新线程执行。

每个线程都可能用到程序里的每个对象和函数。脚注 31 补充，自动或线程存储期的对象属于某个特定线程，其他线程只能通过指针或引用间接访问它。宿主实现中程序可以有多个线程并发运行；独立实现中是否支持多线程由实现定义。

程序的一次执行由它所有线程的执行组成。注 2 指出，通常可以把执行看作各线程的交错，但某些原子操作允许出现与任何交错都不一致的执行，下文的 litmus 测试会看到这样的例子。

[[intro.multithread.general#2]] 不是由 `std::raise` 触发的信号处理函数，由哪个线程执行是未指定的。

## 冲突（¶2）

¶1 一个线程在某一点能看到的对象值，是对象的初值、它自己写入的值或其他线程写入的值，具体由下面的规则决定。注 1 承认，有些情况下结果是未定义行为。

¶2 两个求值**冲突**（conflict），是指其中一个

- ¶2.1 修改（[[defns.access]]）某个内存位置，或 ¶2.2 在某个内存位置开始或结束对象的生命期，

而另一个

- ¶2.3 读或修改同一内存位置，或 ¶2.4 在与它重叠的存储中开始或结束对象的生命期。

注 2 补充，即使修改没有改变任何位，也算冲突：`x = x;` 与另一个线程对 `x` 的读冲突。

冲突按内存位置判断，所以内存位置的划分决定了哪些访问冲突：

```cpp run title="memloc.cpp" ok
#include <thread>
struct S {
  char a;
  int b : 5;
  int c : 11, : 0, d : 8;   // 零宽位域把 c 和 d 分到不同的内存位置
  struct { int ee : 8; } e;
};
S s;
int main() {
  // a、(b 和 c)、d、e.ee 是四个内存位置
  std::thread t1([] { s.a = 1; s.d = 2; });
  std::thread t2([] { s.b = 3; s.e.ee = 4; });   // 与 t1 不冲突
  t1.join(); t2.join();
}
```

如果 t1 写 `s.b`、t2 写 `s.c`，两者是相邻的非零宽位域，属于同一个内存位置，即使是不同的成员也冲突，没有同步就是数据竞争。这个例子改编自 [[intro.memory]] 的例子。

## 同步操作与修改顺序（¶3–¶5）

¶3 标准库把一些原子操作（[[atomics]]）和互斥量操作（[[thread]]）标为**同步操作**（synchronization operation），它们负责让一个线程的写入对另一个线程可见：

| 种类 | 例子 |
|---|---|
| acquire 操作 | `load(acquire)`、`mutex::lock()` |
| release 操作 | `store(release)`、`mutex::unlock()` |
| 既是 acquire 又是 release | `fetch_add(acq_rel)`、`exchange(seq_cst)` |
| 栅栏（fence），没有关联的内存位置 | `atomic_thread_fence(acquire)` 等 |

relaxed 原子操作不是同步操作，但和同步操作一样不会参与数据竞争。原子读-改-写操作（`fetch_add`、`exchange`、`compare_exchange_*`）另有特殊性质。注 3 说明，获取互斥量就是在构成互斥量的位置上执行 acquire 操作，释放互斥量执行 release 操作。

¶4 每个原子对象 M 的全部修改按某个全序发生，叫做 M 的**修改顺序**（modification order）。注 4 强调每个原子对象各有自己的修改顺序，不要求它们能合并成所有对象的单一全序，因为不同线程可能以不一致的顺序观察到对不同对象的修改（见下文 IRIW）。

¶5 以原子对象 M 上的 release 操作 A 开头的 **release sequence**，是 M 的修改顺序中的一段极大连续子序列：第一个是 A，后面每一个都是原子读-改-写操作。

一个线程做 release 写，其他线程随后做了几次 relaxed 的读-改-写，最后某个线程做 acquire 读，读到的是某次读-改-写写入的值。这个 acquire 读仍然与最初的 release 写同步（[[atomics.order#2]]），因为读-改-写延续了 release sequence。引用计数等模式依赖的就是这一点。

```cpp run title="release-seq.cpp" ok
#include <atomic>
#include <cassert>
#include <thread>
int payload = 0;
std::atomic<int> flag{0};
int main() {
  std::thread prod([] {
    payload = 42;
    flag.store(1, std::memory_order::release);       // A：release sequence 的开头
  });
  std::thread mid([] {
    int expected = 1;
    while (!flag.compare_exchange_weak(expected, 2, std::memory_order::relaxed))
      expected = 1;                                   // 读-改-写，延续 A 的 release sequence
  });
  std::thread cons([] {
    while (flag.load(std::memory_order::acquire) != 2) {}   // 读到读-改-写写入的 2
    assert(payload == 42);   // OK：仍与 A 同步
  });
  prod.join(); mid.join(); cons.join();
}
```

## synchronizes with 与 happens before（¶6–¶8）

¶6 某些库调用与另一个线程执行的库调用**同步**（synchronize with）。具体条件在库条款里：

- 原子操作：release 操作 A 与一个读到 A 的 release sequence 中某个值的 acquire 操作同步（[[atomics.order#2]]）。
- 栅栏：release 栅栏与 acquire 栅栏、栅栏与原子操作之间的同步见 [[atomics.fences]]。
- 互斥量：注 6 说明，同一个互斥量上的所有操作构成一个全序，每次加锁相当于读到了上一次解锁写入的值，所以 unlock 与下一次 lock 同步。
- 线程：`std::thread` 构造函数的完成与新线程函数的开始同步，线程结束与 `join` 返回同步（[[thread.thread.constr]]、[[thread.thread.member]]）。

注 5 提醒，除了这些指定的情形，读到一个较新的值并不保证可见性。relaxed 读读到了 release 写的值，两者也不同步。

¶7 求值 A [[g:happens-before|**happens before**]] 求值 B，当且仅当 ¶7.1 A sequenced before B，或 ¶7.2 A 与 B 同步，或 ¶7.3 存在 X，A happens before X 且 X happens before B。也就是说，happens before 是线程内顺序与线程间同步边合在一起的传递闭包。注 7 说明求值不会 happens before 自己。

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

这是消息传递（message passing，MP）模式。C 读到 B 写入的 `true`，B 是 release、C 是 acquire，所以 B 与 C 同步。A sequenced before B，C sequenced before D，于是 A happens before D。下文 ¶9 保证 D 读到 42，而 A 与 D 之间有 happens before，也不构成数据竞争。

如果 B、C 都改成 relaxed，就没有同步，A 与 D 冲突、在不同线程、没有 happens before，构成数据竞争。后果不只是可能读到 0，而是整个程序的行为未定义。

### strongly happens before（¶8）

¶8 A **strongly happens before** D，当且仅当：

- ¶8.1 A sequenced before D；或
- ¶8.2 A 与 D 同步，且两者都是 seq_cst 原子操作；或
- ¶8.3 存在 B、C，A sequenced before B，B happens before C，C sequenced before D；或
- ¶8.4 存在 B，A strongly happens before B，B strongly happens before D。

注 8：非正式地说，A strongly happens before B，就是 A 在所有语境下看起来都先于 B 求值。

为什么需要两种关系？[[atomics.order#4]] 要求所有 seq_cst 操作构成一个全序 S，S 必须与 strongly happens before 一致，但不要求与 happens before 一致（[[atomics.order#6]] 的注 3）。在 POWER 等架构上，acquire/release 与 seq_cst 混用时，常用的指令映射保证不了 S 与包含 acquire/release 同步边的 happens before 一致。C++20 的 [[P0668R5]] 据此修订了定义，让 strongly happens before 成为 happens before 中 S 确实能尊重的那部分。

对比 ¶8.2 和 ¶7.2：同步边只有两端都是 seq_cst 时才直接算进 strongly happens before；¶8.3 允许中间夹一段普通的 happens before，但两头必须是 sequenced before。

本节之外，strongly happens before 还用来规定静态初始化先于动态初始化（[[basic.start.static#2]]），以及程序终止时的析构顺序（[[basic.start.term#4]]）。

## 一次读能读到什么（¶9–¶16）

¶9 对标量对象或位域 M 的值计算 B，M 上的副作用 A 是**可见副作用**（visible side effect），当且仅当 ¶9.1 A happens before B，并且 ¶9.2 不存在 M 上的另一个副作用 X，使 A happens before X 且 X happens before B。非原子对象 M 被 B 求得的值，就是可见副作用 A 存入的值。

换句话说，非原子读读到的是最后一个 happens before 它的写。注 9 说明，如果哪个写可见有歧义（两个写都 happens before 读，而两者之间没有 happens before），行为未指定或未定义。注 10 指出，这条规则说明普通对象上的操作不会被看到重排；在没有数据竞争的程序里，重排本来就观察不到。

¶10 原子对象 M 被 B 求得的值，是某个修改 M 的副作用 A 存入的值，A 是哪一个未指定，只要求 B 不 happens before A。与非原子读不同，原子读可以从修改顺序的多个候选中读一个，不一定是最新的。注 11 指出，候选集合还受下面的一致性规则约束。

### 四条一致性规则（¶11–¶14）

对同一个原子对象 M，happens before 与修改顺序必须相容：

| 段落 | 名称 | 如果 | 那么 |
|---|---|---|---|
| ¶11 | 写-写一致性 | 修改 A happens before 修改 B | A 在 M 的修改顺序中早于 B |
| ¶12 | 读-读一致性 | 读 A happens before 读 B，A 读到 X 写入的值 | B 读到 X 或修改顺序中 X 之后的值 |
| ¶13 | 读-写一致性 | 读 A happens before 修改 B | A 读到修改顺序中 B 之前的某个值 |
| ¶14 | 写-读一致性 | 修改 X happens before 读 B | B 读到 X 或修改顺序中 X 之后的值 |

¶15 的注 16 总结：这四条实际上禁止编译器重排同一个原子对象上的操作，即使两个都是 relaxed 读也不行。它们把大多数硬件提供的缓存一致性保证带到了 C++ 层面。

```cpp run title="corr.cpp" ok
#include <atomic>
#include <cassert>
#include <thread>
std::atomic<int> x{0};
int main() {
  std::thread w([] {
    x.store(1, std::memory_order::relaxed);
    x.store(2, std::memory_order::relaxed);
  });
  std::thread r([] {
    int a = x.load(std::memory_order::relaxed);
    int b = x.load(std::memory_order::relaxed);
    assert(!(a == 2 && b == 1));   // 读-读一致性：读到 2 之后不会再读到更早的 1
    assert(!(a > 0 && b == 0));    // 初值 0 在修改顺序的最前面
  });
  w.join(); r.join();
}
```

¶16 的注 17 讨论了一处看似循环的定义：原子读读到什么取决于 happens before，而 happens before 通过同步边又取决于原子读读到了什么。标准的意思是：只要能找到一种原子读与它所读的写之间的对应关系，连同适当选取的修改顺序和由此导出的 happens before，满足上面所有约束，这就是一次合法的执行。

## 数据竞争（¶17）

¶17 两个动作是**潜在并发**（potentially concurrent）的，当且仅当 ¶17.1 它们由不同线程执行，或 ¶17.2 它们无序、至少一个由信号处理函数执行、且不由同一次信号处理函数调用执行。

!!! std
    The execution of a program contains a data race if it contains two potentially concurrent conflicting actions, at least one of which is not atomic, and neither happens before the other […]

一次执行如果包含两个潜在并发的冲突动作，至少一个不是原子的，并且两者都不 happens before 对方，这次执行就包含[[g:data-race|**数据竞争**]]（data race）。¶18 的信号处理函数情形除外。任何数据竞争都导致未定义行为。

- 两个都是原子操作就不会构成数据竞争，即使都是 relaxed。relaxed 只是不提供同步。
- 只读不冲突，两个线程同时读同一个非原子对象没有问题。
- 数据竞争造成的 UB 发生在所有参与的线程上（[[intro.abstract]] 注 2），程序在这之前产生的可观察行为，也只有可观察检查点之前的部分受保护。

!!! summary "注 18：无数据竞争则顺序一致"
    只用互斥量和 `memory_order::seq_cst` 原子操作消除了所有数据竞争、且不使用其他同步操作的程序，行为如同各线程的操作简单交错执行，每次读取都取交错中该对象最后一次写入的值。这就是**顺序一致性**（sequential consistency），常称 SC-DRF。程序员只需保证没有数据竞争；编译器则可以做几乎所有单线程变换，因为能观察到变换差异的程序都有数据竞争，行为本来就未定义。

## 交错解释不了的结果

下面用上面的关系分析两个经典的并发小程序（litmus 测试）。初值都是 0。

### 存储缓冲（SB）

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

在任何交错里，总有一个 store 先执行，所以 `r1`、`r2` 不可能都是 0。但 C++ 允许这个结果：两个 load 都读初值，检查一致性规则，`x.load` 不 happens after `x.store(1)`（没有同步边），¶14 不要求它读到 1；`y` 同理。四个操作全改成 acquire/release 也一样，硬件上对应的是 store buffer：store 还在缓冲区里，后面的 load 已经执行了。本机（Apple arm64）用 relaxed 反复运行，确实能观察到 `0, 0`。

四个操作都是 seq_cst 时，这个结果被禁止。按 [[atomics.order#4]]，所有 seq_cst 操作在全序 S 中，并且 S 与 strongly happens before 一致，所以 `x.store` 在 S 中先于 `y.load`，`y.store` 先于 `x.load`。假设 `y.load` 读到初值 0：初值在 `y` 的修改顺序中位于 `y.store` 之前，按 [[atomics.order#3]]（¶3.3）`y.load` coherence-ordered before `y.store`，¶4.1 又要求 `y.load` 在 S 中先于 `y.store`。于是 S 中有 `x.store` < `y.load` < `y.store` < `x.load`；`x.load` 在 S 中排在 `x.store` 之后，同理它不可能读到初值。这就是 seq_cst 比 acquire/release 多出来的保证，也是 x86 上 seq_cst store 需要 `xchg` 或 `mfence` 的原因。

### 独立写的独立读（IRIW）

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

rA 看到 x 先于 y 被写，rB 看到 y 先于 x，两个读线程对两次独立写入的先后看法不一。这正是注 4 所说的：各对象的修改顺序不必能合成一个全序。在 POWER 这类非多副本原子（non-multi-copy-atomic）的架构上，这个结果能实际观察到。全部改用 seq_cst 后，S 给出了单一全序，这种分歧被禁止。

### 用栅栏实现 MP

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

按 [[atomics.fences#2]]：A sequenced before X，X 修改 `ready`，Y 读到 X 写入的值，Y sequenced before B，所以 release 栅栏 A 与 acquire 栅栏 B 同步，`data = 42` happens before 断言。栅栏把同步和携带数据的原子变量分开，一个栅栏可以为多个 relaxed 操作服务。

{{c++26}} [[atomics.fences#2]] 要求 Y 不是**原子 modify-write 操作**（[[atomics.order#12]]）。这是 [[P3111R8]] 新增的一类读-改-写，例如只写不返回的 `store_add`，意图是可以用不受 acquire 栅栏排序的硬件机制实现。它们不能充当栅栏同步的读端。

## 信号处理函数（¶18）

¶18 同一线程中对同一个非位域 `volatile std::sig_atomic_t` 对象的两次访问不构成数据竞争，即使其中有的发生在信号处理函数里。对每次信号处理函数调用，被打断线程的求值可以分成两组 A、B，B 中的求值都不 happens before A 中的求值；对这类对象的求值，取值如同 A 全部发生在处理函数之前、处理函数又发生在 B 全部之前。

换句话说，信号处理插在被打断线程的某一点上，对 `volatile sig_atomic_t` 来说这次插入看起来是原子的。这是从 C 继承的机制，现代代码也可以用无锁的 `std::atomic` 加 `atomic_signal_fence`（[[atomics.fences#6]]）。

```cpp run title="sig.cpp" ok
#include <csignal>
#include <cstdio>
volatile std::sig_atomic_t got = 0;
extern "C" void on_sig(int) { got = 1; }   // 同一线程内的 volatile sig_atomic_t 访问
int main() {
  std::signal(SIGINT, on_sig);
  std::raise(SIGINT);       // 处理函数在 raise 内执行（[intro.execution]/15）
  std::printf("%d\n", static_cast<int>(got));
}
```

## 编译器不能引入数据竞争（¶19–¶20）

¶19 的注 19 说明，编译器一般不能引入抽象机不会执行的、对可能共享的内存位置的写入，因为这样的写入可能覆盖另一个线程的写入，而抽象机的执行里本来没有数据竞争：

- 给 `struct { char a; char b; }` 的 `a` 赋值，不能实现为读 4 字节、改 1 字节、写回 4 字节，否则会冲掉另一个线程对 `b` 的写入。只有位域共享内存位置时可以这样做，因为那时标准本来就认为它们冲突。
- `if (cond) x = 1;` 不能改写成 `tmp = x; x = 1; if (!cond) x = tmp;`，后者在 `cond` 为假时引入了对 `x` 的写入。
- 循环里有条件地修改全局变量时，不能把它放进寄存器、循环结束后无条件写回。

注 19 还说，相关原子对象可能互为别名时，一般也不能重排原子读，否则可能违反一致性规则。

¶20 的注 20 说明，引入推测性的读通常是可以的。严格说它可能引入数据竞争，但在目标机器上，竞争的读只是读到某个值，没有其他后果。

!!! impl "实现视角"
    | C++ 操作 | x86-64 | AArch64 |
    |---|---|---|
    | load relaxed / acquire | `mov` | `ldr` / `ldar`（或 `ldapr`） |
    | store relaxed / release | `mov` | `str` / `stlr` |
    | store seq_cst | `xchg`（或 `mov` + `mfence`） | `stlr` |
    | load seq_cst | `mov` | `ldar` |
    | fetch_add | `lock xadd` | `ldaddal` 等（LSE），或 LL/SC 循环 |
    | fence acquire / release | 无指令，只是编译器屏障 | `dmb ishld` / `dmb ish` |
    | fence seq_cst | `mfence` | `dmb ish` |

    x86 是全存储序（TSO），只允许 store 之后的 load 提前，所以 acquire/release 没有额外开销，只有 seq_cst store 需要付出代价，SB 测试的 `0, 0` 是 TSO 下唯一能观察到的反直觉结果。ARMv8 是 other-multi-copy-atomic 的，IRIW 的分歧不会出现，但标准仍然允许它，因为 POWER 上会出现。

    ThreadSanitizer（`-fsanitize=thread`）在运行时近似计算 happens before，检测 ¶17 意义上的数据竞争。它只能发现实际执行到的竞争，对 `atomic_thread_fence` 的支持有限。本机 Clang 23 的 TSan 会把上面正确的栅栏版 MP 误报为数据竞争。

!!! history "历史与演进"
    - C++98/03 中没有线程，多线程程序的语义完全由 POSIX 等平台规范给出，而这些规范在编译器优化面前有许多漏洞（Hans Boehm，*Threads Cannot Be Implemented as a Library*，PLDI 2005）。
    - C++11 引入本节，建立了基于 happens before 的内存模型和 `std::atomic`，C11 同时采用了几乎相同的模型。禁止无中生有（out-of-thin-air）的值后来改成了建议性条款，现在位于 [[atomics.order#8]]，怎样精确地形式化它至今是开放问题。
    - C++20 的 [[P0668R5]] 修订了 seq_cst 的语义和 strongly happens before；[[P0982R1]] 削弱了 release sequence。C++11 中同一线程在 A 之后的普通原子写也延续 release sequence，这条几乎没人使用，却增加了实现和形式化的负担，现在只有读-改-写能延续它。
    - C++26 的 [[P3475R2]] 把 `memory_order::consume` 移出了核心内存模型。consume 想用数据依赖代替 acquire，在 ARM、POWER 上省掉屏障指令，但依赖在源码层面很难跟踪，主流编译器都把它当 acquire 实现。原来为它服务的 carries a dependency、dependency-ordered before、inter-thread happens before 都从本节删除，happens before 简化成现在 ¶7 的三行定义；`memory_order::consume` 移入附录 D，含义与 acquire 相同（[[depr.atomics.order]]）{{deprecated}}。¶3 的注 3 里还留着 consume or acquire 的说法。

## 常见误解

!!! pitfall "volatile 可以用来同步"
    volatile 只保证每次访问真的发生（[[intro.abstract]] 的可观察行为），不提供原子性，也不建立 happens before。两个线程不加同步地访问同一个 `volatile int`，仍然是数据竞争。¶18 只对同一线程内的 `volatile std::sig_atomic_t` 开了例外。MSVC 在 `/volatile:ms` 下给 volatile 附加 acquire/release 语义，这是扩展。

!!! pitfall "有些数据竞争是良性的"
    `if (!initialized) { init(); initialized = true; }` 这类看起来读到旧值也无妨的竞争，在标准下就是 UB。编译器可以假设没有竞争，据此合并读、拆分写。需要时用 `std::atomic<bool>` 配合合适的内存序，或者直接用 `std::call_once`、函数内的静态变量。

!!! pitfall "relaxed 读读到了新值，就能看到之前的写"
    注 5 说得很清楚，读到较新的值不意味着可见性。用 relaxed 标志位发布非原子数据是数据竞争。

## 思考题

!!! question "1. 线程 2 读到 2 时，下面的程序有数据竞争吗？"
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

有。release sequence 只由 release 操作及其后的读-改-写组成（¶5）。`f.store(2, relaxed)` 不是读-改-写，不在以 `f.store(1, release)` 开头的 release sequence 里。线程 2 读到 2，与线程 1 没有同步，`data = 1` 与 `int r = data` 之间没有 happens before，构成数据竞争。

C++11/14/17 中，同一线程之后的原子写也属于 release sequence，这段代码是正确的；[[P0982R1]] 改变的正是这一点。修复方法是把第二个 store 也改为 release。
</details>

!!! question "2. 两个线程同时对同一个 `std::atomic<int>` 执行 `x.store(1, relaxed)` 和 `x.load(relaxed)`，有 UB 吗？读到什么？"

<details markdown="1">
<summary>答案</summary>

没有 UB。按 ¶17，至少一个动作不是原子的才构成数据竞争。读到的是修改顺序中的某个值（¶10），0 或 1 都可能。
</details>

!!! question "3. 为什么 ¶8.2 要求两端都是 seq_cst，而不是只要同步就算 strongly happens before？"

<details markdown="1">
<summary>答案</summary>

因为全序 S 必须与 strongly happens before 一致（[[atomics.order#4]]）。在 POWER 等架构上，seq_cst 与 acquire/release 混用时，主流的指令映射不能保证一条 release 到 acquire 的同步边在 S 中被尊重。如果把所有同步边都算进来，标准就会要求比这些映射更强的保证，seq_cst 也就需要更昂贵的实现。所以只有两端都是 seq_cst 的同步边才直接算进去，其他情况要求 sequenced before、happens before、sequenced before 首尾相接（¶8.3）。
</details>
