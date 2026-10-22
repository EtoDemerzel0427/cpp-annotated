---
title: Contract assertions
summary: "What C++26 contracts mean at run time: the predicates of pre, post and contract_assert, the four evaluation semantics (ignore, observe, enforce, quick-enforce), contract violations, and the contract-violation handler."
updated: 2026-10-19
---

!!! tldr
    - There are three kinds of contract assertion: `pre` and `post` on function declarations, and the statement `contract_assert`. Outside variables, parameters and `*this` referenced in a predicate are treated as const, so unintended modifications fail to compile.
    - Each evaluation of an assertion uses one of four semantics: ignore doesn't check; observe checks and, on violation, calls the handler and then continues; enforce terminates after calling the handler; quick-enforce terminates immediately. Which one is used is up to the implementation, usually controlled by compiler options.
    - Even under ignore, the predicate must compile and the functions it uses must be defined; this differs from `assert`, which vanishes entirely under `NDEBUG`.
    - A predicate may be evaluated 0, 1 or more times, so predicates should have no side effects.
    - There is an observable checkpoint before and after the check: later UB cannot erase output produced before the check, nor let the compiler delete the check itself.

## An example

```cpp
int isqrt(const int x)
  pre (x >= 0)                                      // precondition: on entry to the function
  post (r : r * r <= x && (r + 1) * (r + 1) > x)    // postcondition: on normal return
{
  int r = 0;
  while ((r + 1) * (r + 1) <= x) ++r;
  contract_assert (r >= 0);                         // assertion statement: when execution reaches here
  return r;
}
```

{{c++26}} A [[g:contract-assertion|**contract assertion**]] makes a property the program state should satisfy at this point part of the language, rather than a comment or a macro. The example shows all three kinds: a **precondition assertion** (`pre`), a **postcondition assertion** (`post`, where `r` names the return value) and an **assertion statement** (`contract_assert`).

This subclause covers what contracts mean at run time. The syntax and declaration rules are in [[dcl.contract.func]], [[dcl.contract.res]] and [[stmt.contract.assert]], and the library interface in [[support.contract]].

!!! warning "Compiler support"
    At the time of writing, Clang 23 does not support the `pre`, `post` and `contract_assert` syntax, and GCC has an experimental implementation on a development branch (not verified; we had no GCC to test with). So none of the examples on this page has been verified by compiling, none carries a verdict, and the conclusions rest entirely on the standard's text. The feature-test macro is `__cpp_contracts`.

### How it differs from assert

The `assert` macro has been in use for decades. Contracts solve several problems it cannot:

1. Preconditions and postconditions are part of the interface. `pre` and `post` are written on the function declaration, visible to callers, static analyzers and compilers; `assert` can only go in the function body.
2. The checking policy is separate from the code. `assert` has only two states, on (`NDEBUG` not defined) and off, decided per translation unit, and mixing them causes ODR problems. Contracts have four evaluation semantics chosen by the implementation, and different evaluations of the same assertion can use different semantics.
3. What happens after a violation is selectable: log and continue, log and terminate, terminate immediately, and the handler can be replaced by the user.
4. A clear line against UB. There are observable checkpoints before and after the check (see ¶6 and ¶15 below), and the compiler cannot use later UB to optimize the check away.

## Predicates [basic.contract.general]

¶1–¶2 Each contract assertion has a **contract-assertion predicate**: the condition in parentheses, contextually converted to `bool`, whose value is used to identify program states that are expected. The predicate is a full-expression ([[intro.execution#5]]), and temporaries in it are destroyed at the end of its evaluation.

The predicate's grammar is *conditional-expression*, not *expression*, so a comma or assignment cannot appear at the top level: `pre (a, b)` is a syntax error; write `pre ((a, b))`.

¶3 An invocation of the `va_start` macro shall not appear in a predicate; no diagnostic is required for a violation {{ifndr}}. `va_start` depends on the stack frame of the enclosing function, while a predicate may be evaluated at the call site.

### Variables in a predicate are const (¶4)

Predicates should not modify program state, and the language uses the type system to turn unintended modifications into compile errors. Note 2 in ¶4 summarizes the rule; the normative wording is in [[expr.prim.id.unqual#7]] and [[expr.prim.this]]:

```cpp
int n = 0;
struct X { bool m(); bool cm() const; };
struct Y {
  int z = 0;
  void f(int i, int* p, int& r, X x, X* px)
    pre (++n)        // error: n is a const lvalue in the predicate
    pre (++i)        // error: the parameter i is const too
    pre (++(*p))     // OK: p is int* const, *p is int
    pre (++r)        // error: the object a reference refers to is treated as const
    pre (x.m())      // error: calls a non-const member function on a const object
    pre (x.cm())     // OK
    pre (px->m())    // OK: only the pointer itself is const
    pre (++z);       // error: this is const Y*
};
```

Specifically, when a predicate names a variable (an object or reference) declared outside the assertion, const is added to the type of the expression; `this` is a pointer to const. The name of the return value in a postcondition is likewise const ([[dcl.contract.res]]).

This is only shallow const; modifying through a pointer is unrestricted, and `++(*p)` is valid. Deep const was deliberately not chosen, because it would need cross-function analysis and would reject too much reasonable code. When a predicate really needs to call a non-const function, an explicit `const_cast` can be written, making the side effect plainly visible in the source.

There is a detail about lambdas in predicates. A copy obtained by capturing by value is a member of the closure, not a variable declared outside the assertion, so it can be modified in a `mutable` lambda; but naming an outer variable directly inside the lambda body (for example a variable captured by reference) still makes it const.

## Four evaluation semantics [basic.contract.eval]

### The semantic is chosen by the implementation (¶1–¶3)

¶1 Each evaluation of a contract assertion uses one of four **evaluation semantics**:

| Semantic | Checks the predicate | Calls the handler on violation | After a violation |
|---|---|---|---|
| ignore | no | | |
| observe | yes | yes | continues if the handler returns normally |
| enforce | yes | yes | terminates the program if the handler returns normally |
| quick-enforce | yes | no | terminates the program immediately |

observe, enforce and quick-enforce are the **checking semantics**; enforce and quick-enforce are the **terminating semantics**.

¶2 Which semantic an evaluation uses is implementation-defined {{impl}}. Note 1 adds that an implementation need not support all four; different evaluations of the same assertion may use different semantics, including in constant evaluation.

The standard deliberately provides no syntax for specifying the semantic in source (there is no `pre<enforce>(...)`), leaving the choice to the build system. The same library code needs different checking policies in development, testing and production builds; that is a deployment decision, not a coding decision.

¶3 The standard recommends that implementations provide two options: one making all assertions use ignore, and one making all assertions use enforce; enforce should be the default.

### ignore: not evaluated, but must compile (¶4)

¶4 Evaluating a contract assertion with the ignore semantic has no effect. Note 2 adds that the predicate is still **potentially evaluated** ([[basic.def.odr]]), merely not evaluated.

```cpp
int helper();                        // declaration only
void f(int x) pre (x > helper());
// as long as f is odr-used, helper is odr-used and must be defined,
// even if all assertions use the ignore semantic
```

So the functions and variables used in a predicate still need definitions, templates are still instantiated ([[dcl.contract.func#9]]), and the predicate must be well-formed. This differs from `assert(expr)` vanishing entirely under `NDEBUG`: contracts are checked by the compiler in every build and cannot quietly rot from going uncompiled for a long time.

### Checking semantics: the value may be inferred (¶5)

¶5 An evaluation A with a checking semantic determines the value of the predicate, but whether the predicate is actually evaluated is unspecified {{unspec}}. Let B be the value that evaluating the predicate would produce. Note 3 explains that an implementation may instead determine B by an evaluation with the same result but without side effects.

```cpp
struct S { mutable int g = 5; } s;
void f() pre (( s.g++, false ));    // #1
void g() {
  f();   // even if #1 uses a checking semantic, s.g is not necessarily incremented
}
```

If the compiler can infer B, it can use the result in place of the predicate, and can also merge several evaluations. Add the permission for repeated evaluation in ¶18 below, and you get a programming discipline:

!!! warning "Predicates should have no observable side effects"
    A predicate's side effects may happen 0, 1 or more times. Predicates that rely on side effects (counting, logging, updating caches) behave differently across builds. Variables being const in predicates is the first line of defense against this kind of mistake.

### An observable checkpoint before the check (¶6)

¶6 Every evaluation A with a checking semantic is preceded by an **observable checkpoint** C: every evaluation that happens before A also happens before C. The meaning of an observable checkpoint is in [[intro.abstract#5]]: undefined behavior can only affect observable behavior after the last checkpoint, and what comes before must be produced faithfully.

```cpp
void f(int* p) pre (p != nullptr) {
  std::printf("calling f\n");
  *p = 42;      // UB here if p is null
}
```

Without a checkpoint, the compiler could reason: `*p` is dereferenced later, so `p` must be non-null, `p != nullptr` is always true, and the check can be deleted. This is the classic case of UB affecting code before it. ¶6 places a checkpoint before the check, protecting everything before the check; and as long as the semantic is a checking one, the check itself must really happen. The concept of the observable checkpoint comes from [[P1494]], which also introduced `std::observable_checkpoint()`.

### What counts as a violation (¶7)

¶7 A [[g:contract-violation|**contract violation**]] occurs when:

- ¶7.1 B is `false`;
- ¶7.2 the evaluation of the predicate exits via an exception;
- ¶7.3 the predicate is evaluated in a **manifestly constant-evaluated** context ([[expr.const.defns]]) and is not a core constant expression, for example because it calls a non-constexpr function.

Note 4 explains that when B is `true`, no violation occurs and control continues normally after the assertion. The evaluation of the predicate can also neither produce a value nor constitute a violation, for example by calling `longjmp` or terminating the program.

### Violations in constant evaluation (¶8)

¶8 If a violation occurs in a manifestly constant-evaluated context and the semantic is a terminating one, the program is ill-formed. Note 5 explains that with the observe semantic a diagnostic is produced, and the program remains well-formed (see [[intro.compliance]]).

```cpp
constexpr int safe_div(int a, int b) pre (b != 0) { return a / b; }
constexpr int k = safe_div(1, 0);
// enforce or quick-enforce: ill-formed
// observe: continues after a diagnostic, but the following 1 / 0 is not a constant expression, so initializing k still fails
// ignore: the check is skipped, and 1 / 0 makes constant evaluation fail
```

Note 6 points out a subtle consequence. If different translation units choose different semantics for the same assertion, and the assertion's side effects change the value of a constant expression, the ODR may be violated:

```cpp
constexpr int f(int i) {
  contract_assert((++const_cast<int&>(i), true));
  return i;
}
inline void g() {
  int a[f(1)];   // whether the array size is 1 or 2 depends on the evaluation semantic of contract_assert
}
```

`g` is an inline function that can be defined in several translation units. If those translation units are compiled with different semantics, `a` has different types in the various definitions. This is yet another cost of predicates with side effects.

## After a violation [basic.contract.eval]

### Contract termination and quick-enforce (¶9–¶10)

¶9 When the program is **contract-terminated**, whether this means calling `std::terminate`, calling `std::abort`, or terminating execution directly is implementation-defined, and may depend on context {{impl}}. Note 7 explains that no further execution steps occur ([[intro.progress]]); note 8 explains that performing the actions of `terminate` or `abort` without actually calling the library functions also conforms.

¶10 If a violation occurs in a context that is not manifestly constant-evaluated and the semantic is quick-enforce, the program is contract-terminated immediately, without calling the contract-violation handler.

quick-enforce aims to terminate as quickly as possible with minimal impact on code size (note 11). A typical implementation is a single trap instruction (`ud2` on x86, `brk` on AArch64), requiring neither the construction of a `contract_violation` object nor storage for source-location strings. It suits scenarios like security hardening that require checks enabled in production but cannot accept code bloat.

### Calling the contract-violation handler (¶11–¶16)

¶11 If a violation occurs in a context that is not manifestly constant-evaluated and the semantic is enforce or observe, the **contract-violation handler** (see [basic.contract.handler] below) is invoked with an lvalue referring to an object v of type `const std::contracts::contract_violation`, which contains information about the violation. Storage for v is allocated in an unspecified manner, not through the global `operator new` ([[basic.stc.dynamic.allocation]]), and its lifetime lasts until the handler invocation ends.

¶12 If the violation was caused by the predicate throwing an exception, the handler is invoked from within an active implicit handler for that exception ([[except.handle]]). Note 9 points out that the handler can therefore inspect or rethrow the exception. If the handler returns normally and the semantic is observe, that implicit handler is no longer active, as if the exception had been caught and swallowed.

¶13 If the handler returns normally and the semantic is enforce, the program is contract-terminated. If the violation came from an exception thrown by the predicate, the implicit handler is still active at termination.

¶14 Note 10 explains that if the handler returns normally and the semantic is observe, control continues normally after the assertion.

¶15 There is also an observable checkpoint after the handler returns normally: every evaluation that happens after the return comes after this checkpoint. This guarantees that log output written by the handler is in the protected part and cannot be erased by later UB. This matters especially under observe, because execution continues after the violation and often enters UB soon afterward.

¶16 Note 11 summarizes the uses of the three checking semantics: enforce gives the program a chance to log information about the violation before terminating, or to throw an exception to avoid termination; quick-enforce terminates as quickly as possible with as little code size impact as possible; observe logs information without terminating, suitable for gradually introducing new contracts in production: run with observe for a while to confirm there are no false positives, then switch to enforce.

### The handler throws an exception (¶17)

¶17 If a handler invoked from a function contract assertion (`pre`, `post`) exits via an exception, the effect is as if the function body exited via that exception.

```cpp
void f(int x) noexcept pre (x > 0);
// when the precondition is violated and the handler throws: as if f's body threw, and f is noexcept, so std::terminate is called
```

Note 12 adds two consequences. A *function-try-block* is the function body itself, so it cannot catch this exception. When the function has a non-throwing exception specification, `std::terminate` is called: `noexcept` is the function's promise to its callers, and an exception thrown by the handler cannot cross it either. So adding a precondition to a `noexcept` function means you cannot rely on the handler throwing to recover.

Note 13 explains that if a handler invoked from a `contract_assert` exits via an exception, the exception propagates from that statement, like an ordinary `throw`.

## Evaluation in sequence and repeated evaluation (¶18–¶19)

¶18 To **evaluate in sequence** a list R of contract assertions: first construct a list S such that every element of R is in S, each element may be repeated an implementation-defined number of times, and an assertion earlier in R first appears earlier in S; then evaluate the elements of S in order, each sequenced before the next.

```cpp
void f(int i) {
  contract_assert(i > 0);   // #1
  contract_assert(i < 10);  // #2
  // valid evaluation sequences: #1 #2, #1 #1 #2 #2, #1 #2 #1 #2, #1 #2 #2 #1
  // invalid: #2 #1 (the first occurrence of #2 is earlier than #1)
}
```

All of a function's preconditions ([[expr.call#8]]), all its postconditions ([[expr.call#10]]), and consecutive `contract_assert` statements ([[stmt.contract.assert#3]]) are evaluated in sequence.

Repetition is allowed mainly so that both caller and callee can check: a precondition can be checked once at the call site under the caller's translation-unit options and again at function entry under the callee's, and the implementation need not deduplicate. Repeated evaluation is also a testing tool for discovering predicates with side effects. ¶19 recommends that implementations provide an option to evaluate each assertion a specified number of times, with no repetition by default.

## The contract-violation handler [basic.contract.handler]

¶1 The **contract-violation handler** of a program is a function named `::handle_contract_violation` with a single parameter of type `const std::contracts::contract_violation&`, returning `void`, possibly with a non-throwing exception specification. The implementation must provide a definition, called the **default contract-violation handler**. Note 1 explains that no standard library header declares the default handler; to call it explicitly, use `std::contracts::invoke_default_contract_violation_handler` ([[support.contract]]).

¶2 The standard recommends that the default handler produce suitably formatted diagnostic output with the most relevant contents of the `contract_violation`, rate-limit output for violations that recur under the observe semantic, and then return normally.

¶3 Whether the handler is **replaceable** ([[dcl.fct.def.replace]]) is implementation-defined {{impl}}. If the implementation does not allow replacement, a program declaring a replacement function is ill-formed, no diagnostic required {{ifndr}}. When replacement is allowed, it can be written like this:

```cpp
#include <contracts>
#include <cstdio>

void handle_contract_violation(const std::contracts::contract_violation& v) {
  using namespace std::contracts;
  auto loc = v.location();
  const char* what = v.kind() == assertion_kind::pre  ? "precondition"
                   : v.kind() == assertion_kind::post ? "postcondition"
                                                      : "assertion";
  std::fprintf(stderr, "%s:%u: %s violated: %s\n", loc.file_name(),
               static_cast<unsigned>(loc.line()), what, v.comment());
  if (v.detection_mode() == detection_mode::evaluation_exception)
    std::fputs("  (predicate threw an exception)\n", stderr);
  // after returning: observe continues execution, enforce terminates the program
}
```

The interface of `contract_violation` ([[support.contract.violation]]):

| Member | Meaning |
|---|---|
| `comment()` | an implementation-defined string, recommended to be the text of the predicate; may be truncated or empty |
| `detection_mode()` | `predicate_false` or `evaluation_exception` |
| `is_terminating()` | whether the semantic is a terminating one |
| `kind()` | `pre`, `post` or `assert` |
| `location()` | an implementation-defined `source_location`; for preconditions, the location of the call site is recommended |
| `semantic()` | the semantic used for this evaluation; the handler is called only under observe and enforce, so with standard semantics it can only be one of those two |

`contract_violation` has no user-accessible constructors and can only be created by the implementation.

## Connections to other subclauses

- The order of a function call ([[expr.call#8]], [[expr.call#10]]): parameters are initialized first, then preconditions are evaluated and the function body executes; on normal return, postconditions are evaluated, before the parameters are destroyed.
- Postconditions using parameters ([[dcl.contract.func#7]]): if a `post` predicate odr-uses a non-reference parameter, that parameter must be const in all declarations. The function body may modify parameters, and without this restriction the postcondition would not see the value the caller passed.

    ```cpp
    int f(int x) post (r : r > x);         // error: x is not const
    int g(const int x) post (r : r > x);   // OK
    ```

- Construction and destruction ([[class.base.init#18]]): calling a member function in a constructor's precondition or a destructor's postcondition is UB, because the object's lifetime has not yet begun or has already ended.
- Redeclarations ([[dcl.contract.func#4]], [[dcl.contract.func#5]]): a function's contracts are introduced only by its first declaration; later declarations either omit them or repeat them exactly. If first declarations in different translation units disagree, no diagnostic is required.
- Deleted functions and functions defaulted on their first declaration cannot have contracts ([[dcl.contract.func#6]]).
- Function pointers ([[dcl.contract.func#8]]): contracts belong to the function, not its type; they are still evaluated when called through a pointer, and function pointer types themselves cannot carry contracts.
- Overload resolution does not consider contracts (note 6 of [[dcl.contract.func#9]]).

## History

!!! history "From C++20 contracts to C++26 contracts"
    - [[P0542R5]] once merged contracts into the C++20 working draft, with attribute syntax `[[expects: x > 0]]`, `[[ensures r: r > 0]]`, `[[assert: ...]]`, and three checking levels `default`, `audit` and `axiom`. The dispute centered on assumption semantics (violating a contract is UB, allowing compilers to optimize on that basis) and on the design of build modes, and contracts were removed entirely before C++20 shipped.
    - The subsequent redesign started from a minimum viable product, explicitly excluded assumption semantics, and gradually settled on the evaluation semantics ignore, observe, enforce, and the later-added quick-enforce.
    - C++26 introduced today's contracts with [[P2900]]. The syntax changed to the contextual keywords `pre` and `post` and the new keyword `contract_assert` (not `assert`, to avoid clashing with C's macro); observable checkpoints come from [[P1494]].

## Common misconceptions

!!! pitfall "Contracts can be used to validate input"
    Contract checks may be ignored. Untrusted input from users or the network must be validated with ordinary code. A contract expresses a property that must hold here if the program is correct; a violation means the program has a bug.

!!! pitfall "A predicate's side effects happen exactly once"
    ¶5 allows not evaluating it (as long as the value can be determined), and ¶18 allows repeated evaluation. Something like `pre (log_call())` behaves differently in different builds.

!!! pitfall "Postconditions are checked when an exception is thrown too"
    Postconditions are associated only with normal return (note 1 of [[dcl.contract.func#1]]). When a function is left by throwing an exception or by `longjmp`, `post` is not evaluated.

!!! pitfall "Under observe, the program is safe after a violation"
    Under observe the program keeps running after a violation, and a violated precondition was often there precisely to prevent the UB that follows. The checkpoint of ¶15 only guarantees that the log has been written, not that nothing will crash afterward.

## Questions

!!! question "Question 1"
    Which of the preconditions below are ill-formed?
    ```cpp
    int g;
    struct S {
      int m;
      void f(int a, int& b, int* c) const
        pre (a++ > 0)
        pre (b = 1)
        pre (*c = 1)
        pre (m > 0)
        pre ((g = 1, true));
    };
    ```

<details markdown="1">
<summary>Answer</summary>

- `pre (a++ > 0)`: ill-formed; `a` is const in the predicate.
- `pre (b = 1)`: first of all a syntax error, since the predicate must be a *conditional-expression* and cannot be an assignment expression directly. Writing `pre ((b = 1))` doesn't work either: the object `b` refers to is treated as const.
- `pre (*c = 1)`: likewise a syntax error. Written as `pre ((*c = 1))` it is well-formed, because `c` is `int* const` and `*c` is a modifiable `int`, though it is terrible style.
- `pre (m > 0)`: well-formed, read-only.
- `pre ((g = 1, true))`: ill-formed; `g` is const in the predicate.
</details>

!!! question "Question 2"
    An assertion is evaluated with the observe semantic, the predicate throws an exception, and the handler returns normally. Where does the exception go?

<details markdown="1">
<summary>Answer</summary>

It is swallowed. Per ¶12, the handler is invoked within an active implicit handler for the exception; under observe, after the handler returns normally, the implicit handler is no longer active, which is like a `catch (...) {}` completing, and control continues after the assertion (¶14). To let the exception propagate, the handler can rethrow it with `throw;`; for `pre` and `post` this is as if the function body threw that exception (¶17).
</details>

!!! question "Question 3"
    Why is the predicate still potentially evaluated under the ignore semantic? What are the costs and benefits?

<details markdown="1">
<summary>Answer</summary>

The benefit is that predicates must compile in every build: name lookup, type checking and template instantiation all happen as usual. Assertion expressions under `NDEBUG` can quietly rot, for example referring to a variable that has since been deleted without anyone noticing; contracts don't have this problem. The cost is that functions and variables odr-used by predicates must have definitions, which may add link dependencies, and templates in predicates are instantiated, increasing compile time.
</details>

## Summary

| Concept | Key points | Source |
|---|---|---|
| Three kinds of assertion | `pre`, `post`, `contract_assert`; the predicate is a full-expression of type `bool` | [[basic.contract.general#1]], [[basic.contract.general#2]] |
| const in predicates | outside variables, parameters and `*this` are all const (shallow) | [[basic.contract.general#4]] |
| Four semantics | ignore, observe, enforce, quick-enforce; chosen by the implementation, may differ per evaluation | [[basic.contract.eval#1]], [[basic.contract.eval#2]] |
| ignore | not evaluated, but the predicate is potentially evaluated | [[basic.contract.eval#4]] |
| Checking semantics | may not really evaluate; an observable checkpoint before the check | [[basic.contract.eval#5]], [[basic.contract.eval#6]] |
| Violation | predicate false, throws, or not a constant expression in constant evaluation | [[basic.contract.eval#7]] |
| Violation in constant evaluation | ill-formed under terminating semantics; a diagnostic under observe | [[basic.contract.eval#8]] |
| After a violation | quick-enforce terminates directly; enforce and observe call the handler and, after it returns, terminate or continue respectively | [[basic.contract.eval#10]]–[[basic.contract.eval#14]] |
| Handler throws | `pre`, `post`: as if the function body threw; `contract_assert`: propagates from the statement | [[basic.contract.eval#17]] |
| Evaluation in sequence | repetition allowed, but the order of first occurrences is preserved | [[basic.contract.eval#18]] |
| The handler | `::handle_contract_violation`; replaceability is implementation-defined | [[basic.contract.handler]] |
