---
title: Argument-dependent lookup (ADL)
summary: "An unqualified function call f(args) is looked up not only outward from the call site but also in the namespaces of the argument types, where it also finds friends of associated classes."
updated: 2026-10-19
---

!!! tldr
    - For `f(x)`, the compiler not only looks up `f` outward by the ordinary rules but also looks for functions named `f` in the namespaces the type of `x` belongs to, and the results from both are combined into one overload set. This is ADL.
    - Writing `N::f(x)` or `(f)(x)`, or ordinary lookup finding a class member, a block-scope function declaration or a variable, means ADL does not happen.
    - The namespaces to search are determined by the argument types: the namespace of the class, its base classes and the types of template arguments all count; fundamental types like `int` and `double` bring in nothing.
    - A friend function declared only inside a class (a hidden friend) can only be found by ADL. Writing operators as hidden friends is the standard way to make them usable without polluting overload sets.
    - The two-step `using std::swap; swap(a, b);` and the customization point objects of `std::ranges` were both designed to control ADL in generic code.

## Why ADL is needed

```cpp run ok
#include <iostream>
#include <string>
int main() {
    std::string s = "hi";
    std::cout << s;   // calls std::operator<<(std::ostream&, const std::string&)
}
```

There is no `using namespace std;` here, and the output operator for `string` is a function template in namespace `std`, not a member of `std::ostream`. Searching outward from the global `main` does not find `std::operator<<`.

The code compiles because of **argument-dependent lookup** (ADL, also called Koenig lookup): the types of the arguments `std::cout` and `s` both belong to `std`, so `std` is also searched when looking up `operator<<`. Without ADL, operators in a namespace could only be written as `std::operator<<(std::cout, s)`.

ADL makes a type's non-member functions, such as `swap`, `operator==` or `begin` in the same namespace, as natural to use as member functions. The price is that which function is called depends on where the argument types come from, and ADL sometimes finds functions you did not intend to call.

## When ADL happens (¶1)

```cpp run ok
namespace N {
    struct S { };
    void f(S);
}
void g() {
    N::S s;
    f(s);         // OK: ADL finds N::f in N
}
```

¶1 If the called part of a function call (the *postfix-expression* in the grammar) is an *unqualified-id*, unqualified lookup ([[basic.lookup.unqual]]) is done on it first. As long as that lookup finds none of the following three kinds of declaration, the functions found by ADL are also added to the result:

- ¶1.1 a declaration of a class member;
- ¶1.2 a function declaration inhabiting a block scope;
- ¶1.3 a declaration that is neither a function nor a function template (a variable, type, function object, etc.).

The ADL result is added, not substituted. The functions found by unqualified lookup and those found by ADL form one overload set, which goes to overload resolution.

### Ways to turn ADL off

| Form | Why there is no ADL |
|---|---|
| `N::f(x)` | a qualified name, not an *unqualified-id* |
| `(f)(x)` | the called part is a parenthesized expression, not an *unqualified-id* |
| called in a member function whose class or base has a member named `f` | ¶1.1: a class member is found |
| `void f(int);` declared in the same block scope | ¶1.2: a block-scope function declaration is found |
| ordinary lookup finds a variable, function object or type | ¶1.3: a non-function is found |

```cpp run error
namespace N {
    struct S { };
    void f(S);
}
void g() {
    N::S s;
    (f)(s);       // error: the parentheses turn ADL off, and ordinary lookup does not find f
}
void h() {
    N::S s;
    void f(int);  // block-scope function declaration
    f(s);         // error: ¶1.2 turns ADL off; only f(int) remains, and N::S cannot convert to int
}
void k() {
    N::S s;
    int f = 0;    // non-function
    f(s);         // error: ¶1.3 turns ADL off; an int cannot be called
}
struct M {
    void f(int);
    void m() {
        f(N::S{});   // error: ¶1.1 finds the member M::f; no ADL
    }
};
```

Example 3 in the standard (¶6) shows a practical consequence of ¶1.2: an `extern` declaration in block scope makes an otherwise better candidate disappear:

```cpp ok
namespace NS {
    class T { };
    void f(T);
    void g(T, int);
}
NS::T parm;
void g(NS::T, float);
int main() {
    f(parm);                      // OK: ADL finds NS::f
    extern void g(NS::T, float);  // block-scope function declaration
    g(parm, 1);                   // OK: calls ::g(NS::T, float)
}
```

`NS::g(T, int)` is an exact match for `g(parm, 1)` and would otherwise win. But unqualified lookup finds a function declaration in block scope, ADL does not happen, and `NS::g` is not a candidate at all.

### A block-scope using-declaration does not turn ADL off

`using std::swap;` is also written in block scope, but it is not a function declaration in the sense of ¶1.2. [[basic.lookup#3]] specifies that when a search finds a using-declaration, it is replaced by the declarations it names, here the function templates of `std::swap`. Those inhabit namespace `std`, not the block scope, so ADL proceeds as usual. The two-step swap later on depends on this.

Note 4 in ¶6 also points out that associated namespaces may overlap with namespaces already searched by unqualified lookup. Finding the same declaration along two paths is not ambiguous; it is still one function in the overload set.

## First, deciding whether it is a function call (¶2)

¶2 Note 1 reminds us that whether an expression is a function call is decided during parsing with the ordinary lookup rules. ADL takes no part in that step. This has two consequences.

The first concerns `f<T>(x)`. When a name is followed by `<`, the parser must first decide whether it is a template name ([[temp.names#7]]). Since C++20 ([[P0846R0]]), if unqualified lookup finds nothing or finds functions, the `<` is taken as the start of a template argument list. So `f<T>(x)` becomes a call, and ADL can find the actual function template:

```cpp run error
int h;
void g();
namespace N {
    struct A {};
    template <class T> int f(T);
    template <class T> int g(T);
    template <class T> int h(T);
}
int x = f<N::A>(N::A());   // OK: f is not found, treated as a template name; ADL finds N::f
int y = g<N::A>(N::A());   // OK: g finds a non-template function, also treated as a template name
int z = h<N::A>(N::A());   // error: h finds a variable, so h< does not start a template argument list
```

Before C++20, both the `x` and `y` lines would be parsed as comparisons and fail. Back then getting a tuple element required `std::get<0>(t)`; now it can be written directly:

```cpp run ok
#include <tuple>
int main() {
    std::tuple<int, double> t{1, 2.0};
    return get<0>(t) - 1;   // OK since C++20: ADL finds std::get in std
}
```

The second consequence is that without a call there is no ADL:

```cpp run ok
typedef int f;
namespace N {
    struct A {
        friend void f(A &);
        operator int();
        void g(A a) {
            int i = f(a);   // f is a typedef: this is the type conversion int(a)
            (void)i;
        }
    };
}
```

`f` finds the typedef, so `f(a)` is syntactically a functional-notation type conversion ([[expr.type.conv]]); no ADL is done, and the friend `f` is not found.

## Which associated entities an argument type brings (¶3)

¶3 For each argument type `T` in the call, the standard specifies a (possibly empty) set of [[g:associated-entities|associated entities]], mostly classes and enumerations. ADL then searches the namespaces these entities are in. Associated entities are determined by the type alone; whether the type was written with a typedef or a using alias makes no difference.

| Kind of `T` | Associated entities |
|---|---|
| ¶3.1 `std::meta::info` {{c++26}} | only the enumeration type `std::meta::operators` |
| ¶3.2 other fundamental types (`int`, `double`, `std::nullptr_t`, …) | none |
| ¶3.3 class types (including unions) | the class itself; if it is a nested class, the enclosing class; if it is complete, its direct and indirect base classes |
| ¶3.3 class template specializations, in addition | the associated entities of type template arguments; templates used as template template arguments; the classes of which member templates used as template template arguments are members |
| ¶3.4 enumeration types | the enumeration itself; if it is a class member, that class |
| ¶3.5 `U*`, `U[n]` | the associated entities of `U` |
| ¶3.6 function types | the associated entities of the parameter types and return type |
| ¶3.7 pointer to member function of class `X` | the associated entities of the parameter types and return type, plus `X` |
| ¶3.8 pointer to data member of class `X` | the associated entities of the member type, plus `X` |

An argument can also be a function name, that is, an overload set (or the address of one). Then the associated entities are the union of the associated entities of the parameter types and return types of each function in the set; if the overload set is named with a template argument list, the associated entities of those template arguments are added too.

Note 3 points out that constant template arguments, variable template template arguments and concept template arguments contribute no associated entities.

### Fundamental types: nothing

`swap(i, j)` (with `int`) does not find `std::swap` through ADL. In a template, a call like `g(1)` also does not find, at instantiation, a `g` declared after the template definition, because the second phase of lookup relies on ADL alone.

### Reflection values: a dedicated rule {{c++26}}

`std::meta::info` is an alias for `decltype(^^int)`, which is itself a fundamental type. By ¶3.2 it would bring nothing, and an unqualified call like `members_of(r, ctx)` would not find `std::meta::members_of`. So ¶3.1 specifies its associated entity as the enumeration `std::meta::operators`, which is in `std::meta`, making `std::meta` an associated namespace.

### Classes: enclosing classes and base classes

The enclosing class is an associated entity, so an argument of a nested class brings in the friends of the enclosing class. The base classes of a complete type are also associated entities, so friends defined in a base class are equally available for derived-class objects.

```cpp run error
namespace N {
    struct Out {
        struct In { };
        enum class E { a };
        friend void p(In) { }
        friend void q(E) { }
    };
}
namespace L {
    struct Base { friend void fb(const Base&) { } };
    struct D : Base { };
    struct Inc;                      // declared only, incomplete
}
void t(L::Inc* pi) {
    p(N::Out::In{});    // OK: In's enclosing class Out is an associated entity; Out's friend p is found
    q(N::Out::E::a);    // OK: ¶3.4, the enumeration is a member of Out
    fb(L::D{});         // OK: D is complete, so the base Base is an associated entity
    fb(*pi);            // error: Inc is incomplete, so its bases do not count
}
```

### Template arguments: the most common source of surprises

Most surprising ADL results come from template arguments. `std::vector<N::X>` makes both `N` and `std` associated namespaces. Arguments of arguments count too: the template argument of `std::function<void(N::X)>` is the function type `void(N::X)`, and by ¶3.6 its parameter type `N::X` brings in `N`.

```cpp run ok
#include <functional>
namespace N {
    struct X {};
    void f(std::function<void(X)>);
    void h(void (*)(X));
    void cb(X);
}
namespace O { template<class T> struct Box {}; }
namespace P { struct Y {}; void z(O::Box<Y>); }

void t() {
    std::function<void(N::X)> fn;
    f(fn);                 // OK: the parameter type of template argument void(N::X) brings in N
    h(&N::cb);             // OK: the argument is the overload set {N::cb}; cb's parameter type brings in N
    z(O::Box<P::Y>{});     // OK: the template argument P::Y brings in P
}
```

Aliases have no effect; only the type they denote matters:

```cpp run error
namespace N { struct X {}; }
namespace T {
    using Alias = N::X;
    void f(Alias);
}
void t() {
    T::Alias a;
    f(a);        // error: a has type N::X; the only associated namespace is N, not T
}
```

## Where to look and what to find (¶4)

¶4 The [[g:associated-namespaces|associated namespaces]] of a call are the innermost enclosing non-inline namespaces of the associated entities, together with the inline namespace sets of those namespaces ([[namespace.def]]).

Together, these two parts make a library's versioning inline namespaces transparent to ADL. In libc++, `std::vector` is really `std::__1::vector`; its innermost enclosing non-inline namespace is `std`, plus the inline namespace set of `std` (which contains `__1`). So ADL finds related functions whether they are declared in `std` or in `std::__1`.

For a name `N`, ADL finds the function and function template declarations that satisfy any of the following:

- ¶4.1 found by a search for `N` in some associated namespace;
- ¶4.2 declared as a friend of some associated class whose definition is reachable;
- ¶4.3 exported declarations from named modules, under certain conditions (see the section on modules below).

ADL collects only functions and function templates. A variable or type named `N` in an associated namespace is simply ignored and causes no ambiguity.

### Only one search in an associated namespace

¶4.1 talks about a **search** ([[basic.lookup]]), which looks only at that namespace's own declarations. It is not an inside-out unqualified lookup, so it does not look at enclosing namespaces and does not follow the using-directives in that namespace:

```cpp run error
namespace M { }
namespace N {
    using namespace M;   // ADL does not follow this into M
    struct S { };
}
namespace M { void g(N::S); }

void t() {
    g(N::S{});    // error: the only associated namespace is N, and the search in N does not follow using-directives
}
```

### Friends and hidden friends

`friend void f(X);` inside a class declares a function `f` in the enclosing namespace. But a friend declaration binds no name ([[class.friend#10]], [[dcl.meaning.general#2]]): until a matching declaration appears at namespace scope, neither unqualified nor qualified lookup finds it. ¶4.2 lets ADL find it, provided the class is an associated entity and its definition is reachable.

A friend function declared only inside a class (usually also defined there) and not redeclared at namespace scope is called a **hidden friend**. It can only be found by ADL:

```cpp run error
#include <ostream>
namespace N {
    class P {
        int v = 0;
        friend bool operator==(const P&, const P&) = default;
        friend std::ostream& operator<<(std::ostream& os, const P& p) {
            return os << p.v;
        }
        friend void touch(P&) { }
    };
}
void t(std::ostream& os) {
    N::P a, b;
    os << a;           // OK: ADL finds the friend of N::P
    (void)(a == b);    // OK
    touch(a);          // OK
    N::touch(a);       // error: qualified lookup does not find hidden friends
}
```

There are three reasons to write operators and customization functions as hidden friends.

First, smaller overload sets. An `operator<<` at namespace scope takes part in every lookup of `<<` in that namespace. A large namespace like the standard library's may hold a hundred `operator<<`, and overload resolution has to try each one, which slows compilation and lengthens error messages. A hidden friend appears only when an argument actually involves the class.

Second, no accidental selection through implicit conversions. A hidden friend is found only when an argument's associated class is the class itself. A type that merely converts to the class does not find it:

```cpp run error
namespace units {
    struct Meters { double v; Meters(double d) : v(d) {} };
    struct ToMeters { operator Meters() const { return 1.0; } };
    void show(Meters);                       // namespace scope

    struct Feet {
        double v; Feet(double d) : v(d) {}
        friend void show2(Feet) { }          // hidden friend
    };
    struct ToFeet { operator Feet() const { return 1.0; } };
}
void t() {
    units::ToMeters m;
    show(m);                  // OK: ADL finds show in units, called via conversion
    units::ToFeet f;
    show2(units::Feet(1.0));  // OK
    show2(f);                 // error: ToFeet's associated entities do not include Feet
}
```

Third, a friend can access private members directly, without extra public getters.

## ADL in modules (¶4.3, ¶5)

In modules, whether a declaration is visible before the point of lookup and whether its definition is reachable are separate questions ([[basic.lookup#2]], [[module.reach]]). ¶4.3 lets ADL also find a function that is exported, attached to some named module `M`, not in the current translation unit, and in the same innermost non-inline namespace as some associated entity attached to `M`. It is found even if its namespace is not visible at all in the current translation unit.

Example 2 in the standard has three translation units:

```cpp title="TU1: module M"
export module M;
namespace R {
    export struct X {};
    export void f(X);
}
namespace S {
    export void f(R::X, R::X);
}
```

```cpp title="TU2: module N"
export module N;
import M;
export R::X make();
namespace R { static int g(X); }
export template<typename T, typename U> void apply(T t, U u) {
    f(t, u);
    g(t);
}
```

```cpp title="TU3: an implementation unit of module Q"
module Q;
import N;
namespace S {
    struct Z { template<typename T> operator T(); };
}
void test() {
    auto x = make();     // OK: x has type R::X from module M
    R::f(x);             // error: M is not imported here, so neither R nor R::f is visible
    f(x);                // OK: ¶4.3, R::f is exported, attached to M, and in R with the associated entity R::X
    f(x, S::Z());        // error: S is an associated namespace, but S::f in M does not satisfy ¶4.3:
                         //        the associated entity S::Z in S is attached to Q, not M
    apply(x, S::Z());    // error: S::f is visible in the instantiation context, but R::g has internal linkage
                         //        and cannot be used outside TU2
}
```

The last sentence of ¶4 is about dependent names in templates. For a dependent call, the lookup above is also done from each point in the instantiation context ([[module.context]]). Declarations in another translation unit that are attached to the global module and either discarded ([[module.global.frag]]) or have internal linkage are ignored. The common saying that "the second phase of two-phase lookup only does ADL" is, for modules, stated precisely by this sentence.

[[temp.dep.candidate#1]] adds one more rule: if considering all functions with external linkage in the associated namespaces in all translation units would make a dependent call find a better match or become ill-formed, the program is ill-formed, no diagnostic required.

## Idiom 1: the two-step swap

When generic code swaps two `T`, `std::swap(a, b)` is a qualified name and bypasses the efficient `swap` a user wrote for their type; `swap(a, b)` has no associated namespace when it meets `int` and does not find `std::swap`. The standard approach takes two steps:

```cpp run ok
#include <utility>
namespace N {
    struct Big { int d[100]; };
    void swap(Big&, Big&) noexcept { }   // custom efficient swap
}

template<class T>
void my_algo(T& a, T& b) {
    using std::swap;     // step 1: let unqualified lookup find std::swap as a fallback
    swap(a, b);          // step 2: unqualified call; ADL adds the swap from T's namespace
}

int main() {
    N::Big a, b;
    my_algo(a, b);       // selects N::swap: a non-template beats a template
    int i = 1, j = 2;
    my_algo(i, j);       // selects std::swap
}
```

It works because of three things: a block-scope using-declaration does not turn ADL off; the overload set contains both `std::swap` and `N::swap`; and in overload resolution a non-template beats a template, and a more specialized template beats a more general one.

This idiom is easy to get wrong, for example by forgetting the `using` or writing `std::swap`. So C++20 provides `std::ranges::swap`, a customization point object that does the same thing internally.

## Idiom 2: customization point objects and niebloids

ADL has two systemic problems. One is hijacking: an unqualified call in a generic library can be captured by a function that happens to have the same name in an argument type's namespace. The other is accidental ambiguity: when a library calls its own function, ADL finds an equally good candidate in another associated namespace.

```cpp run error
#include <vector>
#include <iterator>
#include <algorithm>
namespace N {
    struct X { bool operator==(const X&) const = default; };
    template<class It> int distance(It, It) { return 0; }
    template<class It, class T> It find(It b, It, const T&) { return b; }
}
int main() {
    std::vector<N::X> v(3);
    auto n  = distance(v.begin(), v.end());      // error: std::distance and N::distance are ambiguous
    auto it = find(v.begin(), v.end(), N::X{});  // error: std::find and N::find are ambiguous
}
```

`v.begin()` has the iterator type of `std::vector<N::X>` (in libc++, `std::__wrap_iter<N::X*>`). Its template argument `N::X*` brings `N` into the associated namespaces, and `std` is there already. The two function templates are equally good, so the call is ambiguous.

A **customization point object** (CPO, [[customization.point.object]]) makes a library entry point an object rather than a function:

- unqualified lookup finds a variable, which turns ADL off by ¶1.3, so the caller cannot be hijacked;
- ADL collects only functions and never finds the object, so it never forms an ambiguity with same-named functions elsewhere;
- the object's `operator()` does ADL internally in a controlled way and checks semantic requirements at the same time. For example, `std::ranges::swap` first blocks `std::swap` with an overload like `template<class T> void swap(T&, T&) = delete;` (commonly called a poison pill) and then does ADL; `std::ranges::begin` used to have such a poison pill too, but after [[P2602R2]] it does only argument-dependent lookup for a non-member `begin` ([[range.access.begin#2]]) and no longer needs one.

The algorithms in `std::ranges` (`find`, `sort`, …) have the same properties and are commonly called niebloids (after Eric Niebler). C++20 only required that they not be found by ADL and that they turn ADL off when found by unqualified lookup, without requiring them to be objects. Since C++26, the standard defines them directly as **algorithm function objects** ([[alg.func.obj]]):

```cpp run ok
#include <ranges>
#include <vector>
#include <algorithm>
void foo() {
    using namespace std::ranges;
    std::vector<int> vec{1, 2, 3};
    auto it = find(begin(vec), end(vec), 2);   // std::ranges::find: an object, ADL is off
    (void)it;
}
```

## Idiom 3: operators

An operator expression `a @ b` has no qualified form and cannot have ADL turned off with parentheses. [[over.match.oper#3]] specifies that its non-member candidates come from unqualified lookup of `operator@` plus ADL, ignoring all member functions; member candidates are searched for separately in the class of `a`. So unlike named calls, ADL always happens for operators.

Unqualified lookup stops at the first hit. So if a namespace declares any `operator<<` at all, outer `operator<<` are hidden, and only ADL can help:

```cpp run error
#include <iostream>
#include <vector>
std::ostream& operator<<(std::ostream& os, const std::vector<int>&) { return os; }
struct G {};
std::ostream& operator<<(std::ostream& os, G) { return os; }

namespace N {
    struct Z {};
    std::ostream& operator<<(std::ostream& os, Z);   // unqualified lookup stops at N
    void f(const std::vector<int>& v, G g) {
        std::cout << g;   // OK: G is in the global namespace; ADL finds ::operator<<
        std::cout << v;   // error: ADL looks only in std and does not find the global one
    }
}
```

Operators defined for a type should go in that type's namespace, preferably as hidden friends. An operator written at global scope for a type in `std` (such as `std::vector<int>`) is only found by unqualified lookup by accident, and stops working from inside another namespace. Adding such a declaration to `std` is forbidden by the standard ([[namespace.std]]).

## Other easily overlooked cases

```cpp run ok
#include <iostream>
#include <string>
#include <iterator>
int main() {
    endl(std::cout);        // OK: std::cout's type is in std; ADL finds std::endl
    std::string arr[3];
    auto b = begin(arr);    // OK: the array element type std::string brings in std
    (void)b;
}
```

- A lambda's closure type is a class type, and its innermost enclosing namespace is where the lambda appears. Passing a lambda as an argument brings that namespace in too.
- `f(nullptr)`, `f(0)` and `f(1.0)` never involve ADL.
- `std::array<N::X, 3>` brings in `N` (a type argument). The `N::E::a` in `std::integral_constant<N::E, N::E::a>` is a constant template argument and brings in nothing, but the type argument `N::E` still brings in `N`.

!!! impl
    - Clang implements ADL in `Sema::ArgumentDependentLookup` and uses `FindAssociatedClassesAndNamespaces` to compute the associated classes and namespaces per ¶3. A hidden friend's declaration is placed in the namespace but carries a flag that makes it invisible to ordinary lookup.
    - Modules: at instantiation, Clang computes which declarations ADL can see according to the instantiation context. A function that was `#include`d into the global module fragment but discarded because it was not referenced is invisible to ADL in other translation units (Example 4 in [[temp.dep.candidate#5]]).
    - ADL affects compile times: many namespace-scope operator templates make every `<<` trigger expensive overload resolution. This is one reason why, since C++20, new standard library components (such as ranges views and iterators) specify many of their operators as hidden friends.

!!! history "History"
    - C++98: ADL entered the standard. It was originally designed for operators and later extended to all unqualified function calls.
    - C++11: inline namespaces were introduced, and associated namespaces include the inline namespace set. The wording at that time stated explicitly that what turns ADL off is "a block-scope function declaration that is not a using-declaration".
    - C++20: [[P0846R0]] made `f<T>(x)` parse as a template name when no template is found or only functions are found, so that function templates can be called through ADL with explicit template arguments. Modules brought ¶4.3 and ADL in the instantiation context; ranges brought CPOs and niebloids.
    - C++23: [[P1787R6]] rewrote this subclause with concepts such as search and associated entities. That using-declarations do not turn ADL off is no longer stated separately; it follows from the replacement rule in [[basic.lookup#3]].
    - C++26: ¶3.1 associates `std::meta::info` with `std::meta`; niebloids are specified as algorithm function objects.

## Common misconceptions

!!! pitfall "Qualified and unqualified calls differ only in spelling"
    `std::swap(a, b)` and `using std::swap; swap(a, b)` may call different functions, and `std::begin(r)` and `std::ranges::begin(r)` have different semantics too. In generic code, choosing the form of a call is choosing the lookup rules.

!!! pitfall "Only the argument's own namespace is searched"
    Template arguments bring namespaces in too. `std::vector<mylib::Widget>` lets same-named functions in `mylib` take part in unqualified calls inside `std` algorithms; conversely, `mylib::Container<std::string>` lets `std` functions take part in your calls. Be especially careful when giving library functions names like `distance`, `find`, `size` or `data`.

!!! pitfall "Turning ADL off with parentheses or a qualified name is safe"
    `(swap)(a, b)` indeed cannot be hijacked, but it cannot find user customizations either. When a call must be both customizable and safe from hijacking, use a CPO.

## Questions

!!! question "Question 1"
    ```cpp
    namespace A { struct X {}; void f(X, int); }
    namespace B {
        void f(A::X, long);
        void g() { f(A::X{}, 0); }
    }
    ```
    Which `f` does the call in `B::g` select? What if `void f(A::X, long);` is added at the start of `g`'s body?

<details markdown="1">
<summary>Answer</summary>

As written, unqualified lookup finds `B::f` in `B`. It is a namespace member, which does not turn ADL off, and ADL then adds `A::f`. The overload set is `{B::f(X, long), A::f(X, int)}`; the argument `0` is an `int`, so `A::f` is an exact match and wins.

With the block-scope declaration added, unqualified lookup finds a function declaration in block scope, ¶1.2 turns ADL off, and only `B::f(A::X, long)` remains, so it is called. Running it with Clang 23 agrees.
</details>

!!! question "Question 2"
    Why must a niebloid turn ADL off when it is found by unqualified lookup? Why is it not enough that it is not found by ADL itself?

<details markdown="1">
<summary>Answer</summary>

If it were merely not found by ADL, then in `using namespace std::ranges; find(it, it, v)`, after unqualified lookup found `ranges::find`, ADL would still add `std::find` (the iterator is associated with `std`) and even `find` from the user's namespace to the overload set. `std::find` is an unconstrained function template and is often an equally good or better match, so the result would either bypass the ranges version or be ambiguous. Only turning ADL off guarantees that the constrained ranges algorithm is called. Implemented as an object, ¶1.3 achieves this naturally.
</details>

!!! question "Question 3"
    Given `template<int N> struct C {}; namespace N2 { enum E { e }; void f(C<e>); }`, can `f(C<N2::e>{})` written at global scope find `N2::f`?

<details markdown="1">
<summary>Answer</summary>

No. `C<N2::e>` is a specialization of a global class template; its only associated entity is itself, in the global namespace. `N2::e` is a constant template argument and, by note 3, contributes no associated entities. So the only associated namespace is the global namespace, and `N2::f` is not found. Clang 23 reports that `f` is undeclared.
</details>

## Summary

| Question | Answer |
|---|---|
| When it happens | an unqualified name used as a function call, when ordinary lookup found no class member, block-scope function declaration or non-function |
| How the result is used | combined with the unqualified lookup result into one overload set |
| What is associated | the class itself, enclosing classes, base classes (when complete), type template arguments, parameter and return types of function types; fundamental types bring nothing |
| Where it looks | the innermost enclosing non-inline namespaces and their inline namespace sets, with a search only (no using-directives followed); plus friends of associated classes |
| What it finds | only functions and function templates |
| Hidden friends | found only by ADL; small overload sets, no accidental selection through implicit conversion |
| Two-step swap | `using std::swap; swap(a, b);`; the using-declaration does not turn ADL off |
| CPOs / niebloids | objects: ADL is off, and they do ADL internally in a controlled way |
| Operators | non-member candidates = unqualified lookup (ignoring members) + ADL; cannot be turned off |
| `f<T>(x)` | since C++20, parsed as a template name when nothing or only functions are found, so ADL can be used |
