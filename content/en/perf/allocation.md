---
title: What heap allocation costs
summary: How many nanoseconds one new/delete takes on our test machine, how to count allocations by replacing the global operator new, the allocations hidden in string, function, vector, node containers, shared_ptr and exceptions, when the compiler may delete a new/delete pair, and measurements of reuse, object pools, inline storage, aligned allocation and multithreaded allocation.
tags: performance, memory allocation, operator new, SSO, allocation elision, object pool, alignment
updated: 2026-10-19
group: Memory
---

!!! tldr
    - On our test machine (Apple M2 Pro, the libmalloc that ships with macOS), one small `malloc` + `free` takes about 20 ns, and blocks of 64 KiB or more about 100 ns. A program is usually slow because it allocates often, not because a single allocation is expensive.
    - Replacing the global `operator new` lets you count allocations. But the standard allows the compiler to omit a *new-expression*'s call to it, so with optimization the count may drop; the pointer being counted has to escape first.
    - Many allocations hide inside the library: a `std::string` longer than 22 characters (libc++), a `std::function` capturing more than 16 bytes, every `vector` growth, every node of `map`/`list`, the control block of `shared_ptr<T>(new T)`, and exception objects.
    - There are four ways to avoid allocating: `reserve`, reusing capacity after `clear()`, object pools or arenas, and small containers that keep the first few elements inside the object.
    - Over-aligned `new` has no extra cost on our test machine; when several threads allocate at once, the CPU time per operation grows with the thread count.

All timing programs use [[perf/measuring#harness|bench.hpp]]: `bench::run` warms up, then takes the median of 31 samples; `bench::do_not_optimize(x)` is an inline asm statement that generates no instructions and makes the compiler assume `x` was read and written, so it cannot delete the code that produced it.

All numbers are observations on our test machine (Apple M2 Pro, macOS, Homebrew Clang 23 + libc++, `-O2`, arm64). The machine had heavy background load during measurement; the tables give medians that were stable across several runs. Treat absolute values only as orders of magnitude; relative comparisons within one run are more reliable. Different hardware or a different system allocator (glibc, jemalloc, mimalloc) will change the results.

## How long one allocation takes

```cpp title="malloc-sizes.cpp"
#include "bench.hpp"
#include <cstdio>
#include <cstdlib>

int main() {
  bench::prefer_performance_cores();
  constexpr int K = 1000;
  static void* ptrs[K];
  for (std::size_t n : {16, 64, 256, 1024, 4096, 16384,
                        65536, 262144, 1048576}) {
    char name[32];
    std::snprintf(name, sizeof name, "pair %zu", n);
    bench::run(name, [n] {               // allocate, then free immediately
      void* p = std::malloc(n);
      bench::do_not_optimize(p);
      std::free(p);
    });
    std::snprintf(name, sizeof name, "batch %zu (/%d)", n, K);
    bench::run(name, [n] {               // allocate K blocks, then free them all
      for (auto& p : ptrs) {
        p = std::malloc(n);
        bench::do_not_optimize(p);
      }
      for (auto p : ptrs) std::free(p);
    });
  }
}
```

`clang++ -std=c++2c -O2 malloc-sizes.cpp`; the batch column is already divided by 1000:

| Size | Allocate then free immediately | Batches of 1000 |
|---|---|---|
| 16 B | 20.7 ns | 18.6 ns |
| 64 B | 21.8 ns | 20.2 ns |
| 256 B | 22.8 ns | 21.2 ns |
| 1 KiB | 26 ns | 34 ns |
| 4 KiB | 20.4 ns | 32 ns |
| 16 KiB | 26 ns | 47 ns |
| 64 KiB | 100 ns | 109 ns |
| 256 KiB | 105 ns | 108 ns |
| 1 MiB | 104 ns | 103 ns |

There is a step between 16 KiB and 64 KiB: the allocator takes a different, slower path for large blocks. These are best-case numbers: the same memory is allocated and freed over and over, so both the allocator's metadata and the block itself are in cache. In a real program allocations and frees interleave across many sizes, and each one costs more.

The cost of the first write to new memory is not counted either. When a freshly obtained page is written for the first time, the operating system has to handle a page fault; that cost is not in `malloc` but shows up at the first use afterwards. For cache and page-fault costs see [[perf/memory-hierarchy]].

20 ns does not look like much, but allocate once per iteration in a loop and a few million iterations cost tens of milliseconds. So first we learn to count allocations, then look at where they come from.

## Counting allocations

The global `operator new(std::size_t)` is a **replaceable function**: if the program defines a non-`inline` global function with the same signature, it replaces the default version throughout the program ([[new.delete.single#4]], [[dcl.fct.def.replace#1]]). The replacement must still meet the original requirements: return a non-null, suitably aligned pointer, or throw `std::bad_alloc` ([[new.delete.single#2]]). The details are in [[new.delete]].

```cpp run title="count.cpp" ok
#include <cstdio>
#include <cstdlib>
#include <new>
#include <string>

static int g_news = 0;                 // number of calls to the global operator new

void* operator new(std::size_t n) {
  ++g_news;
  if (void* p = std::malloc(n ? n : 1)) return p;
  throw std::bad_alloc{};
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }

template <class F>
int count_news(F f) {                  // how many allocations happened during f()
  int before = g_news;
  f();
  return g_news - before;
}

int main() {
  std::printf("int:        %d\n", count_news([] { delete new int; }));
  std::printf("string(22): %d\n", count_news([] { std::string s(22, 'x'); }));
  std::printf("string(23): %d\n", count_news([] { std::string s(23, 'x'); }));
}
```

Output with Clang 23:

| Options | `int` | `string(22)` | `string(23)` |
|---|---|---|---|
| `-O0` | 1 | 0 | 1 |
| `-O2` | 0 | 0 | 1 |

At `-O2`, `delete new int` counts zero allocations, yet the counter's `++g_news` is a visible side effect. The compiler may delete it because the standard explicitly allows it; see the next section.

The later examples all use the same counting header. To keep allocations from being elided, it also provides `escape`, which makes a pointer look as if it was read and written from outside:

```cpp title="count_new.hpp"
#pragma once
#include <cstdio>
#include <cstdlib>
#include <new>

inline int g_news = 0;

// replacement functions cannot be inline, so only one translation unit may include this header
void* operator new(std::size_t n) {
  ++g_news;
  if (void* p = std::malloc(n ? n : 1)) return p;
  throw std::bad_alloc{};
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }

inline void escape(void* p) { asm volatile("" : : "r"(p) : "memory"); }

template <class F>
int count_news(F f) {
  int before = g_news;
  f();
  return g_news - before;
}
```

## The compiler may delete new and delete

```cpp godbolt title="elide.cpp" flags="-std=c++2c -O2" ok
#include <memory>
#include <vector>

int raw() {
  int* p = new int(42);
  int r = *p + 1;
  delete p;
  return r;
}

int smart() {
  auto p = std::make_unique<int>(42);
  return *p + 1;
}

int vec() {
  std::vector<int> v{1, 2, 3};
  return v[0] + v[1] + v[2];
}
```

`clang++ -std=c++2c -O2 -S elide.cpp`: none of the three functions calls `operator new`:

```asm title="AArch64"
__Z3rawv:
	mov	w0, #43
	ret
__Z5smartv:
	mov	w0, #43
	ret
__Z3vecv:
	mov	w0, #6
	ret
```

With `--target=x86_64-linux-gnu`, `raw` is likewise reduced to `movl $43, %eax`.

!!! std "[expr.new]/14"
    An implementation is allowed to omit a call to a replaceable global allocation function. When it does so, the storage is instead provided by the implementation or provided by extending the allocation of another *new-expression*.

¶14 makes the allocation itself no longer observable behavior. Under the [[g:as-if-rule]] ([[intro.abstract]]) the compiler only has to preserve observable behavior, but a user-replaced `operator new` can print or count, so calling it is observable in its own right. C++14's [[N3664]] added this permission: a *new-expression* may skip the call even if the function has been replaced. Correspondingly, [[expr.delete#6.3]] says that for an omitted allocation, `delete` does not call the deallocation function either. ¶16 also allows two qualifying allocations to be merged into one; details in [[expr.new]].

The allocation in `vec` comes from `std::allocator`, not from a *new-expression*. It can be deleted too because [[allocator.members#5]] says the storage is obtained by calling `::operator new`, but it is unspecified when and how often that function is called. libc++ calls `__builtin_operator_new` inside `std::allocator`, and Clang treats it the same way as a *new-expression*.

Elision requires the compiler to see the pointer's entire lifetime. Once the pointer is passed to a function whose definition it cannot see, the allocation stays:

```cpp godbolt title="noelide.cpp" flags="-std=c++2c -O2" ok
void use(int*);                        // defined in another translation unit
int sink() {
  int* p = new int(42);
  use(p);                              // the pointer escapes
  int r = *p;
  delete p;
  return r;
}
```

Here the assembly keeps `bl __Znwm` and `bl __ZdlPvm`. Compiling `elide.cpp` with `-fno-builtin` also keeps the allocation calls in all three functions. Elision is a permission, not an obligation: which allocations disappear depends on the compiler, the optimization level and inlining, and is not portable. Don't count on it to remove allocations from a hot path; to confirm, look at the assembly ([[perf/reading-assembly]]).

## Hidden allocations

All counts below are taken at `-O2`, and every object under test is passed to `escape` first, so elision cannot lower the count.

### Strings: the SSO boundary

The **short string optimization** ([[g:short-string-optimization|SSO]]) stores short strings directly inside the `std::string` object, without allocating. `count.cpp` in the previous section already shows libc++'s boundary: 22 characters do not allocate, 23 characters allocate once. On our test machine `std::string{}.capacity()` is 22 and `sizeof(std::string)` is 24; the 24 bytes have to hold 22 characters, the terminating null and the length. The standard does not require SSO, the capacity is up to the implementation, and other standard libraries differ.

```cpp title="sso.cpp"
#include "bench.hpp"
#include <string>

int main() {
  bench::prefer_performance_cores();
  const char* src = "abcdefghijklmnopqrstuvwxyz";
  for (std::size_t n : {22, 23}) {
    bench::run(n == 22 ? "string(22 chars)" : "string(23 chars)", [&] {
      std::size_t len = n;
      bench::do_not_optimize(len);       // the length is opaque to the compiler
      std::string s(src, len);
      bench::do_not_optimize(s);
    });
  }
}
```

Constructing and destroying a 22-character string takes about 6 ns on our test machine, a 23-character string about 30 ns; the difference is one allocation and one deallocation. Key names, identifiers, short messages and similar strings do not allocate on libc++ if they stay within 22 characters.

### `std::function`: a 16-byte small-object buffer

`std::function` has to be able to hold a callable of any size, and when it does not fit in the internal buffer it has to allocate.

```cpp title="function.cpp"
#include "count_new.hpp"
#include <array>
#include <functional>

template <int N>
void test() {
  std::printf("%2d-byte capture: %d\n", N, count_news([] {
    std::array<char, N> a{};
    std::function<int()> f = [a] { return a[0]; };
    escape(&f);
  }));
}

int main() { test<16>(); test<17>(); test<24>(); }
```

On our test machine `sizeof(std::function<int()>)` is 32; a closure capturing 16 bytes does not allocate, while 17 bytes and 24 bytes each allocate once. The standard recommends that implementations avoid dynamic allocation for small callables, and its example is an object holding only a pointer to an object and a pointer to a member function ([[func.wrap.func.con#15]]). Such a closure is 24 bytes on arm64, and libc++ still allocates once. This is a recommendation (Recommended practice), not a requirement, so it is not a violation.

For callbacks on a hot path, take the callable directly as a template parameter, or use `std::function_ref` ({{c++26}}, [[func.wrap.ref]]), which does not own the object and does not allocate.

### `vector` growth

```cpp title="growth.cpp"
#include "count_new.hpp"
#include <vector>

int main() {
  std::vector<int> v;
  std::size_t last = v.capacity();
  int n = count_news([&] {
    for (int i = 0; i < 1000; ++i) {
      v.push_back(i);
      if (v.capacity() != last) std::printf("%zu ", last = v.capacity());
    }
  });
  std::printf("\nno reserve: %d allocations\n", n);
  std::printf("reserve:    %d allocation\n", count_news([] {
    std::vector<int> w;
    w.reserve(1000);
    for (int i = 0; i < 1000; ++i) w.push_back(i);
    escape(w.data());
  }));
}
```

```text
1 2 4 8 16 32 64 128 256 512 1024
no reserve: 11 allocations
reserve:    1 allocation
```

libc++ doubles the capacity each time, so 1000 elements take 11 allocations, and each one also moves the existing elements to the new buffer. The growth factor is an implementation detail; the standard only requires `push_back` to have amortized constant complexity. After `reserve(n)`, no reallocation happens as long as the size does not exceed `n` ([[vector.capacity#7]]).

Timing three approaches, each round building 100 elements:

```cpp title="grow.cpp"
#include "bench.hpp"
#include <vector>

constexpr int N = 100;
std::vector<int> kept;                   // buffer reused across rounds

int main() {
  bench::prefer_performance_cores();
  bench::run("fresh", [] {
    std::vector<int> v;
    for (int i = 0; i < N; ++i) v.push_back(i);
    bench::do_not_optimize(v);
  });
  bench::run("reserve", [] {
    std::vector<int> v;
    v.reserve(N);
    for (int i = 0; i < N; ++i) v.push_back(i);
    bench::do_not_optimize(v);
  });
  bench::run("clear + reuse", [] {
    kept.clear();                        // destroys elements, keeps capacity
    for (int i = 0; i < N; ++i) kept.push_back(i);
    bench::do_not_optimize(kept);
  });
}
```

| Approach | Allocations | Median on our test machine |
|---|---|---|
| New, no `reserve` | 8 | about 260 ns |
| New, `reserve(100)` | 1 | about 60 ns |
| Reused after `clear()` | 0 | about 39 ns |

<details class="fine" markdown="1"><summary>An unexplained counterexample</summary>

With `N` changed to 1000, the `reserve` version was slower than the one without `reserve` in several runs on our test machine, even though the assembly of the two inner loops is identical. The cause was not tracked down; it may have to do with the addresses handed out, the memory write pattern or machine load. The difference in allocation count is certain; the difference in time has to be measured under your own workload.
</details>

### `push_back` vs `emplace_back`

`push_back(T(args))` first constructs a temporary and then moves it into the container; `emplace_back(args)` constructs directly in the container. For a type like `std::string`, whose move just steals a pointer, both allocate the same number of times; `push_back` allocates once more only when the type's move degrades to a copy:

```cpp title="emplace.cpp"
#include "count_new.hpp"
#include <string>
#include <vector>

struct Legacy {                        // declares a copy constructor, no move constructor
  std::string s;
  explicit Legacy(const char* p) : s(p) {}
  Legacy(const Legacy&) = default;
};

int main() {
  const char* text = "a string long enough to defeat SSO";
  std::vector<std::string> s;  s.reserve(4);
  std::vector<Legacy> l;       l.reserve(4);
  std::printf("%d %d\n",
    count_news([&] { s.push_back(std::string(text)); }),
    count_news([&] { s.emplace_back(text); }));
  std::printf("%d %d\n",
    count_news([&] { l.push_back(Legacy(text)); }),
    count_news([&] { l.emplace_back(text); }));
}
```

The output is `1 1` and `2 1`. For the cost of copies and moves see [[perf/copies-and-moves]].

### Node containers and `shared_ptr`

With the same counting setup, the results on our test machine:

| Operation | Allocations |
|---|---|
| `std::map<int,int>` inserting 100 keys | 100 |
| `std::list<int>` `push_back` 100 times | 100 |
| `std::shared_ptr<Big>(new Big)` | 2 |
| `std::make_shared<Big>()` | 1 |
| `std::vector<std::string>{"a", "b"}` | 1 |

Every element of `map`, `set`, `list` and `unordered_map` lives in a separately allocated node, so inserting an element is one allocation. For trade-offs between containers see [[perf/choosing-containers]]. `shared_ptr<T>(new T)` allocates once for the object and once for the control block; `make_shared` puts them together, and the standard recommends that implementations allocate only once ([[util.smartptr.shared.create#7.1]]). The cost is that a `weak_ptr` delays freeing the whole block; see [[topics/ownership-and-smart-pointers]]. The last row is easy to misread: both short strings in the initializer list are within SSO, and the only allocation is the `vector`'s buffer.

### Exceptions

```cpp title="exception.cpp"
#include "count_new.hpp"
#include <malloc/malloc.h>             // macOS: malloc_zone_statistics

static int blocks() {                  // live blocks in the default malloc zone
  malloc_statistics_t st;
  malloc_zone_statistics(nullptr, &st);
  return int(st.blocks_in_use);
}

[[gnu::noinline]] void fail(int code) { throw code; }

void once(const char* label) {
  int before = blocks();
  int news = count_news([&] {
    try {
      fail(42);
    } catch (int) {
      std::printf("%s: in handler %+d blocks", label, blocks() - before);
    }
  });
  std::printf(", after %+d, operator new %d\n", blocks() - before, news);
}

int main() {
  once("1st throw");                   // the first one also includes initialization such as the stdout buffer
  once("2nd throw");
}
```

```text
1st throw: in handler +2 blocks, after +2, operator new 0
2nd throw: in handler +1 blocks, after +0, operator new 0
```

On the second throw there is one extra malloc block inside the handler, which is freed after the handler finishes, and `operator new` is never called. The standard says the memory for the exception object is allocated in an unspecified way ([[except.throw#4]]) and explicitly says the global allocation functions are not called (the note in [[basic.stc.dynamic.allocation#5]]). libc++abi calls `malloc` directly in `__cxa_allocate_exception`, so a counter in a replaced `operator new` does not see it.

This allocation is not the main cost of throwing, though. On our test machine, throwing an `int` and catching it one level up takes about 3 µs, while `malloc(16)` + `free` in the same run takes about 20 ns. The time goes mostly into stack unwinding; see [[toolchain/exception-implementation]].

## Ways to allocate less

### Reusing capacity

`clear()` destroys all elements, but the standard does not say it frees memory ([[sequence.reqmts#54]] only says the elements are destroyed and the container becomes empty). libc++'s `vector` and `string` both keep their capacity after `clear()`: on our test machine a 1000-element `vector` still has capacity 1000 after being cleared, a `string` still has 111, and refilling the same amount of content allocates 0 times. In the table above, reusing the buffer is about a third faster again than `reserve` every time.

So a temporary container used repeatedly in a loop can be hoisted out of the loop and `clear()`ed each round. Conversely, when you really want to give memory back, `shrink_to_fit()` is only a non-binding request ([[vector.capacity#9]]); on our test machine libc++ reduces the capacity to 0 when it is called after `clear()`, and to `size()` when the container is non-empty.

### Object pools

When many objects of the same type and size are created and destroyed repeatedly, you can put them in an **object pool**: request one big chunk, chain the free slots into a singly linked list, and both allocation and deallocation become a few pointer operations.

```cpp title="pool.cpp"
#include "bench.hpp"
#include <cstddef>
#include <memory>
#include <utility>
#include <vector>

struct Order { long id; double price; int qty; };

template <class T>
class Pool {
  union Slot {                         // holds next while free, T while in use
    Slot* next;
    T obj;
    Slot() : next(nullptr) {}
    ~Slot() {}
  };
  std::vector<Slot*> chunks_;
  Slot* free_ = nullptr;

  void refill(std::size_t n = 1024) {
    Slot* c = new Slot[n];
    chunks_.push_back(c);
    for (std::size_t i = 0; i < n; ++i) { c[i].next = free_; free_ = &c[i]; }
  }

public:
  Pool() = default;
  Pool(const Pool&) = delete;
  Pool& operator=(const Pool&) = delete;
  ~Pool() { for (Slot* c : chunks_) delete[] c; }   // assumes every object has been destroyed

  template <class... Args> T* create(Args&&... args) {
    if (!free_) refill();
    Slot* s = free_;
    free_ = s->next;
    return std::construct_at(&s->obj, std::forward<Args>(args)...);
  }
  void destroy(T* p) {
    std::destroy_at(p);
    auto* s = reinterpret_cast<Slot*>(p); // a union and its members are pointer-interconvertible
    s->next = free_;
    free_ = s;
  }
};

int main() {
  bench::prefer_performance_cores();
  constexpr int K = 1000;
  static Order* live[K];
  bench::run("new/delete x1000", [] {
    for (int i = 0; i < K; ++i) {
      live[i] = new Order{i, 1.0, 1};
      bench::do_not_optimize(live[i]);
    }
    for (int i = 0; i < K; ++i) delete live[i];
  });
  Pool<Order> pool;
  bench::run("pool x1000", [&] {
    for (int i = 0; i < K; ++i) {
      live[i] = pool.create(i, 1.0, 1);
      bench::do_not_optimize(live[i]);
    }
    for (int i = 0; i < K; ++i) pool.destroy(live[i]);
  });
}
```

In one run on our test machine, `new`/`delete` takes about 24 ns per object and the pool about 2.7 ns, nearly a 10x difference. `std::construct_at` begins the lifetime of an object in `obj`, making it the active member of the union; the assignment to `next` in `destroy` makes `next` the active member again. A union object and its non-static data members are pointer-interconvertible ([[basic.compound#7.2]]), so `reinterpret_cast<Slot*>(p)` yields a pointer to the `Slot`.

This pool is not thread-safe, does not detect double frees, and ASan cannot see misuse inside the pool. That is the price of writing your own allocator.

### Arenas and pmr

An object pool manages one size; an **arena** manages a batch of objects with the same lifetime: allocation just bumps an offset, deallocation does nothing, and the whole chunk is thrown away at the end. The standard library provides an arena as `std::pmr::monotonic_buffer_resource` and a pool binned by size as `unsynchronized_pool_resource`, and `pmr` containers can route their elements' allocations to the same resource. Their usage, propagation rules and our measurements are in [[topics/allocators-and-pmr]].

### Inline storage

Many small collections usually hold just a few elements and only occasionally grow. Keep the first `N` elements inside the object and go to the heap only beyond that, and the common case does not allocate:

```cpp title="small_vector.hpp"
#include <cstddef>
#include <cstring>
#include <new>
#include <type_traits>

// the first N elements live inside the object; only beyond that do we allocate on the heap
// to keep it short, only trivially copyable T is supported
template <class T, std::size_t N>
  requires std::is_trivially_copyable_v<T>
class small_vector {
  T* data_ = inline_;
  std::size_t size_ = 0, cap_ = N;
  T inline_[N];

  void grow() {
    std::size_t cap = cap_ * 2;
    T* p = static_cast<T*>(::operator new(cap * sizeof(T)));
    std::memcpy(p, data_, size_ * sizeof(T));
    if (data_ != inline_) ::operator delete(data_);
    data_ = p;
    cap_ = cap;
  }

public:
  small_vector() = default;
  small_vector(const small_vector&) = delete;
  small_vector& operator=(const small_vector&) = delete;
  ~small_vector() { if (data_ != inline_) ::operator delete(data_); }

  void push_back(const T& v) {
    if (size_ == cap_) grow();
    data_[size_++] = v;
  }
  T* data() { return data_; }
  std::size_t size() const { return size_; }
  T& operator[](std::size_t i) { return data_[i]; }
};
```

On our test machine `small_vector<int, 8>` allocates 0 times for 8 elements and 2 times for 20 elements (capacity 16, then 32); `std::vector<int>` allocates 4 times for 8 elements. Time to build 8 elements in one run: `vector` about 113 ns, `vector` with `reserve(8)` about 29 ns, `small_vector` about 4 ns.

The cost is a bigger object (on our test machine `sizeof(small_vector<int, 8>)` is 56, `vector<int>` is 24), and `data_` may point into the object itself, so a move cannot just copy the pointer; copy and move both need separate handling. Here copying is simply deleted for brevity. LLVM's `SmallVector` and Boost's `small_vector` are complete implementations. The standard library's `std::inplace_vector` ({{c++26}}, [[inplace.vector]]) has a fixed capacity and never allocates; exceeding the capacity is an error rather than a fallback to the heap. At the time of writing, the libc++ on our test machine does not yet provide `<inplace_vector>`.

## Alignment and over-aligned new

A type whose `alignof` exceeds `__STDCPP_DEFAULT_NEW_ALIGNMENT__` has a **new-extended alignment** ([[g:new-extended-alignment]], [[basic.align#3]]). Since C++17 ([[P0035R4]]), `new` of such a type calls the allocation function taking a `std::align_val_t` argument, and the returned address satisfies the type's alignment requirement ([[new.delete.single#1]]).

```cpp title="aligned.cpp"
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <new>

int plain = 0, aligned = 0;
void* operator new(std::size_t n) {
  ++plain;
  if (void* p = std::malloc(n)) return p;
  throw std::bad_alloc{};
}
void* operator new(std::size_t n, std::align_val_t al) {
  ++aligned;
  auto a = static_cast<std::size_t>(al);
  // aligned_alloc requires the size to be a multiple of the alignment
  if (void* p = std::aligned_alloc(a, (n + a - 1) / a * a)) return p;
  throw std::bad_alloc{};
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::align_val_t) noexcept { std::free(p); }

inline void escape(void* p) { asm volatile("" : : "r"(p) : "memory"); }

struct alignas(16) A16 { char c[16]; };
struct alignas(64) Line { char c[64]; };   // aligned to a cache line

int main() {
  std::printf("__STDCPP_DEFAULT_NEW_ALIGNMENT__ = %zu\n",
              std::size_t{__STDCPP_DEFAULT_NEW_ALIGNMENT__});
  A16* a = new A16;   escape(a);
  Line* b = new Line; escape(b);
  auto addr = reinterpret_cast<std::uintptr_t>(b);
  std::printf("plain=%d aligned=%d  addr %% 64 = %zu\n",
              plain, aligned, std::size_t(addr % 64));
  delete a;
  delete b;
}
```

```text
__STDCPP_DEFAULT_NEW_ALIGNMENT__ = 16
plain=1 aligned=1  addr % 64 = 0
```

The default new alignment on our test machine is 16, so the `alignas(16)` type goes through the ordinary version and the `alignas(64)` type through the aligned version. `std::allocator` makes the same choice, so the buffer of a `std::vector<Line>` is also 64-aligned.

In one run, `new`/`delete` of an ordinary 64-byte object, an `alignas(64)` object and an `alignas(4096)` object all take about 24 ns; we see no extra cost for aligned allocation on our test machine. On other platforms aligned allocation may over-allocate and adjust the address, so the cost is not necessarily the same. Cache-line alignment is commonly used to avoid false sharing; see [[perf/false-sharing]].

## Several threads allocating at once

```cpp title="mt-alloc.cpp"
#include "bench.hpp"
#include <atomic>
#include <cstdlib>
#include <ctime>
#include <thread>

double cpu_ns() {                      // CPU time consumed by the current thread
  timespec ts;
  clock_gettime(CLOCK_THREAD_CPUTIME_ID, &ts);
  return ts.tv_sec * 1e9 + ts.tv_nsec;
}

// T threads do malloc(64)+free at the same time; returns the median CPU time per operation
double run(int T, int iters) {
  std::vector<double> per(T);
  std::atomic<int> ready{0};
  {
    std::vector<std::jthread> ts;
    for (int t = 0; t < T; ++t)
      ts.emplace_back([&, t] {
        ready.fetch_add(1);
        while (ready.load() < T) {}    // start only once every thread is ready
        double c0 = cpu_ns();
        for (int i = 0; i < iters; ++i) {
          void* p = std::malloc(64);
          bench::do_not_optimize(p);
          std::free(p);
        }
        per[t] = (cpu_ns() - c0) / iters;
      });
  }                                    // jthread joins in its destructor
  std::sort(per.begin(), per.end());
  return per[T / 2];
}

int main() {
  for (int T : {1, 2, 4, 8}) {
    std::vector<double> v;
    for (int r = 0; r < 7; ++r) v.push_back(run(T, 2'000'000));
    std::sort(v.begin(), v.end());
    std::printf("%d threads: %.1f ns CPU per malloc+free\n", T, v[3]);
  }
}
```

This uses each thread's own CPU time rather than wall-clock time, so time spent descheduled and waiting does not count; the remaining growth comes from synchronization inside the allocator and cache lines moving between cores. Results from two runs on our test machine:

| Threads | CPU time per `malloc` + `free` |
|---|---|
| 1 | about 23 ns |
| 2 | about 32 ns |
| 4 | about 35 ns |
| 8 | about 50–54 ns |

The M2 Pro has 8 performance cores and 4 efficiency cores; with 8 threads some may run on efficiency cores, and the machine had other load during measurement, so this column only shows the trend: the more threads, the more each allocation costs. When the threads' allocations are independent, giving each thread its own pool or `unsynchronized_pool_resource` avoids the shared allocator entirely. Allocators such as jemalloc and mimalloc also use thread-local caches to reduce contention.

## Pitfalls

!!! pitfall "With optimization on, the counter undercounts"
    Replacing `operator new` to count allocations is a common technique in tests. But [[expr.new#14]] allows a *new-expression* to omit the call to it, and at `-O2` `delete new int` is not counted at all. For allocations you want to count, let the pointer escape first, or simply count at `-O0`. Conversely, counting 0 in a test does not mean production code does not allocate.

!!! pitfall "Replacing only half of the allocation functions"
    If you replace only `operator new(size_t)`, the array and nothrow forms forward to it by default and the count stays complete; but the aligned form `operator new(size_t, align_val_t)` does not, so over-aligned objects need their own replacement to be counted. The same goes for deallocation: if you replace the sized `operator delete`, also replace the unsized one; see [[new.delete]].

!!! pitfall "Allocation in a microbenchmark is too cheap"
    A loop that allocates and frees immediately gets the same hot block every time, and measures the best case. The more scattered a program's allocation and deallocation pattern, the more fragmentation and cache misses it has. To decide whether allocation is a bottleneck, [[perf/profiling|profile]] under a real workload and see how much time goes to `malloc`, `free` and page faults.

## Questions

!!! question "1"
    How many times does the function below call `operator new` at `-O2` with Clang 23? If `operator new` is replaced and counted outside `sum`, does the result change?
    ```cpp
    int sum() {
      std::vector<int> v{1, 2, 3};
      return v[0] + v[1] + v[2];
    }
    ```

<details markdown="1">
<summary>Answer</summary>

Zero. Clang 23 compiles it to `mov w0, #6; ret`. Replacing `operator new` does not change this: the standard allows calls to a replaceable global allocation function to be omitted even if it has been replaced ([[expr.new#14]]), and when and how often `std::allocator` calls `::operator new` is unspecified ([[allocator.members#5]]). Whether the call is actually omitted depends on the implementation and optimization; at `-O0` or with `-fno-builtin` the allocation is kept.
</details>

!!! question "2"
    How many allocations does `std::vector<std::string> v; v.reserve(3); v.emplace_back("hello"); v.emplace_back(std::string(30, 'x')); v.push_back("short");` make in total on libc++?

<details markdown="1">
<summary>Answer</summary>

Two. `reserve(3)` makes one; `"hello"` and `"short"` are at most 22 characters, within SSO, and do not allocate; `std::string(30, 'x')` allocates once, and moving it into the container afterwards just transfers the pointer. `push_back("short")` first constructs a temporary `string` and then moves it, also without allocating.
</details>

!!! question "3"
    A function reports failure on a hot path by throwing an exception. How much overhead do you save by changing the exception object from `std::runtime_error` to `int`?

<details markdown="1">
<summary>Answer</summary>

Very little. Both have to allocate memory for the exception object (libc++abi uses `malloc`; [[except.throw#4]] only says the allocation is unspecified), and `runtime_error` also allocates for the message string. But one `throw` + `catch` takes about 3 µs on our test machine and one allocation about 20 ns; nearly all the time goes into stack unwinding. Failures on a hot path should be reported with a return value (for example `std::expected`), not by changing the exception type.
</details>

## Summary

| Source | Observed on our test machine | How to avoid it |
|---|---|---|
| `malloc` + `free` | about 20 ns for small blocks, about 100 ns at 64 KiB and above | Allocate less often |
| `std::string` | one allocation beyond 22 characters (libc++) | Control the length, reuse buffers |
| `std::function` | one allocation for closures over 16 bytes (libc++) | Template parameter, `function_ref` |
| `vector` growth | 11 allocations for 1000 elements | `reserve`, reuse after `clear()` |
| Node containers | one per element | Switch to a contiguous container, or pool/pmr the nodes |
| `shared_ptr(new T)` | 2 | `make_shared` |
| Exceptions | one `malloc` per throw, bypassing `operator new` | Don't throw on a hot path |
| Paired new/delete | may be elided when the pointer does not escape | Don't rely on it; check the assembly |
