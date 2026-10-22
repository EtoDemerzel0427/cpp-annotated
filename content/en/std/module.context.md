---
title: Instantiation context
summary: "When a template is defined in one module and instantiated in another translation unit, from which program points ADL for dependent names and reachability of declarations are determined; defaulted functions, nested instantiations and constant evaluation each have their own rules."
updated: 2026-10-19
---

!!! tldr
    - An instantiation context is a set of program points. ADL for dependent names looks from each of them, and a declaration is reachable if it is reachable from any of them, so the more points, the more is usable.
    - For ordinary code the context is just the point itself; for a template instantiated directly, it is its point of instantiation, usually at the user.
    - A nested instantiation additionally gets the end of the primary interface unit of the template's module, so helper templates called inside a template can use everything reachable in the module interface.
    - Whether a header unit that is only touched indirectly through another module is reachable from the instantiation context is unspecified: `import` whatever you need directly.

## Where a template looks

Without modules, what a template instantiation sees is decided by the **[[g:point-of-instantiation|point of instantiation]]** ([[temp.point]]): roughly right after the declaration that uses the template, and everything declared before it in this translation unit is usable. Headers are pasted into every translation unit, so what is visible where the template is defined is generally also visible where it is instantiated.

Modules break this assumption. A template is defined in an interface unit of module M but instantiated at an importer, and the two places may see completely different things: the definition site sees the modules M itself imports, the headers in its global module fragment, and M's unexported entities; the instantiation site sees only what the importer itself imports. During instantiation, which side should govern lookup of dependent names ([[temp.dep]], names whose meaning depends on template arguments) and the completeness of types? The standard's answer is to give a set of points, with part of each side counting.

## Definition (¶1)

¶1 An **[[g:instantiation-context|instantiation context]]** is a set of points in the program that determines which declarations are found by argument-dependent lookup (ADL, [[basic.lookup.argdep]]) and which are reachable ([[module.reach]]) in the context of a particular declaration or template instantiation. The two uses are:

- ADL for a dependent name, besides looking in the usual places, also looks from each point in the instantiation context ([[basic.lookup.argdep#4]]);
- a declaration is reachable if it is reachable from any point in the instantiation context ([[module.reach#4]]).

Both take a union, so the more points, the more can be found and used. The paragraphs below specify which points the context contains in each situation.

## The various situations

### Ordinary code and direct instantiation (¶7, ¶5)

¶7 When none of the situations below applies, the instantiation context of a point in the program contains only that point. Ordinary non-template code is like this.

¶5 When another template specialization is instantiated, the instantiation context contains the point of instantiation of that template. If an importer writes `f<int>()` in an ordinary function, the point of instantiation of `f<int>` is in the importer's translation unit, and that's all the context contains.

### Nested instantiation (¶3)

```cpp title="M-Impl.cppm"
module M:Impl;
struct Detail { int v = 5; };
```

```cpp title="M.cppm"
export module M;
import :Impl;
export Detail* make() { return new Detail; }
template<class P> int inner(P p) { return p->v; }
export template<class P> int outer(P p) { return inner(p); }
export template<class P> int direct(P p) { return p->v; }
```

```cpp title="use-outer.cpp" ok
import M;
int main() {
  auto p = make();
  return outer(p);   // inner<Detail*> is a nested instantiation (¶3)
}
```

```cpp title="use-direct.cpp" unspecified
import M;
int main() {
  auto p = make();
  return direct(p);  // direct<Detail*> is a direct instantiation (¶5)
}
```

`Detail` is defined in the implementation partition `M:Impl`. An implementation partition isn't a module interface unit and isn't necessarily reachable from importers; but `M.cppm` imports it directly, so it is necessarily reachable from the end of M's primary interface ([[module.reach#1]]).

¶3 When a template is referenced in a way that depends on template parameters within another template specialization, its point of instantiation is specified to be that of the enclosing specialization ([[temp.point#1]]). The context of such a nested instantiation contains:

- each point in the instantiation context of the enclosing specialization; and
- if the template is defined in an interface unit of module M and the point of instantiation isn't in an interface unit of M, also the point at the end of the *declaration-seq* of M's primary module interface unit (before the private module fragment, if any).

`inner<Detail*>` is referenced dependently within `outer<Detail*>`, which is this situation, so the context includes the end of M's primary interface, where `Detail` is complete; therefore `use-outer.cpp` is well-formed. `direct<Detail*>` is a direct instantiation whose context is only the point of instantiation in `use-direct.cpp`, from which `M:Impl` isn't necessarily reachable, so whether it's valid is unspecified ([[module.reach#2]]).

The end of the primary interface is chosen because by then the interface of module M is fully established: all interface partitions have been imported and all of M's own `import`s have taken effect. A template author can expect that whatever M's interface can see is usable inside the template. Direct instantiation doesn't need this rule: the importer has an interface dependency on M's interface units, which are thus necessarily reachable. The point of instantiation of a nested instantiation is inherited from the enclosing specialization and may be far from M, so the end of M's primary interface has to be added explicitly.

!!! impl "Clang 23 doesn't follow ¶3"
    In our tests Clang 23 reports `definition of 'Detail' must be imported from module 'M' before it is required` for both users. For `use-direct.cpp` that's a permitted choice; for `use-outer.cpp`, Clang apparently doesn't implement ¶3's rule of adding the end of the primary interface, at least for implementation partitions. When compiling `M.cppm`, Clang also warns `importing an implementation partition unit in a module interface is not recommended. Names from M:Impl may not be reachable`, indicating that it deliberately doesn't treat implementation partitions imported in the interface as reachable from outside.

    The portable approach: put the types whose definitions exported templates need into an interface partition that the primary interface `export import`s, or directly into the primary interface.

### Defaulted functions (¶2, ¶4)

¶2 When a **defaulted function** (special member functions and comparison operators that are `= default` or implicitly declared; [[special]], [[class.compare.default]]) is implicitly defined, the instantiation context contains two parts: each point in the instantiation context at the class definition, and each point in the instantiation context of the construct that caused the implicit definition.

For example, module M has `export struct S { T t; bool operator==(const S&) const = default; };`, and an importer writes `s1 == s2`, triggering the implicit definition of `operator==`. When comparing `t`, looking up `T`'s `operator==` can use both what is reachable at the class definition in M and what is reachable at the importer's point of use.

¶4 When the implicit definition of a defaulted function references a template and thereby implicitly instantiates it, the instantiation context contains each point in the instantiation context of the defaulted function. For example, a defaulted `operator==` comparing a `std::vector<T>` member triggers instantiation of `vector`'s `operator==`.

### Instantiations caused by constant evaluation (¶6) {{c++26}}

¶6 When an expression evaluated as a core constant expression causes some construct to be implicitly instantiated, the instantiation context contains each point in the **evaluation context** ([[expr.const.reflect]]).

Note 1 explains that such implicit instantiation can come from calls to library functions, such as the reflection metafunction `std::meta::substitute` ([[meta.reflection]]). The evaluation context can contain synthesized points associated with injected declarations produced by `std::meta::define_aggregate`. That is, classes completed during constant evaluation are also visible to instantiations triggered in that evaluation.

### Only these points (¶8)

¶8 The instantiation context contains only the points specified in the paragraphs above; an implementation can't add points of its own to make more declarations reachable or findable by ADL. What an implementation is free to decide is a different matter: [[module.reach#2]] allows it to treat additional translation units as reachable.

## The standard's example (¶9)

```cpp title="TU #1: stuff.cppm"
export module stuff;
export template<typename T, typename U> void foo(T, U u) { auto v = u; }
export template<typename T, typename U> void bar(T, U u) { auto v = *u; }
```

```cpp title="TU #2: M1.cppm"
export module M1;
import "defn.h";        // provides struct X {};
import stuff;
export template<typename T> void f(T t) {
  X x;
  foo(t, x);
}
```

```cpp title="TU #3: M2.cppm"
export module M2;
import "decl.h";        // provides struct X; (not a definition)
import stuff;
export template<typename T> void g(T t) {
  X *x;
  bar(t, x);
}
```

```cpp title="TU #4: test.cpp" unspecified
import M1;
import M2;
void test() {
  f(0);       // OK
  g(0);       // unspecified whether valid
}
```

`foo<int, X>` copies an `X` and needs `X`'s definition. Its instantiation context contains the end of TU #1 (¶9.1), the end of TU #2 (¶9.2) and the point of the call `f(0)` (¶9.3). At the end of TU #2, `defn.h` has been imported directly and `X`'s definition is reachable, so `f(0)` is valid.

`auto v = *u;` in `bar<int, X*>` likewise copies an `X`. Its context contains the end of TU #1 (¶9.4), the end of TU #3 (¶9.5, where only `decl.h` was imported and `X` is incomplete) and the point of the call `g(0)` (¶9.6). `test.cpp` has an interface dependency on the header unit of `defn.h` through M1, but that header unit is neither a module interface unit nor directly imported by `test.cpp`, so it isn't necessarily reachable. An implementation may treat it as reachable or not, so whether `g(0)` is valid is unspecified.

!!! impl "Verified in our tests"
    Building `defn.h` and `decl.h` as Clang 23 header units (`-fmodule-header=user`), then stuff, M1 and M2 in turn, and compiling `test.cpp`: `f(0)` passes; `g(0)` reports `definition of 'X' must be imported from module './defn.h' before it is required`, with the note `definition here is not reachable`. Clang chooses not to treat additional translation units as reachable, which the standard allows.

!!! lawyer "Where does ¶9.2 come from?"
    Derived literally, ¶9.2 isn't obvious. `f<int>` is referenced directly by non-template code in `test.cpp`, which falls under ¶5, so its context is only its point of instantiation in TU #4. What ¶3 adds for `foo<int, X>` is the end of the primary interface of `foo`'s module stuff, that is, TU #1, not TU #2.

    The intent of the example is that what is reachable where template `f` is defined (the end of M1's interface) should be usable by nested instantiations triggered inside `f`, which is also what ¶3 is designed for. But reading this out of the normative wording requires understanding ¶3 as accumulating, along the chain of enclosing specializations, the end of the primary interface of each layer's module. This is a gap in the wording worth noting; Clang accepts `f(0)`, agreeing with the example's conclusion.

## Relation to ADL

The standard's example in [[basic.lookup.argdep#5]] shows the role of instantiation contexts in ADL. Module N's exported template `apply(t, u)` contains the dependent calls `f(t, u)` and `g(t)`. During instantiation, ADL looks from each point in the context, including the end of N's interface and the call site, so `S::f`, visible in N's interface, can also be considered. But `static int R::g(X)` in N, although visible at the end of N's interface, has internal linkage and can't be used outside N's interface unit, so that call is ill-formed.

## History

!!! history
    - Instantiation contexts came into C++20 with the merged modules proposal [[P1103R3]], replacing the Modules TS's rather vague rules about which declarations are visible during instantiation.
    - C++26 added ¶6, bringing the evaluation context of constant evaluation (synthesized points and injected declarations introduced by static reflection) into the instantiation context.

## Common misconceptions

!!! pitfall "A template passes tests inside the module but fails when an importer instantiates it"
    The template depends on the completeness of some type or on some ADL candidate that exists only in an implementation partition inside the module, or in the global module fragment (and was discarded). When the module author tests inside the module, the point of instantiation is in the module and everything works; when an importer instantiates it, the context doesn't contain those points. When testing a module, instantiate the exported templates from outside the module.

!!! pitfall "Relying on transitive reachability of header units"
    As with `g(0)` in ¶9, when a header unit is touched only indirectly through another module, whether its definitions are reachable is unspecified. `import` whatever you need directly.

## Questions

!!! question "Question"
    In ¶9, if TU #4 adds `import "defn.h";` after `import M2;`, is `g(0)` then definitely valid?

<details markdown="1">
<summary>Answer</summary>

Yes. The instantiation context of `bar<int, X*>` contains the point of the call `g(0)` (¶9.6), which comes after `import "defn.h";`. The `defn.h` header unit is imported directly by TU #4 and is necessarily reachable ([[module.reach#1]]), so `X`'s definition is reachable. The `X` in `defn.h` and in `decl.h` are both attached to the global module and have external linkage, so they are the same entity, and this definition is the definition of the `X` in `X*`. In our tests Clang 23 also accepts `test.cpp` modified this way.
</details>
