---
title: Cpp17Clock 要求
summary: 一个类型要成为"时钟"需要提供什么；is_steady 的精确含义；Cpp17TrivialClock 额外要求不抛异常——以及线程库的超时函数为什么依赖它
status: done
related: time.traits, time.clock, time.point, thread.req.timing, intro.multithread
tags: 标准库, chrono, 时钟, 具名要求
updated: 2026-10-18
---

[time.clock.req] 是一张具名要求表（named requirements），和 *Cpp17Allocator*、*Cpp17Hash* 同类：标准里凡是写"`Clock` 满足 *Cpp17Clock* 要求"的地方，都指这张表。标准自带的时钟见 [[time.clock]]；用户也可以写自己的时钟（例如读 CPU 周期计数器 `rdtsc`），只要满足本节，就能用于 `time_point`、`clock_cast`，满足 *Cpp17TrivialClock* 时还能用于线程库的 `_until` 函数。

## 时钟是什么（¶1）

¶1：时钟是"一个 duration、一个 time_point 和一个返回当前 time_point 的 `now()`"的组合。时钟的 time_point 的原点叫做时钟的**纪元**（[[g:clock-epoch]]，epoch）。

注意定义里没有说"时钟是一个对象"。标准时钟全是只有静态成员的类，从来不需要创建实例：`system_clock::now()`。时钟类型在 `time_point<Clock, Duration>` 里扮演的是**标签**角色——它让 `sys_time` 和 `steady_clock::time_point` 成为不同类型，从而禁止把两个起点不同的时刻相减。

## 要求表（¶2，表 131）

¶2 先约定记号：`C1`、`C2` 是时钟类型；`t1`、`t2` 是 `C1::now()` 的返回值，且返回 `t1` 的调用**发生在**（happens before，[[intro.multithread]]）返回 `t2` 的调用之前，两次调用都早于 `C1::time_point::max()`。注 1 解释这句的用意：排除时钟"绕回"（wrap around）的情形。

| 表达式 | 类型 | 语义 |
|---|---|---|
| `C1::rep` | 算术类型或模拟算术类型的类 | `C1::duration` 的表示类型 |
| `C1::period` | `ratio` 的特化 | 时钟的计次周期（秒） |
| `C1::duration` | `duration<C1::rep, C1::period>` | |
| `C1::time_point` | `time_point<C1>` 或 `time_point<C2, C1::duration>` | 后一种情形下 `C1` 与 `C2` 必须有相同纪元 |
| `C1::is_steady` | `const bool` | `t1 <= t2` 总成立**且**计次间隔恒定时为 `true`；必须能用于常量表达式 |
| `C1::now()` | `C1::time_point` | 当前时刻 |

几处值得细读：

- **"happens before"而不是"在时间上先于"。** 稳定性是用多线程内存模型的术语定义的：如果线程 A 的 `now()` 先发生于线程 B 的 `now()`（比如通过一个 release/acquire 同步），那么稳定时钟保证 B 读到的值不小于 A 读到的。两个没有同步关系的线程各自调用 `now()`，标准不对它们的大小作任何承诺。
- **`time_point<C2, C1::duration>` 这一选项**允许一个时钟"借用"另一个时钟的 time_point 类型，只要两者纪元相同。标准里 `steady_clock::time_point` 被写成 `time_point<unspecified, duration>`，正是给实现留下这种余地（例如让 `high_resolution_clock` 与 `steady_clock` 共用 time_point 类型）。
- **`is_steady` 的两个条件缺一不可**：单调不减，**并且**计次间隔恒定。一个会被 NTP "慢慢拉齐"（slew，临时把每秒调快或调慢一点）的时钟，即使从不回跳，也不是 steady。
- `is_steady` "必须能用于常量表达式"使得 `static_assert(Clock::is_steady)` 合法；这也是写测量代码时最直接的自检手段。

¶3（注 2）：时钟报告的时长与 SI 秒之间的偏差是实现质量（quality of implementation）问题。换句话说，标准不保证 `steady_clock` 的一秒真的是一秒；它只保证不回跳、步长恒定。

## Cpp17TrivialClock（¶4）

类型 `TC` 满足 *Cpp17TrivialClock*（[[g:trivial-clock]]），当且仅当：

- ¶4.1：满足 *Cpp17Clock*；
- ¶4.2：`TC::rep`、`TC::duration`、`TC::time_point` 满足 *Cpp17EqualityComparable*、*Cpp17LessThanComparable*、*Cpp17Swappable*，以及数值类型要求（[[numeric.requirements]]）。注 3：这意味着对这些类型的操作**不抛异常**；
- ¶4.3：`TC::now()` 不抛异常；
- ¶4.4：`TC::time_point::clock` 也满足 *Cpp17TrivialClock*（递归）。

为什么需要这个更强的要求？因为线程库的等待函数——`this_thread::sleep_until`、`condition_variable::wait_until`、`timed_mutex::try_lock_until` 等——要在内部反复调用 `Clock::now()` 并做时间算术。[[thread.req.timing]] ¶7 规定实现自带的、用于这些函数的时钟满足 *Cpp17TrivialClock*；¶8 规定若用户的时钟、time_point 或 duration 抛异常，等待函数会把它当作"超时相关异常"抛出。如果 `now()` 可以抛异常，等待函数在已经释放锁、尚未重新加锁的半途中就可能被打断，所以标准把"不抛"作为一类时钟的门槛。

[[time.clock]] ¶1 规定本章定义的时钟默认都满足 *Cpp17TrivialClock*，但 `utc_clock`、`tai_clock`、`gps_clock` 是例外：它们的 `now()` 要查闰秒表，可能抛异常，只有实现能保证不抛时才算 trivial clock。

## 例子：自定义时钟

```cpp title="tick-clock.cpp" ok
#include <chrono>
#include <cstdint>

// 一个以"帧"为单位、纪元为程序启动的游戏时钟（演示用：now() 返回固定值）
struct frame_clock {
    using rep        = std::int64_t;
    using period     = std::ratio<1, 60>;                 // 60 Hz
    using duration   = std::chrono::duration<rep, period>;
    using time_point = std::chrono::time_point<frame_clock>;
    static constexpr bool is_steady = true;
    static time_point now() noexcept { return time_point{duration{42}}; }
};

static_assert(std::chrono::is_clock_v<frame_clock>);
static_assert(frame_clock::is_steady);               // 常量表达式中可用

int main() {
    auto t = frame_clock::now();
    auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(t.time_since_epoch());
    return ms.count() == 700 ? 0 : 1;                // 42 帧 = 700 ms
}
```

[[time.traits|is_clock]] 只检查名字是否存在（¶1 的最低限度），并不能验证 `is_steady` 说的是不是真话——`is_steady` 是一个**承诺**，写错了标准库无从发现，后果由使用者承担。

## 陷阱

!!! pitfall "`high_resolution_clock` 不一定是 steady"
    [[time.clock]] 只说它是"计次周期最短的时钟"，可以是 `system_clock` 或 `steady_clock` 的别名。libc++ 上它是 `steady_clock`（`is_same_v` 为真），而在其他实现上它可能是 `system_clock`。做性能测量时应直接用 `steady_clock`，或者至少 `static_assert(clock::is_steady)`。

!!! pitfall "`now()` 不是 `noexcept` 不等于会抛"
    `utc_clock::now()` 没有标 `noexcept`，但这不说明某次调用一定会抛，只是说实现**可以**抛（例如首次加载时区数据库失败）。这类时钟不能假定满足 *Cpp17TrivialClock*。

## 思考题

1. 一个时钟的 `now()` 每次返回 `time_point::max()`。它违反了表 131 吗？

<details markdown="1">
<summary>答案</summary>

¶2 的 `t1`、`t2` 被限定为"发生在 `C1::time_point::max()` 之前"的调用结果，所以 `is_steady` 的条件对它不构成约束；但 `now()` 的语义是"返回代表当前时刻的 time_point"，一个永远返回 `max()` 的函数显然不满足这条操作语义。这是不可由编译器检查的语义要求，违反它的后果取决于使用方（例如 [[res.on.functions]] 下把它传给标准库组件则行为未定义）。
</details>

2. 为什么 `is_steady` 要求"能用于常量表达式"，而不只是一个 `static const bool`？

<details markdown="1">
<summary>答案</summary>

`static const bool` 若只在类内声明、类外以非常量初始化，就不能用于常量表达式。标准希望用户能写 `static_assert(C::is_steady)` 或 `if constexpr (C::is_steady)` 在编译期选择策略，所以显式要求它可用于常量表达式（[[expr.const]]）。
</details>

## 小结

| 要求 | 关键点 |
|---|---|
| *Cpp17Clock* | `rep`/`period`/`duration`/`time_point`/`is_steady`/`now()`；纪元是 time_point 的原点 |
| `is_steady` | 单调不减（以 happens-before 定义）**且**步长恒定；常量表达式可用 |
| *Cpp17TrivialClock* | 再加：相关类型的操作不抛、`now()` 不抛；线程库超时函数依赖它 |
