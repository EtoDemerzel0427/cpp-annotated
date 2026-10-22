---
title: Dependent names
summary: "What counts as depending on a template parameter: dependent calls, the current instantiation and dependent base classes, dependent qualified names and dependent types, type-dependent and value-dependent expressions, and the dependent splices and dependent namespaces brought by C++26 reflection."
updated: 2026-10-19
---

!!! tldr
    - Whether a construct depends on template parameters decides whether it is checked at the definition or deferred to each specialization. The test is syntactic and conservative: `sizeof(T) * 0` is always 0 but still counts as dependent.
    - A call through an unqualified name is a dependent call as soon as some argument's type depends on a template parameter, and ADL is added at instantiation.
    - Inside a class template, `X` and `X<T>` refer to the current instantiation. Its members can be looked up at the definition without `typename`; if a name isn't found and there are no dependent bases, an error can be reported at the definition.
    - A dependent base class (a base that depends on template parameters and isn't the current instantiation) isn't searched at the definition, so its members must be accessed through `this->` or a qualified name.
    - Type-dependent means the type of an expression may vary; value-dependent means its constant value may vary. The type of `sizeof(t)` is always `size_t`, but its value depends on `T`.

## Dependence decides when checking happens

```cpp error
template<class T> void g(T t) {
    int i = 0;
    auto a = i;
    a.foo();            // error: a has type int, can be diagnosed at the definition
    auto b = t;
    b.foo();            // OK for now: b's type depends on T, deferred to instantiation
}
```

[[temp.res]] specifies that dependent names are looked up again in each specialization after substitution, and other names are looked up once at the definition. This subclause gives the precise definition of "dependent". Almost every kind of construct in a template can be asked whether it is dependent:

| What | Definition | What happens when it is dependent |
|---|---|---|
| function call | dependent call, [[temp.dep.general#2]] | lookup of the called function is deferred, ADL added at instantiation |
| qualified name | [[temp.dep.type#5]] | lookup deferred to instantiation; `typename` or `template` needed if it names a type or template |
| type | [[temp.dep.type#10]] | semantic checks involving this type are deferred |
| type of an expression | type-dependent, [[temp.dep.expr]] | overload resolution and member lookup are deferred |
| value of an expression | value-dependent, [[temp.dep.constexpr]] | constant evaluation is deferred (array bounds, template arguments, `if constexpr`, etc.) |
| splice specifier, namespace alias {{c++26}} | [[temp.dep.splice]], [[temp.dep.namespace]] | the reflected entity is determined later |
| template argument | [[temp.dep.temp]] | the template specialization it appears in is a dependent type |

These definitions refer to each other: a dependent type can be built from a value-dependent array bound, a type-dependent expression comes from a variable declared with a dependent type, and value dependence has type dependence as one of its conditions. Running through all of it is the notion of the current instantiation, which lets a class template's references to its own members still be checked at the definition.

## Dependent calls ([temp.dep.general])

¶1 Some constructs in a template may have semantics that differ from one instantiation to another; such constructs **depend** on the template parameters. An expression may be:

- [[g:type-dependent|**type-dependent**]]: its type may depend on template parameters;
- [[g:value-dependent|**value-dependent**]]: its value when evaluated as a constant expression may depend on template parameters.

The test is syntactic and leans conservative. `sizeof(T) * 0` is 0 for every `T`, but it is still value-dependent. Compilers don't try to prove that an expression doesn't actually depend; that's what keeps the rules decidable and the implementations in agreement.

¶2 A [[g:dependent-call|**dependent call**]] is an expression of the form *postfix-expression* `(` *expression-list*ₒₚₜ `)` where the *postfix-expression* is an unqualified name and one of the following holds:

- ¶2.1 some argument is a pack expansion ([[temp.variadic]]);
- ¶2.2 some argument is a type-dependent expression or braced list;
- ¶2.3 the called name is a *template-id* with dependent template arguments, such as `get<I>(t)` where `I` is a template parameter.

The non-member candidates for an operator expression are judged by the same call form ([[over.match.oper]]). Only unqualified names can make dependent calls: `N::f(t)` is judged by the rules for qualified names, and in `(f)(t)` the callee isn't an unqualified name. This corresponds exactly to the conditions that trigger ADL ([[basic.lookup.argdep#1]]), since the whole point of a dependent call is to add ADL at instantiation.

An unqualified name is dependent if:

- ¶2.4 it is a conversion function name `operator T` whose target type is dependent;
- ¶2.5 it is `operator=` and the current class is a templated entity;
- ¶2.6 it is the name called in a dependent call.

Note 1 explains that such names are looked up only at the point of instantiation ([[temp.point]]), considering both the definition context and the instantiation context ([[temp.dep.candidate]]).

`operator=` is special because every instantiation of a class template declares a different set of assignment operators: the implicitly declared copy assignment has parameter type `const X<T>&`, which doesn't exist yet at the definition.

```cpp run ok
struct B { B& operator=(int) { return *this; } };
template<class T> struct D : B {
    void f() { operator=(1); }   // dependent name (¶2.5): not looked up at the definition
};
int main() { }
```

If `D<int>::f` is instantiated, lookup finds the copy and move assignment operators implicitly declared by `D<int>`, which hide `B::operator=(int)`, and the call fails. Written as a non-template `struct D : B`, the same code is rejected by Clang immediately; inside a template, the error is deferred to instantiation, which shows that `operator=` really is treated as a dependent name.

¶3 Example 1 lists a few obviously dependent names: in `template<class T> struct X : B<T>`, the base class name `B<T>`, the type name `T::A`, and the names `B<T>::i` and `pb->j` (where `pb` has type `B<T>*`) all depend on the template parameter.

## The current instantiation ([temp.dep.type])

If everything involving `X<T>` inside a class template counted as dependent, a class template would need `typename` for every use of its own member types, and every call to its own members could only be checked at instantiation. The notion of the current instantiation tells the compiler that `X<T>` in the definition of `X` is the class itself, whose members are already visible at the definition.

¶1 A name or *template-id* refers to the [[g:current-instantiation|**current instantiation**]] if it is:

- ¶1.1 in the definition of a class template, a nested class of a class template, or a member of either, the injected-class-name ([[temp.local]]) of the class template or nested class;
- ¶1.2 in the definition of a primary class template or a member of one, the name of the class template followed by the template argument list of its template-head, i.e. `X<T>` (or an equivalent alias template specialization);
- ¶1.3 in the definition of a nested class, the name of the nested class referenced as a member of the current instantiation, such as `A<T>::B`;
- ¶1.4 in the definition of a partial specialization or a member of one, the name of the class template followed by a template argument list equivalent to that of the partial specialization;
- ¶1.5 in the definition of a templated function, the name of a local class ([[class.local]]).

¶2 A template argument that is equivalent to a template parameter can be used in place of that parameter. For a type parameter, an argument denoting the same type is equivalent to it. For a constant parameter, an equivalent argument must be an identifier naming a variable that is equivalent to the parameter. A variable is equivalent to a template parameter if: ¶2.1 it has the same type (ignoring cv-qualification); and ¶2.2 its initializer is a single identifier naming the template parameter or, recursively, such a variable. Note 1 adds that parenthesizing a variable name breaks the equivalence.

```cpp run ok
template <class T> class A {
    A* p1;                        // current instantiation
    A<T>* p2;                     // current instantiation
    A<T*>* p3;                    // not the current instantiation
    ::A<T>* p4;                   // current instantiation (¶1.2)
    class B {
        B* p1;                    // current instantiation (nested class B)
        A<T>::B* p2;              // current instantiation (¶1.3)
        typename A<T*>::B* p3;    // not the current instantiation
    };
};

template <class T> class A<T*> {
    A<T*>* p1;                    // current instantiation (¶1.4)
    A<T>* p2;                     // not the current instantiation
};

template <class T1, class T2, int I> struct B {
    B<T1, T2, I>* b1;             // current instantiation
    B<T2, T1, I>* b2;             // not
    typedef T1 my_T1;
    static const int my_I = I;
    static const int my_I2 = I+0;
    static const int my_I3 = my_I;
    static const long my_I4 = I;
    static const int my_I5 = (I);
    B<my_T1, T2, my_I>* b3;       // current instantiation
    B<my_T1, T2, my_I2>* b4;      // not: I+0 isn't a single identifier
    B<my_T1, T2, my_I3>* b5;      // current instantiation: recursively equivalent
    B<my_T1, T2, my_I4>* b6;      // not: long and int are different types
    B<my_T1, T2, my_I5>* b7;      // not: parenthesized
};
int main() { }
```

`I+0` doesn't count as equivalent because deciding it would require constant evaluation and algebraic reasoning. The rule only accepts direct restatements and is purely syntactic, so every compiler reaches the same conclusion.

What being the current instantiation actually affects is whether names can be looked up at the definition. `A<T>` is the current instantiation, so `A<T>::B` is found at the definition, known to be a type, and doesn't need `typename`. `A<T*>::B`, on the other hand, could be turned into something completely different by a partial specialization for `A<U*>`, so it can only be treated as a dependent name:

```cpp error
template<class T> struct A2 {
    struct Nested { int v; };
    void h() {
        A2<T>::Nested n{};        // OK: member of the current instantiation
        A2<T*>::Nested m{};       // error: not the current instantiation, typename required
    }
};
```

!!! impl "Clang's support for equivalent variables is incomplete"
    The big example above compiles under Clang 23 only because member declarations are type-only contexts anyway. Writing `A<k>::type x = 0;` in a member function body (where `k` is a variable equivalent to the parameter `N`), Clang 23 doesn't treat `A<k>` as the current instantiation and still requires `typename`; `A<k>::nonexistent()` isn't reported at the definition either. `A<N>::nonexistent()`, written directly with the template parameter, is reported at the definition.

### Dependent base classes (¶3)

¶3 A [[g:dependent-base-class|**dependent base class**]] is a base class that is a dependent type and is not the current instantiation.

Dependent base classes are not searched at the definition: [[class.member.lookup#4]] only merges lookup results from non-dependent direct bases. The reason is that `Base<T>` can be explicitly specialized into anything, so the primary template's members seen at the definition can't stand for the real members at instantiation. This is the root of why members of a dependent base must be accessed through `this->` or a qualified name; see [[temp.dep.res]].

Note 2 points out that a base class can also be the current instantiation, for example a nested class using the enclosing class as a base:

```cpp run ok
template<class T> struct A {
    typedef int M;
    struct B {
        typedef void M;
        struct C;
    };
};

template<class T> struct A<T>::B::C : A<T> {
    M m;                          // OK: A<T>::M (int)
};
A<int>::B::C c;
int main() { }
```

`A<T>` is the current instantiation, not a dependent base class, so it is searched at the definition and `A<T>::M` is found.

### Members of the current instantiation (¶4)

¶4 A name is a **member of the current instantiation** if: ¶4.1 when it is a qualified name, its [[g:lookup-context|lookup context]] is the current instantiation; and ¶4.2 lookup for it finds a member of a class that is the current instantiation.

```cpp run ok
template <class T> class A {
    static const int i = 5;
    int n1[i];                    // member of the current instantiation
    int n2[A::i];                 // likewise
    int n3[A<T>::i];              // likewise
    int f();
};

template <class T> int A<T>::f() {
    return i;                     // member of the current instantiation
}
int main() { }
```

A member of the current instantiation is a **dependent member of the current instantiation** if, when looked up, it refers to at least one member declaration in the current instantiation (including a *using-declarator* whose terminal name is dependent). The difference: a member found through a non-dependent base is a member of the current instantiation but not a dependent member; only members declared in the template's own definition are. This notion is used later in deciding type and value dependence, for example for static data members initialized outside the class.

### Dependent qualified names (¶5)

¶5 A qualified name ([[basic.lookup.qual]]) is dependent if:

- ¶5.1 it is a conversion function name whose target type is dependent;
- ¶5.2 its lookup context is dependent and is not the current instantiation;
- ¶5.3 its lookup context is the current instantiation and it is `operator=`;
- ¶5.4 its lookup context is the current instantiation, the current instantiation has at least one dependent base class, and qualified name lookup finds nothing.

¶5.2 is the main case: `T::x`, `Base<T>::x` and `t.x` (where `t` has a dependent type) are all dependent.

¶5.4 is a compromise. When the lookup context is the current instantiation, lookup happens first at the definition. If something is found, it's an ordinary name and can be checked early. If nothing is found but there are dependent bases, it might come from a dependent base, so it is deferred. If nothing is found and there are no dependent bases, it can't possibly exist, and an error can be reported at the definition:

<div class="compare" markdown="1">

```cpp ok
template<class T>
struct S : T {
  void f() { S::nothing(); }
  // has a dependent base: deferred (¶5.4)
};
```

```cpp error
template<class T>
struct S2 {
  void f() { S2::nothing(); }
  // error: no dependent base
};
```

</div>

Member access works the same way. The `m` in `this->m` is a member-qualified name ([[basic.lookup.qual.general#2]]), whose lookup context is the type of `*this`, the current instantiation. So in a class template without dependent bases, `this->undeclared()` is also reported at the definition, which is what Clang 23 does.

Example 4 shows a detail of ¶5.2:

```cpp error
struct A {
    using B = int;
    A f();
};
struct C : A {};
template<class T>
void g(T t) {
    decltype(t.A::f())::B i;      // error: typename needed for B to be treated as a type
}
template void g(C);               // even though A here is ::A
```

The type of `t.A::f()` depends on `T`, and `decltype` of a type-dependent expression gives a dependent type (¶10.13). The lookup context of `B` is dependent, so by ¶5.2 it is a dependent name. Block scope isn't a type-only context, so `typename` is required.

### Looking up again at instantiation (¶6)

```cpp run ok
struct A { int m; };
struct B { int m; };

template<typename T>
struct C : A, T {
    int f() { return this->m; }   // finds A::m at the definition
    int g() { return m; }         // finds A::m at the definition
};

template int C<B>::g();           // OK
// template int C<B>::f();        // error: at instantiation finds A::m and B::m
int main() { }
```

¶6 If a qualified name in an instantiated specialization refers to a member of the current instantiation, the name is looked up again in the instantiation context. If the result differs from that in the definition context, the lookup is ambiguous.

`this->m` is a qualified name; at the definition only the non-dependent base is visible, and `A::m` is found. When `C<B>` is instantiated, it is looked up again, the dependent base `B` now joins in, and both `A::m` and `B::m` are found, a different result from the definition, so it is ambiguous. Clang 23 reports that member `m` was found in multiple base classes.

The unqualified `m` is bound to `A::m` at the definition and doesn't change afterwards. The step in [[expr.prim.id.general#2]] that rewrites `m` as `(*this).m` isn't performed in the template definition context, so it doesn't count as referring to a member of the current instantiation with a qualified name, and it isn't looked up again.

This rule ensures that the meaning seen at the definition is the same as at instantiation: at instantiation the view is wider, and if the wider view would change the result, an error is preferred over silently switching to a different member.

### Dependent initializers and placeholder types (¶7–¶9)

¶7 An initializer is dependent if any of its constituent expressions ([[intro.execution]]) is type-dependent. A placeholder type (`auto`, `decltype(auto)`, [[dcl.spec.auto.general]]) whose type is deduced from a dependent initializer is also dependent.

¶8 A placeholder for class template argument deduction ([[dcl.type.class.deduct]]) is dependent if: ¶8.1 its initializer is dependent; ¶8.2 it refers to a type template template parameter; or ¶8.3 it refers to a member alias template of the current instantiation whose type is dependent after deduction and substitution.

```cpp run ok
template<class T, class V>
struct S { S(T) { } };

template<class U>
struct A {
    template<class T> using X = S<T, U>;
    template<class T> using Y = S<T, int>;
    void f() {
        delete new X(1);          // dependent: deduces S<int, U>
        delete new Y(1);          // not dependent: deduces S<int, int>
    }
};
template struct A<char>;
int main() { }
```

The argument `1` of `X(1)` isn't dependent, but the deduced result `S<int, U>` depends on the outer `U` (¶8.3). `Y(1)` can be fully deduced as `S<int, int>` at the definition.

### Dependent types (¶10–¶11)

¶10 The following types are [[g:dependent-type|dependent types]]:

| Paragraph | Content | Example |
|---|---|---|
| ¶10.1 | a template parameter | `T` |
| ¶10.2 | a type denoted by a dependent (qualified) name | `typename T::type` |
| ¶10.3 | a nested class or enumeration that is a direct member of the current instantiation | `struct Nested` in `A<T>` |
| ¶10.4 | a cv-qualified type whose cv-unqualified type is dependent | `const T` |
| ¶10.5 | a compound type constructed from a dependent type | `T*`, `T&`, `void(T)`, `int T::*` |
| ¶10.6 | an array whose element type is dependent or whose bound is value-dependent | `int[N]`, `T[3]` |
| ¶10.7 | a function type whose parameters include a function parameter pack | `void(Ts...)` |
| ¶10.8 | a function type whose exception specification is value-dependent | `void() noexcept(B)` |
| ¶10.9 | a dependent placeholder type | the type of `x` in `auto x = t;` |
| ¶10.10 | a dependent class template deduction placeholder | `X(1)` above |
| ¶10.11 | a *simple-template-id* whose template name is a template parameter or which has dependent template arguments | `TT<int>`, `vector<T>`, the injected-class-name without arguments |
| ¶10.12 | a pack index type | `Ts...[0]` |
| ¶10.13 | `decltype(e)` where `e` is type-dependent | `decltype(t + 1)` |
| ¶10.14 | a splice type whose splice specifier is dependent {{c++26}} | `typename [:R:]` |

¶10.3 says that a nested class of the current instantiation is a dependent type, even though its name isn't a dependent name and needs no `typename`. These two facts don't conflict: whether a name is dependent decides when it is looked up; whether a type is dependent decides whether the type varies with the template arguments. `A<int>::Nested` and `A<char>::Nested` are different types.

The footnote to ¶10.11 points out that the injected-class-name without an argument list is `X<T>`, so the current instantiation itself is a dependent type.

¶11 Note 3 says that a typedef doesn't introduce a new type, so a name referring to a member typedef of the current instantiation is dependent only if the type it refers to is dependent. In `template<class T> struct S { using I = int; I x; };`, `I` is not dependent.

!!! history "Old terminology: member of an unknown specialization"
    From C++11 to C++20 this subclause also defined a **member of an unknown specialization**, describing `T::x`, `Base<T>::x`, and names not found in the current instantiation that might come from a dependent base. C++23's [[P1787R6]] rewrote these rules in terms of dependent qualified names (¶5) and lookup contexts and removed the term. When you meet it in older material, it roughly corresponds to the names described by today's ¶5.2 and ¶5.4.

## Type-dependent expressions ([temp.dep.expr])

¶1 Except as described below, an expression is type-dependent if any subexpression is type-dependent.

¶2 `this` is type-dependent if the current class ([[expr.prim.this]]) is dependent. In a member function of a class template, `this` has type `X<T>*`, so `this->m` is a type-dependent member access. That's why `this->` turns a name into a dependent name; but as discussed above, when the lookup context is the current instantiation, lookup still happens once at the definition.

### Id-expressions (¶3)

¶3 An *id-expression* is type-dependent if it is a dependent *template-id* (other than a concept-id), or if its terminal name is one of the following:

| Paragraph | The entity found by name lookup |
|---|---|
| ¶3.1 | an entity declared with a dependent type (most common: `t` in `T t;`) |
| ¶3.2 | a constant template parameter whose type contains a placeholder type (`V` in `template<auto V>`) |
| ¶3.3 | a variable whose type contains a placeholder type and whose initializer is type-dependent (`auto x = t;`) |
| ¶3.4 | a member function of the current instantiation whose return type contains a placeholder type |
| ¶3.5 | a structured binding whose initializer is type-dependent |
| ¶3.6 | a structured binding pack {{c++26}} |
| ¶3.7 | an entity captured by copy in a lambda whose explicit object parameter has a dependent type |
| ¶3.8 | `__func__`, if some enclosing function is a template, a member of a class template, or a generic lambda |
| ¶3.9 | the result binding of a function whose return type is dependent (contract postconditions, [[dcl.contract.res]]) {{c++26}} |
| ¶3.10 | a conversion function name specifying a dependent type |
| ¶3.11 | a name introduced by an expansion statement whose type contains a placeholder type (the expansion statement is not iterating, or its expansion initializer is type-dependent) {{c++26}} |
| ¶3.12 | a name that is dependent |

In addition, an id-expression naming a dependent member of the current instantiation that is a static data member of array type of unknown bound is type-dependent ([[temp.static]]), because the out-of-class definition may supply the bound.

The type of `__func__` is `const char[N]`, where `N` depends on the length of the function-name string. The content of this string is implementation-defined, and an implementation may make `__func__` differ between specializations (for example by including the template arguments), so its type is unknown before instantiation.

Example 1 for ¶3.6 (C++26 structured binding packs):

```cpp run ok
#include <cstdio>
struct C { };
void g(...) { std::puts("#1 g(...)"); }

template <typename T>
void f() {
    C arr[1];
    auto [...e] = arr;      // e is a structured binding pack
    g(e...);                // dependent call: ADL finds #2 at instantiation
}

void g(C) { std::puts("#2 g(C)"); }

int main() { f<int>(); }    // prints #2 g(C)
```

Nothing in `f` depends on `T`, yet `e` is specified to be type-dependent: the number of elements of a structured binding pack isn't known until instantiation. So `g(e...)` is a dependent call (¶2.1), lookup of `g` is deferred to instantiation, and ADL finds the later-declared `g(C)` in the instantiation context.

### Forms that only look at the written type

The end of ¶3 specifies that the following forms are type-dependent only if the written type is dependent, even if the operand is type-dependent:

- functional casts `T(args)`, `T{args}`;
- `new T(...)`;
- the four named casts, `static_cast<type-id>(e)` and so on;
- C-style casts `(type)e`.

The type of these expressions is the written type (or a pointer to it), independent of the operand. `static_cast<int>(t)` is not type-dependent; its type is simply `int`, though it may be value-dependent (see below).

### Forms that are never type-dependent (¶4)

¶4 The following forms can never have a dependent type: literals, `sizeof`, `sizeof...`, `alignof`, `typeid`, `delete`, `throw`, `noexcept(e)`, *requires*-expressions, and {{c++26}} reflection expressions `^^x` (whose type is always `std::meta::info`).

```cpp run ok
#include <type_traits>
template<class T> void g(T t) {
    auto n = sizeof(t);           // n has type size_t, not dependent
    static_assert(std::is_same_v<decltype(n), decltype(sizeof 0)>);   // checkable at the definition
    int i = 0;
    auto a = i;                   // not dependent
    auto b = t;                   // type-dependent (¶3.3)
    (void)a; (void)b;
}
template void g(int);
int main() { }
```

### Member access and others (¶5–¶9)

¶5 A class member access expression is type-dependent if: ¶5.1 the terminal name of the member name is dependent; ¶5.2 its splice expression is type-dependent; or ¶5.3 the expression refers to a member of the current instantiation and the type of that member is dependent.

Note 2 explains the effect. The type of `x.y` is usually the type of member `y` in the class of `x`. If the type of `x` is dependent and is not the current instantiation, the type of `y` is always dependent. Conversely, for a member declared `int n;` in the current instantiation, `this->n` is not type-dependent; it's known to be `int` at the definition.

¶6 A braced list is type-dependent if any element is type-dependent or is a pack expansion. ¶7 A fold expression is always type-dependent. ¶8 A pack index expression is type-dependent if its *id-expression* is type-dependent. ¶9 {{c++26}} A splice expression is type-dependent if its splice specifier is dependent.

## Value-dependent expressions ([temp.dep.constexpr])

Value dependence only matters where a constant expression is required: array bounds, template arguments, `static_assert`, the condition of `if constexpr`, `noexcept(...)`, bit-field widths, `alignas`, and so on. ¶1 In those places, except as described below, an expression is value-dependent if any subexpression is value-dependent.

### Id-expressions (¶2)

¶2 An *id-expression* is value-dependent if:

- ¶2.1 it is a concept-id and the concept name or some argument is dependent;
- ¶2.2 it is type-dependent (if even the type is uncertain, so is the value);
- ¶2.3 it is the name of a constant template parameter;
- ¶2.4 {{c++26}} it is a name introduced by an expansion statement;
- ¶2.5 it names a static data member that is a dependent member of the current instantiation and isn't initialized in the class;
- ¶2.6 it names a static member function that is a dependent member of the current instantiation;
- ¶2.7 it names a potentially-constant variable ([[expr.const.init]]) whose initializer is value-dependent.

¶2.5 means: `static const int n = 3;` initialized in the class has a value known at the definition; a static member initialized outside the class may have different definitions for different specializations (static members can be explicitly specialized), so it is value-dependent:

```cpp run ok
template<class T> struct S {
    static const int n = 3;       // initialized in class: not value-dependent
    static const int m;           // initialized out of class: value-dependent (¶2.5)
    void f() {
        int a[n];                 // n == 3 at the definition
        int b[m];                 // deferred to instantiation
        (void)a; (void)b;
    }
};
template<class T> const int S<T>::m = 4;
template struct S<int>;
int main() { }
```

The end of ¶2 also specifies that `sizeof`, `alignof` and `typeid` are value-dependent if the operand expression is type-dependent or the operand type is dependent. So `sizeof(t)` is not type-dependent but value-dependent, the classic example of a known type with an unknown value.

### Other forms (¶3–¶6)

- ¶3 Functional casts, named casts and C-style casts are value-dependent if the written type is dependent or the operand is value-dependent. When `N` is a constant template parameter, `static_cast<int>(N)` is value-dependent but not type-dependent.
- ¶4 `sizeof...(pack)` and fold expressions are always value-dependent.
- ¶5 `noexcept(e)` is value-dependent if `e` involves a template parameter. "Involves" is broader than type-dependent: as soon as a template parameter appears in `e`, whether the result is `true` may vary between specializations.
- ¶6 `&` applied to a qualified name that names a dependent member of the current instantiation is value-dependent, for example `&S<T>::sm`. In addition, if the operand of `&` evaluated as a core constant expression succeeds and the result refers to a templated entity that is an object with static or thread storage duration or a member function, the expression is value-dependent too. Each specialization has its own such entity, so the address differs between specializations.

### Reflection and splicing (¶7–¶8) {{c++26}}

¶7 A reflection expression is value-dependent if: ¶7.1 it has the form `^^name` and lookup finds a declaration that inhabits a scope corresponding to a templated entity, or the name is a dependent qualified name, a dependent namespace name, or the name of a template parameter; ¶7.2 it has the form `^^type-id` and the type is dependent; ¶7.3 it has the form `^^id-expression` and that is value-dependent.

The type of `^^x` is always `std::meta::info`, so it is never type-dependent (¶4). But which entity it reflects may depend on the template arguments, which is value dependence. The first case in ¶7.1 means that reflecting, inside a template, an entity declared inside the template (one per specialization) is also value-dependent.

¶8 A splice expression is value-dependent if its splice specifier is dependent.

## Dependent splice specifiers ([temp.dep.splice]) {{c++26}}

¶1 A splice specifier `[: e :]` is dependent if the constant expression `e` is value-dependent. `[: e :]<args>` is dependent if the splice specifier is dependent or any template argument is dependent. A splice used as a nested-name-specifier is dependent if its splice specifier is dependent.

A dependent splice specifier is in the same position as a dependent nested-name-specifier: what it refers to isn't known at the definition, and a following member name that denotes a template or type needs `template` or `typename`, unless it's in a type-only context ([[temp.res#4]]). The following two examples come from the draft; Clang 23 doesn't support reflection (`^^` and `[: :]`), so they haven't been verified by compilation.

```cpp
template<auto T, auto NS>
void fn() {
    using a = [:T:]<1>;                                   // dependent; an alias-declaration is a type-only context
    static_assert([:NS:]::template TCls<1>::v == a::v);   // [:NS:] is dependent: template required
}

namespace N {
    template <auto V> struct TCls { static constexpr int v = V; };
}

int main() {
    fn<^^N::TCls, ^^N>();
}
```

¶3 Example 2 shows a dependent splice deferring checks to instantiation:

```cpp
template<template<class> class X>
struct S {
    [:^^X:]<int, float> m;        // ^^X reflects a template parameter, value-dependent
};

template<class> struct V1 {};
template<class, class = int> struct V2 {};

S<V1> s1;                         // error: too many arguments for V1<int, float>
S<V2> s2;                         // OK
```

Written directly as `X<int, float>`, `X` is a template template parameter that takes one type argument, and the definition would be rejected for too many arguments. Going through `[:^^X:]` turns it into a dependent splice, and the argument count check is deferred to instantiation. With `X = V2`, the second parameter has a default argument, and it's perfectly valid.

## Dependent namespaces ([temp.dep.namespace]) {{c++26}}

¶1 A namespace alias is dependent if, in its definition `namespace A = ...;`, the right-hand side is a dependent qualified name or a dependent splice specifier. A *namespace-name* naming a dependent namespace alias is also dependent.

```cpp
template<std::meta::info R>
int fn() {
    namespace Alias = [:R:];          // [:R:] is dependent, so Alias is dependent
    return typename Alias::T{};       // typename required
}

namespace NS { using T = int; }

int a = fn<^^NS>();
```

Before C++26, a namespace couldn't depend on template parameters, because there was no way to pass a namespace as a template argument. Reflection lets `std::meta::info` represent a namespace, so dependent namespaces appeared, and the rules for qualified names (¶5.2 of [[temp.dep.type#5]]) apply to them as well. This example hasn't been verified by compilation either.

## Dependent template arguments ([temp.dep.temp])

- ¶1 A type template argument is dependent if the type it specifies is dependent.
- ¶2 A constant template argument is dependent if its type is dependent or its constant expression is value-dependent.
- ¶3 In addition, if the corresponding constant template parameter is of reference or pointer type and the template argument refers to a member of the current instantiation or a member of a dependent type, the template argument is dependent.
- ¶4 A template argument that is a pack expansion is dependent.
- ¶5 A template template argument is dependent if it names a template parameter or its terminal name is dependent.

An example of ¶3:

```cpp run ok
template<int* P> struct Tag { };
template<class T> struct W {
    static int sm;
    Tag<&sm> t;           // &sm refers to a member of the current instantiation: dependent (¶3)
};
template<class T> int W<T>::sm = 0;
W<int> w;
int main() { }
```

`W<int>::sm` and `W<char>::sm` are different objects, so `Tag<&sm>` is a different type in different specializations and must count as dependent.

The dependence of template arguments propagates to the *simple-template-id* through ¶10.11 of [[temp.dep.type#10]]: if any argument is dependent, the whole specialization is a dependent type.

!!! impl "How compilers represent dependence"
    - Clang records a set of dependence bits on syntax tree nodes (type-dependent, value-dependent, instantiation-dependent, contains an unexpanded pack, etc.) that correspond directly to the definitions in this subclause. Dependent types have dedicated nodes; for example, `typename T::x`, a template parameter `T` and the injected-class-name each have their own node type, and instantiation walks these nodes to substitute.
    - The current instantiation is what lets Clang report `no member named ... in 'X<T>'` at the definition: it performs real member lookup in the current instantiation at the definition and diagnoses directly when there are no dependent bases.
    - GCC has corresponding predicates for whether an expression is type-dependent or value-dependent, conceptually one-to-one with the standard's terms.

## Common misconceptions

!!! pitfall "Value-dependent means type-dependent"
    `sizeof(t)`, `static_cast<int>(N)` and `noexcept(T())` are all value-dependent but not type-dependent. Types built from them (like `int[sizeof(t)]`) are dependent types, but the type of the expression itself is known at the definition and can take part in overload resolution there.

!!! pitfall "If typename isn't needed, it has nothing to do with T"
    `A<T>::Nested` doesn't need `typename` because the name can be found at the definition; but it is a dependent type (¶10.3) and is a different class in each specialization.

!!! pitfall "this-> defers all checking"
    The lookup context of `this->m` is the current instantiation. When the current instantiation has no dependent bases and `m` doesn't exist, Clang and GCC report an error at the definition. If `m` was found in a non-dependent base at the definition, it is looked up again at instantiation (¶6), and if a dependent base brings in a member with the same name, the lookup is ambiguous.

## Questions

!!! question "Question 1"
    ```cpp
    template<int N> struct A {
        static constexpr int k = N;
        static constexpr int k2 = (N);
        A<k>* p;
        A<k2>* q;
    };
    ```
    Are `p` and `q` pointers to the current instantiation? What practical difference does it make?

<details markdown="1">
<summary>Answer</summary>

`k` has the same type as `N` (both `int`; the const from `constexpr` doesn't count), and its initializer is the single identifier `N`, so `k` is equivalent to `N` and `A<k>` is the current instantiation ([[temp.dep.type#2]]). The initializer of `k2` is parenthesized, so by Note 1 it is no longer equivalent, and `A<k2>` is not the current instantiation, even though in every instantiation it's the same type as `A<N>`.

The practical difference: names accessed through `A<k>::` are members of the current instantiation, can be looked up at the definition, don't need `typename`, and misspellings can be reported early. Names accessed through `A<k2>::` are dependent names (¶5.2); type members need `typename`, and errors are deferred to instantiation.

Clang 23 doesn't implement the equivalent-variable rule; it requires `typename` for `A<k>::type` in a function body too, as noted in the implementation box above.
</details>

!!! question "Question 2"
    In `f` of `template<class T> struct S { int n; void f(); };`, is `this->n` type-dependent? Is `decltype(this->n)` a dependent type?

<details markdown="1">
<summary>Answer</summary>

Neither. `this` is type-dependent ([[temp.dep.expr#2]]), but whether a member access is type-dependent is specified separately by [[temp.dep.expr#5]]. The terminal name `n` is not dependent: the lookup context is the current instantiation, the member is found at the definition, and neither ¶5.2 nor ¶5.4 holds. The expression refers to the member `n` of the current instantiation, whose type `int` is not dependent. So `this->n` is not type-dependent, and `decltype(this->n)` is not a dependent type either (¶10.13 requires the expression to be type-dependent); it is simply `int`.
</details>

!!! question "Question 3"
    Why are fold expressions specified as type-dependent unconditionally, rather than only when the pack elements' types are dependent?

<details markdown="1">
<summary>Answer</summary>

A fold expression necessarily contains an unexpanded pack, whose length isn't known until instantiation. Even if the element types are all known (say an `int...` constant parameter pack), with an empty pack the result depends on the operator: `&&` gives `true`, `||` gives `false`, `,` gives `void()`, and other operators are ill-formed; with a non-empty pack the result type depends on the expanded expressions and operator overloading. The result type can't be determined at the definition, so the standard simply specifies it as type-dependent ([[temp.dep.expr#7]]). Likewise, `sizeof...` and fold expressions are always value-dependent ([[temp.dep.constexpr#4]]).
</details>

## Summary

| Concept | Source | Key point |
|---|---|---|
| Dependent call | [temp.dep.general] ¶2 | unqualified name plus type-dependent arguments, pack expansions or dependent template arguments; ADL added at instantiation |
| Current instantiation | [temp.dep.type] ¶1–¶2 | how a class template refers to itself from inside: injected-class-name, `X<T>`, equivalent arguments |
| Dependent base class | ¶3 | dependent and not the current instantiation; not searched at the definition |
| (Dependent) member of the current instantiation | ¶4 | members that can be looked up at the definition |
| Dependent qualified name | ¶5 | lookup context dependent and not the current instantiation; or the current instantiation has dependent bases and nothing is found |
| Looked up again at instantiation | ¶6 | qualified name referring to a member of the current instantiation; ambiguous if the two results differ |
| Dependent type | ¶10 | 14 cases, including C++26 pack index types and splice types |
| Type-dependent | [temp.dep.expr] | propagates from subexpressions; casts only look at the target type; `sizeof` etc. are never type-dependent |
| Value-dependent | [temp.dep.constexpr] | constant parameters, static members initialized out of class, `sizeof` with dependent operands, `sizeof...`, folds, reflection |
| Dependent splices and namespaces | [temp.dep.splice], [temp.dep.namespace] | new sources of dependence from C++26 reflection |
| Dependent template arguments | [temp.dep.temp] | dependent type, value-dependent, refers to a member of the current instantiation, pack expansion, template parameter |
