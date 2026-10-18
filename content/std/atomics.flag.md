---
title: atomic_flag
summary: 标准唯一保证无锁的原子类型——两个状态、test_and_set/clear/test 的内存序前置条件、C++20 的默认构造与 ATOMIC_FLAG_INIT、wait/notify，以及用它写一个不空转的自旋锁
status: done
covers: atomics.flag
papers: P1135R6
related: atomics, atomics.lockfree, atomics.wait, atomics.order, intro.progress, thread.req
tags: 标准库, 原子操作, 自旋锁
updated: 2026-10-18
---

`atomic_flag` 是 C++11 原子库的"地基"：它是标准**唯一**保证无锁的原子类型，所以任何平台上的实现都可以用它来构建其他东西——包括用锁实现的、非无锁的 `atomic<T>`。它的接口很小：一个布尔状态，一次"测试并置位"，一次"清除"。C++20 又给它加上了 `test`、`wait`、`notify_one`、`notify_all`。

## 类定义

```cpp
struct atomic_flag {
  constexpr atomic_flag() noexcept;
  atomic_flag(const atomic_flag&) = delete;
  atomic_flag& operator=(const atomic_flag&) = delete;
  bool test(memory_order = memory_order::seq_cst) const noexcept;
  bool test_and_set(memory_order = memory_order::seq_cst) noexcept;
  void clear(memory_order = memory_order::seq_cst) noexcept;
  void wait(bool, memory_order = memory_order::seq_cst) const noexcept;
  void notify_one() noexcept;
  void notify_all() noexcept;
  // 以上每个都另有 volatile 重载；非 volatile 版本是 constexpr
};
```

`<atomic>` 里还有对应的非成员函数 `atomic_flag_test`、`atomic_flag_test_and_set(_explicit)`、`atomic_flag_clear(_explicit)`、`atomic_flag_wait(_explicit)`、`atomic_flag_notify_one/all`，供 C 兼容使用。

## 性质（¶1–¶4）

- ¶1 `atomic_flag` 提供经典的 test-and-set 功能，有两个状态：**置位**（set）与**清除**（clear）。
- ¶2 `atomic_flag` 上的操作**必须是无锁的**；还应当是 address-free 的（[[atomics.lockfree]]）。这一句加上 [[intro.progress]] ¶2，使得 `atomic_flag` 的操作是"被定义为无锁"的执行，享有无锁执行的前进保证。
- ¶3 标准布局结构体，平凡析构。
- ¶4 默认构造函数把 `*this` 初始化为**清除**状态。

¶4 是 C++20 的变化。C++11/17 中默认构造的 `atomic_flag` 状态未指定，必须写 `atomic_flag f = ATOMIC_FLAG_INIT;`。

## 操作（¶5–¶20）

| 操作 | 段落 | 内存序前置条件 | 效果 |
|---|---|---|---|
| `test(order)` {{c++20}} | ¶5–¶8 | `relaxed`、`acquire`、`seq_cst` | 原子地返回当前值（不修改） |
| `test_and_set(order)` | ¶9–¶10 | 任意 | 原子地置为 `true`，返回之前的值；**原子读-改-写操作** |
| `clear(order)` | ¶11–¶12 | `relaxed`、`release`、`seq_cst` | 原子地置为 `false` |
| `wait(old, order)` {{c++20}} | ¶13–¶16 | `relaxed`、`acquire`、`seq_cst` | 反复：`test(order) != old` 则返回，否则阻塞直到被通知或虚假唤醒 |
| `notify_one()`、`notify_all()` {{c++20}} | ¶17–¶20 | — | 解除有资格的等待操作的阻塞（[[atomics.wait]]） |

¶5、¶13：对不带 `_explicit` 的非成员版本，`order` 取 `seq_cst`。

`test_and_set` 是 RMW，所以它总是读取修改顺序中最新的值（[[atomics.order#11]]），两个线程同时对清除状态的 flag 调用它，恰好一个得到 `false`。这就是"获取锁"的原语。

`test()` 是 C++20 加的。之前想"只看一眼"状态而不修改，做不到——只能 `test_and_set` 再视情况 `clear`，这会对缓存行产生不必要的写。

## ATOMIC_FLAG_INIT（¶21）

¶21 宏 `ATOMIC_FLAG_INIT` 的定义方式使它可以用来把 `atomic_flag` 初始化为清除状态，可用于形式 `atomic_flag guard = ATOMIC_FLAG_INIT;`。是否能用在其他初始化语境中**未指定**。对完整的静态存储期对象，这样的初始化必须是**静态初始化**。

C++20 起默认构造已经是清除状态且 `constexpr`，所以 `atomic_flag guard;` 就够了，这个宏只为兼容 C 与旧代码保留。

## 用 atomic_flag 写自旋锁

```cpp run title="flag-spinlock.cpp" ok
#include <atomic>
#include <cassert>
#include <mutex>
#include <thread>
#include <vector>

class spinlock {                            // 满足 Cpp17Lockable（[thread.req.lockable.req]）
  std::atomic_flag f;                       // C++20：默认构造为 clear
public:
  void lock() noexcept {
    while (f.test_and_set(std::memory_order::acquire))  // 得到 false 说明是我置的位：获得锁
      f.wait(true, std::memory_order::relaxed);         // 被占用：阻塞到它不再是 true
  }
  bool try_lock() noexcept { return !f.test_and_set(std::memory_order::acquire); }
  void unlock() noexcept {
    f.clear(std::memory_order::release);
    f.notify_one();                          // 先修改、后通知
  }
};

int main() {
  spinlock sl;
  long counter = 0;
  {
    std::vector<std::jthread> ts;
    for (int i = 0; i < 4; ++i)
      ts.emplace_back([&] { for (int k = 0; k < 100000; ++k) { std::lock_guard g(sl); ++counter; } });
  }
  assert(counter == 400000);
}
```

逐行看内存序：

- `test_and_set(acquire)`：读到 `false`（即获得锁）时，它读到的是上一次 `clear(release)` 写入的值，二者同步（[[atomics.order#2]]），上一个持有者在临界区里的写入因此可见。
- `wait(true, relaxed)`：只用来"等它变"，不需要同步——醒来后还会再做一次 acquire 的 `test_and_set`。
- `clear(release)` 之后 `notify_one()`：满足 [[atomics.wait]] ¶4 的"修改 happens before 通知"，不会丢失唤醒。

这把锁在没有争用时只有一次原子 RMW；争用时等待者会经由 `wait` 进入阻塞（libc++ 先自旋约 4 微秒再阻塞），不会一直空转。但它**不公平**：`notify_one` 唤醒的线程可能又被新来的线程抢先。需要公平性时用 `std::mutex`。

## 实现视角

!!! impl "libc++ 中的 atomic_flag"
    libc++ 的 `atomic_flag` 内部就是一个 `__cxx_atomic_impl<bool>`，大小 1 字节；`test_and_set` 用 `exchange(true)` 实现。libc++ 还提供一个非标准的扩展构造函数 `atomic_flag(bool)`。`wait`/`notify` 因而走 [[atomics.wait]] 中描述的全局等待表，而不是直接在 flag 的地址上等待。

## 陷阱

!!! pitfall "纯自旋锁与优先级反转"
    用 `while (f.test_and_set(acquire)) {}` 纯空转的锁，在持有者被抢占时会让等待者烧满 CPU 时间片；若等待者优先级更高，持有者可能一直得不到调度（优先级反转）。在用户态代码中，至少像上例那样配合 `wait`，或直接用 `std::mutex`。

!!! pitfall "不要用 clear(acquire)"
    `clear` 是 store，前置条件只允许 `relaxed`、`release`、`seq_cst`；传 `acquire` 或 `acq_rel` 是 UB（同样，`test` 与 `wait` 不能用 `release`、`acq_rel`）。

## 小结

- `atomic_flag` 是唯一保证无锁的原子类型（¶2），独立实现中也是如此。
- C++20 起默认构造为清除状态，`ATOMIC_FLAG_INIT` 不再必需；新增 `test`、`wait`、`notify_*`。
- `test_and_set` 是 RMW：获得锁用 acquire，`clear` 释放锁用 release。
