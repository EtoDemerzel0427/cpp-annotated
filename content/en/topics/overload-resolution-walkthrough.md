---
title: "Overload resolution walkthrough: eight classic puzzles"
summary: Working through eight common overload resolution problems one by one in four steps, candidate set, viable set, a table of implicit conversion sequences, and tie-breakers.
tags: overload resolution
updated: 2026-10-19
---

!!! tldr
    - Any overload resolution can be worked through in four steps: the candidate set, the viable set, comparing implicit conversion sequences argument by argument, and looking for a tie-breaker when they are tied.
    - Implicit conversion sequences are compared by form first: a standard conversion beats a user-defined conversion regardless of rank. That's why a string literal picks the `bool` overload rather than the `std::string` overload.
    - To win, a function must be no worse than its rival on every argument; if each side wins one argument, it's ambiguous, and no tie-breaker can save it.
    - Rules like non-template preferred, more constrained preferred and non-reversed preferred only apply when all arguments are tied. Specializations deduced from templates are almost always exact matches, so non-template functions often lose to templates.
    - An unconstrained forwarding constructor beats the copy constructor when copying a non-const lvalue; use a constraint to exclude the class itself.

## The four-step method

Each puzzle is analyzed in four steps following the structure of [[over.match]]:

1. **Candidate set** ([[over.match.funcs]]): which functions did name lookup (including ADL) find? Which specializations were deduced from templates? For operators, what member, non-member, built-in and rewritten candidates are there?
2. **Viable set** ([[over.match.viable]]): is the number of arguments right? Are constraints satisfied? Can an implicit conversion sequence be formed for each argument?
3. **Compare implicit conversion sequences** ([[over.best.ics]], [[over.ics.rank]]): an **implicit conversion sequence** (ICS below) is the sequence of steps converting an argument to the parameter type. Write down the form and rank of the ICS for each viable function and each argument, and compare column by column.
4. **Tie-breakers** ([[over.match.best#2]]): if the ICSs are tied, look for a tie-breaker in the order of items 2.2 to 2.13 of that paragraph.

ICSs come in three forms: **standard conversion sequences**, **user-defined conversion sequences** (going through a converting constructor or a conversion function), and **ellipsis conversion sequences** (the argument matches `...`). Standard conversion sequences are further ranked as exact match (identity, array- or function-to-pointer, qualification adjustment), promotion, and conversion. The tables below use these abbreviations:

| Abbreviation | Meaning |
|---|---|
| E | Standard conversion sequence, exact match rank |
| P | Standard conversion sequence, promotion rank |
| C | Standard conversion sequence, conversion rank |
| U | User-defined conversion sequence |
| ✗ | No ICS can be formed; the function is not viable |

## Puzzle 1: `f(0)`, `f(NULL)` and `f(nullptr)`

```cpp
void f(int*);
void f(long);
void use() {
  f(0);         // ?
  f(0L);        // ?
  f('\0');      // ?
  f(nullptr);   // ?
}
```

The candidates are `f(int*)` and `f(long)`; whether they are viable depends on the argument:

| Argument | `f(int*)` | `f(long)` | Result |
|---|---|---|---|
| `0` (`int`, null pointer constant) | C: null pointer conversion ([[conv.ptr]]) | C: integral conversion | Tied, no tie-breaker, ambiguous |
| `0L` (`long`) | C: null pointer conversion | E: identity | `f(long)` |
| `'\0'` (`char`) | ✗: not a null pointer constant | C: integral conversion | `f(long)` |
| `nullptr` | C: null pointer conversion | ✗ | `f(int*)` |

A null pointer conversion has conversion rank and is no better than `int` to `long`. This is the root of the `NULL` problem from the C++98 era: when `0` is used as a pointer, it ranks the same as any integer overload.

`'\0'` is not a null pointer constant. After a defect fix following C++11 ([[CWG903]]), a null pointer constant can only be an integer literal with value 0 or a prvalue of type `std::nullptr_t`; character literals don't count. `nullptr`'s type `std::nullptr_t` can only be converted to pointers, pointers to members, and `bool` (in direct-initialization only), not to `long`, so `f(long)` isn't viable for it.

The result of `f(NULL)` depends on the implementation: `NULL` may be defined as `0`, `0L`, or the compiler built-in `__null` ({{impl}}). Clang 23 + libc++ expands it to `__null`, which is treated as `long` on LP64 platforms, so `f(long)` is selected. On another platform, the same code may be ambiguous. So always write `nullptr` for a null pointer.

## Puzzle 2: `std::string` or `bool`

```cpp run ok
#include <cstdio>
#include <string>
void s(bool)               { std::puts("s(bool)"); }
void s(const std::string&) { std::puts("s(string)"); }
int main() {
  using namespace std::literals;
  s("abc");     // ?
  s("abc"s);    // ?
}
```

Both candidates are viable:

| Argument | `s(bool)` | `s(const std::string&)` |
|---|---|---|
| `"abc"` (`const char[4]` lvalue) | Array-to-pointer, then boolean conversion: C | Constructs a temporary via `std::string(const char*)`: U |
| `"abc"s` (`std::string` prvalue) | ✗ | Direct reference binding: E |

By [[over.ics.rank#2]], a standard conversion sequence is better than a user-defined conversion sequence, regardless of rank. So `s("abc")` picks `s(bool)`, and the literal is converted to `true`. The program prints `s(bool)` and then `s(string)`.

Overloads like this have caused many bugs in real code: an interface with both `setValue(bool)` and `setValue(const std::string&)` silently set `true` when passed a string literal. There are two fixes:

- Add an `s(const char*)` overload, which is an exact match and beats the conversion rank of `bool`.
- Make the `bool` overload a constrained template: `template<std::same_as<bool> B> void s(B);`. For `"abc"` it deduces `B = const char*`, the constraint isn't satisfied, and this overload isn't viable.

Replacing `const std::string&` with `std::string_view` doesn't solve it: constructing a `string_view` from a `const char*` is also a user-defined conversion.

## Puzzle 3: braced arguments

```cpp
#include <vector>
#include <utility>
#include <initializer_list>
void f(std::vector<int>);
void f(std::pair<int, int>);
void g(std::vector<int>);
void g(std::initializer_list<int>);
void use() {
  f({1, 2});   // ?
  g({1, 2});   // ?
}
```

The argument `{1, 2}` is a braced initializer list, not an expression, and its ICS is formed by the special rules of [[over.ics.list]].

`f({1, 2})`:

| Argument `{1, 2}` | `f(std::vector<int>)` | `f(std::pair<int, int>)` |
|---|---|---|
| ICS ([[over.ics.list#7]]) | Via the constructor `vector(initializer_list<int>)`: U | Via a constructor of `pair`: U |

Both are user-defined conversion sequences, but using different constructors, so by [[over.ics.rank#3.3]] they can't be compared. Item 3.1.1 of [[over.ics.rank#3]] prefers a sequence converting to `std::initializer_list`, but neither parameter type here is an `initializer_list`, so it doesn't apply. The result is ambiguous; Clang 23 reports `call to 'f' is ambiguous`.

`g({1, 2})`:

| Argument `{1, 2}` | `g(std::vector<int>)` | `g(std::initializer_list<int>)` |
|---|---|---|
| ICS | Via `vector(initializer_list<int>)`: U | [[over.ics.list#5]]: the worst of the element conversions, `int` to `int`: E |

A standard conversion sequence beats a user-defined one, so `g(std::initializer_list<int>)` is selected.

The corresponding problem at the constructor level, the difference between `std::vector<int>{3}` and `std::vector<int>(3)`, is covered in [[over.match.list]].

## Puzzle 4: C++20's reversed `operator==`

```cpp run ok
struct S {
  int v;
  S(int x) : v(x) {}
  bool operator==(const S& o) const { return v == o.v; }
};
int main() {
  bool a = S(1) == 1;    // ?
  bool b = 1 == S(1);    // ?  and in C++17?
  bool c = 1 != S(2);    // ?
  return a && b && c ? 0 : 1;
}
```

Candidates for `1 == S(1)` ([[over.match.oper]]):

| Candidate | Source | 1st argument | 2nd argument |
|---|---|---|---|
| Member candidates | Look up `operator==` in `int`; `int` isn't a class, none | | |
| Non-member candidates | None | | |
| Built-in `operator==(int, int)` etc. | [[over.built]] | `1`: E | `S(1)` to `int`: ✗, `S` has no conversion function |
| Reversed `S::operator==` | Synthesized for `S(1) == 1` | `1` to `const S&` (the original explicit parameter): U, via `S(int)` | `S(1)` to the object parameter: E |

Only the reversed candidate is viable, so in C++20 `1 == S(1)` is valid and is interpreted as `S(1) == 1`. C++17 has no reversed candidates, and this line is ill-formed. The rewritten candidates for `1 != S(2)` include `x == y` and its reversal; again only the reversed candidate is viable, and it is interpreted as `!(S(2) == 1)`.

Reversed candidates also bring new ambiguities. Write `operator==` as a non-const member:

```cpp error
struct T {
  bool operator==(const T&);     // const forgotten
};
bool d = T{} == T{};             // ambiguous per the standard
```

| Candidate | 1st argument `T{}` | 2nd argument `T{}` |
|---|---|---|
| Ordinary `T::operator==` | Object parameter `T&`: E | `const T&`: E |
| Reversed `T::operator==` | `const T&`: E | Object parameter `T&`: E |
| Comparison ([[over.ics.rank#3.2.6]]) | Ordinary is better: the bound reference is less cv-qualified | Reversed is better |

Each side wins one argument. The non-reversed preference in item 2.9 of [[over.match.best#2]] requires all arguments to be no worse, so it doesn't apply here, and per the standard it's ambiguous. Clang 23 accepts this code as an extension with a `-Wambiguous-reversed-operator` warning. The fix is to add `const`, or, per [[P2468R2]], declare a matching `operator!=`, so that `operator==` no longer generates reversed candidates.

## Puzzle 5: a forwarding constructor hijacks copying

```cpp run ok
#include <cstdio>
#include <utility>
struct P {
  template<class T> P(T&&) { std::puts("P(T&&)"); }
  P(const P&)              { std::puts("P(const P&)"); }
  P(P&&)                   { std::puts("P(P&&)"); }
  P() {}
};
int main() {
  P a;
  const P ca;
  P b(a);             // ?
  P c(ca);            // ?
  P d(std::move(a));  // ?
}
```

In `P b(a)`, `a` is a non-const lvalue of type `P`. Direct-initialization considers all constructors ([[over.match.ctor]]):

| Candidate | Parameter | ICS for argument `a` |
|---|---|---|
| Template, deducing `T = P&`, after reference collapsing | `P&` | Direct binding: E |
| `P(const P&)` | `const P&` | Direct binding: E, but the referenced type has an extra `const` |
| `P(P&&)` | `P&&` | ✗: an rvalue reference can't bind to an lvalue |

Between the two Es, by [[over.ics.rank#3.2.6]], binding to the less cv-qualified reference is better, so the template wins. The non-template preference in item 2.4 of [[over.match.best#2]] never gets a chance, because the ICSs have already decided. Copying a non-const `P` calls the forwarding constructor. If it uses the argument to initialize some member, such as `std::string name`, it usually fails to compile.

In `P c(ca)`, the template deduces `T = const P&`, and the parameter is `const P&`, identical to the copy constructor. The ICSs tie, and by item 2.4 the non-template copy constructor is chosen. `P d(std::move(a))` likewise: the template deduces `T = P`, the parameter `P&&` is the same as the move constructor's, and the move constructor is chosen. The program prints `P(T&&)`, `P(const P&)`, `P(P&&)` in that order.

The fix is to exclude `P` itself and classes derived from it from the template's candidates with a constraint:

```cpp run ok
#include <concepts>
#include <type_traits>
#include <cstdio>
struct P {
  template<class T>
    requires (!std::derived_from<std::remove_cvref_t<T>, P>)
  P(T&&) { std::puts("P(T&&)"); }
  P(const P&) { std::puts("P(const P&)"); }
  P() {}
};
int main() {
  P a;
  P b(a);      // P(const P&): constraint not satisfied for T = P&
  P c(42);     // P(T&&)
}
```

Constructors inherited from a base class have a dedicated rule ([[over.match.funcs.general#9]]): an inherited constructor shaped like a copy or move constructor isn't used to construct a derived class object from a single argument. A forwarding constructor in the same class can only rely on its own constraint.

## Puzzle 6: template versus non-template

```cpp run ok
#include <cstdio>
void f(int)                  { std::puts("f(int)"); }
template<class T> void f(T)  { std::puts("f<T>"); }
int main() {
  f(1);      // ?
  f('a');    // ?
  f(1L);     // ?
  f<>(1);    // ?
}
```

| Argument | `f(int)` | Template `f<T>(T)` | Result | Deciding rule |
|---|---|---|---|---|
| `1` | E | `T = int`: E | `f(int)` | Tied; item 2.4: non-template preferred |
| `'a'` | P, `char` promoted to `int` | `T = char`: E | Template | Item 2.1: E beats P |
| `1L` | C, `long` converted to `int` | `T = long`: E | Template | Item 2.1 |
| `f<>(1)` | Not a candidate; an explicit template argument list only matches templates | `T = int`: E | Template | Only candidate |

A specialization deduced from a template is almost always an exact match, so unless the non-template function is also an exact match, the template wins. Non-template preference is only a tie-breaker.

## Puzzle 7: constraints and subsumption

```cpp run ok
#include <concepts>
#include <cstdio>
template<class T>                void c(T) { std::puts("c(T)"); }               // #1
template<std::integral T>        void c(T) { std::puts("c(integral)"); }        // #2
template<std::signed_integral T> void c(T) { std::puts("c(signed_integral)"); } // #3
int main() {
  c(1);      // ?
  c(1u);     // ?
  c(1.0);    // ?
}
```

| Argument | #1 | #2 | #3 | Result |
|---|---|---|---|---|
| `1` (`int`) | E | E | E | #3 |
| `1u` | E | E | ✗, constraint not satisfied | #2 |
| `1.0` | E | ✗ | ✗ | #1 |

The ICSs all tie, so we go to item 2.5 of [[over.match.best#2]] and partially order the templates by [[temp.func.order]]. Apart from their constraints the three templates are identical, so partial ordering reduces to comparing constraints ([[temp.constr.order]]). `std::signed_integral<T>` is defined as `std::integral<T> && std::is_signed_v<T>`, and therefore **subsumes** `std::integral<T>`, which in turn subsumes no constraint. So #3 is better than #2, and #2 better than #1.

Subsumption is decided at the level of atomic constraints. By [[temp.constr.atomic]], two atomic constraints are identical only if their expressions are the same and come from the same place in the source. If instead of a named concept you write the literally identical `std::is_integral_v<T>` in two places, they are two different atomic constraints that don't subsume each other:

```cpp error
#include <type_traits>
template<class T> requires std::is_integral_v<T>
void d(T);                                                     // #1
template<class T> requires std::is_integral_v<T> && std::is_signed_v<T>
void d(T);                                                     // #2
void use() {
  d(1);   // error: ambiguous, #2 does not subsume #1
}
```

That is why the standard library wraps constraints in named concepts: the definition of `std::integral` appears only once, and everywhere it is used expands to the same atomic constraint.

## Puzzle 8: dispatching on value category

```cpp run ok
#include <cstdio>
void v(int&)        { std::puts("v(int&)"); }          // #1
void v(const int&)  { std::puts("v(const int&)"); }    // #2
void v(int&&)       { std::puts("v(int&&)"); }         // #3
void v(const int&&) { std::puts("v(const int&&)"); }   // #4
int main() {
  int i = 0;
  const int ci = 0;
  v(i);                               // ?
  v(ci);                              // ?
  v(1);                               // ?
  v(static_cast<const int&&>(ci));    // ?
}
```

| Argument | #1 `int&` | #2 `const int&` | #3 `int&&` | #4 `const int&&` | Result | Rule from [[over.ics.rank#3]] |
|---|---|---|---|---|---|---|
| `i`, `int` lvalue | E | E, extra const | ✗ | ✗ | #1 | 3.2.6: less cv-qualified |
| `ci`, `const int` lvalue | ✗ | E | ✗ | ✗ | #2 | Only viable one |
| `1`, `int` prvalue | ✗ | E | E | E, extra const | #3 | 3.2.3: rvalue binding to rvalue reference beats #2; 3.2.6: beats #4 |
| `const int` xvalue | ✗ | E | ✗ | E | #4 | 3.2.3 |

These four overloads show how the two kinds of rule divide the work: the lvalue/rvalue restrictions in [[over.ics.ref#3]] decide which functions are viable; items 3.2.3 and 3.2.6 of [[over.ics.rank#3]] decide which is better. In practice you usually need only two overloads, `const T&` and `T&&`: the former accepts everything, and the latter intercepts rvalues that can be moved from.

## Checklist

1. Lookup first, resolution second. Confirm which functions name lookup (including ADL, and hiding in member lookup) handed over. Many answers to "why wasn't it chosen" are that it wasn't in the candidate set at all.
2. Templates deduce first. A template whose deduction fails or whose constraints aren't satisfied isn't a candidate; deduced parameter types are usually exactly the argument types.
3. Compare ICSs argument by argument. Look at the form first (standard beats user-defined, user-defined beats ellipsis), then the rank, then the finer rules: proper subsequences, lvalue/rvalue and cv-qualification of reference binding, derivation distance, and so on.
4. Being no worse on every argument is a prerequisite. If each side wins one argument, it's ambiguous.
5. Tie-breakers only apply on a tie: non-template, more specialized template, more constrained, not rewritten, not reversed.
6. After selection there are still checks: access, whether it's deleted, narrowing, an explicit constructor selected in copy-list-initialization, and so on. If these checks fail, the program is ill-formed; another function is not chosen instead.
