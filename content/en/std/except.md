---
title: Exception handling
summary: "A guide to Chapter 14: the whole life of an exception, from being thrown, through the search for a handler and stack unwinding, to the destruction of the exception object, and which subclause specifies each step."
updated: 2026-10-19
---

!!! tldr
    - Exceptions are the only transfer of control in C++ that can cross any number of function calls while automatically calling destructors along the way.
    - An exception consists of three things: initializing an exception object, finding a handler whose type matches, and stack unwinding, which destroys the automatic objects passed through.
    - Handlers match by run-time type and allow only a few conversions, not general implicit conversions.
    - Whenever the exception handling mechanism itself fails (a destructor throws during unwinding, no handler is found, an exception leaves a `noexcept` function), `std::terminate` is called.
    - Mainstream implementations add no instructions to the path where nothing is thrown; the whole cost is paid when an exception is actually thrown.

## The whole life of an exception

```cpp run title="lifecycle.cpp" ok
#include <cstdio>
#include <exception>

struct Res {
    const char* n;
    ~Res() { std::printf("~%s (uncaught=%d)\n", n, std::uncaught_exceptions()); }
};
struct Err { int code; };

void inner() {
    Res r{"inner"};
    throw Err{42};
}

void middle() {
    Res r{"middle"};
    inner();
}

int main() {
    try {
        Res r{"try"};
        middle();
    } catch (const Err& e) {
        std::printf("caught %d (uncaught=%d)\n", e.code, std::uncaught_exceptions());
    }
}
```

Output:

```text
~inner (uncaught=1)
~middle (uncaught=1)
~try (uncaught=1)
caught 42 (uncaught=0)
```

`return` can leave only one function. `longjmp` can leave several, but does not call destructors ([[csetjmp.syn]]). Exceptions do both, in five steps:

1. **Throw**: `throw Err{42}` initializes an **exception object**, whose storage is managed separately by the implementation and does not go through `operator new` ([[except.throw]]). From this point the exception is uncaught, and `std::uncaught_exceptions()` returns 1.
2. **Search**: going outward along the call chain, find the most recently entered try block, not yet exited, that has a handler of matching type ([[except.handle]]). If the search leaves a `noexcept` function, `std::terminate` is called directly.
3. **Unwind**: as control leaves each level, the automatic objects already constructed at that level are destroyed; this is called **stack unwinding** ([[except.ctor]]).
4. **Catch**: once the handler's parameter `e` has been initialized, the handler becomes active and the exception is considered caught.
5. **Destroy**: when the handler exits in any way other than rethrowing, the exception object is destroyed; if a `std::exception_ptr` still refers to it, destruction waits until the last reference is gone.

## Division of labor among the subclauses

| Subclause | Question it answers |
|---|---|
| [[except.pre]] | The syntax of `try`, `catch` and function-try-blocks; why `goto` cannot jump into a try block |
| [[except.throw]] | What type the exception object has, where it lives, when it is destroyed; when an exception counts as uncaught |
| [[except.ctor]] | Which objects stack unwinding destroys; which subobjects are destroyed when a construction throws halfway |
| [[except.handle]] | How handlers match; the currently handled exception; what happens when no handler is found |
| [[except.spec]] | The `noexcept` specifier; which functions are implicitly `noexcept` |
| [[except.special]] | Every situation in which `std::terminate` is called, and whether the stack is unwound then |

The suggested reading order is [[except.pre]] → [[except.throw]] → [[except.handle]] → [[except.ctor]] → [[except.spec]] → [[except.special]]. Understand the exception object and handler matching first; stack unwinding and `noexcept` both build on them.

## Traces of the zero-overhead design

The Itanium C++ ABI (the ABI GCC and Clang use on Linux and macOS) inserts no instructions on the normal execution path; it only places a table in the read-only data section recording, for each call site, which cleanup code to run if an exception is thrown there. When an exception is actually thrown, the run-time library looks up the table, decodes the stack frame information, and scans the stack twice, which is several orders of magnitude slower than an ordinary return (for details see [[toolchain/exception-implementation]]). Several seemingly odd rules in the standard exist precisely to leave room for this kind of implementation:

- The way storage for the exception object is allocated is unspecified ([[except.throw#4]]). An implementation can set aside an emergency buffer so that `std::bad_alloc` can still be thrown when memory is exhausted.
- Whether the stack is unwound when no handler is found is implementation-defined ([[except.terminate#2]]). A two-phase implementation knows during the search phase that there is no handler, so it terminates directly without unwinding, preserving the complete crash state.
- When the search leaves a `noexcept` function, the stack may be only partially unwound ([[except.terminate#2]]). Compilers can therefore omit the cleanup code in `noexcept` functions.
- Handler matching does no general type conversions ([[except.handle#3]]). Matching is done at run time from type information, and overload resolution cannot be performed at run time.

## Where this chapter meets others

| Meeting point | Where the rules are |
|---|---|
| The throw expression; the `noexcept` operator | [[expr.throw]], [[expr.unary.noexcept]] |
| The exception specification is part of the function type, affecting function pointer conversions and virtual function overriding | [[dcl.fct#13]], [[conv.fctptr]] |
| Memory is returned when a constructor throws in a `new` expression | [[expr.new]], [[except.ctor]] |
| `std::terminate` is called when the dynamic initialization of a variable with static or thread storage duration throws | [[basic.start.dynamic]], [[except.terminate]] |
| An uncaught exception in a coroutine body is passed to `promise.unhandled_exception()` | [[dcl.fct.def.coroutine]] |
| Throwing and catching exceptions during constant evaluation {{c++26}} | [[expr.const.core#2]] |
| The library interfaces of `std::exception_ptr`, `std::nested_exception` and `std::terminate` | [[support.exception]] |
