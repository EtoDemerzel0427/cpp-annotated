---
title: Namespaces
summary: "How namespaces are defined and extended again and again; at which level a using-directive makes names visible; and what unnamed namespaces, inline namespaces and namespace aliases are each for."
updated: 2026-10-19
---

!!! tldr
    - Namespaces are open: the same namespace can be reopened in many files to add members. An alias can't be used to extend a namespace.
    - `using namespace N;` introduces no names. In unqualified lookup, the members of `N` appear as if declared in the nearest enclosing namespace containing both the directive and `N`, usually the global namespace.
    - An unnamed namespace is equivalent to a name unique to the translation unit plus a using-directive; everything in it has internal linkage, types included.
    - Members of an inline namespace behave as members of the enclosing namespace for lookup, ADL and template specialization. Standard libraries use this for ABI versioning, for example libc++'s `std::__1`.
    - `namespace A::inline B::C { }` is shorthand for nested namespace definitions (C++20); the first component can't be `inline`.

## Namespaces are open [basic.namespace.general]

When two libraries both want to define `log`, `vector` and `detail::impl`, namespaces put each in its own scope. Unlike a class, a namespace's definition can be split into many pieces:

```cpp run title="namespace-open.cpp" ok
namespace lib { int a = 1; }
namespace lib { int b = 2; }        // extends lib, adding members

int main() { return lib::a + lib::b - 3; }
```

¶1 A namespace is an entity, possibly unnamed, in whose scope entities of any kind can be declared. Entities belonging to a namespace are its **members**, accessed through the namespace's name. A namespace's definition can be spread over several translation units and several modules, a property no other entity has.

¶3 A program also has a **[[g:global-namespace|global namespace]]**, to which all declarations not in any namespace belong ([[basic.scope.namespace]]). It has no declaration, so name lookup can't find it: the `::` in `::x` is part of the syntax, not a lookup of some name. The global namespace is not an unnamed namespace either.

¶2 A namespace is not attached to any named module, and names in it never have module linkage. A namespace definition is exported if it contains an exported declaration ([[module.interface]]):

```cpp title="namespace-module.cpp"
export module M;
namespace N1 {}                  // N1 is not exported
export namespace N2 {}           // N2 is exported
namespace N3 { export int n; }   // N3 is exported too, since it contains an exported declaration
```

Different modules often need to add members to the same namespace (`std`, a company's top-level namespace). If a namespace belonged to the first module that declared it, other modules couldn't reopen it.

## Definition and extension [namespace.def.general]

```text
named-namespace-definition:
    inline(opt) namespace attribute-specifier-seq(opt) identifier { namespace-body }
unnamed-namespace-definition:
    inline(opt) namespace attribute-specifier-seq(opt) { namespace-body }
nested-namespace-definition:
    namespace enclosing-namespace-specifier :: inline(opt) identifier { namespace-body }
```

¶1 A namespace definition can only appear at namespace scope; not inside a function body or a class.

¶2 When the compiler meets `namespace X { ... }`, it first looks for the name `X` in the current namespace (together with its inline namespaces, see below). If it finds the definition of some namespace N, this definition **extends** N; if it finds nothing, it introduces a new namespace name. If what it finds is something else, such as a variable or a namespace alias, the new name conflicts with it:

```cpp title="namespace-extend.cpp" error
namespace lib { int a; }
namespace lib { int b; }       // OK: extends lib

namespace Alias = lib;
namespace Alias { }            // error: Alias is an alias and can't be extended
int Thing;
namespace Thing { }            // error: conflicts with the variable Thing
```

¶3 A namespace definition is itself a declaration, so it can be nested. Lookup proceeds from the inside out as usual, and only sees declarations that have already appeared:

```cpp title="namespace-nested.cpp" ok
namespace Outer {
    int i;
    namespace Inner {
        void f() { i++; }    // Outer::i: Inner::i isn't declared yet
        int i;
        void g() { i++; }    // Inner::i
    }
}
int main() {}
```

¶5 Attributes in a namespace definition appertain to the namespace being defined or extended. The one of practical use is `[[deprecated]]`, allowed since C++17 ([[N4266]]): using its members gives deprecation warnings:

```cpp title="namespace-deprecated.cpp" ok
namespace [[deprecated("use v2")]] v1 { inline void f() {} }
namespace v2 { inline void f() {} }

int main() { v2::f(); }    // writing v1::f() would give a deprecation warning
```

## Namespace aliases [namespace.alias]

```cpp run title="namespace-alias.cpp" ok
namespace very::long_::library_name::v3 { int x = 1; }
namespace lib = very::long_::library_name::v3;

int f() { return lib::x; }
int g() {
    namespace L = lib;            // also allowed at block scope
    return L::x;
}
int main() { return f() + g() - 2; }
```

¶3 `namespace lib = ...;` declares a **[[g:namespace-alias|namespace alias]]**.

¶4 An alias is just a synonym; the namespace it refers to is its underlying entity ([[basic.pre]]). So an alias can't be used to extend a namespace (the example in the previous section), and redeclaring the same alias in the same scope must refer to the same namespace. Lookup of the name to the right of `=` considers only namespace names ([[basic.lookup.udir]]).

¶2 C++26 reflection allows `namespace X = [: r :];`, in which case the *splice-specifier* must designate a namespace, and not the global namespace.

## Using-directives [namespace.udir]

```text
using-directive:
    attribute-specifier-seq(opt) using namespace nested-name-specifier(opt) namespace-name ;
    attribute-specifier-seq(opt) using namespace splice-specifier ;
```

¶4 A **[[g:using-directive|using-directive]]** `using namespace N;` introduces no names. It only changes the path of subsequent unqualified and qualified lookup so that members of `N` can be used without qualification. To introduce one specific name into the current scope, use a using-declaration `using N::f;` ([[namespace.udecl]]):

| | using-directive `using namespace N;` | using-declaration `using N::f;` |
|---|---|---|
| Introduces a name | No, only changes the lookup path | Yes, `f` becomes a name in the current scope |
| Declarations added to `N` later | Visible (paragraph 6) | Not visible ([[namespace.udecl#9]]) |
| Allowed in a class | No (paragraph 2) | Yes, for base class members |
| Same-name declarations in this scope | No conflict; ambiguity only on use | May conflict |

### At which level the names appear (¶3)

The effect of a using-directive depends on a positional rule:

!!! std
    During unqualified name lookup, the names appear as if they were declared in the nearest enclosing namespace which contains both the *using-directive* and the designated namespace.

¶3 is a note; the normative rule is in [[basic.lookup.unqual]]. When a function contains `using namespace std;`, the nearest namespace containing both the function and `std` is the global namespace, so the names of `std` appear as if declared in the global namespace. They are no closer to the point of use than the current namespace, so same-name entities in the current namespace still hide them, and local variables all the more so.

The standard's example puts several cases together:

```cpp title="udir-nearest.cpp" error
namespace A {
    int i;
    namespace B {
        namespace C { int i; }
        using namespace A::B::C;
        void f1() { i = 5; }        // OK: C::i appears as if in B and is found before A::i
    }
    namespace D {
        using namespace B;
        using namespace C;
        void f2() { i = 5; }        // error: ambiguous, B::C::i or A::i?
    }
    void f3() { i = 5; }            // OK: A::i
}
void f4() { i = 5; }                // error: neither i is visible
```

- `f1`: the directive is in B and designates `A::B::C`. The nearest namespace containing both B and C is B, so `C::i` appears as if in B. Lookup going outward from `f1` finds it at B and never sees `A::i`.
- `f2`: for the two directives in D, `using namespace B;` and `using namespace C;`, the common enclosing namespace is A. The directive in B designating C is also carried over transitively (see the next subsection). So `C::i` appears as if in A, at the same level as `A::i`; both are variables, hence the ambiguity.
- `f4`: the global namespace has neither an `i` nor a using-directive.

### Transitivity and later declarations (¶5, ¶6)

¶5 Using-directives are transitive. If the designated namespace itself contains using-directives, the namespaces they designate are included in lookup too:

```cpp title="udir-transitive.cpp" error
namespace M { int i; }
namespace N {
    int i;
    using namespace M;
}
void f() {
    using namespace N;
    i = 7;                 // error: both M::i and N::i are visible
}
```

Here `N::i` doesn't hide `M::i`. The directive in N makes `M::i` appear as if in the global namespace, and the directive in `f` makes `N::i` appear as if in the global namespace too; they are at the same level, so it's ambiguous. Qualified lookup `N::i` has no such problem: qualified lookup looks at N's own declarations first and only looks at the targets of N's using-directives if nothing is found ([[namespace.qual]]).

¶6 Declarations added to the designated namespace after the using-directive can also be found through it once they have appeared:

```cpp title="udir-later.cpp" ok
namespace A { void f(int) {} }
using namespace A;
namespace A { void f(char) {} }

void g() { f('a'); }        // calls A::f(char)
int main() { g(); }
```

### Not allowed in a class (¶1, ¶2)

¶2 A using-directive can appear at namespace scope and block scope, but not at class scope:

```cpp title="udir-class.cpp" error
namespace M { int i; }
struct K {
    using namespace M;     // error: using-directives aren't allowed at class scope
};
```

Lookup at class scope searches for members in the class and its base classes ([[class.member.lookup]]). If using-directives were allowed, whether `K::i` should find `M::i`, and whether `M::i` counts as a member of `K`, would be unclear, so the standard forbids it outright.

¶1 The namespace name in the directive can't be dependent, i.e. can't depend on template parameters, because the lookup path must be fixed at template definition time. When writing `using namespace [: r :];` with C++26 reflection, `r` can't designate the global namespace either.

### Conflicts and overloading (¶7, ¶8)

¶7 If unqualified lookup finds the same name in two different namespaces through using-directives, and the two declarations are neither the same entity nor all functions, using the name is ill-formed ([[basic.lookup]]). Within one scope, a variable or function name hides a class with the same name; that hiding rule doesn't work across namespaces.

```cpp title="udir-conflict.cpp" error
namespace A {
    class X { };
    extern "C"   int g();
    extern "C++" int h();
}
namespace B {
    void X(int);
    extern "C"   int g();
    extern "C++" int h(int);
}
using namespace A;
using namespace B;

void f() {
    X(1);          // error: X found in both namespaces
    g();           // OK: A::g and B::g are the same function
    h();           // OK: all functions; overload resolution chooses A::h
}
```

`g()` isn't ambiguous because functions with C language linkage don't belong to namespaces in this sense: the two `extern "C" int g()` declarations declare the same function ([[dcl.link#7]]).

¶8 The order in which namespaces are searched and the relationships between using-directives don't affect overload resolution. With two functions of the same signature in D and E respectively, D's version doesn't win just because D reaches E through a using-directive:

```cpp title="udir-overload.cpp" error
namespace D {
    int d1;
    void f(char);
}
using namespace D;

int d1;              // OK: the declaration itself doesn't conflict with D::d1

namespace E {
    int e;
    void f(int);
}
namespace D {        // extends D
    int d2;
    using namespace E;
    void f(int);
}

void f() {
    d1++;            // error: ::d1 or D::d1?
    ::d1++;          // OK
    D::d1++;         // OK
    d2++;            // OK: D::d2
    e++;             // OK: E::e
    f(1);            // error: D::f(int) and E::f(int) are ambiguous
    f('a');          // OK: D::f(char)
}
```

Footnote 76 contrasts this with lookup in class hierarchies: there, one member hiding another along an inheritance path can resolve an ambiguity; names found through using-directives have no such mechanism.

## Unnamed namespaces [namespace.unnamed]

```cpp run title="unnamed-internal.cpp" ok
namespace {
    struct Helper { int v = 42; };      // the type also belongs only to this translation unit
    int compute() { return Helper{}.v; }
}
int main() { return compute() - 42; }
```

¶1 An **[[g:unnamed-namespace|unnamed namespace]]** `namespace { body }` behaves as if it were replaced by these three lines:

```text
inline(opt) namespace unique { /* empty */ }
using namespace unique;
namespace unique { body }
```

`unique` is an identifier chosen by the compiler: all unnamed namespaces in one translation unit use the same one, and it differs from every other identifier in the program. `inline` appears if and only if the original definition had `inline`, and the attributes appertain to `unique`.

These three lines determine everything about unnamed namespaces. The first line declares the namespace so that the using-directive on the second has something to designate; the second line lets members be used unqualified in the enclosing scope; the third puts the contents in. Unnamed namespaces within one translation unit are the same one and can be reopened; those in different translation units are all different.

```cpp title="unnamed-namespace.cpp" error
namespace { int i; }             // unique::i
void f() { i++; }                // unique::i++

namespace A {
    namespace {
        int i;                   // A::unique::i
        int j;                   // A::unique::j
    }
    void g() { i++; }            // A::unique::i++
}

using namespace A;
void h() {
    i++;                         // error: unique::i or A::unique::i?
    A::i++;                      // OK: A::unique::i
    j++;                         // OK: A::unique::j
}
```

The `i++` in `h` is ambiguous: by the positional rule for using-directives, `::unique::i` and `A::unique::i` both appear as if declared in the global namespace.

### Internal linkage

This subclause doesn't mention linkage; the rule is in [[basic.link#4]]: an unnamed namespace, and any namespace declared directly or indirectly within one, has internal linkage, and the variables, functions, classes and templates declared in it have internal linkage as a result. Names with internal linkage are visible only within their translation unit; a same-name declaration in another translation unit is a different entity.

So the unnamed namespace is the standard way to express "private to this file". It is more general than `static`, because `static` can't be applied to types.

!!! impl "Mangled names"
    The Itanium ABI (the C++ ABI used by GCC and Clang on Linux and macOS) encodes the unnamed namespace as `_GLOBAL__N_1`. The symbol for `compute` above under Clang 23 is `_ZN12_GLOBAL__N_17computeEv`, which `nm` shows as lowercase `t`, i.e. a local symbol that doesn't take part in cross-translation-unit linking. Internal linkage also helps optimization: the compiler knows all call sites and can freely inline or delete unused functions.

!!! pitfall "Unnamed namespaces in headers"
    Every translation unit that includes the header gets its own separate entities. If an `inline` function or template in the header uses those entities, its definitions in different translation units refer to different entities, violating the ODR ([[basic.def.odr]]). Such a violation is ill-formed, no diagnostic required: neither the compiler nor the linker may report it, and the program's behavior is not guaranteed.

## Inline namespaces

¶4 A namespace whose definition starts with `inline` is an **[[g:inline-namespace|inline namespace]]**. When extending it, `inline` may be written or omitted, but it may only be written if the definition that first declared the name had `inline`:

```cpp title="inline-reopen.cpp" error
namespace N {}
inline namespace N {}      // error: N wasn't originally inline
inline namespace M {}
namespace M {}             // OK: inline may be omitted when extending (Clang warns)
```

### Members behave as members of the enclosing namespace (¶6, ¶7)

¶6 Members of an inline namespace can be used in most respects as if they were members of the enclosing namespace. Specifically, four points:

1. ADL: whenever either the inline namespace or its enclosing namespace is added to the set of associated namespaces, the other is added too ([[basic.lookup.argdep]]).
2. Unqualified lookup: a using-directive designating it is implicitly inserted in the enclosing namespace, as with unnamed namespaces.
3. Templates: templates in it can be partially specialized, explicitly instantiated and explicitly specialized in the enclosing namespace, as if they were members of the enclosing namespace.
4. Qualified lookup: when looking up `enclosing::name`, members of the inline namespace are considered as well, even if the enclosing namespace itself has a `name` ([[namespace.qual]]).

Point 4 differs from an ordinary using-directive. With an ordinary using-directive, `N::x` looks at N itself first and stops if N has an `x`; with an inline namespace, both are considered together:

<div class="compare" markdown="1">

```cpp error
namespace N {
  inline namespace V { int x; }
  int x;
}
int a = N::x;  // error: ambiguous
```

```cpp ok
namespace N {
  namespace V { int x; }
  using namespace V;
  int x;
}
int a = N::x;  // OK: N's own x
```

</div>

¶7 These properties are transitive: if N contains an inline namespace M and M contains an inline namespace O, members of O can be used as if they were members of M or N. The transitive closure of all inline namespaces in N is N's **[[g:inline-namespace-set|inline namespace set]]**.

When extending a namespace, as described earlier, the compiler's search also covers this set. So after `namespace std { inline namespace __1 { namespace ranges {} } }`, writing `namespace ranges { ... }` in `std` extends `std::__1::ranges` rather than creating a new `std::ranges`.

### Use: library versioning

Inline namespaces were added in C++11 for library version evolution ([[N2535]]). Suppose the second version of a library needs to change the layout of `Widget`. If it is changed directly, object files compiled against the old headers and linked with the new library disagree about `Widget` with no indication at all. With inline namespaces you can write:

```cpp run title="versioning.cpp" ok
namespace lib {
    namespace v1 {
        struct Widget { int a; };
        inline int use(Widget w) { return w.a; }
    }
    inline namespace v2 {               // the current default version
        struct Widget { int a; long b; };
        inline int use(Widget w) { return w.a + static_cast<int>(w.b); }
        template<class T> struct Box { T t; };
    }
}

// specialize v2's template in lib (point 3)
template<> struct lib::Box<int> { int special; };

int main() {
    lib::Widget w{1, 2};       // actually lib::v2::Widget
    lib::v1::Widget old{3};    // the old version can still be used explicitly
    lib::Box<int> b{4};
    return lib::use(w) + lib::v1::use(old) + b.special - 10;
}
```

Source code writes `lib::Widget` without needing to know the version number; but the mangled name contains `v2` (`lib::v2::Widget` is encoded as `N3lib2v26WidgetE`). So mixing old and new object files gives a link error instead of a run-time layout mismatch.

!!! impl "Inline namespaces in standard libraries"
    - libc++ puts nearly everything in `std::__1` (the name is configurable through `_LIBCPP_ABI_NAMESPACE`), which is why `std::string`'s mangled name on macOS contains `NSt3__1`.
    - When libstdc++ changed the layout of `std::string` and `std::list` in GCC 5 (C++11 forbade copy-on-write `string` and required constant-time `list::size()`), it put the new versions in the inline namespace `std::__cxx11`, combined with GCC's `abi_tag` attribute so that the mangled names of functions returning these types change too.
    - Because inline namespaces are transparent to ADL and template specialization, user specializations of `std::hash` keep working.

## Nested namespace definitions (¶8)

¶8 `namespace E::I { B }` is equivalent to `namespace E { namespace I { B } }`; if `inline` is written before `I`, the inner one is an inline namespace. The components of the *enclosing-namespace-specifier* can also have `inline`, and are expanded recursively:

```cpp title="nested-namespace-def.cpp" error
namespace A::inline B::C {     // C++20
    int i;
}
// equivalent to namespace A { inline namespace B { namespace C { int i; } } }
int j = A::C::i + A::B::C::i;  // OK: both forms work

namespace X::Y { }             // OK (C++17)
inline namespace Z::W { }      // error: can't start with inline
```

C++17 introduced `namespace a::b::c` ([[N4230]]), with no component allowed to be inline. C++20's [[P1094R2]] allows `inline` on any component except the first. The first is still not allowed, because which component the `inline` in `inline namespace A::B` would modify is ambiguous; to make the first component inline, you have to use the traditional form.

## History

!!! history
    - C++98 already had namespaces, unnamed namespaces, namespace aliases and using-directives. Back then, members of unnamed namespaces had external linkage; it was just that nobody else could write their names. C++98 also deprecated `static` on namespace-scope objects, recommending unnamed namespaces instead.
    - C++11 added inline namespaces ([[N2535]]); members of unnamed namespaces were given internal linkage, and the deprecation of `static` was withdrawn accordingly.
    - C++17 added `namespace a::b::c` ([[N4230]]), and namespaces can have attributes ([[N4266]]).
    - C++20 allowed `inline` in nested namespace definitions ([[P1094R2]]); with modules, namespaces were specified not to be attached to modules.
    - C++26 static reflection added `namespace X = [: r :];` and `using namespace [: r :];`.

## Common misconceptions

!!! pitfall "A using-directive in a function puts names closest to the point of use"
    Members of `N` appear as if declared in the nearest common enclosing namespace of `N` and the current position, usually the global namespace. Same-name entities in the current namespace and in local scopes hide them.

!!! pitfall "A same-name declaration in the enclosing namespace hides members of an inline namespace"
    It doesn't. In `namespace N { inline namespace V { int x; } int x; }`, `N::x` is ambiguous; only with an ordinary using-directive is `N::x` N's own `x`.

!!! pitfall "`using namespace std;` in a header is just a matter of style"
    It makes every translation unit that includes the header see all of `std`'s names in the global namespace, including names the standard adds in the future. Every name the standard library adds can make previously unambiguous code ambiguous.

## Questions

!!! question "Question 1"
    In the code below, why is `int l = k;` ambiguous while `int m = i;` isn't?

    ```cpp
    namespace A { int i; }
    namespace B {
        int i;
        int j;
        namespace C {
            namespace D {
                using namespace A;
                int j;
                int k;
                int a = i;
            }
            using namespace D;
            int k = 89;
            int l = k;
            int m = i;
            int n = j;
        }
    }
    ```

<details markdown="1">
<summary>Answer</summary>

- `int a = i;` (in D): `using namespace A;` makes `A::i` appear as if in the global namespace, since the nearest namespace containing both D and A is the global namespace. Lookup goes through D, C, B, finds `B::i` in B and stops; `A::i` is hidden.
- `int l = k;` (in C): `using namespace D;` makes D's members appear as if in C. C itself also has `k`, so at C's level there are both `C::k` and `D::k`; both are variables, so it's ambiguous.
- `int m = i;`: D has no `i`; the `using namespace A;` in D takes effect transitively, and `A::i` still appears as if in the global namespace. Lookup goes through C and B and finds `B::i` in B.
- `int n = j;`: `D::j` appears as if in C and is found before `B::j`.
</details>

!!! question "Question 2"
    libc++ puts `std::vector` in the inline namespace `std::__1`. What would go wrong if it used an ordinary namespace `__1` with `using namespace __1;` in `std` instead?

<details markdown="1">
<summary>Answer</summary>

There are at least two differences. First, ADL: the associated namespaces of `std::__1::vector<int>` would be only `std::__1`, no longer including `std`, so functions declared directly in `std` wouldn't be found by ADL. Second, qualified lookup: for `std::name`, if `std` itself has a same-name declaration, the targets of the using-directive aren't looked at.

Specializations users write in `namespace std { ... }` used to be an issue too: C++11 required explicit specializations to be declared in the namespace of the template, where the enclosing namespace of an inline namespace counts but that of an ordinary `__1` doesn't. The current draft has relaxed this to allow explicit specialization in any scope where the primary template could be defined ([[temp.expl.spec#3]]), and Clang 23 accepts both forms, so this difference no longer matters much.
</details>
