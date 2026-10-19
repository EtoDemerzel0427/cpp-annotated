---
title: 锁与通用加锁算法
summary: lock_guard、scoped_lock、unique_lock、shared_lock 这四种 RAII 锁各管什么，被锁的互斥量为什么必须比锁活得久，哪些误用会抛 system_error 而不是 UB，以及 std::lock 怎样保证不死锁。
status: done
covers: *, thread.lock.algorithm
related: thread.mutex, thread.mutex.requirements, thread.req, thread.condition, basic.life, dcl.ambig.res
tags: 标准库, 并发, 锁, RAII, 死锁
updated: 2026-10-19
---

!!! tldr
    - 锁是在析构时自动解锁互斥量的 RAII 对象。它只引用互斥量，不管理互斥量的生命周期：互斥量先于锁销毁就是 UB。
    - `lock_guard` 和 `scoped_lock` 在整个生命周期内一直持锁；`unique_lock` 和 `shared_lock` 用一个 `owns` 标志记录是否持锁，可以推迟加锁、中途解锁、移动。
    - 对 `unique_lock` 重复加锁或在未持锁时解锁会抛 `system_error`，同样的操作直接作用在 `std::mutex` 上是 UB。`release()` 不解锁。
    - `std::lock` 和多参数的 `scoped_lock` 保证不死锁，但具体的加锁顺序未指定。
    - `std::unique_lock<std::mutex>(m);` 声明了一个名为 `m` 的变量，什么也没锁。锁对象一定要起名字。

## 为什么需要锁

```cpp
std::mutex m;
int balance;

void withdraw(int n) {
  m.lock();
  if (balance < n) return;       // 忘了 unlock
  balance -= n;
  m.unlock();
}
```

提前返回或抛出异常都会跳过 `unlock`，互斥量从此一直被占用。线程在持有互斥量时结束也是 UB（[[thread.mutex.requirements]]）。

[thread.lock.general] ¶1 标准库的解决办法是**锁**（lock）：一个持有可锁对象引用的对象，它可以在自己析构时（比如离开块作用域时）解锁这个可锁对象。可锁对象指具有 `lock`/`unlock` 等成员的类型，标准互斥量都是（[[thread.req]]）。锁当前在替某个线程管理可锁对象的所有权时，称锁**拥有**这个可锁对象。

同一段还规定：锁不管理它所引用的可锁对象的生命周期。下面讲的四种锁都把这一点写成了要求，违反就是 UB。

¶2 有些锁的构造函数接受一个标签参数，说明构造时怎样处理可锁对象：

| 标签 | 含义 |
|---|---|
| `std::defer_lock` | 不加锁 |
| `std::try_to_lock` | 尝试加锁，不阻塞 |
| `std::adopt_lock` | 调用线程已经持有锁，由锁对象接管 |

## lock_guard：构造加锁，析构解锁 [thread.lock.guard]

```cpp run ok
#include <mutex>
std::mutex m;
int balance = 100;

bool withdraw(int n) {
  std::lock_guard lk(m);      // m.lock()
  if (balance < n) return false;
  balance -= n;
  return true;
}                             // ~lock_guard: m.unlock()

int main() { return withdraw(30) ? 0 : 1; }
```

¶1 `lock_guard` 在它的整个生命周期内一直持有可锁对象的所有权。如果它引用的可锁对象没有存在于 `lock_guard` 的整个生命周期，行为未定义 {{ub}}。模板实参只需满足 *Cpp17BasicLockable*，也就是有 `lock` 和 `unlock`。

¶2 `lock_guard(m)` 保存对 `m` 的引用并调用 `m.lock()`。¶6 析构函数调用 `unlock()`。

¶3 `lock_guard(m, adopt_lock)` 只保存引用，不加锁。它的前置条件是调用线程已经持有 `m` 上的非共享锁；¶5 它不抛异常。

`lock_guard` 不可复制、不可移动，也没有解锁、查询之类的成员函数。因为它总是持锁，析构函数不需要检查任何状态，对象里只有一个引用。

## scoped_lock：一次锁多个 [thread.lock.scoped] {{c++17}}

两个线程以相反的顺序给同一对互斥量加锁，是最常见的死锁：

```cpp run title="scoped-lock-transfer.cpp" ok
#include <mutex>
#include <thread>

struct Account {
  std::mutex m;
  long balance = 100;
};

void transfer(Account& from, Account& to, long amt) {
  std::scoped_lock lk(from.m, to.m);   // 两把锁一起锁，不会死锁
  from.balance -= amt;
  to.balance += amt;
}

int main() {
  Account a, b;
  std::jthread t1([&] { for (int i = 0; i < 100000; ++i) transfer(a, b, 1); });
  std::jthread t2([&] { for (int i = 0; i < 100000; ++i) transfer(b, a, 1); });
}
```

如果把 `scoped_lock` 换成两个依次构造的 `lock_guard`，t1 先锁 a 再锁 b，t2 先锁 b 再锁 a，几乎必然死锁。

¶1 `scoped_lock` 是可变参数版本的 `lock_guard`，同样一直持锁，同样要求被引用的可锁对象存在于它的整个生命周期。对模板实参的要求分两种情况：

- ¶1.1 只有一个类型时，它需满足 *Cpp17BasicLockable*，成员 `mutex_type` 就是这个类型；
- ¶1.2 否则，每个类型都要满足 *Cpp17Lockable*（多一个 `try_lock`），并且没有 `mutex_type` 成员。

¶2 构造函数按数量分三种情况：零个可锁对象时什么也不做；一个时调用 `m.lock()`；多个时调用 `std::lock(m...)`，用下文的免死锁算法。零个参数也合法，泛型代码写 `std::scoped_lock lk(ms...);` 时不必单独处理空包。

¶3 采纳已有锁的构造函数是 `scoped_lock(adopt_lock, m...)`。标签放在最前面，因为参数包必须在最后，这与 `lock_guard(m, adopt_lock)` 的顺序相反。前置条件是调用线程持有每个 `m` 上的非共享锁。¶6 析构函数对每个可锁对象调用 `unlock()`。

## unique_lock：可以不持锁的锁 [thread.lock.unique]

`unique_lock` 内部是一个指针 `pm` 和一个布尔值 `owns`。`owns` 记录当前是否持锁，所以它可以先不加锁、中途解锁再加锁、把所有权移交给另一个 `unique_lock`。`condition_variable::wait` 要求的正是这种锁（[[thread.condition]]）。

### 生命周期要求与可锁性 [thread.lock.unique.general]

¶1 `unique_lock` 不可复制，可以移动。如果 `pm` 不为空，而它指向的可锁对象没有存在于 `unique_lock` 剩余的整个生命周期，行为未定义。模板实参需满足 *Cpp17BasicLockable*。

¶2 注 1 指出，`unique_lock<Mutex>` 本身也是可锁对象：它满足 *Cpp17BasicLockable*；`Mutex` 满足 *Cpp17Lockable* 或 *Cpp17TimedLockable* 时，它也满足对应的要求。所以 `unique_lock` 可以再传给 `std::lock` 或 `condition_variable_any`。

### 构造 [thread.lock.unique.cons]

| 构造函数 | 段落 | 效果 | 之后的 `owns` |
|---|---|---|---|
| `unique_lock()` | ¶1 | 不关联任何互斥量 | `false` |
| `unique_lock(m)` | ¶2–¶3 | `m.lock()` | `true` |
| `unique_lock(m, defer_lock)` | ¶4 | 不加锁，`noexcept` | `false` |
| `unique_lock(m, try_to_lock)` | ¶5–¶7 | `m.try_lock()` | 它的返回值 |
| `unique_lock(m, adopt_lock)` | ¶8–¶10 | 不加锁；前置条件：调用线程已持有 `m` | `true` |
| `unique_lock(m, abs_time)` | ¶11–¶13 | `m.try_lock_until(abs_time)` | 它的返回值 |
| `unique_lock(m, rel_time)` | ¶14–¶16 | `m.try_lock_for(rel_time)` | 它的返回值 |

`try_to_lock` 和两个限时版本还要求 `Mutex` 满足 *Cpp17Lockable* 或 *Cpp17TimedLockable*。标准把这写成前置条件，而不是约束；实际上类型缺少 `try_lock` 时会在实例化时编译失败。

¶17 移动构造接管 `u` 的 `pm` 和 `owns`，`u` 变成不关联互斥量、不持锁。¶18 移动赋值等价于 `unique_lock(std::move(u)).swap(*this)`：`*this` 原来持有的锁转到临时对象里，随临时对象析构而释放。¶20 析构函数在 `owns` 为真时调用 `pm->unlock()`。

### 误用会抛异常 [thread.lock.unique.locking]

¶1–¶4 `lock()` 的效果如同 `pm->lock()`，之后 `owns` 为真。它有两个错误条件，出现时抛 `system_error`：

- ¶4.1 `pm` 为空：`operation_not_permitted`；
- ¶4.2 进入时 `owns` 已经为真：`resource_deadlock_would_occur`。

`try_lock`（¶5–¶10）、`try_lock_until`（¶11–¶16）、`try_lock_for`（¶17–¶22）有同样的两个错误条件。

¶23–¶26 `unlock()` 在进入时 `owns` 为假时报告 `operation_not_permitted`。

```cpp run title="unique-lock-errors.cpp" ok
#include <cstdio>
#include <mutex>
#include <system_error>

int main() {
  std::mutex m;
  std::unique_lock lk(m, std::defer_lock);
  try {
    lk.unlock();                 // 未持锁时解锁
  } catch (const std::system_error& e) {
    std::printf("%d\n", e.code() == std::errc::operation_not_permitted);         // 1
  }
  lk.lock();
  try {
    lk.lock();                   // 已持锁时再加锁
  } catch (const std::system_error& e) {
    std::printf("%d\n", e.code() == std::errc::resource_deadlock_would_occur);   // 1
  }
}
```

直接对 `std::mutex` 做同样的事都是 UB：已持有时再 `lock`，或未持有时 `unlock`，都违反 [[thread.mutex.requirements]] 的前置条件。`unique_lock` 用 `owns` 记住了自己是否持锁，所以能把这些错误变成有定义的异常。

### 修改器与观察器 [thread.lock.unique.mod] [thread.lock.unique.obs]

[thread.lock.unique.mod] ¶2–¶3 `release()` 把 `pm` 置空、`owns` 置假，返回原来的 `pm`。它不解锁：之前持有的锁从此由调用者负责手动 `unlock()`。

此外还有 `swap`，以及观察器 `owns_lock()`、`explicit operator bool()`（都返回 `owns`）和 `mutex()`（返回 `pm`）。

## shared_lock：共享锁的 unique_lock [thread.lock.shared] {{c++14}}

`shared_lock` 和 `unique_lock` 结构相同，区别是它获取的是共享锁：加锁调用 `lock_shared`、`try_lock_shared` 等，析构调用 `unlock_shared`。读写锁 `std::shared_mutex` 的读者通常这样写：

```cpp run ok
#include <map>
#include <shared_mutex>
#include <string>

std::shared_mutex rw;
std::map<std::string, int> table;

int lookup(const std::string& k) {
  std::shared_lock lk(rw);           // 多个读者可同时持有
  auto it = table.find(k);
  return it == table.end() ? -1 : it->second;
}

void update(const std::string& k, int v) {
  std::unique_lock lk(rw);           // 写者独占
  table[k] = v;
}

int main() { update("a", 1); return lookup("a") == 1 ? 0 : 1; }
```

[thread.lock.shared.general] ¶1 生命周期要求与 `unique_lock` 相同；模板实参需满足 *Cpp17SharedLockable*。¶2 注 1 指出，`shared_lock<Mutex>` 满足 *Cpp17Lockable*，它的 `lock()` 获取的是共享锁。这样 `shared_lock` 可以传给 `condition_variable_any::wait`，等待期间释放、醒来后重新获取的都是共享锁。

其余子条款与 `unique_lock` 一一对应。[thread.lock.shared.cons] ¶7 `adopt_lock` 版本的前置条件是调用线程已持有 `m` 上的共享锁；[thread.lock.shared.locking] 的错误条件与 `unique_lock` 相同。

## 通用加锁算法 [thread.lock.algorithm]

两个函数模板都接受至少两个参数，每个参数的类型需满足 *Cpp17Lockable*（¶1、¶4）。适当实例化的 `unique_lock` 满足这一要求。

### std::try_lock（¶1–¶3）

¶2 `std::try_lock(l1, l2, ...)` 从第一个参数开始，依次调用 `try_lock()`，直到全部成功，或某一次失败（返回 `false` 或抛出异常）。一旦失败，就对前面已经锁上的参数调用 `unlock()`，不再继续。

¶3 全部成功时返回 `-1`，否则返回失败的那个参数的下标（从 0 开始）。

### std::lock（¶4–¶5）

!!! std
    The sequence of calls does not result in deadlock, but is otherwise unspecified.

¶5 `std::lock(l1, l2, ...)` 通过对各参数调用 `lock()`、`try_lock()`、`unlock()` 的某个序列锁住全部参数。这个序列不会造成死锁，除此之外未指定 {{unspec}}。注 3 提到可以用尝试并退让（try-and-back-off）一类的算法。如果某次 `lock()` 或 `try_lock()` 抛出异常，已经锁上的参数都会被解锁。

不会死锁的承诺对所有用 `std::lock` 或 `scoped_lock` 锁同一组互斥量的线程成立，不论它们传参的顺序。另一个线程如果用 `lock_guard` 按自己的顺序逐个加锁，仍然可能与之死锁。

!!! impl "libc++ 的算法（`<mutex>`）"
    两个参数时，`std::lock` 循环执行：阻塞地锁 `l0`，再 `try_lock` `l1`，成功就返回，失败就解锁 `l0` 并让出 CPU；然后反过来，阻塞地锁 `l1`、尝试 `l0`。

    参数更多时，每一轮阻塞地锁住一个参数，再对其余参数调用 `std::try_lock`。如果第 j 个失败，就全部释放，下一轮先阻塞地锁第 j 个。也就是说，线程总是在上一轮让它失败的那个互斥量上阻塞等待，而不是空转重试。这种算法不会死锁，但高度争用时可能反复重试多轮。

## 常见误解

!!! pitfall "`std::unique_lock<std::mutex>(m);` 能锁住 m"
    按 [[dcl.ambig.res]]，这条语句是一个声明：它声明了一个名为 `m`、默认构造的 `unique_lock<mutex>` 变量，遮蔽了外层的 `m`，什么也没锁。

    ```cpp title="vexing-lock.cpp" ok
    #include <mutex>
    std::mutex m;
    int shared;
    void f() {
      std::unique_lock<std::mutex>(m);   // 声明了一个名为 m 的局部变量
      ++shared;                          // 没有受到保护
    }
    void g() {
      std::scoped_lock{m};               // 临时对象：在分号处就解锁了
      ++shared;                          // 也没有受到保护
    }
    int main() { f(); g(); }
    ```

    两个函数都是良构的，只是锁没有起作用。Clang 23 对 `f` 给出 `-Wvexing-parse` 警告；libc++ 把 `scoped_lock` 的构造函数标为 `[[nodiscard]]`，所以 `g` 也会得到一条警告。给锁对象起名字就能避免这两种错误：`std::scoped_lock lk(m);`。

!!! pitfall "锁可以比互斥量活得久"
    ```cpp
    std::unique_lock<std::mutex> make_lock() {
      std::mutex m;
      return std::unique_lock(m);   // 返回后 m 已销毁，锁还引用着它：UB
    }
    ```
    四种锁都要求被引用的可锁对象在锁的生命周期内一直存在。

!!! pitfall "`release()` 会解锁"
    `release()` 只是让 `unique_lock` 放手，锁仍然被持有。调用者忘记手动 `unlock()`，线程就会在持有互斥量时结束，这是 UB。

## 思考题

!!! question "思考题 1"
    `std::lock(m, m)`，同一个 `std::mutex` 传两次，会怎样？

<details markdown="1">
<summary>答案</summary>

UB。算法会在已经持有 `m` 时对 `m` 调用 `try_lock()` 或 `lock()`，违反 `std::mutex` 的前置条件：调用线程不得已拥有这个互斥量（[[thread.mutex.requirements]]）。`std::scoped_lock lk(m, m);` 也一样。
</details>

!!! question "思考题 2"
    `lock_guard` 的析构函数为什么不检查是否持锁？

<details markdown="1">
<summary>答案</summary>

因为它在整个生命周期内总是持锁（¶1）。普通构造函数要么成功加锁，要么抛出异常，此时对象没有构造完成，析构函数不会运行；`adopt_lock` 版本的前置条件保证调用线程已经持锁；它也没有任何能中途解锁的成员函数。
</details>

## 小结

| | 持锁时间 | 可移动 | 可中途解锁、加锁 | 多个互斥量 | 误用 |
|---|---|---|---|---|---|
| `lock_guard` | 整个生命周期 | 否 | 否 | 否 | 无此类操作 |
| `scoped_lock` | 整个生命周期 | 否 | 否 | 是（`std::lock`） | 无此类操作 |
| `unique_lock` | 由 `owns` 记录 | 是 | 是 | 可以传给 `std::lock` | 抛 `system_error` |
| `shared_lock` | 由 `owns` 记录（共享锁） | 是 | 是 | 可以传给 `std::lock` | 抛 `system_error` |
