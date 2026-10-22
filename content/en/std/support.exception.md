---
title: Exception handling support
summary: "The basic part of the header <exception>: the standard exception base class std::exception and how long the result of what() stays valid, bad_exception, terminate and terminate_handler for when exception handling can't continue, and writing transactional destructors with uncaught_exceptions."
updated: 2026-10-19
---

!!! tldr
    - `std::exception` is the common base class of standard library exceptions, but the language doesn't require thrown objects to derive from it; `throw 42;` is perfectly valid.
    - Copy operations of standard exception classes don't throw; the pointer returned by `what()` becomes invalid once the exception object is destroyed.
    - When exception handling can't continue, the implementation calls `std::terminate`, which calls the current terminate_handler; the default handler calls `abort()`. A custom handler must not return.
    - When `terminate` is entered because of an uncaught exception, `std::current_exception()` in the handler can obtain that exception and print it.
    - `uncaught_exceptions()` returns the number of exceptions in the current thread that have been thrown but not yet caught. A transactional destructor should compare the counts at construction and at destruction, not check whether the count is greater than 0.

`<exception>` defines types and functions related to exception handling ([support.exception.general]). Clause 14, [[except]], specifies the language mechanism of exceptions; this is the library support that goes with it. The whole header is freestanding.

| Component | Purpose | Details |
|---|---|---|
| `exception`, `bad_exception` | The standard exception base class; the substitute when `current_exception` fails to copy | This page |
| `terminate_handler`, `set_terminate`, `get_terminate`, `terminate` | The exit for when exception handling can't continue | This page |
| `uncaught_exceptions` | The number of uncaught exceptions in the current thread | This page |
| `exception_ptr`, `current_exception`, `rethrow_exception`, `make_exception_ptr`, `exception_ptr_cast` | Holding, passing and rethrowing exceptions outside handlers | [[propagation]] |
| `nested_exception`, `throw_with_nested`, `rethrow_if_nested` | Exception chains | [[propagation]] |

## `std::exception` [exception]

```cpp
class exception {
public:
  constexpr exception() noexcept;
  constexpr exception(const exception&) noexcept;
  constexpr exception& operator=(const exception&) noexcept;
  constexpr virtual ~exception();
  constexpr virtual const char* what() const noexcept;
};
```

¶1 `exception` is the base class for the types of objects thrown as exceptions by standard library components, and by certain expressions, to report errors detected during program execution. "Certain expressions" refers to exceptions thrown by the language itself: a failed `dynamic_cast` throws `bad_cast` ([[expr.dynamic.cast]]), `typeid` on a null pointer throws `bad_typeid` ([[expr.typeid]]), and `new` with an invalid array length throws `bad_array_new_length` ([[expr.new]]).

### Copying doesn't throw (¶2–¶3)

¶2 Unless otherwise specified, each standard library class derived from `exception` has a public default constructor (unless the synopsis lists other constructors), a copy constructor and a copy assignment operator, none of which throw. After copying, `what()` of two objects with the same dynamic type compare equal by `strcmp`. Paragraph 3 specifies the same postcondition for `exception` itself.

They don't throw because exception objects may be copied; for example, `current_exception` may copy the current exception ([[propagation]]). If copying threw, you would end up with an exception thrown while handling an exception. So exceptions carrying a message, such as `std::runtime_error`, can't store the message in a `std::string`, because copying a `std::string` may throw `bad_alloc`. Both libc++ and libstdc++ use a reference-counted immutable string, so copying just increments a count.

### When the result of `what()` becomes invalid (¶5–¶6)

```cpp run title="what-lifetime.cpp" ub
#include <cstdio>
#include <stdexcept>

const char* message() {
  try {
    throw std::runtime_error("boom");
  } catch (const std::exception& e) {
    return e.what();   // points into the exception object
  }                    // leaving the handler: the exception object is destroyed
}

int main() {
  std::puts(message());   // UB: the pointer is no longer valid
}
```

¶6 The return value of `what()` remains valid until the exception object from which it was obtained is destroyed or a non-const member function of that object is called. In the example above, the exception object is destroyed when the handler exits ([[except.throw]]), and the returned pointer becomes invalid with it. Running it with AddressSanitizer reports heap-use-after-free.

¶5 `what()` returns an implementation-defined null-terminated byte string, which during constant evaluation is encoded with the ordinary literal encoding ([[lex.ccon]]). Paragraph 6 also says it may be a multibyte string suitable for conversion and display as a `wstring`.

!!! note "`constexpr` exception classes {{c++26}}"
    C++26 allows throwing and catching exceptions during constant evaluation, so the members of `exception` all became `constexpr`, which is also why paragraph 5 has to specify the encoding during constant evaluation. Clang 23 doesn't yet support executing a *throw-expression* during constant evaluation, and libc++ hasn't marked these members `constexpr` yet.

## `bad_exception` [bad.exception]

¶1 When `current_exception()` fails to copy the current exception object, the `exception_ptr` it returns may point to a `bad_exception` object (see [[propagation]]). Paragraph 2 says its `what()` returns an implementation-defined string.

!!! history "A relic of dynamic exception specifications"
    `bad_exception` originally served dynamic exception specifications `throw(A, B)`: when a function threw an exception not in the list, `std::unexpected()` was called, and if the list contained `std::bad_exception`, the unexpected exception was replaced with it. Dynamic exception specifications were deprecated in C++11 and removed in C++17, and `std::unexpected` disappeared with them. Today `bad_exception` has only the one use with `current_exception`.

## When exception handling can't continue [exception.terminate]

```cpp run title="terminate-handler.cpp"
#include <cstdio>
#include <cstdlib>
#include <exception>
#include <stdexcept>

[[noreturn]] void report_and_abort() {
  // when terminate is entered because of an uncaught exception, current_exception() gets it
  if (std::exception_ptr p = std::current_exception()) {
    try {
      std::rethrow_exception(p);
    } catch (const std::exception& e) {
      std::fprintf(stderr, "uncaught: %s\n", e.what());
    } catch (...) {
      std::fprintf(stderr, "uncaught non-std exception\n");
    }
  }
  std::abort();   // must not return
}

int main() {
  std::set_terminate(report_and_abort);
  throw std::runtime_error("boom");   // no handler: std::terminate is called
}
```

The program prints `uncaught: boom` and then ends with SIGABRT. When an exception isn't caught, an exception escapes a `noexcept` function, or a destructor throws during stack unwinding, exception handling can't continue and the implementation calls `std::terminate` (see [[except.terminate]] for the full list). `terminate` in turn calls a handler that the program can specify.

The handler can get the exception because [[except.handle]] says that when `std::terminate` is entered due to a throw, an implicit handler is considered active, and that exception is the currently handled exception. libc++abi's default handler does exactly this: it prints `libc++abi: terminating due to uncaught exception of type ...` and then calls `abort`.

### `terminate_handler` ([terminate.handler])

¶1 `terminate_handler` is `void (*)()`, the type of a **handler function** ([[g:terminate-handler]]) called by `terminate` when terminating exception processing.

¶2 Required behavior: it shall terminate execution of the program without returning to the caller. If a custom handler returns, the behavior is undefined ([[res.on.functions]]).

¶3 Default behavior: the default handler calls `abort()`. `abort` destroys no objects, doesn't run functions registered with `atexit`, and doesn't flush C streams ([[support.start.term]]).

### `set_terminate`, `get_terminate` ([set.terminate], [get.terminate])

```cpp
terminate_handler set_terminate(terminate_handler f) noexcept;
terminate_handler get_terminate() noexcept;
```

`set_terminate` makes `f` the current handler (¶1) and returns the previous handler (¶2). Paragraph 3 says it is unspecified whether a null pointer value designates the default handler. `get_terminate` returns the current handler, and Note 1 reminds us that it may be a null pointer.

Compare the new_handler in [[alloc.errors]]. Having no new_handler has a clear meaning (throw `bad_alloc` directly), so its initial value is a null pointer. terminate always has to call some handler, so its initial value is a default function that calls `abort`; in libc++, the first call to `set_terminate` returns a non-null pointer.

### `terminate` ([terminate])

```cpp
[[noreturn]] void terminate() noexcept;
```

¶1 Calls a terminate_handler. Usually it is the current handler; if `set_terminate` is called while an exception is active, which handler is called is unspecified. Note 1 explains that a default handler is always considered a callable handler in this context.

¶2 It is called by the implementation when exception handling must be abandoned ([[except.terminate]]), and may also be called directly by the program. When no matching handler is found, whether the stack is unwound before `terminate` is called is implementation-defined ([[except.terminate#2]]).

## `uncaught_exceptions` [uncaught.exceptions] {{c++17}}

```cpp run title="uncaught-exceptions.cpp" ok
#include <cstdio>
#include <exception>

class Transaction {
  int entry_ = std::uncaught_exceptions();   // recorded at construction
public:
  ~Transaction() {
    if (std::uncaught_exceptions() > entry_) std::puts("rollback");
    else                                      std::puts("commit");
  }
};

struct Logger {
  ~Logger() { Transaction t; }   // runs during stack unwinding
};

int main() {
  { Transaction t; }                              // commit
  try { Transaction t; throw 1; } catch (...) {}  // rollback
  try { Logger l; throw 2; } catch (...) {}       // commit
}
```

A transaction object wants to know, when it is destroyed, whether it is leaving scope normally (commit) or being destroyed by stack unwinding from an exception (rollback).

¶1 `uncaught_exceptions()` returns the number of **uncaught exceptions** ([[g:uncaught-exception]]) in the current thread. An exception is uncaught from the time the initialization of the exception object completes until a handler for it is activated ([[except.throw]]), that is, the period after it is thrown, during stack unwinding, before it enters a `catch`.

The third case shows why counts must be compared. `Logger`'s destructor runs during stack unwinding, when the count is 1; but the `Transaction` inside it also saw a count of 1 when constructed, and it ends normally, so it should commit. Checking only whether the count is greater than 0 would misjudge it as a rollback.

¶2 When the count is greater than 0, throwing an exception may result in a call to `std::terminate`, for example if an exception thrown by a destructor during stack unwinding escapes the destructor. It says "may" because catching it inside the destructor is fine.

!!! history "From `uncaught_exception()` to `uncaught_exceptions()`"
    C++98 had only the singular `bool uncaught_exception()`, which could only answer whether there was any uncaught exception, and gets exactly the third case above wrong. [[N4152]] introduced the version returning a count (C++17); the singular form was deprecated in C++17 and removed in C++20. libc++ under `-std=c++2c` no longer has `std::uncaught_exception`.

!!! pitfall "The count in coroutines"
    The count is per thread, and the transaction object records a snapshot at construction. If the object lives in a coroutine frame and the coroutine is suspended on one thread and resumed on another, or is suspended and resumed during stack unwinding, the counts at construction and at destruction are no longer comparable.
