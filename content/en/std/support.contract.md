---
title: Contract-violation handling support
summary: "The header <contracts> provides the types a contract-violation handler uses: contract_violation, which describes one violation, three enumerations, and invoke_default_contract_violation_handler, which calls the default handler."
updated: 2026-10-19
---

!!! tldr
    - When a contract assertion is violated, the implementation creates a `std::contracts::contract_violation` object and passes it to the contract-violation handler `::handle_contract_violation`.
    - The object can only be created by the implementation and can't be copied; the handler reads the assertion kind, evaluation semantic, detection mode, location and predicate text through six member functions.
    - Of the four standard evaluation semantics, only observe and enforce call the handler, and only at run time.
    - A custom handler can call the implementation's default handler with `invoke_default_contract_violation_handler`.
    - All of `<contracts>` is freestanding, and its names are all in `std::contracts`.

C++26 **contract assertions** are a core language feature: `pre` and `post` on function declarations, and the statement `contract_assert`; the rules are in [[basic.contract]]. Each evaluation of a contract assertion uses one of four **evaluation semantics**: ignore doesn't check; observe, enforce and quick-enforce check the predicate, and enforce and quick-enforce terminate the program on violation ([[basic.contract.eval]]).

When an assertion is violated and the semantic is observe or enforce, the implementation calls the **contract-violation handler**, the global function `::handle_contract_violation` ([[basic.contract.handler]]). This subclause defines the type of the argument passed to it.

!!! warning "Compiler support"
    At the time of writing, Clang 23 + libc++ doesn't support contracts yet: the `pre(...)` syntax is an error, and there is no `<contracts>` header. The code on this page is written according to the standard's wording and hasn't been verified by compiling it.

## A custom handler

```cpp
#include <contracts>
#include <cstdio>
namespace sc = std::contracts;

// can only be written if the implementation allows replacing the handler
void handle_contract_violation(const sc::contract_violation& v) {
  std::fprintf(stderr, "%s:%u: %s violated: %s\n",
               v.location().file_name(),
               static_cast<unsigned>(v.location().line()),
               v.kind() == sc::assertion_kind::pre ? "precondition" : "assertion",
               v.comment());
  if (v.detection_mode() == sc::detection_mode::evaluation_exception)
    std::fputs("  the predicate threw an exception\n", stderr);
}
```

The handler receives a `const contract_violation&` and reads all the information about this violation from it. What happens after it returns depends on the evaluation semantic: under observe the program continues from the assertion, and under enforce it is terminated. Under enforce the handler can also throw an exception to avoid termination (the note in [[basic.contract.eval#16]]).

Whether the handler is replaceable is implementation-defined ([[basic.contract.handler#3]]), and can be checked with the feature-test macro `__cpp_lib_replaceable_contract_violation_handler` ([[support.limits]]). If the implementation doesn't allow replacement, a program containing the definition above is IFNDR: ill-formed, but the compiler need not report it.

## Contents of `<contracts>` [contracts.syn]

¶1 The header `<contracts>` defines types for reporting information about contract violations. The whole header is freestanding, meaning freestanding implementations (those without operating system support) must provide it too.

```cpp
namespace std::contracts {
  enum class assertion_kind : unspecified {
    pre = 1, post = 2, assert = 3 };
  enum class evaluation_semantic : unspecified {
    ignore = 1, observe = 2, enforce = 3, quick_enforce = 4 };
  enum class detection_mode : unspecified {
    predicate_false = 1, evaluation_exception = 2 };

  class contract_violation {
    // no user-accessible constructor
  public:
    contract_violation(const contract_violation&) = delete;
    contract_violation& operator=(const contract_violation&) = delete;
    /* see below */ ~contract_violation();

    const char* comment() const noexcept;
    contracts::detection_mode detection_mode() const noexcept;
    bool is_terminating() const noexcept;
    assertion_kind kind() const noexcept;
    source_location location() const noexcept;
    evaluation_semantic semantic() const noexcept;
  };

  void invoke_default_contract_violation_handler(const contract_violation&);
}
```

## The three enumerations [support.contract.enum]

All three are scoped enumerations with unspecified underlying types, and their enumerator values are given explicitly starting from 1.

¶2 `assertion_kind` corresponds to the three forms of contract assertion ([[basic.contract.general]]):

| Enumerator | Meaning |
|---|---|
| `pre` | A precondition assertion ([[dcl.contract.func]]) |
| `post` | A postcondition assertion |
| `assert` | An assertion statement `contract_assert(...)` ([[stmt.contract.assert]]) |

¶3 `evaluation_semantic` corresponds to the four evaluation semantics:

| Enumerator | On violation | Handler called |
|---|---|---|
| `ignore` | Not checked; violations aren't detected | No |
| `observe` | Calls the handler, then continues | Yes |
| `enforce` | Calls the handler, then terminates the program | Yes |
| `quick_enforce` | Terminates the program immediately | No |

So under the standard semantics, `semantic()` in a handler can only be `observe` or `enforce`. Violations during constant evaluation don't call the handler either; they become compile-time diagnostics ([[basic.contract.eval#8]]). The other two enumerators exist to describe the semantics completely and to leave room for implementation extensions.

¶4 `detection_mode` says how the violation was detected:

| Enumerator | Meaning |
|---|---|
| `predicate_false` | The predicate evaluated to `false`, or would have evaluated to `false` |
| `evaluation_exception` | An exception was thrown during evaluation of the predicate and wasn't caught inside it |

The "or would have evaluated to `false`" half comes from [[basic.contract.eval#5]]: under a checking semantic, it is unspecified whether the predicate is actually evaluated, and an implementation may decide using an evaluation with the same result and no side effects instead.

When the predicate throws, the handler is called within an active implicit handler for that exception ([[basic.contract.eval#12]]). So within the handler, that exception is the currently handled exception, obtainable with `std::current_exception()` and rethrowable with `throw;`.

¶1 is a recommendation: if an implementation provides additional enumerators, their values should be no less than 1000, to avoid clashing with enumerators the standard may add in the future.

## `contract_violation` [support.contract.violation]

¶1 An object of type `contract_violation` represents a contract violation: a violation was detected when some contract assertion was evaluated with some evaluation semantic. Such objects can only be created by the implementation; there is no constructor the program can use, and copy construction and copy assignment are deleted. The handler can access it only by reference, and the object lives until the handler returns ([[basic.contract.eval#11]]).

Whether the destructor is virtual is implementation-defined. This lets implementations derive internal types carrying extra information from it.

All six member functions are `const noexcept`:

| Function | Returns |
|---|---|
| `kind()` (¶6) | The form of the violated assertion |
| `semantic()` (¶9) | The semantic used for this evaluation |
| `is_terminating()` (¶5) | Whether the semantic is a terminating one (enforce, quick-enforce) |
| `detection_mode()` (¶4) | How the violation was detected |
| `comment()` (¶2–¶3) | An implementation-defined string in the ordinary literal encoding |
| `location()` (¶7–¶8) | An implementation-defined `source_location` |

¶5 With `is_terminating()`, a handler can know whether the program will be terminated after it returns without enumerating every semantic (including implementation-extended ones).

¶2 `comment()` returns a null-terminated multibyte string. ¶3 recommends that it contain the text of the violated predicate, or be an empty string if storing the text isn't desired. Note 1 says this text may be truncated, reformatted or summarized, and may be in its form before or after preprocessing. These are all just recommendations; an implementation could return an empty string every time to reduce binary size, so program logic shouldn't depend on it.

¶7 The value of `location()` is also implementation-defined. ¶8 recommends that it be either a default-constructed `source_location` or one identifying the violated assertion:

- ¶8.1 when possible, for a precondition violation, the location of the function call;
- ¶8.2 otherwise, the location of the contract assertion itself.

A precondition points at the call site because violating a precondition is the caller's fault, and the log should say who passed the bad argument. "When possible" signals that this isn't a guarantee: for calls through function pointers or virtual functions, the implementation may not know the call site.

## Calling the default handler [support.contract.invoke]

```cpp
void invoke_default_contract_violation_handler(const contract_violation& v);
```

¶1 Effects: calls the **default contract-violation handler**, the handler that comes with the implementation ([[basic.contract.handler]]), with `v` as the argument.

This function is needed because no standard library header declares the default handler ([[basic.contract.handler#1]], Note 1), and once a program replaces `::handle_contract_violation`, the original can no longer be called by name. With it, a custom handler can add its own processing before or after the default behavior instead of rewriting everything:

```cpp
#include <contracts>
#include <cstdio>

void handle_contract_violation(const std::contracts::contract_violation& v) {
  if (v.kind() == std::contracts::assertion_kind::pre)
    std::fputs("[app] the caller violated a precondition\n", stderr);
  // leave formatted output, rate limiting and so on to the default handler
  std::contracts::invoke_default_contract_violation_handler(v);
}
```

[[basic.contract.handler#2]] recommends that the default handler produce formatted output describing the violation, rate-limit repeated observe violations, and then return normally.
