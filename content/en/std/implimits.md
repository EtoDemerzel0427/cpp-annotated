---
title: Implementation quantities (Annex B)
summary: "Annex B lists 44 quantities that may be limited by an implementation, each with a suggested minimum; the numbers aren't requirements, but exceeding them in constant evaluation and template instantiation has well-defined consequences. This page includes the limits measured for Clang 23."
updated: 2026-10-19
---

!!! tldr
    - Annex B lists 44 quantities for which a compiler may have an upper limit (nesting levels, numbers of parameters, constexpr recursion depth, template instantiation depth and so on), each with a suggested minimum value. These numbers are only suggestions, not requirements.
    - An implementation may reject a program because it exceeds the implementation's limits; the standard doesn't say what the limits must be.
    - If a limit is exceeded during constant evaluation, the expression isn't a core constant expression; where a constant isn't required, the compiler quietly switches to run-time initialization.
    - Clang's constexpr depth (512), constexpr step count (about 1,048,576) and template instantiation depth (1024) are exactly the suggested values, and all can be adjusted with compiler options.
    - Clang's `#include` nesting limit is 200, below the suggested 256, which doesn't violate the standard.

## Can a compiler reject a valid program?

```cpp error
constexpr int f(int n) { return n == 0 ? 0 : 1 + f(n - 1); }
static_assert(f(511) == 511);   // OK: 512 calls in total
static_assert(f(512) == 512);   // error: not a constant expression (more than 512 levels)
```

`f(512)` breaks no language rule, but Clang 23 rejects the third line, with the note `constexpr evaluation exceeded maximum depth of 512 calls`. The abstract machine has unlimited resources; real compilers don't. This situation is handled jointly by Annex B (Implementation quantities) and a few places in the main text.

[[intro.compliance.general#2.1]] requires an implementation to accept and correctly execute a program that violates no rules, with one exception: unless the program exceeds the implementation's resource limits. The standard doesn't say what those limits must be. [[intro.compliance.general#9]] only recommends that implementations document their limits, and points to Annex B.

Annex B is marked informative. ¶1 says implementations may have limits on many quantities and lists some possible limits, each followed by a number in square brackets, a **potential minimum value**. That number isn't a guaranteed lower bound; implementations can go lower. The C standard requires an implementation to be able to translate at least one program that hits every translation limit at once; C++ doesn't even have that weak guarantee.

## Constant evaluation and template instantiation: two limits with defined consequences

Two places in the main text refer to Annex B directly, giving definite consequences to exceeding a limit.

[[expr.const.core#2.7]]: an expression that exceeds an implementation-defined limit isn't a core constant expression. So when constexpr recursion goes too deep or evaluation takes too many steps, the result is that the expression isn't a constant, rather than the compiler hanging. Where a constant is required (`static_assert`, a `constexpr` variable, an array bound) that's a compile error. Where constant evaluation is merely possible, the compiler falls back to run time:

```cpp run ok
#include <cstdio>
constexpr int f(int n) { return n == 0 ? 0 : 1 + f(n - 1); }
int g = f(600);   // more than 512 levels: no longer constant initialization, dynamic initialization instead
int main() { std::printf("%d\n", g); }
```

In our tests this compiles without any warning and prints `600` when run; `g` is just computed at program startup.

[[temp.inst#18]]: there is an implementation-defined limit on the total depth of recursive instantiations, and the result of infinite recursive instantiation is undefined (see [[ub.temp]]).

```cpp error
template <int N> struct R { static constexpr int v = R<N - 1>::v + 1; };
template <> struct R<0> { static constexpr int v = 0; };

static_assert(R<1025>::v == 1025);   // OK: exactly within the limit
static_assert(R<1026>::v == 1026);   // fatal error: more than 1024 levels
```

The outermost `R<1025>` itself doesn't count toward the recursion depth, so `R<1025>` works and `R<1026>` reports `recursive template instantiation exceeded maximum depth of 1024`. This is a fatal error: Clang stops the entire compilation immediately when it hits it.

Clang's three defaults are exactly the suggested values of Annex B 1.38, 1.39 and 1.41:

| Limit | Default | Option to adjust |
|---|---|---|
| constexpr function recursion depth | 512 | `-fconstexpr-depth=N` |
| Steps in one constant evaluation | About 1,048,576 | `-fconstexpr-steps=N` |
| Template instantiation depth | 1024 | `-ftemplate-depth=N` |

The step count was measured by running a simple accumulation loop in constant evaluation: 1,048,571 iterations pass and 1,048,572 fail, with the note `constexpr evaluation hit maximum step limit; possible infinite loop?`.

## The parser: the stack often runs out first

Clang has an explicit bracket nesting limit, `-fbracket-depth`, defaulting to 2048; nesting braces to level 2049 reports `bracket nesting level exceeded maximum of 2048`. But with nested parenthesized expressions, the front end crashes from stack overflow at 1,104 levels, with no diagnostic and exit code 139; nested class definitions crash the same way at 759 levels.

These depths are all far beyond the 256 Annex B suggests, and normal code won't hit them. But it shows that for a recursive descent parser, the real limit is often the machine stack rather than some number in the documentation. Machine-generated code is the most likely to run into it.

## Clang 23 measurements at a glance

The measured numbers in the table below come from our tests (Clang 23.1.3, arm64 macOS, 8 MB process stack), compiling generated test files with `-fsyntax-only`. "Limit N" is the number given by the diagnostic or the boundary found by bisection; "N passes" only says that N was tested and passed, without finding a limit; "stack overflow" means the front end crashed before reaching an explicit limit, which depends on the stack size; "—" means not tested.

| # | Quantity | Suggested minimum | Clang 23 measured |
|---|---|---|---|
| 1.1 | Nesting levels of compound statements, iteration statements and selection statements | 256 | Brace limit 2048 |
| 1.2 | Nesting levels of conditional inclusion (`#if`) | 256 | 5,000 passes |
| 1.3 | Pointer, pointer-to-member, array and function declarators modifying a type in a declaration | 256 | 5,000 `*` pass |
| 1.4 | Nesting levels of parenthesized expressions within a full-expression | 256 | 1,103 levels pass, 1,104 stack overflow |
| 1.5 | Characters in an internal identifier or macro name | 1,024 | 100,000 characters pass |
| 1.6 | Characters in an external identifier | 1,024 | 100,000 characters pass |
| 1.7 | External identifiers in one translation unit | 65,536 | 200,000 pass |
| 1.8 | Identifiers with block scope declared in one block | 1,024 | 20,000 pass |
| 1.9 | Structured bindings introduced in one declaration | 256 | 1,000 pass |
| 1.10 | Macro identifiers simultaneously defined in one translation unit | 65,536 | 200,000 pass |
| 1.11 | Parameters in one function definition | 256 | 20,000 pass |
| 1.12 | Arguments in one function call | 256 | — |
| 1.13 | Parameters in one macro definition | 256 | 5,000 pass |
| 1.14 | Arguments in one macro invocation | 256 | 5,000 pass |
| 1.15 | Characters in one logical source line | 65,536 | About 230,000 characters pass |
| 1.16 | Characters in a string literal (after concatenation) | 65,536 | 1,000,000 pass |
| 1.17 | Size of an object (bytes) | 262,144 | A static array of 2⁴⁰ bytes passes |
| 1.18 | Nesting levels for `#include` files | 256 | Limit 200 |
| 1.19 | `case` labels for a `switch` (excluding nested `switch`es) | 16,384 | 20,000 pass |
| 1.20 | Non-static data members (including inherited ones) in a class | 16,384 | — |
| 1.21 | Captures in one lambda expression | 256 | 2,000 pass |
| 1.22 | Enumeration constants in one enumeration | 4,096 | 100,000 pass |
| 1.23 | Levels of nested class definitions in one *member-specification* | 256 | 758 levels pass, 759 stack overflow |
| 1.24 | Functions registered by `atexit()` | 32 | — |
| 1.25 | Functions registered by `at_quick_exit()` | 32 | — |
| 1.26 | Direct and indirect base classes | 16,384 | — |
| 1.27 | Direct base classes of one class | 1,024 | 2,000 pass |
| 1.28 | Members declared in one *member-specification* (including member functions) | 4,096 | 7,000 pass |
| 1.29 | Final overriding virtual functions in a class, accessible or not | 16,384 | — |
| 1.30 | Direct and indirect virtual bases of a class | 1,024 | 2,000 pass |
| 1.31 | Static data members of a class | 1,024 | 5,000 pass |
| 1.32 | Friend declarations in a class | 4,096 | 5,000 pass |
| 1.33 | Access control declarations in a class | 4,096 | 5,000 pass |
| 1.34 | Member initializers in a constructor definition | 6,144 | 7,000 pass |
| 1.35 | *initializer-clause*s in one *braced-init-list* | 16,384 | 200,000 pass |
| 1.36 | Scope qualifications of one identifier | 256 | 1,000 levels pass |
| 1.37 | Nested *linkage-specification*s | 1,024 | 2,000 pass |
| 1.38 | Recursive constexpr function invocations | 512 | Limit 512 |
| 1.39 | Full-expressions evaluated within a core constant expression | 1,048,576 | Limit about 1,048,576 |
| 1.40 | Template parameters in a template declaration | 1,024 | 5,000 pass |
| 1.41 | Recursively nested template instantiations, including substitution during template argument deduction | 1,024 | Limit 1024 |
| 1.42 | Handlers per try block | 256 | 2,000 pass |
| 1.43 | Number of placeholders (`std::placeholders`) | 10 | libc++ provides `_1` to `_10` |
| 1.44 | Number of hazard-protectable possibly-reclaimable objects ([[saferecl.hp.general]]) | 256 | — |

A few items deserve a word more:

- The suggested value for 1.17 is only 256 KiB, dating from the era of embedded systems and segmented memory. On 64-bit platforms Clang accepts the declaration of a 1 TiB static array (whether it can be linked and run is another matter), while an array of 2⁶¹ `char`s reports `array is too large`: an object's size in bytes must be representable in `std::size_t`, and the implementation also has to leave room for pointer differences in `std::ptrdiff_t`.
- 1.18 is the only item in the table below its suggested value: header nesting passes at level 199 and fails at level 200 (counting the main file) with `#include nested too deeply`. Real code almost never hits this.

## Summary

| Question | Answer |
|---|---|
| Are the numbers in Annex B requirements? | No, they are only informative potential minimum values, and implementations can go lower |
| What happens when a program exceeds a limit? | The implementation may reject it ([[intro.compliance.general#2.1]]) |
| And when constant evaluation exceeds one? | The expression isn't a core constant expression ([[expr.const.core#2.7]]); where a constant isn't required, it falls back to run-time initialization |
| The limits you're most likely to hit | constexpr depth and steps, template instantiation depth; machine-generated code may also hit the parser's stack depth |
