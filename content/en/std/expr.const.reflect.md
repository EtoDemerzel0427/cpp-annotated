---
title: Reflection and constant evaluation
summary: "In C++26, constant evaluation can produce declarations (std::meta::define_aggregate); where these injected declarations live, who can see them, which consteval blocks alone may produce them, and which context reflection queries answer from."
updated: 2026-10-19
---

!!! tldr
    - {{c++26}} `std::meta::define_aggregate` completes the definition of an incomplete class during constant evaluation. A declaration produced this way is called an injected declaration, and this is currently its only source.
    - Only the evaluation of a `consteval { … }` block can produce injected declarations; calling `define_aggregate` in any other constant expression makes it not a constant expression. The consteval block must also be at the same level as the class being defined, with no function or class boundary in between.
    - An injected declaration is located at a synthesized point after the end of the translation unit. Ordinary code sees it only after the consteval block has been evaluated, while reflection queries see it according to their evaluation context.
    - A nested manifestly constant-evaluated evaluation (such as the initializer of a constexpr local variable) can't see injected declarations just produced by the enclosing evaluation, so the value of a constexpr variable doesn't depend on which call it is evaluated in.
    - When different translation units inject definitions of the same class, what is compared is the characteristic sequence (the member descriptions), not the token sequence.

## Constant evaluation starts modifying the program

```cpp
#include <meta>

struct Point;                       // incomplete class
consteval {
  std::meta::define_aggregate(^^Point, {
    std::meta::data_member_spec(^^int, {.name = "x"}),
    std::meta::data_member_spec(^^int, {.name = "y"}),
  });
}
Point p{1, 2};                      // OK: Point now has a definition
```

In C++23 and earlier, constant evaluation was pure computation: it read the program and computed a value without changing the program itself. C++26 static reflection ([[P2996R13]]) changed that. `^^Point` yields the reflection value of the class `Point`, and `define_aggregate` gives it a definition during constant evaluation. `consteval { … }` is the consteval block declaration new in C++26 ([[P3289]]), whose contents are executed once during translation.

Once constant evaluation has side effects like this, several questions arise that didn't exist before:

- Where in the program is the produced definition, and which code can see it?
- When two translation units each produce a definition of the same class, how do we decide they agree?
- Compilers may evaluate constant expressions tentatively, cache results, or evaluate at arbitrary points during template instantiation. If these evaluations could modify the program, its meaning would depend on the compiler's internal strategy.

The standard answers with three mechanisms: synthesized points and characteristic sequences (¶1), allowing only consteval blocks to produce declarations and restricting where they may be (¶3), and points of evaluation and evaluation contexts (¶5).

!!! impl "Implementation status"
    At the time of writing, Clang 23 doesn't support reflection (there is no `<meta>` header, and `^^` is not recognized). Experimental implementations are available on Compiler Explorer (for example the Clang fork maintained by Bloomberg). The examples here are analyzed from the draft text and have not been compiled locally.

## Injected declarations (¶1)

¶1 The evaluation of an expression can introduce one or more **injected declarations** ([[g:injected-declaration|injected declaration]]), and the evaluation is said to **produce** them. Note 1 points out that a call to `std::meta::define_aggregate` produces an injected declaration ([[meta.reflection.define.aggregate]]). Each injected declaration has:

- ¶1.1 a **synthesized point**, which follows the last non-synthesized program point in its translation unit;
- ¶1.2 a **characteristic sequence**, consisting of a sequence of values.

### Synthesized points: the declaration sits after the end of the translation unit

An injected declaration doesn't appear in the source code, so it needs a virtual location. The standard puts it after the entire translation unit. Under the ordinary reachability rules, a declaration must appear before a point P to be reachable from P ([[module.reach#3.1]]), so nowhere in the source code can a declaration placed after the end be seen.

Two other rules make it visible where it is needed:

- Phase 7 of [[lex.phases]] says that when analyzing the code at a program point P, the side effects of any consteval block reachable from P (usually one written before P) are considered to have already happened. `Point p{1, 2};` in the example above can therefore use the complete `Point`.
- [[module.reach#3.2]] says an injected declaration is reachable from its own synthesized point, and ¶5 puts synthesized points into the evaluation context of reflection queries. This way, a later reflection query within the same evaluation can see a definition just injected.

Inside the consteval block that produces it, ordinary code still can't see the definition. The example in [[module.reach]] demonstrates this:

```cpp
class Incomplete;
consteval {
  int n = nonstatic_data_members_of(
      define_aggregate(^^Incomplete, {data_member_spec(^^int, {.name="x"})}),
      std::meta::access_context::current()
    ).size();      // n == 1: the reflection query can see the member x
  Incomplete y;    // error: Incomplete is still an incomplete type here
}
```

Why not insert the definition at the location of the consteval block? Because an injected declaration produced during template instantiation has no definite location in the source code. Synthesized points together with evaluation contexts give semantics that are independent of when instantiation happens.

### Characteristic sequences and consistency across translation units

Note 3 and [[basic.def.odr#15]] say: if a class is defined by an injected declaration in one translation unit, its definition in another translation unit must also be an injected declaration with the same characteristic sequence. A diagnostic is required only if the class is attached to a named module and the earlier definition is reachable from the later one; other violations require no diagnostic.

The ordinary ODR requires the definitions in the various translation units to be identical token by token. Injected declarations have no tokens, so characteristic sequences are compared instead. For `define_aggregate`, the characteristic sequence is the list of member descriptions passed in ([[meta.reflection.define.aggregate]]).

## Restrictions on consteval blocks (¶3–¶4)

### Only consteval blocks can produce declarations

[[expr.const.core#2.32]] says an expression that would produce an injected declaration is not a core constant expression unless it is the expression corresponding to a consteval block. Calling `define_aggregate` in the initializer of a constexpr variable, a template argument or a `static_assert` makes the expression no longer a constant expression.

A consteval block is a declaration: its position in the program determines when it is evaluated, and it is evaluated exactly once. General constant expressions may be evaluated tentatively, cached, or discarded during SFINAE. Letting only consteval blocks have side effects keeps the meaning of the program independent of how the compiler schedules these evaluations.

The expression corresponding to a consteval block is `[] static consteval -> void { contents of the block }()` ([[dcl.pre#15]]); this matters for the scope rules below.

### The block must be at the same level as the class it defines (¶3)

¶3 Let a consteval block C be such that its evaluation produces an injected declaration defining an entity E. The program is ill-formed if either:

- ¶3.1 C is enclosed by a scope associated with E, i.e. a class S is defined inside its own definition; or
- ¶3.2 letting P be a point whose immediate scope is the scope to which E belongs, there is a function parameter scope or class scope that encloses exactly one of C and P.

¶3.2 means there may be no function or class boundary between the consteval block and the class being defined. Otherwise you would get unclear situations such as defining a namespace-scope class in one particular call of a function f.

### The standard's example (¶4)

```cpp
struct S0 {
  consteval {
    std::meta::define_aggregate(^^S0, {});  // error: ¶3.1, the scope of S0 encloses this block
  }
};

struct S1;
consteval { std::meta::define_aggregate(^^S1, {}); }   // OK: both at namespace scope

template <std::meta::info R> consteval void tfn1() {
  std::meta::define_aggregate(R, {});
}
struct S2;
consteval { tfn1<^^S2>(); }   // OK: what matters is where the consteval block is,
                              //     not which function define_aggregate is written in

template <std::meta::info R> consteval void tfn2() {
  consteval { std::meta::define_aggregate(R, {}); }
}
struct S3;
consteval { tfn2<^^S3>(); }   // error: the declaration is produced by the block in tfn2<^^S3>,
                              //        whose parameter scope encloses it but not S3

template <typename> struct TCls {
  struct S4;
  static void sfn() requires ([] {
    consteval { std::meta::define_aggregate(^^S4, {}); }
    return true;
  }()) { }
};
consteval { TCls<void>::sfn(); }   // error: the parameter scope of the lambda in the requires-clause
                                   //        encloses the block but not TCls<void>::S4

struct S5;
struct Cls {
  consteval { std::meta::define_aggregate(^^S5, {}); }  // error: Cls's class scope encloses the block, not S5
};

struct S6;
consteval {                                 // #1
  struct S7;                                // local class
  std::meta::define_aggregate(^^S7, {});    // error: see below

  struct S8;                                // local class
  consteval {                               // #2
    std::meta::define_aggregate(^^S6, {});  // error: #1 encloses #2 but not S6
    std::meta::define_aggregate(^^S8, {});  // OK: #1 encloses both #2 and S8
  }
}
```

The case of `S7` goes back to how consteval blocks are rewritten. The contents of block #1 are the body of a lambda, so `S7` is declared within that lambda's parameter scope; block #1 itself, as a declaration, is at namespace scope. That parameter scope encloses `S7` but not #1, violating ¶3.2. The nested block #2 and `S8` are both in the parameter scope of #1, at the same level, so that is valid.

## Points of evaluation and evaluation contexts (¶5)

The results of reflection queries such as `std::meta::is_complete_type` and `members_of` depend on which declarations the program already has at the time of the query. ¶5 specifies the time and place of a query.

### Point of evaluation

¶5 During an evaluation V of an expression, conversion or initialization E as a core constant expression, the **point of evaluation** P of E in V is determined as follows:

- ¶5.1 if E is in a default member initializer that is evaluated as part of an (possibly aggregate) initialization, P is the point of evaluation of that initialization;
- ¶5.2 otherwise, if E is in a default argument that is evaluated as part of a function call, P is the point of evaluation of that call;
- ¶5.3 otherwise, P is the point at which E appears.

Default member initializers and default arguments are written in one place but evaluated each time where they are used, so they borrow the location of the use. This is the same idea as default arguments escalating the caller in [[expr.const.imm]].

### Evaluation context

During V, the **evaluation context** of an evaluation X is a set of program points C:

- ¶5.4 if X occurs during the evaluation Y of a manifestly constant-evaluated expression within V, C is the evaluation context of X during Y. In other words, a nested constant evaluation computes its context afresh;
- ¶5.5 otherwise, C contains:
    - ¶5.5.1 the point of evaluation of E in V, and every synthesized point in its instantiation context;
    - ¶5.5.2 the synthesized point of every injected declaration produced by an evaluation sequenced before X in V.

Note 5 points out that the evaluation context determines the behavior of certain reflection functions ([[meta.reflection]]).

### The standard's example

```cpp
struct S;
consteval std::size_t f(int p) {
  constexpr std::size_t r = /* Q */
    std::meta::is_complete_type(^^S) ? 1 : 2;   // #1
  if (!std::meta::is_complete_type(^^S)) {      // #2
    std::meta::define_aggregate(^^S, {});
  }
  return (p > 0) ? f(p - 1) : r;
}

consteval {
  if (f(1) != 2) {
    throw;                                      // OK: not evaluated
  }
}
```

Step through the evaluation V of `f(1) != 2` in the consteval block:

1. Enter `f(1)`. `r` is a constexpr variable, and its initializer is manifestly constant-evaluated, forming a nested evaluation Y. By ¶5.4, the context of the query at #1 contains only Q and the synthesized points in the instantiation context, and can't see injected declarations produced in V. `S` is incomplete, and `r` is 2.
2. The query at #2 is not in a nested evaluation. By ¶5.5, it can see injected declarations produced earlier in V, but there are none yet. `S` is incomplete, so `define_aggregate` is called, producing an injected declaration.
3. The recursive call `f(0)`. The initializer of `r` is again a nested evaluation whose context is still only Q, so `r` is still 2.
4. At #2 in `f(0)`, by ¶5.5.2, the context includes the synthesized point of the injected declaration just produced. `S` is complete, so it is not defined again.
5. `f(0)` returns 2, `f(1) != 2` is false, and `throw;` is not evaluated.

This design guarantees that the value of a constexpr variable doesn't depend on which call it is evaluated in. If #1 could see the injected declaration, `r` would differ between `f(1)` and `f(0)`, while the compiler may well treat a constexpr variable as a value that is the same for all calls.

!!! note "Why side effects are kept on such a tight leash"
    Using tricks such as friend injection, C++ has long allowed stateful metaprogramming whose results depend on the order of template instantiation, which is regarded as a defect in the language ([[CWG2118]]). Reflection officially provides the ability to modify the program, so the standard has to make it deterministic: only consteval blocks can produce declarations, and each is evaluated once; a block must be at the same level as the class it defines; injected definitions are visible only through evaluation contexts, and nested evaluations don't see the side effects of the enclosing one; and characteristic sequences keep translation units consistent.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

¶2 The members of an entity defined by an injected declaration shall not use names reserved for the implementation ([[lex.name]], such as `__x` and `_X`); no diagnostic is required. Member names can be assembled by arbitrary constant-evaluated string operations, and requiring the compiler to diagnose this would cost too much. The rule prevents using reflection to create names that clash with the internals of the standard library implementation, such as `data_member_spec(^^int, {.name = "__value"})`.

</details>

## History and evolution

!!! history
    In C++23 and earlier, constant evaluation could not produce declarations. C++26's [[P2996R13]] introduced static reflection (`^^`, `std::meta::info`, `define_aggregate` and so on), and [[P3289]] introduced consteval blocks. All of [expr.const.reflect], as well as [[expr.const.core#2.32]] and the consteval-only values in [[expr.const.const#1]], come from these two papers.

## Questions

!!! question "Question 1"
    Why is the following code ill-formed?

    ```cpp
    struct T;
    constexpr bool done = (std::meta::define_aggregate(^^T, {}), true);
    ```

<details markdown="1">
<summary>Answer</summary>

Evaluating `define_aggregate` would produce an injected declaration, and the initializer of `done` is not the expression corresponding to a consteval block, so it hits [[expr.const.core#2.32]] and is not a core constant expression. `done` is a constexpr variable whose initializer must be a constant expression, so the program is ill-formed. It should be written as `consteval { std::meta::define_aggregate(^^T, {}); }`.
</details>

!!! question "Question 2"
    In the standard's example in ¶5, what happens if `constexpr std::size_t r` is changed to `std::size_t r`?

<details markdown="1">
<summary>Answer</summary>

The initializer of a non-constexpr local variable is not manifestly constant-evaluated, so #1 is no longer a nested evaluation and, by ¶5.5, can see injected declarations produced earlier in V. In `f(1)`, `S` is incomplete at #1, so `r` is 2, and then `S` is defined; in `f(0)`, `S` is already complete at #1, so `r` is 1. `f(1)` returns the result of `f(0)`, which is 1, so `f(1) != 2` is true and `throw;` is evaluated. There is no currently handled exception at that point, which hits [[expr.const.core#2.25]], so the expression corresponding to the consteval block is not a constant expression, violating [[dcl.pre#15]], and the program is ill-formed.
</details>
