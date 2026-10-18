---
title: 类模板 hh_mm_ss 与 12/24 小时制
summary: hh_mm_ss 把一个 duration 拆成时、分、秒和十进制小数秒；fractional_width 与 precision 如何由 Duration 的周期算出；负时长的表示；is_am / is_pm / make12 / make24
status: done
covers: *, time.12
related: time.duration, time.point, time.cal, time.format
tags: 标准库, chrono, hh_mm_ss
updated: 2026-10-18
---

`hh_mm_ss` 解决的是"把一段时长显示成 `HH:MM:SS.fff`"时的拆分问题。拆分本身不难，难的是**小数秒该有几位**：毫秒精度要 3 位，微秒要 6 位，那 1/3 秒呢？1/8 秒呢？`hh_mm_ss` 在编译期根据 `Duration` 的周期算出所需的十进制位数，并选一个能精确（或尽量精确）表示它的类型。

最常见的用法是取"一天中的时刻"：

```cpp
auto dp  = floor<days>(tp);          // 日期部分
hh_mm_ss tod{tp - dp};               // 时间部分：时、分、秒、小数秒
```

## 概述（[time.hms.overview]）

```cpp
template<class Duration> class hh_mm_ss {
public:
  static constexpr unsigned fractional_width = see below;
  using precision                            = see below;

  constexpr hh_mm_ss() noexcept : hh_mm_ss{Duration::zero()} {}
  constexpr explicit hh_mm_ss(Duration d);

  constexpr bool is_negative() const noexcept;
  constexpr chrono::hours hours() const noexcept;
  constexpr chrono::minutes minutes() const noexcept;
  constexpr chrono::seconds seconds() const noexcept;
  constexpr precision subseconds() const noexcept;

  constexpr explicit operator precision() const noexcept;
  constexpr precision to_duration() const noexcept;
private:
  bool is-neg; chrono::hours h_; chrono::minutes m_; chrono::seconds s_; precision ss_;
};
```

¶1：`hh_mm_ss` 把 duration 拆成"时:分:秒"以及可能的"小数秒"，小数秒的单位是 10 的非正整数次幂秒。`Duration` 决定拆分的精度。负时长用单独的 `is_negative()` 表示，**各字段总是非负的**。

¶2：若 `Duration` 不是 duration 的特化，程序非良构。

与历法类型不同，`hh_mm_ss` 的默认构造函数是**有值的**：等价于用 `Duration::zero()` 构造。

`hours()` 没有上限：`hh_mm_ss{25h + 3min}.hours()` 是 `25h`。`hh_mm_ss` 拆的是**时长**，不是"一天中的时刻"；只是在 `tp − floor<days>(tp)` 这种用法下，时长恰好落在 [0, 24h)。

## fractional_width 与 precision（[time.hms.members] ¶1–¶2）

¶1：`fractional_width` 是 `precision` 所表示的小数位数：在 [0, 18] 中取**最小**的整数，使 `precision` 能精确表示 `Duration` 的所有值；不存在这样的值时取 6。

¶2：`precision` 是

```cpp
duration<common_type_t<Duration::rep, seconds::rep>, ratio<1, 10^fractional_width>>
```

规则的直觉：周期 `num/den`（约分后）能写成有限位十进制小数，当且仅当 `den` 的质因子只有 2 和 5；位数是 `den` 中 2 和 5 的指数的最大值。表 132 的例子：

| `Duration` | `fractional_width` | `Duration{1}` 的小数部分 |
|---|---|---|
| `hours`、`minutes`、`seconds` | 0 | — |
| `milliseconds` | 3 | 0.001 |
| `microseconds` | 6 | 0.000001 |
| `nanoseconds` | 9 | 0.000000001 |
| `ratio<1, 2>` | 1 | 0.5 |
| `ratio<1, 4>` | 2 | 0.25 |
| `ratio<1, 8>` | 3 | 0.125 |
| `ratio<1, 3>`、`ratio<1, 6>`、`ratio<1, 7>`、`ratio<1, 9>` | 6（无法精确表示） | 0.333333 等 |
| `ratio<756, 625>` | 4 | 0.2096 |

最后一行：625 = 5⁴，所以 4 位足够，`756/625 = 1.2096`。

两个推论：

- `hh_mm_ss<minutes>::precision` 是 `seconds`（`fractional_width` 为 0，周期 `ratio<1,1>`），不是 `minutes`。
- 周期为 1/3 秒时 `precision` 是微秒，`subseconds()` 与 `to_duration()` 都会**截断**到微秒：`hh_mm_ss` 对这类周期是有损的。

## 构造（¶3–¶4）

¶3：`explicit hh_mm_ss(Duration d)`：

- ¶3.1：`is-neg` 初始化为 `d < Duration::zero()`；令 *ABS_D* 为 `d` 的绝对值；
- ¶3.2–¶3.4：`h_`、`m_`、`s_` 依次用 `duration_cast` 从 *ABS_D* 中取出整数时、分、秒（每一步减去前面已取出的部分）；
- ¶3.5：若 `precision::rep` 是浮点，`ss_` 是剩余部分本身；否则是 `duration_cast<precision>(剩余部分)`。注 1：`precision::rep` 是整数且周期为 `ratio<1>` 时，`subseconds()` 总是 `0s`。

¶4 *Postconditions*：浮点情形 `to_duration()` 返回 `d`；否则返回 `duration_cast<precision>(d)`。

先取绝对值再拆分，是为了让各字段都非负：`-90min` 拆成"负号 + 1 时 30 分"，而不是"−1 时 −30 分"或"−2 时 +30 分"。

## 观察器（¶5–¶11）

- ¶5–¶9：`is_negative()`、`hours()`、`minutes()`、`seconds()`、`subseconds()` 返回对应字段。
- ¶10：`to_duration()`：各字段之和，`is-neg` 时取负。
- ¶11：`explicit operator precision()` 返回 `to_duration()`。

## 输出（[time.hms.nonmembers]）

¶1：`os << hms` 等价于 `os << format(os.getloc(), "{:L%T}", hms)`。`%T` 是 `%H:%M:%S`，`%S` 会带上 `fractional_width` 位小数，负值前加 `-`（[[time.format]] ¶4）。

¶2 的例子：

```cpp title="hms.cpp" ok
#include <chrono>
#include <iostream>
using namespace std::chrono;

int main() {
    for (auto ms : {-4083007ms, 4083007ms, 65745123ms}) {
        hh_mm_ss hms{ms};
        std::cout << hms << '\n';          // -01:08:03.007 / 01:08:03.007 / 18:15:45.123
    }
    std::cout << hh_mm_ss{65745s} << '\n';  // 18:15:45

    using third = duration<int, std::ratio<1, 3>>;
    hh_mm_ss t{third{4}};                   // 4/3 秒
    static_assert(decltype(t)::fractional_width == 6);
    std::cout << t << ' ' << t.to_duration() << '\n';   // 00:00:01.333333 1333333µs
}
```

`hh_mm_ss{ms}` 用到了类模板实参推导：`Duration` 由构造函数实参推导为 `milliseconds`。

!!! impl "libc++：小时数 ≥ 24 时格式化抛异常"
    截至写作时，libc++ 格式化 `hours()` 不小于 24 的 `hh_mm_ss` 时抛出 `format_error`（消息为 "Formatting a hour needs a valid value"）。而直接格式化 duration `25h + 3min` 用 `%T` 时，libc++ 输出 `01:03:00`——按 [[time.format]] ¶6 把 duration 解释为"自午夜起经过的时间"并对 24 小时取模。标准对这两种情形的写法都不够明确；需要显示"总时长"时，自己拼接 `hours().count()` 更可靠。

## 12/24 小时制函数（[time.12]）

¶1：这些函数帮助在 12 小时制与 24 小时制的时刻之间转换。全部是 `constexpr noexcept`。

| 函数 | 返回 | 段落 |
|---|---|---|
| `is_am(h)` | `0h <= h && h <= 11h` | ¶2 |
| `is_pm(h)` | `12h <= h && h <= 23h` | ¶3 |
| `make12(h)` | `h` 的 12 小时制等价值，范围 [1h, 12h]；`h` 不在 [0h, 23h] 时未指明 | ¶4 |
| `make24(h, is_pm)` | 12 小时制的 `h`（[1h, 12h]）加上午/下午标志，转换为 [0h, 23h]；`h` 不在 [1h, 12h] 时未指明 | ¶5 |

边界：午夜 `0h` 是 `is_am`，`make12(0h) == 12h`（12 AM）；正午 `12h` 是 `is_pm`，`make12(12h) == 12h`（12 PM）；`make24(12h, false) == 0h`，`make24(12h, true) == 12h`。`is_am` 与 `is_pm` 对 [0h, 23h] 之外的值都返回 `false`。

```cpp title="time12.cpp" ok
#include <chrono>
using namespace std::chrono;

static_assert(is_am(0h) && !is_pm(0h) && make12(0h) == 12h);    // 午夜 = 12 AM
static_assert(is_pm(12h) && make12(12h) == 12h);                // 正午 = 12 PM
static_assert(make12(13h) == 1h);
static_assert(make24(12h, false) == 0h && make24(12h, true) == 12h);
static_assert(!is_am(24h) && !is_pm(24h));

int main() {}
```

## 小结

- `hh_mm_ss` 拆的是时长：各字段非负，符号单独存；`hours()` 可超过 23。
- `fractional_width` = 能精确表示周期的最少小数位（最多 18），否则 6；`precision` 是对应的 10⁻ⁿ 秒 duration。
- 典型用法：`hh_mm_ss{tp - floor<days>(tp)}` 取一天中的时刻。
- `make12`/`make24` 处理 12 AM/12 PM 的边界；超出范围的输入结果未指明。
