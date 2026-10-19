---
title: 并发库的通用要求
summary: 第 32 章各节共用的约定：Predicate 与 Clock 形参的要求、system_error 怎样报告错误、native_handle、_for 与 _until 两种超时的语义，以及 Cpp17BasicLockable 等可锁类型要求。
status: done
covers: *
related: thread, thread.mutex.requirements, thread.lock, thread.condition, time.clock.req, syserr
tags: 标准库, 并发, 超时, 锁
updated: 2026-10-19
---

!!! tldr
    - `wait_for(5s)` 是相对超时，应当按稳定时钟计时；`wait_until(tp)` 是绝对超时，跟随 `tp` 自己的时钟。系统时间被调整时，两者的行为不同。
    - 超时函数只保证不会提前返回，不保证准时返回。
    - 需要一个总截止时间时，先算出 `steady_clock` 的时间点再用 `wait_until`，不要在循环里反复 `wait_for`。
    - 可锁类型要求（*Cpp17BasicLockable* 等）只规定接口和阻塞语义，不规定内存同步。同步要靠锁类型自己的实现。
    - `system_error` 的 `code()` 与函数列出的错误条件比较相等，不要拿 `code().value()` 和整数比较。

第 32 章（并发支持库）的各节反复引用这里的约定，例如"按 [thread.req.timing] 处理超时""Mutex 须满足 *Cpp17BasicLockable*"。

## 超时：_for 与 _until [thread.req.timing]

### 两种超时

```cpp run title="deadline.cpp" ok
#include <chrono>
#include <condition_variable>
#include <mutex>

std::mutex m;
std::condition_variable cv;
bool ready = false;

bool wait_with_deadline() {
  using namespace std::chrono_literals;
  // 截止时间只算一次，之后无论被唤醒多少次都不会延后
  auto deadline = std::chrono::steady_clock::now() + 100ms;
  std::unique_lock lk(m);
  return cv.wait_until(lk, deadline, [] { return ready; });   // 超时返回 false
}

int main() { return wait_with_deadline() ? 1 : 0; }
```

本章有很多成对的函数：`sleep_for` 与 `sleep_until`、`try_lock_for` 与 `try_lock_until`、`wait_for` 与 `wait_until`。¶1 超时用 `duration` 或 `time_point` 指定（[[time]]）。

¶3 名字以 `_for` 结尾的函数接受一个时长，产生**相对超时**（relative timeout）。实现应当用**稳定时钟**（steady clock，不会被调整、只会匀速向前的时钟）计时。

¶4 名字以 `_until` 结尾的函数接受一个时间点，产生**绝对超时**（absolute timeout）。实现应当用这个时间点所属的时钟计时。

所以 `wait_for(1h)` 的意思是等一小时的物理时间，`wait_until(system_clock::now() + 1h)` 的意思是等到墙上时钟（`system_clock`，可能被 NTP 或管理员调整）显示那个时刻。每天 9 点执行的定时任务用 `_until` 加 `system_clock`；5 秒内没有响应就放弃，用 `_for`，或者 `_until` 加 `steady_clock`。

### 只保证不提前

¶2 从超时中返回总会有延迟。标准把延迟分成两部分：中断响应、函数返回、调度带来的**实现质量延迟** D<sub>i</sub>，以及处理器和内存争用带来的**管理质量延迟** D<sub>m</sub>。两者每次可以不同，越短越好。

¶3 给定时长 D<sub>t</sub>，相对超时的真实时长是 D<sub>t</sub>+D<sub>i</sub>+D<sub>m</sub>。¶4 给定时间点 C<sub>t</sub>，时钟没有被调整时，绝对超时应在 C<sub>t</sub>+D<sub>i</sub>+D<sub>m</sub> 返回。这些式子说明标准从不承诺准时，只承诺不会在超时之前返回。

### 等待期间时钟被调整（¶4）

¶4 如果绝对超时等待期间，时钟被调整到了 C<sub>a</sub>：

- ¶4.1 C<sub>a</sub> > C<sub>t</sub>，时钟被拨过了截止时间：超时已经满足，应尽快返回。按稳定时钟衡量，总等待时间变短了。
- ¶4.2 C<sub>a</sub> ≤ C<sub>t</sub>：在 `Clock::now()` 返回不小于 C<sub>t</sub> 的值之前不应超时。注 1 指出，时钟往回拨会让等待（按稳定时钟衡量）变长。

这一段最后给实现留了余地：实现可以在上面规定的时刻，与把 C<sub>t</sub> 减去调用时刻的差当作稳定时钟相对超时时会返回的时刻之间的任何一点返回。*推荐做法*是时钟往前拨时缩短等待。

¶5 注 2：如果时钟与稳定时钟不同步，例如 CPU 时间时钟，这类超时可能毫无用处。

!!! pitfall "在循环里反复 `wait_for` 会让截止时间漂移"
    `while (!ready) cv.wait_for(lk, 100ms);` 每次被唤醒（包括虚假唤醒）都会重新计 100ms，总等待时间没有上限。需要总超时时，像上面的例子那样先算出一个 `steady_clock` 时间点，再用 `wait_until`。

标准自己定义条件变量时也遵循了 ¶3：[[thread.condition.general]] 用仅说明用的函数 *rel-to-abs* 把相对时长换算成 `steady_clock` 的时间点，`wait_for` 等价于对这个时间点 `wait_until`。

!!! impl "libc++ 在 macOS 上的 `condition_variable::wait_for`"
    libc++ 只在 glibc ≥ 2.30 或 Android API ≥ 30 上使用 `pthread_cond_clockwait(CLOCK_MONOTONIC)`。macOS 没有这个函数，libc++ 把时长加到 `system_clock::now()` 上交给 `pthread_cond_timedwait`，返回后再用 `steady_clock` 测量实际经过的时间，决定返回 `timeout` 还是 `no_timeout`（见 `<__condition_variable/condition_variable.h>`）。底层等待仍以墙上时钟为基准，¶3 的建议在这里只做到了一部分。

### 分辨率与超时相关异常（¶6–¶8）

¶6 实现能提供的最细计时分辨率叫做**原生分辨率**（[[g:native-resolution]]，native resolution），取决于操作系统和硬件。

¶7 这些函数使用的、由实现提供的时钟满足 *Cpp17TrivialClock*（[[time.clock.req]]），也就是 `now()` 和时间类型上的操作都不抛异常。

¶8 带超时参数的函数，如果执行期间时钟、时间点或时长抛出了异常，就把它抛给调用者。这样的异常叫做**超时相关异常**（[[g:timeout-related-exception]]，timeout-related exceptions）。注 3 说明标准库自带的时间类型都不抛异常，只有用户自定义的时钟或 `rep`（例如带溢出检查的整数类型）才可能抛。本章大量出现的 "*Throws*: Timeout-related exceptions" 因此可以读作：函数自己不抛异常，只转发用户提供的时间类型抛出的异常。

## 模板形参名 [thread.req.paramname]

¶1 本章用模板形参的名字表达类型要求：

- 名为 `Predicate` 的形参是函数对象类型。设 `pred` 是它的左值，`pred()` 必须良构，结果类型必须满足 *boolean-testable*（[[concept.booleantestable]]）。结果转为 `bool` 后表示等待的条件是否满足，例如 `condition_variable::wait(lock, pred)` 中的 `pred`。
- 名为 `Clock` 的形参，实参类型 `C` 必须满足 *Cpp17Clock*（[[time.clock.req]]）；如果 `is_clock_v<C>` 为 `false`，程序非良构。

满足 *Cpp17Clock* 本身是一条语义要求，编译器无法完整检查。`is_clock_v` 检查的是其中能静态检查的部分：成员 `rep`、`period`、`duration`、`time_point`、`is_steady` 和 `now()` 是否存在。标准把这部分升级成了必须诊断的错误。

```cpp run title="not-a-clock.cpp" error
#include <chrono>
#include <thread>
struct almost_clock {             // 缺少 is_steady，is_clock_v 为 false
  using rep = long long;
  using period = std::nano;
  using duration = std::chrono::nanoseconds;
  using time_point = std::chrono::time_point<almost_clock>;
  static time_point now() { return time_point{}; }
};
static_assert(!std::chrono::is_clock_v<almost_clock>);
int main() {
  std::this_thread::sleep_until(almost_clock::now());   // error: almost_clock 不是时钟
}
```

!!! impl "libc++ 没有诊断"
    按 ¶1 这个程序非良构，必须诊断。本机 Clang 23 + libc++ 却能编译通过，因为 `sleep_until` 的实现只用到了 `Clock::now()` 和 `time_point` 的算术，没有检查 `is_clock_v`。这是 libc++ 的符合性缺陷。

## 错误报告 [thread.req.exception]

```cpp run title="join-empty.cpp" ok
#include <cstdio>
#include <system_error>
#include <thread>

int main() {
  std::thread t;       // 不表示任何线程
  try {
    t.join();          // 错误条件：invalid_argument
  } catch (const std::system_error& e) {
    std::printf("%d\n", e.code() == std::errc::invalid_argument);   // 1
  }
}
```

¶1 本章有些函数规定会抛出 `system_error`。它们在两种情况下抛：检测到了函数 *Error conditions* 一项里列出的错误条件；或者底层操作系统 API 出错，使函数无法满足规格。内存分配失败另按 [[res.on.exception.handling]] 报告，通常是 `bad_alloc`。

例 1 描述了映射过程：POSIX 调用返回 `EPERM`（调用者没有权限），实现把它映射为错误条件 `operation_not_permitted`，然后抛出 `system_error`。

¶2 这样抛出的异常，`code()` 与函数列出的某个错误条件比较相等。这是 `error_code` 与 `error_condition` 之间的比较（[[syserr]]），同一个条件在不同平台上可以对应不同的原生错误码，所以要像上例那样与 `std::errc` 比较。

## native_handle [thread.req.native]

¶1 `thread`、`mutex`、`condition_variable` 等类可以有成员 `native_handle_type` 和 `native_handle()`，它们是否存在、语义如何都由实现定义。注 1 解释了标准为什么还要规定这两个名字：方便在编译期可移植地探测它们是否存在，例如 `requires { m.native_handle(); }`，尽管使用它们本身不可移植。

libc++ 在 macOS 上，`std::thread::native_handle()` 返回 `pthread_t`，`std::mutex::native_handle()` 返回 `pthread_mutex_t*`。典型用途是设置线程优先级、CPU 亲和性这类标准接口覆盖不到的属性。

## 可锁类型要求 [thread.req.lockable]

### 执行代理（¶1–¶2）

¶1 **执行代理**（[[g:execution-agent]]，execution agent）指线程这类可以与其他执行代理并行工作的实体。注 1 补充，实现或用户还可以引入进程、线程池任务等其他种类的代理。当前代理由上下文决定，例如包含这次调用的线程。

可锁要求用执行代理而不是线程来表述，是为了不把锁绑定在操作系统线程上。¶2 注 2 举例：普通的自旋锁不记录持有者是谁，对任何执行代理模型都适用，这类锁叫做代理无关的（agent oblivious）。

### 要求只管接口，不管同步（¶3–¶4）

¶3 `unique_lock`、`shared_lock`、`scoped_lock`、`lock_guard`、`std::lock`、`std::try_lock`、`condition_variable_any` 都可以操作用户提供的可锁对象。下面五组要求列出了这些组件获取、释放锁时需要的接口。

注 3 指出，锁所有权的性质以及它带来的任何同步，都不属于这些要求。所以 `std::lock_guard<MyLock>` 本身不保证任何内存可见性，是否同步完全取决于 `MyLock` 的实现。

¶4 对象 `m` 上的锁按获取方式分成两种：通过 `lock`、`try_lock`、`try_lock_for`、`try_lock_until` 获得的是**非共享锁**（non-shared lock）；通过 `lock_shared` 等带 `_shared` 的函数获得的是**共享锁**（shared lock）。注 4 强调只看获取方式。即使某个类型的 `lock()` 允许多个代理同时持有（例如 [[saferecl]] 的 `rcu_domain`），它获得的仍然叫非共享锁。

### 五组要求

| 要求 | 需要的表达式 | 要点 |
|---|---|---|
| *Cpp17BasicLockable* [thread.req.lockable.basic] | `m.lock()`、`m.unlock()` | `lock` 阻塞直到获得锁；`unlock` 要求当前代理持有非共享锁，不抛异常 |
| *Cpp17Lockable* [thread.req.lockable.req] | 再加 `m.try_lock()` | 不阻塞地尝试，返回类型是 `bool` |
| *Cpp17TimedLockable* [thread.req.lockable.timed] | 再加 `try_lock_for`、`try_lock_until` | 在超时之前尝试；没获得锁就不会在超时前返回 |
| *Cpp17SharedLockable* [thread.req.lockable.shared] | `lock_shared`、`try_lock_shared`、`unlock_shared` | 共享版本，`try_lock_shared()` 的类型是 `bool` |
| *Cpp17SharedTimedLockable* [thread.req.lockable.shared.timed] | 再加 `try_lock_shared_for`、`try_lock_shared_until` | 带超时的共享版本，返回 `bool` |

几处细节：

- *Cpp17BasicLockable* ¶2 规定 `lock()` 抛出异常时锁没有被获得。所以 `lock_guard` 的构造函数里 `lock()` 抛异常，析构函数不会运行，也不需要运行。
- *Cpp17BasicLockable* ¶3 要求调用 `unlock` 的代理就是持有锁的代理。在线程 A 中 `lock()`、在线程 B 中 `unlock()` 一个 `std::mutex`，违反前置条件，是 UB。
- *Cpp17TimedLockable* ¶2 只说没获得锁就不会在超时之内返回，没有说锁空闲时必须获得。所以即使锁一直空闲，`try_lock_for` 返回 `false` 也符合这组要求。具体互斥量类型的额外保证在 [[thread.mutex.requirements]] 中。

### 自己写一个满足 Cpp17Lockable 的类型

```cpp run title="spinlock.cpp" ok
#include <atomic>
#include <cassert>
#include <mutex>
#include <thread>

class spinlock {                       // 满足 Cpp17Lockable
  std::atomic<bool> held{false};
public:
  void lock() noexcept {
    while (held.exchange(true, std::memory_order::acquire))
      while (held.load(std::memory_order::relaxed)) {}   // 只读自旋，减少缓存行争用
  }
  bool try_lock() noexcept {
    return !held.load(std::memory_order::relaxed) &&
           !held.exchange(true, std::memory_order::acquire);
  }
  void unlock() noexcept { held.store(false, std::memory_order::release); }
};

spinlock a, b;
long x = 0, y = 0;

int main() {
  std::thread t1([] { for (int i = 0; i < 10000; ++i) { std::scoped_lock lk(a, b); ++x; ++y; } });
  std::thread t2([] { for (int i = 0; i < 10000; ++i) { std::scoped_lock lk(b, a); ++x; ++y; } });
  t1.join(); t2.join();
  assert(x == 20000 && y == 20000);
}
```

`std::scoped_lock` 同时锁多个对象时要求 *Cpp17Lockable*，它需要 `try_lock` 来实现避免死锁的算法（[[thread.lock]]）。两个线程以相反顺序传入 `a`、`b`，也不会死锁。

`x`、`y` 上没有数据竞争，原因不在 `scoped_lock`，而在 `spinlock` 的实现：`unlock` 的 release 存储与下一次 `lock` 中读到 `false` 的 acquire `exchange` 同步（[[atomics.order#2]]）。把 `unlock` 的内存序改成 `relaxed`，这个程序就有数据竞争。反过来，`lock()` 和 `unlock()` 都是空函数的类型同样满足 *Cpp17Lockable*，却什么也保护不了。标准互斥量类型的同步保证写在 [[thread.mutex.requirements]] 的 *Synchronization* 一项里。

!!! tip "需要一个线程获取、另一个线程释放时"
    `std::binary_semaphore`（[[thread.sema]]）没有所有者的概念，可以在一个线程 `acquire`、在另一个线程 `release`。

## 思考题

!!! question "1. `try_lock_for(0s)` 会阻塞吗？"

<details markdown="1">
<summary>答案</summary>

本节只说没获得锁就不会在超时之内返回，超时为零时这句话没有约束力。具体的互斥量类型在 [[thread.mutex.requirements]] 中补充：`rel_time` 不大于零时，函数如同调用 `try_lock()` 那样不阻塞地尝试。用户自定义的 *Cpp17TimedLockable* 类型则取决于它自己的规格。
</details>

!!! question "2. 用户自定义的 `rep` 在 `sleep_for` 里抛了异常，会怎样？"

<details markdown="1">
<summary>答案</summary>

这是超时相关异常（¶8），`sleep_for` 把它抛给调用者（[[thread.thread.this#9]]）。标准没有规定异常发生时线程已经睡了多久。
</details>
