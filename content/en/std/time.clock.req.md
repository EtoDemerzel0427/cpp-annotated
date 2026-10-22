---
title: Cpp17Clock requirements
summary: "To be a clock, a type must provide rep, period, duration, time_point, is_steady and now(); is_steady requires being monotonically non-decreasing with a constant tick interval; Cpp17TrivialClock additionally requires the related operations not to throw, which the thread library's timeout functions depend on."
updated: 2026-10-19
---

!!! tldr
    - A clock is a type: a few member types, an `is_steady` constant and a static `now()`. Standard clocks never need an object to be created.
    - `is_steady` being true requires two conditions: an earlier `now()` is not greater than a later one, and the tick interval is constant. A clock that NTP speeds up and slows down is not steady even if it never jumps back.
    - How far a clock's second differs from a real second is a quality-of-implementation issue; the standard makes no guarantee.
    - *Cpp17TrivialClock* additionally requires that `now()` and operations on the related types do not throw; the clocks the standard library provides for timeout functions all meet it.
    - Use `steady_clock` for performance measurement, and do not assume `high_resolution_clock` is steady.

## Writing your own clock

```cpp run title="frame-clock.cpp" ok
#include <chrono>
#include <cstdint>

// a game clock counting in frames (for demonstration: now() returns a fixed value)
struct frame_clock {
  using rep        = std::int64_t;
  using period     = std::ratio<1, 60>;   // 60 Hz
  using duration   = std::chrono::duration<rep, period>;
  using time_point = std::chrono::time_point<frame_clock>;
  static constexpr bool is_steady = true;
  static time_point now() noexcept {
    return time_point{duration{42}};
  }
};

static_assert(std::chrono::is_clock_v<frame_clock>);
static_assert(frame_clock::is_steady);   // usable in a constant expression

int main() {
  auto t = frame_clock::now().time_since_epoch();
  auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(t);
  return ms.count() == 700 ? 0 : 1;      // 42 frames = 700 ms
}
```

[time.clock.req] is a table of named requirements, of the same kind as *Cpp17Allocator* and *Cpp17Hash*. Wherever the standard says "`Clock` meets the *Cpp17Clock* requirements", it means this table. A type meeting it can be used wherever a clock is needed, such as in `time_point`; if it also meets *Cpp17TrivialClock*, it can be used with the thread library's `_until` functions too. The standard's own clocks are in [[time.clock]].

## What a clock is (¶1)

¶1 A clock is a bundle of a duration, a time_point, and a function `now()` returning the current time_point. The origin of a clock's time_point is called the clock's epoch ([[g:clock-epoch]]).

The definition does not say a clock is an object. The standard clocks are all classes with only static members, written `system_clock::now()`. The clock type acts as a tag in `time_point<Clock, Duration>`: it makes `sys_time` and `steady_clock::time_point` different types, thereby forbidding the subtraction of two instants measured from different origins.

## The requirements table (¶2, Table 131)

¶2 First, notation: `C1` and `C2` are clock types; `t1` and `t2` are values returned by `C1::now()`, where the call returning `t1` happens before ([[intro.multithread]]) the call returning `t2`, and both calls occur before the clock reaches `C1::time_point::max()`. Note 1 says this last condition excludes the clock wrapping around between the two calls.

| Expression | Type | Semantics |
|---|---|---|
| `C1::rep` | an arithmetic type, or a class emulating an arithmetic type | the representation type of `C1::duration` |
| `C1::period` | a specialization of `ratio` | the tick period, in seconds |
| `C1::duration` | `duration<C1::rep, C1::period>` | |
| `C1::time_point` | `time_point<C1>` or `time_point<C2, C1::duration>` | in the latter case, `C1` and `C2` must have the same epoch |
| `C1::is_steady` | `const bool` | `true` if `t1 <= t2` always holds and the tick interval is constant; must be usable in constant expressions |
| `C1::now()` | `C1::time_point` | returns a time_point representing the current instant |

### Happens before, not "earlier in time"

Steadiness is defined in terms of the multithreaded memory model. If thread A's `now()` happens before thread B's `now()` (for example, with a release/acquire synchronization between them), a steady clock guarantees that the value B reads is not less than the one A read. For two threads without a synchronization relationship each calling `now()`, the standard makes no promise about the relative size of the two results.

### The two conditions of is_steady

Monotonically non-decreasing and a constant tick interval: both conditions are required. Some clocks are gradually adjusted (slewed) by NTP: rather than jumping back, they temporarily run each second a little fast or slow. Such a clock meets the first condition but not the second, so it is not steady.

`is_steady` must be usable in constant expressions ([[expr.const]]), so you can write `static_assert(Clock::is_steady)` or `if constexpr (Clock::is_steady)`. Merely declaring a `static const bool` in the class and initializing it outside the class with a non-constant expression does not meet this requirement.

### Borrowing another clock's time_point

The option `time_point<C2, C1::duration>` lets a clock use the time_point type of another clock with the same epoch. The standard writes `steady_clock::time_point` as `time_point<unspecified, duration>`, which leaves implementations exactly this room.

¶3 Note 2 says the relative difference between the durations a clock reports and the SI second is a measure of quality of implementation. In other words, the standard does not guarantee that a second of `steady_clock` really is a second, only that it does not jump back and has a constant step.

## Cpp17TrivialClock (¶4)

¶4 A type `TC` meets the *Cpp17TrivialClock* requirements ([[g:trivial-clock]]) if all of the following hold:

- ¶4.1 it meets the *Cpp17Clock* requirements;
- ¶4.2 `TC::rep`, `TC::duration` and `TC::time_point` meet the *Cpp17EqualityComparable*, *Cpp17LessThanComparable* and *Cpp17Swappable* requirements and the requirements for numeric types ([[numeric.requirements]]). Note 3 points out that this means operations on these types do not throw;
- ¶4.3 `TC::now()` does not throw;
- ¶4.4 `TC::time_point::clock` also meets the *Cpp17TrivialClock* requirements.

The thread library's waiting functions, such as `this_thread::sleep_until`, `condition_variable::wait_until` and `timed_mutex::try_lock_until`, call `now()` repeatedly and do time arithmetic internally. [[thread.req.timing]] paragraph 7 specifies that the clocks implementations provide for these functions meet the *Cpp17TrivialClock* requirements; paragraph 8 specifies that if a user-provided clock, time_point or duration throws during the wait, the waiting function throws it out; such exceptions are called timeout-related exceptions.

[[time.clock.general]] ¶1 specifies that the clocks defined in this clause all meet *Cpp17TrivialClock* by default. The exceptions are `utc_clock`, `tai_clock` and `gps_clock`: their `now()` may need to read leap second data, and they are trivial clocks only if the implementation can guarantee not to propagate exceptions.

## Common misconceptions

!!! pitfall "`is_clock_v` being true means the clock is written correctly"
    [[time.traits|is_clock]] only checks that those few names exist and that `now()` can be called; it cannot verify that `is_steady` is declared truthfully. The `frame_clock` at the top returns the same value every time, and `is_clock_v` is still true. `is_steady` is the clock author's promise, and if it is wrong the standard library cannot detect it.

!!! pitfall "`high_resolution_clock` is always steady"
    [[time.clock]] says only that it is the clock with the shortest tick period; it may be an alias of `system_clock` or `steady_clock`, and the value of `is_steady` is unspecified. On libc++ it is an alias of `steady_clock`; on other implementations it may be `system_clock`. For measuring elapsed time, use `steady_clock` directly, or at least write `static_assert(clock::is_steady)`.

!!! pitfall "If `now()` is not `noexcept`, it will throw"
    `utc_clock::now()` is not marked `noexcept`, which only means an implementation may throw (for example, if loading leap second data fails), not that any given call will throw. But precisely because it may throw, you cannot assume it meets *Cpp17TrivialClock*.
