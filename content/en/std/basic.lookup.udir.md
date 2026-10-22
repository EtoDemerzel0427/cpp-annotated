---
title: Lookup in using-directives and namespace aliases
summary: "In using namespace and namespace A =, the namespace name and the names in its prefix are looked up as namespaces only; same-named variables and types are all skipped."
updated: 2026-10-19
---

!!! tldr
    - In `using namespace X::Y;` and `namespace A = X::Y;`, both `X` and `Y` are looked up only as namespace names, namespace aliases included.
    - Same-named local variables and member classes do not hide the namespace here.
    - An ordinary `X::` also considers types; here even types are skipped, because a class cannot contain a namespace.

## Only namespace names are considered (¶1)

```cpp run error
namespace X { namespace Y { int v = 1; } }

struct S {
    struct X { struct Y {}; };          // a same-named class X in class scope
    int f() {
        using namespace X::Y;           // OK: X considers only namespaces, finding ::X
        namespace Z = X::Y;             // OK: same as above
        return v + Z::v;                // ::X::Y::v
    }
    int g() {
        return X::Y::v;                 // error: ordinary lookup finds the class S::X, and S::X::Y has no v
    }
};

void h() {
    int X = 0;                          // for ordinary lookup, the local variable X hides namespace X
    using namespace X;                  // OK: only namespace names are considered
    namespace A = X;                    // OK
    (void)X;
}
```

The same `X::Y` is hidden by the member class `S::X` in the expression in `g`, but not in the using-directive and alias definition in `f`.

¶1 In a using-directive or a namespace-alias-definition ([[namespace.alias]]), only namespace names are considered when looking up the namespace name and the names in the `X::` prefix before it.

!!! std
    In a using-directive or namespace-alias-definition, during the lookup for a namespace-name or for a name in a nested-name-specifier only namespace names are considered.

These two places accept only namespaces: a using-directive nominates a namespace, and an alias also stands for a namespace ([[namespace.alias#4]]). Considering anything else would be pointless and would only let unrelated names hide the namespace.

An ordinary `X::` is different. Per [[basic.lookup.qual#1]], the `X` in `X::m` also considers types, because `m` might be a class member. But in `using namespace X::Y;`, even if `X` were a class, `X::Y` could not be a namespace, so types can be skipped too.

An alias is itself a namespace name, so it can appear in other alias definitions:

```cpp run ok
namespace very_long_library_name { namespace detail { int k = 0; } }
namespace lib = very_long_library_name;
namespace det = lib::detail;           // lib is an alias, found as a namespace name
int r = det::k;
```

## Related rules

- This subclause only governs how the nominated namespace is found. How a using-directive then affects later lookups is covered in [[basic.lookup.unqual#1]] (unqualified lookup) and [[namespace.qual]] (qualified lookup).
- The name in a using-directive cannot be dependent ([[namespace.udir#1]]), and a using-directive cannot appear in class scope ([[namespace.udir#2]]). The using-directive in the example above is in a member function body, which is a block scope, so it is valid.
- {{c++26}} Using-directives and alias definitions can also use splices: `using namespace [:r:];` and `namespace A = [:r:];`, where `r` must represent a namespace other than the global namespace ([[namespace.udir#1]], [[namespace.alias#2]]). A splice involves no name lookup, so the rule of this subclause does not apply.

!!! impl
    When Clang parses using-directives and namespace aliases, it uses a dedicated lookup that matches only namespaces (`LookupNamespaceName`). So when a name is taken only by other entities, it reports expected namespace name rather than an ambiguity or a type error.

!!! history "History"
    This rule has existed since C++98, with almost no change in wording. C++23's [[P1787R6]] kept it; C++26 added splice forms for using-directives and alias definitions.

## Questions

!!! question "Question"
    ```cpp
    namespace N { int x = 1; }
    namespace M { namespace N = ::N; }   // alias
    void f() {
        struct N { };                    // local class N
        using namespace M::N;            // (1)
        int y = x;                       // (2)
    }
    ```
    Are (1) and (2) valid? Which `x` is it?

<details markdown="1">
<summary>Answer</summary>

(1) is valid. `M` is looked up only as a namespace name, finding `::M`; `N` is looked up in `M`, also considering only namespace names, and finds the alias `M::N`, that is, `::N`. The local class `N` is outside the reach of the lookup in `M::` and is irrelevant.

(2) is valid. The using-directive nominates `::N`. Per [[basic.lookup.unqual#2]], the members of `::N` take part in lookup at the nearest level that contains both the directive and `::N`, which is the global namespace, so `x` is `N::x`. Clang 23 compiles it.
</details>
