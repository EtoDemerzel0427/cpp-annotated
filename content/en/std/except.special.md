---
title: Special functions and std::terminate
summary: "The library facilities the exception mechanism relies on (terminate, uncaught_exceptions, current_exception, nested_exception); the situations in which std::terminate is called; and whether the stack is unwound first: implementation-defined when no handler is found, possibly partial when a noexcept function is left, and forbidden in every other case."
updated: 2026-10-19
---

!!! tldr
    - When the exception mechanism itself fails (for example, no handler is found, or a destructor throws again during unwinding), the program calls `std::terminate`, whose default handler calls `std::abort`.
    - When no handler is found, whether the stack is unwound before `std::terminate` is called is implementation-defined; mainstream implementations do not unwind, and destructors do not run.
    - When an exception leaves a `noexcept` function, the stack may be unwound, partially unwound, or not unwound; this is why `noexcept` enables optimizations.
    - In every other case the stack must not be unwound; and once unwinding has begun, it cannot be cut short because termination is foreseen.
    - `std::uncaught_exceptions`, `std::current_exception` and `std::nested_exception` let a program inspect and save exceptions in flight.

## Library facilities used by the exception mechanism ([except.special.general])

[[except.special.general#1]] lists four library facilities that work with the exception mechanism:

| Facility | Purpose | Defined in |
|---|---|---|
| `std::terminate` | the exit when the exception mechanism itself fails | [[exception.terminate]] |
| `std::uncaught_exceptions()` | the number of exceptions in the current thread that have been thrown but not yet caught by a handler | [[uncaught.exceptions]] |
| `std::current_exception()` | obtains the currently handled exception ([[except.handle#10]]) as an `exception_ptr` | [[propagation]] |
| `std::nested_exception` | saves the currently handled exception when throwing a new one, forming a chain of exceptions | [[except.nested]] |

The typical use of `std::uncaught_exceptions()` is to let a destructor tell whether it is leaving its scope normally or being called during stack unwinding:

```cpp run title="uncaught.cpp" ok
#include <cstdio>
#include <exception>

struct Tx {
    int n = std::uncaught_exceptions();
    ~Tx() { std::puts(std::uncaught_exceptions() > n ? "rollback" : "commit"); }
};

int main() {
    { Tx t; }                                 // commit
    try { Tx t; throw 1; } catch (int) {}     // rollback
}
```

`std::nested_exception` is used to translate a low-level exception into a high-level one without losing the cause:

```cpp run title="nested.cpp" ok
#include <cstdio>
#include <exception>
#include <stdexcept>

void open_config() { throw std::runtime_error("file not found"); }

void load() {
    try { open_config(); }
    catch (...) {
        std::throw_with_nested(std::logic_error("cannot load config"));
    }
}

void print(const std::exception& e, int depth = 0) {
    std::printf("%*s%s\n", depth * 2, "", e.what());
    try { std::rethrow_if_nested(e); }
    catch (const std::exception& inner) { print(inner, depth + 1); }
}

int main() {
    try { load(); } catch (const std::exception& e) { print(e); }
}
```

The output is two lines: `cannot load config`, and an indented `file not found`.

## When std::terminate is called ([except.terminate] ¶1)

```cpp run title="terminate-rethrow-nothing.cpp" ok
#include <cstdio>
#include <cstdlib>
#include <exception>

int main() {
    std::set_terminate([] { std::fputs("terminate: throw; with no exception\n", stderr); std::abort(); });
    throw;      // no exception is being handled, so std::terminate is called
}
```

¶1 Some errors cannot be recovered from, such as an exception not being handled, or a `std::thread` object being destroyed while its thread is still running. The program then calls `std::terminate`. Note 1 collects all such situations; the normative rules are in the subclauses each one cites.

The first 10 items belong to the language and the exception mechanism itself:

| Item | Situation | Source |
|---|---|---|
| 1.1 | after the exception object is initialized and before a handler is activated, a function invoked by the exception mechanism exits via an exception, such as a destructor during unwinding or the copy constructor of a handler parameter | [[except.throw]] |
| 1.2 | no handler is found | [[except.handle#8]] |
| 1.3 | the search for a handler exits the function body of a non-throwing function; {{c++26}} including a contract-violation handler invoked for that function's contract assertions exiting via an exception | [[except.handle#7]], [[basic.contract.eval]] |
| 1.4 | the destruction of an object during stack unwinding throws | [[except.throw]] |
| 1.5 | the initialization of a non-block variable with static or thread storage duration throws | [[basic.start.dynamic]] |
| 1.6 | the destruction of an object with static or thread storage duration throws | [[basic.start.term]] |
| 1.7 | a function registered with `std::atexit` or `std::at_quick_exit` throws | [[support.start.term]] |
| 1.8 | `throw;` is executed when no exception is being handled | [[expr.throw]] |
| 1.9 | `rethrow_nested` is called on a `std::nested_exception` that holds no exception | [[except.nested]] |
| 1.10 | the initial function of a thread throws | [[thread.thread.constr]] |

The remaining items are library components that choose termination for errors they cannot report:

| Item | Situation | Source |
|---|---|---|
| 1.11 | an element access function of a parallel algorithm throws, when the execution policy so specifies | [[algorithms.parallel.exceptions]] |
| 1.12 | the destructor or move assignment of a `std::thread` that is still joinable is invoked | [[thread.thread.destr]], [[thread.thread.assign]] |
| 1.13 | `wait`, `wait_until` or `wait_for` of a condition variable fails to meet a postcondition | [[thread.condition.condvar]] |
| 1.14 | a callback throws when a stop is requested or a `stop_callback` is constructed | [[stopsource.mem]] etc. |
| 1.15–1.19 | {{c++26}} several error states of `std::execution`, such as destroying a `run_loop` that is still running, destroying a `counting_scope` that has not been joined, or throwing from a `std::execution::task` coroutine that does not support completing with an `exception_ptr` error | [[exec.run.loop]], [[exec.simple.counting.ctor]], [[exec.task]] etc. |

```cpp run title="terminate-thread.cpp" ok
#include <cstdio>
#include <cstdlib>
#include <exception>
#include <thread>

int main() {
    std::set_terminate([] { std::fputs("terminate: joinable thread destroyed\n", stderr); std::abort(); });
    std::thread t([] {});
}   // 1.12: t is still joinable, so its destructor calls std::terminate
```

`std::terminate()` calls the current [[g:terminate-handler]], and the default handler calls `std::abort()` ([[terminate.handler]]). `std::set_terminate` can replace it, but the new handler must end the program and must not return. It can log, print a stack trace, and finally call `std::abort` or `std::_Exit`. When termination is caused by an exception, the handler can obtain that exception with `std::current_exception()`; see [[except.handle]] for an example.

## Whether the stack is unwound first (¶2)

```cpp run title="noexcept-partial-unwind.cpp" impl
#include <cstdio>
#include <cstdlib>
#include <exception>

struct D {
    const char* n;
    ~D() { std::printf("~%s\n", n); std::fflush(stdout); }
};

void g() { D d{"g-local"}; throw 1; }
void f() noexcept { D d{"f-local"}; g(); }

int main() {
    std::set_terminate([] { std::puts("terminate"); std::fflush(stdout); std::_Exit(0); });
    D m{"main-local"};
    f();
}
```

With Clang 23 (the same at `-O0` and `-O2`), the output is `~g-local` and `terminate`. The local object of `g` was destroyed; those of `f` and `main` were not. The process of destroying automatic objects level by level along the call chain as an exception propagates is called [[g:stack-unwinding]], and here only part of the stack was unwound. ¶2 specifies the extent of unwinding by situation:

| Situation | Before `std::terminate` is called |
|---|---|
| No matching handler is found (1.2) | {{impl}} unwound or not |
| The search for a handler exits a non-throwing function (1.3) | {{impl}} unwound, partially unwound, or not unwound at all |
| Every other situation | must not be unwound |

!!! std
    In all other situations, the stack shall not be unwound before the function `std::terminate` is invoked.

The last sentence of ¶2 also forbids one optimization: an implementation cannot end unwinding prematurely because it determines that unwinding will eventually result in a call to `std::terminate`. Once a handler has been found and unwinding has begun, all the destructions along the way must be carried out, even if the implementation can foresee that one of those destructors will throw.

### Why not unwinding is allowed

If the stack is not unwound when no handler is found, the call stack in the core dump stops at the throw point, so you can see directly who threw. After unwinding the stack is empty, with only `main` left.

This also matches the two-phase implementation of the Itanium ABI: first a read-only search pass that does not modify the stack; only after a handler is found does the cleanup phase begin, actually destroying objects. When the search fails, it naturally stops where it is (see [[toolchain/exception-implementation]]).

### Why noexcept allows partial unwinding

In a two-phase implementation, a `noexcept` function appears in the exception table as a handler that catches everything and calls `std::terminate`. The search phase finds it, and the cleanup phase unwinds up to that function, which is why the local object of `g` was destroyed in the example above. But the `noexcept` function's own local objects need not be destroyed, so the compiler need not generate cleanup code for them. Allowing partial unwinding describes exactly this most efficient implementation.

## Common misconceptions

!!! pitfall "Destructors always run before termination"
    Whether no handler is found or a `noexcept` function is left, the standard does not guarantee that destructors run. Flushing log buffers, deleting temporary files and releasing lock files cannot rely on uncaught exceptions plus RAII. The portable approach is a `catch (...)` in `main` and in every thread's entry function.

!!! pitfall "A terminate handler can return"
    A handler returning is UB; it violates the required behavior specified by [[terminate.handler]]. A handler must end by calling a function that does not return, such as `std::abort` or `std::_Exit`.

## Questions

!!! question "Question 1"
    Why can the stack be partially unwound when a `noexcept` function is left, while when no handler is found it can only be fully unwound or not unwound at all?

<details markdown="1">
<summary>Answer</summary>

When no handler is found, an implementation either fails in the search phase and so does not unwind, or, like a single-phase implementation, unwinds all the way to the bottom of the stack before discovering there is no handler, and so unwinds fully. Stopping halfway has no natural corresponding implementation and no benefit.

The boundary of a `noexcept` function is in the middle of the call stack. A two-phase implementation treats the `noexcept` function as a handler, and the cleanup phase unwinds only up to it, without cleaning up its own frame. Partial unwinding allows exactly this implementation, while still allowing other implementations to unwind fully or not at all.
</details>

!!! question "Question 2"
    When the constructor of a static object throws (1.5), does the standard allow the stack to be unwound?

<details markdown="1">
<summary>Answer</summary>

No. 1.5 is not one of the two exceptions listed in ¶2; it falls under every other situation, so the stack must not be unwound before `std::terminate` is called. The call comes from the run-time startup code, so the stack is not deep anyway, but the local objects of the functions at each level of the initialization really are not destroyed.
</details>
