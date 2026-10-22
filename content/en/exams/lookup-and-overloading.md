---
title: Exam 3 · Name lookup, overload resolution and access control
summary: 25 questions on scopes and hiding, unqualified and qualified lookup, ADL and hidden friends, using-declarations and using-directives, member lookup under multiple inheritance, the ranking and tie-breaker rules of overload resolution, C++20's rewritten comparison operators, and where access control sits in the whole process.
tags: exam, name lookup, ADL, overload resolution, access control
updated: 2026-10-20
---

!!! tldr
    - Scope: scopes and hiding ([[basic.scope]]), unqualified, qualified and argument-dependent lookup ([[basic.lookup]]), using-declarations and using-directives, inline namespaces, member lookup under multiple inheritance ([[class.member.lookup]]), overload resolution ([[over.match]], [[over.ics.rank]]), rewritten operator candidates ([[over.match.oper]]), and access control ([[class.access]]).
    - One thread runs through the whole exam: name lookup first, then overload resolution, then the access check, and only last whether the selected function is deleted. The answer to many questions depends on which of these steps an error occurs in.
    - Two-phase lookup in templates, initialization and value categories, and constant evaluation are outside this exam; each has its own.
    - Suggested time: 90 minutes. For verdict questions, give the most severe verdict for the whole program; choice questions that ask about output have all been checked by actually running them.

## 1. Scopes, hiding and unqualified lookup

<div class="quiz" data-kind="verdict" data-answer="ok" markdown="1">

Judge the whole program.

```cpp run
int count_big(int limit) {
  int n = 0;
  for (int i = 0; i < limit; ++i) {
    int limit = i * 2;
    if (limit > 10) ++n;
  }
  return n;
}

int main() { return count_big(8); }
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: well-formed.**

The target scope of the parameter `limit` is the function parameter scope ([[basic.scope.param#1]]). The `for` statement itself introduces a block scope, and its body (a compound statement) introduces another block scope ([[basic.scope.block#1]]).

[[basic.scope.block#2]] forbids only two situations: redeclaring, in the outermost compound statement of a function body, a name that conflicts with its parent scope (the parameter scope) (¶2.1); and redeclaring, in the substatement of a selection or iteration statement, a name that conflicts with the scope of that statement (¶2.2). The parent scope of the loop body is the scope of the `for` statement, which contains only `i`, not `limit`. So the `int limit` in the loop body merely hides the parameter, which is allowed. The program returns 2 (counting when `i` is 6 and 7).

One change makes it ill-formed: redeclare `i` in the loop body, or redeclare `limit` in the outermost block of the function body.

```cpp error
int f(int limit) { int limit = 0; return limit; }               // error: conflicts with the parameter (¶2.1)
void g() { for (int i = 0; i < 3; ++i) { int i = 0; (void)i; } } // error: conflicts with the for's i (¶2.2)
```

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ok" markdown="1">

Judge the whole program.

```cpp run
struct A { static int n; };
int A::n = 0;

int main() {
  int A = 1;
  A::n = A;
  struct A* p = nullptr;
  return A::n + (p == nullptr);
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: well-formed; it returns 2.**

The local variable `int A` hides the class name `A`, but the three occurrences of `A` are looked up differently:

1. The `A` in `A::n` is followed by `::`. [[basic.lookup.qual.general#1]] says such a lookup considers only namespaces, types, and templates whose specializations are types; the local variable is ignored, and `struct A` is found.
2. The `A` on the right of the assignment is ordinary unqualified lookup, which finds `int A` first in the block scope; its value is 1.
3. `struct A*` is an elaborated-type-specifier, and the lookup of its name is type-only ([[basic.lookup.elab#1]]), considering only type declarations ([[basic.lookup.general#4]]), so `struct A` is found again.

Drop the `struct` keyword and the `A` in `A* p` finds the variable; the whole declaration is parsed as the expression `A * p`, and `p` is undeclared:

```cpp error
struct A { static int n; };
int main() { int A = 1; A* p = nullptr; (void)A; }   // error: p is undeclared
```

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ifndr" markdown="1">

Judge the whole program.

```cpp run
using T = double;

struct S {
  T scale() { return T(1) / 2; }
  using T = int;
};

int main() { return S{}.scale() == 0.5; }
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: IFNDR (ill-formed, no diagnostic required).**

The two `T`s appear in different contexts.

- The return type `T` is not in a **complete-class context**. Complete-class contexts are only function bodies, default arguments, noexcept-specifiers, contract specifiers, default member initializers and the like ([[class.mem.general#10]]). Looking up `T` in the class scope searches backward from the current point per [[class.member.lookup#3]]; `S::T` has not been declared yet, so the result is empty, and lookup continues outward and finds `::T`, which is `double`.
- The `T(1)` in the function body is in a complete-class context, so the lookup starts from the end of the class definition and finds `S::T`, which is `int`.

[[class.member.lookup#6]] says that if a search in a class scope gives a different result than the same search in a complete-class context, the program is ill-formed, no diagnostic required. The search at the return type yields nothing, while the search in a complete-class context yields `S::T`; they differ.

Clang 23 gives no diagnostic at all and compiles it as `double scale()`; the body computes `int(1) / 2`, which is 0, and `main` returns 0. That is exactly what IFNDR means: the implementation need not complain, yet the program has no meaning. Move `using T = int;` before `scale` and both lookups find `S::T`; the program is well-formed:

```cpp ok
using T = double;
struct S {
  using T = int;
  T scale() { return T(1) / 2; }
};
int main() { return S{}.scale(); }
```

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="C" markdown="1">

What does the program print?

```cpp run
#include <cstdio>
int x = 1;
namespace N {
  int x = 2;
  struct B { static constexpr int x = 3; };
  struct D : B { int get(); };
}
int N::D::get() { return x; }

int main() { std::printf("%d\n", N::D{}.get()); }
```

- A. `1`
- B. `2`
- C. `3`
- D. Compilation fails: `x` is ambiguous

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: C; it prints `3`.**

The definition of `get` is written at global scope, but its declarator-id is the qualified name `N::D::get`. [[basic.scope.class#1]] says the part of such a redeclaration after the declarator-id also belongs to the scope of class `D`. So from the function body, the chain of scopes is: block scope, function parameter scope, the class scope of `D`, namespace `N`, global scope.

Unqualified lookup searches scope by scope and stops at the first scope where a declaration is found ([[basic.lookup.unqual#2]]). When the class scope of `D` is searched, `D` itself has no `x`, so lookup proceeds into the base class `B` per [[class.member.lookup#4]] and finds `B::x`. Lookup ends there; neither `N::x` nor `::x` is ever seen.

The argument for A is that "the function definition is written at global scope", but what determines lookup is scope, not textual position.

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

Judge the whole program.

```cpp run
namespace A { int i = 1; }
int i = 2;

int main() {
  using namespace A;
  return i;
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: ill-formed; `i` is ambiguous.**

A using-directive does not introduce names into the block scope where it appears. ¶2.2 of [[basic.lookup.unqual#2]] says that an unqualified search of a scope S also searches the namespaces nominated by active using-directives that S contains. `A` is not contained in `main`'s block scope, so no `i` is found there; when lookup reaches the global scope, which contains `A`, both `::` and `A` are searched, finding `::i` and `A::i`. The note in [[namespace.udir#3]] summarizes the effect: the members of `A` behave as if declared in the nearest namespace that contains both the directive and `A`, here the global namespace.

Neither declaration is a function and they denote different entities, so per [[basic.lookup.general#1]] the lookup is ambiguous and the program is ill-formed.

A using-declaration gives a completely different result. It binds the name `i` in the block scope, so the block-scope search finds it and the outer `::i` is hidden:

```cpp ok
namespace A { int i = 1; }
int i = 2;
int main() {
  using A::i;
  return i;   // A::i, returns 1
}
```

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="B" markdown="1">

What does the program print?

```cpp run
#include <cstdio>
namespace A { int f(int) { return 1; } }
using A::f;
namespace A { int f(char) { return 2; } }
int g() { return f('a'); }

namespace B { int h(int) { return 1; } }
using namespace B;
namespace B { int h(char) { return 2; } }
int k() { return h('a'); }

int main() { std::printf("%d%d\n", g(), k()); }
```

- A. `11`
- B. `12`
- C. `21`
- D. `22`

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: B; it prints `12`.**

A using-declaration names the set of declarations found by looking up `A::f` at the point where it appears ([[namespace.udecl#1]]). At that point `A` contains only `f(int)`; overloads added to `A` later are not named by it (the note in [[namespace.udecl#9]] has the same example). So `f('a')` in `g` has a single candidate, `f(int)`, and returns 1.

A using-directive introduces no names; it only makes lookup search the nominated namespace. The search happens at the point of use and finds every declaration preceding that point ([[basic.lookup.general#3]]), including `B::h(char)`, which was added after the directive (the note in [[namespace.udir#6]]). The candidates for `h('a')` are `h(int)` and `h(char)`; the latter is an exact match, and it returns 2.

</details>
</div>

## 2. Argument-dependent lookup, hidden friends and inline namespaces

<div class="quiz" data-kind="verdict" data-answer="ok" markdown="1">

Judge the whole program.

```cpp run
namespace N {
  struct S {};
  int f(S) { return 1; }
}
int f(int) { return 2; }

int main() {
  using ::f;
  N::S s;
  return f(s);
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: well-formed; it calls `N::f` and returns 1.**

[[basic.lookup.argdep#1]] lists three situations that turn ADL off: ordinary lookup finds a class member (¶1.1), finds a function declaration that inhabits a block scope (¶1.2), or finds a declaration that is not a function or function template (¶1.3).

The block-scope `using ::f;` looks like the second situation (¶1.2), but it is not. When lookup finds a using-declarator, it is replaced by the declarations it names per [[basic.lookup.general#3]], here the global `f(int)`. That declaration inhabits the global namespace, not a block scope, so none of the three situations holds, ADL proceeds as usual, and it finds `N::f(S)`. In overload resolution `f(int)` is not viable, and `N::f` is selected.

The idiom `using std::swap; swap(a, b);` finds the user's own `swap` thanks to this very rule (see [[topics/name-lookup-and-customization]]). Replace it with a block-scope function declaration and ¶1.2 holds, turning ADL off:

```cpp error
namespace N {
  struct S {};
  int f(S) { return 1; }
}
int f(int) { return 2; }
int main() {
  int f(int);     // block-scope function declaration, turns ADL off
  N::S s;
  return f(s);    // error: only f(int), and N::S cannot convert to int
}
```

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="D" markdown="1">

Which of the four calls in `test` is ill-formed?

```cpp run
namespace B {
  template<class T> struct W {};
  template<auto K>  struct Fixed {};
}
namespace A {
  struct X {};
  enum E { e };
  struct Y { int m; };
  void p(X**);
  void w(B::W<X>);
  void q(int Y::*);
  void v(B::Fixed<e>);
}

void test() {
  A::X* px = nullptr;
  B::W<A::X> wx;
  B::Fixed<A::e> fe;
  p(&px);
  w(wx);
  q(&A::Y::m);
  v(fe);
}
```

- A. `p(&px)`
- B. `w(wx)`
- C. `q(&A::Y::m)`
- D. `v(fe)`

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: D.**

All four functions are declared only in `A`, so ordinary lookup in `test` finds none of them; whether each call works depends entirely on whether `A` is an associated namespace. The associated entities are computed one by one per [[basic.lookup.argdep#3]]:

- A: the argument type is `A::X**`. The associated entities of a pointer are those of the pointee type (¶3.5); recursing twice gives the class `A::X`, whose associated namespace is `A`.
- B: the argument type is `B::W<A::X>`, a class template specialization. Besides the class itself (associated with `B`), the associated entities of the type template argument `A::X` are included too (¶3.3), so `A` is an associated namespace.
- C: the argument type is `int A::Y::*`, a pointer to data member. The associated entities include those of the member type (`int`, none) and the class `A::Y` (¶3.8), associated with `A`.
- D: the argument type is `B::Fixed<A::e>`. `A::e` is a constant template argument, and note 3 in [[basic.lookup.argdep#3]] says explicitly that constant template arguments do not contribute associated entities. The only associated namespace is `B`, `A::v` is not found, and the call is ill-formed.

The easiest one to get wrong is B: many people think template arguments do not take part in ADL. Type template arguments do; constant template arguments do not.

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

Judge the whole program.

```cpp run
struct Meters {
  double v;
  Meters(double d) : v(d) {}
  friend Meters operator+(Meters a, Meters b) { return a.v + b.v; }
  friend double value(Meters m) { return m.v; }
};

int main() {
  Meters m = 1.0;
  Meters a = m + 2.0;
  Meters b = 2.0 + m;
  return static_cast<int>(value(a) + value(b) + value(3.0));
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: ill-formed; no function is found for `value(3.0)`.**

A friend function declared only inside the class is called a **hidden friend**. A friend declaration does not bind a name (¶2.1 of [[dcl.meaning.general#2]]; see also the note in [[class.friend#10]]), so ordinary unqualified lookup never finds it; only ADL can: ¶4.2 of [[basic.lookup.argdep#4]] says ADL finds friend functions declared in associated classes.

- `m + 2.0` and `2.0 + m`: the non-member candidates of an operator come from unqualified lookup plus ADL (¶3.2 of [[over.match.oper#3]]). One operand is a `Meters`, so the associated class is `Meters`, the friend `operator+` is found, and the other operand becomes a `Meters` via the converting constructor. Both lines are valid.
- `value(a)`, `value(b)`: the argument is a `Meters`, ADL finds the friend, valid.
- `value(3.0)`: the argument is a `double`, and fundamental types have no associated entities (¶3.2), so ADL finds nothing. Ordinary lookup finds nothing either, so per [[basic.lookup.general#1]] it is ill-formed.

This is exactly what hidden friends are for: the function enters the candidate set only when at least one argument already has the class type, and is never selected merely because some argument happens to be implicitly convertible. Construct the argument as a `Meters` explicitly and the call is valid:

```cpp ok
struct Meters {
  double v;
  Meters(double d) : v(d) {}
  friend double value(Meters m) { return m.v; }
};
int main() { return static_cast<int>(value(Meters(3.0))); }
```

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ok" markdown="1">

Judge the whole program.

```cpp run
namespace lib {
  inline namespace v1 {
    struct S {};
  }
  int f(S) { return 1; }

  struct T {};
  inline namespace v1 {
    int g(T) { return 2; }
  }
}

int main() {
  return f(lib::S{}) + g(lib::T{});
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: well-formed; it returns 3.**

[[basic.lookup.argdep#4]] says the associated namespaces are the innermost enclosing **non-inline** namespaces of the associated entities, plus every element of the inline namespace sets of those namespaces. The inline namespace set is the transitive closure of all inline namespaces, nested ones included ([[namespace.def.general#7]]).

- `S` is declared in `lib::v1`; the innermost non-inline namespace is `lib`, so the associated namespaces are `lib` and `lib::v1`. `f` is declared in `lib` and is found.
- `T` is declared in `lib`; the associated namespaces are again `lib` and `lib::v1`, and `g`, declared in `lib::v1`, is found too.

It works in both directions: [[namespace.def.general#6]] says that if either an inline namespace or its enclosing namespace is an associated namespace, so is the other.

Inline namespaces have a cost too. A qualified lookup of `lib::f` always searches `lib`'s inline namespace set as well, per [[namespace.qual#1]], even if `lib` already has a declaration of that name. The two `f(int)`s below are different entities, and the call is ambiguous:

```cpp error
namespace lib {
  inline namespace v2 { int f(int) { return 2; } }
  int f(int) { return 1; }
}
int main() { return lib::f(0); }   // error: lib::f and lib::v2::f are ambiguous
```

</details>
</div>

<div class="quiz" data-kind="open" markdown="1">

The program below fails to compile at `#1`. Explain how the candidate set is formed and why the global `operator<<` is not in it, and give one fix that does not require touching `std`.

```cpp run
#include <iostream>
#include <vector>

std::ostream& operator<<(std::ostream& os, const std::vector<int>& v) {
  for (int x : v) os << x << ' ';
  return os;
}

namespace app {
  struct Point { int x, y; };
  std::ostream& operator<<(std::ostream& os, const Point& p) {
    return os << p.x << ',' << p.y;
  }

  void dump(const std::vector<int>& v) {
    std::cout << v << '\n';   // #1
  }
}

int main() { app::dump({1, 2, 3}); }
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Key points: ordinary lookup stops when it finds an `operator<<` in `app`, so the global version is hidden; ADL looks only in `std`; neither route finds the global `operator<<`.**

The candidates for `std::cout << v` are formed per [[over.match.oper#3]]:

1. Member candidates (¶3.1): `operator<<` is searched for in `std::ostream`, giving the overloads for the arithmetic types, pointers and so on, none of which accepts `std::vector<int>`.
2. Non-member candidates (¶3.2): unqualified lookup of `operator<<`, plus ADL. Unqualified lookup starts from the body of `dump`, finds `app::operator<<(std::ostream&, const Point&)` when it reaches namespace `app`, and stops there ([[basic.lookup.unqual#2]]); the global scope is never searched.
3. ADL (still part of the non-member candidates of ¶3.2): the operand types are `std::basic_ostream<char>` and `std::vector<int, std::allocator<int>>`; the template arguments `char` and `int` have no associated entities, and everything else is in `std` ([[basic.lookup.argdep#3]]). The only associated namespace is `std`.
4. Built-in and rewritten candidates are irrelevant here.

The global `operator<<` is found by neither route, none of the candidates is viable, and the program is ill-formed. The non-viable candidates Clang lists include `app::operator<<` (the `Point` version) and the various overloads in `std`, but not the global version, which confirms this.

One fix is to add `using ::operator<<;` in `dump` (or in `app`). The using-declaration brings the global version into the scope that unqualified lookup reaches first:

```cpp run ok
#include <iostream>
#include <vector>
std::ostream& operator<<(std::ostream& os, const std::vector<int>& v) {
  for (int x : v) os << x << ' ';
  return os;
}
namespace app {
  struct Point { int x, y; };
  std::ostream& operator<<(std::ostream& os, const Point& p) { return os << p.x << ',' << p.y; }
  void dump(const std::vector<int>& v) {
    using ::operator<<;
    std::cout << v << '\n';
  }
}
int main() { app::dump({1, 2, 3}); }
```

A more robust approach is not to write operators for other people's types: wrap `std::vector<int>` in a type in your own namespace, so that ADL can find the accompanying operators. Adding the overload to `std` is not an option: adding declarations to `std` is undefined behavior ([[namespace.std#1]]).

</details>
</div>

## 3. Class member lookup and access control

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

Judge the whole program.

```cpp run
struct A { int f(int)    { return 1; } };
struct B { int f(double) { return 2; } };
struct C : A, B {};

int main() {
  C c;
  return c.f(1);
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: ill-formed; member lookup of `f` is ambiguous.**

Name lookup precedes overload resolution ([[basic.lookup.general#1]]), and member lookup does not merge same-named functions from different base classes into one overload set. Computing S(f, C) per [[class.member.lookup]]:

1. `C` itself has no `f`, so the lookup sets of the two direct bases are merged in turn (¶4).
2. S(f, A) = {{`A::f`}, {A}}, S(f, B) = {{`B::f`}, {B}}.
3. When merging, neither subobject is a base class subobject of the other, and the declaration sets differ, so the result is an invalid set (¶5.2).
4. ¶6: the lookup result is an invalid set, so the program is ill-formed.

`f(int)` is an exact match for the argument `1` and overload resolution could have selected it, but overload resolution never gets a chance to start. Bring both `f`s into the same scope with using-declarations in `C`; then lookup finds both declarations in `C` itself (¶3), and overload resolution selects `A::f`:

```cpp ok
struct A { int f(int)    { return 1; } };
struct B { int f(double) { return 2; } };
struct C : A, B { using A::f; using B::f; };
int main() { C c; return c.f(1); }   // calls A::f, returns 1
```

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

Judge the whole program.

```cpp run
class B { public: int v = 0; };
class D : private B {};

class E : public D {
  void reset() {
    B b;
    b.v = 1;
  }
};

int main() {}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: ill-formed; `B` is inaccessible.**

The `B` in `E::reset` is an unqualified name. When lookup passes through the class scope of `E`, it searches the base classes per the member lookup rules and finds, in `D`'s base `B`, the **injected-class-name** of `B`, that is, the binding of the class name in its own class scope ([[class.pre#2]]). Lookup stops there; the global `::B` never gets a chance to be found.

For access checking, the injected-class-name is treated as a public member of `B` ([[class.pre#2]]). Through private inheritance it becomes a private member of `D` ([[class.access.base#1]]), and as a member of `E` it is inaccessible. The lookup is performed in the scope of `E`, so the naming class is `E`; checking [[class.access.base#5]] item by item: ¶5.4 through ¶5.6 do not hold; ¶5.7 requires the member to be accessible when named through some base class that is accessible here, but named through `D` it is a private member of `D`, and `reset` is not a member or friend of `D`; and `B` itself as a base of `E` is not accessible here ([[class.access.base#4]]). So the access is ill-formed.

`b.v` itself is fine. The example in [[class.access.base#3]] is exactly this situation: naming the global class explicitly as `::B` means lookup does not pass through `E`'s class scope, and access is valid:

```cpp ok
class B { public: int v = 0; };
class D : private B {};
class E : public D {
  void reset() { ::B b; b.v = 1; }   // OK: ::B does not go through the inheritance chain
};
int main() {}
```

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

Judge the whole program. `main` only calls the public `f(int)`.

```cpp run
class Base {
public:
  int f(int) { return 1; }
private:
  int f(char) { return 2; }
};

class Derived : public Base {
public:
  using Base::f;
};

int main() {
  Derived d;
  return d.f(0);
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: ill-formed; the error is in the using-declaration itself.**

In an ordinary call, access control applies only to the function selected by overload resolution ([[class.access.general#4]]). Using-declarations have their own rule: [[namespace.udecl#14]] requires **every** declaration named by a using-declarator that does not name a constructor to be accessible. `Base::f(char)` is a private member of `Base` and is not accessible in `Derived`, so `using Base::f;` is ill-formed regardless of which overload is called later. The example in [[namespace.udecl#16]] is the same situation.

Change private to protected and the conclusion changes: the protected member is accessible in a member declaration of `Derived`, the using-declaration is valid, and because it sits in the `public` section it has the accessibility of an ordinary member declaration there, per [[namespace.udecl#16]]. So the formerly protected `f(char)` gets a public synonym in `Derived` and can be called from outside:

```cpp ok
class Base {
public:
  int f(int) { return 1; }
protected:
  int f(char) { return 2; }
};
class Derived : public Base {
public:
  using Base::f;
};
int main() {
  Derived d;
  return d.f('a');   // OK: calls Base::f(char), returns 2
}
```

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

Judge the whole program.

```cpp run
class Base {
protected:
  int n = 0;
};

class Derived : public Base {
public:
  void copy_from(const Base& other) { n = other.n; }
};

int main() {
  Derived a, b;
  a.copy_from(b);
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: ill-formed; `other.n` violates the additional rule for protected members.**

First the general rule: the naming class of `other.n` is `Base` (¶5.2 of [[class.access.base#5]]); `n` as a member of `Base` is protected, and the access occurs in a member of the derived class `Derived`, so by ¶5.6 it would be accessible.

But [[class.protected#1]] adds a check for non-static members: when access is granted because it occurs in a member or friend of some class C (here `Derived`), and the access goes through an object expression, the class of the object expression must be C or a class derived from C. `other` has type `Base`, which does not qualify, so the access is ill-formed. The `n` on the left is `this->n`, whose object expression has class `Derived`, which is fine.

The rationale: `Derived` should only be able to access the `Base` part of its own branch of the hierarchy. `other` might actually be an object of some unrelated derived class `Other : Base`.

Changing the parameter to `const Derived&` makes it valid. Static members are not subject to this additional rule; to form a pointer to member, name it as `&Derived::n`:

```cpp ok
class Base { protected: int n = 0; static int s; };
int Base::s = 0;
class Derived : public Base {
public:
  void copy_from(const Derived& other) { n = other.n + Base::s; }
  int Base::* pm() { return &Derived::n; }   // type is int Base::*
};
int main() { Derived a, b; a.copy_from(b); }
```

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="A" markdown="1">

Which of the following member function bodies is ill-formed?

```cpp run
class A {
  int secret = 0;
  friend struct F;
};
struct B : A {};

struct F {
  int a(A& x) { return x.secret; }
  int b(B& x) { return x.secret; }
  int d(A& x) {
    struct Local { static int get(A& y) { return y.secret; } };
    return Local::get(x);
  }
};
struct G : F {
  int c(A& x) { return x.secret; }
};
```

- A. `G::c`
- B. `F::b`
- C. `Local::get` inside `F::d`
- D. All are well-formed

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: A.**

- `G::c`: `G` derives from the friend `F`, but friendship is neither inherited nor transitive ([[class.friend#9]]). `G` is not a friend of `A`, so `secret` is inaccessible.
- `F::b`: the naming class is `B`. `secret` is a private member of `A` and is not accessible as a member of `B`, but ¶5.7 of [[class.access.base#5]] offers another route: `A` is a base class of `B` that is accessible here (public inheritance, ¶4.1 of [[class.access.base#4]]), and `secret` is accessible when named in class `A` (`F` is a friend of `A`, ¶5.5). In addition, ¶6 requires `x` to be implicitly convertible to a pointer to the naming class `B`, which obviously holds. Valid; this is the same situation as example 4 under ¶5.
- `Local::get`: a local class of a member function may access every member the member function itself can access ([[class.access.general#2]]); `F::d` can access `secret`, so `Local` can too.

If `B` used private inheritance instead (`class B : A {};`), `F::b` would also be ill-formed: `A` as a private base of `B` is not accessible in `F`, and ¶5.7 no longer holds.

</details>
</div>

<div class="quiz" data-kind="open" markdown="1">

Write out the computation of S(id, D) and say what `probe()` returns. Then answer: what happens if both `virtual`s are removed, or only the one on `R`?

```cpp run
#include <cstdio>
struct V { int id() { return 1; } };
struct L : virtual V { int id() { return 2; } };
struct R : virtual V { };
struct D : L, R {
  int probe() { return id(); }
};
int main() { std::printf("%d\n", D{}.probe()); }
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Key points: the original program finds `L::id` and prints `2`; removing both `virtual`s, or only `R`'s, makes the lookup ambiguous and the program ill-formed.**

Computing per [[class.member.lookup]]:

1. `D` itself has no `id`, so S(id, L) and S(id, R) are merged in turn (¶4).
2. S(id, L) = {{`L::id`}, {L}}: `L` declares `id` itself (¶3).
3. S(id, R): `R` has no `id`, so the result from its base `V` is taken: {{`V::id`}, {V}}. This V is the virtual base subobject, of which there is only one in the complete object `D`.
4. Merging: the intermediate result starts as a copy of S(id, L). When S(id, R) is merged in, its subobject set contains only the shared V, and that V is a base class subobject of the L subobject, so per ¶5.1 the intermediate result is unchanged.

The result is `L::id`, and `probe()` returns 2. This is the situation described in the note to ¶9: `L::id` hides `V::id`, and the path to `V::id` through `R` does not go through `L`, but that is not an ambiguity, because both paths reach the same V subobject.

With both `virtual`s removed, `D` contains two V subobjects. The subobject in S(id, R) is the V inside R, which is not a base class subobject of L, nor is L one of it, and the declaration sets differ (`L::id` versus `V::id`), so ¶5.2 yields an invalid set and ¶6 makes the program ill-formed.

Removing only `R`'s `virtual` gives the same result: the V inside `R` is a separate non-virtual subobject, again not a base class subobject of L, and the lookup is ambiguous. Clang reports `member 'id' found in multiple base classes of different types` for both variants.

</details>
</div>

## 4. Overload resolution and rewritten operators

<div class="quiz" data-kind="choice" data-answer="B" markdown="1">

What does the program print (one line per call)?

```cpp run
#include <cstdio>
void f(bool)  { std::puts("bool"); }
void f(void*) { std::puts("void*"); }
void f(long)  { std::puts("long"); }

int main() {
  int x = 0;
  f(&x);
  f(nullptr);
  f(0L);
}
```

- A. `bool` / `bool` / `long`
- B. `void*` / `void*` / `long`
- C. `void*` / `bool` / `long`
- D. Compilation fails: `f(nullptr)` is ambiguous

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: B.**

- `f(&x)`: `int*` to `void*` is a pointer conversion ([[conv.ptr#2]]) and `int*` to `bool` is a boolean conversion ([[conv.bool#1]]); both have Conversion rank ([[over.ics.scs#3]]). ¶4.1 of [[over.ics.rank#4]] says a conversion that does not convert a pointer to `bool` is better, so `f(void*)` is selected. `f(long)` is not viable.
- `f(nullptr)`: `nullptr` to `void*` is a null pointer conversion ([[conv.ptr#1]]). The source types in [[conv.bool#1]] do not include `std::nullptr_t`; `nullptr_t` to `bool` is permitted only in direct-initialization (¶15.8 of [[dcl.init.general#15]]), and parameter initialization is copy-initialization, so `f(bool)` is not viable, leaving only `f(void*)`.
- `f(0L)`: `long` to `long` is the identity conversion, an exact match.

Those who choose C think `nullptr` converts implicitly to `bool`. Compare with `0`: it is a null pointer constant, and its conversions to `void*`, `bool` and `long` all have Conversion rank; ¶4.1 only concerns conversions of pointers to `bool` and does not help, so the call is ambiguous. `NULL` is an implementation-defined null pointer constant ([[support.types.nullptr#2]]), so the result varies by implementation: with Clang 23 and libc++, `f(NULL)` selects `f(long)`.

```cpp error
void f(bool); void f(void*); void f(long);
void g() { f(0); }     // error: all three candidates have Conversion rank, ambiguous
```

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

Judge the whole program.

```cpp run
struct Flags {
  int mode : 3;
};
int load(int& r)  { return r; }
int load(long v)  { return static_cast<int>(v); }

int main() {
  Flags fl{2};
  return load(fl.mode);
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: ill-formed.**

Forming an implicit conversion sequence considers only type, cv-qualification and value category, not whether the argument is a bit-field (note 1 in [[over.best.ics.general#2]]). [[over.ics.ref#4]] gives exactly this example: for an `int&` parameter and an `int` bit-field lvalue, the conversion sequence is still the identity conversion (¶1.2 of [[over.ics.ref#1]]), so `load(int&)` is viable and an exact match. `load(long)` needs an integral conversion, which has Conversion rank. Overload resolution selects `load(int&)`.

Only after selection is the reference actually initialized: ¶5.1.1 of [[dcl.init.ref#5]] excludes bit-fields, and ¶5.2 then says a non-const lvalue reference is ill-formed in this case. So `load(long)`, which could have been called legitimately, is pushed aside by a candidate doomed to fail.

Change the reference to `const int&` and the reference binds to a temporary; the conversion sequence is still an exact match, and the program is well-formed and returns 2:

```cpp ok
struct Flags { int mode : 3; };
int load(const int& r) { return r; }
int load(long v)       { return static_cast<int>(v); }
int main() { Flags fl{2}; return load(fl.mode); }
```

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="C" markdown="1">

What does the program print?

```cpp run
#include <cstdio>
template<class T> int f(T)  { return 1; }
int f(const int&)           { return 2; }

template<class T> int g(T&) { return 1; }
int g(const int&)           { return 2; }

int main() {
  int x = 0;
  std::printf("%d%d\n", f(x), g(x));
}
```

- A. `11`
- B. `12`
- C. `21`
- D. `22`

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: C; it prints `21`.**

The tie-breaker that prefers non-templates (¶2.4 of [[over.match.best.general#2]]) only comes into play when the conversion sequences for every argument tie.

- `f(x)`: the template deduces `f<int>(int)`; an `int` lvalue to `int` needs only the lvalue-to-rvalue conversion, an exact match. `f(const int&)` binds directly to the `int` lvalue, which per ¶1.2 of [[over.ics.ref#1]] is the identity conversion. Lvalue transformations are excluded in the comparison (¶3.2.1 of [[over.ics.rank#3]]), so both are identity; ¶3.2.6 applies only when both sides are reference bindings, and here one side is a by-value parameter. The conversion sequences are indistinguishable, and ¶2.4 makes the non-template `f(const int&)` win: 2.
- `g(x)`: the template deduces `g<int>(int&)`. Now both sides are reference bindings, and ¶3.2.6 says binding to the less cv-qualified reference is better, so `int&` beats `const int&`. The template wins on conversion sequences, the tie-breaker never applies: 1.

¶3.2.3 in the same subclause handles a different reference contest: an rvalue argument binding to an rvalue reference is better than binding to an lvalue reference. For example, with `void h(const int&); void h(int&&);`, `h(0)` selects `h(int&&)`.

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

Judge the whole program.

```cpp run
struct Num {
  operator int() const    { return 1; }
  operator double() const { return 2.0; }
};
int use(int)    { return 1; }
int use(double) { return 2; }

int main() { return use(Num{}); }
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: ill-formed; the call is ambiguous.**

For both candidates the argument needs a user-defined conversion sequence, consisting of a standard conversion sequence, one user-defined conversion, and a second standard conversion sequence ([[over.ics.user#1]]).

1. For `use(int)`: when initializing an `int` from a `Num`, both `operator int` and `operator double` are candidate conversion functions ([[over.match.conv#1]]). The former needs no further conversion, the latter needs a floating-integral conversion afterward, so per ¶2.2 of [[over.match.best.general#2]] `operator int` is chosen. The conversion sequence is U(`operator int`, identity).
2. For `use(double)`: likewise U(`operator double`, identity).
3. Comparing the two user-defined conversion sequences: ¶3.3 of [[over.ics.rank#3]] compares the second standard conversions only if both sequences use the **same** conversion function. Here the conversion functions differ, so the sequences are indistinguishable, and with no other argument to compare, the call is ambiguous.

It is tempting to think that since both second standard conversions are identity and `use(int)` lines up with `operator int`, it should be chosen. But ¶3.3 only compares the standard conversions following the same conversion function; there is no basis for comparing across different conversion functions. ¶3.3 takes effect only when there is a single conversion function:

```cpp ok
struct Num { operator short() const { return 1; } };
int use(int)    { return 1; }
int use(double) { return 2; }
int main() { return use(Num{}); }   // short→int is a promotion, better than short→double: use(int)
```

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

Judge the whole program.

```cpp run
#include <initializer_list>
struct Vec {
  Vec(int, int) {}
  Vec(std::initializer_list<double>) {}
};

int main() {
  int a = 1, b = 2;
  Vec v{a, b};
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: ill-formed; converting `a` and `b` to `double` is narrowing.**

`Vec` is not an aggregate, so list-initialization considers constructors per ¶3.7 of [[dcl.init.list#3]], in two phases ([[over.match.list#1]]):

1. The initializer list is non-empty, so first only initializer-list constructors are candidates, with the whole list as a single argument (¶1.1). `int` converts implicitly to `double`, so `Vec(std::initializer_list<double>)` is viable ([[over.ics.list#5]]) and is selected in the first phase.
2. Only if the first phase finds no viable initializer-list constructor is overload resolution performed again over all constructors with the elements as separate arguments (¶1.2). `Vec(int, int)` never takes part in the comparison.

After selection, the backing array of `const double` is initialized from the elements. Integer to floating-point is narrowing unless the source is a constant expression whose value can be represented exactly (¶7.3 of [[dcl.init.list#7]]). `a` and `b` are not constant expressions, so per [[dcl.init.list#5]] the program is ill-formed. Narrowing does not affect viability; it is checked only after selection.

Written as `Vec v{1, 2};`, the literals are constant expressions, there is no narrowing, and the initializer-list constructor is still called; written with parentheses, `Vec v(a, b);`, list-initialization is not involved and `Vec(int, int)` is called:

```cpp ok
#include <initializer_list>
struct Vec { Vec(int, int) {} Vec(std::initializer_list<double>) {} };
int main() {
  Vec v{1, 2};        // initializer_list<double>, constants do not narrow
  int a = 1, b = 2;
  Vec u(a, b);        // Vec(int, int)
}
```

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="B" markdown="1">

Compiled with `-std=c++2c`, what does the program print?

```cpp run
#include <cstdio>
struct Id {
  int v;
  Id(int x) : v(x) {}
  bool operator==(const Id& o) const {
    std::printf("this=%d o=%d\n", v, o.v);
    return v == o.v;
  }
};

int main() {
  bool b = 1 == Id(2);
  std::printf("%d\n", b);
}
```

- A. `this=1 o=2` / `0`
- B. `this=2 o=1` / `0`
- C. Compilation fails: the member `operator==` requires the left operand to be an `Id`
- D. Compilation fails: the two interpretations are ambiguous

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: B.**

The candidates for `1 == Id(2)` per [[over.match.oper#3]]:

1. Member candidates (¶3.1): the left operand is an `int`, not a class type, so there are none. `1` cannot first be converted to `Id` and then have a member function called on it, because the implicit object parameter does not accept user-defined conversions ([[over.best.ics.general#9]]).
2. Non-member candidates (¶3.2): lookup of `operator==` ignores member functions and finds nothing.
3. Built-in candidates: `Id` cannot be converted to an arithmetic type, so `int == int` and the like are not viable.
4. Rewritten candidates (¶3.4.4): for `y == x`, that is `Id(2) == 1`, take its non-rewritten candidate `Id::operator==` and synthesize a candidate with the parameter order reversed. `Id` has no matching `operator!=`, so it is a rewrite target (¶4). The synthesized candidate's first parameter, `const Id&`, accepts `1` (via the converting constructor), and its second parameter, the object parameter, accepts `Id(2)`. Viable.

This is the only viable candidate. Per ¶10.3 of [[over.match.oper#10]], `x == y` is interpreted as `y == x`, that is `Id(2).operator==(Id(1))`, so it prints `this=2 o=1`, and the result is false.

Those who choose A think `1` becomes the object on the left. C is the C++17 answer: compiled with `-std=c++17`, Clang reports `invalid operands to binary expression ('int' and 'Id')`.

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

Judge the whole program (by the standard, ignoring compiler extensions).

```cpp run
struct S {
  int v;
  bool operator==(const S& o) { return v == o.v; }
};

int main() {
  S a{1}, b{1};
  return a == b;
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: ill-formed; `a == b` is ambiguous. Clang accepts it as an extension with only a warning.**

`operator==` is not declared `const`. There are two candidates ([[over.match.oper#3]]):

- The ordinary member candidate `a.operator==(b)`: its parameters are the implicit object parameter `S&` ([[over.match.funcs.general#4]]) and `const S&`.
- The reversed synthesized candidate, from the member candidate of `b == a` (¶3.4.4): its parameters are `const S&` (accepting `a`) and the object parameter `S&` (accepting `b`).

Comparing argument by argument (¶3.2.6 of [[over.ics.rank#3]]: binding to the less cv-qualified reference is better):

| Argument | Ordinary candidate | Reversed candidate | Better |
|---|---|---|---|
| `a` | `S&` | `const S&` | ordinary |
| `b` | `const S&` | `S&` | reversed |

Each side wins one argument, so per [[over.match.best.general#2]] neither is better than the other. ¶2.8 prefers the non-rewritten candidate, but only if it is not worse for any argument, which does not hold here. There is no unique best viable function, so the program is ill-formed ([[over.match.best.general#3]]).

Clang 23 only gives a `-Wambiguous-reversed-operator` warning (ISO C++20 considers use of overloaded operator '==' ... to be ambiguous) and compiles as usual; it becomes an error only with `-pedantic-errors`. This is a compatibility extension Clang deliberately keeps, not the standard's conclusion.

Two fixes: declare the member function `const`, so the two candidates tie on every argument and ¶2.8 picks the non-rewritten one; or provide a matching `operator!=` per [[over.match.oper#4]], so `operator==` is no longer a rewrite target and no reversed candidate is generated:

```cpp ok
struct S {
  int v;
  bool operator==(const S& o) { return v == o.v; }
  bool operator!=(const S& o) { return v != o.v; }
};
int main() { S a{1}, b{1}; return a == b; }
```

The rule that providing `operator!=` suppresses the reversed candidate comes from [[P2468R2]], whose purpose was to keep this kind of pre-C++20 code working.

</details>
</div>

<div class="quiz" data-kind="open" markdown="1">

For each of the four calls in `use`, give the verdict, and say in which step the error (if any) occurs: name lookup, overload resolution, the access check, or the deleted-function check.

```cpp run
class Widget {
public:
  void set(long) {}
  void set(double) = delete;
private:
  void set(int) {}
};

void use(Widget& w) {
  w.set(1L);     // #1
  w.set(1.0f);   // #2
  w.set('c');    // #3
  w.set(1u);     // #4
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Key points: #1 is well-formed; #2 selects a deleted function; #3 selects a private function; #4 is ambiguous in overload resolution.**

The order is set by [[basic.lookup.general#1]]: name lookup first, then overload resolution, then the access check. A deleted function is an error only once it is selected ([[dcl.fct.def.delete#2]]).

- Name lookup: all three `set`s are found in `Widget`, regardless of whether they are private or deleted. Access control does not affect lookup ([[class.access.general#5]]).
- Overload resolution: accessibility and deletedness are ignored when forming conversion sequences (note 1 in [[over.best.ics.general#2]]), so all three functions take part in the comparison.

Call by call:

1. `w.set(1L)`: `long` is an exact match for `set(long)`, which is public and not deleted. Well-formed.
2. `w.set(1.0f)`: `float` to `double` is a floating-point promotion; to `long` and `int` it is a floating-integral conversion. The promotion wins and `set(double)` is selected. The access check passes, but it is a deleted function, so the call is ill-formed. This is precisely how `= delete` is used to block a class of arguments. It is ill-formed even in an unevaluated context such as `decltype(w.set(1.0f))` (note 1 in [[dcl.fct.def.delete#2]]).
3. `w.set('c')`: `char` to `int` is an integral promotion; to `long` and `double` it is a conversion. `set(int)` is selected. It is private, and the access check applies only to the selected function ([[class.access.general#4]]), so the call is ill-formed. It does not fall back to the public `set(long)` because the selected one is inaccessible.
4. `w.set(1u)`: `unsigned int` to `int` and `long` is an integral conversion, to `double` a floating-integral conversion; all three have Conversion rank, none of the finer rules in [[over.ics.rank#4]] applies, and overload resolution is ambiguous, failing in the second step.

</details>
</div>

## Clauses at a glance

| No. | Topic | Clauses |
|---|---|---|
| 1 | Redeclaring parameters and loop variables in a block scope | [[basic.scope.block#2]] |
| 2 | Only types are considered before `::` and in an elaborated-type-specifier | [[basic.lookup.qual.general#1]], [[basic.lookup.elab#1]] |
| 3 | Class-scope lookup disagreeing with the complete-class context | [[class.member.lookup#6]], [[class.mem.general#10]] |
| 4 | The scope chain of an out-of-class member function definition | [[basic.scope.class#1]], [[basic.lookup.unqual#2]] |
| 5 | Names from a using-directive appear in the nearest common namespace | [[basic.lookup.unqual#2]], [[namespace.udir#3]] |
| 6 | A using-declaration names only the overloads existing at that point | [[namespace.udecl#1]], [[namespace.udecl#9]] |
| 7 | A block-scope using-declaration does not turn off ADL | [[basic.lookup.argdep#1]], [[basic.lookup.general#3]] |
| 8 | Associated entities in ADL; constant template arguments do not take part | [[basic.lookup.argdep#3]] |
| 9 | Hidden friends are found only via ADL | [[basic.lookup.argdep#4]], [[dcl.meaning.general#2]] |
| 10 | Inline namespaces and associated namespaces | [[basic.lookup.argdep#4]], [[namespace.def.general#6]], [[namespace.qual#1]] |
| 11 | Operator lookup hidden by an inner declaration | [[over.match.oper#3]], [[basic.lookup.unqual#2]] |
| 12 | Same-named members in several bases make lookup ambiguous | [[class.member.lookup#5]], [[class.member.lookup#6]] |
| 13 | An injected-class-name found through a private base is inaccessible | [[class.pre#2]], [[class.access.base#5]] |
| 14 | A using-declaration requires every named declaration to be accessible | [[namespace.udecl#14]], [[namespace.udecl#16]] |
| 15 | The additional access check for protected members | [[class.protected#1]] |
| 16 | Friendship is not inherited; accessing a base's private member through a derived class | [[class.friend#9]], [[class.access.base#5]], [[class.access.general#2]] |
| 17 | Hiding and merging lookup sets with a virtual base | [[class.member.lookup#5]], [[class.member.lookup#9]] |
| 18 | Pointer-to-`bool` conversions; `nullptr` cannot copy-initialize a `bool` | [[over.ics.rank#4]], [[conv.bool#1]], [[dcl.init.general#15]] |
| 19 | A bit-field argument and a non-const reference parameter | [[over.ics.ref#4]], [[dcl.init.ref#5]] |
| 20 | Ranking reference bindings, and preferring non-templates | [[over.ics.rank#3]], [[over.match.best.general#2]] |
| 21 | User-defined conversion sequences with different conversion functions are incomparable | [[over.ics.rank#3]], [[over.match.conv#1]] |
| 22 | Initializer-list constructors first; narrowing checked after selection | [[over.match.list#1]], [[dcl.init.list#5]] |
| 23 | The reversed rewritten candidate for `==` | [[over.match.oper#3]], [[over.match.oper#10]] |
| 24 | A non-const `operator==` and ambiguity with the reversed candidate | [[over.match.best.general#2]], [[over.match.oper#4]] |
| 25 | The order of lookup, overload resolution, access check and deleted check | [[basic.lookup.general#1]], [[class.access.general#4]], [[dcl.fct.def.delete#2]] |
