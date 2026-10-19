---
title: 头文件 <ctime> 概要
summary: <ctime> 就是 C23 的 <time.h>：time_t、tm、timespec 和相关函数；gmtime、localtime 返回共享的静态对象，不保证没有数据竞争；C23 新增 timegm、gmtime_r、localtime_r、timespec_getres；与 <chrono> 怎样互相转换。
status: done
related: time, time.clock, depr.ctime, res.on.data.races, c.locales
tags: 标准库, C 兼容, 时间
updated: 2026-10-19
---

!!! tldr
    - `<ctime>` 的内容与 C23 的 `<time.h>` 相同，C++ 只额外规定了一条：`gmtime`、`localtime` 不要求避免数据竞争。
    - 这两个函数返回指向同一个静态 `tm` 对象的指针，第二次调用会覆盖第一次的结果；需要线程安全时用 `gmtime_r`、`localtime_r` 或 `<chrono>`。
    - C23 新增的 `timegm`、`gmtime_r`、`localtime_r`、`timespec_getres` 进入了概要，本机 libc++ 还没有在 `std` 里提供它们。
    - `asctime`、`ctime` 已弃用，移到了附录 D。
    - `<ctime>` 与 `<chrono>` 之间的桥梁是 `system_clock::to_time_t`/`from_time_t`；分解时间优先用 `year_month_day` 和 `hh_mm_ss`。

## 共享的静态缓冲区（¶2）

```cpp run unspecified
#include <cstdio>
#include <ctime>

int main() {
  std::time_t t1 = 1'709'298'307, t2 = 0;
  std::tm* a = std::gmtime(&t1);
  std::tm* b = std::gmtime(&t2);
  std::printf("%d %d\n", a == b, a->tm_year + 1900);   // 本机：1 1970
}
```

`gmtime`、`localtime` 返回的指针指向库内部的一个静态 `tm` 对象。本机上两次调用返回同一个地址，第二次调用把 `*a` 覆盖成了 1970 年。C 标准允许这两个函数共用同一个对象，所以 `a == b` 的结果是未指定的。

单线程里这只是结果被覆盖；两个线程同时调用，就是在没有同步的情况下写同一个对象，构成数据竞争。

¶2 标准明确规定 `gmtime` 和 `localtime` 不要求避免数据竞争。[[res.on.data.races]] 一般要求标准库函数不修改实参以外的对象，这两个函数是例外。附录 D 的 `asctime`、`ctime` 也是如此（[[depr.ctime#2]]）。

线程安全的写法是 `gmtime_r`、`localtime_r`，由调用者提供 `tm` 缓冲区；或者直接用 `<chrono>`。

`localtime` 和 `mktime` 还依赖进程的时区设置，在 POSIX 下是 `TZ` 环境变量，这是另一份全局状态。`<chrono>` 的 `time_zone` 是显式传递的对象，不同线程可以同时使用不同的时区（[[time.zone]]）。

## 概要（¶1）

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

¶1 `<ctime>` 的内容与 C 标准库的 `<time.h>` 相同，引用的是 C23（ISO/IEC 9899:2024）的 7.29。

### 类型

| 类型 | 含义 |
|---|---|
| `time_t` | 日历时间。C 没有规定编码；POSIX 规定为自 1970-01-01 UTC 起的秒数（不计闰秒），与 `sys_seconds` 的数值一致 |
| `clock_t` | `clock()` 的返回类型，表示处理器时间，单位是 `1/CLOCKS_PER_SEC` 秒 |
| `tm` | 分解时间：`tm_year`（自 1900 年起）、`tm_mon`（0–11）、`tm_mday`（1–31）、`tm_wday`（周日为 0）、`tm_yday`、`tm_isdst` 等 |
| `timespec` | `tv_sec`（`time_t`）加 `tv_nsec`（`long`，纳秒） |

`tm` 的月份从 0 开始、年份要减去 1900，星期以周日为 0，与 `weekday::c_encoding()` 相同。这几处对应关系在与 `<chrono>` 互相转换时最容易出错。

### 函数

| 函数 | 作用 | `<chrono>` 中的对应 |
|---|---|---|
| `time(p)` | 当前日历时间 | `system_clock::now()` |
| `clock()` | 进程使用的处理器时间 | 无；`steady_clock` 量的是经过的实际时间 |
| `difftime(t1, t0)` | `t1 − t0`，以秒为单位的 `double` | `duration<double>{tp1 - tp0}` |
| `mktime(tm*)` | 本地时间的 `tm` 转为 `time_t`，并规范化 `tm` 的各字段 | `time_zone::to_sys(local_time)` |
| `timegm(tm*)` | UTC 的 `tm` 转为 `time_t` | `sys_days{year_month_day}` 加时分秒 |
| `gmtime`、`gmtime_r` | `time_t` 转为 UTC 的 `tm` | `year_month_day{floor<days>(tp)}`、`hh_mm_ss` |
| `localtime`、`localtime_r` | `time_t` 转为本地时间的 `tm` | `zoned_time{current_zone(), tp}.get_local_time()` |
| `strftime` | 按格式输出 `tm` | `std::format("{:%...}", tp)`（[[time.format]]） |
| `timespec_get(ts, TIME_UTC)` | 纳秒精度的当前 UTC 时间 | `system_clock::now()` |

脚注 233 补充，`strftime` 支持 C 的转换说明符 `C` `D` `e` `F` `g` `G` `h` `r` `R` `t` `T` `u` `V` `z`，以及修饰符 `E` 和 `O`。

## C23 带来的变化

这份概要以 C23 为基准。与以 C17 为基准的旧版相比，有下面几处变化，属于 C++23 之后的新措辞：

| 新增或变化 | 说明 |
|---|---|
| `__STDC_VERSION_TIME_H__` | 值为 `202311L`，用来检测 `<time.h>` 的 C23 特性 |
| `timegm` | `mktime` 的 UTC 版本：把 `tm` 当作 UTC 解释。此前只是 POSIX/BSD 扩展 |
| `gmtime_r`、`localtime_r` | 结果写入调用者提供的 `tm`，没有共享的静态对象。此前是 POSIX 函数 |
| `timespec_getres` | 查询 `timespec_get` 某个时间基准的分辨率 |
| `TIME_MONOTONIC`、`TIME_ACTIVE`、`TIME_THREAD_ACTIVE` | `timespec_get` 可选的时间基准：单调时钟、进程 CPU 时间、线程 CPU 时间 |
| `asctime`、`ctime` | 移出概要，改在附录 D 的 [[depr.ctime]] 中声明，已弃用 {{deprecated}} |

`asctime` 和 `ctime` 被弃用，是因为它们返回指向静态缓冲区的指针，而且在年份超过 4 位等情形下有缓冲区溢出的历史问题。替代品是 `strftime` 或 `std::format`。

!!! impl "libc++ 尚未跟进"
    本机 libc++ 的 `<ctime>` 中没有 `std::timegm`、`std::gmtime_r`、`std::localtime_r`、`std::timespec_getres`，也没有定义 `__STDC_VERSION_TIME_H__`；使用 `std::asctime` 也没有弃用警告。在 macOS 上，`::timegm`、`::gmtime_r` 等作为 POSIX 函数存在于全局命名空间，可以直接使用。

## 与 `<chrono>` 互相转换

```cpp run ok
#include <chrono>
#include <cstdio>
#include <ctime>
using namespace std::chrono;

int main() {
    std::time_t t = 1'709'298'307;                         // 2024-03-01 13:05:07 UTC
    auto tp = system_clock::from_time_t(t);
    std::printf("%d\n", floor<seconds>(tp).time_since_epoch().count() == t);   // 1

    // chrono → tm（UTC），不经过 gmtime 的静态对象
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

`from_time_t` 和 `to_time_t` 只在 `system_clock` 上提供（[[time.clock]]）。分解时间时，`floor<days>` 得到日期部分，余下的部分交给 `hh_mm_ss`。

## 常见误解

!!! pitfall "用 `clock()` 测量经过的时间"
    `clock()` 返回的是处理器时间：线程睡眠、等待 I/O 时不增加，多线程程序中可能比实际经过的时间增长得更快。测量经过的时间用 `steady_clock`。

!!! pitfall "`time_t` 一定是秒"
    C 标准没有规定 `time_t` 的单位和纪元，只有 POSIX 做了规定。32 位的 `time_t` 在 2038-01-19 溢出。`system_clock::to_time_t` 的舍入方式由实现定义（[[time.clock]]）。

!!! pitfall "`mktime` 只是转换，不改实参"
    `mktime` 会规范化 `tm`（例如把 `tm_mday = 32` 进位到下个月），填写 `tm_wday`、`tm_yday`，而且按本地时区解释输入。把 UTC 的 `tm` 交给 `mktime`，结果会差一个时区偏移。C23 把 `timegm` 标准化，就是为了解决这个问题。
