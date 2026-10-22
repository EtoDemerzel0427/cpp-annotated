---
title: Explicit object parameters (P0847)
summary: C++23 lets a member function write the object it is called on as a first parameter marked with this, so the object's type, constness and value category can be deduced. The duplicated code it targets, the syntaxes and lookup rules the proposal compared, why the final design gives the body no this, makes taking the address yield an ordinary function pointer and forbids virtual, the hidden problems of deducing a derived type, and how the standard library uses it.
tags: deducing this, explicit object parameter, member functions, CRTP, lambda, proposal, C++23
group: Core language
updated: 2026-10-19
---

!!! tldr
    - The `const`, `&` and `&&` qualifiers of a member function can only be written out one at a time, so an accessor has to be written four times. P0847R7 makes the object a written-out parameter `this Self&& self`, which can be deduced like an ordinary function template parameter, so one piece of code covers all four cases.
    - The proposal compared four syntaxes and three lookup rules for the function body, and settled on: `this` written before the first parameter; no `this` in the function body and no implicit member access, with everything going through `self`.
    - From the outside such a function is a non-static member function (called with `obj.f()`, cannot be written `static`); from the inside it looks like a static member function (`&C::f` is an ordinary function pointer). For now it cannot be `virtual`.
    - `Self` deduces to the derived class. That is why it can replace some uses of CRTP, and also its main trap: `self.x` may find a same-named member in the derived class. The standard library's member `visit` avoids this with a C-style cast back to the base.
    - It is a pure extension, with no Annex C entry. A series of CWG fixes completed the rules afterwards; the question of overriding virtual functions (CWG2554) is still open.

## The same function written four times

C++11 added ref-qualifiers to member functions: `f() &` can only be called on lvalues, `f() &&` only on rvalues. Together with `const`, which C++98 already had, an accessor that wants to forward the value category of the object ([[g:value-category|value category]], see [[topics/value-categories]]) as-is needs four overloads. That is exactly how `std::optional::value()` is specified:

```cpp title="before.cpp" run ok
#include <stdexcept>
#include <utility>

template<class T>
class opt {
  T v_; bool has_ = true;
public:
  T& value() & {
    if (!has_) throw std::logic_error("empty");
    return v_;
  }
  const T& value() const& {
    if (!has_) throw std::logic_error("empty");
    return v_;
  }
  T&& value() && {
    if (!has_) throw std::logic_error("empty");
    return std::move(v_);
  }
  const T&& value() const&& {
    if (!has_) throw std::logic_error("empty");
    return std::move(v_);
  }
};
int main() { opt<int> o; o.value() = 1; }
```

The four function bodies differ only in types and `std::move`. A common shortcut is to have three of the overloads call the fourth with a `const_cast` in between, or have them all call a private static function template, passing `*this` as an argument. The latter already shows where the problem lies: for an ordinary function, a forwarding reference `Opt&&` deduces all four cases in one go; only the object a member function is called on cannot be deduced like that.

That object has long been a parameter in overload resolution. The standard calls it the **implicit object parameter** ([[g:implicit-object-parameter|implicit object parameter]], [[over.match.funcs.general#2]]), and its type is determined by the qualifiers after the function: "lvalue reference to cv `X`" with no ref-qualifier or with `&`, and an rvalue reference with `&&` ([[over.match.funcs.general#4]]). The only problem is that it cannot be written out, so it cannot be a template parameter.

Two other things are stuck at the same point. Inside a lambda body no name refers to the closure object itself, so you cannot write a directly recursive lambda ([[topics/lambdas]]). A base class that wants the type of the derived class has to receive the derived class as a template argument, which is CRTP ([[patterns/crtp]]).

## The core of the proposal: write the object parameter out

[[P0847R7]] allows `this` before the first parameter of a non-static member function. That parameter is called the **explicit object parameter** ([[g:explicit-object-parameter|explicit object parameter]]); in a call, the object expression is its argument, and the first argument in parentheses corresponds to the second parameter ([[expr.call#7]]). Its type can be a template parameter, deduced by the ordinary rules of function template argument deduction ([[temp.deduct.call]]):

<div class="compare" markdown="1">

```cpp
// C++20: four overloads
T& value() &;
const T& value() const&;
T&& value() &&;
const T&& value() const&&;
```

```cpp
// C++23: one template
template<class Self>
auto&& value(this Self&& self) {
  if (!self.has_) throw /* … */;
  return std::forward<Self>(self).v_;
}
```

</div>

`Self&&` is a forwarding reference ([[g:forwarding-reference|forwarding reference]]). Called on a `const` lvalue, `Self` deduces to `const opt&`; called on an rvalue, it deduces to `opt`. The value category and constness of `std::forward<Self>(self).v_` therefore follow the object:

```cpp title="after.cpp" run ok
#include <cstdio>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <utility>

template<class T>
class opt {
  T v_{};
  bool has_ = true;
public:
  template<class Self>
  auto&& value(this Self&& self) {
    if (!self.has_) throw std::logic_error("empty");
    return std::forward<Self>(self).v_;
  }
};

int main() {
  opt<std::string> o;
  const opt<std::string>& c = o;
  static_assert(std::is_same_v<decltype(o.value()), std::string&>);
  static_assert(std::is_same_v<decltype(c.value()), const std::string&>);
  static_assert(std::is_same_v<decltype(std::move(o).value()), std::string&&>);
  static_assert(std::is_same_v<decltype(std::move(c).value()), const std::string&&>);
  o.value() = "hello";
  std::string s = std::move(o).value();     // moved out
  std::printf("[%s] [%s]\n", s.c_str(), c.value().c_str());   // [hello] []
}
```

The proposal's abstract is a single sentence: provide a way to tell, from within a member function, whether the expression it is called on is an lvalue or an rvalue, whether it is const, and what its type is. Every decision in the following sections answers the question: now that the object is an ordinary parameter, how must the other rules change?

## The design space

### Syntax: four candidates

R0 put `this` in the middle of the parameter declaration, as `X& this self`. Later revisions listed four syntaxes ([[P0847R7]] §6.5 keeps this history):

```cpp
// Candidate syntaxes compared by the proposal; only #1 is C++ today
struct A {
  int get(this A const& a) { return a.i; }   // #1 first parameter marked with this
  int get(A const& this) { return this.i; }  // #2 a parameter named this
  int get() A const& self { return self.i; } // #3 trailing object type and name
  int get() A const& { return this->i; }     // #4 trailing object type
  int i;
};
```

#3 and #4 put the type where `const &` goes today, which looks closest to the old syntax, but both have fatal flaws. #3 has parsing problems; #4 has no name, so the function body still has to use `this`, whose type would have to vary with the deduction result, and lambdas would have nowhere to put the type. Neither can express passing the object by value. #2 gives the parameter's name semantic meaning and turns `this` from a pointer into an object, conflicting with what capturing `this` means in a lambda. #1 has none of these problems; it is the optional `this` in front of *parameter-declaration* in the grammar of [[dcl.fct#2]].

### Is there still a this in the function body

The object parameter can deduce to a derived class, which makes name lookup inside the function body subtle. The proposal compared three rules using the same example:

```cpp
struct B {
  int i = 0;
  template<class Self> auto&& f1(this Self&&)      { return i; }
  template<class Self> auto&& f2(this Self&&)      { return this->i; }
  template<class Self> auto&& f5(this Self&& self) { return std::forward<Self>(self).i; }
};
struct D : B { double i = 3.14; };   // hides B::i
```

| Option | `this` | Implicit member access `i` | Result |
|---|---|---|---|
| 1 | Not available | Not available | Only `f5` is well-formed; `D().f5()` returns `D::i` |
| 2 | Available, points to the `B` subobject | Not available | `f2` always returns `B::i`, but the constness of `this` has to vary with `Self`, making it a dependent type |
| 3 | Available | Available (as in C++17) | `f1` is the same as `f2` |

Option 1 was chosen. The reason is that it gives the simplest model: a function with an explicit object parameter is a static function with a more convenient call syntax, and the only object in the function body is the parameter that was written out. The cost is just as clear: the author has to guard against `Self` being a derived class (see "Deducing a derived type" below).

That is today's rule. `this` only refers to the object of an implicit object member function ([[expr.prim.this#1]]) and cannot appear in the declaration of an explicit object member function ([[expr.prim.this#4]]). Using a non-static member without qualification would normally be rewritten as `(*this).m`; in an explicit object member function that rewrite is ill-formed (the note in [[expr.prim.id.general#2]]):

```cpp title="no-this.cpp" error
struct B {
  int i = 0;
  void g();
  template<class Self> auto&& f1(this Self&&) { return i; }        // error: no implicit this->i
  template<class Self> auto&& f2(this Self&&) { return this->i; }  // error: no this
  void f3(this B& self) { g(); }                                   // error: g needs an object
  void f4(this B& self) { self.g(); }                              // OK
};
```

### Static or non-static

Option 1 makes such a function look like a static member function from the inside, yet from the outside it must look like a non-static member function: it is called with `obj.f()` and its name cannot be used on its own. The proposal compared the three kinds of function side by side:

| | Ordinary non-static | Explicit object | Static |
|---|---|---|---|
| Needs an object argument | Yes | Yes | No |
| Implicit `this` in the body | Yes | No | No |
| Can declare operators | Yes | Yes | No |
| Type of `&C::f` | Pointer to member function | Function pointer | Function pointer |
| `auto f = x.f;` | No | No | Yes |
| Can be `virtual` | Yes | To be decided | No |

If it were classified as a static member function, something would have to be decided about the `static` keyword: either optional, in which case writing it means nothing; or required, in which case a lambda would have to be written `[](this auto self) static {…}`. Neither is good. From R6 on, the proposal defined it as a non-static member function instead, and named the two kinds of non-static member function: those with an explicit object parameter are **explicit object member functions** ([[g:explicit-object-member-function|explicit object member function]]), and the rest are implicit object member functions ([[dcl.fct#8]]). The object parameters of both are collectively called **object parameters** ([[g:object-parameter|object parameter]], [[dcl.fct#9]]). The authors also pointed out that rules applying to both kinds of non-static member function far outnumber rules applying to both static functions and the new functions, and that treating them as non-static required less wording change.

Another question came up during implementation: should calling an explicit object member function from an implicit object member function without `this->` be allowed? The proposal's answer is yes, on the grounds that users of a class should not be affected by how it is implemented. A class derived from `std::optional<int>` that writes `value()` in a member function should compile no matter how the standard library implements `value`:

```cpp title="implicit-call.cpp" run ok
#include <cstdio>
#include <optional>

struct C {
  int v = 7;
  int get(this const C& self) { return self.v; }
  int twice() const { return get() * 2; }     // implicit (*this).get()
};

struct Big : std::optional<int> {
  using std::optional<int>::optional;
  bool is_big() const { return value() > 42; }   // no need to know how value() is implemented
};

int main() {
  std::printf("%d %d\n", C{}.twice(), Big{50}.is_big());   // 14 1
}
```

This rule lives in [[over.call.func#3]]: when a member function is called without qualification inside a member of the class, the implied object argument is `(*this)`, regardless of which kind the called function is.

### What taking the address gives

Taking the address of an implicit object member function gives a pointer to member function. For explicit object member functions there were two choices; the proposal first chose pointer to member function and later changed to an ordinary function pointer.

The reason is by-value object parameters. `int h(this Y, int)` has no counterpart in the old language, so `&Y::h` can only be a function pointer. If `int g(this const Y&, int)` gave a pointer to member function instead, the same syntax would produce two different kinds of type, and whether a template instantiation yields a member function or a free function would depend on the arguments. Once unified as function pointers, these functions are, after taking their address, ordinary functions taking the object as their first argument:

```cpp title="pointer.cpp" run ok
#include <cstdio>
#include <functional>
#include <type_traits>

struct Y {
  int v = 10;
  int f(int a) const& { return v + a; }
  int g(this const Y& self, int a) { return self.v + a; }
};
static_assert(std::is_same_v<decltype(&Y::f), int (Y::*)(int) const&>);
static_assert(std::is_same_v<decltype(&Y::g), int (*)(const Y&, int)>);

int main() {
  Y y;
  auto pf = &Y::f;
  auto pg = &Y::g;
  std::printf("%d %d\n", (y.*pf)(1), pg(y, 2));        // 11 12
  std::printf("%d %d\n", std::invoke(pf, y, 3),
                         std::invoke(pg, y, 4));        // 13 14
}
```

The corresponding wording is in three places. `&` applied to an explicit object member function gives "pointer to T" rather than a pointer to member, and the operand must be the qualified name `&Y::g` ([[expr.unary.op#3]]). When taking the address of an overload set, explicit object member functions match a target of function pointer type ([[over.over#4]]). Conversely, `(y.*pg)(1)` is ill-formed, and `y.g` cannot be used on its own without being called.

### Can it be virtual

No ([[dcl.fct#7]]). The proposal discussed two obstacles. The first is a semantic difference: `B::f()` without a ref-qualifier can be called on rvalues, while `this D&` does not accept rvalues. The second, bigger problem is the calling convention: an explicit object member function uses the same calling convention as a free function, so virtual dispatch would require either generating a forwarding thunk, generating the function twice under both conventions, or introducing a new pointer-to-member type that can represent by-value object parameters.

The proposal considered that allowing `virtual` would bring no new capability, only a stylistic choice, so it is forbidden for now with the door left open: if it is allowed in the future, only functions of the same kind may override each other, so explicit object member functions would only override explicit object member functions.

To make sure the door really stays open, the proposal states explicitly that `struct D3 : B3 { void f(this D3&); };` is well-formed: it only hides `B3::f` and does not override it. Under the current draft, the object parameter of `D3::f` with the reference removed is `D3`, which differs from `B3` for `B3::f`, so the two do not correspond ([[basic.scope.scope#3]]) and there is no overriding ([[class.virtual#2]]). Clang 23, however, reports "an explicit object parameter cannot appear in a virtual function". The override determination itself has an open issue, [[CWG2554]] (currently in review): it points out that the correspondence rule in [[basic.scope.scope#3]] even gets wrong whether `struct D : B { void f(); }` overrides `B::f`, and the proposed fix is to ignore explicit object parameters in the comparison, under which `D3::f` would override `B3::f` and therefore be ill-formed. Question 3 on [[dcl.fct]] discusses the same example.

### By-value object parameters

The written-out parameter need not be a reference. The proposal gives three uses:

- A function like `sorted(this my_vector self)` naturally works on a copy; an rvalue object is moved straight in, with no template needed.
- Passing small objects by value saves an indirection. The implicit object parameter is always a reference, so a member function of a type like `string_view` that is not inlined must first load data through a pointer.
- A member function coroutine that takes the object by value stores a copy in the coroutine frame, which does not dangle the way `this` can.

The second point can be seen directly. The two functions below are defined outside the class and compiled with `-O2`:

```cpp title="by-value.cpp" ok
#include <cstddef>
struct View {
  const char* p;
  std::size_t n;
  std::size_t size_ref() const;
  std::size_t size_val(this View self);
};
std::size_t View::size_ref() const { return n; }
std::size_t View::size_val(this View self) { return self.n; }
```

Clang 23 (arm64) generates `ldr x0, [x0, #8]` for `size_ref`, reading `n` from the memory `this` points to, and `mov x0, x1` for `size_val`, where both members are passed in directly in registers. This depends on the platform's calling convention; a 16-byte struct is passed in registers on AArch64.

### Deducing only the qualifiers is not possible

Most of the time the author only wants to deduce constness and value category, not the derived type. But `Self&&` also deduces derived classes, with two side effects: the hiding problem described below, and a separate instantiation for each derived class. The proposal acknowledges this in its FAQ, and considers restricting what is deduced to be a feature orthogonal to this proposal: free function templates have long had the same need, and it should be solved in general rather than with a separate set of rules for object parameters.

## Wording

!!! std
    An *explicit-object-parameter-declaration* is a *parameter-declaration* with a `this` specifier. ([[dcl.fct#7]])

    A parameter declaration with the `this` specifier is an explicit object parameter declaration. It can only be the first parameter of a member function or lambda, and the function cannot have cv- or ref-qualifiers and cannot be `static` or `virtual`.

P0847R7's wording is spread over five clauses; here it is organized by location in the current draft. The individual rules are on each subclause's page, and [[dcl.fct]] has full explanations and examples.

| Subclause | Change |
|---|---|
| [[dcl.fct#2]] | `this` may precede a parameter declaration |
| [[dcl.fct#7]]–[[dcl.fct#10]] | Where it may appear and restrictions; defines explicit object parameter, explicit/implicit object member function, object parameter, non-object parameter |
| [[basic.scope.scope#3]] | When two member functions have corresponding object parameters, which decides whether `void f() const&;` and `void f(this const X&);` are redeclarations |
| [[expr.prim.this#1]], [[expr.prim.this#4]] | `this` belongs only to implicit object member functions |
| [[expr.call#7]] | The object expression becomes the first argument |
| [[expr.unary.op#3]], [[over.over#4]] | Taking the address gives a function pointer |
| [[over.match.funcs.general#2]] | Only implicit object member functions are additionally assumed to have an implicit object parameter |
| [[over.best.ics.general#9]] | Conversion to an implicit object parameter only allows standard conversions; a note says conversion to an explicit object parameter can use user-defined conversions |
| [[expr.prim.lambda.closure#6]], [[expr.prim.lambda.closure#7]] | For a lambda with captures, the object parameter must be the closure type or derived from it; a call operator with an explicit object parameter is not `const` |
| [[class.mfct.non.static#3]] | Only implicit object member functions can be virtual |

There is also a feature-test macro, `__cpp_explicit_this_parameter`, currently `202110L` ([[cpp.predefined]]).

`this` was already a keyword and could never appear at the start of a parameter declaration, so this is a pure extension; no old code changes meaning.

## Consequences

### Deducing a derived type: the hiding problem

All member access in the function body goes through `self`, and the static type of `self` may be a derived class. If the derived class has a member of the same name, `self.i` finds the derived class's one:

```cpp title="shadow.cpp" run ok
#include <cstdio>
#include <utility>

struct B {
  int i = 1;
  template<class Self>
  auto&& get(this Self&& self) {
    return std::forward<Self>(self).i;        // look up i starting from Self
  }
  template<class Self>
  auto&& get_b(this Self&& self) {
    return std::forward<Self>(self).B::i;     // fixed to B::i
  }
};

struct D : B {
  double i = 2.5;                             // hides B::i
};

int main() {
  D d;
  std::printf("%g\n", static_cast<double>(d.get()));    // 2.5
  std::printf("%d\n", d.get_b());                       // 1
  std::printf("%d\n", static_cast<B&>(d).get());        // 1
}
```

This is not overriding in the virtual-function sense; the result depends on the static type of the object at the call site. In mixin and CRTP-style uses this is exactly the desired behavior; in a function like `optional::value` that only wants to deduce qualifiers, it is a defect. Writing `self.B::i` pins it to the base-class member.

The proposal calls the worst case the private inheritance problem: a derived class inherits privately from the base and then makes the base's function public with a using-declaration. Then `Self` is `D`, and the conversion from `D` to `B` is not accessible in `B`'s member function, so `self.B::i` is ill-formed too:

```cpp title="private-base-bad.cpp" error
#include <utility>
class B {
  int i = 1;
public:
  template<class Self>
  auto&& get(this Self&& self) {
    return std::forward<Self>(self).B::i;
  }
};
struct D : private B {
  double i = 2.5;
  using B::get;
};
int main() {
  D d;
  d.get();   // error: conversion from D to private base B is inaccessible
}
```

The proposal's solution is a C-style cast. When a C-style cast converts a derived class to an unambiguous base class, the accessibility of the base is not checked ([[expr.cast#4.6]]). First use `std::forward_like` to compute the reference-to-`B` type carrying `Self`'s constness and value category, then cast to it:

```cpp title="private-base.cpp" run ok
#include <cstdio>
#include <type_traits>
#include <utility>

class B {
  int i = 1;
public:
  template<class Self>
  auto&& get(this Self&& self) {
    // B with Self's constness and value category: B&, const B&, B&&, ...
    using Base = decltype(std::forward_like<Self>(std::declval<B&>()));
    return ((Base)self).i;   // a C-style cast does not check base accessibility
  }
};

struct D : private B {
  double i = 2.5;
  using B::get;
};

int main() {
  D d;
  static_assert(std::is_same_v<decltype(d.get()), int&>);
  static_assert(std::is_same_v<decltype(std::move(d).get()), int&&>);
  std::printf("%d\n", d.get());   // 1
}
```

!!! pitfall "Treating `this auto&& self` as a drop-in replacement for `this`"
    Mechanically changing `this->m` in old code to `self.m` keeps the behavior as long as there is no derived class; once some derived class defines a member `m` of its own, the result changes, and the compiler gives no hint. When you only want to deduce the qualifiers, access members as `self.Base::m`, or cast back to the base first as above.

### How the standard library uses it

`std::forward_like` ([[P2445R1]], C++23) is a library facility the proposal assumed would exist but did not propose itself. `std::forward<decltype(self)>(self).m` only works for real members; a lambda's captures are not members accessible through `self.`, and "far away" data behind pointers or in containers does not follow the object's value category either. `forward_like<T>(x)` merges `T`'s constness into `x` and then takes `T`'s value category ([[forward#6]]):

```cpp title="forward-like.cpp" run ok
#include <cstdio>
#include <string>
#include <utility>

void submit(const std::string&) { std::puts("copy"); }
void submit(std::string&&)      { std::puts("move"); }

int main() {
  auto cb = [m = std::string("msg")](this auto&& self) {
    submit(std::forward_like<decltype(self)>(m));
  };
  cb();              // copy: lvalue closure, can be called again
  std::move(cb)();   // move: rvalue closure, last use
}
```

P2445R1 says this was the earliest use case for deducing this: the same callback can be passed both to an algorithm that retries (calling it as an lvalue) and to an algorithm that calls it only once (calling it as an rvalue, moving the capture out).

C++26's member `variant::visit` ([[P2637R3]]) is a member function in the standard declared with an explicit object parameter. Its *Effects* are written as `std::visit(std::forward<Visitor>(vis), (V)self)`, where `V` is a reference to `variant` carrying `Self`'s constness and value category ([[variant.visit#9]]–[[variant.visit#11]]). The C-style cast here is deliberate: the proposal explains that `variant` may be a private base of `Self`, which the non-member `std::visit` does not support, and the Library Evolution Working Group wanted the member `visit` to support it. This is exactly the private inheritance problem from the previous section and its solution.

```cpp title="member-visit.cpp" ok
#include <cstdio>
#include <variant>

struct Shape : private std::variant<int, double> {
  using variant::variant;
  using variant::visit;          // member visit: C++26
};

int main() {
  Shape s = 2.5;
  s.visit([](auto x) { std::printf("%g\n", static_cast<double>(x)); });   // 2.5
}
```

By the standard this code is well-formed. The libc++ that ships with Clang 23 rejects it: libc++ implements this conversion with `static_cast` and reports "cannot cast 'Shape' to its private base class".

On the other hand, `value()` and `operator*` of `std::optional` are still four overloads in the current draft ([[optional.observe]]). The proposal's FAQ relays the view of standard library implementers: they are happy to use it internally, but to put it in the standard interface they first need to be able to constrain the deduced type. The reason is the previous two sections: a deduced derived type changes lookup results and adds an instantiation per derived class.

### Replacing some uses of CRTP

The base class no longer needs to know the derived class's name; the derived type is deduced at the call site. The proposal's example is generating postfix `++` from prefix `++`:

<div class="compare" markdown="1">

```cpp
template<class D>
struct add_postfix {
  D operator++(int) {
    auto& self =
      static_cast<D&>(*this);
    D tmp(self);
    ++self;
    return tmp;
  }
};
struct Counter
  : add_postfix<Counter> {
  using add_postfix<Counter>
    ::operator++;
  int n = 0;
  Counter& operator++();
};
```

```cpp
struct add_postfix {
  template<class Self>
  auto operator++(this Self& self,
                  int) {
    auto tmp = self;
    ++self;
    return tmp;
  }
};
struct Counter : add_postfix {
  using add_postfix::operator++;
  int n = 0;
  Counter& operator++();
};
```

</div>

Both sides need the using-declaration: the prefix `operator++` declared in the derived class hides every function named `operator++` in the base, regardless of how the object parameter is written. The proposal's example omits it, and copying it verbatim gives an error at `c++`. A complete runnable version:

```cpp title="postfix.cpp" run ok
#include <cstdio>

struct add_postfix_increment {
  template<class Self>
  auto operator++(this Self& self, int) {
    auto tmp = self;     // Self is the derived class: copies the whole object
    ++self;
    return tmp;
  }
};

struct Counter : add_postfix_increment {
  using add_postfix_increment::operator++;   // otherwise hidden by the prefix ++ below
  int n = 0;
  Counter& operator++() { ++n; return *this; }
};

int main() {
  Counter c;
  Counter old = c++;
  std::printf("%d %d\n", old.n, c.n);   // 0 1
}
```

Method chaining (builders) is another typical case: a base-class setter returns `Self&`, so a derived builder's chain does not decay to the base type; see [[patterns/named-parameters]]. For the CRTP uses that still cannot be replaced (static data per derived class, member types of the base that need the derived class, keeping the derived type through a base reference), see [[patterns/crtp]] and [[patterns/mixin]].

### Recursive lambdas

A lambda's call operator can also have an explicit object parameter, and the parameter is the closure object itself (the example in [[expr.prim.lambda.closure#5]]):

<div class="compare" markdown="1">

```cpp
// C++14: pass yourself as an argument
auto fib = [](auto& self, int n)
    -> int {
  return n < 2 ? n
    : self(self, n - 1)
    + self(self, n - 2);
};
fib(fib, 20);   // 6765
```

```cpp
// C++23
auto fib = [](this auto& self,
              int n) -> int {
  return n < 2 ? n
    : self(n - 1) + self(n - 2);
};
fib(20);        // 6765
```

</div>

The earlier [[P0839R0]] proposed giving lambdas a name, written `[] self (int n) {…}`. The FAQ of P0847R7 explains why its own approach is easier to implement: the body of a non-generic lambda is not a template, so an expression like `sizeof(self)` has to be answered immediately, while the closure type is still incomplete. With `this auto`, the closure type cannot be written, the type of `self` is always dependent, and the function body is handled by the existing template rules, with no new mechanism needed.

A lambda with captures has one more restriction on the type of the object parameter: it must be the closure type, a class publicly and unambiguously derived from the closure type, or a reference to one of these ([[expr.prim.lambda.closure#6]]). Otherwise, when the function body accesses a capture, the object at hand would not be a closure at all. Other details of lambdas are in [[topics/lambdas]].

### One template instead of four overloads changes overload resolution too

Merging four overloads into one template is not just less code. The proposal points out that call wrappers like `std::not_fn` implemented with four overloads have two problems that cannot be fixed. One of them is silent fallback: if the wrapped object's non-const `operator()` is deleted, the wrapper's non-const overload is removed by SFINAE but the const overload is still viable, so the call succeeds and takes the wrong path. With only one candidate this does not happen:

```cpp title="not-fn.cpp" run ok
#include <cstdio>
#include <functional>
#include <utility>

// overloaded per qualifier (only two shown, enough to make the point)
template<class F>
struct not_fn4 {
  F f;
  template<class... A>
  auto operator()(A&&... a) & -> decltype(!std::invoke(f, std::forward<A>(a)...)) {
    return !std::invoke(f, std::forward<A>(a)...);
  }
  template<class... A>
  auto operator()(A&&... a) const& -> decltype(!std::invoke(f, std::forward<A>(a)...)) {
    return !std::invoke(f, std::forward<A>(a)...);
  }
};

// one template
template<class F>
struct not_fn1 {
  F f;
  template<class Self, class... A>
  auto operator()(this Self&& self, A&&... a)
      -> decltype(!std::invoke(std::forward<Self>(self).f, std::forward<A>(a)...)) {
    return !std::invoke(std::forward<Self>(self).f, std::forward<A>(a)...);
  }
};

struct fun {
  template<class... A> bool operator()(A&&...) = delete;        // non-const version deleted
  template<class... A> bool operator()(A&&...) const { return true; }
};

template<class W>
concept callable = requires(W w) { w(); };

int main() {
  not_fn4<fun> a{};
  std::printf("%d\n", a());                 // 0: silently falls back to the const overload
  static_assert(!callable<not_fn1<fun>&>);  // only one candidate, no fallback
}
```

The libc++ shipped with Clang 23 already implements the call operator of `std::bind_front` this way.

### Later fixes

After P0847R7 went into C++23, the following problems were dealt with one after another:

| Number | Problem | Outcome |
|---|---|---|
| [[CWG2653]] | Can an explicit object parameter have a default argument | No; in the grammar, `this` and `= initializer` no longer appear in the same parameter declaration ([[dcl.fct#2]]) |
| [[CWG2674]] | Can a constructor have an explicit object parameter | No ([[class.ctor.general#7]]) |
| [[CWG2789]] | A call is ambiguous between `f()` and `f(this S&) requires true` | When comparing constraints, compare the non-object parameter lists and the object parameter types, and pick the more constrained one ([[over.match.best.general#2.6]], [[temp.constr.order#6]]) |
| [[P2797R0]] | Can `static void f(A);` and `void f(this A);` coexist | Yes, they are not redeclarations; `(&A::f)(A())` first takes the address of each function in the overload set and then performs overload resolution ([[over.call.func#3]]) |
| [[LWG3617]] | `std::function`'s deduction guide doesn't recognize `&F::operator()` in function-pointer form | Adds an `R(*)(G, A...)` form, deducing `function<R(A...)>` |
| [[CWG2554]] | How object parameters are compared when overriding virtual functions | Still in review; see "Can it be virtual" above |

Clang 23 already handles the first three according to the fixed rules: a default argument gives "the explicit object parameter cannot have a default argument", a constructor gives "an explicit object parameter cannot appear in a constructor", and the CWG2789 example calls the constrained one.

The outcome of LWG3617 is that given `struct F { int operator()(this const F&, int); };`, `std::function h = F{};` should deduce `std::function<int(int)>` ([[func.wrap.func.con#16]]). The libc++ shipped with Clang 23 deduces `std::function<int(const F&, int)>`, and the initialization then fails, which does not conform to the standard.

### Compiler support

Clang 23 defines `__cpp_explicit_this_parameter` as `202110L` under `-std=c++23` and `-std=c++2c`, and all the core-language examples on this page behave as the standard says, with two exceptions: `struct D3 : B3 { void f(this D3&); }` is rejected (see "Can it be virtual"), plus the two libc++ library problems listed above. Support in other compilers has not been verified on this page.

## Questions

!!! question "Question 1"
    Are `struct X { void k(); void k(this X&); };` and `struct Y { void k() &&; void k(this Y&); };` each well-formed?

<details markdown="1">
<summary>Answer</summary>

`X` is ill-formed. `X::k()` is an implicit object member function without a ref-qualifier, so references are removed for the comparison: its object parameter type `X&` and `this X&` are both `X` once the reference is removed. The two declarations have corresponding object parameters and the same non-object parameter lists, so they correspond and are redeclarations of each other ([[basic.scope.scope#3]], [[basic.scope.scope#4]]).

`Y` is well-formed. `Y::k() &&` has a ref-qualifier, so the remove-the-reference rule does not apply and the object parameter types must be identical; `Y&&` differs from `Y&`, so they are different overloads. The proposal deliberately makes an old-style function without a ref-qualifier conflict with both the `&` and the `&&` versions, because there is no reason to think the unqualified form is closer to one of them.
</details>

!!! question "Question 2"
    In the code below, which specialization does `d.name()` instantiate, and what does it return? What if `name` is changed to `std::string name(this const Base& self)`?
    ```cpp
    struct Base {
      std::string tag() const { return "base"; }
      template<class Self>
      std::string name(this const Self& self) { return self.tag(); }
    };
    struct D : Base { std::string tag() const { return "d"; } };
    D d;
    ```

<details markdown="1">
<summary>Answer</summary>

In the template version, `d.name()` deduces `Self` as `D` and instantiates `Base::name<D>`; `self.tag()` is looked up starting from `D`, finds `D::tag`, and returns `"d"`. `static_cast<Base&>(d).name()` instead instantiates `Base::name<Base>` and returns `"base"`.

In the non-template version the object parameter's type is fixed as `const Base&`; `d` binds to it via the derived-to-base conversion, `self.tag()` finds `Base::tag`, and it returns `"base"`. Neither involves virtual functions: the former binds to the static type at the call site, the latter to the type written in the declaration.
</details>

## Summary

| Decision | Choice | Reason |
|---|---|---|
| Syntax | `this` before the first parameter | Deducible, can be by value, works for lambdas, no parsing problems |
| In the function body | No `this`, no implicit member access | Simplest model; the cost is guarding against same-named members of derived classes |
| Classification | Non-static member function, cannot be written `static` | Looks like an ordinary member function from outside; less wording change |
| Calls from other members | `this->` may be omitted | A derived class doesn't need to know how the base implements it |
| `&C::f` | Ordinary function pointer | Consistent with by-value parameters, so templates get consistent result types |
| `virtual` | Not allowed for now | Calling convention and semantic differences, and no new capability; CWG2554 is still open |
| Deducing only the qualifiers | Not provided | Better solved together with the same need for free function templates |
