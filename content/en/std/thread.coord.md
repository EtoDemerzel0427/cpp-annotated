---
title: Latches and barriers
summary: "The two C++20 thread coordination types, the single-use latch and the phased, reusable barrier: their preconditions, synchronization guarantees, which thread runs the completion function, and calling arrive and wait separately."
updated: 2026-10-19
---

!!! tldr
    - `latch` is a single-use countdown: `count_down` decrements the count and `wait` waits for it to reach zero. Once it reaches zero it cannot be reset.
    - `barrier` is reused phase by phase: in each phase, once all participants have arrived, the completion function runs once, then the count resets automatically and the next phase begins.
    - Both guarantee that writes made before arriving are visible to threads after their wait returns. A barrier's completion function also sees the writes of all participants in that phase.
    - Decrementing too much is UB: the decrement of `count_down` must not exceed the remaining count, and `arrive` must not exceed the remaining count of the current phase.
    - The completion function must be `noexcept`, and while it runs no member of the barrier other than `wait` may be called.

## Two coordination types [thread.coord.general] {{c++20}}

```cpp run title="latch-start-gate.cpp" ok
#include <cstdio>
#include <latch>
#include <thread>
#include <vector>

int main() {
  constexpr int N = 4;
  std::latch start{1};           // start gate: the main thread releases all workers at once
  std::latch done{N};            // finish line: wait until all workers are done
  int results[N] = {};
  std::vector<std::jthread> ts;
  for (int i = 0; i < N; ++i)
    ts.emplace_back([&, i] {
      start.wait();              // wait for the main thread's signal
      results[i] = i * i;        // each writes its own element
      done.count_down();
    });
  start.count_down();            // signal
  done.wait();                   // all writes before each count_down are visible after this
  int sum = 0;
  for (int r : results) sum += r;
  std::printf("%d\n", sum);      // 0 + 1 + 4 + 9 = 14
}
```

¶1 [thread.coord] defines two coordination types, `latch` and `barrier`, for concurrent computations carried out jointly by several threads. Both solve the problem of waiting until N participants have arrived before continuing; they differ in whether they can be reused:

| | `latch` | `barrier` |
|---|---|---|
| Number of uses | Once; cannot be reset after the count reaches zero | Many; resets automatically after each phase |
| Who decrements | Any thread, any number of times, by any amount | The participants of the phase, usually once each |
| Waiters vs. decrementers | Can differ, e.g. the main thread only waits | Usually the same (`arrive_and_wait`) |
| Callback on completion | None | The completion function, run exactly once per phase |

## latch [thread.latch]

[thread.latch.general] ¶1 A latch lets any number of threads block until an expected number of threads arrive via `count_down`. The expected count is set at creation. A latch is a single-use object: once the count reaches zero it cannot be used again.

[thread.latch.class] ¶1 A latch maintains an internal counter `counter`. ¶2 Concurrent calls to member functions other than the destructor do not introduce data races. ¶3 `max()` returns the maximum count the implementation supports, and ¶4 the constructor's precondition is `0 <= expected <= max()`.

### count_down (¶7–¶11)

```cpp
void count_down(ptrdiff_t update = 1);
```

¶8 Atomically decrements `counter` by `update`; if it reaches zero, unblocks all threads blocked on this latch.

¶7 Preconditions: `update >= 0` and `update <= counter`. So over-decrementing is UB: if a latch is initialized to 4 and five threads each call `count_down()` once, the fifth call violates the precondition.

¶9 Every `count_down` [[g:strongly-happens-before|strongly happens before]] the return of every call it unblocks, not only the one that brings the count to zero. So in the opening example, the result each worker writes before `count_down` is visible to the main thread after `done.wait()` returns.

### Waiting (¶12–¶16)

¶13 `wait()` returns immediately if the count is zero; otherwise it blocks until some `count_down` brings the count to zero.

¶12 `try_wait()` returns `false` with very low probability, otherwise `counter == 0`. That is, it may return `false` spuriously, but it never returns `true` before the count reaches zero.

¶16 `arrive_and_wait(update)` is equivalent to `count_down(update); wait();`.

!!! impl "latch in libc++"
    libc++'s `latch` contains only one `atomic<ptrdiff_t>`. `count_down` is `fetch_sub(update, release)`, calling `notify_all()` when the count reaches zero; `wait` reads the count with acquire.

    Each `fetch_sub` is a read-modify-write operation, so every `count_down` heads a release sequence that contains all later `fetch_sub`s ([[intro.races#5]]). The acquire read that finally sees 0 therefore synchronizes with every `count_down`, which is why ¶9 holds for every call.

## barrier [thread.barrier]

[thread.barrier.general] ¶1 The lifetime of a barrier consists of a sequence of **barrier phases**. Each phase allows at most an expected number of threads to block until the expected number of threads arrive. Note 1 says it is useful for repeated tasks handled by multiple threads.

```cpp run title="barrier-phases.cpp" ok
#include <barrier>
#include <cstdio>
#include <latch>
#include <thread>
#include <vector>

int main() {
  constexpr int N = 3;
  int phase = 0;
  int partial[N] = {};
  std::barrier sync(N, [&]() noexcept {            // completion function: runs once per phase
    std::printf("phase %d: %d %d %d\n", phase, partial[0], partial[1], partial[2]);
    ++phase;
  });
  std::latch done(N);
  std::vector<std::jthread> ts;
  for (int id = 0; id < N; ++id)
    ts.emplace_back([&, id] {
      for (int round = 0; round < 2; ++round) {
        partial[id] = (round + 1) * 10 + id;       // written before arriving, visible to the completion function (¶14)
        sync.arrive_and_wait();                    // after return, the completion function's writes are visible (¶3)
      }
      done.count_down();
    });
  done.wait();
  std::printf("all done after %d phases\n", phase);
}
```

Output:

```text
phase 0: 10 11 12
phase 1: 20 21 22
all done after 2 phases
```

### Phases ([thread.barrier.class] ¶1–¶4)

¶1 Each phase consists of three steps:

- ¶1.1 each call to `arrive` or `arrive_and_drop` decrements the expected count;
- ¶1.2 after the expected count reaches zero, some thread runs the **completion step** exactly once, inside its `arrive`, `arrive_and_drop` or `wait` call; if no thread calls `wait`, whether the completion step runs is implementation-defined {{impl}};
- ¶1.3 when the completion step finishes, the expected count is reset to the `expected` given at construction (possibly reduced by `arrive_and_drop`), and the next phase starts.

¶2 Each phase has a **phase synchronization point**. Threads that arrive during the phase can call `wait` to block on this point until the completion step has run.

¶3 The completion step first calls the completion function (equivalent to `completion()`), then unblocks all threads blocked on the phase synchronization point. The end of the completion step strongly happens before the return of every call it unblocks.

¶3 also says: if `CompletionFunction` is not the default type, calling any member function of the barrier other than `wait` while the completion step is in progress is undefined behavior {{ub}}. ¶4 Concurrent calls to member functions other than the destructor do not introduce data races; `arrive` and `arrive_and_drop` execute atomically.

Combined with the synchronization rule of paragraph 14 (see below), this tells us about the completion function:

- It runs on one of the participant threads, inside that thread's `arrive`, `arrive_and_drop` or `wait` call. Usually that is the last thread to arrive, but a program cannot rely on that.
- It can safely read data that all participants wrote before `arrive`, which makes it suitable for aggregation.
- After returning from `arrive_and_wait`, participants see the data the completion function wrote, such as the input prepared for the next round.

In the example, the completion function reads `partial` and writes `phase`, and the participants write `partial` in the next round; paragraphs 3 and 14 order all these accesses, so there is no data race.

### Type requirements (¶5–¶7)

¶5 `CompletionFunction` must meet *Cpp17MoveConstructible* and *Cpp17Destructible*, and `is_nothrow_invocable_v<CompletionFunction&>` must be true. The completion function runs inside another thread's `arrive` call, where an exception it throws would have nowhere sensible to go, so throwing is not allowed.

¶6 The default `CompletionFunction` is an unspecified type that is default constructible and whose invocation has no effects. ¶7 `arrival_token` is an unspecified movable type.

### Construction and arrival (¶8–¶29)

¶9–¶10 The precondition of the constructor `barrier(expected, f)` is `0 <= expected <= max()`. It sets the initial expected count of every phase to `expected` and starts the first phase. Note 1 points out that a barrier with `expected` equal to 0 can only be destroyed.

¶12–¶13 `arrive(update)` constructs an `arrival_token` associated with the phase synchronization point of the current phase, then decrements the expected count by `update`. The precondition is `update > 0` and not more than the remaining expected count of the current phase. ¶14 A call to `arrive` strongly happens before the start of the completion step of the current phase.

¶19–¶20 `wait(std::move(token))` blocks on the phase synchronization point associated with the token until that phase's completion step has run. The precondition of ¶19 requires the token to belong to the current phase or the immediately preceding one. Note 3 points out that if the token belongs to a phase that has already completed, it returns immediately.

¶23 `arrive_and_wait()` is equivalent to `wait(arrive())`.

With `arrive` and `wait` separate, a participant can announce its arrival, do some work that does not depend on the others' results, and then wait:

```cpp
auto tok = bar.arrive();     // announce that my part of this phase is done
do_unrelated_work();         // work that does not depend on other participants
bar.wait(std::move(tok));    // only now are the others' results needed
```

A token can only belong to the current phase or the previous one. The phase can advance once before the token is used, but not twice: the next phase cannot complete while this participant has not yet arrived in it.

¶24–¶25 `arrive_and_drop()` first decrements by one the initial expected count of all subsequent phases, then decrements the expected count of the current phase by one; it amounts to a final arrival after which the thread no longer participates. The precondition is that the expected count of the current phase is greater than zero. ¶26 The synchronization rule is the same as for `arrive`.

!!! impl "libc++'s barrier and ThreadSanitizer"
    libc++'s `barrier` is a tree barrier: arriving threads combine level by level in a tree laid out by cache line, to reduce contention on any single cache line. The main body of the tree algorithm lives in the libc++ shared library. The thread that wins the last level runs the completion function inside its own `arrive` call, then writes the new phase number with release and calls `notify_all()`; waiters read the phase number with acquire.

    Running the barrier example above with `-fsanitize=thread`, ThreadSanitizer may report a data race between the completion function's read of `partial` and the participants' writes. Under ¶14 this is a false positive: the synchronization between the participants' writes and the completion function happens inside the shared library, which is not instrumented by TSan, so TSan cannot see it. `latch` is implemented entirely in headers and does not show this false positive.

## Common misconceptions

!!! pitfall "A latch can be reset"
    When every round needs everyone to arrive, use `barrier`. With `latch` you have to create a new one each round, and make sure all threads are done with the old one before destroying it.

!!! pitfall "The completion function may call other members of the barrier"
    For a non-default `CompletionFunction`, calling any member function other than `wait` during the completion step is UB (¶3). The completion function should only do work unrelated to the barrier itself, such as aggregating results and preparing the next round.

!!! pitfall "One extra participant does no harm"
    With `barrier(3)` and four threads calling `arrive_and_wait()`, the fourth arrival either exceeds the remaining count of the current phase, violating the precondition of ¶12, or is counted toward the next phase, putting the phases out of step. A participant that leaves early should call `arrive_and_drop()`.

## Summary

- `latch`: a single-use counter; `count_down` must not over-decrement; every `count_down` strongly happens before the return of the woken threads; `try_wait` may spuriously return `false`.
- `barrier`: reused phase by phase; each phase's completion function runs exactly once, on some participant thread; `arrive` strongly happens before the start of the completion step, and the end of the completion step strongly happens before the waiters return.
- The completion function must be `noexcept`, and while it runs no member of the barrier other than `wait` may be called.
