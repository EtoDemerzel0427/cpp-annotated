---
title: Waiting and notifying
summary: "How atomic wait, notify_one and notify_all work: wait compares by value and handles spurious wakeups itself, notification must come after the modification, notification itself does not synchronize, and intermediate values can be missed."
updated: 2026-10-19
---

!!! tldr
    - `a.wait(old)` blocks until the value of `a` is no longer equal to `old`; spurious wakeups are absorbed by a loop inside the function, and when it returns it has definitely read a different value.
    - Modify first, then notify: as long as the modification happens before the notification, a waiter that saw the old value before the modification and went to sleep is guaranteed to be woken by that notification; no wakeup is lost.
    - Notification is not a synchronization operation. Visibility of data comes from the synchronization between the acquire load inside `wait` and the modifier's release store.
    - When the value goes through a brief change such as 0→1→0, a waiter may miss it entirely (the ABA problem); to observe every change, use an incrementing counter.

## A minimal example

Before C++20, a thread waiting for an atomic variable to take some value either spun in a polling loop, wasting CPU, or paired it with a `mutex` and a `condition_variable`, and also had to put the modification of the atomic variable inside the lock, or else wakeups could be lost. [[P1135R6]] added `wait` and `notify` to atomic types, with semantics close to Linux's futex.

```cpp run title="wait-notify.cpp" ok
#include <atomic>
#include <cassert>
#include <thread>

std::atomic<int> state{0};
int payload = 0;

int main() {
  std::thread consumer([] {
    state.wait(0, std::memory_order::acquire);  // returns only once the value is no longer 0
    assert(payload == 42);                      // OK
  });
  payload = 42;
  state.store(1, std::memory_order::release);   // modify first
  state.notify_one();                           // then notify
  consumer.join();
}
```

`consumer` blocks until `state` is no longer 0. The visibility of `payload` comes from the synchronization between `store(release)` and the `load(acquire)` inside `wait` that reads 1 ([[atomics.order#2]]), and has nothing to do with `notify_one`. ThreadSanitizer reports nothing.

## Two kinds of operation (¶1–¶3)

¶1 **Atomic waiting operations** and **atomic notifying operations** provide a mechanism to wait for the value of an atomic object to change, more efficiently than polling. A waiting operation may block until it is unblocked by a notifying operation, according to each function's *Effects*.

¶2–¶3 Two notes list which functions belong to these two kinds:

| Waiting operations | Notifying operations |
|---|---|
| `atomic<T>::wait`, `atomic_ref<T>::wait` | the `notify_one` and `notify_all` of both |
| `atomic_flag::wait` | `atomic_flag::notify_one`, `notify_all` |
| the non-member `atomic_wait(_explicit)`, `atomic_flag_wait(_explicit)` | the non-member `atomic_notify_*`, `atomic_flag_notify_*` |

These lists are only notes. The normative classification is in each function's *Remarks*, for example [[atomics.types.operations#32]]. The `wait` of `atomic<shared_ptr<T>>` is among them too ([[util.smartptr.atomic]]).

## What wait does

Taking `atomic<T>` as the example, [[atomics.types.operations#31]] specifies that `wait(old, order)` repeatedly performs three steps:

1. Evaluate `load(order)` and compare the value representation of the result with that of `old`;
2. if they are not equal, return;
3. block until unblocked by a notifying operation or spuriously unblocked, then go back to step 1.

Three things follow:

- Spurious wakeups are handled by `wait` itself: after waking it compares again. The caller does not need an extra loop as with `condition_variable::wait`.
- The memory order applies to the load in step 1. In `wait(old, acquire)`, the load that reads the new value is an acquire operation. The precondition is the same as for `load`: `order` cannot be `release` or `acq_rel`.
- What is compared is the value representation, by the same rule as `compare_exchange`. Floating-point `+0.0` and `-0.0` compare equal in value but differ in representation; see [[atomics.types.operations#28]].

`notify_one()` unblocks at least one waiting operation that is eligible to be unblocked by this call ([[atomics.types.operations#34]]); `notify_all()` unblocks all eligible ones (¶37). What "eligible" means is defined by ¶4 of this subclause.

## Who can be woken (¶4)

¶4 A waiting operation on atomic object M is **eligible to be unblocked** ([[g:eligible-to-be-unblocked]]) by a notifying operation on M if there exist side effects X and Y on M such that:

- ¶4.1 the waiting operation blocked after observing the result of X;
- ¶4.2 X precedes Y in the modification order of M;
- ¶4.3 Y happens before the call to the notifying operation.

In other words: if a waiter went to sleep after seeing some value, and the notifier had written a newer value before notifying, that notification must be able to wake it.

This definition rules out lost wakeups without any lock. Consider this interleaving:

```text
waiter                          notifier
v = a.load()     // reads X = 0
                                a.store(1)      // Y
                                a.notify_one()
(v == 0, about to block)
block
```

With a `condition_variable` and no lock, this is exactly the classic lost wakeup: the notification happens before the waiter has actually gone to sleep. By ¶4, the waiter blocked after observing X, X precedes Y, and Y happens before the notification, so it is eligible to be woken, even though in time the notification came before it blocked. Implementations must achieve this; the usual way is for the kernel's wait-on-address call to recheck the value atomically before sleeping.

Conversely, in the following two cases the waiter is not eligible to be woken and may sleep forever:

- the notifier calls `notify_one()` without modifying M, so there is no Y;
- the modification happens in another thread with no happens before relation to the notifying thread.

## Waiting for a particular value

`wait(old)` can only express "not equal to `old`". To wait until `stage == 3`, write the loop yourself, passing the value just seen to `wait` each time:

```cpp run title="wait-for-value.cpp" ok
#include <atomic>
#include <cstdio>
#include <thread>

std::atomic<int> stage{0};

void wait_until(int target) {
  int v = stage.load(std::memory_order::acquire);
  while (v != target) {
    stage.wait(v, std::memory_order::acquire);
    v = stage.load(std::memory_order::acquire);
  }
}

int main() {
  std::thread t([] { wait_until(3); std::puts("stage 3"); });
  for (int i = 1; i <= 3; ++i) {
    stage.store(i, std::memory_order::release);
    stage.notify_all();
  }
  t.join();
}
```

If the loop always called `stage.wait(0)`, then once the value became 1, every `wait(0)` would return immediately and the loop would degenerate into spinning.

## Intermediate values can be missed (¶1 Note 1)

Note 1 in ¶1 warns that programs are not guaranteed to observe transient atomic values; this is the **ABA problem**. A wait may continue to block even if the condition is only temporarily met.

For example, a waiter calls `a.wait(0)`; another thread does `a.store(1)`, then `a.store(0)`, then notifies. The waiter wakes, reads 0 again, which equals `old`, and keeps blocking; the fact that the value was once 1 is lost. When every change needs to be observed, use a monotonically increasing counter (a generation number), not a flag that returns to its original value.

## The implementation's view

!!! impl "libc++'s implementation on macOS (Clang 23)"
    The implementation of `wait` (`<__atomic/atomic_sync.h>`) has three phases: first 64 consecutive load-and-compare iterations; then more polling until about 4 microseconds have elapsed in total; finally a call to the platform wait function in the libc++ shared library to block.

    Blocking has two cases. When the type's size and alignment match libc++'s contention type (`int64_t` on macOS), it waits directly on the atomic object's address. Otherwise it uses a global wait table: the object's address is hashed to an `int64_t` counter in the table, the wait is on that counter, and `notify` increments the counter and then wakes. Different objects may hash to the same slot, causing extra spurious wakeups, which the loop in `wait` absorbs.

    The system calls on macOS are `os_sync_wait_on_address` and `os_sync_wake_by_address_any`/`_all`, which can be verified by inspecting the imported symbols of the libc++ shared library with `nm -u`.

    Practical conclusion: on macOS, waiting on `atomic<long long>` (i.e. `atomic_signed_lock_free`, [[atomics.alias]]) is the most direct; `atomic<int>` and `atomic<bool>` work too but go through the global table. The global table is in-process, so cross-process `wait`/`notify` on these types does not work. libc++'s ABI version 2 switches to deciding by size, so types of 4 or 8 bytes with unique object representations can all wait directly on the object's address; the default version 1 does not, for binary compatibility.

## Relation to other synchronization primitives

Most of C++20's other synchronization components can be implemented with `wait`/`notify`, and libc++ does exactly that:

- `counting_semaphore` ([[thread.sema]]): `wait(0)` when the count is 0;
- `latch` ([[thread.coord]]): `notify_all` when the counter reaches 0;
- `barrier`: waiters do `wait(old phase number)` on the phase number;
- with `atomic_flag` you can write a spin lock that does not burn CPU ([[atomics.flag]]).

## Common misconceptions

!!! pitfall "Notify first, modify afterwards"
    ```cpp
    flag.notify_one();
    flag.store(true);   // wrong: there is no Y yet at the time of notification
    ```
    ¶4.3 requires the modification to happen before the notification. Written this way, the waiter may never wake.

!!! pitfall "Using a relaxed wait to read data the other side published"
    `wait(old, relaxed)` returning only says the value changed; it establishes no synchronization. To read ordinary data the other side wrote before the modification, the `wait` must use `acquire` (or be followed by an acquire fence), and the modification must use `release`.

!!! pitfall "Notification brings visibility"
    `notify_one`/`notify_all` have no memory order parameter and no *Synchronization* clause. Notification decides only whether the waiter wakes up, not what it can see.

## Questions

!!! question "Question"
    Thread A executes `x.store(1, relaxed); x.notify_one();`, and thread B executes `x.wait(0, relaxed);`. Is B guaranteed to return? After returning, can it read an ordinary variable A wrote before the store?

<details markdown="1">
<summary>Answer</summary>

It is guaranteed to return. If B saw 0 before blocking (X is the initialization), A's store is Y, which comes after X in the modification order and is sequenced before the notification, so B is eligible to be woken (¶4); if B already saw 1, `wait` does not block at all.

But B cannot read that ordinary variable: both sides are relaxed, there is no synchronization, and the read is a data race. It works only if the store is changed to `release` and the wait to `acquire`.
</details>
