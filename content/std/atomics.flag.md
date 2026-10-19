---
title: atomic_flag
summary: 在所有实现中都保证无锁的原子布尔标志：test_and_set、clear、test 的内存序要求，C++20 的默认构造与 ATOMIC_FLAG_INIT，以及用它和 wait/notify 写一个不空转的自旋锁。
status: done
covers: atomics.flag
papers: P1135R6
related: atomics, atomics.lockfree, atomics.wait, atomics.order, intro.progress, thread.req
tags: 标准库, 原子操作, 自旋锁
updated: 2026-10-19
---

!!! tldr
    - `atomic_flag` 只有两个状态，置位和清除。它的操作必须是无锁的，包括在独立实现中，这是其他原子类型做不到的保证。
    - `test_and_set` 是原子读-改-写操作：两个线程同时对清除状态的标志调用它，恰好一个得到 `false`，这就是获取锁的原语。
    - `clear` 是 store，内存序不能用 `acquire` 或 `acq_rel`；`test` 和 `wait` 是 load，不能用 `release` 或 `acq_rel`。
    - C++20 起默认构造就是清除状态，`ATOMIC_FLAG_INIT` 只为兼容保留；同时新增了 `test`、`wait`、`notify_one`、`notify_all`。

## 用 atomic_flag 写一把锁

```cpp run title="flag-spinlock.cpp" ok
#include <atomic>
#include <cassert>
#include <mutex>
#include <thread>
#include <vector>

class spinlock {
  std::atomic_flag f;   // C++20：默认构造为清除状态
public:
  void lock() noexcept {
    while (f.test_and_set(std::memory_order::acquire))
      f.wait(true, std::memory_order::relaxed);
  }
  bool try_lock() noexcept {
    return !f.test_and_set(std::memory_order::acquire);
  }
  void unlock() noexcept {
    f.clear(std::memory_order::release);
    f.notify_one();     // 先修改、后通知
  }
};

int main() {
  spinlock sl;
  long counter = 0;
  {
    std::vector<std::jthread> ts;
    for (int i = 0; i < 4; ++i)
      ts.emplace_back([&] {
        for (int k = 0; k < 100000; ++k) {
          std::lock_guard g(sl);
          ++counter;
        }
      });
  }
  assert(counter == 400000);
}
```

`spinlock` 满足 *Cpp17Lockable*（[[thread.req]]），所以可以配合 `lock_guard` 使用。用 ThreadSanitizer 运行没有报告。逐个看内存序：

- `test_and_set(acquire)` 得到 `false` 时就获得了锁。它读到的是上一次 `clear(release)` 写入的值，二者同步（[[atomics.order#2]]），上一个持有者在临界区里的写入因此可见。
- `wait(true, relaxed)` 只用来等标志变化，不需要同步，醒来后还会再执行一次 acquire 的 `test_and_set`。
- `clear(release)` 之后 `notify_one()`，修改 happens before 通知，满足 [[atomics.wait]] ¶4，不会丢失唤醒。

没有争用时，加锁只要一次原子读-改-写。有争用时，等待者经由 `wait` 阻塞（libc++ 先自旋约 4 微秒），不会一直空转。但这把锁不公平：被 `notify_one` 唤醒的线程可能又被新来的线程抢先。需要公平性时用 `std::mutex`。

## 性质（¶1–¶4）

¶1 `atomic_flag` 提供经典的 test-and-set 功能，有两个状态：**置位**（set）和**清除**（clear）。

¶2 `atomic_flag` 上的操作必须是无锁的，还应当是 address-free 的（[[atomics.lockfree]]）。[[intro.progress#2]] 把定义为无锁的执行（即 `atomic_flag` 的操作）列为无锁执行，享有相应的前进保证。

其他原子类型是否无锁由实现决定。宿主实现中 `atomic_signed_lock_free` 和 `atomic_unsigned_lock_free` 也保证无锁，但它们在独立实现中是可选的（[[atomics.alias]]）。所以在任何平台上，实现都可以用 `atomic_flag` 构建其他东西，包括用锁实现的非无锁 `atomic<T>`。

¶3 `atomic_flag` 是标准布局结构体，析构函数平凡。

¶4 默认构造函数把它初始化为清除状态。这是 C++20 的变化：C++11/17 中默认构造的 `atomic_flag` 状态未指定，必须写 `atomic_flag f = ATOMIC_FLAG_INIT;`。

## 操作（¶5–¶20）

每个操作都有 `volatile` 重载和非 `volatile` 的 `constexpr` 重载，还有供 C 兼容使用的非成员版本 `atomic_flag_test`、`atomic_flag_test_and_set(_explicit)`、`atomic_flag_clear(_explicit)`、`atomic_flag_wait(_explicit)`、`atomic_flag_notify_one/all`。不带 `_explicit` 的非成员版本使用 `seq_cst`（¶5、¶13）。

| 操作 | 段落 | 内存序前置条件 | 效果 |
|---|---|---|---|
| `test(order)` {{c++20}} | ¶5–¶8 | `relaxed`、`acquire`、`seq_cst` | 原子地返回当前值，不修改 |
| `test_and_set(order)` | ¶9–¶10 | 任意 | 原子地置为 `true`，返回之前的值；原子读-改-写操作 |
| `clear(order)` | ¶11–¶12 | `relaxed`、`release`、`seq_cst` | 原子地置为 `false` |
| `wait(old, order)` {{c++20}} | ¶13–¶16 | `relaxed`、`acquire`、`seq_cst` | 反复检查 `test(order) != old`，为真就返回，否则阻塞到被通知或虚假唤醒 |
| `notify_one()`、`notify_all()` {{c++20}} | ¶17–¶20 | 无 | 解除有资格的等待操作（[[atomics.wait]]） |

`test_and_set` 是读-改-写，总是读取修改顺序中紧邻其前的值（[[atomics.order#11]]），所以两个线程同时对清除状态的标志调用它，恰好一个得到 `false`。

`test()` 是 C++20 才加的。在此之前想只看一眼状态而不修改是做不到的，只能 `test_and_set` 再视情况 `clear`，对缓存行产生不必要的写。

违反内存序前置条件是 UB。最容易写错的是 `clear(acquire)`：`clear` 是 store，只接受 `relaxed`、`release`、`seq_cst`。

## ATOMIC_FLAG_INIT（¶21）

¶21 宏 `ATOMIC_FLAG_INIT` 可以把 `atomic_flag` 初始化为清除状态，用法是 `atomic_flag guard = ATOMIC_FLAG_INIT;`。能否用在其他初始化语境中未指定。用于静态存储期的完整对象时，这种初始化必须是静态初始化。

C++20 起默认构造已经是清除状态并且是 `constexpr` 的，写 `atomic_flag guard;` 就够了，这个宏只为兼容 C 和旧代码保留。

## 实现视角

!!! impl "libc++ 中的 atomic_flag"
    libc++ 的 `atomic_flag` 内部是一个 `__cxx_atomic_impl<bool>`，大小 1 字节，`test_and_set` 用 `exchange(true)` 实现。它还提供一个非标准的构造函数 `atomic_flag(bool)`。由于大小是 1 字节，`wait`/`notify` 走 [[atomics.wait]] 中描述的全局等待表，而不是直接在标志的地址上等待。

## 常见误解

!!! pitfall "纯自旋锁没什么问题"
    `while (f.test_and_set(acquire)) {}` 纯空转的锁，在持有者被抢占时会让等待者白白烧掉时间片；如果等待者优先级更高，持有者可能一直得不到调度（优先级反转）。在用户态代码中，至少像上面的例子那样配合 `wait`，或者直接用 `std::mutex`。
