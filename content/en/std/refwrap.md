---
title: Class template reference_wrapper
summary: "reference_wrapper<T> is a copyable, assignable, trivially copyable reference wrapper; ref and cref use it to tell bind, make_pair and other components to keep an argument by reference. This page covers how its constructor constraints reject rvalues, the semantics of calling and comparison, and how it works with common_reference."
updated: 2026-10-19
---

!!! tldr
    - A `reference_wrapper<T>` is just a `T*` inside. It can be copied and put into containers; assignment makes it refer to another object instead of assigning to the referenced one. It is guaranteed to be trivially copyable.
    - The constructor is constrained using a pair of exposition-only functions `FUN(T&)` / `FUN(T&&) = delete`: rvalues and conversions that need to materialize a temporary are rejected, and the constructor does not participate in overload resolution rather than being viable but deleted.
    - `std::ref(x)` and `std::cref(x)` create it, to make components that keep their arguments by value by default, such as `bind`, `thread`, `make_pair` and `make_tuple`, keep them by reference instead. Rvalue calls such as `ref(42)` are compile errors.
    - Calling `rw(args...)` is *INVOKE*(`rw.get()`, args...). Since C++26, `==` and `<=>` compare the referenced values, not addresses.
    - Since C++23, `common_reference_t<reference_wrapper<int>&, int&>` is `int&`.

## A reference that can be rebound

```cpp run title="refwrap_tour.cpp" ok
#include <functional>
#include <type_traits>
#include <vector>
#include <algorithm>
#include <cstdio>
int main() {
  int a = 3, b = 1, c = 2;
  std::vector<std::reference_wrapper<int>> v{a, b, c};
  std::ranges::sort(v, std::less<int>{});      // compares the referenced values via operator int&
  v[0].get() = 100;                            // v[0] refers to b
  std::printf("%d %d %d\n", a, b, c);          // 3 100 2

  std::reference_wrapper rw = a;               // CTAD: reference_wrapper<int>
  std::printf("%d\n", rw == 3);                // C++26: compares the referenced value, prints 1
  rw = c;                                      // now refers to c; a is unchanged
  std::printf("%d %d\n", a, rw.get());         // 3 2
}
```

C++ references are not objects: they cannot be rebound (`r = x` assigns to the referenced object), cannot be put into a `std::vector`, and cannot be default-constructed. `reference_wrapper<T>` wraps a reference to `T` into an object. It can be copied, it can be passed by value without copying the referenced object, and assignment changes what it refers to.

Its most important use in the standard library is to say explicitly "pass by reference". `std::bind`, `std::thread`, `std::make_pair` and `std::make_tuple` by default decay their arguments and keep them by value; to make them keep a reference, pass `std::ref(x)`.

## Basic properties [refwrap.general]

| Member | Description |
|---|---|
| `using type = T;` | the referenced type |
| `template<class U> reference_wrapper(U&&)` | the only binding constructor, constrained (see the next section) |
| copy constructor, copy assignment | `noexcept`; what is copied is which object it refers to |
| `operator T&()`, `get()` | retrieve the reference |
| `operator()(ArgTypes&&...)` | calls the referenced callable via *INVOKE* |
| three `operator==` and three `operator<=>` | new in C++26, hidden friends |
| `reference_wrapper(T&) -> reference_wrapper<T>` | deduction guide |

All members are `constexpr`. There is no default constructor, because a reference must be bound to something.

¶1 `reference_wrapper<T>` meets *Cpp17CopyConstructible* and *Cpp17CopyAssignable* and wraps a reference to an object or function of type `T`. `T` can be a function type: `reference_wrapper<int(int)>` is valid, and calling it calls that function.

¶2 `reference_wrapper<T>` is a **trivially copyable type** ([[g:trivially-copyable-type]], [[basic.types]]), that is, a type whose object representation can be copied with `memcpy`. So it can be `std::bit_cast`, put into a `std::atomic`, and when passed by value the ABI usually passes it in a register. The class synopsis shows a copy constructor and a copy assignment operator, but the synopsis only describes the interface; ¶2 requires them to be trivial. libc++ simply does not declare them at all, and the class has only one member, `type* __f_;`.

¶3 `T` may be an incomplete type, so you can write `std::vector<std::reference_wrapper<Node>> children;` inside the definition of `Node`. Note 1 warns that if the comparison operators are used while `T` is incomplete, the result of checking the constraints may differ between points of instantiation, making the program ill-formed, no diagnostic required ([[temp.point]], [[temp.constr.atomic]]).

## Why the constructor is a template [refwrap.const]

The intuitive design is two constructors: `reference_wrapper(T&)` to accept lvalues and `reference_wrapper(T&&) = delete` to reject rvalues. That is exactly how C++11 wrote it. The problem is that deleted functions still participate in overload resolution:

```cpp run title="old_design_ambiguity.cpp" error
struct Old {             // mimics the C++11 design
  Old(int&) {}
  Old(int&&) = delete;
};
struct from_int { from_int(int) {} };
void meow(Old) {}
void meow(from_int) {}
int main() { meow(0); }  // error: ambiguous, both user-defined conversions are viable
```

For the argument `0`, `Old(int&&)`, although deleted, makes the user-defined conversion from `0` to `Old` viable, so it ties with the conversion to `from_int`. A deleted function only causes an error after it has been selected, and whether it is selected is decided by overload resolution.

¶1 The current constructor is a constrained template, `template<class U> reference_wrapper(U&& u)`. The constraint uses a pair of exposition-only functions:

!!! std
    Let *FUN* denote the exposition-only functions `void FUN(T&) noexcept; void FUN(T&&) = delete;`

¶2 The constraints require that the expression *FUN*(declval&lt;U&gt;()) be well-formed and that `remove_cvref_t<U>` not be `reference_wrapper` itself. In other words, call this pair of overloads with the argument; the constructor participates in overload resolution only if `FUN(T&)` is selected:

- The argument is a `T` lvalue: exact match for `FUN(T&)`, viable.
- The argument is an rvalue: `FUN(T&&)` is better (rvalues prefer binding to rvalue references, [[over.ics.rank]]), it is deleted, the call is ill-formed, and the constraint is not satisfied. The constructor is not a candidate at all.
- The argument is of a class type implicitly convertible to `T&` (for example a class with `operator int&()`): `FUN(T&)` is viable through a user-defined conversion. The old design could not do this.
- The argument is itself a `reference_wrapper`: the second condition excludes it, leaving it to the copy constructor.

[[LWG2993]] changed the constructor into this form, and the ambiguity at the beginning disappeared:

```cpp run title="fun_trick.cpp" ok
#include <functional>
#include <type_traits>
#include <cstdio>
struct from_int { from_int(int) {} };
void meow(std::reference_wrapper<int>) { std::puts("ref"); }
void meow(from_int) { std::puts("from_int"); }

struct Holder {
  int value = 7;
  operator int&() { return value; }   // can produce an int lvalue
};
static_assert(!std::is_constructible_v<std::reference_wrapper<const int>, int>);  // rvalue: blocked by the constraint
static_assert(std::is_constructible_v<std::reference_wrapper<const int>, const int&>);
int main() {
  meow(0);                            // prints from_int, no ambiguity
  Holder h;
  std::reference_wrapper<int> r = h;  // OK: FUN(h) selects FUN(int&) via the conversion function
  r.get() = 8;
  std::printf("%d\n", h.value);       // 8
}
```

The second constraint cannot be dropped either. When copying from a non-const lvalue `reference_wrapper`, the template constructor (`U = reference_wrapper&`) is a better match than the copy constructor (parameter `const reference_wrapper&`), and `FUN(rw)` is satisfiable through `operator T&`. Without this constraint, copying would be taken over by the template and turn into converting to `T&` first and then taking the address.

¶3 The effect of construction is as if `T& r = std::forward<U>(u);` were written first and then a reference to `r` stored. ¶4 Its `noexcept` matches that of `FUN(declval<U>())`: if binding the `T&` needs a conversion function that may throw, the constructor may throw too. ¶5 The copy constructor stores a reference to `x.get()`.

## Assignment, access and invocation

Assignment ([refwrap.assign]). After copy assignment, `*this` stores a reference to `x.get()`. That is, it rebinds rather than assigning to the referenced object; this is the fundamental difference from `T&`.

Access ([refwrap.access]). `operator T&()` and `get()` both return the stored reference. The implicit conversion lets a `reference_wrapper<int>` be passed directly to functions taking `int&` or `int`. Member access does not trigger the implicit conversion: `rw.member` is invalid, and you have to write `rw.get().member`.

Invocation ([refwrap.invoke]). `operator()` returns *INVOKE*(`get()`, `std::forward<ArgTypes>(args)...`) ([[func.require]]), with return type `invoke_result_t<T&, ArgTypes...>`. It requires (Mandates) `T` to be a complete type. Because it goes through *INVOKE*, a `reference_wrapper<int (S::*)()>` wrapping a member pointer can also be called.

`operator()` makes `std::ref(f)` itself a callable. When handing a stateful, non-copyable or expensive-to-copy function object to `std::for_each`, `std::thread` or `std::function`, which take it by value, passing `std::ref(f)` avoids the copy, and changes to the state are reflected in the original object.

## Comparison [refwrap.comparisons] {{c++26}}

Before C++26, whether `rw1 == rw2` compiled depended on whether `T`'s `operator==` could be found through the implicit conversion. For `int` it works: the built-in `==` is usable via the `operator int&` conversion. For `std::string` it does not: its `operator==` is a template, and template argument deduction does not consider user-defined conversions. [[P2944R3]] added three pairs of hidden friends ([[g:hidden-friend]], friend functions found only via ADL):

| Operators | Parameters | Constraints |
|---|---|---|
| `==`, `<=>` | `(reference_wrapper, reference_wrapper)` | `x.get() == y.get()` is well-formed and convertible to `bool`; *synth-three-way*(x.get(), y.get()) is well-formed |
| `==`, `<=>` | `(reference_wrapper, const T&)` | same as above, with `y` on the right |
| `==`, `<=>` | `(reference_wrapper, reference_wrapper<const T>)` | same as above, and additionally `is_const_v<T>` is false |

What is compared is the referenced values, not the addresses. To find out whether two wrappers refer to the same object, write `&a.get() == &b.get()`.

The *synth-three-way* used by `<=>` is an internal exposition-only tool of the library ([[expos.only.entity]]): if the type has `<=>` it uses that, otherwise it synthesizes a `weak_ordering` from `<`. So old types that only define `<` can also be compared with `<=>`.

The third pair requires `T` not to be const. When `T` itself is const, `reference_wrapper<const T>` is just `reference_wrapper<T>`, and this pair of overloads would have the same signatures as the first pair.

## `ref` and `cref` [refwrap.helpers]

```cpp
template<class T> constexpr reference_wrapper<T>       ref(T&) noexcept;
template<class T> constexpr reference_wrapper<const T> cref(const T&) noexcept;
template<class T> void ref(const T&&) = delete;
template<class T> void cref(const T&&) = delete;
template<class T> constexpr reference_wrapper<T>       ref(reference_wrapper<T>) noexcept;
template<class T> constexpr reference_wrapper<const T> cref(reference_wrapper<T>) noexcept;
```

For lvalues they return a wrapper. For rvalues, the `const T&&` version is a better match and it is deleted, so `std::ref(42)` and `std::cref(std::string("x"))` are both compile errors, avoiding wrapping a temporary that is about to be destroyed. It is written `const T&&` rather than `T&&` because `T&&` in a template is a forwarding reference and would take lvalues too. The two deleted declarations are in the synopsis of `<functional>` ([[functional.syn]]).

When the argument is already a `reference_wrapper`, no extra layer is added: `ref(ref(x))` is still a `reference_wrapper<T>`, and `cref(ref(x))` is a `reference_wrapper<const T>`. ¶1 The `T` of these function templates may also be an incomplete type.

```cpp run title="ref_rvalue.cpp" error
#include <functional>
int main() {
  auto r = std::ref(42);                     // error: calls the deleted ref(const T&&)
  std::reference_wrapper<const int> c(42);   // error: FUN constraint not satisfied, no viable constructor
}
```

### Which components recognize `reference_wrapper`

A few library rules recognize `reference_wrapper<T>` and treat it as `T&`:

- `make_pair` and `make_tuple` compute element types with `unwrap_ref_decay_t`: `make_pair(std::ref(x), 1)` gives `pair<int&, int>` ([[pairs]], [[tuple]]).
- When a bound argument of `bind` is a `reference_wrapper<T>`, it is passed on as `T&` at the call ([[func.bind.bind#7]]).
- Bullets ¶1.2 and ¶1.5 of *INVOKE* call `.get()` directly on a `reference_wrapper` ([[func.require]]).

`std::thread` and `bind_front` have no special unwrapping rule. They keep the `reference_wrapper` itself, hand it over at the call, and rely on `operator T&` to convert it implicitly to `T&`.

## Working with `common_reference` [refwrap.common.ref]

In C++20, `common_reference_t<reference_wrapper<int>&, int&>` is `int`, a value type. This made ranges of `reference_wrapper` behave awkwardly when combined with ordinary ranges under concepts such as `common_reference_with`. C++23's [[P2655R3]] added two partial specializations of `basic_common_reference`, and the result became `int&`:

```cpp run ok
#include <functional>
#include <type_traits>
static_assert(std::is_same_v<
    std::common_reference_t<std::reference_wrapper<int>&, int&>, int&>);
int main() {}
```

The condition for the partial specializations is: one side `R` is a `reference_wrapper`, `common_reference_t<typename R::type&, TQ>` exists, and `R` (with its original qualifiers) is convertible to it. Then `type` is `common_reference_t<typename R::type&, TQual<T>>`. The condition also requires this relationship to hold in only one direction; otherwise, when both arguments are `reference_wrapper`s, both partial specializations would match and be ambiguous.

## Class template argument deduction

The deduction guide `reference_wrapper(T&) -> reference_wrapper<T>` makes `std::reference_wrapper rw = x;` deduce `reference_wrapper<int>` ([[temp.deduct.guide]]). Without it nothing could be deduced: the `U` in the constructor template `reference_wrapper(U&&)` is unrelated to the class template parameter `T`.

## History and evolution

!!! history
    - C++11: introduced from TR1, with the constructor `reference_wrapper(T&)` plus a deleted `reference_wrapper(T&&)`.
    - C++17: the deduction guide was added; *INVOKE* recognizes `reference_wrapper` directly.
    - C++20: became `constexpr`; the constructor became a template constrained with `FUN` ([[LWG2993]]); `T` may be an incomplete type ([[P0357R3]]).
    - C++23: the partial specializations of `basic_common_reference` ([[P2655R3]]).
    - C++26: `==` and `<=>` ([[P2944R3]]).

## Questions

!!! question "Question 1"
    Does `std::reference_wrapper<const std::string> r = "hello";` compile? What about initializing it with a `std::string_view` lvalue?

<details markdown="1">
<summary>Answer</summary>

Neither compiles. For `"hello"`, both `FUN(const string&)` and `FUN(const string&&)` first need a user-defined conversion constructing a temporary `std::string`; the two conversion sequences use the same conversion function, so the subsequent reference bindings are compared, and an rvalue binding to an rvalue reference is better, so the deleted `FUN(T&&)` is selected and the constraint is not satisfied.

The conversion from `string_view` to `string` is `explicit`, so neither overload of `FUN` is viable, and again the constraint is not satisfied. `FUN` rejects every case where binding would require materializing a temporary.
</details>

!!! question "Question 2"
    Why is `std::function<void()> f = std::ref(callable);` a common optimization? What is the risk?

<details markdown="1">
<summary>Answer</summary>

A `reference_wrapper` is only one pointer in size and trivially copyable, so `std::function` implementations can usually put it in their internal small buffer without a heap allocation; copying `f` also copies only one pointer instead of a potentially large `callable`.

The risk is lifetime: `f` does not own `callable`, and if `callable` is destroyed first, `f` dangles. C++26's `std::function_ref` turns this kind of non-owning call into a dedicated type ([[func.wrap.ref]]).
</details>
