---
title: 原子等待与通知
summary: atomic 的 wait、notify_one、notify_all 怎样工作：wait 按值比较并自己处理虚假唤醒，通知必须在修改之后，通知本身不同步，中间值可能被错过。
status: done
covers: atomics.wait
papers: P1135R6
related: atomics.types.operations, atomics.flag, atomics.ref.ops, util.smartptr.atomic, thread.sema, thread.coord, thread.condition, atomics.alias
tags: 标准库, 原子操作, 等待, futex
updated: 2026-10-19
---

!!! tldr
    - `a.wait(old)` 一直阻塞到 `a` 的值不再等于 `old`；虚假唤醒由函数内部的循环吸收，返回时一定读到过不同的值。
    - 先修改、再通知：只要修改 happens before 通知，在修改之前看到旧值并睡下的等待者就一定会被这次通知唤醒，不会丢失唤醒。
    - 通知不是同步操作。数据的可见性来自 `wait` 内部的 acquire load 与修改方 release store 之间的同步。
    - 值经历 0→1→0 这样的短暂变化时，等待者可能完全错过（ABA 问题），需要观察每次变化时用递增的计数器。

## 一个最小例子

C++20 之前，一个线程要等原子变量变成某个值，要么空转轮询，浪费 CPU；要么另配一个 `mutex` 和 `condition_variable`，还要把对原子变量的修改放进锁里，否则可能丢失唤醒。[[P1135R6]] 给原子类型加上了 `wait` 和 `notify`，语义接近 Linux 的 futex。

```cpp run title="wait-notify.cpp" ok
#include <atomic>
#include <cassert>
#include <thread>

std::atomic<int> state{0};
int payload = 0;

int main() {
  std::thread consumer([] {
    state.wait(0, std::memory_order::acquire);  // 值不再是 0 才返回
    assert(payload == 42);                      // OK
  });
  payload = 42;
  state.store(1, std::memory_order::release);   // 先修改
  state.notify_one();                           // 再通知
  consumer.join();
}
```

`consumer` 阻塞到 `state` 不再是 0。`payload` 的可见性来自 `store(release)` 与 `wait` 内部那次读到 1 的 `load(acquire)` 之间的同步（[[atomics.order#2]]），和 `notify_one` 无关。用 ThreadSanitizer 运行没有报告。

## 两类操作（¶1–¶3）

¶1 **原子等待操作**（atomic waiting operation）和**原子通知操作**（atomic notifying operation）提供一种等待原子对象的值改变的机制，比轮询更高效。等待操作可以阻塞，直到按各函数的 *Effects* 被通知操作解除阻塞。

¶2–¶3 两个注列出了哪些函数属于这两类：

| 等待操作 | 通知操作 |
|---|---|
| `atomic<T>::wait`、`atomic_ref<T>::wait` | 两者的 `notify_one`、`notify_all` |
| `atomic_flag::wait` | `atomic_flag::notify_one`、`notify_all` |
| 非成员的 `atomic_wait(_explicit)`、`atomic_flag_wait(_explicit)` | 非成员的 `atomic_notify_*`、`atomic_flag_notify_*` |

这两个列表只是注。规范性的认定写在每个函数的 *Remarks* 里，例如 [[atomics.types.operations#32]]。`atomic<shared_ptr<T>>` 的 `wait` 也在其中（[[util.smartptr.atomic]]）。

## wait 做了什么

以 `atomic<T>` 为例，[[atomics.types.operations#31]] 规定 `wait(old, order)` 反复执行三步：

1. 求值 `load(order)`，把结果的值表示与 `old` 的值表示比较；
2. 不相等就返回；
3. 阻塞，直到被通知操作解除阻塞，或者虚假地解除阻塞，然后回到第 1 步。

由此可以得到三点：

- 虚假唤醒由 `wait` 自己处理：醒来后会重新比较。调用者不需要像使用 `condition_variable::wait` 那样再套一层循环。
- 内存序作用在第 1 步的 load 上。`wait(old, acquire)` 中读到新值的那次 load 是 acquire 操作。前置条件与 `load` 相同，`order` 不能是 `release` 或 `acq_rel`。
- 比较的是值表示，规则和 `compare_exchange` 相同。浮点的 `+0.0` 与 `-0.0` 值相等但表示不同，见 [[atomics.types.operations#28]]。

`notify_one()` 解除至少一个有资格被这次调用解除阻塞的等待操作（[[atomics.types.operations#34]]）；`notify_all()` 解除全部有资格者（¶37）。什么叫有资格，由本节 ¶4 定义。

## 谁能被唤醒（¶4）

¶4 对原子对象 M 的一次等待操作，如果存在 M 上的两个副作用 X 和 Y 满足下面三条，这次等待就**有资格被**对 M 的一次通知操作**解除阻塞**（[[g:eligible-to-be-unblocked]]）：

- ¶4.1 等待操作在观察到 X 的结果之后阻塞；
- ¶4.2 在 M 的修改顺序中 X 先于 Y；
- ¶4.3 Y happens before 这次通知调用。

换句话说：等待者看到某个值之后睡下，通知者在通知之前已经写入了更新的值，那么这次通知必须能唤醒它。

这个定义不用锁就排除了丢失唤醒。看下面的交错：

```text
等待者                          通知者
v = a.load()     // 读到 X = 0
                                a.store(1)      // Y
                                a.notify_one()
（v == 0，准备阻塞）
阻塞
```

用 `condition_variable` 而不加锁，这正是典型的丢失唤醒：通知发生在等待者真正睡下之前。按 ¶4，等待者在观察到 X 之后阻塞，X 先于 Y，Y happens before 通知，所以它有资格被唤醒，即使通知在时间上早于阻塞。实现必须做到这一点，常见做法是让内核的按地址等待调用在睡眠前原子地重新检查值。

反过来，下面两种情况等待者没有资格被唤醒，可能一直睡下去：

- 通知者没有修改 M 就调用 `notify_one()`，不存在 Y。
- 修改发生在另一个线程，与通知线程没有 happens before 关系。

## 等待某个特定值

`wait(old)` 只能表达不等于 `old`。要等到 `stage == 3`，需要自己写循环，并且每次把刚看到的值传给 `wait`：

```cpp run title="wait-for-value.cpp" ok
#include <atomic>
#include <cstdio>
#include <thread>

std::atomic<int> stage{0};

void wait_until(int target) {
  int v = stage.load(std::memory_order::acquire);
  while (v != target) {
    stage.wait(v, std::memory_order::acquire);
    v = stage.load(std::memory_order::acquire);
  }
}

int main() {
  std::thread t([] { wait_until(3); std::puts("stage 3"); });
  for (int i = 1; i <= 3; ++i) {
    stage.store(i, std::memory_order::release);
    stage.notify_all();
  }
  t.join();
}
```

如果循环里固定写 `stage.wait(0)`，那么值变成 1 之后，每次 `wait(0)` 都会立即返回，循环退化成空转。

## 中间值可能被错过（¶1 注 1）

¶1 的注 1 提醒：程序不保证能观察到短暂出现的原子值，这就是 **ABA 问题**。条件只是暂时满足时，等待可能继续阻塞。

例如等待者调用 `a.wait(0)`；另一个线程先 `a.store(1)`、再 `a.store(0)`，然后通知。等待者醒来重新读到 0，与 `old` 相等，于是继续阻塞，值曾经是 1 这件事丢失了。需要观察每一次变化时，用单调递增的计数器（世代号），不要用会回到原值的标志。

## 实现视角

!!! impl "libc++ 在 macOS 上的实现（Clang 23）"
    `wait` 的实现（`<__atomic/atomic_sync.h>`）分三个阶段：先连续 load 并比较 64 次；再继续轮询，直到累计约 4 微秒；最后调用 libc++ 动态库中的平台等待函数阻塞。

    阻塞时分两种情况。类型的大小和对齐与 libc++ 的 contention 类型（macOS 上是 `int64_t`）一致时，直接在原子对象的地址上等待。否则使用一张全局等待表：按对象地址散列到表里的一个 `int64_t` 计数器，在计数器上等待，`notify` 时递增计数器再唤醒。不同对象可能散列到同一槽位，带来额外的虚假唤醒，由 `wait` 的循环吸收。

    macOS 上的系统调用是 `os_sync_wait_on_address` 和 `os_sync_wake_by_address_any`/`_all`，可以用 `nm -u` 查看 libc++ 动态库的导入符号验证。

    实际结论：在 macOS 上，`atomic<long long>`（即 `atomic_signed_lock_free`，[[atomics.alias]]）的等待最直接；`atomic<int>`、`atomic<bool>` 也能用，但要经过全局表。全局表在进程内，所以这些类型的跨进程 `wait`/`notify` 不起作用。libc++ 的 ABI 版本 2 改为按大小判断，4 或 8 字节、具有唯一对象表示的类型都可以直接在对象地址上等待；默认的版本 1 为了二进制兼容没有这样做。

## 与其他同步原语的关系

C++20 的其他同步组件大都可以用 `wait`/`notify` 实现，libc++ 也确实如此：

- `counting_semaphore`（[[thread.sema]]）：计数为 0 时 `wait(0)`；
- `latch`（[[thread.coord]]）：计数器减到 0 时 `notify_all`；
- `barrier`：等待者对阶段号执行 `wait(旧阶段号)`；
- 用 `atomic_flag` 可以写出不空转的自旋锁（[[atomics.flag]]）。

## 常见误解

!!! pitfall "先通知后修改"
    ```cpp
    flag.notify_one();
    flag.store(true);   // 错：通知时还没有 Y
    ```
    ¶4.3 要求修改 happens before 通知。这样写，等待者可能永远不会醒。

!!! pitfall "用 relaxed 的 wait 读取对方发布的数据"
    `wait(old, relaxed)` 返回只说明值变了，不建立同步。要读取对方在修改之前写入的普通数据，`wait` 要用 `acquire`（或之后加一个 acquire 栅栏），修改要用 `release`。

!!! pitfall "通知会带来可见性"
    `notify_one`/`notify_all` 没有内存序参数，也没有 *Synchronization* 条款。通知只决定等待者是否醒来，不决定它能看到什么。

## 思考题

!!! question "思考题"
    线程 A 执行 `x.store(1, relaxed); x.notify_one();`，线程 B 执行 `x.wait(0, relaxed);`。B 一定会返回吗？返回后能读到 A 在 store 之前写的普通变量吗？

<details markdown="1">
<summary>答案</summary>

一定会返回。如果 B 阻塞前看到的是 0（X 是初始化），A 的 store 是 Y，在修改顺序中位于 X 之后，并且 sequenced before 通知，所以 B 有资格被唤醒（¶4）；如果 B 看到的已经是 1，`wait` 根本不阻塞。

但 B 不能读那个普通变量：两边都是 relaxed，没有同步，读取构成数据竞争。把 store 改成 `release`、wait 改成 `acquire` 才行。
</details>
