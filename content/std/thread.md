---
title: 并发支持库
summary: 第 32 章导读：线程、原子操作、锁、条件变量、信号量、latch/barrier、future 等组件如何为内存模型提供同步手段，以及读这些函数说明时要看哪几个元素。
status: done
covers: thread.general
related: intro.multithread, intro.races, intro.progress, structure.specifications, thread.req, atomics, thread.mutex
tags: 标准库, 并发, 导读
updated: 2026-10-19
---

!!! tldr
    - 核心语言只定义线程间的先后关系（happens before 等）和"数据竞争是 UB"，真正建立这些关系的手段全在第 32 章。
    - 两个线程之间的写入是否可见，只能依据函数说明里的 *Synchronization* 元素判断；`sleep_for` 和 `yield` 明确不同步。
    - "并发调用不引入数据竞争"只说明这些调用彼此安全，不提供任何同步。
    - 违反 *Preconditions*（比如解锁不属于自己的互斥量）是 UB，实现通常不检查；*Error conditions* 则是有定义、以异常报告的失败。

## 核心语言缺的那一半

```cpp run title="sleep-is-not-sync.cpp" ub
#include <chrono>
#include <thread>
int data = 0;
int main() {
  std::thread t([] { data = 1; });
  std::this_thread::sleep_for(std::chrono::milliseconds(100));
  int r = data;   // UB: 与 t 中的写构成数据竞争
  (void)r;
  t.join();
}
```

主线程睡了 100 毫秒，`t` 几乎肯定早已写完，但这段程序仍然有数据竞争。按 [[intro.races#17]]，两个线程对同一对象的冲突访问（至少一个是写），只要彼此之间没有 **happens before** 关系，就是数据竞争，结果是 UB。时间上的先后不算数。用 `-fsanitize=thread` 运行，ThreadSanitizer 会报告 `data race`。

happens before 这类关系定义在 [[intro.multithread]]，但核心语言本身没有任何建立它们的语法：没有创建线程的关键字，也没有内建的锁。能产生**同步**（synchronizes with，[[intro.races#6]]）的操作全部是第 32 章的库函数。把 `int r = data;` 挪到 `t.join()` 之后就对了，因为 [[thread.thread.member#4]] 规定线程执行完毕与 `join()` 的返回同步。

常见的同步来源：

- `std::thread` 的构造完成与线程函数开始执行同步，线程完成与 `join()` 返回同步（[[thread.threads]]）；
- 原子操作的 `memory_order` 决定一次 load/store 建立哪些关系（[[atomics.order]]）；
- 互斥量的 `unlock()` 与之后对同一互斥量的 `lock()` 同步（[[thread.mutex.requirements]]）；
- 条件变量、信号量、latch、barrier、future 各自在函数说明里写明它们建立的关系。

## 本章的组成（¶1）

¶1 只有一句话和一张表（表 154），列出各子条款和头文件：

| 子条款 | 内容 | 头文件 |
|---|---|---|
| [[thread.req]] | 通用要求：异常、native handle、超时、*Cpp17Lockable* 系列要求 | — |
| [[thread.stoptoken]] | `stop_token`、`stop_source`、`stop_callback`，C++26 的 `inplace_stop_*`、`never_stop_token` | `<stop_token>` |
| [[thread.threads]] | `thread`、`jthread`、`this_thread` | `<thread>` |
| [[atomics]] | `memory_order`、`atomic<T>`、`atomic_ref<T>`、`atomic_flag`、栅栏、等待与通知 | `<atomic>`、`<stdatomic.h>` |
| [[thread.mutex]] | 互斥量、`lock_guard`/`scoped_lock`/`unique_lock`/`shared_lock`、`std::lock`、`call_once` | `<mutex>`、`<shared_mutex>` |
| [[thread.condition]] | `condition_variable`、`condition_variable_any` | `<condition_variable>` |
| [[thread.sema]] | `counting_semaphore`、`binary_semaphore` | `<semaphore>` |
| [[thread.coord]] | `latch`、`barrier` | `<latch>`、`<barrier>` |
| [[futures]] | `promise`、`future`、`shared_future`、`packaged_task`、`async` | `<future>` |
| [[saferecl]] {{c++26}} | RCU、hazard pointer | `<rcu>`、`<hazard_pointer>` |

## 读函数说明时看哪几个元素

库条款里每个函数的说明分成若干元素（*Effects*、*Returns* 等），各自的法律效力由 [[structure.specifications]] ¶3 规定。读本章时最要紧的是下面三个。

### Synchronization：线程间可见性的唯一依据

[[structure.specifications]] ¶3.7 规定，*Synchronization* 元素给出适用于该函数的同步操作。本章的措辞有四种强度：

| 措辞 | 例子 | 能推出什么 |
|---|---|---|
| A synchronizes with B | 线程完成 → `join()` 返回；`unlock()` → 之后的 `lock()` | A happens before B（[[intro.races#7]]），A 之前的写对 B 之后的读可见 |
| A strongly happens before B | `latch::count_down` → 被它解除阻塞的调用返回（[[thread.latch.class]] ¶9）；`semaphore::release` → 观察到结果的 `try_acquire`（[[thread.sema.cnt]] ¶10） | 比 happens before 更强（[[intro.races#8]]），还约束 seq_cst 操作的全序（[[atomics.order#4]]） |
| do not introduce data races | 并发调用同一个 `latch` 或 `counting_semaphore` 的成员函数 | 只保证这些调用彼此不构成数据竞争，不附带同步 |
| *Synchronization*: None | `this_thread::yield`、`sleep_for`、`sleep_until`（[[thread.thread.this]]） | 明确不同步，上面的例子就是这种情况 |

第三行容易误读。"do not introduce data races" 说的是对象自身的内部状态可以并发访问，例如两个线程可以同时对一个 `latch` 调用成员函数。它不保证一个线程在调用之前写的普通变量，对另一个线程可见。要得到可见性，还得找一条 synchronizes with 或 happens before。

### Preconditions：违反即 UB

[[structure.specifications]] ¶3.4 规定，违反 *Preconditions* 是未定义行为。本章的前置条件大多与所有权有关：

- 调用 `unlock()` 的线程必须持有这个互斥量（[[thread.mutex.requirements.mutex.general]] ¶21）；
- 已经持有 `std::mutex` 的线程不能再对它 `lock()`；
- 销毁 `condition_variable` 时不能有线程还阻塞在它上面（[[thread.condition]]）；
- `counting_semaphore::release` 不能让计数超过 `max()`（[[thread.sema.cnt]]）。

实现通常不检查这些条件。macOS 上的 libc++ 对一个没人持有的 `std::mutex` 调用 `unlock()`，不报错也不终止，程序继续运行。

### Error conditions：有定义的失败

*Error conditions* 列出的是有定义的失败：函数抛出 `system_error`，其 `code()` 等于列出的某个 `errc` 值（[[thread.req.exception]]）。例如一个线程对代表自己的 `std::thread` 调用 `join()`，按 [[thread.thread.member]] 会抛出 `resource_deadlock_would_occur`，这是标准承诺的行为，不是 UB。

## 内存模型概念与库中的来源

| 内存模型概念（[[intro.races]]） | 本章中的来源 |
|---|---|
| synchronizes with（¶6） | release/acquire 原子操作（[[atomics.order#2]]）、栅栏（[[atomics.fences]]）、各函数的 *Synchronization* 元素 |
| 修改顺序（¶4） | 每个原子对象各有一个；互斥量的 lock/unlock 为判断数据竞争也视作原子操作（[[thread.mutex.requirements.mutex.general]] ¶4） |
| release sequence（¶5） | 原子读-改-写操作：`fetch_add`、`exchange`、成功的 `compare_exchange_*` |
| 单一全序 S | `memory_order::seq_cst`（[[atomics.order#4]]） |
| 阻塞与前进保证（[[intro.progress]]） | 非无锁的原子操作视为可能阻塞（[[atomics.lockfree#4]]）；各类 `wait` 函数 |

建议的阅读顺序：先 [[thread.threads]]（开线程、join）；再 [[thread.mutex.requirements]]、[[thread.lock]]、[[thread.condition]]（基于锁的同步）；然后 [[atomics.order]]、[[atomics.types.generic]]、[[atomics.fences]]（原子操作与内存序）；接着 [[atomics.wait]]、[[thread.sema]]、[[thread.coord]]；最后 [[thread.stoptoken]] 与 `jthread`、[[futures]]、[[saferecl]]。

!!! impl "libc++（macOS，Clang 23）"
    - 线程、互斥量、条件变量直接包装 pthreads：`sizeof(std::mutex)` 为 64，`sizeof(std::condition_variable)` 为 48，`std::thread` 只存一个 `pthread_t`，大小为 8。
    - `atomic::wait`、`counting_semaphore`、`latch`、`barrier` 建立在 libc++ 自己的"自旋、退避、平台等待"框架上，见 [[atomics.wait]]。
    - 尚未提供：`atomic<shared_ptr<T>>`、原子的 `fetch_max`/`fetch_min`、`constexpr` 原子操作、`inplace_stop_token` 系列、`<rcu>`、`<hazard_pointer>`。
