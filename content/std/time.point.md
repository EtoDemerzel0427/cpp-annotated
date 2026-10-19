---
title: 类模板 time_point
summary: time_point 是一个时钟标签加上距该时钟纪元的 duration；时刻与时长之间允许哪些运算，不同时钟的时刻为什么不能混用，以及 time_point_cast 与 floor、ceil、round 的区别。
status: done
covers: *
related: time.duration, time.clock, time.clock.req, time.cal, time.traits
tags: 标准库, chrono, time_point
updated: 2026-10-19
---

!!! tldr
    - `time_point<Clock, Duration>` 只存一个 duration，即距时钟纪元的时间；`Clock` 只是一个类型标签，不占空间。
    - 时刻加减时长得到时刻，同一时钟的两个时刻相减得到时长；两个时刻相加、不同时钟的时刻相减都没有对应的运算符，编译失败。
    - 同一时钟、不同精度的时刻可以互相转换，规则和 duration 一样：不截断的方向可以隐式转换，会截断的方向要显式转换。
    - 取一个时刻的日期部分要用 `floor<days>`。`time_point_cast<days>` 向零截断，对 1970 年以前的时刻会得到第二天。

## 时刻与时长

```cpp run error title="tp-algebra.cpp"
#include <chrono>
using namespace std::chrono;

int main() {
  sys_days today = 2024y/March/15;
  auto tomorrow = today + days{1};     // OK：时刻 + 时长 = 时刻
  auto gap = tomorrow - today;         // OK：时刻 - 时刻 = 时长
  auto nonsense = today + tomorrow;    // error: 时刻 + 时刻没有意义

  auto a = system_clock::now();
  auto b = steady_clock::now();
  auto d = a - b;                      // error: 两个时钟的纪元不同
}
```

`time_point` 和 `duration` 的关系，就像指针和 `ptrdiff_t`：指针加整数得到指针，两个指针相减得到整数，两个指针相加没有意义，两个不同数组里的指针相减也没有意义。

| 表达式 | 结果 | 类比 |
|---|---|---|
| 时刻 + 时长、时长 + 时刻、时刻 − 时长 | 时刻 | 指针 ± 整数 |
| 同一时钟的时刻 − 时刻 | 时长 | 指针 − 指针 |
| 时刻 + 时刻 | 没有这个运算 | 指针 + 指针 |
| 不同时钟的时刻 − 时刻 | 没有这个运算 | 两个数组里的指针相减 |

`system_clock` 和 `steady_clock` 的纪元不同，一个是 1970 年 1 月 1 日，一个通常是开机时刻。它们的时刻是不同的类型，相减时找不到可行的 `operator-`。

## 定义 [time.point.general]

```cpp
template<class Clock, class Duration = typename Clock::duration>
class time_point {
public:
  using clock    = Clock;
  using duration = Duration;
  using rep      = duration::rep;
  using period   = duration::period;
private:
  duration d_;    // 仅用于说明
  // ...
};
```

`time_point` 的全部数据就是 `d_`，距该时钟纪元（[[g:clock-epoch]]）的时间。

¶1 如果 `Duration` 不是 `duration` 的特化，程序非良构。

`Duration` 可以和 `Clock::duration` 不同。`sys_days` 是 `time_point<system_clock, days>`，`sys_seconds` 是 `time_point<system_clock, seconds>`：同一个时钟，不同精度，是不同的类型。

本节对 `Clock` 没有额外要求。`local_time<D>` 就是 `time_point<local_t, D>`，而 `local_t` 只是一个空结构体，连 `now()` 都没有（[[time.clock]]）。

## 构造与精度转换 [time.point.cons]

```cpp run ok title="tp-conv.cpp"
#include <chrono>
#include <type_traits>
using namespace std::chrono;

static_assert( std::is_convertible_v<sys_days, sys_seconds>);      // 天 → 秒：乘法
static_assert(!std::is_convertible_v<sys_seconds, sys_days>);      // 会截断
static_assert(!std::is_convertible_v<sys_seconds, local_seconds>); // 不同时钟
static_assert(!std::is_convertible_v<seconds, sys_seconds>);       // explicit

int main() {
  sys_seconds t{};                        // 纪元：1970-01-01 00:00:00
  return t.time_since_epoch() == 0s ? 0 : 1;
}
```

¶1 默认构造函数用 `duration::zero()` 初始化 `d_`，得到的对象代表纪元。这一点和 duration 不同：`time_point` 的默认构造有确定的值。

¶2 `explicit time_point(const duration& d)` 得到纪元加 `d`。它是 `explicit` 的，防止把一段时长误当成一个时刻：`sys_seconds t = 5s;` 非良构。

¶3 从同一时钟的另一个 time_point 转换时，要求 `Duration2` 能隐式转换为 `duration`。这完全沿用了 duration 的规则（[[time.duration]]）：`sys_seconds` 可以隐式转换为 `sys_time<milliseconds>`，反过来不行。¶4 转换的值就是 `t.time_since_epoch()`。

## 成员

[[time.point.observer#1]] 的 `time_since_epoch()` 返回 `d_`。这是从时刻取出数值的唯一途径，跨时钟换算时手工搬运数值也要经过它。

[[time.point.arithmetic]] 的 `++`、`--`、`+=`、`-=` 直接作用于 `d_`（¶1–¶10），`+=` 的形参是本类型的 `duration`。前置 `++` 让时刻前进一个计次周期，`sys_days` 的 `++` 就是下一天。

[[time.point.special]] 的 `min()` 和 `max()` 分别是 `time_point(duration::min())` 和 `time_point(duration::max())`（¶1–¶2）。

## 非成员算术 [time.point.nonmember]

| 运算 | 返回类型 | 段落 |
|---|---|---|
| `tp + d`、`d + tp`、`tp - d` | `time_point<Clock, common_type_t<Duration1, duration<Rep2, Period2>>>` | ¶1–¶3 |
| `tp1 - tp2` | `common_type_t<Duration1, Duration2>` | ¶4 |

结果的精度取两者中较细的那个：`sys_days + 1h` 的类型是 `sys_time<hours>`，不再是 `sys_days`。这样不会丢失信息，但"在日期上加几个小时"之后类型变了，不能再赋回 `sys_days` 变量。

¶4 的两个形参共用同一个模板参数 `Clock`，所以只有同一时钟的时刻才能相减。不同时钟相减时没有可行的 `operator-`，这就是开头例子出错的出处。

## 比较 [time.point.comparisons]

¶1 `==`、`<`、`>`、`<=`、`>=` 和 `<=>` 都比较 `time_since_epoch()`（¶1–¶6）。两个实参必须属于同一个 `Clock`，`Duration` 可以不同，比较时借助 duration 的跨单位比较。¶6 的 `<=>` 要求 `three_way_comparable_with<Duration1, Duration2>`。

所以 `sys_days{2024y/January/1} == sys_seconds{1704067200s}` 合法，比较的是同一时钟上的两个时刻；`sys_days{} == local_days{}` 非良构。

## 精度转换函数 [time.point.cast]

```cpp run ok title="tp-floor.cpp"
#include <chrono>
#include <iostream>
using namespace std::chrono;

int main() {
  sys_seconds t = sys_days{1969y/December/31} + 18h;  // 纪元前 6 小时
  std::cout << time_point_cast<days>(t) << '\n';     // 1970-01-01
  std::cout << floor<days>(t) << '\n';               // 1969-12-31
}
```

| 函数 | 效果 | 段落 |
|---|---|---|
| `time_point_cast<To>(tp)` | 对 `time_since_epoch()` 做 `duration_cast` | ¶1–¶2 |
| `floor<To>(tp)` | 对 `time_since_epoch()` 做 `floor` | ¶3–¶4 |
| `ceil<To>(tp)` | 对 `time_since_epoch()` 做 `ceil` | ¶5–¶6 |
| `round<To>(tp)` | 对 `time_since_epoch()` 做 `round`；`To::rep` 不能是浮点 | ¶7–¶8 |

四个函数都只要求 `ToDuration` 是 duration 的特化。它们只改变精度，不改变时钟；跨时钟要用 `clock_cast`（[[time.clock]]）。

`time_point_cast` 用的是 `duration_cast`，向零截断。纪元之前的时刻 `time_since_epoch()` 为负，向零截断就是向未来取整。上面的例子里，1969 年 12 月 31 日 18 点被截断成了 1970 年 1 月 1 日。

所以取日期部分一律用 `floor<days>`，`sys_time` 和 `local_time` 都一样。[[time.cal]] 中 `year_month_day{floor<days>(tp)}` 是标准写法。

## 常见陷阱

!!! pitfall "默认的 Duration 由实现决定"
    `time_point<system_clock>` 的精度是 `system_clock::duration`：libc++ 是微秒，libstdc++ 是纳秒，MSVC 是 100 纳秒。不指定单位就把 `time_since_epoch().count()` 写进文件或网络，换一个标准库读回来就错了。存储之前先用 `floor<seconds>` 或 `time_point_cast<milliseconds>` 转换到一个确定的单位。

!!! pitfall "time_point::max() 不适合当哨兵"
    很多代码用 `time_point::max()` 表示永不超时。但等待函数内部常常要计算 `deadline - now()`，或者换算到另一个时钟，`max()` 一参与这类运算就会溢出，结果是未定义行为。标准库实现对 `wait_until(max())` 通常有特殊处理，自己写的时间运算没有。
