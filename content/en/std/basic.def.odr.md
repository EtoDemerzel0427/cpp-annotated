---
title: The one-definition rule (ODR)
summary: "Everything is defined at most once in a translation unit; an ordinary function or variable that is odr-used is defined exactly once in the whole program; things that may be defined in several places, such as classes, inline functions and templates, must have identical definitions everywhere. This page also defines potentially evaluated, the set of potential results, odr-use and odr-usable."
updated: 2026-10-19
---

!!! tldr
    - Within one translation unit, a class, function or variable is defined at most once; the compiler must report violations.
    - If an ordinary (non-inline, non-template) function or variable is odr-used, the whole program must contain exactly one definition of it. odr-use is roughly a use that needs its address or function body; merely reading a constant value known at compile time doesn't count.
    - Classes, enumerations, inline functions and variables, and templates may be defined once in each translation unit, but the definitions must consist of the same tokens and have the same meaning. Violations require no diagnostic, and the linker silently keeps just one copy.
    - Automatic variables and `*this` can only be odr-used within the same function invocation; crossing a lambda requires a capture, and crossing a local class is not possible.
    - A `static` local variable in an inline function exists once in the whole program, because the ODR treats the multiple definitions as one definition.

## A convention the linker doesn't check

```cpp title="a.cpp"
inline int version() { return 1; }
int from_a() { return version(); }
```

```cpp title="b.cpp" ifndr
inline int version() { return 2; }  // differs from the definition in a.cpp: ODR violation
int from_b() { return version(); }
```

`main` prints `from_a()` and `from_b()`. Clang 23 compiles and links this without any message: at `-O0` it prints `1 1`, after swapping the link order of the two files it prints `2 2`, and at `-O2` it prints `1 2`.

A C++ program is made of many **translation units** (TU: a separately compiled source file together with the headers it includes) compiled separately and then joined by the linker. The linker sees only symbol names, not types or source code. An inline function has a copy in every TU that includes it; the linker keeps just one, and doesn't compare whether the copies are the same.

The **One-Definition Rule** (ODR) is the convention that makes this model work. It has three layers:

1. Within one TU everything is defined at most once (¶2). The compiler sees the whole TU, so it must report violations.
2. An ordinary function or variable that is used has exactly one definition in the whole program (¶12, ¶16.1). Too few or too many is IFNDR (ill-formed, no diagnostic required; see [[intro.compliance]]). It usually shows up as a link error, but the standard guarantees nothing.
3. Things that may be defined in several TUs must have identical definitions everywhere (¶16). Violations are also IFNDR, and are almost never reported, as in the example above.

## Definable items and at most one definition per TU (¶1–¶2)

¶1 The things the ODR governs are called **definable items**, and there are seven kinds: class types (including closure types), enumeration types, functions, variables ([[basic.pre#7]], excluding non-static data members), templated entities (templates, entities defined inside templates, etc., [[temp.pre]]), default arguments for a parameter of a function in a given scope, and default template arguments.

Not on the list: namespaces (which is why they can be reopened), type aliases, using-declarations, macros and labels.

Default arguments are listed separately because a default argument is a piece of code substituted at the call site, which may be written differently in different TUs; the ODR brings it within the scope of what must agree (¶16.11). The qualification "in a given scope" is there because redeclarations of the same function in different block scopes can each give their own default arguments ([[dcl.fct.default]]).

¶2 No TU shall contain more than one definition of any definable item.

```cpp error
struct S { int a; };
struct S { int a; };  // error: defined twice in the same TU, even though identical
inline void f() { }
inline void f() { }   // error: inline doesn't help
```

If the same header is included twice, indirectly, into one TU, the classes in it are defined twice; that is what header guards (include guards or `#pragma once`) are for. ¶2 only concerns definitions: `extern int x; extern int x;` and `typedef int I; typedef int I;` are valid repeated declarations.

## When a definition is needed: odr-use

Merely mentioning a variable in code doesn't necessarily require its definition:

```cpp run ok
extern int e;          // never defined
int main() {
  e;                   // no definition needed
  (void)e;             // no definition needed
  (void)sizeof(e);     // no definition needed
  decltype(e) k = 0;   // no definition needed
  return k;
}                      // links fine
```

The standard calls the kind of use that needs a definition an **odr-use**. Defining it requires two concepts first: potentially evaluated, and the set of potential results.

### Potentially evaluated (¶3)

¶3 An expression or conversion is **potentially evaluated** unless it is an unevaluated operand ([[expr.context]]) or a subexpression thereof. Unevaluated operands appear in `sizeof`, `decltype`, the `noexcept` operator, *requires-expression*s, and the operand of `typeid` for a non-polymorphic class type. In the example above, the `e` in `sizeof(e)` and `decltype(e)` is not potentially evaluated.

"Potentially" means it might be evaluated; the standard does no control-flow analysis. The `g()` in `if (false) g();` is still potentially evaluated. The discarded branch of an `if constexpr` ([[stmt.if]]) is also still potentially evaluated, but ¶12 and ¶13 say odr-uses inside it don't require a definition.

### The set of potential results (¶3)

What the ODR cares about is: when a variable's name appears in an expression, does the variable really need a piece of storage? If only its value is read and the value is known at compile time, the compiler can just substitute the value; if its address is needed, for example by taking the address or binding a reference, there must be a definition.

The difficulty is that names are often wrapped in other operations: `(c ? x : y) + 1` only reads a value, but `&(c ? x : y)` wants an address. The **set of potential results** sees through the operations that don't change the identity of the object and finds the names that end up being used as the object itself. The set of potential results of an expression E is:

| ¶ | Form of E | Set of potential results |
|---|---|---|
| 3.1 | *id-expression* (a name), or *splice-expression* {{c++26}} | {E} |
| 3.2 | array subscript `a[i]` | the set of potential results of `a` |
| 3.3 | access to a non-static data member or direct base `E1.m` | the set of potential results of `E1` |
| 3.4 | access to a static data member `E1.s` | the *id-expression* designating that member |
| 3.5 | pointer to member `E1 .* E2` | the set of potential results of `E1` |
| 3.6 | parentheses `(E1)` | the set of potential results of `E1` |
| 3.7 | conditional expression `c ? E2 : E3` yielding a glvalue | the union of the sets of potential results of `E2` and `E3` |
| 3.8 | comma expression `E1, E2` | the set of potential results of `E2` |
| 3.9 | anything else | empty |

Function calls, taking an address and arithmetic all fall under 3.9. The set of potential results of `f(x)` is empty; `x` is only in the set of potential results of the argument `x` itself, so what matters is how that argument initializes the parameter: passing by value reads the value, passing by reference binds a reference.

Subscripting only sees through arrays: `p[i]` (where `p` is a pointer) is equivalent to `*(p+i)` and accesses another object. A conditional expression is seen through only when its result is a glvalue; if the two sides need conversions and the result is a prvalue, each operand has already had its value read. A comma expression takes only the right operand; the left operand is a discarded-value expression and is judged on its own.

### odr-use of variables (¶5)

¶5 An expression **names** a variable x if it is an *id-expression* or *splice-expression* designating x. A potentially evaluated expression N that appears at a program point P and names x **odr-uses** x unless:

- ¶5.1 x is a reference that is usable in constant expressions at P; or
- ¶5.2 N is an element of the set of potential results of an expression E, where
    - ¶5.2.1 E is a discarded-value expression to which the lvalue-to-rvalue conversion is not applied; or
    - ¶5.2.2 x is a non-volatile object usable in constant expressions at P with no mutable subobjects, and
        - ¶5.2.2.1 E is a member access to a non-static data member of reference type whose object expression has non-volatile-qualified type; or
        - ¶5.2.2.2 the lvalue-to-rvalue conversion is applied to E, and E has non-volatile-qualified non-class type.

The **lvalue-to-rvalue conversion** here ([[conv.lval]]) is reading the value out of an object (for background see [[topics/value-categories]]). A variable **usable in constant expressions** ([[expr.const.init]]) is roughly a `constexpr` variable, or a `const` variable of integral or enumeration type initialized with a constant, or a reference, whose initialization is visible at P.

In short, **a variable is odr-used when a potentially evaluated expression names it, unless only its value is actually needed and that value is known at compile time, or it isn't used at all**. The reasons for each exception:

- ¶5.2.2.2 is the most common case. `constexpr int N = 3;` is only read in `int a[N];`, `return N + 1;`, and pass-by-value `f(N)`; the compiler substitutes 3 directly. Non-class type is required because reading a class object calls the copy constructor, which needs the object's address; no mutable subobjects is required because mutable members can change at run time.
- ¶5.2.2.1: suppose `constexpr B b = {x};`, where `B` has a reference member `int& r`. Which object `b.r` is bound to is known at compile time, so `b`'s own storage isn't needed.
- ¶5.1: when the object a reference is bound to is known at compile time, using the reference doesn't need the reference's own storage.
- ¶5.2.1: `e;` and `(void)e;` neither read the value nor take the address, which is why the opening example links. But for a volatile variable, such an expression does apply the lvalue-to-rvalue conversion ([[expr.context#2]]), and so is an odr-use:

```cpp
extern volatile int ev;  // never defined
int main() { ev; }       // reads a volatile variable: odr-use, link fails
```

Here is the classic static data member example. A `static const` member is only a declaration in the class ([[basic.def#2.3]]), so the uses decide whether the program links:

```cpp
struct S { static const int x = 0; };  // only a declaration in the class
const int& f(const int& r) { return r; }
int g(int v) { return v; }
int main(int argc, char**) {
  bool b = argc > 1;
  int n = b ? (1, S::x) : S::x;  // only reads the value: no odr-use
  int a = g(S::x);               // pass by value, reads the value: no odr-use
  const int& r = f(S::x);        // binds a reference: odr-use
  return n + a + r;              // with Clang 23 at -O0, link fails: "S::x" undefined
}
```

The standard's Example 1 has the same structure and adds a C++26 splice: in `int o = [:^^S::x:];` the splice expression itself is the potential result, and reading its value doesn't odr-use `S::x`.

The "usable in constant expressions" condition decides which variables a lambda can read without capturing:

```cpp error
void k() {
  constexpr int n = 3;
  const int m = 4;       // const integral, constant-initialized
  const double d = 1.5;  // not integral, not usable in constant expressions
  auto l1 = [] { return n + m; };               // OK: only reads values
  auto l2 = [] { int a[m]; return sizeof a; };  // OK
  auto l3 = [] { return &n; };  // error: taking the address odr-uses n
  auto l4 = [] { return d; };   // error: reading d is also an odr-use
}
```

!!! note "The standard's Example 2"
    ¶5's Example 2 uses `constexpr` objects with automatic storage duration to illustrate ¶5.2.2.1, such as `constexpr B b1 = {x};`, where `x` is a local variable in the same function. This depends on C++26's [[P2686R5]]: a `constexpr` reference or pointer may refer to an automatic variable in the same function (constexpr-referenceable in [[expr.const.init]]). Clang 23 doesn't implement this yet and reports "must be initialized by a constant expression" for the initializations of `r`, `b1` and `b2`.

    The point of the example: `g(cond ? b1.r : b2.r)` obtains `x` or `y` only through reference members and doesn't odr-use `b1` or `b2`. Inside the lambda, however, the `x` that `b1.r` refers to is no longer constexpr-referenceable, so `b1` isn't usable in constant expressions there; `return b1.r;` therefore odr-uses `b1`, which isn't captured, so it's an error (see ¶10).

### Structured bindings and `*this` (¶6–¶7)

¶6 A structured binding is odr-used whenever a potentially evaluated expression names it; there is no constant exception like the one for variables. So using a structured binding in a lambda requires capturing it (capturing structured bindings is allowed since C++20).

¶7 `*this` is odr-used when `this` appears as a potentially evaluated expression. An `m` written in a member function is implicitly transformed into `(*this).m` ([[expr.prim.id.general]]), which counts too. Combined with ¶10, this is why accessing members in a lambda requires capturing `this`:

```cpp error
struct W {
  int m = 0;
  auto get() { return [] { return m; }; }      // error: this not captured
  auto ok() { return [this] { return m; }; }   // OK
};
```

### odr-use of functions (¶4, ¶8–¶9)

¶8 A function is odr-used if it is named by a potentially evaluated expression or conversion. ¶4 specifies the ways a function is **named**.

¶4.1 The main way is being selected by overload resolution: taking a function's address, calling a function, using an overloaded operator, a user-defined conversion, the allocation function selected by a *new-expression*, a constructor, all fall into this category (Note 2). Pure virtual functions are the exception: they are named only when an explicitly qualified name is used and no pointer to member is formed.

The pure-virtual exception has practical meaning. For a virtual call `p->f()`, overload resolution selects the pure virtual `B::f`, but the final overrider is what gets called at run time, so `B::f` doesn't need a definition. Writing `B::f()` makes a non-virtual call, which really does call `B::f`:

```cpp
struct B { virtual void f() = 0; };          // pure virtual, no definition
struct D : B { void f() override { B::f(); } };  // qualified call: odr-uses B::f
int main() { D d; d.f(); }                   // with Clang 23, link fails: "B::f()" undefined
```

`&B::f` also uses a qualified name, but it forms a pointer to member, and a call through a pointer to member is still a virtual call, so it is excluded.

Note 2 also says that a constructor selected to copy or move is named even if the call is elided. So non-mandatory elision such as NRVO can't sidestep the requirement on the copy constructor. Mandatory elision since C++17, where a prvalue initializes directly, doesn't select a copy constructor at all:

```cpp run ok
struct M { M() {} M(const M&) = delete; };
M make() { return M{}; }      // OK: the prvalue initializes the return object directly

struct N { N() {} N(const N&) {} };
N make2() { N n; return n; }  // N(const N&) is selected, and odr-used even if elided
                              // if it were deleted, this would be an error
int main() { }
```

¶4.2–¶4.3 A class's `operator delete` is named in two cases: it is the single matching deallocation function for the allocation function selected by a *new-expression* (used to reclaim memory if the constructor throws, [[expr.new]]); or it is the usual deallocation function selected by a *delete-expression* ([[expr.delete]]).

¶8 also has three rules unrelated to calls:

- A virtual function that is not pure is always odr-used, whether or not it is called. The vtable has to be filled with the address of every virtual function, and constructors reference the vtable, so declaring a virtual function without defining it violates the ODR. In practice this shows up as `undefined reference to vtable for X`.
- A class's non-placement allocation and deallocation functions are odr-used by the definition of a constructor of that class; a non-placement deallocation function is odr-used by the definition of the destructor, or by being selected by lookup at the point of definition of a virtual destructor ([[class.dtor]]). Footnote 13 says an implementation need not actually call them from the constructor or destructor, but is allowed to. The Itanium ABI's deleting destructor calls `operator delete` from the virtual destructor, so that `delete p` can find the right deallocation function through the vtable.

¶9 An implicitly defined copy or move assignment function assigns member by member, so it odr-uses the assignment operators of member classes ([[class.copy.assign]]); constructors are odr-used as specified in [[dcl.init]]; a destructor is odr-used when it is **potentially invoked**, for example when an automatic variable goes out of scope or a temporary is destroyed ([[class.dtor]]).

```cpp
struct S { ~S(); };           // declared but not defined
void f(bool c) { if (c) { S s; } }
int main() { f(false); }      // ~S is potentially invoked: link fails, though it never runs

struct B { virtual void v(); virtual void p() = 0; };
struct D : B { void p() override { } };
int g() { D d; return 0; }    // B::v is not pure, so it's always odr-used: link fails
```

## A definition must exist (¶12–¶14)

¶12 Every function or variable that is odr-used in a program (outside a discarded statement) must have at least one definition; no diagnostic is required. The definition can be in the program, come from the standard library or another library, or be an implicitly defined special member function.

Why is no diagnostic required? The definition could be in any TU or library, and the compiler can't see the whole picture. The linker can usually find a missing symbol, but the standard doesn't write linker diagnostics into the language rules, and in some cases the linker can't find the problem either:

<div class="compare" markdown="1">

```cpp run ok
void never_defined();
template<class T> void h() {
  if constexpr (sizeof(T) > 100)
    never_defined();  // discarded
}
int main() { h<int>(); }
```

```cpp run ifndr
void never_defined();
int main() {
  if (false)
    never_defined();  // odr-use
}
```

</div>

On the left, the call in a discarded statement needs no definition, and the program is well-formed. On the right, by the standard this is an odr-use with no definition, which is IFNDR; Clang 23 removes the `if (false)` branch even at `-O0`, and the program links. This is typical of IFNDR: it looks fine, but nothing is guaranteed.

Example 5 in ¶12 is a case the compiler can see:

```cpp error
auto f() {
  struct A {};
  return A{};
}
decltype(f()) g();  // g returns the local class A
auto x = g();       // odr-uses g
```

`g` is odr-used, this TU doesn't define it, and no other TU can define it either, because the local class `A` can't be written anywhere else. Clang reports an error directly: "function 'g' is used but not defined in this translation unit, and cannot be defined in any other translation unit because its type does not have linkage".

¶13 Inline functions and variables have a stronger requirement. A **definition domain** is the part of a TU excluding its private module fragment (the part after `module :private;`), or that private module fragment itself. If an inline function or variable is odr-used in a definition domain, its definition must be reachable from the end of that definition domain.

This is the modern statement of "an inline function must be defined in every TU that uses it", and it is why header-only libraries put the implementations of inline functions in headers: to inline-expand at the call site, the compiler has to see the function body. The requirement is "reachable from the end", so a call may appear before the definition.

A private module fragment forms its own definition domain, and importers can't see its contents. If an inline function before the private fragment calls an inline function defined only inside the private fragment, this rule is violated.

¶14 A definition of a class must be reachable at every point where the class type is required to be complete. Example 6 shows that a class used only through pointers needs no definition:

```cpp run ok
struct X;       // declares X
struct X* x1;   // forms a pointer; X need not be complete
X* x2;
int main() { }
```

Note 3 lists the contexts that require a class `T` to be complete: defining an object or non-static data member of type `T`, `new T`, reading a value of type `T`, converting to `T`, converting an expression to `T*` or `T&` (except from a null pointer constant or `void*`), member access on an expression of type `T`, `sizeof`, `alignof` or `typeid` applied to `T`, defining or calling a function with a parameter or return type `T`, defining a class with `T` as a base, assigning to an lvalue of type `T`, and a `catch` of type `T`, `T&` or `T*`.

## Where local entities can be used: odr-usable (¶10–¶11)

```cpp error
void f(int n) {
  [] { n = 1; };              // error: the lambda doesn't capture n
  struct A {
    void f() { n = 2; }       // error: crosses the parameter scope of A::f
  };
  void g(int = n);            // error: crosses the parameter scope of g
  [=](int k = n) {};          // error: the default argument isn't in the lambda body
  [&] { [n]{ return n; }; };  // OK
}
```

This is the standard's Example 3. A local entity ([[basic.pre#9]]: automatic variables, the corresponding structured bindings, result bindings, `*this`) belongs to one particular function invocation. Block scopes, contract assertions and a lambda's parameter list are still within the same invocation and can be crossed directly; the member functions of a local class and the parameter scope of a nested function declaration belong to another function and can't be crossed. A lambda is like a door that opens only when there is a capture, and you're through the door only once inside the lambda's body, so a default argument of a lambda parameter is still outside.

¶10 The precise rule: a local entity is **odr-usable** in a scope if and only if

- ¶10.1 if it is `*this`, there is an enclosing class scope or non-lambda function parameter scope, and if the innermost such scope is a function parameter scope, it belongs to a non-static member function;
- ¶10.2 every intervening scope ([[basic.scope.scope#1]]) between the point where the entity is introduced and the scope is one of: a block scope; a contract-assertion scope ([[basic.scope.contract]]) {{c++26}}; a function parameter scope of a *lambda-expression* or *requires-expression*; or the lambda scope of a lambda that captures the entity (explicitly or with a capture-default), where that lambda's body is also among the intervening scopes.

If a local entity is odr-used in a scope in which it is not odr-usable, the program is ill-formed.

These errors occur only on odr-use. Merely reading the value of a variable usable in constant expressions is not an odr-use, so odr-usability doesn't matter: `constexpr int n = 3; [] { return n; }` is valid.

Example 4 in ¶11 pushes this into templates. Whether something is an odr-use is known only at instantiation, so different specializations of the same generic lambda can be valid and invalid:

```cpp
void g() {
  constexpr int x = 1;
  auto lambda = [] <typename T, int = ((T)x, 0)> {};  // OK
  lambda.operator()<int, 1>();      // OK: the default template argument isn't used at all
  lambda.operator()<int>();         // OK: (int)x only reads the value
  lambda.operator()<const int&>();  // error: binds a reference, odr-uses x
}

void h() {
  constexpr int x = 1;
  auto lambda = [] <typename T> { (T)x; };  // OK
  lambda.operator()<int>();         // OK: reads the value
  lambda.operator()<void>();        // OK: discarded-value expression (¶5.2.1)
  lambda.operator()<const int&>();  // error: odr-uses x
}
```

!!! impl "Clang and Example 4"
    Clang 23 differs from the standard: in `g()`, it reports "variable 'x' cannot be implicitly captured in a lambda with no capture-default specified" on the lambda definition itself (the default template argument `((T)x, 0)`); in `h()`, it accepts `<int>` but reports the same error for `<void>`. By the standard, only the two `<const int&>` lines are errors. Clang handles the non-template case (`[] { return x; }`) correctly.

## Definitions in multiple TUs (¶16)

¶16 is the core of the ODR. It concerns a definable item D that is defined in more than one TU:

- ¶16.1 If D is a non-inline, non-templated function or variable, the program is ill-formed. It has at most one definition in the whole program; together with "at least one" from ¶12, that makes exactly one when it is odr-used.
- ¶16.2 If the definitions in the various TUs don't meet the requirements below, the program is ill-formed.

A diagnostic is required only if D is attached to a named module and a prior definition is reachable at the point where a later one occurs. For traditional header-based code, violating these rules is always {{ifndr}}.

Every definable item not covered by ¶16.1 can be defined once in each TU: classes, enumerations, inline functions and variables, templated entities, default arguments. That is exactly the complete list of things that can go in a header.

| Definable item | Per TU | Whole program |
|---|---|---|
| Non-inline, non-templated functions and variables | ≤ 1 | Exactly 1 if odr-used, otherwise ≤ 1 |
| Inline functions and variables | ≤ 1, reachable from the end of the definition domain that odr-uses it | One per TU allowed, all identical |
| Classes, enumerations | ≤ 1, reachable where a complete type is required | One per TU allowed, all identical |
| Templated entities | ≤ 1 | One per TU allowed, all identical |
| Default arguments, default template arguments | ≤ 1 (in a given scope) | Must be identical (¶16.11) |

The requirements every definition must meet follow. If D is an unnamed enumeration, they apply only to definitions that are all reachable at the same program point.

### Same tokens, same meaning (¶16.3–¶16.5)

¶16.3 Such definitions can't be attached to a named module ([[module.unit]]). An entity in a named module has only one definition, which importers see through reachability; repeating it elsewhere is neither needed nor allowed. Only entities attached to the global module, i.e. traditional header-based code, are subject to the "multiple definitions, must agree" rule.

¶16.4 Each definition must consist of the same sequence of tokens, where the definition of a closure type is considered to consist of the tokens of the corresponding lambda expression. The tokens are those after preprocessing ([[lex.phases]]), so differences in whitespace and comments don't matter, but different macro expansions violate this rule. Compiling the same header with different `-D` options in two TUs can cause problems.

¶16.5 Identical tokens aren't enough: after name lookup, overload resolution and partial specialization matching, corresponding names in each definition must refer to the same entity. There are two exceptions:

- ¶16.5.1 A name may refer to a non-volatile `const` object with internal or no linkage, as long as it has the same (literal) type in all definitions, is initialized with a constant expression, has the same value, and is not odr-used in any definition;
- ¶16.5.2 A name may refer to a reference with internal or no linkage initialized with a constant expression, as long as it refers to the same object or function in all definitions.

The most common header pattern is valid only thanks to ¶16.5.1:

```cpp title="config.h"
const int kBufSize = 4096;     // internal linkage: an independent object in each TU
inline int buffer_bytes() {
  return kBufSize * 2;         // refers to different objects in each TU, but only reads: OK
}
inline const int* buffer_addr() {
  return &kBufSize;            // taking the address is an odr-use: ODR violation (IFNDR)
}
```

`buffer_addr` ought to return a different address in each TU, but the linker keeps only one definition, and which one depends on link order. Changing it to `inline constexpr int kBufSize = 4096;` fixes this: an inline variable has external linkage, and there is one object in the whole program.

!!! tip "Why `inline constexpr` is recommended for header constants"
    A `constexpr` variable at namespace scope is implicitly `const` and so has internal linkage ([[basic.link#3]]); every TU that includes the header gets a copy. Adding `inline` gives it external linkage and one object for the whole program, so taking its address and odr-using it in inline functions are both safe. The C++17 standard library defines variable templates such as `std::is_same_v` as `inline constexpr` for the same reason.

### What the compiler chooses implicitly must agree too (¶16.6–¶16.12)

Even with the same source and names that refer to the same entities, the choices the compiler makes behind the scenes can still differ. The following rules close those gaps one by one.

¶16.6 Corresponding lambda expressions must have the same closure type (except those in D's default arguments and default template arguments; see ¶18). Normally every lambda expression has a unique closure type, but multiple definitions of an inline function are treated as one definition, so the lambdas inside must be the same type. Implementations give them the same mangled name for this purpose; the Itanium ABI encodes the enclosing entity plus a sequence number, such as `f()::{lambda()#1}`.

¶16.7 Corresponding entities must have the same language linkage (`extern "C"` or `extern "C++"`, [[dcl.link]]).

¶16.8 If a `const` object with static or thread storage duration is constant-initialized in one definition, it must be constant-initialized in all definitions. A constant-initialized object is written into the program image at compile time; a dynamically initialized one is filled in by initialization code at run time. Mixing the two breaks both the timing and the value of initialization.

¶16.9 Corresponding manifestly constant-evaluated expressions that are not value-dependent (array bounds, `static_assert`, `if constexpr` conditions, template arguments, etc., [[expr.const]]) must have the same value. This targets cases where the tokens and names are the same but the constant value differs, for example values that depend on implementation-defined properties.

¶16.10 Overloaded operators referred to, and implicit calls to conversion functions, constructors, `operator new` and `operator delete`, must be the same function. These calls have no name in the source, so ¶16.5 can't cover them. A typical violation is an overload visible in only some TUs:

```cpp title="a.cpp"
struct P { int v; };
bool operator==(P, long);
inline bool is_zero(P p) { return p == 0; }  // selects operator==(P, long)
```

```cpp title="b.cpp" ifndr
struct P { int v; };
bool operator==(P, long);
bool operator==(P, int);                     // only b.cpp has this better overload
inline bool is_zero(P p) { return p == 0; }  // selects operator==(P, int)
```

¶16.11 Default arguments used by a function call and default template arguments used by a template-id are treated as if their tokens appeared in the definition of D, and must recursively meet all the requirements above. Default arguments are substituted at the call site: given `inline void f() { g(); }` with `g` declared as `void g(int = N);`, the definition of `f` effectively contains `g(N)`.

¶16.12 {{c++26}} Corresponding reflection expressions `^^x` must produce equivalent values ([[expr.eq]]). If `x` refers to different entities in two TUs, the reflection values differ, and code generated from reflection differs too.

### Implicit definitions and templates (¶17)

¶17.1 If D is a class with an implicitly declared constructor, it is as if the constructor were implicitly defined in every TU where it is odr-used, and the implicit definitions in each TU must call the same constructors for D's subobjects. Example 7:

```cpp title="tu1.cpp"
struct X {
  X(int, int);
  X(int, int, int);
};
X::X(int, int = 0) { }  // in tu1, X(int, int) has a default argument
class D {
  X x = 0;              // selects X(int, int)
};
D d1;
```

```cpp title="tu2.cpp" ifndr
struct X {
  X(int, int);
  X(int, int, int);
};
X::X(int, int = 0, int = 0) { }  // in tu2, X(int, int, int) has default arguments
class D {
  X x = 0;              // selects X(int, int, int): ODR violation
};
D d2;
```

The two definitions of `D` have exactly the same tokens, and the name `X` refers to the same class, but the out-of-class definitions add different default arguments, so overload resolution for `X x = 0` gives different results. The difference can't be seen from `D`'s own tokens, so it needs a separate rule.

¶17.2 The same goes for a defaulted three-way comparison operator (`operator<=>` declared `= default`, [[class.spaceship]]): the implicit definitions in each TU must call the same comparison operator for each subobject.

¶17.3 If D is a template, the requirements apply both to names from enclosing scopes in the template definition and to dependent names at the point of instantiation ([[temp.dep]], [[temp.point]]). If different TUs see different things at the point of instantiation (functions found by ADL, explicit specializations), the ODR is violated. This is also why an explicit specialization must be declared before its first use ([[temp.expl.spec]]).

### Treated as a single entity (¶18–¶19)

¶18 The requirements above also apply to corresponding entities defined within each definition of D, including closure types of lambdas, but excluding entities defined within D's default arguments or within the default arguments of entities not defined within D. For these entities and D itself, **the behavior is as if there were a single entity with a single definition**.

Consequences:

- A `static` local variable in an inline function exists once in the whole program. If `inline int& counter() { static int c = 0; return c; }` is included by 10 TUs, all of them share the same `c`, which is why a Meyers singleton can be written in a header.
- Lambda closure types and local classes in an inline function are the same type in every TU; taking the address of an inline function gives the same address in every TU.
- String literals are not covered. A literal is not an entity, and whether the array object it evaluates to is the same object across evaluations is unspecified (the note in [[lex.string#9]], [[CWG1823]]). So you can't assume that the `"hello"` pointer returned by an inline function in different TUs compares equal.

Note 4 adds that these entities are still declared in several TUs, and [[basic.link]] still applies to those declarations. A lambda appearing in D's type may give different declarations different types, and a lambda appearing in D's default arguments may still be a different type in different TUs.

Example 8 in ¶19 shows the subtleties of the exclusion clause:

```cpp
inline void f(bool cond, void (*p)()) {
  if (cond) f(false, []{});
}
inline void g(bool cond, void (*p)() = []{}) {
  if (cond) g(false);
}
struct X {
  void h(bool cond, void (*p)() = []{}) {
    if (cond) h(false);
  }
};
```

- `f`: the lambda is in the function body, so it is the same closure type in every TU; no problem.
- `g`: the lambda is in `g`'s own default argument, which is excluded from the same-closure-type requirement, so it is a different type in each TU. But `g`'s body uses that default argument through `g(false)`, which by ¶16.11 counts as part of `g`'s definition, so the definitions of `g` use different entities: {{ifndr}}.
- `X::h`: with D = `X`, `h` is an entity defined within `X`, and the lambda in its default argument is also defined within `X`, so it is not excluded; it is the same closure type in every TU, and `X` can appear in multiple TUs.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

¶15 {{c++26}} If a definable item D is defined in a TU by an injected declaration X (a definition generated during constant evaluation by C++26 static reflection, such as `std::meta::define_aggregate`, [[expr.const.reflect]]), and another TU also contains a definition of D, that definition must also be an injected declaration with the same characteristic sequence as X (the reflection values used to generate the definition). An injected definition has no source tokens, so ¶16.4 can't apply, and the characteristic sequences are compared instead. A diagnostic is required only if D is attached to a named module and a prior definition is reachable.

¶20 If, at some point in the program, there is more than one reachable unnamed enumeration definition in the same scope that have the same first enumerator name and no typedef name for linkage purposes, they must be the same type; no diagnostic is required. Unnamed enumerations are identified as the same entity for linkage purposes by their first enumerator ([[dcl.enum]]); with modules, one TU may see several such definitions at once (for example from different header units), and ¶20 requires treating them as the same type.

</details>

## The implementation's view

!!! impl "How the linker merges multiple definitions"
    Inline functions, inline variables, template instantiations, vtables, typeinfo, and static local variables in inline functions together with their guard variables are all marked as mergeable in object files:

    - ELF (Linux): placed in COMDAT groups; the linker keeps one copy of each group with the same name, and the symbols are usually `W` (weak).
    - Mach-O (macOS): marked as weak definitions. In our tests, `nm -m` shows `weak external __Z7versionv` for `inline int version()`.
    - PE/COFF (Windows): COMDAT sections, usually with a "pick any" selection.

    The Itanium C++ ABI calls this way of emitting vague linkage. The linker merges by symbol name only and never compares contents; it assumes the program follows the ODR. That's why violations of ¶16 are almost never reported. In the opening `version()` example, at `-O0` both calls go through the symbol and the linker keeps the copy it sees first; at `-O2` the calls are inlined and each uses its own definition.

!!! impl "Different definitions of a class with the same name: memory corruption"
    Two .cpp files each define a class with the same name, each thinking it is private:

    ```cpp title="a.cpp"
    struct Node { int v; Node() : v(1) {} };   // 4 bytes
    int from_a() { Node n; return n.v; }
    ```
    ```cpp title="b.cpp" ifndr
    struct Node { double d[4]; Node() : d{1, 2, 3, 4} {} };  // 32 bytes
    double from_b() { Node n; return n.d[3]; }
    ```

    A constructor defined in the class is implicitly inline, the two `Node::Node()` have the same mangled name, and the linker keeps only one. In our tests: with link order b, a, the b version of the constructor writes 32 bytes into the 4-byte `n` in `from_a`, ASan reports `stack-buffer-overflow ... WRITE of size 32`, and without ASan it segfaults; with order a, b, `from_b` reads garbage. The fix is to put types used only in one .cpp file into an unnamed namespace so they have internal linkage ([[basic.link#4]]); then each TU's `Node` is a different entity.

!!! impl "vtables and the key function"
    The Itanium ABI emits a vtable only in the TU that defines the key function (the first non-inline, non-pure virtual function); a class without a key function has its vtable emitted with vague linkage in every TU that needs it. If you forget to define the key function, the vtable is never generated anywhere, and the linker reports `undefined reference to vtable for X`. This matches ¶8's rule that a non-pure virtual function is always odr-used.

!!! impl "Tools for detecting ODR violations"
    - GCC's `-Wodr` together with LTO (`-flto`) can compare definitions of same-named types across TUs and warn about layout mismatches; the `Node` case above is exactly what it is designed to catch.
    - AddressSanitizer's `detect_odr_violation` option detects instrumented global variables defined more than once across modules (such as the main program and a shared library); it doesn't check differences in types or inline functions.
    - For entities in named modules, ¶16 requires a diagnostic when a prior definition is reachable; Clang compares hashes of definitions when merging definitions from modules.

    Each of these tools catches only part of the problem. The reliable prevention is: define each entity in only one header, put TU-private things in an unnamed namespace, and use consistent compiler options and macros across the whole program. MSVC's standard library uses `#pragma detect_mismatch` to record configuration such as `_ITERATOR_DEBUG_LEVEL` in object files, and reports LNK2038 at link time on a mismatch; this is an engineering remedy for inconsistent preprocessor configuration.

| Source of the ODR violation | Rule violated | Example |
|---|---|---|
| Different `-D` options | ¶16.4 | Some TUs define a debug macro, and a class in a header gains an extra field |
| TU-private types with the same name | ¶16.4 | Two .cpp files each define `struct Node` |
| Non-inline definitions in headers | ¶16.1 | `int counter = 0;` or the body of an ordinary function in a header |
| Taking the address of a header constant | ¶16.5.1 | An inline function returns `&kConst`, or passes it to `std::max` |
| Different things seen at the point of instantiation | ¶17.3 | An explicit specialization declared in only some TUs |
| Inconsistent default arguments | ¶16.11, ¶17.1 | Out-of-class definitions in different TUs add different default arguments |
| Headers not matching the library binary | ¶16.4 | Linking a v1 library using v2 headers |

## History

!!! history
    - C++98's ODR already had today's skeleton: one definition per TU; exactly one definition of a non-inline function or object that is used; multiple definitions of classes, inline functions and templates with the same tokens and the same meaning. "Use" was coarse then: a name appearing in a potentially evaluated expression was a use. C++03 added one exception through the defect resolution [[CWG48]]: an object that satisfies the requirements for appearing in a constant expression and whose value is read immediately.
    - C++11 renamed the term to odr-use, distinguishing it from use in the everyday sense; the exception clauses were rewritten along with `constexpr`.
    - The set of potential results comes from the defect resolution [[CWG712]], which generalized the "value read immediately" case to see through `?:`, comma, member access and so on, and added the discarded-value expression exception.
    - C++17's inline variables ([[P0386R2]]) let variables, too, be defined once in each TU.
    - C++20 introduced modules: reachability replaced "appears in this TU", entities in named modules can have only one definition, and visible violations require a diagnostic.
    - C++23's [[P1787R6]] introduced the new scope model, and odr-usable was restated in terms of intervening scopes.
    - C++26's static reflection ([[P2996R13]]) lets splice expressions name variables and functions too, and brought ¶15 and ¶16.12; contract-assertion scopes can be crossed directly (¶10.2); [[P2686R5]] allows `constexpr` references to refer to automatic variables, which affects how ¶5's Example 2 is written.

## Common misconceptions

!!! pitfall "IFNDR means a link error"
    No. Extra definitions may be silently merged by the linker (inline, weak symbols); missing definitions may go unreported because optimization removed the call; inconsistent definitions are almost never reported. An IFNDR program has no behavioral guarantees at all, and a successful link doesn't mean there is no problem.

!!! pitfall "A call inside `if (false)` isn't a use"
    It is. odr-use is decided syntactically, with no control-flow analysis. Only uses in unevaluated operands don't count, and the discarded branch of an `if constexpr` doesn't require a definition. Destructors too: `if (c) { S s; }` odr-uses `~S`.

!!! pitfall "Since C++17, `static const int` members no longer need an out-of-class definition"
    Only `static constexpr` and explicitly `static inline` data members are inline. A `static const int N = 0;` that is odr-used (passed to `std::max`, `std::vector::push_back`, etc., whose parameters are `const int&`) still needs an out-of-class definition. And the behavior varies with optimization level: at `-O2` the call is inlined and the constant folded, so it may happen to link.

!!! pitfall "Using a namespace-scope constant in an inline function violates the ODR"
    Usually not: ¶16.5.1 specifically exempts internal-linkage constants whose value is only read. The exemption is lost once you take the address or bind a reference.

## Questions

!!! question "Question 1"
    Does each `S::x` or `s.x` below odr-use `S::x`?

    ```cpp
    struct S { static const int x = 1; int m; };
    void take(int);
    void take_ref(const int&);
    void t(bool c, S s) {
      take(c ? S::x : 2);          // (a)
      take_ref(c ? S::x : 2);      // (b)
      take(s.x);                   // (c)
      int arr[S::x];               // (d)
      take_ref(+S::x);             // (e)
    }
    ```

<details markdown="1">
<summary>Answer</summary>

None of them is an odr-use.

- (a) `S::x` is a `const int` lvalue and `2` is an `int` prvalue, so the conditional expression yields a prvalue and ¶3.7 doesn't apply. `S::x` as the second operand has its own value read; E is `S::x` itself, which is usable in constant expressions, so ¶5.2.2.2 applies.
- (b) Same as (a). The conditional expression produces a value first, and then a temporary is bound to `const int&`.
- (c) `s.x` accesses a static data member, so by ¶3.4 the potential result is the name designating that member; passing by value reads the value, so ¶5.2.2.2 applies.
- (d) An array bound only reads the value.
- (e) Unary `+` reads the operand's value and yields a prvalue. `std::max(+S::x, y)` is a common way to avoid odr-use.
</details>

!!! question "Question 2"
    The header `h.h` contains `const int N = 10; inline int f() { static int calls = 0; return ++calls + N; }` and is included by `a.cpp` and `b.cpp`. How many `N` objects are there? How many `calls` objects? Does this conform to the ODR?

<details markdown="1">
<summary>Answer</summary>

There are two `N`s (unless optimized away): a non-volatile `const` variable at namespace scope has internal linkage ([[basic.link#3]]), so there is one per TU.

There is only one `calls`: by ¶18, the behavior is as if there were a single `f` with a single definition, so the static local variable in it exists once.

It conforms to the ODR. The two definitions of `f` have the same tokens; the name `N` refers to different objects in the two TUs, but that satisfies ¶16.5.1: literal type `const int`, constant-initialized, only its value read so not odr-used, and the value is 10 in both.
</details>

!!! question "Question 3"
    Why does ¶16.1 forbid multiple identical definitions of a non-inline function, while an inline function is allowed them?

<details markdown="1">
<summary>Answer</summary>

A non-inline function is compiled to a strong symbol, and the linker reports a duplicate definition when it sees two strong symbols with the same name; this catches the mistake of accidentally writing a function body in a header. `inline` explicitly says the function will appear in multiple TUs, and the compiler emits it as a mergeable weak symbol or COMDAT. If non-inline functions could be defined in several places, every function would have to be emitted that way, and the linker would lose the ability to check for duplicate definitions. Writing `inline` amounts to the programmer promising that all definitions agree.
</details>

## Summary

| Concept | Key points |
|---|---|
| [[g:definable-item|Definable item]] | Classes, enumerations, functions, variables, templated entities, default arguments, default template arguments |
| At most one definition per TU | ¶2; diagnostic required |
| [[g:potentially-evaluated|Potentially evaluated]] | Not in `sizeof`, `decltype`, `noexcept`, non-polymorphic `typeid`, or a requires-expression; still counts inside `if (false)` |
| [[g:potential-results|Set of potential results]] | Sees through parentheses, array subscripts, non-static member access, `.*`, glvalue `?:`, the right operand of a comma |
| [[g:odr-use]] of a variable | Named in a potentially evaluated way, unless only a compile-time-known value is read, or it isn't used at all |
| odr-use of a function | Selected by overload resolution (for pure virtual functions only via a qualified-name call); always for non-pure virtual functions; destructors when potentially invoked |
| [[g:odr-usable]] | Local entities need a capture to cross a lambda, and can't be used across a local class or a nested function's parameter scope |
| Exactly one definition | Non-inline, non-templated functions and variables that are odr-used (IFNDR) |
| One per TU, identical everywhere | Classes, enumerations, inline functions and variables, templated entities: tokens, names, overloads, closure types, language linkage etc. must all agree |
| Implementation | COMDAT and weak symbols; the linker doesn't compare contents; `-Wodr` with LTO and ASan catch only part |
