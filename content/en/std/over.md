---
title: Overloading
summary: "A guide to Clause 12: how functions with the same name coexist, how a call picks exactly one of them, and the rules for operator overloading and user-defined literals."
updated: 2026-10-19
---

!!! tldr
    - Functions with the same name in the same scope can coexist as long as their parameter lists and related properties differ; this is overloading. Functions with the same name in different scopes hide each other; that isn't overloading.
    - When a call names an overloaded function, the compiler selects a function in three steps: list the candidate functions, filter out the viable functions, and use implicit conversion sequences to find the unique best one.
    - Overload resolution looks only at types. Access and `= delete` are checked after the selection; if the selected function fails them, the program is ill-formed, and resolution doesn't fall back to the runner-up.
    - Suggested reading order: [[over.pre]] → [[over.match]] → [[over.match.viable]] → [[over.best.ics]] → [[over.ics.rank]] → [[over.match.best]], then [[over.match.oper]] for operators.

C has no overloading, so the absolute value function needs three names: `abs`, `labs`, `fabs`. C++ lets all of them be called `abs` and has the compiler choose based on the argument types. Clause 12 specifies that choice: which declarations with the same name can coexist, and which one a given call actually calls.

```cpp run ok
int    abs(int x)    { return x < 0 ? -x : x; }
double abs(double x) { return x < 0 ? -x : x; }

int main() {
  auto a = abs(1);     // abs(int): int → int needs no conversion
  auto b = abs(1.0);   // abs(double)
  static_assert(sizeof(a) == sizeof(int) && sizeof(b) == sizeof(double));
}
```

## Which declarations can coexist

[[over.pre]] defines overloading. Whether two functions with the same name can coexist is decided in the current draft by the notion of **correspondence** from [[basic.scope.scope]]: two declarations whose parameter-type-lists (after adjustments such as array-to-pointer and dropping top-level const), constraints and object parameters are the same correspond; they declare the same function and don't overload each other. So two declarations that differ only in their return type can't coexist.

## How one function is selected

Overload resolution ([[over.match]]) chooses among the functions found by name lookup, in three steps:

| Step | What it does | Subclauses |
|---|---|---|
| Candidate functions | List the competing functions according to the context of the call (ordinary call, operator, constructor, conversion function, etc.) | [[over.match.funcs]], [[over.match.oper]] |
| Viable functions | The number of arguments fits, constraints are satisfied, and each argument can be implicitly converted to its parameter | [[over.match.viable]] |
| Best viable function | Compare the conversions argument by argument, then apply a series of tie-breakers | [[over.match.best]] |

Conversions are compared by their **implicit conversion sequence**: the steps that convert an argument to the parameter type. [[over.best.ics]] defines what conversions such a sequence consists of, and [[over.ics.rank]] specifies how two sequences are compared; for example, no conversion is better than an integral promotion, and an integral promotion is better than other conversions.

Access control, whether the function is deleted, and so on are checked only after the selection; see [[over.match#3]]. Successful overload resolution doesn't mean the call is valid.

## Operators and the rest

| Subclause | Contents |
|---|---|
| [[over.match.class.deduct]] | Class template argument deduction: one round of overload resolution over the deduction guides |
| [[over.over]] | Taking the address of an overloaded function: `&f` selects by target type |
| [[over.oper]] | Which operators can be overloaded, and in what form they are declared |
| [[over.built]] | The built-in operator candidates imagined for the purpose of overload resolution |
| [[over.literal]] | User-defined literals `operator""_km` |

Since C++20, `a < b` can be rewritten as `(a <=> b) < 0` and `a != b` as `!(a == b)`; these rewritten candidates are covered in [[over.match.oper]], and defaulted `==` and `<=>` in [[class.compare]].

## Prerequisites

Overload resolution only chooses among the results of name lookup ([[basic.lookup]], [[basic.lookup.argdep]]). A function that lookup didn't find is invisible to overload resolution. Implicit conversion sequences consist of standard conversions ([[conv]]) and user-defined conversions ([[class.conv]]), and essentially model copy-initializing the parameter from the argument ([[dcl.init]]). A function template first goes through template argument deduction ([[temp.deduct]]) to produce a specialization, which then enters overload resolution.

[[topics/overload-resolution-walkthrough]] works several classic overload resolution problems from start to finish with per-argument conversion tables; it makes good practice after reading this clause.
