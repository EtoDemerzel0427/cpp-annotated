---
title: Order and consistency
summary: "What each memory_order value means: how release/acquire establish synchronization, the single total order S containing seq_cst operations and fences, why S need not be consistent with happens before, out-of-thin-air values, why read-modify-writes always read the latest value, and C++26's atomic modify-write operations; with measurements on Apple Silicon."
updated: 2026-10-19
---

!!! tldr
    - A release write synchronizes with an acquire read that reads its value, and ordinary writes before the write are visible to code after the read. No read of the value, no synchronization.
    - acquire/release do not prevent a store from being reordered with a later load; Dekker-style store→load ordering needs `seq_cst` on both sides, or a `seq_cst` fence in between.
    - All `seq_cst` operations and fences lie in a single total order S, but S need only be consistent with strongly happens before, and mixing with acquire/release can produce surprising results.
    - `relaxed` provides no ordering across variables but still guarantees atomicity and per-object coherence; read-modify-write operations always read the latest value in the modification order, so a relaxed counter never loses increments.
    - Specifying a disallowed memory order (such as `acquire` on a `store`) violates a precondition and is UB, not a compile error.

[[intro.races]] defines happens before, modification order and the coherence rules, but which atomic operations establish the synchronizes with relation is specified in this subclause. It is best to read [[intro.multithread]] first, which analyzes three classic litmus tests: message passing (MP), store buffering (SB) and IRIW.

## Starting with an example: message passing

```cpp run title="mp-acq-rel.cpp" ok
#include <atomic>
#include <cassert>
#include <thread>

int data = 0;
std::atomic<bool> ready{false};

int main() {
  std::thread producer([] {
    data = 42;                                         // ① ordinary write
    ready.store(true, std::memory_order::release);     // ② A: release
  });
  std::thread consumer([] {
    while (!ready.load(std::memory_order::acquire)) {} // ③ B: acquire, reads the true written by A
    assert(data == 42);                                // ④ OK
  });
  producer.join(); consumer.join();
}
```

① is sequenced before ②, ② synchronizes with ③, and ③ is sequenced before ④, so ① happens before ④, and ④ always reads 42. The synchronization between ② and ③ comes from ¶2 below.

Change both ② and ③ to `relaxed`, and there is no synchronization; with no happens before between ① and ④, they form a data race:

```cpp run title="mp-relaxed.cpp" ub
#include <atomic>
#include <thread>
int data = 0;
std::atomic<bool> ready{false};
int main() {
  int r = 0;
  std::thread t1([] {
    data = 42;
    ready.store(true, std::memory_order::relaxed);
  });
  std::thread t2([&r] {
    while (!ready.load(std::memory_order::relaxed)) {}
    r = data;              // UB: a data race with data = 42
  });
  t1.join(); t2.join();
  return r == 42 ? 0 : 1;
}
```

Compiled and run with `-fsanitize=thread` in our tests, ThreadSanitizer reports a `data race`.

## What each value means (¶1)

```cpp
namespace std {
  enum class memory_order : unspecified {
    relaxed = 0, acquire = 2, release = 3, acq_rel = 4, seq_cst = 5
  };
}
```

¶1 `memory_order` specifies the synchronization ordering of non-atomic memory, per the definitions in [[intro.multithread]]:

- ¶1.1 `relaxed`: no operation orders memory.
- ¶1.2 `release`, `acq_rel`, `seq_cst`: a store operation performs a **release operation** on the affected memory location.
- ¶1.3 `acquire`, `acq_rel`, `seq_cst`: a load operation performs an **acquire operation** on the affected memory location.

Read-modify-write (RMW) operations such as `fetch_add`, `exchange` and `compare_exchange` are both loads and stores, so both rules apply:

| Memory order | load | store | RMW |
|---|---|---|---|
| `relaxed` | no ordering | no ordering | no ordering |
| `acquire` | acquire | not allowed | the read half is acquire |
| `release` | not allowed | release | the write half is release |
| `acq_rel` | not allowed | not allowed | acquire plus release |
| `seq_cst` | acquire, and in S | release, and in S | both, and in S |

The disallowed combinations come from the preconditions of the individual operations; for example, [[atomics.types.operations#7]] specifies that the `order` of `store` can only be `relaxed`, `release` or `seq_cst`. Violating a precondition is UB, not a compile error:

```cpp title="bad-order.cpp" ub
#include <atomic>
std::atomic<int> a;
int main() {
  a.store(1, std::memory_order::acquire);   // UB: precondition violated
  int e = 0;
  a.compare_exchange_strong(e, 1, std::memory_order::relaxed,
                            std::memory_order::release);    // UB: failure cannot be release
}
```

libc++ uses `diagnose_if` to warn when the memory order is a constant; Clang 23 reports `warning: memory order argument to atomic operation is invalid [-Wuser-defined-warnings]` for both. When the memory order comes from a run-time variable, there is no warning.

The value 1 originally belonged to `consume`. C++26's [[P3475R2]] moved `memory_order::consume` to [[depr.atomics]] in Annex D; it can be used wherever `acquire` is allowed and means the same as `acquire` {{c++26}}. The accompanying dependency-ordering definitions in the core language (carries a dependency, dependency-ordered before) were removed along with it.

¶1 Note 1: `relaxed` atomic operations are relaxed with respect to memory ordering, but implementations must still guarantee that every atomic access to a given atomic object is indivisible with respect to all other atomic accesses to that object. What relaxed gives up is ordering with respect to other memory locations, not atomicity, and not coherence on a single object (the four coherence rules in [[intro.races#11]]–[[intro.races#14]]).

## release/acquire synchronization (¶2)

!!! std
    An atomic operation A that performs a release operation on an atomic object M synchronizes with an atomic operation B that performs an acquire operation on M and takes its value from any side effect in the release sequence headed by A.

¶2 An atomic operation A that performs a release operation on atomic object M synchronizes with an atomic operation B that performs an acquire operation on M and takes its value from some side effect in the release sequence headed by A. The release sequence consists of A and the subsequent RMW operations on M in its modification order ([[intro.races]]). All three conditions are required:

1. the same atomic object M;
2. A is a release, B is an acquire;
3. B actually reads the value written by A, or by some RMW after A.

The third is easy to overlook: if B reads an old value from before A, there is no synchronization and nothing can be inferred. That is why acquire reads almost always appear in a loop or branch that checks the value, like ③ above.

## coherence-ordered before (¶3)

¶3 defines the **coherence-ordered before** relation ([[g:coherence-ordered-before]]) between two atomic operations on the same atomic object M. A is coherence-ordered before B if:

- ¶3.1 A is a modification and B reads the value stored by A; or
- ¶3.2 A precedes B in the modification order of M; or
- ¶3.3 A and B are not the same RMW operation, and A reads the value stored by some modification X that precedes B in the modification order; or
- ¶3.4 there is a modification X such that A is coherence-ordered before X and X is coherence-ordered before B.

Intuitively, the modification order of M is a line. Each write has its own position on the line, and each read falls after the write it reads and before the next write. Coherence-ordered before is "earlier on this line". ¶3.3 excludes the same RMW because the X an RMW reads naturally precedes the value it writes itself, and this relation is not needed for that.

## The single total order S (¶4–¶7)

### Definition

¶4 is the definition of `seq_cst` as revised in C++20 by [[P0668R5]]. There is a single total order S on all `memory_order::seq_cst` operations (including fences) that satisfies the following constraints.

First, if A and B are both seq_cst operations and A strongly happens before B, then A precedes B in S.

Second, for every pair of atomic operations A and B on M where A is coherence-ordered before B:

- ¶4.1 if A and B are both seq_cst operations, A precedes B in S;
- ¶4.2 if A is a seq_cst operation and B happens before a seq_cst fence Y, A precedes Y in S;
- ¶4.3 if a seq_cst fence X happens before A and B is a seq_cst operation, X precedes B in S;
- ¶4.4 if a seq_cst fence X happens before A and B happens before a seq_cst fence Y, X precedes Y in S.

¶4.2–¶4.4 let seq_cst fences stand in for the non-seq_cst atomic operations around them in the total order. For example, if both threads execute a relaxed write, a seq_cst fence and a relaxed read, the SB outcome where both reads get 0 is still forbidden by ¶4.4: assuming both reads read the initial value lets you derive that each fence precedes the other in S, a contradiction.

¶5 Note 2: this definition ensures that S is consistent with the modification order of every atomic object. It also ensures that a seq_cst read A of M reads either the last modification of M preceding A in S, or some non-seq_cst modification that does not happen before any modification of M preceding A in S.

### S need not be consistent with happens before (¶6)

!!! std
    We do not require that S be consistent with "happens before". This allows more efficient implementation of `memory_order::acquire` and `memory_order::release` on some machine architectures.

¶6 Note 3: the standard does not require S to be consistent with happens before, which allows acquire/release to be implemented more efficiently on some architectures; the price is that they can produce surprising results when mixed with seq_cst accesses.

The first sentence of ¶4 uses strongly happens before ([[intro.races]]), not happens before; that is the relaxation Note 3 refers to. On architectures such as POWER, the common instruction mappings cannot guarantee that a happens before obtained through acquire/release synchronization is respected by S. The original C++11 definition required this, and as a result the standard disagreed with mainstream implementations. C++20 changed it to require consistency only with strongly happens before.

### seq_cst is sequentially consistent only when used throughout (¶7)

¶7 Note 4: `seq_cst` ensures sequential consistency only for programs that are free of data races and use exclusively `seq_cst` atomic operations. Any use of weaker ordering invalidates this guarantee. In many cases, seq_cst operations are reorderable with respect to other atomic operations performed by the same thread.

For example, in `x.store(1); r = y.load(memory_order::acquire);` the store is seq_cst but the load is not, and both the compiler and the hardware may let the load take effect before the store. Only when both are seq_cst, or a seq_cst fence sits between them, is store-then-load ordering guaranteed.

### Measured: SB on Apple Silicon

```cpp run title="sb-litmus.cpp" ok
#include <atomic>
#include <cstdio>
#include <thread>

#ifndef ST
#define ST std::memory_order::release
#define LD std::memory_order::acquire
#endif

std::atomic<int> x, y, go{0};
int r1, r2;

int main() {
  int both_zero = 0;
  constexpr int N = 200000;
  for (int i = 0; i < N; ++i) {
    x.store(0); y.store(0); go.store(0);
    std::thread a([] { while (!go.load(std::memory_order::acquire)) {} x.store(1, ST); r1 = y.load(LD); });
    std::thread b([] { while (!go.load(std::memory_order::acquire)) {} y.store(1, ST); r2 = x.load(LD); });
    go.store(1, std::memory_order::release);
    a.join(); b.join();
    both_zero += (r1 == 0 && r2 == 0);
  }
  std::printf("r1 == r2 == 0: %d / %d\n", both_zero, N);
}
```

Compiled with `clang++ -O2` on an Apple Silicon Mac. With `release` stores and `acquire` loads, `r1 == r2 == 0` appeared a few hundred to a few thousand times out of 200,000, varying with machine load; with `-DST=std::memory_order::seq_cst -DLD=std::memory_order::seq_cst` added, it never appeared.

The reason is in the assembly: release stores and seq_cst stores both compile to `stlr`; an acquire load compiles to `ldapr`, which can execute ahead of an earlier `stlr`, while a seq_cst load compiles to `ldar`, which cannot. The difference between the two memory orders in the standard is, in hardware, the difference of this one instruction.

## Out-of-thin-air values (¶8–¶10)

¶8 Implementations should ensure that no out-of-thin-air (OOTA) values are computed that circularly depend on their own computation. The example in Note 5, with `x` and `y` initially 0:

```cpp
// thread 1
r1 = y.load(memory_order::relaxed);
x.store(r1, memory_order::relaxed);
// thread 2
r2 = x.load(memory_order::relaxed);
y.store(r2, memory_order::relaxed);
```

`r1 == r2 == 42` should not occur: `y` being written as 42 presupposes `x` being written as 42, which in turn depends on `y` being written as 42. Note 5 also admits that without this restriction such an execution is possible; that is, the formal rules of ¶1–¶7 do not by themselves rule it out. ¶9 Note 6 adds that if the writes are made conditional, as in `if (r1 == 42) y.store(42, ...)`, `r1 == r2 == 42` likewise should not occur.

Note 7 describes two kinds of implementation that do not produce OOTA values: one translates non-volatile atomic accesses directly to machine instructions, just as for volatile; the other performs only optimizations that analyze one thread at a time, only eliding or merging atomic accesses to the same object, or reordering atomic accesses to different objects where the as-if rule permits, and treats everything else like volatile. ¶10 Note 8 points out that physical machines carefully manage speculative execution so as not to produce OOTA values at the hardware level.

!!! lawyer "Why only “should”"
    ¶8 says "should"; it is only a recommendation. Precisely characterizing "no OOTA" while still allowing normal compiler optimizations remains an open problem: formalizing dependencies conflicts with optimizations such as constant propagation and dead code elimination, which is also why `consume` failed. So the standard settles for a recommendation plus a description of two kinds of safe implementations. In practice, mainstream compilers and hardware never produce OOTA values.

## Read-modify-writes always read the latest value (¶11)

```cpp run title="relaxed-counter.cpp" ok
#include <atomic>
#include <cassert>
#include <thread>
#include <vector>

std::atomic<long> hits{0};

int main() {
  {
    std::vector<std::jthread> ts;
    for (int t = 0; t < 8; ++t)
      ts.emplace_back([] { for (int i = 0; i < 100000; ++i) hits.fetch_add(1, std::memory_order::relaxed); });
  }   // jthreads join here: thread completion synchronizes with the return from join
  assert(hits.load(std::memory_order::relaxed) == 800000);   // never loses one
}
```

¶11 Atomic read-modify-write operations always read the value of the side effect immediately preceding their own write in the modification order.

This is the essential difference between an RMW and a load followed by a store, and it has nothing to do with the memory order; a relaxed `fetch_add` satisfies it too. So multiple threads doing relaxed `fetch_add` on the same counter never lose increments. relaxed is enough here because the counter is not used to publish other data, and the final read gets visibility through join.

## Atomic modify-write operations (¶12) {{c++26}}

¶12 **Atomic modify-write operations** ([[g:atomic-modify-write-operation]]) are a class of atomic read-modify-write operations with weaker synchronization requirements, the weakening being specified in [[atomics.fences]]. Note 9 explains that the intent is for them to be implemented with mechanisms not ordered by hardware acquire fences, and that no other semantic or hardware property is implied.

They are the members `store_add`, `store_sub`, `store_and`, `store_or`, `store_xor`, `store_max`, `store_min` and so on added by [[P3111R8]] ([[atomics.types.int]] and elsewhere). Compared with the corresponding `fetch_*`:

- they return `void` rather than the old value;
- their preconditions allow only `relaxed`, `release` and `seq_cst`, with no acquire half, since the program cannot see the value they read;
- in [[atomics.fences#2]] they cannot serve as the reading side, so the path release fence, modify-write, acquire fence establishes no synchronization;
- they do not count as execution steps in the sense of [[intro.progress#3]];
- the floating-point versions may follow different arithmetic rules from ordinary operations; the note in [[atomics.types.float#14]] permits tree reductions.

Typical uses are histograms and reductions: many threads accumulate into the same set of counters, and none needs to read back the old value. Hardware can hand such operations off to be performed at the memory controller or near the cache, without pulling the cache line into the local core.

!!! impl "Not yet implemented in libc++"
    In the libc++ shipped with Clang 23, `atomic<int>` has no `store_add` or similar members yet.

## Timely visibility (¶13)

¶13 *Recommended practice*: implementations should make atomic stores visible to atomic loads within a reasonable amount of time. This is in line with the recommendation in [[intro.progress#17]], which asks that the last value in the modification order become visible to all threads in a finite period of time. Without such guarantees, a spin loop like `while (!flag.load(relaxed)) {}` could in theory read the old value forever.

## The implementation's view

!!! impl "The mapping on AArch64 (Apple Silicon, Clang 23 -O2)"
    | Operation | Instruction |
    |---|---|
    | load `relaxed` / `acquire` / `seq_cst` | `ldr` / `ldapr` / `ldar` |
    | store `relaxed` / `release` / `seq_cst` | `str` / `stlr` / `stlr` |
    | `fetch_add` `relaxed` / `acq_rel` / `seq_cst` | `ldadd` / `ldaddal` / `ldaddal` |
    | `atomic_thread_fence` `acquire` / `release` / `seq_cst` | `dmb ishld` / `dmb ish` / `dmb ish` |
    | `atomic_signal_fence(seq_cst)` | no instruction, just a compiler barrier |

    The only difference between an acquire load and a seq_cst load is `ldapr` versus `ldar`: the latter does not pass an earlier `stlr` in the same thread, which is exactly the store→load ordering ¶4.1 needs.

## History and evolution

!!! history "The evolution of memory_order"
    - C++11 had six values: `relaxed`, `consume`, `acquire`, `release`, `acq_rel`, `seq_cst`, and required S to be consistent with happens before.
    - C++17's [[P0371R1]] added a note temporarily discouraging `consume`, because compilers all implemented it as `acquire`.
    - C++20 made `memory_order` a scoped enumeration; [[P0668R5]] rewrote ¶4, introducing coherence-ordered before, requiring S to be consistent only with strongly happens before, and giving the four constraints involving fences.
    - C++26 moved `consume` to Annex D, equivalent to `acquire` ([[P3475R2]]), and added atomic modify-write operations ([[P3111R8]]).

## Common misconceptions

!!! pitfall "A release write followed by an acquire read: the write must take effect first"
    Not so. release constrains only accesses before it, acquire only accesses after it, and `store(release); load(acquire)` leaves exactly a gap between them. When this order is needed (Dekker's and Peterson's algorithms, the SB pattern), use `seq_cst` for both operations, or put a `seq_cst` fence between them. The measurement above shows this gap on real hardware.

!!! pitfall "seq_cst can patch up a data race"
    `seq_cst` orders only atomic operations. A data race on an ordinary variable is still UB, and ¶7's sequential consistency guarantee explicitly presupposes the absence of data races.

!!! pitfall "compare_exchange is acquire on failure too"
    When only one memory order argument is given, the failure order is derived from it: `acq_rel` becomes `acquire`, `release` becomes `relaxed`, and others are unchanged ([[atomics.types.operations#23]]). So `cas(e, d, release)` is not acquire on failure. If after a failure you rely on the value read to access other data, give the failure order explicitly.

## Questions

!!! question "1. A release write, a relaxed read that reads it, and an acquire fence after the read: is synchronization established?"

<details markdown="1">
<summary>Answer</summary>

Yes. This is not the case of ¶2, since the read is not an acquire operation; what applies is [[atomics.fences#4]]: a release operation A synchronizes with an acquire fence B if there is an atomic operation X on the same object, X is sequenced before B, and X reads the value written by A (or by the release sequence headed by A).
</details>

!!! question "2. Two threads each do one `seq_cst` `fetch_add(1)` on the same `atomic<int>`, and a third thread reads it twice with relaxed. Can it read 2 and then 1?"

<details markdown="1">
<summary>Answer</summary>

No, and it has nothing to do with seq_cst. The third thread's first read is sequenced before its second, so it happens before the second. By read-read coherence ([[intro.races#12]]), the second read must get the same value as the first or one later in the modification order. The modification order is 0, 1, 2, so after reading 2 it cannot read 1. Coherence on a single object holds for relaxed operations too (¶1 Note 1).
</details>

!!! question "3. Why does the first sentence of ¶4 use strongly happens before, while ¶4.2–¶4.4 use happens before?"

<details markdown="1">
<summary>Answer</summary>

The first sentence constrains the order between two seq_cst operations. If it used happens before, paths obtained through acquire/release synchronization would also have to be respected by S, which the common mappings on platforms like POWER cannot achieve (¶6). The happens before in ¶4.2–¶4.4 connects ordinary atomic operations with seq_cst fences, and on those platforms fences compile to full barrier instructions (such as POWER's `sync`), enough to meet these constraints, so happens before can be kept there.
</details>

## Summary

| Memory order | Relations established | Uses |
|---|---|---|
| `relaxed` | only atomicity and coherence on a single object | counters, statistics, flags not used to publish data |
| `release` / `acquire` | synchronization when the value is read (¶2) | producer-consumer, lock implementations |
| `acq_rel` | an RMW has both | reference count reaching zero, transferring ownership |
| `seq_cst` | all of the above, plus participation in the single total order S (¶4) | algorithms needing store→load order; the default |
| `consume` | equivalent to `acquire` since C++26, deprecated | no longer used |
