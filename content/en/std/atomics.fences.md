---
title: Fences
summary: "atomic_thread_fence and atomic_signal_fence: how fences combine with relaxed atomic operations to establish synchronization, what a seq_cst fence guarantees beyond an acq_rel fence, and the signal fence, which constrains only the compiler."
updated: 2026-10-19
---

!!! tldr
    - Fences separate synchronization from particular atomic operations: the atomic operations can be relaxed, and synchronization is provided by fences in the same thread.
    - A release fence goes before the write to the atomic variable, and an acquire fence goes after the read; in between there must be a pair of atomic operations, one writing M and one reading that write, or the fences establish nothing.
    - One acquire fence can supply acquire semantics for several preceding relaxed reads at once.
    - A `seq_cst` fence enters the single total order S and can forbid store→load reordering; an `acq_rel` fence cannot.
    - `atomic_signal_fence` constrains only the compiler, is effective only with respect to signal handlers in the same thread, and cannot be used between threads.

## One fence serving several flags

```cpp run title="fence-fan-in.cpp" ok
#include <atomic>
#include <cassert>
#include <thread>

int part[3];
std::atomic<bool> done[3];

int main() {
  std::jthread w[3];
  for (int i = 0; i < 3; ++i)
    w[i] = std::jthread([i] {
      part[i] = (i + 1) * 10;
      done[i].store(true, std::memory_order::release);  // A
    });
  for (auto& d : done)
    while (!d.load(std::memory_order::relaxed)) {}      // X
  std::atomic_thread_fence(std::memory_order::acquire); // B
  assert(part[0] + part[1] + part[2] == 60);            // OK
}
```

The main thread first confirms with relaxed reads that all three flags are set, then executes one acquire fence. For each `i`, the release store on `done[i]` synchronizes with this fence, so all three writes to `part[i]` happen before the assertion.

You could do without the fence by writing all three loads as `acquire`. On x86 the two versions generate the same code; on ARM the difference is three acquire loads versus three plain loads plus one barrier instruction. Another use is paying for synchronization only when needed: read with relaxed first, and add the acquire fence only after reading the expected value.

The fundamental difference between a fence and an atomic operation is that a fence has no associated memory location ([[intro.races#3]]); it can only take effect by means of a pair of reads and writes on some atomic object M. The three rules below specify the exact conditions.

## The three synchronization rules (¶1–¶4)

¶1 A **fence** is a synchronization primitive that may have acquire semantics, release semantics, or both, called an **acquire fence** and a **release fence** respectively.

The three rules have the same shape; they differ only in which end uses a fence and which uses an atomic operation (sb in the table means sequenced before):

| Paragraph | Release end | Acquire end | The link in between |
|---|---|---|---|
| ¶2 | release fence A | acquire fence B | A sb X, X modifies M; Y reads M, Y sb B |
| ¶3 | release fence A | acquire operation B on M | A sb X, X modifies M; B reads the value written by X |
| ¶4 | release operation A on M | acquire fence B | X reads the value written by A, X sb B |

The example above uses ¶4, three times. The text of ¶2:

!!! std
    A release fence A synchronizes with an acquire fence B if there exist atomic operations X and Y, where Y is not an atomic modify-write operation, both operating on some atomic object M, such that A is sequenced before X, X modifies M, Y is sequenced before B, and Y reads the value written by X or a value written by any side effect in the hypothetical release sequence X would head if it were a release operation.

There are three details.

**The direction is determined by the fence's position.** A release fence must be before the write to M (A sb X), and an acquire fence must be after the read of M (Y sb B). Put them the other way round and no relation is established.

**The hypothetical release sequence.** The **release sequence** headed by a release operation is the contiguous run of read-modify-write operations that immediately follow it in the modification order ([[intro.races#5]]); reading the value written by any of them synchronizes just as reading the head's write would. The X in ¶2 and ¶3 may be relaxed and so has no release sequence of its own, so the standard supposes it were a release operation and judges by the sequence it would head. In ¶4, A is itself a release operation, so its real release sequence is used directly.

**Y in ¶2 cannot be an atomic modify-write operation** {{c++26}}. Atomic modify-write operations (such as `store_add`) are read-modify-write operations with weaker synchronization requirements. The note in [[atomics.order#12]] explains that they are meant to be implemented with hardware mechanisms not ordered by acquire fences. If one were allowed to act as the Y in ¶2, implementations would have to let a following acquire fence order it, defeating the purpose of introducing it.

!!! impl "ThreadSanitizer and fences"
    TSan's modeling of `atomic_thread_fence` is incomplete. Running `fence-fan-in.cpp` with `-fsanitize=thread`, Clang 23's TSan reports a `data race` on `part`, which is a false positive. For code that depends on fences, TSan's silence does not prove correctness, and its reports do not prove a bug.

## atomic_thread_fence (¶5)

¶5 `atomic_thread_fence(order)`, according to the value of `order`:

- ¶5.1 `relaxed`: has no effects;
- ¶5.2 `acquire`: is an acquire fence;
- ¶5.3 `release`: is a release fence;
- ¶5.4 `acq_rel`: is both an acquire fence and a release fence;
- ¶5.5 `seq_cst`: is a sequentially consistent acquire and release fence.

`relaxed` is a valid argument too, which helps generic code: a function taking a `memory_order` parameter can call `atomic_thread_fence(order)` unconditionally, and it naturally degenerates to a no-op when the caller passes `relaxed`.

### What a seq_cst fence additionally guarantees

<div class="compare" markdown="1">

```cpp
// thread 1 (x and y initially 0)
x.store(1, relaxed);
atomic_thread_fence(seq_cst); // F1
r1 = y.load(relaxed);
```

```cpp
// thread 2
y.store(1, relaxed);
atomic_thread_fence(seq_cst); // F2
r2 = x.load(relaxed);
```

</div>

The question is whether `r1 == 0 && r2 == 0` is possible. If both fences are `seq_cst`, this outcome is forbidden.

A `seq_cst` fence is a `memory_order::seq_cst` operation, participates in the single total order S of all seq_cst operations, and is subject to the constraints of [[atomics.order#4]]. Suppose `r2 == 0`, i.e. thread 2's load reads the initial value of x; then that load is coherence-ordered before `x.store(1)` on x. F2 happens before the load, and `x.store(1)` happens before F1, so by ¶4.4 F2 precedes F1 in S. Symmetrically, `r1 == 0` means F1 precedes F2 in S. Both cannot hold, so at least one of `r1` and `r2` is 1.

With `acq_rel` fences this does not work. They are not in S; the release half constrains only writes before it and the acquire half only reads after it, leaving no constraint between an earlier write and a later read. This is the key difference between an `acq_rel` fence and a `seq_cst` fence.

## atomic_signal_fence (¶6–¶7)

¶6 `atomic_signal_fence(order)` is equivalent to `atomic_thread_fence(order)`, except that the resulting ordering constraints are established only between a thread and a signal handler executed in the same thread.

¶7 Note 1: it can be used to specify the order in which actions performed by the thread become visible to the signal handler. It inhibits compiler optimizations and reorderings just like `atomic_thread_fence`, but does not emit hardware fence instructions.

The reason is that a signal handler runs on the interrupted thread, and a CPU always sees its own instructions in program order; only the compiler can scramble the order. Compiled at `-O2` on Apple Silicon, `atomic_signal_fence(seq_cst)` generates no instruction at all, while `atomic_thread_fence(seq_cst)` generates a `dmb ish`.

```cpp run title="signal-fence.cpp" ok
#include <atomic>
#include <csignal>
#include <cstdio>

int data = 0;
std::atomic<bool> ready{false};   // a lock-free atomic, usable in a signal handler
std::atomic<int> seen{-1};

extern "C" void handler(int) {
  if (ready.load(std::memory_order::relaxed)) {
    std::atomic_signal_fence(std::memory_order::acquire);
    seen.store(data, std::memory_order::relaxed);
  }
}

int main() {
  std::signal(SIGUSR1, handler);
  data = 42;
  std::atomic_signal_fence(std::memory_order::release);
  ready.store(true, std::memory_order::relaxed);
  std::raise(SIGUSR1);
  std::printf("%d\n", seen.load());   // 42
}
```

Using `std::raise` to trigger the signal synchronously is only for demonstration. The fences are really needed for asynchronous signals; for example, a timer signal may interrupt the main thread between any two statements. Without the two fences, the compiler could move `data = 42` after `ready.store`, and if the signal arrived right between them, the handler would see `ready == true` with `data == 0`.

## Common misconceptions

!!! pitfall "Two seq_cst fences synchronize two threads by themselves"
    Fences establish synchronization only when there is a pair of atomic operations in between, one writing M and one reading that write. Two threads each calling `atomic_thread_fence(seq_cst)`, with no atomic variable passing information between them, produce no happens before relation at all; precedence in S does not itself constitute happens before.

!!! pitfall "An acquire fence before the read works too"
    ```cpp
    std::atomic_thread_fence(std::memory_order::acquire);  // wrong: before the read
    while (!flag.load(std::memory_order::relaxed)) {}
    use(data);                                              // data race
    ```
    ¶2 and ¶4 require the read operation to be sequenced before the acquire fence.

!!! pitfall "atomic_signal_fence can serve as a cheap thread fence"
    It emits no hardware barrier. Using it to synchronize two threads breaks on weakly ordered hardware such as ARM; on x86 it may happen to work because x86's memory model is strong to begin with.

## Questions

!!! question "Question"
    Thread 1 executes release fence A, then `x.store(1, relaxed)`; thread 2 executes `x.fetch_add(1, relaxed)`, reading 1 and writing 2; thread 3 executes `x.load(relaxed)`, reads 2, then executes acquire fence B. Does A synchronize with B?

<details markdown="1">
<summary>Answer</summary>

Yes. By ¶2, X is `x.store(1)` and Y is thread 3's load. If X were a release operation, the release sequence it would head includes the immediately following read-modify-write `fetch_add`; Y reads the value written by `fetch_add`, so the condition is met. Y is a plain load, not an atomic modify-write operation.

If `fetch_add` were replaced with C++26's `store_add`, it is still a read-modify-write operation ([[atomics.order#12]]) and still in the hypothetical release sequence, so the conclusion is the same. ¶2 excludes only the case where Y itself is a modify-write operation.
</details>

## Summary

| Fence | Effect |
|---|---|
| `release` | when some later atomic write is read, synchronizes with the acquire fence or acquire operation on the reading side (¶2, ¶3) |
| `acquire` | when some earlier atomic read read a write after a release fence or the write of a release operation, synchronizes with it (¶2, ¶4) |
| `acq_rel` | both, but does not forbid store→load reordering |
| `seq_cst` | both, and enters the total order S, forbidding store→load reordering ([[atomics.order#4]]) |
| `atomic_signal_fence` | as above, but only with respect to signal handlers in the same thread, and only constrains the compiler |
