---
title: "A short history of C++ standardization: from Cfront to C++26"
summary: How C++ went from a compiler that translated into C to an ISO standard, why C++0x took more than a decade, what the three-year release train left in today's language, and how a proposal becomes standard wording.
tags: history, standardization, WG21, committee
updated: 2026-10-21
---

!!! tldr
    - C++ was first implemented by Cfront, which translated it into C. Compatibility with C was its earliest and most durable design constraint; name mangling and `extern "C"` both come from it.
    - C++98 and C++11 were both feature-driven: pick the features, then wait until they are ready. Both shipped years later than planned. C++0x was finished only after concepts were pulled out.
    - Since 2012 a new standard ships on schedule every three years, and features that aren't ready wait for the next train. That is why many features arrive in stages over several standards, and code has to tell them apart with `-std=` and feature-test macros.
    - A proposal is reviewed for design by an evolution group, then for wording by a wording group, and finally voted on in plenary. Fixes after publication are tracked as CWG/LWG issues; those resolved as defect reports (DRs) usually apply retroactively to older language modes.
    - Recent debate centers on safety. C++26 adopted erroneous behavior, standard library hardening and contracts; profiles are still under discussion in the C++29 cycle.

Individual features (concepts, move semantics, the memory model, the STL and so on) each have their own history page; this page only places them on the overall timeline. For how to read and cite the standard's text, see [[topics/how-to-read-the-standard|how to read the C++ standard]].

The facts on this page come mainly from Stroustrup's two HOPL papers (cited below as HOPL III and HOPL IV; full titles at the end), the committee's schedule document [[P1000R8]], Herb Sutter's trip reports, and the WG21 papers themselves.

## A decade without a standard (1979–1989)

Stroustrup started designing C with Classes at Bell Labs in 1979. It was renamed C++ in 1984, and the first commercial release, Cfront 1.0, shipped in 1985 (HOPL III §2.5). Cfront did not generate machine code. It translated C++ into C and handed that to whatever C compiler the target platform already had. That let C++ spread quickly to almost every machine with a C compiler.

This implementation strategy shaped many properties of C++. The translated C had to be linked with C linkers, which match symbols by name only. When Cfront 2.0 (1989) added type-safe linkage, it did so by encoding parameter types into symbol names, which made it possible to tell overloaded functions apart without changing existing linkers (*The Design and Evolution of C++*, in the section on type-safe linkage). That is today's **name mangling**; see [[toolchain/name-mangling|the page on name mangling]]. To call to and from C code, `extern "C"` turns the mangling off.

<div class="compare" markdown="1">

```cpp title="C++ source"
void f(int);
void f(double);
extern "C" void g(int);
```

```text title="Symbol names on Linux (Itanium ABI)"
_Z1fi
_Z1fd
g
```

</div>

There was no standard in this period. The de facto definition of the language was Cfront's behavior plus Stroustrup's book. From 1987 on, GNU, Zortech and other compilers appeared, and they needed a common definition.

## The ARM and the committee (1989–1991)

*The Annotated C++ Reference Manual* (Ellis and Stroustrup, known as the ARM), published in 1990, was the most complete definition of the language at the time, with extensive annotations explaining design rationale. It became the starting point for standardization (HOPL III §3).

Standardization began in the United States: ANSI's C++ committee (J16) was formed in 1989 and accepted templates and exceptions in 1990. In 1991 the work moved into an international working group under ISO, WG21, and from then on the two groups met together (HOPL III §3). WG21 still maintains the standard today; its full name is ISO/IEC JTC 1/SC 22/WG 21.

A story circulated among committee members: the Swedish warship Vasa kept gaining decks during construction to carry more guns and statues, and capsized shortly after it was launched (HOPL III §3.3). They used it as a reminder that a language must not lose its balance by taking on more features. That worry resurfaces in every standard over the following thirty years.

## C++98: pick the features, then wait for them

The big features the committee accepted in this period were templates and exceptions (1990), RTTI and namespaces (1993), the STL (1994), and `export` templates (1996) (HOPL III §3.2). Their fates differed widely.

**The STL** was the biggest surprise. It was only proposed in 1994, when the standard was originally supposed to be nearly done. The committee accepted it after cutting about two thirds of it, and even so, turning it into standard wording delayed the standard by more than a year (HOPL III §4.1.2). The full story is on [[history/stl-and-early-library|the STL history page]].

**`export` templates** were a dead end. They allowed template definitions to live in `.cpp` files and be compiled separately, like ordinary functions. But they were extremely hard to implement, and very few compilers ever did. C++11 removed the feature and kept only the keyword; C++20 reused the keyword for modules. Annex C gives the reason as a lack of implementation consensus on what `export` meant in C++03 ([[diff.cpp03.temp]]). Template definitions still have to go in headers today, or wait for modules to solve it ([[history/modules|modules history]]).

The committee also turned down a different direction. In the mid-1990s several Japanese embedded tool vendors proposed Embedded C++, a subset without multiple inheritance, templates, exceptions, RTTI or namespaces. Keeping to its tradition of not endorsing dialects, subsets included, the committee instead wrote a technical report analyzing the performance cost of each feature (HOPL III §6.1). Not splitting the language, and making sure features you don't use cost nothing, remained guiding principles from then on.

C++98 was originally expected around 1994; by 1996, people in the community and even on the committee doubted it would ship at all ([[P1000R8]]). The standard was finally approved in 1998 as ISO/IEC 14882:1998.

## C++03 and TR1: maintenance

After the standard shipped, the committee deliberately went into maintenance mode. HOPL III §6 gives the reasons: members had been at it for nearly ten years; the community's understanding of the new features and implementers' progress lagged far behind; and there were no new ideas that felt urgent.

Most of the work in this period was **defect reports**: fixes for errors and contradictions in the published standard. From 1998 to 2006 the core language and library working groups each handled about 600 of them (HOPL III §6). In 2003 these fixes were collected into C++03, which has almost no new features; value-initialization ([[dcl.init]]) is one of the few exceptions.

The other product of the maintenance period was the library technical report **TR1** (draft [[N1836]]), with smart pointers, `function`, `tuple`, type traits, regular expressions, random numbers, hash tables and more. A **technical report** is not a standard and has no normative force; its purpose is to let implementers implement and users try things first. Almost all of TR1 later went into C++11 ([[history/modern-library|the modern library history page]]). This approach of publishing first, gaining experience and merging later evolved into Technical Specifications (TSes).

## Why C++0x slipped to 2011

In 2003 the committee started considering language extensions again, and the next standard was provisionally called C++0x. The plan in 2006 was a feature freeze in 2007, with C++08 or C++09 as a reasonable expectation (HOPL IV §2.3). It ended up as C++11, hence the joke that the 0x was hexadecimal.

The people involved give three main reasons.

1. **Feature-driven releases.** [[P1000R8]] classifies both C++98 and C++11 as following the model of picking features and shipping when they are ready. Whenever a feature turned out to need more time, the whole standard slipped with it. In both 1994–1996 and 2007–2009, the committee kept believing one or two more meetings would be enough, and each time the delay ran to several years.
2. **Concepts.** The C++0x concepts design went into the working draft in 2008, and the first committee draft [[N2800]] used it extensively. In 2009 the committee decided to remove it entirely (HOPL IV §6.2). Concepts came back only in C++20, with a different design; see [[history/concepts|the concepts history page]].
3. **Size.** The memory model, threads, rvalue references, lambdas and variadic templates were all entirely new work ([[history/threads-and-memory-model|threads and the memory model]], [[history/move-semantics|move semantics]]). In 2006 Stroustrup predicted that the first 21 proposals on his list would make it into C++0x; in the end, 24 of the first 25 made it into C++11 (HOPL IV §2.3).

Progress sped up noticeably after concepts were removed, and the standard was approved in 2011.

C++11 was also the first big language revision since C++98, and it broke a small amount of old code. Each of the two programs below is valid under only one of the standards:

<div class="compare" markdown="1">

```cpp run std=c++98 title="C++98 style" ok
#include <vector>
int main() {
  auto int n = 0;  // auto is a storage-class specifier
  std::vector<std::vector<int> > v;
  return n + (int)v.size();  // > > must be separated
}
```

```cpp run std=c++11 title="C++11 style" ok
#include <vector>
int main() {
  auto n = 0;      // auto means type deduction
  std::vector<std::vector<int>> v;
  return n + (int)v.size();  // >> may be written together
}
```

</div>

The left one is ill-formed in C++11, because `auto` now means type deduction ([[diff.cpp03.dcl.dcl]]). Clang 23 only gives a warning, `'auto' storage class specifier is not permitted in C++11`, which still conforms, because one diagnostic is all the standard requires (see [[intro.compliance]]). The right one is ill-formed in C++98, where `>>` is read as the right-shift operator. [[diff.cpp03.temp]] in Annex C also gives an example in the other direction: `X< Y< 1 >> 2 > >` is `Y<(1>>2)>` in C++98 but an error in C++11.

## The train model: shipping on a schedule (2012 on)

After C++11, convener Herb Sutter proposed switching to a **train model**: trains leave on schedule, and whoever misses one takes the next (HOPL IV §3.2). [[P1000R8]] sets the two release models side by side: you can control which features ship and give up control of the date, or control the date and give up control of the feature set, but not both. The committee chose the latter, with a three-year cycle:

!!! std "P1000R8"
    "We find three years to be a good balance, and two years is the effective minimum in the ISO process."

Stroustrup supported three years rather than five, on the grounds that a longer interval would still attract requests to delay for a feature too important to wait (HOPL IV §3.2). Under the train model, delaying a feature only costs that feature three years, which is no reason to hold up the whole standard. In the C++20 cycle, contracts were pulled out after already being merged into the draft ([[history/contracts|contracts history]]); in the C++26 cycle, trivial relocation was likewise pulled out at the last stage and deferred to C++29 ([[P3920R0]]).

### Technical Specifications: feature branches

Big features that take several cycles were developed in **Technical Specifications** (TSes). [[P1000R8]] compares them to feature branches in version control: implementers can implement them early, users can try them, and once mature they are merged into the trunk, the International Standard. Implementations usually put TS components in the `std::experimental` namespace.

Filesystem, the parallel algorithms, concepts, ranges, coroutines and modules all went through a TS before entering C++17 or C++20 in revised form. The Networking TS and the Transactional Memory TS were never merged. Reflection did not reuse its TS design; it went straight into C++26 as [[P2996R13]]. Recent proposals more often target the International Standard directly.

### What it means for your code: features arrive in stages

A direct consequence of the train model is that a feature often boards in its minimal usable form and is relaxed over the following standards. `constexpr` functions are the textbook example ([[history/constexpr|constexpr history]]): C++11 allowed only a single `return` statement, C++14 allowed loops and local variables, C++20 allowed dynamic allocation, and C++26 allowed still more. The rules for when `return x;` moves implicitly changed four times ([[history/move-semantics|move semantics history]]).

So to decide whether code is valid, you have to ask not just which standard, but which revision of it. Code that must support several versions tells them apart with **feature-test macros**, listed in [[cpp.predefined]] and [[version.syn]]; their values are the year and month the feature was merged into the draft:

```cpp run ok
#include <cstdio>
int main() {
#if __cpp_constexpr >= 202306L
    std::puts("C++26-level constexpr");
#elif __cpp_constexpr >= 201304L
    std::puts("at least C++14-level constexpr");
#else
    std::puts("C++11-level constexpr");
#endif
}
// Clang 23: -std=c++11 prints the third line, c++14 through c++23 the second, c++2c the first
```

Another consequence concerns defect reports. When a problem found after publication is handled as a defect report (DR), it is treated as a fix to the published standard, and compilers usually apply it in all language modes. So a compiler's behavior under `-std=c++17` may not match the text published in 2017, but the corrected rule instead.

## The standards at a glance

Since C++11, the year in each name is the year technical work finished; ISO publication is sometimes a year later, so C++23 is numbered 14882:2024. A public draft is a freely available working draft whose content is nearly identical to the official standard, and it is often cited in its place.

| Common name | ISO number | Public draft | `__cplusplus` | Highlights |
|---|---|---|---|---|
| C++98 | 14882:1998 | | `199711L` | Templates, exceptions, namespaces, RTTI, STL, iostreams |
| C++03 | 14882:2003 | | `199711L` | Defect fixes; value-initialization |
| C++11 | 14882:2011 | [[N3337]] | `201103L` | Move semantics, memory model and threads, lambdas, `auto`, variadic templates, `constexpr`, list-initialization, range-based `for`; TR1 merged |
| C++14 | 14882:2014 | [[N4140]] | `201402L` | Generic lambdas, relaxed `constexpr`, variable templates, return type deduction, `make_unique` |
| C++17 | 14882:2017 | [[N4659]] | `201703L` | Structured bindings, `if constexpr`, CTAD, fold expressions, guaranteed copy elision, `optional`/`variant`/`string_view`, filesystem |
| C++20 | 14882:2020 | [[N4861]] | `202002L` | Concepts, modules, coroutines, ranges, `<=>`, `consteval`, `std::format` |
| C++23 | 14882:2024 | [[N4950]] | `202302L` | Explicit object parameters, `if consteval`, `expected`, `print`, `mdspan`, `import std;` |
| C++26 | (in publication) | | `202603L` in the draft | Static reflection, contracts, `std::execution`, erroneous behavior, library hardening, `#embed` |

The rules for each feature are in the corresponding clauses: [[dcl.struct.bind]], [[stmt.if]], [[over.match.class.deduct]], [[temp.constr]], [[module]], [[dcl.fct.def.coroutine]], [[expr.spaceship]], [[expr.reflect]], [[basic.contract]], [[basic.indet]], [[cpp.embed]] and others; the full list of incompatible changes is in Annex C ([[diff]]).

The value of `__cplusplus` is specified by [[cpp.predefined]]. The current working draft says `202603L`, with a note that future revisions will replace it with a greater value. Before a new standard is officially published, compilers usually use an interim value:

```cpp run ok
#include <cstdio>
int main() { std::printf("%ld\n", __cplusplus); }
// Clang 23 -std=c++2c: 202400
```

Technical work on C++26 finished in March 2026, and it entered ISO's final ballot and publication process. In his report on that meeting, Sutter named reflection, memory-safety improvements that need no code changes (erroneous behavior and library hardening), contracts, and `std::execution` as its four headline features.

## How a proposal becomes standard wording

This site often cites numbers like `P2996R13`, `N4950` and `CWG2551`. All of them come out of the WG21 process.

Proposals are submitted as WG21 papers. Since around 2015, proposal numbers look like `P2996R13`: the number after `P` identifies the proposal and the number after `R` is its revision. Older proposals used `N` numbers, with a new number for each revision; working drafts and minutes still use `N` numbers today, such as [[N5032]]. Links like these on this site go to the papers through wg21.link.

isocpp.org divides the handling of a proposal into three stages:

| Stage | Groups | What they do |
|---|---|---|
| Incubation | Study groups (SGs), such as SG1 concurrency, SG7 reflection, SG23 safety | Develop proposals within a specialized area |
| Design | EWG (language evolution), LEWG (library evolution) | Review the design; decide whether it targets the IS or a TS |
| Wording | CWG (core language), LWG (library) | Review the text sentence by sentence and make it consistent with the rest of the standard |

A proposal that passes wording review is voted on in plenary and, once approved, merged into the working draft by the project editor. The working draft's source is public in the cplusplus/draft repository on GitHub. A major proposal typically takes several meetings, several years and many revisions (HOPL IV §3.2), and many design problems only surface at the wording stage. The committee decides by consensus rather than simple majority; the usual threshold is about 2 to 1 within a subgroup and about 3 to 1 in plenary ([[P1000R8]]).

At the end of each three-year cycle, the feature-frozen draft first goes to the national bodies as a Committee Draft (CD) for ballot and comments. After the committee resolves the comments, it sends out a Draft International Standard (DIS) ballot, and then ISO publishes ([[P1000R8]]).

Problems found after publication are recorded as issues: CWG issues for the core language (such as [[CWG2551]]) and LWG issues for the library. Those resolved as defect reports are the retroactive DRs described in the previous section; this site marks them with {{dr}}.

<details class="fine" markdown="1">
<summary>More detail: the committee's other groups</summary>

ISO requires only three formal officers: the convener, the project editor and the secretary (HOPL IV §3.2). Herb Sutter served as convener for a long time starting in 2002; the revision history of [[P1000R8]] shows that by 2026 Guy Davidson had taken over.

SG17 and SG18 are incubators for EWG and LEWG respectively. The Direction Group was formed in 2017 and only speaks when its members agree unanimously; its recommendations are in [[P2000R5]]. Study groups are created as interest arises and go dormant when their work is done. As of early 2026, SG2 modules, SG8 concepts, SG21 contracts and others are dormant, while SG1 concurrency, SG7 compile-time programming and SG23 safety remain active (the isocpp.org committee page).

</details>

## The safety debate (2022 on)

In November 2022 the US National Security Agency (NSA) published guidance on software memory safety, recommending a move from C/C++ to memory-safe languages where possible. Stroustrup responded in [[P2739R0]]: the guidance lumped C and C++ together and ignored decades of progress; safety is not only memory safety; and he argued for a combination of programming style, support libraries and static analysis to get guaranteed type and resource safety where it is needed, with gradual adoption.

Several directions emerged in the committee after that:

- **Profiles.** [[P2687R0]] and Sutter's [[P3081R2]] propose requesting, through compiler options or annotations, that a set of rules (such as type safety or bounds safety) be enforced: rejecting some unsafe constructs, or implicitly inserting run-time checks on some operations.
- **Safe C++.** [[P3390R0]] proposes a superset of C++: undefined behavior is banned in safe contexts, a borrow checker finds use-after-free and iterator invalidation at compile time, operations that cannot be verified must be marked `unsafe`, and there is a new standard library to go with it. The goal is guarantees similar to Rust's.
- **Improvements that apply without code changes.** Turn some undefined behavior into defined behavior or checkable contract violations.

The main technical criticism of profiles came from [[P3543R0]] and [[P3586R0]]: implicitly inserted run-time checks change the semantics of existing correct programs and should be coordinated with contracts; and enabling a profile through an attribute is a problem, because older toolchains ignore attributes they don't recognize, while a safety feature should not be ignorable. The committee's priority poll leaned towards profiles, but they did not make it into C++26 (Sutter's trip report).

What C++26 actually adopted was the third direction:

- Reading an uninitialized local variable changed from undefined behavior to **erroneous behavior**: the read yields an erroneous value chosen by the implementation, and the implementation may diagnose it ([[P2795R5]]; see [[basic.indet]]);
- Standard library **hardening**: some precondition violations, such as an out-of-bounds subscript, become contract violations, so the program can terminate instead of reading or writing out-of-bounds memory ([[P3471R4]]). Sutter reported that it has been deployed at Google with an average performance cost of about 0.3%;
- Contracts themselves ([[P2900R14]]; see [[history/contracts|contracts history]]).

This line of work continues in the C++29 cycle: an annex listing every case of undefined behavior and IFNDR ([[P3596R3]]) has already been merged into the C++29 draft, and the profiles specification is still being written; it may be merged into the standard or published as a white paper (Sutter's trip report, June 2026).

## Timeline

| Year | Event |
|---|---|
| 1979 | C with Classes begins |
| 1985 | Cfront 1.0; *The C++ Programming Language*, first edition |
| 1989–1991 | Cfront 2.0; ANSI J16 formed; the ARM published; ISO WG21 formed |
| 1994 | STL merged into the draft |
| 1998 | C++98 |
| 2003 | C++03; work on C++0x begins |
| 2007 | TR1 published |
| 2009 | Concepts removed from C++0x |
| 2011 | C++11 |
| 2012 | Switch to the three-year train model; big features go into TSes |
| 2014, 2017, 2020 | C++14, C++17, C++20 |
| 2023 | C++23 technical work complete (published 2024) |
| 2026 | C++26 technical work complete; the C++29 cycle begins |

Following the [[P1000R8]] schedule, technical work on C++29 will finish in early 2029. The main threads already in sight are safety (going through the cases in the UB annex one by one, and profiles), follow-ups to contracts and reflection, a redesign of trivial relocation after its removal from C++26, and asynchronous and networking libraries built on `std::execution`.

## References

- Bjarne Stroustrup. *Evolving a language in and for the real world: C++ 1991–2006*. HOPL III, 2007.
- Bjarne Stroustrup. *Thriving in a Crowded and Changing World: C++ 2006–2020*. HOPL IV, 2020.
- Bjarne Stroustrup. *The Design and Evolution of C++*. Addison-Wesley, 1994.
- Margaret A. Ellis, Bjarne Stroustrup. *The Annotated C++ Reference Manual*. Addison-Wesley, 1990.
- Herb Sutter, Guy Davidson. *(Proposed) C++ IS schedule*. [[P1000R8]].
- isocpp.org: *The Committee*; *Current Status*.
- Herb Sutter's trip reports (Sutter's Mill), 2023–2026 meetings.
- Bjarne Stroustrup. *A call to action: Think seriously about "safety"; then do something sensible about it*. [[P2739R0]], 2022.
- Herb Sutter. *Core safety profiles for C++26*. [[P3081R2]]; Sean Baxter, Christian Mazakas. *Safe C++*. [[P3390R0]].
- Mungo Gill et al. *Response to Core Safety Profiles (P3081)*. [[P3543R0]]; Corentin Jabot. *The Plethora of Problems With Profiles*. [[P3586R0]].
