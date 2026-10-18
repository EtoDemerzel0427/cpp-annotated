---
title: 信号量
summary: counting_semaphore 与 binary_semaphore——没有所有者的计数器、least_max_value 与 max()、release 的前置条件（超出 max 是 UB，libc++ 连调试模式也不检查二值信号量的溢出）、release 与观察到其结果的 try_acquire 之间的 strongly happens before、可以虚假失败的 try_acquire
status: done
covers: *
papers: P1135R6
related: thread.mutex.requirements, thread.condition, atomics.wait, thread.coord, thread.req
tags: 标准库, 并发, 信号量
updated: 2026-10-18
---

信号量是 Dijkstra 在 1960 年代提出的同步原语，比互斥量更早。C++ 直到 C++20（[[P1135R6]]）才把它标准化。与互斥量的本质区别：**信号量没有所有者**。任何线程都可以 `release`，不论它是否 `acquire` 过。这让它适合做"信号"（一个线程通知另一个线程）和"资源计数"（最多 N 个线程同时访问）。

本页覆盖 [thread.sema] 的全部子条款。

## 总述（[thread.sema.general]）

¶1 信号量是轻量级同步原语，用来限制对共享资源的并发访问。它们被广泛用于实现其他同步原语；在两者都适用时，可能比条件变量更高效。

¶2 **计数信号量**模拟一个非负的资源计数。**二值信号量**只有两个状态。二值信号量应当比计数信号量在资源计数为 1 时的默认实现更高效。

"可能比条件变量更高效"的原因：信号量把"条件"（计数是否为正）和"等待机制"做在一起，不需要额外的互斥量——`release` 和 `acquire` 在无争用时都只是一次原子操作。

## 概要（[semaphore.syn]）

```cpp
template<ptrdiff_t least_max_value = implementation-defined>
  class counting_semaphore;
using binary_semaphore = counting_semaphore<1>;
```

`least_max_value` 的默认值由实现定义 {{impl}}。二值信号量就是 `least_max_value` 为 1 的计数信号量，"应当更高效"只是建议，实现可以（libc++ 就是）对二者使用同一份代码。

## counting_semaphore（[thread.sema.cnt]）

类定义：`static constexpr ptrdiff_t max() noexcept;`、`constexpr explicit` 构造函数、析构函数、删除的复制操作、`release`、`acquire`、`try_acquire`、`try_acquire_for`、`try_acquire_until`；仅说明用成员 `ptrdiff_t counter`。

¶1 维护一个内部计数器，在创建时初始化。线程**获取**信号量时计数器减一，**释放**时加一。计数器为零时试图获取的线程会阻塞，直到另一个线程通过释放增加计数器。

¶2 `least_max_value` 必须非负，否则程序非良构。

¶3 **除析构函数外，对成员函数的并发调用不引入数据竞争。** 注意这只是"不竞争"，具体的同步关系在 `release` 的 *Synchronization* 中单独规定。

### max() 与构造（¶4–¶7）

- ¶4 `max()` 返回 `counter` 的最大值，**大于等于** `least_max_value`。即模板实参是下界，实现可以支持更大的值。
- ¶5 构造函数 *Preconditions*：`desired >= 0` 且 `desired <= max()`。¶6 用 `desired` 初始化计数器。¶7 不抛异常。

### release（¶8–¶12）

`void release(ptrdiff_t update = 1);`

- ¶8 *Preconditions*：`update >= 0`，且 `update <= max() - counter`。
- ¶9 *Effects*：原子地执行 `counter += update`。然后解除那些等待 `counter` 大于零的线程的阻塞。
- ¶10 *Synchronization*：**strongly happens before** 观察到其效果的 `try_acquire` 调用。
- ¶11–¶12 需要时抛 `system_error`；错误条件为互斥量类型允许的任何错误条件。

¶8 的第二个条件是本类最容易违反的前置条件：**计数器加上 `update` 不能超过 `max()`**。对 `binary_semaphore` 来说，计数器已经是 1 时再 `release()` 就是 UB {{ub}}——"重复发出信号"在二值信号量上不是无害的空操作。

```cpp title="binary-overflow.cpp" ub
#include <cstdio>
#include <semaphore>
int main() {
  std::binary_semaphore s{1};
  s.release();                          // UB：counter 将变为 2 > max() == 1（¶8）
  std::printf("max=%td try1=%d try2=%d\n", s.max(), s.try_acquire(), s.try_acquire());
}
```

!!! impl "libc++ 不检查"
    这个程序在 libc++ 下打印 `max=1 try1=1 try2=1`：二值信号量被"获取"了两次，计数器实际上达到了 2。即使用 `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_DEBUG` 编译也一样——libc++ 的断言检查的是"不超过 `ptrdiff_t` 的最大值"，而不是 `max()`。对 `binary_semaphore` 而言，`max()` 返回 1，但内部实现与默认的 `counting_semaphore` 完全相同。

¶10 用的是 **strongly happens before**（[[intro.races]] ¶8），比 synchronizes with 推出的 happens before 更强：它还参与 seq_cst 全序 S 的约束（[[atomics.order#4]]）。对于只用信号量传递数据的程序，效果就是"`release` 之前的写对观察到这次 `release` 的获取者可见"。

### try_acquire 与 acquire（¶13–¶17）

`bool try_acquire() noexcept;`

- ¶13 *Effects*：若 `counter` 为正，尝试不阻塞地原子地将其减一。若未减，则无效果，立即返回。**即使 `counter` 为正，实现也可以减不成功。** 注 1：这种虚假失败通常不常见，但允许基于简单 CAS 的实现。实现应当保证在没有竞争的信号量操作时 `try_acquire` 不会一直返回 `false`。
- ¶14 *Returns*：减成功返回 `true`。

`void acquire();`

- ¶15 *Effects*：反复执行：(15.1) 求值 `try_acquire()`，结果为 `true` 则返回；(15.2) 阻塞在 `*this` 上，直到 `counter` 大于零。
- ¶16–¶17 需要时抛 `system_error`。

`acquire` 被定义为 `try_acquire` 的循环，所以 ¶10 的同步规则自动覆盖了它：`acquire` 返回，意味着它内部某次 `try_acquire` 观察到了某次 `release` 的效果。

### 带超时的获取（¶18–¶20）

`try_acquire_for(rel_time)`、`try_acquire_until(abs_time)`：

- ¶18 反复执行：(18.1) `try_acquire()` 为 `true` 则返回 `true`；(18.2) 阻塞，直到 `counter` 大于零或超时到期；因超时到期而解除阻塞则返回 `false`。超时到期的含义：`try_acquire_until` 是当前时间晚于 `abs_time`；`try_acquire_for` 是从函数开始起**至少**经过了 `rel_time`。
- ¶19 抛超时相关异常，或需要时抛与超时无关的 `system_error`。

## 用法

### 一次性信号

```cpp run title="semaphore-signal.cpp" ok
#include <cassert>
#include <semaphore>
#include <thread>

std::binary_semaphore ready{0};
int data = 0;

int main() {
  std::jthread t([] {
    ready.acquire();       // 阻塞直到 release
    assert(data == 1);     // OK：release strongly happens before 观察到它的 try_acquire
  });
  data = 1;
  ready.release();         // 由另一个线程释放：信号量没有所有者
}
```

用 `std::mutex` 做同样的事是 UB：在主线程 `lock`、在 `t` 里 `unlock` 违反"调用线程拥有互斥量"的前置条件（[[thread.mutex.requirements]]）。

### 限制并发数

```cpp run title="semaphore-limit.cpp" ok
#include <atomic>
#include <cassert>
#include <semaphore>
#include <thread>
#include <vector>

std::counting_semaphore<3> slots{3};       // 最多 3 个线程同时进入
std::atomic<int> inside{0}, peak{0};

void work() {
  slots.acquire();
  int now = ++inside;
  int p = peak.load();
  while (now > p && !peak.compare_exchange_weak(p, now)) {}
  --inside;
  slots.release();
}

int main() {
  {
    std::vector<std::jthread> ts;
    for (int i = 0; i < 16; ++i) ts.emplace_back(work);
  }
  assert(peak.load() <= 3);
}
```

## 实现视角

!!! impl "libc++ 的 counting_semaphore（`<semaphore>`）"
    - 内部只有一个 `atomic<ptrdiff_t>`，所以 `sizeof` 为 8；`max()` 直接返回模板实参 `least_max_value`，默认值是 `PTRDIFF_MAX`。
    - `release(n)`：`fetch_add(n, release)`；只有当旧值为 0（可能有线程在等）时才 `notify_all()`。
    - `try_acquire()`：relaxed 读当前值，为 0 则失败，否则 `compare_exchange_weak(old, old - 1, acquire, relaxed)` 循环——注意这个循环只在 CAS 因竞争失败时重试，不会把计数器为正的情况误报为失败，所以 libc++ 实际上不产生 ¶13 允许的虚假失败。
    - `acquire()`：用 [[atomics.wait]] 中的"自旋 + 退避 + 平台等待"框架，等待条件"计数器非零且 CAS 成功"。
    - `release` 的 release 与 `try_acquire` 成功时的 acquire 构成 [[atomics.order#2]] 的同步，满足 ¶10。

## 陷阱

!!! pitfall "二值信号量不是“可重复设置的标志”"
    对已经是 1 的 `binary_semaphore` 再 `release()` 是 UB（¶8），不会被饱和到 1。需要"设置标志（幂等）+ 唤醒"的语义时，用 `atomic<bool>` 配合 `wait`/`notify`（[[atomics.wait]]），或者条件变量。

!!! pitfall "信号量不防止优先级反转，也不提供所有权诊断"
    正因为没有所有者，实现无法做优先级继承，也无法检测"忘了释放"或"释放了别人的"。用信号量当互斥量用时，这些都是代价。

## 小结

- 信号量没有所有者：任何线程都可以 `release`。
- `max() >= least_max_value`；`release` 使计数器超过 `max()` 是 UB，对二值信号量尤其要小心。
- `release` strongly happens before 观察到其效果的 `try_acquire`（因而也包括 `acquire`）。
- `try_acquire` 可以虚假失败；`acquire` 是它的循环加阻塞。
