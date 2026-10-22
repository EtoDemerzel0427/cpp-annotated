---
title: bind_front and bind_back
summary: "bind_front and bind_back fix the leading or trailing arguments of a callable and return a perfect forwarding call wrapper; C++26 adds overloads that take the callable as a constant template argument, so the wrapper no longer needs to store it."
updated: 2026-10-19
---

!!! tldr
    - `bind_front(f, a, b)(x, y)` is equivalent to `invoke(f, a, b, x, y)`; `bind_back(f, a, b)(x, y)` is equivalent to `invoke(f, x, y, a, b)`.
    - `f` and the bound arguments are stored as `decay_t` copies; to store a reference, pass `std::ref`.
    - The result is a perfect forwarding call wrapper: when the wrapper is an rvalue, the stored state is also handed over as rvalues, so a bound `unique_ptr` can be passed on.
    - Compared with `std::bind`: no placeholders, no nested evaluation, no unwrapping of `reference_wrapper`, and no discarding of extra call arguments.
    - C++26's `bind_front<f>(args...)` passes `f` as a template argument; the wrapper does not store it, and a null pointer is rejected at compile time.

## Fixing leading or trailing arguments

```cpp run title="bind_front_basics.cpp" ok
#include <functional>
#include <memory>
#include <string>
#include <cstdio>
int sub(int a, int b) { return a - b; }
struct Greeter { std::string greet(const std::string& n) const { return "hi " + n; } };
void consume(std::unique_ptr<int> p) { std::printf("%d\n", *p); }
int main() {
  auto ten_minus = std::bind_front(sub, 10);
  auto minus_ten = std::bind_back(sub, 10);
  std::printf("%d %d\n", ten_minus(3), minus_ten(3));        // 7 -7

  Greeter g;
  auto hi = std::bind_front(&Greeter::greet, &g);            // via INVOKE: pointer to member function plus object pointer
  std::printf("%s\n", hi("bob").c_str());

  auto once = std::bind_front(consume, std::make_unique<int>(42));
  std::move(once)();                                         // the rvalue wrapper hands over unique_ptr&&
}
```

`bind_front` and `bind_back` are `std::bind` ([[func.bind]]) with all its special treatment stripped away. They do only one thing: put the stored arguments before or after the call arguments, then call the target via *INVOKE* ([[func.require]]).

## Specification

```cpp
template<class F, class... Args>
  constexpr unspecified bind_front(F&& f, Args&&... args);
template<class F, class... Args>
  constexpr unspecified bind_back(F&& f, Args&&... args);
```

¶1 The notation is similar to `bind`'s: `FD` is `decay_t<F>`, and the target object `fd` is direct-non-list-initialized with `std::forward<F>(f)`; `BoundArgs` is `decay_t<Args>...`, and the bound argument entities `bound_args` are initialized with `std::forward<Args>(args)...`; `call_args` are the arguments when `g` is called.

¶2 requires (Mandates) that `FD` be constructible from `F` and move-constructible, and that each `BoundArgs` be constructible from the corresponding `Args` and move-constructible; otherwise the program is ill-formed. ¶3 further requires them to meet *Cpp17MoveConstructible* semantically. ¶5 `bind_front` throws any exception thrown by the initialization of the state entities.

¶4 It returns a perfect forwarding call wrapper ([[g:perfect-forwarding-call-wrapper]]) `g` whose call pattern ([[g:call-pattern]]) is:

- ¶4.1 `bind_front`: `invoke(fd, bound_args..., call_args...)`;
- ¶4.2 `bind_back`: `invoke(fd, call_args..., bound_args...)`.

Perfect forwarding means that the form in which `fd` and `bound_args` are handed to `invoke` varies with the value category and const of `g`:

| Call | Form of `fd` and `bound_args` |
|---|---|
| `g(x)` | `FD&`, `BoundArgs&...` |
| `std::as_const(g)(x)` | `const FD&`, `const BoundArgs&...` |
| `std::move(g)(x)` | `FD&&`, `BoundArgs&&...` |
| `std::move(std::as_const(g))(x)` | `const FD&&`, `const BoundArgs&&...` |

The call is expression-equivalent to the call pattern, so when the call pattern is not valid under some qualification, the corresponding `g(...)` is ill-formed and does not fall back to a differently qualified version (see [[func.require]] for an example). Copying and moving the wrapper is done state entity by state entity: if a move-only object is bound, `g` can only be moved too.

!!! pitfall "Overload sets and function templates cannot be passed directly"
    `F` has to be deduced from the argument, so `std::bind_front(std::max, 0)` and `std::bind_front(overloaded_fn, 1)` both fail to deduce. You can wrap it in a lambda: `std::bind_front([](auto... a) { return f(a...); }, 1)`. C++26's template-argument version also needs a definite value, so for an overload set you likewise have to pick one with `static_cast` first.

!!! pitfall "Binding `this` is no safer than capturing `this`"
    `std::bind_front(&Widget::on_event, this)` stores a raw pointer. If it is registered as a callback and the `Widget` is destroyed first, the pointer dangles. This is the same problem as a lambda capturing `this`.

!!! pitfall "Calling as an rvalue more than once"
    After `auto g = std::bind_front(f, std::string("abc"));`, writing `std::move(g)(i)` repeatedly in a loop hands the bound string to `f` as `std::string&&` every time. If `f` takes it by value, the first call moves the string out, and later calls get a valid but unspecified state. A wrapper that may be called several times should be called as an lvalue.

## Passing the callable as a template argument {{c++26}}

```cpp
template<auto f, class... Args> constexpr unspecified bind_front(Args&&... args);
template<auto f, class... Args> constexpr unspecified bind_back(Args&&... args);
```

C++26's [[P2714R1]] added these two overloads, in which the callable `f` is passed as a constant template argument (NTTP). The specification is almost the same as for the function-parameter versions, with three differences:

- ¶7 The requirements no longer mention `FD`, but there is one more: if the type of `f` is a pointer or a member pointer, `f != nullptr` must be true. A null function pointer is rejected at compile time.
- ¶9 The returned perfect forwarding call wrapper's target object is a copy of `cw<f>` (`cw` is C++26's `constant_wrapper`; see [[const.wrap.class]]). The call pattern uses `f` directly: `invoke(f, bound_args..., call_args...)` or `invoke(f, call_args..., bound_args...)`.
- ¶10 The only exceptions that can be thrown are those from initializing `bound_args`.

This has two advantages. One is size: `bind_front(sub, 10)` has to store a function pointer and an `int`, while the target object of `bind_front<sub>(10)` is an empty `constant_wrapper`, so the whole wrapper is only as big as an `int`, and it is more likely to fit in the small buffer of a `std::function` or `move_only_function`. The other is ease of inlining: a function pointer is a run-time value that the optimizer must first prove unchanged before inlining; a template argument is part of the type, so the call target is determined at compile time.

```cpp run title="nttp_bind_front.cpp" ok
#include <functional>
#include <cstdio>
int sub(int a, int b) { return a - b; }
int main() {
  auto a = std::bind_front(sub, 10);      // stores a function pointer and an int
  auto b = std::bind_front<sub>(10);      // C++26: stores only the int
  static_assert(sizeof(b) == sizeof(int));
  std::printf("%zu %zu %d %d\n", sizeof(a), sizeof(b), a(3), b(3));   // in our tests: 16 4 7 7
}
```

```cpp run title="nttp_null.cpp" error
#include <functional>
constexpr int (*null_fp)(int) = nullptr;
int main() { auto g = std::bind_front<null_fp>(1); (void)g; }   // error: violates f != nullptr
```

!!! impl "libc++ does not implement the template-argument `bind_back` yet"
    libc++ (LLVM 23) in our tests implements the template-argument version of `bind_front` (`__cpp_lib_bind_front` is `202306L`), but not the corresponding `bind_back` (`__cpp_lib_bind_back` is still `202202L`), and `std::bind_back<f>(...)` reports no matching function.

    Another small difference: for the function-parameter `bind_front`, libc++ expresses the requirements of ¶2 with a `requires` clause, so a violation gives "no matching function"; for `bind_back` it uses `static_assert`. The standard says Mandates, and both approaches meet the requirement of being ill-formed with a diagnostic.

## History and evolution

!!! history
    - C++20: `bind_front` ([[P0356R5]]).
    - C++23: `bind_back` ([[P2387R3]]). Its main use is implementing user-defined range adaptor closures ([[range.adaptor.object]]): what `views::foo(arg)` returns is exactly an object with the trailing arguments bound, waiting for a range as its first argument.
    - C++26: the template-argument versions of both ([[P2714R1]]), added together with `not_fn<f>` ([[func.not.fn]]).
