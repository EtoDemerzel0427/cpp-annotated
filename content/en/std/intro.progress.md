---
title: Forward progress
summary: "Compilers may assume every thread eventually performs an observable action, so an infinite loop with no side effects is UB (except, since C++26, a trivial infinite loop); implementations in turn guarantee that threads move forward at three levels: concurrent, parallel and weakly parallel."
updated: 2026-10-19
---

!!! tldr
    - The implementation may assume that every thread eventually terminates, or performs I/O, a volatile access, an atomic or synchronization operation, or `yield`. A thread that never does any of these is UB, so compilers can delete empty loops they cannot prove terminate.
    - Since C++26, a loop with an empty body whose condition is a constant `true` (a trivial infinite loop) is no longer UB; `while (true);` can be written safely.
    - A loop whose body is not empty, or whose condition is not a constant expression, does not get this exemption: `for (;; ++i) {}` and `while (flag);` running forever are still UB.
    - Implementations guarantee threads at three levels: concurrent (eventually makes progress), parallel (guaranteed only once started) and weakly parallel (no guarantee). `std::thread` is usually concurrent; worker threads of parallel algorithms have only parallel or weakly parallel guarantees.
    - When a thread with a forward progress guarantee waits on a set of threads with delegation, it lends its guarantee to at least one of them; `sync_wait` and parallel algorithms rely on this to guarantee eventual completion.

## Can the compiler delete a loop that might not terminate? (¶1)

```cpp run title="collatz.cpp" ok
unsigned f(unsigned n) {
  while (n != 1) n = (n % 2) ? 3 * n + 1 : n / 2;
  return 1;
}
int main(int argc, char**) { return f(argc + 26) == 1 ? 0 : 1; }
```

This loop does not terminate for `n == 0` (0 → 0 → …), and whether it terminates for an arbitrary `n` is a famous open problem (the Collatz conjecture). Yet Clang 23 at `-O2` compiles `f` to simply return 1, deleting the loop entirely. The basis is the rule below.

¶1 The implementation may assume that any thread will eventually do one of the following:

- ¶1.1 terminate;
- ¶1.2 invoke `std::this_thread::yield`;
- ¶1.3 make a call to a library I/O function;
- ¶1.4 perform an access through a volatile glvalue;
- ¶1.5 perform an atomic or synchronization operation other than an atomic modify-write operation (see below);
- ¶1.6 {{c++26}} continue execution of a trivial infinite loop (see the next section).

If a thread runs forever without doing any of these, the behavior is undefined {{ub}}. The loop in `f` modifies only local variables; if it didn't terminate, the thread would never again do anything observable, which is exactly what the implementation may assume doesn't happen. So the compiler need not know whether the loop terminates: if it terminates, 1 is returned; if not, it's UB; returning 1 directly is valid in both cases. In this example `n == 27`, the loop terminates, and the program is well-behaved.

Note 1 explains the intent: compilers may remove, merge or reorder empty loops even when termination cannot be proven. In real code, whether many loops terminate depends on invariants the compiler cannot prove, such as a list traversal `for (p = head; p != end; p = p->next)`. Deleting such a loop when its result is unused, or hoisting code after the loop to before it, both presuppose that the loop eventually ends.

## Trivial infinite loops (¶1.6) {{c++26}}

In C++23 and earlier, `while (true) ;` was UB too. This conflicts with a common idiom in embedded and systems programming:

```cpp
[[noreturn]] void halt() { while (true) ; }   // stop here and wait for a watchdog reset or interrupt
```

The programmer wants the program to stop here forever, but the compiler could delete the loop, letting control flow fall into whatever code follows. Older versions of Clang really did this with `int main() { while (1) ; }`: `main` was compiled to an empty body and execution fell straight into the next function.

C++26 fixed this with [[P2809R3]]. [[stmt.iter.general#3]] defines two concepts:

- A **trivially empty iteration statement** is a `while`, `do` or `for` statement with an empty body: `while (E) ;`, `while (E) { }`, `do ; while (E) ;`, `do { } while (E) ;`, `for (init E ; ) ;`, `for (init E ; ) { }`. The `for` statement cannot have an iteration expression, and an omitted condition `E` is treated as `true`.
- A **trivial infinite loop** is a trivially empty iteration statement whose condition is a constant expression with the value `true`. Its body is replaced with a call to `std::this_thread::yield` (whether this replacement happens in a freestanding implementation is implementation-defined).

After the replacement, each iteration of the loop does what ¶1.2 describes; and ¶1.6 lists continuing execution of a trivial infinite loop as an allowed case directly. Together they guarantee it is not UB, and note 1 explains it cannot be removed or reordered.

```cpp run title="trivial-loops.cpp" ok
constexpr bool forever = true;
void a() { while (forever) ; }      // trivial infinite loop
void b() { for (;;) { } }           // trivial infinite loop: an omitted for condition is true
void c() { do { } while (1); }      // trivial infinite loop
bool flag;
void d() { while (flag) ; }         // the condition is not a constant expression
void e() { while (true) { int x = 0; (void)x; } }  // the body is not empty
void f() { for (unsigned i = 0; ; ++i) { } }       // has an iteration expression
int main() {}
```

`d`, `e` and `f` are not trivial infinite loops, and running forever is still UB. Clang 23 at `-O2` generates real infinite jumps for `a`, `b` and `c`; for `e` and `f` it generates a trap instruction (`brk` on AArch64), deeming them unreachable; and for `d` it generates a plain `ret`, returning immediately even if `flag` is true.

`d` is especially easy to get wrong. If the intent is for another thread to set `flag` to `false` to end the wait, that is itself a data race ([[intro.races#17]]); the right way is `std::atomic<bool>`, whose atomic load falls under ¶1.5, so the loop is no longer UB.

!!! note "C's analogous rule"
    Since C11, the C standard says a loop whose controlling expression is not a constant expression, and which performs no I/O, volatile accesses, synchronization or atomic operations, may be assumed by the implementation to terminate. So C excluded `while (1) ;` from the start. C++26's rule moves toward C, but is narrower: C++ also requires the loop body to be empty.

### The modify-write exception in ¶1.5

C++26 added **atomic modify-write operations**: a kind of atomic read-modify-write operation with weaker synchronization requirements, such as `store_add` on integral atomics ([[atomics.order#12]]). They only write and don't return the old value, so a thread cannot use them to observe the progress of other threads. So an infinite loop that only does `store_add`, like a loop that only writes local variables, does not satisfy ¶1.5. The execution steps of ¶3.4 below exclude them likewise.

## What the implementation must guarantee

¶1 is the programmer's promise to the implementation: threads don't silently spin forever. The rest of this subclause specifies, in the other direction, the implementation's obligations: under what conditions a thread is sure to move forward. `std::thread`, parallel algorithms and the schedulers of `std::execution` all describe their guarantees in these terms.

### Execution steps and making progress (¶3–¶5)

¶3 During the execution of a thread, the following are **execution steps**:

- ¶3.1 termination of the thread;
- ¶3.2 performing an access through a volatile glvalue;
- ¶3.3 completion of a call to a library I/O function;
- ¶3.4 completion of an atomic or synchronization operation other than an atomic modify-write operation.

¶1 lists what the implementation may assume a thread will do, and ¶3 lists the events that count as progress; the two lists largely correspond.

¶4 An invocation of a standard library function that blocks is considered to continuously execute execution steps while waiting. To **block** means to wait for some condition to be satisfied before continuing ([[defns.block]]). Example 1 puts it this way: a library function that blocks until I/O completes can be thought of as continuously checking whether the operation is complete. With this rule, a thread blocked in `mutex::lock()` or `condition_variable::wait()` is neither starving nor violating ¶1.

¶5 A thread **makes progress** when an execution step occurs, or when a lock-free execution (see ¶2 below) does not complete because other unblocked threads are running concurrently. In the latter case, losing to a competitor counts as progress, because the competitor is moving forward.

### Three levels of forward progress guarantee (¶6–¶12)

| Guarantee | What the implementation ensures | Paragraph | Typical examples |
|---|---|---|---|
| **concurrent** | as long as the thread hasn't terminated, it will eventually make progress, regardless of other threads | ¶6 | the `main` thread, `std::thread`, `std::jthread` (recommended) |
| **parallel** | no guarantee that the thread will start if it hasn't executed any execution step yet; once it has executed one, concurrent guarantees apply | ¶8 | tasks in a thread pool; worker threads under `execution::par` |
| **weakly parallel** | no guarantee that the thread will eventually make progress | ¶10 | worker threads under `execution::par_unseq`; threads on a GPU |

¶6 Note 4 explains that "eventually" means in an unspecified but finite amount of time.

¶7 Whether the thread executing `main` and threads created by `std::thread` and `std::jthread` provide concurrent forward progress guarantees is implementation-defined {{impl}}; general-purpose implementations should provide them. It says only "should" to leave room for single-core embedded systems without preemption.

¶8–¶9 The parallel guarantee can be understood by analogy with a thread pool: once a task starts executing, it won't be shelved indefinitely, but tasks not yet started may wait in the queue forever. The example in note 5 is exactly this: a thread with concurrent guarantees executing a set of tasks one after another in arbitrary order satisfies the parallel guarantees of those tasks.

¶10–¶11 Weakly parallel can be understood by analogy with SIMD lanes on a GPU. Lanes in a group execute in lockstep; if one lane spins waiting for a flag set by another, and the latter is never scheduled because of branch divergence, there is a deadlock. Weakly parallel threads cannot count on making progress, but blocking with forward progress guarantee delegation, below, can guarantee that they eventually complete.

¶12 The three are in decreasing strength: concurrent > parallel > weakly parallel. Note 7 points out that some kinds of synchronization between threads can make progress only if both threads provide at least parallel guarantees, and can get stuck under weakly parallel.

### Consequences in parallel algorithms

[[algorithms.parallel.exec]] maps these guarantees onto execution policies:

| Policy | Where element access functions execute | Can element access functions use a mutex? |
|---|---|---|
| `execution::seq` | on the calling thread, in order | yes |
| `execution::par` | on library-created threads with parallel guarantees (if `std::thread` has concurrent guarantees) | yes, but one invocation must not wait for another that hasn't started |
| `execution::par_unseq` | weakly parallel, and several invocations may interleave on one thread | no: blocking synchronization may deadlock, and calling vectorization-unsafe library functions is UB |
| `execution::unseq` | on the calling thread, with invocations possibly interleaved | no, for the same reason |

```cpp run title="par-spin.cpp" flags="-std=c++2c -fexperimental-library"
#include <algorithm>
#include <atomic>
#include <execution>
#include <vector>
std::atomic<int> stage{0};
void bad(std::vector<int>& v) {
  std::for_each(std::execution::par, v.begin(), v.end(), [&](int& x) {
    if (&x == &v.front()) {
      while (stage.load() == 0) { }   // waits for another element's invocation
    } else if (&x == &v.back()) {
      stage.store(1);                 // but this invocation is not guaranteed to start
    }
  });
}
int main() { std::vector<int> v(2); (void)v; }
```

Under `par`, the invocation for `back()` may be queued after the one for `front()` on the same worker thread. It then never starts, and the invocation for `front()` spins forever. This is not UB (the spin contains an atomic load) but a deadlock: the parallel guarantee does not promise that an invocation not yet started will start (¶8). With `seq`, if `front()` is processed first, it deadlocks too. The right design is for element access functions not to wait on one another. The libc++ we tested provides parallel execution policies only with `-fexperimental-library`; `main` does not call `bad`, and the code is only for illustration.

[[algorithms.parallel.exec#9]] further specifies that if a parallel algorithm uses library-created threads, the calling thread either blocks with forward progress guarantee delegation on their completion, or executes element access functions itself. So even if the worker threads have only weakly parallel guarantees, the algorithm eventually completes.

### Blocking with forward progress guarantee delegation (¶13–¶16)

¶13 If a thread P is specified to **block with forward progress guarantee delegation** on the completion of a set S of threads, then throughout the whole time P is blocked, the implementation must ensure that the forward progress guarantees of at least one thread in S are at least as strong as P's. A thread in S is removed from S once it terminates, and P is unblocked when S is empty.

Intuitively, P lends its forward progress guarantee to the threads it is waiting on. If P has concurrent guarantees and waits on a batch of weakly parallel tasks, the implementation must run at least one of them with concurrent guarantees. The simplest implementation is for P to execute those tasks itself.

Note 8 adds that which thread in S is chosen, and for how many steps its guarantee is strengthened, are unspecified, and the strengthening is not permanent; but as long as P is blocked, the implementation must eventually choose and strengthen some thread in S. The next three notes explain some consequences:

- ¶14 Note 9: delegation is transitive. If A blocks on B, B is strengthened; if B in turn blocks with delegation on C, C is strengthened too.
- ¶15 Note 10: if all threads in S finish normally, P's forward progress guarantee is not weakened by this blocking.
- ¶16 Note 11: delegation does not lift the restrictions on using blocking synchronization in parallel and weakly parallel threads, because the implementation need not specifically strengthen the one thread that happens to be holding up overall progress.

C++26's `std::execution` ([[exec]]) exposes these terms as a query: `execution::get_forward_progress_guarantee(sch)` returns the scheduler's `forward_progress_guarantee::concurrent`, `parallel` or `weakly_parallel` ([[exec.get.fwd.progress]]). `this_thread::sync_wait` blocks the current thread with forward progress guarantee delegation until the sender completes; it does so by providing a `run_loop` scheduler driven by the current thread ([[exec.sync.wait]]).

### Lock-free executions (¶2)

¶2 Executions of atomic functions that are defined to be lock-free (the operations of `atomic_flag`, [[atomics.flag]]) or indicated as lock-free (`is_lock_free()` is true, [[atomics.lockfree]]) are **lock-free executions**. The standard places two requirements on them:

- ¶2.1 If there is only one thread that is not blocked in a standard library function, a lock-free execution in that thread shall complete. Note 2 explains that concurrently executing threads may prevent progress of a lock-free execution; for example, in an LL/SC (load-linked / store-conditional) implementation, writes by other threads can make the SC fail repeatedly. This property is usually called obstruction-free.
- ¶2.2 When one or more lock-free executions run concurrently, at least one should complete. Note 3 explains that malicious interference (such as repeatedly stealing a cache line) can prevent progress, and it is hard for implementations to guarantee this absolutely; but as long as the implementation avoids such anomalies under expected operating conditions, programmers can ignore them. This property is usually called lock-free.

So the names are somewhat mismatched: the standard's "lock-free execution" mandates only obstruction-freedom, while lock-freedom in the usual sense is merely a recommendation.

### Eventual visibility (¶17)

¶17 An implementation should ensure that the last value (in modification order) assigned by an atomic or synchronization operation becomes visible to all other threads in a finite period of time. [[atomics.order#13]] has the same recommendation. It is only a recommendation, but without it, a spin-wait like the following might in theory never see the new value:

```cpp run title="spin.cpp" ok
#include <atomic>
#include <thread>
std::atomic<bool> go{false};
int main() {
  std::thread t([] {
    while (!go.load(std::memory_order::acquire)) { }  // an atomic load: ¶1.5, not UB
  });
  go.store(true, std::memory_order::release);
  t.join();   // t will eventually see true
}
```

## Implementation view

!!! impl "How compilers implement ¶1"
    - In LLVM IR, C++ functions carry the `mustprogress` attribute by default, meaning the function must eventually return, unwind or interact with the environment, and the optimizer deletes loops without side effects on that basis. C code and C++ trivial infinite loops don't carry the corresponding attribute or loop metadata.
    - GCC controls a similar assumption with `-ffinite-loops`, enabled by default at `-O2` in C++11 and later modes.
    - The standard says the body of a trivial infinite loop is replaced with a `yield()` call, but `yield` has no observable effect, so under the as-if rule implementations need not actually generate the call. Clang 23 generates a single instruction that jumps to itself.

## History

!!! history
    - C++11 introduced the rule that the implementation may assume threads eventually terminate or perform I/O, volatile, synchronization or atomic operations, along with the recommendations on lock-freedom and eventual visibility.
    - C++17 introduced execution steps, the three levels of forward progress guarantees, and blocking with forward progress guarantee delegation, for parallel algorithms.
    - C++26: [[P2809R3]] made trivial infinite loops no longer UB; atomic modify-write operations were excluded from ¶1.5 and ¶3.4; `std::execution` describes the guarantees of schedulers in these terms.

## Common misconceptions

!!! pitfall "An infinite loop waiting for an interrupt has always been valid"
    `while (1) ;` was UB before C++26. Older embedded code often added a volatile access (¶1.4, portable) or `asm volatile("")` (an implementation extension) inside the loop to work around it. Since C++26, a loop with an empty body and a constant condition can be written directly.

!!! pitfall "As long as the condition is true, the loop isn't UB"
    The body must also be empty. `while (true) { ++local; }` running forever is still UB; `for (;;) {}` is fine, `for (;; ++i) {}` is not. The condition must also be a constant expression: `const bool b = true; while (b);` is fine, because `b` is a constant-initialized const variable usable in constant expressions; `while (g);` reading an ordinary global variable is not.

!!! pitfall "Spin-waiting on a plain bool"
    `while (!ready) {}` (where `ready` is a plain `bool`) breaks two rules at once: another thread writing `ready` is a data race ([[intro.races#17]]), and the loop itself violates ¶1. The compiler can hoist the read out of the loop, or even delete the loop entirely like `d` above. Use `std::atomic<bool>`.

## Questions

!!! question "Question 1"
    Which of these functions, if executed forever, are UB in C++26?
    ```cpp
    void f1() { while (true) {} }
    void f2() { while (true) { std::this_thread::yield(); } }
    void f3() { int i = 0; while (true) { ++i; } }
    void f4() { std::atomic<int> a; while (true) { a.load(std::memory_order::relaxed); } }
    void f5() { volatile int v = 0; while (true) { (void)v; } }
    ```

<details markdown="1">
<summary>Answer</summary>

Only `f3` is UB: its body is not empty, so it is not a trivial infinite loop, and it does nothing from ¶1 in the loop. `f1` is a trivial infinite loop (¶1.6); `f2` calls `yield` (¶1.2); `f4` performs atomic operations, relaxed included (¶1.5); `f5` accesses through a volatile glvalue (¶1.4). `(void)v` is a discarded-value expression, and for an expression naming a volatile variable the lvalue-to-rvalue conversion is applied, i.e. it really reads once ([[expr.context]]).
</details>

!!! question "Question 2"
    Why does ¶2.1 mandate only obstruction-freedom, and state true lock-freedom only as a recommendation?

<details markdown="1">
<summary>Answer</summary>

On LL/SC hardware (older ARM, POWER, RISC-V's LR/SC), a CAS loop can in theory be interrupted indefinitely by interference from other cores, so implementations cannot guarantee lock-freedom absolutely. But when only one thread is running, the operation must succeed, and that can be guaranteed. So the standard writes the guaranteeable part as a requirement and the part that holds in practice as a recommendation (note 3).
</details>

## Summary

| Topic | Key points | Paragraph |
|---|---|---|
| Progress assumption | a thread will eventually terminate, yield, do I/O, a volatile access, an atomic or synchronization operation (not modify-write), or execute a trivial infinite loop; otherwise UB | ¶1 |
| Trivial infinite loop | empty body and constant `true` condition; not UB since C++26 | ¶1.6, [[stmt.iter.general#3]] |
| Execution steps | termination, volatile access, completion of I/O, completion of atomic or synchronization operations | ¶3 |
| Blocking library calls | considered to continuously execute execution steps | ¶4 |
| Concurrent / parallel / weakly parallel | eventually progresses / eventually progresses once started / no guarantee | ¶6, ¶8, ¶10 |
| Delegation | the blocked thread lends its guarantee to the threads it waits on | ¶13 |
| Lock-free executions | must be obstruction-free; lock-free recommended | ¶2 |
| Eventual visibility | atomic writes should become visible to other threads in finite time (recommended) | ¶17 |
