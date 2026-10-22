---
title: Immediate functions
summary: "Calls to consteval functions must complete at compile time; what immediate invocations and immediate function contexts are, and when constexpr templates, lambdas and defaulted functions are automatically escalated to immediate functions."
updated: 2026-10-19
---

!!! tldr
    - A function declared `consteval` is an immediate function. A call to it outside an immediate function context is an immediate invocation, which must be a constant expression.
    - There are three immediate function contexts: inside the body of an immediate function, inside a manifestly constant-evaluated expression, and inside the first branch of `if consteval`. A consteval function called in these places may receive non-constant arguments.
    - Since C++23, specializations of constexpr function templates, lambda call operators and compiler-generated defaulted functions are automatically escalated to immediate functions if they contain a non-constant consteval call. A hand-written ordinary constexpr function is not escalated; writing that is simply ill-formed.
    - consteval calls in default arguments and default member initializers count at the place where they are used.
    - Since C++26, a pointer to a consteval function can be stored in a constexpr variable, but cannot enter a run-time object. Clang 23 doesn't implement this yet.

## Functions that can only be called at compile time

```cpp
consteval int sq(int n) { return n * n; }

int x = sq(3);       // OK: 9 is computed at compile time
int rt = 3;
int y = sq(rt);      // error: the call is not a constant expression
```

A `constexpr` function can be called at compile time or at run time. A `consteval` function can only be called at compile time. A function declared with `consteval` is called an **immediate function** ([[g:immediate-function|immediate function]]).

A call to an immediate function that is not in an immediate function context (covered in the next section) is called an **immediate invocation** ([[g:immediate-invocation|immediate invocation]]). An immediate invocation is manifestly constant-evaluated ([[expr.const.defns#1]]) and must be a constant expression; its result is computed during translation and embedded directly in the program. `sq(rt)` reads the non-constant `rt`, so it is not a constant expression, and the program is ill-formed.

An immediate function never executes at run time, so the compiler generates no machine code for it, and there is no symbol for it in the object file.

### Why consteval is needed

C++20 introduced `consteval` ([[P1073R3]]) mainly for two purposes.

The first is guaranteed compile-time evaluation, which `constexpr` doesn't provide. Some functions exist precisely to perform compile-time checks, such as validating format strings, and calling them at run time ought to be a compile error. The format string check in `std::format` works this way: the constructor of `std::basic_format_string` is consteval, so the format string is parsed at compile time ([[P2216R3]], merged into C++20 as a defect fix).

```cpp run error
#include <format>
#include <string>
std::string a = std::format("{} + {}", 1, 2);  // OK
std::string b = std::format("{:d}", "str");    // error: d doesn't apply to strings
```

The second is to give purely compile-time utility functions a home. C++26's reflection API (`std::meta::*`) consists entirely of consteval functions ([[P2996R13]]), because reflection values are meaningful only at compile time.

## Immediate function contexts (¶1)

consteval functions need to be able to call each other. `quad` below passes its own parameter to `sq`; the parameter `n` is not a constant, yet the call is valid:

```cpp run ok
consteval int sq(int n) { return n * n; }
consteval int quad(int n) { return sq(sq(n)); }  // OK
static_assert(quad(2) == 16);
int main() {}
```

¶1 A potentially-evaluated expression or conversion is in an **immediate function context** ([[g:immediate-function-context|immediate function context]]) if any of the following holds:

- ¶1.1 its innermost enclosing non-block scope is the function parameter scope of an immediate function, i.e. it is written in the body of an immediate function;
- ¶1.2 it is a subexpression of a manifestly constant-evaluated expression or conversion, such as the initializer of a constexpr variable, a template argument, or the condition of a `static_assert`;
- ¶1.3 its enclosing statement is enclosed by the compound statement of a consteval if statement (`if consteval { … }`).

Calling an immediate function in an immediate function context is not an immediate invocation, and need not itself be a constant expression. That is because the enclosing context already guarantees compile-time evaluation: `quad` executes only when it is immediately invoked, and by then `n` has a determined value. The check for constancy is deferred to the outermost immediate invocation.

## if consteval

The statement in ¶1.3 is C++23's `if consteval` ([[P1938R3]]; rules in [[stmt.if#4]]–[[stmt.if#6]]). It executes the first branch in a manifestly constant-evaluated context, and the `else` branch otherwise. Both branches must be compound statements.

The first branch is an immediate function context, so non-constant arguments can be passed to consteval functions there. `std::is_constant_evaluated()` can't do that:

<div class="compare" markdown="1">

```cpp run error
#include <type_traits>
consteval int sq(int n) { return n*n; }

constexpr int bad(int n) {
  if (std::is_constant_evaluated())
    return sq(n);  // error
  return n * n;
}
```

```cpp run ok
consteval int sq(int n) { return n*n; }

constexpr int good(int n) {
  if consteval {
    return sq(n);  // OK
  } else {
    return n * n;
  }
}
```

</div>

On the left, the ordinary condition of `if` establishes no context, `sq(n)` is an immediate invocation, and `n` is not a constant, so the compiler reports an error at the definition. On the right, `sq(n)` is in an immediate function context and is just an ordinary call, evaluated along with `good` when `good` is constant-evaluated.

`std::is_constant_evaluated()` itself is specified in terms of `if consteval`: it is equivalent to `if consteval { return true; } else { return false; }` ([[meta.const.eval#1]]).

!!! pitfall "`if constexpr (std::is_constant_evaluated())` is always true"
    The condition of `if constexpr` is manifestly constant-evaluated, so `is_constant_evaluated()` always returns `true` there, and the run-time branch is discarded. Clang warns about this with `-Wconstant-evaluated`. To distinguish compile time from run time, use `if consteval` or an ordinary `if (std::is_constant_evaluated())`.

## Immediate escalation (¶2–¶4)

### The C++20 problem: generic code couldn't forward consteval calls

```cpp
consteval int sq(int n) { return n * n; }

template<class T>
constexpr int tf(T n) { return sq(n); }
```

`sq(n)` in `tf<int>` is not in an immediate function context, and `n` is not a constant. Under the original C++20 rules this was an error. As a result, constexpr forwarding templates such as `std::invoke` and the ranges algorithms couldn't accept consteval callables. C++23's [[P2564R3]] (a defect fix that applies to C++20 too) solved this by making `tf<int>` automatically become an immediate function.

```cpp
consteval int sq(int n) { return n * n; }

constexpr int cf(int n) { return sq(n); }  // error: cf is not escalated

template<class T>
constexpr int tf(T n) { return sq(n); }    // OK: tf<int> is escalated to an immediate function
int t1 = tf(4);                            // OK: an immediate invocation that is a constant
int rt = 3;
int t2 = tf(rt);                           // error: the immediate invocation tf(rt) is not a constant

auto lam = [](int n) { return sq(n); };    // OK: the lambda's call operator is escalated
int l1 = lam(2);                           // OK
```

After escalation, every call to `tf<int>` is an immediate invocation, and the check moves to the call site: `tf(4)` is a constant, so it is valid; `tf(rt)` isn't, so it is ill-formed.

### Three definitions

¶2 A potentially-evaluated expression or conversion is **immediate-escalating** ([[g:immediate-escalating|immediate-escalating]]) if it is neither initially in an immediate function context nor a subexpression of an immediate invocation, and either:

- ¶2.1 it is an immediate constant expression, i.e. a constant expression whose result refers to an immediate function or immediate object ([[expr.const.const#5]]); or
- ¶2.2 it is an immediate invocation that is not a constant expression.

Both cases say the same thing: something that can exist only at compile time appears here, and this position is not guaranteed to be evaluated at compile time. The word "initially" breaks a cycle: whether an expression is in an immediate function context depends on whether the enclosing function is an immediate function, and whether the function escalates depends on whether it contains immediate-escalating expressions, so the check uses the state before escalation.

¶3 The following three kinds of functions are **immediate-escalating functions**:

- ¶3.1 the function call operator of a lambda not declared `consteval`;
- ¶3.2 a defaulted function that is not user-provided and not declared `consteval`, such as an implicitly-declared default constructor or a `= default` comparison operator;
- ¶3.3 a function instantiated from a templated entity declared with `constexpr`, other than a prospective destructor. Specializations of function templates and constexpr member functions of class templates fall into this category.

!!! std
    An immediate-escalating expression shall appear only in an immediate-escalating function.

An immediate-escalating expression may appear only in an immediate-escalating function. `cf` in the example above is a hand-written ordinary constexpr function, which belongs to none of the three kinds, so it is ill-formed.

¶4 An **immediate function** is a function declared with `consteval` (¶4.1), or an immediate-escalating function F whose function body contains an immediate-escalating expression whose innermost enclosing non-block scope is F's function parameter scope (¶4.2).

The innermost-scope requirement excludes nested lambdas: an immediate-escalating expression in a lambda body escalates only the lambda's call operator, not the enclosing function.

### Why only these three kinds escalate

These three kinds of functions have one thing in common: the programmer can't, or can't conveniently, write `consteval` at the declaration.

- Different specializations of the same template may or may not need consteval, depending on the template arguments (see `f<char>` and `f<int>` in the standard's example below).
- Hardly anyone writes `consteval` on a lambda, and a generic lambda is itself a template.
- Compiler-generated constructors and comparison operators have nowhere to write `consteval`, yet they may call consteval functions of members.

A hand-written ordinary constexpr function is a single entity. If it needs to call a consteval function with non-constant arguments, it should be written as `consteval` explicitly, or the call should go into `if consteval`; the standard doesn't decide for the programmer.

### The standard's example (¶5)

```cpp
consteval int id(int i) { return i; }
constexpr char id(char c) { return c; }

template<class T>
constexpr int f(T t) { return t + id(t); }

auto a = &f<char>;           // OK: f<char> calls the constexpr id(char)
auto b = &f<int>;            // error: f<int> is an immediate function, its address cannot be taken
static_assert(f(3) == 6);    // OK

template<class T>
constexpr int g(T t) {       // g<int> is not an immediate function:
  return t + id(42);         // id(42) is already a constant
}
```

From the same template, `f<char>` is an ordinary constexpr function while `f<int>` is an immediate function. That is exactly why escalation can only be decided specialization by specialization. Clang's diagnostic adds a note with the reason: "'f<int>' is an immediate function because its body contains a call to a consteval function 'id' and that call is not a constant expression".

```cpp run ok
template<class T, class F>
constexpr bool is_not(T t, F f) { return not f(t); }

consteval bool is_even(int i) { return i % 2 == 0; }

static_assert(is_not(5, is_even));   // OK
int main() {}
```

Passing a consteval function as a function pointer to an ordinary generic function is valid too:

- The argument `is_even` refers to an immediate function and is an immediate constant expression. But it is in the condition of a `static_assert`, an immediate function context (¶1.2), so it is not an immediate-escalating expression.
- In the body of `is_not<int, bool(*)(int)>`, `f(t)` is a call through a function pointer parameter and statically calls no immediate function, so this specialization doesn't escalate.
- The whole `is_not(5, is_even)` completes within one constant evaluation, and the address of `is_even` never enters run time.

As long as the address of a consteval function doesn't leave constant evaluation, it can pass through any ordinary constexpr generic code.

### Escalation of defaulted constructors

Note 1 of ¶4 explains that default member initializers used to initialize base or member subobjects are considered part of the constructor's function body. So a consteval call in a default member initializer escalates the implicit constructor:

```cpp run ok
consteval int id(int i) { return i; }
struct Z {
  int a = 1;
  int b = id(a);    // not a constant: an immediate-escalating expression
  Z() = default;    // not user-provided → escalated to an immediate function
};
Z z;                // Z() is an immediate invocation, evaluating to b == 1
int f() { Z lz; return lz.b; }   // likewise constructed at compile time
int main() { return f() + z.b - 2; }
```

## Default arguments and default member initializers

A default argument belongs to the caller: it is evaluated at each call that uses it ([[dcl.fct.default]]). So a consteval call in a default argument escalates the caller, not the function that declares it.

```cpp
consteval int id(int i) { return i; }
int x = 0;

template<class T>
constexpr T h(T t = id(x)) {  // h<int> is not an immediate function:
  return t;                   // the default argument isn't evaluated in h
}

template<class T>
constexpr T hh() {            // hh<int> is an immediate function:
  return h<T>();              // the default argument id(x) is used here
}

int i = hh<int>();            // error: hh<int>() is an immediate invocation that reads x, not a constant
```

The last sentence of ¶1 deals with aggregates. Aggregates have no constructor that could be escalated, so the standard says: if an aggregate initialization evaluates a default member initializer that contains an immediate-escalating expression, the aggregate initialization itself is an immediate invocation.

```cpp
consteval int id(int i) { return i; }
struct A {
  int x;
  int y = id(x);     // x is a member, not a constant
};

constexpr int k1 = A(42).y;   // OK: A(42) is an immediate invocation, and the whole is a constant
int rt = 1;
int k2 = A{rt}.y;             // error: the immediate invocation A{rt} is not a constant

template<class T>
constexpr int k(int) {        // k<int> is not an immediate function:
  return A(42).y;             // A(42) is a constant, not an immediate-escalating expression
}
```

!!! impl "Clang 23 disagrees with the standard"
    Clang 23 rejects even `k1`, reporting "call to consteval function 'id' is not a constant expression", and treats `k<int>` as an immediate function (`&k<int>` gives "cannot take address of immediate function"). It evaluates `id(x)` in the default member initializer on its own, where `this` is not available, instead of treating the whole aggregate initialization as one immediate invocation. By the standard, `k1` is valid and `k<int>` is not an immediate function.

## Taking the address of an immediate function {{c++26}}

In C++20 and C++23, a pointer to an immediate function could not be the result of a constant expression and could only be passed around inside immediate function contexts. To accommodate reflection, C++26 restated this rule in terms of consteval-only values and immediate objects ([[expr.const.const#1]]): a pointer to an immediate function can be stored in a constexpr variable or used as a template argument, but it cannot enter a run-time object.

```cpp
consteval int plus1(int x) { return x + 1; }
template <auto V> struct C {};

auto a = plus1;            // error: a run-time variable
constexpr auto b = plus1;  // C++26: OK
auto c = C<plus1>();       // C++26: OK
```

This is the standard's example from [[expr.const.const]]. At the time of writing, Clang 23 still rejects `b` and `c` under the C++23 rules.

## Contracts and constant initialization {{c++26}}

The last part of the standard's example in ¶5 shows how contract assertions affect the kind of initialization:

```cpp
constexpr int l(int c) pre(c >= 2) {
  return (c % 2 == 0) ? c / 0 : c;
}

const int i0 = l(0);  // dynamic initialization; contract violation or undefined behavior
const int i1 = l(1);  // static initialization; value 1, or a contract violation reported at compile time
const int i2 = l(2);  // dynamic initialization; undefined behavior
const int i3 = l(3);  // static initialization; value 3
```

When deciding whether a variable can be constant-initialized, contract assertions are always treated with the ignore semantic ([[expr.const.init#4]]). With the precondition ignored, `l(1)` and `l(3)` are both constants, so `i1` and `i3` are statically initialized; `l(0)` and `l(2)` both divide by 0, so `i0` and `i2` are dynamically initialized, and the problem shows up only at run time.

When `l(1)` is actually evaluated during translation, the implementation may still check the contract; then `1 >= 2` doesn't hold, and a compile-time diagnostic results. The design ensures that switching contract checking on or off doesn't change whether a variable is statically or dynamically initialized; otherwise enabling checks could change the initialization order of global variables. Clang 23 doesn't support contract syntax yet, so this code has not been verified by compilation.

## Other constraints

These rules are in [[dcl.constexpr]] and [[class.virtual]]:

- `consteval` can only be used in the declaration of a function or function template. A consteval function is implicitly inline and is also a constexpr function ([[dcl.constexpr#1]], [[dcl.constexpr#2]]).
- All declarations of a function must consistently have or not have `consteval`.
- Destructors, allocation functions and deallocation functions cannot be consteval ([[dcl.constexpr#2]]). The language calls them implicitly at scope exit, in `new`/`delete` expressions and so on, and cannot guarantee that every such call happens in constant evaluation.
- A consteval virtual function and a non-consteval virtual function cannot override each other ([[class.virtual#18]]).

!!! impl "consteval inside the compiler"
    An immediate invocation is evaluated and replaced by its result during semantic analysis (a `ConstantExpr` node in Clang) and never reaches code generation, so a consteval function has no symbol, and a debugger can't set a breakpoint in it. Escalation requires the compiler, upon finding an immediate-escalating expression while instantiating a function body, to mark that specialization as an immediate function and then go back and check earlier references to it, such as taking its address. Clang applies the P2564 rules under `-std=c++20` too.

## History and evolution

!!! history
    - C++20 ([[P1073R3]]) introduced `consteval`. The rule was simple: a call must be a constant expression unless it is inside another consteval function. It didn't work with generic forwarding code.
    - C++23 ([[P1938R3]]) introduced `if consteval`, letting constexpr functions call consteval functions in the compile-time branch.
    - C++23 ([[P2564R3]], as a defect fix) introduced immediate escalation, so constexpr templates automatically become immediate functions when needed.
    - C++26 ([[P2996R13]]) introduced immediate constant expressions, consteval-only values and immediate objects to accommodate reflection, so pointers to immediate functions can now be stored in constexpr variables.

## Common misconceptions

!!! pitfall "Escalation only affects this one function"
    Adding a consteval call to a constexpr function template can silently turn some specializations into immediate functions, and then a distant `auto p = &tf<int>;` or `tf(runtime_value)` starts failing. The error shows up at the use, not at the change.

!!! pitfall "Ordinary constexpr functions escalate too"
    They don't. `constexpr int wrap(int n) { return sq(n); }` is simply ill-formed; escalation applies only to template specializations, lambdas and defaulted functions. Make it `consteval`, or put the call in `if consteval`.

## Questions

!!! question "Question 1"
    Which line below is wrong, and why?

    ```cpp
    consteval int sq(int n) { return n * n; }
    auto l1 = [](int n) { return sq(n); };
    auto l2 = [](int n) consteval { return sq(n); };
    int a = l1(2);
    int b = l2(2);
    auto p1 = +l1;
    ```

<details markdown="1">
<summary>Answer</summary>

`auto p1 = +l1;` is wrong. The call operator of `l1` is an immediate-escalating function (¶3.1), and `sq(n)` in it is not a constant, so it is escalated to an immediate function. `+l1` converts the captureless lambda to a function pointer pointing to an immediate function, which is an immediate-escalating expression in the initializer of a run-time variable, and a namespace-scope initializer is not in any immediate-escalating function. Clang reports "cannot take address of immediate call operator". `a` and `b` are both immediate invocations with constant arguments and are valid.
</details>

!!! question "Question 2"
    Why is `std::is_constant_evaluated()` a constexpr function rather than a consteval one?

<details markdown="1">
<summary>Answer</summary>

If it were consteval, every call would either be an immediate invocation or be in an immediate function context, always evaluated at compile time, so the result would always be `true`, and it couldn't tell whether the current evaluation is a constant evaluation. It must be callable at run time and return `false` there. Its specification is written in terms of `if consteval` precisely for this reason ([[meta.const.eval#1]]).
</details>
