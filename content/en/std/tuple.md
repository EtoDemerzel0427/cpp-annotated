---
title: Tuples
summary: "std::tuple and the tuple-like protocol: the tuple_size/tuple_element/get protocol that user types can join versus the tuple-like concept that only accepts standard types, constructor constraints and disambiguation, allocator construction, tie, forward_as_tuple, tuple_cat, apply, make_from_tuple, and the comparison and common_reference specializations."
updated: 2026-10-19
---

!!! tldr
    - Structured bindings accept an open protocol: any type that specializes `tuple_size` and `tuple_element` and provides `get` can be used in `auto [a, b] = x;`.
    - `apply`, `tuple_cat`, `make_from_tuple` and `tuple`'s converting constructors accept the closed *tuple-like* concept, which admits only `array`, `complex`, `pair`, `tuple` and `ranges::subrange`.
    - The greedy forwarding constructor `tuple(UTypes&&...)` carries a disambiguating constraint that keeps it from stealing a single-element `tuple`'s copy and allocator-tag construction; libc++ 23 does not implement the latter part.
    - Once the result of `forward_as_tuple` is stored in a named variable, its references to temporaries dangle; the case where `make_from_tuple<T&>` would create a dangling reference is stopped by *Mandates*.
    - The constness of `get` is shallow: the element of a `const tuple<int&>` is still `int&`, and an lvalue reference element in an rvalue `tuple` is still an lvalue.

[tuple.general] ¶1 `std::tuple<Types...>` is a heterogeneous, fixed-size collection of any number of values; a two-element `tuple` behaves similarly to a `pair` of the same two types. The design shared with `pair` (conditional `explicit`, assignment through references, `const` assignment, forbidding dangling reference members) is covered in [[pairs]]; this page focuses on what is specific to `tuple`.

A few labels in library wording: if *Constraints* are not satisfied, the function does not participate in overload resolution; if *Mandates* are not satisfied, the program is ill-formed; if *Preconditions* are not satisfied, the behavior is undefined ([[structure.specifications]]).

## Two kinds of tuple-like: an open protocol and a closed concept

<div class="compare" markdown="1">

```cpp ok
#include <tuple>
#include <cstddef>
using std::size_t;
struct Vec2 { double x, y; };
template<> struct std::tuple_size<Vec2>
  : std::integral_constant<size_t, 2> {};
template<size_t I>
struct std::tuple_element<I, Vec2>
  { using type = double; };
template<size_t I>
double get(const Vec2& v)
  { return I == 0 ? v.x : v.y; }

double f(Vec2 v) {
  auto [a, b] = v;   // OK
  return a + b;
}
```

```cpp error
#include <tuple>
#include <cstddef>
using std::size_t;
struct Vec2 { double x, y; };
template<> struct std::tuple_size<Vec2>
  : std::integral_constant<size_t, 2> {};
template<size_t I>
struct std::tuple_element<I, Vec2>
  { using type = double; };
template<size_t I>
double get(const Vec2& v)
  { return I == 0 ? v.x : v.y; }

double f(Vec2 v) {
  auto add = [](double a, double b)
    { return a + b; };
  return std::apply(add, v);  // error
}
```

</div>

The same `Vec2` works with structured bindings but not with `std::apply`. The standard has two different things that are both called tuple-like.

The **tuple protocol** ([[g:tuple-protocol|tuple protocol]]) is open: specialize `tuple_size` and `tuple_element`, then provide a member `get<I>()` or a `get<I>(x)` that ADL can find. Structured bindings ([[dcl.struct.bind]]) use it: as long as `std::tuple_size<E>` is a complete type with a member named `value`, binding follows the protocol. Specializing `std::tuple_size` for a program-defined type is allowed by [[namespace.std]].

!!! std "[tuple.like]/1"
    A type `T` models and satisfies the exposition-only concept *tuple-like* if `remove_cvref_t<T>` is a specialization of `array`, `complex`, `pair`, `tuple`, or `ranges::subrange`.

The concept ***tuple-like*** is a closed list: only specializations of these five standard templates satisfy it; *pair-like* is the subset of size 2. `tuple`'s converting construction, assignment and comparison, as well as `tuple_cat`, `apply`, `make_from_tuple` and `pair(P&&)`, are all constrained by this concept.

Why not let library functions accept any type that implements the protocol? Library functions call `get<I>(std::forward<T>(t))` and rely on its semantics: it returns a reference to the `I`th element, with a value category that follows `t`. That cannot be guaranteed for user types. So when C++23 introduced the concept ([[P2165R4]]), it made promises only for the standard's own types. `complex` was added to the list in C++26 ([[P2819R2]]), and since then `auto [re, im] = z;` is valid.

### tuple_size and tuple_element ([tuple.helper])

In the `<tuple>` synopsis the primary templates of `tuple_size` and `tuple_element` are declared but not defined. For a type that does not take part in the protocol, `tuple_size<T>` is an incomplete type, and this is exactly how structured bindings decide between binding via the protocol and binding to data members.

¶1–¶3 `tuple_size<tuple<Types...>>` is `integral_constant<size_t, sizeof...(Types)>`; `tuple_element<I, tuple<Types...>>::type` is the `I`th type, requiring `I < sizeof...(Types)`.

!!! std "[tuple.helper]/4"
    If the expression `TS::value` is well-formed when treated as an unevaluated operand, then each specialization of the template meets the *Cpp17UnaryTypeTrait* requirements with a base characteristic of `integral_constant<size_t, TS::value>`. Otherwise, it has no member `value`.

¶4 `tuple_size<const T>` has a `value` only when `tuple_size<T>::value` is valid; otherwise it is a complete class without a `value`. It is written this way for the sake of this perfectly ordinary code:

```cpp ok
struct S { int a, b; };
const S s{1, 2};
auto [x, y] = s;   // E is const S, so tuple_size<const S> must be checked
```

If the partial specialization unconditionally derived from `integral_constant<size_t, tuple_size<T>::value>`, instantiating `tuple_size<const S>` would need the incomplete `tuple_size<S>`. That error occurs inside the template definition, where SFINAE cannot catch it, and code binding to data members would no longer compile. With the current wording, `tuple_size<const S>` has no `value`, and the structured binding falls back to binding to data members.

¶5 When checking `TS::value`, access checking is performed as if in a context unrelated to `TS` and `T`, and only the immediate context of the expression ([[g:immediate-context|immediate context]]) is considered. Note 1 points out that side effects outside the immediate context (such as an error in an implicit instantiation) can still make the program ill-formed.

¶7 `tuple_element<I, const T>::type` is `const TE`. ¶6 and ¶8 specify that these two partial specializations are also available via `<array>`, `<complex>`, `<ranges>` and `<utility>`, so a structured binding to a `const std::array` does not require including `<tuple>` as well. The corresponding `volatile` partial specializations were deprecated in C++20 and now live in [[depr.tuple]].

## Class template tuple ([tuple.tuple.general])

The class definition has the same shape as `pair`'s: a set of `constexpr explicit(see below)` constructors, `= default` copy and move constructors, a set of allocator-extended constructors, an ordinary family and a `const` family of assignment operators, and a member `swap`. The difference is that `tuple`'s elements are private; the standard does not specify the layout, and they can only be accessed via `get`.

¶1 A program that declares an explicit or partial specialization of `tuple` is ill-formed, no diagnostic required ([[g:ifndr|IFNDR]]: the compiler need not report an error, but the standard places no requirements on such a program). The general rule allows specializing standard class templates for program-defined types; it is specifically forbidden here because functions such as `apply` rely on the standard semantics of `tuple`.

There are four deduction guides: `tuple(UTypes...)`, `tuple(pair<T1, T2>)`, and their `allocator_arg_t` versions, all taking parameters by value. So `std::tuple{1, "x"}` deduces `tuple<int, const char*>`, and `std::tuple{std::pair{1, 'c'}}` deduces `tuple<int, char>`, not `tuple<pair<int, char>>`.

## Construction ([tuple.cnstr])

¶2–¶5 A constructor throws only if the construction of some element throws. When all elements are trivially destructible, `tuple`'s destructor is trivial; the default constructor of `tuple<>` is trivial. As with `pair`, `tuple`'s copy assignment is user-written (`tie` needs assignment through references), so `tuple` is not a trivially copyable type.

| Constructor | Paragraphs | Main *Constraints* | `explicit` if and only if |
|---|---|---|---|
| `tuple()` | ¶6–¶8 | all default-constructible | some *Ti* cannot be copy-list-initialized from `{}` |
| `tuple(const Types&...)` | ¶9–¶11 | at least one element; all copy-constructible | some `const Ti&` is not implicitly convertible to *Ti* |
| `tuple(UTypes&&...)` | ¶12–¶15 | at least one element; disambiguating constraint; all constructible | some *Ui* is not implicitly convertible to *Ti* |
| `tuple(const tuple&) = default` | ¶16–¶17 | (*Mandates*: all copy-constructible) | |
| `tuple(tuple&&) = default` | ¶18–¶19 | all move-constructible | |
| four from `tuple<UTypes...>` | ¶20–¶23 | element-wise constructible; extra condition for a single element | some element not implicitly convertible |
| four from `pair<U1, U2>` | ¶24–¶27 | exactly two elements; element-wise constructible | some element not implicitly convertible |
| `tuple(UTuple&&)`, *tuple-like* | ¶28–¶31 | not `tuple` itself or `subrange`; equal sizes; extra condition for a single element | some element not implicitly convertible |
| allocator-extended versions | ¶32–¶33 | as above | as above |

The `explicit` rule is the same as for `pair` and follows the elements:

<div class="compare" markdown="1">

```cpp error
#include <tuple>
#include <vector>
std::tuple<int, std::vector<int>> f() {
  return {1, 5};  // error: explicit
}
```

```cpp ok
#include <tuple>
#include <vector>
std::tuple<int, std::vector<int>> g() {
  return {1, std::vector<int>(5)};
}
```

</div>

The current draft also gives `tuple(const Types&...)` and `tuple(UTypes&&...)` an exception specification: they are `noexcept` when the corresponding constructions of all elements do not throw.

All constructors that construct elements from arguments are defined as deleted when some reference element would bind to a temporary (¶15, ¶23, ¶27, ¶31, [[P2255R2]]), for the same reason as in [[pairs]].

### The disambiguating constraint (¶12–¶13)

`template<class... UTypes> tuple(UTypes&&...)` is a greedy forwarding constructor. Without restrictions, it would steal calls that belong to other constructors in two situations. ¶12 defines *disambiguating-constraint* for this purpose, and ¶13 lists it as one of the constraints.

¶12.1 Copying a single-element `tuple`. In `tuple<X> t2(t1);` where `t1` is a non-`const` lvalue, the forwarding constructor deduces `U0 = tuple<X>&`, an exact match, which is better than the copy constructor `tuple(const tuple&)`, which needs a `const` added ([[over.ics.rank]]). So for a single element it is required that `remove_cvref_t<U0>` not be `tuple` itself.

¶12.2 Allocator tags. Among the allocator-extended constructors, the default-construction version takes 2 arguments (tag, allocator), and the copy, move and converting versions take 3; the forwarding constructor takes *N*. When the number of elements is 2 or 3, the two may collide. So in that case it is required that the first argument not be `allocator_arg_t`, unless the type of the first element is itself `allocator_arg_t`.

A collision is worse than an ambiguity. Consider `tuple<std::any, std::any> t(std::allocator_arg, alloc);`: `any` can be constructed from any copyable value, so the forwarding constructor is viable; for the prvalue argument `alloc`, its `Alloc&&` parameter is better than the allocator version's `const Alloc&` (an rvalue binding to an rvalue reference is preferred). Without ¶12.2 it would win and put the tag and the allocator into the two `any`s.

!!! impl "libc++ 23 does not implement ¶12.2"
    libc++'s forwarding constructor only excludes the case where the single argument is the `tuple` itself; there is no disambiguation condition for `allocator_arg_t`. Running the example above in our tests, `has_value()` is 1 for both `any`s: the forwarding constructor was selected. According to the draft, the allocator-extended default constructor should be selected, and both `any`s should be empty.

### A single element: wrap or convert (¶21.3, ¶29.5)

In `tuple<tuple<int>> outer(inner);` where `inner` is a `tuple<int>`, there are two readings:

- treat `inner` as the element: use `tuple(const Types&...)` and copy `inner` in;
- treat `inner` as a `tuple` to be converted: use `tuple(const tuple<UTypes...>&)` with `UTypes = int`, and initialize the element `tuple<int>` with the `int` `get<0>(inner)`.

Both are viable, but they give different results. ¶21.3 specifies that, for a single element, the converting constructor is excluded if `u` as a whole can be converted to or used to construct the element type `T`, or if `T` and `U` are the same. If it can be used as the element as a whole, it is used as the element. ¶29.5 says the same for *tuple-like* arguments.

```cpp run title="tuple_wrap.cpp" ok
#include <tuple>
#include <type_traits>
int main() {
  std::tuple<int> inner{1};
  std::tuple<std::tuple<int>> outer(inner);   // wrapped
  static_assert(std::is_same_v<std::tuple_element_t<0, decltype(outer)>,
                               std::tuple<int>>);
  return std::get<0>(std::get<0>(outer)) - 1;
}
```

### Allocator-extended constructors (¶32–¶33, [tuple.traits])

Every constructor has a version with `allocator_arg_t, const Alloc&` prepended. ¶32 requires `Alloc` to meet *Cpp17Allocator*. ¶33 specifies that the effect is the same as the corresponding constructor, except that each element of non-reference type is created by **uses-allocator construction** ([[allocator.uses.construction]]): if the element type uses this allocator (`uses_allocator_v<Ti, Alloc>` is true), the allocator is passed to its constructor; otherwise the allocator is ignored. The copy and move versions `tuple(allocator_arg_t, const Alloc&, const tuple&)` are not `explicit`.

[tuple.traits] ¶1–¶2 specialize `uses_allocator<tuple<Types...>, Alloc>` as `true_type`, telling other components that `tuple` can accept an allocator even though it has no nested `allocator_type`. So `std::pmr::vector<std::tuple<int, std::pmr::string>>` passes its memory resource all the way down to the `pmr::string` in each element:

```cpp run title="tuple_alloc.cpp" ok
#include <tuple>
#include <memory>
#include <memory_resource>
#include <string>
#include <cstdio>

int main() {
  std::pmr::monotonic_buffer_resource res;
  std::pmr::polymorphic_allocator<> alloc(&res);
  // pmr::string gets alloc, int ignores it
  std::tuple<int, std::pmr::string> t(std::allocator_arg, alloc, 1,
                                      "a fairly long string, no SSO here");
  std::printf("%d\n", std::get<1>(t).get_allocator().resource() == &res);   // 1
}
```

## Assignment and swap ([tuple.assign], [tuple.swap], [tuple.special])

[tuple.assign] is entirely parallel to `pair`. Copy assignment (¶2–¶4) is defined as deleted unless all elements are copy-assignable; the exception specification of move assignment (¶8–¶11) is the conjunction of `is_nothrow_move_assignable_v` over all elements. In addition there is assignment from `tuple<UTypes...>` (¶15–¶26), from `pair<U1, U2>` (¶27–¶38, requiring exactly two elements) and from *tuple-like* (¶39–¶44, excluding itself and `subrange`).

Each has a `const` version with constraints written as `is_assignable_v<const Ti&, ...>`, serving the proxy references of `ranges::zip` ([[P2321R2]]; see [[pairs]] for details):

```cpp run title="tuple_const_assign.cpp" ok
#include <tuple>
#include <string>

void assign_through(const std::tuple<int&, std::string&>& proxy) {
  proxy = std::tuple{42, std::string("hi")};   // assigns to the referenced objects
}

int main() {
  int i = 0; std::string s;
  assign_through(std::tie(i, s));
  return (i == 42 && s == "hi") ? 0 : 1;
}
```

[tuple.swap] The swappability requirement of the member `swap` is *Mandates* (¶2). ¶4 calls `swap` on each element; by the convention of [[swappable.requirements]], this is a `using std::swap; swap(a, b);`-style call that can find a `swap` the user provides via ADL. The non-member `swap` in [tuple.special], on the other hand, has *Constraints* (¶1), and its exception specification is `noexcept(x.swap(y))`. The division of labor is the same as for `pair`: the non-member version is what `is_swappable` checks, so it must drop out of overload resolution when the elements are not swappable.

## Creation functions ([tuple.creation])

| Function | Result type | Purpose |
|---|---|---|
| `make_tuple(ts...)` | `tuple<unwrap_ref_decay_t<Ts>...>` | pack by value; `std::ref` and `std::cref` unwrap to references |
| `forward_as_tuple(ts...)` | `tuple<Ts&&...>` | pack as references, for forwarding |
| `tie(ts...)` | `tuple<Ts&...>` | pack as lvalue references, for assigning to several variables |
| `tuple_cat(tpls...)` | `tuple<CTypes...>` | concatenate any number of *tuple-like*s |

¶1–¶2 The type of `make_tuple(1, ref(i), cref(j))` is `tuple<int, int&, const float&>` (where `j` is a `float`). With CTAD available, its distinctive use is unwrapping `reference_wrapper`, the same as `make_pair`.

### The result of forward_as_tuple cannot be stored (¶3–¶4)

```cpp run title="forward_as_tuple_dangling.cpp" ub
#include <tuple>
#include <string>
#include <cstdio>

int main() {
  auto t = std::forward_as_tuple(std::string(40, 'x'));   // tuple<string&&>
  // the temporary string was destroyed at the end of the previous full-expression
  std::printf("%zu\n", std::get<0>(t).size());            // UB: dangling reference
}
```

In our tests, running it directly happened to print `40`; with `-fsanitize=address`, ASan reports `stack-use-after-scope`.

¶3 says the result may contain references to temporary objects, and the program must ensure that the return value does not outlive any of its arguments. The correct use is to pass the result immediately as a function argument and consume it within the same full-expression, while the temporaries are still alive: `pair`'s piecewise construction, `map::emplace` and `apply` all use it this way.

### tie and ignore (¶5–¶6)

`std::tie(i, std::ignore, s) = std::make_tuple(42, 3.14, "C++");` is how unpacking was written before C++17. After structured bindings arrived, it still has two uses: assigning to existing variables (structured bindings can only introduce new names), and writing lexicographic comparisons as `std::tie(a.x, a.y) < std::tie(b.x, b.y)` (since C++20 a defaulted `<=>` can be used instead).

`std::ignore` accepts assignment of any value and does nothing. Since C++26 its type is the exposition-only `ignore-type`, which has only a `const` assignment operator accepting any argument ([[P2968R2]]); previously its type was unspecified and it was only guaranteed to work in `tie`. Now `std::ignore = f();` can be used to explicitly discard a `[[nodiscard]]` return value. [tuple.general] ¶2 specifies that `ignore` is also available by including `<utility>`.

### tuple_cat (¶7–¶9)

¶7 defines the result precisely with some notation: the type of each argument with cv and references removed is written *Ui*; concatenating the element types `tuple_element_t<k, Ui>` of all arguments in order gives `CTypes`, and concatenating the corresponding expressions `get<k>(std::forward<Ti>(tpi))` gives `celems`. ¶8–¶9 require each element to be constructible from the corresponding expression, and the function returns `tuple<CTypes...>(celems...)`.

So the arguments can be any *tuple-like*s, mixing `pair`, `array` and `tuple`; element types are preserved as they are, so reference elements remain references; when an argument is an rvalue, its elements are moved out.

```cpp run title="tuple_cat.cpp" ok
#include <tuple>
#include <utility>
#include <array>
#include <type_traits>
int main() {
  auto cat = std::tuple_cat(std::pair{1, 'a'}, std::array<double, 2>{2.5, 3.5},
                            std::tuple<>{});
  static_assert(std::is_same_v<decltype(cat), std::tuple<int, char, double, double>>);
  static_assert(std::tuple{1, 2} == std::pair{1, 2});   // comparison with a pair-like
}
```

## apply and make_from_tuple ([tuple.apply])

¶1 `apply(f, t)` is equivalent to `INVOKE(std::forward<F>(f), get<I>(std::forward<Tuple>(t))...)`, with `I` ranging over 0 to `tuple_size_v - 1`. Using *INVOKE* ([[func.require]]) means `f` can be a pointer to member function, with the first element acting as the object. In the current draft its return type is `apply_result_t<F, Tuple>` and its exception specification is `noexcept(is_nothrow_applicable_v<F, Tuple>)`; these two traits are new in C++26 ([[meta.trans.other]]). The explicit return type makes `apply` detectable by SFINAE when the call is not possible.

!!! impl "apply in libc++ 23"
    libc++ 23's `apply` is still the old form: its return type is `decltype(auto)` and its parameter is not constrained with *tuple-like*, so a non-tuple-like type produces an error internally when `get` is looked up. The header also does not have `is_applicable` and `is_nothrow_applicable` yet. For normal use with *tuple-like* types, the two behave the same.

¶3 `make_from_tuple<T>(t)` is equivalent to `T(get<I>(std::forward<Tuple>(t))...)`, and the internal exposition-only function carries `requires is_constructible_v<T, ...>`. Note 1 points out that `T` cannot be deduced and must be given explicitly. It uses parentheses `T(...)`: since C++20, parentheses can also perform aggregate initialization of aggregate types ([[dcl.init]]).

```cpp run title="apply.cpp" ok
#include <tuple>
#include <array>
#include <string>
#include <cstdio>
int main() {
  auto sum = std::apply([](auto... xs) { return (xs + ...); }, std::array{1, 2, 3});
  auto str = std::make_from_tuple<std::string>(std::tuple{3, 'z'});  // string(3, 'z')
  std::printf("%d %s\n", sum, str.c_str());                          // 6 zzz
}
```

### The dangling check in make_from_tuple (¶2)

```cpp run title="make_from_tuple_dangling.cpp" error
#include <tuple>
#include <string>
int main() {
  // T = const string&, the only element is a const char*
  auto&& r = std::make_from_tuple<const std::string&>(std::tuple<const char*>{"x"});
}
```

With only one element and `T` a reference type, `T(get<0>(...))` is a functional cast, equivalent to `(const std::string&)ptr`: a temporary `string` is constructed first, the reference binds to it, and then it is returned from the function, so the returned reference dangles immediately. The *Mandates* in ¶2 requires that `reference_constructs_from_temporary_v<T, decltype(get<0>(declval<Tuple>()))>` be false in this case. Only the single-element case is checked because `T(x)` is a cast only when there is exactly one argument; with several arguments, `T(a, b)` with a reference type `T` is ill-formed anyway.

!!! impl
    libc++ implements this *Mandates* with a `static_assert`, and Clang reports `Attempted construction of reference element binds to a temporary whose lifetime has ended`. libc++ also adds an outer constraint so that `make_from_tuple` itself drops out of overload resolution when construction is not possible; a comment cites [[LWG3528]].

## Element access: get ([tuple.elem])

¶1–¶2 The by-index `get<I>` has four overloads, `&`, `&&`, `const&` and `const&&`, requires `I < sizeof...(Types)`, and returns a reference to the `I`th element. Two notes explain the behavior of reference elements:

```cpp ok
#include <tuple>
#include <type_traits>
#include <utility>
void f(int i) {
  std::tuple<int&> t{i};
  const std::tuple<int&> ct{i};
  static_assert(std::is_same_v<decltype(std::get<0>(std::move(t))), int&>);  // not int&&
  static_assert(std::is_same_v<decltype(std::get<0>(ct)), int&>);            // not const int&
}
```

¶3 Note 1: when the element type is `X&`, the return type of the `&&` overload, `tuple_element_t<I, ...>&&`, collapses to `X&`. An lvalue reference element in an rvalue `tuple` is still an lvalue, and this is what lets `forward_as_tuple` forward lvalue arguments correctly.

¶4 Note 2: constness is shallow. When the element type is `X&`, the `const&` overload returns `X&`. This is consistent with the core language: a reference member of a `const` object does not thereby become a reference to `const`.

¶5–¶7 The by-type `get<T>` requires `T` to occur exactly once in `Types`. In the example in ¶7, `get<int>` and `get<const int>` on `tuple<int, const int, double, double>` are both valid (`int` and `const int` are different types), while `get<double>` is ill-formed.

¶8 Note 3 explains why `get` is a non-member function: if it were a member template, you would have to write `t.template get<0>()` in dependent contexts ([[temp.names]]).

## Comparison ([tuple.rel])

¶1–¶3 `operator==` has two overloads: `tuple` with `tuple`, and `tuple` with any *tuple-like* (C++23). The constraints require the two to have the same size, each `get<i>(t) == get<i>(u)` to be valid, and the results to model *boolean-testable* (usable like `bool` in `&&` and `!`; see [[concept.booleantestable]]). Empty `tuple`s are equal.

¶4.1 Elements are compared in order starting from index 0, and after the first inequality no further elements are compared or even accessed: short-circuiting is a normative requirement. ¶4.2 The second overload can only be found by ADL, with an effect similar to a [[g:hidden-friend|hidden friend]]: it is considered only when one of the operands is a `tuple`, so it does not interfere with comparisons between other tuple-like types. Thanks to C++20's rewritten candidates, `pair == tuple` is reversed into `tuple == pair`, so one overload covers both directions.

¶5–¶7 The return type of `operator<=>` is the common comparison category of the elements' *synth-three-way-result*s. ¶6 specifies a lexicographic comparison: compare the first elements, return if they are unequal, otherwise compare the rest. *synth-three-way* plays the same role as in [[pairs]]: when an element has only `<` and `==`, they are used to synthesize a `weak_ordering`. ¶8 Note 2 explains that the rest, `ttail`, in the definition is only a notation for describing the recursion and need not actually be constructed (the elements might not be copyable).

`<`, `>`, `<=`, `>=` and `!=` are all obtained from rewritten candidates ([[over.match.oper]]).

## common_reference and common_type specializations ([tuple.common.ref])

¶1–¶3 `basic_common_reference<TTuple, UTuple, TQual, UQual>::type` is `tuple<common_reference_t<TQual<TTypes>, UQual<UTypes>>...>`. ¶4–¶5 `common_type<TTuple, UTuple>::type` is `tuple<common_type_t<TTypes, UTypes>...>`. The constraints in ¶2 and ¶4 are: at least one side is a specialization of `tuple` (two `pair`s are handled by `pair`'s own specializations), both are already decayed, the sizes are equal, and the result type is valid.

They exist for `ranges::zip_view` ([[range.zip]]). The reference type of a `zip` iterator is `tuple<int&, string&>` and its value type is `tuple<int, string>`, and `indirectly_readable` requires them to have a common reference type ([[iterator.concept.readable]]). `TQual` and `UQual` distribute the outer `tuple`'s cv- and ref-qualifiers onto each element:

```cpp run title="tuple_common_ref.cpp" ok
#include <tuple>
#include <type_traits>
using std::tuple, std::common_reference_t, std::is_same_v;
static_assert(is_same_v<common_reference_t<tuple<int&>&, tuple<int>&>, tuple<int&>>);
static_assert(is_same_v<common_reference_t<tuple<int&>, tuple<int>&>, tuple<int&>>);
static_assert(is_same_v<common_reference_t<tuple<int&>, tuple<int>>, tuple<int>>);
static_assert(is_same_v<std::common_type_t<tuple<int, long>, tuple<long, int>>,
                        tuple<long, long>>);
int main() {}
```

!!! impl "libc++ 23 only specializes tuple with tuple"
    The draft's specializations accept a `tuple` on one side and any *tuple-like* on the other ([[P2165R4]]). libc++ 23 only specializes for two `tuple`s, and `std::common_reference_t<std::tuple<int&>, std::pair<int, int>>` cannot be formed in our tests. This is consistent with `__cpp_lib_tuple_like` still being commented out in `<version>`.

## Implementation: how tuple is laid out in memory

The standard says nothing about the layout of `tuple`, and implementations differ widely.

- libc++'s `tuple` holds a `__tuple_impl`, which inherits from `__tuple_leaf<0, T0>`, `__tuple_leaf<1, T1>`, ... in order. Each leaf either holds a `T` member or, when `T` is a non-`final` empty class, inherits from `T` to take advantage of the empty base optimization. In our tests the offsets of the three elements of `tuple<char, int, double>` are 0, 4 and 8.
- libstdc++ inherits recursively from `_Tuple_impl<I, Head, Tail...>`, with the base `_Tuple_impl<I+1, Tail...>` first and `Head` after it, so the elements are laid out in reverse order in memory.

Use a `struct` when you need a definite layout. The empty base optimization also has its limits: in our tests `sizeof(std::tuple<int, Empty>)` is 4, with `Empty` taking no space, but `sizeof(std::tuple<Empty, Empty>)` is 2, because two empty subobjects of the same type must have distinct addresses ([[intro.object]]).

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[tuple.syn] The whole `<tuple>` header is freestanding and includes `<compare>`. *pair-like* is defined as `tuple-like<T> && tuple_size_v<remove_cvref_t<T>> == 2`.

[tuple.cnstr] ¶1 defines notation: *Ti* is the *i*th type in `Types` and *Ui* the *i*th type in `UTypes`, with indices starting from 0. ¶3 The defaulted copy and move constructors are constexpr functions if and only if all element-wise initializations would be constexpr-suitable; those of `tuple<>` are always constexpr functions.

[tuple.assign] ¶1 An assignment operator throws only if the assignment of some element throws. Likewise for [tuple.swap] ¶5.

</details>

!!! history
    C++11 brought `tuple` in from TR1, implemented with variadic templates. C++14 added the by-type `get<T>`. C++17 added `apply`, `make_from_tuple`, deduction guides and conditional `explicit`, and structured bindings were built on the tuple protocol. C++20 replaced the six relational operators with `<=>` and deprecated the `volatile` partial specializations. C++23 introduced the *tuple-like* concept with the related construction, assignment and comparison ([[P2165R4]]), `const` assignment and the `common_reference` specializations ([[P2321R2]]), and the rule forbidding dangling references ([[P2255R2]]). C++26 added `complex` to *tuple-like* ([[P2819R2]]) and specified the type of `ignore` ([[P2968R2]]).

## Common misconceptions

!!! pitfall "std::tuple{p} wraps the pair"
    When `p` is a `pair<int, char>`, `std::tuple{p}` deduces `tuple<int, char>`, using the `tuple(pair<T1, T2>)` deduction guide. To get `tuple<pair<int, char>>`, you must spell out the template arguments.

!!! pitfall "A type implementing the protocol can be used with apply"
    `apply`, `tuple_cat` and `make_from_tuple` accept only the five standard *tuple-like* types. A user type that implements the tuple protocol can only be used with structured bindings.

!!! pitfall "get<0>(std::move(t)) moves the element"
    For `tuple<X&>`, `get<0>(std::move(t))` returns `X&` and does not move the referenced object. Only non-reference elements yield `X&&`.

## Questions

!!! question "Question 1"
    According to the current draft, what does the program below print? Why?
    ```cpp
    std::tuple<std::any, std::any> t(std::allocator_arg, std::allocator<int>{});
    std::printf("%d %d\n", std::get<0>(t).has_value(), std::get<1>(t).has_value());
    ```

<details markdown="1">
<summary>Answer</summary>

It should print `0 0`. There are 2 elements and the type of the first argument is `allocator_arg_t`, while `T0` is `any`, not `allocator_arg_t`, so the disambiguating constraint in ¶12.2 is false and the forwarding constructor does not participate in overload resolution. What remains viable is the allocator-extended default constructor `tuple(allocator_arg_t, const Alloc&)`; `uses_allocator_v<any, allocator<int>>` is false, so both `any`s are value-initialized without the allocator and are empty.

Without this constraint, the forwarding constructor would also be viable, and for the prvalue second argument it binds an rvalue to an rvalue reference, which is better than `const Alloc&` ([[over.ics.rank]]); it would win and print `1 1`. libc++ 23 does not implement ¶12.2, and in our tests it does print `1 1`.
</details>

!!! question "Question 2"
    Which constructor does `std::tuple<int> a{1}; std::tuple<long> b(a);` use? What about `std::tuple<std::tuple<int>> c(a);`?

<details markdown="1">
<summary>Answer</summary>

`b(a)`: a single element, `T = long`, `U = int`. `tuple<int>` cannot be converted to or used to construct a `long`, and `T` and `U` are different, so the extra condition in ¶21.3 holds and the converting constructor `tuple(const tuple<UTypes...>&)` is viable; the element is initialized with `get<0>(a)`.

`c(a)`: `T = tuple<int>`, `U = int`. `a` can construct `T` directly, so ¶21.3 excludes the converting constructor, `tuple(const Types&...)` is selected, and `a` is copied in as a whole to become the only element.
</details>
