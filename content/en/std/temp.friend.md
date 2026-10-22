---
title: Templates and friends
summary: "What a friend declaration in a class template refers to: an ordinary function, one specialization of a template, or a whole template; which specializations a friend template covers; the prohibitions; constrained friends; and why operator<< in a template so often fails to link."
updated: 2026-10-19
---

!!! tldr
    - `friend void f(X<T>)` in a class template has no `<...>`, so it declares an ordinary function for each specialization, not a specialization of a function template. This is the root cause of `operator<<` in templates failing to link.
    - Written as `f<T>` or `f<>`, it refers to one specialization of a function template; written as `template<class U> friend ...`, it refers to every specialization of the whole template.
    - When a template is declared a friend, its partial specializations and explicit specializations are friends too.
    - A friend can't be a partial specialization, a local class can't declare a friend template, and a friend declaration referring to a specialization can't have default arguments or `inline`, `constexpr` or `consteval`.
    - A non-template friend with a *requires-clause* must be a definition; for operators on class templates, prefer a hidden friend defined in the class.

## A link error

```cpp ifndr
#include <iostream>
template<class T> class Box {
    T v;
public:
    Box(T t) : v(t) { }
    friend std::ostream& operator<<(std::ostream&, const Box&);   // the problem is here
};
template<class T>
std::ostream& operator<<(std::ostream& os, const Box<T>& b) { return os << b.v; }

int main() { std::cout << Box<int>(1); }   // compiles, fails to link: undefined reference
```

This code appears to declare a friend and then define it below, yet the linker can't find `operator<<`. To explain this, we first need to pin down what a friend declaration in a class template actually declares. The general rules for friends are in [[class.friend]]; this subclause handles the cases where templates and friends meet.

## Kinds of friends (¶1)

¶1 A friend of a class or class template can be a function template or class template, a specialization of a function template or class template, or a non-template function or class. The standard puts all the combinations into one example:

```cpp run ok
template<class T> class task;
template<class T> task<T>* preempt(task<T>*);

template<class T> class task {
    friend void next_time();                  // (a)
    friend void process(task<T>*);            // (b)
    friend task<T>* preempt<T>(task<T>*);     // (c)
    template<class C> friend int func(C);     // (d)

    friend class task<int>;                   // (e)
    template<class P> friend class frd;       // (f)
};
int main() { }
```

| | The friend of each specialization `task<T>` is |
|---|---|
| (a) | the same ordinary function `::next_time()` |
| (b) | an ordinary function whose type varies with `T`: the friend of `task<int>` is `void process(task<int>*)`, which is not a specialization of a function template |
| (c) | the specialization `preempt<T>` of the function template `preempt`, one specialization per specialization |
| (d) | all specializations of the function template `func` |
| (e) | the class template specialization `task<int>` |
| (f) | all specializations of the class template `frd` |

The key is the difference between (b) and (c): a friend function declaration without explicit template arguments `<...>` declares an ordinary function, even if its parameter types depend on `T`.

Back to the opening example. `friend ... operator<<(std::ostream&, const Box&)` is case (b): it declares, for `Box<int>`, an ordinary function `operator<<(std::ostream&, const Box<int>&)`, and the function template below is a different entity. In overload resolution, this ordinary function has the same conversion sequences as the template specialization `operator<< <int>`, the non-template wins, and so the ordinary function, which is declared but never defined, is selected. Odr-using a non-inline function that has no definition makes the program IFNDR per [[basic.def.odr]], and in practice it shows up as a link error. GCC has a dedicated warning for this pattern, `-Wnon-template-friend`; Clang doesn't warn.

## Fixing operator<<

```cpp run ok
#include <iostream>
#include <sstream>

// Option 1: hidden friend, defined in the class
template<class T> class Box1 {
    T v;
public:
    Box1(T t) : v(t) { }
    friend std::ostream& operator<<(std::ostream& os, const Box1& b) { return os << b.v; }
};

// Option 2: the friend refers to one specialization of a function template; needs forward declarations
template<class T> class Box2;
template<class T> std::ostream& operator<<(std::ostream&, const Box2<T>&);
template<class T> class Box2 {
    T v;
public:
    Box2(T t) : v(t) { }
    friend std::ostream& operator<< <T>(std::ostream&, const Box2&);   // note the <T>; <> also works
};
template<class T> std::ostream& operator<<(std::ostream& os, const Box2<T>& b) { return os << b.v; }

// Option 3: the whole function template as a friend
template<class T> class Box3 {
    T v;
public:
    Box3(T t) : v(t) { }
    template<class U> friend std::ostream& operator<<(std::ostream&, const Box3<U>&);
};
template<class U> std::ostream& operator<<(std::ostream& os, const Box3<U>& b) { return os << b.v; }

int main() {
    std::ostringstream s;
    s << Box1<int>(1) << Box2<int>(2) << Box3<int>(3);
    return s.str() == "123" ? 0 : 1;
}
```

| Option | What the friend is | Pros | Cons |
|---|---|---|---|
| hidden friend | an ordinary function per specialization | concise; found only by ADL; allows implicit conversions | the body is written in the class |
| `operator<< <T>` | one specialization of a function template | one-to-one grant, the most precise | needs forward declarations of the class template and function template |
| `template<class U> friend` | all specializations of a function template | no forward declarations needed | grants too much: `operator<< <char>` can also access the private members of `Box3<int>` |

!!! tip "hidden friend"
    A function first declared in a friend declaration isn't found by ordinary name lookup; only argument-dependent lookup (ADL, which looks for functions in the classes and namespaces associated with the argument types, [[basic.lookup.argdep]]) can find it. Such a friend defined in the class is called a **hidden friend**. It takes part in overload resolution only when an argument's type is associated with `Box1<T>`, so the overload set is smaller and error messages are shorter. It is not a template and does no deduction, so the argument on the other side can undergo implicit conversion.

## How friends are found after instantiation (¶2)

¶2 A friend class, friend class template, friend function or friend function template can be declared in a class template. When the template is instantiated, name lookup treats its friend declarations as if they had been explicitly declared at the point of instantiation of that specialization.

Note 1 adds that a friend declaration can introduce entities belonging to an enclosing namespace ([[dcl.meaning]]); those entities are then attached to the same module as the class template ([[module.unit]]).

## Friend templates (¶3–4)

¶3 A friend template can be declared in a class or class template. A friend function template can be defined in the class; a friend class template can't. In both cases, all specializations of the friend template are friends of the granting class.

```cpp error
class A {
    template<class T> friend class B;                    // OK
    template<class T> friend void f(T) { }               // OK: a friend function template can be defined in the class
    template<class T> friend class C { };                // error: a friend class template can't be defined in the class
};
```

¶4 A template friend declaration makes all specializations of the template friends, whether implicitly instantiated, partially specialized or explicitly specialized:

```cpp run ok
class X {
    template<class T> friend struct A;
    class Y { };                                         // private
};
template<class T> struct A      { X::Y ab; };            // OK: primary template
template<class T> struct A<T*>  { X::Y ab; };            // OK: partial specialization
template<>        struct A<int> { X::Y ab; };            // OK: explicit specialization
int main() { A<char> a; A<int*> b; A<int> c; (void)a; (void)b; (void)c; }
```

Friendship is granted to the template as an entity, and partial and explicit specializations are just other definitions of it. Otherwise, a library author adding a partial specialization to a template would unexpectedly lose access.

## Members of dependent types as friends (¶5)

¶5 A template friend declaration can declare a member of a dependent type to be a friend. The requirements: what is declared is a function, or a type specified with an *elaborated-type-specifier* (such as `struct A<T>::B`); its qualifier ends with a *simple-template-id* naming a class template (call it `C`, e.g. `A<T>`); and all template parameters of the friend declaration are deducible from `C` ([[temp.deduct.type]]).

For a specialization `S` of a class template, deciding whether a member of it is a friend takes two steps: first deduce the template parameters of `C` from `S`; if deduction succeeds, substitute the result into the friend declaration and check whether the resulting declaration corresponds to that member of `S`.

```cpp
template<class T> struct A {
    struct B { };
    void f();
    struct D { void g(); };
    T h();
    template<T U> T i();
};
template<> struct A<int> {
    struct B { };
    int f();
    struct D { void g(); };
    template<int U> int i();
};
template<> struct A<float*> { int* h(); };

class C {
    template<class T> friend struct A<T>::B;      // A<int>::B is a friend too
    template<class T> friend void A<T>::f();      // A<int>::f() is not a friend
    template<class T> friend void A<T>::D::g();   // error: A<T>::D doesn't end with a simple-template-id
    template<class T> friend int* A<T*>::h();     // A<int*>::h() and A<float*>::h() are friends
    template<class T> template<T U>
        friend T A<T>::i();                       // all specializations of A<T>::i and A<int>::i
};
```

- `A<int>` is an explicit specialization, and its `B` is unrelated to the primary template's `A<T>::B`. But substituting `T = int` gives `struct A<int>::B`, which corresponds to it, so it is a friend. Matching only looks at the shape of the declaration.
- `A<int>::f()` returns `int`; the substituted declaration is `void A<int>::f()`, which doesn't match, so it is not a friend.
- The qualifier of `A<T>::D::g()` ends with `D`, which can't be deduced from a specialization `S`, so it is ill-formed.
- `A<T*>::h()` requires `S` to have the form `A<X*>`; both `A<int*>` and `A<float*>` qualify.

!!! warning "Clang doesn't support ¶5"
    For all five friend declarations above, Clang 23 only gives a `-Wunsupported-friend` warning: dependent nested name specifiers aren't supported, so it turns off access control for class `C`. The result grants too much, since any code can access the private members of `C`; the `A<T>::D::g()` line isn't rejected either. That's why the code above has no verdict label. For portable code, declare the whole class template `A` a friend instead.

## Prohibitions (¶6–8)

¶6 A friend template can't be declared in a local class, consistent with local classes not having member templates ([[temp.mem#2]]). ¶7 A friend declaration can't declare a partial specialization.

```cpp error
template<class T> class A { };
class X {
    template<class T> friend class A<T*>;         // error: a friend can't be a partial specialization (¶7)
};
void loc() {
    struct L {
        template<class T> friend void zz(T);      // error: friend template in a local class (¶6)
    };
}
```

To make a particular partial specialization a friend, the only way is to declare the whole template a friend; ¶4 guarantees the partial specializations are included.

¶8 When a friend declaration refers to a specialization of a function template, its parameters can't have default arguments, and the declaration can't use `inline`, `constexpr` or `consteval`. Such a declaration doesn't introduce a new function; it only refers to the specialization generated from the template or explicitly specialized. Default arguments and these specifiers belong on the template itself or on the explicit specialization.

```cpp error
template<class T> void ff(T);
struct Z { friend void ff<int>(int = 0); };       // error: default argument
```

!!! note "What Clang does"
    Clang 23 rejects the code above, but for a different reason: a friend declaration with default arguments must be the only declaration. It accepts `friend inline void ff<long>(long);`, which per ¶8 is also ill-formed.

## Constrained friends (¶9)

¶9 has three sentences:

1. A non-template friend declaration with a *requires-clause* must be a definition.
2. A friend function template whose constraints depend on template parameters of the enclosing template must also be a definition.
3. Such a constrained friend does not declare the same function or function template as a declaration in any other scope.

```cpp error
template<class T> struct Q {
    friend void k() requires (sizeof(T) > 1);     // error: must be a definition
};
```

Sentence 3 is the reason for sentences 1 and 2. `friend void h(R) requires C<T>` has one copy in `R<int>` and another in `R<short>`, and the constraint varies with `T`, so they are different functions. There is no way to write a declaration outside the class that corresponds to the `h` in `R<int>`, so the definition has to be given right there.

Sentence 3 also means that constrained hidden friends don't conflict across multiple instantiations. An in-class friend definition that is unconstrained and doesn't depend on `T` does:

<div class="compare" markdown="1">

```cpp error
template<class T> struct S {
  friend void g() { }
};
S<int> a;
S<char> b;  // error: redefinition of ::g
```

```cpp run ok
template<class T> struct R {
  friend void h(R)
    requires (sizeof(T) > 1) { }
};
R<int> r1;
R<short> r2;  // OK: two different h
int main() { h(r1); h(r2); }
```

</div>

## Questions

!!! question "Question 1"
    With each of the following two forms, can `operator<< <char>` access the private members of `Box<int>`?

    (a) `friend std::ostream& operator<< <T>(std::ostream&, const Box&);`
    (b) `template<class U> friend std::ostream& operator<<(std::ostream&, const Box<U>&);`

<details markdown="1">
<summary>Answer</summary>

(a) No. The only friend of `Box<int>` is `operator<< <int>`, one specialization per specialization (¶1 (c)).

(b) Yes. `Box<int>` declares the whole function template a friend (¶3), so all its specializations, including `operator<< <char>`, are friends of `Box<int>`.
</details>

!!! question "Question 2"
    Do `print(b)` and `print(1)` compile?

    ```cpp
    template<class T> struct Box1 {
        T v;
        Box1(T t) : v(t) {}
        friend void print(const Box1&) {}
    };
    Box1<int> b(0);
    void test() { print(b); print(1); }
    ```

<details markdown="1">
<summary>Answer</summary>

`print(b)` does, `print(1)` doesn't. A hidden friend can only be found by ADL. The associated class of `b` is `Box1<int>`, so ADL finds `print`; the argument `1` has type `int`, which has no associated classes, so name lookup never finds `print` at all, and Clang reports it as an undeclared identifier. Even though there is an implicit conversion from `int` to `Box1<int>`, the hidden friend isn't selected by accident.
</details>
