---
title: Constant initialization
summary: "When the initialization of a variable counts as constant initialization (which decides whether a static variable is initialized at compile time or at run time), where pointers and references in constants may point in C++26, and which variables can be read in constant expressions."
updated: 2026-10-19
---

!!! tldr
    - If a variable with static or thread storage duration is constant-initialized, its value is ready before the program starts, with no cross-translation-unit initialization order problem; otherwise it is dynamically initialized at run time. `constinit` turns this into a compile-time check.
    - The conditions for constant initialization are: the initializer is a constant expression, and the pointers and references in the variable all point to objects that can be referred to as constants from there.
    - Since C++26, a constexpr pointer or reference can point to a local variable in the same function call, but it cannot be stored into a static variable or used inside a lambda.
    - To be read in a constant expression, a variable must also be constexpr, a reference, or of const integral or enumeration type. `const double` doesn't qualify.
    - During the check, `std::is_constant_evaluated()` is true: the compiler first tries to evaluate the initializer at compile time, and if that fails, falls back to run-time initialization.

## Compile-time versus run-time initialization

```cpp title="a.cpp"
int compute();                  // defined elsewhere, not constexpr
int b_val = compute();          // dynamic initialization
```

```cpp title="b.cpp" unspecified
extern int b_val;
int a_val = b_val + 1;          // dynamic initialization; b_val may still be 0
```

The order of dynamic initialization across two translation units is unspecified ([[basic.start.dynamic]]). If `a_val` is initialized first, the `b_val` it reads is just the zero-initialized 0. This is the well-known static initialization order problem.

If `b_val` is initialized with a constant, say `int b_val = 41;`, the problem goes away. [[basic.start.static#2]] says that a variable with static or thread storage duration that is **constant-initialized** ([[g:constant-initialized]]) undergoes constant initialization; otherwise it is zero-initialized first. Together these are called static initialization, and both happen before any dynamic initialization.

| | Constant initialization | Dynamic initialization |
|---|---|---|
| When it completes | Before the program starts; the value is written directly into `.data` or `.rodata` | At run time: before `main` for namespace-scope variables, the first time control passes through for block-scope `static`s |
| Initialization order problem | None | The order across translation units is unspecified |
| Block-scope `static` | No guard variable needed | Needs a thread-safe guard variable (`__cxa_guard_acquire` in the Itanium ABI) |
| `thread_local` | No initialization wrapper function needed | Access from other translation units may go through a TLS wrapper function |

An implementation may also perform static initialization early for a variable that would otherwise be dynamically initialized, as long as the result is the same ([[basic.start.static#3]]). So a variable not being constant-initialized doesn't mean it is necessarily initialized at run time; there is just no guarantee.

!!! tip "constinit: requiring constant initialization"
    C++20's `constinit` ([[P1143R2]]) requires the variable to have static initialization, or the program is ill-formed ([[dcl.constinit#2]]). Unlike `constexpr`, it doesn't imply `const`, so the variable can be modified later.

    ```cpp
    constinit int counter = 0;                  // modifiable global with no initialization order problem
    constinit thread_local int tls_depth = 0;   // access from other translation units can skip the TLS wrapper

    const char* g() { return "dynamic"; }
    constexpr const char* f(bool p) { return p ? "constant" : g(); }
    constinit const char* c = f(true);          // OK
    constinit const char* d = f(false);         // error: not constant initialization
    ```

    The benefit for `tls_depth` requires the declarations in other translation units to carry `constinit` too (`extern constinit thread_local int tls_depth;`), so the compiler knows no initialization check is needed.

## What counts as constant initialization (¶4–¶5)

¶4 A variable v is **constant-initializable** if all three of the following hold:

1. the full-expression of its initialization is a constant expression ([[expr.const.const]]) when interpreted as a *constant-expression*;
2. immediately after the initializing declaration of v, the object or reference declared by v is constexpr-representable;
3. if it has static or thread storage duration, it is also constexpr-representable at the nearest point immediately following the initializing declaration that is directly in namespace scope.

Conditions 2 and 3 are new in C++26 and check where the pointers and references in the variable point; that is covered in the next section.

Condition 1 has two notes. Note 1: during the check, `std::is_constant_evaluated()` has the value true; its consequences are shown later. Note 2 {{c++26}}: during the check, all contract assertions are treated with the ignore semantic ([[basic.contract.eval]]), but if the initialization really is evaluated at compile time, the compiler may still check contracts with another semantic, issuing a diagnostic or making the program ill-formed on violation. So a failed contract check doesn't silently turn constant initialization into dynamic initialization.

¶5 A constant-initializable variable is constant-initialized if it has an initializer or its type is [[g:const-default-constructible]] (a class type whose default initialization initializes all members, [[dcl.init.general]]).

Why the extra condition? `static int sx;` has no initializer, its default initialization does nothing, and the subsequent zero-initialization is handled separately by [[basic.start.static]]. It never goes through initialization with a constant, so it doesn't count as constant initialization.

## Where pointers and references in constants may point (¶1–¶3) {{c++26}}

```cpp
void f() {
  int x;
  constexpr int& ar = x;           // C++26: OK
  static constexpr int& sr = x;    // error: a static reference to a local variable
}
```

On each call to `f`, `ar` refers to the `x` of that call; its meaning is well-defined, and the compiler can implement it as an offset on the stack. `sr`, however, is a static variable, and it would keep the reference to the `x` from the first call forever, dangling by the next call. C++26 turns this intuition into rules with the following three concepts.

¶1 The **constituent values and constituent references** ([[g:constituent-values|constituent values and references]]) of a variable x: if x declares an object, they are the constituent values and references of that object ([[intro.object]], i.e. the values of all scalar subobjects and all reference members once the object is expanded); if x declares a reference, that reference itself is a constituent reference of x. In addition, the constituent values and references of any temporary object whose lifetime is extended by being bound to a constituent reference count recursively as those of x.

Temporaries are included because in `struct A { const int& r; }; constexpr A a{2};`, the lifetime-extended temporary exists and is destroyed together with `a`, so its contents are part of `a`.

¶2 An object o is **constexpr-referenceable** from a program point P if either:

- o has static storage duration; or
- o has automatic storage duration, and the smallest scope containing the variable o belongs to and the smallest scope containing P are the same function parameter scope. When finding the smallest scope, block scopes are skipped, and so is the parameter scope of a *requires* expression, since the latter doesn't correspond to a real function call. The variable o belongs to is the variable corresponding to its complete object, or the variable to which o's lifetime is extended.

Intuitively, an automatic variable can be referred to as a constant only when the referrer and the variable are in the same function call. All blocks in a function body share one stack frame, and the address of a local variable means the same thing anywhere in the function body. A lambda body is a different function, its call is a different stack frame, and the lambda may be carried elsewhere and called there. Objects with thread storage duration are never constexpr-referenceable: there is one instance per thread, and their addresses have no uniform meaning at compile time.

```cpp
struct A {
  int m;
  const int& r;
};
void f() {
  static int sx;
  thread_local int tx;    // tx is not constexpr-referenceable anywhere
  int ax;
  A aa = {1, 2};
  static A sa = {3, 4};
  // here: sx, ax, aa.m, sa.m, and the temporaries bound to aa.r and sa.r are
  auto lambda = [] {
    int ay;
    // here: sx, sa.m, ay, and the temporary bound to sa.r are; ax and aa are not
  };
}
```

¶3 An object or reference x is **constexpr-representable** at P if every object pointed to (or past) by a constituent value of x, and every object referred to by a constituent reference of x, is constexpr-referenceable from P.

Back to the opening example. Right after the initializing declaration of `ar`, `x` is in the same function, so item 4.2 is satisfied. `sr` is static, and item 4.3 requires checking again at the next namespace-scope program point, which is outside `f`, where `x` is not constexpr-referenceable, so `sr` is not constant-initialized.

¶5 The standard's Example 2 combines several storage durations:

```cpp
void f() {
  int ax = 0;                   // constant-initialized
  thread_local int tx = 0;      // constant-initialized
  static int sx;                // not: no initializer, and int is not const-default-constructible
  static int& rss = sx;         // constant-initialized: sx is static
  static int& rst = tx;         // not: tx is thread-local
  static int& rsa = ax;         // not: a static reference to an automatic variable
  thread_local int& rts = sx;   // constant-initialized
  thread_local int& rtt = tx;   // not
  thread_local int& rta = ax;   // not
  int& ras = sx;                // constant-initialized
  int& rat = tx;                // not
  int& raa = ax;                // constant-initialized: the same function call
}
```

Automatic variables such as `ax` and `raa` can also be constant-initialized. The concept doesn't only decide static initialization; it is also a prerequisite for a variable being usable in constant expressions (next section).

!!! history "From permitted results to constexpr-representable"
    In C++23 and earlier, pointers and references in the result of a constant expression could only point to objects with static storage duration (the permitted results in [[expr.const.const]]), so `constexpr int& ar = x;` was invalid. C++26's [[P2686]] introduced the three concepts above and moved the requirement from expressions to variables, which made constexpr references within the same function possible; constexpr structured bindings are implemented on top of this too.

!!! impl "Implementation status"
    Clang 23 still follows the C++23 rules: it rejects `constexpr int& ar = x;`, reporting `constexpr variable 'ar' must be initialized by a constant expression`.

## Variables usable in constant expressions (¶6–¶9)

Which objects created outside the evaluation can be read during constant evaluation? The answer of [[expr.const.core#2.10]] is: objects usable in constant expressions.

```cpp
const int a = 10;           // a constant-initialized const int
int arr1[a];                // OK

int rt();
const int b = rt();         // not constant-initialized
int arr2[b];                // error: b is not usable in constant expressions

const double d = 1.0;       // constant-initialized, but the type is double
static_assert(d == 1.0);    // error: const double is not potentially-constant
```

¶6 A variable is **potentially-constant** ([[g:potentially-constant]]) if it is constexpr, or has reference type, or has non-volatile const-qualified integral or enumeration type. This type threshold preserves a special case from C++98: `const int n = 10;` can be used as an array bound without `constexpr`, but `const double` cannot.

¶7 A variable V is **usable in constant expressions** ([[g:usable-in-constant-expressions|usable in constant expressions]]) at a program point P if all of the following hold:

- V is constant-initialized and potentially-constant;
- the initializing declaration D of V is reachable from P;
- one of the following holds: V is constexpr (7.1); V is not initialized to a TU-local value (7.2); P is in the same translation unit as D (7.3).

```cpp
extern const int late;
static_assert(late == 1);   // error: the initializing declaration of late is not reachable here
const int late = 1;
static_assert(late == 1);   // OK
```

Items 7.2 and 7.3 are mainly about modules. A TU-local value is a value referring to an entity valid only in its own translation unit (such as an object with internal linkage); see [[basic.link]]. If an exported non-constexpr `const` variable is initialized to such a value, other translation units cannot use it as a constant.

¶8 The following objects or references are **potentially usable in constant expressions** at P:

- the object or reference declared by a variable usable in constant expressions at P (8.1);
- a temporary object of non-volatile const-qualified literal type whose lifetime is extended to that of such a variable (8.2);
- a template parameter object (8.3, [[temp.param]]);
- a string literal object (8.4, [[lex.string]]);
- a non-mutable subobject (8.5) or reference member (8.6) of any of the above.

¶9 An object or reference is **usable in constant expressions** at P if it is potentially usable in constant expressions and constexpr-representable at P.

```cpp
struct A { int m; const int& r; };
constexpr A ga = {1, 2};       // the lifetime of the temporary 2 is extended to ga
static_assert(ga.r == 2);      // OK: items 8.2 and 8.6

constexpr const char* s = "abc";
static_assert(s[1] == 'b');    // OK: a string literal object

struct M { mutable int x; };
constexpr M mm{1};
static_assert(mm.x == 1);      // error: mutable subobjects are excluded

const int c = 10;
int& rc = const_cast<int&>(c); // reference type, bound to a static object
static_assert(rc == 10);       // OK: rc is usable, and so is the c it refers to
```

The constexpr-representable condition of paragraph 9 handles a situation that exists only in C++26: a constexpr variable holding a pointer to a local variable cannot be used in a different function call (such as a lambda).

```cpp
struct B { int* const& r; };
void g(int x) {
  constexpr B b = {&x};
  static_assert(b.r == &x);             // C++26: OK
  [&] {
    static_assert(b.r != nullptr);      // error: inside the lambda, x is not constexpr-referenceable
  }();
}
```

Clang 23 already errors at `constexpr B b = {&x};`, because under the C++23 rules a pointer to an automatic variable cannot be the result of a constant expression, and the two `static_assert`s after it fail as a consequence.

## Try at compile time first, fall back to run time

Note 1 on item 4.1 says that `std::is_constant_evaluated()` is true while deciding whether the initializer is a constant expression. So the initialization of a variable with static storage duration has two steps: the compiler first tries to evaluate it at compile time, and if that fails, it is dynamically initialized the run-time way, at which point `is_constant_evaluated()` returns false.

```cpp run ok
#include <cstdio>
#include <type_traits>
int y;
const int a = std::is_constant_evaluated() ? y : 1;  // the trial fails reading y: dynamic initialization
const int b = std::is_constant_evaluated() ? 2 : y;  // the trial gives 2: constant initialization
int main() { std::printf("%d %d\n", a, b); }         // 1 2
```

The result for `a` is particularly counterintuitive: the expression contains `is_constant_evaluated()`, yet it is ultimately evaluated at run time, gets false, and takes 1. See [[expr.const.defns]] for the full analysis.

!!! warning "Clang's warning is not entirely accurate"
    Clang gives a `-Wconstant-evaluated` warning for both lines, saying `is_constant_evaluated` "will always evaluate to 'true' in a manifestly constant-evaluated expression". That doesn't hold for `a`, which is dynamically initialized, and where the call returns false at run time. The real point of the warning is that this kind of code is probably not what you want.

## Common misconceptions

!!! pitfall "The constancy of a `const int` depends on its initializer"
    Whether `n` in `const int n = f();` can be used in constant expressions depends entirely on whether `f()` can be evaluated at compile time. Add one non-constexpr logging call to `f`, and a distant `int arr[n];` breaks, with no diagnostic at the declaration of `n`. Write `constexpr` when you need a constant, and `constinit` when you need static initialization.

!!! pitfall "A constexpr local variable is a static variable"
    `constexpr int arr[1000] = {...};` inside a function has automatic storage duration and is a new object on each call. Compilers usually optimize it into a direct reference to data in `.rodata`, but the standard doesn't guarantee a stable address. If you need a unique address, or want to return a pointer to it, write `static constexpr`.

!!! pitfall "The initializer of a block-scope static always runs at run time"
    If the initializer can be evaluated at compile time, the block-scope `static` variable is constant-initialized, and nothing happens when control passes through it:

    ```cpp run ok
    #include <cstdio>
    int calls = 0;
    constexpr int expensive() {
      if !consteval { ++calls; }   // counts only at run time
      return 42;
    }
    int get() {
      static int cache = expensive();   // constant initialization
      return cache;
    }
    int main() {
      get();
      std::printf("%d\n", calls);       // 0
    }
    ```

## Questions

!!! question "Question 1"
    Is each of the following variables constant-initialized? Is it usable in constant expressions?

    ```cpp
    struct P { int v; constexpr P() : v(7) {} };
    const P p1;                       // (1)
    const int i1 = P().v;             // (2)
    const double d1 = 1;              // (3)
    int& r1 = const_cast<int&>(i1);   // (4)
    ```

<details markdown="1">
<summary>Answer</summary>

1. `p1` has no initializer, but `P` has a user-provided constexpr default constructor and is const-default-constructible, so it is constant-initialized. It has class type and is not constexpr, so it is not potentially-constant and therefore not usable in constant expressions; `static_assert(p1.v == 7)` fails.
2. `i1` is constant-initialized (`P().v` is a constant expression), its type is `const int`, and it is usable in constant expressions.
3. `d1` is constant-initialized (it gets static initialization), but `const double` is not potentially-constant, so it is not usable in constant expressions.
4. `r1` is a reference, so it is potentially-constant; its initializer is a constant expression referring to a static object, so it is constant-initialized and usable in constant expressions. `static_assert(r1 == 7)` reads `i1`, which is usable, so it holds.

Clang 23's results match the above.
</details>

!!! question "Question 2"
    Why does paragraph 2 exclude objects with thread storage duration from constexpr-referenceable altogether, while objects with static storage duration always qualify?

<details markdown="1">
<summary>Answer</summary>

An object with static storage duration has a single instance in the whole program, and its address can be represented as a symbol plus an offset, filled in by the linker or loader, the same for every user. An object with thread storage duration has one instance per thread, and its address can only be computed at run time through the thread pointer; there is no uniform value that could be written into `.data`, so it cannot be stored as a constant in a constexpr variable. `rst` in Example 2 is not constant-initialized for the same reason.
</details>

## Summary

| Concept | Condition | Role |
|---|---|---|
| constexpr-referenceable {{c++26}} | Static storage duration, or an automatic object in the same function call | Defines the next row |
| constexpr-representable {{c++26}} | The targets of all constituent pointers and references are constexpr-referenceable | A condition for constant initialization and usability |
| constant-initializable | The initializer is a constant expression and the result is representable | Required of constexpr variables |
| Constant-initialized | Constant-initializable, and has an initializer or is const-default-constructible | Static initialization, `constinit` |
| Potentially-constant | constexpr, reference, or const non-volatile integral or enumeration | The type threshold for usability |
| Usable in constant expressions | Constant-initialized + potentially-constant + reachable (+ TU-local restriction) | Allowed to be read by [[expr.const.core#2.10]] |
