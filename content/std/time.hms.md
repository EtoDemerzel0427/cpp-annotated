---
title: 类模板 hh_mm_ss 与 12/24 小时制
summary: hh_mm_ss 把一段时长拆成时、分、秒和十进制小数秒；小数位数怎样由 Duration 的周期算出，负时长怎样表示；以及 is_am、is_pm、make12、make24 四个 12/24 小时制函数。
status: done
covers: *, time.12
related: time.duration, time.point, time.cal, time.format
tags: 标准库, chrono, hh_mm_ss
updated: 2026-10-19
---

!!! tldr
    - `hh_mm_ss{d}` 把时长 `d` 拆成时、分、秒和小数秒，最常见的用法是 `hh_mm_ss{tp - floor<days>(tp)}`，取一天之内的时刻。
    - 小数秒的位数 `fractional_width` 在编译期算出：取能精确表示 `Duration` 所有值的最少十进制位数（不超过 18），做不到时取 6。
    - 负时长用单独的 `is_negative()` 表示，各字段总是非负的；`hours()` 没有上限，可以超过 23。
    - `make12(0h)` 是 `12h`（午夜是 12 AM），`make24(12h, false)` 是 `0h`；超出范围的输入，结果未指定。

## 把时长拆成字段

```cpp run ok title="hms.cpp"
#include <chrono>
#include <iostream>
using namespace std::chrono;

int main() {
  for (auto ms : {-4083007ms, 4083007ms, 65745123ms}) {
    hh_mm_ss hms{ms};
    std::cout << hms << '\n';      // -01:08:03.007 / 01:08:03.007 / 18:15:45.123
  }
  std::cout << hh_mm_ss{65745s} << '\n';   // 18:15:45

  sys_seconds tp = sys_days{2024y/March/15} + 13h + 5min;
  hh_mm_ss tod{tp - floor<days>(tp)};      // 一天之内的时刻
  std::cout << tod.hours() << ' ' << tod.minutes() << '\n';   // 13h 5min
}
```

前四行输出就是 [[time.hms.nonmembers#2]] 的例子。`hh_mm_ss hms{ms}` 用到了类模板实参推导，`Duration` 由实参推导为 `milliseconds`。

把时长拆成时、分、秒本身不难，难在小数秒该有几位：毫秒要 3 位，微秒要 6 位，1/3 秒和 1/8 秒呢？`hh_mm_ss` 在编译期根据周期算出位数，并选一个能精确表示（或者尽量精确表示）它的类型。

## 概述 [time.hms.overview]

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

¶1 `hh_mm_ss` 把一段时长拆成"时:分:秒"，可能还有小数秒，小数秒的单位是 10 的非正整数次幂秒。`Duration` 决定拆分的精度。负时长由 `is_negative()` 表示，各字段即使在时长为负时也总是非负的。

¶2 如果 `Duration` 不是 duration 的特化，程序非良构。

和历法类型不同，`hh_mm_ss` 的默认构造函数有确定的值，等价于用 `Duration::zero()` 构造。

`hh_mm_ss` 拆的是时长，不是一天中的时刻，所以 `hours()` 没有上限：`hh_mm_ss{25h + 3min}.hours()` 是 `25h`。只有在 `tp - floor<days>(tp)` 这种用法下，时长才恰好落在 0 到 24 小时之间。

## 小数位数与 precision [time.hms.members]

¶1 `fractional_width` 是 `precision` 表示的小数位数：在 0 到 18 之间取最小的整数，使 `precision` 能精确表示 `Duration` 的所有值；不存在这样的整数时取 6。

¶2 `precision` 是

```cpp
duration<common_type_t<Duration::rep, seconds::rep>, ratio<1, 10^fractional_width>>
```

背后的道理是：约分后的周期 `num/den` 能写成有限位的十进制小数，当且仅当 `den` 的质因子只有 2 和 5；需要的位数是 `den` 中 2 和 5 的指数里较大的那个。表 132 列出了一些例子：

| `Duration` | `fractional_width` | `Duration{1}` 的小数部分 |
|---|---|---|
| `hours`、`minutes`、`seconds` | 0 | 无 |
| `milliseconds`、`microseconds`、`nanoseconds` | 3、6、9 | 0.001 等 |
| 周期 `ratio<1, 2>`、`ratio<1, 4>`、`ratio<1, 8>` | 1、2、3 | 0.5、0.25、0.125 |
| 周期 `ratio<1, 5>`、`ratio<1, 10>` | 1 | 0.2、0.1 |
| 周期 `ratio<1, 3>`、`ratio<1, 6>`、`ratio<1, 7>`、`ratio<1, 9>` | 6，无法精确表示 | 0.333333 等 |
| 周期 `ratio<756, 625>` | 4 | 0.2096 |

最后一行：625 是 5⁴，所以 4 位足够，756/625 等于 1.2096。

由此有两个推论：

- `hh_mm_ss<minutes>` 的 `fractional_width` 是 0，`precision` 的周期是 `ratio<1>`。它是以秒为单位的 duration，不是 `minutes`；本机 libc++ 上它就是 `seconds`。
- 周期为 1/3 秒时，`precision` 是微秒，`subseconds()` 和 `to_duration()` 都会截断到微秒。对这类周期，`hh_mm_ss` 是有损的。

```cpp run ok title="hms-third.cpp"
#include <chrono>
#include <iostream>
using namespace std::chrono;

int main() {
  using third = duration<int, std::ratio<1, 3>>;
  hh_mm_ss t{third{4}};                     // 4/3 秒
  static_assert(decltype(t)::fractional_width == 6);
  std::cout << t << ' ' << t.to_duration() << '\n';   // 00:00:01.333333 1333333µs
}
```

### 构造（¶3–¶4）

¶3 `explicit hh_mm_ss(Duration d)` 的拆分步骤是：

- ¶3.1 记下 `d` 是否为负，令 *ABS_D* 为 `d` 的绝对值；
- ¶3.2–¶3.4 依次用 `duration_cast` 从 *ABS_D* 中取出整小时、整分钟、整秒，每一步先减去已经取出的部分；
- ¶3.5 剩余部分就是小数秒：`precision::rep` 是浮点类型时原样保存，否则用 `duration_cast<precision>` 截断。注 1 指出，`precision::rep` 是整数而周期是 `ratio<1>` 时，`subseconds()` 总是 `0s`。

先取绝对值再拆分，是为了让各字段都非负：`-90min` 拆成负号加上 1 小时 30 分，而不是 −1 小时 −30 分，也不是 −2 小时加 30 分。

¶4 构造之后，`precision::rep` 是浮点类型时 `to_duration()` 返回 `d`，否则返回 `duration_cast<precision>(d)`。

### 观察器（¶5–¶11）

¶5 `is_negative()`、`hours()`、`minutes()`、`seconds()`、`subseconds()` 返回对应的字段。¶10 `to_duration()` 返回各字段之和，为负时取负。¶11 `explicit operator precision()` 返回 `to_duration()`。

## 输出 [time.hms.nonmembers]

¶1 `os << hms` 等价于用 `"{:L%T}"` 格式化。`%T` 即 `%H:%M:%S`，`%S` 带有 `fractional_width` 位小数，负值前面加 `-`（[[time.format]]）。

!!! impl "libc++：小时数不小于 24 时格式化抛异常"
    截至写作时，本机 libc++ 格式化 `hours()` 不小于 24 的 `hh_mm_ss` 时抛出 `format_error`，消息是 "Formatting a hour needs a valid value"。直接用 `%T` 格式化 duration `25h + 3min` 时，它输出 `01:03:00`，即把 duration 当作从午夜起经过的时间，对 24 小时取模。标准对这两种情形写得都不够明确。需要显示总时长时，自己拼接 `hours().count()` 更可靠。

## 12/24 小时制函数 [time.12]

```cpp run ok title="time12.cpp"
#include <chrono>
using namespace std::chrono;

static_assert(is_am(0h) && !is_pm(0h) && make12(0h) == 12h);  // 午夜是 12 AM
static_assert(is_pm(12h) && make12(12h) == 12h);              // 正午是 12 PM
static_assert(make12(13h) == 1h);
static_assert(make24(12h, false) == 0h && make24(12h, true) == 12h);
static_assert(!is_am(24h) && !is_pm(24h));

int main() {}
```

¶1 这些函数帮助在 12 小时制和 24 小时制之间转换，都是 `constexpr noexcept` 的。

| 函数 | 返回 | 段落 |
|---|---|---|
| `is_am(h)` | `0h <= h && h <= 11h` | ¶2 |
| `is_pm(h)` | `12h <= h && h <= 23h` | ¶3 |
| `make12(h)` | `h` 在 12 小时制下的值，范围 1h 到 12h；`h` 不在 0h 到 23h 之间时未指定 | ¶4 |
| `make24(h, is_pm)` | 把 12 小时制的 `h` 加上上午或下午的标志，换算成 0h 到 23h；`h` 不在 1h 到 12h 之间时未指定 | ¶5 |

边界情况都在午夜和正午。午夜 `0h` 属于上午，`make12(0h)` 是 `12h`；正午 `12h` 属于下午，`make12(12h)` 也是 `12h`。反过来，`make24(12h, false)` 是 `0h`，`make24(12h, true)` 是 `12h`。`is_am` 和 `is_pm` 对 0h 到 23h 之外的值都返回 `false`。
