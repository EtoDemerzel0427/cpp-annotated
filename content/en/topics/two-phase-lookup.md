---
title: Two-phase lookup and dependent names
summary: "When, from where and in what way each name in a template is looked up: non-dependent names are bound at the definition, dependent calls get additional ADL at instantiation, and modules decide which declarations are visible at instantiation."
tags: templates, two-phase lookup, dependent names, ADL, modules
updated: 2026-10-19
---

!!! tldr
    - Names in a template that don't depend on template parameters are looked up at the definition and bound permanently; a better overload declared later is invisible to the template.
    - Ordinary unqualified lookup for a dependent call `f(t)` is also done only at the definition; at instantiation only ADL is added, so only functions in the associated namespaces of the argument types can be declared after the template.
    - Members of dependent base classes aren't searched at the definition; you have to write `this->x` to find them, or the name may silently bind to an entity of the same name in an enclosing scope.
    - When the same specialization has different meanings at different points of instantiation, the program is IFNDR; different compilers may give different results.
    - With modules, what is visible at instantiation is determined by the instantiation context, which includes the end of the module interface containing the template.

## Why wasn't the better match chosen

```cpp run ok
#include <cstdio>
void f(int) { std::puts("f(int)"); }
template<class T> void g(T t) { f(t); }
void f(double) { std::puts("f(double)"); }
int main() { g(1.0); }
```

The program prints `f(int)`. When `g<double>` is called, `f(double)` has already been declared and is an exact match, yet it isn't chosen.

[[g:two-phase-lookup|Two-phase name lookup]] isn't a formal term in the standard but a collective name for a set of rules. It has to serve two goals at once: mistakes in a template should be caught at its definition, and at instantiation the functions provided by the caller should still be usable.

- The first phase is at the definition. The compiler fully parses the template definition. Names that don't depend on template parameters are called **non-dependent names**; they are looked up here and bound permanently, and constructs that don't depend on template parameters are checked here, with errors reported on the spot.
- The second phase is at instantiation. Once the template arguments are known, names that depend on template parameters, **dependent names**, are looked up. But for dependent unqualified function calls, this phase only adds ADL (argument-dependent lookup, which looks for functions in the associated namespaces of the argument types; see [[basic.lookup.argdep]]); it doesn't redo ordinary unqualified lookup.

Back to the example above. The argument type of `f(t)` depends on `T`, so it's a dependent call. Ordinary unqualified lookup happens at the definition, where only `f(int)` is visible. At instantiation ADL is added, but `double` is a fundamental type with no associated namespaces, so ADL finds nothing. `f(double)` never enters the candidate set, and `1.0` is converted to `int`.

## When a name is looked up

For a name `n` in a template definition, ask these questions in order:

| Question | Yes | No |
|---|---|---|
| 1. Is `n` dependent? ([[temp.dep]]) | Go to question 2 | Looked up once at the definition and bound, never changes afterwards ([[temp.res.general#1]]) |
| 2. Is `n` a qualified name (`X::n`, `x.n`, `p->n`)? | Go to question 3 | Go to question 4 |
| 3. Is the lookup context the current instantiation? | Looked up first at the definition; deferred if there are dependent bases and it isn't found. Looked up again at instantiation, and if the two results differ, it is ambiguous ([[temp.dep.type#5]], [[temp.dep.type#6]]) | After substituting template arguments, qualified lookup in the now-known class or namespace |
| 4. Is `n` the function name in a dependent call `n(args)`? | Ordinary unqualified lookup only at the definition; ADL at the definition and at every point of the instantiation context ([[basic.lookup.argdep#4]]) | Other dependent unqualified names (such as a dependent `operator T` or `operator=`) are looked up at instantiation |

The **current instantiation** is the class template itself as referred to within its own definition, such as `*this` in a member function of `C<T>`.

A name is dependent in the following cases:

| Form | Reason |
|---|---|
| `T::x`, `Base<T>::x` | The lookup context is a dependent type (¶5.2 of [[temp.dep.type#5]]) |
| `t.x`, `this->x`, where the type of `t` or `this` depends on `T` | The lookup context depends on `T`; or it's the current instantiation with dependent bases, and the name isn't found at the definition |
| `f(t)`, where the type of `t` depends on `T` | Dependent call (¶2.2 of [[temp.dep.general#2]]) |
| `f(ts...)` | The pack expansion makes it a dependent call (item 2.1) |
| `get<I>(x)`, where `I` is a template parameter | The template arguments of the *template-id* depend on a template parameter (item 2.3) |
| A dependent `operator T()`, `operator=` in a class template | Items 2.4, 2.5 |

The following don't make a name dependent:

- `f()`, `f(1)`, `f(sizeof(T))`: none of the arguments is type-dependent. The last one is easy to misread: `T` appears in `sizeof(T)`, but its type is always `size_t`.
- Names in dependent base classes. At the definition, dependent bases aren't searched at all, unless one of the forms in the table above makes the name dependent (see Puzzle 3).

## Puzzles

For each, guess the output first, then look at the answer. All examples were verified with Clang 23.

### Puzzle 1: also declared late, but found this time

```cpp run ok
#include <cstdio>
template<class T> struct Box { T v; };
template<class T> void show(const Box<T>& b) { describe(b); }
struct Tag { };
void describe(const Box<Tag>&) { std::puts("Box<Tag>"); }
int main() { show(Box<Tag>{}); }
```

<details markdown="1">
<summary>Answer: Box&lt;Tag&gt;</summary>

The associated entities of `Box<Tag>` include `Box<Tag>` itself and its type template argument `Tag` ([[basic.lookup.argdep#3]]), whose associated namespace is the global namespace. ADL at instantiation finds the later-declared `describe` in the global namespace. Compared with the opening example, the only difference is whether the argument type has an associated namespace.
</details>

### Puzzle 2: a global operator hidden by a declaration of the same name

```cpp error
#include <iostream>
#include <vector>
std::ostream& operator<<(std::ostream& os, const std::vector<int>& v) { return os << v.size(); }

namespace app {
    struct Widget { };
    std::ostream& operator<<(std::ostream& os, Widget) { return os << "W"; }
    template<class T> void log(const T& t) { std::cout << t << '\n'; }
}
int main() { app::log(std::vector<int>{1, 2}); }
```

<details markdown="1">
<summary>Answer: fails to compile</summary>

The global `operator<<(ostream&, const vector<int>&)` is declared before the template. But unqualified lookup from inside `app::log` first finds `app::operator<<(ostream&, Widget)` in namespace `app`. Unqualified lookup stops at the first scope where it finds the name, so the global one is hidden. The only associated namespace for ADL is `std`, and `std` has no `operator<<` accepting a `vector<int>`. There is no viable function in the candidate set.

Delete `Widget`'s `operator<<` and the program compiles and prints `2`. So don't define operators for other people's types in the global namespace: whether they can be found depends on whether the namespace of the call site has a declaration of the same name. Wrap the type instead, or define the operator in the type's associated namespace; for types in `std`, the latter isn't allowed.
</details>

### Puzzle 3: silently bound somewhere else

```cpp run ok
#include <cstdio>
void g() { std::puts("::g"); }
template<class T> struct Base { void g() { std::puts("Base<T>::g"); } };
template<class T> struct D : Base<T> {
    void f() { g(); }
};
int main() { D<double>{}.f(); }
```

<details markdown="1">
<summary>Answer: ::g</summary>

`g()` has no arguments, isn't a dependent call, and is looked up at the definition. The **dependent base class** (a base class whose type depends on a template parameter) `Base<T>` isn't searched at the definition ([[temp.dep.type#3]]). At this point the compiler doesn't yet know what's in `Base<T>`; for instance `Base<double>` might be explicitly specialized to have no `g`. So lookup continues outward, finds the global `::g`, and binds it permanently. Old versions of MSVC that didn't implement two-phase lookup print `Base<T>::g`. To call the base class version, write `this->g()`, making it a dependent name.
</details>

### Puzzle 4: two points of instantiation

```cpp ifndr
#include <cstdio>
namespace N { struct S { }; }
template<class T> int g(T t) { return h(t); }
int a = g(N::S{});
namespace N { int h(S) { return 42; } }
int main() { std::printf("%d\n", a); }
```

<details markdown="1">
<summary>Answer: IFNDR; Clang prints 42</summary>

`g<N::S>` has two **points of instantiation** ([[temp.point#7]]): one immediately after `int a = ...;`, where `N::h` hasn't been declared yet and the call is ill-formed; and one at the end of the translation unit, where ADL can find `N::h`. The two give different meanings, so the program is IFNDR (ill-formed, no diagnostic required).

Clang defers instantiation of function templates to the end of the translation unit, so it accepts the code and prints 42. If `g` is made `constexpr`, Clang instantiates it immediately and reports `use of undeclared identifier 'h'`. For the same IFNDR code, the result depends on which point the compiler instantiates at.
</details>

### Puzzle 5: class templates get no second chance

```cpp error
namespace N { struct A { }; }
template<class T> struct H { char buf[probe(T{})]; };
int x = sizeof(H<N::A>);
namespace N { constexpr int probe(A) { return 4; } }
```

<details markdown="1">
<summary>Answer: fails to compile; this is genuinely ill-formed</summary>

The point of instantiation of a class template specialization is immediately before the declaration that refers to it, and there is at most one per translation unit ([[temp.point#4]], [[temp.point#7]]). `H<N::A>` is instantiated before `int x`, when `probe` hasn't been declared yet, and ADL can't find it either. There is no end-of-translation-unit point to come to the rescue. Compared with Puzzle 4: function templates can wait, class templates can't.
</details>

### Puzzle 6: writing `this->` causes the error

```cpp error
struct A { int m; };
struct B { int m; };
template<class T> struct C : A, T {
    int f() { return this->m; }
};
template int C<B>::f();
```

<details markdown="1">
<summary>Answer: fails to compile, ambiguous</summary>

The lookup context of `this->m` is the current instantiation `C<T>`. At the definition, `A::m` is found in the non-dependent base `A`. When `C<B>` is instantiated, by [[temp.dep.type#6]] the lookup is done again in the instantiation context, and this time the dependent base `B` takes part too, finding `A::m` and `B::m`; that differs from the result at the definition, so it is ambiguous.

Replacing `this->m` with an unqualified `m` actually works. The unqualified `m` is bound to `A::m` at the definition; the step that transforms it into `(*this).m` doesn't happen in the template definition context ([[expr.prim.id.general#2]]), so it isn't looked up again at instantiation.
</details>

### Puzzle 7: dependence without template parameters {{c++26}}

```cpp run ok
#include <cstdio>
struct C { };
void g(...) { std::puts("g(...)"); }
template<class T> void f() {
    C arr[1];
    auto [...e] = arr;
    g(e...);
}
void g(C) { std::puts("g(C)"); }
int main() { f<int>(); }
```

<details markdown="1">
<summary>Answer: g(C)</summary>

Nothing in `f` depends on `T`. But C++26 says the **structured binding pack** `e` is type-dependent (¶3.6 of [[temp.dep.expr#3]]), and `g(e...)` is a pack expansion, so it becomes a dependent call. Ordinary unqualified lookup still happens at the definition and sees only `g(...)`; ADL is deferred to instantiation and finds the later-declared `g(C)` in `C`'s associated namespace (the global namespace), which matches better than `g(...)`. If it were written `auto [x] = arr; g(x);`, it would be a non-dependent call, and only `g(...)` would be visible at the definition.
</details>

### Puzzle 8: `static_assert(false)`

```cpp run ok
template<class T> void never() { static_assert(false, "boom"); }
template<class T> int pick(T) {
    if constexpr (sizeof(T) <= 8) return 1;
    else static_assert(false, "too big");
}
int main() { return pick(0) - 1; }
```

<details markdown="1">
<summary>Answer: well-formed since C++23</summary>

`never` is never instantiated; in `pick<int>` the `else` branch is discarded and not instantiated. C++23's [[P2593R1]] says a failed `static_assert` is ignored when deciding whether a template can generate a valid specialization (¶6.1 of [[temp.res.general#6]]), and a static assertion evaluated in a template definition context has no effect ([[dcl.pre#13]]).

Before C++23 this was IFNDR, and GCC and Clang reported an error right at the definition. Back then you had to write `static_assert(dependent_false<T>)` to manufacture a dependence.
</details>

## Why the rules are the way they are

C++ wants three things here at once:

1. **Early diagnosis**. Mistakes by the template's author should be found when the template is written, not when a user instantiates it and sees a screenful of errors. This requires parsing and checking templates at the definition, which is why `typename` and `template` are needed to disambiguate.
2. **Stable meaning**. A template's behavior is determined by the declarations its author sees at the definition, and isn't changed by some function of the same name that a user declares before instantiation (the opening example, Puzzle 3). That's why non-dependent names are bound at the definition and dependent bases aren't searched.
3. **Customization points**. Generic code must be able to call `swap`, `begin` and `operator<<` for user types, and these functions don't exist yet when the template is defined. That's why ADL is added at instantiation. Only ADL is added because it finds only functions related to the argument types, which are interfaces the type's author provided deliberately, not functions that merely happen to share the name.

Most of the remaining complexity comes from the fact that "at instantiation" isn't a single point in time: a specialization may be used in several places and instantiated in several translation units, and the compiler may defer to the end of the translation unit. The standard allows all of these implementation strategies, and any program that would get different results because of them is IFNDR ([[temp.point#7]], [[temp.dep.candidate#1]], ¶6.8 of [[temp.res.general#6]]).

## Instantiation contexts in modules

Without modules, what's visible at instantiation is the declarations before the point of instantiation in the same translation unit. With modules, the template is defined in module A, instantiation happens in a translation unit that imports A, and the argument types may come from a third module. C++20 uses the **instantiation context** ([[module.context]]) to answer what's visible at that point.

### An instantiation context is a set of points

By [[module.context#1]], an instantiation context is a set of points in the program. It determines which declarations ADL can find ([[basic.lookup.argdep]]), and which declarations are **reachable** ([[module.reach]]) in the context of some declaration or template instantiation.

| Situation | The instantiation context contains | Paragraph |
|---|---|---|
| Implicit definition of a defaulted function, such as a `= default` `operator==` | The instantiation context of the class definition, plus that of the construct that caused the implicit definition | [[module.context#2]] |
| A template's point of instantiation arises from an enclosing specialization | The instantiation context of the enclosing specialization; if the template is defined in an interface unit of module M and the point of instantiation isn't in it, also the end of M's primary module interface unit | [[module.context#3]] |
| Template instantiation caused by the implicit definition of a defaulted function | That defaulted function's instantiation context | [[module.context#4]] |
| Instantiation of other template specializations | That template's point of instantiation | [[module.context#5]] |
| Implicit instantiation caused by constant evaluation {{c++26}} | Every point in the evaluation context ([[expr.const.reflect]]) | [[module.context#6]] |
| Other cases | That point itself | [[module.context#7]] |

Paragraph 8 says the instantiation context contains only the points listed above. Paragraph 3 is the key one: it brings the end of the interface of every module along the chain into the instantiation context.

### Reachability depends on the modules in the chain

Here is the example from [[module.context#9]]:

```cpp title="TU #1"
export module stuff;
export template<typename T, typename U> void foo(T, U u) { auto v = u; }
export template<typename T, typename U> void bar(T, U u) { auto v = *u; }
```

```cpp title="TU #2"
export module M1;
import "defn.h";        // provides struct X {};
import stuff;
export template<typename T> void f(T t) {
    X x;
    foo(t, x);
}
```

```cpp title="TU #3"
export module M2;
import "decl.h";        // provides struct X; (declaration only)
import stuff;
export template<typename T> void g(T t) {
    X *x;
    bar(t, x);
}
```

```cpp title="TU #4"
import M1;
import M2;
void test() {
    f(0);
    g(0);
}
```

`f(0)` is valid. The instantiation context of `foo<int, X>` is the end of TU #1, the end of TU #2, and the call site of `f(0)`. At the end of TU #2, the definition of `X` from the header unit `defn.h` is reachable, providing the complete type that `auto v = u;` needs.

Whether `g(0)` is valid is unspecified. The instantiation context of `bar<int, X>` is the end of TU #1, the end of TU #3, and the call site of `g(0)`. `*u` needs the definition of `X`, but TU #3 imported only a declaration. TU #4 indirectly imports `defn.h` through `M1`; whether that makes it reachable is unspecified under [[module.reach]].

### Discarded declarations don't take part

By [[basic.lookup.argdep#4]], when ADL is performed for a dependent name from points in the instantiation context, declarations are also ignored if they appear in another translation unit, are attached to the global module, and are either discarded ([[module.global.frag]]) or have internal linkage.

The practical meaning: if a module unit `#include`s a header in its global module fragment and the module itself doesn't use some function from it, that function is discarded. When a downstream translation unit instantiates your template, ADL can't find it (the `dog` example in [[temp.dep.candidate]]). The fix is to actually use it in the module unit, for example by referring to it non-dependently in a template definition, or to import a header unit instead.

### A runnable example

The example in [[temp.dep.candidate]] of a customization point `swap` working across modules can be compiled and run with Clang:

```cpp title="Std.cppm"
export module Std;
export template<typename Iter>
void indirect_swap(Iter lhs, Iter rhs) { swap(*lhs, *rhs); }
```

```cpp title="M.cppm"
export module M;
import Std;
struct S { int v; };
void swap(S& a, S& b) { int t = a.v; a.v = b.v; b.v = t; }   // not exported
export int f() { S a{1}, b{2}; indirect_swap(&a, &b); return a.v; }
```

```cpp ok title="main.cpp"
import M;
#include <cstdio>
int main() { std::printf("%d\n", f()); }   // prints 2
```

Build commands:

```text
clang++ -std=c++2c --precompile Std.cppm -o Std.pcm
clang++ -std=c++2c --precompile -fmodule-file=Std=Std.pcm M.cppm -o M.pcm
clang++ -std=c++2c -fmodule-file=Std=Std.pcm -fmodule-file=M=M.pcm main.cpp M.pcm Std.pcm -o main
```

`swap(S&, S&)` isn't exported, and module `Std` couldn't possibly see it. But the point of instantiation of `indirect_swap<S*>` is in module `M`, and ADL finds it from there.

## Checklist for writing template code

1. Always access members of dependent bases with `this->`. Don't use `Base<T>::`, which turns off virtual dispatch for virtual functions.
2. Write `typename` before dependent type names. Since C++20 it can be omitted in type-only contexts ([[temp.res.general#4]]), but it's still needed for declarations at block scope and in template arguments.
3. Put `template` before dependent member templates, as in `t.template get<0>()` and `T::template rebind<U>`, otherwise `<` is taken as less-than.
4. Define customization points (`swap`, `begin`, `operator<<` and so on) in the same namespace and the same header as the type, so ADL can find them at any point of instantiation, avoiding IFNDR like Puzzle 4.
5. Don't overload operators for other people's types in the global namespace (Puzzle 2).
6. Declare explicit specializations before their first use ([[temp.expl.spec#7]]).
7. To call a function declared after the template definition, you can only rely on ADL; make sure it's in an associated namespace of the argument types.
8. When using modules, don't leave helper functions that templates call dependently only in an `#include` in the global module fragment. Export them, refer to them within the module, or use a header unit instead.

## Related clauses

- [[temp.res]]: where lookup starts, `typename`, type-only contexts, the list of IFNDR cases
- [[temp.local]]: injected-class-names, lookup order of template parameters
- [[temp.dep]]: dependent types, type-dependence and value-dependence, the current instantiation
- [[temp.dep.res]]: points of instantiation, candidate functions, dependent bases
- [[basic.lookup.argdep]]: ADL
- [[module.context]], [[module.reach]]: instantiation contexts and reachability in modules
