---
title: Compound expressions
summary: A map of every expression that combines subexpressions with operators, ordered by precedence from tightest to loosest, and the provisions to look for when reading each operator's subclause.
updated: 2026-10-19
---

!!! tldr
    - The order of the subclauses of 7.6 is the precedence order of the built-in operators: the earlier, the tighter the binding.
    - Postfix expressions (7.6.1) are the tightest layer: function calls, member access, subscripting, postfix increment, the four named casts and functional casts are all here.
    - The C-style cast `(T)e` is not in the postfix layer; it has its own place in 7.6.3, between the unary operators and `.*`.
    - Every operator subclause specifies the same few things: operand requirements, the type and value category of the result, evaluation order, and which cases are UB.
    - 7.6 describes built-in operators. When an operand has class or enumeration type, an operator may become a function call, but the evaluation order still follows the built-in operator's rules.

```cpp run ok
int main() {
  int a[] = {1, 2, 3};
  int* p = a;
  int x = *p++;     // *(p++): postfix ++ binds tighter than unary *
  int y = -a[1];    // -(a[1]): subscripting binds tighter than unary -
  return x + y;     // 1 + (-2)
}
```

Why is `*p++` `*(p++)`? The standard has no precedence table. Precedence comes from the grammar: the operand of postfix `++` can only be a postfix-expression, while the operand of unary `*` can be anything from a tighter layer, so `*p++` has only one parse, `*` applied to the postfix-expression `p++` (see the [[expr]] overview). **Compound expressions** is the umbrella name of section 7.6 for all expressions that combine subexpressions with operators; its subclauses are ordered by this grammatical layering from tightest to loosest. 7.6 itself has no normative text.

## A map of 7.6

| Subclause | Layer (nonterminal) | Form | Note on this site | Key points |
|---|---|---|---|---|
| 7.6.1 | *postfix-expression* | Overview | [[expr.post]] | Postfix operators group left to right |
| 7.6.1.2 | | `a[b]` | [[expr.post]] | Built-in subscripting is just `*((a)+(b))`; multiple arguments since C++23 |
| 7.6.1.3 | | `f(args)` | [[expr.call]] | Evaluation order, initialization and destruction of parameters, variadic arguments, contracts |
| 7.6.1.4 | | `T(x)` `T{x}` `auto(x)` | [[expr.type.conv]] | With a single parenthesized argument, equivalent to a C-style cast |
| 7.6.1.5 | | `a.b` `a->b` | [[expr.ref]] | Type and value category of the result, combining cv, `mutable` |
| 7.6.1.6 | | `a++` `a--` | [[expr.post]] | The result is a prvalue of the old value |
| 7.6.1.7 | | `dynamic_cast` | [[expr.dynamic.cast]] | Polymorphic conversion with a runtime check |
| 7.6.1.8 | | `typeid` | [[expr.typeid]] | Takes the dynamic type of a polymorphic glvalue |
| 7.6.1.9 | | `static_cast` | [[expr.static.cast]] | Implicit conversions and their inverses, downcasts, `void*` |
| 7.6.1.10 | | `reinterpret_cast` | [[expr.reinterpret.cast]] | Pointer–integer conversions, pointers between unrelated types |
| 7.6.1.11 | | `const_cast` | [[expr.const.cast]] | Changes only cv-qualification |
| 7.6.2 | *unary-expression* | `*a` `&a` `-a` `!a` `~a` `++a` `sizeof` `alignof` `noexcept` `new` `delete` `co_await` `^^` | [[expr.unary]] | Unary operators, right-associative |
| 7.6.3 | *cast-expression* | `(T)e` | [[expr.cast]] | Tries combinations of the named casts in turn |
| 7.6.4 | *pm-expression* | `.*` `->*` | [[expr.mptr.oper]] | Pointer-to-member operations |
| 7.6.5–7.6.6 | *multiplicative / additive* | `* / %`, `+ -` | [[expr.mul]], [[expr.add]] | Arithmetic; pointer arithmetic |
| 7.6.7 | *shift-expression* | `<< >>` | [[expr.shift]] | Since C++17 the left operand is sequenced before the right |
| 7.6.8 | *compare-expression* | `<=>` | [[expr.spaceship]] | Three-way comparison (C++20) |
| 7.6.9–7.6.10 | *relational / equality* | `< > <= >=`, `== !=` | [[expr.rel]], [[expr.eq]] | Unspecified cases in pointer comparison |
| 7.6.11–7.6.13 | | `& ^ \|` | [[expr.bit.and]], [[expr.xor]], [[expr.or]] | Bitwise operations |
| 7.6.14–7.6.15 | | `&& \|\|` | [[expr.log.and]], [[expr.log.or]] | Short-circuit evaluation, left sequenced before right |
| 7.6.16 | *conditional-expression* | `a ? b : c` | [[expr.cond]] | Common type and value category of the second and third operands |
| 7.6.17 | *yield-expression* | `co_yield` | [[expr.yield]] | Coroutine yield |
| 7.6.18 | *throw-expression* | `throw` | [[expr.throw]] | Throwing an exception |
| 7.6.19 | *assignment-expression* | `= += -= …` | [[expr.assign]] | Since C++17 the right operand is sequenced before the left |
| 7.6.20 | *expression* | `a, b` | [[expr.comma]] | Left sequenced before right; the result is the right operand |

### Why the C-style cast comes later on its own

The four named casts carry their own parentheses; syntactically `static_cast<T>(e)` is a postfix expression just like a function call, so it lives in 7.6.1. The functional cast `T(x)` is also a postfix expression. The C-style `(T)e`, however, is a *cast-expression* whose operand is another *cast-expression*; it binds looser than the unary operators and tighter than `.*`, so it is placed in 7.6.3.

```cpp run ok
struct S { int m; };
int main() {
  S s{1};
  S* p = &s;
  long n = (long)p->m;   // (long)(p->m): -> binds tighter than the cast
  return static_cast<int>(n) - 1;
}
```

For a side-by-side comparison of all the casts, see [[topics/casts]].

## What each operator subclause specifies

The subclauses under 7.6 are written in a similar way; each one answers the following:

1. Operand requirements: glvalue or prvalue, whether a complete type is needed, which standard conversions ([[conv]]) are applied to the operands.
2. The result: type, value category ([[basic.lval]]), whether it is a bit-field.
3. Evaluation order: whether the operands are sequenced, indeterminately sequenced or unsequenced ([[intro.execution]]). C++17 added ordering for subscripting, shifts, assignment, member access and other operators.
4. Undefined, unspecified and implementation-defined cases.

## Relation to operator overloading

If an operand has class or enumeration type, `a + b` may be interpreted as a call `operator+(a, b)` ([[expr.pre#2]], [[over.match.oper]]). The type and value category of the result are then determined by the rules for function calls ([[expr.call]]), not by [[expr.add]].

Evaluation order is the exception. Since C++17, when an overloaded operator is invoked with operator notation, the operands are evaluated in the order specified for the built-in operator ([[expr.call#8]] Note 8). So in `std::cout << f() << g()`, `f()` is always evaluated before `g()`. Overloaded `&&` and `||` also evaluate the left operand first, but both operands are evaluated; there is no short-circuiting.

```cpp run ok
#include <cstdio>
#include <sstream>
int f() { std::puts("f"); return 1; }
int g() { std::puts("g"); return 2; }
int main() {
  std::ostringstream os;
  os << f() << g();   // prints f first, then g (guaranteed since C++17)
}
```
