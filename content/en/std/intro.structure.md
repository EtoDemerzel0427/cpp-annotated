---
title: Structure of this document
summary: "A map of the whole standard: Clauses 5–15 are the language, Clauses 16–33 and Annex D are the library, and the remaining annexes are informative summaries; where to look for the answer to a given question."
updated: 2026-10-18
---

!!! tldr
    - Clauses 5–15 describe the language; Clauses 16–33 and Annex D describe the standard library.
    - Among the annexes, only Annex D (deprecated features) is normative. The grammar summary, implementation limits, compatibility differences, and the UB and IFNDR summaries are all informative; when citing them, go back to the main text.
    - To find out why code stopped compiling, or changed meaning, after upgrading the standard version, look in Annex C.
    - Cite subclauses by stable name (such as `[basic.life]`), not by number; the numbers often change between editions.

## Where to look

| Question | Where to look |
|---|---|
| Is this code valid? What does it mean? | Clauses 5–15: first the grammar ([[syntax]]), then the semantic rules of the relevant subclause |
| What does this library function guarantee? | First learn what elements like *Preconditions* and *Effects* mean in [[structure.specifications]] in Clause 16, then read the relevant clause |
| Why did my code change after switching `-std=`? | Annex C [[diff]], which lists, by version, the changes that affect existing code |
| Is this UB or IFNDR? | Annex F [[ub]] and Annex G [[ifndr]] are indexes; the conclusion has to rest on a paragraph of the main text |

## The language (¶1)

¶1 Clause 5 [[lex]] through Clause 15 [[cpp]] describe the C++ language, with the grammar given in the notation described in [[syntax]]. For convenience, Annex A [[gram]] repeats all the productions in one summary.

| Clause | Contents |
|---|---|
| 5 [[lex]] | Lexical conventions: phases of translation, character sets, tokens, literals |
| 6 [[basic]] | Basics: declarations and definitions, the ODR, scope, name lookup, linkage, the object model, types, program execution, the memory model, contract assertions |
| 7 [[expr]] | Expressions: value categories, conversions, the operators, constant evaluation |
| 8 [[stmt]] | Statements |
| 9 [[dcl]] | Declarations: specifiers, declarators, initialization, function definitions, structured bindings, enumerations, namespaces, attributes |
| 10 [[module]] | Modules |
| 11 [[class]] | Classes |
| 12 [[over]] | Overloading |
| 13 [[temp]] | Templates |
| 14 [[except]] | Exception handling |
| 15 [[cpp]] | Preprocessing |

Clauses 1–4 are not part of the language description. When [[intro.compliance]] says a freestanding implementation supports "the whole language described in Clauses 5 through 15", it means exactly the range in the table above.

## The library (¶2)

¶2 Clause 17 [[support]] through Clause 33 [[exec]], together with Annex D [[depr]], are collectively called the **library clauses** and describe the standard library. How they are written is specified by Clause 16 [[library]].

Clause 16 itself defines no library facilities. It specifies how to read the library clauses: how to read header synopses, and what elements like *Constraints*, *Mandates*, *Preconditions*, *Effects*, *Returns*, *Throws* and *Complexity* mean ([[structure.specifications]]). It also specifies the contract between programs and the library, such as which names are reserved to the implementation ([[reserved.names]]) and whether a program may add things to `namespace std` ([[namespace.std]]).

| Clause | Contents |
|---|---|
| 17 [[support]] | Language support: `<cstddef>`, `<limits>`, `<new>`, `<exception>`, `<contracts>`, `<compare>`, `<coroutine>` and others |
| 18 [[concepts]] | Concepts |
| 19 [[diagnostics]] | Exception classes, `<system_error>`, `<stacktrace>`, `<debugging>` |
| 20 [[mem]] | Smart pointers, allocators, `<memory_resource>` |
| 21 [[meta]] | Type traits, `<ratio>`, reflection `<meta>` |
| 22 [[utilities]] | `pair`, `tuple`, `optional`, `variant`, `expected`, function objects, `<bit>` and others |
| 23 [[containers]] | Containers, plus `span` and `mdspan` |
| 24 [[iterators]] | Iterators |
| 25 [[ranges]] | Ranges |
| 26 [[algorithms]] | Algorithms |
| 27 [[strings]] | Strings |
| 28 [[text]] | `<charconv>`, localization, `<format>`, regular expressions |
| 29 [[numerics]] | Numerics |
| 30 [[time]] | Time |
| 31 [[input.output]] | Input/output |
| 32 [[thread]] | Concurrency |
| 33 [[exec]] | Execution control (`std::execution`) |

Annex D is listed among the library clauses because deprecated features are still part of the standard and implementations must support them. Deprecation only means a feature may be removed in the future and is not recommended for new use.

## The annexes (¶3–¶4)

¶3 Annex B recommends lower bounds on the capacity of implementations.

¶4 Annex C summarizes the evolution of C++ since its first published description and explains in detail the differences between C++ and C; certain features that exist only for compatibility are in Annex D.

All the annexes of the current draft are listed below; [intro.structure] does not mention E, F and G:

| Annex | Status | Contents |
|---|---|---|
| A [[gram]] | Informative | Grammar summary, which accepts a superset of valid code |
| B [[implimits]] | Informative | Recommended minimums for quantities such as nesting depth and template recursion depth |
| C [[diff]] | Informative | Differences from C and from each earlier version of C++ |
| D [[depr]] | Normative | Deprecated features |
| E [[uaxid]] | Informative | Conformance with Unicode UAX #31 (identifiers) |
| F [[ub]] | Informative | Summary of core-language undefined behavior |
| G [[ifndr]] | Informative | Summary of ill-formed, no diagnostic required rules |

Each entry in Annex C states the affected subclause, the change, the rationale, and the effect on existing code, with an example. For instance, [[diff.cpp23]] lists the C++26 changes that make C++23 code change meaning or become invalid.

!!! history
    The text refers to ranges with stable-name intervals like "Clause [support] through Clause [exec]", not clause numbers, so [intro.structure] hardly needs changing when clauses are added or removed. Clause 33 [exec] is new in C++26; [mem], [meta], [text] and other clauses were split or reorganized out of larger clauses over successive revisions.
