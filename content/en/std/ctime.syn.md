---
title: Header <ctime> synopsis
summary: "<ctime> is C23's <time.h>: time_t, tm, timespec and the related functions; gmtime and localtime return a shared static object and are not guaranteed to avoid data races; C23 adds timegm, gmtime_r, localtime_r and timespec_getres; and how to convert to and from <chrono>."
updated: 2026-10-19
---

!!! tldr
    - The contents of `<ctime>` are the same as C23's `<time.h>`; C++ adds only one rule: `gmtime` and `localtime` are not required to avoid data races.
    - These two functions return a pointer to the same static `tm` object, so a second call overwrites the result of the first; when thread safety is needed, use `gmtime_r`, `localtime_r` or `<chrono>`.
    - `timegm`, `gmtime_r`, `localtime_r` and `timespec_getres`, new in C23, have entered the synopsis; libc++ in our tests does not yet provide them in `std`.
    - `asctime` and `ctime` are deprecated and have moved to Annex D.
    - The bridge between `<ctime>` and `<chrono>` is `system_clock::to_time_t`/`from_time_t`; for broken-down time, prefer `year_month_day` and `hh_mm_ss`.

## The shared static buffer (¶2)

```cpp run unspecified
#include <cstdio>
#include <ctime>

int main() {
  std::time_t t1 = 1'709'298'307, t2 = 0;
  std::tm* a = std::gmtime(&t1);
  std::tm* b = std::gmtime(&t2);
  std::printf("%d %d\n", a == b, a->tm_year + 1900);   // in our tests: 1 1970
}
```

The pointer returned by `gmtime` and `localtime` points to a static `tm` object inside the library. In our tests the two calls return the same address, and the second call overwrites `*a` with 1970. The C standard allows the two functions to share the same object, so the result of `a == b` is unspecified.

In a single thread this just means the result is overwritten; when two threads call them at the same time, they write the same object without synchronization, which is a data race.

¶2 The standard states explicitly that `gmtime` and `localtime` are not required to avoid data races. [[res.on.data.races]] generally requires standard library functions not to modify objects other than their arguments; these two functions are exceptions. The same is true of `asctime` and `ctime` in Annex D ([[depr.ctime#2]]).

The thread-safe alternatives are `gmtime_r` and `localtime_r`, where the caller provides the `tm` buffer, or simply `<chrono>`.

`localtime` and `mktime` also depend on the process's time zone setting, which under POSIX is the `TZ` environment variable, another piece of global state. A `time_zone` in `<chrono>` is an explicitly passed object, and different threads can use different time zones at the same time ([[time.zone]]).

## Synopsis (¶1)

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

¶1 The contents of `<ctime>` are the same as the C standard library header `<time.h>`, referring to 7.29 of C23 (ISO/IEC 9899:2024).

### Types

| Type | Meaning |
|---|---|
| `time_t` | Calendar time. C does not specify the encoding; POSIX specifies seconds since 1970-01-01 UTC (not counting leap seconds), numerically the same as `sys_seconds` |
| `clock_t` | The return type of `clock()`, representing processor time, in units of `1/CLOCKS_PER_SEC` seconds |
| `tm` | Broken-down time: `tm_year` (since 1900), `tm_mon` (0–11), `tm_mday` (1–31), `tm_wday` (Sunday is 0), `tm_yday`, `tm_isdst`, etc. |
| `timespec` | `tv_sec` (`time_t`) plus `tv_nsec` (`long`, nanoseconds) |

In `tm`, months start at 0, 1900 must be subtracted from the year, and weekdays have Sunday as 0, the same as `weekday::c_encoding()`. These correspondences are where conversions to and from `<chrono>` most often go wrong.

### Functions

| Function | Purpose | Counterpart in `<chrono>` |
|---|---|---|
| `time(p)` | Current calendar time | `system_clock::now()` |
| `clock()` | Processor time used by the process | None; `steady_clock` measures real elapsed time |
| `difftime(t1, t0)` | `t1 − t0` as a `double` in seconds | `duration<double>{tp1 - tp0}` |
| `mktime(tm*)` | Converts a local-time `tm` to `time_t` and normalizes the fields of the `tm` | `time_zone::to_sys(local_time)` |
| `timegm(tm*)` | Converts a UTC `tm` to `time_t` | `sys_days{year_month_day}` plus hours, minutes and seconds |
| `gmtime`, `gmtime_r` | Converts `time_t` to a UTC `tm` | `year_month_day{floor<days>(tp)}`, `hh_mm_ss` |
| `localtime`, `localtime_r` | Converts `time_t` to a local-time `tm` | `zoned_time{current_zone(), tp}.get_local_time()` |
| `strftime` | Formats a `tm` | `std::format("{:%...}", tp)` ([[time.format]]) |
| `timespec_get(ts, TIME_UTC)` | Current UTC time with nanosecond precision | `system_clock::now()` |

Footnote 233 adds that `strftime` supports the C conversion specifiers `C` `D` `e` `F` `g` `G` `h` `r` `R` `t` `T` `u` `V` `z` and the modifiers `E` and `O`.

## What C23 changed

This synopsis is based on C23. Compared with the older version based on C17, the following changed; this is wording new after C++23:

| Addition or change | Description |
|---|---|
| `__STDC_VERSION_TIME_H__` | Value `202311L`, for detecting the C23 features of `<time.h>` |
| `timegm` | The UTC version of `mktime`: interprets the `tm` as UTC. Previously only a POSIX/BSD extension |
| `gmtime_r`, `localtime_r` | Write the result into a caller-provided `tm`, with no shared static object. Previously POSIX functions |
| `timespec_getres` | Queries the resolution of a time base of `timespec_get` |
| `TIME_MONOTONIC`, `TIME_ACTIVE`, `TIME_THREAD_ACTIVE` | Optional time bases for `timespec_get`: a monotonic clock, process CPU time, thread CPU time |
| `asctime`, `ctime` | Removed from the synopsis and declared instead in [[depr.ctime]] in Annex D; deprecated {{deprecated}} |

`asctime` and `ctime` are deprecated because they return pointers to static buffers and have a history of buffer overflows, for example with years of more than 4 digits. The replacements are `strftime` or `std::format`.

!!! impl "libc++ has not caught up"
    The `<ctime>` of libc++ in our tests has no `std::timegm`, `std::gmtime_r`, `std::localtime_r` or `std::timespec_getres`, and does not define `__STDC_VERSION_TIME_H__`; using `std::asctime` gives no deprecation warning either. On macOS, `::timegm`, `::gmtime_r` and the like exist in the global namespace as POSIX functions and can be used directly.

## Converting to and from `<chrono>`

```cpp run ok
#include <chrono>
#include <cstdio>
#include <ctime>
using namespace std::chrono;

int main() {
    std::time_t t = 1'709'298'307;                         // 2024-03-01 13:05:07 UTC
    auto tp = system_clock::from_time_t(t);
    std::printf("%d\n", floor<seconds>(tp).time_since_epoch().count() == t);   // 1

    // chrono → tm (UTC), without going through gmtime's static object
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

`from_time_t` and `to_time_t` are provided only on `system_clock` ([[time.clock]]). To break a time down, `floor<days>` gives the date part, and the remainder goes to `hh_mm_ss`.

## Common misconceptions

!!! pitfall "Measuring elapsed time with `clock()`"
    `clock()` returns processor time: it does not advance while a thread sleeps or waits for I/O, and in a multithreaded program it can grow faster than the real elapsed time. Use `steady_clock` to measure elapsed time.

!!! pitfall "`time_t` is always seconds"
    The C standard does not specify the unit or epoch of `time_t`; only POSIX does. A 32-bit `time_t` overflows on 2038-01-19. The rounding of `system_clock::to_time_t` is implementation-defined ([[time.clock]]).

!!! pitfall "`mktime` only converts and does not modify its argument"
    `mktime` normalizes the `tm` (for example, carrying `tm_mday = 32` into the next month), fills in `tm_wday` and `tm_yday`, and interprets the input in the local time zone. Passing a UTC `tm` to `mktime` gives a result that is off by a time zone offset. C23 standardized `timegm` precisely to solve this problem.
