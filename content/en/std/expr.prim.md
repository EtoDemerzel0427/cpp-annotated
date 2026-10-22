---
title: Primary expressions
summary: "The bottom layer of the expression grammar, and the rules for three of its forms: the value category of literals, where this can appear and what type it has, and parenthesized expressions."
updated: 2026-10-19
---

!!! tldr
    - A string literal is an lvalue because it designates an array object that really exists; the value category of a user-defined literal depends on what the corresponding `operator""` returns; all other literals are prvalues.
    - `this` is a prvalue pointer of type pointer to cv `X`: it depends only on the member function's cv-qualifiers, not on its ref-qualifier.
    - `this` can appear only in the part of an implicit object member function after the cv-qualifiers, and in default member initializers; it can't appear in static member functions or explicit object member functions.
    - A lambda does not introduce a class scope, but a local class does, and that determines which object `this` points to.
    - `(E)` has exactly the same type and value category as `E`; it means something different only in a few contexts, most commonly `decltype((x))` and `return (x);`.

**Primary expressions** are the bottom layer of the expression grammar: postfix expressions ([[expr.post]]), unary expressions ([[expr.unary]]) and every layer above eventually bottom out in some primary expression. They are not built from operators; they are where the operands of all operators start.

[expr.prim] groups eight different things together:

| Grammar alternative | Example | Covered in |
|---|---|---|
| *literal* | `42`, `"abc"`, `1.5_km` | this page |
| `this` | `this` | this page |
| `( expression )` | `(x)` | this page |
| *id-expression* | `x`, `N::x`, `~T`, `ts...[0]` | [[expr.prim.id]] |
| *lambda-expression* | `[&](int i) { return i + n; }` | [[expr.prim.lambda]] |
| *fold-expression* | `(... + args)` | [[expr.prim.fold]] |
| *requires-expression* | `requires (T t) { t + t; }` | [[expr.prim.req]] |
| *splice-expression* {{c++26}} | `[: ^^x :]` | [[expr.prim.splice]] |

What they have in common is purely grammatical: each can be the left operand of postfix operators such as `()`, `[]`, `.` and `->` directly, without parentheses. That is why a lambda can be called right where it is written (`[]{ return 1; }()`), and why `requires { ... } && C<T>` needs no parentheses.

Most of the rules on this page answer two questions: what type the expression has, and which value category it belongs to. Value categories ([[basic.lval]]) divide expressions into lvalues (designating an object or function with identity, whose address can be taken), xvalues (objects about to be moved from) and prvalues (just a value, used to initialize an object).

## Grammar [expr.prim.grammar]

The grammar has a single production listing the eight alternatives in the table above. Three points are worth noting.

An *id-expression* also appears after `.` and `->` ([[expr.ref]]); there it is part of a member access, not a standalone primary expression. That is why many rules in [[expr.prim.id]] have to exclude this case explicitly.

The parentheses of a fold expression are part of its own grammar, not the `( expression )` alternative; `... + args` without parentheses is not an expression.

Only certain primary expressions can be written directly in a *requires-clause* ([[temp.pre]]), which is why an ad hoc constraint is written `requires requires { ... }`: the first `requires` introduces the clause, the second starts a *requires-expression* (see [[expr.prim.req]]).

## Literals [expr.prim.literal]

¶1 The type of a literal is determined by how it is written, by the rules in the lexical chapter [[lex.literal]]: `42` is `int`, `42u` is `unsigned int`, `'a'` is `char`, `1.0f` is `float`, `nullptr` is `std::nullptr_t`. This subclause adds the value category:

| Literal | Value category |
|---|---|
| String literal | lvalue, designating an array object with static storage duration ([[lex.string]]) |
| User-defined literal | Same as the `operator""` call it is rewritten to by [[lex.ext]] |
| Other literals | prvalue |

A string literal is an lvalue because it really is an object: `"abc"` is a `const char[4]` array with an address, which can bind to a `const char(&)[4]`. `42` is just a value and occupies no storage until it is materialized as a temporary object ([[conv.rval]]).

```cpp run ok
#include <type_traits>

static_assert(std::is_same_v<decltype("ab"), const char(&)[3]>);  // lvalue: decltype gives T&
static_assert(std::is_same_v<decltype(42), int>);                  // prvalue: no reference
static_assert(std::is_same_v<decltype(u8"x"), const char8_t(&)[2]>);
static_assert(std::is_same_v<decltype(nullptr), std::nullptr_t>);

const char (*p)[4] = &"abc";   // OK: a string literal's address can be taken
// int* q = &42;               // error: can't take the address of a prvalue

int main() { }
```

Whether evaluating the same string literal twice yields the same object, and whether distinct string literals share storage (for example the tail of `"abc"` overlapping `"bc"`), are both unspecified ([[lex.string]]). So don't compare the addresses of string literals. GCC and Clang merge literals with identical contents by default, but that is just an implementation choice.

A user-defined literal is rewritten to a function call to `operator""`, and its value category is that of the call:

```cpp run ok
#include <type_traits>

struct Reg { int v; };
Reg  table[4];
Reg& operator""_reg(unsigned long long i) { return table[i]; }
Reg  operator""_val(unsigned long long i) { return Reg{int(i)}; }

static_assert(std::is_same_v<decltype(2_reg), Reg&>);  // returns an lvalue reference: lvalue
static_assert(std::is_same_v<decltype(2_val), Reg>);   // returns by value: prvalue

int main() { (3_reg).v = 7; }   // assign to a member of an lvalue
```

!!! pitfall "`3_reg.v` is not a member access"
    A preprocessing number (pp-number, [[lex.ppnumber]]) can contain `.` and identifier characters, so `3_reg.v` is lexed as a single token: a user-defined literal with suffix `_reg.v`, for which no literal operator is found, hence an error. Write `(3_reg).v` or `3_reg .v` instead. The pseudo-destructor call `0.T::~T()` has the same problem ([[expr.prim.id.dtor]]).

## this [expr.prim.this]

```cpp error
struct Y {
  static void s() { (void)this; }        // error: static member function
  void e(this Y& self) { (void)this; }   // error: explicit object member function, use self
  void d(Y* p = this);                   // error: default argument
  static auto t() -> decltype(this);     // error: declaration of a static member function
};
```

`this` can appear in very few places. Below we first cover what it points to, then where it is valid and what type it has.

### What this points to

¶1 The keyword `this` is a pointer to one of two kinds of object: the object for which an **implicit object member function** (the traditional non-static member function, [[class.mfct.non.static]]) is invoked, or the object whose default member initializer ([[class.mem]]) is being evaluated.

`this` is a prvalue, not a variable: you can't assign to it or write `&this`.

¶2 The [[g:current-class|**current class**]] at a point is the class associated with the innermost class scope containing that point. Note 1 points out that a lambda expression does not introduce a class scope. So for a lambda in a member function, the current class in its body is still the enclosing class, not the closure type, and a `this` captured in the lambda body points to the enclosing object ([[expr.prim.lambda.closure]]). A local class does introduce a new class scope: in a `struct Inner` defined inside a member function, `this` is `Inner*`.

### Type and scope in member functions

¶4 In a declaration of a member function (or member function template) of class `X`, if `X` is the current class, then from after the optional cv-qualifier-seq to the end of the function definition or declarator, `this` is a prvalue of type pointer to cv `X`.

```cpp run ok
#include <type_traits>

struct X {
  void f()            { static_assert(std::is_same_v<decltype(this), X*>); }
  void g() const      { static_assert(std::is_same_v<decltype(this), const X*>); }
  void h() volatile & { static_assert(std::is_same_v<decltype(this), volatile X*>); }  // & has no effect
  auto k() -> decltype(this) { return this; }   // OK: the trailing return type comes after cv
  int  n = sizeof(*this);                       // OK: default member initializer
  X*   self = this;                             // OK
};
static_assert(std::is_same_v<decltype(&X::k), X* (X::*)()>);

int main() { }
```

The type of `this` carries only the cv-qualification, not the ref-qualifier: in `void f() const &&`, `this` is still `const X*`. The ref-qualifier only affects the type of the implicit object parameter in overload resolution ([[over.match.funcs]]); `*this` itself is always an lvalue.

The valid range starts after the cv-qualifiers, so `this` can be used in a trailing return type and in a `noexcept` specifier but not in the parameter list; `void d(Y* p = this)` is ill-formed ([[dcl.fct.default]] also separately forbids `this` in default arguments).

¶4 also says `this` shall not appear within the declaration of a static member function or an explicit object member function ([[dcl.fct]], C++23's deducing this) of the current class. The wording first says the type and value category of `this` are defined in these functions, and then forbids it. Note 2 explains why: you need to read the whole declarator to match it to an earlier declaration. An out-of-class definition `auto X::f() -> decltype(this)` doesn't say `static`, so when the compiler reaches `decltype(this)` it doesn't yet know whether `f` is static; it can only determine the type as for an ordinary member function and check afterward.

!!! note "Why explicit object member functions forbid this"
    In `void f(this Self&& self)`, the object the function is called on is passed in through `self`, and `Self` may be deduced as a derived class. If `this` were also allowed, should it be `X*` or `Self*`? For a call on a derived-class object the two would disagree. Forbidding `this` and always going through `self` removes the ambiguity. Likewise, a bare member name `m` in the body doesn't become `this->m`; you have to write `self.m` ([[expr.prim.id.general#2]]).

Note 3 points out a detail about trailing return types: the class is still incomplete there, but member access is still possible; you just can't see members declared later.

```cpp ok
struct A {
  char g();
  template<class T> auto f(T t) -> decltype(t + g())  // g() means this->g()
    { return t + g(); }
};
template auto A::f(int t) -> decltype(t + g());       // explicit instantiation outside the class
```

### In default member initializers

¶5 In a default member initializer for a non-static data member, `this` is `X*` without cv, because the object is not yet const during construction ([[class.ctor]]). So `X* self = this;` and `Callback cb{this};` are both valid. The range is limited to the initializer; the array bound in `int a[sizeof(*this)];` is not part of it.

### Forbidden everywhere else

¶6 Outside those two kinds of places, `this` shall not appear. The standard's example:

```cpp error
class Outer {
  int a[sizeof(*this)];               // error: not inside a member function
  unsigned int sz = sizeof(*this);    // OK: default member initializer

  void f() {
    int b[sizeof(*this)];             // OK: inside Outer::f

    struct Inner {
      int c[sizeof(*this)];           // error: not inside a member function of Inner
    };
  }
};
```

`Inner` is written inside the body of `Outer::f`, but the current class has become `Inner`, and an array bound in `Inner` is neither of the two places above. ¶4 gives `this` only where `X` is the current class, so the `this` of `Outer::f` doesn't extend into the local class.

A lambda doesn't introduce a class scope, so `this` in a lambda body still comes from the enclosing member function, but it must be captured ([[expr.prim.lambda.capture]]):

```cpp error
struct Z {
  int v = 0;
  void f() {
    auto l1 = [this] { return v; };            // OK: v means this->v
    auto l2 = []     { return v; };            // error: this is not captured
    struct Inner { int x = sizeof(*this); };   // OK: this is Inner*
  }
};
```

### this in contract assertions {{c++26}}

¶3 C++26 contract assertions ([[basic.contract.general]], i.e. `pre`, `post` and `contract_assert`) should only observe program state, not modify it. So if `this` appears in the predicate of a contract assertion and the current class encloses the assertion, the type of `this` gets an extra `const`. This includes an implicitly transformed `this` (writing `m` in a predicate really means `(*this).m`, see [[expr.prim.id.general#2]]), and `this` inside a nested lambda body.

So even in a non-const member function, `pre(mutate())` is ill-formed, because it calls a non-const member function through a `const X*`. External variables named in a predicate are also treated as const; see [[expr.prim.id.unqual#7]]. As of this writing, Clang 23 doesn't support contracts yet, so this rule couldn't be verified locally.

## Parenthesized expressions [expr.prim.paren]

¶1 `(E)` is a primary expression whose type, result and value category are identical to those of `E`. It can be used wherever `E` can be used, with the same meaning, except as otherwise indicated.

Parentheses change only grouping, not the expression itself. So `(x)` and `x` are both lvalues, `(std::move(x))` is still an xvalue, and `return (x);` still moves implicitly ([[expr.prim.id.unqual#15]] says explicitly that parentheses are allowed). Bit-fields too: `int& r = (b.bf);` is ill-formed just like `int& r = b.bf;`.

The part worth remembering is "except as otherwise indicated". Here are the places where parentheses change the meaning:

| Context | Without parentheses | With parentheses | Source |
|---|---|---|---|
| `decltype` | `decltype(x)`: the declared type of `x` | `decltype((x))`: computed from the expression; an lvalue gives `T&` | [[dcl.type.decltype]] |
| `decltype(auto)` | `return x;` deduces `T` | `return (x);` deduces `T&` | [[dcl.type.auto.deduct]] |
| Pointer to member | `&S::m` is `int S::*` | `&(S::m)` is `int*` inside a member function of `S`, ill-formed elsewhere | [[expr.unary.op]] |
| Function call | `f(a)` does argument-dependent lookup (ADL) | `(f)(a)` doesn't do ADL | [[basic.lookup.argdep]] |
| Template argument | `A<1>2>` fails to parse | `A<(1>2)>` OK | [[temp.names]] |
| Splice as a template argument {{c++26}} | `e<[:r:]>` ill-formed | `e<([:r:])>` OK | [[expr.prim.splice#1]] |

```cpp run ok
#include <type_traits>

int x = 0;
static_assert(std::is_same_v<decltype(x),   int>);    // declared type of the entity
static_assert(std::is_same_v<decltype((x)), int&>);   // (x) is an lvalue of type int

decltype(auto) r1() { return x; }     // int
decltype(auto) r2() { return (x); }   // int&
static_assert(std::is_same_v<decltype(r1()), int>);
static_assert(std::is_same_v<decltype(r2()), int&>);

struct S {
  int m;
  void k() {
    auto p = &(S::m);                 // equivalent to &(this->m)
    static_assert(std::is_same_v<decltype(p), int*>);
  }
};
int S::* pm = &S::m;                  // no parentheses: pointer to member

int main() { }
```

```cpp error
namespace N { struct A {}; void f(A) {} }
struct S { int m; };

void g() {
  N::A a;
  f(a);        // OK: ADL finds N::f
  (f)(a);      // error: parentheses suppress ADL, ordinary lookup doesn't find f
}
auto q = &(S::m);   // error: not in a member function, S::m can't be used like this
```

!!! tip "`(std::max)(a, b)`"
    Windows headers define `max` as a function-like macro, and a function-like macro expands only when the name is immediately followed by `(`. Writing `(std::max)(a, b)` sidesteps the macro. This is an effect at the preprocessing level, not a rule from this subclause.

!!! lawyer "Parentheses and declarations"
    In the most vexing parse, the extra parentheses in `T x((T()));` make it impossible to parse as a function declaration ([[stmt.ambig]], [[dcl.ambig.res]]). That resolves an ambiguity between declarations and expressions; once something is known to be an expression, parentheses no longer change anything.

## Implementation view

!!! impl
    Both the Itanium C++ ABI (GCC and Clang on Linux and macOS) and MSVC pass `this` as a hidden first argument; on x86-64 System V that is `rdi`. The `self` of an explicit object member function is an ordinary first parameter and can be passed by value (`this Self self`), in which case the calling convention is entirely different from passing a `this` pointer.

## History

!!! history
    Early C++ allowed assigning to `this` to customize object allocation; this was later replaced by overloading `operator new`, and `this` became a non-assignable prvalue. C++11 introduced default member initializers, trailing return types and lambdas, increasing the places `this` can appear; the distinction between `decltype((x))` and `decltype(x)` also dates from C++11. C++14's `decltype(auto)` brought the difference of `return (x);` into everyday code. C++23 introduced explicit object member functions and forbade `this` in them. C++26 made `this` const in contract predicates and added splice expressions.

## Common misconceptions

!!! pitfall "`return (local);` returns a dangling reference"
    ```cpp
    decltype(auto) get() {
      int local = 42;
      return (local);   // deduced as int&, refers to a destroyed local variable
    }
    ```
    Clang warns with `-Wreturn-stack-address` in this simple case, but after a member access or a structured binding it may not catch it.

!!! pitfall "`*this` is an lvalue even in a `&&`-qualified member function"
    To forward yourself as an rvalue, write `std::move(*this)`. Since C++23 you can use an explicit object parameter instead: `void f(this Self&& self)`, then `std::forward<Self>(self)`.

## Questions

!!! question "1. Which of these lines are well-formed?"
    ```cpp
    struct A {
      int v;
      auto f() const -> decltype((v));            // #1
      auto g() -> decltype(this->v);              // #2
      static auto h() -> decltype(sizeof(v));     // #3
    };
    ```

<details markdown="1">
<summary>Answer</summary>

`#1` is well-formed. `v` is transformed into `(*this).v` ([[expr.prim.id.general#2]]); it comes after `const`, so `this` is `const A*`, and `decltype((v))` is `const int&`.

`#2` is well-formed. `decltype` applied to an unparenthesized member access gives the member's declared type, `int`.

`#3` is ill-formed under the current draft. `v` is a member of the current class `A` itself, so condition (2.1) of [[expr.prim.id.general#2]] holds and it is transformed into `(*this).v` even in an unevaluated operand, which is ill-formed in a static member function. Clang 23 rejects `#3` but accepts `static int h2() { return sizeof(v); }` in a function body; see [[expr.prim.id]] for details. The uncontroversial way to write it is `sizeof(std::declval<A&>().v)`, or simply write the type.
</details>

!!! question "2. If `(E)` has the same type and value category as `E`, why do `decltype((x))` and `decltype(x)` differ?"

<details markdown="1">
<summary>Answer</summary>

`decltype` has two sets of rules ([[dcl.type.decltype]]): when the operand is an unparenthesized *id-expression* or class member access, it gives the declared type of the named entity; otherwise it is computed from the expression's type and value category, and an lvalue gives `T&`. `x` and `(x)` are identical as expressions, both lvalues of type `int`; the difference is that `decltype` looks at the syntactic form. This is exactly the exception meant by "except as otherwise indicated" in ¶1.
</details>
