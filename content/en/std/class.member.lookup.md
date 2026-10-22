---
title: Member name lookup
summary: "To find a name in a class scope, look in the class itself first; if nothing is found, merge the results from each base class in turn. This one algorithm explains name hiding, dominance through virtual bases, ambiguity under multiple inheritance, and why static members are never ambiguous."
updated: 2026-10-19
---

!!! tldr
    - To find a name in a class, look at the class itself first. If the class has any declaration of that name, same-named members of base classes are not considered at all, whatever their parameters; use `using Base::f;` to bring the base-class overloads back.
    - If the class itself has none, look in each direct base class separately and merge the results: when the subobject found on one side is a base class subobject of one found on the other, it is dominated and discarded; otherwise, if the two sides found different declarations, the result is ambiguous.
    - Virtual inheritance lets one base class subobject be shared by several paths, so a declaration in a virtual base can be dominated by a declaration on another path; non-virtual inheritance can't do this.
    - An unambiguous lookup can still lead to an ambiguous use: static members, types and enumerators are fine when found along several paths, but a non-static member also requires the object to be unambiguously convertible to that base class.
    - In a class template, base classes that depend on a template parameter take no part in lookup, which is why you write `this->f()`.

Finding a name in a namespace only requires looking at what is bound in that scope ([[g:single-search]], [[basic.lookup#3]]). Classes are different: a class also inherits the members of its base classes, and there may be several bases, a base may occur more than once (a non-virtual diamond), or be shared (virtual inheritance). The **search** defined in this subclause is the algorithm that finds a name in a class scope by following base classes.

Member access `obj.m`, qualified names `C::m`, unqualified names in member function bodies, and member candidates for overloaded operators are all looked up with this algorithm. Before reading on, you need the notion of base class subobjects ([[class.mi]]): every occurrence of a non-virtual base is a separate subobject, while a virtual base has a single shared subobject in the whole object.

## A derived-class name hides same-named base members

```cpp run error
struct Base {
    void f(int);
    void f(double);
};
struct Der : Base {
    void f(const char*);     // hides both of Base's f
};
void t(Der& d) {
    d.Base::f(1);            // OK: the qualified name is looked up directly in Base
    d.f(1);                  // error: only Der::f(const char*) is found
}
```

¶1 A **search** for a name M in a scope X from a program point P: if X is not the scope of a class, it is a single search; if X is the scope of a class or class template T, the result is computed by the steps below. Note 1 points out that the result differs from a single search in only two cases: M is a conversion function name (paragraph 7), or the single search found nothing (in which case the base classes are searched).

In other words, as soon as the derived class has one declaration of the name, lookup stops there and same-named base class members do not become candidates. `d.f(1)` sees only `Der::f(const char*)`, and `int` cannot be converted to `const char*`, so it is an error.

To make the base-class overloads take part, bring them into the derived class with a using-declaration. The using-declaration is bound in the scope of `Der`; when the search finds it, it is replaced by the declarations of `Base::f` ([[basic.lookup#3]]). A base-class function whose parameters are the same as those of a function in the derived class is not brought in, and the derived-class version remains ([[namespace.udecl#11]]):

```cpp run ok
struct Base {
    void f(int);
    void f(double);
    void g(int);
};
struct Der : Base {
    using Base::f;           // brings in Base::f(int), Base::f(double)
    using Base::g;           // Base::g(int) has the same parameters as Der::g(int): not brought in
    void f(const char*);
    void g(int);
};
void t(Der& d) {
    d.f(1);                  // Base::f(int)
    d.f("x");                // Der::f(const char*)
    d.g(1);                  // Der::g(int)
}
```

!!! note "Hiding versus overriding"
    Hiding happens at the level of lookup; virtual function overriding happens at the level of call dispatch. The two are unrelated. If `Base::h` is virtual and `Der::h` has the same signature, `Der::h` both hides and overrides `Base::h`: looking up `h` through `Der&` finds only `Der::h`, and calling `h` through `Base&` dispatches to `Der::h`.

## Lookup sets (¶2–¶3)

¶2 The **lookup set** ([[g:lookup-set]]) for a name N in a class C, written S(N,C), consists of two parts:

- the **declaration set**: the member declarations named N that were found;
- the **subobject set**: the subobjects in which those declarations were found (possibly via using-declarations).

In the declaration set, type declarations, including injected-class-names (the binding of a class's name in its own class), are replaced by the types they designate. The same type may be found along different paths; for example, two base classes both derive from `A` and so both carry the injected-class-name `A`. After replacement by the type, the declaration sets on both sides are equal, and merging does not make the result ambiguous:

```cpp run ok
struct A {};
struct B : A {};
struct C : A {};
struct D : B, C {
    A* p;    // OK: along both the B path and the C path, the type A is found
};
```

¶3 The first step looks only at C itself: a single search for N in the scope of C. If P is in a [[g:complete-class-context]] of C (member function bodies, default arguments, default member initializers, etc., [[class.mem#10]]), the search is done from the end of the class definition and sees all members; otherwise it is done from P and sees only members declared before P.

If the result is non-empty, the subobject set is `{C}` and the computation ends. This is the name hiding of the previous section.

## Merging the results from base classes (¶4–¶5)

¶4 If C itself has no member named N, S(N,C) is first set to empty; then S(N,Bᵢ) is computed recursively for each direct base class subobject Bᵢ and merged into S(N,C) in turn. Only non-dependent base classes are considered ([[temp.dep.type]]).

Note 2 adds two points. While C is incomplete (P is inside the class definition, not in a complete-class context), only the base classes whose base-specifiers appear before P are considered. An instantiated class has no dependent base classes.

¶5 Merging S(N,Bᵢ) into the current S(N,C):

| Case | Result |
|---|---|
| ¶5.1 S(N,Bᵢ) is empty, or each of its subobjects is a base class subobject of some subobject in S(N,C) | S(N,C) is unchanged: the result from Bᵢ is dominated |
| ¶5.1 Conversely, S(N,C) is empty, or each of its subobjects is a base class subobject of some subobject in S(N,Bᵢ) | S(N,C) is replaced by S(N,Bᵢ): the previous result is dominated |
| ¶5.2 Otherwise, the two declaration sets differ | ambiguous: the declaration set is marked invalid and the subobject sets are united; in later merges, an invalid declaration set is considered different from any other |
| ¶5.3 Otherwise (the declaration sets are equal) | the declaration set is unchanged and the subobject sets are united |

"Is a base class subobject of some subobject" compares subobjects, not types. In a non-virtual diamond, the A in B and the A in C are two subobjects, neither a base of the other; a virtual base V has a single subobject, which is a base of every subobject that virtually inherits V. Dominance under virtual inheritance comes from exactly this.

## The result of lookup (¶6)

¶6 The result of the search is the declaration set of S(M,T). If it is invalid, the program is ill-formed; this is member ambiguity.

If it differs from the result of a search for M in a complete-class context of T, the program is ill-formed, no diagnostic required ({{ifndr}}):

```cpp ifndr
typedef int I;
struct S {
    I x;                 // I is not found in S here; the search goes outward and finds ::I (int)
    typedef double I;    // a search in a complete-class context of S would find S::I (double)
};
```

This rule ensures that the meaning of class members does not depend on the order of members: compilers can process a class definition top to bottom, and programmers cannot write a class whose meaning changes when members are reordered. GCC reports that `I` changes meaning for the code above, Clang 23 gives no diagnostic, and both conform.

### Example 1 in the standard

```cpp run ok
struct A { int x; };                    // S(x,A) = { {A::x}, {A} }
struct B { float x; };                  // S(x,B) = { {B::x}, {B} }
struct C: public A, public B { };       // S(x,C) = { invalid, {A in C, B in C} }
struct D: public virtual C { };         // S(x,D) = S(x,C)
struct E: public virtual C { char x; }; // S(x,E) = { {E::x}, {E} }
struct F: public D, public E { };       // S(x,F) = S(x,E)
int main() {
    F f;
    f.x = 0;                            // OK: finds E::x
}
```

Computing S(x,F):

1. F itself has no `x`, so its direct bases D and E are merged.
2. S(x,D) is merged into the empty set; by the second case of item 5.1 it is simply copied, giving {invalid, {A in C, B in C}}.
3. S(x,E) = {{E::x}, {E}} is merged. C is a virtual base, so F has only one C subobject, which is a base class subobject of both D and E; hence the A and B in C are both base class subobjects of E. By the second case of item 5.1, S(x,F) is replaced by S(x,E).

So the invalid state can be eliminated in later merges, as long as a declaration that dominates it appears later. Remove `virtual`, and D and E each have their own C; step 3 no longer holds and the result is ambiguous.

## Virtual bases and dominance (¶9)

¶9 Note 5 explains that when virtual base classes are used, a hidden declaration can be reached along a path that does not go through the hiding declaration; this is not an ambiguity. The same structure with non-virtual bases is ambiguous, because no single declaration hides all the others. Example 3 in the standard:

```cpp run error
struct V { int f();  int x; };
struct W { int g();  int y; };
struct B : virtual V, W {
    int f();  int x;
    int g();  int y;
};
struct C : virtual V, W { };
struct D : B, C { void glorp(); };

void D::glorp() {
    x++;              // OK: B::x hides V::x
    f();              // OK: B::f() hides V::f()
    y++;              // error: B::y and W::y of the W in C
    g();              // error: B::g() and W::g() of the W in C
}
```

The object structure (Figure 1 in the standard): V is a virtual base, so there is one; W is a non-virtual base, so B and C each have one:

```text
   W₁   V   W₂
    \  / \  /
     B     C
      \   /
        D
```

S(x,D): S(x,B) = {{B::x}, {B}}, because B declares `x` itself; C has no `x` of its own and neither does W, so S(x,C) = {{V::x}, {V}}. When merging, is V a base class subobject of B? Yes: the single V in D is a base of both B and C. By the first case of item 5.1, S(x,D) stays {{B::x}, {B}}.

S(y,D): S(y,B) = {{B::y}, {B}} and S(y,C) = {{W::y}, {W₂}}. W₂ is not a base class subobject of B (B has its own W₁), B is not a base class subobject of W₂, and the declaration sets differ, so the result is invalid, that is, ambiguous.

!!! tip "How to think about dominance"
    "The nearest declaration wins" is not accurate. The accurate statement is: if the subobject containing one declaration has the subobject containing another declaration as a base class subobject, the former dominates the latter. Virtual inheritance lets the same subobject be shared by several paths, which is what allows dominance to hold across paths; under non-virtual inheritance the subobjects on different paths are independent and cannot dominate each other.

## Unambiguous lookup, possibly ambiguous use (¶8, ¶10, ¶11)

```cpp run error
struct V { int v; };
struct A {
    int a;
    static int s;
    enum { e };
    using T = int;
    static void sf();
};
struct B : A, virtual V { };
struct C : A, virtual V { };
struct D : B, C { };

void f(D* pd) {
    pd->v++;          // OK: there is only one V subobject
    pd->s++;          // OK: static member
    int i = pd->e;    // OK: enumerator
    D::T k = i;       // OK: nested type
    D::sf();          // OK: static member function
    (void)k;
    pd->a++;          // error: D has two A
}
```

¶8 Note 4 says that even if an object has more than one base class subobject of type T, the static members, nested types and enumerators defined in T can be found unambiguously; two base class subobjects share the non-static member subobjects of their common virtual base classes.

In terms of the merge algorithm: `A::s` found along two paths gives the declaration set {A::s} both times, so by item 5.3 only the subobject sets are merged, and the lookup itself is not ambiguous. The same goes for `A::a`: lookup again yields {A::a}. So why is `pd->a` an error? Because using a non-static member also requires converting the object expression to `A`, and D has two `A`. That is an error specified by [[expr.ref]], not a lookup error.

¶10 When a pointer to or object of a derived class is explicitly or implicitly converted to a pointer or reference to a base class, the result must unambiguously refer to a unique object representing the base class:

```cpp run error
struct V { };
struct A { };
struct B : A, virtual V { };
struct C : A, virtual V { };
struct D : B, C { };

void g() {
    D d;
    B* pb = &d;       // OK
    A* pa = &d;       // error: the A in B or the A in C?
    A* pa2 = pb;      // OK: first to B, then to its only A
    V* pv = &d;       // OK: there is only one V
    (void)pa2; (void)pv;
}
```

This rule sits in member lookup because it says the same thing as paragraphs 8 and 11: lookup only decides which declaration is found; which subobject the member is taken from is decided by this conversion.

¶11 Note 6 and Example 5 show the distinction in one place:

```cpp
struct B1 {
    void f();
    static void f(int);
    int i;
};
struct B2 {
    void f(double);
};
struct I1: B1 { };
struct I2: B1 { };

struct D: I1, I2, B2 {
    using B1::f;
    using B2::f;
    void g() {
        f();                        // ambiguous: converting this to B1* is ambiguous
        f(0);                       // unambiguous: the static B1::f(int) needs no object
        f(0.0);                     // unambiguous: there is only one B2
        int B1::* mpB1 = &D::i;     // unambiguous: &D::i has type int B1::*
        int D::* mpD = &D::i;       // ambiguous: converting int B1::* to int D::* is ambiguous
    }
};
```

- Both using-declarations are bound in D, so the search of D finds them and replaces them with {B1::f(), B1::f(int), B2::f(double)}. D's own result is non-empty, the base classes are not merged, and the lookup is not ambiguous.
- `f()` selects the non-static `B1::f()`, which requires converting `*this` to `B1`; D has two B1, so the conversion is ambiguous.
- `f(0)` selects the static member and needs no object.
- `&D::i` has type `int B1::*`, because `i` is a member of B1 ([[expr.unary.op]]), so the first of those two lines needs no conversion. The second has to convert `int B1::*` to `int D::*` ([[conv.mem]]), which requires B1 to be an unambiguous base of D, so it fails.

!!! impl "Where Clang deviates"
    Clang 23 rejects `int B1::* mpB1 = &D::i;`, reporting non-static member 'i' found in multiple base-class subobjects of type 'B1'. Example 5 in the standard marks this line unambiguous; Clang checks subobject uniqueness too early when forming the pointer to member. Clang agrees with the standard on every other line, which is why this example carries no verdict.

!!! lawyer "Wording of the diagnostic"
    For `pd->a`, Clang reports non-static member 'a' found in multiple base-class subobjects of type 'A', which sounds like a lookup problem. Per the standard, lookup succeeded; what fails is the later conversion of the object expression to `A`. The distinction matters in practice: the same name as a static member would be valid.

## Conversion function templates (¶7)

```cpp run ok
struct A {
    operator int();
    template<class T> operator T*();
};
struct B : A {
    operator double();      // its name differs from those of the base conversion functions, so it does not hide them
};
void t(B b) {
    int i = b;              // A::operator int
    int* p = b;             // A::operator T*, T = int
    double d = b;           // B::operator double
    (void)i; (void)p; (void)d;
}
```

Conversion function names are compared by type ([[basic.pre#4]]): `operator double` and `operator int` are different names, so `B::operator double` does not hide `A::operator int`. But it follows that `operator int*` and the template `template<class T> operator T*` also have different names, and a single search for `operator int*` does not find the template.

¶7 So when M is a non-dependent conversion function name, the member conversion function templates of T are also considered: for each such template F, the function template declarations that correspond to F ([[basic.scope.scope#4]]) are treated as having the same name, a lookup set is built, and its declaration set (which shall not be invalid) is added to the result. Templates that cannot convert to the target type are eliminated later by overload resolution and template argument deduction ([[temp.over]]).

## More examples

### Diamond inheritance

```cpp run error
struct A { int x; void f(); static int s; };
struct B : A { };
struct C : A { };
struct D : B, C { };          // non-virtual diamond: two A
struct VB : virtual A { };
struct VC : virtual A { int x; };
struct VD : VB, VC { };       // virtual diamond: one A; VC::x dominates A::x

void t(D& d, VD& vd) {
    d.s = 1;                  // OK: static member
    d.B::x = 1;               // OK: B contains only one A
    vd.x = 1;                 // OK: VC::x dominates A::x
    vd.f();                   // OK: there is only one A
    d.x = 1;                  // error: two A subobjects
}
```

`d.B::x`: the qualified name `B::x` is looked up in B and yields `A::x`. [[expr.ref]] then checks that `A`, the class `x` belongs to, is an unambiguous base of `B`, and converts `d` to `B`; neither step is ambiguous.

### Same-named members of different kinds

If a data member of one base has the same name as a member function of another base, the declaration sets again differ, and by item 5.2 the result is ambiguous. Choose one with a using-declaration in the derived class, and lookup ends in the derived class:

```cpp run error
struct B1 { int x; };
struct B2 { void x(); };
struct D : B1, B2 { };
struct E : B1, B2 { using B1::x; };

void t(D d, E e) {
    e.x = 1;          // OK: the using-declaration in E, i.e. B1::x
    d.x;              // error: {B1::x} and {B2::x} differ: ambiguous
}
```

### Private inheritance and injected-class-names

Injected-class-names also take part in member lookup, which leads to a common surprise:

```cpp run error
struct P { };
struct Q : private P { };
struct R : Q {
    ::P* good;        // OK: looked up in the global namespace
    P* bad;           // error: finds the injected-class-name inherited through a private base
};
```

Looking up `P` in `R`: R has none of its own, so base Q is merged, and the injected-class-name `P` is found in Q's base P. The lookup itself is fine, but the access check finds that the name was inherited through Q's private base and is inaccessible in R. Writing `::P` fixes it.

### Dependent base classes

```cpp run error
template<class T> struct Base { void f(); };
template<class T> struct Der : Base<T> {
    void g() {
        this->f();           // OK: dependent member access, looked up at instantiation
        Der::f();            // OK: qualified name, lookup deferred to instantiation
        f();                 // error: unqualified lookup does not look into the dependent base Base<T>
    }
};
```

¶4 merges only non-dependent base classes. `Base<T>` depends on `T`; in the template definition its members are simply not known (`Base` may have specializations), so lookup does not look into it. `this->f()` and `Der::f()` make the name dependent, and lookup is deferred until after instantiation.

## Implementation view

!!! impl "What compilers do"
    - Clang uses `CXXRecordDecl::lookupInBases` and `CXXBasePaths` to record what was found along which paths, the equivalent of the subobject set of a lookup set. Its diagnostics distinguish two situations: same-named members found in base classes of different types (the ambiguity of item 5.2, member found in multiple base classes of different types), and a non-static member found in several base class subobjects of the same type (the ambiguous use described in paragraph 11).
    - Lookup happens entirely at compile time and does not affect object layout, but it decides which subobject a member is taken from. Offsets of non-virtual bases are compile-time constants; offsets of virtual bases are obtained at run time from the vtable.

## History

!!! history
    - C++98 described lookup under multiple inheritance in prose, in terms of dominance and the like, and its interaction with static members, types and using-declarations had many unclear points.
    - C++11 switched to the merge algorithm on lookup sets, the skeleton of today's paragraphs 2–5.
    - C++23 ([[P1787R6]]) defined it as the search in a class scope, as part of all lookup; the old [basic.scope.class] rule that reordering members must not change meaning was rewritten as the no-diagnostic-required rule of paragraph 6.

## Common misconceptions

!!! pitfall "Overloading works across base and derived classes"
    Once a derived class declares an `f`, none of the base class's `f` are visible, even if their parameters are completely different. Clang's `-Woverloaded-virtual` warns about one typical case: a virtual function in the derived class hides other virtual overloads of the same name in the base class.

!!! pitfall "A using-declaration makes the base version win over the derived version"
    A function brought in by `using Base::f;` is not brought in if its parameters are the same as a function in the derived class ([[namespace.udecl#11]]): no conflict, no ambiguity, and the derived-class version wins.

!!! pitfall "In a template you can call base members directly"
    Members of dependent base classes are outside the reach of unqualified lookup; write `this->f()`. MSVC finds them when not in `/permissive-` mode, and such code fails to compile on other compilers.

## Questions

!!! question "Question 1"
    ```cpp
    struct A { void f(); };
    struct B : virtual A { void f(); };
    struct C : virtual A { };
    struct D : B, C { };
    struct E : D, A { };   // plus a non-virtual A
    ```
    What are the lookup results for `D{}.f()` and `E{}.f()`?

<details markdown="1">
<summary>Answer</summary>

S(f,D): S(f,B) = {{B::f}, {B}} and S(f,C) = {{A::f}, {virtual base A}}. The virtual base A is a base class subobject of B, so it is dominated, and the result is {{B::f}, {B}}: `D{}.f()` calls `B::f`.

S(f,E): first S(f,D) = {{B::f}, {B}} is merged, then S(f,A) = {{A::f}, {non-virtual A}} of the non-virtual base A. This A is a direct base of E and a different subobject from the virtual base A in D; it is not a base class subobject of B, B is not a base class subobject of it, and the declaration sets differ, so the result is ambiguous and `E{}.f()` is ill-formed. Clang 23 reports member 'f' found in multiple base classes of different types, and warns that the direct base A is inaccessible due to ambiguity.
</details>

!!! question "Question 2"
    Why does paragraph 2 require type declarations to be replaced by the types they designate? Give an example that would wrongly be judged ambiguous without the replacement.

<details markdown="1">
<summary>Answer</summary>

For example, B has `using T = int;`, C has `typedef int T;`, and D derives from B and C. The two paths find two different alias declarations; compared as declarations, item 5.2 would make the result ambiguous. After replacement by the type, both sides are {int}, they are merged by item 5.3, and `D::T` is unambiguous. The same reasoning applies to the same injected-class-name found along several paths.
</details>
