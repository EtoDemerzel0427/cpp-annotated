---
title: Assertions
summary: "The assert macro of <cassert>: what NDEBUG makes it expand to, printing a diagnostic and calling abort on failure, being a variadic macro since C++26, being redefined according to the current NDEBUG on every inclusion, how it works during constant evaluation, and how it differs from contract_assert."
updated: 2026-10-19
---

!!! tldr
    - If `NDEBUG` is defined where `<cassert>` is included, `assert(...)` expands to `((void)0)` and the argument isn't evaluated at all; otherwise the argument is evaluated, and if it is false a diagnostic is written to standard error and `abort()` is called.
    - Since C++26 `assert` is a variadic macro, so `assert(std::is_same_v<int, int>)` no longer needs extra parentheses; but the argument must be a single assignment-expression, and `assert(x, "msg")` is ill-formed.
    - Every inclusion of `<cassert>` redefines `assert` according to the `NDEBUG` in effect at that point, so assertions can be switched on and off locally within a file.
    - `assert` can be used in `constexpr` functions: a true condition doesn't get in the way of constant evaluation, and a false one is a compile-time error.
    - Compiling the same inline function with different `NDEBUG` settings in different translation units violates the ODR. C++26's `contract_assert` doesn't have this problem.

## What happens on failure

```cpp run title="assert-fail.cpp" ok
#include <cassert>

int main() {
  int balance = -5;
  assert(balance >= 0 && "balance must be non-negative");
}
```

On macOS, running it prints

```text
Assertion failed: (balance >= 0 && "balance must be non-negative"), function main, file assert-fail.cpp, line 5.
```

and the process then terminates with `SIGABRT`. `&& "explanatory text"` is an old idiom: a string literal converted to `bool` is always true, so it doesn't affect the result, but it shows up in the printed expression text.

[assertions.general] ¶1 says `<cassert>` provides a macro for documenting C++ program assertions and a mechanism for disabling the assertion checks by defining the macro `NDEBUG`. An assertion is documentation first: it writes the programmer's assumptions about program state in executable form.

## Two definitions ([assertions.assert])

¶1 If `NDEBUG` is defined as a macro name at the point in the source file where `<cassert>` is included, `assert` is defined as

```cpp
#define assert(...) ((void)0)
```

The argument disappears during preprocessing and isn't evaluated at all. In a build with `NDEBUG` defined, `assert(init_subsystem())` means the subsystem is never initialized.

¶2 Otherwise, `assert` expands to an expression of type `void` with the following effects:

- ¶2.1 `__VA_ARGS__` is evaluated and [[g:contextually-converted-to-bool|contextually converted to `bool`]];
- ¶2.2 if the result is `true`, there are no further effects;
- ¶2.3 otherwise, a diagnostic in an implementation-defined format is written to the standard error stream and `abort()` is called. The diagnostic contains `#__VA_ARGS__` (the source text of the argument) and the source file name, line number and enclosing function name, the information `source_location::current()` can provide.

It calls `abort()`, not `exit()`: functions registered with `atexit` aren't run, static objects aren't destroyed, whether C stream buffers are flushed is implementation-defined ([[support.start.term]]), and usually a core dump is produced. A failed assertion means the program state can no longer be trusted; running cleanup code at that point could do more damage, while a core dump preserves the scene.

## Commas in the argument (¶3){{c++26}}

Before C++26, `assert` had a single macro parameter. The preprocessor recognizes only parentheses, not angle brackets or braces, so

```cpp
assert(std::is_same_v<int, int>);    // C++23: the preprocessor sees two macro arguments
assert(std::pair{1, 2} == p);        // the same problem
assert((std::is_same_v<int, int>));  // the traditional workaround: another pair of parentheses
```

C++26 changed it to `assert(...)` ([[P2264R7]], consistent with C23), so `__VA_ARGS__` takes all the commas. This brings a new problem: someone might imitate `static_assert` and write `assert(x, "message")`. That now gets through preprocessing and expands to a comma expression whose condition is always the `true` converted from the string literal, so the assertion can never fail. ¶3 closes this loophole:

!!! std
    If `__VA_ARGS__` does not expand to a well-formed *assignment-expression*, the program is ill-formed.

*assignment-expression* is the grammar production one level below *expression*, and it contains no top-level comma operator ([[expr.comma]]). So `assert(x, "msg")` is ill-formed, while `assert(std::is_same_v<int, int>)` is valid, because the comma in a template argument list isn't a comma operator.

The second sentence of ¶3 says that if the assignment-expression would be ill-formed when treated as an unevaluated operand, the program is {{ifndr}}. This leaves implementations a way to check: putting the argument into an unevaluated context such as `sizeof` or `decltype` checks whether it is a single assignment-expression. `co_await` and `co_yield` can't appear in unevaluated operands ([[expr.await]], [[expr.yield]]), so a form like `assert(co_await f())` is made IFNDR, and implementations need no special handling.

!!! warning "Implementation status"
    libc++'s `<cassert>` uses the platform C library's `<assert.h>` directly, so the form of `assert` is decided by the C library. The macOS SDK still defines the single-parameter `assert(e)`, so `assert(std::is_same_v<int, int>)` gives "too many arguments provided to function-like macro invocation" there. By the standard it is valid; the platform hasn't caught up yet.

!!! lawyer "How ¶3 is enforced when `NDEBUG` is defined"
    ¶3 doesn't distinguish whether `NDEBUG` is defined. But ¶1 says that in that case the macro expands to exactly `((void)0)`, and the argument is discarded during preprocessing, so the implementation has no way to check whether `assert(x, "msg")` is a single assignment-expression. In practice, implementations can diagnose this kind of error only when `NDEBUG` isn't defined.

## Redefined on every inclusion (¶4)

¶4 The `assert` macro is redefined according to the current state of `NDEBUG` each time `<cassert>` is included. So `<cassert>` has no include guard, as the standard specifies. This allows assertions to be switched on and off locally within a translation unit:

```cpp run title="ndebug-toggle.cpp" ok
#define NDEBUG
#include <cassert>
void hot_path([[maybe_unused]] int x) {
  assert(x > 0);    // this assert is disabled
}

#undef NDEBUG
#include <cassert>
int main() {
  hot_path(-1);     // doesn't fire
  assert(true);     // this assert is active
}
```

## `assert` during constant evaluation (¶5)

```cpp run title="constexpr-assert.cpp" ok
#include <cassert>

constexpr int checked_div(int a, int b) {
  assert(b != 0);
  return a / b;
}
static_assert(checked_div(6, 3) == 2);
// constexpr int bad = checked_div(1, 0);   // compile error

int main() { return checked_div(4, 2) - 2; }
```

¶5 says the expression `assert(E)` is a [[g:constant-subexpression|constant subexpression]] if either:

- ¶5.1 `NDEBUG` is defined at the point where `assert` was last defined or redefined; or
- ¶5.2 `E` contextually converted to `bool` is a constant subexpression that evaluates to `true`.

So `assert` can go into `constexpr` functions. When the condition is true it doesn't get in the way of constant evaluation; when it is false, `abort()` would have to be called, which isn't a constant expression, so it is a compile-time error. Uncomment the line above and Clang reports that `bad` must be initialized by a constant expression, with the note "assertion failed during evaluation of constant expression". The same check is a hard error at compile time and an `abort` at run time.

## Differences from contract assertions and `[[assume]]`

C++26's contract assertions comprise `pre` and `post` on functions and the statement `contract_assert` ([[stmt.contract.assert]]). They can be seen as assertions built into the language that fix the various problems of `assert`:

| | `assert` | `contract_assert` |
|---|---|---|
| What it is | A macro | A statement |
| How it is switched | `NDEBUG` at each inclusion point | Implementation-defined evaluation semantics: ignore, observe, enforce, quick-enforce ([[basic.contract.eval]]) |
| On failure | Prints a diagnostic, calls `abort()` | Depends on the semantic: observe and enforce call the replaceable contract-violation handler, and enforce and quick-enforce terminate the program |
| Commas in the argument | Needs parentheses before C++26 | No problem |
| Different settings in different translation units | May violate the ODR | Explicitly allowed |

The last row needs explaining. If an inline function in a header uses `assert`, and one translation unit defines `NDEBUG` while another doesn't, the function's token sequence after preprocessing differs between the two translation units, violating the one-definition rule ([[basic.def.odr]]), and the program is {{ifndr}}. The linker keeps one version arbitrarily, with the result that some assertions may still be active in a release build, or some may have no effect in a debug build. Each evaluation of a contract assertion may use a different semantic, so they don't have this problem.

`[[assume]]` ([[dcl.attr.assume]]) is the exact opposite. It tells the compiler the condition holds and may be used for optimization; a false condition is undefined behavior, and it is never checked. `assert` checks when enabled and does nothing when disabled, and never lets the compiler optimize based on it.

At the time of writing, Clang 23 doesn't support `contract_assert` yet.

## Common misconceptions

!!! pitfall "Side effects in the argument"
    `assert(fd = open(path))` and `assert(++count < limit)` vanish entirely in a build with `NDEBUG` defined. The argument of an assertion should be a condition without side effects.

!!! pitfall "Checking external input with `assert`"
    Errors in user input, file contents or network data are runtime errors, not bugs. With assertions disabled, all these checks disappear. External input should go through ordinary error handling, such as returning an error code or throwing an exception.

!!! pitfall "Inconsistent `NDEBUG` across translation units"
    If inline functions, templates or `constexpr` functions in headers use `assert`, and translation units are compiled with different `NDEBUG` settings, that is an IFNDR ODR violation. The whole program should use a uniform `NDEBUG` setting.

## Questions

!!! question "Questions"
    1. Is `assert((x, y))` (with double parentheses) well-formed in C++26? What does it check?
    2. If an assertion fails during static initialization before `main`, does `abort()` run the destructors of the static objects already constructed?
    3. When `NDEBUG` is defined, which item of ¶5 makes `assert(E)` in a `constexpr` function a constant subexpression?

<details markdown="1">
<summary>Answer</summary>

1. Well-formed. `(x, y)` is a parenthesized expression, which is an *assignment-expression*, and a comma expression may appear inside the parentheses. It checks `y`; `x` is evaluated and discarded. ¶3 can't stop this kind of deliberate workaround.
2. No. `abort()` doesn't run functions registered with `atexit` and doesn't destroy objects with static storage duration ([[support.start.term]]).
3. ¶5.1. `NDEBUG` was defined where `assert` was last defined, so `assert(E)` expands to `((void)0)`, which is always a constant subexpression. When `NDEBUG` isn't defined, ¶5.2 guarantees that an `assert` with a true condition doesn't get in the way of constant evaluation either. Together, the two items mean `assert` can safely be written in any `constexpr` function.
</details>
