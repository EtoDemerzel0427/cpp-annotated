---
title: The inline specifier
summary: "The binding meaning of inline in the standard is that each of several translation units may have its own identical definition, while they remain one entity with one address; inline expansion is only a non-binding hint. This page also covers inline variables, what is implicitly inline, and how the linker handles these definitions."
updated: 2026-10-19
---

!!! tldr
    - An inline function or inline variable may have a definition in each of several translation units (the definitions must be the same); in the whole program it is still one entity with one address, and its static local variables exist only once.
    - `inline` doesn't change linkage; the part asking the compiler to expand calls inline is only a hint that implementations may ignore.
    - You can't give a non-inline definition first and add an inline declaration afterwards; one translation unit treating something as inline while another doesn't is an error with no diagnostic required.
    - Member functions defined in a class definition, constexpr functions, and `static constexpr` data members are implicitly inline; function templates are not inline, and their explicit specializations need an explicit `inline` when placed in a header.
    - The linker keeps one of the definitions by name without comparing contents, so inconsistent definitions don't cause an error.

## What inline really means

```cpp title="counter.h"
inline int next_id() {
    static int n = 0;          // only one n in the whole program
    return ++n;
}
inline int global_config = 42; // C++17: only one global_config in the whole program
```

```cpp title="a.cpp"
#include "counter.h"
int* addr_a() { return &global_config; }
int call_a() { return next_id(); }
```

```cpp title="b.cpp"
#include "counter.h"
#include <cassert>
int* addr_a();
int call_a();
int main() {
    assert(addr_a() == &global_config);  // the same address
    call_a();
    assert(next_id() == 2);              // both TUs share the same static local variable
}
```

`counter.h` is included by two translation units (TUs: a separately compiled source file together with the headers it includes), so `next_id` and `global_config` each have a definition on both sides. Without `inline`, linking fails with duplicate definitions; with `inline`, the program runs normally and both assertions hold. Verified by compiling and running with Clang 23.

¶2 A function declaration with `inline` declares an **inline function** ([[g:inline-function]]), and a variable declaration with `inline` declares an **inline variable** ([[g:inline-variable]]). Their key property is stated in Note 1:

!!! std
    An inline function or variable with external or module linkage can be defined in multiple translation units, but is one entity with one address.

An inline function or variable with external or module linkage may be defined in multiple TUs ([[basic.def.odr]] requires these definitions to be the same), but it is still just one entity with only one address. Note 1 goes on to conclude that types and static variables defined in the body of such a function also exist only once. This is what makes a Meyers singleton (a `static` local object inside a function) in a header work correctly.

Putting function definitions in headers needs exactly these semantics. C++17 extended them to variables ([[P0386R2]]), which also shows that `inline` has long stopped being an optimization hint: inline expansion of a variable is meaningless.

### inline doesn't change linkage (¶2 Note 2)

`inline void f();` still has external linkage; `static inline void f();` has internal linkage, each TU has its own `f`, and the problem of multiple definitions doesn't arise.

Note 2 also points out that an inline function sometimes can't use names with internal linkage ([[basic.link]]). A module interface can't expose entities that belong only to its own TU; and if an inline function in a header refers to a `static` variable, the definitions in different TUs refer to different objects, so the definitions are no longer the same:

```cpp ifndr
// header.h
static int helper_state = 0;                    // one per TU
inline int bump() { return ++helper_state; }    // refers to a different object in each TU: violates the ODR
```

A program that violates the ODR like this is **ill-formed, no diagnostic required** (IFNDR): the compiler and linker may give no indication at all, and the program has no guarantees.

### Inline expansion is only a hint (¶3)

¶3 says that `inline` indicates to the implementation that inline substitution of the function body at the point of call is preferred to the usual call. The implementation need not perform it; even if it doesn't, the other rules for inline functions still apply.

Real optimizers inline any function they consider suitable, including non-inline functions, and refuse to inline inline functions they consider unsuitable. GCC and Clang treat `inline` only as a very weak heuristic signal. To force or forbid inlining, use implementation extensions: `[[gnu::always_inline]]`, `[[gnu::noinline]]`, MSVC's `__forceinline`.

## Where it can appear (¶1)

```cpp error
inline struct T { };         // error: declares no variable or function
void g() {
    inline int x = 0;        // error: block scope
}
void h(inline int);          // error: parameter
```

¶1 `inline` can only be used in the declaration of a function or variable; it can't appear on a block-scope declaration or be applied to a parameter. `inline struct S { int v; } s;` is valid, because `inline` applies to the variable `s`.

A variable at block scope is either a local variable defined only once right there, so multiple definitions across TUs don't come up, or an `extern` declaration referring to some variable outside. A block-scope function declaration also always refers to a function outside. In those last two cases, `inline` belongs on the entity's own declaration.

The last sentence of ¶1 says that if a friend function declaration has `inline`, it must be a definition or the function must have been previously declared inline. `struct S { friend inline void f(); };` may be the first declaration of `f`; it makes `f` an inline function, so every TU that uses `f` must have a definition of `f` (see the next section), and this obligation, hidden inside a class, is easily overlooked. Clang 23 doesn't check this rule (see [[dcl.friend]]).

## inline first, definition later (¶4)

<div class="compare" markdown="1">

```cpp run ok
inline void f();   // declared inline first
void f() { }       // OK: the definition need not repeat it
void g();
inline void g() { }
// OK: the first inline declaration is the definition
int main() { f(); g(); }
```

```cpp error
void f() { }
inline void f();
// error: the definition is already reachable
int v = 1;
inline int v;
// error: likewise (also a redefinition)
```

</div>

The first rule of ¶4: if a definition of a function or variable is reachable at the point of its first declaration as inline, the program is ill-formed. Having seen a non-inline definition, the compiler may already have emitted it as an ordinary external definition that exists only once, and a later inline declaration can't undo that decision.

The second rule concerns multiple TUs. First a term: a **definition domain** is the part of a TU outside its private module fragment, or the private module fragment itself ([[basic.def.odr#13]]); without modules, a TU is one definition domain. If a function or variable with external or module linkage is declared inline in one definition domain, an inline declaration of it must be reachable from the end of every definition domain in which it is declared. Violating this requires no diagnostic {{ifndr}}: TU A thinks `f` is inline, TU B thinks it isn't, and compiling either TU alone reveals no problem.

Note 3 points out that within a TU an inline function can be called before its definition appears, as long as the definition is reachable from the end of the definition domain ([[basic.def.odr#13]]):

```cpp run ok
inline int twice(int);
int use() { return twice(21); }     // OK: the definition comes later
inline int twice(int x) { return 2 * x; }
int main() { return use() - 42; }
```

## inline in modules (¶5)

¶5 An inline function or variable attached to a named module must be defined in the definition domain in which it is declared.

Note 4 recalls two rules about implicit inline: constexpr functions are implicitly inline ([[dcl.constexpr#1]]); a function defined in a class definition is implicitly inline only in the global module (i.e. when it isn't attached to any named module) ([[class.mfct#1]], [[class.friend#6]]).

So since C++20, in `export struct S { void f() { … } };` in a named module interface, `f` is not inline. A module interface can compile the function body just once, in the module's own object file; if functions defined in a class were automatically inline, importers would have to see and inline the body, and changing the body would affect every importer, defeating the module goal of separating interface from implementation. When you want inline, write it explicitly in the module.

## What is implicitly inline

| Entity | Inline? | Basis |
|---|---|---|
| Member function defined in a class definition (global module) | Yes | [[class.mfct#1]] |
| Friend function defined in a class definition (global module) | Yes | [[class.friend#6]] |
| Member or friend function defined in a class definition, in a named module | No | Same as above |
| `constexpr` and `consteval` functions | Yes | [[dcl.constexpr#1]] |
| Static data member whose first declaration has `constexpr` | Yes | [[dcl.constexpr#1]] |
| `constexpr` variable at namespace scope | No (but const variables have internal linkage by default) | [[basic.link#3]] |
| Non-constexpr static data member such as `static const int` | No | [[class.static.data]] |
| Deleted function (`= delete`) | Yes | [[dcl.fct.def.delete#4]] |
| Function explicitly defaulted on its first declaration (`= default`) | Yes | [[dcl.fct.def.default#3]] |
| Implicitly declared special member function | Yes | [[class.default.ctor]], [[class.copy.ctor]], [[class.dtor]], etc. |
| Function call operator of a non-generic lambda | Yes | [[expr.prim.lambda.closure#5]] |
| Function templates, variable templates | No (the ODR has a separate exemption for templates) | [[basic.def.odr]] |

The last row is often misunderstood. Function templates can go in headers because the ODR allows templates to be defined in multiple TUs, not because they are inline. An explicit specialization `template<> void f<int>() { }` is an ordinary function that no longer enjoys the template exemption; if it is in a header included by multiple TUs, it needs `inline`:

```cpp title="spec.h"
template<class T> void describe() { }            // template: may be defined in multiple TUs
template<> inline void describe<int>() { }       // explicit specialization: needs inline to go in a header
```

## How the linker handles multiple definitions

!!! impl "COMDAT and vague linkage"
    For every inline function or variable that is used, the compiler emits a definition in each TU's object file and marks it mergeable, and the linker keeps one of them:

    - ELF (Linux): each inline entity goes into a COMDAT group, with `WEAK` symbols; only one group with a given name is kept.
    - Mach-O (macOS): `nm -m` shows it as `weak external`.
    - LLVM IR: the linkage type is `linkonce_odr`. `linkonce` means it can be discarded if unreferenced, and `odr` means the compiler may assume all definitions are equivalent, so it can inline the body from any one of them.
    - COFF (Windows): a COMDAT section with selection `IMAGE_COMDAT_SELECT_ANY`.

    The GCC documentation calls this scheme, where something may appear in several object files and the linker deduplicates it, vague linkage; inline functions, template instantiations, vtables and `type_info` objects are all handled this way.

    Below are the COMDAT groups for `inline int counter`, `inline int next()` and its static local variable in an x86-64 ELF object file (compiled with Clang 23 `--target=x86_64-linux-gnu`, excerpt of `llvm-readelf -g` output):

    ```text
    COMDAT group section [    4] `.group' [_Z4nextv] contains 2 sections:
       [    5]   .text._Z4nextv
    COMDAT group section [    7] `.group' [_ZZ4nextvE1n] contains 1 sections:
       [    8]   .bss._ZZ4nextvE1n
    COMDAT group section [    9] `.group' [counter] contains 1 sections:
       [   10]   .bss.counter
    ```

    An inline variable with dynamic initialization also gets an equally mergeable guard variable (in the Itanium ABI its mangled name starts with `_ZGV`), which ensures the variable is initialized only once even if several TUs carry initialization code.

!!! warning "The linker doesn't report inconsistent definitions"
    If an inline function's definitions differ between two TUs (for example because of different macros), the program is IFNDR. The linker just keeps one by name, usually the first it encounters, without comparing contents. The result may be that one TU has version A expanded inline while another TU calls and gets version B, which is extremely hard to debug. With `-flto`, GCC's `-Wodr` can catch some of these.

!!! warning "Shared libraries"
    One entity, one address is the standard's guarantee for a single program, and the standard doesn't know shared libraries exist. On Windows, each DLL by default has its own copy of inline variables and static local variables; on ELF, options such as `-fvisibility=hidden` or `-Bsymbolic` can also produce multiple copies. Don't rely on the uniqueness of inline variables to share state across shared libraries.

!!! history "History"
    - C++98: `inline` is a function specifier, alongside `virtual` and `explicit`; the main rule is that every TU that uses an inline function must have its definition.
    - C++11: constexpr functions are implicitly inline.
    - C++17: inline variables ([[P0386R2]]); `inline` is no longer a function specifier; `static constexpr` data members are implicitly inline, fixing the old problem that an in-class-initialized `static const` member that is odr-used also needs an out-of-class definition.
    - C++20: modules; functions defined in a class in a named module are no longer implicitly inline; the rules formerly phrased per TU are rephrased in terms of definition domains and reachability.

!!! pitfall "Common misconceptions"
    - inline makes a function get inlined: it neither guarantees this nor is that its main meaning.
    - Inline functions have internal linkage: they don't; `inline` doesn't affect linkage.
    - `static inline` is the same as `inline`: it isn't; a `static inline` function exists once per TU, each with its own address and static local variables.
    - Function templates are implicitly inline: they aren't; they enjoy the template's own ODR exemption, and explicit specializations need `inline` written explicitly.
    - constexpr variables at namespace scope are inline: they aren't; only static data members are.

!!! question "Question 1"
    A header has `const std::string kName = "x";` at namespace scope and is included by 100 TUs. What happens? What about `inline const std::string kName = "x";`?

<details markdown="1">
<summary>Answer</summary>

const variables have internal linkage by default ([[basic.link#3]]), so each TU has its own `kName`, each dynamically initialized at startup. The result is 100 objects, 100 constructions and destructions, all with different addresses. With `inline` it has external linkage: the whole program has one object, a guard variable ensures it is initialized only once, and all TUs see the same address.
</details>

!!! question "Question 2"
    Why might `struct S { static const int N = 10; }; const int& r = S::N;` fail to link in C++14, while in C++17 replacing `const` with `constexpr` fixes it?

<details markdown="1">
<summary>Answer</summary>

The in-class declaration of a non-inline static data member is not a definition (item 2.3 of [[basic.def#2]]). Binding the reference `r` to `S::N` odr-uses it and needs a definition; without `const int S::N;` in the program, the linker can't find the symbol. Since C++17 `static constexpr int N = 10;` is implicitly inline ([[dcl.constexpr#1]]), so the in-class declaration is a definition and each TU emits a mergeable definition. In C++17 `static const int N = 10;` is still not inline, and the problem remains.
</details>
