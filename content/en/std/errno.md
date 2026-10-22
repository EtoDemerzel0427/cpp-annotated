---
title: Error numbers
summary: "The contents of <cerrno> are the same as POSIX <errno.h>, and errno must be a macro, with one per thread; the right way to read errno, and how it corresponds to std::errc."
updated: 2026-10-19
---

!!! tldr
    - `<cerrno>` has the same contents as POSIX's `<errno.h>`, so C++ requires the full set of POSIX error number macros, not just the three from ISO C.
    - `errno` must be a macro, and each thread has its own: a failure in one thread doesn't change another thread's `errno`.
    - Library functions never set `errno` to 0, but successful calls may change it to a nonzero value. So clear it first, then call, judge failure by the return value, and read `errno` immediately.
    - Each enumerator of `std::errc` has the same value as the corresponding `E*` macro; on platforms where two macros have the same value, the corresponding two enumerators are equal too.

`errno` is C's mechanism for reporting errors: when a library function fails, it writes a positive integer into `errno`, and the caller reads it afterwards. C++ keeps it mainly for calling C library and POSIX interfaces.

## An example

```cpp run title="errno-strtol.cpp" ok
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <thread>

int main() {
    errno = 0;                                   // 1. clear it first
    long v = std::strtol("99999999999999999999", nullptr, 10);
    int e = errno;                               // 2. save it immediately
    if (e == ERANGE)                             // 3. the return value LONG_MAX is ambiguous; check errno
        std::printf("ERANGE, v=%ld (%s)\n", v, std::strerror(e));

    std::thread t([] { errno = EDOM; });         // changes the new thread's own errno
    t.join();
    std::printf("%d\n", errno == ERANGE);        // 1: this thread's errno is unaffected
}
```

The output in our tests is `ERANGE, v=9223372036854775807 (Result too large)` and `1`.

The three steps come from ISO C's conventions for library functions: library functions never set `errno` to 0; and as long as a function's description doesn't specify how it uses `errno`, the function may change `errno` to a nonzero value even if it succeeds. So:

1. clear it before the call, otherwise you may read a value left by some earlier call;
2. save it immediately after the call, because the next library call (including `printf`) may overwrite it;
3. look at `errno` only when the return value indicates a possible failure. On overflow `strtol` returns `LONG_MAX`, which is also a valid conversion result, and only `errno` can tell the two apart.

## Aligned with POSIX, one per thread [errno.general]

!!! std
    The contents of the header `<cerrno>` are the same as the POSIX header `<errno.h>`, except that errno shall be defined as a macro.

¶1 This sentence has three layers of meaning.

First, the reference is POSIX, not ISO C. ISO C's `<errno.h>` requires only the three macros `EDOM`, `EILSEQ` and `ERANGE`, while C++ requires POSIX's full set of `E*` macros, even on non-POSIX platforms such as Windows. Note 1 explains that this is for compatibility with POSIX.

Second, `errno` must be a macro. C allows it to be a macro or an identifier with external linkage; C++ allows only a macro. The macro can expand to a dereference of a function's return value, the function returning the address of this thread's `errno`: `(*__error())` on macOS, `(*__errno_location())` on glibc. So a program can't write `extern int errno;` itself, nor `std::errno`; macros have no namespaces.

Third, each thread has a distinct `errno` value. ISO C says the initial thread's `errno` is 0 at program startup, and the initial value in other threads is indeterminate, so in a new thread it must likewise be cleared before use.

## Synopsis [cerrno.syn]

```cpp
#define errno see below

#define E2BIG see below            // freestanding
#define EACCES see below           // freestanding
// ... more than seventy E* macros in all, each marked freestanding
#define EXDEV see below            // freestanding
```

¶1 The meaning of these macros is defined by POSIX.

All the `E*` macros are marked freestanding, so freestanding implementations (implementations that can run without depending on an operating system; see [[intro.compliance]]) must provide them too; `errno` itself isn't. Error numbers are just a set of integer constants, which `std::errc` ([[syserr]]), also freestanding, needs to use; a thread-local `errno` needs run-time support.

## Correspondence with `std::errc`

`enum class errc` in `<system_error>` gives a name to nearly every `E*` macro, and each enumerator has the same value as the corresponding macro ([[system.error.syn#1]]): the value of `errc::no_such_file_or_directory` is `ENOENT`.

POSIX allows some error numbers to have the same value, for example `EAGAIN` and `EWOULDBLOCK`, or `ENOTSUP` and `EOPNOTSUPP`. On such platforms the corresponding two enumerators are equal, and putting both in the same `switch` fails to compile:

```cpp run title="errc-duplicates.cpp" impl
#include <system_error>

int classify(std::errc e) {
    switch (e) {
    case std::errc::resource_unavailable_try_again: return 1;   // EAGAIN
    case std::errc::operation_would_block:          return 2;   // EWOULDBLOCK
    // equal on macOS and Linux: error: duplicate case value
    default: return 0;
    }
}

int main() {}
```

On macOS, `EAGAIN` and `EWOULDBLOCK` are both 35, and Clang reports "duplicate case value"; `ENOTSUP` (45) and `EOPNOTSUPP` (102) aren't equal. On Linux both pairs are equal. Portable code can assume neither that these enumerators are distinct nor that they are the same.

!!! tip "Alternatives that don't depend on errno"
    C++17's `std::from_chars` / `to_chars` ([[charconv]]) don't use `errno`; they bring back a `std::errc` in the returned struct. `<filesystem>` uses `error_code` out-parameters or `filesystem_error` exceptions. When calling C or POSIX interfaces directly, you can immediately save the error number as a value with `std::error_code(errno, std::generic_category())` (see [[syserr]]).

## Common misconceptions

!!! pitfall "Calling another function before checking"
    In `if (fopen(...) == nullptr) { log("failed"); if (errno == ENOENT) ... }`, the I/O inside `log` may already have overwritten `errno`. Save it first with `int e = errno;`.

!!! pitfall "Using `errno != 0` to decide whether a call failed"
    Successful calls may also change `errno` to a nonzero value. Look at the return value first, and only when it indicates failure, or is ambiguous as with `strtol`, look at `errno`.

!!! pitfall "Thinking C++ standard library functions set errno"
    Apart from functions inherited from C, the standard library generally doesn't specify any effect on `errno`; the components of `<system_error>` are explicitly specified not to change `errno` ([[syserr.general#2]]).

## Questions

!!! question "Question 1"
    Why does C++ require `errno` to be a macro, while C allows it to be an identifier with external linkage?

<details markdown="1">
<summary>Answer</summary>

A macro lets implementations provide a thread-local `errno` uniformly: it expands to a call to some function returning this thread's address. It also prevents programs from declaring `errno` themselves with `extern int errno;`, which would be wrong under a thread-local implementation.
</details>

!!! question "Question 2"
    A coroutine may resume on another thread after `co_await`. What happens if `errno` is set before the `co_await` and read after it?

<details markdown="1">
<summary>Answer</summary>

`errno` is thread-local, and the code before and after the suspension may run on different threads, so it reads a different `errno` object. An error number set before suspension may be gone after resumption, or be another thread's value. In a coroutine, convert `errno` into a value such as an `error_code` and save it before the suspension point.
</details>
