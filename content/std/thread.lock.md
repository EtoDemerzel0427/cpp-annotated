---
title: 锁与通用加锁算法
summary: lock_guard、scoped_lock、unique_lock、shared_lock 的精确契约——被引用的互斥量必须活得比锁久、adopt_lock 的前置条件、unique_lock 哪些误用是有定义的 system_error 而不是 UB、release() 不解锁；std::lock 的免死锁保证与 libc++ 的"尝试并退让"算法；声明式陷阱 unique_lock<mutex>(m)
status: done
covers: *, thread.lock.algorithm
related: thread.mutex, thread.mutex.requirements, thread.req, thread.condition, basic.life, dcl.ambig.res
tags: 标准库, 并发, 锁, RAII, 死锁
updated: 2026-10-18
---

互斥量的 `lock`/`unlock` 必须严格配对，并且 [[thread.mutex.requirements]] 规定"线程在拥有互斥量时终止"是 UB。手工配对在异常和提前返回面前很脆弱，所以标准库提供了 RAII 包装——**锁**（lock）。本页覆盖 [thread.lock] 的全部子条款，以及紧随其后的 [thread.lock.algorithm]。

## 总述（[thread.lock.general]）

¶1 **锁**是持有一个可锁对象的引用、并可能在自身析构时（比如离开块作用域时）解锁该对象的对象。执行代理可以用锁以异常安全的方式管理可锁对象的所有权。锁当前正在为某个执行代理管理一个可锁对象的所有权时，称锁**拥有**该可锁对象。**锁不管理它所引用的可锁对象的生命周期。** 注 1：锁意在减轻在正常与异常情况下解锁的负担。

¶2 一些锁的构造函数接受**标签类型**，描述构造时如何处置可锁对象：

| 标签 | 含义 |
|---|---|
| `defer_lock` | 不获取所有权 |
| `try_to_lock` | 不阻塞地尝试获取所有权 |
| `adopt_lock` | 假定调用线程**已经**获得了所有权，由锁来管理它 |

## lock_guard（[thread.lock.guard]）

最简单的锁：构造时加锁，析构时解锁，中间不能做任何事。类里只有一个仅说明用的引用成员 `mutex_type& pm`，不可复制、不可移动。

¶1 `lock_guard` 在一个作用域内控制可锁对象的所有权，并在其整个生命周期内保持所有权。**若 `pm` 引用的可锁对象没有在 `lock_guard` 的整个生命周期内存在，行为未定义** {{ub}}。`Mutex` 须满足 *Cpp17BasicLockable*。

- ¶2 `explicit lock_guard(mutex_type& m)`：初始化 `pm`，调用 `m.lock()`。
- ¶3–¶5 `lock_guard(mutex_type& m, adopt_lock_t)`：*Preconditions*：调用线程持有 `m` 上的非共享锁；只初始化 `pm`；不抛异常。
- ¶6 析构函数：等价于 `pm.unlock()`。

`lock_guard` 只要求 *Cpp17BasicLockable*（只用 `lock`/`unlock`），所以也能包装任何用户自定义的锁、`unique_lock`，甚至 RCU 的 `rcu_domain`（[[saferecl]]）。

## scoped_lock（[thread.lock.scoped]） {{c++17}}

`scoped_lock` 是可变参数版的 `lock_guard`：仅说明用成员 `tuple<MutexTypes&...> pm`。

¶1 同样的生命周期要求（被引用的可锁对象必须在整个生命周期内存在，否则 UB）。以及：

- ¶1.1 若 `sizeof...(MutexTypes)` 为 1，唯一的类型须满足 *Cpp17BasicLockable*，成员 `mutex_type` 就是该类型；
- ¶1.2 否则，所有类型须满足 *Cpp17Lockable*（需要 `try_lock`），且**没有** `mutex_type` 成员。

¶2 `explicit scoped_lock(MutexTypes&... m)`：用 `tie(m...)` 初始化 `pm`。然后：0 个互斥量时无效果；1 个时调用 `m.lock()`；**多个时调用 `std::lock(m...)`**——即使用下面的免死锁算法。

¶3–¶5 `explicit scoped_lock(adopt_lock_t, MutexTypes&... m)`：*Preconditions*：调用线程持有每个 `m` 上的非共享锁；只初始化 `pm`；不抛异常。注意标签放在**最前面**（可变参数包必须在最后），与 `lock_guard(m, adopt_lock)` 的顺序相反。

¶6 析构函数：对 `[0, sizeof...(MutexTypes))` 中的每个 `i`，调用 `get<i>(pm).unlock()`。

`scoped_lock<>`（零个互斥量）是合法的，什么也不做。这让泛型代码可以写 `std::scoped_lock lk(ms...);` 而不必特殊处理空包。

```cpp run title="scoped-lock-transfer.cpp" ok
#include <mutex>
#include <thread>

struct Account {
  std::mutex m;
  long balance = 100;
};

void transfer(Account& from, Account& to, long amt) {
  std::scoped_lock lk(from.m, to.m);   // 两把锁：用 std::lock 的免死锁算法
  from.balance -= amt;
  to.balance += amt;
}

int main() {
  Account a, b;
  std::jthread t1([&] { for (int i = 0; i < 100000; ++i) transfer(a, b, 1); });
  std::jthread t2([&] { for (int i = 0; i < 100000; ++i) transfer(b, a, 1); });   // 相反的顺序，不会死锁
}
```

如果把 `scoped_lock lk(from.m, to.m)` 换成两个 `lock_guard` 按参数顺序加锁，t1 先锁 a 再锁 b、t2 先锁 b 再锁 a，几乎必然死锁。

## unique_lock（[thread.lock.unique]）

`unique_lock` 是"可以不持有锁的锁"：仅说明用成员 `mutex_type* pm` 与 `bool owns`。它可移动、可推迟加锁、可中途解锁再加锁、可转移所有权，是 `condition_variable` 必须使用的锁类型。

### 总述（[thread.lock.unique.general]）

¶1 `unique_lock` 在一个作用域内控制可锁对象的所有权。所有权可以在构造时或构造后获得，获得后可以转移给另一个 `unique_lock`。不可复制但可移动。**若 `pm` 非空，而它指向的可锁对象没有在 `unique_lock` 剩余的整个生命周期内存在，行为未定义**。`Mutex` 须满足 *Cpp17BasicLockable*。

¶2 注 1：`unique_lock<Mutex>` 满足 *Cpp17BasicLockable*；`Mutex` 满足 *Cpp17Lockable* 时它也满足 *Cpp17Lockable*；满足 *Cpp17TimedLockable* 时它也满足。所以 `unique_lock` 可以再传给 `std::lock` 或 `condition_variable_any`。

### 构造、析构与赋值（[thread.lock.unique.cons]）

| 构造函数 | 段落 | 前置条件 | 效果 | 之后 `owns` |
|---|---|---|---|---|
| `unique_lock()` | ¶1 | — | — | `false`，`pm == nullptr` |
| `unique_lock(m)` | ¶2–¶3 | — | `m.lock()` | `true` |
| `unique_lock(m, defer_lock)` | ¶4 | — | 不加锁；`noexcept` | `false` |
| `unique_lock(m, try_to_lock)` | ¶5–¶7 | `Mutex` 满足 *Cpp17Lockable* | `m.try_lock()` | 其返回值 |
| `unique_lock(m, adopt_lock)` | ¶8–¶10 | 调用线程持有 `m` 上的非共享锁 | 不加锁；不抛 | `true` |
| `unique_lock(m, abs_time)` | ¶11–¶13 | `Mutex` 满足 *Cpp17TimedLockable* | `m.try_lock_until(abs_time)` | 其返回值 |
| `unique_lock(m, rel_time)` | ¶14–¶16 | 同上 | `m.try_lock_for(rel_time)` | 其返回值 |

- ¶17 移动构造：接管 `u` 的 `pm` 与 `owns`，`u` 变为 `pm == 0`、`owns == false`。
- ¶18–¶19 移动赋值：等价于 `unique_lock(std::move(u)).swap(*this)`——原先持有的锁随临时对象析构而释放。
- ¶20 析构函数：若 `owns`，调用 `pm->unlock()`。

注意 "满足 *Cpp17Lockable*" 被写成**前置条件**（¶5），不是 *Constraints*。用一个只有 `lock`/`unlock` 的类型调用 `unique_lock(m, try_to_lock)` 时，在实践中会因为找不到 `try_lock` 而编译失败，但标准把它归为 UB 而非非良构。

### 加锁（[thread.lock.unique.locking]）

`lock()`（¶1–¶4）：如同 `pm->lock()`；之后 `owns == true`。错误条件：

- ¶4.1 `operation_not_permitted`：`pm` 为空；
- ¶4.2 `resource_deadlock_would_occur`：进入时 `owns` 已为 `true`。

`try_lock()`（¶5–¶10）、`try_lock_until()`（¶11–¶16）、`try_lock_for()`（¶17–¶22）：同理，也有同样两个错误条件。

`unlock()`（¶23–¶26）：如同 `pm->unlock()`；之后 `owns == false`；错误条件 ¶26.1 `operation_not_permitted`：进入时 `owns` 为 `false`。

这一点很重要：**对 `unique_lock` 的误用多数是有定义的**。对一个没有持锁的 `unique_lock` 调用 `unlock()` 会抛 `system_error`；而对**互斥量本身**做同样的事是 UB。`unique_lock` 用 `owns` 记住了"我是否持有锁"，因此能检测这些错误。

```cpp run title="unique-lock-errors.cpp" ok
#include <cstdio>
#include <mutex>
#include <system_error>

int main() {
  std::mutex m;
  std::unique_lock lk(m, std::defer_lock);
  try {
    lk.unlock();                                // 没有持锁：有定义的错误
  } catch (const std::system_error& e) {
    std::printf("unlock: %d\n", e.code() == std::errc::operation_not_permitted);   // 1
  }
  lk.lock();
  try {
    lk.lock();                                  // 已经持锁：有定义的错误，不是重复加锁 m
  } catch (const std::system_error& e) {
    std::printf("lock: %d\n", e.code() == std::errc::resource_deadlock_would_occur); // 1
  }
}
```

### 修改器与观察器（[thread.lock.unique.mod]、[thread.lock.unique.obs]）

- `swap`（¶1）交换数据成员。
- `release()`（¶2–¶3）：之后 `pm == 0`、`owns == false`，返回原来的 `pm`。**它不解锁**：如果之前持有锁，锁现在归调用者手动管理。忘记这一点是常见的锁泄漏来源。
- 非成员 `swap`（¶4）。
- `owns_lock()`、`explicit operator bool()`（返回 `owns`）、`mutex()`（返回 `pm`）。

## shared_lock（[thread.lock.shared]） {{c++14}}

`shared_lock` 是 `unique_lock` 的共享版本：同样的成员 `pm`、`owns`，但加锁函数调用的是 `lock_shared`、`try_lock_shared`、`try_lock_shared_for`、`try_lock_shared_until`，析构调用 `unlock_shared`。

[thread.lock.shared.general] ¶1：同样的生命周期要求；`Mutex` 须满足 *Cpp17SharedLockable*。¶2 注 1：`shared_lock<Mutex>` 满足 *Cpp17Lockable*（它的 `lock()` 获取的是**共享**锁）；`Mutex` 满足 *Cpp17SharedTimedLockable* 时它满足 *Cpp17TimedLockable*。

这个"把共享锁伪装成普通锁"的设计让 `shared_lock` 可以传给 `condition_variable_any::wait`，在等待期间释放并重新获取**共享**锁。

[thread.lock.shared.cons]、[thread.lock.shared.locking]、[thread.lock.shared.mod]、[thread.lock.shared.obs] 与 `unique_lock` 一一对应：`adopt_lock` 的前置条件是"调用线程持有 `m` 上的**共享**锁"（¶7）；错误条件同样是 `operation_not_permitted`（`pm` 为空或未持锁时解锁）与 `resource_deadlock_would_occur`（已持锁时再加锁）。

## 通用加锁算法（[thread.lock.algorithm]）

### std::try_lock（¶1–¶3）

`template<class L1, class L2, class... L3> int try_lock(L1&, L2&, L3&...)`

- ¶1 *Preconditions*：每个模板形参类型满足 *Cpp17Lockable*。注 1：适当实例化的 `unique_lock` 满足这一要求。
- ¶2 *Effects*：**按顺序**对每个实参调用 `try_lock()`，直到全部处理完或某次 `try_lock()` 失败（返回 `false` 或抛出异常）。若某次失败，对**之前所有**实参调用 `unlock()`，不再继续 `try_lock()`。
- ¶3 *Returns*：全部成功时返回 `-1`，否则返回失败的那个实参的从零开始的下标。

### std::lock（¶4–¶5）

- ¶4 前置条件同上。
- ¶5 *Effects*：通过对每个实参调用 `lock()`、`try_lock()` 或 `unlock()` 的一个序列锁住所有实参。**这个调用序列不会导致死锁，但除此之外未指定** {{unspec}}。注 3：可以使用诸如"尝试并退让"（try-and-back-off）的死锁避免算法，但为了不过度约束实现，没有指定具体算法。若某次 `lock()` 或 `try_lock()` 抛出异常，对已经通过 `lock()` 或 `try_lock()` 锁住的每个实参调用 `unlock()`。

"不会导致死锁"是一个很强的承诺：**无论**其他线程以什么顺序对同一组互斥量调用 `std::lock`，都不会死锁。但它只对**都使用 `std::lock`（或 `scoped_lock`）**的线程成立——另一个线程用 `lock_guard` 按固定顺序逐个加锁，仍然可能与之死锁。

!!! impl "libc++ 的算法（`<mutex>`）"
    两个互斥量时：

    ```text
    循环：
      阻塞地锁 l0；try_lock l1；成功则返回，否则解锁 l0
      yield
      阻塞地锁 l1；try_lock l0；成功则返回，否则解锁 l1
      yield
    ```

    多于两个时（`__lock_first`）：阻塞地锁住第 i 个，再对其余的调用 `std::try_lock`；若第 j 个失败，就全部释放，下一轮改为**先阻塞地锁第 j 个**。也就是说，每一轮都从"上一轮让自己失败的那个互斥量"开始阻塞等待，而不是空转重试。这就是注 3 所说的"尝试并退让"。它不会死锁，但在高争用时可能活锁般地多次重试。

## 陷阱

!!! pitfall "`std::unique_lock<std::mutex>(m);` 是一个声明"
    按 [[dcl.ambig.res]]，这条语句被解析为**声明一个名为 `m` 的变量**（类型 `unique_lock<mutex>`，默认构造，不持有任何锁），而不是创建一个锁住 `m` 的临时对象。它会遮蔽外层的 `m`，然后什么也不锁。

    ```cpp title="vexing-lock.cpp" ok
    #include <mutex>
    std::mutex m;
    int shared;
    void f() {
      std::unique_lock<std::mutex>(m);   // 声明了一个名为 m 的局部变量！
      ++shared;                          // 没有被保护
    }
    void g() {
      std::scoped_lock{m};               // 临时对象：在分号处就解锁
      ++shared;                          // 也没有被保护
    }
    int main() { f(); g(); }
    ```

    两段代码都是良构的，行为也有定义（单线程下）——只是完全没有起到保护作用。Clang 23 对前者给出 `warning: parentheses were disambiguated as redundant parentheses around declaration of variable named 'm' [-Wvexing-parse]`；对后者，libc++ 把构造函数标为 `[[nodiscard]]`，Clang 给出 `warning: ignoring temporary created by a constructor declared with 'nodiscard' attribute [-Wunused-value]`。正确写法是**总是给锁起名字**：`std::scoped_lock lk(m);`。

!!! pitfall "锁比互斥量活得久"
    ```cpp
    std::unique_lock<std::mutex> make_lock() {
      std::mutex m;
      return std::unique_lock(m);   // 返回后 m 已销毁，而锁还持有它：UB
    }
    ```
    所有四种锁都把"可锁对象在锁的生命周期内存在"列为要求（违反即 UB）。

!!! pitfall "release() 之后忘记解锁"
    `lk.release()` 把"持有锁"的责任交还给你；若之前持有锁，你必须手动 `m.unlock()`，否则线程终止时仍拥有互斥量（UB）。

## 思考题

!!! question "1. `std::lock(m, m)`——同一个 `std::mutex` 传两次——会怎样？"

<details markdown="1">
<summary>答案</summary>

UB。`std::lock` 的算法会在持有 `m` 的情况下对同一个 `m` 调用 `try_lock()`，违反 `mutex` 的前置条件"调用线程不拥有该互斥量"（[[thread.mutex.requirements]]）。`scoped_lock lk(m, m)` 同理。
</details>

!!! question "2. `lock_guard` 的析构函数为什么不检查是否持有锁？"

<details markdown="1">
<summary>答案</summary>

因为 `lock_guard` 在其整个生命周期内**总是**持有锁（¶1）：构造函数要么成功加锁，要么以异常退出（此时对象未构造完成，析构函数不运行）；`adopt_lock` 构造函数的前置条件保证已持有锁；且没有任何成员函数能在中途释放它。不需要 `owns` 标志，所以 `lock_guard` 只是一个引用的大小。
</details>

## 小结

| | 持有锁的时间 | 可移动 | 可中途解锁/加锁 | 多个互斥量 | 误用检测 |
|---|---|---|---|---|---|
| `lock_guard` | 整个生命周期 | 否 | 否 | 否 | — |
| `scoped_lock` | 整个生命周期 | 否 | 否 | 是（`std::lock`） | — |
| `unique_lock` | 可变（`owns`） | 是 | 是 | 否（但可传给 `std::lock`） | `system_error` |
| `shared_lock` | 可变（`owns`），共享锁 | 是 | 是 | 否 | `system_error` |

- 被引用的可锁对象必须在锁的生命周期内存在。
- `std::lock`/`scoped_lock` 承诺不死锁，具体调用序列未指定。
- 永远给锁对象起名字。
