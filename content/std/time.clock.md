---
title: 时钟
summary: 标准提供的各个时钟：system_clock（Unix 时间）、steady_clock（单调）、high_resolution_clock、计入闰秒的 utc_clock、tai_clock、gps_clock、file_clock 和伪时钟 local_t，以及 clock_cast 怎样经由 sys 或 utc 在任意两个时钟之间换算。
status: done
covers: *
papers: P0355R7
related: time.clock.req, time.point, time.zone, time.cal, thread.req.timing, fs.filesystem.syn, ctime.syn
tags: 标准库, chrono, 时钟, 闰秒, UTC
updated: 2026-10-19
---

!!! tldr
    - 测量耗时用 `steady_clock`：它不会被调整，两次 `now()` 相减就是经过的时间。`high_resolution_clock` 可能只是另外两个时钟之一的别名，没有可移植的用途。
    - `system_clock` 表示 Unix 时间：从 1970-01-01 00:00:00 UTC 起计，不计闰秒，所以每天正好 86400 秒，可以直接和日期互转。
    - `utc_clock` 计入闰秒，`tai_clock` 和 `gps_clock` 不插入闰秒；它们之间的换算要查闰秒表或者加减一个常数。
    - `local_t` 不是时钟，`local_time` 表示时区尚未确定的钟面时间，和 `sys_time` 是不同的类型。
    - `clock_cast` 只要求每个时钟提供到 sys 或到 utc 的一组换算函数，就能在任意两个时钟之间换算，并且要求最佳路径唯一。

## 选哪个时钟

| 问题 | 时钟 |
|---|---|
| 这段代码跑了多久？ | `steady_clock` |
| 现在几点？要和日期、`time_t` 互转 | `system_clock` |
| 需要精确到闰秒的 UTC、原子时、GPS 时 | `utc_clock`、`tai_clock`、`gps_clock` |
| 这个文件什么时候修改的？ | `file_clock` |
| 当地时间早上 8 点，还没确定是哪个时区 | `local_t`（伪时钟） |

```cpp run ok title="measure.cpp"
#include <chrono>
#include <iostream>
using namespace std::chrono;

int main() {
  static_assert(steady_clock::is_steady);
  auto t0 = steady_clock::now();
  volatile long sum = 0;
  for (long i = 0; i < 1'000'000; ++i) sum = sum + i;
  auto elapsed = steady_clock::now() - t0;            // steady_clock::duration
  std::cout << duration_cast<microseconds>(elapsed) << '\n';
  std::cout << duration<double, std::milli>{elapsed} << '\n';  // 转为浮点：隐式
}
```

[[time.clock.general#1]] 规定，本节定义的类型都满足 *Cpp17TrivialClock* 要求（[[time.clock.req]]），除非另有说明。另有说明的是 `utc_clock`、`tai_clock`、`gps_clock`（它们的 `now()` 可能抛异常）和 `local_t`（它根本不是时钟）。

## steady_clock [time.clock.steady]

¶1 `steady_clock` 的时刻随着物理时间的推进永不减少，并且以相对真实时间稳定的速率前进。换句话说，这个时钟不能被调整。

它的纪元未指定，通常是系统启动的时刻，所以它的时刻没有民用意义，不能转换成日期，也没有 `to_sys`。它只适合一件事：两次 `now()` 相减，得到一段经过的时间。

它的 `time_point` 写作 `time_point<unspecified, duration>`，允许实现让它和别的时钟共用同一种 time_point 类型。

## high_resolution_clock [time.clock.hires]

¶1 `high_resolution_clock` 是计次周期最短的时钟，可以是 `system_clock` 或 `steady_clock` 的别名，`is_steady` 未指定。

同一份测量代码，在一个实现上用的是单调时钟，在另一个实现上可能受系统校时影响。本机 libc++ 中它就是 `steady_clock`，两者都以纳秒计。测量耗时直接用 `steady_clock`。

## system_clock：Unix 时间 [time.clock.system]

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

### 不计闰秒的秒数

¶1 `system_clock` 表示系统范围的实时时钟，也就是墙上时间。`sys_time<Duration>` 度量从 1970-01-01 00:00:00 UTC 起、不计闰秒的时间，这就是通常所说的 [[g:unix-time]]。

标准的例子给出两个值：1970-01-01 的 `time_since_epoch()` 是 `0s`；2000-01-01 的是 `946'684'800s`，正好等于 `10'957 * 86'400s`。这 30 年里实际插入过 22 个闰秒，但在 `sys_time` 里每一天都是 86400 秒。

这样规定的好处是 `sys_days` 和 `year_month_day` 之间的换算只是一段算术，不用查闰秒表（[[time.cal]]）。代价是闰秒那一秒在 `sys_time` 里没有位置：2016-12-31 23:59:60 UTC 无法和下一秒 00:00:00 区分开。需要区分时用 `utc_clock`。

C++11 只说 `system_clock` 是墙上时间，没有规定纪元，尽管所有实现都用了 Unix 纪元。C++20 的 [[P0355R7]] 把它确定为 Unix 时间，日历库就建立在这一点上。

### 成员 [time.clock.system.members]

¶1 `rep` 的类型未指定，但要满足 `system_clock::duration::min() < system_clock::duration::zero()`。注 1 指出，这意味着 `rep` 是有符号类型，1970 年以前的时刻必须能表示。

¶2 `to_time_t` 和 ¶3 `from_time_t` 在 `time_t` 和 `time_point` 之间转换，两边都取二者中较粗的精度；多余的精度是舍入还是截断，由实现定义。这对函数是和 C 接口（[[ctime.syn]]）打交道的桥梁。

`is_steady` 未指定，主流实现都是 `false`：管理员改时间、NTP 校时都可能让它跳变。夏令时不影响它，因为它表示的是 UTC。

### 输出与解析 [time.clock.system.nonmembers]

```cpp run ok title="sys-clock.cpp"
#include <chrono>
#include <ctime>
#include <iostream>
using namespace std::chrono;

int main() {
  std::cout << sys_seconds{946'688'523s} << '\n';      // 2000-01-01 01:02:03
  std::cout << sys_days{2024y/February/last} << '\n';  // 2024-02-29
  std::time_t c = system_clock::to_time_t(sys_seconds{0s});
  std::cout << c << '\n';                              // 0
}
```

¶2 `os << sys_time<Duration>` 等价于用 `"{:L%F %T}"` 格式化。¶1 要求 `Duration` 的计数不是浮点类型，并且 `Duration{1} < days{1}`；精度为一天或更粗的 `sys_days` 走 ¶4 的重载，只输出日期。

¶6 `from_stream` 按 [[time.parse]] 解析。如果格式里用了 `%z` 并且解析出了 UTC 偏移，这个偏移会从结果中减去：解析 `2024-01-01 08:00:00 +0800` 得到的 `sys_time` 是 UTC 的 00:00。

## local_t：时区未定的本地时间 [time.clock.local]

```cpp
struct local_t {};
template<class Duration> using local_time = time_point<local_t, Duration>;
using local_seconds = local_time<seconds>;
using local_days    = local_time<days>;
```

¶1 `local_time<Duration>` 以伪时钟 `local_t` 为参数。`local_t` 没有 `now()`，不满足时钟要求。`local_time` 表示相对于一个尚未指定的时区的本地时间（[[g:local-time]]）。除了获取当前时间，`sys_time` 能做的时刻运算 `local_time` 都能做。

为什么不直接用 `sys_time` 表示本地时间？`sys_time` 的 08:00 是一个确定的物理时刻；`local_time` 的 08:00 在北京、伦敦、纽约是三个不同的时刻，在夏令时切换的那天甚至可能不存在或者出现两次。让二者成为不同的类型，编译器就能拦住把本地时间当成 UTC 用的错误。两者之间的换算必须经过 `time_zone`（[[time.zone]]）。

¶3 `os << local_time` 把 `time_since_epoch()` 包成 `sys_time` 输出，格式相同，只是不表示任何时区。¶5 的 `from_stream` 解析到 `%z` 偏移时不从结果中减去，因为本地时间本来就不对齐 UTC。

## utc_clock：计入闰秒 [time.clock.utc]

```cpp
class utc_clock {
public:
  using rep = a signed arithmetic type;
  // period、duration、time_point、is_steady 与上面类似
  static time_point now();
  template<class Duration>
    static sys_time<common_type_t<Duration, seconds>> to_sys(const utc_time<Duration>& t);
  template<class Duration>
    static utc_time<common_type_t<Duration, seconds>> from_sys(const sys_time<Duration>& t);
};
```

### 和 sys_time 差多少 [time.clock.utc.overview]

¶1 `utc_clock` 和它的 `utc_time` 同样从 1970-01-01 00:00:00 UTC 起计，但计入闰秒。2000-01-01 的 `utc_time` 是 `946'684'822s`，比 `sys_time` 多出的 22 秒就是这期间插入的闰秒。注 1 补充，UTC 本身从 1972-01-01 00:00:10 TAI 开始，要以那一刻为起点，加减 `63'072'000s` 即可。

¶2 除非实现能保证 `now()` 不传播异常，`utc_clock` 不是 *Cpp17TrivialClock*。注 2 指出 `from_sys(system_clock::now())` 不是 `noexcept` 的：`from_sys` 要查时区数据库中的闰秒表（[[time.zone]]），第一次访问数据库可能因加载失败而抛异常。

### 闰秒期间的换算 [time.clock.utc.members]

¶1 `now()` 返回 `from_sys(system_clock::now())`，或者更精确的值。实现通常没有一个专门的 UTC 时钟，而是读系统时间，再加上闰秒数。

¶3 `from_sys(t)` 的结果和 `t` 的 `time_since_epoch()` 之差，等于 1970-01-01 到 `t` 之间插入的闰秒总数。`t` 恰好是插入闰秒的时刻时，算作已经插入。标准的例子展示了这个边界（2015-07-01 插入了一个闰秒，此前累计 25 个）：

```cpp
auto diff = [](sys_time<nanoseconds> t) {
  return utc_clock::from_sys(t).time_since_epoch() - t.time_since_epoch();
};
auto t = sys_days{July/1/2015} - 2ns;
assert(diff(t)       == 25s);   // 插入前 2ns
assert(diff(t + 1ns) == 25s);   // 插入前 1ns
assert(diff(t + 2ns) == 26s);   // 恰好是插入时刻：算作已插入
assert(diff(t + 3ns) == 26s);
```

¶2 `to_sys(u)` 返回满足 `from_sys(t) == u` 的 `t`。如果 `u` 落在一个正闰秒之中，这样的 `t` 不存在；这时把这个闰秒当作没有插入，返回插入前 `sys_time` 能表示的最后一个值。例如 `utc_time<milliseconds>` 的 23:59:60.500 转换成 `sys_time<milliseconds>` 是 23:59:59.999。

### 输出与闰秒信息 [time.clock.utc.nonmembers]

```cpp title="utc-leap.cpp"
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

按标准，输出依次是 23:59:59.500（leap=0，elapsed=25s）、23:59:60.000 和 23:59:60.500（leap=1，elapsed=26s）、次日 00:00:00.000（leap=0，elapsed=26s）。本机 libc++ 编译不了这个例子：它的构建关闭了时区数据库，`utc_clock` 不存在，`clock_cast` 也还没有实现。

¶1 `os << utc_time` 用 `"{:L%F %T}"` 格式化，闰秒期间秒字段显示为 `60`。

¶5 `leap_second_info` 只有两个数据成员：`bool is_leap_second` 和 `seconds elapsed`。¶6 `get_leap_second_info(ut)` 的 `is_leap_second` 表示 `ut` 是否落在一个正闰秒之中；`elapsed` 是 1970 年到 `ut` 的闰秒总数，`ut` 正处于闰秒中时也算上这一个。

## tai_clock 与 gps_clock [time.clock.tai] [time.clock.gps]

这两个时钟都不插入闰秒。UTC 每插入一个闰秒，就相对它们多落后一秒。它们和 `utc_clock` 之间的换算只是加减一个常数：

| 时钟 | 纪元 | 和 UTC 的关系 | `to_utc` |
|---|---|---|---|
| `tai_clock` | 1958-01-01 00:00:00 TAI | 1958 年时比 UTC 快 10 秒，之后每个闰秒再快 1 秒 | 减 `378691210s` |
| `gps_clock` | 1980 年 1 月第一个星期日 00:00:00 UTC | 固定比 TAI 慢 19 秒 | 加 `315964809s` |

[[time.clock.tai.overview#1]] 举例：到 2000-01-01 共插入了 22 个正闰秒，所以 2000-01-01 00:00:00 UTC 相当于 2000-01-01 00:00:32 TAI，即 22 秒加上初始的 10 秒。

[[time.clock.gps.overview#1]] 说明 GPS 比 TAI 慢 19 秒的来源：1958 到 1970 年之间的 10 秒偏差，加上 1970 到 1980 年插入的 9 个闰秒。

两个常数在 [[time.clock.tai.members#2]] 和 [[time.clock.gps.members#2]] 的注里有推导：`378691210s` 是 1958 到 1970 年的 4383 天再加 10 秒；`315964809s` 是 1970-01-01 到 1980 年 1 月第一个星期日的天数再加 9 秒。

`to_utc` 和 `from_utc` 都是 `noexcept` 的，因为和 UTC 之间只差一个常数，不用查表；查表发生在 UTC 和 sys 之间。所以这两个时钟的 `now()` 同样可能抛异常，overview ¶2 说它们和 `utc_clock` 一样，不能假定是 *Cpp17TrivialClock*。

两个时钟的 nonmembers 子条款规定输出用 `"{:L%F %T}"`，`%Z` 分别显示 `TAI` 和 `GPS`（[[time.format]]）。标准的例子是 `2000-01-01 00:00:00 UTC == 2000-01-01 00:00:32 TAI` 和 `2000-01-01 00:00:00 UTC == 2000-01-01 00:00:13 GPS`。

## file_clock [time.clock.file]

[[time.clock.file.overview#1]] 规定 `file_clock` 是某个满足 *Cpp17TrivialClock* 的类型的别名，`rep` 是有符号算术类型，用作 `filesystem::file_time_type` 的时钟（[[fs.filesystem.syn]]）。纪元未指定，`now()` 是 `noexcept` 的。注 1 说明它指代的类型可以在别的命名空间里，比如 `std::filesystem`。

[[time.clock.file.members#1]] 要求这个类型恰好提供下面两组静态函数之一：`to_sys` 和 `from_sys`，或者 `to_utc` 和 `from_utc`。实现按文件系统时间戳的性质选择：时间戳是 Unix 时间就提供 sys 版本，计入闰秒就提供 utc 版本。

恰好一组，是为了让 `clock_cast` 能自动选出唯一的换算路径（见下文）。用户代码应当写 `clock_cast<system_clock>(ft)`，不要假设 `file_clock::to_sys` 存在。

!!! impl "libc++ 的 file_clock"
    libc++ 中 `file_clock` 是 `std::filesystem::_FilesystemClock`。在支持 `__int128` 的平台上，`rep` 是 `__int128`，周期是纳秒，纪元和 `system_clock` 相同，提供 `to_sys` 和 `from_sys`。libc++ 还没有 `clock_cast`，目前只能直接调用 `file_clock::to_sys`。

## 跨时钟换算 [time.clock.cast] {{c++20}}

### clock_time_conversion [time.clock.conv]

```cpp
template<class DestClock, class SourceClock>
struct clock_time_conversion {};
```

¶1 `clock_time_conversion<DestClock, SourceClock>` 是一个特征类。它的特化要提供一个 `const` 的 `operator()`，接受 `time_point<SourceClock, Duration>`，返回表示同一时刻的 `time_point<DestClock, OtherDuration>`；`OtherDuration` 由各特化根据输入自行决定。只要至少一个模板实参是用户定义的时钟类型，程序就可以特化它。

¶2 实现提供了下面几组特化：

| 子条款 | 特化 | 效果 |
|---|---|---|
| [time.clock.cast.id] | `<Clock, Clock>`、`<system_clock, system_clock>`、`<utc_clock, utc_clock>` | 原样返回 |
| [time.clock.cast.sys.utc] | `<utc_clock, system_clock>`、`<system_clock, utc_clock>` | `utc_clock::from_sys` / `to_sys` |
| [time.clock.cast.sys] | `<system_clock, S>`、`<D, system_clock>` | `S::to_sys(t)` / `D::from_sys(t)` |
| [time.clock.cast.utc] | `<utc_clock, S>`、`<D, utc_clock>` | `S::to_utc(t)` / `D::from_utc(t)` |

后两组有两层要求。*Constraints* 要求对应的静态函数调用良构，不良构时这个特化的 `operator()` 不可用。*Mandates* 要求返回类型确实是目标时钟的 time_point：一个时钟如果提供了名叫 `to_sys`、却返回别的东西的函数，程序非良构，而不是悄悄地不可用。

为什么恒等转换和 sys 与 utc 之间的转换要单独写成完全特化？看后两组的四个偏特化：`<utc_clock, system_clock>` 同时匹配 `<utc_clock, S>` 和 `<D, system_clock>`，两者谁也不比谁更特化，选择偏特化时就会有歧义（[[temp.spec.partial.order]]）。`<system_clock, system_clock>`、`<system_clock, utc_clock>`、`<utc_clock, utc_clock>` 也是这样。为这几个组合提供完全特化，歧义就消失了。

### clock_cast [time.clock.cast.fn]

```cpp
template<class DestClock, class SourceClock, class Duration>
  auto clock_cast(const time_point<SourceClock, Duration>& t);
```

¶1 `clock_cast` 要求下面五种换算表达式中至少有一种良构。调用 `operator()` 的次数越少，表达式越好。

| 编号 | 路径 | 调用次数 |
|---|---|---|
| ¶1.1 | Source → Dest | 1 |
| ¶1.2 | Source → sys → Dest | 2 |
| ¶1.3 | Source → utc → Dest | 2 |
| ¶1.4 | Source → sys → utc → Dest | 3 |
| ¶1.5 | Source → utc → sys → Dest | 3 |

¶2 在良构的表达式中，必须有唯一的最佳者，否则程序非良构。¶3 返回最佳表达式的结果。

这样，N 个时钟之间不需要 N² 个转换。每个时钟只要提供 `to_sys`/`from_sys` 或 `to_utc`/`from_utc` 中的一组，就能和其他所有时钟互转。几个具体的例子：

- `clock_cast<utc_clock>(sys_time)` 走 ¶1.1，用的是完全特化。
- `clock_cast<tai_clock>(sys_time)`：`tai_clock` 只有 `from_utc`，¶1.1 和 ¶1.2 都不良构；¶1.3 先用 `<utc_clock, system_clock>` 换到 utc，再用 `tai_clock::from_utc`，调用 2 次。
- `clock_cast<gps_clock>(tai_time)` 走 tai → utc → gps，也是 ¶1.3。
- `clock_cast<system_clock>(file_time)` 走 ¶1.1 还是 ¶1.3，取决于 `file_clock` 提供哪一组函数，用户不用关心。

唯一最佳的要求可能失败。假设用户有两个时钟 `A` 和 `B`，都同时提供了 sys 和 utc 两组函数，二者之间又没有直接特化。`clock_cast<B>(a)` 既可以走 ¶1.2，也可以走 ¶1.3，都调用 2 次，最佳者不唯一，程序非良构。这就是 `file_clock` 必须恰好提供一组函数的原因：标准时钟之间的换算路径总是唯一的。

```cpp title="clock-cast.cpp"
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

本机 libc++ 编译不了这个例子：`tai_clock`、`gps_clock` 不可用，`clock_cast` 也没有实现。注释中的输出取自标准的例子。

## 时钟调整与等待函数

线程库的超时规则写在 [[thread.req.timing]]，它依赖本节对时钟的区分：

- 以 `_for` 结尾的函数（`sleep_for`、`wait_for`、`try_lock_for`）接受一段时长，是相对超时，实现应当用稳定的时钟测量（[[thread.req.timing#3]]）。
- 以 `_until` 结尾的函数接受一个时刻，是绝对超时，实现应当用这个时刻所属的时钟测量（[[thread.req.timing#4]]）。如果等待期间时钟被调整，等待会相应地变长或变短。

```cpp
std::this_thread::sleep_for(10s);                          // 约 10 秒，不受改系统时间影响
std::this_thread::sleep_until(system_clock::now() + 10s);  // 期间系统时间被往回拨 1 小时，就多睡 1 小时
std::this_thread::sleep_until(steady_clock::now() + 10s);  // 不受影响
```

选择的依据是语义。等 10 秒，用 `_for` 或 `steady_clock`。等到明早 9 点，才用 `system_clock` 的 `_until`：这时用户把时钟拨快了，程序本来就应该提前醒来。

<details class="fine" markdown="1"><summary>其余条文</summary>

各时钟的 `from_stream`（[[time.clock.system.nonmembers#6]]、[[time.clock.utc.nonmembers#3]]、tai 和 gps 的 nonmembers ¶3、[[time.clock.file.nonmembers#2]]）都按 [[time.parse]] 解析，失败时设置 `failbit` 且不修改目标；解析到 `%Z` 时存入 `abbrev`，解析到 `%z` 时存入 `offset`，并从结果中减去这个偏移。只有 `local_time` 版本不减。

[[time.clock.tai.members#1]]、[[time.clock.gps.members#1]]：`now()` 返回 `from_utc(utc_clock::now())`，或者更精确的值。

[[time.clock.file.members#1]] 还要求 `file_clock` 的换算函数与 `utc_clock`、`tai_clock`、`gps_clock` 的换算保持一致，结果的精度由输入的精度计算得出。

</details>

## 常见陷阱

!!! pitfall "用 system_clock 测量耗时"
    `auto t0 = system_clock::now(); work(); auto dt = system_clock::now() - t0;` 遇到 NTP 校时、虚拟机迁移或者用户改时间，可能得到负数或者巨大的值。`system_clock` 只用来回答现在几点，测量耗时用 `steady_clock`。

!!! pitfall "以为 sys_time 能表示闰秒"
    把含有 `23:59:60` 的时间戳解析成 `sys_time`，不会得到第 60 秒。需要精确处理闰秒的场合（金融、天文、卫星数据）用 `utc_time`，并用 `get_leap_second_info` 识别闰秒内的时刻。

## 思考题

!!! question "思考题 1"
    `utc_clock::to_sys` 对闰秒期间的 `utc_time`，返回闰秒前 `sys_time` 能表示的最后一个值。为什么不返回下一秒的 00:00:00？

<details markdown="1">
<summary>答案</summary>

这样 `to_sys` 是单调不减的：闰秒内的时刻都映射到 23:59:59.999…，之后的 00:00:00 UTC 映射到 00:00:00。如果映射到 00:00:00，闰秒内的时刻会和闰秒之后的时刻挤在一起，而且比闰秒前一刻晚了整整一秒，丢失的顺序信息更多。另外，`from_sys(to_sys(u))` 落在闰秒之前，不会凭空跳过一秒。
</details>

!!! question "思考题 2"
    一个用户时钟 `my_clock` 只提供 `to_utc` 和 `from_utc`。`clock_cast<system_clock>(my_time)` 走哪条路径？

<details markdown="1">
<summary>答案</summary>

表达式 ¶1.1 需要 `clock_time_conversion<system_clock, my_clock>`，即 `my_clock::to_sys`，不满足；¶1.2 同样需要 `my_clock::to_sys`。¶1.3 先用 `<utc_clock, my_clock>` 调用 `my_clock::to_utc`，再用完全特化 `<system_clock, utc_clock>` 调用 `utc_clock::to_sys`，良构，调用 2 次。¶1.5 也良构，但要调用 3 次。唯一的最佳者是 ¶1.3。
</details>
