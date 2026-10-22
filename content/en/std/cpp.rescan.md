---
title: Rescanning and further replacement
summary: "The last step of macro replacement: the result is scanned again together with the following tokens of the source file; a macro name currently being replaced that is found during this scan isn't expanded, and never will be, which is why macros can't recurse."
updated: 2026-10-19
---

!!! tldr
    - After a macro is replaced, the result is scanned again together with the following tokens of the source file, so the end of a replacement result can combine with a following `(...)` into a new macro invocation.
    - When rescanning finds the name of a macro currently being replaced, that name isn't expanded, and never will be, even if it's passed as an argument to another macro. That's why macros can't recurse.
    - When the token after a function-like macro name isn't `(`, the macro has merely missed this invocation; it isn't permanently disabled. Deferred-expansion tricks rely on this.
    - Even if the result of macro expansion looks like `#define`, it isn't treated as a preprocessing directive; but any `_Pragma` in it is executed.

## The expansion result is scanned again (¶1)

```cpp
#define LP (
#define F1(x) [x]
#define CALL(m) m(5)
F1 LP 1)        // result: F1 ( 1); F1 isn't expanded
CALL(F1)        // result: [5]
```

In the first line, when the preprocessor scans `F1`, the next token is `LP`, not `(`, so this isn't an invocation and `F1` is left as is. `LP` then expands to `(`, but the scan has already passed `F1` and doesn't go back.

In the second line, `CALL(F1)` is first replaced by `F1(5)`. This result is scanned again, and now `F1` is immediately followed by `(`, so it expands as an invocation to `[5]`.

¶1 specifies this step. After all parameters in the replacement list have been substituted and `#` and `##` processed, all [[g:placemarker|placemarkers]] (temporary tokens inserted when `##` meets an empty argument; see [[cpp.concat]]) are first removed. Then the resulting token sequence is scanned again, **together with all subsequent tokens of the source file**, for more macro names to replace. This step is called **rescanning**.

"Together with subsequent tokens" means a replacement result can borrow tokens from the source file:

```cpp
#define h g(~
#define g f
#define f(a) [a]
h 5)            // h → g(~ → f(~, then borrows the 5) from the source → f(~ 5) → [~ 5]
```

The parenthesis in `h`'s replacement result `g(~` isn't closed; the closing `)` is later in the source file. Rescanning joins the two into a complete invocation of `f`.

## Macros don't expand themselves (¶3)

If rescanning found the same macro again and kept expanding it, it would loop forever. ¶3 prevents this with three sentences.

The first sentence of ¶3: if, while scanning the replacement list of macro M, M's own name is found, it isn't replaced. The parenthetical qualification is important: this is limited to the replacement list itself; M appearing later in the source file is expanded as usual.

```cpp
#define foo foo bar
foo         // → foo bar          the foo in the replacement list isn't expanded
foo foo     // → foo bar foo bar  the second foo comes from the source and is expanded as usual
```

The second sentence: M's name found in nested replacements isn't replaced either. Nested replacements are other macros expanded within M's replacement result.

```cpp
#define AA BB
#define BB AA
AA          // AA → BB → AA: AA is still being replaced while BB expands, so it isn't expanded again. Result: AA
BB          // likewise, result: BB
```

The third sentence: these nonreplaced macro name tokens are no longer available for further replacement, even if they later appear in contexts where they would otherwise be replaced.

```cpp
#define id(x) x
#define ff(x) x
#define gg ff(gg)
gg          // gg → ff(gg); the gg in the argument is found while replacing gg, so it isn't expanded. Result: gg
id(gg)      // id's argument is first fully expanded, giving a gg that won't be expanded;
            // after substitution into id and rescanning, gg is no longer being replaced, but it still isn't expanded. Result: gg
```

Without the third sentence, after substitution into `id`, the `gg` in `id(gg)` would no longer be within its own replacement and would expand again to `ff(gg)`. Wrapping a few more layers of `id(...)` would get around the protection of the first two sentences.

So not being expandable is a property of the token itself; it travels with the token and survives being passed through arguments. The community calls such tokens **painted blue**; the standard's text doesn't use the phrase, saying only "nonreplaced macro name preprocessing tokens".

## The standard's big example (¶2)

¶2 is the longest macro example in the standard, and every rule above has a counterpart in it. The definitions:

```cpp
#define x       3
#define f(a)    f(x * (a))
#undef  x
#define x       2
#define g       f
#define z       z[0]
#define h       g(~
#define m(a)    a(w)
#define w       0,1
#define t(a)    a
#define p()     int
#define q(x)    x
#define r(x,y)  x ## y
#define str(x)  # x
```

First the first four lines. When `f` is defined, `x` is 3; afterwards `x` is redefined as 2. A replacement list stores tokens and isn't expanded at definition time; `x` is replaced only when used, so every `x` below is 2.

### The first line

```cpp
f(y+1) + f(f(z)) % t(t(g)(0) + t)(1);
// → f(2 * (y+1)) + f(2 * (f(2 * (z[0])))) % f(2 * (0)) + t(1);
```

`f(y+1)` after substitution gives `f(x * (y+1))`. On rescanning, `f` is the macro being replaced and isn't expanded even though it's followed by `(`; `x` expands to `2`. The result is `f(2 * (y+1))`.

The argument `f(z)` of `f(f(z))` must be fully expanded first ([[cpp.subst#1]]). `z` expands to `z[0]`, in which `z` is painted blue; the inner `f` gives `f(2 * (z[0]))`, in which `f` is also painted blue. The outer substitution is rescanned, the outer `f` is painted blue, the inner `f` was blue already, and the result is `f(2 * (f(2 * (z[0]))))`.

For `t(t(g)(0) + t)(1)`, the outer `t`'s argument `t(g)(0) + t` is expanded first:

1. The argument `g` of `t(g)` expands to `f`. Here `f` isn't followed by `(`; it just isn't invoked and isn't painted blue. Substitution gives `f`.
2. Rescanning `f` together with the following `(0) + t` within the argument: `f(0)` forms an invocation, giving `f(2 * (0))`.
3. The `t` in the argument isn't followed by `(` and is left as is. The argument expands to `f(2 * (0)) + t`.

The outer `t`'s replacement list is just `a`, so substitution gives `f(2 * (0)) + t`. Rescanning continues with the `(1);` later in the source file, but the `t` in it was found in the replacement list of `t` and is painted blue, so `(1)` doesn't form an invocation. The result is `f(2 * (0)) + t(1)`.

### The second line

```cpp
g(x+(3,4)-w) | h 5) & m
    (f)^m(m);
// → f(2 * (2+(3,4)-0,1)) | f(2 * (~ 5)) & f(2 * (0,1))^m(0,1);
```

`g` is an object-like macro that expands to `f`, which on rescanning combines with the following `(x+(3,4)-w)` in the source file into an invocation of `f`. There's only one argument: the comma in `(3,4)` is inside parentheses, and the comma that `w` expands to appears only after arguments have been delimited, so it doesn't split the argument in two.

`h 5)` is the token-borrowing example from the previous section, giving `f(2 * (~ 5))`.

Between `m` and `(f)` there's a newline. In a macro invocation a newline is just ordinary whitespace ([[cpp.replace.general#13]]), so this is the invocation `m(f)`. Substituting into `a(w)` gives `f(w)`; what's being replaced now is `m`, not `f`, so `f(w)` expands normally, giving `f(2 * (0,1))`.

`m(m)` after substitution gives `m(w)`. This `m` is found while replacing `m` and is painted blue; `w` expands to `0,1`, giving `m(0,1)`. The same replacement list `a(w)` with a different argument gives a completely different result.

### The third and fourth lines

```cpp
p() i[q()] = { q(1), r(2,3), r(4,), r(,5), r(,) };
char c[2][6] = { str(hello), str() };
// → int i[] = { 1, 23, 4, 5, };
//   char c[2][6] = { "hello", "" };
```

`p()` is a macro with zero parameters that expands to `int`. `q()` has one empty argument and expands to nothing, so `i[q()]` becomes `i[]`. In `r(4,)`, `4` concatenated with a placemarker gives `4`; `r(,)` leaves only a placemarker after concatenation, which is removed, leaving nothing. `str()` stringizes the empty argument into `""`.

In our tests Clang 23's `-E` output for the whole example matches the standard token for token, differing only in whitespace.

## The result doesn't become a directive (¶4)

```cpp
#define DEFINE_X # define X 1
DEFINE_X        // → # define X 1, which goes on to phase 7 as ordinary tokens, causing a syntax error

#define WARN_OFF _Pragma("GCC diagnostic ignored \"-Wunused\"")
WARN_OFF        // OK: _Pragma in the result of macro expansion is executed
```

¶4 The token sequence resulting from complete replacement isn't processed as a preprocessing directive even if it resembles one. But all `_Pragma` unary operator expressions in it are processed as specified in [[cpp.pragma.op]].

That's why `_Pragma` exists: a macro can produce `_Pragma(...)` but not `#pragma`. [[cpp.pre]] has a complementary rule: a line that isn't a directive before macro expansion doesn't become one after expansion either.

## Missing an invocation isn't being painted blue: deferred expansion

In the opening example, `F1` was followed by `LP`; `F1` merely missed the invocation and wasn't painted blue. If there's another round of scanning later, it can still expand. Macro metaprogramming libraries use exactly this to simulate recursion:

```cpp run title="defer.cpp" ok
#define EMPTY()
#define DEFER(m) m EMPTY()
#define EXPAND(...) __VA_ARGS__
#define A() 123

// DEFER(A)()         → A ()   in this round of scanning, A is followed by EMPTY, not (
// EXPAND(DEFER(A)()) → 123    one more round of scanning, and A meets (
static_assert(EXPAND(DEFER(A)()) == 123);
int main() {}
```

`DEFER(A)` after substitution gives `A EMPTY()`. On rescanning, the token after `A` is `EMPTY`, so `A` is skipped; then `EMPTY()` expands to nothing, leaving `A ()`. The scan doesn't go back, so in this round `A` stays where it is.

`EXPAND`'s job is to give one more round of scanning: its argument is first fully expanded to `A ()`, and after substitution it's rescanned, `A` meets `(`, and the invocation succeeds. Nesting `EXPAND` a few levels, for example `#define EVAL(...) EVAL1(EVAL1(EVAL1(__VA_ARGS__)))`, gives hundreds or thousands of rounds of scanning. A macro defers a reference to itself in one round; by the next round it's no longer being replaced, and the deferred name was never painted blue, so it can keep expanding. The loops and recursion of libraries such as Boost.Preprocessor are all built on this trick.

These tricks fully conform to the standard, but are hard to read and debug. In most situations, use templates, `constexpr` functions, fold expressions or reflection instead. Where macros still fit is mainly generating declarations (X-macros), turning identifiers into strings, and conditional compilation.

## Implementation view: hide sets

!!! impl "Prosser's hide-set algorithm"
    The standard describes the rules in terms of "being replaced" and "nested replacements", which aren't convenient to implement directly. During C89 standardization, Dave Prosser gave a reference algorithm: each token carries a **hide set**, the set of macro names that can't be expanded for that token.

    - When an object-like macro `T` expands, the hide set of each token in the result is: the hide set of the macro name token `T` ∪ {T}.
    - When a function-like macro `T(...)` expands, the hide set of each token in the result is: (the hide set of the macro name token `T` ∩ the hide set of the closing `)`) ∪ {T}.
    - When a macro name is scanned, it's expanded as long as it isn't in that token's own hide set.

    A macro name being in a token's hide set is equivalent to that token being painted blue. GCC and Clang implement the same semantics with a no-expand flag on tokens plus a record of the macros currently being expanded.

The intersection in the function-like macro rule handles the case where an invocation comes half from a replacement result and half from the source file. The hiding relationship continues only if the closing parenthesis is also part of the same expansion. The following example comes from the C standard:

```cpp
#define f(a) a*g
#define g(a) f(a)
f(2)(9)
```

1. `f(2)` expands to `2*g`, where the hide set of `g` is {f}.
2. `g` and the `(9)` in the source file form the invocation `g(9)`. `g`'s hide set is {f}, and the closing `)` comes from the source file with an empty hide set; the intersection is empty, unioned with {g}, giving `f(9)` whose tokens have hide set {g}.
3. `f` isn't in {g}, so it expands further to `9*g`. The final result is `2*9*g`.

But by the standard's text, does the expansion of `g(9)` count as a nested replacement of `f`? If it does, the `f` in `f(9)` should be painted blue, and the result would be `2*f(9)`. The C standard says explicitly for this example that either result is possible, which is unspecified behavior. The C++ standard has no similar statement. In our tests Clang 23 gives `2*9*g`, matching Prosser's algorithm, and so does GCC.

## Common misconceptions

!!! pitfall "Macros can recurse"
    ```cpp
    #define LIST(x, ...) x __VA_OPT__(, LIST(__VA_ARGS__))
    LIST(1, 2, 3)   // → 1 , LIST(2, 3): the inner LIST is painted blue and not expanded
    ```
    To handle a variable number of elements, pass `__VA_ARGS__` directly to a function template or fold expression; use the deferred-expansion trick above only when you really need loops at preprocessing time.

!!! pitfall "The parenthesis after a macro name can come from another macro"
    After `#define LP (`, `F LP x)` doesn't invoke the function-like macro `F`, because when `F` is scanned the next token is `LP`. It needs one more round of scanning: `EXPAND(F LP x))`.

## Questions

!!! question "Question 1"
    ```cpp
    #define a a b
    #define b a
    a
    ```
    What's the result of expansion? Explain why each `a` and `b` is or isn't expanded.

<details markdown="1">
<summary>Answer</summary>

The result is `a a`, which can be verified with Clang 23's `-E` in our tests.

1. `a` expands to `a b`. The `a` in the replacement list is found while replacing `a`, so by the first sentence of ¶3 it isn't expanded and is painted blue.
2. Scanning continues and finds `b`, which isn't being replaced, so it expands to `a`. This is a replacement nested within the replacement of `a`, so by the second sentence of ¶3, the `a` found in it isn't expanded and is painted blue.
3. The result is two blue `a`s.
</details>

!!! question "Question 2"
    Why does `m(f)` expand to `f(2 * (0,1))` while `m(m)` expands to `m(0,1)`? Explain again using the hide-set algorithm.

<details markdown="1">
<summary>Answer</summary>

`m(a)`'s replacement list is `a(w)`; the `m` and `)` in the source file both have empty hide sets, so every token in the replacement result has hide set {m}.

- `m(f)`: the result is `f ( w )`. `f`'s hide set {m} doesn't contain `f`, and it's followed by `(`, so `f(w)` expands.
- `m(m)`: when the argument `m` is expanded on its own, it isn't followed by `(` and is left as is. In the substituted `m ( w )`, `m`'s hide set {m} contains itself, so it isn't expanded; `w` isn't in {m} and expands to `0,1`.

Note that in the second case, `m` wasn't painted blue during argument expansion; it just wasn't followed by `(`. It was painted blue only after substitution, when the replacement list of `m` was rescanned.
</details>
