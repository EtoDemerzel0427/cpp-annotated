---
title: Function contract specifiers
summary: "C++26 preconditions pre and postconditions post: where they go, when they are checked, why they belong to the function rather than to a declaration or the type, how redeclarations stay consistent, and parameters and result bindings in postconditions."
updated: 2026-10-19
---

!!! tldr
    - `pre(condition)` is checked after the parameters are initialized and before the function body; `post(r: condition)` is checked when the function returns normally, not when it exits by throwing.
    - Contracts belong to the function and are introduced by its first declaration. A redeclaration either omits contracts or repeats a set with exactly the same meaning.
    - By-value parameters used in a postcondition must be `const` in all declarations of the function; otherwise the body could modify them and the postcondition would not see the value the caller passed.
    - Contracts are not part of the function type and don't take part in overload resolution; they are still checked when calling through a function pointer.
    - As of writing, Clang 23 doesn't support contract syntax; the examples on this page are analyzed from the standard text and haven't been verified by compiling, so they carry no verdict.

## Preconditions and postconditions

```cpp
#include <cstddef>
#include <vector>

// i must be a valid index; the return value never exceeds the number of elements in v
std::size_t count_from(const std::vector<int>& v,
                       std::size_t i)
  pre(i <= v.size())
  post(r: r <= v.size())
{
  return v.size() - i;
}
```

C++26 **contract assertions** ([[g:contract-assertion|contract assertion]]) come in three forms: `pre` and `post` written on function declarations, and the statement `contract_assert` in a function body ([[stmt.contract.assert]]). Their shared rules are in [[basic.contract]]: an assertion's condition is called its **predicate**, and each evaluation uses one of four semantics, ignore, observe, enforce or quick-enforce; which one is implementation-defined, usually controlled by compiler options. The last three check the predicate, and enforce and quick-enforce terminate the program on violation ([[basic.contract.eval]]).

This page covers the rules for the first two as part of a declaration.

¶1 A **function contract assertion** ([[g:function-contract-assertion|function contract assertion]]) is a contract assertion associated with a function. `pre` introduces a **precondition assertion**, associated with entering the function; `post` introduces a **postcondition assertion**, associated with exiting the function normally. Note 1 explains that leaving a function via an exception ([[expr.throw]]) or `longjmp` is not a normal exit, and postconditions aren't checked. A postcondition describes what the function guarantees when it succeeds.

¶2 The predicate is the *conditional-expression* in parentheses, contextually converted to `bool`. The grammar uses *conditional-expression* rather than *expression*, so there can be no top-level comma operator or assignment; add another pair of parentheses if needed. External variables and parameters referenced in the predicate are const, and `this` is a pointer to const ([[basic.contract.general]]).

### Where they go

```
precondition-specifier:   pre attributes(opt) ( condition )
postcondition-specifier:  post attributes(opt) ( result-name:(opt) condition )
```

`pre` and `post` are not reserved keywords; they have special meaning only in this position, and `int pre = 0;` is still valid. Contract specifiers go after the declarator and before the function body or semicolon; if there is a trailing requires-clause or `override`/`final`, they go after those ([[dcl.decl]], [[class.mem]], [[dcl.fct.def.general]]):

```cpp
#include <concepts>
int f(int x) pre(x > 0) post(r: r > x);

template<class T>
T g(T x) requires std::integral<T> pre(x != 0);

auto l = [](int n) pre(n > 0) { return n; };
```

Note 2 explains that contracts on a lambda apply to the function call operator of the closure type. [[dcl.decl.general#6]] says only a declarator that declares a function can have contract specifiers.

### When they are checked

[[expr.call]] specifies when the checks happen:

- Preconditions are evaluated after all parameters are initialized and before the function body starts;
- Postconditions are evaluated after the return value is initialized and local variables are destroyed, before the parameters are destroyed ([[stmt.return]]). If the implementation introduces temporaries for the return value ([[class.temporary]]), the order between the postconditions and the initialization of those temporaries or the result object is indeterminate.

{{c++29}} Virtual functions can also have contracts. For a virtual call through class member access, the checking order is: preconditions of the statically chosen function, preconditions of the function actually called, the function body, postconditions of the function actually called, postconditions of the statically chosen function ([[expr.call#5]]). So when calling through a base class reference, the contracts of both the base class and the final overrider are checked. For a non-virtual call with a qualified name `x.Base::f()`, only `Base::f`'s own contracts are checked. C++26 itself forbids virtual functions from having contract specifiers; the current draft has removed this restriction.

## Contracts belong to the function (¶3–5)

### Introduced by the first declaration (¶3)

A declaration is a **first declaration** ([[basic.def]]) if no other declaration of the same entity is reachable from it; otherwise it is a **redeclaration**.

¶3 Contract specifiers on a first declaration of a function introduce the corresponding contract assertions for that function. Attributes after `pre` or `post` appertain to the introduced contract assertion.

So contracts are a property of the function, not of a particular declaration. This is the opposite of default arguments ([[dcl.fct.default]]): default arguments are attached to declarations, and a declaration at block scope can have a different set; once contracts are given by the first declaration, the same set applies no matter which declaration a call finds the function through.

### Redeclarations must agree (¶4–5)

```cpp
bool b1, b2;

void f() pre (b1) pre ([]{ return b2; }());
void f();                    // OK: contracts omitted
void f() pre (b1) pre ([]{ return b2; }());
                             // IFNDR: the two closure types differ
void f() pre (b1);           // error: only part of them repeated

int g() post(r : b1);
int g() post(b1);            // error: one has a result name, the other doesn't

namespace N {
  void h() pre (b1);         // ::b1
  bool b1;
  void h() pre (b1);         // error: here it's N::b1
}
```

¶4 A redeclaration either has no contract specifiers or has the same ones as any first declaration reachable from it. If the two are in different translation units, for example with the first declaration in a module interface, a diagnostic is required only if the redeclaration is attached to a named module.

When two translation units each include the same header, the declarations in the header are first declarations in both and are not reachable from each other. Paragraph 4 requires such first declarations to have the same contract specifiers; a violation makes the program ill-formed, no diagnostic required (IFNDR): neither the compiler nor the linker may say anything.

¶5 defines what "the same" means: the same specifiers, in the same order, with each pair satisfying:

- ¶5.1 placing each predicate into a function definition would satisfy the ODR ([[basic.def.odr]]), i.e. the same tokens with each name finding the same entity. Parameters, template parameters of enclosing templates, and the result name may be renamed;
- ¶5.2 either both have a result name or neither does.

So "the same" means the same meaning, not the same text. In the example above, `N::h` writes `b1` both times, but lookup finds different entities, so the contracts differ. If the condition fails only because two lambdas in the predicates differ, no diagnostic is required, since every lambda expression has its own unique closure type.

In practice, write contracts on the declaration in the header and omit them on the definition in the source file; paragraph 4 allows this, and it avoids maintaining two copies.

## Where contracts can't appear (¶6, ¶8)

¶6 Deleted functions ([[dcl.fct.def.delete]]) and functions defaulted on their first declaration ([[dcl.fct.def.default]]) can't have contract specifiers. The former are never called; the latter's behavior is specified by the language and may be trivial.

```cpp
struct S {
  S() pre(true) = default;          // error: defaulted on its first declaration
  void f(int) pre(true) = delete;   // error: deleted function
  S(const S&);
};
S::S(const S&) pre(true) = default;
  // error: this is a redeclaration and disagrees with the in-class first declaration (no contracts)
```

¶8 is a note: when a function is called indirectly through a function pointer or pointer to member function, its contracts are still evaluated. But function pointers, pointers to member functions and function type aliases can't themselves have contract specifiers, because contracts are not part of the function type ([[dcl.fct#13]]).

```cpp
int f(int x) pre(x > 0);
int (*pf)(int) = f;             // OK: pf(-1) still checks f's precondition
int (*pg)(int) pre(true);       // error: pg is not a function
using F = int(int) pre(true);   // error: an alias can't have contracts
```

## Parameters in postconditions must be const (¶7)

A postcondition is evaluated after the function body runs, and the body can modify parameters passed by value:

```cpp
int next(int x) post(r: r == x + 1) {   // suppose this were allowed
  x = 100;
  return 1;    // the x the postcondition reads is 100, not the value the caller passed
}
```

To the caller, `x` means the value passed in. So paragraph 7 says: if the predicate of a postcondition odr-uses a non-reference parameter of the function, that parameter and its corresponding parameter in every declaration of the function must have const type. const guarantees the body can't change it, so the postcondition sees the value passed in.

Note 4 adds two points:

- The requirement also applies to declarations that don't have the postcondition; for example, if a header only has `int g(const int x);` and the definition has a postcondition, both need `const`. Top-level const is normally not part of the function type ([[dcl.fct#5]]), so this is an extra requirement;
- Parameters of array or function type are adjusted to pointers, and the pointer itself isn't const even if const was written:

```cpp
int f(const int i[10])
  post(r: r == i[0]);   // error: i has type const int*, not int* const

int g(int x) post(r: r > x);         // error: x is not const
int h(const int x) post(r: r > x);   // OK
int k(int& x) post(x > 0);           // OK: reference parameters are unrestricted
```

Reference parameters are unrestricted. They refer to the caller's object, and the postcondition reads that object's state at return, which is exactly what one wants to express about a reference parameter.

Coroutines go further: their parameters are copied into the coroutine frame and the body modifies the copies, so a coroutine postcondition that odr-uses a non-reference parameter is always ill-formed ([[dcl.fct.def.coroutine#6]]).

## Result bindings [dcl.contract.res]

```cpp
int f()
  post(r : r == 1)      // r refers to the int returned by f()
{
  return 1;
}
int i = f();            // the check passes
```

¶1 The `r :` in a postcondition is a declaration that introduces `r` as the name of the function's **result binding** ([[g:result-binding|result binding]]):

- The result binding refers to the object or reference returned by this call itself, not a copy; its type is the function's return type;
- If the return type is cv `void`, a result name can't be written;
- Note 1 explains that an expression naming the result binding is a const lvalue ([[expr.prim.id.unqual#6]]).

That the result binding refers to the returned object itself relates to a permission in [[class.temporary]]: for a return value of trivially copyable type, the implementation may first put it in a temporary (e.g. returning via registers) and then copy it to the destination. Example 2 in the standard:

```cpp
struct A {};                          // may be returned via a temporary
struct B { B() {} B(const B&) {} };   // never introduces a temporary

template <typename T>
T f(T* const ptr)
  post(r: &r == ptr)
{
  return {};
}

int main() {
  A a = f(&a);   // the check may fail: r may refer to a temporary
  B b = f(&b);   // the check always passes: r is b
}
```

When the implementation introduces a temporary, `r` refers to the most recently initialized temporary ([[expr.prim.id.unqual#14]]), whose address is not `&a`.

¶2 If the return type of a non-templated function contains a placeholder (such as `auto`), a postcondition with a result name can only be written on the definition. Without a body the return type can't be deduced, and the type of the result binding can't be determined. Templated functions aren't restricted, since there will always be a definition at instantiation.

```cpp
auto g(auto&) post(r: r >= 0);   // OK: g is a function template
auto h()      post(r: r >= 0);   // error: not a definition
auto k()      post(r: r >= 0)    // OK: a definition
{
  return 0;
}
```

## When contracts are needed (¶9)

¶9 A function's contract assertions are considered **needed** when the function is odr-used or defined. [[temp.inst]] uses this to decide when to instantiate the predicates of a function template specialization.

Note 6 explains that overload resolution doesn't consider contract specifiers. Contracts don't filter candidates the way requires-clauses do:

```cpp
template <typename T> void f(T t) pre(t == "");
template <typename T> void f(T&& t);
void g() {
  f(5);   // error: ambiguous; it doesn't matter that the first one's
          //   precondition can't even be instantiated for int
}
```

This is by design. Contracts are run-time checks of correctness, and adding or removing a contract shouldn't change which function a call selects. To exclude overloads conditionally, use a requires-clause.

## Implementation notes

!!! impl
    - The standard allows the checking code to be inserted on the caller side or the callee side. Checking at the callee's entry and exit needs only one copy of the code; checking at the call site lets different translation units use different evaluation semantics ([[basic.contract.eval]]).
    - Contract specifiers don't enter the function type and don't affect name mangling. Adding contracts to the declaration of an existing function doesn't change the ABI.
    - Inconsistent contracts on redeclarations within one translation unit must be diagnosed. Inconsistency across translation units, typically from a header included under different macro configurations, is IFNDR, and the linker usually can't detect it.

## History

!!! history
    - The C++20 working draft once added contracts with attribute syntax `[[expects: …]]`, `[[ensures r: …]]`, `[[assert: …]]` ([[P0542R5]]); because of design disagreements, they were removed entirely before C++20 shipped.
    - The design then restarted with a minimal viable product as its goal, eventually becoming [[P2900]]: switching to `pre`, `post` and `contract_assert` and introducing four evaluation semantics. C++26 adopted it.
    - After C++26, the current draft allows virtual functions to have contracts and specifies the checking order ([[expr.call#5]]).

## Common misconceptions

!!! pitfall "Postconditions are checked when an exception is thrown too"
    Postconditions are only checked on normal return. To express properties that hold no matter what, use RAII or a `contract_assert` in the function body.

!!! pitfall "Adding const only on the declaration with the postcondition"
    `int f(int x) post(r: r > x)` is ill-formed and must be written `int f(const int x)`, and every declaration needs the `const`, including the one in the header without the postcondition.

!!! pitfall "Side effects in a predicate always happen"
    Under the checking semantics, a predicate may not actually be evaluated; the implementation can obtain its value through an equivalent computation without side effects; under the ignore semantic the predicate isn't evaluated at all ([[basic.contract.eval]]). Don't rely on side effects of predicates.

## Questions

!!! question "Question 1"
    The header `a.h` has `int f(int x) pre(x > LIMIT);`, where `LIMIT` is a macro. One source file does `#define LIMIT 0` before the include, another does `#define LIMIT 1`. Is the program well-formed?

<details markdown="1">
<summary>Answer</summary>

The declarations in both translation units are first declarations, and paragraph 4 requires their contract specifiers to be the same. After macro expansion the predicates are `x > 0` and `x > 1`, which differ under the ODR comparison of item 5.1, so the program is ill-formed, no diagnostic required. It's the same kind of problem as an inline function body expanding different macro values in different translation units and violating the ODR.
</details>

!!! question "Question 2"
    Why does paragraph 7 only require non-reference parameters to be const, while `int& x` can be used freely in a postcondition?

<details markdown="1">
<summary>Answer</summary>

A non-reference parameter is the function's own copy, and the caller cares about the value passed in. If the body modified the copy, the value the postcondition reads would differ from what the caller understands `x` to be; requiring const rules that out. A reference parameter refers to the caller's object, modifying it is part of what the function does, and having the postcondition read its state at return is exactly what is meant.
</details>
