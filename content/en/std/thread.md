---
title: Concurrency support library
summary: "A guide to chapter 32: how threads, atomic operations, locks, condition variables, semaphores, latches/barriers, futures and the rest provide the means of synchronization for the memory model, and which elements to look at when reading these function specifications."
updated: 2026-10-19
---

!!! tldr
    - The core language defines only the ordering relations between threads (happens before and so on) and "a data race is UB"; the means of actually establishing those relations are all in chapter 32.
    - Whether a write in one thread is visible to another can only be decided from the *Synchronization* element of the function specifications; `sleep_for` and `yield` explicitly do not synchronize.
    - "Concurrent calls do not introduce data races" says only that those calls are safe with respect to each other; it provides no synchronization.
    - Violating *Preconditions* (such as unlocking a mutex you do not own) is UB, and implementations usually do not check; *Error conditions* are defined failures reported by exceptions.

## The half the core language is missing

```cpp run title="sleep-is-not-sync.cpp" ub
#include <chrono>
#include <thread>
int data = 0;
int main() {
  std::thread t([] { data = 1; });
  std::this_thread::sleep_for(std::chrono::milliseconds(100));
  int r = data;   // UB: a data race with the write in t
  (void)r;
  t.join();
}
```

The main thread sleeps for 100 milliseconds, and `t` has almost certainly finished writing long before, but this program still has a data race. By [[intro.races#17]], two conflicting accesses to the same object from two threads (at least one a write) form a data race unless there is a **happens before** relation between them, and the result is UB. Being earlier in time does not count. Run with `-fsanitize=thread`, ThreadSanitizer reports a `data race`.

Relations like happens before are defined in [[intro.multithread]], but the core language itself has no syntax to establish them: no keyword to create a thread, no built-in lock. The operations that produce **synchronization** (synchronizes with, [[intro.races#6]]) are all library functions in chapter 32. Moving `int r = data;` after `t.join()` makes it correct, because [[thread.thread.member#4]] specifies that the completion of the thread synchronizes with the return from `join()`.

Common sources of synchronization:

- the completion of the `std::thread` constructor synchronizes with the start of the thread function, and the completion of the thread synchronizes with the return from `join()` ([[thread.threads]]);
- the `memory_order` of an atomic operation determines which relations a load or store establishes ([[atomics.order]]);
- a mutex's `unlock()` synchronizes with a subsequent `lock()` on the same mutex ([[thread.mutex.requirements]]);
- condition variables, semaphores, latches, barriers and futures each state in their function specifications the relations they establish.

## What the chapter contains (¶1)

¶1 is a single sentence and a table (Table 154) listing the subclauses and headers:

| Subclause | Contents | Header |
|---|---|---|
| [[thread.req]] | General requirements: exceptions, native handles, timeouts, the *Cpp17Lockable* family of requirements | — |
| [[thread.stoptoken]] | `stop_token`, `stop_source`, `stop_callback`, C++26's `inplace_stop_*` and `never_stop_token` | `<stop_token>` |
| [[thread.threads]] | `thread`, `jthread`, `this_thread` | `<thread>` |
| [[atomics]] | `memory_order`, `atomic<T>`, `atomic_ref<T>`, `atomic_flag`, fences, waiting and notifying | `<atomic>`, `<stdatomic.h>` |
| [[thread.mutex]] | Mutexes, `lock_guard`/`scoped_lock`/`unique_lock`/`shared_lock`, `std::lock`, `call_once` | `<mutex>`, `<shared_mutex>` |
| [[thread.condition]] | `condition_variable`, `condition_variable_any` | `<condition_variable>` |
| [[thread.sema]] | `counting_semaphore`, `binary_semaphore` | `<semaphore>` |
| [[thread.coord]] | `latch`, `barrier` | `<latch>`, `<barrier>` |
| [[futures]] | `promise`, `future`, `shared_future`, `packaged_task`, `async` | `<future>` |
| [[saferecl]] {{c++26}} | RCU, hazard pointers | `<rcu>`, `<hazard_pointer>` |

## Which elements to look at in a function specification

Each function specification in the library clauses is divided into elements (*Effects*, *Returns* and so on), whose legal force is set by [[structure.specifications]] ¶3. When reading this chapter, the following three matter most.

### Synchronization: the only basis for visibility between threads

[[structure.specifications]] ¶3.7 specifies that the *Synchronization* element gives the synchronization operations applicable to the function. This chapter uses wording of four strengths:

| Wording | Example | What follows |
|---|---|---|
| A synchronizes with B | thread completion → `join()` returns; `unlock()` → a subsequent `lock()` | A happens before B ([[intro.races#7]]); writes before A are visible to reads after B |
| A strongly happens before B | `latch::count_down` → return from the call it unblocks ([[thread.latch.class]] ¶9); `semaphore::release` → a `try_acquire` that observes the result ([[thread.sema.cnt]] ¶10) | stronger than happens before ([[intro.races#8]]), also constraining the total order of seq_cst operations ([[atomics.order#4]]) |
| do not introduce data races | concurrent calls to member functions of the same `latch` or `counting_semaphore` | guarantees only that these calls do not race with each other; no synchronization comes with it |
| *Synchronization*: None | `this_thread::yield`, `sleep_for`, `sleep_until` ([[thread.thread.this]]) | explicitly no synchronization; the example above is this case |

The third row is easy to misread. "Do not introduce data races" means the object's own internal state can be accessed concurrently; for example, two threads can call member functions on one `latch` at the same time. It does not guarantee that an ordinary variable written by one thread before the call is visible to the other. For visibility you still need to find a synchronizes with or happens before.

### Preconditions: violation is UB

[[structure.specifications]] ¶3.4 specifies that violating *Preconditions* is undefined behavior. Most preconditions in this chapter have to do with ownership:

- the thread calling `unlock()` must own the mutex ([[thread.mutex.requirements.mutex.general]] ¶21);
- a thread that already owns a `std::mutex` cannot `lock()` it again;
- no thread may still be blocked on a `condition_variable` when it is destroyed ([[thread.condition]]);
- `counting_semaphore::release` must not raise the count above `max()` ([[thread.sema.cnt]]).

Implementations usually do not check these conditions. libc++ on macOS, when `unlock()` is called on a `std::mutex` nobody owns, neither reports an error nor terminates; the program keeps running.

### Error conditions: defined failures

*Error conditions* list defined failures: the function throws `system_error` whose `code()` equals one of the listed `errc` values ([[thread.req.exception]]). For example, a thread calling `join()` on the `std::thread` that represents itself throws `resource_deadlock_would_occur` per [[thread.thread.member]]; that is behavior the standard promises, not UB.

## Memory model concepts and their sources in the library

| Memory model concept ([[intro.races]]) | Source in this chapter |
|---|---|
| synchronizes with (¶6) | release/acquire atomic operations ([[atomics.order#2]]), fences ([[atomics.fences]]), the *Synchronization* element of each function |
| modification order (¶4) | each atomic object has one; mutex lock/unlock are also treated as atomic operations for the purpose of determining data races ([[thread.mutex.requirements.mutex.general]] ¶4) |
| release sequence (¶5) | atomic read-modify-write operations: `fetch_add`, `exchange`, successful `compare_exchange_*` |
| single total order S | `memory_order::seq_cst` ([[atomics.order#4]]) |
| blocking and progress guarantees ([[intro.progress]]) | atomic operations that are not lock-free are considered potentially blocking ([[atomics.lockfree#4]]); the various `wait` functions |

Suggested reading order: start with [[thread.threads]] (starting threads, joining); then [[thread.mutex.requirements]], [[thread.lock]], [[thread.condition]] (lock-based synchronization); then [[atomics.order]], [[atomics.types.generic]], [[atomics.fences]] (atomic operations and memory orders); next [[atomics.wait]], [[thread.sema]], [[thread.coord]]; and finally [[thread.stoptoken]] with `jthread`, [[futures]], [[saferecl]].

!!! impl "libc++ (macOS, Clang 23)"
    - Threads, mutexes and condition variables wrap pthreads directly: `sizeof(std::mutex)` is 64, `sizeof(std::condition_variable)` is 48, and `std::thread` stores just a `pthread_t`, size 8.
    - `atomic::wait`, `counting_semaphore`, `latch` and `barrier` are built on libc++'s own "spin, back off, platform wait" framework; see [[atomics.wait]].
    - Not yet provided: `atomic<shared_ptr<T>>`, atomic `fetch_max`/`fetch_min`, `constexpr` atomic operations, the `inplace_stop_token` family, `<rcu>`, `<hazard_pointer>`.
