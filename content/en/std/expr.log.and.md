---
title: Logical AND and logical OR operators
summary: "&& and || contextually convert their operands to bool, evaluate the left operand first, and don't evaluate the right operand once the result is determined; overloaded versions lose short-circuiting; short-circuiting affects only evaluation and cannot prevent template instantiation; in constraints, && and || are conjunction and disjunction."
updated: 2026-10-19
---

!!! tldr
    - `&&` and `||` contextually convert both operands to `bool`, so smart pointers with an `explicit operator bool` and `std::optional` can be used directly as operands.
    - The left operand is evaluated first, and its side effects are complete before the right operand begins; when the left side of `&&` is false or the left side of `||` is true, the right side is not evaluated. That is short-circuit evaluation.
    - Overloaded `&&` and `||` are ordinary function calls, and both sides are evaluated; since C++17 the only guarantee is that the left side comes before the right.
    - Short-circuiting affects evaluation, not compilation: an unevaluated right operand must still be well-formed, and `std::is_class_v<T> && T::value` does not protect `T::value`.
    - In constraint expressions, `&&` and `||` are the conjunction and disjunction of constraints; when the left side is not satisfied, no substitution is performed on the right side. That is a separate set of rules.

```cpp run title="logand-guard.cpp" ok
#include <cstddef>

int find(const int* a, std::size_t n, int x) {
    std::size_t i = 0;
    while (i < n && a[i] != x) ++i;   // when i == n, a[n] is never read
    return i < n ? int(i) : -1;
}

int main() {
    int a[3] = {4, 5, 6};
    return find(a, 3, 6) == 2 && find(a, 3, 7) == -1 ? 0 : 1;
}
```

Check-then-access patterns such as `i < n && a[i] != x` and `p && p->ok()` all rely on what [[expr.log.and]] (`&&`) and [[expr.log.or]] (`||`) specify: [[g:short-circuit-evaluation|short-circuit evaluation]]. The two subclauses are symmetric, with two paragraphs each.

## Short-circuiting (¶1)

!!! std
    Unlike &, && guarantees left-to-right evaluation: the second operand is not evaluated if the first operand is false.

¶1 `&&` evaluates left to right: if the first operand is `false`, the second operand is not evaluated. `||` is symmetric: if the first operand is `true`, the second is not evaluated. Both group left-to-right, so `a && b && c` is `(a && b) && c`, and a chain of `&&` checks each operand from left to right, stopping at the first `false`.

The result of `&&` is true if and only if both operands are true; the result of `||` is true if and only if at least one is true.

### Contextual conversion to `bool`

Both operands are **contextually converted to `bool`** ([[conv]]), i.e. converted as in the direct-initialization `bool t(e);`. Direct-initialization considers `explicit` conversion functions, so smart pointers, `std::optional` and stream objects can be used directly as operands, just as in the condition of an `if`:

```cpp run title="logand-contextual.cpp" ok
#include <memory>
#include <optional>

struct Flag { explicit operator bool() const { return true; } };

int main() {
    auto p = std::make_unique<int>(42);
    std::optional<int> o = 7;
    Flag f;
    bool ok = p && *p == 42 && o && f;   // each operand is contextually converted to bool
    // bool b = f;                       // error: copy-initialization doesn't consider explicit conversion functions
    return ok ? 0 : 1;
}
```

## Result type and ordering (¶2)

¶2 The result type is `bool`. If the second operand is evaluated, the first operand is **sequenced before** it ([[intro.execution#8]]): every value computation and side effect of the first operand completes before any evaluation of the second operand begins. So the following code is well-defined:

```cpp run title="logand-sequencing.cpp" ok
int main() {
    int i = 0;
    bool r = (i++ == 0) && (i == 1);   // the side effect of i++ completes before the second i is read
    int j = 0;
    bool s = (j = 5) || (j = 6);       // the second assignment is not executed
    return (r && s && j == 5) ? 0 : 1;
}
```

C++98 expressed the same thing as a sequence point after the first operand; since C++11 it is described with the sequenced-before relation (see [[topics/order-of-evaluation]]). The bitwise operators `&` and `|` have no such guarantee: the evaluations of their two operands are unsequenced ([[expr.bit.and]]).

## Overloading loses short-circuiting

`&&` and `||` can be overloaded ([[over.binary]]), but an overloaded version is an ordinary function call: both arguments are evaluated before the call, so short-circuiting is gone.

```cpp run title="logand-overload.cpp" ok
#include <cstdio>

struct B {
    bool v;
    friend B operator&&(B a, B b) { return {a.v && b.v}; }
};

B make(bool v, const char* name) { std::printf("eval %s\n", name); return {v}; }

int main() {
    B r = make(false, "left") && make(true, "right");
    // prints eval left and eval right: the right operand is evaluated anyway
    return r.v ? 1 : 0;
}
```

Before C++17 even the order of left and right was not guaranteed, because the order among function arguments is unspecified. Since C++17's [[P0145R3]], [[over.match.oper#2]] specifies that when an overloaded operator is invoked with operator syntax, the operands are evaluated in the order of the corresponding built-in operator, so the left side still comes before the right, but both sides are evaluated.

Because the call site gives no hint that the semantics have changed, most coding guidelines advise against overloading `&&`, `||` and the comma. The only reasonable uses are domain-specific languages such as expression templates, for example for building query conditions; the element-wise `&&` of `std::valarray<bool>` belongs to this category too, where short-circuiting has no meaning anyway.

## Short-circuiting and compile time

### Constant evaluation

An operand that is not evaluated doesn't stop the expression from being constant:

```cpp title="logand-constexpr.cpp" error
int runtime_only();     // not a constexpr function

constexpr bool a = false && runtime_only();   // OK: the right operand is not evaluated
constexpr bool b = true  || runtime_only();   // OK
constexpr bool c = true  && runtime_only();   // error: evaluates a non-constexpr function
```

But an operand that is not evaluated still has to compile: names in it are looked up, types are checked, and the variables and functions it uses still count as odr-used ([[basic.def.odr]]). Short-circuiting is a concept at the level of evaluation, not compilation.

### `&&` cannot prevent instantiation

A common misuse is trying to guard a later expression with `&&` in a template:

```cpp title="logand-template.cpp" error
#include <type_traits>

template<class T>
constexpr bool has_true_value() {
    return std::is_class_v<T> && T::value;   // T::value is instantiated anyway
}

constexpr bool x = has_true_value<int>();    // error: int::value is ill-formed
```

When `has_true_value<int>` is instantiated, `int::value` must make sense, regardless of whether it would be evaluated at run time. You can use `if constexpr` ([[stmt.if]]) instead; or `std::conjunction`, which stops accessing `::value` of the remaining types after the first `false`; or a constraint:

```cpp run title="logand-concept.cpp" ok
#include <type_traits>

template<class T>
concept HasTrueValue = std::is_class_v<T> && T::value;   // conjunction of constraints

static_assert(!HasTrueValue<int>);   // the first atomic constraint is not satisfied, so the second is not checked

int main() {}
```

In a constraint expression, top-level `&&` and `||` are not operators but the **conjunction** and **disjunction** of constraints ([[temp.constr.op]]). When a conjunction is checked, the left operand is checked first, and if it is not satisfied, no template argument substitution is performed on the right operand, so `int::value` causes no error.

### Fold expressions

`(... && args)` and `(... || args)` are common unary folds. For an empty pack, a `&&` fold gives `true` and a `||` fold gives `false` ([[expr.prim.fold]]). The expansion is an ordinary chain of `&&`, so short-circuiting applies too: `(f(args) && ...)` stops calling `f` after the first `false`.

## Precedence

`&&` has higher precedence than `||`, so `a || b && c` is `a || (b && c)`. This matches Boolean algebra, where AND corresponds to multiplication and OR to addition, but mixing them is hard to read, and Clang's `-Wlogical-op-parentheses` (part of `-Wparentheses`) suggests parentheses. Both bind less tightly than bitwise `|` and more tightly than `?:` and assignment. The alternative tokens are `and` and `or` ([[lex.digraph]]).

!!! impl
    Short-circuiting usually compiles to conditional jumps. Under the as-if rule ([[intro.abstract]]), when the right operand has no side effects, cannot fail, and is cheap, for example two integer comparisons, the compiler can compile `a && b` into a branchless `a & b` to avoid branch mispredictions. Conversely, the branchless intent expressed with `a & b` is not necessarily preserved: the optimizer may introduce a branch to skip an expensive right operand. When you need reliably branchless code, check the generated assembly.

## Common misconceptions

!!! pitfall "Overloaded `&&` short-circuits too"
    Once overloaded, both sides are evaluated. C++17 only guaranteed the order; it did not restore short-circuiting.

!!! pitfall "`a || b && c` is `(a || b) && c`"
    `&&` has higher precedence.

!!! pitfall "Replacing `&&` with `&` for performance"
    Without short-circuiting, a right operand that relies on a check in the left operand can go wrong, for example with a null pointer or an out-of-bounds index; and the evaluations of the two sides become unsequenced.

## Questions

!!! question "Question 1"
    In `bool r = f() || g() && h();`, which functions are called if `f()` returns `true`?

<details markdown="1">
<summary>Answer</summary>

The expression parses as `f() || (g() && h())`. When `f()` is `true`, the entire right operand `g() && h()` is not evaluated, so only `f()` is called.
</details>

!!! question "Question 2"
    Given an overloaded `B operator&&(B, B);`, is the order of the two calls in `make("left") && make("right")` guaranteed in C++14? In C++17?

<details markdown="1">
<summary>Answer</summary>

C++14: `a && b` is rewritten as the function call `operator&&(a, b)`, and the evaluation order of the two arguments is unspecified; no guarantee.

C++17: [[over.match.oper#2]] specifies that the operands are evaluated in the order of the built-in operator, and built-in `&&` is left before right, so `make("left")` comes before `make("right")`, but both are called. If you write `operator&&(make("left"), make("right"))` explicitly, this rule doesn't apply, and the two arguments are still only indeterminately sequenced ([[expr.call]]).
</details>

## Summary

| Aspect | `&&` | `\|\|` |
|---|---|---|
| Operands | Contextually converted to `bool` | Same |
| Short-circuiting | Right side not evaluated if left is `false` | Right side not evaluated if left is `true` |
| Order | If the right side is evaluated, the left is sequenced before it | Same |
| Result | `bool` | `bool` |
| When overloaded | No short-circuiting; still left before right since C++17 | Same |
| In constraints | Conjunction | Disjunction |
