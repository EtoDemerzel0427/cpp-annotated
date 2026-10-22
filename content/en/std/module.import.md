---
title: Import declarations
summary: "Where import can appear, which translation units importing a module, a partition or a header unit actually imports, re-exporting and transitive imports, and why imports can't form a cycle."
updated: 2026-10-19
---

!!! tldr
    - `import M;` imports all of module M's interface units: the exported names become visible and all declarations in them become reachable. `import` doesn't paste text and doesn't bring in macros.
    - Module M doing `import Q;` itself doesn't let M's importers see Q's names; `export import Q;` does. Between units of the same module, ordinary imports are transitive too.
    - `import <vector>;` or `import "x.h";` imports a header unit: the header is translated separately once, all its declarations are implicitly exported, and the macros it defines come along too.
    - In a module unit, imports must come before all other declarations; imports can't form a cycle.
    - Since C++23 there are standard library modules: `import std;` provides the names of the whole standard library, but not macros such as `assert`.

## import vs #include

```cpp title="Q.cppm"
export module Q;
export int q() { return 4; }
```

```cpp title="M.cppm"
export module M;
import Q;                 // non-exported import
export int m();
```

```cpp title="M.cpp" ok
module M;                 // implicitly imports M, and thus indirectly Q
int m() { return q(); }   // OK: q is visible
```

```cpp title="user.cpp" error
import M;                 // imports only M
int main() { return m(); }
int z = q();              // error: q isn't visible
```

`#include` pastes the text of a header in, and the includer sees everything the header includes. `import` is different: it makes the declarations in another set of already-translated TUs visible or reachable to the current TU, and only their exported names are visible. `user.cpp` imports M, and M imports Q, but `user.cpp` can't see `q`. Clang 23 reports "declaration of 'q' must be imported from module 'Q' before it is required".

Which TUs an import declaration **imports** is the subject of [module.import]. Name lookup ([[basic.lookup#2]]) and reachability ([[module.reach]]) are both based on this set.

An import declaration has three forms:

```text
module-import-declaration:
    import-keyword module-name attribute-specifier-seq(opt) ;
    import-keyword module-partition attribute-specifier-seq(opt) ;
    import-keyword header-name attribute-specifier-seq(opt) ;
```

They import a named module (`import M;`), a partition of this module (`import :P;`) and a header unit (`import <vector>;`, `import "config.h";`) respectively.

Like `module`, `import` isn't a keyword. When the preprocessor recognizes an `import` directive at the start of a line, it replaces it with the special token *import-keyword* ([[cpp.import#3]]), so an import declaration must be at the start of a line and can't be produced by macro expansion. This design comes from [[P1857R3]]: a build system only needs to preprocess a file to find all its module dependencies.

## Where imports go (¶1)

¶1 An import declaration must inhabit the global namespace scope. In a module unit, all import declarations (including `export import`) must appear before all other declarations; imports in a private module fragment must likewise come first in that fragment.

<div class="compare" markdown="1">

```cpp title="late.cppm" error
export module L;
int x;
import Q;
// error: imports in a module unit
// must precede other declarations
```

```cpp title="late.cpp" ok
int x;
import Q;
// OK: non-module TUs aren't subject to this
int main() { return q() + x; }
```

</div>

With imports gathered at the start, a build system scanning dependencies only needs to look at the head of the file, and the compiler can load all dependencies before processing any declaration, so a name can't mean different things before and after an import. The rule constrains only module units: ordinary TUs often begin with a run of `#include`s, and forcing an order would make migration very hard.

```cpp title="ns.cpp" error
namespace N {
  import Q;               // error: an import declaration must inhabit the global namespace scope
}
```

Clang 23 reports "imports must immediately follow the module declaration" for `late.cppm` and "import declaration can only appear at the top level" for `ns.cpp`.

An import declaration may end with attributes, which appertain to that import declaration.

## Which translation units are imported (¶2–¶4)

¶2 An import declaration imports a set of TUs, specified by the paragraphs below. Note 1 explains the two effects of importing: exported namespace-scope declarations in the imported TUs can be found by name lookup in the importer; all declarations in the imported TUs are reachable from the importer after the import declaration.

¶3 `import M;` imports all module interface units of M, that is, the primary interface unit and all interface partitions.

¶4 `import :P;` can appear only in a module unit of some module M, after the module declaration, and imports M's partition `M:P`. A partition name is always relative to the current module, and there's no syntax to import another module's partition, so partitions aren't visible outside the module.

## Transitive imports (¶7)

¶7 When a TU T is imported, all TUs imported by exported import declarations (`export import`) in T are imported too; these TUs are said to be **exported by T**.

In addition, when a unit of module M imports another unit U of M, it also imports all TUs imported by ordinary import declarations in U's purview. These rules apply recursively.

| Importer | Imported T contains `import X;` | Imported T contains `export import X;` |
|---|---|---|
| A TU outside the module | X isn't imported (X's interface units are still reachable; see [[module.reach#1]]) | X is imported |
| Another unit of the same module | X is imported | X is imported |

In the opening example, `M.cpp` implicitly imports M's primary interface unit ([[module.unit#8]]) and, by the second rule, also imports Q, so it can call `q()`. The units of one module are a single whole split across several files, so what the primary interface imports should be usable by the implementation units too. `user.cpp`, outside the module, imports only M.

Re-exporting makes one module's interface part of another module's interface:

```cpp title="R.cppm"
export module R;
export import Q;          // whoever imports R also imports Q
```

```cpp title="user2.cpp" ok
import R;
int main() { return q(); }   // OK: Q is exported by R
```

Dots in module names have no semantics ([[module.unit]]); `import lib;` doesn't import `lib.core`. To have `import lib;` bring in all submodules, write an umbrella module: `export module lib; export import lib.core; export import lib.io;`.

Note 6 stresses that such indirect imports bring no macros. An imported TU is a sequence of tokens from translation phase 7 ([[lex.phases]]), and macros were already dealt with in phase 4. Macros can only be obtained by directly importing a header unit.

## Header units (¶5–¶6)

¶5 `import "h.h";` imports a synthesized [[g:header-unit|header unit]]: the TU obtained by applying translation phases 1 through 7 to `h.h` on its own. The file shall not contain a module declaration.

Note 2 describes the nature of header units: a header unit is a separate TU with its own set of macro definitions; all its declarations are implicitly exported ([[module.interface#2]]) and attached to the global module ([[module.unit#7]]). Note 4 points out that the preprocessor also recognizes such imports, and macros defined at the end of phase 4 in the header unit become visible to the importer ([[cpp.import]]). No other import brings macros.

```cpp title="cfg.h (importable header)"
#pragma once
#define CFG_LEVEL 3
static int helper() { return CFG_LEVEL; }   // internal linkage: allowed by ¶6
inline int twice(int x) { return 2 * x; }
```

```cpp title="use.cpp" ok
import "cfg.h";           // the macro CFG_LEVEL is visible too
int main() { return twice(CFG_LEVEL) + helper(); }   // 2*3 + 3 = 9
```

```cpp title="N.cppm"
export module N;
import "cfg.h";
export int fromN() { return twice(1); }
```

```cpp title="use2.cpp" ok
import N;                 // named module: no macros, even though N imports cfg.h
#ifdef CFG_LEVEL
#error "never fires"
#endif
int main() { return fromN(); }
```

The three ways of bringing code in compared:

| | `#include "h.h"` | `import "h.h";` | `import m;` |
|---|---|---|---|
| How it's translated | text pasted into the current TU | separate TU, translated once | separate TU, translated once |
| Includer's macros affect what's brought in | yes | no | no |
| Macros of what's brought in come out | yes | yes | no |
| Declarations attached to | global module | global module | module m |
| Which names are visible | all | all (implicitly exported) | only exported ones |

### Which headers can be imported

¶5 What can be imported this way must be an **importable header**. The set of importable headers is implementation-defined, but must include all importable C++ library headers, that is, `<vector>`, `<string>` and the rest in Table 24 of [[headers#4]]. Headers for C library facilities such as `<cstdio>` and `<cassert>` aren't in Table 24; whether they are importable is up to the implementation.

If an `#include` names an importable header, the implementation may replace that `#include` with the corresponding `import`; whether it does so is implementation-defined ([[cpp.include#10]]). A header unit has its own macro environment, so this replacement can change the meaning of a program: a configuration macro defined before `#include <vector>` no longer affects `<vector>` after replacement. Importable headers should therefore not depend on the includer's macro state.

### Is the same header the same header unit?

¶5 Given two declarations that import headers:

- ¶5.1 if they name different header files or source files, they import different header units;
- ¶5.2 otherwise, if they are in the same TU, they import the same header unit;
- ¶5.3 otherwise, it is unspecified whether they import the same header unit.

¶5.3 leaves the choice to the implementation: it may build separate header units of the same header for different compilation configurations (different command-line macros, different language modes), or share one across the whole project. Note 3 points out the consequence: entities with internal linkage in an importable header (`static` functions, namespace-scope `const` variables) may exist in multiple copies, just as each TU has its own copy with `#include`.

### What a header unit may contain (¶6)

¶6 A header unit may declare names with internal linkage, even though all its declarations are implicitly exported ([[module.interface#3]] makes an exception for this). Note 5 reminds us that definitions appearing in multiple TUs (inline functions, for example) generally can't refer to such names ([[basic.def.odr]]).

A header unit shall not contain a definition of a non-inline function or variable with external linkage. Because of ¶5.3, different importers may get the same header unit or different ones, so such a definition might be linked into the program several times, or there might be no definite object file to hold it. What can go into a header unit is exactly what can go into an ordinary header without violating the ODR. Clang 23 reports "non-inline external definitions are not permitted in C++ header units" for `int bad() { return 0; }`.

!!! impl "Implementation status of header units"
    In our tests Clang 23 builds a user header unit with `-fmodule-header=user -xc++-header cfg.h -o cfg.pcm` (system headers use `-fmodule-header=system -xc++-system-header vector`) and imports it with `-fmodule-file=cfg.pcm`. The two examples above return 9 and 2, but every import warns "the implementation of header units is in an experimental phase". Header units require the build system to decide which set of macros and options to compile each header with, which makes them the weakest-supported part across toolchains; CMake 3.29 in our tests supports only named modules, not header units. See [[toolchain/modules-in-practice]].

## Implementation partitions can't be exported (¶8)

¶8 A module implementation unit shall not be exported. The only implementation units that can be imported are implementation partitions, so this rule forbids `export import :Part;` where `:Part` is an implementation partition. An implementation partition can't contain `export` declarations, so exporting it would be meaningless and would blur the boundary of the interface.

```cpp title="M-Part.cppm"
module M:Part;
```

```cpp title="M.cppm" error
export module M;
export import :Part;      // error: :Part is an implementation unit
```

Clang 23 reports "module partition implementations cannot be exported".

## An implementation unit can't import its own module (¶9)

¶9 An implementation unit of module M that isn't a partition shall not import M. It already implicitly imports M ([[module.unit#8]]), so writing it again would be redundant.

```cpp title="M.cpp" error
module M;
import M;                 // error: can't import M in its own implementation unit
```

A partition can explicitly import its own module, as long as no cycle forms; see `module B:X2; import B;` in Example 2 of [[module.unit#8]].

## Imports can't form a cycle (¶10)

¶10 A TU has an [[g:interface-dependency|interface dependency]] on a TU U if it contains a declaration (possibly a module declaration, since `module M;` implicitly imports the primary interface) that imports U, or if it has an interface dependency on a TU that has an interface dependency on U. A TU shall not have an interface dependency on itself.

```cpp title="M1.cppm"
export module M1;
import M2;
```

```cpp title="M2.cppm"
export module M2;
import M3;
```

```cpp title="M3.cppm" error
export module M3;
import M1;                // error: cyclic interface dependency M3 → M1 → M2 → M3
```

Importing a module requires it to have been translated already (in implementations, its BMI, the interface information the compiler caches, is needed). With a cycle, there's no valid compilation order. `#include` cycles can be cut by include guards, but there's no notion of a half-translated module.

This rule is diagnosable, but a compiler translating a single TU can't see the whole cycle. In practice the build system discovers it during dependency scanning; compiling `M3.cppm` directly in our tests, Clang reports "module 'M1' not found", because M1's BMI doesn't exist yet. Common ways to break a cycle are to move the mutually dependent parts into partitions of the same module, or to extract them into a third module.

The notion of interface dependency is also used in [[module.reach#1]] (necessarily reachable TUs) and [[lex.phases]] (whether the source of depended-on units must be available is implementation-defined).

## Standard library modules: `import std;`

Since C++23 the standard library provides two named modules ([[std.modules]], [[P2465R3]]):

- `std` exports the declarations in `namespace std` provided by the C++ library headers of Table 24 and the C library facility headers of Table 25 (`<cstdio>` and so on), plus `operator new` and `operator delete` in the global namespace.
- `std.compat` exports everything in `std`, plus the global-namespace versions of the C library functions (`::printf`, `::size_t`, etc.).

```cpp title="hello.cpp" ok
import std;
int main() {
  std::vector<int> v{3, 1, 2};
  std::ranges::sort(v);
  std::println("{}", v);              // [1, 2, 3]
#ifdef assert
  std::println("assert is a macro");
#else
  std::println("no assert macro");    // this line is what's actually printed
#endif
}
```

Like every named module, `import std;` provides no macros: `assert`, `errno`, `offsetof` and `va_arg` still need `#include` of the corresponding header ([[std.modules#6]] note 2).

The standard doesn't specify which module the standard library's declarations are attached to ([[std.modules#4]]), but requires that mixing `#include <vector>` with `import std;` causes no attachment conflict: `std::vector` is the same entity whichever route it comes through ([[std.modules#5]]). The common approach is to attach standard library entities to the global module: libc++'s `std.cppm` includes all headers in the global module fragment and then exports the names with `export namespace std { using std::vector; ... }`.

!!! impl "Building `import std;` in our tests"
    Homebrew's LLVM provides the source of the `std` module at `share/libc++/v1/std.cppm`:
    ```bash
    clang++ -std=c++2c -Wno-reserved-module-identifier --precompile \
        /opt/homebrew/opt/llvm/share/libc++/v1/std.cppm -o std.pcm
    clang++ -std=c++2c -fmodule-file=std=std.pcm hello.cpp std.pcm -o hello
    ```
    The resulting `std.pcm` is about 37 MB. In our tests at `-O0`, compiling just `hello.cpp` takes about 0.33 s, while an equivalent program using `#include <vector>`, `<algorithm>` and `<print>` takes about 0.60 s (three runs each). For detailed steps, see [[toolchain/modules-in-practice]].

## History

!!! history
    - The three forms of import, header units, `export import` and interface dependencies come from C++20's [[P1103R3]].
    - [[P1857R3]] made lines beginning with `import`, `module` and `export` preprocessing directives, so dependency scanning only needs preprocessing. That's also why `import` must be at the start of a line and can't be generated by macros.
    - C++20 required all C++ library headers to be importable but didn't provide `import std;`. [[P2465R3]] added `std` and `std.compat` in C++23. For more background, see [[history/modules]].

## Common misconceptions

!!! pitfall "`import M;` brings in everything M imports"
    Only `export import` passes names on. An ordinary `import <string>;` in M doesn't let M's importers see the name `std::string`. The definition of `std::string` is still reachable, so a function exported by M that returns `std::string` works fine, and `.size()` can be called on its return value, but importers can't write `std::string s;` themselves.

!!! pitfall "`import std;` provides `assert`"
    It doesn't. `assert` is a macro and still needs `#include <cassert>`. The standard explicitly supports mixing `#include` with `import std;` ([[std.modules#4]] note 1).

!!! pitfall "Importing a header containing ordinary function definitions as a header unit"
    This violates ¶6. Such a header shouldn't be listed as importable.

## Questions

!!! question "Question 1"
    Module A's interface unit contains `import B;` (not exported), module B exports `struct S { int x; };` and `S make();`, and A exports `export S getS() { return make(); }`. In a TU that imports A, which of these lines are valid?

    ```cpp
    import A;
    auto s = getS();     // (1)
    int n = s.x;         // (2)
    S t;                 // (3)
    decltype(getS()) u;  // (4)
    ```

<details markdown="1">
<summary>Answer</summary>

- (1) Valid: `getS` is exported by A.
- (2) Valid: the current TU has an interface dependency on B's interface unit, which is therefore necessarily reachable from it ([[module.reach#1]]), so `S` is a complete type and the member `x` can be found by class member lookup.
- (3) Ill-formed: the name `S` isn't visible, since the import in A isn't exported (¶7). Clang 23 reports "declaration of 'S' must be imported from module 'B' before it is required".
- (4) Valid: the name `S` isn't written, and the definition of the type `decltype` yields is reachable.
</details>

!!! question "Question 2"
    Why doesn't the second rule of ¶7 (ordinary imports are transitive between units of the same module) create new import cycles?

<details markdown="1">
<summary>Answer</summary>

The rule only enlarges the set of imported TUs, and the extra ones are TUs that U already imports. Since U can be translated, those TUs don't depend on U. When importer T imports U, by the transitive definition of ¶10 T already has an interface dependency on those TUs through U. The second rule adds no new dependency edges; it only makes names from existing dependencies visible, so no new cycle can arise.
</details>
