---
title: Class template constant_wrapper
summary: "C++26's std::constant_wrapper and std::cw encode a compile-time value in a type, so a constant passed as a function argument can still be used in constant expressions inside the function body, and operations on it still produce a constant_wrapper."
updated: 2026-10-19
---

!!! tldr
    - A function parameter is not a constant expression, even if a literal was passed in the call. `std::cw<42>` puts the value in the type and the object itself is empty, so after being passed as a parameter it can still be used as a constant.
    - Operations on `constant_wrapper` yield another `constant_wrapper`: the type of `cw<42> + cw<13>` is `constant_wrapper<55>`. Mix in a single ordinary value and it degrades to an ordinary operation.
    - `&&` and `||` do not wrap `bool` values, to preserve short-circuit evaluation; the comma operator is deleted; `++cw<5>` is an error.
    - The second template parameter `T` is only a shadow of `decltype(X)`; its purpose is to let ADL find functions in the namespace of the wrapped value. Specifying a different type is ill-formed.
    - `operator()` and `operator[]` return a `constant_wrapper` when all arguments are `constant_wrapper`s, and otherwise degrade to an ordinary call and subscript.

## A parameter is not a constant expression

<div class="compare" markdown="1">

```cpp error
#include <array>
auto make(int n) {
  // error: n is not a constant expression
  return std::array<int, n>{};
}
```

```cpp ok
#include <array>
#include <utility>
auto make(auto n) {
  return std::array<int, n>{};  // OK
}
auto a = make(std::cw<3>);
```

</div>

In the `make` on the left, even if it is declared `constexpr` and even if a literal is passed in the call, `n` cannot be used as a template argument inside the function body. The same function can be called at run time with any value, and the rules for constant expressions ([[expr.const]]) do not allow reading a parameter whose value is unknown.

On the right, the type of `n` is `std::constant_wrapper<3>`. The template argument needs a `size_t` constant, so `n`'s conversion function is called, which returns the static data member `value`. That call reads no state of the object `n` (it is an empty class and has no state to begin with), so the whole expression is still a constant expression. The value lives in the type; the object is just an empty shell.

Encoding a value in a type has been done for a long time: `std::integral_constant<int, 3>` ([[meta.help]]). But it can only wrap integral and enumeration types, it is verbose, and adding two `integral_constant`s yields a plain `int`, so constness is lost as soon as you compute anything. {{c++26}} `std::constant_wrapper<X>` (with the shorthand variable template `std::cw<X>`) fills these gaps.

!!! std "[const.wrap.class]/1"
    The class template `constant_wrapper` aids in metaprogramming by ensuring that the evaluation of expressions comprised entirely of `constant_wrapper` are core constant expressions ([expr.const.core]), regardless of the context in which they appear.

¶1 An expression made up entirely of `constant_wrapper`s is a [[g:core-constant-expression|core constant expression]] when evaluated in any context, including operations on parameters inside a function body. The values that can be wrapped are any values that can be constant template arguments, that is, values of [[g:structural-type|structural type]] ([[temp.param]]), not just integers.

## Operations still produce a constant_wrapper

```cpp run title="cw_basic.cpp" ok
#include <utility>
#include <type_traits>

constexpr auto add(auto a, auto b) { return a + b; }

int main() {
  auto r = add(std::cw<42>, std::cw<13>);
  static_assert(std::is_same_v<decltype(r), std::constant_wrapper<55>>);
  static_assert(r == 55);                  // implicit conversion to int
  static_assert(decltype(r)::value == 55);

  constexpr auto x = add(42, 13);          // ordinary integers: the result is just int
  static_assert(x == 55);
}
```

The standard's example in ¶3 uses exactly this property. The function `final_phase(auto gathered, auto available)` contains `if constexpr (gathered == available)`. When `constant_wrapper`s are passed, the result of `==` is `constant_wrapper<true>` or `constant_wrapper<false>`, which is then converted to `bool`, and that is a constant expression; when plain `int`s are passed, `==` has to read the values of both parameters, which is not a constant expression, so compilation fails.

### How the operators are defined

`constant_wrapper` publicly inherits from an exposition-only class `cw-operators`, where all the operators are defined in a uniform form:

```cpp
template<constexpr-param L, constexpr-param R>
  friend constexpr auto operator+(L, R) noexcept
    -> constant_wrapper<(L::value + R::value)> { return {}; }
```

The concept `constexpr-param` (defined in the synopsis in [[utility]]) requires that `typename constant_wrapper<T::value>` be valid: `T` has a static member `value`, and that value can itself be wrapped. It only checks for `::value`, so `std::integral_constant` satisfies it too.

The computation happens in the return type. If `L::value + R::value` is not a constant expression (for example division by zero or signed overflow), or the result cannot be a template argument, substitution fails and this template is removed from overload resolution (SFINAE: when template argument substitution fails, only that candidate is discarded, without an error; see [[temp.deduct]]). The expression then converts the operands to the wrapped values and uses the built-in operator instead.

These operators are all [[g:hidden-friend|hidden friends]]: friend functions defined in the class, not found by ordinary lookup, only by ADL (argument-dependent lookup, which looks up functions in the associated classes and namespaces of the argument types; see [[basic.lookup.argdep]]). `cw-operators` is a base class of `constant_wrapper` and therefore an associated class, so they are found as long as one operand is a `constant_wrapper`.

```cpp run title="cw_ops.cpp" ok
#include <utility>
#include <type_traits>
using std::cw, std::constant_wrapper, std::is_same_v;
static_assert(is_same_v<decltype(cw<1> < cw<2>), constant_wrapper<true>>);
static_assert(is_same_v<decltype(-cw<3>), constant_wrapper<-3>>);
static_assert(is_same_v<decltype(cw<1> + std::integral_constant<int, 2>{}),
                        constant_wrapper<3>>);
static_assert(is_same_v<decltype(cw<2> + 3), int>);             // ordinary value mixed in: int
static_assert(is_same_v<decltype(cw<true> && cw<false>), bool>); // built-in &&
int main() {}
```

The unary operators provided by `cw-operators` are `+ - ~ ! & *`; the binary operators are the arithmetic, bitwise, shift and comparison operators (including `<=>`) and `->*`. There are three special arrangements among them.

**`&&` and `||`**: these carry a requires-clause and are usable only when the value of at least one side cannot construct a `bool`. When both sides can be converted to `bool`, the expression uses the built-in `&&` and `||` instead, preserving short-circuit evaluation. An overloaded `&&` is an ordinary function call, and both operands are evaluated ([[over.match.oper]]). The wrapped versions exist only for user types that overload `&&`.

**Comma**: `operator,` is deleted; `(cw<1>, cw<2>)` is an error.

**Pseudo-mutators**: `++`, `--` and the compound assignments such as `+=` are declared with an explicit object parameter (`this T`), with return types like `constant_wrapper<(++T::value)>`. For an `int` value, `++T::value` would modify a constant, which is not a valid constant expression, so they are removed, and `++cw<5>` is an error. They serve wrapped user types: if some literal type's `operator++` is a `const` member that returns a new value, `++cw<obj>` yields a `constant_wrapper` of the new value.

```cpp run title="cw_errors.cpp" error
#include <utility>
int main() {
  auto x = std::cw<5>;
  auto y = ++x;                     // error: ++T::value is invalid; no usable ++
  auto q = (std::cw<1>, std::cw<2>); // error: the comma operator is deleted
}
```

## The class definition

```cpp
template<auto X, class T = decltype(X)>
struct constant_wrapper : cw-operators {
  static constexpr decltype(auto) value = (X);
  using type = constant_wrapper;
  using value_type = decltype(X);
  // operator=, conversion function, static operator(), static operator[]
};
template<auto X>
  constexpr auto cw = constant_wrapper<X>{};
```

The parentheses in `value`'s initializer `(X)` are intentional. For an `X` of scalar type, `(X)` is a prvalue and `value` is simply a constant `int` or the like. For an `X` of class type, a constant template parameter is an lvalue that refers to a **template parameter object** ([[g:template-parameter-object|template parameter object]]; there is only one such object for a given value in the whole program; see [[temp.param]]), so `(X)` has type `const T&` and `value` is a reference bound to that object. This avoids copying a potentially large object, and `&cw<obj>.value` is the same address throughout the program.

`type` refers to the class itself, consistent with `integral_constant`. The conversion function `operator decltype(value)() const` returns `value`, so `cw<5>` can be used anywhere an `int` is needed. `operator=` is a `const` member returning `constant_wrapper<(value = R::value)>`; like the pseudo-mutators, it only makes sense for special user types.

### The second template parameter is for ADL (¶2)

¶2 If `constant_wrapper` is instantiated with a `T` for which `is_same_v<T, value_type>` does not hold, the program is ill-formed. Users cannot specify the second argument themselves; it is only a shadow of `decltype(X)`.

Note 1 explains why it exists. The associated entities of ADL include the type template arguments of a class template specialization, but not the types of constant template arguments. With only `template<auto X>`, `constant_wrapper<geo::Point{3, -4}>` would have no connection to the namespace `geo`. With the extra `class T = decltype(X)`, `geo::Point` becomes a type template argument and `geo` is an associated namespace:

<div class="compare" markdown="1">

```cpp ok
#include <utility>
namespace geo {
  struct Point { int x, y; };
  constexpr int norm1(Point p)
    { return p.x + p.y; }
}
constexpr auto p =
  std::cw<geo::Point{3, 4}>;
// ADL finds geo::norm1,
// then the conversion function gives a Point
static_assert(norm1(p) == 7);
```

```cpp error
template<auto X> struct W {
  operator decltype(X)() const
    { return X; }
};
namespace geo {
  struct Point { int x, y; };
  constexpr int norm1(Point p)
    { return p.x + p.y; }
}
// error: ADL cannot find geo::norm1
int r = norm1(W<geo::Point{3, 4}>{});
```

</div>

## Calls and subscripts (¶4–¶11)

`constant_wrapper` has a static `operator()` and a static `operator[]` (C++23 allows static call operators and multi-argument subscripts).

¶4 First, *call-expr* is defined. If, after removing cv and references, all argument types satisfy `constexpr-param`, and `constant_wrapper<INVOKE(value, remove_cvref_t<Args>::value...)>` is a valid type, then *call-expr* is an object of that type, and the result is still a constant. Otherwise *call-expr* is `INVOKE(value, std::forward<Args>(args)...)`, that is, an ordinary call.

¶5–¶7 `operator()` is constrained on *call-expr* being valid, its effect is to return *call-expr*, and its exception specification is `noexcept(call-expr)`. See [[func.require]] for the meaning of *INVOKE*; the wrapped value can therefore be any callable, such as a function pointer, a lambda or a member pointer.

¶8–¶11 specify `operator[]` in parallel, with `value[...]` in place of *INVOKE*.

```cpp run title="cw_call.cpp" ok
#include <utility>
#include <type_traits>
#include <cstdio>

constexpr int twice(int a) { return a * 2; }
constexpr int table[] = {10, 20, 30};

void check(auto a, auto b) {
  if constexpr (a == b)                 // a and b are ordinary function parameters
    std::puts("equal");
  else
    std::puts("different");
}

int main(int argc, char**) {
  auto c = std::cw<twice>(std::cw<21>);   // all constant_wrapper: so is the result
  static_assert(std::is_same_v<decltype(c), std::constant_wrapper<42>>);

  int rt = std::cw<twice>(argc);          // run-time argument mixed in: ordinary call
  auto e = std::cw<table>[std::cw<1>];    // subscripts work the same way
  static_assert(e == 20);

  check(std::cw<1> + std::cw<2>, std::cw<3>);   // prints equal
  std::printf("%d\n", rt);
}
```

## Compared with integral_constant

| | `integral_constant<T, v>` | `constant_wrapper<X>` |
|---|---|---|
| Wrappable values | integral and enumeration types | values of any structural type (class objects, pointers, function pointers, etc.) |
| Shorthand | a few aliases like `bool_constant`, `true_type` | `cw<X>`, with the type deduced automatically |
| Result of operations | converted to `T`, built-in operator, result is an ordinary value | wrapped again as a `constant_wrapper` |
| Calls, subscripts | `operator()` returns the value itself | the result is still a `constant_wrapper` when all arguments are constants |
| ADL association | `T` | `decltype(X)`, via the shadow parameter |

The two can be mixed, because `integral_constant` also satisfies `constexpr-param`.

`constant_wrapper` is well suited to passing compile-time parameters to ordinary functions: the call is written `f(cw<3>)` instead of `f<3>()`, and the same function with an `auto` parameter can also accept run-time values. The standard library uses it this way itself: `std::function_ref` uses an argument of `constant_wrapper` type to indicate that the function to call is determined at compile time ([[func.wrap.ref]]), and the slicing interface of multidimensional views also accepts it to denote ranges known at compile time ([[views.multidim]]).

!!! impl "libc++ 23"
    libc++ 23 already implements `constant_wrapper`, and the feature-test macro `__cpp_lib_constant_wrapper` is `202606L`. The implementation is in `__utility/constant_wrapper.h`: the default argument of the second template parameter is written `remove_cvref_t<decltype(_Xp)>`; the `operator()` and `operator[]` that the draft describes as a choice between two forms of *call-expr* are split into two pairs of overloads with mutually exclusive constraints; most operators carry `[[nodiscard]]`.

!!! history
    This facility comes from [[P2781]]. It was originally called `std::constexpr_v`, was renamed to `constexpr_wrapper` and then `constant_wrapper` during revision, and entered C++26 under the latter name. Its wording has also changed since it entered the draft: in the current draft `operator()` and `operator[]` degrade to ordinary calls when there are run-time arguments, which is not quite the same as in earlier versions. libc++'s feature-test macro value `202606L` reflects the newer revision. When reading older material, go by the current draft.

## Questions

!!! question "Question 1"
    What is the type of `std::cw<1> + 2`? And of `std::cw<1> + std::integral_constant<int, 2>{}`?

<details markdown="1">
<summary>Answer</summary>

The former is `int`. `int` has no `::value` and does not satisfy `constexpr-param`, so `cw-operators`'s `operator+` is not viable; `cw<1>` is turned into an `int` by its conversion function and the built-in addition is used ([[over.built]]).

The latter is `constant_wrapper<3>`. `integral_constant<int, 2>` has a static member `value`, and `constant_wrapper<2>` is valid, so it satisfies `constexpr-param` and the wrapping version is selected. ADL can find this hidden friend because the left operand's base class `cw-operators` is an associated class.
</details>

!!! question "Question 2"
    Why is the result of `cw<true> && cw<false>` a `bool` rather than `constant_wrapper<false>`? What does this design give up, and what does it keep?

<details markdown="1">
<summary>Answer</summary>

The requires-clause of `operator&&` requires that the value of at least one side cannot construct a `bool`. When both sides are `bool`, this is not satisfied, the wrapping version does not participate in overload resolution, and the expression converts both sides to `bool` and uses the built-in `&&`.

What is given up is the result type: it is no longer a `constant_wrapper`. The result is still a constant expression, though, because neither conversion reads object state. What is kept is short-circuit evaluation: an overloaded `&&` is an ordinary function call and both sides are evaluated, whereas the built-in `&&` does not evaluate the right side when the left side is false.
</details>
