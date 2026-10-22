---
title: Locks and generic locking algorithms
summary: "What each of the four RAII locks lock_guard, scoped_lock, unique_lock and shared_lock manages, why the locked mutex must outlive the lock, which misuses throw system_error rather than being UB, and how std::lock guarantees freedom from deadlock."
updated: 2026-10-19
---

!!! tldr
    - A lock is an RAII object that automatically unlocks a mutex on destruction. It only refers to the mutex and does not manage its lifetime: destroying the mutex before the lock is UB.
    - `lock_guard` and `scoped_lock` hold the lock for their entire lifetime; `unique_lock` and `shared_lock` record whether they hold it in an `owns` flag, so they can defer locking, unlock midway and be moved.
    - Locking a `unique_lock` twice or unlocking it when not held throws `system_error`, while the same operations directly on a `std::mutex` are UB. `release()` does not unlock.
    - `std::lock` and multi-argument `scoped_lock` guarantee no deadlock, but the exact locking order is unspecified.
    - `std::unique_lock<std::mutex>(m);` declares a variable named `m` and locks nothing. Always give lock objects a name.

## Why locks are needed

```cpp
std::mutex m;
int balance;

void withdraw(int n) {
  m.lock();
  if (balance < n) return;       // forgot to unlock
  balance -= n;
  m.unlock();
}
```

An early return or an exception skips the `unlock`, and the mutex stays held forever. A thread ending while holding a mutex is also UB ([[thread.mutex.requirements]]).

[thread.lock.general] ¶1 The standard library's solution is the **lock**: an object that holds a reference to a lockable object and may unlock it during its own destruction (such as when leaving block scope). A lockable object is one of a type with members like `lock`/`unlock`, which all the standard mutexes are ([[thread.req]]). A lock is said to **own** a lockable object if it is currently managing the ownership of that lockable object for a thread.

The same paragraph also specifies that a lock does not manage the lifetime of the lockable object it references. All four locks below write this down as a requirement, and violating it is UB.

¶2 Some lock constructors take a tag argument describing what to do with the lockable object at construction:

| Tag | Meaning |
|---|---|
| `std::defer_lock` | do not lock |
| `std::try_to_lock` | try to lock without blocking |
| `std::adopt_lock` | the calling thread already holds the lock; the lock object takes it over |

## lock_guard: lock on construction, unlock on destruction [thread.lock.guard]

```cpp run ok
#include <mutex>
std::mutex m;
int balance = 100;

bool withdraw(int n) {
  std::lock_guard lk(m);      // m.lock()
  if (balance < n) return false;
  balance -= n;
  return true;
}                             // ~lock_guard: m.unlock()

int main() { return withdraw(30) ? 0 : 1; }
```

¶1 A `lock_guard` holds ownership of the lockable object throughout its lifetime. If the lockable object it references does not exist for the entire lifetime of the `lock_guard`, the behavior is undefined {{ub}}. The template argument need only meet *Cpp17BasicLockable*, i.e. have `lock` and `unlock`.

¶2 `lock_guard(m)` stores a reference to `m` and calls `m.lock()`. ¶6 The destructor calls `unlock()`.

¶3 `lock_guard(m, adopt_lock)` only stores the reference, without locking. Its precondition is that the calling thread holds a non-shared lock on `m`; ¶5 it throws nothing.

`lock_guard` is neither copyable nor movable, and has no member functions for unlocking, querying and the like. Because it always holds the lock, its destructor needs to check no state, and the object contains only a reference.

## scoped_lock: locking several at once [thread.lock.scoped] {{c++17}}

Two threads locking the same pair of mutexes in opposite orders is the most common deadlock:

```cpp run title="scoped-lock-transfer.cpp" ok
#include <mutex>
#include <thread>

struct Account {
  std::mutex m;
  long balance = 100;
};

void transfer(Account& from, Account& to, long amt) {
  std::scoped_lock lk(from.m, to.m);   // lock both together, no deadlock
  from.balance -= amt;
  to.balance += amt;
}

int main() {
  Account a, b;
  std::jthread t1([&] { for (int i = 0; i < 100000; ++i) transfer(a, b, 1); });
  std::jthread t2([&] { for (int i = 0; i < 100000; ++i) transfer(b, a, 1); });
}
```

If `scoped_lock` were replaced with two `lock_guard`s constructed one after the other, t1 would lock a then b, t2 would lock b then a, and they would almost certainly deadlock.

¶1 `scoped_lock` is a variadic `lock_guard`: it too always holds the lock, and it too requires the referenced lockable objects to exist for its entire lifetime. The requirements on the template arguments fall into two cases:

- ¶1.1 with a single type, it must meet *Cpp17BasicLockable*, and the member `mutex_type` is that type;
- ¶1.2 otherwise, each type must meet *Cpp17Lockable* (which adds `try_lock`), and there is no `mutex_type` member.

¶2 The constructor has three cases by count: with zero lockable objects it does nothing; with one it calls `m.lock()`; with several it calls `std::lock(m...)`, using the deadlock-avoidance algorithm described below. Zero arguments are valid too, so generic code writing `std::scoped_lock lk(ms...);` need not special-case an empty pack.

¶3 The constructor adopting existing locks is `scoped_lock(adopt_lock, m...)`. The tag comes first because the parameter pack must come last, the opposite order from `lock_guard(m, adopt_lock)`. The precondition is that the calling thread holds a non-shared lock on each `m`. ¶6 The destructor calls `unlock()` on each lockable object.

## unique_lock: a lock that may not hold the lock [thread.lock.unique]

Inside a `unique_lock` are a pointer `pm` and a boolean `owns`. `owns` records whether the lock is currently held, so it can start out unlocked, unlock and relock midway, and hand ownership over to another `unique_lock`. This is exactly the kind of lock `condition_variable::wait` requires ([[thread.condition]]).

### Lifetime requirement and lockability [thread.lock.unique.general]

¶1 `unique_lock` is not copyable but is movable. If `pm` is not null and the lockable object it points to does not exist for the entire remaining lifetime of the `unique_lock`, the behavior is undefined. The template argument must meet *Cpp17BasicLockable*.

¶2 Note 1 points out that a `unique_lock<Mutex>` is itself a lockable object: it meets *Cpp17BasicLockable*, and when `Mutex` meets *Cpp17Lockable* or *Cpp17TimedLockable*, so does it. So a `unique_lock` can in turn be passed to `std::lock` or `condition_variable_any`.

### Construction [thread.lock.unique.cons]

| Constructor | Paragraphs | Effect | `owns` afterwards |
|---|---|---|---|
| `unique_lock()` | ¶1 | not associated with any mutex | `false` |
| `unique_lock(m)` | ¶2–¶3 | `m.lock()` | `true` |
| `unique_lock(m, defer_lock)` | ¶4 | does not lock, `noexcept` | `false` |
| `unique_lock(m, try_to_lock)` | ¶5–¶7 | `m.try_lock()` | its return value |
| `unique_lock(m, adopt_lock)` | ¶8–¶10 | does not lock; precondition: the calling thread already holds `m` | `true` |
| `unique_lock(m, abs_time)` | ¶11–¶13 | `m.try_lock_until(abs_time)` | its return value |
| `unique_lock(m, rel_time)` | ¶14–¶16 | `m.try_lock_for(rel_time)` | its return value |

`try_to_lock` and the two timed versions also require `Mutex` to meet *Cpp17Lockable* or *Cpp17TimedLockable*. The standard writes this as a precondition rather than a constraint; in practice, a type lacking `try_lock` fails to compile on instantiation.

¶17 Move construction takes over `u`'s `pm` and `owns`, leaving `u` unassociated and not holding a lock. ¶18 Move assignment is equivalent to `unique_lock(std::move(u)).swap(*this)`: the lock `*this` held moves into the temporary and is released when the temporary is destroyed. ¶20 The destructor calls `pm->unlock()` if `owns` is true.

### Misuse throws [thread.lock.unique.locking]

¶1–¶4 `lock()` behaves as if by `pm->lock()`, after which `owns` is true. It has two error conditions, on which it throws `system_error`:

- ¶4.1 `pm` is null: `operation_not_permitted`;
- ¶4.2 `owns` is already true on entry: `resource_deadlock_would_occur`.

`try_lock` (¶5–¶10), `try_lock_until` (¶11–¶16) and `try_lock_for` (¶17–¶22) have the same two error conditions.

¶23–¶26 `unlock()` reports `operation_not_permitted` if `owns` is false on entry.

```cpp run title="unique-lock-errors.cpp" ok
#include <cstdio>
#include <mutex>
#include <system_error>

int main() {
  std::mutex m;
  std::unique_lock lk(m, std::defer_lock);
  try {
    lk.unlock();                 // unlocking when not held
  } catch (const std::system_error& e) {
    std::printf("%d\n", e.code() == std::errc::operation_not_permitted);         // 1
  }
  lk.lock();
  try {
    lk.lock();                   // locking again when already held
  } catch (const std::system_error& e) {
    std::printf("%d\n", e.code() == std::errc::resource_deadlock_would_occur);   // 1
  }
}
```

Doing the same things directly on a `std::mutex` is UB: `lock` when already held, or `unlock` when not held, both violate the preconditions in [[thread.mutex.requirements]]. `unique_lock` remembers in `owns` whether it holds the lock, so it can turn these errors into defined exceptions.

### Modifiers and observers [thread.lock.unique.mod] [thread.lock.unique.obs]

[thread.lock.unique.mod] ¶2–¶3 `release()` sets `pm` to null and `owns` to false, returning the old `pm`. It does not unlock: the lock previously held is from then on the caller's responsibility to `unlock()` manually.

There is also `swap`, and the observers `owns_lock()` and `explicit operator bool()` (both return `owns`) and `mutex()` (returns `pm`).

## shared_lock: unique_lock for shared locks [thread.lock.shared] {{c++14}}

`shared_lock` has the same structure as `unique_lock`; the difference is that it acquires a shared lock: locking calls `lock_shared`, `try_lock_shared` and so on, and destruction calls `unlock_shared`. Readers of the reader-writer lock `std::shared_mutex` are usually written like this:

```cpp run ok
#include <map>
#include <shared_mutex>
#include <string>

std::shared_mutex rw;
std::map<std::string, int> table;

int lookup(const std::string& k) {
  std::shared_lock lk(rw);           // several readers may hold it at once
  auto it = table.find(k);
  return it == table.end() ? -1 : it->second;
}

void update(const std::string& k, int v) {
  std::unique_lock lk(rw);           // the writer has exclusive access
  table[k] = v;
}

int main() { update("a", 1); return lookup("a") == 1 ? 0 : 1; }
```

[thread.lock.shared.general] ¶1 The lifetime requirement is the same as for `unique_lock`; the template argument must meet *Cpp17SharedLockable*. ¶2 Note 1 points out that `shared_lock<Mutex>` meets *Cpp17Lockable*, and its `lock()` acquires a shared lock. So a `shared_lock` can be passed to `condition_variable_any::wait`, and what is released during the wait and reacquired on waking is the shared lock.

The other subclauses correspond one-to-one with `unique_lock`. [thread.lock.shared.cons] ¶7 The precondition of the `adopt_lock` version is that the calling thread already holds a shared lock on `m`; the error conditions in [thread.lock.shared.locking] are the same as for `unique_lock`.

## Generic locking algorithms [thread.lock.algorithm]

Both function templates take at least two arguments, each of whose types must meet *Cpp17Lockable* (¶1, ¶4). A suitably instantiated `unique_lock` meets this requirement.

### std::try_lock (¶1–¶3)

¶2 `std::try_lock(l1, l2, ...)` calls `try_lock()` on each argument in order, starting with the first, until all succeed or one fails (returns `false` or throws). As soon as one fails, `unlock()` is called on the arguments already locked, and no further calls are made.

¶3 Returns `-1` if all succeed, otherwise the 0-based index of the argument that failed.

### std::lock (¶4–¶5)

!!! std
    The sequence of calls does not result in deadlock, but is otherwise unspecified.

¶5 `std::lock(l1, l2, ...)` locks all its arguments via some sequence of calls to `lock()`, `try_lock()` and `unlock()` on them. The sequence of calls does not result in deadlock but is otherwise unspecified {{unspec}}. Note 3 mentions that an algorithm such as try-and-back-off can be used. If a call to `lock()` or `try_lock()` throws, the arguments already locked are unlocked.

The no-deadlock promise holds for all threads that lock the same set of mutexes with `std::lock` or `scoped_lock`, regardless of the order in which they pass them. Another thread that locks them one by one in its own order with `lock_guard` can still deadlock with them.

!!! impl "libc++'s algorithm (`<mutex>`)"
    With two arguments, `std::lock` loops: lock `l0` blocking, then `try_lock` `l1`; if that succeeds it returns, otherwise it unlocks `l0` and yields the CPU; then the other way round: lock `l1` blocking and try `l0`.

    With more arguments, each round locks one argument blocking and then calls `std::try_lock` on the rest. If the j-th fails, everything is released, and the next round blocks on the j-th first. That is, a thread always blocks waiting on the mutex that made it fail in the previous round, rather than spinning in retries. This algorithm does not deadlock, but under heavy contention it may retry for many rounds.

## Common misconceptions

!!! pitfall "`std::unique_lock<std::mutex>(m);` locks m"
    Per [[dcl.ambig.res]], this statement is a declaration: it declares a default-constructed `unique_lock<mutex>` variable named `m`, shadowing the outer `m`, and locks nothing.

    ```cpp title="vexing-lock.cpp" ok
    #include <mutex>
    std::mutex m;
    int shared;
    void f() {
      std::unique_lock<std::mutex>(m);   // declares a local variable named m
      ++shared;                          // not protected
    }
    void g() {
      std::scoped_lock{m};               // a temporary: unlocked at the semicolon
      ++shared;                          // not protected either
    }
    int main() { f(); g(); }
    ```

    Both functions are well-formed; the locks just have no effect. Clang 23 gives a `-Wvexing-parse` warning for `f`; libc++ marks `scoped_lock`'s constructor `[[nodiscard]]`, so `g` gets a warning too. Naming the lock object avoids both mistakes: `std::scoped_lock lk(m);`.

!!! pitfall "A lock can outlive its mutex"
    ```cpp
    std::unique_lock<std::mutex> make_lock() {
      std::mutex m;
      return std::unique_lock(m);   // after return m is destroyed but the lock still refers to it: UB
    }
    ```
    All four locks require the referenced lockable object to exist throughout the lock's lifetime.

!!! pitfall "`release()` unlocks"
    `release()` only makes the `unique_lock` let go; the lock is still held. If the caller forgets to `unlock()` manually, the thread ends while holding the mutex, which is UB.

## Questions

!!! question "Question 1"
    What happens with `std::lock(m, m)`, passing the same `std::mutex` twice?

<details markdown="1">
<summary>Answer</summary>

UB. The algorithm will call `try_lock()` or `lock()` on `m` while already holding `m`, violating `std::mutex`'s precondition that the calling thread does not already own the mutex ([[thread.mutex.requirements]]). `std::scoped_lock lk(m, m);` is the same.
</details>

!!! question "Question 2"
    Why does `lock_guard`'s destructor not check whether the lock is held?

<details markdown="1">
<summary>Answer</summary>

Because it always holds the lock throughout its lifetime (¶1). The ordinary constructor either locks successfully or throws, in which case the object is not fully constructed and the destructor does not run; the precondition of the `adopt_lock` version guarantees the calling thread already holds the lock; and it has no member function that could unlock midway.
</details>

## Summary

| | How long it holds the lock | Movable | Can unlock/lock midway | Multiple mutexes | Misuse |
|---|---|---|---|---|---|
| `lock_guard` | entire lifetime | no | no | no | no such operations |
| `scoped_lock` | entire lifetime | no | no | yes (`std::lock`) | no such operations |
| `unique_lock` | recorded in `owns` | yes | yes | can be passed to `std::lock` | throws `system_error` |
| `shared_lock` | recorded in `owns` (shared lock) | yes | yes | can be passed to `std::lock` | throws `system_error` |
