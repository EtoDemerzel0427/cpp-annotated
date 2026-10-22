---
title: Fold expressions
summary: "Joining every element of a pack into one expression with the same binary operator: the four forms, associativity, the syntactic restrictions on operands, and the rules for empty packs."
updated: 2026-10-19
---

!!! tldr
    - The four forms `(... op e)`, `(e op ...)`, `(i op ... op e)`, `(e op ... op i)` are the unary left fold, unary right fold, binary left fold and binary right fold; the parentheses pile up on the side where the `...` is.
    - The outer parentheses are part of the syntax, and the operand can only be a *cast-expression*, so `(... + a * 2)` has to be written `(... + (a * 2))`.
    - For an empty pack, a binary fold yields the initial value; a unary fold is defined only for `&&` (`true`), `||` (`false`) and `,` (`void()`); other operators are ill-formed.
    - When the pack has exactly one element, a unary fold yields that element itself, so `(... && a)` is not necessarily a `bool`.
    - A fold expression is itself a pack expansion; what it expands to is specified in [[temp.variadic#15]].

## From recursive templates to folds

Summing a [[g:pack|pack]] (a template parameter pack or function parameter pack, [[temp.variadic]]) took a recursive template before C++17; since C++17 a single **fold expression** is enough:

<div class="compare" markdown="1">

```cpp ok
// C++11/14: recursion
int sum() { return 0; }
template<class T, class... R>
int sum(T t, R... r) {
  return t + sum(r...);
}
```

```cpp ok
// C++17: fold expression
template<class... A>
int sum(A... a) {
  return (0 + ... + a);
}
```

</div>

On instantiation, `(0 + ... + a)` expands directly into a nested expression like `((0 + a₁) + a₂) + a₃`, with no recursive function calls and no chain of intermediate instantiations.

## The four forms (¶2–¶3)

¶2 A fold with one operand is a **unary fold** ([[g:unary-fold|unary fold]]): `(... op e)` is a unary left fold, `(e op ...)` a unary right fold. The operand `e` must contain an unexpanded pack.

¶3 A fold of the form `(e1 op1 ... op2 e2)` is a **binary fold** ([[g:binary-fold|binary fold]]). The two operators must be the same, and exactly one of `e1` and `e2` contains an unexpanded pack; the other is the initial value. With the pack on the right (`e2`) it is a binary left fold; with the pack on the left (`e1`) it is a binary right fold.

[[temp.variadic#15]] specifies what they expand to. Let the elements of the pack be E₁ … Eₙ and the initial value be I:

| Form | Name | Expands to |
|---|---|---|
| `(... op E)` | Unary left fold | `((E₁ op E₂) op …) op Eₙ` |
| `(E op ...)` | Unary right fold | `E₁ op (… op (Eₙ₋₁ op Eₙ))` |
| `(I op ... op E)` | Binary left fold | `((I op E₁) op …) op Eₙ` |
| `(E op ... op I)` | Binary right fold | `E₁ op (… op (Eₙ op I))` |

A left fold associates from left to right, a right fold from right to left. The initial value is always innermost.

For associative operations such as `+`, `&&` and `||` on integers, the direction doesn't affect the result; for `-`, `/`, `<<` and `=`, the direction determines it:

```cpp run ok
#include <cstdio>

template<class... A> int lsub(A... a) { return (... - a); }
template<class... A> int rsub(A... a) { return (a - ...); }

int main() {
  std::printf("%d %d\n", lsub(10, 3, 2),   // (10 - 3) - 2 = 5
                         rsub(10, 3, 2));  // 10 - (3 - 2) = 9
}
```

The most common use of a binary left fold is stream output, with the stream object as the initial value:

```cpp run ok
#include <iostream>

template<class... Args> void print(Args&&... args) {
  (std::cout << ... << args) << '\n';   // ((cout << a1) << a2) << a3
}

int main() { print(1, "a", 2.5); }      // prints 1a2.5
```

Only a left fold works here. Written as the right fold `(args << ... << std::cout)`, the innermost part becomes `aₙ << std::cout`, which for an `int` means shifting by a stream, and doesn't compile.

Below are the two errors from Example 1 in the standard, plus the case of mismatched operators:

```cpp error
template<class... Args> bool f(Args... args) {
  return (true && ... && args);   // OK: binary left fold, initial value true
}
template<class... Args> auto g(Args... args) {
  return (args + ... + args);     // error: both sides contain unexpanded packs
}
template<class... Args> auto h(Args... args) {
  return (args + ... * 1);        // error: the two operators must be the same
}
```

## Syntactic restrictions (¶1)

¶1 gives the grammar of fold expressions. There are 32 allowed *fold-operator*s:

```text
+   -   *   /   %   ^   &   |   <<   >>
+=  -=  *=  /=  %=  ^=  &=  |=  <<=  >>=  =
==  !=  <   >   <=  >=  &&  ||  ,    .*   ->*
```

The three-way comparison `<=>` is not among them; `?:`, `[]`, `()`, `.` and `->` are not ordinary binary operators to begin with and aren't either.

Two more points about the grammar. First, the outer parentheses are part of the fold expression itself; `return ... + args;` is not a valid expression. Second, the operand is a *cast-expression*, i.e. an expression at the precedence of a cast or higher. Unary operations (`-a`, `!a`, `*a`), postfix operations (`a.size()`, `f(a)`) and casts (`(void)a`) can be written directly; lower-precedence expressions such as `a * 2` and `a ? 1 : 0` need parentheses.

```cpp error
template<class... A> auto k(A... a) { return (... + a * 2); }     // error: a * 2 is not a cast-expression
template<class... A> auto q(A... a) { return (... + (a * 2)); }   // OK: parenthesized
template<class... A> auto p(A... a) { return (... + -a); }        // OK: unary expression
```

This restriction removes an ambiguity: `(a * 2 + ...)` could be read as folding `a * 2` with `+`, or as folding with `*`, so the standard simply requires you to spell it out.

## Empty and single-element packs

When a binary fold meets an empty pack, the result is the initial value I.

When a unary fold meets an empty pack, there is no initial value to use. Table 20 in [[temp.variadic#15]] specifies values for empty packs for only three operators; all other operators are ill-formed:

| Operator | Value for an empty pack |
|---|---|
| `&&` | `true` |
| `\|\|` | `false` |
| `,` | `void()` |

These three values don't depend on the element type. `+` and `*` are different: the identity for `int` is `0`, for `std::string` it is `""`, for a matrix it is the zero matrix, and the standard has no way to choose. When empty packs need to be supported, use a binary fold with an initial value.

```cpp run ok
#include <cstdio>
#include <type_traits>

template<class... A> bool all(A... a)  { return (... && a); }    // empty pack: true
template<class... A> bool any(A... a)  { return (... || a); }    // empty pack: false
template<class... A> int  sum0(A... a) { return (0 + ... + a); } // empty pack: 0
template<class... A> auto comma(A... a) { return (a, ...); }     // empty pack: void()

int main() {
  std::printf("%d %d %d\n", all(), any(), sum0());   // 1 0 0
  static_assert(std::is_same_v<decltype(comma()), void>);
}
```

```cpp error
template<class... A> auto sum(A... a) { return (... + a); }
int x = sum();   // error: + has no value for an empty pack
```

This error only appears when the template is actually instantiated with an empty pack, so it often stays hidden until some caller passes zero arguments.

!!! history "Choosing the empty-pack values"
    The original proposal [[N4295]] also specified empty-pack values for `+`, `*`, `&` and `|` (`0`, `1`, `-1`, `0`). That meant summing an empty pack of `std::string` would quietly give an `int` `0`. Before C++17 shipped, [[P0036R0]] removed those four, keeping only `&&`, `||` and comma.

When the pack has one element, a unary fold expands to just that element, and the operator doesn't appear at all. So `(... && a)` is guaranteed to be a `bool` only when the number of elements is not 1:

```cpp run ok
#include <type_traits>

template<class... A> auto f(A... a) { return (... && a); }

static_assert(std::is_same_v<decltype(f()), bool>);         // empty pack: true
static_assert(std::is_same_v<decltype(f(5)), int>);         // single element: just 5
static_assert(std::is_same_v<decltype(f(5, 6)), bool>);     // 5 && 6

int main() {}
```

To make the result always `bool`, write the binary fold `(true && ... && a)`.

## Doing the same thing to every element: comma folds

`(f(args), ...)` calls `f` on each element in turn. The built-in comma operator guarantees left-to-right evaluation ([[expr.comma]]), so the order is determined.

```cpp run ok
#include <cstdio>
#include <vector>

template<class T, class... A> void push_all(std::vector<T>& v, A&&... a) {
  (v.push_back(a), ...);
}

int main() {
  std::vector<int> v;
  push_all(v, 1, 2, 3);
  std::printf("%zu\n", v.size());   // 3
}
```

If the type returned by `f(args)` overloads `operator,`, the fold calls that overload. The defensive form in generic code is `((void)f(args), ...)`: an operand of type `void` can only use the built-in comma.

`&&` and `||` folds keep short-circuit semantics: `(... && check(args))` stops evaluating further elements at the first `false`.

## A fold expression is a pack expansion (¶4)

¶4 A fold expression is a **pack expansion** ([[g:pack-expansion|pack expansion]]). So it can only appear where there are packs, i.e. in templates; the packs it contains are expanded by the fold itself, so no outer `...` can be applied to it; and its instantiation rules are specified together with other pack expansions in [[temp.variadic]].

In *requires-clause*s and concept definitions, fold expressions such as `(C<T> && ...)` can combine constraints. Since C++26, `&&` and `||` folds are normalized into **fold expanded constraints** ([[g:fold-expanded-constraint|fold expanded constraint]], [[temp.constr.fold]]), so they can take part in subsumption between constraints: `(D<T> && ...)` can be more constrained than `(C<T> && ...)` (when `D` subsumes `C`). Before C++26, the whole fold counted as one atomic constraint and couldn't be compared this way. {{c++26}}

## Common mistakes

!!! pitfall "Folding a non-associative operation in the wrong direction"
    `(args = ... = 0)` is a binary right fold expanding to `a1 = (a2 = (a3 = 0))`, which assigns 0 to every element. Written as the left fold `(0 = ... = args)`, it becomes `(0 = a1) = a2`, which is ill-formed.

!!! pitfall "Expecting an empty pack to give 0"
    `(... + args)` is ill-formed for an empty pack, not 0. When it must work with zero elements, write `(0 + ... + args)`.

## Questions

!!! question "Question"
    Is `(std::cout << ... << args)` a left fold or a right fold? What about `(args << ... << std::cout)`?

<details markdown="1">
<summary>Answer</summary>

The former has the pack on the right, so it is a binary left fold with the initial value `std::cout` innermost: `((cout << a1) << a2) << …`. The latter has the pack on the left, so it is a binary right fold: `a1 << (a2 << (… << (aₙ << cout)))`. From the innermost level it requires `aₙ << std::cout` to make sense, which for elements of arithmetic type is usually ill-formed, or calls an unexpected overload (¶3, [[temp.variadic#15]]).
</details>
