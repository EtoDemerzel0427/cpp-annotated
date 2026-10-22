---
title: Global module fragment
summary: "Where a module unit includes traditional headers, between module; and the module declaration; declarations there that the module doesn't use are discarded, and the decl-reachable relation specifies precisely what counts as used."
updated: 2026-10-19
---

!!! tldr
    - When a module unit needs traditional headers, put the `#include`s between `module;` and `export module M;`. This section is called the global module fragment; its declarations are attached to the global module and are the same entities as those obtained by `#include` elsewhere.
    - Only preprocessing directives can be written in the global module fragment; declarations can enter only through `#include`.
    - Declarations in the global module fragment aren't exported, and importers can't see their names.
    - Declarations the module body doesn't use are discarded, and are neither visible nor reachable outside the module unit; what counts as used is specified by the decl-reachable relation.
    - If the function a dependent call in a template is looking for exists only in the global module fragment, it may have been discarded, and instantiation by an importer then fails.

## Using traditional headers in a module

<div class="compare" markdown="1">

```cpp title="wrong.cppm"
export module M;
#include "legacy.h"
// int parse(const char*);
// this parse is attached to M
export int use() {
  return parse("1");
}
```

```cpp title="right.cppm" ok
module;
#include "legacy.h"
// global module fragment: attached to the global module
export module M;
export int use() {
  return parse("1");
}
```

</div>

Most libraries still ship as headers, while a module unit must begin with a module declaration. If you `#include` after `export module M;` as on the left, the header's declarations are all in M's purview and, by [[module.unit#7]], attached to M. The `parse` on the left is therefore a new function of module M itself, not the same entity as the `::parse` defined in the library ([[basic.link#8]]). In our tests, compiling the left file with Clang 23 produces an object file referring to the symbol `__ZW1M5parsePKc` (`parse@M`), while the library provides `__Z5parsePKc`, so the link fails to find a definition. For the `#include <...>` form, Clang also gives a `-Winclude-angled-in-module-purview` warning.

¶1 The right form puts the `#include` before the module declaration. The part from `module;` to the module declaration is the module unit's **[[g:global-module-fragment|global module fragment]]**. It belongs to the global module ([[module.unit#6]]); its declarations are attached to the global module and are usable as usual in this module unit. It isn't in M's purview, so `export` can't be written here ([[module.interface#1]]).

```text
global-module-fragment:
    module-keyword ; declaration-seq(opt)
```

### Only preprocessing directives

[[cpp.pre#5]] specifies that at the start of translation phase 4, the global module fragment may contain neither ordinary text lines nor `import` directives. So only preprocessing directives such as `#include`, `#define` and `#if` can be written here, and declarations can enter only through `#include`.

<div class="compare" markdown="1">

```cpp title="ok.cppm" ok
module;
#define _GNU_SOURCE
#include <cstdio>
export module M;
```

```cpp title="bad.cppm" error
module;
void f();
// error: a text line in
// the global module fragment
export module M;
```

</div>

The global module fragment is only a compatibility layer serving `#include`. The proper way to declare entities of the global module in a module is `extern "C++"` ([[module.unit#7]]); imports should be written in the module purview ([[module.import#1]]).

!!! impl "Clang doesn't diagnose text lines"
    In our tests Clang 23 gives no diagnostic at all for the `bad.cppm` on the right, even with `-Wall -Wextra -pedantic`. [[cpp.pre#5]] is a diagnosable rule, so this is a nonconformance in Clang. For portable code, put only preprocessing directives in the global module fragment.

## Declarations in the global module fragment aren't exported

Declarations in the global module fragment aren't in any *export-declaration*, so they aren't exported. Importers' name lookup can't find them:

```cpp title="lib.h"
#pragma once
namespace lib {
  struct Used { int v = 1; };
  inline int helper(Used u) { return u.v; }
}
```

```cpp title="L.cppm"
module;
#include "lib.h"
export module L;
export lib::Used make() { return {}; }
```

```cpp title="user.cpp" error
import L;
int main() {
  auto u = make();       // OK
  int a = u.v;           // OK: lib::Used's definition is reachable, and member lookup only needs the definition to be reachable
  return helper(u) + a;  // error: lib::helper isn't visible
}
```

Argument-dependent lookup for `helper(u)` (ADL, which looks up functions in the namespaces of the argument types) goes into `lib`, but `lib::helper` is attached to the global module and not exported, so it isn't visible to `user.cpp`. Clang 23 reports "use of undeclared identifier 'helper'".

For an importer to use `lib::helper`, module L can write `export using lib::helper;` ([[module.interface#5]]), or the importer can `#include "lib.h"` itself.

## Unused declarations are discarded

A module's global module fragment may contain hundreds of thousands of lines of system headers, of which the module actually uses only a small part. ¶3 specifies that a declaration D in the global module fragment that isn't used by any declaration in the module body is **[[g:discarded-declaration|discarded]]**. The precise meaning of "used" is decl-reachable, in the next section.

Note 2 explains the effect of discarding: a discarded declaration is neither reachable nor visible outside the module unit. If a template's point of instantiation ([[temp.point]]) is outside the module unit, a discarded declaration is neither reachable nor visible in the instantiation, even if the instantiation context ([[module.context]]) includes the module unit.

Discarding has two purposes:

- The compiler needn't write discarded declarations into the BMI (binary module interface, the interface information the compiler caches for importers), so interface files are smaller.
- Importers don't accidentally depend on headers the module happens to include, for example by finding some function through ADL or by having some type become complete. Otherwise a module author removing one `#include` could break importers.

The standard's Example 2 shows the effect of discarding:

```cpp title="foo.h"
namespace N {
  struct X {};
  int d();
  int e();
  inline int f(X, int = d()) { return e(); }
  int g(X);
  int h(X);
}
```

```cpp title="M.cppm (interface unit of module M)"
module;
#include "foo.h"
export module M;
template<typename T> int use_f() {
  N::X x;                       // N::X, N and :: are decl-reachable from use_f
  return f(x, 123);             // N::f is decl-reachable from use_f;
                                // N::e and N::d are decl-reachable from N::f, and hence from use_f,
                                // even though this call doesn't use the default argument
}
template<typename T> int use_g() {
  N::X x;                       // N::X, N and :: are decl-reachable from use_g
  return g((T(), x));           // N::g is not decl-reachable from use_g
}
template<typename T> int use_h() {
  N::X x;                       // N::X, N and :: are decl-reachable from use_h
  return h((T(), x));           // N::h is not decl-reachable from use_h, but...
}
int k = use_h<int>();           // use_h<int> is decl-reachable from k,
                                // N::h is decl-reachable from use_h<int>, so N::h isn't discarded
```

```cpp title="M-impl.cpp (implementation unit of module M)" error
module M;
int a = use_f<int>();           // OK
int b = use_g<int>();           // error: g can't be found; it was discarded
int c = use_h<int>();           // OK
```

The point of instantiation of `use_g<int>` is in the implementation unit; `g((T(), x))` is a dependent call that relies on ADL to find `g` in `N`. No declaration in the interface unit uses `N::g`, so it was discarded and isn't visible in the implementation unit. `N::h`, on the other hand, is kept because the instantiation of `int k = use_h<int>();` in the interface uses it.

This also shows how fragile discarding is: delete the seemingly unrelated `int k = use_h<int>();` from the interface, and `use_h<int>()` in the implementation unit fails to compile. Module authors should make sure what templates need is explicitly used, or simply export it.

!!! impl "Clang's two kinds of BMI"
    In our tests with Clang 23, the result of this example depends on how the BMI is produced:

    - A full BMI produced with `--precompile` (about 30 KB) doesn't apply discarding, and `use_g<int>()` is accepted.
    - Producing the object file and BMI in one step with `-c M.cppm -fmodule-output=M.pcm` yields a reduced BMI by default (about 24 KB; `-fno-modules-reduced-bmi` yields a full BMI). It applies discarding, and `use_g<int>()` reports "use of undeclared identifier 'g'", in line with the standard.

    CMake drives Clang the `-fmodule-output` way (see [[toolchain/modules-in-practice]]). The same code behaves differently under different build setups, which is one more reason not to depend on global-module-fragment declarations that aren't explicitly used.

## What counts as used: decl-reachable (¶2)

Discarding requires the compiler to decide, when the module is defined, whether a declaration is used. Templates are the hard part: for a dependent call `g(x)`, what will be called isn't known at definition time. ¶2 gives a conservative relation that can be computed statically at definition time.

### Direct use (¶2.1–¶2.4)

¶2 Within the same TU, a declaration D is [[g:decl-reachable|decl-reachable]] from a declaration S if any of the following holds:

- ¶2.1 D doesn't declare a function or function template, and S contains an *id-expression*, *namespace-name*, *type-name*, *template-name* or *concept-name* naming D.
- ¶2.2 D declares a function or function template that is named by an expression in S (named in the sense of [[basic.def.odr]], that is, selected by overload resolution).
- ¶2.3 S contains a dependent call E ([[temp.dep]]), and D is found by any name lookup performed for the expression synthesized from E by replacing each type-dependent argument or operand with a value of a placeholder type with no associated namespaces or entities. Note 1 adds that this includes the lookups for `operator==`, `operator<=>` and `operator!=` when rewriting comparison operators.
- ¶2.4 S contains an expression that takes the address of an overload set containing D ([[over.over]]) and the target type is dependent, as in `static_cast<T>(&f)`.

Functions are treated differently from everything else. Writing a function name `f` may make name lookup find a whole overload set, and only the one selected counts as used, which lets more useless overloads be discarded.

A dependent call can't undergo overload resolution at definition time, so ¶2.3 does only name lookup and counts everything found. The placeholder type has no associated namespaces, so ADL for the synthesized expression considers only the namespaces brought by non-dependent arguments. In Example 2:

- In `f(x, 123)`, the type of `x` doesn't depend on `T`, so ADL goes into `N` and finds `N::f`.
- In `g((T(), x))`, the comma expression `(T(), x)` is type-dependent (`T` might overload the comma operator), so the whole thing is replaced by a placeholder value; ADL doesn't go into `N` and doesn't find `N::g`.

### Kept along with it (¶2.5)

When a declaration is used, the declarations inseparable from it must be kept too, or it would be incomplete for importers. ¶2.5: if there's a declaration M that isn't a namespace definition and is decl-reachable from S, and any of the following holds, D is also decl-reachable from S:

| Item | Relation between D and M | Example |
|---|---|---|
| ¶2.5.1 | D is decl-reachable from M (transitivity) | `N::e`, used by `N::f` |
| ¶2.5.2 | D and M declare the same entity, and D isn't a friend declaration and doesn't inhabit a block scope | a function's forward declaration and its definition |
| ¶2.5.3 | D declares a namespace N, and M is a member of N | the enclosing `N` and `::` |
| ¶2.5.4 | one declares a class C, the other a member or friend of C | class and members, both directions |
| ¶2.5.5 | one declares an enumeration E, the other an enumerator of E | enumeration and enumerators, both directions |
| ¶2.5.6 | D declares a function or variable, and M is declared within D | a local class in a function body, declarations in a lambda in a variable's initializer |
| ¶2.5.7 | one declares a template, the other a partial specialization, explicit specialization or instantiation of it | `use_h<int>` in Example 2 |
| ¶2.5.8 | M declares a class template, and D is a deduction guide for it | |
| ¶2.5.9 | one declares a class or enumeration type, the other introduces a typedef name for linkage purposes for it | `typedef struct { ... } P;` |

¶2.5 requires that M not be a namespace definition. A definition like `namespace std { ... }` contains the declarations of all its members; if M could be a namespace definition, as soon as one member were used, the whole contents of the namespace would be pulled in through the enclosing namespace, and discarding would be useless. So from a member you can only go one way, to the enclosing namespace (¶2.5.3), and can't spread out again from the namespace.

### Left to the implementation (¶2.6–¶2.10)

In making the determinations above, it is unspecified whether the following replacements happen first:

- ¶2.6 whether references to alias declarations, typedefs, using-declarations and namespace aliases are first replaced by the declarations they name;
- ¶2.7 whether an alias template specialization that doesn't denote a dependent type is first replaced by the type it denotes;
- ¶2.8 whether a `decltype` that doesn't denote a dependent type is first replaced by the type it denotes;
- ¶2.9 whether a constant expression that isn't value-dependent is first replaced by the result of its evaluation;
- ¶2.10 whether a splice ([[basic.splice]]) in a non-dependent context is first replaced by the construct it designates.

When building the syntax tree, compilers often have already replaced aliases, `decltype` and constant expressions with what they denote. For example, the type of `int a[size];` might be recorded directly as `int[2]`, and tracing back to the reference to `size` would require keeping extra information. The standard doesn't force implementations to keep it, at the cost that determinations depending on these references may differ between implementations. The standard's Example 1:

```cpp
const int size = 2;
int ary1[size];                 // unspecified whether size is decl-reachable from ary1 (¶2.9)
constexpr int identity(int x) { return x; }
int ary2[identity(2)];          // unspecified whether identity is decl-reachable from ary2

template<typename> struct S;
template<typename, int> struct S2;
constexpr int g(int);

template<typename T, int N>
S<S2<T, g(N)>> f();             // S, S2, g and :: are decl-reachable from f
                                // g(N) is value-dependent and isn't replaced

template<int N>
void h() noexcept(g(N) == N);   // g and :: are decl-reachable from h
```

### Where it starts (¶3)

¶3 In determining whether something is discarded, the starting points are the declarations in the TU's *declaration-seq*. By the grammar of *translation-unit*, that's the part after the module declaration and before the private module fragment.

- Declarations within the global module fragment referring to each other don't count.
- Declarations used only by the private module fragment are discarded. That's no problem: the private module fragment isn't reachable from other TUs anyway, and discarded declarations remain usable within this module unit.
- Only the global module fragment of a module unit discards declarations; ordinary TUs discard nothing.

[[basic.lookup.argdep#4]] works together with this: ADL for dependent names looks from every point in the instantiation context, but ignores declarations that appear in another TU, are attached to the global module, and are either discarded or have internal linkage.

## Implementation view

!!! impl "The global module fragment and the ODR"
    Inline functions, class definitions and so on brought in by `#include` in the global module fragment are the same entities as those other TUs get through `#include`, and must obey the ODR requirement that multiple definitions be identical ([[basic.def.odr]]). If a module's global module fragment includes some header with `NDEBUG` defined, and another TU includes it without `NDEBUG`, there are two different definitions of an inline function, which is IFNDR just as with traditional headers (a rule with no diagnostic required has been violated, and the program has no guarantees).

    When importing several BMIs, the compiler has to merge the definitions of the same global-module entity in them, which gives it a chance to catch violations that headers alone wouldn't reveal. An experiment in our tests: module A's global module fragment includes `cfg.h` after `#define BIG` (giving `struct Cfg { long v; }`), and module B includes it without defining `BIG` (giving `struct Cfg { int v; }`). Accessing `a().v` in a TU that imports both A and B, Clang 23 reports "reference to 'v' is ambiguous" and lists both `Cfg::v` as candidates. Per the standard this is IFNDR; such a diagnostic is just a bonus.

## History

!!! history
    - The global module fragment comes from the Modules TS; C++20's [[P1103R3]] required it to begin with `module;`, so a file can be recognized as a module unit from its first line without parsing. For design background, see [[history/modules]].
    - The decl-reachable and discarding rules also come from the C++20 merged design and have been corrected several times since, for example the lookups when rewriting comparison operators in note 1, and ¶2.10, added with C++26 reflection.

## Common misconceptions

!!! pitfall "Importers can use names from a module's global module fragment"
    They can't; those names aren't exported. Importers should `#include` or `import` what they need themselves.

!!! pitfall "An exported template makes a dependent call whose target exists only in the global module fragment"
    That's `use_g` in Example 2: the module body never uses `N::g` in a non-dependent way, so it is discarded and can't be found when instantiated outside the module. The fix is to make it used within the module (for example with `using N::g;`), or to call it non-dependently.

## Questions

!!! question "Question 1"
    The global module fragment contains `struct P { int x; }; struct Q { P p; };`, and the module body has only `export Q make();`. Is `P` discarded?

<details markdown="1">
<summary>Answer</summary>

No. `Q` is decl-reachable from `make` (¶2.1: a *type-name* names `Q`). By ¶2.5.4, the declaration of the member `p` is also decl-reachable; the declaration of `p` contains the *type-name* `P`, so by ¶2.1 and ¶2.5.1, `P` is decl-reachable too. Intuitively it has to be: an importer using `Q` needs to know its layout, which in turn needs `P` to be a complete type.
</details>

!!! question "Question 2"
    Why does ¶2.2 count only the selected function as used, while ¶2.3 counts every declaration found by name lookup for a dependent call?

<details markdown="1">
<summary>Answer</summary>

A non-dependent call completes overload resolution at the point of definition, so the selected function is fixed, and the other overloads can never be used by this call; they can safely be discarded. Overload resolution for a dependent call is deferred to instantiation, when any of the candidates found by name lookup might be selected; they can't be ruled out at definition time and must all be kept. Candidates findable only through ADL on dependent arguments aren't among them, though, since the placeholder type has no associated namespaces; this part is deliberately excluded, and it's up to the module author to make sure they are used.
</details>
