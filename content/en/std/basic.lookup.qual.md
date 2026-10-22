---
title: Qualified name lookup
summary: "How the names in X::m and obj.m are looked up: a name before :: considers only namespaces and types, and a name after it is searched in the class, namespace or object type designated by what comes before; A::A qualified by its own class names the constructor; N::x searches N and its inline namespaces first, and follows using-directives only if nothing is found."
updated: 2026-10-19
---

!!! tldr
    - The `X` in `X::` considers only namespaces, types and class templates; same-named variables and functions are skipped.
    - The `m` in `X::m` is searched only in `X`; the `m` in `obj.m` or `p->m` is searched in the object's type. Qualified lookup never searches enclosing scopes.
    - The `B` in `p->B::f()` is first looked up in the object's class, and only if nothing is found is unqualified lookup done where the expression appears. This is the C++23 rule; Clang 23 still implements the old one.
    - `A::A` qualified by its own class names the constructor, not the type; `B::A` qualified by a derived class is the type.
    - `N::x` searches `N` and its inline namespaces first; only if nothing is found are the namespaces nominated by using-directives in `N` searched.

## Names before `::` ([basic.lookup.qual.general] ¶1)

```cpp run error
class A {
public:
    static int n;
};
int main() {
    int A;
    A::n = 42;    // OK: A:: considers only types, so the local variable A is skipped
    A b;          // error: ordinary lookup finds the local variable A, which is not a type
}
```

¶1 Lookup of an identifier followed by `::` considers only namespaces, types, and templates whose specializations are types. `X::` means "look for something in the scope of `X`", and only namespaces, classes and enumerations have such scopes. Same-named variables and functions should be skipped; otherwise C-style code where a class and a variable share a name could not access the class's static members.

The second sentence of ¶1 requires a name followed by `::`, a *template-id* (such as `B<0>`), and the like to designate a namespace, class, enumeration or dependent type. The types-only restriction applies to identifiers immediately followed by `::`; a name followed by `<` is still looked up normally:

```cpp run error
struct A { static int n; };
template<int> struct B : A {};
namespace N {
    template<int> void B();
    int f() {
        return B<0>::n;   // error: N::B<0> is not a type
    }
}
```

`B` is followed by `<`, so ordinary unqualified lookup is done for `B`; it finds the function template `N::B` in `N` and stops, and the global class template `::B` is hidden. `N::B<0>` is a function template specialization and cannot appear before `::`.

More and more forms can appear before `::`:

| Form | Example | Introduced |
|---|---|---|
| namespace names, class names, enumeration names, typedef-names | `std::`, `Outer::`, `Color::` | C++98 (enumeration names C++11) |
| template-ids | `std::vector<int>::` | C++98 |
| `decltype` specifiers | `decltype(s)::In::` | C++11 |
| pack-index-specifiers | `Ts...[0]::type` | {{c++26}} |
| splice-scope-specifiers | `[:r:]::` | {{c++26}} |

```cpp run ok
template<class... Ts>
struct First { using type = typename Ts...[0]::type; };   // C++26: pack index followed by ::
struct I { using type = int; };
static_assert(__is_same(First<I, double>::type, int));

struct S { struct In { static const int v = 1; }; };
S s;
int k = decltype(s)::In::v;                                // C++11: decltype followed by ::
```

## Qualified names and lookup contexts (¶2)

`N::C::m.Base::f()` contains several names, and for each one we need to know where to look. ¶2 defines a few terms for this.

¶2 A [[g:member-qualified-name|member-qualified name]] is the name immediately following `.` or `->` in a member access `obj.X` or `p->X`: either an ordinary member name (the `m` in `obj.m`) or a prefix of the form `type-name::` or `namespace-name::` (the `Base` in `p->Base::f()`).

A [[g:qualified-name|qualified name]] is a member-qualified name or the terminal name of anything with an `X::` prefix: the name in a *qualified-id*, a using-declaration, `typename T::x`, a namespace alias, and so on.

Every qualified name has a [[g:lookup-context|lookup context]], which is where it is looked up:

- The lookup context of a member-qualified name is the type of the object expression. If that type depends on a template parameter, the lookup context is considered dependent too.
- The lookup context of any other qualified name is the type, template or namespace designated by the preceding `X::`.

In `N::C::m.Base::f()`, `Base` is a member-qualified name looked up in the type of `N::C::m`; `C` is looked up in `N`, `m` in `N::C`, and `f` in the class `Base` designates. Note 1 adds that when a member access is parsed, the name after `.` or `->` always counts as a qualified name, even though it is not yet known which kind it is.

## Searching in the lookup context (¶3)

¶3 **Qualified name lookup** in a class, namespace or enumeration performs a [[g:search-in-scope|search]] of its scope. A search of a class scope extends to base classes ([[class.member.lookup]]), and namespaces have the supplementary rules of [namespace.qual].

A qualified name undergoes this lookup in its lookup context, from the point where it appears. There are two exceptions: the lookup context depends on a template parameter and is not the current instantiation ([[temp.dep.type]]), in which case lookup waits for instantiation; and the lookup context is not a class, as in `p->m` where `p` points to `int`.

¶3 also has a fallback rule: if a member-qualified name is followed by `::`, is not dependent, and nothing is found in the class, unqualified lookup is done instead. This rule is aimed at the `Base` in `p->Base::f()`: it is first looked up in the class of `*p`, where the injected-class-name of a base class (the copy of a class's name in its own scope, [[class.pre]]) is usually found; if nothing is found, the search goes outward from where the expression appears.

Note 2 points out that within a template specialization there are no dependent names any more.

### Example 3 in the standard

```cpp
int f();
struct A {
    int B, C;
    template<int> using D = void;
    using T = void;
    void f();
};
using B = A;
template<int> using C = A;
template<int> using D = A;
template<int> using X = A;

template<class T>
void g(T *p) {                  // explained for the instantiation g<A>
    p->X<0>::f();               // error: no X in A; parsed as ((p->X) < 0) > ::f()
    p->template X<0>::f();      // OK: falls back and finds ::X at the definition
    p->B::f();                  // OK: A::B is not a type and is skipped; the fallback finds ::B
    p->template C<0>::f();      // error: A::C is not a template
    p->template D<0>::f();      // error: A::D<0> is not a class type
    p->T::f();                  // error: A::T is not a class type
}
template void g(A*);
```

1. `p->X<0>::f()`: the lookup context `T` of `X` is dependent, so lookup is deferred to instantiation. At instantiation, `X` is not found in `A`. With no `template` keyword in front, whether `<` starts a template argument list depends on the lookup result ([[temp.names#7]]); since nothing was found, `<` is the less-than operator. The whole expression becomes `((p->X) < 0) > ::f()`, and `p->X` does not exist.
2. With `template` added, `X<0>` must be a template-id. `X` is not found in `A`, so by ¶3 lookup falls back to unqualified lookup at the definition, finding `::X`; `::X<0>` is `A`.
3. `B` is followed by `::`, so by ¶1 only types are considered; the data member `B` of `A` is skipped, nothing is found, and the fallback finds `::B`.
4. `C` finds the data member `C` in `A`. `template C<0>` requires `C` to be a template, and it is not. Since something was found, there is no fallback.
5. `D` finds the member alias template in `A`, and `A::D<0>` is `void`, not a class.
6. `T` finds `A::T`, that is, `void`, in `A`. This `T` is a member-qualified name looked up in `A`, not `g`'s template parameter `T`.

!!! impl "Compiler status"
    For Example 3, Clang 23 rejects only line 6 and accepts lines 1, 4 and 5. It still follows the rule of C++20 and earlier: a name before `::` in a member access is looked up both in the object's class and in the context of the whole expression, and the usable one is chosen. Under the current draft, all three lines are ill-formed.

!!! history "The old rule: look in both places"
    From C++98 to C++20, [basic.lookup.classref] specified that the `X` in `p->X::m` is looked up both in the class of `*p` and in the context of the entire postfix expression; if both found something, it had to be the same entity. The rule was complicated, prone to contradictions, and entangled with dependent lookup in templates. [[P1787R6]] replaced it with the rule of ¶3: look in the class first, and fall back if nothing is found.

## Destructor names (¶4)

The `X` in `~X` has many valid spellings: a class name, a typedef, a template parameter, even an alias of a scalar type (`p->~I()` where `I` is an alias of `int`, a pseudo-destructor call). The idea of ¶4 is to try in several places, and accept as long as one interpretation matches the object type.

¶4 Let the qualified name `Q` follow `~`:

- ¶4.1 if `Q` is a member-qualified name (`p->~Q()`), it undergoes both unqualified lookup and qualified lookup;
- ¶4.2 otherwise, the `N::` before it must designate a type. If `N` is preceded by another `S::` (`S::N::~Q`), `Q` is looked up in `S`;
- ¶4.3 otherwise, if `N` itself is a member-qualified name (`p->N::~Q`), `Q` is looked up as if `~Q` appeared in place of `N`, that is, per ¶4.1;
- ¶4.4 otherwise `Q` undergoes unqualified lookup.

¶4.5 Each lookup considers only types (if `Q` is not followed by `<`) and templates whose specializations are types; a lookup that finds nothing or is ambiguous is discarded. ¶4.6 Under the interpretation given by at least one successful lookup, the type-name containing `Q` must be the original lookup context (ignoring cv-qualification).

```cpp run ok
struct C { typedef int I; };
typedef int I1, I2;
void f(int* p, int* q) {
    p->C::I::~I();      // ¶4.2: I is looked up in C, finding C::I, i.e. int
    q->I1::~I2();       // ¶4.3, ¶4.1: I2 is not found in int; unqualified lookup finds ::I2
}
struct A { ~A(); };
typedef A AB;
void g(AB* p) {
    p->AB::~AB();       // explicitly calls A's destructor
}
```

Since C++20, a pseudo-destructor call on a scalar type ends the object's lifetime ([[expr.prim.id.dtor]]).

## `A::A` is the constructor [class.qual]

```cpp run error
struct A { A(); };
struct B : public A { B(); };

A::A() { }          // OK: A::A names the constructor
B::B() { }

B::A ba;            // OK: what is found in B is the injected-class-name of the base A, naming the type A
struct A::A a2;     // OK: an elaborated type specifier ignores function names, so A::A names the type
A::A a;             // error: A::A names the constructor, not a type
```

[class.qual] ¶1 In a qualified lookup whose lookup context is a class `C` and in which function names are not ignored, a name `N` is considered to name the constructor of `C` in two cases:

- ¶1.1 the search finds the injected-class-name of `C` itself;
- ¶1.2 `N` is dependent and is the terminal name of a using-declaration that inherits constructors.

A constructor name obtained this way can be used only in the declarator of a constructor declaration (including a friend constructor declaration) or in a using-declaration.

Footnote 15 lists the lookups in which function names are ignored: names before `::`, elaborated type specifiers (forms with a keyword, like `struct X`), and base-specifiers. In these places the injected-class-name names the type as usual.

`B::A` is not the constructor, because ¶1.1 requires the injected-class-name of the lookup context `C` itself. What is found in `B` is the injected-class-name of the base `A`, just an ordinary type name.

In early standards, `A::A` sometimes named the type and sometimes the constructor, and the meaning of things like `A::A::A::A` was unclear. Today the rule is uniform: where function names are not ignored, `C::C` is the constructor; to name the type, write `C` or `struct C::C`.

```cpp run ok
struct A { A(); };
A::A::A::A() { }    // the first three A precede ::, ignore function names, and name class A;
                    // the final A::A is in the declarator and names the constructor
```

¶1.2 handles inherited constructors in templates. In `using TB<T>::TB;`, `TB` is a dependent name, and at definition time lookup cannot confirm that it is the injected-class-name, so the standard simply specifies that it names the constructor:

```cpp run ok
struct Base { Base(int); };
struct Der : Base { using Base::Base; };     // inherits Base's constructors
Der d(1);

template<class T> struct TB { TB(T); };
template<class T> struct TD : TB<T> { using TB<T>::TB; };   // ¶1.2
TD<int> td(1);
```

## Namespace members [namespace.qual]

### Search N first, follow using-directives only if nothing is found (¶1)

[namespace.qual] ¶1 Qualified lookup in a namespace `N` has two steps:

1. search `N` and each namespace in the inline namespace set of `N` ([[namespace.def]]);
2. if nothing is found, recursively do qualified lookup in the namespaces nominated by each using-directive in `N` (and its inline namespaces) that precedes the point of lookup, and combine the results.

Note 1 points out that a using-directive naming a namespace that has already been considered does not affect the result. This guarantees that the recursion terminates.

Example 1 in the standard:

```cpp run error
int x;
namespace Y { void f(float); void h(int); }
namespace Z { void h(double); }
namespace A { using namespace Y; void f(int); void g(int); int i; }
namespace B { using namespace Z; void f(char); int i; }
namespace AB { using namespace A; using namespace B; void g(); }

void h() {
    AB::g();      // g is declared directly in AB; the result is {AB::g}
    AB::f(1);     // no f in AB, so recurse into A and B; A has f, so Y is not entered
                  // result {A::f(int), B::f(char)}; selects A::f(int)
    AB::f('c');   // as above; selects B::f(char)
    AB::h(16.8);  // no h in AB, A or B; recurse into Y and Z: {Y::h(int), Z::h(double)}; selects Z::h
    AB::x++;      // error: no x in AB, A, B, Y or Z; the global ::x is not among them
    AB::i++;      // error: {A::i, B::i} are two entities: ambiguous
}
```

`AB::f(1)` best illustrates "recurse only if nothing is found": `A` has an `f`, so this branch goes no deeper into `Y`, and `Y::f(float)` is not a candidate, even though it would be a better match for some arguments.

This differs from how unqualified lookup treats using-directives:

| | Unqualified lookup ([[basic.lookup.unqual]]) | Qualified lookup `N::x` |
|---|---|---|
| namespaces nominated by using-directives | searched together with the declarations at some enclosing namespace level | entered only if `N` (and its inline namespaces) found nothing |
| inline namespaces | treated like a using-directive in the enclosing namespace | searched together with `N` |

### Finding the same declaration twice is not ambiguous (¶2)

¶2 Note 2 points out that the same declaration found more than once is still one declaration and causes no ambiguity:

```cpp run ok
namespace A { int a; }
namespace B { using namespace A; }
namespace C { using namespace A; }
namespace BC { using namespace B; using namespace C; }
void f() { BC::a++; }    // OK: {A::a, A::a}, the same declaration

namespace D { using A::a; }
namespace BD { using namespace B; using namespace D; }
void g() { BD::a++; }    // OK: the using-declaration in D is replaced by A::a, still the same declaration
```

### Each namespace is searched at most once (¶3)

¶3 Example 3 shows that because each namespace is searched only once, using-directives that nominate each other do not cause an infinite loop:

```cpp run ok
namespace B { int b; }
namespace A { using namespace B; int a; }
namespace B { using namespace A; }      // A and B nominate each other

void f() {
    A::a++;     // OK: a is directly in A
    B::a++;     // OK: no a in B; searches A and finds A::a
    A::b++;     // OK: no b in A; searches B and finds B::b
    B::b++;     // OK: b is directly in B
}
```

### Classes from different namespaces are not hidden (¶4)

Within one scope, a class name is hidden by a same-named variable ([[basic.lookup#4]]). ¶4 Note 3 points out that this rule only operates within a single search. When a class and a variable are found in different namespaces through using-directives, the class is not discarded and the result is ambiguous:

```cpp run error
namespace A {
    struct x { };
    int x;          // same scope: the class x is hidden by the variable x
    int y;
}
namespace B {
    struct y { };
}
namespace C {
    using namespace A;
    using namespace B;
    int i = C::x;   // OK: one search in A finds both; the class is discarded, giving the variable A::x
    int j = C::y;   // error: A::y and B::y come from different searches: ambiguous
}
```

### Inline namespaces

In qualified lookup, members of an inline namespace behave like members of the enclosing namespace. Library versioning is built on this:

```cpp run ok
namespace lib {
    inline namespace v2 {
        struct W {};
        void f(W);
    }
    namespace v1 { struct W {}; }
}
lib::W w;                // finds lib::v2::W
void t() {
    lib::f(w);           // OK
    lib::v2::f(w);       // OK: version given explicitly
    f(w);                // OK: ADL, associated namespace lib and its inline namespace set
}
```

Unlike using-directives, inline namespaces are searched together with `N` in step 1. So if `lib` itself also declared a `W`, `lib::W` would be ambiguous.

!!! impl
    The name of an inline namespace becomes part of the mangled name. libc++'s `std::vector<int>` is really `std::__1::vector<int>`, and under the Itanium ABI its mangled name contains `NSt3__16vectorIiNS_9allocatorIiEEEE`; libstdc++'s mangled names have no such layer, so code compiled against the two libraries does not accidentally link together. At the source level, qualified lookup and ADL let `std::vector` find `std::__1::vector` directly.

!!! history "History"
    - C++98: qualified lookup, the two-place lookup in member access, and qualified namespace lookup propagating through using-directives all already existed.
    - C++11: inline namespaces were introduced; `decltype` can appear before `::`; enumeration names can be used as qualifiers (`Color::red`).
    - C++23: [[P1787R6]] introduced member-qualified names and lookup contexts, replaced the two-place lookup with "look in the class first, fall back if nothing is found", and wrote the rule that `A::A` names the constructor uniformly into [class.qual].
    - C++26: pack-index-specifiers (`Ts...[0]::`) and splice-scope-specifiers (`[:r:]::`) can appear before `::`.

## Common misconceptions

!!! pitfall "If N::x is not found, lookup continues outward"
    Qualified lookup looks only at `N`, the inline namespaces of `N`, and the namespaces (recursively) nominated by using-directives in `N`; it never looks at the scopes enclosing `N`. `AB::x` does not find the global `::x`.

!!! pitfall "Namespaces nominated by using-directives have the same standing as N"
    As soon as `N` itself (or one of its inline namespaces) has a same-named declaration, the namespaces nominated by using-directives are not considered at all. Adding a declaration to `N` can make a better overload previously found through a using-directive disappear.

!!! pitfall "B::A and A::A are the same thing"
    A base class name qualified by a derived class, `B::A`, is a type; `A::A` qualified by its own class is the constructor. Writing `typename Derived::Base` in templates is common and valid.

## Questions

!!! question "Question 1"
    ```cpp
    namespace N { inline namespace I { int v = 1; } }
    namespace M { int v = 2; }
    namespace N { using namespace M; }
    int r = N::v;
    ```
    What is `r`? What if `inline` is removed?

<details markdown="1">
<summary>Answer</summary>

With `inline`, step 1 searches `N` and its inline namespace `I`, finding `N::I::v`, so `r == 1`; the using-directive is not considered.

Without `inline`, step 1 finds no `v` in `N` (`I` is no longer in the inline namespace set), so step 2 applies: the using-directive nominates `M`, `M::v` is found, and `r == 2`. Running it with Clang 23 agrees.
</details>

!!! question "Question 2"
    In `template<class T> void g(T* p) { p->Base::f(); }`, suppose that at instantiation the class of `T` has no type named `Base`, but a global class `Base` is visible at the definition of `g`. What happens under the C++23 rules? What if the class of `T` has a data member named `Base`?

<details markdown="1">
<summary>Answer</summary>

`Base` is a member-qualified name followed by `::`. At instantiation it is looked up in the class of `T`, considering only types (¶1); nothing is found, so by ¶3 lookup falls back to unqualified lookup, which finds the global `Base`. After that, `Base::f` still requires `Base` to be an accessible, unambiguous base of `*p`; otherwise the member access is ill-formed.

If the `Base` in the class of `T` is a data member, it is likewise skipped because it is not a type, nothing is found, and the fallback proceeds as for `p->B::f()` in Example 3.
</details>

## Summary

| Rule | Key points |
|---|---|
| The `X` in `X::` | considers only namespaces, types and class templates; must designate a namespace, class, enumeration or dependent type |
| Member-qualified names | the name after `.` or `->`, or a `T::` prefix there; the lookup context is the object's type |
| Lookup context | the entity designated by the preceding `X::`; deferred to instantiation when dependent |
| Fallback | a name before `::` in a member access that is not found in the class undergoes unqualified lookup |
| Destructor names | looked up in several places; one interpretation matching the object type suffices |
| `C::C` | names the constructor where function names are not ignored; `B::A` and `struct A::A` are types |
| Namespace qualification | `N` plus its inline namespaces; recurse through using-directives only if nothing is found; each namespace at most once; never outward |
| Ambiguity | the same declaration found more than once is not ambiguous; classes from different searches are not hidden by variables |
