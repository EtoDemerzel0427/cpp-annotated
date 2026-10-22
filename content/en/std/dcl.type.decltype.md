---
title: Decltype specifiers
summary: "What type decltype(e) yields: unparenthesized names and member accesses give the declared type, other expressions give T&&, T& or T according to value category; a prvalue operand creates no temporary, so incomplete types and deleted destructors are allowed."
updated: 2026-10-19
---

!!! tldr
    - `decltype(x)` is the type variable `x` was declared with; `decltype((x))` treats `(x)` as an expression, and an lvalue gives `T&`. One pair of parentheses changes the result.
    - For general expressions, `decltype` encodes the value category in a reference: an xvalue gives `T&&`, an lvalue gives `T&`, a prvalue gives `T`.
    - Unparenthesized structured bindings, constant template parameters and splice expressions also give a declared type, each with its own rule.
    - The operand of `decltype` is not evaluated. When the operand is a prvalue, no temporary is created, so the type may be incomplete and the destructor may be deleted, but this only holds for the outermost prvalue.
    - `decltype(auto)` copies these rules, so `return (v);` makes it deduce a reference.

## The difference one pair of parentheses makes ¶1

```cpp run ok
#include <type_traits>
template<class A, class B> constexpr bool same = std::is_same_v<A, B>;

int i;
struct A { double x; };
const A* a = new A();

static_assert(same<decltype(i), int>);                 // declared type of the variable i
static_assert(same<decltype((i)), int&>);              // the expression (i) is an lvalue
static_assert(same<decltype(a->x), double>);           // declared type of the member A::x
static_assert(same<decltype((a->x)), const double&>);  // a points to const, so the expression is a const lvalue
int main() {}
```

`decltype` really packs two queries into one keyword. When the operand is an unparenthesized name or member access, it asks for the **declared type** of the entity the name denotes: `A::x` is declared `double`, and `a` pointing to const doesn't matter. When the operand is any other expression (one pair of parentheses is enough), it asks for the expression's type and **value category**. Value categories classify expressions ([[basic.lval]]): an lvalue designates an object or function with identity, an xvalue designates an object whose resources can be taken (such as the result of `std::move(x)`), and a prvalue is a pure value used to initialize an object (such as `42`, or the non-reference value returned by `f()`).

Both needs are real. Declaring a variable of the same type as `x` (`decltype(x) y;`) needs the declared type, without a stray `&`; writing `auto f(T t) -> decltype(t.get())` needs the expression's type and value category, to preserve exactly whether a reference or a value is returned. Distinguishing them by parentheses is a compromise: a single unparenthesized name is treated as an entity, everything else as an expression.

¶1 For an expression E, `decltype(E)` takes the first applicable rule, in order:

| ¶ | Form of E | `decltype(E)` |
|---|---|---|
| 1.1 | Unparenthesized name naming a structured binding | The referenced type given in the structured binding declaration |
| 1.2 | Unparenthesized name naming a constant template parameter | The type of the template parameter (after `auto` or CTAD deduction) |
| 1.3 | Unparenthesized name, or unparenthesized class member access | The type of the entity named; ill-formed if there is no such entity |
| 1.4 | Unparenthesized splice expression {{c++26}} | The type of the entity, object or value designated by the splice |
| 1.5 | xvalue | `T&&`, where T is the type of E |
| 1.6 | lvalue | `T&` |
| 1.7 | Otherwise (prvalue) | `T` |

The operand of `decltype` is an **unevaluated operand** ([[expr.context]]): it is used only to determine a type, it isn't executed, and it doesn't odr-use the variables and functions in it ([[basic.def.odr]]).

### Expressions: value category becomes a reference (¶1.5–¶1.7)

```cpp run ok
#include <type_traits>
#include <utility>
template<class A, class B> constexpr bool same = std::is_same_v<A, B>;
int i;
int arr[3];
int f();
int&& rr();
struct S { int m; };
enum E { e1 };

static_assert(same<decltype(i++), int>);           // postfix ++ is a prvalue
static_assert(same<decltype(++i), int&>);          // prefix ++ is an lvalue
static_assert(same<decltype(i = 1), int&>);        // assignment is an lvalue
static_assert(same<decltype(std::move(i)), int&&>);
static_assert(same<decltype(rr()), int&&>);        // a call returning an rvalue reference is an xvalue
static_assert(same<decltype(f()), int>);
static_assert(same<decltype("abc"), const char(&)[4]>);  // a string literal is an lvalue
static_assert(same<decltype(arr), int[3]>);        // 1.3: doesn't decay to a pointer
static_assert(same<decltype(arr[0]), int&>);
static_assert(same<decltype(f), int()>);           // 1.3: function type
static_assert(same<decltype((f)), int(&)()>);
static_assert(same<decltype(true ? i : 1), int>);  // one side is a prvalue, so the result is a prvalue
static_assert(same<decltype(true ? i : i), int&>);
static_assert(same<decltype((S{}.m)), int&&>);     // a member of a temporary is an xvalue
static_assert(same<decltype((e1)), E>);            // an enumerator is a prvalue
int main() {}
```

For forms like `decltype(i++)`, Clang gives a `-Wunevaluated-expression` warning, reminding you that the side effects won't happen.

### Names and member accesses (¶1.3)

Inside a member function, a member name `m` is implicitly transformed into `this->m` ([[class.mfct.non.static]]), but in the source it is still an unparenthesized name, so it gives the declared type. Variables captured by copy in a lambda are similar: unparenthesized, `decltype` gives the declared type of the original variable; parenthesized, it is treated as an access to a member of the closure object, and the default `operator()` is const ([[expr.prim.id.unqual]]).

```cpp run ok
#include <type_traits>
struct W {
    int m;
    void cf() const {
        static_assert(std::is_same_v<decltype(m), int>);
        static_assert(std::is_same_v<decltype((m)), const int&>);  // this is const W*
    }
};
int main() {
    W{1}.cf();
    int loc = 0;
    auto l = [loc] {
        static_assert(std::is_same_v<decltype(loc), int>);
        static_assert(std::is_same_v<decltype((loc)), const int&>);
        return loc;
    };
    return l();
}
```

The second half of ¶1.3 says it is ill-formed if the name doesn't name an entity. The typical case is an overload set: `ov` names two functions and has no single type.

```cpp error
void ov(int);
void ov(double);
using T = decltype(ov);   // error: overloaded function name
```

### Structured bindings (¶1.1)

A structured binding is not a variable but an alias for some hidden object (or a member of it). ¶1.1 makes `decltype` return the referenced type specified by [[dcl.struct.bind]]: when binding to a class member, the declared type of the member (with the hidden object's cv added); for tuple-like binding, `std::tuple_element<i, E>::type`.

```cpp run ok
#include <type_traits>
#include <tuple>
template<class A, class B> constexpr bool same = std::is_same_v<A, B>;
int g = 0;
int main() {
    std::tuple<int, int&> tp{1, g};
    auto [p, q] = tp;
    static_assert(same<decltype(p), int>);     // tuple_element<0>::type
    static_assert(same<decltype(q), int&>);    // tuple_element<1>::type is itself a reference
    static_assert(same<decltype((p)), int&>);  // parenthesized: an ordinary lvalue

    struct S { int x; const int y; } s{1, 2};
    auto& [sx, sy] = s;
    static_assert(same<decltype(sx), int>);        // not int&
    static_assert(same<decltype(sy), const int>);
    return p - 1;
}
```

In `auto& [sx, sy] = s;` the `&` applies to the hidden object `e` (of type `S&`); `sx` is just a name for `e.x`, and its referenced type is `int`.

### Constant template parameters (¶1.2)

```cpp run ok
#include <type_traits>
struct C { int v; };
template<auto N> void t() {
    static_assert(std::is_same_v<decltype(N), int>);    // the deduced type
    static_assert(std::is_same_v<decltype((N)), int>);  // a scalar parameter is a prvalue
}
template<C c> void u() {
    static_assert(std::is_same_v<decltype(c), C>);
    static_assert(std::is_same_v<decltype((c)), const C&>);  // a class-type parameter is a const lvalue
}
int main() { t<1>(); u<C{1}>(); }
```

A constant template parameter is not a variable. A parameter of scalar type is a prvalue in expressions; a parameter of class type designates a **template parameter object** ([[temp.param]]) and is a const lvalue. ¶1.2 uniformly gives the declared type after deduction; when parenthesized, the value category rules apply.

### Pack indexing and splicing (¶1.3, ¶1.4)

An unparenthesized pack indexing expression `pack...[0]` ([[expr.prim.pack.index]]) counts as a name and gives the declared type of parameter 0:

```cpp run ok
#include <type_traits>
void f() {
    [](auto... pack) {
        static_assert(std::is_same_v<decltype(pack...[0]), int>);
        static_assert(std::is_same_v<decltype((pack...[0])), int&>);
    }(0);
}
int main() { f(); }
```

¶1.4 treats C++26 splice expressions `[: r :]` the same way. In the standard's example `x1` is a variable of type `const int&&`, `decltype([:^^x1:])` is `const int&&`, and `decltype(([:^^x1:]))` is `const int&`. Clang 23 doesn't implement reflection yet, so this hasn't been verified.

## A prvalue operand creates no temporary (¶2)

```cpp run ok
struct Incomplete;
Incomplete make();
using T1 = decltype(make());     // OK: incomplete type

struct Abstract { virtual void f() = 0; };
Abstract mk_abs();
using T2 = decltype(mk_abs());   // OK: abstract class

struct NoDtor { ~NoDtor() = delete; };
NoDtor mk();
using T3 = decltype(mk());       // OK: the destructor is deleted
using T4 = decltype((mk()));     // OK: parentheses make no difference
using T5 = decltype(0, mk());    // OK: the result is still this prvalue
int main() {}
```

¶2 If the operand of `decltype` is a prvalue, the **temporary materialization** conversion (which turns a prvalue into a temporary object, [[conv.rval]]) is not applied, and no result object is provided for it. So the prvalue's type may be incomplete or an abstract class. The wording excludes a (possibly parenthesized) immediate invocation; an immediate invocation is a kind of call to a `consteval` function, defined precisely in [[expr.const.imm]].

Note 2 explains the consequences: since no storage is allocated for the prvalue, it doesn't need to be destroyed, so the returned class template need not be instantiated and the destructor need not be checked for accessibility. Note 3 points out that, unlike in ¶1, parentheses have no special meaning here.

The protection only applies to the outermost prvalue. Once a prvalue is used to initialize another object, or appears as a discarded-value expression, it is materialized:

```cpp error
struct NoDtor { ~NoDtor() = delete; };
NoDtor mk();
void take(NoDtor);
using T6 = decltype(take(mk()));   // error: the parameter object needs to be destroyed
using T7 = decltype(mk(), 0);      // error: the left side of the comma is a discarded-value expression and is materialized
```

In `take(mk())`, `mk()` initializes the parameter directly with no extra temporary, but the parameter object is destroyed by the caller ([[expr.call]]), so the destructor is still used.

### Why this rule matters

Example 2 in the standard shows its effect on overload resolution:

```cpp
template<class T> struct A { ~A() = delete; };
template<class T> auto h() -> A<T>;
template<class T> auto i(T) -> T;                      // identity function
template<class T> auto f(T) -> decltype(i(h<T>()));   // #1
template<class T> auto f(T) -> void;                   // #2
auto g() -> void {
    f(42);    // OK: calls #2
}
template<class T> auto q(T) -> decltype((h<T>()));
void r() {
    q(42);    // error
}
```

In the return type of `#1`, `h<T>()` is an argument of `i` and has to be materialized into an object to initialize `i`'s parameter; this requires `A<int>` to be complete and uses the deleted destructor. So substitution fails (SFINAE, [[temp.deduct]]), `#1` is discarded and `#2` is chosen. The result of `i(...)` itself is the direct operand of `decltype` and introduces no further temporary.

The return type of `q`, `decltype((h<T>()))`, doesn't require `A<T>` to be complete, so deduction succeeds and `q<int>` is chosen. But the call `q(42)` itself produces an `A<int>` temporary whose destructor must be used, so `r` is ill-formed.

This rule was added by [[N3276]] before C++11 was finalized. It targets deeply nested return types like `auto f(...) -> decltype(g(...))`: if every level required a complete return type, it would trigger lots of unnecessary class template instantiations, and in recursive structures such as expression templates even infinite recursion.

## decltype(auto)

Note 1 points out that the rules for `decltype(auto)` are in [[dcl.type.auto.deduct#4]]: it deduces by treating the initializer as the operand of `decltype`, so the effect of parentheses is preserved as is.

```cpp run ok
#include <type_traits>
int x = 0;
decltype(auto) a = x;     // int
decltype(auto) b = (x);   // int&
static_assert(std::is_same_v<decltype(a), int>);
static_assert(std::is_same_v<decltype(b), int&>);

decltype(auto) get_ref() { static int v = 0; return (v); }   // int&
static_assert(std::is_same_v<decltype(get_ref()), int&>);
int main() {}
```

!!! pitfall "Parenthesizing a local variable in a return"
    The return type of `decltype(auto) danger() { int v = 0; return (v); }` is `int&` in C++20; since C++23 an expression naming a local variable in a return statement is an xvalue ([[expr.prim.id.unqual]]), and the return type becomes `int&&`. Either way it returns a dangling reference.

## Implementation notes

!!! impl "decltype and name mangling"
    When `decltype` appears in a function template signature (a trailing return type, a default template argument), the expression is encoded in the mangled name. The Itanium ABI has two encodings: `Dt <expression> E` for an unparenthesized name or member access, and `DT <expression> E` for other expressions, exactly matching the two modes of ¶1. So `decltype(x)` and `decltype((x))` are two distinguishable spellings in a signature.

## History

!!! history
    - C++11 introduced `decltype`; [[N3276]] added the rule that prvalue operands are not materialized.
    - C++14 added `decltype(auto)`.
    - C++17 added structured bindings (¶1.1) and `auto` constant template parameters; C++20 added constant template parameters of class type. Their types all need deduction and are handled by ¶1.2.
    - C++23 made local variables in return statements xvalues, which affects what `decltype(auto)` deduces.
    - C++26 added pack indexing and splice expressions (¶1.4).

## Questions

!!! question "Question 1"
    Given `struct S { int m; }; const S cs{}; S&& rs();`, what are `decltype(cs.m)`, `decltype((cs.m))`, `decltype(rs().m)` and `decltype((rs().m))`?

<details markdown="1">
<summary>Answer</summary>

- `decltype(cs.m)`: an unparenthesized member access, giving the member's declared type `int`.
- `decltype((cs.m))`: `cs.m` is a `const int` lvalue, giving `const int&`.
- `decltype(rs().m)`: still an unparenthesized member access, giving `int`.
- `decltype((rs().m))`: `rs()` is an xvalue and so is its member ([[expr.ref]]), giving `int&&`.
</details>

!!! question "Question 2"
    SFINAE detection often uses `template<class T> auto f(T t) -> decltype(t.size(), void())`. Why is the right operand `void()`? How is `decltype(void(t.size()))` different?

<details markdown="1">
<summary>Answer</summary>

If `t.size()` is invalid, substitution fails and `f` is discarded; if it is valid, the whole `decltype` yields the type of the right operand, `void`.

The right operand is `void()` to avoid calling a user-overloaded comma operator: if the return type of `t.size()` has an overloaded `operator,`, but the right operand has type `void`, no user-defined `operator,` can accept it, and only the built-in comma operator can be used ([[over.match.oper]]).

`decltype(void(t.size()))` converts `t.size()` to `void`, has no comma operator issue, and works the same. In both forms `t.size()` is a discarded-value expression, so if it returns a prvalue of class type, it is materialized, requiring the type to be complete and the destructor usable; the protection of ¶2 doesn't cover it.
</details>
