---
title: Cpp17Clock 要求
summary: 一个类型要成为时钟，需要提供 rep、period、duration、time_point、is_steady 和 now()；is_steady 要求单调不减且计次间隔恒定；Cpp17TrivialClock 进一步要求相关操作不抛异常，线程库的超时函数依赖这一点。
status: done
related: time.traits, time.clock, time.point, thread.req.timing, intro.multithread
tags: 标准库, chrono, 时钟, 具名要求
updated: 2026-10-19
---

!!! tldr
    - 时钟是一个类型：几个成员类型、一个 `is_steady` 常量和一个静态 `now()`。标准时钟从不需要创建对象。
    - `is_steady` 为真要满足两个条件：先发生的 `now()` 不大于后发生的，并且计次间隔恒定。被 NTP 调快调慢的时钟即使从不回跳，也不算 steady。
    - 时钟的一秒与真实的一秒差多少，是实现质量问题，标准不作保证。
    - *Cpp17TrivialClock* 额外要求 `now()` 和相关类型的操作都不抛异常；标准库为超时函数提供的时钟都满足它。
    - 做性能测量用 `steady_clock`，不要假定 `high_resolution_clock` 是 steady 的。

## 写一个自己的时钟

```cpp run title="frame-clock.cpp" ok
#include <chrono>
#include <cstdint>

// 以帧为单位的游戏时钟（演示用：now() 返回固定值）
struct frame_clock {
  using rep        = std::int64_t;
  using period     = std::ratio<1, 60>;   // 60 Hz
  using duration   = std::chrono::duration<rep, period>;
  using time_point = std::chrono::time_point<frame_clock>;
  static constexpr bool is_steady = true;
  static time_point now() noexcept {
    return time_point{duration{42}};
  }
};

static_assert(std::chrono::is_clock_v<frame_clock>);
static_assert(frame_clock::is_steady);   // 可用于常量表达式

int main() {
  auto t = frame_clock::now().time_since_epoch();
  auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(t);
  return ms.count() == 700 ? 0 : 1;      // 42 帧 = 700 ms
}
```

[time.clock.req] 是一张具名要求表（named requirements），与 *Cpp17Allocator*、*Cpp17Hash* 同类。标准中凡是写"`Clock` 满足 *Cpp17Clock* 要求"的地方，指的都是这张表。满足它的类型可以用在 `time_point` 等需要时钟的地方；如果还满足 *Cpp17TrivialClock*，就也能用于线程库的 `_until` 函数。标准自带的时钟见 [[time.clock]]。

## 时钟是什么（¶1）

¶1 时钟是一个 duration、一个 time_point 和一个返回当前 time_point 的函数 `now()` 的组合。时钟的 time_point 的原点叫做这个时钟的纪元（epoch，[[g:clock-epoch]]）。

定义中没有说时钟是一个对象。标准时钟都是只有静态成员的类，写作 `system_clock::now()`。时钟类型在 `time_point<Clock, Duration>` 中起标签作用：它让 `sys_time` 和 `steady_clock::time_point` 成为不同的类型，从而禁止把起点不同的两个时刻相减。

## 要求表（¶2，表 131）

¶2 先约定记号：`C1`、`C2` 是时钟类型；`t1`、`t2` 是 `C1::now()` 的返回值，返回 `t1` 的那次调用发生在（happens before，[[intro.multithread]]）返回 `t2` 的调用之前，并且两次调用都早于时钟到达 `C1::time_point::max()`。注 1 说明，这一条排除了时钟在两次调用之间回绕（wrap around）的情形。

| 表达式 | 类型 | 语义 |
|---|---|---|
| `C1::rep` | 算术类型，或模拟算术类型的类 | `C1::duration` 的表示类型 |
| `C1::period` | `ratio` 的特化 | 计次周期，以秒为单位 |
| `C1::duration` | `duration<C1::rep, C1::period>` | |
| `C1::time_point` | `time_point<C1>` 或 `time_point<C2, C1::duration>` | 后一种情况下，`C1` 与 `C2` 必须有相同的纪元 |
| `C1::is_steady` | `const bool` | `t1 <= t2` 总成立，且计次间隔恒定时为 `true`；必须可用于常量表达式 |
| `C1::now()` | `C1::time_point` | 返回表示当前时刻的 time_point |

### 先发生，而不是时间上更早

稳定性用多线程内存模型的术语定义。如果线程 A 的 `now()` 先发生于线程 B 的 `now()`（例如两者之间有一次 release/acquire 同步），稳定时钟保证 B 读到的值不小于 A 读到的。两个没有同步关系的线程各自调用 `now()`，标准对两个结果的大小不作任何承诺。

### is_steady 的两个条件

单调不减和计次间隔恒定，两个条件缺一不可。有的时钟会被 NTP 慢慢校准（slew）：不往回跳，而是临时把每秒调快或调慢一点。这样的时钟满足第一个条件，但不满足第二个，所以不是 steady 的。

`is_steady` 必须可用于常量表达式（[[expr.const]]），所以可以写 `static_assert(Clock::is_steady)` 或 `if constexpr (Clock::is_steady)`。如果只是在类内声明一个 `static const bool`、在类外用非常量表达式初始化，就达不到这个要求。

### 借用另一个时钟的 time_point

`time_point<C2, C1::duration>` 这个选项允许一个时钟使用另一个纪元相同的时钟的 time_point 类型。标准把 `steady_clock::time_point` 写成 `time_point<unspecified, duration>`，就给实现留下了这样的余地。

¶3 注 2 说，时钟报告的时长与国际单位制的秒之间的相对偏差，是实现质量（quality of implementation）的度量。换句话说，标准不保证 `steady_clock` 的一秒真的是一秒，只保证它不回跳、步长恒定。

## Cpp17TrivialClock（¶4）

¶4 类型 `TC` 满足 *Cpp17TrivialClock* 要求（[[g:trivial-clock]]），需要同时满足：

- ¶4.1 满足 *Cpp17Clock* 要求；
- ¶4.2 `TC::rep`、`TC::duration`、`TC::time_point` 满足 *Cpp17EqualityComparable*、*Cpp17LessThanComparable*、*Cpp17Swappable* 要求以及数值类型的要求（[[numeric.requirements]]）。注 3 指出，这意味着对这些类型的操作不会抛异常；
- ¶4.3 `TC::now()` 不抛异常；
- ¶4.4 `TC::time_point::clock` 也满足 *Cpp17TrivialClock* 要求。

线程库的等待函数，如 `this_thread::sleep_until`、`condition_variable::wait_until`、`timed_mutex::try_lock_until`，在内部要反复调用 `now()` 并做时间运算。[[thread.req.timing]] 第 7 段规定，实现为这些函数提供的时钟满足 *Cpp17TrivialClock* 要求；第 8 段规定，如果用户提供的时钟、time_point 或 duration 在等待期间抛出异常，等待函数会把它抛出来，这类异常叫做超时相关异常。

[[time.clock.general]] ¶1 规定，本章定义的时钟默认都满足 *Cpp17TrivialClock*。例外是 `utc_clock`、`tai_clock`、`gps_clock`：它们的 `now()` 可能要读取闰秒数据，只有实现能保证不传播异常时，它们才是 trivial clock。

## 常见误解

!!! pitfall "`is_clock_v` 为真就说明时钟写对了"
    [[time.traits|is_clock]] 只检查那几个名字是否存在、`now()` 能否调用，不能验证 `is_steady` 是不是如实声明。开头的 `frame_clock` 每次返回同一个值，`is_clock_v` 照样为真。`is_steady` 是时钟作者的承诺，写错了标准库发现不了。

!!! pitfall "`high_resolution_clock` 一定是 steady 的"
    [[time.clock]] 只说它是计次周期最短的时钟，它可以是 `system_clock` 或 `steady_clock` 的别名，`is_steady` 的值未指定。libc++ 上它是 `steady_clock` 的别名，其他实现上它可能是 `system_clock`。测量耗时应该直接用 `steady_clock`，或者至少写 `static_assert(clock::is_steady)`。

!!! pitfall "`now()` 没有 `noexcept` 就一定会抛"
    `utc_clock::now()` 没有标 `noexcept`，这只表示实现可以抛异常（例如加载闰秒数据失败），并不表示某次调用一定会抛。但正因为可能抛，不能假定它满足 *Cpp17TrivialClock*。
