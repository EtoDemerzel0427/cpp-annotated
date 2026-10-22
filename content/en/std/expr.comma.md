---
title: Comma operator
summary: "a, b first evaluates and discards a, then evaluates b, and the result takes its type, value and value category from b; the commas between function arguments are not this operator; overloaded commas and the void() defensive idiom; since C++23 a comma inside a subscript means a multidimensional subscript."
updated: 2026-10-19
---

!!! tldr
    - `a, b` first evaluates `a` completely and discards its result, then evaluates `b`; all side effects of `a` complete before `b` begins.
    - The type, value and value category of the result all come from the right operand, so `(a, b) = 5` assigns to `b`.
    - Commas between function arguments, in initializer lists and between template arguments are separators, not the comma operator, and guarantee no order.
    - The comma can be overloaded. Generic code writes `void(f(x)), g(y)`, making the left operand `void`, so that a user's `operator,` is never picked up.
    - Since C++23 `a[i, j]` is a multidimensional subscript, ill-formed for built-in arrays and pointers; to use the comma operator, write `a[(i, j)]`.

## The rule (¶1)

```cpp run title="comma-basics.cpp" ok
#include <type_traits>
#include <utility>

int a = 1, b = 2;
static_assert(std::is_same_v<decltype((a, b)), int&>);              // the right operand is an lvalue
static_assert(std::is_same_v<decltype((a, 3)), int>);               // prvalue
static_assert(std::is_same_v<decltype((a, std::move(b))), int&&>);  // xvalue

int main() {
    (a, b) = 5;                 // OK: the result is the lvalue b itself
    int i = 0;
    int r = (i++, i++, i);      // OK: completed one by one from left to right, r == 2
    return (b == 5 && r == 2) ? 0 : 1;
}
```

¶1 The comma operator groups left-to-right and is also evaluated left to right:

- The left operand is a **discarded-value expression** ([[g:discarded-value-expression]]): it is evaluated only for its side effects, and its result is discarded ([[expr.context#2]]).
- The left operand is **sequenced before** ([[g:sequenced-before]]) the right operand: the right side begins only after all value computations and side effects of the left side have completed ([[intro.execution]]).
- The type and value of the result are those of the right operand, and the value category is the same as the right operand's; if the right operand is a bit-field, the result is a bit-field.

So `(i++, i++, i)` is defined, while `i++ + i++` is UB: the comma specifies an order and `+` doesn't ([[intro.execution#10]]).

In C, the result of a comma expression is never an lvalue. C++ keeps the value category of the right operand, so a comma expression can appear transparently where an lvalue is needed, for example `(check(), obj).member = v` produced by a macro expansion.

When the left operand has no effect, Clang and GCC give a `-Wunused-value` warning. That warning often catches mistakes such as writing `a[i, j]` for `a[i][j]`.

## Which commas are the operator (¶2)

```text
expression:
    assignment-expression
    expression , assignment-expression
```

The nonterminal *expression* is itself the comma expression. Where the grammar requires an *expression*, such as inside parentheses, the middle operand of the conditional operator, or the parts of a `for`, the comma operator can appear directly; where only an *assignment-expression* is required, such as function arguments and initializers, it cannot.

Note 1 of ¶2 explains that in contexts where the comma has another meaning, namely function calls ([[expr.call]]), subscripts ([[expr.sub]]), initializer lists ([[dcl.init]]) and template argument lists ([[temp.names]]), the comma operator can appear only in parentheses:

```cpp run title="comma-context.cpp" ok
int f(int a, int b, int c) { return a * 100 + b * 10 + c; }

int main() {
    int a = 1, t = 0, c = 3;
    int r = f(a, (t = 3, t + 2), c);   // three arguments, the second is 5
    return r == 153 ? 0 : 1;
}
```

The commas between function arguments are not the comma operator, so there is no left-to-right guarantee between arguments. Since C++17, the evaluations of arguments are indeterminately sequenced with respect to each other ([[expr.call]]): `f(i++, i++)` is no longer UB, but which is evaluated first is unspecified.

### Commas in subscripts {{removed:C++23}}

Before C++20, `a[i, j]` was just `a[(i, j)]`, i.e. `a[j]`, which was almost always a typo. C++20's [[P1161R3]] deprecated unparenthesized comma expressions in subscripts; C++23's [[P2128R6]] turned that syntax into a multidimensional subscript: `a[i, j]` calls `a.operator[](i, j)` ([[over.sub]]), which is what `m[i, j]` on `std::mdspan` relies on. The brackets of a built-in subscript must contain exactly one expression:

```cpp title="comma-subscript.cpp" error
int main() {
    int arr[3]{};
    int x = arr[1, 2];      // error: a built-in subscript accepts only one expression (since C++23)
    int y = arr[(1, 2)];    // OK: a parenthesized comma expression, i.e. arr[2]
    return x + y;
}
```

See [[diff.cpp20.expr]].

## Overloaded comma

The comma operator can be overloaded ([[over.binary]]). Once overloaded, it is an ordinary function call. Before C++17, the evaluation order of the two arguments was unspecified, and the comma's ordering guarantee disappeared with it; since C++17, [[over.match.oper#2]] specifies that an overloaded operator invoked with operator syntax evaluates its operands in the order of the corresponding built-in operator, so an overloaded comma is also left before right ([[P0145R3]]).

The ordering problem is solved, but the problem of accidental calls remains. In generic code, if the return type of `f(x)` can find an `operator,` through ADL, `f(x), g(y)` calls it. Converting the left operand to `void` avoids this: an operand of type `void` can never match any user-defined `operator,`.

```cpp run title="comma-overload.cpp" ok
#include <cstdio>

struct Evil {
    template<class T>
    friend Evil operator,(Evil, T) { std::puts("evil comma called"); return {}; }
};
Evil make() { return {}; }

int main() {
    make(), 1;          // calls the overloaded operator, (prints once)
    void(make()), 1;    // built-in comma: the left operand is void
}
```

That is why forms like `++first1, (void)++first2` are common in the algorithm implementations of libc++ and libstdc++.

## Commas in fold expressions

The unary fold `(E, ...)` expands over the comma into the form `E1, (E2, (E3, ...))` ([[expr.prim.fold]]), so each pack element is evaluated in order. In C++17, this is the standard way to call a function once per argument:

```cpp run title="comma-fold.cpp" ok
#include <cstdio>

template<class... Ts>
void print_all(const Ts&... xs) {
    (void(std::printf("%d ", xs)), ...);   // prints in argument order; void() guards against an overloaded comma
    std::puts("");
}

int main() { print_all(1, 2, 3); }   // prints 1 2 3
```

For an empty pack, `(E, ...)` expands to `void()`.

## Common misconceptions

!!! pitfall "Thinking `return a, b;` returns two values"
    It returns `b`. For multiple values, use `std::pair`, `std::tuple` or a struct.

!!! pitfall "Thinking the comma in `int x = 1, y = 2;` is the comma operator"
    Here it separates declarators, declaring two variables.

## Questions

!!! question "Question"
    What is the structure of `x = 1, y = 2;` as an expression statement? What is `z` in `int z = (x = 1, y = 2);`? And without the parentheses?

<details markdown="1">
<summary>Answer</summary>

The comma in `x = 1, y = 2;` is the comma operator. Assignment has higher precedence than the comma, so it is `(x = 1), (y = 2)`.

In `int z = (x = 1, y = 2);` the parentheses contain a comma expression whose result is that of the right operand `y = 2`, i.e. `y` with value 2, so `z == 2`.

Without the parentheses, `int z = x = 1, y = 2;` becomes a declaration: `z` is initialized with the value 1 of `x = 1`, and then a new variable `y` is declared. If there is already a `y` in the same scope, that is a redefinition, and the program is ill-formed.
</details>

## Summary

| Aspect | Rule |
|---|---|
| Evaluation | Left to right; left sequenced before right, including all side effects |
| Left operand | Discarded-value expression |
| Result | Type, value, value category and bit-field-ness all from the right operand |
| In arguments, initializers, template arguments | The comma is a separator; the comma operator needs parentheses |
| Comma in a subscript | Deprecated in C++20; a multidimensional subscript since C++23, ill-formed for built-in subscripts |
| Overloading | Ordinary function call; still left before right since C++17; guard with `void()` |
