---
title: Parsing chrono values
summary: "is >> parse(fmt, x) reads a chrono value from a stream according to a % format string, calling from_stream through ADL; how parse flags differ from formatting specifiers (maximum width, case insensitivity, the century window of %y, whitespace matching); failure sets failbit and leaves the target unmodified; sys_time subtracts the %z offset while local_time does not."
updated: 2026-10-19
---

!!! tldr
    - `in >> parse("%F %T", tp)` reads a chrono value from a stream according to a format string. `parse` is just a wrapper; the actual parsing is done by `from_stream`, found through argument-dependent lookup, so user types can plug in too.
    - On a parse failure or insufficient information (for example, reading a `year_month_day` with no day), `failbit` is set, the target object keeps its value, and nothing is thrown.
    - A single space in the format string matches zero or more whitespace characters; `%n` matches exactly one, and `%t` matches zero or one.
    - When parsing into a `sys_time`, the offset read by `%z` is subtracted from the result, giving UTC; when parsing into a `local_time`, the offset is only reported and the time is not modified.
    - The manipulator returned by `parse` stores only a pointer to the format string; create and use it within the same full-expression.

## Basic usage

```cpp
#include <chrono>
#include <iostream>
#include <sstream>
using namespace std::chrono;

int main() {
    sys_seconds st;
    local_seconds lt;
    minutes off{};
    std::istringstream{"2024-03-01 08:00:00 +0800"} >> parse("%F %T %z", st);
    std::istringstream{"2024-03-01 08:00:00 +0800"} >> parse("%F %T %z", lt, off);
    std::cout << st << '\n';                  // 2024-03-01 00:00:00: converted to UTC
    std::cout << lt << ' ' << off << '\n';    // 2024-03-01 08:00:00 480min: kept as is
}
```

`parse` is the inverse of [[time.format]]. It is built on iostreams rather than being a standalone facility like `std::format`, because in C++20 the standard library had no corresponding `std::scan`, and streams were the only ready-made input abstraction.

!!! impl "Not yet implemented in libc++"
    libc++ in our tests does not implement `parse` or the `from_stream` overloads, so none of the code on this page has been verified by compiling it, and it carries no verdict marks. It is written to the standard and can be run on Compiler Explorer with a recent GCC or MSVC.

## `parse` and `from_stream` (¶1–¶14)

¶1 Each `parse` overload calls `from_stream` unqualified, so as to enable argument-dependent lookup (ADL, [[basic.lookup.argdep]]).

This is a customization point design. `from_stream(is, fmt, value, abbrev, offset)` does the actual parsing, and this clause provides one for every chrono type, for example [[time.duration.io#3]], [[time.clock.system.nonmembers#6]] and [[time.cal.day.nonmembers#8]]. `parse(fmt, value, ...)` is only a wrapper that returns a manipulator, making the `is >> parse(...)` spelling work. When users provide a `from_stream` in their own type's namespace, `parse` finds it through ADL.

The four groups of overloads differ in whether they additionally take a time zone abbreviation `abbrev` and a UTC offset `offset`. Each group has two forms of format string, `const charT*` and `basic_string`; in the table below, `F` is `fmt` for the former and `fmt.c_str()` for the latter:

| Overload | Calls | Paragraphs |
|---|---|---|
| `parse(fmt, tp)` | `from_stream(is, F, tp)` | ¶3–¶5 |
| `parse(fmt, tp, abbrev)` | `from_stream(is, F, tp, addressof(abbrev))` | ¶6–¶8 |
| `parse(fmt, tp, offset)` | `from_stream(is, F, tp, static_cast<basic_string<...>*>(nullptr), &offset)` | ¶9–¶11 |
| `parse(fmt, tp, abbrev, offset)` | `from_stream(is, F, tp, addressof(abbrev), &offset)` | ¶12–¶14 |

The *Constraints* (¶4, ¶7, ¶10, ¶13) require the corresponding `from_stream` call to be well-formed when treated as an unevaluated operand. So calling `parse` for a type with no `from_stream` makes `parse` itself non-viable, and the error appears at the call site rather than deep inside an instantiation.

The *Returns* (¶5, ¶8, ¶11, ¶14) is a manipulator of unspecified type: the expression `is >> parse(...)` has type `basic_istream<charT, traits>&` and value `is`, and calls the corresponding `from_stream`.

The address of `abbrev` is taken with `addressof`, not `&`. The template arguments of `basic_string<charT, traits, Alloc>` can be user-defined types, and ADL might find a unary `operator&` that the user overloaded for it. Using `addressof` for any object that may involve user types is the standard library's consistent practice.

### Dangling format strings (¶2)

```cpp
auto m = parse(std::string("%F"), ymd);   // the temporary string is destroyed at the end of this line
in >> m;                                  // the pointer in the manipulator dangles: UB
```

The manipulator stores only a pointer to the format string. ¶2 *Recommended practice* suggests that implementations make it difficult to accidentally store or use such a manipulator, for example by making it non-moveable and disallowing stream extraction into an lvalue of such a manipulator.

Being non-moveable alone does not stop the first line: since C++17, `auto m = parse(...)` still compiles thanks to guaranteed copy elision ([[class.copy.elision]]). So the second half of the recommendation is to disallow extraction into an lvalue, which makes the second line fail to compile, leaving only the `in >> parse(...)` form that creates and uses the manipulator in the same full-expression. This is only a recommendation; portable code should stick to that form on its own.

## General parsing rules (¶15–¶17)

¶15 All `from_stream` functions behave as **unformatted input functions** ([[istream.unformatted]]): constructing the sentry does not skip leading whitespace. What effect they have on the value later returned by `gcount()` is unspecified.

A format string consists of ordinary characters and flags beginning with `%`. Some flags can be modified by `E` or `O`, and some can take a positive integer width *N* giving the maximum number of characters to read, as in `%4Y`. Characters in the format string not listed in Table 134, other than whitespace, must match the input exactly. A whitespace character in the format string matches zero or more whitespace characters in the input.

¶16 If the type being parsed cannot represent the information a flag refers to, `is.setstate(ios_base::failbit)` is called. Example 1: a duration cannot represent a weekday. As with formatting, the time-of-day flags (`%H`, `%I`, `%p`, etc.) are interpreted for a duration as the time elapsed since midnight.

¶17 If not everything specified by the format string can be parsed, or the parsed information is not sufficient to determine a complete duration, time_point or calendar type, `setstate(failbit)` is called:

```cpp
year_month_day ymd;
std::istringstream{"2024-03"} >> parse("%Y-%m", ymd);   // failbit: no day
year_month ym;
std::istringstream{"2024-03"} >> parse("%Y-%m", ym);    // OK
```

Each `from_stream` also specifies that the target object is not modified if parsing fails (for example [[time.clock.system.nonmembers#6]]). So after a failure `ymd` keeps its value, and you must check the stream state before using it.

## Parse flags (Table 134)

Most flags mirror the formatting specifiers of Table 133 in [[time.format]]; only the parsing-specific rules are listed below. Flags with a width all allow, but do not require, leading zeros.

| Flag | Parsing rule | Default width *N* |
|---|---|---|
| `%a` `%A` | The locale's weekday name, full or abbreviated, case-insensitive | |
| `%b` `%B` `%h` | The locale's month name, full or abbreviated, case-insensitive | |
| `%Y` | Year | 4 |
| `%y` | Last two digits of the year; if the century is not given by `%C` or similar, 69–99 means 1969–1999 and 00–68 means 2000–2068 | 2 |
| `%C` | Century | 2 |
| `%m` `%d` `%e` `%H` `%I` `%M` | Month, day, hour, minute | 2 |
| `%j` | Day of the year; for a duration, the number of days | 3 |
| `%S` | Seconds; default width 2 if the target precision converts to whole seconds, otherwise the width is determined by the decimal precision of the target, read as a fixed-format `long double`, with the decimal point determined by the locale | 2 or wider |
| `%u` `%w` | Weekday as a number (ISO encoding / C encoding) | 1 |
| `%U` `%W` `%V` `%G` `%g` | Week numbers, ISO week-based year | 2, 2, 2, 4, 2 |
| `%F` | `%Y-%m-%d`; with a width *N*, it applies only to `%Y` | |
| `%z` | `[+|-]hh[mm]`: `-0430`, `04` | |
| `%Ez` `%Oz` | `[+|-]h[h][:mm]`: `-04:30`, `4` | |
| `%Z` | Time zone abbreviation or name: a single word containing only letters, digits and `_` `/` `-` `+` from the basic character set | |
| `%n` | Exactly one whitespace character | |
| `%t` | Zero or one whitespace character | |
| `%%` | A `%` | |

The 69/68 boundary of `%y` is the same as in POSIX `strptime`. Example 2 in the `%y` row of the table: `istringstream{"-20 76"} >> parse("%3C %y", y)` gives `-1976y`. `%3C` reads at most 3 characters and reads the signed `-20`; with the century already given, `%y` does not apply the window.

Combining spaces, `%n` and `%t` can describe various whitespace patterns. Note 1 in the `%n` row gives examples: `"%n "` matches one or more whitespace characters, and `"%n%t%t"` matches one to three.

The string read by `%Z` is handed to the caller only through the `abbrev` output parameter and takes no part in the time conversion. Time zone abbreviations are not unique ([[time.zone]]), and the standard does not attempt to infer an offset from one.

## Offsets: how `sys_time` and `local_time` differ

The opening example parses the same input twice with different results. When `%z` is parsed successfully, the clocks' `from_stream` functions behave in one of two ways:

- `sys_time`, `utc_time`, `tai_time`, `gps_time`, `file_time`: the offset is written to `*offset` (if non-null) and subtracted from the parsed time, so the result is the true UTC time point ([[time.clock.system.nonmembers#6]] etc.).
- `local_time`: the offset is only written to `*offset` and the time is not modified, because local time is not aligned with UTC in the first place ([[time.clock.local#5]]).

## Providing parsing for a custom type

`parse` finds `from_stream` through ADL, so all that is needed is a `from_stream` with a compatible signature in the type's namespace:

```cpp
#include <chrono>
#include <iostream>
#include <sstream>
#include <string>

namespace app {
    struct date { std::chrono::year_month_day ymd; };

    template<class CharT, class Traits, class Alloc = std::allocator<CharT>>
    std::basic_istream<CharT, Traits>&
    from_stream(std::basic_istream<CharT, Traits>& is, const CharT* fmt, date& d,
                std::basic_string<CharT, Traits, Alloc>* abbrev = nullptr,
                std::chrono::minutes* offset = nullptr) {
        std::chrono::year_month_day tmp;
        std::chrono::from_stream(is, fmt, tmp, abbrev, offset);   // reuse the standard implementation
        if (is) d.ymd = tmp;                                     // leave d unmodified on failure
        return is;
    }
}

int main() {
    app::date d;
    std::istringstream{"2024-02-29"} >> std::chrono::parse("%F", d);   // ADL finds app::from_stream
    std::cout << d.ymd << '\n';
}
```

## Common misconceptions

!!! pitfall "A parse failure throws"
    A failed `parse` only sets `failbit`; unless the stream has `exceptions()` set, nothing is thrown, and the target object keeps its value. You must check `in` after `in >> parse(...);`.

!!! pitfall "A time without an offset can be parsed straight into `sys_time`"
    A `"2024-03-01 08:00:00"` from a user interface is almost always local time. Parsing it into `sys_seconds` gives no error, but the result is 08:00 UTC. Parse it into `local_seconds` instead, then convert through a `time_zone` or `zoned_time` ([[time.zone]]).

!!! pitfall "A space in the format string matches exactly one space"
    A space matches zero or more whitespace characters, so `parse("%F %T", tp)` also accepts `"2024-03-01      13:05:07"`, and even `"2024-03-0113:05:07"`. Use `%n` when exactly one whitespace character is required.

## Summary

- `is >> parse(fmt, x)` calls `from_stream` through ADL; a user type plugs in by providing its own `from_stream`.
- On failure `failbit` is set and the target is not modified; insufficient information (such as a missing day when parsing a `year_month_day`) also counts as failure.
- Parse flags broadly mirror the formatting specifiers, with the addition of a maximum width *N*, case-insensitive names, the century window of `%y`, and whitespace matching rules.
- The `sys_time` family subtracts the `%z` offset to get UTC; `local_time` does not.
- The manipulator may refer to a temporary format string; create and use it within the same full-expression.
