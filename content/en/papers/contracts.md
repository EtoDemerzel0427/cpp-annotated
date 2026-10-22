---
title: Contracts (P2900)
summary: How P2900 made preconditions, postconditions and assertions part of the language. Why pre/post/contract_assert rather than attribute syntax or assert; why whether to check is left to the build instead of written on each assertion; why predicates are treated as const and may be evaluated zero or more times; and the gaps the minimum viable product leaves on purpose, along with the objections that remain.
tags: contracts, proposal, C++26, assertions, design trade-offs
group: C++26
updated: 2026-10-19
---

!!! tldr
    - P2900 introduces three kinds of contract assertions: `pre` and `post` on function declarations, and the `contract_assert` statement in function bodies. The conditions are written on the interface, where both callers and tools can see them.
    - Which of ignore, observe, enforce and quick-enforce each evaluation uses is up to the implementation (usually a compiler option); the code can neither specify nor query it.
    - Predicates should have no side effects: they may be evaluated zero, one or more times, and any outside variable named in a predicate is treated as const.
    - A value parameter used in a postcondition must be const on every declaration; otherwise the function body could modify the parameter and the postcondition would lose its meaning.
    - Virtual functions, class invariants, old values, an assumption semantic and per-assertion semantics are all outside the minimum viable product. Objections remain to this day, for example to UB inside predicates and to semantics being chosen by the implementation.

## Before contracts: comments and assert

What a function requires of its callers used to be written only in comments, and then checked again in the function body with `assert`:

```cpp
#include <cassert>
#include <cstddef>

// requires: p is non-null, i < n
int at(const int* p, std::size_t n, std::size_t i) {
    assert(p != nullptr);
    assert(i < n);
    return p[i];
}
```

This has three problems. First, the conditions are hidden in the function body; the compiler and static analyzers at the call site cannot see them unless the function is inlined. Second, `assert` has only two states, on and off, decided by whether `NDEBUG` is defined in each translation unit. Third, `assert` is a macro: when it is turned off, the preprocessor deletes the whole argument, and any side effects in the argument vanish with it:

```cpp title="assert.cpp" run ok
#include <cassert>
#include <cstdio>

int calls = 0;
bool check() { ++calls; return true; }

int main() {
    assert(check());          // the side effect vanishes with NDEBUG
    std::printf("calls = %d\n", calls);
}
```

With Clang 23, it prints `calls = 1` without `-DNDEBUG` and `calls = 0` with it. The macro also has syntax problems of its own: a comma in the argument not enclosed in parentheses splits the argument, and `assert(std::is_same_v<T, int>);` gives "too many arguments provided to function-like macro invocation" in Clang.

The long history of contracts (D-style `in`/`out` blocks, Bloomberg's assertion macros, the `[[expects:]]` of the C++20 draft and why it was withdrawn) is covered in [[history/contracts]]. This page only covers the design of [[P2900R14]]: after the C++20 failure it was redesigned with a minimum viable product (MVP) as the goal, and merged into the C++26 draft in February 2025.

## Syntax: why pre, post and contract_assert

### What it looks like

```cpp title="C++26 (does not compile with Clang 23)"
int f(const int x)
    pre(x != 1)                  // precondition
    post(r: r == x && r != 2)    // postcondition; r names the return value
{
    contract_assert(x != 3);     // assertion statement
    return x;
}
```

`pre` and `post` go at the very end of the declarator: after the trailing return type and the `requires` clause, immediately before the semicolon or the function body (the grammar in [[dcl.contract.func]]; for class members they also come after `override`, see [[class.mem.general]]). They are contextual keywords with special meaning only in this position; a variable named `pre` is unaffected. `contract_assert` is a full keyword ([[stmt.contract.assert]]), because it has to be distinguished from a function call.

The grammar inside the parentheses is *conditional-expression*, not an arbitrary expression. So `pre(a = b)`, where `==` was mistyped as `=`, is ill-formed; if you really want an assignment you need another pair of parentheses (P2900R14 §3.2).

### The attribute-like syntax that was abandoned

The C++20 draft used notation like `[[expects: x > 0]]`. During the P2900 discussions it was still a candidate ([[P2935R3]]), and was finally replaced by the notation of [[P2961R2]]. The reasons given in P2961R2 §1 fall into three groups:

1. Contracts are not attributes. Standard attributes are designed to be ignorable (removing one does not change the meaning of the program), but contracts cannot be ignored: they may terminate the program, and when the handler throws they even open a new control-flow path out of the middle of a function. Double square brackets would make users think the two are the same kind of thing.
2. Wrong position. Attributes follow the thing they appertain to. The position for attributes of a function type is before the trailing return type, `override` and the `requires` clause, which goes against reading order and would force postconditions to be parsed late; assertions could only be attached to null statements and could not be used as expressions.
3. Too little room to extend. In `[[post r: …]]` there is only one slot before the colon. Later additions such as labels, captures or a return-value name in structured-binding form would all be crowded into that one spot, creating ambiguities: is an identifier before the colon a label or a return-value name? Are square brackets a capture or a structured binding?

Two other alternatives were also compared: [[P2461R1]] put the predicate in braces, which looks like a lambda, but a predicate is an expression, not a statement; [[P2737R0]] was the first to adopt the `keyword(predicate)` structure, but also proposed renaming to `precond`/`postcond`/`incond`, using a predefined name `result`, and so on, and these additional choices were not well received in SG21 (P2961R2 §2). P2961R2 kept the basic structure and dropped the rest.

### Why not call it assert

The most natural name is `assert`, which nearly every language uses. P2961R2 §5.2 lists several ways to make it coexist with the `<cassert>` macro and rejects each one:

| Option | Problem |
|---|---|
| Remove `<cassert>` | Breaks a large amount of existing code, including code shared between C and C++ |
| Make `assert` a keyword with contract-assertion behavior | The macro's behavior depends on `NDEBUG`. Even if `NDEBUG` were mapped to the ignore semantic, under ignore the predicate is still parsed and odr-used, so debug variables declared only inside `#ifndef NDEBUG` would no longer compile |
| A macro if `<cassert>` is included, a contract otherwise | The meaning of the same line `assert(x)` would depend on whether a header was included somewhere else; the author of a library header could not tell |

The only option left was a different keyword. P2961R2 compared a set of candidates and finally chose `contract_assert`. This new keyword is an incompatibility of C++26 with C++23, recorded in [[diff.cpp23.lex#2]]: C++23 code that uses `contract_assert` as an identifier is no longer valid. Another is in [[diff.cpp23.cpp#1]]: identifiers with special meaning such as `pre` and `post` can no longer be defined as macros.

## Four semantics, chosen by the build

### Semantics are not written on the assertion

Each evaluation of a contract assertion uses one of four [[g:evaluation-semantic|evaluation semantics]] ([[basic.contract.eval#1]]):

| Semantic | Checks the predicate | After a violation |
|---|---|---|
| ignore | No | Nothing happens |
| observe | Yes | Calls the contract-violation handler, then continues after it returns |
| enforce | Yes | Calls the contract-violation handler, then terminates the program after it returns |
| quick-enforce | Yes | Does not call the handler; terminates immediately |

¶2 Which one is used is implementation-defined, and different evaluations of the same assertion may differ ([[basic.contract.eval#2]]). ¶3 Only a recommended practice is given: provide compiler options for all-ignore and all-enforce, with enforce as the default.

P2900 deliberately provides no way to specify the semantic in source code. Among the features not proposed listed in §2.3 are writing the semantic directly on an assertion and assigning levels to assertions (C++20's `default`/`audit`/`axiom`). §3.5.5 gives the reasoning: when a programmer writes an assertion, they are stating what ought to hold at that point; whether to check it and what to do on failure are deployment decisions, to be determined by how the program is built. A platform may also provide only some of the semantics; for example, a safety-critical embedded platform might not offer observe at all.

### No compile-time query

`assert` has `NDEBUG` to test; contracts deliberately have no counterpart. P2900's Principle 5 requires that which semantic an evaluation uses should in general not be detectable at compile time, otherwise turning checks on would amount to compiling a different program (§3.1.1). The same principle explains why the predicate is still potentially evaluated under ignore ([[basic.contract.eval#4]]): the predicate must always compile, code does not rot from checks being turned off for a long time, and switching semantics does not change the rest of the program.

This has a direct consequence: the same inline function may be compiled with different semantics in two translation units. P2900 §3.5.11 calls this mixed mode and considers it not an ODR violation in itself, since the two definitions have identical tokens. Which copy the linker ends up keeping is effectively random on implementations that don't change the linker. The authors consider this better than making mixed compilation IFNDR, since IFNDR amounts to program-wide UB. The draft acknowledges an ODR violation in only one case: the predicate has side effects and they change the value of some constant expression ([[basic.contract.eval#8]], Note 6).

### Compile-time evaluation

Contract assertions are also evaluated during constant evaluation. There is no handler to call then: under observe a violation only produces a diagnostic, and under enforce and quick-enforce a violation makes the program ill-formed ([[basic.contract.eval#8]]). A predicate that is not a core constant expression during constant evaluation also counts as a violation ([[basic.contract.eval#7]] ¶7.3).

### Why quick-enforce exists

enforce has to construct a `contract_violation` object and call the handler, which generates a fair amount of code. A note in the draft explains that quick-enforce is for terminating as quickly as possible while minimizing the impact of checks on code size ([[basic.contract.eval#16]]). How it terminates is implementation-defined too: calling `std::terminate`, calling `std::abort`, or simply ending execution ([[basic.contract.eval#9]]); the last option lets an implementation insert just a trap instruction.

## The contract-violation handler

When a violation happens at run time under observe or enforce, the program calls the [[g:contract-violation-handler|contract-violation handler]] `::handle_contract_violation` ([[basic.contract.handler#1]]). The implementation provides a default version, and whether users may replace it is implementation-defined ([[basic.contract.handler#3]]). Replacing it works like replacing the global `operator new`: define a function with the same name and signature in the program.

```cpp title="handler.cpp (C++26, does not compile with Clang 23)"
#include <contracts>
#include <cstdio>

void handle_contract_violation(
    const std::contracts::contract_violation& v) {
    std::fprintf(stderr, "%s:%u: %s\n",
                 v.location().file_name(),
                 v.location().line(),
                 v.comment());
}
```

Two details come from explicit choices in P2900 §3.5.9. No standard library header declares this function ([[basic.contract.handler#1]], Note 1), so the user's replacement can decide for itself whether to be `noexcept`; `operator new` is declared by the library, so a replacement has to follow its exception specification. `contract_violation` has no constructor usable by users, so a violation cannot be faked outside the handler.

The members of `contract_violation` ([[support.contract.violation]]) report the text of the predicate, the source location, the kind of assertion, the semantic used, whether that semantic is terminating, and how the violation was detected: the predicate was false, or the predicate threw an exception. P2900R14 also had an `evaluation_exception()` member, which is no longer in the class definition in the current draft. The handler is called within an implicit handler for that exception ([[basic.contract.eval#12]]), and can rethrow it.

The handler itself may throw. When it throws out of a function contract assertion, the effect is as if the function body threw that exception, so a `noexcept` function calls `std::terminate` ([[basic.contract.eval#17]]). P2900 §3.6.6 points out the cost of this design: as long as a platform allows installing a handler that may throw, the compiler must assume every contract assertion may throw.

## Predicates may be evaluated zero or more times

### The redundancy principle

P2900 §3.1 builds the whole design on a set of principles. The first two are:

- **The Prime Directive**: the presence or evaluation of a contract assertion should not change whether a program is correct.
- **The redundancy principle**: in a correct program, contract assertions are redundant; removing any of them does not change the correctness of the program.

It follows that a predicate's side effects must not be something the program depends on. P2900 does not make predicates with side effects ill-formed, because the compiler cannot tell which side effects are harmful (logging is usually harmless), and such a restriction would be too strict (§3.1.2). Instead it does not guarantee how many times side effects happen:

```cpp title="Example from P2900R14 §3.5.8 (does not compile with Clang 23)"
int i = 0;
void f() pre((++i, true));

void g() {
    f();   // i may be 0, 1, 17, ...
}
```

Zero times comes from [[basic.contract.eval#5]]: when evaluating with a checking semantic, it is unspecified whether the predicate is actually evaluated, and the implementation may use an expression without side effects that produces the same result instead. Multiple times comes from evaluation in sequence in [[basic.contract.eval#18]]: all the preconditions of a function (or all its postconditions, or a run of adjacent `contract_assert`s) form a group, and the assertions in it may be repeated an implementation-defined number of times, as long as the order of each assertion's first occurrence is unchanged. One common source is both the caller and the callee checking once each (P2900R14 §3.5.7).

The argument of `assert` is evaluated either zero times (with `NDEBUG` defined) or exactly once. Old code that depends on this needs adjusting when converted to contracts. The example in P2900 §3.6.7 is adapted from the Clang source: `assert(++nIter < 6)` increments a counter in the assertion, which is wrong as a contract. The correct way is to move the state maintenance out of the assertion and leave the predicate to only test:

```cpp title="counter.cpp" run ok
#include <cassert>
bool keep_iterating(unsigned i) { return i < 5; }

int main() {
    unsigned n_iter = 0;
    while (keep_iterating(n_iter)) {
        ++n_iter;               // state maintained outside the assertion
        assert(n_iter < 6);     // the predicate has no side effects
    }
}
```

Replace this `assert` with `contract_assert` and the meaning stays the same under every semantic.

### Names become const automatically

To catch predicates that unintentionally modify state as early as possible, P2900 makes names in a predicate that refer to outside variables const lvalues ([[expr.prim.id.unqual#7]]), makes `this` a pointer to const ([[expr.prim.this#3]]), and makes the result binding const as well ([[expr.prim.id.unqual#6]]). This is the same idea as members becoming const in a const member function.

```cpp title="(does not compile with Clang 23)"
int global = 0;
void f(int x, char* p, int& ref)
    pre((x = 0) == 0)    // error: x is a const lvalue
    pre((*p = 5))        // OK: const is shallow and does not go through the pointer
    pre((ref = 5))       // error: the object a reference refers to is treated as const too
    pre((global = 2));   // error
```

The const is added only at the level of the name and does not go through pointers. P2900 §3.4.2 explains that deep const would make raw pointers and smart pointers behave differently. `mutable` members can still be modified, and `const_cast` can get around it, but modifying an object that really is const is still UB.

This rule has a less intuitive consequence: moving the same expression into a predicate can change the result of overload resolution.

<div class="compare" markdown="1">

```cpp
// contract (does not compile with Clang 23)
struct X {};
bool p(X&);        // returns true
bool p(const X&);  // returns false

void f(X x)
    pre(p(x));     // picks p(const X&)
```

```cpp
// equivalent C++23
#include <utility>
// p declared as on the left
void g(X x) {
    p(x);                 // p(X&)
    p(std::as_const(x));  // inside a predicate
}                         // it is like this
```

</div>

The full version of the right side was checked with Clang 23: `p(x)` picks `p(X&)`, and `p(std::as_const(x))` picks `p(const X&)`. P2900 considers an overload set that gives different answers depending on constness to be defective in itself. Opponents see it differently; see below.

## Postconditions: return value and parameters

### The result binding

The `r` in `post(r: …)` is called the **result binding**; it refers to the object or reference returned by the function ([[dcl.contract.res#1]]) and is a const lvalue in the predicate. The user picks its name, rather than using a predefined `result`; that was exactly one of P2737R0's additional choices that was rejected.

If the return type is deduced and there is no earlier declaration, the postcondition cannot be parsed until the function body determines the type, so a postcondition with a result binding can only be written on the definition ([[dcl.contract.res#2]]).

For types that can be passed in registers, an implementation may first construct a temporary object and then copy it to the final result object. The postcondition may see that temporary, so an assertion comparing addresses such as `post(r: &r == ptr)` may fail ([[dcl.contract.res#1]] Example 2, [[expr.prim.id.unqual#14]]). P2900 §3.4.5's position is that the values are guaranteed to be the same, and users should not depend on the identity of the two objects.

### Value parameters must be const

If a postcondition odr-uses a non-reference parameter, that parameter must have const type on every declaration of the function ([[dcl.contract.func#7]]), even though top-level const is ignored elsewhere. P2900 §3.4.4 uses `clamp` to show why:

```cpp title="The problem without the const rule (does not compile with Clang 23)"
double clamp(double lo, double hi, double v)
    post(r: (v < lo && r == lo) || (v > hi && r == hi)
            || r == v);

double clamp(double lo, double hi, double v) {
    lo = hi = v = 0.0;    // satisfies the postcondition, but is useless
    return 0.0;
}
```

A postcondition is written for callers to read, and `v` should mean the value the caller passed in. If the function body can modify parameters, the postcondition checks the modified values, and there is no way to know that from the declaration alone. The modification may also be implicit: in `std::string g(std::string p) post(r: r.starts_with(p)) { return p; }`, `return p` moves from `p`, and the postcondition sees the moved-from string. Requiring the parameter to be const means the function body cannot change it.

The same reasoning leads to two corollaries. Array parameters decay to pointers, and `const int a[10]` decays to `const int*`, not `int* const`, so using an array parameter in a postcondition is always ill-formed ([[dcl.contract.func#7]] Example 2). A coroutine copies its parameters into the coroutine frame, ignoring const when copying, and can modify them afterwards as usual, so a coroutine postcondition that odr-uses a value parameter is ill-formed too ([[dcl.fct.def.coroutine#6]] Note 1).

## Other restrictions

- Only the first declaration counts. A function's contract is introduced by its first declaration; later declarations either omit it or repeat it exactly ([[dcl.contract.func#4]]). If the first declarations in different translation units disagree, the program is IFNDR.
- Not part of the type. Contracts are not part of the function type; function pointers, pointers to member functions and type aliases cannot carry contracts. But when calling indirectly through a pointer, the callee's contract is still checked ([[dcl.contract.func#8]]). This means an implementation cannot always check at the call site; sometimes it must check inside the function or in a thunk.
- Overload resolution does not see contracts. Contracts do not affect overload resolution ([[dcl.contract.func#9]] Note 6), nor the result of the `noexcept` operator, nor whether a concept is satisfied (P2900 Principle 3).
- Construction and destruction. A constructor's preconditions are evaluated before members are initialized, and a destructor's postconditions after members are destroyed; reading members directly at that point is UB. So referring to members through an implicit `this->` in these two places is ill-formed ([[expr.prim.id.general#2]]); when needed you must write `this->` explicitly, and use only the address, without reading the value.
- Defaulted and deleted functions. A function that is `= default` or `= delete` on its first declaration cannot have contracts ([[dcl.contract.func#6]]).

## Gaps the MVP leaves on purpose

P2900R14 §2.3 lists features deliberately not proposed, and says they will be proposed separately as extensions later:

| Not proposed | Status |
|---|---|
| `pre`/`post` on virtual functions | Ill-formed in C++26; the approach of [[P3097R3]] is in the C++29 draft: a virtual call first checks the preconditions of the statically chosen function, then those of the function actually called ([[expr.call#5]]) |
| Contracts on function pointers and type aliases | Not supported |
| Referring to old values of parameters in postconditions | Not supported; only const parameters are available |
| An assumption semantic (unchecked predicates assumed to hold, for optimization) | Not provided; for optimization hints use C++23's `[[assume]]` ([[P1774R8]], [[dcl.attr.assume]]) |
| Writing the semantic on an assertion, assertion levels | Not provided; the semantic is chosen entirely by the implementation |
| Postconditions on exit via exception | Not supported; postconditions are only evaluated on normal return ([[dcl.contract.func#1]]) |
| Predicates that cannot be evaluated at run time (such as calls to functions without definitions) | Not supported; predicates are always potentially evaluated |
| State kept across assertions (like variables inside `#ifndef NDEBUG`) | Not supported |
| Class invariants, procedural interfaces | Not supported |

How the deferred parts are written into the wording is governed by Principle 14 (P2900R14 §3.1.4): constructs without consensus are made ill-formed, not unspecified or undefined. Relaxing them to be valid later then does not change the meaning of any existing program. `pre` on a virtual function being ill-formed in C++26 and becoming valid in the C++29 draft followed exactly this path.

The assumption semantic deserves a separate remark. One reason C++20 contracts were withdrawn was precisely that unchecked contracts were treated as assumptions, which in turn allowed the checks themselves to be optimized away. P2900's Principle 13 says contracts introduce no new UB (§3.1.4), so ignore really does nothing; the need to inject facts into the compiler is served by `[[assume]]`, and from then on the two are different tools. In R14's draft `<contracts>`, `evaluation_semantic` has a commented-out line `assume = 5`, marked as an anticipated future extension (§3.7.1).

## Controversy: some public objections

P2900 was not adopted into C++26 unanimously. Below, two papers of objections are summarized by technical issue, together with P2900's own position on each.

UB in predicates. [[P3173R0]] argues that allowing UB during predicate evaluation goes against the consensus SG21 had earlier reached to put safety first; it also argues that a contract facility without support for virtual functions and function pointers is insufficient, and asks for its application to the standard library to be demonstrated first. P2900R14 §3.6.1 acknowledges this: contracts introduce no new UB, but predicates are ordinary expressions, and their own UB stays. Its example is `pre(f(a) > a)` where `f(a)` returns `a + 100`: the compiler may assume signed addition does not overflow and optimize the whole precondition to `true`, even under enforce. Observable checkpoints ([[g:observable-checkpoint]], [[basic.contract.eval#6]], [[basic.contract.eval#15]]) only protect against UB outside the assertion reaching back to affect the assertion.

Too much is implementation-defined. [[P3573R0]] lists a dozen or so concerns, several of which directly target the design choices discussed above:

- The semantic and the manner of termination are both chosen by the implementation, so ordinary users can hardly know what will be checked and what happens on failure, and portable contracts are hard to write;
- contracts cannot be grouped and switched on and off separately;
- when translation units compiled with different settings are linked together, which setting templates and inline functions end up with is not specified clearly;
- const-ification (names becoming const automatically) is a new irregular rule, and warnings could catch most of the errors it aims at;
- a predicate throwing should not count as a violation, but should propagate normally like any other exception;
- the approach for virtual functions has no implementation experience, and many designs need contracts to be inherited.

P2900 makes explicit choices on all of these, and the reasons have been covered above: leaving semantics to the build follows directly from Principle 5 and Principle 12 (contracts are not control flow); mixed mode is considered better than IFNDR; a throwing predicate counts as a violation because a predicate that does not produce a value has failed to confirm that the contract holds (§3.5.6). The disagreement is over whether the costs of these trade-offs are acceptable, not over the facts. Follow-up work such as group control (labels) and assertions that are always enforced, and the debate that continued after adoption into C++26, are covered in [[history/contracts]].

## Where the wording lives

| Subclause | Contents |
|---|---|
| [[basic.contract.general]] | What contract assertions and predicates are; `va_start` cannot appear in a predicate |
| [[basic.contract.eval]] | The four semantics, determining a violation, the handling process, evaluation in sequence and repetition |
| [[basic.contract.handler]] | `::handle_contract_violation`, the default version and replacement |
| [[dcl.contract.func]] | Syntax of `pre`/`post`, the first declaration, the const parameter rule |
| [[dcl.contract.res]] | Result binding |
| [[stmt.contract.assert]] | The `contract_assert` statement |
| [[expr.prim.id.unqual]], [[expr.prim.this]] | Const-ification of names and `this` in predicates |
| [[support.contract]] | The `<contracts>` header and `contract_violation` |
| [[diff.cpp23.lex]], [[diff.cpp23.cpp]] | The new keyword; `pre`/`post` cannot be macro names |

The feature-test macro is `__cpp_contracts`; its value in the current draft is `202606L` ([[cpp.predefined]]).

!!! impl "Compiler support"
    Homebrew Clang 23.1.3 does not support contracts: `pre(…)` gives "expected function body after function declarator", `__cpp_contracts` is not defined, and libc++ has no `<contracts>` header. The contract code on this page therefore carries no verdicts, and the conclusions are based on the standard wording and P2900R14. A development branch of GCC has an implementation following P2900; GCC was not available for testing, so it has not been verified.

## Common misconceptions

!!! pitfall "`contract_assert` is `assert` with a new name"
    It isn't. It is a statement, not a macro; it is not controlled by `NDEBUG`, and its predicate must always compile; the number of evaluations is not guaranteed to be 0 or 1; outside variables are const inside the predicate, so the same expression may pick a different overload; and a violation goes through the contract-violation handler.

!!! pitfall "observe can be used for error handling"
    P2900's Principle 12 says explicitly that contracts are not control flow. The same assertion may be ignore in another build, so errors that must be handled (such as validating external input) need ordinary `if` and exceptions, not contracts.

!!! pitfall "Writing `pre` guarantees the function is never entered with the condition violated"
    Only terminating semantics give that guarantee, and which semantic is used is up to the implementation. Even under enforce, UB in the predicate itself can cause the check to be optimized away.

## Questions

!!! question "1"
    What is wrong with the postcondition below? How do you fix it?
    ```cpp
    int scale(int x, int k)
        post(r: r == x * k);
    ```

<details markdown="1">
<summary>Answer</summary>

The postcondition odr-uses the non-reference parameters `x` and `k`, so by [[dcl.contract.func#7]] they must be const on every declaration (including the definition). Here they are not, so the program is ill-formed. Change it to `int scale(const int x, const int k) post(r: r == x * k);`, and write the definition with `const int` too. Then the function body cannot modify `x` and `k`, and the postcondition checks the values the caller passed in. Incidentally, when `x * k` overflows the predicate itself has UB, and the contract won't protect you from it.
</details>

!!! question "2"
    A function has two preconditions, `pre(a) pre(b)`. Which of these evaluation sequences are valid: `a b`, `a b a b`, `b a`, `a a b`, `b`?

<details markdown="1">
<summary>Answer</summary>

`a b`, `a b a b` and `a a b` are valid; `b a` and `b` are not. By [[basic.contract.eval#18]], the implementation may repeat the assertions in the list any (implementation-defined) number of times, but each assertion must occur at least once, and the order of first occurrences must match the declaration order. `b a` has `b` occur first before `a`, and `b` leaves out `a`.
</details>

!!! question "3"
    Why does `<contracts>` not declare `handle_contract_violation`, while `<new>` does declare the replaceable `operator new`?

<details markdown="1">
<summary>Answer</summary>

If the library provided a declaration, the user's replacement would have to match its exception specification. Without one, the user can decide whether the handler is `noexcept`: a project that wants to turn violations into exceptions can let it throw, and a project that wants a guarantee of no throwing can mark it `noexcept` ([[basic.contract.handler#1]], P2900R14 §3.5.9). On the other hand, `contract_violation` has no constructor usable by users, so even with a declaration, users could not call it outside the handler.
</details>
