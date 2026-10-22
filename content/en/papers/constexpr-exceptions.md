---
title: Exceptions at compile time (P3068)
summary: C++26 lets constant evaluation throw and catch exceptions, as long as the exception object is destroyed within the same evaluation. Why compile-time code used to need two error paths, what the alternatives were, how the wording changes only two items in [expr.const], how the library's exception types followed, and why uncaught_exceptions and current_exception had their constexpr withdrawn again.
tags: constexpr, exceptions, constant evaluation, consteval, C++26, proposal
group: C++26
updated: 2026-10-19
---

!!! tldr
    - Since C++20 a constexpr function may contain a `try` block, but constant evaluation fails as soon as it reaches a `throw`, so the `catch` never runs. Compile-time code either used `throw` as a way to report an error, or wrote a separate error path returning `optional`.
    - [[P3068R6]] allows throwing exceptions during constant evaluation, provided the exception object (together with its implicit copies) is destroyed within the same evaluation. This is the same boundary C++20 drew for dynamic allocation: effects must not escape the evaluation.
    - An uncaught exception makes the whole expression not a constant expression, so existing code that uses `throw` to produce compile errors is unaffected; undefined behavior and other errors did not become exceptions either.
    - The wording changes only a few items in [[expr.const.core]]. The library then marked `std::exception`, the `<stdexcept>` types and others `constexpr` ([[P3378R2]]), and reflection reports errors with `std::meta::exception` ([[P3560R2]]).
    - Making `uncaught_exceptions` and `current_exception` constexpr changes the outcome of trial constant initialization, so [[P3842R2]] withdrew it. Clang 23 does not implement P3068 yet; GCC's status page lists it under GCC 16.

## Error paths in compile-time code

C++20's [[P1002R1]] allowed `try` blocks in constexpr functions but did not change the evaluation rules: as soon as constant evaluation evaluates a *throw-expression*, the whole expression is not a **core constant expression** ([[g:core-constant-expression|core constant expression]], an expression that can be evaluated at compile time). So a `catch` clause never runs at compile time.

This rule has a useful side effect: `throw` can serve as a way to report errors at compile time. The success path evaluates as usual; the failure path fails compilation as soon as it hits `throw`, and the diagnostic points at the line with the `throw`. P3068 mentions that libraries such as fmt and CTHASH use this to improve compile-time error messages.

```cpp title="throw-as-error.cpp" error
#include <string_view>
consteval int parse_digit(std::string_view s) {
  if (s.size() != 1 || s[0] < '0' || s[0] > '9')
    throw "parse_digit: not a single digit";
  return s[0] - '0';
}
static_assert(parse_digit("7") == 7);   // OK
constexpr int bad = parse_digit("x7");  // error: evaluation reaches throw
```

Clang 23 reports `constexpr variable 'bad' must be initialized by a constant expression`, with the note `subexpression not valid in a constant expression` pointing at the `throw` line. Because the diagnostic shows the source line of the `throw`, the string literal in the operand works as an error message.

### No recovery, so write it twice

The trouble starts when the caller wants to handle the error. A `catch` does nothing at compile time, so the caller has to switch to a different function that does not throw. The same parsing logic often ends up written twice:

```cpp title="two-paths.cpp" run ok
#include <optional>
#include <string_view>

constexpr std::optional<int> try_parse(std::string_view s) {
  if (s.empty()) return std::nullopt;
  int v = 0;
  for (char c : s) {
    if (c < '0' || c > '9') return std::nullopt;
    v = v * 10 + (c - '0');
  }
  return v;
}

struct parse_error {};
constexpr int parse(std::string_view s) {
  auto r = try_parse(s);
  if (!r) throw parse_error{};
  return *r;
}

constexpr int port_or(std::string_view s, int dflt) {
  auto r = try_parse(s);      // can't call parse and catch
  return r ? *r : dflt;
}

static_assert(parse("8080") == 8080);
static_assert(port_or("http", 80) == 80);
int main() { return parse("42") == 42 ? 0 : 1; }
```

Clang 23 accepts it and runs it correctly from `-std=c++20` through `-std=c++2c`. `parse` is for run-time callers, `try_parse` for compile-time callers that need to recover, and the two must keep their error conditions in sync. The introduction of P3068 sums this up: without compile-time exceptions, library authors are pushed toward more intrusive error reporting such as `std::expected` and `std::optional`, or toward not handling errors at all.

The standard library has the same problem. Since C++20 `std::vector` can be used in constant evaluation ([[P0784R7]]), but `at()` throws `std::out_of_range` when out of bounds, and a compile-time caller cannot catch it; it can only check the index beforehand.

### Reflection needs to report errors

The third motivation comes from static reflection ([[P2996R13]]). Reflection's query functions are all `consteval`, and many of them can fail, for example calling `members_of` on `int`. P3068 says that in the reflection proposal, throwing an exception is the preferred way to report errors. The trade-offs on the reflection side are covered below and in [[papers/reflection]].

## The design space

A compile-time function has four possible ways to report an error. [[P3560R2]] compared them side by side when choosing an error-reporting mechanism for reflection, and the conclusions apply to constexpr code in general:

| Approach | Problem |
|---|---|
| Return a value meaning "invalid", like floating-point NaN | Only works for some return types; functions returning `vector` or `string_view` have no natural invalid value |
| Return `std::expected<T, E>` | Every caller has to unwrap by hand, with no help from the language |
| Make the expression not a constant expression | The C++23 status quo; the caller cannot recover |
| Throw an exception, catchable within the same evaluation | Needs P3068 |

P3560 points out that before P3068 the fourth option was equivalent to the third, because `throw` itself made the evaluation fail. P3068 separates the two: an uncaught exception still makes the evaluation fail, while a caught exception goes through `catch` as usual.

The usual arguments against exceptions at run time, such as binary size and run-time overhead, do not exist at compile time. On that basis P3560 argues that compilers have no reason to reject compile-time exceptions even in modes where exceptions are disabled.

### What was not proposed

P3068 only makes exceptions produced by `throw` catchable; it does not turn other causes of evaluation failure into exceptions. Core-language undefined behavior such as reading through a null pointer or signed overflow still directly makes the expression non-constant:

```cpp title="ub-not-exception.cpp" error
constexpr int read(const int* p) { return *p; }
constexpr int try_to_ignore_ub() {
  try { return read(nullptr); }
  catch (...) { return 0; }
}
constexpr int v = try_to_ignore_ub();   // error: reads through a null pointer
```

This is the paper's own example; Clang 23 reports `dereferencing a null pointer is not allowed in a constant expression`. If undefined behavior could be swallowed by `catch (...)`, compile-time UB checking would be pointless (¶2.8 of [[expr.const.core#2]]).

### Why exceptions can't leave the evaluation

C++20 allows memory allocation during constant evaluation but requires it to be freed within the same evaluation; this is called **transient allocation** ([[g:transient-allocation|transient allocation]]). The reason is that memory allocated at compile time does not exist in the run-time heap, so the running program cannot keep using a pointer to it.

Exception objects are the same. Throwing an exception initializes an **exception object** ([[g:exception-object|exception object]], [[except.throw#3]]) with dynamic storage duration, whose storage is allocated in an unspecified way ([[except.throw#4]]). P3068 says its wording essentially treats an exception like an allocation: the exception object must be destroyed within the constant evaluation that constructed it and cannot be kept around for run time.

## The final design

### Throwing and catching within an evaluation

```cpp title="catch-at-compile-time.cpp" run std=c++2c
#include <string_view>

struct parse_error { std::string_view input; };

constexpr int parse(std::string_view s) {
  if (s.empty()) throw parse_error{s};
  int v = 0;
  for (char c : s) {
    if (c < '0' || c > '9') throw parse_error{s};
    v = v * 10 + (c - '0');
  }
  return v;
}

constexpr int port_or(std::string_view s, int dflt) {
  try { return parse(s); }
  catch (const parse_error&) { return dflt; }
}

static_assert(parse("8080") == 8080);
static_assert(port_or("http", 80) == 80);  // holds since C++26
int main() { return port_or("x", 0); }
```

Under the C++26 rules, evaluating `port_or("http", 80)` constructs a `parse_error` exception object, which is destroyed once the `catch` has handled it, and the whole expression is a constant expression. One piece of code serves both run time and compile time; `try_parse` is no longer needed.

Clang 23 does not implement P3068 yet and reports `subexpression not valid in a constant expression` for the second `static_assert`, pointing at the `throw` in `parse`, so no verdict is marked here. With that line removed the program compiles, and at run time `port_or("x", 0)` catches the exception normally and returns 0.

### Uncaught exceptions

If an exception propagates all the way out of the evaluation, the exception object is not destroyed within the evaluation, and the expression is not a core constant expression. The result is a compile error just as in C++23; only the reason changes from "evaluation reached `throw`" to "the exception was not caught". P3068 therefore says it does not break existing code: programs that used to compile never reach a `throw` during evaluation, and programs that reach a `throw` never compiled.

The boundary of an evaluation is determined by the constant expression itself, not by an enclosing `try` block. Below, `v` is a constexpr variable, and its initializer is a separate constant evaluation:

```cpp title="separate-evaluation.cpp" error
struct my_exception {};
constexpr int just_error() { throw my_exception{}; }

constexpr int foo() {
  try {
    constexpr int v = just_error();  // error: the exception escapes v's initialization
    return v;
  } catch (my_exception) { return 0; }
}
```

The outer `catch` cannot help, at compile time or at run time; the initialization of `v` must itself be a constant expression. Remove the `constexpr` and `auto v = just_error();` becomes part of the evaluation of `foo`, so the exception can be caught by that same `catch`. The example is adapted from the paper. Clang 23 rejects it as well, but because it does not allow `throw` at all.

!!! pitfall "An immediate invocation is also a separate evaluation"
    Calling a `consteval` function is an **immediate invocation** ([[g:immediate-invocation|immediate invocation]]). If it is not a constant expression, it is an immediate-escalating expression, which may only appear in a function that can be escalated to `consteval` (¶2.2 and ¶3 of [[expr.const.imm#2]]); in an ordinary function the program is ill-formed. So an exception thrown by a `consteval` function can only be caught inside that immediate invocation. Writing `try { auto x = f_consteval(bad); } catch (...) {}` in run-time code does not make the program compile: the exception escapes the immediate invocation, so the invocation is not a constant expression.

### exception_ptr and implicit copies

`std::exception_ptr` can extend the lifetime of an exception object: as long as some `exception_ptr` still refers to it, it is not destroyed (¶4.2 of [[except.throw#4]]). `std::rethrow_exception` may also make a copy before throwing ([[propagation#11]]). The wording therefore requires both the exception object and these implicit copies to be destroyed within the evaluation:

<div class="compare" markdown="1">

```cpp title="Used up within the evaluation: allowed"
#include <exception>
constexpr int f() {
  auto p = std::make_exception_ptr(42);
  try {
    std::rethrow_exception(p);
  } catch (int i) {
    return i;
  }
}
static_assert(f() == 42);
```

```cpp title="Escapes the evaluation: not allowed" error
#include <exception>
constexpr std::exception_ptr p =
  std::make_exception_ptr(42);
// error: the exception object is
// still referenced by p afterwards
```

</div>

The effect of `make_exception_ptr` is as if by `throw e;` followed by obtaining the current exception in a `catch (...)` ([[propagation#12]]), so it constructs an exception object too. Under the C++26 rules the left side is a constant expression; libc++'s `make_exception_ptr` is not constexpr, so the left side does not compile with Clang 23 and no verdict is marked. Clang 23 rejects the right side too, but because libc++'s `exception_ptr` is not a literal type, not because of ¶2.24.

### throw; and expressions that the language makes throw

`throw;` without an operand rethrows the exception currently being handled ([[expr.throw#3]]). After P3068 a loophole appeared: constant evaluation can happen inside a run-time `catch` clause, where the exception currently being handled is a run-time one. [[CWG3059]] gives this example:

```cpp title="cwg3059.cpp" error
int main() {
  try {
    throw 0;
  } catch (...) {
    constexpr int x = [] {
      try { throw; }          // error: the current exception was not constructed in this evaluation
      catch (...) { return 1; }
    }();
    return x;
  }
}
```

CWG3059, as a defect report, added a restriction: `throw;` may only rethrow an exception constructed in the current evaluation. Clang 23 rejects this code, but again because it does not allow any `throw`.

The language itself also throws exceptions: a failed `dynamic_cast` to a reference throws `std::bad_cast`, `typeid` applied to a dereferenced null pointer throws `std::bad_typeid`, and an array *new-expression* with an invalid length throws `std::bad_array_new_length`. Before P3068, a `dynamic_cast` or `typeid` that would throw was listed as non-constant outright; afterwards they can throw at compile time and be caught, provided the definition of the exception type is reachable, for example by including `<typeinfo>` or `<new>`.

## Wording changes

All core-language changes are in the list of prohibitions in [[expr.const.core#2]]; the [except] clause was not touched: the rules for throwing, propagating and catching apply unchanged during constant evaluation.

One old item was removed: a *throw-expression* ([expr.throw]). A new ¶2.24 was added:

!!! std
    a construction of an exception object, unless the exception object and all of its implicit copies created by invocations of std::current_exception or std::rethrow_exception ([propagation]) are destroyed within the evaluation of E;
    
    Constructing an exception object is not allowed unless the exception object and all implicit copies produced by `current_exception` and `rethrow_exception` are destroyed within the evaluation of E.

¶2.20 through ¶2.23 use the same sentence pattern for *new-expression*s, `delete` and `std::allocator`: allocated within the evaluation of E, and also deallocated within the evaluation of E.

Two more items:

- ¶2.25 comes from [[CWG3059]]: a *throw-expression* with no operand is not allowed unless the exception object of the currently handled exception was constructed during the evaluation of E.
- ¶2.30 dropped "or that would throw an exception" from the old item about `dynamic_cast` and `typeid`; the new ¶2.31 only prohibits a `dynamic_cast`, `typeid` or *new-expression* that would throw when the definition of the exception type is not reachable.

These items are explained one by one in the section on exceptions in [[expr.const.core]]. The full story of how constant evaluation was gradually relaxed from C++11 to C++26 is in [[history/constexpr]].

### The library's exception types

The type of the exception object must also be constructible and destructible during constant evaluation. P3068's own library wording marks the types in `<exception>`, `<new>` and `<typeinfo>` constexpr: the constructors, destructor and `what()` of `std::exception` ([[exception]]), and `what()` of `bad_alloc`, `bad_array_new_length`, `bad_cast`, `bad_typeid` and `bad_exception`. [[exception#5]] also specifies that during constant evaluation the string returned by `what()` uses the ordinary literal encoding, so that the compiler can show it in diagnostics.

The `<stdexcept>` part was added by [[P3378R2]]: `logic_error`, `runtime_error` and their seven derived classes, along with `bad_optional_access`, `bad_variant_access`, `bad_expected_access` and `format_error`, have all their members made constexpr ([[std.exceptions]]). The paper's argument is direct: `vector::at` can already be called at compile time, so the `out_of_range` it throws should be constructible and catchable at compile time too. The paper also recommends that from now on, every proposal that makes a library component constexpr should make the related exception types constexpr along with it.

```cpp title="vector-at.cpp" run std=c++2c
#include <stdexcept>
#include <vector>

constexpr int third_or(const std::vector<int>& v, int dflt) {
  try { return v.at(2); }
  catch (const std::out_of_range&) { return dflt; }
}
static_assert(third_or({1, 2, 3}, 0) == 3);
static_assert(third_or({1, 2}, 0) == 0);   // holds since C++26
int main() {}
```

In libc++, `__throw_out_of_range`, which `vector::at` calls when out of bounds, is not constexpr, and Clang 23 reports `non-constexpr function '__throw_out_of_range' cannot be used in a constant expression` for the second `static_assert`. In our tests, libc++'s `std::exception` and `std::out_of_range` constructors are not constexpr either.

P3378 records the implementation obstacles. Taking libc++ as an example: `what()` and the destructors of most exception types are defined in `.cpp` files and must move into headers, while the existing symbols in the shared library must be kept to preserve ABI; `logic_error` internally uses a reference-counted string built on `reinterpret_cast` and atomic operations, so during constant evaluation it has to copy the string every time instead.

[[P3295R3]] originally also contained constexpr `<stdexcept>` material; its subject is making `vector`, `string` and these exception types usable at compile time in freestanding implementations. R3 dropped that part on the grounds that it had already gone into the standard.

## Aftermath: uncaught_exceptions and current_exception withdrawn

P3068 marked nearly every function in `<exception>` constexpr, including `std::uncaught_exceptions()` and `std::current_exception()`. At run time these two functions read global state of the current thread; during constant evaluation they can only see exceptions inside the current evaluation. [[P3820R1]] points out that this difference silently changes the behavior of existing programs:

```cpp title="trial-evaluation.cpp" run ok
#include <exception>
int i = 1;

int main() {
  try {
    struct S {
      ~S() {
        const int x = std::uncaught_exceptions();
        i = x;
      }
    };
    S s;
    throw 0;
  } catch (...) {
    const bool b = (std::current_exception() != nullptr);
    return i + b;
  }
}
```

`x` and `b` are both const integral variables, which makes them **potentially-constant** ([[g:potentially-constant|potentially-constant]]) variables. The compiler first tries to evaluate their initializers as constant expressions, and if that succeeds they are constant-initialized ([[expr.const.init#5]]); in that case the initializer is manifestly constant-evaluated (¶1.6 of [[expr.const.defns#1]]). If these two functions were constexpr, the trial evaluation would succeed: inside the constant evaluation there is no uncaught exception and no exception being handled, so `x` would be 0, `b` would be `false`, and the program would return 0. In C++23 the trial evaluation fails, the variables are initialized at run time, and the program returns 2.

The two papers proposed different fixes:

- P3820 proposed removing constexpr from `uncaught_exceptions` and adding a separate `consteval` version that only counts the current constant evaluation; `current_exception` would only be constant when the current exception was thrown in the current evaluation.
- [[P3842R2]] took the conservative route: simply remove constexpr from these two functions, and from `nested_exception`, `throw_with_nested` and `rethrow_if_nested`, leaving compile-time support to be designed for C++29.

The current draft adopted P3842. In [[exception.syn]], `uncaught_exceptions` and `current_exception` are no longer constexpr; `make_exception_ptr` is still constexpr, and its specification now uses an exposition-only constexpr function *current-exception* ([[propagation#12]]). Clang 23 runs the program above and returns 2, consistent with the current draft.

## std::meta::exception in reflection

After P3068 went into the standard, [[P3560R2]] changed the failure of reflection queries from "not a constant expression" to throwing `std::meta::exception` ([[meta.reflection.exception#1]]). It is a single exception type rather than a hierarchy, recording an error message, the function that failed (as a reflection, `from()`), and the call location `where()`. It derives from `std::exception`; P3560's reason is consistency with the other standard exceptions, some of which are also used at compile time.

```cpp title="meta-exception.cpp" std=c++2c
#include <meta>

consteval bool has_members(std::meta::info r) {
  try {
    (void)members_of(r, std::meta::access_context::current());
    return true;
  } catch (const std::meta::exception&) {
    return false;
  }
}
static_assert(!has_members(^^int));
```

`int` is neither a class type nor a namespace, so by [[meta.reflection.member.queries#5]] `members_of` throws `meta::exception`, which `has_members` catches. Clang 23 has neither the `<meta>` header nor an implementation of reflection, so this example has not been compiled. Why the error message is provided in both UTF-8 and the ordinary encoding, and why a failed `define_aggregate` is still unrecoverable, is covered in [[papers/reflection]].

## Compiler support

| Item | Clang 23.1.3 / libc++ (tested) | Others |
|---|---|---|
| Throwing and catching during constant evaluation (P3068) | Not implemented; reaching `throw` gives `subexpression not valid in a constant expression` | Clang's status page says No; GCC's status page lists P3068 under GCC 16 (not verified here) |
| `__cpp_constexpr_exceptions` | Not defined | `202411L` in the current draft |
| constexpr exception types (library part of P3068, P3378) | The constructors of `std::exception`, `bad_alloc` and `out_of_range` are not constexpr | `__cpp_lib_constexpr_exceptions` is `202502L` in the current draft; not defined in our tests |
| Reflection and `std::meta::exception` | No `<meta>` | GCC's status page lists P2996 and P3560 under GCC 16, requiring `-freflection` (not verified here) |

!!! impl "With exceptions disabled"
    The standard has no mode with exceptions disabled, but `-fno-exceptions` is widely used. Under `-fno-exceptions`, Clang 23 reports `cannot use 'throw' with exceptions disabled` for any `throw`, constexpr functions included. P3560 argues that compile-time exceptions do not affect generated code and there is no reason to forbid them in this mode; whether implementations will make that distinction can only be observed once they implement P3068.

## Questions

!!! question "1. One function, two versions"
    What happens to the two `static_assert`s below in C++23 and in C++26?
    
    ```cpp
    constexpr int f(bool b) {
      try {
        if (b) throw 1;
        return 0;
      } catch (int) {
        return 1;
      }
    }
    static_assert(f(false) == 0);
    static_assert(f(true) == 1);
    ```

<details markdown="1">
<summary>Answer</summary>

In C++23 the first holds: since C++20 a `try` block may appear in a constexpr function ([[P1002R1]]), and as long as evaluation does not go through a `throw` there is no problem. The second is not a constant expression, because evaluation reaches a *throw-expression*. In C++26 both hold: the exception object is destroyed when the `catch` finishes, which satisfies ¶2.24 of [[expr.const.core#2]]. Clang 23 rejects only the second under both `-std=c++20` and `-std=c++2c`, which is the C++23 behavior.

</details>

!!! question "2. After a rethrow"
    ```cpp
    constexpr int g() {
      try { throw 1; }
      catch (...) { throw; }
    }
    static_assert(g() == 1);
    ```
    Is `throw;` allowed during constant evaluation? Does this `static_assert` hold?

<details markdown="1">
<summary>Answer</summary>

`throw;` itself is allowed: the exception being handled was constructed in the current evaluation, which satisfies ¶2.25. But the rethrown exception is not caught by any `catch` and propagates out of the evaluation, so the exception object is not destroyed within the evaluation, violating ¶2.24. So `g()` is not a constant expression and the `static_assert` is ill-formed. `throw;` creates no new exception object; it just lets the same object continue to propagate ([[expr.throw#3]]).

</details>
