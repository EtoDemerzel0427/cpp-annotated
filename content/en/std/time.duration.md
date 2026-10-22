---
title: Class template duration
summary: "duration represents a length of time as a tick count plus a compile-time period; which conversions may happen implicitly, how the types of arithmetic results are determined, how duration_cast, floor, ceil and round round, and the two common mistakes: overflow and integer truncation."
updated: 2026-10-19
---

!!! tldr
    - `duration` keeps the number in the object and the unit in the type: `milliseconds{1500}` is just an integer 1500 at run time, and "milliseconds" exists only in the template arguments.
    - Conversions that lose no information (seconds to milliseconds, anything to floating point) may happen implicitly; conversions that truncate (milliseconds to seconds, floating point to integer) must be written with `duration_cast`, `floor`, `ceil` or `round`.
    - Addition, subtraction and comparison across units first convert to the common type, whose period is the greatest common divisor of the two periods; a duration divided by a duration gives a unitless number.
    - `duration_cast` truncates toward zero, `floor` and `ceil` round toward negative and positive infinity, and `round` rounds halfway cases to even.
    - Implicit conversion guarantees only no truncation, not no overflow. `nanoseconds` can represent only about ±292 years.

## The unit is in the type

<div class="compare" markdown="1">

```cpp run ok
#include <chrono>
using namespace std::chrono;
void wait_for(milliseconds) {}
int main() {
  wait_for(2s);      // converted to 2000ms
  wait_for(1500ms);
}
```

```cpp run error
#include <chrono>
using namespace std::chrono;
void wait_for(milliseconds) {}
int main() {
  wait_for(2);       // error: no unit
  wait_for(1.5s);    // error: may truncate
}
```

</div>

The parameter of `wait_for` is `milliseconds`. Passing `2s` converts seconds to milliseconds automatically, just a multiplication by 1000. Passing the bare integer `2` fails to compile, because nobody knows whether it is seconds or milliseconds. Passing `1.5s` fails too: its count is floating point, and converting to integer milliseconds would in general truncate.

The conversion factors are computed at compile time, leaving at most one multiplication or division at run time. A `milliseconds` is as big and as fast as a `long long`.

## Representation: tick count plus period [time.duration.general]

¶1 A duration measures the time between two points in time. It has two parts: a **representation**, which holds the tick count, and a **tick period** ([[g:tick-period]]), the number of seconds between successive ticks, expressed as a compile-time rational number `ratio` ([[ratio]]).

```cpp
template<class Rep, class Period = ratio<1>>
class duration {
public:
  using rep    = Rep;
  using period = Period::type;   // the reduced ratio
private:
  rep rep_;                      // exposition only
};
```

The standard's examples (¶6):

```cpp
duration<long, ratio<60>> d0;       // counts minutes using a long
duration<long long, milli> d1;      // counts milliseconds using a long long
duration<double, ratio<1, 30>> d2;  // counts 1/30 of a second (30 Hz frames) using a double
```

`period` is the reduced `Period::type`. So the `period` of `duration<int, ratio<2, 4>>` is `ratio<1, 2>`, but it and `duration<int, ratio<1, 2>>` are still two different types.

¶2 `Rep` should be an arithmetic type or a class emulating an arithmetic type. Using a cv-qualified type or another `duration` as `Rep` makes the program ill-formed. The latter rules out durations of durations such as `duration<seconds>`, which would make overload resolution of `common_type` and `operator/` ambiguous.

¶3 `Period` must be a specialization of `ratio`, and `Period::num` must be positive, or the program is ill-formed. A zero or negative period makes no sense.

The default constructor is `= default` and does not initialize `rep_`. A local variable `seconds s;` has an indeterminate count, and since C++26 reading it gives an erroneous value ([[basic.indet]]). When you need zero, write `seconds{}` or `seconds::zero()`.

## When implicit conversion is allowed [time.duration.cons]

### Construction from a number (¶1–¶2)

```cpp
template<class Rep2> constexpr explicit duration(const Rep2& r);
```

¶1 This constructor requires `Rep2` to be implicitly convertible to `rep`, and one of the following: `rep` is a floating-point type (¶1.1), or `Rep2` is not a floating-point type (¶1.2). In other words, it forbids only constructing an integer-count duration from a floating-point number, which would drop the fractional part.

```cpp
duration<int, milli> d(3);       // OK
duration<int, milli> d2(3.5);    // error: Rep2 is floating-point, rep is not
```

The constructor is `explicit`, so `seconds s = 5;` is ill-formed. A bare number has no unit and cannot silently become a duration.

### Construction from another duration (¶3–¶4)

```cpp
template<class Rep2, class Period2>
constexpr duration(const duration<Rep2, Period2>& d);   // not explicit
```

¶3 This converting constructor requires `Rep2` to be implicitly convertible to `rep`, the division of the two periods not to overflow at compile time, and one of the following:

- ¶3.1 the target `rep` is a floating-point type;
- ¶3.2 the source period is an integral multiple of the target period (`ratio_divide<Period2, period>::den` is 1), and the source `Rep2` is not a floating-point type.

¶3.2 means the conversion needs only multiplication. Note 1 says this requirement prevents implicit truncation between integer durations. ¶4 specifies that the converted value is `duration_cast<duration>(d).count()`.

| Direction | Example | Implicit conversion |
|---|---|---|
| integer, coarse to fine | `seconds` → `milliseconds` | allowed, multiply by 1000 |
| integer, fine to coarse | `milliseconds` → `seconds` | not allowed, needs division |
| integer, periods not multiples | `ratio<1,3>` → `ratio<1,2>` | not allowed |
| anything to floating point | `milliseconds` → `duration<double>` | allowed |
| floating point to integer | `duration<double>` → `seconds` | not allowed, even with the same period |

```cpp run ok title="duration-conv.cpp"
#include <chrono>
#include <type_traits>
using namespace std::chrono;

static_assert( std::is_convertible_v<seconds, milliseconds>);
static_assert(!std::is_convertible_v<milliseconds, seconds>);
static_assert( std::is_convertible_v<milliseconds, duration<double>>);
static_assert(!std::is_convertible_v<duration<double>, seconds>);
static_assert( std::is_convertible_v<days, hours>);
static_assert(!std::is_convertible_v<hours, days>);
static_assert(!std::is_constructible_v<seconds, double>);   // ¶1

int main() {
  milliseconds ms = 2s;                      // 2000ms
  auto s = duration_cast<seconds>(1999ms);   // explicit truncation: 1s
  return (ms.count() == 2000 && s.count() == 1) ? 0 : 1;
}
```

These conditions are all written as *Constraints*. When they are not met, the constructor does not participate in overload resolution, rather than erroring at instantiation. So `is_convertible_v` detects non-convertibility, and with two overloads `f(seconds)` and `f(milliseconds)`, `f(1500ms)` selects only the latter.

## Observers, member operations and special values

[[time.duration.observer#1]] specifies that `count()` returns `rep_`, that is, the tick count, not the number of seconds: `milliseconds{1500}.count()` is 1500.

The member operators of [time.duration.arithmetic] all act directly on `rep_`, with three points worth noting:

- Unary `+` and `-` return `common_type_t<duration>`, that is, the type with the reduced period (¶1–¶2). The difference shows only for types written with an unreduced `ratio`.
- The parameter of `+=` and `-=` is `const duration&` of the same type (¶9–¶12). `ms += 1s` compiles because `1s` first converts implicitly to `milliseconds`; `s += 1ms` does not compile.
- The parameter of `*=`, `/=` and `%=` is `const rep&`; they multiply or divide by a unitless number (¶13–¶18). There is also a `%=` taking a duration (¶19).

`zero()`, `min()` and `max()` in [time.duration.special] are given by `duration_values<rep>` ([[time.traits]]). The `min()` of an integer count is the most negative value, not zero.

## Mixed-unit arithmetic [time.duration.nonmember]

```cpp run ok title="duration-arith.cpp"
#include <chrono>
#include <type_traits>
using namespace std::chrono;

static_assert(std::is_same_v<decltype(1s + 1ms), milliseconds>);
static_assert(std::is_same_v<decltype(1s * 1.5), duration<double>>);
static_assert(std::is_same_v<decltype(1s / 2ms), long long>);   // libc++
static_assert(std::is_same_v<decltype(1h % 7min), minutes>);

static_assert(1s + 1ms == 1001ms);
static_assert(1s / 2ms == 500);
static_assert(1h % 7min == 4min);
static_assert(seconds{1} / 2 == 0s);   // integer division: truncates
static_assert(-7s / 2 == -3s);         // truncates toward zero

int main() {}
```

¶1 Below, `CD` denotes the return type of the function.

| Operation | Return type | Paragraphs |
|---|---|---|
| `d1 + d2`, `d1 - d2` | `common_type_t<D1, D2>` | ¶2–¶3 |
| `d * s`, `s * d` | `duration<common_type_t<Rep1, Rep2>, Period>` | ¶4–¶7 |
| `d / s`, `d % s` | same | ¶8–¶9, ¶12–¶13 |
| `d1 / d2` | `common_type_t<Rep1, Rep2>`, a pure number | ¶10–¶11 |
| `d1 % d2` | `common_type_t<D1, D2>` | ¶14 |

The common type of two durations takes the greatest common divisor of the two periods ([[time.traits]]), so `1s + 1ms` has type `milliseconds` and value 1001ms. Converting to the common type needs only multiplication, so integer counts lose no information, but they may overflow.

When a duration is multiplied by a number, the count type may widen: `1s * 1.5` has type `duration<double>`.

¶8 `d / s` and `d % s` have an extra constraint: `Rep2` is not a specialization of duration. Without it, `1s / 2ms` would match both the "duration divided by number" and "duration divided by duration" templates.

¶10 When dividing two durations, both are first converted to the common type, then the counts are divided. `1s / 2ms` asks how many 2 milliseconds fit in 1 second; the result is 500, with no unit. On libc++ its type is `long long`; this depends on the choice of `seconds::rep` and `milliseconds::rep`, for which the standard specifies only minimum bit counts.

The result of `d1 % d2` is a duration of the common type, often used to take the part within a day: `tp.time_since_epoch() % days{1}`.

All integer operations follow the rules of the built-in operations: division truncates toward zero ([[expr.mul]]), and signed overflow is undefined behavior.

## Comparison [time.duration.comparisons]

¶2 `==` and `<` first convert both sides to the common type, then compare the counts (¶3). So `1s == 1000ms` is true and `1999ms < 2s` is true: what is compared is physical duration. `>`, `<=` and `>=` are derived from `<` (¶4–¶6).

¶7 `<=>` requires the `rep` of the common type to satisfy `three_way_comparable`. For `duration<double>`, the result is `partial_ordering`, because NaN is incomparable with every value.

!!! lawyer "Cross-unit comparison can overflow too"
    `nanoseconds::max() == hours{3'000'000}` must first convert `hours` to `nanoseconds`, and that multiplication overflows. The result is undefined behavior, not `false`.

## Truncation and rounding [time.duration.cast]

```cpp run ok title="rounding.cpp"
#include <chrono>
using namespace std::chrono;

static_assert(duration_cast<seconds>(-1500ms) == -1s);  // toward zero
static_assert(floor<seconds>(-1500ms)         == -2s);  // toward negative infinity
static_assert(ceil<seconds>(-1500ms)          == -1s);  // toward positive infinity
static_assert(round<seconds>(1500ms)          ==  2s);  // 1.5 → 2
static_assert(round<seconds>(2500ms)          ==  2s);  // 2.5 → 2, to even
static_assert(round<seconds>(-2500ms)         == -2s);

int main() {}
```

### duration_cast (¶1–¶3)

¶2 Let `CF` be the conversion factor `ratio_divide<Period, ToDuration::period>` and `CR` the intermediate computation type `common_type<ToDuration::rep, Rep, intmax_t>::type`. There are four cases by `CF`:

| Case | Computation |
|---|---|
| ¶2.1 `CF` is 1/1 | `static_cast<ToRep>(d.count())` |
| ¶2.2 only the denominator is 1 | `static_cast<ToRep>(static_cast<CR>(d.count()) * CF::num)` |
| ¶2.3 only the numerator is 1 | `static_cast<ToRep>(static_cast<CR>(d.count()) / CF::den)` |
| ¶2.4 otherwise | `static_cast<ToRep>(static_cast<CR>(d.count()) * CF::num / CF::den)` |

The note in ¶3 sums up the design: all conversions use `static_cast`; multiplications and divisions are omitted when the factor is known at compile time to be 1; intermediate results are computed in `CR`, at least as wide as `intmax_t`, and converted to the target type only in the last step.

Several conclusions follow:

- In the integer cases `duration_cast` truncates toward zero, because ¶2.3 uses the built-in `/`. `duration_cast<seconds>(-1500ms)` is `-1s`, not `-2s`.
- ¶2.4 multiplies before dividing to preserve precision, but the multiplication may overflow in `CR`.
- In the final `static_cast` from floating point to integer, if the value is out of the target type's range the behavior is undefined ([[conv.fpint]]).

### floor, ceil, round (¶4–¶9) {{c++17}}

¶5 `floor<To>(d)` returns the greatest value of `To` with `t <= d`, rounding toward negative infinity. ¶7 `ceil<To>(d)` returns the least value with `t >= d`, rounding toward positive infinity.

¶9 `round<To>(d)` returns the value closest to `d`; when two values are equally close, it returns the one with `t % 2 == 0`. This rounding is often called banker's rounding; it does not accumulate a systematic bias when many rounded values are summed. ¶8 requires `To::rep` not to be a floating-point type.

For time points, `floor` is the one used most. `floor<days>(system_clock::now())` gives midnight today (UTC); with `duration_cast<days>` instead, time points before 1970 would give midnight tomorrow, because negative values truncate toward zero (see [[time.point]]).

### abs [time.duration.alg] {{c++17}}

¶1 `abs` accepts only a signed `Rep`. ¶2 It returns `d` if `d >= d.zero()`, otherwise `-d`. As with the built-in `abs(INT_MIN)`, taking `abs` of `min()` overflows.

## Literals [time.duration.literals] {{c++14}}

```cpp
using namespace std::chrono_literals;
auto constexpr aday       = 24h;
auto constexpr lesson     = 45min;
auto constexpr halfanhour = 0.5h;
```

¶1 The suffixes `h`, `min`, `s`, `ms`, `us` and `ns` on integer literals give `hours`, `minutes`, `seconds`, `milliseconds`, `microseconds` and `nanoseconds` respectively. ¶2 On floating-point literals, the count type is an unspecified floating-point type, so `0.5h` means half an hour.

¶3 If the value of an integer literal cannot be represented in the result type, the program is ill-formed.

The note in ¶8 says `s` does not conflict with `basic_string`'s `""s`: one applies to numbers, the other to string literals. The microsecond suffix is `us` rather than `µs` because literal suffixes must be identifiers, and ASCII characters are the easiest to type.

!!! impl "libc++ does not diagnose literal overflow"
    Per ¶3, `18'000'000'000'000'000'000h` should be an error: it fits in `unsigned long long` but not in `hours::rep`. libc++ in our tests constructs `hours` directly from the value, compiles it, and the count becomes `-446744073709551616`. This is a nonconformance in libc++.

## Output [time.duration.io] {{c++20}}

```cpp run ok title="duration-io.cpp"
#include <chrono>
#include <iostream>
using namespace std::chrono;

int main() {
  std::cout << 42ms << ' ' << 3us << ' ' << 90min << ' ' << days{2} << '\n';
  std::cout << duration<int, std::ratio<1, 3>>{5} << ' ' << weeks{1} << '\n';
  std::cout << duration<double, std::milli>{1.5} << '\n';
}
```

libc++ in our tests prints `42ms 3µs 90min 2d`, `5[1/3]s 1[604800]s` and `1.5ms`.

¶1 The effect of `os << d` is: output `d.count()` and the unit suffix into a string stream that copies `os`'s format flags, locale and precision, then write the whole string to `os`. Building a string first makes `setw` apply to the number and suffix together.

The suffix is determined by the reduced period (¶1.1–¶1.22):

| Period | Suffix |
|---|---|
| `atto`, `femto`, `pico`, `nano` | `as`, `fs`, `ps`, `ns` |
| `micro` | `µs` or `us`, implementation-defined |
| `milli`, `centi`, `deci`, `ratio<1>` | `ms`, `cs`, `ds`, `s` |
| `deca` through `exa` | `das`, `hs`, `ks`, `Ms`, `Gs`, `Ts`, `Ps`, `Es` |
| `ratio<60>`, `ratio<3600>`, `ratio<86400>` | `min`, `h`, `d` |
| otherwise, denominator 1 | `[num]s` |
| otherwise | `[num/den]s` |

`weeks`, `months` and `years` have no dedicated suffixes and display as `[604800]s`, `[2629746]s` and `[31556952]s` respectively.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[[time.duration.general#4]]: members of duration do not throw exceptions other than those thrown by operations on the count type itself. When the count is a built-in arithmetic type, no member throws.

[[time.duration.general#5]]: whether the defaulted copy constructor is a constexpr function depends entirely on whether the initialization copying `rep_` is constexpr-suitable ([[dcl.constexpr]]).

[[time.duration.io#3]] and paragraph 4: `from_stream` parses a duration in the format of [[time.parse]]; on failure it sets `failbit` and leaves the target unmodified. libc++ in our tests does not implement it yet.

</details>

## History

!!! history
    - C++11 introduced `<chrono>` via [[N2661]]; the implicit conversion rules of `duration` have barely changed since.
    - C++14 added the literal suffixes `h`, `min`, `s` and so on.
    - C++17's [[P0092R1]] added `floor`, `ceil`, `round` and `abs`. Before that there was only `duration_cast`, truncating toward zero.
    - C++20's [[P0355R7]] added calendars and time zones, and with them gave duration stream output, `from_stream`, and the aliases `days`, `weeks`, `months` and `years`.

## Common pitfalls

!!! pitfall "Implicit conversion can overflow too"
    The count of `nanoseconds` is at least 64 bits, and 2⁶³ nanoseconds is about 292 years. libstdc++'s `system_clock` counts in nanoseconds, so it can represent only up to the year 2262.

    ```cpp
    auto ns = duration_cast<nanoseconds>(years{300});   // UB: signed overflow
    nanoseconds x = years{300};                         // also UB
    ```

    The second line is more insidious. The condition for implicit conversion (¶3.2) looks only at whether the periods are multiples, not at the range of values. Running with UBSan reports `signed integer overflow`; in a constant expression, the same overflow makes evaluation fail and the compiler gives a diagnostic.

!!! pitfall "Using int as the count type"
    2³¹ milliseconds is about 24.8 days. A service running for a month that accumulates uptime in a `duration<int, milli>` will overflow. The standard aliases have minimum bit requirements ([[time.syn]]), with `milliseconds` at least 45 bits; prefer them.

!!! pitfall "Division of integer durations truncates"
    `seconds{1} / 2` is `0s`, and `seconds{3} / seconds{2}` is `1`. When you need fractions, convert to a floating-point duration first: `duration<double>{3s} / 2s` is `1.5`.

!!! pitfall "Unsigned count types"
    `duration<unsigned>{1} - duration<unsigned>{2}` gives 4294967295 seconds, and `abs` cannot be used on unsigned counts either. Time differences can be positive or negative, so count types should be signed. `system_clock::rep` is explicitly required to be signed ([[time.clock]]).

!!! pitfall "count() throws the unit away"
    `usleep(d.count())` is correct only if `d` happens to be `microseconds`. At interface boundaries, convert to the target unit before taking the count: `usleep(duration_cast<microseconds>(d).count())`; better still, let the function take a duration directly.

## Questions

!!! question "Question 1"
    `seconds s = 1500ms;` is ill-formed. What about direct-initialization, `seconds s{1500ms};`?

<details markdown="1">
<summary>Answer</summary>

Equally ill-formed. The converting constructor is not `explicit`; what blocks it is the constraint in ¶3: the denominator of `milli` divided by `ratio<1>` is not 1, and the count type is an integer, so the constructor does not participate in overload resolution, and direct-initialization finds no viable constructor either. Write `duration_cast<seconds>(1500ms)` or `floor<seconds>(1500ms)`.
</details>

!!! question "Question 2"
    `1s / 2ms` and `1s / 2` are both a duration divided by something. Why is there no ambiguity?

<details markdown="1">
<summary>Answer</summary>

¶8 constrains the duration-divided-by-number version: `Rep2` is not a specialization of duration. For `1s / 2ms`, `Rep2` deduces as `milliseconds`, the constraint fails, and only the duration-divided-by-duration version remains. For `1s / 2`, deduction of the duration-divided-by-duration version fails, and only the duration-divided-by-number version remains.
</details>

!!! question "Question 3"
    Why is `round<seconds>(2500ms)` `2s` and not `3s`?

<details markdown="1">
<summary>Answer</summary>

¶9: 2s and 3s are equally close to 2.5s, in which case the one with `t % 2 == 0` is returned, that is, 2s.
</details>
