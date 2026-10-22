---
title: Compatibility (Annex C)
summary: Annex C lists, version by version, the changes that make old code stop compiling or silently change meaning, plus the differences between C++ and C; when you raise -std, use it together with the compiler's compatibility warnings.
updated: 2026-10-19
---

!!! tldr
    - Annex C answers one question: if you replace `-std=c++17` with a newer version, which previously valid code becomes an error, becomes undefined, or silently changes meaning?
    - The per-version subclauses are cumulative: upgrading from C++17 to the current draft means reading [[diff.cpp17]], [[diff.cpp20]], [[diff.cpp23]] and [[diff.cpp26]] in turn.
    - The annex is only an informative summary; the normative text governs. It is also incomplete: fixes made as defect reports are usually not listed.
    - Incompatibilities the compiler can detect show up in the old mode with Clang warnings such as `-Wc++20-compat`; entries that silently change behavior have to be checked by hand.

## What breaks after an upgrade

```cpp
int concept = 0;      // concept is a keyword since C++20
int requires = 0;     // likewise
int char8_t = 0;      // likewise
```

These three lines are perfectly valid in C++17 and fail to compile with `-std=c++20`. The standard records every such cost in Annex C (Compatibility): which subclause changed, what changed, why, and what it does to old code. New features themselves are not listed there unless they take over a name or syntax that old code was using.

Not every incompatibility produces an error. Since C++23, temporaries in the initializer of a range-based `for` live until the loop ends; since C++20, `a == b` may find a reversed `b == a` candidate and select a different function. Changes like these give the same code a different meaning, and the compiler says nothing.

## Structure of the annex

| Subclause | Page | Compares | Entries |
|---|---|---|---|
| C.1 | [[diff.cpp26]] | current draft vs C++26 | 3 |
| C.2 | [[diff.cpp23]] | current draft vs C++23 | 21 |
| C.3 | [[diff.cpp20]] | current draft vs C++20 | 18 |
| C.4 | [[diff.cpp17]] | current draft vs C++17 | 35 |
| C.5 | [[diff.cpp14]] | current draft vs C++14 | 19 |
| C.6 | [[diff.cpp11]] | current draft vs C++11 | 7 |
| C.7 | [[diff.cpp03]] | current draft vs C++03 | 39 |
| C.8 | [[diff.iso]] | C++ vs C | 39 |
| C.9 | [[diff.library]] | C++ standard library vs C standard library | — |

C.1 through C.7 each record only the incompatibilities introduced by their own step; from C.3 on, each general subclause states that its list is "in addition to those listed above". For example, [[diff.cpp20]] covers only the step from C++20 to C++23; C++23 to C++26 is in [[diff.cpp23]], and changes after C++26 are in [[diff.cpp26]]. So to assess the risk of moving C++17 code to the current draft, read all of C.4 down to C.1.

The current draft is the working draft after C++26, which is why there is a [[diff.cpp26]] subclause: it records changes merged after C++26 was published. They will appear in the next standard, and no compiler implements them yet.

C.8 compares C++ with C without naming a particular C version; C.9 only describes the changes C++ made when incorporating the C standard library.

## What an entry looks like

Each entry consists of a few fixed fields:

- **Affected subclause**: the normative subclause affected. That is what you actually need to read when deciding a case; the annex is only a summary.
- **Change**: what changed.
- **Rationale**: why. The Rationale in the annex is often the shortest statement of a rule's design motivation anywhere.
- **Effect on original feature**: the effect on old code, usually one of: previously well-formed code becomes ill-formed, behavior changes, it becomes IFNDR (ill-formed, no diagnostic required), or it becomes UB.

Entries in [[diff.iso]] have two more fields, Difficulty of converting and How widely used; entries between C++ versions do not. The sub-pages on this site add a difficulty of converting based on experience, and compile the annex's examples on Clang 23.1.3 with both the old and the new `-std=` to show whether the change actually appears.

## The annex cannot be relied on alone

Annex C is marked informative and, like [[ub]] and [[ifndr]], creates no rules. Whether code is well-formed under a new standard is decided by the normative text. Two consequences follow.

First, it is incomplete. The annex lists only the incompatibilities the committee considered worth recording. Fixes made as defect reports (DRs) are treated as what the old standard should always have said and usually do not appear here; differences caused by library implementation details certainly do not.

Second, it does not say what compilers do. Many changes are applied in compilers as DRs to all language modes. For example, Clang applies C++17's changes to deduction for `auto x{1}` and to the semantics of inheriting constructors under `-std=c++14` as well. So if switching `-std=` shows no change, that does not mean the annex is wrong; the compiler may have unified the behavior long ago.

## Relation to Annex D

Annex D [[depr]] lists features that are still valid but deprecated. When a feature is removed from Annex D, the removal is recorded as an incompatibility in Annex C. For example, `std::auto_ptr` was deprecated in C++11 and its removal in C++17 is recorded as [[diff.cpp14.depr]] ¶1; the removal of `<codecvt>` and `<strstream>` is recorded in [[diff.cpp23.depr]]. That is why the last subclause of each version's section is usually Annex [depr].

Read both annexes together when upgrading: Annex C tells you what this version breaks, Annex D warns what the next version may break.

## Steps for raising `-std=`

Step one: turn on the compatibility warnings in the old mode. Clang provides `-Wc++11-compat`, `-Wc++14-compat`, `-Wc++17-compat`, `-Wc++20-compat`, `-Wc++23-compat` and `-Wc++2c-compat`, which point out, while still in the old mode, the places that will break in the new one. For the three lines at the top:

```text
$ clang++ -std=c++17 -Wc++20-compat -fsyntax-only compat.cpp
compat.cpp:1:5: warning: 'concept' is a keyword in C++20 [-Wc++20-compat]
compat.cpp:2:5: warning: 'requires' is a keyword in C++20 [-Wc++20-compat]
compat.cpp:3:5: warning: 'char8_t' is a keyword in C++20 [-Wc++20-compat]
```

`-Wdeprecated` reports usages that are on their way to removal (see [[depr]]).

Step two: go through the entries the compiler cannot detect, subclause by subclause. Three kinds of change produce no diagnostic: silent behavior changes (the range-based `for` temporaries and reversed `==` candidates mentioned above); becoming IFNDR (since C++20, default arguments for the same function must be the same in different translation units); and becoming UB (since C++20, a pseudo-destructor call ends the object's lifetime). These can only be found by reading.

Step three: watch for new headers. Every version has a New headers entry: if the project has its own `<version>`, `<format>` or `<print>` and its include path comes before the system paths, the wrong file gets included after the upgrade.

## Highlights per version

| Step | Incompatibilities you are most likely to hit |
|---|---|
| C++26 → draft | declaring an `operator delete` that may throw is ill-formed; designated initializers can designate base class members, causing overload ambiguity; a defaulted assignment cannot be `const`/`&&`-qualified |
| C++23 → C++26 | arithmetic mixing an enumeration with floating-point or another enumeration is ill-formed; comparing two arrays directly is ill-formed; `delete` of an incomplete type is ill-formed; `T...[n]` becomes pack indexing; `to_string(double)` output changes; `<codecvt>`, `<strstream>` and `wstring_convert` removed |
| C++20 → C++23 | range-based `for` extends temporary lifetimes; a movable name in `return x;` becomes an xvalue; a comma inside a subscript changes meaning; `std::format` format strings are checked at compile time |
| C++17 → C++20 | new keywords (`concept`, `requires`, `char8_t`, `co_*`, ...); `u8` literals have type `char8_t`; a class with user-declared constructors is no longer an aggregate; reversed `==` candidates; `throw()` removed |
| C++14 → C++17 | trigraphs removed; `register` removed; `bool` increment removed; exception specifications become part of the type system; dynamic exception specifications removed; `auto_ptr` and others removed |
| C++11 → C++14 | digit separator `'`; `constexpr` member functions no longer implicitly `const` |
| C++03 → C++11 | new keywords; `>>` can close two template argument lists; narrowing conversions; `auto` is no longer a storage class specifier; `export` repurposed |

When writing headers shared between C and C++, read [[diff.iso]] and [[diff.library]].
