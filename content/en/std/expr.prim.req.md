---
title: Requires expressions
summary: "A prvalue of type bool that checks at compile time whether a set of expressions and types is valid: the four kinds of requirements, local parameters, why a substitution failure gives false, and why that only holds in the immediate context."
updated: 2026-10-19
---

!!! tldr
    - A requires-expression is a prvalue of type `bool`: `requires (T t) { t.size(); }` is `true` when `t.size()` is valid and `false` otherwise.
    - There are four kinds of requirements: a simple requirement `e;` only checks that the expression is valid, a type requirement `typename X;` only checks that the type can be formed, a compound requirement `{ e } noexcept -> C;` also checks non-throwing and the type, and only a nested requirement `requires constraint;` checks values.
    - A substitution failure gives `false` only if it happens in the immediate context; errors inside a class template instantiation or a function body are still hard errors. Requirements are checked in the order written, stopping at the first failure.
    - The return-type check of a compound requirement uses `decltype((e))`, so an lvalue expression gives a reference type, and `{ t.x } -> std::same_as<int>` usually doesn't hold.
    - Local parameters are only notation, with no storage and no value; in requirements they are lvalues.

## Usage

Before C++20, detecting whether a type has a `size()` member took SFINAE and partial specialization; a requires-expression writes the same check out directly:

<div class="compare" markdown="1">

```cpp ok
// C++17
#include <type_traits>
#include <utility>
template<class T, class = void>
struct has_size : std::false_type {};
template<class T>
struct has_size<T, std::void_t<
  decltype(std::declval<T&>().size())>>
  : std::true_type {};
```

```cpp ok
// C++20
template<class T>
concept has_size = requires (T& t) {
  t.size();
};
```

</div>

¶2 A **requires-expression** ([[g:requires-expression|requires-expression]]) is a prvalue of type `bool` and can be used wherever a `bool` constant is needed: concept definitions, *requires-clause*s, `static_assert`, the condition of `if constexpr`.

¶3 Example 1 in the standard shows two typical uses. One is defining a concept:

```cpp run ok
#include <concepts>

template<typename T>
concept R = requires (T i) {
  typename T::type;                                        // type requirement
  { *i } -> std::convertible_to<const typename T::type&>;  // compound requirement
};

struct It { using type = int; int operator*() const; };
static_assert(R<It>);
static_assert(!R<int>);   // int has no ::type: the result is false, not a compile error

int main() {}
```

The other is writing it directly in a *requires-clause* ([[temp.pre]]), giving `requires requires`:

```cpp run ok
template<typename T>
  requires requires (T x) { x + x; }
T add(T a, T b) { return a + b; }

int main() { return add(1, 2) - 3; }
```

The first `requires` introduces the *requires-clause*, the second starts a requires-expression. This is valid, but usually the requirements should be extracted into a named concept. The reason isn't only readability: two requires-expressions written separately in two templates, even if identical token for token, are two different atomic constraints and can't be compared for which is more constrained ([[temp.constr.order]]).

## Grammar and local parameters (¶1, ¶4)

¶1 A requires-expression consists of the keyword `requires`, an optional parameter list, and a sequence of requirements in braces:

```text
requires-expression:  requires ( parameter-declaration-clause )opt { requirement-seq }
requirement:          simple-requirement | type-requirement
                    | compound-requirement | nested-requirement
```

The *requirement-seq* can't be omitted, so `requires {}` is invalid.

| Kind | Form | What it checks |
|---|---|---|
| Simple requirement | `e;` | The expression is valid |
| Type requirement | `typename T::type;` | The type can be formed |
| Compound requirement | `{ e } noexcept -> C;` | The expression is valid, optionally non-throwing and with a type satisfying a concept |
| Nested requirement | `requires constraint;` | The constraint is satisfied; can check values |

¶4 The parameter list introduces **local parameters**. Their types are determined by the rules for function parameters ([[dcl.fct]]), so arrays are adjusted to pointers and top-level cv is dropped. Local parameters have no linkage, no storage and no lifetime; they are only notation for writing requirements. They can't have default arguments, and the parameter list can't end with `...`.

```cpp error
template<typename T>
concept C = requires(T t, ...) {   // error: ends with an ellipsis
  t;
};

template<typename T>
concept C2 = requires(T p[2]) {
  (decltype(p))nullptr;            // OK: p has type T*
};
```

With local parameters you don't need `std::declval<T&>()`. Note that `t` is a named variable and is an lvalue in the requirements. To check operations on a const object, write `requires (const T& t)`; to check operations on an rvalue, write `std::move(t)`.

## Substitution failure gives false (¶5)

¶5 The value of a requires-expression is determined like this: the template arguments are substituted into the requirements. If an invalid type or expression is formed in the immediate context of a requirement, or a semantic constraint of a requirement is violated (for example, the return-type constraint of a compound requirement is not satisfied), the result is `false`, and the program is not ill-formed because of it. If everything passes, it is `true`.

The **immediate context** ([[g:immediate-context|immediate context]]) is the same as for SFINAE ([[temp.deduct.general]]): only the types and expressions written directly in the requirement. If substitution needs to instantiate some class template or function template, and the error happens inside that instantiation, it is not a substitution failure but a hard error.

```cpp error
template<class T> struct Bad { static_assert(sizeof(T) == 0); using type = int; };

template<class T> concept HB = requires { typename Bad<T>::type; };
bool hb = HB<int>;   // error: the static_assert fails while instantiating Bad<int>, not in the immediate context
```

¶5 also says substitution and checking proceed in lexical order and stop when a condition that determines the result is encountered. So after the first requirement fails, the later ones are not substituted at all. Putting requirements that filter out unsuitable types first keeps later requirements from triggering hard errors:

```cpp ok
template<class T> struct Bad { static_assert(sizeof(T) == 0); using type = int; };

template<class T> concept Safe = requires {
  typename T::type;          // for int: fails, stops here
  typename Bad<T>::type;     // never substituted, Bad<int> is not instantiated
};
static_assert(!Safe<int>);
```

### Requires-expressions outside templates

Note 1 says that if a requires-expression is not in the declaration of a **templated entity** ([[g:templated-entity|templated entity]], templates and things defined inside templates, [[temp.pre]]) and its requirements contain invalid types or expressions, the program is ill-formed. There are no template arguments to substitute, so these requirements are checked when parsed, and invalidity is an ordinary compile error.

But that doesn't mean a requires-expression in non-template code can only be `true`. When all the expressions are valid but a semantic constraint is not satisfied, the result is still `false`:

```cpp ok
#include <concepts>

constexpr bool b1 = requires { 1 + 1; };                            // true
constexpr bool b2 = requires { requires false; };                   // false: nested requirement not satisfied
constexpr bool b3 = requires { { 1 } -> std::same_as<long>; };      // false: return-type constraint not satisfied
static_assert(b1 && !b2 && !b3);
```

```cpp error
constexpr bool b4 = requires { nonexistent(); };      // error: not in a template, name not declared
constexpr bool b5 = requires (int x) { x.foo(); };    // error: int has no members
```

The body of a generic lambda and member functions of class templates are also templated entities, so writing `if constexpr (requires { t.size(); })` there is a common idiom:

```cpp run ok
#include <vector>

template<class T> auto describe(T t) {
  if constexpr (requires { t.size(); }) return t.size();
  else return 0;
}

int main() { return describe(1) + int(describe(std::vector<int>{})); }
```

### Requirements that always fail

The last sentence of ¶5: if substitution into a requirement would always fail, whatever the template arguments, the program is **ill-formed, no diagnostic required** (IFNDR) {{ifndr}}: the compiler may not report an error, but the program has no guarantees at all.

```cpp ifndr
template<typename T> concept C =
  requires {
    new decltype((void)T{});   // new void for any T, never valid
  };
```

This rule follows the same idea as "a template with no valid specialization is IFNDR" in [[temp.res]]: it lets compilers report obviously wrong requirements at the definition, without forcing them to prove that a requirement always fails. Clang 23 doesn't diagnose the example above, which is conforming.

## Simple requirements [expr.prim.req.simple]

¶1 A simple requirement `e;` asserts that the expression `e` is valid. `e` is an **unevaluated operand** ([[g:unevaluated-operand|unevaluated operand]], [[expr.context]]): it is not executed and odr-uses nothing.

```cpp ok
template<typename T> concept Addable = requires (T a, T b) {
  a + b;   // only requires a + b to be valid, doesn't care about the result
};
static_assert(Addable<int> && !Addable<int*>);
```

¶2 A requirement that starts with the token `requires` is never a simple requirement; it is a nested requirement. If `requires C<T>;` were a simple requirement, it would check whether a requires-expression or concept specialization itself is valid, which almost always holds and means nothing.

!!! pitfall "Simple requirements don't check values"
    ```cpp
    template<class T> concept Wrong = requires { sizeof(T) > 4; };           // only checks the expression is valid: always true for complete types
    template<class T> concept Right = requires { requires sizeof(T) > 4; };  // nested requirement: checks the value
    template<class T> concept Best  = sizeof(T) > 4;                         // the most direct form
    ```

## Type requirements [expr.prim.req.type]

¶1 A type requirement `typename …;` asserts that a type is valid. Common uses:

```cpp ok
template<typename T, typename T::type = 0> struct S;
template<typename T> using Ref = T&;

template<typename T> concept C = requires {
  typename T::inner;   // the nested type exists
  typename S<T>;       // the template-id is valid: T::type exists and 0 converts to it
  typename Ref<T>;     // alias template substitution succeeds: fails for T = void
};

struct Good { using inner = int; using type = int; };
static_assert(C<Good>);
static_assert(!C<int>);
```

Since C++26, a type requirement can also be a splice `typename [: r :];`, which fails when `r` is not a reflection of a type ([[expr.prim.splice]]). {{c++26}}

¶2 A type requirement that names a class template specialization doesn't require the type to be complete. In the example above `S` is only declared, never defined, and `C<Good>` still holds. `typename S<T>;` only checks that the name can be formed; it doesn't instantiate the definition of `S<T>`, so it doesn't trigger errors inside the class template body either.

## Compound requirements [expr.prim.req.compound]

```text
compound-requirement:  { expression } noexcept-specifier(opt) return-type-requirement(opt) ;
return-type-requirement:  -> type-constraint
```

¶1 A compound requirement asserts properties of the expression `E`. `E` is an unevaluated operand. The checks happen in this order; if any step fails, the result is `false`:

1. (1.1) `E` is substituted;
2. (1.2) if there is a *noexcept-specifier*, its constant expression is substituted; if its value is `true`, `E` must not be a potentially-throwing expression ([[except.spec]]);
3. (1.3) if there is a return-type requirement, the *type-constraint* is substituted, and then its immediately-declared constraint ([[g:immediately-declared-constraint|immediately-declared constraint]], [[temp.param]]) on `decltype((E))` must be satisfied.

Step 3 means `{ E } -> C<A>;` checks `C<decltype((E)), A>`. Example 1 in the standard shows this with an equivalent rewrite:

<div class="compare" markdown="1">

```cpp
requires {
  { E1 } -> C;
  { E2 } -> D<A1, A2>;
};
```

```cpp
requires {
  E1; requires C<decltype((E1))>;
  E2; requires D<decltype((E2)), A1, A2>;
};
```

</div>

The double-parenthesized `decltype((E))` keeps the value category: an lvalue gives `T&`, an xvalue gives `T&&`, a prvalue gives `T`. This is the most error-prone part of compound requirements:

```cpp ok
#include <concepts>

struct P { int x; };
template<class T> concept HasX  = requires (T t) { { t.x } -> std::same_as<int>; };
template<class T> concept HasX2 = requires (T t) { { t.x } -> std::same_as<int&>; };
static_assert(!HasX<P>);   // t.x is an lvalue, decltype((t.x)) is int&
static_assert(HasX2<P>);
```

So when checking a return type, you usually write `std::convertible_to<int>` rather than `std::same_as<int>`.

¶2 Example 2 in the standard sums up three common forms:

```cpp ok
#include <concepts>
#include <vector>

template<typename T> concept C1 = requires(T x) {
  {x++};                                     // equivalent to the simple requirement x++;
};
template<typename T> concept C2 = requires(T x) {
  {*x} -> std::same_as<typename T::inner>;   // *x valid, T::inner is a type, same_as<decltype((*x)), T::inner>
};
template<typename T> concept NoThrowSwap = requires(T& a, T& b) {
  { a.swap(b) } noexcept;                    // valid and not potentially-throwing
};

static_assert(C1<int>);
static_assert(NoThrowSwap<std::vector<int>>);
```

!!! note "`noexcept(condition)`"
    The C++20 grammar allowed only a bare `noexcept` here. The current draft changed it to a *noexcept-specifier*, so `noexcept(constant-expression)` can also be written, and `noexcept(false)` imposes no requirement, making it easy to require non-throwing conditionally in generic code. This is new wording after C++23. As of this writing, Clang 23 still doesn't accept `{ e } noexcept(true);`, complaining that it expected `->`.

## Nested requirements [expr.prim.req.nested]

¶1 A nested requirement `requires constraint-expression;` requires that the constraint expression be satisfied with the substituted template arguments ([[temp.constr.decl]]). The constraint expression is handled by the rules for constraints: it is first normalized into conjunctions and disjunctions of atomic constraints, which are then checked one by one, with `&&` and `||` short-circuiting ([[temp.constr.constr]]); it is not substituted as a whole like an ordinary expression.

```cpp ok
template<typename U> concept C = sizeof(U) == 1;

template<typename T> concept D = requires (T t) {
  requires C<decltype(+t)>;   // for char, +t is promoted to int
};
static_assert(!D<char>);
```

A nested requirement is the only way to check a value inside a requires-expression, but what it checks must be a constant expression. Local parameters have no value, so `requires t > 0;` is not a constant expression after substitution, and the program is ill-formed ([[temp.constr.atomic]]) rather than giving `false`. In a nested requirement, local parameters can only appear in unevaluated places such as `sizeof` and `decltype`:

<div class="compare" markdown="1">

```cpp error
template<class T>
concept V = requires (T t) {
  requires t > 0;
};
bool v = V<int>;
// error: not a constant expression
```

```cpp ok
template<class T>
concept Big = requires (T t) {
  requires sizeof(t) > 4;
};
static_assert(Big<double>);
static_assert(!Big<char>);
```

</div>

A nested requirement can contain another requires-expression, commonly used to express negation:

```cpp ok
template<class T> concept NoFoo = requires (T t) {
  *t;
  requires !requires { t.foo(); };   // t must not have foo()
};
static_assert(NoFoo<int*>);
```

`!requires {…}` as a whole is one atomic constraint (`!` is not a logical operator of constraints) and doesn't take part in subsumption.

## Implementation view

!!! impl
    - Compilers cache the satisfaction results of concept specializations. The standard says that if the same atomic constraint with the same template arguments has different satisfaction results at different points, the program is IFNDR ([[temp.constr.atomic]]), so caching is conforming. Location-dependent tricks such as using a requires-expression to detect whether a type is complete at this point are not portable.
    - When a concept isn't satisfied, Clang and GCC point out which requirement failed. The finer-grained the requirements, the more specific the diagnostics; this is one of the practical advantages over SFINAE.

## History and evolution

!!! history
    - In the Concepts TS, a compound requirement allowed `{ e } -> Type;`, meaning `e` is implicitly convertible to `Type`. That was inconsistent with the meaning of `-> Concept`, and when concepts were merged into C++20, [[P1452R2]] removed it; requiring convertibility must now be written `-> std::convertible_to<Type>`.
    - In C++26, type requirements can use splice specifiers (static reflection).

## Common mistakes

!!! pitfall "Thinking a requires-expression swallows every error"
    Only invalidity in the immediate context gives `false`. A typical example: `f` is a function template with return type `auto`; `requires (T t) { f(t); }` needs the type of `f(t)`, which means instantiating `f`'s body to deduce the return type, and errors in that body are hard errors.

!!! pitfall "Forgetting that local parameters are lvalues"
    `requires (T t) { { t } -> std::same_as<T>; }` never holds for a non-reference type `T`, because `decltype((t))` is `T&`.

## Questions

!!! question "Question 1"
    Are the following three concepts `true` or `false` for `std::string`?
    ```cpp
    template<class T> concept A = requires (T t) { { t.size() } -> std::same_as<std::size_t>; };
    template<class T> concept B = requires (T t) { { t[0] } -> std::same_as<char>; };
    template<class T> concept D = requires (const T t) { { t[0] } -> std::same_as<const char&>; };
    ```

<details markdown="1">
<summary>Answer</summary>

`A` is `true`: `t.size()` is a prvalue, and `decltype((t.size()))` is `std::size_t`. `B` is `false`: `t[0]` returns `char&`, an lvalue, so `decltype((t[0]))` is `char&`. `D` is `true`: `t` is declared `const T`; as a parameter type the top-level const is dropped, but in the requirements `t` is still a const lvalue, so the const `operator[]` is selected and returns `const char&`. Clang 23 confirms all three results in our tests.
</details>

!!! question "Question 2"
    Why does `template<class T> concept C = requires { sizeof(T) == 4; };` hold for every complete type? What about incomplete types?

<details markdown="1">
<summary>Answer</summary>

`sizeof(T) == 4;` is a simple requirement, which only checks that the expression is valid, not its value ([expr.prim.req.simple]/1). For a complete type it is always valid, so `C` is `true`. For an incomplete type, substitution into `sizeof(T)` fails and `C` is `false`. To check the value, change it to the nested requirement `requires sizeof(T) == 4;`, or simply write `concept C = sizeof(T) == 4;`.
</details>
