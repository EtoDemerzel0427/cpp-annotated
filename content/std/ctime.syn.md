---
title: 头文件 <ctime> 概要
summary: C 的时间函数在 C++ 中的样子——time_t / clock_t / tm / timespec，gmtime/localtime 的数据竞争，C23 带来的 timegm、gmtime_r、localtime_r、timespec_getres 与可选的 TIME_MONOTONIC，asctime/ctime 移入附录 D；与 <chrono> 的互操作
status: done
related: time, time.clock, depr.ctime, res.on.data.races, c.locales
tags: 标准库, C 兼容, 时间
updated: 2026-10-18
---

`<ctime>` 是 C 头文件 `<time.h>` 在 C++ 中的对应物。它与 `<chrono>` 是两套平行的设施：`<chrono>` 用类型表达单位和时钟，`<ctime>` 用整数和结构体。新代码应当首选 `<chrono>`，但与操作系统 API、C 库、文件格式打交道时仍然经常需要 `<ctime>`，两者之间的桥梁是 `system_clock::to_time_t` / `from_time_t`（[[time.clock]]）。

## 概要

```cpp
#define __STDC_VERSION_TIME_H__ 202311L
#define NULL see [support.types.nullptr]
#define CLOCKS_PER_SEC see below
#define TIME_UTC see below
#define TIME_MONOTONIC see below     // optional
#define TIME_ACTIVE see below        // optional
#define TIME_THREAD_ACTIVE see below // optional

namespace std {
  using size_t = see [support.types.layout];
  using clock_t = see below;
  using time_t = see below;
  struct timespec;
  struct tm;

  clock_t clock();
  double difftime(time_t time1, time_t time0);
  time_t mktime(tm* timeptr);
  time_t timegm(tm* timeptr);
  time_t time(time_t* timer);
  int timespec_get(timespec* ts, int base);
  int timespec_getres(timespec* ts, int base);
  tm* gmtime(const time_t* timer);
  tm* gmtime_r(const time_t* timer, tm* buf);
  tm* localtime(const time_t* timer);
  tm* localtime_r(const time_t* timer, tm* buf);
  size_t strftime(char* s, size_t maxsize, const char* format, const tm* timeptr);
}
```

¶1：`<ctime>` 的内容与 C 标准库的 `<time.h>` 相同。概要末尾的"See also"指向 ISO/IEC 9899:2024（即 C23）的 7.29。

脚注 233 补充：`strftime` 支持 C 的转换说明符 `C` `D` `e` `F` `g` `G` `h` `r` `R` `t` `T` `u` `V` `z`，以及修饰符 `E` 和 `O`。这些说明符是 C99 加入的，脚注确认 C++ 的 `strftime` 也支持它们。

¶2：`gmtime` 与 `localtime` **不要求避免数据竞争**（[[res.on.data.races]]）。

## 与 C23 对齐

这份概要以 C23 为基准，相比以 C17 为基准的旧版本，有几处变化（C++23 之后的新措辞）：

| 新增 / 变化 | 说明 |
|---|---|
| `__STDC_VERSION_TIME_H__` | 值为 `202311L`，用于检测 `<time.h>` 的 C23 特性 |
| `timegm` | `mktime` 的 UTC 版本：把 `tm` 当作 UTC 解释，返回 `time_t`。此前它只是 POSIX/BSD 扩展 |
| `gmtime_r`、`localtime_r` | 把结果写入调用者提供的 `tm`，没有共享的静态缓冲区。此前是 POSIX 函数 |
| `timespec_getres` | 查询 `timespec_get` 某个时间基准的分辨率 |
| `TIME_MONOTONIC`、`TIME_ACTIVE`、`TIME_THREAD_ACTIVE` | `timespec_get` 的可选时间基准：单调时钟、进程 CPU 时间、线程 CPU 时间 |
| `asctime`、`ctime` | 移出本概要，改在附录 D 的 [[depr.ctime]] 中声明，**已弃用** {{deprecated}} |

`asctime` 与 `ctime` 被弃用，是因为它们返回指向静态缓冲区的指针，并且对年份超过 4 位等情形有缓冲区溢出的历史问题；[[depr.ctime]] ¶2 同样说明它们不要求避免数据竞争。替代品是 `strftime` 或 `std::format`。

!!! impl "libc++ 尚未跟进"
    截至写作时，本机 libc++ 的 `<ctime>` 中没有 `std::timegm`、`std::gmtime_r`、`std::localtime_r`、`std::timespec_getres`，也没有定义 `__STDC_VERSION_TIME_H__`；`asctime` 也没有弃用警告。在 macOS 上 `::timegm`、`::gmtime_r` 等作为 POSIX 函数存在于全局命名空间，可以直接使用。

## 类型

| 类型 | 含义 |
|---|---|
| `time_t` | 日历时间的实数类型。C 没有规定编码；POSIX 规定为自 1970-01-01 UTC 起的秒数（不计闰秒），与 `sys_seconds` 的数值一致 |
| `clock_t` | `clock()` 的返回类型，处理器时间，以 `CLOCKS_PER_SEC` 为单位 |
| `tm` | 分解时间：`tm_year`（自 1900 年起）、`tm_mon`（0–11）、`tm_mday`（1–31）、`tm_wday`（周日 = 0）、`tm_yday`、`tm_isdst` 等 |
| `timespec` | `tv_sec`（`time_t`）加 `tv_nsec`（`long`，纳秒） |

`tm` 的月份从 0 开始、年份减去 1900，`weekday::c_encoding()` 与 `tm_wday` 相同——这些对应关系在与 `<chrono>` 互转时最容易出错。

## 函数

| 函数 | 作用 | `<chrono>` 中的对应 |
|---|---|---|
| `time(p)` | 当前日历时间 | `system_clock::now()` |
| `clock()` | 进程使用的处理器时间 | 无（`steady_clock` 是墙上时间，不是 CPU 时间） |
| `difftime(t1, t0)` | `t1 − t0`，以秒为单位的 `double` | `duration<double>{tp1 - tp0}` |
| `mktime(tm*)` | 本地时间 `tm` → `time_t`，并规范化 `tm` 的各字段 | `time_zone::to_sys(local_time)` |
| `timegm(tm*)` | UTC 的 `tm` → `time_t` | `sys_days{year_month_day} + 时分秒` |
| `gmtime`、`gmtime_r` | `time_t` → UTC 的 `tm` | `year_month_day{floor<days>(tp)}`、`hh_mm_ss` |
| `localtime`、`localtime_r` | `time_t` → 本地时间的 `tm` | `zoned_time{current_zone(), tp}.get_local_time()` |
| `strftime` | 按格式输出 `tm` | `std::format("{:%...}", tp)` |
| `timespec_get(ts, TIME_UTC)` | 纳秒精度的当前 UTC 时间 | `system_clock::now()` |

### 数据竞争（¶2）

`gmtime`、`localtime`（以及附录 D 中的 `asctime`、`ctime`）返回指向**静态存储**中 `tm` 对象的指针。两个线程同时调用会写同一个对象，这是数据竞争（{{ub}}）；即使单线程，第二次调用也会覆盖第一次的结果。标准通过 ¶2 明确豁免了 [[res.on.data.races]] 对它们的一般要求。

```cpp
std::tm* a = std::gmtime(&t1);
std::tm* b = std::gmtime(&t2);   // a 与 b 可能指向同一个对象：*a 已被覆盖
```

线程安全的写法是 `gmtime_r` / `localtime_r`（调用者提供缓冲区），或者干脆用 `<chrono>`。

`localtime` 与 `mktime` 还依赖进程的时区设置（POSIX 下的 `TZ` 环境变量），这是又一个全局状态。`<chrono>` 的 `time_zone` 则是显式传递的对象，不同线程可以同时使用不同时区。

## 与 chrono 互转

```cpp title="ctime-chrono.cpp" ok
#include <chrono>
#include <cstdio>
#include <ctime>
using namespace std::chrono;

int main() {
    std::time_t t = 1'709'298'307;                         // 2024-03-01 13:05:07 UTC
    auto tp = system_clock::from_time_t(t);
    std::printf("%d\n", floor<seconds>(tp).time_since_epoch().count() == t);   // 1

    // chrono → tm（UTC），不经过 gmtime 的静态缓冲区
    auto dp  = floor<days>(tp);
    year_month_day ymd{dp};
    hh_mm_ss hms{floor<seconds>(tp - dp)};
    std::tm tm{};
    tm.tm_year = int(ymd.year()) - 1900;
    tm.tm_mon  = unsigned(ymd.month()) - 1;
    tm.tm_mday = unsigned(ymd.day());
    tm.tm_hour = hms.hours().count();
    tm.tm_min  = hms.minutes().count();
    tm.tm_sec  = int(hms.seconds().count());
    tm.tm_wday = weekday{dp}.c_encoding();

    char buf[64];
    std::strftime(buf, sizeof buf, "%F %T %A", &tm);
    std::puts(buf);                                        // 2024-03-01 13:05:07 Friday
}
```

## 陷阱

!!! pitfall "用 clock() 测量墙上时间"
    `clock()` 返回的是**处理器时间**：线程睡眠、等待 I/O 时不增加，多线程程序中可能比墙上时间增长得更快。测量经过的时间用 `steady_clock`。

!!! pitfall "time_t 的单位与范围"
    C 标准没有规定 `time_t` 是秒，也没有规定纪元；只有 POSIX 做了规定。32 位 `time_t` 在 2038-01-19 溢出。`system_clock::to_time_t` 的舍入方式由实现定义（[[time.clock]]）。

!!! pitfall "mktime 会修改实参"
    `mktime` 会把 `tm` 规范化（例如把 `tm_mday = 32` 进位到下个月）并填写 `tm_wday`、`tm_yday`，而且按**本地时区**解释输入。把 UTC 的 `tm` 交给 `mktime` 会得到偏差一个时区偏移的结果——这正是 `timegm` 被 C23 标准化的原因。

## 小结

- `<ctime>` = C23 的 `<time.h>`：新增 `timegm`、`gmtime_r`、`localtime_r`、`timespec_getres` 和可选的单调/CPU 时间基准。
- `asctime`、`ctime` 已弃用，移入附录 D。
- `gmtime`、`localtime` 使用共享静态缓冲区，不保证无数据竞争。
- 与 `<chrono>` 的桥梁是 `system_clock::to_time_t` / `from_time_t`；分解时间优先用 `year_month_day` + `hh_mm_ss`。
- libc++ 尚未提供 C23 新增函数的 `std::` 版本。
