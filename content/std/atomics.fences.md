---
title: 栅栏
summary: atomic_thread_fence 与 atomic_signal_fence——三种栅栏同步规则（栅栏-栅栏、栅栏-操作、操作-栅栏）中的"假想 release sequence"、原子 modify-write 操作为何被排除、seq_cst 栅栏如何进入全序 S，以及只约束编译器的 signal fence
status: done
covers: atomics.fences
related: atomics.order, intro.races, intro.multithread, intro.execution, support.signal
tags: 标准库, 原子操作, 内存模型, 栅栏
updated: 2026-10-18
---

[[atomics.order#2]] 的 release/acquire 同步把"同步"绑在一次具体的原子操作上：`store(release)` 既写数据又负责发布。栅栏（fence）把这两件事拆开：原子操作本身可以是 `relaxed` 的，同步由线程里的一个**栅栏**提供。这有两个用处：

- 一个栅栏可以同时为多个 relaxed 操作"补上"内存序（如读多个标志位后只付一次 acquire 的代价）；
- 只在需要时才付同步的代价（如先 relaxed 地读，读到期望的值后才加 acquire 栅栏）。

栅栏**没有关联的内存位置**（[[intro.races]] ¶3），这是它与原子操作的根本区别。[[intro.multithread]] 已经给出了"栅栏版 MP"的例子与分析，本页逐段看条文。

## 栅栏的定义（¶1）

¶1 本子条款引入称为**栅栏**的同步原语。栅栏可以有 acquire 语义、release 语义或两者兼有。有 acquire 语义的叫 **acquire 栅栏**，有 release 语义的叫 **release 栅栏**。

## 三条同步规则（¶2–¶4）

三条规则形状相同，区别只是两端哪一端用栅栏、哪一端用原子操作：

| 段落 | release 端 | acquire 端 | 中间连接 |
|---|---|---|---|
| ¶2 | release **栅栏** A | acquire **栅栏** B | A sb X，X 修改 M；Y 读 M，Y sb B |
| ¶3 | release **栅栏** A | acquire **操作** B（在 M 上） | A sb X，X 修改 M；B 读到 X 的值 |
| ¶4 | release **操作** A（在 M 上） | acquire **栅栏** B | X 读到 A 的值，X sb B |

（sb = sequenced before）

¶2 全文：

!!! std
    A release fence A synchronizes with an acquire fence B if there exist atomic operations X and Y, where Y is not an atomic modify-write operation, both operating on some atomic object M, such that A is sequenced before X, X modifies M, Y is sequenced before B, and Y reads the value written by X or a value written by any side effect in the hypothetical release sequence X would head if it were a release operation.

    若存在都作用于某原子对象 M 的原子操作 X 与 Y（Y 不是原子 modify-write 操作），使得 A sb X、X 修改 M、Y sb B，且 Y 读到 X 写入的值，或读到"假如 X 是 release 操作，它所领头的假想 release sequence"中任一副作用写入的值，则 release 栅栏 A 与 acquire 栅栏 B 同步。

几个细节：

**"假想 release sequence"**：X 本身可以是 relaxed 的，它没有真正的 release sequence。但为了让 RMW 链同样能"传递"栅栏的同步，标准假设 X 是 release 操作、按 [[intro.races]] ¶5 构造它会领头的 release sequence——Y 读到其中任何 RMW 写入的值都算。¶3 也用了同样的措辞。¶4 中 A 本身就是 release 操作，直接用它真实的 release sequence。

**Y 不能是原子 modify-write 操作**（只在 ¶2 中出现）{{c++26}}：原子 modify-write 操作（如 `store_add`，[[atomics.order#12]]）的"读"不供程序观察，意图是用不受 acquire 栅栏排序的硬件机制实现（例如在内存控制器执行的远端原子操作）。如果允许它作为 ¶2 中的 Y，实现就必须保证后续的 acquire 栅栏能对这种操作排序，违背了引入它的初衷。

**同步的方向由栅栏的位置决定**：release 栅栏必须在写 M **之前**（A sb X），acquire 栅栏必须在读 M **之后**（Y sb B）。把栅栏放反了不建立任何关系。

### 一个栅栏服务多个标志

```cpp run title="fence-fan-in.cpp" ok
#include <atomic>
#include <cassert>
#include <thread>

int part[3];
std::atomic<bool> done[3];

int main() {
  std::jthread w[3];
  for (int i = 0; i < 3; ++i)
    w[i] = std::jthread([i] {
      part[i] = (i + 1) * 10;
      done[i].store(true, std::memory_order::release);    // A：release 操作
    });
  for (auto& d : done)
    while (!d.load(std::memory_order::relaxed)) {}        // X：relaxed 读，读到了 A 的值
  std::atomic_thread_fence(std::memory_order::acquire);   // B：acquire 栅栏
  assert(part[0] + part[1] + part[2] == 60);              // OK
}
```

这是 ¶4 的情形，用了三次：对每个 `i`，`done[i].store(release)` 与这一个 acquire 栅栏同步，于是三个 `part[i] = ...` 都 happens before 断言。若不用栅栏，就得把三次 load 都写成 `acquire`；在 x86 上二者没有区别，在 ARM 上则是"三次 `ldapr`"与"三次 `ldr` + 一次 `dmb ishld`"的差别。

!!! impl "ThreadSanitizer 与栅栏"
    TSan 对 `atomic_thread_fence` 的建模不完整。上面这个程序用 `-fsanitize=thread` 运行，Clang 23 的 TSan 会对 `part` 报告 `data race`——这是误报。[[intro.multithread]] 中的"栅栏版 MP"例子也一样。依赖栅栏的代码不能用 TSan 的沉默来证明正确，也不能用 TSan 的报告来证明错误。

## atomic_thread_fence（¶5）

¶5 `extern "C" constexpr void atomic_thread_fence(memory_order order) noexcept` 按 `order` 的值：

- ¶5.1 `relaxed`：**没有效果**；
- ¶5.2 `acquire`：是 acquire 栅栏；
- ¶5.3 `release`：是 release 栅栏；
- ¶5.4 `acq_rel`：既是 acquire 栅栏也是 release 栅栏；
- ¶5.5 `seq_cst`：是**顺序一致**的 acquire 和 release 栅栏。

`seq_cst` 栅栏除了同时是 acquire 与 release 栅栏，还是 `memory_order::seq_cst` 操作，因此参与单一全序 S，受 [[atomics.order#4]] 中 ¶4.2–¶4.4 的约束。这三条让 seq_cst 栅栏可以为它前后的非 seq_cst 操作建立 store→load 顺序：

```cpp
// x、y 初始为 0
// 线程 1                                        // 线程 2
x.store(1, relaxed);                            y.store(1, relaxed);
atomic_thread_fence(seq_cst);   // F1           atomic_thread_fence(seq_cst);   // F2
r1 = y.load(relaxed);                           r2 = x.load(relaxed);
```

`r1 == r2 == 0` 被禁止。推理：F1、F2 都在 S 中，不妨设 F1 先于 F2。若 `r2 == 0`，即 `x.load` 读到初值，那么这次 load 在 x 上 coherence-ordered before `x.store(1)`；而 F2 happens before 这次 load，`x.store(1)` happens before F1——由 ¶4.4，F2 在 S 中先于 F1，矛盾。所以 `r2 == 1`。对称地，F2 先于 F1 时 `r1 == 1`。

注意 `acq_rel` 栅栏**不能**做到这一点：它不在 S 中，release 半边只约束它之前的写、acquire 半边只约束它之后的读，"之前的写"与"之后的读"之间不受约束。这是 `acq_rel` 栅栏与 `seq_cst` 栅栏唯一但关键的区别。

## atomic_signal_fence（¶6–¶7）

¶6 `atomic_signal_fence(order)` 等价于 `atomic_thread_fence(order)`，但所建立的顺序约束**只在一个线程与同一线程中执行的信号处理函数之间**成立。

¶7 注 1：`atomic_signal_fence` 可用于指定线程的操作对信号处理函数可见的顺序。编译器优化与 load/store 的重排受到与 `atomic_thread_fence` 相同的抑制，但**不发出** `atomic_thread_fence` 会插入的硬件栅栏指令。

原理：信号处理函数在被打断的线程上执行，CPU 看自己的指令总是按程序顺序的；能打乱顺序的只有编译器。所以只需一个"编译器屏障"。在 Apple Silicon 上，`atomic_signal_fence(seq_cst)` 不生成任何指令，而 `atomic_thread_fence(seq_cst)` 生成 `dmb ish`（见 [[atomics.order]] 的映射表）。

```cpp run title="signal-fence.cpp" ok
#include <atomic>
#include <csignal>
#include <cstdio>

int data = 0;
std::atomic<bool> ready{false};      // 无锁原子：可以在信号处理函数中使用
std::atomic<int> seen{-1};

extern "C" void handler(int) {
  if (ready.load(std::memory_order::relaxed)) {
    std::atomic_signal_fence(std::memory_order::acquire);
    seen.store(data, std::memory_order::relaxed);
  }
}

int main() {
  std::signal(SIGUSR1, handler);
  data = 42;
  std::atomic_signal_fence(std::memory_order::release);   // 只约束编译器，不产生指令
  ready.store(true, std::memory_order::relaxed);
  std::raise(SIGUSR1);
  std::printf("%d\n", seen.load());                        // 42
}
```

这里用 `std::raise` 同步地触发信号只是为了演示；栅栏真正的用武之地是异步信号（如定时器信号）可能在任意两条语句之间打断主线程的场合。若去掉两个栅栏，编译器理论上可以把 `data = 42` 挪到 `ready.store` 之后，信号恰好在两者之间到来时，处理函数就会看到 `ready == true` 而 `data == 0`。

## 陷阱

!!! pitfall "栅栏不能凭空同步"
    栅栏只有在中间有一个"写 M → 读到这个写"的原子操作对时才建立同步。两个线程各自调用 `atomic_thread_fence(seq_cst)`，中间没有原子变量传递信息，什么关系也不会产生（S 中的先后本身不构成 happens before）。

!!! pitfall "acquire 栅栏要放在读之后"
    ```cpp
    std::atomic_thread_fence(std::memory_order::acquire);   // 错：放在了读之前
    while (!flag.load(std::memory_order::relaxed)) {}
    use(data);                                               // 数据竞争
    ```
    ¶2/¶4 要求 Y（或 X）sequenced before B。

!!! pitfall "atomic_signal_fence 不能用于线程间"
    它不发出硬件屏障。用它来"同步"两个线程，在 ARM 等弱序硬件上会出错；在 x86 上可能"碰巧"能用，因为 TSO 本身就很强。

## 思考题

!!! question "1. release 栅栏 A sb `x.store(1, relaxed)`；另一线程 `x.fetch_add(1, relaxed)` 读到 1、写入 2；第三个线程 `x.load(relaxed)` 读到 2，之后执行 acquire 栅栏 B。A 与 B 同步吗？"

<details markdown="1">
<summary>答案</summary>

同步。按 ¶2：X 是 `x.store(1)`，Y 是第三个线程的 load。假如 X 是 release 操作，它领头的假想 release sequence 包括其后紧接着的 RMW `fetch_add`（写入 2）；Y 读到了这个值，所以条件满足。Y 是普通 load，不是原子 modify-write 操作。如果把 `fetch_add` 换成 C++26 的 `store_add`，它仍然是 RMW，仍在假想 release sequence 中；被排除的只是"Y 本身是 modify-write 操作"的情形。
</details>

!!! question "2. 为什么 `atomic_thread_fence(memory_order::relaxed)` 没有效果，却仍然是合法调用？"

<details markdown="1">
<summary>答案</summary>

为了泛型代码的方便：一个以 `memory_order` 为参数的函数可以无条件地调用 `atomic_thread_fence(order)`，调用方传 `relaxed` 时自然退化为无操作，而不必写特殊分支。¶5.1 明确规定其没有效果，不是 UB。
</details>

## 小结

| 栅栏 | 加入的关系 |
|---|---|
| `release` | 之后的某个原子写被读到时，与读端的 acquire 栅栏/操作同步（¶2、¶3） |
| `acquire` | 之前的某个原子读读到了 release 栅栏/操作之后的写时，与之同步（¶2、¶4） |
| `acq_rel` | 两者兼有；**不**提供 store→load 顺序 |
| `seq_cst` | 两者兼有，并进入全序 S，提供 store→load 顺序（[[atomics.order#4]]） |
| `atomic_signal_fence` | 同上，但只对同线程的信号处理函数，只约束编译器 |
