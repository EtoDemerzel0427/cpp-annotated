---
title: Unqualified name lookup
summary: "A name without :: or a member-access prefix is searched outward scope by scope from where it appears, stopping as soon as something is found; namespaces nominated by using-directives join the search at one particular level. The lookup order in function bodies, member functions, friends, local classes, templates and so on all follows from this one algorithm."
updated: 2026-10-19
---

!!! tldr
    - An unqualified name is searched starting from the immediate scope where it appears, outward one scope at a time, stopping at the first scope where any declaration is found.
    - So one same-named declaration in an inner scope hides all same-named declarations in outer scopes, including every overload of an outer function.
    - A using-directive declares no name. It makes the names of the nominated namespace take part in the search at the level of the innermost scope that contains both the directive and that namespace, which is often further out than expected.
    - When a member function is defined outside its class, everything after the function name belongs to the class scope and can use member names directly; a return type written before the function name does not.
    - In a class template, the class's own members and the members of non-dependent base classes are found before the template parameters.

Names like `x`, `f(a)`, `T` and `operator+` have no `N::` before them and do not follow `.` or `->`, so the compiler can only search outward from where they appear. This subclause specifies exactly what searching outward means.

## Outward scope by scope, stopping at the first hit (¶2–¶4)

```cpp run ok
void h(int);
namespace N {
    void h(double);
    void k() { h(1); }   // calls N::h(double); ::h(int) is not a candidate
}
```

¶3 **Unqualified name lookup** starts at the program point where the name appears and performs an unqualified search in its immediate scope (the smallest scope that contains it, [[basic.scope.scope#1]]).

¶2 An **unqualified search** ([[g:unqualified-search]]) in a scope S searches S (a search of a class scope also covers base classes, [[class.member.lookup]]) together with the namespaces nominated by the using-directives active at that level (see the next section). If nothing is found, the unqualified search continues in the parent scope of S.

In the example above, neither the function body of `k` nor its parameter scope contains `h`, so the search moves to namespace `N`, finds `N::h(double)`, and stops; the global `h(int)` is never seen. Overload resolution chooses only from `{N::h(double)}`, and `1` is converted to `double`.

Older standards had a dedicated subclause saying that inner declarations hide same-named outer ones. That is no longer needed: hiding is simply the result of stopping at the first hit. If an argument has class type, ADL may still add functions from elsewhere ([[basic.lookup.argdep]]).

Note 1 adds two points. Searching a class scope also searches its base classes; with a single base, it is as if the base class's scope directly contained the derived class's scope. Template parameter scopes associated with a scope on the chain are also considered ([[temp.local]], see below).

¶4 An **unqualified name** is a name that does not immediately follow a nested-name-specifier (`N::`) or the `.` or `->` of a member access, possibly with the `template` keyword or `~` in between. Unless otherwise specified, it is looked up by unqualified name lookup where it appears. Common cases specified otherwise:

- the `f` of a function call `f(args)` also gets the results of ADL ([[basic.lookup.argdep]]);
- when a non-member `operator@` is looked up for an operator expression, member functions are ignored ([[over.match.oper#3]]);
- the name being declared in a declaration is not a use and is not looked up;
- the conversion types of paragraph 5 and the friend declarators of paragraph 6 below.

## At which level a using-directive takes effect (¶1–¶2)

```cpp run ok
#include <type_traits>
namespace A { int i = 1; }
namespace B {
    long i = 2;
    void f() {
        using namespace A;
        static_assert(std::is_same_v<decltype(i), long>);   // finds B::i
    }
}
void g() {
    using namespace A;
    static_assert(std::is_same_v<decltype(i), int>);        // finds A::i
}
```

`B::f` contains `using namespace A;`, yet what is found is `B::i`, not `A::i`.

¶1 A using-directive is **active** ([[g:active-using-directive]]) in a scope S at a program point P if it precedes P and inhabits S, or inhabits a namespace nominated by another using-directive that is active in S. The second case is recursive: if S has `using namespace A;` and A in turn has `using namespace C;`, the directive in A is also active in S. This is the transitivity of using-directives ([[namespace.udir#5]]).

¶2 An unqualified search in a scope S searches:

- ¶2.1 S itself;
- ¶2.2 for each scope U that contains P and is or is contained by S, the namespaces contained by S that are nominated by the using-directives active in U.

Item 2.2 has two conditions: the using-directive must be within S (or be in S itself), and the nominated namespace must also be within S. So a nominated namespace joins the search only when the search reaches the innermost scope that contains both the directive and the namespace. Note 2 of [[namespace.udir#3]] says the same thing more intuitively:

!!! std
    During unqualified name lookup, the names appear as if they were declared in the nearest enclosing namespace which contains both the using-directive and the designated namespace.

Looking up `i` in `B::f`:

| Scope searched | Does namespace A join? | Result |
|---|---|---|
| the function body of `f` | A is not within the function body: no | nothing |
| the parameter scope of `f` | same as above | nothing |
| namespace `B` | A is not within B: no | finds `B::i`, stops |

A would join only at the global scope, but the search stops at B. In the global function `g`, the global scope contains both the directive and A, so `A::i` takes part in the search at the global level, where there is no other `i`, and `A::i` is found.

If the level where the namespace joins already has a same-named declaration, the lookup is ambiguous:

```cpp run error
int x = 0;
namespace A { int x = 1; }
void f() {
    using namespace A;
    x = 2;            // error: the global level finds both ::x and A::x
}
```

Local declarations are always found first; a using-directive can't override them:

```cpp run ok
namespace N { int y = 0; }
int f() {
    using namespace N;
    int y = 1;        // block-scope y
    return y;         // the local y; N::y only takes part at the global level
}
```

!!! tip "Compared with using-declarations"
    `using N::y;` is a declaration: it binds `y` in the scope where it appears. Writing `using N::y;` in a block and then `int y;` is a conflicting redeclaration. A using-directive declares no name at all ([[namespace.udir#4]]); it only decides which namespace is searched along with which level.

## Lookup order in various places

Older standards spent a dozen or so paragraphs listing the lookup order one by one for namespace member functions, member function bodies, friend functions, constructor initializer lists, and so on. Today all of these follow from how scopes nest ([[basic.scope]]) plus stopping at the first hit.

### Point of declaration

Lookup finds only declarations whose locus is before the use, and a variable's locus is after its complete declarator and before its initializer ([[basic.scope.pdecl#1]]):

```cpp run ok
const int i = 2;
void g() {
    int i[i];      // the i in the brackets is ::i; the new i is not yet in effect
    (void)i;
}
```

`int v = v;` is the opposite: the `v` in the initializer is the `v` being declared. Its lifetime has not begun, and reading it is undefined behavior ([[basic.life]]). This is not C++26 erroneous behavior, which applies to variables whose lifetime has begun but that have not been initialized ([[basic.indet]]).

### Namespace members defined outside their namespace

In `void N::g() { ... }`, everything after `N::g` belongs to the scope of namespace N ([[basic.scope.namespace]]). So names in the function body are looked up in turn in the function body of `g`, its parameter scope, N, and the global scope, even though the definition is written at global scope:

```cpp run ok
namespace N { void g(); int helper(); }
void N::g() {
    helper();        // OK: finds N::helper
}
```

### Member functions

A member function body inside a class definition is a [[g:complete-class-context]] ([[class.mem#10]]). When the search reaches the class scope, it searches from the end of the class definition ([[class.member.lookup#3]]), so members declared later can be used. The same holds for default arguments, default member initializers and `noexcept` specifiers; array bounds and member types are not complete-class contexts:

```cpp run error
struct X {
    int f(int a = k) { return a + m; }   // OK: the default argument and the body both see later members
    static constexpr int k = 3;
    int m = 0;
    int arr[k2];                         // error: k2 is not yet declared in the array bound
    static constexpr int k2 = 4;
};
```

For an out-of-class definition `X::T X::f() { ... }`, the parameter list, trailing return type and function body after `X::f` belong to the class scope ([[basic.scope.class]]); the return type before it does not and must be fully qualified:

```cpp run error
struct X { using T = int; T f(); T g(); auto h() -> T; };

X::T X::f() { T local = 0; return local; }  // OK: the return type must be qualified; T is used directly in the body
auto X::h() -> T { return 0; }              // OK: the trailing return type comes after X::h
T X::g() { return 0; }                      // error: the T in the return type is not in the scope of X
```

### Friend functions

For a friend function defined inside a class, the function body is textually within the class definition, the scope chain passes through the class scope, and the class's member names can be used directly:

```cpp run ok
struct X {
    static constexpr int k = 3;
    int m = 0;
    friend int peek(const X& x) { return x.m + k; }   // k is X::k
};
int main() { return peek(X{}) - 3; }
```

A friend function defined outside the class is not in the class scope ([[class.friend#6]]), because [[basic.scope.class]] excludes friend declarations.

A friend declaration itself binds no name ([[class.friend#10]]). After `friend void f(X);`, unqualified lookup in the enclosing namespace does not find this `f`; only ADL does. The hidden-friend idiom is built on this ([[basic.lookup.argdep]]).

### Local classes

The scope chain of a local class's member function passes through the enclosing function's block scope, so it can find the enclosing function's local variables. But odr-using them is ill-formed ([[basic.def.odr#10]]); uses that are not odr-uses (`sizeof`, reading a constant usable in constant expressions) are fine:

```cpp run error
void f() {
    int n = 1;
    const int c = 2;
    struct L {
        int g() { return sizeof(n) + c; }   // OK: n is not odr-used; c is a constant
        int h() { return n; }               // error: odr-uses a local variable of the enclosing function
    };
    (void)n;
}
```

### Template parameters

[[temp.local#7]] specifies that unqualified lookup considers the template parameter scope of a template declaration immediately after the outermost scope associated with that declaration, even though in an out-of-class definition that scope does not textually contain the template parameter list. It follows that members of a class template, including members of non-dependent base classes, are found before the template parameters. Example 6 in the standard:

```cpp run ok
#include <type_traits>
struct B { };
namespace N {
    typedef void V;
    template<class T> struct A : B {
        typedef void C;
        void f();
        template<class U> void g(U);
    };
}

template<class V> void N::A<V>::f() {      // N::V is not considered here
    V v;                                   // V is the template parameter (int), not N::V
    static_assert(!std::is_void_v<V>);
}

template<class B> template<class C> void N::A<B>::g(C) {
    B b;                                   // B is the base class ::B, not the template parameter
    C c;                                   // C is g's template parameter, not A::C
    static_assert(std::is_same_v<B, ::B>);
}
template struct N::A<int>;
template void N::A<int>::g(long);
```

In `f`, `V` is looked up in this order: the body of `f`, its parameter scope, class `A` (including base `B`), the template parameter scope of `A`, `N`, the global scope. So the template parameter `V` is found before `N` is reached.

The `B` in `g`: the scope of class `A` (including the injected-class-name of base `B`) comes before the template parameter scope of `A`, so `B` refers to the base class. `C`, on the other hand, is the template parameter of the member template `g` itself: the outermost scope associated with `g` is its parameter scope, and `g`'s template parameter scope comes right after it, before class `A`.

A template parameter's name cannot be redeclared within its scope ([[temp.local#6]]), so a template parameter can be hidden by a member only through base class members or out-of-class definitions.

### Dependent base classes

When the search reaches the scope of a class template, only non-dependent base classes are merged ([[class.member.lookup#4]]). Members of dependent bases require `this->`, `Derived::` or `typename Derived::`:

```cpp run error
template<class T> struct Base { using type = T; };
template<class T> struct D : Base<T> {
    typename D::type y;   // OK: qualified name, lookup deferred to instantiation
    type x;               // error: unqualified lookup does not look into dependent bases
};
```

## Two special rules (¶5, ¶6)

### Type names in conversion functions (¶5)

`x.operator T()` calls a conversion function of the class of `x`, and this `T` is quite likely a member type of that class. If `T` were looked up only at the point of the call, such a call couldn't be written.

¶5 So an unqualified name in the type part of a conversion function name `operator ...` is first looked up in the same way as the whole conversion function name; if nothing is found, ordinary unqualified lookup is done. In both cases only types and templates whose specializations are types are considered. Example 1 in the standard:

```cpp run ok
struct T1 { struct U { int i; }; };
struct T2 { };
struct U1 {};
struct U2 {};

struct B {
    using T = T1;
    using U = U1;
    operator U1 T1::*();
    operator U1 T2::*();
    operator U2 T1::*();
    operator U2 T2::*();
};

template<class X, class T>
int g() {
    using U = U2;
    X().operator U T::*();                // #1
    X().operator U decltype(T())::*();    // #2
    return 0;
}
int x = g<B, T2>();   // #1 calls B::operator U1 T1::*
                      // #2 calls B::operator U1 T2::*
```

In `#1`, `operator U T::*` follows `.`, so it is looked up in `X`, that is, `B`; the `U` and `T` inside it are also looked up in `B` first, giving `B::U` (U1) and `B::T` (T1). In `#2`, `U` is likewise found in `B`; the `T` in `decltype(T())` is an ordinary name in an expression and finds the template parameter `T` (T2).

### Friend declarations with qualified names (¶6)

`friend void A::f(F);` befriends an existing `f` in `A`, and the parameter type `F` should naturally be understood in the original context of `A::f`. For out-of-class member definitions this already holds, since everything after the function name belongs to the class scope; but friend declarations are excluded from that ([[basic.scope.class]]), so a separate rule is needed.

¶6 In the declarator of a friend declaration, if the declared name is a qualified name whose nested-name-specifier designates a class or namespace S, unqualified names that appear after that name are first searched for in the scope of S; if nothing is found, ordinary unqualified lookup is done. Example 2 in the standard:

```cpp run error
using I = int;
using D = double;
namespace A {
    inline namespace N { using C = char; }
    using F = float;
    void f(I);
    void f(D);
    void f(C);
    void f(F);
}
struct X0 { using F = float; };
struct W {
    using D = void;
    struct X : X0 {
        void g(I);
        void g(::D);
        void g(F);
    };
};
namespace B {
    typedef short I, F;
    class Y {
        friend void A::f(I);        // error: no I in A; finds B::I (short), and there is no A::f(short)
        friend void A::f(D);        // OK: no D in A; finds ::D (double)
        friend void A::f(C);        // error: a search in A does not include the inline namespace N
        friend void A::f(F);        // OK: finds A::F (float) in A
        friend void W::X::g(I);     // error: there is no X::g(short)
        friend void W::X::g(D);     // OK: no D in X or X0; finds ::D
        friend void W::X::g(F);     // OK: finds F in X's base X0
    };
}
```

- `A::f(C)`: paragraph 6 calls for one search in S, and a search does not include inline namespaces; only qualified name lookup goes on to search inline namespaces ([[namespace.qual#1]]). So `C` is not found.
- `W::X::g(D)`: `D` is not found in X (including X0), so ordinary unqualified lookup is done from where the friend declaration appears. The scope chain is Y, B, global, which does not pass through W, so `::D` is found.

!!! impl "Clang's implementation status"
    Clang 23 does not fully implement this rule; in both the namespace and the class case it continues searching in the scopes enclosing S:

    - `friend void A::f(F);`: Clang resolves `F` as `B::F` (short) and reports that the friend declaration matches no declaration in A. Per the standard this line is well-formed.
    - `friend void W::X::g(D);`: Clang first finds `W::D` (void) in `W` and reports no match among the declarations in `W::X`. Per the standard this line is well-formed.
    - `friend void W::X::g(I);`: Clang finds `::I` (int) and accepts the line. Per the standard it is ill-formed.

    `W::X::g(F)` passes because `F` is found in X's base class, which happens to agree with the standard. On the remaining lines Clang agrees with the standard.

## Implementation view

!!! impl "What compilers do"
    - Clang's unqualified lookup walks outward along the `Scope` and `DeclContext` chains. At each level it uses `UnqualUsingDirectiveSet` to attach the namespaces nominated by using-directives to the level of the nearest enclosing namespace that contains both the directive and the namespace, which is equivalent to item 2.2.
    - Before `/permissive-`, MSVC looked into dependent base classes again at instantiation, so code like `type x;` above compiled; Clang and GCC report an error as the standard requires.

## History

!!! history
    - Through C++20, this subclause was a list of a dozen or so paragraphs organized by situation, describing the lookup order separately for namespace scope, class definitions, member function definitions, friends, constructor initializer lists, static data member definitions, and so on.
    - C++23 ([[P1787R6]]) condensed it into today's six paragraphs: active using-directives, unqualified search, unqualified lookup, the definition of unqualified names, and two special cases for conversion types and friend declarators. The various situations are now derived from the scope rules, the key being the rule in [[basic.scope.class]] and [[basic.scope.namespace]] that everything after the function name also belongs to that scope.

## Common misconceptions

!!! pitfall "using namespace overrides same-named outer declarations"
    In `namespace B { long i; void f() { using namespace A; i; } }`, the `i` is still `B::i`. Names introduced by a using-directive take part in the search only at the level that contains both the directive and the target namespace.

!!! pitfall "using namespace std in a header just saves typing"
    With `using namespace std;` at global scope, the names of std take part in the search at the global level. If the standard library later adds a function with the same name as one of your global functions (for example `std::size` or `std::data`), code that used to be unambiguous may become ambiguous, or silently start calling a different function.

!!! pitfall "An out-of-class definition's return type can use member types directly"
    The return type comes before the function name and is not in the class scope. Either write `X::T X::f()` or use a trailing return type `auto X::f() -> T`.

## Questions

!!! question "Question 1"
    ```cpp
    namespace A { int n = 1; }
    namespace B { using namespace A; }
    namespace C {
        int n = 2;
        namespace D {
            using namespace B;
            int get() { return n; }
        }
    }
    ```
    What does `C::D::get()` return?

<details markdown="1">
<summary>Answer</summary>

It returns 2. The directive in D nominates B; by the transitivity of paragraph 1, the directive in B nominating A is also active in D. But the only scope containing these directives and A is the global scope. Searching along the scope chain: the body of `get`, its parameter scope, D (neither A nor B is within D), C; `C::n` is found in C and the search stops. `A::n` would join only at the global level.
</details>

!!! question "Question 2"
    Paragraph 5 requires the type in a conversion function name to be looked up first in the way the whole conversion function name is, and paragraph 6 requires names in a friend declarator to be searched in S first. What motivation do the two share?

<details markdown="1">
<summary>Answer</summary>

The meaning of a name should be determined by the context of the declaration it refers to, not by the context of the use. `x.operator T()` refers to a conversion function in the class of `x`, and its `T` is usually a member of that class; `friend void A::f(F)` refers to an existing `f` in A, and `F` should be understood as it is in A. Without these two rules, it would be hard or even impossible to name these declarations from elsewhere.
</details>
