---
title: Every form of initialization
summary: Which kind of initialization each initialization syntax performs for each category of type, what value the object gets, when it is initialized, and the most common pitfalls.
tags: initialization, topic
updated: 2026-10-19
---

!!! tldr
    - To work out what an initialization does, look at three things in order: the syntactic form of the initializer, the type being initialized, and the object's storage duration.
    - Every initialization ends up as one of four actions: zero-initialization, default-initialization, value-initialization, list-initialization.
    - `T x{}` zeroes first only if the default constructor is not user-provided; for a class with a hand-written `S() {}`, `S{}` does not zero the members.
    - Braces forbid narrowing and prefer `std::initializer_list` constructors: `std::vector<int>{10, 1}` has two elements.
    - Objects with static storage duration are always zero-initialized first. An automatic scalar without an initializer gets an erroneous value since C++26 (reading it is erroneous behavior); before that, reading it was UB.

## Three questions to place an initialization

```cpp
int a;        // automatic variable: not initialized
int b{};      // 0
int c();      // not a variable but a function declaration
static int d; // 0
```

The four lines look alike, but the results all differ. Any initialization can be placed by three questions:

1. **What is the syntactic form?** Forms with `=` (`T x = v;`, `T x = {v};`), as well as argument passing and return values, are [[g:copy-initialization|copy-initialization]]; `T x(v)`, `T x{v}`, `new T(v)`, `static_cast` and the like without `=` are [[g:direct-initialization|direct-initialization]] ([[dcl.init#13]], [[dcl.init#14]]). When the initializer is braced, it is also [[g:list-initialization|list-initialization]].
2. **What type is being initialized?** Scalars, [[g:aggregate|aggregates]], classes with constructors, references and arrays each take their own branch ([[dcl.init#15]], [[dcl.init.list#3]]). An aggregate is an array, or a class with no user-declared constructors, no private or protected direct data members, and no virtual functions or virtual base classes.
3. **What is the object's storage duration?** Objects with static or thread storage duration complete static initialization before any dynamic initialization: constant initialization if possible, otherwise zero-initialization ([[basic.start.static]]). Objects with automatic and dynamic storage duration have no such safety net ([[basic.indet]]).

## The four basic actions

| Action | For `int` | For classes | Typical trigger |
|---|---|---|---|
| [[g:zero-initialization\|Zero-initialization]] ([[dcl.init#5]]) | `0` | Every member and base is zero-initialized, padding bits are zeroed, no constructor is called | First step for objects with static storage duration; first step of value-initialization |
| [[g:default-initialization\|Default-initialization]] ([[dcl.init#6]]) | Does nothing | Calls the default constructor | `T x;`, `new T`, members not mentioned by the constructor |
| [[g:value-initialization\|Value-initialization]] ([[dcl.init#8]]) | `0` | If the selected default constructor is not user-provided: zero-initialize, then default-initialize; otherwise only default-initialize | `T()`, `T{}` (non-aggregate), `new T()`, `: m()` |
| List-initialization ([[dcl.init.list]]) | Initialized from the single element; narrowing forbidden | Aggregate: aggregate initialization; otherwise a constructor is selected, `initializer_list` constructors first | Every `{…}` |

The fork in value-initialization for classes is the most error-prone. A constructor is [[g:user-provided|user-provided]] if it is user-declared and not explicitly defaulted or deleted on its first declaration. So:

<div class="compare" markdown="1">

```cpp
struct A { A() = default; int i; };
A a{};   // a.i == 0
// = default in the class: not user-provided
// value-initialization zeroes first
```

```cpp
struct S { S() {} int i; };
S s{};   // s.i is not initialized
// user-provided constructor:
// value-initialization only calls S()
```

</div>

## Syntax × type

The table below uses these types to represent each category:

```cpp
#include <initializer_list>
#include <string>
struct Agg { int a; std::string s; };                 // aggregate
struct Usr { Usr() {} Usr(int) {} int i; };           // user-provided default constructor, doesn't initialize i
struct Dft { Dft() = default; Dft(int) {} int i; };   // non-aggregate, default constructor not user-provided
struct IL  { IL(std::initializer_list<int>) {} IL(int, int) {} };
```

`v` stands for a value of a suitable type. By default the table describes automatic variables at block scope. "Uninitialized" in the table means, in C++26, that the object holds an [[g:erroneous-value|erroneous value]] and reading it is erroneous behavior (an operation the standard deems incorrect but whose behavior is defined, and which implementations may diagnose); in C++23 and earlier reading it is UB.

| Syntax | `int` | `Agg` | `Usr` | `Dft` | `int[3]` | Reference |
|---|---|---|---|---|---|---|
| `T x;` | Uninitialized | `a` uninitialized, `s` empty | Calls `Usr()`, `i` uninitialized | `i` uninitialized | All 3 uninitialized | Ill-formed |
| `T x{};` | `0` | Aggregate initialization: `a = 0`, `s` empty | Value-initialization, only calls `Usr()`, `i` uninitialized | Value-initialization, zeroes first, `i = 0` | `{0, 0, 0}` | `int&` ill-formed; `const int&` binds to a temporary `0` |
| `T x();` | Function declaration | Function declaration | Function declaration | Function declaration | — | — |
| `T x = v;` | `v` after conversion | Copy if `v` is an `Agg` | Via `Usr(int)` if `v` is an `int` | Same as left | Ill-formed (except character arrays initialized from a string literal) | Binds; see [[dcl.init.ref]] |
| `T x(v);` | `v` | If `v` isn't an `Agg`, parenthesized aggregate initialization, `a = v` (C++20) | `Usr(v)` | `Dft(v)` | `{v, 0, 0}` (C++20) | Binds |
| `T x{v};` | `v`, narrowing forbidden | Aggregate initialization `a = v` | `Usr(v)`, narrowing forbidden | `Dft(v)` | `{v, 0, 0}` | Binds |
| `T x = {v};` | Same as `{v}` | Same as `{v}` | Same as `{v}`, but ill-formed if an explicit constructor is selected | Same as left | Same as `{v}` | Same as `{v}` |
| `T x(a, b);` | Ill-formed | Parenthesized aggregate initialization (C++20) | Constructor | Constructor | `{a, b, 0}` (C++20) | Ill-formed |
| `new T` | Indeterminate value; reading it is UB | Same as `T x;` | Same as `T x;` | Same as `T x;` | Same as `T x;` | — |
| `new T()`, `new T{}` | `0` | `a = 0`, `s` empty | `Usr()`, `i` uninitialized | `i = 0` | All 0 | — |
| Expression `T()`, `T{}` | `0` | `a = 0`, `s` empty | `Usr()`, `i` uninitialized | `i = 0` | — | — |
| Member: not mentioned by the constructor, no default member initializer | Uninitialized | Default-initialized | `Usr()` | `i` uninitialized | Uninitialized | Ill-formed |
| Member: `: m()` | `0` | Value-initialized | `Usr()` | `i = 0` | All 0 | Ill-formed |
| `static T x;` | `0` | `a = 0`, `s` empty | Zero-initialized first, then `Usr()` is called, `i = 0` | `i = 0` | All 0 | Ill-formed |

The `new T` row differs from `T x;`: the erroneous value rules don't apply to objects with dynamic storage duration, so after default-initialization they have an [[g:indeterminate-value|indeterminate value]], and reading it is UB in every version ([[basic.indet]]).

For a class with an `initializer_list` constructor, braces change meaning:

| Syntax | Constructor selected | Reason |
|---|---|---|
| `IL x{1, 2};` | `IL(initializer_list<int>)` | For a non-empty list only `initializer_list` constructors are considered first ([[over.match.list]]) |
| `IL x(1, 2);` | `IL(int, int)` | Not list-initialization |
| `IL x{};` | `IL(initializer_list<int>)`, empty list | `IL` has no default constructor, so it doesn't go to value-initialization ([[dcl.init.list#3.5]]), and the first phase still considers only `initializer_list` constructors |
| `IL x{1.5, 2};` | Ill-formed | The first phase selects the `initializer_list` constructor, then finds that `1.5` to `int` is narrowing; it does not fall back to `IL(int, int)` |

A [[g:narrowing-conversion|narrowing conversion]] is an implicit conversion that may lose information, such as floating point to integer, `long` to `int` (when the value doesn't fit), or pointer to `bool`. The full definition is in [[dcl.init.list#7]].

## The decision process

The two tables above can be boiled down to one process. Braced initialization is decided in the order of [[dcl.init.list#3]], the other forms by [[dcl.init#15]]:

```text
Is the initializer {…}?
├─ Yes → list-initialization [dcl.init.list]
│     ├─ Designators?                       → aggregate initialization (designators in declaration order)
│     ├─ Aggregate class + single element of same or derived class? → copy from that element
│     ├─ Character array + string literal?   → [dcl.init.string]
│     ├─ Aggregate?                          → aggregate initialization
│     ├─ Empty list + class with default constructor? → value-initialization
│     ├─ Class?                              → initializer_list constructors first, then other constructors; narrowing is an error
│     ├─ Enum with fixed underlying type + single-element direct-init? → convert to that enum
│     ├─ Single element (and not a reference needing a temporary)? → initialize from that element; narrowing is an error
│     ├─ Reference?                          → create a temporary (copy-list-initialization), then bind
│     └─ Empty list?                         → value-initialization
└─ No → [dcl.init]/15
      ├─ Reference?                          → [dcl.init.ref]
      ├─ Character array + string literal?   → [dcl.init.string]
      ├─ Initializer is ()?                  → value-initialization (but the declaration T x(); is a function declaration)
      ├─ Array?                              → (x1,…,xk): copy-initialize each, value-initialize the rest (C++20)
      ├─ Class?
      │    ├─ prvalue of the same type?      → initialize directly from it (guaranteed copy elision)
      │    ├─ Direct-init, or source of same/derived class? → select a constructor; if none viable and it's an aggregate → parenthesized aggregate initialization
      │    └─ Other copy-initialization?     → one user-defined conversion (explicit not considered)
      ├─ Source is a class?                  → conversion function
      └─ Otherwise                           → standard conversions
```

## When initialization happens

| Object | When | Clause |
|---|---|---|
| Namespace-scope variables, static data members, static local variables | Static initialization first at program start (constant initialization, otherwise zero-initialization) | [[basic.start.static]] |
| Dynamic initialization of namespace-scope variables | Before `main`, or deferred until before the first odr-use; in definition order within a translation unit, unspecified order across translation units | [[basic.start.dynamic]] |
| Dynamic initialization of static local variables | The first time control passes through the declaration; only once even with multiple threads; if it throws, it is retried next time | [[stmt.dcl]] |
| Automatic variables | Each time control passes through the declaration | [[stmt.dcl]] |
| Bases and members | Before the constructor body, in declaration order, not in the written order of the *mem-initializers* | [[class.base.init]] |
| Objects created by `new` | When the *new-expression* is evaluated | [[expr.new]] |

The order of dynamic initialization across translation units is unspecified, so when the initializer of one global object uses a global object from another file, it may read a value that hasn't been initialized yet. `constinit` ([[dcl.constinit]]) requires a variable to be constant-initialized or compilation fails, so it doesn't take part in dynamic initialization.

## Common pitfalls

### A function declaration instead of an object

```cpp
struct Timer {};
struct Guard { Guard(Timer) {} };
void f() {
  Timer t();            // function declaration: no parameters, returns Timer
  Guard g(Timer());     // also a function declaration: the parameter is "function returning Timer"
  Guard g2{Timer{}};    // OK: an object
}
```

[[dcl.ambig.res]] says that anything that can be parsed as a declaration is parsed as one; this is the [[g:most-vexing-parse|most vexing parse]]. `()` by itself is also not a valid *initializer* ([[dcl.init#15]] Note 6). Braces don't have this problem. Clang gives `-Wvexing-parse` warnings for the first two lines.

### Narrowing

```cpp
#include <vector>
int n = 7.9;               // OK: truncated to 7, Clang only warns
int m{7.9};                // error: narrowing
std::vector<int> v{3.0};   // error: narrowing found after selecting the initializer_list constructor
```

Watch out in generic code: with the same arguments, `T{args...}` may fail due to narrowing while `T(args...)` compiles.

### `initializer_list` constructors take priority

```cpp
#include <string>
#include <vector>
std::vector<int> a(10, 1);              // 10 ones
std::vector<int> b{10, 1};              // 2 elements: 10 and 1
std::vector<std::string> c{3};          // 3 empty strings: int can't convert to string, falls back to vector(size_type)
std::vector<std::string> d{"a", "b"};   // 2 strings
// std::vector<std::string> e{{"a", "b"}};
//   UB: one string, constructed from two unrelated pointers used as an iterator range
```

For container types, use braces to list elements and parentheses to pass arguments such as sizes and counts.

### `= default` outside the class is user-provided

```cpp
struct A { A() = default; int i; };
struct B { B(); int i; };
B::B() = default;   // not = default on its first declaration, so it is user-provided
A a{};              // a.i == 0
B b{};              // b.i is not initialized
```

Likewise, if a class has a hand-written constructor that misses some scalar member, neither `{}` nor `()` from outside will zero it. The safest approach is a default member initializer for every scalar member: `int i = 0;`. Since C++14 this doesn't stop the class from being an aggregate.

### A missed member

```cpp
struct Conn {
  int fd;
  bool open;
  Conn() : fd(-1) {}   // open is not initialized
};
```

In a `Conn` with automatic storage duration, reading `open` is erroneous behavior since C++26 and UB in C++23 and earlier. In an object obtained from `new Conn`, `open` has an indeterminate value, and reading it is UB in every version.

### `auto` and braces

```cpp
auto a = {1};   // std::initializer_list<int>
auto b{1};      // int (since C++17, N3922)
auto c{1, 2};   // error: auto with direct-list-initialization takes only one element
```

### Parenthesized aggregate initialization doesn't extend temporaries

```cpp
#include <string>
struct R { const std::string& name; };
R r1{"temp"};   // the temporary string's lifetime is extended to match r1
void f() {
  R r2("temp"); // valid since C++20, but r2.name dangles immediately (Clang: -Wdangling)
}
```

Parenthesized aggregate initialization was designed on the model of "calling a constructor", and a constructor's reference parameter doesn't extend the lifetime of its argument ([[dcl.init#15]] Note 7, [[class.temporary#6.11]]). More cases are in [[topics/dangling-references]].

### Since C++20, a class with user-declared constructors is not an aggregate

```cpp
struct P { P() = default; int x, y; };
P p{1, 2};   // C++17: OK, P is an aggregate; C++20: error, no matching constructor
```

[[P1008R1]] changed the aggregate condition from "no user-provided constructors" to "no user-declared constructors". The history is in [[dcl.init.aggr]].

### Members are initialized in declaration order

```cpp
struct S {
  int b;
  int a;
  S() : a(1), b(a + 1) {}   // b is initialized first, when a hasn't been initialized yet
};
```

The written order of *mem-initializers* doesn't affect initialization order ([[class.base.init]]). Clang gives two warnings for this code, `-Wreorder-ctor` and `-Wuninitialized`.

## Evolution

| Version | Change |
|---|---|
| C++98 | Zero-initialization, default-initialization; aggregate initialization inherited from C |
| C++03 | Value-initialization added: in C++98, `T()` zeroed only PODs; since C++03, classes without user-declared constructors (such as a class with a `std::string` member) are also zeroed first ([[dcl.init#8]]) |
| C++11 | Brace initialization and `std::initializer_list`, narrowing checks, default member initializers, `= default`/`= delete`, thread-safe initialization of static locals |
| C++14 | Classes with default member initializers can be aggregates; brace elision allowed in direct-list-initialization too, as in `std::array<int, 3> a{1, 2, 3}` |
| C++17 | Guaranteed copy elision ([[P0135R1]]); aggregates may have base classes; `auto x{1}` deduces `int` ([[N3922]]); enumerations with a fixed underlying type allow `E e{1}` |
| C++20 | Designated initializers; parenthesized aggregate initialization ([[P0960R3]]); classes with user-declared constructors are no longer aggregates ([[P1008R1]]); `constinit`; pointer to `bool` counts as narrowing |
| C++23 | Temporaries in range-based for initializers have their lifetime extended (see [[topics/dangling-references]]) |
| C++26 | Uninitialized automatic variables change from UB to erroneous behavior, and `[[indeterminate]]` restores the old behavior ([[P2795R5]]); `return` binding a reference to a temporary is ill-formed |

The current draft also allows designating members of base classes in designated initializers (`B e{.x = 1, .q = 3}` in Example 2 of [[dcl.init.list#3]]). Clang 23 doesn't implement this yet and reports "field designator 'x' does not refer to any field".

!!! summary "Practical advice"
    - Write `T x{…}` or `T x = …` by default to avoid the function declaration ambiguity; use parentheses for size and count arguments to containers.
    - Give every scalar member a default member initializer, so every construction path has a definite value.
    - If you want a class to stay an aggregate, don't declare any constructor for it, including `= default`.
    - Prefer `constexpr` or `constinit` for variables with static storage duration, to avoid cross-file dynamic initialization order problems.
    - Don't store a `std::initializer_list`, and don't let reference members bind to temporaries from constructor arguments.
