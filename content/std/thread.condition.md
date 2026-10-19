---
title: 条件变量
summary: condition_variable 与 condition_variable_any 怎样让线程等到某个条件成立：wait 的三个原子部分为什么能避免丢失唤醒，虚假唤醒与谓词循环，同一条件变量的等待者必须用同一个互斥量，超时等待的返回值，以及 C++20 可被停止请求打断的等待。
status: done
covers: *
papers: P0660R10
related: thread.mutex.requirements, thread.lock, thread.req, thread.stoptoken, atomics.wait, thread.sema, intro.races
tags: 标准库, 并发, 条件变量, 虚假唤醒
updated: 2026-10-19
---

!!! tldr
    - `wait` 原子地释放互斥量并进入等待，所以只要修改条件时持有同一个互斥量，通知就不会丢失。条件即使是原子变量，修改时也要持锁。
    - `wait` 可以在没有任何通知时返回（虚假唤醒），所以必须在循环里检查条件。带谓词的 `wait(lock, pred)` 就是这个循环。
    - 同时在一个 `condition_variable` 上等待的线程必须使用同一个互斥量，否则是 UB；`condition_variable_any` 没有这条限制，可以配合任何锁类型。
    - 带谓词的超时等待返回谓词的最终值：返回 `false` 说明超时了，返回 `true` 不能说明没超时。
    - `condition_variable_any` 的带谓词等待可以接受一个 `stop_token`，有停止请求时立即醒来。

## 等一个条件成立

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
      q.push(i);                     // 修改条件时持有锁
    }
    cv.notify_one();                 // 通知可以在锁外
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
    cv.wait(lk, [] { return !q.empty() || closed; });
    if (q.empty()) break;            // 已关闭且队列为空
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

没有条件变量，消费者只能反复加锁、检查队列、解锁，白白占用 CPU。条件变量让它在条件不成立时睡眠，由修改条件的线程负责叫醒它。

[thread.condition.general] ¶1 标准提供两种条件变量。`condition_variable` 只能配合 `unique_lock<mutex>` 使用，这让实现可以更高效；`condition_variable_any` 可以配合用户提供的任何锁类型。¶2 所有的 `wait`、`notify` 成员函数都可以被并发调用。

## 为什么不会丢失唤醒（¶3–¶4）

¶3 `notify_one` 和 `notify_all` 的执行是原子的。`wait`、`wait_for`、`wait_until` 的执行分成三个原子部分：

1. 释放互斥量并进入等待状态；
2. 解除等待；
3. 重新获取锁。

¶4 实现的行为如同：所有 `notify` 的执行和每次等待的每个部分，都处在同一个未指定的全序中，这个全序与 [[g:happens-before|happens before]] 一致。

关键在第 1 部分：释放互斥量与进入等待是同一个原子步骤，中间没有缝隙。于是：

- 等待者持有锁时检查条件，发现不成立，调用 `wait`；
- 通知者要修改条件，必须先拿到同一把锁，这只能发生在等待者执行完第 1 部分之后，此时等待者已经在等待；
- 通知者随后的 `notify` 在全序中排在第 1 部分之后，一定能唤醒它。

如果修改条件时不持锁，修改可能恰好落在等待者检查条件与调用 `wait` 之间：

```text
等待者（持有锁）                    通知者（不持有锁）
--------------------------          ------------------------
检查 ready，结果为 false
                                     ready = true
                                     cv.notify_one()   // 此时没有线程在等待
cv.wait(lk)  // 释放锁并等待，再也没人叫醒它
```

所以修改条件必须在持有互斥量时进行，即使 `ready` 是 `std::atomic<bool>` 也一样。`notify` 本身不要求持锁。

¶5 条件变量的构造和析构不需要同步。

## condition_variable [thread.condition.condvar]

### wait 与虚假唤醒（¶7–¶16）

```cpp
void wait(unique_lock<mutex>& lock);
```

¶7 前置条件：`lock` 持有锁，且互斥量被调用线程锁定。另外，要么 ¶7.1 没有其他线程在这个条件变量上等待，要么 ¶7.2 所有并发等待的线程传入的锁，`lock.mutex()` 都相同。

¶8 效果：

- ¶8.1 原子地调用 `lock.unlock()` 并阻塞；
- ¶8.2 解除阻塞后调用 `lock.lock()`（可能在锁上阻塞），然后返回；
- ¶8.3 解除阻塞的原因可以是 `notify_one()`、`notify_all()`，也可以是虚假的。

¶8.3 明文允许的就是**虚假唤醒**（[[g:spurious-wakeup|spurious wakeup]]）：`wait` 可以在没有任何通知的情况下返回。这给了实现自由，有些平台的底层原语会因为信号等原因提前返回。另外，从 `wait` 返回时条件也可能已经被别的线程改回去了。所以无谓词的 `wait` 必须写在检查条件的循环里。

¶13 带谓词的版本就是这个循环：

```cpp
template<class Predicate> void wait(unique_lock<mutex>& lock, Predicate pred);
// 等价于
while (!pred())
  wait(lock);
```

¶7.2 的同一个互斥量要求常被忽视。两个线程分别用 `m1`、`m2` 在同一个 `condition_variable` 上等待是 UB。POSIX 的 `pthread_cond_wait` 也有同样的要求。

### wait 失败只能 terminate（¶9–¶11）

¶9 `wait` 的后置条件是调用线程重新持有锁。¶10 它不抛异常。¶11 如果做不到后置条件，就调用 `terminate()`；注 2 说明，重新加锁抛出异常时会出现这种情况。

这是唯一合理的选择。函数不能正常返回，因为调用者会以为自己持有锁；也不能抛出异常，因为栈展开时 `unique_lock` 的析构函数会去解锁一个没有锁上的互斥量。

### 超时等待（¶17–¶41）

¶17–¶22 `wait_until(lock, abs_time)` 与 `wait` 相同，只是绝对超时到期也会解除阻塞（[[thread.req]]）。¶20 超时到期时返回 `cv_status::timeout`，否则返回 `cv_status::no_timeout`。¶18.4 如果函数以异常退出（时钟可能抛出超时相关的异常），退出前会先调用 `lock.lock()`，保证调用者的 `unique_lock` 状态一致。

[thread.condition.general] ¶6 定义了一个仅用于说明的函数 *rel-to-abs*：

```cpp
template<class Dur>
  chrono::steady_clock::time_point rel-to-abs(const Dur& rel_time) {
    return chrono::steady_clock::now() + chrono::ceil<chrono::steady_clock::duration>(rel_time);
  }
```

¶23–¶28 每个 `wait_for(lock, rel_time)` 都定义为 `wait_until(lock, rel-to-abs(rel_time))`。基准是 `steady_clock`，所以修改系统时间不影响相对超时。`ceil` 向上取整，在粒度很粗的时钟上 `wait_for(1ns)` 也不会变成不等待。

¶29–¶34 带谓词的 `wait_until` 等价于：

```cpp
while (!pred())
  if (wait_until(lock, abs_time) == cv_status::timeout)
    return pred();
return true;
```

¶32 注 6 指出，返回值表示谓词最终是否为真，与是否超时无关：超时那一刻条件恰好成立，返回的就是 `true`。¶35–¶41 带谓词的 `wait_for` 同理；¶37 注 8 补充，如果 `pred()` 一开始就为真，即使超时时间已过也不阻塞。

!!! impl "libc++ 怎样实现相对超时"
    libc++ 的 `condition_variable` 包装了一个 `pthread_cond_t`。平台提供 `pthread_cond_clockwait` 时（如 glibc），`steady_clock` 的等待直接用 `CLOCK_MONOTONIC`。macOS 没有这个函数，libc++ 只能把时长换算成 `system_clock` 的绝对时间交给 `pthread_cond_timedwait`，返回后再用 `steady_clock` 判断是否超时（详见 [[thread.req]]）。

### 通知与析构（¶4–¶6）

¶5 `notify_one()` 解除一个阻塞线程（如果有的话），¶6 `notify_all()` 解除全部。两者都是 `noexcept`，都不要求调用者持锁。

¶4 析构函数的前置条件只是：没有线程阻塞在这个条件变量上。注 1 解释说，这比通常的规则宽松。按通常的规则，所有 `wait` 调用都要 happens before 析构；这里只要求解除等待的那次通知 happens before 析构。被唤醒的线程可能还在第 3 部分里等着重新获取锁，但它们已经不再阻塞在条件变量上，于是通知者可以在 `notify_all()` 之后立即销毁条件变量。

### notify_all_at_thread_exit [thread.condition.nonmember]

```cpp
void notify_all_at_thread_exit(condition_variable& cond, unique_lock<mutex> lk);
```

¶2 这个函数把 `lk` 持有的锁转移到内部存储，并安排在当前线程退出时执行 `cond.notify_all(); lk.unlock();`。¶3 这次通知和解锁排在当前线程所有 `thread_local` 对象的析构之后。

用途是等待一个已 detach 的线程连同它的 `thread_local` 对象的析构一起完成。在线程函数最后设置标志再通知做不到这一点，因为 `thread_local` 对象在线程函数返回之后才析构。

¶1 它的前置条件与 `wait` 相同：`lk` 已锁定，所有并发等待者使用同一个互斥量。¶4 注 1 提醒，锁会一直持有到线程退出，可能因为加锁顺序导致死锁。¶5 注 2 提醒，等待者被虚假唤醒时不能误以为线程已经结束，通常的做法是在持有 `lk` 时满足等待的条件，并且在调用本函数前不释放这把锁。

## condition_variable_any [thread.condition.condvarany]

### 配合任意锁 [thread.condition.condvarany.general]

¶1 `condition_variable_any` 的模板形参 `Lock` 只需满足 *Cpp17BasicLockable*。注 1 说明，如果用的不是标准互斥量或标准互斥量的 `unique_lock`，谓词所需的同步就要由这把锁自己提供。

它的四个不可中断的 `wait` 系列函数（[thread.condvarany.wait]）与 `condition_variable` 一一对应，只是把 `unique_lock<mutex>` 换成了 `Lock`。它也没有所有并发等待者必须用同一个互斥量的前置条件。常见用途：

- 在 `shared_lock<shared_mutex>` 上等待，读者等待期间只持有共享锁；
- 在 `unique_lock<timed_mutex>` 或用户自定义的锁上等待。

¶2 构造函数可能抛 `bad_alloc`，因为实现可能需要分配内存。¶4 析构函数采用与 `condition_variable` 相同的宽松前置条件。

!!! impl "libc++ 的 condition_variable_any"
    libc++ 的 `condition_variable_any` 内部是一个 `condition_variable` 加一个 `shared_ptr<mutex>`，构造函数里的 `make_shared` 就是 `bad_alloc` 的来源。`wait(lock)` 先复制这个 `shared_ptr`，锁住内部互斥量，再解锁用户的锁，然后在内部互斥量上等待；返回时先解锁内部互斥量，再重新锁用户的锁。

    复制 `shared_ptr` 是为了满足宽松的析构规则：条件变量被销毁后，仍在第 3 部分的等待者手里的内部互斥量依然有效。`notify` 也会短暂获取内部互斥量，这使用户锁的释放和进入等待对通知者来说是原子的。

### 可中断的等待 [thread.condvarany.intwait] {{c++20}}

```cpp run title="cv-stop.cpp" ok
#include <condition_variable>
#include <cstdio>
#include <mutex>
#include <queue>
#include <thread>

std::mutex m;
std::condition_variable_any cv;
std::queue<int> q;

int main() {
  std::jthread worker([](std::stop_token st) {
    std::unique_lock lk(m);
    while (cv.wait(lk, st, [] { return !q.empty(); })) {   // 已请求停止且队列为空时返回 false
      std::printf("got %d\n", q.front());
      q.pop();
    }
    std::puts("stopped");
  });
  {
    std::lock_guard lk(m);
    q.push(1);
  }
  cv.notify_one();
}   // ~jthread 先 request_stop() 再 join()，worker 被唤醒并退出
```

¶1 这些 `wait` 函数在传入的 `stop_token` 上出现停止请求时会被通知，然后立即返回；如果此时谓词为假，就返回 `false`。

¶2 `wait(lock, stoken, pred)` 在调用期间登记 `*this`，使它在 `stoken` 收到停止请求时得到通知，然后等价于：

```cpp
while (!stoken.stop_requested()) {
  if (pred())
    return true;
  wait(lock);
}
return pred();
```

¶3 注 1 指出，返回值表示谓词最终是否为真，与有没有停止请求无关。¶7–¶13 带超时的版本同时受谓词、停止请求和超时约束；¶8 注 3 指出，如果谓词一开始为真、已经有停止请求或超时已过，就不阻塞。

可中断的等待只有带谓词的版本。没有谓词的话，函数返回时调用者分不清是被通知、被停止还是虚假唤醒。`stop_token` 的工作方式见 [[thread.stoptoken]]，`jthread` 的用法见 [[thread.threads]]。

## 常见误解

!!! pitfall "先解锁再通知总是更好"
    在锁外通知通常更高效，被唤醒的线程不必立即在互斥量上阻塞，开头的队列例子就是这样写的。但如果条件变量的生命周期由等待者控制，这样写就是错的：

    ```cpp
    struct Completion { std::mutex m; std::condition_variable cv; bool done = false; };

    void worker(Completion* c) {
      { std::lock_guard lk(c->m); c->done = true; }
      c->cv.notify_one();        // 此时 *c 可能已被销毁
    }

    void wait_for_worker() {
      Completion c;              // 在等待者的栈上
      std::thread(worker, &c).detach();
      std::unique_lock lk(c.m);
      c.cv.wait(lk, [&] { return c.done; });
    }                            // 返回时销毁 c
    ```

    worker 解锁之后、通知之前，等待者可能拿到锁，看到 `done` 为真（也许它根本还没开始等待，也许是被虚假唤醒），于是返回并销毁 `c`。随后 worker 对已销毁的条件变量调用 `notify_one`，这是 UB。改成在锁内通知就没有问题：等待者要返回必须先拿到锁，而那时通知已经完成。

!!! pitfall "条件是原子变量，修改时就不用加锁"
    `ready = true; cv.notify_one();` 不持有 `m` 时会丢失唤醒，原因见上文对第 3、4 段的分析。谓词涉及的状态，修改时必须持有等待者所用的互斥量。如果只想等一个原子变量改变，应当用 `atomic::wait`（[[atomics.wait]]），它不需要互斥量。

!!! pitfall "notify_one 恰好唤醒一个线程"
    第 5 段只保证解除其中一个线程的阻塞，但其他线程可能同时被虚假唤醒。程序逻辑要假定任何等待者都可能随时醒来。

## 思考题

!!! question "思考题 1"
    `cv.wait_for(lk, 100ms, pred)` 返回 `false`，能断定发生了超时吗？

<details markdown="1">
<summary>答案</summary>

能。按第 30 段的等价代码，只有内部的 `wait_until` 返回 `cv_status::timeout` 而此时 `pred()` 为假，才会返回 `false`，其他路径都返回 `true`。反过来，返回 `true` 不能说明没有超时（¶32 注 6）。
</details>

!!! question "思考题 2"
    为什么 `condition_variable` 只接受 `unique_lock<mutex>`？

<details markdown="1">
<summary>答案</summary>

[thread.condition.general] ¶1 说，这让实现可以更高效。限定为 `std::mutex` 后，实现可以把底层的 `pthread_mutex_t` 直接交给 `pthread_cond_wait`，由操作系统完成原子地解锁并等待。`condition_variable_any` 面对任意锁类型，只能像 libc++ 那样再引入一把内部互斥量来实现这种原子性，开销更大。
</details>

## 小结

| 规则 | 出处 |
|---|---|
| `wait` 分三个原子部分，所有操作处在与 happens before 一致的全序中 | general ¶3–¶4 |
| 修改条件必须持有互斥量，否则会丢失唤醒 | 由 general ¶3–¶4 推出 |
| `wait` 可以虚假返回；带谓词的版本等价于 `while (!pred()) wait(lock);` | condvar ¶8.3、¶13 |
| 同一 `condition_variable` 的并发等待者必须用同一个互斥量 | condvar ¶7.2 |
| 重新加锁失败时调用 `terminate` | condvar ¶11 等 |
| `wait_for` 以 `steady_clock` 计时 | general ¶6 |
| 带谓词的超时等待返回谓词的最终值 | condvar ¶32、¶39 |
| 析构只要求没有线程阻塞在条件变量上 | condvar ¶4 |
| `condition_variable_any` 可被停止请求唤醒（只有带谓词的版本） | [thread.condvarany.intwait] |
