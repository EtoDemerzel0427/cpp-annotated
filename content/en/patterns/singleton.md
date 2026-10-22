---
title: Singletons and static initialization order
summary: Why the initialization and destruction order of global objects across translation units is unreliable; which part of the problem the Meyers singleton, constinit, never-destroyed singletons, nifty counters and inline variables each solve; the cost of the guard check; multiple copies of a singleton in shared libraries; and replacing singletons with dependency injection.
tags: singleton, static initialization, SIOF, constinit, inline variables, shared libraries, dependency injection, pattern
updated: 2026-10-19
---

!!! tldr
    - There is no guaranteed order of dynamic initialization between global objects in different translation units. If a global object's constructor reads a global object from another translation unit, the result can change with the link order.
    - Variables whose initial values can be computed at compile time get constant initialization and don't take part in this ordering; `constinit` makes the compiler check this.
    - The Meyers singleton (a `static` local object in a function) defers initialization to the first call and is thread-safe since C++11. The cost is a guard variable check on every call, and that acquire load prevents the compiler from hoisting accesses out of loops.
    - Destruction happens in reverse order of the completion of construction, so a singleton constructed later is destroyed earlier, and accessing it afterwards is UB. Singletons needed during the exit phase are usually made never-destroyed.
    - Singletons are hard to test and may exist in multiple copies across shared libraries. In most cases, passing the dependency in as a parameter (dependency injection) is better than a singleton.

## A program that depends on link order

```cpp title="config.cpp"
#include <map>
#include <string>
std::map<std::string, int> config = {   // dynamic initialization: nodes must be allocated
  {"port", 8080}, {"threads", 4},
};
int get(const std::string& key) {
  auto it = config.find(key);
  return it == config.end() ? -1 : it->second;
}
```

```cpp title="server.cpp" ub
#include <cstdio>
#include <string>
int get(const std::string& key);
struct Server {
  int port;
  Server() : port(get("port")) {}       // reads a global object from another TU
} server;
int main() { std::printf("port = %d\n", server.port); }
```

With Clang 23 and libc++, `clang++ config.cpp server.cpp` prints `port = 8080`, and `clang++ server.cpp config.cpp` prints `port = -1`, the same at `-O0` and `-O2`. The source of the two programs is identical; the only difference is the order of the files on the command line.

In the second order, `server` is constructed first, and the `get` it calls looks things up in a `map` that hasn't been constructed yet. At that point the `map` is just zero-initialized memory, and calling a member function on it is UB. We happened to get `-1`; a different standard library might simply crash.

This problem is called the **static initialization order fiasco** ([[g:static-initialization-order-fiasco|static initialization order fiasco]], SIOF). ASan doesn't report it by default; running the second order with `ASAN_OPTIONS=check_initialization_order=1` reports `initialization-order-fiasco`, and with `strict_init_order=1` added, the first order is reported too, because it is only correct by accident.

Most of the discussion of the singleton pattern in C++ revolves around how to make a globally unique object already constructed when it is used and not yet destroyed while it is being used.

## Static and dynamic initialization

Variables with static storage duration (globals, namespace-scope variables, static data members of classes, `static` variables in functions) are initialized in two ways ([[basic.start.static#2]]):

- **Static initialization**: if the variable is constant-initialized, i.e. its initializer is a constant expression ([[expr.const.init]]), **constant initialization** is performed; otherwise it is zero-initialized first. This happens before the program starts running; implementations usually write the initial value straight into the executable's data section.
- **Dynamic initialization**: all other initialization, which requires running code at run time, such as calling a non-`constexpr` constructor.

All static initialization happens before any dynamic initialization ([[basic.start.static#2]]). So constant-initialized variables have no ordering problem: any constructor reading them at any time reads the final value.

The order of dynamic initialization is specified by [[basic.start.dynamic#3]]; details are in [[basic.start]]. In terms of code, three points:

- Ordinary global variables in the same translation unit are initialized in order of definition;
- Ordinary global variables in different translation units are initialized indeterminately sequenced, i.e. definitely one before the other, but the standard doesn't say which;
- Static data members of templates (implicitly or explicitly instantiated specializations) have unordered initialization, with no ordering guarantee relative to any variable ([[basic.start.dynamic#1]]).

`config` and `server` in the example fall under the second point. The implementation in our tests runs each translation unit's initialization functions in the order of the object files at link time, so the result follows the command line.

### Turning the problem into a compile error with constinit

If a global object can be constructed at compile time, it needs no ordering. `constinit` (C++20, [[P1143R2]]) declares that a variable must be constant-initialized, otherwise the program is ill-formed ([[dcl.constinit#2]]):

<div class="compare" markdown="1">

```cpp ok
#include <array>
#include <string_view>
struct Entry {
  std::string_view key;
  int value;
};
constinit std::array<Entry, 2> config = {{
  {"port", 8080}, {"threads", 4},
}};
```

```cpp error
#include <map>
#include <string_view>
constinit std::map<std::string_view, int>
  config = {{"port", 8080}};
// error: not constant initialization;
// map nodes are allocated on the heap
```

</div>

For the right side Clang 23 reports `variable does not have a constant initializer`, with a note that a pointer to a heap-allocated object is not a constant expression. The `config` on the left already has its final value before the program starts, and constructors in any translation unit can safely read it.

`constinit` doesn't change how initialization happens; it only requires a check. A variable without `constinit` whose initialization happens to be a constant expression is constant-initialized all the same; writing it guards against some later change silently making the initialization dynamic. Nor does it imply `const` as `constexpr` does; the variable can still be modified.

[[basic.start.static#3]] also allows implementations to turn certain dynamic initializations into static ones ahead of time, as long as the result is the same. This is an optimization license; programs cannot rely on it.

## The Meyers singleton

A global object is initialized at program startup; a `static` object in a function is initialized the first time control passes through its declaration ([[stmt.dcl#3]]). Replacing the global object with a function that returns a reference to a local `static` object hands the initialization order problem over to call order:

```cpp run title="classic.cpp" ok
#include <cstdio>
#include <string>
#include <string_view>

class Logger {
public:
  static Logger& instance() {
    static Logger l;               // constructed on first call, thread-safe
    return l;
  }
  Logger(const Logger&) = delete;
  Logger& operator=(const Logger&) = delete;

  void log(std::string_view msg) {
    std::printf("%s%.*s\n", prefix_.c_str(), int(msg.size()), msg.data());
  }
private:
  Logger() : prefix_("[app] ") {}  // outsiders can't construct a second one
  ~Logger() = default;             // outsiders can't delete it
  std::string prefix_;
};

int main() {
  Logger::instance().log("started");
}
```

This technique is usually called the **Meyers singleton**. Rewrite the opening `config.cpp` the same way, with a `static` `map` inside `std::map<std::string, int>& config()`, and both link orders print `port = 8080`; ASan with `strict_init_order=1` no longer reports anything. The first time `server`'s constructor calls `config()`, the `map` is constructed on the spot.

The rules it relies on:

- [[stmt.dcl#3]]: dynamic initialization of a local `static` variable is performed the first time control passes through its declaration. If initialization exits via an exception, it is not complete, and the next call retries.
- Same paragraph: if another thread enters the declaration while initialization is in progress, it must wait for initialization to complete. This guarantee was added in C++11 ([[N2660]]). C++98 had no threads or memory model, and the double-checked locking commonly used then could not be written correctly in a portable way; see [[history/threads-and-memory-model]].
- Same paragraph: if the same thread re-enters the declaration recursively before initialization completes, the behavior is undefined. A singleton constructor that indirectly calls `instance()` falls into this; see [[stmt.dcl]].
- [[dcl.inline#2]] note 1: an inline function defined in multiple translation units is still one entity, and so is the `static` variable inside it. So with `instance()` written in the class definition (implicitly inline) and put in a header, the whole program still has only one `Logger`. Shared libraries break this; see below.

The private constructor and destructor prevent outsiders from constructing a second instance or deleting the instance by mistake. `l` is defined inside a member function, and access is checked in the context of the member function, so the private destructor doesn't prevent `l` from being destroyed at program exit.

### The cost of the guard variable

`Logger`'s constructor is not `constexpr`, so `l` needs dynamic initialization, and the compiler must record whether it has been initialized. The Itanium C++ ABI (used by GCC and Clang on Linux and macOS) allocates an 8-byte **guard variable** for such a variable. Below is the code Clang 23 `-O2 --target=x86_64-linux-gnu` generates for such a function, with exception tables and directives removed:

```cpp
struct Logger { Logger(); int level; };   // constructor defined elsewhere
Logger& meyers() { static Logger l; return l; }
```

```text
_Z6meyersv:
        pushq   %rbx
        movzbl  _ZGVZ6meyersvE1l(%rip), %eax   # load the guard's first byte
        testb   %al, %al
        je      .LBB0_1                        # 0: maybe not initialized yet
.LBB0_4:
        leaq    _ZZ6meyersvE1l(%rip), %rax     # fast path: return the address
        popq    %rbx
        retq
.LBB0_1:
        leaq    _ZGVZ6meyersvE1l(%rip), %rdi
        callq   __cxa_guard_acquire@PLT        # lock, then check again
        testl   %eax, %eax
        je      .LBB0_4                        # another thread finished initializing
        leaq    _ZZ6meyersvE1l(%rip), %rdi
        callq   _ZN6LoggerC1Ev@PLT             # construct
        leaq    _ZGVZ6meyersvE1l(%rip), %rdi
        callq   __cxa_guard_release@PLT        # mark done, wake up waiters
        jmp     .LBB0_4
```

Once initialization is done, every call takes only the fast path: load a byte, compare, branch. If the constructor throws, the landing pad calls `__cxa_guard_abort` to unlock, and the next call retries. `Logger`'s destructor is trivial, so there is no `__cxa_atexit` here; with a non-trivial destructor, a destructor registration also appears around `__cxa_guard_release`. A step-by-step explanation is in the implementation section of [[stmt.dcl]].

The load on the fast path is an acquire load: a thread that sees the guard set must also see everything the constructor wrote. On x86-64 an ordinary `mov` already has acquire semantics, so no difference is visible; on arm64 in our tests this load is `ldaprb`, a byte load with acquire semantics.

If the local `static` object can be constant-initialized, the guard disappears entirely. Change the type to `struct Counter { int n = 0; };`, whose default constructor is implicitly `constexpr`, and the same function compiles to two instructions:

```text
_Z14constant_localv:
        leaq    _ZZ14constant_localvE1c(%rip), %rax
        retq
```

### Measured: call overhead and loop optimization

On Apple Silicon (arm64) with Clang 23 `-O2`, we measured two scenarios.

The first calls a non-inlined accessor on its own, returning `meyers().level` or the `level` of an ordinary global object, 10⁹ calls each. All three rounds gave 0.91–0.94 ns per call, with no distinguishable difference between the two. The guard's branch always goes the same way, the predictor predicts it perfectly, and its cost is drowned out by the function call itself.

The second uses the singleton inside a loop:

```cpp
void scale_meyers(const int* in, int* out, long n) {
  for (long i = 0; i < n; ++i) out[i] = in[i] * meyers().scale;
}
void scale_global(const int* in, int* out, long n) {
  for (long i = 0; i < n; ++i) out[i] = in[i] * global_config.scale;
}
void scale_hoisted(const int* in, int* out, long n) {
  const int k = meyers().scale;    // fetched once outside the loop
  for (long i = 0; i < n; ++i) out[i] = in[i] * k;
}
```

With 4096 `int`s repeated 200,000 times, three rounds measured about 0.36 ns, 0.048 ns and 0.048 ns per element. The Meyers version was about 7.5 times slower.

The assembly explains why. Each iteration of `scale_meyers`'s loop performs one `ldaprb` to load the guard and one conditional branch, then multiplies one element at a time with scalar code. Acquire loads cannot be merged or hoisted out of the loop, and behind the guard check hangs a slow path that may call `__cxa_guard_acquire`, so the compiler cannot vectorize the loop. The other two versions are both vectorized into `mul.4s` loops handling 16 elements per iteration.

So the guard itself is cheap; what is expensive is how it blocks optimization. When using a singleton in a hot loop, fetch the reference or the needed value outside the loop first.

## Destruction order and dead references

The Meyers singleton solves the construction order, and the destruction order problem follows. Objects with static storage duration are destroyed at `std::exit` (including returning from `main`), in reverse order of the completion of their construction ([[basic.start.term#4]]). A `static` object in a function completes construction only at the first call, so it is destroyed earlier than global objects constructed before it.

```cpp run title="dead-reference.cpp" ub
#include <cstdio>
#include <string>
struct Logger {
  std::string prefix = "[app] a prefix long enough to live on the heap: ";
  void log(const char* m) { std::printf("%s%s\n", prefix.c_str(), m); }
  ~Logger() { std::puts("~Logger"); }
};
Logger& logger() { static Logger l; return l; }

struct Session {
  Session() { std::puts("Session()"); }
  ~Session() { logger().log("session closed"); }   // uses the singleton on destruction
};
Session session;                     // construction completes before main

int main() { logger().log("hello"); } // l completes construction only here, after session
```

`l` completes construction after `session`, so it is destroyed before it. `session`'s destructor calls `logger()`, control passes through the definition of `l` again, and `l` has already been destroyed: this is UB ([[basic.start.term#5]]). The guard is still in the initialized state, so `logger()` doesn't reconstruct it; it just returns a reference to a destroyed object.

Run without sanitizers in our tests, the last line of output is `session closed` without the prefix: `prefix` has already been destroyed. Run with `-fsanitize=address`, it reports `heap-use-after-free`: the read happens in `Logger::log` called from `Session::~Session`, and the free in `Logger::~Logger`.

This kind of problem is called a **dead reference**: during the exit phase, one object's destructor uses another singleton that has already been destroyed. Singletons that may be used from anywhere, such as logging, memory pools and statistics counters, run into it most often.

### Three remedies

The first is to call `logger()` once in the dependent's constructor. Change `Session()` to `Session() { logger(); }`, and `l` completes construction before `session` and so is destroyed after it. ASan no longer reports anything in our tests, and `~Logger` is printed last. This approach requires every user to remember to do it, and only works for dependencies that are foreseeable in the constructor.

The second is to make the singleton never destroyed. At program exit the operating system reclaims memory and closes file descriptors, and many singleton destructors have nothing they must do anyway:

```cpp run title="no-destructor.cpp" ok
#include <cstdio>
#include <new>
#include <string>
#include <utility>

template<class T>
class NoDestructor {               // constructs a T but never destroys it
  alignas(T) unsigned char buf_[sizeof(T)];
public:
  template<class... Args>
  explicit NoDestructor(Args&&... args) {
    ::new (static_cast<void*>(buf_)) T(std::forward<Args>(args)...);
  }
  NoDestructor(const NoDestructor&) = delete;
  NoDestructor& operator=(const NoDestructor&) = delete;
  T& get() { return *std::launder(reinterpret_cast<T*>(buf_)); }
};                                 // trivial destructor: nothing registered with atexit

struct Logger {
  std::string prefix = "[app] a prefix long enough to live on the heap: ";
  void log(const char* m) { std::printf("%s%s\n", prefix.c_str(), m); }
  ~Logger() { std::puts("~Logger"); }   // never runs
};

Logger& leaky() {                  // approach 1: heap-allocated, deliberately never freed
  static Logger* p = new Logger;
  return *p;
}
Logger& no_dtor() {                // approach 2: constructed in static storage, never destroyed
  static NoDestructor<Logger> l;
  return l.get();
}

struct Session {
  ~Session() {
    leaky().log("session closed (leaky)");
    no_dtor().log("session closed (no_dtor)");
  }
} session;

int main() {
  leaky().log("hello");
  no_dtor().log("hello");
}
```

Both approaches work in `session`'s destructor, ASan + UBSan report no errors, and `~Logger` is never printed. LeakSanitizer (`detect_leaks=1`) doesn't report the `new` in `leaky()` either, because the object is still reachable through the static variable `p` at exit. In the `-O2` assembly the whole program has only one `__cxa_atexit`, registered for `session`.

The `NoDestructor` version allocates no heap memory; the object lives in static storage. It corresponds to the utility of the same name in codebases such as Chromium and Abseil. The standard library treats the standard streams the same way: `std::cout` and the other seven objects are not destroyed during program execution ([[iostream.objects.overview#3]]), so the destructor of any static object can log to `std::cerr`.

The cost of never destroying is that the work in the destructor doesn't happen. If `Logger` has a buffer that must be flushed before exit, that needs separate arrangements, such as registering an `atexit` function that only flushes, or having `main` call it explicitly.

The third is to give the depended-on object **constant destruction** ([[g:constant-destruction|constant destruction]]), meaning its destruction could be done in constant evaluation; the typical case is a type with a trivial destructor. Such static objects are destroyed after all other static objects and `atexit` callbacks ([[basic.start.term#3]]). A `constinit` `std::atomic<long>` counter can be safely read and written in any destructor.

## Nifty counters and ios_base::Init

Before the Meyers singleton, iostreams used another technique to guarantee that `std::cout` is usable before any user global object is constructed and remains valid until after they are destroyed. This technique is called the **nifty counter**, also known as the Schwarz counter.

```cpp
// stream.h
struct Stream { /* ... */ };
Stream& stream();                       // the object lives in a buffer in stream.cpp
static struct StreamInitializer {       // one per TU that includes stream.h
  StreamInitializer();                  // constructs Stream when the counter goes 0→1
  ~StreamInitializer();                 // destroys Stream when the counter goes 1→0
} stream_initializer;
```

Every translation unit including stream.h has a `stream_initializer`, whose definition appears before the global objects defined after the `#include` in that translation unit, so by [[basic.start.dynamic#3]] it is initialized first. The counter is a zero-initialized `int`, already 0 before any dynamic initialization, so whichever translation unit's initializer runs first can tell that it is the first. Destruction proceeds symmetrically, and `Stream` is destroyed only when the last initializer is destroyed. Complete runnable code and a step-by-step explanation are in [[basic.start]].

The standard writes this mechanism into the specification of `<iostream>`: including `<iostream>` behaves as if it defines an `ios_base::Init` object with static storage duration ([[iostream.objects.overview#5]]). `Init`'s constructor constructs the eight standard stream objects if they haven't been constructed yet ([[ios.init]]). "As if" specifies only the effect, and implementations may achieve it differently; libc++'s approach in our tests is described in [[iostream.objects]].

New code today rarely needs a nifty counter: the Meyers singleton or inline variables are simpler. Its value is in illustrating an idea: use a helper object placed first to control when the real object is constructed.

## Inline static data members: the simplest global

Many so-called singletons are just a global variable plus access control. C++17 inline variables ([[P0386R2]]) let a static data member be defined directly in the class definition ([[class.static.data#4]]), with no separate definition line needed in some .cpp file:

```cpp ok
#include <atomic>
struct Stats {
  inline static constinit std::atomic<long> requests{0};
};
void on_request() { Stats::requests.fetch_add(1, std::memory_order_relaxed); }
long count() { return Stats::requests.load(std::memory_order_relaxed); }
```

`requests` is constant-initialized, so there is no ordering problem; accessing it involves no guard either: at `-O2` in our tests, `on_request` takes the address and executes a single `ldadd` atomic add, with no checks. It is an inline variable, so it can live in a header included by any number of translation units, and the whole program has just one.

Inline variables that need dynamic initialization are also somewhat better than ordinary globals. [[basic.start.dynamic#1]] says non-template inline variables have **partially-ordered** initialization. By [[basic.start.dynamic#3]], if every definition of W is preceded by some definition of V, the partially-ordered V is initialized before W. An inline variable defined in a header appears, in every translation unit including that header, before the global variables that follow the header:

```cpp title="config.h"
#include <map>
#include <string>
struct Config {
  inline static std::map<std::string, int> values = {   // dynamic initialization
    {"port", 8080}, {"threads", 4},
  };
  static int get(const std::string& key) {
    auto it = values.find(key);
    return it == values.end() ? -1 : it->second;
  }
};
```

```cpp title="b.cpp" ok
#include <cstdio>
#include "config.h"
extern int threads;                    // defined in a.cpp, which also includes config.h
int port = Config::get("port");        // comes after Config::values in this TU
int main() { std::printf("port = %d, threads = %d\n", port, threads); }
```

Another file, a.cpp, includes the same header and defines `int threads = Config::get("threads");`. Both link orders print `port = 8080, threads = 4` in our tests, and ASan with `strict_init_order=1` reports nothing. Compared with the opening `config.cpp`, the only difference is that the `map`'s definition moved from a .cpp file into a header that its users include.

This guarantee covers only translation units that include the definition. If a translation unit doesn't include config.h and reads `values` only indirectly by calling a function in another .cpp, the global variables in that translation unit get no guarantee. Static data members of class templates aren't covered either; their initialization is unordered.

## Singletons across shared libraries

The standard describes one program and has no notion of shared libraries. [[dcl.inline#2]] says there is only one `static` variable in an inline function, assuming the whole program is linked as a unit; dynamic libraries are linked separately and loaded at run time, and an entity may have one copy in each library.

Here is an experiment on macOS in our tests. A header has an inline Meyers singleton `registry()` and an inline variable `instances`; two dynamic libraries, liba and libb, each have a function that adds an entry to `registry()` and increments `instances`; the main program calls these two functions in turn and then reads `registry()` and `instances`:

| Build | What the main program sees | Copies of the singleton |
|---|---|---|
| Default visibility | 2 entries, `instances = 2` | 1 |
| Both libraries with `-fvisibility=hidden` | 0 entries, `instances = 0` | 3 (main program, liba and libb each have one) |
| A non-inline `registry()` in a static library linked into both libraries | 1 entry | 2 |

With default visibility, `nm -m` shows the guard, the object and `instances` as `weak external` symbols, and dyld coalesces same-named weak definitions across images at load time into one, so there is a single copy. `-fvisibility=hidden` makes them private symbols of each library, each library uses its own, and nobody ever writes to the main program's copy. In the third case, each library statically links its own definition of `registry()`, and macOS's two-level namespace makes each library call its own; the main program binds to the first library it found at link time.

Linux (ELF) has different rules: symbols with default visibility can be interposed by same-named symbols in the executable or earlier-loaded libraries; see [[toolchain/linking-and-symbols]]. This page did not test Linux; the actual results depend on visibility, linker options like `-Bsymbolic` and `dlopen` flags.

Some advice that holds on every platform:

- Define a singleton in only one shared library, as a non-inline exported function, and have other libraries obtain it through that library's interface;
- Don't link the same static library containing a singleton into multiple shared libraries;
- Inline singletons and inline variables in headers can be shared across libraries only when the relevant symbols are confirmed to have default visibility, and `-fvisibility=hidden` is exactly the default in many projects.

Registry-style singletons are the most affected: a plugin's self-registering objects register themselves in the plugin's private copy of the registry, and the main program sees an empty table. This pattern is covered in [[patterns/factory-and-registration]].

## Testing and dependency injection

The most common criticism of singletons is that they are hard to test.

<div class="compare" markdown="1">

```cpp
class SystemClock {
public:
  static SystemClock& instance();
  std::int64_t now_ms() const;
};
bool expired(std::int64_t expiry_ms) {
  return SystemClock::instance().now_ms()
         > expiry_ms;  // tests can't control time
}
```

```cpp
struct Clock {
  virtual std::int64_t now_ms() const = 0;
protected:
  ~Clock() = default;
};
class TokenChecker {
  const Clock& clock_;   // injected by the caller
public:
  explicit TokenChecker(const Clock& c)
    : clock_(c) {}
  bool expired(std::int64_t e) const {
    return clock_.now_ms() > e;
  }
};
```

</div>

The `expired` on the left doesn't reveal in its signature that it depends on a clock, and tests can only wait for real time to pass. Singleton state also leaks between test cases: configuration written by one case affects the next, and tests running in parallel share the same instance.

The right side passes the dependency in as a constructor parameter, which is called **dependency injection**. Tests pass in a fake clock:

```cpp run title="di.cpp" ok
#include <cassert>
#include <chrono>
#include <cstdint>

struct Clock {
  virtual std::int64_t now_ms() const = 0;
protected:
  ~Clock() = default;
};

struct SystemClock final : Clock {
  std::int64_t now_ms() const override {
    using namespace std::chrono;
    return duration_cast<milliseconds>(
        system_clock::now().time_since_epoch()).count();
  }
};

class TokenChecker {
  const Clock& clock_;
public:
  explicit TokenChecker(const Clock& c) : clock_(c) {}
  bool expired(std::int64_t expiry_ms) const {
    return clock_.now_ms() > expiry_ms;
  }
};

struct FakeClock final : Clock {
  std::int64_t t = 0;
  std::int64_t now_ms() const override { return t; }
};

int main() {
  FakeClock clock;
  TokenChecker checker(clock);
  clock.t = 1000;
  assert(!checker.expired(1500));
  clock.t = 2000;                      // time is controlled by the test
  assert(checker.expired(1500));

  static SystemClock system_clock;     // production code: create just one at the composition point
  TokenChecker real(system_clock);
  return real.expired(0) ? 0 : 1;
}
```

Having only one instance hasn't gone away; it has turned from a constraint of the class into a decision made where the program is assembled (usually `main`). `TokenChecker` doesn't care how many clocks there are, or when they are constructed and destroyed; object lifetimes are determined by the scope at the composition point, and the ordering problems of the exit phase disappear with them.

`Clock`'s destructor is protected and non-virtual: `TokenChecker` only borrows the clock and never deletes it through a `Clock*`, so no virtual destructor is needed. A reference is injected, so the caller must ensure the clock outlives the `TokenChecker`; lifetime problems of this kind are covered in [[topics/dangling-references]].

Virtual calls cost an indirect jump. When the dependency is fixed at compile time, it can be injected as a template parameter instead; `TokenChecker<FakeClock>` and `TokenChecker<SystemClock>` each generate their own code, and calls can be inlined; see [[patterns/policy-based-design]].

There is also a compromise that keeps a global access point but lets tests replace the instance, e.g. `Clock& clock()` returning the object pointed to by a pointer that `set_clock(Clock*)` can overwrite. This is usually called a service locator. It requires the fewest changes, but the dependency is still hidden inside function bodies, tests must remember to restore it afterwards, and parallel tests still share it.

## How to choose

| Need | Approach |
|---|---|
| Global constants, or global state that can be constructed at compile time | a `constexpr` or `constinit` variable; `inline static constinit` inside a class |
| Dynamic initialization, and all users include the header where it is defined | inline variables (partially-ordered initialization) |
| Dynamic initialization, lazy construction, possibly used by other global objects' constructors | the Meyers singleton |
| Also possibly used by other static objects' destructors | a never-destroyed singleton (`NoDestructor` or a deliberate leak) |
| Accessed in a hot loop | fetch the reference outside the loop, or use a constant-initialized variable |
| Only one copy across shared libraries | a non-inline exported accessor defined in one library |
| Must be replaceable in tests, or the number and lifetime of instances should be up to the user | dependency injection, not a singleton |

An object is often unique only because the current program happens to need just one. Database connections, configuration and clocks all belong to this category, and will very likely need a second one some day (test doubles, multi-tenancy, multiple configuration sources). Only objects that truly must be unique, such as resources representing the process itself (the standard streams, a process-wide memory allocator), are suited to being singletons.

## Questions

!!! question "1"
    If the opening `config.cpp` replaced `std::map` with a class with a `constexpr` constructor, `Config { int port; constexpr Config() : port(8080) {} };`, without writing `constinit`, would the result of `server.cpp` still depend on link order?

<details markdown="1">
<summary>Answer</summary>

No. The initializer calls a `constexpr` constructor, the whole initialization is a constant expression, and the variable is constant-initialized ([[expr.const.init]]): static initialization, which completes before any dynamic initialization ([[basic.start.static#2]]). In the `-O2` assembly in our tests, `config` appears directly in the data section as `.long 8080`, with no initialization function at all.

`constinit` doesn't affect this conclusion; its role is to turn constant initialization from a fact into a check: if someone later adds a non-`constexpr` line to `Config`'s constructor, without `constinit` the program silently goes back to dynamic initialization, while with it compilation fails.
</details>

!!! question "2"
    In `dead-reference.cpp`, why is it no longer UB after changing `Session`'s constructor to `Session() { logger(); }`? If `session`'s constructor didn't call `logger()`, but `main` called it before constructing anything, would the conclusion be the same?

<details markdown="1">
<summary>Answer</summary>

Destruction order is determined by when construction completes ([[basic.start.term#4]]). With `logger()` called in `Session()`, `l` completes construction during the execution of `Session`'s constructor, before `session`'s construction completes, so `l` is destroyed after `session`, and is still alive when `~Session` uses it. ASan reports nothing in our tests, and `~Logger` is printed last.

The second case is different. `session` is a global object whose construction completes before `main` starts, so the first call to `logger()` in `main` is necessarily later, and `l` is still destroyed first. What determines the order is the moment each object's construction completes, not which one is used first.
</details>

!!! question "3"
    In `scale_meyers`'s loop, `meyers()` has completed initialization in the first iteration. Why can't the compiler hoist the guard check out of the loop and check only once?

<details markdown="1">
<summary>Answer</summary>

The guard load is an acquire load, an atomic operation. Under the C++ memory model, another thread could complete initialization and publish the result at any moment, and the compiler cannot merge multiple acquire loads into one without changing the synchronization the program might observe. Moreover, the slow path calls the external functions `__cxa_guard_acquire` and the constructor, and the compiler doesn't know whether they modify the memory `in` and `out` point to, so it cannot vectorize the loop either.

Fetching `meyers().scale` once by hand outside the loop moves the guard check out of the loop. In our tests this runs at the same speed as an ordinary global variable, about 0.048 ns per element.
</details>

## Summary

| Question | Conclusion | Source |
|---|---|---|
| Which global object in different TUs is initialized first? | indeterminately sequenced; the result may change with link order | [[basic.start.dynamic#3]] |
| Constant-initialized variables | precede all dynamic initialization, no ordering problem; `constinit` enforces the check | [[basic.start.static#2]], [[dcl.constinit#2]] |
| When is a local `static` object initialized? | the first time control passes its declaration; thread-safe, retried after an exception | [[stmt.dcl#3]] |
| A `static` in an inline function in a header | one per program, but shared libraries can break this | [[dcl.inline#2]] |
| Cost of the guard | one acquire load on the fast path; blocks hoisting out of loops and vectorization | measured in our tests |
| Destruction order of static objects | reverse order of completed construction; using a destroyed local `static` is UB | [[basic.start.term#4]], [[basic.start.term#5]] |
| Inline variables defined in headers | partially ordered, before variables defined after them in TUs that include them | [[basic.start.dynamic#1]], [[basic.start.dynamic#3]] |
| The standard streams of `<iostream>` | as if each TU had an `ios_base::Init`; never destroyed | [[iostream.objects.overview#3]], [[iostream.objects.overview#5]] |
