---
title: Class template time_point
summary: "A time_point is a clock tag plus a duration since that clock's epoch; which operations are allowed between time points and durations, why time points of different clocks cannot be mixed, and how time_point_cast differs from floor, ceil and round."
updated: 2026-10-19
---

!!! tldr
    - `time_point<Clock, Duration>` stores only a duration, the time since the clock's epoch; `Clock` is just a type tag and takes no space.
    - A time point plus or minus a duration gives a time point, and subtracting two time points of the same clock gives a duration; there is no operator for adding two time points or for subtracting time points of different clocks, so these fail to compile.
    - Time points of the same clock with different precisions convert to each other by the same rules as durations: the non-truncating direction is implicit, the truncating direction must be explicit.
    - To take the date part of a time point, use `floor<days>`. `time_point_cast<days>` truncates toward zero and gives the next day for time points before 1970.

## Time points and durations

```cpp run error title="tp-algebra.cpp"
#include <chrono>
using namespace std::chrono;

int main() {
  sys_days today = 2024y/March/15;
  auto tomorrow = today + days{1};     // OK: time point + duration = time point
  auto gap = tomorrow - today;         // OK: time point - time point = duration
  auto nonsense = today + tomorrow;    // error: time point + time point makes no sense

  auto a = system_clock::now();
  auto b = steady_clock::now();
  auto d = a - b;                      // error: the two clocks have different epochs
}
```

The relationship between `time_point` and `duration` is like that between pointers and `ptrdiff_t`: a pointer plus an integer gives a pointer, subtracting two pointers gives an integer, adding two pointers makes no sense, and neither does subtracting pointers into two different arrays.

| Expression | Result | Analogy |
|---|---|---|
| time point + duration, duration + time point, time point − duration | time point | pointer ± integer |
| time point − time point of the same clock | duration | pointer − pointer |
| time point + time point | no such operation | pointer + pointer |
| time point − time point of different clocks | no such operation | subtracting pointers into two arrays |

`system_clock` and `steady_clock` have different epochs: one is January 1, 1970, the other is usually boot time. Their time points are different types, and no viable `operator-` can be found to subtract them.

## Definition [time.point.general]

```cpp
template<class Clock, class Duration = typename Clock::duration>
class time_point {
public:
  using clock    = Clock;
  using duration = Duration;
  using rep      = duration::rep;
  using period   = duration::period;
private:
  duration d_;    // exposition only
  // ...
};
```

All the data of a `time_point` is `d_`, the time since the clock's epoch ([[g:clock-epoch]]).

¶1 If `Duration` is not a specialization of `duration`, the program is ill-formed.

`Duration` may differ from `Clock::duration`. `sys_days` is `time_point<system_clock, days>` and `sys_seconds` is `time_point<system_clock, seconds>`: the same clock with different precisions, and different types.

This subclause places no additional requirements on `Clock`. `local_time<D>` is just `time_point<local_t, D>`, and `local_t` is merely an empty struct without even a `now()` ([[time.clock]]).

## Construction and precision conversion [time.point.cons]

```cpp run ok title="tp-conv.cpp"
#include <chrono>
#include <type_traits>
using namespace std::chrono;

static_assert( std::is_convertible_v<sys_days, sys_seconds>);      // days → seconds: multiplication
static_assert(!std::is_convertible_v<sys_seconds, sys_days>);      // would truncate
static_assert(!std::is_convertible_v<sys_seconds, local_seconds>); // different clocks
static_assert(!std::is_convertible_v<seconds, sys_seconds>);       // explicit

int main() {
  sys_seconds t{};                        // the epoch: 1970-01-01 00:00:00
  return t.time_since_epoch() == 0s ? 0 : 1;
}
```

¶1 The default constructor initializes `d_` with `duration::zero()`, and the resulting object represents the epoch. This differs from duration: default construction of `time_point` has a definite value.

¶2 `explicit time_point(const duration& d)` gives the epoch plus `d`. It is `explicit` to keep a length of time from being mistaken for an instant: `sys_seconds t = 5s;` is ill-formed.

¶3 Converting from another time_point of the same clock requires `Duration2` to be implicitly convertible to `duration`. This follows the duration rules entirely ([[time.duration]]): `sys_seconds` converts implicitly to `sys_time<milliseconds>`, not the other way round. ¶4 The converted value is just `t.time_since_epoch()`.

## Members

`time_since_epoch()` in [[time.point.observer#1]] returns `d_`. This is the only way to get the number out of a time point, and moving the number by hand for a cross-clock conversion also goes through it.

`++`, `--`, `+=` and `-=` in [[time.point.arithmetic]] act directly on `d_` (¶1–¶10), and the parameter of `+=` is this type's `duration`. Prefix `++` advances the time point by one tick period; `++` on a `sys_days` is the next day.

`min()` and `max()` in [[time.point.special]] are `time_point(duration::min())` and `time_point(duration::max())` respectively (¶1–¶2).

## Non-member arithmetic [time.point.nonmember]

| Operation | Return type | Paragraphs |
|---|---|---|
| `tp + d`, `d + tp`, `tp - d` | `time_point<Clock, common_type_t<Duration1, duration<Rep2, Period2>>>` | ¶1–¶3 |
| `tp1 - tp2` | `common_type_t<Duration1, Duration2>` | ¶4 |

The precision of the result is the finer of the two: `sys_days + 1h` has type `sys_time<hours>`, no longer `sys_days`. This loses no information, but after "adding a few hours to a date" the type has changed, and it can no longer be assigned back to a `sys_days` variable.

The two parameters in ¶4 share a single template parameter `Clock`, so only time points of the same clock can be subtracted. Subtracting different clocks finds no viable `operator-`, which is where the error in the opening example comes from.

## Comparison [time.point.comparisons]

¶1 `==`, `<`, `>`, `<=`, `>=` and `<=>` all compare `time_since_epoch()` (¶1–¶6). The two arguments must belong to the same `Clock`; the `Duration`s may differ, with comparison relying on cross-unit duration comparison. The `<=>` of ¶6 requires `three_way_comparable_with<Duration1, Duration2>`.

So `sys_days{2024y/January/1} == sys_seconds{1704067200s}` is valid, comparing two time points of the same clock; `sys_days{} == local_days{}` is ill-formed.

## Precision conversion functions [time.point.cast]

```cpp run ok title="tp-floor.cpp"
#include <chrono>
#include <iostream>
using namespace std::chrono;

int main() {
  sys_seconds t = sys_days{1969y/December/31} + 18h;  // 6 hours before the epoch
  std::cout << time_point_cast<days>(t) << '\n';     // 1970-01-01
  std::cout << floor<days>(t) << '\n';               // 1969-12-31
}
```

| Function | Effect | Paragraphs |
|---|---|---|
| `time_point_cast<To>(tp)` | `duration_cast` on `time_since_epoch()` | ¶1–¶2 |
| `floor<To>(tp)` | `floor` on `time_since_epoch()` | ¶3–¶4 |
| `ceil<To>(tp)` | `ceil` on `time_since_epoch()` | ¶5–¶6 |
| `round<To>(tp)` | `round` on `time_since_epoch()`; `To::rep` may not be floating point | ¶7–¶8 |

All four functions require only that `ToDuration` be a specialization of duration. They change only the precision, not the clock; for cross-clock conversion use `clock_cast` ([[time.clock]]).

`time_point_cast` uses `duration_cast`, which truncates toward zero. For time points before the epoch, `time_since_epoch()` is negative, and truncating toward zero means rounding toward the future. In the example above, 18:00 on December 31, 1969 is truncated to January 1, 1970.

So always use `floor<days>` to take the date part, for both `sys_time` and `local_time`. In [[time.cal]], `year_month_day{floor<days>(tp)}` is the standard idiom.

## Common pitfalls

!!! pitfall "The default Duration is up to the implementation"
    The precision of `time_point<system_clock>` is `system_clock::duration`: microseconds on libc++, nanoseconds on libstdc++, 100 nanoseconds on MSVC. Write `time_since_epoch().count()` to a file or the network without fixing the unit, and reading it back with another standard library gets it wrong. Convert to a definite unit with `floor<seconds>` or `time_point_cast<milliseconds>` before storing.

!!! pitfall "time_point::max() is not a good sentinel"
    A lot of code uses `time_point::max()` to mean "never time out". But waiting functions often compute `deadline - now()` internally, or convert to another clock, and once `max()` takes part in such arithmetic it overflows, which is undefined behavior. Standard library implementations usually special-case `wait_until(max())`; your own time arithmetic does not.
