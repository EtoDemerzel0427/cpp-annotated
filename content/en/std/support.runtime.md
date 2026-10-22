---
title: Other runtime support
summary: "The rules C++ adds to the runtime facilities inherited from C: data races with getenv and setlocale, argument promotion and va_start in <cstdarg>, longjmp skipping non-trivial destructors being UB, and which operations in a signal handler are signal-safe."
updated: 2026-10-19
---

!!! tldr
    - `getenv` itself doesn't introduce data races, but running it concurrently with `setenv` or `putenv` is a data race.
    - When retrieving variadic arguments with `va_arg`, write the promoted type: retrieve `float` as `double`, and `char` and `short` as `int`.
    - If replacing `setjmp`/`longjmp` with `catch`/`throw` would call a non-trivial destructor of some automatic object, that `longjmp` is UB.
    - A signal handler may do only signal-safe things: lock-free atomic operations and the few library functions marked signal-safe; it can't call `printf` or `new`, throw exceptions, or access `thread_local`.

C++ inherits several runtime facilities from C: variadic arguments, non-local jumps and signals. C's rules don't deal with destructors, exceptions, threads or coroutines, so they can't answer questions like what happens when `longjmp` skips a `std::string`, or whether a signal handler can `new`. This subclause holds the rules C++ adds to them, mostly tightening the C semantics.

## Environment variables and locale [support.runtime.general]

¶1 `<csetjmp>` (non-local jumps), `<csignal>` (signal handling), `<cstdarg>` (variadic arguments) and the runtime environment functions in `<cstdlib>` (`getenv`, `system`) are provided for compatibility with C code.

¶2 Calls to `getenv` don't introduce a data race ([[res.on.data.races]]) provided that nothing modifies the environment. Note 1 points out that POSIX's `setenv` and `putenv` modify the environment. So one thread calling `getenv` while another calls `setenv` is a data race. This is a common cause of crashes in multithreaded programs, for example when some third-party library calls `setenv` in a background thread.

¶3 A call to `setlocale` may introduce a data race with other calls to `setlocale` or with calls to functions affected by the current C locale (`printf`, `isalpha`, `strtod` and so on). The implementation shall behave as if no library function other than `locale::global` calls `setlocale`. That is, the standard library never changes the C locale behind the program's back.

## Variadic arguments [cstdarg.syn]

```cpp run title="va-args.cpp" ok
#include <cstdarg>

int sum(int count, ...) {
  std::va_list ap;
  va_start(ap, count);   // per the draft the second argument is discarded; Clang still requires it
  int s = 0;
  for (int i = 0; i < count; ++i)
    s += va_arg(ap, int);   // char and short have been promoted to int
  va_end(ap);
  return s;
}

double avg(int n, ...) {
  std::va_list ap;
  va_start(ap, n);
  double s = 0;
  for (int i = 0; i < n; ++i)
    s += va_arg(ap, double);   // float has been promoted to double
  va_end(ap);
  return s / n;
}

int main() {
  char c = 1;
  short h = 2;
  return (sum(3, c, h, 3) == 6 && avg(2, 1.0f, 3.0) == 2.0) ? 0 : 1;
}
```

¶1 The contents of `<cstdarg>` are the same as C's `<stdarg.h>`, and the whole header is freestanding. C++ changes two things.

### Default argument promotions (¶1.1)

¶1.1 The default argument promotions are those of C++ ([[expr.call#13]]), not C. When arguments are passed to `...`, `float` is promoted to `double` and integer types smaller than `int` undergo integral promotion, as in C. So `va_arg(ap, float)` and `va_arg(ap, char)` can never be right: if the type written in `va_arg` isn't compatible with the promoted argument type, the behavior is undefined.

C++ also specifies several types that C doesn't have:

- an argument of type `std::nullptr_t` is converted to `void*`;
- an argument of scoped enumeration type, or of a class type with an eligible non-trivial copy constructor, an eligible non-trivial move constructor or a non-trivial destructor, is **conditionally-supported**: the implementation may not support it, and if it does, the semantics are implementation-defined.

For types such as `std::string`, Clang chooses not to support it and gives a diagnostic that is an error by default:

```cpp error
#include <string>
void v(int, ...);
void f(std::string s) { v(0, s); }   // error: can't pass a non-trivial type to ...
```

The diagnostic reads `cannot pass object of non-trivial type 'std::string' ... through variadic function; call will abort at runtime [-Wnon-pod-varargs]`.

In C++, a variadic template ([[temp.variadic]]) is almost always the better choice: it is type-safe and can take any type.

### `va_start` needs only one argument (¶1.2)

```cpp
#define va_start(V, ...) see below
```

¶1.2 In the current draft, `va_start`, as in C23, needs only one argument: `va_start(ap)` is enough, and the last named parameter no longer has to be written. If a second or later argument is written, its preprocessing tokens are discarded; but if those arguments, after expansion, contain unbalanced parentheses or a preprocessing token that can't be converted to a token, the program is IFNDR, ill-formed with no diagnostic required. Note 1 explains that the second argument is kept for compatibility with how earlier versions of C++ wrote it.

This is especially useful for a function with no named parameters, such as `void f(...)`, which previously couldn't use `va_start` at all.

!!! impl "Clang's C++ mode doesn't support single-argument `va_start` yet"
    Clang's `<stdarg.h>` defines `va_start` as a variadic macro only in C23 mode (`__STDC_VERSION__ >= 202311L`); in C++ mode it is still `va_start(ap, param)`, and `va_start(ap)` gives the error `too few arguments provided to function-like macro invocation`. At the time of writing, the portable form is still to write two arguments.

## Non-local jumps [csetjmp.syn]

```cpp
namespace std {
  using jmp_buf = see below;
  [[noreturn]] void longjmp(jmp_buf env, int val);
}
#define setjmp(env) see below
```

¶1 The contents of `<csetjmp>` are the same as C's `<setjmp.h>`.

### Skipping non-trivial destructors is UB (¶2)

<div class="compare" markdown="1">

```cpp run ok
#include <csetjmp>
#include <cstdio>

std::jmp_buf env;
void fail() { std::longjmp(env, 1); }

int main() {
  if (setjmp(env) == 0) {
    int x = 42;   // trivially destructible
    (void)x;
    fail();
  } else {
    std::puts("jumped back");
  }
}
```

```cpp run ub
#include <csetjmp>
#include <string>

std::jmp_buf env;
void fail() { std::longjmp(env, 1); }

void work() {
  std::string s = "this string owns heap memory";
  fail();   // UB: with throw instead, s's destructor would be called
}

int main() {
  if (setjmp(env) == 0) work();
}
```

</div>

!!! std
    A `setjmp`/`longjmp` call pair has undefined behavior if replacing the `setjmp` and `longjmp` by `catch` and `throw` would invoke any non-trivial destructors for any objects with automatic storage duration.

¶2 The test is a thought experiment: replace `longjmp` with `throw` and the location of `setjmp` with `catch`, then see which automatic objects stack unwinding ([[except.ctor]]) would destroy along the way. If any of those destructors is non-trivial, this `longjmp` is UB. On the left, `x` is an `int` with no non-trivial destructor, so there is no problem; on the right, `s`'s destructor is skipped.

Why make it UB instead of specifying that destructors are skipped? A typical `longjmp` implementation just restores a few registers (stack pointer, program counter, callee-saved registers) and knows nothing about C++ objects. Skipping destructors means a `std::string`'s heap memory leaks and a `std::lock_guard`'s lock is never released. On the other hand, on some platforms (such as MSVC on Windows), `longjmp` does unwind the stack and call destructors. The standard doesn't want to mandate either, so it is UB.

The second sentence of ¶2 is about coroutines: calling `setjmp` or `longjmp` in a coroutine's **suspension context** (a place in the function body where `co_await` may appear; see [[expr.await]]) has undefined behavior. The coroutine frame may be on the heap, and on suspension control returns to the caller, so the stack state saved in a `jmp_buf` is incompatible with how coroutines execute.

### Restrictions from C

Several of C's restrictions still apply in C++:

- `setjmp` may appear only in a few contexts: as the entire condition of an `if`, `switch` or loop, compared with an integer constant expression, as `!setjmp(env)`, or alone as an expression statement. Storing its return value in a variable is UB.
- In the function containing `setjmp`, a non-`volatile` automatic variable modified between `setjmp` and `longjmp` has an indeterminate value after the `longjmp`.
- Calling `longjmp` back to a `jmp_buf` after the function containing the `setjmp` has returned is UB.

!!! tip "Use exceptions instead of `longjmp` in C++"
    The only reasonable use of `setjmp`/`longjmp` in C++ is interacting with C libraries that report errors with it, such as libpng, libjpeg and Lua's C API. In that case, make sure the C++ stack frames between `setjmp` and `longjmp` contain only trivially destructible objects. The usual approach is to call `setjmp` in a very thin C-style wrapper function, and after jumping back, throw an exception at the C++ level.

## Signals [csignal.syn] [support.signal]

```cpp
namespace std {
  using sig_atomic_t = see below;
  extern "C" using signal-handler = void(int);   // exposition only
  signal-handler* signal(int sig, signal-handler* func);
  int raise(int sig);
}
// plus the macros SIG_DFL, SIG_ERR, SIG_IGN, SIGABRT, SIGFPE, SIGILL, SIGINT, SIGSEGV, SIGTERM
```

[csignal.syn] ¶1 The contents of `<csignal>` are the same as C's `<signal.h>`. The handler type is an `extern "C"` function type, so strictly speaking, passing a function with C++ language linkage to `signal` is a type mismatch ([[dcl.link]]). Mainstream compilers don't distinguish function types by language linkage, so this works in practice, but the most rigorous way is to declare the handler `extern "C"`.

```cpp run title="signal-handler.cpp" ok
#include <atomic>
#include <csignal>
#include <cstdio>

volatile std::sig_atomic_t flag = 0;
std::atomic<int> counter{0};
static_assert(std::atomic<int>::is_always_lock_free);

extern "C" void handler(int sig) {
  flag = 1;                                         // OK
  counter.fetch_add(1, std::memory_order_relaxed);  // OK: plain lock-free atomic operation
  std::signal(sig, handler);                        // OK: ¶4
  // std::printf("got signal\n");                   // UB: printf isn't signal-safe
  // throw 1;                                       // UB: ¶3.4
}

int main() {
  std::signal(SIGINT, handler);
  std::raise(SIGINT);   // triggers the handler synchronously
  std::printf("%d %d\n", int(flag), counter.load());   // 1 1
}
```

### Signal safety (¶3)

!!! std
    A signal handler invocation has undefined behavior if it includes an evaluation that is not signal-safe.

[support.signal] ¶3 An invocation of a signal handler that includes an evaluation that isn't **signal-safe** ([[g:signal-safe]]) has undefined behavior. An evaluation isn't signal-safe if it involves any of the following:

| ¶ | Unsafe operation | Reason |
|---|---|---|
| ¶3.1 | A call to a standard library function, except plain lock-free atomic operations (see below) and functions explicitly identified as signal-safe | Library functions may hold locks, for example `malloc` and `printf`. If the signal interrupts a thread holding the lock and the handler takes the same lock, it deadlocks. Note 1 points out that this also excludes `new` and `delete` expressions that use the library-provided allocation functions |
| ¶3.2 | An access to an object with thread storage duration | Accessing a `thread_local` may trigger lazy initialization or call `__tls_get_addr`, which may allocate memory |
| ¶3.3 | A `dynamic_cast` expression | The runtime library's implementation can't necessarily run safely in a signal |
| ¶3.4 | Throwing an exception | The stack unwinder isn't async-signal-safe, and signal frames don't necessarily have unwind information |
| ¶3.5 | Control entering a *try-block* or *function-try-block* | Same reason as the previous item |
| ¶3.6 | Initialization of a variable with static storage duration requiring dynamic initialization ([[basic.start.dynamic]], [[stmt.dcl]]) | A footnote explains that this can happen when the handler is the first to odr-use the variable; initialization of local statics takes a lock |
| ¶3.7 | Waiting for the completion of the initialization of a variable with static storage duration | If the interrupted thread holds the initialization lock, the handler waits forever |

Functions explicitly identified as signal-safe are scattered across the standard, for example `_Exit`, `abort`, `quick_exit` when all registered callbacks are signal-safe ([[support.start.term]]), all member functions of `numeric_limits` ([[numeric.limits.members]]), all functions of `initializer_list` ([[support.initlist]]), the functions in `<type_traits>` ([[type.traits.general]]), and `std::forward`, `std::move` and others ([[forward]]).

### Plain lock-free atomic operations (¶2)

¶2 A **plain lock-free atomic operation** ([[g:plain-lock-free-atomic-operation]]) is an invocation of a function `f` from [[atomics]] such that:

- ¶2.1 `f` is `atomic_is_lock_free()`, or ¶2.2 `f` is the member function `is_lock_free()`;
- ¶2.3 `f` is a non-static member function of `atomic_flag`, or ¶2.4 `f` is a non-member function whose first parameter has type *cv* `atomic_flag*`;
- ¶2.5 `f` is a non-static member function invoked on an object `A` such that `A.is_lock_free()` is `true`;
- ¶2.6 `f` is a non-member function, and for every pointer-to-atomic argument `A` passed to `f`, `atomic_is_lock_free(A)` is `true`.

`atomic_flag` qualifies unconditionally because its operations are guaranteed to be lock-free ([[atomics.flag]]). For other atomic types it depends on whether the particular object is lock-free; the example above confirms this with `static_assert(std::atomic<int>::is_always_lock_free)`.

### Synchronization and reinstallation (¶1, ¶4)

¶1 A call to `signal` synchronizes with ([[intro.races]]) every invocation of the signal handler it installs. So data written before the call to `signal` is visible in the handler.

¶4 A call to `signal` in a signal handler is signal-safe if the first argument equals the number of the signal that caused this handler invocation. This lets a handler reinstall itself; some systems reset the disposition to `SIG_DFL` before calling the handler.

!!! note "C++ signal safety versus POSIX async-signal safety"
    POSIX has its own list of async-signal-safe functions, allowing system calls such as `write` and `_exit` in handlers. The C++ standard doesn't concern itself with these functions: they aren't standard library functions, ¶3.1 doesn't prohibit them, and whether they are safe is up to POSIX. In practice, signal handlers on Unix usually do one of three things: set an atomic flag, write a byte to a self-pipe, or call `_exit`.
