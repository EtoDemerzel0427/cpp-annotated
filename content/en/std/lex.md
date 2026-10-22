---
title: Lexical conventions
summary: "A guide to Chapter 5: how a source file passes through the translation phases, is split into preprocessing tokens and then into tokens, and which page covers the character sets, identifiers, keywords and literals."
updated: 2026-10-19
---

!!! tldr
    - Chapter 5 explains how a sequence of characters becomes the sequence of tokens the compiler parses, and what each token is.
    - Translation is divided into 8 conceptual phases, with a place for preprocessing, string concatenation, template instantiation and linking; many lexical oddities follow from the order of the phases.
    - The preprocessor works on preprocessing tokens; the parser works on tokens. Keywords, and the types and values of literals, appear only in phase 6.
    - Lexical splitting is greedy (maximal munch), so `x+++++y` and `0xe+foo` do not compile.
    - C++26 turned the remaining cases of undefined behavior in this chapter into ill-formed or valid code.

A whole class of C++ questions is answered at the lexical level: why `x+++++y` does not compile, why `-2147483648` is not an `int`, why `u8"..."` cannot be passed to `const char*`, why `"\xA" "B"` is not `"\xAB"`.

Chapter 5 [lex] answers two things. First, which translation phases a source file goes through ([[lex.phases]]), and in which phase preprocessing (Chapter 15, [[cpp]]), template instantiation ([[temp.inst]]) and linking ([[basic.link]]) take place. Second, what each token that comes out is: an identifier, a keyword, an operator, or some kind of literal; and what the type and value of a literal are ([[lex.literal]]). The expressions chapter only says that the type of a literal is determined by Chapter 5 ([[expr.prim.literal]]).

## Structure of the chapter

| Subclause | Content | Page on this site |
|---|---|---|
| 5.1 | Source files, preprocessing translation units, separate translation | [[lex.separate]] |
| 5.2 | The 8 phases of translation | [[lex.phases]] |
| 5.3 | Translation character set, basic character set, literal encodings, universal-character-names | [[lex.char]] |
| 5.4–5.8, 5.10 | Comments, preprocessing tokens and maximal munch, header names, preprocessing numbers, operators and punctuators, tokens | [[lex.pptoken]] |
| 5.9 | Alternative tokens (`<%`, `and`, etc.) | [[lex.digraph]] |
| 5.11 | Identifiers, identifiers with special meaning, reserved identifiers | [[lex.name]] |
| 5.12 | Keywords | [[lex.key]] |
| 5.13 | Overview of literals, Boolean and pointer literals | [[lex.literal]] |
| 5.13.2 | Integer literals | [[lex.icon]] |
| 5.13.3 | Character literals, escape sequences | [[lex.ccon]] |
| 5.13.4 | Floating-point literals | [[lex.fcon]] |
| 5.13.5–6 | String literals, raw strings, concatenation, unevaluated strings | [[lex.string]] |
| 5.13.9 | User-defined literals | [[lex.ext]] |

Start with [[lex.phases]], then read [[lex.char]] and [[lex.pptoken]]. [[lex.char]] separates two things that are often confused: what the characters in the source are (the translation character set), and what bytes a literal is at run time (the literal encoding). The literal pages can be consulted as needed; the type table in [[lex.icon]] and the concatenation rules in [[lex.string]] are used most often.

## Two kinds of tokens

This chapter has two kinds of tokens, used in different phases.

A **preprocessing token** is the unit split out of the character stream in phase 3; the preprocessor works only on these. In phase 6 each preprocessing token is converted into a **token**, and the parser works only on tokens.

| | Preprocessing token | Token |
|---|---|---|
| Exists in | Phases 3–5, converted in phase 6 | After phase 6 |
| Kinds | header names, placeholder tokens produced by module directives, identifiers, pp-numbers, character and string literals, preprocessing operators and punctuators, other single non-whitespace characters | identifiers, keywords, literals, header names, operators and punctuators |
| Keywords | None; `int` and `new` are identifiers | Yes |
| Numbers | pp-number, with no type and no value | Integer or floating-point literal, with a type and a value |
| Defined in | [[lex.pptoken]] | [[lex.token]] (see the [[lex.pptoken]] page) |

So `new` written in `#if` is just an identifier, replaced by 0 under the usual rule. The text of [[lex.token]] says there are six kinds of tokens: identifiers, keywords, literals, header names, operators, and other separators; in the grammar, operators and other separators (punctuators) are merged into one alternative, *operator-or-punctuator*, so there are only five alternatives.

## Consequences of breaking the rules of this chapter

Most rules in this chapter are ordinary diagnosable rules: violating one makes the program ill-formed, and the compiler must report it. The exceptions fall into these groups:

- Using a reserved identifier (`__x`, `_Upper`, a global `_lower`): {{ifndr}} ([[lex.name#4]]).
- Declaring a literal operator named by a literal suffix without a leading `_`; those suffixes are reserved for future standardization: {{ifndr}} ([[over.literal#1]]).
- A multicharacter literal `'ab'`, a conditional escape sequence `'\q'`, and `'`, `\`, `//`, `/*` in a header name: conditionally-supported, meaning an implementation may not support them, and when it does the semantics are implementation-defined.
- Modifying a string literal object: {{ub}}. Note 5 in [[lex.string#9]] mentions this; the normative basis is that modifying a const object is UB ([[dcl.type.cv]]).
- Whether evaluating the same string literal several times yields the same object: {{unspec}} (Note 4 in [[lex.string#9]]; the normative basis is in [[intro.object]]).

In C++23 and earlier this chapter had several more cases of UB, such as an unterminated `'` or `"`. [[P2621R2]] in C++26 made them ill-formed or valid.

## Main changes by version

| Version | Changes |
|---|---|
| C++11 | Raw strings; `u8`/`u`/`U` prefixes and `char16_t`/`char32_t`; user-defined literals; `nullptr`; `long long`; `>>` in a template argument list can close two levels ([[temp.names]]) |
| C++14 | Binary literals `0b`, digit separator `'` |
| C++17 | Trigraphs removed; hexadecimal floating-point literals; `u8` character literals |
| C++20 | `char8_t` (the type of `u8` literals changes with it); `<=>`; lexical handling of `import`/`module`; keywords such as `concept`, `requires`, `co_await` |
| C++23 | Character set and encoding model rewritten; UTF-8 source files must be supported; delimited escapes such as `\N{...}` and `\x{...}`; `z`/`uz` suffixes; suffixes for extended floating-point types; identifiers use the Unicode XID properties |
| C++26 | `$` `@` `` ` `` added to the basic character set; unevaluated strings; `^^`, `[:`, `:]` for reflection; `contract_assert`, `pre`, `post`; `#embed`; cleanup of lexical UB |
