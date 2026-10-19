---
title: 栅栏
summary: atomic_thread_fence 与 atomic_signal_fence：栅栏怎样和 relaxed 原子操作配合建立同步，seq_cst 栅栏比 acq_rel 栅栏多保证了什么，以及只约束编译器的 signal fence。
status: done
covers: atomics.fences
related: atomics.order, intro.races, intro.multithread, intro.execution, support.signal
tags: 标准库, 原子操作, 内存模型, 栅栏
updated: 2026-10-19
---

!!! tldr
    - 栅栏把同步和具体的原子操作分开：原子操作可以是 relaxed 的，同步由同一线程里的栅栏提供。
    - release 栅栏要放在写原子变量之前，acquire 栅栏要放在读原子变量之后；中间必须有一对写 M、读到这个写的原子操作，否则栅栏什么也不建立。
    - 一个 acquire 栅栏可以同时为前面的多次 relaxed 读补上 acquire 语义。
    - `seq_cst` 栅栏进入单一全序 S，能禁止 store→load 重排；`acq_rel` 栅栏做不到。
    - `atomic_signal_fence` 只约束编译器，只对同一线程中的信号处理函数有效，不能用于线程之间。

## 一个栅栏服务多个标志

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
      done[i].store(true, std::memory_order::release);  // A
    });
  for (auto& d : done)
    while (!d.load(std::memory_order::relaxed)) {}      // X
  std::atomic_thread_fence(std::memory_order::acquire); // B
  assert(part[0] + part[1] + part[2] == 60);            // OK
}
```

主线程先用 relaxed 读确认三个标志都已置位，再执行一次 acquire 栅栏。对每个 `i`，`done[i]` 上的 release store 都与这个栅栏同步，三次写 `part[i]` 因此都 happens before 断言。

不用栅栏也可以，但要把三次 load 都写成 `acquire`。在 x86 上两种写法生成的代码没有区别；在 ARM 上则是三次 acquire load 与三次普通 load 加一条屏障指令的区别。另一个用处是只在需要时才付同步的代价：先 relaxed 地读，读到期望的值后才加 acquire 栅栏。

栅栏和原子操作的根本区别是栅栏没有关联的内存位置（[[intro.races#3]]），它必须借助某个原子对象 M 上的一对读写才能起作用。下面三条规则规定了具体条件。

## 三条同步规则（¶1–¶4）

¶1 **栅栏**（fence）是一种同步原语，可以有 acquire 语义、release 语义或两者兼有，分别叫 **acquire 栅栏**和 **release 栅栏**。

三条规则形状相同，区别只是两端哪一端用栅栏、哪一端用原子操作（表中 sb 表示 sequenced before）：

| 段落 | release 端 | acquire 端 | 中间的连接 |
|---|---|---|---|
| ¶2 | release 栅栏 A | acquire 栅栏 B | A sb X，X 修改 M；Y 读 M，Y sb B |
| ¶3 | release 栅栏 A | M 上的 acquire 操作 B | A sb X，X 修改 M；B 读到 X 写的值 |
| ¶4 | M 上的 release 操作 A | acquire 栅栏 B | X 读到 A 写的值，X sb B |

上面的例子用的是 ¶4，用了三次。¶2 的原文是：

!!! std
    A release fence A synchronizes with an acquire fence B if there exist atomic operations X and Y, where Y is not an atomic modify-write operation, both operating on some atomic object M, such that A is sequenced before X, X modifies M, Y is sequenced before B, and Y reads the value written by X or a value written by any side effect in the hypothetical release sequence X would head if it were a release operation.

有三个细节。

**方向由栅栏的位置决定。** release 栅栏必须在写 M 之前（A sb X），acquire 栅栏必须在读 M 之后（Y sb B）。放反了不建立任何关系。

**假想的 release sequence。** 一个 release 操作领头的 **release sequence**，是修改顺序中紧随其后、连续的一串读-改-写操作（[[intro.races#5]]）；读到其中任何一个写入的值，都和读到领头的写一样能同步。¶2 和 ¶3 里的 X 可以是 relaxed 的，本身没有 release sequence，标准就假设它是 release 操作，按它会领头的序列来判断。¶4 中 A 本身是 release 操作，直接用它真实的 release sequence。

**¶2 中的 Y 不能是原子 modify-write 操作** {{c++26}}。原子 modify-write 操作（如 `store_add`）是同步要求更弱的读-改-写操作。[[atomics.order#12]] 的注说明，它们的本意是用不受 acquire 栅栏排序的硬件机制实现。如果允许它充当 ¶2 中的 Y，实现就必须让后面的 acquire 栅栏能对它排序，违背了引入它的目的。

!!! impl "ThreadSanitizer 与栅栏"
    TSan 对 `atomic_thread_fence` 的建模不完整。用 `-fsanitize=thread` 运行 `fence-fan-in.cpp`，Clang 23 的 TSan 对 `part` 报告 `data race`，这是误报。依赖栅栏的代码不能用 TSan 的沉默证明正确，也不能用它的报告证明错误。

## atomic_thread_fence（¶5）

¶5 `atomic_thread_fence(order)` 按 `order` 的值：

- ¶5.1 `relaxed`：没有效果；
- ¶5.2 `acquire`：是 acquire 栅栏；
- ¶5.3 `release`：是 release 栅栏；
- ¶5.4 `acq_rel`：既是 acquire 栅栏也是 release 栅栏；
- ¶5.5 `seq_cst`：是顺序一致的 acquire 和 release 栅栏。

`relaxed` 也是合法实参，这方便泛型代码：以 `memory_order` 为参数的函数可以无条件调用 `atomic_thread_fence(order)`，调用方传 `relaxed` 时自然退化为无操作。

### seq_cst 栅栏多保证了什么

<div class="compare" markdown="1">

```cpp
// 线程 1（x、y 初始为 0）
x.store(1, relaxed);
atomic_thread_fence(seq_cst); // F1
r1 = y.load(relaxed);
```

```cpp
// 线程 2
y.store(1, relaxed);
atomic_thread_fence(seq_cst); // F2
r2 = x.load(relaxed);
```

</div>

问题是 `r1 == 0 && r2 == 0` 是否可能。如果两个栅栏都是 `seq_cst`，这个结果被禁止。

`seq_cst` 栅栏是 `memory_order::seq_cst` 操作，参与所有 seq_cst 操作的单一全序 S，受 [[atomics.order#4]] 的约束。设 `r2 == 0`，即线程 2 的 load 读到 x 的初值，那么这次 load 在 x 上 coherence-ordered before `x.store(1)`。F2 happens before 这次 load，`x.store(1)` happens before F1，按 ¶4.4，S 中 F2 先于 F1。对称地，`r1 == 0` 意味着 S 中 F1 先于 F2。两者不能同时成立，所以 `r1`、`r2` 至少有一个是 1。

换成 `acq_rel` 栅栏就不行了。它不在 S 中，release 半边只约束它之前的写，acquire 半边只约束它之后的读，之前的写和之后的读之间没有约束。这是 `acq_rel` 栅栏与 `seq_cst` 栅栏的关键区别。

## atomic_signal_fence（¶6–¶7）

¶6 `atomic_signal_fence(order)` 等价于 `atomic_thread_fence(order)`，但建立的顺序约束只在一个线程与同一线程中执行的信号处理函数之间成立。

¶7 注 1：它可以用来规定线程的操作以什么顺序对信号处理函数可见。它像 `atomic_thread_fence` 一样抑制编译器的优化和重排，但不发出硬件栅栏指令。

原因是信号处理函数在被打断的线程上执行，CPU 看自己的指令总是按程序顺序的，能打乱顺序的只有编译器。在 Apple Silicon 上用 `-O2` 编译，`atomic_signal_fence(seq_cst)` 不生成任何指令，`atomic_thread_fence(seq_cst)` 生成一条 `dmb ish`。

```cpp run title="signal-fence.cpp" ok
#include <atomic>
#include <csignal>
#include <cstdio>

int data = 0;
std::atomic<bool> ready{false};   // 无锁原子，可在信号处理函数中使用
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
  std::atomic_signal_fence(std::memory_order::release);
  ready.store(true, std::memory_order::relaxed);
  std::raise(SIGUSR1);
  std::printf("%d\n", seen.load());   // 42
}
```

这里用 `std::raise` 同步地触发信号只是为了演示。栅栏真正需要的场合是异步信号，例如定时器信号可能在任意两条语句之间打断主线程。去掉两个栅栏，编译器可以把 `data = 42` 挪到 `ready.store` 之后，信号恰好在两者之间到来时，处理函数会看到 `ready == true` 而 `data == 0`。

## 常见误解

!!! pitfall "两个 seq_cst 栅栏本身就能同步两个线程"
    栅栏只有在中间有一对写 M、读到这个写的原子操作时才建立同步。两个线程各自调用 `atomic_thread_fence(seq_cst)`，中间没有原子变量传递信息，不会产生任何 happens before 关系；S 中的先后本身不构成 happens before。

!!! pitfall "acquire 栅栏放在读之前也可以"
    ```cpp
    std::atomic_thread_fence(std::memory_order::acquire);  // 错：在读之前
    while (!flag.load(std::memory_order::relaxed)) {}
    use(data);                                              // 数据竞争
    ```
    ¶2 和 ¶4 要求读操作 sequenced before acquire 栅栏。

!!! pitfall "atomic_signal_fence 可以当作便宜的线程栅栏"
    它不发出硬件屏障。拿它在两个线程之间同步，在 ARM 等弱序硬件上会出错；在 x86 上可能碰巧能用，因为 x86 的内存模型本身就很强。

## 思考题

!!! question "思考题"
    线程 1 执行 release 栅栏 A，再执行 `x.store(1, relaxed)`；线程 2 执行 `x.fetch_add(1, relaxed)`，读到 1、写入 2；线程 3 执行 `x.load(relaxed)` 读到 2，然后执行 acquire 栅栏 B。A 与 B 同步吗？

<details markdown="1">
<summary>答案</summary>

同步。按 ¶2，X 是 `x.store(1)`，Y 是线程 3 的 load。假如 X 是 release 操作，它领头的 release sequence 包括紧随其后的读-改-写 `fetch_add`；Y 读到了 `fetch_add` 写的值，条件满足。Y 是普通 load，不是原子 modify-write 操作。

如果把 `fetch_add` 换成 C++26 的 `store_add`，它仍然是读-改-写操作（[[atomics.order#12]]），仍在假想的 release sequence 中，结论不变。¶2 排除的只是 Y 本身是 modify-write 操作的情形。
</details>

## 小结

| 栅栏 | 作用 |
|---|---|
| `release` | 之后的某个原子写被读到时，与读端的 acquire 栅栏或 acquire 操作同步（¶2、¶3） |
| `acquire` | 之前的某个原子读读到了 release 栅栏之后的写或 release 操作的写时，与之同步（¶2、¶4） |
| `acq_rel` | 两者兼有，不禁止 store→load 重排 |
| `seq_cst` | 两者兼有，并进入全序 S，禁止 store→load 重排（[[atomics.order#4]]） |
| `atomic_signal_fence` | 同上，但只对同一线程的信号处理函数，只约束编译器 |
