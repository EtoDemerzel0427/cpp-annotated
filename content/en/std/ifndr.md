---
title: Ill-formed, no diagnostic required (Annex G)
summary: "Annex G collects all 45 no-diagnostic-required rules of the core language: why compilers are allowed to stay silent about these errors, an example for each, and what Clang 23 actually does."
updated: 2026-10-19
---

!!! tldr
    - IFNDR means the program violates a rule but the standard does not require the compiler to report it. Such a program has no behavioral guarantees at all, even if the offending code never runs.
    - The standard gives up on requiring a diagnostic for four kinds of reasons: several translation units must be seen together, the question itself is undecidable, the names are reserved for the implementation, or implementations' parsers have historically differed.
    - The linker catches only part of it: duplicate definitions of strong symbols, and missing definitions. For entities that may legitimately appear more than once, such as inline functions and template instantiations, the linker picks any one copy without comparing contents.
    - No diagnostic required does not mean diagnostics are forbidden. Compilers often report problems they can see, and modules turn some cross-translation-unit errors into ones that must be diagnosed.
    - Templates account for 14 of the 45 entries, mainly because a template may see different declarations at its definition and at its instantiation.

## An error that never gets reported

The two source files below each compile without complaint, and linking gives no hint either:

```cpp title="tu1.cpp"
inline int f(int x, int y = 2);
inline int f(int x = 1, int y);     // accumulated: f(1, 2)
inline int f(int x, int y) { return x * 10 + y; }
int from1() { return f(); }
```

```cpp title="tu2.cpp" ifndr
#include <cstdio>
inline int f(int x = 3, int y = 4); // accumulated: f(3, 4), different from tu1
inline int f(int x, int y) { return x * 10 + y; }
int from1();
int main() { std::printf("%d %d\n", from1(), f()); }
```

On Clang 23 this prints `12 34`: each translation unit uses its own default arguments. The standard requires the accumulated default arguments of an inline function to be the same everywhere ([[dcl.fct.default#4]]), and this program violates that rule, but the compiler compiles one translation unit (a source file together with the headers it includes) at a time and never gets the chance to notice the two sides disagree.

Rules like this are marked no diagnostic is required in the wording. A program that violates them is **ill-formed, no diagnostic required**, or **IFNDR** for short ([[g:ifndr]]). Per [[intro.compliance.general#2.2]], the standard places no requirements on such a program: the compiler may report an error or not, and whatever the generated program does conforms.

The consequences of IFNDR reach further than UB. UB only removes the guarantees for a run that reaches it; IFNDR is a property of the program text, and the whole program loses its guarantees, whether or not the offending code is executed.

## What Annex G covers (G.1) [ifndr.general]

¶1 Annex G collects the rules in Clause 4 [intro] through Clause 15 [cpp] marked with one of three phrasings: no diagnostic is required, no diagnostic required, and a diagnostic is required only if.

The third phrasing means the rule sometimes requires a diagnostic. For example, the ODR requires the definitions of an inline function in different translation units to be the same; a diagnostic is required only when the entity is attached to a named module and a prior definition is reachable at the point where a later one occurs ([[basic.def.odr#16]]). In that case the compiler can see the earlier definition in the imported module.

Each entry has a stable name with the `ifndr:` prefix, a link to the main text, a summary, and non-exhaustive examples. The annex is informative and the main text governs; the main text marks each rule with `([ifndr:…])` pointing to the corresponding entry. Core language UB has an annex of the same form, Annex F; see [[ub]].

The 45 entries are distributed as: [lex] 1, [basic] 9, [expr] 1, [stmt] 1, [dcl] 9, [module] 4, [class] 2, [over] 1, [temp] 14, [cpp] 3.

## Why no diagnostic is required

Looking at all 45 together, the reasons fall into four categories:

| Category | Reason | Typical entries |
|---|---|---|
| Needs a whole-program view | The violation only exists when several translation units are put together. The compiler sees one translation unit at a time, and the linker sees only symbols, not source code | the ODR entries; language linkage, `alignas`, `[[noreturn]]`, `[[indeterminate]]`, default arguments and contract specifiers inconsistent across translation units; explicit or partial specializations not visible elsewhere; points of instantiation with different meanings |
| Undecidable or too costly | Deciding whether two expressions are equal for all template arguments, or whether a requirement fails substitution for all arguments, is undecidable in general | `temp.over.link.equiv.not.equiv`, `expr.prim.req.always.sub.fail`, constraint satisfaction changing with position |
| Names reserved for the implementation | Standard library headers use these names themselves, and the compiler can hardly tell user code from implementation code | reserved identifiers, reserved module names, reserved literal suffixes |
| Historical differences between implementations | Requiring a diagnostic would force some implementations to rewrite their parser or name lookup | a name changing meaning in class scope, different bindings after statement disambiguation, `defined` produced by macro expansion |

### How much tools can catch

The linker is the last line of defense, and a weak one. Duplicate definitions of non-inline entities are reported as `duplicate symbol`, and missing definitions as `Undefined symbols`. But entities allowed to appear in several object files, such as inline functions, template instantiations and vtables, are emitted as COMDATs (sections deduplicated at link time), and the linker picks any one copy without comparing contents. ODR violations get no hint at all here.

The optimization level affects whether a problem shows up. If the code that calls an undefined function is optimized away, linking succeeds (see [G.3.2](#basic.def.odr.minimum.one.def)). If an inline function is inlined in one translation unit and not in another, the program uses both versions at once.

With LTO, GCC can compare type and vtable definitions across translation units with `-Wodr` (according to the GCC documentation; not verified, as GCC was not available for these tests). Clang performs ODR checks in module scenarios; `clang++ --help` lists switches such as `-fskip-odr-check-in-gmf`. For the traditional build model of headers plus several source files, Clang has no corresponding cross-translation-unit check.

The observations in the entries below all come from Clang 23.1.3 (arm64 macOS, Apple ld).

## Clause [lex]: lexical conventions {#lex}

### G.2.1 Using reserved identifiers {#lex.name.reserved}

`ifndr:lex.name.reserved` · main text [[lex.name#4]]

Identifiers containing a double underscore, and identifiers beginning with an underscore followed by an uppercase letter, are reserved to the implementation everywhere; identifiers beginning with an underscore are reserved in the global namespace. Standard library headers are full of names like `__x` and `_Tp`, and it is hard for the compiler to tell whether a name comes from the user or the implementation, so no diagnostic is required.

```cpp ifndr
int _z;            // IFNDR: starts with _ at global scope

int main() {
  int __x = 0;     // IFNDR: starts with __
  int _Y = 0;      // IFNDR: _ followed by an uppercase letter
  int x__y = 0;    // IFNDR: contains __
  return __x + _Y + x__y + _z;
}
```

By default there is no diagnostic at all, not even with `-Wall -Wextra -pedantic`. Explicitly enabling `-Wreserved-identifier` gives warnings for all four, for example `identifier '_z' is reserved because it starts with '_' at global scope`. See [[lex.name]] for details.

## Clause [basic]: basics {#basic}

### G.3.1 Conflicting declarations of the same entity that are not reachable from each other {#basic.link.consistent.types}

`ifndr:basic.link.consistent.types` · main text [[basic.link#11]]

Multiple declarations of the same entity must agree: if they all declare a variable, the types must be the same; if they all declare a function, the types must be the same; for templates, the template-heads must be equivalent. If two declarations are reachable from each other (in the same translation unit, or via import), the compiler can see them and must diagnose; it is IFNDR only when neither is reachable from the other.

The annex's example is two module interfaces:

```cpp title="M.cppm"
export module M;
void g();                       // #1
void h();                       // #2
template <typename T> int j;    // #3
```

```cpp title="N.cppm"
export module N;
int g();                        // type differs from #1
namespace h {}                  // kind differs from #2
template <int X> int j;         // template-head not equivalent to #3
```

```cpp title="user.cpp" ifndr
import M;
import N;   // annex: the three pairs of declarations conflict, IFNDR
```

!!! lawyer "The annex's example does not hold"
    Per [[basic.link#8]], for two declarations in different translation units to declare the same entity, both must have module or external linkage and be attached to the same module (¶8.3). The `g` in `M` is attached to module `M` and the `g` in `N` to module `N`, so they are two different entities to begin with. For the example to hold, the declarations should be attached to the global module, for example written in two headers included separately by two translation units that do not include each other.

### G.3.2 odr-using a function or variable that has no definition {#basic.def.odr.minimum.one.def}

`ifndr:basic.def.odr.minimum.one.def` · main text [[basic.def.odr#12]]

Every function or variable that is [[g:odr-use|odr-used]] in the program (not counting uses in discarded statements) must have at least one definition. The definition could be in any translation unit, so the compiler cannot diagnose this; the linker usually notices, provided the call actually appears in the object code.

```cpp ifndr
int f();   // never defined

int main(int argc, char**) {
  if (argc > 100 && argc < 50) f();   // never executed, but f is odr-used
}
```

At `-O0`, linking fails (`Undefined symbols for architecture arm64`); at `-O2`, the condition is folded, the call is deleted, and linking succeeds. The same ill-formed program gives different results at different optimization levels, which is exactly why the standard cannot require a diagnostic.

The annex's example is a special case that can be detected from a single translation unit: the function's type involves a local class with no linkage, so it cannot possibly be defined anywhere else. Clang reports it directly as an error:

```cpp error
auto f() {
  struct A {};
  return A{};
}
decltype(f()) g();
auto x = g();   // error (Clang chooses to diagnose): g cannot be defined in any translation unit
```

The diagnostic reads `function 'g' is used but not defined in this translation unit, and cannot be defined in any other translation unit because its type does not have linkage`.

### G.3.3 Defined by an injected declaration in one place and an ordinary definition in another {#basic.def.odr.injected.match}

`ifndr:basic.def.odr.injected.match` · main text [[basic.def.odr#15]]

C++26 static reflection can generate the definition of a class during constant evaluation with functions such as `std::meta::define_aggregate`; this is an **injected declaration** ([[expr.const.reflect]]). If one translation unit defines a class with an injected declaration, the definitions in other translation units must also be injected declarations with the same characteristic sequence.

```cpp title="tu1.cpp"
#include <meta>
struct S;
consteval { std::meta::define_aggregate(^^S, {}); }   // #1: an injected definition
```

```cpp title="tu2.cpp" ifndr
struct S {};   // IFNDR: an ordinary definition here, while #1 is an injected declaration
```

Clang 23 does not support static reflection yet, so this example was not compiled.

### G.3.4 An ordinary function or variable defined in more than one translation unit {#basic.def.odr.maximum.one.def}

`ifndr:basic.def.odr.maximum.one.def` · main text [[basic.def.odr#16.1]]

This is the basic requirement of the ODR: non-inline, non-template functions and variables may have only one definition in the whole program. When the entity is attached to a named module and a prior definition is reachable, a diagnostic is required.

```cpp title="a.cpp"
int x = 1;
int f() { return 1; }
```

```cpp title="b.cpp" ifndr
int x = 2;              // IFNDR: second definition of x
int f() { return 2; }   // IFNDR: second definition of f
int main() {}
```

The linker catches this one: `duplicate symbol '_x'`, `duplicate symbol 'f()'`. It is still IFNDR in order to cover cases the linker cannot see, for example when both definitions are inlined and no symbol is emitted. The annex's example has two module partitions each defining `f()`, with neither definition reachable from the other, which is likewise IFNDR.

### G.3.5 An entity allowed multiple definitions, with the definitions differing {#basic.def.odr.definition.matches}

`ifndr:basic.def.odr.definition.matches` · main text [[basic.def.odr#16.2]]

Inline functions and variables, classes, and templates may each have one definition in several translation units, but the definitions must be the same: the same token sequence, names looked up to the same entities, lambdas producing the same closure types, and so on (the long list of requirements after [[basic.def.odr#16]]).

```cpp title="tu1.cpp"
inline void f() {}          // #1
inline void g() {}          // #2
inline void h() {[]{}();}   // #3
namespace { int i = 0; }
inline void j() {++i;}      // #4
```

```cpp title="tu2.cpp" ifndr
inline void f() {}          // OK: same as #1
inline void g() {;}         // IFNDR: token sequence differs from #2
inline void h() {[]{}();}   // IFNDR: closure type differs from the one in #3
namespace { int i = 0; }
inline void j() {++i; }     // IFNDR: i is an entity in the unnamed namespace of a different translation unit
```

The two definitions of `h` and of `j` are identical character for character and still violate the ODR. Each lambda expression in a non-template inline function produces a unique closure type; the `i` in the unnamed namespace is a different entity in each translation unit.

Linking gives no diagnostic at all; the linker picks any one of the COMDATs. [[intro.compliance]] has a tested example: the same inline function returns different values in two translation units; at `-O0` the result depends on link order, and at `-O2` both versions appear in the same run.

### G.3.6 Unnamed enumerations with the same first enumerator name are not the same type {#basic.def.odr.unnamed.enum.same.type}

`ifndr:basic.def.odr.unnamed.enum.same.type` · main text [[basic.def.odr#20]]

An enumeration with no name and no typedef name for linkage purposes is identified across translation units by the name of its first enumerator. If two such definitions are both reachable somewhere in the program, they must be the same type.

```cpp title="a.h"
enum { a };
```

```cpp title="b.h"
enum { a, b };
```

```cpp title="main.cpp" ifndr
import "a.h";
import "b.h";
auto n = decltype(a)::b;   // IFNDR: two unnamed enumerations whose first enumerators are both named a are reachable, but they are not the same type
```

### G.3.7 Calling va_start in the predicate of a contract assertion {#basic.contract.vastart.contract.predicate}

`ifndr:basic.contract.vastart.contract.predicate` · main text [[basic.contract.general#3]]

The predicate of a C++26 contract assertion may be evaluated zero, one or more times, depending on the evaluation semantic ([[basic.contract.eval]]). Calling a macro such as `va_start`, which changes the function's state, makes no sense there.

```cpp ifndr
#include <cstdarg>

void f(int n, ...) {
  va_list args;
  contract_assert((va_start(args, n), true));   // IFNDR
}
```

Clang 23 does not support contracts yet, so this example was not compiled.

### G.3.8 Replacing the violation handler on a platform where it is not replaceable {#basic.contract.handler.replacing.nonreplaceable}

`ifndr:basic.contract.handler.replacing.nonreplaceable` · main text [[basic.contract.handler#3]]

Whether the contract violation handler `::handle_contract_violation` can be replaced by the program is implementation-defined. On platforms where it cannot, writing a declaration that could serve as a replacement is IFNDR. The same code is valid on one platform and ill-formed on another, so no diagnostic is required.

```cpp ifndr
#include <contracts>
void handle_contract_violation(const std::contracts::contract_violation& violation);
// if the handler is not replaceable: IFNDR
```

### G.3.9 A name in a class changes meaning once the class is complete {#class.member.lookup.name.refers.diff.decl}

`ifndr:class.member.lookup.name.refers.diff.decl` · main text [[class.member.lookup#6]]

The declaration found when a name N is used somewhere in a class definition must be the same as the result of looking up N in the class's complete-class context ([[g:complete-class-context]], such as a member function body). Otherwise the same name means different things in the first and second halves of the class. Checking this requires looking up every used name again at the end of the class, so no diagnostic is required.

```cpp ifndr
struct foo {};

struct bar {
  foo* m_foo;
  foo* foo() { return m_foo; }   // IFNDR: the foo in the return type is ::foo,
                                 // but in the complete scope of bar, foo is the member function bar::foo
};
```

```cpp ifndr
struct B { static int f(); };

struct D : public B {
  using B::f;
  int g(decltype(f()) x) { return 0; }   // IFNDR: here f() is B::f(), of type int,
  static float f();                       // but in the complete scope of D, f() selects D::f(), of type float
};
```

Clang diagnoses neither example. GCC reports a changes meaning error for the first case (based on GCC's known behavior; not verified here); both implementations conform.

## Clause [expr]: expressions {#expr}

### G.4.1 A requirement fails substitution for every template argument {#expr.prim.req.always.sub.fail}

`ifndr:expr.prim.req.always.sub.fail` · main text [[expr.prim.req.general#5]]

If a requirement in a *requires* expression would fail substitution whatever the template arguments are, the program is IFNDR. This follows the same idea as the rule that a template definition for which no valid specialization exists ([[temp.res.general]]): the compiler may report it early, or not.

```cpp ifndr
template <typename T> concept C = requires {
  new int[-(int)sizeof(T)];   // IFNDR: the array length is always negative
};
```

Clang does not diagnose it, and `static_assert(!C<int>)` passes: for a concrete argument, substitution failure just makes the requirement unsatisfied.

## Clause [stmt]: statements {#stmt}

### G.5.1 Names in template arguments bound differently before and after disambiguation {#stmt.ambig.bound.diff.parse}

`ifndr:stmt.ambig.bound.diff.parse` · main text [[stmt.ambig#3]]

When a statement could be either an expression statement or a declaration, the compiler first does a tentative, purely syntactic parse, and once it has determined that the statement is a declaration, parses it for real ([[stmt.ambig]]). If, in the real parse, a name in a template argument binds to the very declaration being parsed, while in the tentative parse it bound to something else, the program is IFNDR.

```cpp ifndr
template <int N> struct A { const static int a = 20; };
template <> struct A<100> { using a = char; };

const int x = 10;

int main() {
  using T = const int;
  T(x)
  (100), (y)(A<x>::a);   // IFNDR: in the tentative parse, the x in A<x> is the global x (10);
                         // in the real parse it is the local x (100) just declared on this line
}
```

Clang accepts this code, with only unused-variable warnings.

## Clause [dcl]: declarations {#dcl}

### G.6.1 constinit not on the initializing declaration {#dcl.constinit.specifier.not.reachable}

`ifndr:dcl.constinit.specifier.not.reachable` · main text [[dcl.constinit#1]]

If `constinit` appears on any declaration of a variable, it must appear on its **initializing declaration** (the one with the initializer). Only at the initializing declaration can the compiler check that the initialization is constant initialization; an `extern` declaration with `constinit` in another translation unit is invisible from the initializing declaration.

```cpp title="tu1.cpp"
int x = 5;   // initializing declaration of x, without constinit
```

```cpp title="tu2.cpp" ifndr
#include <cstdio>
extern constinit int x;   // IFNDR: the declaration with constinit is not reachable from the initializing declaration
int main() { std::printf("%d\n", x); }
```

Neither compiling nor linking gives a diagnostic, and the program prints `5`.

### G.6.2 Declared inline in one place but not in another {#dcl.inline.missing.on.definition}

`ifndr:dcl.inline.missing.on.definition` · main text [[dcl.inline#4]]

If a function or variable with external or module linkage is declared inline in some definition domain ([[g:definition-domain]], roughly a translation unit), then an inline declaration of it must be reachable at the end of every definition domain in which it appears.

```cpp title="tu1.cpp"
inline int f();
int g() { return f(); }
```

```cpp title="tu2.cpp" ifndr
#include <cstdio>
int f() { return 17; }   // IFNDR: no inline declaration of f is visible at the end of this translation unit
int g();
int main() { std::printf("%d\n", g()); }
```

tu1 gets a warning `inline function 'f' is not defined [-Wundefined-inline]`. Linking succeeds and the program prints `17`: tu1 needs an `f` symbol, and tu2 happens to provide an ordinary strong symbol.

### G.6.3 The accumulated default arguments of an inline function differ {#dcl.fct.default.inline.same.defaults}

`ifndr:dcl.fct.default.inline.same.defaults` · main text [[dcl.fct.default#4]]

This is the example at the top of the page. Default arguments are substituted by the caller at the call site, and when they differ between translation units the function itself has no way of knowing, so the program prints `12 34`.

### G.6.4 First declarations in different translation units have different contract specifiers {#dcl.contract.func.mismatched.contract.specifiers}

`ifndr:dcl.contract.func.mismatched.contract.specifiers` · main text [[dcl.contract.func#4]]

A redeclaration in the same translation unit must have the same `pre` and `post` as the reachable first declaration, and that can be diagnosed. The first declarations in different translation units must also agree with each other, which the compiler cannot check unless they are attached to a named module.

```cpp title="tu1.cpp"
int f(int x) pre(x >= 0);   // IFNDR: the first declaration elsewhere has no pre
int g(int x) pre(x == 0);   // IFNDR: differs from the pre elsewhere
int h(int x) pre(x <= 0);   // OK
```

```cpp title="tu2.cpp" ifndr
int f(int x);
int g(int x) pre(x != 0);
int h(int y) pre(y <= 0);   // OK: different parameter names do not affect equivalence
```

Clang 23 does not support contracts yet, so this example was not compiled.

### G.6.5 A nonconforming replacement for a replaceable function {#dcl.fct.def.replace.bad.replacement}

`ifndr:dcl.fct.def.replace.bad.replacement` · main text [[dcl.fct.def.replace#1]]

The program may provide its own definitions for **replaceable functions** ([[g:replaceable-function]]) such as `operator new`, `operator delete` and the contract violation handler. A replacement must not be inline, must be attached to the global module, must have C++ language linkage and the correct return type; if a standard library header has a corresponding declaration, the replacement must be a valid redeclaration of it. Replacement happens at link level, and when compiling a single file the standard library's declaration may not be visible.

```cpp ifndr
#include <new>
#include <contracts>

extern "C"   // IFNDR: wrong language linkage
inline       // IFNDR: inline
int          // IFNDR: wrong return type
handle_contract_violation(const std::contracts::contract_violation&) {}

void* operator new(decltype(sizeof(0))) noexcept;   // IFNDR: exception specification differs from the declaration in <new>
```

With `<new>` included, the `operator new` line is an invalid redeclaration within the same translation unit, and Clang can diagnose it: `exception specification in declaration does not match previous declaration`. Without `<new>`, there is nothing to compare against.

### G.6.6 Declarations not reachable from each other give different language linkages {#dcl.link.mismatched.language.linkage}

`ifndr:dcl.link.mismatched.language.linkage` · main text [[dcl.link#6]]

```cpp title="tu1.cpp"
extern "C" { void f() {} }
```

```cpp title="tu2.cpp" ifndr
extern "C++" { void f(); }   // IFNDR: language linkage differs from tu1
int main() { f(); }
```

Linking fails: `Undefined symbols … "f()"`. The `f` with C language linkage is exported as `_f`, while `f()` with C++ language linkage is mangled into `__Z1fv`, and the two do not match. The problem is only exposed as a side effect of name mangling; if `f` were never called, there would be no diagnostic at all.

### G.6.7 Alignment specifiers inconsistent across translation units {#dcl.align.diff.translation.units}

`ifndr:dcl.align.diff.translation.units` · main text [[dcl.align#6]]

If a defining declaration has an alignment specifier (`alignas`), other declarations must either specify an equivalent alignment or none; if any declaration has an alignment specifier, every defining declaration must specify an equivalent alignment. Across translation units no diagnostic is required.

```cpp title="tu1.cpp"
struct S { int x; } s, *p = &s;
```

```cpp title="tu2.cpp" ifndr
struct alignas(16) S;   // IFNDR: the definition of S has no alignas(16)
extern S* p;
int main() { return p != nullptr; }
```

There is no diagnostic in compiling, linking or running. tu2 will assume `*p` is 16-byte aligned and may generate access instructions that require that alignment.

### G.6.8 `[[indeterminate]]` inconsistent across translation units {#dcl.attr.indet.mismatched.declarations}

`ifndr:dcl.attr.indet.mismatched.declarations` · main text [[dcl.attr.indet#2]]

C++26's `[[indeterminate]]` on a parameter determines how the caller treats an uninitialized argument: whether reading it gives an erroneous value or an indeterminate value ([[basic.indet]]). So the first declarations everywhere must agree.

```cpp title="tu1.cpp"
int h(int x [[indeterminate]]);   // IFNDR: inconsistent with the first declaration elsewhere
```

```cpp title="tu2.cpp" ifndr
int h(int x);                     // IFNDR
```

Clang 23 does not recognize this attribute yet (`unknown attribute 'indeterminate' ignored`).

### G.6.9 `[[noreturn]]` inconsistent across translation units {#dcl.attr.noreturn.trans.unit.mismatch}

`ifndr:dcl.attr.noreturn.trans.unit.mismatch` · main text [[dcl.attr.noreturn#1]]

Within one translation unit, if any declaration has `[[noreturn]]`, the first declaration must have it, and that can be diagnosed. Across translation units no diagnostic is required.

```cpp title="tu1.cpp"
[[noreturn]] void f() { throw 0; }
```

```cpp title="tu2.cpp" ifndr
void f();   // IFNDR: no [[noreturn]]
int main() { try { f(); } catch (int) { return 0; } }
```

This example gives no diagnostic and runs normally. The reverse is more dangerous: if the declaration in tu2 had `[[noreturn]]` and the definition actually returned, the code after the call in tu2 could be treated as unreachable and deleted.

## Clause [module]: modules {#module}

### G.7.1 Reserved module names {#module.unit.reserved.identifiers}

`ifndr:module.unit.reserved.identifiers` · main text [[module.unit#1]]

Module names beginning with `std` followed by zero or more digits, and module names containing reserved identifiers, are reserved for the implementation and may not appear in a module declaration. The standard library itself must provide the `std` and `std.compat` modules.

```cpp ifndr
export module std0;   // IFNDR: std followed by digits
```

Clang has a warning for this that is on by default: `'std0' is a reserved name for a module [-Wreserved-module-identifier]`. The annex's example also has `module module;`, but the sentence in [[module.unit#1]] forbidding `module` and `import` as module name components requires a diagnostic.

### G.7.2 A named module without exactly one primary module interface unit {#module.unit.named.module.no.partition}

`ifndr:module.unit.named.module.no.partition` · main text [[module.unit#2]]

A named module must have exactly one interface unit without a partition name, called the **primary module interface unit**. Module units are compiled separately, and no step sees all of them, so no diagnostic is required.

```cpp title="a1.cppm"
export module A;
```

```cpp title="a2.cppm" ifndr
export module A;   // IFNDR: a second primary module interface unit for module A
```

The annex's example is `module A;` followed by `export import :Internals;`. That `export` appears in a module implementation unit, which violates a rule in [[module.interface]] that does require a diagnostic, so it does not illustrate this entry well.

### G.7.3 An interface partition not exported by the primary module interface unit {#module.unit.unexported.module.partition}

`ifndr:module.unit.unexported.module.partition` · main text [[module.unit#3]]

Every partition of a module that is an interface unit must be exported, directly or indirectly, by the primary module interface unit. The same paragraph also says a module cannot have two partitions with the same name, likewise with no diagnostic required.

```cpp title="M.cppm"
export module M;
export import :A;
```

```cpp title="M-A.cppm"
export module M:A;   // OK: exported directly by M
export import :B;
```

```cpp title="M-B.cppm"
export module M:B;   // OK: exported indirectly by M
```

```cpp title="M-C.cppm" ifndr
export module M:C;   // IFNDR: not exported, directly or indirectly, by M
```

Compiling these four units separately with `--precompile`, Clang gives no diagnostic at all.

### G.7.4 A module with a private module fragment has other module units {#module.private.frag.other.module.units}

`ifndr:module.private.frag.other.module.units` · main text [[module.private.frag#1]]

A private module fragment (`module :private;`) lets you put interface and implementation in the same file; whatever follows the fragment is not reachable from importers. So a module unit with a private module fragment must be the only unit of its module.

```cpp title="M.cppm"
export module M;
module :private;
```

```cpp title="M-A.cppm" ifndr
module M:A;   // IFNDR: M already has a private module fragment and can have no other module units
```

## Clause [class]: classes {#class}

### G.8.1 A constructor delegating to itself directly or indirectly {#class.base.init.delegate.itself}

`ifndr:class.base.init.delegate.itself` · main text [[class.base.init#6]]

A cycle of delegating constructors is infinite recursion at run time. The cycle may go through several constructors defined in different translation units, so no diagnostic is required.

```cpp ifndr
struct C {
  C(int) {}                // #1: non-delegating constructor
  C() : C(42) {}           // #2: delegates to #1
  C(char c) : C(42.0) {}   // #3: IFNDR, forms a cycle with #4
  C(double d) : C('a') {}  // #4: IFNDR, forms a cycle with #3
};
```

When the constructors are all defined in the class, Clang can see the whole cycle and reports an error: `constructor for 'C' creates a delegation cycle [-Wdelegating-ctor-cycles]`. This warning is an error by default. No diagnostic required does not stop an implementation from diagnosing when it can see the problem.

### G.8.2 A non-pure virtual function without a definition {#class.virtual.pure.or.defined}

`ifndr:class.virtual.pure.or.defined` · main text [[class.virtual#12]]

A virtual function declared in a class must be defined, or declared pure, or both. A virtual function counts as odr-used even if it is never called, because the vtable refers to it, and its definition could be in any translation unit.

```cpp ifndr
class A {
  virtual void f();   // neither defined nor pure
};

int main() {
  A a;   // IFNDR
}
```

Linking fails, but it reports `Undefined symbols … "vtable for A"` rather than a missing `A::f`. The Itanium ABI emits the vtable in the translation unit that defines the key function (the first non-inline, non-pure virtual function, here `f`); since `f` has no definition, nobody emits the vtable.

## Clause [over]: overloading {#over}

### G.9.1 A literal operator using a reserved suffix {#over.literal.reserved}

`ifndr:over.literal.reserved` · main text [[over.literal#1]]

Literal suffixes not beginning with an underscore are reserved for the standard library ([[usrlit.suffix]]), such as `s`, `h`, `i` and `if`. In addition, if a literal operator is written `operator"" _Bq` (with a space between the quotes and the suffix, a deprecated form), `_Bq` is a separate identifier, and identifiers beginning with an underscore followed by an uppercase letter are reserved.

```cpp ifndr
double operator"" _Bq(long double);   // IFNDR: _Bq is a reserved identifier (and this form is deprecated)
double operator""_Bq(long double);    // OK: without the space _Bq is a ud-suffix, not subject to the identifier reservation rules
```

The first line only gets a deprecation warning: `identifier '_Bq' preceded by whitespace in a literal operator declaration is deprecated`. The annex's other example, `float operator ""E(const char*);`, is treated by Clang as an error (`invalid suffix on literal; C++11 requires a space between literal and identifier`), with an accompanying warning `user-defined literal suffixes not starting with '_' are reserved`.

## Clause [temp]: templates {#templates}

Templates account for 14 entries, nearly a third of the total. There are two reasons. Templates are processed in two phases, at the definition and at the instantiation, and the two may see different declarations; and the same specialization may be instantiated once in each of several translation units, which the standard requires to agree but has no way of checking.

### G.10.1 The template definition is not visible at an implicit instantiation {#temp.pre.reach.def}

`ifndr:temp.pre.reach.def` · main text [[temp.pre#10]]

If a function template, a member function of a class template, a variable template or a static data member of a class template is implicitly instantiated in some definition domain, its definition must be reachable at the end of that definition domain, unless the specialization is explicitly instantiated somewhere. This is the standard's basis for templates usually being written in headers.

```cpp title="a.h"
template <typename T>
void f();
```

```cpp title="a.cpp" ifndr
#include "a.h"
int main() {
  f<int>();   // IFNDR: f<int> is implicitly instantiated, but the definition is not reachable and there is no explicit instantiation
}
```

Linking fails: `Undefined symbols … "void f<int>()"`. If another translation unit happened to contain `template void f<int>();`, the program would be valid. Whether it is valid depends on other translation units, so it can only be IFNDR here.

### G.10.2 When a template template parameter is instantiated, the partial specialization that should be selected is not reachable {#temp.arg.template.sat.constraints}

`ifndr:temp.arg.template.sat.constraints` · main text [[temp.arg.template#2]]

```cpp ifndr
template <class T> struct A { int x; };

template <template <class U> class V> struct C {
  V<int> y;
  V<int*> z;
};

C<A> c;   // A<int*> is instantiated here, using the primary template

template <class T> struct A<T*> { long x; };   // IFNDR: had it been reachable, A<int*> should have selected it
```

Clang does not diagnose it.

### G.10.3 The result depends on whether two functionally equivalent atomic constraints are equivalent {#temp.constr.atomic.equiv.but.not.equiv}

`ifndr:temp.constr.atomic.equiv.but.not.equiv` · main text [[temp.constr.atomic#2]]

When comparing which of two constraints is stricter (subsumption, see [[topics/concepts]]), atomic constraints are judged **equivalent** by whether they are written the same, not by their semantics. `2 * N` and `N * 2` give the same result for every `N`, which makes them **functionally equivalent** ([[g:functionally-equivalent]]), but they are not equivalent. If the result of overload resolution depends on whether the two are treated as equivalent, the program is IFNDR, because deciding whether two arbitrary expressions are functionally equivalent is undecidable.

```cpp ifndr
template <int N> concept Add1 = true;

template <unsigned N> void f2() requires Add1<2 * N>;
template <unsigned N> int  f2() requires Add1<N * 2> && true;

void h2() {
  f2<0>();   // IFNDR: which one is selected depends on whether Add1<2 * N> and Add1<N * 2> are equivalent
}
```

Clang does not diagnose it and selects the second overload, which returns `int` (`static_assert(__is_same(decltype(f2<0>()), int))` passes).

### G.10.4 The same constraint has different satisfaction results at different points {#temp.constr.atomic.sat.result.diff}

`ifndr:temp.constr.atomic.sat.result.diff` · main text [[temp.constr.atomic#3]]

The same atomic constraint with the same template arguments must give the same result when checked at different points in the program. The most common violation is using a concept to detect whether a type is complete, with the type being completed between the two checks.

```cpp ifndr
template <class T>
concept Complete = sizeof(T) == sizeof(T);

struct A;
static_assert(!Complete<A>);   // #1: A is incomplete, not satisfied
struct A {};
static_assert(Complete<A>);    // IFNDR: satisfaction result differs from #1
```

Clang caches the first satisfaction result, so the second `static_assert` fails (`static assertion failed`). It does report an error, but for the wrong reason: it just reuses the old answer. Allowing implementations to cache like this is exactly why the standard makes such programs IFNDR.

### G.10.5 Substitution during normalization produces an invalid type or expression {#temp.constr.normal.invalid}

`ifndr:temp.constr.normal.invalid` · main text [[temp.constr.normal#1]]

**Normalization** ([[g:normalization]]) expands uses of concepts into atomic constraints and substitutes arguments into the parameter mapping of each atomic constraint. If the substitution produces an invalid type or expression, the program is IFNDR, even if that atomic constraint would never be evaluated.

```cpp ifndr
template <typename T> concept A = T::value || true;
template <typename U> concept B = A<U*>;   // OK: mapping T ↦ U*
template <typename V> concept C = B<V&>;   // IFNDR: the mapping would form V&* (pointer to reference)
```

With only these three concepts defined, Clang does not diagnose anything; as soon as `C<int>` is used, it reports `'type name' declared as a pointer to a reference of type 'V &'`.

In the main text, the annex entry is attached to ¶1.5.3.1 (expansion of a concept template parameter pack in a fold expression), while this example demonstrates another sentence with the same wording in ¶1.4.2. Both require no diagnostic.

### G.10.6 The partial specialization that should be used is not reachable at the point of use {#temp.spec.partial.general.partial.reachable}

`ifndr:temp.spec.partial.general.partial.reachable` · main text [[temp.spec.partial.general#1]]

```cpp ifndr
template <typename T> class X {
public:
  void foo() {}
};

template class X<void*>;   // IFNDR: at this explicit instantiation the partial specialization below is not yet reachable

template <typename T> class X<T*> {
public:
  void baz();
};
```

Clang does not diagnose it.

### G.10.7 The result depends on whether two functionally equivalent constructs are equivalent {#temp.over.link.equiv.not.equiv}

`ifndr:temp.over.link.equiv.not.equiv` · main text [[temp.over.link#7]]

This is the general form of [G.10.3](#temp.constr.atomic.equiv.but.not.equiv). Whether two function template declarations are the same template or two overloads is decided by whether the expressions in their template-heads and signatures are equivalent. `I+10` and `I+1+2+3+4` are functionally equivalent but not equivalent.

```cpp ifndr
template <int I> struct A {};

// IFNDR: the two are functionally equivalent but not equivalent
template <int I> void f(A<I>, A<I+10>);
template <int I> void f(A<I>, A<I+1+2+3+4>);
```

Clang treats them as two different templates, and the declarations themselves are not diagnosed. Given definitions and a call `f<0>(A<0>{}, A<10>{})`, it reports `call to 'f' is ambiguous`.

### G.10.8 A default argument the template cannot see would change the result {#temp.res.general.default.but.not.found}

`ifndr:temp.res.general.default.but.not.found` · main text [[temp.res.general#2]]

Names in a template that do not depend on template parameters are looked up at the template definition ([[g:two-phase-lookup]]). If a declaration after the template definition adds a default argument to some function, it is reachable at the point of instantiation but invisible to the template's lookup; if taking it into account would change the result, the program is IFNDR.

```cpp ifndr
#include <cstdio>

void f(long) { std::puts("f(long)"); }        // #1
void f(int, int) { std::puts("f(int,int)"); } // #2
template <typename T> void g(T t) { f(t); }
void f(int, int = 0);                          // #3: adds a default argument to #2

void h() { g(0); }   // IFNDR: taking #3 into account would select f(int, int = 0), but the template's lookup selected #1
```

Clang does not diagnose it, and the call prints `f(long)`.

### G.10.9 The same specialization has different meanings at different points of instantiation {#temp.point.diff.pt.diff.meaning}

`ifndr:temp.point.diff.pt.diff.meaning` · main text [[temp.point#7]]

A specialization may have a point of instantiation ([[g:point-of-instantiation]]) in each of several translation units, and a function template may have several within the same translation unit. If the specialization means different things at different points of instantiation, the program is IFNDR. The classic example is a trait that detects whether a type is complete:

```cpp title="a.h"
#include <type_traits>

template <typename T, typename = void>
struct is_complete : std::false_type {};

template <typename T>
struct is_complete<T, std::void_t<decltype(sizeof(T))>> : std::true_type {};
```

```cpp title="a.cpp"
#include "a.h"
struct X;
bool in_a() { return is_complete<X>::value; }   // X is incomplete here: false
```

```cpp title="b.cpp" ifndr
#include "a.h"
#include <cstdio>
struct X {};
bool in_a();
int main() {
  // IFNDR: is_complete<X> selects different specializations in the two translation units
  std::printf("a: %d, b: %d\n", in_a(), (int)is_complete<X>::value);
}
```

There is no diagnostic at all, and the program prints `a: 0, b: 1`: the same type `is_complete<X>` has two different definitions in the same program. So a trait that detects whether a type is complete cannot be implemented correctly.

### G.10.10 Taking all translation units into account, a dependent call would give a different result {#temp.dep.candidate.different.lookup.different}

`ifndr:temp.dep.candidate.different.lookup.different` · main text [[temp.dep.candidate#1]]

A call that depends on template parameters looks for candidate functions through argument-dependent lookup (ADL, [[g:argument-dependent-lookup]]) in the template definition context and the instantiation context. If, counting the functions with external linkage in the associated namespaces of all translation units, the call would become ill-formed or find a better match, the program is IFNDR.

```cpp title="tu1.cpp"
namespace A {
  struct S {};
  void f(S&, long x, int y);   // #3
  void g(S&, int x);           // #4
}
```

```cpp title="tu2.cpp" ifndr
namespace A {
  struct S {};
  void f(S&, int x, long y);   // #5
  void g(S&, long x);          // #6
}
template <typename T>
void h(T& t) {
  f(t, 1, 1);   // in h<A::S> selects #5; taking all declarations into account would be ambiguous
  g(t, 1);      // in h<A::S> selects #6; taking all declarations into account would select #4
}
```

### G.10.11 An explicit instantiation declaration without an explicit instantiation definition {#temp.explicit.decl.implicit.inst}

`ifndr:temp.explicit.decl.implicit.inst` · main text [[temp.explicit#12]]

An **explicit instantiation declaration** (`extern template`) tells the compiler not to instantiate here, because it will be provided elsewhere. If the entity is used in a way that would require an implicit instantiation, and there is no explicit instantiation definition anywhere in the program, the program is IFNDR.

```cpp ifndr
#include <vector>
#include <cstdio>

extern template class std::vector<int>;   // explicit instantiation declaration

int main() {
  std::printf("%zu\n", std::vector<int>().size());   // IFNDR: no explicit instantiation definition in the whole program
}
```

Linking succeeds and the program prints `0`. An explicit instantiation declaration does not prevent instantiation of inline functions ([[temp.explicit]]), and nearly all members of libc++'s `vector` are inline, so no undefined symbol results. With a class template whose member functions are defined non-inline outside the class, you would get a link error.

### G.10.12 The declaration of an explicit specialization is not reachable at a point of use {#temp.expl.spec.unreachable.declaration}

`ifndr:temp.expl.spec.unreachable.declaration` · main text [[temp.expl.spec#7]]

The declaration of an explicit specialization must be reachable at every use that would cause an implicit instantiation, in every such translation unit. Otherwise one translation unit uses the specialization and another uses the primary template, and the same `S<int>` has two layouts.

```cpp title="a.h"
template <typename T> struct S {};
```

```cpp title="tu2.cpp"
#include "a.h"
template <> struct S<int> { int oops; };   // #1
```

```cpp title="tu3.cpp" ifndr
#include "a.h"
S<int> s;   // IFNDR: #1 is not reachable, but it should have been selected
```

### G.10.13 An explicit specialization used without being defined {#temp.expl.spec.missing.definition}

`ifndr:temp.expl.spec.missing.definition` · main text [[temp.expl.spec#7]]

If an explicit specialization is declared but not defined, and the specialization is used in a way that would require an implicit instantiation (or it is a virtual member function), the program is IFNDR. Once an explicit specialization has been declared, the primary template's definition is no longer used to generate that specialization.

```cpp ifndr
template <typename T> int f(T&&) { return 0; }
template <> int f<int>(int&&);   // declared only

int j = f(1);   // IFNDR: f<int> is odr-used, but it has no definition
```

Linking fails (`Undefined symbols`).

### G.10.14 Different declarations have different substitution orders {#temp.deduct.general.diff.order}

`ifndr:temp.deduct.general.diff.order` · main text [[temp.deduct.general#7]]

Substitution in template argument deduction proceeds in lexical order and stops when a condition that causes deduction to fail is encountered. If two declarations of the same function template are written differently (say one with a leading return type and one with a trailing return type), the order in which substitution triggers instantiations may differ: under one order it is a substitution failure (SFINAE, [[g:sfinae]]), under the other a hard error.

```cpp ifndr
template <class T> struct A { using X = typename T::X; };

template <class T> typename T::X h(typename A<T>::X);           // #1
template <class T> auto h(typename A<T>::X) -> typename T::X;   // redeclaration #2
template <class T> void h(...) {}

void x() {
  h<int>(0);   // IFNDR: substituting per #1, T::X fails first and A<int> is not instantiated;
               // substituting per #2, A<int> is instantiated first, which is a hard error
}
```

Clang follows the order of #2 and reports a hard error, `type 'int' cannot be used prior to '::' because it has no members`, from the instantiation of `A<int>`.

## Clause [cpp]: preprocessing directives {#cpp}

### G.11.1 defined produced by macro expansion in #if {#cpp.cond.defined.after.macro}

`ifndr:cpp.cond.defined.after.macro` · main text [[cpp.cond#9]]

`defined` is supposed to be recognized before macro expansion. When it is the product of macro expansion, preprocessors have historically behaved differently (GCC and MSVC disagree), and the standard chooses not to specify it.

```cpp ifndr
#define X
#define D defined(X)
#if D        // IFNDR: defined is produced by macro replacement
#endif
```

Clang warns `macro expansion producing 'defined' has undefined behavior [-Wexpansion-to-defined]`. The warning text follows the C standard's wording (in C this is UB); C++ now makes it IFNDR. The annex's example is `#define A defined` followed by `#if A`, where nothing follows `defined`, and Clang reports an error directly: `macro name missing`.

### G.11.2 A malformed defined {#cpp.cond.defined.malformed}

`ifndr:cpp.cond.defined.malformed` · main text [[cpp.cond#9]]

`defined` has only two valid forms, `defined X` and `defined ( X )`, judged by the tokens before macro replacement.

```cpp ifndr
#define A
#define B A)
#if defined ( B   // IFNDR: before replacement, defined ( B is missing the closing parenthesis
#endif
```

Clang reports the error `missing ')' after 'defined'`.

### G.11.3 #include does not form a header name after macro replacement {#cpp.include.malformed.headername}

`ifndr:cpp.include.malformed.headername` · main text [[cpp.include#7]]

If what follows `#include` is neither `<...>` nor `"..."`, it is macro-replaced first, and the result must form one of those two forms; how whitespace is handled is implementation-defined. If it does not, the program is IFNDR.

```cpp ifndr
#include “   // IFNDR: a typographic curly quotation mark, neither of the two valid forms
```

Clang reports the error `expected "FILENAME" or <FILENAME>`.

## Common misconceptions

!!! pitfall "It compiles, links and runs, so the program is fine"
    That is precisely how IFNDR programs typically behave. The examples in [G.3.5](#basic.def.odr.definition.matches), [G.6.3](#dcl.fct.default.inline.same.defaults) and [G.10.9](#temp.point.diff.pt.diff.meaning) all compile, link and run without trouble, yet the same program contains two versions of the same thing.

!!! pitfall "IFNDR is just ill-formedness the compiler can't be bothered to report"
    The consequences are completely different. An ill-formed program that must be diagnosed gets at least one diagnostic; an IFNDR program may get an executable, and the standard places no requirements on anything that executable does, including the parts unrelated to the offending code.

!!! pitfall "Compilers never report the problems in the annex"
    When compilers can see a problem they often report it: delegation cycles ([G.8.1](#class.base.init.delegate.itself)), reserved module names ([G.7.1](#module.unit.reserved.identifiers)), and the preprocessor entries (G.11).

!!! pitfall "It's enough for each translation unit to be fine on its own"
    Well over half of the 45 entries involve multiple translation units. In practice the most common source of ODR violations is a build system that lets different translation units use different macro definitions or compiler options, such as `-D` switches that affect struct layout or inline function bodies.

## Questions

!!! question "Question 1"
    Why is the requirement that inline function definitions be the same IFNDR under the header model, but in some cases required to be diagnosed with modules? Hint: compare the conditions after a diagnostic is required only if in [[basic.def.odr#16]].

<details markdown="1">
<summary>Answer</summary>

[[basic.def.odr#16]] requires a diagnostic only when the entity is attached to a named module and a prior definition is reachable at the point where a later one occurs. That is exactly the situation in which the compiler can see both definitions at once: when importing a module, the compiler reads the imported module's BMI (the compiled form of the module interface), which contains the earlier definition. Under the header model, translation units are compiled independently, no step sees both definitions at once, and the standard can only give up on requiring a diagnostic. One benefit of modules is turning some IFNDR into errors that must be diagnosed.
</details>

!!! question "Question 2"
    In [G.10.4](#temp.constr.atomic.sat.result.diff), Clang made the second `static_assert` fail. `Complete<A>` clearly ought to be satisfied after `A` is completed; does this violate the standard?

<details markdown="1">
<summary>Answer</summary>

It does not. Per [[temp.constr.atomic#3]], if the same atomic constraint with the same arguments has different satisfaction results at different points in the program, the program is IFNDR, and the standard places no requirements on the implementation: reporting an error, not reporting one, or giving any result at all conforms. Clang caches satisfaction results to keep the cost of constraint checking under control; the standard makes such programs IFNDR precisely to allow that caching.
</details>

## Summary

| Question | Answer |
|---|---|
| Consequences of IFNDR | the program is ill-formed and the implementation is under no constraints ([[intro.compliance.general#2.2]]); the offending code need not be executed |
| Status of Annex G | informative, 45 entries, collecting no diagnostic (is) required and a diagnostic is required only if |
| Why no diagnostic is required | needs a whole-program view, undecidable, reserved names, historical differences between implementations |
| What the linker can find | duplicate definitions of strong symbols; missing definitions (depending on optimization); inconsistent language linkage (depending on whether it is called) |
| What the linker cannot find | inconsistent definitions of inline functions, templates, vtables and the like; inconsistent default arguments; different meanings at points of instantiation |
| What modules change | some cross-translation-unit IFNDR must be diagnosed when the prior definition is reachable |
