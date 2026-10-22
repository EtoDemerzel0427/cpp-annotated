---
title: C++ and ISO C++ 2026
summary: "The three incompatible changes merged into the working draft after C++26 was finalized: deallocation functions with potentially-throwing exception specifications, designated initializers that can designate base class members, and defaulted assignment operators with cv or && qualifiers."
updated: 2026-10-19
---

!!! tldr
    - This subclause lists changes merged into the working draft after C++26 was finalized that invalidate valid C++26 code. There are only three so far, all marked {{c++29}} below.
    - `operator delete` can no longer be declared potentially-throwing, for example with `noexcept(false)`.
    - Designated initializers can designate members of an aggregate's base class, so `f({.a = 1})`, which used to match a single overload, may become ambiguous.
    - A `= default` assignment operator can no longer carry a `const` or `&&` qualifier, and a move assignment's parameter cannot be `const T&&`.
    - As of Clang 23.1.3 none of the three is implemented; the old code compiles as before under both `-std=c++2c` and `-std=c++2d`.

All three changes turn well-formed code into ill-formed code; none silently changes behavior. Clang uses `-std=c++2d` for the version after C++26 (`__cplusplus` is `202700L`), but none of the three takes effect in either mode.

## Deallocation functions cannot be declared potentially-throwing [diff.cpp26.basic]

```cpp error
struct T {
  void operator delete(void*) noexcept(false);   // error: ill-formed now; well-formed in C++26
};
```

¶1 The change is in [[basic.stc.dynamic.deallocation]]. **Deallocation functions** are `operator delete` and `operator delete[]`. They are called by a *delete-expression* and during cleanup after a constructor throws, and C++26 says the behavior is undefined if a deallocation function terminates by throwing an exception. Since anything you could declare would necessarily be UB to use, the new rule simply forbids the declaration; the stated rationale is removing potential undefined behavior.

A deallocation function with no exception specification is already implicitly `noexcept` ([[except.spec]]). So the only declarations affected are those that explicitly say `noexcept(false)`, or `noexcept(expr)` where the expression may evaluate to `false`. The fix is to delete it; if the function body really contains an operation that may throw, that was already a defect and needs to be made non-throwing.

## Designated initializers can designate base class members [diff.cpp26.dcl]

```cpp
struct A { int a; };
struct B : A { int b; };

void f(A);              // #1
void f(B);              // #2

void g() {
  f({.a = 1});          // now: #1 and #2 are ambiguous; C++26: calls #1
}
```

¶1 The change is in [[dcl.init]], with the details in [[dcl.init.aggr]]. It is a new feature: aggregates have been allowed to have base classes since C++17, but in C++26 a designated initializer can only designate direct non-static data members of the class itself, and base class members can only be initialized positionally, as in `B{{1}, 2}`. Now `.a` can also designate the member of base class `A`.

The new feature breaks old code through overload resolution. In C++26, `{.a = 1}` can only initialize an `A`, so only #1 is viable. Under the new rule it can also initialize a `B`; both candidates need one list-initialization conversion, neither is better, and the call is ambiguous. The ambiguity in [[diff.cpp20]] caused by UTF-8 literals being able to initialize `char` arrays is the same kind of problem.

Clang 23 selects #1 in both modes. Until compilers implement the new rule this problem cannot be detected; the fix is to name the type: `f(A{.a = 1})`.

## Defaulted assignment operators cannot have cv or && qualifiers

```cpp error
struct S {
  S& operator=(const S&) && = default;      // error: ill-formed now; well-formed in C++26
};
struct T {
  T& operator=(const T&) const = default;   // error: ill-formed now; well-formed but deleted in C++26
};
struct U {
  U& operator=(const U&&) = default;        // error: ill-formed now; well-formed but deleted in C++26
};
```

¶2 The change is in [[dcl.fct.def.default]]. An explicitly defaulted assignment operator can no longer have a *cv-qualifier-seq* or a `&&` *ref-qualifier*; an explicitly defaulted move assignment operator cannot have a parameter of type reference to cv-qualified `T`. The stated rationale is removing a rare and easily misunderstood form.

The three forms fare differently in C++26:

- The declarations of `T` and `U` compile, but their types do not match the implicitly declared assignment operator, so the function is defined as deleted and any call is an error. The new rule just turns a silent deletion into an immediate error.
- The `&&`-qualified version in `S` can be called normally in C++26, only on rvalues. This is a feature that was genuinely removed; the fix is to drop the `&&` or write a user-provided body.

Clang 23 gives only a `-Wdefaulted-function-deleted` warning (explicitly defaulted ... is implicitly deleted) for `T` and `U`, and no diagnostic at all for `S`.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[diff.cpp26.general] ¶1 only says that this subclause lists the differences from ISO C++ 2026, by chapter of the main text.

</details>

## Summary

| Entry | C++26 | Current draft | Clang 23 |
|---|---|---|---|
| `operator delete(void*) noexcept(false)` | well-formed | ill-formed | not implemented |
| `f({.a = 1})` with overloads `f(A)`, `f(B)`, `B` derived from `A` | calls `f(A)` | ambiguous | not implemented |
| defaulted assignment with `const`, `&&`, or a `const T&&` parameter | well-formed (the last two deleted) | ill-formed | not implemented |
