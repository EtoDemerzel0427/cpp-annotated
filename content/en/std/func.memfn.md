---
title: Function template mem_fn
summary: "mem_fn(pm) wraps a member pointer into a function object that can be called as f(obj, args...); it is a simple call wrapper with call pattern invoke(pmd, call_args...), so an object, a pointer, a smart pointer or a reference_wrapper can all be the first argument."
updated: 2026-10-19
---

!!! tldr
    - A member pointer cannot be called as `pm(obj)`; `std::mem_fn(pm)` returns a function object that can.
    - The call goes through *INVOKE*, so the first argument can be an object, an object of a derived class, a raw pointer, a smart pointer or a `reference_wrapper`.
    - The result is a simple call wrapper: it can be copied and assigned, and these operations are all non-throwing `constexpr` functions.
    - Ranges algorithms already call predicates and projections via `std::invoke`, so member pointers can be passed to them directly without `mem_fn`.

## Turning a member pointer into a function object

```cpp run title="mem_fn.cpp" ok
#include <functional>
#include <algorithm>
#include <memory>
#include <string>
#include <vector>
#include <cstdio>
struct Person {
  std::string name; int age;
  bool adult() const { return age >= 18; }
};
int main() {
  std::vector<Person> ps{{"a", 20}, {"b", 10}};
  auto adult = std::mem_fn(&Person::adult);
  auto age = std::mem_fn(&Person::age);
  std::printf("%td\n", std::count_if(ps.begin(), ps.end(), adult));   // 1
  auto up = std::make_unique<Person>(Person{"c", 30});
  std::printf("%d %d %d\n", age(ps[1]), age(&ps[0]), age(up));       // object, pointer, smart pointer
  auto copy = adult;  copy = adult;                                   // copyable, assignable
  std::printf("%d\n", copy(std::ref(ps[0])));                         // reference_wrapper works too
}
```

A member pointer is a callable type but not a function object type ([[function.objects]]): `pmf(obj)` is not a valid expression. Classic algorithms such as `std::count_if` call the predicate as `pred(*it)` and only accept things that can be written as `f(x)`. `mem_fn` is the adapter that turns `&Person::adult` into that shape.

## Specification [func.memfn]

```cpp
template<class R, class T> constexpr unspecified mem_fn(R T::* pm) noexcept;
```

The parameter type `R T::*` matches both pointers to data members (`R` is an object type, such as `int`) and pointers to member functions (`R` is a function type, such as `bool() const`).

¶1 `mem_fn` returns a simple call wrapper ([[g:simple-call-wrapper]]) `fn`. Its target object `pmd` has type `R T::*` and is direct-non-list-initialized with `pm`; the call pattern is `invoke(pmd, call_args...)`. It follows that:

- The first call argument is handled by the bullets of *INVOKE* ([[func.require]]), and can be an object, an object of a derived class, a `reference_wrapper`, a raw pointer or a smart pointer. When wrapping a pointer to data member, only one argument is accepted and the object's value category is preserved: an rvalue object gives an xvalue.
- A simple call wrapper is required to be copy-constructible and copy-assignable, with copying, moving and assignment all being non-throwing `constexpr` functions. The only state of `mem_fn` is a member pointer, which naturally satisfies this.
- `mem_fn` itself is `noexcept`, and `constexpr` since C++20.

## Is `mem_fn` still needed today

The predicates and projections of Ranges algorithms are already called via `std::invoke`, so `std::ranges::count_if(ps, &Person::adult)` works directly. `mem_fn` is still useful where an interface only accepts function objects that can be written as `f(x)`, such as classic algorithms or third-party callback systems, or where you need a named object that can be stored, copied and assigned.

!!! pitfall "Overloaded member functions"
    When `Widget::draw` is overloaded, `std::mem_fn(&Widget::draw)` cannot deduce `R`. You can write `R` explicitly, `std::mem_fn<void() const>(&Widget::draw)`, or pick an overload with `static_cast` first.

!!! pitfall "Member functions of standard library types"
    Taking a member pointer to a non-static member function of a standard library class (such as `std::string::size`) has unspecified behavior and may be ill-formed ([[namespace.std#6]]) {{unspec}}. So `std::mem_fn(&std::string::size)` is not portable; use a lambda for standard library types.
