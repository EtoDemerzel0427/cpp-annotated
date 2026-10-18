---
title: 类模板 time_point
summary: time_point = 时钟标签 + 距纪元的 duration；时刻与时长的代数（时刻 ± 时长 = 时刻，时刻 − 时刻 = 时长，时刻 + 时刻 无意义）；不同时钟的时刻为什么不能混用；time_point_cast 与 floor/ceil/round
status: done
covers: *
related: time.duration, time.clock, time.clock.req, time.cal, time.traits
tags: 标准库, chrono, time_point
updated: 2026-10-18
---

`time_point<Clock, Duration>` 表示"某个时钟上的一个时刻"。它的全部数据是一个 duration：距该时钟纪元（[[g:clock-epoch]]）的时间。`Clock` 只作为类型标签存在，不占空间，也从不被实例化。

time_point 与 duration 的关系就像仿射空间里的点与向量，或者指针与 `ptrdiff_t`：

| 表达式 | 结果 | 类比 |
|---|---|---|
| 时刻 + 时长、时长 + 时刻 | 时刻 | 指针 + 整数 |
| 时刻 − 时长 | 时刻 | 指针 − 整数 |
| 时刻 − 时刻（同一时钟） | 时长 | 指针 − 指针 |
| 时刻 + 时刻 | **不存在** | 指针 + 指针 |
| 时刻 − 时刻（不同时钟） | **不存在** | 两个数组里的指针相减 |

"今天 12:00 + 明天 12:00"没有意义，所以没有这个运算符；`system_clock` 与 `steady_clock` 的纪元不同，两者的时刻相减同样没有意义，所以它们是不同类型，相减直接编译失败。

## 定义（[time.point.general]）

```cpp
template<class Clock, class Duration = typename Clock::duration>
class time_point {
public:
  using clock    = Clock;
  using duration = Duration;
  using rep      = duration::rep;
  using period   = duration::period;
private:
  duration d_;          // 仅用于说明
public:
  constexpr time_point();                                   // 值为纪元
  constexpr explicit time_point(const duration& d);         // 纪元 + d
  template<class Duration2>
    constexpr time_point(const time_point<clock, Duration2>& t);
  constexpr duration time_since_epoch() const;
  // ++ -- += -=，min() max()
};
```

¶1：若 `Duration` 不是 `duration` 的特化，程序非良构。

注意 `Duration` 可以与 `Clock::duration` 不同——`sys_days` 就是 `time_point<system_clock, days>`，`sys_seconds` 是 `time_point<system_clock, seconds>`。同一个时钟、不同精度的时刻是不同类型，但可以互相转换（见下文构造函数）。

正文对 `Clock` 没有提要求：`Clock` 可以不满足 *Cpp17Clock*。`local_time<D>` 就是 `time_point<local_t, D>`，而 `local_t` 只是一个空结构体（[[time.clock]]）。

## 构造（[time.point.cons]）

- ¶1：默认构造函数用 `duration::zero()` 初始化 `d_`，得到的对象**代表纪元**。与 `duration` 不同，`time_point` 的默认构造是**有值的**。
- ¶2：`explicit time_point(const duration& d)` 得到"纪元 + d"。`explicit` 防止把一个时长误当成时刻：`sys_seconds t = 5s;` 非良构。
- ¶3–¶4：从同一时钟的另一个 time_point 转换，约束为 `is_convertible_v<Duration2, duration>`——完全复用 duration 的隐式转换规则：`sys_seconds` → `sys_time<milliseconds>` 可以隐式，反之不行。

```cpp title="tp-conv.cpp" ok
#include <chrono>
#include <type_traits>
using namespace std::chrono;

static_assert( std::is_convertible_v<sys_days, sys_seconds>);          // 天 → 秒：只需乘法
static_assert(!std::is_convertible_v<sys_seconds, sys_days>);          // 需要截断
static_assert(!std::is_convertible_v<sys_seconds, local_seconds>);     // 不同"时钟"
static_assert(!std::is_convertible_v<seconds, sys_seconds>);           // 时长不是时刻（explicit）

int main() {
    sys_seconds t{};                         // 纪元：1970-01-01 00:00:00
    return t.time_since_epoch() == 0s ? 0 : 1;
}
```

## 观察器、成员算术与特殊值

- [time.point.observer] ¶1：`time_since_epoch()` 返回 `d_`。这是从时刻"取出"数值的唯一途径，也是跨时钟换算时（例如自己实现 `to_sys`）手工搬运数值的入口。
- [time.point.arithmetic] ¶1–¶10：`++`、`--`、`+=`、`-=` 直接作用于 `d_`；`+=` 的参数是本类型的 `duration`。前置 `++` 让时刻前进一个计次周期：`sys_days` 的 `++` 是"下一天"。
- [time.point.special] ¶1–¶2：`min()`、`max()` 返回 `time_point(duration::min())` 和 `time_point(duration::max())`。

## 非成员算术（[time.point.nonmember]）

| 运算 | 返回类型 | 段落 |
|---|---|---|
| `tp + d`、`d + tp` | `time_point<Clock, common_type_t<Duration1, duration<Rep2, Period2>>>` | ¶1–¶2 |
| `tp - d` | 同上 | ¶3 |
| `tp1 - tp2` | `common_type_t<Duration1, Duration2>` | ¶4 |

结果的精度是两者中**更细**的那个：`sys_days + 1h` 的类型是 `sys_time<hours>`，不再是 `sys_days`。这条规则让信息不会丢失，但也意味着"在日期上加几个小时"之后，变量类型变了，不能再赋回 `sys_days` 变量。

¶4 的两个 time_point 必须属于**同一个** `Clock`（模板参数只有一个 `Clock`），这就是"不同时钟不能相减"的出处——没有可行的 `operator-`，编译失败。

```cpp title="tp-mixed-clocks.cpp" error
#include <chrono>
using namespace std::chrono;

int main() {
    auto a = system_clock::now();
    auto b = steady_clock::now();
    auto d = a - b;               // error: 没有匹配的 operator-（两个 Clock 不同）
    sys_days sd{}; local_days ld{};
    auto e = sd - ld;             // error: sys_time 与 local_time 也是不同"时钟"
}
```

## 比较（[time.point.comparisons]）

¶1–¶6：`==`、`<`、`>`、`<=`、`>=`、`<=>` 都比较 `time_since_epoch()`，两个实参必须是同一个 `Clock`，`Duration` 可以不同（经由 duration 的跨单位比较）。`<=>` 要求 `three_way_comparable_with<Duration1, Duration2>`。

所以 `sys_days{2024y/January/1} == sys_seconds{...}` 是合法的，比较的是同一时钟上的两个时刻；`sys_days{} == local_days{}` 非良构。

## 转换（[time.point.cast]）

| 函数 | 效果 | 段落 |
|---|---|---|
| `time_point_cast<To>(tp)` | `time_point<Clock, To>(duration_cast<To>(tp.time_since_epoch()))` | ¶1–¶2 |
| `floor<To>(tp)` | 对 `time_since_epoch()` 做 `floor` | ¶3–¶4 |
| `ceil<To>(tp)` | 对 `time_since_epoch()` 做 `ceil` | ¶5–¶6 |
| `round<To>(tp)` | 对 `time_since_epoch()` 做 `round`；`To::rep` 不能是浮点 | ¶7–¶8 |

四个函数的约束都是"`ToDuration` 是 duration 的特化"——它们只改精度，不改时钟。跨时钟要用 `clock_cast`（[[time.clock]]）。

注意 `time_point_cast` 名字里有 cast，而截断规则来自 `duration_cast`：**向零截断**。对于纪元之前的时刻（`time_since_epoch()` 为负），这会向"未来"取整：

```cpp title="tp-floor.cpp" ok
#include <chrono>
#include <iostream>
using namespace std::chrono;

int main() {
    sys_seconds t = sys_days{1969y/December/31} + 18h;   // 纪元前 6 小时
    std::cout << time_point_cast<days>(t) << '\n';      // 1970-01-01：向零截断，跑到了"明天"
    std::cout << floor<days>(t) << '\n';                // 1969-12-31：正确的"当天零点"
}
```

**取"日期部分"永远用 `floor<days>`**。这条规则对 `sys_time` 和 `local_time` 都适用（[[time.cal]] 中 `year_month_day{floor<days>(tp)}` 是标准写法）。

## 陷阱

!!! pitfall "默认的 Duration 是时钟的 duration"
    `time_point<system_clock>` 的精度由实现决定：libc++ 是微秒，libstdc++ 是纳秒，MSVC 是 100 纳秒。序列化 `time_since_epoch().count()` 时若不指定单位，换一个标准库就会读出错误的值。先 `time_point_cast<milliseconds>` 或 `floor<seconds>` 到一个确定的单位再存储。

!!! pitfall "time_point::max() 加任何正数都会溢出"
    把 `time_point::max()` 当作"永不超时"的哨兵很常见，但等待函数内部常常要做 `deadline - now()` 或换算到另一个时钟，`max()` 一参与运算就溢出（{{ub}}）。标准库实现对 `wait_until(max())` 通常有特判，但自己写的时间算术没有。

## 小结

- time_point 只存一个 duration；时钟是零开销的类型标签。
- 时刻 ± 时长 = 时刻；同钟时刻 − 时刻 = 时长；其他组合不存在。
- 精度不同可以隐式转换（规则同 duration），时钟不同绝不能。
- 取日期用 `floor<days>`，不要用 `time_point_cast<days>`。
