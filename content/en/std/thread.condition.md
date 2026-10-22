---
title: Condition variables
summary: "How condition_variable and condition_variable_any let a thread wait until a condition holds: why the three atomic parts of wait prevent lost wakeups, spurious wakeups and the predicate loop, why waiters on one condition variable must use the same mutex, the return value of timed waits, and C++20 waits that a stop request can interrupt."
updated: 2026-10-19
---

!!! tldr
    - `wait` atomically releases the mutex and starts waiting, so as long as the condition is modified while holding the same mutex, notifications are not lost. Even if the condition is an atomic variable, modify it under the lock.
    - `wait` may return without any notification (a spurious wakeup), so the condition must be checked in a loop. The predicate overload `wait(lock, pred)` is that loop.
    - Threads waiting concurrently on one `condition_variable` must use the same mutex, otherwise it is UB; `condition_variable_any` has no such restriction and works with any lock type.
    - A timed wait with a predicate returns the final value of the predicate: `false` means it timed out, but `true` does not mean it did not.
    - The predicate waits of `condition_variable_any` can take a `stop_token` and wake immediately on a stop request.

## Waiting for a condition to hold

```cpp run title="cv-queue.cpp" ok
#include <condition_variable>
#include <cstdio>
#include <mutex>
#include <queue>
#include <thread>

std::mutex m;
std::condition_variable cv;
std::queue<int> q;
bool closed = false;

void producer() {
  for (int i = 0; i < 5; ++i) {
    {
      std::lock_guard lk(m);
      q.push(i);                     // hold the lock while modifying the condition
    }
    cv.notify_one();                 // notification may be outside the lock
  }
  {
    std::lock_guard lk(m);
    closed = true;
  }
  cv.notify_all();
}

void consumer() {
  std::unique_lock lk(m);
  while (true) {
    cv.wait(lk, [] { return !q.empty() || closed; });
    if (q.empty()) break;            // closed and the queue is empty
    int x = q.front(); q.pop();
    lk.unlock();
    std::printf("consumed %d\n", x);
    lk.lock();
  }
}

int main() {
  std::jthread c(consumer), p(producer);
}
```

Without a condition variable, the consumer could only lock, check the queue and unlock over and over, wasting CPU. A condition variable lets it sleep while the condition does not hold, and the thread that modifies the condition is responsible for waking it.

[thread.condition.general] ¶1 The standard provides two condition variables. `condition_variable` works only with `unique_lock<mutex>`, which allows implementations to be more efficient; `condition_variable_any` works with any user-supplied lock type. ¶2 All the `wait` and `notify` member functions may be called concurrently.

## Why wakeups are not lost (¶3–¶4)

¶3 Executions of `notify_one` and `notify_all` are atomic. Executions of `wait`, `wait_for` and `wait_until` are performed in three atomic parts:

1. release the mutex and enter the waiting state;
2. unblock the wait;
3. reacquire the lock.

¶4 The implementation behaves as if all executions of `notify` and every part of every wait are in a single unspecified total order consistent with the [[g:happens-before|happens before]] order.

The key is part 1: releasing the mutex and entering the wait are one atomic step, with no gap in between. Hence:

- the waiter checks the condition while holding the lock, finds it false, and calls `wait`;
- the notifier, to modify the condition, must first acquire the same lock, which can only happen after the waiter has finished part 1, at which point the waiter is already waiting;
- the notifier's subsequent `notify` comes after part 1 in the total order and is sure to wake it.

If the condition is modified without holding the lock, the modification may land exactly between the waiter checking the condition and calling `wait`:

```text
waiter (holds the lock)              notifier (does not hold the lock)
--------------------------          ------------------------
check ready, result is false
                                     ready = true
                                     cv.notify_one()   // no thread is waiting yet
cv.wait(lk)  // releases the lock and waits; nobody will ever wake it
```

So the condition must be modified while holding the mutex, even if `ready` is a `std::atomic<bool>`. `notify` itself does not require holding the lock.

¶5 Construction and destruction of condition variables need not be synchronized.

## condition_variable [thread.condition.condvar]

### wait and spurious wakeups (¶7–¶16)

```cpp
void wait(unique_lock<mutex>& lock);
```

¶7 Preconditions: `lock` owns the lock, and the mutex is locked by the calling thread. In addition, either ¶7.1 no other thread is waiting on this condition variable, or ¶7.2 `lock.mutex()` is the same for all lock arguments supplied by all concurrently waiting threads.

¶8 Effects:

- ¶8.1 atomically calls `lock.unlock()` and blocks;
- ¶8.2 when unblocked, calls `lock.lock()` (possibly blocking on the lock), then returns;
- ¶8.3 the function unblocks when signaled by `notify_one()` or `notify_all()`, or spuriously.

What ¶8.3 explicitly allows is the **spurious wakeup** ([[g:spurious-wakeup|spurious wakeup]]): `wait` may return without any notification. This gives implementations freedom; some platforms' underlying primitives return early for reasons such as signals. Also, by the time `wait` returns, another thread may already have changed the condition back. So a `wait` without a predicate must be written inside a loop that checks the condition.

¶13 The predicate version is that loop:

```cpp
template<class Predicate> void wait(unique_lock<mutex>& lock, Predicate pred);
// equivalent to
while (!pred())
  wait(lock);
```

The same-mutex requirement of ¶7.2 is often overlooked. Two threads waiting on the same `condition_variable` with `m1` and `m2` respectively is UB. POSIX's `pthread_cond_wait` has the same requirement.

### A failed wait can only terminate (¶9–¶11)

¶9 The postcondition of `wait` is that the calling thread holds the lock again. ¶10 It throws nothing. ¶11 If the postcondition cannot be satisfied, `terminate()` is called; Note 2 says this can happen if reacquiring the lock throws.

This is the only reasonable choice. The function cannot return normally, because the caller would believe it holds the lock; nor can it throw, because during stack unwinding the `unique_lock` destructor would unlock a mutex that is not locked.

### Timed waits (¶17–¶41)

¶17–¶22 `wait_until(lock, abs_time)` is the same as `wait`, except that it also unblocks when the absolute timeout expires ([[thread.req]]). ¶20 It returns `cv_status::timeout` if the timeout expired, otherwise `cv_status::no_timeout`. ¶18.4 If the function exits via an exception (the clock may throw timeout-related exceptions), `lock.lock()` is called before exiting, keeping the caller's `unique_lock` consistent.

[thread.condition.general] ¶6 defines an exposition-only function *rel-to-abs*:

```cpp
template<class Dur>
  chrono::steady_clock::time_point rel-to-abs(const Dur& rel_time) {
    return chrono::steady_clock::now() + chrono::ceil<chrono::steady_clock::duration>(rel_time);
  }
```

¶23–¶28 Every `wait_for(lock, rel_time)` is defined as `wait_until(lock, rel-to-abs(rel_time))`. The base is `steady_clock`, so changing the system time does not affect relative timeouts. `ceil` rounds up, so on a very coarse clock `wait_for(1ns)` does not turn into no wait at all.

¶29–¶34 `wait_until` with a predicate is equivalent to:

```cpp
while (!pred())
  if (wait_until(lock, abs_time) == cv_status::timeout)
    return pred();
return true;
```

¶32 Note 6 points out that the return value indicates whether the predicate is finally true, regardless of whether the timeout expired: if the condition happens to hold at the moment of timeout, it returns `true`. ¶35–¶41 `wait_for` with a predicate is analogous; ¶37 Note 8 adds that if `pred()` is true initially, it does not block even if the timeout has already passed.

!!! impl "How libc++ implements relative timeouts"
    libc++'s `condition_variable` wraps a `pthread_cond_t`. When the platform provides `pthread_cond_clockwait` (as glibc does), `steady_clock` waits use `CLOCK_MONOTONIC` directly. macOS lacks that function, so libc++ has to convert the duration to an absolute `system_clock` time and pass it to `pthread_cond_timedwait`, then use `steady_clock` after return to decide whether it timed out (see [[thread.req]]).

### Notification and destruction (¶4–¶6)

¶5 `notify_one()` unblocks one of the blocked threads, if any; ¶6 `notify_all()` unblocks all of them. Both are `noexcept`, and neither requires the caller to hold the lock.

¶4 The destructor's only precondition is that no thread is blocked on the condition variable. Note 1 explains that this is weaker than the usual rule. Under the usual rule, all `wait` calls would have to happen before destruction; here it is only required that the notification that unblocked the waits happen before destruction. The woken threads may still be in part 3 waiting to reacquire the lock, but they are no longer blocked on the condition variable, so the notifier may destroy the condition variable right after `notify_all()`.

### notify_all_at_thread_exit [thread.condition.nonmember]

```cpp
void notify_all_at_thread_exit(condition_variable& cond, unique_lock<mutex> lk);
```

¶2 This function transfers ownership of the lock held by `lk` into internal storage, and schedules `cond.notify_all(); lk.unlock();` to run when the current thread exits. ¶3 This notification and unlock are sequenced after the destruction of all of the current thread's `thread_local` objects.

Its purpose is to wait for a detached thread to finish, including the destruction of its `thread_local` objects. Setting a flag and notifying at the end of the thread function cannot achieve this, because `thread_local` objects are destroyed after the thread function returns.

¶1 Its preconditions are the same as `wait`'s: `lk` is locked, and all concurrent waiters use the same mutex. ¶4 Note 1 warns that the lock is held until the thread exits, which can cause deadlock due to lock ordering. ¶5 Note 2 warns that a waiter woken spuriously must not mistakenly assume the thread has finished; the usual practice is to satisfy the waited-for condition while holding `lk`, and not to release that lock before calling this function.

## condition_variable_any [thread.condition.condvarany]

### Working with any lock [thread.condition.condvarany.general]

¶1 The template parameter `Lock` of `condition_variable_any` need only meet *Cpp17BasicLockable*. Note 1 explains that if a lock other than a standard mutex or a `unique_lock` of a standard mutex is used, any synchronization needed by the predicate must be provided by that lock itself.

Its four non-interruptible `wait` family functions ([thread.condvarany.wait]) correspond one-to-one with those of `condition_variable`, with `unique_lock<mutex>` replaced by `Lock`. It also lacks the precondition that all concurrent waiters use the same mutex. Common uses:

- waiting on a `shared_lock<shared_mutex>`, so that a reader holds only a shared lock while waiting;
- waiting on a `unique_lock<timed_mutex>` or a user-defined lock.

¶2 The constructor may throw `bad_alloc`, because the implementation may need to allocate memory. ¶4 The destructor uses the same weakened precondition as `condition_variable`.

!!! impl "libc++'s condition_variable_any"
    Internally, libc++'s `condition_variable_any` is a `condition_variable` plus a `shared_ptr<mutex>`; the `make_shared` in the constructor is where `bad_alloc` comes from. `wait(lock)` first copies this `shared_ptr`, locks the internal mutex, then unlocks the user's lock, and waits on the internal mutex; on return it unlocks the internal mutex first and then relocks the user's lock.

    Copying the `shared_ptr` satisfies the weakened destruction rule: after the condition variable is destroyed, the internal mutex held by waiters still in part 3 remains valid. `notify` also briefly acquires the internal mutex, which makes releasing the user's lock and entering the wait atomic as far as the notifier is concerned.

### Interruptible waits [thread.condvarany.intwait] {{c++20}}

```cpp run title="cv-stop.cpp" ok
#include <condition_variable>
#include <cstdio>
#include <mutex>
#include <queue>
#include <thread>

std::mutex m;
std::condition_variable_any cv;
std::queue<int> q;

int main() {
  std::jthread worker([](std::stop_token st) {
    std::unique_lock lk(m);
    while (cv.wait(lk, st, [] { return !q.empty(); })) {   // returns false when stop is requested and the queue is empty
      std::printf("got %d\n", q.front());
      q.pop();
    }
    std::puts("stopped");
  });
  {
    std::lock_guard lk(m);
    q.push(1);
  }
  cv.notify_one();
}   // ~jthread does request_stop() and then join(); worker wakes and exits
```

¶1 These `wait` functions are notified when a stop request is made on the given `stop_token`, and then return immediately, returning `false` if the predicate is false at that point.

¶2 `wait(lock, stoken, pred)` registers `*this` for the duration of the call to be notified if a stop request is made on `stoken`, and is then equivalent to:

```cpp
while (!stoken.stop_requested()) {
  if (pred())
    return true;
  wait(lock);
}
return pred();
```

¶3 Note 1 points out that the return value indicates whether the predicate is finally true, regardless of whether a stop was requested. ¶7–¶13 The timed versions are bounded by the predicate, the stop request and the timeout together; ¶8 Note 3 points out that it does not block if the predicate is true initially, a stop has already been requested, or the timeout has already passed.

Interruptible waits come only in predicate versions. Without a predicate, on return the caller could not tell whether it was notified, stopped or spuriously woken. How `stop_token` works is in [[thread.stoptoken]], and the use of `jthread` in [[thread.threads]].

## Common misconceptions

!!! pitfall "Unlocking before notifying is always better"
    Notifying outside the lock is usually more efficient, since the woken thread does not immediately block on the mutex; the queue example at the start is written that way. But if the condition variable's lifetime is controlled by the waiter, it is wrong:

    ```cpp
    struct Completion { std::mutex m; std::condition_variable cv; bool done = false; };

    void worker(Completion* c) {
      { std::lock_guard lk(c->m); c->done = true; }
      c->cv.notify_one();        // *c may already have been destroyed here
    }

    void wait_for_worker() {
      Completion c;              // on the waiter's stack
      std::thread(worker, &c).detach();
      std::unique_lock lk(c.m);
      c.cv.wait(lk, [&] { return c.done; });
    }                            // c is destroyed on return
    ```

    After the worker unlocks and before it notifies, the waiter may get the lock and see `done` true (perhaps it had not even started waiting, perhaps it woke spuriously), so it returns and destroys `c`. The worker then calls `notify_one` on a destroyed condition variable, which is UB. Notifying inside the lock fixes it: the waiter must get the lock before it can return, and by then the notification has finished.

!!! pitfall "If the condition is an atomic variable, no lock is needed to modify it"
    `ready = true; cv.notify_one();` without holding `m` loses wakeups, for the reasons analyzed above for paragraphs 3 and 4. State involved in the predicate must be modified while holding the mutex the waiter uses. If you only want to wait for an atomic variable to change, use `atomic::wait` ([[atomics.wait]]), which needs no mutex.

!!! pitfall "notify_one wakes exactly one thread"
    Paragraph 5 guarantees only that one of the threads is unblocked, but other threads may be spuriously woken at the same time. Program logic must assume any waiter may wake up at any time.

## Questions

!!! question "Question 1"
    If `cv.wait_for(lk, 100ms, pred)` returns `false`, can you conclude that it timed out?

<details markdown="1">
<summary>Answer</summary>

Yes. By the equivalent code in paragraph 30, it returns `false` only if the inner `wait_until` returns `cv_status::timeout` and `pred()` is false at that point; every other path returns `true`. Conversely, returning `true` does not mean there was no timeout (¶32 Note 6).
</details>

!!! question "Question 2"
    Why does `condition_variable` accept only `unique_lock<mutex>`?

<details markdown="1">
<summary>Answer</summary>

[thread.condition.general] ¶1 says it allows implementations to be more efficient. Restricted to `std::mutex`, an implementation can hand the underlying `pthread_mutex_t` straight to `pthread_cond_wait` and let the operating system do the atomic unlock-and-wait. `condition_variable_any`, facing arbitrary lock types, can only achieve that atomicity by introducing an extra internal mutex, as libc++ does, at greater cost.
</details>

## Summary

| Rule | Source |
|---|---|
| `wait` has three atomic parts, and all operations are in a total order consistent with happens before | general ¶3–¶4 |
| the condition must be modified while holding the mutex, or wakeups are lost | follows from general ¶3–¶4 |
| `wait` may return spuriously; the predicate version is equivalent to `while (!pred()) wait(lock);` | condvar ¶8.3, ¶13 |
| concurrent waiters on one `condition_variable` must use the same mutex | condvar ¶7.2 |
| `terminate` is called if relocking fails | condvar ¶11 and others |
| `wait_for` measures time with `steady_clock` | general ¶6 |
| a timed wait with a predicate returns the final value of the predicate | condvar ¶32, ¶39 |
| destruction requires only that no thread is blocked on the condition variable | condvar ¶4 |
| `condition_variable_any` can be woken by a stop request (predicate versions only) | [thread.condvarany.intwait] |
