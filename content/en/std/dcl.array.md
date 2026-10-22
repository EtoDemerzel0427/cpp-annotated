---
title: Arrays
summary: "What the array declarators `D1[N]` and `D1[]` mean: the bound must be a std::size_t constant greater than zero, which types can't be elements, an array's cv is its elements' cv, how arrays of unknown bound are completed, the real structure of multidimensional arrays, and why C++ has no variable-length arrays."
updated: 2026-10-19
---

!!! tldr
    - An array's bound is part of its type: `int[3]`, `int[4]` and `int[]` are three different types, and `int[]`, of unknown bound, is an incomplete type.
    - The bound must be a converted constant expression of type `std::size_t` and greater than zero. Floating-point values, negative numbers, scoped enumerations and run-time values are all out, so C++ has no variable-length arrays (VLAs).
    - Elements can't be references, functions, arrays of unknown bound or `void`. Adding cv to an array actually adds it to the elements.
    - C++ has no true multidimensional arrays, only arrays of arrays. `int a[3][5]` has 3 elements, each an `int[5]`; only the first bound can be omitted.
    - With an initializer, the bound can be omitted and is determined by the number of initial values; it can also be inherited from a previous declaration in the same host scope.

Arrays can't be assigned, can't be passed or returned by value, and convert to a pointer to the first element in almost every expression. This subclause specifies what array declarators mean and the basic properties of array types. Array initialization is in [[dcl.init.aggr]] and [[dcl.init.string]], subscripting in [[expr.sub]], and the array-to-pointer conversion in [[conv.array]].

## The array bound (¶1)

<div class="compare" markdown="1">

```cpp run ok
enum E { e3 = 3 };
int a4[e3];   // unscoped enumeration
struct Conv {
  constexpr operator int() const
  { return 4; }
};
int a6[Conv{}];   // constexpr conversion
const int c = 5;
int a11[c];   // const integral variable
int main() { }
```

```cpp run error
int a1[1.5];   // error: floating-point
int a2[-1];    // error: negative
enum class EC { k = 3 };
int a5[EC::k]; // error: scoped enumeration
int n = 3;
int a7[n];     // error: not a constant
```

</div>

¶1 If `D` in a declaration `T D` has the form `D1[N]`, the type of the name is "array of `N` `T`", preceded by the modifiers accumulated by the inner declarator (see [[dcl.decl]]).

!!! std
    The *constant-expression* shall be a converted constant expression of type `std::size_t`. Its value N specifies the *array bound*, i.e., the number of elements in the array; N shall be greater than zero.

Each qualification in this sentence excludes some forms:

- Constant expression ([[expr.const]]): the bound must be determined at compile time, which excludes variable-length arrays. A `const int c` initialized with a constant expression can be used in constant expressions, so `a11` is valid.
- Converted constant expression ([[g:converted-constant-expression|converted constant expression]], [[expr.const.const]]): only implicit conversions that lose no information are allowed from the expression to `std::size_t`, such as integral promotions, non-narrowing integral conversions, and `constexpr` user-defined conversions. Floating-to-integral conversion is not allowed; converting `-1` to `std::size_t` is narrowing and not allowed either.
- Of type `std::size_t`: a scoped enumeration can't be implicitly converted to an integer, so it can't be used directly as a bound.
- Greater than zero: C++ has no zero-length arrays. GCC and Clang accept `int a[0];` as an extension with `sizeof` 0, and give a `-Wzero-length-array` warning with `-pedantic`.

The **array bound** ([[g:array-bound|array bound]]) is the number of elements `N`. Arrays with the same element type and different bounds are different types.

## Arrays of unknown bound (¶2–3)

¶2 If `D` has the form `D1[]`, the type is "array of unknown bound of `T`", with some exceptions described in paragraphs 7 and 8.

¶3 "Array of `N` `U`" and "array of unknown bound of `U`" are collectively called **array types**. Attributes can follow `[]` and appertain to the array type.

An array of unknown bound is an [[g:incomplete-type|incomplete type]] ([[basic.types]]). You can declare a variable of this type (`extern int a[];`) and form pointers and references to it (`int (*)[]`, `int (&)[]`), but you can't define an object of this type or apply `sizeof` to it.

## Element types (¶4–6)

### Which types can't be elements (¶4)

```cpp run error
int& a8[2];     // error: array of references
void a9[2];     // error: array of void
int a10[2][];   // error: element is an array of unknown bound
int f[2]();     // error: array of functions
```

¶4 The **element type** ([[g:array-element-type|element type]]) `U` of an array can't be:

- a reference, because references are not objects ([[dcl.ref#5]]);
- a function: functions are not objects and have no size. What is usually wanted is an array of function pointers, `int (*f[2])();`;
- an array of unknown bound, because then the outer array couldn't compute the size of its elements. This is why only the first dimension of a multidimensional array can be omitted;
- cv `void`, an incomplete type that can never be completed.

Note 1 lists positively which types can be elements: fundamental types other than `void`, pointers, pointers to members, classes, enumerations, and arrays of known bound. When an array object is defined, class-type elements must be complete; an abstract class can't be an element type ([[class.abstract]]).

### An array's cv is its elements' cv (¶5)

```cpp run ok
#include <type_traits>
typedef int A[5], AA[2][3];
typedef const A  CA;    // array of 5 const int
typedef const AA CAA;   // array of 2 [arrays of 3 const int]

static_assert(std::is_same_v<CA, const int[5]>);
static_assert(std::is_same_v<CAA, const int[2][3]>);
static_assert(std::is_const_v<CA>);   // the array type itself also counts as const-qualified
int main() { }
```

¶5 "cv array of `N` `U`" is always adjusted to "array of `N` cv `U`", and likewise for arrays of unknown bound. For multidimensional arrays, cv sinks all the way down to the innermost elements. Note 2 adds that the adjusted array type itself also counts as a cv-qualified type ([[basic.type.qualifier]]), so `std::is_const_v<CA>` is true.

The reasoning behind this design: an array can't be modified as a whole, so the only possible meaning of a const array is that its elements are const. Putting cv on the elements uniformly also gives `const T` in a template a natural meaning when `T` is an array.

### Elements are stored contiguously (¶6)

¶6 An object of type "array of `N` `U`" consists of `N` contiguously allocated subobjects of type `U`, called the array's **elements**, numbered 0 to `N-1`; element 0 is the **first element**.

Contiguous means there is no padding between elements: `sizeof(U[N]) == N * sizeof(U)` ([[expr.sizeof#2]]). The alignment each element needs is already included in the tail padding of `sizeof(U)`. Pointer arithmetic ([[expr.add]]) is defined only between elements of the same array and its past-the-end position, precisely because these elements are all subobjects of the same array object.

## Omitting the bound (¶7–8)

### Determined by the initializer (¶7)

```cpp run ok
#include <type_traits>
int b[] = {1, 2, 3};          // int[3]
char s[] = "abc";             // char[4], including the terminating '\0'
static_assert(std::is_same_v<decltype(b), int[3]>);
static_assert(sizeof s == 4);
int main() {
  auto p = new int[]{1, 2, 3};   // new int[3]
  delete[] p;
}
```

¶7 Apart from declarations where an incomplete object type is allowed anyway, there are two cases in which the bound can be omitted:

- Function parameters ([[dcl.fct]]). The parameter type is adjusted to a pointer, so the bound has no effect anyway.
- A declaration of an object (but not a non-static data member) with an initializer. The bound is then computed from the number `N` of initial values ([[dcl.init.aggr]]), and the type is "array of `N` `U`". This also applies to `new int[]{1, 2, 3}` ([[expr.new]]) and functional casts like `int[]{1, 2}` ([[expr.type.conv]]).

```cpp run error
struct M { int m[] = {1, 2}; };   // error: the bound can't be deduced from a default member initializer
```

Non-static data members can't do this because the class layout must be determined at the end of the class definition. A default member initializer is only used when a constructor doesn't provide an initialization, and different constructors may provide different numbers of initial values.

### Inherited from a previous declaration (¶8)

```cpp run error
extern int x[10];
struct S { static int y[10]; };

int x[];                // OK: the bound is 10
int S::y[];             // OK: the bound is 10

void f() {
  extern int x[];       // its host scope is the block, unlike the earlier declaration
  int i = sizeof(x);    // error: incomplete type
}

namespace A { extern int z[3]; }
int A::z[] = {};        // OK: defines an array of 3 elements
```

¶8 If a reachable previous declaration specifies the bound and has the same host scope as the current declaration, the omitted bound is taken from that declaration. The same applies to out-of-class definitions of static data members. Host scope is defined in [[basic.scope.scope]]: if a declaration inhabits a block scope, its host scope is that block; otherwise it is the declaration's target scope.

So `extern int x[];` inside a function doesn't inherit the bound: its host scope is the block of the function body, while the earlier declaration is in the global namespace. A block-scope redeclaration only introduces a locally visible name and doesn't accumulate information from outer declarations.

## Multidimensional arrays (¶9)

```cpp run ok
#include <type_traits>
int x3d[3][5][7];
static_assert(std::is_same_v<decltype(x3d[1]),    int(&)[5][7]>);
static_assert(std::is_same_v<decltype(x3d[1][2]), int(&)[7]>);
static_assert(std::is_same_v<decltype(+x3d),      int(*)[5][7]>);  // unary + triggers array-to-pointer conversion
static_assert(sizeof x3d == 3 * 5 * 7 * sizeof(int));

void g(int m[][5][7]);   // the parameter is adjusted to int (*)[5][7]; the last two bounds must be written
int main() { }
```

¶9 is a note: when several array declarators are adjacent, a multidimensional array type is formed, and only the first bound can be omitted.

Reading `int x3d[3][5][7];` by the method of [[dcl.decl]]: postfix operators group left to right, i.e. `((x3d[3])[5])[7]`, so the outermost is `[7]`, which sits right next to `int`, giving "array of 7 `int`"; then comes `[5]`, and finally `[3]`. So `x3d` has 3 elements, each an `int[5][7]`, each of whose elements is in turn an `int[7]`.

In an expression, `x3d[i]` is equivalent to `*(x3d + i)`. `x3d` first converts to `int (*)[5][7]` pointing to the first element; adding `i` advances by `sizeof(int[5][7])`; dereferencing gives element `i`, an lvalue of type `int[5][7]`. Further subscripts work the same way.

The note's conclusion: the first bound determines how much storage the array occupies but takes no part in any subscript computation. That's why the first dimension can be omitted, and why a function parameter's first dimension is lost when it is adjusted to a pointer.

¶10 This paragraph and paragraph 11 are both notes: conversions of expressions of array type are in [[conv.array]]; the subscript operator can be overloaded for classes ([[over.sub]]), and its built-in meaning is in [[expr.sub]].

## C++ has no variable-length arrays

```cpp run error
void f(int m) {
  int vla[m];             // error: the bound is not a constant expression
  int* ok = new int[m];   // OK: the first dimension of a new expression can be a run-time value
  delete[] ok;
  (void)vla;
}
```

C99 introduced variable-length arrays (VLAs), and C11 made them optional. C++ never adopted them: paragraph 1 requires the bound to be a constant expression, so `int vla[m];` above is ill-formed.

There are three main reasons. First, the type of a VLA depends on a run-time value, so `sizeof` becomes a run-time operation, and template argument deduction, overload resolution and `decltype` would all have to deal with types known only at run time, which conflicts with C++'s design of determining types at compile time. Second, allocating arbitrary amounts of stack space overflows the stack outright when `m` is too large, and this can't be detected. Third, alternatives already exist: `std::vector`, `std::unique_ptr<T[]>`, and `new T[n]` ([[expr.new]] allows the first dimension of a *new-declarator* to be non-constant). Arrays of run-time bound and `std::dynarray` were discussed during the development of C++14, but neither made it into the standard.

GCC and Clang accept VLAs as an extension. Clang 23 gives a `-Wvla-cxx-extension` warning by default (variable length arrays in C++ are a Clang extension), and an error with `-pedantic-errors`. MSVC doesn't support VLAs.

## Implementation notes

!!! impl
    - Flexible array members: C99's `struct S { int n; int data[]; };` is ill-formed in C++, because a non-static data member can't be an array of unknown bound. GCC and Clang accept it as an extension; Clang gives a `-Wc99-extensions` warning with `-pedantic`.
    - Name mangling: the Itanium C++ ABI encodes array types as `A<N>_<element type>`; for example the parameter `int(&)[3]` mangles to `RA3_i`. An array of unknown bound is encoded as `A_i`.
    - The size of an array type has an upper limit. The bound of `int b[sizeof(int) - 5];` is `SIZE_MAX`, and Clang 23 reports array is too large.

## History

!!! history
    - Array semantics are inherited from C. C++98 required the bound to be an integral constant expression.
    - C++11 added `std::array`, uniform list-initialization, and range-for over arrays.
    - C++14 changed the requirement on the bound to a converted constant expression of type `std::size_t`. This lets class types serve as bounds through `constexpr` conversion functions, and negative bounds are rejected by the same rules, as narrowing conversions.
    - C++20 allowed pointers or references to arrays of known bound to convert to those to arrays of unknown bound ([[conv.qual]]), and `new int[]{1, 2, 3}` can deduce its bound.
    - C++23 allowed an overloaded `operator[]` to have multiple parameters (`m[i, j]`).

## Pitfalls

!!! pitfall "Arrays as parameters"
    The `10` in `void f(int a[10])` is ignored; `a` has type `int*` ([[dcl.fct#5]]), and `sizeof a` is the size of a pointer. Writing `sizeof(a) / sizeof(a[0])` on a parameter gives the wrong answer, and Clang gives `-Wsizeof-array-argument` and `-Wsizeof-pointer-div` warnings for it. To keep the bound, use a reference `int (&a)[10]` or `std::span<int, 10>`; to get the element count, use `std::size(a)`, which fails to compile for pointers.

!!! pitfall "`int (*p)[3]` versus `int *p[3]`"
    The former is a pointer to an array of 3 `int`; the latter is an array of 3 pointers. Postfix `[]` binds tighter than prefix `*` ([[dcl.decl]]).

!!! pitfall "Arrays can't be assigned or used as return types"
    `int a[3], b[3]; a = b;` is ill-formed; a function can't return an array type ([[dcl.fct#16]]). But a class containing an array member can be copied and returned, and the implicit copy constructor copies the elements one by one. A lambda capturing an array by value also copies the elements one by one.

## Questions

!!! question "Question 1"
    Which of the following declarations are well-formed?
    ```cpp
    constexpr int k = -1;
    int a[k + 2];
    int c[true];
    int d['a'];
    ```

<details markdown="1">
<summary>Answer</summary>

All of them. The value of `k + 2` is 1; when the `int` is converted to `std::size_t`, the value is representable, so it isn't narrowing. `true` converts to `std::size_t` as 1. The value of `'a'` is 97. A converted constant expression looks at whether the value is representable in the target type, not just at the source type.
</details>

!!! question "Question 2"
    Why is `extern int a[]; int (*p)[] = &a;` well-formed while `int (*q)[3] = &a;` is ill-formed?

<details markdown="1">
<summary>Answer</summary>

`&a` has type `int (*)[]`, the same as `p`. Going from a pointer to an array of unknown bound to a pointer to an array of known bound is not any standard conversion: C++20 only allows the opposite direction (known to unknown, [[conv.qual]]), since the compiler can't verify that the bound really is 3. Clang 23 rejects even `static_cast<int(*)[3]>(&a)`; only `reinterpret_cast` works, and the resulting pointer is only meaningful if `a` actually has at least 3 elements.
</details>
