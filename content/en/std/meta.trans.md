---
title: Transformations between types
summary: "The basic traits that turn one type into another: adding and removing top-level cv, adding and removing references, changing the signedness of integers, removing array dimensions, adding and removing pointers."
updated: 2026-10-19
---

!!! tldr
    - `remove_const` and friends remove only top-level cv: `remove_const_t<const int*>` is unchanged, and so is `remove_const_t<const int&>`.
    - `add_lvalue_reference` and `add_rvalue_reference` follow reference collapsing and return non-referenceable types such as `void` unchanged; `declval` relies on exactly this.
    - For enumerations and character types, `make_unsigned` picks the integer type of lowest rank by `sizeof`, so an enumeration with underlying type `long long` gets `unsigned long` on LP64.
    - `remove_pointer` does not recognize member pointers; `add_pointer` removes a reference first and then adds the pointer.

The templates in [meta.trans] take a type and produce another one by fixed rules ([meta.trans.general] paragraph 1). Each is a **transformation trait** (*Cpp17TransformationTrait*, [[meta.rqmts]]): the result is in the nested `type`, and a `_t` alias gives the result directly; for example, `remove_const_t<T>` is `typename remove_const<T>::type`.

This page covers five groups of transformations with simple rules; the only difficulties are at the boundary types: references, function types, arrays and `void`. More complex transformations such as `decay`, `common_type` and `invoke_result` are in [[meta.trans.other]].

## cv modifications [meta.trans.cv]

```cpp run title="cv-mods.cpp" ok
#include <type_traits>
using namespace std;

static_assert(is_same_v<remove_const_t<const volatile int>, volatile int>);
static_assert(is_same_v<remove_const_t<const int*>, const int*>);
static_assert(is_same_v<remove_const_t<const int* const>, const int*>);
static_assert(is_same_v<remove_const_t<const int&>, const int&>);
static_assert(is_same_v<remove_const_t<const int[3]>, int[3]>);
static_assert(is_same_v<add_const_t<int&>, int&>);
static_assert(is_same_v<add_const_t<void()>, void()>);
static_assert(is_same_v<add_cv_t<int>, const volatile int>);

int main() {}
```

`remove_const`, `remove_volatile` and `remove_cv` remove [[g:top-level-cv-qualifiers|top-level cv-qualifiers]], i.e. the cv that qualifies the type itself directly. The `const` in `const int*` qualifies the pointed-to `int` and is not at the top level, so `remove_const_t<const int*>` is unchanged; the trailing `const` in `const int* const` qualifies the pointer itself and is the one removed.

A reference itself cannot be cv-qualified; the `const` in `const int&` belongs to the referenced `int` and is not at the top level either. So `remove_const` does nothing to reference types. To remove the cv behind a reference, apply `remove_reference_t` first, or use `remove_cvref_t` directly ([[meta.trans.other]]).

Arrays are another special case. Per [[basic.type.qualifier]], a cv-qualified array type is an array of cv-qualified elements, so the top-level cv of `const int[3]` is the elements' cv, and `remove_const_t<const int[3]>` is `int[3]`.

`add_const<T>` gives `const T`, and likewise `add_volatile` and `add_cv`. cv on references and function types is ignored, so `add_const_t<int&>` is still `int&` (Notes 1 and 2).

## Reference modifications [meta.trans.ref]

```cpp run title="ref-mods.cpp" ok
#include <type_traits>
#include <utility>
using namespace std;

static_assert(is_same_v<remove_reference_t<int&&>, int>);
static_assert(is_same_v<add_lvalue_reference_t<int&&>, int&>);
static_assert(is_same_v<add_rvalue_reference_t<int&>, int&>);
static_assert(is_same_v<add_lvalue_reference_t<void>, void>);
static_assert(is_same_v<add_lvalue_reference_t<void() &>, void() &>);
static_assert(is_same_v<decltype(declval<int>()), int&&>);
static_assert(is_same_v<decltype(declval<void>()), void>);

int main() {}
```

`remove_reference<T>` gives the referenced type if `T` is a reference, and `T` otherwise.

`add_lvalue_reference<T>` gives `T&` and `add_rvalue_reference<T>` gives `T&&`, with the result following [[g:reference-collapsing|reference collapsing]] ([[dcl.ref]]): if either side is an lvalue reference, the result is an lvalue reference. So `add_rvalue_reference_t<int&>` is `int&`, not an rvalue reference (Note 2).

These two templates add references only to [[g:referenceable-type|referenceable types]]. The non-referenceable types are `void` and function types with cv- or ref-qualifiers (such as `void() const`, which can only appear in the declaration of a member function). For them, the result is `T` itself rather than a compile error.

The declaration of `declval` makes use of this:

```cpp
template<class T> add_rvalue_reference_t<T> declval() noexcept;
```

So `declval<int>()` has type `int&&` and is an xvalue; `declval<int&>()` has type `int&` and is an lvalue; `declval<void>()` has type `void` and can still be written. The hypothetical expressions built with `declval` in [[meta.unary.prop]] and [[meta.rel]] all depend on these value categories.

## Sign modifications [meta.trans.sign]

`make_signed<T>` checks three rules in order, and `make_unsigned` is symmetric:

1. If `T` is already a signed integer type (possibly cv-qualified), the result is `T` itself.
2. If `T` is an unsigned integer type, the result is the corresponding signed integer type ([[basic.fundamental]]), with the same cv.
3. Otherwise, the result is the signed integer type with the lowest [[conv.rank|integer conversion rank]] for which `sizeof(T) == sizeof(type)`, with the same cv.

`T` must be an integral or enumeration type other than `bool`, or the program is ill-formed (*Mandates*).

```cpp run title="make-signed.cpp" ok
#include <type_traits>
using namespace std;

enum EL : long long {};
using CVU = const volatile unsigned char;

static_assert(is_same_v<make_signed_t<char>, signed char>);
static_assert(is_same_v<make_unsigned_t<char>, unsigned char>);
static_assert(is_same_v<make_signed_t<char16_t>, short>);
static_assert(is_same_v<make_signed_t<CVU>,
                        const volatile signed char>);
static_assert(is_same_v<make_unsigned_t<long long>,
                        unsigned long long>);
static_assert(is_same_v<make_unsigned_t<EL>, unsigned long>);  // LP64

int main() {}
```

Rule 3 applies to character types and enumerations. `char`, `signed char` and `unsigned char` are three distinct types; `char` counts as neither a signed nor an unsigned integer type, so it falls under rule 3 and yields `signed char` of the same size.

The result for enumerations can be surprising. `EL`'s underlying type is `long long`, but rule 3 only looks at size: on LP64 platforms `unsigned long` and `unsigned long long` are both 8 bytes, and the former has lower rank, so `make_unsigned_t<EL>` is `unsigned long`. To get the unsigned version of the underlying type, write `make_unsigned_t<underlying_type_t<E>>`.

!!! lawyer "Enumerations whose underlying type is `bool`"
    The *Mandates* only excludes `bool` itself. `enum class EB : bool {};` is an enumeration type, and read literally it seems allowed, with rule 3 giving `signed char`. Clang's builtin `__make_signed`, however, rejects it, reporting that the underlying type of `EB` is `bool`. This is a place where the implementation is stricter than the wording.

!!! impl "Extended integer types"
    libc++ uses Clang's builtins `__make_signed` and `__make_unsigned` directly. In our tests, `make_unsigned_t<__int128>` is `unsigned __int128` and `make_signed_t<unsigned _BitInt(7)>` is `_BitInt(7)`; extended integer types are handled correctly too.

## Array modifications [meta.trans.arr]

`remove_extent<T>` gives `U` if `T` is an array of `U`, and `T` otherwise. For multidimensional arrays only the first dimension is removed; for an array of `const U`, removing the dimension gives `const U` (Note 1). `remove_all_extents<T>` removes all dimensions. Both support arrays of unknown bound:

```cpp run title="extents.cpp" ok
#include <type_traits>
using namespace std;

static_assert(is_same_v<remove_extent_t<int>, int>);
static_assert(is_same_v<remove_extent_t<int[2][3]>, int[3]>);
static_assert(is_same_v<remove_extent_t<int[][3]>, int[3]>);
static_assert(is_same_v<remove_extent_t<const int[2][3]>,
                        const int[3]>);
static_assert(is_same_v<remove_all_extents_t<int[][3]>, int>);

int main() {}
```

The two examples in paragraphs 2 and 3 of [meta.trans.arr] are these assertions. `remove_all_extents_t` is commonly used in [[meta.unary.prop]] to get the element type of an array, for example in the precondition "`remove_all_extents_t<T>` shall be a complete type".

## Pointer modifications [meta.trans.ptr]

```cpp run title="ptr-mods.cpp" ok
#include <type_traits>
using namespace std;

struct S;
static_assert(is_same_v<remove_pointer_t<int* const>, int>);
static_assert(is_same_v<remove_pointer_t<int**>, int*>);
static_assert(is_same_v<remove_pointer_t<void (S::*)()>,
                        void (S::*)()>);
static_assert(is_same_v<add_pointer_t<int&&>, int*>);
static_assert(is_same_v<add_pointer_t<int[3]>, int (*)[3]>);
static_assert(is_same_v<add_pointer_t<int(int)>, int (*)(int)>);
static_assert(is_same_v<add_pointer_t<void() const>, void() const>);
static_assert(is_same_v<add_pointer_t<const void>, const void*>);

int main() {}
```

`remove_pointer<T>` gives `T1` if `T` is a pointer to `T1` (the pointer itself may be cv-qualified), and `T` otherwise. It removes only one level, and does not recognize member pointers, because member pointers are not pointer types ([[basic.compound]]).

`add_pointer<T>` gives `remove_reference_t<T>*` if `T` is referenceable or is `void`, and `T` otherwise. There are no pointers to references, so it removes the reference first. For function types it gives a function pointer, for arrays a pointer to array. A function type like `void() const` is neither referenceable nor `void`, has no corresponding pointer type, and is returned unchanged.

!!! impl "`_t` aliases do not instantiate class templates"
    libc++ forwards all these transformations to Clang's type transformation builtins, such as `__remove_cv(T)` and `__add_pointer(T)`. Its `remove_cv_t<T>` is defined directly as `__remove_cv(T)`, without going through `remove_cv<T>::type`. The standard only requires the two to be the same type, not that the `_t` alias instantiate the class template. Generic code that uses `_t` aliases heavily saves many class template instantiations this way.

## Pitfalls

!!! pitfall "`remove_const` on a forwarding reference"
    In `template<class T> void f(T&& x)`, if the argument is a `const int` lvalue, `T` is deduced as `const int&`, and `remove_const_t<T>` is still `const int&`. Use `remove_cvref_t<T>`.

## Questions

!!! question "Question"
    What are the types `std::add_pointer_t<int(&)(int)>` and `std::remove_pointer_t<int (*const*)(int)>`?

<details markdown="1">
<summary>Answer</summary>

The first is `int (*)(int)`: `add_pointer` first removes the reference to get the function type `int(int)`, then adds a pointer.

The second is `int (*const)(int)`: the original type is a pointer to a const function pointer; `remove_pointer` removes only the outermost pointer, leaving the pointed-to type, which itself carries a top-level `const`.
</details>

## Summary

| Group | Rule | Edge cases |
|---|---|---|
| cv | Only touches top-level cv | An array's cv is its elements' cv; references and function types have no top-level cv |
| References | Follow reference collapsing | Non-referenceable types are returned unchanged |
| Sign | Unchanged if already; the corresponding type if there is one; otherwise the lowest rank of the same size | `char` and enumerations take rule 3; `bool` is ill-formed |
| Arrays | `remove_extent` removes one level, `remove_all_extents` removes all | Arrays of unknown bound supported |
| Pointers | `remove_pointer` removes one level; `add_pointer` removes references first | Member pointers are not pointers; non-referenceable function types are returned unchanged |
