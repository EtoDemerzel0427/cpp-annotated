---
title: "Overloading: preamble"
summary: What overloading and overload resolution are; when two declarations of functions with the same name can coexist, and when they are redeclarations of the same function.
updated: 2026-10-19
---

!!! tldr
    - Two or more functions or function templates with the same name in the same scope are called overloads; a function with the same name in a derived class hides the base class's function instead of overloading it.
    - Whether two declarations of functions with the same name can coexist depends on whether they correspond: two declarations with the same (adjusted) parameter-type-list, trailing constraints and object parameters correspond, and declare the same function.
    - Corresponding declarations must have exactly the same type, so two declarations that differ only in the return type or only in `noexcept` are an error; declarations that differ only in top-level `const` or default arguments are redeclarations of the same function.
    - The return type of a function template takes part in the comparison, so two templates that differ only in the return type can coexist.
    - Member functions with the same name and parameters can't have one with a ref-qualifier (`&`/`&&`) and one without, nor one static and one non-static.

## Overloading and hiding (¶1)

```cpp run ok
struct B {
  int f(int) { return 1; }
};
struct D : B {
  int f(double) { return 2; }   // hides B::f
};
struct E : B {
  using B::f;                   // brings B::f into the scope of E
  int f(double) { return 2; }
};

int main() {
  D d;
  E e;
  int a = d.f(1);   // 2: lookup stops when it finds f in D; B::f(int) isn't a candidate
  int b = e.f(1);   // 1: both B::f(int) and E::f(double) are candidates; the former is an exact match
  return a * 10 + b == 21 ? 0 : 1;
}
```

¶1 The standard says this in a note: when two or more entities with the same name in the same scope are all functions or function templates, they are commonly said to **overload**.

Both conditions must hold. `D::f` and `B::f` aren't in the same scope, so they don't overload: class member lookup ([[class.member.lookup]]) stops at `D` once it finds `f` there and doesn't look into the base class, so `B::f(int)` never makes it into the candidate set. To make the base class version compete, it has to be brought into the derived class with a *using-declaration* ([[namespace.udecl]]), as in `E`.

Also, a variable and a function with the same name in the same scope don't overload; they conflict, and the program is ill-formed ([[basic.scope.scope#6]]).

## Overload resolution (¶2)

¶2 When a function is named in a call, which declaration is being called and whether the call is well-formed are determined by comparing the types of the arguments with the types of the parameters of the declarations in the overload set. This selection process is called **[[g:overload-resolution|overload resolution]]** and is specified in [[over.match]].

Note 2 says the **overload set** is formed by an *id-expression* naming a function or function template, and since {{c++26}} also by a *splice-expression* (`[:r:]`) of a reflection.

What is determined is which declaration, not just which function. Default arguments are attached to declarations, and the same function can have different default arguments in different scopes, so it matters which declaration is used ([[over.match.viable#2]]).

## Which declarations with the same name can't coexist

<div class="compare" markdown="1">

```cpp error
int    f(int);
double f(int);  // error: differs only in the return type
```

```cpp ok
template<class T> int    g(T);
template<class T> double g(T);  // OK
```

</div>

The two declarations on the left conflict, yet the two templates on the right can coexist. The rules are spread over three places: [[basic.scope.scope#3]] and [[basic.scope.scope#4]] define when two declarations **correspond**, [[basic.link#8]] says that corresponding declarations declare the same entity, and [[basic.link#11]] requires all declarations of the same entity to have the same type. Together:

- Two declarations of functions with the same name that don't correspond declare different functions and overload each other;
- Two corresponding declarations declare the same function and must have the same type; otherwise the program is ill-formed.

### What corresponds means

A non-static member function has an **object parameter**: the parameter that `*this` is bound to in a call. In the traditional form it is implicit (of type `X&`, `const X&`, etc.); since C++23 it can also be written explicitly with `this`. The **non-object-parameter-type-list** is the parameter-type-list without the object parameter.

Per [[basic.scope.scope#4]], two non-template function declarations **correspond** if and only if:

- their non-object-parameter-type-lists are the same;
- their trailing *requires-clause*s (if any) are equivalent;
- if both are non-static member functions, their object parameters also correspond.

The rule for corresponding object parameters ([[basic.scope.scope#3]]) is designed around **ref-qualifiers** (*ref-qualifier*, the `&` or `&&` at the end of a member function declaration): if exactly one is an implicit object member function without a ref-qualifier, the object parameter types are compared after removing references; otherwise the object parameter types are compared directly.

Two function templates correspond only if, in addition, their template-heads and return types are equivalent. The return type is where templates differ from ordinary functions.

### Cases decided this way

**Differing only in the return type**: the return type isn't among the conditions for correspondence, so the two declarations correspond but have different types, which is ill-formed. The design reason is that the call `f(1)` itself carries no expected return type, so overload resolution would have nothing to choose by.

**Parameter types that are the same after adjustment**: when [[dcl.fct]] forms a function type, array parameters are adjusted to pointers, function parameters to function pointers, and top-level cv-qualifiers on parameters are dropped. Lists that are the same after adjustment are the same parameter-type-list.

```cpp run ok
typedef int Int;
void f(int);
void f(Int);          // redeclares the same f: an alias doesn't introduce a new type
void g(int*);
void g(int[]);        // redeclaration: int[] is adjusted to int*
void h(int());        // the parameter has function type, adjusted to int(*)()
void h(int (*)());    // redeclaration
void k(int);
void k(const int);    // redeclaration: top-level const isn't part of the function type

void k(const int x) { (void)x; }   // definition of k(int); x is const inside the body
int main() { k(1); }
```

Non-top-level cv-qualification does distinguish overloads: `m(int&)` and `m(const int&)`, `m(int*)` and `m(const int*)` are different functions. `char`, `signed char` and `unsigned char` are three distinct types, and an enumeration type is distinct from its underlying type; all of them can be overloaded separately.

**Differing only in default arguments**: default arguments aren't part of the function type. `void f(int);` and `void f(int, int = 0);` have different numbers of parameters, don't correspond, and can coexist, but a call `f(1)` is an exact match for both and is ambiguous.

**Differing only in `noexcept`**: since C++17 `noexcept` is part of the function type, but it isn't among the conditions for correspondence. So `void f() noexcept;` and `void f();` correspond and declare the same function but have different types, which is ill-formed per [[basic.link#11]].

**One static, one non-static**: a static member function has no object parameter, and [[basic.scope.scope#4.4]] compares object parameters only when both are non-static members. So a static and a non-static member function with the same parameters correspond, and they conflict.

```cpp error
struct X {
  static void f();
  void f() const;     // error: corresponds to static f()
};
```

This is prohibited because `x.f()` could call either (the implicit object parameter of a static member function matches any object, [[over.match.funcs#4]]), and the object argument's match for the static function is neither better nor worse, so such an overload would almost always be ambiguous.

**Ref-qualifiers**: member functions with the same name and parameters, one with a ref-qualifier and one without, can't coexist.

```cpp error
struct X {
  void g();
  void g() const;      // OK: after removing references, X and const X differ
  void g() &;          // error: corresponds to g()
  void h() &;
  void h() &&;         // OK: both have a qualifier, and X& and X&& differ
  void k() const;
  void k() const &&;   // error: corresponds to k() const
};
```

`g()` has no ref-qualifier and can be called on both lvalues and rvalues; alongside `g() &` it would only make calls on lvalues ambiguous. When C++11 introduced ref-qualifiers, it required member functions with the same name and parameters to either all have one or all lack one; the current correspondence rule expresses the same thing.

**Explicit object parameters**{{c++23}}: the `this` parameter introduced by [[P0847R7]] is compared by the same rules as the implicit object parameter.

```cpp error
struct X {
  void k();
  void k(this X&);     // error: both object parameters are X&
  void j(this const X&);
  void j() const &;    // error: both object parameters are const X&
  void h(this X&, int);
  void h(int) &&;      // OK: X& and X&& differ
  void m(this X);
  void m() const;      // OK: after removing references, X and const X differ
};
```

### Templates: the return type distinguishes them

The two `g` templates on the right at the start of this section have different return types, so per [[basic.scope.scope#3]] they don't correspond and are valid. A call `g(1)` is ambiguous, but one of them can be selected by target type:

```cpp ok
template<class T> int    g(T);
template<class T> double g(T);
int (*p)(int) = &g<int>;       // OK: selects the first ([over.over])
```

A template's return type can depend on template parameters and take part in substitution failure (as in `auto f(T t) -> decltype(t.foo())`), so it has to be part of the template's identity. For the same reason the Itanium C++ ABI encodes the return type in the mangled name of a function template specialization, whereas the mangled name of an ordinary function contains no return type.

### Constraints also distinguish declarations

Two declarations whose trailing *requires-clause*s aren't equivalent don't correspond and can coexist; [[over.match.best#2.6]] makes the more constrained one win:

```cpp run ok
#include <concepts>
template<class T>
struct Box {
  int get() const requires std::integral<T> { return 1; }
  int get() const { return 2; }   // doesn't correspond: one is constrained, the other isn't
};
int main() {
  return Box<int>{}.get() == 1 && Box<double>{}.get() == 2 ? 0 : 1;
}
```

### Corresponding declarations from different scopes

Corresponding declarations conflict only in the same scope. Through a *using-directive* or ADL, overload resolution can see corresponding declarations from different scopes at once; the declarations themselves are valid, but the call is often ambiguous ([[basic.scope.scope#6]], Note 4):

```cpp error
namespace A { int f(int); }
namespace B { int f(int); }
using namespace A;
using namespace B;
void use() {
  f(1);   // error: A::f and B::f have identical parameters; ambiguous
}
```

!!! impl "Name mangling"
    Under the Itanium C++ ABI, `int f(int)` and `double f(int)` both mangle to `_Z1fi`; the return type doesn't go into the symbol. So when two translation units disagree on the return type of the same function, the linker still links them together; this is an ODR violation with no diagnostic required. `const` and ref-qualifiers do go into the mangled name of a member function (`K`, `R`, `O`).

!!! history
    Up to C++20, the declarations that can't be overloaded were listed one by one in `[over.load]`: differing only in the return type, static and non-static with the same parameters, differing only in top-level cv, array and pointer parameters being equivalent, differing only in default arguments, and so on. [[P1787R6]] in C++23 removed that subclause and expressed the rules uniformly through the correspondence notion of [[basic.scope.scope]]; the conclusions are essentially unchanged.

## Common misconceptions

!!! pitfall "`const` parameters can form overloads"
    `void f(int)` and `void f(const int)` are the same function. Writing `int` in the declaration and `const int` in the definition is valid and a common style.

!!! pitfall "A function with the same name in a derived class overloads the base class's"
    It hides all base class functions with that name, regardless of parameters. To merge the overload sets, write `using Base::f;`.

!!! pitfall "Default arguments can resolve an ambiguity"
    Default arguments only make calls with fewer arguments viable; they don't affect ranking. `f(int)` and `f(int, int = 0)` are always ambiguous for `f(1)`.

## Questions

!!! question "1. Which of these declarations can appear in the same class?"
    ```cpp nocheck
    struct S {
      void a() &;        // #1
      void a() const &;  // #2
      void a() &&;       // #3
      void a();          // #4
    };
    ```

<details markdown="1">
<summary>Answer</summary>

\#1, #2 and #3 all have ref-qualifiers, so their object parameter types are compared directly: `S&`, `const S&` and `S&&` all differ, so they can coexist. #4 has no ref-qualifier; compared with #1, references are removed and both are `S`, so the two correspond and the program is ill-formed ([[basic.scope.scope#3]]).
</details>

!!! question "2. Can `void f(int[3]);` and `void f(int(&)[3]);` coexist? Which one does `int a[3]; f(a);` select?"

<details markdown="1">
<summary>Answer</summary>

They can coexist. The former is adjusted to `void f(int*)`; the latter's parameter is a reference to an array, a different type. For the call `f(a)`, the former needs an array-to-pointer conversion and the latter is a direct binding; both are exact matches. Lvalue transformations such as array-to-pointer aren't considered in the comparison ([[over.ics.rank#3.2.1]]), so they can't be distinguished and the call is ambiguous. Clang also reports `call to 'f' is ambiguous`.
</details>
