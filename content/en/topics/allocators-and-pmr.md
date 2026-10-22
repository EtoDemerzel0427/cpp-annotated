---
title: Allocators and pmr
summary: Starting from one requirement, putting a vector and all of its strings into the same arena, this page covers the allocator requirements and allocator_traits, how stateful allocators propagate on copy, move assignment and swap, uses-allocator construction and scoped_allocator_adaptor, and the memory resources, performance and common pitfalls of std::pmr.
tags: allocators, pmr, memory resources, arena, topic
updated: 2026-10-19
---

!!! tldr
    - A classic allocator is part of the container's type: `vector<T, A>` and `vector<T>` are two different types. The container's allocator also only manages the container's own buffer; elements (for example `std::string`) still use their own allocators.
    - `allocator_traits` fills in default members for an allocator. Whether a stateful allocator follows the contents on copy assignment, move assignment and swap is decided by the three `propagate_on_container_*` traits. When the allocators are unequal, move assignment degrades to moving elements one by one, and swap is UB.
    - Containers pass the allocator to their elements through uses-allocator construction. The `construct` of both `scoped_allocator_adaptor` and `polymorphic_allocator` does this; the default `allocator_traits::construct` does not.
    - pmr moves the allocation strategy into a run-time `memory_resource`: with one `monotonic_buffer_resource` and a `pmr::vector<pmr::string>`, all the memory of the whole structure comes from the same arena, and the type does not change with the resource.
    - Using pmr takes three rules of discipline: the resource must outlive the container; pmr strings and ordinary strings do not mix; copying a container falls back to the default resource.

## The problem: one arena for a whole `vector<string>`

An **arena** is a very simple allocation strategy: grab a large block of memory up front, make each allocation just bump an offset forward, make individual deallocation do nothing, and throw the whole block away when done. It suits scenarios where you build a batch of objects, use them for a while, then destroy them all together, such as one request or one frame.

First write a minimal arena allocator, give it to `std::vector<std::string>`, and replace the global `operator new` to count how many allocations went to the default heap:

```cpp run title="classic.cpp" ok
#include <cstddef>
#include <cstdio>
#include <cstdlib>
#include <new>
#include <string>
#include <vector>

int heap_allocs = 0;   // counts calls to the global operator new
void* operator new(std::size_t n) {
  ++heap_allocs;
  if (void* p = std::malloc(n)) return p;
  throw std::bad_alloc{};
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }

struct Arena {                       // one fixed buffer, only moves forward
  alignas(std::max_align_t) std::byte buf[64 * 1024];
  std::size_t used = 0;
  void* take(std::size_t n, std::size_t align) {
    used = (used + align - 1) / align * align;
    void* p = buf + used;
    used += n;
    return p;
  }
};

template <class T>
struct ArenaAlloc {
  using value_type = T;
  Arena* arena = nullptr;
  ArenaAlloc() = default;
  explicit ArenaAlloc(Arena* a) : arena(a) {}
  template <class U> ArenaAlloc(const ArenaAlloc<U>& o) : arena(o.arena) {}
  T* allocate(std::size_t n) {
    if (!arena) throw std::bad_alloc{};
    return static_cast<T*>(arena->take(n * sizeof(T), alignof(T)));
  }
  void deallocate(T*, std::size_t) {}
  bool operator==(const ArenaAlloc& o) const { return arena == o.arena; }
};

int main() {
  Arena arena;
  std::vector<std::string, ArenaAlloc<std::string>> v{ArenaAlloc<std::string>(&arena)};
  v.reserve(100);
  heap_allocs = 0;
  for (int i = 0; i < 100; ++i)
    v.emplace_back("a string long enough to need the heap");
  std::printf("arena bytes: %zu, heap allocs: %d\n", arena.used, heap_allocs);
}
```

```text
arena bytes: 2400, heap allocs: 100
```

The arena holds only 2400 bytes, exactly the 100 `std::string` objects themselves (24 bytes each with libc++ in our tests). Each string's character buffer still went through the global `operator new` once. The reason is in the types: `std::string` is `basic_string<char, char_traits<char>, std::allocator<char>>`. It has its own allocator type, which has nothing to do with the allocator of the outer vector.

To get the characters into the arena too, the string type has to change:

```cpp
using AString = std::basic_string<char, std::char_traits<char>, ArenaAlloc<char>>;
std::vector<AString, ArenaAlloc<AString>> v{ArenaAlloc<AString>(&arena)};
v.emplace_back("a string long enough to need the heap");   // throws bad_alloc
```

This still doesn't work. When the vector constructs an element it passes only `"a string..."` to `AString`'s constructor, not the allocator. Each string gets a default-constructed `ArenaAlloc` that points to no arena, and the first allocation throws `bad_alloc`. Either you add the allocator by hand on every insertion, `emplace_back("...", ArenaAlloc<char>(&arena))`, or the container has to pass the allocator down automatically.

This small example exposes two problems of classic allocators: the allocation strategy is written into the type, so changing the strategy means changing every related type; and the container's allocator is not passed to its elements automatically.

## What an allocator is

### Minimal requirements and `allocator_traits`

The standard calls the allocator requirements *Cpp17Allocator* ([[allocator.requirements.general]], explained item by item on this site under [[utility.requirements]]). An allocator is a class type that knows how to allocate and deallocate uninitialized storage for arrays of `T`. Only a few things must be written by hand: `value_type`, `allocate(n)`, `deallocate(p, n)`, a converting constructor from allocators of the same family, and `==` (Example 2 in [[allocator.requirements.general#98]] is exactly such a minimal allocator).

All other members are optional; `allocator_traits<A>` supplies defaults for them ([[allocator.requirements.general#3]]). Containers never call an allocator directly; they always go through `allocator_traits`:

```cpp run title="mini.cpp" ok
#include <cstddef>
#include <list>
#include <memory>
#include <type_traits>

template <class T>
struct Mini {
  using value_type = T;
  Mini() = default;
  template <class U> Mini(const Mini<U>&) {}
  T* allocate(std::size_t n) { return std::allocator<T>{}.allocate(n); }
  void deallocate(T* p, std::size_t n) { std::allocator<T>{}.deallocate(p, n); }
  bool operator==(const Mini&) const = default;
};

using Tr = std::allocator_traits<Mini<int>>;
static_assert(std::is_same_v<Tr::pointer, int*>);
static_assert(std::is_same_v<Tr::size_type, std::make_unsigned_t<std::ptrdiff_t>>);
static_assert(std::is_same_v<Tr::rebind_alloc<long>, Mini<long>>);
static_assert(!Tr::propagate_on_container_move_assignment::value);
static_assert(Tr::is_always_equal::value);          // empty class

int main() {
  std::list<int, Mini<int>> l{1, 2, 3};   // what actually gets allocated is nodes: Mini<node type>
}
```

The rule for each default is in [[allocator.traits.types]]. Three are used most:

- `pointer` defaults to `T*`. An allocator may also provide a class-type [[g:fancy-pointer|fancy pointer]], such as an offset pointer used in shared memory.
- `allocate` only allocates storage; it does not construct elements. Construction and destruction are done by `allocator_traits::construct` and `destroy`; when the allocator does not provide these two members, they call `construct_at(p, args...)` and `destroy_at(p)` directly ([[allocator.traits.members#6]], [[allocator.traits.members#7]]).
- `rebind_alloc<U>` turns `Mini<int>` into `Mini<U>` ([[allocator.traits.types#11]]). What `std::list<int, Mini<int>>` really allocates is its internal node type. It gets `Mini<node>` through rebind, then constructs it from the user's `Mini<int>` with the converting constructor.

For two allocators, `a1 == a2` means storage allocated by one can be deallocated by the other ([[allocator.requirements.general#54]]). The discussion of propagation below relies on this definition.

### Why the allocator is part of the type

The container stores the allocator object inside itself, and every allocation is an ordinary (non-virtual) call on it, which the compiler can inline. When the allocator is an empty class, the library implementation can also compress it to zero bytes. This design costs nothing extra for `std::allocator`. The price is that the allocation strategy becomes part of the type:

<div class="compare" markdown="1">

```cpp error
// Mini is the allocator from above
void print(const std::vector<int>&);

void f() {
  std::vector<int, Mini<int>> v{1, 2};
  print(v);  // error: different type
}
```

```cpp ok
void print(const std::pmr::vector<int>&);

void f() {
  std::pmr::monotonic_buffer_resource r;
  std::pmr::vector<int> v({1, 2}, &r);
  print(v);  // OK: the resource is not in the type
}
```

</div>

On the left, even a function that only wants to read a vector has to be written once per allocator, or written as a template. On the right is the pmr approach described later: the allocation strategy becomes a run-time pointer, and the type stays the same.

## Stateful allocators and propagation

`std::allocator` has no data members, so any two instances are equal. `ArenaAlloc` stores an `Arena*`, and two instances pointing to different arenas are unequal; such an allocator is called stateful. It raises a question: when a container is copied, assigned or swapped, should the allocator go along with the elements?

The standard's answer: a container's allocator is fixed at construction and afterwards can only be replaced by copy assignment, move assignment or swap, and only when the corresponding trait is true ([[container.reqmts#64]]):

| Operation | Member that decides the allocator | Default | Standard allocator |
|---|---|---|---|
| Copy construction `X b(a)` | `select_on_container_copy_construction()` | Returns a copy of `a`'s allocator | Same as default |
| Move construction `X b(std::move(a))` | Always move-constructed from `a`'s allocator | | |
| Copy assignment `b = a` | `propagate_on_container_copy_assignment` (POCCA) | `false_type` | False |
| Move assignment `b = std::move(a)` | `propagate_on_container_move_assignment` (POCMA) | `false_type` | True for `std::allocator` |
| Swap `a.swap(b)` | `propagate_on_container_swap` (POCS) | `false_type` | False |
| Always equal? | `is_always_equal` | `is_empty<A>` | True for `std::allocator` |

These defaults come from [[allocator.requirements.general#79]]–¶91 and [[allocator.traits.types#7]]–¶10; the two entries for `std::allocator` are in [[default.allocator.general#2]] and its class definition. The reason for not propagating by default is that the allocator represents who owns the memory. A container built from arena A should usually stay in arena A after being assigned to.

### Move assignment: element-wise moves when allocators differ

Without propagation, copy assignment is unremarkable: the left side keeps its own allocator, allocates storage with it, then copies the elements. Move assignment is different. `b = std::move(a)` wants to take over `a`'s buffer directly, but if `b`'s allocator cannot deallocate that memory, there is no way to free it correctly after the takeover:

```cpp run title="move-assign.cpp" ok
#include <cstddef>
#include <cstdio>
#include <type_traits>
#include <utility>
#include <vector>

struct Arena {
  alignas(std::max_align_t) std::byte buf[4096];
  std::size_t used = 0;
};
template <class T>
struct ArenaAlloc {
  using value_type = T;
  Arena* arena = nullptr;
  explicit ArenaAlloc(Arena* a) : arena(a) {}
  template <class U> ArenaAlloc(const ArenaAlloc<U>& o) : arena(o.arena) {}
  T* allocate(std::size_t n) {
    void* p = arena->buf + arena->used;
    arena->used += n * sizeof(T);   // the example only stores int; alignment is ignored
    return static_cast<T*>(p);
  }
  void deallocate(T*, std::size_t) {}
  bool operator==(const ArenaAlloc& o) const { return arena == o.arena; }
};
using Vec = std::vector<int, ArenaAlloc<int>>;

int main() {
  Arena a1, a2;
  Vec x({1, 2, 3, 4}, ArenaAlloc<int>(&a1));
  Vec y({5, 6, 7, 8}, ArenaAlloc<int>(&a1));
  Vec z({9, 9, 9, 9, 9, 9}, ArenaAlloc<int>(&a2));

  const int* yd = y.data();
  x = std::move(y);                       // allocators equal: take over the buffer
  std::printf("same arena:  stole=%d a1.used=%zu\n", x.data() == yd, a1.used);

  const int* zd = z.data();
  x = std::move(z);                       // allocators unequal and POCMA false: element-wise moves
  std::printf("other arena: stole=%d a1.used=%zu\n", x.data() == zd, a1.used);

  static_assert(!std::is_nothrow_move_assignable_v<Vec>);
  static_assert(std::is_nothrow_move_assignable_v<std::vector<int>>);
}
```

```text
same arena:  stole=1 a1.used=32
other arena: stole=0 a1.used=56
```

In the first assignment both allocators point to the same arena. Equal means each can deallocate the other's memory, so `x` takes over `y`'s buffer directly. In the second, `z`'s memory is in `a2`, and `x`'s allocator cannot free it. `x` has to allocate 6 new `int`s in `a1` (`a1.used` grows by 24) and then move the elements over one by one. For move assignment the standard only requires that existing elements are either move-assigned or destroyed, with linear complexity ([[container.alloc.reqmts#27]], ¶29).

Element-wise moves need to allocate memory and can throw. Only when this can be ruled out at compile time, that is, when POCMA is true or `is_always_equal` is true, is `vector`'s move assignment `noexcept`. That is why both `static_assert`s above hold: for `std::allocator` both traits are true, for `ArenaAlloc` both are false (it has a data member, so `is_empty` is false).

### Swap: UB when allocators differ

The rule for swap is stricter. When POCS is false the allocators are not swapped, and if they are unequal the behavior is undefined ([[container.reqmts#65]]). Swap must be constant-time and must not throw, so there is no room to fall back to element-wise moves:

```cpp run title="swap.cpp" ub
#include <memory_resource>
#include <vector>
int main() {
  std::pmr::monotonic_buffer_resource r1, r2;
  std::pmr::vector<int> a({1, 2}, &r1);
  std::pmr::vector<int> b({3}, &r2);
  a.swap(b);   // UB: allocators unequal, POCS false
}
```

With a default libc++ build in our tests, this program exits normally: the two vectors swapped buffers but not allocators, and from then on `a` would use `r1` to free memory that came from `r2`. With `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_EXTENSIVE`, the program traps in `swap` and terminates.

## Passing the allocator to elements: uses-allocator construction

Back to the opening problem. When a vector constructs an element it calls `allocator_traits::construct(alloc, p, args...)`, which by default is `construct_at(p, args...)`, with no allocator among the arguments. For the element to get the allocator, `construct` has to rewrite the argument list.

For this the standard defines [[g:uses-allocator-construction|uses-allocator construction]]: when constructing a `T` with allocator `alloc` and arguments `args...`, if `T` uses an allocator compatible with `alloc`, the allocator is passed in by one of two conventions; otherwise it is ignored ([[allocator.uses.construction#2]]):

1. Leading convention: call `T(allocator_arg, alloc, args...)`, where `allocator_arg` is a tag object used to distinguish overloads;
2. Trailing convention: call `T(args..., alloc)`. `std::string` and the standard containers all use this one.

Whether `T` uses a compatible allocator is decided by the trait `uses_allocator<T, Alloc>`: `T` has a nested type `allocator_type`, and `Alloc` is convertible to it ([[allocator.uses.trait#1]]). `uses_allocator_construction_args` produces the rewritten argument tuple according to these rules ([[allocator.uses.construction#5]]), with an extra overload for `pair` that handles each member recursively. This site's [[allocator.uses]] page covers all the details.

### `scoped_allocator_adaptor`

C++11's `scoped_allocator_adaptor<Outer, Inner...>` is a wrapper allocator: the container's own memory is allocated with the outer allocator, and when constructing elements it passes the inner allocator to them through uses-allocator construction ([[allocator.adaptor.members#9]]). When only one allocator type is given, the inner allocator is the adaptor itself, so however many levels of containers are nested, they all use the same allocator ([[allocator.adaptor.syn#1]]).

Change the opening example to:

```cpp
using AString = std::basic_string<char, std::char_traits<char>, ArenaAlloc<char>>;
using Outer = std::scoped_allocator_adaptor<ArenaAlloc<AString>>;
std::vector<AString, Outer> v{Outer(ArenaAlloc<AString>(&arena))};
v.reserve(100);
for (int i = 0; i < 100; ++i)
  v.emplace_back("a string long enough to need the heap");
```

```text
arena bytes: 7200, heap allocs: 0
```

This time the character buffers of the 100 strings also go into the arena, and the global heap is not used even once. Inside `construct`, the arguments of `emplace_back` are rewritten to `("a string...", ArenaAlloc<char>(&arena))`, which matches `basic_string`'s trailing-allocator constructor exactly.

<details class="fine" markdown="1"><summary>libc++ in our tests requires ArenaAlloc to be default-constructible</summary>

If you remove `ArenaAlloc() = default;`, the code above fails to compile with Clang 23 / libc++, with the error in the default argument of `basic_string(const char*, const Alloc& = Alloc())`. libc++'s `uses_allocator_construction_args` first evaluates `is_constructible_v<AString, const char(&)[38]>`, and that check instantiates the default argument `ArenaAlloc<char>()`; the error is not in the immediate context for SFINAE. As [[allocator.uses.construction#5]] is written, this check should not be needed when `uses_allocator_v` is true; whether the standard permits such an implementation is left open here. Giving the allocator a default constructor works around it.

</details>

The scoped adaptor gets the allocator to the elements, but the allocation strategy is still written into the type, and a type like `AString` is hard to interoperate with code that accepts `std::string`.

## pmr: moving the allocation strategy to run time

C++17's `<memory_resource>` (namespace `std::pmr`) takes a different approach: it puts the allocation strategy into an object with virtual functions, and the allocator type itself stays fixed.

- `memory_resource` is an abstract base class. Its public interface `allocate(bytes, align)`, `deallocate(p, bytes, align)` and `is_equal(other)` forwards to the private virtual functions `do_allocate`, `do_deallocate` and `do_is_equal` ([[mem.res.class]]). Writing your own resource means deriving from it and implementing these three functions.
- `polymorphic_allocator<T>` satisfies *Cpp17Allocator* and stores only a `memory_resource*`. The same specialization constructed with different resources can behave completely differently while having the same type ([[mem.poly.allocator.class.general#1]]).
- The standard containers and strings all have corresponding aliases in `std::pmr`, such as `namespace pmr { template<class T> using vector = std::vector<T, polymorphic_allocator<T>>; }` ([[vector.syn]]); `pmr::string` is `basic_string<char, char_traits<char>, polymorphic_allocator<char>>`.

The key piece is `polymorphic_allocator::construct`: it performs uses-allocator construction on elements ([[mem.poly.allocator.mem#15]]). So pmr does not need the scoped adaptor; the resource is passed automatically into nested pmr elements:

```cpp run title="pmr-arena.cpp" ok
#include <cstddef>
#include <cstdio>
#include <cstdlib>
#include <memory_resource>
#include <new>
#include <string>
#include <vector>

int heap_allocs = 0;
void* operator new(std::size_t n) {
  ++heap_allocs;
  if (void* p = std::malloc(n)) return p;
  throw std::bad_alloc{};
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }

int main() {
  alignas(std::max_align_t) std::byte buf[16 * 1024];
  std::pmr::monotonic_buffer_resource arena(
      buf, sizeof buf, std::pmr::null_memory_resource());   // throws bad_alloc when exhausted

  std::pmr::vector<std::pmr::string> v(&arena);
  for (int i = 0; i < 100; ++i)
    v.emplace_back("a string long enough to need the heap");

  std::printf("heap allocs: %d\n", heap_allocs);
  std::printf("same resource: %d\n",
              v[42].get_allocator().resource() == &arena);
}
```

```text
heap allocs: 0
same resource: 1
```

The vector's buffer, the new buffer after each growth, and the characters of the 100 strings all come from the 16 KB buffer on the stack. The upstream resource is `null_memory_resource()`, so as soon as the buffer runs out it throws `bad_alloc` instead of quietly switching to the heap. The program finishing normally is itself proof that all memory came from the arena.

### Resources provided by the standard

| Resource | Behavior | Clause |
|---|---|---|
| `new_delete_resource()` | Uses `::operator new` and `::operator delete`; the initial value of the default resource | [[mem.res.global#1]] |
| `null_memory_resource()` | `allocate` always throws `bad_alloc`; `deallocate` does nothing | [[mem.res.global#2]] |
| `monotonic_buffer_resource` | Arena: bumps a pointer in the current buffer and asks upstream for a bigger block when it runs out; `deallocate` does nothing; everything is returned at destruction or on `release()` | [[mem.res.monotonic.buffer]] |
| `unsynchronized_pool_resource` | Split into pools by block size; freed blocks can be reused; must not be accessed from multiple threads at once | [[mem.res.pool]] |
| `synchronized_pool_resource` | Same as above, but can be accessed from multiple threads at once | [[mem.res.pool]] |

The last three each have an upstream resource from which they get their own memory. Resources can be stacked layer by layer this way, for example a pool resource with an arena as its upstream.

`monotonic_buffer_resource`'s `do_deallocate` does nothing ([[mem.res.monotonic.buffer.mem#7]]), and the memory it occupies only grows (¶9). Old buffers dropped when a vector grows, or erased strings, are not reclaimed until the arena is destroyed. When putting a container with repeated insertions and erasures into an arena, `reserve` first, or use a pool resource instead.

### The default resource

When no resource is given explicitly, pmr uses the [[g:default-memory-resource-pointer|default memory resource pointer]]: its initial value is `new_delete_resource()`, it can be changed with `set_default_resource` and read with `get_default_resource` ([[mem.res.global#3]]–¶7). A default-constructed `polymorphic_allocator` takes the default resource at that moment ([[mem.poly.allocator.ctor#1]]), and the default constructors of `monotonic_buffer_resource()` and the pool resources also use the default resource at that moment as their upstream.

In tests the default resource is often set to `null_memory_resource()`: any place that should have specified a resource but forgot immediately throws `bad_alloc`. The pitfalls section below uses this technique.

### Why `polymorphic_allocator` does not propagate

The design principle of `polymorphic_allocator` is that a container binds to one resource at construction and keeps it for life (the [[mem.poly.allocator.class]] page discusses this in detail). Concretely, three rules:

1. The copy assignment operator is deleted, so an allocator object cannot be repointed to another resource;
2. None of the `propagate_on_container_*` traits are defined, so all three take the default false;
3. `select_on_container_copy_construction()` returns a default-constructed `polymorphic_allocator`, that is, the default resource; the standard's note says memory resources do not propagate ([[mem.poly.allocator.mem#18]], ¶19).

Resources are often tied to a scope, such as an arena in a function. If copying a container inherited the resource automatically, a copy stored elsewhere that outlives the arena would dangle. Making the copy fall back to the default resource trades a bit of surprise for safety. When the copy should also live in the same resource, pass it explicitly: `std::pmr::vector<T> copy(v, &arena);`.

The other side of not propagating: `is_always_equal` is also false for pmr containers, so `pmr::vector`'s move assignment is not `noexcept`. Move assignment between two pmr containers with different resources moves elements one by one, and swap is the UB from the previous section.

## Performance: measurements in our tests

The following compares three ways to build a vector of 100,000 strings of 37 characters and then destroy it. The string length exceeds the internal buffer of the [[g:short-string-optimization|short string optimization]], so each one needs its own allocation:

```cpp run title="bench.cpp" ok
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <memory_resource>
#include <string>
#include <vector>

constexpr int N = 100'000, ROUNDS = 50;
const char* text = "a string long enough to need the heap";

template <class F> double best_ms(F f) {
  double best = 1e9;
  for (int r = 0; r < ROUNDS; ++r) {
    auto t0 = std::chrono::steady_clock::now();
    f();
    auto t1 = std::chrono::steady_clock::now();
    best = std::min(best, std::chrono::duration<double, std::milli>(t1 - t0).count());
  }
  return best;
}

int main() {
  double heap = best_ms([] {
    std::vector<std::string> v;
    v.reserve(N);
    for (int i = 0; i < N; ++i) v.emplace_back(text);
  });
  double mono = best_ms([] {
    std::pmr::monotonic_buffer_resource arena;
    std::pmr::vector<std::pmr::string> v(&arena);
    v.reserve(N);
    for (int i = 0; i < N; ++i) v.emplace_back(text);
  });
  double pool = best_ms([] {
    std::pmr::unsynchronized_pool_resource pool;
    std::pmr::vector<std::pmr::string> v(&pool);
    v.reserve(N);
    for (int i = 0; i < N; ++i) v.emplace_back(text);
  });
  std::printf("std::allocator   %.2f ms\n", heap);
  std::printf("monotonic arena  %.2f ms\n", mono);
  std::printf("unsync pool      %.2f ms\n", pool);
}
```

On an Apple M2 Pro (macOS, Clang 23 `-O2`, libc++), three consecutive runs, each entry taking the fastest of 50 rounds:

| Approach | Time |
|---|---|
| `std::vector<std::string>` | about 3.3 ms |
| `monotonic_buffer_resource` | about 1.2 ms |
| `unsynchronized_pool_resource` | about 1.6 ms |

The arena is faster for two reasons: each allocation just bumps a pointer without going through the system allocator, and at destruction 100,000 calls to `free` become one bulk release. This is an observation on one machine with one workload; a different system allocator (such as jemalloc or mimalloc) or a different string length will change the gap. Also, every pmr allocation costs one extra virtual call, so there is no gain where allocations are rare. Whether it is worth using should be decided by measuring your own program.

## Pitfalls

### The resource dies before the container

```cpp run title="lifetime.cpp" ub
#include <cstdio>
#include <memory_resource>
#include <string>
#include <vector>

std::pmr::vector<std::pmr::string> load() {
  std::pmr::monotonic_buffer_resource arena;   // local resource
  std::pmr::vector<std::pmr::string> v(&arena);
  v.emplace_back("a string long enough to need the heap");
  return v;                                    // v is moved out, but the resource is destroyed here
}

int main() {
  auto v = load();
  std::printf("%s\n", v[0].c_str());           // UB: memory already returned upstream
}
```

`return v;` move-constructs the return value, and the allocator moves with it, so the returned vector still points to the local `arena`. `arena` is destroyed when the function ends and returns all its memory upstream; from then on the returned vector dangles (see [[topics/dangling-references]]). When the container is destroyed it also calls the virtual `deallocate` on a resource that has already been destroyed, which is UB as well. AddressSanitizer's report:

```text
$ clang++ -std=c++2c -g -gdwarf-4 -fsanitize=address,undefined lifetime.cpp && ./a.out
==ERROR: AddressSanitizer: heap-use-after-free on address 0x61d000000877 ...
    #4 ... in main lifetime.cpp:15
freed by thread T0 here:
    #2 ... in std::__1::pmr::monotonic_buffer_resource::release() ...
    #3 ... in std::__1::pmr::monotonic_buffer_resource::~monotonic_buffer_resource() ...
    #5 ... in load() lifetime.cpp:11
```

The compiler gives no warning at all. The resource has to live in a scope longer than all of its users; the usual approach is for the caller to own the resource and pass a pointer in.

### Mixing pmr strings and ordinary strings

`std::string` and `std::pmr::string` are two unrelated types with no implicit conversion between them:

```cpp
void take_std(const std::string&);
void take_view(std::string_view);

void f(std::pmr::vector<std::pmr::string>& v, const std::string& s) {
  take_std(v[0]);              // error: no matching function
  v.push_back(s);              // error: no matching member function
  std::string t = v[0];        // error: no viable conversion
  take_std(std::string(v[0])); // OK: copies to the default heap
  v.emplace_back(s);           // OK: copies into v's resource
  take_view(v[0]);             // OK: no copy
}
```

Every form that compiles has to construct a new string explicitly, costing one allocation and one copy each time. Using `std::string_view` for interface parameters accepts both kinds of string without copying.

A subtler mistake is the wrong element type: `std::pmr::vector<std::string>` compiles and the vector's buffer is in the arena, but `std::string`'s `allocator_type` is `std::allocator<char>`, which `polymorphic_allocator` cannot convert to. `uses_allocator` is false, the resource is ignored, and the characters still go to the global heap. Even setting the default resource to `null_memory_resource()` won't catch it, because `std::string` never goes through pmr at all.

### Copying a container falls back to the default resource

```cpp run title="copy.cpp" ok
#include <cstdio>
#include <memory_resource>
#include <new>
#include <string>
#include <vector>

int main() {
  std::pmr::monotonic_buffer_resource arena;   // upstream is the current default: new_delete
  std::pmr::set_default_resource(std::pmr::null_memory_resource());  // guard

  std::pmr::vector<std::pmr::string> v(&arena);
  v.emplace_back("a string long enough to need the heap");

  auto moved = std::move(v);                        // move: the allocator goes along
  std::printf("moved uses arena: %d\n",
              moved.get_allocator().resource() == &arena);

  std::pmr::vector<std::pmr::string> same(moved, &arena);   // resource given explicitly
  std::printf("explicit copy ok, size %zu\n", same.size());

  try {
    auto copy = moved;                              // copy: falls back to the default resource
  } catch (const std::bad_alloc&) {
    std::puts("copy went to the default resource");
  }
}
```

```text
moved uses arena: 1
explicit copy ok, size 1
copy went to the default resource
```

Move construction move-constructs the new allocator from the original container's allocator ([[container.alloc.reqmts#16]]), so the resource is unchanged. `auto copy = moved;` is copy construction; the allocator comes from `select_on_container_copy_construction()`, that is, the default resource, which the guard catches here. Note that `arena` must be constructed before the guard is set, or its upstream would also be `null_memory_resource()`.

The same fallback happens in every copy construction: passing by value, returning a data member by value, capturing by value in a lambda, and so on. Wherever the copy needs to stay in the original resource, use the constructor with an allocator parameter, `X(t, alloc)` ([[container.alloc.reqmts#14]]).

!!! history
    C++98 allocators were considered stateless: implementations could assume that allocators of the same type were all equal. C++11 rebuilt the allocator model around `allocator_traits` ([[N2982]]), giving stateful allocators explicit propagation rules, and `scoped_allocator_adaptor` was added in the same period. pmr was proposed in [[N3916]], went first into the Library Fundamentals TS, and was merged into C++17 via [[P0220R1]]. C++20's [[P0339R6]] made `byte` the default template argument of `polymorphic_allocator` and added members such as `allocate_bytes` and `new_object`, so that `polymorphic_allocator<>` can serve as a general-purpose allocator type.

## Questions

!!! question "1"
    `std::pmr::vector<std::pmr::vector<int>> outer(&arena); outer.emplace_back();` Which resource does the newly inserted inner vector use? What if it is written `outer.push_back(std::pmr::vector<int>{1, 2});`?

<details markdown="1">
<summary>Answer</summary>

`emplace_back()` uses uses-allocator construction; the inner vector calls `vector(const allocator_type&)`, and its resource is `arena`.

`push_back(std::pmr::vector<int>{1, 2})` first constructs a temporary vector with the default resource, then constructs the element from it. `polymorphic_allocator::construct` rewrites the arguments to `(std::move(tmp), alloc)`, calling the allocator-extended move constructor `X(rv, m)`. The new element's resource is `arena`; the temporary's resource is the default resource. The two are unequal, so the elements are moved into the arena one by one, with linear complexity ([[container.alloc.reqmts#19]], ¶20). The temporary's own allocation goes to the default resource.
</details>

!!! question "2"
    An allocator sets POCCA, POCMA and POCS all to `true_type`. After two containers using it are swapped, are their elements still in their original arenas?

<details markdown="1">
<summary>Answer</summary>

Yes. When POCS is true, swap exchanges both the buffers and the allocators ([[container.reqmts#65]]). The elements' memory does not move; it only changes owner, and the new owner gets exactly the allocator that can free that memory. So the swap is no longer UB. The cost is that the container's owner changes with the swap: a container that belonged to arena A before the swap uses arena B afterwards, and if B is destroyed first, that container dangles.
</details>

!!! question "3"
    `std::allocator` used to define the member type `is_always_equal = true_type`. C++26 removed it ([[P2868R3]]), while `allocator_traits<std::allocator<T>>::is_always_equal` is still true. What is gained by removing it?

<details markdown="1">
<summary>Answer</summary>

When an allocator lacks this member, `allocator_traits` uses `is_empty<A>`. `std::allocator` is an empty class, so the result is still true, and the removal has no effect on it.

The problem is with derived classes. Suppose someone derives a stateful allocator from `std::allocator<T>` (say, adding an `Arena*` member). The member type `is_always_equal` is inherited too, and containers will consider any two instances equal: move assignment takes over the buffer from another arena directly, and memory is freed with the wrong allocator. With the member removed, the derived class's `is_always_equal` goes back to `is_empty`, which is false, the correct answer. In our tests libc++ gives `true` for such a derived class under `-std=c++20` and `false` under `-std=c++2c`. An inherited POCMA of true does not have this problem: it only makes the allocator move together with the buffer and cannot cause a wrong deallocation.
</details>

## Summary

| Question | Classic allocators | pmr |
|---|---|---|
| Where the allocation strategy lives | In the allocator type, fixed at compile time | In a `memory_resource` object, chosen at run time |
| Are containers with different strategies the same type? | No | Yes |
| How elements get the allocator | They don't by default; use `scoped_allocator_adaptor` | `polymorphic_allocator::construct` does uses-allocator construction automatically |
| Copy construction | Copies the allocator by default | Falls back to the default resource |
| Assignment, swap | Depends on POCCA, POCMA, POCS | Never propagates; with different resources, move assignment moves element-wise and swap is UB |
| Cost per allocation | Can be inlined | One virtual call |
| Main risks | Type proliferation, interfaces hard to reuse | Resource lifetime, mixing strings, changed resource after copying |
