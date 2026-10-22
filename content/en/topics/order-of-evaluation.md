---
title: Order of evaluation
summary: Whether the operands of each operator are sequenced, indeterminately sequenced or unsequenced, which forms are undefined behavior as a result, and how these rules evolved from sequence points to C++17.
tags: order of evaluation, sequence points, UB, topic
updated: 2026-10-19
---

!!! tldr
    - Two evaluations stand in one of three relations: sequenced (one before the other), indeterminately sequenced (which comes first is unspecified, but they don't interleave), or unsequenced (they may interleave). Two modifications of the same scalar, or a modification and a read of it, are UB if unsequenced.
    - Since C++17, `<<`, `>>`, `[]`, `.*`, `->*` and the object expression of a member call are evaluated left before right, and assignment right before left; `&&`, `||`, `?:` and `,` have always been left before right.
    - Function arguments are indeterminately sequenced with each other; the two operands of the other binary operators such as `+`, `*` and `==` are still unsequenced.
    - When an overloaded operator is invoked with operator syntax, its operands are evaluated in the order of the corresponding built-in operator.
    - During constant evaluation, subexpressions that would otherwise be unsequenced or indeterminately sequenced are all evaluated in lexical order.

## A few examples first

```cpp run title="classic-cases.cpp" ok
#include <map>
#include <cstddef>

int main() {
    int i = 0;
    i = i++ + 1;            // C++17: i == 1
    int a[4]{};
    a[i] = i++;             // C++17: i++ is evaluated first (value 1, i becomes 2), then a[2] = 1
    std::map<int, std::size_t> m;
    m[7] = m.size();        // C++17: size() is called first, m[7] == 0
    int x = 3, y = 5;
    x ^= y ^= x ^= y;       // C++17: swaps x and y
    return (i == 2 && a[2] == 1 && m[7] == 0 && x == 5 && y == 3) ? 0 : 1;
}
```

```cpp title="still-ub.cpp" ub
int g(int x) { return x; }

int main() {
    int i = 0;
    int a = i++ + i++;          // UB: the two operands of + are unsequenced
    int b = (i = i++ + i);      // UB: the modification by i++ is unsequenced with the read of i (standard example)
    int c = g(i++) + g(i++);    // UB: the two i++ belong to the two operands of +, unsequenced
    return a + b + c;
}
```

Every line in the first snippet was UB or had an unspecified result in C++14, and all are defined since C++17. The second snippet is UB in every version, and Clang 23 gives a `-Wunsequenced` warning for all three lines. The difference is which rule gives the two evaluations an order.

## Three relations

An **evaluation** has two parts: **value computation**, working out the value of the expression (for a glvalue, determining which object it refers to); and **side effects**, such as modifying an object, accessing a volatile object, or calling an I/O function.

[[intro.execution#8]] defines three relations between two evaluations in the same thread:

| Relation | Meaning | When both act on the same scalar |
|---|---|---|
| **Sequenced before** | A completes before B starts | Defined |
| **Indeterminately sequenced** | A first or B first, without overlapping, but which is unspecified | Unspecified result, not UB |
| **Unsequenced** | No ordering; execution may overlap | UB |

[[intro.execution#10]] gives the condition for UB: a side effect on a memory location is unsequenced relative to another side effect on the same location, or to a value computation using the value of that location, and the two are not potentially concurrent (the concurrent case is handled by the data race rules in [[intro.races]]). The current draft also includes starting or ending the lifetime of an object in the same location.

Overlap is the root of the UB. At the hardware level, `i++ + i++` could be scheduled as read i, read i, write i+1, write i+1, with the two writes interleaved, and the result is meaningless. At the optimizer level, the compiler may assume unsequenced side effects act on different objects and reorder code accordingly.

Two more rules apply generally:

- The value computations of an operator's operands are sequenced before the value computation of the operator's result. This only says the operands' values are computed first; it says nothing about the operands' side effects ([[intro.execution#10]]).
- All value computations and side effects of a full-expression are sequenced before the next full-expression ([[intro.execution#9]]). So two statements are always sequenced.

### Function calls don't interleave

By [[intro.execution#12]], for each function call (and *await-expression*, *throw-expression*) *F*, every evaluation not inside *F* is either sequenced entirely before all evaluations inside *F* or entirely after them. That is, the executions of two function bodies don't interleave: in `f() + g()` the two calls are indeterminately sequenced, not unsequenced.

So putting side effects into a function body avoids UB, though the result may still be unspecified. Note that arguments are evaluated in the caller, not inside the function body. In `g(i++) + g(i++)` the two `i++` belong to the two operands of `+` and are unsequenced with each other, which is why the third line of the second snippet above is UB.

## What each operator specifies (since C++17)

| Construct | Relation between operands | Since | Clause |
|---|---|---|---|
| `a && b`, `a \|\| b` | `a` before `b`; `b` may not be evaluated | C++98 | [[expr.log.and]] |
| `a ? b : c` | `a` before whichever of `b` or `c` is chosen | C++98 | [[expr.cond]] |
| `a , b` (built-in) | `a` before `b` | C++98 | [[expr.comma]] |
| `a << b`, `a >> b` | `a` before `b` | C++17 | [[expr.shift#4]] |
| `a = b`, `a op= b` | `b` before `a`; the assignment itself after both value computations | C++17 | [[expr.assign#1]] |
| `a.*b`, `a->*b` | `a` before `b` | C++17 | [[expr.mptr.oper#4]] |
| `a[b]` | `a` before `b`; multiple subscript arguments indeterminately sequenced | C++17 | [[expr.sub#1]] |
| `f(a, b)` | `f` before each argument; initializations of parameters indeterminately sequenced | C++17 | [[expr.call#8]] |
| `a.f(b)`, `p->f(b)` | The object expression is part of the postfix expression, before `b` | C++17 | [[expr.call#8]] |
| `new T(a)` | Calling the allocation function before evaluating `a` | C++17 | [[expr.new#25]] |
| `T{a, b}`, `{a, b}` | `a` before `b` | C++11 | [[dcl.init.list#4]] |
| `a++`, `a--` | Value computation before the modification | C++11 | [[expr.post.incr]] |
| `a + b`, `a * b`, `a < b`, `a == b`, `a & b`, `a <=> b` etc. | Unsequenced | | [[intro.execution#10]] |
| Overloaded operator, operator syntax | Same as the corresponding built-in operator | C++17 | [[over.match.oper#2]] |
| Overloaded operator, function call syntax `operator+(a, b)` | As a function call: arguments indeterminately sequenced | | [[expr.call]] |

## Function calls

### The callee and the arguments

By [[expr.call#8]], the postfix expression designating the called function is sequenced before every argument and default argument. The initialization of each parameter, including every associated value computation and side effect, is indeterminately sequenced with respect to the initialization of any other parameter. All of these are sequenced before the evaluation of precondition assertions, which are in turn before the function body ([[intro.execution#11]]).

Two practical consequences follow. First, `p->f(std::move(p))` is safe in C++17:

```cpp run title="move-self.cpp" ok
#include <memory>

struct Node {
    int v = 7;
    int consume(std::unique_ptr<Node> self) { return self->v; }
};

int main() {
    auto up = std::make_unique<Node>();
    int r = up->consume(std::move(up));   // up->consume is evaluated first (reading up), then the parameter is initialized from up
    return (r == 7 && up == nullptr) ? 0 : 1;
}
```

In C++14, the initialization of the parameter (moving out of `up`) could happen before `up->` was evaluated, resulting in a member function call through a null pointer.

Second, `f(std::unique_ptr<T>(new T), g())` no longer leaks. In C++14 the evaluations of the two arguments could interleave: first `new T`, then call `g()`, and only then construct the `unique_ptr`. If `g()` threw, the object created by `new` leaked; this was one of the reasons `std::make_unique` was recommended. In C++17 the initialization of each parameter is a single unit, and interleaving is no longer possible.

### The actual order of arguments

Indeterminately sequenced means different implementations, and even the same implementation at different call sites, may use different orders:

```cpp run title="arg-order.cpp" unspecified
#include <cstdio>

int n = 0;
int next() { return ++n; }
void show(int a, int b) { std::printf("%d %d\n", a, b); }

int main() {
    show(next(), next());   // prints "1 2" or "2 1", unspecified
}
```

Clang 23 prints `1 2`. Some implementations that prepare arguments right to left according to the calling convention get `2 1`. Portable code can't rely on either.

## Overloaded operators

[[over.match.oper#2]] says that for an overloaded operator invoked with operator syntax, the operands are evaluated in the order specified for the built-in operator. The following is adapted from Example 5 in [[expr.call]]:

```cpp run title="overloaded-order.cpp" ok
struct S { S(int) {} };
int operator<<(S, int) { return 0; }

int main() {
    int i, j;
    int x = S(i = 1) << (i = 2);             // operator syntax: left before right, i ends up 2
    int y = operator<<(S(j = 1), j = 2);     // function call syntax: whether j is 1 or 2 is unspecified
    (void)x; (void)y;
    return i == 2 ? 0 : 1;
}
```

Clang 23 warns `multiple unsequenced modifications to 'j'` for the second line. The two arguments are actually indeterminately sequenced rather than unsequenced, so the warning is conservative.

This rule applies to overloaded `&&`, `||` and `,` as well. Since C++17 their left operand is sequenced before the right, but overloaded `&&` and `||` still don't short-circuit; both operands are evaluated ([[expr.log.and]], [[expr.comma]]).

## Other contexts

- **Brace initialization**: the initializer-clauses inside braces are sequenced left to right ([[dcl.init.list#4]]), even if a constructor is ultimately called. So `T{f(), g()}` has a definite order and `T(f(), g())` doesn't. You can use this when you need a definite order.
- **new expressions**: calling the allocation function is sequenced before evaluating the expressions in the *new-initializer* ([[expr.new#25]]). In C++14, `new T(f())` could call `f()` before allocating memory.
- **Member initialization**: proceeds in declaration order of the members, regardless of the written order of the *mem-initializers* ([[class.base.init]]). This is the execution order of the constructor, not a rule of expression evaluation.
- **Destruction of temporaries**: happens after the full-expression has been evaluated, usually in reverse order of construction ([[class.temporary]]).

## Lexical order during constant evaluation

[[intro.execution#16]] says that when evaluating as a core constant expression, operands and subexpressions that would otherwise be unsequenced or indeterminately sequenced are evaluated in lexical order. Default arguments that are used are evaluated in the order as if an argument had been written for the corresponding parameter. This is new wording after C++23.

```cpp run title="constexpr-lexical.cpp" ok
constexpr int g(int a, int b) { return a * 10 + b; }

constexpr int h() {
    int i = 0;
    return g(++i, ++i);         // lexical order during constant evaluation: g(1, 2)
}
static_assert(h() == 12);

constexpr int f() {
    int i = 0;
    return i++ + i++;           // lexical order during constant evaluation: 0 + 1
}
static_assert(f() == 1);

int main() {}
```

This makes compile-time results independent of the implementation. Clang 23 accepts both `static_assert`s while giving `-Wunsequenced` warnings for both `return`s. Note that `f()` is defined only during constant evaluation; when the same function is called at run time, `i++ + i++` is still UB.

## History: from sequence points to C++17

### C++98: sequence points

C++98 inherited C's **sequence point** model. At a sequence point, all earlier side effects are complete and none of the later ones have started. Sequence points are at the end of a full-expression, after the first operand of `&&` `||` `?:` `,`, before entering a function body, and so on. The rule was: between two adjacent sequence points, an object may be modified at most once, and its old value may be read only to determine the new value to be stored.

This model had two problems. In nested expressions it is hard to pin down which two sequence points are adjacent; and it only describes single-threaded execution and can't be connected to a multithreaded memory model.

### C++11: the sequenced-before relation

To go with the new memory model ([[intro.multithread]]), C++11 rewrote all the ordering rules in terms of the sequenced-before relation ([[N2239]]). Sequenced before within a thread, together with synchronization between threads, makes up happens-before ([[intro.races]]).

The rewrite largely kept the old semantics while also fixing some corners. For example `i = ++i + 1`: prefix `++i` is defined as `i += 1`, and the modification by an assignment is specified to come after the value computations of its operands, so the modification by `++i` is sequenced before the outer assignment. This was UB in C++03 and is defined since C++11.

### C++17: P0145

The motivating example of [[P0145R3]] came from a widely circulated C++ textbook, and the standard includes it as Example 4 in [[expr.call]]:

```cpp run title="p0145-replace.cpp" ok
#include <string>
#include <cassert>

int main() {
    std::string s = "but I have heard it works even if you don't believe in it";
    s.replace(0, 4, "").replace(s.find("even"), 4, "only").replace(s.find(" don't"), 6, "");
    assert(s == "I have heard it works only if you believe in it");   // guaranteed since C++17
}
```

In C++14 there was no ordering between the postfix expression `s.replace(0, 4, "").replace` and the argument `s.find("even")`. `find` could run first, see the string before `but ` had been removed, and get the wrong position.

P0145 added ordering where programmers intuitively expect it: the postfix expression before the arguments (including the previous call in a chain); `<<` and `>>` left before right, for iostream chains; assignment right before left; `.*`, `->*` and `[]` left before right; overloaded operators following the built-in order.

Arguments were originally also going to be specified left to right, but because some implementations prepare arguments right to left according to the calling convention, in the end only indeterminate sequencing was specified. That is stronger than C++14's unsequenced and interleavable, but still not a fixed order.

### Verdicts by version

| Code | C++03 | C++11/14 | Since C++17 |
|---|---|---|---|
| `i = ++i + 1;` | {{ub}} | OK | OK |
| `i = i++ + 1;` | {{ub}} | {{ub}} | OK, `i` increases by 1 |
| `i = i++ + i;` | {{ub}} | {{ub}} | {{ub}}, the operands of `+` are unsequenced |
| `i++ + i++` | {{ub}} | {{ub}} | {{ub}} |
| `a[i] = i++;` | {{ub}} | {{ub}} | OK, right side first |
| `f(i++, i++);` | {{ub}} | {{ub}} | {{unspec}}, indeterminately sequenced |
| `f(i++) + g(i++)` | {{ub}} | {{ub}} | {{ub}}, the `i++` aren't inside the function bodies |
| `std::cout << i << i++;` | {{ub}} | {{ub}} | OK, prints the old value twice |
| `m[k] = m.size();` | {{unspec}} | {{unspec}} | OK, `size()` called first |
| `x = (i++, i);` | OK | OK | OK |
| `a ^= b ^= a ^= b;` | {{ub}} | {{ub}} | OK, swaps `a` and `b` |

## Tools

Clang's `-Wunsequenced` (on by default) and GCC's `-Wsequence-point` (included in `-Wall`) detect unsequenced modifications of the same variable within one full-expression. They work at the syntactic level and only find cases where the variable name appears directly; they can't see through pointers and references. UBSan doesn't detect this class of problem.

The most reliable defense is how you write the code: within one full-expression, modify an object at most once, and don't read it elsewhere in the same expression unless you can name the rule that guarantees the order. When you need an order, split it into several statements, or use brace initialization, the comma operator, `&&` or `||`.

## Questions

!!! question "Question 1"
    What about `v[i] = v[j]++;` (with `i == j`, `v` a `std::vector<int>`) in C++14 and in C++17?

<details markdown="1">
<summary>Answer</summary>

`v[i]` and `v[j]` are both calls to the overloaded `operator[]`, returning references; `=` and postfix `++` are both built-in operators acting on `int`.

In C++17 assignment is right before left: `v[j]++` is evaluated completely first, yielding the old value and incrementing the element; then `v[i]` is evaluated, then the assignment. The element ends up equal to the old value, the increment is overwritten, and the behavior is defined.

In C++14 the assignment's modification was only guaranteed to come after the value computations of both sides, and the modification by postfix `++` isn't part of its value computation, so the two modifications of the same element are unsequenced, which is UB.
</details>

!!! question "Question 2"
    Why did C++17 specify an order for `<<` and `>>` but not for `+` and `*`?

<details markdown="1">
<summary>Answer</summary>

P0145 only specified an order where programmers already use the operators as sequential operations. `<<` and `>>` are used for chained iostream input and output; assignment, `[]`, `.*` and member call chains all carry the meaning of locating first and then operating. `+` and `*` are mathematical operations, code that depends on the order of their operands is almost always wrong, and leaving them unsequenced also leaves the optimizer free to reorder the two operands.
</details>
