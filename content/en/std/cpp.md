---
title: Preprocessing directives
summary: "An overview of Chapter 15: preprocessing happens in translation phase 4 and deals only with preprocessing tokens; what each subclause covers and in what order to read them; features added in recent years (__VA_OPT__, module directives, feature detection, #elifdef, #warning, #embed); most of the old undefined behavior is now ill-formed."
updated: 2026-10-19
---

!!! tldr
    - Preprocessing is translation phase 4: executing directives, expanding macros, executing `_Pragma`. It operates on preprocessing tokens and can't see keywords, types or scopes.
    - Whether a line is a directive is decided lexically at the start of phase 4; macro expansion can neither create nor remove directives.
    - The subclauses of this chapter most worth reading closely are [[cpp.pre]] (what a directive is), [[cpp.replace]] and [[cpp.rescan]] (the macro replacement algorithm), and [[cpp.cond]] (how `#if` is evaluated).
    - Since C++20, some lines beginning with `import`, `module` or `export` are also preprocessing directives, so that build systems can scan module dependencies with preprocessing alone.
    - Most of this chapter's former undefined behavior has become ill-formed or IFNDR in the current draft.

Chapter 15, [cpp], specifies the preprocessor: conditional inclusion, source file inclusion, resource inclusion, macros, module directives, line control, pragmas and predefined macros. It corresponds almost sentence by sentence to the preprocessing section of the C standard (C23 6.10); C and C++ share the same preprocessor.

## Where preprocessing sits among the translation phases

Per [[lex.phases]], a source file goes through 8 translation phases in order; the first 7 are relevant to this chapter:

| Phase | Relation to this chapter |
|---|---|
| 1–2 | Decode the source file and splice lines ending in `\`. Directives work on the spliced logical lines. |
| 3 | Split into preprocessing tokens and whitespace; each comment becomes one space. A `<...>` immediately after `#include`, `#embed`, `import` and so on is recognized as a *header-name* ([[lex.pptoken]]). |
| 4 | Everything in this chapter: executing directives, expanding macros, executing `_Pragma`. Files brought in by `#include` go through phases 1–4 recursively. At the end of the phase, all directives have been deleted. |
| 5–6 | Concatenate adjacent string literals; convert preprocessing tokens to tokens; keywords exist only from here on. |
| 7 | Syntactic and semantic analysis. Module directives become declarations here. |

Several basic properties of the preprocessor follow from this table:

- The preprocessor can't see keywords or types. `#if sizeof(int) == 4` doesn't work; `#if new` is valid and evaluates to 0 ([[cpp.cond]]).
- The preprocessor can't see comments. By phase 3 a comment is already a space, and macros can't form comments either ([[cpp.concat]]).
- String concatenation comes after preprocessing. Neither `#include "a" "b"` nor `_Pragma("a" "b")` works ([[cpp.include]], [[cpp.pragma.op]]).
- Macro expansion can't create directives; whether a line is a directive is decided at the start of phase 4 ([[cpp.pre]]).

## Structure of the chapter and reading order

| Subclause | Contents | Page on this site |
|---|---|---|
| 15.1 | overall grammar; what a directive is; conditionally-supported directives; skipped groups | [[cpp.pre]] |
| 15.2 | the `#if` family; `defined`, `__has_include`, `__has_embed`, `__has_cpp_attribute` | [[cpp.cond]] |
| 15.3 | `#include` and header search | [[cpp.include]] |
| 15.4 | {{c++26}} `#embed` and its parameters | [[cpp.embed]] |
| 15.5–15.6 | module directives; macros when importing header units | [[cpp.module]] |
| 15.7 | macro definition, argument substitution, `__VA_ARGS__`, `__VA_OPT__`, `#`, `##` | [[cpp.replace]] |
| 15.7.5 | rescanning and recursion suppression | [[cpp.rescan]] |
| 15.8–15.11, 15.13 | `#line`, `#error`, `#warning`, `#pragma`, the null directive, `_Pragma` | [[cpp.line]] |
| 15.12 | predefined macros, `__cplusplus`, feature-test macros | [[cpp.predefined]] |

The suggested reading order:

1. [[cpp.pre]]: which lines are directives. Since C++20, it's no longer just lines beginning with `#`.
2. [[cpp.replace]] and [[cpp.rescan]]: the complete macro replacement algorithm. Why stringizing a macro's value takes two layers of macros, what problem `__VA_OPT__` solves, why macros can't recurse: the answers are all here.
3. [[cpp.cond]]: the evaluation rules of `#if`; undefined identifiers are treated as 0, and arithmetic is done in `intmax_t`.
4. [[cpp.include]] and [[cpp.embed]]: two mechanisms for bringing in external content, with nearly identical search rules.
5. [[cpp.module]]: why modules had to change the preprocessor.
6. [[cpp.line]], [[cpp.predefined]]: for reference.

## Recent changes

The C++98 preprocessor was almost exactly the C89 preprocessor. The changes since then go in three main directions.

Keeping in step with C. C++11 absorbed C99's preprocessor improvements ([[N1653]]): variadic macros, `_Pragma`, empty macro arguments. C++23 caught up with C23's `#elifdef`, `#elifndef` ([[P2334R1]]) and `#warning` ([[P2437R1]]), and C++26 with `#embed` ([[P1967R14]]).

Feature detection. C++17 added `__has_include` ([[P0061R1]]); C++20 put `__has_cpp_attribute` and the `__cpp_xxx` feature-test macros into the normative text ([[P0941R2]]); C++26 added `__has_embed`.

Modules. C++20 made some lines beginning with `import`, `module` or `export` preprocessing directives ([[P1703R1]], [[P1857R3]]), and specified how macros come in when a header unit is imported. C++26 forbade module names from coming from macro expansion ([[P3034R1]]). The goal of all these changes is to let build systems scan module dependencies with preprocessing alone.

In addition, C++20's `__VA_OPT__` ([[P0306R4]], [[P1042R1]]) solved the problem of an extra comma when the variadic arguments are empty.

| Version | Added |
|---|---|
| C++11 | variadic macros, `__VA_ARGS__`, `_Pragma`, empty arguments, `__STDC_HOSTED__`, `__STDCPP_THREADS__` |
| C++17 | `__has_include`, `__STDCPP_DEFAULT_NEW_ALIGNMENT__` |
| C++20 | `__VA_OPT__`, `__has_cpp_attribute`, feature-test macros, module directives, header units, `#include` translatable to `import` |
| C++23 | `#elifdef`, `#elifndef`, `#warning`, macros for extended floating-point types |
| C++26 | `#embed`, `__has_embed`, `__STDC_EMBED_*__`, module names must not come from macros |

## Undefined behavior turned ill-formed

The preprocessing chapter used to have a lot of undefined behavior: `##` forming an invalid token, directives in macro arguments, macro expansion producing `defined`, redefining predefined macros, a `#line` number out of range. These stemmed from early disagreements among preprocessor implementations, which standardization could only resolve by making them all UB.

Preprocessing happens entirely at compile time, so all these violations can be detected. Wording after C++23 has rewritten almost all of them:

| Case | C++23 and earlier | Current draft |
|---|---|---|
| The result of `##` isn't a valid preprocessing token | UB | ill-formed ([[cpp.concat#3]]) |
| The result of `#` isn't a valid string literal | UB | ill-formed ([[cpp.stringize#2]]) |
| A directive appears in a macro argument | UB | ill-formed ([[cpp.replace.general#14]]) |
| Macro expansion in `#if` produces `defined` | UB | {{ifndr}} ([[cpp.cond#9]]) |
| `defined` used in the wrong form | UB | {{ifndr}} ([[cpp.cond#9]]) |
| A macro-form `#include` doesn't form a *header-name* | UB | {{ifndr}} ([[cpp.include#7]]) |
| A `#line` number outside `[1, 2147483647]` | UB | conditionally-supported ([[cpp.line#3]]) |
| `#define` or `#undef` of a predefined macro | UB | ill-formed ([[cpp.predefined#4]]) |

The few that remain IFNDR are where major implementations still disagree.

Ill-formed only requires a diagnostic, and a warning counts. Clang and GCC give only warnings for most cases in the table (such as `-Wexpansion-to-defined`, `-Wembedded-directive`, `-Wbuiltin-macro-redefined`), whose wording still says undefined behavior, which is the old standard's phrasing.

## Implementations

!!! impl
    - GCC's preprocessor is `libcpp`, integrated into `cc1plus`; `gcc -E` runs only the preprocessor.
    - Clang interleaves preprocessing with lexing: the parser asks the preprocessor for the next token each time, and macros are expanded on demand. Each token records its expansion location and spelling location, which is how diagnostics can show the complete "expanded from macro" chain.
    - MSVC long used a traditional preprocessor that diverged from the standard in many ways; `/Zc:preprocessor` enables the new conforming preprocessor.
    - `clang-scan-deps` runs only preprocessing to scan module dependencies ([[cpp.module]]). `mcpp` and Boost.Wave are standalone preprocessor implementations, often used to check edge cases.
