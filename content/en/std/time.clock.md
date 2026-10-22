---
title: Clocks
summary: "The clocks the standard provides: system_clock (Unix Time), steady_clock (monotonic), high_resolution_clock, the leap-second-counting utc_clock, tai_clock, gps_clock, file_clock and the pseudo-clock local_t, and how clock_cast converts between any two clocks by way of sys or utc."
updated: 2026-10-19
---

!!! tldr
    - Use `steady_clock` to measure elapsed time: it is never adjusted, so subtracting two `now()` calls gives the time elapsed. `high_resolution_clock` may be just an alias of one of the other two, and has no portable use.
    - `system_clock` represents Unix Time: counted from 1970-01-01 00:00:00 UTC without leap seconds, so every day is exactly 86400 seconds and converts directly to and from dates.
    - `utc_clock` counts leap seconds; `tai_clock` and `gps_clock` insert none; converting among them takes a leap second table lookup or adding/subtracting a constant.
    - `local_t` is not a clock; `local_time` represents a clock-face time whose time zone is not yet determined, and is a different type from `sys_time`.
    - `clock_cast` can convert between any two clocks as long as each clock provides one set of conversion functions, to sys or to utc, and it requires the best path to be unique.

## Which clock to choose

| Question | Clock |
|---|---|
| How long did this code take? | `steady_clock` |
| What time is it now? Need to convert to and from dates and `time_t` | `system_clock` |
| Need UTC accurate to leap seconds, atomic time, GPS time | `utc_clock`, `tai_clock`, `gps_clock` |
| When was this file modified? | `file_clock` |
| 8 a.m. local time, time zone not yet decided | `local_t` (a pseudo-clock) |

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
  std::cout << duration<double, std::milli>{elapsed} << '\n';  // to floating point: implicit
}
```

[[time.clock.general#1]] specifies that the types defined in this subclause all meet the *Cpp17TrivialClock* requirements ([[time.clock.req]]) unless otherwise specified. The ones otherwise specified are `utc_clock`, `tai_clock` and `gps_clock` (whose `now()` may throw) and `local_t` (which is not a clock at all).

## steady_clock [time.clock.steady]

¶1 The time points of `steady_clock` never decrease as physical time advances, and advance at a steady rate relative to real time. In other words, the clock cannot be adjusted.

Its epoch is unspecified, usually system boot time, so its time points have no civil meaning, cannot be converted to dates, and there is no `to_sys`. It is suited to exactly one thing: subtracting two `now()` calls to get an elapsed time.

Its `time_point` is written `time_point<unspecified, duration>`, allowing implementations to have it share a time_point type with another clock.

## high_resolution_clock [time.clock.hires]

¶1 `high_resolution_clock` is the clock with the shortest tick period; it may be an alias of `system_clock` or `steady_clock`, and its `is_steady` is unspecified.

The same measurement code might use a monotonic clock on one implementation and be affected by system time adjustments on another. In libc++ in our tests it is `steady_clock`, both counting in nanoseconds. Use `steady_clock` directly to measure elapsed time.

## system_clock: Unix Time [time.clock.system]

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

### Seconds without leap seconds

¶1 `system_clock` represents the system-wide real-time clock, that is, wall-clock time. `sys_time<Duration>` measures time since 1970-01-01 00:00:00 UTC excluding leap seconds, which is what is commonly called [[g:unix-time]].

The standard's example gives two values: the `time_since_epoch()` of 1970-01-01 is `0s`; that of 2000-01-01 is `946'684'800s`, exactly `10'957 * 86'400s`. 22 leap seconds were actually inserted during those 30 years, but in `sys_time` every day is 86400 seconds.

The benefit of this specification is that converting between `sys_days` and `year_month_day` is pure arithmetic with no leap second table ([[time.cal]]). The cost is that a leap second has no place in `sys_time`: 2016-12-31 23:59:60 UTC cannot be distinguished from the next second, 00:00:00. When you need to distinguish them, use `utc_clock`.

C++11 said only that `system_clock` is wall-clock time and did not specify an epoch, although every implementation used the Unix epoch. C++20's [[P0355R7]] fixed it as Unix Time, and the calendar library is built on that.

### Members [time.clock.system.members]

¶1 The type of `rep` is unspecified, but `system_clock::duration::min() < system_clock::duration::zero()` must hold. Note 1 points out that this means `rep` is a signed type: time points before 1970 must be representable.

¶2 `to_time_t` and ¶3 `from_time_t` convert between `time_t` and `time_point`, both taking the coarser of the two precisions; whether excess precision is rounded or truncated is implementation-defined. This pair of functions is the bridge to the C interfaces ([[ctime.syn]]).

`is_steady` is unspecified, and it is `false` on mainstream implementations: an administrator changing the time or NTP synchronization can both make it jump. Daylight saving time does not affect it, because it represents UTC.

### Output and parsing [time.clock.system.nonmembers]

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

¶2 `os << sys_time<Duration>` is equivalent to formatting with `"{:L%F %T}"`. ¶1 requires the count of `Duration` not to be floating point and `Duration{1} < days{1}`; `sys_days`, with a precision of a day or coarser, goes through the overload in ¶4 and outputs only the date.

¶6 `from_stream` parses per [[time.parse]]. If the format uses `%z` and a UTC offset is parsed, the offset is subtracted from the result: parsing `2024-01-01 08:00:00 +0800` gives a `sys_time` of 00:00 UTC.

## local_t: local time with the time zone undetermined [time.clock.local]

```cpp
struct local_t {};
template<class Duration> using local_time = time_point<local_t, Duration>;
using local_seconds = local_time<seconds>;
using local_days    = local_time<days>;
```

¶1 `local_time<Duration>` is parameterized by the pseudo-clock `local_t`. `local_t` has no `now()` and does not meet the clock requirements. A `local_time` represents local time with respect to a not-yet-specified time zone ([[g:local-time]]). Apart from getting the current time, every time-point operation `sys_time` can do, `local_time` can do too.

Why not just use `sys_time` for local time? 08:00 in `sys_time` is a definite physical instant; 08:00 in `local_time` is three different instants in Beijing, London and New York, and on a daylight saving transition day it may not exist or may occur twice. Making them different types lets the compiler catch the mistake of using a local time as UTC. Conversion between the two must go through a `time_zone` ([[time.zone]]).

¶3 `os << local_time` wraps `time_since_epoch()` in a `sys_time` for output, with the same format but representing no time zone. The `from_stream` of ¶5 does not subtract a parsed `%z` offset from the result, since local time is not aligned to UTC in the first place.

## utc_clock: counting leap seconds [time.clock.utc]

```cpp
class utc_clock {
public:
  using rep = a signed arithmetic type;
  // period, duration, time_point, is_steady similar to the above
  static time_point now();
  template<class Duration>
    static sys_time<common_type_t<Duration, seconds>> to_sys(const utc_time<Duration>& t);
  template<class Duration>
    static utc_time<common_type_t<Duration, seconds>> from_sys(const sys_time<Duration>& t);
};
```

### How far it differs from sys_time [time.clock.utc.overview]

¶1 `utc_clock` and its `utc_time` also count from 1970-01-01 00:00:00 UTC, but include leap seconds. The `utc_time` of 2000-01-01 is `946'684'822s`; the 22 extra seconds over `sys_time` are exactly the leap seconds inserted in the meantime. Note 1 adds that UTC itself starts at 1972-01-01 00:00:10 TAI; to use that instant as the origin, add or subtract `63'072'000s`.

¶2 Unless the implementation can guarantee that `now()` does not propagate an exception, `utc_clock` is not a *Cpp17TrivialClock*. Note 2 points out that `from_sys(system_clock::now())` is not `noexcept`: `from_sys` has to consult the leap second table in the time zone database ([[time.zone]]), and the first access to the database may throw if loading fails.

### Conversion during a leap second [time.clock.utc.members]

¶1 `now()` returns `from_sys(system_clock::now())`, or a more accurate value. Implementations usually have no dedicated UTC clock; they read the system time and add the number of leap seconds.

¶3 The difference between the result of `from_sys(t)` and `t`'s `time_since_epoch()` is the total number of leap seconds inserted between 1970-01-01 and `t`. If `t` is exactly the instant a leap second is inserted, it counts as already inserted. The standard's example shows this boundary (a leap second was inserted at 2015-07-01, with 25 accumulated before it):

```cpp
auto diff = [](sys_time<nanoseconds> t) {
  return utc_clock::from_sys(t).time_since_epoch() - t.time_since_epoch();
};
auto t = sys_days{July/1/2015} - 2ns;
assert(diff(t)       == 25s);   // 2ns before insertion
assert(diff(t + 1ns) == 25s);   // 1ns before insertion
assert(diff(t + 2ns) == 26s);   // exactly the insertion instant: counts as inserted
assert(diff(t + 3ns) == 26s);
```

¶2 `to_sys(u)` returns the `t` such that `from_sys(t) == u`. If `u` falls within a positive leap second, no such `t` exists; in that case the leap second is treated as not inserted, and the last value representable in `sys_time` before the insertion is returned. For example, 23:59:60.500 as a `utc_time<milliseconds>` converts to 23:59:59.999 as a `sys_time<milliseconds>`.

### Output and leap second information [time.clock.utc.nonmembers]

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

Per the standard, the output is in order 23:59:59.500 (leap=0, elapsed=25s), 23:59:60.000 and 23:59:60.500 (leap=1, elapsed=26s), and 00:00:00.000 the next day (leap=0, elapsed=26s). libc++ in our tests cannot compile this example: its build has the time zone database disabled, so `utc_clock` does not exist, and `clock_cast` is not implemented yet either.

¶1 `os << utc_time` formats with `"{:L%F %T}"`, with the seconds field showing `60` during a leap second.

¶5 `leap_second_info` has just two data members: `bool is_leap_second` and `seconds elapsed`. ¶6 In `get_leap_second_info(ut)`, `is_leap_second` says whether `ut` falls within a positive leap second; `elapsed` is the total number of leap seconds from 1970 to `ut`, including the current one if `ut` is in a leap second.

## tai_clock and gps_clock [time.clock.tai] [time.clock.gps]

Neither of these clocks inserts leap seconds. Every time UTC inserts a leap second, it falls one more second behind them. Converting between them and `utc_clock` is just adding or subtracting a constant:

| Clock | Epoch | Relation to UTC | `to_utc` |
|---|---|---|---|
| `tai_clock` | 1958-01-01 00:00:00 TAI | 10 seconds ahead of UTC in 1958, and 1 second more ahead for each leap second after | subtract `378691210s` |
| `gps_clock` | 00:00:00 UTC on the first Sunday of January 1980 | a constant 19 seconds behind TAI | add `315964809s` |

[[time.clock.tai.overview#1]] gives an example: 22 positive leap seconds had been inserted by 2000-01-01, so 2000-01-01 00:00:00 UTC corresponds to 2000-01-01 00:00:32 TAI, that is, 22 seconds plus the initial 10.

[[time.clock.gps.overview#1]] explains where GPS being 19 seconds behind TAI comes from: the 10-second offset between 1958 and 1970, plus the 9 leap seconds inserted between 1970 and 1980.

The two constants are derived in the notes to [[time.clock.tai.members#2]] and [[time.clock.gps.members#2]]: `378691210s` is the 4383 days from 1958 to 1970 plus 10 seconds; `315964809s` is the number of days from 1970-01-01 to the first Sunday of January 1980 plus 9 seconds.

`to_utc` and `from_utc` are both `noexcept`, because they differ from UTC by only a constant and need no table lookup; the lookup happens between UTC and sys. So the `now()` of these two clocks may throw just the same, and overview ¶2 says that, like `utc_clock`, they cannot be assumed to be *Cpp17TrivialClock*.

The nonmembers subclauses of both clocks specify output with `"{:L%F %T}"`, with `%Z` showing `TAI` and `GPS` respectively ([[time.format]]). The standard's examples are `2000-01-01 00:00:00 UTC == 2000-01-01 00:00:32 TAI` and `2000-01-01 00:00:00 UTC == 2000-01-01 00:00:13 GPS`.

## file_clock [time.clock.file]

[[time.clock.file.overview#1]] specifies that `file_clock` is an alias for some type meeting *Cpp17TrivialClock*, with a signed arithmetic `rep`, used as the clock of `filesystem::file_time_type` ([[fs.filesystem.syn]]). The epoch is unspecified, and `now()` is `noexcept`. Note 1 says the type it denotes may be in another namespace, such as `std::filesystem`.

[[time.clock.file.members#1]] requires this type to provide exactly one of the following two sets of static functions: `to_sys` and `from_sys`, or `to_utc` and `from_utc`. The implementation chooses based on the nature of the file system's timestamps: the sys versions if timestamps are Unix Time, the utc versions if they count leap seconds.

Exactly one set, so that `clock_cast` can automatically pick a unique conversion path (see below). User code should write `clock_cast<system_clock>(ft)` rather than assume `file_clock::to_sys` exists.

!!! impl "libc++'s file_clock"
    In libc++, `file_clock` is `std::filesystem::_FilesystemClock`. On platforms supporting `__int128`, `rep` is `__int128`, the period is nanoseconds, the epoch is the same as `system_clock`'s, and it provides `to_sys` and `from_sys`. libc++ has no `clock_cast` yet, so for now you can only call `file_clock::to_sys` directly.

## Cross-clock conversion [time.clock.cast] {{c++20}}

### clock_time_conversion [time.clock.conv]

```cpp
template<class DestClock, class SourceClock>
struct clock_time_conversion {};
```

¶1 `clock_time_conversion<DestClock, SourceClock>` is a trait class. Its specializations must provide a `const` `operator()` taking a `time_point<SourceClock, Duration>` and returning a `time_point<DestClock, OtherDuration>` representing the same instant; `OtherDuration` is decided by each specialization based on the input. A program may specialize it as long as at least one template argument is a user-defined clock type.

¶2 The implementation provides the following sets of specializations:

| Subclause | Specializations | Effect |
|---|---|---|
| [time.clock.cast.id] | `<Clock, Clock>`, `<system_clock, system_clock>`, `<utc_clock, utc_clock>` | returns its argument unchanged |
| [time.clock.cast.sys.utc] | `<utc_clock, system_clock>`, `<system_clock, utc_clock>` | `utc_clock::from_sys` / `to_sys` |
| [time.clock.cast.sys] | `<system_clock, S>`, `<D, system_clock>` | `S::to_sys(t)` / `D::from_sys(t)` |
| [time.clock.cast.utc] | `<utc_clock, S>`, `<D, utc_clock>` | `S::to_utc(t)` / `D::from_utc(t)` |

The last two sets have two layers of requirements. *Constraints* require the corresponding static function call to be well-formed; if not, the `operator()` of that specialization is unusable. *Mandates* require the return type to really be a time_point of the destination clock: a clock that provides a function named `to_sys` returning something else makes the program ill-formed, rather than silently unusable.

Why are the identity conversions and the conversions between sys and utc written as separate full specializations? Look at the four partial specializations of the last two sets: `<utc_clock, system_clock>` matches both `<utc_clock, S>` and `<D, system_clock>`, neither of which is more specialized than the other, so choosing a partial specialization would be ambiguous ([[temp.spec.partial.order]]). The same goes for `<system_clock, system_clock>`, `<system_clock, utc_clock>` and `<utc_clock, utc_clock>`. Providing full specializations for these combinations removes the ambiguity.

### clock_cast [time.clock.cast.fn]

```cpp
template<class DestClock, class SourceClock, class Duration>
  auto clock_cast(const time_point<SourceClock, Duration>& t);
```

¶1 `clock_cast` requires at least one of the following five conversion expressions to be well-formed. The fewer calls to `operator()` an expression makes, the better it is.

| Number | Path | Calls |
|---|---|---|
| ¶1.1 | Source → Dest | 1 |
| ¶1.2 | Source → sys → Dest | 2 |
| ¶1.3 | Source → utc → Dest | 2 |
| ¶1.4 | Source → sys → utc → Dest | 3 |
| ¶1.5 | Source → utc → sys → Dest | 3 |

¶2 Among the well-formed expressions, there must be a unique best one, otherwise the program is ill-formed. ¶3 The result of the best expression is returned.

So N clocks do not need N² conversions. Each clock only has to provide one set of `to_sys`/`from_sys` or `to_utc`/`from_utc` to convert to and from every other clock. Some concrete examples:

- `clock_cast<utc_clock>(sys_time)` takes ¶1.1, using a full specialization.
- `clock_cast<tai_clock>(sys_time)`: `tai_clock` has only `from_utc`, so ¶1.1 and ¶1.2 are both ill-formed; ¶1.3 first converts to utc with `<utc_clock, system_clock>`, then uses `tai_clock::from_utc`, 2 calls.
- `clock_cast<gps_clock>(tai_time)` goes tai → utc → gps, also ¶1.3.
- Whether `clock_cast<system_clock>(file_time)` takes ¶1.1 or ¶1.3 depends on which set of functions `file_clock` provides, which users need not care about.

The unique-best requirement can fail. Suppose a user has two clocks `A` and `B`, both providing both the sys and utc sets, with no direct specialization between them. `clock_cast<B>(a)` can take either ¶1.2 or ¶1.3, both with 2 calls; the best is not unique, and the program is ill-formed. This is why `file_clock` must provide exactly one set: conversion paths between the standard clocks are always unique.

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

libc++ in our tests cannot compile this example: `tai_clock` and `gps_clock` are unavailable, and `clock_cast` is not implemented. The output in the comments is taken from the standard's examples.

## Clock adjustments and waiting functions

The timeout rules of the thread library are in [[thread.req.timing]], and they rely on the distinctions among clocks in this subclause:

- Functions ending in `_for` (`sleep_for`, `wait_for`, `try_lock_for`) take a duration, a relative timeout, which implementations should measure with a steady clock ([[thread.req.timing#3]]).
- Functions ending in `_until` take a time point, an absolute timeout, which implementations should measure with the clock the time point belongs to ([[thread.req.timing#4]]). If the clock is adjusted during the wait, the wait becomes correspondingly longer or shorter.

```cpp
std::this_thread::sleep_for(10s);                          // about 10 seconds, unaffected by changing the system time
std::this_thread::sleep_until(system_clock::now() + 10s);  // if the system time is set back 1 hour meanwhile, sleeps 1 hour longer
std::this_thread::sleep_until(steady_clock::now() + 10s);  // unaffected
```

The choice is driven by semantics. To wait 10 seconds, use `_for` or `steady_clock`. Only to wait until 9 a.m. tomorrow use `_until` with `system_clock`: if the user sets the clock forward, the program should indeed wake earlier.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

The `from_stream` of each clock ([[time.clock.system.nonmembers#6]], [[time.clock.utc.nonmembers#3]], ¶3 of the tai and gps nonmembers, [[time.clock.file.nonmembers#2]]) parses per [[time.parse]], setting `failbit` and leaving the target unmodified on failure; a parsed `%Z` is stored in `abbrev`, and a parsed `%z` is stored in `offset` and subtracted from the result. Only the `local_time` version does not subtract.

[[time.clock.tai.members#1]], [[time.clock.gps.members#1]]: `now()` returns `from_utc(utc_clock::now())`, or a more accurate value.

[[time.clock.file.members#1]] also requires the conversion functions of `file_clock` to be consistent with the conversions of `utc_clock`, `tai_clock` and `gps_clock`, with the precision of the result computed from the precision of the input.

</details>

## Common pitfalls

!!! pitfall "Measuring elapsed time with system_clock"
    `auto t0 = system_clock::now(); work(); auto dt = system_clock::now() - t0;` may give a negative or huge value after an NTP adjustment, a virtual machine migration, or a user changing the time. Use `system_clock` only to answer what time it is; measure elapsed time with `steady_clock`.

!!! pitfall "Assuming sys_time can represent leap seconds"
    Parsing a timestamp containing `23:59:60` into a `sys_time` does not give the 60th second. Where leap seconds must be handled precisely (finance, astronomy, satellite data), use `utc_time`, and use `get_leap_second_info` to identify time points within a leap second.

## Questions

!!! question "Question 1"
    For a `utc_time` during a leap second, `utc_clock::to_sys` returns the last value representable in `sys_time` before the leap second. Why not return the next second's 00:00:00?

<details markdown="1">
<summary>Answer</summary>

This keeps `to_sys` monotonically non-decreasing: time points within the leap second all map to 23:59:59.999…, and 00:00:00 UTC after it maps to 00:00:00. If they mapped to 00:00:00, time points within the leap second would be crowded together with those after it, a full second later than the instant before the leap second, losing more ordering information. Also, `from_sys(to_sys(u))` lands before the leap second rather than skipping a second out of nowhere.
</details>

!!! question "Question 2"
    A user clock `my_clock` provides only `to_utc` and `from_utc`. Which path does `clock_cast<system_clock>(my_time)` take?

<details markdown="1">
<summary>Answer</summary>

Expression ¶1.1 needs `clock_time_conversion<system_clock, my_clock>`, that is, `my_clock::to_sys`, which is not available; ¶1.2 likewise needs `my_clock::to_sys`. ¶1.3 first uses `<utc_clock, my_clock>` to call `my_clock::to_utc`, then the full specialization `<system_clock, utc_clock>` to call `utc_clock::to_sys`: well-formed, 2 calls. ¶1.5 is also well-formed but takes 3 calls. The unique best is ¶1.3.
</details>
