---
title: How to read a proposal
summary: How to read the numbers and revisions of WG21 proposals and where to find them, what parts a proposal is made of, how to map its wording changes onto the current draft, and how to tell whether it finally entered the standard as a new feature or as a defect fix.
tags: proposal, WG21, method, guide, DR
group: Getting started
updated: 2026-10-19
---

!!! tldr
    - In a number like P2647R1, P2647 is the paper number and R1 is the revision; a proposal keeps its number from R0 until it is adopted. `wg21.link/P2647` always points to the latest revision.
    - A proposal usually first explains the problem and motivation, then compares several designs, and finally gives the wording: a list of changes against the working draft of the time, with inserted and deleted text marked.
    - Section and paragraph numbers in the wording refer to the draft of the time of writing. When comparing with today's standard, look things up by stable name and then check against the text of the current draft; the draft text is the final word.
    - A proposal adopted as a defect report (DR) is treated as a fix to the old standard, and compilers usually apply the new rules in older `-std=` modes too; an ordinary new feature only takes effect in the new mode.
    - To tell what a proposal finally got adopted as, look at the labels on its status page, the current draft, the Annex C compatibility entries and the feature-test macros, not just the proposal itself.

## Numbers: N, P, R and issues

Every document of WG21 (the C++ standards committee) has a number. When reading proposals you will meet these kinds:

| Number | What it is | Example |
|---|---|---|
| N + four digits | Early proposals, and formal documents such as working drafts and meeting minutes | [[N4950]] is the public draft closest to C++23; [[N5054]] is a 2026 working draft |
| P + four digits + R + revision | Proposals from around 2015 on | [[P2647R1]]: the 2nd version of P2647 (R0 is the 1st) |
| CWG + number | Core language issues: errors, ambiguities or omissions in the wording | [[CWG2652]] |
| LWG + number | Library issues | [[LWG3000]] |

The paper number stays the same over the whole lifecycle. Each time the author revises it in response to review, a new revision is published: R0, R1, R2, and so on. So when discussing a proposal, give the revision: a design in R0 may have been overturned by R3.

A proposal roughly follows this path: optionally a study group (SG, organized by topic; for example SG16 handles text and Unicode) discusses it first; then a design group reviews the design (EWG for language features, LEWG for the library); then a wording group reviews the text (CWG for the language, LWG for the library); finally there is a plenary vote, and the editor merges the wording into the working draft. [[P2513R4]], for example, went through SG16, then EWG, and finally had its wording reviewed by CWG. More background is in [[history/standards-timeline]]; how to read the wording itself is in [[topics/how-to-read-the-standard]].

## Where to find things

| Address | Purpose |
|---|---|
| `wg21.link/P2647R1` | Full text of a specific revision |
| `wg21.link/P2647` | Without a revision number, jumps to the latest revision |
| `wg21.link/P2647/github` | The status issue for the paper on github.com/cplusplus/papers |
| `wg21.link/cwg2652`, `wg21.link/lwg3000` | Pages for CWG / LWG issues |
| `wg21.link/index.txt`, `wg21.link/index.json` | Index of all documents with titles, authors and dates, searchable by keyword |
| `wg21.link/draft` | The current working draft on eel.is (HTML) |
| `jtc1/sc22/wg21/docs/papers/<year>/` on open-std.org | Mailings listed by year, each a batch of new documents |
| cppreference's compiler support page, Clang's C++ Status and DR Status pages | Which version of each compiler implements a given proposal |

On this site, `[[P2647R1]]` and `[[CWG2652]]` also link to wg21.link.

Each proposal has an issue on github.com/cplusplus/papers, and its labels record how far the proposal has got. For example, the P2647 issue is labelled `EWG` and `plenary-approved` (approved by the plenary), and the P2513 one `CWG`, `C++23` and `plenary-approved`.

## What a proposal looks like

Take [[P2647R1]] (*Permitting static constexpr variables in constexpr functions*) as an example. It is short but has the complete structure.

**Header.** Document number, date, target group (Audience: EWG), author contact details. The Audience tells you where it is in the review process.

**Revision history.** Lists what each revision changed relative to the previous one. P2647R1's revision history is a single sentence: relative to R0, the wording was updated and an example and a feature-test macro were added. The revision history is the quickest way into how a design changed, especially when reading a proposal with a dozen or more revisions.

**Motivation.** A good proposal starts with code that can't be written, or can only be written awkwardly. P2647's starting point is a function that converts a number to a hexadecimal digit:

<div class="compare" markdown="1">

```cpp title="C++20: OK" ok
char xdigit(int n) {
  static constexpr char digits[] =
      "0123456789abcdef";
  return digits[n];
}
```

```cpp title="C++20: not OK once constexpr is added" error std=c++20
constexpr char xdigit(int n) {
  static constexpr char digits[] =
      "0123456789abcdef";
  return digits[n];
}
```

</div>

C++20 does not allow a constexpr function to pass through the declaration of a static variable during execution, even if the variable is itself `constexpr`. Under `-std=c++20`, Clang 23 gives the warning `definition of a static variable in a constexpr function is a C++23 extension` for the code on the right, which becomes an error with `-pedantic-errors`.

**Design discussion and alternatives.** A proposal has to explain why existing ways of writing it are not good enough. P2647 lists four workarounds: subscript the literal directly, move the array to namespace scope, drop the `static`, or wrap it in a consteval lambda. Each has a cost; the second, for example, exposes data that should be local. In big proposals this section is much longer and also records rejected designs and the reasons, which is often the most worthwhile part to read.

Claims in the motivation should be read in light of when they were written. P2647 says the version without `static` produced worse code on compilers of the time; at `-O2`, Clang 23 compiles both versions to a single table lookup, with identical generated code.

**Implementation experience.** Larger proposals usually say whether they have been implemented in some compiler or library and what user feedback was. A small change like P2647 has no such section.

**Wording.** The normative part of the proposal: changes to the working draft, place by place. The next section is devoted to reading it.

Design and wording are sometimes split into two papers. The design for fixing temporary lifetimes in range-based for is in [[P2644R1]], while the text CWG approved is in a separate [[P2718R0]], titled *Wording for P2644R1 Fix for Range-based for Loop*. The full story of this change is in [[papers/range-for-temporaries]].

## Reading wording: P2647R1

### What the proposal says

The wording of P2647R1 changes only one place. It is written as Change 7.7 [expr.const]/5.2, with the inserted text highlighted in green (shown here with `+`):

```diff
 (5.2) a control flow that passes through a declaration of a
       variable with static ([basic.stc.static]) or thread
       ([basic.stc.thread]) storage duration
+      , unless that variable is usable in constant expressions
       ;
```

It also inserts an example and changes the value of the feature-test macro `__cpp_constexpr` from `202207L` to `20XXXXL`. Leaving the value blank is common practice; the editor fills in the year and month of adoption when merging into the draft.

Different authors mark changes differently: some use `<ins>` and `<del>`, some green and red backgrounds, some underline and strikethrough; the beginning of a proposal usually explains which. They all read the same way: text marked as deleted is in the old draft and gone after the change, text marked as inserted is new, and the rest is kept as-is and is there only for context.

### Finding it in the current draft

The 7.7 and /5.2 in the proposal are numbers from the 2022 draft. Section and paragraph numbers may change afterwards, so look things up by stable name, not by number:

```bash
python3 tools/eel.py expr.const.core
```

Today the rule is in [[expr.const.core#2.2]]. [expr.const] was later split into several subclauses, and the rules for core constant expressions moved into [expr.const.core], so /5.2 became /2.2:

!!! std
    a control flow that passes through a declaration of a block variable ([basic.scope.block]) with static ([basic.stc.static]) or thread ([basic.stc.thread]) storage duration, unless that variable is usable in constant expressions;

The clause P2647 inserted is there verbatim, and the example it added became Example 1 of this subclause. But the beginning of the wording already differs from the proposal: a variable became a block variable. That is a later change, not something P2647 wrote. The draft is continually modified by later proposals, issues and editorial changes, so the text in a proposal can only tell you what it changed at the time; the current rule is whatever the draft says.

Feature-test macros are the same. Clang 23's `__cpp_constexpr` under `-std=c++23` is `202211L`, the value P2647 filled in; under `-std=c++2c` it is `202406L`, matching [[cpp.predefined]] in the current draft, which shows that a later proposal changed it again.

This rule is explained in full on the [[expr.const.core]] page, including the step before it, [[P2242R3]]: that proposal first allowed static variables in constexpr functions, as long as execution does not pass through their declarations.

## Reading wording: P2513R4, a DR

The wording of [[P2513R4]] (*char8_t Compatibility and Portability Fix*) changes three places, covering exactly the three common kinds of change in a proposal: the main text, Annex C, and a feature-test macro. Its header says Target: C++23 (DR C++20).

**The problem.** C++20 changed the type of `u8"…"` from `const char[N]` to `const char8_t[N]`, so `const char s[] = u8"abc";`, valid in C++17, no longer compiled in C++20 ([[diff.cpp17]]).

**Main text.** The proposal modifies paragraph 1 of [dcl.init.string], adding a sentence:

!!! std
    Additionally, an array of char or unsigned char may be initialized by a UTF-8 string literal, or by such a string literal enclosed in braces.

It also adds a statement at the end of the paragraph about integral conversion where necessary. In the proposal this subclause is numbered 9.4.3; in the current draft it is 9.5.3, with the same stable name. `eel.py dcl.init.string` confirms that the inserted sentence is in [[dcl.init.string#1]] verbatim.

**Annex C.** Whenever a change might make previously valid code change meaning or stop compiling, a compatibility note has to be added to Annex C. The entry P2513 added is now in [[diff.cpp20]], under [diff.cpp20.dcl]:

```cpp title="annex-c.cpp" error
struct A { char8_t s[10]; };
struct B { char s[10]; };
void f(A);
void f(B);
int main() { f({u8""}); }   // error: ambiguous call
```

Under C++20's original rules, `u8""` could only initialize a `char8_t` array, so `f(A)` was the only viable function. After the fix both aggregates can be initialized with `u8""`, and the call becomes ambiguous. When reading a proposal, the Annex C entries are the quickest way to learn what it breaks.

**Feature-test macro.** `__cpp_char8_t` changed from `201811L` to a new value, `202207L` in the current draft.

## DRs and new features

P2513 and P2647 were both adopted during the C++23 cycle, but in different capacities: the former is a defect report (DR) against C++20, the latter a new C++23 feature.

A **defect report** means the committee has decided that the old standard's rule was wrong in the first place, and the fix should be considered part of the old standard. There is only one up-to-date standard text: a DR's fix goes into the current draft, and the old standard's text is not republished; a DR takes effect through implementations. Clang's status page says it usually implements DRs retroactively in all older language modes where the fix makes sense; for other compilers, see their own documentation.

With Clang 23 the difference is immediate:

<div class="compare" markdown="1">

```cpp title="P2513 (DR)" ok std=c++20
// clang++ -std=c++20: no diagnostic
const char a[] = u8"abc";
const unsigned char b[] = u8"abc";
// __cpp_char8_t == 202207L
```

```cpp title="P2647 (new feature)" std=c++20
// clang++ -std=c++20: warning
// "... is a C++23 extension"
constexpr char xdigit(int n) {
  static constexpr char d[] = "0";
  return d[n];
}
// __cpp_constexpr == 202002L
```

</div>

The code on the left passes under `-std=c++20` with no diagnostic, and `__cpp_char8_t` reports the fixed value `202207L`, as if C++20 had specified it that way from the start. In the same mode, the ambiguous Annex C example gives an error as well. The code on the right is accepted under `-std=c++20` only as an extension, and `__cpp_constexpr` is still C++20's `202002L`.

This affects how you write code in two ways. First, a DR changes behavior in older modes, so upgrading the compiler without changing `-std=` can change what code means. Second, when checking whether a feature can be used in C++17 or C++20, first find out whether it is a DR. The Clang and GCC status pages and cppreference's compiler support tables all mark DRs separately. This site marks such changes with {{dr}}.

<details class="fine" markdown="1"><summary>CWG issue statuses</summary>

The status on the CWG issues list records how far an issue has got: Open (a new issue), Drafting (rough consensus, no wording yet), Review (wording exists), Ready / Tentatively Ready (wording is ready, awaiting the plenary), NAD (not a defect).

After adoption, the status records which document it was incorporated into, such as CD7 or C++26. According to the explanation at the start of the list, such a status can mean either a DR or a change to the working draft only (accepted), so the status by itself does not say whether it applies retroactively. To find out, look at the disposition on the issue page, or at Clang's C++ Defect Report Support page, which lists by issue number the Clang version from which each DR is implemented.

</details>

## How to tell what was finally adopted

The last revision of a proposal is not necessarily the one adopted: some proposals are modified by later proposals after adoption, some are split or merged before adoption, and some are never adopted. Check in this order:

1. **The status issue.** If the labels on `wg21.link/Pxxxx/github` include `plenary-approved`, the plenary adopted it. Without that label, the design in the proposal is only a design.
2. **The current draft.** Use `python3 tools/eel.py <stable-name>` or eel.is to find where the wording changes go, confirm the text is there, and watch for later changes, like the block that was later added to P2647's item.
3. **Annex C.** [[diff.cpp20]], [[diff.cpp23]] and so on list the changes in each version that break compatibility, and the entries name the affected subclauses.
4. **Feature-test macros.** Values in [[cpp.predefined]] are given as year and month, and a proposal that changes a feature usually updates it to a new year and month. The value a compiler reports roughly indicates how far it has implemented things.
5. **Compiler status pages.** They list the implemented revision, and whether it is treated as a DR.

## Reading path

The other pages in this section each cover one design decision, traced through the proposals: what the problem was, which approaches were considered, where the final wording changed the standard, and what the consequences were. Pick whatever interests you, or follow the order below.

**Objects, values and initialization**

- [[papers/guaranteed-copy-elision]]: how C++17, by redefining prvalues, made `return T{};` no longer need a callable copy constructor.
- [[papers/implicit-object-creation]]: why, strictly speaking, memory from `malloc` held no objects before C++20.
- [[papers/implicit-move]]: when `return x;` is treated as an rvalue.
- [[papers/range-for-temporaries]]: lifetime extension of temporaries in the range initializer.
- [[papers/trivial-relocation]]: replacing a move plus destruction with a single memory copy.

**Declarations, templates and metaprogramming**

- [[papers/declarations-and-lookup]]: the rewrite of the name lookup rules.
- [[papers/deducing-this]]: the problems `this auto self` solves.
- [[papers/class-type-template-parameters]]: which classes' objects can be template arguments.
- [[papers/pack-indexing]]: `Ts...[0]`.
- [[papers/reflection]]: C++26's `^^` and `std::meta`.

**Errors, safety and constant evaluation**

- [[papers/contracts]]: `pre`, `post` and `contract_assert`.
- [[papers/erroneous-behaviour]]: why reading an uninitialized variable went from UB to erroneous behavior.
- [[papers/constexpr-exceptions]]: `throw` comes to constexpr.
- [[papers/library-hardening]]: checked preconditions.

**The standard library**

- [[papers/std-execution]]: the sender/receiver model.
- [[papers/mdspan]]: the design of a multidimensional view.
- [[papers/print-and-format]]: type-safe formatting.
- [[papers/ranges-to]]: collecting a range into a container.
- [[papers/generator]]: the first coroutine type in the standard library.

## Questions

!!! question
    A proposal's wording says Change [expr.prim.lambda.closure]/4, and you can't find the sentence it wants to change in that paragraph of the current draft. What could be the reason? What should you do?

<details markdown="1">
<summary>Answer</summary>

The paragraph number is from the draft of the time the proposal was written. Later proposals, issues or editorial changes may have inserted or deleted paragraphs, or split the subclause (P2647's paragraph moved from [expr.const]/5.2 to [expr.const.core]/2.2). It is also possible that the proposal was not adopted, or that its change was later replaced by another proposal.

Search for keywords from the proposal's sentence under the same stable name in the current draft; if it moved, look in the neighbouring subclauses. Once found, go by the draft text, and use the status issue to confirm whether the proposal was adopted.
</details>

!!! question
    Your project compiles with `-std=c++20`. After a compiler upgrade, a call `f({u8""})` suddenly gives an ambiguity error, though `-std=` was never changed. Why?

<details markdown="1">
<summary>Answer</summary>

[[P2513R4]] is a DR against C++20. The new compiler applies the fixed [[dcl.init.string#1]] under `-std=c++20` too, allowing `u8""` to initialize a `char` array, so a call that used to have only one viable function gains another candidate. Annex C's [[diff.cpp20]] records this example. Writing the type of the argument explicitly, as in `f(A{u8""})`, removes the ambiguity.
</details>
