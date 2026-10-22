---
title: Type equivalence
summary: "When two template-ids are the same type, function or variable: type arguments compare as types, constant arguments by template-argument-equivalence (integers by value, floating-point by identical bits, pointers by pointer value, class types subobject by subobject), and dependent decltype and pack indexing by expression equivalence."
updated: 2026-10-19
---

!!! tldr
    - `buffer<char, 2*512>` and `buffer<char, 1024>` are the same type: what is compared is the converted value of a constant argument, not the argument expression.
    - Constant arguments can only be the same if their types are the same, so under `template<auto V>`, `X<0>` and `X<0u>` are two types.
    - Floating-point arguments are compared bitwise: `0.0` and `-0.0` give different specializations, while a NaN gives the same specialization as itself.
    - Class-type arguments are compared subobject by subobject; a user-written `operator==` plays no part.
    - `decltype(t + 1)` and `decltype(1 + t)` are two different types in a function template signature, because the expressions are not equivalent.

## When two names are the same specialization (¶1)

```cpp run title="same-template-id.cpp" ok
#include <type_traits>

template<class E, int size> class buffer {};
static_assert(std::is_same_v<buffer<char, 2*512>, buffer<char, 1024>>);   // same value

template<int N> struct I {};
static_assert(std::is_same_v<I<'A'>, I<65>>);    // 'A' converted to int is 65

template<class T> struct X {};
template<class> struct Y {};
template<class T> using Z = Y<T>;
static_assert(std::is_same_v<X<Y<int>>, X<Z<int>>>);   // Z<int> is Y<int>
int main() {}
```

The same arguments must yield the same specialization; otherwise `std::vector<int>` could be two types in two translation units, and the ODR, linking and overloading would all fall apart.

¶1 Two *template-id*s are the same if all of the following hold, and the same *template-id* refers to the same class, function or variable:

- ¶1.1 their template names (or *operator-function-id*s or *literal-operator-id*s) refer to the same template;
- ¶1.2 their corresponding type template arguments are the same type;
- ¶1.3 the parameter values determined by their corresponding constant template arguments are **template-argument-equivalent** (see the next section);
- ¶1.4 their corresponding template template arguments refer to the same template.

¶1.3 compares the values after the arguments are converted to the parameter type ([[temp.arg.nontype]]), so `2*512` and `1024`, or `'A'` and `65`, make no difference. A specialization of an alias template is the substituted type ([[temp.alias]]), so `Z<int>` is not a specialization of another template, and the argument of `X<Z<int>>` is simply `Y<int>`.

¶3 is the standard's example. Besides `buffer` and the alias template above, it has a group of function-pointer arguments: `list<int, &h2>` is the same type as `list<int, &h2>`, and a different type from `list<int, &h1>` (different function) or `list<char, &h2>` (different type argument).

## Template-argument-equivalence (¶2)

¶2 Two values are **template-argument-equivalent** ([[g:template-argument-equivalent]]) if they are of the same type and, depending on the type, meet the condition in this table:

| Item | Type | Equivalent when |
|---|---|---|
| ¶2.1 | integral | they have the same value |
| ¶2.2 | floating-point | the values are identical (not `==`) |
| ¶2.3 | `std::nullptr_t` | always |
| ¶2.4 {{c++26}} | `std::meta::info` | they compare equal with `==` ([[expr.eq]]) |
| ¶2.5 | enumeration | they have the same value |
| ¶2.6 | pointer | they have the same pointer value |
| ¶2.7 | pointer-to-member | they refer to the same class member or are both the null member pointer value |
| ¶2.8 | reference | they refer to the same object or function |
| ¶2.9 | array | corresponding elements are either both within their lifetimes and equivalent, or both not within their lifetimes |
| ¶2.10 | union | neither has an active member, or they have the same active member and its values are equivalent |
| ¶2.11 | closure | always |
| ¶2.12 | class | corresponding direct subobjects and reference members are equivalent |

The same type is a precondition in every case. Under `template<auto V>`, the type of `V` is deduced from the argument, so `X<1>` and `X<1L>` (`int` and `long`), or `X<0>` and `X<false>`, are different specializations.

### Floating-point: identical bits, not `==` (¶2.2)

```cpp run title="float-identical.cpp" ok
#include <limits>
#include <type_traits>

template<double D> struct F {};
constexpr double nan = std::numeric_limits<double>::quiet_NaN();

static_assert(!std::is_same_v<F<0.0>, F<-0.0>>);   // equal but not identical
static_assert( std::is_same_v<F<nan>, F<nan>>);    // not equal but identical
static_assert(!std::is_same_v<F<nan>, F<-nan>>);   // different sign bit
int main() {}
```

Identical means the two values have exactly the same representation. `0.0 == -0.0` is true, but the two are not identical; `nan == nan` is false, but a NaN is identical to itself.

Type identity must be an equivalence relation; at the very least every value must be the same as itself. Floating-point `==` fails this for NaN, and it also merges `+0.0` and `-0.0`, two values that can be told apart. If `F<0.0>` and `F<-0.0>` were the same type, whether `1.0 / D` inside it is positive or negative infinity would depend on which translation unit instantiated it first.

### Enumerations: by value (¶2.5)

```cpp run title="enum-value.cpp" ok
#include <type_traits>
enum E { a = 1, b = 1 };
template<E e> struct Q {};
static_assert(std::is_same_v<Q<a>, Q<b>>);   // a and b both have value 1
int main() {}
```

Footnote 105 explains that the identity of the enumerator itself is not preserved. Two enumerators with the same value give the same specialization.

### Pointers: by pointer value (¶2.6)

```cpp run title="pointer-value.cpp" ok
#include <type_traits>
struct S { int a[2]; int b; } s;
template<int* p> struct P {};

// &s.a[2] points past the end of s.a, &s.b points to s.b. The addresses may be equal; the pointer values differ
static_assert(!std::is_same_v<P<&s.a[2]>, P<&s.b>>);
int main() {}
```

¶2.6 compares pointer values ([[basic.compound]]), not addresses. A pointer to an object and a pointer past the end are different pointer values, even if the addresses are numerically equal.

### Closure types: same type means equivalent (¶2.11)

```cpp run title="closure.cpp" ok
#include <type_traits>
template<auto L> struct Lam {};

constexpr auto l1 = [] {};
constexpr auto l2 = l1;                     // same closure type
static_assert(std::is_same_v<Lam<l1>, Lam<l2>>);
static_assert(!std::is_same_v<Lam<[] {}>, Lam<[] {}>>);   // two different closure types
int main() {}
```

A closure that can be used as a constant argument has no captures, so it has no data members to compare, and values of the same closure type are always equivalent. But every lambda-expression has its own closure type, so two lambda-expressions fail the same-type precondition.

### Class types: subobject by subobject (¶2.12)

```cpp run title="class-equiv.cpp" ok
#include <type_traits>
struct V {
    int v;
    constexpr bool operator==(const V&) const { return true; }   // claims everything is equal
};
template<V v> struct VV {};
static_assert(!std::is_same_v<VV<V{1}>, VV<V{2}>>);   // still compared by member v: different
int main() {}
```

¶2.12 reduces equivalence of class types to equivalence of each direct subobject (base class subobjects and non-static data members) and each reference member. A user-defined `operator==` plays no part at all, because type identity can't depend on user-written code that might not be consistent.

The original C++20 design required class-type arguments to have a defaulted `operator==` and used it to decide equivalence; [[P1907R1]] replaced that with today's member-wise recursive definition, decoupled from `operator==`.

### Arrays and unions (¶2.9–¶2.10)

```cpp run title="union-equiv.cpp" ok
#include <type_traits>
union U { int i; float f; };
template<U u> struct UU {};
static_assert(!std::is_same_v<UU<U{.i = 0}>, UU<U{.f = 0.0f}>>);   // different active member
static_assert( std::is_same_v<UU<U{.i = 0}>, UU<U{.i = 0}>>);
int main() {}
```

Unions compare their active member: two values with different active members are not equivalent, even if every bit of the object representation is the same.

Arrays are compared element by element, taking lifetime into account: two elements are either both within their lifetimes and equivalent, or both not within their lifetimes. A template parameter of array type is adjusted to a pointer (footnote 106, [[temp.param#15]]), so ¶2.9 mainly applies to array members of class-type arguments.

## Dependent decltype and pack indexing (¶4–¶6)

```cpp title="decltype-identity.cpp" error
template<class T> auto f(T t) -> decltype(t + 1);
template<class T> auto f(T t) -> decltype(t + 1) { return t + 1; }   // redeclaration: equivalent expressions
template<class T> auto f(T t) -> decltype(1 + t) { return 1 + t; }   // another function template

int x = f(1);   // error: ambiguous, the two function template specializations have the same signature
```

¶4 If an expression `e` is type-dependent (depends on template parameters), `decltype(e)` denotes a unique dependent type. Two such `decltype`s are the same type only if their expressions are equivalent ([[temp.over.link]]). Note 1 adds that such a type can be given a typedef name.

So in the example above, `decltype(t + 1)` and `decltype(1 + t)` yield the same type for every `T`, yet at the template level they are two types, and the third line declares a new function template. At the call the two specializations have the same signature and partial ordering can't tell them apart, so the call is ambiguous.

The compiler can't compute `decltype(t + 1)` first and then compare, because `T` is unknown at the template definition, and deciding whether two declarations declare the same function template has to be done there.

¶5 {{c++26}} Pack indexing `T...[N]` ([[dcl.type.pack.index]]) works the same way: for a type template parameter pack `T`, `T...[N]` denotes a unique dependent type. Two such types are the same if they index the same parameter pack and their indices are the same: if neither index is value-dependent, their values are compared; otherwise the index expressions must be equivalent.

```cpp run title="pack-index.cpp" ok
template<class... Ts>
struct L {
    using first     = Ts...[0];
    using alsofirst = Ts...[1 - 1];   // indices are not value-dependent and both are 0: same type
};
static_assert(__is_same(L<int, char>::first, L<int, char>::alsofirst));
int main() {}
```

¶6 There is a parallel rule for the template-name pack index, *pack-index-template-name* (taking the Nth template from a template template parameter pack, [[temp.names]]). This wording is newer than C++26's type pack indexing.

## Implementation notes

!!! impl "The mangled name is the identity"
    Under the Itanium ABI, whether two specializations are the same ultimately shows up as whether their mangled names are the same, and each equivalence rule has a counterpart in the encoding rules: integers are encoded by value; floating-point values by bit pattern, so `±0` and different NaNs are naturally distinguished; class types recursively by member; pointers as the entity pointed to plus the subobject path. The mangled name of a closure type includes the lambda's ordinal in its enclosing context, so different lambda-expressions have different mangled names.

## Common misconceptions

!!! pitfall "Class-type arguments are compared with `operator==`"
    They are compared member by member (¶2.12), whatever `operator==` says.

!!! pitfall "`0.0 == -0.0`, so `F<0.0>` and `F<-0.0>` are the same"
    They are different types (¶2.2).

!!! pitfall "Two pointer arguments with the same address are the same"
    Pointer values are compared; a past-the-end pointer is different from a pointer to the next object that happens to be there (¶2.6).

!!! pitfall "`decltype(a + b)` and `decltype(b + a)` are interchangeable in a function template signature"
    They aren't; they are different dependent types (¶4). Declarations and definitions must correspond token for token.

## Questions

!!! question "Question 1"
    With `template<auto V> struct X {};`, how many different types are `X<0>`, `X<0u>`, `X<'\0'>`, `X<false>` and `X<nullptr>`?

<details markdown="1">
<summary>Answer</summary>

Five. The type of `V` is deduced as `int`, `unsigned`, `char`, `bool` and `std::nullptr_t` respectively; the types differ, so the precondition for equivalence isn't met.
</details>

!!! question "Question 2"
    ```cpp
    struct A { int x; int& r; };
    int g1, g2;
    template<A a> struct T {};
    ```
    Are `T<A{1, g1}>` and `T<A{1, g2}>` the same? What about `T<A{1, g1}>` and `T<A{1, g1}>`?

<details markdown="1">
<summary>Answer</summary>

The first pair is different: the reference member `r` refers to `g1` in one and `g2` in the other, and ¶2.8 requires them to refer to the same object. The second pair is the same. Reference members are compared by which object they refer to, not by the object's value, so even if `g1 == g2` the first pair differs.
</details>
