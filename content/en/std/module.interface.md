---
title: Export declarations
summary: "Where export can be written and what it can apply to, what counts as an exported declaration, and how exporting relates to linkage."
updated: 2026-10-19
---

!!! tldr
    - `export` can appear only at namespace scope within the purview of a module interface unit; not in implementation units, unnamed namespaces or the private module fragment.
    - Exporting decides which names importers can write. Class members don't need to be exported separately; as long as the class definition is reachable from the importer, the members can be used.
    - An exported name can't have internal linkage; an exported `using` declaration may only refer to entities with external linkage or to type aliases.
    - Whether an entity is exported is decided by its first declaration: exporting first and defining later is fine, but not exporting first and adding `export` later isn't.
    - Exporting a name doesn't mean importers can use it fully: if the definition for `export struct A;` is in an implementation unit, importers always see an incomplete type.

## Three ways to write export

```cpp title="M.cppm" ok
export module M;
import Q;
export import R;               // re-export: whoever imports M also imports R
export int f();                // export a single declaration
export {                       // export block: every declaration in the block is exported
  struct S { int v; };
  int g(S);
}
export namespace N {           // export a whole namespace definition
  int h();
}
```

Grammatically, an *export-declaration* has three forms:

```text
export-declaration:
    export name-declaration
    export { declaration-seq(opt) }
    export-keyword module-import-declaration
```

The third is re-exporting (`export import`), whose meaning is specified in [[module.import#7]]. The first accepts only a *name-declaration* ([[dcl.pre]]), not explicit specializations, explicit instantiations or another *export-declaration*, so `export template<> void f<int>(int) {}` and `export template void f<long>(long);` don't parse.

!!! impl "Clang deviates"
    In our tests Clang 23 accepts `export template<> void f<int>(int) {}` and `export template void f<long>(long);`, and also accepts exporting a partial specialization (see the next section), all without a diagnostic. Under the current draft all three are ill-formed.

## Where export can appear (¶1)

¶1 An *export-declaration* must inhabit a namespace scope (the global namespace or a named namespace) and appear in the purview of a module interface unit ([[module.unit#5]], from the module declaration to the end of the TU). It can't appear, directly or indirectly, in an unnamed namespace or a private module fragment.

<div class="compare" markdown="1">

```cpp title="M.cppm" error
export module M;
export { export int q; }
// error: export nested in an export block
module :private;
export int z;
// error: can't export in the private module fragment
```

```cpp title="impl.cpp" error
module M;
export int g();
// error: not in a module interface unit
```

</div>

Each of these placement restrictions has a direct reason:

- The purpose of exporting is to provide names to importers outside the module, and only interface units can be imported from outside. So `export` can't be written in implementation units, implementation partitions, global module fragments or non-module TUs.
- Everything in an unnamed namespace has internal linkage, and other TUs can't refer to it (a special case of ¶3).
- The private module fragment exists precisely so as not to affect importers ([[module.private.frag]]).
- Class members and local declarations aren't at namespace scope and can't be exported on their own.

¶1 has three more rules:

- `export` doesn't change the effect of the declaration itself: an *export-declaration* has the effect of the declaration it contains. Note 1 adds that it doesn't establish a scope; the `a` in `export { int a; }` is in the enclosing namespace, just like `export int a;`.
- Partial specializations can't be exported ([[temp.decls.general]]). A partial specialization introduces no name; as long as the primary template and the partial specialization are reachable from the importer, it is used in matching. Allowing it to be exported would suggest that not exporting it hides it from importers. This restriction comes from [[P2615R1]] and, as a defect report, also applies to C++20.
- An export block can't contain another `export` or an import declaration.

Clang 23 reports "export declaration appears within another export declaration" and "export declaration cannot be used in a private module fragment" for the two errors on the left, and "export declaration can only be used within a module interface" for the right.

## What counts as exported (¶2)

¶2 A declaration is **[[g:exported-declaration|exported]]** if it is within an *export-declaration* and inhabits a namespace scope, or it is one of the following:

- ¶2.1 a namespace definition that contains an exported declaration;
- ¶2.2 a declaration within a header unit that introduces at least one name.

```cpp title="M.cppm" ok
export module M;
export {
  int a;                  // exported
  namespace N { int b; }  // this definition of N and N::b are both exported
}
namespace P {
  export int c;           // this definition of P is exported by ¶2.1
  int d;                  // not exported: module linkage
}
export enum E { e1 };     // E and e1 both inhabit namespace scope and are both exported
export struct S {         // S is exported; S::m isn't an exported declaration
  int m;
};
```

`S::m` inhabits a class scope and isn't an exported declaration, yet importers can still write `s.m`. Class members are found by class member lookup and only need `S`'s definition to be reachable from the importer (¶7).

¶2.1 lets importers write `P::c`: if the namespace definition containing `c` weren't exported, importers couldn't even write `P::`. Only this one namespace definition is exported; unexported members in other `namespace P { ... }` blocks in the same module remain invisible.

¶2.2 makes everything in a header unit (`import "x.h";`, see [[module.import#5]]) implicitly exported. Headers have no notion of exporting, and `import "x.h";` should provide the same names as `#include "x.h"`.

## Names with internal linkage can't be exported (¶3–¶4)

¶3 An exported declaration that isn't within a header unit shall not declare a name with internal linkage. Exporting means other TUs can refer to the entity through this name, while internal linkage means only this TU can; the two contradict each other.

Header units are the exception: headers contain lots of `static` functions and `const` variables, and `import "x.h";` must be able to provide them just like `#include` ([[module.import#6]]).

¶4 The standard's Example 1:

```cpp title="M.cppm" error
module;
#include "a.h"                  // a.h contains export int x;
                                // error: the global module fragment isn't in the purview of an interface unit
export module M;
export namespace {}             // error: an unnamed namespace has internal linkage
namespace {
  export int a2;                // error: exported within an unnamed namespace
}
export static int b;            // error: b is explicitly declared static
export int f();                 // OK
export namespace N { }          // OK
export using namespace N;       // OK, but has no effect
```

Clang 23 reports the four errors in turn as "export declaration can only be used within a module interface", "anonymous namespaces cannot be exported", "export declaration appears within anonymous namespace" and "declaration of 'b' with internal linkage cannot be exported".

The last line is a using-directive. It is a *name-declaration*, so grammatically it can be exported; but it introduces no name, so by ¶2 it isn't an exported declaration. A using-directive affects only name lookup in this TU ([[basic.lookup.udir]]); importers don't get the effect of `using namespace N` from it.

In an ordinary header, `const int n = 5;` has internal linkage and by ¶3 couldn't be exported. For this reason, `const` variables in the purview of a module interface unit no longer have internal linkage by default (¶3.2.1 of [[basic.link#3]]); `export const int n = 5;` is valid and `n` has external linkage.

## Exporting using-declarations (¶5)

A using-declaration ([[namespace.udecl]]) declares no new entity; it just lets an entity declared elsewhere be found here by some name. Exporting it means letting importers find that entity by this name.

¶5 So in an exported using-declaration not within a header unit, each entity named by a *using-declarator* must be either a type alias or introduced with a name having external linkage. Entities with module linkage won't do, since the importer isn't in the same module; internal linkage even less so. The standard's Example 2:

```cpp title="b.h"
int f();
```

```cpp title="c.h (importable header)"
int g();
```

```cpp title="X.cppm"
export module X;
export int h();
```

```cpp title="M.cppm" error
module;
#include "b.h"
export module M;
import "c.h";
import X;
export using ::f, ::g, ::h;     // OK: f and g are attached to the global module, h to X, all with external linkage
struct S;
export using ::S;               // error: S has module linkage
namespace N {
  export int h();
  static int h(int);            // #1
}
export using N::h;              // error: #1 has internal linkage
```

The last line shows that a using-declaration brings in the whole overload set: if even one overload of `N::h` has internal linkage, ¶5 is violated. Clang 23 reports the two errors as "using declaration referring to 'S' with module linkage cannot be exported" and "... 'h' with internal linkage cannot be exported".

The most common use of this rule is to re-export declarations obtained by `#include` in the global module fragment ([[module.global.frag]]). Functions from a header included in the global module fragment aren't exported; `export using ::f;` exports them. libc++'s `std.cppm` implements `import std;` this way: it includes all headers in the global module fragment and then writes `export namespace std { using std::vector; ... }`.

Note 2 adds that for an exported type alias, the underlying entity need not have external linkage:

```cpp title="M.cppm" ok
export module M;
struct S;
export using T = S;             // OK: exports the name T, which denotes the type S
```

Importers can write `T` but not `S`. Whether `T` can be used to define objects depends on whether `S`'s definition is reachable ([[module.reach#6]]).

## Export status is decided by the first declaration (¶6)

<div class="compare" markdown="1">

```cpp title="M2.cppm" ok
export module M2;
export struct X;
struct X { int a; };
// OK: implicitly exported
export int v();
int v() { return 1; }
// OK: implicitly exported
```

```cpp title="M.cppm" error
export module M;
struct S { int n; };
export struct S;
// error: an exported declaration
// follows a non-exported one
```

</div>

¶6 A redeclaration of an entity X is implicitly exported if X was introduced by an exported declaration; otherwise the redeclaration shall not be exported, unless it is a type alias, namespace or namespace alias.

The left is the common pattern: export the declaration at the top of the interface and define it later. On the right, `S` had module linkage when first declared, and exporting it afterwards would amount to changing it to external linkage. If linkage changed midway, code before and after would disagree about the linkage of the same entity, so the standard requires linkage to be fixed at the first declaration. Clang 23 reports "cannot export redeclaration 'S' here since the previous declaration has module linkage" for the right.

The three exceptions don't have this problem. A type alias can be redeclared and exported at any time; a namespace is attached to the global module and always has external linkage ([[module.unit#7]]), so each definition can independently choose whether to export; a namespace alias likewise. The standard's Example 4:

```cpp title="M.cppm" error
export module M;
struct S { int n; };
typedef S S;
export typedef S S;             // OK: type alias
export struct S;                // error: an exported declaration follows a non-exported one
namespace N {                   // external linkage, attached to the global module, not exported
  void f();
}
namespace N {                   // OK: an exported namespace redeclaring a non-exported namespace
  export void g();
}
```

## How importers use exported names (¶7)

¶7 Note 3 sums up several consequences of exporting:

- Names introduced by exported declarations never have module linkage; they have external linkage, no linkage, or (in header units) internal linkage. This follows directly from [[basic.link#4]]: only names attached to a named module and not exported have module linkage.
- Namespace-scope declarations exported by a module can be found by name lookup in any TU that imports the module ([[basic.lookup]]).
- Member names of classes and enumerations can be found wherever the definition of the type is reachable.

Visibility and reachability are two things: exporting lets importers write the name, and **reachability** ([[module.reach]]) decides whether importers can see semantic information such as definitions and default arguments. The standard's Example 5 puts the two together:

```cpp title="M.cppm (interface unit of M)"
export module M;
export struct X {
  static void f();
  struct Y { };
};

namespace {
  struct S { };
}
export void f(S);               // marked OK in the standard's example; see the discussion below
struct T { };
export T id(T);                 // OK: T has module linkage and isn't TU-local

export struct A;                // A exported as an incomplete type

export auto rootFinder(double a) {
  return [=](double x) { return (x + a/x)/2; };
}

export const int n = 5;         // OK: n has external linkage
```

```cpp title="M-impl.cpp (implementation unit of M)"
module M;
struct A {
  int value;
};
```

```cpp title="main.cpp" error
import M;
int main() {
  X::f();                       // OK: X is exported and its definition is reachable
  X::Y y;                       // OK: X::Y is usable along with X's definition
  auto f = rootFinder(2);       // OK
  return A{45}.value;           // error: A is an incomplete type
}
```

- `X::f` and `X::Y` aren't exported separately; `X`'s definition is in the interface unit and reachable, so the members can be used.
- `T` isn't exported; importers can't write `T`, but they can write `auto t = id({});`. `T`'s definition is reachable, so the return value can be used normally.
- `rootFinder` returns a lambda's closure type, which importers receive with `auto`. An exported function whose return type contains a placeholder must be defined in the TU containing the exported declaration, outside the private module fragment ([[dcl.spec.auto#12]]); otherwise importers can't deduce the return type.
- `A` is exported, so importers can write `A`, but its definition is in an implementation unit. Implementation units can't be imported and aren't reachable from importers, so the `A` importers see is always incomplete. Clang 23 reports "invalid use of incomplete type 'A'" for the last line.

!!! lawyer "Is `export void f(S);` really OK?"
    `S` is in an unnamed namespace, has internal linkage, and is a **TU-local** entity (an entity usable only within this TU; see [[basic.link#15]]). The `f` declared by `export void f(S);` has external linkage and isn't TU-local; its parameter type names `S` ([[basic.link#13]]), so by [[basic.link#14]] this declaration is an **exposure**: what a non-inline function may ignore is only its function body, not its parameter types. [[basic.link#17]] specifies that if a declaration of a non-TU-local entity in a module interface unit is an exposure, the program is ill-formed.

    So by the normative wording this line is ill-formed; examples aren't normative, and the OK comment is most likely left over from before the TU-local rules ([[P1815R2]]) were added. In our tests Clang 23 gives the warning `TU local entity 'S' is exposed [-WTU-local-entity-exposure]` for this line, in line with the normative wording. When an example conflicts with the normative wording, the normative wording prevails.

## Exported namespaces and linkage blocks (¶8)

¶8 Note 4 points out that declarations in an exported namespace definition or an exported linkage specification ([[dcl.link]]) are all exported and subject to all the rules above. So `export namespace N { ... }` can contain nothing with internal linkage, and no using-declaration referring to an entity with module linkage (the standard's Example 6):

```cpp title="M.cppm" error
export module M;
int g;
export namespace N {
  int x;                        // OK
  using ::g;                    // error: ::g has module linkage
}
```

Declarations in `export extern "C++" { ... }` are both attached to the global module ([[module.unit#7]]) and exported, with the same symbol names as in the header era, which suits migrating an existing library to modules step by step:

```cpp title="legacy.cppm" ok
export module legacy;
export extern "C++" {
  int parse(const char*);       // attached to the global module, exported
}
```

## Quick reference: what can be exported

| Declaration | Can it be `export`ed | Basis |
|---|---|---|
| Functions, variables, classes, enumerations, templates, concepts with external linkage | yes | |
| `const` and `constexpr` variables in a module interface | yes; here they don't default to internal linkage | [[basic.link#3]] |
| `static` functions and variables, anything in an unnamed namespace | no | ¶1, ¶3 |
| Partial specializations | no | ¶1 |
| Explicit specializations, explicit instantiations | can't take `export` directly (grammar); can appear in an export block | grammar |
| Type aliases | yes; the underlying type need not have external linkage | ¶5 note 2 |
| Using-declarations | yes, provided every entity referred to has external linkage or is a type alias | ¶5 |
| Using-directives, `static_assert` | grammatically yes, but they introduce no name and have no effect | ¶2 |
| Namespaces | yes; a namespace definition containing an exported declaration is exported automatically | ¶2.1 |
| Class members | can't be exported separately; reachable along with the class definition | ¶1, ¶7 |
| Redeclarations of an entity whose first declaration wasn't exported | no (except type aliases, namespaces, namespace aliases) | ¶6 |
| Import declarations | `export import` is a re-export | [[module.import#7]] |

## History

!!! history
    - The three forms of `export` and the rule that names with internal linkage can't be exported come from C++20's [[P1103R3]]. `const` variables in module interfaces no longer defaulting to internal linkage also came into C++20 along with modules.
    - [[P2615R1]] (*Meaningful exports*), as a defect report against C++20, tightened the declarations `export` can apply to, for example forbidding the export of declarations that introduce no name, such as partial specializations.

## Common misconceptions

!!! pitfall "When a class is exported, member functions defined in it are inline"
    In a named module, the `get` in `export struct S { int get() { return v; } int v; };` isn't inline ([[class.mfct#1]]). An importer calling `s.get()` makes an ordinary external call, unless cross-TU optimization such as LTO is enabled. If you need inline, write `inline` explicitly.

!!! pitfall "`export using namespace std;` is passed on to importers"
    It isn't. A using-directive only affects name lookup in this TU; exporting it is a valid no-op.

!!! pitfall "An exported inline function can call any function in the module"
    `void helper(); export inline void api() { helper(); }` is valid: `helper` has module linkage and isn't TU-local. But if `helper` is `static`, the definition of `api` is an exposure ([[basic.link#14]]), which is ill-formed in a module interface. In our tests Clang 23 gives only a `-WTU-local-entity-exposure` warning for it.

## Questions

!!! question "Question 1"
    Which lines below are ill-formed?

    ```cpp
    export module M;
    struct A {};
    export using B = A;            // (1)
    export struct A;               // (2)
    export struct C;               // (3)
    struct C { int x; };           // (4)
    export namespace { }           // (5)
    ```

<details markdown="1">
<summary>Answer</summary>

- (1) Valid: exporting a type alias; the underlying entity need not have external linkage (¶5 note 2).
- (2) Ill-formed: `A` wasn't exported when first declared, so a redeclaration can't be exported (¶6).
- (3), (4) Valid: (4) is implicitly exported (¶6).
- (5) Ill-formed: an unnamed namespace has internal linkage, violating ¶3; the same line in the standard's Example 1 is marked error.
</details>

!!! question "Question 2"
    An interface unit has only `export struct Handle; export Handle* make();`, with `Handle`'s definition in an implementation unit. What can importers do?

<details markdown="1">
<summary>Answer</summary>

Importers can write `Handle`, declare `Handle*` variables and call `make()`, but `Handle`'s definition isn't reachable from them, so `Handle` is an incomplete type: they can't create `Handle` objects, access members, take `sizeof(Handle)`, or `delete` the pointer (since C++26, deleting an object of incomplete type is ill-formed; see [[expr.delete#4]]). This is the module version of an opaque handle; destruction also has to be done by a function the module provides.
</details>
