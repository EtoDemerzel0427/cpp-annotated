---
title: 并发支持库
summary: 第 32 章导读——线程、停止令牌、原子操作、互斥量、条件变量、信号量、latch/barrier、future、安全回收这十组组件怎样建立在 [intro.multithread] 的内存模型之上；读本章时 Synchronization 元素与"前置条件即 UB"各意味着什么
status: done
covers: thread.general
related: intro.multithread, intro.progress, structure.specifications, thread.req, atomics, thread.mutex
tags: 标准库, 并发, 导读
updated: 2026-10-18
---

核心语言在 [[intro.multithread]] 里只定义了一套抽象的关系——sequenced before、synchronizes with、happens before、修改顺序——并宣布"数据竞争是 UB"。但核心语言本身**没有任何创建线程或建立同步的手段**：没有 `spawn` 关键字，也没有内建锁。所有能真正产生 synchronizes with 边的东西都在本章。可以把本章理解为内存模型的"驱动程序"：

- `std::thread` 的构造与 `join` 是最粗的两条边（[[thread.threads]]）；
- 原子操作的 `memory_order` 决定一次 load/store 往关系图里添哪些边（[[atomics.order]]）；
- 互斥量的 `unlock` 与随后的 `lock` 同步（[[thread.mutex.requirements]]）；
- 条件变量、信号量、latch、barrier、future 都在自己的 *Synchronization* 元素里写明它们建立什么关系。

读前需要：[[intro.races]]（关系的定义）、[[intro.progress]]（阻塞、前进保证）、[[structure.specifications]]（库函数说明里各个元素的法律效力）。

## 本章地图（[thread.general] ¶1）

¶1 只有一句话和一张表（表 154），列出各子条款与头文件：

| 子条款 | 内容 | 头文件 | 本站笔记 |
|---|---|---|---|
| [thread.req] | 本章通用要求：异常、native handle、超时规格、*Cpp17Lockable* 系列要求 | — | [[thread.req]] |
| [thread.stoptoken] | `stop_token`、`stop_source`、`stop_callback`，以及 C++26 的 `inplace_stop_*`、`never_stop_token` | `<stop_token>` | [[thread.stoptoken]] |
| [thread.threads] | `thread`、`jthread`、`this_thread` | `<thread>` | [[thread.threads]] |
| [atomics] | `memory_order`、`atomic<T>`、`atomic_ref<T>`、`atomic_flag`、栅栏、等待/通知、C 兼容头 | `<atomic>`、`<stdatomic.h>` | [[atomics]] 及其子页 |
| [thread.mutex] | 六种互斥量、`lock_guard`/`scoped_lock`/`unique_lock`/`shared_lock`、`std::lock`、`call_once` | `<mutex>`、`<shared_mutex>` | [[thread.mutex]] 及其子页 |
| [thread.condition] | `condition_variable`、`condition_variable_any` | `<condition_variable>` | [[thread.condition]] |
| [thread.sema] | `counting_semaphore`、`binary_semaphore` | `<semaphore>` | [[thread.sema]] |
| [thread.coord] | `latch`、`barrier` | `<latch>`、`<barrier>` | [[thread.coord]] |
| [futures] | `promise`、`future`、`shared_future`、`packaged_task`、`async` | `<future>` | [[futures]] |
| [saferecl] | RCU、hazard pointer {{c++26}} | `<rcu>`、`<hazard_pointer>` | [[saferecl]] |

## 读本章时要盯住的三种元素

### Synchronization：唯一能添"同步边"的地方

[[structure.specifications]] ¶3.7 规定 *Synchronization* 元素给出"适用于该函数的同步操作"。本章几乎每个阻塞函数都有这一项，而它的措辞决定了你能推出什么：

| 措辞 | 例子 | 能推出什么 |
|---|---|---|
| A **synchronizes with** B | `thread` 构造完成 → 线程函数开始；`unlock()` → 后续 `lock()` | A happens before B（[[intro.races#7]]），进而 A 之前的写对 B 之后的读可见（¶9–¶10） |
| A **strongly happens before** B | `latch::count_down` → 被唤醒的 `wait` 返回；`semaphore::release` → 观察到结果的 `try_acquire` | 比 happens before 更强（[[intro.races#8]]），还参与 seq_cst 全序 S 的约束（[[atomics.order#4]]） |
| "do not introduce data races" | 对同一个 `stop_source` 并发调 `request_stop`；`counting_semaphore` 的成员 | **只**保证这些调用彼此不构成数据竞争，**不**附带任何同步 |
| *Synchronization*: None | `this_thread::yield`、`sleep_for` | 明确声明：睡一觉不会让别的线程的写变得可见 |

最后两行特别容易被误读。"do not introduce data races" 是一个比"同步"弱得多的承诺：两个线程同时调用 `promise::get_future()` 与 `set_value()` 不会出事，但这不等于 `set_value` 之前写的普通变量对 `get_future` 的调用者可见。

```cpp run title="sleep-is-not-sync.cpp" ub
#include <chrono>
#include <thread>
int data = 0;
int main() {
  std::thread t([] { data = 1; });
  std::this_thread::sleep_for(std::chrono::seconds(1));
  int r = data;   // UB：sleep_for 没有同步，读与 t 中的写构成数据竞争
  (void)r;
  t.join();
}
```

即使实际运行时线程早已写完，按 [[intro.races#17]] 这仍然是数据竞争：两次冲突访问之间没有 happens before。把 `int r = data;` 挪到 `t.join()` 之后才正确——[[thread.thread.member#4]] 规定线程完成 synchronizes with `join()` 的返回。

### Preconditions：违反即 UB

[[structure.specifications]] ¶3.4 规定违反 *Preconditions* 是未定义行为 {{ub}}。本章的前置条件大多关于**所有权**：

- 解锁一个自己不拥有的互斥量（[[thread.mutex.requirements]]）；
- 对 `std::mutex` 重复加锁；
- 销毁一个还有线程在上面等待的 `condition_variable`（[[thread.condition]]）；
- `counting_semaphore::release` 让计数器超过 `max()`（[[thread.sema]]）。

实现通常**不检查**这些条件。比如 macOS 上的 libc++ 对未加锁的 `std::mutex` 调用 `unlock()` 会静默返回，程序继续运行——这正是 UB 最危险的样子。

### Error conditions：可以预期的失败

与前置条件相对，*Error conditions* 列出的是**有定义**的失败：以 `system_error` 报告，`code()` 等于列出的某个 `errc` 值（[[thread.req.exception]]）。例如 `thread::join()` 在 `get_id() == this_thread::get_id()` 时报 `resource_deadlock_would_occur`，这是标准承诺的行为，不是 UB。

## 本章与内存模型的分工

[[intro.multithread]] 给出的是"只要建立了这些关系，就有这些保证"；本章给出的是"调用这个函数，就建立这个关系"。它们之间的对应关系：

| 内存模型概念 | 本章中的来源 |
|---|---|
| synchronizes with（¶6） | [[atomics.order#2]]（release/acquire）、[[atomics.fences]]、各类的 *Synchronization* 元素 |
| 修改顺序（¶4） | 每个原子对象；互斥量的 lock/unlock 也"如同"处于一个全序（[[thread.mutex.requirements]]） |
| release sequence（¶5） | 原子 RMW 操作：`fetch_add`、`exchange`、成功的 `compare_exchange_*` |
| 阻塞与前进保证（[[intro.progress]]） | 非无锁的原子操作"可能阻塞"（[[atomics.lockfree#4]]）；`wait` 系列函数阻塞 |
| 单一全序 S | `memory_order::seq_cst`（[[atomics.order#4]]） |

!!! tip "推荐的阅读顺序"
    1. [[thread.threads]]：先会开线程、会 join；
    2. [[thread.mutex.requirements]] → [[thread.lock]] → [[thread.condition]]：基于锁的经典同步；
    3. [[atomics.order]] → [[atomics.types.generic]] → [[atomics.fences]]：无锁编程与内存序；
    4. [[atomics.wait]]、[[thread.sema]]、[[thread.coord]]：C++20 的"同步库"；
    5. [[thread.stoptoken]] 与 `jthread`：协作式取消；
    6. [[futures]]、[[saferecl]]：更高层的抽象。

## 实现视角

!!! impl "libc++ 在 macOS 上的情况（Clang 23）"
    - 线程、互斥量、条件变量都直接包装 pthreads：`std::mutex` 64 字节（即 `pthread_mutex_t`），`condition_variable` 48 字节，`std::thread` 只存一个 `pthread_t`（8 字节）。
    - C++20 同步库（`atomic::wait`、`counting_semaphore`、`latch`、`barrier`）建立在 libc++ 自己的"自旋 + 退避 + 平台等待"框架上，见 [[atomics.wait]]。
    - **未实现**：`atomic<shared_ptr<T>>`、整数/指针原子的 `fetch_max`/`fetch_min`、`store_add` 等原子 modify-write 操作、`constexpr` 原子操作、线程属性 `name_hint`/`stack_size_hint`、`inplace_stop_token` 系列、`<rcu>`、`<hazard_pointer>`。各页会具体说明。

## 小结

- 核心语言只定义关系，本章提供产生关系的手段；每个函数的 *Synchronization* 元素是唯一可靠的依据。
- 区分 synchronizes with、strongly happens before 与"不引入数据竞争"三种承诺强度。
- 前置条件违反是 UB，错误条件是有定义的异常；本章的前置条件多与"谁拥有锁"有关。
