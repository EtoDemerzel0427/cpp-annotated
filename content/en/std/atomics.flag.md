---
title: Flag type and operations
summary: "The atomic boolean flag guaranteed lock-free on every implementation: the memory order requirements of test_and_set, clear and test, C++20's default construction and ATOMIC_FLAG_INIT, and writing a spin lock that does not burn CPU with it and wait/notify."
updated: 2026-10-19
---

!!! tldr
    - `atomic_flag` has only two states, set and clear. Its operations must be lock-free, including in freestanding implementations, a guarantee no other atomic type gets.
    - `test_and_set` is an atomic read-modify-write operation: when two threads call it on a clear flag at the same time, exactly one gets `false`, which is the primitive for acquiring a lock.
    - `clear` is a store, so its memory order cannot be `acquire` or `acq_rel`; `test` and `wait` are loads and cannot use `release` or `acq_rel`.
    - Since C++20, default construction gives the clear state and `ATOMIC_FLAG_INIT` is kept only for compatibility; `test`, `wait`, `notify_one` and `notify_all` were added at the same time.

## Writing a lock with atomic_flag

```cpp run title="flag-spinlock.cpp" ok
#include <atomic>
#include <cassert>
#include <mutex>
#include <thread>
#include <vector>

class spinlock {
  std::atomic_flag f;   // C++20: default-constructed in the clear state
public:
  void lock() noexcept {
    while (f.test_and_set(std::memory_order::acquire))
      f.wait(true, std::memory_order::relaxed);
  }
  bool try_lock() noexcept {
    return !f.test_and_set(std::memory_order::acquire);
  }
  void unlock() noexcept {
    f.clear(std::memory_order::release);
    f.notify_one();     // modify first, then notify
  }
};

int main() {
  spinlock sl;
  long counter = 0;
  {
    std::vector<std::jthread> ts;
    for (int i = 0; i < 4; ++i)
      ts.emplace_back([&] {
        for (int k = 0; k < 100000; ++k) {
          std::lock_guard g(sl);
          ++counter;
        }
      });
  }
  assert(counter == 400000);
}
```

`spinlock` meets *Cpp17Lockable* ([[thread.req]]), so it works with `lock_guard`. ThreadSanitizer reports nothing. Going through the memory orders one by one:

- When `test_and_set(acquire)` returns `false`, the lock is acquired. It reads the value written by the previous `clear(release)`, and the two synchronize ([[atomics.order#2]]), so the previous holder's writes in the critical section are visible.
- `wait(true, relaxed)` is used only to wait for the flag to change and needs no synchronization; after waking, another acquire `test_and_set` is executed anyway.
- `clear(release)` is followed by `notify_one()`; the modification happens before the notification, satisfying ¶4 of [[atomics.wait]], so no wakeup is lost.

Without contention, locking takes a single atomic read-modify-write. Under contention, waiters block via `wait` (libc++ first spins for about 4 microseconds) instead of spinning forever. But this lock is not fair: a thread woken by `notify_one` may be beaten to it by a newly arriving thread. When fairness is needed, use `std::mutex`.

## Properties (¶1–¶4)

¶1 `atomic_flag` provides the classic test-and-set functionality and has two states: **set** and **clear**.

¶2 Operations on an `atomic_flag` must be lock-free, and should also be address-free ([[atomics.lockfree]]). [[intro.progress#2]] counts executions defined to be lock-free (i.e. the operations of `atomic_flag`) as lock-free executions, with the corresponding progress guarantees.

Whether other atomic types are lock-free is up to the implementation. In hosted implementations, `atomic_signed_lock_free` and `atomic_unsigned_lock_free` are also guaranteed lock-free, but they are optional in freestanding implementations ([[atomics.alias]]). So on any platform, an implementation can build other things out of `atomic_flag`, including a non-lock-free `atomic<T>` implemented with locks.

¶3 `atomic_flag` is a standard-layout struct with a trivial destructor.

¶4 The default constructor initializes it to the clear state. This is a C++20 change: in C++11/17 a default-constructed `atomic_flag` had an unspecified state, and you had to write `atomic_flag f = ATOMIC_FLAG_INIT;`.

## Operations (¶5–¶20)

Each operation has a `volatile` overload and a non-`volatile` `constexpr` overload, plus non-member versions for C compatibility: `atomic_flag_test`, `atomic_flag_test_and_set(_explicit)`, `atomic_flag_clear(_explicit)`, `atomic_flag_wait(_explicit)`, `atomic_flag_notify_one/all`. The non-member versions without `_explicit` use `seq_cst` (¶5, ¶13).

| Operation | Paragraphs | Memory order precondition | Effect |
|---|---|---|---|
| `test(order)` {{c++20}} | ¶5–¶8 | `relaxed`, `acquire`, `seq_cst` | atomically returns the current value without modifying it |
| `test_and_set(order)` | ¶9–¶10 | any | atomically sets it to `true` and returns the previous value; an atomic read-modify-write operation |
| `clear(order)` | ¶11–¶12 | `relaxed`, `release`, `seq_cst` | atomically sets it to `false` |
| `wait(old, order)` {{c++20}} | ¶13–¶16 | `relaxed`, `acquire`, `seq_cst` | repeatedly checks `test(order) != old`, returning if true, otherwise blocking until notified or spuriously woken |
| `notify_one()`, `notify_all()` {{c++20}} | ¶17–¶20 | none | unblock eligible waiting operations ([[atomics.wait]]) |

`test_and_set` is a read-modify-write and always reads the value immediately preceding it in the modification order ([[atomics.order#11]]), so when two threads call it on a clear flag at the same time, exactly one gets `false`.

`test()` was added only in C++20. Before that, just peeking at the state without modifying it was impossible; you had to `test_and_set` and then `clear` if appropriate, causing unnecessary writes to the cache line.

Violating a memory order precondition is UB. The easiest one to get wrong is `clear(acquire)`: `clear` is a store and accepts only `relaxed`, `release` and `seq_cst`.

## ATOMIC_FLAG_INIT (¶21)

¶21 The macro `ATOMIC_FLAG_INIT` can initialize an `atomic_flag` to the clear state, used as `atomic_flag guard = ATOMIC_FLAG_INIT;`. Whether it can be used in other initialization contexts is unspecified. For a complete object with static storage duration, this initialization shall be static.

Since C++20 default construction already gives the clear state and is `constexpr`, so `atomic_flag guard;` is enough; the macro is kept only for compatibility with C and old code.

## The implementation's view

!!! impl "atomic_flag in libc++"
    Internally, libc++'s `atomic_flag` is a `__cxx_atomic_impl<bool>` of size 1 byte, and `test_and_set` is implemented with `exchange(true)`. It also provides a non-standard constructor `atomic_flag(bool)`. Because its size is 1 byte, `wait`/`notify` go through the global wait table described in [[atomics.wait]] instead of waiting directly on the flag's address.

## Common misconceptions

!!! pitfall "A pure spin lock is fine"
    A lock that spins purely with `while (f.test_and_set(acquire)) {}` makes waiters burn their time slices for nothing when the holder is preempted; if a waiter has higher priority, the holder may never get scheduled (priority inversion). In user-space code, at least combine it with `wait` as in the example above, or just use `std::mutex`.
