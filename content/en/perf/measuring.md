---
title: Measuring so you can trust the result
summary: "Writing a microbenchmark whose results you can trust: why a naive timing loop measures 0 nanoseconds, which clock to use, how the inline asm of DoNotOptimize and ClobberMemory holds back the optimizer, warm-up, repetition and medians, sources of noise on macOS, common pitfalls, how to compare two versions fairly, and bench.hpp, the small harness shared by the rest of this section."
tags: performance, benchmarking, measurement, as-if, inline assembly, statistics
updated: 2026-10-19
group: Measurement
---

!!! tldr
    - The compiler only has to preserve the program's observable behavior ([[intro.abstract]]). Computations whose results nobody uses get deleted, constant inputs get computed ahead of time, and invariant expressions get hoisted out of loops. When a measurement comes out absurdly small, look at the assembly first.
    - Time with `steady_clock`. On our test machine its actual step is 41 ns and one `now()` takes over ten nanoseconds, so a sample has to call the code under test many times in a row, lasting on the order of a millisecond.
    - `do_not_optimize` and `clobber_memory` are inline asm statements that generate no instructions; through operand constraints they convince the compiler that a value is read and modified, and that memory is read and written. They constrain only the compiler, not the CPU.
    - Warm up before recording, repeat many times and look at the median and the distribution. The mean is pulled up by a few samples that were preempted or scheduled onto efficiency cores.
    - To compare two versions, put them in the same program and measure them alternately, and first run an A/A test to see how big the noise is; a difference smaller than the noise supports no conclusion.

All numbers in this section come from the same machine: Apple M2 Pro (8 performance cores, 4 efficiency cores), macOS, Homebrew Clang 23.1.3 + libc++, arm64, compiled with `clang++ -std=c++2c -O2` unless stated otherwise. They are observations on this machine; on another machine or compiler version the numbers will change, but the method will not. Many other processes were running on this machine while this was written (load average between 30 and 100 on 12 cores). Absolute numbers are therefore slow and scattered; what can be trusted are ratios measured back to back in the same process, and the assembly. Don't read too much into small differences in the tables. Such an environment also makes noise easier to see.

## The 0-nanosecond benchmark

```cpp title="naive.cpp" run ok
#include <chrono>
#include <cstdio>

long sum_to(long n) {
  long s = 0;
  for (long i = 0; i < n; ++i) s += i * i;
  return s;
}

int main() {
  auto t0 = std::chrono::steady_clock::now();
  for (int r = 0; r < 1000; ++r)
    sum_to(1'000'000);                  // result discarded
  auto t1 = std::chrono::steady_clock::now();
  auto ns = std::chrono::duration_cast<std::chrono::nanoseconds>(t1 - t0);
  std::printf("%lld ns per call\n", (long long)(ns.count() / 1000));
}
```

On our test machine `-O0` prints `928503 ns per call` and `-O2` prints `0 ns per call`. In the `-O2` assembly of `main`, the two `now()` calls sit right next to each other:

```text
bl   __ZNSt3__16chrono12steady_clock3nowEv
mov  x19, x0
bl   __ZNSt3__16chrono12steady_clock3nowEv
sub  x8, x0, x19          ; t1 - t0, with nothing in between
```

All 1000 calls are gone. This is allowed. The standard only requires an implementation to emulate the **observable behavior** of the abstract machine ([[intro.abstract#1]]): volatile accesses, data written to files, and the order of input and output on interactive devices ([[intro.abstract#8]]). Execution time is not on the list. `sum_to` has no side effects and its return value is discarded, so deleting it makes no difference to observable behavior. This principle is called the [[g:as-if-rule]]; the detailed discussion is in [[intro.abstract]].

Deletion is not the whole story. Even when the result is used, `sum_to` itself no longer contains a loop:

```text
__Z6sum_tol:
  subs  x8, x0, #1
  b.lt  LBB0_2
  sub   x9, x0, #2
  umulh x10, x8, x9
  mul   x8, x8, x9
  ...                     ; a dozen or so multiplications and shifts, no backward jump
  ret
```

Clang recognized the induction pattern of a sum of squares and replaced the loop with the closed form (n−1)·n·(2n−1)/6. Once the harness below blocks the deletion, `sum_to(1'000'000)` measures 1.53 ns per call on our test machine. A million iterations cannot be done in 1.5 ns; this number measures the formula, not the loop.

So the first habit is a sanity check on the order of magnitude: convert the measured time into per iteration, per element or per clock cycle, and compare it with what the hardware can do. If the order of magnitude is wrong, look at the assembly (see [[perf/reading-assembly]]).

## Which clock

`<chrono>` has three clocks that can be used for timing ([[time.clock]]):

- `system_clock` represents wall-clock time; it can be adjusted by an administrator or NTP and may jump backwards ([[time.clock.system#1]]);
- `steady_clock`'s time points never decrease, advance at a steady rate, and cannot be adjusted ([[time.clock.steady#1]]);
- `high_resolution_clock` is the clock with the shortest tick period, and may be just an alias for one of the other two ([[time.clock.hires#1]]).

!!! std
    Objects of class `steady_clock` represent clocks for which values of `time_point` never decrease as physical time advances ... That is, the clock may not be adjusted.

`period` only gives the unit of the count, not how often the clock actually ticks. The program below measures the smallest nonzero difference between two consecutive `now()` calls (the actual step), and the cost of one `now()` itself:

```cpp title="clocks.cpp" run ok
#include <chrono>
#include <cstdio>
using namespace std::chrono;

template <class C>
void probe(const char* name) {
  long long step = -1;                  // smallest nonzero difference
  for (int i = 0; i < 1'000'000; ++i) {
    auto a = C::now(), b = C::now();
    while (b == a) b = C::now();
    long long d = duration_cast<nanoseconds>(b - a).count();
    if (step < 0 || d < step) step = d;
  }
  constexpr int N = 10'000'000;         // average cost of one now()
  auto t0 = steady_clock::now();
  typename C::rep acc = 0;
  for (int i = 0; i < N; ++i) acc += C::now().time_since_epoch().count();
  double cost = duration<double, std::nano>(steady_clock::now() - t0).count() / N;
  std::printf("%-22s period %lld/%lld  steady %d  step %lld ns  now() %.1f ns  [%d]\n",
              name, (long long)C::period::num, (long long)C::period::den,
              C::is_steady, step, cost, int(acc & 1));
}

int main() {
  probe<steady_clock>("steady_clock");
  probe<system_clock>("system_clock");
  probe<high_resolution_clock>("high_resolution_clock");
}
```

Over three runs on our test machine, the step was the same every time; the cost of `now()` was about 16 ns when the machine was relatively idle and measured higher under heavy load:

| Clock | `period` | `is_steady` | Measured step | One `now()` |
|---|---|---|---|---|
| `steady_clock` | 1/10⁹ s | 1 | 41 ns | 16–22 ns |
| `system_clock` | 1/10⁶ s | 0 | 1000 ns | 17–43 ns |
| `high_resolution_clock` | 1/10⁹ s | 1 | 41 ns | 16–39 ns |

In libc++, `high_resolution_clock` is just an alias for `steady_clock` (`std::is_same_v` is true). Although `steady_clock` counts in nanoseconds, it actually ticks only every 41 ns, consistent with the 24 MHz system counter reported by `sysctl hw.tbfrequency` (1/24 MHz ≈ 41.7 ns).

Three conclusions. Use `steady_clock` to measure elapsed time; it does not jump when the clock is corrected. `high_resolution_clock` may be `system_clock` on other implementations and has no portable use. Code whose single call is shorter than a few hundred nanoseconds cannot be timed on its own, because both the step and the cost of `now()` itself are tens of nanoseconds. Have one sample call the code under test n times in a row and divide by n, and make a sample last about 1 ms; then the 41 ns step is only 0.004%.

## Holding back the optimizer

To keep the code under test from being deleted, folded or hoisted out of the loop, without adding overhead to it, the usual approach is Google Benchmark's `DoNotOptimize` and `ClobberMemory`. Each boils down to one line of inline assembly:

```cpp
template <class T>
inline void do_not_optimize(T& v) {
  asm volatile("" : "+r"(v) : : "memory");
}
inline void clobber_memory() {
  asm volatile("" : : : "memory");
}
```

This is GCC's extended inline assembly syntax, which Clang also supports. The C++ standard only says the `asm` declaration is conditionally-supported, with implementation-defined meaning ([[dcl.asm#1]]), so these two functions are not portable; MSVC's x64 compiler, for instance, does not accept inline assembly. Item by item:

| Syntax | Meaning | Effect on the optimizer |
|---|---|---|
| `""` | Empty assembly template | Generates no instructions, no run-time cost |
| `volatile` | This asm has side effects the compiler cannot see | Cannot be deleted because its outputs are unused, and cannot be hoisted out of loops |
| `"+r"(v)` | Input-output operand in a register | Before the asm, the value of `v` must really be computed; after it, `v` is treated as an unknown new value |
| `"+m"(v)` | Same, but the operand is in memory | For objects that don't fit in a register, such as arrays and structs |
| `"memory"` | Clobber list: the asm may read and write any memory | Before the asm, pending writes must really reach memory; after it, values in memory must be reloaded |

The harness's version chooses `"+r"` or `"+m"` by type, and has an extra overload taking `const T&` that uses only the input operand `"m"`, to catch temporaries; the full code is at [the end of the page](#harness).

### What it blocks

```cpp title="dno.cpp"
#include "bench.hpp"

int square(int x) { return x * x; }

void discard(int x) { int r = square(x); (void)r; }
void keep(int x) { int r = square(x); bench::do_not_optimize(r); }
void keep_const() { int r = square(12); bench::do_not_optimize(r); }
```

The `-O2` assembly on our test machine:

```text
__Z7discardi:            ; result unused: nothing left
  ret
__Z4keepi:               ; the multiplication stays; the asm itself is empty
  mul  w8, w0, w0
  ; InlineAsm Start
  ; InlineAsm End
  ret
__Z10keep_constv:        ; constant input: already computed at compile time
  mov  w8, #144
  ret
```

`do_not_optimize` only guarantees the result is computed, not that it is computed at run time. All `keep_const` keeps is the constant 144. To measure `square` itself, the input must also be opaque to the compiler, that is, call `do_not_optimize` on the input before the call as well.

### Invariant computations get hoisted out of the loop

The harness repeats the code under test n times in a loop. If every iteration has the same input, the computation is hoisted out of the loop:

<div class="compare" markdown="1">

```cpp
void hoisted(long a, long b, long n) {
  for (long i = 0; i < n; ++i) {
    long r = a / b;
    bench::do_not_optimize(r);
  }
}
```

```cpp
void opaque(long a, long b, long n) {
  for (long i = 0; i < n; ++i) {
    bench::do_not_optimize(a);
    bench::do_not_optimize(b);
    long r = a / b;
    bench::do_not_optimize(r);
  }
}
```

</div>

<div class="compare" markdown="1">

```text
  sdiv  x8, x0, x1     ; outside the loop
LBB0_2:
  mov   x9, x8
  ; InlineAsm Start
  subs  x2, x2, #1
  b.ne  LBB0_2
```

```text
LBB1_1:
  ; InlineAsm Start
  ; InlineAsm Start
  sdiv  x8, x0, x1     ; inside the loop
  ; InlineAsm Start
  subs  x2, x2, #1
  b.ne  LBB1_1
```

</div>

On the left, the division is done once, and the loop contains only the empty asm and the counter. Measured with the harness, the left side takes 0.31 ns per iteration and the right 0.61 ns. 0.31 ns is about one clock cycle, exactly the cost of this empty loop itself.

What the right side measures is also only the division's throughput: the divisions in different iterations are independent and can overlap. To measure latency, the next input has to depend on the previous result (for example `a = a / b + c`); measured this way on our test machine it is about 2.8 ns per iteration. Whether a microbenchmark measures throughput or latency depends on this kind of dependency; decide which one you want before writing it.

### Writes nobody reads get deleted

```cpp
bench::run("fill", [] {
  int buf[1024];
  std::fill(buf, buf + 1024, 7);
});
bench::run("fill, kept", [] {
  int buf[1024];
  std::fill(buf, buf + 1024, 7);
  bench::do_not_optimize(buf);       // "+m" plus "memory"
});
```

On our test machine the first takes 0.00 ns and the second 41.8 ns. `buf` is destroyed right after being written and nobody reads it, so the writes are dead stores and can be deleted entirely. `do_not_optimize(buf)` declares that the asm reads this memory, so the writes must complete first. When you only want to say that any memory may be read, without involving a particular variable, use `clobber_memory()`, for example when the code under test writes to an external buffer.

### Other approaches

Writing the result to a volatile variable also prevents deletion, and needs no inline assembly:

```cpp
volatile int sink;
bench::run("volatile sink", [&] {
  sink = std::accumulate(v.begin(), v.end(), 0);
});
```

Accesses through a volatile glvalue are observable behavior and must be performed strictly according to the abstract machine ([[intro.execution#7]], [[intro.abstract#8]]), so every result has to be computed and written. Summing 4096 `int`s on our test machine measures about 143 ns this way, and about 145 ns with `do_not_optimize`; the two are comparable. Its limitation is that it only protects the output: constant inputs are still folded, and it costs one real store each time.

!!! pitfall "noinline is not a barrier"
    Marking the function under test `[[gnu::noinline]]` only prevents inlining, not deletion. For `[[gnu::noinline]] long sum_to(long)` and `void caller() { sum_to(1'000'000); }`, Clang still generates just a `ret`: the compiler works out that `sum_to` has no side effects and deletes the call. Constant propagation across the function boundary also still happens.

!!! note "Can the timing calls themselves prevent reordering?"
    `steady_clock::now()` is an opaque external call to the compiler. A pure register computation that does not access memory may, under the as-if rule, be moved outside the two `now()` calls. In our test with Clang, an integer loop between two `now()` calls was not moved, but this is not guaranteed. Inside the timed interval, the harness calls `do_not_optimize` with `"memory"` on the result; since both the asm and `now()` may access memory, the compiler cannot swap their order.

## Warm-up: the first time is always slow

The same code faces a different machine state the first time it runs than afterwards:

- **Page faults**: newly allocated memory is mapped to physical pages by the operating system only on first write, one page fault per page. The page size on our test machine is 16 KiB;
- **Caches**: data and instructions have to come from slower levels the first time;
- **Branch predictor**: it has to see a branch a few times before predicting it well;
- **CPU frequency and scheduling**: the core may be at a low frequency, and the thread may land on an efficiency core first.

```cpp title="first.cpp"
#include "bench.hpp"
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <memory>
#include <numeric>
#include <sys/resource.h>
#include <vector>
using clk = std::chrono::steady_clock;

long page_faults() {
  rusage r;
  getrusage(RUSAGE_SELF, &r);
  return r.ru_minflt + r.ru_majflt;
}
double us_since(clk::time_point t0) {
  return std::chrono::duration<double, std::micro>(clk::now() - t0).count();
}

int main() {
  bench::prefer_performance_cores();
  constexpr std::size_t n = 8 << 20;             // 8M ints = 32 MiB
  std::unique_ptr<int[]> p(new int[n]);          // uninitialized: pages not mapped yet
  for (int pass = 1; pass <= 3; ++pass) {
    long f0 = page_faults();
    auto t0 = clk::now();
    std::fill(p.get(), p.get() + n, pass);
    double us = us_since(t0);
    bench::do_not_optimize(p[n / 2]);
    std::printf("fill pass %d: %7.0f us, %ld page faults\n",
                pass, us, page_faults() - f0);
  }
  std::vector<int> v(1 << 18, 1);                // 1 MiB, already written once
  for (int call = 1; call <= 5; ++call) {
    auto t0 = clk::now();
    int s = std::accumulate(v.begin(), v.end(), 0);
    bench::do_not_optimize(s);
    std::printf("sum call %d: %5.1f us\n", call, us_since(t0));
  }
}
```

Ranges over three runs on our test machine:

| | 1st | 2nd | 3rd and later |
|---|---|---|---|
| Fill 32 MiB | 2.7–3.0 ms, 2048 page faults | 0.95–1.25 ms, 0 page faults | 0.55–0.59 ms |
| Sum 1 MiB | 18.5–20.6 µs | 12.3–12.6 µs | 12.2 µs |

2048 page faults is exactly 32 MiB ÷ 16 KiB. The first fill is about five times slower than the steady state, mostly due to page faults. The second fill has no page faults but is still about twice as slow as the third; we did not find out why on our test machine, and with a 64 MiB buffer the second fill was sometimes even slower than the first. Whatever the cause, measuring only once includes these one-time costs.

The harness calls the code a few rounds first and discards the results before it starts recording. Be aware that warm-up can also hide reality: if in the real program this code runs only once, or always faces cold data, measuring the steady state answers the wrong question. Which one to measure depends on the question you want answered.

## Repetition and statistics

Even after warm-up, the time taken by the same code is not a fixed number. Below we sum 4096 `int`s, with each sample calling 64 times in a row (about 10 µs), and record 3000 samples:

```cpp title="dist.cpp"
#include "bench.hpp"
#include <algorithm>
#include <cstdio>
#include <limits>
#include <numeric>
#include <vector>

int main() {
  bench::prefer_performance_cores();
  std::vector<int> v(4096, 1);
  auto f = [&] {
    int s = std::accumulate(v.begin(), v.end(), 0);
    bench::do_not_optimize(s);
  };
  std::vector<double> t;
  for (int i = 0; i < 3000; ++i) t.push_back(bench::sample(f, 64));
  double mean = std::accumulate(t.begin(), t.end(), 0.0) / t.size();
  std::sort(t.begin(), t.end());
  auto q = [&](double p) { return t[std::size_t(p * (t.size() - 1))]; };
  std::printf("min %.1f  median %.1f  p90 %.1f  p99 %.1f  max %.1f  mean %.1f\n",
              q(0), q(.5), q(.9), q(.99), q(1), mean);
  double inf = std::numeric_limits<double>::infinity();
  double edges[] = {0, 150, 160, 200, 290, 330, 1000, inf};
  for (int b = 0; b + 1 < 8; ++b)
    std::printf("[%4.0f, %4.0f)  %ld\n", edges[b], edges[b + 1],
                std::count_if(t.begin(), t.end(), [&](double x) {
                  return x >= edges[b] && x < edges[b + 1]; }));
}
```

Results of one run on our test machine (in ns per call):

| Range | Samples |
|---|---|
| [0, 150) | 2558 |
| [150, 160) | 200 |
| [160, 200) | 4 |
| [200, 290) | 0 |
| [290, 330) | 208 |
| [330, 1000) | 24 |
| [1000, ∞) | 6 |

min 143.9, median 145.8, p90 153.0, p99 315.8, max 6033.2, **mean 164.1**. In two other runs, the medians were 145.2 and 145.2, the means 165.7 and 164.9, and 360 and 349 samples fell in [290, 330).

The distribution is not bell-shaped but a narrow peak plus a long tail, with a second peak in the tail. The second peak is around 300 ns, almost exactly twice the main peak; the next section shows this is the thread being placed on an efficiency core. The largest sample is 40 times the main peak; samples like that are usually the thread being preempted in the middle of a sample.

On such a distribution the mean is not representative: it is larger than more than 90% of the samples, and depends on how much interference this run happened to meet. Each statistic has its use:

| Statistic | Question it answers | Weakness |
|---|---|---|
| Median | How fast a typical run is | Insensitive to the tail |
| Minimum | How fast it can be with no interference | Reflects only the best case, may be a fluke |
| p90, p99, max | How heavy the tail is | Needs many samples to stabilize |
| Mean | Total time ÷ count | Skewed by a few outliers |

The harness reports the median, along with the minimum and maximum as hints of the spread. Compare versions by the median; when the minimum is far from the median and the maximum is several times the median, the measurement was badly disturbed and should be rerun rather than trusting any number. When the real program cares about latency tails (for example per-frame or per-request time), measure the tail specifically; the median alone won't do.

## Noise sources on macOS

### Performance and efficiency cores

The M2 Pro has 8 performance cores and 4 efficiency cores (`sysctl hw.perflevel0.logicalcpu hw.perflevel1.logicalcpu` prints 8 and 4). The same code can run more than twice as fast on one kind of core as on the other. On Linux, `taskset` can pin a process to specific cores; macOS offers no such interface, and the scheduler's choice can only be influenced through quality-of-service (QoS) classes:

```cpp title="qos.cpp"
#include "bench.hpp"
#include <cstring>
#include <numeric>
#include <pthread.h>
#include <vector>

int main(int argc, char** argv) {
  bool bg = argc > 1 && std::strcmp(argv[1], "background") == 0;
  pthread_set_qos_class_self_np(
      bg ? QOS_CLASS_BACKGROUND : QOS_CLASS_USER_INTERACTIVE, 0);
  std::vector<int> v(4096, 1);
  bench::run(bg ? "background" : "user-interactive", [&] {
    int s = std::accumulate(v.begin(), v.end(), 0);
    bench::do_not_optimize(s);
  });
}
```

Alternating three runs on our test machine: the `user-interactive` median is 146.0–146.6 ns; the `background` median is 579–751 ns, with a minimum of 302–322 ns. According to Apple's documentation, on Apple silicon `QOS_CLASS_BACKGROUND` threads are scheduled only on efficiency cores. The minimum we measured, about twice the performance-core time, is consistent with this and corresponds exactly to the second peak in the previous section's distribution; the median is higher because when the machine is busy, the efficiency cores are also occupied by other processes.

The harness's `prefer_performance_cores()` sets the thread to `QOS_CLASS_USER_INTERACTIVE`. It is only a hint, not pinning: the distribution in the previous section was measured with this setting, and with the system busy, 7%–12% of samples in three runs still landed around 300 ns.

### Other interference

- **Background load**: other processes preempt the CPU and share caches and memory bandwidth. Close unnecessary programs while measuring, and note the load (`uptime`) in reports. The numbers on this page were measured at a load average above 30; medians remained stable, while tails got noticeably heavier.
- **Temperature**: sustained full load may trigger throttling, showing up as samples slowly getting slower over time. We did not measure this separately on our test machine; to check, plot the samples in time order and look for a trend.
- **Power**: on a laptop running on battery or in Low Power Mode, the frequency ceiling may differ.

## Common microbenchmark pitfalls

We have already seen several of these; here they are together:

| Pitfall | Symptom | Data from our test machine | Remedy |
|---|---|---|---|
| Result unused | The whole code is deleted | The 0 ns benchmark | `do_not_optimize(result)` |
| Constant input | Computed entirely at compile time | `keep_const` reduced to `mov w8, #144` | `do_not_optimize(input)` |
| Invariant computation | Hoisted out of the repetition loop | `a / b` at 0.31 ns | Make the input opaque in every iteration |
| Measuring loop overhead | Code under test too short; the empty loop dominates | Empty loop about 0.31 ns per iteration | Code under test should be at least one or two orders of magnitude bigger |
| Data always in cache | Faster than the real scenario | See below | Measure with realistic data sizes and access patterns |
| Same input every time | The branch predictor memorizes the answers | See below | Prepare enough different inputs |

The harness prints a hint when the median is below 0.1 ns. On our test machine, an empty function like `[] {}` measures 0.00 ns with this hint, and a body containing only `clobber_memory()` measures 0.31 ns, which is the empty loop itself.

### Data size

Summing an `int` array sequentially, the time per element on our test machine: 0.036 ns for a 16 KiB array, 0.045 ns at 1 MiB, about 0.08 ns at 64 MiB. The same code gets more than twice as slow per element when the data moves from L1 cache to main memory; with random access the gap would be much larger. A benchmark that measures a small array over and over measures the all-cache-hits case. How much data the real program has, and whether it was just evicted by other code, must be prepared to match reality; details in [[perf/memory-hierarchy]].

### The branch predictor memorizes the input

```cpp title="bp.cpp"
#include "bench.hpp"
#include <algorithm>
#include <random>
#include <vector>

[[gnu::noinline]] int count_small(const unsigned char* p, int n) {
  int c = 0;
  for (int i = 0; i < n; ++i)
    if (p[i] < 128) { ++c; asm volatile(""); }  // keep the compiler from making it branchless
  return c;
}

int main() {
  bench::prefer_performance_cores();
  constexpr int N = 4096, K = 64;
  std::mt19937 rng(42);
  std::vector<unsigned char> data(N * K);
  for (auto& x : data) x = rng() & 0xff;
  bench::run("same 4 KiB each time", [&] {
    int c = count_small(data.data(), N);
    bench::do_not_optimize(c);
  });
  int k = 0;
  bench::run("rotate 64 buffers", [&] {
    int c = count_small(data.data() + N * k, N);
    k = (k + 1) % K;
    bench::do_not_optimize(c);
  });
  for (int j = 0; j < K; ++j)
    std::sort(data.begin() + N * j, data.begin() + N * (j + 1));
  bench::run("rotate 64 sorted", [&] {
    int c = count_small(data.data() + N * k, N);
    k = (k + 1) % K;
    bench::do_not_optimize(c);
  });
}
```

The data is random bytes, so each branch has an even chance of going either way. Two runs on our test machine:

| Input | Median |
|---|---|
| The same 4 KiB of random data over and over | 2.62–2.63 µs |
| 64 different random buffers in rotation | 12.7 µs |
| 64 sorted buffers in rotation | 1.45 µs |

With the same data repeated thousands of times, the predictor learns the directions of these 4096 branches, and the measured time is only a fifth of the truly random case. Rotating through 64 buffers (256 KiB in total) defeats the learning. The third row shows the gap does not come from caching: rotating through the same 64 buffers, but sorted, makes the branches easy to predict, and it is fast. Branch prediction itself is covered in [[perf/branches]].

## Comparing two versions fairly

The purpose of optimization is usually to answer "is B faster than A?" To make this comparison fair:

1. **Same program, same compiler options, same input.** Put both versions in the same executable and measure them on the same data.
2. **Measure alternately.** If you measure all of A and then B, B is affected by the cache state A left behind, frequency changes, and changes in background load. Alternating samples exposes both sides to roughly the same drift. The harness's `compare` alternates in ABBA order, cancelling even the bias from ordering.
3. **Run an A/A test first.** Measure the same version as both A and B. The difference between them is the noise floor of this measurement setup; in a real comparison, differences below it mean nothing.
4. **Run several processes.** Samples within one process are not independent (same memory layout, same code addresses). Run the whole program several times and see whether the conclusion holds every time.

```cpp title="aa.cpp"
#include "bench.hpp"
#include <numeric>
#include <vector>

[[gnu::noinline]] int sum_a(const std::vector<int>& v) {
  return std::accumulate(v.begin(), v.end(), 0);
}
[[gnu::noinline]] int sum_b(const std::vector<int>& v) {
  return std::accumulate(v.begin(), v.end(), 0);
}

int main() {
  bench::prefer_performance_cores();
  std::vector<int> v(4096, 1);
  auto a = [&] { int s = sum_a(v); bench::do_not_optimize(s); };
  auto b = [&] { int s = sum_b(v); bench::do_not_optimize(s); };
  bench::run("A", a);                    // measured one after the other
  bench::run("B", b);
  bench::compare(a, b);                  // measured alternately
}
```

The two functions' code is identical (`nm` shows two distinct symbols; they were not merged). Six runs on our test machine: measured one after the other, the ratio of B's median to A's ranged from 0.995 to 1.022, the largest being 149.97 ns vs 153.26 ns, a 2.2% difference; measured alternately, B/A ranged from 0.999 to 1.005.

On this machine under this load, the noise floor is about 0.5% for alternating measurement and about 2% for sequential measurement. An optimization claimed to be 1.5% faster cannot be distinguished from noise by sequential measurement at all. When the gap is within a few percent, also beware of code layout effects: the same instructions can run faster or slower just because a function's address or alignment changed.

## Ready-made tools

Neither Google Benchmark nor nanobench is installed on our test machine (neither is in `brew list`), so this section demonstrates the concepts with a small hand-written harness. Both follow the same ideas as above:

- **Google Benchmark**: the code under test goes inside a `for (auto _ : state)` loop, and the library chooses the iteration count automatically; `benchmark::DoNotOptimize` and `benchmark::ClobberMemory` are the full versions of the two lines of inline assembly above. `--benchmark_repetitions=N` repeats the whole measurement N times and reports mean, median and standard deviation; recent versions also provide warm-up time and randomly interleaved execution options.
- **nanobench**: a single header, `ankerl::nanobench::Bench().run("name", [&] { ... })`, protecting results with `ankerl::nanobench::doNotOptimizeAway`. It reports the median and `err%` (deviation relative to the median), and on Linux can also read hardware performance counters, giving instructions, cycles and branch misprediction rate per call.

Real projects should use these libraries; they handle many details omitted here. Understanding the mechanisms above is what lets you read their output, and know where to look when results seem off.

Measurement answers how fast, not why. To find out where the time goes, use [[perf/profiling|profiling]].

## A reusable harness: bench.hpp {#harness}

The examples on the other pages of this section all use this header. It requires C++20 and GCC/Clang inline assembly syntax.

```cpp title="bench.hpp" impl
// bench.hpp: a good-enough microbenchmark harness (C++20, GCC/Clang inline asm syntax)
#pragma once
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <type_traits>
#include <utility>
#include <vector>
#if defined(__APPLE__)
#include <pthread.h>
#endif

namespace bench {

// Convince the compiler that v's value is read and may have been modified, and that any memory may be read or written.
template <class T>
inline void do_not_optimize(T& v) {
  if constexpr (std::is_trivially_copyable_v<T> && sizeof(T) <= sizeof(void*))
    asm volatile("" : "+r"(v) : : "memory");
  else
    asm volatile("" : "+m"(v) : : "memory");
}
template <class T>
inline void do_not_optimize(const T& v) {
  asm volatile("" : : "m"(v) : "memory");
}
// Only declares "any memory may be read or written", without involving a particular variable.
inline void clobber_memory() { asm volatile("" : : : "memory"); }

struct stats { double min, median, max; };   // unit: ns per call

// One sample: call f() n times in a row, return the average nanoseconds per call.
template <class F>
double sample(F& f, long n) {
  auto t0 = std::chrono::steady_clock::now();
  for (long i = 0; i < n; ++i) f();
  auto t1 = std::chrono::steady_clock::now();
  return std::chrono::duration<double, std::nano>(t1 - t0).count() / n;
}

// Choose n so that one sample lasts at least about 1 ms (over twenty thousand clock steps).
template <class F>
long calibrate(F& f) {
  long n = 1;
  while (n < (1L << 30) && sample(f, n) * n < 1e6) n *= 2;
  return n;
}

inline stats summarize(std::vector<double> t) {
  std::sort(t.begin(), t.end());
  return {t.front(), t[t.size() / 2], t.back()};
}

template <class F>
stats run(const char* name, F f, int samples = 31) {
  long n = calibrate(f);
  for (int i = 0; i < 3; ++i) sample(f, n);           // warm-up, results discarded
  std::vector<double> t;
  for (int i = 0; i < samples; ++i) t.push_back(sample(f, n));
  stats s = summarize(t);
  std::printf("%-20s median %9.2f ns  min %9.2f  max %9.2f%s\n",
              name, s.median, s.min, s.max,
              s.median < 0.1 ? "  <- optimized away?" : "");
  return s;
}

// Measure a and b alternately (ABBA order) so both sides see as much the same drift and interference as possible.
template <class A, class B>
std::pair<stats, stats> compare(A a, B b, int rounds = 31) {
  long n = std::max(calibrate(a), calibrate(b));
  for (int i = 0; i < 3; ++i) { sample(a, n); sample(b, n); }
  std::vector<double> ta, tb;
  for (int i = 0; i < rounds; ++i) {
    if (i % 2 == 0) { ta.push_back(sample(a, n)); tb.push_back(sample(b, n)); }
    else            { tb.push_back(sample(b, n)); ta.push_back(sample(a, n)); }
  }
  stats sa = summarize(ta), sb = summarize(tb);
  std::printf("A median %.2f ns, B median %.2f ns, B/A = %.3f\n",
              sa.median, sb.median, sb.median / sa.median);
  return {sa, sb};
}

// macOS cannot pin threads to specific cores; the highest QoS makes the scheduler prefer performance cores.
inline void prefer_performance_cores() {
#if defined(__APPLE__)
  pthread_set_qos_class_self_np(QOS_CLASS_USER_INTERACTIVE, 0);
#endif
}

}  // namespace bench
```

Typical use:

```cpp title="use.cpp"
#include "bench.hpp"
#include <numeric>
#include <vector>

int main() {
  bench::prefer_performance_cores();
  std::vector<int> v(4096, 1);
  bench::run("sum 4096 ints", [&] {
    int s = std::accumulate(v.begin(), v.end(), 0);
    bench::do_not_optimize(s);
  });
}
```

```bash
clang++ -std=c++2c -O2 use.cpp -o use && ./use
```

One run on our test machine prints `sum 4096 ints  median 146.57 ns  min 145.54  max 331.79`. A few conventions:

- Each sample lasts about 1 ms; 31 samples are recorded by default, after discarding 3 warm-up samples;
- The median is reported, with the minimum and maximum as hints of the spread;
- The lambda under test is responsible for calling `do_not_optimize` on its own inputs and results; the harness does not decide for you which values should be opaque;
- If the code under test carries state between calls (for example rotating through several inputs), keep the state in variables captured by the lambda; its cost is included in the measurement.

## Questions

!!! question "Constant input"
    What does `long n = 1'000; bench::run("x", [&] { bench::do_not_optimize(sum_to(n)); });` measure?

<details markdown="1">
<summary>Answer</summary>

`sum_to(n)` is a temporary, so the `const T&` overload is selected. `n` is a local variable that is never modified, so the compiler knows it equals 1000, and `sum_to(1000)` is computed to the constant 332833500 at compile time. At `-O2` on our test machine, all that precedes the asm is one `mov` and one `str` storing the constant to the stack, and it measures 0.31 ns, the cost of the empty loop. To measure the run-time computation, first call `do_not_optimize` on `n`; even then, what is measured is the closed-form formula, see the first section. The basis is the as-if rule ([[intro.abstract#1]]): whether something is computed at compile time or run time is not observable behavior.
</details>

!!! question "Why not time each call separately?"
    For a 150 ns call, what is wrong with calling `steady_clock::now()` once before and once after, recording 10000 such differences and taking the median?

<details markdown="1">
<summary>Answer</summary>

`steady_clock`'s step on our test machine is 41 ns, so measured values can only fall near multiples of 41.7 ns; 150 ns gets quantized to around 125 or 167, and the error of a single difference can exceed 15%. Each `now()` also takes ten to several tens of nanoseconds itself and disrupts the pipeline. Calling thousands of times in a row and dividing by the count amortizes both to almost nothing. The price is that you cannot see the distribution of single calls; to really measure single-call latency, you need finer timing tools and must subtract the cost of timing itself.
</details>

!!! question "A 1.5% improvement"
    New version B measured 1.5% faster than A sequentially. In the A/A test, the largest sequential difference was 2% and the largest alternating difference 0.5%. What should you do?

<details markdown="1">
<summary>Answer</summary>

No conclusion can be drawn yet; 1.5% is within the noise of sequential measurement. Switch to alternating measurement (`bench::compare`) and run the whole program several times. Only if B/A is stable around 0.985 in every run, clearly beyond the 0.5% noise, can you say B is really about 1.5% faster. After that, confirm the difference comes from the code itself rather than layout: for example, swap the order of the two functions in the source file and measure again.
</details>
