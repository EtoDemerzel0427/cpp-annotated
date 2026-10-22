---
title: Additive operators
summary: "Which operands binary + and - accept; adding an integer to or subtracting it from a pointer is defined only within the same array (including the past-the-end position), and merely computing an out-of-bounds pointer is undefined behavior; subtracting two pointers yields ptrdiff_t."
updated: 2026-10-19
---

!!! tldr
    - For arithmetic operands, `+` and `-` first apply the usual arithmetic conversions, and the overflow rules are the same as for multiplication and division: signed overflow is undefined behavior, unsigned arithmetic wraps around modulo.
    - When an integer is added to or subtracted from a pointer, the result must land between element 0 and the past-the-end position of the same array. Merely computing a pointer outside that range is undefined behavior; no dereference is needed.
    - An object that is not an array element is treated as an array of one element, so `&x + 1` is valid and `&x + 2` is UB; you can't use pointer arithmetic to walk across adjacent members or adjacent rows of a two-dimensional array.
    - Subtracting two pointers yields `std::ptrdiff_t` and is defined only when they point into the same array; adding 0 to a null pointer and subtracting two null pointers are both defined.
    - The pointer's type must be similar to the array element type: an `int` array cannot be traversed with arithmetic on an `unsigned*`, even though the aliasing rules allow reading through it.

## Arithmetic operands (¶1, ¶3)

¶1 `+` and `-` group left-to-right, and the operands must be prvalues: lvalues first undergo the lvalue-to-rvalue conversion, and arrays decay to pointers. When both operands have arithmetic or unscoped enumeration type, the usual arithmetic conversions ([[expr.arith.conv]]) are applied first, bringing both sides to the same type.

¶3 The result of `+` is the sum, and the result of `-` is the difference. When the result is out of range, [[expr.pre#4]] handles it uniformly: signed integer overflow is {{ub}}, and unsigned integers are computed modulo 2<sup>N</sup> and never overflow. All of this is exactly the same as for multiplication; see [[expr.mul]].

The part of this subclause that really needs careful reading is pointer arithmetic: when adding an integer to a pointer gives a meaningful pointer, and when subtracting two pointers is defined. `a[i]` is just `*((a)+(i))` ([[expr.sub]]), so the validity of subscripting is decided here too.

## Which pointers allow arithmetic (¶1, ¶2)

```cpp title="add-operands.cpp" error
struct Incomplete;
void fn();

void f(void* pv, Incomplete* pi, int* p, int* q) {
    auto a = pv + 1;        // error: void is not an object type
    auto b = pi + 1;        // error: points to an incomplete type
    auto c = &fn + 1;       // error: function pointer
    auto d = p + q;         // error: two pointers cannot be added
    auto e = nullptr + 0;   // error: nullptr_t is not a pointer type
}
```

¶1 For addition, either both sides have arithmetic type, or one side is a pointer to a completely-defined object type and the other has integral type. Pointer arithmetic moves by the size of an element, so `void*`, function pointers and pointers to incomplete types don't work. If the other side is `bool`, `char` or an unscoped enumeration, integral promotion ([[conv.prom]]) is applied first:

```cpp run title="add-operands-ok.cpp" ok
enum E { two = 2 };

int f(int* p) {
    int* a = p + two;       // OK: the enumerator is first promoted to int
    int* b = true + p;      // OK: bool is an integral type, and addition commutes
    return int(a - b);
}

int main() {}
```

¶2 Subtraction has three valid forms: both sides of arithmetic type (¶2.1); both sides pointers to similar completely-defined object types (¶2.2); a pointer on the left and an integral type on the right (¶2.3). **Similar** ([[conv.qual]]) means the types are the same after removing cv-qualification at every level, so `const int*` minus `int*` is valid, `int*` minus `long*` is not, and neither is `3 - p`.

GCC and Clang accept arithmetic on `void*` and on function pointers as a GNU extension, treating them as `char*`; `-pedantic` gives a warning, and `-pedantic-errors` rejects it.

## Adding an integer to or subtracting it from a pointer (¶4)

```cpp run title="add-bounds.cpp" ok
constexpr bool test() {
    int a[3]{};
    int* end = a + 3;      // OK: past-the-end position
    int* p = end - 3;      // OK: back to element 0
    int v = 0;
    int* q = &v + 1;       // OK: v is treated as a 1-element array, q is a past-the-end pointer
    int* n = nullptr;
    n = n + 0;             // OK: null pointer plus 0 is still a null pointer
    return p == a && q - 1 == &v && n == nullptr;
}
static_assert(test());

int main() {}
```

¶4 Let `P` be a pointer and `J` an expression of integral type with value *j*. The result has the type of `P`, and its value is determined as follows:

- ¶4.1 If `P` is a null pointer and *j* is 0, the result is a null pointer.
- ¶4.2 Otherwise, if `P` points to element *i* of an array object *x* with *n* elements, `P + J` points to element *i + j* and `P - J` points to element *i − j*, provided the resulting index is between 0 and *n*.
- ¶4.3 Every other case is {{ub}}.

The elements in ¶4.2 may be hypothetical; this comes from two conventions in [[basic.compound#3]] (restated in footnote 58):

1. A **past-the-end pointer**, i.e. a pointer past the last element, is treated as pointing to a hypothetical element *n*. So the resulting index may equal *n*, which is what makes `for (p = a; p != a + n; ++p)` valid.
2. An object that is not an array element is treated as belonging to an array with a single element. So `&v + 1` is the past-the-end pointer of `v` and is valid; `&v + 2` is UB.

Going one step out of bounds falls under item 4.3. An expression with UB in constant evaluation is not a constant expression and the compiler must diagnose it, so this is the easiest place to observe the rule:

```cpp title="add-oob-const.cpp" error
constexpr bool f() {
    int a[3]{};
    int* p = a + 4;        // UB: beyond the past-the-end position
    return p != nullptr;
}
static_assert(f());        // error: not a constant expression

constexpr bool g() {
    int a[3]{};
    int* p = a - 1;        // UB: there is no before-the-beginning position
    return p != nullptr;
}
static_assert(g());        // error: not a constant expression
```

Clang's explanation for `f` is "cannot refer to element 4 of array of 3 elements in a constant expression".

### UB even without a dereference

`a + 4` is never dereferenced, so why isn't it allowed? There are three kinds of situation the standard wants to accommodate:

1. In a segmented memory model, a pointer consists of a segment and an offset. Arithmetic past the end of a segment may wrap around, and merely loading such a value into a segment register may raise a hardware exception.
2. An array may sit right at the end of the address space. The implementation only has to guarantee that the one position past the end is representable; beyond that it may wrap around to near address 0.
3. The compiler may assume that pointer arithmetic doesn't go out of bounds. So `p + i < p + j` can be simplified to `i < j`, and loop transformations also rely on this premise.

The third point is the one that shows up most in real code:

```cpp title="add-overflow-check.cpp" ub
#include <cstddef>

bool will_overflow(const char* p, std::size_t len) {
    return p + len < p;    // if p + len is out of bounds, computing it is already UB
}
```

Since `p + len` cannot be out of bounds, `p + len < p` is always false. Clang 23 warns "pointer comparison always evaluates to false" right away and compiles the whole function to `return false`. The correct way is to compare the remaining length in the integer domain: `len > static_cast<std::size_t>(end - p)`.

### Adjacent members are not the same array

Note 1 of ¶4 states the rule more directly: for a pointer to a base class subobject, a member subobject or a complete object, adding any value other than 0 or 1 is UB.

```cpp run title="add-member-walk.cpp" ub
struct P { int x, y, z; };

int main() {
    P s{1, 2, 3};
    int* px = &s.x;
    int* end = px + 1;     // OK: past-the-end pointer of s.x
    int bad = *(px + 2);   // UB: s.x is not an array element, only +0 or +1 is allowed
    (void)end;
    return bad;
}
```

The address of `px + 1` may happen to equal `&s.y`, but it is still the past-the-end pointer of `s.x`. Note 2 of [[basic.compound#3]] explains that a past-the-end pointer does not count as pointing to an unrelated object that happens to be at that address, and dereferencing it is UB as well.

### A two-dimensional array cannot be flattened

`int a[2][3]` is an array of 2 elements, each of which is an `int[3]`. `&a[0][0]` points to element 0 of the 3-element array `a[0]`, so pointer arithmetic can only move within `a[0]`:

```cpp title="add-2d.cpp" error
constexpr int f() {
    int a[2][3]{{1, 2, 3}, {4, 5, 6}};
    int* p = &a[0][0];
    return p[4];           // UB: p + 4 goes beyond a[0]
}
constexpr int v = f();     // error: not a constant expression
```

The memory is contiguous and the address of `p + 4` is exactly `a[1][1]`; at run time mainstream compilers usually give 5 too. But by the standard it is UB. When you need one-dimensional access, declare the storage as a one-dimensional array and compute the index yourself.

## Subtracting pointers (¶5)

¶5 When two pointers are subtracted, the result is a prvalue of type `std::ptrdiff_t` ([[support.types.layout]]):

- ¶5.1 If both are null pointers, the result is 0.
- ¶5.2 If they point to elements *i* and *j* of the same array (possibly the past-the-end position), the result is *i − j*.
- ¶5.3 Every other case is {{ub}}.

```cpp title="add-sub-unrelated.cpp" error
constexpr long f() {
    int a[3]{}, b[3]{};
    return b - a;          // UB: they point into different arrays
}
constexpr long v = f();    // error: not a constant expression
```

Note 2 adds that even within the same array, it is UB if *i − j* is outside the range of `ptrdiff_t`. On a 32-bit platform, subtracting the two ends of a `char` array larger than 2 GiB does this. That is why `max_size()` of containers such as `std::vector` usually doesn't exceed `PTRDIFF_MAX`.

!!! lawyer "Unrelated pointers: equality, ordering, subtraction"
    For two pointers `p` and `q` to different complete objects:

    - `p == q` is defined and is `false`; the only exception is comparing a past-the-end pointer with the address of another object, where the result is unspecified ([[expr.eq#4]]).
    - The result of `p < q` is unspecified, but it is not UB ([[expr.rel#5]]). Use `std::less<T*>` when you need a total order.
    - `p - q` is UB (¶5.3).

## The element type must be similar (¶6)

```cpp run title="add-similar.cpp" ub
int main() {
    int arr[5] = {1, 2, 3, 4, 5};
    unsigned int* p = reinterpret_cast<unsigned int*>(arr + 1);
    unsigned int k = *p;    // OK: an int may be read through the corresponding unsigned type, k == 2
    unsigned int* q = p + 1;// UB: unsigned int and int are not similar
    return int(k + *q);
}
```

¶6 For addition or subtraction, if the pointer has type "pointer to cv `T`" and `T` is not similar to the array element type, the behavior is undefined. The above is Example 1 in the standard: the aliasing rules in [[basic.lval]] allow reading an `int` through the corresponding unsigned type, so the first read is valid; but pointer arithmetic requires similar types, and `unsigned int` and `int` are not similar, so `p + 1` is UB. Being allowed to read is not the same as being allowed to do arithmetic.

!!! warning "Traversing an object's bytes with `unsigned char*`"
    Read strictly by paragraphs 4 and 6, `reinterpret_cast<unsigned char*>(&obj) + k` is UB for any *k*, even 1 (unless `obj` itself is an `unsigned char`). The pointer points to `obj` itself, not to an element of some `unsigned char` array, and `unsigned char` is not similar to the type of `obj`.

    Yet byte-wise access to the object representation underlies a great deal of code, including `memcpy`-style serialization and standard library implementations, and every compiler handles it as the programmer intends. This is a recognized wording defect. [[P1839]] proposes making the object representation actually be an array of `unsigned char`; at the time of writing it has not been merged into the draft.

## Implementation view

!!! impl
    - `p + j` compiles to `p + j * sizeof(T)`, usually a single `lea` or `add`. `p - q` compiles to the byte difference divided by `sizeof(T)`; paragraph 5 guarantees the difference is a multiple of `sizeof(T)`, so the compiler replaces the real division with a multiplication by the modular inverse.
    - UBSan's `-fsanitize=pointer-overflow` only checks pointer arithmetic that wraps around the address space and a null pointer plus a non-zero value; ASan only checks out-of-bounds accesses. An out-of-bounds pointer like `a + 4` that is computed but never accessed escapes both, and constant evaluation turns out to be the strictest checker.
    - `-Warray-bounds` can catch some out-of-bounds constant subscripts at compile time.

## History and evolution

!!! history
    - The past-the-end guarantee has existed since C89 and C++98. It made the half-open range `[first, last)` the foundation of the STL iterator model.
    - C++ has always specified that a null pointer plus or minus 0 is a null pointer and that subtracting two null pointers gives 0. C left `NULL + 0` as UB until C23; this is one point where the two languages differ on pointer arithmetic.
    - Early standards only talked about pointers to array elements, and the treatment of past-the-end pointers and non-array objects was scattered across notes. Today's wording unifies them into the hypothetical-element convention of [[basic.compound#3]].
    - C++20's implicit object creation ([[intro.object]]) lets storage obtained from `malloc` support valid pointer arithmetic too: the allocation function implicitly creates a suitable array object.

## Common misconceptions

!!! pitfall "Only dereferencing an out-of-bounds pointer is UB"
    Computing an out-of-bounds pointer is itself UB (¶4.3). Overflow checks of the form `p + n < p` are treated by the compiler as always false and deleted.

!!! pitfall "A type the aliasing rules let you read through can also be used for pointer arithmetic"
    The aliasing rules allow reading through the corresponding signed/unsigned type or a character type, but pointer arithmetic requires the type to be similar to the array element (¶6).

!!! pitfall "Subtracting pointers into different arrays merely gives an unspecified result"
    The result of a relational comparison is unspecified; subtraction is UB.

## Questions

!!! question "Question 1"
    Does the following loop have UB?

    ```cpp
    void f(int* a, int n) {
        for (int* p = a + n - 1; p >= a; --p) { /* ... */ }
    }
    ```

<details markdown="1">
<summary>Answer</summary>

Yes. After the last iteration `--p` is executed, and `p` goes from `a` to `a - 1`. The standard only guarantees the past-the-end position; there is no before-the-beginning position, so this step is itself UB (¶4.3), and the subsequent `p >= a` is moot. Also, when `n == 0`, `a + n - 1` is already out of bounds.

The correct form is `for (int* p = a + n; p != a; ) { --p; /* ... */ }`. `std::reverse_iterator` does the same: it stores the next position internally and decrements before dereferencing.
</details>

!!! question "Question 2"
    In `int x; int* p = &x + 1; int* q = p - 1;`, what does `q` point to? What is `p - &x`?

<details markdown="1">
<summary>Answer</summary>

`x` is treated as element 0 of a 1-element array, and `p` is hypothetical element 1, the past-the-end position. `q = p - 1` goes back to element 0, points to `x`, and can be dereferenced. By item 5.2, `p - &x` is 1 − 0 = 1, of type `std::ptrdiff_t`.
</details>

## Summary

| Operation | Defined when | Otherwise | Paragraph |
|---|---|---|---|
| `p + j`, `p - j` | Resulting index between 0 and *n* (past-the-end) | {{ub}}, even without a dereference | ¶4 |
| Null pointer ± 0 | The result is a null pointer | | ¶4.1 |
| Non-array object | Treated as a 1-element array; only +0 and +1 | {{ub}} | ¶4 Note 1 |
| `p - q` | Within the same array (including past-the-end); result is `ptrdiff_t` | {{ub}} | ¶5 |
| Subtracting two null pointers | 0 | | ¶5.1 |
| Pointer type not similar to the element type | | {{ub}} | ¶6 |
| `void*`, function pointers, incomplete types | | {{ill-formed}} | ¶1, ¶2 |
