---
title: Relational and equality operators
summary: "Which operands < > <= >= and == != accept; pointer < is guaranteed only for elements of the same array and members of the same object, and is unspecified otherwise; == compares addresses, with an exception for past-the-end pointers and adjacent objects; pointers to members can only be compared for equality; since C++26 two arrays cannot be compared directly."
updated: 2026-10-19
---

!!! tldr
    - `a < b < c` is `(a < b) < c`, and likewise `a == b == c`; arithmetic operands first undergo the usual arithmetic conversions, so `-1 < 1u` is false.
    - For pointers, `<` only guarantees ordering by index within the same array and by member declaration order within the same object; `<` on unrelated pointers gives an unspecified result (not UB), and when you need a total order, use `std::less<T*>`.
    - Pointer `==` compares addresses and almost always has a definite result. The only exception is comparing the past-the-end pointer of one object with the address of another complete object, which gives an unspecified result.
    - Pointers to members can only be compared with `==` and `!=`; when a virtual member function is involved, or the members come from two classes neither of which is a base of the other, the result is unspecified.
    - Since C++26 two arrays cannot be compared directly, and `"abc" == "abc"` is ill-formed too; to compare addresses, decay the arrays first with unary `+`.

[[expr.rel]] specifies `<`, `>`, `<=` and `>=`, and [[expr.eq]] specifies `==` and `!=`. For arithmetic types both are simple; what needs careful reading is the comparison of pointers and pointers to members.

## Relational operators [expr.rel]

### Left-to-right grouping (¶1)

```cpp run title="rel-chain.cpp" ok flags="-std=c++2c -Wno-error=parentheses"
int main() {
    int a = 5, b = 3, c = 2;
    bool x = a < b < c;    // (5 < 3) < 2, i.e. false < 2, i.e. 0 < 2
    return x ? 0 : 1;      // x is true, even though 5 < 3 < 2 is mathematically false
}
```

¶1 The relational operators group left-to-right. Example 1 in the standard makes a point of it: `a<b<c` means `(a<b)<c`, not `(a<b)&&(b<c)`.

By the standard this program is well-formed. But Clang 23 treats it as an error by default: "chained comparison 'X < Y < Z' does not behave the same as a mathematical expression [-Wparentheses]"; it takes `-Wno-error=parentheses` to downgrade it to a warning, and the godbolt button above already includes that option. This is an example of a compiler rejecting well-formed code for practical reasons; if you really need this form, write `(a < b) < c`.

### Which operands are allowed (¶1–¶3)

```cpp title="rel-operands-bad.cpp" error
struct S { int m; };
enum E1 { e1 };
enum E2 { e2 };

void f(int* p, long* q, int S::* pm) {
    bool a = p < q;              // error: int* and long* have no composite pointer type
    bool b = p < 0;              // error: a pointer cannot be ordered against an integer, not even 0
    bool c = nullptr < nullptr;  // error: nullptr_t is not a pointer type
    bool d = pm < pm;            // error: pointers to members cannot be ordered
    bool e = e1 < e2;            // error: two different enumeration types (since C++26)
    bool g = e1 < 1.5;           // error: enumeration and floating-point (since C++26)
}
```

¶1 The operands first undergo the lvalue-to-rvalue and function-to-pointer conversions. The array-to-pointer conversion is applied only when the other operand is a pointer, so two arrays cannot be compared; see below.

¶2 The converted operands must have arithmetic, enumeration or pointer type, and the result has type `bool`. `std::nullptr_t`, pointers to members, and class types without overloaded comparisons cannot be compared with the relational operators.

¶3 Arithmetic and enumeration operands undergo the usual arithmetic conversions ([[expr.arith.conv]]). When both are pointers, pointer conversions ([[conv.ptr]]), function pointer conversions ([[conv.fctptr]]) and qualification conversions ([[conv.qual]]) bring them to their **composite pointer type** ([[expr.type]]), i.e. the common pointer type both can convert to. After conversion the two sides must have the same type.

There is no such common type between `int*` and `long*`, so they cannot be compared. Early standards allowed ordering a pointer against a null pointer constant; C++14 removed that, because asking whether a pointer is less than a null pointer makes no sense. Comparisons between different enumerations, and between an enumeration and a floating-point type, were deprecated in C++20 by [[P1120R0]] and made ill-formed in C++26 ([[diff.cpp23.expr]]).

The old problem caused by the usual arithmetic conversions is still there:

```cpp run title="rel-signed-unsigned.cpp" ok
int main() {
    int i = -1;
    unsigned u = 1;
    bool r = i < u;    // false: i is converted to unsigned, with value UINT_MAX
    return r ? 1 : 0;  // returns 0
}
```

`-Wsign-compare`, included in `-Wextra`, warns on this line. With `<=>` this comparison is simply ill-formed ([[expr.spaceship#4]]); C++20's `std::cmp_less` and related functions ([[utility.intcmp]]) give the mathematically correct result.

### The partial order on pointers (¶4)

```cpp run title="rel-partial-order.cpp" ok
struct Inner { int x, y; };
struct S {
    int a;
    Inner in;
    int b;
};

constexpr bool test() {
    int arr[4]{};
    S s{};
    return &arr[1] < &arr[3]          // ¶4.1: same array, the higher index compares greater
        && &arr[3] < arr + 4          // the past-the-end pointer is treated as hypothetical element 4
        && &s.a < &s.b                // ¶4.2: the later-declared member compares greater
        && &s.a < &s.in.y             // ¶4.2: applies recursively to subobjects of members
        && &s.in.x < &s.in.y;
}
static_assert(test());

int main() {}
```

¶4 The result of comparing unequal object pointers is determined by a **partial order** consistent with the following rules:

- ¶4.1 If they point to different elements of the same array (or subobjects thereof), the pointer to the element with the higher subscript must compare greater.
- ¶4.2 If they point to different non-static data members of the same object (or subobjects of such members, recursively), the pointer to the later-declared member must compare greater, provided neither member is a subobject of zero size and the class is not a union.
- ¶4.3 Otherwise, neither pointer is required to compare greater than the other.

Footnote 59 follows the convention of [[expr.add]]: an object that is not an array element is treated as a 1-element array, and a past-the-end pointer is treated as hypothetical element *n*. So `p < a + n` always makes sense for a `p` within the array `a`, which is what makes `for (p = a; p < a + n; ++p)` valid.

Both exceptions in ¶4.2 have reasons. A subobject of zero size, such as an empty member marked `[[no_unique_address]]` ([[intro.object]]), may share its address with other members. All members of a union have the same address ([[class.union]]), so there is no before or after.

!!! history "Member order and access control"
    From C++11 to C++20, item 4.2 also required both members to have the same access control, because implementations were then allowed to reorder members in different access sections (`public:`, `private:`). C++23's [[P1847R4]] removed that permission, which no implementation had actually used, and the condition here went with it.

### Unspecified results in all other cases (¶5–¶6)

¶5 translates the partial order into the results of the four operators. If `p` and `q` are equal (per [[expr.eq]]), `<=` and `>=` yield true and `<` and `>` yield false. Otherwise, if the partial order says `p` is greater than `q`, the four operators give the corresponding results. **Otherwise, the result of each operator is unspecified.**

Note 1 adds two points: relational comparison of unequal function pointers gives an unspecified result, because functions are neither array elements nor members; and since a `void*` can point to an object, comparing elements of the same array through `void*` is also covered by paragraph 4.

Unspecified is not UB. Comparing the addresses of two unrelated objects still gives a meaningful program, just not a portable answer. But in constant evaluation, a comparison with an unspecified result stops the expression from being a constant expression ([[expr.const.core]] ¶2.28):

```cpp title="rel-unrelated-const.cpp" error
int x, y;
bool rt = &x < &y;                     // OK: at run time, unspecified result
constexpr bool ct = &x < &y;           // error: unspecified result, not a constant expression
```

¶6 For arithmetic and enumeration operands, the result is `true` if the relation holds and `false` otherwise. No relation holds when a NaN is involved, so `NaN < 1` and `NaN >= 1` are both `false`.

### The total order of `std::less`

Given that `<` on unrelated pointers is unspecified, how does `std::set<T*>` work? The answer is in the library: function objects such as `std::less<T*>` use an implementation-defined **strict total order** on pointers ([[comparisons.general#2]], [[defns.order.ptr]]), consistent with the partial order of the built-in operators. On a flat address space the implementation just compares addresses.

```cpp run title="rel-std-less.cpp" ok
#include <functional>
#include <set>

int main() {
    int x = 0, y = 0;
    std::less<int*> lt;
    bool a = lt(&x, &y), b = lt(&y, &x);
    std::set<int*> s{&x, &y};       // relies on the total order of std::less<int*>
    return (a != b && s.size() == 2) ? 0 : 1;   // exactly one of a and b is true
}
```

So generic code that orders pointers should use `std::less` or `std::ranges::less`, not `<`.

### Two arrays cannot be compared {{removed:C++26}}

```cpp title="rel-array-compare.cpp" error
int a1[3], a2[3];

bool e1 = a1 == a2;          // error: ill-formed since C++26
bool e2 = a1 < a2;           // error: likewise
bool e3 = "abc" == "abc";    // error: two string literals are also two arrays
```

In C++23 and earlier, comparing two arrays decayed both to pointers and compared addresses rather than contents, which was almost never what the author wanted. C++20 deprecated such comparisons through [[P1120R0]], and C++26 removed them through [[P2865]]: the array-to-pointer conversion is applied only when the other operand is a pointer (or, for `==` and `!=`, a null pointer constant).

When you really want to compare addresses, use unary `+` to decay the array first:

```cpp run title="rel-array-compare-ok.cpp" ok
int a1[3], a2[3];

bool p1 = a1 == +a2;         // OK: compares addresses, result is false
bool p2 = +a1 < +a2;         // OK: compares addresses, result is unspecified
int* p = a1;
bool p3 = p == a1;           // OK: one side is a pointer, so the array decays
bool p4 = a1 == nullptr;     // OK: for ==, a null pointer constant also triggers decay; always false

int main() { return (p3 && !p1) ? 0 : 1; }
```

It is a good thing that `"abc" == "abc"` is ill-formed in C++26: it never compared contents, and whether two identical literals are the same object is itself unspecified (see below). To compare string contents, use `std::string_view` or `std::strcmp`.

## Equality operators [expr.eq]

### Which operands are allowed (¶1–¶3)

¶1 `==` and `!=` also group left-to-right, so `a == b == c` is likewise a trap. The operands first undergo the lvalue-to-rvalue and function-to-pointer conversions; if one operand is a pointer or a null pointer constant, the array-to-pointer conversion is applied to the other. Compared with the relational operators, the null pointer constant is the extra case, so `arr == nullptr` is valid, just always `false`, and Clang warns about it.

¶2 The converted operands must have scalar type ([[basic.types.general]]): arithmetic, enumeration, pointer, pointer to member, `std::nullptr_t`, and, in C++26, `std::meta::info`. The result is `bool`. Every case below requires both sides to have the same type after conversion.

¶3 Any two pointer values, or any two pointer-to-member values, are either equal or unequal; there is no case where they cannot be compared. Note 1 adds that as long as neither is an invalid pointer value, repeated comparisons give consistent results. An **invalid pointer value** is a pointer whose storage has been deallocated, such as a pointer after `delete`; comparing it has implementation-defined behavior ([[basic.compound#6]]).

### Pointer equality (¶4)

```cpp run title="eq-same-address.cpp" ok
struct Empty {};
struct S { int a; double b; };
struct D : Empty { int x; };

constexpr bool test() {
    S s{};
    D d{};
    return static_cast<void*>(&s) == static_cast<void*>(&s.a)   // object and first member share an address
        && static_cast<void*>(&d) == static_cast<void*>(static_cast<Empty*>(&d));  // empty base class subobject
}
static_assert(test());

int main() {}
```

¶4 If at least one operand is a pointer, both are first converted to the composite pointer type, and then:

- ¶4.1 If one pointer represents the address of a complete object and the other represents the address one past the end of a different complete object, the result is unspecified.
- ¶4.2 Otherwise, they compare equal if both are null, both point to the same function, or both represent the same address.
- ¶4.3 Otherwise they compare unequal.

The criterion in ¶4.2 is representing the same address, not pointing to the same object. So in the example above, pointers to different objects that have the same address compare equal.

### Past-the-end pointers and adjacent objects (¶4.1)

```cpp title="eq-past-end.cpp" unspecified
#include <cstdio>

int main() {
    int a = 0, b = 0;
    int* p = &a + 1;     // past-the-end pointer of a
    int* q = &b;
    // if b happens to come right after a, p and q represent the same address
    std::printf("%d\n", p == q);   // unspecified: may be 0, may be 1
}
```

Why is this comparison in particular unspecified? Compilers rely on a pointer's **provenance** in alias analysis: `p` is computed from `&a`, so it cannot point to `b`. GCC and other compilers do fold such comparisons to `false` at compile time on that basis, while at run time the two addresses may in fact be the same. If the standard required equal addresses to compare equal, this optimization would be a compiler bug. Making it unspecified amounts to acknowledging that address and provenance are two different things.

Correspondingly, Note 2 of [[basic.compound#3]] says a past-the-end pointer does not count as pointing to an unrelated object that happens to be at that address. Even if `p == q` is true, you cannot access `b` through `p`.

In constant evaluation this comparison is likewise not a constant:

```cpp title="eq-past-end-const.cpp" error
int a, b;
constexpr bool r = &a + 1 == &b;   // error: unspecified result
```

Clang's explanation is "comparison against pointer '&a + 1' that points past the end of a complete object has unspecified value".

### Function pointers and string literals

¶4.2 says pointers to the same function compare equal; conversely, pointers to different functions must compare unequal. The linker's identical code folding (ICF) conflicts with this: MSVC's `/OPT:ICF` and lld's and gold's `--icf=all` merge different functions with identical machine code into one, making `&f == &g` true, which does not conform. `--icf=safe` only merges functions whose address is never taken and doesn't break this rule.

String literals, on the other hand, are **potentially non-unique objects** ([[intro.object]]): whether two identical literals, or one that is a suffix of the other, share storage is unspecified. So the result of `+"foo" == +"foo"` is unspecified; in constant evaluation, a comparison where the two pointers might point to the same offset of the same merged object is not a constant ([[expr.const.core]] ¶2.29). Since C++26 the backing array of `std::initializer_list` is also a potentially non-unique object ([[diff.cpp23.dcl.dcl]]).

```cpp run title="eq-string-literal.cpp" ok
constexpr const char* p = "foo";
static_assert(p == p);                 // OK: the same pointer value
static_assert(!("foo" == +"bar"));     // OK: different contents, cannot be merged into the same place
// static_assert(+"foo" == "foo");     // error: whether they are merged is unspecified, not a constant

int main() {}
```

### Pointer-to-member equality (¶5)

¶5 If at least one operand is a pointer to member, pointer-to-member conversions ([[conv.mem]]), function pointer conversions and qualification conversions are applied to both sides to bring them to their composite pointer type. Then:

- ¶5.1 If both are null member pointer values, they compare equal.
- ¶5.2 If only one is a null member pointer value, they compare unequal.
- ¶5.3 If either points to a virtual member function, the result is unspecified.
- ¶5.4 If one refers to a member of class `C1` and the other to a member of a different class `C2`, where neither is a base class of the other, the result is unspecified.
- ¶5.5 If both refer to (possibly different) members of the same union, they compare equal.
- ¶5.6 Otherwise, imagine indirecting through a hypothetical object of the associated class type: they compare equal if they would refer to the same member of the same most derived object or the same subobject, and unequal otherwise.

The reason for ¶5.3 lies in the implementation. In the Itanium ABI, a pointer to a virtual member function stores the vtable offset plus 1, and the same virtual function may have different offsets in different classes' vtables. Requiring exact equality semantics would make every comparison expensive.

```cpp title="eq-mptr-virtual-const.cpp" error
struct B { virtual int v(); };
constexpr bool r = &B::v == &B::v;   // error: unspecified result, not a constant
```

¶5.4 corresponds to Example 1 in the standard: `B::x` and `C::x` are cast to `int A::*` and compared; `B` and `C` are not bases of each other, so the result is unspecified.

¶5.6 uses a hypothetical object as the criterion in order to handle diamond inheritance. Example 2 in the standard:

```cpp run title="eq-mptr-diamond.cpp" ok
struct B { int f(); };
struct L : B {};
struct R : B {};
struct D : L, R {};

int (B::*pb)() = &B::f;
int (L::*pl)() = pb;
int (R::*pr)() = pb;
int (D::*pdl)() = pl;    // reaches B through L
int (D::*pdr)() = pr;    // reaches B through R

bool x = (pdl == pdr);   // false
bool y = (pb == pl);     // true

int B::f() { return 0; }
int main() { return (!x && y) ? 0 : 1; }
```

`pdl` and `pdr` both point to `B::f`, but when called on a `D` object, `this` is adjusted to two different `B` subobjects of `D`, so they compare unequal. A pointer to member records not only which member, but also which inheritance path it reaches it through.

Comparing a pointer to member with `nullptr` is always valid: a null pointer constant can be converted to a null member pointer.

### `nullptr_t` (¶6)

¶6 Two operands of type `std::nullptr_t`, or one of type `std::nullptr_t` and the other a null pointer constant, compare equal. They cannot be compared relationally.

### `std::meta::info` {{c++26}} (¶7)

C++26 static reflection ([[P2996R13]]) introduced the scalar type `std::meta::info` ([[basic.fundamental]]), whose values are called reflections and represent program entities such as types, variables and functions.

¶7 Two reflections compare equal if and only if both are null reflections (¶7.1), or they represent values that are template-argument-equivalent ([[temp.type]]) (¶7.2), the same object (¶7.3), the same entity (¶7.4), the same annotation (¶7.5, [[dcl.attr.annotation]]), the same direct base class relationship (¶7.6), or equal data member descriptions (¶7.7, [[class.mem.general]]).

```cpp title="eq-meta-info.cpp"
#include <meta>

struct S { int m; };
using Alias = S;

static_assert(^^S != ^^Alias);                       // ^^Alias reflects the alias itself
static_assert(std::meta::dealias(^^Alias) == ^^S);   // after removing the alias, the same type
static_assert(std::meta::info{} == std::meta::info{});   // two null reflections (¶7.1)
```

A type alias is a separate entity ([[expr.reflect]] ¶5.6), and reflecting it gives a different value from reflecting the target type; to check whether two reflections denote the same type, `dealias` first. Clang 23 doesn't provide `<meta>` yet, so this example has not been verified by compilation.

### Result (¶8–¶9)

¶8 `==` yields `true` and `!=` yields `false` if the operands are equal, and the opposite otherwise.

¶9 Arithmetic and enumeration operands first undergo the usual arithmetic conversions, and the result follows the mathematical relation. Floating-point has two special cases: `NaN == NaN` is `false`, and `-0.0 == 0.0` is `true`.

## Implementation view

!!! impl
    - On mainstream platforms pointer comparisons compile to integer comparisons, and comparisons whose results are unspecified actually give address order at run time. But the optimizer can exploit the unspecifiedness: provenance-based analysis may fold `&a + 1 == &b` to `false` at compile time, while the same comparison elsewhere, not optimized, gives `true`.
    - In the Itanium ABI, pointers to data members are compared by offset; pointers to member functions compare the two words `{ptr, adj}`, ignoring `adj` when `ptr` is 0 (null). MSVC's representation of pointers to member functions varies with the inheritance model, and comparison is correspondingly more complex.
    - Clang's `-Wtautological-compare` family warns about an array compared with a null pointer being always false, string literal comparisons having unspecified results, and so on; under `-std=c++2c` comparing two arrays is an error (`-Warray-compare-cxx26`).

## Common misconceptions

!!! pitfall "Sorting arbitrary pointers with `<`"
    `<` on unrelated pointers gives an unspecified result; use `std::less<T*>`.

!!! pitfall "Comparing unrelated pointers is UB"
    Relational comparison gives an unspecified result, and equality comparison is defined (except for a past-the-end pointer against an adjacent object). What really is UB is subtracting unrelated pointers ([[expr.add#5]]).

!!! pitfall "Comparing C strings with `==`"
    Comparing two literals directly is ill-formed in C++26; `==` between `const char*` values compares addresses.

## Questions

!!! question "Question 1"
    What are `r1` and `r2` below?

    ```cpp
    struct S { int a; int b[2]; int c; };
    S s;
    bool r1 = &s.b[1] < &s.c;
    bool r2 = &s.b[2] == &s.c;
    ```

<details markdown="1">
<summary>Answer</summary>

`r1`: `s.b[1]` is a subobject of the member `b`, and `s.c` is a later-declared member. Item 4.2 of [[expr.rel#4]] applies recursively to subobjects of members, so `r1` must be `true`.

`r2`: `&s.b[2]` is the past-the-end pointer of the array `b`. Item 4.1 of [[expr.eq#4]] only concerns a different complete object, and `s.c` is a subobject, so it doesn't apply. By item 4.2, they compare equal if they represent the same address. In a typical layout there is no padding between `b` and `c`, and the result is `true`; but whether there is padding is up to the implementation, so the result depends on the layout.
</details>

!!! question "Question 2"
    Why does the standard give only a partial order for `<`, yet an almost completely determined answer for `==`?

<details markdown="1">
<summary>Answer</summary>

`==` only needs to decide whether two addresses are the same, which can be implemented efficiently under any memory model; a segmented architecture can normalize segment and offset and then compare. `<`, however, needs a total order, and on a segmented architecture there is no natural answer to which of two segments is greater; forcing a total order would make every pointer comparison pay for normalization.

So the standard leaves the total order to `std::less`, which pays the cost only when needed; built-in `<` only guarantees a partial order within a single object, which is enough for array traversal and iterator comparison. The one unspecified case `==` keeps, a past-the-end pointer against an adjacent object, exists for provenance-based optimization, not for the hardware.
</details>

## Summary

| Comparison | Result | Basis |
|---|---|---|
| Arithmetic, enumeration | Mathematical relation after the usual arithmetic conversions; NaN is equal to nothing | [[expr.rel#6]], [[expr.eq#9]] |
| Pointer `<` within the same array, or between members of the same object | By index, by declaration order | [[expr.rel#4]] |
| `<` on unrelated pointers, `<` on unequal function pointers | {{unspec}} | [[expr.rel#5]] |
| Pointer `==` | Equal if the addresses are the same | [[expr.eq#4]] |
| Past-the-end pointer `==` another complete object | {{unspec}} | [[expr.eq#4]] ¶4.1 |
| `==` on pointers to virtual member functions, or to members of unrelated classes | {{unspec}} | [[expr.eq#5]] |
| `==` on pointers to members of the same union | Equal | [[expr.eq#5]] ¶5.5 |
| Comparing two arrays | {{ill-formed}} (C++26; deprecated since C++20) | [[expr.rel#1]], [[expr.eq#1]] |
| Pointer `<` `0`, `<` on `nullptr_t` or pointers to members | {{ill-formed}} | [[expr.rel#2]], [[expr.rel#3]] |
