---
title: 时间库
summary: 第 30 章导读——<chrono> 的三层结构（duration / time_point / clock）与 C++20 加上的历法、时区、格式化层；概要里那些类型别名的位宽为什么这样定；C++26 的散列支持；libc++ 的实现现状
status: done
covers: time.general, time.syn, time.hash
papers: N2661, P0355R7, P1361R2, P2592R3
related: time.duration, time.point, time.clock, time.cal, time.zone, time.format, ctime.syn, ratio, thread.req.timing
tags: 标准库, chrono, 时间, 导读
updated: 2026-10-18
---

第 30 章 [time] 几乎全部是 `<chrono>`，外加 C 的 `<ctime>`。`<chrono>` 要解决的核心问题只有一个：**让"时间量"带上单位，并让编译器检查单位**。C 接口里，`sleep(5)` 是 5 秒还是 5 毫秒、`time_t` 和 `clock_t` 能不能相减，全靠文档和约定；`<chrono>` 把这些信息编码进类型，用错单位会编译失败，换单位时乘除系数由编译器在编译期算好。

## 本章地图（[time.general] ¶1）

¶1 的表 130 把本章分成 13 个子条款：

| 子条款 | 内容 | 头文件 | 本站笔记 |
|---|---|---|---|
| [time.clock.req] | *Cpp17Clock* / *Cpp17TrivialClock* 要求 | — | [[time.clock.req]] |
| [time.traits] | `treat_as_floating_point`、`duration_values`、`common_type` 特化、`is_clock` | `<chrono>` | [[time.traits]] |
| [time.duration] | `duration`：带单位的时间长度 | `<chrono>` | [[time.duration]] |
| [time.point] | `time_point`：某个时钟上的时刻 | `<chrono>` | [[time.point]] |
| [time.clock] | `system_clock`、`steady_clock`、`utc_clock`、`tai_clock`、`gps_clock`、`file_clock`、`local_t`、`clock_cast` | `<chrono>` | [[time.clock]] |
| [time.cal] | 公历：`year`、`month`、`day`、`weekday`、`year_month_day` 等 15 个类型与 `/` 语法 | `<chrono>` | [[time.cal]] |
| [time.hms] / [time.12] | `hh_mm_ss`；`is_am`、`make12` 等 | `<chrono>` | [[time.hms]] |
| [time.zone] | IANA 时区数据库、`time_zone`、`zoned_time`、闰秒 | `<chrono>` | [[time.zone]] |
| [time.format] / [time.parse] | `std::format` 的 chrono 格式说明；`parse` 操纵符 | `<chrono>` | [[time.format]]、[[time.parse]] |
| [time.hash] | 各 chrono 类型的 `std::hash` 特化 {{c++26}} | `<chrono>` | 本页 |
| [ctime.syn] | C 的时间函数 | `<ctime>` | [[ctime.syn]] |

与本章紧密相关、但不在本章的内容：

- 线程库里所有 `_for` / `_until` 超时函数的语义在 [[thread.req.timing]]，它规定了"时钟被调整时等待函数该怎么办"，本站在 [[time.clock]] 中讨论；
- `ratio` 在 [[ratio]]（第 21 章元编程库），它是 `duration` 计次周期的载体；
- `filesystem::file_time_type` 就是 `time_point<file_clock>`，见 [[fs.filesystem.syn]]；
- `<locale>` 里的 `time_get` / `time_put` 是另一套与 `<chrono>` 无关的老接口（[[category.time]]）。

## 三层核心 + 三层扩展

C++11 的 `<chrono>`（[[N2661]]）只有三样东西，它们至今仍是全章的骨架：

```text
clock ──now()──▶ time_point<Clock, Duration> ──time_since_epoch()──▶ duration<Rep, Period>
                    "时刻：距纪元多远"                              "长度：计次数 × 计次周期"
```

- **[[time.duration|duration]]**：一个算术值 `count()` 加一个编译期有理数周期 `Period`。`milliseconds{1500}` 存的是整数 1500，"毫秒"只存在于类型里。
- **[[time.point|time_point]]**：一个 duration 加一个时钟类型。时钟类型只是"标签"，决定了这段 duration 从哪里量起（[[g:clock-epoch]]）。不同时钟的 time_point 是不同类型，不能比较、不能相减。
- **[[time.clock|clock]]**：提供 `now()` 的类型，满足 [[g:cpp17clock]]。

C++20 的 [[P0355R7]] 在这个骨架上加了三层，几乎原样采纳了 Howard Hinnant 的 date/tz 库：

- **历法**（[[time.cal]]）：`year_month_day` 等"字段式"日期，与 `sys_days`（以天计的 `time_point`）互相转换。关键设计是 `system_clock` 被规定为 [[g:unix-time]]——每天恰好 86400 秒——所以日期与时刻之间的换算是纯算术，不需要查表。
- **时区**（[[time.zone]]）：IANA 数据库、`local_time` 与 `sys_time` 之间的换算、闰秒与 `utc_clock`。
- **文本 I/O**（[[time.format]]、[[time.parse]]）：`std::format` 的 `%Y-%m-%d` 风格格式说明（[[P1361R2]]），以及对称的 `parse`。

## 概要（[time.syn]）里值得注意的几处

`<chrono>` 的概要有九百多行，绝大部分只是把各子条款的声明汇总在一起。下面几处只在概要里规定，没有对应的正文段落。

### 便利别名的最小位宽

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

这些数字不是随便挑的：

- 从 `nanoseconds` 到 `hours`，位宽保证每个类型至少能表示 **±292 年**左右（2⁶³ ns ≈ 292 年，2⁵⁴ µs ≈ 571 年，2³⁴ s ≈ 544 年……）。换句话说，任何一个"小单位"别名都至少覆盖 1970 年前后几百年。
- `days`、`months`、`years` 的位宽则是为了覆盖 `year` 的取值范围 [-32767, 32767]（[[time.cal]]）：2²⁴ 天 ≈ 45 900 年，2¹⁹ 个月 ≈ 43 690 年，2¹⁶ = 65 536 年。
- `years` 的周期是 `146097/400` 天，即公历的平均年长（400 年 146097 天）；`months` 是它的 1/12。所以 `years{1}` **不是** 365 天也不是 366 天，而是 365.2425 天 = 31 556 952 秒。它们是"平均长度"，用于 `sys_days` 上会得到带时分秒的奇怪结果，正确的"加一年"应在 `year_month_day` 上做（见 [[time.cal]]）。

`nanoseconds` 只保证 ±292 年是本章最常见的溢出来源，详见 [[time.duration]] 的陷阱一节。

### 字面量与常量

- 时长字面量 `h`、`min`、`s`、`ms`、`us`、`ns` 以及日期字面量 `d`、`y` 都在 `std::literals::chrono_literals` 中，两个 `inline namespace` 让 `using namespace std::literals;` 或 `using namespace std::chrono_literals;` 都能引入它们。
- 概要末尾还有一句 `namespace std::chrono { using namespace literals::chrono_literals; }`——所以 `using namespace std::chrono;` **也会**把字面量带进来，这就是大多数示例只写这一行的原因。
- 历法常量：`last`（`last_spec` 类型）、`Sunday` … `Saturday`（`weekday`）、`January` … `December`（`month`），都是 `inline constexpr` 变量。

`s` 后缀与 `std::string` 的 `""s` 并不冲突：前者只接受数字字面量，后者只接受字符串字面量（[time.duration.literals] ¶8）。

## 散列支持（[time.hash]）{{c++26}}

C++26 通过 [[P2592R3]] 给 chrono 的值类型加上了 `std::hash` 特化，之前想把 `seconds` 或 `year_month_day` 放进 `unordered_set` 必须自己写散列器。

- ¶1：`hash<duration<Rep, Period>>` **当且仅当** `hash<Rep>` 启用（[[unord.hash]]）时启用；成员函数不保证 `noexcept`（`Rep` 可以是会抛异常的类类型）。
- ¶2：`hash<time_point<Clock, Duration>>` 当且仅当 `hash<Duration>` 启用时启用。
- ¶3：15 个历法类型的特化总是启用。注里特别强调：即使对 `ok()` 为 `false` 的对象调用，它们也满足 *Cpp17Hash* 要求——历法类型允许存放无效值（如 `February/30`），散列不能因此出错。
- ¶4：`hash<zoned_time<Duration, TimeZonePtr>>` 当且仅当 `hash<Duration>` 与 `hash<TimeZonePtr>` 都启用时启用。
- ¶5：`hash<leap_second>` 总是启用。

散列与相等比较的关系需要留意：`duration` 的 `==` 是**跨单位**比较（`1s == 1000ms`），但 `hash<seconds>` 与 `hash<milliseconds>` 是两个不同的特化，标准不要求 `hash<seconds>{}(1s) == hash<milliseconds>{}(1000ms)`。同一个无序容器里键的类型是固定的，所以这不会造成问题；只是不要指望跨类型的散列值一致。

```cpp title="chrono-hash.cpp" ok
#include <chrono>
#include <unordered_set>
#include <cassert>
using namespace std::chrono;

int main() {
    std::unordered_set<seconds> s{1s, 2s, 1s};
    assert(s.size() == 2);
    std::unordered_set<year_month_day> d{2024y/February/29, 2024y/February/30}; // 后者 !ok()，照样能散列
    assert(d.size() == 2);
}
```

## libc++ 的实现现状

本站用 Homebrew Clang 23 + libc++ 验证例子。截至写作时，本机这套 libc++ 的情况是：

| 部分 | 状态 |
|---|---|
| `duration`、`time_point`、`system_clock`、`steady_clock`、`file_clock` | 完整 |
| 历法类型、`hh_mm_ss`、`time.12` 函数 | 完整 |
| `std::format` 的 chrono 格式化、`operator<<` | 已实现（时区相关部分除外） |
| `hash` 特化（[time.hash]） | 已实现（`unordered_set<seconds>` 可用） |
| `utc_clock`、`tai_clock`、`gps_clock`、`tzdb`、`time_zone`、`zoned_time`、`leap_second` | 头文件存在，但本机构建的 `__config_site` 定义 `_LIBCPP_HAS_TIME_ZONE_DATABASE` 为 0，这些名字**不可用**；此外 libc++ 中这部分还受 `_LIBCPP_HAS_EXPERIMENTAL_TZDB` 控制，即属于需要 `-fexperimental-library` 的实验特性 |
| `clock_cast`、`clock_time_conversion` | 未实现 |
| `parse`、`from_stream` | 未实现 |

因此 [[time.zone]] 和 [[time.parse]] 两页的例子无法在本机运行，页面上会单独说明；涉及这些设施的例子请在 Compiler Explorer 上用较新的 GCC（libstdc++）或 MSVC 尝试。

## 历史脉络

| 版本 | 变化 |
|---|---|
| C++11 | `duration`、`time_point`、`system_clock`、`steady_clock`、`high_resolution_clock`（[[N2661]]） |
| C++14 | 时长字面量 `h`、`min`、`s`、`ms`、`us`、`ns`；更多 `constexpr` |
| C++17 | `floor`、`ceil`、`round`、`abs` |
| C++20 | 历法、时区、`utc_clock`/`tai_clock`/`gps_clock`/`file_clock`、`local_t`、`clock_cast`、`hh_mm_ss`、`days`/`weeks`/`months`/`years`、`is_clock`（[[P0355R7]]）；`std::format` 集成（[[P1361R2]]）；`system_clock` 被规定为 Unix 时间 |
| C++23 | chrono 格式化默认改用 "C" locale，只有 `L` 选项才用本地化（作为对 C++20 的缺陷修复） |
| C++26 | `hash` 支持（[[P2592R3]]） |
| C++23 之后的新措辞 | `<ctime>` 对齐 C23：新增 `timegm`、`gmtime_r`、`localtime_r`、`timespec_getres`；`asctime`、`ctime` 移入附录 D（[[depr.ctime]]） |

## 小结

- 记住骨架：**duration = 计次数 + 周期**，**time_point = duration + 时钟**，**clock = 纪元 + now()**。
- `system_clock` 就是 Unix 时间，这是历法层能做纯算术换算的前提。
- 概要里的位宽保证：小单位别名至少 ±292 年，`days`/`months`/`years` 覆盖 ±32767 年。
- C++26 起 chrono 值类型可以直接作为无序容器的键。
- libc++ 尚缺时区数据库（本机构建中关闭）、`clock_cast` 与 `parse`。
