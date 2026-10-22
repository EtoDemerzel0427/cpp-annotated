---
title: Properties of expressions
summary: Independent of any particular operator, every expression has two static properties, a type and a value category, and may appear in an unevaluated or discarded-value context; the three subclauses of 7.2 cover these three things.
updated: 2026-10-19
---

!!! tldr
    - Every expression has a type and a value category (one of lvalue, xvalue, prvalue); the subclause for each operator supplies them.
    - The type of an expression is never a reference type; the type of a prvalue of non-class, non-array type is not cv-qualified.
    - When an operator needs a different value category, the standard inserts a conversion automatically: a glvalue becomes a prvalue (reading the value), a prvalue becomes an xvalue (materializing a temporary object).
    - The same expression is not evaluated inside `sizeof`, and when written alone as a statement it is evaluated but its result is discarded; each of these contexts has its own rules.

[expr.prop] has no text of its own, only three subclauses:

| Subclause | Question it answers |
|---|---|
| 7.2.1 [[basic.lval]] | Which value category an expression belongs to; how conversions happen automatically when the category doesn't match; when an object may be accessed through another type (strict aliasing) |
| 7.2.2 [[expr.type]] | How reference types and cv-qualifiers are removed from the type of an expression; what type two pointers are brought to when compared (the composite pointer type) |
| 7.2.3 [[expr.context]] | Unevaluated operands and discarded-value expressions: whether an expression is evaluated, and what happens to its result |

## The static description of an expression

```cpp ok
#include <type_traits>
#include <utility>
int x = 0;
int& r = x;

static_assert(std::is_same_v<decltype((r)), int&>);             // type int, lvalue
static_assert(std::is_same_v<decltype((std::move(x))), int&&>); // type int, xvalue
static_assert(std::is_same_v<decltype((x + 1)), int>);          // type int, prvalue
```

All three expressions have type `int`; they differ only in value category. `decltype((e))` encodes both properties in one type: an lvalue is encoded as `T&`, an xvalue as `T&&`, a prvalue as `T` ([[dcl.type.decltype]]). Although `r` is declared as a reference, the expression `r` still has type `int`, because [[expr.type]] removes the reference before the expression is analyzed.

The **value category** ([[g:value-category]]) describes what an expression produces: an **lvalue** designates an object or function that already exists; an **xvalue** also designates an object, but one whose resources can be taken; a **prvalue** designates no object and is only used to initialize an object or compute a value. For the detailed definitions and how to tell them apart, see [[basic.lval]] and the topic page [[topics/value-categories]].

Built-in operators have requirements on the value categories of their operands, and when these aren't met, [[basic.lval]] converts automatically. For example, in `x + 1`, `+` needs a prvalue and `x` is an lvalue, so the lvalue-to-rvalue conversion is applied to `x`, that is, its value is read; in `f().m`, member access needs an object and `f()` is a prvalue, so a temporary object is materialized first. The conversions themselves are defined in [[conv]].

## Evaluation contexts

```cpp ok
int calls = 0;
int f() { return ++calls; }

auto a = sizeof(f());      // f is not called: unevaluated operand
void g() { f(); }          // f is called and its return value discarded: discarded-value expression
```

The operands of `sizeof`, `decltype` and `noexcept` are **unevaluated operands**, used only to determine static information such as the type. A standalone `f();`, the expression on the left of a comma, and `(void)e` are **discarded-value expressions**: they are evaluated but their result is not used. [[expr.context]] gives the details of both contexts, such as when a discarded-value expression actually reads a `volatile` object.

The suggested reading order is the first few paragraphs of [[basic.lval]], then [[expr.type]]; [[expr.context]] can wait until you run into a question about `volatile`, the ODR or `sizeof`.
