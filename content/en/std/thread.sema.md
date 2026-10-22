---
title: Semaphores
summary: "counting_semaphore and binary_semaphore: an ownerless counter, why release must not push the count above max(), the synchronization between a release and the acquire that observes it, and a try_acquire that may fail spuriously."
updated: 2026-10-19
---

!!! tldr
    - A semaphore is a non-negative counter: `acquire` decrements it and blocks while it is zero; `release` increments it. It has no owner; any thread may `release`.
    - `binary_semaphore` is just `counting_semaphore<1>`. Calling `release()` on a binary semaphore whose count is already 1 is UB; the count does not stay at 1.
    - `release` [[g:strongly-happens-before|strongly happens before]] the `try_acquire` that observes its result, so data written before `release` is visible to the acquirer.
    - `try_acquire` may fail spuriously even when the count is positive; `acquire` is a loop of `try_acquire` plus blocking.
    - Semaphores were added in C++20. Typical uses are one thread signalling another, and limiting how many threads access a resource at once.

## One thread signalling another

```cpp run title="semaphore-signal.cpp" ok
#include <cassert>
#include <semaphore>
#include <thread>

std::binary_semaphore ready{0};
int data = 0;

int main() {
  std::jthread t([] {
    ready.acquire();       // blocks until the count becomes positive
    assert(data == 1);     // writes made before release are visible here
  });
  data = 1;
  ready.release();         // released by a different thread
}
```

Doing the same with `std::mutex` is UB: `lock` in the main thread and `unlock` in `t` violates the precondition that only the thread owning the mutex may unlock it ([[thread.mutex.requirements]]). A semaphore has no owner, so it has no such restriction.

[thread.sema.general] ¶1 Semaphores are lightweight synchronization primitives used to constrain concurrent access to a shared resource. They are often used to implement other synchronization primitives, and where both apply they can be more efficient than condition variables: the count itself is the condition, no separate mutex is needed, and without contention `acquire` and `release` are each a single atomic operation.

¶2 A **counting semaphore** models a non-negative resource count. A **binary semaphore** has only two states. The standard recommends that a binary semaphore be more efficient than the default implementation of a counting semaphore with a count of 1, but this is only a recommendation.

## Types and the count limit [semaphore.syn] [thread.sema.cnt]

```cpp
template<ptrdiff_t least_max_value = implementation-defined>
  class counting_semaphore;
using binary_semaphore = counting_semaphore<1>;
```

[thread.sema.cnt] ¶1 A semaphore maintains an internal counter, initialized when it is created. The counter is decremented when a thread acquires the semaphore and incremented when a thread releases it. A thread that tries to acquire while the counter is zero blocks until another thread releases.

¶2 `least_max_value` must be non-negative, otherwise the program is ill-formed. The default value is implementation-defined {{impl}}.

¶4 `max()` returns the maximum value of the counter, which is at least `least_max_value`. The template argument is only a lower bound; the implementation may support larger values. ¶5 The constructor's precondition is `0 <= desired <= max()`.

¶3 Concurrent calls to member functions other than the destructor do not introduce data races. The specific synchronization relationship is specified separately under `release`.

## release [thread.sema.cnt]

```cpp
void release(ptrdiff_t update = 1);
```

¶9 Atomically performs `counter += update`, then unblocks the threads waiting for the counter to become positive.

¶8 Preconditions: `update >= 0` and `update <= max() - counter`. In other words, the counter must not exceed `max()` after the release. For `binary_semaphore`, calling `release()` when the counter is already 1 violates this {{ub}}. Signalling twice is not a harmless no-op on a binary semaphore.

```cpp title="binary-overflow.cpp" ub
#include <cstdio>
#include <semaphore>
int main() {
  std::binary_semaphore s{1};
  s.release();                          // UB: the counter would become 2, exceeding max() == 1
  std::printf("max=%td try1=%d try2=%d\n", s.max(), s.try_acquire(), s.try_acquire());
}
```

!!! impl "libc++ does not check this precondition"
    With libc++ this program prints `max=1 try1=1 try2=1`: the binary semaphore was acquired twice, so the counter really did become 2. The result is the same when compiled with `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_DEBUG`, because libc++'s assertion checks against the maximum of `ptrdiff_t`, not against `max()`. In libc++, `binary_semaphore` and the default `counting_semaphore` share one implementation.

¶10 `release` strongly happens before the `try_acquire` calls that observe its result. Strongly happens before is a stronger relation than ordinary happens before ([[intro.races#8]]); it also constrains the total order of seq_cst operations. For a program that passes data only through the semaphore, the effect is that writes made before `release` are visible to the acquirer that observes that `release`.

¶11–¶12 Throws `system_error` when required, with the same error conditions as for mutexes.

## acquire and try_acquire

```cpp
bool try_acquire() noexcept;
void acquire();
```

¶13 `try_acquire` attempts to atomically decrement the counter, without blocking, if it is positive. If it does not decrement, it has no effect and returns immediately. The implementation may fail to decrement even when the counter is positive. Note 1 says this spurious failure is normally uncommon and allows an implementation based on a simple compare-and-exchange. The standard recommends that implementations ensure `try_acquire` does not consistently return `false` in the absence of contention. ¶14 Returns `true` if it decremented the counter.

¶15 `acquire` repeatedly performs two steps: evaluate `try_acquire()` and return if it is true; otherwise block until the counter is positive. Because `acquire` is defined in terms of `try_acquire`, the synchronization rule of ¶10 covers it as well: when `acquire` returns, some `try_acquire` inside it observed the result of some `release`.

¶18 `try_acquire_for(rel_time)` and `try_acquire_until(abs_time)` are loops too: return `true` if `try_acquire()` succeeds; otherwise block until the counter is positive or the timeout expires, and return `false` if woken by the timeout. For `try_acquire_for`, the timeout means at least `rel_time` has passed since the start of the function.

## Limiting concurrency

```cpp run title="semaphore-limit.cpp" ok
#include <atomic>
#include <cassert>
#include <semaphore>
#include <thread>
#include <vector>

std::counting_semaphore<3> slots{3};       // at most 3 threads inside at once
std::atomic<int> inside{0}, peak{0};

void work() {
  slots.acquire();
  int now = ++inside;
  int p = peak.load();
  while (now > p && !peak.compare_exchange_weak(p, now)) {}
  --inside;
  slots.release();
}

int main() {
  {
    std::vector<std::jthread> ts;
    for (int i = 0; i < 16; ++i) ts.emplace_back(work);
  }
  assert(peak.load() <= 3);
}
```

!!! impl "counting_semaphore in libc++"
    A libc++ semaphore contains only one `atomic<ptrdiff_t>`; `max()` returns the template argument directly, and the default is `PTRDIFF_MAX`.

    - `release(n)` is `fetch_add(n, release)`, and calls `notify_all()` only when the old value was 0, that is, when threads may be waiting.
    - `try_acquire()` first does a relaxed read of the current value and fails if it is 0; otherwise it loops on `compare_exchange_weak(old, old - 1, acquire, relaxed)`, retrying with the new value when the CAS fails because of contention.
    - `acquire()` uses the waiting mechanism of [[atomics.wait]] and waits until the CAS succeeds.

    The release write in `release` pairs with the acquire read of a successful CAS to form synchronization ([[atomics.order#2]]), which satisfies the requirement of paragraph 10.

## Common misconceptions

!!! pitfall "A binary semaphore can be used as a flag that may be set repeatedly"
    Calling `release()` on a `binary_semaphore` that is already 1 is UB (¶8); the count does not saturate at 1. To set a flag idempotently and wake waiters, use `atomic<bool>` with `wait`/`notify` ([[atomics.wait]]), or a condition variable.

!!! pitfall "A semaphore can directly replace a mutex"
    A semaphore initialized to 1 can provide mutual exclusion, but because it has no owner, the implementation cannot do priority inheritance, nor detect a forgotten release or the release of a resource held by someone else. Using it as a mutex means accepting these costs.

## Summary

- A semaphore has no owner; any thread may `release`.
- `max()` is at least `least_max_value`; a `release` that pushes the counter above `max()` is UB, especially relevant for binary semaphores.
- `release` strongly happens before the `try_acquire` that observes its result, and so this also covers `acquire`.
- `try_acquire` may fail spuriously; `acquire` is a loop of it plus blocking.
