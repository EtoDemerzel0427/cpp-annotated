---
title: Function template not_fn
summary: "not_fn(f) returns a perfect forwarding call wrapper that negates the result of f, with call pattern !invoke(fd, call_args...); it replaces not1 / not2, which were removed in C++20, and C++26 adds not_fn<f>(), which does not store the callable."
updated: 2026-10-19
---

!!! tldr
    - `not_fn(f)(args...)` is equivalent to `!invoke(f, args...)`, and can negate a predicate with any number of parameters, including member pointers.
    - The result is a perfect forwarding call wrapper: the wrapper's const and value category are passed on to the stored `f`, so ref-qualified `operator()`s are selected correctly.
    - The return type is the type of the `!` expression, not necessarily `bool`.
    - C++26's `not_fn<f>()` passes `f` as a template argument; the result is an empty object, and a null pointer is rejected at compile time.

## Negating a predicate

```cpp run title="not_fn_basics.cpp" ok
#include <functional>
#include <algorithm>
#include <type_traits>
#include <vector>
#include <cstdio>
bool is_even(int x) { return x % 2 == 0; }
struct Odd { int operator()(int x) const { return x % 2; } };      // returns int
struct Pred {
  bool operator()(int x) &  { std::puts("&");  return x > 0; }
  bool operator()(int x) && { std::puts("&&"); return x > 0; }
};
int main() {
  std::vector<int> v{1, 2, 3, 4, 5};
  std::printf("%td\n", std::ranges::count_if(v, std::not_fn(is_even)));   // 3

  auto even = std::not_fn(Odd{});
  static_assert(std::is_same_v<decltype(even(3)), bool>);                 // the type of !int is bool
  std::printf("%d %d\n", even(3), even(4));                               // 0 1

  auto n = std::not_fn(Pred{});
  (void)n(1);              // lvalue wrapper: the target is Pred&, prints &
  (void)std::move(n)(1);   // rvalue wrapper: the target is Pred&&, prints &&
}
```

`not_fn` was added in C++17 ([[P0005R4]]). It replaces C++98's `not1` and `not2`: those supported only unary and binary predicates and required the wrapped type to provide member types such as `argument_type`; they were deprecated in C++17 and removed in C++20.

## Specification [func.not.fn]

```cpp
template<class F> constexpr unspecified not_fn(F&& f);
```

¶1 The notation is the same as in [[func.bind.partial]]: `FD` is `decay_t<F>`, the target object `fd` is direct-non-list-initialized with `std::forward<F>(f)`, and `call_args` are the call arguments. ¶2 requires (Mandates) that `FD` be constructible from `F` and move-constructible; ¶3 further requires it to meet *Cpp17MoveConstructible* semantically; ¶5 `not_fn` throws any exception thrown by the initialization of `fd`.

¶4 It returns a perfect forwarding call wrapper ([[g:perfect-forwarding-call-wrapper]]) whose call pattern is `!invoke(fd, call_args...)`. The following properties all follow from this:

- The return type is the type of the `!` expression. When `f` returns `int`, it is the built-in `!` and the result is `bool`; when `f` returns a class that overloads `operator!`, the result is the return type of that `operator!`.
- When the wrapper is called as an lvalue the target is `FD&`, and as an rvalue it is `FD&&`, and likewise for const; that is why the two ref-qualified versions of `Pred` are selected in the example above.
- The call goes through `invoke`, so member pointers can be negated too, for example `not_fn(&Person::is_adult)`.
- When the call pattern is not valid, `g(...)` is ill-formed and does not fall back to a differently qualified version ([[func.require]]).

## `not_fn<f>()` {{c++26}}

```cpp
template<auto f> constexpr unspecified not_fn() noexcept;
```

This overload was added together with `bind_front<f>` by [[P2714R1]]. ¶7 If the type of `f` is a pointer or a member pointer, `f != nullptr` is required, so null pointers are rejected at compile time. ¶8 It returns a perfect forwarding call wrapper whose target object is a copy of `cw<f>` ([[const.wrap.class]]) and whose call pattern is `!invoke(f, call_args...)`.

The wrapper stores nothing, so the function itself is `noexcept`, the result is an empty object, and the call target is determined at compile time.

```cpp run title="not_fn_nttp.cpp" ok
#include <functional>
#include <algorithm>
#include <vector>
#include <cstdio>
bool is_even(int x) { return x % 2 == 0; }
int main() {
  std::vector<int> v{1, 2, 3, 4, 5};
  auto odd = std::not_fn<is_even>();
  static_assert(sizeof(odd) == 1);                       // empty class: no function pointer stored
  static_assert(sizeof(std::not_fn(is_even)) == sizeof(bool (*)(int)));
  std::printf("%td\n", std::ranges::count_if(v, odd));   // 3
}
```

libc++ (LLVM 23) in our tests already implements this overload, and `__cpp_lib_not_fn` is `202306L`.
