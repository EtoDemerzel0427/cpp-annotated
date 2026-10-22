---
title: Modules
summary: "An overview of Chapter 10: which problems of #include C++20 modules solve, and how module units, partitions, the global module, attachment, exporting, visibility and reachability fit together."
updated: 2026-10-19
---

!!! tldr
    - `#include` is text pasting, which brings three problems: macros leak in both directions between headers and their users, the same header is parsed again by every source file, and the names of all libraries are crowded together. Modules answer each of the three.
    - Importing a named module brings in no macros, and the importer's macros can't affect the module; only a header unit, `import "x.h";`, brings in macros.
    - Every declaration is attached to a module. Two non-exported functions with the same name in two modules are two different functions and don't clash at link time.
    - Exporting decides whether a name can be found by importers (visible); reachability decides whether semantic information such as definitions can be used. A type that isn't exported can still be used through an exported alias.
    - A module isn't a namespace: `export module foo;` doesn't create `foo::`.

## Macros no longer cross the boundary

```cpp title="counter.cppm"
module;
#include <cstddef>
export module counter;
#define COUNTER_MAX 100            // effective only in this translation unit
export class Counter {
  std::size_t n = 0;
public:
  bool tick() { return ++n < COUNTER_MAX; }
  std::size_t value() const { return n; }
};
```

```cpp title="main.cpp" ok
#define value oops                 // doesn't affect value in the counter module
import counter;
#undef value
#ifdef COUNTER_MAX
#  error "macro leaked"            // never fires: named modules don't export macros
#endif
int main() {
  Counter c;
  while (c.tick()) {}
  return c.value() == 100 ? 0 : 1;
}
```

In our tests Clang 23 first precompiles `counter.cppm` into a module file and then compiles `main.cpp`; the program returns 0 normally. If `counter` were a header included with `#include`, the result would be completely different: the `#define value oops` in `main.cpp` would rename `value()` in the header, and the header's `COUNTER_MAX` would leak into `main.cpp`.

`#include` is text pasting: the preprocessor inserts the contents of the header verbatim at the current position, and the compiler then treats the result as one big source file. The meaning of a header therefore depends on which macros were defined before it was included, and on the order of inclusion. The same header in two translation units (a source file compiled separately, together with the headers it includes) can expand to different code because of different macros; this is the most common source of ODR violations (the definitions of the same entity must be the same everywhere, [[basic.def.odr#16]]).

Modules cut off this channel. A module unit is translated separately, and importers get the result of its translation, not its source text. Per [[module.import#5]] note 4 and [[module.import#7]] note 6, importing a named module makes no macros available. Where macros are needed, such as configuration switches and `assert`, you can still use `#include`, or import a header unit, `import "config.h";`, which is the only kind of import that brings in macros ([[cpp.import]]).

## Each module is translated once

For a source file that includes `<vector>`, `<string>` and `<algorithm>`, the compiler has to reparse tens of thousands of lines of standard library code; a project with a thousand source files repeats that a thousand times. Precompiled headers ease the problem, but they require all source files to share the same opening section, and semantically they are still textual inclusion.

A module interface unit is translated only once, producing a binary module interface file (BMI; Clang calls it `.pcm`, GCC `.gcm`, MSVC `.ifc`), and importers read the serialized declarations from it directly. The standard itself doesn't mention BMIs; it only specifies which declarations an import makes findable and usable. But the semantics of modules, unaffected by the importer's macros and independent of import order, were designed precisely to make such an implementation possible. For actual build setups and their effect, see [[toolchain/modules-in-practice]].

## Names belong to modules

```cpp title="M.cppm"
export module M;
int helper() { return 1; }          // not exported
export int f() { return helper(); }
```

In the header model, if two libraries each define an `int helper();`, at link time either the symbols clash or the linker quietly picks one, and the program violates the ODR with no diagnostic required.

Modules introduce **[[g:attached|attachment]]**: every declaration is attached to some module ([[module.unit#7]]), and entities with the same name attached to different modules are different entities ([[basic.link#8]] item 8.3). The `helper` above isn't exported, so it has **[[g:module-linkage|module linkage]]**: only other units of module `M` can refer to it by this name.

Clang and GCC encode the module name into the symbol names of entities attached to a named module. In our tests, compiling the module above with Clang 23 gives `helper` the symbol `_ZW1M6helperv` and the exported `f` the symbol `_ZW1M1fv`, where `W1M` stands for module `M`. So to the linker, a `helper` in another module is a different symbol.

!!! note "What modules are not"
    - A module isn't a namespace. `export module foo;` doesn't create a `foo::` scope; names stay in whatever namespace you wrote them in. Modules govern visibility and ownership, namespaces govern the scope of names, and the two are unrelated.
    - A module isn't access control. Importers can't find a non-exported declaration by name, but its definition can still have an effect, for example by being used through an exported alias or a function's return type (see reachability below).
    - Modules don't prescribe file names, directory layout or build method. Extensions such as `.cppm` and `.ixx` are toolchain conventions.

## Four kinds of module unit

```cpp title="geo.cppm"
export module geo;         // primary module interface unit
export import :shapes;     // an interface partition must be exported by the primary interface unit
export double area_sum();
```

```cpp title="geo-shapes.cppm"
export module geo:shapes;  // interface partition
export struct Circle { double r; };
```

```cpp title="geo-detail.cppm"
module geo:detail;         // implementation partition
constexpr double pi = 3.14159265358979;
```

```cpp title="geo.cpp"
module geo;                // implementation unit, implicitly imports geo
import :detail;            // implementation partitions are imported only within the module
double area_sum() { return pi * Circle{1}.r * Circle{1}.r; }
```

A translation unit that begins with a **module declaration** such as `export module M;` or `module M;` (optionally preceded by a global module fragment) is a [[g:module-unit|module unit]]; otherwise it's an ordinary translation unit. Module units are classified along two dimensions ([[module.unit]]):

| | No partition name | With partition name `:P` |
|---|---|---|
| Interface unit `export module …` | primary module interface unit, exactly one per module | interface partition, must be `export import`ed directly or indirectly by the primary interface unit |
| Implementation unit `module …` | implementation unit, implicitly imports the primary interface unit, can't be imported | implementation partition, can be imported by other units of the module, not exposed outside |

All the module units with the same name together make up a [[g:named-module|named module]]. What belongs to no named module makes up the [[g:global-module|global module]]: all ordinary translation units, plus the global module fragment at the start of each module unit. The global module has no name and no interface unit. Header units are also ordinary translation units, and their declarations are attached to the global module.

A declaration is generally attached to the module it appears in. A few kinds are exceptions and are attached to the global module: namespaces with external linkage, type aliases, namespace aliases, and declarations inside `extern "C"` and `extern "C++"` blocks ([[module.unit#7]]). So a module can use an `extern "C++"` block to declare entities shared with legacy code.

## Exporting, visibility and reachability

```cpp title="A.cppm"
export module A;
struct X {};
export using Y = X;
```

```cpp title="use.cpp" error
import A;
Y y;   // OK: the definition of X is reachable
X x;   // error: X isn't visible
```

This is the example from [[module.reach#6]]; in our tests Clang 23 reports `unknown type name 'X'` for line 3. It shows two different things in modules:

- **Visible**: whether name lookup can find the declaration. The standard's formal phrasing is that the declaration precedes this program point ([[basic.lookup#2]]). To an importer, only exported declarations are visible. `X` isn't exported, so writing the name `X` finds nothing.
- **Reachable**: whether the semantic information a declaration brings, such as a class definition or default arguments, can take effect at this point ([[module.reach]]). In an imported translation unit, non-exported declarations are generally reachable too. `Y` is an alias for `X`; declaring a variable with `Y` needs the complete definition of `X`, and that definition is reachable, so `Y y;` is valid.

**Exporting** ([[module.interface]]) means marking a declaration with `export` so that importers can find it. An exported name never has module linkage. **Importing** ([[module.import]]) decides which translation units the current translation unit imports, and `export import` passes the import relationship on downstream.

## Two special fragments

```cpp title="hello.cppm"
module;                    // the global module fragment begins
#include <cstdio>          // only preprocessing directives may appear here
export module hello;       // from here on is the purview of module hello
export void greet();
module :private;           // private module fragment
void greet() { std::puts("hi"); }
```

- **[[g:global-module-fragment|Global module fragment]]** ([[module.global.frag]]): the part between `module;` and the module declaration, used to `#include` headers that haven't been modularized yet. Its declarations are attached to the global module, and those the module doesn't use are discarded.
- **[[g:private-module-fragment|Private module fragment]]** ([[module.private.frag]]): the part after `module :private;` isn't reachable from importers. It can appear only in a primary interface unit, and the module can then have only that one unit. It lets a single-file module put implementation and interface together, while ensuring that the implementation part can't affect the behavior of other translation units.

## What each subclause covers

| Subclause | Clause | Contents |
|---|---|---|
| 10.1 | [[module.unit]] | kinds of module unit, reserved module names, the purview of a module, the global module, which module a declaration is attached to |
| 10.2 | [[module.interface]] | where `export` can appear, which declarations can be exported, exporting and linkage |
| 10.3 | [[module.import]] | which translation units `import` imports, partitions and header units, transitivity of `export import`, no cyclic imports |
| 10.4 | [[module.global.frag]] | the global module fragment, which declarations are discarded |
| 10.5 | [[module.private.frag]] | the private module fragment |
| 10.6 | [[module.context]] | where names are looked up when a template is instantiated across modules |
| 10.7 | [[module.reach]] | which translation units and declarations are reachable, reachability vs visibility |

Many module rules are written outside Chapter 10:

| Topic | Location |
|---|---|
| Module linkage, attachment and determining the same entity | [[basic.link#4]], [[basic.link#8]], [[basic.link#10]] |
| TU-local entities and exposure | [[basic.link#14]]–[[basic.link#18]] |
| Where inline functions and variables attached to a named module are defined | [[dcl.inline#5]] |
| Member functions defined in a class in a named module are no longer implicitly inline | [[class.mfct#1]] |
| Preceding definitions in name lookup | [[basic.lookup#2]] |
| ADL can find functions that are exported but not visible | [[basic.lookup.argdep#4]] |
| Points of instantiation | [[temp.point]] |
| `module`, `import` and `export` as preprocessing directives | [[cpp.module]], [[cpp.import]], [[cpp.pre]] |
| Standard library modules `std` and `std.compat` | [[std.modules]] |

## History

!!! history
    - The Modules TS was published in 2018. Before that, Clang's module-map-based header modules and MSVC's early implementation had already built up experience.
    - C++20: [[P1103R3]] merged the Modules TS and the Clang-side proposal into the standard, introducing the global module fragment, partitions, header units and the rules for importing macros. Later proposals filled in the details: [[P1815R2]] introduced TU-local entities and exposure; [[P1779R3]] made member functions defined in a class in a named module no longer implicitly inline; [[P1857R3]] turned `module` and `import` into preprocessing directives that build systems can scan cheaply.
    - C++23: [[P2465R3]] introduced the standard library modules `std` and `std.compat`. [[P2615R1]], as a defect report, tightened which declarations `export` can apply to; for example, partial specializations can't be exported.
    - C++26: module names can no longer be produced by macro expansion ([[cpp.module]]).
