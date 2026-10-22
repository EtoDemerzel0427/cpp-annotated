---
title: The assertion statement (contract_assert)
summary: "C++26's contract_assert statement: writing a contract assertion in a function body, with the predicate contextually converted to bool and consecutive assertions evaluated in sequence as a group; and how it differs from the assert macro and the assume attribute."
updated: 2026-10-19
---

!!! tldr
    - `contract_assert(condition);` is a C++26 statement that introduces a contract assertion, sharing the same evaluation rules as `pre` and `post` on functions.
    - Only a *conditional-expression* can go in the parentheses: assignment and comma expressions need another pair of parentheses.
    - Variables from outside that appear in the predicate are treated as const, so the predicate cannot modify them directly; whether the predicate is evaluated, and how many times, is not guaranteed, so do not rely on its side effects.
    - Whether it is checked and what happens on failure are decided by the evaluation semantic the implementation chooses (ignore, observe, enforce, quick-enforce), independently of `NDEBUG`.
    - Several adjacent assertion statements are evaluated in sequence as a group; an implementation may evaluate the group repeatedly, but the order of first occurrence does not change.

At the time of writing, Clang 23 does not recognize `contract_assert` and treats it as an undeclared identifier. The examples on this page were analyzed against the standard text and not verified by compiling, so they carry no verdict markers.

## An assertion statement

```cpp
#include <cstddef>
int at(const int* p, std::size_t n, std::size_t i) {
    contract_assert(p != nullptr);
    contract_assert(i < n);
    return p[i];
}
```

A [[g:contract-assertion|contract assertion]] is the basic unit of C++26 contracts: it carries a **predicate**, a `bool` expression describing a condition the program should satisfy at that point. Contract assertions come in three forms: preconditions `pre(...)` and postconditions `post(...)` on function declarations ([[dcl.contract]]), and the assertion statement of this subclause. The evaluation and violation handling of all three are specified uniformly in [[basic.contract]]; this subclause specifies only what is particular to the statement form.

The grammar is:

```text
assertion-statement:
    contract_assert attribute-specifier-seq(opt) ( conditional-expression ) ;
```

`contract_assert` is a keyword ([[lex.key]]). `pre` and `post`, by contrast, are just identifiers with special meaning in particular positions of a function declarator. The name does not use `assert` because `assert` has long been a macro in `<cassert>`.

¶1 An *assertion-statement* introduces a contract assertion. Attributes written between the keyword and the opening parenthesis appertain to that contract assertion, not to the statement.

It is a statement, so it can appear anywhere a statement is allowed: function bodies, lambda bodies, loop bodies, branches of `if`, including in `constexpr` and `consteval` functions. It cannot appear inside an expression, such as in a member initializer list or a default argument. Where a check is needed in those positions, the condition can be put in the called function's `pre`, or wrapped in an immediately invoked lambda.

## Only a conditional expression goes in the parentheses

```cpp
void f(int x) {
    contract_assert(x = 1);           // error: an assignment expression is not a conditional-expression
    contract_assert(x > 0, x < 10);   // error: a comma expression is not a conditional-expression
    contract_assert((x > 0, x < 10)); // syntactically OK, but only checks x < 10
}
```

The grammar requires a *conditional-expression*, which lacks the assignment and comma levels of *expression*. So mistyping `==` as `=` becomes an outright syntax error. And `contract_assert(a, b)` is not silently read as a comma expression that checks only `b`. When these operators really are needed, add another pair of parentheses.

## The predicate (¶2)

¶2 The predicate of an assertion statement is its *conditional-expression* [[g:contextually-converted-to-bool|contextually converted to bool]], the same conversion `if (e)` applies to its condition. So pointers, integers, and class types with an `explicit operator bool` can all be written directly.

There is another rule for predicates, from [[expr.prim.id.unqual#7]]: if a name refers to a variable declared outside the assertion, the type of the expression is const-qualified. `this` in a predicate is also a pointer to const ([[expr.prim.this#3]]). That way the predicate cannot directly modify the state it checks:

```cpp
#include <vector>
void g(std::vector<int>& v, int i) {
    contract_assert(++i > 0);                 // error: i here is const int
    contract_assert(v.emplace_back(1) == 1);  // error: v is const, so a non-const member cannot be called
}
```

The const is added only to the name itself; it does not propagate through pointers, and it does not stop `const_cast` or `mutable` members. A predicate with side effects can still be written by deliberately circumventing it, but those side effects need not happen; see the next section.

## Evaluation semantics

Each evaluation of a contract assertion uses one of four [[g:evaluation-semantic|evaluation semantics]] ([[basic.contract.eval#1]]). Which one is chosen is up to the implementation, typically controlled by compiler options, and different evaluations of the same assertion may differ ([[basic.contract.eval#2]]). The standard recommends enforce as the default.

| Semantic | Is the predicate checked? | When the predicate is false |
|---|---|---|
| ignore | no | nothing happens |
| observe | yes | the contract-violation handler is called, and execution continues after it returns normally |
| enforce | yes | the contract-violation handler is called, and the program is terminated after it returns normally |
| quick-enforce | yes | no handler is called; the program is terminated immediately |

The last three are called checking semantics. Even under a checking semantic the predicate is not necessarily evaluated: the implementation may replace it with a computation that has the same result and no side effects ([[basic.contract.eval#5]]). Under ignore the predicate is not evaluated, but it is still potentially evaluated, so the functions and variables used in it are still odr-used.

An assertion statement is not a macro and does not pass through the preprocessor; `NDEBUG` has no effect on it.

The contract-violation handler may throw an exception. For an assertion statement, the exception continues looking for a handler outward from the position of the statement (Note 13 in [[basic.contract.eval#17]]). The case of `pre` and `post` is different: there the exception appears as the function body exiting via that exception.

### Violations during constant evaluation

```cpp
constexpr int checked_div(int a, int b) {
    contract_assert(b != 0);
    return a / b;
}
constexpr int ok  = checked_div(6, 3);   // OK
constexpr int bad = checked_div(1, 0);   // violation
```

When a violation occurs during constant evaluation, the outcome depends on the semantic of that evaluation ([[basic.contract.eval#8]]). Under enforce and quick-enforce the program is ill-formed. Under observe the implementation must issue a diagnostic and may then continue, but the following `1 / 0` is not a constant expression, so the initialization of `bad` fails anyway. Under ignore it likewise gets stuck on the division by zero. So this initialization fails under every semantic; the only difference is which error is reported.

## Consecutive assertions are evaluated in sequence (¶3)

¶3 The evaluation of several consecutive assertion statements is an **evaluation in sequence** ([[basic.contract.eval#18]]) of the contract assertions they introduce.

```cpp
void f(int i) {
    contract_assert(i > 0);    // #1
    contract_assert(i < 10);   // #2
}
// valid evaluation sequences: #1 #2; #1 #1 #2 #2; #1 #2 #1 #2; #1 #2 #2 #1
// invalid: #2 #1
```

An evaluation in sequence allows the implementation to evaluate each assertion an implementation-defined number of times, the only constraint being that the order of each assertion's first occurrence matches the source. So `#2 #1` is not allowed, while `#1 #2 #2 #1` is.

Repetition is allowed for the benefit of tools and testing: a predicate without side effects should give the same result however many times it is evaluated, and repeated evaluation exposes predicates that do have side effects. The standard recommends that implementations offer an option for repeated evaluation, but not repeat by default ([[basic.contract.eval#19]]). Assertions separated by some other statement are not consecutive and belong to two groups.

## Compared with the assert macro and `[[assume]]`

| | `assert(e)` | `contract_assert(e);` | `[[assume(e)]];` |
|---|---|---|---|
| What it is | a preprocessor macro ([[cassert.syn]]) | a statement introducing a contract assertion | an attribute on a null statement ([[dcl.attr.assume]]) |
| How to turn it off | define `NDEBUG` | the implementation chooses the ignore semantic | it cannot be turned off |
| When `e` is false | calls `abort` | depends on the evaluation semantic | undefined behavior |
| Is `e` evaluated? | yes, when `NDEBUG` is not defined | unspecified | never |
| Outside variables are const in `e` | no | yes | no |
| Usable in an expression | yes | no | no |

`[[assume]]` points the opposite way from contract assertions. A contract assertion means "please check this condition, and report it if it does not hold"; `[[assume(e)]]` means "I guarantee `e` holds, and the compiler may optimize on that basis; if it does not, the behavior is undefined".

With `assert`, if `NDEBUG` is set inconsistently across translation units, the same inline function has different definitions, violating the ODR. The evaluation semantic of a contract assertion is not part of the definition, so this problem generally does not arise. Only when the side effects of a predicate change the value of some constant expression can different semantic choices lead to an ODR violation (Note 6 in [[basic.contract.eval#8]]).

## Common misconceptions

!!! pitfall "Doing useful work in the predicate"
    A predicate may not be evaluated (under ignore, or when replaced by an equivalent computation), and it may be evaluated several times (repetition in an evaluation in sequence). Side effects the program depends on, such as logging, counting or modifying state, should not go in a predicate.

!!! pitfall "After the assertion, the following code is safe"
    Under the observe semantic, the program continues executing after the contract-violation handler returns. With `contract_assert(p != nullptr); use(*p);`, what follows is still a null pointer dereference. Code after an assertion must either tolerate the condition not holding, or be sure it is never deployed with the observe or ignore semantic.

## History and evolution

!!! history
    - The C++20 working draft once had contracts based on attribute syntax (`[[expects]]`, `[[ensures]]`, `[[assert]]`), which were removed wholesale before C++20 was published; the disagreements centered on whether execution could continue after a violation and how build modes should be configured.
    - The later design entered C++26 as [[P2900R14]]: the syntax changed to the `contract_assert` keyword and `pre`, `post`, and per-evaluation evaluation semantics replaced the earlier build levels.
    - In C++23 and earlier, assertions in a function body could only use the `assert` macro from `<cassert>` or vendor extensions.

## Questions

!!! question "Question 1"
    Is the code below well-formed? What is the value of `n` after calling `g()`?
    ```cpp
    int n = 0;
    void f(int* p) { contract_assert((*p = 1, true)); }
    void g() { f(&n); }
    ```

<details markdown="1">
<summary>Answer</summary>

It is well-formed. The const is added only to the name `p` appearing in the predicate, making its type `int* const`; `*p` is still a modifiable `int` lvalue. The outer parentheses make the comma expression a *primary-expression*, which satisfies the grammar.

But whether the assignment happens is unspecified: under ignore the predicate is not evaluated; under a checking semantic the implementation may see that the predicate is always `true` and skip evaluating it ([[basic.contract.eval#5]]); with repeated evaluation it may assign several times. So `n` may be 0 or 1.
</details>

!!! question "Question 2"
    In `contract_assert(x > 0); log(); contract_assert(x < 10);`, may the implementation check `x < 10` before `x > 0`?

<details markdown="1">
<summary>Answer</summary>

No. A statement separates them, so the two assertions are not consecutive; each is evaluated on its own, in the execution order of the statements. Only consecutive assertion statements form a group evaluated in sequence (¶3), and even within a group the order of first occurrence must match the source.
</details>
