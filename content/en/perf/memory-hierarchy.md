---
title: Caches, locality and data layout
summary: "Why the way you access memory often decides speed more than the amount of computation: measuring cache and memory latency on our test machine, comparing sequential, strided and random access, row-major vs column-major, linked lists vs vector, AoS vs SoA, padding caused by member order, prefetching, TLB and huge pages, and the effect of packing data into bits."
tags: performance, cache, locality, data layout, alignment, padding, TLB, prefetching
updated: 2026-10-19
group: Memory
---

!!! tldr
    - On our test machine (Apple M2 Pro), the latency of one load ranges from about 0.9 ns in L1 cache to 115–150 ns from memory, a difference of over a hundredfold. Which cache level the working set lands in often decides speed more than the instruction count does.
    - The CPU moves data in cache lines, 128 bytes each on our test machine. Sequential access uses every line fully and can be prefetched by the hardware; strides beyond a line, random access and pointer chasing make each load pay for a whole line or even a whole memory access.
    - Independent loads can overlap; dependent loads (linked lists, trees) can only wait one after another. Both doing random accesses to memory, the former took about 5 ns per access on our test machine, the latter about 120 ns.
    - Data layout is under your control and the compiler will not change it for you: the standard requires members to be laid out in declaration order, so how much padding there is depends on the order you write. Grouping hot fields, splitting fields into arrays (SoA), and using bits instead of bytes all reduce the number of bytes moved per access.
    - `__builtin_prefetch` and huge pages are not routine tools on our test machine: manual prefetching gives small, distance-dependent gains, and macOS on Apple silicon offers no user-space huge pages.

Summing the same 8192×8192 `int` matrix by rows and by columns does exactly the same additions:

<div class="compare" markdown="1">

```cpp
// by rows: adjacent elements
for (size_t i = 0; i < n; ++i)
  for (size_t j = 0; j < n; ++j)
    s += m[i * n + j];
```

```cpp
// by columns: 4n bytes apart
for (size_t j = 0; j < n; ++j)
  for (size_t i = 0; i < n; ++i)
    s += m[i * n + j];
```

</div>

On our test machine, summing by columns is 75 times slower. The entire difference comes from the order of memory accesses. To understand it, we first need to know how expensive one memory access really is.

All timings below use this section's shared [[perf/measuring#harness|bench.hpp]]: `bench::run` warms up and then takes the median of 31 samples; `bench::compare` measures two versions alternately and reports the ratio of their medians; `bench::do_not_optimize(x)` is an inline asm statement that generates no instructions and makes the compiler believe `x` was read and written, so the code producing it cannot be deleted.

All programs are compiled with `clang++ -std=c++2c -O2` (Homebrew Clang 23.1.3, libc++, arm64) and use `prefer_performance_cores()` to request performance cores. Many other processes were running on the machine during measurement (load average 80–120), occupying the shared caches and memory bandwidth, so absolute numbers are slow and scattered. Ratios measured back to back in the same process are more trustworthy; don't read too much into small differences.

## How expensive is one load?

### Caches and cache lines

Between the CPU and memory sit several levels of **cache**: small, fast storage that keeps copies of recently used data. When reading an address whose data is already in the cache (a hit), it arrives quickly; otherwise (a miss) it has to be fetched from the next level, all the way down to memory.

Caches do not manage data by the byte but in fixed-size blocks called **cache lines**. Reading one `int` brings the whole line containing it into the cache. The parameters of our test machine can be read with `sysctl`:

```bash
sysctl hw.cachelinesize hw.pagesize hw.l1dcachesize hw.l2cachesize \
       hw.perflevel0.l1dcachesize hw.perflevel0.l2cachesize hw.perflevel0.cpusperl2
```

| Key | Value on our test machine | Meaning |
|---|---|---|
| `hw.cachelinesize` | 128 | 128-byte cache lines |
| `hw.pagesize` | 16384 | 16 KiB virtual memory pages |
| `hw.l1dcachesize` | 65536 | 64 KiB; this is the efficiency cores' L1 data cache |
| `hw.l2cachesize` | 4194304 | 4 MiB, also the efficiency cores' value |
| `hw.perflevel0.l1dcachesize` | 131072 | Performance cores' L1 data cache: 128 KiB |
| `hw.perflevel0.l2cachesize` | 16777216 | Performance cores' L2: 16 MiB |
| `hw.perflevel0.cpusperl2` | 4 | Every 4 performance cores share one L2 |

Keys without `perflevel` report the efficiency cores' values; for performance cores, look at `perflevel0`. After L2 there is one more level shared by all cores, the system level cache (SLC), whose size `sysctl` does not report (`hw.l3cachesize` does not exist).

A 128-byte cache line is twice the 64 bytes common on x86-64. libc++'s `std::hardware_destructive_interference_size` is 128 on our test machine and `hardware_constructive_interference_size` is 64 ([[hardware.interference]], see [[support.dynamic]]); both come from the compiler's predefined macros `__GCC_DESTRUCTIVE_SIZE` and `__GCC_CONSTRUCTIVE_SIZE`. The former is used to separate data written by different threads; see [[perf/false-sharing]].

### Measuring latency by pointer chasing

To measure the latency of one load, each load must wait for the previous one to finish. The way to do that is to make the next address the value just read, that is, to walk a linked list:

```cpp title="latency.cpp"
#include "bench.hpp"
#include <cstdio>
#include <numeric>
#include <random>
#include <vector>

struct alignas(128) Slot { Slot* next; };   // each node occupies its own cache line

// chase pointers around a random cycle in a kib-KiB buffer, printing the time per step
void chase(std::size_t kib) {
  std::vector<Slot> buf(kib * 1024 / sizeof(Slot));
  std::size_t n = buf.size();
  std::vector<std::size_t> perm(n);
  std::iota(perm.begin(), perm.end(), 0);
  std::mt19937_64 rng(42);
  for (std::size_t i = n - 1; i > 0; --i)    // Sattolo's algorithm: the permutation is a single cycle
    std::swap(perm[i], perm[rng() % i]);
  for (std::size_t i = 0; i < n; ++i) buf[i].next = &buf[perm[i]];

  Slot* p = &buf[0];
  char name[32];
  std::snprintf(name, sizeof name, "%zu KiB", kib);
  bench::run(name, [&] {
    p = p->next;                             // the next address depends on the value just read
    bench::do_not_optimize(p);
  });
}

int main() {
  bench::prefer_performance_cores();
  for (std::size_t kib = 16; kib <= 1024 * 1024; kib *= 2) chase(kib);
}
```

Each design decision has its reason:

- `alignas(128)` makes each node occupy a whole line ([[dcl.align]]), so every step touches a new cache line.
- The link order is a random permutation. With a sequential order, the hardware would guess the next address and fetch the data early, and what we measured would not be latency.
- An ordinary random shuffle may split the nodes into several small cycles; the pointer would circle in a small cycle and the memory actually touched would be smaller than the buffer. Sattolo's algorithm generates only permutations that are exactly one cycle, guaranteeing every node is visited.

Medians (per step) from one run on our test machine:

| Working set | Per step | Roughly in |
|---|---|---|
| 16 KiB – 128 KiB | 0.92 ns | L1 |
| 256 KiB | 6.6 ns | L2 |
| 512 KiB – 4 MiB | 6.0 ns | L2 |
| 8 MiB | 7.5 ns | L2 |
| 16 MiB | 58 ns (minimum 21 ns) | Transition |
| 32 MiB – 64 MiB | 115–118 ns | Memory |
| 128 MiB – 1 GiB | 125–148 ns | Memory |

The steps line up clearly with the performance cores' parameters: up to 128 KiB is L1, at 256 KiB it jumps to L2, and around 16 MiB it starts leaving L2. Expecting the efficiency cores' `hw.l1dcachesize` (64 KiB) would not match. No clear plateau belonging to the SLC appears on this curve between L2 and memory; the 16 MiB step, whose median and minimum differ greatly, is a transition region. Beyond 64 MiB the latency keeps creeping up; one possible reason is that address translation also starts missing, see the TLB section below.

!!! note "The order of magnitude matters more than the exact numbers"
    L1 and memory differ by over a hundredfold. A loop whose working set doesn't fit in cache and whose accesses depend on each other waits over a hundred nanoseconds per iteration, time in which the CPU could have executed hundreds of instructions.

## Sequential, strided and random

Latency is only the worst case. Independent loads can be in flight at the same time, and the CPU also recognizes regular access patterns and fetches data early; this is called **hardware prefetching**. Below, on a 64 MiB `uint32_t` array, each element is read exactly once with different strides:

```cpp title="stride.cpp"
#include "bench.hpp"
#include <cstdint>
#include <cstdio>
#include <numeric>
#include <random>
#include <vector>

int main() {
  bench::prefer_performance_cores();
  const std::size_t n = 16 * 1024 * 1024;            // 64 MiB of uint32_t
  std::vector<std::uint32_t> a(n, 1);
  for (std::size_t stride : {1, 4, 8, 16, 32, 64, 1024, 4096}) {
    char name[32];
    std::snprintf(name, sizeof name, "stride %zu B", stride * 4);
    auto s = bench::run(name, [&] {
      std::uint32_t sum = 0;
      for (std::size_t start = 0; start < stride; ++start)   // every element read exactly once
        for (std::size_t i = start; i < n; i += stride) sum += a[i];
      bench::do_not_optimize(sum);
    }, 7);
    std::printf("  -> %.2f ns/elem\n", s.median / n);
  }
  std::vector<std::uint32_t> idx(n);                 // random order, again each element read once
  std::iota(idx.begin(), idx.end(), 0u);
  std::shuffle(idx.begin(), idx.end(), std::mt19937_64(1));
  auto s = bench::run("random", [&] {
    std::uint32_t sum = 0;
    for (std::size_t i = 0; i < n; ++i) sum += a[idx[i]];
    bench::do_not_optimize(sum);
  }, 7);
  std::printf("  -> %.2f ns/elem\n", s.median / n);
}
```

The stride is a run-time value, so every stride executes the same scalar loop; the inner loop in the assembly has no vector instructions. The instruction count per element is the same, and the difference comes only from memory:

| Stride | Per element |
|---|---|
| 4 B, 16 B | 0.48 ns |
| 32 B | 1.22 ns (minimum 0.57 ns) |
| 64 B | 2.09 ns |
| 128 B | 4.56 ns |
| 256 B | 5.64 ns |
| 4 KiB | 6.94 ns |
| 16 KiB | 7.77 ns |
| Random order | 3.80 ns |

With a 4-byte stride, one 128-byte cache line serves 32 loads; at a 128-byte stride, every load has to bring in a whole line and uses only 4 bytes of it. Beyond that, each load still costs one line, but the pattern becomes harder and harder for the prefetcher to exploit, and page crossings become more and more frequent.

Random order costs 3.8 ns per element, much less than the 120 ns of pointer chasing. Both read randomly in over 64 MiB of data; the difference is that here the loads are independent: the address of `a[idx[i]]` depends only on `idx`, not on the value of the previous load, so the CPU can issue many missing requests at once, and their waiting times overlap. In linked lists, trees and hash-table collision chains, you only know where to read next once the current read completes.

## Two-dimensional arrays: row-major vs column-major

A C++ multidimensional array is an array of arrays ([[dcl.array#9]]), and array elements are allocated contiguously ([[dcl.array#6]]), so `int m[R][C]` is **row-major**: elements of the same row are adjacent, and the next row follows. Manual flattening like `m[i * n + j]` follows the same convention. Traversing by rows is sequential access; traversing by columns skips a whole row at each step, which is 32 KiB when `n = 8192`.

```cpp title="matrix.cpp"
#include "bench.hpp"
#include <cstdio>
#include <vector>

long sum_rows(const std::vector<int>& m, std::size_t n) {
  long s = 0;
  for (std::size_t i = 0; i < n; ++i)
    for (std::size_t j = 0; j < n; ++j) s += m[i * n + j];   // adjacent elements
  return s;
}
long sum_cols(const std::vector<int>& m, std::size_t n) {
  long s = 0;
  for (std::size_t j = 0; j < n; ++j)
    for (std::size_t i = 0; i < n; ++i) s += m[i * n + j];   // 4n bytes apart
  return s;
}

int main() {
  bench::prefer_performance_cores();
  for (std::size_t n : {128, 1024, 8192}) {
    std::vector<int> m(n * n, 1);
    std::printf("n = %zu (%zu KiB)\n", n, n * n * sizeof(int) / 1024);
    bench::compare([&] { long s = sum_rows(m, n); bench::do_not_optimize(s); },
                   [&] { long s = sum_cols(m, n); bench::do_not_optimize(s); }, 11);
  }
}
```

| n | Matrix size | By rows (per element) | By columns (per element) | Columns/rows |
|---|---|---|---|---|
| 128 | 64 KiB | 0.080 ns | 0.30 ns | 3.8 |
| 1024 | 4 MiB | 0.047 ns | 2.9 ns | 62 |
| 8192 | 256 MiB | 0.11 ns | 7.9 ns | 75 |

Even when the matrix fits entirely in L1, columns are 3.8 times slower, and this part of the difference does not come from caching. Look at the `-O2` assembly: the inner loop of `sum_rows` is vectorized, reading 32 bytes at a time with `ldp q16, q17` and widening and accumulating 4 `int`s with `saddw`/`saddw2`; the inner loop of `sum_cols` is scalar `ldrsw` plus `add`, one element at a time. Contiguous access lets the compiler use SIMD instructions (see [[perf/vectorization]]); strided access does not. As the matrix grows, the cost of cache misses piles on, and the gap widens to 60–75 times.

In real code, the fix is to swap the loop order, or, where that is impossible (as in matrix transposition or matrix multiplication), to use blocking: process only a small block that fits in cache at a time, so the data within a block is reused repeatedly.

## Linked lists vs vector

Each node of a `std::list` is allocated separately and linked by pointers. Traversing a list is pointer chasing, so its speed depends on where the nodes are in memory:

```cpp title="list.cpp"
#include "bench.hpp"
#include <cstdio>
#include <list>
#include <random>
#include <vector>

template<class C> long sum(const C& c) { long s = 0; for (int x : c) s += x; return s; }

int main() {
  bench::prefer_performance_cores();
  const int n = 4'000'000;
  std::vector<int> v(n, 1);
  std::list<int> fresh(n, 1);          // nodes allocated in order, addresses mostly contiguous

  std::list<int> shuffled(n, 1);       // the same nodes, with the link order shuffled
  std::vector<std::list<int>::iterator> its;
  for (auto it = shuffled.begin(); it != shuffled.end(); ++it) its.push_back(it);
  std::shuffle(its.begin(), its.end(), std::mt19937_64(7));
  std::list<int> tmp;
  for (auto it : its) tmp.splice(tmp.end(), shuffled, it);   // only relinks, doesn't move nodes
  shuffled.swap(tmp);

  double tv = bench::run("vector", [&] { long s = sum(v); bench::do_not_optimize(s); }, 11).median;
  double tf = bench::run("list, fresh", [&] { long s = sum(fresh); bench::do_not_optimize(s); }, 11).median;
  double ts = bench::run("list, shuffled", [&] { long s = sum(shuffled); bench::do_not_optimize(s); }, 11).median;
  std::printf("ns/elem: vector %.3f  list fresh %.2f  list shuffled %.1f\n", tv / n, tf / n, ts / n);
}
```

| Container | Per element |
|---|---|
| `vector<int>` | 0.058 ns |
| `list<int>`, freshly created | 1.11 ns |
| `list<int>`, link order shuffled | 134 ns |

In a freshly created list the nodes are allocated consecutively, their addresses are mostly adjacent, and the cache and prefetcher still work. It is 19 times slower than `vector` because each step must first read `next` before continuing, the loop cannot be vectorized, and each node carries two extra pointers. `splice` only changes links without moving nodes; after shuffling, traversal order is unrelated to address order, and every step is a memory latency, matching the 120–150 ns measured by pointer chasing earlier.

Linked lists in real programs, after repeated insertions and erasures, have node distributions close to the latter case. How to choose containers is in [[perf/choosing-containers]]; how the allocator affects node placement is in [[perf/allocation]].

## Member order and padding

### The compiler won't reorder for you

```cpp title="layout.cpp" run impl
#include <cstddef>
#include <cstdint>

struct Order {               // arranged by business meaning
  bool         active;
  double       price;
  std::int16_t venue;
  std::int64_t qty;
  bool         is_buy;
};
struct OrderSorted {         // arranged by alignment requirement, largest first
  double       price;
  std::int64_t qty;
  std::int16_t venue;
  bool         active;
  bool         is_buy;
};
static_assert(sizeof(Order) == 40 && alignof(Order) == 8);
static_assert(offsetof(Order, price) == 8 && offsetof(Order, qty) == 24);
static_assert(sizeof(OrderSorted) == 24);
int main() {}
```

Every type has an [[g:alignment]] requirement: objects of that type can only be placed at addresses that are a multiple of it ([[basic.align#1]]). `double` and `int64_t` require 8-byte alignment on our test machine, so 7 bytes must be left after `active` before `price` can go in, and 6 bytes after `venue` before `qty`; the size of the whole class must also be rounded up to a multiple of 8 so the next element of an array is aligned. These empty bytes are **padding**. With the same 20 bytes of data, `Order` takes 40 bytes and `OrderSorted` 24. The exact sizes and alignments are up to the implementation, so this example is marked {{impl}}.

Clang's `-Wpadded` points out each place padding is inserted:

```text
layout.cpp:6:16: warning: padding struct 'Order' with 7 bytes to align 'price' [-Wpadded]
layout.cpp:8:16: warning: padding struct 'Order' with 6 bytes to align 'qty' [-Wpadded]
layout.cpp:4:8: warning: padding size of 'Order' with 7 bytes to alignment boundary [-Wpadded]
layout.cpp:11:8: warning: padding size of 'OrderSorted' with 4 bytes to alignment boundary [-Wpadded]
```

`clang++ -Xclang -fdump-record-layouts -fsyntax-only` prints the full offset table; usage is in [[toolchain/object-layout-and-vtables]].

The compiler does not reorder members by size automatically. [[expr.rel#4.2]] requires a pointer to a later-declared non-static data member of the same object to compare greater (except for zero-size subobjects and unions), and the note in [[class.mem.general#24]] explains the consequence: members are allocated in declaration order, later ones at higher addresses, and alignment requirements may leave gaps between adjacent members.

!!! history "C++23: access control no longer permits reordering"
    Up to C++20, this ordering guarantee applied only to members with the same access control; the relative order of a `public:` section and a `private:` section was unspecified. Mainstream compilers never took advantage of this permission. C++23's [[P1847R4]] removed it; now all non-static data members are laid out in declaration order regardless of access control.

### The cost of padding

Padding bytes have to be brought into the cache just like useful bytes. Counting `active` orders over 8 million elements:

```cpp title="layout-bench.cpp"
// continues from Order and OrderSorted above
template<class T> long open_qty(const std::vector<T>& v) {
  long s = 0;
  for (const T& o : v) if (o.active) s += o.qty;
  return s;
}
// in main:
//   std::vector<Order> a(8'000'000);  std::vector<OrderSorted> b(8'000'000);
//   every third element active, qty all 1
//   bench::compare([&] { long s = open_qty(a); bench::do_not_optimize(s); },
//                  [&] { long s = open_qty(b); bench::do_not_optimize(s); }, 11);
```

In two runs, the time ratio of `OrderSorted` to `Order` was 0.664 and 0.654, close to the size ratio 24/40 = 0.6. When the array is too big to fit in cache, scanning speed is largely determined by the number of bytes per element.

## Hot and cold fields

### AoS, hot/cold splitting and SoA

A particle system updates only positions every frame; fields like color and name are used only for rendering or debugging. Frequently accessed fields are called **hot fields**, rarely accessed ones **cold fields**. Comparing three layouts:

```cpp title="particles.cpp"
#include "bench.hpp"
#include <cstdio>
#include <vector>

struct Particle {              // AoS: hot and cold fields together
  float x, y, z, vx, vy, vz;   // updated every frame: 24 bytes
  float color[4];              // used only for rendering
  char name[48];               // used only for debugging
  int id, flags;
};                             // 96 bytes

struct Hot  { float x, y, z, vx, vy, vz; };              // hot/cold split: 24 bytes
struct Cold { float color[4]; char name[48]; int id, flags; };

struct Particles {             // SoA: one array per field
  std::vector<float> x, y, z, vx, vy, vz;
};

void step(std::vector<Particle>& ps, float dt) {
  for (auto& p : ps) { p.x += p.vx * dt; p.y += p.vy * dt; p.z += p.vz * dt; }
}
void step(std::vector<Hot>& ps, float dt) {
  for (auto& p : ps) { p.x += p.vx * dt; p.y += p.vy * dt; p.z += p.vz * dt; }
}
void step(Particles& s, float dt) {
  for (std::size_t i = 0; i < s.x.size(); ++i) s.x[i] += s.vx[i] * dt;
  for (std::size_t i = 0; i < s.y.size(); ++i) s.y[i] += s.vy[i] * dt;
  for (std::size_t i = 0; i < s.z.size(); ++i) s.z[i] += s.vz[i] * dt;
}

int main() {
  bench::prefer_performance_cores();
  static_assert(sizeof(Particle) == 96 && sizeof(Hot) == 24);
  for (std::size_t n : {4'000, 4'000'000}) {
    std::vector<Particle> aos(n, Particle{0, 0, 0, 1, 1, 1, {}, {}, 0, 0});
    std::vector<Hot> hot(n, Hot{0, 0, 0, 1, 1, 1});
    std::vector<Cold> cold(n);                 // matches hot by index
    std::vector<float> zero(n), one(n, 1);
    Particles soa{zero, zero, zero, one, one, one};
    float dt = 0.01f;
    bench::do_not_optimize(dt);
    std::printf("n = %zu\n", n);
    double a = bench::run("AoS", [&] { step(aos, dt); bench::clobber_memory(); }).median;
    double h = bench::run("hot/cold", [&] { step(hot, dt); bench::clobber_memory(); }).median;
    double s = bench::run("SoA", [&] { step(soa, dt); bench::clobber_memory(); }).median;
    std::printf("  ns/particle: AoS %.2f  hot/cold %.2f  SoA %.2f\n", a / n, h / n, s / n);
  }
}
```

**AoS** (array of structures) is the most natural form: one struct per particle, placed in an array. **SoA** (structure of arrays) puts each field in its own array. Hot/cold splitting is in between: the hot fields still form a struct, and the cold fields move to another array matched by index.

| Particles | AoS (96 B each) | Hot/cold split (24 B each) | SoA |
|---|---|---|---|
| 4000 | 1.19 ns | 0.46 ns | 0.18 ns |
| 4 million | 2.75 ns | 0.72 ns | 0.56 ns |

AoS moves 96 bytes per particle updated, of which 72 bytes are not needed this frame. With 4000 particles, AoS totals 375 KiB, more than the 128 KiB L1, while the split version's 94 KiB fits. With 4 million particles all three are in memory, and the time roughly tracks the bytes per particle.

SoA and the hot/cold split move the same number of bytes, yet SoA is faster still; the reason is in the instructions. The SoA loop is vectorized, its inner loop handling 16 `float`s per iteration with 4 `fmla.4s`; in the AoS and split versions, `x` and `y` use one `fmla.2s` and `z` a scalar `fmadd`, and each iteration handles only one particle. The SoA loop is also preceded by a run-time check (`ccmp`), because the compiler cannot prove the `x` and `vx` arrays don't overlap; the conditions for vectorization are in [[perf/vectorization]].

!!! pitfall "SoA isn't free"
    SoA makes code that looks at one particle at a time harder to write: fetching a complete particle reads 6 arrays, and adding or removing elements means keeping all arrays in sync. Split according to the access pattern: code that scans all elements each frame and uses few fields suits SoA or a hot/cold split; code that fetches single objects at random and uses most of their fields suits AoS.

## Prefetching

### Hardware and manual prefetching

As we have seen, sequential and regularly strided access is prefetched automatically by the hardware. GCC and Clang also provide an extension, `__builtin_prefetch(addr)`, which generates a hint instruction (`prfm` on arm64) requesting that the line containing `addr` be brought into the cache early. It is not standard C++, and the hardware may ignore the hint.

Manual prefetching only makes sense for addresses the hardware cannot guess but the program knows in advance. The typical case is random reads through an index table: when reading `a[idx[i]]`, `idx[i + d]` is already known.

```cpp title="prefetch.cpp"
#include "bench.hpp"
#include <cstdint>
#include <cstdio>
#include <random>
#include <vector>

int main() {
  bench::prefer_performance_cores();
  const std::size_t n = 32 * 1024 * 1024;     // 256 MiB of uint64_t
  const std::size_t m = 4 * 1024 * 1024;      // 4 million random reads per round
  std::vector<std::uint64_t> a(n, 1);
  std::vector<std::uint32_t> idx(m);
  std::mt19937_64 rng(3);
  for (auto& i : idx) i = rng() % n;

  auto gather = [&](std::size_t d) {          // prefetch d iterations ahead
    return [&a, &idx, d] {
      std::uint64_t sum = 0;
      for (std::size_t i = 0; i < m; ++i) {
        if (d != 0 && i + d < m) __builtin_prefetch(&a[idx[i + d]]);
        sum += a[idx[i]];
      }
      bench::do_not_optimize(sum);
    };
  };
  for (std::size_t d : {8, 32, 128}) {
    std::printf("d = 0 vs d = %zu: ", d);
    bench::compare(gather(0), gather(d), 11);
  }
}
```

The condition `i + d < m` cannot be omitted: `idx[i + d]` out of bounds is undefined behavior, regardless of prefetching being only a hint.

| Prefetch distance d | Time ratio (prefetch/no prefetch), two runs |
|---|---|
| 8 | 1.23, 1.10 |
| 32 | 1.03, 1.12 |
| 128 | 0.85, 0.83 |

Without prefetching each load takes about 5.3 ns, already more than twenty times less than memory latency, because these loads are independent and the CPU was overlapping them anyway. When the distance is too short, the prefetched data has not arrived by the time it is needed, and the extra instructions actually slow the loop down; at distance 128 it is about 15% faster. The best distance depends on memory latency, the length of the loop body and the hardware, and must be remeasured on another machine.

For dependency chains like pointer chasing, manual prefetching is useless: the next address is known only once the current node is read, and by then prefetching it is too late. On the 128 MiB random linked list from earlier, doing `__builtin_prefetch(p->next)` before advancing each step gave a time ratio of 0.987, no different from not prefetching. The only way to make linked structures faster is to change the layout, for example putting nodes in a contiguous array and using indices instead of pointers.

## TLB and huge pages

### Address translation needs a cache too

Programs use virtual addresses, and every access must be translated to a physical address. Translation works in units of pages, 16 KiB on our test machine. Recently used translations are cached in the **TLB** (translation lookaside buffer); on a TLB miss, the hardware must read the page tables in memory to complete the translation.

Below, n nodes are placed either right next to each other (128 bytes apart) or one per page (16 KiB + 128 bytes apart), comparing pointer-chasing latency. Both layouts touch the same number of cache lines; they differ only in how many pages are crossed:

```cpp title="tlb.cpp"
#include "bench.hpp"
#include <cstdio>
#include <memory>
#include <numeric>
#include <random>
#include <unistd.h>
#include <vector>

struct alignas(128) Slot { Slot* next; };

// n nodes, adjacent nodes gap bytes apart (gap a multiple of 128), chasing pointers around a random cycle
auto chase(std::size_t n, std::size_t gap) {
  std::size_t k = gap / sizeof(Slot);
  auto buf = std::make_shared<std::vector<Slot>>(n * k);
  auto at = [&](std::size_t i) { return &(*buf)[i * k]; };
  std::vector<std::size_t> perm(n);
  std::iota(perm.begin(), perm.end(), 0);
  std::mt19937_64 rng(42);
  for (std::size_t i = n - 1; i > 0; --i) std::swap(perm[i], perm[rng() % i]);
  for (std::size_t i = 0; i < n; ++i) at(i)->next = at(perm[i]);
  return [buf, p = at(0)]() mutable {
    p = p->next;
    bench::do_not_optimize(p);
  };
}

int main() {
  bench::prefer_performance_cores();
  const std::size_t page = getpagesize();          // 16384 on our test machine
  for (std::size_t n : {256, 1024, 4096}) {
    std::printf("%zu nodes: packed vs one per page\n", n);
    bench::compare(chase(n, 128), chase(n, page + 128));
  }
  bench::run("256, gap = page", chase(256, page));
}
```

| Nodes | Packed | One per page | Address range spanned |
|---|---|---|---|
| 256 | 0.92 ns | 0.92 ns | 4 MiB |
| 1024 | 0.94 ns | 3.0–7.0 ns | 16 MiB |
| 4096 | 6.0–6.9 ns | 20–23 ns | 64 MiB |

1024 nodes occupy only 128 KiB of cache lines, and packed together they are all in L1; spread across 1024 pages, the data may still be in cache, but address translation starts missing, and each step is several times slower. The latency curve's continued slow rise beyond 64 MiB likely has this factor as well.

When the node spacing is exactly 16 KiB (without the extra 128 bytes), the latency for 256 nodes rises from 0.92 ns to 5.2–6.8 ns. This time the cause is not the TLB: the cache assigns lines to sets by the low bits of the address, and when the spacing is a large power of two, all nodes fall into the same few sets, which fill up and evict each other, so only a small part of the 128 KiB L1 is actually used. Striding by a power of two (for example traversing a matrix with 4096-wide rows by columns) hits the same problem; adding a little padding to each row avoids it.

### Huge pages are unavailable on macOS

Larger pages let the same number of TLB entries cover more memory. Linux provides transparent huge pages and `MAP_HUGETLB`. macOS's `mmap` has two flags, `VM_FLAGS_SUPERPAGE_SIZE_ANY` and `VM_FLAGS_SUPERPAGE_SIZE_2MB` (passed via the `fd` argument), but on our test machine (Apple silicon, macOS 26) both return `EINVAL` (Invalid argument). What a user program can do on this machine is reduce the number of pages crossed: keep data that is used together close together in the address space as well.

## Bits instead of bytes

A flag needs only 1 bit, but stored as a `bool` or `char` it takes 8. The standard's specification of `vector<bool>` does not require contiguous storage of `bool`s and recommends bit packing ([[vector.bool.pspc#3]]); `std::bitset<N>` also stores bits (see [[bitset]]). Packed, the same cache line holds 8 times as many flags:

```cpp title="flags.cpp"
#include "bench.hpp"
#include <cstdint>
#include <cstdio>
#include <memory>
#include <random>
#include <vector>

template<class Flags> auto lookups(std::size_t n, const std::vector<std::uint32_t>& q) {
  auto f = std::make_shared<Flags>(n);
  for (std::size_t i = 0; i < n; i += 3) (*f)[i] = true;
  return [f, &q] {
    std::size_t hits = 0;
    for (auto i : q) hits += (*f)[i];
    bench::do_not_optimize(hits);
  };
}

int main() {
  bench::prefer_performance_cores();
  std::mt19937 rng(5);
  for (std::size_t n : {1u << 20, 1u << 25, 1u << 28}) {
    std::vector<std::uint32_t> q(1'000'000);
    for (auto& x : q) x = rng() % n;
    std::printf("%zu flags: bool %zu KiB, char %zu KiB\n", n, n / 8 / 1024, n / 1024);
    auto [b, c] = bench::compare(lookups<std::vector<bool>>(n, q),
                                 lookups<std::vector<char>>(n, q), 11);
    std::printf("  ns/lookup: bool %.2f  char %.2f\n", b.median / q.size(), c.median / q.size());
  }
}
```

| Flags | `vector<bool>` size | `vector<char>` size | `vector<bool>` per lookup | `vector<char>` per lookup |
|---|---|---|---|---|
| 2²⁰ | 128 KiB | 1 MiB | 0.38 ns | 0.60 ns |
| 2²⁵ | 4 MiB | 32 MiB | 1.2–1.3 ns | 2.5–5.7 ns |
| 2²⁸ | 32 MiB | 256 MiB | 4.2–4.4 ns | 4.5–5.0 ns |

These are the results of two of three runs; the other run measured 18.5 ns for `vector<bool>` and 7.5 ns for `vector<char>` at 2²⁸, clearly affected by machine load, so no conclusion can be drawn about the difference at that size.

The differences in the first two sizes both come from the cache level: when `vector<bool>` fits in L1 or L2, `vector<char>` has already dropped to the next level. Bit storage needs an extra shift and mask per access; once neither fits in L2, the space saved buys little speed. Problems with `vector<bool>` such as proxy references, not being able to take addresses, and concurrent writes to adjacent elements constituting a data race are covered in [[vector.bool]].

## Questions

!!! question "Question 1"
    If `struct S { char tag; double v; };` is changed to `struct S { double v; char tag; };`, what is `sizeof(S)` on our test machine? Does the memory footprint of `std::vector<S>` shrink?

<details markdown="1">
<summary>Answer</summary>

Both are 16 on our test machine. `double` requires 8-byte alignment; the first form pads 7 bytes after `tag`, and the second has 7 bytes of tail padding after `tag`, because `sizeof` must be a multiple of the alignment so that the next array element's `v` is aligned. Reordering can only remove padding between members, not the tail padding needed for alignment. Reordering reduces the size only when several small members can be packed together into the same gap, as with `Order` and `OrderSorted`. To compress further, move `tag` out (hot/cold split or SoA), or give up alignment with an extension like `#pragma pack`. The latter is not standard C++, produces misaligned members whose access may be slower, and taking the address of such members and using it as an ordinary pointer is not safe.
</details>

!!! question "Question 2"
    Someone calls `__builtin_prefetch` on the next node inside a loop iterating over a `std::map`, hoping to speed it up. Based on the measurements above, what effect do you expect? What would be a more effective change?

<details markdown="1">
<summary>Answer</summary>

Iterating a `std::map` moves along the tree's pointers; the next node's address is known only after reading the current node, which is a dependency chain just like the pointer chasing above. Prefetching one node ahead amounts to issuing the request just as it is about to be read; on the random linked list above the measured time ratio was 0.987, no gain. The more effective approach is to change the layout: if the key set rarely changes after construction, switch to a sorted `std::vector` (or C++23's `std::flat_map`) with binary search, and traversal becomes sequential access.
</details>

!!! question "Question 3"
    Summing a 4096×4096 `float` matrix by columns, after changing each row's storage length to 4096 + 32 elements (the extra ones unused), the measured time on our test machine dropped to 0.61–0.64 of the original. Why?

<details markdown="1">
<summary>Answer</summary>

A row of 4096 `float`s is 16 KiB, exactly the page size on our test machine and a large power of two. When traversing by columns, consecutive accesses are 16 KiB apart and share all their low address bits, so these lines are assigned to the same few cache sets and evict each other, greatly shrinking the cache's effective capacity. The measurement with spacing of exactly 16 KiB in the TLB section shows this phenomenon. With 32 extra elements (128 bytes, exactly one cache line), the same column of consecutive rows falls into different sets and the conflicts vanish. Column traversal still brings in a whole line per access, but now the whole cache can be used, so it remains much slower than row traversal.
</details>

## Summary

| Problem | Observed on our test machine | Remedy |
|---|---|---|
| Working set exceeds the cache | L1 about 0.9 ns, L2 about 6 ns, memory 115–150 ns | Shrink hot data, process in blocks |
| Strided, column-wise access | From a 128 B stride on, every load pays for a whole line; columns 4–75 times slower than rows | Swap loop order, store data in access order |
| Dependency chains (lists, trees) | Shuffled list 134 ns per element, `vector` 0.058 ns | Use contiguous arrays and indices, fewer pointer hops |
| Padding | `Order` 40 B vs 24 B version, scan time ratio about 0.66 | Declare members from largest to smallest alignment, check with `-Wpadded` |
| Cold fields | AoS 2.6–3.8 times slower than hot/cold split | Hot/cold split or SoA |
| Manual prefetching | At most about 15% faster for random reads, useless for dependency chains | Fix the layout first; measure prefetch distance |
| TLB | 1024 nodes spread over 1024 pages, each step 3–7 times slower | Keep data used together close in the address space; macOS has no user-space huge pages |
| Flags | `vector<bool>` 1.6–4.4 times faster when it fits in the next cache level up | Store as bits, mind proxy references |

All programs and build commands can be rerun on a quiet machine. The numbers will vary with CPU, memory, compiler version and system load; the direction of the conclusions and the orders of magnitude are what is worth remembering.
