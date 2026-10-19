---
title: 互斥量要求与六种互斥量
summary: 标准库互斥量的同步语义：谁拥有互斥量、unlock 与后续加锁同步、失败的 try_lock 不同步、哪些误用是未定义行为，以及递归、超时与共享互斥量的额外规则。
status: done
covers: *
related: thread.mutex, thread.req, thread.lock, thread.condition, intro.races, atomics.order, structure.specifications
tags: 标准库, 并发, 互斥量, UB
updated: 2026-10-19
---

!!! tldr
    - 线程从加锁成功到调用 `unlock` 为止拥有互斥量。`unlock()` 与随后获得同一互斥量所有权的加锁操作同步，这是用锁保护数据在标准中的依据。
    - `try_lock()` 可以虚假失败，失败的 `try_lock()` 不同步，不能据此推断另一个线程的状态。
    - 对非递归互斥量重复加锁、解锁不归自己所有的互斥量、销毁被持有的互斥量、持有互斥量的线程结束，都是未定义行为，不保证死锁或抛异常。
    - 共享互斥量中，读者之间不同步。在共享锁下修改数据是数据竞争；递归地获取共享锁是 UB。

## 拥有 [thread.mutex.requirements.general]

[[thread.req]] 中的 *Cpp17Lockable* 系列要求只规定了接口，并明确说明锁的所有权性质和同步都不在要求之内。[thread.mutex.requirements] 给标准库自己的六种互斥量补上了同步语义，它也是 [[intro.races#3]] 注 3（获取互斥量是 acquire 操作，释放是 release 操作）的规范来源。

¶1 互斥量对象帮助防止数据竞争，并让执行代理之间可以安全地同步数据。**执行代理**（execution agent）指线程这类可以与其他代理并行工作的实体（[[thread.req.lockable.general]]）。执行代理从成功调用某个加锁函数起，到调用 `unlock` 为止，**拥有**（owns）这个互斥量。互斥量可以是递归或非递归的，可以同时授予一个或多个执行代理所有权。下面的前置条件都用拥有来表述。

## 公共要求 [thread.mutex.requirements.mutex.general]

¶1 **互斥量类型**是 `mutex`、`recursive_mutex`、`timed_mutex`、`recursive_timed_mutex`、`shared_mutex`、`shared_timed_mutex`，它们都满足 *Cpp17Lockable*。

¶2 它们可以默认构造和析构，初始化失败时抛 `system_error`，既不可复制也不可移动。不可移动的一个原因是其他线程可能正阻塞在这个对象的地址上。¶3 列出成员函数可能报告的错误条件，如 `operation_not_permitted`（线程没有权限）。

### 加锁和解锁如同原子操作（¶4）

!!! std
    For purposes of determining the existence of a data race, these behave as atomic operations. The lock and unlock operations on a single mutex appear to occur in a single total order.

¶4 在判断是否存在数据竞争时，加锁和解锁操作表现为原子操作；同一互斥量上的加锁和解锁操作看起来以单一全序发生。注 2 说可以把这个全序看作互斥量的修改顺序。

这句话有两层作用。第一，多个线程同时 `lock` 同一个互斥量不是数据竞争，否则互斥量就没法用了。第二，下面同步规则里说的之前的 `unlock`，指的就是在这个全序中排在前面的 `unlock`。

注 3 补充：互斥量的构造和析构不必是线程安全的，需要用其他同步手段保证互斥量对象已经初始化并且对其他线程可见。

### lock（¶5–¶12）

| 段落 | 规定 |
|---|---|
| ¶6 前置条件 | 对 `mutex`、`timed_mutex`、`shared_mutex`、`shared_timed_mutex`，调用线程不拥有这个互斥量 |
| ¶7 效果 | 阻塞调用线程，直到为它取得所有权 |
| ¶8 同步 | 同一对象上之前的 `unlock()` 与本操作同步 |
| ¶9 后置条件 | 调用线程拥有这个互斥量 |
| ¶11–¶12 异常 | 必要时抛 `system_error`；错误条件包括实现检测到将会死锁时的 `resource_deadlock_would_occur` |

按 ¶6，对非递归互斥量重复加锁违反前置条件，是 UB {{ub}}。标准不保证死锁，也不保证抛异常。¶12.2 只是说，如果实现恰好检测到了，可以报告 `resource_deadlock_would_occur`。

### try_lock（¶13–¶19）

¶14 的前置条件与 `lock` 相同。¶15 `try_lock` 不阻塞地尝试取得所有权，失败时没有效果、立即返回。实现可以在没有任何线程持有互斥量时也失败；注 4 说这种虚假失败通常很少见，但它允许基于简单 CAS 的实现。实现应当保证没有竞争时 `try_lock()` 不会一直返回 `false`。

¶16 只有 `try_lock()` 返回 `true` 时，之前的 `unlock()` 才与它同步。¶19 `try_lock` 不抛异常。

!!! std
    Since `lock()` does not synchronize with a failed subsequent `try_lock()`, the visibility rules are weak enough that little would be known about the state after a failure, even in the absence of spurious failures.

¶16 的注 5 说明，`try_lock()` 失败不能用来推断另一个线程已经拿到锁、因而它在加锁之前写的东西我都能看到：

```cpp title="trylock-failure.cpp" ub
#include <chrono>
#include <mutex>
#include <thread>
std::mutex m;
int data = 0;
int main() {
  std::thread t([] {
    data = 1;                        // ① 加锁之前写
    std::lock_guard g(m);            // ②
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
  });
  while (m.try_lock()) m.unlock();   // 直到 try_lock 失败
  int r = data;   // UB：失败的 try_lock 不同步，① 与此读取之间没有 happens before
  (void)r;
  t.join();
}
```

ThreadSanitizer 对这个程序报告 `data race`。

### unlock（¶20–¶25）

¶21 前置条件是调用线程拥有这个互斥量。¶22 释放调用线程的所有权。¶24 本操作与随后取得同一对象所有权的加锁操作同步。¶25 不抛异常。

违反 ¶21 的典型情况有三种：解锁一个从未加锁的互斥量；在线程 A 加锁、在线程 B 解锁；对已经解锁的互斥量再解锁一次。都是 UB。

```cpp title="unlock-not-owned.cpp" ub
#include <cstdio>
#include <mutex>
int main() {
  std::mutex m;
  m.unlock();   // UB：调用线程不拥有 m（¶21）
  std::puts("returned");
}
```

用 Clang 23 + libc++ 在 macOS 上运行，程序打印 `returned` 后正常退出，没有任何诊断。libc++ 的 `mutex::unlock` 直接转调 `pthread_mutex_unlock`，在未启用库断言时不检查返回值。这只是这一次碰巧没出事。

## mutex [thread.mutex.class]

¶1 `mutex` 是非递归、独占所有权的互斥量。一个线程拥有它时，其他线程的获取尝试会失败（`try_lock`）或阻塞（`lock`），直到拥有者调用 `unlock`。¶3 它满足全部互斥量要求，是标准布局类。它的默认构造函数是 `constexpr` 且 `noexcept` 的，见 [[thread.mutex]]。

¶4 注 2：拥有 `mutex` 的线程再对它调用 `lock()`，程序可能死锁；实现如果能检测到，可能报告 `resource_deadlock_would_occur`。规范性的规则仍是上面 ¶6 的前置条件，这只是对可能后果的说明。

¶5 下面两种情况是 UB {{ub}}：销毁一个被任何线程拥有的 `mutex`；线程在拥有 `mutex` 时结束。后者意味着线程函数忘记解锁就返回是 UB，这是使用 RAII 锁（[[thread.lock]]）的又一个理由。

### unlock 之后立即销毁（¶2）

¶2 注 1 讲了一个常被忽视的场景：线程 A 调用 `unlock()` 之后，线程 B 可能加锁、发现互斥量已经没人用、解锁并销毁它，这一切都可能发生在 A 看起来从 `unlock` 返回之前。只要 A 在 `unlock` 返回后不再访问这个互斥量，符合标准的实现必须正确处理这种情况。它通常出现在用互斥量保护引用计数的对象里：

```cpp run title="refcounted-mutex.cpp" ok
#include <mutex>
#include <thread>

struct Shared {
  std::mutex m;
  int refs = 2;
};

void release(Shared* s) {
  s->m.lock();
  bool last = --s->refs == 0;
  s->m.unlock();        // 另一个线程可能紧接着 delete s
  if (last) delete s;   // OK
}

int main() {
  auto* s = new Shared;
  std::thread a(release, s), b(release, s);
  a.join(); b.join();
}
```

调用者在 `unlock` 之后不再碰 `s->m`；注 1 要求实现保证 `unlock` 内部也不会。假如某个实现的 `unlock` 先把状态置为未锁定，再去读互斥量里的等待队列唤醒等待者，就会访问已释放的内存，注 1 正是要排除这种实现。这个程序在 ThreadSanitizer 和 AddressSanitizer 下都没有报告。

## recursive_mutex [thread.mutex.recursive]

```cpp run title="recursive.cpp" ok
#include <cstdio>
#include <mutex>

std::recursive_mutex rm;
int depth = 0;

void visit(int n) {
  std::lock_guard g(rm);   // 同一线程重复加锁：合法
  ++depth;
  if (n > 0) visit(n - 1);
}

int main() {
  visit(3);
  std::printf("%d\n", depth);   // 4
}
```

¶1 `recursive_mutex` 是递归、独占所有权的互斥量。¶3 拥有者可以再次 `lock()` 或 `try_lock()`，获得额外层级的所有权。能获得多少层未指定 {{unspec}}；达到上限后再 `try_lock()` 会失败，再 `lock()` 会抛 `system_error`。每一层所有权都要对应一次 `unlock()`，所有层级都释放后，其他线程才能取得所有权。

¶4 与 `mutex` 一样，销毁被拥有的 `recursive_mutex`、线程在拥有它时结束，都是 UB。

## 超时互斥量 [thread.timedmutex.requirements]

[thread.timedmutex.requirements.general] ¶1 **超时互斥量类型**是 `timed_mutex`、`recursive_timed_mutex`、`shared_timed_mutex`，它们满足 *Cpp17TimedLockable*。

`try_lock_for(rel_time)`（¶2–¶8）在相对时限内尝试取得所有权。前置条件与 `lock` 类似：对非递归的类型，调用线程不能已经拥有它。¶4 规定 `rel_time` 小于等于零时不阻塞地尝试，如同 `try_lock()`；只有取得了所有权，函数才会在时限之前返回。和 `try_lock()` 一样，即使锁可用也不保证取得。¶5 返回 `true` 时，之前的 `unlock()` 与之同步。¶8 可能抛出与超时相关的异常（[[thread.req]]）。

`try_lock_until(abs_time)`（¶9–¶15）同理：`abs_time` 已经过去时不阻塞地尝试；¶12 返回 `true` 时同步。

### timed_mutex 与 recursive_timed_mutex

[thread.timedmutex.class] ¶1 `timed_mutex` 是非递归、独占所有权的互斥量，¶2 是标准布局类。¶3 列出三种 UB：

- ¶3.1 销毁被任何线程拥有的 `timed_mutex`；
- ¶3.2 拥有 `timed_mutex` 的线程对它调用 `lock()`、`try_lock()`、`try_lock_for()` 或 `try_lock_until()`；
- ¶3.3 线程在拥有它时结束。

¶3.2 把 `try_lock` 也列了进来：对已经拥有的非递归互斥量调用 `try_lock()`，不会安全地返回 `false`。`mutex` 也一样，依据是公共要求中 `try_lock` 的前置条件（¶14），只是 `mutex` 的类条款没有重复列出。

[thread.timedmutex.recursive] 中 `recursive_timed_mutex` 与 `recursive_mutex` 平行，四种加锁函数都可以增加所有权层级。

## 共享互斥量 [thread.sharedmutex.requirements]

```cpp run title="shared-mutex.cpp" ok
#include <cstdio>
#include <map>
#include <mutex>
#include <shared_mutex>
#include <string>
#include <thread>
#include <vector>

class Registry {
  mutable std::shared_mutex m;
  std::map<std::string, int> table;
public:
  int get(const std::string& k) const {
    std::shared_lock lk(m);   // 多个读者可以同时进入
    auto it = table.find(k);
    return it == table.end() ? -1 : it->second;
  }
  void set(const std::string& k, int v) {
    std::unique_lock lk(m);   // 写者独占
    table[k] = v;
  }
};

int main() {
  Registry r;
  r.set("a", 1);
  {
    std::vector<std::jthread> ts;
    for (int i = 0; i < 4; ++i)
      ts.emplace_back([&] {
        for (int k = 0; k < 1000; ++k) (void)r.get("a");
      });
    ts.emplace_back([&] {
      for (int k = 0; k < 1000; ++k) r.set("a", k);
    });
  }
  std::printf("%d\n", r.get("a"));   // 999
}
```

### 公共要求

[thread.sharedmutex.requirements.general] ¶1 **共享互斥量类型**是 `shared_mutex` 和 `shared_timed_mutex`，它们满足互斥量类型的全部要求，另外满足 *Cpp17SharedLockable*。

¶2 除了独占所有权，共享互斥量还提供**共享锁**所有权模式：多个执行代理可以同时持有共享锁，但有代理持有共享锁时，没有代理持有独占锁，反之亦然。能同时共享的代理数的上限未指定，但至少是 10000；超过上限的代理会阻塞，直到共享锁的数量降到上限以下。

| 操作 | 前置条件 | 同步 |
|---|---|---|
| `lock_shared()`（¶3–¶10） | 调用线程对它没有任何所有权（¶4） | 之前的 `unlock()` 与之同步（¶6） |
| `unlock_shared()`（¶11–¶16） | 调用线程持有共享锁（¶12） | 与随后取得所有权的 `lock()` 同步（¶15） |
| `try_lock_shared()`（¶17–¶23） | 没有任何所有权（¶18） | 返回 `true` 时，之前的 `unlock()` 与之同步（¶20） |

把这些规则和公共要求中 `lock`/`unlock` 的规则放在一起，同步关系如下：

| 从 | 到 | 同步？ |
|---|---|---|
| 写者 `unlock()` | 写者 `lock()` | 是（[thread.mutex.requirements.mutex.general] ¶8） |
| 写者 `unlock()` | 读者 `lock_shared()` | 是（¶6） |
| 读者 `unlock_shared()` | 写者 `lock()` | 是（¶15） |
| 读者 `unlock_shared()` | 读者 `lock_shared()` | 否 |

最后一行是有意的：读者只读，彼此不需要同步。但这也意味着在共享锁下修改数据是数据竞争，即使每个修改者都持有锁。`mutable` 缓存、惰性初始化的成员都属于这种情况。

### shared_mutex 与 shared_timed_mutex

[thread.sharedmutex.class] ¶1 `shared_mutex` 是非递归、具有共享所有权语义的互斥量，¶2 是标准布局类。¶3 列出三种 UB：

- ¶3.1 销毁被任何线程拥有的 `shared_mutex`；
- ¶3.2 线程试图递归地获得任何所有权，包括持有共享锁时再次 `lock_shared()`；
- ¶3.3 线程在持有任何所有权时结束。

¶4 `shared_mutex` 可以是 `shared_timed_mutex` 的别名。

¶3.2 常被误认为对共享锁无害。问题在于：读者 A 持有共享锁时，写者 B 开始等待；为了避免写者饥饿，许多实现会阻止新的共享加锁。于是 A 再次 `lock_shared()` 要等 B，B 要等 A，形成死锁。

[thread.sharedtimedmutex.requirements] 中的 `shared_timed_mutex` 同时满足超时互斥量和共享互斥量的要求，另外提供 `try_lock_shared_for` 和 `try_lock_shared_until`（¶2–¶15）：前置条件是没有任何所有权；时限为零或已过时不阻塞地尝试；返回 `true` 时之前的 `unlock()` 与之同步。[thread.sharedtimedmutex.class] 规定的三种 UB 与 `shared_mutex` 相同。

!!! impl "libc++ 的 shared_mutex：两道闸门"
    libc++ 的 `shared_mutex` 不使用 `pthread_rwlock_t`，而是一个 `mutex`、两个 `condition_variable` 和一个 `unsigned` 状态字：最高位表示有写者进入，其余 31 位是读者计数，上限 2<sup>31</sup>−1，远超 ¶2 要求的 10000。写者先在第一道闸门设置最高位，此后新读者被挡在外面；再在第二道闸门等现有读者全部离开。这是写者优先的策略，也正是递归共享加锁会死锁的典型原因。

## 常见误解

!!! pitfall "同一线程重复 lock 会死锁"
    对 `mutex` 重复加锁是前置条件违反，是 UB，注 2 只说可能死锁。实际行为取决于平台：默认属性的 pthread 互斥量通常死锁，带错误检查属性的会返回错误，某些调试运行库会直接终止程序。不要依赖其中任何一种。

!!! pitfall "可以在一个线程加锁、另一个线程解锁"
    `std::mutex` 的所有权属于线程。需要在一个线程获取、在另一个线程释放时，用 `std::binary_semaphore`（[[thread.sema]]）。

## 思考题

!!! question "思考题 1"
    构造和析构 `std::mutex` 是线程安全的吗？

<details markdown="1">
<summary>答案</summary>

不必是（公共要求 ¶4 注 3）。互斥量对象本身也需要正确地发布给其他线程：在一个线程里 `new std::mutex`，再用 relaxed 原子指针交给另一个线程去 `lock()`，是数据竞争。命名空间作用域的 `std::mutex` 由 `constexpr` 构造函数常量初始化，在任何线程启动之前就已就绪，没有这个问题。
</details>

!!! question "思考题 2"
    线程 A 执行 `m.lock(); x = 1; m.unlock();`，线程 B 执行 `if (m.try_lock()) { r = x; m.unlock(); }`。有数据竞争吗？

<details markdown="1">
<summary>答案</summary>

没有。B 只在 `try_lock()` 成功时读 `x`。如果在全序中 A 的 `unlock` 先于 B 的 `try_lock`，二者同步（¶16），`x = 1` happens before `r = x`；如果 B 先取得锁，B 的 `unlock` 与 A 的 `lock` 同步（¶24、¶8），`r = x` happens before `x = 1`。两种情况下两次访问都有 happens before 关系。`try_lock` 失败时 B 根本不访问 `x`。
</details>

## 小结

| 规则 | 出处 |
|---|---|
| 加锁和解锁表现为原子操作，同一互斥量上处于单一全序 | 公共要求 ¶4 |
| `unlock()` 与随后取得所有权的加锁操作同步 | 公共要求 ¶8、¶24 |
| `try_lock` 可以虚假失败，失败时不同步 | 公共要求 ¶15–¶16 |
| 对非递归互斥量重复加锁、解锁不归自己的互斥量：UB | 公共要求 ¶6、¶14、¶21 |
| 销毁被拥有的互斥量、线程持有互斥量时结束：UB | 各类的条款 |
| 时限为零或已过时如同 `try_lock` | 超时互斥量 ¶4、¶11 |
| 读者之间不同步；递归获取共享所有权：UB | 共享互斥量 ¶6、¶15；`shared_mutex` ¶3 |
