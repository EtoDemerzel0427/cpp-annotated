---
title: Constant evaluation
summary: "An overview of subclause 7.7: what core constant expressions, constant expressions, manifest constant evaluation, constant initialization and immediate functions each cover; constant evaluation performs no optional copy elision, and floating-point results may differ from run time; how constexpr was relaxed from C++11 to C++26."
updated: 2026-10-19
---

!!! tldr
    - The standard doesn't define a constant expression positively; it gives a list of prohibitions instead: an expression whose evaluation runs into nothing on the list is a core constant expression.
    - Whether something is a constant expression is a property of the expression; whether it is evaluated at compile time is a matter of timing. Only manifestly constant-evaluated contexts (array bounds, template arguments, initializers of `constexpr` variables and so on) tie the two together.
    - Constancy is judged assuming no optional copy elision is performed, so NRVO never happens in constant evaluation.
    - Whether the same floating-point expression gives the same result at compile time and at run time is unspecified.
    - Core-language undefined behavior during constant evaluation makes the expression non-constant and the compiler must diagnose it; this is the only place in the language where detecting UB is mandatory.

## The structure of subclause 7.7

Some contexts require a constant expression, such as array bounds, `case` labels, template arguments and the condition of `static_assert`. In other contexts the semantics depend on whether an expression is a constant expression, such as the initialization of a global variable: if it is a constant expression, the variable is statically initialized before the program starts; otherwise it is dynamically initialized at run time. Subclause 7.7 defines these concepts in seven subclauses:

| Subclause | Contents |
|---|---|
| [[expr.const.general]] (this page) | The grammar of *constant-expression*, the copy elision assumption, floating-point consistency |
| [[expr.const.core]] | The list of prohibitions for core constant expressions (UB, `reinterpret_cast`, calling non-constexpr functions…); constexpr-unknown |
| [[expr.const.const]] | Constant expressions, integral constant expressions, converted constant expressions |
| [[expr.const.init]] | Constant initialization, variables usable in constant expressions |
| [[expr.const.imm]] | Immediate functions (`consteval`), immediate invocations, upward propagation of consteval |
| [[expr.const.reflect]] | {{c++26}} Reflection: injected declarations, evaluation contexts |
| [[expr.const.defns]] | Manifestly constant-evaluated, potentially constant evaluated, constant destruction |

## How the concepts are layered

A **core constant expression** ([[g:core-constant-expression]], [[expr.const.core#2]]) constrains the evaluation: evaluating the expression `E` according to the rules of the abstract machine does none of the things on the list of prohibitions. The list includes calling a non-constexpr function, `reinterpret_cast`, reading a variable that is neither usable in constant expressions nor has its lifetime begin within this evaluation, producing undefined behavior, and so on.

A **constant expression** ([[g:constant-expression]], [[expr.const.const#4]]) additionally constrains the result: the result must be able to leave the evaluation, with no dangling pointers and no indeterminate or erroneous values in it.

Each context then adds its own requirements:

- **Integral constant expressions** ([[expr.const.const#6]]): used for bit-field widths, `alignas` and the like.
- **Converted constant expressions** ([[g:converted-constant-expression]], [[expr.const.const#8]]): used for array bounds, `case` labels, non-type template arguments and the like; only safe implicit conversions are allowed, and narrowing is forbidden.
- The conditions of `static_assert` and `if constexpr` only need to be constant expressions after contextual conversion to `bool`; since C++23 narrowing is allowed, so `static_assert(N % 4)` is valid ([[dcl.pre#13]], [[stmt.if#2]]).

A separate line of concepts answers when evaluation happens:

- **Manifestly constant-evaluated** ([[g:manifestly-constant-evaluated]], [[expr.const.defns#1]]): expressions the language requires to be evaluated during translation. `std::is_constant_evaluated()` and `if consteval` observe exactly this property.
- **Constant initialization** ([[g:constant-initialized]], [[expr.const.init]]): when a variable with static or thread storage duration is initialized with a constant expression, the initialization happens in the static initialization phase and takes no part in the ordering of dynamic initialization ([[basic.start.static#2]]).
- **Immediate functions** ([[g:immediate-function]], [[expr.const.imm]]): functions every call of which must be evaluated at compile time, namely `consteval` functions, as well as constexpr function template specializations and the like that are forced to become immediate because they call one.

## Grammar and definition (¶1)

```text
constant-expression:
    conditional-expression
```

Grammatically, a *constant-expression* is a *conditional-expression*, which excludes assignment expressions and comma expressions. So `case 1, 2:` fails at the level of the grammar; a comma expression needs parentheses, and only `int a[(1, 2)];` gets past the grammar, after which the semantic rules decide whether it is constant.

¶1 adds a premise when defining constant expressions:

!!! std
    Expressions that satisfy these requirements, assuming that copy elision is not performed, are called constant expressions.

### Property versus timing

Note 1 says that some constant expressions are evaluated during translation, not all of them. In `int n = sq(3);`, `sq(3)` is a constant expression, but the standard doesn't require it to be computed at compile time; in `int a[sq(3)];`, `sq(3)` is an array bound and must be evaluated at compile time.

```cpp run ok
constexpr int sq(int x) { return x * x; }

int main() {
    int a[sq(3)];          // array bound: must be evaluated during translation
    int n = sq(3);         // ordinary initialization: a constant expression, evaluated whenever the implementation decides
    static_assert(sizeof a == 9 * sizeof(int));
    return n - 9;
}
```

### No optional copy elision

Whether optional copy elision such as NRVO ([[class.copy.elision]]) happens at run time is up to the implementation. If constancy depended on it, the same code could be constant on one compiler and not on another. So paragraph 1 says constancy is judged assuming no copy elision, and [[dcl.constexpr#4]] repeats that copy elision is not performed in a constant expression. The copy or move that could have been elided is always called in constant evaluation, and it must be constexpr too.

```cpp run ok
struct C {
    int copies = 0;
    constexpr C() = default;
    constexpr C(const C& o) : copies(o.copies + 1) {}
};

constexpr C make() {
    C c;          // named local variable
    return c;     // at run time: NRVO may or may not happen; in constant evaluation: never
}

static_assert(make().copies == 1);   // always copied once in constant evaluation

int main() {
    C rt = make();
    return rt.copies;                 // 0 or 1, depending on NRVO; 0 with Clang at -O0 in our tests
}
```

The mandatory elision since C++17 when a prvalue initializes an object of the same type is not optional elision, and it still happens in constant evaluation.

## Floating-point: compile time and run time may disagree (¶2)

¶2 is a recommended practice: implementations should give consistent results for floating-point operations during translation and at run time. Note 2 adds that the standard places no requirements on floating-point accuracy, so whether the same floating-point expression gives the same result at the two times is **unspecified**. The standard's example:

```cpp unspecified
bool f() {
    char array[1 + int(1 + 0.2 - 0.1 - 0.1)];   // must be evaluated during translation
    int size = 1 + int(1 + 0.2 - 0.1 - 0.1);    // may be evaluated at run time
    return sizeof(array) == size;               // true or false: unspecified
}
```

Whether `1 + 0.2 - 0.1 - 0.1` comes out slightly less than 1 or exactly 1 depends on the precision of intermediate results: x87 80-bit extended precision, `-ffast-math` and FMA contraction can all change it.

!!! impl
    GCC and Clang both emulate IEEE rounding in the target format when constant folding, and with the default options on x86-64 using SSE2, compile-time and run-time results usually agree. Disagreements arise mainly when: 32-bit x86 uses x87 arithmetic; `-ffast-math` or `-ffp-contract=fast` is enabled and the run-time code may use FMA; or the rounding mode is changed at run time with `fesetround`, while constant evaluation always uses the default round-to-nearest.

## Constant evaluation is one run of the abstract machine

A C++11 constexpr function body could contain little more than a single `return`, a purely functional subset. C++14 changed the approach: instead of restricting what can be written in a function, it restricts what may be done during evaluation. Constant evaluation is the compiler internally executing the code according to the rules of the abstract machine; as long as that execution touches nothing that exists only at run time, produces no undefined behavior, and doesn't leave memory allocated at compile time for run time, it is valid.

This has two consequences.

First, a constexpr function is a function that can also run at compile time, not one that runs only at compile time. [[dcl.constexpr#4]] says that a call to a constexpr function gives the same result as a call to an equivalent non-constexpr function, except that the former can appear in constant expressions and copy elision is not performed in constant evaluation. The same `std::vector` implementation can therefore be used at both times; code that can only run at one of them is split off with `if consteval`.

Second, constant evaluation became a UB detector. [[expr.const.core#2.8]] says that an operation that would have undefined or erroneous behavior makes the expression not a core constant expression, so signed overflow, out-of-bounds access, reading uninitialized objects and dereferencing dangling pointers must all be diagnosed in constant evaluation:

```cpp error
#include <climits>
constexpr int add(int a, int b) { return a + b; }
int ok = add(INT_MAX, 1);                    // evaluated at run time: UB, no diagnostic required
constexpr int bad = add(INT_MAX, 1);         // error: overflow in constant evaluation, not a constant expression
```

## History and evolution

| Version | Change | Papers |
|---|---|---|
| C++98 | Only integral constant expressions: literals, enumerators, `const` integral variables initialized with constants, `sizeof`; no function calls | — |
| C++11 | `constexpr` variables and functions, function bodies essentially limited to one `return`; literal types | [[N2235]] |
| C++14 | constexpr functions may have local variables, loops and branches, and may modify objects whose lifetime began within the evaluation | [[N3652]] |
| C++17 | constexpr lambdas; `if constexpr` | [[P0170R1]], [[P0292R2]] |
| C++20 | constexpr virtual functions, `try` blocks, `dynamic_cast` and polymorphic `typeid`, changing the active member of a union, trivial default initialization; compile-time `new`/`delete` (must be freed within the same evaluation); `std::is_constant_evaluated()`; `consteval`; `constinit` | [[P1064R0]], [[P1002R1]], [[P1327R1]], [[P1330R0]], [[P1331R2]], [[P0784R7]], [[P0595R2]], [[P1073R3]], [[P1143R2]] |
| C++23 | `if consteval`; variables of non-literal type, `goto` and labels in constexpr functions; `static constexpr` local variables; removal of the requirement that at least one set of constant arguments exist; upward propagation of consteval; using unknown references | [[P1938R3]], [[P2242R3]], [[P2647R1]], [[P2448R2]], [[P2564R3]], [[P2280R4]] |
| C++26 | Conversions from `void*`; placement new; throwing and catching exceptions; constexpr structured bindings and constexpr references to automatic variables; static reflection and consteval blocks; erroneous behavior also makes an expression non-constant | [[P2738R1]], [[P2747R2]], [[P3068]], [[P2686]], [[P2996R13]], [[P3289]], [[P2795R5]] |

A few of these are worth knowing:

- C++20 compile-time allocation must be freed within the same evaluation ([[expr.const.core#2.20]]). This is the foundation of constexpr `std::vector` and `std::string`, and also the reason you still can't declare a non-empty `constexpr std::vector` global variable.
- In C++20 and earlier, if no arguments existed for which a call to a constexpr function could be a constant expression, the program was ill-formed, no diagnostic required. The rule was hard to check and conflicted with splitting code using `std::is_constant_evaluated()`, so C++23's [[P2448R2]] removed it. Now [[dcl.constexpr#3]] only requires a non-template constexpr function not to be a coroutine.
- In C++20, calling `template<class T, size_t N> constexpr size_t size(T(&)[N])` with a reference parameter was, surprisingly, not a constant expression, because the reference itself had to be read. [[P2280R4]] fixed this by introducing constexpr-unknown ([[g:constexpr-unknown]]), applied retroactively to earlier standards as a defect report.

## Common misconceptions

!!! pitfall "Thinking constexpr means computed at compile time"
    `constexpr int f(int);` only says that `f` can be called in constant expressions. When `f(3)` in `int x = f(3);` is evaluated is up to the implementation; at `-O0` it is usually a real call. To force compile-time evaluation, put the result into a `constexpr` or `constinit` variable, a template argument or a `static_assert`, or declare `f` `consteval`.

!!! pitfall "Thinking the value of a constant expression is known at compile time"
    `constexpr int* p = &global;` is a constant expression, but the numeric value of `p` can't be known before linking or loading. The value of a constant expression can be a symbolic address ([[expr.const.const]]).

## Questions

!!! question "Question 1"
    Does the following `static_assert` pass? What happens if the copy constructor is made non-constexpr?

    ```cpp
    struct C {
        int n = 0;
        constexpr C() = default;
        constexpr C(const C& o) : n(o.n + 1) {}
    };
    constexpr C id(C c) { return c; }
    static_assert(id(C{}).n == 1);
    ```

<details markdown="1">
<summary>Answer</summary>

It passes. `C{}` is a prvalue, and using it to initialize the parameter `c` is mandatory elision, without calling the copy constructor. `return c;` returns a parameter, and NRVO cannot apply to parameters; `C` has a user-declared copy constructor and no move constructor, so it is copied once and `n` becomes 1.

If the copy constructor is made non-constexpr, the evaluation calls a non-constexpr function ([[expr.const.core#2.3]]), the condition of the `static_assert` is not a constant expression, and the program is ill-formed. Whether this copy would be optimized away at run time is irrelevant: paragraph 1 says constancy is judged assuming no copy elision.
</details>

!!! question "Question 2"
    What is the difference between `int a[(1, 2)];` and `int b[1, 2];`?

<details markdown="1">
<summary>Answer</summary>

The grammar for an array bound is *constant-expression*, i.e. *conditional-expression*. `1, 2` is a comma expression, not a *conditional-expression*, so `int b[1, 2];` is a syntax error. `(1, 2)` is a parenthesized primary expression, which is fine grammatically, and the comma expression is not on the list of prohibitions, so `int a[(1, 2)];` declares an `int[2]`; the compiler may warn about the left operand having no effect.
</details>

## Summary

| Concept | Concern | Defined in |
|---|---|---|
| Core constant expression | The evaluation avoids the list of prohibitions (including UB) | [[expr.const.core#2]] |
| Constant expression | The result can leave the evaluation (no invalid pointers, no indeterminate or erroneous values) | [[expr.const.const#4]] |
| Integral and converted constant expressions | Type and conversion constraints added by the context | [[expr.const.const#6]], [[expr.const.const#8]] |
| Constant initialization | Whether a variable with static storage duration is initialized in the static initialization phase | [[expr.const.init]] |
| Manifestly constant-evaluated | Whether the language requires evaluation during translation | [[expr.const.defns#1]] |
| Immediate function | Every call must be evaluated at compile time | [[expr.const.imm]] |
