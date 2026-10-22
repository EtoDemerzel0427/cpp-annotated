---
title: Statements
summary: "The structure of Chapter 8: what statements there are, how control flow moves between them, and which objects are constructed and destroyed as it does; the chapter's habit of defining statements by equivalent rewrites; and the statement forms added from C++11 to C++26."
updated: 2026-10-19
---

!!! tldr
    - Chapter 7 specifies what expressions compute; Chapter 8 specifies in what order statements execute, how many times, how control flow moves, and which automatic variables are constructed and destroyed when it does.
    - Many statements, including `while`, `for`, range-based `for`, `if` with an initializer and `co_return`, are defined by equivalent rewrites; watch for the "except that" provisos attached to the rewrites.
    - Where `break`, `case` and `goto` can be written depends on substatements and enclosure, and none of them crosses a lambda body.
    - On leaving a scope, automatic variables are destroyed in reverse order of construction; a jump cannot bypass a non-vacuous initialization.
    - A condition can declare a variable, C++17 added the *init-statement*, and C++26 allows a structured binding as a condition, all so that a variable's scope covers exactly the statement that uses it.

A function body is made of statements. Expressions ([[expr]]) decide what is computed; statements decide when it is computed, how many times, and where to go afterwards. This chapter also relies on a few concepts from Chapter 6: block scope ([[basic.scope.block]]), object lifetime ([[basic.life]]) and order of evaluation ([[intro.execution]]).

## How the chapter is organized

| Subclause | Content | Notes on this site |
|---|---|---|
| 8.1–8.4 | Kinds of statements; substatements and enclosure; conditions; labels, expression statements, compound statements | [[stmt.pre]] |
| 8.5 | `if`, `if constexpr`, `if consteval`, `switch` | [[stmt.select]] |
| 8.6 | `while`, `do`, `for`; trivial infinite loops | [[stmt.iter]] |
| 8.6.5 | The rewrite rule for range-based `for` | [[stmt.ranged]] |
| 8.7 | Expansion statements `template for` {{c++26}} | [[stmt.expand]] |
| 8.8 | `break`, `continue`, `return`, `co_return`, `goto` | [[stmt.jump]] |
| 8.9 | `contract_assert` {{c++26}} | [[stmt.contract.assert]] |
| 8.10 | Declaration statements: skipping initialization, local static variables | [[stmt.dcl]] |
| 8.11 | Ambiguity between expression statements and declarations | [[stmt.ambig]] |

## Rules that run through the chapter

### Semantics defined by equivalent rewrites

Many statements in this chapter are not described directly; instead the text says "X is equivalent to Y":

- an `if` or `switch` with an initializer is equivalent to wrapping it in another block, `{ init-statement; if (…) … }` ([[stmt.if#3]], [[stmt.switch#7]]);
- `while` is equivalent to an `if` with a label and a `goto` ([[stmt.while#2]]), and `for` is equivalent to `while` ([[stmt.for#1]]);
- range-based `for` is equivalent to a classic `for` plus a few exposition-only variables ([[stmt.ranged#1]]);
- `template for` is equivalent to a sequence of expanded compound statements ([[stmt.expand#5]]);
- `co_return` is equivalent to `{ p.return_value(…); goto final-suspend; }` ([[stmt.return.coroutine#2]]).

Almost all these rewrites carry an "except that" proviso. For example, the *init-statement* and the condition are in the same scope, whereas a literal rewrite would put them in two nested scopes; and a `continue` in the body of a `for` loop executes the iteration expression first. Many subtle questions arise right where the rewrite meets its proviso.

### Substatements and enclosure

[[stmt.pre]] defines substatements and the enclosure relation. `break` and `continue` must be enclosed by a loop, a `switch` or an expansion statement, and a `case` label must be enclosed by a `switch`. A lambda body is not a substatement, so none of these rules crosses a lambda: a `break` inside a lambda cannot leave an outer loop.

The branches of `if constexpr` and `if consteval` and the body of `template for` are control-flow-limited statements; they cannot be jumped into from outside by `goto` or `case` ([[stmt.label#3]]).

### Jumps and the destruction of automatic variables

However a scope is left, automatic variables already constructed are destroyed in reverse order of construction; this is the language-level foundation of RAII. [[stmt.dcl#2]] puts it this way: when control transfers from point P to point Q, variables that are active at P and not active at Q are destroyed. Conversely, a jump cannot bypass a variable that needs real initialization:

<div class="compare" markdown="1">

```cpp run error
#include <string>
void f(bool b) {
  if (b) goto end;  // error
  std::string s = "x";  // bypassed
end:
  ;
}
```

```cpp run ok
void f(bool b) {
  if (b) goto end;
  int n;   // vacuous initialization, can be bypassed
end:
  n = 1;
  (void)n;
}
```

</div>

### Declarations in conditions

C++ has always allowed a variable to be declared in a condition, as in `if (T* p = get())`. C++17 added the *init-statement* (`if (auto x = f(); x > 0)`), and C++26 allows a structured binding declaration as a condition (`if (auto [p, ec] = std::from_chars(…))`). All three serve the same purpose: make a variable's scope cover exactly the statement that uses it.

## Changes by version

| Version | Changes relevant to this chapter |
|---|---|
| C++98 | The basic statement forms; declarations in conditions; `switch` must not skip initialization; local static variables are initialized the first time control passes through |
| C++11 | Range-based `for`; thread-safe initialization of local static variables; implicit move when `return`ing a local variable; attributes can precede statements |
| C++17 | `if constexpr`; *init-statement* for `if` and `switch`; begin and end of range-based `for` can have different types; `[[fallthrough]]` |
| C++20 | *init-statement* for range-based `for`; `co_return`; `[[likely]]`, `[[unlikely]]`; implicit move applies more widely |
| C++23 | `if consteval`; labels at the end of a block; an *init-statement* can be an alias declaration; lifetime extension of temporaries in the range-based `for` initializer; implicit move further simplified; the condition of `if constexpr` allows narrowing conversions to `bool` |
| C++26 | `template for` expansion statements; `contract_assert`; structured bindings as conditions; trivial infinite loops are no longer UB; `return` binding a temporary to a returned reference becomes ill-formed |

See the notes on each subclause for the detailed rules and papers.
