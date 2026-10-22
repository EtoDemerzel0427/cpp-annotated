---
title: Default arguments
summary: "A default argument is an expression filled in at the call site: it is evaluated on every call, but its names are looked up where it is declared; it belongs to a declaration, not to the function type, and later declarations in the same scope can add default arguments but never repeat them."
updated: 2026-10-19
---

!!! tldr
    - When trailing arguments are missing in a call, the compiler fills in the default arguments at the call site. They are evaluated anew on every such call.
    - Names in a default argument are looked up where it is written, regardless of the call site. `std::source_location::current()` is the exception to the exception: it gets the location of the call site.
    - Default arguments are not part of the function type: function pointers, `std::function` and typedefs don't see them.
    - Later declarations in the same scope can add default arguments but can't repeat them, not even with the same value. Declarations at block scope have their own separate set.
    - A virtual function call picks default arguments by the static type of the pointer or reference; an overrider doesn't inherit the base class's default arguments.

## An expression filled in at the call site (¶1–2, ¶9)

```cpp run title="default-each-call.cpp" ok
#include <cstdio>
int counter = 0;
int next() { return ++counter; }
void f(int a = next()) { std::printf("%d ", a); }

int main() {
  f(); f(); f(10);   // prints 1 2 10
}
```

¶1 The initializer after `=` in a function parameter declaration is a **default argument** ([[g:default-argument|default argument]]). The `= …` of a template parameter is a default template argument, governed by [[temp.param]]. Note 1 explains that when trailing arguments are missing in a call, the default arguments are used to fill them in ([[expr.call]]). The example in ¶2: after `void point(int = 3, int = 4);`, `point(1)` is equivalent to `point(1, 4)`, and `point()` to `point(3, 4)`.

¶9 Every call that omits the corresponding argument evaluates the default argument anew. The two `f()` calls above each call `next()`, giving 1 and 2. Python's default parameters are evaluated only once, at `def` time; C++ is not like that.

Think of a default argument as a piece of expression attached to a particular declaration. At the call site, the compiler splices this expression into the argument list; the called function itself doesn't know whether an argument came from a default. The rest of the rules on this page all follow from this model.

## Names are looked up at the declaration (¶5)

```cpp run title="default-lookup.cpp" ok
#include <cstdio>
int a = 1;
int f(int x) { return x * 10; }
int g(int x = f(a)) { return x; }   // a is already fixed as ::a

int main() {
  a = 2;
  {
    int a = 3;                       // doesn't affect the default argument
    (void)a;
    std::printf("%d\n", g());        // g(f(::a)), prints 20
  }
}
```

¶5 Names in a default argument are looked up, and semantic checks performed, where the default argument appears, regardless of the call site. The expression is still evaluated only at the call, though, so it reads the value of `::a` at that time, which is 2.

A default argument is subject to the same semantic constraints as the initializer of a variable of the parameter type, using copy-initialization ([[dcl.init]]). So an `explicit` constructor can't be used for an implicit conversion in a default argument: after `struct E { explicit E(int); };`, `void k(E e = 1);` is ill-formed.

### Immediate invocations are deferred to the call site

A call to a `consteval` function is an **immediate invocation** ([[g:immediate-invocation|immediate invocation]], [[expr.const.imm]]), which in general must be a constant expression right where it appears. Paragraph 5 makes an exception: a potentially-evaluated immediate invocation in a default argument is neither evaluated nor checked for being a constant expression at the point of declaration.

This rule exists for `std::source_location::current()`. It is a `consteval` function, and if it were evaluated at the declaration, it would give the declaration's location. Deferred to the call site, [[support.srcloc]] makes it return the call site's location:

```cpp run title="source-location.cpp" ok
#include <cstdio>
#include <source_location>

void log(const char* msg,
         std::source_location loc =
             std::source_location::current()) {
  std::printf("%s @ line %u\n", msg,
              static_cast<unsigned>(loc.line()));
}

int main() {
  log("hello");   // prints this line's number, not log's
}
```

### Default arguments in classes and templates

Note 3 explains that a default argument is a **complete-class context** ([[g:complete-class-context|complete-class context]], [[class.mem]]): default arguments of member functions are analyzed only after the class definition ends, so they can use members declared later and can apply `sizeof` to the class itself. Access checking applies as usual ([[class.access]]).

For a templated function, name lookup and semantic checking of default arguments follow [[temp.inst]], i.e. they are instantiated only when used. So even if `T` has no default constructor, a default argument like `T t = T()` doesn't prevent instantiating the class template, as long as calls don't omit that argument.

```cpp run title="complete-class.cpp" ok
struct S {
  void f(int x = later);          // later is declared below
  void g(int x = sizeof(S));      // S is complete at this point
  static constexpr int later = 5;
};
void S::f(int) {}
void S::g(int) {}

template<class T>
struct TT { void m(T t = T()) { (void)t; } };
struct NoDef { NoDef(int) {} };

int main() {
  S{}.f();
  S{}.g();
  TT<NoDef> x;          // OK: T() hasn't been instantiated
  x.m(NoDef(1));        // OK: the default argument isn't used
}
```

## Where they can appear (¶3)

¶3 A default argument can only be written in the parameter list of a function declaration or lambda declarator; it can't be given for a function parameter pack, and can't appear inside the declarator of a parameter. Footnote 70 explains that this means declarations of function pointers, function references and typedefs can't have default arguments.

```cpp title="default-where.cpp" error
void (*pf)(int = 0);            // error: function pointer
typedef void F(int = 0);        // error: typedef
void g(void (*cb)(int = 0));    // error: inside a parameter's declarator
template<class... T>
void h(T... = 0);               // error: parameter pack
auto l = [](int x = 1) { return x; };   // OK: lambda
```

Function pointers can't carry default arguments because default arguments aren't in the type, and a pointer's type has nowhere to store them. If `void (*pf)(int = 0)` were allowed, it wouldn't be clear whom the default belongs to after `pf = &other;`.

A default argument can itself contain a lambda, e.g. `void g(int x = [] { return 42; }());`. `co_await`, however, can't appear in a default argument ([[expr.await]]).

## Accumulation across declarations (¶4)

¶4 First, the **host scope** ([[basic.scope.scope]]): for a declaration at block scope, the host scope is that block; for other declarations, it is the target scope, e.g. a function declaration in a namespace has that namespace. Then:

- For a non-template function, later declarations with the same host scope can add default arguments;
- Declarations with different host scopes each have their own set of default arguments; inner ones don't inherit the outer set, and outer ones don't see the inner ones;
- In each declaration, every parameter after one with a default argument must have a default argument in this or a previous declaration, except parameters expanded from a parameter pack and function parameter packs;
- Note 2 explains that a default argument can't be given again for the same parameter, even with the same value ([[basic.def.odr]]).

Example 2 in the standard uses all of these:

```cpp title="default-accumulate.cpp" error
void g(int = 0, ...);       // OK: the ellipsis is not a parameter
void f(int, int);
void f(int, int = 7);       // adds: the second parameter now has a default argument
void h() {
  f(3);                     // OK: f(3, 7)
  void f(int = 1, int);     // error: block scope doesn't inherit "= 7",
                            //   so the second parameter has no default argument
}
void m() {
  void f(int, int);         // this block's declaration, no default arguments
  f(4);                     // error: the outer "= 7" isn't visible here
  void f(int, int = 5);     // OK: added in this block
  f(4);                     // OK: f(4, 5)
  void f(int, int = 5);     // error: can't be given again
}
void n() {
  f(6);                     // OK: f(6, 7); the "= 5" in m belongs only to m
}
template<class... T> struct C {
  void f(int n = 0, T...);  // parameters expanded from a pack need no default argument
};
C<int> c;                   // OK: void C<int>::f(int n = 0, int)
```

A function declaration at block scope is by nature a local redescription of an external function. Isolating default arguments by host scope means each scope sees a self-consistent set, which doesn't change because of what was written in some other function body.

The end of ¶4 has two more rules:

- When the same inline function is defined in multiple translation units, the accumulated sets of default arguments at the end of each translation unit must be the same. A violation makes the program ill-formed, no diagnostic required (IFNDR): neither the compiler nor the linker may say anything.
- If a friend declaration specifies a default argument, it must be a function definition, and no other declaration of the function may be reachable from it or have it reachable. In effect, a friend function with default arguments can only be declared once, like a hidden friend.

```cpp title="friend-default.cpp" error
struct F  { friend void fr(int = 0); };      // error: must be a definition
struct F2 { friend void fr2(int = 0) {} };   // OK
```

## Member functions defined outside the class (¶6)

¶6 Default arguments given in an out-of-class definition of a member function are added to the set from the in-class declaration. There are two restrictions:

- If doing so turns the function into a default constructor, a copy or move constructor, or a copy or move assignment operator, the program is ill-formed;
- For a member function of a templated class, default arguments can only be given in the initial in-class declaration.

```cpp title="member-default.cpp" error
class C {
  void f(int i = 3);
  void g(int i, int j = 99);
  C(int x);
};
void C::f(int i = 3) {}          // error: already given in the class
void C::g(int i = 88, int j) {}  // OK: from here on C::g can be called with no arguments
C::C(int x = 0) {}               // error: becomes a default constructor

template<class T> struct T1 { void f(int); };
template<class T>
void T1<T>::f(int = 1) {}        // error: can only be given in the class
```

Special member functions are restricted because whether a class has a default constructor or copy constructor determines properties such as whether it is trivial and which members are implicitly declared. These properties must be settled at the end of the class definition and be consistent across all translation units; they can't change because some source file added a default argument outside the class.

## What default arguments can't use (¶7–9)

A default argument is evaluated in the caller, so it can't use anything the caller doesn't have.

### Local variables and this (¶7, ¶8)

¶7 is a note: a local variable can't be odr-used in a default argument ([[basic.def.odr]]). Roughly, an odr-use is a use that needs the variable itself to exist, such as reading the value of a non-constant variable; using it inside `sizeof`, or reading a `const int` initialized with a constant expression, doesn't count.

```cpp title="default-local.cpp" error
void f() {
  int i;
  extern void g(int x = i);          // error: odr-uses a local variable
  extern void h(int x = sizeof(i));  // OK: unevaluated operand
  const int k = 3;
  extern void p(int x = k);          // OK: reading a constant is not an odr-use
}
```

`g` is a function of the namespace and may be called outside `f`, when `i` no longer exists.

¶8 is also a note: `this` can't appear in a default argument of a member function ([[expr.prim.this]]); for example, `void f(A* p = this);` is ill-formed.

### Other parameters (¶9)

¶9 A parameter can't be potentially evaluated in a default argument. Note 6 reminds us that parameters written before the default argument are already in scope and hide namespace and class members with the same name:

```cpp title="default-param.cpp" error
int a;
int f(int a, int b = a);          // error: uses the parameter a
typedef int I;
int g(float I, int b = I(2));     // error: finds the parameter I
int h(int a, int b = sizeof(a));  // OK: unevaluated operand
```

Using earlier parameters is forbidden because the order in which parameters are initialized is indeterminate ([[expr.call]]); when the default value of `b` is computed, `a` isn't necessarily initialized yet. In `g`, the parameter `I` hides the type name `I`, so `I(2)` becomes a call on a `float`.

### Non-static members (¶9)

A default argument can't refer to a non-static member unless:

- ¶9.1 it appears in a class member access expression, such as `obj.m`;
- ¶9.2 it is used to form a pointer to member, such as `&X::m`;
- ¶9.3 {{c++26}} it is the operand of a reflection expression `^^m`.

```cpp title="default-member.cpp" error
int b;
class X {
  int a;
  int mem1(int i = a);           // error: no object to provide a
  int mem2(int i = b);           // OK: X::b, a static member
  int mem3(int X::*p = &X::a);   // OK: pointer to member
  static int b;
};
```

The `b` in `mem2` is `X::b`, not `::b`, because a default argument is a complete-class context and can find members declared later. Example 8 in the standard also shows that a splice like `[:^^a:]` counts as referring to `a` too and is not allowed; `^^a` itself is fine.

## Default arguments are not part of the function type (¶9)

```cpp title="default-not-type.cpp" error
int f(int = 0);
void h() {
  int j = f(1);
  int k = f();            // OK: i.e. f(0)
}
int (*p1)(int) = &f;
int (*p2)() = &f;         // error: f has type int(int)
```

The end of ¶9 states explicitly that a default argument is not part of a function's type (see also [[dcl.fct#13]]). Notes 7 and 8 explain which default arguments overload resolution can use: if some declaration of a candidate function has host scope *S*, the default arguments on all reachable declarations in *S* can be used ([[over.match.viable]]); but for a candidate found through a using-declaration, the declaration providing a default argument isn't necessarily reachable from there.

## Virtual functions take default arguments by static type (¶10)

```cpp run title="virtual-default.cpp" ok
#include <cstdio>
struct A {
  virtual void v(int a = 7) { std::printf("A %d\n", a); }
  virtual ~A() = default;
};
struct B : A {
  void v(int a = 9) override { std::printf("B %d\n", a); }
};
int main() {
  B b;
  A& ra = b;
  ra.v();   // B 7: the body follows the dynamic type, the default argument the static type
  b.v();    // B 9
}
```

!!! std
    A virtual function call uses the default arguments in the declaration of the virtual function determined by the static type of the pointer or reference denoting the object.

¶10 An overriding function also doesn't inherit default arguments from the function it overrides. In Example 10 in the standard, `B::f(int)` has no default argument, so `pb->f()` is ill-formed, while `pa->f()` calls `B::f(7)`.

Default arguments are filled in by the compiler at the call site, where it only knows the static type. Choosing by dynamic type would require putting default arguments in the vtable too or dispatching at run time, which goes against the design that default arguments are not part of the function type. So don't write different default arguments in an overrider. The usual practice is to put default arguments on a public non-virtual function that calls a protected virtual function: the NVI (non-virtual interface) idiom.

## Implementation notes

!!! impl
    - Default arguments are expanded at each call site; they don't affect name mangling and don't enter the ABI.
    - Consequently, after changing a default value in a header, recompiling only the source file with the definition isn't enough; all callers must be recompiled. This is a common problem in library ABI evolution.
    - Clang 23's diagnostics: giving a default argument again reports "redefinition of default argument"; adding a default argument out of class that makes a constructor a default constructor reports "addition of default argument on redeclaration makes this constructor a default constructor"; adding a default argument out of class for a member of a class template reports "default arguments cannot be added to an out-of-line definition of a member of a class template".

## History

!!! history
    - C++98 already had most of the rules in this subclause, including choosing default arguments for virtual functions by static type.
    - C++11 lambdas originally didn't allow default arguments; this was opened up by a core language defect resolution and is available since C++14.
    - After `consteval` and `std::source_location` entered C++20, a defect resolution clarified that immediate invocations in default arguments are deferred to the call site rather than evaluated at the declaration.
    - C++26: `^^member` can reflect non-static members in default arguments.

## Common misconceptions

!!! pitfall "Writing the default argument once in the header and once in the source file"
    Declaring `void f(int x = 1);` in a header and then defining `void f(int x = 1) {}` in the source file gives the default argument twice and is ill-formed. Write default arguments only in the declaration, usually the header.

!!! pitfall "A default argument is evaluated only once"
    It is re-evaluated on every call that omits the argument; it can have side effects, and the result can differ each time, as with `std::chrono::steady_clock::now()`.

!!! pitfall "Function pointers and `std::function` can use default arguments"
    They only see the type. With `void f(int = 0)`, `std::function<void()> fn = f;` is ill-formed.

## Questions

!!! question "Question 1"
    What does the following program print?
    ```cpp
    #include <cstdio>
    void f(int a, int b = 2);
    void f(int a = 1, int b);
    int main() {
      f();
      { void f(int, int = 20); f(10); }
      f();
    }
    void f(int a, int b) { std::printf("%d%d ", a, b); }
    ```

<details markdown="1">
<summary>Answer</summary>

It prints `12 1020 12 `. The second declaration is valid: `b` already has a default argument in a previous declaration with the same host scope, which satisfies the requirement that defaults be contiguous. After accumulation, `f()` is `f(1, 2)`. The declaration in the block has its own set of default arguments, with only `b = 20`, so `f(10)` is `f(10, 20)`. After leaving the block, the global set applies again (paragraph 4).
</details>

!!! question "Question 2"
    Why does `std::source_location::current()` as a default argument get the call site's location, while an ordinary `constexpr` function `my_line()` can't?

<details markdown="1">
<summary>Answer</summary>

Both are evaluated at the call site; the difference is that `current()` is specially handled by the implementation: [[support.srcloc]] specifies that when it appears in a default argument, it returns the location of the call site. Paragraph 5 guarantees that this immediate invocation isn't evaluated early at the declaration. An ordinary function has no way of knowing its caller's location, unless it too takes a `source_location` default argument.
</details>
