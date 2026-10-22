---
title: Multi-threaded executions and data races
summary: "The formal definition of the C++ memory model: threads, conflicts, modification order, release sequences, synchronizes with, happens before, the four coherence rules, and why data races are undefined behavior."
updated: 2026-10-19
---

!!! tldr
    - Two threads access the same memory location, at least one access is a write, at least one is not atomic, and there is no happens-before relation between them: that is a data race, and the behavior of the whole program is undefined.
    - Happens before is made of sequenced before within a thread and synchronizes with between threads. A release write synchronizes with an acquire read that reads it, and a mutex unlock synchronizes with the next lock.
    - All modifications of each atomic object have a total order (the modification order), and four coherence rules forbid reads and writes on the same atomic object from going backward. The modification orders of different objects need not combine into one total order.
    - A program without data races that uses only mutexes and seq_cst atomic operations behaves as a simple interleaving of the threads' operations. Use acquire/release or relaxed, and results appear that no interleaving can explain.
    - volatile is not a means of synchronization. The only exception is between accesses to `volatile std::sig_atomic_t` within one thread and a signal handler.

## A data race

```cpp run title="race.cpp" ub
#include <thread>
int counter = 0;
int main() {
  std::thread t([] { ++counter; });
  ++counter;          // UB: a data race with the ++counter in t
  t.join();
  return counter;
}
```

Compiled and run with `-fsanitize=thread`, ThreadSanitizer reports a data race. Change `counter` to `std::atomic<int>`, or protect it with a mutex, and the program becomes correct.

Explaining why this code is UB, and why the fixed version is correct, takes the set of relations defined in [intro.races]. These relations describe not hardware but the executions the abstract machine allows. The semantics of the memory orders of atomic operations ([[atomics.order]]), mutexes ([[thread.mutex.requirements]]) and fences ([[atomics.fences]]) all consist of adding edges to these relations.

Prerequisites: sequenced before (order within a thread) as defined in [[intro.execution]], and [[intro.memory|memory locations]] (a scalar object, or a sequence of adjacent non-zero-width bit-fields).

## Threads [intro.multithread.general]

[[intro.multithread.general#1]] A **thread of execution** (also known as a thread) is a single flow of control within a program, including the initial invocation of a specific top-level function, and recursively including every function invocation subsequently executed by the thread. Note 1 explains that when one thread creates another, the initial call to the top-level function of the new thread is executed by the new thread.

Every thread can potentially access every object and function in the program. Footnote 31 adds that an object with automatic or thread storage duration is associated with one specific thread, and other threads can access it only indirectly through a pointer or reference. Under a hosted implementation a program can have more than one thread running concurrently; under a freestanding implementation, whether multiple threads are supported is implementation-defined.

The execution of a program consists of the execution of all its threads. Note 2 points out that execution can usually be viewed as an interleaving of the threads, but certain atomic operations allow executions inconsistent with any interleaving; the litmus tests below show such examples.

[[intro.multithread.general#2]] Which thread executes a signal handler not triggered by `std::raise` is unspecified.

## Conflicts (¶2)

¶1 The value of an object visible to a thread at a particular point is the object's initial value, a value written by the thread itself, or a value written by another thread, as determined by the rules below. Note 1 admits that in some cases the result is undefined behavior.

¶2 Two evaluations **conflict** if one of them

- ¶2.1 modifies ([[defns.access]]) a memory location, or ¶2.2 starts or ends the lifetime of an object in a memory location,

and the other one

- ¶2.3 reads or modifies the same memory location, or ¶2.4 starts or ends the lifetime of an object occupying storage that overlaps with it.

Note 2 adds that a modification can still conflict even if it doesn't change any bits: `x = x;` conflicts with a read of `x` in another thread.

Conflicts are judged by memory location, so the division into memory locations decides which accesses conflict:

```cpp run title="memloc.cpp" ok
#include <thread>
struct S {
  char a;
  int b : 5;
  int c : 11, : 0, d : 8;   // the zero-width bit-field puts c and d in different memory locations
  struct { int ee : 8; } e;
};
S s;
int main() {
  // a, (b and c), d, e.ee are four memory locations
  std::thread t1([] { s.a = 1; s.d = 2; });
  std::thread t2([] { s.b = 3; s.e.ee = 4; });   // no conflict with t1
  t1.join(); t2.join();
}
```

If t1 wrote `s.b` and t2 wrote `s.c`, they would be adjacent non-zero-width bit-fields in the same memory location; even though they are different members they would conflict, and without synchronization that is a data race. This example is adapted from the one in [[intro.memory]].

## Synchronization operations and modification order (¶3–¶5)

¶3 The library marks some atomic operations ([[atomics]]) and mutex operations ([[thread]]) as **synchronization operations**; they are what make one thread's writes visible to another:

| Kind | Examples |
|---|---|
| acquire operations | `load(acquire)`, `mutex::lock()` |
| release operations | `store(release)`, `mutex::unlock()` |
| both acquire and release | `fetch_add(acq_rel)`, `exchange(seq_cst)` |
| fences, with no associated memory location | `atomic_thread_fence(acquire)` etc. |

Relaxed atomic operations are not synchronization operations, but like synchronization operations they cannot contribute to data races. Atomic read-modify-write operations (`fetch_add`, `exchange`, `compare_exchange_*`) have additional special properties. Note 3 explains that acquiring a mutex performs an acquire operation on the locations comprising the mutex, and releasing it performs a release operation.

¶4 All modifications to a particular atomic object M occur in some total order, called the **modification order** of M. Note 4 stresses that each atomic object has its own modification order, and there is no requirement that they combine into a single total order for all objects, because different threads may observe modifications to different objects in inconsistent orders (see IRIW below).

¶5 A **release sequence** headed by a release operation A on an atomic object M is a maximal contiguous sub-sequence of side effects in the modification order of M, where the first operation is A and every subsequent operation is an atomic read-modify-write operation.

One thread does a release write, other threads then do several relaxed read-modify-writes, and finally some thread does an acquire read that reads a value written by one of those read-modify-writes. That acquire read still synchronizes with the original release write ([[atomics.order#2]]), because the read-modify-writes continue the release sequence. Patterns like reference counting depend on this.

```cpp run title="release-seq.cpp" ok
#include <atomic>
#include <cassert>
#include <thread>
int payload = 0;
std::atomic<int> flag{0};
int main() {
  std::thread prod([] {
    payload = 42;
    flag.store(1, std::memory_order::release);       // A: the head of the release sequence
  });
  std::thread mid([] {
    int expected = 1;
    while (!flag.compare_exchange_weak(expected, 2, std::memory_order::relaxed))
      expected = 1;                                   // a read-modify-write, continuing A's release sequence
  });
  std::thread cons([] {
    while (flag.load(std::memory_order::acquire) != 2) {}   // reads the 2 written by the read-modify-write
    assert(payload == 42);   // OK: still synchronizes with A
  });
  prod.join(); mid.join(); cons.join();
}
```

## Synchronizes with and happens before (¶6–¶8)

¶6 Certain library calls **synchronize with** other library calls performed by another thread. The conditions are in the library clauses:

- Atomic operations: a release operation A synchronizes with an acquire operation that reads a value from A's release sequence ([[atomics.order#2]]).
- Fences: synchronization between a release fence and an acquire fence, and between fences and atomic operations, is in [[atomics.fences]].
- Mutexes: note 6 explains that all operations on a given mutex occur in a single total order, and each lock acquisition "reads the value written" by the last unlock, so an unlock synchronizes with the next lock.
- Threads: the completion of the `std::thread` constructor synchronizes with the beginning of the new thread's function, and the completion of a thread synchronizes with the return from `join` ([[thread.thread.constr]], [[thread.thread.member]]).

Note 5 warns that, outside these specified cases, reading a later value does not necessarily ensure visibility. If a relaxed read reads the value of a release write, the two still do not synchronize.

¶7 An evaluation A [[g:happens-before|**happens before**]] an evaluation B if and only if ¶7.1 A is sequenced before B, or ¶7.2 A synchronizes with B, or ¶7.3 for some X, A happens before X and X happens before B. That is, happens before is the transitive closure of in-thread order together with cross-thread synchronization edges. Note 7 explains that an evaluation does not happen before itself.

```cpp run title="mp.cpp" ok
#include <atomic>
#include <cassert>
#include <thread>
int data = 0;
std::atomic<bool> ready{false};
int main() {
  std::thread t1([] {
    data = 42;                                         // A
    ready.store(true, std::memory_order::release);     // B
  });
  std::thread t2([] {
    while (!ready.load(std::memory_order::acquire)) {} // C
    assert(data == 42);                                // D
  });
  t1.join(); t2.join();
}
```

This is the message passing (MP) pattern. C reads the `true` written by B; B is a release and C an acquire, so B synchronizes with C. A is sequenced before B and C is sequenced before D, so A happens before D. ¶9 below guarantees that D reads 42, and with happens before between A and D there is no data race either.

If B and C were both made relaxed, there would be no synchronization; A and D conflict, are in different threads, and have no happens before, which is a data race. The consequence is not merely that 0 might be read: the behavior of the whole program is undefined.

### Strongly happens before (¶8)

¶8 A **strongly happens before** D if and only if:

- ¶8.1 A is sequenced before D; or
- ¶8.2 A synchronizes with D, and both are seq_cst atomic operations; or
- ¶8.3 there are B and C such that A is sequenced before B, B happens before C, and C is sequenced before D; or
- ¶8.4 there is B such that A strongly happens before B and B strongly happens before D.

Note 8: informally, if A strongly happens before B, then A appears to be evaluated before B in all contexts.

Why two relations? [[atomics.order#4]] requires all seq_cst operations to form a single total order S that is consistent with strongly happens before, but not with happens before (note 3 of [[atomics.order#6]]). On architectures like POWER, when acquire/release is mixed with seq_cst, the usual instruction mappings cannot guarantee that S is consistent with a happens before that includes acquire/release synchronization edges. C++20's [[P0668R5]] revised the definitions accordingly, making strongly happens before the part of happens before that S can actually respect.

Compare ¶8.2 and ¶7.2: a synchronization edge counts directly toward strongly happens before only if both ends are seq_cst; ¶8.3 allows a stretch of ordinary happens before in the middle, but both ends must be sequenced before.

Beyond this subclause, strongly happens before is also used to specify that static initialization precedes dynamic initialization ([[basic.start.static#2]]), and the order of destruction at program termination ([[basic.start.term#4]]).

## What a read can see (¶9–¶16)

¶9 For a value computation B of a scalar object or bit-field M, a side effect A on M is a **visible side effect** if and only if ¶9.1 A happens before B, and ¶9.2 there is no other side effect X on M such that A happens before X and X happens before B. The value of a non-atomic object M, as determined by B, is the value stored by the visible side effect A.

In other words, a non-atomic read sees the last write that happens before it. Note 9 explains that if there is ambiguity about which write is visible (two writes both happen before the read, with no happens before between them), the behavior is unspecified or undefined. Note 10 points out that this rule means operations on ordinary objects are not visibly reordered; in a program without data races, reordering cannot be observed anyway.

¶10 The value of an atomic object M, as determined by B, is the value stored by some unspecified side effect A that modifies M, where B does not happen before A. Unlike a non-atomic read, an atomic read can read one of several candidates in the modification order, not necessarily the latest. Note 11 points out that the set of candidates is further restricted by the coherence rules below.

### Four coherence rules (¶11–¶14)

For one atomic object M, happens before and the modification order must be compatible:

| Paragraph | Name | If | Then |
|---|---|---|---|
| ¶11 | write-write coherence | modification A happens before modification B | A is earlier than B in the modification order of M |
| ¶12 | read-read coherence | read A happens before read B, and A reads the value written by X | B reads X or a value later than X in the modification order |
| ¶13 | read-write coherence | read A happens before modification B | A reads a value earlier than B in the modification order |
| ¶14 | write-read coherence | modification X happens before read B | B reads X or a value later than X in the modification order |

Note 16 in ¶15 sums up: these four rules effectively forbid compiler reordering of operations on a single atomic object, even if both are relaxed loads. They bring the cache coherence guarantee provided by most hardware up to the C++ level.

```cpp run title="corr.cpp" ok
#include <atomic>
#include <cassert>
#include <thread>
std::atomic<int> x{0};
int main() {
  std::thread w([] {
    x.store(1, std::memory_order::relaxed);
    x.store(2, std::memory_order::relaxed);
  });
  std::thread r([] {
    int a = x.load(std::memory_order::relaxed);
    int b = x.load(std::memory_order::relaxed);
    assert(!(a == 2 && b == 1));   // read-read coherence: after reading 2, the earlier 1 is never read
    assert(!(a > 0 && b == 0));    // the initial 0 is first in the modification order
  });
  w.join(); r.join();
}
```

Note 17 in ¶16 discusses a seemingly circular definition: what an atomic read sees depends on happens before, while happens before, through synchronization edges, depends on what atomic reads see. The standard's meaning is: as long as one can find a mapping from atomic reads to the writes they read, together with suitably chosen modification orders and the happens before derived from them, that satisfies all the constraints above, it is a valid execution.

## Data races (¶17)

¶17 Two actions are **potentially concurrent** if and only if ¶17.1 they are performed by different threads, or ¶17.2 they are unsequenced, at least one is performed by a signal handler, and they are not both performed by the same signal handler invocation.

!!! std
    The execution of a program contains a data race if it contains two potentially concurrent conflicting actions, at least one of which is not atomic, and neither happens before the other […]

An execution that contains two potentially concurrent conflicting actions, at least one of which is not atomic, and neither of which happens before the other, contains a [[g:data-race|**data race**]], except for the signal handler case of ¶18. Any data race results in undefined behavior.

- Two atomic operations never form a data race, even if both are relaxed. Relaxed only means no synchronization is provided.
- Reads alone don't conflict; two threads reading the same non-atomic object at the same time is fine.
- The UB caused by a data race occurs in all participating threads (note 2 of [[intro.abstract]]), and of the observable behavior the program produced before it, only the part before an observable checkpoint is protected.

!!! summary "Note 18: data-race-free means sequentially consistent"
    A program that uses mutexes and `memory_order::seq_cst` atomic operations to prevent all data races, and uses no other synchronization operations, behaves as if the operations of its threads were simply interleaved, with each read taking the value of the last write to that object in the interleaving. This is **sequential consistency**, often called SC-DRF. Programmers only need to ensure there are no data races; compilers can perform almost any single-threaded transformation, because any program that could observe the difference has a data race and so had undefined behavior anyway.

## Results no interleaving can explain

Below, the relations above are used to analyze two classic small concurrent programs (litmus tests). All initial values are 0.

### Store buffering (SB)

```cpp run title="sb.cpp"
#include <atomic>
#include <thread>
std::atomic<int> x{0}, y{0};
int r1, r2;
int main() {
  std::thread a([] { x.store(1, std::memory_order::relaxed); r1 = y.load(std::memory_order::relaxed); });
  std::thread b([] { y.store(1, std::memory_order::relaxed); r2 = x.load(std::memory_order::relaxed); });
  a.join(); b.join();
  // r1 == 0 && r2 == 0 is an allowed result
}
```

In any interleaving, one store always executes first, so `r1` and `r2` cannot both be 0. But C++ allows this result: both loads read the initial values; checking the coherence rules, `x.load` does not happen after `x.store(1)` (there is no synchronization edge), so ¶14 does not require it to read 1; likewise for `y`. Making all four operations acquire/release changes nothing; in hardware this corresponds to the store buffer: the store is still in the buffer while the later load has already executed. In our tests (Apple arm64), running the relaxed version repeatedly does produce `0, 0`.

When all four operations are seq_cst, this result is forbidden. By [[atomics.order#4]], all seq_cst operations are in the total order S, and S is consistent with strongly happens before, so `x.store` precedes `y.load` in S and `y.store` precedes `x.load`. Suppose `y.load` reads the initial 0: the initial value is before `y.store` in the modification order of `y`, so by [[atomics.order#3]] (¶3.3) `y.load` is coherence-ordered before `y.store`, and ¶4.1 then requires `y.load` to precede `y.store` in S. So S contains `x.store` < `y.load` < `y.store` < `x.load`; `x.load` comes after `x.store` in S, and by the same argument it cannot read the initial value. This is the extra guarantee seq_cst gives over acquire/release, and why a seq_cst store on x86 needs `xchg` or `mfence`.

### Independent reads of independent writes (IRIW)

```cpp run title="iriw.cpp"
#include <atomic>
#include <thread>
std::atomic<int> x{0}, y{0};
int r1, r2, r3, r4;
int main() {
  std::thread w1([] { x.store(1, std::memory_order::release); });
  std::thread w2([] { y.store(1, std::memory_order::release); });
  std::thread rA([] { r1 = x.load(std::memory_order::acquire); r2 = y.load(std::memory_order::acquire); });
  std::thread rB([] { r3 = y.load(std::memory_order::acquire); r4 = x.load(std::memory_order::acquire); });
  w1.join(); w2.join(); rA.join(); rB.join();
  // r1==1, r2==0, r3==1, r4==0 is allowed under acquire/release
}
```

rA sees x written before y, rB sees y written before x: the two reader threads disagree about the order of two independent writes. This is exactly what note 4 means: the modification orders of the objects need not combine into one total order. On non-multi-copy-atomic architectures like POWER, this result can actually be observed. With everything seq_cst, S gives a single total order, and this disagreement is forbidden.

### MP with fences

```cpp run title="fence-mp.cpp" ok
#include <atomic>
#include <cassert>
#include <thread>
int data = 0;
std::atomic<bool> ready{false};
int main() {
  std::thread t1([] {
    data = 42;
    std::atomic_thread_fence(std::memory_order::release);   // fence A
    ready.store(true, std::memory_order::relaxed);          // X
  });
  std::thread t2([] {
    while (!ready.load(std::memory_order::relaxed)) {}      // Y
    std::atomic_thread_fence(std::memory_order::acquire);   // fence B
    assert(data == 42);
  });
  t1.join(); t2.join();
}
```

Per [[atomics.fences#2]]: A is sequenced before X, X modifies `ready`, Y reads the value written by X, and Y is sequenced before B, so the release fence A synchronizes with the acquire fence B, and `data = 42` happens before the assertion. Fences separate synchronization from the atomic variable carrying the data, and one fence can serve several relaxed operations.

{{c++26}} [[atomics.fences#2]] requires that Y not be an **atomic modify-write operation** ([[atomics.order#12]]). This is a new kind of read-modify-write added by [[P3111R8]], for example `store_add`, which writes without returning a value, intended to be implementable with hardware mechanisms not ordered by acquire fences. They cannot serve as the read side of fence synchronization.

## Signal handlers (¶18)

¶18 Two accesses to the same non-bit-field object of type `volatile std::sig_atomic_t` in the same thread do not form a data race, even if one or more occurs in a signal handler. For each signal handler invocation, the evaluations of the interrupted thread can be divided into two groups A and B, such that no evaluation in B happens before any evaluation in A; for such objects, the evaluations take values as though all of A happened before the handler and the handler happened before all of B.

In other words, the signal handler is inserted at some point in the interrupted thread, and for `volatile sig_atomic_t` this insertion appears atomic. This mechanism is inherited from C; modern code can also use lock-free `std::atomic` with `atomic_signal_fence` ([[atomics.fences#6]]).

```cpp run title="sig.cpp" ok
#include <csignal>
#include <cstdio>
volatile std::sig_atomic_t got = 0;
extern "C" void on_sig(int) { got = 1; }   // volatile sig_atomic_t accesses within the same thread
int main() {
  std::signal(SIGINT, on_sig);
  std::raise(SIGINT);       // the handler runs inside raise ([intro.execution]/15)
  std::printf("%d\n", static_cast<int>(got));
}
```

## Compilers may not introduce data races (¶19–¶20)

Note 19 in ¶19 explains that compilers generally cannot introduce writes to potentially shared memory locations that the abstract machine would not perform, because such a write might overwrite another thread's write when the abstract machine's execution had no data race:

- An assignment to `a` in `struct { char a; char b; }` cannot be implemented as read 4 bytes, modify 1 byte, write back 4 bytes, or it would clobber another thread's write to `b`. This is allowed only when bit-fields share a memory location, because then the standard already considers them conflicting.
- `if (cond) x = 1;` cannot be rewritten as `tmp = x; x = 1; if (!cond) x = tmp;`, which introduces a write to `x` when `cond` is false.
- When a loop conditionally modifies a global variable, the compiler cannot keep it in a register and write it back unconditionally after the loop.

Note 19 also says that reordering of atomic loads, in cases where the atomics in question may alias, is generally precluded too, since it could violate the coherence rules.

Note 20 in ¶20 explains that introducing speculative reads is usually fine. Strictly speaking it may introduce a data race, but on the target machine a racing read merely reads some value with no other consequences.

!!! impl
    | C++ operation | x86-64 | AArch64 |
    |---|---|---|
    | load relaxed / acquire | `mov` | `ldr` / `ldar` (or `ldapr`) |
    | store relaxed / release | `mov` | `str` / `stlr` |
    | store seq_cst | `xchg` (or `mov` + `mfence`) | `stlr` |
    | load seq_cst | `mov` | `ldar` |
    | fetch_add | `lock xadd` | `ldaddal` etc. (LSE), or an LL/SC loop |
    | fence acquire / release | no instruction, just a compiler barrier | `dmb ishld` / `dmb ish` |
    | fence seq_cst | `mfence` | `dmb ish` |

    x86 is total store order (TSO), which allows only loads to move ahead of earlier stores, so acquire/release costs nothing extra and only seq_cst stores pay; the `0, 0` of the SB test is the only counterintuitive result observable under TSO. ARMv8 is other-multi-copy-atomic, so the IRIW disagreement does not occur there, but the standard still allows it because it occurs on POWER.

    ThreadSanitizer (`-fsanitize=thread`) approximates happens before at run time and detects data races in the sense of ¶17. It can only find races that actually execute, and its support for `atomic_thread_fence` is limited. Clang 23's TSan falsely reports the correct fence-based MP above as a data race.

!!! history "History"
    - C++98/03 had no threads; the semantics of multithreaded programs came entirely from platform specifications like POSIX, which had many holes in the face of compiler optimizations (Hans Boehm, *Threads Cannot Be Implemented as a Library*, PLDI 2005).
    - C++11 introduced this subclause, establishing a memory model based on happens before together with `std::atomic`; C11 adopted almost the same model at the same time. The prohibition of out-of-thin-air values was later turned into a recommendation, now in [[atomics.order#8]]; how to formalize it precisely is still an open problem.
    - C++20's [[P0668R5]] revised the semantics of seq_cst and strongly happens before; [[P0982R1]] weakened release sequences. In C++11, ordinary atomic writes by the same thread after A also continued the release sequence; hardly anyone used this, yet it burdened implementations and formalizations, and now only read-modify-writes continue it.
    - C++26's [[P3475R2]] removed `memory_order::consume` from the core memory model. consume aimed to replace acquire with data dependencies, saving barrier instructions on ARM and POWER, but dependencies are hard to track at the source level, and all mainstream compilers implemented it as acquire. Carries a dependency, dependency-ordered before and inter-thread happens before, which existed to serve it, were all deleted from this subclause, and happens before was simplified to today's three-line definition in ¶7; `memory_order::consume` moved to Annex D with the same meaning as acquire ([[depr.atomics.order]]) {{deprecated}}. Note 3 in ¶3 still says "consume or acquire".

## Common misconceptions

!!! pitfall "volatile can be used for synchronization"
    volatile only guarantees that each access really happens (observable behavior in [[intro.abstract]]); it provides no atomicity and establishes no happens before. Two threads accessing the same `volatile int` without synchronization is still a data race. ¶18 makes an exception only for `volatile std::sig_atomic_t` within the same thread. MSVC gives volatile acquire/release semantics under `/volatile:ms`, which is an extension.

!!! pitfall "Some data races are benign"
    Races like `if (!initialized) { init(); initialized = true; }`, where reading a stale value seems harmless, are UB under the standard. Compilers may assume there is no race and merge reads or split writes accordingly. When needed, use `std::atomic<bool>` with an appropriate memory order, or simply `std::call_once` or a function-local static variable.

!!! pitfall "If a relaxed read sees a new value, earlier writes are visible"
    Note 5 is clear that reading a later value does not imply visibility. Publishing non-atomic data through a relaxed flag is a data race.

## Questions

!!! question "1. When thread 2 reads 2, does the program below have a data race?"
    ```cpp
    int data = 0;
    std::atomic<int> f{0};
    // thread 1
    data = 1;
    f.store(1, std::memory_order::release);
    f.store(2, std::memory_order::relaxed);
    // thread 2
    if (f.load(std::memory_order::acquire) == 2) { int r = data; }
    ```

<details markdown="1">
<summary>Answer</summary>

Yes. A release sequence consists only of a release operation and the read-modify-writes after it (¶5). `f.store(2, relaxed)` is not a read-modify-write and is not in the release sequence headed by `f.store(1, release)`. Thread 2 reads 2 and does not synchronize with thread 1, so there is no happens before between `data = 1` and `int r = data`: a data race.

In C++11/14/17, later atomic writes by the same thread were also part of the release sequence, and this code was correct; that is exactly what [[P0982R1]] changed. The fix is to make the second store a release too.
</details>

!!! question "2. Two threads simultaneously execute `x.store(1, relaxed)` and `x.load(relaxed)` on the same `std::atomic<int>`. Is there UB? What is read?"

<details markdown="1">
<summary>Answer</summary>

No UB. Per ¶17, a data race requires at least one action to be non-atomic. The read sees some value in the modification order (¶10); either 0 or 1 is possible.
</details>

!!! question "3. Why does ¶8.2 require both ends to be seq_cst, rather than counting any synchronization as strongly happens before?"

<details markdown="1">
<summary>Answer</summary>

Because the total order S must be consistent with strongly happens before ([[atomics.order#4]]). On architectures like POWER, when seq_cst is mixed with acquire/release, the mainstream instruction mappings cannot guarantee that a release-to-acquire synchronization edge is respected in S. If all synchronization edges counted, the standard would require stronger guarantees than those mappings give, and seq_cst would need a more expensive implementation. So only synchronization edges with seq_cst at both ends count directly; other cases require sequenced before, happens before, sequenced before joined end to end (¶8.3).
</details>
