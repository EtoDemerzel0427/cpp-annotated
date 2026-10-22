---
title: The floating-point environment
summary: "<cfenv> is a subset of C's <fenv.h>; whether the FENV_ACCESS pragma is supported is implementation-defined, so whether testing exception flags and switching rounding modes actually take effect is implementation-defined too; each thread has its own floating-point environment, and a new thread inherits its creator's environment at the time."
updated: 2026-10-19
---

!!! tldr
    - `<cfenv>` provides functions for reading and writing floating-point exception flags and the rounding mode; it is a subset of C's `<fenv.h>`, without the functions added in C23.
    - The standard does not require implementations to support `#pragma STDC FENV_ACCESS`. So `fesetround` returning success does not guarantee that later operations actually round in the new mode.
    - Constant evaluation does not follow a rounding mode set at run time; C library calls that would raise floating-point exceptions other than inexact are not constant expressions.
    - Each thread has its own floating-point environment. The standard says a new thread inherits its creator's environment at the time; libc++ on macOS does not do this in our tests.

## What the floating-point environment is

```cpp
std::fesetround(FE_UPWARD);
double x = a / b;              // rounded upward? not necessarily
if (std::fetestexcept(FE_INEXACT)) { /* result inexact */ }
```

IEEE 754 specifies a set of **floating-point status**: five exception flags (divide-by-zero, inexact, invalid, overflow, underflow) and several control modes, the most important being the rounding direction. Together these are called the **floating-point environment**. C lets programs read and write them through `<fenv.h>`, and C++'s `<cfenv>` copies that interface.

The problem is the compiler. By default the optimizer assumes the program runs in the default floating-point environment: round to nearest, and nobody cares about the exception flags. Based on that assumption it can compute `1.0 / 3.0` at compile time, delete divisions whose results are unused, and move operations across a `fesetround` call. So both lines above may not work as expected.

## Header contents ([cfenv.syn])

The synopsis declares:

- the exception macros `FE_DIVBYZERO`, `FE_INEXACT`, `FE_INVALID`, `FE_OVERFLOW`, `FE_UNDERFLOW` and `FE_ALL_EXCEPT`;
- the rounding macros `FE_DOWNWARD`, `FE_TONEAREST`, `FE_TOWARDZERO`, `FE_UPWARD`;
- `FE_DFL_ENV` and the types `fenv_t` and `fexcept_t`;
- the exception flag functions `feclearexcept`, `fegetexceptflag`, `feraiseexcept`, `fesetexceptflag`, `fetestexcept`;
- the rounding functions `fegetround`, `fesetround`;
- the whole-environment functions `fegetenv`, `feholdexcept`, `fesetenv`, `feupdateenv`.

The exception and rounding macros are all marked optional: if an implementation does not support some exception or rounding direction, it does not define the corresponding macro.

¶1 The contents and meaning of the header are a subset of C's `<fenv.h>`; only the declarations listed in the synopsis are present. C23's additions `fesetexcept`, `fetestexceptflag`, `femode_t`, `fegetmode`, `fesetmode` and others are not in the synopsis and are not part of `<cfenv>`.

## FENV_ACCESS and implementation-definedness (¶1 Note 1)

C uses `#pragma STDC FENV_ACCESS ON` to tell the compiler that this code will observe or modify the floating-point environment, so the default-environment assumption does not hold here. C++ does not require support for it:

!!! std
    This document does not require an implementation to support the FENV_ACCESS pragma; it is implementation-defined whether the pragma is supported.

Note 1 goes on to draw two conclusions. First, whether these functions can be used to test exception flags, set control modes, or run under non-default modes is all implementation-defined. `fesetround(FE_UPWARD)` returning 0 only says the call itself succeeded. Second, even if the pragma is used to enable control over the floating-point environment, the standard does not specify its effect on floating-point evaluation in constant expressions.

```cpp run title="fenv.cpp" impl
#include <cfenv>
#include <cstdio>

#pragma STDC FENV_ACCESS ON   // whether supported: implementation-defined

int main() {
  std::feclearexcept(FE_ALL_EXCEPT);
  volatile double zero = 0.0;
  double r = 1.0 / zero;          // raises FE_DIVBYZERO, result +inf
  std::printf("%g %d\n", r, std::fetestexcept(FE_DIVBYZERO) != 0);

  std::fesetround(FE_UPWARD);
  volatile double one = 1.0, three = 3.0;
  std::printf("%.17g\n", one / three);   // run time: rounded upward
  constexpr double c = 1.0 / 3.0;        // constant evaluation: unaffected
  std::printf("%.17g\n", c);
}
```

In our tests (Clang 23, arm64 macOS, `-O2`) the output is `inf 1`, `0.33333333333333338`, `0.33333333333333332`. The run-time division rounds upward, while the constant-evaluated result is still rounded to nearest; the two differ by one ulp.

!!! impl "How compilers handle it"
    - Clang recognizes `#pragma STDC FENV_ACCESS ON` and, within its scope, forbids reordering across environment changes and constant folding under the default environment. `-ffp-model=strict` achieves a similar effect for a whole translation unit.
    - GCC has long not supported this pragma; options such as `-frounding-math` and `-ftrapping-math` are generally used instead to control the same kind of assumptions.

### Relation to constant evaluation

[[library.c#3]] says that a call to a C standard library function that would raise a floating-point exception other than `FE_INEXACT` is a [[g:non-constant-library-call|non-constant library call]] and may not appear in a constant expression. The semantics of C library functions during constant evaluation are understood per C Annex F (the IEEE 754 binding).

Combined with Note 1 above, the picture is: compile-time floating-point arithmetic is done in the default environment, and the standard does not promise that it follows a rounding mode set at run time.

## Threads ([cfenv.thread])

¶1 The floating-point environment has thread storage duration ([[basic.stc.thread]]). The initial state of a new thread's floating-point environment is the floating-point environment of the thread that constructs the corresponding `thread` or `jthread` object, at the time of construction. Note 1 puts it more directly: a child thread inherits the floating-point state of its parent at the time the child is created.

¶2 Each thread maintains its own floating-point environment, and each function accesses the environment of the calling thread.

So `fesetround` in one thread does not affect other threads that already exist; a `std::thread` created after it should, per the standard, start with the same rounding mode.

```cpp run title="fenv-thread.cpp" impl
#include <cfenv>
#include <cstdio>
#include <thread>

int main() {
  std::fesetround(FE_UPWARD);
  int child = -1;
  std::thread t([&] { child = std::fegetround(); });   // standard: should equal FE_UPWARD
  t.join();
  std::printf("parent=%d child=%d FE_UPWARD=%d\n",
              std::fegetround(), child, FE_UPWARD);
}
```

!!! warning "libc++ in our tests does not satisfy ¶1"
    On arm64 macOS with Clang 23 + libc++, the parent thread is `FE_UPWARD` and the child thread reads `0` (`FE_TONEAREST`). libc++'s `std::thread` creates the thread directly with pthreads and does not copy the creator's floating-point control state, and new threads on this platform start from the default floating-point environment. To use a non-default mode in a child thread, the portable approach is to set it yourself at the start of the thread function.

## Common misconceptions

!!! pitfall "Assuming fesetround takes effect as soon as it is called"
    Without `FENV_ACCESS` or an equivalent compiler option, the compiler may move operations after `fesetround` to before it, or compute them at compile time with default rounding. The standard classes all of this as implementation-defined. When testing rounding-sensitive code, first confirm that the compiler supports the pragma, then check the behavior after optimization.

!!! pitfall "Changing the environment without restoring it"
    The floating-point environment is thread-level global state. A library function that changes the rounding mode without restoring it affects all of its caller's later computations. The usual approach is to save with `feholdexcept` and restore with `feupdateenv`, or to write an RAII guard that calls `fegetenv` on construction and `fesetenv` on destruction.

## Questions

!!! question "Question 1"
    Under the current draft, can `constexpr double x = std::nextafter(1.0, 2.0);` be a constant expression? What about `constexpr double y = 1e308 * 10;`?

<details markdown="1">
<summary>Answer</summary>

`nextafter` is declared `constexpr` in [[cmath.syn]]. This call raises no exception other than `FE_INEXACT`, so per [[library.c#3]] it is not a non-constant library call, and it can be a constant expression. libc++ in our tests does not yet provide a `constexpr` version, so it actually fails to compile.

`1e308 * 10` is a built-in operation unrelated to the library. The mathematical result exceeds the range of `double` and rounds to `+inf` under IEEE 754. Per [[expr.pre#4]], the result is an infinity the type has, so it is not UB. But [[expr.const.core]] ¶2.9.1 says an arithmetic expression whose operands are all finite and whose result is not finite is not a core constant expression, so the declaration of `y` is ill-formed. Clang 23 in our tests accepts this line; the rule is new wording after C++23 that Clang has not implemented yet.
</details>

## Summary

| Rule | Source | Key point |
|---|---|---|
| `<cfenv>` is a subset of `<fenv.h>` | [cfenv.syn] ¶1 | only the declarations in the synopsis |
| whether `FENV_ACCESS` is supported | ¶1 Note 1 | implementation-defined; so whether testing flags and changing rounding take effect is implementation-defined too |
| constant evaluation | ¶1 Note 1, [[library.c#3]] | does not follow the run-time environment; library calls raising non-inexact exceptions are not constant |
| threads | [cfenv.thread] ¶1–¶2 | one per thread; a child inherits its creator's environment at the time (not done by libc++ in our tests) |
