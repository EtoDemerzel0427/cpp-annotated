---
title: 时间库
summary: 第 30 章导读：<chrono> 用 duration、time_point、clock 三个类型把时间单位编进类型系统，C++20 在此基础上加了历法、时区和格式化；概要里规定了各个时长别名的最小位宽和字面量的引入方式；C++26 给 chrono 类型加上了 std::hash。
status: done
covers: time.general, time.syn, time.hash
papers: N2661, P0355R7, P1361R2, P2592R3
related: time.duration, time.point, time.clock, time.cal, time.zone, time.format, ctime.syn, ratio, thread.req.timing
tags: 标准库, chrono, 时间, 导读
updated: 2026-10-19
---

!!! tldr
    - `<chrono>` 的骨架是三个类型：duration 是计次数乘计次周期，time_point 是 duration 加一个时钟，clock 提供纪元和 `now()`。单位写在类型里，用错单位会编译失败。
    - `system_clock` 被规定为 Unix 时间（每天恰好 86400 秒），所以 C++20 的历法类型与时刻之间可以纯算术换算。
    - `nanoseconds` 到 `hours` 的别名都保证至少覆盖约 ±292 年；`days`、`months`、`years` 覆盖 `year` 的全部取值范围 [−32767, 32767]。
    - `using namespace std::chrono;` 会顺带引入 `1s`、`500ms` 这类字面量。
    - C++26 起，`duration`、`time_point`、历法类型都有 `std::hash` 特化，可以直接作为无序容器的键。

## 为什么要把单位放进类型

```cpp run title="chrono-units.cpp" ok
#include <chrono>
using namespace std::chrono;

milliseconds timeout = 2s;          // OK：秒转毫秒只需乘 1000
// seconds s = 1500ms;              // error: 需要除法，会截断
seconds s = duration_cast<seconds>(1500ms);   // 显式截断：1s
static_assert(1s + 1ms == 1001ms);  // 不同单位可以直接相加
int main() {}
```

在 C 接口里，`sleep(5)` 是 5 秒还是 5 毫秒、`time_t` 和 `clock_t` 能否相减，全靠文档和约定。`<chrono>` 把这些信息编进类型：`milliseconds{1500}` 里只存整数 1500，毫秒这个单位存在于类型中。换单位时需要的乘除系数由编译器在编译期算出；可能丢失精度的转换必须显式写出。

## 骨架：三个核心类型

C++11 的 `<chrono>`（[[N2661]]）只有三样东西，它们至今仍是整章的骨架：

```text
clock ──now()──▶ time_point<Clock, Duration> ──time_since_epoch()──▶ duration<Rep, Period>
```

- [[time.duration|duration]]：一个算术值 `count()`，加一个编译期的有理数周期 `Period`（[[ratio]]）。
- [[time.point|time_point]]：一个 duration 加一个时钟类型。时钟类型在这里只起标签作用，说明这段 duration 从哪一刻量起，这一刻叫做时钟的纪元（[[g:clock-epoch]]）。不同时钟的 time_point 是不同的类型，不能比较，也不能相减。
- [[time.clock|clock]]：提供 `now()` 的类型，满足 [[g:cpp17clock]] 要求（[[time.clock.req]]）。

C++20 的 [[P0355R7]] 在骨架上加了三部分，基本采纳了 Howard Hinnant 的 date/tz 库：

- 历法（[[time.cal]]）：`year_month_day` 等按年月日字段存储的日期，能与 `sys_days`（以天为单位的 time_point）互相转换。`system_clock` 被规定为 [[g:unix-time]]，每天恰好 86400 秒，所以日期和时刻之间的换算是纯算术，不需要查表。
- 时区（[[time.zone]]）：IANA 时区数据库、`local_time` 与 `sys_time` 的换算、闰秒与 `utc_clock`。
- 文本 I/O（[[time.format]]、[[time.parse]]）：`std::format` 中 `%Y-%m-%d` 风格的格式说明（[[P1361R2]]），以及对应的 `parse`。

## 本章的组成（[time.general]）

¶1 本章描述 chrono 库和 C 的时间函数，表 130 列出了各子条款：

| 子条款 | 内容 | 本站笔记 |
|---|---|---|
| [time.clock.req] | *Cpp17Clock* 和 *Cpp17TrivialClock* 要求 | [[time.clock.req]] |
| [time.traits] | `treat_as_floating_point`、`duration_values`、`common_type` 特化、`is_clock` | [[time.traits]] |
| [time.duration] | 类模板 `duration` | [[time.duration]] |
| [time.point] | 类模板 `time_point` | [[time.point]] |
| [time.clock] | `system_clock`、`steady_clock`、`utc_clock`、`file_clock` 等时钟，以及 `clock_cast` | [[time.clock]] |
| [time.cal] | 公历：`year`、`month`、`year_month_day` 等类型和 `/` 语法 | [[time.cal]] |
| [time.hms]、[time.12] | `hh_mm_ss`；`is_am`、`make12` 等 12/24 小时制函数 | [[time.hms]] |
| [time.zone] | 时区数据库、`time_zone`、`zoned_time`、闰秒 | [[time.zone]] |
| [time.format]、[time.parse] | 格式化与解析 | [[time.format]]、[[time.parse]] |
| [time.hash] | 散列支持 {{c++26}} | 本页 |
| [ctime.syn] | C 的时间函数，头文件 `<ctime>` | [[ctime.syn]] |

除 [ctime.syn] 外，这些设施都在 `<chrono>` 中。几处相关内容不在本章：线程库中 `_for`、`_until` 超时函数的规则在 [[thread.req.timing]]；`filesystem::file_time_type` 就是 `time_point<file_clock>`（[[fs.filesystem.syn]]）；`<locale>` 中的 `time_get`、`time_put` 是另一套与 `<chrono>` 无关的旧接口（[[category.time]]）。

## 概要中的规定（[time.syn]）

`<chrono>` 的概要大部分只是汇总各子条款的声明，但下面几点只在概要里规定。

### 时长别名的最小位宽

```cpp
using nanoseconds  = duration<signed integer type of at least 64 bits, nano>;
using microseconds = duration<signed integer type of at least 55 bits, micro>;
using milliseconds = duration<signed integer type of at least 45 bits, milli>;
using seconds      = duration<signed integer type of at least 35 bits>;
using minutes      = duration<signed integer type of at least 29 bits, ratio<  60>>;
using hours        = duration<signed integer type of at least 23 bits, ratio<3600>>;
using days         = duration<signed integer type of at least 25 bits, ...>;
using weeks        = duration<signed integer type of at least 22 bits, ...>;
using years        = duration<signed integer type of at least 17 bits, ...>;
using months       = duration<signed integer type of at least 20 bits, ...>;
```

这些位宽是算出来的：

- 从 `nanoseconds` 到 `hours`，每个别名都至少能表示约 ±292 年（2⁶³ ns ≈ 292 年，2⁵⁴ µs ≈ 571 年，2³⁴ s ≈ 544 年）。也就是说，任何一个小单位都至少覆盖 1970 年前后几百年。
- `days`、`months`、`years` 的位宽是为了覆盖 `year` 的取值范围 [−32767, 32767]（[[time.cal]]）：2²⁴ 天约 45 900 年，2¹⁹ 个月约 43 690 年，2¹⁶ 年是 65 536 年。
- `years` 的周期是 146097/400 天，即公历的平均年长（400 年共 146097 天）；`months` 是它的 1/12。所以 `years{1}` 既不是 365 天也不是 366 天，而是 365.2425 天，即 31 556 952 秒。把它加到 `sys_days` 上会得到带时分秒的结果；按日历加一年应该在 `year_month_day` 上做（[[time.cal]]）。

`nanoseconds` 只保证 ±292 年，这是 chrono 中最常见的溢出来源，见 [[time.duration]]。

### 字面量与常量

- 时长字面量 `h`、`min`、`s`、`ms`、`us`、`ns`，以及历法字面量 `d`、`y`，都声明在 `std::inline literals::inline chrono_literals` 中，所以 `using namespace std::literals;` 和 `using namespace std::chrono_literals;` 都能引入它们。
- 概要还有一行 `namespace std::chrono { using namespace literals::chrono_literals; }`，所以 `using namespace std::chrono;` 也会引入这些字面量。大多数示例只写这一行就够了。
- 历法常量 `last`、`Sunday` 到 `Saturday`、`January` 到 `December` 都是 `inline constexpr` 变量。

后缀 `s` 与 `std::string` 的 `""s` 不冲突：前者只用于数字字面量，后者只用于字符串字面量（[[time.duration.literals#8]]）。

## 散列支持（[time.hash]）{{c++26}}

```cpp run title="chrono-hash.cpp" ok
#include <cassert>
#include <chrono>
#include <unordered_set>
using namespace std::chrono;

int main() {
  std::unordered_set<seconds> s{1s, 2s, 1s};
  assert(s.size() == 2);
  // 2024 年 2 月 30 日 !ok()，照样能散列
  std::unordered_set<year_month_day> d{
      2024y/February/29, 2024y/February/30};
  assert(d.size() == 2);
}
```

C++26 的 [[P2592R3]] 加入了这些特化。在此之前，把 `seconds` 或 `year_month_day` 放进 `unordered_set` 需要自己写散列器。

- ¶1 `hash<duration<Rep, Period>>` 当且仅当 `hash<Rep>` 启用（[[unord.hash]]）时启用。成员函数不保证 `noexcept`，因为 `Rep` 可以是会抛异常的类类型。
- ¶2 `hash<time_point<Clock, Duration>>` 当且仅当 `hash<Duration>` 启用时启用。
- ¶3 15 个历法类型的特化总是启用。注 1 指出，即使对 `ok()` 为 `false` 的对象调用，它们也满足 *Cpp17Hash* 要求。历法类型允许存放 `February/30` 这样的无效值，散列不能因此出问题。
- ¶4 `hash<zoned_time<Duration, TimeZonePtr>>` 当且仅当 `hash<Duration>` 和 `hash<TimeZonePtr>` 都启用时启用。
- ¶5 `hash<leap_second>` 总是启用。

`duration` 的 `==` 可以跨单位比较（`1s == 1000ms`），但 `hash<seconds>` 和 `hash<milliseconds>` 是两个不同的特化，标准不要求两者对相等的值给出相同的散列值。一个无序容器的键类型是固定的，所以这不会出错，只是不能指望跨类型的散列值一致。

## libc++ 的实现现状

本站用 Homebrew Clang 23 + libc++ 验证例子。本机的情况是：

| 部分 | 状态 |
|---|---|
| `duration`、`time_point`、`system_clock`、`steady_clock`、`file_clock` | 可用 |
| 历法类型、`hh_mm_ss`、12/24 小时制函数 | 可用 |
| chrono 的 `std::format` 和 `operator<<` | 可用（时区相关部分除外） |
| `hash` 特化 | 可用 |
| `utc_clock`、`tai_clock`、`gps_clock`、`tzdb`、`time_zone`、`zoned_time`、`leap_second` | 不可用：本机构建的 `__config_site` 把 `_LIBCPP_HAS_TIME_ZONE_DATABASE` 定义为 0，加 `-fexperimental-library` 也一样 |
| `clock_cast`、`parse` | 未实现 |

所以 [[time.zone]] 和 [[time.parse]] 的例子无法在本机运行，相关页面会单独说明。这些例子可以在 Compiler Explorer 上用较新的 GCC（libstdc++）或 MSVC 试验。

## 演进

| 版本 | 变化 |
|---|---|
| C++11 | `duration`、`time_point`、`system_clock`、`steady_clock`、`high_resolution_clock`（[[N2661]]） |
| C++14 | 时长字面量；更多函数成为 `constexpr` |
| C++17 | `floor`、`ceil`、`round`、`abs` |
| C++20 | 历法、时区、`utc_clock` 等新时钟、`clock_cast`、`hh_mm_ss`、`days` 到 `years` 的别名、`is_clock`（[[P0355R7]]）；与 `std::format` 集成（[[P1361R2]]）；`system_clock` 被规定为 Unix 时间 |
| C++23 | chrono 格式化默认改用 "C" locale，只有 `L` 选项才使用本地化格式（作为对 C++20 的缺陷修复） |
| C++26 | `hash` 支持（[[P2592R3]]） |
| C++23 之后的新措辞 | `<ctime>` 与 C23 对齐：新增 `timegm`、`gmtime_r`、`localtime_r`、`timespec_getres`；`asctime`、`ctime` 移入附录 D（[[depr.ctime]]） |
