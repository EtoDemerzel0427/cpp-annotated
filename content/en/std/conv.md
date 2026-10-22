---
title: Standard conversions
summary: "All the implicit conversions built into the language: lvalue-to-rvalue, array- and function-to-pointer, temporary materialization, qualification conversions, integral and floating-point promotions, the arithmetic conversions, pointer and pointer-to-member conversions, boolean conversions, and the order in which they make up a standard conversion sequence."
updated: 2026-10-19
---

!!! tldr
    - A standard conversion sequence has at most four steps: reading a value or decaying, one arithmetic or pointer conversion, dropping `noexcept`, adding cv. So `Derived*` can't become `Base*` and then `void*`; it becomes `void*` directly.
    - Promotions (`short` → `int`, `float` → `double`, etc.) and conversions may make no difference to the value at all, but promotions rank higher in overload resolution.
    - Conversions between integers are always well-defined (modulo 2<sup>N</sup>); converting a floating-point value to an integer is UB when the truncated value doesn't fit.
    - `T**` can't be implicitly converted to `const T**`, only to `const T* const*`: when `const` is added at an inner level, every level outside it must also be `const`.
    - The only null pointer constants are integer literals with value zero and `nullptr`; converting pointers, pointers to members and floating-point values to `bool` is narrowing in list-initialization.

## Standard conversion sequences [conv.general]

```cpp ok
struct Base {}; struct Derived : Base {};
void take(const void*);

void demo(Derived* d, short s, int arr[3]) {
    take(d);          // pointer conversion Derived* → void*, then qualification conversion → const void*
    double x = s;     // one step: floating-integral conversion
    long n = arr[0];  // read the value, then an integral conversion
    (void)x; (void)n;
}
```

A **standard conversion** is an implicit conversion with built-in meaning. Passing an `int` to a `long` parameter, using an array name as a pointer, assigning a `char*` to a `const char*`, testing a pointer for non-null with `if (p)`: the basis for all of these is in this clause.

¶1 A **standard conversion sequence** ([[g:standard-conversion-sequence]]) is a sequence of standard conversions in the following order, with at most one conversion from each step; the sequence may also be empty:

1. one of lvalue-to-rvalue, array-to-pointer, function-to-pointer;
2. one of the eight: integral promotions, floating-point promotion, integral conversions, floating-point conversions, floating-integral conversions, pointer conversions, pointer-to-member conversions, boolean conversions;
3. a function pointer conversion;
4. a qualification conversion.

A standard conversion sequence is applied to an expression if necessary to convert it to the required type and value category.

Step 2 allows only one conversion, so you can't do two in a row. `short` can be converted to `double` because the source of a floating-integral conversion can be any integer type, not because it is first promoted to `int` and then converted. `Derived*` → `void*` is a single pointer conversion by itself and doesn't go through `Base*`.

The rank of each conversion in overload resolution is defined in [[over.ics.scs]]. The distinction between promotions and conversions only matters there:

| Conversion | Section on this page | Rank in overload resolution |
|---|---|---|
| Lvalue-to-rvalue, array-to-pointer, function-to-pointer | [[conv.lval]], [[conv.array]], [[conv.func]] | Exact Match |
| Qualification, function pointer | [[conv.qual]], [[conv.fctptr]] | Exact Match |
| Integral promotion, floating-point promotion | [[conv.prom]], [[conv.fpprom]] | Promotion |
| Integral, floating-point, floating-integral, pointer, pointer-to-member, boolean | [[conv.integral]] etc. | Conversion |
| Temporary materialization | [[conv.rval]] | Not part of a standard conversion sequence |

### Where implicit conversions happen (¶2–¶8)

¶2 is a note listing the contexts where expressions are implicitly converted: as operands of operators; as the condition of an `if` or a loop (destination `bool`); as the expression of a `switch` (destination an integral type); as the source of an initialization, including function arguments and the operand of `return`.

The following three definitions are used often elsewhere, and all of them rely on an invented declaration:

| Term | Definition | Where it's used |
|---|---|---|
| ¶3 `E` can be implicitly converted to `T` | `T t = E;` is well-formed | Everywhere, e.g. `std::is_convertible` |
| ¶4 `E` is contextually converted to `bool` | `bool t(E);` is well-formed | Conditions of `if`, `while`, `for`; `!`, `&&`, `\|\|`; the first operand of `?:`; `static_assert`; `noexcept(E)`; `explicit(E)` |
| ¶5 `E` of class type is contextually implicitly converted to a type | Look in the class for non-explicit conversion functions whose return type (cv `T` or a reference to it) has a `T` the context allows; there must be exactly one such `T` | The condition of `switch`, the length in an array `new`, the operand of `delete` |

The difference between ¶3 and ¶4 is the difference between copy-initialization and direct-initialization: direct-initialization considers `explicit` conversion functions. That is how `explicit operator bool` works:

```cpp error
struct Handle { explicit operator bool() const { return true; } };

void demo(Handle h) {
    if (h) {}                // OK: bool t(h);
    bool ok = h && true;     // OK: operands of && are also contextually converted
    bool bad = h;            // error: copy-initialization doesn't consider explicit conversion functions
    int n = h + 1;           // error: no going through bool and then promoting to int
}
```

¶5 requires exactly one `T`:

```cpp error
struct One { operator int() const; };
struct Two { operator int() const; operator long() const; };

void demo(One a, Two b) {
    switch (a) { case 1: break; }   // OK: only T = int
    switch (b) { case 1: break; }   // error: two candidates, int and long
}
```

¶6 The effect of an implicit conversion is the same as performing the invented declaration and initialization and then using the invented variable as the result. If `T` is an lvalue reference or an rvalue reference to function, the result is an lvalue; if it is an rvalue reference to object, the result is an xvalue; otherwise it is a prvalue. This matches the rule for explicit conversions ([[expr.static.cast]]).

¶7 and ¶8 are notes. For class types, user-defined conversions also have to be considered ([[class.conv]]); a general implicit conversion sequence is a standard conversion sequence, a user-defined conversion, then another standard conversion sequence ([[over.best.ics]]). Some contexts suppress certain conversions; for example, the operand of unary `&` doesn't undergo the lvalue-to-rvalue conversion.

## Lvalue-to-rvalue conversion [conv.lval]

The name is misleading, and the footnote admits it is kept for historical reasons. The conversion turns a glvalue (lvalue or xvalue) of any non-function, non-array type into a prvalue; in essence, it reads the object's value.

### Type (¶1)

¶1 A glvalue of a non-function, non-array type `T` can be converted to a prvalue. If `T` is an incomplete type, a program that needs this conversion is ill-formed. If `T` is a non-class type, the type of the prvalue is the cv-unqualified version of `T`, so reading a `const int` gives an `int`; class types keep their cv. The footnote points out that in C++ class and array prvalues can be cv-qualified, which differs from C.

### When nothing is actually read (¶2)

¶2 When the lvalue-to-rvalue conversion is applied to an expression `E`, the value contained in the referenced object is not accessed if `E` is not potentially evaluated (as in `sizeof`), or if the evaluation of `E` results in the evaluation of a member `Ex` of its set of potential results and `Ex` names a variable `x` that is not odr-used ([[basic.def.odr]]). The second case is mostly about constants: a constexpr variable used in a constant expression is not odr-used, and its value is known at compile time.

```cpp run title="not-accessed.cpp" ub
struct S { int n; };

auto f() {
    S x{1};
    constexpr S y{2};
    return [&](bool b) { return (b ? y : x).n; };
}

int main() {
    auto g = f();
    int n = g(true);     // OK: y.n is not accessed
    int m = g(false);    // UB: accesses x.n, and x's lifetime has ended
    return n + m;
}
```

The potential results of `(b ? y : x).n` include `y.n` and `x.n`. `g(true)` selects `y.n`; `y` is constexpr and not odr-used, so the conversion directly produces the constant 2 without accessing the long-destroyed `y`.

### Result (¶3)

¶3 The result is determined as follows:

- ¶3.1 If `T` is cv `std::nullptr_t`, the result is a null pointer constant. No object is accessed, so even a `volatile` `T` has no side effect, and the glvalue may even refer to an inactive member of a union.
- ¶3.2 If `T` is a class type, the result object is copy-initialized from the glvalue, i.e. the copy constructor is called (the move constructor for an xvalue). Reading a class object is not an access but a constructor call.
- ¶3.3 If the bits in the object's value representation are not valid for its type, the behavior is undefined.
- ¶3.4 Otherwise the object is read ([[defns.access]]). Let `V` be the value contained in the object: if `T` is an integer type, the result is the value of type `T` congruent to `V`; if `T` is `volatile`-qualified and `V` is a pointer value that is invalid in that evaluation, the result is `reinterpret_cast<T>(reinterpret_cast<std::uintptr_t>(V))`; otherwise the result is `V`.

```cpp run title="bad-bool.cpp" ub
#include <cstring>
#include <cstdio>

bool f() {
    bool b = true;
    char c = 42;
    std::memcpy(&b, &c, 1);
    return b;    // UB: 42 is not a valid value representation of bool
}

int main() { std::printf("%d\n", f()); }
```

Run with `-fsanitize=undefined`, UBSan reports `load of value 42, which is not a valid value for type 'bool'`. Without the sanitizer the consequences can be strange: the compiler knows a `bool` is only 0 or 1, and may use it directly to index a two-element table, or let `b` and `!b` both be true.

The congruence rule in ¶3.4 serves access through the corresponding signed/unsigned type (the aliasing that [[basic.lval#11]] allows): reading an `int` object whose value is −1 through a glvalue of `unsigned` gives `UINT_MAX`. The volatile item means that volatile storage may be modified externally, so an invalid pointer read from it is treated like a pointer converted from an integer, and the compiler may not make any assumptions about its origin.

!!! note "Reading uninitialized variables {{c++26}}"
    The rules for reading uninitialized objects are not here but in [[basic.indet]]. Since C++26, an automatic storage duration variable (not marked `[[indeterminate]]`) that is not initialized has an erroneous value, and reading it is erroneous behavior {{erroneous}}: you get some value chosen by the implementation, the implementation may diagnose it, but it is no longer UB. Objects with dynamic storage duration and variables marked `[[indeterminate]]` still have indeterminate values, and reading them is usually UB. If the erroneous value happens not to be a valid value of the type (`bool`, say), it is still UB by the invalid value representation rule above.

    ```cpp eb
    int main() {
        int x;          // C++26: x has an erroneous value
        return x;       // erroneous behavior, not UB
    }
    ```

## Array-to-pointer and function-to-pointer conversions [conv.array] [conv.func]

[conv.array] ¶1 An expression `E` of type "array of `N` `T`" or "array of unknown bound of `T`" can be converted to a pointer to `T`. If `E` is a prvalue, it is materialized first (an array prvalue also needs an object for the pointer to point to). If the result of `E` is an object whose type is similar to the type of `E`, the result points to its first element; otherwise the behavior is undefined.

```cpp ok
using Arr = int[3];
int k = Arr{1, 2, 3}[1];      // the array prvalue is materialized, k == 2
int* dangling = Arr{1, 2, 3}; // well-formed, but the temporary array is destroyed at the end of the full-expression: dangling pointer
```

Clang gives a `-Wdangling` warning for the second line. The final UB rule deals with the case where the type of the expression doesn't match the actual object; with it, the compiler can trust the type of an array expression, including its bound:

```cpp run title="array-ub.cpp" ub
int main() {
    int a3[3] = {1, 2, 3};
    int (&r4)[4] = reinterpret_cast<int(&)[4]>(a3);   // the cast itself is fine
    int* p = r4;    // UB: the object r4 refers to is int[3], not similar to int[4]
    return p[0] - 1;
}
```

[conv.func] ¶1 An lvalue of function type `T` can be converted to a pointer to `T`; the result points to the function. The footnote points out that it never applies to non-static member functions, because there is no way to get an lvalue designating a non-static member function: `obj.mf` can only be called immediately, and `&C::mf` gives a pointer to member, not a function pointer.

```cpp ok
void f(int);
void (*p1)(int) = f;    // function-to-pointer conversion
void (*p2)(int) = &f;   // taking the address: no conversion needed
void (&r)(int) = f;     // binding a function reference: no conversion
auto p3 = *****f;       // each * dereferences the pointer to a function lvalue, which decays to a pointer again
```

## Temporary materialization conversion [conv.rval]

¶1 A prvalue of type `T` can be converted to an xvalue of type `T`. The conversion initializes a temporary object ([[class.temporary]]) of type `T` by evaluating the prvalue with the temporary object as its result object, and produces an xvalue denoting the temporary object. `T` must be a complete type; the note adds that a class type (or array thereof) must also have an accessible, non-deleted destructor.

```cpp ok
struct X { int n; };
int k = X().n;          // X() is a prvalue and member access needs an object: materialized
const X& r = X{42};     // binding a reference: materialized, the temporary's lifetime is extended to that of r
```

Since C++17 a prvalue is not an object itself ([[basic.lval#5]]). When an object is needed and the context doesn't provide a result object, this conversion materializes one. The triggering contexts are listed in [[basic.lval#7]] and [[class.temporary#2]]: binding references, member access, array subscripting and decay, discarded-value expressions, the backing array of a `std::initializer_list`, and so on. The stable name of this subclause, `conv.rval`, is kept from the old name; before C++17 it described a different conversion.

## Qualification conversions [conv.qual]

Qualification conversions allow adding cv to the levels of a pointer (and of pointers to members and arrays). Several concepts it defines are used elsewhere too: the composite pointer type in [[expr.type#3]], reference-related in [[dcl.init.ref]], and similar types in [[basic.lval#11]].

### Qualification-decompositions and similar types (¶1, ¶2)

¶1 Writing a type in the form

> cv<sub>0</sub> P<sub>0</sub> cv<sub>1</sub> P<sub>1</sub> ⋯ cv<sub>n−1</sub> P<sub>n−1</sub> cv<sub>n</sub> U (n ≥ 0)

is called a **qualification-decomposition** of it. Each P<sub>i</sub> is one of "pointer to", "pointer to member of class C<sub>i</sub> of type", "array of N<sub>i</sub>", or "array of unknown bound of". Arrays themselves have no cv, so the element type's cv<sub>i+1</sub> is also taken as the array's cv<sub>i</sub>.

A type can have several decompositions, depending on how many levels you peel off. In the decompositions of `const int**`, `U` can be `int`, "pointer to `const int`", or "pointer to pointer to `const int`". The longest decomposition is:

| cv<sub>0</sub> | P<sub>0</sub> | cv<sub>1</sub> | P<sub>1</sub> | cv<sub>2</sub> | U |
|---|---|---|---|---|---|
| none | pointer to | none | pointer to | `const` | `int` |

¶2 Two types are **similar** ([[g:similar-types|similar]]) if they have decompositions with the same n such that corresponding P<sub>i</sub> are the same (or one is an array of known bound and the other an array of unknown bound), and the `U`s are the same. Intuitively, the two types are the same once cv at every level is removed and array bounds are ignored.

| T1 | T2 | Similar? |
|---|---|---|
| `int**` | `const int* const*` | Yes |
| `int[3]` | `const int[]` | Yes |
| `int B::* const*` | `const int B::**` | Yes |
| `int*` | `unsigned*` | No: different `U` |
| `Derived*` | `Base*` | No |
| `int(*)[3]` | `int**` | No: P<sub>1</sub> is an array in one, a pointer in the other |

### Which conversions are safe

```cpp error
int main() {
    const char c = 'c';
    char* pc;
    const char** pcc = &pc;   // #1: suppose this were allowed (actually an error)
    *pcc = &c;                // through pcc, writes a const char* into the char* slot pc
    *pc = 'C';                // #2: modifies the const object c through pc
}
```

This is the counterexample from the note in the standard. The problem is the intermediate level: the intermediate level of `const char**` is a writable slot holding a pointer to `const char`. Allowing `char**` → `const char**` amounts to allowing a pointer to const to be written into a slot that should only hold pointers to non-const.

The fix: if `const` is added at an inner level, the intermediate levels must be `const` too. `char**` → `const char* const*` is safe, because the intermediate level is not writable and `&c` can't be put there.

### The qualification-combined type (¶3)

¶3 turns this rule into a precise algorithm. The **qualification-combined type** of `T1` and `T2` is the type `T3` similar to `T1` whose decomposition satisfies:

- ¶3.1 for every i > 0, cv3<sub>i</sub> is the union of cv1<sub>i</sub> and cv2<sub>i</sub>;
- ¶3.2 if either P1<sub>i</sub> or P2<sub>i</sub> is "array of unknown bound of", P3<sub>i</sub> is "array of unknown bound of", otherwise it is P1<sub>i</sub>;
- ¶3.3 if the resulting cv3<sub>i</sub> differs from cv1<sub>i</sub> or cv2<sub>i</sub>, or P3<sub>i</sub> differs from P1<sub>i</sub> or P2<sub>i</sub>, then `const` is added to every cv3<sub>k</sub> for 0 < k < i.

A prvalue of type `T1` can be converted to `T2` if the qualification-combined type of `T1` and `T2` is exactly `T2`. In other words, `T1` → `T2` is valid if and only if: the two are similar; at every level `T2` has at least the cv of `T1`, and array bounds can only go from known to unknown; and where some level changed, levels 1 through i−1 outside it are `const` in `T2`. The outermost cv<sub>0</sub> doesn't take part: it is the prvalue's own top-level qualification, which gets removed anyway.

Note 2 points out that for any two similar types, both can be converted to their qualification-combined type; [[expr.type#3]] uses exactly this to define the composite pointer type.

<div class="compare" markdown="1">

```cpp ok
void demo(int** pp, int (*pa)[3]) {
    const int* const* a = pp;
    int* const* b = pp;
    const int (*c)[3] = pa;
    int (*d)[] = pa;       // C++20
    (void)a; (void)b;
    (void)c; (void)d;
}
```

```cpp error
void demo(int** pp,
          int (**ppa)[3]) {
    // error: intermediate level isn't const
    const int** a = pp;
    // error: should be int (* const*)[]
    int (**b)[] = ppa;
}
```

</div>

!!! lawyer "Why dropping an array bound also needs outer const"
    If `int(**)[3]` → `int(**)[]` were allowed, you could write a pointer to an `int[5]` through the latter (`int(*)[5]` converts to `int(*)[]`), and the original `int(*)[3]` slot would point to a 5-element array, corrupting the bound information. This has the same structure as the `const` hole, so the same rule closes it.

¶4 and ¶5 are notes. ¶4 gives the most common single-level case: if *cv2* `T` is more cv-qualified than *cv1* `T`, a pointer to *cv1* `T` can be converted to a pointer to *cv2* `T`, and likewise for pointers to members. ¶5 points out that function types are never cv-qualified ([[dcl.fct]]): the `const` of a member function is part of the function type, not a cv-qualifier, so `void (C::*)()` can't become `void (C::*)() const` through a qualification conversion.

## Integral and floating-point promotions [conv.prom] [conv.fpprom]

```cpp run title="promotion-overload.cpp" ok
#include <cstdio>
int f(int)      { return 1; }
int f(long)     { return 2; }
int f(unsigned) { return 3; }

int main() {
    short s = 1; unsigned short us = 1; char c = 'a'; bool b = true;
    // all select f(int): a promotion beats a conversion
    std::printf("%d %d %d %d\n", f(s), f(us), f(c), f(b));   // 1 1 1 1
}
```

**Integral promotion** ([[g:integral-promotion]]) turns integer types narrower than `int` into `int` or `unsigned int`. It comes from C: `int` corresponds to the machine's natural word size, and arithmetic on narrower types is first widened to `int`. Promotions happen on the operands of arithmetic operations ([[expr.arith.conv]]) and on arguments to variadic functions ([[expr.call]]), and they rank higher than ordinary integral conversions in overload resolution.

### Narrow integers (¶1, ¶2)

¶2 A prvalue that is not a bit-field, whose type is an integer type with integer conversion rank ([[conv.rank]]) less than that of `int` (other than `bool`, `char8_t`, `char16_t`, `char32_t` and `wchar_t`), is promoted to `int` if `int` can represent all the values of the source type, and otherwise to `unsigned int`.

On platforms where `int` is 32 bits, `signed char`, `unsigned char`, `char`, `short` and `unsigned short` are all promoted to `int`. If on some platform `short` is as wide as `int`, `unsigned short` is promoted to `unsigned int`.

¶1 defines a term for bit-fields: a **converted bit-field** is the prvalue obtained by applying the lvalue-to-rvalue conversion to a bit-field. Bit-fields have their own rule (¶5) that looks at the width rather than the declared type.

### Enumerations (¶3, ¶4)

¶3 An unscoped enumeration whose underlying type is not fixed is promoted to the first of `int`, `unsigned int`, `long`, `unsigned long`, `long long`, `unsigned long long` that can represent all the values of the enumeration ([[dcl.enum]]). What counts is the enumeration's range of values, not its underlying type. If none of these can represent them, it is promoted to the extended integer type of lowest rank greater than that of `long long` that can represent all the values (choosing the signed one if there are two).

¶4 An unscoped enumeration whose underlying type is fixed can be promoted to its underlying type; if the underlying type can itself be promoted, it can also be promoted to the promoted type. Both are promotions, but [[over.ics.rank]] says the former is better:

```cpp ok
#include <type_traits>
enum E : short { e };
int  g(short);
long g(int);
static_assert(std::is_same_v<decltype(g(e)), int>);  // selects g(short): promoting to the underlying type is better
static_assert(std::is_same_v<decltype(+e), int>);    // in arithmetic it is promoted further to int
```

The note in ¶4 says that a bit-field of enumeration type is treated like any other value of that type. Scoped enumerations (`enum class`) have no promotions at all.

### Bit-fields (¶5)

¶5 A converted bit-field of integral type is promoted to `int` if `int` can represent all its values, otherwise to `unsigned int` if `unsigned int` can. If neither can, ¶5 doesn't apply, and ¶2 handles it by the rank of the declared type; for example, a 40-bit `unsigned long long` bit-field is not promoted.

```cpp ok
#include <type_traits>
struct BF {
    unsigned a : 3;               // int can represent 0..7 → int
    unsigned u31 : 31;            // int can represent it → int
    unsigned u32 : 32;            // int can't, unsigned can → unsigned
    unsigned long long big : 40;  // neither can → not promoted
};
BF bf;
static_assert(std::is_same_v<decltype(+bf.a), int>);
static_assert(std::is_same_v<decltype(+bf.u31), int>);
static_assert(std::is_same_v<decltype(+bf.u32), unsigned>);
static_assert(std::is_same_v<decltype(+bf.big), unsigned long long>);
```

!!! pitfall "Unsigned bit-fields become signed in arithmetic"
    `unsigned a : 3;` is promoted to `int` in arithmetic, so `bf.a - 4` can be negative, unlike an `unsigned` variable.

### Character types and `bool` (¶6–¶8)

¶6 `char8_t`, `char16_t`, `char32_t` and `wchar_t` (including bit-fields of these types not already promoted above) are promoted to the first of `int`, `unsigned int`, `long`, `unsigned long`, `long long`, `unsigned long long`, or their underlying type, that can represent all the values of the underlying type.

| Type | Underlying type (typical) | Promoted to (32-bit `int`) |
|---|---|---|
| `char8_t` | `unsigned char` | `int` |
| `char16_t` | `uint_least16_t` | `int` |
| `char32_t` | `uint_least32_t` | `unsigned int` |
| `wchar_t` | `int` on Linux and macOS, `unsigned short` on Windows | `int` |

¶7 `bool` can be promoted to `int`: `false` becomes 0 and `true` becomes 1. ¶8 These are collectively called integral promotions.

### Floating-point promotion

[conv.fpprom] ¶1 A `float` can be converted to `double` with the value unchanged; ¶2 this is called **floating-point promotion**. It is the only promotion. `float` → `long double`, `double` → `long double` and conversions involving extended floating-point types are floating-point conversions, which rank lower in overload resolution:

```cpp error
int g(double);
int g(long double);
int h(long double);
int h(int);
int x = g(1.0f);   // selects g(double): a promotion
int y = h(1.0f);   // error: float → long double and float → int are both conversions; ambiguous
```

Arguments to variadic functions also undergo floating-point promotion, so `printf("%f", 1.0f)` receives a `double`, and `%f` works for both `float` and `double` ([[expr.call]]).

## Conversions between arithmetic types [conv.integral] [conv.double] [conv.fpint]

### Integral conversions are always well-defined

[conv.integral] ¶1 An integer type can be converted to another integer type, and an unscoped enumeration can be converted to an integer type. ¶2 For a destination of `bool`, see boolean conversions below; for a source of `bool`, `false` becomes 0 and `true` becomes 1. ¶3 Otherwise:

!!! std
    the result is the unique value of the destination type that is congruent to the source integer modulo 2^N, where N is the width of the destination type.

So integral conversions have neither UB nor implementation-defined behavior:

```cpp run title="modular.cpp" ok
#include <cstdio>
int main(int argc, char**) {
    long long ll = 1LL << 40;
    int i = (int)ll;                             // 2^40 mod 2^32 = 0
    signed char sc = (signed char)(200 * argc);  // 200 - 256 = -56
    unsigned u = -1;                             // UINT_MAX
    std::printf("%d %d %u\n", i, sc, u);         // 0 -56 4294967295
}
```

¶4 Conversions allowed as integral promotions are not integral conversions, so `short` → `int` is a promotion rather than a conversion, which affects overload resolution.

!!! history "Before C++20"
    Before C++20, when converting to a signed type and the value didn't fit, the result was implementation-defined. C++20 requires two's complement representation for signed integers ([[P1236R1]]), and this conversion was then defined as modular. It differs from arithmetic overflow: `INT_MAX + 1` is still UB ([[expr.pre]]), while `(int)(INT_MAX + 1LL)` is well-defined and gives `INT_MIN`.

### Floating-point conversions

[conv.double] ¶1 A floating-point type can be converted to another floating-point type whose floating-point conversion rank ([[conv.rank]]) is greater than or equal to its own; the three standard floating-point types (`float`, `double`, `long double`) can be converted to each other freely. This asymmetry comes from C++23's extended floating-point types ([[P1467R9]]):

- `float` → `double` → `long double`: increasing rank, always implicitly convertible.
- `double` → `float`: both are standard types, so for C compatibility it is implicitly convertible. In list-initialization, though, it is narrowing unless the source is a constant that doesn't overflow after conversion.
- `double` → `std::float16_t`: the destination has lower rank and they aren't both standard types, so there is no implicit conversion; you have to write `static_cast`.
- `std::float32_t` ↔ `float` (when they have the same set of values): equal rank, implicitly convertible.

¶2 If the source value can be exactly represented in the destination type, the result is that value; if the source value is between two adjacent destination values, the result is one of them, which one being implementation-defined (usually round-to-nearest under the current rounding mode); otherwise the behavior is undefined. Whether a `double` beyond the range of `float` (such as `1e300`) counts as lying between the largest finite value and +∞ is not stated explicitly; in practice IEEE implementations give +∞, and Clang also accepts `constexpr float f = 1e300;` during constant evaluation. ¶3 Conversions allowed as floating-point promotions are not floating-point conversions.

### Floating point to integer: out of range is UB

[conv.fpint] ¶1 A floating-point type can be converted to an integer type; the conversion truncates, discarding the fractional part. If the truncated value can't be represented, the behavior is undefined. For a destination of `bool`, see boolean conversions.

```cpp run title="fpint.cpp" ub
#include <cstdio>
int main(int argc, char**) {
    double d = 3e10 * argc;
    int i = (int)d;                          // UB: 3e10 doesn't fit in int
    unsigned ok = (unsigned)(-0.5 * argc);   // OK: truncates to 0
    unsigned bad = (unsigned)(-1.5 * argc);  // UB: truncates to -1, which unsigned can't hold
    std::printf("%d %u %u\n", i, ok, bad);
}
```

UBSan (`-fsanitize=float-cast-overflow`, included in `undefined`) reports `3e+10 is outside the range of representable values of type 'int'`. Conversions between integers are modular, but floating point to integer is UB, and the reason is hardware: x86's `cvttsd2si` returns `0x80000000` when out of range, while ARM's `fcvtzs` saturates to the maximum or minimum (on arm64 in our tests, `i` prints as 2147483647). Making it UB lets the compiler use a single hardware instruction directly. If you need a definite result, check the range first.

¶2 An integer type or unscoped enumeration can be converted to a floating-point type. If the value can be exactly represented, the result is exact; if it is within the representable range but can't be represented exactly, the result is the next lower or higher representable value, which one being implementation-defined; if it is outside the representable range, the behavior is undefined. For a source of `bool`, `false` becomes 0 and `true` becomes 1.

```cpp ok
float f = 16777217;     // 2^24 + 1: float can't represent it exactly; gives 16777216 or 16777218
double d = 1LL << 62;   // exact
```

## Pointer conversions [conv.ptr]

### Null pointer constants (¶1)

```cpp error
int* p1 = 0;            // OK: integer literal with value zero
int* p2 = 0L;           // OK
int* p3 = nullptr;      // OK
const int zero = 0;
int* p4 = zero;         // error: zero isn't a literal (it was fine in C++03)
int* p5 = '\0';         // error: a character literal isn't an integer literal
int* p6 = false;        // error: a boolean literal isn't an integer literal
```

¶1 A **null pointer constant** ([[g:null-pointer-constant]]) is an integer literal with value zero or a prvalue of type `std::nullptr_t`. It can be converted to any pointer type, and the result is the null pointer value of that type ([[basic.compound]]), distinguishable from every value of object pointer or function pointer type. This is called a null pointer conversion.

Two details. First, converting a null pointer constant to a pointer to a cv-qualified type is a single conversion, not a pointer conversion followed by a qualification conversion, which matters for overload resolution. Second, a null pointer constant of integral type can be converted to a prvalue of type `std::nullptr_t`; the note reminds you that the result is not a null pointer value, since `std::nullptr_t` is not a pointer type.

!!! history "Tightening null pointer constants"
    In C++03, a null pointer constant was an integral constant expression with value zero, so `zero`, `'\0'`, `false` and `1 - 1` all counted. That caused trouble in templates: whether a value-dependent expression is a null pointer constant is only known at instantiation, and that in turn changes overload resolution. [[CWG903]] tightened it to integer literals with value zero, as a defect report applying to C++11 and later.

### To `void*` (¶2)

¶2 A pointer to cv `T` (where `T` is an object type) can be converted to a pointer to cv `void`; the pointer value is unchanged. Function pointers can't be implicitly converted to `void*`, and neither can pointers to members (the footnote in [[conv.mem]]).

### Derived to base (¶3)

¶3 A pointer `v` to cv `D` (where `D` is a complete class type) can be converted to a pointer to cv `B`, where `B` is a base class of `D`:

- if `B` is an inaccessible or ambiguous base class of `D`, a program that needs this conversion is ill-formed;
- a null pointer value is converted to a null pointer value;
- if `B` is a virtual base class of `D` (or a base class of a virtual base class) and `v` doesn't point to an object whose type is similar to `D` and that is within its lifetime or under construction or destruction, the behavior is undefined;
- otherwise the result points to the base class subobject of the derived class object.

```cpp error
struct A {}; struct B1 : A {}; struct B2 : A {};
struct D : B1, B2 {};
struct P : private A {};

void demo(D* d, P* p) {
    A* a1 = d;          // error: A is an ambiguous base class of D
    A* a2 = p;          // error: A is an inaccessible base class of P (outside P)
}
```

The virtual base item exists because of implementations. The offset of a non-virtual base is known at compile time, and the conversion just adds a constant; the offset of a virtual base has to be read from the object's vtable, and if the pointer doesn't point to a live `D`, there is no vtable to read:

```cpp run title="vbase.cpp" ub
#include <new>
struct V { int v; };
struct D : virtual V { int d; };

int main() {
    D* p = static_cast<D*>(::operator new(sizeof(D)));   // storage, but no D object
    V* pv = p;          // UB: V is a virtual base, the vtable must be read
    (void)pv;
    ::operator delete(p);
}
```

Built with Clang 23 at `-O0` on arm64, this example segfaults in our tests: the conversion code reads a so-called vtable pointer out of uninitialized storage and then dereferences it.

## Pointer-to-member conversions [conv.mem]

¶1 A null pointer constant can be converted to a pointer-to-member type; the result is the **null member pointer value**, distinguishable from any pointer to member not obtained from a null pointer constant. Likewise, converting to a pointer to member of cv-qualified type is a single conversion, not a pointer-to-member conversion followed by a qualification conversion.

¶2 A pointer to member of `B` of type cv `T` can be converted to a pointer to member of `D` of type cv `T`, where `D` is a complete class derived from `B`:

- if `B` is an inaccessible, ambiguous or virtual base class of `D` (or a base class of a virtual base class), the program is ill-formed;
- if `D` neither contains the original member nor is a base class of the class containing the original member, the behavior is undefined;
- otherwise the result refers to the same member, but as a member of `D`. Dereferencing it with a `D` object is equivalent to dereferencing the original pointer to member with that object's `B` subobject.

```cpp ok
struct B { int x; void mf(); };
struct D : B { int y; };

int D::* pd = &B::x;          // base to derived
void (D::* pmf)() = &B::mf;   // the same for pointers to member functions

int read(D& d) { return d.*pd; }   // reads x in d's B subobject
```

The direction is the opposite of object pointers, and the footnote says this inversion is necessary for type safety. `Derived*` → `Base*` is safe because every `Derived` object contains a `Base`; `int Base::*` → `int Derived::*` is safe because every member of `Base` is also a member of `Derived`. The other way round, an `int Derived::*` might point to a member only `Derived` has, and using it on a `Base` object would go out of bounds.

```cpp error
struct B { int x; };
struct D : B { int y; };
struct VD : virtual B {};

int B::* pb = &D::y;      // error: no implicit conversion in the derived-to-base direction
int VD::* pv = &B::x;     // error: B is a virtual base class
```

Virtual bases are disallowed for a reason similar to pointers: in the Itanium ABI a pointer to data member is just a compile-time constant offset, which can't express a virtual base offset known only at run time.

The UB where `D` doesn't contain the original member can only arise with the help of an explicit conversion:

```cpp ub
struct B {};
struct D1 : B { int x; };
struct D2 : B {};

int main() {
    int B::* pb = static_cast<int B::*>(&D1::x);  // explicit derived-to-base, allowed by static_cast
    int D2::* p2 = pb;   // UB: D2 doesn't contain D1::x and isn't a base class of D1
    (void)p2;
}
```

The footnote finally points out that a pointer to member is neither an object pointer nor a function pointer, so the rules for pointer conversions don't apply to it; in particular, it can't be converted to `void*`.

## Function pointer conversions [conv.fctptr]

¶1 A pointer to a `noexcept` function can be converted to a pointer to function; the result points to the same function. The same goes for pointers to member functions. The direction can only be dropping `noexcept`: a function that promises not to throw can certainly be called as one that might throw, but not the other way round.

<div class="compare" markdown="1">

```cpp ok
void h() noexcept;
void (*fp)() = h;
void (*fp2)() = &h;
struct C { void m() noexcept; };
void (C::*pm)() = &C::m;
```

```cpp error
void (*p)();
// error: can't add noexcept
void (**pp)() noexcept = &p;

struct S {
  typedef void (*fp)();
  operator fp();
};
// error: same as above
void (*q)() noexcept = S();
```

</div>

The right-hand side is adapted from the standard's example. This conversion occupies step 3 of a standard conversion sequence by itself, after pointer conversions and before qualification conversions, and is an Exact Match in overload resolution. C++17 made `noexcept` part of the function type ([[P0012R1]]), so `void() noexcept` and `void()` became different types; this conversion was added at the same time for compatibility with existing code.

## Boolean conversions [conv.bool]

¶1 A prvalue of arithmetic, unscoped enumeration, pointer or pointer-to-member type can be converted to `bool`. A zero value, null pointer value or null member pointer value becomes `false`; any other value becomes `true`.

```cpp error
#include <cstddef>
enum class Color { red };
void f();
int* ptr();

bool a = &f;            // OK (Clang warns: the address of a function is always true)
bool b{ptr()};          // error: pointer to bool is a narrowing conversion
bool c = nullptr;       // error: nullptr_t has no boolean conversion
bool d(nullptr);        // OK: a special case for direct-initialization, d == false
bool e = Color::red;    // error: scoped enumerations have no boolean conversion
bool g{0.5};            // error: floating point to bool is a narrowing conversion
```

Some edge cases:

- `std::nullptr_t` is not in the list, so `bool b = nullptr;` is ill-formed; a special rule in [[dcl.init]] allows the direct-initialization `bool b(nullptr);`, giving `false`.
- Scoped enumerations are not in the list, so `if (scoped_value)` is ill-formed.
- When converting floating point to `bool`, `0.0` and `-0.0` become `false` and NaN becomes `true`.
- In list-initialization, converting a pointer or pointer to member to `bool` is narrowing (item 7.5 of [[dcl.init.list#7]], introduced by [[P1957R2]] as a defect report applying to C++20). Floating point to `bool` is narrowing too, since `bool` is an integer type and this is floating point to integer (item 7.1), and that item has no exception for constants, so even `bool b{0.0};` is ill-formed.

!!! pitfall "A string literal selects `f(bool)`"
    Given `void f(bool); void f(const std::string&);`, `f("hello")` calls `f(bool)`. The string literal decays to a pointer and then undergoes a boolean conversion, which is a standard conversion sequence; converting to `std::string` needs a user-defined conversion. A standard conversion sequence always beats a user-defined conversion sequence. Types that can be implicitly constructed from a string, such as `std::string_view`, have the same problem.

## From the implementation side

!!! impl
    - The lvalue-to-rvalue conversion corresponds to a load instruction; temporary materialization corresponds to reserving storage on the stack; array- and function-to-pointer just take an address. Qualification conversions, function pointer conversions, conversions to `void*` and non-virtual derived-to-base conversions under single inheritance usually generate no code.
    - Derived-to-base conversions under multiple inheritance have to add an offset, and must check for null first (a null pointer stays null after conversion; no offset may be added). So `static_cast<Base2*>(d)` sometimes generates a conditional branch.
    - In the Itanium ABI a pointer to data member is a `ptrdiff_t` offset with −1 as the null value (offset 0 may be a valid member); a pointer to member function takes two words: a function pointer or vtable offset, plus a `this` adjustment. Base-to-derived conversion only needs to adjust the offset or the adjustment. MSVC's pointer-to-member representation is more complex and depends on the class's inheritance model.

## History

!!! history
    - C++98 already had the basic framework. A null pointer constant was an integral constant expression with value zero; out-of-range signed integral conversions gave implementation-defined results.
    - C++11 added `std::nullptr_t`, promotions for `char16_t` and `char32_t`, `explicit` conversion functions, and contextual conversion to `bool`; [[CWG903]] tightened null pointer constants to integer literals.
    - C++14 relaxed contextual implicit conversion to the exactly-one-`T` rule, so a class can also have conversion functions to other non-integral types.
    - C++17: [[P0135R1]] introduced the temporary materialization conversion, and [[P0012R1]] the function pointer conversion.
    - C++20: two's complement made integral conversions modular ([[P1236R1]]); `char8_t` was added ([[P0482R6]]); qualification conversions support array bounds ([[P0388R4]]); pointer to `bool` became narrowing in list-initialization ([[P1957R2]]).
    - C++23 introduced extended floating-point types and floating-point conversion rank ([[P1467R9]]); floating-point conversions changed from any direction to non-decreasing rank or between standard types.
    - New wording after C++23: the lvalue-to-rvalue conversion spells out UB for invalid value representations, the congruent value for integer reads, and the treatment of invalid pointers read from volatile storage; the array-to-pointer conversion adds UB when the object's type isn't similar to the expression's type; pointer conversions add the UB condition for virtual bases.

## Questions

!!! question "Question 1"
    Can `int*` be implicitly converted to `const void*`? Can `int**` be implicitly converted to `const void**` or `void**`?

<details markdown="1">
<summary>Answer</summary>

- `int*` → `const void*`: yes, first a pointer conversion to `void*`, then a qualification conversion to `const void*`, an order that fits a standard conversion sequence.
- `int**` → `const void**`: no. The pointed-to type of `int**` is `int*`; treating it as `void**` means treating an `int*` slot as a `void*` slot, the two aren't similar, and no standard conversion can do it.
- `int**` → `void**`: no, for the same reason. But `int**` → `void*` works, because the pointed-to type `int*` is an object type.
</details>

!!! question "Question 2"
    Given `void f(int); void f(double);`, which does each of `f('a')`, `f(1.0f)` and `f(1L)` call?

<details markdown="1">
<summary>Answer</summary>

- `f('a')`: `char` → `int` is a promotion, `char` → `double` a conversion, so `f(int)`.
- `f(1.0f)`: `float` → `double` is a promotion, `float` → `int` a conversion, so `f(double)`.
- `f(1L)`: `long` → `int` is an integral conversion and `long` → `double` a floating-integral conversion; same rank, ambiguous, ill-formed.
</details>

!!! question "Question 3"
    Is `int* const*` → `const int* const*` valid? What about `int* const*` → `const int**`?

<details markdown="1">
<summary>Answer</summary>

The first is valid. The two are similar; `const` is added at the innermost level, so by the third rule of the qualification-combined type, level 1 must be `const` in the destination, and it is. The qualification-combined type equals the destination type.

The second is not. The destination drops the `const` at level 1, but the combined type's level 1 is still `const` from the union, which differs from the destination. Qualification conversions can only add cv, not remove it.
</details>
