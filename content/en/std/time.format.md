---
title: Formatting chrono types
summary: "How std::format formats chrono types: the meaning of conversion specifiers such as %Y, %m and %S; no localization without L; the number of %S fractional digits is set by the type; where the sign of a negative duration goes; format_error when the type lacks the needed information, which often becomes a compile error; %Z/%z with local_time_format and zoned_time."
updated: 2026-10-19
---

!!! tldr
    - A chrono format specification consists of fill, align, width, an optional precision and `L`, plus conversion specifiers starting with `%`, as in `{:>12%F}`.
    - Without `L` the `"C"` locale is always used, regardless of the global locale; only with `L` is the output localized.
    - The number of fractional digits of `%S` is determined by the precision of the type: `milliseconds` always gives 3 digits, `seconds` gives none.
    - If the type being formatted lacks the information a specifier needs, `format_error` is thrown; if the format string is checked at compile time, this usually shows up as a compile error.
    - `%Z` of a `sys_time` is always `UTC`, and `local_time` has no `%Z`/`%z` at all; when time zone information is needed, use `zoned_time` or `local_time_format`.

## An example

```cpp run ok
#include <chrono>
#include <format>
#include <iostream>
using namespace std::chrono;

int main() {
    auto t = sys_days{2024y/March/1} + 13h + 5min + 7s + 250ms;
    std::cout << std::format("{}", t) << '\n';                            // 2024-03-01 13:05:07.250
    std::cout << std::format("{:%Y-%m-%dT%H:%M:%SZ}", floor<seconds>(t)) << '\n';
                                                                         // 2024-03-01T13:05:07Z
    std::cout << std::format("{:%a %d %b %Y, %I:%M %p}", t) << '\n';      // Fri 01 Mar 2024, 01:05 PM
    std::cout << std::format("{:%j %u %V}", t) << '\n';                   // 061 5 09
    std::cout << std::format("[{:>12%F}]", t) << '\n';                    // [  2024-03-01]
    std::cout << std::format("{:%H:%M}", 90min) << ' '                    // 01:30
              << std::format("{:%Q%q}", 90min) << '\n';                   // 90min
    std::cout << std::format("{:%z %Z}", t) << '\n';                      // +0000 UTC
}
```

C++20 hooked `<chrono>` into `std::format` through [[P1361R2]]. Durations, the time_points of every clock, all the calendar types, `hh_mm_ss`, `sys_info`, `local_info` and `zoned_time` all have `formatter` specializations ([[time.syn]]). Every `operator<<` in this clause is also defined in terms of `format`; for example, the output of `sys_time` is `{:L%F %T}`. So this subclause is the single normative source for chrono text output.

The conversion specifiers follow the `%` notation of C's `strftime`, with three differences: they are type-safe, they handle fractional seconds of any precision, and by default they are locale-independent.

## Syntax of the format specification (¶1)

¶1 Each `formatter` specialization in the chrono library meets the *Formatter* requirements ([[format.formatter]]), and their `parse` interprets the format specification according to the following syntax:

```text
chrono-format-spec:  fill-and-align(opt) width(opt) precision(opt) L(opt) chrono-specs(opt)
chrono-specs:        conversion-spec | chrono-specs conversion-spec | chrono-specs literal-char
literal-char:        any character other than {, }, or %
conversion-spec:     % modifier(opt) type
modifier:            E O
type:                a A b B c C d D e F g G h H I j m M n p q Q r R S t T u U V w W x X y Y z Z %
```

*fill-and-align*, *width* and *precision* mean the same as in [[format.string]] and apply to the whole formatted result: `{:>20%F}` right-aligns the date in 20 columns. *precision* is valid only for a `duration` whose rep is a floating-point type; for other types, a *precision* in the format specification throws `format_error`.

A *literal-char* is copied to the output unchanged, so `{:%Y年%m月%d日}` (the Chinese date style) is valid.

## The formatting locale (¶2)

¶2 The **formatting locale** ([[g:formatting-locale]]) is determined as follows:

- ¶2.1 If the format specification has no `L` option, the `"C"` locale; otherwise
- ¶2.2 the locale passed to the formatting function, if any; otherwise
- ¶2.3 the global locale.

So `format("{:%c}", t)` always prints the C locale's `Fri Mar  1 13:05:07 2024`, regardless of what `std::locale::global` was set to; only `{:L%c}` is localized. This is consistent with how `std::format` handles numbers: locale-independent by default, with `L` turning localization on explicitly.

Every `operator<<` in this clause is written as `format(os.getloc(), "{:L...}", ...)`: stream output should respect the stream's locale, so it carries `L` explicitly.

!!! history "A fix after C++20"
    In the original C++20 wording, chrono formatting used the locale by default, conflicting with the principle that `std::format` is unaffected by locale by default. A later proposal changed it to the current rule, applied to C++20 as a defect fix.

## Conversion specifiers (¶3, Table 133)

¶3 Each conversion specifier is replaced as given in Table 133; where the table says ISO 8601 format is used, the output follows that standard. Some specifiers depend on the formatting locale. If the string literal encoding is a Unicode encoding form and the locale is among an implementation-defined set of locales, the locale-dependent replacement is converted to the literal encoding. If the object being formatted does not contain the information a specifier needs, `format_error` is thrown.

Grouped by purpose, using 2024-03-01 13:05:07.250 in the C locale as the example:

| Category | Specifier | Meaning |
|---|---|---|
| Year | `%Y` | Year, zero-padded to 4 digits: `2024`; `year{12}` is `0012` |
| | `%y` `%C` | Last two digits of the year, `24`; century (year divided by 100, rounded down), `20` |
| | `%G` `%g` | ISO 8601 week-based year (4 digits / last two digits) |
| Month | `%m` | `03` |
| | `%b` `%h` `%B` | The locale's abbreviated or full month name: `Mar`, `March` |
| Day | `%d` `%e` | `01`, ` 1` (space-padded) |
| | `%j` | Day of the year, `061`; for a duration, the number of days, unpadded |
| Weekday | `%a` `%A` | `Fri`, `Friday` |
| | `%u` `%w` | ISO encoding (Monday is 1, Sunday is 7), `5`; C encoding (Sunday is 0), `5` |
| | `%U` `%W` `%V` | Week number with Sunday or Monday as the first day of the week; ISO 8601 week number |
| Time | `%H` `%I` `%M` | 24-hour `13`, 12-hour `01`, minute `05` |
| | `%S` | Seconds, including the fractional part: `07.250` (see below) |
| | `%p` | `AM` / `PM` |
| Composite | `%F` `%T` `%R` `%D` | `%Y-%m-%d`, `%H:%M:%S`, `%H:%M`, `%m/%d/%y` |
| | `%c` `%x` `%X` `%r` | The locale's date and time, date, time, 12-hour time |
| Time zone | `%z` | UTC offset `+0000`; `%Ez` and `%Oz` add a colon, `+00:00` |
| | `%Z` | Time zone abbreviation `UTC` |
| duration | `%Q` | The value of `count()` |
| | `%q` | The unit suffix, the same as in the stream output of [[time.duration]]: `ms`, `min`, `[1/3]s` |
| Other | `%n` `%t` `%%` | Newline, tab, `%` |

The modifiers `E` and `O` request the locale's alternative representation, such as Japanese era names or non-Arabic digits. They can only be combined with the specifiers listed in the table, such as `%Ec`, `%EY`, `%Od` and `%OH`.

Example 3 of Table 133 shows that `%y` ignores the sign of the year: `format("{:%C %y}", -1976y)` prints `-20 76`.

### `%S` and fractional seconds

| Type | `format("{:%S}", ...)` |
|---|---|
| `7s` | `07` |
| `7000ms` | `07.000` |
| `duration<int, ratio<1, 3>>{22}` | `07.333333` |

What Table 133 specifies for `%S`: if the number of seconds is less than 10, a leading 0 is added; if the precision of the input cannot be exactly represented with whole seconds, a fixed-point decimal is printed whose number of fractional digits matches the precision of the input, the same as `fractional_width` in [[time.hms]]; if it cannot be exactly represented within 18 fractional digits, the output is to microseconds. One third of a second is the last case, so 6 fractional digits are printed. The decimal point character is determined by the locale.

So the number of `%S` digits is determined by the type, not the value. For whole seconds, `floor<seconds>(t)` first and then format.

## Negative durations (¶4)

```cpp run ok
#include <chrono>
#include <format>
#include <iostream>
using namespace std::chrono;

int main() {
  std::cout << std::format("{:%T}", -10'000s) << '\n';        // -02:46:40
  std::cout << std::format("{:%H:%M:%S}", -10'000s) << '\n';  // -02:46:40
  std::cout << std::format("minutes {:%M, hours %H, seconds %S}", -10'000s) << '\n';
                                                   // minutes -46, hours 02, seconds 40
}
```

¶4 Formatting a `duration` with a negative value, or an `hh_mm_ss` whose `is_negative()` is true, is equivalent to formatting its absolute value with a `-` placed before the replacement of the first conversion specifier. The third line shows that the minus sign goes with the first conversion specifier, not at the start of the whole result.

## When information is missing (¶5–¶6)

¶6 If the type being formatted does not contain the information a specifier needs, `format_error` is thrown. Example 2 uses a duration: it does not have enough information to be formatted as a weekday.

However, if the specifier refers to a time of day (`%H`, `%I`, `%p`, etc.), a duration is interpreted as the time elapsed since midnight. So `format("{:%H:%M}", 90min)` prints `01:30`.

¶5 Unless explicitly requested, the result of formatting a chrono type does not contain time zone abbreviation or offset information. When the information is available, `%Z` and `%z` print them, respectively; note 1 explains that if the information is not available, `%Z` or `%z` throws `format_error`.

Roughly what information each type has:

| Type | Date fields | Time fields | Time zone |
|---|---|---|---|
| `duration`, `hh_mm_ss` | None (except `%j`: number of days) | Yes, counted from midnight | None |
| `sys_time`, `utc_time`, `file_time`, etc. | Yes | Yes | `%Z` is `UTC` (`TAI` for tai, `GPS` for gps), `%z` is `+0000` |
| `local_time` | Yes | Yes | None: `%Z` and `%z` throw |
| Calendar types | Their own fields | None | None |
| `zoned_time` | Yes | Yes (local time) | Yes |

### `format_error` often becomes a compile error

```cpp
#include <chrono>
#include <format>
using namespace std::chrono;

int main() {
    auto a = std::format("{:%A}", 3s);                  // libc++: compile error, a duration has no weekday
    auto b = std::format("{:%Z}", local_seconds{});     // libc++: compile error, local_time has no time zone
}
```

The format string of `std::format` is checked at compile time: the constructor of `basic_format_string` is `consteval`, and it calls the formatter's `parse` during constant evaluation ([[format]]). Whether a type has a given piece of information at all can be determined during `parse`. `parse` throws `format_error`, constant evaluation fails, and the result is a compile error.

libc++ (Clang 23) reports `call to consteval function ... is not a constant expression` for both lines, with a message such as `"The supplied date time doesn't contain a weekday"` in the notes. The standard only says `format_error` is thrown, without specifying whether the check happens in `parse` or `format`. Only when the compile-time check is bypassed with `std::vformat` is the exception received at run time.

Some errors can only be detected at run time, because they depend on the value. Table 133 specifies that `%a` throws `format_error` if the value is not a valid weekday:

```cpp run ok
#include <chrono>
#include <format>
#include <iostream>
using namespace std::chrono;

int main() {
    try {
        weekday wd{9};
        std::cout << std::vformat("{:%a}", std::make_format_args(wd)) << '\n';
    } catch (const std::format_error& e) {
        std::cout << "format_error: " << e.what() << '\n';
    }
    std::cout << std::format("{}", weekday{9}) << '\n';   // 9 is not a valid weekday
}
```

## Omitting chrono-specs (¶7)

¶7 Unless otherwise specified, if *chrono-specs* is omitted, the result is as if the object were streamed to a `basic_ostringstream` imbued with the formatting locale, and `os.str()` were then copied to the output according to the fill, width and other specifications. Example 4: `format("{:=>8}", 42ms)` gives `"====42ms"`.

This unifies `{}` with `operator<<`. Formatting a `sys_time` with `{}` gives the `%F %T` form; formatting the invalid `year_month_day{2024y/February/30}` gives `2024-02-30 is not a valid date`, while writing `{:%F}` explicitly prints only `2024-02-30`, with no note appended.

## The formatters for each clock (¶10–¶15)

| Specialization | `%Z` | `%z` | Other | Paragraph |
|---|---|---|---|---|
| `sys_time` | `UTC` | `+0000` | | ¶10 |
| `utc_time` | `UTC` | `+0000` | During a leap second insertion, the integral part of the seconds field is `60` | ¶11 |
| `tai_time` | `TAI` | `+0000` | Displayed as `sys_time{tp.time_since_epoch()}` minus the days from 1958 to 1970 | ¶12 |
| `gps_time` | `GPS` | `+0000` | Displayed as `sys_time{tp.time_since_epoch()}` plus the days from 1970-01-01 to 1980-01-06 | ¶13 |
| `file_time` | `UTC` | `+0000` | Displayed as `clock_cast<system_clock>(t)` or `clock_cast<utc_clock>(t)` | ¶14 |
| `local_time` | Throws `format_error` | Throws `format_error` | | ¶15 |

The conversions of ¶12 and ¶13 just shift the epoch, ignoring leap seconds. TAI and GPS do not insert leap seconds in the first place; their readings are counted from their own epochs at 86400 seconds per day.

## `local_time_format` and `zoned_time` (¶16–¶19)

`local_time` has no time zone information. If you know its abbreviation and offset (read from a file, say) and want to print them together, use `local_time_format`:

```cpp
template<class Duration>
  local-time-format-t<Duration>
    local_time_format(local_time<Duration> time, const string* abbrev = nullptr,
                      const seconds* offset_sec = nullptr);
```

¶16 It returns an exposition-only aggregate `{time, abbrev, offset_sec}`. ¶17–¶18 The formatter for this type is equivalent to `%F %T %Z` when *chrono-specs* is omitted; `%Z` prints `*abbrev` and `%z` prints `*offset_sec`, and if the corresponding pointer is null, `format_error` is thrown.

The parameters are pointers, and the returned object stores only the pointers, so the objects pointed to must outlive the formatting call:

```cpp
std::string abbr = "CST";
std::cout << std::format("{}", local_time_format(lt, &abbr));   // OK
auto f = local_time_format(lt, &std::string("CST"));            // error: cannot take the address of a prvalue
```

¶19 The formatter for `zoned_time` derives from the formatter for `local-time-format-t`. Its `format` first gets `sys_info info = tp.get_info()`, then calls the base class with `{tp.get_local_time(), &info.abbrev, &info.offset}`. So `%Z` and `%z` are always available for `zoned_time`, and `{}` prints something like `2024-03-15 09:00:00 EDT`. `info` is a local variable, and the pointers are used only within this call, so they do not dangle.

libc++ in our tests does not yet provide `local_time_format` or `zoned_time`, so the code in this section has not been verified by compiling it.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

¶8–¶9 {{c++26}}: `std::print` may write output directly without holding the stream lock when the formatter is guaranteed not to call user code; this is controlled by `enable_nonlocking_formatter_optimization` ([[print.fun]]). For `duration`, the library provides only one specialization, whose value is the same as for `Rep`; for `zoned_time`, it provides a specialization only for the case where `TimeZonePtr` is `const time_zone*`, with value `true`. A user-defined `Rep` or `TimeZonePtr` may run arbitrary code, so it cannot be enabled by default.

</details>

## Common misconceptions

!!! pitfall "`%S` prints only whole seconds"
    `format("{:%T}", system_clock::now())` prints 6 fractional digits with libc++ in our tests, because `system_clock::duration` is microseconds; with libstdc++ it is nanoseconds and prints 9 digits. For a fixed format, `floor<seconds>` or `floor<milliseconds>` first.

!!! pitfall "`%Z` gives the local time zone"
    `format("{:%Z}", system_clock::now())` is always `UTC`, because a `sys_time` is UTC by definition. To display the local time zone, format `zoned_time{current_zone(), now}`.

!!! pitfall "Setting the global locale localizes the output"
    After setting the global locale, `format("{:%B}", t)` still prints the English month name. Localization requires writing `{:L%B}` and passing or setting the appropriate locale.

## Summary

- Format specification: fill, align, width, a precision usable only for floating-point durations, an optional `L`, plus conversion specifiers.
- The `"C"` locale is used by default; only `L` localizes.
- The number of `%S` fractional digits is determined by the precision of the type.
- The `-` of a negative duration is placed before the first conversion specifier.
- Missing information throws `format_error`; what can be detected during `parse` becomes a compile error through compile-time format string checking.
- `local_time` has no `%Z`/`%z`; use `local_time_format` or `zoned_time` when needed.
