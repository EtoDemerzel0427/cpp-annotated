---
title: Dependent name resolution
summary: "Where a dependent call in a template looks for functions: ordinary lookup only at the template definition, ADL also at the point of instantiation; how points of instantiation are determined; and why the program is ill-formed, no diagnostic required, when different points of instantiation give different meanings or another set of headers would select a better overload."
updated: 2026-10-19
---

!!! tldr
    - The candidate functions of a dependent call `f(t)` come from two places: ordinary unqualified lookup at the template definition, plus ADL at both the definition and the point of instantiation. A function declared after the template definition can only be found through ADL.
    - Members of a dependent base aren't visible at the template definition; write `this->g()` or `Base<T>::g()`. The latter suppresses virtual dispatch.
    - The point of instantiation of a function template specialization immediately follows the namespace-scope declaration that refers to it; that of a class template specialization immediately precedes it.
    - A function template specialization also has a point of instantiation at the end of the translation unit. If several points of instantiation give different meanings, the program is ill-formed, no diagnostic required.
    - If considering the declarations from all translation units would make a dependent call ill-formed or find a better overload, the program is likewise ill-formed, no diagnostic required.

## Can a function declared after the template definition be called?

```cpp run ok title="where_lookup_happens.cpp"
#include <cstdio>
void f(int) { std::puts("f(int)"); }

template<class T> void g(T t) { f(t); }

void f(double) { std::puts("f(double)"); } // declared after the definition
namespace N {
  struct S { operator int() const { return 0; } };
  void f(S) { std::puts("N::f(S)"); }      // declared after the definition
}

int main() {
  g(1.0);      // prints f(int)
  g(N::S{});   // prints N::f(S)
}
```

The `f(t)` in `g` is a **dependent call**: the type of the argument `t` depends on a template parameter, so which `f` to call can't be decided at the template definition ([[temp.dep]]). When `g(1.0)` is instantiated, `f(double)` has long been declared and is an exact match, yet `f(int)` is what gets called. `g(N::S{})`, on the other hand, finds `N::f(S)`, which was also declared after the definition.

The difference lies in how they are looked up. Ordinary unqualified lookup is done only once, at the template definition, when only `f(int)` exists. **Argument-dependent lookup** (ADL, [[g:argument-dependent-lookup]]) searches for functions in the associated namespaces of the argument types, and for a dependent call it is done again at instantiation. The associated namespace of `N::S` is `N`, so `N::f(S)` is found; `double` is a fundamental type with no associated namespaces, and ADL finds nothing.

### The complete two-phase lookup rules

This set of rules is usually called **two-phase lookup** ([[g:two-phase-lookup]]). It isn't a standard term but a collective name for several scattered rules:

| Kind of name | Where it is looked up | Source |
|---|---|---|
| non-dependent names (qualified or unqualified) | once at the template definition, result fixed | [[temp.res.general#1]] |
| ordinary unqualified lookup for a dependent call `f(args)` | from the template definition only | [[temp.res.general#1]] |
| ADL for a dependent call `f(args)` | from the template definition and from each point in the instantiation context | [[basic.lookup.argdep#4]] |
| dependent qualified names `T::x`, `Base<T>::x`, `t.x` | qualified lookup in the now-known class at instantiation | [[temp.dep.type#5]] |

!!! std
    If N is a dependent name, the above lookup is also performed from each point in the instantiation context of the lookup, ...

This sentence from [[basic.lookup.argdep#4]] is the basis for the third row: for a dependent name, ADL is performed again from each point in the **instantiation context** ([[g:instantiation-context]]). In a program that doesn't use modules, the instantiation context has only one point, the point of instantiation discussed below ([[module.context#5]]).

## Dependent bases and `this->`

```cpp error
template<class T> struct Base { void g() { } };
template<class T> struct D : Base<T> {
  void f() { g(); }    // error: g not found
};
```

`g()` has no arguments, so it can't be a dependent call; `g` is a non-dependent name, looked up only at the definition. `D` itself has no `g`; `Base<T>` is a **dependent base class** ([[g:dependent-base-class]]), a base that depends on template parameters, and isn't searched at the definition ([[temp.dep.type#3]]); and there's no global `g`. So lookup fails.

Dependent bases aren't searched because `Base<T>` can be explicitly specialized into anything. The following program happens to have a global `g`:

```cpp run ok title="silent_rebinding.cpp"
#include <cstdio>
void g() { std::puts("::g"); }

template<class T> struct Base {
  void g() { std::puts("Base<T>::g"); }
};
template<class T> struct D : Base<T> {
  void f() {
    g();          // bound to ::g at the definition
    this->g();    // dependent name, looked up at instantiation
  }
};
template<> struct Base<int> { };   // no g

int main() { D<double>{}.f(); }    // ::g, then Base<T>::g
```

The unqualified `g()` is silently bound to `::g`, without any diagnostic. If the rules allowed looking at the members of the primary template `Base<T>` at the definition, the meaning would change again for `D<int>`, which meets a `Base<int>` without `g`. The standard chose a consistent rule: at the template definition, dependent bases are treated as if they didn't exist.

To use members of a dependent base, there are several ways to write it:

```cpp run ok
template<class T> struct Base { void g() { } };
template<class T> struct D : Base<T> {
  void f() {
    this->g();      // the type of this is dependent, so the member access is too
    D::g();         // not found in the current class, and there is a dependent base: dependent
    Base<T>::g();   // the class searched depends on T: dependent
  }
};
template<class T> struct D2 : Base<T> {
  using Base<T>::g; // brings the name into D2
  void f() { g(); }
};
int main() { D<int>{}.f(); D2<int>{}.f(); }
```

`D::g()` and `Base<T>::g()` are dependent by items 5.4 and 5.2 of [[temp.dep.type#5]] respectively.

!!! pitfall "`Base<T>::f()` suppresses virtual dispatch"
    Calling a virtual function through a qualified name doesn't dispatch dynamically ([[class.virtual]]). If `hook` is virtual, `Base<T>::hook()` always calls the base version; only `this->hook()` is a virtual call:

    ```cpp run ok
    #include <cstdio>
    template<class T> struct Base {
      virtual void hook() { std::puts("Base::hook"); }
    };
    template<class T> struct D : Base<T> {
      void hook() override { std::puts("D::hook"); }
      void call() { this->hook(); Base<T>::hook(); }
    };
    int main() { D<int> d; d.call(); }   // D::hook, then Base::hook
    ```

    So `this->` is generally the recommended form.

!!! impl "MSVC's old behavior"
    For a long time MSVC didn't implement two-phase lookup: it stored template bodies as token streams and parsed and looked up names only at instantiation. So members of dependent bases could be used unqualified, code missing `typename` compiled anyway, ordinary functions declared after the definition were found, and errors in templates that were never instantiated went unreported. Such code doesn't compile on GCC or Clang, and `silent_rebinding.cpp` calls `Base<T>::g` on old MSVC.

    Since VS 2017, MSVC implements two-phase lookup in `/permissive-` mode, and `/Zc:twoPhase-` turns it off. Clang's `-fdelayed-template-parsing` mimics old MSVC, deferring parsing of function template bodies to the end of the translation unit; compiled with it, the example above that can't find `g()` no longer errors. This is non-conforming behavior, and Clang also warns that the option is deprecated after C++20.

## Point of instantiation [temp.point]

Where do the points in the instantiation context come from? The most basic one is the **point of instantiation** (POI, [[g:point-of-instantiation]]): a location in the source code where the compiler behaves as if the specialization's definition were generated. ADL for dependent calls starts from here and sees the declarations before it.

### Functions: immediately after (¶1)

```cpp
namespace N { struct S { }; }
template<class T> void call(T t) { touch(t); }

void use() {
  call(N::S{});
}
// ← point of instantiation of call<N::S>
namespace N { void touch(S) { } }
// ← end of the translation unit: also a point of instantiation (¶7)
```

¶1 For a function template specialization, a member function template specialization, or a specialization of a member function or static data member of a class template, the point of instantiation immediately follows the namespace-scope declaration or definition that refers to it. `call(N::S{})` is written in the body of `use`, but the point of instantiation isn't at the call; it's after the whole definition of `use`.

The exception is the nested case. If the specialization is implicitly instantiated because it is referenced from within another template specialization (¶1.1), and the context from which it is referenced depends on a template parameter (¶1.2), its point of instantiation is that of the enclosing specialization. For example, if `call<N::S>` in turn calls `helper(t)`, the point of instantiation of `helper<N::S>` is that of `call<N::S>`. Inside a template definition there is no namespace-scope declaration to anchor to, so the enclosing one is reused.

¶2 When a call uses a default argument, the point of instantiation of the default argument is the point of instantiation of the function specialization.

¶3 The rule for a *noexcept-specifier* is the same as ¶1: if it is needed by another template specialization and the context that needs it depends on a template parameter, it takes that specialization's point of instantiation (¶3.1, ¶3.2); otherwise it immediately follows the namespace-scope declaration that needs it. Default arguments and noexcept-specifiers are each instantiated separately on demand ([[temp.inst]]), so they need their own points of instantiation.

### Classes: immediately before (¶4)

```cpp error
namespace N { struct A { }; }
template<class T> struct H {
  char buf[probe(T{})];      // probe(T{}) is a dependent call
};

int x = sizeof(H<N::A>);     // the point of instantiation of H<N::A> is before this line

namespace N { constexpr int probe(A) { return 4; } }
```

¶4 For a class template specialization, a class member template specialization, or a specialization of a member class of a class template, the point of instantiation immediately precedes the namespace-scope declaration or definition that refers to it. In the example above, instantiation happens before the declaration of `x`, when `N::probe` hasn't been declared yet, so the program is ill-formed. Moving `N::probe` before `x` fixes it.

Classes go before because the declaration that refers to one usually needs its complete definition: parsing `int x = sizeof(H<N::A>);` requires knowing the size of `H<N::A>`. A function can be referred to with just a declaration, and its definition can be generated later.

The nested case also mirrors functions: when referenced from another template specialization (¶4.1), in a context that depends on a template parameter (¶4.2), and not previously instantiated (¶4.3), the point of instantiation is immediately before that of the enclosing template.

### Virtual functions, explicit instantiation and expansion statements (¶5, ¶6, ¶8)

¶5 The point of instantiation of an implicitly instantiated virtual function immediately follows that of its enclosing class template specialization. Virtual functions go into the vtable, which is needed as soon as the class is instantiated.

¶6 An explicit instantiation definition (`template void f<int>(int);`, see [[temp.explicit]]) is also a point of instantiation for the specialization it specifies.

¶8 {{c++26}} The point of instantiation of the body of an expansion statement ([[stmt.expand]]) is that of the enclosing templated entity; outside a template, it immediately follows the namespace-scope declaration containing it. Expansion statements instantiate their bodies even in non-template functions, so this is specified separately.

### The end of the translation unit is also a point of instantiation (¶7)

¶7 A function specialization of the kind described in paragraph 1 can have several points of instantiation in one translation unit. Besides the positions described above, the end of the translation unit's declaration sequence is also a point of instantiation (¶7.1); if the point of instantiation is in a private module fragment, the end of the translation unit is too (¶7.2). A class template specialization has at most one point of instantiation in a translation unit. Any specialization can have points of instantiation in several translation units.

!!! std
    If two different points of instantiation give a template specialization different meanings according to the one-definition rule, the program is ill-formed, no diagnostic required.

If the points of instantiation give different meanings per the ODR (one-definition rule, [[basic.def.odr]]), the program is **ill-formed, no diagnostic required** (IFNDR): the standard places no requirements on the program, the compiler needn't report an error, and the generated program may do anything ([[intro.compliance]]).

Counting the end of the translation unit as a point of instantiation lets compilers defer instantiation of function templates and process it all at the end. Clang and GCC both do this. The standard accepts both positions as valid and requires them to agree in meaning.

```cpp ifndr title="two_pois.cpp"
#include <cstdio>
namespace N { struct S { }; }
template<class T> int g(T t) { return h(t); }

int a = g(N::S{});   // point 1: right after this declaration, N::h not yet declared
                     // point 2: end of the translation unit, N::h declared

namespace N { int h(S) { return 42; } }
int main() { std::printf("%d\n", a); }
```

By point 1, ADL can't find `h` and the program is ill-formed; by point 2, it calls `N::h`. The two points mean different things: IFNDR. Clang 23 instantiates `g<N::S>` at the end of the translation unit, accepts the program and prints `42`.

Make `g` `constexpr`, and Clang instantiates it immediately when used (constant evaluation needs its definition) and reports `h` as undeclared. Both outcomes conform, because the program was IFNDR to begin with.

Declaring an overload late can likewise lead different implementations to different conclusions:

```cpp ifndr
namespace N { struct S { }; }
template<class T> void call(T t) { touch(t); }
namespace N { void touch(S) { } }
void use() { call(N::S{}); }   // point 1: only touch(S)
namespace N { void touch(const S&) { } }
// point 2: two touch overloads, the call is ambiguous
```

Clang 23 instantiates at the end of the translation unit and reports the call to `touch` as ambiguous.

Across translation units it's the same: if `g<N::S>` in two translation units sees different `h`, it's IFNDR. Each translation unit instantiates separately and emits mergeable weak symbols, the linker keeps an arbitrary one, and the inconsistency is never detected.

!!! lawyer "An explicit specialization declared after use"
    Another related rule is in [[temp.expl.spec#7]]: an explicit specialization must be declared before every use that would cause implicit instantiation.

    ```cpp error
    template<class T> void show(T) { }
    void use() { show(1); }               // implicitly instantiates show<int>
    template<> void show<int>(int) { }    // error: too late
    ```

    Within one translation unit Clang can diagnose this (explicit specialization after instantiation); split across translation units it is basically undiagnosable.

## Candidate functions [temp.dep.candidate]

### The result can't depend on which headers were seen (¶1)

```cpp title="h.h"
namespace N { struct S { }; void g(S, long); }
template<class T> void call(T t) { g(t, 0); }
```

```cpp title="a.cpp"
#include "h.h"
void use() { call(N::S{}); }   // only g(S, long) is visible
```

```cpp ifndr title="b.cpp"
#include "h.h"
namespace N { void g(S, int) { } }   // a better match for g(t, 0)
```

`call<N::S>` in `a.cpp` selects `g(S, long)`. But `b.cpp` declares `g(S, int)` in the same namespace `N`, an exact match for the argument `0`.

¶1 For a dependent call, suppose lookup considered not just the template definition context and the instantiation context but all functions with external linkage declared in the associated namespaces in all translation units. If that would make the call ill-formed or find a better match, the program is {{ifndr}}. The program above is exactly this case.

Neither compilers nor linkers can reliably detect such errors. The way to avoid them is a convention: declare all overloads for a type together with the type itself, in the same header or the same module interface.

!!! history "From UB to IFNDR"
    Earlier standards made the situation in ¶1 undefined behavior; the current wording is ill-formed, no diagnostic required.

### Dependent calls in modules (¶2–¶5)

¶2–¶5 are all examples showing how modules affect ADL in the instantiation context. Two pieces of background are needed:

- The part of a module unit after a leading `module;` is the **global module fragment** ([[g:global-module-fragment]]), used to `#include` traditional headers. Declarations in it that the module unit doesn't use are discarded ([[module.global.frag]]) and aren't visible to importers.
- The instantiation context is more than the point of instantiation. For nested instantiations it also includes the enclosing specialization's instantiation context; when a template is defined in an interface unit of module M and the point of instantiation isn't in an interface unit of M, it also includes the end of M's primary module interface unit ([[module.context#3]]). ADL in the instantiation context ignores declarations from other translation units that are attached to the global module and are either discarded or have internal linkage ([[basic.lookup.argdep#4]]).

Example 2 (¶3) shows customization points working as usual with modules:

```cpp title="Module interface unit of Std"
export module Std;
export template<typename Iter>
void indirect_swap(Iter lhs, Iter rhs) {
  swap(*lhs, *rhs);   // unqualified lookup can't find swap; only ADL can
}
```

```cpp ok title="Module interface unit of M"
export module M;
import Std;

struct S { /* ... */ };
void swap(S&, S&);        // #1, not exported

void f(S* p, S* q) {
  indirect_swap(p, q);    // finds #1 through ADL in the instantiation context
}
```

`Std` can't see `M`, and `#1` isn't exported, but the point of instantiation of `indirect_swap<S*>` is in `M`, and ADL from there finds `swap(S&, S&)`. We compiled and ran an executable version of this example with Clang 23, and it behaved as expected.

The key points of the other three examples:

- Example 1 (¶2): the global module fragment of module `M1` contains `Q::g_impl`, and the definition of template `g` calls it with the non-dependent argument `Q::X{}`, so ADL at the definition finds it. That counts as a use, so `g_impl` isn't discarded, and other modules instantiating `g` can call it.
- Example 3 (¶4): `t + t` in a template is also treated as a dependent call; it's enough for `operator+` to be visible in the instantiation context.
- Example 4 (¶5): module `C1` does `#include "foo.h"` in its global module fragment, and `dog(foo, foo)` from it isn't used by `C1`, so it's discarded; then `dog(t, t)` in a template instantiated elsewhere through `C1` can't find it, which is ill-formed. `cat` from the same header is a hidden friend of `foo` and can still be found per item 4.2 (when the definition of an associated class is reachable, its friends are found). If a header unit is imported instead, `dog` isn't discarded, is visible at the end of `C2`'s interface unit, and the call is valid.

!!! impl "Clang doesn't implement the discarding rule"
    Clang 23 doesn't report an error for the ill-formed case in Example 4: it doesn't fully implement discarding of declarations in the global module fragment. Per the standard it's ill-formed here, and code relying on this leniency isn't portable.

## Common misconceptions

!!! pitfall "All names are looked up again at instantiation"
    Instantiation only adds ADL. Ordinary unqualified lookup stays at the template definition, so overloads declared after the definition that take only fundamental types like `int`, `double` or plain pointers are never found by a dependent call.

!!! pitfall "Header order doesn't affect the result"
    Code that declares a customization function after using the template often happens to work on Clang and GCC because of instantiation at the end of the translation unit. Switch implementations, or make the function `constexpr`, and it may fail. Declare all overloads and specializations before the first use of the template.

## Questions

!!! question "Question 1"
    ```cpp
    #include <vector>
    template<class T> void print_all(const std::vector<T>& v) {
      for (auto& x : v) print(x);
    }
    struct Point { int x, y; };
    void print(const Point&);
    int main() { print_all(std::vector<Point>{}); }
    ```
    Can `print(x)` find `::print(const Point&)`? What if `Point` is replaced by `int` and `print` by `void print(int);`?

<details markdown="1">
<summary>Answer</summary>

Yes. The associated namespace of `Point` is the global namespace, and ADL in the instantiation context finds `print(const Point&)` there; it was declared before the point of instantiation.

With `int`, it can't be found. `int` has no associated namespaces, so ADL searches nothing; ordinary unqualified lookup happens only at the template definition, when `print(int)` hasn't been declared yet. The associated namespace `std` of `std::vector<int>` is irrelevant, since the argument of `print` is an `int`. Clang 23 reports: call to function 'print' that is neither visible in the template definition nor found by argument-dependent lookup.
</details>

!!! question "Question 2"
    Why does a class template specialization have at most one point of instantiation in a translation unit, while a function template specialization can have several?

<details markdown="1">
<summary>Answer</summary>

Once a class template specialization is instantiated, it is a complete type, and later code depends on its size, members and bases. Allowing it to be instantiated again at the end of the translation unit could invalidate decisions already made based on the first instantiation. The definition of a function template specialization only affects the generated code, not type checking of earlier declarations, so it can be deferred to the end. The standard therefore also counts the end as a point of instantiation for function specializations and requires the two to agree in meaning (¶7).
</details>

!!! question "Question 3"
    In `template<class T> struct D : Base<T> { void f() { g(*this); } };`, if `Base<T>` has a member function `g`, is it called at instantiation?

<details markdown="1">
<summary>Answer</summary>

No. `*this` has type `D<T>`, so `g(*this)` is a dependent call. But its candidates come only from unqualified lookup at the definition and from ADL: dependent bases aren't searched at the definition, and ADL only finds namespace-scope functions and friends of associated classes, not member functions. The result is either some `g` in a namespace or an ill-formed program. To call the member, write `this->g(*this)`.
</details>
