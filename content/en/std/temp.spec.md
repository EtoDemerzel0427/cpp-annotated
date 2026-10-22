---
title: Instantiation and specialization
summary: "Where specializations come from: implicit instantiation, explicit instantiation and explicit specialization; at most one definition per set of arguments, and when an explicit specialization and an explicit instantiation can coexist; names in specialization declarations are exempt from access checking; each class template specialization has its own static members."
updated: 2026-10-19
---

!!! tldr
    - Substituting template arguments into a template to produce a concrete class, function or variable is called instantiation; the resulting entities, as well as replacements written by hand with `template<>`, are called specializations.
    - Specializations come from three sources: implicit instantiation on use, explicit instantiation like `template class X<int>;`, and explicit specialization like `template<> class X<int> {…};`.
    - An explicit specialization for a set of arguments must be visible before an explicit instantiation of the same arguments; the reverse is an error, and no diagnostic is required when the two are in different translation units.
    - The declarations of explicit instantiations and explicit specializations may name private types and private members, but function bodies, class bodies and similar parts are access-checked as usual.
    - Static members belong to specializations, not to the template: `X<int>::n` and `X<long>::n` are two variables.

## Three routes, one specialization

```cpp run ok
template<class T> struct Box { T v; };

Box<int> a;                         // implicit instantiation: generated from the template when used
template struct Box<long>;          // explicit instantiation: generated here, as specified
template<> struct Box<char> {       // explicit specialization: this definition instead of the template
  char v[4];
};

int main() { Box<char> c; (void)a; (void)c; }
```

A template itself is not a class, function or variable but a recipe for producing them. ¶1 calls the process of substituting template arguments and obtaining a concrete entity **template instantiation** ([[g:template-instantiation]]). What is instantiated can be a function, variable or class, or a member or member template of a class template. A member function `Box<T>::f` of a class template has no template parameter list of its own and isn't a template, but it still has to be instantiated to get the definition of `Box<int>::f`.

¶4 The entities produced by instantiation, as well as explicit specializations written by the programmer for a set of arguments, are called **specializations** ([[g:specialization]]). `Box<int>`, `Box<long>` and `Box<char>` above are all specializations of `Box`; they differ only in where the definition comes from:

| Route | Syntax | Definition comes from | Details |
|---|---|---|---|
| implicit instantiation | none, triggered by use | generated from the template by the compiler | [[temp.inst]] |
| explicit instantiation | `template struct Box<long>;`<br>`extern template struct Box<long>;` | generated from the template by the compiler, at a location the programmer specifies | [[temp.explicit]] |
| explicit specialization | `template<> struct Box<char> {…};` | written by the programmer, replacing the template entirely | [[temp.expl.spec]] |

Partial specializations ([[temp.spec.partial]]) aren't in the table: a partial specialization is itself still a template, providing an alternative template definition for a family of arguments, and it still has to be instantiated in the end.

!!! note "Specialization in everyday usage"
    In everyday speech, "writing a specialization" usually means an explicit specialization with `template<>`. In the standard the term is broader: `std::vector<int>` is a specialization of `std::vector` even if nobody ever wrote a `template<>` for it.

## How explicit specializations are written (¶3)

¶3 An explicit specialization starts with `template<>` and can be for a function template, variable template, class template, or a member or member template of a class template. For classes, variables and class members, a *simple-template-id* with angle brackets must say which one is specialized; for function templates the angle brackets may be omitted and the compiler deduces the arguments from the function type ([[temp.deduct.decl]]).

```cpp run ok title="spec_forms.cpp"
template<class T = int> struct A {
  static int x;
};
template<class U> void g(U) { }

template<> struct A<double> { };   // T == double
template<> struct A<> { };         // T == int, the default argument still applies
template<> void g(char) { }        // U == char, deduced from the parameter type
template<> void g<int>(int) { }    // U == int, written explicitly
template<> int A<char>::x = 0;     // explicit specialization of a class template member

int main() {}
```

`A<>` is also a *simple-template-id*; with the default argument filled in it is `A<int>`. Writing `template<> struct A { };` is invalid. Functions can omit the angle brackets because they have a type to deduce from; classes don't.

## At most one definition per set of arguments (¶5)

¶5 For a given template and set of template arguments:

- ¶5.1 an explicit instantiation definition shall appear at most once in a program;
- ¶5.2 an explicit specialization shall be defined at most once, as required by the ODR ([[basic.def.odr]]);
- ¶5.3 both an explicit instantiation and a declaration of an explicit specialization shall not appear, unless the explicit specialization is reachable from the explicit instantiation (reachable roughly means its declaration can be seen; see [[module.reach]]). If neither is reachable from the other, no diagnostic is required.

An explicit instantiation asks for the definition to be generated from the template, and an explicit specialization asks for the template not to be used; the two contradict each other. The only way to reconcile them is for the specialization to come first, in which case the explicit instantiation has no effect ([[temp.explicit#7]]).

<div class="compare" markdown="1">

```cpp error
template<class T>
struct S { void f() {} };
template struct S<int>;
template<> struct S<int> { };
// error: specialized after instantiation
```

```cpp ok
template<class T>
struct S { void f() {} };
template<> struct S<int> { };
template struct S<int>;
// OK: the instantiation has no effect
```

</div>

Clang 23 gives a `-Winstantiation-after-specialization` warning for the right-hand side. When the two are in different translation units and can't see each other, the compiler can't detect the conflict, so ¶5.3 is {{ifndr}} (ill-formed, no diagnostic required: the standard places no requirements on such a program).

¶5.1 doesn't say no diagnostic is required, and duplicate explicit instantiation definitions in the same translation unit are reported. But mainstream implementations emit explicit instantiation definitions as mergeable weak symbols, so duplicates across translation units aren't reported by the linker.

¶5.2 is a reminder of a common link error: an explicit specialization of a function template is an ordinary function and isn't inline by default ([[temp.expl.spec]]). Putting its definition in a header included by several translation units violates the ODR.

## Specialization declarations are exempt from access checking (¶6)

```cpp run ok title="access_exempt.cpp"
class Widget {
  struct Impl { int v = 42; };   // private
};

template<class T> struct Probe { static int get() { return 0; } };
template<> struct Probe<Widget::Impl> {   // OK
  static int get() { return 1; }
};

template<class T> int peek() { return 0; }
template<> int peek<Widget::Impl>() {     // OK
  return 1;
}

int main() { return Probe<int>::get() + peek<int>(); }
```

¶6 The usual access checking rules don't apply to names in a declaration of an explicit instantiation or explicit specialization. Note 1 points out that names in the template arguments and in the function declarator (parameter types, return type, exception specification) may be private types or objects that would normally be inaccessible. This way, specializing a trait for a private type doesn't require making the type public or adding friends everywhere.

The exemption doesn't cover: function bodies, default arguments, base-clauses, the class's member list (*member-specification*), enumerator lists, and initializers of static data members and variable templates.

```cpp error
class Widget { struct Impl { int v = 42; }; };
template<class T> int peek() { return 0; }
template<> int peek<Widget::Impl>() {
  Widget::Impl i;   // error: 'Impl' is a private member of 'Widget'
  return i.v;
}
```

Before C++20 only explicit instantiations had this exemption; writing an explicit or partial specialization for a private type was technically ill-formed, although most compilers had long allowed it. [[P0692R1]] extended the exemption to specializations.

!!! lawyer "Getting a pointer to a private member legally"
    The explicit instantiation exemption can be used to obtain a pointer to a private member, with fully defined behavior:

    ```cpp run ok title="steal.cpp"
    #include <cstdio>
    class Bank { int balance = 100; };

    template<int Bank::* M> struct Thief {
      friend int Bank::* steal() { return M; }
    };
    int Bank::* steal();   // so that ordinary lookup can find steal

    template struct Thief<&Bank::balance>;   // OK: exempt from access checking

    int main() {
      Bank b;
      std::printf("%d\n", b.*steal());       // 100
    }
    ```

    The template argument `&Bank::balance` is written in an explicit instantiation and isn't access-checked; the friend function `steal` carries the member pointer out of the template. With an implicit instantiation instead (`Thief<&Bank::balance> t;`) access is checked, and Clang 23 reports `'balance' is a private member of 'Bank'`. Test frameworks and serialization libraries use this trick.

## Each specialization has its own static members (¶7)

```cpp run ok
template<class T> struct Counter { static int n; };
template<class T> int Counter<T>::n = 0;

int main() {
  Counter<int>::n += 1;
  Counter<long>::n += 5;
  return Counter<int>::n == 1 && Counter<long>::n == 5 ? 0 : 1;
}
```

¶7 Each class template specialization instantiated from a template has its own copy of any static members. `Counter<int>` and `Counter<long>` are two unrelated classes, and `n` is two variables. A template isn't a class and has no members; only specializations do. Local static variables in function templates work the same way, one per specialization ([[temp.fct.spec.general#2]]).

!!! pitfall "A counter in a template isn't global"
    To count how many `Handle<T>` have been created in total, putting `static int count` in `Handle<T>` is wrong: each `T` counts separately. The counter belongs in a non-template base class or at namespace scope.

## A dependent type can't turn a declaration into a function declaration (¶8)

```cpp error
template<class T> struct A {
  static T t;
};
typedef int function();
A<function> a;   // error: A<function>::t would become a static member function
```

¶8 If a function declaration acquires its function type through a dependent type rather than through the syntactic form of a function declarator, the program is ill-formed. In ordinary code `typedef int F(); F f;` is a valid function declaration ([[dcl.fct]]). If this were allowed in templates, whether `static T t;` declares a data member or a member function would depend on the template argument, and the structure of the class template couldn't be determined. Clang 23's diagnostic is static data member instantiated with function type.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

¶2 gives names to instantiated entities: a function instantiated from a function template is an instantiated function, a class instantiated from a class template is an instantiated class; a member function, member class, member enumeration or static data member of a class template instantiated from the member definition is an instantiated member function, member class, member enumeration or static data member respectively; member function templates, member class templates, variable templates and static data member templates have corresponding names too. These names carry no extra semantics; they just let later text refer to things precisely.

</details>

## Questions

!!! question "Question 1"
    Is the following program well-formed?
    ```cpp
    template<class T> struct S { static const int v = 1; };
    template<> struct S<int>;   // (a)
    S<int>* p;                  // (b)
    int n = S<int>::v;          // (c)
    ```

<details markdown="1">
<summary>Answer</summary>

It's ill-formed, and the error is at (c). (a) declares the explicit specialization `S<int>` without defining it. (b) only needs a pointer, which doesn't require a complete type. (c) requires `S<int>` to be complete; per [[temp.expl.spec#7]], a declared explicit specialization isn't implicitly instantiated, and without a definition it is an incomplete type. The `v` in the primary template has nothing to do with `S<int>`. Clang 23 reports incomplete type 'S<int>' named in nested name specifier.
</details>

!!! question "Question 2"
    `Impl` is a private member of `Widget`. Where would the following report access errors?
    ```cpp
    template<> struct std::hash<Widget::Impl> {
      std::size_t operator()(const Widget::Impl& i) const { return i.v; }
    };
    ```

<details markdown="1">
<summary>Answer</summary>

`Widget::Impl` in the template argument of `std::hash<Widget::Impl>` is exempt. But `operator()` is in the class definition of the specialization, part of the *member-specification*, which ¶6 excludes from the exemption, so both `Widget::Impl` in the parameter type and `i.v` in the function body are checked and rejected. The exemption only covers the specialization declaration itself, not the specialization's contents. In practice, have `Widget` declare `std::hash<Widget::Impl>` a friend.
</details>
