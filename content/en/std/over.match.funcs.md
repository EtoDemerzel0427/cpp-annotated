---
title: Candidate functions and argument lists
summary: "Where the input to overload resolution comes from: which functions are candidates, and what the argument list is, in function calls, calls of class objects, construction, user-defined conversions, list-initialization and the other contexts."
updated: 2026-10-19
---

!!! tldr
    - In overload resolution a member function gets an extra implicit object parameter, and the object of the call is matched against it as the first argument. This lets member and non-member functions be compared on the same argument list.
    - No user-defined conversions are applied to the implicit object parameter; for a member function without a ref-qualifier, an rvalue can bind to its non-const implicit object parameter.
    - An unqualified call `f()` inside a class gets `(*this)` added; where there is no `this`, a contrived object is added, and selecting a non-static member function is then an error; resolution doesn't fall back to a static function.
    - Whether constructors or conversion functions are chosen during initialization depends on the form of initialization: copy-initialization considers only non-explicit ones, direct-initialization considers all.
    - List-initialization has two phases: first only the `std::initializer_list` constructors are considered, and all constructors only if none of those is viable; copy-list-initialization that selects an explicit constructor is an error, not a reason to choose another one.

Overload resolution starts from a set of **candidate functions** and an **argument list**, first filters out the viable functions ([[over.match.viable]]), then picks the best one ([[over.match.best]]). A function missing from the candidate set can never be selected; an argument list with one more or one fewer object argument also gives a different comparison result.

How the candidate set and the argument list are determined depends on the context in which overload resolution happens:

| Context | Candidates | Argument list |
|---|---|---|
| Function call `f(args)`, `obj.f(args)` | The result of name lookup | `args`, with the object prepended for member functions |
| Call of a class object `obj(args)` | `operator()` and surrogate call functions | `obj` plus `args` |
| Choosing a constructor `T t(args)`, `T t;` | The constructors of `T` | `args` |
| User-defined conversion `T t = s;` where `s` isn't a `T` | The constructors of `T` and the conversion functions of `s` | `s` |
| Conversion to a non-class type `int i = s;` | The conversion functions of `s` | `s` |
| Direct reference binding `T& r = s;` | The conversion functions of `s` | `s` |
| List-initialization `T t{args}` | First the `initializer_list` constructors, then all | The whole list, or its individual elements |

Operator expressions and class template argument deduction are also contexts for overload resolution; see [[over.match.oper]] and [[over.match.class.deduct]] respectively.

## The implicit object parameter [over.match.funcs.general]

`a + b` could match the member `A::operator+(B)` or the non-member `operator+(A, B)`. To compare the two, their numbers of parameters have to line up. The standard's solution is to give the member function an extra parameter.

¶2 If a member function is an **[[g:implicit-object-member-function|implicit object member function]]** other than a constructor (a non-static member function without an explicit `this` parameter), or a static member function and the argument list includes an object argument, it is considered to have an extra first parameter, called the **[[g:implicit-object-parameter|implicit object parameter]]**, which represents the object for which the member function has been called.

¶3 Correspondingly, the argument list constructed by the context begins with an **[[g:implied-object-argument|implied object argument]]**, which denotes the object to be operated on. The argument list of `obj.f(1)` is `(obj, 1)`.

¶4 The type of the implicit object parameter is determined by the cv-qualification and ref-qualification of the member function, where `X` is the class of which the function is a direct member:

| Member function declaration | Implicit object parameter type |
|---|---|
| `void f() cv;` or `void f() cv &;` | `cv X&` |
| `void f() cv &&;` | `cv X&&` |

The implicit object parameter of a static member function matches any object, since the object is discarded when it is selected. The standard gives it no type and computes no conversion sequence for it (Note 1); in comparisons it is neither better nor worse than any conversion sequence ([[over.best.ics#8]]).

There are two more exceptions, both so that `X` is the class of the object of the call rather than the class in which the function is declared:

- a conversion function is considered a member of the class of the implied object argument;
- a base class member function brought into a derived class by a *using-declaration* (other than a conversion function) is considered a member of the derived class.

The second one determines the result below:

```cpp run ok
#include <cstdio>
struct B {
  void f(int)  { std::puts("B::f(int)"); }
};
struct D : B {
  using B::f;
  void f(long) { std::puts("D::f(long)"); }
};
int main() {
  D d;
  d.f(1);   // B::f(int)
}
```

| Candidate | Object argument `d` | Argument `1` |
|---|---|---|
| `B::f(int)`, considered a member of `D` | to `D&`: identity | `int` to `int`: exact match |
| `D::f(long)` | to `D&`: identity | `int` to `long`: integral conversion |

`B::f(int)` is better on the second argument and wins. If its implicit object parameter were `B&`, `d` to `B&` would be a derived-to-base conversion, each candidate would win on one argument, and the call would be ambiguous. A *using-declaration* would then be unable to merge base class overloads into the derived class.

### Two special properties of the implicit object parameter (¶5)

¶5 The implied object argument is treated like any other argument, but **no user-defined conversions can be applied** to the implicit object parameter ([[over.best.ics#9]]). For a call `s.f()`, the compiler won't first convert `s` to some other class and then call that class's member.

Also, for a member function without a ref-qualifier, an rvalue can bind to the implicit object parameter even when it is a non-const lvalue reference:

```cpp error
struct S {
  void f();      // implicit object parameter S&
  void g() &;    // implicit object parameter S&, with a ref-qualifier
  void h() &&;   // implicit object parameter S&&
};
void use() {
  S{}.f();       // OK: no ref-qualifier, an rvalue can bind to S&
  S{}.g();       // error: g is &-qualified, an rvalue can't bind
  S s;
  s.h();         // error: an lvalue can't bind to S&&
}
```

This allowance dates from C++98: there were no ref-qualifiers then, and code like `std::string("a").append("b")`, which calls a non-const member function on a temporary, had to be valid. Since C++11, adding `&` to a member function prohibits calling it on rvalues.

## Function calls [over.call.func]

### The two forms of a call ([over.match.call.general])

¶1 For a function call `E(args)`, if `E` names one or more functions (or function templates), it is handled by [over.call.func]; if `E` is a class object, it is handled by [over.call.object] in the next section.

### Qualified and unqualified calls ([over.call.func] ¶1–¶3)

¶2 A **qualified call** is `a.f(args)` or `p->f(args)`. `p->f` is always treated as `(*p).f`. The candidate set is the result of member name lookup ([[class.member.lookup]]) in the class of `a`, and the argument list is `args` preceded by the operand to the left of the `.`, which is the implied object argument. The cv-qualification of the object type matters in resolution; that is how a `const` object can only call `const` member functions.

¶3 An **unqualified call** is `f(args)`. The candidate set is the result of ordinary name lookup ([[basic.lookup]]), possibly including argument-dependent lookup. That result is either all non-member functions or all members of some class `T`: when lookup finds a member in class scope it stops, and no argument-dependent lookup is done ([[basic.lookup.argdep]]).

- If the candidates are non-member functions, the argument list is `args`.
- If the candidates are member functions, an implied object argument is added. If we are inside a non-static member function of `T` (or a class derived from it) and `this` is available, `(*this)` is added (¶3.2).
- Otherwise, for example inside a static member function, a **contrived object** of type `T` is added; it serves only to line up with the implicit object parameter (¶3.4). If resolution selects a non-static member function, the call is ill-formed (¶3.3).

```cpp error
struct C {
  void m(int);
  static void m(double);
  static void s() {
    m(1.0);   // OK: selects the static m(double)
    m(1);     // error: selects the non-static m(int), but there's no this here
  }
};
```

In the second call, the contrived object lets the non-static `m(int)` compete, and it wins as an exact match; only then is it found that there is no `this`. Overload resolution doesn't switch to `m(double)` because the non-static function can't be called here. The contrived object matches the implicit object parameter of every member function equally well, so by itself it doesn't cause any function to be selected or eliminated (footnote 94).

{{c++26}} In a constructor's precondition the object hasn't been fully constructed, and in a destructor's postcondition it has already been destroyed. An unqualified call there that selects a non-static member function is likewise ill-formed (¶3.1); writing `this->f()` is fine.

### Explicit object parameters {{c++23}}

C++23 allows the object parameter to be written explicitly: `void f(this const C& self)` ([[P0847R7]]). For such an **explicit object member function**, the first parameter itself corresponds to the implied object argument:

```cpp error
struct C {
  void f(this const C&);
  void g() const {
    f();          // OK: (*this).f()
    this->f();    // OK
    f(*this);     // error: really (*this).f(*this), one argument too many
  }
  static void h() {
    C{}.f();      // OK
    f(C{});       // error: contrived object + C{}, two arguments for one parameter
  }
};
```

Inside a static member function, `f(C{})` doesn't treat `C{}` as the explicit object argument. An unqualified call always adds an implied object argument, and the explicit object parameter only ever corresponds to that.

### Calling through an address ([over.match.call.general] ¶2)

¶2 If what is called is the address of an overload set, such as `(&f)(args)` or `(&C::f)(args)`, resolution is performed over that set, but no implied object argument is added (Note 1). If an implicit object member function is selected, the program is ill-formed, because `&C::f` yields a pointer to member, which can't be called directly.

The standard's example (abridged) puts several forms side by side:

```cpp error
struct C {
  void c(this const C&);    // #1
  void c() &;               // #2
  static void c(int = 0);   // #3

  void d() {
    c();              // error: ambiguous between #2 and #3
    (C::c)();         // error: same as above; parentheses don't change which function is named
    (&C::c)(C{});     // selects #1: no object argument is added, C{} corresponds to the explicit object parameter
    (&C::c)();        // selects #3: only #3 accepts 0 arguments
    (&C::c)(*this);   // error: selects #2, and a call through an address can't call an implicit object member function
  }
};
```

The argument list of `c()` is `(*this)`, an lvalue `C`. The implicit object parameter of #2 is `C&` and the explicit object parameter of #1 is `const C&`; binding to the less cv-qualified reference is better, so #2 beats #1 ([[over.ics.rank#3.2.6]]). #3 is static, and its object parameter is neither better nor worse than any conversion sequence, so #2 and #3 can't be distinguished.

## Calling a class object [over.call.object]

¶1 If `E` in `E(args)` is a class object of type `cv T`, the candidates include at least the function call operators `operator()` of `T`.

¶2 In addition, each non-explicit conversion function of `T` that converts to a pointer to function, a reference to pointer to function, or a reference to function, and whose cv-qualification is at least `cv`, yields an additional **[[g:surrogate-call-function|surrogate call function]]**. If the function type of the target is `R(P1, …, Pn)`, the surrogate call function is equivalent to:

```cpp
R call-function(conversion-type-id F, P1 a1, …, Pn an);
```

Its first parameter is the conversion function's target type. Such conversion functions in base classes yield surrogate call functions too, as long as they aren't hidden by declarations in `T`.

¶3 The argument list is `args` preceded by `E`. When compared against `operator()`, `E` corresponds to its object parameter; when compared against a surrogate call function, `E` corresponds to the first parameter `F`, which requires going through the conversion function and is a user-defined conversion.

```cpp run ok
#include <cstdio>
int f1(int)   { return 1; }
int f2(float) { return 2; }
typedef int (*fp1)(int);
typedef int (*fp2)(float);
struct A {
  operator fp1() { return f1; }
  operator fp2() { return f2; }
} a;
int main() {
  std::printf("%d\n", a(1));   // 1: calls f1 through fp1
}
```

The two surrogate call functions are `call(fp1, int)` and `call(fp2, float)`. The first argument needs a user-defined conversion for both, which is a tie; on the second argument `int` to `int` wins, so `f1` is called.

Surrogate call functions make class objects that convert to function pointers directly callable, and compare them against `operator()` in the same resolution. The object argument to the object parameter of `operator()` is usually an identity conversion, while to a surrogate call function it is a user-defined conversion, so with otherwise identical arguments `operator()` wins. But a surrogate call function may be better on another argument, and the result is an ambiguity:

```cpp error
int g(int);
struct C {
  void operator()(long) const;
  using FP = int(*)(int);
  operator FP() const { return g; }
};
void use(const C& c) {
  c(1L);   // OK: operator()(long)
  c(1);    // error: ambiguous: operator() is better on the object argument, the surrogate call function on the int argument
}
```

The closure type of a captureless lambda has both an `operator()` and a non-explicit conversion function to a function pointer ([[expr.prim.lambda.closure]]), so when it is called, a surrogate call function is also a candidate. The two have identical parameters, and `operator()` always wins on the object argument.

## Choosing a constructor [over.match.ctor]

¶1 When a class object is direct-initialized, default-initialized, or copy-initialized from an expression of the same (or a derived) class, overload resolution selects the constructor:

| Form of initialization | Candidates | Argument list |
|---|---|---|
| Direct-initialization: `T t(a, b);`, `T(a)`, `static_cast<T>(a)` | All constructors | `a, b` |
| Default-initialization: `T t;`, `new T` | All constructors | Empty |
| Copy-initialization: `T t = u;` where `u` is of type `T` or a derived class | Non-explicit constructors | `u` |

Copy-initialization considers only non-explicit constructors:

```cpp error
struct E {
  E() {}
  explicit E(const E&) {}
};
E a;
E b(a);    // OK: direct-initialization
E c = a;   // error: copy-initialization; the explicit copy constructor isn't a candidate
```

Default-initialization in the context of copy-list-initialization is a special case: all constructors are candidates, but selecting an explicit one is ill-formed.

```cpp error
struct D { explicit D(); };
struct Agg { D d; };
D d1;          // OK: default-initialization
D d2{};        // OK: direct-list-initialization
D d3 = {};     // error: copy-list-initialization selected explicit D()
Agg a = {};    // error: member d is copy-initialized from an empty list, same reason
```

## User-defined conversions [over.match.copy]

### Only one user-defined conversion ([over.match.funcs.general] ¶6)

A **user-defined conversion** is a type conversion performed by calling a converting constructor or a conversion function. ¶6 Except for list-initialization, an implicit conversion sequence contains at most one user-defined conversion, so dedicated rules are needed to pick one among several possible user-defined conversions.

```cpp error
struct T { T(); };
struct C : T { C(int); };
T a = 1;   // error: T(C(1)) is not considered
```

`1` to `C` is one user-defined conversion and `C` to `T` is a derived-to-base conversion, which looks like only one step short. But the candidates for `T a = 1` are the non-explicit constructors of `T`, and initializing the `const T&` parameter of the copy constructor from `1` would require constructing a `C` first, and [[over.best.ics#4]] says user-defined conversions aren't considered there.

### Constructors and conversion functions compete together (¶1–¶2)

¶1 When an object of type `cv1 T` (`T` a class) is copy-initialized and the initializer's type isn't `T` or a class derived from it, there are two kinds of candidates:

- ¶1.1 the non-explicit constructors of `T`;
- ¶1.2 if the initializer's type is a class `cv S`, also the conversion functions of `S`, provided they yield `T` or a class derived from `T`.

¶2 The argument list has one argument, the initializer. It is compared against the first parameter of a constructor, or against the object parameter of a conversion function.

```cpp error
struct S;
struct T  { T();  T(const S&); };
struct S  { operator T(); };          // non-const
struct S2;
struct T2 { T2(); T2(const S2&); };
struct S2 { operator T2() const; };   // const

void use() {
  S s;
  T t = s;      // OK: chooses S::operator T()
  S2 s2;
  T2 t2 = s2;   // error: ambiguous
}
```

In `T t = s`, binding `s` to the conversion function's implicit object parameter `S&` is better than binding it to the constructor's `const S&`. In `T2 t2 = s2`, the argument binds to `const S2&` for both candidates, and they can't be distinguished. This is what happens when the same conversion is written twice (once as a constructor, once as a conversion function); keep only one.

### Which conversion functions are candidates ([over.match.funcs.general] ¶7)

¶7 Whenever the conversion functions of a class `S` are considered for initializing an object or reference of type `T`, the candidates include the result of looking up `operator T` in `S`, which may be specializations deduced from conversion function templates. In addition, each non-template conversion function of `S` is a candidate if:

- ¶7.1 it isn't hidden within `S`;
- ¶7.2 it yields a **[[g:permissible-type|permissible type]]**;
- ¶7.3 for the non-explicit set, it isn't itself explicit.

Each context specifies the permissible types for explicit and non-explicit conversion functions separately: [over.match.copy] above, and [over.match.conv] and [over.match.ref] below. When initializing an object, if `cv U` is a permissible type, so are `cv2 U`, `cv2 U&` and `cv2 U&&`, so a conversion function returning `const U&` can also be used to initialize a `U` object. When the set of permissible types for explicit conversion functions is empty, all explicit candidates are discarded.

### An exception for explicit conversion functions (¶1.2)

In [over.match.copy], explicit conversion functions normally have no permissible types. The only exception: when a `cv3 T` object is direct-initialized and a constructor is called with a single argument, so that a temporary has to be initialized to bind to the constructor's `cv2 T&` first parameter, explicit conversion functions have the same permissible types as non-explicit ones.

```cpp run ok
struct U {};
struct V { explicit operator U() const { return {}; } };
int main() {
  V v;
  U u(v);    // OK: direct-initialization selects U's copy or move constructor;
             //     the temporary bound to the parameter is initialized by explicit operator U()
  (void)u;
}
```

`U u(v)` is an explicitly written direct-initialization; the programmer has already expressed the intent to convert `v` to `U`, so explicit conversion functions are allowed to take part, as with `static_cast<U>(v)`.

## Conversion to a non-class type [over.match.conv]

¶1 When an object of non-class type `cv T` is initialized from an expression of class type, as in `int i = obj;` or `double d(obj);`, the candidates are conversion functions:

- permissible types for non-explicit conversion functions: types that can be converted to `T` via a standard conversion sequence;
- permissible types for explicit conversion functions: only in direct-initialization, types that can be converted to `T` with a (possibly trivial) qualification conversion; that is, the result must be exactly `T`, up to cv-qualification.

¶2 The argument list has only the initializer, compared against the conversion function's object parameter.

When two conversion functions tie on the object argument, the second standard conversion sequence from the conversion result to the target type is compared ([[over.match.best#2.2]]):

```cpp error
struct A {
  operator int();
  operator double();
} a;
int   i = a;   // OK: no conversion needed after operator int()
float x = a;   // error: ambiguous: int to float and double to float both have Conversion rank
long  l = a;   // error: ambiguous: same reason
```

An explicit conversion function can only convert exactly to the target type, which is why `explicit operator bool` works in `if (p)` but doesn't silently turn into `int`. The condition of an `if` is contextually converted to `bool`, defined as the direct-initialization `bool t(p);`:

```cpp error
struct P { explicit operator bool() const { return true; } };
void use(P p) {
  if (p) {}     // OK: equivalent to the direct-initialization bool t(p)
  bool b1(p);   // OK: direct-initialization
  bool b2 = p;  // error: copy-initialization; the explicit conversion function isn't a candidate
  int  n(p);    // error: direct-initialization, but bool to int is an integral promotion, not a qualification conversion
}
```

## Binding a reference directly to a conversion result [over.match.ref]

¶1 Per [[dcl.init.ref]], a reference can be bound directly to the result of a conversion function, without a temporary. Let the reference being initialized be a reference to `cv1 T`:

- To bind to an lvalue, conversion functions yielding lvalue reference types are considered; to bind to an rvalue, conversion functions yielding non-reference types or rvalue reference types are considered.
- Permissible types for non-explicit conversion functions: those of the above types whose referenced type `cv2 T2` is reference-compatible ([[dcl.init.ref]]) with `cv1 T`, that is, `T2` is `T` or a class derived from it and has no more cv-qualification than `cv1`.
- Permissible types for explicit conversion functions: only in direct-initialization, requiring that `T2` can be converted to `T` with a qualification conversion.

¶2 The argument list has only the initializer.

```cpp run ok
struct Base {};
struct Derived : Base {};
struct Holder {
  Derived d;
  operator Derived&() { return d; }
};
int main() {
  Holder h;
  Base& r = h;                  // direct binding: operator Derived&() yields a Derived lvalue
  return &r == &h.d ? 0 : 1;    // r is bound to h.d itself, no temporary
}
```

If the conversion function returned by value, `operator Derived()`, `const Base& r = h` would bind to a temporary, and `Base& r = h` would be ill-formed, since a non-const lvalue reference can't bind to an rvalue. Cases where direct binding isn't possible are handed to [[over.match.copy]] or [[over.match.conv]] to initialize a temporary.

## List-initialization [over.match.list]

¶1 When a non-aggregate class type `T` is list-initialized, constructors are selected in two phases:

- ¶1.1 Phase one: if the initializer list is non-empty, or `T` has no default constructor, the candidates are only the **initializer-list constructors** of `T`, that is, constructors whose first parameter is `std::initializer_list<E>` (or a reference to it) and whose other parameters all have default arguments ([[dcl.init.list]]). The whole initializer list is a single argument.
- ¶1.2 Phase two: if the list is empty and there is a default constructor, or phase one found no viable function, the candidates are all constructors of `T`, and the argument list consists of the elements of the initializer list.

### What's inside the braces is preferably taken as elements

As long as one initializer-list constructor is viable, phase two is never reached, even if other constructors would match better:

```cpp run ok
#include <vector>
#include <cassert>
int main() {
  std::vector<int> a(3);      // vector(size_type): three 0s
  std::vector<int> b{3};      // phase one: initializer_list<int> is viable, one element 3
  std::vector<int> c(3, 1);   // three 1s
  std::vector<int> d{3, 1};   // two elements, 3 and 1
  assert(a.size() == 3 && b.size() == 1 && c.size() == 3 && d.size() == 2);
}
```

If all constructors were compared together, in `vector<double>{3}` both `int` to `double` and `int` to `size_t` have Conversion rank and the result would be ambiguous; with another element type the result might be a different surprise. The two-phase rule gives a simple, predictable guarantee: what's inside the braces is preferably taken as elements. The price is the well-known difference between `(3)` and `{3}`.

The bar for viability is low. Narrowing doesn't make an initializer-list constructor non-viable; narrowing is checked only after the selection:

```cpp error
#include <vector>
std::vector<int> v{1.5};   // error: initializer_list<int> is selected, and double to int is narrowing
```

Phase one comes up empty only when the elements can't be implicitly converted to `E` at all:

```cpp run ok
#include <vector>
#include <string>
#include <cassert>
int main() {
  std::vector<std::string> v{3};   // 3 can't convert to string, so phase two
  assert(v.size() == 3);           // selects vector(size_type)
}
```

When the list is empty and there is a default constructor, phase two is entered directly. In practice [[dcl.init.list#3.5]] has already turned this case into value-initialization before this point:

```cpp run ok
#include <initializer_list>
struct S {
  int which;
  S() : which(0) {}
  S(std::initializer_list<int>) : which(1) {}
};
int main() {
  S a{};     // default constructor
  S b{{}};   // the list is non-empty and the element {} converts to int: initializer_list constructor
  return a.which == 0 && b.which == 1 ? 0 : 1;
}
```

### Copy-list-initialization and explicit

!!! std
    "In copy-list-initialization, if an explicit constructor is chosen, the initialization is ill-formed."

    If copy-list-initialization selects an explicit constructor, the initialization is ill-formed.

This differs from [over.match.ctor] and [over.match.copy], where copy-initialization doesn't consider explicit constructors as candidates at all. Copy-list-initialization does consider them, and only raises an error once one is selected (Note 1):

```cpp error
struct X {
  explicit X(int);
  X(double);
};
X a = 1;     // OK: copy-initialization considers only non-explicit constructors, selects X(double)
X b{1};      // OK: direct-list-initialization selects X(int)
X c = {1};   // error: copy-list-initialization selected explicit X(int)
```

The difference between `X a = 1` and `X c = {1}` is intentional. If `= {1}` also removed explicit constructors, it would silently use `X(double)` instead. By marking `X(int)` explicit, the author meant to forbid using it implicitly, not to have the compiler pick a different constructor. An error is safer than a silent switch.

Note 1 also says this restriction applies only if this initialization is part of the final result of overload resolution. When a conversion sequence is being formed for a parameter of another function, selecting an explicit constructor doesn't make that function non-viable ([[over.ics.list]]); see [[over.match.viable]] for an example.

## Template candidates and excluded candidates [over.match.funcs.general]

### Template candidates (¶8)

¶8 When a candidate is a function template, template argument deduction ([[temp.over]], [[temp.deduct]]) generates specializations that become candidates. A template for which deduction fails produces no candidate: it isn't non-viable, it simply isn't in the candidate set. After deduction, the parameter types of the specialization are fully determined, and from then on, unless specified otherwise, a specialization is treated like a non-template function (footnote 92). Being a template matters again only in the final tie-breakers ([[over.match.best#2.4]], [[over.match.best#2.5]]).

When the `explicit(condition)` of a constructor template or conversion function template depends on template arguments, deduction comes first, then whether the resulting specialization is explicit is checked. If the context accepts only non-explicit candidates and the specialization is explicit, it is removed from the candidate set. That is why conditionally explicit constructors such as those of `std::pair` and `std::optional` need only one template:

```cpp error
#include <type_traits>
struct W {
  template<class U>
  explicit(!std::is_convertible_v<U, int>) W(U) {}
};
struct P { explicit operator int() const { return 0; } };
W a = 1;      // OK: int implicitly converts to int, so the specialization isn't explicit
W b(P{});     // OK: direct-initialization; explicit candidates are usable too
W c = P{};    // error: the specialization is explicit and is removed from the copy-initialization candidate set
```

### Two kinds of functions that aren't candidates (¶9)

¶9 Two kinds of functions never enter the candidate set, in any context:

1. a defaulted move constructor or move assignment operator that is defined as deleted;
2. a constructor inherited from a base class `C` whose first parameter is a reference to `cv1 P`, when constructing an object of type `cv2 D` with exactly one argument, where `C` is reference-related to `P` and `P` is reference-related to `D`. Intuitively: an inherited constructor that looks like a copy or move constructor can't be used to copy or move a derived class object.

```cpp run ok
#include <cstdio>
struct A {
  A() {}
  A(A&&) { std::puts("#2"); }
  template<class T> A(T&&) { std::puts("#3"); }
};
struct B : A {
  using A::A;
  B(const B&) { std::puts("#4"); }
  B(B&&) = default;   // #5: member x isn't movable, so this is defined as deleted
  struct X { X() {} X(X&&) = delete; } x;
};
int main() {
  B b1;
  B b2 = static_cast<B&&>(b1);   // prints #4
}
```

- #5 is defined as deleted and by item 1 isn't a candidate. Otherwise it would be an exact match for the rvalue, be selected, and then be reported as a use of a deleted function. With it excluded, the copy constructor #4 takes over, so non-movable types automatically fall back to copying.
- #2 and #3 (with `T` deduced as `B`) are inherited constructors whose first parameters both refer to types reference-related to `B`, so by item 2 they aren't candidates. Otherwise #3's `B&&` would be an exact match, and the derived class object would be constructed by the base class's forwarding constructor, initializing only the base class subobject.

Clang 23 gives a `-Wdefaulted-function-deleted` warning for #5 in our tests; the program compiles and prints `#4`.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[over.match.funcs.general] ¶1: the transformations the subclauses apply to source code (rewriting `a->f()` as `(*a).f()`, rewriting operators as function calls, constructing surrogate call functions, and so on) are only a means of describing overload resolution; implementations need not actually perform them.

[over.call.object] footnote 95: surrogate call functions may be indistinguishable from each other (identical declarations, or differing only in the return type); the call is then ambiguous.

</details>

## History

!!! history
    - C++98 already had the implicit object parameter, the contrived object, surrogate call functions, and the various candidate sets for constructors and conversion functions.
    - C++11 added ref-qualifiers (the implicit object parameter can be an rvalue reference), list-initialization and its two-phase resolution, explicit conversion functions, and the rule that defaulted move operations defined as deleted aren't candidates.
    - C++17 switched to the new model of inheriting constructors and added the rule that inherited constructors that look like copy or move constructors aren't candidates.
    - C++20 added conditional explicit (`explicit(bool)`) and its deduce-first, then-remove rule.
    - C++23 added explicit object parameters ([[P0847R7]]).
    - C++26 allows a *splice-expression* to designate the candidate set, and prohibits calling non-static member functions through an implicit `this` in constructor preconditions and destructor postconditions.

## Common misconceptions

!!! pitfall "`vector<int>{n}` has n elements"
    Braces prefer the `initializer_list` constructor, so `vector<int>{n}` has one element. For n elements, use parentheses. In generic code `T{args...}` and `T(args...)` can mean completely different things, which is why factory functions like `std::make_unique` consistently use parentheses.

!!! pitfall "Copy-list-initialization skips explicit constructors"
    It doesn't. `X x = {1};` selects the explicit constructor and then fails, instead of using a non-explicit one.

!!! pitfall "Writing both a constructor and a conversion function is safer"
    When `T(const S&)` and `S::operator T() const` both exist, `T t = s;` is ambiguous. Making one of them win by removing `const` relies on details of reference binding, which is fragile and obscure. Keep only one.

## Questions

!!! question "Question 1"
    In `struct S { void f() const; static void f(int); };`, which function does `s.f(1)` select (where `s` is a non-const lvalue of type `S`)? Since the static function has no real object parameter, does that create an ambiguity?

<details markdown="1">
<summary>Answer</summary>

Only the static `f(int)` is viable; `f() const` has the wrong number of arguments. Here the static member function is considered to have an implicit object parameter that matches any object (¶2.2, ¶4); the object argument `s` corresponds to it, and no conversion sequence is computed. If both candidates were viable, the static function would be neither better nor worse than the other on the object argument ([[over.best.ics#8]]), and the comparison would depend entirely on the other arguments.
</details>

!!! question "Question 2"
    Why is the code below ill-formed? How can changing a single character make it well-formed?
    ```cpp
    #include <initializer_list>
    struct A { A(std::initializer_list<int>); explicit A(int, int); };
    A a = {1, 2.5};
    ```

<details markdown="1">
<summary>Answer</summary>

In phase one `A(initializer_list<int>)` is viable, since `2.5` can be implicitly converted to `int`; narrowing doesn't affect viability. It is selected, and then `2.5` to `int` turns out to be narrowing, which is ill-formed ([[dcl.init.list#3.7]]). Change it to `A a = {1, 2};`. Even if phase one came up empty, selecting `explicit A(int, int)` in phase two would be equally ill-formed in copy-list-initialization.
</details>
