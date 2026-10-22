---
title: Common definitions
summary: "The most basic types and macros in <cstddef> and <cstdlib>: size_t, ptrdiff_t, nullptr_t, NULL, std::byte, max_align_t and offsetof."
updated: 2026-10-19
---

!!! tldr
    - `size_t` is the result type of `sizeof`, and `ptrdiff_t` is the result type of pointer subtraction. Which integer types they are is up to the implementation, and Linux and Windows differ.
    - `NULL` may be `0`, `0L` or `nullptr`, so which overload `f(NULL)` selects isn't portable; write `nullptr`.
    - `std::byte` can access the bytes of any object, like `unsigned char`, but it isn't an arithmetic type and supports only bitwise operations.
    - `alignof(std::max_align_t)` is the upper limit of fundamental alignment; its value varies by platform, so don't hard-code 16.
    - `offsetof` is guaranteed only for standard-layout classes; use with other classes is conditionally-supported.

The properties of these names are all determined by core language rules, and the library just gives them names: `size_t` corresponds to [[expr.sizeof]], `ptrdiff_t` to [[expr.add]], `max_align_t` to [[basic.align]], and `nullptr_t` to [[basic.fundamental]].

## `size_t` and `ptrdiff_t` ([support.types.layout] ¶2–¶4)

¶3 `size_t` is an implementation-defined unsigned integer type that is large enough to contain the size in bytes of any object. [[expr.sizeof]] says the result type of both `sizeof` and `alignof` is `std::size_t`. Since it can hold the size of any object, a type larger than `SIZE_MAX` can't be defined at all; the compiler reports that the array is too large.

¶2 `ptrdiff_t` is an implementation-defined signed integer type that can hold the difference of two subscripts in the same array object. [[expr.add]] says the result type of pointer subtraction is `std::ptrdiff_t`, and the behavior is undefined if the result can't be represented in `ptrdiff_t`. Implementations meet this requirement by limiting the maximum object size; for example, glibc's `malloc` refuses to allocate blocks larger than `PTRDIFF_MAX` bytes.

| Platform | `size_t` | `ptrdiff_t` |
|---|---|---|
| x86-64 and AArch64 on Linux and macOS (LP64) | `unsigned long` | `long` |
| Windows x64 (LLP64) | `unsigned long long` | `long long` |
| Most 32-bit platforms (ILP32) | `unsigned int` | `int` |

¶4 is a recommended practice: the integer conversion ranks ([[conv.rank]]) of `ptrdiff_t` and `size_t` should not be greater than that of `long`, unless a larger type is necessary to contain all the possible values. The recommendation comes from C; the aim is to avoid choosing unnecessarily wide types that make promotions in mixed arithmetic surprising. Windows x64 is a case where a larger type is necessary: `long` there is only 32 bits and can't hold object sizes in a 64-bit address space.

!!! pitfall "Counting down with an unsigned index"
    `for (std::size_t i = v.size() - 1; i >= 0; --i)` is an infinite loop: `size_t` is unsigned, so `i >= 0` is always true. On an empty container, `v.size() - 1` also wraps around to `SIZE_MAX`. C++20's `std::ssize()` returns a signed size and is meant for exactly such cases.

## `nullptr_t` and `NULL` ([support.types.nullptr])

¶1 `nullptr_t` is `decltype(nullptr)`, and its properties are specified by [[basic.fundamental]] and [[conv.ptr]]: it is a distinct fundamental type, neither a pointer type nor a pointer-to-member type, and its value can be converted to the null value of any pointer or pointer-to-member type. Note 1 adds that the address of `nullptr` itself can't be taken, but an lvalue object of type `nullptr_t` can have its address taken:

```cpp run title="nullptr-t.cpp" ok
#include <cstddef>

int main() {
    std::nullptr_t n = nullptr;
    std::nullptr_t* p = &n;      // OK: n is an lvalue
    int* ip = n;                 // OK: converts to a null pointer
    // auto q = &nullptr;        // error: nullptr is a prvalue
    return (p != nullptr && ip == nullptr) ? 0 : 1;
}
```

¶2 `NULL` is an implementation-defined null pointer constant, which must be a literal ([[lex.icon]], [[lex.nullptr]]). Footnote 148 lists possible definitions such as `nullptr`, `0` and `0L`, but not `(void*)0`: that isn't a literal, and C++ doesn't allow `void*` to convert implicitly to other object pointer types, so `int* p = (void*)0;` is ill-formed.

Because the type of `NULL` is up to the implementation, the result of calling an overloaded function with it isn't portable:

```cpp run title="null-overload.cpp" ok
#include <cstddef>

int f(int)   { return 1; }
int f(char*) { return 2; }

int main() {
    // f(NULL);  NULL is 0 → f(int); 0L → ambiguous;
    //           nullptr → f(char*); Clang 23 reports ambiguity
    return f(nullptr);   // always f(char*)
}
```

!!! impl "Clang's and GCC's `__null`"
    In C++ mode, Clang and GCC define `NULL` as `__null` on most platforms. It is an integer constant as wide as a pointer (equivalent to `0L` on LP64), but the compiler knows it stands for a null pointer, so it can give a `-Wnull-conversion` warning for `int x = NULL;`. Clang 23 reports the call `f(NULL)` as ambiguous.

## `std::byte` ([cstddef.syn], [support.types.byteops])

The definition of `std::byte` is a single line:

```cpp
enum class byte : unsigned char {};
```

It is a scoped enumeration with underlying type `unsigned char` and no enumerators. C++17 introduced it to have a type that represents only raw bytes, neither numbers nor characters:

- Like `unsigned char`, it can access the bytes of any object: [[basic.lval]] allows any object to be accessed through an lvalue of type `char`, `unsigned char` or `std::byte`. Arrays of `unsigned char` and `std::byte` can also provide storage for other objects ([[intro.object]]); arrays of `char` can't.
- It isn't an arithmetic type: you can't write `b + 1`, it doesn't convert implicitly to `int`, and it isn't treated as a character when written to `std::cout`. When you need the numeric value, use `std::to_integer<int>(b)`.
- An enumeration with a fixed underlying type can be list-initialized with `T{v}` ([[dcl.init.list]]), so `std::byte{0x2A}` is valid; `std::byte{300}` is a narrowing conversion and ill-formed.

The operations the library provides are all `constexpr` and `noexcept`, and their effects are all written as converting to `unsigned int`, operating, and `static_cast`ing back to `byte`:

| Operation | Constraint | Equivalent to |
|---|---|---|
| `b << n`, `b >> n` (¶3–¶4, ¶7–¶8) | `n` is an integer type | `static_cast<byte>(static_cast<unsigned int>(b) << n)` |
| `l \| r`, `l & r`, `l ^ r` (¶10, ¶12, ¶14) | None | The bitwise operation on two `unsigned int`s, converted back |
| `~b` (¶15) | None | `static_cast<byte>(~static_cast<unsigned int>(b))` |
| Compound assignments `<<=`, `\|=` and so on | As above | `return b = b << n;` and so on |
| `to_integer<T>(b)` (¶16–¶17) | `T` is an integer type | `static_cast<T>(b)` |

```cpp run title="byte-ops.cpp" ok
#include <cstddef>

constexpr std::byte f() {
    std::byte b{0x0F};
    b <<= 4;                         // 0xF0
    b |= std::byte{0x01};            // 0xF1
    return ~b;                       // 0x0E
}
static_assert(std::to_integer<int>(f()) == 0x0E);
static_assert((std::byte{0x80} << 1) == std::byte{0});  // the high bit is cut off

int main() {
    std::byte b{42};
    // int i = b;         // error: a scoped enumeration doesn't convert implicitly
    // auto c = b + 1;    // error: byte has no arithmetic operations
    // auto d = b << 1.0; // error: constraint not satisfied
    int i = std::to_integer<int>(b);
    return i == 42 ? 0 : 1;
}
```

Two details are worth noting. First, when the *Constraints* aren't met, the operator template doesn't participate in overload resolution, so `b << 1.0` is reported as finding no matching operator.

Second, "Equivalent to" means undefined behavior in that code is carried over too. `b << 8` is valid and gives `byte{0}`: when the `unsigned int` result is converted back to `byte`, it is first converted to the underlying type `unsigned char`, keeping only the low 8 bits ([[expr.static.cast]]). `b << 32`, however, is undefined behavior, because the shift amount isn't less than the width of `unsigned int` ([[expr.shift]]), even though the result is about to be truncated to 8 bits. Clang 23 rejects `std::byte{1} << 32` during constant evaluation.

!!! pitfall "`std::byte` can't replace every `unsigned char`"
    C functions taking `void*`, such as `memcpy` and `fwrite`, accept `std::byte*` directly. But `std::string` and `std::string_view` don't accept `std::byte`; and `std::byte` isn't a character type, so an array of `std::byte` can't be initialized with a string literal.

## `max_align_t` ([support.types.layout] ¶5)

!!! std
    The type `max_align_t` is a trivially copyable standard-layout type whose alignment requirement is at least as great as that of every scalar type, and whose alignment requirement is supported in every context.

¶5 The alignment requirement of `max_align_t` is at least as great as that of every scalar type and is supported in every context. It is also a trivially copyable, trivially default constructible standard-layout type.

"Supported in every context" ties it to [[basic.align]]: `alignof(std::max_align_t)` is the upper limit of **fundamental alignment** ([[g:fundamental-alignment]]). Any alignment not exceeding it is a fundamental alignment; anything beyond it is an extended alignment ([[g:extended-alignment]]), and whether and where it is supported is up to the implementation.

A pointer returned by `malloc` is suitably aligned for any type with fundamental alignment. The alignment `operator new(size_t)` guarantees by default is a separate quantity, `__STDCPP_DEFAULT_NEW_ALIGNMENT__` ([[cpp.predefined]]), which can be larger than `alignof(max_align_t)`; for types with stricter alignment, `new` switches to the allocation functions taking a `std::align_val_t` parameter ([[new.delete]]).

```cpp run title="max-align.cpp" impl
#include <cstddef>
#include <cstdio>

int main() {
    std::printf("alignof(max_align_t) = %zu, sizeof = %zu\n",
                alignof(std::max_align_t), sizeof(std::max_align_t));
    std::printf("__STDCPP_DEFAULT_NEW_ALIGNMENT__ = %zu\n",
                static_cast<std::size_t>(__STDCPP_DEFAULT_NEW_ALIGNMENT__));
}
```

On Apple Silicon, Clang defines `max_align_t` as an alias for `long double`, which there is the same as `double`, so the example prints 8, 8 and 16. On x86-64 Linux, `max_align_t` is a struct with `long long` and `long double` members, and it usually prints 16, 32 and 16. A hand-written memory allocator shouldn't hard-code 16.

## `offsetof` ([support.types.layout] ¶1)

`offsetof(type, member-designator)` is an integral constant expression of type `size_t` whose value is the offset in bytes of the member from the start of the class object. ¶1 adds several restrictions to the C semantics:

!!! std
    Use of the `offsetof` macro with a *type* other than a standard-layout class is conditionally-supported.

- Only **standard-layout classes** ([[class.prop]]) are guaranteed. Using `offsetof` with other types is **conditionally-supported** ([[g:conditionally-supported]]): an implementation may not support it, but must issue a diagnostic if it doesn't.
- The result of applying `offsetof` to a static data member or a member function is undefined.
- `offsetof` can't throw an exception; `noexcept(offsetof(type, member-designator))` must be `true`.
- `offsetof(type, member-designator)` is never type-dependent, and its type is always `size_t`; it is value-dependent if and only if *type* is dependent ([[temp.dep.constexpr]]).
- Footnote 149: `offsetof` must work correctly even if the type involved overloads unary `operator&`. So the common C idiom `((size_t)&((T*)0)->m)` can't be used to implement it; Clang and GCC use the built-in `__builtin_offsetof`.

Why restrict it to standard-layout classes? The member layout of a standard-layout class corresponds to a C struct. Once there are virtual functions, virtual base classes or mixed access control, the layout is left to the ABI. The offset of a virtual base class subobject isn't even a constant; it depends on the most derived object type and can only be found at run time by consulting the vtable.

```cpp run title="offsetof.cpp"
#include <cstddef>

struct S  { char c; double d; int operator&() const; };  // overloads unary &
struct V  { virtual ~V(); int x; };                      // has virtual functions, not standard-layout
struct B  { int b; };
struct VB : virtual B { int x; };                        // virtual base class
struct M  { static int s; int f(); int arr[4]; struct { int y; } in; };

static_assert(offsetof(S, d) == alignof(double));  // OK: unaffected by operator&
static_assert(noexcept(offsetof(S, d)));           // OK
constexpr auto e = offsetof(M, arr[2]);            // OK: may have a subscript
constexpr auto g = offsetof(M, in.y);              // OK: may be a nested member
auto v = offsetof(V, x);       // conditionally-supported: Clang accepts with a warning
// auto w = offsetof(VB, b);   // Clang rejects: member of a virtual base
// auto s = offsetof(M, s);    // undefined result: Clang reports an error
// auto f = offsetof(M, f);    // likewise

template<class T>
constexpr auto off = offsetof(T, b);  // value-dependent, but the type is always size_t

int main() { (void)e; (void)g; (void)v; return off<B>; }
```

The line with `V` in this code uses a conditionally-supported feature, so the block as a whole carries no verdict. Clang 23 accepts it with a `-Winvalid-offsetof` warning, and rejects the virtual base member outright with "invalid application of 'offsetof' to a field of a virtual base". Supporting part of it and diagnosing the unsupported part is exactly what conditionally-supported means.

!!! pitfall "A member designator isn't an expression"
    *member-designator* follows the C grammar: an identifier, optionally followed by `.identifier` or `[constant-expression]`. Also, `offsetof` is a macro, so in `offsetof(std::pair<int, int>, first)` the comma in the template argument list is taken by the preprocessor as a separator between macro arguments; give the type an alias first.

## The headers `<cstddef>` and `<cstdlib>`

The synopsis in [cstddef.syn] begins with "all freestanding": all of `<cstddef>` must be provided by freestanding implementations ([[g:freestanding-implementation]]) too. ¶1 says it is the same as C's `<stddef.h>`, with a few differences: it doesn't declare `wchar_t`, which is a keyword in C++; it doesn't define C23's `unreachable` macro, since C++ uses `std::unreachable()` from `<utility>`; it additionally declares `std::byte` and its operations; and `NULL` and `offsetof` have the restrictions described above.

`<cstdlib>` in [cstdlib.syn] corresponds to C's `<stdlib.h>`, and its contents are a miscellany: program termination (`exit`, `atexit` and others; see [[support.start.term]]), the `malloc` family ([[c.malloc]]), numeric conversions such as `strtol`, `qsort` and `bsearch` ([[alg.c.library]]), `rand`, `abs` and `div`. ¶1 says it doesn't declare `wchar_t`, `once_flag` or `call_once`; C++ uses `std::call_once` from `<mutex>`. Note 1 explains that some functions have additional overloads in C++, for example `abs` has floating-point versions, but their behavior is the same as in the C library.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

The synopsis of `<cstdlib>` uses four exposition-only function type aliases: `c-atexit-handler` and `atexit-handler` are both `void()`, the former with C language linkage and the latter with C++ language linkage; `c-compare-pred` and `compare-pred` likewise. So `atexit`, `at_quick_exit`, `qsort` and `bsearch` each have two overloads. The reason is that, by [[dcl.link]], language linkage is part of a function type, and C and C++ functions could in principle have different calling conventions. Clang and GCC don't make language linkage part of the function type, a long-standing deviation of theirs, so in practice you never notice these two overloads.

The synopsis also declares `abs`, `labs`, `div` and others `constexpr`, which C++23 requires. libc++ (with Clang 23) hasn't implemented this yet: `constexpr int y = std::abs(-1);` is an error.

</details>

## Questions

!!! question "Questions"
    1. Can `offsetof(A, x)` be used portably with `struct A { int x; private: int y; };`?
    2. Is `std::byte b{1}; auto r = b << 31;` valid?
    3. Why can't `NULL` be defined as `(void*)0`, while it can be defined as `nullptr`?

<details markdown="1">
<summary>Answer</summary>

1. It isn't guaranteed. The non-static data members of `A` have different access control, so by [[class.prop]] it isn't a standard-layout class, and `offsetof` is conditionally-supported. Clang 23 accepts it with a `-Winvalid-offsetof` warning, but the standard doesn't guarantee that every implementation accepts it.
2. Valid, and the result is `byte{0}`. By [support.types.byteops] ¶4, it is equivalent to `static_cast<byte>(static_cast<unsigned int>(b) << 31)`. With a 32-bit `unsigned int`, `1u << 31` is `0x80000000`, and converting back to `byte` keeps only the low 8 bits, i.e. 0. Writing `b << 32` would be undefined behavior under [[expr.shift]].
3. [support.types.nullptr] ¶2 requires `NULL` to be a null pointer constant that is a literal. `(void*)0` isn't a literal, and its type is `void*`; C++ doesn't allow `void*` to convert implicitly to other object pointer types, so `int* p = NULL;` wouldn't compile. `nullptr` is a pointer literal ([[lex.nullptr]]) and meets both requirements.
</details>
