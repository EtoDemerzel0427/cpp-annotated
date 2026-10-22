---
title: Operators in expressions
summary: "How an operator expression with class or enumeration operands becomes a round of overload resolution: the four kinds of candidates (member, non-member, built-in, rewritten), how C++20 rewrites comparisons in terms of operator== and operator<=>, and how a matching operator!= turns that rewriting off."
updated: 2026-10-19
---

!!! tldr
    - When no operand has class or enumeration type, the operator is always the built-in one and no overload resolution is performed.
    - Otherwise there are four kinds of candidates: member functions of the left operand, functions found by non-member lookup, imaginary built-in operator functions, and, since C++20, rewritten candidates.
    - Since C++20, `a != b` can be implemented by `operator==` and `a < b` by `operator<=>`, both possibly with the operands swapped. `==` and `<=>` aren't rewritten in terms of each other.
    - If an `operator==` has a matching `operator!=`, that `operator==` takes no part in rewriting and reversal, and the behavior falls back to C++17.
    - The operands of an overloaded operator are evaluated in the order of the built-in operator, so `std::cout << f() << g()` is guaranteed to evaluate `f()` first.

```cpp run ok
#include <cassert>
struct S {
  int v;
  bool operator==(int i) const { return v == i; }
};
int main() {
  S s{1};
  assert(s == 1);       // calls S::operator== directly
  assert(1 == s);       // C++20: operands reversed, interpreted as s == 1
  assert(!(s != 1));    // C++20: rewritten, interpreted as !(s == 1)
  assert(!(1 != s));    // C++20: reversed and rewritten, interpreted as !(s == 1)
}
```

With a single `operator==`, all four forms work. In C++17 this took four functions. As soon as one operand has class or enumeration type, an operator expression undergoes overload resolution, with candidates from four sources.

## No overload resolution between built-in types (¶1)

¶1 If no operand of an operator has class or enumeration type, the operator is assumed to be a built-in operator and is interpreted according to [[expr.compound]]; no operator functions are looked up and no overload resolution is performed.

```cpp error
struct String {
  String(const String&);
  String(const char*);
  operator const char*();
};
String operator+(const String&, const String&);

void f() {
  const char* p = "one" + "two";   // error: two pointers can't be added; operator+ is never considered
  int i = 1 + 1;                   // always 2
}
```

[[over.oper]] also requires an operator function to have at least one parameter of class or enumeration type. Together, the two rules guarantee that user code can't change the meaning of operations on built-in types.

Note 1 points out that `.`, `.*` and `::` can't be overloaded and are always built-in. `?:` can't be overloaded either, but when its second and third operands have class or enumeration type, [[expr.cond]] borrows the rules of this subclause to decide how to convert them.

## Operator notation becomes function call notation (¶2)

¶2 As soon as one operand has class or enumeration type, there may be a user-defined function implementing the operator, or a user-defined conversion may be needed to turn an operand into a type the built-in operator accepts. To resolve between these, the operator notation is first transformed into equivalent function call notation:

| Operator | Expression | As member function | As non-member function |
|---|---|---|---|
| Unary ([[over.unary]]) | `@a` | `(a).operator@()` | `operator@(a)` |
| Binary ([[over.binary]]) | `a@b` | `(a).operator@(b)` | `operator@(a, b)` |
| Assignment ([[over.assign]]) | `a=b` | `(a).operator=(b)` | none |
| Subscripting ([[over.sub]]) | `a[b]` | `(a).operator[](b)` | none |
| Class member access ([[over.ref]]) | `a->` | `(a).operator->()` | none |
| Postfix increment and decrement ([[over.inc]]) | `a@` | `(a).operator@(0)` | `operator@(a, 0)` |

!!! std
    "However, the operands are sequenced in the order prescribed for the built-in operator."

    The sequencing of the operands still follows the rules of the built-in operator.

This sentence was added by [[P0145R3]] in C++17. So even when an overloaded `operator<<` is called, `std::cout << f() << g()` is guaranteed to evaluate `f()` before `g()`; in `a = b`, `b` is sequenced before `a`. In C++14 and earlier, overloaded operators were treated as ordinary function calls, and the evaluation order of the arguments was unspecified.

## The four kinds of candidates (¶3)

¶3 For a unary operator `@` with an operand of type `cv1 T1`, or a binary operator `@` with a left operand of type `cv1 T1` and a right operand of type `cv2 T2`, there are four kinds of candidates: **member candidates**, **non-member candidates**, **built-in candidates** and **rewritten candidates**.

### Member candidates (¶3.1)

¶3.1 If `T1` is a complete class type or a class currently being defined, the member candidates are the result of looking up `operator@` in the scope of `T1`; otherwise there are none.

Member candidates depend only on the left operand: `1 + x` doesn't consider a member `operator+` of `x`. That is why symmetric binary operators are traditionally written as non-member functions or hidden friends.

### Non-member candidates (¶3.2)

¶3.2 For `=`, `[]` and `->` the set of non-member candidates is empty; these operators can be overloaded only as member functions. For other operators, the non-member candidates are the result of unqualified lookup ([[basic.lookup.unqual]]) and argument-dependent lookup ([[basic.lookup.argdep]]) of `operator@`, **ignoring all member functions**.

Ignoring member functions makes an operator expression behave differently from the same thing written as a function call (Note 3 in ¶14):

```cpp error
struct A {};
void operator+(A, A);

struct B {
  void operator+(B);
  void f();
};
A a;
void B::f() {
  a + a;             // OK: non-member lookup ignores members and finds the global operator+
  operator+(a, a);   // error: ordinary unqualified lookup finds B::operator+ in B first, hiding the global one
}
```

¶3.2 has one more restriction: if no operand has class type (only enumerations), only non-member functions whose first parameter is `T1` (or a reference to `cv T1`) or whose second parameter is `T2` (or a reference to it) are candidates. In other words, only operators written specifically for the enumeration are used for it; going through some class's converting constructor doesn't count:

```cpp error
enum class E { a };
struct S { S(E) {} };
int operator+(S, S) { return 42; }
int x = operator+(E::a, E::a);   // OK: function call notation, converts via S(E)
int y = E::a + E::a;             // error: operator+(S, S) doesn't have E parameters, so it isn't a candidate
```

### Built-in candidates (¶3.3)

[[over.built]] lists a family of imaginary functions representing the built-in operators, for example `operator+(L, R)` for every pair of promoted arithmetic types `L`, `R`, and `bool operator==(T, T)` for every enumeration type `T`. They let built-in operators be compared together with user-defined operators, for example when a class type operand is converted to `int` by a conversion function and the built-in `+` is used.

¶3.3 For `,`, unary `&` and `->`, the set of built-in candidates is empty. For other operators, the built-in candidates are those functions from [[over.built]] that:

- ¶3.3.1 have the same operator name;
- ¶3.3.2 accept the same number of operands;
- ¶3.3.3 accept operand types to which the given operands can be converted according to [[over.best.ics]];
- ¶3.3.4 do not have the same parameter-type-list as any non-template non-member candidate (including rewritten non-member candidates).

¶3.3.4 keeps a user-defined operator for an enumeration from tying with the built-in candidate of the same signature:

```cpp run ok
enum class Color { red };
bool operator==(Color, Color) { return false; }   // same signature as the built-in bool operator==(Color, Color)
int main() {
  return Color::red == Color::red;   // returns 0: the built-in candidate is dropped and the user version is called
}
```

### Rewritten candidates (¶3.4) {{c++20}}

¶3.4 Rewritten candidates let comparison operators be implemented by `operator==` or `operator<=>`:

| Expression | Rewritten candidates |
|---|---|
| `x < y`, `x <= y`, `x > y`, `x >= y` | All non-rewritten candidates for `x <=> y`; for each non-rewritten candidate for `y <=> x`, a synthesized candidate with the order of the parameters reversed |
| `x <=> y` | For each non-rewritten candidate for `y <=> x`, a synthesized candidate with the order of the parameters reversed |
| `x != y` | The non-rewritten candidates for `x == y` that are rewrite targets with first operand `x`; for each rewrite target for `y == x` with first operand `y`, a synthesized candidate with the parameters reversed |
| `x == y` | For each rewrite target for `y == x` with first operand `y`, a synthesized candidate with the parameters reversed |
| Other operators | None |

What a rewrite target is is explained in ¶4 below; roughly, an `operator==` without a matching `operator!=`.

Two design points:

- `==` isn't rewritten in terms of `<=>`. The original [[P0515R3]] allowed `==` to be implemented by `<=>`, but types like `std::vector` and `std::string` can compare lengths first when testing equality and finish immediately if they differ; implementing it with `<=>` would pay an unnecessary cost. [[P1185R2]] therefore separated equality from ordering: `==` and `!=` are rewritten only in terms of `operator==`, and `<`, `<=`, `>`, `>=` and `<=>` only in terms of `operator<=>`.
- Rewriting uses only non-rewritten candidates as raw material; it isn't recursive.

Note 2: in a candidate obtained by reversing a member candidate, the object parameter becomes the second parameter, so implicit conversions are possible on the first parameter and no user-defined conversion is possible on the second.

## After a rewritten candidate is selected (¶9–¶10)

¶9 If a rewritten `operator<=>` candidate is selected for an operator `@`, `x @ y` is interpreted as `0 @ (y <=> x)` if the candidate is reversed, and as `(x <=> y) @ 0` otherwise. Rewritten candidates aren't considered in the interpreted expression, so the rewriting can't go on forever.

¶10 If a rewritten `operator==` candidate is selected for an operator `@`, its return type must be `cv bool`, and:

| `@` | Selected candidate | Interpreted as |
|---|---|---|
| `!=` | reversed | `!(y == x)` |
| `!=` | not reversed | `!(x == y)` |
| `==` | necessarily reversed | `y == x` |

The return type is required to be `bool` because `!(x == y)` has a clear meaning only for `bool`. An `operator==` in a numerics library often returns a proxy object such as an expression template, and an automatically generated `!=` would very likely be wrong for it. So when the return type isn't `bool`, the program is simply ill-formed, rather than calling the proxy object's `operator!`.

```cpp error
struct V { int operator==(const V&) const; };
bool f(V v, V w) { return v != w; }   // error: a rewritten operator== is selected, but it returns int
struct Q { int operator==(int) const; };
bool g(Q q) { return 1 == q; }        // error: a reversed operator== is selected, which also requires returning bool
```

!!! impl "Where Clang deviates"
    In our tests Clang 23 only gives a `-Wrewrite-not-bool` warning for both and compiles them anyway. Per the standard they are ill-formed.

An example with `<=>`, which also shows the tie-breaker preferring non-rewritten candidates ([[over.match.best#2.8]]):

```cpp run ok
#include <compare>
#include <cassert>
struct P {
  int x;
  auto operator<=>(const P&) const = default;   // also implicitly declares a defaulted operator==
};
struct S {
  friend auto operator<=>(const S&, const S&) = default;       // #1
  friend bool operator<(const S&, const S&) { return true; }   // #2
};
int main() {
  P a{1}, b{2};
  assert(a < b);       // (a <=> b) < 0
  assert(b > a);       // (b <=> a) > 0
  assert(a != b);      // !(a == b), using the defaulted operator==
  assert(S() < S());   // #2: the rewritten candidate from #1 is as good as #2, and the non-rewritten one wins
}
```

## A matching operator!= turns off rewriting (¶4)

The reversed candidates of C++20 made a body of old code ambiguous (see the compatibility section below). The code hit hardest was C++17-style code that defines both `operator==` and `operator!=` but with asymmetric signatures, such as a member function missing `const`. [[P2468R2]], as a defect report against C++20, introduced the notion of a **[[g:rewrite-target|rewrite target]]** to deal with this.

¶4 A function or function template `F` named `operator==` is a rewrite target with first operand `o` unless a search for the name `operator!=` in the scope `S` finds a function that would correspond ([[basic.scope.scope]]) to `F` if its name were `operator==`, that is, one with the same parameters, a redeclaration of the same function. If `F` is a class member, `S` is the scope of the class of `o`; otherwise `S` is the namespace scope of which `F` is a member.

Put simply, writing a matching `operator!=` for an `operator==` keeps that `operator==` out of reversal and rewriting. Such code was clearly written the C++17 way, and the compiler treats it the C++17 way.

```cpp error
struct A {};
template<typename T> bool operator==(A, T);   // #1
bool a1 = 0 == A();                           // OK: calls the reversed #1
template<typename T> bool operator!=(A, T);   // matches #1
bool a2 = 0 == A();                           // error: #1 is no longer a rewrite target; no viable candidate
```

The search is performed from the instantiation context of the operator expression, so the same `operator==` can be a rewrite target at one point of a translation unit and not at another.

The member function case shows what the scope of the class of `o` means:

```cpp
struct B {
  bool operator==(const B&);    // #2, non-const
};
struct C : B {
  C();
  C(B);
  bool operator!=(const B&);    // #3
};
bool c1 = B() == C();   // OK: calls #2
bool c2 = C() == B();   // error: ambiguous
```

For the same #2, the scope searched when deciding whether it is a rewrite target with a given first operand depends on that object's class:

- `B() == C()`: a reversed candidate requires #2 to be a rewrite target with first operand `C()`. Searching `C` for `operator!=` finds #3, so it isn't; there is no reversed candidate, only `B().operator==(C())`.
- `C() == B()`: the ordinary candidate is `C().operator==(B())`. A reversed candidate requires #2 to be a rewrite target with first operand `B()`; no `operator!=` is found in `B`, so it is, giving the reversed candidate `B().operator==(C())`. The ordinary candidate binds `C()` to the implicit object parameter `B&` and the reversed one binds it to `const B&`; the former is less cv-qualified and better. For the second argument `B()` it is exactly the other way round. Each wins on one argument, hence the ambiguity.

In our tests Clang 23 only gives a `-Wambiguous-reversed-operator` warning for `c2` and selects the ordinary candidate. Per the standard it is ill-formed.

In the namespace case, only the namespace scope that `F` is a member of is searched:

```cpp run ok
struct D {};
template<typename T> bool operator==(D, T) { return true; }   // #4
inline namespace N {
  template<typename T> bool operator!=(D, T);                 // #5
}
int main() {
  return 0 == D() ? 0 : 1;   // calls the reversed #4: #5 isn't in the scope #4 belongs to
}
```

## The union of candidates and the arguments (¶5–¶8)

¶5 For the first parameter of the built-in assignment operators, only standard conversion sequences are considered. ¶6 Other operators have no such restriction.

The point of ¶5 is that in `x = 1`, even if the class object `x` can become an `int&` through a conversion function, the built-in `int& operator=(int&, int)` won't be selected; otherwise assigning to a class object would actually modify some `int` returned by the conversion function. It's the same idea as not applying user-defined conversions to the implicit object parameter ([[over.best.ics#9]]).

¶7 The set of candidates is the union of the member, non-member, built-in and rewritten candidates. ¶8 The argument list contains all the operands of the operator, and the best function is selected per [[over.match.viable]] and [[over.match.best]]. If the set of candidates is empty, resolution fails (footnote 96).

```cpp
struct A {
  operator int();
};
A operator+(const A&, const A&);
void m() {
  A a, b;
  a + b;   // selects operator+(a, b), not int(a) + int(b)
}
```

Both arguments of `operator+(const A&, const A&)` are direct reference bindings, which are exact matches. Both arguments of the built-in `operator+(int, int)` need user-defined conversions. A standard conversion sequence is better than a user-defined conversion sequence ([[over.ics.rank#2.1]]).

## After a built-in candidate is selected (¶11)

¶11 If a built-in candidate is selected, the operands of class type are converted to the types of the corresponding parameters of the selected operation function, except that the second standard conversion sequence of a user-defined conversion sequence is not applied. The operator is then treated as the built-in operator and interpreted according to [[expr.compound]].

```cpp error
struct X { operator double(); };
struct Y { operator int*(); };
int* a = Y() + 100.0;   // error: pointer arithmetic requires an integral operand
int* b = Y() + X();     // error: same reason
```

In `Y() + 100.0`, the built-in candidate `T* operator+(T*, std::ptrdiff_t)` is viable, since `100.0` can be converted to `ptrdiff_t`. Once it is selected, only the class type operand `Y()` is converted, to `int*`; `100.0` isn't of class type and isn't converted, so the expression becomes the built-in `int* + double`, which is ill-formed. In `Y() + X()`, `X()` only goes through the conversion function `operator double()`; the subsequent `double` to `ptrdiff_t` isn't applied, and the result is again `int* + double`.

Selecting a built-in candidate only borrows its signature to decide how to convert class objects; the actual operation still follows the built-in rules.

## `->`, `,` and unary `&` (¶12–¶13)

¶12 When `operator->` is selected, the member name on the right of `->` isn't considered and isn't an argument either. After `operator->` returns, `->` and the original member name are applied to the return value. If that is still of class type, `operator->` is selected and called again, until a non-class type is returned (footnote 97). This is how smart pointers forward layer by layer:

```cpp run ok
struct T { int v = 7; };
struct Inner { T t; T* operator->() { return &t; } };
struct Outer { Inner i; Inner& operator->() { return i; } };
int main() {
  Outer o;
  return o->v == 7 ? 0 : 1;   // Outer::operator-> gives Inner&, Inner::operator-> gives T*, and finally the built-in ->
}
```

¶13 For `,`, unary `&` and `->`, if there is no viable function, the operator is treated as the built-in one. Their sets of built-in candidates are empty, so this rule is needed as a fallback.

```cpp run ok
struct S {
  int operator&(int) const { return 0; }   // binary &
};
int main() {
  S s;
  S* p = &s;   // unary &: the member operator&(int) has the wrong arity and isn't viable, so the built-in address-of is used
  return p == &s ? s & 1 : 1;
}
```

## Incompatibilities introduced by C++20

Reversed candidates were an intentional incompatible change, and Annex [[diff.cpp17.over]] lists its effects. The first kind is that some calls now select a different function or become ambiguous, typically when one type can be implicitly converted to another:

```cpp
struct A {
  operator int() const;
};
bool operator==(A, int);   // #1
// built-in candidates: bool operator==(int, int), bool operator!=(int, int)

int check(A x, A y) {
  return (x == y) +        // ill-formed in C++20 (C++17 calls the built-in int == int)
         (10 == x) +       // calls the reversed #1 (C++17 calls the built-in ==)
         (10 != x);        // calls the reversed and rewritten #1 (C++17 calls the built-in !=)
}
```

In `x == y`, the ordinary #1 (`x` an exact match, `y` a user-defined conversion) and the reversed #1 (`y` an exact match, `x` a user-defined conversion) each win on one argument, hence the ambiguity. The built-in `int == int` needs user-defined conversions for both arguments and is worse. In our tests Clang 23 only gives a `-Wambiguous-reversed-operator` warning here and selects the ordinary candidate.

The second kind is an asymmetric member `operator==`:

```cpp
struct B {
  bool operator==(const B&);   // const forgotten
};
B b1;
bool eq = (b1 == b1);          // ambiguous in C++20, well-formed in C++17
```

The ordinary candidate binds the object argument to `B&` and the other argument to `const B&`; the reversed candidate does the opposite. Each is better on one argument. Although one is a rewritten candidate and the other isn't, the rule preferring the non-rewritten one ([[over.match.best#2.8]]) only applies when no conversion sequence is worse, so it doesn't help here.

Member `operator==` missing `const` is common in real projects. Clang accepts it as an extension with a `-Wambiguous-reversed-operator` warning. [[P2468R2]] provides the fix at the standard level: also declare a matching `operator!=`, and the `operator==` isn't a rewrite target, so the behavior falls back to C++17. Old code with `==` and `!=` in pairs is thus largely unaffected; code with only `==` gets the new C++20 semantics.

!!! tip "Migration advice"
    - Always make member `operator==` `const`, with a parameter type symmetric to the class type.
    - Write only `operator==`, not `operator!=`, and let the compiler rewrite.
    - When ordering is needed, write `operator<=>` (or `= default`) instead of the four functions `<`, `<=`, `>`, `>=`.
    - When comparing with types that convert implicitly, watch for ambiguities from reversed candidates, and mark converting constructors or conversion functions `explicit` where needed.

## Implementation view

!!! impl
    - The candidate families of [[over.built]] are logically infinite (one set per pointer type, one per enumeration type). Compilers generate only the few that could be viable for the operand types.
    - Clang's diagnostics label reversed candidates as candidate function (with reversed parameter order).
    - Rewriting and reversal are purely semantic transformations and produce no new symbols. What's called is still the original `operator==` or `operator<=>`, only with the arguments swapped and possibly a `!` or `@ 0` around the result.

## History

!!! history
    - C++98 already had the three kinds of candidates (member, non-member, built-in), chained calls of `->`, and the rule falling back to the built-in operator when `,`, `&` or `->` has no viable function.
    - C++17: [[P0145R3]] specified that the operands of overloaded operators are sequenced in the order of the built-in operator.
    - C++20: [[P0515R3]] introduced `<=>` and rewritten candidates; [[P1185R2]] separated `==` from `<=>` and required a rewritten `operator==` to return `bool`.
    - [[P2468R2]], as a defect report against C++20, introduced rewrite targets: a matching `operator!=` turns off rewriting and reversal of an `operator==`.

## Common misconceptions

!!! pitfall "`a != b` always calls `operator!=`"
    If only `operator==` is defined, `a != b` calls `!(a == b)`. The return type of `operator==` must then be `bool`.

!!! pitfall "Inside a member function, writing `operator+(a, b)` is equivalent to `a + b`"
    The function call form uses ordinary unqualified lookup, in which global functions are hidden by members with the same name; the non-member candidate lookup for `a + b` ignores members. The two forms can find different functions.

## Questions

!!! question "Question 1"
    With only a user-provided `auto operator<=>(const P&) const` (not `= default`), is `a == b` valid?

<details markdown="1">
<summary>Answer</summary>

No, unless there is also an `operator==`. The rewritten candidates for `==` come only from `operator==` (¶3.4.4); it is never rewritten in terms of `<=>`. Only a defaulted `operator<=>` implicitly declares a defaulted `operator==` ([[class.compare.default]]); a user-provided one doesn't. This is exactly the design of [[P1185R2]]: equality can have an implementation much faster than three-way comparison, and shouldn't be silently replaced by `<=>`.
</details>

!!! question "Question 2"
    Declare `struct T {};`, `bool operator==(const T&, int);` and `bool operator!=(const T&, int);` in the same namespace. Is `1 == T{}` valid? What if the two functions are made hidden friends of `T` instead?

<details markdown="1">
<summary>Answer</summary>

The namespace version: searching for `operator!=` in the namespace that the `operator==` belongs to finds the matching declaration, so `operator==` isn't a rewrite target, `1 == T{}` has no reversed candidate, and it is ill-formed, as in C++17.

The hidden friend version: ¶4 still searches the namespace scope that `F` belongs to, but friend declarations don't bind names ([[basic.scope.scope#2.9]]), so the search doesn't find the hidden friend `operator!=`. Hence `operator==` is still a rewrite target, `1 == T{}` selects the reversed candidate, and it is well-formed. Clang 23 agrees in our tests:

```cpp error
struct S {
  friend bool operator==(const S&, int);
  friend bool operator!=(const S&, int);
};
bool x1 = 1 == S{};   // OK: the hidden friend operator!= isn't found
struct T {};
bool operator==(const T&, int);
bool operator!=(const T&, int);
bool x2 = 1 == T{};   // error: operator== isn't a rewrite target
```

Declaring `==` and `!=` as a pair of hidden friends doesn't turn off reversal.
</details>
