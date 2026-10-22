---
title: Defaulted comparisons
summary: "C++20's = default comparison operators: which declarations can be defaulted, how == and <=> compare subobject by subobject, how the return type of auto <=> is deduced, how legacy types with only == and < take part in three-way comparison, and when a defaulted comparison is defined as deleted."
updated: 2026-10-19
---

!!! tldr
    - Write one `auto operator<=>(const T&) const = default;` and you get all six comparison operators: `==` is implicitly declared, and `<`, `!=` and the rest come from rewritten candidates.
    - Defaulted `==` and `<=>` compare bases and members one by one in declaration order, expanding arrays element by element; `==` returns `false` at the first inequality, and `<=>` returns the first result that isn't equal.
    - The return type of `auto <=>` is the weakest comparison category among the members' results; when a specific category (such as `std::weak_ordering`) is written, legacy-type members that have only `==` and `<` can take part as well.
    - Only a defaulted `<=>` implicitly declares `==`, and only if the class has no declaration named `operator==` at all; `==` is never rewritten to `<=>`.
    - With a reference member, a union member, or a member that can't be compared, the defaulted comparison is defined as deleted rather than being an error.

## Write two functions, get six operators

```cpp run title="overview.cpp" ok
#include <compare>
#include <string>

struct Point {
  int x;
  int y;
  auto operator<=>(const Point&) const = default;
  // also implicitly declares bool operator==(const Point&) const = default;
};

struct Person {
  std::string name;
  int age;
  bool operator==(const Person&) const = default;   // equality only
};

int main() {
  Point a{1, 2}, b{1, 3};
  bool r1 = a < b;     // (a <=> b) < 0: x equal, then compare y, 2 < 3
  bool r2 = a != b;    // !(a == b)
  bool r3 = a >= b;    // (a <=> b) >= 0
  Person p{"Ann", 30}, q{"Ann", 30};
  bool r4 = p == q;    // memberwise ==
  bool r5 = p != q;    // !(p == q)
  // bool r6 = p < q;  // error: Person has no <=>
  return (r1 && r2 && !r3 && r4 && !r5) ? 0 : 1;
}
```

Before C++20, a class that supported all comparisons had to hand-write six functions, `==`, `!=`, `<`, `>`, `<=` and `>=`, and keep them consistent itself. C++20 solves this with two mechanisms.

The first is **rewritten candidates** ([[g:rewritten-candidate|rewritten candidates]], [[over.match.oper]]): when doing overload resolution for `a < b`, the compiler also considers interpreting it as `(a <=> b) < 0` or `0 < (b <=> a)`; `a != b` can be interpreted as `!(a == b)`; and `a == b` can also swap its operands into `b == a`. So given just `==` and `<=>`, all six operators work, with the operands in either order.

The second is this page's **defaulted comparisons**: `==` and `<=>` themselves can be written `= default`, with the compiler comparing member by member. The result type of `<=>` is one of three **comparison categories**: `std::strong_ordering`, `std::weak_ordering` and `std::partial_ordering`, the last of which allows unordered results, such as NaN ([[cmp.categories]], [[expr.spaceship]]).

## Which declarations can be defaulted [class.compare.default]

¶1 A defaulted comparison operator function must be a non-template function that:

- ¶1.1 is a non-static member or friend of some class `C`;
- ¶1.2 is defined as defaulted in `C` or in a context where `C` is complete; and
- ¶1.3 has either two parameters of type `const C&` or two parameters of type `C`. For a member function, the implicit object parameter counts as the first parameter.

Such a function is called a **defaulted comparison operator function** ([[g:defaulted-comparison-operator-function|defaulted comparison operator function]]) for `C`. Name lookups and access checks in its implicit definition are performed from a context equivalent to its function body, so it can access `C`'s private members. A comparison operator defined as defaulted in the class must be the first declaration of that function.

<div class="compare" markdown="1">

```cpp run ok
#include <compare>
struct A { int x;
  bool operator==(const A&) const
    = default; };
struct B { int x;
  friend bool operator==(const B&,
    const B&) = default; };
struct C { int x;
  friend auto operator<=>(C, C)
    = default; };       // by value
struct D { int x;
  bool operator==(this D, D)
    = default; };       // explicit object parameter
struct G { int x;
  bool operator==(const G&) const; };
bool G::operator==(const G&) const
  = default;            // defaulted outside the class
int main() {
  static_assert(A{1} == A{1});
  static_assert(C{1} < C{2});
  static_assert(D{1} == D{1});
  return G{1} == G{1} ? 0 : 1;
}
```

```cpp error
#include <compare>
struct M1 { int x;
  bool operator==(const M1&)
    = default; };
// error: the implicit object parameter is M1&
struct M2 { int x;
  bool operator==(M2) const
    = default; };
// error: const M2& differs from M2
struct S2 {
  friend bool operator==(S2,
    const S2&) = default; };
// error: the two parameter types differ
enum E {};
bool operator==(E, E) = default;
// error: not a member or friend of a class
```

</div>

Because the implicit object parameter counts as the first parameter, the member form can only be written `bool operator==(const C&) const`; leaving out `const` disqualifies it. To take both parameters by value, use a friend, or a C++23 explicit object parameter.

Defaulting outside the class (`G`) lets the comparison's definition live in a `.cpp` file, with only the declaration in the header.

### When they are defined as deleted (¶2, ¶3)

¶2 If `C` has a non-static data member of reference type, or has variant members (that is, `C` is a union or contains an anonymous union, [[class.union.anon]]), `C`'s defaulted `<=>` and `==` are defined as deleted.

```cpp title="deleted-cases.cpp" error
struct Ref {
  int& r;
  bool operator==(const Ref&) const = default;   // defined as deleted
};

struct HasUnion {
  union { int i; float f; };
  bool operator==(const HasUnion&) const = default;   // defined as deleted
};

bool f(Ref a, Ref b) { return a == b; }   // error: uses a deleted function
```

Comparing reference members has two equally reasonable meanings: comparing the referenced values, or comparing whether they are bound to the same object. The standard doesn't choose for the programmer. And for a union, there is no way to know which member is active. Clang gives a `-Wdefaulted-function-deleted` warning for both declarations.

The other deletion conditions all rely on **usable** ([[g:usable-comparison|usable]]), defined in paragraph 3: a binary expression `a @ b` is usable if

- ¶3.1 `a` or `b` is of class or enumeration type and overload resolution for `a @ b` yields a usable candidate, that is, the selected function is not deleted and is accessible ([[over.match.general#4]]); or
- ¶3.2 neither `a` nor `b` is of class or enumeration type and `a @ b` is a valid expression.

Whether something can be compared is left entirely to ordinary overload resolution, rewritten candidates included. So for a member type that defines only `<=>`, `x == x` is not usable (`==` isn't rewritten to `<=>`), but `x < x` is.

### The implicitly declared `==` (¶4)

¶4 If the member-specification of a class explicitly declares no member or friend named `operator==`, then for each three-way comparison operator function defined as defaulted in it, an `operator==` is implicitly declared, with the same access, function definition and class scope as that `<=>`, except that the return type is replaced with `bool` and the name with `operator==`.

Note 1 adds: the implicit `==` is defined as defaulted in the class definition, with the same parameters and trailing *requires-clause* as the `<=>`; if the `<=>` is `friend`, `virtual`, `constexpr` or `consteval`, so is the `==`. If the `<=>` has no *noexcept-specifier*, the `==` has its own implicit exception specification, and the two may differ. Note 2: the `==` is implicitly declared even if the `<=>` is defined as deleted; whether it is deleted is decided separately.

Example 2 in the standard shows what the implicit declarations look like:

```cpp run title="implicit-eq.cpp" ok
#include <compare>

template<typename T> struct X {
  friend constexpr std::partial_ordering operator<=>(X, X)
      requires (sizeof(T) != 1) = default;
  // implicitly declares: friend constexpr bool operator==(X, X)
  //                          requires (sizeof(T) != 1) = default;

  [[nodiscard]] virtual std::strong_ordering operator<=>(const X&) const = default;
  // implicitly declares: [[nodiscard]] virtual bool operator==(const X&) const = default;
};

int main() {
  X<char> a, b;      // the friend's constraint isn't satisfied; only the member version remains
  (void)(a <=> b);
  (void)(a == b);    // the implicitly declared member ==
}
```

This example is meant only to show the declarations. With `X<int>`, the by-value friend and the `const&` member match lvalue arguments equally well, and Clang reports both `a <=> b` and `a == b` as ambiguous.

Why doesn't `<=>` simply double as `==`? C++20's original design ([[P0515R3]]) did allow rewriting `a == b` as `(a <=> b) == 0`. Then [[P1185R2]] pointed out a performance problem: `==` for `std::vector` and `std::string` can compare lengths first and return immediately if they differ, whereas `<=>` has to compare element by element lexicographically to determine the order. If `==` were always implemented via `<=>`, every class compared memberwise would quietly get slower. So now `==` is never rewritten to `<=>`, and a defaulted `<=>` separately implicitly declares a defaulted `==` that calls `==` member by member.

The condition in paragraph 4 is that there is no declaration named `operator==` at all. As soon as you write one, even with completely different parameter types, the implicit `==` doesn't appear:

```cpp title="no-implicit-eq.cpp" error
#include <compare>

struct U {
  int x;
  std::strong_ordering operator<=>(const U& o) const { return x <=> o.x; }   // hand-written, not defaulted
};

struct V {
  int x;
  auto operator<=>(const V&) const = default;
  bool operator==(int) const;   // explicitly declares an operator==
};

bool t1(U a, U b) { return a < b; }    // OK: (a <=> b) < 0
bool t2(U a, U b) { return a == b; }   // error: a hand-written <=> doesn't implicitly declare ==
bool t3(V a, V b) { return a == b; }   // error: operator==(int) exists, so V == V isn't implicitly declared
```

### The expanded list of subobjects (¶5)

¶5 A defaulted comparison compares, one by one, the **expanded list of subobjects** ([[g:expanded-list-of-subobjects|expanded list of subobjects]]) of an object `x`:

1. first the direct base class subobjects of `C`, in the order of their declaration in the base-specifier-list;
2. then the non-static data members of `C`, in declaration order;
3. subobjects of array type are recursively expanded into their elements, in order of increasing subscript.

The *i*-th element of the list is written x<sub>i</sub>. Only direct bases are listed; a base's own members are the business of the base's comparison operators. Static data members aren't in the list. Bases come before members, consistent with construction order.

```cpp run title="subobject-order.cpp" ok
#include <compare>
#include <cstdio>

struct Loud {
  int v;
  bool operator==(const Loud& o) const {
    std::printf("==%d ", v); return v == o.v;
  }
  std::strong_ordering operator<=>(const Loud& o) const {
    std::printf("<=>%d ", v); return v <=> o.v;
  }
};

struct B { Loud b; auto operator<=>(const B&) const = default; };
struct D : B {
  Loud m1, m2;
  auto operator<=>(const D&) const = default;
};

int main() {
  D x{{{0}}, {1}, {2}}, y{{{0}}, {9}, {2}};
  bool e = x == y;  std::printf("-> %d\n", e);   // ==0 ==1 -> 0
  bool l = x < y;   std::printf("-> %d\n", l);   // <=>0 <=>1 -> 1
  bool n = x != y;  std::printf("-> %d\n", n);   // ==0 ==1 -> 1
}
```

The output shows the members of the base `B` compared first, then `m1`; since `m1` differs, comparison stops there and `m2` is never compared.

## Defaulted `==` [class.eq]

¶1 A defaulted `==` must have a declared return type of `bool`.

¶2 If, for some x<sub>i</sub> in the expanded list, `xi == xi` is not usable, `C`'s defaulted `==` is defined as deleted.

¶3 The return value is obtained by comparing x<sub>i</sub> and y<sub>i</sub> in increasing index order; at the first index where `xi == yi`, converted to `bool`, is `false`, it returns `false`, and otherwise it returns `true`. In other words, it is a short-circuiting memberwise `&&`; an empty class with no subobjects always returns `true`.

¶4 is Example 1 in the standard:

```cpp run title="eq-example.cpp" ok
struct D {
  int i;
  friend bool operator==(const D& x, const D& y) = default;   // returns x.i == y.i
};

int main() { return D{1} == D{1} ? 0 : 1; }
```

## Defaulted `<=>` [class.spaceship]

### The `auto` return type (¶2.1, ¶4)

```cpp run title="common-category.cpp" ok
#include <compare>
#include <string>
#include <type_traits>

struct Weak {
  int v;
  std::weak_ordering operator<=>(const Weak&) const = default;
};

struct A { int i; std::string s; auto operator<=>(const A&) const = default; };
struct B { int i; Weak w;        auto operator<=>(const B&) const = default; };
struct C { int i; Weak w; double d;
           auto operator<=>(const C&) const = default; };
struct E { auto operator<=>(const E&) const = default; };              // empty class
struct F { int a[3]; auto operator<=>(const F&) const = default; };    // array

static_assert(std::is_same_v<decltype(A{} <=> A{}), std::strong_ordering>);
static_assert(std::is_same_v<decltype(B{} <=> B{}), std::weak_ordering>);
static_assert(std::is_same_v<decltype(C{} <=> C{}), std::partial_ordering>);
static_assert(std::is_same_v<decltype(E{} <=> E{}), std::strong_ordering>);
static_assert(F{{1, 2, 3}} < F{{1, 2, 4}});

int main() {}
```

¶2.1 When the return type is written `auto`, let R<sub>i</sub> be the type of `xi <=> xi`. If any of these expressions is not usable, or some R<sub>i</sub> is not a comparison category type, the function is defined as deleted. Otherwise the return type is deduced as the **common comparison type** ([[g:common-comparison-type|common comparison type]]) of all the R<sub>i</sub>.

¶4 The common comparison type takes the weakest category among them:

- ¶4.1 if any is `std::partial_ordering`, the result is `std::partial_ordering`;
- ¶4.2 otherwise, if any is `std::weak_ordering`, the result is `std::weak_ordering`;
- ¶4.3 otherwise it is `std::strong_ordering`. Note 2 points out that this is also the result when the list is empty (as for the empty class `E` above).

`strong` converts to `weak` and `weak` converts to `partial`, but not the other way round, so only the weakest can be chosen. In the example above, `<=>` on `double` gives `partial_ordering`, so `C`'s result does too. The standard library's `std::common_comparison_category` does the same computation ([[cmp.common]]).

### The return value (¶3)

¶3 The return value is obtained by comparing x<sub>i</sub> and y<sub>i</sub> in increasing index order; at the first result v<sub>i</sub> for which `vi != 0`, it returns that result; if all are equal it returns `static_cast<R>(std::strong_ordering::equal)`. This is lexicographic comparison.

For `partial_ordering`, `unordered != 0` is true, so an unordered member such as NaN makes it return `unordered` immediately:

```cpp run title="nan.cpp" ok
#include <cmath>
#include <compare>

struct P {
  double x;
  int y;
  auto operator<=>(const P&) const = default;
};

int main() {
  P a{NAN, 1}, b{NAN, 2};
  auto r = a <=> b;                          // the first member is already unordered; returns immediately
  bool ok = r == std::partial_ordering::unordered
            && !(a < b) && !(a > b) && !(a == b);
  return ok ? 0 : 1;
}
```

### Members with only `==` and `<`: synthesized three-way comparison (¶1, ¶2.2)

Many types written before C++20 have only `==` and `<`, no `<=>`. An `auto <=>` meeting such a member is deleted, because `xi <=> xi` isn't usable. If the return type is written as a specific comparison category, the compiler builds the three-way comparison out of `==` and `<`:

```cpp run title="synthesized.cpp" ok
#include <compare>

struct Legacy {                  // only == and <
  int v;
  constexpr bool operator==(const Legacy& o) const { return v == o.v; }
  constexpr bool operator<(const Legacy& o) const  { return v < o.v; }
};

struct W {
  Legacy l;
  std::strong_ordering operator<=>(const W&) const = default;   // OK: synthesized from == and <
};

struct W2 {
  Legacy l;
  auto operator<=>(const W2&) const = default;   // defined as deleted
};

static_assert(W{{1}} < W{{2}});
static_assert(W{{1}} == W{{1}});   // the implicitly declared ==, which calls Legacy::operator==

int main() {}
```

This construction is called the **synthesized three-way comparison** for type `R` ([[g:synthesized-three-way-comparison|synthesized three-way comparison]]), introduced by [[P1186R3]]. ¶1 defines it for glvalues `a` and `b` of the same type:

- ¶1.1 if `a <=> b` is usable and can be explicitly converted to `R` with `static_cast`, the result is `static_cast<R>(a <=> b)`;
- ¶1.2 otherwise, if `a <=> b` is usable, or overload resolution for it finds at least one viable candidate, the synthesized three-way comparison is not defined;
- ¶1.3 otherwise, if `R` is not a comparison category type, or either `a == b` or `a < b` is not usable, it is not defined;
- ¶1.4 if `R` is `strong_ordering`, the result is `a == b ? equal : a < b ? less : greater`;
- ¶1.5 if `R` is `weak_ordering`, the same, except with `equivalent` in place of `equal`;
- ¶1.6 if `R` is `partial_ordering`, the result is `a == b ? equivalent : a < b ? less : b < a ? greater : unordered`.

Note 1: if overload resolution finds usable candidates that don't otherwise meet the requirements of the expressions above (for example, the result of `a < b` can't be converted to `bool`), the synthesized three-way comparison is ill-formed.

Item 1.2 prevents an unauthorized fallback: as long as the type has a `<=>`, even if its result can't be converted to `R` or the call is ambiguous, `==` and `<` aren't used instead. The type's author evidently has a design of their own for three-way comparison, and quietly bypassing it would be dangerous. `partial_ordering` needs one extra comparison, `b < a`, to distinguish `greater` from `unordered`.

¶2.2 When the return type is not `auto`, `R` can't contain a placeholder type (for example, `decltype(auto)` can't be written). If the synthesized three-way comparison of type `R` between some x<sub>i</sub> and itself is not defined, the function is defined as deleted.

## Defaulted `!=`, `<` and so on [class.compare.secondary]

¶1 A **secondary comparison operator** ([[g:secondary-comparison-operator|secondary comparison operator]]) is `<`, `>`, `<=`, `>=` or `!=`. A defaulted secondary comparison operator must have a declared return type of `bool`.

¶2 For parameters `x` and `y`, the operator function is defined as deleted if any of the following holds:

- ¶2.1 the first overload resolution for `x @ y` doesn't yield a usable candidate (¶2.1.1), or the selected candidate is not a rewritten candidate (¶2.1.2);
- ¶2.2 the second overload resolution, for the expression obtained by interpreting `x @ y` with the selected rewritten candidate (for example `(x <=> y) @ 0`), doesn't yield a usable candidate;
- ¶2.3 `x @ y` can't be implicitly converted to `bool`.

Neither overload resolution counts the defaulted function itself as a candidate, or it would select itself. If not deleted, the function returns `x @ y`.

That is, a defaulted `<` is a `<` implemented via `<=>`, and a defaulted `!=` is a `!=` implemented via `==`. Rewritten candidates already provide these automatically; the point of defaulting them is to get a function that really exists: one whose address can be taken, and which can be overridden as a virtual function.

```cpp run title="secondary.cpp" ok
#include <compare>

struct HasNoLessThan {};

struct C {
  friend HasNoLessThan operator<=>(const C&, const C&);
  bool operator<(const C&) const = default;   // OK: defined as deleted (¶2.2)
};

template<class T> concept LessComparable = requires(T a) { a < a; };
static_assert(!LessComparable<C>);

struct Good {
  int v;
  auto operator<=>(const Good&) const = default;
  bool operator<(const Good&) const = default;   // returns (x <=> y) < 0
};
static_assert(Good{1} < Good{2});
static_assert(&Good::operator< != nullptr);     // its address can be taken

int main() {}
```

`C` is Example 1 in [class.compare.secondary]: in `(x <=> y) < 0`, `HasNoLessThan < int` isn't usable, so `<` is deleted.

!!! note "Where Clang reports it"
    When `C`'s `<` is actually called, by the standard a deleted function is being used. Clang 23 instead reports the error inside the defaulted function: `invalid operands to binary expression ('HasNoLessThan' and 'int')`. For a `<=>` written as `std::strong_ordering` with a `double` member, Clang likewise reports a failed `static_cast` inside the function. The conclusion that the program is ill-formed is the same; and in contexts such as `requires`, Clang correctly treats them as deleted.

## Interaction with rewritten candidates

Defaulted comparisons generate only `==` and `<=>`. What makes them support six operators and swapped operands is the rewritten candidates of [[over.match.oper]]:

| Expression | Additional candidates considered | Meaning when selected |
|---|---|---|
| `x < y` (likewise `>`, `<=`, `>=`) | `x <=> y` and the reversed `y <=> x` | `(x <=> y) < 0` or `0 < (y <=> x)` |
| `x <=> y` | The reversed `y <=> x` | `0 <=> (y <=> x)` |
| `x != y` | `x == y` and the reversed `y == x` | `!(x == y)` or `!(y == x)` |
| `x == y` | The reversed `y == x` | `y == x` |

When two candidates are equally good, [[over.match.best]] prefers non-rewritten candidates over rewritten ones ([[over.match.best#2.8]]), and non-reversed over reversed ([[over.match.best#2.9]]).

### Ambiguity from reversal

Reversal makes forms like `1 == s` work automatically, but it also broke a category of old code: a non-`const` member `operator==` becomes ambiguous with its own reversed version.

```cpp run title="reversed-ambiguity.cpp" error
struct S {
  int x;
  bool operator==(const S& o) { return x == o.x; }   // forgot const
};

bool f(S a, S b) { return a == b; }
// a.operator==(b): a binds to S& (exact), b binds to const S&
// reversed b.operator==(a): a binds to const S&, b binds to S& (exact)
// each is better on one argument, so by the standard it is ambiguous

int main() { S a{1}, b{1}; return f(a, b) ? 0 : 1; }
```

Each candidate is better on one argument, and the non-reversed preference of [[over.match.best#2.9]] applies only when neither is worse on any argument, so by the standard it is ambiguous and the program is ill-formed. So that a large body of old code wouldn't stop compiling on upgrading to C++20, both Clang and GCC accept it, choosing the non-reversed one with a warning. Clang 23 reports `-Wambiguous-reversed-operator`: ISO C++20 considers the use ambiguous despite there being a unique best viable function. The right fix is to add `const` to the member `operator==`.

### Writing `!=` stops `==` from being rewritten

[[over.match.oper#4]] says that a function *F* named `operator==` is a **rewrite target** unless a matching `operator!=` (one that would correspond to *F* if renamed `operator==`) can be found in the relevant scope. Only rewrite targets can be reversed or used to implement `!=`. This rule comes from [[P2468R2]], applied as a defect report against C++20: since the author wrote `==` and `!=` as a pair, the compiler no longer rewrites on their behalf.

```cpp title="rewrite-target.cpp" error
struct A {
  int x;
  bool operator==(int i) const { return x == i; }
  bool operator!=(int i) const { return x != i; }   // corresponds to operator==(int)
};
struct B {
  int x;
  bool operator==(int i) const { return x == i; }   // no corresponding !=
};

bool f1(A a) { return 1 == a; }   // error: A::operator== isn't a rewrite target, so it can't be reversed
bool f2(B b) { return 1 == b; }   // OK: reversed to b == 1
bool f3(B b) { return 1 != b; }   // OK: !(b == 1)
```

!!! impl "Generated code"
    A defaulted `<=>` is a literal translation of [[class.spaceship#3]]: compare subobject by subobject and return at the first nonzero result; a defaulted `==` is a short-circuiting memberwise `&&`. The optimizer sees all the comparisons, and the generated code is usually the same as hand-written equivalent logic. Defaulted comparisons are implicitly `constexpr` when the conditions are met ([[dcl.fct.def.default]]), and their exception specification is implicit too: `noexcept` only if none of the member comparisons used can throw ([[except.spec]]).

!!! history
    C++20's [[P0515R3]] introduced `<=>`, the comparison categories and defaulted `<=>`. Then [[P1185R2]] stopped `==` from being rewritten to `<=>`, having a defaulted `<=>` implicitly declare a defaulted `==` instead; [[P1186R3]] added synthesized three-way comparison so legacy types with only `==` and `<` can be used with a defaulted `<=>`; [[P2002R1]] tidied up the forms that can be defaulted, the deletion conditions and the lookup context. [[P2468R2]], a defect report against C++20, introduced rewrite targets: `operator==` is no longer rewritten when a corresponding `operator!=` exists.

## Common misconceptions

!!! pitfall "Writing my own `<=>` gives me `==`"
    Only a defaulted `<=>` implicitly declares `==`. With a hand-written `<=>`, also write `bool operator==(const T&) const = default;` or a hand-written `==`.

!!! pitfall "Adding an `operator==(int)` doesn't affect same-type comparison"
    The condition in [[class.compare.default#4]] is that there is no member or friend named `operator==` at all. Any one of them suppresses the implicit `==`, and then you need to write `bool operator==(const T&) const = default;` explicitly.

!!! pitfall "`auto <=>` can handle legacy types with only `<`"
    `auto` doesn't synthesize ([[class.spaceship#2.1]]); the whole `<=>` is deleted, and `<`, `>` and so on become unusable along with it. Write the return type as a specific category, such as `std::weak_ordering`.

!!! pitfall "A class with floating-point members can declare a `std::strong_ordering <=>`"
    `<=>` on `double` returns `partial_ordering`, which can't be `static_cast` to `strong_ordering` or `weak_ordering`, so the synthesized three-way comparison isn't defined ([[class.spaceship#1.2]]) and the enclosing `<=>` is deleted. When you need a total order, write the comparison by hand, for example using `std::strong_order` on floating-point members.

!!! pitfall "Pointer members are compared by what they point to"
    A defaulted comparison compares the pointer values themselves, that is, the addresses. Comparing by content requires writing it by hand.

## Questions

!!! question "1. Which functions do `a == b` and `a < b` each call?"
    ```cpp nocheck
    struct Str {
      bool operator==(const Str&) const;
      std::strong_ordering operator<=>(const Str&) const;
    };
    struct T {
      int n;
      Str s;
      auto operator<=>(const T&) const = default;
    };
    T a, b;
    ```

<details markdown="1">
<summary>Answer</summary>

`a == b` calls the implicitly declared defaulted `T::operator==` ([[class.compare.default#4]]), which evaluates `a.n == b.n` (built-in) and then `a.s == b.s` (`Str::operator==`), skipping the latter if the former is false. No `<=>` is called.

`a < b`: `T` has no `operator<`, so it is rewritten as `(a <=> b) < 0`, calling the defaulted `T::operator<=>`. That evaluates `a.n <=> b.n` (built-in) and then `a.s <=> b.s` (`Str::operator<=>`), returning the first nonzero result. The return type is deduced as `strong_ordering`.
</details>

!!! question "2. Given `struct X { int v; bool operator<(const X&) const; bool operator==(const X&) const; };`, which of these classes have a usable `<=>`?"
    ```cpp nocheck
    struct Y1 { X x; auto operator<=>(const Y1&) const = default; };
    struct Y2 { X x; std::weak_ordering operator<=>(const Y2&) const = default; };
    struct Y3 { X x; std::partial_ordering operator<=>(const Y3&) const = default; };
    ```

<details markdown="1">
<summary>Answer</summary>

`Y1`'s `<=>` is defined as deleted: the return type is `auto` and `x <=> x` isn't usable ([[class.spaceship#2.1]]). `Y2`'s is usable, computed by synthesized three-way comparison per [[class.spaceship#1.5]]. `Y3`'s is usable, computed per [[class.spaceship#1.6]], with one extra call to `y < x`. All three implicitly declare a defaulted `==`, which calls `X::operator==`. Clang's results agree with this.
</details>

!!! question "3. Why doesn't synthesized three-way comparison fall back to `==` and `<` whenever overload resolution for `a <=> b` finds a viable candidate, even if it ends up ambiguous?"

<details markdown="1">
<summary>Answer</summary>

That shows the type's author really did provide a three-way comparison, and something is wrong with this particular call (ambiguity, the wrong result type, deletion and so on). Quietly switching to building it from `==` and `<` could give semantics inconsistent with the author's design, and would hide the error. Making the defaulted `<=>` deleted exposes the problem where it is used. Falling back only when the type has no three-way comparison at all is the design intent of [[P1186R3]].
</details>
