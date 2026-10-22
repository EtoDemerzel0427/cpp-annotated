---
title: "Multithreaded performance: contention and false sharing"
summary: "Why adding threads can make things slower: false sharing from cache lines bouncing between cores, contention when every thread updates the same atomic, which instructions each memory order produces on arm64 and what they cost, mutex vs spinlock vs atomic, reference-count contention when copying shared_ptr, and the overhead of starting threads and of thread pools, all measured on an M2 Pro with 1 to 12 threads."
tags: performance, concurrency, false sharing, cache line, atomics, memory order, mutex, thread pool
updated: 2026-10-19
group: Memory
---

!!! tldr
    - When several cores write the same cache line, the line has to bounce between them. Even if each thread writes a different variable (false sharing), 8 threads ran 7 times slower than one on our test machine; aligning each variable to `std::hardware_destructive_interference_size` (128 in libc++ on our test machine) removes the problem.
    - When every thread does `fetch_add` on the same atomic variable, adding threads only lowers total throughput; only accumulating in a local variable per thread and combining once at the end scales with the thread count.
    - On arm64, a relaxed `fetch_add` is `ldadd`, while `acq_rel` and `seq_cst` are both `ldaddal`; uncontended, the former takes about 2 ns and the latter about 4 ns on our test machine. Memory orders also constrain the compiler: ordinary variables cannot stay in registers across an acquire load.
    - With short critical sections under contention, `std::mutex` was far more stable than a naive spinlock in our tests; when the work fits in a single atomic operation, the atomic is fastest.
    - Copying a `shared_ptr` is two atomic read-modify-writes; several threads copying the same `shared_ptr` contend on the same counter. Creating a thread takes over 10 µs on our test machine, and handing one task to a thread pool and waiting for it takes a few microseconds.

## The test machine and method

All numbers below come from an Apple M2 Pro, macOS, Homebrew Clang 23 + libc++, `-std=c++2c -O2`. First, how many cores this machine has and how big a cache line is:

```text
$ sysctl hw.perflevel0.physicalcpu hw.perflevel1.physicalcpu hw.cachelinesize
hw.perflevel0.physicalcpu: 8
hw.perflevel1.physicalcpu: 4
hw.cachelinesize: 128
```

That is 8 performance cores (P-cores), 4 efficiency cores (E-cores), and 128-byte cache lines. A **cache line** is the smallest unit of data moved between cache and memory and between caches, and it determines most of the phenomena below. The cache hierarchy itself is in [[perf/memory-hierarchy]].

Timing uses [[perf/measuring#harness|bench.hpp]], which provides `do_not_optimize` (an inline asm statement that generates no instructions and makes the compiler believe a value has been read, so the code computing it is not deleted) and `prefer_performance_cores` (sets the thread's QoS to the highest level so the scheduler prefers P-cores; macOS cannot pin threads to specific cores). Multithreaded measurement adds two more functions:

```cpp title="mt.hpp"
// mt.hpp: multithreaded timing on top of bench.hpp
#pragma once
#include "bench.hpp"
#include <atomic>
#include <thread>

namespace bench {

// start n threads, wait until all are ready, release them together, each runs body(i);
// returns nanoseconds from release until the last thread finishes. Thread creation is not counted.
template <class F>
double run_threads(int n, F body) {
  std::atomic<int> ready{0};
  std::atomic<bool> go{false};
  std::vector<std::jthread> ts;
  for (int i = 0; i < n; ++i)
    ts.emplace_back([&, i] {
      prefer_performance_cores();
      ready.fetch_add(1);
      while (!go.load(std::memory_order::acquire)) {}
      body(i);
    });
  while (ready.load() != n) {}
  auto t0 = std::chrono::steady_clock::now();
  go.store(true, std::memory_order::release);
  for (auto& t : ts) t.join();
  auto t1 = std::chrono::steady_clock::now();
  return std::chrono::duration<double, std::nano>(t1 - t0).count();
}

// f() returns the result of one measurement; warm up once, measure reps times, summarize
template <class F>
stats repeat(F f, int reps = 11) {
  f();
  std::vector<double> t;
  for (int r = 0; r < reps; ++r) t.push_back(f());
  return summarize(t);
}

}  // namespace bench
```

`run_threads` gets every thread ready before releasing them together, so the timing excludes thread creation, and the first thread cannot finish before the last one has started. The moment all threads finish is established by `join`: a thread's completion synchronizes with the return of `join`, so the thread's writes are visible to the main thread ([[thread.thread.member#4]]).

!!! warning "These numbers were measured on a busy machine"
    At the time of writing, this machine was running many other processes; the load average shown by `uptime` was between 90 and 100, far beyond its 12 cores. Multithreaded wall-clock times are the most sensitive to this kind of interference: when a thread is preempted by another process, the last thread finishes later. So every table below takes the minimum of 11 runs (interference can only make times longer), and only the relative differences within one table should be read. The absolute numbers, especially in the 8- and 12-thread rows, would differ on an idle machine, and even more on another CPU.

### The ideal case: nothing shared

First, a task with no shared data at all, as the baseline for the tables that follow. The total work is fixed (200 million multiply-adds) and split evenly among t threads:

```cpp title="scaling.cpp"
#include "mt.hpp"

constexpr long K = 200'000'000;

int main() {
  bench::prefer_performance_cores();
  double base = 0;
  std::printf("threads  wall_ms  speedup\n");
  for (int t : {1, 2, 4, 6, 8, 10, 12}) {
    auto s = bench::repeat([t] {
      return bench::run_threads(t, [t](int i) {
        unsigned long x = i + 1;
        for (long k = 0; k < K / t; ++k)       // one dependency chain of multiply-adds
          x = x * 6364136223846793005ul + 1442695040888963407ul;
        bench::do_not_optimize(x);
      });
    });
    if (t == 1) base = s.min;
    std::printf("%7d %8.1f %8.2f\n", t, s.min / 1e6, base / s.min);
  }
}
```

| Threads | 1 | 2 | 4 | 6 | 8 | 10 | 12 |
|---|---|---|---|---|---|---|---|
| Wall time (ms) | 197.5 | 102.7 | 52.5 | 36.9 | 28.7 | 23.3 | 23.8 |
| Speedup | 1.00 | 1.92 | 3.77 | 5.35 | 6.89 | 8.47 | 8.31 |

Up to 8 threads it is close to linear. Threads beyond that can only land on E-cores or time-share with other processes, and the gain shrinks noticeably. Wherever a later table does worse than this curve, the cause is sharing between threads.

## False sharing

### Each writes its own, yet they slow each other down

Each thread has its own counter that only it writes. Three layouts: counters packed next to each other, 8 bytes each; each aligned to 64 bytes; each aligned to 128 bytes.

```cpp title="falseshare.cpp"
#include "mt.hpp"
#include <new>

constexpr long N = 20'000'000;          // increments per thread

struct Packed { std::atomic<long> v; };
template <std::size_t A>
struct alignas(A) Padded { std::atomic<long> v; };
constexpr auto D = std::hardware_destructive_interference_size;

template <class Slot>
double ns_per_inc(int threads) {
  static Slot slots[16];
  return bench::repeat([&] {
    return bench::run_threads(threads, [&](int i) {
      auto* p = &slots[i].v;
      bench::do_not_optimize(p);         // all three layouts generate the same addressing instructions
      for (long k = 0; k < N; ++k)       // only this thread writes *p: load, add one, store
        p->store(p->load(std::memory_order::relaxed) + 1,
                 std::memory_order::relaxed);
    }) / N;
  }).min;
}

int main() {
  bench::prefer_performance_cores();
  std::printf("threads  packed  pad64  pad128  (ns per increment)\n");
  for (int t : {1, 2, 4, 8, 12})
    std::printf("%7d %7.2f %6.2f %7.2f\n", t, ns_per_inc<Packed>(t),
                ns_per_inc<Padded<64>>(t), ns_per_inc<Padded<D>>(t));
}
```

The counters are relaxed atomics only so that every increment really reads and writes memory (an ordinary `long` would be kept in a register by the compiler and the loop folded into a single addition). Each counter is written by only one thread, so loading then storing loses no increments. The numbers in the table are wall time divided by the per-thread count, that is, the average time for one thread to do one increment; if the threads did not interfere, this column would not change with the thread count.

| Threads | Packed (8 bytes) | Aligned to 64 | Aligned to 128 |
|---|---|---|---|
| 1 | 0.31 ns | 0.32 ns | 0.31 ns |
| 2 | 1.59 | 0.74 | 0.33 |
| 4 | 1.87 | 0.66 | 0.60 |
| 8 | 2.24 | 0.95 | 0.72 |
| 12 | 3.02 | 1.05 | 0.62 |

With one thread all three layouts are equally fast; 0.31 ns is about one clock cycle. With two threads the packed version is 5 times slower, while the version aligned to 128 bytes is barely affected. Aligning to 64 bytes solves only half the problem: the cache line on our test machine is 128 bytes, so two adjacent 64-byte slots are still in the same line. The version aligned to 128 also slows down at 4 or more threads; on our test machine this part has to do with the busy machine (when a thread is preempted, the last one finishes late) and needs to be remeasured on an idle machine.

### Why

Multicore CPUs use a **cache coherence protocol** to make the caches of all cores look like a single memory. The specific protocol varies by CPU, but the common rule is: for a core to write a cache line, it must first own it exclusively, and copies in other cores' caches are invalidated. So when two cores take turns writing the same line, the line bounces back and forth between them, and every write may have to wait for a transfer between cores instead of completing in its own L1 in one cycle.

The two threads here write different variables; in the C++ sense there is no conflict at all. The standard counts each scalar object as a separate [[g:memory-location]] and says explicitly that two threads accessing different memory locations do not interfere ([[intro.memory#3]]), so this code has no [[g:data-race]] and the result is entirely correct. The interference happens only at the hardware level: the coherence protocol works in units of cache lines and does not know how many C++ objects a line holds. This slowdown, caused by data that is not shared logically but physically shares a cache line, is called **false sharing**.

### `hardware_destructive_interference_size`

Since C++17, `<new>` provides two constants ([[P0154R1]], [[hardware.interference]]). `hardware_destructive_interference_size` is the recommended minimum offset between two concurrently accessed objects, intended precisely to avoid the situation above ([[hardware.interference#1]]):

!!! std
    This number is the minimum recommended offset between two concurrently-accessed objects to avoid additional performance degradation due to contention introduced by the implementation.

    Two concurrently accessed objects should be at least this many bytes apart to avoid extra contention introduced by the implementation (the cache line).

Its value is implementation-defined. libc++ uses the compiler's predefined macros `__GCC_DESTRUCTIVE_SIZE` and `__GCC_CONSTRUCTIVE_SIZE` directly; Clang 23 gives the following values for different targets (`clang++ --target=… -dM -E -x c++ /dev/null`):

| Target | destructive | constructive |
|---|---|---|
| `arm64-apple-darwin` (our test machine) | 128 | 64 |
| `aarch64-linux-gnu` | 256 | 64 |
| `x86_64-linux-gnu`, `x86_64-apple-darwin` | 64 | 64 |

The 128 on our test machine matches `hw.cachelinesize`. Note that it is a compile-time constant that depends on the target and options at compile time, not a hardware parameter queried at run time: a program compiled for x86-64 and run on the M2 under Rosetta 2 sees 64. Using it in an `alignas` in a header makes class layout vary with compiler options; this ABI risk is explained on the [[support.dynamic]] page.

Usage is to put an `alignas` on each object that needs separating:

<div class="compare" markdown="1">

```cpp
struct Stats {               // false sharing
  std::atomic<long> hits;    // written by thread A
  std::atomic<long> misses;  // written by thread B
};
```

```cpp
struct Stats {
  alignas(std::hardware_destructive_interference_size)
    std::atomic<long> hits;
  alignas(std::hardware_destructive_interference_size)
    std::atomic<long> misses;
};
```

</div>

The `Stats` on the right takes 256 bytes on our test machine. When a type whose alignment exceeds `__STDCPP_DEFAULT_NEW_ALIGNMENT__` is allocated with `new` or `std::vector`, since C++17 the allocation function taking `std::align_val_t` is called, and alignment is guaranteed ([[expr.new]]).

!!! pitfall "Where false sharing hides"
    Besides explicit arrays of counters, common cases are: result arrays partitioned by thread index, such as `std::vector<long> per_thread(n)`; two fields of one struct written by different threads; a lock and the data it protects that another thread reads frequently; and small-object allocations. Allocators usually place small blocks requested one after another at adjacent addresses; the `shared_ptr` section below has a measured example.

## Contention on one atomic variable

False sharing is unnecessary sharing; if all threads really do need to update the same variable, the contention cannot be removed by alignment. The most common example is a statistics counter:

```cpp title="counter.cpp"
#include "mt.hpp"

constexpr long K = 10'000'000;           // each thread counts K times
std::atomic<long> total{0};

template <std::memory_order MO>
void shared_counter(int) {
  for (long k = 0; k < K; ++k) total.fetch_add(1, MO);
}

void local_then_reduce(int) {
  long local = 0;
  for (long k = 0; k < K; ++k) {
    ++local;
    bench::do_not_optimize(local);       // keep the compiler from folding the loop into local = K
  }
  total.fetch_add(local, std::memory_order::relaxed);
}

int main() {
  bench::prefer_performance_cores();
  std::printf("threads  relaxed  seq_cst   local  (ns per increment)\n");
  for (int t : {1, 2, 4, 8, 12}) {
    auto per = [t](auto f) {
      return bench::repeat([&] { return bench::run_threads(t, f); }).min /
             (double(K) * t);            // wall time / total count
    };
    double a = per(shared_counter<std::memory_order::relaxed>);
    double b = per(shared_counter<std::memory_order::seq_cst>);
    double c = per(local_then_reduce);
    std::printf("%7d %8.2f %8.2f %7.3f\n", t, a, b, c);
  }
}
```

The numbers in this table are wall time divided by the total count across all threads, that is, how long on average the whole system takes to complete one increment. Ideally, doubling the threads halves this number.

| Threads | Shared, relaxed | Shared, seq_cst | Accumulate locally, then combine |
|---|---|---|---|
| 1 | 2.08 ns | 4.04 ns | 0.309 ns |
| 2 | 3.34 | 10.97 | 0.164 |
| 4 | 7.12 | 14.46 | 0.079 |
| 8 | 10.49 | 13.81 | 0.050 |
| 12 | 11.19 | 15.66 | 0.051 |

Total throughput of the shared counter drops as threads are added: 8 threads doing the same number of increments are 5 times slower than 1 thread. Every `fetch_add` needs exclusive ownership of this cache line, so the updates of all threads effectively queue up and only one core can proceed at a time; on top of the queuing comes the time to move the cache line between cores. The locally accumulating version matches the ideal curve from the previous section, close to linear up to 8 threads; the final 12 `fetch_add`s are negligible.

As for correctness: each thread adds its local sum to `total` only at the end, and the main thread reads it after `join`, which provides the synchronization, so relaxed is enough. Why relaxed read-modify-writes do not lose increments is explained in the section on relaxed counters in [[topics/memory-model]].

If you really need a live global count, the usual compromise is sharding: prepare several counters aligned to cache lines, have each thread update one of them according to its index, and add them up when reading. The sum read is not an exact snapshot of one instant, but each shard sees far less contention.

!!! note "C++26 `store_add`"
    C++26 adds operations such as `store_add` and `store_sub` to integer and floating-point atomic types that do not return the old value ([[P3111R8]]); the standard calls them [[g:atomic-modify-write-operation|atomic modify-write operations]] ([[atomics.order#12]]). Their synchronization requirements are weaker than `fetch_add`'s: the standard's note explains the intent is to let implementations use hardware mechanisms that are not ordered by acquire fences. At the time of writing, the libc++ on our test machine does not implement `store_add`.

## The cost of memory orders

The semantics of `memory_order` are in [[topics/memory-model]]; here we look only at which instructions they produce on our test machine and how long they take.

### Generated instructions

```cpp title="mo.cpp"
#include <atomic>
std::atomic<long> c;
void add_relaxed() { c.fetch_add(1, std::memory_order::relaxed); }
void add_seq_cst() { c.fetch_add(1); }                 // seq_cst by default
void store_relaxed(long v) { c.store(v, std::memory_order::relaxed); }
void store_seq_cst(long v) { c.store(v); }
long load_acquire() { return c.load(std::memory_order::acquire); }
long load_seq_cst() { return c.load(); }
```

The key instructions generated by `clang++ -std=c++2c -O2 -S` on our test machine, compared with `--target=x86_64-linux-gnu` and `--target=aarch64-linux-gnu` (for the cross-compiles there were no matching standard library headers, so the equivalent `__atomic_*` builtins were used):

| Operation | arm64 macOS (`-mcpu=apple-m1`) | x86-64 | aarch64 Linux (default ARMv8.0) |
|---|---|---|---|
| `fetch_add` relaxed | `ldadd` | `lock inc` | `ldxr` / `stxr` loop |
| `fetch_add` acq_rel, seq_cst | `ldaddal` | `lock inc` | `ldaxr` / `stlxr` loop |
| `store` relaxed | `str` | `mov` | `str` |
| `store` seq_cst | `stlr` | `xchg` | `stlr` |
| `load` acquire | `ldapr` | `mov` | |
| `load` seq_cst | `ldar` | `mov` | `ldar` |

A few points worth noting:

- The arm64 `ldadd` family are ARMv8.1 LSE atomic instructions that do load-add-store in a single instruction. The suffix `a` means acquire semantics, `l` means release semantics, and `al` both. All Apple chips support LSE, so Clang generates them by default for `arm64-apple-darwin`.
- When compiling for generic ARMv8.0 there is no LSE, and only `ldxr`/`stxr` (load-exclusive, store-exclusive) can be used, written as a retry-on-failure loop; with `-march=armv8.1-a` they become `ldadd`/`ldaddal`, and with `-moutline-atomics` they become calls to helper functions such as `__aarch64_ldadd8_relax`, which choose the instructions at run time. On Linux servers, the cost of atomic operations in the same source can differ depending on compiler options.
- On x86-64 every read-modify-write instruction carries the `lock` prefix and is a full barrier by itself, so relaxed and seq_cst `fetch_add` are the same instruction; only the seq_cst `store` differs (`xchg` instead of `mov`). Measuring relaxed and seq_cst as equally fast on x86 does not carry over to ARM.
- arm64 acquire loads use `ldapr` (the ARMv8.3 RCpc instruction) and seq_cst loads use `ldar`. The difference is that `ldar` cannot pass an earlier `stlr`, which is exactly the store buffering seq_cst has to forbid.

### Measured times

Single-threaded, uncontended, the same loop body with different memory orders, measured with bench.hpp's `run`:

```cpp title="memorder.cpp"
#include "mt.hpp"
using std::memory_order;
constexpr auto R = memory_order::relaxed, Acq = memory_order::acquire,
               Rel = memory_order::release, AR = memory_order::acq_rel,
               SC = memory_order::seq_cst;

std::atomic<long> a{0}, b{0};
long k = 0, s = 0;

int main() {
  bench::prefer_performance_cores();
  bench::run("fetch_add relaxed", [] { a.fetch_add(1, R); });
  bench::run("fetch_add acq_rel", [] { a.fetch_add(1, AR); });
  bench::run("fetch_add seq_cst", [] { a.fetch_add(1, SC); });
  bench::run("store relaxed", [] { a.store(++k, R); });
  bench::run("store seq_cst", [] { a.store(++k, SC); });
  bench::run("load relaxed", [] { s += a.load(R); });
  bench::run("load acquire", [] { s += a.load(Acq); });
  bench::run("load seq_cst", [] { s += a.load(SC); });
  bench::run("store Rel, load Acq", [] { a.store(++k, Rel); s += b.load(Acq); });
  bench::run("store SC, load SC", [] { a.store(++k, SC); s += b.load(SC); });
  bench::do_not_optimize(s);
}
```

| Operation | Instruction | Per operation (minimum / median of 31 samples) |
|---|---|---|
| `fetch_add` relaxed | `ldadd` | 1.94 / 2.04 ns |
| `fetch_add` acq_rel | `ldaddal` | 3.99 / 4.04 ns |
| `fetch_add` seq_cst | `ldaddal` | 3.99 / 4.04 ns |
| `store` relaxed | `str` | 0.31 / 0.32 ns |
| `store` seq_cst | `stlr` | 0.31 / 0.52 ns |
| `load` relaxed | `ldr` | 0.11 / 0.13 ns |
| `load` acquire | `ldapr` | 1.15 / 1.36 ns |
| `load` seq_cst | `ldar` | 1.15 / 2.62 ns |
| `store` release then `load` acquire (different variables) | `stlr` + `ldapr` | 0.46 / 0.47 ns |
| `store` seq_cst then `load` seq_cst (different variables) | `stlr` + `ldar` | 0.46 / 0.46 ns |

The difference is clearest for read-modify-write operations: the same loop, with the same single atomic instruction, and `ldaddal` is twice as slow as `ldadd`. In this test on our test machine, `stlr` with release is no different from a plain `str`; `stlr` followed by `ldar` is where seq_cst's extra cost over acquire/release should lie, but we measured no difference on our test machine either. These conclusions hold only for this chip and this kind of uncontended loop.

Relaxed and acquire loads differ by 10x, but most of the difference is not in the instruction itself. Look at the assembly of the two loops:

<div class="compare" markdown="1">

```text
; s += a.load(relaxed)
; s stays in a register, loop unrolled 4 times
LBB0_3:
  ldr  x16, [x11, _a@PAGEOFF]
  add  x9, x9, x16
  ldr  x16, [x11, _a@PAGEOFF]
  add  x12, x12, x16
  ...
```

```text
; s += a.load(acquire)
; s is loaded from and stored to memory every time
LBB1_2:
  ldapr x10, [x8]
  ldr   x11, [x9, _s@PAGEOFF]
  add   x10, x11, x10
  str   x10, [x9, _s@PAGEOFF]
  subs  x0, x0, #1
  b.ne  LBB1_2
```

</div>

Reads and writes after an acquire load cannot be moved before it (this is where the definition of happens before in [[intro.races]] comes from). Another thread might have modified `s` before a release and then synchronized via this acquire load, so the compiler cannot keep `s` cached in a register across the acquire load, and every iteration has to actually load and store memory. Memory orders constrain the compiler first and the CPU second; their cost often shows up as optimizations that are forbidden.

### Under contention

In the counter table in the previous section, the shared `seq_cst` counter was 1.3 to 3 times slower than relaxed at 2 or more threads, a larger factor than the 2x uncontended. For counters that only collect statistics and are not used to publish other data, relaxed is both correct and cheapest; the default `seq_cst` exists to make reasoning simplest, not because counting needs it.

## Mutexes, spinlocks and atomics

The same counter with three kinds of protection: `std::mutex`; a test-and-test-and-set spinlock (grab the lock with `exchange`, and if that fails, wait with plain loads until the lock looks free, then grab again); and a direct atomic `fetch_add`.

```cpp title="locks.cpp"
#include "mt.hpp"
#include <mutex>

constexpr long K = 2'000'000;            // each thread adds K times

class Spinlock {                         // test-and-test-and-set
  std::atomic<bool> locked_{false};
public:
  void lock() {
    while (locked_.exchange(true, std::memory_order::acquire))
      while (locked_.load(std::memory_order::relaxed)) {}
  }
  void unlock() { locked_.store(false, std::memory_order::release); }
};

long plain = 0;
std::mutex m;
Spinlock spin;
std::atomic<long> a{0};

int main() {
  bench::prefer_performance_cores();
  std::printf("threads   mutex    spin  atomic  (ns per increment)\n");
  for (int t : {1, 2, 4, 8, 12}) {
    auto per = [t](auto f) {
      return bench::repeat([&] { return bench::run_threads(t, f); }).min /
             (double(K) * t);
    };
    double x = per([](int) {
      for (long k = 0; k < K; ++k) { std::lock_guard g(m); ++plain; }
    });
    double y = per([](int) {
      for (long k = 0; k < K; ++k) { std::lock_guard g(spin); ++plain; }
    });
    double z = per([](int) {
      for (long k = 0; k < K; ++k) a.fetch_add(1, std::memory_order::relaxed);
    });
    std::printf("%7d %7.1f %7.1f %7.1f\n", t, x, y, z);
  }
}
```

`Spinlock` has `lock` and `unlock`, meets *BasicLockable*, and can be handed straight to `std::lock_guard`. The release store in `unlock` synchronizes with the next successful acquire `exchange`, so every read and write of `plain` is ordered by happens before; running this program with `-fsanitize=thread` (with a smaller `K`), TSan reports nothing. For `std::mutex`, the synchronization of `unlock` with a later `lock` is guaranteed by the standard ([[thread.mutex.requirements.mutex.general#8]]).

The table shows wall time divided by the total count:

| Threads | `std::mutex` | Spinlock | Atomic `fetch_add` |
|---|---|---|---|
| 1 | 6.1 ns | 4.9 ns | 2.1 ns |
| 2 | 11.3 | 20.3 | 4.3 |
| 4 | 22.7 | 24.8 | 9.8 |
| 8 | 18.8 | 71.2 | 9.9 |
| 12 | 18.9 | 126.0 | 20.1 |

- Uncontended, the spinlock is slightly faster than `std::mutex`: locking and unlocking are one atomic instruction each, while `std::mutex` in libc++ wraps `pthread_mutex_t` and goes through a function call and more checks.
- Under contention, the spinlock deteriorates quickly with the thread count. All waiting threads read the same cache line; as soon as the lock is released, all waiters `exchange` at once, and the line is fought over again. Worse, if the lock holder is descheduled by the operating system (common when there are more threads than idle cores, which was the machine's state during measurement), the other threads can only spin for an entire time slice.
- Under contention `std::mutex` puts waiting threads to sleep to be woken by the kernel, and it does not keep getting worse at 8 and 12 threads. Each operation costs more than a spinlock's, but it does not collapse under preemption.
- When the critical section is just an integer addition, the atomic operation is fastest, but it is subject to the same single-cache-line contention described in the first section, and at 12 threads it is no faster than at 1.

In a repeated run under somewhat lower load, the `std::mutex` column was 6.1, 7.6, 13.8, 15.3, 15.8 ns, and the spinlock was 174 and 281 ns at 8 and 12 threads; the conclusion is the same, and the spinlock's numbers fluctuate the most.

The real conclusion is the last point: none of the three makes counting scale with the thread count. The shorter and more frequent the critical section, the larger the share of locking overhead; to scale, you have to reduce the sharing itself, as in the previous section, not switch to a faster lock. Writing your own spinlock rarely pays off in a user-space program, unless you can be sure the critical section is extremely short and the thread count does not exceed the core count.

## Copying `shared_ptr`

The reference count of `shared_ptr` is maintained by the implementation with atomic operations, so multiple threads separately copying and destroying `shared_ptr`s to the same object is safe ([[util.smartptr.shared.general#5]]; the three levels of thread safety are in [[topics/ownership-and-smart-pointers]]). The price of safety is atomic operations. In libc++ on our test machine, a loop body that copies and then destroys a `shared_ptr` compiles to:

```text
ldr   x8, [x20, #8]          ; control block pointer
ldr   q0, [x20]              ; copy the two pointers
str   q0, [sp, #16]
cbz   x8, ...
add   x8, x8, #8             ; address of the shared count
ldadd x24, x8, [x8]          ; copy: count + 1, relaxed
...
ldaddal x23, x8, [x8]        ; destroy: count - 1, acq_rel (x23 = -1)
cbnz  x8, ...                ; destroy the object only when it reaches 0
```

One `ldadd` to copy, one `ldaddal` to destroy. If several threads copy `shared_ptr`s pointing to the same object, they contend on the counter in the same control block, exactly like the shared counter in the previous section.

```cpp title="sp.cpp"
#include "mt.hpp"
#include <memory>

constexpr long K = 5'000'000;

struct Config { int value = 42; };
struct alignas(128) PaddedConfig { int value = 42; };

template <class P>
void copy_loop(const P& src) {
  for (long k = 0; k < K; ++k) {
    P copy = src;                        // count + 1
    bench::do_not_optimize(copy);
  }                                      // destruction: count - 1
}

int main() {
  bench::prefer_performance_cores();
  auto shared = std::make_shared<Config>();
  std::shared_ptr<Config> own[16];
  std::shared_ptr<PaddedConfig> own_padded[16];
  for (auto& p : own) p = std::make_shared<Config>();
  for (auto& p : own_padded) p = std::make_shared<PaddedConfig>();
  std::printf("own[0..3]: %p %p %p %p\n", (void*)own[0].get(),
              (void*)own[1].get(), (void*)own[2].get(), (void*)own[3].get());

  std::printf("threads  same  own  own_padded  by_ref  (ns per copy)\n");
  for (int t : {1, 2, 4, 8, 12}) {
    auto per = [t](auto f) {
      return bench::repeat([&] { return bench::run_threads(t, f); }).min /
             (double(K) * t);
    };
    double a = per([&](int) { copy_loop(shared); });
    double b = per([&](int i) { copy_loop(own[i]); });
    double c = per([&](int i) { copy_loop(own_padded[i]); });
    double d = per([&](int) {
      for (long k = 0; k < K; ++k) {
        const auto& ref = shared;        // no copy, just borrow
        bench::do_not_optimize(ref->value);
      }
    });
    std::printf("%7d %6.2f %5.2f %11.2f %7.2f\n", t, a, b, c, d);
  }
}
```

| Threads | Same object | Own objects | Own objects, aligned to 128 | No copy, by reference |
|---|---|---|---|---|
| 1 | 5.11 ns | 5.38 ns | 5.13 ns | 1.39 ns |
| 2 | 13.45 | 2.58 | 2.71 | 0.81 |
| 4 | 17.01 | 1.40 | 1.61 | 0.70 |
| 8 | 24.15 | 8.75 | 0.90 | 0.38 |
| 12 | 31.23 | 4.54 | 0.81 | 0.31 |

(Wall time divided by the total count.)

The first column is the expected contention: one copy plus destruction takes about 5 ns single-threaded, and at 8 threads total throughput actually drops to about a fifth of single-threaded.

The second column is a less obvious case of false sharing. Each thread copies its own `shared_ptr` to a distinct object, yet at 8 threads it is still nearly 10 times slower than the aligned version. The addresses the program prints show why:

```text
own[0..3]: 0x101585d78 0x101585d98 0x101585b78 0x101585b98
```

`make_shared<Config>` puts the control block and the `Config` in a single 32-byte allocation, and the allocator places consecutive allocations at adjacent addresses 32 bytes apart, so four control blocks are crammed into the same 128-byte cache line. The third column aligns the objects to 128 bytes, separating the control blocks along with the objects, and the false sharing disappears.

The fourth column shows that most of the time no copy is needed at all. For functions that only use the object for the duration of the call, write the parameter as `const T&` or `T*`, or `const shared_ptr<T>&`, which does not touch the reference count; take `shared_ptr` by value only where you need to extend the object's life and store ownership. This parameter-passing rule is discussed fully in [[topics/ownership-and-smart-pointers]].

## Starting threads and thread pools

The last easily overlooked cost is threads themselves. Below we compare four ways of running 2000 tiny tasks: create a new `std::jthread` per task and `join` it immediately; call `std::async(std::launch::async, …)` once per task and `get()`; hand tasks to a pre-created pool of 8 threads, submitting one and waiting for it to finish before submitting the next; and hand all 2000 tasks to the pool at once and wait once at the end.

```cpp title="pool.cpp"
#include "mt.hpp"
#include <condition_variable>
#include <deque>
#include <functional>
#include <future>
#include <mutex>

class Pool {
  std::mutex m_;
  std::condition_variable cv_;
  std::deque<std::function<void()>> q_;
  bool stop_ = false;
  std::vector<std::jthread> workers_;
public:
  explicit Pool(int n) {
    for (int i = 0; i < n; ++i)
      workers_.emplace_back([this] {
        bench::prefer_performance_cores();
        for (;;) {
          std::function<void()> job;
          {
            std::unique_lock lk(m_);
            cv_.wait(lk, [this] { return stop_ || !q_.empty(); });
            if (q_.empty()) return;          // stop_ and the queue is empty
            job = std::move(q_.front());
            q_.pop_front();
          }
          job();
        }
      });
  }
  void submit(std::function<void()> f) {
    { std::lock_guard lk(m_); q_.push_back(std::move(f)); }
    cv_.notify_one();
  }
  ~Pool() {
    { std::lock_guard lk(m_); stop_ = true; }
    cv_.notify_all();
  }                                          // workers_ join in their destructors
};

constexpr int Tasks = 2000;
std::atomic<int> done{0};

double ns_per_task(auto f) {
  return bench::repeat([&] {
    auto t0 = std::chrono::steady_clock::now();
    f();
    auto t1 = std::chrono::steady_clock::now();
    return std::chrono::duration<double, std::nano>(t1 - t0).count() / Tasks;
  }).min;
}

int main() {
  bench::prefer_performance_cores();
  auto tiny = [] { done.fetch_add(1, std::memory_order::relaxed); };

  double create = ns_per_task([&] {        // start a thread, run, join, one after another
    for (int i = 0; i < Tasks; ++i) std::jthread(tiny).join();
  });
  double async = ns_per_task([&] {
    for (int i = 0; i < Tasks; ++i) std::async(std::launch::async, tiny).get();
  });
  Pool pool(8);
  double pooled = ns_per_task([&] {        // submit to the pool, wait until done, then submit the next
    for (int i = 0; i < Tasks; ++i) {
      std::atomic<bool> f{false};
      pool.submit([&] { tiny(); f.store(true, std::memory_order::release);
                        f.notify_one(); });
      f.wait(false, std::memory_order::acquire);
    }
  });
  double batch = ns_per_task([&] {         // submit all tasks at once, wait once at the end
    int start = done.load();
    for (int i = 0; i < Tasks; ++i) pool.submit(tiny);
    while (done.load() - start < Tasks) std::this_thread::yield();
  });
  std::printf("thread create+join  %8.0f ns\n", create);
  std::printf("std::async + get    %8.0f ns\n", async);
  std::printf("pool round trip     %8.0f ns\n", pooled);
  std::printf("pool batch          %8.0f ns\n", batch);
}
```

| Method | Per task (minimum of 11 rounds per run, range over 5 runs) |
|---|---|
| New `std::jthread`, then `join` | 13–22 µs |
| `std::async(launch::async)`, then `get` | 11–23 µs |
| Thread pool, submit one and wait | 3.1–6.4 µs |
| Thread pool, submit all at once | 0.06–1.3 µs |

This table is the most sensitive to machine load; the variation across the 5 runs is larger than in any other table, so only the orders of magnitude are meaningful.

Creating a thread means asking the kernel for a thread, allocating a stack and scheduling it to run, and `join` must also wait for it to be scheduled, finish and report back; in total it takes between 10 and over 20 microseconds on our test machine, equivalent to several thousand uncontended atomic operations. `std::async` is in the same range, because libc++ implements `launch::async` by creating a new thread every time and then detaching it (the standard requires it to behave as if run in a new thread represented by a `thread` object, [[futures.async#3]]).

A thread pool saves the creation; what remains is the handoff: enqueue, wake a sleeping worker, and wake the submitter on completion. Submitting one and waiting means two cross-thread wakeups per task, about 3 to 6 µs. Submitting everything at once amortizes the wakeup cost; awake workers keep taking tasks from the queue back to back, and at best each task takes only a few dozen nanoseconds, with what remains being mostly contention between workers and the submitter for the queue's lock; when the machine is busy and workers are descheduled, it rises to about 1 µs. So tasks need to be at least one or two orders of magnitude larger than these overheads for parallelism to pay off; smaller work should be merged into chunks before being distributed.

## Common mistakes

!!! pitfall "Result arrays partitioned by thread index"
    `std::vector<long> sum(nthreads)` with thread i repeatedly writing `sum[i]` in a loop is the most common false sharing. Either accumulate in a local variable and write once at the end, or align each element to `hardware_destructive_interference_size`.

!!! pitfall "Assuming 64-byte alignment is enough"
    A lot of code hardcodes `alignas(64)` out of x86 habit. On our test machine, with two threads the 64-byte-aligned version was still more than twice as slow as the 128-byte-aligned one (0.74 ns vs 0.33 ns). On Apple chips use 128, or just use `std::hardware_destructive_interference_size`.

!!! pitfall "Measuring memory orders on x86"
    On x86, relaxed and seq_cst `fetch_add` are the same `lock` instruction, so no difference can be measured. On ARM they are `ldadd` and `ldaddal`, a 2x difference on our test machine. Choose memory orders by the standard's semantics, and measure performance on the target platform.

!!! pitfall "Trying to make counting scale with locking"
    Switching to a faster lock or to atomic operations only changes how fast the queue moves. All threads updating the same cache line is itself the scaling limit.

## Questions

!!! question "1"
    If `std::atomic<long>` in `falseshare.cpp` is replaced with a plain `long` and the increment written as `++slots[i].v`, will the three layouts still differ in speed when compiled with `-O2`? Does the change introduce a data race?

<details markdown="1">
<summary>Answer</summary>

It does not introduce a data race: each `long` is a separate memory location accessed by only one thread, which does not conflict with other threads' accesses ([[intro.memory#3]], [[intro.races#2]]), and the main thread reads only after synchronizing via `join`.

Nor will the speeds differ any more. No data race means the compiler may assume no other thread touches this `long`, and so it merges the accesses under the as-if rule ([[intro.abstract#1]]). Clang 23 at `-O2` compiles the whole loop into one `ldr`, one `add x9, x9, x1` (adding the count N) and one `str`. With no repeated memory writes, there is no bouncing of cache lines. That is exactly why measuring false sharing requires relaxed atomics or `volatile` to force every increment to access memory. In real programs, false sharing usually occurs where the compiler cannot merge like this: loops containing function calls, writes to a different address each time, or variables that are atomic to begin with.
</details>

!!! question "2"
    A server keeps its request count in a global `std::atomic<long> requests`, and every request-handling thread does `requests++`. Does changing it to `requests.fetch_add(1, std::memory_order::relaxed)` solve the scaling problem on multicore machines?

<details markdown="1">
<summary>Answer</summary>

It reduces some overhead but does not solve the scaling problem. `requests++` is equivalent to `fetch_add(1)`, that is, seq_cst ([[atomics.types.memop#2]]), which is `ldaddal` on arm64; relaxed makes it `ldadd`, dropping from about 4 ns to about 2 ns single-threaded on our test machine. But with any memory order, every addition needs exclusive ownership of the same cache line; in the `counter.cpp` table, the relaxed shared counter at 8 threads still had only a fifth of single-threaded total throughput. Scaling requires sharded counting or thread-local accumulation with periodic combining.
</details>

## Summary

| Symptom | Cause | Measured on our test machine | Remedy |
|---|---|---|---|
| Slows down even though each thread writes its own variable | False sharing: one cache line bouncing between cores | 5x slower with 2 threads | Align to `hardware_destructive_interference_size` (128 on our test machine) |
| Shared counter gets slower with more threads | All updates queue for exclusive ownership of one cache line | Total throughput at 8 threads is 1/5 of single-threaded | Thread-local accumulation then combine; sharding |
| seq_cst read-modify-write is slower | `ldaddal` vs `ldadd` on arm64 | 4 ns vs 2 ns | Use relaxed for statistics only |
| Code after an acquire load slows down | The compiler cannot cache variables across it | Loop 10x slower | Move acquire loads out of hot loops |
| Spinlock collapses under contention | Waiters fight over the cache line; lock holder preempted | More than 6x slower than mutex at 12 threads | Use `std::mutex`; reduce sharing |
| Copying `shared_ptr` doesn't scale | One atomic read-modify-write each for copy and destruction | 24 ns per copy at 8 threads | Pass by reference when borrowing; adjacent control blocks also false-share |
| Parallelizing small tasks is slower | Creating a thread takes over 10 µs, a pool handoff a few µs | | Use a thread pool; merge into larger tasks |
