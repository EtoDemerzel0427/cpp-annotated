---
title: Startup and termination
summary: "The program-ending functions exit, quick_exit, _Exit and abort in <cstdlib>, and the callback-registering atexit and at_quick_exit: which objects each destroys, which callbacks each calls, and whether each can be used in a signal handler."
updated: 2026-10-19
---

!!! tldr
    - `std::exit` destroys static objects and the current thread's `thread_local` objects, calls the functions registered with `atexit` and flushes the C streams, but destroys no local variables.
    - `std::quick_exit` destroys no objects; it just calls the functions registered with `at_quick_exit` in reverse order and then calls `_Exit`.
    - `std::_Exit` and `std::abort` clean up nothing; they can be called in a signal handler, and `exit` can't.
    - `atexit` and `at_quick_exit` are two independent registries.
    - To have the local variables along the way destroyed on exit, throw an exception caught in `main`, then return from `main` or call `exit`.

## `exit` doesn't destroy local variables

```cpp run title="exit-no-unwind.cpp" ok
#include <cstdio>
#include <cstdlib>

struct Noisy {
    const char* name;
    ~Noisy() { std::printf("~%s\n", name); }
};

Noisy global{"global"};                  // static storage duration
thread_local Noisy tl{"thread_local"};   // thread storage duration

void handler() { std::puts("atexit handler"); }

int main() {
    std::atexit(handler);
    (void)tl;                            // use tl so that it is constructed
    Noisy local{"local"};                // automatic storage duration
    std::exit(0);                        // ~local doesn't run
}
// output:
// ~thread_local
// atexit handler
// ~global
```

The destructor of `local` didn't run. If an RAII object is responsible for flushing a file, releasing a lock or deleting a temporary file, calling `exit` while it is still alive means none of that work gets done.

[[basic.start.main]] and [[basic.start.term]] specify how a program starts and in what order static objects are destroyed; the functions that actually end the program are provided by the library, in this subclause. ¶1 Note 1 says they are all declared in `<cstdlib>`, and [[cstdlib.syn]] lists them all as functions freestanding implementations must also provide.

## Five ways to end

| Way | Local variables destroyed | Static and thread objects destroyed | `atexit` callbacks | `at_quick_exit` callbacks | C streams flushed | Signal-safe |
|---|---|---|---|---|---|---|
| Returning from `main` | `main`'s local variables | Yes | Yes | No | Yes | Not applicable |
| `std::exit` | No | Yes | Yes | No | Yes | No |
| `std::quick_exit` | No | No | No | Yes | Implementation-defined | Yes, if all callbacks are signal-safe |
| `std::_Exit` | No | No | No | No | Implementation-defined | Yes |
| `std::abort` | No | No | No | No | Implementation-defined | Yes |

A **signal-safe** function can be called in a signal handler; calling other library functions in a signal handler is undefined behavior ([[support.signal]]).

Returning from `main` is equivalent to leaving `main`, destroying its local variables, and then calling `std::exit` with the return value ([[basic.start.main#5]]). So the main difference between returning from `main` and calling `exit` in `main` is whether `main`'s own local variables are destroyed. In C++26, `return` also evaluates `main`'s postcondition assertions.

## `exit`: normal termination (¶9)

```cpp
[[noreturn]] void exit(int status);
```

`exit` isn't declared `noexcept`, because it runs user destructors and callbacks. Its effects come in three steps.

¶9.1 First, objects with thread storage duration associated with the current thread are destroyed; then objects with static storage duration are destroyed and functions registered with `atexit` are called, interleaved in the order specified by [[basic.start.term]]. Objects with automatic storage duration are not destroyed as a result of calling `exit`. If a registered function exits via an exception, `std::terminate` is called ([[except.terminate]]).

!!! std
    Objects with automatic storage duration are not destroyed as a result of calling `exit()`.

¶9.2 Next, all open C streams (`FILE*` from `<cstdio>`) with unwritten buffered data are flushed, all open C streams are closed, and all files created by `tmpfile()` are removed. `std::cout` is synchronized with `stdout` by default, and it is itself flushed in the first step along with the destruction of static objects, so output to `std::cout` isn't lost when ending through `exit`.

¶9.3 Finally, control is returned to the host environment. If `status` is 0 or `EXIT_SUCCESS`, an implementation-defined form of the status successful termination is returned; if it is `EXIT_FAILURE`, unsuccessful termination is returned; the meaning of other values is implementation-defined.

### Getting local variables destroyed too

Footnote 166 gives a way: if `main` itself contains no objects with automatic storage duration, then all automatic objects have already been destroyed when `exit` is called in `main`. To get back to such a `main` from a deep call, throw an exception caught in `main`; stack unwinding destroys all the local variables along the way.

```cpp run title="exit-via-exception.cpp" ok
#include <cstdio>
#include <cstdlib>

struct ExitRequest { int status; };
struct Guard { ~Guard() { std::puts("~Guard"); } };

void deep() {
    Guard g;
    throw ExitRequest{3};   // instead of std::exit(3): g is destroyed
}

int run() { deep(); return 0; }

int main() {
    try {
        return run();
    } catch (const ExitRequest& e) {
        std::exit(e.status);  // main has no live automatic objects at this point
    }
}
```

!!! ub "Calling `exit` again during termination"
    The C standard says that if a program calls `exit` more than once, or calls both `exit` and `quick_exit`, the behavior is undefined. The typical case is calling `exit` in an `atexit` callback or in the destructor of a static object.

!!! pitfall "Calling `exit` in a multithreaded program"
    `exit` destroys only the current thread's thread-storage-duration objects; other threads are still running and may be using static objects that are about to be destroyed. Note 3 of [[basic.start.term#7]] points out that a use of an object with static storage duration that doesn't happen before its destruction is undefined behavior. In a multithreaded program, either join all threads before `exit`, or use `quick_exit` instead.

## `atexit`: registering callbacks for normal termination (¶6–¶8)

```cpp
int atexit(c-atexit-handler* f) noexcept;   // void() with extern "C"
int atexit(atexit-handler* f) noexcept;     // void() with extern "C++"
```

¶6 `atexit` registers `f` to be called without arguments at normal termination. The two overloads accept functions with C language linkage and C++ language linkage respectively (see [[cstdlib.syn]]).

- If a call to `atexit` doesn't happen before ([[intro.races]]) the call to `exit`, for example because another thread has already started executing `exit`, it is unspecified whether the registration succeeds.
- Note 2 says `atexit` doesn't introduce data races and can be called concurrently from several threads.
- ¶7 The implementation shall support registration of at least 32 functions. ¶8 It returns 0 if the registration succeeds and nonzero if it fails.
- Footnote 165: a function registered several times is called that many times.

The interleaving order of callbacks and static object destruction is specified by [[basic.start.term#6]]. You can think of each `atexit` registration as constructing an object, all of which are then torn down in reverse order along with the static objects. In the example above, `handler` is registered after `global` has been constructed, so it is called before `~global`.

## `quick_exit`: exit without destroying objects (¶10–¶14)

Sometimes a program must exit but other threads can't be stopped safely, for example because they are blocked in system calls. Then destroying static objects is actually dangerous, since those threads may still be using them. `quick_exit`, introduced in C++11, destroys no objects; it calls only a set of specially registered callbacks and then calls `_Exit`.

```cpp
int at_quick_exit(c-atexit-handler* f) noexcept;
int at_quick_exit(atexit-handler* f) noexcept;
[[noreturn]] void quick_exit(int status) noexcept;
```

¶10 `at_quick_exit` registers `f` to be called without arguments when `quick_exit` is called. If a registration doesn't happen before all calls to `quick_exit`, it is unspecified whether it succeeds. Note 5 stresses that `at_quick_exit` registrations are distinct from `atexit` registrations; a function that should run on both paths must be registered with both. ¶11–¶12 Likewise at least 32 registrations are supported, and success returns 0.

¶13 `quick_exit` calls these functions in the reverse order of their registration. The exception is a function registered while the callbacks are running: it is called after the functions that had already been called at the time it was registered.

- No objects are destroyed as a result of calling `quick_exit`.
- If a registered function exits via an exception, `std::terminate` is called.
- Note 6: the callbacks are run by the thread calling `quick_exit`, which isn't necessarily the thread that registered them, so callbacks can't rely on the identity of thread-storage-duration objects.
- After calling all the callbacks, `quick_exit` calls `_Exit(status)`.

¶14 `quick_exit` is signal-safe when all the registered functions are signal-safe. This lets it be used in a signal handler, which `exit` can't.

```cpp run title="quick-exit.cpp" ok
#include <cstdio>
#include <cstdlib>

struct Noisy { ~Noisy() { std::puts("~Noisy (not printed)"); } };
Noisy global;

void q1() { std::puts("quick 1"); std::fflush(stdout); }
void q2() { std::puts("quick 2"); std::fflush(stdout); }
void a1() { std::puts("atexit (not printed)"); }

int main() {
    std::atexit(a1);
    std::at_quick_exit(q1);
    std::at_quick_exit(q2);
    std::puts("main");
    std::fflush(stdout);   // _Exit isn't guaranteed to flush C streams
    std::quick_exit(3);    // prints main, quick 2, quick 1; exit code 3
}
```

!!! pitfall "Don't forget to flush"
    `quick_exit` ends by calling `_Exit`, and whether `_Exit` flushes streams is implementation-defined; neither macOS nor glibc flushes. Without the `fflush` in the example above, when stdout is redirected to a file and fully buffered, what `puts` wrote stays in the buffer and disappears with the process.

## `_Exit` and `abort`: immediate termination (¶2–¶5)

```cpp
[[noreturn]] void _Exit(int status) noexcept;
[[noreturn]] void abort() noexcept;
```

¶2, ¶4 Both have the same semantics as in the C standard library. ¶3, ¶5 add the C++ part: the program is terminated without executing destructors for objects of automatic, thread or static storage duration, and without calling functions registered with `atexit`; both are signal-safe.

The difference between them comes from C:

- `_Exit(status)` hands `status` to the host environment as a normal exit status. Whether open streams are flushed and closed and whether temporary files are removed is, per the C standard, implementation-defined.
- `abort()` means abnormal termination. It raises the `SIGABRT` signal and returns an implementation-defined form of unsuccessful termination to the host; on Unix-like systems it usually produces a core dump. If the program catches `SIGABRT` and the signal handler doesn't return, `abort` doesn't end the program.

## Connections to the core language

- The default `std::terminate` handler calls `abort` ([[terminate.handler]]). So uncaught exceptions, exceptions thrown out of `noexcept` functions and the other cases in [[except.terminate]] all end up in `abort` by default, destroying no objects.
- {{c++26}} When a contract assertion checked with the enforce or quick-enforce semantic fails, the program is contract-terminated. By [[basic.contract.eval#9]], whether this calls `std::terminate`, calls `std::abort`, or just terminates execution is implementation-defined.

## Questions

!!! question "Questions"
    1. If an `atexit` callback calls `std::atexit(g)` to register a new callback, is `g` called?
    2. Can you call `std::exit` in a signal handler? If not, what should you use?
    3. The program executes `return 0;` in `main`, and afterwards the destructor of some static object throws an exception. What happens?

<details markdown="1">
<summary>Answer</summary>

1. Unspecified. This registration happens after the call to `exit` and doesn't happen before it, so by ¶6 it is unspecified whether it succeeds, and therefore whether `g` is called. By contrast, ¶13 for `quick_exit` explicitly specifies when functions registered while callbacks are running are called.
2. No. `exit` isn't signal-safe: it runs arbitrary destructors and callbacks and operates on C streams; by [[support.signal]], a signal handler calling a function that isn't signal-safe is undefined behavior. Use `_Exit` or `abort` instead (¶3, ¶5), or `quick_exit` provided all `at_quick_exit` callbacks are signal-safe (¶14).
3. `std::terminate` is called. Destructors are `noexcept` by default ([[except.spec]]), and throwing out of one calls `std::terminate`. Even if the destructor is declared `noexcept(false)`, [[basic.start.term#4]] and [[except.terminate]] say that `std::terminate` is called when the destruction of an object with static or thread storage duration exits via an exception.
</details>
