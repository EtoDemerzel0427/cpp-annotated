---
title: Literals
summary: "What the seven kinds of literals are and which value category each has as an expression, plus the two simplest: the Boolean literals true/false and the pointer literal nullptr."
updated: 2026-10-19
---

!!! tldr
    - There are seven kinds of literals: integer, character, floating-point, string, Boolean, pointer and user-defined.
    - A string literal is an lvalue, a user-defined literal has the value category of the corresponding operator call, and all other literals are prvalues.
    - `-1` is not a literal but unary `-` applied to the literal `1`.
    - `true` and `false` have type `bool`, and keep their values in `#if` rather than being replaced by 0.
    - `nullptr`'s type `std::nullptr_t` is not a pointer type; it converts to any pointer but not to an integer, so overload resolution never treats it as an `int`.

A **literal** is a value written directly in the source, such as `42`, `'a'` or `"abc"`. Chapter 5 specifies only a literal's spelling, type and value; whether it is an lvalue or an rvalue as an expression is specified by [[expr.prim.literal]].

## The seven kinds of literals ([[lex.literal.kinds]])

¶1 The grammar divides literals into seven kinds, five of which have their own pages:

| Kind | Examples | Page |
|---|---|---|
| Integer literal | `42`, `0x2A`, `0b101`, `1'000uz` | [[lex.icon]] |
| Character literal | `'a'`, `u8'x'`, `L'w'`, `'\n'` | [[lex.ccon]] |
| Floating-point literal | `3.14`, `1e-9f`, `0x1p-3` | [[lex.fcon]] |
| String literal | `"abc"`, `R"(raw)"`, `u8"x"` | [[lex.string]] |
| Boolean literal | `true`, `false` | this page |
| Pointer literal | `nullptr` | this page |
| User-defined literal | `12_km`, `"abc"s` | [[lex.ext]] |

### Value categories

Note 1 points out that a literal appearing as an expression has a type and a value category. [[expr.prim.literal]] specifies:

- a string literal is an **lvalue** designating a string literal object with static storage duration ([[lex.string]]);
- a user-defined literal has the same value category as the corresponding literal operator call ([[lex.ext]]);
- all other literals are prvalues.

A string literal is an lvalue because it really does correspond to an array object in memory, so its address can be taken and it can be bound to a reference to array.

```cpp run title="literal-categories.cpp" ok
#include <type_traits>
#include <cstddef>
// decltype((e)) gives a reference type for an lvalue and a non-reference type for a prvalue
static_assert(std::is_same_v<decltype(("abc")), const char(&)[4]>);
static_assert(std::is_same_v<decltype((42)), int>);
static_assert(std::is_same_v<decltype(true), bool>);
static_assert(std::is_same_v<decltype(nullptr), std::nullptr_t>);
const char (*p)[4] = &"abc";   // OK: a string literal is an lvalue, so its address can be taken
int main() {}
```

### Negative numbers are not literals

The grammar has no minus sign. `-1` is the unary operator `-` applied to the integer literal `1`. This affects the type: the type of `-2147483648` is determined by `2147483648`, which on a platform with 32-bit `int` is `long` or `long long`, not `int` (see [[lex.icon]]). This is also why `INT_MIN` is usually defined as `(-2147483647 - 1)`.

### Literals and constant expressions are not the same thing

Literal is a lexical concept; constant expression is a semantic one ([[expr.const]]). `42` is both; `std::numeric_limits<int>::max()` is a constant expression but not a literal. A **literal type** ([[basic.types.general]]) is yet another concept, meaning a type that can be used in constant evaluation; it merely has a similar name.

## Boolean literals ([[lex.bool]])

¶1 The Boolean literals are the keywords `false` and `true`, with type `bool`.

In arithmetic they become the `int` values 0 and 1 by integral promotion ([[conv.prom]]), so `true + true == 2`.

The preprocessor knows them too. When `#if` is evaluated, all identifiers and keywords remaining after macro expansion are replaced by 0, except `true` and `false` ([[cpp.cond]]). So `#if true` holds in C++.

```cpp run title="bool-literal.cpp" ok
static_assert(true + true == 2);     // promoted to int
#if true && !false                   // the preprocessor keeps the values of true/false
static_assert(sizeof(true) == sizeof(bool));
#endif
int main() {}
```

C made `true` and `false` keywords only in C23; before that they were macros in `<stdbool.h>` with the `int` values 1 and 0.

## The pointer literal ([[lex.nullptr]])

¶1 The pointer literal is the keyword `nullptr`, with type `std::nullptr_t`.

Note 1 adds the properties of this type: `std::nullptr_t` is a distinct type that is neither a pointer type nor a pointer-to-member type. A prvalue of this type is a **null pointer constant** and can be converted to a null pointer value of any pointer type or a null member pointer value of any pointer-to-member type ([[conv.ptr]], [[conv.mem]]).

### Why `nullptr` is needed

Before C++11, a null pointer constant could only be an integer literal with value 0, such as `0` or `0L`. Its type was an integer type, and overload resolution treated it as an integer:

```cpp title="null-overload.cpp" error
#include <cstddef>
void f(int);
void f(char*);
void g() {
  f(0);         // picks f(int), probably not what was intended
  f(NULL);      // error: with Clang 23 NULL is __null, and the two overloads are ambiguous
  f(nullptr);   // OK: picks f(char*)
}
```

The definition of `NULL` is up to the implementation ([[support.types.nullptr]]); it may be `0`, `0L` or the compiler built-in `__null`, so `f(NULL)` may pick `f(int)` on one platform and be ambiguous on another. Clang 23 reports an ambiguity.

`std::nullptr_t` converts implicitly to any pointer type but not to integer types, so `f(nullptr)` has only one viable function. In template argument deduction, `nullptr` deduces `std::nullptr_t` while `0` deduces `int`, so the meaning of a null pointer is not lost even through perfect forwarding.

### Other properties of `std::nullptr_t`

[[basic.fundamental#16]] specifies that `std::nullptr_t` has the same size and alignment as `void*`; its value representation may contain no bits at all, since all its values are the same. `<cstddef>` defines the name with `decltype(nullptr)`.

Variables of type `std::nullptr_t` can be defined. The value read from one is a `std::nullptr_t` prvalue, which is also a null pointer constant, so it too converts to any pointer.

Conversion to `bool` is allowed only in direct-initialization ([[dcl.init.general#15.8]]), with result `false`:

<div class="compare" markdown="1">

```cpp ok
bool a{nullptr};   // OK: direct-initialization, false
```

```cpp error
bool b = nullptr;  // error: copy-initialization
```

</div>

Clang still gives a `-Wnull-conversion` warning for the left one, because this form is almost always a typo.

!!! history
    `nullptr` was introduced in C++11 ([[N2431]]). C23 also introduced `nullptr` and `nullptr_t`, with semantics essentially the same as C++.

## Common misconceptions

!!! pitfall "String literals are rvalues"
    `"abc"` is an lvalue of type `const char[4]`; its address can be taken and it can be bound to `const char(&)[4]`. In most contexts it becomes a `const char*` prvalue, but that is the result of the array-to-pointer conversion, not the value category of the literal itself.

!!! pitfall "`nullptr` is a pointer"
    `std::is_pointer_v<std::nullptr_t>` is `false`. `nullptr` cannot be dereferenced, and `std::nullptr_t` is not any `T*`. It merely converts to pointers.

## Questions

!!! question "Question"
    What is the type and value category of each expression below?

    ```cpp
    'a'      u8"x"      nullptr      -1      true      1.0f
    ```

<details markdown="1">
<summary>Answer</summary>

- `'a'`: a `char` prvalue.
- `u8"x"`: a `const char8_t[2]` lvalue.
- `nullptr`: a `std::nullptr_t` prvalue.
- `-1`: not a literal but a unary `-` expression, an `int` prvalue.
- `true`: a `bool` prvalue.
- `1.0f`: a `float` prvalue.
</details>
