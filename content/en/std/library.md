---
title: Library introduction
summary: "A guide to Clause 16: the categories the standard library is divided into and the clauses they live in, how library wording is written, and the global constraints this clause places on user programs and on implementations."
updated: 2026-10-19
---

!!! tldr
    - Clause 16 defines no classes or functions. It is the general part for the library clauses 17–33: how library wording is written, what user programs must obey, and what implementations may do.
    - The constraints in this clause go both ways: [[constraints]] constrains programs, and a violation is usually UB; [[conforming]] constrains implementations, and a violation means the implementation doesn't conform.
    - Labels in library function specifications such as *Constraints*, *Mandates* and *Preconditions* each have a definite consequence: not taking part in overload resolution, a compile error, UB on violation ([[description]]).
    - The library is divided into 17 categories, corresponding to Clauses 17–33, plus the deprecated facilities in Annex D.

Clauses 5–15 specify the language itself; the **standard library** starts at Clause 16. The questions Clause 16 answers have nothing to do with any particular library component and apply to all of them:

- May you add declarations to `namespace std`? May you specialize `std::swap`? May you define a macro with the same name as a standard library function? May you take `&std::toupper`?
- Is `v.push_back(std::move(v[0]))` safe? If two threads call `const` member functions on different `std::vector` objects at the same time, is there a data race?
- May an implementation add `noexcept` to `std::vector::operator[]`? May it add default arguments or overloads to standard library functions?

## Sections of this clause

| Section | Subclause | Page on this site | Content |
|---|---|---|---|
| 16.1 | [library.general] | This page | Library categories and their clauses |
| 16.2 | [library.c] | [[library.c]] | How the C standard library is incorporated; semantics of C functions during constant evaluation |
| 16.3 | [description] | [[description]], [[conventions]] | How library wording is written: synopses, the elements of a function specification, exposition-only entities, bitmask types, customization point objects |
| 16.4.1–16.4.3 | [requirements.general], [organization], [using] | [[requirements]] | Headers, the modules `std` and `std.compat`, freestanding implementations, how to include or import, linkage |
| 16.4.4 | [utility.requirements] | [[utility.requirements]] | Named requirements such as *Cpp17EqualityComparable*, swappable, *Cpp17Hash*, *Cpp17Allocator* |
| 16.4.5 | [constraints] | [[constraints]], [[namespace.constraints]], [[reserved.names]] | Constraints on programs: `namespace std`, reserved names, replacement functions, validity of arguments, semantic requirements of concepts |
| 16.4.6 | [conforming] | [[conforming]] | Constraints on implementations: latitude for member and non-member functions, `constexpr`, data races, exceptions, moved-from state |

The most frequently needed page is [[description]], which explains how to read library function specifications. Next come [[namespace.constraints]] and [[constraints]], where user code most easily breaks the rules. [[conforming]] describes the latitude implementations have; you need it to write portable code. The other sections can be consulted as needed.

## Scope of this clause (¶1–¶2)

¶1 This clause describes the contents of the **C++ standard library**, how a well-formed C++ program makes use of the library, and how a conforming implementation provides the entities in the library.

¶2 The contents of the library, and the library requirements on both programs and implementations, are specified in [[requirements]], Clause 17 [[support]] through Clause 33 [[exec]], and Annex D [[depr]].

So when reading a sentence of library wording, first work out whom it constrains. Requirements under [[constraints]] constrain programs; when a program violates them the behavior is usually undefined, and the compiler usually can't diagnose it. Requirements under [[conforming]] constrain implementations; an implementation that violates them doesn't conform.

## Library categories (¶3)

¶3 The detailed specifications of each component are in Clauses 17–33, as shown in Table 23. The right-hand column lists representative headers added by this site; it isn't part of Table 23:

| Clause | Subclause | Category | Representative contents |
|---|---|---|---|
| 17 | [[support]] | Language support library | `<cstddef>`, `<limits>`, `<new>`, `<typeinfo>`, `<exception>`, `<compare>`, `<coroutine>`, `<contracts>`, `<initializer_list>`, `<source_location>` |
| 18 | [[concepts]] | Concepts library | `<concepts>` |
| 19 | [[diagnostics]] | Diagnostics library | `<stdexcept>`, `<system_error>`, `<stacktrace>`, `<debugging>` |
| 20 | [[mem]] | Memory management library | `<memory>`, `<memory_resource>`, `<scoped_allocator>` |
| 21 | [[meta]] | Metaprogramming library | `<type_traits>`, `<ratio>`, `<meta>` (reflection) |
| 22 | [[utilities]] | General utilities library | `<utility>`, `<tuple>`, `<optional>`, `<variant>`, `<any>`, `<expected>`, `<bitset>`, `<functional>`, `<bit>` |
| 23 | [[containers]] | Containers library | `<vector>`, `<map>`, `<flat_map>`, `<hive>`, `<inplace_vector>`, `<span>`, `<mdspan>` and others |
| 24 | [[iterators]] | Iterators library | `<iterator>` |
| 25 | [[ranges]] | Ranges library | `<ranges>`, `<generator>` |
| 26 | [[algorithms]] | Algorithms library | `<algorithm>`, `<numeric>`, `<execution>` (execution policies) |
| 27 | [[strings]] | Strings library | `<string>`, `<string_view>`, `<cstring>` |
| 28 | [[text]] | Text processing library | `<charconv>`, `<format>`, `<locale>`, `<regex>`, `<text_encoding>` |
| 29 | [[numerics]] | Numerics library | `<complex>`, `<random>`, `<valarray>`, `<cmath>`, `<numbers>`, `<linalg>`, `<simd>` |
| 30 | [[time]] | Time library | `<chrono>` |
| 31 | [[input.output]] | Input/output library | `<iostream>`, `<fstream>`, `<print>`, `<filesystem>`, `<spanstream>` and others |
| 32 | [[thread]] | Concurrency support library | `<thread>`, `<atomic>`, `<mutex>`, `<future>`, `<stop_token>`, `<rcu>`, `<hazard_pointer>` and others |
| 33 | [[exec]] | Execution control library | `<execution>` (the senders and receivers of `std::execution`) |

Some headers span clauses. For example, the specialized algorithms in `<memory>` are in Clause 26; the execution policies of `<execution>` are in Clause 26, while the sender/receiver framework is in Clause 33.

¶5–¶18 introduce each category in a sentence or two. ¶5 deserves attention: the **language support library** provides components required by certain parts of the language itself, such as memory allocation ([[expr.new]], [[expr.delete]]) and exception processing ([[except]]). This is the seam between the core language and the library: a `new` expression calls `operator new`, `typeid` produces a `std::type_info`, the result of `<=>` has a type such as `std::strong_ordering`, coroutines need `std::coroutine_handle`, and a contract violation constructs a `std::contracts::contract_violation`. These language rules depend directly on types from the library.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

¶4 The operating system interface described in ISO/IEC/IEEE 9945:2009 is hereinafter called POSIX. The name is used in [[namespace.posix]] and [[value.error.codes]].

¶6–¶18 introduce the remaining categories in turn. Some of the phrasing reflects design intent: ¶9 says the metaprogramming library serves templates and constant evaluation; ¶11 says the containers, iterators, ranges and algorithms libraries provide a subset of the most widely used algorithms and data structures, and the standard never meant to be exhaustive; ¶12 says the strings library supports sequences of `char`, `char8_t`, `char16_t`, `char32_t` and `wchar_t` as well as any other character-like type, which refers to the generic capability of `basic_string<CharT, Traits>`; ¶14 says `valarray` supports n-at-a-time operations, which can be implemented as parallel operations on platforms that support them; ¶16 says iostreams are the primary mechanism for C++ program input and output.

</details>

## Some points on reading library wording

1. **Look at the label first, then the content.** The same sentence "`T` meets the *Cpp17CopyConstructible* requirements" is a condition for overload resolution under *Constraints*, a compile error under *Mandates*, and UB on violation under *Preconditions* ([[description]]).
2. ***Equivalent to* specifies effects, not implementation.** It carries over the full semantics of that code but doesn't constrain how the implementation achieves them ([[structure.specifications#4]]).
3. **When a program violates a library requirement, the consequence is almost always UB.** Giving `std::sort` a comparator that isn't a strict weak ordering, adding overloads to `namespace std`, and passing an invalid range to an algorithm all fall into this category ([[res.on.functions]], [[res.on.arguments]], [[namespace.std]]), and the compiler usually can't diagnose any of them.
4. **Implementations have more latitude than it seems.** Member functions may have extra overloads and default arguments, classes may have extra base classes, headers may include each other, and `noexcept` may be strengthened ([[conforming]]). Portable code can't rely on any of these details.
5. **Much is unspecified.** Whether a name is declared in an inline namespace ([[contents#2]]), whether a class is trivially copyable ([[library.class.props]]), whether you may take a function's address ([[namespace.std#6]]), and the value of an object after it has been moved from ([[lib.types.movedfrom]]) are all left unspecified.

## History

!!! history
    - The C++98 library introduction already established the structure of a general part plus individual clauses, and the method of describing functions with elements such as *Requires*, *Effects*, *Returns*, *Throws* and *Complexity*.
    - C++11 added corresponding general rules for concurrency and move semantics: data race avoidance ([[res.on.data.races]]), moved-from state ([[lib.types.movedfrom]]), and the assumption that rvalue reference arguments are not aliased ([[res.on.arguments]]).
    - C++20 introduced the concepts library and Ranges, replaced *Requires* with *Constraints*, *Mandates* and *Preconditions* ([[P0788R3]]), prohibited specializing standard library function templates, and introduced the notion of addressable functions ([[P0551R3]]).
    - C++23 added the standard library modules `std` and `std.compat` ([[P2465R3]]) and greatly expanded the library subset that freestanding implementations must provide.
    - C++26 added standard library hardening ([[P3471R4]]), contract assertions in the library ([[res.contract.assertions]]), restrictions on reflecting library entities ([[namespace.std#7]]), and specified algorithm function objects as customization point objects ([[P3136R1]]).
