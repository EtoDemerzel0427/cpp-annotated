---
title: Function declarators
summary: "What a function type is made of, how parameter types are adjusted, and the rules for ellipses, explicit object parameters, function types with cv/ref qualifiers, and abbreviated function templates."
updated: 2026-10-19
---

!!! tldr
    - A function type consists of the return type, the adjusted parameter-type-list (including whether there is an ellipsis), cv-qualifiers, ref-qualifier and `noexcept`. Default arguments, requires-clauses, contracts and parameter names are not part of the type.
    - Parameter types are adjusted before entering the function type: arrays and functions become pointers, and top-level cv is removed. So `f(int)` and `f(const int)` are the same function.
    - `void f(int...)` is a C-style variadic function, not a parameter pack; this comma-less form is deprecated since C++26.
    - An explicit object parameter `this Self&& self` (C++23) can only be the first parameter of a member function, and the function can then have no cv/ref qualifiers and can't be `static` or `virtual`.
    - A function type like `int() const` can only be used to declare member functions, form pointers to members, appear in a typedef, or serve as a template argument; it can't form ordinary pointers or references.

## What a function type is made of (¶1, ¶13)

```cpp run title="fn-type-parts.cpp" ok
#include <type_traits>

// const on the return type counts too (Clang warns that it has no effect)
static_assert(!std::is_same_v<const int(), int()>);
// noexcept is part of the type (since C++17)
static_assert(!std::is_same_v<void() noexcept, void()>);

void nf() noexcept {}
void (*pf)() = nf;   // OK: noexcept can be dropped ([conv.fctptr])
// void (*pnf)() noexcept = pf;  // error: noexcept can't be added out of thin air

int main() {}
```

¶13 A function type includes the return type, the parameter-type-list, the ref-qualifier, the cv-qualifier-seq and the exception specification. Default arguments ([[dcl.fct.default]]) and trailing requires-clauses are not part of the function type. Note 6 explains that this type is what is checked when a function is used to initialize or is assigned to a pointer to function, reference to function or pointer to member function.

| Component | Example | Part of the function type? |
|---|---|---|
| Return type (including its cv) | `int` vs `const int` | Yes |
| Parameter-type-list (after adjustment) | `(int, char*)` | Yes |
| Presence of an ellipsis | `(int, ...)` | Yes |
| cv-qualifiers | `() const` | Yes |
| ref-qualifier | `() &&` | Yes |
| Exception specification | `noexcept` | Yes, since C++17 |
| Default arguments | `(int = 0)` | No |
| Trailing requires-clause | `requires C<T>` | No |
| Contract specifiers | `pre(x > 0)` | No ([[dcl.contract]]) |
| Parameter names | `(int x)` | No |

Several commonly used facts follow from this:

- Default arguments don't travel with function pointers. After `int f(int = 0);`, `int (*p)() = &f;` is ill-formed, because `f` has type `int(int)`.
- All declarations of the same function must have compatible exception specifications, and overloads can't differ only in `noexcept` ([[except.spec]]).
- Templates can deduce `noexcept` from a function pointer type: `template<bool NE> void g(void(*)() noexcept(NE));`.
- Although requires-clauses aren't in the type, two function template declarations that differ only in their constraints still don't correspond ([[basic.scope.scope]]); they are two different templates.

```cpp title="noexcept-redecl.cpp" error
void ne() noexcept;
void ne();              // error: missing noexcept
void ov(int) noexcept;
void ov(int);           // error: can't overload on noexcept alone
```

¶1 gives the form of a function declarator. In a declaration `T D`, if `D` has the form `D1 ( parameter-declaration-clause ) cv ref noexcept attributes trailing-return-type`, then `D` declares a function whose type is "function of (parameter-type-list) cv ref returning `U`", with `noexcept` added if the exception specification is non-throwing ([[except.spec]]). The return type `U` is determined as follows:

- With a trailing return type, `T` must be exactly `auto`, and `U` is the trailing return type (¶1.3);
- The return type of a conversion function `operator int()` is determined by its name; see [[class.conv.fct]] (¶1.1, ¶1.4);
- Otherwise `U` is `T` (¶1.5).

Attributes at the end appertain to the function type. Attributes before a parameter appertain to that parameter (paragraph 2).

## Adjustment of parameter types (¶5)

```cpp title="param-adjust.cpp" error
void f(char*);              // #1
void f(char[]) {}           // defines #1: char[] → char*
void f(const char*) {}      // OK: another overload
void f(char* const) {}      // error: redefinition of #1

void g(char(*)[2]);         // #2
void g(char[3][2]) {}       // defines #2: only the outermost level is adjusted
void g(char[3][3]) {}       // OK: another overload

void h(int x(const int));   // #3: function → function pointer
void h(int (*)(int)) {}     // defines #3
```

¶5 The type of a function is determined in three steps:

1. The type of each parameter (including function parameter packs) is determined from its own declaration;
2. A parameter of type "array of `T`" or of function type `T` is **adjusted** to "pointer to `T`";
3. Top-level cv-qualifiers are deleted from each parameter type.

The resulting list of types, together with whether there is an ellipsis or a function parameter pack, is the function's **parameter-type-list**. It is what gets compared when deciding whether two declarations are the same function or whether a function pointer matches.

Each of the three steps has a reason. Arrays and functions can't be passed by value, and `f(char[])` has always meant passing a pointer in C, at the cost of losing the length. Top-level const only determines whether the function body can modify its own copy of the parameter, which callers can't observe; if it were part of the type, `f(int)` and `f(const int)` would be two overloads that no call could distinguish.

Note 3 points out that the adjustment only affects the function type, not the type of the parameter itself. Inside the function body, `const int x` is still const:

```cpp run title="adjust-not-param.cpp" ok
#include <type_traits>

void f(const int x) {
  // the parameter itself is still const
  static_assert(std::is_same_v<decltype(x), const int>);
}
void f(int);   // redeclaration of the same function

// the const in the second parameter isn't top-level, so it stays
static_assert(std::is_same_v<int(*)(const int p, decltype(p)*),
                             int(*)(int, const int*)>);
int main() { f(1); }
```

So a common practice is to declare `void set(int v);` in the header and define `void set(const int v) { … }` in the source file, preventing the body from accidentally modifying the parameter.

## Parameter lists

### Empty lists and `(void)` (¶3)

¶3 The parameter-declaration-clause determines which arguments can be passed in a call and how they are converted to the parameters ([[expr.call]]). If the clause is empty, the function takes no arguments. In C, `int f();` used to mean unspecified parameters; C only matched C++ in C23.

A single unnamed parameter of a type that is the same as `void` also means an empty parameter list. Otherwise, a parameter can't have cv `void` type:

```cpp title="void-param.cpp" error
using V = void;
void g0(V);          // OK: zero parameters
void p(void, int);   // error: void must be the only parameter
void q(void x);      // error: a void parameter can't have a name

template<class T> struct S3 { void f(T); };
S3<void> z;          // error: f has a parameter of type void
```

The last line shows that a `void` produced by substitution during template instantiation doesn't turn the parameter list into an empty one. Example 1 in the standard further distinguishes dependent and non-dependent types:

```cpp title="void-t-param.cpp"
#include <type_traits>
template<class T>
struct S  { void f(std::void_t<T*>); };    // depends on T
S<int> x;            // per the standard: error, f has a void parameter

template<class T>
struct S2 { void f(std::void_t<int*>); };  // doesn't depend on T
S2<int> y;           // OK: f has no parameters
```

`std::void_t<int*>` is already `void` at the point of declaration, so `S2::f` is a zero-parameter function from the start. Whether `std::void_t<T*>` is `void` is only known at instantiation, by which time it is already a parameter. Clang 23 accepts `S<int>` and allows calling `x.f()` with no arguments, which is inconsistent with the standard.

volatile-qualified parameter types are deprecated ([[depr.volatile.type]]).

### Ellipses (¶4, ¶6, ¶27)

¶4 If the parameter-declaration-clause ends with an ellipsis or a function parameter pack, the number of arguments must be at least the number of parameters that have no default argument and are not packs. ¶6 A function whose parameter-type-list has an ellipsis is a **vararg function**; `printf` is the classic example. Arguments passed to the ellipsis first undergo the default argument promotions ([[expr.call]]), and the function reads them with `va_start` and `va_arg` from `<cstdarg>`:

```cpp run title="vararg.cpp" ok
#include <cstdarg>

int sum(int n, ...) {
  std::va_list ap;
  va_start(ap, n);
  int s = 0;
  for (int i = 0; i < n; ++i) s += va_arg(ap, int);
  va_end(ap);
  return s;
}
void all(...) {}   // C++ has always allowed an ellipsis alone; C only since C23

int main() {
  all(1, "two", 3.0);
  return sum(3, 1, 2, 3) == 6 ? 0 : 1;
}
```

Where syntactically correct, `...` is synonymous with `, ...`. The trouble is that without the comma, `...` might also be declaring a parameter pack. Paragraph 27 disambiguates: if the parameter's type names a template parameter pack that hasn't been expanded, or contains `auto`, the `...` belongs to that parameter and declares a function parameter pack; otherwise it is a C-style ellipsis.

```cpp title="ellipsis-ambig.cpp" ok
template<class... T> void a(T...); // parameter pack
template<class T>    void b(T...); // b(T, ...), deprecated
void c(auto...);                   // parameter pack
void d(int...);                    // d(int, ...), deprecated
int main() {}
```

`b` and `d` look like parameter packs but are actually variadic functions. C++26 therefore deprecated the comma-less ellipsis (the last sentence of paragraph 4, [[depr.ellipsis.comma]], [[P3176R1]]); new code should always write `, ...`. Clang 23 emits a `-Wdeprecated-missing-comma-variadic-parameter` warning for `b` and `d`.

### Function parameter packs (¶26)

¶26 Only a parameter declaration can have `...` in its declarator. In a function's parameter-declaration-clause it declares a **function parameter pack**; in a template parameter list it declares a template parameter pack ([[temp.param]]). A function parameter pack is itself a pack expansion ([[temp.variadic]]).

```cpp run title="fn-param-pack.cpp" ok
// t is a pack of function pointers
template<typename... T>
void f(T (* ...t)(int, int)) { (void)sizeof...(t); }

int add(int, int) { return 0; }
float subtract(int, int) { return 0; }
int main() { f(add, subtract); }   // T = {int, float}
```

## Restrictions on return types and function definitions (¶16–19)

¶16 The return type must be a non-array object type, a reference type, or cv `void`. A function can't return an array or a function, but it can return a pointer or reference to one. Note 8 explains that an array of a placeholder type also counts as an array type.

¶18 Types can't be defined in return or parameter types. C allows defining a struct in a parameter, but such a type is visible only within the prototype and is nearly useless.

```cpp title="return-type.cpp" error
int arr()[3];             // error: can't return an array
int fn()();               // error: can't return a function
auto ok() -> int(*)[3];   // OK: returns a pointer to an array
auto ok2() -> int(&)();   // OK: returns a function reference

struct A { virtual void f() = 0; };
A g();                    // OK: just a declaration, abstract class not checked

void def(struct S {} s);  // error: defines a type in a parameter type
struct S2 {} ret();       // error: defines a type in the return type
```

A function returning an abstract class can be declared; since C++20 this is only checked at the definition and at calls.

¶17 volatile-qualified return types are deprecated ([[depr.volatile.type]]).

¶19 A typedef of function type can be used to declare a function but not to define one, because a typedef has no parameter names:

```cpp title="typedef-fn.cpp" error
typedef void F();
F fv;            // OK: equivalent to void fv();
F fv {}          // error: a typedef can't be used to define a function
void fv() {}     // OK: the definition of fv
```

## Explicit object parameters {{c++23}} (¶7–10)

An ordinary non-static member function has an implied parameter representing the object it is called on; overload resolution calls it the **implicit object parameter** ([[g:implicit-object-parameter|implicit object parameter]], [[over.match.funcs]]). The `const`, `&` or `&&` after a function describes the type of this parameter. C++23 allows writing it out:

```cpp run title="deducing-this.cpp" ok
#include <cstdio>
#include <type_traits>
#include <utility>

struct C {
  int v = 1;
  void f(this C& self) { self.v++; }   // no this in the body
  template<class Self>
  int g(this Self&& self, int k) {     // one piece of code covers &, const& and &&
    return std::forward<Self>(self).v + k;
  }
};
// taking the address gives an ordinary function pointer, not a pointer to member function
static_assert(std::is_same_v<decltype(&C::f), void (*)(C&)>);

struct Base {
  template<class Self>
  auto name(this const Self&) { return Self::tag; }
};
struct D1 : Base { static constexpr const char* tag = "D1"; };

int main() {
  C c;
  c.f();
  auto pf = &C::f;
  pf(c);                                   // called like an ordinary function
  std::printf("%d %d %d\n", c.v, c.g(10), std::move(c).g(20));  // 3 13 23
  std::printf("%s\n", D1{}.name());        // D1: Self deduced as D1

  auto fib = [](this auto const& self, int n) -> int {   // recursive lambda
    return n < 2 ? n : self(n - 1) + self(n - 2);
  };
  std::printf("%d\n", fib(10));            // 55
}
```

`Base::name` gets the derived class type without CRTP; `fib` is a lambda that can call itself.

¶7 A parameter declaration with the `this` specifier is an **explicit object parameter declaration**. It can only be the first parameter in the parameter list, and can only appear in:

- ¶7.1 a declaration of a member function or member function template;
- ¶7.2 an explicit instantiation or explicit specialization of a templated member function;
- ¶7.3 a lambda declarator ([[expr.prim.lambda]]).

A member function with an explicit object parameter can't have cv-qualifiers or a ref-qualifier and can't be declared `static` or `virtual`. Grammatically, `this` and a default argument can't appear in the same parameter declaration (paragraph 2), so an explicit object parameter can't have a default argument either.

```cpp title="deducing-this-bad.cpp" error
struct C {
  void h(this C) const;          // error: can't have cv-qualifiers
  void i(this C&) &;             // error: can't have a ref-qualifier
  static void s(this C);         // error: can't be static
  virtual void v(this C&);       // error: can't be virtual
  void k(int, this C&);          // error: must be the first parameter
  template<class... Ts>
  void p(this Ts...);            // error: can't be a parameter pack
  void b(this C& self) {
    this->k(1, self);            // error: this can't be used in the body
  }
};
void free_fn(this int);          // error: only for member functions
```

cv- and ref-qualifiers are forbidden because the object's type is already written on the `this` parameter, and writing it again would be redundant and possibly contradictory. `virtual` is forbidden because an explicit object parameter is often a template (`this Self&&`), and function templates can't be virtual; even when it isn't a template, the object argument can be passed by value, which is incompatible with the virtual call mechanism. The ban on using `this` in the body comes from [[expr.prim.this]].

¶8–10 define a few terms:

- A parameter introduced by an explicit object parameter declaration is an **explicit object parameter** ([[g:explicit-object-parameter|explicit object parameter]]); it can't be a function parameter pack;
- A non-static member function with an explicit object parameter is an **explicit object member function**; one without is an **implicit object member function**;
- The two kinds of object parameter are together called **object parameters** ([[g:object-parameter|object parameter]]);
- All other parameters are **non-object parameters**, and their adjusted types form the **non-object-parameter-type-list**. This is what is used when comparing the signatures of two member functions ([[basic.scope.scope]]).

## Function types with cv- or ref-qualifiers (¶11–12)

Types like `int(int) const` and `void() &&` really exist: such a type is the type of a `const` member function with its class removed. These types are often called abominable function types, because they can hardly be used anywhere.

¶11 Such a function type, including one obtained through a typedef name, can only appear as:

- ¶11.1 the type of a non-static member function;
- ¶11.2 the function type to which a pointer to member refers, as in `int (S::*)(int) const`;
- ¶11.3 the top-level type of a function typedef or alias declaration, as in `using F = int(int) const;`;
- ¶11.4 the default argument of a type template parameter;
- ¶11.5 the template argument for a type template parameter, as in `std::is_function<int() const>`;
- ¶11.6 {{c++26}} the operand of a reflection expression `^^`.

```cpp title="abominable.cpp" error
#include <type_traits>
typedef int FIC(int) const;
FIC f;                // error: not a member function
FIC* pf;              // error: can't form an ordinary pointer
struct S {
  FIC f;              // OK: declares int f(int) const
};
FIC S::*pm = &S::f;   // OK: pointer to member
static_assert(std::is_function_v<FIC>);  // OK: template argument
```

Metaprogramming has to match each of these forms, so a naive implementation of `std::is_function` needs 48 partial specializations: 4 kinds of cv × 3 kinds of ref-qualifier × 2 for noexcept × 2 for the presence of an ellipsis.

¶12 cv-qualification in a function declarator is different from adding cv on the outside of a function type; the latter is simply ignored. Note 5 explains that a function type with a cv-qualifier-seq is not a cv-qualified type; there are no cv-qualified function types in C++.

```cpp title="const-fn-typedef.cpp" ok
#include <type_traits>
typedef void F();
struct S {
  const F f;     // equivalent to void f();, not void f() const
};
void S::f() {}
static_assert(std::is_same_v<decltype(&S::f), void (S::*)()>);
int main() {}
```

Clang 23 warns on `const F f;` that the const has no effect.

## Abbreviated function templates {{c++20}} (¶22–25)

```cpp run title="abbrev.cpp" ok
#include <concepts>
#include <type_traits>

void g1(const std::integral auto*, std::floating_point auto&);
// equivalent to template<std::integral T, std::floating_point U>
//               void g1(const T*, U&);
template<> void g1<int>(const int*, double&);   // can be explicitly specialized

auto sum(auto... xs) { return (xs + ... + 0); } // introduces a template parameter pack
static_assert(std::is_same_v<decltype(sum(1, 2L)), long>);

int main() { return sum(1, 2, 3) - 6; }
```

¶23 A function declaration whose parameter types contain generic parameter type placeholders (`auto` or `C auto`, [[dcl.spec.auto]]) is an **abbreviated function template** ([[g:abbreviated-function-template|abbreviated function template]]). It is equivalent to a function template in which each placeholder, in order of appearance, introduces an invented type template parameter:

- `auto` introduces an unconstrained type parameter, `C auto` a type parameter constrained by `C`;
- if the corresponding parameter is a function parameter pack, a template parameter pack is introduced;
- if a placeholder contains `decltype(auto)`, the program is ill-formed.

The standard says such a declaration and the fully written-out form are functionally equivalent but not equivalent ([[temp.over.link]]): the two forms accept the same calls but are not two declarations of the same template, so you can't declare with one form and define with the other.

¶24 An abbreviated function template can also have a template head; the invented parameters come after the explicitly written template parameters:

```cpp run title="abbrev-head.cpp" ok
#include <concepts>
template<typename T, std::integral U>
void g(T, U, std::integral auto) {}
// i.e. template<typename T, std::integral U, std::integral W>
//      void g(T, U, W);

int main() {
  g<double, int, long>(1.0, 2, 3L);  // the third argument corresponds to auto
}
```

¶25 A function declaration at block scope can't declare an abbreviated function template, because templates can only be declared at namespace or class scope ([[temp.pre]]):

```cpp title="abbrev-bad.cpp" error
void f(decltype(auto) x);      // error: decltype(auto) not allowed
void blk() { void h(auto); }   // error: block scope
```

¶22 A function that is not a function template specialization is a **non-template function**. Note 11 reminds us that a function template is not itself a function. A member function of a class template, once instantiated, is a non-template function: it is templated but not a specialization of any function template. Overload resolution prefers non-template functions when all else is equal ([[over.match.best]]), and this is the distinction it uses.

## Implementation notes

!!! impl
    - Name mangling (Itanium ABI): top-level cv is removed, so `f(int)` and `f(const int)` both mangle to `_Z1fi`. `noexcept` function types carry a `Do` prefix: `void k(void(*)() noexcept)` mangles to `_Z1kPDoFvvE`. Explicit object member functions have an extra `H` in the nested name: `C::f(this C&)` mangles to `_ZNH1C1fERS_`. All of these were confirmed with Clang 23 output.
    - When C++17 made `noexcept` part of the type, the mangled names of functions with `noexcept` function pointer parameters changed; this is one of the few language changes that affected the ABI. GCC provides the `-Wnoexcept-type` warning for it.
    - In terms of calling convention, an explicit object member function is just an ordinary function with the object as its first argument.
    - Variadic functions use a different calling convention from ordinary functions: x86-64 System V passes the number of vector registers used in `%al`; Apple's AArch64 platforms put all variadic arguments on the stack. So calling a variadic function through a wrong prototype lacking `...` gives wrong results on Apple Silicon.

## History

!!! history
    - C++98: parameter type adjustment and cv-qualified member functions already existed. Dynamic exception specifications `throw(T)` were not part of the function type.
    - C++11: trailing return types, ref-qualifiers, `noexcept`, function parameter packs.
    - C++17: `noexcept` became part of the function type ([[P0012R1]]); dynamic exception specifications were removed, and C++20 also removed `throw()`.
    - C++20: abbreviated function templates; volatile parameters and return types deprecated; abstract class return types checked only at definitions and calls.
    - C++23: explicit object parameters ([[P0847R7]]).
    - C++26: the comma-less ellipsis deprecated ([[P3176R1]]); function types with cv/ref qualifiers can be the operand of `^^`.

## Common misconceptions

!!! pitfall "`void f(int a[10])` keeps the array length"
    The length is lost during adjustment. `sizeof(a)` is the size of a pointer, and any `int*` can be passed in. To keep the length, use `int (&a)[10]` or `std::span<int, 10>`.

!!! pitfall "A function with a default argument can be used as a zero-argument function"
    Default arguments are not part of the type. With `int f(int = 0)`, `std::function<int()> fn = f;` is ill-formed. Wrap it in a lambda: `[] { return f(); }`.

!!! pitfall "`int f(int...)` is a parameter pack"
    It is `int f(int, ...)`, a C-style variadic function, and this form is deprecated since C++26. A parameter pack is written `template<class... T> int f(T...)` or `int f(auto...)`.

!!! pitfall "A by-value explicit object parameter modifies the original object"
    `void f(this C self)` copies the object on every call, and the body modifies the copy. For small value types that's exactly right; elsewhere it can be a subtle bug.

## Questions

!!! question "Question 1"
    Which of the following declarations redeclare the same function?
    ```cpp
    void f(int (*)[5]);
    void f(int [][5]);
    void f(int [5][5]);
    void f(int (*const)[5]);
    void f(const int (*)[5]);
    void f(int [5][6]);
    ```

<details markdown="1">
<summary>Answer</summary>

The first four are the same function. Array parameters are adjusted only at the outermost level, so `int [][5]` and `int [5][5]` both become `int (*)[5]`; the const in `int (*const)[5]` is top-level and is removed. In the fifth, the const qualifies the elements, not the top level, so it's another overload. The sixth adjusts to `int (*)[6]`, also another overload (paragraph 5).
</details>

!!! question "Question 2"
    Why is `struct S { void f() const; }; using T = decltype(&S::f);` valid, while `using U = std::remove_pointer_t<void (*)() const>;` is ill-formed?

<details markdown="1">
<summary>Answer</summary>

`decltype(&S::f)` is `void (S::*)() const`, where `void() const` appears as the type a pointer to member refers to, a position allowed by item 11.2. `void (*)() const` tries to form an ordinary pointer to such a type, which isn't on the list in paragraph 11. The error is in writing that type at all and has nothing to do with `remove_pointer_t`.
</details>

!!! question "Question 3"
    Given `struct B { virtual void f(); };`, are `struct D : B { void f(this B&); };` and `struct D2 : B { void f(this D2&); };` well-formed?

<details markdown="1">
<summary>Answer</summary>

A member function of a derived class that corresponds to a declaration of a base class virtual function overrides it and thereby becomes virtual ([[class.virtual#2]]). For two member functions to correspond, their object parameters must correspond: when exactly one of them is an implicit object member function with no ref-qualifier, the object parameter types are compared after removing references ([[basic.scope.scope#3]]).

The object parameter of `D::f(this B&)`, after removing the reference, is `B`, the same as the implicit object parameter of `B::f`, so `D::f` overrides `B::f` and becomes virtual. An explicit object member function can't be virtual (paragraph 7), so it is ill-formed.

The object parameter of `D2::f(this D2&)` is `D2`, which differs from `B`, so by the letter of the rules it doesn't override and only hides `B::f`; it looks like it should be well-formed. Clang 23 reports "an explicit object parameter cannot appear in a virtual function" for both, and the latter is inconsistent with the literal reasoning above. When you need virtual dispatch, you should still use implicit object member functions.
</details>

<details class="fine" markdown="1"><summary>Remaining wording</summary>

¶2 is the grammar of the parameter-declaration-clause: it can be empty, can be just `...`, or can be a parameter list followed by `, ...` or (deprecated) `...`. Each parameter declaration can have attributes, `this` and a default argument, but `this` and a default argument can't both appear.

¶14 is an example: `int fseek(FILE*, long, int);` declares a function taking three arguments and returning `int`. ¶15 is a note: a single name can denote several functions in the same scope; this is overloading ([[over]]).

¶20 Parameter names are optional. When a name appears in a function definition, it names that parameter. Note 9 adds that parameter names can also be omitted in a definition (common for unused parameters), and the parameter names in different declarations need not match.

¶21 is an example comparing `*fpi(int)` (a function returning `int*`) with `(*pif)(const char*, const char*)` (a function pointer): the former groups as `*(fpi(int))`, matching the expression form of calling first and then dereferencing. Note 10 suggests writing complicated return types with a typedef or a trailing return type, for example `auto fpif(int) -> int(*)(int);`, and `auto add(T t, U u) -> decltype(t + u)` when the return type depends on the parameters.

</details>
