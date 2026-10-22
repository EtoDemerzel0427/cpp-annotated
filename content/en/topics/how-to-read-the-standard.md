---
title: How to read the C++ standard
summary: How to find the text in the C++ standard that answers a question, understand it, cite it precisely, and how the standard changes through proposals and defect reports.
tags: guide, method, tools
updated: 2026-10-19
---

!!! tldr
    - The standard is a specification written for compiler and standard library implementers, not something to read from cover to cover. Look things up with a concrete question in hand and it becomes readable.
    - Clauses are located by stable names in square brackets, such as `[basic.life]`. Cite as `[basic.life]/8`, and give the version when discussing older ones, because paragraph numbers change.
    - Only the main text, the grammar and Annex D are binding. Notes, examples and footnotes only aid understanding and can't serve as an argument on their own.
    - shall is a requirement, should a recommendation, may a permission, and can only states a fact. Italicized words are terms defined right there; find the definition before reading the rule.
    - Compiler behavior is evidence, not a conclusion. When compilers disagree with each other or with the standard is exactly when you need to look up the standard.

## The standard and the drafts

The official name of the C++ standard is ISO/IEC 14882, produced by WG21 (the C++ standards committee). The official versions published by ISO cost money, but the committee's **working draft** is public, and each official version has a public draft with nearly identical content:

| Version | Closest public draft | `__cplusplus` |
|---|---|---|
| C++98, C++03 | — | `199711L` |
| C++11 | [[N3337]] | `201103L` |
| C++14 | [[N4140]] | `201402L` |
| C++17 | [[N4659]] | `201703L` |
| C++20 | [[N4861]] | `202002L` |
| C++23 | [[N4950]] | `202302L` |
| C++26 | The current working draft | Specified as `202603L` in the current draft ([[cpp.predefined]]) |

To see how a rule was worded in C++17, read N4659. This site follows the current working draft on eel.is. The draft already contains the annex [[diff.cpp26]] (differences from C++26), which shows that C++26 has been finalized and the draft has started collecting changes for the next version. The {{c++26}} badge on this site marks features introduced in C++26.

The structure of the standard is described in [[intro.structure]]: chapters 1–4 cover scope, terms and general principles; chapters 5–15 are the core language (from lexical conventions [[lex]] to preprocessing [[cpp]]); chapters 16–33 are the standard library; and finally there are annexes A–G (grammar summary, implementation limits, compatibility, deprecated features, a summary of UB, a summary of IFNDR, and so on).

## The address of a clause

### Stable names

Every clause has a **stable name** written in square brackets: `[basic.life]`, `[dcl.init.list]`, `[over.match.best]`. Section numbers change between versions: `[basic.life]` is 6.8 in C++17 and 6.8.4 in the current draft, while the stable name is kept as constant as possible. So always cite clauses by stable name.

Stable names are hierarchical: `dcl.init` is initialization, `dcl.init.list` is list-initialization within it, and `dcl.init.aggr` is aggregate initialization. There are exceptions: when a clause moves, it sometimes keeps its old name; `[intro.execution]` and `[intro.races]` now live under [[basic.exec]] in chapter 6 but their names still start with `intro.`.

### Paragraph numbers

Paragraphs within each clause are numbered from 1, and eel.is shows the numbers in the margin. List items within a paragraph are numbered "paragraph.item", with further levels for nested lists: 2.3.4 in [[intro.compliance]] is the 4th sub-item of item 3 of paragraph 2. Notes and Examples belong to the paragraph they appear in and are numbered separately within the clause as Note 1, Example 2 and so on.

### How to cite

| Form | Meaning |
|---|---|
| `[basic.life]` | The whole clause |
| `[basic.life]/8` or `[basic.life] p8` | Paragraph 8 |
| `[basic.life]/8.1` | Item 1 of paragraph 8 |
| `C++23 [basic.life]/8` or `N4950 [basic.life]/8` | Paragraph 8 in a specific version |
| `[basic.life]/8, Note 5` | Note 5 in paragraph 8 |

Paragraph numbers change often between versions, so always give the version when discussing the behavior of an older one. eel.is URLs correspond one-to-one with this notation: `https://eel.is/c++draft/basic.life#8.1`. On this site, `[[basic.life#8]]` renders as [[basic.life#8]].

## Which text is binding

The text of the standard falls into two categories:

- **Normative** text constitutes requirements: the main paragraphs, the grammar productions, and the only normative annex, Annex D (deprecated features);
- **Informative** text only aids understanding and imposes no requirements: notes, examples, footnotes, the other annexes, and the table of contents and index.

So you can't argue that something is legal or illegal from a note or an example alone. Notes and examples are supposed to agree with the main text; when they conflict, the main text wins, and that usually indicates a defect in the standard, for which there is often a corresponding CWG issue.

Notes and examples are still very useful, though: they often point out consequences of the main text, or directly show the committee's intent. The worked example below relies on an example in the standard to confirm its conclusion.

***Recommended practice*** paragraphs are normative but worded with should; they are only recommendations and don't affect whether an implementation conforms.

### shall, should, may, can

The standard uses these auxiliary verbs according to ISO's drafting rules:

| Word | Meaning | Example |
|---|---|---|
| shall / shall not | Requirement / prohibition | "A program shall contain exactly one function called `main`" ([[basic.start.main]]) |
| should / should not | Recommendation | "An implementation should issue a diagnostic" ([[intro.abstract]]) |
| may / need not | Permission | "A conforming implementation may have extensions" ([[intro.compliance]]) |
| can / cannot | Ability or possibility; only states a fact | Common in notes |

The consequences of a program violating a shall rule are determined by [[intro.compliance]]: by default it is ill-formed and the compiler must issue a diagnostic; when the rule says no diagnostic is required, it is IFNDR (ill-formed, but no diagnostic required; the compiler may compile it without a word); when the rule itself says the result is undefined, it is UB. The behavior categories are in [[intro.defs]].

Notes deliberately use can rather than may, because a note can't grant permission. When a note says an implementation "can" do something, it is only describing what the main text already allows.

## Italics are definitions

A word that appears in *italics* in the main text, immediately followed by an explanation, is a term defined right there. For example, [[basic.life#2]] defines *lifetime* and *vacuous initialization*. Every later occurrence of the word means exactly that definition; its everyday English meaning doesn't count.

- Terms used across chapters are defined together in chapter 3, [[intro.defs]];
- Most core terms are defined in place: *odr-use* in [[basic.def.odr]], *glvalue* in [[basic.lval]], *core constant expression* in [[expr.const.core]];
- The standard's index lists where each term is defined, and eel.is can be searched as well.

object, entity, variable and name all have precise and distinct meanings in the standard. When you meet a word you're unsure about, find its definition first; that's the first step in avoiding a misreading.

## Grammar and library specifications

The notation for grammar productions is described in [[syntax]]: italics are nonterminals, monospace is terminals, and the subscript opt means optional. Matching the grammar is only the first step, a long way from being well-formed.

The specification of a library function is made of several elements, whose precise meanings are defined in [[structure.specifications]]:

- *Constraints*: if not met, the function doesn't participate in overload resolution;
- *Mandates*: if not met, the program is ill-formed;
- *Preconditions*: violating them is UB;
- *Hardened preconditions* {{c++26}}: in a hardened implementation these conditions are checked with terminating semantics before the function executes, and a violation terminates the program; in a non-hardened implementation a violation is UB;
- *Effects*, *Returns*, *Throws*, *Complexity*, and so on.

The exact meaning of "*Effects*: Equivalent to: ..." is also in [[structure.specifications]]; read that section before reading library clauses. Members and concepts marked exposition only exist only to make the description convenient, and implementations needn't actually provide them ([[conventions]]).

## A complete lookup: `unsigned char x = x;`

```cpp ub
unsigned char x = 12;
void f() {
  unsigned char x = x;   // which x is on the right? what is the behavior of this line?
}
```

A reader familiar with C++26 might think: the inner `x` hasn't been initialized yet, and reading an uninitialized automatic variable is erroneous behavior (behavior that is well-defined since C++26 but that the standard deems incorrect). Check it step by step:

1. **Which `x` does the right side refer to?** [[basic.scope.pdecl#1]] says the name declared by a declarator takes effect right after the complete declarator, that is, before the initializer. So the `x` in the initializer is already the inner `x`; the outer one is hidden.
2. **Has the inner `x`'s lifetime begun at that point?** [[basic.life#2]]: an object's lifetime begins when its initialization is complete. We are in the middle of its initialization, so its lifetime hasn't begun.
3. **What happens when it's read before its lifetime begins?** [[basic.life#8]]: when storage has been allocated but the lifetime hasn't begun, accessing the object through a glvalue referring to it is UB ([[basic.life#8.1]]). The initializer performs an lvalue-to-rvalue conversion on `x`, which is an access (see the definition of *access* in [[intro.defs]]).
4. **Is there corroboration?** Example 1 in [[basic.scope.pdecl]] is exactly this code, and states that the initialization of the second `x` has undefined behavior, because the initializer accesses it outside its lifetime.

The conclusion is UB, not erroneous behavior. Erroneous behavior applies to objects whose lifetime has begun and whose value is merely erroneous (such as reading `y` after `unsigned char y;`); here the object's lifetime hasn't even begun.

The pattern of the lookup is: first establish what the name refers to (name lookup), then what state the object is in (lifetime, value), then find the paragraph that governs the operation, and finally cross-check with notes and examples.

Compiler behavior is only a reference: Clang 23 gives no warning for the code above under `-Wall -Wextra`; only if `x` is used further in the function does it give `-Wuninitialized`.

## How the standard changes

**Proposals.** All substantive changes enter the standard through proposals (papers). Proposal numbers look like P2795R5: P plus four digits is the paper number, and R plus a number is the revision. Early documents and working drafts use N numbers, such as N4950. After a proposal has been reviewed by the committee's groups and passed by a plenary vote, the editors merge it into the working draft. On this site, `[[P2795]]` and `[[N4950]]` link to wg21.link, the committee's short-link service for documents.

**Issues and DRs.** Errors, ambiguities and contradictions in the standard are handled through issues. Core language issues are CWG issues and library issues are LWG issues; each has a public list recording the problem, the discussion and the status. Links are written `[[CWG2551]]`, `[[LWG3000]]`. If an issue's resolution is treated as a correction of a defect in a published standard, it is called a **defect report** (DR). Compilers usually apply DRs to older language modes as well, so some C++23 changes take effect under `-std=c++17` too. This site marks such changes with {{dr}}. Some proposals are also adopted as DRs, with the same effect.

**Editorial changes.** Changes that don't alter technical meaning (clarified wording, typesetting, reorganized sections) are made directly by the editors in the cplusplus/draft repository on GitHub. Many changes in section and paragraph numbers come from here, which is another reason to cite by stable name.

## Tools

| Tool | Use |
|---|---|
| eel.is/c++draft | HTML version of the current working draft, one page per stable name, with direct links to paragraphs (`#8.1`). This site's clause text follows it |
| timsong-cpp.github.io/cppwp | HTML version in the same style that also provides older versions (`/cppwp/n4950/`, `/cppwp/n4659/` and so on); good for looking up older standards |
| github.com/cplusplus/draft | LaTeX source of the draft; you can see the diff of every change and trace where a piece of wording came from |
| wg21.link | Short links to proposals, N documents and CWG/LWG issues |
| CWG / LWG issue lists | Check whether a rule has a known defect and what the committee intended |
| cppreference.com | Unofficial reference site organized by feature, noting version differences, DRs and compiler support; a good entry point, but conclusions should go back to the standard's text |
| Compiler Explorer (godbolt.org) | Quick checks across several compilers and versions; the godbolt button on this site's code blocks opens it directly |
| Compiler status pages | Clang's C++ Status, GCC's C++ Standards Support, MSVC's conformance table, for finding which version implemented a feature |

All three major compilers have bugs, have features not yet implemented, and are not fully conforming in their default modes (see the part about extensions in [[intro.compliance]]). "Clang accepted it" or "GCC rejected it" is only evidence; reach a conclusion together with the text.

## The process for looking things up

1. **Make the question specific.** Break "is this code correct?" into "which declaration does this name lookup find?", "what conversions happen here?", "does this read happen within the lifetime?".
2. **Find the clause.** Start from the structure in [[intro.structure]], this site's table of contents, the eel.is index or cppreference's see-also links, and find the most relevant stable name.
3. **Find the paragraph.** Read the definitions and overview at the start of the clause first, then locate the specific paragraph. Pay attention to whether list items are joined by "and" or "or".
4. **Chase definitions.** Follow italicized terms and cross-references of the form `([xxx])` when needed, rather than guessing from everyday experience.
5. **Look at notes and examples.** They often answer the question directly, or point out a consequence you missed.
6. **Check the annexes.** Annex C (compatibility), Annex F (UB summary) and Annex G (IFNDR summary) make good indexes.
7. **Check issues.** When the text looks contradictory or incomplete, search the CWG/LWG issue lists to see whether it has already been discussed.
8. **Verify with compilers.** Try several compilers and versions, with `-pedantic-errors` and sanitizers. Disagreement between compilers is itself a sign the question isn't simple.
9. **Write down the conclusion and the source.** Use the form `[stable.name]/N`, and give the version.

## A reading path

This site is organized by the standard's chapters, but you don't have to read them in order. One workable path:

1. **The metalanguage**: this page, [[intro.defs]] (especially the behavior categories), [[intro.compliance]] (conformance, the as-if rule, observable behavior), [[syntax]] (grammar notation).
2. **How programs are translated and organized**: [[lex.phases]] (phases of translation), [[basic.def]] and [[basic.def.odr]] (declarations, definitions and the ODR), [[basic.scope]] and [[basic.lookup]] (scopes and name lookup), [[basic.link]] (linkage).
3. **The object model**: [[basic.memobj]], [[intro.object]], [[basic.life]] (objects, storage, lifetime), [[basic.types]] (types), [[basic.lval]] and [[conv]] (value categories and standard conversions).
4. **Execution**: [[intro.execution]] (order of evaluation), [[intro.multithread]] (the memory model and data races), [[expr.const]] (constant evaluation).
5. **Go deeper as needed**: [[dcl.init]] (initialization), [[class]] (classes), [[over]] (overloading), [[temp]] (templates), [[except]] (exceptions), [[module]] (modules), [[basic.contract]] (contracts). For the library, read the method of description in [[library]] first, then go into chapters as your interest leads.
