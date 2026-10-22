---
title: Implicit conversion sequences
summary: "The tool overload resolution uses to measure how well an argument matches a parameter: standard conversion sequences and their three ranks, user-defined conversion sequences, ellipsis conversion sequences, special rules for reference binding and braced-list arguments, plus the limit of one user-defined conversion per conversion and ambiguous conversion sequences."
updated: 2026-10-19
---

!!! tldr
    - An implicit conversion sequence describes copy-initializing the parameter from the argument, looking only at type, cv-qualification and value category. Access, bit-fields, whether a function is deleted, and narrowing are checked only after the function is selected.
    - Implicit conversion sequences come in three forms: standard conversion sequence, user-defined conversion sequence, ellipsis conversion sequence. Standard conversion sequences have three ranks: Exact Match, Promotion, Conversion; a sequence's rank is that of its worst step.
    - Passing an object of the same class by value counts as the identity conversion, and passing an object of a derived class counts as Conversion rank, even though a constructor is actually called.
    - An argument's implicit conversion contains at most one user-defined conversion; the implicit object parameter accepts only standard conversions.
    - When the argument is a braced list, `std::initializer_list`, arrays, aggregates, non-aggregate classes and scalars each have their own rule.

## A surprising overload

```cpp run ok
#include <string>
#include <cstdio>
void f(const char*) { std::puts("f(const char*)"); }
void f(std::string) { std::puts("f(std::string)"); }
void g(bool)        { std::puts("g(bool)"); }
void g(std::string) { std::puts("g(std::string)"); }
int main() {
  f("abc");   // f(const char*)
  g("abc");   // g(bool)
}
```

`g("abc")` picks `g(bool)`. The string literal first decays to `const char*`, then a boolean conversion makes it `bool`, using only built-in conversions throughout. Converting to `std::string` requires calling a constructor of `std::string`, which is a user-defined conversion. Overload resolution specifies that a sequence using only built-in conversions always beats one that uses a user-defined conversion, however unreasonable the built-in conversion looks ([[over.ics.rank#2]]).

To understand results like this, you first need to know how the compiler describes the conversion of one argument to one parameter.

## What an implicit conversion sequence is [over.best.ics.general]

¶1 An **implicit conversion sequence** (ICS) is the sequence of conversions used to convert an argument in a function call to the type of the corresponding parameter. It follows the rules for initializing an object or reference by a single expression ([[dcl.init]], [[dcl.init.ref]]). In other words, an ICS describes initializing the parameter from the argument, and it is what [[over.match.best]] compares argument by argument.

¶2 An ICS cares only about the argument's type, cv-qualification and value category, and how to make them agree with the parameter.

!!! std
    "Other properties, such as the lifetime, storage duration, linkage, alignment, accessibility of the argument, whether the argument is a bit-field, and whether a function is deleted, are ignored."

So a function may be viable because an ICS exists, get selected, and then fail when the parameter is actually initialized (note 1):

```cpp error
struct S { int b : 3; };
void f(int&);
void use(S s) {
  f(s.b);   // error: a non-const reference can't bind to a bit-field
}
```

When the ICS is computed, the bit-field `s.b` is treated as an ordinary `int` lvalue, an exact match for `int&`, so `f` is viable ([[over.ics.ref#4]]). Only after selection does the rule forbidding binding a non-const lvalue reference to a bit-field ([[dcl.init.ref]]) take effect.

¶3 A well-formed ICS takes one of three forms:

1. **standard conversion sequence**: uses only built-in conversions ([[conv]]);
2. **user-defined conversion sequence**: goes through one constructor or conversion function in the middle;
3. **ellipsis conversion sequence**: the argument corresponds to `...`.

In comparisons a standard conversion sequence is best and an ellipsis worst ([[over.ics.rank#2]]), which is why `g(bool)` wins in the opening example.

¶10–¶11 When no conversion is needed, the ICS is a standard conversion sequence consisting only of the identity conversion. When no conversion can be found, no ICS can be formed and the function isn't viable. ¶13 just says that the three forms are defined in the subclauses that follow.

## Standard conversion sequences [over.ics.scs]

### Categories and ranks (¶1–¶3)

¶1 The standard sorts the conversions of [[conv]] into four categories, and ¶3 gives each conversion a **rank**: Exact Match, Promotion or Conversion.

| Conversion | Category | Rank |
|---|---|---|
| No conversion required | Identity | Exact Match |
| Lvalue-to-rvalue ([[conv.lval]]) | Lvalue Transformation | Exact Match |
| Array-to-pointer ([[conv.array]]) | Lvalue Transformation | Exact Match |
| Function-to-pointer ([[conv.func]]) | Lvalue Transformation | Exact Match |
| Qualification conversion, e.g. `int*` → `const int*` ([[conv.qual]]) | Qualification Adjustment | Exact Match |
| Function pointer conversion, dropping `noexcept` ([[conv.fctptr]]) | Qualification Adjustment | Exact Match |
| Integral promotion ([[conv.prom]]) | Promotion | Promotion |
| Floating-point promotion, only `float` → `double` ([[conv.fpprom]]) | Promotion | Promotion |
| Integral conversion ([[conv.integral]]) | Conversion | Conversion |
| Floating-point conversion ([[conv.double]]) | Conversion | Conversion |
| Floating-integral conversion ([[conv.fpint]]) | Conversion | Conversion |
| Pointer conversion, including null pointer, to `void*`, derived to base ([[conv.ptr]]) | Conversion | Conversion |
| Pointer-to-member conversion ([[conv.mem]]) | Conversion | Conversion |
| Boolean conversion ([[conv.bool]]) | Conversion | Conversion |

Note 1 points out that the four categories don't overlap: an Lvalue Transformation changes only the value category, a Qualification Adjustment changes only cv-qualification, and Promotions and Conversions change only the data representation.

¶2 Note 2 adds that a standard conversion sequence is either the identity conversion alone or one to three conversions from the other categories, in a fixed order: an Lvalue Transformation, then a Promotion or Conversion, finally a Qualification Adjustment. For example, the string literal `"abc"` to `const void*` is array-to-pointer followed by the pointer conversion `const char*` → `const void*`.

¶3 The rank of the whole sequence is that of its worst step, with reference binding also counting as a step: if any step has Conversion rank, it's Conversion; otherwise if any has Promotion rank, it's Promotion; otherwise it's Exact Match. The example above has Conversion rank. `int[3]` to `const int*` is array-to-pointer plus a qualification conversion, with Exact Match rank.

### Ranks that are easy to get wrong

```cpp error
void f(int);    void f(long);
void g(double); void g(long double);
void h(int);    void h(unsigned);
void p(void*);  void p(const int*);
void q(int*);   void q(long);
void use(short s, float fl, char c, int* ip) {
  f(s);    // f(int): short → int is a promotion, short → long a conversion
  g(fl);   // g(double): float → double is a promotion, float → long double a conversion
  h(c);    // h(int): char → int is a promotion, char → unsigned a conversion
  p(ip);   // p(const int*): a qualification conversion is Exact Match, to void* is a conversion
  q(0);    // error: ambiguous, 0 → int* and 0 → long both have Conversion rank
}
```

- The only floating-point promotion is `float` → `double`. `float` → `long double` and `double` → `long double` are floating-point conversions.
- Integral promotions target only a few types such as `int` and `unsigned int` (character types, unscoped enumerations and bit-fields have their own rules; see [[conv.prom]]). `short` → `long` and `int` → `long` are integral conversions. `bool` → `int` is a promotion.
- A qualification conversion is Exact Match, so `int*` → `const int*` has the same rank as identity; the two are told apart by [[over.ics.rank#3.2.1]].

`q(0)` is the old problem with `NULL`, and one of the reasons C++11 introduced `nullptr`. `nullptr` converts to any pointer type but not to `long`, so `q(nullptr)` isn't ambiguous.

## User-defined conversion sequences [over.ics.user]

¶1 A user-defined conversion sequence has three parts:

```text
initial standard conversion  →  one user-defined conversion ([class.conv])  →  second standard conversion
```

When the user-defined conversion is done by a constructor ([[class.conv.ctor]]), the first part converts the source type to the type of that constructor's first parameter; when it is done by a conversion function, the first part converts the source type to the type of the conversion function's object parameter.

¶2 The second part converts the result of the user-defined conversion to the destination type; reference binding also counts as part of it. Take `f("hello")` calling `void f(std::string)`: the first part is array-to-pointer, the user-defined conversion is the constructor `std::string(const char*)`, and the second part is identity.

The last sentence of paragraph 2 also says that choosing which constructor or conversion function to use is itself an overload resolution, subject to the special rules for initialization by user-defined conversion, such as comparing the step from the conversion result to the destination ([[over.match.best#2.2]]).

¶3 If the user-defined conversion is done by a specialization of a conversion function template, the second part must have Exact Match rank. `template<class T> operator T()` can convert to any type; if a promotion or conversion were then still allowed after it, it would be viable for almost any destination and create a lot of ambiguity with other candidates. Template argument deduction ([[temp.deduct.conv]]) usually deduces the destination type directly, so the second part is identity anyway; ¶3 rules out the remaining cases.

### Passing class objects by value (¶6–¶7, [over.ics.user]/4)

```cpp error
struct A {
  A();
  A(A&);      // only a copy constructor taking non-const
};
void f(A);
void f(...);
void use(const A ca) {
  f(ca);      // error: f(A) is selected, but no constructor can initialize the parameter from const A
}
```

[[over.best.ics#6]] specifies that when the parameter isn't a reference, the ICS describes copy-initializing the parameter from the argument, that is, converting the argument to a prvalue of the parameter type. Note 3 adds that when the parameter has class type, this is only a conceptual conversion defined for overload resolution; the actual initialization is done by a constructor.

[[over.best.ics#7]] specifies that when the argument type without cv is the same as the parameter type, the ICS is the **identity conversion**; when the parameter has class type and the argument is of a derived class, the ICS is a **derived-to-base Conversion**, with Conversion rank. Note 4 explains that there's no such conversion among the standard conversions; it exists only in the description of ICSs.

In the example above, the ICS from `const A` to `A` is identity and contains no conversion at all, even though `A` has no constructor that accepts `const A` (the standard's Example 2). So `f(A)` is viable and beats the ellipsis by identity, and the error comes only when the parameter is initialized after selection.

[over.ics.user]/4 says the same thing from another angle: converting an expression of class type to the same class type is an Exact Match, and to a base class is Conversion rank, even though a constructor is actually called. If passing an object of the same class by value counted as a user-defined conversion, `f(A)` would be much worse than `f(const A&)`, and overloads taking an object by value and by reference couldn't be compared sensibly.

## At most one user-defined conversion per conversion (¶4)

```cpp error
struct Y { Y(int); };
struct A { operator int(); };
Y y1 = A();   // error: needs A → int → Y, two user-defined conversions

struct X { X(); };
struct B { operator X(); };
B b;
X x{{b}};     // error: B::operator X() is not a candidate
```

¶4 When a constructor or conversion function is itself being called as a user-defined conversion, its argument can't go through another user-defined conversion. Specifically, when the target is one of:

- ¶4.1 the first parameter of a constructor;
- ¶4.2 the object parameter of a user-defined conversion function;

and the function became a candidate by one of:

- ¶4.3 [[over.match.ctor]], when the argument is the temporary in the second step of a class copy-initialization;
- ¶4.4 [[over.match.copy]], [[over.match.conv]] or [[over.match.ref]];
- ¶4.5 the second phase of [[over.match.list]], when the braced list has exactly one element that is itself a braced list, the target is the first parameter of a constructor of class `X`, and the conversion is to `X` or reference to cv `X`;

user-defined conversion sequences are not considered. Note 2 explains the purpose: to prevent more than one user-defined conversion in overload resolution, and thus avoid infinite recursion.

`Y y1 = A()` copy-initializes a `Y` from a value of type `A`; the candidates come from [[over.match.copy]], where `Y(int)` is itself that one user-defined conversion. Its parameter needs `A → int`, another user-defined conversion, which by ¶4.1 and ¶4.4 isn't considered, so `Y(int)` isn't viable.

In `X x{{b}}`, `{b}` has to match the first parameter `const X&` or `X&&` of `X`'s copy or move constructor, so ¶4.5 applies and the conversion `b → X` isn't considered. Otherwise this initialization would become converting `b` into a temporary `X` first and then constructing `x` from it.

The one-user-defined-conversion limit is per argument. Each parameter of a multi-parameter constructor corresponds to a different argument, and each can have one user-defined conversion.

## Object parameters (¶8–¶9)

¶8 A static member function is also treated as having an implicit object parameter, so that it can be compared alongside non-static member functions in the same candidate set. The ICS for that parameter is neither better nor worse than any standard conversion sequence, so the comparison depends entirely on the other arguments.

¶9 For a conversion to the implicit object parameter, or to the left operand of an assignment operation, only standard conversion sequences are allowed. Otherwise `x.f()` could first convert `x` to an unrelated type and then call a member of that type. Note 5 points out that an explicit object parameter (C++23's `this` parameter) is an ordinary parameter and can be matched through a user-defined conversion:

```cpp ok
struct C {
  void k(this int);   // the explicit object parameter is int
  operator int() const { return 0; }
  void m(this const C& c) {
    c.k();            // OK: c → int via a user-defined conversion
  }
};
```

## Ambiguous conversion sequences (¶12)

```cpp error
class B;
class A { A(B&); };
class B { operator A(); };
class C { C(B&); };
void f(A) { }
void f(C) { }
B b;
void use() {
  f(b);   // error: ambiguous
}
```

There are two ways to convert `b` to `A`: `A`'s constructor `A(B&)`, and `B`'s conversion function `operator A()`. Both functions are private in the example, but the ICS ignores access.

¶12 If more than one well-formed ICS can convert the argument to the parameter type, the ICS for that parameter is the **ambiguous conversion sequence**. For ranking, it is treated as a user-defined conversion sequence that is indistinguishable from any other user-defined conversion sequence. If the function that uses it is eventually selected, the call is ill-formed.

So `f(A)` is still viable; its ICS and `f(C)`'s are both user-defined conversions that can't be told apart, and the call is ambiguous. Note 6 explains the intent: don't silently drop a whole function because the conversion for one parameter is ambiguous. If ambiguity were treated as no conversion, `f(b)` would select `f(C)`; and if someone later removed one of the conversion paths to `A`, `f(A)` would become viable again and the call target would silently change.

Add a `void f(B)` and the call is no longer ambiguous: `f(B)` is identity, which beats both user-defined conversion sequences.

## Ellipsis conversion sequences [over.ics.ellipsis]

¶1 An ellipsis conversion sequence is formed when an argument matches the `...` of the called function. Almost any argument can match `...`, and it is the worst of the three forms, so `f(...)` can serve as a fallback overload. Pre-C++11 SFINAE detection often used this trick:

```cpp run ok
#include <type_traits>
template<class T> std::true_type  has_size_impl(decltype(&T::size));
template<class T> std::false_type has_size_impl(...);
struct A { int size(); };
struct B {};
static_assert(decltype(has_size_impl<A>(nullptr))::value);
static_assert(!decltype(has_size_impl<B>(nullptr))::value);
int main() {}
```

For `A`, the first overload is viable, and `nullptr` to a pointer to member function has Conversion rank, which beats the ellipsis. For `B`, deduction fails for the first overload, leaving only the ellipsis.

In an evaluated context, passing a class object with a non-trivial copy constructor, move constructor or destructor to `...` is conditionally-supported ([[expr.call]]). The example above is inside `decltype`, unevaluated, so the issue doesn't arise.

## Reference binding [over.ics.ref]

### Direct binding (¶1)

A reference **binds directly** ([[dcl.init.ref]]) when it binds to the argument itself (or a base class subobject of it), without a temporary.

¶1 When a reference parameter of type cv `T` binds directly to the argument:

- ¶1.1 the argument type `D` is derived from `T`: the ICS is the derived-to-base Conversion from `D` to `T`, with Conversion rank;
- ¶1.2 otherwise, if the argument type is (possibly cv-qualified) `T`, or `T` is an array of unknown bound of `U` and the argument is an array of known bound of (possibly cv-qualified) `U`: the ICS is identity;
- ¶1.3 otherwise, if `T` is a function type: the ICS is a function pointer conversion (the argument is a `noexcept` function and the parameter a reference to a function without `noexcept`);
- ¶1.4 otherwise: the ICS is a qualification conversion.

```cpp
struct A {};
struct B : public A {} b;
int f(A&);
int f(B&);
int i = f(b);               // f(B&): identity beats derived-to-base

void g() noexcept;
int h(void (&)() noexcept); // #1
int h(void (&)());          // #2
int j = h(g);               // #1: identity beats a function pointer conversion
```

By ¶1.2, binding `const int&` to an `int` lvalue is also identity; the argument having less cv than the parameter doesn't count as a conversion and is compared separately by [[over.ics.rank#3.2.6]]. The part of ¶1.2 about arrays of unknown bound comes from C++20's [[P0388R4]], which allows `int(&)[]` to bind to `int[3]`. ¶1.4 arises with multi-level pointers plus cv, for example `const int* const&` binding directly to an `int*` lvalue.

If the reference binds directly to the result of applying a conversion function to the argument, the ICS is a user-defined conversion sequence whose second part is determined by the four rules above.

!!! impl "Clang deviates"
    In our tests Clang 23 reports "call to 'h' is ambiguous" for `h(g)`; it doesn't treat the function pointer conversion as a worse sequence than identity. Per the standard (this is Example 1 of [over.ics.ref]), #1 should be called. The result for `f(b)` agrees with the standard.

### Not binding directly (¶2)

¶2 When the reference doesn't bind directly, the ICS is the sequence needed to convert the argument to the referenced type, as if copy-initializing a temporary of the referenced type from the argument. For example, `void f(const long&)` accepting an `int` argument has the ICS `int` → `long`, an integral conversion. Differences in top-level cv on the referenced type are absorbed by the initialization itself and don't count as a conversion.

### Restrictions on lvalues and rvalues (¶3–¶4)

¶3 Except for the implicit object parameter (see [[over.match.funcs]]), the following two bindings can't form an ICS: binding an lvalue reference to an rvalue, unless it refers to a non-volatile const type; binding an rvalue reference to an lvalue of object type.

```cpp error
void f(const volatile int&);
void g(int&&);
void h(void(&&)());
void fn();
void use(int i) {
  f(1);    // error: an lvalue reference to const volatile can't bind to an rvalue
  g(i);    // error: an rvalue reference can't bind to an lvalue of object type
  h(fn);   // OK: an rvalue reference can bind to a function lvalue
}
```

Note 1 points out that this means if the parameter is a non-const lvalue reference and the argument would need a temporary to be created, the function isn't viable. Functions are only lvalues, and an rvalue reference can bind to a function lvalue, so ¶3 restricts only lvalues of object type.

¶4 Other restrictions on binding that don't depend on the types of the reference and the argument don't affect forming the ICS. The bit-field example earlier is such a case (the standard's Example 2).

## Braced-list arguments [over.ics.list]

¶1 When the argument is a braced list ([[dcl.init.list]]), it isn't an expression and has no type, so the conversion rules are specified separately. The rules below are joined by "otherwise"; take the first that applies, in order:

| Paragraph | Parameter type | Condition | ICS |
|---|---|---|---|
| ¶2 | non-reference | the list has designators | a user-defined conversion sequence (second part identity) if the parameter is an aggregate that can be aggregate-initialized from it; otherwise no conversion |
| ¶3 | aggregate class `X` | exactly one element, of type cv `U`, where `U` is `X` or derived from `X` | the sequence converting that element to the parameter type |
| ¶4 | character array | exactly one element, a string literal of suitable type | identity |
| ¶5 | `std::initializer_list<X>` | every element can be implicitly converted to `X` | the worst of the element conversions; identity for an empty list |
| ¶6 | `X[N]` or `X[]` | every element (plus padding `{}` if `N` is larger) can be converted to `X` | the worst of them |
| ¶7 | non-aggregate class `X` | [[over.match.list]] chooses a single best constructor `C` | see below |
| ¶8 | aggregate | can be initialized by the aggregate initialization rules | a user-defined conversion sequence (second part identity) |
| ¶9 | reference | | per [over.ics.ref], with this section's rules applied to initializing the temporary the reference binds to |
| ¶10 | non-class type | one element that is not a braced list, or an empty list | that element's conversion; identity for an empty list |
| ¶11 | other | | no conversion |

Narrowing doesn't affect forming the ICS. In `f({1.0})` below, `double` → `int` is a floating-integral conversion, the ICS exists, `f` is selected, and then [[dcl.init.list]] detects the narrowing, making it ill-formed.

### Scalars and `initializer_list` (¶5, ¶10)

```cpp error
#include <initializer_list>
void f(std::initializer_list<int>);
void g(int);
void use() {
  f({});           // OK: identity
  f({'a', 'b'});   // OK: integral promotion
  f({1.0});        // error: narrowing
  g({'a'});        // OK: same as char → int, a promotion
  g({});           // OK: identity (value-initialization)
}
```

¶5 The conversion of an element to `X` may be a user-defined conversion, even in a context where an initializer-list constructor is being called. In the standard's example, `A(std::initializer_list<std::string>)` can accept `{"foo", "bar"}`, with each element converted by a constructor of `std::string`.

¶11 All other cases are no conversion, for example calling `g({1, 2})` or `g({{1}})` (the element itself is a braced list) for `void g(int)`.

### Non-aggregate classes (¶7)

¶7 When the parameter is a non-aggregate class `X` and [[over.match.list]] chooses a single best constructor `C` to initialize `X` from the list:

- ¶7.1 if `C` is not an initializer-list constructor and the list has a single element of type cv `U`, where `U` is `X` or derived from `X`: Exact Match if `U` is `X`, Conversion rank if it is derived;
- ¶7.2 otherwise: a user-defined conversion sequence whose second part is identity.

When several constructors are viable but none is best, the ICS is the ambiguous conversion sequence.

```cpp error
#include <initializer_list>
#include <string>
struct A { A(std::initializer_list<int>); };
struct B { B(int, double); };
struct C { C(std::string); };
void f(A);
void g(B);
void h(C);
void use() {
  f({'a', 'b'});   // OK: via A(initializer_list<int>)
  g({'a', 'b'});   // OK: via B(int, double)
  g({1.0, 1.0});   // error: narrowing
  h({"foo"});      // OK: via C(std::string)
}
void f(B);
void use2() {
  f({'a', 'b'});   // error: f(A) and f(B) are ambiguous
}
```

`f({'a', 'b'})` becomes ambiguous once `f(B)` is added: both sides are user-defined conversion sequences using different constructors, which can't be compared ([[over.ics.rank#3.3]]).

In `h({"foo"})`, the list to `C` is one user-defined conversion, and the element `"foo"` to `std::string` is another. List-initialization can involve more than one user-defined conversion; [[over.match.funcs#6]] explicitly excludes it from the only-one limit.

### Lists with designators (¶2) {{c++20}}

```cpp error
struct A { int x, y; };
struct B { int y, x; };
void f(A a, int);         // #1
void f(B b, ...);         // #2
void g(A a);              // #3
void g(B b);              // #4
void h() {
  f({.x = 1, .y = 2}, 0); // OK: #1
  f({.y = 2, .x = 1}, 0); // error: #1 is selected, but the designator order doesn't match A's member order
  g({.x = 1, .y = 2});    // error: #3 and #4 are ambiguous
}
```

¶2 A list with designators can only be converted to an aggregate that can be aggregate-initialized from it. Note 1 explains that viability ignores the order of the designators; if the selected function has a mismatching order, it's ill-formed only when the parameter is initialized. So both overloads of `g` are viable, both ICSs are user-defined conversions, and the call is ambiguous.

In the first two `f` calls, the first argument is viable for both overloads, and `0` matching `int` beats matching `...`, so both pick #1. The second call is then ill-formed because of the order mismatch. In our tests Clang 23 only gives a `-Wreorder-init-list` warning for it and accepts it as an extension.

### A single-element aggregate of the same class (¶3)

```cpp run ok
struct Agg { int a; int b; };
struct D : Agg {};
int f(Agg) { return 1; }
int main() {
  Agg x{1, 2};
  D d{};
  return f({x}) + f({d}) == 2 ? 0 : 1;   // {x}: identity; {d}: derived-to-base
}
```

Without ¶3, `{x}` would be read as initializing `Agg`'s first member `a` from `x`, and since `Agg` can't convert to `int`, the conversion would fail. That's exactly how it was in C++11; a later defect report added this rule and changed [[dcl.init.list]] accordingly.

### Arrays, aggregates and references (¶6, ¶8, ¶9)

```cpp ok
typedef int IA[3];
void h(const IA&);
struct A { int m1; double m2; };
void f(A);
void g(const A&);
void k(const double&);
void use() {
  h({1, 2, 3});    // OK: identity
  h({1, 2});       // OK: the third element is initialized from {}
  f({'a', 'b'});   // OK: aggregate initialization, a user-defined conversion
  g({'a', 'b'});   // OK: reference parameter; the rules apply to the underlying temporary
  k({1});          // OK: the same conversion as int → double
}
```

The parameter type in ¶6 is an array, which only occurs as the referenced type of a reference parameter, since there are no parameters of array type (footnote 99). Conversion to an array of unknown bound, and the ranking rule that prefers fewer elements, both come from C++20's [[P0388R4]]; see [[over.ics.rank#3.1]].

## Implementation view

!!! impl
    - Clang represents an ICS with `ImplicitConversionSequence`, with five kinds: standard, user-defined, ellipsis, ambiguous and bad (no conversion). `StandardConversionSequence` has three slots, `First`, `Second` and `Third`, corresponding to Lvalue Transformation, Promotion or Conversion, and Qualification Adjustment, in the same order as [over.ics.scs].
    - The checks ignored at the ICS stage, such as narrowing, bit-fields and access, are also done in two steps by the compiler: first compute ICSs and select the function, then perform the full initialization for the selected function, which is when the error is reported.

## History

!!! history
    - C++98 already had the three forms, the rank table, the one-user-defined-conversion rule and ambiguous conversion sequences.
    - C++11 added the rules for braced-list arguments and the binding restrictions for rvalue references. Later defect reports added the single-element aggregate of the same class (¶3) and the rank for a single-element same-class list for a non-aggregate class (¶7.1).
    - C++17 made `noexcept` part of the function type, adding the function pointer conversion as a Qualification Adjustment with Exact Match rank.
    - C++20 added lists with designators (¶2) and conversion to arrays of unknown bound ([[P0388R4]]).
    - C++23's explicit object parameters can be matched through a user-defined conversion (¶9 note 5).

## Common misconceptions

!!! pitfall "`int` → `long` is a promotion"
    Integral promotions only go up to `int` and `unsigned int`. `int` → `long` is an integral conversion with the same Conversion rank as `int` → `double`, so with both `f(long)` and `f(double)` present, `f(1)` is ambiguous.

!!! pitfall "Narrowing makes an overload non-viable"
    Narrowing is reported only after the function is selected. When `f(int)` receives `{1.5}`, the call is ill-formed; the compiler doesn't switch to another overload because of it, unless the other overload was better to begin with, for example `f(double)` with identity.

!!! pitfall "Passing an object of the same class by value is a user-defined conversion"
    When `f(A)` receives an `A` argument, the ICS is identity, even though the copy constructor is actually called (¶7, [over.ics.user]/4).

## Questions

!!! question "Question 1"
    With `void k(long); void k(std::string);` both present, which does each of `k(0)` and `k("x")` call?

<details markdown="1">
<summary>Answer</summary>

`k(0)`: `0` → `long` is an integral conversion, a standard conversion sequence. `0` is a null pointer constant and can also be converted to `std::string` through a constructor of `std::string`, but that's a user-defined conversion sequence. The standard conversion sequence is better, so `k(long)` is chosen.

`k("x")`: `const char[2]` can't become `long` by standard conversions (pointers don't implicitly convert to integers), so `k(long)` isn't viable and only `k(std::string)` remains.
</details>

!!! question "Question 2"
    ¶12 treats an ambiguous conversion sequence as a user-defined conversion sequence in comparisons rather than as no conversion. Give an example where the two treatments give different results.

<details markdown="1">
<summary>Answer</summary>

The `A`, `B`, `C` example in the text is one. If the ambiguity of `b → A` were treated as no conversion, `f(A)` wouldn't be viable and `f(b)` would select `f(C)`. Under the standard's treatment, `f(A)` is viable and indistinguishable from `f(C)`, so the call is ambiguous. The standard chooses an error so that the accidental existence of two conversion paths doesn't silently decide the call target.
</details>
