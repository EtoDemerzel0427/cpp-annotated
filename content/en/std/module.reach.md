---
title: Reachability
summary: "Modules separate whether a name can be written (visible) from whether a declaration's effects apply (reachable): which translation units are necessarily reachable from a point and which may be, when a declaration is reachable, and how all reachable declarations together decide whether a type is complete and whether default arguments can be used."
updated: 2026-10-19
---

!!! tldr
    - Visibility decides whether name lookup can find a declaration and is controlled by exporting and importing; reachability decides whether a declaration's effects (type completeness, default arguments, etc.) apply. Whether something is exported has nothing to do with whether it is reachable.
    - Directly imported translation units, and module interface units with an interface dependency, are necessarily reachable. Whether header units and implementation partitions depended on only indirectly through another module are reachable is unspecified.
    - A type that isn't exported can still be used fully by importers through `auto`, exported aliases and so on, as long as its definition is in an interface unit.
    - How an entity behaves at some point is decided by the properties of all declarations reachable there, taken together. Default arguments are evaluated at the call site, so the types they use must also be complete at the call site.

## Visible vs reachable

```cpp title="TU #1: A.cppm"
export module A;
struct X {};
export using Y = X;
```

```cpp title="TU #2: user.cpp" error
import A;
Y y;                // OK: X's definition is reachable
X x;                // error: X isn't visible to unqualified lookup
```

This is the standard's Example 3 (¶6). `X` isn't exported, so `user.cpp` can't write the name, and Clang 23 reports `unknown type name 'X'`. But the exported alias `Y` refers to `X`, and `X`'s definition is in `A`'s interface unit, reachable from `user.cpp`, so `Y y;` can define a complete `X` object.

Modules separate two things:

- **Visible**: whether name lookup can find a declaration, which decides whether you can write the name. Controlled by exporting and importing ([[module.interface]], [[module.import]], [[basic.lookup#2]]).
- **Reachable**: whether a declaration's effects apply at some point, which decides whether a type is complete, whether members can be accessed, and whether default arguments can be used. Specified by this subclause.

Why separate them? Suppose a module exports `export Widget make();` without exporting `Widget`. An importer writing `auto w = make(); w.draw();` never writes `Widget`, but the compiler must know its size, members and destructor. If reachable meant the same as visible, modules couldn't hide any implementation type; conversely, if visible meant the same as reachable, exporting would be pointless.

Note 5 under ¶6 says exactly this: a declaration of an entity can be reachable at a point even though name lookup can't find it there.

## Which translation units are reachable (¶1, ¶2)

First, a few terms. A **[[g:module-interface-unit|module interface unit]]** is a unit beginning with `export module`, including the primary interface unit and interface partitions; an **implementation partition** is a partition without `export`, like `module M:P;`; a **[[g:header-unit|header unit]]** is a header imported with `import "x.h";`. A translation unit that imports U, or imports something that (transitively) depends on U, has an **[[g:interface-dependency|interface dependency]]** on U ([[module.import#10]]).

¶1 A translation unit U is **[[g:necessarily-reachable|necessarily reachable]]** from a program point P if, before P, either:

- U is a module interface unit on which the translation unit containing P has an interface dependency; or
- the translation unit containing P imports U directly.

| What U is | Relation to the translation unit containing P | Necessarily reachable |
|---|---|---|
| Module interface unit | imported directly | yes |
| Module interface unit | indirect interface dependency (for example through a non-exported `import`) | yes |
| Header unit | imported directly | yes |
| Header unit | only an indirect interface dependency | no |
| Implementation partition | imported directly by a unit of the same module | yes |
| Implementation partition | only an indirect interface dependency (external importer → primary interface → implementation partition) | no |

Note 1 adds that a module interface unit is reachable even if it is only imported transitively through a non-exported `import`; name lookup just can't find its namespace-scope names.

¶2 All necessarily reachable translation units are **reachable**. Other translation units on which P has an interface dependency may also be considered reachable, but which ones, and under what circumstances, is unspecified. A footnote explains that implementations therefore need not prevent the effects of additional translation units involved in the compilation from being observed. Note 2 recommends that portable programs not depend on the reachability of additional translation units.

The standard gives a lower bound (necessarily reachable) and an upper bound (interface dependency) and leaves the middle to implementations, because implementation approaches differ greatly: for some, loading indirectly depended-on header units or implementation partitions is expensive; others load everything anyway.

## When a declaration is reachable (¶3, ¶4)

¶3 A declaration D is reachable from a point P if:

- ¶3.1 P is not a synthesized point, and
    - ¶3.1.1 D appears before P in the same translation unit; or
    - ¶3.1.2 D isn't discarded ([[module.global.frag#3]]), appears in a translation unit reachable from P, and doesn't appear in a private module fragment;
- ¶3.2 D is an injected declaration and P is the synthesized point corresponding to it. {{c++26}}

The three conditions of ¶3.1.2 correspond to other subclauses of this chapter: declarations discarded from the global module fragment aren't reachable from outside; the private module fragment isn't reachable from outside ([[module.private.frag]]); all other declarations, exported or not, are reachable as long as their translation unit is.

¶4 A declaration is reachable if it is reachable from any point in the instantiation context ([[module.context]]). For ordinary code, the instantiation context is just the current point; for a template instantiation, it may include certain points in the module where the template is defined. Note 3 stresses: **whether a declaration is exported has no bearing on whether it is reachable**.

### Synthesized points and injected declarations {{c++26}}

C++26 static reflection can complete an incomplete class during constant evaluation with `std::meta::define_aggregate`, which produces an **[[g:injected-declaration|injected declaration]]** ([[expr.const.reflect]]). It doesn't appear at some position in the source; instead it is reachable at an associated **synthesized point**. The standard's Example 1:

```cpp
class Incomplete;

consteval {
  int n = nonstatic_data_members_of(
      define_aggregate(^^Incomplete, {data_member_spec(^^int, {.name="x"})}),
      std::meta::access_context::current()
    ).size();               // n is 1: the member x is reachable at the synthesized point P

  Incomplete y;             // error: the injected declaration isn't reachable from here (not a synthesized point); the type is incomplete
}
/* P */                     // after the consteval block, Incomplete is complete
```

Clang 23 in our tests doesn't implement static reflection yet and has no `<meta>` header, so this example hasn't been compiled; the comments follow the standard's text.

## Accumulating semantic properties (¶5)

The same entity may have several declarations in several translation units: a forward declaration, a definition, a redeclaration with default arguments. ¶5 specifies that in a given context, the properties of all reachable declarations of an entity, taken together, decide its behavior in that context. Note 4 lists these properties: whether a type is complete, type definitions, initializers, default arguments of functions or templates, attributes, names bound, and so on.

So if the declarations reachable from some point include a class definition, the type is complete there; if they include a function declaration with default arguments, arguments can be omitted there; if they include `[[deprecated]]`, uses there may get a warning.

The standard's Example 2:

```cpp title="TU #1: M-A.cppm"
export module M:A;
export struct B;              // only a forward declaration
```

```cpp title="TU #2: M-B.cppm"
module M:B;                   // implementation partition
struct B {
  operator int();
};
```

```cpp title="TU #3: M-C.cppm" error
module M:C;
import :A;
B b1;                         // error: no reachable definition of B
```

```cpp title="TU #4: M.cppm" ok
export module M;
export import :A;
import :B;                    // implementation partition imported directly: necessarily reachable
B b2;                         // OK
export void f(B b = B());
```

```cpp title="TU #5: user.cpp" error
import M;
B b3;                         // error: no reachable definition of B
void g() { f(); }             // error: likewise; the default argument B() is evaluated at the call site
```

In TU #5 the name `B` is visible, because `M` exports it through `export import :A`. `B`'s definition is in the implementation partition `M:B`. `user.cpp` has an interface dependency on `M:B` (user → M → M:B), but `M:B` isn't a module interface unit and `user.cpp` can't import it directly, so it isn't necessarily reachable. The standard's example marks these two lines as errors on the assumption that the implementation doesn't use the freedom of ¶2 to treat `M:B` as reachable; strictly speaking, whether they are valid is unspecified, and portable code should treat them as errors.

The `f()` line illustrates the last sentence of note 4: a default argument is evaluated in the context of the call expression, so the reachable properties of the parameter type are also determined at the call site. `B()` needs `B` to be complete, and at the call site `B` is incomplete. That `f` is declared in TU #4, where `B` is complete, doesn't help.

!!! impl "Clang 23's behavior"
    For TU #3, Clang reports `variable has incomplete type 'B'`. For `B b3;` in TU #5, it reports `definition of 'B' must be imported from module 'M' before it is required`, with the note `definition here is not reachable`, showing that Clang chooses not to treat indirectly depended-on implementation partitions as reachable.

    But Clang doesn't diagnose `void g() { f(); }`: it doesn't recheck the default argument's completeness requirement at the call site. Written as `void h(B* p) { f(*p); }`, which explicitly needs to copy a `B` at the call site, Clang reports the same not-reachable error. On the `f()` line, Clang disagrees with the standard's example.

## Summary table

| What you want to do | What's needed | Rule |
|---|---|---|
| Write a namespace-scope name `N::f` | the declaration is visible: imported and exported, or in the same module and not internal linkage | [[basic.lookup#2]] |
| Access a class member `obj.m`, `T::m` | the class definition is reachable | ¶3–¶5 |
| Define an object, `sizeof`, copy | the type definition is reachable | ¶5 |
| Use a default argument | the declaration with the default argument is reachable, and the types used in the argument are reachable at the call site | ¶5 note 4 |
| ADL for a dependent name finds a function | visible from some point in the instantiation context, or meets the module special case | [[basic.lookup.argdep#4]], [[module.context]] |
| odr-use an inline function | the definition is reachable at the end of the definition domain where it is used | [[basic.def.odr]] |

!!! impl "Reachability and BMIs"
    In implementation terms, reachable roughly corresponds to the compiler having loaded the corresponding BMI (precompiled module interface file) with this declaration retained in it. Clang loads transitively depended-on BMIs as needed when compiling an importer, but models reachability as the standard does: the `definition here is not reachable` above shows that Clang found the definition but judged it unreachable. This is stricter than making everything loaded reachable, and better for writing portable code.

## History

!!! history
    - Reachability came into C++20 with the merged modules proposal [[P1103R3]]. In early versions of the Modules TS the boundary between visible and reachable was unclear; the merged proposal distinguished the two explicitly and defined necessarily reachable.
    - C++23's rewrite of the name lookup clauses ([[P1787R6]]) defined visibility precisely in terms of "precedes", complementing the reachability of this subclause.
    - C++26 added synthesized points and injected declarations (¶3.2) for static reflection's `define_aggregate`.

## Common misconceptions

!!! pitfall "Not exported means private"
    A type that isn't exported is reachable from all importers as long as its definition is in an interface unit. Importers can use all its functionality through `auto`, `decltype`, template argument deduction and exported type aliases, including accessing its public members. To really hide it, put the definition in an implementation unit or the private module fragment.

!!! pitfall "The definition is in an implementation partition, but the name is exported from the interface"
    Like `B` in ¶5, importers get only an incomplete type (definitely so on Clang; possibly different on other implementations). If you want importers to be able to use the definition, put it in an interface partition and `export import` it, or put it directly in the primary interface. When an exported function's default argument constructs such a type, calls from importers may fail too.

## Questions

!!! question "Question 1"
    Module `M`'s primary interface unit contains `struct Impl { int x = 1; }; export Impl get();`. Can an importer write `int v = get().x;`? `decltype(get()) i; i.x = 2;`? `Impl i;`?

<details markdown="1">
<summary>Answer</summary>

The first two, yes. `Impl`'s definition is in `M`'s interface unit, and the importer imports `M`, so it is necessarily reachable. The member `x` is found by class member lookup, which only needs the definition to be reachable; `decltype` doesn't require writing the name.

`Impl i;` no: `Impl` isn't exported, so name lookup can't find it. In our tests Clang 23 reports `unknown type name 'Impl'`.
</details>

!!! question "Question 2"
    ¶3.1.2 requires that D not be in a private module fragment. Why doesn't ¶3.1.1 (appears before P in the same translation unit) have this restriction?

<details markdown="1">
<summary>Answer</summary>

¶3.1.1 handles the inside of a single translation unit: declarations in the private module fragment are of course reachable to later code in the fragment; that's just ordinary declare-before-use. ¶3.1.2 handles the cross-translation-unit case, and the purpose of the private module fragment is not to affect other translation units ([[module.private.frag#2]]), so it has to be excluded.
</details>
