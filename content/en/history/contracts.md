---
title: "Contracts: pulled from C++20, back in C++26"
summary: Why C++ contracts were pulled out of C++20 entirely in 2019, how the C++26 redesign answers the old disagreements, and the problems that are still open.
tags: contracts, history, safety, standard library hardening
updated: 2026-10-19
---

!!! tldr
    - Contracts put preconditions and postconditions on function declarations, and let the build mode decide what happens on a violation; C's `assert` macro can do neither.
    - The C++20 draft once had a version of contracts (`[[expects: …]]`). It was withdrawn entirely in 2019, before the standard was published, and never appeared in any published standard.
    - The withdrawal came down to three questions without consensus: whether unchecked contracts may be treated as assumptions by the compiler, whether execution may continue after a violation, and whether semantics are set by a global switch or per contract.
    - C++26's answer is four named evaluation semantics (ignore, observe, enforce, quick-enforce), chosen by the implementation; there is no assume semantic; wherever there was no consensus, the construct is ill-formed, leaving room for later extension.
    - The debate is not over: the problem of the same inline function being compiled with different semantics in different translation units, and always-enforced assertions, were left to C++29; contracts on virtual functions are already in the C++29 draft.

## What contracts are for

A function's interface contract has three parts: what the caller must guarantee (the **precondition**), what the function guarantees when it returns (the **postcondition**), and conditions that must hold at some point in the function body (assertions). C's `assert` can only express the third.

<div class="compare" markdown="1">

```cpp
// C's assert: can only go in the function body
#include <cassert>
int isqrt(int x) {
    assert(x >= 0);
    int r = 0;
    while ((r + 1) * (r + 1) <= x) ++r;
    return r;
}
```

```cpp
// C++26: the condition is part of the declaration
int isqrt(int x)
    pre(x >= 0)
    post(r: r * r <= x);
```

</div>

On the left, the condition is hidden in the implementation, invisible at the call site to callers, static analyzers and the compiler; it has only two states, on (`abort`) and off (`NDEBUG`). On the right, the condition is on the declaration and can be checked at the call site; what happens after a violation is chosen by the build mode. Clang 23 cannot compile this C++26 code yet, so none of the contract code on this page is marked with a verdict.

The idea is called **Design by Contract**, popularized by Bertrand Meyer through the Eiffel language in the 1980s. Eiffel also specified how contracts interact with inheritance: an overriding function may only weaken the precondition and strengthen the postcondition. As we will see, that rule caused the longest-running argument in C++.

## Two early attempts

### Following D (2004–2006)

The first proposal, [[N1613]], copied D's approach, adding `in` and `out` blocks before the function body:

```cpp title="N1613 syntax (historical proposal, not adopted)"
int foo(int& i)
in {              // precondition
    i > 0;
}
out {             // postcondition
    i == in i + 1;
    return % 2 == 0;
}
do {              // function body
    ++i;
    return 4;
}
```

It also included class invariants, a syntax for referring to the old value of a parameter (`in i`, renamed several times later), and Eiffel-style inheritance rules. After several revisions it still did not make it into C++0x. Stroustrup's summary is that it failed mainly because its complexity and notation were felt to be too heavy (HOPL IV §9.6.1).

### Assertion macros (2013–2015)

The second attempt came from Bloomberg: [[N3604]] standardized assertion macros the company had long used internally, with three checking levels (safe, debug, optimized), several build modes and a user-definable violation handler. In the last revision, the macro happened to be named `contract_assert`.

This approach did not succeed either. Stroustrup pointed out two problems: it was based on macros, and it was only an assertion inside the implementation, without making the interface itself express anything more (HOPL IV §9.6.1). Still, the two ideas it brought, checking levels and violation handlers, can be found in every design since.

## C++20 contracts: three switches

In 2016 the macro-contracts side and another group of authors focused on static analysis wrote [[P0380R1]] together, which [[P0542R5]] turned into wording; it was merged into the C++20 working draft in 2018. It used a syntax that looked like an attribute but was not one:

```cpp title="Contracts in the C++20 working draft (removed in 2019)"
int f(int x, int y)
    [[expects: x > 0]]           // precondition
    [[expects audit: y != 0]]    // checking level audit
    [[ensures r: r > x + y]]     // postcondition; r is the return value
{
    int n = get_n();
    [[assert: n > 0]];           // assertion
    return x + y + n;
}
```

Whether a contract was checked, and what happened on a violation, was determined by a combination of three switches:

- The **contract level**, written on each contract: `default` is cheap and can be checked even in production; `audit` is expensive and checked only in dedicated builds; `axiom` is only for static analyzers and never checked at run time.
- The **build level**, a global setting: `off`, `default` or `audit`, determining which levels of contracts are checked.
- The **violation continuation mode**, a global setting: whether the program terminates or keeps running after the violation handler returns.

The continuation mode was the most controversial. Bloomberg's experience was that adding contracts to a large old code base always produces violations, and in some cases the code is actually fine and the newly written contract is wrong. If violations can be logged and execution continued, contracts can be turned on in deployed programs and one run can find several problems. This was later accepted by all sides as a prerequisite for adopting contracts gradually (HOPL IV §9.6.1).

## Why they were withdrawn

### Unchecked contracts became assumptions

Under P0542R5's wording, if a contract that was not checked had a false predicate, the behavior was undefined. In other words, with checking off, the compiler could assume the predicate held. Consider:

```cpp title="C++20 contract syntax (example from HOPL IV)"
[[assert: p != nullptr]];
p->m = 7;
```

If checking is on and the continuation mode allows continuing after a violation, the next line still runs after the check fails. The compiler deduces from `p->m` that `p` is not null (otherwise the next line would be UB), and on that basis deletes the check before it. A check meant to find errors gets optimized away by the very error it was supposed to catch; this is often called time-travel optimization (HOPL IV §9.6.1). Some people held that assuming unchecked contracts was exactly the design intent and would help optimization; others held that introducing new UB by adding a contract was unacceptable (P2899R1 §3.5.4).

### Global switch or per-contract semantics

In the second half of 2018, the Bloomberg authors proposed letting each contract spell out its own semantics, for example `[[assert check_maybe_continue: x > 0]]`; [[P1607R1]] in 2019 proposed replacing checking levels with these per-contract semantics. The reasoning was that a three-level scale plus one global continuation switch was not enough: large organizations need to control different libraries and different conditions separately. The opposing side saw this as changing a design that already had consensus on the eve of feature freeze, and possibly turning assertions into a new control-flow mechanism (HOPL IV §9.6.1).

### The withdrawal

In July 2019, at the meeting where C++20's features were frozen, EWG first accepted P1607's direction, then switched to adopting [[P1823R0]], which removed contracts from C++20 entirely. P1823R0's reasons were: there was no consensus on whether the just-accepted changes were an improvement or a step back, with disagreement even among the original design's authors; there was no implementation experience; and under the train model (ship every three years on time, and features that aren't ready take the next train), pushing ahead would put all of C++20 at risk.

After the meeting the contracts study group SG21 was formed. Meanwhile, the need to feed assumptions to the compiler was split off and became C++23's `[[assume]]` attribute ([[P1774R8]], see [[dcl.attr.assume]]). Optimization hints and correctness checks have been two separate tools ever since.

## C++26: starting again from a minimum viable product

### First, list the disagreements

SG21 did not patch the C++20 design; it first went through the reasons for the failure. [[P2076R0]] summarized the disagreements as a few questions, and P2900 gives an explicit answer to each (P2899R1, P2900R14 §3.1):

| Disagreement in C++20 | How C++26 (P2900) handles it |
|---|---|
| Whether unchecked contracts are assumed to hold | No assume semantic. Contracts introduce no new UB, apart from UB in the predicate itself |
| Whether execution may continue after a violation | The observe semantic is kept, but contracts are specified not to be control flow and cannot be used for error handling |
| One level scale controlling checking | Levels removed. Which semantic each evaluation uses is up to the implementation |
| Global switch versus per-contract semantics | C++26 specifies neither, leaving it to implementations and future extensions |

The new design first does only a minimum viable product (MVP): three kinds of assertion, a few semantics, one violation handler, with everything else deferred. [[P2900R14]] was merged into the C++26 draft in February 2025.

### Syntax

C++20's double square brackets were dropped. Contracts are different in nature from attributes: an attribute can be ignored by an implementation, a contract cannot. After comparing several syntaxes, SG21 chose the one from [[P2961R2]]:

<div class="compare" markdown="1">

```cpp
// C++20 draft (removed)
int f(int x)
    [[expects: x > 0]]
    [[ensures r: r > x]]
{
    [[assert: x != 42]];
    return x + 1;
}
```

```cpp
// C++26
int f(int x)
    pre(x > 0)
    post(r: r > x)
{
    contract_assert(x != 42);
    return x + 1;
}
```

</div>

`pre` and `post` are contextual keywords, special only in this position, so they don't break variables named `pre`. The assertion statement uses the new keyword `contract_assert` rather than `assert`, to avoid clashing with C's `assert` macro.

### Three switches become four semantics

In C++20, a contract's behavior had to be derived from the combination of three switches. C++26 lists the possible outcomes directly as four [[g:evaluation-semantic|evaluation semantics]] ([[basic.contract.eval#1]]):

| Semantic | Checks the predicate | After a violation |
|---|---|---|
| ignore | No | — |
| observe | Yes | Calls the violation handler, continues after it returns |
| enforce | Yes | Calls the violation handler, then terminates |
| quick-enforce | Yes | Terminates immediately without calling the handler |

Which one each evaluation uses is implementation-defined ([[basic.contract.eval#2]]); the standard only recommends that implementations provide two compiler options, all-ignore and all-enforce, with enforce as the default ([[basic.contract.eval#3]]). quick-enforce was added later ([[P3191R0]]), for settings that cannot afford the overhead of the violation-handling machinery or want to minimize the attack surface.

The violation handler also changed from an implementation-defined setup mechanism to an ordinary replaceable function, `::handle_contract_violation` (see [[g:contract-violation-handler]], [[support.contract]]):

```cpp title="handler.cpp (C++26, does not compile with Clang 23)"
#include <contracts>
#include <cstdio>

void handle_contract_violation(
    const std::contracts::contract_violation& v) {
    std::fprintf(stderr, "contract violated: %s\n",
                 v.comment());
    // after a normal return: continue under observe, terminate under enforce
}
```

### Where some odd-looking rules come from

P2900 lists a set of design principles, several of which directly explain today's wording:

- In a correct program, contract assertions are redundant. Adding or removing any of them should not change the meaning of a correct program. So contracts do not affect whether a concept is satisfied, the result of overload resolution, or the value of the `noexcept` operator.
- Predicates should have no side effects, and each evaluation is independent. So the standard allows an implementation not to actually evaluate a predicate if it can know its value (in the example in [[basic.contract.eval#5]], the `s.g++` in the predicate may never happen).
- Questions without consensus are specified as ill-formed first, rather than unspecified or undefined. Relaxing them to valid later will not change the meaning of any existing program. That C++26 does not allow `pre`/`post` on virtual functions is an application of this principle.

Another related change is the [[g:observable-checkpoint]] ([[P1494R5]]): output that happened before a contract check is not wiped out by UB after the check ([[basic.contract.eval#6]]). That is the other half of the answer to C++20's time-travel problem.

## Virtual functions: the question that went back and forth most

How do the contracts of an overriding function relate to those of the function it overrides? There are two models.

The first is the inheritance model of Eiffel and D: the overriding function inherits the base class contracts and may weaken the precondition and strengthen the postcondition. The second is the caller/callee model of [[P3097R3]]: each function has its own independent contracts. For a virtual call through a base class reference, the preconditions of the statically chosen function (the base class one) are checked first, then those of the function actually called; postconditions go the other way.

```cpp title="Contracts on virtual functions in the C++29 draft (does not compile with Clang 23)"
struct Shape {
    virtual void scale(double k) pre(k > 0);
};
struct Circle : Shape {
    void scale(double k) override pre(k >= 0);
};

void g(Shape& s) {
    s.scale(2.0);
    // checks the pre of Shape::scale first, then the pre of Circle::scale
}
```

The reasoning: someone calling through `Shape&` only knows `Shape`'s contract and should be checked against it; the author of `Circle` is also entitled to protect their implementation. The cost is that it departs from a classic model decades old, and there is no deployment experience.

SG21 and EWG went back and forth between the two models several times. P3097's model was at one point merged into P2900, then removed at the February 2025 meeting where P2900 went into C++26, so C++26 makes `pre`/`post` on virtual functions ill-formed. In June 2026 P3097R3 was merged into the C++29 working draft; [[expr.call#5]] in the current draft is the checking order described above, and the value of `__cpp_contracts` changed to `202606L` with it. Following the principle of ill-formed first, relax later, this step did not change the meaning of any C++26 program.

## Objections that remained after C++26

P2900 went into C++26 with a considerable number of votes against, and before C++26 was finalized there was a proposal to take it out again. Several of the technical issues among the objections are still being discussed:

- **The predicate itself can have UB.** Contract checks are meant to find errors, but an out-of-bounds access or null pointer dereference inside a predicate is UB all the same. Opponents ([[P3173R0]], [[P3506R0]]) argued this goes against the principle of safety first. P2900's position is that contracts introduce no new UB but do not remove UB in the predicate itself.
- **Which kind of safety contracts provide.** As long as an implementation can choose ignore or observe, contracts cannot guarantee that a given check will stop execution. [[P3500R1]] distinguishes functional safety (the program runs according to its specification) from language safety (no UB), and describes several ways to make assertions always enforced within the existing design.
- **Different translation units compiled with different semantics.** The same inline function or template may be instantiated in several translation units compiled with different semantics, and which copy the linker keeps in the end is not determined. So a library author cannot guarantee that their checks run with enforce ([[P3835R0]]).

The third problem led to proposals for always-enforced assertions ([[P3911R2]], with candidate syntax such as `pre!(…)`), but their ABI impact could not be resolved within the C++26 time frame, and they were pushed to C++29 ([[P3850R0]]). The C++29 roadmap also includes labels on contracts with per-library control over semantics ([[P3400R4]]), and hooking existing assertion macros into the same violation-handling machinery ([[P3290R6]]). Labels effectively bring back the problem C++20's checking levels were trying to solve, only this time the grouping is defined by users.

## Relation to standard library hardening

Standard library hardening ([[P3471R4]]) was merged into C++26 at the same meeting as P2900. It specifies [[g:hardened-precondition|hardened preconditions]] for out-of-bounds and null accesses on `std::span`, `std::string_view`, `std::vector`, `std::optional` and others: in a hardened implementation these conditions are always checked before the call; in a non-hardened implementation, violating them is still UB ([[structure.specifications#3.5]]).

<div class="compare" markdown="1">

```cpp
// non-hardened implementation
std::vector<int> v(3);
int x = v[10];   // UB
```

```cpp
// hardened implementation (C++26)
std::vector<int> v(3);
int x = v[10];   // contract violation,
                 // handled with a terminating semantic
```

</div>

The original wording allowed hardened preconditions to be checked with the observe semantic. But under observe, the out-of-bounds access still happens after the handler returns. [[P3878R1]] argued that hardening must not use observe and was adopted in November 2025; the current draft requires hardened preconditions to be checked with a terminating semantic (enforce or quick-enforce) ([[structure.specifications#3.5.1]]).

## Common misconceptions

!!! pitfall "C++20 has contracts"
    It doesn't. C++20 contracts existed only in the working draft, for about a year, and were removed entirely by P1823 before C++20 was published. GCC once had an experimental implementation of that version, which is not standard C++.

!!! pitfall "C++26 contracts are checked by default"
    The standard does not say so. Which semantic each evaluation uses is implementation-defined ([[basic.contract.eval#2]]); enforce as the default is only a recommended practice ([[basic.contract.eval#3]]), not a requirement.

!!! pitfall "Unchecked contracts are treated as assumptions by the optimizer"
    That was a problem with C++20 contracts. C++26's ignore semantic has no effect at all: the predicate is still potentially evaluated (functions it odr-uses still need definitions), but it is not evaluated ([[basic.contract.eval#4]]). To feed an assumption to the compiler, use `[[assume]]` ([[dcl.attr.assume]]).

!!! pitfall "contract_assert is just assert with a new name"
    `contract_assert` is a statement, not a macro, and is not controlled by `NDEBUG`; its semantic is chosen by the implementation from four; a violation calls the replaceable violation handler; and a predicate that throws an exception also counts as a violation ([[basic.contract.eval#7]]).

## Timeline

| Date | Event |
|---|---|
| 2004–2006 | Proposals modeled on D ([[N1613]] and revisions), not in C++0x |
| 2013–2015 | Bloomberg's assertion macro proposal ([[N3604]]), no consensus |
| 2018-06 | C++20 contracts ([[P0542R5]]) merged into the working draft |
| 2019-07 | Contracts removed from C++20 ([[P1823R0]]); SG21 formed |
| 2020 | The C++20 disagreements written up ([[P2076R0]]) |
| 2022 | `[[assume]]` enters C++23 as a separate feature ([[P1774R8]]) |
| 2023 | P2900 becomes the main proposal; `pre`/`post`/`contract_assert` syntax adopted ([[P2961R2]]) |
| 2025-02 | [[P2900R14]] and standard library hardening ([[P3471R4]]) merged into C++26; support for virtual functions removed at the last moment |
| 2025-11 | Hardened preconditions must not use observe ([[P3878R1]]); always-enforced assertions deferred |
| 2026-03 | C++26 technical work complete, with contracts in it |
| 2026-06 | Contracts on virtual functions merged into the C++29 draft ([[P3097R3]]) |

## References

- Bjarne Stroustrup, *Thriving in a Crowded and Changing World: C++ 2006–2020*, HOPL IV (2020), §9.6.1 *Contracts*. The history before C++20 is mainly based on this.
- Timur Doumler et al., *Contracts for C++ — Rationale*, [[P2899R1]]: §2.6 is a short history of contracts, §3.2 covers syntax, §3.3.2 virtual functions, §3.5.4 evaluation semantics. Written by the authors of P2900.
- [[P2900R14]] *Contracts for C++*; §3.1 lists the design principles.
- [[P1823R0]] *Remove Contracts from C++20*; [[P2076R0]] *Previous disagreements on Contracts*.
- Objections: [[P3173R0]], [[P3506R0]], [[P3573R0]], [[P3829R0]], [[P3835R0]]; responses: [[P3591R0]], [[P3500R1]].
- The C++29 roadmap: [[P3850R0]] *A proposed plan for extending Contracts in C++29*; [[P3097R3]], [[P3400R4]], [[P3290R6]], [[P3911R2]].
- Herb Sutter's trip reports (herbsutter.com): Cologne 2019, Hagenberg 2025, Kona 2025, Croydon 2026, Brno 2026.
