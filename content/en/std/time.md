---
title: Time library
summary: "A guide to Clause 30: <chrono> builds time units into the type system with three types, duration, time_point and clock, and C++20 adds calendars, time zones and formatting on top; the synopsis specifies the minimum bit widths of the duration aliases and how the literals are brought in; C++26 adds std::hash for chrono types."
updated: 2026-10-19
---

!!! tldr
    - The skeleton of `<chrono>` is three types: a duration is a tick count times a tick period, a time_point is a duration plus a clock, and a clock provides an epoch and `now()`. Units are written into the types, so using the wrong unit fails to compile.
    - `system_clock` is specified to measure Unix Time (every day is exactly 86400 seconds), so C++20 calendar types and time points convert by pure arithmetic.
    - The aliases from `nanoseconds` to `hours` are all guaranteed to cover at least about ±292 years; `days`, `months` and `years` cover the whole range of `year`, [−32767, 32767].
    - `using namespace std::chrono;` also brings in literals like `1s` and `500ms`.
    - Since C++26, `duration`, `time_point` and the calendar types have `std::hash` specializations and can be used directly as keys in unordered containers.

## Why put units in the type

```cpp run title="chrono-units.cpp" ok
#include <chrono>
using namespace std::chrono;

milliseconds timeout = 2s;          // OK: seconds to milliseconds just multiplies by 1000
// seconds s = 1500ms;              // error: needs division, which truncates
seconds s = duration_cast<seconds>(1500ms);   // explicit truncation: 1s
static_assert(1s + 1ms == 1001ms);  // different units add directly
int main() {}
```

In C interfaces, whether `sleep(5)` is 5 seconds or 5 milliseconds, and whether a `time_t` and a `clock_t` can be subtracted, depend entirely on documentation and convention. `<chrono>` encodes this information into types: `milliseconds{1500}` stores only the integer 1500, and the millisecond unit lives in the type. The multiplication and division factors needed to change units are computed by the compiler at compile time; conversions that may lose precision must be written explicitly.

## The skeleton: three core types

C++11's `<chrono>` ([[N2661]]) had only three things, and they remain the skeleton of the whole clause:

```text
clock ──now()──▶ time_point<Clock, Duration> ──time_since_epoch()──▶ duration<Rep, Period>
```

- [[time.duration|duration]]: an arithmetic value `count()` plus a compile-time rational period `Period` ([[ratio]]).
- [[time.point|time_point]]: a duration plus a clock type. The clock type serves here only as a tag saying which instant the duration is measured from; that instant is the clock's epoch ([[g:clock-epoch]]). time_points of different clocks are different types and can be neither compared nor subtracted.
- [[time.clock|clock]]: a type providing `now()`, meeting the [[g:cpp17clock]] requirements ([[time.clock.req]]).

C++20's [[P0355R7]] added three parts to the skeleton, largely adopting Howard Hinnant's date/tz library:

- Calendars ([[time.cal]]): dates stored as year/month/day fields, such as `year_month_day`, convertible to and from `sys_days` (a time_point in units of days). `system_clock` is specified as [[g:unix-time]], with every day exactly 86400 seconds, so conversion between dates and time points is pure arithmetic with no table lookups.
- Time zones ([[time.zone]]): the IANA time zone database, conversion between `local_time` and `sys_time`, leap seconds and `utc_clock`.
- Text I/O ([[time.format]], [[time.parse]]): `%Y-%m-%d`-style format specs in `std::format` ([[P1361R2]]) and the corresponding `parse`.

## Contents of the clause ([time.general])

¶1 This clause describes the chrono library and the C time functions; Table 130 lists the subclauses:

| Subclause | Contents | Notes on this site |
|---|---|---|
| [time.clock.req] | the *Cpp17Clock* and *Cpp17TrivialClock* requirements | [[time.clock.req]] |
| [time.traits] | `treat_as_floating_point`, `duration_values`, `common_type` specializations, `is_clock` | [[time.traits]] |
| [time.duration] | the class template `duration` | [[time.duration]] |
| [time.point] | the class template `time_point` | [[time.point]] |
| [time.clock] | clocks such as `system_clock`, `steady_clock`, `utc_clock` and `file_clock`, and `clock_cast` | [[time.clock]] |
| [time.cal] | the civil calendar: types such as `year`, `month` and `year_month_day`, and the `/` syntax | [[time.cal]] |
| [time.hms], [time.12] | `hh_mm_ss`; 12/24-hour functions such as `is_am` and `make12` | [[time.hms]] |
| [time.zone] | the time zone database, `time_zone`, `zoned_time`, leap seconds | [[time.zone]] |
| [time.format], [time.parse] | formatting and parsing | [[time.format]], [[time.parse]] |
| [time.hash] | hash support {{c++26}} | this page |
| [ctime.syn] | the C time functions, header `<ctime>` | [[ctime.syn]] |

Except for [ctime.syn], these facilities are all in `<chrono>`. Some related material is not in this clause: the rules for the `_for` and `_until` timeout functions of the thread library are in [[thread.req.timing]]; `filesystem::file_time_type` is just `time_point<file_clock>` ([[fs.filesystem.syn]]); and `time_get` and `time_put` in `<locale>` are a separate, older interface unrelated to `<chrono>` ([[category.time]]).

## What the synopsis specifies ([time.syn])

Most of the `<chrono>` synopsis just collects declarations from the subclauses, but the following points are specified only in the synopsis.

### Minimum bit widths of the duration aliases

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

These widths are calculated:

- From `nanoseconds` to `hours`, each alias can represent at least about ±292 years (2⁶³ ns ≈ 292 years, 2⁵⁴ µs ≈ 571 years, 2³⁴ s ≈ 544 years). That is, every small unit covers at least a few centuries on either side of 1970.
- The widths of `days`, `months` and `years` are chosen to cover the range of `year`, [−32767, 32767] ([[time.cal]]): 2²⁴ days is about 45,900 years, 2¹⁹ months about 43,690 years, and 2¹⁶ years is 65,536 years.
- The period of `years` is 146097/400 days, the average Gregorian year length (400 years have 146097 days); `months` is 1/12 of it. So `years{1}` is neither 365 nor 366 days but 365.2425 days, that is, 31,556,952 seconds. Adding it to a `sys_days` gives a result with hours, minutes and seconds; adding a calendar year should be done on a `year_month_day` ([[time.cal]]).

`nanoseconds` guarantees only ±292 years, and this is the most common source of overflow in chrono; see [[time.duration]].

### Literals and constants

- The duration literals `h`, `min`, `s`, `ms`, `us` and `ns`, and the calendar literals `d` and `y`, are all declared in `std::inline literals::inline chrono_literals`, so both `using namespace std::literals;` and `using namespace std::chrono_literals;` bring them in.
- The synopsis also has the line `namespace std::chrono { using namespace literals::chrono_literals; }`, so `using namespace std::chrono;` brings the literals in too. Most examples need only that one line.
- The calendar constants `last`, `Sunday` through `Saturday`, and `January` through `December` are all `inline constexpr` variables.

The suffix `s` does not conflict with `std::string`'s `""s`: the former applies only to number literals, the latter only to string literals ([[time.duration.literals#8]]).

## Hash support ([time.hash]) {{c++26}}

```cpp run title="chrono-hash.cpp" ok
#include <cassert>
#include <chrono>
#include <unordered_set>
using namespace std::chrono;

int main() {
  std::unordered_set<seconds> s{1s, 2s, 1s};
  assert(s.size() == 2);
  // February 30, 2024 is !ok(), but hashes all the same
  std::unordered_set<year_month_day> d{
      2024y/February/29, 2024y/February/30};
  assert(d.size() == 2);
}
```

C++26's [[P2592R3]] added these specializations. Before that, putting `seconds` or `year_month_day` in an `unordered_set` required writing your own hasher.

- ¶1 `hash<duration<Rep, Period>>` is enabled if and only if `hash<Rep>` is enabled ([[unord.hash]]). The member function is not guaranteed `noexcept`, because `Rep` can be a class type that throws.
- ¶2 `hash<time_point<Clock, Duration>>` is enabled if and only if `hash<Duration>` is enabled.
- ¶3 The specializations for the 15 calendar types are always enabled. Note 1 points out that they meet the *Cpp17Hash* requirements even when called on objects for which `ok()` is `false`. Calendar types are allowed to hold invalid values like `February/30`, and hashing must not break because of it.
- ¶4 `hash<zoned_time<Duration, TimeZonePtr>>` is enabled if and only if both `hash<Duration>` and `hash<TimeZonePtr>` are enabled.
- ¶5 `hash<leap_second>` is always enabled.

`duration`'s `==` can compare across units (`1s == 1000ms`), but `hash<seconds>` and `hash<milliseconds>` are two different specializations, and the standard does not require them to give the same hash value for equal values. An unordered container's key type is fixed, so this does not cause errors; just don't expect hash values to agree across types.

## The state of libc++

The examples on this site are verified with Homebrew Clang 23 + libc++. In our tests:

| Part | Status |
|---|---|
| `duration`, `time_point`, `system_clock`, `steady_clock`, `file_clock` | available |
| calendar types, `hh_mm_ss`, 12/24-hour functions | available |
| `std::format` and `operator<<` for chrono | available (except the time-zone-related parts) |
| `hash` specializations | available |
| `utc_clock`, `tai_clock`, `gps_clock`, `tzdb`, `time_zone`, `zoned_time`, `leap_second` | unavailable: the `__config_site` of our build defines `_LIBCPP_HAS_TIME_ZONE_DATABASE` as 0, and `-fexperimental-library` does not change that |
| `clock_cast`, `parse` | not implemented |

So the examples in [[time.zone]] and [[time.parse]] cannot run in our setup, as those pages note separately. They can be tried on Compiler Explorer with a recent GCC (libstdc++) or MSVC.

## Evolution

| Version | Change |
|---|---|
| C++11 | `duration`, `time_point`, `system_clock`, `steady_clock`, `high_resolution_clock` ([[N2661]]) |
| C++14 | duration literals; more functions become `constexpr` |
| C++17 | `floor`, `ceil`, `round`, `abs` |
| C++20 | calendars, time zones, new clocks such as `utc_clock`, `clock_cast`, `hh_mm_ss`, the aliases `days` through `years`, `is_clock` ([[P0355R7]]); integration with `std::format` ([[P1361R2]]); `system_clock` specified as Unix Time |
| C++23 | chrono formatting defaults to the "C" locale, using localized formats only with the `L` option (as a defect fix against C++20) |
| C++26 | `hash` support ([[P2592R3]]) |
| new wording after C++23 | `<ctime>` aligned with C23: `timegm`, `gmtime_r`, `localtime_r` and `timespec_getres` added; `asctime` and `ctime` moved to Annex D ([[depr.ctime]]) |
