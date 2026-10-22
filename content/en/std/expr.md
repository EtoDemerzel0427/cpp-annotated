---
title: Expressions
summary: "How Chapter 7 is organized: properties of expressions, standard conversions, the operators in order of precedence, and constant evaluation. The standard has no precedence table; precedence and associativity are derived from the grammar."
updated: 2026-10-19
---

!!! tldr
    - Chapter 7 first gives the rules that apply throughout (value categories, standard conversions, the usual arithmetic conversions), then describes the operators one by one from highest to lowest precedence, and ends with constant evaluation.
    - The standard has no operator precedence table. Each precedence level corresponds to a grammar nonterminal, and precedence and associativity are derived from the grammar.
    - The grammar has a few asymmetries: `sizeof (int)x` is a syntax error, `c ? a : b = x` is `c ? a : (b = x)`, and `throw` can be an operand of `?:`.
    - Precedence only decides how operands are grouped, not which one is evaluated first.
    - Overloaded operators keep the syntax and evaluation order of the built-in operators, but not their requirements on operand types and value categories.

What type an expression has, what its value category is, what implicit conversions happen during its evaluation, when it is UB, and whether it can be evaluated at compile time: most of these answers are in Chapter 7. It also relies on several concepts from Chapter 6: objects and lifetime ([[basic.life]]), types ([[basic.types]]), order of evaluation ([[intro.execution]]) and odr-use ([[basic.def.odr]]).

## How the chapter is organized

| Subclause | Contents | Notes on this site |
|---|---|---|
| 7.1 | Preamble: expressions, how overloaded operators relate to built-in operators, UB in arithmetic expressions | [[expr.pre]] |
| 7.2 | Properties of expressions: value categories, type adjustments, unevaluated operands, discarded-value expressions | [[expr.prop]], [[basic.lval]], [[expr.type]], [[expr.context]] |
| 7.3 | Standard conversions: lvalue-to-rvalue, array-to-pointer, temporary materialization, qualification conversions, integral promotions, etc. | [[conv]] |
| 7.4 | Usual arithmetic conversions | [[expr.arith.conv]] |
| 7.5 | Primary expressions: literals, `this`, names, lambdas, fold expressions, requires-expressions, splices | [[expr.prim]] |
| 7.6 | Compound expressions: postfix, unary, casts, pointer-to-member, multiplicative... all the way down to comma | [[expr.compound]] |
| 7.7 | Constant evaluation: core constant expressions, constant initialization, immediate functions | [[expr.const]] |

7.2–7.4 are the foundation for every later operator subclause. Each operator's description says that the lvalue-to-rvalue conversion is applied to the operands, that the usual arithmetic conversions are performed, whether the result is an lvalue or a prvalue; all these terms are defined in these subclauses. Value categories also have a topic page of their own, [[topics/value-categories]].

## Precedence is derived from the grammar

You won't find an operator precedence table in the standard. Footnote 33 in [[expr.pre]] explains why:

!!! std
    The precedence of operators is not directly specified, but it can be derived from the syntax.

Each precedence level corresponds to a grammar nonterminal whose operands are the next tighter nonterminal. Addition, for example:

```text
additive-expression:
    multiplicative-expression
    additive-expression + multiplicative-expression
    additive-expression - multiplicative-expression
```

The right operand of `+` can only be a *multiplicative-expression*, so `a + b * c` can only parse as `a + (b * c)`. The left operand is an *additive-expression* itself (left recursion), so `a - b - c` can only parse as `(a - b) - c`: that is left associativity. Right-associative operators (assignment, conditional, unary) are written with right recursion.

### The derived precedence table

The table goes from highest to lowest; each row corresponds to one nonterminal:

| Level | Nonterminal | Operators or forms | Associativity | Subclause |
|---|---|---|---|---|
| 1 | *primary-expression* | literals, `this`, `( e )`, names, lambdas, fold expressions, requires-expressions, `[: r :]` | | [[expr.prim]] |
| 2 | *postfix-expression* | `a[b]` `f(args)` `T(args)` `T{args}` `a.b` `a->b` `a++` `a--` `*_cast<T>(e)` `typeid` | left | [[expr.post]] |
| 3 | *unary-expression* | `*a` `&a` `+a` `-a` `!a` `~a` `++a` `--a` `co_await` `sizeof` `alignof` `noexcept` `new` `delete` `^^` | right | [[expr.unary]] |
| 3′ | *cast-expression* | `(T) e` | right | [[expr.cast]] |
| 4 | *pm-expression* | `.*` `->*` | left | [[expr.mptr.oper]] |
| 5 | *multiplicative-expression* | `*` `/` `%` | left | [[expr.mul]] |
| 6 | *additive-expression* | `+` `-` | left | [[expr.add]] |
| 7 | *shift-expression* | `<<` `>>` | left | [[expr.shift]] |
| 8 | *compare-expression* | `<=>` | left | [[expr.spaceship]] |
| 9 | *relational-expression* | `<` `>` `<=` `>=` | left | [[expr.rel]] |
| 10 | *equality-expression* | `==` `!=` | left | [[expr.eq]] |
| 11 | *and-expression* | `&` | left | [[expr.bit.and]] |
| 12 | *exclusive-or-expression* | `^` | left | [[expr.xor]] |
| 13 | *inclusive-or-expression* | `\|` | left | [[expr.or]] |
| 14 | *logical-and-expression* | `&&` | left | [[expr.log.and]] |
| 15 | *logical-or-expression* | `\|\|` | left | [[expr.log.or]] |
| 16 | *conditional-expression*, *assignment-expression* | `?:` `=` `op=` `throw` `co_yield` | right | [[expr.cond]], [[expr.assign]], [[expr.throw]], [[expr.yield]] |
| 17 | *expression* | `,` | left | [[expr.comma]] |

### Places that only the grammar makes clear

```cpp run title="grammar.cpp" ok
#include <cstdio>
int a = 1, b = 2, c = 3;

int f(bool q) {
    q ? a : b = c;            // parsed as q ? a : (b = c)
    int x = -(int)2.5;        // the operand of unary - is a cast-expression: x == -2
    int y = q ? 1 : throw 0;  // a throw-expression can be the third operand of ?:
    return x + y;
}

int main() {
    int r = f(true);          // q is true: b is not assigned, nothing is thrown
    std::printf("%d %d\n", b, r);   // prints 2 -1
}
```

- The operand of a unary operator is a *cast-expression*, so `-(int)x` and `!(bool)p` can be written directly. But the operand of `sizeof` is a *unary-expression*, so `sizeof (int)x` is parsed as `sizeof(int)` followed by a stray `x`, which is a syntax error.
- The three operands of the conditional operator are asymmetric: the first is a *logical-or-expression*, the second any *expression* (it may contain commas), the third an *assignment-expression*. So `c ? a : b = x` parses as `c ? a : (b = x)`. C's grammar is different: the same line parses in C as `(c ? a : b) = x` and is rejected because the result is not an lvalue.
- The left operand of assignment is a *logical-or-expression* and the right side is right-recursive, so `a = b ? c : d = e` parses as `a = (b ? c : (d = e))`.
- `throw` and `co_yield` are *assignment-expression*s, so `cond ? x : throw std::runtime_error("…")` is valid; but without parentheses, `throw` cannot be an operand of `+`.

<div class="compare" markdown="1">

```cpp run ok
int x;
auto s = sizeof (int) + x;
// sizeof(int) plus x
```

```cpp run error
int x;
auto s = sizeof (int)x;
// error: the operand of sizeof
// cannot be a cast-expression
```

</div>

!!! pitfall "Precedence decides the order of evaluation"
    Precedence only decides how operands are grouped, not which one is evaluated first. The order of the three calls in `f() + g() * h()` is governed by [[intro.execution]] and is unspecified; it has nothing to do with `*` binding tighter than `+`. Since C++17, `<<`, `>>`, assignment, `[]`, `.*`, `->*` and the function part of a function call have ordering guarantees; see the history section of [[expr.pre]].

## How overloaded operators fit into these rules

Chapter 7 describes the meaning of the **built-in operators**. When an operand has class or enumeration type, `a @ b` first goes through overload resolution ([[over.match.oper]]); the candidates include member `operator@`, non-member `operator@`, and the built-in candidates listed in [[over.built]]. When a user-defined function is selected, the expression is rewritten as a function call ([[over.oper]]). The syntax and order of evaluation then follow the built-in operator, the requirements on operand types and value categories are determined by the function's parameters instead, and identities such as `++a` being equivalent to `a += 1` are no longer guaranteed. The detailed rules are in [[expr.pre]].

## Summary

!!! summary
    - Chapter 7 has three parts: rules that apply throughout (7.1–7.4), the operators in order of precedence (7.5–7.6), and constant evaluation (7.7).
    - The standard has no precedence table; precedence and associativity are derived from the grammar. Remember the asymmetries: `sizeof`, the second and third operands of `?:`, and the left operand of assignment.
    - Precedence decides grouping, not order of evaluation.
    - Overloaded operators keep the syntax and evaluation order, but not the type and value-category requirements or the identities between operators.
