---
title: "Choosing containers: beyond complexity"
summary: "Why containers with the same or better complexity are often slower: measurements on our test machine from 10 to 1 million elements of vector, deque and list; map, unordered_map, flat_map and sorted vector; reserve and bad hashes; small sets; heterogeneous lookup with string keys; per-element memory overhead; and, finally, why the real use of node containers is iterator and reference stability."
tags: performance, containers, vector, list, map, unordered_map, flat_map, hashing, heterogeneous lookup, memory overhead
updated: 2026-10-19
group: Code
---

!!! tldr
    - Complexity only describes the growth trend as size increases; it leaves out the constant. In practice the constant comes mostly from memory access: contiguous storage can use the cache and the prefetcher, while every step through a node container may be a cache miss.
    - In our measurements, for maintaining a sorted sequence (find the position linearly, then insert), `vector<int>` beats `list<int>` at every size from 10 to 1 million elements, by about 3.7x at 1 million. With 256-byte elements, `list` leads between a few dozen and a few thousand elements and falls behind again at larger sizes.
    - For lookup-heavy work `unordered_map` is fastest; `flat_map` and a sorted `vector` look up several times faster than `map` and iterate two or three orders of magnitude faster, but inserting one element at a time is linear, so collect first and sort. Hash tables should be `reserve`d in advance, and the hash function must spread keys out, or lookups degrade into walking a linked list.
    - With `std::string` keys, enabling heterogeneous lookup with `is_transparent` lets `find` take a `string_view` directly; a lookup with a long key saves one allocation and was 2.3x faster in our tests.
    - Node containers use 16 to 40 extra bytes per element; the real reason to pick them is that insertion and rehashing do not invalidate references. Choose them when you need to hold pointers or references to elements over time; otherwise start with `vector`.

## A result complexity doesn't explain

Maintain a sorted sequence: for each new value, search linearly from the front for the first element not less than it, and insert there. Insertion into a `std::list` is constant time ([[list.modifiers#1]]); insertion into a `std::vector` has to shift all later elements one by one and is linear ([[vector.modifiers#1]]). Going by complexity alone, `list` should win.

Each operation below searches linearly, inserts, then erases the element just inserted so the container's size stays at N. The values are random, so on average half the elements are traversed.

```cpp
// each operation: find the position, insert, then erase
int v = int(rng() % (2 * n));
auto it = std::find_if(c.begin(), c.end(),
                       [&](int x) { return x >= v; });
it = c.insert(it, v);
c.erase(it);
```

| N | `vector<int>` | `deque<int>` | `list<int>` |
|---:|---:|---:|---:|
| 10 | 32 ns | 33 ns | 38 ns |
| 100 | 35 ns | 60 ns | 80 ns |
| 1 000 | 120 ns | 293 ns | 516 ns |
| 10 000 | 1.05 µs | 2.52 µs | 5.93 µs |
| 100 000 | 11.6 µs | 24.0 µs | 63.0 µs |
| 1 000 000 | 107 µs | 159 µs | 391 µs |

`vector` is fastest at every size. The total complexity of the two is actually the same: the search is already linear, and all `list` saves is the insertion step. The problem is that the constants of the two linear processes differ a lot. Both the search and the shifting in `vector` are sequential reads and writes over contiguous memory, and `memmove` can move dozens of bytes at a time; each step of the search in `list` must first read the next node's address out of the current node before it can issue the next load.

The rest of this page puts the common choices through the same kind of measurement on our test machine, one by one.

## How we measured

All numbers come from the same machine: Apple M2 Pro, macOS, Homebrew Clang 23.1 with libc++, arm64, compiled with

```bash
clang++ -std=c++2c -O2 -Wall -Wextra -pedantic seq.cpp -o seq && ./seq
```

The timing harness works like [[perf/measuring#harness|bench.hpp]]: the code under test goes in a lambda, a fixed number of consecutive calls makes one sample, one round is run as warm-up, then several samples are taken; results are kept alive with `do_not_optimize` (an inline asm statement that generates no instructions and makes the compiler believe the value is read, so it cannot delete the code that computes it). Unlike that page, this one reports the minimum of the samples rather than the median. Many other processes were running on the machine during measurement; interference can only make a sample slower, never faster, so the minimum is closest to the undisturbed time.

```cpp
template <class F>
double bench(F&& f, long inner, int reps = 9) {
  using clk = std::chrono::steady_clock;
  for (long i = 0; i < inner; ++i) f();   // warm-up
  std::vector<double> s;
  for (int r = 0; r < reps; ++r) {
    auto t0 = clk::now();
    for (long i = 0; i < inner; ++i) f();
    auto t1 = clk::now();
    s.push_back(std::chrono::duration<double, std::nano>(t1 - t0).count() / inner);
  }
  return *std::min_element(s.begin(), s.end());
}
```

Even so, the absolute values in the large-size rows still differ by up to about 2x when the same program runs at different times (for example, `map` lookup with 1 million elements measured 545 ns in one run and 1.3 µs in another). The relative order of the columns stays the same across runs, and the conclusions below depend only on that relative order. On another machine or another standard library the specific numbers and crossover points will move; measure again with your own data.

## Sequence containers

### Appending at the end

| N | `vector` | `vector` + `reserve` | `deque` | `list` |
|---:|---:|---:|---:|---:|
| 10 | 22 ns | 3.2 ns | 6.7 ns | 38 ns |
| 100 | 5.0 ns | 1.0 ns | 1.4 ns | 47 ns |
| 1 000 | 0.96 ns | 0.79 ns | 0.94 ns | 35 ns |
| 100 000 | 0.64 ns | 0.77 ns | 0.95 ns | 49 ns |
| 1 000 000 | 0.62 ns | 0.77 ns | 0.94 ns | 47 ns |

The table shows the average time per element, including building a container of N elements and destroying it. `list` needs one `operator new` and one `operator delete` per element, so it costs tens of nanoseconds regardless of size; the cost of an allocation itself is in [[perf/allocation]].

Without reserved capacity, `vector`'s cost at small sizes is concentrated in growth: libc++ doubles the capacity each time, so 10 elements go through 5 allocations. `reserve` merges them into one and is 7x faster at 10 elements. At larger sizes the number of growths is logarithmic and amortizes to under 1 ns per element, and the difference between the two is within measurement noise (in these runs the version without reserve was even slightly faster; this page did not pursue why). `deque` allocates fixed-size blocks and falls in between.

### Traversal

| N | `vector` | `deque` | `list`, built in order | `list`, links shuffled |
|---:|---:|---:|---:|---:|
| 100 | 0.057 ns | 0.59 ns | 1.08 ns | 0.81 ns |
| 10 000 | 0.039 ns | 0.61 ns | 1.68 ns | 9.2 ns |
| 1 000 000 | 0.046 ns | 0.46 ns | 1.36 ns | 92 ns |

0.04 ns per element means more than ten `int`s per clock cycle. Only vectorization can do that:

```cpp
long sum_vec(const std::vector<int>& c) {
  long s = 0;
  for (int x : c) s += x;
  return s;
}
```

At `-O2`, the main loop Clang 23 generates for this reads 64 bytes per iteration and uses `saddw`/`saddw2` to widen 4-byte `int`s to 8 bytes, accumulating into 8 vector registers. The same loop over a `std::list<int>` is reduced to pointer chasing:

```text
LBB1_2:                       ; the loop in sum_list
    ldrsw   x10, [x9, #16]    ; load the value from the node
    add     x8, x8, x10
    ldr     x9, [x9, #8]      ; load next; only then can the next iteration start
    cmp     x9, x0
    b.ne    LBB1_2
```

The address of the next load depends on the result of this one, so the CPU cannot issue the request early. When nodes are allocated in order they are mostly adjacent in memory and loads usually hit the cache, about 1 ns per element; after `sort`, the link order has nothing to do with address order, and at 1 million elements every step waits for memory: 92 ns. A linked list in a real program with repeated insertions and erasures is close to the latter case. The mechanism and how cache latency is measured are in [[perf/memory-hierarchy]]; vectorization is in [[perf/vectorization]].

A `deque` iterator has to check at every step whether it has reached the end of the current block, and the loop is not vectorized, so it is an order of magnitude slower than `vector`; but its blocks are contiguous, so shuffling does not affect it.

### Inserting in the middle: where is the crossover?

The table at the top used 4-byte `int`s, which are cheap to move. Switching to a 256-byte struct (key plus padding) makes moving 64 times more expensive, while insertion into a `list` moves no elements at all:

| N | `vector<Big>` | `deque<Big>` | `list<Big>` |
|---:|---:|---:|---:|
| 10 | 47 ns | 62 ns | 39 ns |
| 100 | 345 ns | 239 ns | 83 ns |
| 1 000 | 3.91 µs | 2.22 µs | 2.50 µs |
| 10 000 | 44.4 µs | 26.6 µs | 27.4 µs |
| 100 000 | 542 µs | 348 µs | 2 206 µs |

Now there is a crossover. `list` leads or nearly leads between 10 and 1 000 elements; at 100 000 elements, 27 MB of nodes do not fit in cache, and the cost of pointer chasing again exceeds `vector`'s bulk moves.

`deque` is consistently faster than `vector` with large elements, for a reason written into its complexity requirement: the cost of inserting in the middle is proportional to the smaller of the distances to the two ends ([[deque.modifiers#2]]), so implementations move the shorter side, N/4 elements on average; `vector` always moves every element after the insertion point, N/2 on average ([[vector.modifiers#1]]).

Note too that this test favors `list`: it is built in order, and each erased node is reused by the next insertion, so the nodes stay mostly contiguous. Where `list` really has the advantage is when the insertion position is already in hand as an iterator and no search is needed.

## Lookup tables: `map`, `unordered_map`, `flat_map`, sorted `vector`

`std::map` is a red-black tree with one node per element. `std::unordered_map` is a hash table with chaining, also one node per element. `std::flat_map` ({{c++23}}, [[P0429R9]]) is a container adaptor that keeps keys and values in two separate sorted sequence containers, two `vector`s by default ([[flat.map.overview#5]]). A sorted `vector<pair<K, V>>` with `std::lower_bound` is the hand-written version, except that keys and values are interleaved.

The libc++ on our test machine provides `<flat_map>` and `<flat_set>` (`flat_set` is the set version of the same idea, [[P1222R4]]), with `__cpp_lib_flat_map` at `202511`.

In the next three tables, keys and values are random 64-bit integers.

### Lookup

Each lookup searches for an existing key, in random order:

| N | `map` | `unordered_map` | `flat_map` | Sorted `vector` |
|---:|---:|---:|---:|---:|
| 10 | 2.9 ns | 2.5 ns | 4.0 ns | 3.1 ns |
| 100 | 4.8 ns | 2.3 ns | 7.7 ns | 6.7 ns |
| 1 000 | 7.1 ns | 3.6 ns | 12.9 ns | 11.7 ns |
| 10 000 | 59 ns | 7.6 ns | 27 ns | 28 ns |
| 100 000 | 103 ns | 10.7 ns | 44 ns | 44 ns |
| 1 000 000 | 545 ns | 28 ns | 95 ns | 70 ns |

All three ordered structures make about log₂N comparisons; the difference is where the memory read before each comparison lives. Each level of a `map` is a separately allocated node, and at large sizes nearly every level is a cache miss. Binary search jumps around a contiguous array; the first few jumps are long and miss too, but the last few land in the same cache line, and the array is much smaller than a tree with the same contents. Up to a few thousand elements all three are in cache, and `map` is even slightly faster, because binary search's branches are hard to predict.

`unordered_map` looks at just one bucket and reads one node on average, and is fastest at every size. The price is that it keeps no order and does not support range queries.

### Insertion

Starting from an empty container and inserting N random keys one at a time; the table gives the average time per element. The last column does not insert one at a time but first `push_back`s everything into a `vector`, then calls `std::sort` once:

| N | `map` | `unordered_map` | `unordered_map` + `reserve` | `flat_map` | Sorted `vector` | Collect then sort |
|---:|---:|---:|---:|---:|---:|---:|
| 10 | 57 ns | 81 ns | 48 ns | 91 ns | 20 ns | 14 ns |
| 100 | 92 ns | 82 ns | 47 ns | 44 ns | 33 ns | 7.0 ns |
| 1 000 | 117 ns | 69 ns | 71 ns | 109 ns | 186 ns | 14 ns |
| 10 000 | 179 ns | 90 ns | 68 ns | 1.50 µs | 2.32 µs | 80 ns |
| 100 000 | 378 ns | 146 ns | 85 ns | 28.3 µs | 27.5 µs | 54 ns |
| 1 000 000 | 1.03 µs | 438 ns | 260 ns | not measured | not measured | 117 ns |

A single insertion into `flat_map` is linear, as the standard says outright ([[flat.map.overview#2.3]]): up to 100 elements it is faster than `map`, at 1 000 they are even, and at 100 000 it is 75x slower. Inserting 1 million elements one at a time would move 500 000 keys and 500 000 values per insertion on average, about 4×10¹² bytes in total; we did not measure it.

So `flat_map` and a sorted `vector` suit data that is read much more than written and can be built in batches. When building in batches, collecting then sorting beats every one-at-a-time insertion at every size. `flat_map` has constructors that accept already sorted data (tagged with `std::sorted_unique`), which skip the sort.

### Traversal

| N | `map` | `unordered_map` | `flat_map` | Sorted `vector` |
|---:|---:|---:|---:|---:|
| 100 | 2.4 ns | 0.80 ns | 0.069 ns | 0.12 ns |
| 10 000 | 15 ns | 5.1 ns | 0.078 ns | 0.19 ns |
| 1 000 000 | 167 ns | 36 ns | 0.094 ns | 0.20 ns |

`map`'s nodes were allocated in insertion order and the keys were random, so traversing in key order jumps randomly through memory; at 1 million elements every step is a memory latency, just like the shuffled `list`. `flat_map` reads only the `vector` holding the values, and the loop is vectorized; the sorted `vector` has to step over the interleaved keys and reads twice as much memory.

## Hash tables: `reserve` and bad hashes

### Reserving buckets

The default maximum load factor of `unordered_map` (the upper limit on the average number of elements per bucket) is 1.0 ([[unord.map.cnstr#1]]). When the element count exceeds the bucket count, the container allocates a larger bucket array and relinks every node into the new buckets; this is called a [[g:rehash]]. `reserve(n)` sets the bucket count up front to be enough for n elements ([[unord.req.general#239]]). In the insertion table in the previous section, at 1 million elements it cut the insertion time per element from 438 ns to 260 ns.

`reserve` also has an effect unrelated to speed: as long as the element count after insertion does not exceed the bucket count times the maximum load factor, insertion does not invalidate iterators ([[unord.req.general#243]]).

### The hash function decides everything

The average constant time of `unordered_map` rests on the premise that hash values are spread out. The worst case the standard gives is linear ([[unord.req.general#174]]), which happens when every key lands in the same bucket. Comparing three hash functions:

```cpp
struct Low8 {    // only 256 distinct hash values
  std::size_t operator()(std::uint64_t k) const { return k & 0xFF; }
};
struct Const {   // every key collides
  std::size_t operator()(std::uint64_t) const { return 0; }
};
```

| Hash | N | Insert (per element) | Lookup | Longest bucket |
|---|---:|---:|---:|---:|
| `std::hash`, random keys | 100 000 | 61 ns | 12 ns | 7 |
| `std::hash`, keys `i << 12` | 100 000 | 33 ns | 3.2 ns | 1 |
| `Low8` | 100 000 | 1.45 µs | 1.26 µs | 443 |
| `Const` | 1 000 | 2.13 µs | 990 ns | 1 000 |
| `Const` | 10 000 | 9.85 µs | 9.88 µs | 10 000 |

`Low8` squeezes 100 000 keys into 256 buckets, and lookup becomes 100x slower; `Const` degrades the hash table into a linked list, where every lookup and insertion traverses all elements, and building a 10 000-element table takes 0.1 seconds. Insertion slows down just as much, because inserting a unique key first requires confirming it is not already in the bucket.

The second row looks like it should be bad: the libc++ `std::hash<std::uint64_t>` on our test machine returns the key itself (`std::hash<std::uint64_t>{}(12345)` prints 12345), and the low 12 bits of `i << 12` are all 0. It is fine because libc++'s bucket count is prime (102 877 in this table), and the modulo uses every bit of the hash. A hash table implementation that uses a power of two as the bucket count and takes the low bits of the hash directly would pile the same keys into very few buckets. The quality of hash values is a contract between the implementation and its users; the standard only requires equal keys to hash equal and the probability of unequal keys hashing the same to be small ([[hash.requirements]]), and does not specify how `std::hash` is implemented.

!!! pitfall "An attacker can choose the keys"
    If keys come from external input (HTTP headers, JSON field names) and the hash function is public and fixed, an attacker can craft keys that land in the same bucket and degrade the server to the `Const` row above. Externally facing services should use a hash function with a random seed.

## Small sets

With very few elements, the constant is everything. The sets below hold N distinct `uint8_t` keys; each query looks up a random `uint8_t`, with a hit rate of about N/256:

| N | Unsorted `vector` + `find` | Sorted `vector` + `binary_search` | `set` | `unordered_set` | `flat_set` | `bitset<256>` |
|---:|---:|---:|---:|---:|---:|---:|
| 4 | 1.7 ns | 2.2 ns | 2.6 ns | 1.8 ns | 2.1 ns | 0.37 ns |
| 16 | 2.2 ns | 3.8 ns | 6.6 ns | 1.8 ns | 3.8 ns | 0.37 ns |
| 64 | 4.4 ns | 5.3 ns | 12.8 ns | 2.5 ns | 5.4 ns | 0.37 ns |
| 128 | 6.1 ns | 6.5 ns | 15.8 ns | 2.2 ns | 6.5 ns | 0.37 ns |

When the key range is small enough to enumerate, `std::bitset` (or a `bool` array) turns lookup into one shift and one bitwise AND, independent of N ([[bitset]]). Otherwise, up to a few dozen elements, a linear scan of a contiguous array is no worse than binary search, and `std::set` is slowest at every size.

The `unordered_set` here is in an ideal situation: `std::hash` is the identity function, and the 256 possible keys never collide. With string keys, computing the hash itself means reading the whole key, and on a small set it may no longer win.

## String keys and heterogeneous lookup

Using `std::string` as a key is common, and the key used for a query is often a `std::string_view` sliced out of a buffer. Constructing a `std::string` from a `string_view` is `explicit`, and the default `unordered_map<std::string, int>::find` only accepts `const std::string&`:

```cpp title="het-error.cpp" error
#include <string>
#include <string_view>
#include <unordered_map>
int main() {
  std::unordered_map<std::string, int> prices;
  std::string_view sym = "AAPL";
  prices.find(sym);   // error: string_view does not implicitly convert to string
}
```

The caller has to write `prices.find(std::string(sym))`, constructing a temporary string for every lookup. When the key is longer than the SSO limit (short string optimization: short strings are stored inside the `std::string` object itself, at most 22 characters in libc++ on our test machine), that means a heap allocation.

**Heterogeneous lookup** lets `find` accept an argument of a type different from the key type but comparable with keys. It is enabled per container: ordered containers require the comparator to have a member type named `is_transparent` ([[associative.reqmts.general#180]], C++14, [[N3657]]); unordered containers require both the hash function and the equality predicate to have it ([[unord.req.general#245]], C++20, [[P0919R3]], [[P1690R1]]). Such a comparator is called a [[g:transparent-comparator]]; `std::less<>` and `std::equal_to<>` are ready-made examples.

```cpp title="het.cpp" run ok
#include <cstdio>
#include <functional>
#include <string>
#include <string_view>
#include <unordered_map>

struct SvHash {
  using is_transparent = void;
  std::size_t operator()(std::string_view s) const {
    return std::hash<std::string_view>{}(s);
  }
};

int main() {
  std::unordered_map<std::string, int,
                     SvHash, std::equal_to<>> prices;
  prices["AAPL240119C00190000"] = 7;
  std::string_view line = "AAPL240119C00190000,buy";
  std::string_view sym = line.substr(0, line.find(','));
  if (auto it = prices.find(sym); it != prices.end())  // no std::string constructed
    std::printf("%d\n", it->second);
}
```

`SvHash` uses the same function for `std::string` and `std::string_view`, so equal values of the two get the same hash, which is the condition a transparent hash must satisfy. Ordered containers only need the comparator changed to `std::less<>`: `std::map<std::string, int, std::less<>>`.

Looking up each of 10 000 keys once on our test machine; `allocs` is the number of allocations per lookup, counted with a replaced global `operator new`:

| Key length | Container | `find(std::string(sv))` | `find(sv)`, transparent |
|---:|---|---:|---:|
| 16 | `unordered_map` | 18.8 ns, 0 allocs | 15.1 ns, 0 allocs |
| 40 | `unordered_map` | 47.4 ns, 1 alloc | 20.4 ns, 0 allocs |
| 16 | `map` | 118 ns, 0 allocs | 116 ns, 0 allocs |
| 40 | `map` | 166 ns, 1 alloc | 133 ns, 0 allocs |

16 characters is within SSO, so the temporary string does not allocate, and transparent lookup only saves a copy. At 40 characters the temporary string has to allocate and free, and transparent lookup makes `unordered_map` 2.3x faster. The gain for `map` is proportionally smaller, because its time goes mostly to a dozen or so string comparisons and the cache misses along the way.

## How much memory each element takes

A counting allocator (a minimal implementation of the [[allocator.requirements.general|allocator requirements]]) records every allocation a container makes, showing how many bytes each element really costs:

```cpp
template <class T>
struct Counting {
  using value_type = T;
  Counting() = default;
  template <class U> Counting(const Counting<U>&) {}
  T* allocate(std::size_t n) {
    g.bytes += n * sizeof(T);
    g.rounded += malloc_good_size(n * sizeof(T));  // macOS: the size malloc actually hands out
    ++g.blocks;
    return static_cast<T*>(std::malloc(n * sizeof(T)));
  }
  void deallocate(T* p, std::size_t n) { /* subtract symmetrically */ std::free(p); }
  friend bool operator==(Counting, Counting) { return true; }
};
```

Elements are 8-byte `long`s (for `map` and `unordered_map`, both key and value are `long`, 16 bytes of payload), N = 1 million:

| Container | Requested bytes/element | Actual malloc bytes/element | Allocations/element |
|---|---:|---:|---:|
| `vector`, `push_back` | 8.4 | 8.4 | ≈0 |
| `vector`, `reserve` | 8.0 | 8.0 | ≈0 |
| `deque` | 8.0 | 8.0 | ≈0 |
| `list` | 24 | 32 | 1 |
| `set` | 40 | 48 | 1 |
| `unordered_set` | 37 | 45 | 1 |
| `map<long, long>` | 48 | 48 | 1 |
| `unordered_map<long, long>` | 45 | 45 | 1 |
| `unordered_map`, `reserve` | 40 | 40 | 1 |
| `flat_map<long, long>` | 16.8 | 16.8 | ≈0 |

These numbers can be broken down by libc++'s node structures (the exact layout is the implementation's choice; the standard does not specify it):

- A `list` node is two pointers plus the element, 24 bytes. macOS malloc has 16-byte granularity, so it actually takes 32 bytes, of which only a quarter is payload.
- `set` and `map` nodes are three pointers (left, right, parent), plus a color flag (8 bytes after alignment), plus the element: 40 bytes for `set<long>`, rounded up to 48; exactly 48 for `map<long, long>`.
- An `unordered_map` node is a `next` pointer, the cached hash value and the element, 32 bytes in all; in addition each bucket is an 8-byte pointer. Without reserving, the bucket count is about 1.6 times the element count, adding 13 bytes per element; after `reserve` the bucket count is close to the element count, adding 8 bytes.
- `vector`'s overhead comes from unused capacity: 1 million is not a power of two, and doubling growth leaves 5% of slots empty. The two `vector`s of `flat_map` are the same.

Node containers take roughly 16 to 40 extra bytes per element, 2 to 3 times the 16 bytes of payload. More importantly, the nodes are scattered over the heap: a 64-byte cache line holds 8 keys of a `flat_map` but only one node of a `map`. The cost of allocation itself and ways to allocate less (object pools, `std::pmr`) are in [[perf/allocation]] and [[topics/allocators-and-pmr]].

## The real reason to pick a node container: reference stability

Almost all the data above says contiguous storage is faster. Node containers still have a use nothing else can replace: once an element is in, it is never moved.

```cpp title="dangle.cpp" run ub
#include <cstdio>
#include <string>
#include <vector>

struct Order { int id; std::string owner; };

int main() {
  std::vector<Order> book;
  book.push_back({1, "alice"});
  Order& first = book.front();   // the reference points into the vector's buffer
  for (int i = 2; i <= 100; ++i)
    book.push_back({i, "bob"});  // growth: elements move to a new buffer
  std::printf("%d\n", first.id); // UB: first points into the freed old buffer
}
```

Growth invalidates every reference, pointer and iterator to the elements of a `vector` ([[vector.modifiers#2]]). Running with `-fsanitize=address` on our test machine reports `heap-use-after-free`, with the free happening in `deallocate` during growth. More forms of this bug are in [[topics/dangling-references]].

```cpp title="stable.cpp" run ok
#include <cstdio>
#include <deque>
#include <string>
#include <unordered_map>

struct Order { int id; std::string owner; };

int main() {
  std::deque<Order> book;
  book.push_back({1, "alice"});
  Order& first = book.front();
  for (int i = 2; i <= 100; ++i)
    book.push_back({i, "bob"});  // inserting at either end does not invalidate references
  std::printf("%d\n", first.id); // 1

  std::unordered_map<int, Order> by_id;
  Order& o = by_id[1] = {1, "alice"};
  for (int i = 2; i <= 1000; ++i)
    by_id[i] = {i, "bob"};       // several rehashes
  std::printf("%s\n", o.owner.c_str()); // alice: the reference is still valid
}
```

Inserting at either end of a `deque` invalidates all iterators but does not affect references to elements ([[deque.modifiers#1]]), because it only adds a new block to the block index; old blocks stay put. A rehash of `unordered_map` only relinks nodes into new buckets without moving the nodes, so iterators are invalidated but pointers and references are not ([[unord.req.general#9]]).

The rules for each container are summarized below. The exact conditions for [[g:iterator-invalidation]] are on each clause's page.

| Container | After insertion, references to other elements | After insertion, iterators | Source |
|---|---|---|---|
| `vector` | All invalidated on growth; otherwise those after the insertion point | Same | [[vector.modifiers#2]] |
| `deque` | Insertion at either end: stay valid; in the middle: all invalidated | All invalidated | [[deque.modifiers#1]] |
| `list` / `forward_list` | Stay valid | Stay valid | [[list.modifiers#2]] |
| `map` / `set` | Stay valid | Stay valid | [[associative.reqmts.general#175]] |
| `unordered_map` / `unordered_set` | Stay valid | All invalidated on rehash | [[unord.req.general#242]] |
| `flat_map` / `flat_set` | No guarantee | No guarantee | [[flat.map.overview#2.2]] |

`flat_map` explicitly states that it does not meet the associative container requirements on iterator invalidation. Its elements live in `vector`s; insertion moves every element after it and may reallocate.

So the reason to pick a node container is usually one of these: another data structure holds pointers to the elements (indexes, intrusive lists, observers); the elements cannot be moved; or you need `splice`, `merge` or node-handle `extract` to transfer elements between containers without copying ([[list.ops]], [[container.node]]). If the only reason is frequent insertion and erasure, measure `vector` first.

!!! tip "When all you need is a stable address"
    When elements need stable addresses but you also want the traversal speed of contiguous storage, a common compromise is `vector<std::unique_ptr<T>>` (element addresses are stable, the pointer array is contiguous), or using indices instead of pointers and keeping the elements in a `vector` or `deque` that never shrinks. The former still costs one allocation per element and adds an indirection during traversal.

## How to choose

Each row of the table corresponds to a group of measurements above.

| Need | First choice | Basis |
|---|---|---|
| A general sequence, mostly adding/removing at the back and traversing | `vector`; `reserve` if you can estimate the size | Appending about 0.6–1 ns/element vs about 40 ns for `list`; traversal more than 20x faster |
| Adding/removing at both ends, or element references must stay valid while appending | `deque` | Insertion at the ends does not invalidate references; traversal about 10x slower than `vector` |
| A sorted sequence where you find the position by value and insert | `vector` for small elements; for large elements and sizes up to a few thousand, consider `list` or `deque` | `int`: `vector` leads at every size; 256 bytes: crossover between 100 and 1 000, and at 100 000 `list` is slowest again |
| Key-to-value mapping, lookup by key only | `unordered_map`, `reserve` in advance | Lookup at 1 million elements 28 ns, `map` 545 ns |
| Ordered traversal or range queries, read-mostly | `flat_map` or sorted `vector`, built in batches | Above 10 000 elements, lookup 2–8x faster than `map`, traversal two or three orders of magnitude faster; one-at-a-time insertion at 100 000 is 75x slower |
| Ordered, with frequent insertion/erasure, or holding element references | `map` / `set` | Insertion invalidates no references or iterators |
| Very small key domain (e.g. 0–255) | `bitset` or `bool` array | 0.37 ns, independent of element count |
| Sets of up to a few dozen elements | Linear scan of an unsorted `vector` | 4.4 ns at 64 elements, `set` 12.8 ns |
| `std::string` keys, looked up by `string_view` | Transparent hash + `equal_to<>`, or `less<>` | 40-character keys: one fewer allocation per lookup, 2.3x faster |
| Pointers or references to elements held long-term elsewhere | A node container, or `vector<unique_ptr<T>>` | See the invalidation rules in the previous section |

This table is only a starting point. The choice of container depends on actual element size, scale, mix of operations and access patterns; the most reliable approach is to put real data into a small benchmark like the ones above and measure once.

## Questions

!!! question "1"
    An `unordered_map` first calls `reserve(1000)`, then 1000 elements are inserted starting from empty. Are iterators obtained before the insertions still valid afterwards?

<details markdown="1">
<summary>Answer</summary>

Yes. `a.reserve(n)` is equivalent to `a.rehash(ceil(n / a.max_load_factor()))` ([[unord.req.general#239]]), after which the bucket count B satisfies B ≥ n / z, where z is the maximum load factor. The element counts satisfy N + n ≤ 1000 ≤ z × B, and by [[unord.req.general#243]] such insertions do not affect the validity of iterators.

This assumes nobody changed `max_load_factor` during the insertions. The rule only concerns iterators; references and pointers stay valid whether or not a rehash happens ([[unord.req.general#242]]).
</details>

!!! question "2"
    For middle insertion of 256-byte elements, `deque` is faster than `vector`. If the insertion position is always within the last 10%, how does the gap between them change?

<details markdown="1">
<summary>Answer</summary>

It essentially disappears. `deque` moves whichever side is closer to an end ([[deque.modifiers#2]]); `vector` moves the part after the insertion point ([[vector.modifiers#1]]). With the insertion point near the back, both move only that short tail. `deque`'s advantage appears only when insertion positions are evenly distributed or near the front, where `vector` has to move nearly all elements. This is guaranteed by the complexity requirements and does not depend on the implementation.
</details>

!!! question "3"
    Change the `list` in the opening test so that each insertion creates a new node and nothing is ever erased, growing from empty to 100 000 elements. Would you expect the gap to `vector` to be larger or smaller than in the table?

<details markdown="1">
<summary>Answer</summary>

Larger. The `list` in the table kept reusing the same erased node, and the other nodes were laid out in address order, so the cache and prefetcher were effective during traversal. New nodes inserted at random positions are laid out on the heap in allocation order, unrelated to their order in the list; once the list grows, traversal approaches the shuffled case. In the traversal table, the shuffled list takes 9.2 ns per step at 10 000 elements and 92 ns at 1 million, with 100 000 falling in between; a list built in order stays at 1–2 ns at every size. `vector` is unaffected; its memory layout is contiguous after every insertion.
</details>
