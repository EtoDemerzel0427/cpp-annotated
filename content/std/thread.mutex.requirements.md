---
title: 互斥量要求与六种互斥量
summary: 互斥量的形式语义——"拥有"的定义、lock/unlock 如同原子操作且处于单一全序、unlock 与后续 lock 同步、失败的 try_lock 不同步、各种前置条件违反（重复加锁、解锁不拥有的互斥量、销毁被持有的互斥量）都是 UB；递归、超时与共享互斥量的额外规则
status: done
covers: *
related: thread.mutex, thread.req, thread.lock, thread.condition, intro.races, atomics.order, structure.specifications
tags: 标准库, 并发, 互斥量, UB
updated: 2026-10-18
---

[thread.req] 中的 *Cpp17Lockable* 系列只规定了接口和"阻塞"的含义，明确说**不涉及同步**。[thread.mutex.requirements] 则为标准库自己的六种互斥量补上了同步语义——这是"用锁保护数据"在标准中的唯一依据，也是 [[intro.races]] ¶3 注 3"获取互斥量是 acquire 操作，释放是 release 操作"的规范来源。

本页覆盖 [thread.mutex.requirements] 的全部子条款：总述、互斥量类型（`mutex`、`recursive_mutex`）、超时互斥量类型（`timed_mutex`、`recursive_timed_mutex`）、共享互斥量类型（`shared_mutex`）、共享超时互斥量类型（`shared_timed_mutex`）。

## 拥有（[thread.mutex.requirements.general]）

¶1 互斥量对象帮助防止数据竞争，并允许在执行代理之间安全地同步数据。执行代理从**成功调用某个加锁函数**起，到**调用 `unlock`** 为止，**拥有**（owns）该互斥量。互斥量可以是递归或非递归的，可以授予一个或多个执行代理同时拥有。标准同时提供递归与非递归的互斥量。

"拥有"是一个**归属于执行代理**的概念（通常就是线程）。下面所有前置条件都用它表述：谁拥有、谁能解锁。

## 互斥量类型的公共要求（[thread.mutex.requirements.mutex.general]）

¶1 **互斥量类型**是 `mutex`、`recursive_mutex`、`timed_mutex`、`recursive_timed_mutex`、`shared_mutex`、`shared_timed_mutex`。注 1：它们都满足 *Cpp17Lockable*（[[thread.req]]）。

¶2 它们满足 *Cpp17DefaultConstructible* 与 *Cpp17Destructible*；初始化失败抛 `system_error`；**既不可复制也不可移动**。不可移动是因为其他线程可能正阻塞在这个对象的地址上。

¶3 成员函数报告的错误条件：`resource_unavailable_try_again`（某个原生句柄类型不可用）、`operation_not_permitted`（线程无权限）、`invalid_argument`（构造时操作的原生句柄类型不正确）。

### 如同原子操作，处于单一全序（¶4）

!!! std
    For purposes of determining the existence of a data race, these behave as atomic operations. The lock and unlock operations on a single mutex appear to occur in a single total order.

    为判断是否存在数据竞争，这些（加锁、解锁）操作表现为原子操作。同一个互斥量上的加锁与解锁操作看起来以单一全序发生。

注 2：这可以看作互斥量的**修改顺序**。注 3：互斥量的**构造与析构不必是线程安全的**；可以用其他同步手段保证互斥量对象被初始化并对其他线程可见。

两层意思：

1. 多个线程同时 `lock` 同一个互斥量**不是**数据竞争（否则互斥量就没法用了）——这是"表现为原子操作"的作用。
2. 全序让下面的同步规则有意义：所谓"**之前的** `unlock`"，指的就是在这个全序中排在前面的 `unlock`。

### lock（¶5–¶12）

- ¶6 *Preconditions*：若 `m` 是 `mutex`、`timed_mutex`、`shared_mutex` 或 `shared_timed_mutex`，调用线程**不拥有**该互斥量。即对非递归互斥量重复加锁违反前置条件，是 UB {{ub}}——标准**不**保证死锁，也不保证抛异常。
- ¶7 *Effects*：阻塞调用线程直到能为其获得所有权。
- ¶8 *Synchronization*：同一对象上**之前的** `unlock()` 操作与本操作**同步**。
- ¶9 *Postconditions*：调用线程拥有该互斥量。
- ¶11–¶12 *Throws* `system_error`，错误条件：`operation_not_permitted`；`resource_deadlock_would_occur`（实现**检测到**将会发生死锁）。

¶12.2 与 ¶6 并存：重复加锁是 UB，但如果实现**恰好**能检测到，它**可以**抛出 `resource_deadlock_would_occur`。这是"UB 允许任何行为"的一个被点名的特例，不是保证。

### try_lock（¶13–¶19）

- ¶14 前置条件同 `lock`。
- ¶15 *Effects*：不阻塞地尝试获得所有权；失败则无效果，立即返回。**实现可以在互斥量没有被任何线程持有时也获取失败。** 注 4：这种虚假失败通常不常见，但允许基于简单 CAS 的实现。实现应当保证在没有竞争的加锁时 `try_lock()` 不会**一直**返回 `false`。
- ¶16 *Synchronization*：**若 `try_lock()` 返回 `true`**，之前的 `unlock()` 与之同步。
- ¶19 *Throws*：Nothing。

¶16 注 5 值得逐字理解：

!!! std
    Since `lock()` does not synchronize with a failed subsequent `try_lock()`, the visibility rules are weak enough that little would be known about the state after a failure, even in the absence of spurious failures.

    由于 `lock()` 不与随后失败的 `try_lock()` 同步，可见性规则弱到这种程度：即使没有虚假失败，失败之后对状态也几乎一无所知。

也就是说，`try_lock()` 返回 `false` **不能**用来推断"另一个线程已经拿到锁、因而它在加锁前写的东西我能看到"。

```cpp title="trylock-failure.cpp" ub
#include <chrono>
#include <mutex>
#include <thread>
std::mutex m;
int data = 0;
int main() {
  std::thread t([] {
    data = 1;                        // ① 在 lock 之前写入
    std::lock_guard g(m);            // ②
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
  });
  while (m.try_lock()) m.unlock();   // 等到 try_lock 失败，"说明" t 已经执行了 ②
  int r = data;                      // UB：失败的 try_lock 不同步，① 与此读取之间没有 happens before
  (void)r;
  t.join();
}
```

### unlock（¶20–¶25）

- ¶21 *Preconditions*：**调用线程拥有该互斥量**。
- ¶22 *Effects*：释放调用线程的所有权。
- ¶24 *Synchronization*：本操作与随后获得同一对象所有权的加锁操作同步。
- ¶25 *Throws*：Nothing。

违反 ¶21 的典型情况：解锁一个从未加锁的互斥量；在 A 线程加锁、B 线程解锁；对已解锁的互斥量再解锁一次。都是 UB。

```cpp title="unlock-not-owned.cpp" ub
#include <cstdio>
#include <mutex>
int main() {
  std::mutex m;
  m.unlock();      // UB：调用线程不拥有 m（¶21）
  std::puts("returned");
}
```

!!! impl "libc++/macOS 不检查"
    这个程序用 Clang 23 + libc++ 在 macOS 上编译运行，打印 `returned` 并正常退出，没有任何诊断。libc++ 的 `mutex::unlock` 只是转调 `pthread_mutex_unlock`，在未启用库断言时不检查其返回值。程序看起来没事，但这种"没事"没有任何保证。

## mutex（[thread.mutex.class]）

类定义：`constexpr mutex() noexcept;`、析构函数、删除的复制操作、`lock`、`try_lock`、`unlock`、`native_handle`。**只有它的默认构造函数是 `constexpr` 且 `noexcept`**。

¶1 `mutex` 是**非递归**、**独占**所有权的互斥量。一个线程拥有它时，其他线程的获取尝试会失败（`try_lock`）或阻塞（`lock`），直到拥有者调用 `unlock` 释放。

¶2 注 1 描述了一个常被忽视的场景：

> 线程 A 调用 `unlock()` 释放互斥量后，线程 B 可能加锁、发现它已不再使用、解锁并**销毁**它——这一切都可能发生在线程 A **看起来**从 `unlock` 调用返回之前。符合标准的实现能正确处理这种情况，只要 A 在 `unlock` 返回后不再访问该互斥量。这种情况通常发生在一个引用计数对象内含一个保护引用计数的互斥量时。

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
  s->m.unlock();          // 另一个线程可能在这里之后立即 delete s
  if (last) delete s;     // OK：注 1 保证 unlock 内部不会在"释放所有权"之后再访问 *s
}

int main() {
  auto* s = new Shared;
  std::thread a(release, s), b(release, s);
  a.join(); b.join();
}
```

关键在于 `unlock` 之后，调用者自己的代码不再碰 `s->m`；注 1 要求实现保证 `unlock` 内部也不会。若某个实现的 `unlock` 是"先把状态置为未锁定，再去唤醒等待者（需要读互斥量里的等待队列）"，就违反了这一点——注 1 正是为了排除这种实现。

¶3 `mutex` 满足全部互斥量要求，是**标准布局类**。

¶4 注 2：拥有 `mutex` 的线程再对它调用 `lock()`，程序可能死锁；实现若能检测，可能观察到 `resource_deadlock_would_occur`。

¶5 以下情况行为未定义 {{ub}}：

- 销毁一个被任何线程拥有的 `mutex`；
- 线程在拥有 `mutex` 时终止。

第二条意味着线程函数忘记解锁就返回是 UB——这是使用 RAII 锁（[[thread.lock]]）的又一个理由。

## recursive_mutex（[thread.mutex.recursive]）

¶1 递归、独占所有权。其他线程的获取尝试会失败或阻塞，直到第一个线程**完全**释放所有权。

¶2 满足全部互斥量要求，是标准布局类。

¶3 拥有者可以通过再次 `lock()` 或 `try_lock()` 获得**额外层级**的所有权。一个线程能获得多少层**未指定** {{unspec}}；已达到最大层级时，再 `try_lock()` 失败，再 `lock()` 抛 `system_error`。线程必须对每一层所有权调用一次 `unlock()`；只有所有层级都释放后，其他线程才能获得所有权。

¶4 UB：销毁被任何线程拥有的 `recursive_mutex`；线程在拥有它时终止。

```cpp run title="recursive.cpp" ok
#include <cstdio>
#include <mutex>

std::recursive_mutex rm;
int depth = 0;

void visit(int n) {
  std::lock_guard g(rm);      // 同一线程重复加锁：合法，每层对应一次 unlock
  ++depth;
  if (n > 0) visit(n - 1);
}

int main() {
  visit(3);
  std::printf("%d\n", depth);   // 4
}
```

## 超时互斥量（[thread.timedmutex.requirements]）

### 公共要求（[thread.timedmutex.requirements.general]）

¶1 **超时互斥量类型**是 `timed_mutex`、`recursive_timed_mutex`、`shared_timed_mutex`；注 1：它们满足 *Cpp17TimedLockable*。

`m.try_lock_for(rel_time)`（¶2–¶8）：

- ¶3 前置条件：对 `timed_mutex`、`shared_timed_mutex`，调用线程不拥有该互斥量；
- ¶4 在相对超时内尝试获得所有权。**若 `rel_time` 小于等于 `rel_time.zero()`，不阻塞地尝试（如同调用 `try_lock()`）**。只有获得所有权时，函数才会在超时之内返回。注 2：与 `try_lock()` 一样，即使锁可用也不保证能获得，但实现应尽力；
- ¶5 返回 `true` 时，之前的 `unlock()` 与之同步；
- ¶8 *Throws*：超时相关异常（[[thread.req]]）。

`m.try_lock_until(abs_time)`（¶9–¶15）：同理；**若 `abs_time` 已过，不阻塞地尝试**；¶12 返回 `true` 时同步。

### timed_mutex 与 recursive_timed_mutex

[thread.timedmutex.class]：¶1 非递归、独占；其他线程的 `lock`/`try_lock_for`/`try_lock_until` 阻塞，直到拥有者释放或超时。¶2 标准布局。¶3 UB：

- ¶3.1 销毁被任何线程拥有的 `timed_mutex`；
- ¶3.2 拥有 `timed_mutex` 的线程对它调用 `lock()`、`try_lock()`、`try_lock_for()` 或 `try_lock_until()`；
- ¶3.3 线程在拥有它时终止。

注意 ¶3.2 把 `try_lock` 也列为 UB：对已拥有的非递归互斥量 `try_lock()` **不会**安全地返回 `false`。`mutex` 也一样（由 ¶14 的前置条件），只是 `mutex` 的类条款里没有重复列出。

[thread.timedmutex.recursive]：¶1–¶4 与 `recursive_mutex` 平行，四种加锁函数都可以增加所有权层级。

## 共享互斥量（[thread.sharedmutex.requirements]）

### 公共要求（[thread.sharedmutex.requirements.general]）

¶1 **共享互斥量类型**是 `shared_mutex` 与 `shared_timed_mutex`，它们满足互斥量类型的要求，并额外满足下面的要求；注 1：它们满足 *Cpp17SharedLockable*。

¶2 除了独占所有权模式，共享互斥量还提供**共享锁**所有权模式。多个执行代理可以同时持有共享锁；但**一个代理持有共享锁时，没有代理持有独占锁，反之亦然**。能同时共享的代理数的上限**未指定，但至少为 10000**；超过上限的代理阻塞，直到其他代理释放共享锁使数量降到上限以下。

`lock_shared()`（¶3–¶10）：

- ¶4 前置条件：调用线程**对该互斥量没有任何所有权**（既不持有独占锁，也不持有共享锁）；
- ¶5 阻塞直到获得共享所有权；抛异常则未获得；
- ¶6 *Synchronization*：**之前的 `unlock()`** 与本操作同步；
- ¶10 错误条件：`operation_not_permitted`、`resource_deadlock_would_occur`。

`unlock_shared()`（¶11–¶16）：

- ¶12 前置条件：调用线程持有共享锁；
- ¶15 *Synchronization*：与**随后获得所有权的 `lock()` 操作**同步。

`try_lock_shared()`（¶17–¶23）：同理，可以虚假失败；返回 `true` 时，之前的 `unlock()` 与之同步。

把 ¶6 与 ¶15 合起来看，同步关系是：

| 从 | 到 | 同步？ |
|---|---|---|
| `unlock()`（写者释放） | `lock()`（写者获取） | 是（[thread.mutex.requirements.mutex.general] ¶8） |
| `unlock()`（写者释放） | `lock_shared()`（读者获取） | 是（¶6） |
| `unlock_shared()`（读者释放） | `lock()`（写者获取） | 是（¶15） |
| `unlock_shared()`（读者释放） | `lock_shared()`（读者获取） | **否** |

最后一行是有意的：读者之间本来就不需要同步，因为它们只读。但这也意味着：**在共享锁下修改数据（比如更新一个 `mutable` 缓存）是数据竞争**，即使每个修改者都"持有锁"。

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
    std::shared_lock lk(m);                 // 多个读者可以同时进入
    auto it = table.find(k);
    return it == table.end() ? -1 : it->second;
  }
  void set(const std::string& k, int v) {
    std::unique_lock lk(m);                 // 写者独占
    table[k] = v;
  }
};

int main() {
  Registry r;
  r.set("a", 1);
  std::vector<std::jthread> ts;
  for (int i = 0; i < 4; ++i) ts.emplace_back([&] { for (int k = 0; k < 1000; ++k) (void)r.get("a"); });
  ts.emplace_back([&] { for (int k = 0; k < 1000; ++k) r.set("a", k); });
  ts.clear();
  std::printf("%d\n", r.get("a"));          // 999
}
```

### shared_mutex（[thread.sharedmutex.class]）

¶1 非递归，具有共享所有权语义。¶2 满足全部共享互斥量要求，标准布局。¶3 UB：

- ¶3.1 销毁被任何线程拥有的 `shared_mutex`；
- ¶3.2 线程**试图递归地获得任何所有权**——包括持有共享锁时再 `lock_shared()`；
- ¶3.3 线程在持有任何所有权时终止。

¶4 `shared_mutex` **可以是** `shared_timed_mutex` 的别名。

¶3.2 的"递归共享加锁"常被误认为安全（"反正是共享锁"）。它不安全的原因：若读者 A 持有共享锁时写者 B 开始等待，许多实现（为了避免写者饥饿）会阻止**新的**共享加锁；A 再次 `lock_shared()` 就会等 B，B 等 A——死锁。

### 共享超时互斥量（[thread.sharedtimedmutex.requirements]）

[thread.sharedtimedmutex.requirements.general] ¶1：`shared_timed_mutex` 是**共享超时互斥量类型**，满足超时互斥量与共享互斥量的要求；注 1：满足 *Cpp17SharedTimedLockable*。¶2–¶15 `try_lock_shared_for`、`try_lock_shared_until`：前置条件"无任何所有权"；超时为零或已过时不阻塞地尝试；返回 `true` 时之前的 `unlock()` 与之同步；抛异常则未获得共享锁。

[thread.sharedtimedmutex.class] ¶1–¶3：与 `shared_mutex` 平行，同样的三种 UB。

## 实现视角

!!! impl "libc++ 的 shared_mutex：两道闸门"
    libc++ 的 `shared_mutex` 不使用 `pthread_rwlock_t`，而是一个 `mutex`、两个 `condition_variable`（`__gate1_`、`__gate2_`）和一个 `unsigned` 状态字：最高位表示"有写者已进入"，其余 31 位是读者计数（所以上限是 2<sup>31</sup>−1，远超 ¶2 要求的 10000）。写者先在第一道闸门处设置最高位——此后新读者被挡在第一道闸门外——再在第二道闸门处等现有读者全部离开。这是一种**写者优先**的策略，也正是 ¶3.2 中"递归共享加锁会死锁"的典型来源。

## 陷阱

!!! pitfall "\"同一个线程重复 lock 会死锁\"——不，是 UB"
    标准对 `mutex` 重复加锁只规定为前置条件违反（¶6），注 2 只说"可能"死锁。实际行为取决于平台：默认属性的 pthread 互斥量通常死锁，带错误检查属性的会返回错误，某些调试运行库会直接终止程序。不要依赖任何一种。

!!! pitfall "跨线程解锁"
    `std::mutex` 的所有权属于线程。需要"在一个线程获取、在另一个线程释放"时，用 `std::binary_semaphore`（[[thread.sema]]）。

!!! pitfall "共享锁下的写"
    读者之间不同步。在 `shared_lock` 下修改任何共享状态（包括 `mutable` 成员、惰性初始化的缓存）都需要额外的同步，比如原子变量或另一把互斥量。

## 思考题

!!! question "1. 构造与析构 `std::mutex` 是线程安全的吗？"

<details markdown="1">
<summary>答案</summary>

不必是（¶4 注 3）。互斥量对象本身也需要被安全地发布给其他线程：在一个线程里 `new std::mutex`，再用 relaxed 原子指针交给另一个线程去 `lock()`，是数据竞争。命名空间作用域的 `std::mutex` 由于是常量初始化的（`constexpr` 构造函数），在任何线程启动之前就已就绪，不存在这个问题。
</details>

!!! question "2. 线程 A：`m.lock(); x = 1; m.unlock();`；线程 B：`if (m.try_lock()) { r = x; m.unlock(); }`。有数据竞争吗？"

<details markdown="1">
<summary>答案</summary>

没有。B 只在 `try_lock()` 成功时读取 `x`。若 A 的 `unlock` 在全序中先于 B 的 `try_lock`，二者同步（¶16），`x = 1` happens before `r = x`；若 B 先获得锁，B 的 `unlock` 与 A 的 `lock` 同步（¶24 + ¶8），`r = x` happens before `x = 1`。两种情况下两次访问都被 happens before 排序。`try_lock` 失败时 B 根本不访问 `x`。
</details>

## 小结

| 规则 | 出处 |
|---|---|
| lock/unlock 表现为原子操作，同一互斥量上处于单一全序 | ¶4 |
| `unlock()` 与随后获得所有权的加锁操作同步 | ¶8、¶24 |
| 失败的 `try_lock` 不同步；`try_lock` 可以虚假失败 | ¶15–¶16 |
| 对非递归互斥量重复加锁、解锁不拥有的互斥量：UB（前置条件） | ¶6、¶14、¶21 |
| 销毁被拥有的互斥量、线程拥有互斥量时终止：UB | 各类条款 |
| 超时为零或已过：如同 `try_lock` | 超时互斥量 ¶4、¶11 |
| 读者之间不同步；递归获取共享所有权：UB | 共享互斥量 ¶6、¶15；`shared_mutex` ¶3 |
