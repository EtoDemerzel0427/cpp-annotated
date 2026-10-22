---
title: Mutex requirements and the six mutex types
summary: "The synchronization semantics of the standard library's mutexes: who owns a mutex, unlock synchronizing with subsequent locking, a failed try_lock not synchronizing, which misuses are undefined behavior, and the extra rules for recursive, timed and shared mutexes."
updated: 2026-10-19
---

!!! tldr
    - A thread owns a mutex from a successful lock until it calls `unlock`. `unlock()` synchronizes with a subsequent lock operation that obtains ownership of the same mutex; this is the standard's basis for protecting data with locks.
    - `try_lock()` may fail spuriously, and a failed `try_lock()` does not synchronize, so nothing can be inferred from it about another thread's state.
    - Locking a non-recursive mutex twice, unlocking a mutex you do not own, destroying a mutex that is held, and a thread ending while holding a mutex are all undefined behavior; neither deadlock nor an exception is guaranteed.
    - In a shared mutex, readers do not synchronize with each other. Modifying data under a shared lock is a data race; acquiring shared ownership recursively is UB.

## Ownership [thread.mutex.requirements.general]

The *Cpp17Lockable* family of requirements in [[thread.req]] specifies only the interface and states explicitly that the nature of lock ownership and synchronization are not part of the requirements. [thread.mutex.requirements] supplies the synchronization semantics for the standard library's own six mutexes; it is also the normative source of [[intro.races#3]] Note 3 (acquiring a mutex is an acquire operation, releasing it is a release operation).

¶1 Mutex objects help protect against data races and allow safe synchronization of data between execution agents. An **execution agent** is an entity such as a thread that may perform work in parallel with other agents ([[thread.req.lockable.general]]). An execution agent **owns** a mutex from the time it successfully calls one of the lock functions until it calls `unlock`. Mutexes can be recursive or non-recursive, and can grant ownership to one or many execution agents simultaneously. The preconditions below are all phrased in terms of ownership.

## Common requirements [thread.mutex.requirements.mutex.general]

¶1 The **mutex types** are `mutex`, `recursive_mutex`, `timed_mutex`, `recursive_timed_mutex`, `shared_mutex` and `shared_timed_mutex`, all of which meet *Cpp17Lockable*.

¶2 They are default-constructible and destructible, throw `system_error` if initialization fails, and are neither copyable nor movable. One reason they are not movable is that other threads may be blocked on the object's address. ¶3 lists the error conditions member functions may report, such as `operation_not_permitted` (the thread lacks the privilege).

### Locking and unlocking behave as atomic operations (¶4)

!!! std
    For purposes of determining the existence of a data race, these behave as atomic operations. The lock and unlock operations on a single mutex appear to occur in a single total order.

¶4 For purposes of determining the existence of a data race, lock and unlock operations behave as atomic operations; lock and unlock operations on a single mutex appear to occur in a single total order. Note 2 says this total order can be viewed as the mutex's modification order.

This sentence does two things. First, several threads `lock`ing the same mutex at once is not a data race; otherwise mutexes would be unusable. Second, "a prior `unlock`" in the synchronization rules below means an `unlock` that comes earlier in this total order.

Note 3 adds: construction and destruction of a mutex need not be thread-safe; other synchronization must be used to ensure that the mutex object is initialized and visible to other threads.

### lock (¶5–¶12)

| Paragraph | Specification |
|---|---|
| ¶6 Preconditions | for `mutex`, `timed_mutex`, `shared_mutex`, `shared_timed_mutex`: the calling thread does not own the mutex |
| ¶7 Effects | blocks the calling thread until ownership is obtained for it |
| ¶8 Synchronization | prior `unlock()` operations on the same object synchronize with this operation |
| ¶9 Postconditions | the calling thread owns the mutex |
| ¶11–¶12 Throws | `system_error` when required; error conditions include `resource_deadlock_would_occur` if the implementation detects that a deadlock would occur |

By ¶6, locking a non-recursive mutex twice violates a precondition and is UB {{ub}}. The standard guarantees neither a deadlock nor an exception. ¶12.2 only says that if the implementation happens to detect it, it may report `resource_deadlock_would_occur`.

### try_lock (¶13–¶19)

¶14 has the same precondition as `lock`. ¶15 `try_lock` attempts to obtain ownership without blocking; on failure it has no effect and returns immediately. An implementation may fail even if no thread holds the mutex; Note 4 says this spurious failure is normally uncommon but allows implementations based on a simple CAS. Implementations should ensure that `try_lock()` does not consistently return `false` in the absence of contention.

¶16 Only if `try_lock()` returns `true` do prior `unlock()` operations synchronize with it. ¶19 `try_lock` throws nothing.

!!! std
    Since `lock()` does not synchronize with a failed subsequent `try_lock()`, the visibility rules are weak enough that little would be known about the state after a failure, even in the absence of spurious failures.

Note 5 in ¶16 explains that a failed `try_lock()` cannot be used to infer "another thread has taken the lock, so I can see what it wrote before locking":

```cpp title="trylock-failure.cpp" ub
#include <chrono>
#include <mutex>
#include <thread>
std::mutex m;
int data = 0;
int main() {
  std::thread t([] {
    data = 1;                        // ① written before locking
    std::lock_guard g(m);            // ②
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
  });
  while (m.try_lock()) m.unlock();   // until try_lock fails
  int r = data;   // UB: a failed try_lock does not synchronize; no happens before between ① and this read
  (void)r;
  t.join();
}
```

ThreadSanitizer reports a `data race` for this program.

### unlock (¶20–¶25)

¶21 The precondition is that the calling thread owns the mutex. ¶22 Releases the calling thread's ownership. ¶24 This operation synchronizes with subsequent lock operations that obtain ownership on the same object. ¶25 Throws nothing.

There are three typical ways to violate ¶21: unlocking a mutex that was never locked; locking in thread A and unlocking in thread B; unlocking an already unlocked mutex again. All are UB.

```cpp title="unlock-not-owned.cpp" ub
#include <cstdio>
#include <mutex>
int main() {
  std::mutex m;
  m.unlock();   // UB: the calling thread does not own m (¶21)
  std::puts("returned");
}
```

Run with Clang 23 + libc++ on macOS, the program prints `returned` and exits normally, with no diagnostic. libc++'s `mutex::unlock` forwards straight to `pthread_mutex_unlock` and does not check the return value when library assertions are disabled. It just happened not to go wrong this time.

## mutex [thread.mutex.class]

¶1 `mutex` is a non-recursive mutex with exclusive ownership. While one thread owns it, other threads' attempts to acquire it fail (`try_lock`) or block (`lock`) until the owner calls `unlock`. ¶3 It meets all the mutex requirements and is a standard-layout class. Its default constructor is `constexpr` and `noexcept`; see [[thread.mutex]].

¶4 Note 2: a program may deadlock if the thread that owns a `mutex` calls `lock()` on it; if the implementation can detect the deadlock, a `resource_deadlock_would_occur` error condition might be observed. The normative rule is still the ¶6 precondition above; this is only a description of possible consequences.

¶5 The following two cases are UB {{ub}}: destroying a `mutex` owned by any thread; a thread terminating while owning a `mutex`. The latter means a thread function that returns without unlocking is UB, one more reason to use RAII locks ([[thread.lock]]).

### Destroying immediately after unlock (¶2)

¶2 Note 1 covers an often overlooked scenario: after thread A calls `unlock()`, thread B may lock, find the mutex no longer in use, unlock and destroy it, all of this possibly before A appears to have returned from `unlock`. As long as A does not access the mutex after `unlock` returns, a conforming implementation must handle this correctly. It typically arises in reference-counted objects protected by a mutex:

```cpp run title="refcounted-mutex.cpp" ok
#include <mutex>
#include <thread>

struct Shared {
  std::mutex m;
  int refs = 2;
};

void release(Shared* s) {
  s->m.lock();
  bool last = --s->refs == 0;
  s->m.unlock();        // another thread may delete s right after this
  if (last) delete s;   // OK
}

int main() {
  auto* s = new Shared;
  std::thread a(release, s), b(release, s);
  a.join(); b.join();
}
```

The caller does not touch `s->m` after `unlock`; Note 1 requires the implementation to guarantee that `unlock` itself does not either. If some implementation's `unlock` first marked the state unlocked and then read the waiter queue inside the mutex to wake a waiter, it would access freed memory; Note 1 is there to rule out such implementations. This program produces no reports under ThreadSanitizer or AddressSanitizer.

## recursive_mutex [thread.mutex.recursive]

```cpp run title="recursive.cpp" ok
#include <cstdio>
#include <mutex>

std::recursive_mutex rm;
int depth = 0;

void visit(int n) {
  std::lock_guard g(rm);   // the same thread locking again: valid
  ++depth;
  if (n > 0) visit(n - 1);
}

int main() {
  visit(3);
  std::printf("%d\n", depth);   // 4
}
```

¶1 `recursive_mutex` is a recursive mutex with exclusive ownership. ¶3 The owner can call `lock()` or `try_lock()` again to acquire additional levels of ownership. The maximum number of levels is unspecified {{unspec}}; once it is reached, a further `try_lock()` fails and a further `lock()` throws `system_error`. Each level of ownership must be matched by an `unlock()`, and only after all levels are released can another thread obtain ownership.

¶4 As with `mutex`, destroying a `recursive_mutex` that is owned and a thread terminating while owning it are UB.

## Timed mutexes [thread.timedmutex.requirements]

[thread.timedmutex.requirements.general] ¶1 The **timed mutex types** are `timed_mutex`, `recursive_timed_mutex` and `shared_timed_mutex`, which meet *Cpp17TimedLockable*.

`try_lock_for(rel_time)` (¶2–¶8) attempts to obtain ownership within a relative timeout. The precondition is like `lock`'s: for non-recursive types, the calling thread must not already own it. ¶4 specifies that if `rel_time` is less than or equal to zero, it attempts without blocking, as if by `try_lock()`; the function returns before the timeout only if ownership was obtained. Like `try_lock()`, there is no guarantee of obtaining it even if the lock is available. ¶5 If it returns `true`, prior `unlock()` operations synchronize with it. ¶8 It may throw timeout-related exceptions ([[thread.req]]).

`try_lock_until(abs_time)` (¶9–¶15) is analogous: if `abs_time` has already passed it attempts without blocking; ¶12 it synchronizes if it returns `true`.

### timed_mutex and recursive_timed_mutex

[thread.timedmutex.class] ¶1 `timed_mutex` is a non-recursive mutex with exclusive ownership; ¶2 it is a standard-layout class. ¶3 lists three kinds of UB:

- ¶3.1 destroying a `timed_mutex` owned by any thread;
- ¶3.2 a thread that owns a `timed_mutex` calling `lock()`, `try_lock()`, `try_lock_for()` or `try_lock_until()` on it;
- ¶3.3 a thread terminating while owning it.

¶3.2 includes `try_lock` too: calling `try_lock()` on a non-recursive mutex you already own does not safely return `false`. The same holds for `mutex`, based on the precondition of `try_lock` in the common requirements (¶14), even though the class clause for `mutex` does not repeat it.

In [thread.timedmutex.recursive], `recursive_timed_mutex` parallels `recursive_mutex`: all four lock functions can add levels of ownership.

## Shared mutexes [thread.sharedmutex.requirements]

```cpp run title="shared-mutex.cpp" ok
#include <cstdio>
#include <map>
#include <mutex>
#include <shared_mutex>
#include <string>
#include <thread>
#include <vector>

class Registry {
  mutable std::shared_mutex m;
  std::map<std::string, int> table;
public:
  int get(const std::string& k) const {
    std::shared_lock lk(m);   // several readers may enter at once
    auto it = table.find(k);
    return it == table.end() ? -1 : it->second;
  }
  void set(const std::string& k, int v) {
    std::unique_lock lk(m);   // the writer has exclusive access
    table[k] = v;
  }
};

int main() {
  Registry r;
  r.set("a", 1);
  {
    std::vector<std::jthread> ts;
    for (int i = 0; i < 4; ++i)
      ts.emplace_back([&] {
        for (int k = 0; k < 1000; ++k) (void)r.get("a");
      });
    ts.emplace_back([&] {
      for (int k = 0; k < 1000; ++k) r.set("a", k);
    });
  }
  std::printf("%d\n", r.get("a"));   // 999
}
```

### Common requirements

[thread.sharedmutex.requirements.general] ¶1 The **shared mutex types** are `shared_mutex` and `shared_timed_mutex`; they meet all the requirements of mutex types and additionally meet *Cpp17SharedLockable*.

¶2 In addition to exclusive ownership, shared mutexes provide a **shared lock** ownership mode: several execution agents can hold a shared lock at once, but while any agent holds a shared lock, no agent holds an exclusive lock, and vice versa. The maximum number of agents that can share is unspecified but at least 10000; agents beyond the limit block until the number of shared locks drops below it.

| Operation | Precondition | Synchronization |
|---|---|---|
| `lock_shared()` (¶3–¶10) | the calling thread has no ownership of it (¶4) | prior `unlock()` operations synchronize with it (¶6) |
| `unlock_shared()` (¶11–¶16) | the calling thread holds a shared lock (¶12) | synchronizes with subsequent `lock()` operations that obtain ownership (¶15) |
| `try_lock_shared()` (¶17–¶23) | no ownership (¶18) | if it returns `true`, prior `unlock()` operations synchronize with it (¶20) |

Putting these together with the rules for `lock`/`unlock` in the common requirements, the synchronization relations are:

| From | To | Synchronizes? |
|---|---|---|
| writer `unlock()` | writer `lock()` | yes ([thread.mutex.requirements.mutex.general] ¶8) |
| writer `unlock()` | reader `lock_shared()` | yes (¶6) |
| reader `unlock_shared()` | writer `lock()` | yes (¶15) |
| reader `unlock_shared()` | reader `lock_shared()` | no |

The last row is deliberate: readers only read and need no synchronization among themselves. But it also means that modifying data under a shared lock is a data race, even if every modifier holds the lock. `mutable` caches and lazily initialized members fall into this category.

### shared_mutex and shared_timed_mutex

[thread.sharedmutex.class] ¶1 `shared_mutex` is a non-recursive mutex with shared ownership semantics; ¶2 it is a standard-layout class. ¶3 lists three kinds of UB:

- ¶3.1 destroying a `shared_mutex` owned by any thread;
- ¶3.2 a thread attempting to recursively gain any ownership, including calling `lock_shared()` again while holding a shared lock;
- ¶3.3 a thread terminating while having any ownership.

¶4 `shared_mutex` may be a synonym for `shared_timed_mutex`.

¶3.2 is often thought harmless for shared locks. The problem: while reader A holds a shared lock, writer B starts waiting; to avoid writer starvation, many implementations then block new shared locks. So A's second `lock_shared()` waits for B, B waits for A, and they deadlock.

`shared_timed_mutex` in [thread.sharedtimedmutex.requirements] meets the requirements of both timed mutexes and shared mutexes, and additionally provides `try_lock_shared_for` and `try_lock_shared_until` (¶2–¶15): the precondition is no ownership; with a zero or past timeout they attempt without blocking; if they return `true`, prior `unlock()` operations synchronize with them. The three kinds of UB specified in [thread.sharedtimedmutex.class] are the same as for `shared_mutex`.

!!! impl "libc++'s shared_mutex: two gates"
    libc++'s `shared_mutex` does not use `pthread_rwlock_t`; it consists of a `mutex`, two `condition_variable`s and an `unsigned` state word: the top bit means a writer has entered, and the remaining 31 bits count readers, with a limit of 2<sup>31</sup>−1, far beyond the 10000 required by ¶2. A writer first sets the top bit at the first gate, after which new readers are kept out; then at the second gate it waits for the existing readers to leave. This is a writer-preferring policy, and exactly the typical reason recursive shared locking deadlocks.

## Common misconceptions

!!! pitfall "Locking twice in the same thread deadlocks"
    Locking a `mutex` twice violates a precondition and is UB; Note 2 says only that it may deadlock. The actual behavior depends on the platform: pthread mutexes with default attributes usually deadlock, those with the error-checking attribute return an error, and some debug runtimes terminate the program outright. Do not rely on any of these.

!!! pitfall "You can lock in one thread and unlock in another"
    Ownership of a `std::mutex` belongs to a thread. When acquisition in one thread and release in another is needed, use `std::binary_semaphore` ([[thread.sema]]).

## Questions

!!! question "Question 1"
    Are construction and destruction of a `std::mutex` thread-safe?

<details markdown="1">
<summary>Answer</summary>

They need not be (common requirements ¶4 Note 3). The mutex object itself must be properly published to other threads: doing `new std::mutex` in one thread and handing it via a relaxed atomic pointer to another thread that then calls `lock()` is a data race. A namespace-scope `std::mutex` is constant-initialized by its `constexpr` constructor and ready before any thread starts, so it does not have this problem.
</details>

!!! question "Question 2"
    Thread A executes `m.lock(); x = 1; m.unlock();` and thread B executes `if (m.try_lock()) { r = x; m.unlock(); }`. Is there a data race?

<details markdown="1">
<summary>Answer</summary>

No. B reads `x` only if `try_lock()` succeeds. If in the total order A's `unlock` precedes B's `try_lock`, they synchronize (¶16), and `x = 1` happens before `r = x`; if B obtains the lock first, B's `unlock` synchronizes with A's `lock` (¶24, ¶8), and `r = x` happens before `x = 1`. In both cases the two accesses are related by happens before. If `try_lock` fails, B does not access `x` at all.
</details>

## Summary

| Rule | Source |
|---|---|
| lock and unlock behave as atomic operations, in a single total order on one mutex | common requirements ¶4 |
| `unlock()` synchronizes with a subsequent lock operation that obtains ownership | common requirements ¶8, ¶24 |
| `try_lock` may fail spuriously, and does not synchronize on failure | common requirements ¶15–¶16 |
| locking a non-recursive mutex twice, unlocking a mutex you do not own: UB | common requirements ¶6, ¶14, ¶21 |
| destroying an owned mutex, a thread ending while holding a mutex: UB | each class's clause |
| a zero or past timeout behaves like `try_lock` | timed mutexes ¶4, ¶11 |
| readers do not synchronize with each other; acquiring shared ownership recursively: UB | shared mutexes ¶6, ¶15; `shared_mutex` ¶3 |
