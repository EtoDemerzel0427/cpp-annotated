---
title: Separate translation
summary: "What source files, preprocessing translation units and translation units are, and why a program can be compiled one translation unit at a time and linked at the end."
updated: 2026-10-19
---

!!! tldr
    - A source file, plus everything it `#include`s, minus the lines skipped by conditional inclusion, is called a preprocessing translation unit.
    - After it is preprocessed and converted into tokens, that sequence of tokens is called a translation unit (TU). This is what rules such as the ODR and linkage mean by "each translation unit".
    - TUs are translated separately and finally linked into a program. The compiler sees one TU at a time, so most errors across TUs (such as ODR violations) need no diagnostic.
    - Files in the standard are only a concept: reading source from standard input, unity builds, precompiled headers and LTO all fit within this model.

## Source files, preprocessing translation units, translation units

A project usually has many `.cpp` files, each `#include`s some headers, each is compiled into an object file, and the object files are linked together. The standard uses three nouns for three things in this process.

¶1 The text of the program is kept in **source files**. A source file, together with all the headers and source files included via `#include`, minus the lines skipped by conditional inclusion directives (`#if`, `#ifdef`, etc., [[cpp.cond]]), and as modified by the implementation's handling of pragmas ([[cpp.pragma]]) and conditionally-supported directives ([[cpp.pre]]), is a [[g:preprocessing-translation-unit|preprocessing translation unit]].

A preprocessing translation unit passes through translation phases 4 (preprocessing), 5 (string concatenation) and 6 (conversion into tokens), producing a sequence of tokens. Phase 7 in [[lex.phases]] says this sequence of tokens constitutes a **translation unit** (TU), which is syntactically and semantically analyzed as a whole. When rules such as the ODR ([[basic.def.odr]]) say "in every translation unit", they mean this token-level unit.

| Term | What it is | Defined in |
|---|---|---|
| Source file | The input program text | ¶1 |
| Preprocessing translation unit | Source file + recursively included content − skipped lines | ¶1 |
| Translation unit | The token sequence produced by phase 6 and analyzed by phase 7 | [[lex.phases]] phase 7 |
| Translated translation unit | The output of phase 7 and input of phase 8, usually corresponding to an object file | [[lex.phases]] phase 8 |

The standard also distinguishes headers from source files. `#include <...>` looks for a header, which need not be a file at all; `<vector>`, for example, could in principle be built into the compiler. `#include "..."` looks for a source file first and, if that fails, retries as if it were `<...>` ([[cpp.include]]). How header names map to headers or files is implementation-defined ([[lex.header]]).

## Separate translation and linking

Note 1 says that a program need not all be translated at the same time: the TUs can be translated separately and later linked into an executable program ([[basic.link]]).

```cpp title="a.cpp"
int counter = 0;         // external linkage: the extern declaration in b.cpp refers to this
static int helper = 1;   // internal linkage: visible only in a.cpp
```

```cpp title="b.cpp"
extern int counter;      // matched with the definition in a.cpp in phase 8 (linking)
static int helper = 2;   // a different entity from helper in a.cpp
int main() { return counter + helper - 2; }
```

Compiled separately and then linked, these two files form a well-formed program that returns 0. Many core rules follow from separate translation:

- If the definitions of the same inline function differ between two TUs, the ODR is violated, but no diagnostic is required ({{ifndr}}), because the compiler sees only one TU at a time.
- `static` and unnamed namespaces give names internal linkage, so that same-named entities in different TUs do not interfere.
- Template definitions are usually written in headers, because instantiation takes place in the TU that uses them.
- The order of dynamic initialization of non-local variables in different TUs is indeterminate ([[basic.start.dynamic]]), because there is no ordering between TUs.

TU boundaries carry meaning and cannot be changed at will. Merge the two files above into one TU (as a unity build does, see below) and the two `static int helper` become a redefinition in the same scope, making the program ill-formed.

## Files are only a concept

Note 2 says that source files, translation units and translated translation units need not be stored as files, nor need there be a one-to-one correspondence between them and any external representation; the description is conceptual only. So all of the following are compatible with the standard:

- reading source from standard input, for example `clang++ -x c++ -`;
- a unity build: one `.cpp` that `#include`s several `.cpp` files in turn, combining them into one TU;
- precompiled headers (PCH) and the compiled output of modules (BMI);
- link-time optimization (LTO): translated TUs are kept as an intermediate representation, and machine code is generated only at link time.

The convention of the mainstream toolchains is that one `-c` invocation processes one `.cpp` and outputs one `.o`, that is, one source file corresponds to one TU and one object file. The output of `-E` is what the preprocessing translation unit looks like after phase 4.

Since C++20 a TU can be a module unit ([[module.unit]]). It is still translated separately; the difference is that besides communicating through names with linkage, a TU can import the interface of another TU ([[module.import]]). Whether the source of an imported unit must be available is implementation-defined ([[lex.phases]] phase 7); in practice compilers read a precompiled interface file.

## Questions

!!! question "Question"
    Each of the two files below is valid C++ on its own. Linking them as two TUs into a program, compared with a unity build (a third file that does `#include "x.cpp"` and then `#include "y.cpp"`): what is the difference?

    ```cpp
    // x.cpp
    namespace { int f() { return 1; } }
    int gx() { return f(); }
    // y.cpp
    namespace { int f() { return 2; } }
    int gy() { return f(); }
    ```

<details markdown="1">
<summary>Answer</summary>

As two TUs, each TU has its own unnamed namespace, the two `f` are different entities, and the program is well-formed.

In a unity build, both files belong to the same TU, and the unnamed namespaces in one TU are the same namespace ([[namespace.unnamed]]). So `f` is defined twice in the same TU, which violates [[basic.def.odr]]; the program is ill-formed and the compiler must diagnose it.
</details>
