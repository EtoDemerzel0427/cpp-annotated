---
title: Member relationships
summary: "Two constexpr functions: one tells whether a data member is pointer-interconvertible with objects of its class, the other whether two data members are at corresponding positions in a common initial sequence."
updated: 2026-10-19
---

!!! tldr
    - `is_pointer_interconvertible_with_class(&S::m)` tells whether `m` is the first data member of a standard-layout class `S`, i.e. whether `S*` and a pointer to the member can be converted to each other with `reinterpret_cast`.
    - `is_corresponding_member(&S1::m1, &S2::m2)` tells whether two members are at corresponding positions in the common initial sequence of two standard-layout structs.
    - They take member pointer values as arguments, so they are functions, not type traits.
    - The type of `&C::b` may be a member pointer of a base class, `int B::*`, and template argument deduction then deduces the base. When inheritance is involved, write the class template arguments explicitly.

These two functions come from [[P0466R5]], the same proposal as `is_layout_compatible` and `is_pointer_interconvertible_base_of` in [[meta.rel]]. They query two guarantees the core language gives standard-layout classes:

- [[g:pointer-interconvertible|Pointer-interconvertibility]] ([[basic.compound]]): two objects have the same address, and a pointer to one can be obtained from a pointer to the other with `reinterpret_cast`. An object of a standard-layout class is pointer-interconvertible with its first non-static data member; a union object is pointer-interconvertible with each of its non-static data members.
- [[g:common-initial-sequence|Common initial sequence]] ([[class.mem]]): the leading run of members of two standard-layout structs whose types are layout-compatible.

```cpp
template<class S, class M>
  constexpr bool is_pointer_interconvertible_with_class(M S::*m) noexcept;
template<class S1, class S2, class M1, class M2>
  constexpr bool is_corresponding_member(M1 S1::*m1, M2 S2::*m2) noexcept;
```

They ask about a property of one particular member, and the member has to be specified by a member pointer value; values cannot be type arguments of a type trait, so these are functions. They are `constexpr` rather than `consteval`, so they can be used in constant expressions and also evaluated at run time on a member pointer variable.

## Example

```cpp run title="corresponding.cpp"
#include <type_traits>
using std::is_corresponding_member;
using std::is_pointer_interconvertible_with_class;

struct Header { int tag; long len; };
struct Packet { int kind; long size; char payload[16]; };

static_assert( is_pointer_interconvertible_with_class(&Packet::kind));
static_assert(!is_pointer_interconvertible_with_class(&Packet::size));
static_assert( is_corresponding_member(&Header::len, &Packet::size));
static_assert(!is_corresponding_member(&Header::tag, &Packet::size));

int main() {}
```

`kind` is the first member of `Packet`; `size` is not. The common initial sequence of `Header` and `Packet` is the two members `int, long`; `len` and `size` are both in the second position, so they are corresponding members; `tag` and `size` are at different positions.

!!! impl "Cannot be verified with Clang 23"
    Neither Clang 23 nor libc++ implements these two functions: libc++ does not declare them, and Clang has no corresponding builtin. The examples on this page were not compiled in our tests, so they carry no verdict. GCC's libstdc++ does implement them; use the godbolt button to compare.

## `is_pointer_interconvertible_with_class`

¶1: `S` must be a complete type (*Mandates*).

¶2: returns `true` if and only if all of the following hold:

1. `S` is a standard-layout type;
2. `M` is an object type, i.e. `m` points to a data member, not a member function;
3. `m` is not a null member pointer;
4. every object `s` of type `S` is pointer-interconvertible with its subobject `s.*m`.

For a standard-layout struct, condition 4 is equivalent to `m` being the first non-static data member; for a union, any non-static data member qualifies. So this function can be seen as a precise version of `offsetof(S, m) == 0`: a member of a non-standard-layout class may also have offset 0, but then `reinterpret_cast` cannot be used to convert between the two.

The typical use is `container_of` in intrusive data structures: given a pointer to a member, compute a pointer to the enclosing object. Only when the member is pointer-interconvertible with the enclosing object does `reinterpret_cast<S*>(&member)` yield a pointer to that `S` object.

## `is_corresponding_member`

¶3: `S1` and `S2` must be complete types (*Mandates*).

¶4: returns `true` if and only if `S1` and `S2` are both standard-layout structs ([[class.prop]]), `M1` and `M2` are both object types, neither `m1` nor `m2` is null, and the two point to corresponding members in the common initial sequence of `S1` and `S2`.

Common initial sequences matter for unions. If the currently active member of a union is an object of type `S1`, the standard allows reading the values in the common initial sequence through a member of type `S2` ([[class.mem]]). `is_corresponding_member` lets you assert at compile time that two members really are at positions where such reads are allowed.

## A pitfall with inheritance

Note 1 in ¶5 points out that the type of the member pointer expression `&C::b` is not necessarily a member pointer of `C`. Per [[expr.unary.op]], if `b` is declared in a base class `B`, the type of `&C::b` is `int B::*` even when it is named through the derived class `C`. Template argument deduction ([[temp.deduct.call]]) then deduces `S` as `B`, not `C`.

Here is the standard's Example 1:

```cpp run title="member-of-base.cpp"
#include <type_traits>
using std::is_corresponding_member;
using std::is_pointer_interconvertible_with_class;

struct A { int a; };               // standard-layout
struct B { int b; };               // standard-layout
struct C : public A, public B {};  // not standard-layout

// &C::b has type int B::*, S is deduced as B, and b is B's first member
static_assert( is_pointer_interconvertible_with_class(&C::b));
// explicitly S = C: C is not standard-layout
static_assert(!is_pointer_interconvertible_with_class<C, int>(&C::b));

// what is actually compared is A::a with B::b
static_assert( is_corresponding_member(&C::a, &C::b));
static_assert(!is_corresponding_member<C, C, int, int>(&C::a, &C::b));

int main() {}
```

Both base classes of `C` have data members, so `C` is not a standard-layout class. Without template arguments, the first assertion actually asks about the first member of `B`, and the third compares the classes `A` and `B`, each with a single `int` member; both results are true. With `C` specified explicitly, `int B::*` is implicitly converted to `int C::*`, the question really concerns `C`, and the result is false.

When inheritance is involved, write the class template arguments explicitly; otherwise the question may not be about the class you think it is.

## Relation to reflection

C++26 static reflection ([[meta.reflection.queries]]) provides more general tools: for example, `std::meta::offset_of` gives a member's offset and `nonstatic_data_members_of` lists all data members, which together with a query for standard layout can express what the two functions on this page mean. These two functions, however, need no reflection and can also be used at run time.

## Questions

!!! question "Question"
    Given `union U { int i; float f; };`, what is the value of `std::is_pointer_interconvertible_with_class(&U::f)`? And of `std::is_corresponding_member(&U::i, &U::f)`?

<details markdown="1">
<summary>Answer</summary>

The former is `true`. A union is also a class, and `U` is a standard-layout type; per [[basic.compound]], a union object is pointer-interconvertible with each of its non-static data members, not just the first.

The latter is `false`. Paragraph 4 requires `S1` and `S2` to be standard-layout structs, i.e. standard-layout classes declared with `struct` or `class` ([[class.prop]]), which a union is not.
</details>
