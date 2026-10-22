---
title: Debugging support
summary: "C++26's <debugging> provides three functions: breakpoint() hands control to the debugger, breakpoint_if_debugging() does so only when a debugger is present, and is_debugger_present() detects a debugger and can be replaced by the program; all three are freestanding and noexcept."
updated: 2026-10-19
---

!!! tldr
    - The semantics of `std::breakpoint()` are implementation-defined; the intent is to halt the program and hand control to the debugger, and when the debugger resumes, the program continues as if it had never been called.
    - Without a debugger, `breakpoint()` may make the program end abnormally, so in everyday code use `std::breakpoint_if_debugging()`.
    - `std::is_debugger_present()` is a replaceable function: the program can supply its own definition, for example to force the debugger branch on in tests.
    - The whole header is freestanding, and all three functions are `noexcept`.
    - libc++ (as tested with Clang 23) has no `<debugging>` yet; in the meantime, use Clang's `__builtin_debugtrap()` or MSVC's `__debugbreak()`.

{{c++26}} Many large projects have their own `DEBUG_BREAK()` macro: on Windows it expands to `__debugbreak()`, on GCC/Clang to `__builtin_debugtrap()`, `raise(SIGTRAP)`, or a piece of inline assembly. It usually comes with a function that detects a debugger: Windows has `IsDebuggerPresent()`, on Linux you read `TracerPid` from `/proc/self/status`, and on macOS you use `sysctl` to check the `P_TRACED` flag. [[P2546R5]] standardized both as `<debugging>`.

## An example

```cpp
#include <cstdio>
#include <cstdlib>
#include <debugging>

[[noreturn]] void fatal(const char* what) {
    std::fprintf(stderr, "fatal: %s\n", what);
    std::breakpoint_if_debugging();   // running under a debugger: stop here and inspect the state
    std::abort();                     // no debugger, or the debugger chose to continue: terminate as usual
}
```

`<debugging>` does no checking of its own; it is an exit point for facilities such as assertions and error handling. Under a debugger, the program stops at the scene of the failure; without one, it does nothing and continues with the error handling that follows. C++26's contract-violation handler ([[basic.contract]]) is another natural place to call it.

Clang 23 with libc++ does not provide `<debugging>` (the `#include` fails with file not found, and `__cpp_lib_debugging` is commented out in `<version>`), so this example has no verdict and was not verified in our tests.

## Overview [debugging.general]

¶1 This subclause describes functionality to introspect and interact with the execution of the program. Note 1 says this functionality interacts with a program that might be tracing the program's execution, such as a debugger.

The abstract machine has no debugger, so almost everything in this subclause is implementation-defined and there is very little normative content. Its value lies in giving a portable name and a clear statement of intent.

```cpp
// all freestanding
namespace std {
  void breakpoint() noexcept;
  void breakpoint_if_debugging() noexcept;
  bool is_debugger_present() noexcept;
}
```

The whole header is freestanding. Embedded development is exactly where stopping at some point and handing control to a debugger connected through a JTAG/SWD probe is needed most.

## `breakpoint()` [debugging.utility]

!!! std
    The semantics of this function are implementation-defined.

¶1 This sentence is the only normative content: the semantics are implementation-defined. The intent is given in Note 1:

- With a debugger present, the program halts and control is handed to the debugger until the debugger either terminates the program or resumes it as if the function had not been called.
- Resuming in any other manner is not intended to be supported.
- Without a debugger, the program may end abnormally.

Resuming "as if it had not been called" is what distinguishes it from `__builtin_trap()`. The compiler treats `__builtin_trap()` as never returning and the code after it as unreachable, so even if the debugger lets the program continue, it cannot resume normally. `breakpoint()` corresponds to a resumable breakpoint trap, which in Clang is `__builtin_debugtrap()`: with Clang 23 on arm64 it compiles to `brk #0xf000`, which LLDB recognizes and lets the program continue past.

May end abnormally without a debugger: on POSIX systems the breakpoint instruction raises `SIGTRAP`, whose default action is to terminate the process. In our tests, running a program that calls `__builtin_debugtrap()` directly ends the process with a Trace/BPT trap.

## `breakpoint_if_debugging()`

¶2 The effect is equivalent to:

```cpp
if (is_debugger_present()) breakpoint();
```

This is the one used most in everyday code: put it in failed assertions, contract violations, and branches that should never be reached; with a debugger, execution stops; without one, it continues.

## `is_debugger_present()`

The specification of this function is split into two parts, which is how the standard library describes replaceable functions ([[structure.specifications]]):

- ¶3 *Required behavior*: no preconditions. This constrains every definition, including a replacement supplied by the program.
- ¶4 *Default behavior*: implementation-defined. This describes only the definition provided by the implementation.

Note 2 states the intent: the implementation should query each time (no caching) and return `true` only when the program is actually being traced by a debugger. On Windows it can call `::IsDebuggerPresent()`; on systems compatible with the Linux Standard Base (ISO/IEC 23360:2021) it can check for a tracer process and, where possible, determine whether that tracer is a debugger. No caching, because a debugger can attach or detach while the program is running.

### Replaceable (¶5)

¶5 specifies that this function is **replaceable** ([[g:replaceable-function]]). As with the global `operator new`, a program can supply a definition with the same signature to take the place of the implementation's version ([[dcl.fct.def.replace]]): it must not be inline and must be attached to the global module. This was added by [[P2810R4]]; uses include:

- the implementation's detection method does not work in some environments, such as custom debug agents, emulators, or embedded probes;
- tests need to force the debugger-present branch on or off;
- some security-sensitive programs want to disable the detection.

```cpp
#include <cstdlib>
#include <debugging>

// replacement definition supplied by the program (only one per program): controlled by an environment variable, handy for testing the debug branch in CI
bool std::is_debugger_present() noexcept {
    return std::getenv("FORCE_DEBUGGER") != nullptr;
}
```

`breakpoint()` and `breakpoint_if_debugging()` are not replaceable.

## Until implementations catch up

`breakpoint()` can be approximated with compiler builtins: Clang's `__builtin_debugtrap()`, MSVC's `__debugbreak()`. `is_debugger_present()` has to be implemented per platform: on Windows call `IsDebuggerPresent()`, on Linux read `TracerPid` from `/proc/self/status`, on macOS use `sysctl` to check the `P_TRACED` flag in `kinfo_proc`.

```cpp run title="debugtrap.cpp" ok
// libc++ (Clang 23) has no <debugging> yet; fall back to the Clang builtin
#if __has_include(<debugging>)
#  include <debugging>
inline void debug_break() noexcept { std::breakpoint(); }
#else
inline void debug_break() noexcept { __builtin_debugtrap(); }   // arm64: brk #0xf000; x86: int3
#endif

int main(int argc, char**) {
    if (argc > 99) debug_break();   // only shows that it compiles; actually calling it without a debugger terminates with SIGTRAP
}
```

## Common misconceptions

!!! pitfall "Calling `breakpoint()` unconditionally"
    Without a debugger, `breakpoint()` may terminate the program outright. A `breakpoint()` left in the code becomes a crash site in CI or in production. You almost always want `breakpoint_if_debugging()`.

!!! pitfall "Treating `is_debugger_present()` as a security mechanism"
    A debugger can fake its state, and the program can replace this function, so anti-debugging checks are easy to bypass. It is a development convenience, not a security boundary.

!!! pitfall "Assuming everything is normal after the debugger continues"
    The intent of Note 1 is to resume as if the function had not been called. But how the compiler treats the surrounding code is up to the implementation; in heavily optimized code, variables you look at at the breakpoint may already have been optimized away.

## Questions

!!! question "Question 1"
    The standard specifies no behavior for `breakpoint()` at all. Why is it still worth standardizing?

<details markdown="1">
<summary>Answer</summary>

The value is a portable name and a stated intent. Every platform and every compiler has its own breakpoint primitive, and projects have to maintain their own layer of macros. The standard provides a uniform spelling and a clear statement of intent (Note 1), and the implementation maps it to the platform primitive. The abstract machine has no debugger, so the standard cannot specify a debugger's behavior; it can only leave it implementation-defined.
</details>

!!! question "Question 2"
    A program supplies `bool std::is_debugger_present() noexcept { return true; }`. What happens when `std::breakpoint_if_debugging()` is called?

<details markdown="1">
<summary>Answer</summary>

`breakpoint_if_debugging()` is equivalent to `if (is_debugger_present()) breakpoint();` ([[debugging.utility#2]]), and it calls the replacement, so `breakpoint()` is always called. If there is no debugger at that point, then per Note 1 the program may end abnormally. A replacement only has to meet the requirement of ¶3 (no preconditions); nothing constrains whether its return value actually reflects the debugger state.
</details>

!!! question "Question 3"
    Why is `<debugging>` freestanding while `<stacktrace>` is not?

<details markdown="1">
<summary>Answer</summary>

Setting a breakpoint and detecting a debugger need only a few instructions or a single system query, with no heap allocation or file system, and embedded environments, working through hardware debug probes, need them most. `<stacktrace>` ([[stacktrace]]) allocates memory, returns `std::string`, and reads debug information, relying on facilities of a hosted environment.
</details>
