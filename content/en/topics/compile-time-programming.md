---
title: Compile-time programming
summary: What constexpr, consteval, constinit, if constexpr, if consteval, templates and concepts, and static reflection are each responsible for, when to use which, and why constant evaluation can catch undefined behavior for you.
tags: constant evaluation, constexpr, consteval, templates, reflection
updated: 2026-10-19
---

!!! tldr
    - A `constexpr` function can be evaluated at compile time; it is not guaranteed to be. Every call to a `consteval` function must be completed at compile time. `constinit` guarantees static initialization, while the variable itself remains modifiable.
    - The standard requires compile-time evaluation only in manifestly constant-evaluated contexts (array bounds, template arguments, `static_assert`, initializers of `constexpr` variables, and so on).
    - Core-language undefined behavior is not allowed during constant evaluation, so if you write tests as `static_assert`, the compiler checks that set of inputs for UB.
    - Memory allocated with `new` at compile time must be freed within the same constant evaluation; it cannot be left for run time.
    - Use `if constexpr` to dispatch on types; use `if consteval` when the same function needs separate compile-time and run-time implementations.

## constexpr does not guarantee compile-time execution

```cpp run ok
constexpr int fib(int n) { return n < 2 ? n : fib(n - 1) + fib(n - 2); }
consteval int fib_ct(int n) { return fib(n); }

int run() {
  int a = fib(20);             // may be computed at run time
  constexpr int b = fib(20);   // must be computed at compile time
  int c = fib_ct(20);          // immediate invocation: must be computed at compile time
  return a + b + c;
}
int main() { return run() == 3 * 6765 ? 0 : 1; }
```

All three lines call the same `constexpr` function. Compiled with Clang 23 at `-O2`, `a` is still a real call to `fib(20)`, since the optimizer doesn't unfold recursion that deep; `b` and `c` are just the constant 6765 in the assembly.

The reason is that whether an expression can be a constant expression and when it is actually evaluated are two separate things.

- Whether it can be a constant expression is a property of the expression, specified by [[expr.const.core]] and [[expr.const.const]].
- When it is evaluated is the implementation's choice. The standard requires a result at translation time only in **manifestly constant-evaluated** contexts ([[expr.const.defns#1]]), such as array bounds, template arguments, `static_assert`, initializers of `constexpr` and `constinit` variables, and calls to `consteval` functions.
- Elsewhere, a constant expression may be left for run time, and a non-constant expression may be folded at compile time by the optimizer.

To guarantee compile-time computation, put the result in a manifestly constant-evaluated context: capture it in a `constexpr` variable, use it as a template argument, put it in a `static_assert`, or declare the function `consteval`.

## The tools at a glance

| Tool | Applies to | Meaning | Introduced | Clause |
|---|---|---|---|---|
| `constexpr` variable | Variables | Must be constant-initialized and have constant destruction; implies `const`; usable in constant expressions | C++11 | [[dcl.constexpr#6]] |
| `constexpr` function | Functions | Can be called in constant expressions, and also at run time | C++11, greatly relaxed in C++14 | [[dcl.constexpr]] |
| `consteval` function | Functions | Can only be called at compile time; every call must be a constant expression | C++20 | [[expr.const.imm]] |
| `constinit` | Variables with static or thread storage duration | Must be statically initialized; does not imply `const` | C++20 | [[dcl.constinit]] |
| `if constexpr` | Statements | The condition is a constant; in a template, the branch not taken is not instantiated | C++17 | [[stmt.if#2]] |
| `if consteval` | Statements | Tests whether the current evaluation is manifestly constant-evaluated; the first branch may call `consteval` functions | C++23 | [[stmt.if#4]] |
| `std::is_constant_evaluated()` | Expressions | Tests the same thing as `if consteval`, but can't be used to call `consteval` functions | C++20 | [[meta.const.eval]] |
| `static_assert` | Declarations | Compile-time assertion | C++11 | [[dcl.pre#13]] |
| Templates and non-type template parameters | Types and values | Generate code parameterized by types and constant values; since C++20 non-type template parameters can be floating-point or of structural class type | C++98, C++20 | [[temp.arg.nontype]] |
| Concepts and `requires` | Constraints | Compile-time predicates that take part in overload resolution | C++20 | [[temp.constr]] |
| Static reflection `^^`, `[: :]` | Program entities | Turns types, members and namespaces into `std::meta::info` values that `consteval` code can query and generate from | C++26 | [[expr.const.reflect]] |
| `consteval { }` block | Declarations | Runs compile-time code at namespace or class scope, which may produce injected declarations | C++26 | [[dcl.pre#15]] |

## The constant evaluator is a strict interpreter

In C++11 a `constexpr` function could contain only a single `return` statement. Since C++14 ([[N3652]]) the rules instead restrict what may happen during evaluation: [[expr.const.core#2]] lists the operations that are not allowed, and the function body may contain loops, local variables and mutation.

You can think of the constant evaluator as a strict interpreter:

- It knows the type, array bounds and lifetime of every object, and the currently active member of every union;
- It doesn't know things that exist only at run time: the values of non-const global variables, the numeric values of addresses, I/O;
- It rejects any undefined behavior.

So code that doesn't touch run-time state, has no UB, doesn't let compile-time allocations escape, and doesn't do type punning can usually be evaluated at compile time.

### Compile-time allocations must not escape

C++20 allows `new`, `delete`, `std::vector` and `std::string` during constant evaluation ([[P0784R7]]), but allocated memory must be freed within the same constant evaluation ([[expr.const.core#2.20]]):

```cpp
#include <vector>
constexpr std::vector<int> v{1, 2, 3};                // error: memory escapes to run time
constexpr int n = std::vector<int>{1, 2, 3}.size();   // OK: the temporary vector is destroyed within the evaluation
```

To get a sequence computed at compile time, a common two-step approach is to compute the length with a dynamic container first, then copy the contents into a fixed-size `std::array`.

```cpp run ok
#include <algorithm>
#include <array>
#include <vector>

constexpr std::vector<int> primes_upto(int n) {
  std::vector<int> v;
  for (int i = 2; i <= n; ++i) {
    bool p = true;
    for (int d : v) {
      if (d * d > i) break;
      if (i % d == 0) { p = false; break; }
    }
    if (p) v.push_back(i);
  }
  return v;
}

constexpr auto primes = [] {
  std::array<int, primes_upto(50).size()> a{};   // first evaluation: just the length
  std::ranges::copy(primes_upto(50), a.begin()); // second evaluation: copy the contents
  return a;
}();

static_assert(primes.size() == 15 && primes.back() == 47);
int main() { return primes[3]; }   // 7
```

C++26's `std::define_static_array` can put a range computed at compile time directly into an array with static storage, without the two-step approach.

## Constant evaluation catches UB

[[expr.const.core#2.8]] says an operation that would have undefined behavior or [[g:erroneous-behavior|erroneous behavior]] makes the expression not a core constant expression. Contexts like `static_assert` require a constant expression, so the compiler must report the UB there. This is the only place where the standard mandates detecting UB.

Write unit tests as `static_assert` and the compiler proves that this set of inputs has no core-language UB:

```cpp error
#include <cstddef>
constexpr int find_last(const int* a, std::size_t n, int x) {
  for (std::size_t i = n; i >= 0; --i)    // bug: size_t is always >= 0
    if (a[i - 1] == x) return int(i - 1);
  return -1;
}
constexpr int test() {
  int a[3] = {1, 2, 3};
  return find_last(a, 3, 42);
}
static_assert(test() == -1);   // error: out-of-bounds access (the index wraps to a huge value)
```

Clang's diagnostic points to where it went out of bounds: `cannot refer to element 18446744073709551615 of array of 3 elements`. At run time the same code is an out-of-bounds read, which may happen to pass or may crash.

Each function below contains a typical kind of UB, and every `static_assert` fails:

```cpp error
#include <climits>
constexpr int t1() { int x = INT_MAX; return x + 1; }               // signed overflow
constexpr int t2() { int a[2]{}; return a[2]; }                     // out-of-bounds read
constexpr int t3() { int* p = new int(1); delete p; return *p; }    // use after free
constexpr int t4() { int* p = new int(1); delete p; delete p; return 0; }   // double free
constexpr int t5() { int* p = new int[2]; delete p; return 0; }     // new[] paired with delete
constexpr int t6() { int x; return x; }                             // reading an uninitialized value (erroneous behavior since C++26)
union U { int i; float f; };
constexpr float t7() { U u{.i = 1}; return u.f; }                   // reading an inactive union member
struct B { virtual constexpr ~B() = default; };
struct D : B { int d = 1; };
constexpr int t8() { B b; return static_cast<D&>(b).d; }            // wrong downcast

static_assert(t1() == 0);   // error
static_assert(t2() == 0);   // error
static_assert(t3() == 0);   // error
static_assert(t4() == 0);   // error
static_assert(t5() == 0);   // error
static_assert(t6() == 0);   // error
static_assert(t7() == 0);   // error
static_assert(t8() == 0);   // error
```

For each one Clang points to the UB itself, for example `value 2147483648 is outside the range of representable values of type 'int'`, `read of heap allocated object that has been deleted`, `non-array delete used to delete pointer to array object of type 'int[2]'`, `read of member 'f' of union with active member 'i'`, `cannot cast object of dynamic type 'B' to type 'D'`.

!!! warning "Limits of this checking"
    1. Only the paths actually executed with the given inputs are checked. `static_assert(f(3) == 9)` passing doesn't mean `f(INT_MAX)` has no UB.
    2. Whether standard library UB is detected is unspecified ([[expr.const.core#4]]). An out-of-bounds `std::vector::operator[]` is usually caught because of the underlying core-language out-of-bounds access, but the standard doesn't guarantee it.
    3. Whether run-time undefined behavior such as `[[assume(false)]]` is detected is implementation-defined ([[expr.const.core#3]]).
    4. Compilers may not have fully caught up with the standard. The current draft says that finite floating-point operands producing infinity is not a constant expression ([[expr.const.core#2.9]]); Clang 23 still accepts `constexpr double d = DBL_MAX * 2;`.
    5. Only code that can be evaluated at compile time is covered; I/O, threads, system calls and `reinterpret_cast` cannot be.

## Three kinds of branch

`if constexpr`, `if consteval` and `std::is_constant_evaluated()` all seem to ask "is this compile time?", but they don't ask the same question:

| | `if constexpr (C)` | `if consteval` | `if (std::is_constant_evaluated())` |
|---|---|---|---|
| Question asked | The value of the constant C | Whether the current evaluation is manifestly constant-evaluated | Same as left |
| When it's decided | At translation or template instantiation, statically | At each evaluation | At each evaluation |
| The branch not taken | Discarded; not instantiated in a template; may be ill-formed | Compiled normally; must be well-formed | Compiled normally; must be well-formed |
| Can the first branch call a `consteval` function with non-constant arguments? | No | Yes | No |
| Typical use | Dispatching on types, e.g. `if constexpr (std::is_integral_v<T>)` | Separate compile-time and run-time implementations | Same as left, the C++20 spelling |

The first branch of `if consteval` is an [[g:immediate-function-context|immediate function context]], where calling a `consteval` function is not required to be a constant expression.

```cpp run ok
#include <cstddef>
#include <cstring>
#include <type_traits>

template<class T>
constexpr void copy_n(T* dst, const T* src, std::size_t n) {
  if consteval {
    for (std::size_t i = 0; i < n; ++i) dst[i] = src[i];   // compile time: element by element
  } else {
    if constexpr (std::is_trivially_copyable_v<T>)
      std::memcpy(dst, src, n * sizeof(T));               // run time: memcpy (not a constexpr function)
    else
      for (std::size_t i = 0; i < n; ++i) dst[i] = src[i];
  }
}
constexpr int t() { int a[3]{1, 2, 3}, b[3]{}; copy_n(b, a, 3); return b[2]; }
static_assert(t() == 3);
int main() { int a[3]{1, 2, 3}, b[3]{}; copy_n(b, a, 3); return b[2] - 3; }
```

!!! pitfall "`if constexpr (std::is_constant_evaluated())`"
    The condition of `if constexpr` is itself manifestly constant-evaluated, so `is_constant_evaluated()` is always `true` there, and the run-time branch is simply discarded. Clang warns `'std::is_constant_evaluated' will always evaluate to 'true' in a manifestly constant-evaluated expression`.

## Initialization: constexpr, constinit and const

| Declaration | Must be constant-initialized | Implies const | Usable in constant expressions | Storage duration |
|---|---|---|---|---|
| `constexpr T x = e;` | Yes | Yes | Yes | Any |
| `constinit T x = e;` | Yes | No | No (except when also `const` and of integral or enumeration type) | Static, thread |
| `const int x = e;` | No; it is if it succeeds | Yes | Yes if constant initialization succeeds (integral and enumeration types only) | Any |
| `T x = e;` (static storage duration) | No; it is if it succeeds | No | No | |

[[g:static-initialization|Static initialization]] is initialization completed before the program starts executing. Without `constinit`, whether a global variable is statically initialized depends on whether its initializer can be evaluated at compile time, and the compiler won't tell you the result. `constinit` turns it into a guarantee the compiler checks, ruling out the [[g:static-initialization-order-fiasco|static initialization order fiasco]]; at the same time the variable can still be modified afterwards, which `constexpr` can't do. See [[expr.const.init]].

```cpp run ok
constinit int counter = 0;               // modifiable, but guaranteed free of initialization order problems
constinit thread_local int depth = 0;    // for cross-TU access, the compiler can omit the TLS init wrapper
int main() { return counter + depth; }
```

## Templates, concepts and constant expressions

Before `constexpr` functions existed, compile-time computation could only be done with templates. Three generations compared:

```cpp ok
// C++98: class templates as functions, specializations as branches
template<int N> struct Fact { static const int value = N * Fact<N - 1>::value; };
template<>      struct Fact<0> { static const int value = 1; };
static_assert(Fact<5>::value == 120);

// C++11: recursion with a single return
constexpr int fact11(int n) { return n <= 1 ? 1 : n * fact11(n - 1); }

// Since C++14: ordinary code
constexpr int fact14(int n) { int r = 1; while (n > 1) r *= n--; return r; }

static_assert(fact11(5) == 120 && fact14(5) == 120);
```

Today values are computed with `constexpr` functions, while types are still computed with templates, because types are not values and a function can't return a type. C++26 reflection, which represents types as `std::meta::info` values, is what breaks this boundary.

Concepts and `requires` clauses are compile-time predicates. The result of substituting into an atomic constraint is manifestly constant-evaluated ([[expr.const.defns#1.5]]), so constraints can call `constexpr` functions:

```cpp ok
constexpr bool is_pow2(unsigned n) { return n && !(n & (n - 1)); }

template<unsigned N> requires (is_pow2(N))
struct RingBuffer { /* use & (N-1) instead of % N */ };

RingBuffer<64> ok;
// RingBuffer<60> bad;   // error: constraints not satisfied
```

Since C++20 a non-type template parameter can be a floating-point number, or a class object of [[g:structural-type|structural type]], roughly a class whose members are all public and not `mutable`:

```cpp ok
struct Point { int x, y; };
template<Point P> constexpr int manhattan = (P.x < 0 ? -P.x : P.x) + (P.y < 0 ? -P.y : P.y);
static_assert(manhattan<Point{3, -4}> == 7);
```

## consteval: must be compile time

A `consteval` function is called an [[g:immediate-function|immediate function]]. Outside an immediate function context, every call to it is an immediate invocation and must be a constant expression ([[expr.const.imm]]). There are three typical uses:

- Validating input at compile time. `std::format` parses its format string at compile time, so a wrong format specifier is a compile error.
- Functions that only make sense at compile time and shouldn't generate code. All the functions of the reflection library are `consteval`.
- Forcing compile-time computation, such as generating `case` labels for a `switch`:

```cpp run ok
#include <cstdint>
#include <string_view>
consteval std::uint32_t fnv1a(std::string_view s) {
  std::uint32_t h = 2166136261u;
  for (char c : s) { h ^= static_cast<unsigned char>(c); h *= 16777619u; }
  return h;
}
constexpr std::uint32_t fnv1a_rt(std::string_view s) {   // run-time version, for the switch condition
  std::uint32_t h = 2166136261u;
  for (char c : s) { h ^= static_cast<unsigned char>(c); h *= 16777619u; }
  return h;
}
int dispatch(std::string_view cmd) {
  switch (fnv1a_rt(cmd)) {
  case fnv1a("start"): return 1;
  case fnv1a("stop"):  return 2;
  default:             return 0;
  }
}
int main() { return dispatch("stop") == 2 ? 0 : 1; }
```

`consteval` used to be hard to use in generic code. C++23's [[P2564R3]] says: if a specialization of a `constexpr` function template calls a `consteval` function and that call is not a constant expression, the specialization automatically becomes an immediate function. A non-template `constexpr` function is not escalated this way:

```cpp error
consteval int id(int x) { return x; }
template<class T> constexpr int tf(T x) { return id(x); }  // OK: tf<int> is escalated to an immediate function
constexpr int nf(int x) { return id(x); }                 // error: not a constant expression
```

When you need two implementations, use `if consteval` in the non-template function.

## Static reflection {{c++26}}

[[P2996R13]] lets a program treat its own structure as data at compile time: `^^T` gives the reflection of type `T`, a `std::meta::info` value; `[: r :]` splices a reflection back into code. Together with C++26's expansion statement `template for`, converting an enumeration value to a string can be written like this:

```cpp
#include <meta>
#include <string_view>
#include <type_traits>

template<typename E> requires std::is_enum_v<E>
constexpr std::string_view enum_to_string(E value) {
  template for (constexpr auto e :
                std::define_static_array(std::meta::enumerators_of(^^E))) {
    if (value == [:e:])
      return std::meta::identifier_of(e);
  }
  return "<unnamed>";
}

enum class Color { red, green, blue };
static_assert(enum_to_string(Color::green) == "green");
```

Reflection values are **consteval-only values** ([[expr.const.const#1]]) and cannot get into run-time objects. A `consteval { ... }` block combined with `std::meta::define_aggregate` can even define classes at compile time. This gives constant evaluation side effects, and the standard uses rules such as evaluation contexts to ensure the result doesn't depend on evaluation order ([[expr.const.reflect]]).

Clang 23 doesn't support reflection, so the examples in this section have not been compiled; you can try them on Compiler Explorer with an experimental reflection implementation.

## Evolution

| Version | Main changes |
|---|---|
| C++98 | Integral constant expressions; template metaprogramming |
| C++11 | `constexpr` variables and functions ([[N2235]]), with function bodies limited to a single `return`; `static_assert` |
| C++14 | Relaxed `constexpr` functions ([[N3652]]): local variables, loops, mutation of local objects |
| C++17 | `if constexpr` ([[P0292R2]]); `constexpr` lambdas |
| C++20 | `consteval` ([[P1073R3]]), `constinit` ([[P1143R2]]), `std::is_constant_evaluated` ([[P0595R2]]); compile-time dynamic allocation and `constexpr` `vector` and `string` ([[P0784R7]]); `constexpr` virtual functions, `try`, `dynamic_cast`, changing the active union member; concepts; class-type non-type template parameters |
| C++23 | `if consteval` ([[P1938R3]]); upward propagation of `consteval` ([[P2564R3]]); using references to unknown values in constant expressions ([[P2280R4]]); variables of non-literal type, `goto` and `static constexpr` variables allowed in `constexpr` functions |
| C++26 | Casting from `void*`, placement new and exceptions in constant evaluation; `constexpr` structured bindings; static reflection, `consteval` blocks, expansion statements |

For clause-level details see [[expr.const]].

## Common pitfalls

!!! pitfall "The parameters of a constexpr function are not constants"
    `constexpr void f(int n) { static_assert(n > 0); }` is always an error, and so is `std::array<int, n>`. The `static_assert` is a separate constant expression, and reading `n` is an lvalue-to-rvalue conversion on an object whose lifetime did not begin within that expression ([[expr.const.core#2.10]]). Clang puts it as `function parameter 'n' with unknown value cannot be used in a constant expression`. To pass a constant, use a template parameter.

!!! pitfall "The compile-time and run-time implementations must be equivalent"
    If the two branches of `if consteval` give different results, the same call gets different values in `constexpr int x = f();` and `int x = f();`; and which branch the latter takes also depends on whether the compiler can complete the initialization at compile time (see Question 1).

!!! pitfall "Whether a global const variable is a constant depends on its initializer"
    In `const int n = g();`, a seemingly unrelated change, such as adding a log line to `g`, turns `n` from static into dynamic initialization, and it can no longer be used in constant expressions. Write `constexpr` when you need a constant and `constinit` when you need static initialization.

!!! pitfall "A constexpr variable inside a function has automatic storage duration"
    `constexpr std::array<int, 1000> table = make();` written inside a function semantically has a copy on the stack for every call. When you need a unique address or want to return a pointer to it, write `static constexpr` (since C++23 this is also allowed in `constexpr` functions).

!!! pitfall "Compile-time computation has a cost"
    The constant evaluator is an interpreter, orders of magnitude slower than native code, and it is subject to implementation limits (Clang's `-fconstexpr-steps`, GCC's `-fconstexpr-ops-limit`, and so on). When a limit is exceeded, it is a compile error in a context that requires a constant; in `const int x = ...;` it silently falls back to dynamic initialization.

!!! pitfall "Floating-point results may differ from run time"
    The standard doesn't guarantee that floating-point computations at translation time and at run time give the same result ([[expr.const.general]]), especially with x87, `-ffast-math`, FMA contraction, or a changed rounding mode.

## Questions

!!! question "Question 1"
    What are `a`, `b` and `c` below? What if `if constexpr (std::is_constant_evaluated())` is replaced with `if consteval`?

    ```cpp
    #include <type_traits>
    constexpr int g() {
      if constexpr (std::is_constant_evaluated()) return 1;
      else return 2;
    }
    constexpr int a = g();
    int b = g();
    int rt;
    int c = g() + rt * 0;
    ```

<details markdown="1">
<summary>Answer</summary>

All are 1. The condition of `if constexpr` is manifestly constant-evaluated, `is_constant_evaluated()` is always `true` there, and the `else` branch is discarded when `g` is defined, so `g` is effectively `return 1;`.

With `if consteval` the result is `1 1 2`. `a` is evaluated at compile time. `b` is a variable with static storage duration; the compiler first tries to evaluate its initializer as a constant expression ([[expr.const.defns#1]]), succeeds, and so it is statically initialized and takes the first branch. `c`'s initializer reads the non-const variable `rt`, the attempt fails, and it falls back to dynamic initialization at run time, taking the `else` branch. Running it with Clang 23 gives the same result.
</details>

!!! question "Question 2"
    Which form guarantees all of the following: `table` is computed at compile time, there is only one copy in the program, and it can be modified at run time?

    ```cpp
    #include <array>
    constexpr auto make() { std::array<int, 4> a{}; for (int i = 0; i < 4; ++i) a[i] = i * i; return a; }
    // (A) constexpr auto table = make();
    // (B) constinit auto table = make();
    // (C) static const auto table = make();
    // (D) auto table = make();
    ```

<details markdown="1">
<summary>Answer</summary>

(B), provided it is at namespace scope, or written as `static constinit` at block scope. `constinit` guarantees static initialization and doesn't imply `const`, so it can be modified at run time.

(A) can't be modified. (C) is `const`, and static initialization isn't guaranteed, although in practice it will happen. (D) will in practice also be constant-initialized when it can be evaluated at compile time, but this isn't checked, and a change to `make` may make it fall back to dynamic initialization.
</details>

!!! question "Question 3"
    Why does C++ say that UB during constant evaluation makes an expression not a constant, rather than saying the result of the UB is unspecified?

<details markdown="1">
<summary>Answer</summary>

The values of constant expressions enter the type system (template arguments, array bounds) and are subject to the ODR: `X<f()>` must be the same type in two translation units. If UB could produce arbitrary values, different compilers, or even the same compiler in different translation units, could arrive at different types, and the program would lose a consistent meaning. During constant evaluation the compiler already fully simulates the object model, so detecting UB is cheap. So the standard says that UB means not a constant ([[expr.const.core#2.8]]), which is a compile error wherever a constant is required.
</details>
