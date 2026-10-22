---
title: Member templates
summary: "Templates declared inside a class or class template; an out-of-class definition needs two template-heads; destructors and virtual functions can't be templates; which wins when a non-template member coexists with a template specialization of the same type; how specializations of conversion function templates are named."
updated: 2026-10-19
---

!!! tldr
    - When a member template of a class template is defined outside the class, the class template's *template-head* comes first, then the member template's own; the two levels can't be merged.
    - A destructor can't be a template, a member function template can't be virtual, and a local class that isn't a closure type can't have member templates; generic lambdas are the exception.
    - A specialization of a member function template doesn't override a base-class virtual function, but it does hide base-class members with the same name.
    - A non-template member function and a member template that can generate a specialization of the same type can coexist; without explicit template arguments, the name refers to the non-template.
    - A constructor template is never a copy or move constructor, but it may beat them in overload resolution.

## Two levels of templates (¶1)

```cpp run ok
template<class T> struct string {
    template<class T2> int compare(const T2&);
    template<class T2> string(const string<T2>&) { }   // defined in the class
    string() = default;
};

template<class T> template<class T2>
int string<T>::compare(const T2&) { return 0; }        // outer first, inner second

int main() {
    string<char> s;
    string<wchar_t> w(s);              // constructor template: T = wchar_t, T2 = char
    return s.compare(w);
}
```

¶1 A template declared inside a class or class template is a **member template**: a member function template, member class template, static data member template or member alias template. The range constructor of `std::vector<T>`, `template<class InputIt> vector(InputIt, InputIt)`, is a member template: it depends on the outer `T` and also has its own parameter `InputIt`.

A member template can be defined inside or outside the class. When a member template of a class template is defined outside the class, it is written with a *template-head* equivalent to the class template's, followed by a *template-head* equivalent to the member template's (see [[temp.over.link#6]] for what equivalent means).

The two levels can't be merged into `template<class T, class T2>`. That would declare a template with two parameters, whereas what is being defined is a member of a single-parameter class template that is itself a single-parameter template.

Constraints must be equivalent level by level too:

```cpp error
template<typename T> concept C1 = true;
template<typename T> concept C2 = sizeof(T) <= 4;

template<C1 T> struct S {
    template<C2 U> void f(U);
    template<C2 U> void g(U);
};

template<C1 T> template<C2 U>
void S<T>::f(U) { }             // OK
template<C1 T> template<typename U>
void S<T>::g(U) { }             // error: S<T> has no unconstrained g
```

For a member template of an ordinary class, the out-of-class definition needs only one level:

```cpp run ok
struct Logger {
    template<class T> void log(const T&);
};
template<class T> void Logger::log(const T&) { }
int main() { Logger{}.log(42); }
```

## Which members can't be templates

### Local classes (¶2)

The first sentence of ¶2 says that a local class (a class defined in a function body, [[class.local]]) of non-closure type can't have member templates. Likewise, friend templates can't be declared in a local class ([[temp.friend#6]]).

<div class="compare" markdown="1">

```cpp error
void f() {
  struct Local {
    template<class T>
    void g(T) { }    // error
  };
}
```

```cpp run ok
int main() {
  auto id = [](auto x) {
    return x;
  };
  return id(0);
}
```

</div>

The "non-closure type" qualification is there for generic lambdas. The closure type of a generic lambda is also a local class, and its function call operator is a member function template ([[expr.prim.lambda.closure]]); that is allowed.

The second sentence of ¶2 says access control applies to member template names as usual: a `private` member template can't be accessed outside the class ([[class.access]]).

### Destructors (¶2)

The third sentence of ¶2: a destructor can't be a member template. A destructor has no parameters, so there is nothing to deduce template arguments from, and there is no syntax to specify them explicitly.

```cpp error
struct X {
    template<class T> ~X();       // error: a destructor can't be a template
};
```

Since C++20 a class can have several prospective destructors with different constraints, but none of them are templates ([[class.dtor]]).

Constructors can be templates, with two caveats. First, every template argument of a constructor template must be deducible or have a default, because there is no syntax for specifying template arguments to a constructor explicitly ([[temp.arg.explicit]]). Second, a constructor template is never a copy or move constructor ([[class.copy.ctor]]): even if it can instantiate a signature like `X(const X&)`, the class still implicitly declares a copy constructor.

In overload resolution, though, a constructor template can be better than the copy constructor:

```cpp run ok
#include <cstdio>
struct S {
    S() = default;
    S(const S&) { std::puts("copy ctor"); }
    template<class T> S(T&&) { std::puts("template ctor"); }
};
int main() {
    S a;
    S b = a;          // template ctor: T = S&, parameter S& is a better match than const S&
    const S c;
    S d = c;          // copy ctor: same parameter type, the non-template wins
    (void)b; (void)d;
}
```

`S b = a` copies a non-const lvalue but calls the forwarding-reference constructor. The usual fix is to constrain the template, for example with `requires (!std::is_same_v<std::remove_cvref_t<T>, S>)`.

### Virtual functions (¶3)

¶3 A member function template can't be declared `virtual`:

```cpp error
template<class T> struct AA {
    template<class C> virtual void g(C);   // error: virtual member function template
    virtual void f();                      // OK: an ordinary member function of a class template can be virtual
};
```

Virtual functions are usually implemented with a vtable: its size must be fixed when the class definition is compiled, and each virtual function occupies a fixed slot. The set of specializations of a member function template is open, though; any translation unit could instantiate `g<C>` with new arguments, so the number of slots needed can't be known when the class definition is compiled.

`AA<T>::f` is unaffected. It is not a function template; for each specialization such as `AA<int>` it is an ordinary member function, and the set of virtual functions in that specialization is fixed. When you need virtual functions together with genericity, the usual alternatives are type erasure (`std::function`, `std::any`), the visitor pattern, or CRTP.

### Specializations don't override virtual functions (¶4)

¶4 A specialization of a member function template does not override a virtual function from a base class:

```cpp run ok
#include <cstdio>
struct B {
    virtual void f(int) { std::puts("B::f"); }
    virtual ~B() = default;
};
struct D : B {
    template<class T> void f(T) { std::puts("D::f<T>"); }   // doesn't override B::f(int)
};
struct E : B {
    template<class T> void f(T) { std::puts("E::f<T>"); }
    void f(int i) override { f<>(i); }                       // overrides, then forwards to the template
};
int main() {
    D d; E e;
    B& rd = d; B& re = e;
    rd.f(1);          // B::f
    re.f(1);          // E::f<T>
    d.f(1);           // D::f<T>
}
```

This follows from ¶3: if a template specialization could override a virtual function, it would have to go into the vtable. `D::f` still hides `B::f`, since name lookup stops once it finds `f` in `D` ([[class.member.lookup]]), so `d.f(1)` calls `D::f<int>`; it's just that a virtual call through `B&` won't dispatch to it.

## The non-template member wins (¶2)

The last sentence of ¶2: a class may declare both a non-template member function and a member function template with the same name that can generate a specialization of the same type. When both exist, using that name and type refers to the non-template member, unless an explicit template argument list is supplied.

```cpp run ok
#include <cstdio>
template<class T> struct A {
    void f(int) { std::puts("non-template"); }
    template<class T2> void f(T2) { std::puts("template"); }
};

int main() {
    A<char> ac;
    ac.f(1);          // non-template: both are exact matches, the non-template wins
    ac.f('c');        // template: T2 = char is an exact match, better than the char-to-int promotion
    ac.f<>(1);        // template: there is an explicit template argument list (even if empty)
}
```

For calls, this agrees with the rule in [[over.match.best]] that a non-template is better than a template specialization. Where a function has to be named, as in an explicit specialization, the same rule tells them apart:

```cpp run ok
template<class T> struct A {
    void f(int);
    template<class T2> void f(T2);
};
template<> void A<int>::f(int) { }                  // non-template member f(int)
template<> template<> void A<int>::f<>(int) { }     // specialization f<int> of the member template
int main() { A<int> a; a.f(1); a.f<>(1); }
```

The difference between the two lines is whether `f` is followed by `<>`. With `<>` it names a specialization of the template; the member template itself is being specialized too, so an extra `template<>` level is needed.

## Conversion function templates (¶5)

¶5 is a note: a specialization of a conversion function template is named the same way as a non-template conversion function that converts to the same type ([[class.conv.fct]]). `operator char*` can refer either to a non-template conversion function or to the specialization of `template<class T> operator T*()` with `T = char`.

```cpp run ok
struct A {
    template<class T> operator T*();
};
template<class T> A::operator T*() { return nullptr; }
template<> A::operator char*() { return nullptr; }      // explicit specialization: T = char
template A::operator void*();                           // explicit instantiation: T = void

int main() {
    A a;
    int* ip = a.operator int*();       // explicit call, T deduced from int*
    double* dp = a;                    // implicit conversion, T deduced from the target type
    return ip == nullptr && dp == nullptr ? 0 : 1;
}
```

The template arguments of a conversion function template can only be deduced from the target type of the conversion ([[temp.deduct.conv]]); there is no syntax for specifying them explicitly.

!!! std
    An expression designating a particular specialization of a conversion function template can only be formed with a *splice-expression*.

{{c++26}} The last sentence of the note says that the only way to write an expression designating a particular specialization of a conversion function template is a static-reflection *splice-expression* ([[expr.prim.splice]]); ordinary syntax has no corresponding *template-id* form. Clang 23 doesn't implement static reflection yet, so there is no example here.

!!! lawyer "Conversion function templates alongside non-template conversion functions"
    A class can have both `operator int*()` and `template<class T> operator T*()`. When converting to `int*`, the two have the same conversion sequence and the non-template wins ([[over.match.best]]). Partial ordering of two conversion function templates compares return types ([[temp.deduct.partial#3.2]]); when their return types differ, constraints don't break the tie ([[temp.func.order#8.3]]).

## Questions

!!! question "Question"
    Which function does each of these three calls select?

    ```cpp
    struct X {
        void g(long);
        template<class T> void g(T);
    };
    X x;
    x.g(1);       // (a)
    x.g(1L);      // (b)
    x.g<long>(1); // (c)
    ```

<details markdown="1">
<summary>Answer</summary>

(a) The template `g<int>`. Deduction gives `T = int`, an exact match; the non-template `g(long)` needs an integral conversion from int to long. The exact match is better, so the template wins. The non-template preference only applies when the two conversion sequences are indistinguishable.

(b) The non-template `g(long)`. Both are exact matches, and the non-template wins.

(c) The template `g<long>`. The explicit template argument list excludes the non-template.
</details>
