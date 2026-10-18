---
title: 条件变量
summary: condition_variable 与 condition_variable_any 的规范模型——wait 的"三个原子部分"与单一全序如何排除丢失唤醒、虚假唤醒、所有并发等待者必须用同一个互斥量、析构的放宽前置条件与"解锁后再通知"的生命周期陷阱、wait_for 以 steady_clock 计时、重新加锁失败即 terminate、notify_all_at_thread_exit，以及 C++20 的停止令牌可中断等待
status: done
covers: *
papers: P0660R10
related: thread.mutex.requirements, thread.lock, thread.req, thread.stoptoken, atomics.wait, thread.sema, intro.races
tags: 标准库, 并发, 条件变量, 虚假唤醒
updated: 2026-10-18
---

互斥量解决"同一时刻只有一个线程访问"；条件变量解决"等到某个条件成立"。没有条件变量，等待者只能反复"加锁—检查—解锁"空转。条件变量让等待者在条件不成立时**原子地**释放锁并睡眠，由修改条件的线程负责唤醒它。

本页覆盖 [thread.condition] 的全部子条款：总述、`<condition_variable>` 概要、非成员函数 `notify_all_at_thread_exit`、`condition_variable`、`condition_variable_any`（含不可中断与可中断等待）。

## 总述（[thread.condition.general]）

¶1 条件变量提供同步原语，用来阻塞一个线程，直到被另一个线程通知某个条件已满足，或直到到达某个系统时间。`condition_variable` 只能在 `unique_lock<mutex>` 上等待，这使实现可以更高效；`condition_variable_any` 是通用的条件变量，可以在用户提供的锁类型上等待。

¶2 条件变量允许并发调用 `wait`、`wait_for`、`wait_until`、`notify_one`、`notify_all`。

¶3 `notify_one` 与 `notify_all` 的执行是**原子的**。`wait`、`wait_for`、`wait_until` 的执行分三个原子部分进行：

1. 释放互斥量并进入等待状态；
2. 解除等待的阻塞；
3. 重新获取锁。

¶4 实现的行为如同：所有 `notify_one`、`notify_all` 的执行，以及每个 `wait` 类执行的每个部分，都在**一个未指定的、与 happens before 一致的单一全序**中执行。

这两段是条件变量能正确工作的根本。关键在 ¶3 的第 1 部分："释放互斥量**并**进入等待状态"是**一个**原子部分。于是：

- 等待者在持有锁时检查条件，发现不成立，调用 `wait`——释放锁与开始等待之间**没有缝隙**；
- 通知者若要修改条件，必须先获得同一把锁，这只能发生在等待者释放锁之后，也就是等待者**已经**处于等待状态之后；
- 按 ¶4，通知者的 `notify` 在全序中排在等待者的第 1 部分之后，因此一定能唤醒它。

这就是为什么**修改条件必须在持有互斥量时进行**——即使条件变量本身是 `std::atomic<bool>` 也一样。一旦修改发生在锁外，它就可能落在等待者"检查条件"与"进入等待"之间，唤醒丢失：

```text
等待者（持有锁）                    通知者（不持有锁）
--------------------------          ------------------------
检查 ready → false
                                     ready = true
                                     cv.notify_one()   // 此时没有人在等待：丢失
cv.wait(lk)  // 释放锁并等待……永远
```

¶5 条件变量的构造与析构不必同步。

¶6 定义了本条款使用的仅说明用函数：

```cpp
template<class Dur>
  chrono::steady_clock::time_point rel-to-abs(const Dur& rel_time) {
    return chrono::steady_clock::now() + chrono::ceil<chrono::steady_clock::duration>(rel_time);
  }
```

所有 `wait_for` 都被定义为 `wait_until(lock, rel-to-abs(rel_time), ...)`。两个细节：基准是 **`steady_clock`**——落实了 [[thread.req]] 中"相对超时应当用稳定时钟"的建议；用 `ceil` 向上取整，所以 `wait_for(1ns)` 在一个粗粒度的稳定时钟上也不会退化成"不等待"。

## 概要（[condition.variable.syn]）

`<condition_variable>` 声明 `condition_variable`、`condition_variable_any`、`notify_all_at_thread_exit`，以及 `enum class cv_status { no_timeout, timeout };`。

## notify_all_at_thread_exit（[thread.condition.nonmember]）

`void notify_all_at_thread_exit(condition_variable& cond, unique_lock<mutex> lk);`

- ¶1 *Preconditions*：`lk` 被调用线程锁定；并且没有其他线程在 `cond` 上等待，或所有并发等待者提供的锁 `lk.mutex()` 都相同。
- ¶2 *Effects*：把 `lk` 关联的锁的所有权转移到内部存储，安排在当前线程退出时通知 `cond`。这个通知 sequenced after 当前线程所有线程存储期对象的析构，等价于 `cond.notify_all(); lk.unlock();`。
- ¶3 *Synchronization*：隐含的 `lk.unlock()` sequenced after 线程存储期对象的析构。
- ¶4 注 1：锁会一直持有到线程退出，可能因加锁顺序问题导致死锁。
- ¶5 注 2：用户有责任保证等待者遇到虚假唤醒时不会错误地以为线程已经结束。这通常要求被等待的条件在持有 `lk` 上的锁时被满足，且在调用 `notify_all_at_thread_exit` 之前没有释放并重新获取这把锁。

用途：等待一个 detach 线程**连同它的 `thread_local` 对象的析构**一起完成。普通的"最后设个标志再 notify"做不到这一点，因为 `thread_local` 的析构发生在线程函数返回之后。

## condition_variable（[thread.condition.condvar]）

¶1 `condition_variable` 是标准布局类。

¶2–¶3 构造函数：需要时抛 `system_error`；错误条件 `resource_unavailable_try_again`（非内存的资源限制阻止了初始化）。

### 析构：放宽的前置条件（¶4）

¶4 *Preconditions*：**没有线程阻塞在 `*this` 上**。

注 1 解释："即所有线程都已被通知；它们随后可以阻塞在 `wait` 所指定的锁上。这放宽了通常的规则——通常要求所有 `wait` 调用都 happens before 析构。现在只要求**解除等待阻塞的通知** happens before 析构。若在析构函数开始之后还有线程在 `*this` 上等待，则行为未定义，特别是当等待线程在循环中调用 wait 函数、或使用带谓词的 wait 重载时。"

这一放宽允许这样的模式：通知者 `notify_all()` 后立即销毁条件变量，而被唤醒的线程还在"重新获取锁"（第 3 部分）中——它们已经不再"阻塞在 `*this` 上"。

### 通知（¶5–¶6）

- ¶5 `notify_one()`：若有线程阻塞在 `*this` 上，解除其中**一个**的阻塞。
- ¶6 `notify_all()`：解除所有阻塞在 `*this` 上的线程的阻塞。

两者都是 `noexcept`，都**不要求**调用者持有锁。

### wait（¶7–¶16）

`void wait(unique_lock<mutex>& lock);`

- ¶7 *Preconditions*：`lock.owns_lock()` 为 `true` 且 `lock.mutex()` 被调用线程锁定；并且，要么 ¶7.1 没有其他线程在此条件变量上等待，要么 ¶7.2 所有并发等待（`wait`、`wait_for`、`wait_until`）的线程提供的锁，`lock.mutex()` 返回相同的值。
- ¶8 *Effects*：
    - ¶8.1 原子地调用 `lock.unlock()` 并阻塞在 `*this` 上；
    - ¶8.2 被解除阻塞时，调用 `lock.lock()`（可能阻塞在锁上），然后返回；
    - ¶8.3 被 `notify_one()` 或 `notify_all()` 唤醒，**或者虚假地**解除阻塞。
- ¶9 *Postconditions*：`lock.owns_lock()` 为 `true`，`lock.mutex()` 被调用线程锁定。
- ¶10 *Throws*：Nothing。
- ¶11 *Remarks*：若函数未能满足后置条件，调用 `terminate()`。注 2：重新加锁抛出异常时会发生这种情况。

¶7.2 的"同一个互斥量"要求常被忽视：两个线程分别用 `m1`、`m2` 在同一个条件变量上等待是 UB。因为 ¶8.1 的"原子地解锁并阻塞"在实现上依赖于互斥量与条件变量的绑定（pthreads 也有同样的要求）。

¶11 解释了为什么 `wait` 是 `noexcept` 的却可能"失败"：重新加锁失败时，函数既不能返回（后置条件不成立，调用者会以为自己持有锁），也不能抛异常（栈展开时 `unique_lock` 会对一个没锁住的互斥量 `unlock`），只能 `terminate`。

`template<class Predicate> void wait(unique_lock<mutex>& lock, Predicate pred);`

- ¶12 同样的前置条件。
- ¶13 *Effects*：等价于

  ```cpp
  while (!pred())
    wait(lock);
  ```

- ¶15 *Throws*：`pred` 抛出的任何异常。

**虚假唤醒**（spurious wakeup，[[g:spurious-wakeup]]）是 ¶8.3 明文允许的：`wait` 可以在没有任何通知的情况下返回。它不是实现缺陷，而是给实现的自由（某些平台的底层原语会因信号等原因提前返回；`notify_one` 也可能唤醒不止一个）。所以无谓词的 `wait` **必须**写在检查条件的循环里，带谓词的重载就是这个循环的标准写法。

```cpp run title="cv-queue.cpp" ok
#include <condition_variable>
#include <cstdio>
#include <mutex>
#include <queue>
#include <thread>

std::mutex m;
std::condition_variable cv;
std::queue<int> q;
bool closed = false;

void producer() {
  for (int i = 0; i < 5; ++i) {
    {
      std::lock_guard lk(m);
      q.push(i);                     // 修改条件：持有锁
    }
    cv.notify_one();                 // 通知：可以在锁外
  }
  {
    std::lock_guard lk(m);
    closed = true;
  }
  cv.notify_all();
}

void consumer() {
  std::unique_lock lk(m);
  while (true) {
    cv.wait(lk, [] { return !q.empty() || closed; });   // 吸收虚假唤醒
    if (q.empty()) break;            // closed 且队列已空
    int x = q.front(); q.pop();
    lk.unlock();
    std::printf("consumed %d\n", x);
    lk.lock();
  }
}

int main() {
  std::jthread c(consumer), p(producer);
}
```

### 带超时的等待（¶17–¶41）

`wait_until(lock, abs_time)`（¶17–¶22）：

- ¶18 *Effects*：原子地解锁并阻塞；被解除阻塞时重新加锁后返回；被通知、**绝对超时到期**（[[thread.req]]）或虚假地解除阻塞；¶18.4 **若函数以异常退出，在退出前调用 `lock.lock()`**。
- ¶20 *Returns*：若 `abs_time` 指定的绝对超时已到期，返回 `cv_status::timeout`，否则 `cv_status::no_timeout`。
- ¶21 *Throws*：超时相关异常。

¶18.4 与 ¶11 配合：时钟抛出超时相关异常时，`wait_until` 先把锁重新拿回来再抛，保证调用者的 `unique_lock` 状态一致。

`wait_for(lock, rel_time)`（¶23–¶28）：¶24 等价于 `return wait_until(lock, rel-to-abs(rel_time));`。

`wait_until(lock, abs_time, pred)`（¶29–¶34）：¶30 等价于

```cpp
while (!pred())
  if (wait_until(lock, abs_time) == cv_status::timeout)
    return pred();
return true;
```

¶32 注 6：**返回值表示谓词最终是否为 `true`，与是否超时无关**。即超时的那一刻条件恰好成立，返回 `true`。

`wait_for(lock, rel_time, pred)`（¶35–¶41）：¶36 等价于 `return wait_until(lock, rel-to-abs(rel_time), std::move(pred));`；¶37 注 8：若 `pred()` 一开始就为 `true`，即使超时已过也不阻塞。

!!! impl "libc++ 在 macOS 上的超时等待"
    `condition_variable` 只是一个 48 字节的 `pthread_cond_t`。macOS 没有 `pthread_cond_clockwait`，所以 libc++ 的 `wait_for` 把时长换算成 `system_clock` 的绝对时间交给 `pthread_cond_timedwait`，返回后再用 `steady_clock` 判断是否超时（详见 [[thread.req]]）。`wait_until` 对非 `system_clock`（包括 `steady_clock`）的时钟，转成相对时长再走 `wait_for`。

## condition_variable_any（[thread.condition.condvarany]）

### 总述（[thread.condition.condvarany.general]）

¶1 本条款中名为 `Lock` 的模板形参，其实参须满足 *Cpp17BasicLockable*。注 1：所有标准互斥量都满足。若用于 `condition_variable_any` 的不是标准互斥量类型或标准互斥量的 `unique_lock` 包装，则**假定与条件变量关联的谓词所需的同步已经就位**——标准不为用户自定义的锁提供同步保证，同步完全取决于该锁的实现。

¶2–¶3 构造函数：可能抛 `bad_alloc` 或 `system_error`。（与 `condition_variable` 不同，它可能需要分配内存，见下文实现。）

¶4 析构函数：与 `condition_variable` 相同的放宽前置条件。¶5–¶6 `notify_one`、`notify_all`。

注意 `condition_variable_any` **没有**"所有并发等待者用同一个锁"的前置条件——这是它比 `condition_variable` 更通用的另一面。

### 不可中断的等待（[thread.condvarany.wait]）

与 `condition_variable` 的四个 `wait` 系列一一对应（¶1–¶19），模板形参 `Lock` 代替 `unique_lock<mutex>`，后置条件改为"`lock` 被调用线程锁定"。

用途：在 `shared_lock<shared_mutex>` 上等待（读者等待条件时只持有共享锁）；在用户自定义的锁（例如 [[thread.req]] 中的自旋锁）上等待；在 `unique_lock<timed_mutex>` 等非 `std::mutex` 的锁上等待。

### 可中断的等待（[thread.condvarany.intwait]） {{c++20}}

¶1 下列 `wait` 函数在传入的 `stop_token` 上有停止请求时会被通知。此时函数立即返回，若谓词为 `false` 则返回 `false`。

`template<class Lock, class Predicate> bool wait(Lock& lock, stop_token stoken, Predicate pred);`

¶2 *Effects*：在本次调用期间注册 `*this`，使其在 `stoken` 上有停止请求时得到通知，然后等价于

```cpp
while (!stoken.stop_requested()) {
  if (pred())
    return true;
  wait(lock);
}
return pred();
```

¶3 注 1：返回值表示谓词最终是否为 `true`，与是否有停止请求无关。¶4–¶6 后置条件、异常、重新加锁失败时 `terminate`。

¶7–¶13 带超时的版本 `wait_until(lock, stoken, abs_time, pred)`、`wait_for(lock, stoken, rel_time, pred)`：同时受谓词、停止请求和超时三者约束；¶8 注 3：若 `pred()` 初始为 `true`、`stoken.stop_requested()` 已为 `true` 或超时已过，则不阻塞。

可中断等待只有**带谓词**的版本：没有谓词，函数返回时调用者无法区分"被通知""被停止""虚假唤醒"。[[thread.stoptoken]] ¶12 注 3 中"停止请求包括通知所有临时注册的 `condition_variable_any`"指的就是这里的"注册"。用法见 [[thread.threads]] 中 `jthread` 的例子。

!!! impl "libc++ 的 condition_variable_any"
    libc++ 的 `condition_variable_any`（64 字节）内部是一个 `condition_variable` 加一个 `shared_ptr<mutex>`——构造函数里的 `make_shared` 就是 ¶2 中 `bad_alloc` 的来源。`wait(lock)` 的步骤是：复制一份 `shared_ptr`（使条件变量可以在等待者仍在第 3 部分时被销毁，满足 ¶4 的放宽规则）、锁住内部 `mutex`、解锁用户的 `lock`、在内部 `mutex` 上 `__cv_.wait`，返回时先解锁内部 `mutex`、再重新锁用户的 `lock`。

    可中断等待注册一个 `stop_callback`，回调里调用 `notify_all()`；并且在检查 `stop_requested()` 之前先锁住内部互斥量，而 `notify_all` 也会获取这把内部锁——这样停止请求不会落在"检查"与"进入等待"之间而丢失。

## 陷阱

!!! pitfall "“先解锁再通知”与条件变量的生命周期"
    "在锁外通知"通常更高效（被唤醒的线程不必立即阻塞在互斥量上），本页的队列例子也是这样做的。但当**条件变量本身的生命周期由等待者控制**时，它是错的：

    ```cpp
    struct Completion { std::mutex m; std::condition_variable cv; bool done = false; };

    void worker(Completion* c) {
      { std::lock_guard lk(c->m); c->done = true; }
      c->cv.notify_one();        // 危险：此时 *c 可能已被销毁
    }

    void wait_for_worker() {
      Completion c;              // 在等待者的栈上
      std::thread t(worker, &c);
      t.detach();
      std::unique_lock lk(c.m);
      c.cv.wait(lk, [&] { return c.done; });   // 可能因虚假唤醒在 notify 之前就看到 done == true
    }                            // 返回，销毁 c，而 worker 还要调用 c->cv.notify_one()
    ```

    等待者可能被**虚假唤醒**，看到 `done == true`（worker 已经解锁），返回并销毁 `c`；随后 worker 对已销毁的条件变量调用 `notify_one`——UB。在锁内通知就没有这个问题：等待者要返回，必须先拿到锁，而那时 worker 已经完成通知。

!!! pitfall "用原子变量当条件却不加锁修改"
    `std::atomic<bool> ready;` 然后 `ready = true; cv.notify_one();`（不持有 `m`）——会丢失唤醒（见 ¶3–¶4 的分析）。条件变量的谓词所涉及的状态，修改时必须持有等待者所用的那把互斥量。只想等一个原子变量变化，应当用 `atomic::wait`（[[atomics.wait]]），它不需要互斥量。

!!! pitfall "notify_one 不等于“唤醒恰好一个”"
    ¶5 只说解除"其中一个"的阻塞，但由于虚假唤醒，被唤醒的线程可能多于一个。逻辑上应该假设任何等待者随时可能醒来。

## 思考题

!!! question "1. `cv.wait_for(lk, 100ms, pred)` 返回 `false`，能断定发生了超时吗？"

<details markdown="1">
<summary>答案</summary>

能。按 ¶30 的等价代码，只有 `wait_until` 返回 `cv_status::timeout` 且此时 `pred()` 为 `false` 时才返回 `false`；其他路径（`pred()` 为 `true`）都返回 `true`。反过来，返回 `true` **不能**断定没有超时（注 6）。
</details>

!!! question "2. 为什么 `condition_variable` 的 `wait` 只接受 `unique_lock<mutex>`，而不是任何锁？"

<details markdown="1">
<summary>答案</summary>

¶1："这使实现可以更高效"。限定为 `std::mutex` 后，实现可以直接把底层的 `pthread_mutex_t` 交给 `pthread_cond_wait`，由操作系统完成"原子地解锁并等待"。`condition_variable_any` 面对任意锁类型，只能像 libc++ 那样再引入一把内部互斥量来实现这一原子性，开销更大。
</details>

## 小结

| 规则 | 出处 |
|---|---|
| `wait` 分三个原子部分；所有操作处于与 happens before 一致的单一全序 | ¶3–¶4 |
| 修改条件必须持有互斥量，否则会丢失唤醒 | 由 ¶3–¶4 推出 |
| `wait` 可以虚假返回；带谓词的重载等价于 `while (!pred()) wait(lock);` | condvar ¶8.3、¶13 |
| `condition_variable` 的所有并发等待者必须使用同一个互斥量 | condvar ¶7.2 |
| 析构只要求"没有线程阻塞在其上" | condvar ¶4 |
| 重新加锁失败 → `terminate` | condvar ¶11 等 |
| `wait_for` 以 `steady_clock` 计时（*rel-to-abs*） | general ¶6 |
| 带谓词的超时等待返回谓词的最终值 | condvar ¶32、¶39 |
| `condition_variable_any` 可在停止请求时被唤醒（仅带谓词版本） | [thread.condvarany.intwait] |
