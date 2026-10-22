---
title: Function object binders
summary: "std::bind fixes some of a callable's arguments and lets placeholders reorder the rest. This page covers how it stores state by value, the four rules for handling bound arguments, the user-specializable is_bind_expression and is_placeholder, and why new code should use lambdas or bind_front / bind_back instead."
updated: 2026-10-19
---

!!! tldr
    - `std::bind(f, args...)` stores `f` and the bound arguments as `decay_t` copies and returns an argument forwarding call wrapper. To store a reference, you must pass `std::ref(x)`.
    - At the call, each bound argument is handled by four rules: a `reference_wrapper` is unwrapped to `T&`; a nested bind expression is first evaluated with all the call arguments; a placeholder `_j` is replaced by the jth call argument; everything else is handed over as an lvalue.
    - Bound values are always handed to the target as lvalues, even when the wrapper itself is an rvalue. So a bound `unique_ptr` cannot be passed on to a function that takes it by value.
    - Call arguments not referenced by any placeholder are silently discarded; if the same placeholder appears twice, an rvalue argument is forwarded twice.
    - New code should prefer lambdas, or C++20's `bind_front` and C++23's `bind_back`.

## Partial application and argument reordering

```cpp run title="bind_rules.cpp" ok
#include <functional>
#include <cstdio>
using namespace std::placeholders;
int add3(int a, int b, int c) { return 100 * a + 10 * b + c; }
int twice(int x) { return 2 * x; }
void bump(int& n) { ++n; }
int main() {
  auto g = std::bind(add3, _2, 5, _1);                    // placeholders can reorder
  std::printf("%d\n", g(1, 2));                           // add3(2, 5, 1) = 251
  std::printf("%d\n", g(1, 2, 999));                      // extra call arguments silently discarded

  auto h = std::bind(add3, std::bind(twice, _1), 0, _1);  // nested bind evaluated first
  std::printf("%d\n", h(3));                              // add3(twice(3), 0, 3) = 603

  int n = 0;
  auto by_copy = std::bind(bump, n);                      // binds a copy of n
  auto by_ref  = std::bind(bump, std::ref(n));            // unwrapped to int&
  by_copy(); by_copy();
  by_ref();
  std::printf("%d\n", n);                                 // 1
}
```

`std::bind` comes from Boost.Bind and TR1 and entered the standard in C++11. It solved two problems from before lambdas were widespread: **partial application** (fixing some of a function's arguments) and argument reordering. `std::placeholders::_1`, `_2`, ... are called **placeholders** and stand for the 1st, 2nd, ... argument when the call wrapper is called.

Today most of its uses have been taken over by lambdas and by `bind_front` and `bind_back` ([[func.bind.partial]]), but it is still common in old code. Its specification is built on *INVOKE* and the call wrapper concepts from [[func.require]].

## What is stored: decayed copies [func.bind.bind]

```cpp
template<class F, class... BoundArgs>
  constexpr unspecified bind(F&& f, BoundArgs&&... bound_args);
template<class R, class F, class... BoundArgs>
  constexpr unspecified bind(F&& f, BoundArgs&&... bound_args);
```

¶1 first defines the notation used later:

| Notation | Meaning |
|---|---|
| `g` | the call wrapper returned by `bind` |
| `FD`, `fd` | `decay_t<F>`; the target object, direct-non-list-initialized with `std::forward<F>(f)` |
| `TDi`, `tdi` | `decay_t<Ti>` of the ith bound argument; the corresponding bound argument entity, initialized with `std::forward<Ti>(ti)` |
| `Uj`, `uj` | the type deduced for the jth argument when `g(u1, …, uM)` is called, and the argument itself |

The key is `decay`: everything bound is stored by value. Functions decay to function pointers, arrays decay to pointers, and references are stripped. To store a reference, you can only use `std::ref` explicitly.

¶2 requires (Mandates) that `FD` be constructible from `F` and each `TDi` from `Ti`; otherwise the program is ill-formed. This is not a constraint: `bind` still participates in overload resolution and then reports an error inside the function body. Note 1 in ¶6 says that if `FD` and all `TDi` are copy-constructible, the returned wrapper is copy-constructible too.

## What happens at the call

¶4 `bind` returns an argument forwarding call wrapper ([[g:argument-forwarding-call-wrapper]]), not a perfect forwarding call wrapper. Calling a `volatile`-qualified `g` is ill-formed. Otherwise `g(u1, …, uM)` is [[g:expression-equivalent|expression-equivalent]] to:

```cpp
INVOKE(static_cast<Vfd>(vfd), static_cast<V1>(v1), …, static_cast<VN>(vN))      // the first overload
INVOKE<R>(static_cast<Vfd>(vfd), static_cast<V1>(v1), …, static_cast<VN>(vN))   // the overload with R
```

¶8 `vfd` is just `fd`, and its type `Vfd` is `cv FD&`, where `cv` is the cv-qualification of `g` itself. That is, the target object is always handed over as an lvalue, whether `g` is an lvalue or an rvalue.

¶7 Each bound argument `vi` and its type `Vi` are determined by `TDi`, matching four rules in order:

| Rule | Condition | `vi` handed to the target | Type `Vi` |
|---|---|---|---|
| ¶7.1 | `TDi` is `reference_wrapper<T>` | `tdi.get()` | `T&` |
| ¶7.2 | `is_bind_expression_v<TDi>` is true | `static_cast<cv TDi&>(tdi)(std::forward<Uj>(uj)...)` | `invoke_result_t<cv TDi&, Uj...>&&` |
| ¶7.3 | the value j of `is_placeholder_v<TDi>` is nonzero | `std::forward<Uj>(uj)` | `Uj&&` |
| ¶7.4 | otherwise | `tdi` | `cv TDi&` |

Their consequences are respectively:

- A `reference_wrapper` is unwrapped. At the call, `std::bind(f, std::ref(x))` passes `x` itself, so `f` can modify `x`.
- A nested bind expression is evaluated immediately. The inner bind is called with all the call arguments, and its result becomes an argument to the outer one, so `bind(f, bind(g, _1))(x)` is `f(g(x))`. If the intent was to hand a bind expression to `f` as a callback object, it gets called first (see below).
- A placeholder takes the jth call argument and perfectly forwards it. Call arguments not referenced by any placeholder are silently discarded: the `999` in `g(1, 2, 999)` causes no error.
- The other bound arguments are handed over as `cv TDi&` lvalues. Even if you write `std::move(g)()`, the target function does not get an rvalue, so a bound `unique_ptr` cannot be passed on to a function that takes it by value.

The overload with `R` uses *INVOKE*&lt;R&gt;: the result is implicitly converted to `R`, and discarded when `R` is `void` ([[func.require#2]]).

```cpp run title="bind_r.cpp" ok
#include <functional>
#include <type_traits>
#include <cstdio>
long twice(int x) { return 2L * x; }
int main() {
  auto g = std::bind<double>(twice, std::placeholders::_1);   // INVOKE<double>
  auto h = std::bind<void>(twice, 21);                        // INVOKE<void>: return value discarded
  static_assert(std::is_same_v<decltype(g(1)), double>);
  static_assert(std::is_same_v<decltype(h()), void>);
  std::printf("%g\n", g(21));                                 // 42
}
```

## Two recognition traits [func.bind.isbind] [func.bind.isplace]

¶7.2 and ¶7.3 need to recognize nested bind expressions and placeholders, which they do with two class templates. Both meet *Cpp17UnaryTypeTrait* ([[meta.rqmts]]):

- `is_bind_expression<T>`: derived from `true_type` when `T` is a type returned by `bind`, otherwise from `false_type`. A program may specialize it as `true_type` for a program-defined type ([[g:program-defined-type]]) to make that type be evaluated first at the call, like a bind subexpression.
- `is_placeholder<T>`: derived from `integral_constant<int, J>` when `T` is the type of `std::placeholders::_J`, otherwise from `integral_constant<int, 0>`. A program may specialize it with `N > 0` for its own type to make it act as the Nth placeholder.

```cpp run title="custom_placeholder.cpp" ok
#include <functional>
#include <cstdio>
struct MyPh {};
template<> struct std::is_placeholder<MyPh> : std::integral_constant<int, 2> {};
int sub(int a, int b) { return a - b; }
int main() {
  auto g = std::bind(sub, MyPh{}, std::placeholders::_1);   // MyPh acts as _2
  std::printf("%d\n", g(1, 10));                            // sub(10, 1) = 9
}
```

## Placeholders [func.bind.place]

¶1 The number of placeholders is implementation-defined ({{impl}}); libc++ provides `_1` to `_10`. ¶2 Placeholder types are default-constructible and copy-constructible, and these constructors are all non-throwing `constexpr` functions; whether they are copy-assignable is implementation-defined.

¶3 The standard recommends defining placeholders as `inline constexpr unspecified _1{};`, and otherwise declaring them as `extern unspecified _1;`. ¶4 Placeholders must also be provided in freestanding implementations.

!!! impl "libc++'s placeholders are `extern const`"
    libc++ declares the placeholders in `__functional/bind.h` as `extern const __ph<1> _1;`, with the definitions in the shared library. A source comment explains that switching to `inline constexpr` would require removing the existing definitions from the shared library to avoid violating the ODR, and removing them would itself break the ABI. Placeholders are empty classes, so the two forms make almost no difference in use.

## Pitfalls

### A nested bind is evaluated unexpectedly

```cpp run title="nested_bind_trap.cpp" error
#include <functional>
using namespace std::placeholders;
int twice(int x) { return 2 * x; }
int apply(std::function<int(int)> f, int x) { return f(x); }
int main() {
  auto g = std::bind(apply, std::bind(twice, _1), _1);
  return g(3);   // error: the inner bind is evaluated first (¶7.2), apply receives an int
}
```

The intent was to hand `bind(twice, _1)` to `apply` as a callback, but per ¶7.2 it is first evaluated with the call argument `3`, and `apply`'s first argument becomes an `int`. To pass a bind expression in as a value, first wrap it in a type that `is_bind_expression` does not recognize, such as `std::function` or a lambda.

### The same placeholder forwarded twice

```cpp run title="placeholder_twice.cpp"
#include <functional>
#include <string>
#include <cstdio>
using namespace std::placeholders;
void two(std::string a, std::string b) { std::printf("[%s] [%s]\n", a.c_str(), b.c_str()); }
int main() {
  auto g = std::bind(two, _1, _1);
  std::string s = "hello";
  g(s);                       // lvalue: copied twice
  g(std::string("world"));    // rvalue forwarded twice: one parameter gets a moved-from string
}
```

¶7.3 says the argument for `_1` is `std::forward<U1>(u1)`, so appearing twice means forwarding twice. When the argument is an rvalue, the first parameter initialization moves from it, and the second gets a valid but unspecified state ([[g:valid-but-unspecified-state]]). The order in which function parameters are initialized is also unspecified ([[expr.call]]), so which parameter gets the empty string is not determined; in our tests the output is `[world] []`. This code has no UB, but the result depends on unspecified behavior, so it carries no verdict tag.

### libc++ falls back to the const version

```cpp run title="bind_cv_fallback.cpp"
#include <functional>
#include <cstdio>
struct F {
  void operator()() const { std::puts("const"); }
  void operator()() = delete;
};
int main() {
  auto g = std::bind(F{});
  g();      // ill-formed per the wording; libc++ accepts it and prints const
}
```

Per ¶4 and ¶8, the non-const `g()` is equivalent to a call on `F&`, overload resolution selects the deleted non-const version, and the program should be ill-formed. libc++ in our tests accepts this code and outputs `const`: its `__bind` falls back to the const version when the non-const call is not valid. With `bind_front` instead, libc++ correctly rejects the same code (see [[func.require]]). Because the standard and the implementation disagree, this code block carries no verdict tag.

## Why switch to `bind_front`, `bind_back` or lambdas

| Issue | `bind` | `bind_front` / `bind_back` | lambda |
|---|---|---|---|
| How the state is handed to the target | always as `cv TDi&` lvalues | perfectly forwarded according to the wrapper's value category | your choice |
| Extra call arguments | silently discarded | passed on as usual; a count mismatch is an error | error |
| Nested bind expressions | evaluated first | ordinary objects | ordinary objects |
| `reference_wrapper` | unwrapped | not unwrapped; relies on implicit conversion | write it yourself |
| Overloaded function names | `F` cannot be deduced; cast first | likewise cannot be deduced | called in the body; overload resolution works normally |
| Reordering arguments | supported | only fixed leading or trailing arguments | anything |

The most typical difference is a move-only bound argument:

```cpp run title="bind_vs_bind_front_move.cpp" ok
#include <functional>
#include <memory>
#include <cstdio>
void consume(std::unique_ptr<int> p) { std::printf("%d\n", *p); }
int main() {
  auto g = std::bind_front(consume, std::make_unique<int>(42));
  std::move(g)();      // OK: the rvalue wrapper forwards the state as unique_ptr&&
  // g();              // error: the lvalue wrapper hands over unique_ptr&, which cannot be copied
  auto b = std::bind(consume, std::make_unique<int>(7));
  // std::move(b)();   // error: bind always hands over bound arguments as lvalues (¶7.4)
  (void)b;
}
```

C++20's `bind_front` ([[P0356R5]]) was designed precisely for this: no placeholders, no nested evaluation, and perfectly forwarded state.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[func.bind.general] ¶1 only says that this subclause describes a uniform mechanism for binding arguments.

The preconditions in [func.bind.bind] ¶3 require `FD` and each `TDi` to meet *Cpp17MoveConstructible* and *Cpp17Destructible*, and that for some values `w1, …, wN` (where N is the number of bound arguments), `INVOKE(fd, w1, …, wN)` is a valid expression. The latter merely excludes bindings whose number of arguments cannot possibly match; it is a precondition, and implementations usually do not diagnose violations until the call. ¶5 specifies that `bind` throws any exception thrown by the initialization of the state entities.

</details>

## Questions

!!! question "Question 1"
    `auto g = std::bind(f, _1); g();`: what happens when a bind expression that references `_1` is called with no arguments? Conversely, what about `auto h = std::bind(f); h(1, 2, 3);`?

<details markdown="1">
<summary>Answer</summary>

The former is ill-formed. ¶7.3 needs the 1st call argument, but the call has no arguments, so the *INVOKE* expression cannot be formed; libc++ reports that there is no matching call operator.

The latter is well-formed. No placeholder references the three arguments, so per ¶7 they do not appear in the *INVOKE* expression at all, and `h(1, 2, 3)` is just `f()`. This is how extra arguments are silently discarded.
</details>

!!! question "Question 2"
    Why is the type `Vi` of a nested bind subexpression in ¶7.2 written as `invoke_result_t<cv TDi&, Uj...>&&` rather than without the `&&`?

<details markdown="1">
<summary>Answer</summary>

¶4 hands each argument to *INVOKE* with `static_cast<Vi>(vi)`. With the `&&` added, reference collapsing gives: when the inner call returns `T&`, `Vi` is `T&`; when it returns `T&&` or a prvalue `T`, `Vi` is `T&&`. This both preserves the value category of the inner call's result and avoids an extra copy or move of a prvalue result.
</details>
