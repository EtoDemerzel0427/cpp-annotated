---
title: Where modules came from
summary: Why C++20 modules don't export macros, why there are both a global module fragment and header units, and why module and import are preprocessing directives; these rules come from several competing designs over more than a decade, and from concessions made to build tools.
tags: modules, history, build, preprocessing
updated: 2026-10-19
---

!!! tldr
    - Modules address three problems with `#include`: macros and declarations interfering across headers, declarations of the same entity possibly differing between translation units, and the same header text being parsed again in every translation unit.
    - The longest argument was about macros. C++20's answer is layered: named modules don't export macros, header units do, and `#include` is still possible in the global module fragment.
    - `module` and `import` lines are preprocessing directives, module names cannot come from macros, and the module declaration must be at the start of the file. All these rules exist so that build tools can find dependencies without parsing C++.
    - In a named module, member functions defined inside the class are no longer implicitly inline, and a module interface cannot expose entities with internal linkage. Both rules are there to really separate interface from implementation.
    - Adoption has been slow since modules entered C++20, mainly because of the toolchain: build ordering, binary interfaces that cannot be distributed, and header units that are still experimental.

The rules themselves are in [[module]], [[module.unit]] and [[module.import]], and on the preprocessing side [[cpp.module]] and [[cpp.import]]; how they are used in practice with compilers and CMake is in [[toolchain/modules-in-practice]].

## What was wrong with textual inclusion

`#include` is an interface mechanism inherited from C. The preprocessor pastes the text of a header verbatim into the current translation unit, and the compiler then parses the whole pasted text as source. Stroustrup sums up its problems in three points (HOPL IV §9.3.1):

1. **No isolation.** Code in one header, especially macros, can change the meaning of another header that comes after it, so the order of `#include`s matters.
2. **Inconsistent separate compilation.** Declarations of the same entity in two translation units may differ, and compilers and linkers cannot find all such errors. The many no-diagnostic-required rules in [[basic.def.odr]] come from this.
3. **Slow compilation.** A 70-character Hello World program, once `#include <iostream>` is expanded, has the compiler processing about 420,000 characters (HOPL IV §9.3.1). As more and more templates, inline functions and `constexpr` functions are written in headers, this problem gets worse every year.

The first problem is the easiest to demonstrate. Macros are expanded during preprocessing; they know nothing about scopes, nor which library a piece of code belongs to:

```cpp title="textual.cpp" error
#define value 0      // a macro defined by some header included earlier
// what follows stands for another library's header
struct Config {
    int value;       // error: expands to int 0;
};
```

Modules cut this channel. Macros defined in a module interface unit do not reach importers; [[cpp.import]] only lets imports of header units bring in macros. The two files below compile and run with Clang 23, and `#ifdef LIMIT` in the importer is false:

```cpp title="config.cppm" ok
export module config;
#define LIMIT 10                   // only in effect within this module unit
export constexpr int limit = LIMIT;
```

```cpp title="use.cpp" ok
import config;
#ifdef LIMIT
#error "macros don't cross the module boundary; this doesn't fire"
#endif
int main() { return limit == 10 ? 0 : 1; }
```

## The first attempt: modules written into the language (2005–2012)

The first systematic modules proposal came from Daveed Vandevoorde of EDG and went through six revisions starting in 2005. The fourth, [[N2073]], stated three goals: significantly shorten build times for large projects, better separate interface from implementation, and provide a transition path for existing libraries. These three goals carried through all the way to C++20.

Its syntax was very different from today's. A module definition was wrapped in `export ModuleName { ... }`, declarations were private by default, and a `public:` label exported them:

<div class="compare" markdown="1">

```cpp title="N2073 (not adopted)"
export Lib {
  import std;
public:
  struct S { /* ... */ };
}
// another file
import Lib;
```

```cpp title="C++20"
export module Lib;
import std;
export struct S { /* ... */ };


// another file
import Lib;
```

</div>

N2073 already specified that imports are unaffected by macros and that macros cannot reach inside a module. It discussed exporting macros, but concluded this would force compilers to integrate the preprocessor (N2073 §6.4). That question later became the core of the disagreement. The committee's energy was focused on C++0x at the time, and according to Stroustrup the proposal got very limited support (HOPL IV §9.3.1).

## Two approaches: change the language, or wrap existing headers

### Clang's module maps

In 2012 Clang built a module system for C and Objective-C, starting from the opposite end to Vandevoorde: don't modify headers, but put a map file beside them that describes, outside the language, which headers make up a module:

```text title="module.modulemap (a Clang extension, not C++ syntax)"
module MyLib {
  header "MyLib.h"
  export *
}
```

With `-fmodules` enabled, Clang automatically replaces `#include`s of these headers with module imports. Each header is compiled only once, the result is cached and reused by all translation units, and the importer's macros cannot affect it (Clang documentation, *Modules*). This mechanism had large-scale deployment experience at Google and Apple ([[P0273R1]], [[P0841R0]]). It made the Clang side care especially about two things: existing headers that use macros as interfaces must be able to move smoothly into modules, and build performance must be validated on large code bases.

### Microsoft's design and the Modules TS

From 2014, Gabriel Dos Reis and others at Microsoft proposed a different design. By the revision [[N4465]], its syntax was already close to today's:

```cpp title="N4465 syntax (historical proposal)"
module Alfa;            // the declarations that follow belong to module Alfa
export namespace Alfa {
  struct S3 { /* ... */ };
}
```

Its goals were componentization, isolation from macros, scalable builds and support for semantics-aware tools. N4465 explicitly specified that modules don't export macros, and libraries that use macros as interfaces keep using headers (N4465 §4.11). This design proceeded as a Technical Specification (TS), published in 2018 as ISO/IEC TS 21544, usually called the Modules TS. The TS already took in some of the Clang side's input: the module declaration must be the first declaration in the file, an interface can be split into several partitions, and implementation units are syntactically distinct from interface units (P0273R1).

### The disagreement was about macros

P0273's central request, allowing modules to export macros, did not go into the TS. Both sides had technical reasons:

- Those against exporting macros held that `import X; import Y;` must be equivalent to `import Y; import X;`, and nothing should leak implicitly from one module into another (HOPL IV §9.3.1).
- Those wanting macro export pointed out that Qt, ICU, Google Test and even the standard library itself (`NULL`, `offsetof`, feature-test macros) treat macros as part of their public interface. If modules couldn't express those interfaces, these libraries would become second-class citizens (P0273R1, section "Exported macros").

## ATOM and the merged design

In 2018 Richard Smith of Google proposed another complete design, [[P0947R1]] (*Another take on Modules*, often called ATOM). It followed the TS wherever its priorities did not require otherwise; the main differences were four:

- **Legacy header units.** `import "legacy.h";` compiles an existing header separately into a synthesized module, and importing it has only semantic effects, with no textual pasting. In the TS, a module could only use traditional headers through `#include`, so macro leakage and repeated parsing were still there.
- **The module declaration must be at the start of the file**, so that whether a file is a module unit, and which modules it depends on, can be known without full preprocessing.
- **`module` and `import` are contextual keywords**, so existing code using these words as identifiers is not broken.
- **Exporting macros is decoupled from modules themselves**, making macro export a separate part that can be taken or left.

Smith and Dos Reis merged the two designs into [[P1103R3]] (*Merging Modules*), which went into C++20 in 2019. The merged design gave a layered answer to the macro question, and that is where the several kinds of units in today's [[module]] chapter come from:

| What you write | Do macros reach importers | Main origin | Clause |
|---|---|---|---|
| `export module M;` named module | No | N2073, N4465, Modules TS | [[module.unit]] |
| `module M:part;` module partition | No | P0273, ATOM | [[module.unit]] |
| `#include` after `module;` (global module fragment) | Only within this unit | Modules TS | [[module.global.frag]] |
| `import <h>;` header unit | Yes | ATOM | [[module.import]], [[cpp.import]] |
| `#include` replaced by the implementation with a header unit import | Yes | ATOM, Clang module maps | [[cpp.include]] |

Header unit imports bringing in macros is the response to the P0273 side. The example below requires `<climits>` to be precompiled into a header unit first; it compiles and runs with Clang 23, but every import produces a warning that header units are still experimental:

```cpp title="header_unit.cpp" ok
import <climits>;            // header unit: macros are imported with it
static_assert(INT_MAX > 0);  // INT_MAX is a macro
int main() {}
```

### The global module fragment: using old headers in a module

The global module fragment is another path left over from the TS. Between `module;` and the module declaration, only preprocessing directives may appear, but those directives can `#include` declarations:

```cpp title="foo.cppm" ok
module;
#include <cstddef>    // global module fragment: preprocessing directives only
export module foo;
export std::size_t count() { return 42; }
```

These declarations belong to the global module, not to `foo`. If the module unit doesn't use them, they are discarded, and are neither visible nor reachable to importers (P1103R3 §2.3.1). This rule later developed into the definition of decl-reachable in [[module.global.frag]]; the goal is to keep headers a module includes privately from bloating its interface.

The merged design also left one deliberate gap. For declarations in global module fragments and header units, it only requires them to be reachable when visible; whether they are reachable when only imported indirectly is left unspecified, on the grounds that strict enforcement would be very costly for some implementations (P1103R3 §2.3.3). The few unspecified provisions in [[module.reach]] are traces of that compromise.

## Making way for build tools

In the header era, each `.cpp` file could be compiled independently and in parallel. Modules break this: before a module can be imported, its interface unit must be compiled to get a **binary module interface** (BMI, the compiler's cache format for a module interface), and to know what a file imports you have to read it first. So the build system has to do a dependency scan before compiling and then order the work by the dependency graph. [[P1300R0]] (*Remember the FORTRAN*) used the experience of Fortran 90 modules to warn the committee about this.

Scanning has to be fast, ideally just preprocessing, without parsing C++. This requirement left several rules in the language.

### module and import are preprocessing directives (P1857)

ATOM's contextual keywords were not enough. An earlier patch treated any `import` at the start of a line as a keyword, which would break code like `import -> doImport();`. [[P1857R3]] made `module` and `import` lines real preprocessing directives and specified precisely when they are recognized ([[cpp.module]], [[cpp.import]]). From then on, a scanner only needs to preprocess to know which modules a file provides and requires.

### Module names cannot be macros (P3034)

For the same reason, another rule was added later: the components of a module name cannot come from macro expansion. [[P3034R1]] was accepted in 2024 as a defect report (DR, a fix that applies retroactively to older standards), and Clang 23 implements it:

```cpp title="macro_name.cppm" error
#define NAME foo
export module NAME;   // error: a module name cannot be an object-like macro
```

### Outside the standard

The standard says nothing about files, BMIs or build order; [[lex.phases]] only says that whether the source of a depended-on module unit must be available is implementation-defined. So the remaining problems are outside the standard and are coordinated by SG15, the tooling study group. Its most useful result is [[P1689R5]], a JSON format describing which module a file provides and which modules it needs. It is not part of the standard, but Clang (`clang-scan-deps`), GCC and MSVC can all emit it, and CMake's module support is built on it. CMake has officially supported named modules since 3.28, only with the Ninja and Visual Studio generators; header units are not supported with any generator (Kitware blog; CMake manual *cmake-cxxmodules(7)*).

## Really separating interface from implementation

The second goal of modules is to separate interface from implementation: when only a function body changes, importers should not need to be recompiled. Two fixes before C++20 was finalized put this into effect.

### Member functions defined in the class are no longer implicitly inline (P1779)

In a traditional header, a member function defined inside the class is implicitly inline, and its body is part of the interface. [[P1779R3]] changed this so that only member functions attached to the global module are implicitly inline ([[class.mfct#1]]). After compiling the module below with Clang 23, `area` appears as a strong definition in the module's object file, with a symbol name carrying the module attachment marker, `Square@shapes::area() const`:

<div class="compare" markdown="1">

```cpp title="shape.h (header)"
struct Square {
  int side;
  // implicitly inline: every includer
  // sees the body and may inline it
  int area() const
  { return side * side; }
};
```

```cpp title="shapes.cppm (named module)"
export module shapes;
export struct Square {
  int side;
  // not implicitly inline: the body
  // lives only in the module's object file
  int area() const
  { return side * side; }
};
```

</div>

### Interfaces cannot expose entities with internal linkage (P1815)

If an exported inline function calls a `static` function, importers see something that belongs only to the inside of the module. [[P1815R2]] introduced TU-local entities and the concept of an [[g:exposure]] ([[basic.link#14]]–[[basic.link#16]]), and made such exposures in a module interface unit ill-formed ([[basic.link#17]]):

```cpp title="tu_local.cppm" error
export module tu;
static int helper() { return 1; }             // internal linkage: TU-local
export inline int api() { return helper(); }  // error: exposes helper
```

Clang 23 only gives a `-WTU-local-entity-exposure` warning here, not an error. By [[basic.link#17]] this program is ill-formed, so Clang's behavior meets the requirement of at least one diagnostic, but it still produces a BMI.

## import std (C++23)

C++20 had modules but no standard library in module form; standard library headers could only be imported as header units. A plan to split the library by domain into several modules such as `std.core` and `std.io` ([[P0581R1]]) was deferred. [[P2412R0]] suggested that C++23 first provide one module containing the entire standard library, and gave measurements on MSVC: Hello World took about 0.87 seconds to compile with `#include <iostream>` and about 0.08 seconds with `import std;`. Importing a module much bigger than `<iostream>` was about 10 times faster, because a module only needs to load an already compiled interface once.

The final [[P2465R3]] provides two modules ([[std.modules]]):

- `import std;` imports everything in the standard library in namespace `std`, plus things like `::operator new`;
- `import std.compat;` additionally provides the names of the C headers in the global namespace, such as `::fopen`.

Splitting it into two modules was a chance to shed the historical baggage of whether `<cstdio>` also declares `::printf`, without making migration of existing code too hard (P2465R3, section "Rationale"). The program below, compiled and run after first building a BMI from libc++'s own `std.cppm`, prints `Hello, modules`:

```cpp title="hello.cpp" ok
import std;
int main() { std::println("Hello, {}", "modules"); }
```

## Why adoption has been slow

Modules have been in the standard for more than seven years and are still not the default choice in most projects. The reasons are mainly implementations and toolchains:

- **Compilers.** Microsoft's documentation says modules are feature-complete since Visual Studio 2019 16.10; the minimum versions listed in CMake's documentation are the MSVC toolset 14.34, Clang 16 and GCC 14. The GCC 16 release notes still describe module support as experimental, enabled with `-fmodules`.
- **Header units.** This is the most weakly implemented part of the merged design: Clang 23 gives an experimental warning on every import, and CMake doesn't support them.
- **BMIs can't be distributed.** Each compiler's BMI format is incompatible with the others and tied to the compiler version and compile options. Libraries can only distribute module interface sources for users to build themselves.
- **Ecosystem inertia.** Most libraries still have to support compilers without modules, so they can only offer a module wrapper in addition to their headers.

For practical usage and the current state, see [[toolchain/modules-in-practice]].

## Common misconceptions

!!! pitfall "C++20 modules are the Modules TS"
    They are not. C++20 modules come from P1103's merge of the Modules TS and ATOM, and have changed many times since. Some code valid under the TS is no longer valid in C++20; for example, the global module fragment must now start with `module;` (P1103R3 §3.4). Header units, `module`/`import` as preprocessing directives and TU-local entities are not in the TS either.

!!! pitfall "import <vector>; is equivalent to #include <vector>"
    Not entirely. A header unit is processed as a separate source file, and macros defined before the import cannot affect it ([[module.import]]); `#include` does textual replacement in the current macro environment. Both bring in the macros the header defines. An implementation may replace `#include` of an importable header with a header unit import ([[cpp.include]]), but that is implementation-defined.

!!! pitfall "Using modules means no ODR problems"
    Modules reduce the opportunities for ODR violations: entities declared in a named module are attached to that module ([[module.unit]]), so non-exported functions with the same name defined in two modules are different entities. But declarations in global module fragments and header units still belong to the global module and are still subject to [[basic.def.odr]].

## Timeline

| Year | Event | Reference |
|---|---|---|
| 2005–2012 | Vandevoorde's modules proposal, six revisions | [[N2073]] |
| 2012 | Clang module maps | Clang documentation |
| 2014–2018 | Microsoft's design, which became the Modules TS | [[N4465]] |
| 2016 | Google, drawing on Clang deployment experience, asks for macro export and other changes | [[P0273R1]] |
| 2018 | ATOM | [[P0947R1]] |
| 2019 | The merged design goes into C++20 | [[P1103R3]] |
| 2019–2020 | Dependency scanning, ABI isolation for member functions, TU-local entities | [[P1857R3]], [[P1779R3]], [[P1815R2]] |
| 2022 | `import std` and `import std.compat` go into C++23 | [[P2465R3]] |
| 2023 | CMake 3.28 officially supports named modules | Kitware blog |
| 2024 | Module names cannot be macros (DR) | [[P3034R1]] |

## References

- Bjarne Stroustrup. *Thriving in a Crowded and Changing World: C++ 2006–2020*. HOPL IV (2020), §9.3.1 *Modules*.
- Daveed Vandevoorde. *Modules in C++*, [[N2073]].
- Gabriel Dos Reis, Mark Hall, Gor Nishanov. *A Module System for C++*, [[N4465]].
- Richard Smith, Chandler Carruth, David Jones. *Proposed modules changes from implementation and deployment experience*, [[P0273R1]].
- Richard Smith. *Another take on Modules*, [[P0947R1]]; Richard Smith, Gabriel Dos Reis. *Merging Modules*, [[P1103R3]].
- Michael Spencer. *Modules Dependency Discovery*, [[P1857R3]]; *Module Declarations Shouldn't be Macros*, [[P3034R1]].
- Davis Herring. *ABI isolation for member functions*, [[P1779R3]]; *Translation-unit-local entities*, [[P1815R2]].
- Ben Boeckel, Brad King. *Format for describing dependencies of source files*, [[P1689R5]].
- Bjarne Stroustrup. *Minimal module support for the standard library*, [[P2412R0]]; Stephan T. Lavavej et al. *Standard Library Modules std and std.compat*, [[P2465R3]].
- Clang documentation, *Modules*; Kitware, *import CMake; the Experiment is Over!*; CMake manual *cmake-cxxmodules(7)*; GCC 16 release notes.
