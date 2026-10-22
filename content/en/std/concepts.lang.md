---
title: Language-related concepts
summary: "The definitions, semantic requirements and design rationale of same_as, derived_from, convertible_to, common_reference_with, common_with, the integral and floating-point concepts, assignable_from, swappable and ranges::swap, destructible, constructible_from, default_initializable, move_constructible and copy_constructible."
updated: 2026-10-19
---

!!! tldr
    - Most of these concepts wrap `<type_traits>`. Wrapping them in concepts is what lets constraints be compared for strictness (subsumption), and the concepts also carry semantic requirements the compiler doesn't check.
    - `convertible_to` requires both implicit and explicit conversion to work and to give equal results; a type with only one of them doesn't satisfy it.
    - `ranges::swap` skips unconstrained template `swap`s written by users and uses only `swap`s written for specific types, falling back to the three-move swap when none is found.
    - `default_initializable` checks `T()`, `T{}` and `T t;` together, so `const int` doesn't satisfy it.
    - A type whose destructor may throw isn't `destructible`, and therefore not `movable` or `copyable`, and is nearly unusable with ranges.

[concepts.lang] collects the concepts corresponding to language features ([concepts.lang.general] ¶1): relations between types (same, derived, convertible, having a common type), classification of types (integral, floating-point), and the most basic object operations (assignment, swapping, destruction, construction). The `movable`, `copyable` and `regular` in [[concepts.object]] are assembled from them.

This page needs two words from [[concepts]]. A type **satisfies** a concept when the concept's definition, with the type substituted, is `true`, which the compiler checks. A type **models** a concept when it both satisfies the concept and meets the semantic requirements in the concept's specification, which the programmer vouches for. Handing a type that satisfies but doesn't model to the standard library makes the program {{ifndr}} ([[res.on.requirements]]).

## Why not use type traits directly: `same_as`

```cpp run title="same-as-subsumption.cpp" ok
#include <concepts>
#include <cstdio>

template<class T>
void f(T) requires std::same_as<T, int> { std::puts("#1"); }

template<class T>
void f(T) requires std::same_as<int, T> && true { std::puts("#2"); }

int main() {
  f(1);   // selects #2
}
```

Both overloads are viable. #2's constraints subsume #1's ([[temp.constr.order]]), so #2 is more constrained and is selected. Replace both `std::same_as` with `std::is_same_v` and Clang reports the call as ambiguous.

The reason is that subsumption only recognizes atomic constraints produced by the same concept. `is_same_v<T, int>` and `is_same_v<int, T>` written directly in constraints are two different expressions, and the compiler can't compare them. `same_as` is deliberately defined with the check written twice:

```cpp
template<class T, class U>
  concept same-as-impl = is_same_v<T, U>;       // exposition only
template<class T, class U>
  concept same_as = same-as-impl<T, U> && same-as-impl<U, T>;
```

So `same_as<T, int>` normalizes to two atomic constraints, `is_same_v<T, int>` and `is_same_v<int, T>`, which come from the same expression with different parameter mappings. `same_as<int, T>` gives the same two constraints in the opposite order. A conjunction doesn't care about order, so the two subsume each other, which is exactly what Note 1 says.

`same_as` doesn't decay anything: `same_as<int, const int>` and `same_as<int&, int>` are both false. In a *type-constraint* `{ e } -> same_as<T>`, `decltype((e))` is passed as the first argument, so the value category of the expression can be checked exactly: an lvalue expression gives `T&`.

## Public derivation: `derived_from`

```cpp
template<class Derived, class Base>
  concept derived_from =
    is_base_of_v<Base, Derived> &&
    is_convertible_v<const volatile Derived*, const volatile Base*>;
```

`is_base_of_v` looks only at the inheritance graph, so private inheritance and ambiguous bases count too. Adding the check that pointers convert implicitly rules out cases where a derived class pointer can't convert to a base class pointer (an inaccessible or ambiguous base; see [[conv.ptr]], [[class.derived]]). Per Note 1, the result is: `Derived` is publicly and unambiguously derived from `Base`, or both are the same class type ignoring cv-qualifiers. The pointers get `const volatile` so that cv-qualified types pass too.

```cpp run title="derived-from.cpp" ok
#include <concepts>
#include <type_traits>

struct B {};
struct D : B {};
struct P : private B {};
struct M1 : B {};
struct M2 : B {};
struct MM : M1, M2 {};   // two B subobjects

static_assert(std::derived_from<D, B>);
static_assert(std::is_base_of_v<B, P>);
static_assert(!std::derived_from<P, B>);   // private inheritance
static_assert(std::is_base_of_v<B, MM>);
static_assert(!std::derived_from<MM, B>);  // ambiguous base
static_assert(std::derived_from<const B, B>);
static_assert(!std::derived_from<int, int>);  // not a class

int main() {}
```

## Both implicit and explicit conversion: `convertible_to`

```cpp run title="convertible-to.cpp" ok
#include <concepts>
#include <type_traits>

struct From {};
struct To {
  template<class T> To(T&&) {}   // anything converts implicitly
  explicit To(From) = delete;    // selected when converting From explicitly
};
static_assert(std::is_convertible_v<From, To>);
static_assert(!std::convertible_to<From, To>);

struct E { explicit E(int) {} };   // explicit conversion only
static_assert(!std::convertible_to<int, E>);
static_assert(std::constructible_from<E, int>);

static_assert(std::convertible_to<void, void>);
static_assert(!std::convertible_to<int, void>);

int main() {}
```

`From` converts implicitly to `To`, yet doesn't satisfy `convertible_to<From, To>`, because the definition requires both conversions to work:

```cpp
template<class From, class To>
  concept convertible_to =
    is_convertible_v<From, To> &&
    requires { static_cast<To>(declval<From>()); };
```

`is_convertible_v` checks [[g:copy-initialization|copy-initialization]], equivalent to whether `return declval<From>();` can return a `To`. `static_cast<To>(e)` checks [[g:direct-initialization|direct-initialization]] ([[expr.static.cast]]). The two see different candidate functions: copy-initialization doesn't consider `explicit` constructors, while direct-initialization does ([[over.match.copy]], [[over.match.ctor]]). So two kinds of inconsistency arise:

- With only an `explicit` constructor or conversion function, explicit works and implicit doesn't, as with `E` above.
- If the explicit path has an extra, better candidate that is deleted or ambiguous, implicit works and explicit doesn't. That is the case with `To` above: in `static_cast<To>(From{})`, the conversion sequences for the template constructor `To(From&&)` and for `To(From)` are both identity conversions, and by [[over.match.best]] the non-template wins, selecting the deleted one.

Why require both? Generic code casually writes `To t = e;`, `return e;`, `static_cast<To>(e)` and `To(e)`. If the constraint guaranteed only one form, switching forms in the template body could fail to compile, or even call a conversion with different semantics.

¶1 also requires the results of the two conversions to be equal. ¶2 states this more precisely with a hypothetical function: let `FromR` be `add_rvalue_reference_t<From>` and `f` an equality-preserving function taking no arguments and returning `FromR`; then `From` and `To` model `convertible_to` only if:

- ¶2.1 if `To` is an object type or a reference to an object type, `static_cast<To>(f())` equals `test(f)`, the result of `To test(FromR (&f)()) { return f(); }`;
- ¶2.2.1 if `FromR` is an rvalue reference to a non-const type, the source object is left in a [[g:valid-but-unspecified-state|valid but unspecified state]] after the conversion, i.e. it may be moved from;
- ¶2.2.2 in other cases of object references, the conversion doesn't modify the source object.

When `To` is a non-object type such as `void`, ¶2.1 doesn't apply.

## Common references and common types

### The problem with proxy iterators

Dereferencing a `vector<bool>::iterator` gives a proxy object `vector<bool>::reference`, but its value type is `bool`. Dereferencing an iterator of `views::zip` gives `tuple<int&, double&>`, with value type `tuple<int, double>`. Generic algorithms often have to handle references and values together: `ranges::sort` compares `*it` with `*jt`, and also `*it` with a temporarily stored `value_type` variable.

`common_reference_t<R, V&>` answers the question: is there a type to which both `R` and `V&` can convert, so that one function can accept both? For ordinary references it gives the intuitive result; for proxy types, `basic_common_reference` can be specialized to specify the answer ([[meta.trans.other]]). `indirectly_readable` in `<iterator>` requires `common_reference_with<iter_reference_t<I>&&, iter_value_t<I>&>`.

```cpp run title="common-reference.cpp" ok
#include <concepts>
#include <string>
#include <type_traits>
#include <utility>

using std::common_reference_t, std::same_as;

static_assert(same_as<common_reference_t<int&, const int&>,
                      const int&>);
static_assert(same_as<common_reference_t<int&&, int&>,
                      const int&>);
// with no common reference, fall back to a value type
static_assert(same_as<common_reference_t<int&, double&>,
                      double>);
static_assert(std::common_reference_with<int&, double&>);
static_assert(!std::common_reference_with<int*, std::string>);

// pair specializes basic_common_reference (C++23)
using PR = std::pair<int&, int&>;
using PV = std::pair<int, int>;
static_assert(same_as<common_reference_t<PR, PV&>, PR>);
static_assert(std::common_reference_with<PR, PV&>);

int main() {}
```

### `common_reference_with` ([concept.commonref])

¶1 If `common_reference_t<T, U>` is well-formed and denotes a type `C` such that both `convertible_to<T, C>` and `convertible_to<U, C>` are modeled, then `T` and `U` share a **common reference type** ([[g:common-reference-type|common reference type]]) `C`. Per Note 1, `C` may be `T` or `U` itself, some other type, or a reference type.

```cpp
template<class T, class U>
  concept common_reference_with =
    same_as<common_reference_t<T, U>, common_reference_t<U, T>> &&
    convertible_to<T, common_reference_t<T, U>> &&
    convertible_to<U, common_reference_t<T, U>>;
```

The first term requires symmetry. `common_reference` may be specialized by users, and the standard can't assume such specializations are symmetric, so symmetry is written into the constraint.

¶2 is the semantic requirement. Let `t1` and `t2` be equality-preserving expressions of type `T`, and likewise `u1` and `u2`; then `C(t1)` equals `C(t2)` if and only if `t1` equals `t2` (¶2.1), and likewise for `u` (¶2.2). In other words, converting to `C` can neither make different values equal nor make equal values different. So comparing in `C` is the same as comparing in the original types, which is what the cross-type comparison concepts in [[concepts.compare]] build on.

### `common_with` ([concept.common])

`common_with` is the value version. ¶1 says that if `T` and `U` can both be explicitly converted to some third type `C`, they share a **common type** ([[g:common-type|common type]]) `C`; Note 1 adds that `C` isn't necessarily unique.

```cpp
template<class T, class U>
  concept common_with =
    same_as<common_type_t<T, U>, common_type_t<U, T>> &&
    requires {
      static_cast<common_type_t<T, U>>(declval<T>());
      static_cast<common_type_t<T, U>>(declval<U>());
    } &&
    common_reference_with<add_lvalue_reference_t<const T>,
                          add_lvalue_reference_t<const U>> &&
    common_reference_with<
      add_lvalue_reference_t<common_type_t<T, U>>,
      common_reference_t<add_lvalue_reference_t<const T>,
                         add_lvalue_reference_t<const U>>>;
```

The four terms are, in order: `common_type_t` is symmetric; both sides convert explicitly to the common type (only explicitly, which is looser than `convertible_to`); `const T&` and `const U&` have a common reference; and an lvalue reference to the common type and that common reference also have a common reference, ensuring the world of values and the world of references are mutually compatible.

¶2's semantic requirement is the same as for `common_reference_with`, with `C` replaced by `common_type_t<T, U>`. ¶3 Note 2 points out that `common_type` can be specialized to customize it.

```cpp run title="common-with.cpp" ok
#include <concepts>
#include <string>
#include <type_traits>

using std::string;

static_assert(std::common_with<int, double>);
static_assert(std::same_as<
  std::common_type_t<string, const char*>, string>);
static_assert(std::common_with<string, const char*>);
// the common reference in the third term is the non-reference type const string
static_assert(std::same_as<
  std::common_reference_t<const string&,
                          const char* const&>,
  const string>);

int main() {}
```

## Integral and floating-point ([concepts.arithmetic])

```cpp run title="arithmetic.cpp" ok
#include <concepts>
#include <cstddef>
#include <type_traits>

static_assert(std::unsigned_integral<bool>);
static_assert(std::unsigned_integral<char8_t>);
// whether char is signed is implementation-defined
static_assert(std::signed_integral<char> ==
              std::is_signed_v<char>);
static_assert(std::integral<const int>);
static_assert(!std::integral<const int&>);
static_assert(!std::integral<std::byte>);

int main() {}
```

```cpp
template<class T> concept integral          = is_integral_v<T>;
template<class T> concept signed_integral   = integral<T> && is_signed_v<T>;
template<class T> concept unsigned_integral = integral<T> && !signed_integral<T>;
template<class T> concept floating_point    = is_floating_point_v<T>;
```

`integral` is exactly what [[basic.fundamental]] calls the [[g:integral-type|integral types]]: `bool`, all character types, and the signed and unsigned integer types (including extended integer types). cv-qualified versions count; references, enumerations and `std::byte` don't. `floating_point` includes extended floating-point types ([[basic.extended.fp]]).

`unsigned_integral` is written as `integral && !signed_integral` rather than `is_unsigned_v`. For integral types the results are the same, but this way both concepts refer to `integral` by name and so both subsume it.

Notes 1 and 2 warn that the concept names don't correspond one to one with the terms of [[basic.fundamental]]. `char` isn't a signed integer type, but on implementations where `char` is signed it models `signed_integral`. `bool`, `char8_t` and `char16_t` aren't unsigned integer types, yet they all model `unsigned_integral`.

!!! pitfall "Constraining numbers with `unsigned_integral` lets in `bool` and characters"
    `template<std::unsigned_integral T> T gcd(T, T)` can be instantiated with `bool` or `char8_t`. Where the standard library needs real integers, such as `popcount` in `<bit>` and the saturation arithmetic functions, the specification says `T` is an unsigned integer type (the [[basic.fundamental]] term) rather than using these concepts, thereby excluding `bool` and the character types.

## Assignment: `assignable_from`

```cpp run title="assignable-from.cpp" ok
#include <concepts>
#include <type_traits>

struct VoidAssign {
  void operator=(const VoidAssign&) {}
};

static_assert(!std::assignable_from<int, int>);
static_assert(std::assignable_from<int&, int>);
static_assert(std::is_copy_assignable_v<VoidAssign>);
// returns void, so not satisfied
static_assert(!std::assignable_from<VoidAssign&,
                                    const VoidAssign&>);

int main() {}
```

```cpp
template<class LHS, class RHS>
  concept assignable_from =
    is_lvalue_reference_v<LHS> &&
    common_reference_with<const remove_reference_t<LHS>&, const remove_reference_t<RHS>&> &&
    requires(LHS lhs, RHS&& rhs) {
      { lhs = std::forward<RHS>(rhs) } -> same_as<LHS>;
    };
```

There are three easy mistakes in the definition:

1. `LHS` must be an lvalue reference. Write `assignable_from<T&, U>`, not `assignable_from<T, U>`. This rules out assigning to rvalues (`T{} = x`), which in generic code is almost always a mistake.
2. The type of the assignment expression must be exactly `LHS`, using `same_as` rather than `convertible_to`. An `operator=` returning `void` or returning a copy doesn't satisfy it.
3. The two sides must have a common reference. This restricts assignment to types representing the same kind of value: `string&` can be assigned from `const char*` because the two have a common reference; a type that happens to overload `operator=(int)` but has no common reference with `int` doesn't satisfy it.

¶1's semantic requirements: let `lhs` refer to an object `lcopy`, and let `rcopy` be a distinct object equal to `rhs`.

- ¶1.4 `addressof(lhs = rhs) == addressof(lcopy)`, i.e. what is returned is the left operand itself.
- ¶1.5.1 After the assignment `lhs` equals `rcopy`. The only exception is when `rhs` is a non-const xvalue referring to `lcopy`, i.e. self-move-assignment isn't required to preserve the value.
- ¶1.5.2 If `rhs` is a non-const xvalue, the object it refers to is in a valid but unspecified state.
- ¶1.5.3 Otherwise, if `rhs` is a glvalue, the object it refers to isn't modified.

¶2 Note 1 explains that assignment need not be defined for all values ([[structure.requirements]]). If assigning to `x` would modify another object `y`, for example because `y` is a subobject of `x`, then `x = y` is likely not in the domain of `=`.

## Swapping: `swappable` and `ranges::swap`

### Unconstrained template `swap`s are skipped

```cpp run title="poison-pill.cpp" ok
#include <concepts>
#include <cstdio>
#include <utility>

namespace N {
  struct A { int v; };
  template<class T>              // unconstrained template
  void swap(T& a, T& b) {
    std::puts("N::swap<T>");
    T t = a; a = b; b = t;
  }

  struct B { int v; };
  void swap(B& a, B& b) {        // non-template
    std::puts("N::swap(B&, B&)");
    std::swap(a.v, b.v);
  }
}

int main() {
  N::A a{1}, b{2};
  std::ranges::swap(a, b);   // prints nothing: N::swap<T> isn't used
  std::printf("%d %d\n", a.v, b.v);   // 2 1

  N::B c{1}, d{2};
  std::ranges::swap(c, d);   // prints N::swap(B&, B&)
  std::printf("%d %d\n", c.v, d.v);   // 2 1

  int x[2]{1, 2}, y[2]{3, 4};
  std::ranges::swap(x, y);   // element-wise swap
  std::printf("%d %d\n", x[0], y[0]); // 3 1
}
```

`std::ranges::swap` isn't a function but a **customization point object** (CPO, [[customization.point.object]]): a function object that, when called, looks for a suitable way to swap in a fixed order. ¶2 says `ranges::swap(E1, E2)` is [[g:expression-equivalent|expression-equivalent]] to an expression `S` determined as follows:

1. ¶2.1 If `E1` or `E2` has class or enumeration type and the unqualified call `(void)swap(E1, E2)` is valid, `S` is that call. Overload resolution is performed in a context that includes the declaration `template<class T> void swap(T&, T&) = delete;` and doesn't include `ranges::swap` itself. If the selected function doesn't exchange the values, the program is {{ifndr}}.
2. ¶2.2 Otherwise, if both are lvalues of arrays of equal extent and `ranges::swap(*E1, *E2)` is valid, `S` is `(void)ranges::swap_ranges(E1, E2)`, with `noexcept` matching the element-wise swap.
3. ¶2.3 Otherwise, if both are lvalues of the same type `T` that models `move_constructible<T>` and `assignable_from<T&, T>`, `S` is an expression that exchanges the values, in effect one move construction plus two move assignments. It is a constant expression when ¶2.3.1–¶2.3.3 hold; its `noexcept` equals `is_nothrow_move_constructible_v<T> && is_nothrow_move_assignable_v<T>`.
4. ¶2.4 Otherwise `ranges::swap(E1, E2)` is ill-formed. Per Note 3, in the immediate context of a template instantiation this is only a substitution failure.

¶3 Note 4 sums up: whenever `ranges::swap(E1, E2)` is valid, it exchanges the values and has type `void`.

The deleted template in ¶2.1 is often called the **poison pill**. It is as specialized as any equally general template `swap`, so an unconstrained template found by ADL (including the primary template of `std::swap`) ties with it, the call is ambiguous, and ¶2.1 doesn't apply. Note 2 describes the consequence: a user's `swap` is selected only if it is a non-template function or more specialized than the poison pill ([[temp.func.order]]). That is why `N::A` above falls through to ¶2.3. Leaving out the declaration of `ranges::swap` keeps the CPO from finding itself through unqualified lookup.

!!! impl "The libc++ implementation"
    In `<__concepts/swappable.h>`, libc++ implements ¶2.1–¶2.3 with three constrained `operator()`s, with the poison pill declared in the same internal namespace. ¶2.3 is written as `__y = std::exchange(__x, std::move(__y));`.

### Defining "exchanges the values" (¶1)

¶1 first gives the semantic term. Let `t1` and `t2` denote distinct but equal objects of type `T`, and likewise `u1` and `u2`. An operation **exchanges the values** ([[g:exchanges-values|exchanges the values]]) denoted by `t1` and `u1` if and only if it doesn't modify `t2` or `u2`, and:

- ¶1.1 if `T` and `U` are the same, the result is that `t1` equals `u2` and `u1` equals `t2`;
- ¶1.2 if `T` and `U` are different but model `common_reference_with<decltype((t1)), decltype((u1))>`, the same holds under the common reference type `C`.

`t2` and `u2` record the values before the swap and are used to state the result after it. Note 1 allows `t1` and `u1` to be the same object, so a self-swap must leave the value unchanged.

### The two concepts

```cpp
template<class T>
  concept swappable = requires(T& a, T& b) { ranges::swap(a, b); };

template<class T, class U>
  concept swappable_with =
    common_reference_with<T, U> &&
    requires(T&& t, U&& u) {
      ranges::swap(std::forward<T>(t), std::forward<T>(t));
      ranges::swap(std::forward<U>(u), std::forward<U>(u));
      ranges::swap(std::forward<T>(t), std::forward<U>(u));
      ranges::swap(std::forward<U>(u), std::forward<T>(t));
    };
```

`swappable<T>` takes a type and checks whether two lvalues of it can be swapped. The arguments of `swappable_with<T, U>` are usually reference types, such as `swappable_with<int&, int&>`, which is what makes it possible to express swapping an lvalue with a proxy rvalue. `value_swap(a1, proxy(a2))` in the standard's Example 1 is such a use. It requires all four combinations to be swappable, plus a common reference.

¶4 Note 5 says the semantics of these two concepts are fully specified by `ranges::swap`: ¶2.1 already makes not exchanging values IFNDR, and ¶2.2 and ¶2.3 themselves guarantee exchanging values, so no separate semantic paragraph is needed.

## Construction and destruction

### `destructible`

```cpp
template<class T>
  concept destructible = is_nothrow_destructible_v<T>;
```

¶1 says it specifies properties of all types with which instances can be destroyed at the end of their lifetime, and of reference types. Arrays of known bound satisfy it; `void`, function types and arrays of unknown bound don't. ¶2 Note 1 points out the difference from *Cpp17Destructible*: a type with a **potentially-throwing** destructor (for example, one declared `noexcept(false)`) never satisfies it, even if a particular destruction doesn't actually throw.

This propagates up the composition chain. `constructible_from` begins with `destructible`, so such a type isn't `move_constructible`, nor `movable`, `copyable` or `regular`, and most ranges algorithms and views can't use it.

```cpp run title="destructible.cpp" ok
#include <concepts>

struct Throwy { ~Throwy() noexcept(false) {} };
static_assert(!std::destructible<Throwy>);
static_assert(!std::movable<Throwy>);   // propagates upward
static_assert(std::destructible<int&>);
static_assert(!std::destructible<void>);
static_assert(!std::destructible<int[]>);
static_assert(std::destructible<int[3]>);

int main() {}
```

### `constructible_from`

```cpp
template<class T, class... Args>
  concept constructible_from = destructible<T> && is_constructible_v<T, Args...>;
```

¶1 says it constrains the initialization of a variable from a given set of argument types. `is_constructible_v<T, Args...>` checks whether `T t(declval<Args>()...);` is well-formed ([[meta.unary.prop]]), i.e. direct-initialization. `destructible<T>` is added because an object that can be constructed but not safely destroyed is useless in value semantics. This concept has no semantic requirements.

### `default_initializable`: all three forms must work

```cpp run title="default-initializable.cpp" ok
#include <concepts>
#include <type_traits>

static_assert(std::is_default_constructible_v<const int>);
static_assert(!std::default_initializable<const int>);

struct CM  { const int x; };
struct CM2 { const int x = 0; };
static_assert(!std::default_initializable<CM>);
static_assert(std::default_initializable<CM2>);

struct E { explicit E() = default; };
struct A { E e; };
static_assert(std::is_default_constructible_v<A>);
static_assert(!std::default_initializable<A>);

int main() {}
```

`const int()` can be written, but `const int t;` can't, because a const object must be initialized unless its type is a [[g:const-default-constructible]] class ([[dcl.init]]). Generic code uses all three forms, so the concept checks all three:

```cpp
template<class T>
  constexpr bool is-default-initializable = see below;   // exposition only

template<class T>
  concept default_initializable = constructible_from<T> &&
                                  requires { T{}; } &&
                                  is-default-initializable<T>;
```

| Form | Kind of initialization | Checked by |
|---|---|---|
| `T()` | Value-initialization | `constructible_from<T>` |
| `T{}` | List-initialization (value-initialization or aggregate initialization) | `requires { T{}; }` |
| `T t;` | Default-initialization | *`is-default-initializable`* |

¶1 defines *`is-default-initializable<T>`*: true if the variable definition `T t;` is well-formed. Access checking is performed as if in a context unrelated to `T`, and only the validity of the immediate context of the variable initialization is considered.

`A` in the example shows that `T{}` can fail on its own. `A()` is value-initialization, which is fine; `A{}` is aggregate initialization, which copy-list-initializes the member `e`, and copy-list-initialization selecting an `explicit` constructor is ill-formed.

!!! impl "How libc++ checks `T t;`"
    A requires-expression can't declare variables, so whether `T t;` is well-formed can't be written directly. In `<__concepts/constructible.h>`, libc++ approximates it with `requires { ::new _Tp; }`: a new-expression without an initializer default-initializes the object, by the same rules as `T t;` ([[expr.new]]).

!!! history
    In the C++20 draft this concept was originally called `default_constructible` and checked only `is_default_constructible`. It was later found to say `const int` is default constructible, which didn't match how generic code is actually written, so before C++20 shipped the `T{}` and `T t;` checks were added and it got its current name.

### `move_constructible`

```cpp run title="explicit-move.cpp" ok
#include <concepts>

struct ExplMove {
  ExplMove() = default;
  explicit ExplMove(ExplMove&&) = default;
};
static_assert(std::constructible_from<ExplMove, ExplMove>);
static_assert(!std::move_constructible<ExplMove>);

int main() {}
```

```cpp
template<class T>
  concept move_constructible = constructible_from<T, T> && convertible_to<T, T>;
```

`constructible_from<T, T>` checks `T t(rv)`, and `convertible_to<T, T>` checks `T t = rv;` and `static_cast<T>(rv)`. A type whose move constructor is `explicit` fails the second term.

Note that `ExplMove x = ExplMove{};` is itself valid: C++17's mandatory copy elision means no move constructor is called at all. But `is_convertible_v<ExplMove, ExplMove>` uses `declval<ExplMove>()`, an xvalue, and initializing from it really must call the move constructor, so it fails.

¶1's semantic requirements (when `T` is an object type): let `rv` be an rvalue of type `T` and `u2` a distinct object equal to `rv`.

- ¶1.1 After the definition `T u = rv;`, `u` equals `u2`;
- ¶1.2 `T(rv)` equals `u2`;
- ¶1.3 If `T` isn't const, `rv` is afterwards in a valid but unspecified state; otherwise it is unchanged.

When `T` is a reference type, `move_constructible<int&>` is also true, but there are no semantic requirements.

### `copy_constructible`

```cpp
template<class T>
  concept copy_constructible =
    move_constructible<T> &&
    constructible_from<T, T&> && convertible_to<T&, T> &&
    constructible_from<T, const T&> && convertible_to<const T&, T> &&
    constructible_from<T, const T> && convertible_to<const T, T>;
```

There are three sources of copying: a non-const lvalue, a const lvalue and a const rvalue, and each requires both the direct and the implicit path to work. The implicit expression variations of [[concepts.equality]] paragraph 6 apply only to expressions written in requires-expressions; here type traits are used, so each case has to be listed.

These are all only syntactic checks. For a type with an unconstrained forwarding constructor `template<class U> S(U&&)`, the template is a better match than `S(const S&)` for a non-const lvalue, so `S s2 = s1;` doesn't call the copy constructor at all. It still satisfies `copy_constructible`; if the object that template constructs isn't equal to `s1`, it satisfies without modeling.

¶1's semantic requirements (when `T` is an object type): let `v` be an lvalue of type `T` or `const T`, or an rvalue of type `const T`.

- ¶1.1 After the definition `T u = v;`, `u` equals `v`, and `v` isn't modified;
- ¶1.2 `T(v)` equals `v` and doesn't modify `v`.

The copy equals the original and the original is unchanged: that is what copying means. A copy-means-transfer design like `auto_ptr` violates it.

## Common misconceptions

!!! pitfall "A concept is the same as the *Cpp17* requirement of the same name"
    The concepts are usually stricter. `destructible` forbids potentially-throwing destructors; `default_initializable` requires three forms; `move_constructible` requires implicit convertibility, ruling out `explicit` move constructors; `assignable_from` requires returning `T&` and a common reference. When migrating from C++17 to concepts, types that used to work but no longer satisfy the concepts usually fail at one of these points.

!!! pitfall "Customizing swap with a template `swap` as before, in ranges"
    If you write an unconstrained `template<class T> void swap(T&, T&)` in your own namespace, `ranges::swap` skips it because it is ambiguous with the poison pill, and falls back to the three-move swap. Provide a non-template `swap` for the specific type (preferably a hidden friend), or constrain the template so that it is more specialized than the poison pill.

## Questions

!!! question "Questions"
    1. Is `std::convertible_to<int, short>` true? Do `int` and `short` model it?
    2. Why does `assignable_from` require `common_reference_with<const remove_reference_t<LHS>&, const remove_reference_t<RHS>&>`, rather than just `convertible_to<RHS, remove_reference_t<LHS>>`?
    3. For two `int` lvalues `x` and `y`, which item of ¶2 does `ranges::swap(x, y)` take? What about `ranges::swap(x, x)`?

<details markdown="1">
<summary>Answer</summary>

1. It is true, and they model it. Narrowing is prohibited only in list-initialization ([[dcl.init.list]]); both implicit and explicit conversion work, both give the same value, and the source object isn't modified. `convertible_to` only requires the two paths to agree, not the conversion to be lossless; losslessness is a concern only of the semantic requirements of `common_reference_with`.
2. ¶1.5.1 requires `lhs` to equal `rcopy` after the assignment, which needs the values on both sides to be comparable under the same notion of equality. A common reference provides such a shared domain of values, and conversion to it preserves equality. Mere convertibility can't do that: `RHS` might convert to the value type of `LHS` yet have no consistent notion of equality with it.
3. `int` isn't a class or enumeration type, so ¶2.1 doesn't apply; nor is it an array, so ¶2.2 doesn't apply. `int` models `move_constructible` and `assignable_from<int&, int>`, so it takes ¶2.3, and the result is a constant expression and `noexcept`. `ranges::swap(x, x)` also takes ¶2.3; by Note 1 of ¶1 it must leave `x` with its original value, which a move construction plus two move assignments does for `int`.
</details>

## Quick reference

| Concept | Syntactic core | Semantics and design points |
|---|---|---|
| `same_as` | `is_same_v` both ways | Writing it both ways makes `same_as<T,U>` and `same_as<U,T>` subsume each other |
| `derived_from` | `is_base_of` + pointer convertibility | Only public, unambiguous derivation counts |
| `convertible_to` | Both implicit and explicit | Both paths give equal results; an rvalue source may be moved from |
| `common_reference_with` | Symmetric `common_reference_t` | Converting to `C` preserves equality and doesn't merge values |
| `common_with` | Symmetric `common_type_t` | Same as above, the value version |
| `integral` and others | Type traits | `bool` and character types count too |
| `assignable_from<L, R>` | `L` is an lvalue reference, the result is exactly `L` | Returns the left operand itself; self-move is the exception |
| `swappable(_with)` | `ranges::swap` is callable | Semantics specified by the CPO |
| `destructible` | `is_nothrow_destructible` | A potentially-throwing destructor doesn't satisfy it |
| `constructible_from` | `destructible` + `is_constructible` | Direct-initialization |
| `default_initializable` | `T()`, `T{}`, `T t;` | `const int` doesn't satisfy it |
| `move_constructible` | Construction + implicit conversion from `T` | An `explicit` move constructor doesn't satisfy it |
| `copy_constructible` | Three sources × two paths | The copy equals the original, and the original is unchanged |
