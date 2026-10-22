---
title: Basics
summary: "A guide to Chapter 6: where names and declarations, the ODR, scope and name lookup, linkage, objects and lifetime, types, program execution and contracts are each specified, and the basic distinctions the chapter draws."
updated: 2026-10-19
---

!!! tldr
    - Chapter 6 defines the basic terms shared by the rest of the standard: name, declaration, entity, scope, linkage, object, lifetime, type, evaluation.
    - The chapter has three parts: names and declarations in the program text (6.1–6.7), objects and types at run time (6.8–6.9), and how the program executes (6.10–6.11).
    - Names, declarations, scopes and linkage belong to the program text; objects, storage, lifetime and values belong to run time. Much confusion comes from mixing up these two layers.
    - Many rules in this chapter are IFNDR (e.g. the ODR) or undefined behavior (e.g. lifetime, data races) when violated, rather than errors the compiler must report.

The answers to many C++ questions are in Chapter 6: why a name can't be found, whether two functions with the same name in two files are the same function, why a program fails to link, why a pointer can no longer be used, what happens when two threads write the same variable at once.

Chapter 5 [[lex]] splits source files into tokens, and Chapters 7 onward specify the meaning of each syntactic construct: expressions, statements, declarations, classes, templates. The terms they share are almost all defined in Chapter 6 [basic].

## How the chapter is organized

### Names, declarations and entities (6.1–6.7)

| Subclause | Content | Page on this site |
|---|---|---|
| 6.1 | Names, declarations, entities, variables, local entities | [[basic.pre]] |
| 6.2 | Which declarations are also definitions | [[basic.def]] |
| 6.3 | The one-definition rule (ODR) and odr-use | [[basic.def.odr]] |
| 6.4 | Scope: which scope a declaration belongs to, and when two declarations conflict | [[basic.scope]] |
| 6.5 | Name lookup: unqualified lookup, qualified lookup, member lookup, argument-dependent lookup | [[basic.lookup]] |
| 6.6 | {{c++26}} Splice specifiers `[: r :]`: turning a reflection back into a program construct | [[basic.splice]] |
| 6.7 | Linkage: when two declarations declare the same entity | [[basic.link]] |

A suggested reading order: first [[basic.pre]] and [[basic.def]], to see what a declaration introduces; then [[basic.scope]] and [[basic.lookup]], to see where declarations live and how names are found; then [[basic.link]], to see when declarations in different translation units are the same entity ([[basic.link#8]]); and finally [[basic.def.odr]]. The ODR specifies how many definitions one entity may have and how closely those definitions must agree, and it uses all the earlier concepts.

### Memory, objects and types (6.8–6.9)

| Subclause | Content | Page on this site |
|---|---|---|
| 6.8.1 | Memory model: bytes, memory locations | [[intro.memory]] |
| 6.8.2 | Object model: how objects are created, subobjects, implicit object creation | [[intro.object]] |
| 6.8.3 | Alignment | [[basic.align]] |
| 6.8.4 | Lifetime | [[basic.life]] |
| 6.8.5 | Indeterminate and erroneous values | [[basic.indet]] |
| 6.8.6 | Storage duration: static, thread, automatic, dynamic | [[basic.stc]] |
| 6.8.7 | Temporary objects | [[class.temporary]] |
| 6.9 | Type categories, trivially copyable types, fundamental types, compound types, cv-qualification, conversion ranks | [[basic.types]] |

Most common undefined behavior comes from this part: accessing an object outside its lifetime ([[basic.life]]), reading an indeterminate value ([[basic.indet]]), misalignment ([[basic.align]]), and the type-aliasing rule together with [[basic.lval]].

### Program execution (6.10–6.11)

| Subclause | Content | Page on this site |
|---|---|---|
| 6.10.1 | Order of evaluation within a single thread | [[intro.execution]] |
| 6.10.2 | Multiple threads, data races, forward progress | [[intro.multithread]] |
| 6.10.3 | The `main` function, initialization of static variables, program termination | [[basic.start]] |
| 6.11 | {{c++26}} Evaluation of the contract assertions `pre`, `post`, `contract_assert` and handling of violations | [[basic.contract]] |

## Some basic distinctions

### Read terms by their definitions

Chapter 6's terms are often narrower than their everyday meaning. Per [[basic.pre]], a **variable** is introduced by the declaration of an object or a reference, but non-static data members of reference type and template parameters are not variables; the identifier of a label is not a **name**. Since C++23, a **scope** is a region of the program text, not the range over which a name can be used ([[basic.scope]]). When you meet such a word, go back to its definition and check.

### Program text versus run time

Names, declarations, scopes and linkage are static concepts; they describe the program text. Objects, storage, lifetime and values are dynamic concepts; they describe execution.

The two are connected through declarations, but not one-to-one. An automatic variable in a function has one declaration and one name in the source, yet each call of the function creates a new object; with recursion, the same name corresponds to several objects at once.

### Consequences of breaking the rules

Many rules in this chapter require no diagnostic when violated. Most requirements of the ODR are IFNDR (ill-formed, but the compiler need not report it), because the compiler sees one translation unit at a time and cannot see conflicts between files ([[basic.def.odr]]). Violations of the lifetime and data-race rules are undefined behavior, because whether they are violated depends on run-time state ([[basic.life]], [[intro.races]]).

Understanding why a rule requires no diagnostic often also tells you what it is guarding against. These kinds of consequence are defined in [[intro.defs]] and [[intro.compliance]].

### Headers and modules

C++20 modules reworked many concepts that used to depend on textual order. In a module, whether a declaration can be used depends on whether it is **reachable** ([[module.reach]]), not only on whether it appeared earlier; and deciding whether two declarations are the same entity also depends on which module they are attached to ([[basic.link#8]]). Much of the wording in the first part exists to accommodate both ways of organizing code, headers and modules.

## Main changes by version

| Version | Change |
|---|---|
| C++11 | Multi-threaded memory model ([[intro.multithread]]); the term odr-use |
| C++17 | inline variables; rewritten object-model wording (objects are created by a definition, a new-expression, changing the active member of a union, or creating a temporary object); temporary materialization and guaranteed copy elision |
| C++20 | Modules bring module linkage, reachability and TU-local entities; implicit object creation ([[P0593R6]]); signed integers use two's complement |
| C++23 | Scope and name lookup rewritten ([[P1787R6]]); extended floating-point types |
| C++26 | Static reflection: [[basic.splice]] and the type `std::meta::info`; contracts: [[basic.contract]] and contract-assertion scope; erroneous values ([[basic.indet]]); name-independent declarations `_` |
