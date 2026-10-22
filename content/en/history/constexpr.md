---
title: "constexpr: fifteen years of growing compile-time evaluation"
summary: From C++98's integral constant expressions and template metaprogramming, to C++11 constexpr functions limited to a single return, to C++20's compile-time vector, consteval and constinit, and C++26's compile-time exceptions; what each step relaxed, why, and which limits never moved.
tags: history, constexpr, consteval, constinit, constant evaluation
updated: 2026-10-19
---

!!! tldr
    - In C++98 the only thing computable at compile time was an integral constant expression, with no function calls; anything more complex had to be written as template metaprogramming.
    - C++11's `constexpr` explicitly marks functions that may be called at compile time, under rules so conservative that only a single `return` was allowed. Every standard since has relaxed them: C++14 allowed local variables and loops, C++20 virtual calls and dynamic allocation, C++26 throwing and catching exceptions.
    - One limit has never moved: every effect of a constant evaluation must be wrapped up before the evaluation ends. That is why memory obtained with `new` at compile time must be freed in the same evaluation, and why a `constexpr std::vector` variable still cannot be written.
    - Constant evaluation has disallowed undefined behavior from the start, which turns `static_assert` into a UB detector that covers only the paths actually executed.
    - `consteval`, `constinit` and `if consteval` answer three questions `constexpr` itself cannot: callable only at compile time, must be statically initialized, and telling compile time from run time inside a function.

The rules themselves are in [[expr.const]], [[expr.const.core]] and [[dcl.constexpr]]; how the tools divide the work and how to use them is covered in [[topics/compile-time-programming]]. HOPL IV on this page is Stroustrup's *Thriving in a Crowded and Changing World: C++ 2006–2020* (2020), a retrospective by one of the participants.

## C++98: what could be computed at compile time

### Only integral constant expressions

C++98 inherited constant expressions from C, and only the integral kind. Array bounds, `case` labels, enumerator values and non-type template arguments all required an **integral constant expression**: literals, enumerators, `const` integral variables initialized with constants, `sizeof`, and built-in operations on these. Function calls were never allowed.

The first example Dos Reis and Stroustrup give in [[N2235]] §3.1 is `std::numeric_limits<int>::max()`. It is functionally equivalent to the macro `INT_MAX`, but because it is a function call it cannot be used in an array bound, so programmers had to fall back on the macro.

§3.4 of the same proposal also points out that a variable that looks like a constant may silently be dynamically initialized, and there was no way to require that it be initialized at compile time. That problem only got an answer with C++20's `constinit`:

<div class="compare" markdown="1">

```cpp run std=c++98 ok
#include <limits>
struct S { static const int size; };
const int limit = 2 * S::size;
// S::size is defined later, so limit is
// dynamically initialized, without a warning
const int S::size = 256;
const int z =
  std::numeric_limits<int>::max();
// a function call: also dynamic initialization
int main() {}
```

```cpp run std=c++20 error
struct S { static const int size; };
constinit const int limit = 2 * S::size;
// error: not constant initialization. constinit
// turns the hidden hazard into a compile error
const int S::size = 256;
int main() {}
```

</div>

### Template metaprogramming

The other route was to let template instantiation do the computation: a recursive class template plus a terminating specialization, with the result stored in an enumerator.

```cpp run std=c++98 ok
template <unsigned N> struct Factorial {
  enum { value = N * Factorial<N - 1>::value };
};
template <> struct Factorial<0> {
  enum { value = 1 };
};

// C++98's static_assert: the array length is -1 when the condition is false
typedef char check[Factorial<5>::value == 120 ? 1 : -1];
int main() {}
```

This works, but the cost is obvious: branches need specializations, loops need recursive instantiation, only integers and types can be computed, errors produce a long instantiation stack, and every step of the computation leaves a class template instance behind in the compiler (see [[history/template-metaprogramming]]). HOPL IV §4.2.7 calls it "tedious and error-prone".

## C++11: why a keyword, and why only one return

### An explicit marker

In 2003 Gabriel Dos Reis proposed generalized constant expressions ([[N1521]]): allowing simple enough functions and simple enough user-defined types in constant expressions. The latter kind of type later became the [[g:literal-type|literal type]]. The goals included making compile-time computation type-safe, putting data into ROM, and making compile-time programming as similar as possible to ordinary programming (HOPL IV §4.2.7).

The original proposal had no keyword; the compiler was to decide by itself which functions were simple enough. The committee required a syntactic marker ([[N2235]] §4.5), and so `constexpr` came about. HOPL IV gives two reasons:

- Without a marker, whether a function could be used in a constant expression would depend on how clever each compiler was, and code would not be portable;
- To be ready for constant evaluation at any moment, compilers would have to keep every function body around.

The first reason says what `constexpr` really is: part of a function's interface, a promise from the author to callers. This comes up again in the debate over making every function `constexpr` by default (later on this page).

### A conservative start

[[N2235]], merged into C++0x in 2007, specified that the body of a `constexpr` function could only be a single `return expr;`; the proposal itself describes this as just a different way of writing named constant expressions with parameters. It also introduced `constexpr` constructors and floating-point constant expressions.

N2235 originally also banned recursion, saying it did not intend to allow it before seeing convincing use cases. That rule did not survive: C++11 allows recursive `constexpr` functions, and implementations may limit the recursion depth ([[implimits]]). So C++11 `constexpr` functions were commonly written as a conditional operator plus recursion:

<div class="compare" markdown="1">

```cpp run std=c++11 ok
constexpr unsigned long long
fact(unsigned n) {
  return n <= 1 ? 1 : n * fact(n - 1);
}
static_assert(fact(5) == 120, "");
int main() {}
```

```cpp run std=c++14 ok
constexpr unsigned long long
fact(unsigned n) {
  unsigned long long r = 1;  // not in C++11
  for (unsigned i = 2; i <= n; ++i)
    r *= i;                  // not in C++11
  return r;
}
static_assert(fact(5) == 120, "");
int main() {}
```

</div>

The right side is ill-formed in C++11. With `-std=c++11`, Clang 23 gives only an extension warning for the local variable and an error for the `for` statement.

According to Stroustrup, the proposal was repeatedly considered both useless and unimplementable, until the major compilers implemented it; the first version took four years to get accepted (HOPL IV §4.2.7). Along with it, C++11 made the member functions of `numeric_limits` `constexpr`, removing the embarrassment N2235 opened with.

## C++14: local variables and loops

Soon after C++11 shipped, users started asking for relaxation. Richard Smith's [[N3652]], accepted in 2013, allowed local variables, `if`/`switch` and loops in the function body, allowed a `void` return type, and allowed modifying objects whose lifetime began within the current constant evaluation.

The second half of its title is *constexpr member functions and implicit const*. In C++11 a `constexpr` non-static member function was implicitly `const`, which conflicted with the new rule allowing objects to be modified, so C++14 dropped the implicit `const`. This is one of the few incompatible changes in the history of `constexpr`: C++11 code relying on the implicit `const` has to add `const` explicitly.

```cpp run std=c++14 ok
struct Point {
    int x, y;
    constexpr Point(int x, int y) : x(x), y(y) {}
    constexpr void move(int dx) { x += dx; }   // C++11: implicitly const, can't assign; can't return void either
};
constexpr Point shifted() {
    Point p{1, 2};       // local variable
    p.move(3);           // modify an object created in this evaluation
    return p;
}
static_assert(shifted().x == 4, "");
int main() {}
```

With `-std=c++11`, Clang reports two errors for `move` (assigning to a member in a `const` member function, and the return type `void` not being a literal type), and warns that it is no longer implicitly `const` in C++14.

HOPL IV specifically points out that these local variables exist only inside the compiler, and the evaluation cannot have side effects on the caller's environment. That limit shaped every later relaxation: constant evaluation can do more and more, but all of its effects must be wrapped up before the evaluation ends.

## C++17: lambdas and if constexpr

### Lambdas are constant-evaluable by default

[[P0170R1]] specifies that a lambda's function call operator is implicitly `constexpr` whenever it meets the requirements for a `constexpr` function. This was the first time `constexpr` did not need to be written.

```cpp run std=c++17 ok
auto square = [](int x) { return x * x; };   // no constexpr written
static_assert(square(7) == 49);              // not a constant expression in C++14
int main() {}
```

### if constexpr: a scaled-down static if

In 2012 there was a proposal to borrow D's `static if` ([[N3329]]): it could appear at namespace and class scope, did not introduce a new scope, and the branch not taken was not even parsed. [[N3613]] by Stroustrup, Dos Reis and Sutton argued against it systematically: the same syntax had three different semantics in different contexts; unparsed branches made programs hard to read and debug and got in the way of tools based on syntax trees; and the part of the need that was about constraining templates should be handled by concepts.

A few years later the idea came back in a much smaller form as C++17's `if constexpr` ([[P0292R2]]): just a statement, allowed only in function bodies, with its own scope, and the branch not taken is still parsed. These limits are still visible in today's rules: the branch not taken is a **discarded statement**, which is not instantiated in a template but must be syntactically valid code ([[stmt.if#2]]).

<div class="compare" markdown="1">

```cpp run std=c++17 error
#include <string>
#include <type_traits>
template <class T>
std::string describe(T v) {
  if (std::is_integral_v<T>)
    return "int:" + std::to_string(v);
  else return "other";
}
int main() { describe("x"); }
// error: both branches are instantiated,
// and there is no to_string(const char*)
```

```cpp run std=c++17 ok
#include <string>
#include <type_traits>
template <class T>
std::string describe(T v) {
  if constexpr (std::is_integral_v<T>)
    return "int:" + std::to_string(v);
  else return "other";
}
int main() { describe("x"); }
// OK: with T = const char*, the first
// branch is discarded and not instantiated
```

</div>

`if constexpr` did not extend what constant evaluation can do. It lets a template choose which code to instantiate based on a compile-time condition, replacing a lot of tag dispatch and SFINAE code.

## C++20: dynamic allocation at compile time

### Virtual functions, try, unions, new

A set of proposals in 2018–2019 removed, one by one, things that were banned in constant evaluation: virtual function calls ([[P1064R0]]), `try` blocks ([[P1002R1]], though evaluation still fails if it reaches a `throw`), `dynamic_cast` and polymorphic `typeid` ([[P1327R1]]), changing the active member of a union ([[P1330R0]]), and uninitialized local variables ([[P1331R2]], as long as the evaluation does not read them).

The one with the biggest impact was [[P0784R7]] *More constexpr containers*. Its goal was to make `std::vector` usable at compile time, which needed two things: destructors that can be `constexpr`, and `new`/`delete` in constant evaluation.

```cpp run std=c++20 ok
struct Shape {
    virtual constexpr ~Shape() = default;
    virtual constexpr int area() const = 0;
};
struct Square : Shape {
    int s;
    constexpr explicit Square(int s) : s(s) {}
    constexpr int area() const override { return s * s; }
};
constexpr int total() {
    Shape* p = new Square(3);   // allocation during constant evaluation
    int a = p->area();          // virtual call during constant evaluation
    delete p;                   // must be freed before the evaluation ends
    return a;
}
static_assert(total() == 9);
int main() {}
```

With `-std=c++17`, Clang reports that neither destructors nor virtual functions can be `constexpr`.

### Transient allocation: memory cannot leave compile time

Allocation follows the rules of [[g:transient-allocation|transient allocation]]: memory allocated during constant evaluation must be freed before that same evaluation ends, otherwise the expression is not a constant expression ([[expr.const.core]]). This continues the limit from the C++14 section. On this basis, Louis Dionne's [[P1004R2]] and [[P0980R1]] made `vector` and `string` `constexpr`:

<div class="compare" markdown="1">

```cpp run std=c++20 ok
#include <numeric>
#include <vector>
constexpr int sum_squares(int n) {
  std::vector<int> v;
  for (int i = 1; i <= n; ++i)
    v.push_back(i * i);
  return std::accumulate(
    v.begin(), v.end(), 0);
}  // v is destroyed; memory freed within the evaluation
static_assert(sum_squares(4) == 30);
int main() {}
```

```cpp run std=c++20 error
#include <vector>
constexpr std::vector<int> v =
  {1, 2, 3};
// error: memory not yet freed when the evaluation ends
int main() {}
```

</div>

For the right side Clang explains `pointer to subobject of heap-allocated object is not a constant expression`. Why not let memory allocated at compile time survive into run time? That would require answering how heap objects at compile time become static data in the program image, and who frees them at run time; no answer to those questions has been accepted yet ([[P3032R2]] is one attempt). C++26 took another approach: functions such as `std::define_static_array` ([[P3491R3]]) explicitly copy data computed at compile time into arrays with static storage duration.

### consteval: callable only at compile time

A `constexpr` function can be called at compile time or at run time. Some functions should exist only at compile time. [[P1073R3]] introduced the **immediate function**, with the keyword `consteval`; in early revisions it was spelled `constexpr!`. The proposal says the main motivation came from static reflection, then being designed: reflection query functions should exist only at compile time and generate no object code.

```cpp run std=c++20 error
consteval int sq(int x) { return x * x; }
constexpr int a = sq(4);          // OK
int runtime_value();
int b = sq(runtime_value());      // error: a call to an immediate function must be a constant expression
int main() {}
```

This line continued into C++26: the reflection functions in `std::meta` are all `consteval`.

### constinit: requiring only static initialization

The dynamic initialization problem from the C++98 section was answered by [[P1143R2]]. It originally proposed an attribute `[[constinit]]`, later changed to a keyword on the grounds that the whole point of the feature is to enforce a check, and attributes can be ignored by compilers. `constinit` only requires the variable to be constant-initialized ([[dcl.constinit]]); it does not make the variable `const`, which is how it differs from a `constexpr` variable:

```cpp run std=c++20 ok
consteval int sq(int x) { return x * x; }
constinit int counter = sq(3);    // guaranteed static initialization
int next() { return ++counter; }  // counter is not const and can be modified
int main() { return next() == 10 ? 0 : 1; }
```

### is_constant_evaluated and its trap

Library authors often want the same function to use a constant-evaluable implementation at compile time and a faster one at run time (builtins, SIMD). [[P0595R2]] provided `std::is_constant_evaluated()` for this ([[meta.const.eval]]). It has a well-known trap: placed in the condition of `if constexpr`, the condition itself is computed in constant evaluation, so the result is always `true`.

```cpp run std=c++20
#include <type_traits>
constexpr int f(int x) {
    if constexpr (std::is_constant_evaluated())   // always true
        return x;
    else
        return -x;
}
int main() { return f(1) == 1 ? 0 : 1; }   // a run-time call also takes the first branch
```

This code is well-formed; it just doesn't do what the programmer meant. Clang warns `'std::is_constant_evaluated' will always evaluate to 'true' in a manifestly constant-evaluated expression`.

## C++23: fixing inconsistencies

### if consteval

`is_constant_evaluated()` has a second problem: even when written correctly as `if (std::is_constant_evaluated())`, the branch cannot pass function parameters to a `consteval` function, because the compiler cannot be sure the branch only runs at compile time. [[P1938R3]]'s `if consteval` solves both problems: it has no condition expression, so it can't be written wrong, and its first branch is an immediate function context ([[stmt.if#5]]).

<div class="compare" markdown="1">

```cpp run std=c++20 error
#include <type_traits>
consteval int sq(int x) { return x * x; }
constexpr int g(int x) {
  if (std::is_constant_evaluated())
    return sq(x);  // error: x is not a constant
  return x * x;
}
int main() {}
```

```cpp run std=c++23 ok
consteval int sq(int x) { return x * x; }
constexpr int g(int x) {
  if consteval { return sq(x); }  // OK
  else { return x * x; }
}
static_assert(g(3) == 9);
int main(int argc, char**) {
  return g(argc) == 1 ? 0 : 1;
}
```

</div>

### From syntactic checks to evaluation checks

C++20 checked `constexpr` function bodies syntactically: if a variable of non-literal type, a `static` variable, `goto` or a label appeared anywhere, the whole function could not be `constexpr`, even if that code was only in a run-time branch. [[P2242R3]] turned these into checks at evaluation time: they may appear as long as constant evaluation does not reach them.

```cpp run std=c++23 ok
constexpr int h(int x) {
    if (x < 0) {
        static int calls = 0;  // C++20: ill-formed; C++23: fine as long as constant evaluation doesn't reach it
        return ++calls;
    }
    return x;
}
static_assert(h(1) == 1);
int main() { return h(-1) == 1 ? 0 : 1; }
```

With `-std=c++20`, Clang 23 gives only an extension warning for the `static` variable.

### constexpr means less

Since C++11 there had been a rule: if a `constexpr` function could not produce a constant expression for any arguments, the program was ill-formed, no diagnostic required. Barry Revzin's [[P2448R2]] removed it. The reason was that the rule punished code that might become valid in the future: a `constexpr` function that today calls some non-`constexpr` library function may find that library function `constexpr` tomorrow.

```cpp run std=c++23 ok
int g();                            // not constexpr
constexpr int f() { return g(); }   // C++20: IFNDR (Clang errors); C++23: well-formed
int g() { return 0; }
int main() { return f(); }
```

With `-std=c++20`, Clang reports `constexpr function never produces a constant expression`. From then on, `constexpr` on a function only means it may be called during constant evaluation; it no longer guarantees that any call can be constant-evaluated.

## C++26: type erasure, exceptions and reflection

### Casting back from void*, placement new

The core operation of type-erasure tools such as `std::any` and `std::function` is to store an address as `void*` and cast it back to the original type when used. C++23 constant evaluation banned casts from `void*`, so none of these could be used at compile time. [[P2738R1]] allows such a cast, provided the type of the object `void*` actually points to matches the target type. C++20 had allowed `std::construct_at` but not placement new written directly; [[P2747R2]] filled that gap.

```cpp run std=c++2c ok
#include <memory>
#include <new>
constexpr int via_void_ptr() {
    int x = 42;
    void* p = &x;
    return *static_cast<int*>(p);          // C++26: P2738
}
static_assert(via_void_ptr() == 42);

constexpr int placement() {
    std::allocator<int> a;
    int* p = a.allocate(1);
    ::new (static_cast<void*>(p)) int(7);  // C++26: P2747
    int r = *p;
    std::destroy_at(p);
    a.deallocate(p, 1);
    return r;
}
static_assert(placement() == 7);
int main() {}
```

With `-std=c++23`, Clang reports `cast from 'void *' is not allowed in a constant expression in C++ standards before C++2c`.

### Compile-time exceptions

C++20 allowed `try` blocks, but evaluation failed as soon as it reached a `throw`. Hana Dusíková's [[P3068R6]] allows exceptions to be thrown inside constant evaluation, as long as they are caught within the same evaluation; once again, the limit that effects cannot leave the evaluation. C++26's reflection library reports errors with exceptions ([[P3560R2]]), and it relies on exactly this step.

```cpp run std=c++2c
#include <stdexcept>
constexpr int checked_div(int a, int b) {
    if (b == 0) throw std::domain_error("division by zero");
    return a / b;
}
constexpr int safe(int a, int b) {
    try { return checked_div(a, b); }
    catch (const std::domain_error&) { return 0; }
}
static_assert(safe(6, 3) == 2);
static_assert(safe(1, 0) == 0);   // C++26: the exception is thrown and caught inside constant evaluation
int main() {}
```

According to the standard this code is well-formed in C++26. Clang 23 does not yet implement P3068 and reports `subexpression not valid in a constant expression` for the second `static_assert`, so no verdict is marked here.

C++26 also allows structured bindings to be declared `constexpr` ([[P2686R5]]), allows virtual inheritance in constant evaluation ([[P3533R2]]), and makes more standard library components `constexpr`.

```cpp run std=c++2c ok
struct P { int x, y; };
constexpr P pt{1, 2};
constexpr auto [a, b] = pt;   // C++23: error; C++26: OK
static_assert(a + b == 3);
int main() {}
```

As of C++26, the main things constant evaluation still forbids are: `reinterpret_cast`, reading objects whose values are only known at run time, calling non-`constexpr` functions, mismatched allocation and deallocation, and core-language undefined behavior. The full list is in [[expr.const.core]].

### Reflection: consteval programming

C++26 static reflection ([[P2996R13]]) continues this line. Reflection was the main motivation for `consteval` in the first place; P0784's dynamic allocation lets reflection functions return `std::vector<std::meta::info>`; P3068's exceptions give reflection its error handling. Metaprogramming can now be written with ordinary functions, loops and containers, without resorting to template specialization.

```cpp
#include <meta>
struct S { int a; double b; };
constexpr auto ctx = std::meta::access_context::unchecked();
static_assert(std::meta::nonstatic_data_members_of(^^S, ctx).size() == 2);
```

This code is well-formed in C++26. Clang 23 does not provide the `<meta>` header, so we could not verify it and no verdict is marked. The rules are in [[expr.const.reflect]].

## Constant evaluation as a UB detector

Since N2235, constant expressions have not been allowed to contain undefined behavior. Item 2.8 of [[expr.const.core#2]] in the current draft says that if the evaluation performs an operation the core language specifies as undefined behavior or erroneous behavior, the expression is not a core constant expression.

```cpp run std=c++2c error
#include <climits>
constexpr int add(int a, int b) { return a + b; }
constexpr int x = add(INT_MAX, 1);      // error: signed overflow is UB
constexpr int arr[3] = {1, 2, 3};
constexpr int y = arr[3];               // error: out-of-bounds read
int main() {}
```

For the two errors Clang explains `value 2147483648 is outside the range of representable values of type 'int'` and `read of dereferenced one-past-the-end pointer is not allowed in a constant expression`. The same code at run time gets no diagnostic at all.

This led to a common technique: call the function under test inside a `static_assert` and let the compiler check for UB (see [[topics/compile-time-programming]] and [[topics/undefined-behavior]]). It has three limitations:

- It checks only the path this particular evaluation actually takes;
- It covers only core-language UB. Whether standard library UB is detected is unspecified ([[expr.const.core#4]]), because requiring compilers to check every library precondition is not realistic;
- For cases like `[[assume]]` that are only undefined at run time (runtime-undefined behavior), whether constant evaluation rejects them is implementation-defined ([[expr.const.core#3]]).

This need in turn pushed the standard itself to become more precise. In HOPL IV §9.3.3 Stroustrup writes that for a construct to become `constexpr`, it has to be precisely specified and "stripped of the possibility of undefined behavior". The new annex [[ub]] in the current draft systematically lists all core-language UB ([[P3596R3]]).

## Should everything be constexpr?

If more and more functions can be constant-evaluated, why mark `constexpr` by hand at all?

[[P1235R0]] *Implicit constexpr* (2018) proposed that when a constant expression calls a function not marked `constexpr` whose definition is visible, the function be treated as `constexpr`. The reasoning was that manual marking had become a burden in both the standard library and third-party libraries, and that C++17 had already made lambdas implicitly `constexpr`, creating an inconsistency between functions and lambdas. The proposal did not make it into the standard. GCC has an experimental option `-fimplicit-constexpr` that treats `inline` functions as `constexpr`; Clang 23 does not support it.

There were three main objections:

- **Interface promise.** Being constant-evaluable becomes part of the interface. If it were the default, users would come to depend on it, and a library author who later switched to an implementation that cannot be constant-evaluated (P1235's own example is switching to SIMD intrinsics) would break user code. P1235's answer was to provide `constexpr(false)` as an opt-out for authors.
- **Compile-time cost.** This was exactly the second reason for requiring an explicit marker in the first place. HOPL IV §9.3.3 also says C++ programmers must learn to use compile-time computation only where it pays off.
- **Where the boundary is.** Stroustrup acknowledges that some people want every C++ construct usable at compile time; his response is "That may be too much of a good thing", and he asks whether threads are really needed at compile time. At the same time he admits that the current division between what is allowed and what is not is "a bit ad hoc and not coherent" (HOPL IV §9.3.3).

C++23's [[P2448R2]] took a middle road: keep the keyword, but weaken its meaning to: may be called during constant evaluation. Library authors can mark functions `constexpr` up front, and it takes effect naturally once the things they depend on become `constexpr` too.

## Timeline

| Standard | New capabilities in constant evaluation | Main proposals |
|---|---|---|
| C++98 | Integral constant expressions only; complex computation via template metaprogramming | |
| C++11 | `constexpr` functions (single `return`), literal types, `constexpr` constructors | [[N2235]] |
| C++14 | Local variables, loops, modifying local objects; member functions no longer implicitly `const` | [[N3652]] |
| C++17 | Lambdas implicitly `constexpr`; `if constexpr` | [[P0170R1]], [[P0292R2]] |
| C++20 | Virtual calls, `try` blocks, transient dynamic allocation, `constexpr` destructors; `vector`/`string`; `consteval`, `constinit`, `is_constant_evaluated` | [[P0784R7]], [[P1073R3]], [[P1143R2]], [[P0595R2]] |
| C++23 | `if consteval`; parts not evaluated are unrestricted; the requirement that some set of arguments be constant-evaluable is removed | [[P1938R3]], [[P2242R3]], [[P2448R2]] |
| C++26 | Casts from `void*`, placement new, compile-time exceptions, `constexpr` structured bindings; static reflection | [[P2738R1]], [[P2747R2]], [[P3068R6]], [[P2996R13]] |

## Work in progress

- constexpr coroutines ([[P3367]]), not yet merged into the draft as of October 2026;
- Non-transient allocation, letting memory allocated at compile time survive into run time ([[P3032R2]]);
- Making more library functions `constexpr`; almost every meeting sees new proposals;
- A systematic survey of UB: the [[ub]] annex and the framework proposed in [[P3100R8]] will affect which operations are rejected in constant evaluation.

Looking back, fifteen years of `constexpr` have followed one pattern: enter the standard with the most conservative rules, then relax them one at a time as implementation experience and user demand accumulate. What has not changed is the limit: the effects of a constant evaluation cannot leave the evaluation.

## References

- Bjarne Stroustrup. *Thriving in a Crowded and Changing World: C++ 2006–2020*. HOPL IV, Proc. ACM Program. Lang. 4 (HOPL), 2020. §4.2.7, §5.5, §9.3.3.
- Gabriel Dos Reis, Bjarne Stroustrup, Jens Maurer. *Generalized Constant Expressions — Revision 5*. [[N2235]], 2007.
- Richard Smith. *Relaxing constraints on constexpr functions / constexpr member functions and implicit const*. [[N3652]], 2013.
- Bjarne Stroustrup, Gabriel Dos Reis, Andrew Sutton. *"Static If" Considered*. [[N3613]], 2013.
- Peter Dimov, Louis Dionne, Nina Ranns, Richard Smith, Daveed Vandevoorde. *More constexpr containers*. [[P0784R7]], 2019.
- Richard Smith, Andrew Sutton, Daveed Vandevoorde. *Immediate functions*. [[P1073R3]], 2018.
- Eric Fiselier. *Adding the constinit keyword*. [[P1143R2]], 2019.
- Barry Revzin, Daveed Vandevoorde, Richard Smith, Andrew Sutton. *if consteval*. [[P1938R3]], 2021.
- Barry Revzin. *Relaxing some constexpr restrictions*. [[P2448R2]], 2022.
- Hana Dusíková. *Allowing exception throwing in constant-evaluation*. [[P3068R6]], 2024.
- Bryce Adelstein Lelbach, Hana Dusíková. *Implicit constexpr*. [[P1235R0]], 2018.
