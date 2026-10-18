---
title: 时钟
summary: system_clock（Unix 时间）、steady_clock（单调）、high_resolution_clock（别名）、utc/tai/gps_clock（闰秒与三种纪元）、file_clock、伪时钟 local_t，以及 clock_time_conversion / clock_cast 如何经由 sys 或 utc 中转在任意两个时钟之间换算；sleep_for 与时钟调整
status: done
covers: *
papers: P0355R7
related: time.clock.req, time.point, time.zone, time.cal, thread.req.timing, fs.filesystem.syn, ctime.syn
tags: 标准库, chrono, 时钟, 闰秒, UTC
updated: 2026-10-18
---

本节定义标准提供的全部时钟。按用途可以分成三组：

| 组 | 时钟 | 回答的问题 |
|---|---|---|
| 测量间隔 | `steady_clock`（以及可能是它别名的 `high_resolution_clock`） | "这段代码跑了多久？" |
| 民用时间 | `system_clock`、`utc_clock`、`tai_clock`、`gps_clock`、`file_clock` | "现在几点？这个文件什么时候改的？" |
| 无时区的钟面时间 | `local_t`（伪时钟） | "当地时间 8:00"——还不知道是哪里的当地 |

¶1（[time.clock.general]）：本节定义的类型都满足 *Cpp17TrivialClock* 要求（[[time.clock.req]]），除非另有说明。"另有说明"的是 `utc_clock`、`tai_clock`、`gps_clock`（`now()` 可能抛异常）和 `local_t`（根本不是时钟）。

## system_clock（[time.clock.system]）

```cpp
class system_clock {
public:
  using rep        = see below;
  using period     = ratio<unspecified, unspecified>;
  using duration   = chrono::duration<rep, period>;
  using time_point = chrono::time_point<system_clock>;
  static constexpr bool is_steady = unspecified;
  static time_point now() noexcept;
  static time_t     to_time_t  (const time_point& t) noexcept;
  static time_point from_time_t(time_t t) noexcept;
};
```

### Unix 时间（[time.clock.system.overview] ¶1）

¶1：`system_clock` 代表系统范围的实时时钟（墙上时间）。`sys_time<Duration>` 度量自 1970-01-01 00:00:00 UTC 起、**不计闰秒**的时间——即 [[g:unix-time]]。这一规定让 `sys_time` 与历法类型（[[time.cal]]）之间可以高效映射。

例子给出两个数值：`sys_seconds{sys_days{1970y/January/1}}.time_since_epoch()` 是 `0s`；`sys_seconds{sys_days{2000y/January/1}}.time_since_epoch()` 是 `946'684'800s`，恰好是 `10'957 * 86'400s`——30 年里每一天都是 86400 秒，尽管期间实际插入了 22 个闰秒。

C++11 时标准只说 system_clock 是"墙上时间"，纪元未指明（虽然所有实现都用 Unix 纪元）。C++20（[[P0355R7]]）把它钉死为 Unix 时间，这是整个历法层成立的前提：`sys_days` 与 `year_month_day` 的互转只是一段纯算术，不用查闰秒表。

"不计闰秒"的代价是：闰秒那一刻在 `sys_time` 里**没有表示**。2016-12-31 23:59:60 UTC 这一秒，`sys_time` 无法区分它与下一秒 00:00:00。需要区分时用 `utc_clock`。

### 成员（[time.clock.system.members]）

- ¶1：`rep` 是未指明的类型，*Constraints*：`system_clock::duration::min() < system_clock::duration::zero()`。注 1：这意味着 `rep` 有符号——1970 年以前的时刻必须能表示。
- ¶2–¶3：`to_time_t` / `from_time_t` 在 `time_t` 与 `time_point` 之间转换，两者都限制到较粗的精度；是舍入还是截断由实现定义（{{impl}}）。这对函数是与 C 接口（[[ctime.syn]]）交互的桥梁。

`is_steady` 是未指明的，但在主流实现上都是 `false`：管理员手动改时间、NTP 校时都可能让它跳变（夏令时不影响它——它表示的是 UTC）。

### 流与解析（[time.clock.system.nonmembers]）

- ¶1–¶3：`os << sys_time<Duration>` 等价于 `os << format(os.getloc(), "{:L%F %T}", tp)`。*Constraints*：`Duration::rep` 不是浮点，且 `Duration{1} < days{1}`——精度粗于一天的 `sys_time` 走下一个重载。
- ¶4–¶5：`os << sys_days` 输出 `year_month_day{dp}`，即 `2024-02-29` 这样的日期。
- ¶6–¶7：`from_stream` 按 [[time.parse]] 解析；若格式中用了 `%z` 并成功解析出 UTC 偏移，会**从结果中减去**这个偏移——解析 `2024-01-01 08:00:00 +0800` 得到的 `sys_time` 是 00:00 UTC。

```cpp title="sys-clock.cpp" ok
#include <chrono>
#include <ctime>
#include <iostream>
using namespace std::chrono;

int main() {
    static_assert(system_clock::duration::min() < system_clock::duration::zero());
    std::cout << sys_seconds{946'688'523s} << '\n';        // 2000-01-01 01:02:03
    std::cout << sys_days{2024y/February/last} << '\n';    // 2024-02-29
    std::time_t c = system_clock::to_time_t(sys_seconds{0s});
    std::cout << c << '\n';                                // 0
}
```

## utc_clock（[time.clock.utc]）

```cpp
class utc_clock {
public:
  using rep = a signed arithmetic type;
  // period, duration, time_point, is_steady 同上
  static time_point now();
  template<class Duration>
    static sys_time<common_type_t<Duration, seconds>> to_sys(const utc_time<Duration>& t);
  template<class Duration>
    static utc_time<common_type_t<Duration, seconds>> from_sys(const sys_time<Duration>& t);
};
```

### 计入闰秒（overview ¶1–¶2）

¶1：与 `sys_time` 不同，`utc_clock` 及其 `utc_time` 计入闰秒，同样从 1970-01-01 00:00:00 UTC 起算。注 1 补充：UTC 本身是从 1972-01-01 00:00:10 TAI 开始的，需要的话可以加减 63'072'000s 换算到那个起点。例子：2000-01-01 的 `utc_time` 是 `946'684'822s`，比 `sys_time` 多 22 秒——1972 年到 2000 年插入的闰秒数。

¶2：除非实现能保证 `now()` 不传播异常，否则 `utc_clock` 不是 *Cpp17TrivialClock*。注 2：`noexcept(from_sys(system_clock::now()))` 为假——`from_sys` 要访问时区数据库中的闰秒表，首次访问可能因加载失败而抛异常。

### 成员（[time.clock.utc.members]）

- ¶1：`now()` 返回 `from_sys(system_clock::now())`，或更精确的值。也就是说，实现通常并不真的有一个"UTC 硬件时钟"，而是读系统时间再加上闰秒数。
- ¶2：`to_sys(u)`：返回使 `from_sys(t) == u` 的 `sys_time t`。若 `u` 落在一个正闰秒**之中**，这个映射不存在；此时把该闰秒当作没插入，返回闰秒插入前 `sys_time` 的**最后一个可表示值**。比如 `utc_time<milliseconds>` 的 23:59:60.500 转换为 `sys_time<milliseconds>` 得到 23:59:59.999。
- ¶3：`from_sys(t)`：结果与 `t` 的 `time_since_epoch()` 之差，等于 1970-01-01 与 `t` 之间插入的闰秒总数。若 `t` 恰好是闰秒插入的时刻，算作已插入。

¶3 的例子精确展示了边界（2015-07-01 插入了一个闰秒，此前累计 25 个），这里改写成一个函数：

```cpp
// 返回 from_sys(t) 与 t 的 time_since_epoch() 之差
auto diff = [](sys_time<nanoseconds> t) {
    return utc_clock::from_sys(t).time_since_epoch() - t.time_since_epoch();
};
auto t = sys_days{July/1/2015} - 2ns;
assert(diff(t)       == 25s);   // 闰秒插入前
assert(diff(t + 1ns) == 25s);   // 插入前 1ns
assert(diff(t + 2ns) == 26s);   // 恰好是插入时刻：算作已插入
assert(diff(t + 3ns) == 26s);
```

### 流、解析与闰秒信息（[time.clock.utc.nonmembers]）

- ¶1–¶2：`os << utc_time` 用 `{:L%F %T}` 格式化；闰秒期间秒字段显示为 `60`。¶2 的例子从 2015-06-30 23:59:59.500 开始每次加 250ms，会依次输出 `23:59:60.000`、`23:59:60.250`、… 、`2015-07-01 00:00:00.000`。
- ¶3–¶4：`from_stream`，与 `sys_time` 版本一样会减去解析到的偏移。
- ¶5：`leap_second_info` 是只有 `bool is_leap_second` 和 `seconds elapsed` 两个成员的结构体，没有其他基类或成员。
- ¶6：`get_leap_second_info(ut)`：`is_leap_second` 表示 `ut` 是否落在一个正闰秒之中；`elapsed` 是 1970 年以来到 `ut` 的闰秒总和（若 `ut` 正处于闰秒中，包括这一个）。

```cpp title="utc-leap.cpp" ok
#include <chrono>
#include <iostream>
using namespace std::chrono;

int main() {
    auto u = clock_cast<utc_clock>(sys_days{July/1/2015} - 500ms);
    for (int i = 0; i < 4; ++i, u += 500ms) {
        auto info = get_leap_second_info(u);
        std::cout << u << "  leap=" << info.is_leap_second
                  << " elapsed=" << info.elapsed << '\n';
    }
}
```

标准规定的输出是 23:59:59.500（leap=0, elapsed=25s）、23:59:60.000 与 23:59:60.500（leap=1, elapsed=26s）、00:00:00.000（leap=0, elapsed=26s）。**本机 libc++ 无法编译此例**：`utc_clock` 依赖时区数据库（本机构建中关闭），`clock_cast` 尚未实现。

## tai_clock 与 gps_clock（[time.clock.tai]、[time.clock.gps]）

这两个时钟都**不插入闰秒**，所以每插入一个闰秒，UTC 就相对它们多落后一秒。它们与 `utc_clock` 的换算只是加减一个常数：

| 时钟 | 纪元 | 相对 UTC 的关系 | 换算常数（相对 utc_time） |
|---|---|---|---|
| `tai_clock` | 1958-01-01 00:00:00 TAI | 1958 年时比 UTC 快 10 秒，此后每个闰秒再快 1 秒 | `378691210s` |
| `gps_clock` | 1980-01-06 00:00:00 UTC（1980 年 1 月第一个星期日） | 比 TAI 慢 19 秒（固定） | `315964809s` |

- [time.clock.tai.overview] ¶1：2000-01-01 00:00:00 UTC 相当于 2000-01-01 00:00:32 TAI：22 个闰秒加初始的 10 秒。
- [time.clock.tai.members] ¶2–¶3：`to_utc(t)` = `utc_time{t.time_since_epoch()} - 378691210s`，`from_utc` 反之。注：`378691210s == sys_days{1970y/January/1} - sys_days{1958y/January/1} + 10s`（1958–1970 共 4383 天）。
- [time.clock.gps.overview] ¶1：GPS 比 TAI 慢 19 秒，由 1958–1970 的 10 秒偏差与 1970–1980 插入的 9 个闰秒构成。
- [time.clock.gps.members] ¶2–¶3：`to_utc(t)` = `utc_time{t.time_since_epoch()} + 315964809s`，`from_utc` 反之。注：`315964809s == sys_days{1980y/January/Sunday[1]} - sys_days{1970y/January/1} + 9s`。
- 两者的 overview ¶2：同 `utc_clock`，不能假定是 *Cpp17TrivialClock*。
- nonmembers ¶1–¶4：输出用 `{:L%F %T}`；`%Z` 分别显示 `TAI` 和 `GPS`（[[time.format]]）。例子：`2000-01-01 00:00:00 UTC == 2000-01-01 00:00:32 TAI`，`2000-01-01 00:00:00 UTC == 2000-01-01 00:00:13 GPS`。

注意 `to_utc`/`from_utc` 是 `noexcept` 的——与 UTC 之间只差常数，不需要查表；查表发生在 UTC 与 sys 之间。

## file_clock（[time.clock.file]）

- [time.clock.file.overview] ¶1：`file_clock` 是一个满足 *Cpp17TrivialClock* 的类型的**别名**，`rep` 是有符号算术类型，用作 `filesystem::file_time_type` 的时钟（[[fs.filesystem.syn]]）。纪元未指明，`noexcept(file_clock::now())` 为真。注 1：它指代的类型可以在别的命名空间里，比如 `std::filesystem`。
- [time.clock.file.members] ¶1：该类型**恰好提供下面两组静态函数之一**：`to_sys`/`from_sys`，或 `to_utc`/`from_utc`。结果的 Duration 由输入的 Duration 计算。实现按文件系统时间戳的本质选择：如果文件系统时间戳是 Unix 时间（不计闰秒），就提供 sys 版本；如果计入闰秒，就提供 utc 版本。
- [time.clock.file.nonmembers] ¶1–¶3：流输出与解析，与其他时钟相同。

"恰好一组"让 `clock_cast` 能自动选出换算路径（见下文）。用户代码应当写 `clock_cast<system_clock>(ft)`，而不是假设 `file_clock::to_sys` 存在。

!!! impl "libc++ 的 file_clock"
    libc++ 中 `file_clock` 是 `std::filesystem::_FilesystemClock`：在支持 `__int128` 的平台上 `rep` 为 `__int128`、`period` 为 `nano`，纪元与 `system_clock` 相同，提供 `to_sys`/`from_sys`（实现只是原样搬运 `time_since_epoch()`）。由于 libc++ 没有 `clock_cast`，目前只能直接调用 `file_clock::to_sys`。

## steady_clock（[time.clock.steady]）

```cpp
class steady_clock {
public:
  using rep        = unspecified;
  using period     = ratio<unspecified, unspecified>;
  using duration   = chrono::duration<rep, period>;
  using time_point = chrono::time_point<unspecified, duration>;
  static constexpr bool is_steady = true;
  static time_point now() noexcept;
};
```

¶1：`steady_clock` 的 time_point 值随物理时间推进**永不减少**，并以相对真实时间稳定的速率前进；也就是说，**这个时钟不能被调整**。

它的纪元未指明（通常是系统启动时刻），所以它的 time_point 本身没有民用意义，不能转换成日期，也没有 `to_sys`。它只适合一件事：两次 `now()` 相减得到一段经过的时间。

`time_point` 写成 `time_point<unspecified, duration>`，允许实现让它与别的时钟共享 time_point 类型（[[time.clock.req]] 表 131）。

## high_resolution_clock（[time.clock.hires]）

¶1：计次周期最短的时钟，**可以是** `system_clock` 或 `steady_clock` 的别名。`is_steady` 未指明。

这条规定让 `high_resolution_clock` 几乎没有可移植的用途：同一份测量代码，在一个实现上用的是单调时钟，在另一个实现上可能会受 NTP 调整影响。本机 libc++ 中它就是 `steady_clock`（`is_same_v<high_resolution_clock, steady_clock>` 为真，两者都是纳秒精度）。**测量耗时请直接用 `steady_clock`**。

```cpp title="measure.cpp" ok
#include <chrono>
#include <iostream>
using namespace std::chrono;

int main() {
    static_assert(steady_clock::is_steady);
    auto t0 = steady_clock::now();
    volatile long sum = 0;
    for (long i = 0; i < 1'000'000; ++i) sum = sum + i;
    auto elapsed = steady_clock::now() - t0;                 // steady_clock::duration
    std::cout << duration_cast<microseconds>(elapsed) << '\n';
    std::cout << duration<double, std::milli>{elapsed} << '\n';   // 浮点：可隐式转换
}
```

## 本地时间（[time.clock.local]）

¶1：`local_time<Duration>` 族以伪时钟 `local_t` 为参数。`local_t` 只是一个空结构体，没有 `now()`，因而不满足时钟要求。但 `local_time` 起着关键作用：表示**相对于一个尚未指定的时区**的本地时间（[[g:local-time]]）。除了获取当前时间，`sys_time` 有的完整 time_point 代数，`local_time` 都有。

```cpp
struct local_t {};
template<class Duration> using local_time = time_point<local_t, Duration>;
using local_seconds = local_time<seconds>;
using local_days    = local_time<days>;
```

为什么不直接用 `sys_time` 表示本地时间？因为两者的数值含义不同：`sys_time` 的 `08:00` 是一个确定的物理时刻；`local_time` 的 `08:00` 在北京、伦敦、纽约代表三个不同的物理时刻，甚至在夏令时切换日可能不存在或出现两次。让它们成为不同类型，编译器就能拦住"把本地时间当 UTC 用"这一类经典错误；两者之间的转换必须经过 `time_zone`（[[time.zone]]）。

- ¶2–¶4：`os << local_time` 等价于把 `time_since_epoch()` 包成 `sys_time` 输出（同样的 `%F %T` 格式，只是不显示时区）。*Constraints*：对应的 `sys_time` 输出表达式有效。
- ¶5–¶6：`from_stream` 解析 `local_time`。与 `sys_time` 版本不同，解析到 `%z` 偏移时**不**从结果中减去——本地时间本来就不对齐 UTC。

## 跨时钟换算（[time.clock.cast]）{{c++20}}

### clock_time_conversion（[time.clock.conv]）

```cpp
template<class DestClock, class SourceClock>
struct clock_time_conversion {};
```

¶1：这是一个特征：特化 `clock_time_conversion<DestClock, SourceClock>` 需要提供一个 `const` 的 `operator()`，接受 `time_point<SourceClock, Duration>`，返回代表同一时刻的 `time_point<DestClock, OtherDuration>`；`OtherDuration` 由各特化自己根据输入算出。**只要至少一个模板实参是用户定义的时钟类型**，程序就可以特化它。

¶2：实现提供以下几组特化。

| 子条款 | 特化 | 效果 |
|---|---|---|
| [time.clock.cast.id] ¶1–¶3 | `<Clock, Clock>`、`<system_clock, system_clock>`、`<utc_clock, utc_clock>` | 原样返回 |
| [time.clock.cast.sys.utc] ¶1–¶2 | `<utc_clock, system_clock>`、`<system_clock, utc_clock>` | `utc_clock::from_sys` / `to_sys` |
| [time.clock.cast.sys] ¶1–¶6 | `<system_clock, S>`、`<D, system_clock>` | 调用 `S::to_sys(t)` / `D::from_sys(t)` |
| [time.clock.cast.utc] ¶1–¶6 | `<utc_clock, S>`、`<D, utc_clock>` | 调用 `S::to_utc(t)` / `D::from_utc(t)` |

后两组的约束是对应的静态函数调用"良构"，强制（*Mandates*）是返回类型确实是目标时钟的 time_point——一个时钟提供了名叫 `to_sys` 但返回别的东西的函数，是硬错误而不是静默不可用。

为什么恒等转换和 sys↔utc 要单独写成完全特化？看四个偏特化 `<system_clock, S>`、`<D, system_clock>`、`<utc_clock, S>`、`<D, utc_clock>`：`<utc_clock, system_clock>` 同时匹配 `<utc_clock, S>` 与 `<D, system_clock>`，两者谁也不比谁更特化，偏特化的选择就有歧义（[[temp.spec.partial.order]]）；`<system_clock, system_clock>`、`<system_clock, utc_clock>`、`<utc_clock, utc_clock>` 也是同样的情况。为这几个组合提供完全特化，歧义就消失了。

### clock_cast（[time.clock.cast.fn]）

```cpp
template<class DestClock, class SourceClock, class Duration>
  auto clock_cast(const time_point<SourceClock, Duration>& t);
```

¶1 *Constraints*：下列"时钟换算表达式"中至少一个良构：

| 编号 | 路径 | `operator()` 调用次数 |
|---|---|---|
| ¶1.1 | Source → Dest | 1 |
| ¶1.2 | Source → sys → Dest | 2 |
| ¶1.3 | Source → utc → Dest | 2 |
| ¶1.4 | Source → sys → utc → Dest | 3 |
| ¶1.5 | Source → utc → sys → Dest | 3 |

调用次数越少的表达式越"好"。

¶2 *Mandates*：在良构的表达式中，**存在唯一的最佳者**。¶3：返回最佳表达式的结果。

这套设计让 N 个时钟之间不需要 N² 个转换：每个时钟只要提供 `to_sys`/`from_sys` 或 `to_utc`/`from_utc` 中的一组，就能与所有其他时钟互转。几个具体路径：

- `clock_cast<utc_clock>(sys_time)`：¶1.1（直接特化）。
- `clock_cast<tai_clock>(sys_time)`：sys → utc → tai。`tai_clock` 只有 `from_utc`，¶1.1、¶1.2 都不良构，¶1.3 中 `clock_time_conversion<utc_clock, system_clock>` 可用，于是走 ¶1.3（2 次调用）。
- `clock_cast<gps_clock>(tai_time)`：tai → utc → gps，¶1.3。
- `clock_cast<system_clock>(file_time)`：取决于 `file_clock` 提供哪一组，¶1.1 或 ¶1.3——用户无需关心。

¶2 的"唯一最佳"可能失败。设用户有两个时钟 `A`、`B`，**都**同时提供 `to_sys`/`from_sys` 与 `to_utc`/`from_utc`，且两者之间没有直接特化。那么 `clock_cast<B>(a)` 既可以走 ¶1.2（A → sys → B），也可以走 ¶1.3（A → utc → B），都是 2 次调用，最佳者不唯一，违反 *Mandates*，程序非良构。这正是 `file_clock` 被要求"恰好提供一组"的原因：标准时钟之间的换算路径永远唯一。

```cpp title="clock-cast.cpp" ok
#include <chrono>
#include <format>
#include <iostream>
using namespace std::chrono;

int main() {
    auto st = sys_days{2000y/January/1};
    auto tt = clock_cast<tai_clock>(st);
    auto gt = clock_cast<gps_clock>(st);
    std::cout << std::format("{0:%F %T %Z} == {1:%F %T %Z}\n", st, tt);  // ... 00:00:32 TAI
    std::cout << std::format("{0:%F %T %Z} == {1:%F %T %Z}\n", st, gt);  // ... 00:00:13 GPS
}
```

**本机 libc++ 无法编译此例**：`tai_clock`、`gps_clock` 不可用，`clock_cast` 未实现。

## 时钟调整与等待函数

线程库的超时规则在 [[thread.req.timing]]，但它的设计完全建立在本节的时钟区分上：

- ¶3：以 `_for` 结尾的函数（`sleep_for`、`wait_for`、`try_lock_for`）接受 duration，产生**相对**超时；实现**应当**用稳定时钟测量。
- ¶4：以 `_until` 结尾的函数接受 time_point，产生**绝对**超时，实现应当用 time_point 所属的时钟测量。如果等待期间该时钟被调整到 `Ca`：若 `Ca` 超过了截止时刻 `Ct`，应尽快醒来；否则要等到 `Clock::now()` 返回不小于 `Ct` 的值。注 1：时钟往回调，等待的实际时长会**变长**；往前调，会变短。

后果是：

```cpp
std::this_thread::sleep_for(10s);                              // 约 10 秒，不受改系统时间影响
std::this_thread::sleep_until(system_clock::now() + 10s);      // 若期间系统时间被往回拨 1 小时，会多睡 1 小时
std::this_thread::sleep_until(steady_clock::now() + 10s);      // 不受影响
```

选择的原则是语义而不是习惯：**"等 10 秒"用 `_for` 或 `steady_clock`；"等到明早 9 点"才用 `system_clock` 的 `_until`**——后一种情况下，用户把时钟拨快了，你就**应该**提前醒来。

!!! pitfall "用 system_clock 测量耗时"
    `auto t0 = system_clock::now(); work(); auto dt = system_clock::now() - t0;` 在 NTP 校时、虚拟机迁移、用户改时间时会得到负数或巨大的值。`system_clock` 只用于"现在几点"，测耗时用 `steady_clock`。

!!! pitfall "以为 sys_time 能表示闰秒"
    把含 `23:59:60` 的时间戳解析成 `sys_time` 不会得到"第 60 秒"。需要精确处理闰秒（例如金融、天文、卫星数据）时用 `utc_time`，并且用 `get_leap_second_info` 区分闰秒内的时刻。

## 思考题

1. `utc_clock::to_sys` 对闰秒期间的 `utc_time` 返回"闰秒前最后一个可表示值"。为什么不返回下一秒的 00:00:00？

<details markdown="1">
<summary>答案</summary>

¶2 的选择保证了单调性：闰秒内的 utc 时刻映射到 23:59:59.999…，随后的 00:00:00 UTC 映射到 00:00:00 sys，`to_sys` 是单调不减的。若映射到 00:00:00，闰秒内的时刻与闰秒后的时刻会撞在一起，并且"闰秒内的较早时刻"会映射到比"闰秒前一刻"晚整整一秒的值，顺序信息丢失得更多。同时 `from_sys(to_sys(u))` 落在闰秒之前，不会凭空"跳过"一秒。
</details>

2. 写一个只提供 `to_utc`/`from_utc` 的用户时钟 `my_clock`。`clock_cast<system_clock>(my_time)` 走哪条路径？

<details markdown="1">
<summary>答案</summary>

¶1.1 需要 `clock_time_conversion<system_clock, my_clock>`，即 [time.clock.cast.sys] 中要求 `my_clock::to_sys` 良构——不满足；¶1.2 同样需要 `my_clock::to_sys`；¶1.3：`clock_time_conversion<utc_clock, my_clock>` 调用 `my_clock::to_utc`，再接 `clock_time_conversion<system_clock, utc_clock>`（`utc_clock::to_sys`），良构，2 次调用。¶1.5 也良构但需 3 次。唯一最佳是 ¶1.3。
</details>

## 小结

| 时钟 | 纪元 | 闰秒 | steady | 用途 |
|---|---|---|---|---|
| `system_clock` | 1970-01-01 UTC | 不计 | 未指明（实际为否） | 民用时间、与 `time_t` 互转 |
| `steady_clock` | 未指明 | — | 是 | 测量耗时、相对超时 |
| `high_resolution_clock` | 随别名 | — | 未指明 | 别用 |
| `utc_clock` | 1970-01-01 UTC | 计入 | 未指明 | 精确到闰秒的 UTC |
| `tai_clock` | 1958-01-01 TAI | 不插入 | 未指明 | 原子时 |
| `gps_clock` | 1980-01-06 UTC | 不插入 | 未指明 | GPS 时 |
| `file_clock` | 未指明 | 实现选择 | 未指明 | 文件时间戳 |
| `local_t` | — | — | 不是时钟 | 时区未定的钟面时间 |
