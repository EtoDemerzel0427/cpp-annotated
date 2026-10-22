---
title: Alias templates
summary: "An alias template is a name for a family of types, and its specialization is simply the substituted type; it follows that aliases can't be used to overload, can't themselves be deduced, and can't be specialized, while a dependent alias specialization still has every argument substituted."
updated: 2026-10-19
---

!!! tldr
    - With `template<class T> using Vec = std::vector<T, Alloc<T>>;`, `Vec<int>` is `std::vector<int, Alloc<int>>`, not a new type.
    - So aliases can't distinguish overloads, and the alias template itself can't be deduced from a type; deducing its arguments through the alias does work.
    - Alias templates can't be specialized. To choose by type, put the specialization on a class template and forward to it through the alias.
    - A dependent alias specialization (such as `void_t<typename T::foo>`) still has all its arguments substituted, including unused ones; this is the basis of the `void_t` detection idiom.
    - An alias can't refer to itself directly or indirectly; a lambda in an alias is a different type in every instantiation.

## Declaration (¶1)

```cpp run ok
#include <memory>
#include <type_traits>
#include <vector>
template<class T> struct Alloc : std::allocator<T> { };

template<class T> using Vec = std::vector<T, Alloc<T>>;
template<class T> using Ptr = T*;            // needn't be a class template specialization
template<class T, int N> using Arr = T[N];

Vec<int> v;                                  // same as std::vector<int, Alloc<int>> v;
static_assert(std::is_same_v<Ptr<int>, int*>);
static_assert(sizeof(Arr<char, 4>) == 4);
int main() {}
```

¶1 A template declaration whose declaration is an alias-declaration (`using name = type;`, [[dcl.pre]]) declares an [[g:alias-template|**alias template**]]. An alias template is a name for a family of types.

C++03's `typedef` couldn't take template parameters; the workaround was a typedef nested inside a class template, used as `typename MyAlloc<T>::type`. An alias template is a typedef with parameters: it defines no new entity, it just gives a name to the substituted type.

## Aliases are transparent (¶2)

¶2 A *template-id* that refers to a specialization of an alias template, such as `Vec<int>`, is equivalent to the type obtained by substituting the template arguments into the alias's definition (the *defining-type-id* to the right of `=`). The same goes for a specialization obtained by splicing (*splice-specialization-specifier*, {{c++26}}, [[basic.splice]]). The only exception is a *template-id* that is the operand of the reflection operator `^^`; see the end of this page.

Note 1 points out a consequence: an alias template name is never deduced from such a type ([[temp.deduct.type]]).

```cpp error
#include <memory>
#include <vector>
template<class T> struct Alloc : std::allocator<T> { };
template<class T> using Vec = std::vector<T, Alloc<T>>;
Vec<int> v;

template<class T> void process(Vec<T>&) { }
template<class T> void process(std::vector<T, Alloc<T>>&) { }   // error: redefinition

template<template<class> class TT> void f(TT<int>);
template<template<class, class> class TT> void g(TT<int, Alloc<int>>);

void test() {
  f(v);   // error: can't deduce TT = Vec
  g(v);   // OK: TT = std::vector
}
```

- `process` is redefined: `Vec<T>` is `std::vector<T, Alloc<T>>`, so the two declarations are the same function template. An alias creates no new type, so naturally it can't be used to overload.
- `f(v)` fails: the type of `v`, `std::vector<int, Alloc<int>>`, doesn't remember that it was written through `Vec`. The compiler only sees a specialization of `std::vector` with two arguments, which can't match the single-argument `TT<int>`.
- `g(v)` succeeds: `TT<int, Alloc<int>>` has the same structure as `std::vector<int, Alloc<int>>`, so `TT = std::vector`.

What can't be deduced is the alias template's name. Deducing its arguments through the alias is fine, because after substitution the alias is gone and what remains is an ordinary parameter type:

```cpp run ok
#include <type_traits>
template<class T> using Id = T;
template<class T> int deduce(Id<T>) { return 1; }                        // just T, deducible
template<class T> int no_deduce(T, std::type_identity_t<T>) { return 2; }

int main() {
  return deduce(1) + no_deduce(1, 2.0) - 3;   // in no_deduce, T is deduced as int from the first argument only
}
```

After substitution `std::type_identity_t<T>` is `typename type_identity<T>::type`; `T` appears to the left of `::`, which is a non-deduced context ([[temp.deduct.type]]). So the second parameter doesn't take part in deduction, the argument `2.0` is simply converted to `int`, and it doesn't conflict with the first argument. This trick exists precisely to keep a parameter out of deduction.

## Dependent alias specializations are still substituted (¶3)

¶3 If a *template-id* is dependent, subsequent template argument substitution still applies to the *template-id*.

```cpp error
template<typename...> using void_t = void;
template<typename T> void_t<typename T::foo> f();
void test() {
  f<int>();   // error: int has no nested type foo
}
```

By ¶2, `void_t<typename T::foo>` is equivalent to `void`. If the compiler replaced it with `void` right away, the signature would lose `typename T::foo`, substituting `T = int` wouldn't fail, and `f<int>()` would be accepted. ¶3 requires the dependent *template-id* to be kept as is and its arguments substituted one by one, so the failure of `typename int::foo` is detected. In a function template signature, this is SFINAE:

```cpp run ok
template<typename...> using void_t = void;

template<class T> void_t<typename T::foo> f(int) { }   // viable only for types with T::foo
template<class T> void f(long) { }                     // fallback

struct HasFoo { using foo = int; };
int main() {
  f<HasFoo>(0);   // picks the first
  f<int>(0);      // substitution into the first fails, picks the second
}
```

!!! history "CWG1558"
    The original C++11 wording had no ¶3. When an alias doesn't use some of its arguments, it was unclear whether those arguments were substituted and could cause SFINAE, and compilers behaved differently. [[CWG1558]] added ¶3: in a dependent alias specialization, all arguments are substituted. Before that, the portable approach went through a class template to make sure the arguments were used:

    ```cpp
    template<class...> struct make_void { using type = void; };
    template<class... Ts> using void_t = typename make_void<Ts...>::type;
    ```

## No self-reference (¶4)

¶4 The definition of an alias template can't refer to the alias template being declared, and the type produced by an alias specialization can't directly or indirectly use that specialization itself.

```cpp error
template<class T> using Self = Self<T*>;   // error: Self isn't usable here yet

template<class T> struct A;
template<class T> using B = typename A<T>::U;
template<class T> struct A {
  typedef B<T> U;
};
B<short> b;   // error: B<short> uses itself through A<short>::U
```

The first is a direct reference: inside the alias's definition, `Self` isn't a usable name yet. The second is indirect: `B<short>` needs `A<short>::U`, which in turn is `B<short>`. For the second, Clang 23 already reports that `U` can't be found at the definition of `A`; the location differs from the standard's example, but it is rejected all the same.

An alias is just an expansion; unlike a class template, it can't break recursion with an incomplete type. Recursive structures like linked lists and trees must go through a class template.

## Lambdas in alias templates (¶5)

¶5 A lambda in an alias template declaration has a different type in different instantiations of the template, even if the lambda doesn't depend on template parameters.

```cpp run ok
#include <type_traits>
template<class T>
using A = decltype([] { });
static_assert(!std::is_same_v<A<int>, A<char>>);   // different closure types
int main() {}
```

This lambda doesn't depend on `T`, so it could be read either as one shared by all specializations or as a new one generated at each substitution. The standard chose the latter, consistent with how lambdas behave in function templates.

!!! lawyer "What about writing the same specialization twice?"
    ¶5 only says the types differ between different instantiations; it doesn't directly answer whether `A<int>` written twice is the same type. In Clang 23, `std::is_same_v<A<int>, A<int>>` is false: it treats every use as a new substitution. Don't rely on this behavior, and especially don't use aliases containing lambdas in function signatures ([[temp.over.link#5]]: lambdas are never equivalent).

## Alias templates and CTAD {{c++20}}

Note 1 says alias template names are never deduced, but C++20 allows class template argument deduction (CTAD, [[P1814R0]]) through alias templates, provided the alias's definition has the form of a class template specialization ([[dcl.type.class.deduct]]):

```cpp run ok
#include <memory>
#include <type_traits>
#include <vector>
template<class T> struct Alloc : std::allocator<T> { };
template<class T> using Vec = std::vector<T, Alloc<T>>;

Vec w{1, 2, 3};
static_assert(std::is_same_v<decltype(w), std::vector<int, Alloc<int>>>);
int main() {}
```

Starting from the deduction guides of `std::vector`, the compiler deduces the alias's definition against each guide's return type and generates deduction guides specific to the alias ([[over.match.class.deduct]]). This doesn't contradict Note 1: what is deduced is the alias's parameter `T`, not the alias being recognized in an existing type.

## No specialization

The grammar of alias declarations doesn't allow a *template-id*, so alias templates can be neither partially nor explicitly specialized ([[temp.decls#4]]). To choose by type, put the specialization on a class template and forward through the alias:

```cpp run ok
#include <type_traits>
template<class T> struct add_ptr_impl     { using type = T*; };
template<class T> struct add_ptr_impl<T&> { using type = T*; };   // specialization on the class template
template<class T> using add_ptr = typename add_ptr_impl<T>::type;

static_assert(std::is_same_v<add_ptr<int&>, int*>);
int main() {}
```

## Reflection sees the alias itself {{c++26}}

C++26 static reflection needs to distinguish the alias `Vec<int>` from the type it stands for: `^^Vec<int>` should reflect a type alias, which can be queried as an alias and have its name extracted, rather than reflecting `std::vector<int, Alloc<int>>` directly. So ¶2 excludes a *template-id* that is the operand of `^^` from the transparency rule and says it is the *typedef-name* of a type alias; if substitution fails when forming the type it stands for, the *template-id* is ill-formed ([[expr.reflect]]). Clang 23 doesn't support static reflection, so this part hasn't been verified by compilation.

## Implementation notes

!!! impl
    - Aliases don't appear in mangled names. `Vec<T>` in a signature is encoded as the substituted `std::vector<T, Alloc<T>>`; this is transparency at the ABI level.
    - Compiler diagnostics usually keep the alias spelling, e.g. `Vec<int>` (aka `std::vector<int, Alloc<int>>`). That's just for readability and has no semantic effect.

## History

!!! history
    - C++11 introduced alias templates ([[N2258]]).
    - [[CWG1558]] added ¶3 as a defect report; after that, the C++14 standard library provided the `std::xxx_t` aliases, and C++17 added `std::void_t`.
    - C++20 allowed CTAD through alias templates ([[P1814R0]]); lambdas became allowed in unevaluated operands, so ¶5 was needed to specify the type of a lambda in an alias.
    - C++26 static reflection made alias specializations that are operands of `^^` no longer transparent.

## Common misconceptions

!!! pitfall "You can overload on `Vec<T>` and `std::vector<T, Alloc<T>>`"
    They are the same type, and the two declarations are the same function template.

!!! pitfall "The template template parameter `TT = Vec` can be deduced from `std::vector<int, Alloc<int>>`"
    You can pass an alias template explicitly as a template template argument, but an alias template can't be deduced from a type.

!!! pitfall "`void_t<typename T::foo>` collapses to `void` immediately"
    A dependent alias specialization still has all its arguments substituted (¶3), and substitution failures are detected.

## Questions

!!! question "Question 1"
    Can the following call be deduced?

    ```cpp
    template<class T> using P = T*;
    template<class T> void f(P<T>);
    int x;
    f(&x);
    ```

<details markdown="1">
<summary>Answer</summary>

Yes, `T = int`. `P<T>` is equivalent to `T*`, so the parameter type of `f` is just `T*`, and `int*` deduces `T = int`. What can't be deduced is the alias template name itself, for example deducing `P` for some template template parameter. Deducing its arguments through the alias is fine, as long as `T` is still in a deducible position after substitution (compare `std::type_identity_t<T>`).
</details>

!!! question "Question 2"
    Under ¶3, is there any difference between these two `void_t`s?

    ```cpp
    template<class...> using void_t1 = void;
    template<class... Ts> struct make_void { using type = void; };
    template<class... Ts> using void_t2 = typename make_void<Ts...>::type;
    ```

<details markdown="1">
<summary>Answer</summary>

In dependent contexts they behave the same: the arguments of a dependent *template-id* are always substituted, so `void_t1<typename T::foo>` also fails substitution when `T::foo` doesn't exist. The only difference is that `void_t2` instantiates an extra class template. Before CWG1558, the C++11 wording allowed implementations to replace `void_t1<...>` with `void` directly and drop the unused arguments, and back then only `void_t2` could portably trigger SFINAE.
</details>
