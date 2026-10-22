---
title: Start and termination
summary: "The forms of and restrictions on main; how global variables are initialized and in what order, the static initialization order problem and its remedies; exit, atexit and the order of destruction of static objects."
updated: 2026-10-19
---

!!! tldr
    - `main` must return `int` and cannot be called recursively, have its address taken, or be declared `inline`, `static` or `constexpr`; flowing off the end of `main` is equivalent to `return 0;`, and returning from `main` is equivalent to destroying local objects and then calling `std::exit`.
    - Global variables first undergo static initialization (constant initialization or zero-initialization), then dynamic initialization. Static initialization is complete before any code runs and has no ordering problem.
    - Global variables in the same translation unit are dynamically initialized in definition order; across translation units the order is indeterminate, which is the static initialization order problem. The remedies are `constinit`, function-local static variables and modules.
    - Static objects are destroyed in the reverse order of completion of construction, and functions registered with `atexit` take part in the same reverse order; objects with constant destruction are destroyed last.
    - Passing through an already destroyed local static variable during destruction is UB; threads still running after `main` returns that use the standard library are UB too.

Before the first statement of `main` and after it returns, the program is still executing code: constructing and destroying global objects, initializing `thread_local` variables, calling functions registered with `atexit`. This subclause specifies when and in what order these happen. Concepts used: objects with **static storage duration** exist for the whole run of the program, such as global variables and `static` local variables ([[basic.stc.static]]); objects with **thread storage duration** exist once per thread, i.e. `thread_local` variables ([[basic.stc.thread]]).

## The main function [basic.start.main]

### Valid forms (¶1–¶2)

```cpp run title="main-ok.cpp" ok
auto main(int argc, char** argv) noexcept -> int {
  return argv[argc] == nullptr ? 0 : 1;   // argv[argc] is guaranteed to be a null pointer
}
```

¶1 A program shall contain exactly one function called `main` that belongs to the global scope. Executing a program starts a main thread of execution in which `main` is invoked. Whether a freestanding implementation (one without operating system support, such as a kernel or firmware) requires `main` to be defined is implementation-defined {{impl}}.

¶2 The declared return type of `main` shall be `int`; otherwise its type is implementation-defined. An implementation shall allow two forms: `int()` and `int(int, char**)`, both possibly with `noexcept`. The trailing return type form above is also fine, since the declared return type is still `int`; but `auto main() { return 0; }` is ill-formed, and Clang reports "'main' must return 'int'".

In the second form, `argc` is the number of arguments passed from the environment and is non-negative. If `argc` is nonzero, `argv[0]` through `argv[argc-1]` point to null-terminated strings, with `argv[0]` being the name used to invoke the program or `""`; `argv[argc]` shall be a null pointer. The standard recommends adding any further parameters after `argv`, which is what the common extension `int main(int, char**, char** envp)` does.

### Restrictions on main (¶3)

¶3 lists a set of prohibitions; violating any of them makes the program ill-formed:

| Form | Why it is prohibited |
|---|---|
| using `main` in an expression (recursive calls, taking its address) | the implementation may insert startup code at the beginning of `main`; re-entering it makes no sense |
| defining `main` as deleted, or declaring it `inline`, `static`, `constexpr` or `consteval` | `main` must be a function that really exists and can be called by the environment |
| `main` being a coroutine | the environment cannot drive the suspension and resumption of a coroutine |
| `main` with a linkage specification other than `"C++"` | |
| a variable `main` at global scope, or a function template `main` at global scope | conflicts with the entry symbol |
| a global-scope function `main` attached to a named module | the module would change its linkage and symbol name |
| an entity named `main` with C language linkage in any namespace | its symbol name is `main` |

The linkage of `main` is implementation-defined {{impl}}. Otherwise the name `main` is not reserved: member functions, classes and functions in other namespaces can all be called `main`:

<div class="compare" markdown="1">

```cpp run ok
namespace N { int main() { return 1; } }
struct S { void main() {} };
int main() { return N::main() - 1; }
```

```cpp run error
inline int main() {}
// error: main cannot be inline
```

</div>

!!! impl "Clang only warns about two of these"
    For `int main() { return main(); }` and `extern "C" int main() {}`, Clang 23 gives only `-Wmain` warnings, the former saying "referring to 'main' within an expression is a Clang extension". An ill-formed program only requires at least one diagnostic, and a warning counts, so Clang conforms; it just accepts the program as an extension after diagnosing it ([[intro.compliance]]).

### Returning from main and calling exit (¶4–¶5)

```cpp run title="exit-vs-return.cpp" ok
#include <cstdio>
#include <cstdlib>
struct T { ~T() { std::puts("~T"); } };
int main(int argc, char**) {
  T t;
  if (argc > 5) std::exit(0);   // does not print "~T"
  return 0;                     // destroys t first, printing "~T", then calls exit(0)
}
```

¶5 A `return` statement in `main` first leaves `main`, which destroys local objects and {{c++26}} evaluates the postcondition assertions of `main` ([[basic.contract]]), and then calls `std::exit` with the return value as the argument. Control reaching the end of `main` is equivalent to `return 0;`, so `main` is the only non-void function for which flowing off the end is not UB (see [[stmt.return]]).

¶4 Terminating the program without leaving the current block, by means such as `std::exit`, does not destroy any objects with automatic storage duration (ordinary local variables); the `exit(0)` path in the example does not print `~T`. If `std::exit` is called during the destruction of an object with static or thread storage duration, the behavior is undefined {{ub}}, because `exit` would re-enter the destruction process already under way.

## Static initialization [basic.start.static]

### Zero-initialization and constant initialization (¶1–¶2)

```cpp run title="static-vs-dynamic.cpp" ok
#include <cstdlib>
int a = 42;                    // constant initialization
int b;                         // zero-initialization
constexpr double pi = 3.14159; // constant initialization
struct P { int x, y; };
P p = { 1, 2 };                // constant initialization
bool c = std::getenv("HOME");  // dynamic initialization; c was zero-initialized before this
int main() { return a - 42 + b + (p.x - 1) + (int(pi) - 3); }
```

¶1 Variables with static storage duration are initialized at program startup, and variables with thread storage duration when their thread starts executing.

¶2 If a variable with static or thread storage duration is **constant-initialized** (roughly, its initializer is a constant expression; the precise condition is in [[expr.const.init]]), **constant initialization** is performed; otherwise it is first **zero-initialized**, setting every byte to the zero value ([[dcl.init]]).

!!! std
    Together, zero-initialization and constant initialization are called static initialization; all other initialization is dynamic initialization. All static initialization strongly happens before any dynamic initialization.

Zero-initialization and constant initialization are collectively [[g:static-initialization|**static initialization**]]; all other initialization is **dynamic initialization**, i.e. initialization that executes code at run time. All static initialization completes before any dynamic initialization.

In practice, statically initialized values are written directly into the executable's `.data` section (constant initialization) or `.bss` section (zero-initialization), mapped into memory by the loader, without executing any code. So static initialization has no ordering problem. `c` in the example is already `false` before `getenv` is called.

### Implementations may perform dynamic initialization early (¶3)

¶3 An implementation may perform a dynamic initialization as a static initialization even when not required, provided the difference cannot be observed: the dynamic version would not change the value of any other static object before its initialization (¶3.1), and the static version produces the same value as if all initializations were done dynamically (¶3.2). This lets compilers compute initializers like `double d = 1.0 + 2.0;` or calls to inline functions at compile time.

Note 2 points out a consequence:

```cpp run title="note2.cpp" unspecified
#include <cstdio>
inline double fd() { return 1.0; }
extern double d1;
double d2 = d1;     // does it read 1.0 or 0.0?
double d1 = fd();
int main() { std::printf("%g %g\n", d1, d2); }
```

The initialization of `d2` reads `d1`, defined later in the same translation unit. If `d1` is done early as static initialization while `d2` is dynamically initialized, both are 1.0; otherwise `d2` is 0.0 (it saw only the zero-initialized `d1`). The standard doesn't say which. Clang 23 prints `1 0` at both `-O0` and `-O2`.

## Dynamic initialization of global variables [basic.start.dynamic]

### Three kinds of initialization (¶1)

¶1 Dynamic initialization of non-block variables with static storage duration (namespace-scope variables and static data members) falls into three kinds:

| Kind | Applies to | Why |
|---|---|---|
| **unordered** | instantiated specializations: static data members of class templates, specializations of variable templates | instantiations may appear in any number of translation units, so there is no place of definition to speak of |
| **partially-ordered** | `inline` variables that are not instantiated specializations | the definition appears in several translation units, but at a definite place in each |
| **ordered** | everything else: ordinary global variables, ordinary static data members | there is only one definition, at a definite place |

Note 1 adds that a non-inline explicit specialization of a templated variable has ordered initialization, because it is not instantiated and has only one definition.

```cpp run title="categories.cpp" ok
#include <cstdio>
struct Tr { Tr(const char* s) { std::puts(s); } };
inline Tr i1("inline i1");                     // partially-ordered
Tr o1("ordered o1");                           // ordered
template<class T> struct H { static Tr t; };
template<class T> Tr H<T>::t("template member");  // unordered
template struct H<int>;
Tr o2("ordered o2");                           // ordered: always after o1
int main() {}
```

`i1` is always before `o1`, and `o1` always before `o2` (the rules are in the next section), while the template member's position is not guaranteed. Clang 23 prints `i1`, the template member, `o1`, `o2`: the template member is written after `o1` but initialized before it.

### Order of initialization (¶2–¶3)

¶2 A declaration D is **appearance-ordered before** a declaration E if D and E are in the same translation unit and D appears before E, or if the translation unit containing E imports (directly or indirectly) the module unit containing D, with the import point before E. The second case comes with C++20 modules: variables defined in an imported module are treated as appearing before the import point.

¶3 For two non-block variables V and W with static storage duration, there are three cases:

- ¶3.1 V and W both have ordered initialization and the definition of V is appearance-ordered before that of W; or V has partially-ordered initialization, W does not have unordered initialization, and every definition of W is preceded by some definition of V. Then V is initialized before W. Only if there is just the main thread, or V and W both have ordered initialization and are in the same translation unit, is this "before" sequenced before (order within one thread); otherwise it is strongly happens before (an order that holds across threads too, see [[intro.races]]).
- ¶3.2 Otherwise, if the program starts other threads before V or W is initialized, it is unspecified in which threads they are initialized; if in the same thread, they are unsequenced.
- ¶3.3 Otherwise, their initializations are indeterminately sequenced: one definitely comes before the other, but which is unknown.

Note 2 explains that this definition allows a sequence of ordered variables to be initialized concurrently with another sequence. For everyday code, the conclusions are three:

- Ordinary global variables in the same translation unit are initialized in definition order.
- Ordinary global variables in different translation units, without module import relations, are initialized in an indeterminate order.
- Static data members of templates have no ordering guarantee with respect to any variable.

### The static initialization order problem

```cpp title="a.cpp"
#include <string>
std::string greeting = "hello, this is a long string beyond SSO";
```

```cpp title="b.cpp" ub
#include <cstdio>
#include <string>
extern std::string greeting;
std::size_t len = greeting.size();   // greeting may not be constructed yet
int main() { std::printf("%zu\n", len); }
```

`greeting` and `len` both have ordered initialization but are defined in different translation units with no appearance-order relation between them, so by ¶3.3 they are indeterminately sequenced. If b.cpp's initialization runs first, `greeting.size()` calls a member function on an object whose lifetime has not begun and which has only been zero-initialized, which is UB ([[basic.life]]). This problem is known as the **static initialization order fiasco** (SIOF).

Measured with Clang 23 and libc++: `clang++ a.cpp b.cpp` prints 39, `clang++ b.cpp a.cpp` prints 0; the initialization order follows the order of files on the command line.

Change the string to the short `"hello"` and both orders print 5. libc++'s `std::string` constructor is `constexpr`, and short strings are stored inside the object (SSO, the small string optimization) without allocating, so the whole initialization is a constant expression; `greeting` is then constant-initialized and doesn't take part in the ordering of dynamic initialization at all. This leads to the first remedy.

#### Remedy 1: constinit

C++20's `constinit` ([[dcl.constinit]], [[P1143R2]]) asserts that a variable is constant-initialized; otherwise the program is ill-formed. Unlike `constexpr` it does not imply `const`, and the variable can still be modified:

<div class="compare" markdown="1">

```cpp run ok
constinit int counter = 42;
constinit thread_local int tls = 0;
int main() { return counter - 42 + tls; }
```

```cpp run error
int f();
constinit int bad = f();
// error: not constant-initialized
```

</div>

This turns "this variable has no SIOF" from a convention into a compile-time check. Relying on libc++ happening to make short strings constant-initialized is not dependable; switch standard libraries or lengthen the string and the conclusion changes.

#### Remedy 2: function-local static variables

```cpp run title="meyers.cpp" ok
#include <string>
std::string& greeting() {
  static std::string s = "hello, this is a long string beyond SSO";
  return s;                          // s is initialized only on the first call
}
std::size_t len = greeting().size(); // safe whichever translation unit is initialized first
int main() { return len == 0; }
```

A block-scope static variable is initialized the first time control passes through its declaration ([[stmt.dcl#3]]). Since C++11 this initialization is thread-safe: threads entering concurrently wait for initialization to complete. The cost is a check on every access for whether it has been initialized, plus a symmetric problem at destruction, see [[basic.start.term#5]] below. This idiom is often called the Meyers singleton.

#### Remedy 3: the Schwarz counter

This is the traditional approach of iostreams, also called the nifty counter. A header defines a `static` initializer object, so every translation unit that includes the header has its own copy. Its constructor increments a counter and constructs the real global object when the counter goes from 0 to 1; its destructor decrements the counter and destroys the global object when it reaches 0.

```cpp run title="nifty.cpp" ok
#include <cstdio>
#include <new>
// ---- stream.h ----
struct Stream {
  Stream() { std::puts("[Stream ctor]"); }
  ~Stream() { std::puts("[Stream dtor]"); }
  void write(const char* s) { std::fputs(s, stdout); }
};
Stream& stream();
static struct StreamInitializer {      // one per translation unit
  StreamInitializer();
  ~StreamInitializer();
} stream_initializer;
// ---- stream.cpp ----
static int nifty_counter;              // zero-initialized, before all dynamic initialization
alignas(Stream) static unsigned char buf[sizeof(Stream)];
Stream& stream() { return *std::launder(reinterpret_cast<Stream*>(buf)); }
StreamInitializer::StreamInitializer() {
  if (nifty_counter++ == 0) ::new (buf) Stream();
}
StreamInitializer::~StreamInitializer() {
  if (--nifty_counter == 0) stream().~Stream();
}
// ---- user.cpp ----
struct User { User() { stream().write("using stream\n"); } } user;
int main() {}
```

It works because of two things. First, in every translation unit that includes stream.h, the definition of the initializer object comes before the users in that translation unit, so by ¶3.1 it is initialized first. Second, `nifty_counter` is zero-initialized and is 0 before any dynamic initialization begins, so whichever translation unit's initializer runs first can correctly tell whether it is the first.

The standard still specifies that including `<iostream>` behaves as if it defines an `ios_base::Init` object with static storage duration, and that objects such as `std::cout` are constructed before `main` begins and are not destroyed during program execution ([[iostream.objects.overview]]). Implementations may meet these requirements in other ways, such as specifying initialization priorities inside the runtime library.

#### Remedy 4: modules

Since C++20, if b.cpp `import`s the module defining `greeting`, then by ¶2.2 the definition of `greeting` is appearance-ordered before `len`, and by ¶3.1 it is initialized first.

### Deferred initialization (¶4–¶7)

¶5 Whether the dynamic initialization of a non-block, non-inline variable with static storage duration is done before the first statement of `main` or deferred is implementation-defined {{impl}}. If it is deferred, it must happen before the first non-initialization odr-use of any non-inline function or variable defined in the same translation unit.

¶4 An **odr-use** is, roughly, a use that requires the entity to have a definition ([[basic.def.odr]]). A **non-initialization odr-use** is an odr-use not caused directly or indirectly by the initialization of some global variable, i.e. a use in the program's normal run.

Deferral is allowed mainly for dynamically loaded libraries: the global objects of a shared library loaded with `dlopen` cannot possibly be constructed before `main`. In which thread and when a deferred initialization runs is implementation-defined; the standard recommends that implementations choose a point that allows programmers to avoid deadlocks. Footnote 32 adds that a variable whose initialization has side effects is initialized even if it is not itself odr-used.

¶6 The rule for inline variables is similar, but a deferred initialization need only happen before the non-initialization odr-use of that variable itself. An inline variable may be defined in several translation units, so "other entities in the same translation unit" makes no sense for it.

¶7 Whether the dynamic initialization of a non-block, non-inline variable with thread storage duration is done before the initial function of the thread begins or deferred is implementation-defined. If deferred, the initialization in a thread t must happen before t's first non-initialization odr-use of any non-inline `thread_local` variable with dynamic initialization in the same translation unit.

!!! impl "What mainstream implementations do"
    For ordinary global variables, GCC and Clang initialize before `main` (via `.init_array` on ELF), without deferral; the global objects of shared libraries are initialized when the library is loaded.

    `thread_local` variables needing dynamic initialization, on the other hand, are deferred. In the Itanium C++ ABI, every access goes through a TLS wrapper function (symbol prefix `_ZTW`), which checks whether this thread has been initialized and, if not, calls the TLS init function (prefix `_ZTH`) to initialize all dynamically initialized `thread_local` variables of that translation unit at once, matching exactly the per-translation-unit granularity of ¶7. A `thread_local` declared `constinit` can skip this check.

<details class="fine" markdown="1"><summary>The standard's example for ¶5</summary>

```cpp
// - File 1 -
#include "a.h"
#include "b.h"
B b;
A::A() { b.Use(); }

// - File 2 -
#include "a.h"
A a;

// - File 3 -
#include "a.h"
#include "b.h"
extern A a;
extern B b;
int main() { a.Use(); b.Use(); }
```

The example says it is implementation-defined whether `a` and `b` are initialized before `main` is entered or deferred until `a` is first odr-used in `main`. If `a` is initialized before `main`, it is not guaranteed that `b` is initialized when `A::A` calls `b.Use()`: that is the SIOF. If the initialization of `a` is deferred until after `main` begins, the example asserts that `b` will be initialized before `A::A` uses it.

This last assertion is hard to derive strictly from the normative wording: `A::A`'s use of `b` is caused indirectly by the initialization of `a`, so per ¶4 it is an initialization odr-use and does not trigger the guarantee of ¶5. The example's intent is probably that an implementation with deferred initialization works per translation unit, completing all of a translation unit's initialization before the first use of any of its entities. Since mainstream implementations do not defer initialization of ordinary global variables, this point is mainly theoretical. Examples are not normative.

</details>

### Initialization that throws (¶8)

```cpp run title="init-throw.cpp" ok
#include <stdexcept>
int init() { throw std::runtime_error("boom"); }
int x = init();          // the exception escapes the initialization: std::terminate is called
int main() {}
```

¶8 If the initialization of a non-block variable with static or thread storage duration exits via an exception, `std::terminate` is called ([[except.terminate]]). At this point `main` hasn't started, and no `try` can surround it. The behavior is defined, so the example is marked ok; in our tests it ends with an abort when run. Block-scope static variables are different: an exception thrown by their initialization propagates to the caller normally, and initialization is attempted again the next time the declaration is reached ([[stmt.dcl#3]]).

## Termination [basic.start.term]

### Who is destroyed when (¶1–¶3)

¶1 Destroying constructed complete objects with static storage duration and calling functions registered with `atexit` are part of a call to `std::exit`. Returning from `main` calls `std::exit` (note 1).

¶2 Objects with thread storage duration are destroyed when the thread's initial function returns, or when that thread calls `std::exit`. Their destruction precedes the destruction of any object with static storage duration, so the main thread's `thread_local` variables are destroyed before global variables.

¶3 Objects with **constant destruction**, i.e. whose destruction could be done in constant evaluation ([[expr.const.defns]]), typically objects with trivial destructors, are destroyed last: those with thread storage duration after the thread's other objects with thread storage duration, and those with static storage duration after all other static objects and all `atexit` callbacks. The remaining ordering rules of this subclause apply only to objects without constant destruction.

Destroying an object with constant destruction has no observable effect, and putting them last means the destructors of other objects can safely use them, for example reading a global `int` or `std::array<int, N>` in a destructor.

### Destruction is the reverse of construction (¶4)

¶4 If the **deemed construction** of a complete object X with static storage duration strongly happens before that of Y, then the destruction of Y completes before the destruction of X begins. Deemed construction refers to the moment an object's initialization completes; when the initialization is a full-expression, it is the moment that full-expression finishes evaluating ([[dcl.init.general#21]]).

The rule for objects with thread storage duration is the same, with the relation being sequenced before instead. Statically initialized objects are destroyed in the order they would have been if they had been dynamically initialized. If a destruction exits via an exception, `std::terminate` is called.

The reference point is the completion of initialization rather than its start, for a reason. Consider Example 1 in the standard:

```cpp run title="term-example.cpp" ok
#include <cstdio>
struct DTemp { ~DTemp() { std::puts("~DTemp"); } };
struct Temp {
  ~Temp() { static DTemp dt; }
};
struct BTemp {
  int i;
  BTemp(int i) : i(i) {}
  ~BTemp() { std::printf("~BTemp%d\n", i); }
};
struct A { const BTemp& tb; ~A() { std::printf("~A%d\n", tb.i); } };
A a[] = { (Temp(), BTemp(1)), BTemp(2) };
int main() {}
```

The whole declaration of `a` is one full-expression. Evaluating it creates the temporaries `Temp()`, `BTemp(1)` and `BTemp(2)` in turn; the two `BTemp`s bind to reference members and their lifetimes are extended to that of `a`. At the end of the full-expression `Temp()` is destroyed, and its destructor constructs the static local variable `dt`. Only after this, when the full-expression has finished evaluating, is `a` deemed constructed, so `dt` comes before `a`.

So at termination the elements of `a` are destroyed first, then `dt`, and finally the two `BTemp`s. Temporaries with extended lifetimes are destroyed in the reverse order of completion of their construction, and later than objects of the same storage duration created after them ([[class.temporary#11]]). Clang 23 prints `~A2`, `~A1`, `~DTemp`, `~BTemp2`, `~BTemp1`, consistent with the standard.

The consequence most used in everyday code: a function-local static object completes construction only on the first call, so it is destroyed before global objects that completed construction before it.

### Using a destroyed local static variable (¶5)

```cpp run title="dead-reference.cpp" ub
#include <cstdio>
#include <string>
struct Logger {
  std::string prefix = "log: a fairly long prefix to force heap allocation";
  void log(const char* m) { std::printf("%s%s\n", prefix.c_str(), m); }
};
Logger& logger() { static Logger l; return l; }
struct Client {
  ~Client() { logger().log("client destroyed"); }   // UB: l is already destroyed
};
Client c;                              // constructed before main
int main() { logger().log("main"); }   // l completes construction only here, after c
```

¶5 If a function is called during the destruction of an object with static or thread storage duration, and control flow passes through the definition of a previously destroyed static (or thread storage duration) local variable in that function, the behavior is undefined {{ub}}. Note 2 adds that using a destroyed local variable indirectly, through a pointer for example, is also UB.

In the example, the deemed construction of `l` is later than that of `c`, so `l` is destroyed first; then `c`'s destructor calls `logger()`, passing through the definition of `l`. Run with `-fsanitize=address` in our tests, it reports heap-use-after-free. This is the ordering problem of function-local static variables at destruction time. There are three common remedies:

- never destroy the singleton: `static Logger& l = *new Logger;`, leaking deliberately;
- call `logger()` once in `Client`'s constructor first, so that `l` completes construction before `c` and is therefore destroyed after `c`;
- give the depended-upon object constant destruction (¶3), so it goes last.

### atexit interleaved with destruction (¶6)

¶6 Functions registered with `atexit` and the destruction of static objects are placed in the same reverse order:

- if the deemed construction of an object happens before an `atexit` call, the registered function is called before the object's destruction begins;
- if an `atexit` call happens before the deemed construction of an object, the registered function is called after the object's destruction completes;
- of two `atexit` calls, the function registered later is called first.

You can think of an `atexit` registration as constructing an object, with everything then torn down uniformly in reverse order:

```cpp run title="term-order.cpp" ok
#include <cstdio>
#include <cstdlib>
struct T {
  const char* n;
  T(const char* s) : n(s) { std::printf("ctor %s\n", n); }
  ~T() { std::printf("dtor %s\n", n); }
};
T a("a");
void bye1() { std::puts("atexit 1"); }
void bye2() { std::puts("atexit 2"); }
int r1 = std::atexit(bye1);
T b("b");
int r2 = std::atexit(bye2);
T& local() { static T l("local"); return l; }
int main() {
  local();
  T autoobj("auto");
  std::exit(0);           // autoobj is not destroyed ([basic.start.main]/4)
}
```

```text
ctor a
ctor b
ctor local
ctor auto
dtor local
atexit 2
dtor b
atexit 1
dtor a
```

The order of construction and registration is a, bye1, b, bye2, local, and the teardown order is exactly the reverse; `auto` is never destroyed.

### Other threads during termination (¶7)

¶7 If a standard library object or function not permitted within signal handlers ([[support.signal]]) is used, and that use does not happen before the completion of the destruction of static objects and the `atexit` callbacks, the behavior is undefined {{ub}}. Very few library facilities are permitted in signal handlers, so this rule covers nearly all of them, including `std::cout`, `std::string` and the containers.

Note 3 adds: using an object with static storage duration where the use does not happen before its destruction is also UB. Terminating every thread before calling `std::exit` or returning from `main` is sufficient to meet these requirements.

The practical consequence: when `main` returns, if a `detach`ed thread is still running and using any standard library facility or global object, it is UB, because global objects may be in the middle of being torn down.

### abort and quick_exit (¶8)

¶8 `std::abort()` terminates the program without executing any destructors and without calling functions registered with `atexit` or `at_quick_exit`. Together with [[support.start.term]], the ways of ending a program compare as follows:

| Way | Automatic objects | Thread storage duration objects | Static objects | atexit callbacks | at_quick_exit callbacks |
|---|---|---|---|---|---|
| returning from `main` | destroyed | destroyed | destroyed | called | not called |
| `std::exit` | not destroyed | destroyed (current thread) | destroyed | called | not called |
| `std::quick_exit` | not destroyed | not destroyed | not destroyed | not called | called in reverse order |
| `std::_Exit`, `std::abort` | not destroyed | not destroyed | not destroyed | not called | not called |

`quick_exit` suits this scenario: background threads are still running, and doing full static destruction would be dangerous (¶7), so only a few explicitly registered cleanup functions run before `_Exit` ends the process. `std::terminate` calls `abort` by default.

## Implementation view

!!! impl "Startup and termination code"
    - On ELF (Linux), the compiler collects each translation unit's dynamic initialization into one function (named `_GLOBAL__sub_I_<filename>` by GCC) and puts its address in the `.init_array` section, which the C runtime calls in turn before `main`. The order across translation units depends on how the linker arranges `.init_array`. GCC and Clang's `__attribute__((init_priority(N)))` can adjust the priority explicitly.
    - In the Itanium ABI, after a static object is constructed, the compiler generates a call `__cxa_atexit(dtor, obj, __dso_handle)`. Destructors and `atexit` callbacks share one registration stack, which yields the interleaving of ¶6 naturally. `__dso_handle` lets `dlclose` of a shared library run only the destructors belonging to it.
    - Function-local static variables use a guard variable plus `__cxa_guard_acquire`, `__cxa_guard_release` and `__cxa_guard_abort` to implement thread-safe one-time initialization. GCC's `-fno-threadsafe-statics` turns this off, but that does not conform to the standard.
    - MSVC orders initialization functions with `.CRT$XC*` sections, and `#pragma init_seg(compiler|lib|user)` controls which section an object goes into, and thus its approximate order.

## History

!!! history
    - C++98 already had the rule of definition order within a translation unit and no specified order across translation units, and allowed deferred initialization.
    - C++11 made initialization of block-scope static variables thread-safe, introduced `thread_local` with its initialization rules and `quick_exit`, and rephrased the ordering rules in terms of sequenced before and happens before.
    - C++17's inline variables brought the partially-ordered category.
    - C++20 added `constinit` ([[P1143R2]]); `constexpr` destructors made constant destruction possible; modules let appearance order hold across translation units; and `main` was prohibited from being a coroutine or attached to a named module.
    - Since C++26, returning from `main` evaluates the postcondition assertions of `main`.

## Common misconceptions

!!! pitfall "Global objects are always constructed before main"
    ¶5 allows deferral. Mainstream implementations do construct before `main`, but code should not rely on the side effects of some global constructor (registering itself with a factory, for example) necessarily happening before `main`. Also, if an object file in a static library is not referenced from anywhere, the linker doesn't link it in at all, and its self-registering global objects simply don't exist. That is linker behavior, not something the standard specifies, but it defeats self-registering factories just the same.

!!! pitfall "An object with a constexpr destructor has constant destruction"
    ¶3 puts only objects with constant destruction last. If the destructor is `constexpr` but this particular destruction actually does something that cannot be done in constant evaluation, it is not constant destruction.

!!! pitfall "After main returns, background threads can safely use std::cout"
    `std::cout` itself is indeed never destroyed, but ¶7 doesn't look at whether the object has been destroyed: any use of a library facility not permitted in signal handlers that does not happen before the completion of static destruction is UB, and `std::cout` is one of them. Joining all threads before `main` returns, for example by holding them in `std::jthread` locals in `main`, avoids the problem.

## Questions

!!! question "Question 1"
    What does the following program print?
    ```cpp
    #include <cstdio>
    struct S { S() { std::puts("S"); } ~S() { std::puts("~S"); } };
    S& get() { static S s; return s; }
    struct U { U() { get(); std::puts("U"); } ~U() { std::puts("~U"); } } u;
    int main() {}
    ```

<details markdown="1">
<summary>Answer</summary>

`S`, `U`, `~U`, `~S`. `u`'s constructor calls `get()`, so `s` completes initialization before `u` does. By ¶4, the order of destruction is based on deemed construction, i.e. the moment initialization completes; `s` comes before `u`, so `u` is destroyed first, and calling `get()` again in `~U` is safe. This is the principle behind the remedy of calling the singleton once in the constructor.
</details>

!!! question "Question 2"
    Two translation units both have `inline int x = f();` (the same inline variable), and TU1 defines the ordinary global variable `int y = x + 1;` after `x`. Is `y` guaranteed to see the initialized `x`?

<details markdown="1">
<summary>Answer</summary>

Yes. `x` has partially-ordered initialization, and `y` has ordered, not unordered, initialization. The second case of ¶3.1 requires every definition of `y` (just the one in TU1) to be preceded by some definition of `x`; the definition of `x` in TU1 comes before `y`, so `x` is initialized before `y`. If `y` were defined in a translation unit with no definition of `x`, there would be no such guarantee.
</details>

!!! question "Question 3"
    Why is `int main() { return main(); }` ill-formed rather than UB?

<details markdown="1">
<summary>Answer</summary>

That `main` shall not be used in an expression is a diagnosable rule: [[basic.start.main#3]] uses "shall not" and does not say no diagnostic is required. Per [[intro.compliance]], a program violating it is ill-formed, and the implementation must issue at least one diagnostic. Whether an executable is still produced after the diagnostic is up to the implementation; Clang accepts it as an extension.
</details>

## Summary

| Phase | Rule | Source |
|---|---|---|
| Static initialization | constant initialization or zero-initialization; before all dynamic initialization, no ordering problem | [[basic.start.static#2]] |
| Dynamic initialization within a translation unit | in definition order | [[basic.start.dynamic#3]] |
| Dynamic initialization across translation units | indeterminately sequenced, i.e. the SIOF; remedies: `constinit`, function-local statics, the Schwarz counter, modules | [[basic.start.dynamic#3]] |
| Static members of templates | unordered | [[basic.start.dynamic#1]] |
| Deferred initialization | implementation-defined; if deferred, before the first non-initialization odr-use of an entity in the same translation unit | [[basic.start.dynamic#5]] |
| Initialization throws | `std::terminate` | [[basic.start.dynamic#8]] |
| Order of destruction | reverse of deemed construction, with `atexit` callbacks in the same reverse order; objects with constant destruction last | [[basic.start.term#3]]–[[basic.start.term#6]] |
| `exit` | does not destroy automatic objects; calling `exit` during destruction is UB | [[basic.start.main#4]] |
| Destroyed local statics | passing through their definition again during destruction is UB | [[basic.start.term#5]] |
