---
title: Visiting variants
summary: "The rules of std::visit, visit<R> and C++26's member visit: the visitor must handle every combination, the result types must agree, valueless variants throw, a single variant is visited in constant time; plus the overload pattern and libc++'s function-pointer table implementation."
updated: 2026-10-19
---

!!! tldr
    - `std::visit(f, vs...)` finds out at run time which type each variant currently holds and calls `f` with values of those concrete types; `f` must handle every combination of types, and missing one fails compilation.
    - Without an explicit return type, the calls for all combinations must have the same type and the same value category; to unify them into one type, use C++20's `visit<R>`.
    - If any argument holds no value (valueless), `bad_variant_access` is thrown; when visiting a single variant, the call must be made in constant time.
    - Classes derived from variant can be passed to `visit` directly; C++26 also adds the member function `v.visit(f)`.
    - The overload pattern, which assembles a visitor from a set of lambdas, is just ordinary overload resolution: implicit conversions happen as usual, and a missing branch is not necessarily an error.

For the declaration of `visit` and the basic concepts of `variant`, see [[variant]]. `visit` hands the call to *INVOKE* ([[func.require]]), so the visitor can be any callable object, including a member pointer.

## What visit does

```cpp run title="visit-basic.cpp" ok
#include <cassert>
#include <string>
#include <variant>

int main() {
  std::variant<int, double, std::string> v = 3.5;
  auto size = [](const auto& x) { return sizeof(x); };
  assert(std::visit(size, v) == sizeof(double));
  v = std::string("hi");
  assert(std::visit(size, v) == sizeof(std::string));
}
```

The `operator()` of a generic lambda is a template, and `visit` instantiates it once for each alternative. At run time `visit` reads `v.index()` and calls the corresponding one. In other words, it turns a run-time index into a compile-time overload choice: no hand-written `switch`, and no branch can be forgotten.

[variant.visit] specifies two non-member function templates and two member function templates:

```cpp
template<class Visitor, class... Variants>
  constexpr see below visit(Visitor&& vis, Variants&&... vars);  // ①
template<class R, class Visitor, class... Variants>
  constexpr R visit(Visitor&& vis, Variants&&... vars);          // ② C++20

// members of variant, C++26
template<class Self, class Visitor>
  constexpr decltype(auto) visit(this Self&& self, Visitor&& vis);  // ③
template<class R, class Self, class Visitor>
  constexpr R visit(this Self&& self, Visitor&& vis);               // ④
```

## The form of the call (¶4–6)

¶4 Suppose there are `n` variants among the arguments. Taking one index from each variant forms a pack `m`; as long as each index is in range, the pack is valid. For each valid `m`, the standard defines a call expression `e(m)`:

```cpp
INVOKE(std::forward<Visitor>(vis), GET<m>(std::forward<V>(vars))...)     // form ①
INVOKE<R>(std::forward<Visitor>(vis), GET<m>(std::forward<V>(vars))...)  // form ②
```

Note `std::forward<V>(vars)`: the arguments' value categories and constness are passed on to *GET*. In `std::visit(f, std::move(v))` the visitor receives the alternative as an rvalue; in `std::visit(f, std::as_const(v))` it receives a `const` lvalue.

¶6 What is actually executed is the `e(m)` corresponding to the current indices of the variants, and the return type of form ① is `decltype(e(m))`.

## Every combination must be valid, and the results must agree (¶5)

!!! std
    *Mandates*: For each valid pack `m`, `e(m)` is a valid expression. All such expressions are of the same type and value category.

This sentence has two parts.

First, the visitor must handle every combination. If two variants have 3 and 2 alternatives, all 6 calls must be valid. This is *Mandates* ([[structure.specifications]]): if it is not met, compilation fails outright; `visit` does not drop out of overload resolution.

Second, the results of all combinations must have the same type and value category, regardless of which type is actually held on this run. This often surprises people:

<div class="compare" markdown="1">

```cpp error
#include <variant>
int main() {
  std::variant<int, double> v = 1;
  // one returns int, the other double
  auto r = std::visit(
      [](auto x) { return x; }, v);
  (void)r;  // error on the previous line
}
```

```cpp error
#include <variant>
int g;
struct F {
  int& operator()(int) const { return g; }
  int operator()(double) const { return 0; }
};
int main() {
  std::variant<int, double> v = 1;
  // different value categories: lvalue and prvalue
  (void)std::visit(F{}, v);  // error
}
```

</div>

libc++ gives the same `static_assert` message for both cases: "`std::visit` requires the visitor to have a single return type."

Why not take the common type automatically? That would introduce implicit conversions the visitor never wrote. If you want a unified return type, write it out explicitly; that is form ②.

### visit<R>

Form ② uses *INVOKE*<R>: the result of each call is implicitly converted to `R`; when `R` is `void` the result is discarded. The original result types of the calls may differ, as long as they all convert to `R`. It was added in C++20 by [[P0655R1]].

```cpp run title="visit-r.cpp" ok
#include <cassert>
#include <string>
#include <type_traits>
#include <variant>

int main() {
  std::variant<int, double> v = 1;
  double r = std::visit<double>([](auto x) { return x; }, v);
  assert(r == 1.0);  // both int and double convert to double

  int calls = 0;
  std::visit<void>([&](auto x) { ++calls; return x; }, v);
  assert(calls == 1);  // R = void: result discarded

  std::variant<int, std::string> w = "abc";
  auto n = w.visit<std::size_t>([](const auto& x) {  // member visit<R>
    if constexpr (std::is_same_v<std::decay_t<decltype(x)>, int>) return x;
    else return x.size();
  });
  assert(n == 3);
}
```

## Exceptions and complexity (¶7–8)

¶7 If any argument variant is valueless (see [[variant.variant]]), `visit` throws `bad_variant_access`, and the visitor is never called.

```cpp run title="visit-valueless.cpp" ok
#include <cassert>
#include <variant>

struct S { operator int() { throw 42; } };

int main() {
  std::variant<float, int> v{12.f};
  try { v.emplace<1>(S()); } catch (int) {}  // v loses its value
  try {
    std::visit([](auto) {}, v);
    assert(false);
  } catch (const std::bad_variant_access&) {}
}
```

¶8 specifies the complexity:

!!! std
    For *n* ≤ 1, the invocation of the callable object is implemented in constant time, i.e., for *n* = 1, it does not depend on the number of alternative types of `V_0`. For *n* > 1, the invocation of the callable object has no complexity requirements.

This is a normative requirement. When visiting a single variant, it cannot be implemented as a chain of `if`s comparing indices one by one; even with 100 alternatives it must take constant time. In practice this means a jump table (an array of function pointers), or a `switch` the compiler can turn into a jump table.

There is no requirement when visiting several variants, because `k` variants with `N` alternatives each have `N^k` combinations, and the standard does not want to force implementations to generate tables of exponential size. When `n` is 0, `visit(f)` is just a direct call `f()`.

## Classes derived from variant (¶1–3)

```cpp run title="visit-derived.cpp" ok
#include <cassert>
#include <variant>

struct Expr : std::variant<int, double> {
  using variant::variant;
};

int main() {
  Expr e = 2.5;
  double d = std::visit([](auto x) { return double(x); }, e);
  assert(d == 2.5);
  assert(e.visit([](auto x) { return x > 0; }));  // member visit
}
```

Deriving from variant is a natural way to define recursive data structures such as expression trees. `visit` can accept `Expr` thanks to a set of exposition-only function templates *as-variant* ([[g:as-variant]]) defined in ¶1: they accept the four kinds of references to `variant<Ts...>` (`&`, `const&`, `&&`, `const&&`) and return them unchanged.

`visit` first passes each argument to *as-variant*, and the type of the result is written `V_i`. The constraint in ¶2 requires each `V_i` to be a valid type. Because *as-variant* is a function template, when template argument deduction is done against the parameter `variant<Ts...>&` and the argument is a class derived from some variant specialization, deduction yields that base class ([[temp.deduct.call]]). So:

- if the argument is a variant itself, `V_i` is its reference type;
- if the argument is unambiguously and accessibly derived from some variant specialization, `V_i` is a reference to that base class, and the visit operates on that base class subobject;
- if the argument is not a variant, or is derived from several variant specializations so that deduction is ambiguous, `V_i` is not valid and `visit` does not participate in overload resolution.

```cpp run title="visit-ambiguous-base.cpp" error
#include <variant>

struct Both : std::variant<int>, std::variant<double> {};

int main() {
  Both b;
  std::visit([](auto) {}, b);  // error: as-variant deduction is ambiguous
}
```

!!! history "Why as-variant is needed"
    C++17's `visit` required the arguments to be variants and described its rules with type traits such as `variant_size_v<remove_reference_t<Variants>>`. `variant_size<Expr>` has no specialization, so deriving from variant compiled on some implementations and not on others. [[P2162R2]] unified the rules with *as-variant* and went into C++23, and implementations adopted it in C++17 mode as well. libc++'s `__cpp_lib_variant` is `202102L`, indicating that this change is implemented.

## Member visit (¶9–13)

C++26's [[P2637R3]] added a member `visit` to variant, written with an explicit object parameter (deducing this, [[dcl.fct]]).

¶9 First let `V` be *OVERRIDE_REF*(`Self&&`, *COPY_CONST*(`remove_reference_t<Self>`, `variant`)) ([[forward]]), meaning that `self`'s constness and kind of reference are copied onto `variant`. ¶11 The effect is equivalent to `return std::visit(std::forward<Visitor>(vis), (V)self);`. ¶13 The `visit<R>` version is analogous and forwards to `std::visit<R>`.

The conversion `(V)self` is necessary: `Self` may be a derived class like `Expr`, which is first converted to a reference to the base variant and then handed to the non-member `visit`.

¶10 has an inconspicuous constraint:

!!! std
    *Constraints*: The call to `visit` does not use an explicit *template-argument-list* that begins with a type *template-argument*.

The reason lies in the template parameter lists of the two member templates. ③ is `<class Self, class Visitor>`, ④ is `<class R, class Self, class Visitor>`. Someone who writes `v.visit<int>(f)` wants to call ④ with `R = int`, but for ③ the explicitly given `int` would be taken as `Self`, leading to a wrong selection or a baffling error. ¶10 excludes ③ from such calls.

libc++ does this by putting, at the very front of ③'s template parameter list, a constant template parameter whose type is a private tag class, `__variant_visit_barrier_tag`, with a default argument. No explicit template argument list that begins with a type can match it, so ③ is naturally not viable.

The benefit of member `visit` is mainly in how it reads: `v.visit(f)` puts the object first and the operation after, consistent with chained calls, and there is no need to convert a derived class to variant first.

## The overload pattern

Assembling a visitor from a set of lambdas is the most common use of `visit`, known as the **overload pattern** ([[g:overload-pattern]]):

```cpp run title="overloaded.cpp" ok
#include <cassert>
#include <string>
#include <variant>

template<class... Ts>
struct overloaded : Ts... { using Ts::operator()...; };

int main() {
  std::variant<int, double, std::string> v = 3.5;
  auto describe = overloaded{
    [](int) { return std::string("int"); },
    [](double) { return std::string("double"); },
    [](const std::string& s) { return "string:" + s; },
  };
  assert(std::visit(describe, v) == "double");
  v = "hi";
  assert(std::visit(describe, v) == "string:hi");

  // two variants: the visitor must handle 3×2 = 6 combinations
  std::variant<int, std::string> w = 7;
  auto both = std::visit([](const auto& a, const auto& b) {
    return sizeof(a) + sizeof(b);
  }, v, w);
  assert(both == sizeof(std::string) + sizeof(int));
}
```

The two-line definition of `overloaded` uses three language features:

1. Closure types are ordinary classes ([[expr.prim.lambda.closure]]) and can be used as base classes.
2. The pack expansion in a using-declaration, `using Ts::operator()...;` (C++17, [[P0195R2]], [[namespace.udecl]]), brings the `operator()` of every base into the same scope, forming one overload set. Without this line, same-named members of different bases would make name lookup ambiguous ([[class.member.lookup]]).
3. `overloaded` is an aggregate with no constructors, and each lambda initializes one base class subobject ([[dcl.init.aggr]]). C++17 needed a hand-written deduction guide `template<class... Ts> overloaded(Ts...) -> overloaded<Ts...>;`; C++20's [[P1816R0]] introduced the **aggregate deduction candidate** ([[g:aggregate-deduction-candidate]], [[over.match.class.deduct]]), with which the compiler generates this guide automatically from the aggregate's elements.

!!! pitfall "The overload pattern is just ordinary overload resolution"
    Which lambda is chosen is decided by ordinary overload resolution on `vis(alt)`, and implicit conversions happen as usual:

    ```cpp run title="overload-trap.cpp" ok
    #include <cassert>
    #include <string>
    #include <variant>

    template<class... Ts>
    struct overloaded : Ts... { using Ts::operator()...; };

    int main() {
      std::variant<std::string, bool> v = std::string("x");
      auto r = std::visit(overloaded{
        [](bool) { return 1; },
        [](const auto&) { return 2; },
      }, v);
      assert(r == 2);  // the generic lambda is an exact match

      std::variant<char, double> w = 'a';
      auto r2 = std::visit(overloaded{
        [](int) { return 1; },
        [](double) { return 2; },
      }, w);
      assert(r2 == 1);  // no char branch: char→int is a promotion
    }
    ```

    The second example shows that forgetting a branch does not necessarily fail compilation, as long as an existing branch can catch it through an implicit conversion. When strict exhaustiveness is needed, add one more base, `struct strict { template<class T> void operator()(T) = delete; };`, written as `overloaded{..., strict{}}`. Any type without an exact match then selects this deleted template and causes an error.

## The libc++ implementation: a table of function pointers

libc++ builds an N-dimensional array of function pointers at compile time, and at run time picks one entry by index and calls it:

1. For each combination of indices `(I_0, I_1, ...)`, a dispatch function is instantiated, which simply calls the visitor with `__get_alt<I_0>(v0), __get_alt<I_1>(v1), ...`;
2. The addresses of these functions are put into nested `__farray<FnPtr, N>`, and the whole table is a `constexpr` local variable;
3. The table is indexed dimension by dimension using each variant's index, and the resulting function pointer is called.

Each of the requirements in the specification has a counterpart in the implementation:

- The agreement of results in ¶5: all function pointers must have the same type to go into one array; when they do not, the `static_assert` mentioned above fires.
- Exhaustiveness in ¶5: `visit<R>` checks with `static_assert(is_invocable_v<...>)` before the call, with the message "`std::visit` requires the visitor to be exhaustive.". `std::visit` without `R` never reaches this assertion: SFINAE in the trailing return type of the internal dispatch function fails first, and Clang 23 reports "no matching function for call to '__invoke'" and "cannot deduce return type 'auto'".
- The valueless check in ¶7: `__throw_if_valueless` is called before the table lookup, because the valueless marker is not a valid index.
- The constraint in ¶2: the declaration of `visit` carries a default template argument `void_t<decltype(std::__as_variant(std::declval<_Vs>()))...>`, implemented with SFINAE.
- The complexity in ¶8: the table lookup is O(1). With several variants, the size of the table is the product of the numbers of alternatives, and compile time and code size grow with it.

variant's own copy construction, assignment, `swap`, comparison operators and `hash` also reuse this dispatch machinery.

!!! impl "The code after optimization"
    The function-pointer table is `constexpr`, and the optimizer can see through it. In our tests (arm64, `-O2`), calling `std::visit([](auto x) { return f(x); }, v)` on a `variant<A, B, C>` (where `f` is overloaded as three external functions), Clang 23 generates a few index comparisons plus three direct tail calls, with no indirect jump. So there is no need to assume `visit` is necessarily slower than a `switch`; at `-O0`, though, it really does go through several layers of function calls.

## Questions

!!! question "Question 1"
    `v` is an lvalue `variant<int, double>`. Does `std::visit([](auto&& x) -> decltype(auto) { return x; }, v)` compile? What if the return statement is changed to `return (x);`?

<details markdown="1">
<summary>Answer</summary>

Neither compiles. With `return x;`, `decltype(auto)` deduces `decltype(x)`, the declared type of the parameter: `int&` for the `int` branch and `double&` for the `double` branch, which are different types, violating ¶5. With `return (x);` it deduces `decltype((x))`; `x` is an lvalue, which again gives `int&` and `double&`. Only making all branches return the same type (such as `return double(x);` in each), or switching to `visit<R>`, gets it through. The check that results agree applies to all combinations, regardless of which type is actually held at run time.
</details>

!!! question "Question 2"
    When visiting a single variant, is an implementation that does a binary search on the index (O(log N)) conforming? Does variant's copy constructor have a similar complexity requirement?

<details markdown="1">
<summary>Answer</summary>

It is not conforming. ¶8 says explicitly that for *n* = 1 the invocation does not depend on the number of alternatives, and O(log N) depends on N. This requirement applies only to `visit`: [variant.ctor] and [variant.assign] have no *Complexity* element, so at the level of the standard copy construction and assignment can dispatch any way they like; actual implementations all reuse the `visit` machinery. Also, ¶8 constrains the invocation of the callable object, not the valueless check in ¶7, and that check is just one comparison for *n* = 1 anyway.
</details>

## Summary

| Aspect | Rule |
|---|---|
| Acceptable arguments | a variant, or a class unambiguously derived from some variant specialization (*as-variant*, a constraint) |
| Form of the call | `INVOKE(vis, GET<m>(std::forward<V>(vars))...)`, with value category and const passed on from the arguments |
| Compile-time requirements | every combination is callable; for form ①, all results have the same type and value category |
| `visit<R>` (C++20) | each result is implicitly converted to `R`; discarded when `R = void` |
| Exceptions | throws `bad_variant_access` when any argument is valueless |
| Complexity | constant time for one variant; no requirement for several |
| Member `visit` (C++26) | equivalent to `std::visit(vis, (V)self)`; `v.visit<Type>(f)` only matches the version with `R` |
| Overload pattern | inheriting from lambdas, `using Ts::operator()...`, class template argument deduction for aggregates |
