---
title: Diagnostics library
summary: "A guide to Clause 19: what problems the <stdexcept> exception classes, assert, errno, <system_error>, <stacktrace> and <debugging> each solve, how they divide the work, and how they relate to exceptions and contracts in the language."
updated: 2026-10-19
---

!!! tldr
    - Clause 19 contains six groups of tools: predefined exception classes, `assert`, `errno`, `<system_error>`, `<stacktrace>` (C++23) and `<debugging>` (C++26).
    - Bugs in the program itself (precondition violations) are reported with assertions or contracts; failures caused by the environment, such as a missing file or a timeout, are reported with exceptions or error codes.
    - Interfaces such as `<filesystem>` usually provide both a version that throws `system_error` and a version that reports through an `error_code&` out-parameter, both sharing the same set of error codes.
    - `throw`, `try`, `std::exception` and contracts aren't in this clause; see [[except]], [[support.exception]] and [[basic.contract]] respectively.

[diagnostics] ¶1 says this clause describes components that C++ programs may use to detect and report error conditions. Table 49 in ¶2 lists six groups:

| Subclause | Header | Problem solved |
|---|---|---|
| [[std.exceptions]] | `<stdexcept>` | A set of predefined exception types, in two branches: logic errors and runtime errors |
| [[assertions]] | `<cassert>` | The `assert` macro, which can be turned off with `NDEBUG` |
| [[errno]] | `<cerrno>` | C- and POSIX-style thread-local error numbers |
| [[syserr]] | `<system_error>` | Wrapping integer error codes from the operating system or low-level APIs in portable, comparable, extensible types |
| [[stacktrace]] {{c++23}} | `<stacktrace>` | Getting the current call stack at run time |
| [[debugging]] {{c++26}} | `<debugging>` | Interacting with a debugger: setting breakpoints, detecting whether a debugger is present |

The other parts of error handling are elsewhere. The language mechanism of exceptions (`throw`, `try`, stack unwinding) is in [[except]]; the `std::exception` base class, `bad_alloc`, `exception_ptr` and `terminate` are in the language support library, [[support.exception]]; `std::expected` is in the general utilities library; and the contract assertions `pre`, `post` and `contract_assert` are in the core language, [[basic.contract]].

## How the work is divided

| Nature of the error | How it is reported |
|---|---|
| A bug in the program itself, such as a precondition violation | `assert`, contract assertions; when the library chooses to check, the `logic_error` branch is thrown |
| A failure caused by the environment, such as a missing file or a timeout | Throw from the `runtime_error` branch or `system_error`; or an `error_code` out-parameter or return value; C and POSIX interfaces use `errno` |
| Locating problems after the fact | `stacktrace` records the call path, and `<debugging>` hands over to the debugger |

The standard doesn't mandate this division, but the library's design reflects it:

- Violating the *Preconditions* of a standard library function is undefined behavior ([[structure.specifications]]) and doesn't throw `logic_error`. C++26 [[g:hardened-implementation|hardened implementations]] turn violations of some hardened preconditions into contract violations. The `logic_error` branch is used where the library actively checks and reports, for example the `out_of_range` thrown by `vector::at`.
- For expected environmental failures, the library often provides both ways. Most operations in `<filesystem>` have two overloads: one throws `filesystem_error` (derived from `system_error`), and one takes an `error_code&` out-parameter and doesn't throw.
- `errno` is a legacy facility for compatibility with C. The components of [[syserr]] don't modify `errno` ([[syserr.general]] ¶2); the two connect through the `errc` enumeration and `generic_category()`.

## Freestanding implementations

[[g:freestanding-implementation|Freestanding implementations]] (implementations that may lack operating system support) must also provide the `E*` macros in `<cerrno>`, the `errc` enumeration in `<system_error>`, and all of `<debugging>`. `errno` itself, `<stdexcept>` (which depends on `std::string`), and `<stacktrace>` are provided only by hosted implementations.

## Changes since C++23

- `<stacktrace>` was added in C++23 ([[P0881R7]]), with formatting support from [[P2693R1]].
- `assert` became a variadic macro in C++26 ([[P2264R7]]), so commas in template arguments no longer need extra parentheses.
- `<debugging>` was added in C++26 ([[P2546R5]]), and `is_debugger_present` was later specified as a replaceable function ([[P2810R4]]).
- The constructors of all exception classes in `<stdexcept>` are `constexpr` in the current draft, to go with C++26 allowing exceptions to be thrown during constant evaluation ([[P3068R6]]).
- `error_code` got a `std::formatter` specialization ([[syserr.fmt]]), which is new wording after C++23.

At the time of writing, Clang 23 + libc++ doesn't yet provide `<stacktrace>` or `<debugging>`, and doesn't support throwing exceptions during constant evaluation.
