---
title: Overloaded operators
summary: "Which operators can be overloaded and how operator functions must be declared: number of parameters, whether they can be members or static members, whether they can have default arguments, and the special forms ->, postfix ++ and so on."
updated: 2026-10-19
---

!!! tldr
    - An operator function is a function whose name has the form `operator@`. Once the expression `a @ b` selects it, it is rewritten into an ordinary call such as `a.operator@(b)` or `operator@(a, b)`.
    - An operator function must have at least one parameter of class or enumeration type (or a reference to one), so the meaning of `int + int` can never be changed; nor can precedence, associativity or the number of operands.
    - `.`, `.*`, `::` and `?:` can't be overloaded. `&&`, `||` and `,` can be, but once overloaded they no longer short-circuit.
    - `=`, `()`, `[]` and `->` must be member functions. Only `()` and `[]` can have default arguments and any number of parameters, and since C++23 they can also be static members.
    - `x->m` applies `->` repeatedly to the return value of `operator->` until it gets a raw pointer; postfix `++` is distinguished from prefix `++` by a dummy `int` parameter.

This page covers the declaration of operator functions: how many parameters they should have, whether they can be members or static members, whether they can have default arguments. When the expression `a @ b` appears, how the choice is made among members, non-members and built-in operators is specified by [[over.match.oper]]; the list of built-in operators that take part is in [[over.built]].

## Operator functions [over.oper.general]

```cpp run ok
struct V { int x, y; };
V operator+(V a, V b) { return {a.x + b.x, a.y + b.y}; }
int main() {
  V a{1, 2}, b{3, 4};
  V c = a + b;             // rewritten as operator+(a, b)
  V d = operator+(a, b);   // can also be called directly by its function name
  return c.x - d.x;        // 0
}
```

¶1 A declaration whose declarator-id is an *operator-function-id* (the keyword `operator` followed by an operator) must declare a function, a function template, or an explicit instantiation or explicit specialization of a function template. A function so declared is an **[[g:operator-function|operator function]]**; a function template is an operator function template, and its specializations are also operator functions. So a variable declaration like `int operator+;` is ill-formed.

There are 44 operators that can follow `operator`:

```text
new  delete  new[]  delete[]  co_await  ()  []  ->  ->*
~  !  +  -  *  /  %  ^  &  |  =  +=  -=  *=  /=  %=  ^=  &=  |=
==  !=  <  >  <=  >=  <=>  &&  ||  <<  >>  <<=  >>=  ++  --  ,
```

Of these, `new[]`, `delete[]`, `()` and `[]` consist of more than one token (note 1), so whitespace may appear inside `operator ( )`. ¶2 specifies that both the unary and binary forms of `+`, `-`, `*` and `&` can be overloaded; the two have the same name and are distinguished by the number of parameters.

¶4 Operator functions are usually called implicitly by operator expressions, but can also be called explicitly, as with `operator+(a, b)` above. An explicit call is an ordinary function call ([[over.call.func]]) that doesn't go through [[over.match.oper]], so there are no built-in candidates and no C++20 rewritten candidates.

¶5 `operator new`, `operator new[]`, `operator delete` and `operator delete[]` are specified entirely by [[basic.stc.dynamic]], and ¶6 `co_await` entirely by [[expr.await]]. The other restrictions in this subclause don't apply to them. For example, `operator new(std::size_t)` has no parameter of class type, and an `operator new` in a class is implicitly a static member.

### Operators that can't be overloaded

Note 2 under ¶3 lists the operators that can't be overloaded: `.`, `.*`, `::`, `?:`, and the preprocessing operators `#` and `##`. `sizeof`, `typeid`, the various `*_cast`, the reflection operator `^^` and so on aren't in ¶1's list at all, so naturally they can't be overloaded either.

Each of these has its own reason:

- `::` resolves names at compile time; its left side isn't a value.
- If `.` and `.*` could be overloaded, there would be no reliable way to access the members of the object itself.
- `?:` evaluates only one of its two branches, while a function call evaluates all its arguments.

### Operations on built-in types can't be changed (¶7)

<div class="compare" markdown="1">

```cpp error
// error: no parameter of class or enumeration type
int operator+(int, int);
```

```cpp ok
enum class C {};
C operator~(C);   // OK: enumeration
struct S {};
S operator-(S, int);   // OK: class
```

</div>

¶7 An operator function must have at least one function parameter or implicit object parameter whose type is a class, an enumeration, or a reference to one. Pointers don't count: `int operator+(C*, int)` is ill-formed too. Member functions satisfy this automatically, because their implicit object parameter has a type such as `X&`.

Together with [[over.match.oper#1]], this rule guarantees that if no operand is of class or enumeration type, the operator is always built-in. The function template `template<class T> int operator-(T*, T*);` can itself be declared, but `p - p` (`int*`) never undergoes overload resolution, so this template can never be used.

¶7 goes on to specify that the precedence, associativity and number of operands of an operator can't be changed. `=`, unary `&` and `,` have predefined meanings for every type and can be redefined for specific classes; unary `&` and `,` can also be redefined for specific enumerations. `=` can't be redefined for enumerations, because `operator=` must be a member and enumerations have no members.

Operator functions are inherited by derived classes like other member functions. The only exception, in effect, is `operator=`, which is always hidden by the copy assignment implicitly declared in the derived class (see [over.assign] below).

!!! lawyer "Explicit object parameters and ¶7"
    ¶7 speaks of a function parameter or implicit object parameter. A C++23 explicit object member function has no implicit object parameter; the `this` parameter is just an ordinary function parameter. So both parameters of `struct S { int operator+(this int, int); };` are `int`, which is ill-formed by ¶7. At the time of writing, Clang 23 doesn't diagnose this.

### Number of parameters and default arguments (¶8–¶11)

¶8 An operator function must be one of: a prefix unary, binary, function call, subscripting, class member access, increment or decrement operator function, each defined in the subsections that follow. `!` and `~` have no binary form, so `operator!(S, S)` is ill-formed.

¶10 The number of parameters must be exactly the number the operator needs, and there can be no default arguments; the only exceptions are `operator()` and `operator[]`. If default arguments were allowed, `operator-(S = S{})` could act as both unary and nullary, and a postfix `operator++(int = 0)` couldn't be told apart from the prefix version.

```cpp
struct S {
  void operator+(int = 0);    // error: can't have a default argument
  void operator()(int = 0);   // OK: the function call operator is an exception
  int  operator[](int = 0);   // OK: the subscript operator is an exception
  void operator-(int, int);   // error: a member binary - can have only one non-object parameter
};
```

¶11 Operators not specified separately below are treated as ordinary unary and binary operators. So `->*`, `&&`, `||`, `,`, compound assignments such as `+=`, and `<=>` can all be non-members. The only ones specified separately and required to be members are `=`, `()`, `[]` and `->`.

Note 3 under ¶9 reminds us that identities among built-in operators need not hold for operator functions. The language doesn't derive `+=` from `+`; for fundamental types `++a` is equivalent to `a += 1`, but not necessarily for class types. The built-in `+=` requires its left operand to be an lvalue; operator functions have no such requirement.

## Unary and binary operators [over.unary] [over.binary]

### Member or non-member

```cpp run ok
struct Num {
  int v;
  Num(int x) : v(x) {}
  friend Num operator+(Num a, Num b) {
    return a.v + b.v;
  }
};
int main() {
  Num a = 1;
  Num b = 2 + a;   // OK: both sides can convert via Num(int)
  return b.v - 3;
}
```

[over.unary] ¶1 A **[[g:prefix-unary-operator-function|prefix unary operator function]]** is a non-static member function with no non-object parameters, or a non-member function with exactly one parameter. `@x` is interpreted as `x.operator@()` if a member is selected and as `operator@(x)` if a non-member is selected.

[over.binary.general] ¶1 A **[[g:binary-operator-function|binary operator function]]** is a non-static member function with exactly one non-object parameter, or a non-member function with exactly two parameters. `x @ y` is interpreted as `x.operator@(y)` if a member is selected and as `operator@(x, y)` if a non-member is selected. Non-static members here include C++23 explicit object member functions ([[P0847R7]]), whose `this` parameter counts as the object parameter.

The left operand of the member version corresponds to the object parameter, which may not be reached through a user-defined conversion ([[over.best.ics#9]]). If `operator+` in the example above were a member, `a + 2` would compile but `2 + a` wouldn't. Operators that need symmetric conversions on both sides should be non-members, ideally **hidden friends** as in the example: friend functions defined only inside the class, which can be found only by argument-dependent lookup (ADL) and don't leak into the overload sets of enclosing scopes.

A binary operator can't be a static member function. A static member has no object parameter, leaving only one parameter and nowhere to put the left operand.

```cpp
struct S {
  static int operator+(S, S);   // error: can't be a static member
  int operator+(this S, int);   // OK: explicit object parameter
};
```

### Unary and binary share a name

Note 2 under [over.unary] ¶2 points out that the unary and binary forms of the same operator have the same name, so a unary version can hide a binary version in an enclosing scope, and vice versa:

```cpp error
namespace A { struct S {}; }
A::S operator-(A::S, A::S);     // global binary -
namespace B {
  void operator-(A::S);         // unary - in B
  void f(A::S x) { x - x; }     // error: unqualified lookup stops in B and finds only the unary version
}
```

Unqualified lookup stops as soon as it finds `operator-` in namespace `B`, hiding the global binary version; ADL only looks in `A`, the namespace of `S`, where there's nothing. Put the binary `operator-` in `A` and ADL finds it. This is one reason to put operators in the same namespace as their types.

### Comparison operator functions

[over.binary.general] ¶2 defines some terms used in places such as [[class.compare.default]]: one implementing `==` or `!=` is an equality operator function, one implementing `<`, `>`, `<=` or `>=` a relational operator function, and one implementing `<=>` a three-way comparison operator function; together they are **[[g:comparison-operator-function|comparison operator functions]]**. Apart from special member functions, only comparison operator functions and the postfix increment and decrement below can be `= default`.

### `&&`, `||`, `,` and unary `&`

The built-in versions of these operators have special semantics: `&&` and `||` short-circuit, `,` evaluates its left operand first and discards it, and unary `&` takes an address. Once overloaded, the expression becomes a function call, and both operands are evaluated:

```cpp run ok
#include <cstdio>
struct B { bool v; };
bool operator&&(B a, B b) { return a.v && b.v; }
B make(bool v, const char* s) { std::puts(s); return {v}; }
int main() {
  bool r = make(false, "left") && make(true, "right");   // prints left, right: no short-circuit
  return r;
}
```

Since C++17, the operands of an overloaded operator are sequenced by the rules of the corresponding built-in operator ([[P0145R3]], [[over.match.oper#2]]), so at least the left operand is evaluated before the right.

Once unary `&` is overloaded, `&obj` no longer yields the address, which is why the standard library provides `std::addressof`. In generic code, `a, b` might also call a user's `operator,`; the usual defensive form is `(void)a, b`: an operand of type `void` can't be passed to any function, so only the built-in comma can be used ([[over.match.oper#13]]).

```cpp run ok
#include <memory>
struct Evil { int operator&() const { return 0; } };
int main() {
  Evil e;
  auto a = &e;                   // calls Evil::operator&; a is an int
  Evil* p = std::addressof(e);   // the real address
  static_assert(__is_same(decltype(a), int));
  return p ? 0 : 1;
}
```

## Assignment [over.assign]

¶1 A **simple assignment operator function** is a binary operator function named `operator=`, and must be a non-static member function.

Why can't it be a non-member? Every class implicitly declares a copy assignment operator. If a non-member `operator=` were allowed, the same `a = b` could call different functions before and after its declaration, and the class author would lose control of the assignment semantics of their own type.

Note 1 adds that for the left operand of an assignment only standard conversion sequences are considered ([[over.match.oper#5]]), so when the left operand has class type, `x = y` is always interpreted as `x.operator=(y)` and the built-in assignment can never be selected:

```cpp
struct S {};
void operator=(S&, int);              // error: must be a non-static member function
struct T { static T& operator=(int); };   // error: can't be a static member
struct R { operator int&(); };
void g(R r) { r = 5; }                // error: built-in int& = int isn't viable, and R has no operator= taking int
```

Note 2 under ¶2: a derived class always implicitly declares its own copy assignment operator, which hides all of the base class's `operator=`. To use the base class version, you have to write `using Base::operator=;`.

```cpp
struct B { B& operator=(int); };
struct D : B {};
struct D2 : B { using B::operator=; };
void f(D d, D2 d2) {
  d2 = 1;   // OK: B::operator=(int) is visible through the using-declaration
  d = 1;    // error: hidden by D's implicit copy and move assignment, and 1 can't convert to D
}
```

Note 3 under ¶3: any assignment operator, including copy and move assignment, can be virtual. But the copy assignment of derived class `D` doesn't override the virtual copy assignment of base class `B`, because the former's parameter is `const D&` and the latter's is `const B&`:

```cpp run ok
#include <cstdio>
struct B {
  virtual int operator=(int) { return 0; }
  virtual B& operator=(const B&) { std::puts("B::operator=(const B&)"); return *this; }
};
struct D : B {
  int operator=(int) override { std::puts("D::operator=(int)"); return 1; }
  D& operator=(const B&) override { std::puts("D::operator=(const B&)"); return *this; }
};
int main() {
  D d1, d2;
  B* bp = &d1;
  *bp = 99;   // virtual call to D::operator=(int)
  *bp = d2;   // virtual call to D::operator=(const B&)
  d1 = d2;    // implicitly declared D::operator=(const D&), which calls B::operator=(const B&) on the base subobject
}
```

The last line prints `B::operator=(const B&)`: `d1 = d2` selects the implicitly declared `D::operator=(const D&)`, bypassing the virtual function written for the purpose. Polymorphic assignment is prone to surprises like this.

## Function call [over.call]

¶1 A **function call operator function** is a member function named `operator()`, with any number of parameters, which may have default arguments. For `f(args)` with `f` of class type, overload resolution is done by [[over.call.object]].

Besides `operator()`, the candidates include **surrogate call functions**: if the class has conversion functions to a function pointer or function reference, each such conversion function produces a candidate. If a surrogate call function is selected, the conversion function is called first to get `e`, and the expression is interpreted as `e(args)`; otherwise it's interpreted as `f.operator()(args)`.

```cpp run ok
#include <cstdio>
using F = int (*)(int);
int twice(int x) { return 2 * x; }
struct Conv { operator F() const { return twice; } };   // produces a surrogate call function
struct Adder { int operator()(int a, int b = 10) const { return a + b; } };
struct Stateless { static int operator()(int x) { return x + 1; } };   // C++23
int main() {
  auto inc = [](int v) static { return v + 1; };   // C++23 static lambda
  std::printf("%d %d %d %d %d\n",
              Conv{}(21),                 // (c.operator F())(21): 42
              Adder{}(1),                 // default argument: 11
              Stateless{}(1),             // 2
              Stateless::operator()(1),   // a static member can be called with the class name
              inc(1));                    // 2
}
```

¶1 says member function, not non-static member function. C++23's [[P1169R4]] relies on this to allow `static operator()`, and a capture-less lambda can also be declared `static`. A static `operator()` doesn't need to pass `this`, which suits stateless function objects such as comparators, hashes and projections.

Surrogate call functions compete on equal terms with the real `operator()` and may produce ambiguity:

```cpp error
using F = int (*)(int);
int twice(int x) { return 2 * x; }
struct Both {
  operator F() const { return twice; }
  int operator()(long) const { return -1; }
};
int x = Both{}(1);   // error: ambiguous
```

For `operator()(long)`, the object argument needs no conversion and `1` must be converted from `int` to `long`. For the surrogate call function, the object argument goes through a user-defined conversion and `1` needs no conversion. Each candidate is better on one argument, so the call is ambiguous.

## Subscripting [over.sub]

¶1 A **subscripting operator function** is a member function named `operator[]`, with any number of parameters, which may have default arguments. If `a[args]` selects it, it is interpreted as `a.operator[](args)`.

```cpp run ok
struct Matrix {
  int d[3][4]{};
  int& operator[](int i, int j) { return d[i][j]; }   // multidimensional subscript
  static int operator[]() { return 42; }              // zero arguments, static member
};
int main() {
  Matrix m;
  m[1, 2] = 7;
  return m[1, 2] + Matrix{}[] - 49;
}
```

The brackets contain an *expression-list*, which can have zero, one or more arguments; this is C++23's multidimensional subscript ([[P2128R6]]), the syntax `std::mdspan` uses. To make room for it, C++20 first deprecated unparenthesized comma expressions in subscripts ([[P1161R3]]): `a[1, 2]` in C++20 is `a[(1, 2)]` with a deprecation warning, and since C++23 it is a subscript with two arguments. Also in C++23, [[P2589R1]] allowed `static operator[]`.

The example in ¶2 shows that the built-in subscript still accepts only one subscript:

```cpp
#include <initializer_list>
struct Z {};
struct X {
  Z operator[](std::initializer_list<int>);
  Z operator[](auto...);
};
X x;
void f() {
  x[{1,2,3}] = Z{};   // OK: x.operator[]({1,2,3})
  x[1,2,3] = Z{};     // OK: x.operator[](1,2,3)
  int a[10];
  a[{1,2,3}] = 7;     // error: built-in subscript operator
  a[1,2,3] = 7;       // error: the built-in subscript operator accepts only one subscript
}
```

To get the old comma-expression meaning, parenthesize it: `a[(i, j)]`.

## Member access `->` [over.ref]

¶1 A **class member access operator function** is a non-static member function named `operator->` with no non-object parameters. If `x->m` selects it, it is interpreted as

```text
(x.operator->())->m
```

The same applies when `x->` is followed by a C++26 splice expression.

The key is that the result gets another `->` applied to it. If `operator->()` returns a class type rather than a pointer, the new `->` is again an operator expression, so its `operator->()` is called in turn. This continues layer by layer until a raw pointer is obtained, and finally the built-in `->` is applied:

```cpp run ok
struct T { int v = 7; };
struct Inner { T t; T* operator->() { return &t; } };
struct Outer { Inner i; Inner& operator->() { return i; } };   // returns a class type: keeps going
int main() {
  Outer o;
  return o->v - 7;   // o.operator->() gives Inner&, then .operator->() gives T*, then built-in ->
}
```

The right side of `x->m` is a member name, not an expression that can be evaluated, so it can't be passed to a function as an argument; that's why `operator->` is defined as a function without non-object parameters, responsible only for producing a result to which `->` can be applied again.

The return type of `operator->` itself is unrestricted; returning `int` can be declared, but `b->x` fails at the last step because the built-in `->` needs a pointer. Returning its own type would go on forever; the standard has no specific rule for this, and what you actually hit is an implementation limit: Clang reports `circular pointer delegation detected`.

```cpp
struct Bad { int operator->() { return 0; } };
struct Self { Self operator->() { return *this; } int x; };
void f(Bad b, Self s) {
  (void)b.operator->();   // OK: an ordinary member function call
  (void)b->x;             // error: the result is int; -> can't be applied again
  (void)s->x;             // error: goes on forever
}
```

## Increment and decrement [over.inc]

### Prefix and postfix ([over.inc.general])

```cpp run ok
struct X {
  int n = 0;
  X& operator++() { ++n; return *this; }            // prefix ++a
  X  operator++(int) { X t = *this; ++n; return t; } // postfix a++
};
struct Y { int n = 0; };
Y& operator++(Y& y) { ++y.n; return y; }             // prefix ++b
Y  operator++(Y& y, int) { Y t = y; ++y.n; return t; }   // postfix b++
int main() {
  X a; Y b;
  ++a; a++;   // a.operator++(); a.operator++(0);
  ++b; b++;   // operator++(b); operator++(b, 0);
  return a.n + b.n - 4;
}
```

¶1 An **increment operator function** is a function named `operator++`. A non-static member function with no non-object parameters, or a non-member function with one parameter, defines prefix `++`. A non-static member function with one non-object parameter, or a non-member function with two parameters, defines postfix `++`, and that extra parameter must be `int`. ¶2 A **decrement operator function** `operator--` works the same way.

The dummy `int` parameter's only purpose is to make the prefix and postfix signatures differ. When called through `a++`, the argument is 0; a footnote explains that an explicit call `a.operator++(2)` is nothing special, and the argument is simply 2. The parameter must be exactly `int`: `long` won't do, nor will a default argument `int = 0` (¶10).

```cpp
struct S {
  S operator++(long);      // error: postfix ++'s parameter must be int
  S operator--(int = 0);   // error: can't have a default argument
};
```

By convention prefix returns a reference and postfix returns a copy of the old value. The language doesn't enforce this (¶9), but breaking it surprises users. The postfix version has to copy, which is why generic code habitually writes `++it`.

### Defaulted postfix increment and decrement ([over.inc.default]) {{c++29}}

Postfix `++` is almost always written the same way: make a copy, call the prefix version, return the copy. [[P3668R4]], merged into the draft after C++26, allows declaring it directly as `= default`.

¶1 A defaulted postfix increment or decrement operator for type `C` must be a non-template function and satisfy:

- ¶1.1 its first parameter has type `C&` or `volatile C&`. The implicit object parameter of a member function counts as the first parameter.
- ¶1.2 it is defined as defaulted within `C` or in a context where `C` is complete.
- ¶1.3 its declared return type is `C`.

Name lookup and access checking in the implicit definition are performed in a context equivalent to its function body. If it is defined as defaulted within the class, this must be the function's first declaration.

¶3 If not deleted, the implicit definition is equivalent to the following, where `c` stands for `*this` or the first parameter:

```cpp
C tmp(c);
++c;          // --c for the decrement version
return tmp;
```

¶2 A defaulted postfix operator is defined as deleted if: `C` is a class type that can't be direct-initialized from an lvalue of `C` (not copyable, ¶2.1); `C`'s destructor is deleted or inaccessible (¶2.2); for an lvalue `c` of `C`, `++c` (or `--c`) has no usable candidate (¶2.3).

The example in ¶4:

```cpp
struct S {
  S(const S&) = default;
  S& operator++() { return *this; }
};
S operator++(S, int) = default;      // error: the first parameter must be a reference

struct T {
  T operator++(int) = default;       // OK, defined as deleted: T has no prefix ++
};

enum class E1 {};
E1 operator++(E1&, int) = default;   // OK, defined as deleted: enumerations have no built-in ++

enum E2 {};
E2& operator++(E2& e);
E2 operator++(E2&, int) = default;   // OK, not deleted: calls the user's prefix ++
```

Even unscoped enumerations have no built-in `++`. [[over.built#4]] provides `++` candidates only for arithmetic types and object pointer types, and promoting an enumeration to an integer yields a prvalue, which can't bind to `int&`.

At the time of writing, Clang 23 doesn't implement this rule yet; every `= default` above gets `only special member functions and comparison operators may be defaulted`. Under the current draft, the lines marked OK are well-formed.

## Summary

| Operator | Can be non-member | Can be static member | Default arguments | Number of parameters (member / non-member) |
|---|---|---|---|---|
| unary `+ - * & ! ~` | yes | no | no | 0 / 1 |
| binary (including `->*`, `&&`, `,`, compound assignment, comparison) | yes | no | no | 1 / 2 |
| `=` | no | no | no | 1 |
| `()` | no | yes (C++23) | yes | any |
| `[]` | no | yes (C++23) | yes | any (exactly 1 before C++23) |
| `->` | no | no | no | 0 |
| prefix `++ --` | yes | no | no | 0 / 1 |
| postfix `++ --` | yes | no | no | 1 / 2, the last one `int` |
| `new delete new[] delete[]` | see [[basic.stc.dynamic]] | implicitly static in a class | | |
| `co_await` | see [[expr.await]] | | | |

For members, the number of parameters means non-object parameters; C++23 explicit object parameters aren't counted.

!!! impl
    - In the Itanium C++ ABI, the name mangling of operator functions uses two letters for the operator: `operator+` is `pl`, `operator()` is `cl`, `operator[]` is `ix`, `operator->` is `pt`, `operator<=>` is `ss`. `S::operator+(int)` mangles to `_ZN1SplEi`.
    - A static `operator()` saves the `this` argument. When the call is inlined, the non-static version's `this` is usually optimized away too; through `std::function` or across translation units, the static version passes one argument fewer. With `static` added to a capture-less lambda, the conversion to function pointer can return the address of `operator()` directly, without generating a separate forwarding function.
    - Clang's diagnostics for violations of this subclause mostly start with `overloaded 'operator@' must` or `cannot`, for example `must have at least one parameter of class or enumeration type`, `must be a non-static member function`, `cannot have a default argument`.

## History

!!! history
    - C++98 already had the basic framework of this subclause: the list of overloadable operators, at least one class or enumeration parameter, `=`, `()`, `[]` and `->` as non-static members, the dummy `int` parameter for postfix, and the layer-by-layer application of `->`.
    - C++11 allowed braced lists as subscripts (`x[{1,2,3}]`), and user-defined literals got their own [[over.literal]].
    - C++17's [[P0145R3]] made the operands of overloaded operators follow the evaluation order of the built-in operators.
    - C++20 added `<=>`, defaulted comparison operators and overloadable `co_await`, and deprecated comma expressions in subscripts ([[P1161R3]]).
    - C++23 added explicit object parameters ([[P0847R7]]), `static operator()` ([[P1169R4]]), multidimensional subscripts ([[P2128R6]]) and `static operator[]` ([[P2589R1]]).
    - After C++26, [[P3668R4]] added defaulted postfix increment and decrement.

## Common misconceptions

!!! pitfall "A derived class inherits the base class's `operator=`"
    All other operator functions can be inherited, but `operator=` is always hidden by the copy assignment the derived class implicitly declares; you need `using Base::operator=;`.

!!! pitfall "Symmetric operators as members"
    `x + 1` compiles but `1 + x` doesn't, because the left operand corresponds to the object parameter, which doesn't undergo user-defined conversions. Write symmetric operators as hidden friends.

!!! pitfall "Writing `&x` or `a, b` directly in generic code"
    The operand's type may overload unary `&` or `,`. Use `std::addressof(x)` to take the address, and write the comma as `(void)a, b`.

## Questions

!!! question "1. Which of these declarations are ill-formed?"
    ```cpp
    struct S {};
    enum E { e };
    S& operator+=(S&, int);          // (a)
    int operator,(E, E);             // (b)
    E* operator&(E&);                // (c)
    void operator=(E&, int);         // (d)
    int operator->*(S, int S::*);    // (e)
    struct T { static int operator[](int, int); };   // (f)
    struct U { static bool operator==(U, U); };      // (g)
    ```

<details markdown="1">
<summary>Answer</summary>

- (a) Well-formed. A compound assignment isn't the simple assignment of [over.assign]; by ¶11 it's an ordinary binary operator and can be a non-member.
- (b)(c) Well-formed. ¶7 explicitly allows redefining `,` and unary `&` for enumerations.
- (d) Ill-formed. `operator=` must be a non-static member function, and enumerations have no members, so assignment for enumerations can't be redefined.
- (e) Well-formed. `->*` is an ordinary binary operator and can be a non-member, unlike `->`.
- (f) Well-formed (C++23). A static subscript operator with two parameters.
- (g) Ill-formed. A binary operator function must be a non-static member or a non-member; `static` is open only to `()` and `[]`.

Clang 23 reports errors only for (d) and (g).
</details>

!!! question "2. Why can `operator()` and `operator[]` be static, but not `operator+`?"

<details markdown="1">
<summary>Answer</summary>

In `f(args)` and `a[args]` the arguments are all written inside the brackets; `f` and `a` are just the object being called or indexed. The static member version treats that object as an implied object argument, which is discarded after matching ([[over.match.funcs.general#4]]), and the argument list inside the brackets is still complete. In `a + b` the two operands have equal status, and in the member form the left operand is the object argument. A static member has no object parameter, so there's nowhere to put the left operand, and the number of parameters doesn't meet the requirements of [over.binary].
</details>
