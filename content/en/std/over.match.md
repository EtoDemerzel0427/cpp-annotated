---
title: Overload resolution
summary: "The framework of overload resolution: seven contexts each list their candidate functions, then a uniform procedure filters the viable functions and picks the unique best one; access control and = delete are checked only after the selection."
updated: 2026-10-19
---

!!! tldr
    - Overload resolution has three steps: list the candidate functions, filter out the viable functions, and use implicit conversion sequences to pick the unique best viable function.
    - The seven contexts (ordinary call, call of a function object, operator, constructor, two kinds of conversion function, reference binding) each list candidates differently; the last two steps are identical.
    - If there is no viable function, or none is better than all others (ambiguity), the call is ill-formed.
    - Access control and `= delete` take no part in the selection: if the selected function is inaccessible or deleted, the program is ill-formed; resolution doesn't switch to the next best function.
    - A usable candidate means resolution succeeded and selected a built-in operator or a non-deleted, accessible function; the term mainly serves defaulted comparisons.

## Three steps: candidate, viable, best (¶1–¶2)

```cpp run ok
#include <cstdio>
void f(int)         { std::puts("f(int)"); }
void f(double)      { std::puts("f(double)"); }
void f(int, int)    { std::puts("f(int,int)"); }
void f(const char*) { std::puts("f(const char*)"); }

int main() {
  f('a');   // prints f(int)
}
```

For the call `f('a')`, name lookup finds four `f`s; they are all **[[g:candidate-function|candidate functions]]**. `f(int, int)` has the wrong number of parameters and `f(const char*)` can't be converted to from `char`, so both are eliminated; the remaining `f(int)` and `f(double)` are the **[[g:viable-function|viable functions]]**. `char → int` is an integral promotion and `char → double` a floating-integral conversion; the promotion is better, so `f(int)` is the **best viable function**.

¶1 Overload resolution selects, from a set of candidate functions, the one that best fits a given argument list. The basis is the number of arguments, how well the arguments match the parameter types, (for non-static member functions) how well the object matches the object parameter, and some other properties of the candidates, such as whether they are templates and how strong their constraints are; see the tie-breakers in [[over.match.best#2]].

¶2 Overload resolution is performed in the following seven contexts, each of which determines the candidate functions and the argument list in its own way:

| | Context | Example | Where the candidates come from |
|---|---|---|---|
| ¶2.1 | A function named in function call syntax | `f(x)`, `obj.m(x)` | [[over.call.func]] |
| ¶2.2 | A class object called with call syntax: `operator()`, or a conversion function to a function pointer or function reference | `fn(x)` where `fn` is an object | [[over.call.object]] |
| ¶2.3 | An operator in an expression | `a + b`, `!a` | [[over.match.oper]] |
| ¶2.4 | A constructor for default- or direct-initialization of a class object | `T t(1, 2);` | [[over.match.ctor]] |
| ¶2.5 | A user-defined conversion for copy-initialization of a class object | `T t = u;` (where `u` isn't of type `T`) | [[over.match.copy]] |
| ¶2.6 | A conversion function for initializing a non-class object from an expression of class type | `int i = obj;` | [[over.match.conv]] |
| ¶2.7 | A conversion function whose result a reference binds to directly | `int& r = obj;` | [[over.match.ref]] |

List-initialization ([[over.match.list]]) and class template argument deduction ([[over.match.class.deduct]]) also reuse this machinery. Taking the address of an overloaded function ([[over.over]]) isn't overload resolution; it matches by target type under different rules.

Once the candidate functions and the argument list are determined, the selection is the same in all contexts:

- ¶2.8 first the **viable functions** are filtered out: the number of arguments fits, constraints are satisfied, and each argument has an implicit conversion sequence to its parameter ([[over.match.viable]]);
- ¶2.9 then, based on the **[[g:implicit-conversion-sequence|implicit conversion sequence]]** each argument needs (the steps that convert the argument to the parameter type), the **best viable function** is selected ([[over.match.best]]).

## After the selection: access control and deletion (¶3)

¶3 If there is a unique best viable function, overload resolution succeeds and produces it as the result. Otherwise overload resolution fails and the call is ill-formed. There are two kinds of failure: there is no viable function at all, or there are viable functions but none is better than all others; the latter is **ambiguity**.

After resolution succeeds, if the selected function is inaccessible at the point of use, the program is ill-formed.

```cpp error
class C {
  void f(int);          // private
public:
  void f(double);
};
void use(C& c) {
  c.f(1.0);             // OK: selects f(double)
  c.f(1);               // error: selects f(int), but it is private
}
```

`f(double)` could take `1` perfectly well, but overload resolution ignores access: it first selects the exact match `f(int)`, then checks access, which fails. This is what Note 1 in ¶1 says: the function selected by overload resolution isn't guaranteed to be usable in the given context.

The design lets access control only reject a choice, never change it. If `private` members disappeared from the candidates, the same call would select different functions inside and outside the class; a class author making a member `private` could silently change which function outside code calls. As it is, such a change can at most cause a compile error.

Deleted functions ([[dcl.fct.def.delete]]) work the same way: they take part in overload resolution as usual and cause an error only once selected. This is what lets `= delete` prohibit certain conversions:

```cpp error
void take(double);
void take(int) = delete;   // don't let int silently convert to double
void use() {
  take(1.0);               // OK
  take(1);                 // error: selects the deleted take(int)
  take(1.0f);              // OK: float → double is a promotion, better than float → int
}
```

If deleted functions didn't take part in resolution, `take(1)` would call `take(double)`, and the `= delete` would be pointless.

!!! lawyer "An exception: defaulted move operations defined as deleted"
    [[over.match.funcs#9]] says that a defaulted move constructor or move assignment operator that is defined as deleted isn't a candidate in any context. Otherwise, initializing a class with a non-movable member from an rvalue would select the deleted move constructor and fail, instead of falling back to the copy constructor.

## Usable candidates (¶4)

¶4 If overload resolution succeeds and the selected candidate is either not a function (that is, a built-in operator candidate, [[over.built]]) or a function that is not deleted and is accessible from the context of the resolution, the result is said to be a **[[g:usable-candidate|usable candidate]]**.

This term is used by C++20 defaulted comparisons. A defaulted `==` performs `==` member by member; if some member's `==` isn't a usable candidate, the outer `= default` doesn't cause an error but is defined as deleted ([[class.compare]]):

```cpp run ok
struct NoEq {
  bool operator==(const NoEq&) const = delete;
};
struct S {
  NoEq m;
  bool operator==(const S&) const = default;   // defined as deleted
};
template<class T>
concept EqComparable = requires(const T& a, const T& b) { a == b; };
static_assert(!EqComparable<S>);
int main() {}
```

Clang gives a `-Wdefaulted-function-deleted` warning for `S::operator==`, saying it is implicitly defined as deleted.

!!! impl "Compiler implementation"
    Clang and GCC both implement the three steps candidate, viable, best, and record why each non-viable candidate was eliminated. The "candidate function not viable: no known conversion from ... to ..." lines in diagnostics explain one by one why candidates aren't viable. To select the best function, Clang first makes one pass to find a candidate that is not worse than any rival, then a second pass to confirm it is indeed better than all other candidates; this is exactly the linear algorithm described in the footnote of [[over.match.best]].

!!! history
    The three-step algorithm, the seven contexts and access checking after resolution were all established in C++98. Later revisions only added to them: list-initialization, ref-qualifiers and deleted functions in C++11; class template argument deduction in C++17; constraints, rewritten candidates for `==`/`<=>` and the usable candidates of ¶4 in C++20; explicit object parameters in C++23.

## Common misconceptions

!!! pitfall "private or deleted makes the compiler pick the next best function"
    It doesn't. If the best function is unusable, the program is ill-formed. To keep an overload out of the competition for outside callers, make name lookup not find it (for example, put it in another scope), or use a constraint so that it is eliminated during the viability stage.

!!! pitfall "Two viable functions means ambiguity"
    The number of viable functions doesn't matter, as long as one is better than all the others. Ambiguity means there is no unique best one; the typical case is A being better on the first argument and B better on the second (see the example in [[over.match.best#3]]).

## Questions

!!! question "1. Which function does each of these calls select? Is the program well-formed?"
    ```cpp nocheck
    struct S {
      void g(long);
    private:
      void g(int);
    public:
      void call() { g(1); }
    };
    void h(S s) { s.g(1); }
    ```

<details markdown="1">
<summary>Answer</summary>

Both select `S::g(int)`: `int → int` is an exact match, which beats the integral conversion `int → long`. In `S::call` it is accessible, so that is well-formed; in `h` it is inaccessible, so that is ill-formed (¶3). If access took part in resolution, `h` would silently call `g(long)`.
</details>

!!! question "2. Why define usable candidate separately, instead of just saying overload resolution succeeds?"

<details markdown="1">
<summary>Answer</summary>

In an ordinary call, selecting a deleted or inaccessible function is simply an error, and no separate term is needed. But defaulted comparisons need a test that doesn't raise an error directly: when a member's comparison selects a deleted function, the outer `= default` should be defined as deleted instead of making the whole program ill-formed. A built-in operator candidate isn't a function, so deletion and access don't apply to it; that is why the definition lists it separately as usable.
</details>
