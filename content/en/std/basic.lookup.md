---
title: Name lookup
summary: "Name lookup associates a use of a name in the source with a set of declarations. This page covers how the result is used (overload resolution and access checking come after it), which declarations lookup can see (program points and precedes, including modules), the basic single search, and the rule that a class name is hidden by a variable or function of the same name."
updated: 2026-10-19
---

!!! tldr
    - Name lookup associates a use of a name with a set of declarations. If they are all functions, the result is an overload set, handed to overload resolution; otherwise the declarations must all denote the same entity, or the lookup is ambiguous and the program is ill-formed.
    - The order is fixed: lookup, then overload resolution, then access checking. `private` does not make a name disappear from lookup, and it does not make overload resolution fall back to another function.
    - Lookup only finds declarations that precede the point of use. For modules, an imported namespace member must be exported to precede; a class member only needs the class definition to be reachable.
    - When a class and a variable or function have the same name in the same scope, the class name is hidden, and you must write `struct X` to refer to the type.
    - Every lookup rule is built on the single search: find the declarations in one scope that bind this name and precede the point of use.

Every time the compiler meets a name, `x`, `std::vector`, `operator+`, `~T`, it first has to determine which declaration or declarations it refers to. This step is **name lookup**. Its result determines everything that follows: whether `a < b > c` is a comparison or a template argument list ([[temp.names]]), what type an expression has, which function is called.

Subclause 6.5 consists of a general framework (this page) and several specific sets of rules:

| Subclause | Question it answers |
|---|---|
| [[class.member.lookup]] | When a name is looked up in a class scope, how are the results found in the various base classes merged? |
| [[basic.lookup.unqual]] | Where does a name without `::` start being searched, and in what order does the search go outward? How do using-directives take part? |
| [[basic.lookup.argdep]] | For a call `f(x)`, how does the type of `x` pull in other namespaces too (ADL)? |
| [[basic.lookup.qual]] | Where is the name after `::` in `A::m` or `p->B::m` looked up? |
| [[basic.lookup.elab]] | How is the `X` in `struct X` looked up? |
| [[basic.lookup.udir]] | How is the `N` in `using namespace N;` or `namespace A = N;` looked up? |

This page uses a few scope terms: a declaration **inhabits** ([[g:inhabit]]) a scope, and its name is **bound** in the target scope; a declaration takes effect from its **locus** ([[g:locus]]). They are defined in [[basic.scope]].

## After lookup: overload resolution and access checking (¶1)

```cpp run error
struct B { void f(int); };
struct D : B {
private:
    void f(double);        // hides B::f
};

class X {
public:  void g(double);
private: void g(int);
};

void t() {
    D d;
    d.f(1);   // error: lookup finds only the private D::f; B::f is hidden
    X x;
    x.g(1);   // error: overload resolution selects g(int); access check fails
}
```

Both calls have a public function that looks usable, yet both are errors. The reason is the order in which a name is processed.

¶1 Name lookup associates a use of a name with a set of declarations of that name ([[basic.def]]). The rules apply to all names alike, typedef-names, namespace names and class names included; some contexts merely filter the result (see paragraph 4 below). Unless otherwise specified, finding nothing makes the program ill-formed.

If the declarations found are all functions or function templates, they form an **overload set** ([[g:overload-set]]), from which overload resolution ([[over.match]], [[over.over]]) later selects one. Otherwise, if the declarations found do not all denote the same entity, the lookup is **ambiguous** and the program is ill-formed. Finding the same variable along two paths is not ambiguous ([[namespace.qual#2]]).

!!! std
    The access rules ([class.access]) are considered only once name lookup and function overload resolution (if applicable) have succeeded.

Access is checked only after lookup and overload resolution have both succeeded. Only after that are the semantic properties introduced by the declaration (its type, whether it is `constexpr`, `[[deprecated]]`, and so on) used. So a name is processed in this order:

| Step | Rule | Result |
|---|---|---|
| 1. Name lookup | [basic.lookup] | a set of declarations |
| 2. Overload resolution (if the result is an overload set) | [[over.match]] | one function |
| 3. Access checking | [[class.access]] | whether it may be used |
| 4. Use of the declaration's properties | various subclauses | type, value category, etc. |

Back to the example. `d.f(1)`: looking up `f` in `D` finds the private `D::f(double)`; the derived-class declaration hides `B::f` ([[class.member.lookup]]), so `B::f` is not even a candidate; the access check then fails. `x.g(1)`: both `g` are candidates, overload resolution selects the exact match `g(int)`, and the access check then fails; the compiler does not fall back to `g(double)`.

This is by design: access control only decides whether something may be used, not what is found. Changing a member from `public` to `private` either leaves the program's meaning unchanged or makes it an error; it never silently makes a call go to another function. The same code also always finds the same declarations whether it is inside or outside the class.

Cases where finding nothing is not ill-formed are specified elsewhere; the common ones are:

- in a call `f(x)`, ADL may still find a function even if ordinary lookup found nothing ([[basic.lookup.argdep]]);
- in `f<T>(x)`, when ordinary lookup finds nothing, `f` is still parsed as a template name ([[temp.names]], since C++20);
- `struct X* p;` declares a new class when `X` is not found ([[dcl.type.elab]]);
- an unqualified friend declaration `friend void f();` does no lookup ([[dcl.meaning.general#2]]).

## Which declarations lookup can see: program points and precedes (¶2)

¶2 To say precisely that a declaration comes before a use, the standard defines **program points** ([[g:program-point]]): there is one before the first token of a translation unit, at least one between every two adjacent tokens, and one after the last token.

A program point P **follows** a declaration in the same translation unit if the declaration's locus is before P. Note 1 points out that the declaration may be in a scope that does not contain P; follows looks only at textual order, and scopes are handled separately by the lookup algorithms.

A declaration X **precedes** ([[g:precedes]]) a program point P in a translation unit L if one of the following holds:

1. P follows X;
2. X inhabits a class scope and is reachable ([[module.reach]]) from P;
3. X is in another translation unit D, and all of the following hold:
    - ¶2.1 P follows a module-import-declaration or module-declaration that directly or indirectly imports D;
    - ¶2.2 X appears after the module-declaration of D and before its private-module-fragment;
    - ¶2.3 X is exported; or D and L are part of the same module and X neither inhabits a namespace with internal linkage nor declares a name with internal linkage.

Precedes is the precise version of what older texts called visible; all lookups find only declarations that precede the point of use. Within a single translation unit it just means the declaration appears earlier; items 2 and 3 are there for modules.

Item 2 means class members need not be exported: as long as the class definition is reachable, its members can be found. A module can leave a class name unexported and export only a function returning an object of that class, and an importer that obtains the object can still access its members:

```cpp title="m.cppm"
export module M;
struct S { int x = 1; };          // S is not exported
export S make() { return {}; }
```

```cpp title="use.cpp" error
import M;
int main() {
    auto s = make();
    int v = s.x;    // OK: S::x inhabits a class scope, and S's definition is reachable here
    S s2;           // error: S inhabits a namespace scope and is not exported, so it does not precede this point
    return v;
}
```

Clang 23 reports unknown type name 'S' for `S s2;`; with that line deleted, the code compiles.

Note 2 adds that names introduced by using-declarations have no linkage, so the internal-linkage exclusion in item 2.3 does not affect them. Note 3 explains that importing is transitive: if module R contains `export import Q;`, importing R also imports Q.

!!! lawyer "Reachable versus precedes"
    Reachability is about whether a declaration's semantic properties can be used, for example whether a class is complete; precedes is about whether name lookup can find it. A declaration can be reachable without preceding: declarations in an indirectly imported module interface unit may be reachable ([[module.reach#1]]), yet names at namespace scope in it cannot be found by lookup. Class members are the exception: reachable means preceding.

## Single search (¶3)

¶3 defines the basic operation of all lookup, the **single search** ([[g:single-search]]):

!!! std
    A single search in a scope S for a name N from a program point P finds all declarations that precede P to which any name that is the same as N is bound in S.

Taken apart:

- Only the one scope S is examined; the search goes neither outward nor into base classes. Which scope a name is bound in is decided by [[basic.scope.scope#2]], and the exceptions listed there all apply here: for example, friend declarations do not bind names, and a block-scope function declaration binds its name in the block.
- Same name: identifiers are compared as character sequences; conversion function names `operator T` are compared by whether the types are the same ([[basic.pre#4]]).
- If a using-declarator is found and the name it names is not dependent, it is replaced by the declarations it designates ([[namespace.udecl]]). So the lookup result contains the original declarations; the `f` introduced by `using N::f;` and `N::f` are the same entity and cause no ambiguity.

```cpp run ok
namespace N { int v = 1; void f(int); }
namespace M { using N::v; using N::f; void f(double); }

using namespace N;
using namespace M;

void t() {
    v = 2;       // OK: both via N and via M's using-declaration, N::v is found
    f(1);        // OK: overload set {N::f(int), M::f(double)}; N::f(int) is selected
}
```

All other lookups are built from single searches:

| Operation | Defined in | What it does |
|---|---|---|
| Single search | paragraph 3 of this page | examines only one scope |
| Search | [[class.member.lookup#1]] | a single search for a non-class scope; for a class scope, the results are also merged along base classes |
| Unqualified search | [[basic.lookup.unqual#2]] | searches a scope together with the using-directives active there; if nothing is found, moves to the parent scope |
| Qualified name lookup | [[basic.lookup.qual#3]] | searches the class, namespace or enumeration named before `::` |
| Argument-dependent lookup (ADL) | [[basic.lookup.argdep]] | searches the associated namespaces of the argument types |

## A class name hidden by an entity of the same name (¶4)

```cpp run error
struct stat { long st_size; };
int stat(const char* path, struct stat* buf);   // function with the same name as a class: valid

void t() {
    struct stat s;          // OK: struct stat considers only types
    stat("/tmp", &s);       // OK: finds the class and the function; the class is discarded, so it is the function
    stat s2;                // error: stat refers to the function here
}
```

C puts struct tags and ordinary identifiers in different name spaces, so `struct stat` and the function `stat` can coexist, and POSIX uses exactly that. C++ put class names into ordinary scopes; to keep such code working, it specifies that a class name is hidden by other entities in the same scope.

¶4 Some contexts accept only certain kinds of declarations. For example, lookup of an identifier before `::` considers only namespaces, types, and templates whose specializations are types ([[basic.lookup.qual#1]]). After such filtering, there is one more general rule:

!!! std
    any declarations of classes or enumerations are discarded if any other declarations are found.

If any other declarations are found, class and enumeration declarations are discarded. Note 4 draws the conclusion: a type is hidden by any other entity in the same scope. The rule discards only class and enumeration declarations; type aliases and templates are not discarded this way. An alias and a variable cannot have the same name in the same scope anyway; that is a conflicting redeclaration ([[basic.scope.scope#6]]).

The rule applies only to the result of one search. When a class and a variable are found in different namespaces through using-directives, the class is not discarded and the lookup is ambiguous (note 3 of [[namespace.qual#4]], [[namespace.udir#7]]).

### Type-only lookup

The second half of ¶4 defines **type-only lookup** ([[g:type-only-lookup]]): only types and templates whose specializations are types are considered. In addition, if both a type alias and the type it denotes are found, the alias is the one discarded. Type-only lookup is used for:

- the name in an elaborated type specifier such as `struct X` or `enum E` ([[basic.lookup.elab]]);
- class names in a base clause ([[class.derived.general]]).

Why discard the alias and keep the type? An elaborated type specifier cannot name a typedef-name ([[dcl.type.elab#6]]); when both the alias and the original type are found, the original type must remain for `struct X` to be valid:

<div class="compare" markdown="1">

```cpp run ok
namespace A { struct X {}; }
namespace B { using X = A::X; }
using namespace A;
using namespace B;
struct X* p;  // the alias is discarded, leaving A::X
X* q;         // both are the same entity
```

```cpp run error
struct S {};
typedef S T;
struct T* p;
// error: only the alias T is found,
// and an elaborated type specifier
// cannot name a typedef-name
```

</div>

## Lookup in templates

Names in a template definition are divided into dependent and non-dependent names ([[temp.dep]]):

- non-dependent names are looked up and bound at the point of the template definition ([[temp.res]]);
- a dependent function call `g(t)` (where the type of `t` depends on a template parameter) proceeds in two steps: ordinary unqualified lookup is done at the point of definition, and ADL is done both at the point of definition and at the point of instantiation ([[temp.dep.candidate]], [[basic.lookup.argdep#4]]);
- unqualified lookup does not look into dependent base classes ([[class.member.lookup#4]]), which is why you write `this->f()`.

```cpp run error
template<class T> void call(T t) { g(t); }   // g is not found at the definition
void g(int);                                  // declared only after the template definition
int main() { call(1); }   // error: at instantiation only ADL is done, and int has no associated namespaces
```

If `int` is replaced by a class type in some namespace and `g` is declared in that same namespace, ADL finds it at the point of instantiation. This is what lets ADL serve as a customization point for templates.

## Implementation view

!!! impl "What compilers do"
    - Clang uses `LookupResult` to record the kind of lookup result: not found, found one declaration, found an overload set, not yet determinable in a dependent context, or ambiguous. Overload resolution and access checking are separate later steps, matching exactly the order prescribed by paragraph 1.
    - For the two-phase lookup example above, Clang 23 reports call to function 'g' that is neither visible in the template definition nor found by argument-dependent lookup. MSVC did not implement two-phase lookup for a long time before `/permissive-` and accepts this code.
    - Spelling corrections like "did you mean …" happen after lookup has failed and do not affect the meaning of the program.

## History

!!! history
    - Through C++20, the standard described lookup in terms of declarative regions, potential scope and visibility. Hiding of outer declarations by inner ones had its own subclause, and unqualified lookup was a list organized by situation (names in namespace member functions, names in member function bodies, names in friend functions, …). Every new piece of syntax required another entry, and gaps accumulated between the entries.
    - C++23 switched to today's model with [[P1787R6]]: visible became precedes, to handle modules; hiding no longer needs a separate rule, because unqualified search stops as soon as it finds something in an inner scope ([[basic.lookup.unqual#2]]); the list of situations was replaced by one algorithm that searches outward along the scope tree. Most code kept its meaning, but many corner cases the old text did not cover or contradicted itself on got definite answers.
    - C++26 static reflection added special ADL rules for `std::meta::info` ([[basic.lookup.argdep#3]]) and allows a splice to appear before `::` ([[basic.lookup.qual#1]]).

## Common misconceptions

!!! pitfall "private hides a name"
    Private members still take part in lookup and overload resolution, and still hide same-named members of base classes. To make an overload unusable from outside, use `= delete` or constraints, not `private`.

!!! pitfall "If lookup succeeds, the name can be used"
    Even if the lookup of `d.x` is unambiguous, the conversion from `d` to the base class that contains `x` may still be ambiguous, and the program is still ill-formed ([[class.member.lookup#11]], [[expr.ref]]).

!!! pitfall "Finding two functions with the same name is ambiguous"
    Two namespaces each have a function `f`, and both are found through using-directives. This is not ambiguous: they form an overload set for overload resolution. Lookup is ambiguous only when the result contains non-functions (variables, types, etc.) and the declarations do not all denote the same entity.

## Questions

!!! question "Question 1"
    Which function does `d.f(0)` below call? What if `private:` is deleted?
    ```cpp
    struct B { void f(long); };
    struct D : B {
        using B::f;
    private:
        void f(int);
    };
    void t(D& d) { d.f(0); }
    ```

<details markdown="1">
<summary>Answer</summary>

Looking up `f` in `D` finds the using-declaration (replaced by `B::f(long)`) and `D::f(int)`, which form an overload set. For the argument `0`, overload resolution selects the exact match `D::f(int)`; the access check then fails and the program is ill-formed. With `private:` deleted, `D::f(int)` is called. Access specifiers do not make overload resolution pick `B::f(long)` instead.
</details>

!!! question "Question 2"
    After `struct X {}; int X;`, what does `sizeof(X)` refer to? And `sizeof(struct X)`?

<details markdown="1">
<summary>Answer</summary>

`sizeof(X)`: lookup finds the class `X` and the variable `X`; by paragraph 4 the class is discarded, so it refers to the variable and the result is `sizeof(int)`. `sizeof(struct X)`: type-only lookup considers only types, so the result is the size of class `X`, 1.
</details>

!!! question "Question 3"
    Why does paragraph 2 say that a reachable declaration inhabiting a class scope precedes P, instead of requiring class members to be exported too?

<details markdown="1">
<summary>Answer</summary>

`export` applies only to declarations at namespace scope; class members have no separate notion of being exported. Whether a member can be used should depend on whether the class definition is reachable, because that determines whether the class is complete and its layout known. Otherwise a module could not export just a factory function and hide the class name while still letting users access the object's members.
</details>
