---
title: Manifest constant evaluation and constant destruction
summary: "Which expressions must be evaluated during translation (exactly what std::is_constant_evaluated() observes); which expressions trigger the instantiation of constexpr functions; and why the destruction of constexpr variables must also be possible at compile time."
updated: 2026-10-19
---

!!! tldr
    - Manifestly constant-evaluated expressions are the ones the language requires to be evaluated during translation: array bounds, template arguments, the condition of `if constexpr`, consteval blocks, immediate invocations, constraint checking, and the initializers of constant-initialized variables.
    - `std::is_constant_evaluated()` and `if consteval` observe exactly this property, not whether the code actually runs at compile time or at run time.
    - Whether a variable is constant-initialized is decided by trial evaluation of its initializer, during which `is_constant_evaluated()` is true. A variable whose trial fails is initialized at run time, where it is false again, and the same initializer picks the other branch.
    - constexpr functions named by potentially constant evaluated expressions are instantiated, even if they are not odr-used. Expressions in brace initialization fall into this category, because narrowing has to be checked.
    - constexpr variables must have constant destruction: the process of destroying them must itself be evaluable as a constant expression.

## Manifest constant evaluation (¶1)

### Which expressions must be evaluated at compile time

The values of some expressions determine the structure of the program, such as array lengths and template arguments, and the compiler must compute them during translation. ¶1 calls such expressions or conversions **manifestly constant-evaluated** ([[g:manifestly-constant-evaluated|manifestly constant-evaluated]]):

| Item | Case | Examples |
|---|---|---|
| ¶1.1 | A syntactic *constant-expression* | Array bounds, `case` labels, template arguments, `static_assert` conditions, `alignas`, bit-field widths, enumerator initializers, `noexcept(…)` |
| ¶1.2 | The condition of a constexpr if statement | `if constexpr (cond)` |
| ¶1.3 | The expression corresponding to a consteval block {{c++26}} | `consteval { … }` |
| ¶1.4 | An immediate invocation | Calling a consteval function outside an immediate function context ([[expr.const.imm]]) |
| ¶1.5 | The result of substitution into an atomic constraint expression to determine whether it is satisfied | `requires (sizeof(T) > 4)` |
| ¶1.6 | The initializer of a variable that is usable in constant expressions or has constant initialization | `constexpr int x = …;`, `constinit` variables, successfully constant-initialized `const int n = …;` and static variables |

The first five items are determined by syntactic position and obvious at a glance. ¶1.6 is different: whether an initializer is manifestly constant-evaluated depends on whether the variable is constant-initialized ([[basic.start.static]]), which in turn depends on whether the initializer can be evaluated as a constant expression, forming a cycle.

The standard breaks the cycle with a conceptual trial evaluation (footnote 63, [[expr.const.init#4]]). To decide, the initializer is first tried as a constant expression, during which `std::is_constant_evaluated()` is true and contract assertions are treated with the ignore semantic. If the trial succeeds, the variable is constant-initialized and the initializer is manifestly constant-evaluated; if it fails, the variable is dynamically initialized at run time, where `is_constant_evaluated()` is false.

### The standard's example

```cpp run title="mce.cpp" ok
#include <cstdio>
#include <type_traits>
template<bool> struct X {};
X<std::is_constant_evaluated()> x;   // template argument (¶1.1): the type is X<true>

int y;
const int a = std::is_constant_evaluated() ? y : 1;  // dynamically initialized to 1
const int b = std::is_constant_evaluated() ? 2 : y;  // statically initialized to 2
int c = y + (std::is_constant_evaluated() ? 2 : y);  // dynamically initialized to y + y

constexpr int f() {
  const int n = std::is_constant_evaluated() ? 13 : 17;  // n is 13
  int m = std::is_constant_evaluated() ? 13 : 17;        // 13 or 17
  char arr[n] = {};                                      // char[13]
  return m + sizeof(arr);
}
int p = f();       // m is 13 in this call: p == 26
int q = p + f();   // m is 17 in this call: q == 56

int main() { std::printf("%d %d %d %d\n", a, b, p, q); }   // 1 2 26 56
```

One by one:

- `a`: the trial picks `y`, and reading the non-constant `y` fails, so `a` is dynamically initialized. At run time `is_constant_evaluated()` is false and picks `1`. The value of `a` is 1, but it is not constant-initialized and cannot be used in constant expressions.
- `b`: the trial picks `2` and succeeds, so it is statically initialized to 2.
- `c`: either branch reads `y`, so the trial fails, and at run time it gets `y + y`. `c` is not `const`, but it is a variable with static storage duration, so "has constant initialization" in ¶1.6 applies as well, and it is tried too.
- `n`: a `const int` variable that is constant-initialized is usable in constant expressions, so its initializer is manifestly constant-evaluated. Even when `f()` is called at run time, `n` is 13, which is why `char arr[n]` is valid.
- `m`: not `const`, so its initializer is not manifestly constant-evaluated, and the value of `is_constant_evaluated()` depends on whether the enclosing `f()` is being constant-evaluated. The trial for `int p = f();` succeeds, so `p` is statically initialized to 26. `int q = p + f();` reads the non-const `p`, the trial fails, `f()` is called at run time with `m` being 17, and `q` is 56.

Running this with Clang 23 gives the same results as the standard's example.

<div class="compare" markdown="1">

```cpp run ok
#include <type_traits>
int y;
const int b =
  std::is_constant_evaluated() ? 2 : y;
static_assert(b == 2);   // OK
```

```cpp run error
#include <type_traits>
int y;
const int a =
  std::is_constant_evaluated() ? y : 1;
static_assert(a == 1);   // error
```

</div>

The standard's example uses `double z[a];`. Without `-pedantic-errors`, Clang 23 only warns about it, treating it as a variable-length array extension and folding it into a fixed-size array, so `static_assert` is used here instead.

!!! warning "Clang's `-Wconstant-evaluated` isn't always right"
    Clang warns on the `X<…>`, `a`, `b` and `n` lines: "'std::is_constant_evaluated' will always evaluate to 'true' in a manifestly constant-evaluated expression". For `a` that is wrong: `a` is ultimately initialized to 1 at run time. The value of the warning is in pointing out that this kind of code is probably not what you want.

### Evaluated even inside unevaluated operands

Note 1 of ¶1: except for the message of a `static_assert`, a manifestly constant-evaluated expression is evaluated even when it appears in an unevaluated operand ([[expr.context]]).

```cpp run error
template<class T> constexpr int f() { return T::value; }
constexpr int g() { return sizeof(char[f<int>()]); }  // error: int::value doesn't exist
```

The operand of `sizeof` is not evaluated, but the array bound is a *constant-expression* whose value must be computed to determine the type `char[N]`, so `f<int>` is instantiated and evaluated. The message of a `static_assert` is the exception because C++26 allows user-generated messages ([[dcl.pre#13]]), which only need to be evaluated when the assertion fails.

### Why is_constant_evaluated is designed this way

When C++20 introduced `std::is_constant_evaluated()` ([[P0595R2]]), the more intuitive semantics would have been to tell you whether the code is currently executing at compile time. But that can't be specified: the optimizer can fold any run-time computation into a constant, and whether something executes at compile time varies with the optimization level. So it observes a property determined by the language: whether the current evaluation is manifestly constant-evaluated, or is inside such an evaluation. The price is the counterintuitive cases above.

C++23's `if consteval` ([[P1938R3]]) observes the same property, and its first branch is an immediate function context ([[expr.const.imm]]). Today the specification of `is_constant_evaluated()` is simply `if consteval { return true; } else { return false; }` ([[meta.const.eval#1]]).

!!! pitfall "Three misuses of `is_constant_evaluated()`"
    1. `if constexpr (std::is_constant_evaluated())`: the condition is manifestly constant-evaluated (¶1.2) and always true.
    2. `constexpr bool b = std::is_constant_evaluated();`: the initializer is manifestly constant-evaluated, the result is always true, and it tells you nothing.
    3. `const int a = std::is_constant_evaluated() ? runtime() : 1;`: after the trial fails, it gets 1 at run time, not the result of `runtime()`.

    `is_constant_evaluated()` belongs in the body of a constexpr function, switching between a compile-time and a run-time implementation of the same algorithm, and the two branches should compute the same result.

## Potentially constant evaluated and needed for constant evaluation (¶2)

These two definitions decide when constexpr functions are instantiated. First, a comparison:

<div class="compare" markdown="1">

```cpp run ok
template<class T>
constexpr int f() { return T::value; }

// unevaluated operand: f<int> is not instantiated
decltype(f<int>()) x = 0;
```

```cpp run error
template<class T>
constexpr int f() { return T::value; }

// must decide whether int → char narrows
using A = decltype(char{f<int>()});
// error: instantiating f<int> fails
```

</div>

On both sides `f<int>()` is inside `decltype` and not odr-used. The difference on the right is that it is an immediate subexpression of a braced list. Whether `int` to `char` narrows in list-initialization depends on whether the source value is a representable constant ([[dcl.init.list]]), so the compiler must instantiate `f<int>` and try to evaluate it.

¶2 An expression or conversion is **potentially constant evaluated** if it is:

- ¶2.1 a manifestly constant-evaluated expression;
- ¶2.2 a potentially-evaluated expression ([[basic.def.odr]]);
- ¶2.3 an immediate subexpression of a *braced-init-list* (footnote 64: constant evaluation can be necessary to determine whether a conversion is narrowing);
- ¶2.4 an expression of the form `& cast-expression` that occurs within a templated entity (footnote 65: constant evaluation can be necessary to determine whether it is value-dependent; see [[temp.dep.constexpr]]);
- ¶2.5 a potentially-evaluated subexpression of any of the above.

A function or variable is **needed for constant evaluation** ([[g:needed-for-constant-evaluation|needed for constant evaluation]]) if it is:

- ¶2.6 a constexpr function named by a potentially constant evaluated expression;
- ¶2.7 a potentially-constant variable ([[expr.const.init#6]]: a constexpr variable, or a variable of reference, const integral or const enumeration type) named by a potentially constant evaluated expression.

[[temp.inst]] uses these definitions to specify that a constexpr function template specialization needed for constant evaluation is implicitly instantiated even if it is not odr-used; defaulted special member functions and variable templates are implicitly defined or instantiated under the same conditions.

Instantiation is not an inconsequential implementation detail. It can trigger hard errors (as in the example above), instantiate further templates, and, with tricks like friend injection, even change the meaning of later code. So the standard must specify precisely which expressions cause instantiation; odr-use alone is not enough.

## Constant destruction (¶3)

The destruction of a constexpr variable must also be possible at compile time. ¶3 An object a has **constant destruction** ([[g:constant-destruction|constant destruction]]) in two cases:

- ¶3.1 it is not of class type nor a (possibly multidimensional) array thereof; or
- ¶3.2 it is of class type or a (possibly multidimensional) array thereof, that class type has a constexpr destructor, and for a hypothetical expression E whose only effect is to destroy a, E would be a core constant expression if the lifetime of a and its non-mutable subobjects were considered to start within E.

[[dcl.constexpr#6]] requires constexpr variables, and the temporaries that constexpr references are bound to, to have constant destruction.

```cpp
int g;
struct T { int* p; constexpr ~T() { *p = 0; } };
constexpr T t{&g};    // error: the destructor modifies g, whose lifetime does not start within E

struct T2 { int v; constexpr ~T2() { v = 0; } };
constexpr T2 t2{1};   // OK: only modifies its own non-mutable member

struct M { mutable int v; constexpr ~M() { v = 0; } };
constexpr M m{1};     // error: mutable members are not considered to start within E

struct ND { int v; ~ND() {} };
constexpr ND nd{1};   // error: the destructor is not constexpr, ND is not a literal type
```

Once C++20 allowed constexpr destructors ([[P0784R7]]), a destructor could do anything constexpr allows. If it modifies an outside object, the compiler can't simulate that at compile time. ¶3.2 considers the lifetime of a to start within E, so the destructor may modify a's own members; after all, a is being destroyed.

Mutable members are the exception. The mutable members of a constexpr object can be modified at run time, and the compiler doesn't know their values at destruction during translation, so as soon as the destructor reads or writes one, the object doesn't have constant destruction. Clang 23 also reports "must have constant destruction" for a destructor that only reads a mutable member.

Constant destruction also blocks dynamic memory from crossing between compile time and run time:

```cpp
struct Owner {
  int* p;
  constexpr Owner() : p(new int(1)) {}
  constexpr ~Owner() { delete p; }
};
constexpr int use() { return *Owner().p; }  // OK: allocated and freed within the same evaluation
static_assert(use() == 1);
constexpr Owner o;   // error: the allocated memory is not freed within the evaluation of the initialization
```

`o` fails one step earlier: the memory allocated by its initializer is not freed within that evaluation, so the initializer is not a constant expression ([[expr.const.core#2.20]]).

!!! note "Constant destruction and program termination"
    Objects with static storage duration and constant destruction are destroyed after all other static objects and the functions registered with `atexit`, outside the ordinary ordering rules for destruction ([[basic.start.term#3]]). Their destruction has no observable effects, so the compiler can skip registering the destructor altogether: Clang 23 generates no `__cxa_atexit` call for `t2` above, even at `-O0`. A `constinit` variable with trivial or constant destruction avoids the static destruction order problem entirely.

## History and evolution

!!! history
    - C++11–17 had only the syntactic contexts of constant expressions and no `is_constant_evaluated`, so there was no need to define manifest constant evaluation precisely. The timing of instantiation was determined by odr-use and a few special cases.
    - C++20: [[P0595R2]] introduced `std::is_constant_evaluated()` and manifest constant evaluation; [[P0784R7]] allowed constexpr destructors and introduced constant destruction along with them. "Potentially constant evaluated" and "needed for constant evaluation" also took shape in this period, to specify instantiation.
    - C++23: [[P1938R3]] introduced `if consteval`.
    - C++26: consteval blocks were added (¶1.3); contract assertions are ignored during the trial evaluation for constant initialization.

## Questions

!!! question "Question 1"
    What are the values of the three variables below? Are they statically or dynamically initialized?

    ```cpp
    #include <type_traits>
    constexpr int pick() { return std::is_constant_evaluated() ? 1 : 2; }
    int rt = 0;
    int u = pick();
    int v = pick() + rt;
    const int w = pick() + 0 * rt;
    ```

<details markdown="1">
<summary>Answer</summary>

- `u`: the trial of `pick()` succeeds with 1, so it is statically initialized and `u == 1`.
- `v`: the trial fails reading `rt`, so it is dynamically initialized; at run time `pick()` returns 2 and `v == 2`.
- `w`: `0 * rt` still reads `rt`, so the trial fails and it is dynamically initialized; `w == 2`, and `w` cannot be used in constant expressions.

Any non-constant read anywhere in the initializer makes the whole initialization dynamic, which changes the result of `is_constant_evaluated()`. Running it with Clang 23 prints `1 2 2`.
</details>

!!! question "Question 2"
    Why does the definition of constant destruction not consider the lifetime of mutable subobjects to start within E?

<details markdown="1">
<summary>Answer</summary>

The mutable members of a constexpr object are not constants: the program can modify them at run time through a const reference, which is exactly what mutable is for. When the compiler simulates destruction during translation, it doesn't know the value a mutable member will have at the end of the run; if the destructor were allowed to read or write it, the destruction simulated at compile time could differ from the real one. So the standard treats mutable subobjects as outside objects: if the destructor reads or writes one, the object doesn't have constant destruction.
</details>
