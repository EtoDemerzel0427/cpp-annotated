---
title: Scope
summary: "A scope is a region of the program; this page covers where a declaration takes effect, which scope a name is placed in, and when two declarations of the same name are a redeclaration, an overload, or a conflict."
updated: 2026-10-19
---

!!! tldr
    - A scope is a region of the program text, and scopes nest to form a tree. Name lookup starts at the point of use and searches outward along this tree.
    - A declaration takes effect from its point of declaration. A variable's locus is after its complete declarator and before its initializer, so the `x` on the right of `int x = x;` is the variable itself; a range-based `for`'s locus is after the expression to the right of the colon, so the `x` on the right of `for (int x : x)` is the outer one.
    - Two declarations of the same name in the same scope either declare the same entity (a redeclaration), form an overload, or conflict. The decision rests on two concepts: correspond and potentially conflict.
    - The outermost block of a function body can't redeclare a parameter, and the outermost block of an `if` or `for` body can't redeclare a variable from the condition; one more nested block makes it fine.
    - Since C++26, local variables, structured bindings and the like can be named `_` repeatedly without conflict.

## A scope is a region of the program [basic.scope.scope]

```cpp
int a;                          // global scope
namespace N {                   // namespace scope of N
  struct S {                    // class scope of S
    void f(int p) {             // function parameter scope of f; p is here
                                // the function body is a block scope
      for (int i = 0; i < p; ++i) {  // block scope of the for statement; i is here
        int k = i;              // the loop body is another block scope
      }
    }
  };
}
```

¶1 Declarations in a program appear in **scopes**. The **global scope** contains the entire program; every other scope is introduced by a declaration, parameter list, statement, `catch` clause, lambda expression or contract assertion that appears in another scope, which **contains** it. So all scopes form a tree whose root is the global scope.

A scope is in general discontiguous. The same namespace can be opened in many places, and member functions can be defined outside their class; all these fragments belong to the same scope.

For a given point in the program, every scope that contains it is an **enclosing scope** of it, and the smallest of them is its **immediate scope**. In the example above, the immediate scope at `int k` is the block scope of the loop body.

C++ has eight kinds of scope in all, each explained below:

| Scope | Introduced by | Details |
|---|---|---|
| Block scope | compound statements; `if`, `switch`, iteration statements and their substatements; `catch` clauses | [[basic.scope.block]] |
| Function parameter scope | parameter lists | [[basic.scope.param]] |
| Lambda scope | lambda expressions | [[basic.scope.lambda]] |
| Namespace scope | namespace definitions; the global scope is also of this kind | [[basic.scope.namespace]] |
| Class scope | class definitions | [[basic.scope.class]] |
| Enumeration scope | enumeration definitions | [[basic.scope.enum]] |
| Template parameter scope | template declarations | [[basic.scope.temp]] |
| Contract-assertion scope {{c++26}} | `pre`, `post`, `contract_assert` | [[basic.scope.contract]] |

### Intervening scopes

¶1 ends by defining a relation. Let scope S not contain program point P; a scope X **intervenes** between P and S if X is or contains S but does not contain P. Intuitively, walk outward from S one level at a time until you hit a scope that contains P; the scopes passed on the way (including S itself) are the intervening ones.

This concept is mainly used to decide whether a local variable of an enclosing function can be used somewhere ([[g:odr-usable]], [[basic.def.odr#10]]):

```cpp run error
void f(int n) {
  struct L {
    int g() { return n; }       // error
  };
  auto h = [] { return n; };    // error
  auto k = [=] { return n; };   // OK
}
```

Walking outward from `g`'s body to the scope containing `n` passes through `g`'s body, `g`'s function parameter scope, `L`'s class scope and `f`'s body. The rule only allows the intervening scopes to be block scopes, contract-assertion scopes, parameter scopes of lambdas or requires-expressions, or the lambda scope of a lambda that captures the variable. Class scopes and the parameter scopes of ordinary functions are not on that list, so `g` can't use `n`; `h` doesn't capture `n`, so it can't use it either; `k` captures with `[=]`, so it can.

## Where a declaration takes effect [basic.scope.pdecl]

Every declaration has a **locus** ([[g:locus]]). Name lookup only finds declarations whose locus is before the point of use (for the precise wording see [[basic.lookup#2|precedes]]). For declarations formed with a declarator, such as variables and functions, the locus is as follows.

¶1 The locus is immediately after the complete declarator, that is, before the initializer.

<div class="compare" markdown="1">

```cpp ub
unsigned char x = 12;
void f() {
  unsigned char x = x;
  // the x on the right is the x being declared
}
```

```cpp run ok
const int i = 2;
void g() {
  int i[i];
  // the i in the brackets is the outer i
  static_assert(sizeof i
                == 2 * sizeof(int));
}
```

</div>

On the left, the inner `x`'s locus is before the `=`, so the `x` in the initializer is the inner `x` itself. Its lifetime hasn't begun yet, so reading it is undefined behavior ([[basic.life]]). This isn't C++26 erroneous behavior: erroneous behavior concerns variables whose lifetime has begun but that haven't been initialized ([[basic.indet]]). Clang warns about this line with `-Wuninitialized`.

¶2 On the right, the declarator `i[i]` isn't complete until the `]`, so the `i` in the brackets can't find the inner `i` yet and finds only the outer constant 2. This is a note: an outer name remains visible up to the locus of the declaration that hides it.

### Loci of other declarations (¶3–¶15)

| ¶ | Declaration | Locus | Consequence |
|---|---|---|---|
| 3 | class definition | after the class name in the class-head | the class name can be used in the base-clause and the class body: `struct Node { Node* next; };` |
| 3 | enumeration definition | after the enum-head | the enum name can be used in enumerator initializers |
| 3 | opaque enum declaration, alias declaration | after the whole declaration | the `T` on the right of `using T = T;` is the outer `T` |
| 4 | using-declarator (not naming a constructor) | after it | |
| 5 | enumerator definition | after it | an enumerator's own initializer can't see itself |
| 7 | elaborated-type-specifier as a declaration (`struct X;`) | after it | |
| 8 | injected-class-name (the class name's binding within its own class) | after the opening brace of the class definition | |
| 9 | `__func__` | before the function body | |
| 10 | structured binding | after the identifier list in brackets | already visible in the initializer, but may not be referenced ([[dcl.struct.bind]]) |
| 11 | loop variable of range-based `for` and expansion statements {{c++26}} | after the expression to the right of the colon | the `x` on the right of `for (int x : x)` is the outer one |
| 12 | template parameter | after it | |
| 13 | result name of a postcondition {{c++26}} | after it | |
| 14 | concept definition | after the concept name | |
| 15 | named namespace definition | after the name | |

An enumerator is the opposite of an ordinary variable: its locus is after the whole definition:

```cpp run ok
const int x = 12;
void b() {
  enum { x = x };          // the x on the right is the outer constant 12
  static_assert(x == 12);
}
int main() { b(); }
```

Range-based `for` works the same way. The loop variable isn't visible to the right of the colon, so iterating over a variable with the same name is valid, though not recommended:

```cpp run ok
#include <vector>
std::vector<int> x = {1, 2, 3};
int main() {
  int s = 0;
  for (int x : x) s += x;   // the x to the right of the colon is the global vector
  return s - 6;
}
```

A structured binding's locus is after the identifier list, so a same-named name in the initializer refers to the binding being declared, and [[dcl.struct.bind]] forbids such a reference:

```cpp error
struct P { int a, b; };
P p{1, 2};
void sb() {
  auto [p, q] = p;   // error: the p in the initializer is the binding being declared
}
```

A template parameter isn't yet visible in its own default argument, but is visible in later parameters:

```cpp run ok
typedef unsigned char T;
template<class T
  = T               // the outer typedef ::T
  , T               // the template parameter T
    N = 0> struct A { };
static_assert(sizeof(A<int>) == 1);
int main() { }
```

¶14 A concept's locus is after the concept name, so the concept's constraint-expression hides outer entities of the same name; Note 3 adds that the constraint-expression can't use the concept name, so a concept can't be defined recursively. Clang reports "concept definition cannot refer to itself" for `template<class T> concept C = C<T>;`.

¶6 A class member can be found in the class scope as soon as it is declared, even before the class is complete:

```cpp run ok
struct X {
  enum E { z = 16 };
  int b[X::z];          // OK: z is already declared
};
int main() { }
```

¶16 is a note restating two special cases covered later: a friend declaration can introduce a function or class that belongs to an enclosing namespace or block scope, but binds no name anywhere ([[class.friend]]); a function declaration or `extern` variable declaration in block scope introduces an entity belonging to the nearest enclosing namespace, but its name isn't bound in that namespace.

## Which scope a declaration goes into: inhabit, target and bind

```cpp run ok
namespace X {
  void p() {
    void q();     // declares X::q, but the name q can only be found in p's body
    q();          // OK
  }
  void r() {
    // q();       // error: q can't be found here
  }
  void q() { }    // defines the same X::q
}
int main() { X::p(); }
```

The function declared by the block-scope `void q();` belongs to namespace `X`, yet the name can only be found in that block. To describe such cases, the standard splits the relation between a declaration and scopes into three things.

¶2 Unless otherwise specified:

- ¶2.1 the smallest scope that contains a scope S is the **parent scope** of S;
- ¶2.2 no two declarations (re)introduce the same entity;
- ¶2.3 each declaration **inhabits** ([[g:inhabit]]) the immediate scope at its locus;
- ¶2.4 a declaration's **target scope** ([[g:target-scope]]) is the scope it inhabits;
- ¶2.5 any names (re)introduced by a declaration are **bound** to it in its target scope.

In addition, the **host scope** of a declaration is the block scope it inhabits, if it inhabits one, and otherwise its target scope. An entity **belongs to** a scope S if S is the target scope of a declaration of the entity.

By default, the inhabited scope, the target scope and the scope the name is bound in are the same. All the complicated cases are exceptions, listed in Note 1:

| Item | Exception | Example |
|---|---|---|
| 2.6 | A template parameter scope is the parent scope only of other template parameter scopes | see [[basic.scope.temp]] |
| 2.7 | Corresponding declarations with appropriate linkage declare the same entity | `extern int x;` in two translation units ([[basic.link]]) |
| 2.8 | The declaration in a template-declaration inhabits the scope the template-declaration is in | in `template<class T> void f();`, `f` inhabits the namespace scope |
| 2.9 | Friend declarations and declarations of template specializations don't bind names; declarations with qualified names target the scope the qualifier specifies; other friend declarations and certain elaborated-type-specifiers target a larger enclosing scope | `friend void h();` declares `h` in the enclosing namespace, but ordinary lookup can't find it; only ADL can |
| 2.10 | Block-scope `extern` declarations and function declarations target a larger enclosing scope, but bind the name in their immediate scope | the `void q();` above |
| 2.11 | The names of enumerators of an unscoped enumeration are bound in the two innermost enclosing scopes | after `enum E { a };`, both `a` and `E::a` work |
| 2.12 | A class's name is also bound in the class's own scope | [[g:injected-class-name]] |
| 2.13 | The names of anonymous union members are bound in the union's parent scope | after `union { int i; float f; };`, `i` can be used directly |

## Same-named declarations: redeclaration, overload or conflict

```cpp run ok
typedef int Int;
enum E : int { a };
void f(int);        // #1
void f(Int) {}      // defines #1: Int is int
void f(E) {}        // another overload: E and int are different types
int main() {}
```

When two declarations of the same name appear in the same scope, there are three possible outcomes: they declare the same entity (a redeclaration), they are different overloads under the same name, or they conflict and make the program ill-formed. The standard decides using two concepts: **correspond** ([[g:correspond]]) and **potentially conflict** ([[g:potentially-conflict]]).

### Correspond (¶4)

¶4 Two declarations **correspond** if they (re)introduce the same name, both declare constructors, or both declare destructors, unless

- ¶4.1 either is a using-declarator;
- ¶4.2 one declares a type (not a typedef-name) and the other declares a variable, non-static data member other than of an anonymous union, enumerator, function, or function template; or
- ¶4.3 each declares a function or function template and they do not declare corresponding overloads.

Two function declarations declare **corresponding overloads** if:

- ¶4.4 they have the same parameter-type-list (ignoring object parameters, footnote 14), equivalent trailing requires-clauses (if any), and, if both are non-static members, corresponding object parameters (see below);
- ¶4.5 for function templates, corresponding signatures, equivalent template-heads, and equivalent trailing requires-clauses.

Correspond means the two declarations occupy the same slot under the same name. So:

- corresponding and declaring the same entity is a redeclaration ([[basic.link#8]]);
- corresponding but declaring different entities is a potential conflict (see below), and the program is ill-formed;
- not corresponding means they can coexist, like overloads with different parameters.

¶4.2 comes from C compatibility. C allows a struct `stat` and a function `stat` to coexist with the same name, and POSIX uses exactly that. In C++ a type and a function don't correspond, so they can share a name; lookup prefers the non-type name ([[basic.lookup#4]]), and to refer to the type you must write `struct stat`:

```cpp run ok
struct stat { int size; };
int stat(const char*, struct stat*);   // a type and a function with the same name: valid
int main() {
  struct stat s{};
  return s.size;
}
```

Note 2 points out that two declarations can correspond even if neither binds a name:

```cpp run ok
struct A {
  friend void f();      // #1: binds no name; targets the global namespace
};
struct B {
  friend void f() {}    // corresponds to #1 and defines it
};
int main() { }
```

### Object parameters of member functions (¶3)

Non-static member functions also have their object parameters compared, i.e. the type of `*this`. C++23's explicit object parameters (`this X& self`, [[P0847R7]]) complicated this, so paragraph 3 gives a dedicated definition.

¶3 Two non-static member functions have **corresponding object parameters** if:

- ¶3.1 exactly one is an implicit object member function with no ref-qualifier and the types of their object parameters, after removing references, are the same, or
- ¶3.2 their object parameters have the same type.

The rules for member function templates (items 3.3 and 3.4) are the same, with "same" replaced by "equivalent". Two function templates have **corresponding signatures** if their template-parameter-lists have the same length, their corresponding template parameters are equivalent, they have equivalent non-object-parameter-type-lists and return types, and, if both are members, they have corresponding object parameters.

Why does item 3.1 remove references? A `void g();` with no ref-qualifier can be called on both lvalue and rvalue objects, so it overlaps both the `&` version and the `&&` version, and can't coexist with either. Here is the standard's Example 2 with comments added:

```cpp error
struct X {
  static void f();
  void f() const;          // error: redeclaration
  void g();
  void g() const;          // OK: object parameters X& and const X& differ
  void g() &;              // error: corresponds to g()

  void h(this X&, int);
  void h(int) &&;          // OK: X& and X&& differ
  void j(this const X&);
  void j() const &;        // error: both const X&
  void k();
  void k(this X&);         // error: corresponds to k()
};
```

- `f`: one static, one non-static. Item 4.4's condition on object parameters applies only when both are non-static members, so only the non-object parameters are compared; both are empty, so they correspond. They are two different entities, so they conflict. This is the basis for the rule that you can't overload on `static` alone ([[over.load]]).
- `g() &`: `g()` has no ref-qualifier, so by item 3.1, after removing references both are `X`; they correspond.
- `h`: both have references, so item 3.1 doesn't apply; `X&` and `X&&` differ, so they don't correspond.
- `k(this X&)`: `k()` has no ref-qualifier; after removing references both are `X`; they correspond.

### Potentially conflict (¶6)

¶6 Two declarations **potentially conflict** if they correspond and cause their shared name to denote different entities.

!!! std
    The program is ill-formed if, in any scope, a name is bound to two declarations A and B that potentially conflict and A precedes B ([basic.lookup]), unless B is name-independent.

If, in any scope, a name is bound to two declarations that potentially conflict, the program is ill-formed, unless the later one is a name-independent declaration (see the next section). Redefinitions, same-named symbols of different kinds, and conflicting declarations all fall under this rule. The standard's Example 3:

```cpp error
void f() {
  int x,y;
  void x();             // error: x corresponds to int x but denotes a different entity
  int y;                // error: redefinition
}
enum { f };             // error: the enumerator f corresponds to the function ::f
namespace A {}
namespace B = A;
namespace B = A;        // OK: both refer to namespace A
namespace B = B;        // OK: likewise
namespace A = B;        // OK: the name A refers to namespace A both times
namespace B {}          // error: B is an alias of A, but this declares a new namespace B
```

`enum { f }` is an error because item 4.2 only exempts the type/non-type combination, and neither an enumerator nor a function is a type.

!!! impl "Clang rejects `namespace A = B;`"
    Clang 23 reports "redefinition of 'A'" for `namespace A = B;`. Under the current draft, an alias denotes its underlying entity ([[basic.pre#8]]), both declarations of the name `A` refer to namespace `A`, and they don't potentially conflict; the standard's example also marks it OK. This line is where Clang disagrees with the standard; Clang's verdicts on the other lines match the standard.

Note 4 notes that through using-directives or operator lookup, potentially conflicting declarations may be found from different scopes; they then enter overload resolution together, and the result is usually ambiguous.

### Name-independent declarations `_` (¶5) {{c++26}}

```cpp run ok
#include <mutex>
std::mutex m1, m2;
int main() {
  std::lock_guard _(m1);
  std::lock_guard _(m2);   // both locks are held until the end of the scope
}
```

Many variables exist only for their side effects and their names don't matter, like the locks above or the unneeded part of `auto [_, ok] = s.insert(v);`. Before C++26, each such variable in the same scope needed a different name ([[P2169R4]]).

¶5 A declaration whose name is `_` is **name-independent** if it declares

- ¶5.1 a variable with automatic storage duration, other than a function parameter;
- ¶5.2 a structured binding with no storage-class-specifier and not inhabiting a namespace scope;
- ¶5.3 the result binding of a postcondition ([[dcl.contract.res]]);
- ¶5.4 the variable introduced by an init-capture;
- ¶5.5 a non-static data member of other than an anonymous union.

By paragraph 6, it is not a conflict if the later declaration is name-independent. Both `_` exist, both live until the end of the scope, and they are destroyed in reverse order of declaration; it's just that the name `_` can't be used unambiguously afterwards (Note 3):

```cpp error
void g() {
  int _;
  _ = 0;                // OK: only one _
  int _;                // OK: name-independent declaration
  _ = 0;                // error: two _s, lookup is ambiguous
}
void h() {
  int _;                // #1
  _++;                  // OK
  static int _;         // error: a static variable isn't name-independent; conflicts with #1
}
```

¶5 also has a recommendation: implementations should not emit a warning that a name-independent declaration is used or unused.

## Block scope [basic.scope.block]

¶1 Each of the following introduces a **block scope** that includes it:

- ¶1.1 a selection statement (`if`, `switch`), iteration statement, or expansion statement (`template for` {{c++26}});
- ¶1.2 a substatement of such a statement;
- ¶1.3 a handler (`catch` clause);
- ¶1.4 a compound statement that is not the compound-statement of a handler.

Note 1 adds that a substatement that is itself a compound statement counts as only one block scope. A variable that belongs to a block scope is a **block variable**.

Selection and iteration statements introduce scopes themselves, so variables declared in `for (int i = 0; ...)` or `if (auto p = get(); p)` disappear when the statement ends:

```cpp run ok
int i = 42;
int a[10];
int main() {
  for (int i = 0; i < 10; i++)   // this i belongs to the block scope of the for statement
    a[i] = i;
  int j = i;                     // j == 42: the for's i is no longer visible
  return j - 42;
}
```

A handler's compound statement doesn't start a separate scope, so the two `e`s in `catch (E e) { int e; }` are in the same scope and conflict directly.

### No redeclaring at the outermost level (¶2)

¶2 If a declaration that is not name-independent, in one of the following block scopes S, potentially conflicts with a declaration whose target scope is the parent scope of S, the program is ill-formed:

- ¶2.1 the compound-statement of a lambda, function body, or function-try-block;
- ¶2.2 a substatement of a selection, iteration or expansion statement that is not itself a selection, iteration or expansion statement;
- ¶2.3 a handler of a function-try-block.

Ordinary hiding is allowed; this rule specifically forbids three kinds of hiding: the outermost block of a function body hiding a parameter, the outermost block of an `if` or `for` body hiding a variable from the condition, and a function-try-block's `catch` hiding a parameter. Such hiding is almost always a typo:

```cpp error
int f();
void t1() {
  if (int x = f()) {
    int x;            // error: conflicts with the x in the condition
  } else {
    int x;            // error: likewise
  }
}
void t2(int p) {
  int p = 1;          // error: outermost block of the function body conflicts with the parameter
}
void t3(int p) try { } catch (...) {
  int p = 0;          // error: the function-try-block's catch conflicts with the parameter
}
void t4() {
  for (int i = 0; i < 3; ++i) {
    { int i = 5; (void)i; }   // OK: one more nested block, ordinary hiding
  }
}
```

This rule only looks at the direct parent scope; one more nested block makes it valid hiding.

## Function parameter scope [basic.scope.param]

¶1 Each parameter list introduces a **function parameter scope**. How far it extends depends on what the parameter list belongs to:

- ¶1.1 an ordinary function declarator: to the end of the whole declaration or function definition, but not including the locus of the declarator itself. Note 2 adds that a member function's parameter scope is nested within its class scope;
- ¶1.2 a lambda: to the end of the lambda body;
- ¶1.3 a requires-expression's parameter list: to the end of the requires-expression;
- ¶1.4 a deduction guide: to the end of the deduction guide.

So parameters are visible in the trailing return type, the requires-clause, the `noexcept` specifier and the function body. Note 1 points out that a parameter's value can't be used in the parameter list ([[dcl.fct.default]]), but it can appear in unevaluated operands:

```cpp error
auto tr(int n) -> decltype(n) { return n; }   // OK: parameters usable in the trailing return type
void d1(int a, int b = sizeof(a));            // OK: unevaluated operand
void d2(int a, int b = a);                    // error: default argument uses the parameter's value
template<class T> void g(T t) noexcept(noexcept(t.swap(t)));  // OK
```

## Lambda scope [basic.scope.lambda]

A lambda expression introduces a **lambda scope** that starts immediately after the bracketed capture part (the lambda-introducer) and extends to the end of the body. The whole capture list, including the initializers of init-captures, is outside the lambda scope; but [[expr.prim.lambda.capture#6]] specifically says that the variable declared by an init-capture inhabits the lambda scope. It follows that:

- a same-named name in an init-capture's initializer refers to the outer entity, which is why `[x = std::move(x)]` works;
- the name of an init-capture is visible in the parameter list, the return type and the body;
- a parameter with the same name as an init-capture conflicts, so `[a = 42](int a) { }` is ill-formed.

```cpp run ok
int main() {
  int p = 1;
  auto l = [p = p + 1] { return p; };  // the p in the initializer is the outer variable; l() == 2
  auto c = [i = 0]() mutable -> decltype(i) { return i++; };
  return l() - 2 + c();
}
```

The lambda scope is also the checkpoint for using outer local variables (see intervening scopes above): a local variable can be odr-used in a lambda only if the lambda captures it, or has a capture-default.

## Namespace scope and class scope

¶1 ([basic.scope.namespace]) Every definition of a namespace introduces the same **namespace scope**, which includes the namespace-body of every definition of it. The global scope is the namespace scope of the global namespace.

¶1 ([basic.scope.class]) Each declaration of a class or class template introduces a **class scope**, which includes the member-specification of the class definition.

Both have the same second half: if a redeclaration or specialization (other than a friend) targets this scope or a scope within it, the portion of the declaration after the declared name also belongs to this scope. So when a member is defined outside its class or namespace, the parameter list after the function name, the trailing return type and the function body can use the members of that class or namespace unqualified, but a return type written before the function name can't:

```cpp run ok
namespace Q {
  namespace V { void f(); }
  void V::f() {         // the part after V::f belongs to V's scope
    void h();           // declares Q::V::h
  }
}
struct S { using T = int; T get(); };
S::T S::get() {         // the return type comes before S::get, so write S::T
  T t = 0;              // T can be used directly in the body
  return t;
}
int main() { }
```

Friend declarations are excluded, so the `F` in `friend void A::f(F);` is not automatically looked up in `A`; [[basic.lookup.unqual#6]] has a separate rule for it.

A class scope covers only the member-specification in the class definition. Note 1 points out that a lookup from a point before the class definition finds nothing in the class scope. The standard's Example 1:

```cpp error
template<class D>
struct B {
  D::type x;            // #1
};

struct A { using type = int; };
struct C : A, B<C> {};  // error at #1: C::type not found
```

`B<C>` is instantiated because it is used in `C`'s base-clause, and its point of instantiation is before the definition of `C` ([[temp.point]]). Looking up `C::type` from there finds nothing in `C`'s class scope, and the same goes for the `type` inherited from `A`. So a CRTP base class template can't use the derived class's members in its member declarations. Member function bodies can, because they are instantiated after the derived class definition is complete.

## Enumeration scope [basic.scope.enum]

¶1 Each enumeration declaration introduces an **enumeration scope**, which includes the enumerator-list of the enumeration definition.

Enumerators all inhabit the enumeration scope. The names of enumerators of a scoped enumeration (`enum class`) are bound only there, so you must write `E::a`; the names of enumerators of an unscoped enumeration are also bound in the enclosing scope, so both `a` and `E::a` work.

## Template parameter scope [basic.scope.temp]

¶2 Each template declaration introduces a **template parameter scope** that starts at the template parameter list and extends to the end of the template declaration.

This scope is a little special. In `template<class T> struct A { ... };`, `A` should obviously be a member of the enclosing namespace, not of the template parameter scope; and the parent scope of `A`'s class scope should also be that namespace. So paragraph 2 specifies:

- a declaration outside the template parameter list that would otherwise inhabit the template parameter scope inhabits the scope of the template declaration instead;
- the parent scope of any scope that is not a template parameter scope is the smallest scope containing it that is not a template parameter scope.

Note 1 sums up: only template parameters belong to a template parameter scope, and only template parameter scopes have a template parameter scope as their parent. Looking outward from inside a class body still has to find `T`; [[basic.lookup.unqual]] and [[temp.local#7]] specify when the template parameter scope is considered.

¶1 A template template parameter's own parameter list also introduces a template parameter scope, covering only its own template-head. The `U` in `template<template<class U> class TT>` is valid only within `TT`'s template-head.

A template parameter's name can't be redeclared within its scope ([[temp.local]]):

```cpp error
template<class T> struct A { int T; };          // error: member T has the same name as the template parameter
template<class T> void ff(T) { int T = 0; }     // error: likewise
template<class T> struct S2 { void m(); };
template<class U> void S2<U>::m() { }           // OK: an out-of-class definition may use a different parameter name
```

## Contract-assertion scope [basic.scope.contract] {{c++26}}

¶1 Each contract assertion (`pre(...)`, `post(...)`, `contract_assert(...)`, [[basic.contract]]) introduces a **contract-assertion scope** that includes the assertion.

A postcondition can name the return value, like the `r` in `post(r: r > 0)`. With this scope, `r` is visible only in that postcondition and doesn't leak into the function body. At the same time, a contract-assertion scope can be crossed to use outer local entities ([[basic.def.odr#10]]), so an assertion can use function parameters directly.

¶2 If a result name that is not name-independent potentially conflicts with a declaration in one of the following scopes, the program is ill-formed:

- ¶2.1 the function parameter scope of the function it belongs to;
- ¶2.2 if the postcondition belongs to a lambda, the nearest enclosing lambda scope.

```cpp
int f(int x) post(r: r > x);    // OK
int g(int r) post(r: r > 0);    // error: result name r conflicts with parameter r
auto l = [r = 1](int) post(r: r > 0) { return 1; };  // error: conflicts with init-capture r
```

At the time of writing Clang 23 doesn't support contract syntax; this code was analyzed against the standard and not verified by compiling.

## Nominable (¶7)

¶7 At a program point P, a declaration is **nominable** in a class, class template or namespace E if it meets these three conditions:

- it precedes P;
- it does not inhabit a block scope;
- its target scope is the scope of E, or, if E is a namespace, any element of the inline namespace set of E ([[namespace.def]]).

Nominability decides whether it can be redeclared or defined outside in the form `E::name` ([[dcl.meaning]]). The standard's Example 4:

```cpp run ok
namespace A {
  void f() {void g();}
  inline namespace B {
    struct S {
      friend void h();
      static int i;
    };
  }
}
int main() { }
```

At the end of the example, the declarations of `f`, `B`, `S` and `h` are nominable in `A`, while those of `g` and `i` are not. `g` inhabits a block scope; `i`'s target scope is `S`'s class scope. `h` is written inside the class, but a friend declaration targets the nearest enclosing namespace `B`, and `B` is an inline namespace of `A`.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

¶8 ([basic.scope.scope]) When a templated entity is instantiated, any scope introduced by any part of the template definition is considered to be introduced by the instantiated entity and to contain the instantiations of any declarations that inhabit it. For example, the members of `A<int>` inhabit the class scope of `A<int>`.

¶17 ([basic.scope.pdecl]) is a note: the point of instantiation of a template is specified separately in [[temp.point]].

</details>

## The implementation's view

!!! impl "How compilers represent scopes"
    - Clang's AST uses two structures for scopes: `Scope` objects pushed and popped during parsing, used for unqualified lookup; and the semantic `DeclContext` (namespaces, classes, functions, enumerations, lambda closure classes, etc.). A declaration's lexical context and semantic context can differ; for example, a member function defined outside its class is lexically in a namespace but semantically belongs to the class. This corresponds to the standard's distinction between the inhabited scope and the target scope.
    - Clang words potential conflicts several ways, such as "redefinition of 'x'", "redefinition of 'x' as different kind of symbol" and "class member cannot be redeclared"; all of them correspond to the single rule in [[basic.scope.scope#6]].
    - `-Wshadow` warns about valid hiding, such as a local variable hiding an outer variable or a member. The standard doesn't forbid such hiding.

## History

!!! history "From declarative regions to a tree of scopes"
    - Up to C++20, the standard used declarative regions and potential scopes to describe the text in which a name is valid, and "scope" meant the range in which a name is valid. Out-of-class definitions, friends, block-scope `extern`, injected-class-names, template parameters and other special cases each had their own paragraph, with quite a few gaps between them.
    - C++23 switched to today's model through [[P1787R6]]: a scope is a region of the program, and scopes form a tree; inhabiting, targeting and binding are described separately; correspond and potentially conflict unify the decisions about redeclarations and conflicts. Explicit object parameters ([[P0847R7]]) from the same period brought the definition of corresponding object parameters.
    - C++26 added name-independent declarations `_` ([[P2169R4]]), contract-assertion scopes and expansion statements.

## Common misconceptions

!!! pitfall "`int x = x;` initializes from the outer x"
    The locus is after the declarator and before the initializer, so the `x` on the right is the variable being declared, and reading it is undefined behavior. To use the outer variable, write `::x` or rename. Range-based `for` is the opposite: the `x` on the right of `for (int x : x)` is the outer one.

!!! pitfall "A function body can't hide a parameter"
    Only the outermost block of the function body can't. `void f(int p) { int p; }` is ill-formed, while `void f(int p) { { int p; } }` is valid hiding.

!!! pitfall "Member functions can be overloaded on `static` or on the presence of a ref-qualifier alone"
    `static void f();` and `void f() const;` correspond and can't coexist; neither can `void g();` and `void g() &;`. To overload on value category, every version must have a ref-qualifier.

## Questions

!!! question "Question 1"
    Which of these member declarations are ill-formed?

    ```cpp
    struct S {
      void a() &;
      void a() &&;
      void b();
      void b(this S);
      void c(this S&);
      void c() &&;
      static void d(int);
      void d(double);
    };
    ```

<details markdown="1">
<summary>Answer</summary>

- `a() &` and `a() &&`: both have ref-qualifiers, so item 3.1 doesn't apply; `S&` and `S&&` differ, so they don't correspond. OK.
- `b()` and `b(this S)`: `b()` has no ref-qualifier, so by item 3.1, after removing references both are `S`, and the object parameters correspond; the non-object parameters are both empty, so they are corresponding overloads. They are two different entities: ill-formed.
- `c(this S&)` and `c() &&`: `c() &&` has a ref-qualifier, so item 3.1 doesn't apply; `S&` and `S&&` differ. OK.
- `d(int)` and `d(double)`: different non-object parameters, so they don't correspond. OK.

Clang 23 reports an error only for `b(this S)`.
</details>

!!! question "Question 2"
    ```cpp
    const int n = 3;
    void f() {
      int n[n] = {};
      int m = sizeof(n);
      enum { n2 = n };
    }
    ```
    What is the value of `m`? Is `enum { n2 = n }` valid?

<details markdown="1">
<summary>Answer</summary>

The locus of `int n[n]` is after the complete declarator, so the `n` in the brackets is the outer constant 3, and the declaration declares an `int[3]`. From then on `n` refers to this array, so `m == 3 * sizeof(int)`, which is 12 on platforms where `int` is 4 bytes.

The `n` in `enum { n2 = n }` is that local array, which is not an integral constant expression and can't be an enumerator's initializer, so it is ill-formed.
</details>
