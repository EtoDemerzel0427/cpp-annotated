---
title: 原子等待与通知
summary: atomic::wait / notify_one / notify_all 的规范模型——等待操作按值比较、可以虚假解除阻塞、ABA 问题，"有资格被解除阻塞"（eligible to be unblocked）的三个条件如何排除丢失唤醒；通知本身不同步；libc++ 在 macOS 上的自旋 + os_sync_wait_on_address + 全局等待表实现
status: done
covers: atomics.wait
papers: P1135R6
related: atomics.types.operations, atomics.flag, atomics.ref.ops, util.smartptr.atomic, thread.sema, thread.coord, thread.condition, atomics.alias
tags: 标准库, 原子操作, 等待, futex
updated: 2026-10-18
---

C++20 之前，一个线程要等待某个原子变量变成特定值，只有两种选择：空转轮询（浪费 CPU），或者另配一个 `mutex` + `condition_variable`（笨重，且必须小心地把原子变量的修改放进锁里，否则会丢失唤醒）。[[P1135R6]] 给原子类型加上了 `wait`/`notify`，语义上类似 Linux 的 futex：**等到值不再是 `old` 为止**。

[atomics.wait] 本身只有四段，定义了两个概念：**原子等待操作**和**原子通知操作**，以及它们之间"谁能唤醒谁"的规则。各个类型的成员函数（[[atomics.types.operations]] ¶29–¶38、[[atomics.ref.ops]] ¶28–¶36、[[atomics.flag]] ¶13–¶20、[[util.smartptr.atomic]]）都引用这里。

## 目的（¶1）

¶1 原子等待操作与原子通知操作提供一种机制，用来等待原子对象的值改变，**比轮询更高效**。原子等待操作可以阻塞，直到被原子通知操作按各函数的 *Effects* 解除阻塞。

注 1：程序**不保证**能观察到**瞬时的**原子值——这就是 A-B-A 问题——所以如果条件只是暂时满足，等待可能继续阻塞。

例如等待者调用 `a.wait(0)`；另一个线程先 `a.store(1)` 再 `a.store(0)`，然后 `notify_one()`。等待者醒来后重新读到 0，与 `old` 相等，于是**继续阻塞**。值"曾经"是 1 这件事丢失了。需要观察每一次变化时，应当用单调递增的计数器（"世代号"）而不是可能回到原值的标志。

## 哪些函数是等待/通知操作（¶2–¶3）

¶2 注 2 列出原子等待操作：`atomic<T>::wait`、`atomic_flag::wait`、`atomic_wait`、`atomic_wait_explicit`、`atomic_flag_wait`、`atomic_flag_wait_explicit`、`atomic_ref<T>::wait`。

¶3 注 3 列出原子通知操作：上述各类型的 `notify_one`、`notify_all` 及其非成员版本。

它们都是注（非规范）——规范性的认定写在每个函数的 *Remarks* 里，如"This function is an atomic waiting operation"。

## wait 的效果（以 atomic<T> 为例）

[[atomics.types.operations]] ¶31 规定 `wait(old, order)` **反复**执行：

1. 求值 `load(order)`，把结果的**值表示**与 `old` 的值表示比较（逐字节比较，同 `compare_exchange`）；
2. 不相等则返回；
3. 阻塞，直到被原子通知操作解除阻塞，**或者虚假地解除阻塞**。

三点推论：

- **虚假唤醒被函数自己吸收了**：解除阻塞后会回到第 1 步重新比较。所以 `wait` 返回时，必然读到过一个与 `old` 不同的值——不需要像 `condition_variable::wait` 那样由调用者再套一层循环（但如果你等的是"某个特定值"，仍需要循环，见下面的例子）。
- **内存序作用于第 1 步的 load**：`wait(old, acquire)` 中那次读到新值的 load 是 acquire 操作，若它读到的是 release store 写入的值，就与该 store 同步（[[atomics.order#2]]）。前置条件同 `load`：不能是 `release` 或 `acq_rel`。
- **按值表示比较**：对有填充位的类型、浮点的 `+0.0`/`-0.0` 等，"值相等"与"值表示相等"不同，规则与 `compare_exchange` 相同（[[atomics.types.operations]] ¶28 注 6）。

`notify_one()`（¶34）：解除**至少一个**"有资格被此次调用解除阻塞"的等待操作的阻塞（若存在）。`notify_all()`（¶37）：解除**所有**有资格者的阻塞。

## 有资格被解除阻塞（¶4）

¶4 是本节的核心。对原子对象 M 的一次原子等待操作，**有资格被**对 M 的一次原子通知操作**解除阻塞**（[[g:eligible-to-be-unblocked]]，eligible to be unblocked），若存在 M 上的副作用 X 和 Y，使得：

- ¶4.1 等待操作在**观察到 X 的结果之后**阻塞；
- ¶4.2 X 在 M 的修改顺序中**先于** Y；
- ¶4.3 Y **happens before** 这次通知操作的调用。

用人话说：**你在看到旧值之后睡下，而通知者在通知之前已经写入了一个更新的值，那么这次通知必须能唤醒你。**

这一定义的妙处在于它**排除了丢失唤醒**，却不需要锁。考虑经典的竞争：

```text
等待者                              通知者
-----------------------------       -----------------------------
v = a.load()      // 读到 X = 0
                                    a.store(1)        // Y
                                    a.notify_one()
（检查 v == 0，准备阻塞）
阻塞
```

用 `condition_variable` 而不加锁，这正是丢失唤醒的典型场景：通知发生在等待者真正睡下之前。但按 ¶4，等待者"在观察到 X 之后阻塞"，X 先于 Y，Y happens before 通知——等待者**有资格**被这次通知唤醒，即使通知在时间上先于阻塞发生。实现必须保证这一点（实际做法是：内核的"按地址等待"系统调用会在睡眠前原子地重新检查值，或者实现维护一个"通知计数"在阻塞前比较）。

反过来，以下情况**没有**资格：

- **没有修改**：通知者不修改 M 就调用 `notify_one()`。不存在 Y，等待者可能一直睡下去。所以"先通知、后修改"是错误的。
- **修改不 happens before 通知**：在另一个线程修改 M，而通知线程与它没有同步关系。
- **等待者看到的就是最新值之后的值**：等待者观察到的是 Y 本身（或更晚的值）——但那样的话 `wait` 根本不会阻塞（值与 `old` 不同）。

```cpp run title="wait-notify.cpp" ok
#include <atomic>
#include <cassert>
#include <thread>

std::atomic<int> state{0};
int payload = 0;

int main() {
  std::thread consumer([] {
    state.wait(0, std::memory_order::acquire);   // 值不再是 0 才返回
    assert(payload == 42);                        // OK：读到新值的 load(acquire) 与 store(release) 同步
  });
  payload = 42;
  state.store(1, std::memory_order::release);    // Y：先修改
  state.notify_one();                             // 再通知：Y happens before 通知（sequenced before）
  consumer.join();
}
```

!!! note "通知不是同步操作"
    `notify_one`/`notify_all` 没有 `memory_order` 参数，也没有 *Synchronization* 元素。上例中 `payload` 的可见性**完全**来自 `store(release)` 与 `wait` 内部 `load(acquire)` 之间的同步，与 `notify_one()` 无关。通知只影响"是否阻塞"，不影响"看到什么"。

### 等待特定值

`wait(old)` 只能表达"不等于 `old`"。要等到 `state == 3`，需要自己写循环：

```cpp
int v = state.load(std::memory_order::acquire);
while (v != 3) {
  state.wait(v, std::memory_order::acquire);     // 等它离开当前看到的值
  v = state.load(std::memory_order::acquire);
}
```

注意传给 `wait` 的是**刚刚看到的值** `v`，而不是固定的某个值——否则在值从 1 变成 2 时，`wait(1)` 会返回，但 `wait(0)` 会立即返回导致空转。

## 实现视角

!!! impl "libc++（Clang 23）在 macOS 上的实现"
    `wait` 的实现（`<__atomic/atomic_sync.h>`）分三个阶段：

    1. **快速轮询**：连续 load 并比较 64 次；
    2. **自旋**：继续轮询，直到自开始起经过约 4 微秒；
    3. **阻塞**：调用 libc++ 动态库中的平台等待函数。

    第 3 步分两种情况：

    - 若类型的大小、对齐恰好是平台原生等待支持的类型，就**直接在原子对象的地址上**等待。在默认的 ABI 版本 1 下，这只包括 libc++ 的"contention 类型"——macOS 上是 `int64_t`；
    - 否则使用一张**全局等待表**：按对象地址散列到表中一个 `int64_t` 计数器上，在计数器上等待；`notify` 时递增计数器再唤醒。不同对象可能散列到同一个槽位，所以会出现额外的虚假唤醒（被 `wait` 的循环吸收）。

    libc++ 的动态库在 macOS 上导入的是 `os_sync_wait_on_address` / `os_sync_wake_by_address_any` / `os_sync_wake_by_address_all`（可以用 `nm -u libc++.1.dylib` 验证）。

    由此有两个实际结论：在 macOS 上，`atomic<long long>`（即 `atomic_signed_lock_free`，见 [[atomics.alias]]）的等待最直接；`atomic<int>`、`atomic<bool>` 也能用，但会经过全局表。全局表在进程内，所以**跨进程**的 `wait`/`notify` 对这些类型不起作用。

!!! impl "ABI 版本 2"
    libc++ 的 ABI v2 定义了 `_LIBCPP_ABI_ATOMIC_WAIT_NATIVE_BY_SIZE`：此时只要类型的大小（macOS 上为 4 或 8 字节）、对齐合适，且具有唯一对象表示，就直接在对象地址上等待。默认的 v1 为了二进制兼容没有启用这一点。

## 陷阱

!!! pitfall "先通知后修改"
    ```cpp
    flag.notify_one();
    flag.store(true);     // 错：通知时还没有 Y，等待者可能永远不会醒
    ```
    ¶4.3 要求修改 happens before 通知。

!!! pitfall "用 relaxed 等待去\"发布\"数据"
    `wait(old, relaxed)` 返回只说明值变了，不建立同步。要读取对方在修改前写入的普通数据，`wait` 必须用 `acquire`（或之后接一个 acquire 栅栏），修改必须用 `release`。

!!! pitfall "ABA"
    `wait(0)` 期间值经历 0→1→0，等待者可能完全错过（注 1）。用递增的版本号代替布尔标志。

## 与其他同步原语的关系

C++20 的其余同步库组件大都可以用 `wait`/`notify` 实现，libc++ 也确实如此：

- `counting_semaphore`（[[thread.sema]]）：一个 `atomic<ptrdiff_t>` 计数器，`acquire` 在计数为 0 时 `wait(0)`；
- `latch`（[[thread.coord]]）：计数器减到 0 时 `notify_all`；
- `barrier`：阶段号是一个原子变量，等待者 `wait(旧阶段号)`；
- `atomic_flag` 可以写出不空转的自旋锁（[[atomics.flag]]）。

## 小结

- `wait(old)`：反复"load 并按值表示比较，相等则阻塞"；虚假唤醒在内部被吸收；返回时必然看到过不同的值。
- 有资格被唤醒 = 阻塞前看到的修改 X ＜ 通知前已发生的修改 Y（修改顺序）。所以**先修改、后通知**，就不会丢失唤醒。
- 通知不同步；可见性来自 `wait` 内部 load 与修改之间的 release/acquire。
- 中间值可能被错过（ABA）。
