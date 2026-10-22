---
title: "From pthreads to C++26: threads and the memory model"
summary: How C++ went from a language that didn't know threads existed to one whose standard defines data races and memory orders; why it chose sequential consistency for data-race-free programs, why consume and out-of-thin-air values were never solved well, and which debates produced the destructor behavior of thread, async and jthread.
tags: memory model, concurrency, atomics, data races, history
updated: 2026-10-19
---

!!! tldr
    - The C++98 abstract machine had a single flow of execution. Multithreaded programs relied on libraries like pthreads, and their correctness depended on a tacit understanding that compilers treat locking functions as opaque calls.
    - In 2005 Boehm argued that this was not enough: legitimate single-threaded compiler transformations rewrite adjacent data and promote shared variables to registers, so the language itself must define memory locations and data races.
    - The core of C++11 is sequential consistency for data-race-free programs: a program without data races behaves as if the threads' operations were simply interleaved, and a data race is undefined behavior. Compilers thus keep almost all single-threaded optimizations, and `memory_order` is an escape hatch for experts.
    - Two problems were not solved well: `memory_order_consume` could not be implemented as specified, and C++26 demoted it to a synonym for `acquire`; out-of-thin-air values can still only be ruled out by a recommendation.
    - `~thread` calling `terminate`, the future returned by `async` waiting in its destructor, and `jthread` offering only cooperative cancellation each correspond to a debate about interface safety.

This page is based mainly on two papers by Boehm (*Threads Cannot Be Implemented As a Library*, PLDI 2005; *Foundations of the C++ Concurrency Memory Model*, with Adve, PLDI 2008), Stroustrup's HOPL IV paper, and WG21 papers. Terms used: [[g:data-race|data race]], [[g:happens-before|happens before]], [[g:synchronizes-with|synchronizes with]], [[g:memory-location|memory location]]. The rules themselves are in [[intro.multithread]].

## C++98: no threads in the standard

C++98 describes program semantics with an abstract machine (today's [[intro.abstract]]): an implementation may transform code arbitrarily as long as observable behavior is preserved. This abstract machine has only one flow of execution. Meyers and Alexandrescu put it bluntly in 2004: "As languages, neither C nor C++ have threads." (*C++ and the Perils of Double-Checked Locking*, Dr. Dobb's Journal)

Multithreaded C++ programs were common at the time; it was just that threads came from outside the language: pthreads on POSIX systems, the Win32 API on Windows. pthreads has only one rule about memory: while one thread modifies a memory location, other threads must not read or write it, and that mutual exclusion is achieved with synchronization functions such as `pthread_mutex_lock` (Boehm 2005 §3).

Implementations honored this rule with two things: the synchronization functions contain hardware memory barriers internally, preventing the processor from reordering memory operations across the call; and compilers treat these functions as opaque external calls that may read or write any global variable, so they don't move memory accesses across the call. As long as all shared data is protected by mutexes, this tacit understanding mostly works.

### Double-checked locking

The trouble came with code that tried to bypass the mutex. The best-known example is double-checked locking, used to create a singleton lazily:

<div class="compare" markdown="1">

```cpp
// common pattern around 2004 (data race)
Widget* p = nullptr;
Widget* get() {
  if (p == nullptr) {     // read without the lock
    Lock lock;
    if (p == nullptr)
      p = new Widget;     // write with the lock
  }
  return p;
}
```

```cpp
// since C++11: leave it to the language
Widget& get() {
  static Widget w;  // concurrent first entry
                    // is synchronized by the implementation
  return w;
}
```

</div>

`p = new Widget` consists of three steps: allocation, construction and assigning the pointer. Under single-threaded semantics, moving the assignment before the construction is unobservable, and both compilers and hardware may do so. Another thread may then see a non-null `p` and get an object that has not finished construction. Meyers and Alexandrescu went through remedies such as `volatile` and temporary variables one by one, and concluded that it cannot be fixed portably in standard C++.

The right side is the C++11 solution: initialization of a block-scope static variable is synchronized by the implementation when entered concurrently ([[N2660]], today's [[stmt.dcl#3]]).

Compilers had their own remedies at the time. GCC provided the `__sync_*` builtins; MSVC gave `volatile` acquire/release semantics, and Microsoft's documentation also says code relying on this is not portable (Microsoft Learn, *volatile (C++)*). This state of dialects is part of the background to C++11 strictly separating `volatile` from atomic operations.

## Threads cannot be just a library

In 2005 Hans Boehm of HP Labs published *Threads Cannot Be Implemented As a Library*. His argument: if a compiler is designed for single-threaded semantics and threads are a library added afterwards, the generated code cannot be guaranteed to be correct. He gave three kinds of problems (§4).

### Compilers rewrite adjacent data

```cpp
struct { int a : 17; int b : 15; } x;
// thread 1: x.a = 42;
// thread 2: x.b = 7;
```

Almost no machine can write 17 bits directly, so `x.a = 42` is compiled to read the whole word, change the low 17 bits and write the whole word back. If thread 2 happens to modify `x.b` between the read and the write, that modification is lost, even though the two threads write different members.

pthreads only forbids concurrent modification of the same memory location, and memory location was not defined. On the broadest reading, a compiler merging assignments to eight adjacent `char` members into one 64-bit write-back would be legal, and even two global variables that happen to be adjacent could overwrite each other (§4.2).

### Compilers promote shared variables to registers

The loop on the left below updates the global variable `x` under a lock only when `mt` is true. If the compiler decides `mt` is usually false, it may promote `x` to a register, reading it before the loop and writing it back after (§4.3):

<div class="compare" markdown="1">

```cpp
// source
for (...) {
  if (mt) lock();
  x = f(x);
  if (mt) unlock();
}
```

```cpp
// after the compiler's transformation (sketch)
r = x;
for (...) {
  if (mt) { x = r; lock(); r = x; }
  r = f(r);
  if (mt) { x = r; unlock(); r = x; }
}
x = r;   // writes x without holding the lock
```

</div>

The transformed code reads and writes `x` without holding the lock, which is completely wrong with multiple threads, yet does not violate the letter of pthreads' requirements. Boehm says he knew of at least four optimizing compilers that had performed this transformation at some point.

### What counts as a data race must be defined by the language

The third problem is a circularity in the definitions: pthreads says programs with data races get no guarantees, but whether a program has a race depends on the semantics the language gives it. Two threads execute `if (x == 1) ++y;` and `if (y == 1) ++x;` respectively, both starting at 0; intuitively neither condition holds and there is no race. But if the compiler only needs to preserve single-threaded correctness, it may rewrite the first statement as `++y; if (x != 1) --y;`, and a race appears out of nowhere (§4.1).

Moreover, pthreads only recognizes one style, protecting everything with mutexes; lock-free algorithms are undefined under its rules (§5).

This paper directly determined several design decisions of C++11: the language must define the semantics of threads itself; it must define memory locations precisely and forbid compilers from writing to locations the program does not write; and it must provide atomic operations so that lock-free algorithms have a legitimate way to be written.

## C++11's answer: sequential consistency for data-race-free programs

### Why not copy Java

The first memory model proposal submitted to WG21 in 2004, [[N1680]], had among its authors Bill Pugh and Doug Lea, who had just worked on the Java memory model. C++ did not end up copying Java, for two reasons.

One was cost. According to Stroustrup, representatives from Intel and IBM pointed out that Java's model would significantly slow down the JVM itself (HOPL IV §4.1.1). The other was different goals. Java must give semantics even to programs with data races, because it has to limit the damage untrusted code can do; C++ has no such need, and programs with races can be entirely undefined (Boehm 2005 §3). The latter point became the cornerstone of the C++ model.

### DRF-SC

The approach of [[N2429]], merged into the C++0x draft in 2007, was summarized by Boehm and Adve in their PLDI 2008 paper as: programs without data races get sequentially consistent semantics. This is often called DRF-SC (data-race-free implies sequential consistency). It splits the responsibility in two:

- Programmers are responsible for not writing data races. As long as all shared data is protected by mutexes or `seq_cst` atomic operations, the program behaves as if all threads' operations were simply interleaved.
- Compilers and hardware can keep doing almost all single-threaded optimizations. If a program can observe these optimizations, it must have a data race, and a program with a data race has undefined behavior.

This is exactly the content of note 18 in today's [[intro.races#17]]. The same paragraph defines a data race as two potentially concurrent conflicting actions, at least one of which is not atomic, and neither of which happens before the other.

### Memory locations: a line drawn for compilers

Boehm's adjacent data problem is answered by [[intro.memory#3]]. A **memory location** is a scalar object that is not a bit-field, or a maximal sequence of adjacent bit-fields of non-zero width. Different memory locations can be accessed by different threads at the same time, and a compiler may no longer implement a write to `a` as a combined write-back of `a` and `b`:

```cpp run title="separate_locations.cpp" ok
#include <thread>

struct S {
    char a;
    char b;      // a and b are different memory locations
    int  x : 5;
    int  y : 11; // x and y are adjacent bit-fields in the same memory location
};

S s{};

int main() {
    std::thread t1([] { s.a = 1; });
    std::thread t2([] { s.b = 2; }); // OK: doesn't conflict with t1
    t1.join(); t2.join();
}
```

Two threads writing `s.x` and `s.y` respectively is still a data race (the note in [[intro.memory#4]]). This is a trade-off: hardware cannot write a few bits on their own, so the standard counts adjacent bit-fields as one location and makes the programmer responsible for synchronization; in every other case, the compiler is responsible for not writing out of bounds.

### volatile is not synchronization

With a definition of data race, the old technique of using an ordinary or `volatile` variable as a flag has a clear verdict:

```cpp run title="volatile_flag.cpp" ub
#include <thread>

int payload = 0;
volatile bool ready = false;     // volatile is not a synchronization operation

int main() {
    std::thread producer([] {
        payload = 42;
        ready = true;
    });
    std::thread consumer([] {
        while (!ready)
            ;
        int r = payload;         // UB: a data race with payload = 42
        (void)r;
    });
    producer.join();
    consumer.join();
}
```

Run with Clang's ThreadSanitizer (`-fsanitize=thread`), it reports a data race. The correct way is in the next section.

After N2429, Batty, Owens, Sarkar, Sewell, Weber and others at the University of Cambridge formalized the model mathematically, finding and fixing several problems in the draft ([[N3132]], [[N3196]]; *Mathematizing C++ Concurrency*, POPL 2011). C11 adopted the same model (HOPL IV §4.1.1).

## Why there are so many memory_orders

If DRF-SC were all that was wanted, the standard would only need to provide sequentially consistent atomic operations. But on weakly ordered architectures such as Power and ARM, sequential consistency requires extra barrier instructions, and the whole point of lock-free algorithms is to avoid unnecessary synchronization.

There was also a debate in the committee about the lowest-level primitives: Intel's side favored TSO plus a few atomic operations, IBM's side weak consistency plus fences. According to Stroustrup, IBM had a large amount of fence-based code buried deep in complex algorithms that could not move to an Intel-style model, and in the end C++11 supported both (HOPL IV §4.1.1). That is why today's standard has both atomic operations with memory orders and standalone fences ([[atomics.fences]]).

So C++11 lets the memory order be specified per operation ([[atomics.order]]):

| Memory order | Guarantee | Typical use |
|---|---|---|
| `seq_cst` (default) | Participates in a single total order, preserving DRF-SC | When you don't want to reason about memory orders |
| `acquire` / `release` / `acq_rel` | An acquire load that reads a release store synchronizes with it | Message passing, locks |
| `relaxed` | Only atomicity and coherence on a single object | Counters |
| `consume` | Originally meant to order only operations that depend on the value read; since C++26 the same as `acquire` | See the next section |

The cost is that once you use a memory order other than `seq_cst`, you leave the protection of DRF-SC and have to reason in terms of happens before. The most common case, release/acquire message passing, looks like this:

```cpp run title="message_passing.cpp" ok
#include <atomic>
#include <cassert>
#include <thread>

int payload = 0;                 // ordinary variable
std::atomic<bool> ready{false};

int main() {
    std::thread producer([] {
        payload = 42;                                   // (1)
        ready.store(true, std::memory_order_release);   // (2)
    });
    std::thread consumer([] {
        while (!ready.load(std::memory_order_acquire))  // (3)
            ;
        assert(payload == 42);                          // (4) OK
    });
    producer.join();
    consumer.join();
}
```

(1) is sequenced before (2), (2) synchronizes with the (3) that reads `true`, and (3) is sequenced before (4), so (1) happens before (4), and the two accesses to `payload` do not form a data race ([[intro.races#7]], [[atomics.order#2]]).

Note 1 in [[intro.races#1]] says that much of this subclause is written for atomic operations with explicit visibility constraints, but that it also implicitly supports a simpler view. That is Boehm and Adve's two-level design: programmers who use only mutexes and `seq_cst` stay in a sequentially consistent world, and only those who use weaker memory orders need to deal with all the details of happens before.

## Two problems not solved well

### memory_order_consume

The motivation for `consume` was RCU, used heavily in the Linux kernel: readers read a data structure through a pointer, and on Power and ARM, as long as subsequent accesses depend on that pointer through data, the hardware guarantees ordering without barrier instructions. Proposals by Paul McKenney and others ([[N2664]] and others) aimed to bring this cheap ordering into C++.

For this, C++11's [intro.races] introduced relations such as carries a dependency, dependency-ordered before and inter-thread happens before; the definition of happens before became complicated as a result, and lost transitivity. At the language level, the `[[carries_dependency]]` attribute and `std::kill_dependency` were added to carry or cut dependency chains at function boundaries.

The problem was that the standard defines dependencies in terms of source code: a value being an operand of another evaluation counts as a dependency. But compiler optimizations eliminate dependencies, for example folding the subscript in `p->a[x - x]` into a constant. To implement `consume` as specified, a compiler would have to suppress such optimizations along the entire dependency chain. As a result, every compiler treated `consume` as `acquire` ([[P3475R2]]).

C++17, through [[P0371R1]], added a note to [[atomics.order]] temporarily discouraging the use of `consume`. Over the following ten years there were several alternative proposals, none of which reached consensus. C++26's [[P3475R2]] finally acknowledged reality:

<div class="compare" markdown="1">

```text
happens before in C++11–C++23:
  A sequenced before B, or
  A inter-thread happens before B
inter-thread happens before is in turn
  defined recursively via
  synchronizes with,
  dependency-ordered before, etc.;
  not transitive, and since C++20
  helper relations such as simply
  happens before are also needed
```

```text
happens before in C++26:
  A sequenced before B, or
  A synchronizes with B, or
  A happens before X and
  X happens before B
(just a transitive closure)
```

</div>

P3475R2 removed the dependency-related relations and the `[[carries_dependency]]` attribute, and moved `consume` out of the main text of `memory_order` into [[depr.atomics.order]] in Annex D: it still exists, its value is still 1, and it means the same as `acquire`; `kill_dependency(y)` simply returns `y`.

```cpp run title="consume_today.cpp" ok
#include <atomic>

struct Node { int v; };
std::atomic<Node*> head{nullptr};

int read() {
    Node* p = head.load(std::memory_order_consume); // deprecated: a synonym for acquire
    return p ? p->v : 0;
}

int main() { return read(); }
```

At the time of writing, Clang 23 (libc++) gives no deprecation warning for this code. The reasons P3475R2 gives also reflect changes in hardware: `consume` never had any benefit on x86, ARM's acquire loads are close to relaxed loads in common cases, and the main remaining beneficiaries are Power and GPUs.

Note 3 in [[intro.races#3]] still says that a release operation makes prior side effects visible to a thread performing a consume or acquire operation. Since consume is now a synonym for acquire, the meaning of the sentence is unchanged; it simply keeps the old wording.

### Out-of-thin-air values

Relaxed atomic operations have another problem that is still not fully solved: out-of-thin-air (OOTA) values. The example below is adapted from the note in [[atomics.order#8]]:

```cpp title="oota.cpp"
// x and y are std::atomic<int>, both initially 0
// thread 1:
r1 = y.load(std::memory_order::relaxed);
x.store(r1, std::memory_order::relaxed);
// thread 2:
r2 = x.load(std::memory_order::relaxed);
y.store(r2, std::memory_order::relaxed);
```

Intuitively, `r1 == r2 == 42` cannot happen, because there is nowhere for 42 to come from. But with only happens before and the coherence rules, the formal model cannot exclude it: the two loads can circularly justify each other's stores.

C++11 forbade this outcome with a normative requirement. In [[N3786]], Boehm and others pointed out that the requirement was badly worded, and read literally would forbid every reasonable implementation of `relaxed` on ARM and Power; and after about ten years of attempts, nobody knew how to state it precisely without hurting performance. So C++14 turned it into a recommendation, the "should" in today's [[atomics.order#8]]: implementations should ensure that no out-of-thin-air values are computed that circularly depend on their own computation. Discussion has continued in WG21 since (for example [[P1217R2]]), without a conclusion.

## The thread library: debates in the interface

C++11's thread library derives from Boost.Thread; the first proposal was [[N1682]] in 2004, and the final version was [[N2497]]. Stroustrup points out that the constructor of `std::thread` is a variadic template, and its type-safe interface relies heavily on variadic templates and lambdas, added at the same time (HOPL IV §4.1.2).

### No cancellation

According to Stroustrup, the biggest controversy over the thread library was cancellation. Almost all C++ programmers on the committee wanted some form of cancellation, but representatives of the C committee (WG14) and POSIX considered cancellation both unnecessary and impossible to implement safely (HOPL IV §4.1.2). C++11 ended up providing no cancellation. That gap was only filled in C++20, with cooperative cancellation; see the end of this section.

### Why ~thread calls terminate

The 2008 draft specified that if a `std::thread` was destroyed while its thread had not been joined, it would automatically `detach()`. Boehm pointed out the problem in [[N2802]]:

```cpp title="detach-hazard.cpp"
void f() {
    int local = 0;
    std::thread t([&] { local = 1; });
    may_throw();   // if this throws, t has not been joined
    t.join();
}
```

When `may_throw()` throws, `t` is destroyed during stack unwinding. If the destructor detached, the thread would keep writing to the already destroyed `local`, causing memory corruption that is hard to debug. N2802 offered two alternatives: `join()` in the destructor, or `terminate()` in the destructor. C++11 chose the latter. The note in [[thread.thread.destr]] still explains this choice: an implicit detach leads to correctness problems that are hard to debug, and an implicit join leads to performance problems that only appear when an exception is thrown, and both show up only on exceptional paths.

### Why the future from async waits in its destructor

According to Stroustrup, the committee was split into two camps at the time: one basically wanted only a more type-safe POSIX, the other wanted higher-level facilities such as message queues and thread pools. The compromise reached in 2007 was that C++0x would provide promises, futures and an `async()` that allows, but does not require, the use of a thread pool. He says the compromise satisfied nobody (HOPL IV §4.1.3).

The rules for `async` ([[N2996]]) specify that if a future is the last object referring to the shared state created by `async`, its destructor waits for the task to finish. So futures returned by `async` behave differently from other futures:

```cpp run title="async_blocks.cpp" ok
#include <chrono>
#include <future>
#include <iostream>
#include <thread>

using namespace std::chrono_literals;

int main() {
    auto t0 = std::chrono::steady_clock::now();
    {
        auto f = std::async(std::launch::async, [] { std::this_thread::sleep_for(200ms); });
    }   // f's destructor waits here for the task to finish
    auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now() - t0).count();
    std::cout << (ms >= 200 ? "blocked\n" : "did not block\n");
}
```

In our tests it prints `blocked`.

In 2012 Sutter argued in [[N3451]] that this difference makes futures non-composable: a function that receives a future cannot know whether it came from `async`, and so cannot know whether its destructor will wait. Boehm gave the opposing argument in [[N3679]]: if it didn't wait, the task could keep running after the data it refers to had been destroyed, the same problem as with detach above, triggerable by one unexpected exception and hard to find in testing. Proposals to change `~future` and to deprecate `async` ([[N3776]], [[N3777]]) both failed.

So the rule remains to this day: [[futures.state#5]] says releasing a shared state does not block waiting for it to become ready, the sole exception being the last reference to a not-yet-ready shared state created by `async`.

### jthread: cooperative cancellation

[[P0660R10]], proposed by Nicolai Josuttis in 2017, combined two long-delayed things: a thread that joins automatically on destruction, and cooperative cancellation. `std::jthread` ([[thread.jthread.class]]) first requests a stop in its destructor, then joins. Stop requests are delivered through the `stop_token` in [[thread.stoptoken]], and the thread function has to check it periodically itself; no thread is ever forcibly terminated from outside, which sidesteps the cancellation debate of the C++11 era.

```cpp run title="jthread_stop.cpp" ok
#include <chrono>
#include <iostream>
#include <stop_token>
#include <thread>

using namespace std::chrono_literals;

int main() {
    std::jthread worker([](std::stop_token st) {
        int n = 0;
        while (!st.stop_requested()) {
            ++n;
            std::this_thread::sleep_for(1ms);
        }
        std::cout << "stopped after " << (n > 0 ? "some" : "no") << " iterations\n";
    });
    std::this_thread::sleep_for(20ms);
}   // ~jthread: request_stop() first, then join()
```

## Later additions

Most concurrency features after C++11 added facilities on top of the established model. The shape of several of them can be explained by history:

- **The name of the reader-writer lock.** The reader-writer lock accepted in 2013 was originally named `shared_mutex`; because it supports locking with timeouts, [[N3891]] proposed renaming it `shared_timed_mutex`, leaving the short name for a future version without timeouts that might be more efficient. So C++14 has only `shared_timed_mutex`, and `shared_mutex` appeared only in C++17 ([[thread.sharedmutex.class]]).
- **scoped_lock is a new name.** [[P0156R2]] originally wanted to turn `lock_guard` into a variadic template; out of concern about breaking ABI, it introduced the new name `std::scoped_lock` instead ([[thread.lock.scoped]]).
- **Forward progress guarantees.** C++17's parallel algorithms needed to say what kind of scheduling element access functions can rely on, and [[P0296R2]] provided the basic definitions of the forward progress guarantees in [[intro.progress]] for this.
- **The C++20 synchronization library.** [[P1135R6]] added atomic waiting ([[atomics.wait]]), semaphores, `latch` and `barrier`; `std::atomic_ref` ([[atomics.ref.generic]]) lets ordinary objects be accessed atomically for a while; `atomic<shared_ptr<T>>` replaced C++11's free functions such as `atomic_load(const shared_ptr<T>*)`, which have been removed from the current draft.
- **C++20 fixes to the model.** [[P0668R5]] found that common implementation schemes on Power and ARM did not satisfy the then-current definition of `seq_cst`, and redefined strongly happens before ([[intro.races#8]]), in which synchronizes with only counts when both ends are `seq_cst` operations. [[P0982R1]] narrowed release sequences to contain only atomic read-modify-write operations ([[intro.races#5]]).
- **Safe reclamation in C++26.** After a lock-free data structure unlinks a node, when can it be `delete`d? Hazard pointers and RCU are the two classic answers, and C++26 added both through [[P2530R3]] and [[P2545R4]] ([[saferecl]]). The hazard pointer interface is a subset of the Concurrency TS 2 version; P2530R3 says production experience with the Folly library showed that common uses don't need the omitted parts.
- **Trivial infinite loops.** [[intro.progress#1]] allows implementations to assume that every thread eventually terminates, does I/O, accesses a volatile, performs an atomic operation, and so on. C++26's [[P2809R3]] added continuing to execute a trivial infinite loop to that list ([[stmt.iter.general]]), so `while (true) {}` is no longer undefined behavior because of the forward progress assumption.

C++26 also added atomic operations such as `fetch_max` and `fetch_min` ([[P0493R5]]). At the time of writing, Clang 23 with libc++ does not provide them yet, nor the `<hazard_pointer>` and `<rcu>` headers.

## History in today's [intro.races]

| Current draft | Content | Origin |
|---|---|---|
| [[intro.memory#3]], [[intro.memory#4]] | Memory locations; different locations can be accessed concurrently | Boehm 2005's adjacent data problem |
| [[intro.races#2]] | Conflict: one modifies, the other reads or writes the same memory location | Formalization of the pthreads rule |
| [[intro.races#3]] | Synchronization operations: acquire, release, fences; relaxed is not a synchronization operation | The atomics library [[N2427]]; the TSO-versus-fences debate |
| [[intro.races#5]] | Release sequences consist only of read-modify-writes | C++20's [[P0982R1]] |
| [[intro.races#7]] | happens before is a transitive closure | The simplification after C++26 removed consume |
| [[intro.races#8]] | strongly happens before | C++20's [[P0668R5]] |
| [[intro.races#17]] | Data races cause UB; note 18 explains DRF-SC | Boehm and Adve's design |
| [[intro.races#18]] | Accesses to `volatile std::sig_atomic_t` within the same thread are not data races | Compatibility with signal handlers |
| [[atomics.order#8]] | The recommendation against out-of-thin-air values | C++14's [[N3786]] |
| [[depr.atomics.order]] | `consume` is a synonym for `acquire` | [[P3475R2]] |

## Work still in progress

- When the lifetime of the object a pointer points to ends, the pointer value becomes invalid. Many lock-free algorithms compare a pointer that may already be invalid, which conflicts with the standard; [[P2414R12]] discusses solutions.
- Algorithms like seqlocks need byte-granularity atomic copies; [[P1478R8]] proposes byte-wise atomic copy functions, currently not in the IS draft.
- The synchronous reclamation left out of hazard pointers is added by [[P3427R9]].
- Out-of-thin-air values are still only a recommendation; `consume` remains in Annex D, and no replacement design has been submitted.

## References

- Hans-J. Boehm, *Threads Cannot Be Implemented As a Library*, PLDI 2005.
- Hans-J. Boehm, Sarita V. Adve, *Foundations of the C++ Concurrency Memory Model*, PLDI 2008.
- Mark Batty et al., *Mathematizing C++ Concurrency*, POPL 2011.
- Scott Meyers, Andrei Alexandrescu, *C++ and the Perils of Double-Checked Locking*, Dr. Dobb's Journal, 2004.
- Bjarne Stroustrup, *Thriving in a Crowded and Changing World: C++ 2006–2020*, HOPL IV, 2020 (§4.1 concurrency support in C++11, §9.4 concurrency in C++20).
- Microsoft Learn, *volatile (C++)*.
