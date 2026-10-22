---
title: General requirements of the concurrency library
summary: "Conventions shared by every subclause of chapter 32: requirements on Predicate and Clock parameters, how system_error reports errors, native_handle, the semantics of _for and _until timeouts, and the lockable type requirements such as Cpp17BasicLockable."
updated: 2026-10-19
---

!!! tldr
    - `wait_for(5s)` is a relative timeout and should be measured with a steady clock; `wait_until(tp)` is an absolute timeout and follows `tp`'s own clock. When the system time is adjusted, the two behave differently.
    - Timeout functions guarantee only that they do not return early, not that they return on time.
    - When you need an overall deadline, compute a `steady_clock` time point first and use `wait_until`; do not repeat `wait_for` in a loop.
    - The lockable type requirements (*Cpp17BasicLockable* and so on) specify only the interface and blocking semantics, not memory synchronization. Synchronization depends on the lock type's own implementation.
    - The `code()` of a `system_error` compares equal to the error condition listed for the function; do not compare `code().value()` with an integer.

The subclauses of chapter 32 (the concurrency support library) refer back to these conventions over and over, as in "timeouts are handled per [thread.req.timing]" or "Mutex shall meet *Cpp17BasicLockable*".

## Timeouts: _for and _until [thread.req.timing]

### Two kinds of timeout

```cpp run title="deadline.cpp" ok
#include <chrono>
#include <condition_variable>
#include <mutex>

std::mutex m;
std::condition_variable cv;
bool ready = false;

bool wait_with_deadline() {
  using namespace std::chrono_literals;
  // the deadline is computed once and never moves, however many times we wake up
  auto deadline = std::chrono::steady_clock::now() + 100ms;
  std::unique_lock lk(m);
  return cv.wait_until(lk, deadline, [] { return ready; });   // returns false on timeout
}

int main() { return wait_with_deadline() ? 1 : 0; }
```

This chapter has many paired functions: `sleep_for` and `sleep_until`, `try_lock_for` and `try_lock_until`, `wait_for` and `wait_until`. ¶1 Timeouts are specified with a `duration` or a `time_point` ([[time]]).

¶3 Functions whose names end in `_for` take a duration and produce a **relative timeout**. Implementations should measure it with a **steady clock** (a clock that is never adjusted and only moves forward at a steady rate).

¶4 Functions whose names end in `_until` take a time point and produce an **absolute timeout**. Implementations should measure it with the clock the time point belongs to.

So `wait_for(1h)` means "wait an hour of physical time", while `wait_until(system_clock::now() + 1h)` means "wait until the wall clock (`system_clock`, which may be adjusted by NTP or an administrator) shows that moment". A scheduled task that runs at 9 o'clock every day uses `_until` with `system_clock`; "give up if there is no response within 5 seconds" uses `_for`, or `_until` with `steady_clock`.

### Only guaranteed not to be early

¶2 Returning from a timeout always involves some delay. The standard splits the delay into two parts: the **quality of implementation delay** D<sub>i</sub> from interrupt response, function return and scheduling, and the **quality of management delay** D<sub>m</sub> from contention for processors and memory. Both may differ from one timeout to the next, and shorter is better.

¶3 Given a duration D<sub>t</sub>, the real-time duration of a relative timeout is D<sub>t</sub>+D<sub>i</sub>+D<sub>m</sub>. ¶4 Given a time point C<sub>t</sub>, if the clock is not adjusted, an absolute timeout should return at C<sub>t</sub>+D<sub>i</sub>+D<sub>m</sub>. These formulas show that the standard never promises punctuality, only that the function will not return before the timeout.

### The clock is adjusted during the wait (¶4)

¶4 If, during an absolute-timeout wait, the clock is adjusted to C<sub>a</sub>:

- ¶4.1 C<sub>a</sub> > C<sub>t</sub>, the clock was moved past the deadline: the timeout has been met and the function should return as soon as possible. Measured by a steady clock, the total wait got shorter.
- ¶4.2 C<sub>a</sub> ≤ C<sub>t</sub>: the function should not time out until `Clock::now()` returns a value not less than C<sub>t</sub>. Note 1 points out that setting the clock back makes the wait (measured by a steady clock) longer.

The paragraph closes by leaving implementations some room: an implementation may return at any point between the time specified above and the time it would return from a steady-clock relative timeout on the difference between C<sub>t</sub> and the time of the call. The *recommended practice* is to shorten the wait when the clock is moved forward.

¶5 Note 2: if the clock is not synchronized with a steady clock, such as a CPU time clock, these timeouts might not provide useful functionality.

!!! pitfall "Repeating `wait_for` in a loop lets the deadline drift"
    `while (!ready) cv.wait_for(lk, 100ms);` restarts the 100ms every time it wakes up (including spurious wakeups), so the total wait has no upper bound. When you need an overall timeout, compute a `steady_clock` time point first as in the example above, then use `wait_until`.

The standard follows ¶3 itself when defining condition variables: [[thread.condition.general]] uses the exposition-only function *rel-to-abs* to convert a relative duration into a `steady_clock` time point, and `wait_for` is equivalent to `wait_until` on that time point.

!!! impl "`condition_variable::wait_for` in libc++ on macOS"
    libc++ uses `pthread_cond_clockwait(CLOCK_MONOTONIC)` only on glibc ≥ 2.30 or Android API ≥ 30. macOS lacks that function, so libc++ adds the duration to `system_clock::now()` and hands it to `pthread_cond_timedwait`, then after return measures the actually elapsed time with `steady_clock` to decide between returning `timeout` and `no_timeout` (see `<__condition_variable/condition_variable.h>`). The underlying wait is still based on the wall clock, so the recommendation in ¶3 is only partly met here.

### Resolution and timeout-related exceptions (¶6–¶8)

¶6 The finest timing resolution an implementation can provide is called the **native resolution** ([[g:native-resolution]]); it depends on the operating system and hardware.

¶7 The implementation-provided clocks used by these functions meet *Cpp17TrivialClock* ([[time.clock.req]]), meaning `now()` and operations on the time types do not throw.

¶8 A function taking a timeout argument throws to its caller any exception thrown by a clock, time point or duration during its execution. Such exceptions are called **timeout-related exceptions** ([[g:timeout-related-exception]]). Note 3 explains that none of the standard library's own time types throw; only user-defined clocks or `rep` types (for example, integer types with overflow checking) can. So the "*Throws*: Timeout-related exceptions" that appears so often in this chapter can be read as: the function itself throws nothing, and only forwards exceptions thrown by user-provided time types.

## Template parameter names [thread.req.paramname]

¶1 This chapter expresses type requirements through template parameter names:

- A parameter named `Predicate` is a function object type. With `pred` an lvalue of it, `pred()` must be well-formed and its result type must model *boolean-testable* ([[concept.booleantestable]]). The result, converted to `bool`, says whether the condition being waited for is satisfied, as with the `pred` in `condition_variable::wait(lock, pred)`.
- For a parameter named `Clock`, the argument type `C` must meet *Cpp17Clock* ([[time.clock.req]]); if `is_clock_v<C>` is `false`, the program is ill-formed.

Meeting *Cpp17Clock* is itself a semantic requirement that the compiler cannot fully check. `is_clock_v` checks the statically checkable part: whether the members `rep`, `period`, `duration`, `time_point`, `is_steady` and `now()` exist. The standard upgrades that part into an error that must be diagnosed.

```cpp run title="not-a-clock.cpp" error
#include <chrono>
#include <thread>
struct almost_clock {             // lacks is_steady, so is_clock_v is false
  using rep = long long;
  using period = std::nano;
  using duration = std::chrono::nanoseconds;
  using time_point = std::chrono::time_point<almost_clock>;
  static time_point now() { return time_point{}; }
};
static_assert(!std::chrono::is_clock_v<almost_clock>);
int main() {
  std::this_thread::sleep_until(almost_clock::now());   // error: almost_clock is not a clock
}
```

!!! impl "libc++ does not diagnose this"
    By ¶1 this program is ill-formed and must be diagnosed. Yet Clang 23 + libc++ compiles it, because the implementation of `sleep_until` uses only `Clock::now()` and `time_point` arithmetic and never checks `is_clock_v`. This is a conformance defect in libc++.

## Error reporting [thread.req.exception]

```cpp run title="join-empty.cpp" ok
#include <cstdio>
#include <system_error>
#include <thread>

int main() {
  std::thread t;       // represents no thread
  try {
    t.join();          // error condition: invalid_argument
  } catch (const std::system_error& e) {
    std::printf("%d\n", e.code() == std::errc::invalid_argument);   // 1
  }
}
```

¶1 Some functions in this chapter are specified to throw `system_error`. They throw in two situations: when an error condition listed in the function's *Error conditions* element is detected, or when an underlying operating system API fails in a way that prevents the function from meeting its specification. Failure to allocate memory is reported separately per [[res.on.exception.handling]], usually as `bad_alloc`.

Example 1 describes the mapping: a POSIX call returns `EPERM` (the caller lacks permission), the implementation maps it to the error condition `operation_not_permitted`, and then throws `system_error`.

¶2 For exceptions thrown this way, `code()` compares equal to one of the error conditions listed for the function. This is a comparison between an `error_code` and an `error_condition` ([[syserr]]); the same condition can correspond to different native error codes on different platforms, so compare with `std::errc` as in the example above.

## native_handle [thread.req.native]

¶1 Classes such as `thread`, `mutex` and `condition_variable` may have the members `native_handle_type` and `native_handle()`; whether they exist and what they mean are implementation-defined. Note 1 explains why the standard still specifies these names: so that their presence can be detected portably at compile time, for example with `requires { m.native_handle(); }`, even though using them is not portable.

With libc++ on macOS, `std::thread::native_handle()` returns a `pthread_t` and `std::mutex::native_handle()` returns a `pthread_mutex_t*`. Typical uses are setting thread priority, CPU affinity and other attributes the standard interface does not cover.

## Lockable type requirements [thread.req.lockable]

### Execution agents (¶1–¶2)

¶1 An **execution agent** ([[g:execution-agent]]) is an entity such as a thread that may perform work in parallel with other execution agents. Note 1 adds that implementations or users may introduce other kinds of agents, such as processes or thread-pool tasks. The calling agent is determined by context, e.g. the calling thread that contains the call.

The lockable requirements are phrased in terms of execution agents rather than threads so as not to tie locks to operating system threads. ¶2 Note 2 gives an example: an ordinary spin lock that does not record who holds it works with any execution agent model; such locks are called agent oblivious.

### The requirements cover the interface, not synchronization (¶3–¶4)

¶3 `unique_lock`, `shared_lock`, `scoped_lock`, `lock_guard`, `std::lock`, `std::try_lock` and `condition_variable_any` can all operate on user-supplied lockable objects. The five sets of requirements below list the interface these components need to acquire and release locks.

Note 3 points out that the nature of lock ownership, and any synchronization it may entail, are not part of these requirements. So `std::lock_guard<MyLock>` by itself guarantees no memory visibility; whether it synchronizes depends entirely on the implementation of `MyLock`.

¶4 Locks on an object `m` are of two kinds according to how they are acquired: a lock obtained through `lock`, `try_lock`, `try_lock_for` or `try_lock_until` is a **non-shared lock**; one obtained through `lock_shared` or the other `_shared` functions is a **shared lock**. Note 4 stresses that only the way of acquisition matters. Even if some type's `lock()` lets several agents hold it at once (such as `rcu_domain` in [[saferecl]]), what it acquires is still called a non-shared lock.

### The five sets of requirements

| Requirement | Expressions needed | Key points |
|---|---|---|
| *Cpp17BasicLockable* [thread.req.lockable.basic] | `m.lock()`, `m.unlock()` | `lock` blocks until the lock is acquired; `unlock` requires the current agent to hold a non-shared lock, and throws nothing |
| *Cpp17Lockable* [thread.req.lockable.req] | plus `m.try_lock()` | attempts without blocking; the return type is `bool` |
| *Cpp17TimedLockable* [thread.req.lockable.timed] | plus `try_lock_for`, `try_lock_until` | attempts until the timeout; does not return before the timeout unless the lock was acquired |
| *Cpp17SharedLockable* [thread.req.lockable.shared] | `lock_shared`, `try_lock_shared`, `unlock_shared` | the shared versions; the type of `try_lock_shared()` is `bool` |
| *Cpp17SharedTimedLockable* [thread.req.lockable.shared.timed] | plus `try_lock_shared_for`, `try_lock_shared_until` | the shared versions with timeouts, returning `bool` |

A few details:

- *Cpp17BasicLockable* ¶2 specifies that if `lock()` throws, the lock was not acquired. So when `lock()` throws in the constructor of `lock_guard`, the destructor does not run, and need not.
- *Cpp17BasicLockable* ¶3 requires the agent calling `unlock` to be the agent holding the lock. Calling `lock()` on a `std::mutex` in thread A and `unlock()` in thread B violates the precondition and is UB.
- *Cpp17TimedLockable* ¶2 says only that the function does not return within the timeout unless the lock was acquired; it does not say the lock must be acquired if it is free. So even if the lock stays free throughout, `try_lock_for` returning `false` conforms to these requirements. The additional guarantees of the concrete mutex types are in [[thread.mutex.requirements]].

### Writing a type that meets Cpp17Lockable

```cpp run title="spinlock.cpp" ok
#include <atomic>
#include <cassert>
#include <mutex>
#include <thread>

class spinlock {                       // meets Cpp17Lockable
  std::atomic<bool> held{false};
public:
  void lock() noexcept {
    while (held.exchange(true, std::memory_order::acquire))
      while (held.load(std::memory_order::relaxed)) {}   // read-only spin, less cache-line contention
  }
  bool try_lock() noexcept {
    return !held.load(std::memory_order::relaxed) &&
           !held.exchange(true, std::memory_order::acquire);
  }
  void unlock() noexcept { held.store(false, std::memory_order::release); }
};

spinlock a, b;
long x = 0, y = 0;

int main() {
  std::thread t1([] { for (int i = 0; i < 10000; ++i) { std::scoped_lock lk(a, b); ++x; ++y; } });
  std::thread t2([] { for (int i = 0; i < 10000; ++i) { std::scoped_lock lk(b, a); ++x; ++y; } });
  t1.join(); t2.join();
  assert(x == 20000 && y == 20000);
}
```

`std::scoped_lock` requires *Cpp17Lockable* when locking several objects at once; it needs `try_lock` to implement its deadlock-avoidance algorithm ([[thread.lock]]). Even though the two threads pass `a` and `b` in opposite orders, there is no deadlock.

There is no data race on `x` and `y`, but the reason is not `scoped_lock`; it is the implementation of `spinlock`: the release store in `unlock` synchronizes with the acquire `exchange` in the next `lock` that reads `false` ([[atomics.order#2]]). Change the memory order of `unlock` to `relaxed`, and this program has a data race. Conversely, a type whose `lock()` and `unlock()` are both empty functions also meets *Cpp17Lockable*, yet protects nothing. The synchronization guarantees of the standard mutex types are written in the *Synchronization* elements of [[thread.mutex.requirements]].

!!! tip "When one thread acquires and another releases"
    `std::binary_semaphore` ([[thread.sema]]) has no notion of an owner; it can be `acquire`d in one thread and `release`d in another.

## Questions

!!! question "1. Does `try_lock_for(0s)` block?"

<details markdown="1">
<summary>Answer</summary>

This subclause says only that the function does not return within the timeout unless the lock was acquired, which has no force when the timeout is zero. The concrete mutex types fill this in in [[thread.mutex.requirements]]: if `rel_time` is not greater than zero, the function attempts to obtain ownership without blocking, as if by calling `try_lock()`. For a user-defined *Cpp17TimedLockable* type, it depends on that type's own specification.
</details>

!!! question "2. What happens if a user-defined `rep` throws inside `sleep_for`?"

<details markdown="1">
<summary>Answer</summary>

It is a timeout-related exception (¶8), and `sleep_for` throws it to its caller ([[thread.thread.this#9]]). The standard does not say how long the thread had slept when the exception occurred.
</details>
