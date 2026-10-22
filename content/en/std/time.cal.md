---
title: The civil calendar
summary: "The Gregorian types of <chrono>: the four fields day, month, year and weekday, the weekday selectors last and weekday[n], and nine composite types; how the field-based and serial representations of a date convert into each other, the design where construction does not check and ok() tests validity, the \"/\" date syntax, and why adding months can give February 31."
updated: 2026-10-19
---

!!! tldr
    - A date has two representations: `sys_days` is a count of days since 1970-01-01, suited to day-based arithmetic; `year_month_day` stores year, month and day separately, suited to reading fields and to month- and year-based arithmetic. The two convert implicitly into each other, at the cost of a bit of integer arithmetic.
    - Construction of calendar types never checks: even `2023y/February/29` can be constructed. Use `ok()` to test validity, and `/last` or a conversion to `sys_days` to fix it up.
    - `2024y/January/31 + months{1}` is the invalid date 2024-02-31. How to handle the end of the month is up to the caller: clamp to the last day of the month, or convert to `sys_days` and roll over to March 2.
    - The "/" syntax supports three orders, year/month/day, month/day/year and day/month/year, but at least one side of the first `/` must be a calendar type; `4/4/2016` is just integer division, and the result is 0.
    - Adding to or subtracting from `month` and `weekday` wraps around modulo the cycle; `day` and `year` do not wrap; `weekday` cannot be compared for ordering.

## Two representations of a date

```cpp run ok title="two-forms.cpp"
#include <chrono>
#include <iostream>
using namespace std::chrono;

int main() {
  year_month_day ymd = 2024y/February/27;
  sys_days sd = ymd;                        // field-based → serial: implicit
  sd += days{3};                            // adding days: integer addition
  year_month_day later = sd;                // serial → field-based: implicit
  std::cout << later << ' ' << weekday{sd} << '\n';   // 2024-03-01 Fri
  std::cout << later.year() / later.month() / last << '\n';  // 2024/Mar/last
}
```

[[time.cal.general#1]] is a single sentence: the types in this subclause describe the civil Gregorian calendar and its relationship to `sys_days` and `local_days`.

A date has two representations, each with its strengths:

- **Serial**: `sys_days` is `time_point<system_clock, days>`, an integer "number of days since 1970-01-01". Adding or subtracting days, finding how many days apart two dates are, and finding the day of the week are each a single integer operation.
- **Field-based** ([[g:field-based-time-point]]): `year_month_day` stores the year, month and day separately. Reading the year, month or day and adding months or years is convenient; adding days is awkward, because month ends and leap years have to be handled.

So the standard gives `year_month_day` no "add some days" operation; instead it converts implicitly to and from `sys_days`, and day-based arithmetic is left to `sys_days`. Both directions of conversion are constant-time arithmetic, which is owed to `system_clock` being specified as Unix Time, which does not count leap seconds ([[time.clock]]).

## Fifteen types

| Category | Type | Represents | Ordered |
|---|---|---|---|
| Fields | `day` | Day of the month, usually 1–31 | Yes |
| | `month` | 1–12 | Yes |
| | `year` | −32767–32767 | Yes |
| | `weekday` | 0–6, Sunday to Saturday | No |
| Weekday selectors | `weekday_indexed` | The nth weekday X, n from 1–5 | No |
| | `weekday_last` | The last weekday X | No |
| No year | `month_day`, `month_day_last` | A given day of a given month every year, the last day of a given month | Yes |
| | `month_weekday`, `month_weekday_last` | The nth or last weekday X of a given month every year | No |
| No day | `year_month` | A given month of a given year | Yes |
| Complete dates | `year_month_day` | Year/month/day | Yes |
| | `year_month_day_last` | The last day of a given month of a given year | Yes |
| | `year_month_weekday` | The nth weekday X of a given month of a given year | No |
| | `year_month_weekday_last` | The last weekday X of a given month of a given year | No |

There is also `last_spec` ([[time.cal.last#1]]), an empty type whose only value is the constant `last`, meaning the last one in a sequence: depending on context, the last day of a month or the last weekday X of a month. Its default constructor is `explicit`, so `{}` does not implicitly convert to `last_spec`, and `ym / {}` is not interpreted as `ym / last`.

The last paragraph of each type's overview specifies that it is a trivially copyable and standard-layout class type. Almost every operation is `constexpr noexcept`. With libc++ in our tests, `year_month_day` takes only 4 bytes.

## Construction does not check; ok() does

```cpp run ok title="cal-ok.cpp"
#include <chrono>
using namespace std::chrono;

static_assert(!day{0}.ok() && day{31}.ok() && !day{32}.ok());
static_assert(!month{13}.ok());
static_assert((February/29).ok());                 // month_day: year unknown, counted as 29 days
static_assert((2024y/February/29).ok());           // leap year
static_assert(!(2023y/February/29).ok());          // common year
static_assert(!(2025y/February/Monday[5]).ok());   // February 2025 has only 4 Mondays
static_assert(weekday{7} == Sunday);               // 7 normalized to 0

int main() {}
```

The constructors of the calendar types never check and never throw. `day{40}`, `month{13}` and `2023y/February/29` can all be constructed, and every type provides `ok()` to tell you whether the value is valid. There are three reasons for this design:

1. Construction is just storage, so it can be `constexpr noexcept`, suitable for constant expressions and performance-sensitive code.
2. `2024y/January/31 + months{1}` first yields 2024-02-31, and the caller can decide how to handle it: clamp to the end of the month, roll over to March 2, or report an error. If construction threw or clamped the value, none of these policies could be implemented.
3. Out-of-range values can serve as intermediate results. `sys_days{2017y/January/32}` is exactly February 1 (see below), which is useful in date computations.

The price is checking `ok()` before use. Most operations on invalid values give unspecified results, but not undefined behavior; stream output appends the words "is not a valid ...".

| Type | `ok()` is true when |
|---|---|
| `day` | 1 ≤ d ≤ 31 |
| `month` | 1 ≤ m ≤ 12 |
| `year` | −32767 ≤ y ≤ 32767 |
| `weekday` | wd ≤ 6 |
| `weekday_indexed` | The weekday is valid and 1 ≤ index ≤ 5 |
| `month_day` | The month is valid and the day is between 1 and the number of days in that month, February counting as 29 |
| `year_month_day` | The year and month are valid and the day is between 1 and the last day of that month of that year |
| `year_month_weekday` | Every field is valid and the month really has an index-th such weekday |

`month_day` counts February as 29 days ([[time.cal.md.members#4]]) because it has no year: `February/29` is valid as the birthday of someone born in a leap year.

## The four field types

### day [time.cal.day]

[[time.cal.day.overview#1]] specifies that `day` represents a day of a month, normally 1 to 31, but it may hold non-negative values outside that range.

A `day` can be added to or subtracted from `days` ([[time.cal.day.nonmembers#3]] through paragraph 6), and subtracting two `day`s gives `days`. The arithmetic does not wrap: `day{31} + days{5}` is `day{36}`, and `ok()` is false. The constructor takes `unsigned`; ¶1 [time.cal.day.members] says that if the value is not in the range 0 to 255, the stored value is unspecified.

[[time.cal.day.nonmembers#10]] defines a literal suffix: `5d` is `day{5}`, not `days{5}`.

### month [time.cal.month]

`month` has the same structure as `day`; the difference is in the arithmetic. [[time.cal.month.nonmembers#3]] specifies that `month + months` wraps using Euclidean division, so the result is always between 1 and 12, even if the original value was invalid: `February + months{11} == January`.

¶6 Subtracting two `month`s returns a value `m` in the range 0 to 11 months such that `y + m == x`: `January - February == months{11}`. Months form a cycle; there is no "minus one month".

### year [time.cal.year]

[[time.cal.year.overview#1]] specifies that `year` can represent values from `min()` to `max()`, that is, −32767 to 32767 ([[time.cal.year.members#19]] and ¶20). −32768 is excluded so that `-y` is always valid. Year arithmetic does not wrap.

`is_leap()` in [[time.cal.year.members#16]] computes `y % 4 == 0 && (y % 100 != 0 || y % 400 == 0)`. This is the proleptic Gregorian calendar: years before 1582 also follow the Gregorian rules. The literal suffix `y` of ¶10 [time.cal.year.nonmembers] makes `2024y` a `year{2024}`.

### weekday [time.cal.wd]

[[time.cal.wd.overview#1]] specifies that the values 0 to 6 of `weekday` correspond to Sunday through Saturday. It can only be compared for equality, not ordered. Note 1 gives the reason: there is no universal consensus on which day is the first day of the week, so `weekday` arithmetic treats the week as a cycle with no beginning or end.

The constructors of `weekday` ([[time.cal.wd.members]]) have a few details:

- Paragraph 1: `weekday{7}` is stored as 0, so it can be constructed directly from the ISO encoding (Sunday is 7).
- Paragraph 2: construction from `sys_days` is implicit and computes the day of the week of that day. Paragraph 3 gives an example: 1970-01-01 was a Thursday, so 4 is stored.
- Paragraph 4: construction from `local_days` is `explicit`, and paragraph 5 specifies that the result is the same as constructing from `sys_days{dp.time_since_epoch()}`.

¶18 `c_encoding()` returns 0 to 6 with Sunday as 0, matching C's `tm_wday`; `iso_encoding()` in paragraph 19 returns 1 to 7 with Monday as 1 and Sunday as 7, matching ISO 8601. ¶21–¶22 `wd[n]` gives a `weekday_indexed`, and `wd[last]` gives a `weekday_last`.

[[time.cal.wd.nonmembers#2]] specifies that `weekday + days` wraps modulo 7: `Monday + days{6} == Sunday`. Per paragraph 5, subtracting two `weekday`s gives a result between 0 and 6 days: `Sunday - Monday == days{6}`.

Why is construction from `sys_days` implicit but construction from `local_days` explicit? The pattern runs through the whole calendar library: `sys_days` and the calendar types convert implicitly into each other, while `local_days` must be converted explicitly, so that local time does not silently slip into UTC computations. The constructors and conversion functions of `year_month_day` and the other types follow the same pattern.

## Weekday selectors and the types without a year

`weekday_indexed` ([[time.cal.wdidx]]) is a weekday plus an index from 1 to 5, representing the nth weekday X of some month not yet known. The example in ¶2 constructs one with `Sunday[2]`. `weekday_last` ([time.cal.wdlast]) represents the last weekday X of some month, usually written `Sunday[last]`.

The four types without a year describe a day that occurs every year, such as a holiday or a billing date:

| Type | Typical spelling | Comparison |
|---|---|---|
| `month_day` | `December/25`, `25d/December` | Month first, then day |
| `month_day_last` | `February/last` | By month |
| `month_weekday` | `November/Thursday[4]` | Equality only |
| `month_weekday_last` | `May/Monday[last]` | Equality only |

Lacking a year, they cannot be converted to a date. When needed, supply the year with `/`: `2024y/(November/Thursday[4])`. `weekday_last`, `month_day_last`, `month_weekday` and `month_weekday_last` have no default constructor; you must say which weekday and which month. `weekday_indexed` and `month_day` do have one.

## The "/" date syntax [time.cal.operators]

```cpp run ok title="slash-int.cpp"
#include <chrono>
using namespace std::chrono;

static_assert(2015/4/4 == 125);                  // all int: built-in division
static_assert(2015y/4/4 == year_month_day{year{2015}, month{4}, day{4}});
static_assert(April/4/2016 == 2016y/April/4d);   // month/day/year
static_assert(4d/April/2016 == 2016y/April/4d);  // day/month/year
static_assert(4/4/2016 == 0);                    // US order, but all int

int main() {}
```

¶1 A set of overloaded `operator/` functions provides a conventional syntax for creating dates. The note in paragraph 2 explains that year, month and day can be written in three orders:

```text
year/month/day      2024y/February/29
month/day/year      February/29/2024
day/month/year      29d/February/2024
```

Anywhere a "day" is needed, `last`, `weekday[i]` or `weekday[last]` can be used instead. The note in paragraph 3 adds that leaving out one `/` gives a partial date: `2015y/April` is a `year_month`, and `April/4` and `4d/April` are `month_day`s.

The forty overloads of ¶5–¶44 can be summed up in one rule: at least one of the two operands of the first `/` is a calendar type, and it determines what the `int` on the other side means.

| Operands of the first `/` | Result | Meaning of the `int` |
|---|---|---|
| `year / month`, `year / int` | `year_month` | Month |
| `month / day`, `month / int` | `month_day` | Day |
| `int / day`, `day / month`, `day / int` | `month_day` | Month |
| `month / last`, `int / last`, `last / month`, `last / int` | `month_day_last` | Month |
| `month / weekday_indexed`, `int / weekday_indexed`, etc. | `month_weekday` | Month |
| `year_month / day`, `year_month / int` | `year_month_day` | Day |
| `year / month_day`, `int / month_day`, `month_day / int`, etc. | `year_month_day` | Year |
| `year_month / last`, `year / month_day_last`, etc. | `year_month_day_last` | Year |
| `year_month / weekday_indexed`, `year / month_weekday`, etc. | `year_month_weekday` | Year |
| `year_month / weekday_last`, `year / month_weekday_last`, etc. | `year_month_weekday_last` | Year |

The example in ¶4 covers several edge cases:

```cpp
auto a = 2015/4/4;          // a == int(125)
auto b = 2015y/4/4;         // b == year_month_day{year(2015), month(4), day(4)}
auto c = 2015y/4d/April;    // error: no viable operator/ for the first /
auto d = 2015/April/4;      // error: no viable operator/ for the first /
```

- Both `/` in `a` have only `int` operands, so this is built-in integer division: 2015/4 is 503, and 503/4 is 125.
- In `b`, `2015y/4` matches `year / int` and gives a `year_month`, with 4 as the month; the following `/4` matches `year_month / int` and gives a `year_month_day`.
- `c` would need `year / day`. There is no such overload: "year 2015, day 4" is not the start of any of the orders.
- `d` would need `int / month`, and there is no such overload either. The reason is that it is ambiguous: in day/month/year order the leading `int` would be the day; in year/month/day order it would be the year. The standard simply does not provide it, and requires `2015y` or `4d`.

!!! pitfall "It compiles, but the result is an integer"
    `auto d = 4/4/2016;` gives no error; `d` is an `int` with value 0. As long as one side of the first `/` is a calendar type, such as `2016y`, `April` or `4d`, the following `int`s are interpreted correctly. Always giving the year a `y` suffix, or always using the named month constants, avoids this mistake.

## year_month and adding months [time.cal.ym]

[[time.cal.ym.overview#1]] specifies that `year_month` represents a specific month of a specific year, with the day unspecified; it is a field-based time point with a resolution of months.

`year_month` supports adding and subtracting `months` and `years`, and subtracting two `year_month`s gives `months` ([[time.cal.ym.nonmembers#10]]). Per paragraph 4, `ym + dm` returns a value `z` such that `z.ok() && z - ym == dm`, and paragraph 5 requires the complexity to be independent of the magnitude of `dm`: no looping one month at a time.

### That odd constraint

Every `+`, `-`, `+=` and `-=` that takes `months` carries the same constraint, for example [[time.cal.ym.nonmembers#3]]:

!!! std
    If the argument supplied by the caller for the months parameter is convertible to years, its implicit conversion sequence to years is worse than its implicit conversion sequence to months.

That is: if the argument is convertible to `years`, the overload taking `months` participates in overload resolution only when the argument's implicit conversion sequence to `years` is worse than its conversion sequence to `months`.

The problem is that `years` implicitly converts to `months`, because a year is exactly 12 months. Suppose the user defines `decades = duration<int, ratio_multiply<years::period, ratio<10>>>`: it implicitly converts both to `years` and to `months`, both are user-defined conversions, overload resolution cannot rank one above the other ([[over.ics.rank]]), and `ymd + decades{1}` is ambiguous.

With the constraint, for any argument that converts to `years` and whose conversion to `months` is not better, the `months` overload drops out, so `ymd + decades{1}` unambiguously selects the `years` overload and adds years. The same holds for `years{1}` itself: its conversion to `years` is the identity conversion, its conversion to `months` goes through a user-defined conversion, and the `months` overload drops out. The result is that any argument that can be taken as a number of years is treated as years.

!!! impl "libc++ does not yet implement this constraint"
    At the time of writing, libc++ writes these operators as ordinary non-template functions and does not implement the constraint. `2024y/January/1 + decades{1}` fails with Clang 23 with `use of overloaded operator '+' is ambiguous`, the candidates being the two `operator+` taking `months` and taking `years`. Per the standard it should select the `years` version.

## year_month_day [time.cal.ymd]

This is the most commonly used calendar type. Note 1 of [[time.cal.ymd.overview#1]] explains that it supports year- and month-oriented arithmetic but not day-oriented arithmetic; for day-oriented arithmetic, convert to `sys_days` first.

### Converting to and from sys_days [time.cal.ymd.members]

¶3 `year_month_day` can be implicitly constructed from `sys_days`. Paragraph 4 guarantees a lossless round trip: for any `ymd` whose `ok()` is true, `ymd == year_month_day{sys_days{ymd}}`. ¶5 Construction from `local_days` is `explicit`. ¶2 It can also be implicitly constructed from `year_month_day_last`; note 1 says this is more efficient than going through `sys_days`.

¶19 `year_month_day` implicitly converts to `sys_days`, in three cases:

- If `ok()` is true, it returns the number of days since the epoch, negative before 1970.
- Otherwise, if the year and month are valid, it returns `sys_days{y/m/1d} + (d - 1d)`; that is, a day field past the end of the month rolls over day by day.
- Otherwise the returned value is unspecified.

The example in ¶21 shows the second case:

```cpp
static_assert(year_month_day{sys_days{2017y/January/0}}  == 2016y/December/31);
static_assert(year_month_day{sys_days{2017y/January/31}} == 2017y/January/31);
static_assert(year_month_day{sys_days{2017y/January/32}} == 2017y/February/1);
```

January 0 is the day before January 1, and January 32 is the day after January 31. With this rollover rule, `sys_days` can normalize out-of-range dates.

¶20 specifies that a `sys_days` in the range `days{-12687428}` to `days{11248737}`, converted to `year_month_day` and back, keeps its value. This range corresponds exactly to `year`'s −32767 to 32767. ¶22 The conversion to `local_days` is `explicit`.

### Adding months and years [time.cal.ymd.nonmembers]

```cpp run ok title="month-end.cpp"
#include <chrono>
#include <iostream>
using namespace std::chrono;

int main() {
  auto d = 2024y/January/31 + months{1};
  std::cout << d << '\n';                     // 2024-02-31 is not a valid date
  std::cout << sys_days{d} << '\n';           // 2024-03-02: rolled over per ¶19
  if (!d.ok()) d = d.year()/d.month()/last;   // another policy: clamp to end of month
  std::cout << d << '\n';                     // 2024-02-29

  std::cout << (2024y/February/29 + years{1}).ok() << '\n';  // 0: 2025-02-29 is invalid
}
```

¶4 specifies that `ymd + months` equals `(ymd.year() / ymd.month() + dm) / ymd.day()`, keeping the day field as is. The note in paragraph 5 says the result is guaranteed to be valid only if the day is between 1 and 28.

¶10 specifies that `ymd + years` equals `(ymd.year() + dy) / ymd.month() / ymd.day()`. The note in paragraph 11 says adding years to February 29 may give an invalid result.

What day is January 31 plus one month? There is no single right answer. Clamping to the end of the month (February 29), rolling over (March 2) and reporting an error each suit different applications. The standard makes `+` do only field arithmetic and leaves the policy to the caller, who combines `ok()`, `/last` and `sys_days{}` into the semantics they need.

## The other three complete dates

### year_month_day_last [time.cal.ymdlast]

[[time.cal.ymdlast.overview#1]] specifies that it represents the last day of a specific month of a specific year, that is, a `month_day_last` plus a year; it can be ordered.

`day()` in [[time.cal.ymdlast.members#15]] returns the last day of the month when `ok()` is true, and the note in paragraph 16 says this value may be computed on demand. It implicitly converts to `sys_days` (¶17); the conversion to `local_days` is `explicit`.

The key difference from `year_month_day` is in adding months. [[time.cal.ymdlast.nonmembers#4]] specifies that `ymdl + months` equals `(y/m + dm) / last`, so the result is still the end of a month. `2024y/January/last + months{1}` is the last day of February 2024, the 29th, and is always valid. When you need a sequence like "the last day of every month", accumulate on a `year_month_day_last`.

### year_month_weekday [time.cal.ymwd]

[[time.cal.ymwd.overview#1]] specifies that it represents the nth weekday X of a specific month of a specific year; it can only be compared for equality.

Per [[time.cal.ymwd.members#2]], it can be implicitly constructed from `sys_days`, and paragraph 3 guarantees a lossless round trip for values whose `ok()` is true; construction from `local_days` is `explicit`.

¶20 When converting to `sys_days`, if the year, month and weekday are valid, the result is `(index - 1) * 7` days after the first weekday X of the month; if index is 0, the result is 7 days before the first weekday X; otherwise it is unspecified. This does not require index to be at most 5: in a month with only 4 Mondays, `Monday[5]` rolls over into the next month.

¶22 `ok()` requires every field to be valid and the value to actually represent a valid date, that is, the month has an index-th weekday X.

[[time.cal.ymwd.nonmembers#3]] and paragraph 8 specify that adding months or years preserves "the nth weekday X", not the day number. So `2024y/November/Thursday[4] + years{1}` is the fourth Thursday of November 2025.

### year_month_weekday_last [time.cal.ymwdlast]

It represents the last weekday X of a specific month of a specific year. [[time.cal.ymwdlast.members#16]] specifies that, when `ok()` is true, it converts to the `sys_days` of the last weekday X of that month. Adding months or years preserves "the last weekday X".

```cpp run ok title="holidays.cpp"
#include <chrono>
#include <iostream>
using namespace std::chrono;

int main() {
  for (auto y = 2024y; y <= 2025y; ++y) {
    sys_days thanksgiving = y/November/Thursday[4];   // US Thanksgiving
    sys_days memorial     = y/May/Monday[last];       // US Memorial Day
    sys_days eom          = y/February/last;          // last day of February
    std::cout << thanksgiving << ' ' << memorial << ' ' << eom << ' '
              << weekday{eom} << '\n';
  }
  auto gap = sys_days{2024y/December/25} - sys_days{2024y/January/1};
  std::cout << gap << '\n';                           // 359d
}
```

<details class="fine" markdown="1"><summary>Remaining wording</summary>

Stream output of each type: `day` prints two digits (`%d`), `month` prints the locale's abbreviated month name (`%b`), `year` prints at least four digits (`%Y`), `weekday` prints the locale's abbreviated weekday name (`%a`), `weekday_indexed` prints something like `Sun[2]`, and `year_month_day` prints `%F` (such as `2024-02-29`). For an invalid value, an "is not a valid ..." note is appended.

Every type's `from_stream` parses per [[time.parse]]; if no valid value can be parsed, it sets `failbit` and leaves the target unmodified.

The constructor of `weekday_indexed` ([[time.cal.wdidx.members#1]]) stores an unspecified value if the weekday is invalid or the index is not in the range 0 to 7.

The prefix and postfix `++` and `--` and the compound assignments of `day`, `month` and `year` are defined in terms of the corresponding `+` and `-` (in each type's members subclause).

</details>

## Common pitfalls

!!! pitfall "Adding years to sys_days"
    `sys_days{2024y/February/29} + years{1}` compiles, but `years{1}` is the average year length, 365.2425 days. The result is a `sys_time` with a precision of 216 seconds, whose value is 2025-02-28 05:49:12. To add a calendar year, do it on a field-based type: `2024y/February/29 + years{1}`, then check `ok()`. Likewise, `months{1}` is 30.436875 days.

!!! pitfall "weekday cannot be ordered"
    `Monday < Friday` is ill-formed. If your application really treats Monday as the start of the week, compare `wd.iso_encoding()`; if Sunday, compare `c_encoding()`.

!!! pitfall "Default-constructed calendar objects are uninitialized"
    The default constructors of `day`, `month`, `year`, `weekday`, `year_month_day` and so on are all `= default`, and like `int` they do not initialize. In a local variable `year_month_day d;` the field values are indeterminate, and since C++26 reading them gives erroneous values ([[basic.indet]]).

!!! pitfall "Computing sys_days of an invalid value"
    Computing `sys_days` of, or taking differences between, objects whose `ok()` is false mostly gives unspecified results, for example [[time.cal.month.nonmembers#6]] and the last case of [[time.cal.ymd.members#19]]. This is not undefined behavior, but the result is meaningless. `+` on `month` and `weekday` are the exceptions: they give an in-range result even for invalid values.

## Questions

!!! question "Question 1"
    What day is `sys_days{2024y/February/30}`? What about `sys_days{2024y/month{13}/1}`?

<details markdown="1">
<summary>Answer</summary>

In the first, the year and month are valid and the day is not, so per [[time.cal.ymd.members#19]] it returns `sys_days{2024y/February/1} + days{29}`, which is 2024-03-01. In the second the month is invalid, and ¶19 says the returned value is unspecified.
</details>

!!! question "Question 2"
    Why does `month + months` wrap, while `day + days` and `year + years` do not?

<details markdown="1">
<summary>Answer</summary>

Months and weekdays form cycles: January follows December, and Sunday follows Saturday. For an isolated `month` field, wrapping is the only sensible meaning of adding a month; carrying into the year is handled by `year_month`. Days have no fixed period: a month has 28 to 31 days, and a `day` does not know which month it belongs to, so it cannot wrap correctly; it just adds and subtracts, leaving validity to `ok()`. A year is an unbounded linear quantity and needs no wrapping either.
</details>

!!! question "Question 3"
    Does `year_month_weekday{sys_days{2025y/February/Monday[5]}}` equal `2025y/February/Monday[5]`?

<details markdown="1">
<summary>Answer</summary>

No. February 2025 has only 4 Mondays, so `ok()` is false for `2025y/February/Monday[5]`. Per [[time.cal.ymwd.members#20]], converting it to `sys_days` gives 28 days after the first Monday (February 3), which is 2025-03-03. A `year_month_weekday` constructed from that `sys_days` is `2025y/March/Monday[1]`. The round-trip guarantee of ¶3 holds only for values whose `ok()` is true.
</details>
