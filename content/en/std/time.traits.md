---
title: Time-related traits
summary: "duration learns about its representation type through four traits: treat_as_floating_point decides whether durations convert implicitly, duration_values gives the zero and extreme values, the common_type specialization takes the greatest common divisor of two periods, and is_clock decides whether a type is a clock; a program adding a specialization of is_clock is UB."
updated: 2026-10-19
---

!!! tldr
    - A duration with an integer representation converts implicitly only when no division is needed: `seconds` can become `milliseconds`, not the other way round. Representation types for which `treat_as_floating_point` is true are not subject to this restriction.
    - `duration::zero()`, `min()` and `max()` come from `duration_values`, where `min()` is `numeric_limits<Rep>::lowest()`, not `numeric_limits<Rep>::min()`.
    - The common type of two durations takes the greatest common divisor of the two periods, so both sides convert to it by multiplication alone; that is why `1s + 1ms` has type `milliseconds`. The multiplication may still overflow.
    - `is_clock` does only a syntactic check; a program adding a specialization of it has undefined behavior.

## treat_as_floating_point ([time.traits.is.fp])

```cpp run title="treat-as-fp.cpp" ok
#include <chrono>
#include <type_traits>
using namespace std::chrono;
using std::is_convertible_v;

struct fixed16 { /* some fixed-point type, implementation omitted */ };
template<>
struct std::chrono::treat_as_floating_point<fixed16>
    : std::true_type {};

// floating-point representation: allowed
static_assert(is_convertible_v<milliseconds, duration<double>>);
// integer representation needing division: rejected
static_assert(!is_convertible_v<milliseconds, seconds>);
// integer representation needing only multiplication: allowed
static_assert(is_convertible_v<seconds, milliseconds>);
static_assert(treat_as_floating_point_v<fixed16>);

int main() {}
```

```cpp
template<class Rep> struct treat_as_floating_point : is_floating_point<Rep> { };
```

¶1 `duration` uses this trait to decide whether a duration can be converted to another duration with a different tick period. If `treat_as_floating_point_v<Rep>` is true, durations always convert implicitly; otherwise implicit conversion depends on the two periods (see the constructors in [[time.duration]]).

Note 1 explains the intent: the trait indicates that a type behaves like a floating-point number, so losing a little precision in division is acceptable. When it is `false`, `Rep` is treated as an integer, and division truncates.

Converting `milliseconds` to `seconds` is exact for 1000ms and loses 500ms for 1500ms. The compiler does not know the value at compile time, so for integer representations it rejects every implicit conversion needing division, requiring you to write `duration_cast`, `floor` or `round` to show you know it truncates.

The specialization for `fixed16` in the example above is allowed: per [[namespace.std]], a program may specialize standard library class templates as long as the specialization depends on a program-defined type. `is_clock` below is exactly the opposite.

## duration_values ([time.traits.duration.values])

```cpp
template<class Rep>
struct duration_values {
  static constexpr Rep zero() noexcept;   // Rep(0)
  static constexpr Rep min() noexcept;    // numeric_limits<Rep>::lowest()
  static constexpr Rep max() noexcept;    // numeric_limits<Rep>::max()
};
```

¶1 `duration` uses this trait to construct special values of the representation type; `duration::zero()`, `min()` and `max()` ([[time.duration]]) all forward here. It is a separate trait because `Rep` can be a class type for which constructing these values may need some other approach, in which case the type's author specializes `duration_values`.

- ¶2–¶3 `zero()` returns `Rep(0)`, and the returned value must be the additive identity. Note 1 explains why `Rep()` is not used: for some types, `Rep()` may mean something else, such as an uninitialized value.
- ¶4–¶5 `min()` returns `numeric_limits<Rep>::lowest()` and must be less than or equal to `zero()`. For floating-point types, `numeric_limits<Rep>::min()` is the smallest positive normalized number, a positive value, which is why `lowest()` is used here.
- ¶6–¶7 `max()` returns `numeric_limits<Rep>::max()` and must be greater than `zero()`.

## The common_type specializations ([time.traits.specializations])

```cpp run title="common-period.cpp" ok
#include <chrono>
#include <iostream>
using namespace std::chrono;

int main() {
  using third = duration<int, std::ratio<1, 3>>;
  using half  = duration<int, std::ratio<1, 2>>;
  using C = std::common_type_t<third, half>;
  static_assert(std::is_same_v<C::period, std::ratio<1, 6>>);
  std::cout << third{1} + half{1} << '\n';   // 5[1/6]s, i.e. 5/6 of a second
}
```

```cpp
template<class Rep1, class Period1, class Rep2, class Period2>
struct common_type<chrono::duration<Rep1, Period1>, chrono::duration<Rep2, Period2>> {
  using type = chrono::duration<common_type_t<Rep1, Rep2>, see below>;
};
```

¶1 The period of the result is the greatest common divisor of `Period1` and `Period2`. Note 1 gives the algorithm: the numerator is the gcd of the two numerators, and the denominator is the lcm of the two denominators.

¶2 Note 2 explains why the gcd is used: it is the largest period to which both durations can be converted without division. Using only multiplication means even integer representations do not truncate. Addition, subtraction and comparison of durations all convert to the common type first, so `1s + 1ms` has type `milliseconds`: `1s` is multiplied by 1000, and no information is lost.

| `Period1` | `Period2` | Common period |
|---|---|---|
| `ratio<1>` (seconds) | `milli` | `milli` |
| `ratio<60>` (minutes) | `ratio<3600>` (hours) | `ratio<60>` |
| `ratio<1, 3>` | `ratio<1, 2>` | `ratio<1, 6>` |
| `ratio<1, 30>` (30 Hz frames) | `milli` | `ratio<1, 3000>` |

Note 2 also says that the representation type of the common type is intended to hold the converted values without truncation, but that is only the intent; the multiplication itself can still overflow. The common type of `nanoseconds` and `years` is `nanoseconds`, and converting 300 years to nanoseconds exceeds the range of a 64-bit integer (see [[time.duration]]).

¶3 The common type of two time_points of the same clock is the time_point on that clock whose duration is the common type of their durations. The standard provides no specialization for time_points of different clocks, which cannot be mixed anyway.

## is_clock ([time.traits.is.clock])

```cpp run title="is-clock.cpp" ok
#include <chrono>
using namespace std::chrono;

static_assert( is_clock_v<system_clock>);
static_assert( is_clock_v<steady_clock>);
static_assert( is_clock_v<file_clock>);
static_assert(!is_clock_v<local_t>);   // a pseudo-clock with no now()
static_assert(!is_clock_v<seconds>);

int main() {}
```

¶1 If `T` meets the *Cpp17Clock* requirements ([[time.clock.req]]), `is_clock<T>` derives from `true_type`, otherwise from `false_type`. The extent to which an implementation determines that a type does not meet the requirements is unspecified, but at minimum it checks that:

- ¶1.1 `T::rep`, `T::period`, `T::duration` and `T::time_point` are all valid and all denote types;
- ¶1.2 `T::is_steady` is well-formed as an unevaluated operand;
- ¶1.3 `T::now()` is well-formed as an unevaluated operand.

This is a syntactic check. It cannot verify that `now()` is really monotonic, or that `is_steady` is declared truthfully. Implementations may check more, but not less.

`local_t` is a pseudo-clock used to form `local_time`, representing a local time whose time zone has not yet been determined. It has no `now()`, so `is_clock_v<local_t>` is false.

¶2 A program that adds a specialization of `is_clock` has undefined behavior ({{ub}}). This matches the rule for most type traits in `<type_traits>` ([[meta.rqmts]]): the value of `is_clock` should truthfully reflect whether a type meets the requirements; types that meet them get `true` anyway without specialization, and allowing specialization would only let a type that is not a clock masquerade as one.

!!! impl "libc++ diagnoses such specializations"
    libc++ marks `is_clock` and `is_clock_v` with Clang's `[[clang::no_specializations]]` attribute. In our tests, `template<> struct std::chrono::is_clock<X> : std::true_type {};` gives the error `'is_clock' cannot be specialized`. The standard says only that it is UB; this is extra protection from the implementation.
