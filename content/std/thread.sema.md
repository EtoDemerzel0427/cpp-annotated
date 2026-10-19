---
title: 信号量
summary: counting_semaphore 与 binary_semaphore：没有所有者的计数器，release 不得使计数超过 max()，release 与观察到它的获取之间的同步，以及可以虚假失败的 try_acquire。
status: done
covers: *
papers: P1135R6
related: thread.mutex.requirements, thread.condition, atomics.wait, thread.coord, thread.req
tags: 标准库, 并发, 信号量
updated: 2026-10-19
---

!!! tldr
    - 信号量是一个非负计数器：`acquire` 减一，计数为零时阻塞；`release` 加一。它没有所有者，任何线程都可以 `release`。
    - `binary_semaphore` 就是 `counting_semaphore<1>`。对计数已经是 1 的二值信号量再 `release()` 是 UB，不会停在 1。
    - `release` [[g:strongly-happens-before|strongly happens before]] 观察到其结果的 `try_acquire`，所以 `release` 之前写入的数据对获取者可见。
    - `try_acquire` 允许在计数为正时虚假失败；`acquire` 是 `try_acquire` 加阻塞的循环。
    - C++20 引入信号量，常见用法是一个线程向另一个线程发信号，以及限制同时访问某资源的线程数。

## 一个线程给另一个线程发信号

```cpp run title="semaphore-signal.cpp" ok
#include <cassert>
#include <semaphore>
#include <thread>

std::binary_semaphore ready{0};
int data = 0;

int main() {
  std::jthread t([] {
    ready.acquire();       // 阻塞，直到计数变为正
    assert(data == 1);     // release 之前的写入在这里可见
  });
  data = 1;
  ready.release();         // 由另一个线程释放
}
```

用 `std::mutex` 做同样的事是 UB：在主线程 `lock`、在 `t` 里 `unlock`，违反了只有拥有互斥量的线程才能解锁的前置条件（[[thread.mutex.requirements]]）。信号量没有所有者，所以没有这个限制。

[thread.sema.general] ¶1 信号量是轻量的同步原语，用来限制对共享资源的并发访问。它常被用来实现其他同步原语，在两者都适用时可能比条件变量更高效：计数本身就是条件，不需要另配互斥量，无争用时 `acquire` 和 `release` 都只是一次原子操作。

¶2 **计数信号量**（counting semaphore）表示一个非负的资源计数。**二值信号量**（binary semaphore）只有两个状态。标准建议二值信号量比计数为 1 的计数信号量的默认实现更高效，但这只是建议。

## 类型与计数上限 [semaphore.syn] [thread.sema.cnt]

```cpp
template<ptrdiff_t least_max_value = implementation-defined>
  class counting_semaphore;
using binary_semaphore = counting_semaphore<1>;
```

[thread.sema.cnt] ¶1 信号量维护一个内部计数器，创建时初始化。线程获取信号量时计数器减一，释放时加一。计数器为零时试图获取的线程会阻塞，直到另一个线程释放。

¶2 `least_max_value` 必须非负，否则程序非良构。默认值由实现定义 {{impl}}。

¶4 `max()` 返回计数器的最大值，它不小于 `least_max_value`。模板实参只是下界，实现可以支持更大的值。¶5 构造函数的前置条件是 `0 <= desired <= max()`。

¶3 除析构函数外，并发调用成员函数不会引入数据竞争。具体的同步关系另在 `release` 中规定。

## release [thread.sema.cnt]

```cpp
void release(ptrdiff_t update = 1);
```

¶9 原子地执行 `counter += update`，然后解除那些等待计数器变为正的线程的阻塞。

¶8 前置条件：`update >= 0`，并且 `update <= max() - counter`。也就是说，释放之后计数器不能超过 `max()`。对 `binary_semaphore`，计数器已经是 1 时再 `release()` 就违反了这一条 {{ub}}。重复发信号在二值信号量上不是无害的空操作。

```cpp title="binary-overflow.cpp" ub
#include <cstdio>
#include <semaphore>
int main() {
  std::binary_semaphore s{1};
  s.release();                          // UB：计数器将变为 2，超过 max() == 1
  std::printf("max=%td try1=%d try2=%d\n", s.max(), s.try_acquire(), s.try_acquire());
}
```

!!! impl "libc++ 不检查这条前置条件"
    在 libc++ 下这个程序打印 `max=1 try1=1 try2=1`：二值信号量被获取了两次，计数器实际变成了 2。即使用 `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_DEBUG` 编译也一样，因为 libc++ 的断言检查的是不超过 `ptrdiff_t` 的最大值，而不是 `max()`。`binary_semaphore` 和默认的 `counting_semaphore` 在 libc++ 里用的是同一份实现。

¶10 `release` strongly happens before 观察到其结果的 `try_acquire` 调用。strongly happens before 是比普通 happens before 更强的关系（[[intro.races#8]]），它还约束 seq_cst 操作的全序。对只用信号量传递数据的程序，效果就是：`release` 之前的写入，对观察到这次 `release` 的获取者可见。

¶11–¶12 需要时抛 `system_error`，错误条件与互斥量相同。

## acquire 与 try_acquire

```cpp
bool try_acquire() noexcept;
void acquire();
```

¶13 `try_acquire` 尝试在计数器为正时不阻塞地将它原子地减一。没有减成就什么也不做，立即返回。即使计数器为正，实现也可以减不成功。注 1 说明这种虚假失败一般很少见，它允许用一次简单的比较交换来实现。标准建议实现保证在没有竞争时 `try_acquire` 不会一直返回 `false`。¶14 减成功时返回 `true`。

¶15 `acquire` 反复执行两步：求值 `try_acquire()`，为真就返回；否则阻塞，直到计数器为正。`acquire` 是用 `try_acquire` 定义的，所以 ¶10 的同步规则也覆盖了它：`acquire` 返回，说明它内部某次 `try_acquire` 观察到了某次 `release` 的结果。

¶18 `try_acquire_for(rel_time)` 和 `try_acquire_until(abs_time)` 也是循环：`try_acquire()` 成功就返回 `true`；否则阻塞到计数器为正或超时，因超时醒来就返回 `false`。`try_acquire_for` 的超时指从函数开始起至少经过了 `rel_time`。

## 限制并发数

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

!!! impl "libc++ 的 counting_semaphore"
    libc++ 的信号量内部只有一个 `atomic<ptrdiff_t>`，`max()` 直接返回模板实参，默认值是 `PTRDIFF_MAX`。

    - `release(n)` 是 `fetch_add(n, release)`，只有旧值为 0、可能有线程在等时才 `notify_all()`。
    - `try_acquire()` 先 relaxed 读取当前值，为 0 就失败；否则用 `compare_exchange_weak(old, old - 1, acquire, relaxed)` 循环，CAS 因竞争失败时用新值重试。
    - `acquire()` 用 [[atomics.wait]] 的等待机制，等到 CAS 成功为止。

    `release` 的 release 写与成功 CAS 的 acquire 读配对，构成同步（[[atomics.order#2]]），满足第 10 段的要求。

## 常见误解

!!! pitfall "二值信号量可以当作可重复设置的标志"
    对已经是 1 的 `binary_semaphore` 再 `release()` 是 UB（¶8），计数不会饱和在 1。需要幂等地设置标志并唤醒等待者时，用 `atomic<bool>` 配合 `wait`/`notify`（[[atomics.wait]]），或者用条件变量。

!!! pitfall "信号量可以直接代替互斥量"
    用初值为 1 的信号量可以实现互斥，但因为它没有所有者，实现无法做优先级继承，也无法检测忘记释放或释放了别人持有的资源。用它当互斥量用时，要接受这些代价。

## 小结

- 信号量没有所有者，任何线程都可以 `release`。
- `max()` 不小于 `least_max_value`；`release` 使计数器超过 `max()` 是 UB，二值信号量尤其要注意。
- `release` strongly happens before 观察到其结果的 `try_acquire`，因而也覆盖 `acquire`。
- `try_acquire` 可以虚假失败；`acquire` 是它加阻塞的循环。
