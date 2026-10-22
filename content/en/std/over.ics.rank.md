---
title: Ranking implicit conversion sequences
summary: "Which of two implicit conversion sequences is better: first compare the form (standard, user-defined, ellipsis), then apply the special rules within one form (braced lists, subsequences and ranks of standard conversions, reference binding, the same user-defined conversion), and finally a few fine-grained rules between standard conversions of equal rank."
updated: 2026-10-19
---

!!! tldr
    - Comparing two implicit conversion sequences has three layers: first the form, where a standard conversion sequence beats a user-defined conversion sequence, which beats an ellipsis; then the special rules within one form; finally a few fine-grained rules between standard conversions of the same rank.
    - A braced argument converting to `std::initializer_list` is preferred, overriding the other rules within the same form, so `f({42})` picks `f(std::initializer_list<long>)` over `f(int)`.
    - Doing one fewer conversion is better, but transformations such as array-to-pointer and lvalue-to-rvalue don't count in the comparison, so `g(int)` and `g(const int&)` can't be told apart for any argument.
    - An rvalue prefers to bind an rvalue reference, which is the basis of move semantics; when two references can both bind, the one whose referenced type has less cv is better.
    - Two user-defined conversion sequences can be compared only if they use the same constructor or conversion function; among standard conversions of the same rank, not converting to `bool`, not converting to `void*`, and staying closer in the inheritance hierarchy are better.

## Three layers of comparison

```cpp run ok
#include <cstdio>
#include <string>
void g(bool)        { std::puts("g(bool)"); }
void g(std::string) { std::puts("g(std::string)"); }
void e(int)         { std::puts("e(int)"); }
void e(...)         { std::puts("e(...)"); }
void f(int)         { std::puts("f(int)"); }
void f(double)      { std::puts("f(double)"); }
struct S { operator int() const { return 0; } };
int main() {
  g("abc");   // g(bool): layer one, a standard conversion beats a user-defined one
  e(S{});     // e(int): layer one, a user-defined conversion beats the ellipsis
  short s = 1;
  f(s);       // f(int): both standard conversions, a promotion beats a conversion
}
```

When [[over.match.best]] selects a function, it compares the [[g:implicit-conversion-sequence|implicit conversion sequences]] (ICSs) argument by argument; this subclause specifies which of two ICSs is better. The three forms of ICS (standard conversion sequence, user-defined conversion sequence, ellipsis conversion sequence) and the three ranks of standard conversions (Exact Match, Promotion, Conversion) are defined in [[over.best.ics]].

¶1 This subclause defines a **partial ordering** of ICSs. When S1 is a **better conversion sequence** than S2, S2 is a worse conversion sequence than S1. When S1 is neither better nor worse than S2, they are **indistinguishable** conversion sequences. A partial ordering means many ICSs can't be compared, which is how ambiguity arises.

## Layer one: the form (¶2)

¶2 When comparing the basic forms of ICSs:

- ¶2.1 a standard conversion sequence is better than a user-defined conversion sequence or an ellipsis conversion sequence;
- ¶2.2 a user-defined conversion sequence is better than an ellipsis conversion sequence.

This layer ignores rank. `const char*` → `bool` has Conversion rank, yet still beats any user-defined conversion, which is why `g("abc")` picks `g(bool)`.

## Layer two: within one form (¶3)

¶3 Two ICSs of the same form are indistinguishable unless one of the following rules applies.

### Braced lists (¶3.1)

```cpp run ok
#include <cstdio>
#include <initializer_list>
#include <string>
#include <utility>
using std::initializer_list;
void f1(int)                     { std::puts("f1(int)"); }
void f1(initializer_list<long>)  { std::puts("f1(il<long>)"); }
void f2(std::pair<const char*, const char*>) {
  std::puts("f2(pair)");
}
void f2(initializer_list<std::string>) {
  std::puts("f2(il<string>)");
}
int main() {
  f1({42});            // f1(il<long>)
  f2({"foo", "bar"});  // f2(il<string>)
}
```

¶3.1 When the argument is a braced list, the ICS is called a list-initialization sequence ([[over.ics.list]]). List-initialization sequence L1 is better than L2 if:

- ¶3.1.1 L1 converts to some `std::initializer_list<X>` and L2 doesn't; or, if that doesn't hold,
- ¶3.1.2 L1 and L2 both convert to arrays of the same element type and L1 initializes fewer elements than L2; or the same number, and L2 converts to an array of unknown bound while L1 doesn't.

!!! std
    "… even if one of the other rules in this paragraph would otherwise apply."

This rule overrides every other rule in ¶3, but not layer one. In `f1({42})`, `{42}` → `int` is identity and `{42}` → `initializer_list<long>` is the integral conversion `int` → `long` (the worst of the element conversions); both are standard conversion sequences and layer one can't separate them. In layer two, ¶3.1.1 directly decides in favor of `initializer_list`, without comparing ranks.

This agrees with the rule in [[over.match.list]] that prefers initializer-list constructors: the contents of the braces are preferably treated as a sequence of elements. Function arguments follow the same principle, so the behavior of `f({1})` and `T x{1}` doesn't contradict each other.

The array rules come from C++20's [[P0388R4]]:

```cpp run ok
#include <cstdio>
void f(int    (&&)[] ) { std::puts("#1 int[]"); }
void f(double (&&)[] ) { std::puts("#2 double[]"); }
void f(int    (&&)[2]) { std::puts("#3 int[2]"); }
int main() {
  f({1});          // #1
  f({1.0});        // #2
  f({1.0, 2.0});   // #2
  f({1, 2});       // #3
}
```

In `f({1})`, #1 beats #2 because identity beats a floating-integral conversion. #1 beats #3 because #3 has to initialize two elements (the second filled in from `{}`) while #1 initializes only one, a closer fit to the elements actually given. In `f({1, 2})`, #1 and #3 both initialize two elements, and #3, with a known bound, wins.

### Standard conversion sequences (¶3.2)

¶3.2 Two standard conversion sequences S1 and S2 are compared in the following order; the next rule is considered only if the previous doesn't hold.

#### One fewer step is better (¶3.2.1)

```cpp run ok
#include <cstdio>
void f(int*)       { std::puts("f(int*)"); }
void f(const int*) { std::puts("f(const int*)"); }
int main() {
  int i = 0;
  f(&i);   // f(int*)
}
```

¶3.2.1 If S1 is a proper subsequence of S2, S1 is better. The steps are arranged in the fixed order of [[over.ics.scs]] for the comparison, **excluding any Lvalue Transformation**; the identity conversion is considered a subsequence of any non-identity sequence.

A qualification conversion and identity are both Exact Match, the same rank; this rule makes the side that does nothing win.

Lvalue Transformations are the three conversions lvalue-to-rvalue, array-to-pointer and function-to-pointer. Because they don't count, both groups of calls below are ambiguous:

```cpp error
void f(int*);
void f(int (&)[3]);
void g(int);
void g(const int&);
void use() {
  int a[3];
  f(a);    // error: ambiguous; array-to-pointer doesn't count, both sides are effectively identity
  int i = 0;
  g(i);    // error: ambiguous; lvalue-to-rvalue doesn't count
  g(1);    // error: ambiguous
}
```

So for any argument, taking by value and taking by const reference can't be told apart. To dispatch on lvalue versus rvalue, use the two overloads `const T&` and `T&&` (¶3.2.3).

#### Rank (¶3.2.2)

¶3.2.2 S1 has a higher rank than S2; or both have the same rank but can be distinguished by the fine-grained rules of layer three (¶4). Ranks from highest to lowest are Exact Match, Promotion, Conversion. For example, with `f(int)` and `f(double)` both present, a `short` argument picks `f(int)` (a promotion beats a conversion) and a `float` argument picks `f(double)` (`float` → `double` is a promotion).

#### Rvalues prefer to bind rvalue references (¶3.2.3)

```cpp run ok
#include <cstdio>
int i;
int   f1() { return 0; }
int&& f2() { return static_cast<int&&>(i); }
int g(const int&)  { return 1; }
int g(const int&&) { return 2; }

struct A {
  A& operator<<(int) {
    std::puts("A::operator<<(int)"); return *this;
  }
  void p() &  { std::puts("p() &"); }
  void p() && { std::puts("p() &&"); }
};
A& operator<<(A&& a, char) {
  std::puts("operator<<(A&&, char)");
  return static_cast<A&>(a);
}

int main() {
  std::printf("%d %d %d\n", g(i), g(f1()), g(f2()));  // 1 2 2
  A() << 1;     // A::operator<<(int)
  A() << 'c';   // operator<<(A&&, char)
  A a;
  a << 1;       // A::operator<<(int)
  a << 'c';     // A::operator<<(int)
  A().p();      // p() &&
  a.p();        // p() &
}
```

¶3.2.3 If S1 and S2 are both reference bindings ([[dcl.init.ref]]), neither binds the implicit object parameter of a non-static member function declared without a ref-qualifier, and S1 binds an rvalue reference to an rvalue while S2 binds an lvalue reference, S1 is better.

With `f(const T&)` and `f(T&&)` both present, an rvalue argument picks the latter; move semantics rests on this rule. `f2()` returns `int&&`, so the call expression is an xvalue, also an rvalue, and likewise picks `g(const int&&)`.

For the member function exception, look at `A() << 1`:

| Call | `A::operator<<(int)` | `operator<<(A&&, char)` | Result |
|---|---|---|---|
| `A() << 1` | object: `A&` binds an rvalue (special permission); `1`: identity | object: `A&&` binds an rvalue; `1` → `char`: integral conversion | member |
| `A() << 'c'` | object: as above; `'c'` → `int`: promotion | object: as above; `'c'`: identity | non-member |
| `a << 1`, `a << 'c'` | viable | not viable; `A&&` can't bind an lvalue | member |

A member function without a ref-qualifier can also be called on an rvalue, in which case its implicit object parameter `A&` is specially permitted to bind the rvalue ([[over.match.funcs#5]]). If ¶3.2.3 applied to such a parameter, then for `A() << 1` the non-member would be better on the first argument and the member better on the second, making it ambiguous. The exception ensures that adding a non-member overload taking an rvalue reference to a class written before C++11 doesn't make existing calls ambiguous. The ref-qualified `p() &` and `p() &&` aren't affected by the exception and are distinguished by ¶3.2.3 as usual.

#### Function lvalues prefer to bind lvalue references (¶3.2.4)

```cpp run ok
int f(void(&)())  { return 1; }   // #1
int f(void(&&)()) { return 2; }   // #2
void g() {}
int main() { return f(g) == 1 ? 0 : 1; }   // calls #1
```

¶3.2.4 If S1 and S2 are both reference bindings, S1 binds an lvalue reference to a function lvalue and S2 binds an rvalue reference to a function lvalue, S1 is better. Functions are only lvalues, but an rvalue reference can also bind one ([[over.ics.ref#3]]); this rule makes the result match the fact that functions are lvalues.

#### Adding less cv is better (¶3.2.5)

```cpp
int f(const volatile int*);
int f(const int*);
int i;
int j = f(&i);   // f(const int*)

int g(const int*);
int g(const volatile int* const&);
int* p;
int k = g(p);    // per the standard: g(const int*)
```

¶3.2.5 If S1 and S2 differ only in their qualification conversion and yield [[g:similar-types|similar]] but different types T1 and T2 (a reference binding is considered to yield the cv-unqualified referenced type), and `const T2` is reference-compatible with T1 ([[dcl.init.ref]]), S1 is better. Intuitively, when both sides add cv, the one that adds less is better.

In `g(p)`, `g(const volatile int* const&)` is a direct binding, which by [[over.ics.ref#1.4]] is also a qualification conversion, and by the parenthetical rule the resulting type is `const volatile int*`. It adds `volatile` on top of `const int*`, so `g(const int*)` is better.

!!! impl "Clang deviates"
    In our tests Clang 23 handles `f(&i)` as the standard says, but reports "call to 'g' is ambiguous" for `g(p)`. Per the standard ([over.ics.rank] Example 5), `g(const int*)` should be called.

#### Less cv on the referenced type is better (¶3.2.6)

```cpp
int f(const int&);
int f(int&);
int g(const int&);
int g(int);
struct X {
  void f() const;
  void f();
};
int h(int (&)[]);
int h(int (&)[1]);
void use(const X& a, X b) {
  int i = 0;
  f(i);      // f(int&)
  g(i);      // error: ambiguous; g(int) isn't a reference binding
  a.f();     // X::f() const: the only viable one
  b.f();     // X::f()
  int arr[1];
  h(arr);    // per the standard: h(int (&)[1])
}
```

¶3.2.6 If S1 and S2 bind references to T1 and T2 respectively, T1 and T2 are different, and T2 is reference-compatible with T1, S1 is better. That is, the referenced type with less cv is better, and a known array bound is better.

`b.f()` shows how const overloading of member functions works: the implicit object parameters are `X&` and `const X&`, and by this rule the non-const version is better; a const object can only call the const version.

!!! impl "Clang deviates"
    In our tests Clang 23 reports `h(arr)` as ambiguous. Per the standard ([over.ics.rank] Example 6), `int (&)[1]` is better. This part of the rule came in with C++20's [[P0388R4]]. Clang agrees with the standard on the other lines.

#### Same reference type, different sources (¶3.2.7)

```cpp
struct Z {};
struct A {
  operator Z&();
  operator const Z&();    // #1
};
struct B {
  operator Z();
  operator const Z&&();   // #2
};
const Z& r1 = A();        // OK: uses #1
const Z&& r2 = B();       // OK: uses #2
```

¶3.2.7 If S1 and S2 bind the same reference type "reference to `T`" and have source types V1 and V2, and the standard conversion sequence from `V1*` to `T*` is better than the one from `V2*` to `T*`, S1 is better.

Different source types occur only when comparing the second standard conversion after a user-defined conversion ([[over.match.best#2.2]]). Both conversion function results for `r1` can bind `const Z&`; restated in terms of pointers, `const Z*` → `const Z*` is identity and `Z*` → `const Z*` is a qualification conversion, so #1 is better. This way the comparison of references reuses the rules of ¶3.2.1 and ¶3.2.5 for qualification conversions.

!!! impl "Clang deviates"
    In our tests Clang 23 reports "reference initialization … is ambiguous" for both `r1` and `r2`; it doesn't implement this rule yet.

### User-defined conversion sequences (¶3.3)

```cpp run ok
#include <cstdio>
struct A {
  operator short() { return 0; }
} a;
int f(int)   { return 1; }
int f(float) { return 2; }
int main() {
  std::printf("%d\n", f(a));   // 1
}
```

¶3.3 User-defined conversion sequence U1 is better than U2 only if they use the same conversion function or constructor (or initialize the same class in an aggregate initialization) and U1's second standard conversion is better than U2's. In the example both sides go through `operator short()`; `short` → `int` is a promotion and `short` → `float` a conversion, so `f(int)` wins.

When they don't use the same conversion, the two sequences can't be compared:

```cpp error
struct C { C(int); };
struct D { D(double); };
void f(C);
void f(D);
void use() {
  f(1);   // error: ambiguous
}
```

`int` → `int` is clearly a better match than `int` → `double`, but that's a difference in the first part; this rule compares only the second part, and only between uses of the same conversion.

## Layer three: standard conversions of the same rank (¶4)

¶4 Standard conversion sequences are ordered by rank: Exact Match is better than Promotion, which is better than Conversion. Two sequences of the same rank are indistinguishable unless one of the following rules applies.

### Not converting to `bool` (¶4.1)

```cpp run ok
#include <cstdio>
void h(bool)  { std::puts("h(bool)"); }
void h(void*) { std::puts("h(void*)"); }
int main() {
  int* p = nullptr;
  h(p);   // h(void*)
}
```

¶4.1 A conversion that doesn't convert a pointer or pointer to member to `bool` is better than one that does. `int*` → `void*` and `int*` → `bool` both have Conversion rank, and this rule makes the former win. Converting a pointer to `bool` loses the most information; since C++20 it also counts as narrowing in brace initialization.

### Enumeration promoted to its underlying type (¶4.2)

```cpp run ok
#include <cstdio>
enum E : short { e };
int g(short) { return 1; }
int g(int)   { return 2; }
int main() { std::printf("%d\n", g(e)); }   // 1
```

¶4.2 For an enumeration with a fixed underlying type, promoting to the underlying type is better than promoting to the promoted underlying type (when the two differ). By [[conv.prom#4]], `E` → `short` and `E` → `int` are both integral promotions; without this rule the call would be ambiguous.

### Floating-point types of equal rank (¶4.3) {{c++23}}

```cpp
#include <stdfloat>
int f(std::float32_t);
int f(std::float64_t);
int f(long long);
float x;
std::float16_t y;
int i = f(x);   // calls f(std::float32_t) on implementations where float and float32_t have equal conversion ranks
int j = f(y);   // error: ambiguous; no candidate has a rank equal to float16_t's
```

¶4.3 A conversion in either direction between floating-point type FP1 and floating-point type FP2 is better than a conversion in the same direction between FP1 and arithmetic type T3 if:

- ¶4.3.1 the [[g:floating-point-conversion-rank|floating-point conversion rank]] of FP1 is equal to that of FP2 ([[conv.rank]]), and
- ¶4.3.2 T3 is not a floating-point type; or T3 is a floating-point type whose rank is not equal to FP1's; or the floating-point conversion subrank of FP2 is greater than that of T3.

C++23 added this rule along with the extended floating-point types ([[P1467R9]]). `float` to `std::float32_t`, `std::float64_t` and `long long` all have Conversion rank; this rule makes `std::float32_t`, which has the same format, win. libc++ in our tests doesn't have `<stdfloat>` yet, so this example hasn't been compiled.

### To `void*` is worse (¶4.4)

¶4.4 If class `B` is derived directly or indirectly from `A`, `B*` → `A*` is better than `B*` → `void*`, and `A*` → `void*` is better than `B*` → `void*`. So with `v(void*)` and `v(A*)` both present, a `B*` argument picks `v(A*)`.

### Closer in the inheritance hierarchy (¶4.5)

```cpp run ok
#include <cstdio>
struct A { int m; };
struct B : A {};
struct C : B {};
int f(A*) { return 1; }
int f(B*) { return 2; }
int g(A)  { return 1; }
int g(B)  { return 2; }
int h(int B::*) { return 1; }
int h(int C::*) { return 2; }
int main() {
  C c;
  std::printf("%d %d %d\n", f(&c), g(c), h(&A::m));   // 2 2 1
}
```

¶4.5 If `B` is derived from `A` and `C` from `B` (directly or indirectly), the closer conversion is better:

| Rule | Better | Worse | Compares |
|---|---|---|---|
| ¶4.5.1 | `C*` → `B*` | `C*` → `A*` | same source, different targets |
| ¶4.5.2 | `A::*` → `B::*` | `A::*` → `C::*` | likewise, pointers to members (direction from base to derived) |
| ¶4.5.3 | `C` → `B` | `C` → `A` | likewise, class objects |
| ¶4.5.4 | `B*` → `A*` | `C*` → `A*` | different sources, same target |
| ¶4.5.5 | `B::*` → `C::*` | `A::*` → `C::*` | likewise, pointers to members |
| ¶4.5.6 | `B` → `A` | `C` → `A` | likewise, class objects |

Note 1 points out that the different-source cases (¶4.5.4–¶4.5.6) arise only when comparing the second standard conversion after a user-defined conversion ([[over.match.best#2.2]]), for example a class with both `operator B()` and `operator C()` picks `operator B()` when used to initialize an `A`. Elsewhere the source is the same and the targets differ, and ¶4.5.1–¶4.5.3 apply.

## All the rules at a glance

```text
Comparing two ICSs for the same argument: S1 vs S2
├─ Different forms: standard > user-defined > ellipsis                        ¶2
├─ Both braced lists: initializer_list first; fewer array elements, known bound first   ¶3.1
├─ Both standard conversions:
│    ¶3.2.1 proper subsequence (Lvalue Transformations excluded)
│    ¶3.2.2 rank; for equal rank, see ¶4:
│             not to bool / enum to underlying type / equal-rank floating point / not to void* / closer in hierarchy
│    ¶3.2.3 rvalue binds rvalue reference (except implicit object parameter without ref-qualifier)
│    ¶3.2.4 function lvalue binds lvalue reference
│    ¶3.2.5 qualification conversion adds less cv
│    ¶3.2.6 referenced type has less cv, known array bound
│    ¶3.2.7 same reference type, better pointer conversion from the source
├─ Both user-defined: compare the second part only for the same conversion, else indistinguishable   ¶3.3
└─ Otherwise: indistinguishable
```

## Implementation view

!!! impl
    - Clang's `CompareImplicitConversionSequences`, `CompareStandardConversionSequences`, `CompareQualificationConversions` and `CompareDerivedToBaseConversions` are essentially a paragraph-by-paragraph implementation of this subclause; reading them is a good way to check your understanding.
    - This page has three places where Clang 23 disagrees with the standard: the reference side of the qualification conversion in ¶3.2.5, the array bound in ¶3.2.6, and ¶3.2.7. All are rules added or revised in the standard in recent years.
    - These rules only decide which function is called; they have no runtime cost.

## History

!!! history
    - C++98 already had the three-layer structure, proper subsequence, rank, less cv, inheritance distance, and pointer-to-`bool` being worse.
    - C++11's rvalue references brought ¶3.2.3 (including the implicit object parameter exception) and ¶3.2.4; list-initialization brought ¶3.1.1; enumerations with a fixed underlying type brought ¶4.2.
    - C++20's [[P0388R4]] added the list-initialization ordering for arrays (¶3.1.2) and the reference-binding comparison for arrays of unknown bound.
    - C++23's [[P1467R9]] added rule ¶4.3 for extended floating-point types.
    - Wording after C++23 restated ¶3.2.5 in terms of similar types and reference-compatibility, and added ¶3.2.7.

## Common misconceptions

!!! pitfall "`initializer_list` is preferred only for constructors"
    ¶3.1.1 applies to ordinary functions too: with `f(int)` and `f(std::initializer_list<long>)` both present, `f({42})` picks the latter.

!!! pitfall "The compiler compares which of two converting constructors matches its input better"
    The first parts of different user-defined conversions are not compared; if both are viable, it's ambiguous (¶3.3).

!!! pitfall "A `bool` parameter is a safe fallback"
    Pointers, string literals and pointers to members can all become `bool` through standard conversions, and a standard conversion beats any user-defined conversion (¶2).

## Questions

!!! question "Question 1"
    Explain the result of each call.
    ```cpp
    #include <string_view>
    void f(long);           void f(double);           // f(1)
    void g(unsigned char);  void g(int);              // g('a')
    void h(const char*);    void h(std::string_view); // h("x")
    void k(int&&);          void k(const int&);       // int x; k(x); k(1);
    ```

<details markdown="1">
<summary>Answer</summary>

- `f(1)`: `int` → `long` is an integral conversion and `int` → `double` a floating-integral conversion, both Conversion rank; nothing in ¶4 distinguishes them, so it's ambiguous.
- `g('a')`: `char` → `int` is an integral promotion and `char` → `unsigned char` an integral conversion, so `g(int)` is picked.
- `h("x")`: array-to-pointer is a standard conversion, while converting to `std::string_view` calls a constructor, a user-defined conversion, so `h(const char*)` is picked.
- `k(x)`: `int&&` can't bind an lvalue, so only `k(const int&)` is viable. `k(1)`: both are viable; by ¶3.2.3 an rvalue binding an rvalue reference is better, so `k(int&&)` is picked.
</details>

!!! question "Question 2"
    If the exception for the implicit object parameter in ¶3.2.3 were removed, which call in the standard's example would change its result?

<details markdown="1">
<summary>Answer</summary>

`A() << 1` would become ambiguous. The non-member `operator<<(A&&, char)` is better on the first argument (an rvalue binding an rvalue reference), and the member `A::operator<<(int)` is better on the second (identity beats an integral conversion), so each wins one argument. `A() << 'c'` is unaffected: the non-member is already better on the second argument and no worse on the first.
</details>
