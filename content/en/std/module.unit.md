---
title: Module units and purviews
summary: "Which translation units make up a module (interface units, implementation units, partitions), what restrictions apply to module names, and which module each declaration is attached to."
updated: 2026-10-19
---

!!! tldr
    - A translation unit that begins with a `module` declaration is a module unit; module units with the same name together make up a named module, and dots in module names carry no hierarchy.
    - Those with `export` are interface units, those without are implementation units; those with `:name` are partitions. Every module has exactly one interface unit without a partition name, the primary interface unit.
    - Only an ordinary implementation unit `module M;` implicitly imports the primary interface unit; partitions don't, since that would form an import cycle.
    - Every declaration is attached to a module: by default the module it appears in; namespaces, aliases and declarations inside `extern "C++"`/`extern "C"` are attached to the global module.
    - Attachment decides whether two declarations are the same entity, and also decides the mangled symbol name. Exporting changes only linkage, not attachment.

## Which files make up a module

```cpp title="A.cppm (primary interface unit)"
export module A;
export import :Foo;   // the primary interface must export the interface partition A:Foo
export int baz();
```

```cpp title="A-Foo.cppm (interface partition)"
export module A:Foo;
import :Internals;    // imports this module's implementation partition
export int foo() { return 2 * (bar() + 1); }
```

```cpp title="A-Internals.cppm (implementation partition)"
module A:Internals;
int bar();            // not exported: usable only inside module A
```

```cpp title="A.cpp (implementation unit)"
module A;             // implicitly imports the primary interface, so baz is visible
import :Internals;
int bar() { return baz() - 10; }
int baz() { return 30; }
```

```cpp title="main.cpp" ok
import A;
int main() { return foo() + baz(); }   // 2*(20+1) + 30 = 72
```

This is the example in the standard's ¶4 plus a user. In our tests, after compiling with Clang 23 in the order `A-Internals → A-Foo → A → (A.cpp, main.cpp)` and linking, the program returns 72. Calling `bar()` in `main.cpp` reports "use of undeclared identifier": `bar` isn't exported, and `main.cpp` doesn't belong to module A.

The line at the start of each file is called a **module declaration** (*module-declaration*):

```text
module-declaration:
    export-keyword(opt) module-keyword module-name module-partition(opt) attribute-specifier-seq(opt) ;
```

¶1 A translation unit (TU: a source file compiled separately, together with the headers it includes; see [[lex.phases]]) that contains a module declaration is a [[g:module-unit|module unit]]. All the module units with the same module name together are called a **named module**.

There's no separate module object in the standard; a module is just the set of module units with the same name. Which files are compiled and linked together is decided by the build system; the standard constrains this set only with a few no-diagnostic-required rules (see below).

¶2 A module unit whose module declaration begins with `export` is a **module interface unit**; the rest are **module implementation units**. ¶3 A module unit whose module declaration has a `:name` is a [[g:module-partition|module partition]]. The two dimensions combine into four kinds of unit:

| Module declaration | Kind | File in the example | Can it be imported? |
|---|---|---|---|
| `export module A;` | primary module interface unit | `A.cppm` | yes: `import A;` |
| `export module A:Foo;` | interface partition | `A-Foo.cppm` | only within the module: `import :Foo;` |
| `module A:Internals;` | implementation partition | `A-Internals.cppm` | only within the module: `import :Internals;` |
| `module A;` | implementation unit | `A.cpp` | no (there's no name to import) |

¶4 The standard explains the example this way: `A:Foo` forms part of the interface of module A, `A:Internals` contributes nothing to A's external interface, and `A.cpp` has no partition name, so it can't be imported.

!!! impl "Warning on implementation partitions"
    For the `import :Internals;` in `A-Foo.cppm`, Clang 23 warns `-Wimport-implementation-partition-unit-in-interface-unit`: "Names from A:Internals may not be reachable". The standard doesn't require this warning. It's a reminder that reachability of an implementation partition from importers is unspecified ([[module.reach#2]]), so relying on definitions in it isn't portable.

## Module names

`module` and `import` aren't keywords. When the preprocessor recognizes a module directive at the start of a line, it replaces `export` and `module` with the special tokens *export-keyword* and *module-keyword* ([[cpp.module#2]]), so a module declaration must start a line on its own, and `int module = 0;` is still valid.

Dots in module names have no semantics. `a.b` is just a name containing a dot, with no parent-child relationship to module `a`: `import a;` doesn't import `a.b`, and `a.b` can't see anything non-exported in `a`. Partition names can contain dots too (`:detail.io`), also with no hierarchy.

Module names can't come from macros. During preprocessing, the identifiers in the name must not be object-like macros and must not be followed by `(` ([[cpp.module#1]]). That way a build system can scan which module a file belongs to without fully reproducing all macro definitions.

¶1 places two more restrictions on the name itself:

<div class="compare" markdown="1">

```cpp title="bad.cppm" error
export module my.import;
// error: import can't
// appear in a module name
```

```cpp title="reserved.cppm" ifndr
export module std2.util;
// reserved: begins with std followed by digits
// no diagnostic required
```

</div>

- `module` and `import` must not be components of a module name or partition name, and a violation must be diagnosed. A line beginning with `import` is treated as an import directive, and these two words appearing in a name would interfere with scanning.
- Names beginning with `std` followed by zero or more digits (`std`, `std.core`, `std23.x`), and names containing a reserved identifier ([[lex.name]], such as `__foo` or `_Foo`), are reserved and shall not be used in a module declaration; no diagnostic is required. Names with reserved identifiers are for the implementation; the rest are for future standards (the standard library already uses `std` and `std.compat`; see [[std.modules]]).

`stdx` isn't reserved, because `x` isn't a digit.

Why is the reserved-name rule only no-diagnostic-required? The standard library's own `std` module is written with `export module std;` (libc++'s `std.cppm`, MSVC's `std.ixx`). Requiring a diagnostic would force the implementation to tell whether that line was written by a user or provided by itself, which goes beyond the language itself.

!!! impl "Diagnostics in our tests"
    Clang 23 gives only a `-Wreserved-module-identifier` warning for `std`, `std2.util` and `__impl`, nothing for `stdx`, and an error "is an invalid name for a module" for `my.import` and `a.module`. libc++'s `std.cppm` therefore needs `-Wno-reserved-module-identifier` to compile.

A module declaration may end with attributes, which appertain to that module declaration. The standard defines no attributes that can be used here.

## Constraints on the primary interface unit and partitions (¶2–¶3)

¶2 A named module must have exactly one interface unit without a partition name, called the [[g:primary-module-interface-unit|primary module interface unit]]. ¶3 A module can't have two partitions with the same name, and every interface partition must be exported, directly or indirectly, by the primary interface unit (`export import :Foo;`).

All three are no-diagnostic-required ({{ifndr}}), because the compiler sees only one TU at a time and can't know whether there's a second `export module M;` elsewhere, or whether a partition has been exported. Only the build system has a chance to catch these errors.

!!! impl "Two primary interface units"
    In our tests, building two files that both say `export module M;` with CMake 3.29 + Ninja, Ninja reports `multiple rules generate CMakeFiles/dup.dir/M.pcm` and stops. Compiling either file on its own, Clang reports no error.

Note 1 points out that partitions can be imported only by other units of the same module, and how a module is divided into units isn't visible outside it. The partition name in `import :P;` is always relative to the current module; there's no syntax to import a partition of another module. Importers see only module A and don't know `A:Foo` exists.

Partitions solve two problems: a large module's interface can be split across several files, and declarations can be shared inside a module without falling back to internal headers. The two kinds of partition differ as follows:

| | Interface partition `export module M:P;` | Implementation partition `module M:P;` |
|---|---|---|
| Can contain `export` declarations | yes | no ([[module.interface#1]]) |
| Must the primary interface export it | must (¶3) | can't be exported ([[module.import#8]]) |
| Typical use | split the interface across files | declarations shared inside the module |
| Implicitly imports the primary interface | no (¶8) | no (¶8) |

The primary interface unit has a few other special roles: the private module fragment can appear only in it ([[module.private.frag]]); its end is a special point in the instantiation context of templates ([[module.context#3]]).

## Implementation units implicitly import the primary interface (¶8)

¶8 A module declaration with neither `export` nor a partition name, that is, `module M;`, implicitly imports the primary module interface unit, as if `import M;` were written.

Partitions don't, because the primary interface usually imports the partitions. If a partition implicitly imported the primary interface in return, that would form an import cycle, which is forbidden ([[module.import#10]]). The standard's Example 2:

```cpp title="B-Y.cppm"
module B:Y;               // doesn't implicitly import B
int y();
```

```cpp title="B.cppm"
export module B;
import :Y;                // OK: no cycle formed
int n = y();
```

```cpp title="B-X1.cppm" error
module B:X1;              // doesn't implicitly import B
int &a = n;               // error: n isn't visible here
```

```cpp title="B-X2.cppm" ok
module B:X2;
import B;                 // a partition can import the primary interface explicitly, as long as B doesn't import B:X2
int &b = n;               // OK
```

```cpp title="B.cpp" ok
module B;                 // implicitly imports B
int &c = n;               // OK
```

`n` isn't exported, yet `B:X2` and `B.cpp` can use it: they belong to the same module as `B.cppm`, and non-exported names within the same module are visible after import ([[basic.lookup#2]]). In our tests Clang 23's verdicts on these five units match the comments.

## Purviews and the global module (¶5–¶6)

¶5 The sequence of tokens from the module declaration to the end of the TU is called the **module unit purview**. The purviews of all units of module M together are M's [[g:purview|purview]].

```cpp
module;                   // global module fragment: not in M's purview
#include <cstdio>
export module M;          // M's purview starts here
int f();
module :private;          // private module fragment: still in the purview
```

The global module fragment before the module declaration ([[module.global.frag]]) isn't in M's purview; the private module fragment after it is. Many rules are conditioned on the purview; for example, `export` can appear only in the purview of an interface unit ([[module.interface#1]]), and `const` variables in the purview of an interface unit no longer have internal linkage by default ([[basic.link#3]]).

¶6 All global module fragments, plus all TUs that aren't module units, make up the [[g:global-module|global module]]. Declarations in these places are in the purview of the global module. Note 2 adds that the global module has no name, no interface unit, and isn't introduced by any module declaration.

This definition gives all pre-C++20 code a home: declarations in traditional `.cpp` files and the headers they include are in the global module. Header units ([[module.import#5]]) aren't module units and also belong to the global module. If two unrelated TUs both write `int f();`, they declare the same `f`, because they are in the same module (the global module), which is exactly what backward compatibility requires.

## Which module a declaration is attached to (¶7)

¶7 A **module** is a named module or the global module. Every declaration is **attached to** one module. Attachment decides whether two declarations declare the same entity: two declarations with external or module linkage can be the same entity only if they are attached to the same module ([[basic.link#8]]).

```cpp title="M.cppm" ok
export module M;
int f1() { return 1; }                 // attached to M, module linkage
export int f2() { return 2; }          // attached to M, external linkage
extern "C++" int f3() { return 3; }    // attached to the global module
extern "C++" { export int f4() { return 4; } }   // attached to the global module, and exported
extern "C" int f5() { return 5; }      // attached to the global module, C language linkage
namespace N { int g() { return 6; } }  // N attached to the global module, N::g attached to M
export struct S { friend int h(S) { return 7; } };   // h attached to M
export int use() { return f1() + N::g() + h(S{}); }
```

In our tests we compiled this interface unit with Clang 23 and inspected the object file with `nm` (Mach-O, demangled with `llvm-cxxfilt`):

| Declaration | Symbol | Demangled |
|---|---|---|
| `f1` (not exported) | `__ZW1M2f1v` | `f1@M()` |
| `f2` (exported) | `__ZW1M2f2v` | `f2@M()` |
| `f3` (`extern "C++"`) | `__Z2f3v` | `f3()` |
| `f4` (`extern "C++"`, exported) | `__Z2f4v` | `f4()` |
| `f5` (`extern "C"`) | `_f5` | |
| `N::g` | `__ZN1NW1M1gEv` | `N::g@M()` |
| friend `h` | `__ZW1M1hS_1S` | `h@M(S@M)` |

The symbols of both `f1` and `f2` carry `W1M`: the mangled name reflects attachment, not whether it's exported. `extern "C++"` removes the module marker. Namespace `N` itself has no module marker, but its member `g` does. The three cases below explain these results.

### Default: attached to the module it appears in (¶7.3)

¶7.3 A declaration that isn't one of the two special cases below is attached to the module whose purview it appears in. Functions, classes, variables and templates written after `export module M;` are attached to M; those written in a global module fragment or an ordinary TU are attached to the global module.

Exporting doesn't affect attachment. `export int f2();` and `int f1();` are both attached to M; the only difference is linkage: the former has external linkage, the latter module linkage ([[basic.link#4]]). Thinking that exported things belong to the global module is a common misconception.

### Namespaces, aliases and linkage blocks are attached to the global module (¶7.2)

¶7.2 The following four kinds of declaration are attached to the global module:

- ¶7.2.1 Declarations of namespaces with external linkage. Namespaces are open, and many modules and ordinary code add members to `namespace std`, `namespace util` and so on. If a namespace were attached to a module, two modules' `namespace util` would be two different namespaces. So the namespace itself is attached to the global module, and its members follow their own rules. Unnamed namespaces have internal linkage and aren't included.
- ¶7.2.2, ¶7.2.3 Declarations of type aliases or namespace aliases. An alias introduces no new entity, and two modules declaring an alias with the same name for the same type shouldn't conflict (¶8.2 of [[basic.link#8]]).
- ¶7.2.4 Declarations inside a language linkage specification (*linkage-specification*, i.e. `extern "C"` or `extern "C++"`; see [[dcl.link]]).

The last one is the only way to explicitly choose the global module in module code. The reason for `extern "C"` is straightforward: C functions have no notion of modules. `extern "C++"` is a new use that C++20 gave it for modules: declaring entities also declared in headers, or keeping symbol names unchanged while migrating a codebase to modules.

### Friends naming an existing entity (¶7.1)

¶7.1 A non-dependent friend declaration of one of the following forms is attached to the module the named entity is attached to:

- it names a function, and the declarator is a qualified name (`friend void ::g();`, `friend void N::g();`) or a template-id (`friend void g<>(int);`);
- it names a class, other than in the form `class X` with neither qualification nor template arguments (for example `friend X;`, `friend class N::X;`, `friend class Y<int>;`).

These forms necessarily name an existing entity. Without ¶7.1, writing `friend void ::gfr();` in module M would attach it to M by ¶7.3, conflicting with the original attachment of `::gfr`, and code that should be valid would become ill-formed.

```cpp title="M2.cppm" ok
module;
#include "gfr.h"               // void gfr();  attached to the global module
export module M2;
export struct S {
  friend void ::gfr();         // ¶7.1: attached to the global module, like ::gfr
  friend void hid(S) {}        // ¶7.3: may introduce a new function; attached to M2
};
```

Unqualified `friend void hid(S);` and `friend class X;` may introduce new entities and are attached to the current module by ¶7.3.

### Attachment conflicts

If two corresponding declarations (same name, same signature, in the same scope) are attached to different modules and one precedes the other, the program is ill-formed ([[basic.scope.scope]], note 5 under [[basic.link#10]]). So when a module redeclares an entity of the global module, that declaration must also be attached to the global module:

<div class="compare" markdown="1">

```cpp title="M.cppm" error
module;
#include "decls.h"  // int g();
export module M;
int g();
// error: corresponds to the g in decls.h,
// but is attached to M
```

```cpp title="M.cppm" ok
module;
#include "decls.h"  // int g();
export module M;
extern "C++" int g();
// OK: attached to the global module,
// a redeclaration of the g in decls.h
```

</div>

Clang 23 reports "declaration of 'g' in module M follows declaration in the global module" for the left one.

It follows from these rules that all declarations of an entity are attached to the same module, so the entity itself can be said to be attached to that module ([[basic.link#10]]). Attachment has two more direct consequences:

- An inline function or variable attached to a named module must be defined in the domain where it is declared ([[dcl.inline#5]]).
- For a class attached to a named module, member functions defined in the class aren't implicitly inline ([[class.mfct#1]]). There's only one strong definition in the module's object file, and changing the function body doesn't change the module interface.

## Implementation view

!!! impl "Module units and object files"
    - Each module unit is still a separate TU and produces one object file. Units that can be imported (primary interface, interface partitions, implementation partitions) also produce a binary module interface (BMI, the interface information the compiler caches) for importers; ordinary implementation units can't be imported and produce no BMI. For each compiler's command lines, see [[toolchain/modules-in-practice]].
    - The Itanium ABI marks attachment with `W <module-name>`, encoding dotted module names component by component: in our tests the `f` in `export module a.b;` is `__ZW1aW1b1fv`. This mangling embodies strong ownership: same-named entities attached to different modules are different symbols. GCC uses the same mangling; MSVC has its own scheme.
    - Partitions don't appear in the mangled names of entities. `greet::bracket` declared in partition `:fmt` of module `greet` has the same symbol as if it were declared in the primary interface, so moving declarations between partitions doesn't change the ABI. Partition names appear only in the symbols of module initializer functions (such as `__ZGIW5greetWP3fmt`).

## History

!!! history
    - Module units, partitions, the global module and attachment come from C++20's [[P1103R3]], which merged the Modules TS with another design, ATOM ([[P0947R1]]); partitions come from the latter. For the background of the design, see [[history/modules]].
    - Weak ownership was discussed early on: the symbols of exported entities would not contain the module name and would be the same as same-named entities in the global module. C++20 adopted strong ownership, with `extern "C++"` as the explicit exception.
    - The rule that module names can't come from macros was added by [[P3034R1]], adopted in 2024 as a defect report, so it applies to C++20 and C++23 as well.

## Common misconceptions

!!! pitfall "A module name is a namespace"
    After `export module math; export int add(int, int);`, importers write `add(1, 2)`, not `math::add(1, 2)`. If you want a namespace, write `export namespace math { ... }` yourself.

!!! pitfall "Implementation units can be imported"
    An ordinary implementation unit `module M;` has no name to import. To share helper declarations inside a module, use an implementation partition `module M:helpers;`.

!!! pitfall "`#include` a header after `export module M;`"
    The declarations included this way are all attached to M and are no longer the same entities as those defined in the library; the common result is undefined references at link time. Put `#include` in the global module fragment, or use `import` instead; see [[module.global.frag]].

## Questions

!!! question "Question 1"
    In the module unit below, which module is each declaration attached to? Which names have module linkage?

    ```cpp
    module;
    #include <cstddef>
    export module M;
    namespace util {
      using index = std::size_t;
      std::size_t count();
      export int version();
    }
    namespace { int secret; }
    extern "C++" void legacy();
    ```

<details markdown="1">
<summary>Answer</summary>

- The declarations in `<cstddef>` are in the global module fragment and attached to the global module (¶6, ¶7.3).
- `namespace util` has external linkage and is attached to the global module (¶7.2.1).
- `util::index` is a type alias, attached to the global module (¶7.2.2).
- `util::count` is attached to M (¶7.3) and not exported, so it has module linkage.
- `util::version` is attached to M and exported, so it has external linkage.
- The unnamed namespace has internal linkage, so ¶7.2.1 doesn't apply and it is attached to M by ¶7.3; `secret` is also attached to M, with internal linkage ([[basic.link#4]]).
- `legacy` is inside a linkage specification, attached to the global module (¶7.2.4), with external linkage.
</details>

!!! question "Question 2"
    How does `f` in `struct S { void f() {} };` inside `export module M;` differ from the same code in an ordinary header? What does that mean for binary compatibility?

<details markdown="1">
<summary>Answer</summary>

In a named module, `S` is attached to M, and `f`, defined in the class, isn't implicitly inline; [[class.mfct#1]] specifies implicit inline only for member functions attached to the global module. In our tests `nm -m` shows it as an `external` strong definition in M's object file (not `weak external`), and importers call it with an ordinary external call. Changing the body of `f` only requires recompiling M's object file. In a header, `f` is inline and its body is part of every includer. When you really need inline in a module, write `inline` explicitly.
</details>

## Summary

| Concept | Definition | Paragraph |
|---|---|---|
| Module unit, named module | a TU containing a module declaration; the set of module units with the same name | ¶1 |
| Reserved module names | beginning with `std` plus digits, or containing a reserved identifier; no diagnostic required | ¶1 |
| Interface unit, implementation unit | whether the module declaration begins with `export` | ¶2 |
| Primary module interface unit | the interface unit without a partition name, exactly one | ¶2 |
| Partition | has `:P`; no duplicate names; interface partitions must be exported | ¶3 |
| Purview | from the module declaration to the end of the TU | ¶5 |
| Global module | global module fragments plus all non-module TUs | ¶6 |
| Attachment | friends naming an existing entity follow that entity; namespaces, aliases, linkage blocks follow the global module; everything else follows the module it appears in | ¶7 |
| Implicit import | only `module M;` implicitly imports the primary interface | ¶8 |
