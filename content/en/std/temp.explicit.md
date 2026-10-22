---
title: Explicit instantiation
summary: "`template class X<int>;` generates the specialization's definition here, and `extern template class X<int>;` tells this translation unit not to generate it and to use the definition from elsewhere; used to cut compile times, hide template implementations in .cpp files, and force every member to be checked."
updated: 2026-10-19
---

!!! tldr
    - `template class X<int>;` is an explicit instantiation definition, generating `X<int>` from the template here; `extern template class X<int>;` is an explicit instantiation declaration, telling the compiler this translation unit needn't generate it because it exists elsewhere.
    - There is no `<>` after `template`. `template<>` with `<>` is an explicit specialization, which means something completely different.
    - Explicitly instantiating a class template specialization instantiates all its defined direct non-template members whose constraints are satisfied, which can be used to force every member to be checked.
    - If `extern template` is used and the entity is then used in this translation unit, the program must contain an explicit instantiation definition for it; otherwise it is ill-formed, no diagnostic required, which in practice shows up as a link error.
    - For inline functions, `extern template` doesn't prevent instantiation for inlining; it only suppresses the out-of-line copy.

## Two forms (¶1–¶2)

With implicit instantiation ([[temp.inst]]) the compiler decides where to generate a specialization's definition, usually one copy in each translation unit that uses it, deduplicated by the linker. **Explicit instantiation** ([[g:explicit-instantiation]]) hands this decision to the programmer:

```cpp
template class std::vector<int>;          // explicit instantiation definition: generate here
extern template class std::vector<int>;   // explicit instantiation declaration: don't generate in this TU
```

¶1 Specializations of class templates, function templates, variable templates and member templates can be explicitly instantiated, as can member functions, member classes and static data members of class templates.

¶2 The syntax is `extern`(opt) `template` *declaration*. With `extern` it is an **explicit instantiation declaration** ([[g:explicit-instantiation-declaration]]); without it, an **explicit instantiation definition**.

| Form | Meaning |
|---|---|
| `template struct X<int>;` | explicit instantiation definition: generate `X<int>` from the template |
| `extern template struct X<int>;` | explicit instantiation declaration: don't generate in this translation unit |
| `template<> struct X<int> { … };` | explicit specialization: use this definition instead of the template ([[temp.expl.spec]]) |

It has three uses:

1. Cutting compile times. Instantiating a heavyweight specialization in every translation unit is expensive. Put `extern template` in the header and one explicit instantiation definition in some `.cpp` file, and other translation units only generate calls. libstdc++ and libc++ do this for `basic_string<char>`, `basic_ostream<char>` and others.
2. Hiding template implementations in `.cpp` files. When a template only makes sense for a few arguments, put only declarations in the header, the definitions in a `.cpp` file, and explicitly instantiate those few.
3. Testing. An explicit instantiation definition instantiates every member of the class, exposing errors early that would otherwise only appear when a particular member is called (¶9).

## Syntactic restrictions (¶3–¶4)

¶3 An explicit instantiation can't have storage class specifiers other than `thread_local`; explicit instantiations of function templates, member functions of class templates and variable templates can't use `inline`, `constexpr` or `consteval`; and they can't have attributes. These properties belong to the entity itself and are determined by the template; an explicit instantiation only causes the entity to be generated here.

```cpp error
template<class T> inline void f(T) {}
template inline void f(int);          // error: can't be inline
template static void f(char);         // error: can't have a storage class
template [[nodiscard]] void f(long);  // error: can't have attributes
```

¶4 When instantiating a class, the *declaration* must name the class with a *simple-template-id* with angle brackets; otherwise the *declaration* must be a simple declaration with exactly one declarator and no initializer. The name of a variable template specialization must likewise be a *simple-template-id*.

```cpp run ok title="explicit_forms.cpp"
template<class T> class Array { void mf(); };
template<class T> void Array<T>::mf() { }

template class Array<char>;            // the whole class
template void Array<int>::mf();        // only one member function

template<class T> void sort(Array<T>&) { }
template void sort(Array<char>&);      // T deduced from the function type

namespace N {
  template<class T> void f(T&) { }
}
template void N::f<int>(int&);         // qualified name, explicit template argument

int main() { }
```

An explicit instantiation of a function template can omit the template arguments; [[temp.deduct.decl]] deduces them from the declared function type.

## Relationship to the original template (¶5–¶8)

¶5 An explicit instantiation doesn't introduce a new name. The declaration of a function template, variable template, or member function or static data member of a class template must be reachable from the explicit instantiation; the definition of a class template or member class must be reachable too, unless an explicit specialization with the same arguments is already reachable.

¶5 also says that an explicit instantiation can't name an implicitly-declared special member function ([[special]]). Such functions are implicitly defined only when needed and aren't instantiated from a member definition of the template, so there is nothing to explicitly instantiate.

```cpp error
template<class T> struct S { };
template S<int>::S();   // error: S<int>::S() is implicitly declared
```

¶6 The declaration in an explicit instantiation and the declaration produced by substituting into the template are two declarations of the same entity. Note 1 points out that their types must match per [[basic.link]]:

```cpp
template<typename T> T var = {};
template float var<float>;      // OK: the instantiated variable has type float
template int var<int[16]>[];    // OK: the first array bound may be omitted
template int *var<int>;         // error: the instantiated variable has type int

template<typename T> auto av = T();
template int av<int>;           // OK: an auto variable can be redeclared with int

template<typename T> auto f() {}
template void f<int>();         // error: a function with a deduced return type must be redeclared with a placeholder type
```

The last line must be written `template auto f<int>();` ([[dcl.spec.auto]]). The last sentence of ¶6 explains that an explicit instantiation of a variable looks like a definition syntactically but isn't one, and doesn't conflict with the definition generated by an explicit instantiation definition.

!!! impl "Clang deviates"
    Clang 23 rejects `template int var<int[16]>[];` with type 'int[]' of explicit instantiation of 'var' does not match expected type 'int[16]'. The standard's example states explicitly that it is valid.

¶7 If, for the same arguments, an explicit instantiation appears after a declaration of an explicit specialization, the explicit instantiation has no effect (Clang 23 gives a `-Winstantiation-after-specialization` warning). The reverse order is ill-formed; see [[temp.spec#5]]. Apart from that, every translation unit containing an explicit instantiation definition must contain the definition of the corresponding function template, variable template, member function or static data member: without the template's definition, there is nothing to generate from.

¶8 is a note: explicitly instantiating a constrained template requires its associated constraints to be satisfied ([[temp.constr.decl]]).

## Instantiating a class instantiates its members (¶9–¶11)

```cpp error
template<class T> struct Box {
  T v;
  void ok() { }
  void bad() { v.nope(); }   // valid only for T with nope()
};
Box<int> b;                  // OK: implicit instantiation doesn't generate bad's definition
template struct Box<int>;    // error: the explicit instantiation definition generates bad
```

¶9 An explicit instantiation of a class template specialization is also an explicit instantiation of the same kind (declaration or definition) of each of its **direct non-template members**. Two kinds of members are skipped: those already explicitly specialized in this translation unit, and those whose associated constraints aren't satisfied by these arguments. Note 3 adds that implementation data associated with the class, such as the vtable, is typically instantiated too.

¶10 An explicit instantiation definition is an explicit instantiation definition only for those members that have been defined at the point of instantiation.

```cpp run ok
template<class T> struct Box {
  T v;
  void bad() requires requires (T t) { t.nope(); }
  { v.nope(); }              // constraints not satisfied: skipped (¶9)
  void later();              // not defined: skipped (¶10)
};
template struct Box<int>;    // OK
int main() {}
```

The exception for constraints was added with C++20 concepts. Without it, a member with a `requires` clause that exists only for some `T` would make explicit instantiation of the whole class fail.

¶9 talks about direct non-template members. Member function templates and member class templates still lack template arguments and aren't instantiated. A nested class is a non-template member; it is instantiated, and its members recursively instantiated.

¶11 An explicit instantiation of a prospective destructor (since C++20 a class can declare several destructors with different constraints, see [[class.dtor]]) must correspond to the one finally selected for the class.

## Rules for extern template (¶12)

¶12 If an entity has both an explicit instantiation declaration and an explicit instantiation definition in the same translation unit, the definition must follow the declaration:

<div class="compare" markdown="1">

```cpp run ok
template<class T> void f(T) {}
extern template void f(int);
template void f(int);   // OK
int main() {}
```

```cpp error
template<class T> void f(T) {}
template void f(int);
extern template void f(int);
// error: declaration after definition
```

</div>

If an entity has an explicit instantiation declaration and is used in this translation unit in a way that would otherwise cause an implicit instantiation, there must be an explicit instantiation definition for it somewhere in the program; otherwise the program is {{ifndr}} (ill-formed, no diagnostic required: the standard places no requirements on such a program). In practice this shows up as a link error.

Note 4 explains that this also applies to inline functions, even though an explicit instantiation declaration of an inline function has no other normative effect. The reason: if some translation unit takes the address of the inline function and the implementation chooses not to emit the body there, another translation unit has to provide it.

An explicit instantiation declaration can't name a specialization of a template with internal linkage, because no other translation unit could provide its definition:

```cpp error
namespace { template<class T> void f(T) {} }
extern template void f(int);   // error: has internal linkage
```

### A multi-translation-unit example

```cpp title="big.h"
#pragma once
#include <cstdio>
template<class T> struct Big {
  T v{};
  void work() { std::printf("work %d\n", (int)v); }   // defined in class: implicitly inline
};
extern template struct Big<int>;   // includers shouldn't instantiate Big<int>'s members
```

```cpp title="big.cpp"
#include "big.h"
template struct Big<int>;          // the only explicit instantiation definition
```

```cpp title="main.cpp"
#include "big.h"
int main() { Big<int> b; b.work(); }
```

Compiling `main.cpp` with Clang 23 and inspecting the symbols with `nm`:

- `-O0`: `Big<int>::work()` is an undefined symbol, left for the linker to find in `big.o`. Linking `main.o` alone gives `Undefined symbols … Big<int>::work()`; this is what the IFNDR of ¶12 looks like in practice.
- `-O2`: `work` is inlined, `main.o` has no reference to it at all, and linking it alone succeeds.

The `-O2` result is exactly the effect of item 1.1 of [[temp.inst#1]]: an inline function, even with `extern template`, can still be instantiated for inlining; only the out-of-line copy isn't emitted. So for member functions defined in the class, what `extern template` saves is mainly the cost of emitting code and of linker deduplication, while the front end still instantiates the body; only for member functions defined outside the class without `inline` does it really avoid instantiation in this translation unit.

!!! pitfall "Only debug builds fail to link"
    The header has `extern template class X<int>;`, but no `.cpp` file has `template class X<int>;`. Linking fails at `-O0`, and may succeed at `-O2` because everything got inlined. Problems like this are hard to track down.

!!! tip "When to use extern template"
    It is worth it only when a few specializations are used by many translation units and are expensive to instantiate, and you should measure first. Precompiled headers and modules usually give bigger gains. Templates exported from modules are still instantiated in the importer, so `extern template` remains meaningful with modules.

## Default arguments aren't instantiated (¶13)

```cpp run ok
char* p = 0;
template<class T> T g(T x = &p) { return x; }
template int g<int>(int);   // OK: even though &p can't be converted to int
int main() {}
```

¶13 An explicit instantiation doesn't count as a use of default arguments, so no default argument instantiation is done ([[temp.inst#14]]). The default argument `&p` has type `char**`, which is ill-formed for `T = int`, but as long as no call omits that argument, it is never instantiated.

## Implementation notes

!!! impl "ABI and object files"
    - With the Itanium C++ ABI (Linux, macOS), symbols generated by implicit instantiation and by explicit instantiation definitions may appear repeatedly in several object files, and the linker merges them. So duplicate explicit instantiation definitions across translation units (violating item 5.1 of [[temp.spec#5]]) go unnoticed in practice.
    - On MSVC, `extern template` combined with `__declspec(dllexport)` / `__declspec(dllimport)` is the usual way to export template specializations from a DLL.
    - Explicitly instantiating a class template generates the vtable (the implementation data mentioned in Note 3 of ¶9), which can pin the vtable to one translation unit.

!!! history "History"
    | Version | Change |
    |---|---|
    | C++98 | explicit instantiation definition `template class X<int>;` |
    | C++11 | explicit instantiation declaration `extern template`, previously a compiler extension |
    | C++14 | explicit instantiation of variable templates |
    | C++20 | members with unsatisfied constraints are skipped (¶9); prospective destructors (¶11) |

## Common misconceptions

!!! pitfall "`template` and `template<>` are about the same"
    `template void f<int>(int);` is an instantiation, using the template's definition; `template<> void f<int>(int);` declares an explicit specialization, promising to provide a definition separately. Without that definition the latter fails to link; and if `f<int>` was already used before the specialization declaration, the program is ill-formed ([[temp.expl.spec#7]]).

!!! pitfall "Explicitly instantiating a standard library container always works"
    `template class std::vector<NonCopyable>;` instantiates every defined non-template member of `vector` whose constraints are satisfied. If some member not constrained with `requires` (the copy constructor, say) is ill-formed for that type, it is an error even if never called. The standard doesn't guarantee that standard library containers can be explicitly instantiated for arbitrary element types.

## Questions

!!! question "Question 1"
    ```cpp
    template<class T> struct S {
      void f();
      template<class U> void g(U) { T::nope(); }
      struct Inner { void h() { T::nope(); } };
    };
    template<class T> void S<T>::f() { }
    template struct S<int>;
    ```
    Does this explicit instantiation cause an error?

<details markdown="1">
<summary>Answer</summary>

Yes, in `Inner`. Per ¶9, explicitly instantiating `S<int>` also explicitly instantiates each of its direct non-template members. `f` is defined and instantiates fine; `g` is a member template and isn't instantiated; `Inner` is a non-template member class, gets an explicit instantiation definition, which in turn instantiates its member `h`, and `int::nope()` is an error. Clang 23 reports the error in the body of `h`.
</details>

!!! question "Question 2"
    The template definitions are in a `.cpp` file, the header has only declarations, and the end of the `.cpp` file has `template class Matrix<float>; template class Matrix<double>;`. What happens when a user uses `Matrix<int>::foo()`?

<details markdown="1">
<summary>Answer</summary>

The user's translation unit has only the declaration of `foo`, not the definitions of the template's members, so the compiler can only generate a call to an external symbol. No translation unit in the program provides a definition of `Matrix<int>::foo`, which violates the requirement that an odr-used non-inline function be defined exactly once ([[basic.def.odr]]). This is {{ifndr}}, and in practice shows up as a link error.
</details>
