---
title: Exception safety and noexcept
summary: "What state an object is left in when an operation throws partway through: what stack unwinding destroys, the basic, strong and nothrow guarantees and how the standard library states them, the cost of copy-and-swap, why move constructors should be noexcept, what happens when a noexcept function throws, and destructors, RAII and scope guards."
tags: exceptions, exception safety, noexcept, RAII, topic
updated: 2026-10-19
---

!!! tldr
    - Exception safety asks: after an operation throws partway through, what state is the object in, and were any resources leaked? The answers come in three levels: nothrow, the strong guarantee (no effect on failure), and the basic guarantee (still valid after failure, but with an indeterminate value).
    - The general way to achieve the strong guarantee is to do all the work that can fail on the side first, then commit with operations that can't fail. Copy-and-swap is one instance of this; its cost is a fresh allocation every time.
    - When `std::vector` grows, it moves elements only if the move constructor doesn't throw (or the type isn't copyable); otherwise it copies. Forget `noexcept` on a hand-written move constructor and `vector` will always copy.
    - `noexcept` is a promise, not a check. When an exception actually leaves a `noexcept` function, `std::terminate` is called, and whether the stack is unwound is implementation-defined.
    - Destructors don't throw by default. A destructor that throws during stack unwinding terminates the program. Cleanup should be handed to RAII objects; use `std::uncaught_exceptions` when you need to tell success from failure.

## An assignment operator that breaks the object

```cpp run title="broken-assign.cpp" ub
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <new>

bool fail_next = false;            // fault injection: make the next new[] fail
void* operator new[](std::size_t n) {
  if (fail_next) { fail_next = false; throw std::bad_alloc(); }
  if (void* p = std::malloc(n)) return p;
  throw std::bad_alloc();
}
void operator delete[](void* p) noexcept { std::free(p); }

class Buffer {
  std::size_t n_;
  int* p_;
public:
  explicit Buffer(std::size_t n) : n_(n), p_(new int[n]{}) {}
  Buffer(const Buffer&) = delete;
  ~Buffer() { delete[] p_; }
  Buffer& operator=(const Buffer& o) {
    if (this != &o) {
      delete[] p_;                 // free the old array first
      p_ = new int[o.n_];          // throws: p_ still points to the freed array
      n_ = o.n_;
      std::copy_n(o.p_, n_, p_);
    }
    return *this;
  }
};

int main() {
  Buffer a(4), b(8);
  try {
    fail_next = true;
    a = b;
  } catch (const std::bad_alloc&) {
    std::puts("assignment failed");
  }
}                                  // ~Buffer delete[]s the same pointer again
```

`operator=` frees the old array before allocating the new one. When the allocation fails, the exception leaves the function with `a.p_` still pointing to freed memory, and `a`'s invariant is broken. The caller catches the exception and the program seems to recover, but when `a` goes out of scope its destructor frees the same pointer again, which is UB. Running with Clang 23 and `-fsanitize=address` reports `attempting double-free`, with the second free in `Buffer::~Buffer()` and the first in `Buffer::operator=`.

The fix only needs a change of order: do what can fail first, then what can't.

```cpp run title="fixed-assign.cpp" ok
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <new>

bool fail_next = false;
void* operator new[](std::size_t n) {
  if (fail_next) { fail_next = false; throw std::bad_alloc(); }
  if (void* p = std::malloc(n)) return p;
  throw std::bad_alloc();
}
void operator delete[](void* p) noexcept { std::free(p); }

class Buffer {
  std::size_t n_;
  int* p_;
public:
  explicit Buffer(std::size_t n) : n_(n), p_(new int[n]{}) {}
  ~Buffer() { delete[] p_; }
  std::size_t size() const { return n_; }
  Buffer& operator=(const Buffer& o) {
    int* q = new int[o.n_];        // may throw: *this not yet modified
    std::copy_n(o.p_, o.n_, q);    // copying ints doesn't throw
    delete[] p_;                   // nothing can fail from here on
    p_ = q;
    n_ = o.n_;
    return *this;
  }
};

int main() {
  Buffer a(4), b(8);
  try { fail_next = true; a = b; } catch (const std::bad_alloc&) {}
  std::printf("%zu\n", a.size());  // 4: unchanged
  a = b;
  std::printf("%zu\n", a.size());  // 8
}
```

Now when the allocation fails, `a` is left untouched, as if the assignment never happened. This version also no longer needs the `this != &o` check: on self-assignment it first makes a copy, then frees the old array, and the result is still correct.

Properties like these, what state an object is in after an operation throws partway through and whether resources were leaked, are collectively called **exception safety**. To analyze it, you first need to know what the language does when an exception is thrown.

## What happens on a throw

### Stack unwinding

As an exception travels from the `throw` to the `catch` clause (handler) that catches it, every automatic object constructed since entry to that try block and not yet destroyed is destroyed in reverse order of construction ([[except.ctor#2]]). This process is called [[g:stack-unwinding|stack unwinding]].

C++ has no `finally`; cleanup relies on exactly this rule: hand the resource to a local object whose destructor runs on both normal return and exceptional exit. This idiom is called **RAII** (resource acquisition is initialization), and we'll come back to it later. `Buffer` in the example above is itself an RAII class; its problem was the order of steps in the assignment operator.

### Failing halfway through construction

When a constructor throws, the object's lifetime never began, and its own destructor doesn't run. Base classes and members whose initialization has completed are destroyed in reverse order; those not yet initialized are unaffected ([[except.ctor#3]]).

<div class="compare" markdown="1">

```cpp
struct Leaky {
  int* p;
  int* q;
  Leaky()
    : p(new int[100]),
      q(new int[100]) {}  // throws: p leaks
  ~Leaky() { delete[] p; delete[] q; }
};
```

```cpp
struct Safe {
  std::unique_ptr<int[]> p;
  std::unique_ptr<int[]> q;
  Safe()
    : p(new int[100]),
      q(new int[100]) {}  // throws: p is destroyed
};
```

</div>

On the left, when the second `new` throws, `~Leaky` doesn't run, and `p` is an `int*` with no destructor to call, so the memory leaks. On the right, `p` is a fully constructed subobject, and its destructor frees the memory during unwinding. This gives a rule: if a class manages several resources, have each one managed by a separate subobject. A clause-by-clause explanation, and the special case of delegating constructors, are in [[except.ctor]].

### The function-try-block of a constructor

To catch exceptions thrown while initializing members inside a constructor, the `try` must also enclose the member initializer list. This form is called a **function-try-block**:

```cpp run title="ctor-function-try-block.cpp" ok
#include <cstdio>
#include <stdexcept>

struct Conn {
  explicit Conn(const char* host) {
    if (!*host) throw std::invalid_argument("empty host");
  }
};

struct Client {
  Conn conn;
  explicit Client(const char* host) try : conn(host) {
  } catch (const std::invalid_argument& e) {
    std::printf("Client: %s\n", e.what());
  }                                // reaching the end: rethrown automatically
};

int main() {
  try {
    Client c("");
  } catch (const std::exception& e) {
    std::printf("main: %s\n", e.what());
  }
}
```

The output is `Client: empty host` and `main: empty host`. A constructor's function-try-block can't swallow the exception: when control reaches the end of the handler, the current exception is rethrown automatically ([[except.handle#14]]), and a `return` in the handler is ill-formed ([[except.handle#13]]). The reasoning is simple: the member wasn't constructed, so there is no object to give to the caller.

So it is only good for two things: logging, or translating the exception into another type and throwing that. By the time the handler is entered, the constructed members and bases have already been destroyed ([[except.ctor#3]]), and accessing the object's non-static members or bases in the handler is UB ([[except.handle#11]]). Releasing resources isn't its job either; leave that to the subobjects' destructors.

## The three guarantees

When the assignment in `fixed-assign.cpp` fails, the object is untouched; some operations can only guarantee that the object is still usable after failure. Classified by the state after failure, exception safety has three levels. The classification comes from David Abrahams's work during the standardization of the STL and is usually called the Abrahams guarantees:

| Guarantee | After failure | Typical operations |
|---|---|---|
| **Nothrow guarantee** | Can't fail | Destructors, `swap`, move construction, `pop_back` |
| **Strong guarantee** | The state is the same as before the call, as if it was never called | `vector::push_back`, the assignment in `fixed-assign.cpp` |
| **Basic guarantee** | Invariants hold and nothing leaks, but the value is indeterminate | `vector` copy assignment, `insert` in the middle of a `vector` |

An operation with no guarantee at all, such as the opening `broken-assign.cpp`, isn't even safe to destroy after failure.

The three levels build on each other. The strong guarantee usually relies on doing all the work that can fail on the side, then committing with nothrow operations; without nothrow operations there is nothing to commit with. The basic guarantee requires that every resource is owned by some RAII object at every moment.

### How the standard library states them

The standard's text doesn't use names like basic and strong; it spells out the effect of failure function by function:

- The strong guarantee is written as "has no effects" or "there are no effects";
- Nothrow is written as `noexcept`, or *Throws*: Nothing;
- The closest thing to the basic guarantee is the [[g:valid-but-unspecified-state|valid but unspecified state]] ([[defns.valid]]): the object's invariants hold, and all operations without preconditions can be called. Moved-from standard library objects are in this state by default ([[lib.types.movedfrom#1]]).

The library-wide rules are in [[res.on.exception.handling]]: library functions report failure by throwing the types listed in their *Throws*: paragraph (or types derived from them) (¶1); standard library destructors don't throw and behave as if they had a non-throwing exception specification (¶3); functions without a *Throws*: paragraph that aren't `noexcept` may throw implementation-defined exceptions, most commonly `bad_alloc` (¶4); implementations may add `noexcept` to non-virtual functions (¶5). Conversely, the library places requirements on user code: if a destructor called by the standard library exits via an exception, the behavior is undefined ([[res.on.functions#2.4]]).

The rules for containers are collected in [[container.reqmts#66]]: a single-element `insert` or `emplace` that throws has no effect (66.1); `push_back`, `push_front` and the corresponding `emplace` have no effect when they throw (66.2); `erase`, `clear`, `pop_back`, `pop_front` and `swap` don't throw (66.3, 66.5). The paragraph states at the outset that associative containers, unordered containers, `deque`, `inplace_vector` and `vector` have their own rules.

The exception for `vector` is in [[vector.modifiers#2]], in three layers:

1. If the exception doesn't come from `T`'s copy or move constructor or assignment, for example an allocation failure: no effect;
2. If a single element is inserted at the end and `T` is copy-insertable or `is_nothrow_move_constructible_v<T>` is true: no effect;
3. Otherwise, if the exception comes from the move constructor of a non-copyable `T`: the effects are unspecified.

Layers 2 and 3 concern the element's move constructor and are discussed separately below. For insertion in the middle with an exception from an operation of `T`, the standard doesn't promise no effect, so there is only the basic guarantee.

For some components the guarantee depends on the element type. For `optional`'s copy assignment, if `T`'s copy assignment throws, the state of the contained value "is as defined by the exception safety guarantee of T's copy assignment" ([[optional.assign#7]]). A generic component can only pass on whatever guarantee its elements provide.

### Container copy assignment has only the basic guarantee

For `t = v`, [[container.reqmts#18]] specifies only the postcondition on success, `t == v`; it says nothing about failure.

```cpp run title="vector-assign-basic.cpp" unspecified
#include <cstdio>
#include <vector>

int budget = 2;                    // throws on the 3rd copy assignment
struct E {
  int v;
  E(int x) : v(x) {}
  E(const E&) = default;
  E& operator=(const E& o) {
    if (budget-- == 0) throw 0;
    v = o.v;
    return *this;
  }
};

int main() {
  std::vector<E> a(5, E(0)), b(5, E(1));
  try { a = b; } catch (int) {}
  for (const E& e : a) std::printf("%d ", e.v);
  std::puts("");
}
```

libc++ in our tests prints `1 1 0 0 0`: when capacity is sufficient, `vector` copy-assigns over the existing elements one by one, and when the third throws, the first two have already changed. This is a deliberate choice; the next section explains why.

## copy-and-swap

Give `Buffer` a move constructor and a non-throwing `swap`, and the assignment operator can be written as:

```cpp run title="copy-and-swap.cpp" ok
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <new>
#include <type_traits>
#include <utility>
#include <vector>

int allocs = 0;                    // counts heap allocations
void* operator new(std::size_t n) {
  ++allocs;
  if (void* p = std::malloc(n)) return p;
  throw std::bad_alloc();
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }

class Buffer {
  std::size_t n_ = 0;
  int* p_ = nullptr;
public:
  explicit Buffer(std::size_t n) : n_(n), p_(new int[n]{}) {}
  Buffer(const Buffer& o) : n_(o.n_), p_(new int[o.n_]) {
    std::copy_n(o.p_, n_, p_);
  }
  Buffer(Buffer&& o) noexcept
      : n_(std::exchange(o.n_, 0)), p_(std::exchange(o.p_, nullptr)) {}
  ~Buffer() { delete[] p_; }
  friend void swap(Buffer& a, Buffer& b) noexcept {
    std::swap(a.n_, b.n_);
    std::swap(a.p_, b.p_);
  }
  Buffer& operator=(Buffer o) noexcept {   // by-value parameter: the copy happens in the caller
    swap(*this, o);
    return *this;                          // o is destroyed, taking the old array with it
  }
};

static_assert(std::is_nothrow_move_assignable_v<Buffer>);
static_assert(!std::is_nothrow_copy_assignable_v<Buffer>);

int main() {
  Buffer a(1000), b(1000);
  std::vector<int> u(1000), v(1000);
  allocs = 0;
  for (int i = 0; i < 100; ++i) a = b;
  std::printf("Buffer copy-and-swap: %d allocations\n", allocs);
  allocs = 0;
  for (int i = 0; i < 100; ++i) u = v;
  std::printf("std::vector<int>:     %d allocations\n", allocs);
}
```

This is **copy-and-swap**: the parameter `o` is passed by value, initialized with the copy constructor for `a = b` and with the move constructor for `a = std::move(b)`, so a single operator serves as both copy and move assignment. All the work that can fail is done while initializing the parameter, when `*this` hasn't been touched yet; the body contains only the non-throwing `swap`.

The function itself can be marked `noexcept`, because the parameter is initialized in the caller. But the expression `a = b` includes that copy, so `is_nothrow_copy_assignable_v<Buffer>` is still `false`, which matches the facts.

The cost of copy-and-swap is in the output: with Clang 23 at `-O2`, 100 assignments of `Buffer` allocated memory 100 times, while assignments of a `std::vector<int>` of the same size allocated not once, because it simply reuses its existing storage. The strong guarantee requires keeping the old state until the new state is fully built, so the old storage can't be reused in the meantime.

That is why the standard library chose the basic guarantee for `vector`'s copy assignment. A caller that needs the strong guarantee can pay the cost itself:

```cpp
std::vector<T> tmp = b;   // may fail: a is unaffected
a.swap(tmp);              // doesn't throw
```

Conversely, if the library paid it on everyone's behalf, callers that don't need the strong guarantee would have no way to get the performance back. This is a general design principle: implement operations with the basic guarantee, and let callers layer the strong guarantee on top when they need it.

## Why move constructors should be noexcept

### Copies and moves during `vector` growth

When a `vector` runs out of capacity, it allocates larger storage and moves the old elements over. Moving them with the move constructor is cheaper than copying, but if a move throws halfway through, the earlier elements have already been moved out and can't be restored, so the strong guarantee is lost.

```cpp run title="realloc-counts.cpp" ok
#include <cstdio>
#include <type_traits>
#include <vector>

int copies, moves;

template<bool NoexceptMove, bool Copyable>
struct T {
  int v;
  T(int x) : v(x) {}
  T(const T& o) requires Copyable : v(o.v) { ++copies; }
  T(T&& o) noexcept(NoexceptMove) : v(o.v) { ++moves; }
};

template<class U>
void run(const char* name) {
  copies = moves = 0;
  std::vector<U> v;
  for (int i = 0; i < 1000; ++i) v.emplace_back(i);   // only relocation during growth is counted
  std::printf("%-26s copies=%4d moves=%4d\n", name, copies, moves);
}

int main() {
  run<T<true,  true >>("noexcept move");
  run<T<false, true >>("throwing move, copyable");
  run<T<false, false>>("throwing move, move-only");
}
```

Output with Clang 23 + libc++:

```text
noexcept move              copies=   0 moves=1023
throwing move, copyable    copies=1023 moves=   0
throwing move, move-only   copies=   0 moves=1023
```

libc++'s capacity doubles 1, 2, 4, …, 1024, and ten reallocations relocate 1 + 2 + … + 512 = 1023 elements in total. The three types differ only in whether relocation uses copies or moves:

- The move constructor is `noexcept`: move, and the strong guarantee still holds;
- The move may throw, but the type is copyable: copy; on error, just discard the new storage and the old elements are intact;
- Move-only, and the move may throw: there is no choice but to move and give up the strong guarantee; this is the unspecified effect of layer 3 in [[vector.modifiers#2]].

This decision is encoded by `std::move_if_noexcept` ([[forward]]), whose return type is:

```cpp
conditional_t<!is_nothrow_move_constructible_v<T> && is_copy_constructible_v<T>,
              const T&, T&&>
```

Returning `const T&` selects the copy constructor; returning `T&&` selects the move constructor.

### The visible difference on failure

```cpp run title="realloc-failure.cpp" unspecified
#include <cstdio>
#include <vector>

int budget = 1000;                 // number of copies or moves that may still succeed
template<bool Copyable>
struct T {
  int v;
  T(int x) : v(x) {}
  T(const T& o) requires Copyable : v(o.v) { if (budget-- == 0) throw 0; }
  T(T&& o) : v(o.v) { if (budget-- == 0) throw 0; o.v = -1; }   // no noexcept
};

template<class U> void test(const char* name) {
  std::vector<U> v;
  for (int i = 0; i < 4; ++i) v.emplace_back(i);   // size 4, capacity 4
  budget = 2;                                      // the 3rd relocation during growth throws
  try { v.emplace_back(4); } catch (int) {}
  std::printf("%-10s size=%zu:", name, v.size());
  for (auto& e : v) std::printf(" %d", e.v);
  std::puts("");
}

int main() {
  test<T<true>>("copyable");     // no effect: guaranteed by the standard
  test<T<false>>("move-only");   // effects unspecified
}
```

In our tests the output is `copyable   size=4: 0 1 2 3` and `move-only  size=4: -1 -1 2 3`. For the copyable type, a failed growth leaves everything as it was; for the move-only type, the first two elements have already been moved out, and what's left in the `vector` are moved-from objects.

### Making the move constructor noexcept

`std::is_nothrow_move_constructible_v<T>` queries the exception specification of the move constructor, not its body. A hand-written move constructor without `noexcept` is potentially-throwing; for one that is implicitly declared or `= default`, the exception specification is deduced from the members ([[except.spec#7]]).

```cpp ok
#include <string>
#include <type_traits>
#include <utility>

struct A {                         // everything implicitly declared
  std::string s;
};
struct B {                         // hand-written move constructor, forgot noexcept
  std::string s;
  B(B&& o) : s(std::move(o.s)) {}
};
struct C {                         // = default: deduced from members
  std::string s;
  C(C&&) = default;
  ~C() {}                          // destructor without a specification: implicitly noexcept
};
struct D { B b; };                 // member B's move may throw, so D's does too

static_assert( std::is_nothrow_move_constructible_v<A>);
static_assert(!std::is_nothrow_move_constructible_v<B>);
static_assert( std::is_nothrow_move_constructible_v<C>);
static_assert(!std::is_nothrow_move_constructible_v<D>);
static_assert( std::is_nothrow_destructible_v<C>);
static_assert(!std::is_nothrow_copy_constructible_v<A>);  // copying a string allocates
```

`B`'s problem is contagious: any class with a `B` member also has a potentially-throwing implicit move constructor, and in a `vector` it gets copied on growth as well. Write `= default` wherever you can; for move operations you must write by hand, add `noexcept` after confirming they really can't throw. A move constructor usually just transfers pointers and can't fail anyway.

When special member functions are implicitly declared, and how an empty destructor turns moves into copies, see [[topics/special-members-and-elision]].

!!! pitfall "`is_nothrow_move_constructible` counts the destructor too"
    This trait tests the expression `T(std::declval<T>())`, which contains a temporary that has to be destroyed. For a type whose move constructor is `noexcept` but whose destructor is `noexcept(false)`, libc++ in our tests gives `false`, and `vector` still copies on growth. This is the known library issue [[LWG2116]]; see [[except.spec]].

!!! history "Where noexcept came from"
    C++98's `push_back` already provided the strong guarantee, copying elements during growth. When C++11 introduced move semantics, it was found that a throwing move would break that existing guarantee ([[N2855]]). The final solution ([[N3050]]) allowed move constructors to throw, while adding `noexcept` and `move_if_noexcept` so the library could distinguish the two cases at compile time. The story is in [[history/move-semantics]].

## The noexcept specifier and the noexcept operator

The same keyword has two uses:

- The **noexcept specifier** goes at the end of a function declaration: `void f() noexcept;` or `void f() noexcept(condition);`. It specifies the function's exception specification, that is, whether the function may exit via an exception ([[except.spec#1]]).
- The **noexcept operator** `noexcept(expression)` is a compile-time `bool` constant; the expression is not evaluated. If any part of the expression is potentially-throwing, such as a call to a function not marked `noexcept`, the result is `false` ([[expr.unary.noexcept#2]]).

Together they form the `noexcept(noexcept(...))` common in generic code: the outer one is the specifier, the inner one the operator. A wrapper type's exception specification should follow that of the wrapped type:

```cpp ok
#include <string>
#include <type_traits>
#include <utility>
#include <vector>

template<class T>
struct Wrapper {
  T value;
  Wrapper(Wrapper&& o) noexcept(std::is_nothrow_move_constructible_v<T>)
      : value(std::move(o.value)) {}
  friend void swap(Wrapper& a, Wrapper& b)
      noexcept(noexcept(std::swap(a.value, b.value))) {   // specifier wrapping the operator
    std::swap(a.value, b.value);
  }
};

struct Slow { Slow(Slow&&); Slow& operator=(Slow&&); };   // moves are not noexcept

static_assert( std::is_nothrow_move_constructible_v<Wrapper<std::string>>);
static_assert(!std::is_nothrow_move_constructible_v<Wrapper<Slow>>);
static_assert( std::is_nothrow_swappable_v<Wrapper<std::vector<int>>>);
static_assert(!std::is_nothrow_swappable_v<Wrapper<Slow>>);
```

With an unconditional `noexcept`, moving a `Wrapper<Slow>` terminates the program as soon as `Slow` throws; without one, `Wrapper<std::string>` gets copied when put in a `vector`. The conditional `noexcept` gets both cases right.

Without a specifier, a few default rules apply to the exception specification ([[except.spec#4]]): ordinary functions are potentially-throwing; destructors and deallocation functions are non-throwing unless some subobject's destructor is potentially-throwing ([[except.spec#8]], [[except.spec#10]]); implicitly declared special member functions, and those defaulted on their first declaration, are deduced from the functions they would call ([[except.spec#7]], [[except.spec#9]]).

### When a noexcept function throws

The compiler doesn't check whether a `noexcept` function can throw. When an exception actually leaves a `noexcept` function, the program calls `std::terminate` ([[except.handle#7]]).

```cpp run title="noexcept-terminate.cpp" impl
#include <cstdio>
#include <stdexcept>

struct Guard {
  const char* n;
  ~Guard() { std::fprintf(stderr, "~%s\n", n); }
};

void parse() { Guard g{"parse"}; throw std::runtime_error("bad input"); }
void handle() noexcept { Guard g{"handle"}; parse(); }

int main() {
  Guard g{"main"};
  try {
    handle();
  } catch (...) {
    std::fputs("caught\n", stderr);   // never runs
  }
}
```

Output with Clang 23 (same at `-O0` and `-O2`):

```text
~parse
libc++abi: terminating due to uncaught exception of type std::runtime_error: bad input
```

The exit code is 134, i.e. `SIGABRT`. The `catch (...)` in `main` never gets a chance to catch the exception; the local object in `parse` was destroyed, those in `handle` and `main` were not. The standard permits this partial unwinding: when an exception passes out of a `noexcept` function, whether the stack is unwound, partially unwound or not unwound at all before `std::terminate` is called is implementation-defined ([[except.terminate#2]]). So you can't count on destructors outside a `noexcept` function to clean up; the reasons and implementation details are in [[except.special]].

This also shows the correct use of `noexcept`: put it only on functions that truly can't fail, or on functions where failure should terminate the program. Marking a function that calls `push_back` internally as `noexcept` amounts to deciding to terminate when memory runs out.

## Destructors should not throw

A destructor without an exception specification is non-throwing by default ([[except.spec#8]]), and a `throw` inside it leads straight to `std::terminate`. Writing `noexcept(false)` explicitly lets the exception propagate, but throwing from a destructor during stack unwinding still terminates the program ([[except.terminate#1.4]]):

```cpp run title="throwing-dtor.cpp" ok
#include <cstdio>
#include <stdexcept>

struct Implicit {
  ~Implicit() { throw std::runtime_error("from ~Implicit"); }   // implicitly noexcept
};
struct Explicit {
  ~Explicit() noexcept(false) { throw std::runtime_error("from ~Explicit"); }
};

int main(int argc, char**) {
  try {
    if (argc == 1) { Implicit a; }                 // case 1
    if (argc == 2) { Explicit b; }                 // case 2
    if (argc == 3) { Explicit c; throw 42; }       // case 3: c destroyed during unwinding
  } catch (const std::exception& e) {
    std::fprintf(stderr, "caught: %s\n", e.what());
  }
}
```

Clang 23 gives a `-Wexceptions` warning for `~Implicit` ("has a non-throwing exception specification but can still throw"). The results of the three cases:

| Case | Output | Reason |
|---|---|---|
| 1: implicitly `noexcept` destructor throws | `terminating due to uncaught exception of type std::runtime_error: from ~Implicit` | An exception leaves a non-throwing function ([[except.handle#7]]) |
| 2: `noexcept(false)`, leaving scope normally | `caught: from ~Explicit` | The exception propagates as usual |
| 3: `noexcept(false)`, throwing during unwinding | `terminating due to uncaught exception of type int` | A destructor exits via an exception during unwinding ([[except.terminate#1.4]]) |

In case 3 there are two exceptions to propagate at once, and the language can't choose which to drop, so it terminates. Even if a destructor is allowed to throw, it always has to consider that it might be running during unwinding. Add to that the UB of a destructor called by the standard library throwing ([[res.on.functions#2.4]]), and, as noted earlier, the fact that a member's `noexcept(false)` destructor makes the enclosing class's move constructor potentially-throwing as far as the trait is concerned, and there is only one conclusion: destructors shouldn't throw.

When an operation in a destructor really can fail, such as flushing a buffer while closing a file, the usual approach is to provide an explicit `close()` that lets the caller handle the error, and have the destructor do only a fallback that can't fail, logging or ignoring any failure. When a destructor body throws, members and bases are still destroyed as usual and nothing leaks ([[except.ctor#3]]), but that doesn't change the conclusion above.

## RAII and scope guards

RAII ties cleanup to an object's destruction, so cleanup happens on both the normal path and the exceptional path. `std::unique_ptr`, `std::lock_guard` and `std::fstream` are all RAII classes. When no ready-made RAII class exists, you can use a **scope guard**: it records a function object at construction and calls it at destruction.

Some cleanup should only happen on failure, such as undoing a previous step that completed. To tell normal exit from exit by unwinding, use `std::uncaught_exceptions()`: it returns the number of exceptions in the current thread that have been thrown but not yet caught by a handler ([[uncaught.exceptions#1]], {{c++17}}).

```cpp run title="scope-fail.cpp" ok
#include <cstdio>
#include <exception>
#include <set>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

template<class F>
class ScopeFail {                  // runs f only if the scope is exited via an exception
  F f_;
  int entry_ = std::uncaught_exceptions();
public:
  explicit ScopeFail(F f) : f_(std::move(f)) {}
  ScopeFail(const ScopeFail&) = delete;
  ScopeFail& operator=(const ScopeFail&) = delete;
  ~ScopeFail() { if (std::uncaught_exceptions() > entry_) f_(); }
};

std::vector<std::string> names;
std::set<int> ids;

void add_user(const std::string& name, int id) {
  names.push_back(name);                         // step 1
  ScopeFail undo{[] { names.pop_back(); }};      // undo step 1 if step 2 fails
  if (!ids.insert(id).second)                    // step 2
    throw std::invalid_argument("duplicate id");
}

int main() {
  add_user("ada", 1);
  try { add_user("bob", 1); } catch (const std::exception& e) { std::puts(e.what()); }
  std::printf("%zu names, %zu ids\n", names.size(), ids.size());
}
```

The output is `duplicate id` and `1 names, 1 ids`. `add_user` therefore has the strong guarantee: a failed `push_back` does nothing ([[container.reqmts#66]]); if `insert` fails or throws, `undo` runs, and `pop_back` doesn't throw. This is exactly the pattern described earlier: every step can fail, but the operation that undoes each step can't.

`ScopeFail` compares the count at construction with the count at destruction, rather than checking whether the count is greater than 0. When a `ScopeFail` is used inside another destructor (during unwinding), the count is 1 from the start, and checking only for greater than 0 would misjudge it as a failure; see the example in [[support.exception]]. Before C++17 there was only `std::uncaught_exception()`, returning `bool`, which had exactly this flaw; it was removed in C++20 ([[N4152]]).

The standard library has no general-purpose scope guard. Version 3 of the Library Fundamentals TS provides `std::experimental::scope_exit`, `scope_fail` and `scope_success`; libc++ in our tests doesn't implement them.

## Exceptions, error codes and `expected`

Exceptions suit errors that are unlikely and need to cross several levels of calls to be handled, such as running out of memory or a corrupted configuration file. Failures the caller expects to encounter often, such as parsing user input, are better put in the return value: `std::expected<T, E>` holds either a result or an error ([[expected]], {{c++23}}); `std::error_code` suits interfacing with operating system error codes ([[syserr]]).

The two approaches aren't mutually exclusive. Even if a function reports business errors through `expected`, the `std::string` and `std::vector` inside it can still throw `bad_alloc`, and the analysis on this page still applies.

The run-time cost of exceptions is concentrated at the moment of the throw: with the table-driven implementation of the Itanium ABI, there are no extra instructions on the non-throwing path, while a throw needs table lookups and two passes over the stack, orders of magnitude slower than an ordinary return. `noexcept` lets callers omit the landing-pad code used for cleanup. Measurements and assembly are in [[toolchain/exception-implementation]].

## Questions

!!! question "1"
    The `operator=` in `copy-and-swap.cpp` is marked `noexcept`, yet `a = b` clearly allocates memory and may throw `bad_alloc`. Does this break the `noexcept` promise?

<details markdown="1">
<summary>Answer</summary>

No. The parameter `o` is initialized in the caller, as part of the call expression `a = b`, not inside the body of `operator=` ([[expr.call]]). When the copy constructor throws, the exception propagates out of the caller's expression and never enters `operator=`, so it never leaves a `noexcept` function.

This is also why `is_nothrow_copy_assignable_v<Buffer>` is `false` and `is_nothrow_move_assignable_v<Buffer>` is `true`: the noexcept operator looks at the whole expression, which for copying includes the potentially-throwing copy constructor, and for moving only the `noexcept` move constructor.
</details>

!!! question "2"
    A class's move constructor is marked `noexcept` and its destructor `noexcept(false)`. When `std::vector` grows, does it move or copy the elements?

<details markdown="1">
<summary>Answer</summary>

On libc++ in our tests it copies. `vector` chooses based on `is_nothrow_move_constructible_v<T>`, and the expression this trait checks includes the destruction of a temporary; the destructor is potentially-throwing, so the result is `false` ([[LWG2116]]). Triggering one growth on a 4-element `vector` measured 4 copies and 0 moves. One more reason destructors shouldn't throw.
</details>

!!! question "3"
    If the two steps in `scope-fail.cpp` are reversed, `ids.insert` first and then `names.push_back`, does `add_user` still need `ScopeFail`?

<details markdown="1">
<summary>Answer</summary>

Yes; only what gets undone changes. When `push_back` fails (allocation failure), the successful `insert` has to be undone, so the guard must be set up after `insert` succeeds, with `ids.erase(id)` as its action. An associative container's `erase(k)` throws only if the comparison object throws ([[associative.reqmts.except#1]]), and `std::less<int>` doesn't throw, so the undo operation still can't fail. The general rule: the last step needs no undo, and every step before it needs a non-throwing undo operation.
</details>

## Summary

| Question | Conclusion | Source |
|---|---|---|
| What is destroyed when an exception propagates | Fully constructed automatic objects, in reverse order | [[except.ctor#2]] |
| A constructor throws | The object's own destructor doesn't run; constructed subobjects are destroyed | [[except.ctor#3]] |
| A constructor's function-try-block | Can only log or translate the exception; rethrows automatically at the end | [[except.handle#14]] |
| How the standard library says strong guarantee | "no effects" | [[container.reqmts#66]], [[vector.modifiers#2]] |
| `push_back` growth | Moves only if the move constructor doesn't throw, otherwise copies | [[vector.modifiers#2]], [[forward]] |
| Default exception specifications | Ordinary functions potentially-throwing; destructors non-throwing; defaulted functions deduced from members | [[except.spec#4]], [[except.spec#7]], [[except.spec#8]] |
| An exception leaves a `noexcept` function | `std::terminate`; the extent of unwinding is implementation-defined | [[except.handle#7]], [[except.terminate#2]] |
| A destructor throws during unwinding | `std::terminate` | [[except.terminate#1.4]] |
| Telling normal exit from unwinding | Compare `uncaught_exceptions()` at construction and destruction | [[uncaught.exceptions]] |
