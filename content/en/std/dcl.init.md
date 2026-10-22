---
title: Initializers (general)
summary: "The forms an initializer can take, the definitions of zero-, default- and value-initialization, the difference between copy- and direct-initialization, and the overall procedure (paragraph 15) that decides what a given initializer actually does."
updated: 2026-10-19
---

!!! tldr
    - Initialization of parameters, return values and exception objects follows the same rules as initialization of variables; `T x = e`, argument passing and `return` are copy-initialization, while `T x(e)`, `T x{e}` and `static_cast` are direct-initialization. The main difference is that copy-initialization doesn't consider `explicit`.
    - Zero-initialization sets an object to the value of 0 converted to its type; default-initialization calls the default constructor for classes and does nothing for scalars; value-initialization zeroes first and then default-initializes when the constructor is not user-provided.
    - What an initializer does is decided, in order, by the procedure in paragraph 15: braces, references, string literals, `()`, arrays, classes, class to non-class, `nullptr` to `bool`, standard conversions.
    - Since C++17, initializing an object from a prvalue of the same type involves no temporary and needs no copy or move constructor.
    - Since C++26, reading an uninitialized automatic variable is erroneous behavior, no longer UB; `new int` still gives an indeterminate value.

## Same type, different spellings

```cpp run ok
#include <cassert>
struct P { int i; P() = default; };
int main() {
  int a = 1;        // copy-initialization
  int b(1);         // direct-initialization
  int c{1};         // direct-list-initialization
  int d = {1};      // copy-list-initialization
  P p1{};           // value-initialization: p1.i == 0
  P p2;             // default-initialization: p2.i is not initialized
  int f();          // not a variable but a function declaration
  assert(a + b + c + d == 4 && p1.i == 0);
  (void)p2;
}
```

These spellings look like matters of style, but the result can be no initialization, zeroing, a call to some constructor, or not even a variable. All of them are decided by this subclause: paragraphs 5–8 define the basic initialization actions, paragraphs 13–14 distinguish two kinds of syntactic context, and paragraph 15 gives a procedure checked in order. The branches for braces, references, character arrays and aggregates each have a subclause of their own: [[dcl.init.list]], [[dcl.init.ref]], [[dcl.init.string]], [[dcl.init.aggr]].

When variables are initialized (static initialization, dynamic initialization, block-scope static variables) is not covered here; see [[basic.start.static]], [[basic.start.dynamic]] and [[stmt.dcl]].

### Where initialization happens (¶1)

¶1 The rules of this subclause apply to all initialization, whatever syntactic position it occurs in. Initializing a parameter from an argument ([[expr.call]]), a return value by `return` ([[stmt.return]]), and an exception object by `throw` are initialization just like an initializer in a variable declaration.

So the initialization of the parameter in `f(x)` is the same thing as `T p = x;`: both are copy-initialization (see below). An `explicit` constructor can't be used for implicit argument passing for exactly the same reason it can't be used for `T p = x;`.

The grammar of initializers can be summarized as these forms:

| Form | Grammar |
|---|---|
| `T x = e;` | `= initializer-clause` |
| `T x = { … };` | `= braced-init-list` |
| `T x( … );` | `( expression-list )` |
| `T x{ … };` | *braced-init-list* |
| `T x{ .m = … };` | *designated-initializer-list* {{c++20}} |

A *braced-init-list* allows a trailing comma `{1, 2, 3,}` and can be empty `{}`. A clause can be followed by `...` to denote a pack expansion (¶17). `()` is not a valid *initializer*, so `T x();` declares a function (see item 4 of paragraph 15 below).

Note 1 adds that even where a context's grammar only allows the `=` and brace forms, such as a default member initializer in a class, which can't use parentheses, the rules of this subclause still apply.

The grammar of a designated-initializer-list is some ordinary clauses followed by some designated clauses. The leading ordinary clauses can only initialize base class subobjects ([[dcl.init.aggr#4]]); this is new wording after C++23. In C++20/23 a list had to consist entirely of designated clauses.

## The three basic actions (¶5–¶11)

The procedure in paragraph 15 ultimately comes down to the following three actions. Their names are similar, but their effects differ greatly:

| Action | When it happens | For `int` | For a class with a user-provided constructor | For a class whose constructor is not user-provided |
|---|---|---|---|---|
| Zero-initialization | The first thing done for variables with static storage duration | `0` | Members zeroed, no constructor called | Same |
| Default-initialization | No initializer written | Not initialized | Default constructor called | Implicit default constructor called; scalar members not initialized |
| Value-initialization | Empty `()` or `{}` written | `0` | Default constructor called | Zeroed first, then default constructor called |

A **user-provided** ([[g:user-provided|user-provided]]) function is one that is user-declared and not explicitly defaulted or deleted on its first declaration ([[dcl.fct.def.default]]). A constructor written `= default` inside the class is not user-provided; one written outside is.

### Zero-initialization (¶5)

```cpp run ok
#include <cassert>
struct P { int i; double d; int* p; };
P g;                // static storage duration: zero-initialized, no further initialization
int main() {
  assert(g.i == 0 && g.d == 0.0 && g.p == nullptr);
  static int s;     // also zero-initialized
  assert(s == 0);
}
```

¶5 To **zero-initialize** ([[g:zero-initialization|zero-initialize]]) an object or reference of type `T`:

- ¶5.1 {{c++26}} if `T` is `std::meta::info` (the value type of static reflection, [[P2996R13]]), it is initialized to a null reflection value. It is a scalar type, but the integer 0 doesn't convert to it, so it is listed separately.
- ¶5.2 For other scalar types, it is initialized to the value obtained by converting the integer literal `0` to `T`.
- ¶5.3 For a non-union class, padding bits are zeroed and each non-static data member and each non-virtual base class subobject is zero-initialized recursively; virtual base class subobjects are zero-initialized only if the object is not itself a base class subobject, because virtual bases are the responsibility of the most derived class alone.
- ¶5.4 For a union, padding bits are zeroed and the first named non-static data member is zero-initialized.
- ¶5.5 For an array, each element is zero-initialized.
- ¶5.6 For a reference, nothing is done.

¶5.2 speaks of the value converted from 0, not all bits zero. Pointers get the null pointer value, and floating-point values get `+0.0`. On the Itanium C++ ABI a null pointer to data member is represented as `-1`, so for a struct containing a member pointer, zero-initialization and `memset(…, 0, …)` are not equivalent.

Zero-initialization mainly occurs in two places: for variables with static and thread storage duration, before all other initialization (the note in ¶10, [[basic.start.static]]); and inside value-initialization, where it is the first step for classes and the whole story for scalars (see ¶8 below).

### Default-initialization (¶6, ¶11)

¶11 An object with no initializer is default-initialized. This sentence is where the meaning of `T x;` comes from.

¶6 To **default-initialize** ([[g:default-initialization|default-initialize]]) an object of type `T`:

- ¶6.1 For a class type, overload resolution among constructors is performed with an empty argument list ([[over.match.ctor]]), and the chosen constructor is called. If no default constructor is usable (deleted, inaccessible, ambiguous), it is ill-formed.
- ¶6.2 For an array, the semantic constraints of default-initializing a hypothetical element are checked first, then each element is default-initialized. Thanks to the hypothetical element, whether the element type can be default-constructed is checked even when there are zero elements.
- ¶6.3 {{c++26}} For `std::meta::info`, it is zero-initialized. So such a variable has a determinate null reflection value even without an initializer.
- ¶6.4 Otherwise, no initialization is performed.

¶6.4 is the zero-overhead choice: `int buf[4096];` shouldn't be forced to zero. For classes, default-initialization calls a constructor; an implicitly defined default constructor likewise does nothing for scalar members:

```cpp
struct S { int i; std::string s; };
void f() {
  S x;   // s is constructed as an empty string, x.i is not initialized
}
```

Putting ¶11, ¶6 and static initialization together:

| Declaration | Storage duration | Result |
|---|---|---|
| `int g;` at namespace scope | Static | Zero-initialized at startup, value 0 |
| `static int s;` at block scope | Static | Same as above |
| `int a;` at block scope | Automatic | Not initialized; an erroneous value since C++26 |
| `new int` | Dynamic | Not initialized; an indeterminate value |

### Uninitialized automatic variables {{c++26}}

```cpp run eb
int f() {
  int x;      // not initialized: x's bytes have an erroneous value
  return x;   // C++26: erroneous behavior; C++23 and earlier: UB
}
int main() { return f() & 0; }
```

In C++23 and earlier, reading an uninitialized local `int` was undefined behavior, and the optimizer could assume it never happens. C++26's [[P2795R5]] changed this. [[basic.indet#1]] says that as soon as storage for an object with automatic storage duration is obtained, its bytes have an **erroneous value** ([[g:erroneous-value|erroneous value]]): a value determined by the implementation independently of the program's state. Reading it is **erroneous behavior** ([[g:erroneous-behavior|erroneous behavior]]).

Erroneous behavior is still a bug in the program; the implementation may diagnose it or terminate the program. But if the implementation does neither, what is read is that erroneous value, and the compiler can no longer assume the read doesn't happen. Clang 23 gives a `-Wuninitialized` warning for the code above.

This rule has three boundaries. The bytes of objects with dynamic storage duration (`new int`) are still indeterminate, and reading them is still UB (item 1 of [[basic.indet#1]]). Variables marked with the `[[indeterminate]]` attribute ([[dcl.attr.indet]]) also revert to indeterminate values, which suits cases where you don't want the compiler to write fill values into a large buffer. If the erroneous value is not valid for the type, e.g. a `bool` bit pattern that is neither 0 nor 1, reading it is still UB (Note 1 of [[basic.indet#1]]).

### Value-initialization (¶8)

¶8 To **value-initialize** ([[g:value-initialization|value-initialize]]) an object of type `T`:

- ¶8.1 For a class type, let `C` be the constructor that default-initialization would select. If `C` is not user-provided, the whole object is first zero-initialized; then, in any case, it is default-initialized.
- ¶8.2 For an array, the constraints of a hypothetical element are checked, then each element is value-initialized.
- ¶8.3 Otherwise, it is zero-initialized.

The two steps of ¶8.1 give exactly the result people expect from `X{}`:

```cpp run ok
#include <cassert>
#include <string>
struct X {
  X() = default;     // not user-provided
  int i;
  std::string s;     // needs a constructor
};
int main() {
  X x{};             // X is not an aggregate, so {} causes value-initialization
  assert(x.i == 0);  // zeroed first, so i is 0; then the implicit default constructor constructs s
}
```

With only the default constructor call, `x.i` wouldn't be initialized; with only zeroing, `s` wouldn't be constructed. Together, everything the compiler generates is zeroed and user-written constructors are still called.

Conversely, as soon as the constructor is user-provided, even if it is `= default` outside the class, value-initialization no longer zeroes:

<div class="compare" markdown="1">

```cpp ok
struct Y { Y() = default; int i; };
int f() {
  Y y{};       // zeroed first
  return y.i;  // 0
}
```

```cpp eb
struct Y { Y(); int i; };
Y::Y() = default;  // user-provided
int f() {
  Y y{};       // not zeroed
  return y.i;  // reads an erroneous value
}
```

</div>

### const objects must have an initial value (¶7)

```cpp
struct A { int i; };
struct B { int i; B() {} };            // user-provided constructor
struct C { int i = 0; };
struct D { int i; D() = default; };    // = default in the class: not user-provided
struct F { };
union  U { int a; int b = 0; };

const A ca;      // error: A is not const-default-constructible
const B cb;      // OK: ¶7.3, although cb.i is still uninitialized
const C cc;      // OK: ¶7.4.1
const D cd;      // error
const F cf;      // OK: no members, so all the conditions of ¶7.4 hold
const U cu;      // OK: ¶7.4.2
const int ci;    // error
```

A const object can't be assigned afterwards. If default-initialization left members uninitialized, they would never have determinate values, which is almost certainly a bug. So ¶7 says that when an object of const-qualified type `T` is default-initialized, `T` must be **const-default-constructible**, i.e. satisfy one of:

- ¶7.1 `T` is `std::meta::info`; ¶7.2 `T` is `std::nullptr_t`;
- ¶7.3 default-initializing `T` would invoke a user-provided constructor of `T` that is not inherited from a base class;
- ¶7.4 `T` is a class, and each direct non-variant non-static data member has a default member initializer or is itself const-default-constructible (¶7.4.1); if it is a union with members, exactly one variant member has a default member initializer (¶7.4.2); if it is not a union, each anonymous union member is const-default-constructible (¶7.4.3); and each potentially constructed base class is also const-default-constructible (¶7.4.4);
- ¶7.5 `T` is an array whose element type is const-default-constructible.

¶7.3 only looks at form: `B` has a user-provided constructor that does nothing, and `const B cb;` passes. ¶7.4 is the resolution of [[CWG253]]; before it, the rule only accepted user-provided default constructors, and even `struct F {}; const F cf;` was rejected.

### References can't be default- or value-initialized (¶9)

¶9 A program that calls for default-initialization or value-initialization of a reference is ill-formed. An example is a reference member of an aggregate that isn't given an initializer and has no default member initializer ([[dcl.init.aggr#6]]). A reference declaration without an initializer, like `int& r;`, is separately forbidden by [[dcl.init.ref#1]].

## Copy-initialization and direct-initialization (¶13–¶14)

```cpp
struct E { explicit E(int); };
E e1 = 1;                   // error: copy-initialization doesn't consider explicit constructors
E e2(1);                    // OK: direct-initialization
E e3{1};                    // OK: direct-list-initialization
E e4 = {1};                 // error: copy-list-initialization selected an explicit constructor
E e5 = static_cast<E>(1);   // OK: static_cast is direct-initialization
void take(E);
void g() { take(1); }       // error: argument passing is copy-initialization
```

Initialization comes in two kinds, distinguished only by syntactic context, regardless of whether a copy actually takes place.

¶13 Initialization in the following contexts is **copy-initialization** ([[g:copy-initialization|copy-initialization]]):

| Context | Example |
|---|---|
| Initializer of the `=` form | `T x = e;`, `T x = {a, b};` |
| Condition of the `=` form | `if (T x = e)` |
| Argument passing | `f(e)` initializes the parameter |
| Return | `return e;` initializes the returned object |
| Throwing an exception | `throw e;` initializes the exception object ([[except.throw]]) |
| Handling an exception | `catch (T x)` initializes `x` from the exception object ([[except.handle]]) |
| Aggregate members, non-designated | The members in `S s{e};` and `S s(e);` are initialized from `e` |

Note 5 reminds us that copy-initialization may invoke a move constructor ([[class.copy.ctor]]); "copy" in the name is a historical term.

¶14 Initialization in the following contexts is **direct-initialization** ([[g:direct-initialization|direct-initialization]]):

- ¶14.1 Initializers in parenthesized or braced form: `T x(a, b);`, `T x{a};`, member initializers `: m(a)`;
- ¶14.2 *new-initializer*s: `new T(a)`, `new T{a}`;
- ¶14.3 `static_cast<T>(e)`;
- ¶14.4 functional-notation type conversions: `T(e)`, `T{e}`;
- ¶14.5 conditions of the braced form: `if (T x{e})`.

The practical differences come down to three points:

1. `explicit` constructors and `explicit` conversion functions are candidates only in direct-initialization ([[over.match.ctor]], [[over.match.copy]], [[over.match.conv]]).
2. When copy-initializing a class object from an unrelated type, the user-defined conversion of item 6.3 of paragraph 15 applies rather than the constructor overload resolution of item 6.2, and the candidate sets differ (see below).
3. `nullptr` to `bool` is allowed only in direct-initialization (item 8 of paragraph 15).

`e1` and `e4` fail for different reasons. In `E e1 = 1;`, the explicit constructor isn't a candidate at all, so no conversion is found. In `E e4 = {1};`, it is a candidate and is selected, and the program is ill-formed because copy-list-initialization selected an explicit constructor ([[over.match.list]]). Even if there were a non-explicit constructor that matched worse, the compiler wouldn't fall back to it.

The form of a designated initializer determines which kind it is: `.m = e` is copy-initialization, `.m{e}` is direct-list-initialization (Note 3 in [[dcl.init.aggr#5]]).

## The overall procedure (¶15)

¶15 first defines two terms. The **destination type** is the type of the object or reference being initialized, with top-level cv-qualifiers removed. The **source type** is the type of the initializer expression; when the initializer is not a single (possibly parenthesized) expression, such as `(a, b)` or a braced list, the source type is not defined.

Then the following are checked in order, and the first branch that applies determines the result:

```text
15.1  initializer is {…} or = {…}                     → list-initialization [dcl.init.list]
15.2  destination type is a reference                 → reference binding [dcl.init.ref]
15.3  destination is a char array, initializer is a string literal → [dcl.init.string]
15.4  initializer is ()                               → value-initialization
15.5  destination is an array, initializer is (x1, …, xk) → copy-initialize elements in turn, value-initialize the rest   C++20
15.6  destination is a class type
  .1  initializer is a prvalue of the same type        → initialize the destination with it directly          C++17
  .2  direct-init, or copy-init from same/derived class → constructor overload resolution
      .2.1 succeeds                                   → call the constructor
      .2.2 no viable constructor, aggregate, (…) form  → parenthesized aggregate initialization              C++20
      .2.3 otherwise                                  → ill-formed
  .3  remaining copy-initialization                   → user-defined conversion [over.match.copy]
15.7  source type is a class type (destination isn't) → conversion function [over.match.conv]
15.8  direct-initialization, nullptr_t → bool          → false
15.9  otherwise                                       → standard conversion sequence
```

A minimal example for each branch:

| Branch | Example | Result |
|---|---|---|
| 15.1 | `std::vector<int> v{1, 2};` | List-initialization, calls the `initializer_list` constructor |
| 15.2 | `const int& r = 1;` | The reference binds to a materialized temporary |
| 15.3 | `char s[] = "hi";` | `s` is `char[3]` |
| 15.4 | `new int()`, `T()`, `: m()` | Value-initialization |
| 15.5 | `int a[](1, 2, 3);` | `int[3]` |
| 15.6.1 | `T x = T(T(T()));` | There is only one object, and it is value-initialized |
| 15.6.2 | `std::string s("abc");` | Calls `string(const char*)` |
| 15.6.2.2 | `struct P { int a, b; }; P p(1, 2);` | Parenthesized aggregate initialization |
| 15.6.3 | `std::string s = "abc";` | A converting constructor produces a prvalue, which then initializes `s` |
| 15.7 | `struct Q { operator int(); } q; int n = q;` | Calls `Q::operator int` |
| 15.8 | `bool b(nullptr);` | `b == false` |
| 15.9 | `double d = 1;` | Standard integral-to-floating conversion |

### Items 1–3: handed off to subclauses

Item 1: if the initializer is a braced list without outer parentheses, i.e. `T x{…}` or `T x = {…}`, it is handed to [[dcl.init.list]] regardless of whether `T` is a reference, scalar or class. So list-initialization takes priority over all the later rules about references, arrays and classes. `T x({1, 2})` is the parenthesized form whose single expression happens to be a braced list; it doesn't take this item but reaches item 6.2, passing `{1, 2}` as a constructor argument.

Item 2: if the destination is a reference, it is handed to [[dcl.init.ref]]. Item 3: if the destination is an array of `char`, `char8_t`, `char16_t`, `char32_t` or `wchar_t` and the initializer is a string literal, it is handed to [[dcl.init.string]].

### Item 4: `()` means value-initialization

```cpp run ok
#include <cassert>
struct M { int v; M() : v() {} };   // () in a member initializer: v == 0
int main() {
  int* p = new int();               // () in new: *p == 0
  int i = int();                    // functional conversion T(): i == 0
  M m;
  assert(*p == 0 && i == 0 && m.v == 0);
  delete p;
}
```

If the initializer is `()`, the object is value-initialized. But Note 6 points out that the grammar of *initializer* doesn't allow `()`, so `X a();` is not an object declaration; it declares a function with no parameters returning `X`. `()` only appears in `new`, functional conversions and member initializers.

This is the simplest form of the **most vexing parse** ([[g:most-vexing-parse|most vexing parse]]). More complex forms like `T x(U());` are also parsed as function declarations, with a parameter that is a function returning `U`; the reason is that [[dcl.ambig.res]] says whatever can be parsed as a declaration is a declaration. C++11's `T x{};` avoids this ambiguity. Clang 23 gives a `-Wvexing-parse` warning for `T x();` (empty parentheses interpreted as a function declaration).

### Item 5: parenthesized initialization of arrays {{c++20}}

```cpp run ok
int a[](1, 2, 3);   // int[3]
int b[5](1, 2);     // {1, 2, 0, 0, 0}
static_assert(sizeof a == 3 * sizeof(int));
int main() { return b[4]; }
```

When the destination is an array, braces, string literals and `()` have all been handled earlier, so the remaining initializer must have the form `(x1, …, xk)`; a single expression as in `T a[3] = x;` is ill-formed.

An array of unknown bound is defined as having k elements. If k exceeds the array length, it is ill-formed. The i-th element is copy-initialized from xi, and the remaining elements are value-initialized. The elements are initialized strictly left to right.

This item and item 6.2.2 both come from [[P0960R3]]; the motivation was to let generic code that internally writes `T(std::forward<Args>(args)...)`, such as `std::make_unique<T>(args...)` and `emplace_back(args...)`, work for aggregates and arrays too.

### Item 6.1: a prvalue of the same type

```cpp run ok
struct NoMove {
  NoMove(int) {}
  NoMove(const NoMove&) = delete;
  NoMove(NoMove&&) = delete;
};
NoMove make() { return NoMove(1); }    // OK: the prvalue initializes the returned object directly
NoMove a = NoMove(NoMove(NoMove(1)));  // OK: constructed only once
NoMove b = make();                     // OK
int main() {}
```

If the initializer expression is a prvalue and its type, ignoring cv, is the same as the destination type, the destination object is initialized directly by that expression.

This is the core of C++17's [[P0135R1]] (guaranteed copy elision): a prvalue no longer denotes a temporary object but a way of initializing some object, called its **result object**, which is determined by the context ([[basic.lval]]). In C++14, all three places above required an accessible copy or move constructor even though implementations would elide the copy, so they were all ill-formed.

This item doesn't distinguish direct- from copy-initialization and doesn't look at constructors at all. So since C++17 you can write `auto g = std::lock_guard<std::mutex>(m);`, and a function can return by value a type like `std::lock_guard` that can be neither copied nor moved.

### Item 6.2: constructor overload resolution

If it is direct-initialization, or copy-initialization where the source type (ignoring cv) is the same as or derived from the destination type, constructors are considered: candidates are listed per [[over.match.ctor]], including explicit constructors for direct-initialization, and overload resolution is performed.

- Item 6.2.1: if resolution succeeds, the selected constructor is called with the initializer expression or expression list as arguments.
- Item 6.2.2 {{c++20}}: if there is no viable constructor, the destination is an aggregate class, and the initializer is a parenthesized expression list, parenthesized aggregate initialization is performed.
- Item 6.2.3: otherwise, it is ill-formed.

The condition that the source type is derived from the destination type sends slicing copies like `Base b = derived;` through constructors, calling `Base`'s copy or move constructor.

Aggregates also have implicit copy and move constructors, so `P p(other_p);` still calls the copy constructor; parenthesized aggregate initialization only gets its turn when the arguments match no constructor.

### Parenthesized aggregate initialization (item 6.2.2) {{c++20}}

Let the aggregate's elements be e1…en ([[dcl.init.aggr#2]]) and the expressions x1…xk. If k is greater than n, it is ill-formed. ei is copy-initialized from xi, and the remaining elements are initialized from their default member initializers or, lacking those, value-initialized. The elements are initialized strictly left to right.

Note 7 lists four differences from the braced form; here is Example 3 from the standard:

```cpp
struct A {
  int a;
  int&& r;
};
int f();
int n = 10;

A a1{1, f()};               // OK: the temporary's lifetime is extended
A a2(1, f());               // well-formed, but a2.r dangles
A a3{1.0, 1};               // error: narrowing
A a4(1.0, 1);               // well-formed (narrowing allowed), but a4.r dangles
A a5(1.0, std::move(n));    // OK
```

| | `T{…}` | `T(…)` for an aggregate |
|---|---|---|
| Narrowing conversions | Forbidden | Allowed |
| Designated initializers | Allowed | Not allowed |
| Temporaries bound to reference members | Lifetime extended | Not extended ([[class.temporary#6]]) |
| Brace elision | Yes | No |

These differences are intentional: when `T(args...)` is used for an aggregate, it behaves like calling a constructor that takes the members as parameters in order. Constructor parameters allow narrowing; temporaries bound to a constructor's reference parameters are destroyed at the end of the full-expression; and constructor calls have no brace elision. This way, turning an aggregate into a class with constructors, or vice versa, changes the meaning of `T(args...)` as little as possible.

```cpp
struct In { int i, j; };
struct O { In in; int k; };
O o1{1, 2, 3};      // OK: brace elision, o1.in = {1, 2}
O o2({1, 2}, 3);    // OK: the first element is copy-initialized from {1, 2}
O o3(1, 2, 3);      // error: no brace elision, and int can't convert to In
```

### Item 6.3: user-defined conversions in copy-initialization

What remains is copy-initialization where the source type is unrelated to the destination type. The user-defined conversions that can convert the source type to the destination type are listed per [[over.match.copy]]: the non-explicit converting constructors of the destination class, and the non-explicit conversion functions of the source type (which may return a class derived from the destination type); the best one is then selected.

If a constructor is selected, the call is a prvalue of the destination type whose result object is the object being initialized. If a conversion function is selected, its return value is used to direct-initialize the destination object by the rules above.

```cpp
#include <string>
std::string s1 = "abc";   // the prvalue from string(const char*) becomes s1 directly
struct Base {}; struct Der : Base {};
struct From { operator Der() const; };
Base b = From();          // the conversion function returns Der, which then direct-initializes b:
                          // item 6.2, calling Base's move constructor (slicing)
```

Compared with item 6.2, only one user-defined conversion is allowed here, and it is chosen among all conversions that can reach the destination type, not just among the destination type's constructors:

<div class="compare" markdown="1">

```cpp ok
struct A { A(int); };
struct B { B(A); };
B b1(1);
// direct-initialization: calls B(A),
// with argument 1 converted via A(int)
```

```cpp error
struct A { A(int); };
struct B { B(A); };
B b2 = 1;
// needs int→A→B:
// two user-defined conversions
```

</div>

Before C++17, the result of this item was a temporary object, which was then used to copy- or move-construct the destination; even if that copy was elided, the copy or move constructor had to be accessible.

### Item 7: from class type to non-class type

```cpp
struct Q { explicit operator int() const; };
Q q;
int a(q);        // OK: direct-initialization considers explicit conversion functions
int b = q;       // error: copy-initialization doesn't
int c = int(q);  // OK: a functional conversion is direct-initialization
bool d = q;      // error: explicit operator int is not a candidate
```

If the destination is not a class type and the source type is a class type, conversion functions are listed per [[over.match.conv]] and overload resolution is performed. In direct-initialization, explicit conversion functions are also candidates.

`explicit operator bool` works in `if (q)` because a condition is contextually converted to `bool`, and that conversion is defined as the direct-initialization `bool t(e);` ([[conv]]).

### Item 8: direct-initializing `bool` with `nullptr`

```cpp
bool b1(nullptr);    // OK: false
bool b2{nullptr};    // OK: direct-list-initialization, which also ends up at item 8
bool b3 = nullptr;   // error
```

If it is direct-initialization, the source type is `std::nullptr_t` and the destination is `bool`, the result is `false`. Copy-initialization can't reach this item and falls through to item 9, and the boolean conversions of [[conv.bool]] only cover arithmetic, unscoped enumeration, pointer and pointer-to-member types, not `std::nullptr_t`, so `b3` is ill-formed.

With this design, `bool(x)` works in generic code for any pointer-like type, while an implicit null test of the `nullptr` literal doesn't happen silently. Clang 23 gives `-Wnull-conversion` warnings for `b1` and `b2`.

### Item 9: standard conversions

Otherwise, neither the source nor the destination is a class type. The initializer expression is converted to a prvalue of the destination type using a standard conversion sequence ([[conv]]), without considering user-defined conversions; if it can't be converted, it is ill-formed.

Initializing a bit-field with a value it can't represent gives an implementation-defined result {{impl}}. Conversions of ordinary integers are defined modulo since C++20 ([[conv.integral]]), but the width of a bit-field is not part of its type, so it is specified separately. Note 8 reminds us that cv-qualification doesn't affect initialization: `const int b = a; int c = b;` are both fine.

## Expressions in parentheses (¶12, ¶19)

¶12 If the entity being initialized is neither a class nor an array, the parentheses can contain only one expression:

```cpp
int x(1, 2);     // error: a parenthesized initializer for a scalar can have only one expression
int y((1, 2));   // OK: the inner parentheses form a comma expression, y == 2
```

The comma in `int x(1, 2)` separates an expression list; it is not the comma operator. Arrays are excluded because since C++20 arrays can be initialized with parentheses (item 5 of paragraph 15).

¶19 If the destination type is not an aggregate and the initializer is a parenthesized expression list, the expressions are evaluated as function arguments are, **indeterminately sequenced** ([[g:indeterminately-sequenced|indeterminately sequenced]], [[expr.call]]) with respect to each other. The clauses of a braced list, by contrast, are evaluated strictly left to right ([[dcl.init.list#4]]), and parenthesized aggregate initialization is also left to right.

```cpp run unspecified
#include <cstdio>
struct I { I(int x) { std::printf("%d", x); } };
struct S { S(I, I) {} };
int main() {
  S(I(1), I(2)); std::puts("");   // prints 12 or 21, unspecified
  S{I(1), I(2)}; std::puts("");   // always prints 12
}
```

## Other rules (¶2, ¶16–¶18, ¶20–¶22)

¶2 Except for `constexpr` variables (which require a constant expression, see [[dcl.constexpr]]), the initializer of a variable can be any expression, regardless of storage duration. C requires initializers of objects with static storage duration to be constant expressions; C++ allows `int b = f(a);` at namespace scope. The price is dynamic initialization and the resulting initialization order problem ([[g:static-initialization-order-fiasco|static initialization order fiasco]]); see [[basic.start.dynamic]].

¶16 {{c++20}} An **immediate invocation** (a call to a `consteval` function, [[expr.const.imm]]) in a default argument or default member initializer is not evaluated where it appears; it is evaluated at the function call, constructor definition or aggregate initialization that uses the initializer, and is checked there for being a constant expression.

¶17 A clause followed by `...` is a pack expansion ([[temp.variadic]]), as in `int arr[]{args...};`.

¶18 Initialization includes the evaluation of all subexpressions of the initializer (including those nested in braces) and the creation of temporaries for function arguments or return values. This sentence delimits what counts as the initialization; for example, [[stmt.dcl]] says that if the initialization of a static local variable exits by an exception, it is retried next time, and the exception can come from any subexpression of the initializer.

¶20 The same name can't appear twice in one designated-initializer-list: `A a{.x = 1, .x = 2};` is ill-formed. C lets the later one override the earlier; C++ doesn't, because each member is initialized only once. Clang 23 in C++ mode only gives a `-Winitializer-overrides` warning for this and reports an error only with `-pedantic-errors`; by the standard it is ill-formed.

¶21 defines **deemed construction**: when an object's initialization completes, it is deemed constructed, even if it is not of class type or no constructor was called. For the purposes of [[basic.start.term]], if the initialization is a full-expression, the object is deemed constructed when that full-expression's evaluation completes. Objects with static storage duration are destroyed in reverse order of construction completion, and only constructed objects are destroyed ([[stmt.dcl#4]]), which requires saying when objects like `int`s and aggregates count as constructed. The second half of ¶21 says: destroying a class object calls its destructor; destroying a scalar has no effect other than ending its lifetime; destroying an array destroys its elements in reverse subscript order.

¶22 The declaration that specifies how a variable is initialized (through an initializer, or through default-initialization) is the variable's **initializing declaration** ([[g:initializing-declaration|initializing declaration]]). Note 10 points out that it is usually the definition; but the initializing declaration of a non-inline static data member can be the in-class declaration, with the definition outside the class:

```cpp
struct S {
  static const int n = 42;   // initializing declaration, not a definition
};
const int S::n;              // definition, with no initializer
```

[[expr.const]] uses this term to specify from where a variable can be used in constant expressions.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

The note in ¶3: default arguments are more restricted; see [[dcl.fct.default]].

The note in ¶4: the order of initialization of variables with static storage duration is in [[basic.start]] and [[stmt.dcl]].

The note in ¶10: every object with static storage duration is statically initialized at program startup, before any other initialization ([[basic.start.static]]); some objects then also undergo dynamic initialization.

</details>

## Implementation notes

!!! impl
    - Objects with static storage duration that only need zero-initialization go into the `.bss` section, zeroed by the loader and taking no space in the executable; constant-initialized objects go into `.data` or `.rodata`; only objects needing dynamic initialization get initialization code (registered in `.init_array` on ELF).
    - Zero-initialization isn't necessarily all-zero bits. In the Itanium ABI a null pointer to data member is `-1`, so zero-initializing a struct containing a member pointer requires the compiler to write a nonzero value, and such objects can't go into `.bss` either.
    - `X x{};` (with `X() = default`) usually compiles to a zeroing plus an (often empty) constructor call; `Y y{};` (with a user-provided constructor) is just the constructor call.

## History

!!! history
    - C++98 had only zero-initialization and default-initialization. Back then, default-initialization called the default constructor for non-POD classes and zero-initialized POD types, while POD objects without an initializer were not initialized. So `T()` zeroed a POD but did not zero the scalar members of a class with non-trivial members.
    - C++03 introduced value-initialization: `T()` zeroes first for classes without a user-declared constructor, fixing the problem above.
    - C++11 added list-initialization ([[dcl.init.list]]), introduced the notion of user-provided and `= default`, and value-initialization was rewritten in those terms.
    - C++17's [[P0135R1]] guaranteed copy elision, giving item 6.1 of paragraph 15, and the result of the conversion in item 6.3 also initializes the destination directly; the resolution of [[CWG253]] relaxed the rule for const objects to const-default-constructible.
    - C++20's [[P0960R3]] added parenthesized initialization of arrays and aggregates; designated initializers were also added.
    - C++26's [[P2795R5]] changed reading uninitialized automatic variables from UB to erroneous behavior; [[P2996R13]] added the zero- and default-initialization rules for `std::meta::info`.

## Common misconceptions

!!! pitfall "`T x();` declares an object"
    It declares a function. After `std::mutex m();`, writing `std::lock_guard g(m);` produces an error far from the real cause. Write `T x;` or `T x{};`.

!!! pitfall "`= default` inside or outside the class makes no difference"
    `struct Y { Y(); int i; }; Y::Y() = default;` makes the constructor user-provided, and `Y{}` no longer zeroes `i`. Put `= default` in the class, or give the member a default member initializer `int i = 0;`; the latter is the most robust.

!!! pitfall "`std::make_unique<A>(1, f())` is the same as `A{1, f()}`"
    `make_unique` uses parenthesized initialization internally. If `A` is an aggregate with a reference member, the parenthesized form doesn't extend the temporary's lifetime, and the reference member dangles immediately.

## Questions

!!! question "Question 1"
    What values do the members of these three automatic variables have?
    ```cpp
    struct A { int i; A() = default; };
    struct B { int i; B(); }; B::B() = default;
    struct C { A a; int j; C() {} };
    A a1{}; B b1{}; C c1{};
    ```

<details markdown="1">
<summary>Answer</summary>

`A` has a user-declared constructor, so since C++20 it is not an aggregate. `A a1{}` is value-initialized per item 5 of [[dcl.init.list#3]]; the default constructor is not user-provided, so it zeroes first, and `a1.i == 0`.

`B::B()` is user-provided, so value-initializing `B b1{}` doesn't zero, and `b1.i` is not initialized; in C++26 it has an erroneous value.

`C()` is user-provided, so `C c1{}` doesn't zero and just calls `C()`. Its member initializer list doesn't mention `a` or `j`, so both are default-initialized ([[class.base.init]]): `a` calls `A`'s implicit default constructor, `a.i` is not initialized, and neither is `j`. The outer value-initialization doesn't reach into a user-written constructor.
</details>

!!! question "Question 2"
    Why is `bool b = nullptr;` ill-formed while `bool b{nullptr};` is well-formed?

<details markdown="1">
<summary>Answer</summary>

`bool b = nullptr;` is copy-initialization, which can't reach item 8 of paragraph 15 and falls to item 9, requiring a standard conversion from `std::nullptr_t` to `bool`, and [[conv.bool]] doesn't include `nullptr_t`.

`bool b{nullptr};` is direct-list-initialization: item 1 hands it to item 9 of [[dcl.init.list#3]] (a single-element list), which initializes from that element by direct-initialization; back in paragraph 15, item 8 applies and the result is `false`. It isn't narrowing either: item 5 of [[dcl.init.list#7]] only lists conversions from pointers and pointers to members to `bool` as narrowing.
</details>

!!! question "Question 3"
    For `struct NoMove { NoMove(int); NoMove(NoMove&&) = delete; };`, what happens with `NoMove x = 1;` in C++14 and in C++17?

<details markdown="1">
<summary>Answer</summary>

Both go through item 6.3 of paragraph 15: copy-initialization from a source type `int` unrelated to the destination, selecting the converting constructor `NoMove(int)`.

In C++14, the result of the conversion is a temporary object, which then direct-initializes `x`; that needs the move constructor, which is deleted, so it is ill-formed. In C++17, the constructor call is a prvalue whose result object is `x`, no move constructor is needed, and so it is well-formed.
</details>
