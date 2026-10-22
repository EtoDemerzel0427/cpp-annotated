---
title: The memory model in practice
summary: Starting from a broken piece of message-passing code, this page reasons about multithreaded programs with sequenced before, synchronizes with, happens before and modification order, using ThreadSanitizer and litmus results measured on Apple Silicon to explain what acquire/release, relaxed, seq_cst, fences and the standard library's synchronization facilities each guarantee.
tags: memory model, concurrency, atomics, data races, TSan, topic
updated: 2026-10-19
---

!!! tldr
    - When two threads access the same memory location, at least one access is a write, at least one is not atomic, and there is no happens before between them, that is a data race, and the behavior of the whole program is undefined.
    - happens before has only two sources: sequenced before within a thread, and synchronizes with between threads. The latter exists only if the acquire side actually reads the value written by the release side.
    - relaxed atomic operations don't cause data races, but they don't carry the visibility of any other data between threads; read-modify-write operations always read the latest value, so a relaxed counter doesn't lose increments.
    - acquire/release can't order a write followed by a read (store buffering). That needs `seq_cst` on both sides, or a `seq_cst` fence in between.
    - Not seeing a problem on x86 doesn't make the code correct: the same relaxed message-passing program goes wrong tens of thousands of times per million runs on Apple Silicon, and not once in the x86-64 build running under Rosetta 2.

## A broken message pass

One thread prepares some data and then raises a flag; another thread waits for the flag and then reads the data. This pattern is called **message passing** (MP). The most direct way to write it:

```cpp run title="mp-plain.cpp" ub
#include <chrono>
#include <cstdio>
#include <thread>
int data = 0;
bool ready = false;
int main() {
  std::thread producer([] {
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    data = 42;
    ready = true;            // plain write
  });
  std::thread consumer([] {
    while (!ready) {}        // races with ready = true
    std::printf("%d\n", data);
  });
  producer.join(); consumer.join();
}
```

Compiled with Clang 23 at `-O0` it prints `42`; at `-O2` it prints `0`. Looking at the AArch64 assembly at `-O2`, the consumer has no instruction that reads `ready` at all: the loop has been deleted entirely, and it just reads `data` and prints it.

The compiler's reasoning goes like this: if another thread could modify `ready` while this loop runs, that would be a data race and the program would have no defined behavior anyway, so it may assume `ready` doesn't change during the loop and read it only once. If it reads `true`, the loop does nothing; if it reads `false`, the loop is an infinite loop that never does anything, and [[intro.progress#1]] allows implementations to assume every thread eventually terminates or performs an action such as I/O, a volatile access, or an atomic or synchronization operation (except for trivial infinite loops with a constant condition). Neither case needs the loop, so it is deleted.

Running under ThreadSanitizer (TSan, `-fsanitize=thread`), it reports a race on `ready`:

```text
$ clang++ -std=c++2c -g -gdwarf-4 -O0 -fsanitize=thread mp-plain.cpp && ./a.out
WARNING: ThreadSanitizer: data race (pid=38557)
  Write of size 1 at 0x00010295c0dc by thread T1:
    #0 main::$_0::operator()() const mp-plain.cpp:10
  Previous read of size 1 at 0x00010295c0dc by thread T2:
    #0 main::$_1::operator()() const mp-plain.cpp:13
  As if synchronized via sleep:
    #0 nanosleep <null>
  Location is global 'ready' at 0x00010295c0dc
```

`As if synchronized via sleep` hints that `sleep_for` separated the two accesses in time, but TSan reports it anyway, because `sleep_for` provides no synchronization at all ([[thread.thread.this#8]] says *Synchronization: None*). What TSan checks is the happens before relation defined below, not order in time.

### Making the flag a relaxed atomic

```cpp run title="mp-relaxed-flag.cpp" ub
#include <atomic>
#include <cstdio>
#include <thread>
int data = 0;
std::atomic<bool> ready{false};
int main() {
  std::thread producer([] {
    data = 42;
    ready.store(true, std::memory_order::relaxed);
  });
  std::thread consumer([] {
    while (!ready.load(std::memory_order::relaxed)) {}
    std::printf("%d\n", data);   // races with data = 42
  });
  producer.join(); consumer.join();
}
```

The race on `ready` is gone, since accesses to an atomic object don't form data races. The loop isn't deleted either; every atomic load has to actually execute. But TSan reports a race on `data` every run: the read on line 13 against the write on line 8. relaxed atomic operations guarantee only `ready` itself; they don't make `data = 42` visible to the consumer.

### Making the data atomic too

If `data` is also a `std::atomic<int>` and all accesses are relaxed, the program has no data race and its behavior is well defined: the `data` the consumer reads may be 0 or 42, and both are valid results. In the litmus tests below, measured on Apple Silicon, seeing the flag but reading 0 happened thousands to tens of thousands of times per million.

### The correct version

```cpp run title="mp.cpp" ok
#include <atomic>
#include <cstdio>
#include <thread>
int data = 0;
std::atomic<bool> ready{false};
int main() {
  std::thread producer([] {
    data = 42;                                          // A
    ready.store(true, std::memory_order::release);      // B
  });
  std::thread consumer([] {
    while (!ready.load(std::memory_order::acquire)) {}  // C: reads the true written by B
    std::printf("%d\n", data);                          // D
  });
  producer.join(); consumer.join();
}
```

Only two memory order arguments changed; TSan no longer reports anything, and D always reads 42. The next few sections explain why.

## The definition of a data race

Two evaluations **conflict** if they access the same [[g:memory-location|memory location]] and at least one of them is a modification ([[intro.races#2]]). A memory location is a scalar object or a maximal sequence of adjacent non-zero-width bit-fields ([[intro.memory]]); the two members of `struct { char a; char b; }` are two memory locations, and two threads writing them separately don't conflict.

[[intro.races#17]] gives the definition: if an execution contains two conflicting actions that are potentially concurrent (in different threads), at least one is not atomic, and neither happens before the other, that execution contains a [[g:data-race|data race]], and the behavior is undefined.

Each of the three conditions corresponds to a fix:

| Condition | How to break it |
|---|---|
| Conflict | Have the threads access different memory locations, or only read |
| At least one is not atomic | Make the object a `std::atomic`, or access it through `std::atomic_ref` |
| No happens before | Establish ordering with synchronization: mutexes, acquire/release, `join` and so on |

The relaxed version in the first section fixed `ready` with the second approach, but `data` still meets all three conditions. The correct version uses the third.

Data races are UB, rather than being specified to read some old value, so that compilers can keep their single-threaded optimizations: keeping variables in registers, merging reads, deleting loops that look useless. Note 18 in [[intro.races#17]] explains that programs without data races can't observe these transformations. The price is that programs with data races may produce results like the `-O2` run above. The general consequences of UB are covered in [[topics/undefined-behavior]].

## Building happens before step by step

To decide whether there is happens before between two accesses, draw an execution as a graph whose nodes are evaluations, with two kinds of edges.

### The first kind of edge: sequenced before

Within one thread, [[g:sequenced-before|sequenced before]] specifies the order of evaluations ([[intro.execution#8]]). The rule used most is: every value computation and side effect of a full-expression is sequenced before the next full-expression ([[intro.execution#9]]). So in `mp.cpp`, A is sequenced before B, and C is sequenced before D.

This is an ordering at the language level, unrelated to the order in which instructions actually execute. Compilers and processors may reorder A and B as long as a single thread can't tell the difference.

### The second kind of edge: synchronizes with

The edges between threads are called [[g:synchronizes-with|synchronizes with]], and they can only be created by certain library operations ([[intro.races#6]]). The rule for atomic operations is [[atomics.order#2]]: a release operation A synchronizes with an acquire operation B if both act on the same atomic object and B reads the value written by A (or a value written by a later read-modify-write, see release sequences below).

A `store` with `release`, `acq_rel` or `seq_cst` is a release operation; a `load` with `acquire`, `acq_rel` or `seq_cst` is an acquire operation ([[atomics.order#1]]). `relaxed` is neither.

All three conditions are required. Especially the last one: synchronization happens between two specific operations in one execution, not between two lines of code. If C reads the initial value `false`, that read has nothing to do with B. That's why acquire loads almost always appear in a loop or branch that checks the value.

### Putting it together: happens before

[[intro.races#7]] defines [[g:happens-before|happens before]] as the transitive closure of these two kinds of edge: A happens before B if and only if A is sequenced before B, or A synchronizes with B, or there is an X such that A happens before X and X happens before B.

```text
producer                     consumer
  A: data = 42
     │ sequenced before
  B: ready.store(true, release) ──synchronizes with──▶ C: ready.load(acquire) reads true
                                                          │ sequenced before
                                                       D: reads data
```

Following the arrows from A gets to D, so A happens before D. With happens before between the two conflicting accesses, there is no data race.

### Which value is read

With no data race, we still need to know what D reads. For a non-atomic object, [[intro.races#9]] says it reads the value of the **visible side effect**: the write that happens before this read and is not overwritten by another write that also happens before this read. A is the only write that qualifies, so D reads 42.

Atomic objects are different. [[intro.races#10]] only requires an atomic read to read some write that doesn't happen after it; it may choose among several candidates, constrained by the coherence rules in the next section. That's why in the relaxed version the consumer can read the old value 0.

!!! note "strongly happens before"
    The standard also defines a stronger relation, [[g:strongly-happens-before|strongly happens before]] ([[intro.races#8]]). It excludes the part of happens before obtained through acquire/release synchronization that the seq_cst total order need not respect. For everyday reasoning happens before is enough; the stronger one appears in the definition of `seq_cst` and in the synchronization clauses for `latch`, `barrier` and semaphores. Details are in [[intro.multithread]].

## Modification order and coherence

All modifications of each atomic object M form a total order, called the [[g:modification-order|modification order]] of M ([[intro.races#4]]). All threads see the same order, but each object has its own modification order, and they aren't required to combine into one global order.

The four coherence rules in [[intro.races#11]]–[[intro.races#14]] tie happens before to modification order. In short: on a single atomic object, a thread never sees a new value and then an old one; a write that is earlier in happens before is also earlier in the modification order. These rules hold even if everything is relaxed. The exact statements and examples are in [[intro.multithread]].

### A relaxed counter

Read-modify-write operations (`fetch_add`, `exchange`, `compare_exchange_*` and so on) have an additional guarantee: they always read the value immediately preceding their own write in the modification order ([[atomics.order#11]]). A `load` followed by a `store` is two independent atomic operations and has no such guarantee:

```cpp run title="counter.cpp" ok
#include <atomic>
#include <cstdio>
#include <thread>
#include <vector>
std::atomic<long> a{0}, b{0};
int main() {
  {
    std::vector<std::jthread> ts;
    for (int t = 0; t < 4; ++t)
      ts.emplace_back([] {
        for (int i = 0; i < 1'000'000; ++i) {
          a.store(a.load(std::memory_order::relaxed) + 1,
                  std::memory_order::relaxed);      // the read and the write are two atomic operations
          b.fetch_add(1, std::memory_order::relaxed);  // one read-modify-write
        }
      });
  }                                                 // jthread joins on destruction
  std::printf("a = %ld\nb = %ld\n", a.load(), b.load());
}
```

In three runs in our tests, `a` was 2542693, 2388766 and 1246778, and `b` was 4000000 every time. The increments lost from `a` aren't a data race, so TSan reports nothing for this program; it is a logic error, avoidable only with read-modify-write.

relaxed is enough for `b`, because the counter itself isn't used to publish other data. The main thread reads the final value after `join`, and `join` provides the synchronization.

## Counting outcomes on real hardware

After using the standard to work out whether an outcome is allowed, you can use a **litmus test** to see what the hardware actually produces: run a few lines of code in two threads many times and count how often each outcome appears. The program below contains both MP and the store buffering (SB) test from the next section, with macros selecting the test and the memory orders:

```cpp run title="litmus.cpp"
#include <atomic>
#include <cstdio>
#include <thread>
using std::memory_order;
#ifndef ST
#define ST relaxed                    // memory order for stores
#endif
#ifndef LD
#define LD relaxed                    // memory order for loads
#endif
constexpr auto st = memory_order::ST, ld = memory_order::LD;
constexpr int N = 1'000'000;

std::atomic<int> xs[N], ys[N];        // a fresh pair of variables each round, all initially 0
int r1[N], r2[N];
std::atomic<int> round{-1}, done{0};

#ifdef SB  // store buffering: each writes one variable, then reads the other
void t0(int i) { xs[i].store(1, st); r1[i] = ys[i].load(ld); }
void t1(int i) { ys[i].store(1, st); r2[i] = xs[i].load(ld); }
bool weird(int i) { return r1[i] == 0 && r2[i] == 0; }
#else      // message passing: write x then y; read y then x
void t0(int i) { xs[i].store(1, st); ys[i].store(1, st); }
void t1(int i) { r1[i] = ys[i].load(ld); r2[i] = xs[i].load(ld); }
bool weird(int i) { return r1[i] == 1 && r2[i] == 0; }
#endif

void worker(void (*body)(int)) {
  for (int i = 0; i < N; ++i) {
    while (round.load(memory_order::acquire) != i) {}
    body(i);
    done.fetch_add(1, memory_order::release);
  }
}

int main() {
  std::thread a(worker, t0), b(worker, t1);
  for (int i = 0; i < N; ++i) {
    round.store(i, memory_order::release);
    while (done.load(memory_order::acquire) != 2 * (i + 1)) {}
  }
  a.join(); b.join();
  int count = 0;
  for (int i = 0; i < N; ++i) count += weird(i);
  std::printf("%d / %d\n", count, N);
}
```

The program itself has no data race. Each round the main thread releases the two workers through `round`, and each worker does one `fetch_add` on `done` when finished. `r1[i]` and `r2[i]` are ordinary variables, and the main thread can read them safely because both `fetch_add`s are read-modify-writes: the release sequence headed by the first is continued by the second, and the main thread's acquire load reads the final value and so synchronizes with both workers (release sequences are covered below).

Compile with commands like `clang++ -O2 -DSB -DST=seq_cst -DLD=seq_cst`. The table below shows three runs of each combination on an Apple M2 Pro; the numbers are how many of each million rounds gave the weird outcome (`r1 == 1 && r2 == 0` for MP, `r1 == r2 == 0` for SB). The x86-64 column is the same code compiled with Apple Clang 21 and `-arch x86_64`, run under Rosetta 2 translation:

| Test | Store | Load | arm64 (Clang 23) | x86-64 (Rosetta 2) |
|---|---|---|---|---|
| MP | `relaxed` | `relaxed` | 7956 – 42891 | 0 |
| MP | `release` | `relaxed` | 482 – 793 | 0 |
| MP | `relaxed` | `acquire` | 40 – 145 | 0 |
| MP | `release` | `acquire` | 0 | 0 |
| SB | `relaxed` | `relaxed` | about 470k – 510k | about 260k – 350k |
| SB | `release` | `acquire` | about 350k – 380k | about 240k – 380k |
| SB | `seq_cst` | `acquire` | about 340k – 360k | 0 |
| SB | `release` | `seq_cst` | 0 | about 330k – 380k |
| SB | `seq_cst` | `seq_cst` | 0 | 0 |

The counts vary with machine load, but the orders of magnitude are stable. A result of 0 only means it didn't happen on this machine, not that the standard forbids it; the next two sections explain each row.

## acquire/release: message passing needs both ends

The four MP rows in the table ask the same question: if t1 sees `y == 1`, is it guaranteed to also see `x == 1`?

- Both ends relaxed: there is no synchronization, and the standard allows `r1 == 1 && r2 == 0`. The arm64 assembly is two `str` and two `ldr`, in the same order as the source; the weird outcome comes from the processor: AArch64 allows two stores to become visible to other cores in a different order, and allows two loads to execute out of order.
- Only one end strengthened: a `release` store compiles to `stlr`, but the load is still `ldr` and can be reordered, so the problem remains; the same goes the other way round. At the level of the standard, synchronization needs a release store paired with an acquire load; with one end missing there is no synchronizes with.
- Both ends paired: `stlr` plus `ldapr`. The write to y is release, the read of y is acquire and reads 1, so they synchronize; the write to x happens before the read of x, and by the coherence rules it must read 1.

release means reads and writes before it can't move after it, and acquire means reads and writes after it can't move before it. That is an approximate description from the implementation's point of view; the standard's definition consists only of the synchronization edges in the previous section. Reasoning with synchronization edges is more reliable, especially with three or more threads:

```cpp run title="chain.cpp" ub
#include <atomic>
#include <cstdio>
#include <thread>
int data = 0;
std::atomic<int> a{0}, b{0};
int main() {
  std::jthread t1([] { data = 42; a.store(1, std::memory_order::release); });
  std::jthread t2([] {
    while (a.load(std::memory_order::acquire) == 0) {}
    b.store(1, std::memory_order::relaxed);    // should be release
  });
  std::jthread t3([] {
    while (b.load(std::memory_order::acquire) == 0) {}
    std::printf("%d\n", data);   // UB: no happens before with data = 42
  });
}
```

t1 synchronizes with t2, but t2 writes `b` with relaxed, so there is no synchronization edge between t2 and t3, and the chain breaks there. TSan reports a race on `data` every run; after changing `b.store` to `release` it no longer does. happens before is transitive, but every segment needs an edge.

## seq_cst: a single total order and store buffering

In the SB test each of two threads writes one variable and then reads the other:

```cpp
// x, y initially 0
// t0:                       // t1:
x.store(1);                  y.store(1);
r1 = y.load();               r2 = x.load();
```

However the four operations are interleaved, some store executes first, so `r1 == r2 == 0` seems impossible. But in hardware each core has a store buffer: a store first goes into the buffer and only later becomes visible to other cores, while the following load doesn't have to wait for it. If both cores' loads read the old values the other hasn't committed yet, the result is `0, 0`.

### Why acquire/release isn't enough

release only constrains operations before it, and acquire only constrains operations after it. A `store(release)` followed by a `load(acquire)` falls right into the gap that neither covers. The same follows from synchronization edges: both loads read the initial values and don't read any release store, so there isn't a single synchronization edge, and the standard places no constraint on `r1` and `r2`. The `release` / `acquire` row in the table appeared hundreds of thousands of times on both architectures.

### What seq_cst adds

All `seq_cst` operations are in a single total order S that is consistent with the modification order of each atomic object ([[atomics.order#4]]). When all four operations are seq_cst, suppose both loads read 0: the load of y reads y's initial value, so it must come before `y.store(1)` in S; likewise the load of x comes before `x.store(1)`; and within each thread the store comes before the load, so S contains a cycle, a contradiction. So `0, 0` is forbidden. The full derivation is in the store buffering section of [[intro.multithread]].

### Only one end seq_cst

The most interesting rows in the table are the two in the middle:

- Store `seq_cst`, load `acquire`: 0 times on x86-64, hundreds of thousands of times on arm64.
- Store `release`, load `seq_cst`: 0 times on arm64, hundreds of thousands of times on x86-64.

The standard allows `0, 0` for both combinations: only seq_cst operations enter S, and the other half isn't constrained by S (Note 4 in [[atomics.order#7]] says that as soon as any weaker memory order is used, the sequential consistency guarantee is lost). Each piece of hardware happens to block one of the two:

| Operation | x86-64 | AArch64 |
|---|---|---|
| store `release` | `mov` | `stlr` |
| store `seq_cst` | `xchg` | `stlr` |
| load `acquire` | `mov` | `ldapr` |
| load `seq_cst` | `mov` | `ldar` |

x86-64 puts the cost of seq_cst on the store, where `xchg` waits for the store buffer to drain; AArch64 puts it on the load, where `ldar` won't pass an earlier `stlr` in the same thread, but `ldapr` will. So code that writes seq_cst on only one end always passes its tests on one platform and fails on the other. Algorithms that need write-then-read ordering (Dekker, Peterson, SB-style handshakes) must use `seq_cst` on both ends.

## Fences

A fence detaches synchronization from specific atomic operations: with `std::atomic_thread_fence(release)` before a relaxed store and `atomic_thread_fence(acquire)` after a relaxed load, the two fences synchronize as long as the load reads the value of that store ([[atomics.fences#2]]). Fences and atomic operations can also be paired with each other ([[atomics.fences#3]], [[atomics.fences#4]]). One acquire fence can provide acquire semantics for several relaxed loads before it at once; usage is shown in [[atomics.fences]].

The SB test can also be fixed with fences, but they must be `seq_cst`:

<div class="compare" markdown="1">

```cpp
// not enough: the standard allows r1 == r2 == 0
x.store(1, relaxed);
atomic_thread_fence(acq_rel);
r1 = y.load(relaxed);
```

```cpp
// enough: 0, 0 is forbidden
x.store(1, relaxed);
atomic_thread_fence(seq_cst);
r1 = y.load(relaxed);
```

</div>

An `acq_rel` fence has the same gap as in the previous section, and since the loads here don't read the other thread's store, there is no synchronization edge between the fences either. A `seq_cst` fence enters the total order S, and ¶4.4 of [[atomics.order#4]] makes the order of the two fences in S constrain the relaxed operations on either side, leading to the same contradiction as in the previous section.

The measurements again depend on the platform. The `acq_rel` fence version produced `0, 0` over three hundred thousand times per million on x86-64 (Rosetta 2) and never on arm64, because Clang 23 compiles both `acq_rel` and `seq_cst` fences to `dmb ish`, while on x86-64 an `acq_rel` fence generates no instruction at all. The `seq_cst` fence version gave 0 on both.

## Release sequences and read-modify-write: reference counting

Several threads share an object; each decrements the reference count when it's done, and the thread that brings it to zero destroys the object. The destroyer has to read data the other threads wrote before releasing their references:

```cpp run title="refcount.cpp" ok
#include <atomic>
#include <cstdio>
#include <thread>
#include <vector>
struct Obj {
  std::atomic<int> refs{4};
  int log[4] = {};
};
void release_ref(Obj* p, int id) {
  p->log[id] = id + 1;                               // write the object before releasing the reference
  if (p->refs.fetch_sub(1, std::memory_order::acq_rel) == 1) {
    int sum = 0;
    for (int v : p->log) sum += v;                   // read other threads' writes
    std::printf("sum = %d\n", sum);
    delete p;
  }
}
int main() {
  Obj* p = new Obj;
  std::vector<std::jthread> ts;
  for (int i = 0; i < 4; ++i) ts.emplace_back(release_ref, p, i);
}
```

The last thread is directly adjacent only to the writer of the value it read; how does it synchronize with the two earlier threads? Through the [[g:release-sequence|release sequence]] ([[intro.races#5]]): the release sequence headed by a release operation A consists of A followed by the run of read-modify-writes immediately after it in the modification order. An acquire load that reads any value in that sequence synchronizes with A ([[atomics.order#2]]). All four `fetch_sub`s are read-modify-writes; each one heads a release sequence that the later `fetch_sub`s continue, so the acquire half of the last one synchronizes with every earlier one.

TSan in our tests reports nothing for this version. Change the memory order to `release` or `relaxed`, and the read that reaches zero is no longer an acquire; TSan reports a race on `log` every run.

Another common form is `fetch_sub(1, release)` followed, after reaching zero, by `atomic_thread_fence(acquire)`, paying the acquire cost only once; by [[atomics.fences#4]] it is equally correct. Clang 23's TSan doesn't understand standalone fences and falsely reports this form as a data race.

Only read-modify-writes continue a release sequence. Before C++20, ordinary atomic stores by the same thread after A also continued it; [[P0982R1]] removed that, and Question 1 in [[intro.multithread]] gives code affected by it.

## Where did consume go

`memory_order::consume` was meant to replace acquire with data dependencies: after loading a pointer, only accesses through that pointer would be ordered, which could save barriers on ARM and POWER. Compilers couldn't reliably preserve source-level dependencies through optimization, so they all implemented it as `acquire`. C++26's [[P3475R2]] moved it to Annex D ([[depr.atomics.order#1]]), with the same meaning as `acquire` {{deprecated}}. New code should just write `acquire`. The history is in [[history/threads-and-memory-model]].

## lock-free, wait and notify

Lock-free is about progress guarantees, not memory order. `std::atomic<T>` is available for any trivially copyable `T`; when the hardware has no atomic instruction wide enough, the implementation emulates it with a lock, and such operations may block ([[atomics.lockfree#4]]). But their memory order semantics are exactly the same as a lock-free implementation's, and the reasoning above still applies. Whether it is lock-free affects whether it can be used in signal handlers, whether it can be shared between processes ([[atomics.lockfree]]), and the progress guarantees of [[intro.progress#2]].

`wait` and `notify` spare the waiting side from spinning. The synchronization still comes from the store and the load:

```cpp run title="wait.cpp" ok
#include <atomic>
#include <cstdio>
#include <thread>
int data = 0;
std::atomic<bool> ready{false};
int main() {
  std::jthread consumer([] {
    ready.wait(false, std::memory_order::acquire);   // blocks while the value is still false
    std::printf("%d\n", data);
  });
  data = 42;
  ready.store(true, std::memory_order::release);   // synchronization comes from this store and the load inside wait
  ready.notify_one();                              // only wakes the waiter
}
```

The effect of `wait(old, order)` is to repeatedly `load` with `order`, returning when the value differs from `old` and blocking when it is the same ([[atomics.types.operations#31]]). The acquire `load` just before returning reads the value of the release `store`, and that is how synchronization is established. `notify_one` has no memory order parameter and provides no visibility. Change both memory orders to relaxed and TSan reports a race on `data` every run. The details of the wakeup rules are in [[atomics.wait]].

## Synchronization provided by standard library facilities

Most code doesn't write memory orders directly but uses the standard library's synchronization facilities. Their clauses all have a *Synchronization* item stating which edges they add to the happens before graph:

| Facility | Edge added | Clause |
|---|---|---|
| Constructing `std::thread`, `std::jthread` | Completion of the constructor → start of the new thread's function | [[thread.thread.constr#7]], [[thread.jthread.cons#7]] |
| `join()` | Thread completion → return from `join` | [[thread.thread.member#4]] |
| Mutexes | Each `unlock` → a later `lock` that obtains ownership | [[thread.mutex.requirements.mutex.general#8]], [[thread.mutex.requirements.mutex.general#24]] |
| `try_lock` | Synchronizes only when it returns `true` | [[thread.mutex.requirements.mutex.general#16]] |
| `std::call_once` | The call that executed the function → the return of every other call | [[thread.once.callonce#3]] |
| `std::promise`/`std::future` | Setting the result → successful return of a waiting function | [[futures.state#9]] |
| `std::latch` | Each `count_down` strongly happens before the return of the calls it unblocks | [[thread.latch#9]] |
| `std::barrier` | The end of the completion step strongly happens before the return of the calls it unblocks | [[thread.barrier.class#3]] |
| `std::counting_semaphore` | `release` strongly happens before a `try_acquire` that observes its result | [[thread.sema.cnt#10]] |
| `sleep_for`, `yield` | None | [[thread.thread.this]] |

Condition variables have no synchronization clause of their own; their synchronization comes from the associated mutex: `wait` reacquires the lock before returning, which synchronizes with the notifier's earlier `unlock`. For the initialization of function-local static variables, [[stmt.dcl#3]] says threads entering concurrently wait for the initialization to complete, and in practice you can treat that as synchronization between completing the initialization and the waiters.

With this table, many questions can be answered without touching memory orders:

```cpp run title="latch.cpp" ok
#include <cstdio>
#include <latch>
#include <thread>
#include <vector>
int main() {
  constexpr int n = 4;
  int results[n] = {};                     // plain array, no atomics
  std::latch done(n);
  std::vector<std::jthread> ts;
  for (int i = 0; i < n; ++i)
    ts.emplace_back([&, i] {
      results[i] = i * i;                  // each writes its own element
      done.count_down();
    });
  done.wait();
  int sum = 0;
  for (int r : results) sum += r;
  std::printf("%d\n", sum);
}
```

Each worker's write to `results[i]` is sequenced before its own `count_down`, `count_down` strongly happens before the return of `wait`, and the return of `wait` is sequenced before the main thread reads the array. The workers write different elements, which are different memory locations, so they don't conflict.

<details class="fine" markdown="1"><summary>A literal gap in the latch wording</summary>

[[thread.latch#9]] is worded as `count_down` strongly happening before the return of calls that are unblocked. If the count is already 0 when the main thread calls `wait`, then by [[thread.latch#13]] `wait` returns immediately without being unblocked, and the literal text doesn't cover this case. The obvious intent is that both cases synchronize; libc++'s `wait` in our tests reads the counter with acquire in either case, and `count_down` is a release `fetch_sub`, so the actual behavior is fine.

</details>

## Common mistakes

!!! pitfall "volatile as atomic"
    ```cpp
    volatile long hits = 0;
    // two threads each run this a million times:
    hits = hits + 1;   // UB: data race
    ```
    Two runs in our tests gave 1053997 and 1509420, and TSan reports a data race. `volatile` only guarantees that every access actually happens ([[intro.abstract]]); it provides no atomicity and establishes no happens before. It doesn't work for message passing either: replacing `xs` and `ys` in the litmus test with `volatile int` still gives ten to twenty thousand weird outcomes per million rounds on arm64. The only thread-related use of `volatile` is `volatile std::sig_atomic_t` for communicating with a signal handler in the same thread ([[intro.races#18]]).

!!! pitfall "Double-checked locking with the wrong memory orders"
    ```cpp
    std::atomic<Config*> instance{nullptr};
    std::mutex m;
    Config* get() {
      Config* p = instance.load(std::memory_order::acquire);  // must not be relaxed
      if (p == nullptr) {
        std::lock_guard lock(m);
        p = instance.load(std::memory_order::relaxed);  // inside the lock, relaxed is fine
        if (p == nullptr) {
          p = new Config;
          instance.store(p, std::memory_order::release);    // must not be relaxed
        }
      }
      return p;
    }
    ```
    When the first check outside the lock reads a non-null pointer, it hasn't gone through the mutex, and only release-store/acquire-load synchronization lets it see the members written by `Config`'s constructor. With both changed to relaxed, TSan in our tests reports a race between a write in the constructor and another thread reading `port` every run. Simpler alternatives are a function-local static or `std::call_once`, whose synchronization is handled by the implementation.

!!! pitfall "A relaxed flag with ordinary data"
    `mp-relaxed-flag.cpp` in the first section is exactly this mistake. Reading a new value doesn't mean seeing the writer's earlier writes, as Note 5 in [[intro.races#6]] states explicitly. When a flag is used to publish data, use `release` for the store and `acquire` for the load.

!!! pitfall "Assuming it's correct because tests pass on x86"
    x86-64's hardware memory model is total store order (TSO), which only lets later loads pass earlier stores, so relaxed MP under Rosetta 2 gave 0 in a million runs. The same source compiled for arm64 went wrong tens of thousands of times per million. On the other hand, acquire/release loads and stores on x86 are just plain `mov`s, and the compiler can still reorder relaxed operations at compile time within the limits the standard allows, so even when targeting only x86 it is necessary to write code to the C++ memory model. The two SB rows above also show that arm64 hides some bugs that x86 exposes. The most reliable approach is to reason by the standard, then check with TSan and tests on several platforms.

!!! pitfall "Using sleep to wait for another thread"
    Neither `sleep_for` nor `yield` provides synchronization ([[thread.thread.this#8]]). In the TSan report in the first section, `As if synchronized via sleep` is hinting at exactly this problem.

## Questions

!!! question "1. The code below implements a two-thread handshake with seq_cst stores and acquire loads. Does it guarantee that r1 and r2 aren't both 0?"
    ```cpp
    // t0:                                  // t1:
    x.store(1, memory_order::seq_cst);      y.store(1, memory_order::seq_cst);
    r1 = y.load(memory_order::acquire);     r2 = x.load(memory_order::acquire);
    ```

<details markdown="1">
<summary>Answer</summary>

No. The total order S contains only seq_cst operations; the two acquire loads aren't in S, [[atomics.order#4]] yields no contradiction, and the standard allows `0, 0`. On x86-64 a seq_cst store compiles to `xchg`, which drains the store buffer, so tests don't catch it; on arm64 the store is `stlr` and the acquire load is `ldapr`, which can pass it, and in the measurements above this happened about 350,000 times per million. The two loads must also be seq_cst.
</details>

!!! question "2. One thread does `x.store(1, relaxed)`, and another thread's `x.load(relaxed)` reads 1. If the second thread then reads x again with relaxed, can it read 0?"

<details markdown="1">
<summary>Answer</summary>

No. The two reads are in the same thread, the first is sequenced before the second and therefore happens before it. By read-read coherence ([[intro.races#12]]), the second read must read the same value as the first, or one later in the modification order. The modification order is 0, 1, so after reading 1 it can't read 0 again. The coherence rules hold for relaxed operations too.
</details>

!!! question "3. In code protected by a `std::mutex`, can a shared `int` be replaced with a relaxed atomic? Conversely, what if two threads access the same `int`, one with the lock held and one without?"

<details markdown="1">
<summary>Answer</summary>

The first is possible but unnecessary. Each `unlock` synchronizes with the later `lock` ([[thread.mutex.requirements.mutex.general#8]]), so all accesses inside the lock are ordered by happens before, and a plain `int` already has no data race.

The second is a data race. A mutex provides a synchronization edge only when both threads lock it; if one thread accesses without locking, there is no happens before between its access and the other thread's write inside the lock. Locking on only one side is the same as not locking.
</details>

## Summary

| Need | Approach |
|---|---|
| Passing ordinary data between threads | Library facilities such as mutexes, `join`, `latch`, `future`; when rolling your own, a release store paired with an acquire load |
| Just counting, not publishing other data with the count | relaxed read-modify-write (`fetch_add`) |
| Write your own flag, then read the other's flag | `seq_cst` on both ends, or a `seq_cst` fence in between |
| One synchronization covering several relaxed operations | release fence / acquire fence |
| Destroying an object when its reference count reaches zero | `fetch_sub(acq_rel)`, or `release` plus an acquire fence after reaching zero |
| Waiting for a value to change without spinning | `wait(old, acquire)` with a release store and `notify` |
| Checking your reasoning | Draw the happens before graph; TSan for data races; litmus tests on several architectures |
