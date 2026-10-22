---
title: Expression splicing
summary: "In C++26 static reflection, writing a constant std::meta::info as [: r :] puts it back in expression position: it can yield a function, variable, data member, base class subobject, enumerator or value, and it differs from an ordinary name in a few key ways."
updated: 2026-10-19
---

!!! tldr
    - `^^x` turns a construct of the program into a value of type `std::meta::info`, and `[: r :]` turns such a constant value back into the construct it represents; a `[: r :]` in expression position is a splice-expression. {{c++26}}
    - What `[: r :]` yields depends on what `r` represents: a function gives an overload set, variables and data members give lvalues, enumerators and values give prvalues, and things like types and namespaces can't be used as expressions.
    - Unlike an ordinary name, a `[: r :]` that designates a non-static member is not automatically turned into `this->m`, and no access checking is done.
    - You can't splice an enclosing function's local variable inside a lambda in an evaluated way; as a template argument it must be parenthesized: `([: r :])`.

!!! warning "Compiler support"
    Clang 23 doesn't support the `^^` and `[: :]` syntax. The examples on this page are analyzed from the draft and have not been verified by compiling, so none of them has a verdict mark. You can experiment with the experimental Clang branch for P2996 on Compiler Explorer.

## Reflection and splicing

Static reflection ([[P2996R13]]) provides a pair of opposite operations:

- The **reflection operator** ([[g:reflection-operator|reflection operator]]) `^^` ([[expr.reflect]]): `^^x` is a prvalue of type `std::meta::info` representing the variable `x`; `^^int` represents the type `int`; `^^S::m` represents the data member `S::m`.
- The **splice specifier** ([[g:splice-specifier|splice specifier]]) `[: r :]` ([[basic.splice]]): what is inside the bracket-colons must be a constant expression of type `std::meta::info`, and the construct it represents is the construct the specifier **designates**.

```cpp
struct S { int m; };

void f(S s) {
  constexpr std::meta::info r = ^^S::m;
  s.[: r :] = 42;          // equivalent to s.m = 42
}
```

`r` must be a constant, because what `[: r :]` is (a variable or a function, of which type) determines how the surrounding code is parsed and type-checked, so the compiler must know its value at compile time. Parameters of a `consteval` function are not constant expressions, so `consteval int get(std::meta::info v) { return [: v :]; }` is ill-formed ([[basic.splice]] Example 1). The reflection value needs to be passed as a template argument, or used inside an expansion statement `template for`.

Splices can appear in several syntactic positions: types (`typename [: r :]`, [[dcl.type.splice]]), nested-name-specifiers (`[: r :]::x`), template names, and so on. This subclause deals only with splices that appear as expressions:

```text
splice-expression:
    [: r :]                       // splice-specifier
    template [: r :]              // designates a function template
    template [: r :]< args >      // a specialization of a function template or variable template
```

## When `[: :]` is not an expression (¶1)

¶1 A *splice-specifier* immediately followed by `::`, or preceded by `typename`, is never interpreted as a splice-expression. The former is a nested-name-specifier, the latter a type. This is a purely syntactic rule: when the parser sees `[:` it doesn't know what is inside, so it can only decide from the surrounding tokens.

Example 1 in the standard (with comments added):

```cpp
struct S { static constexpr int a = 1; };
template<typename> struct TCls { static constexpr int b = 2; };

constexpr int c = [:^^S:]::a;                   // OK: followed by ::, a nested-name-specifier
constexpr int d = template [:^^TCls:]<int>::b;  // OK: same
template<auto V> constexpr int e = [:V:];       // OK: a splice-expression dependent on a template parameter
constexpr int f = template [:^^e:]<^^S::a>;     // OK: a variable template specialization, value 1

constexpr auto g = typename [:^^int:](42);      // OK: preceded by typename, a type; this is a functional cast

constexpr auto h = ^^g;
constexpr auto i = e<[:^^h:]>;                  // error: unparenthesized splice-expression as a template argument
constexpr auto j = e<([:^^h:])>;                // OK
```

The rule for the last two lines is in [[temp.arg.general#10]]: the constant expression of a template argument can't be an unparenthesized splice-expression. A template argument can be a type, an expression or a template, and `[:^^h:]` alone doesn't tell which; with parentheses, only an expression can be inside, which removes the ambiguity. The rule applies only when the entire argument is `[: r :]`; `S<[:r:] + 1>` is unaffected.

## What `[: r :]` yields (¶2)

¶2 Let S be the construct designated by `[: r :]`. The table lists the results in the order of ¶2:

| S is | Result of the expression |
|---|---|
| A constructor, destructor, or unnamed bit-field | Ill-formed (¶2.1.1–¶2.1.3) |
| A local entity across a lambda (see below) | Ill-formed (¶2.1.4) |
| A function F | The overload set of the declarations of F, followed by overload resolution (¶2.2) |
| An object or non-static data member | An lvalue designating S, with the same type as S (¶2.3) |
| A direct base class relationship (D, B) | An lvalue of type B (¶2.4) |
| A variable or structured binding | An lvalue designating the corresponding object or function (¶2.5) |
| A value or enumerator | A prvalue computing S (¶2.6) |
| Anything else (types, namespaces, templates, concepts…) | Ill-formed (¶2.7) |

A few rows need explanation.

### No implicit `this->` (¶2.3)

In a member function, writing the name `m` of a non-static data member rewrites it to `(*this).m` ([[expr.prim.id.general#2]]). Note 1 says splice-expressions get no such rewrite:

!!! std
    The implicit transformation whereby an *id-expression* denoting a non-static member becomes a class member access does not apply to a *splice-expression*.

So a `[: r :]` designating a non-static data member can only be used in the three places [[expr.prim.id.general#4]] allows: as the right operand of a class member access (`obj.[: r :]`), to form a pointer to member (`&[: r :]`), and in an unevaluated operand.

```cpp
struct S { int m; };
int S::* k = &[:^^S::m:];            // OK: forms a pointer to member

void g(S s) {
  s.[:^^S::m:] = 42;                 // OK: class member access
  int n = sizeof([:^^S::m:]);        // OK: unevaluated operand
}

struct T {
  int m;
  void h() {
    [:^^T::m:] = 1;                  // error: not rewritten to this->m
    this->[:^^T::m:] = 1;            // OK
  }
};
```

The effect of this design is that the meaning of `[: r :]` depends only on `r`, not on which class's member function it happens to appear in. The typical use of splicing is iterating over a class's data members and accessing each one, and the object being accessed is written explicitly anyway.

### A function gives only its own declarations (¶2.2)

`^^f` represents one specific function: [[expr.reflect]] requires that `&f` select a unique function, otherwise `^^f` is ill-formed. So the overload set produced by the splice contains only the declarations of that one function (those preceding the expression, or, in a complete-class context, preceding the end of the outermost class definition); other overloads with the same name are not mixed in. Different declarations may give different default arguments, and that is mainly what overload resolution deals with here.

### Direct base class relationships (¶2.4)

Metafunctions such as `std::meta::bases_of` return reflections of direct base class relationships. Splicing such a reflection gives an lvalue of type B, and by [[expr.prim.id.general#5]] it can only be the second operand of a class member access: `d.[: base :]` is the B base class subobject of `d`. This accesses a base class subobject without writing the base class's name.

### Variables and structured bindings (¶2.5)

When S is a variable or structured binding, it must either have static or thread storage duration or inhabit a scope that encloses the expression. The latter prevents carrying the reflection of one function's local variable into another function and splicing it there, where the variable doesn't exist at all.

The result is an lvalue. If S is a reference, the result designates the referenced object or function directly, and the type loses the reference by [[expr.type]] (Note 2). When a contract assertion's predicate splices a variable declared outside the assertion, the type gets `const`, consistent with the rule for ordinary names ([[expr.prim.id.unqual#7]]).

Like an ordinary name, `return [: ^^x :];` can also move implicitly: [[expr.prim.id.unqual#15]] lists *splice-expression* alongside *id-expression* when defining move-eligibility.

### No splicing of local entities across a lambda (¶2.1.4)

¶2.1.4 says that if S is a **local entity** ([[g:local-entity|local entity]]: an automatic variable, parameter, structured binding, etc. in a function), a lambda scope intervenes between the expression and the declaration of S, and the expression would be potentially evaluated if the effect of enclosing `typeid`s were ignored, the expression is ill-formed.

```cpp
void f() {
  int x = 0;
  constexpr auto r = ^^x;
  [: r :] = 1;                        // OK: no lambda in between
  [&] { [: r :] = 2; }();             // error: splicing a local entity across a lambda
  [&] { (void)sizeof([: r :]); }();   // OK: unevaluated
}
```

The reason is lambda capture. Implicit capture in [[expr.prim.lambda.capture#7]] is determined by the names appearing in the lambda body; the compiler can decide what to capture just by scanning names. `[: r :]` contains only a constant expression, and constant evaluation is needed to know which variable it designates. To keep capture from depending on constant evaluation, the standard simply forbids this usage.

There is a matching restriction on the reflection side: [[expr.reflect#7]] says that if a lambda scope intervenes between `^^x` and the declaration of the local entity `x`, `^^x` is ill-formed; variables introduced by init-captures can't be reflected either. So inside a lambda you can neither reflect an enclosing local variable (even if captured) nor splice, in an evaluated way, a reflection of a local variable brought in from outside.

## The two forms with `template` (¶3–¶4)

¶3 `template [: r :]` requires `r` to designate a function template (not a constructor template). The result is the overload set of its declarations, and calls perform template argument deduction as usual.

`template` is mandatory here: when parsing `[: r :](5)` the compiler doesn't know whether `r` is a template, and `template` tells it to treat it as one. This is the same reasoning as writing `template` before a dependent name ([[temp.names]]).

¶4 `template [: r :]<args>` requires `r` to designate a template: a function template gives an overload set (with explicit template arguments); a variable template gives an lvalue for the corresponding specialization; other templates (class templates, alias templates, concepts) are ill-formed, since their specializations are not expressions.

```cpp
template<int V> constexpr int e = V;
template<class T> constexpr T twice(T t) { return t + t; }

constexpr int a = template [:^^e:]<3>;            // variable template specialization, an lvalue
constexpr int b = template [:^^twice:]<int>(4);   // function template, explicit template argument
constexpr int c = template [:^^twice:](5);        // the ¶3 form, deduces T = int
```

## Access checking (Note 4)

Note 4 makes two points. First, a class member designated through a splice-expression is accessible from any point ([[class.access.base]]). Access control takes effect when the reflection value is obtained, e.g. `std::meta::members_of` filters members by access context ([[meta.reflection.access.context]]); there is no further check when splicing.

Second, in `obj.[: r :]`, the left operand (considered as a pointer) must be implicitly convertible to a pointer to the **designating class** ([[g:designating-class|designating class]]) of the right operand, otherwise it is ill-formed. You can't access a member through an object of an unrelated type.

The first point is deliberate. Libraries for serialization, debug printing and the like need to see all of a class's members, and couldn't be implemented if splicing also checked access. The price is that anyone holding the reflection of a private member can access it, but such a bypass is written out explicitly and can be found in code review.

## Comparison with ordinary names

| | Name (id-expression) | splice-expression |
|---|---|---|
| How the entity is determined | Name lookup | A reflection value from constant evaluation |
| Implicit `(*this).` for non-static members | Yes | No |
| Access checking | At the point of use | None (checked when the reflection is obtained) |
| Using an enclosing local variable in a lambda | Triggers capture | Ill-formed when potentially evaluated |
| Function → overload set | All visible declarations with that name | Only this function's (template's) own declarations |
| As a template argument | Written directly | Must be parenthesized |
| Base class subobject | Only via conversion | `obj.[: base :]` |
| Implicit move on `return` | Yes | Yes |

## Implementation view

!!! impl
    - There is a Clang branch implementing P2996, maintained by Bloomberg, selectable on Compiler Explorer; EDG also has an experimental implementation. Clang 23 doesn't support it yet.
    - In implementations, `std::meta::info` is usually an opaque handle to a node in the compiler's internal syntax tree; it is meaningful only during constant evaluation and can't appear at run time.
    - When the `V` in `[: V :]` depends on a template parameter, the splice is deferred until instantiation ([[temp.dep.splice]]).

!!! history
    Before P2996, C++ had no way to turn something computed at compile time back into a name or expression, except through macros and template tricks. The reflection operator was originally spelled as a single `^`; because that conflicted with the syntax of Clang's blocks extension, it was changed to `^^`.

## Common mistakes

!!! pitfall "Forgetting the parentheses in a template argument"
    `foo<[: r :]>` is ill-formed; write `foo<([: r :])>`. When `r` represents a type, write `foo<typename [: r :]>`.

!!! pitfall "Splicing a data member directly in a member function"
    `[: member :]` doesn't become `this->[: member :]`; you have to write `this->[: member :]` yourself.

## Questions

!!! question "Question 1"
    Are the following three lines well-formed?
    ```cpp
    struct B { int x; };
    struct D : B { void f(); };
    void D::f() {
      constexpr auto r = ^^B::x;
      int a = x;              // #1
      int b = [: r :];        // #2
      int c = this->[: r :];  // #3
    }
    ```

<details markdown="1">
<summary>Answer</summary>

`#1` is well-formed: the name `x` is implicitly rewritten to `(*this).x` ([[expr.prim.id.general#2]]). `#2` is ill-formed: splice-expressions get no such rewrite (¶2.3 Note 1), so a non-static data member is used on its own in a potentially-evaluated position, violating [[expr.prim.id.general#4]]. `#3` is well-formed: it is a class member access, `this` converts implicitly to `B*`, and `B` is the designating class of the right operand.
</details>

!!! question "Question 2"
    Splicing an enclosing local variable in an evaluated way inside a lambda is ill-formed. If you first write `[x]` in the capture list and then write `^^x` in the lambda body and splice it, does that get around the restriction?

<details markdown="1">
<summary>Answer</summary>

No. The name `x` in the lambda body still denotes the local entity in the enclosing function (capturing only changes which object an odr-use accesses), and a lambda scope intervenes between it and `^^x`, so by 7.1.4 of [[expr.reflect#7]], `^^x` itself is ill-formed. Using the init-capture `[y = x]` doesn't work either: 7.1.1 forbids reflecting variables introduced by init-captures. When you need the variable in a lambda, just use its name; if you must go through reflection, do the splice outside the lambda.
</details>
