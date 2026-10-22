---
title: General principles
summary: "Clause 4 guide: this clause is not about any particular language feature but about how the rules take effect: what a compiler owes a program, what the compiled program has to behave like, and how to find and read a rule in the standard."
updated: 2026-10-18
---

!!! tldr
    - After this clause you can answer questions like: does a compiler conform if it only gave a warning? Why may the optimizer delete my overflow check? Why did the output printed before the crash disappear?
    - Clauses 1–3 are the fixed opening of an ISO document; this site files them here as well. The classification of behavior in Clause 3 (undefined, unspecified, implementation-defined, erroneous) is used together with this clause.
    - Suggested order: read the behavior classification in [[intro.defs]] first, then [[intro.compliance]]; before reading the grammar productions of Clauses 5–15, look at [[syntax]].

## What a compiler owes a program

[[intro.compliance]] specifies what a compiler must do when a program is wrong. Most errors require only a diagnostic, and a warning is enough; only a few cases, such as `#error` and a failed `static_assert`, require the compilation to be rejected; and there is a class of rules (for example the ODR across files) that the compiler need not check at all. This explains why compiling successfully never proves code is valid, and also why compiler extensions and options like `-pedantic` exist.

## What the compiled program has to behave like

The second half of the same page, [intro.abstract], defines the **abstract machine**: the semantics the standard describes are all stated for this hypothetical machine. An implementation only has to match it in observable behavior, and observable behavior covers only volatile accesses, data written to files, and the ordering of prompts on interactive devices. This is the as-if rule, and almost every compiler optimization relies on it.

Undefined behavior makes this freedom larger: the optimizer may assume it does not happen. C++26 introduced observable checkpoints, which specify which output before UB must actually be produced.

## How to find rules in the standard

[[intro.structure]] is the map of the whole document: which clauses cover the language, which cover the library, and which annexes are only summaries. [[syntax]] explains the notation for grammar productions; almost every subclause of Clauses 5–15 has productions, so it is worth reading once beforehand.

## Clauses 1–3

[[intro.scope]] is a single sentence: the standard specifies requirements on implementations. [[intro.refs]] lists the external standards C++ depends on, the most important being the C23 standard library and IEEE 754 floating point. [[intro.defs]] is the standard's dictionary, and its classification of behavior is a prerequisite for understanding Clause 4.

[[intro.scope]] and [[intro.refs]] can be skimmed; come back to them when you need to look up how the C standard specifies something.

!!! history "How this clause has changed"
    From C++98 to C++14, the scope, normative references, terms and definitions, implementation compliance and program execution all lived in Clause 1, General. C++17 split the opening into today's Clauses 1–4, following the common structure of ISO documents. Later, program execution ([[intro.execution]]) and multithreading ([[intro.multithread]]) moved to [[basic.exec]] in Clause 6, but their stable names did not change, so today some subclauses named `intro.*` live in Clause 6.
