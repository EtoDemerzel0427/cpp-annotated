---
title: The constexpr and consteval specifiers
summary: "Which declarations constexpr and consteval may appear on; a constexpr function definition now only has to not be a coroutine, and whether it can be evaluated at compile time is decided call by call; a constexpr variable must be of literal type, constant-initializable and have constant destruction; and the implicit const and implicit inline that follow."
updated: 2026-10-19
---

!!! tldr
    - A `constexpr` function can be called in constant expressions and also called at run time like an ordinary function; every call to a `consteval` function (an immediate function) must be completed at compile time.
    - The current draft has only one requirement left for the definition of a constexpr function: it can't be a coroutine. Whether a particular call can be evaluated at compile time depends on what that evaluation actually executes.
    - Adding `constexpr` doesn't change a function's run-time behavior or its type, so you can't overload on constexpr-ness.
    - A `constexpr` variable is const, must be of literal type, must be initialized by a constant expression, and must be destructible at compile time.
    - constexpr functions, and static data members whose first declaration has `constexpr`, are implicitly inline; constexpr variables at namespace scope are not inline.

Things declared `constexpr` can take part in **constant evaluation**, i.e. having their results computed during translation. The conditions under which an expression is a constant expression are specified in [[expr.const]]; this subclause only specifies the specifiers themselves: what they can apply to, and what they mean for functions and for variables.

## Where they can be written (¶1)

```cpp error
constexpr void square(int& x);  // OK: a function may just be declared
constexpr int bufsz = 1024;     // OK: variable definition
constexpr struct pixel {        // error: pixel is a type, can't be constexpr
    int x, y;
};
int next(constexpr int x);      // error: a parameter can't be constexpr
extern constexpr int memsz;     // error: constexpr can only be written on a variable's definition
struct S { constexpr int m = 1; };   // error: a non-static data member can't be constexpr
constexpr int f();
int f();                        // error: all declarations must agree
```

¶1 `constexpr` can only be applied to the definition of a variable or variable template, a structured binding declaration, or the declaration of a function or function template. `consteval` can only be applied to the declaration of a function or function template. If any declaration of a function has `constexpr` or `consteval`, all of its declarations must have the same specifier; note 1 adds that an explicit specialization can differ from the primary template.

A variable can have `constexpr` only on its definition, because the point of a constexpr variable is that its value is known where it is used, and a declaration without an initializer provides no value. A function can be declared first and defined later; until its definition appears, though, calls to it can't be evaluated at compile time (see the `pixel` example below).

Note 2 says that parameters can't be `constexpr`. The same function is called with different arguments, so a parameter's value can't be determined at compile time. If you need a compile-time argument, use a template parameter (which can be of class type since C++20), or declare the whole function `consteval`.

## constexpr functions and immediate functions (¶2)

```cpp run ok
consteval int sq(int n) { return n * n; }
constexpr int sq2(int n) { return n * n; }
int main(int argc, char**) {
    constexpr int a = sq(4);     // OK: constant expression
    int b = sq2(argc);           // OK: a constexpr function can be called at run time
    // int c = sq(argc);         // error: a call to an immediate function must be a constant expression
    return a + b - 17;           // returns 0 when argc == 1
}
```

¶2 A function declared with `constexpr` or `consteval` is a **constexpr function** ([[g:constexpr-function]]). Note 3 points out that a function declared with `consteval` is an **immediate function**: unless the call itself is in a compile-time context such as another immediate function, every call to it must be a constant expression ([[expr.const.imm]]).

So, terminologically, a consteval function is also a constexpr function. Everything below about implicit inline, requirements on the definition and consistent behavior applies to it too.

¶2 Its last sentence says that destructors, allocation functions (`operator new`) and deallocation functions (`operator delete`) can't be `consteval`:

```cpp error
struct S {
    consteval ~S() { }                                  // error
    consteval void* operator new(decltype(sizeof 0));   // error
};
```

These functions are called implicitly by the language: the destructor when an object goes out of scope, the allocation function by a `new` expression. If they were immediate functions, objects created at run time couldn't be allocated or destroyed. They can be `constexpr`; constexpr destructors have been allowed since C++20 ([[P0784R7]]).

## The only requirement on the definition: not a coroutine (¶3)

```cpp run ok
constexpr int square(int x) { return x * x; }
constexpr int abs_(int x) { if (x < 0) x = -x; return x; }  // since C++14: modifying local variables
constexpr int constant_non_42(int n) {
    if (n == 42) {
        static int value = n;    // may appear in a constexpr function since C++23
        return value;            // but this path can't be evaluated at compile time
    }
    return n;
}
constexpr int pow_(int x, int n) {
    int r = 1;
    while (--n > 0) r *= x;      // since C++14: loops
    return r;
}
static_assert(square(3) == 9 && abs_(-2) == 2);
static_assert(constant_non_42(7) == 7 && pow_(2, 4) == 8);
int main() { return constant_non_42(42) - 42; }   // takes the n == 42 path at run time: valid
```

`pow_(2, 4)` is 8, not 16: `--n > 0` makes the loop run only 3 times. This function copies `g` from the standard's example.

¶3 A function that is not a coroutine is called **constexpr-suitable**. Except for constexpr functions obtained by instantiating a template, a non-template constexpr function must be constexpr-suitable. Suspending and resuming a coroutine needs a coroutine frame and run-time scheduling, which the current model of constant evaluation can't express.

Beyond that, the definition itself has no restrictions any more. Whether it declares `static` variables, calls ordinary functions or reads uninitialized variables is not checked at definition time; it is deferred to each constant evaluation: if an evaluation actually executes a disallowed operation ([[expr.const.core]]), that evaluation is not a constant expression. `constant_non_42` above works this way: when `n` isn't 42 it can be evaluated at compile time; when it is 42 it can only be called at run time.

The standard's example also has an `uninit()` with an error comment:

```cpp run ok
constexpr int uninit() {
    struct { int a; } s;
    return s.a;          // commented in the standard's example as "error: uninitialized read of s.a"
}
int main() { }
```

That error means any constant evaluation of `uninit()` fails, because reading an uninitialized value is not a core constant expression. The function definition itself is well-formed, and Clang 23 accepts it; with `constexpr int u = uninit();`, the error is in that variable's initialization.

!!! note "From IFNDR to well-formed: P2448"
    C++20 and earlier had a rule: if no argument values exist such that a call to a non-template constexpr function could be a constant expression, the program is **ill-formed, no diagnostic required** (IFNDR: the compiler may or may not report an error, and the program has no guarantees at all). The problem was that a function calling a library function that isn't constexpr yet could never be constant-evaluated; once that library function became constexpr in the next standard, the same code became valid again. [[P2448R2]] removed this rule in C++23. Note 5 keeps the idea: it is entirely possible to write a constexpr function for which no call is a core constant expression.

    ```cpp run ok
    int rt();
    constexpr int calls_rt() { return rt(); }   // well-formed since C++23; IFNDR in C++20
    int rt() { return 1; }
    int main() { return calls_rt() - 1; }
    ```

    With `-std=c++20`, Clang 23 reports a `-Winvalid-constexpr` error for this function (which IFNDR permits); from `-std=c++23` on it no longer does.

!!! history "What constexpr functions can do"
    | Standard | Added | Papers |
    |---|---|---|
    | C++11 | The body is essentially a single `return` (plus `static_assert`, typedefs, etc.); member functions are implicitly const | |
    | C++14 | Local variables, assignment, `if`, `switch`, loops; member functions no longer implicitly const | |
    | C++17 | constexpr lambdas; `if constexpr` | |
    | C++20 | Virtual functions; `try` blocks (but no actual throwing); trivial default initialization; unevaluated `asm`; changing the active member of a union; constexpr destructors and `new`/`delete`; `consteval` | [[P1064R0]], [[P1331R2]], [[P0784R7]], [[P1073R3]] |
    | C++23 | Variables of non-literal type, `goto`, labels, `static`/`thread_local` variables (as long as they are not evaluated); removal of the requirement that constant arguments exist; `static constexpr` local variables usable in constant evaluation | [[P2242R3]], [[P2448R2]], [[P2647R1]] |
    | C++26 | Conversion from `void*`; placement new; throwing and catching exceptions; classes with virtual bases can have constexpr constructors and destructors; the only requirement left on the definition is not being a coroutine | [[P2738R1]], [[P2747R2]], [[P3068R6]], [[P3533R2]] |

## Define first, then call at compile time

```cpp run ok
constexpr void square(int& x);           // declaration only
struct pixel {
    int x, y;
    constexpr pixel(int);                // declaration only
};
constexpr pixel::pixel(int a) : x(a), y(x) { square(x); }
// constexpr pixel small(2);             // error: square isn't defined yet
constexpr void square(int& x) { x *= x; }
constexpr pixel large(4);                // OK: square is defined
static_assert(large.x == 16 && large.y == 4);   // y took the old value of x before square
int main() { }
```

This is the second half of Example 1 in the standard. Calling a constexpr function that hasn't been defined yet is not a core constant expression ([[expr.const.core]]), so `small(2)` fails the requirement that a constexpr variable be constant-initializable (¶6). Constant evaluation sees the definitions available up to the current point of translation; it isn't deferred to later the way template instantiation is.

## Adding constexpr doesn't change a function's behavior (¶4–¶5)

¶4 A call to a constexpr function produces the same result as a call to an equivalent non-constexpr function in the same context in all respects, with two exceptions:

- ¶4.1 a call to a constexpr function can appear in a constant expression;
- ¶4.2 copy elision is not performed in a constant expression ([[class.copy.elision]]).

**Copy elision** means omitting the copy or move construction when returning or passing by value. Except in the cases mandated since C++17, it is an optional optimization. If constant evaluation could decide for itself whether to do it, then when a copy constructor has observable effects, the value of a constant expression would depend on the implementation's choice. Requiring that it is never done makes the result deterministic.

Note 4 points out a subtlety: adding `constexpr` can change whether some expression is a constant expression, and so indirectly change the result of `std::is_constant_evaluated()` (or `if consteval`) inside the function:

```cpp run ok
#include <type_traits>
constexpr int which() { return std::is_constant_evaluated() ? 1 : 2; }
int non_constexpr_twin() { return std::is_constant_evaluated() ? 1 : 2; }
const int a = which();      // initializing a const int tries constant evaluation first: 1
int main() {
    int b = which();        // initializing an ordinary variable is not constant evaluation: 2
    return (a == 1 && b == 2 && non_constexpr_twin() == 2) ? 0 : 1;
}
```

¶5 `constexpr` and `consteval` don't affect the type of a function. So you can't overload on constexpr-ness, and a constexpr definition and an ordinary definition can't coexist:

```cpp error
constexpr int bar(int x, int y) { return x + y + x * y; }
int bar(int x, int y) { return x * 2 + 3 * y; }   // error: redefinition of bar
```

To use different implementations at compile time and at run time, branch inside the same function with `if consteval` (C++23, [[stmt.if]]) or `std::is_constant_evaluated()`. An ordinary function pointer `int(*)(int, int)` can also point to a constexpr function.

## constexpr variables (¶6)

```cpp error
struct pixel { int x, y; };
constexpr pixel ur = { 1294, 1024 };     // OK
constexpr pixel origin;                  // error: not initialized
struct NonLit { NonLit(); };
constexpr NonLit nl{};                   // error: not a literal type
constexpr int* leak = new int(1);        // error: the allocated memory isn't freed by the end of the evaluation
```

¶6 When `constexpr` is used in an object declaration:

1. the object is const;
2. the object must be of **literal type** (roughly, a type that can be created and destroyed during constant evaluation, [[basic.types.general]]) and must be initialized;
3. the variable must be **constant-initializable**: the full-expression of its initialization is a constant expression, and the pointers and references in the resulting value refer only to objects that can be referred to at compile time ([[expr.const.init#4]]);
4. a constexpr variable that is an object, and any temporary a constexpr reference is bound to, must have **constant destruction**: destroying it can also be done at compile time ([[expr.const.defns#3]]).

`const` only means the object can't be modified through this name, and its initialization may happen at run time; `constexpr` requires the initialization itself to be a constant expression, so the value is fixed during translation. C++98 left a special case: a const variable of integral or enumeration type that happens to be initialized with a constant expression can also be used in constant expressions ([[expr.const.init#6]], [[expr.const.init#7]]). Variables of type `double` or of class type only qualify if they are declared `constexpr`.

Point 4 guarantees that an object created at compile time can also be destroyed at compile time. Memory allocated with `new` during constant evaluation must be freed within the same evaluation; this is called **transient allocation**. So `constexpr std::vector<int> v{1, 2, 3};` is ill-formed: `v` still owns heap memory when the initialization ends.

### constexpr references bound to local variables {{c++26}}

```cpp
namespace N {
    void f() {
        int x;
        constexpr int& ar = x;              // C++26: OK
        static constexpr int& sr = x;       // error: x is not referenceable at the point marked below
    }
    // the immediate scope here is N
}
```

In C++23 and earlier, a constexpr reference could only bind to an object with static storage duration, because the object's address had to be a constant. C++26 introduces **constexpr-referenceable**: seen from a point P, an automatic variable is constexpr-referenceable if it is within the scope of the same function as P (with only block scopes in between) ([[expr.const.init#2]]). An object or reference is **constexpr-representable** at P when all the pointers and references in it refer to such objects ([[expr.const.init#3]]).

- `ar` is an automatic variable in the function. After its declaration, `x` is in `f` with it, so it's OK.
- `sr` is `static`, and item 4.3 of [[expr.const.init#4]] additionally requires it to be representable at the first point after its declaration whose immediate scope is a namespace scope. That point is outside `f`, where `x` is not referenceable, so it is ill-formed.

The direct motivation for this change ([[P2686R5]]) was C++26's constexpr structured bindings: `constexpr auto& [a, b] = local;` needs to bind to a local object. Clang 23 doesn't implement it yet and also reports an error for the `ar` line.

!!! lawyer "constexpr variables and odr-use"
    A constexpr variable is const. If reading its value can be done in a constant expression, that read is not an **odr-use** (the kind of use that requires the variable to have a definition, [[basic.def.odr]]). So after `constexpr int n = 3;` in a function, a lambda can use the value of `n` without capturing it; but taking `&n` or binding a reference to it is an odr-use and requires a capture.

## Implicit inline (¶1)

¶1 also says: a function or static data member whose first declaration has `constexpr` or `consteval` is implicitly inline ([[dcl.inline]]). Inline means that each of several translation units may have its own identical definition. This has two consequences:

- constexpr functions can, and usually should, be defined in headers; every translation unit using one has a definition, without violating the ODR ([[basic.def.odr]]).
- Since C++17, an in-class `static constexpr` data member declaration is itself a definition, and the out-of-class `constexpr int S::m;` is no longer needed. That out-of-class declaration is now a redundant redeclaration and is deprecated ([[depr.static.constexpr]]).

```cpp run ok
struct S { static constexpr int m = 1; };
const int* p = &S::m;     // OK since C++17: S::m is an inline variable, the in-class declaration is the definition
int main() { return *p - 1; }
```

!!! pitfall "constexpr variables at namespace scope are not inline"
    Implicit inline applies only to static data members. `constexpr int N = 10;` at namespace scope is not an inline variable; it is const and therefore has internal linkage ([[basic.link#3]]), so every translation unit including the header has its own object, and the `&N` all differ. That's usually harmless. But if you need a unique address, or need to odr-use it in an inline function without violating the ODR, write `inline constexpr int N = 10;`. The standard library's `std::is_same_v` and friends are written this way.

!!! impl "Parts Clang 23 doesn't implement yet"
    - A class with a virtual base still can't have a constexpr constructor or destructor; the diagnostic is "constexpr constructor not allowed in struct with virtual base class". This is the old C++23 rule, which C++26 removed ([[P3533R2]]).
    - Exceptions can't be thrown during constant evaluation yet: `try { throw 1; } catch (int) { … }` fails to evaluate in a `static_assert`.
    - constexpr references can't bind to local variables yet (see above).

!!! pitfall "Common misconceptions"
    - A constexpr function always runs at compile time: that's only guaranteed where a constant expression is required; elsewhere it's an ordinary call, and constant folding by the compiler is just an optimization. To guarantee compile-time evaluation, use `consteval`, or assign the result to a constexpr variable.
    - constexpr member functions are implicitly const: only in C++11; since C++14 they aren't.
    - constexpr variables in headers violate the ODR: they don't. At namespace scope they have internal linkage, one per translation unit; static data members are inline.
    - A consteval function is not a constexpr function: by the definition in paragraph 2, it is.

!!! summary "Summary"
    | | constexpr function | consteval function | constexpr variable |
    |---|---|---|---|
    | Usable at run time | Yes | No; calls must be constant expressions | The value is known during translation; the object also exists at run time |
    | Implicitly inline | Yes | Yes | Only static data members |
    | Implicitly const | No (since C++14) | No | Yes |
    | Structural requirements | Not a coroutine | Not a coroutine; not a destructor, allocation or deallocation function | Literal type, initialized, constant-initializable, constant destruction |
    | Across declarations | Must agree | Must agree | Only on the definition |

!!! question "Question 1"
    What is the status of the following program in C++20 and in C++23?

    ```cpp
    #include <cstdio>
    int now();
    constexpr int stamp() { return now(); }
    int now() { return 42; }
    int main() { std::printf("%d\n", stamp()); }
    ```

<details markdown="1">
<summary>Answer</summary>

`now` is not a constexpr function, so no call to `stamp` can be a core constant expression. In C++20 this is a non-template constexpr function for which no constant arguments exist, which is IFNDR, and an implementation may reject it; Clang 23 reports a `-Winvalid-constexpr` error under `-std=c++20`. Since C++23 ([[P2448R2]]) the program is well-formed and prints 42 at run time.
</details>

!!! question "Question 2"
    Why is `constexpr std::string_view sv = "hello";` always well-formed, while `constexpr std::string s = "...";` depends on the string's length and the standard library implementation?

<details markdown="1">
<summary>Answer</summary>

¶6 requires the initialization of a constexpr variable to be a constant expression and the variable to have constant destruction, and memory allocated during constant evaluation must be freed within the same evaluation. When a string exceeds the capacity of the short string optimization (SSO), `std::string` allocates heap memory and still owns it when the initialization ends, so it is not a constant expression. A short string lives inside the object and allocates nothing, so whether it passes depends on the implementation: in our tests libc++ accepts `constexpr std::string s = "hello";` and rejects a long string. A `string_view` stores only a pointer to a string literal (an object with static storage duration) and a length, allocates nothing, is a literal type and has a trivial destructor, so it is always well-formed.
</details>
