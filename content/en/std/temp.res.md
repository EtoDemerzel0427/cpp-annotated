---
title: Name resolution
summary: "When names in a template definition are looked up: non-dependent names are bound once at the definition, dependent names are looked up again in each specialization; when typename and template are required; and the group of IFNDR rules that let a compiler reject a template before it is instantiated."
updated: 2026-10-19
---

!!! tldr
    - A name in a template that doesn't depend on template parameters is looked up once at the definition and the result is fixed; a name that depends on template parameters is looked up again in each specialization after substitution.
    - Ordinary lookup for a dependent call `f(t)` is also done only at the definition; instantiation only adds ADL. So an `f(int)` declared after the definition is never visible for `T = int`.
    - A dependent qualified name is assumed to denote a value by default. To denote a type, write `typename`; to denote a template, write `template`. Since C++20, `typename` can be omitted in type-only contexts such as member declarations, aliases and return types, but is still required at block scope.
    - If a template can't possibly have a valid specialization, or a part of it that doesn't depend on template parameters is wrong in itself, the program is IFNDR: the compiler may reject it at the definition, or not.
    - Since C++23, failing `static_assert`s are not counted when deciding whether a valid specialization exists, so `else static_assert(false, "...")` is valid.

## The compiler has to parse the template at its definition

```cpp
template<class T> void f(T t) {
    T::x * p;      // a multiplication? or declaring a pointer p?
    t.get<0>();    // a member template? or (t.get < 0) > ()?
    g(t);          // which g?
}
```

C++ syntax depends on what names mean: whether `a * b` is an expression or a declaration, and whether `<` is less-than or the start of a template argument list, both depend on what the name refers to. Yet when the compiler reads this definition, it doesn't know what `T` is.

The standard's approach is to parse the template completely at its definition and divide the names in it into two kinds:

- **dependent names**: names whose meaning may vary with the template arguments, such as `T::x`, or a call `g(t)` whose argument type depends on `T`. The precise definition is in [[temp.dep]].
- **non-dependent names**: all other names.

¶1 Non-dependent names are looked up at the template definition, and the result is the same for every specialization. Dependent names are looked up again in each specialization, after the template arguments are substituted. Together these two lookups are usually called [[g:two-phase-lookup|two-phase name lookup]]; see [[topics/two-phase-lookup]].

!!! std
    If the name is dependent (as specified in [temp.dep]), it is looked up for each specialization (after substitution) because the lookup depends on a template parameter.

So that parsing at the definition can proceed, the programmer has to mark dependent names that denote types or templates with `typename` or `template` (see below). So that checking at the definition is meaningful, ¶6 specifies a group of violations: if a part of the template that doesn't depend on template parameters is wrong in itself, the compiler may reject it on the spot.

### Dependent and non-dependent calls (Example 2)

```cpp run ok title="two_phase.cpp"
#include <cstdio>
void f(char) { std::puts("f(char)"); }

template<class T> void g(T t) {
    f(1);        // non-dependent: only f(char) is visible here
    f(T(1));     // dependent call
    f(t);        // dependent call
}

enum E { e };
void f(E) { std::puts("f(E)"); }   // declared after g

int main() {
    g(e);        // f(char) f(E) f(E)
    g('a');      // f(char) f(char) f(char)
}
```

The argument of `f(1)` doesn't depend on `T`, so it isn't a dependent call. `f` is looked up at the definition, finds only `f(char)`, and is bound to it; no `f` declared afterwards changes that.

The argument types of `f(T(1))` and `f(t)` depend on `T`, so they are [[g:dependent-call|dependent calls]]. Their candidate functions come from two sources: the result of unqualified lookup at the definition, plus the results of [[g:argument-dependent-lookup|argument-dependent lookup]] (ADL) in both the definition context and the instantiation context ([[temp.dep.candidate]]). For `g(e)`, `T = E`, the associated namespace of `E` is the global namespace, and ADL finds the later-declared `f(E)`. For `g('a')`, `T = char`; fundamental types have no associated namespaces, ADL finds nothing, and only `f(char)` remains.

The standard's Example 2 also has a line `dd++;`, where `dd` is declared after the template. `dd` is not a dependent name, lookup at the definition fails, and the program is ill-formed. Clang and GCC don't wait for instantiation; they report an undeclared identifier at the definition:

```cpp error
template<class T> void g(T) {
    dd++;        // error: dd is not dependent and isn't found at the definition
}
double dd;
```

!!! pitfall "Ordinary lookup for a dependent call is not deferred"
    A common misconception is that all names in a template are looked up at instantiation. In fact only dependent names are deferred, and even for a dependent call, unqualified lookup is done only at the definition; instantiation only adds ADL. So an `f(int)` declared after `template<class T> void g(T t) { f(t); }` is never visible to `g(1)`, because `int` has no associated namespaces. The fix is to move the declaration of `f` before the template.

### Members of the template argument don't change the binding (Example 3)

```cpp run ok
struct A {
    struct B { };
    int a;
    int Y;
};

int a;

template<class T> struct Y : T {
    struct B { };
    B b;                       // Y's own B
    void f(int i) { a = i; }   // ::a, not A::a
    Y* p;                      // Y<T>, not A::Y
};

Y<A> ya;
int main() { ya.f(1); return a == 1 ? 0 : 1; }
```

The base class `A` of `Y<A>` happens to have the three members `B`, `a` and `Y`. But the base class `T` depends on a template parameter, and lookup at the definition doesn't search it ([[temp.dep.type#3]]), so the three names are bound at the definition to `Y::B`, `::a` and the injected-class-name `Y` respectively. They aren't looked up again when `Y<A>` is instantiated.

This way the meaning of a template is decided by what its author sees at the definition, and doesn't change with the types users pass in. To use a member of the base class, the name must be made dependent, for example `this->a` or `T::a`; see [[temp.dep.res]].

### Dependent conversion function names (Example 1)

```cpp run ok
struct A { operator int() { return 42; } };

template<class B, class T>
struct D : B {
    T get() { return operator T(); }   // dependent name
};

int f(D<A, int> d) { return d.get(); } // finds A::operator int
int main() { return f({}) == 42 ? 0 : 1; }
```

The target type of `operator T` depends on `T`, so by [[temp.dep.general#2]] it is a dependent name; it is looked up only in the specialization `D<A, int>`, where it finds the base class's `A::operator int`.

## Default arguments added later (¶2)

If ordinary lookup for a dependent call is done only at the definition, what about default arguments added to a function by a later redeclaration?

```cpp ifndr
void f(int, int);
template<class T> void g(T t) { f(t); }   // only f(int, int) is found at the definition
void f(int, int = 0);                     // redeclaration adding a default argument
void use() { g(1); }                      // IFNDR
```

¶2 If a declaration that introduces a default argument or default template argument is reachable from the point of instantiation of a specialization ([[temp.point]]), but isn't found by lookup in the specialization, and considering that default argument would change whether the program is valid or what it means, the program is {{ifndr}} (ill-formed, no diagnostic required: the standard doesn't require the compiler to diagnose it; see [[g:ifndr]]).

In the example above, lookup in `g<int>` finds only the first declaration, which has no default argument, and `int` has no associated namespaces. Considering the second declaration's default argument would make `f(t)` valid, which is exactly the situation ¶2 describes. No diagnostic is required because compilers usually record default arguments on the function entity, accumulating across declarations, and find it hard to tell which declaration a default argument came from. Clang 23 reports an error here and suggests that `f` should be declared before the call site.

## typename: declaring that a dependent name is a type (¶3)

```text
typename-specifier:
    typename nested-name-specifier identifier
    typename nested-name-specifier template(opt) simple-template-id
```

¶3 The type (or class template) denoted by a *typename-specifier* is whatever the *simple-type-specifier* left after removing `typename` denotes ([[dcl.type.simple]]). `typename` only assures the parser that a type appears here; it doesn't change the lookup itself.

So Note 2 points out specifically that with `typename`, ordinary qualified name lookup is still performed ([[basic.lookup.qual]]). If what is found at instantiation is not a type, the program is ill-formed:

```cpp error
struct A {
    struct X { };
    int X;            // data member X hides class X
};
struct B { struct X { }; };

template<class T> void f(T) { typename T::X x; }

void foo() {
    f(B{});           // OK: B::X is a class
    f(A{});           // error: finds the data member A::X
}
```

The elaborated type specifier `struct T::X` uses type-only lookup ([[basic.lookup.elab]]) and skips data members; `typename T::X` doesn't.

`typename` can only precede a name with a nested-name-specifier; `typename int` is invalid. Since C++11 it can also be used outside templates, where it is just redundant:

```cpp ok
struct S { using type = int; };
typename S::type x = 0;   // OK
```

## Type-only contexts: where typename can be omitted (¶4–¶5)

In C++17 and earlier, a dependent qualified name that denoted a type always required `typename`, with base class lists and mem-initializers as the only exceptions. C++20's [[P0634R3]] observed that many positions can syntactically only be types, where requiring `typename` serves no purpose, and introduced the [[g:type-only-context|**type-only context**]].

<div class="compare" markdown="1">

```cpp ok
template<class T> struct S {
  using A = T::R;      // alias
  T::R m;              // member declaration
  void f(T::R);        // member function parameter
  auto g() -> T::R;    // trailing return type
};
```

```cpp error
template<class T> void f() {
  T::R local;
  // error: block scope is not a
  // type-only context, typename needed
}
```

</div>

¶5 A qualified name in a type-only context whose terminal name is dependent is assumed to name a type. A dependent qualified name not in a type-only context is assumed not to name a type, unless `typename` is written. The [[g:terminal-name|terminal name]] here means the last name in the qualified name, the `R` in `T::R`.

¶4 The terminal name in the following constructs is in a type-only context:

| Paragraph | Position | Example |
|---|---|---|
| ¶4.1 | *typename-specifier*, *type-requirement*, nested-name-specifier, elaborated type specifier, base specifier and mem-initializer, *using-enum-declarator* | `struct D : T::Base` |
| ¶4.2 | friend type declaration | `friend T::R;` |
| ¶4.3.1 | the type in `new` | `new T::R{}` |
| ¶4.3.2 | the type in an alias-declaration | `using A = T::R;` |
| ¶4.3.3 | the type of a conversion function | `operator T::R();` |
| ¶4.3.4 | trailing return type | `auto f() -> T::R;` |
| ¶4.3.5 | default argument of a type template parameter | `template<class U = T::R>` |
| ¶4.3.6 | target type of the four named casts | `static_cast<T::R>(x)` |
| ¶4.4.1 | a declaration or function definition at namespace scope | `template<class T> T::R f();` |
| ¶4.4.2 | member declaration | `T::R m;` |
| ¶4.4.3 | parameters in a member declaration (except inside default arguments) | in-class `void f(T::R);` |
| ¶4.4.4 | parameters of a function whose declarator-id is qualified | `void S<T>::f(T::R) {}` |
| ¶4.4.5 | lambda parameters, parameters of a *requires*-expression | `[](T::R r) {}` |
| ¶4.4.6 | the type of a constant template parameter | `template<T::R V>` |

What these positions have in common: if what appears there weren't a type, the syntax wouldn't work. Every position outside the table admits a valid expression interpretation, and `typename` is still required there, including block-scope declarations, parameters of ordinary namespace-scope functions, template arguments (`std::vector<typename T::R>`), and the operands of `sizeof` and `decltype`.

{{c++26}} The end of ¶4 also says that whether a splice specifier `[: ... :]` is in a type-only context is decided as if a hypothetical qualified name appeared in the same position. So `using Alias = [:^^int:];` doesn't need `typename`.

The following example puts most of the positions in the table together:

```cpp run ok title="down_with_typename.cpp"
template<class T, class U = T::R>             // ¶4.3.5
struct S {
    T::R m;                                   // ¶4.4.2
    void f(T::R);                             // ¶4.4.3
    operator T::R();                          // ¶4.3.3
    static T::R sm;
    friend T::R;                              // ¶4.2
    using A = T::R;                           // ¶4.3.2
    auto g() -> T::R { return static_cast<T::R>(m); }   // ¶4.3.4, ¶4.3.6
};
template<class T, class U> void S<T, U>::f(T::R) { }   // ¶4.4.4
template<class T, class U> T::R S<T, U>::sm{};          // ¶4.4.1

template<class T> T::R gv{};                  // ¶4.4.1
template<class T> void blk() {
    auto l = [](T::R r) { return r; };        // ¶4.4.5
    typename T::R local{};                    // block scope: typename still required
    auto* p = new T::R{};                     // ¶4.3.1
    delete p; (void)l; (void)local;
}

struct X { using R = int; };
template struct S<X>;
template void blk<X>();
int main() { }
```

### The scope of the parameter decides whether it can be omitted

¶4.4.3 and ¶4.4.4 only cover member functions and functions declared with a qualified name. Parameters of an ordinary namespace-scope function aren't in the table, and the result is completely different:

```cpp ifndr
template<class T> T::R f();          // OK: return type of a namespace-scope declaration
template<class T> void f(T::R);      // IFNDR: declares a void variable template
```

The `f` on the second line isn't a qualified name, its parameter isn't in a type-only context, and `T::R` is treated as an expression. So `void f(T::R)` is parsed as a variable template of type `void`, direct-initialized with `(T::R)`. A `void` variable can't possibly have a valid specialization, so by ¶6.1 it's IFNDR. Clang 23 reports here that the variable has incomplete type `void`.

Why the difference? At namespace scope, `int x(expr);` is a valid direct-initialization, so `void f(T::R);` really could be a variable declaration. Inside a class, members can't be initialized with parentheses, and a qualified declaration like `S<T>::f(...)` can only be a function, so its parameters can't be misread as an initializer.

Block scope works the same way, and it's even easier to misread:

```cpp error
template<typename T> void f() {
    void (*pf)(T::X);   // OK: void* variable pf, initialized with T::X
    void g(T::X);       // error: attempts to declare a void variable g
}
```

The first line is not a function pointer. `T::X` is treated as an expression, and `void (*pf)(T::X)` declares a variable `pf` of type `void*`, direct-initialized with `T::X`.

### A dependent name outside a type-only context is assumed to be a value (Example 6)

```cpp error
template <class T> void f(int i) {
    T::x * i;           // expression (multiplication), not declaring a variable i
}

struct Foo { typedef int x; };
struct Bar { static int const x = 5; };

int main() {
    f<Bar>(1);          // OK
    f<Foo>(1);          // error: Foo::x is a type
}
```

`T::x * i` was already parsed as a multiplication at the definition. When `f<Foo>` is instantiated, lookup finds a type, which contradicts the parse, and the program is ill-formed.

¶5 has one more sentence: if the terminal name of a *using-declarator* is dependent and preceded by `typename`, names referring to it are treated as *typedef-name*s.

```cpp run ok
template<class T> struct Base { using type = T; };
template<class T> struct D : Base<T> {
    using typename Base<T>::type;   // dependent using-declaration with typename
    type x{};                       // type is treated as a typedef-name
};
D<int> d;
int main() { }
```

## template: declaring that a dependent name is a template

`typename` resolves types; `template` resolves `<`. The rule is in [[temp.names#7]]: `<` starts a template argument list only if the preceding name is found by lookup to be a template, is preceded by the `template` keyword, or meets a few syntactic conditions. A dependent member name can't be found at the definition, so `template` is needed:

<div class="compare" markdown="1">

```cpp error
template<class T> void f(T* p) {
  T* q = p->alloc<200>();
  // error: < treated as less-than
}
```

```cpp ok
template<class T> void f(T* p) {
  T* q = p->template alloc<200>();
  T::template adjust<100>();
}
```

</div>

Without `template`, `p->alloc<200>()` is parsed as `(p->alloc < 200) > ()`, and `()` is not an expression. Cases where `template` isn't needed:

- Unqualified lookup of the name finds a function, or finds nothing. C++20's [[P0846R0]] added this, so `get<0>(t)` parses even when no `get` template is visible.
- The name is the terminal name in a type-only context (¶7.3.4), such as `typename T::Y<int>` or the member declaration `T::Y<int> m;`.
- The name is a member of the current instantiation and lookup at the definition finds a template.

Writing `template` when a template can already be found is still well-formed ([[temp.names#11]]).

!!! impl "Clang hasn't implemented ¶7.3.4"
    Per the current draft, `typename T::Y<int>`, the in-class `T::Y<long> b;` and `using Z = T::Y<char>;` don't need `template`. Clang 23 still rejects all three and asks for `template`. Portable code should keep writing `typename T::template Y<int>`.

## Checking templates before instantiation (¶6)

¶6 The validity of a [[g:templated-entity|templated entity]] (a template, and everything defined in a template) may be checked before any instantiation. Note 3 points out the prerequisite: with `typename` and `template`, the compiler knows which names are types and which are templates, so it can check the syntax of every template.

¶6 then lists a group of IFNDR cases. They give the compiler permission to report errors at the definition, but don't require it.

### No valid specialization possible (¶6.1)

¶6.1 If no valid specialization, ignoring failing `static_assert`s, can be generated for a templated entity, or for a substatement of a constexpr if statement within it, and the innermost enclosing template is not instantiated, the program is IFNDR.

No valid specialization being possible means the code is wrong whatever the template arguments are. Examples are `void f(T::R)` above, which is parsed as a `void` variable template, or `int a[-int(sizeof(T))];`, whose array bound is always negative. Such a template has no reason to exist, and the standard lets compilers reject it early. Diagnosis isn't required because proving that no valid specialization exists is undecidable in general.

If the template is in fact instantiated, the error is handled by the ordinary rules: the program is ill-formed and a diagnostic is required.

### static_assert(false) {{c++23}}

The half-sentence in ¶6.1 about ignoring failing `static_assert`s was added by C++23's [[P2593R1]]:

```cpp run ok title="static_assert_false.cpp"
#include <type_traits>
template<class T> int classify(T) {
    if constexpr (std::is_integral_v<T>)            return 1;
    else if constexpr (std::is_floating_point_v<T>) return 2;
    else static_assert(false, "unsupported type");  // OK since C++23
}
int a = classify(1), b = classify(1.0);

template<class T> void never_used() { static_assert(false); }  // OK: never instantiated
int main() { }
```

Before C++23, the substatement `else static_assert(false, ...)` couldn't possibly have a valid specialization, the whole program was IFNDR, and in practice GCC and Clang reported the assertion failure right at the definition. Programmers had to write a false condition that depended on `T`:

```cpp
template<class> inline constexpr bool dependent_false = false;
// ...
else static_assert(dependent_false<T>, "unsupported type");
```

This worked because `dependent_false<T>` depends on `T`; in theory some explicit specialization could make it `true`, so a valid specialization existed.

C++23's rule is more direct. [[dcl.pre#13]] says a `static_assert` evaluated in a template definition has no effect, and ¶6 ignores failing assertions when deciding whether a valid specialization exists. A discarded constexpr if branch is not instantiated ([[stmt.if#2]]), so the assertion is never evaluated; the branch actually chosen is evaluated at instantiation, and if it fails, the error is reported as usual:

```cpp error
template<class T> int f(T) {
    if constexpr (sizeof(T) == 4) return 1;
    else static_assert(false, "unsupported type");
}
int c = f('a');   // error: f<char> takes the else branch, assertion fails
```

P2593R1 was handled as a defect report, and compilers usually apply the new behavior in earlier language modes too.

!!! lawyer "A static_assert that doesn't depend on template parameters is deferred too"
    [[dcl.pre#13]] doesn't distinguish whether the condition depends on template parameters. So `template<class T> void f(T) { static_assert(sizeof(int) == 0); }` causes no error at the definition and fails only when `f` is instantiated; Clang 23 behaves this way. This only holds inside templates: `if constexpr (false) { static_assert(false); }` in a non-template function still fires, because a discarded statement outside a template is still fully checked.

### Parts that don't depend on template parameters must be right now (¶6.7–¶6.8)

¶6.7 Imagine an instantiation performed immediately after the closing brace of the template definition. If this hypothetical instantiation would be ill-formed because of a construct that doesn't depend on template parameters (other than a failing `static_assert`), the program is IFNDR. A construct that doesn't depend on template parameters already has a definite meaning at this point; if it is wrong now, it is wrong in every instantiation.

<div class="compare" markdown="1">

```cpp error
template<class T> void f() {
  int* p = 1;
  // int can't initialize int*
}
```

```cpp error
struct Inc;
template<class T> int f(T) {
  return sizeof(Inc);  // incomplete here
}
struct Inc { int x; };
```

</div>

In the example on the right, even if every instantiation of `f` happens after `Inc` is complete, `Inc` is still incomplete in the hypothetical instantiation right after the definition, so it's IFNDR. Clang 23 reports both examples at the definition.

¶6.8 is about meaning: if a construct is valid in the hypothetical instantiation but its interpretation differs from its interpretation in some actual instantiation, the program is also IFNDR. Note 4 lists the typical cases:

- ¶6.9 a type used by a non-dependent name is incomplete at the definition but complete at the instantiation;
- ¶6.10 lookup at the definition finds a *using-declaration* that is a pack expansion, and the corresponding pack is empty at instantiation, so nothing is found;
- ¶6.11 the instantiation uses a default argument or default template argument that didn't exist when the template was defined;
- ¶6.12 constant evaluation in the instantiation uses the value of a const integral or unscoped enumeration object, the value of a constexpr object, the value of a reference, or the definition of a constexpr function that wasn't defined when the template was defined;
- ¶6.13 the specialization named by a non-dependent *simple-template-id* comes from a partial specialization not yet defined when the template was defined, or is an explicit specialization not yet declared at that point.

An example of ¶6.12:

```cpp ifndr
constexpr int k();
template<class T> void f() { int a[k()]; (void)a; }   // k is not defined at the definition
constexpr int k() { return 3; }
template void f<int>();                                  // at the instantiation k() == 3
```

At the definition, calling an undefined constexpr function isn't a constant expression, so `int a[k()]` is a variable-length array, which is ill-formed in standard C++; at the instantiation it is `int[3]`. The two interpretations differ, so it's IFNDR. Clang 23 treats it as a variable-length array (a Clang extension) at the definition and gives a `-Wvla-cxx-extension` warning, which shows it really did fix the interpretation at the definition.

The idea behind these rules: a construct that doesn't depend on template parameters should have its meaning settled at the definition, and later declarations shouldn't change it. A compiler may parse and bind immediately at the definition (GCC, Clang) or defer until instantiation (old MSVC). Every program for which the two strategies would give different results is made IFNDR, so the meaning of a valid program doesn't depend on which strategy the compiler chooses.

### The remaining cases (¶6.2–¶6.6)

- ¶6.2 {{c++26}} The body of an expansion statement (`template for`, [[stmt.expand]]) is instantiated once per element. If it is never instantiated (for example when iterating over an empty tuple) and couldn't possibly be valid, the program is IFNDR.
- ¶6.3 A default template argument can't produce a valid specialization and is never used in any instantiation.
- ¶6.4 An alias template ([[temp.alias]]) has no valid specialization, and no specialization of it is ever named in the program.
- ¶6.5 The normal form of some constraint expression contains an atomic constraint for which no satisfaction check could be well-formed, and it is never checked.
- ¶6.6 Every valid specialization of a variadic template requires a template parameter pack to be empty. A template that can only be instantiated with an empty pack has no reason to be variadic. For example, a member `void operator++(int, T... t);`: postfix `++` can only have one `int` parameter, so the pack must be empty. Clang 23 rejects it outright.

### Which errors can be diagnosed early (Example 7)

Note 5 says that once a template is instantiated, errors are diagnosed per the other rules of the standard, and exactly when diagnostics are issued is a quality-of-implementation issue. Example 7 marks which errors can be diagnosed before instantiation:

```cpp
int j;
template<class T> class X {
    void f(T t, int i, char* p) {
        t = i;          // dependent: diagnosed only if X::f is instantiated and the assignment is invalid
        p = i;          // non-dependent: may be diagnosed even if X::f is never instantiated
        p = j;          // likewise
        X<T>::g(t);     // OK: g is a member of the current instantiation
        X<T>::h();      // may be diagnosed early: no h in the current instantiation and no dependent base
    }
    void g(T t) {
        +;              // syntax error: may be diagnosed early
    }
};
```

`X<T>::h()` can be diagnosed early because of [[temp.dep.type#5]]: when the lookup context of a qualified name is the current instantiation (the template referring to `X<T>` itself from inside, see [[temp.dep]]) and there are no dependent base classes, a name that isn't found is not dependent, and its absence can be determined at the definition. If `X` had a dependent base class, `h` might come from there, and the check would have to wait for instantiation.

## Default arguments and noexcept-specifiers (¶7)

¶7 Note 6 explains that, for name lookup, the default arguments and *noexcept-specifier*s of function templates and of member functions of class templates are treated as definitions ([[temp.decls]]). Like function bodies, they are instantiated separately when used ([[temp.inst]]), and the names in them are looked up by the two-phase rules on this page. That's why [[temp.point]] specifies separate points of instantiation for them.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

The first sentence of ¶1 handles a template with multiple declarations (for example, seeing several copies of the same definition through module imports): a name is looked up from where it appears in some unspecified declaration of `T` that either is `D` itself or is reachable from `D`, and from which no other declaration of `T` containing the use is reachable. Intuitively, the newest declaration containing the name. For ordinary code you can simply think of it as: a name is looked up from where it appears in the template definition.

Note 1 adds two points. Some dependent names are also looked up once during parsing, to decide whether they are dependent or whether a following `<` starts a template argument list ([[temp.names#7]]); what they actually refer to is still decided by the lookup at instantiation. A *using-declarator* is never dependent in a specialization, so lookup in the specialization replaces it with the declarations it names ([[basic.lookup.general]]).

</details>

!!! impl "Two-phase lookup in the three major compilers"
    - Clang and GCC build a full syntax tree on seeing a template definition, bind non-dependent names, keep the dependent parts as dependent nodes, and substitute at instantiation. ¶6 allows them to report errors at the definition, and they use this permission heavily: `p = i`, undeclared identifiers, incomplete types, and so on.
    - MSVC used to store template bodies as token sequences and parse them only at instantiation, so for a long time it accepted non-conforming code that omits `typename` or uses members of dependent bases directly (see [[temp.dep.res]]). Since VS 2017, `/permissive-` mode implements conforming two-phase lookup, and `/Zc:twoPhase-` turns it off.
    - Clang's `-fdelayed-template-parsing` mimics old MSVC behavior by deferring parsing of function template bodies to the end of the translation unit. This is non-conforming, and in C++20 and later modes Clang warns that the option is deprecated.

!!! history "History"
    | Version | Change |
    |---|---|
    | C++98 | two-phase lookup, disambiguation with `typename` and `template`, and "no valid specialization means IFNDR" already exist; `typename` can only be used inside templates |
    | C++11 | the `typename` and `template` prefixes can be used outside templates |
    | C++17 | the discarded substatement of constexpr if is not instantiated, and ¶6.1 judges constexpr if substatements separately |
    | C++20 | [[P0634R3]] introduces type-only contexts; [[P0846R0]] makes `name<...>(args)` parse as a template even when lookup finds nothing |
    | C++23 | [[P1787R6]] rewrites name lookup in terms of component names, terminal names and lookup contexts; [[P2593R1]] excludes failing `static_assert`s from the valid-specialization test |
    | C++26 | expansion statements (¶6.2); splice specifiers brought into type-only contexts |

## Common misconceptions

!!! pitfall "typename makes lookup find only types"
    It doesn't. `typename T::X` performs ordinary qualified lookup, and finding a data member is an error (Note 2). To look up types only, use the elaborated type specifier `struct T::X`.

!!! pitfall "Since C++20, typename can always be omitted"
    Only in type-only contexts. It is still required in block-scope declarations, parameters of ordinary namespace-scope functions, template arguments, and the operands of `sizeof` and `decltype`, because every one of these positions admits a valid expression interpretation.

!!! pitfall "If it compiles on one compiler, the template is fine"
    Most of the cases in ¶6 are IFNDR. Clang and GCC catch some of them; MSVC's permissive mode lets almost all of them through. When code starts failing after switching compilers or upgrading, it has often run into ¶6.

## Questions

!!! question "Question 1"
    Is the following code well-formed under C++20? If not, what kind of error is it?
    ```cpp
    template<class T> struct S {
        void f(T::type);
    };
    template<class T> void g(T::type);
    ```

<details markdown="1">
<summary>Answer</summary>

The parameter of `S::f` falls under ¶4.4.3 (parameters in a member declaration), which is a type-only context, so `T::type` is treated as a type: well-formed.

`g` is a namespace-scope function template, the name `g` isn't qualified, and its parameter falls under none of the items in ¶4.4. `T::type` is treated as an expression, and `void g(T::type);` is parsed as a `void` variable template initialized with `T::type`, which can't possibly have a valid specialization, so by ¶6.1 it's IFNDR (the second line of Example 5 in [temp.res.general] in the draft is exactly this case). Write `template<class T> void g(typename T::type);`.
</details>

!!! question "Question 2"
    ```cpp
    template<class T> void f() {
        if constexpr (false) {
            int* p = 1;
        }
    }
    ```
    `f` is never instantiated. Is this program well-formed? What if `int* p = 1;` is replaced with `static_assert(false);`?

<details markdown="1">
<summary>Answer</summary>

`int* p = 1;` doesn't depend on template parameters, and it is ill-formed in the hypothetical instantiation immediately after the definition described in ¶6.7, even though it is in a discarded branch. constexpr if only avoids instantiating the discarded branch; it doesn't make errors that don't depend on template parameters valid. So the program is IFNDR, and Clang and GCC do report it at the definition.

With `static_assert(false);` instead, it is well-formed (since C++23, [[P2593R1]]): ¶6.1 and ¶6.7 both exclude failing `static_assert`s, and the discarded branch is never instantiated.
</details>

!!! question "Question 3"
    Why doesn't the standard require errors that don't depend on template parameters to be diagnosed at the definition, making them IFNDR instead?

<details markdown="1">
<summary>Answer</summary>

First, "no valid specialization exists" is a claim about all possible template arguments, undecidable in general, so a diagnostic can't be required. Second, the standard wants implementations that defer parsing (old MSVC, Clang's `-fdelayed-template-parsing`) to still be able to conform. Third, issues like ¶6.8 require comparing the definition context with the instantiation context; requiring a diagnostic would mean rechecking every construct that doesn't depend on template parameters at every instantiation, which is expensive. IFNDR puts the responsibility on the programmer while allowing good implementations to report errors early.
</details>

## Summary

| Rule | Paragraph | Consequence |
|---|---|---|
| Non-dependent names are looked up and bound once at the definition | ¶1 | later declarations don't affect them |
| Dependent names are looked up again in each specialization after substitution | ¶1 | dependent calls only add ADL at instantiation; see [[temp.dep.res]] |
| A reachable but unfound default argument changes the meaning | ¶2 | {{ifndr}} |
| `typename` performs ordinary qualified lookup | ¶3 | ill-formed if a non-type is found |
| Dependent qualified names in type-only contexts are assumed to be types | ¶4–¶5 | `typename` can be omitted (C++20) |
| Dependent qualified names elsewhere are assumed not to be types | ¶5 | `T::x * i` is a multiplication |
| No valid specialization possible (ignoring failing `static_assert`s) | ¶6.1–¶6.6 | {{ifndr}} |
| A construct not depending on template parameters is ill-formed or means something different in the hypothetical instantiation | ¶6.7–¶6.8 | {{ifndr}} |
| Default arguments and noexcept-specifiers are treated as definitions | ¶7 | instantiated only when used |
