---
title: Private module fragment
summary: "module :private; lets a module consisting of a single file still hide implementation details from importers; everything importers need must be written before it."
updated: 2026-10-19
---

!!! tldr
    - `module :private;` splits a module interface unit in two: the part before it affects importers, and the part after it is used only to generate this module's object code and isn't reachable from importers.
    - The private module fragment can appear only in a primary module interface unit, and the module can have no other units (no diagnostic required for violations).
    - The definitions of inline functions, templates and exported functions whose return type is deduced must all be written before the private module fragment.
    - Declarations in the private module fragment aren't subject to exposure checks and can freely use entities usable only in this TU, such as `static` functions.
    - The typical uses are single-file modules and opaque handles: export an incomplete type and put its definition in the private module fragment.

## Separating interface and implementation in one file

```cpp title="handle.cppm"
export module handle;
export struct Handle;                    // export an incomplete type
export Handle* make();
export int value(const Handle*);
export void destroy(Handle*);
module :private;
struct Handle { int v = 42; };           // not reachable from importers
Handle* make() { return new Handle; }
int value(const Handle* h) { return h->v; }
void destroy(Handle* h) { delete h; }
```

<div class="compare" markdown="1">

```cpp title="main.cpp" ok
import handle;
int main() {
  Handle* h = make();
  int r = value(h) - 42;
  destroy(h);
  return r;
}
```

```cpp title="peek.cpp" error
import handle;
int n = sizeof(Handle);
// error: Handle's definition
// isn't reachable
```

</div>

Traditional C++ separates interface and implementation with a header plus a source file. Modules can do the same: the primary interface unit holds the declarations, an implementation unit (`module M;`) the definitions. But for a small module, two files are an unnecessary burden, especially when you just want to turn one `.cpp` file into a module.

The [[g:private-module-fragment|private module fragment]] lets one file play both roles. The contents after `module :private;` are still in the module's purview and still attached to this module, but aren't reachable from other TUs ([[module.reach#3]]). `main.cpp` above runs normally and returns 0; `peek.cpp` can't see the definition of `Handle`, and Clang 23 reports "'Handle' must be defined before it is used", with the note "definition here is not reachable".

```text
private-module-fragment:
    module-keyword : private ; declaration-seq(opt)
```

## Only for single-file modules (¶1)

¶1 A private module fragment can appear only in a primary module interface unit ([[module.unit#2]]). A module unit with a private module fragment must be the only unit of its module; no diagnostic is required for violations ({{ifndr}}).

```cpp title="P-part.cppm" error
export module P:part;
module :private;          // error: the private module fragment can appear only in a primary module interface unit
```

Clang 23 reports "private module fragment declaration with no preceding module declaration" for this. Rejecting it is right, though the wording isn't quite accurate.

The uniqueness requirement exists because the private module fragment is designed for single-file modules. If the module had an implementation unit, that unit would implicitly import the primary interface ([[module.unit#8]]) and should see everything in it, yet the contents of the private fragment wouldn't be reachable from it, giving inconsistent views within the same module. Besides, an implementation unit can already hold the implementation details, so there'd be no need for the private fragment.

The compiler sees only one TU at a time and can't discover the module's other units, so this rule can only be no-diagnostic-required. In our tests Clang 23 gives no diagnostic when compiling a `module A2;` implementation unit whose primary interface has a private fragment.

## Everything importers need comes before it (¶2)

¶2 Note 1 explains that the private module fragment ends the part of the module interface unit that can affect the behavior of other TUs. Its presence affects the following six things, whose normative rules are scattered around the standard:

| | Rule affected | What it says |
|---|---|---|
| ¶2.1 | the point by which inline functions and variables must be defined | an inline entity attached to a named module must be defined in the definition domain where it is declared ([[dcl.inline#5]]); the private fragment is a separate definition domain ([[basic.def.odr#13]]) |
| ¶2.2 | the point by which exported functions with a deduced return type must be defined | they must be defined outside the private fragment ([[dcl.spec.auto#12]]) |
| ¶2.3 | whether declarations are required not to be exposures | [[basic.link#17]] checks only declarations outside the private fragment |
| ¶2.4 | where definitions of inline functions and templates must appear | definitions importers need must come before the private fragment ([[basic.def.odr]], [[temp.pre]]) |
| ¶2.5 | the instantiation context of templates instantiated before it | the extra point of instantiation is placed before the private fragment instead of at the end of the TU ([[temp.point#7]], [[module.context#3]]) |
| ¶2.6 | the reachability of declarations in it | not reachable from other TUs ([[module.reach#3]]) |

These rules boil down to one: everything importers see must be written before `module :private;`.

The **[[g:exposure|exposure]]** in ¶2.3 means a declaration that uses a TU-local entity, that is, an entity usable only within this TU (such as a `static` function; see [[basic.link#15]]). Exposures in a module interface are ill-formed, because importers might need that entity and couldn't get it. Declarations in the private fragment aren't reachable from importers, which can never use them, so they needn't be checked.

## Example (¶3)

¶3 The standard's Example 1:

```cpp title="A.cppm" error
export module A;
export inline void fn_e();      // error: exported inline function fn_e not defined before the private fragment
inline void fn_m();             // error: non-exported inline function fn_m not defined before the private fragment
static void fn_s();
export struct X;
export void g(X *x) {
  fn_s();                       // OK: calls a static function in the same TU
}
export X *factory();            // OK

module :private;
struct X {};                    // this definition isn't reachable from importers of A
X *factory() {
  return new X ();
}
void fn_e() {}
void fn_m() {}
void fn_s() {}
```

- `fn_e` and `fn_m` are attached to the named module A and declared in the definition domain before the private fragment, but defined in the private fragment, violating [[dcl.inline#5]]. `fn_m` not being exported doesn't help: the rule looks at attachment, not exporting. Clang 23 reports "inline function not defined before the private module fragment" for both, with the note "private module fragment begins here".
- `g` calls the `static` function `fn_s`. `g` isn't an inline function, so its body is ignored in determining exposure ([[basic.link#14]]), and this isn't an exposure. Importers calling `g` only need its symbol.
- `X` is exported as an incomplete type with its definition in the private fragment, so importers can only use `X*`. This is the pattern of `handle` at the top.
- `factory` is an ordinary function; importers only need its declaration, so the definition can go in the private fragment.

### Exported functions with a deduced return type

```cpp title="auto.cppm" error
export module autom;
export auto deduced();
module :private;
auto deduced() { return 1; }    // error: must be defined outside the private fragment ([dcl.spec.auto]/12)
```

An importer calling `deduced()` needs to know the return type, and the definition in the private fragment isn't reachable from it, so [[dcl.spec.auto#12]] requires the definition to be written outside the private fragment.

!!! impl "Clang deviates"
    In our tests Clang 23 accepts `auto.cppm` without any diagnostic. An importer calling `deduced()` also compiles, and the program returns 1, showing that Clang used the definition in the private fragment. [[dcl.spec.auto#12]] is a diagnosable rule, so this is a nonconformance in Clang.

## Private module fragment vs implementation unit

| | Private module fragment | Implementation unit `module M;` |
|---|---|---|
| Number of files | 1 | at least 2 |
| Do importers need recompiling after the implementation changes | not per the standard; in practice it depends on the toolchain (see below) | no, implementation units produce no BMI |
| Can there be partitions | no, the module has only this one unit | yes |
| Can the implementation use `static` functions from the interface | yes, same TU | no, internal linkage doesn't cross TUs |
| Suits | small modules, turning a single `.cpp` into a module | large modules, parallel compilation |

At the level of the standard, the private fragment doesn't affect the behavior of other TUs. Whether this avoids recompiling importers depends on whether the compiler can produce a byte-for-byte identical BMI (binary module interface, the interface information the compiler caches for importers) when the private fragment changes, and on whether the build system decides staleness by content or by timestamp. The BMI and the object file come from the same file, so a timestamp-based build system will still recompile importers. This is a quality-of-implementation matter.

## History

!!! history
    The private module fragment came into C++20 with [[P1103R3]], so that single-file modules could also separate interface and implementation. The Modules TS had no corresponding facility.

## Common misconceptions

!!! pitfall "constexpr functions can be defined in the private fragment"
    They can't. `constexpr` functions are implicitly inline and, like functions explicitly marked `inline`, must be defined before the private fragment. Member functions defined in a class in a named module aren't implicitly inline ([[class.mfct#1]]), so an ordinary member function declared before the private fragment and defined in it is fine.

!!! pitfall "Template definitions can go into the private fragment"
    If an exported template is defined only in the private fragment, importers can't see the definition when instantiating it and can't use it. Template definitions must be written before the private fragment.

## Questions

!!! question "Question 1"
    In the module below, `get` is defined in the private fragment. Can importers call `S{}.get()`? What if the in-class declaration is changed to `inline int get();`?

    ```cpp
    export module m;
    export struct S { int get(); };
    module :private;
    int S::get() { return 1; }
    ```

<details markdown="1">
<summary>Answer</summary>

Yes. `get` isn't an inline function (it's defined outside the class and not marked `inline`), so importers only need its declaration and symbol; the definition of `S` comes before the private fragment and is reachable. In our tests this compiles and runs with Clang 23.

After changing it to `inline int get();`, `get` is an inline function attached to a named module, declared in the definition domain before the private fragment, so it must be defined there (¶2.1, [[dcl.inline#5]]); defining it in the private fragment is ill-formed.
</details>

!!! question "Question 2"
    In `export inline int api() { return helper(); }`, `helper` is a `static` function. Does moving the definition of `api` into the private fragment fix the exposure problem?

<details markdown="1">
<summary>Answer</summary>

No. The exposure check does ignore declarations in the private fragment (¶2.3), but `api` is an inline function and must be defined before the private fragment (¶2.1). A workable approach is to drop `inline`: write only `export int api();` before the private fragment and put the definition in it. Another is to make `helper` not `static`; with module linkage it is no longer a TU-local entity.
</details>
