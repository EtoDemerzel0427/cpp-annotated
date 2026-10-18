---
title: 并发库的通用要求
summary: 第 32 章的公共约定——Predicate 与 Clock 模板形参、system_error 的报告方式、native_handle、超时规格（_for 用稳定时钟、_until 跟随给定时钟、时钟被调整时怎么办），以及 Cpp17BasicLockable/Lockable/TimedLockable/SharedLockable 系列要求
status: done
covers: *
related: thread, thread.mutex.requirements, thread.lock, thread.condition, time.clock.req, syserr
tags: 标准库, 并发, 超时, 锁
updated: 2026-10-18
---

[thread.req] 是本章的"总则"：后面每个子条款都会说"按 [thread.req.timing] 处理超时"、"Mutex 须满足 *Cpp17BasicLockable*"、"在需要时抛 `system_error`（[thread.req.exception]）"。这些引用如果不先读懂，后面的条文就只能看个大概。

本页覆盖五个三级条款：模板形参名（[thread.req.paramname]）、异常（[thread.req.exception]）、native handle（[thread.req.native]）、超时规格（[thread.req.timing]）、可锁类型要求（[thread.req.lockable] 及其六个子条款）。

## 模板形参名（[thread.req.paramname]）

¶1 本章用模板形参的**名字**表达类型要求：

- 名为 `Predicate` 的形参：函数对象类型。设 `pred` 是该类型的左值，`pred()` 必须良构，`decltype(pred())` 必须实现 *boolean-testable*（[[concept.booleantestable]]）。返回值转为 `bool` 后表示"等待条件是否满足"。这用在 `condition_variable::wait(lock, pred)` 一类函数上。
- 名为 `Clock` 的形参：实参类型 `C` 必须满足 *Cpp17Clock*（[[time.clock.req]]）；**若 `is_clock_v<C>` 为 `false`，程序非良构** {{ill-formed}}。

第二条值得注意："shall meet *Cpp17Clock*" 本身只是一条语义要求（违反是 UB），但紧跟着的"is_clock_v 为 false 则非良构"把其中可以静态检查的部分升级成了必须诊断的错误。`is_clock_v` 检查的是语法层面的成员：`rep`、`period`、`duration`、`time_point`、`is_steady`、`now()`。

```cpp run title="not-a-clock.cpp" error
#include <chrono>
#include <thread>
struct almost_clock {             // 有 now()，但缺少 is_steady：is_clock_v 为 false
  using rep = long long;
  using period = std::nano;
  using duration = std::chrono::nanoseconds;
  using time_point = std::chrono::time_point<almost_clock>;
  static time_point now() { return time_point{}; }
};
static_assert(!std::chrono::is_clock_v<almost_clock>);
int main() {
  std::this_thread::sleep_until(almost_clock::now());   // error：is_clock_v<almost_clock> 为 false
}
```

!!! impl "libc++ 没有诊断"
    按 ¶1 这个程序非良构，必须给出诊断。但 Clang 23 自带的 libc++ 编译它**没有任何错误**：`sleep_until` 的实现只用到了 `Clock::now()` 和 `time_point` 的算术，没有显式检查 `is_clock_v`。如果把 `now()` 也删掉，libc++ 会报错，但那是因为函数体里找不到 `now`，并非出于 ¶1 的检查。这是实现的一致性缺陷。

## 异常（[thread.req.exception]）

¶1 本章有些函数规定"抛出 `system_error`"。它们在两种情况下抛：

1. 检测到该函数 *Error conditions* 元素里列出的某种错误条件；
2. 底层操作系统 API 调用出错，导致库函数无法满足其规格。

分配失败则按 [[res.on.exception.handling]] 报告（通常是 `bad_alloc`）。

例 1 讲了映射过程：POSIX 调用返回 `EPERM`（"调用者没有权限"），实现把它映射为 `errc::operation_not_permitted`，抛出 `system_error`。

¶2 这样抛出的异常，其 `code()` 与函数 *Error conditions* 中列出的某个条件**比较相等**。注意是 `error_code` 与 `error_condition` 的比较（[[syserr]]），不是 `code().value()` 等于某个整数：同一个条件在不同平台上可以对应不同的原生错误码。

```cpp run title="join-self.cpp" ok
#include <cstdio>
#include <system_error>
#include <thread>

int main() {
  std::thread t;
  try {
    t.join();          // 不可 join：Error conditions 规定为 invalid_argument
  } catch (const std::system_error& e) {
    std::printf("%d\n", e.code() == std::errc::invalid_argument);   // 1
  }
}
```

## Native handle（[thread.req.native]）

¶1 `thread`、`mutex`、`condition_variable` 等类可能有成员 `native_handle_type` 与 `native_handle()`。它们**是否存在、语义如何都由实现定义** {{impl}}。注 1 解释了为什么还要在标准里写出名字：为了能在编译期**可移植地探测**它们是否存在（例如用 `requires { m.native_handle(); }`），尽管实际使用它们本身不可移植。

在 libc++/macOS 上，`std::thread::native_handle()` 返回 `pthread_t`，`std::mutex::native_handle()` 返回 `pthread_mutex_t*`。典型用途是设置线程优先级、CPU 亲和性或线程名——标准接口（如 C++23 之后加入草案的 `thread::name_hint`，见 [[thread.threads]]）覆盖不到的地方。

## 超时规格（[thread.req.timing]）

本章有大量 `_for`/`_until` 后缀的函数：`sleep_for`、`try_lock_until`、`wait_for`、`try_acquire_until`……它们共享一套超时语义，全写在这里。

### 两种延迟（¶1–¶2）

¶1 超时以 `duration` 或 `time_point` 指定（[[time]]）。

¶2 实现从超时返回**必然**有延迟，标准把它分成两部分：

- **实现质量延迟** D<sub>i</sub>（quality of implementation）：中断响应、函数返回、调度带来的开销；
- **管理质量延迟** D<sub>m</sub>（quality of management）：对处理器和内存资源的争用带来的延迟。

两者可以每次不同，"越短越好"。这一段的法律意义是：**标准从不承诺超时函数准时返回**，只承诺不会**提前**返回（下面的 ¶3、¶4 都以"至少"的方式表述）。

### 相对超时：应该用稳定时钟（¶3）

¶3 名字以 `_for` 结尾的函数接受时长，产生**相对超时**。实现**应当**（should）用**稳定时钟**（steady clock）计时。给定时长 D<sub>t</sub>，超时的真实时长是 D<sub>t</sub>+D<sub>i</sub>+D<sub>m</sub>。

为什么要强调稳定时钟？因为 `system_clock` 可能被 NTP 或管理员调整。如果 `wait_for(5s)` 内部换算成"现在的墙钟时间 + 5 秒"再按墙钟等待，那么等待期间墙钟被往回拨一小时，线程就会多睡一小时。

标准自己在定义条件变量时就贯彻了这一点：[[thread.condition.general]] 的仅说明用函数 *rel-to-abs* 把相对时长换算成 **`steady_clock`** 的时间点，`wait_for` 被规定为等价于 `wait_until(lock, rel-to-abs(rel_time))`。

### 绝对超时：跟随给定的时钟（¶4–¶5）

¶4 名字以 `_until` 结尾的函数接受时间点，产生**绝对超时**。实现应当用**时间点自己的时钟**计时。给定时间点 C<sub>t</sub>：若等待期间时钟没有被调整，返回时刻应为 C<sub>t</sub>+D<sub>i</sub>+D<sub>m</sub>。若时钟在等待期间被调整到 C<sub>a</sub>：

- ¶4.1 C<sub>a</sub> > C<sub>t</sub>（往前拨过了截止时间）：应尽快醒来（C<sub>a</sub>+D<sub>i</sub>+D<sub>m</sub>），因为超时已经满足。用稳定时钟衡量，总等待时间**变短**了。
- ¶4.2 C<sub>a</sub> ≤ C<sub>t</sub>：在 `Clock::now()` 返回某个 C<sub>n</sub> ≥ C<sub>t</sub> 之前不应超时。注 1：时钟往回拨会让等待（按稳定时钟衡量）**变长**，往前拨会**变短**。

然后是一句给实现留余地的话：实现可以在"上面规定的时刻"到"如果把 C<sub>t</sub> 与调用时刻之差当作一个稳定时钟相对超时来等待，会返回的时刻"之间的任何一点返回。*推荐做法*：时钟往前拨时，实现应当缩短等待。

换句话说：`wait_until(system_clock::now() + 1h)` 的意思是"等到墙钟显示那个时刻"，而 `wait_for(1h)` 的意思是"等一个小时的物理时间"。二者在时钟被调整时行为不同，这是**有意为之**的。选择哪个取决于你的意图：定时任务"每天 9 点执行"用 `_until` + `system_clock`；"5 秒内没响应就放弃"用 `_for`（或 `_until` + `steady_clock`）。

¶5 注 2：若时钟与稳定时钟不同步（例如 CPU 时间时钟），这类超时可能毫无用处。

```cpp run title="deadline.cpp" ok
#include <chrono>
#include <condition_variable>
#include <mutex>

std::mutex m;
std::condition_variable cv;
bool ready = false;

bool wait_with_deadline() {
  using namespace std::chrono_literals;
  // 一个截止时间贯穿多次等待：用 steady_clock 的绝对时间点，避免每次 wait_for 重新计时
  auto deadline = std::chrono::steady_clock::now() + 100ms;
  std::unique_lock lk(m);
  return cv.wait_until(lk, deadline, [] { return ready; });   // 超时则返回 false
}

int main() { return wait_with_deadline() ? 1 : 0; }
```

!!! pitfall "在循环里反复 `wait_for` 会让截止时间漂移"
    `while (!ready) cv.wait_for(lk, 100ms);` 每次被（虚假）唤醒都会重新计 100ms，总等待时间没有上限。需要总超时时，像上例那样先算出一个 `steady_clock` 时间点，再用 `wait_until`。

!!! impl "libc++ 在 macOS 上的 condition_variable::wait_for"
    libc++ 只有在 glibc ≥ 2.30 或 Android API ≥ 30 上才使用 `pthread_cond_clockwait(CLOCK_MONOTONIC)`。macOS 没有这个函数，libc++ 的做法（见 `<__condition_variable/condition_variable.h>`）是：把相对时长加到 `system_clock::now()` 上，交给 `pthread_cond_timedwait`；返回后再用 `steady_clock` 测量实际经过的时间，决定返回 `timeout` 还是 `no_timeout`。也就是说，**底层等待仍然以墙钟为基准**，¶3 的"应当用稳定时钟"在这里只是部分做到。

### 分辨率、时钟要求与超时相关异常（¶6–¶8）

¶6 实现提供的最细计时分辨率称为**原生分辨率**（[[g:native-resolution]]，native resolution），取决于操作系统和硬件。

¶7 这些函数使用的、由实现提供的时钟满足 *Cpp17TrivialClock*（[[time.clock.req]]）——即 `now()` 不抛异常，`rep`/`duration`/`time_point` 的操作也不抛。

¶8 接受超时参数的函数，如果在执行期间时钟、时间点或时长**抛出了异常**，函数就抛出该异常。这样的异常称为**超时相关异常**（[[g:timeout-related-exception]]，timeout-related exceptions）。注 3：实现自带的时钟、时间点、时长类型都不抛异常；只有用户自定义的 `rep`（比如带溢出检查的整数类型）或用户时钟才可能抛。所以你会在本章大量看到 "*Throws*: Timeout-related exceptions"——它的意思是"本函数自己不抛，只转发你提供的时间类型抛出的异常"。

## 可锁类型要求（[thread.req.lockable]）

### 执行代理与锁的两种类型（[thread.req.lockable.general]）

¶1 **执行代理**（[[g:execution-agent]]，execution agent）是线程之类、可以与其他执行代理并行工作的实体。注 1：实现或用户可以引入其他种类的代理，如进程或线程池任务。"调用方代理"由上下文决定，例如包含该调用的线程。

为什么不直接说"线程"？因为可锁要求描述的是一种**协议**，不应把锁绑死在 OS 线程上。¶2 注 2 举例：有些可锁对象是"代理无关"的（agent oblivious），比如普通的自旋锁，它们不记录、也不判断拥有者是谁，所以对任何执行代理模型都适用。

¶3 `unique_lock`、`shared_lock`、`scoped_lock`、`lock_guard`、`std::lock`、`std::try_lock`、`condition_variable_any` 都操作**用户提供**的可锁对象。下面五组要求列出这些库组件为获取、释放锁所需的接口。注 3 很重要：**锁所有权的性质以及它带来的任何同步，不属于这些要求**。也就是说，`std::lock_guard<MyLock>` 本身不保证任何内存可见性——是否同步完全取决于 `MyLock` 的实现。

¶4 对对象 `m` 的锁分两种：

- ¶4.1 **非共享锁**（non-shared lock）：通过 `m` 上的 `lock`、`try_lock`、`try_lock_for`、`try_lock_until` 获得；
- ¶4.2 **共享锁**（shared lock）：通过 `lock_shared`、`try_lock_shared`、`try_lock_shared_for`、`try_lock_shared_until` 获得。

注 4：这里只看**获取方式**，不管所有权的性质。所以即使某个类型的 `lock()` 实际上允许多个代理同时持有（比如 [[saferecl]] 的 `rcu_domain`），按定义它获得的仍叫"非共享锁"。

### 五组要求

| 要求 | 额外的表达式 | 关键语义 |
|---|---|---|
| *Cpp17BasicLockable*（[thread.req.lockable.basic]） | `m.lock()`、`m.unlock()` | `lock` 阻塞直到获得；抛异常则未获得。`unlock` 的**前置条件**：当前代理持有 `m` 上的非共享锁；不抛异常 |
| *Cpp17Lockable*（[thread.req.lockable.req]） | + `m.try_lock()` | 不阻塞地尝试；返回 `bool` |
| *Cpp17TimedLockable*（[thread.req.lockable.timed]） | + `try_lock_for(rel)`、`try_lock_until(abs)` | 在相对/绝对超时内尝试；**除非获得锁，否则不会在超时前返回** |
| *Cpp17SharedLockable*（[thread.req.lockable.shared]） | `lock_shared`、`try_lock_shared`、`unlock_shared` | 与上面平行的共享版本；`unlock_shared` 的前置条件是持有共享锁 |
| *Cpp17SharedTimedLockable*（[thread.req.lockable.shared.timed]） | + `try_lock_shared_for`、`try_lock_shared_until` | 带超时的共享版本，返回类型须为 `bool` |

逐条看几个容易忽略的细节：

**[thread.req.lockable.basic]** ¶2：`m.lock()`"阻塞直到能为当前执行代理获得一把锁。若抛出异常，则锁不应已被获得"。这一句保证了 RAII 包装的异常安全：`lock_guard` 的构造函数里 `lock()` 抛了异常，析构函数不会运行，也不需要运行。¶3–¶5：`unlock()` 的前置条件是**当前**代理持有非共享锁；*Throws*: Nothing。

**[thread.req.lockable.req]** ¶2–¶4：`try_lock()` 的返回类型就是 `bool`（*Return type*），不是"可转换为 bool"。

**[thread.req.lockable.timed]** ¶2：`try_lock_for(rel_time)` "除非已为当前代理获得 `m` 上的锁，否则不会在 `rel_time` 指定的超时之内返回"。注意反过来不成立：超时到了也可能还没返回（D<sub>i</sub>+D<sub>m</sub>），而即使锁一直空闲，`try_lock_for` 也**可以**返回 `false`——要求里只说返回 `true` 当且仅当获得了锁，没说锁空闲时必须获得。具体的互斥量类型在 [[thread.mutex.requirements]] 里另有"实现应尽力获得"的说明。

**[thread.req.lockable.shared]** ¶1 与 **[thread.req.lockable.shared.timed]** ¶1：共享版本的措辞略有不同——直接要求 `try_lock_shared()` 等表达式的类型是 `bool`，而不是另起一个 *Return type* 元素。效果相同。

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

`std::scoped_lock` 锁多个对象时要求 *Cpp17Lockable*（需要 `try_lock` 来实现免死锁算法，见 [[thread.lock]]）。这里两个线程以相反顺序传入 `a`、`b`，不会死锁。

注意同步从哪里来：按 ¶3 注 3，`scoped_lock` 本身不提供同步。`x`、`y` 上没有数据竞争，是因为 `spinlock::unlock` 的 release 存储与下一次 `lock` 中读到 `false` 的 acquire `exchange` 同步（[[atomics.order#2]]）。若把 `unlock` 的内存序改成 `relaxed`，这个程序就有数据竞争 {{ub}}。

## 陷阱

!!! pitfall "\"满足 Lockable\" 不等于 \"能用来保护数据\""
    *Cpp17Lockable* 只是语法加上"阻塞/尝试"的语义。一个 `lock()`/`unlock()` 都是空函数的类型也满足这些要求（只要你不同时让两个代理"持有"它而违反自己的规约）。数据保护所需的 happens before 必须由类型自己的实现提供；标准的互斥量类型在 [[thread.mutex.requirements]] 里用 *Synchronization* 元素明确提供了它。

!!! pitfall "unlock 的前置条件看的是\"当前代理\""
    *Cpp17BasicLockable* ¶3 要求**调用 `unlock` 的代理**持有锁。在 A 线程 `lock()`、在 B 线程 `unlock()`，对 `std::mutex` 而言违反前置条件 {{ub}}。需要"一个线程获取、另一个线程释放"的语义时，用 `std::binary_semaphore`（[[thread.sema]]），它没有所有者的概念。

## 思考题

!!! question "1. `try_lock_for(0s)` 会阻塞吗？"

<details markdown="1">
<summary>答案</summary>

本节只说"除非获得锁，否则不会在超时之内返回"，超时为零时这句话没有约束力。具体的互斥量类型在 [[thread.mutex.requirements]] 中补充：若 `rel_time` 小于等于 `rel_time.zero()`，函数"如同调用 `try_lock()`"那样不阻塞地尝试。对用户自定义的 *Cpp17TimedLockable* 类型，则取决于该类型自己的规约。
</details>

!!! question "2. 用户自定义的 `rep` 在 `sleep_for` 里抛了异常，会怎样？"

<details markdown="1">
<summary>答案</summary>

¶8：这是超时相关异常，`sleep_for` 把它抛给调用者（[[thread.thread.this]] ¶9：*Throws*: Timeout-related exceptions）。线程可能已经睡了一部分，也可能还没开始睡——标准没有规定异常发生时已经等了多久。
</details>

## 小结

- `Predicate`、`Clock` 这些形参名本身就是要求；`Clock` 不满足 `is_clock_v` 时非良构（libc++ 目前不诊断）。
- `system_error` 的 `code()` 与 *Error conditions* 中的条件**比较相等**，不是整数相等。
- `_for` 应以稳定时钟计时，`_until` 跟随给定时钟，二者在时钟调整时行为不同；超时只保证不早于，不保证准时。
- 可锁要求只规定接口与阻塞语义，**不规定同步**；"非共享/共享锁"只按获取方式区分。
