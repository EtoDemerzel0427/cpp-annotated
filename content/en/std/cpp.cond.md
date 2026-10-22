---
title: Conditional inclusion
summary: "How the #if family decides which code goes into the translation unit: how conditions are evaluated at preprocessing time, the #ifdef family, feature-detection operators such as __has_include, and how skipped groups are handled."
updated: 2026-10-19
---

!!! tldr
    - `#ifdef X` only checks whether `X` is defined as a macro; `#if X` looks at its expanded value. With `#define X 0` the two give opposite results.
    - `#if` conditions are evaluated during preprocessing, when there are no keywords or types: identifiers remaining after macro expansion all become `0`, so a misspelled macro name isn't an error, and `sizeof` can't be used.
    - Integer arithmetic in conditions is always done in `intmax_t` / `uintmax_t`; `#if -1 > 0u` is true.
    - `__has_include`, `__has_cpp_attribute` and `__has_embed` detect whether headers, attributes and resources are available; detecting whether they themselves exist needs a separate layer of `#if defined(...)`.
    - Only the first group whose condition is true is processed; later `#elif` conditions aren't evaluated at all. In skipped groups only the nesting of directives is tracked.

Conditional inclusion is the `#if` family: deciding, from compile-time conditions, which source code goes into the translation unit. Portable code, platform adaptation and feature detection are all built on it.

These directives are executed in translation phase 4 ([[lex.phases]]). At that point the source is just a sequence of preprocessing tokens ([[g:preprocessing-token]], see [[lex.pptoken]]), with no keywords, types or declarations yet, only macro names and non-macro names. Most of the rules on this page stem from that.

## #ifdef vs #if (¶2, ¶12)

```cpp run title="defined.cpp" ok
#define A
#define B 0
#if defined A && defined(B) && !defined C
static_assert(true);   // included: B's value is 0, but it is defined
#endif
#ifdef B
static_assert(true);   // included
#endif
#if B
static_assert(false);  // not included: B expands to 0
#endif
int main() {}
```

¶2 `defined X` and `defined ( X )` evaluate to 1 if `X` is currently defined as a macro name, and 0 otherwise. Currently defined means it is a predefined macro or has an active macro definition ([[g:active-macro-definition]]): usually it was `#define`d and not `#undef`ed since; macros brought in by `import` of a header unit also count ([[cpp.import]]).

`defined` cares only whether the macro exists, not its value. That's the difference between `#ifdef FEATURE` and `#if FEATURE`: with `#define FEATURE 0`, the former is true and the latter false.

¶12 `#ifdef X`, `#ifndef X`, `#elifdef X` and `#elifndef X` are equivalent to `#if defined X`, `#if !defined X`, `#elif defined X` and `#elif !defined X` respectively.

`#elifdef` and `#elifndef` are new in C++23, in step with C23 ([[P2334R1]]). Before that, `#if` had a matching `#elif`, but `#ifdef` had no else-if form.

```cpp run title="elifdef.cpp" ok std=c++23 flags="-std=c++23"
#define USE_EPOLL
#ifdef USE_IO_URING
#  define BACKEND 1
#elifdef USE_EPOLL
#  define BACKEND 2
#elifndef NO_SELECT
#  define BACKEND 3
#else
#  define BACKEND 0
#endif
static_assert(BACKEND == 2);
int main() {}
```

!!! pitfall "Old compilers that don't know #elifdef"
    To an implementation that doesn't support `#elifdef`, it's just an unknown directive name. If the preceding `#ifdef` is true, the `#elifdef` is in the part being processed and the compiler reports an error, so the problem is easy to spot. If the preceding `#ifdef` is false, the `#elifdef` is in a skipped group and is silently ignored ([[cpp.pre#6]]), so the code after it is skipped as part of the previous group, and the program quietly picks the wrong branch. That's why Clang recognizes `#elifdef` in C++20 mode too, issuing only a `-Wc++23-extensions` warning.

## How #if conditions are evaluated (¶1, ¶8–¶11)

¶1 The expression controlling conditional inclusion must be an integral constant expression ([[expr.const]]), with two differences: identifiers in it are handled as described below, and `defined`, plus `__has_include`, `__has_embed` and `__has_cpp_attribute` introduced later, can be used as unary operators.

¶8 `#if` and `#elif` check whether this expression's value is nonzero. Evaluation has four steps:

1. Macro expansion, except for the operand of `defined` (¶9);
2. Evaluate `defined`, `__has_include`, `__has_embed` and `__has_cpp_attribute` (¶10);
3. Replace all remaining identifiers, except `true` and `false`, with `0` (¶10);
4. Convert the preprocessing tokens to tokens and evaluate as a constant expression, with all integer types treated as `intmax_t` or `uintmax_t` (¶11).

### Macro expansion first (¶9)

¶9 Before evaluation, macro invocations in the condition are replaced just as in ordinary text; only a macro name after `defined` isn't expanded.

If the token `defined` appears as a result of macro expansion, or if the use of `defined` before macro replacement isn't of one of the two forms `defined X` or `defined ( X )`, the program is ill-formed, no diagnostic required (IFNDR: the compiler may accept it, and the standard places no requirements on the whole program).

```cpp run title="defined-from-macro.cpp" ifndr
#define A
#define HAS_A defined(A)
#if HAS_A          // IFNDR: macro expansion produced defined
#endif
int main() {}
```

The standard doesn't specify the behavior of this form because historically implementations handled it differently, for example whether the operand of a `defined` produced mid-expansion should be expanded further. GCC and Clang evaluate it as usual, and Clang issues a `-Wexpansion-to-defined` warning (whose wording still says undefined behavior; in C++23 and earlier it really was UB). The portable way is to have the macro expand to 0 or 1:

```cpp run title="defined-portable.cpp" ok
#define A
#if defined(A)
#  define HAS_A 1
#else
#  define HAS_A 0
#endif
#if HAS_A
#endif
int main() {}
```

¶9 forbids one more situation: if, during macro replacement between `__has_embed(` and the matching `)`, a `limit`, `prefix`, `suffix` or `if_empty` defined as a macro is encountered, the program is ill-formed. This matches what [[cpp.pre#4]] requires of the `#embed` directive.

### Remaining identifiers become 0 (¶10)

```cpp run title="ident-zero.cpp" ok
#if new == 0 && undefined_thing == 0
// true: phase 4 has no keywords; new is just an identifier that isn't a macro
#endif
#if true && !false
// true and false are exceptions and keep their meaning as boolean literals
#endif
int main() {}
```

¶10 After macro replacement and evaluation of the four special operators, all remaining identifiers, including those spelled like keywords, except `true` and `false`, are replaced by the *pp-number* `0`, and then each preprocessing token is converted to a token. Footnote 115 explains why: in phase 4 an identifier is either a macro name or not; there's no distinction such as keywords or enumerators.

The most common problem this rule causes is that a misspelled macro name isn't an error; it just quietly yields 0:

```cpp
#if HAVE_THREDS     // misspelled: yields 0, picks the wrong branch
#endif
```

GCC's and Clang's `-Wundef` warns when an undefined identifier appears in `#if`.

Note 3 under ¶10 points out that alternative tokens ([[g:alternative-token]], see [[lex.digraph]]) such as `and`, `or`, `not` and `bitor`, though made entirely of letters, aren't identifiers, so they don't become 0 and work as operators as usual:

```cpp run title="alt-tokens-in-if.cpp" ok
#if not 0 and (1 bitor 0)
// true: not, and and bitor are operators
#endif
int main() {}
```

!!! lawyer "sizeof and casts in #if"
    In `#if sizeof(int) == 4`, both `sizeof` and `int` become 0, giving `0(0) == 4`, which isn't a valid expression, so it's ill-formed. `#if (long)1` becomes `(0)1`, likewise a syntax error. To know type sizes at preprocessing time, you can only rely on macros predefined by the implementation (such as GCC's and Clang's `__SIZEOF_INT__`) or the macros in `<climits>`.

### Computed in the widest integer types (¶11)

```cpp run title="if-arith.cpp"
#if -1 > 0u                         // -1 converts to uintmax_t, i.e. the maximum value
// true
#else
#  error "never gets here"
#endif
#if 0xFFFFFFFFFFFFFFFF == -1        // the literal doesn't fit in intmax_t, so it's uintmax_t
// true: -1 is also converted to uintmax_t
#endif
int main() {}
```

¶11 The tokens from step four are evaluated by the rules for constant expressions, with arithmetic range at least as required by [[support.limits]]. In this conversion and evaluation, all signed integer types act as `intmax_t` and all unsigned integer types as `uintmax_t`. This has three consequences:

1. The type of a literal may differ from ordinary code. Note 4 gives an example: on an implementation with 16-bit `int`, `0x8000` is a signed positive number in `#if`, but `unsigned int` in ordinary code in phase 7.
2. All arithmetic happens in the widest types; there's no `int` overflow, only `intmax_t` overflow.
3. The usual arithmetic conversions apply as usual; mixing signed and unsigned converts to `uintmax_t`, so `#if -1 > 0u` is true.

Clang gives a "converted from negative value to unsigned" warning for both `#if`s above. That warning has no corresponding `-W` switch and can't be turned off on its own, so this example has no verdict tag; the program is well-formed and the results conform to the standard.

!!! ub "Overflow and division by zero in #if"
    `#if 0x7FFFFFFFFFFFFFFF + 1 > 0` overflows signed arithmetic with a 64-bit `intmax_t`. The overflow means the expression is no longer a constant expression ([[expr.const]]), so this `#if` is ill-formed. Clang 23 gives only an "integer overflow in preprocessor expression" warning and carries on with some value. A warning counts as a diagnostic, so it formally conforms, but don't rely on the branch it picks.

    `#if 1/0` is likewise ill-formed, and Clang reports an error directly. But `#if 1 || 1/0` is valid: the right operand of `||` isn't evaluated, and the constant-expression restrictions apply only to the evaluated parts.

¶11 also specifies that character literals are interpreted by the rules of [[lex.ccon]], and note 5 adds that literals in `#if` use the same encoding as in ordinary expressions. So `#if 'A' == 65` always agrees with `'A' == 65` at run time: true with ASCII-compatible encodings, false with EBCDIC. The C standard is looser here, allowing character constants in `#if` to have values different from run time.

Finally, each subexpression of type `bool` undergoes integral promotion before further computation, so `#if true + true == 2` is true.

!!! note "Literals usable in #if"
    Any *pp-number* that can become an integer literal, a character literal or `true`/`false` after phase 6 can be used: binary literals `0b101`, digit separators `1'000`, the suffix `10z`, `u8'a'` all work. Floating-point literals and string literals don't, since they can't appear in integral constant expressions. C++ also allows the comma operator inside parentheses (`#if (1, 2)`), which C doesn't, so Clang notes it under `-pedantic`.

## Feature detection (¶3–¶7, ¶14–¶15)

### __has_include (¶3)

```cpp run title="has-optional.cpp" ok
#if __has_include(<optional>)
#  include <optional>
#  if __cpp_lib_optional >= 201603
#    define have_optional 1
#  endif
#elif __has_include(<experimental/optional>)
#  include <experimental/optional>
#  if __cpp_lib_experimental_optional >= 201411
#    define have_optional 1
#    define experimental_optional 1
#  endif
#endif
#ifndef have_optional
#  define have_optional 0
#endif
static_assert(have_optional == 1);
int main() {}
```

This is the standard's Example 1 in ¶14: use `<optional>` if available, otherwise fall back to `<experimental/optional>`, and finally define `have_optional` uniformly as 0 or 1.

¶3 `__has_include( ... )` searches for a file treating the tokens in the parentheses as the operand of an `#include` directive ([[cpp.include]]), evaluating to 1 if found and 0 if not. No further macro expansion happens here, since ¶9 already expanded once. The tokens in the parentheses must be a header name, or be combinable into one by the rules of `#include`; otherwise the program is ill-formed.

```cpp run title="has-include.cpp" ok
#define HDR "no_such_header.h"
#if __has_include(HDR)          // HDR was expanded to "no_such_header.h" in ¶9
#  error "should not be found"
#endif
int main() {}
```

`__has_include` answers whether the file can be found, not whether it can be used. Note 1 under [[cpp.include#6]] points out that if a file is found but the implementation can't process it (it's a directory, say), the program is ill-formed even if it was only probed with `__has_include`.

A header existing doesn't mean its functionality is available either. Older standard libraries might provide `<optional>` under `-std=c++14` too, with the contents removed by `#if`. That's why Example 1 also checks `__cpp_lib_optional` after finding the header. Since C++20, the more direct approach is to include `<version>` and check the library feature-test macros ([[cpp.predefined]]).

### __has_cpp_attribute (¶5–¶6)

```cpp run title="has-attr.cpp" ok
#if __has_cpp_attribute(nodiscard) >= 201907L
#  define NODISCARD(msg) [[nodiscard(msg)]]   // since C++20 nodiscard can take a reason
#elif __has_cpp_attribute(nodiscard)
#  define NODISCARD(msg) [[nodiscard]]
#else
#  define NODISCARD(msg)
#endif
NODISCARD("check the error") int f() { return 0; }
int main() { return f(); }
```

¶5 `__has_cpp_attribute( ... )` interprets the tokens in the parentheses, after macro expansion, as an attribute name (`name` or `ns::name`). If the implementation supports the attribute, the whole expression is replaced by a nonzero integer literal; otherwise by 0. If the contents of the parentheses don't have the form of an attribute name, the program is ill-formed.

¶6 For attributes specified by the standard, whether the result is 0 or the value in Table 21 is implementation-defined. For other attributes the implementation recognizes, the value is also implementation-defined. Note 2 says any nonzero value can be taken to mean the attribute is available.

| Attribute | Value | Attribute | Value |
|---|---|---|---|
| `assume` | `202207L` | `maybe_unused` | `201603L` |
| `deprecated` | `201309L` | `no_unique_address` | `201803L` |
| `fallthrough` | `201603L` | `nodiscard` | `201907L` |
| `indeterminate` | `202403L` | `noreturn` | `200809L` |
| `likely` | `201803L` | `unlikely` | `201803L` |

The table no longer has `carries_dependency`; that attribute has been removed from the current draft ([[dcl.attr]]).

Standard attributes may report 0 because recognizing an attribute isn't the same as making use of it. For example, MSVC recognizes `[[no_unique_address]]` but doesn't change layout for ABI reasons, so it reports 0 and provides `[[msvc::no_unique_address]]`. The recommended practice in the individual attribute subclauses follows the same idea: if an implementation can't issue deprecation diagnostics, the value for `deprecated` should be 0 ([[dcl.attr.deprecated#4]]); if it can't suppress fallthrough warnings, the value for `fallthrough` should be 0 ([[dcl.attr.fallthrough#2]]).

The standard's Example 2 in ¶15 demonstrates using a vendor attribute if available and falling back to the standard one otherwise:

```cpp run title="attr-fallback.cpp" ok
#if __has_cpp_attribute(acme::deprecated)
#  define ATTR_DEPRECATED(msg) [[acme::deprecated(msg)]]
#else
#  define ATTR_DEPRECATED(msg) [[deprecated(msg)]]
#endif
ATTR_DEPRECATED("This function is deprecated") void anvil();
int main() {}
```

!!! impl "Actual values in Clang 23"
    `__has_cpp_attribute(indeterminate)` is 0 (not yet implemented), `assume` is `202207L`, `nodiscard` is `201907L`, `no_unique_address` is `201803L`. `carries_dependency` still reports `200809L`, because Clang hasn't yet followed the draft in removing that attribute. Vendor attributes such as `gnu::always_inline` report 1.

### __has_embed (¶4) {{c++26}}

The `#embed` directive puts the bytes of a file into the source as a comma-separated list of integers ([[cpp.embed]]); `__has_embed` is its probing version.

```cpp run title="has-embed.cpp" ok
#if __has_embed(__FILE__) != __STDC_EMBED_FOUND__
#  error "the source file itself should be embeddable"
#endif
#if __has_embed(__FILE__ limit(0)) != __STDC_EMBED_EMPTY__
#  error "limit(0) makes the resource empty"
#endif
#if __has_embed(__FILE__ acme::frobnicate) != __STDC_EMBED_NOT_FOUND__
#  error "an unknown parameter counts as unsupported"
#endif
int main() {}
```

¶4 `__has_embed( ... )` processes the tokens in the parentheses as the operand of an `#embed` directive, likewise without further macro expansion. There are three possible results:

- ¶4.1 the resource is found, all parameters are supported and the resource isn't empty: `__STDC_EMBED_FOUND__` (1);
- ¶4.2 otherwise, if the resource is found, all parameters are supported and the resource is empty: `__STDC_EMBED_EMPTY__` (2);
- ¶4.3 otherwise: `__STDC_EMBED_NOT_FOUND__` (0).

Note 1 explains that an unknown parameter doesn't make the program ill-formed; it just counts as unsupported, giving 0. So `__has_embed` can also probe whether the implementation supports some vendor parameter. Whether the resource is empty is judged by the number of bytes after parameters such as `limit` take effect, so `limit(0)` makes any existing resource count as empty ([[cpp.embed.param.if.empty]] Example 2).

The `__FILE__` in the example is expanded in ¶9 to a string literal of the current file name, which is then used as the file name.

### They count as defined macros themselves (¶1, ¶7)

¶7 `#ifdef`, `#ifndef`, `#elifdef`, `#elifndef` and the `defined` operator treat `__has_include`, `__has_embed` and `__has_cpp_attribute` as defined macro names. So you can first check whether the compiler supports these operators:

```cpp run title="detect-has-include.cpp" ok
#if defined(__has_include)
#  if __has_include(<version>)
#    include <version>
#  endif
#endif
int main() {}
```

¶7 also specifies that these three identifiers shall not appear in any context not mentioned in this subclause. So `#define __has_include ...` or writing `__has_include(x)` in ordinary code is ill-formed. The last sentence of ¶1 adds another restriction: `defined` can't be written inside the parentheses of `__has_include` or `__has_embed`.

!!! pitfall "Detection and use can't go in the same #if"
    `#if defined(__has_include) && __has_include(<x>)` still errors on old compilers that don't support `__has_include`. The right side of `&&` is macro-replaced all the same; `__has_include` as an ordinary identifier becomes 0, leaving `0(<x>)`, which is a syntax error. Short-circuit evaluation doesn't help, because the syntax error happens before evaluation. So nest two layers of `#if` as in the example above.

## Select one group, skip the rest (¶13)

```cpp run title="elif-not-evaluated.cpp" ok
#if 1
int x;
#elif 1/0          // not evaluated: an earlier group was already selected
#elif (            // not even syntax-checked
#endif
int main() {}
```

¶13 The conditions of the directives in an `#if` construct are checked in order:

1. If a condition is false (zero), the group it controls is skipped.
2. Only the first group whose condition is true is processed. All later groups are skipped, and their controlling directives are processed as if in a skipped group, so later `#elif` conditions aren't evaluated.
3. If no condition is true, the `#else` group is processed if there is one; otherwise everything is skipped up to `#endif`.

When skipping a group, the preprocessor reads only the directive name of each directive, to track the nesting of `#if`; the rest of each directive and all other tokens in the group are ignored.

Footnote 116 notes that by the grammar, no preprocessing tokens may follow `#else` and `#endif` before the newline, but comments may. So `#endif // FOO_H` is valid and `#endif FOO_H` ill-formed (GCC and Clang give only a `-Wextra-tokens` warning, which counts as a diagnostic). But if that `#endif` line itself is in a skipped group, it's read only up to the directive name, and `FOO_H` causes no problem. Whether the same line of code is ill-formed depends on whether the group it's in is skipped.

!!! impl "How the preprocessor skips a group"
    When Clang skips a group, the lexer only looks for `#` at the start of a line and reads the directive name: `if`, `ifdef` and `ifndef` increase the nesting level, `endif` decreases it, and only at the outermost level does `elif`, `elifdef`, `elifndef`, `else` or `endif` decide whether to stop skipping. The other characters are not fully tokenized where possible, which is why a lone `'` in a skipped group isn't an error on Clang (see [[cpp.pre]]).

    Both GCC and Clang have the multiple-include optimization: if a header's entire contents are wrapped in `#ifndef X` / `#define X` / … / `#endif`, the preprocessor remembers `X`, and the next time the same file is `#include`d, it doesn't open it again as long as `X` is defined (see [[cpp.include]]).

## History

!!! history
    - C++98 already had `#if`, `#ifdef`, `#ifndef`, `#elif`, `#else`, `#endif` and `defined`. `true` and `false` not being replaced by 0 is one difference between C++ and C. Arithmetic was then done in `long` and `unsigned long`.
    - C++11 caught up with C99, moving arithmetic to `intmax_t` and `uintmax_t`.
    - C++17 added `__has_include` ([[P0061R1]]).
    - C++20 put `__has_cpp_attribute` and the feature-test macros into the normative text ([[P0941R2]]); before that they were only committee recommendations.
    - C++23 added `#elifdef` and `#elifndef` ([[P2334R1]]).
    - C++26 added `__has_embed` ([[P1967R14]]); macro expansion producing `defined` and `defined` in the wrong form changed from UB to IFNDR.

## Questions

!!! question "Question 1"
    On an implementation with 64-bit `intmax_t` and 32-bit `int`, is `#if -0x80000000 < 0` true? What about the same expression in ordinary code, `static_assert(-0x80000000 < 0);`?

<details markdown="1">
<summary>Answer</summary>

True in `#if`. By ¶11, `0x80000000` in `#if` is an `intmax_t`; negating it gives a negative number, and `< 0` is true.

Not true in ordinary code. `0x80000000` doesn't fit in a 32-bit `int`, and by the rules of [[lex.icon]] a hexadecimal literal tries `unsigned int` next, so it's an `unsigned int`. Negating it gives the still-unsigned `0x80000000u`, `< 0` is false, and the `static_assert` fails. This is the phenomenon note 4 under ¶11 describes: the same literal can have a different type in `#if`.
</details>

!!! question "Question 2"
    ¶5 says the argument of `__has_cpp_attribute` is macro-expanded, while ¶3 says the argument of `__has_include` isn't expanded further. Is that a contradiction?

<details markdown="1">
<summary>Answer</summary>

No. By ¶9, the whole `#if` line (except operands of `defined`) has already been expanded once before evaluation, so the `HDR` in `__has_include(HDR)` was replaced then. ¶3's "not expanded further" means the tokens aren't expanded again per [[cpp.include#7]] when treated as the operand of `#include`. The "after macro expansion" in ¶5 also refers to that one expansion in ¶9. Both arguments are expanded exactly once.

One detail is header names: the `<foo.h>` in `__has_include(<foo.h>)` is recognized as a single header-name token in phase 3, so the `foo` in it isn't expanded even if it's a macro.
</details>

!!! question "Question 3"
    ```cpp
    #define FOO 0
    #ifdef FOO
    #elifdef FOO
    #endif junk
    ```
    Is this code well-formed?

<details markdown="1">
<summary>Answer</summary>

Ill-formed; the problem is the last line. `#ifdef FOO` is true, so the first (empty) group is processed; `#elifdef FOO` and its group are skipped. But `#endif junk` ends this `#if` construct itself and isn't in any skipped group, so it must follow the strict grammar: no tokens after `#endif` before the newline. GCC and Clang give only a warning, and the warning is the diagnostic the standard requires.
</details>

## Summary

!!! summary
    - `#if` evaluates in four steps: macro expansion (except operands of `defined`), evaluating `defined` and the three `__has_*` operators, replacing remaining identifiers (except `true`/`false`) with 0, and evaluating as a constant expression in `intmax_t`/`uintmax_t`.
    - A misspelled macro name silently yields 0; `-Wundef` catches it.
    - Macro expansion producing `defined` is IFNDR (UB in C++23 and earlier); have the macro expand to 0 or 1 instead.
    - `__has_embed` has three results: 0 not found or parameter unsupported, 1 found and nonempty, 2 found but empty.
    - `__has_cpp_attribute` may report 0 even for standard attributes, meaning recognized but not made use of.
    - Only the first group whose condition is true is processed; later `#elif`s aren't evaluated.
