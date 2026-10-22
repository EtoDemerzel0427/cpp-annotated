---
title: hh_mm_ss and the 12/24-hour functions
summary: "hh_mm_ss splits a duration into hours, minutes, seconds and decimal fractional seconds; how the number of fractional digits is computed from the period of Duration, how negative durations are represented; and the four 12/24-hour functions is_am, is_pm, make12 and make24."
updated: 2026-10-19
---

!!! tldr
    - `hh_mm_ss{d}` splits the duration `d` into hours, minutes, seconds and fractional seconds. The most common use is `hh_mm_ss{tp - floor<days>(tp)}`, to get the time of day.
    - The number of fractional digits, `fractional_width`, is computed at compile time: the fewest decimal digits (at most 18) that represent every value of `Duration` exactly, or 6 if that is impossible.
    - A negative duration is represented by a separate `is_negative()`, and the fields are always non-negative; `hours()` has no upper bound and can exceed 23.
    - `make12(0h)` is `12h` (midnight is 12 AM), and `make24(12h, false)` is `0h`; for out-of-range inputs the result is unspecified.

## Splitting a duration into fields

```cpp run ok title="hms.cpp"
#include <chrono>
#include <iostream>
using namespace std::chrono;

int main() {
  for (auto ms : {-4083007ms, 4083007ms, 65745123ms}) {
    hh_mm_ss hms{ms};
    std::cout << hms << '\n';      // -01:08:03.007 / 01:08:03.007 / 18:15:45.123
  }
  std::cout << hh_mm_ss{65745s} << '\n';   // 18:15:45

  sys_seconds tp = sys_days{2024y/March/15} + 13h + 5min;
  hh_mm_ss tod{tp - floor<days>(tp)};      // time of day
  std::cout << tod.hours() << ' ' << tod.minutes() << '\n';   // 13h 5min
}
```

The first four lines of output are the example of [[time.hms.nonmembers#2]]. `hh_mm_ss hms{ms}` uses class template argument deduction, and `Duration` is deduced from the argument as `milliseconds`.

Splitting a duration into hours, minutes and seconds is not hard in itself; the hard part is how many digits the fractional seconds should have: milliseconds need 3, microseconds need 6, and what about 1/3 second or 1/8 second? `hh_mm_ss` computes the number of digits from the period at compile time and picks a type that represents it exactly (or as exactly as possible).

## Overview [time.hms.overview]

```cpp
template<class Duration> class hh_mm_ss {
public:
  static constexpr unsigned fractional_width = see below;
  using precision                            = see below;

  constexpr hh_mm_ss() noexcept : hh_mm_ss{Duration::zero()} {}
  constexpr explicit hh_mm_ss(Duration d);

  constexpr bool is_negative() const noexcept;
  constexpr chrono::hours hours() const noexcept;
  constexpr chrono::minutes minutes() const noexcept;
  constexpr chrono::seconds seconds() const noexcept;
  constexpr precision subseconds() const noexcept;

  constexpr explicit operator precision() const noexcept;
  constexpr precision to_duration() const noexcept;
private:
  bool is-neg; chrono::hours h_; chrono::minutes m_; chrono::seconds s_; precision ss_;
};
```

¶1 `hh_mm_ss` splits a duration into "hours:minutes:seconds", possibly with fractional seconds, where the fractional seconds are in units of a non-positive integral power of 10 seconds. `Duration` determines the precision of the split. A negative duration is indicated by `is_negative()`, and the fields are always non-negative even when the duration is negative.

¶2 If `Duration` is not a specialization of duration, the program is ill-formed.

Unlike the calendar types, the default constructor of `hh_mm_ss` gives a determinate value, equivalent to constructing from `Duration::zero()`.

`hh_mm_ss` splits a duration, not a time of day, so `hours()` has no upper bound: `hh_mm_ss{25h + 3min}.hours()` is `25h`. Only in a use such as `tp - floor<days>(tp)` does the duration happen to fall between 0 and 24 hours.

## Fractional digits and precision [time.hms.members]

¶1 `fractional_width` is the number of fractional decimal digits represented by `precision`: the smallest integer in the range 0 to 18 such that `precision` can exactly represent every value of `Duration`, or 6 if no such integer exists.

¶2 `precision` is

```cpp
duration<common_type_t<Duration::rep, seconds::rep>, ratio<1, 10^fractional_width>>
```

The reasoning behind it: a reduced period `num/den` can be written as a finite decimal fraction if and only if the only prime factors of `den` are 2 and 5, and the number of digits needed is the larger of the exponents of 2 and 5 in `den`. Table 132 lists some examples:

| `Duration` | `fractional_width` | Fractional part of `Duration{1}` |
|---|---|---|
| `hours`, `minutes`, `seconds` | 0 | None |
| `milliseconds`, `microseconds`, `nanoseconds` | 3, 6, 9 | 0.001 etc. |
| Period `ratio<1, 2>`, `ratio<1, 4>`, `ratio<1, 8>` | 1, 2, 3 | 0.5, 0.25, 0.125 |
| Period `ratio<1, 5>`, `ratio<1, 10>` | 1 | 0.2, 0.1 |
| Period `ratio<1, 3>`, `ratio<1, 6>`, `ratio<1, 7>`, `ratio<1, 9>` | 6, not exactly representable | 0.333333 etc. |
| Period `ratio<756, 625>` | 4 | 0.2096 |

The last row: 625 is 5⁴, so 4 digits suffice, and 756/625 equals 1.2096.

Two consequences follow:

- The `fractional_width` of `hh_mm_ss<minutes>` is 0, and the period of `precision` is `ratio<1>`. It is a duration in seconds, not `minutes`; with libc++ in our tests it is exactly `seconds`.
- For a period of 1/3 second, `precision` is microseconds, and both `subseconds()` and `to_duration()` truncate to microseconds. For periods like this, `hh_mm_ss` is lossy.

```cpp run ok title="hms-third.cpp"
#include <chrono>
#include <iostream>
using namespace std::chrono;

int main() {
  using third = duration<int, std::ratio<1, 3>>;
  hh_mm_ss t{third{4}};                     // 4/3 seconds
  static_assert(decltype(t)::fractional_width == 6);
  std::cout << t << ' ' << t.to_duration() << '\n';   // 00:00:01.333333 1333333µs
}
```

### Construction (¶3–¶4)

¶3 The steps by which `explicit hh_mm_ss(Duration d)` splits its argument are:

- ¶3.1 Record whether `d` is negative, and let *ABS_D* be the absolute value of `d`.
- ¶3.2–¶3.4 Use `duration_cast` to extract whole hours, whole minutes and whole seconds from *ABS_D* in turn, each step first subtracting the parts already extracted.
- ¶3.5 What remains is the fractional seconds: stored as is if `precision::rep` is a floating-point type, otherwise truncated with `duration_cast<precision>`. Note 1 points out that when `precision::rep` is an integer type and the period is `ratio<1>`, `subseconds()` is always `0s`.

Taking the absolute value before splitting keeps every field non-negative: `-90min` splits into a negative sign plus 1 hour 30 minutes, not −1 hour −30 minutes, nor −2 hours plus 30 minutes.

¶4 After construction, `to_duration()` returns `d` if `precision::rep` is a floating-point type, and `duration_cast<precision>(d)` otherwise.

### Observers (¶5–¶11)

¶5 `is_negative()`, `hours()`, `minutes()`, `seconds()` and `subseconds()` return the corresponding fields. ¶10 `to_duration()` returns the sum of the fields, negated if negative. ¶11 `explicit operator precision()` returns `to_duration()`.

## Output [time.hms.nonmembers]

¶1 `os << hms` is equivalent to formatting with `"{:L%T}"`. `%T` is `%H:%M:%S`, `%S` has `fractional_width` fractional digits, and a negative value is preceded by `-` ([[time.format]]).

!!! impl "libc++: formatting throws when the hour count is 24 or more"
    At the time of writing, libc++ (Clang 23) throws `format_error` when formatting an `hh_mm_ss` whose `hours()` is 24 or more, with the message "Formatting a hour needs a valid value". Formatting the duration `25h + 3min` directly with `%T` prints `01:03:00`, that is, it treats the duration as time elapsed since midnight and takes it modulo 24 hours. The standard is not clear enough about either case. To display a total duration, building the string yourself from `hours().count()` is more reliable.

## 12/24-hour functions [time.12]

```cpp run ok title="time12.cpp"
#include <chrono>
using namespace std::chrono;

static_assert(is_am(0h) && !is_pm(0h) && make12(0h) == 12h);  // midnight is 12 AM
static_assert(is_pm(12h) && make12(12h) == 12h);              // noon is 12 PM
static_assert(make12(13h) == 1h);
static_assert(make24(12h, false) == 0h && make24(12h, true) == 12h);
static_assert(!is_am(24h) && !is_pm(24h));

int main() {}
```

¶1 These functions aid in translating between a 12-hour and a 24-hour clock; all are `constexpr noexcept`.

| Function | Returns | Paragraph |
|---|---|---|
| `is_am(h)` | `0h <= h && h <= 11h` | ¶2 |
| `is_pm(h)` | `12h <= h && h <= 23h` | ¶3 |
| `make12(h)` | The 12-hour equivalent of `h`, in the range 1h to 12h; unspecified if `h` is not in the range 0h to 23h | ¶4 |
| `make24(h, is_pm)` | The 12-hour `h` together with an AM/PM flag, converted to 0h to 23h; unspecified if `h` is not in the range 1h to 12h | ¶5 |

The edge cases are all at midnight and noon. Midnight, `0h`, is AM, and `make12(0h)` is `12h`; noon, `12h`, is PM, and `make12(12h)` is also `12h`. Conversely, `make24(12h, false)` is `0h` and `make24(12h, true)` is `12h`. `is_am` and `is_pm` both return `false` for values outside 0h to 23h.
