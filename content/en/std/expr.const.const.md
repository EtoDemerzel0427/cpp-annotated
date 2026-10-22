---
title: Constant expressions
summary: "What else a core constant expression must satisfy to be a constant expression; which conversions are allowed in the converted constant expressions required by array bounds, template arguments, case labels and the like; values that can exist only at compile time and immediate objects in C++26."
updated: 2026-10-19
---

!!! tldr
    - A core constant expression only constrains the evaluation. To be a constant expression, its result must also contain no invalid pointers (for example to a destroyed local variable), indeterminate values or erroneous values.
    - Array bounds, `case` labels, constant template arguments and the like require converted constant expressions: only implicit conversions that lose no information are allowed; narrowing and conversions between integers and floating-point are not.
    - The conditions of `noexcept(...)` and `explicit(...)` cannot be integers narrowed to `bool`; those of `static_assert` and `if constexpr` can, since C++23.
    - In C++26, reflection values and pointers to `consteval` functions are meaningful only at compile time. Objects containing such values can only live in constexpr variables, template arguments, or inside a single constant evaluation.

## The evaluation is fine, but the result can't be used (¶4)

```cpp
constexpr int* dang() {
  int x = 0;
  return &x;                      // returns the address of a local variable
}
constexpr int* dp = dang();       // error: the result is an invalid pointer value

struct S {
  int x;
  constexpr S() {}                // doesn't initialize x
};
int f() {
  constexpr S s;                  // error: s.x is an erroneous value
  return 0;
}
```

There is nothing wrong with the evaluation of `dang()`: taking the address of a local variable and returning it are not on the list of prohibitions for a [[expr.const.core|core constant expression]]. The problem is the result: a pointer to a destroyed object is carried out of the evaluation. So the standard needs a separate rule for results.

!!! std
    A core constant expression is a constant expression unless it is a prvalue whose result object has a constituent value that is an invalid pointer value or is indeterminate or erroneous.

¶4 A core constant expression is a **constant expression** unless it is a prvalue and the [[g:constituent-values|constituent values]] of its result object (all the values obtained by expanding the object down to each scalar subobject, [[intro.object]]) include one of three kinds of value:

1. an **invalid pointer value** ([[basic.compound]]): one pointing to storage whose duration has ended, typically coming from something like `dang()` above;
2. an [[g:indeterminate-value|indeterminate value]] ([[basic.indet]]);
3. an [[g:erroneous-value|erroneous value]] {{c++26}}: the value uninitialized automatic variables have by default in C++26 ([[P2795R5]]). `s.x` above is such a case; in C++23 it would be an indeterminate value.

!!! history "Permitted results"
    In C++23 and earlier, this was a long specification of the permitted results of a constant expression: a glvalue had to refer to an object with static storage duration or to a function, and pointers in a prvalue had to point to objects with static storage duration or functions, or be null.

    C++26's [[P2686]] moved the static-storage-duration requirement out, turning it into a requirement on variables, namely being constexpr-representable ([[expr.const.init#3]]). Whether something is a constant expression now depends only on whether its value is determined; whether it can be stored in a particular constexpr variable depends on where that variable is. `constexpr int* p = &local;` inside a function has a definite meaning, while a constexpr pointer at namespace scope must point to an object with static storage duration.

Note 1 (after paragraph 5) reminds us that a glvalue core constant expression that refers or points to an unspecified object is not a constant expression. This concerns references of unknown value ([[expr.const.core#9]]): in `void f(int& r) { constexpr int* p = &r; }`, `r` is treated as bound to an unspecified object, and `&r` cannot be the result of a constant expression.

## Converted constant expressions (¶8)

```cpp
template<char C>   struct TC {};
template<bool B>   struct TB {};
template<int N>    struct TI {};
template<double D> struct TD {};
template<const int& R> struct TR {};

TC<65>  c1;    // OK: int → char, 65 is representable
TC<300> c2;    // error: 300 can't be represented as char, narrowing
TB<2>   b1;    // error: 2 → bool is narrowing
TI<2.0> i1;    // error: floating → integer not allowed
TD<1>   d1;    // error: integer → floating not allowed

long gl = 0;
TR<gl>  r1;    // error: would bind to a temporary, not directly
```

Constant template arguments, array bounds, `case` labels, array lengths in *new-expression*s, the initializers of enumerators of enumerations with fixed underlying types, and C++26's *splice-specifier*s all require a **converted constant expression** (Note 3).

¶8 A converted constant expression of type T is an expression implicitly converted to T, where the converted expression is a constant expression and the implicit conversion sequence contains only the conversions listed below; if a reference binding is involved, it must bind directly, not to a temporary.

| Allowed conversion | Item | Remarks |
|---|---|---|
| User-defined conversions | 8.1 | The selected conversion function or constructor must be callable in constant evaluation |
| Lvalue-to-rvalue, array-to-pointer, function-to-pointer | 8.2–8.4 | |
| Qualification conversions | 8.5 | Adding `const` |
| Integral promotions | 8.6 | |
| Integral conversions other than narrowing | 8.7 | Not narrowing if the value is representable in the target type ([[dcl.init.list]]) |
| Floating-point promotions | 8.8 | `float` → `double` |
| Floating-point conversions where the source value is exactly representable | 8.9 | `double` 1.0 → `float` is fine, 0.1 is not |
| From `std::nullptr_t` to null pointer and null member pointer | 8.10–8.11 | |
| Function pointer conversions | 8.12 | Dropping `noexcept` |

Conversions not in the table are not allowed: conversions between integers and floating-point, derived-to-base pointer conversions, pointer to `void*`, pointer to `bool`, and narrowing integral conversions.

Why so strict? These places need an exact value. Template arguments determine whether types are the same; if `TC<300>` silently became `TC<44>`, two arguments that look different would give the same type. Forbidding narrowing follows the same idea as list-initialization ([[dcl.init.list]]).

```cpp
template<float F> struct TF {};
TF<1.0> f1;    // OK by the standard: 1.0 is exactly representable as float
TF<0.1> f2;    // error: 0.1 is not
```

!!! impl "Clang's deviation"
    Clang 23 also rejects `TF<1.0>` (`conversion from 'double' to 'float' is not allowed in a converted constant expression`); it doesn't yet implement the exactly-representable floating-point conversions allowed by item 8.9.

### `case` labels: promote first, then convert

The target type of a `case` label is the type of the `switch` condition after integral promotion ([[stmt.switch]]):

```cpp ok
void sw(unsigned char c) {
  switch (c) {          // the condition is promoted to int
  case 1000: break;     // OK: 1000 is an int, no narrowing
  }
}
```

Many people think `case 1000` is a narrowing error for `unsigned char`. Actually the target type is `int`, and this `case` simply never matches.

### User-defined conversions

Item 8.1 allows user-defined conversions, so objects of literal class type can be used as array bounds or `case` labels:

```cpp ok
struct Idx {
  int v;
  constexpr operator int() const { return v; }
};
constexpr Idx three{3};
int arr[three];              // Idx → int → std::size_t, 3 is representable
void sw(int x) {
  switch (x) { case Idx{1}: break; }
}
```

## Contextually converted constant expressions of type bool (¶9)

```cpp
struct S { explicit(2) S(int); };   // error: 2 → bool is narrowing
void f() noexcept(2);               // error: likewise
static_assert(2);                   // OK: doesn't use this definition
void g() { if constexpr (2) {} }    // OK: likewise
```

¶9 A **contextually converted constant expression of type bool** is an expression that, contextually converted to `bool` ([[conv]]), is a constant expression, with a conversion sequence containing only the conversions listed in paragraph 8. `noexcept(...)` ([[except.spec]]) and `explicit(...)` ([[dcl.fct.spec]]) use this definition, so the narrowing `2 → bool` is not allowed.

!!! history "Relaxing static_assert and if constexpr"
    In C++17 and C++20, the condition of `if constexpr` was also a contextually converted constant expression of type bool, so `if constexpr (N % 4)` and `if constexpr (sizeof(T) & 1)` were invalid because of narrowing and had to be written with `!= 0`. C++23's [[P1401R5]] changed `static_assert` and `if constexpr` to require only that the converted expression be a constant expression, with no restriction on narrowing ([[dcl.pre#13]], [[stmt.if#2]]); `noexcept` and `explicit` were left unchanged. Mainstream compilers apply this change in earlier language modes too.

## Integral constant expressions (¶6–¶7)

¶6 An **integral constant expression** is an expression of integral or unscoped enumeration type that, implicitly converted to a prvalue, is a core constant expression. An integral value cannot be an invalid pointer, so a core constant expression is enough. Bit-field lengths ([[class.bit]]), enumerator initializers of enumerations without a fixed underlying type ([[dcl.enum]]) and alignment values (`alignas`) use this definition (Note 2).

¶7 If an expression of literal class type is used where an integral constant expression is required, it is contextually implicitly converted to an integral or unscoped enumeration type ([[conv]]), and the selected conversion function must be constexpr. This conversion requires exactly one viable target type; otherwise it is ambiguous:

```cpp error
struct A {
  constexpr A(int i) : val(i) { }
  constexpr operator int() const { return val; }
  constexpr operator long() const { return 42; }
private:
  int val;
};
constexpr A a = alignof(int);
alignas(a) int n;              // error: convert to int or to long?
struct B { int n : a; };       // error: likewise
```

## Values that can exist only at compile time (¶1–¶3, ¶5) {{c++26}}

```cpp
consteval int plus1(int x) { return x + 1; }
template <auto V> struct C {};

auto a = plus1;              // error: a run-time variable holds a pointer to a consteval function
constexpr auto b = plus1;    // OK
auto c = C<plus1>();         // OK: template parameter object

auto d = ^^int;              // error: a reflection value enters a run-time variable
auto e = C<^^char>();        // OK
```

A `consteval` function is also called an [[g:immediate-function|immediate function]]: it is only called at compile time, generates no code, and has no address at run time. A reflection value (the result of `^^int`, of type `std::meta::info`) is a handle to the compiler's internal data and doesn't exist at run time either. Once such a value gets into a run-time object, the program holds something that doesn't exist.

¶1 The following two kinds of values are called **consteval-only values** ([[g:consteval-only-value|consteval-only value]]):

- non-null reflection values ([[basic.fundamental]]);
- pointers or pointers to members that point to an immediate function, or to (or past the end of) an immediate object.

¶2 An object is an **immediate object** ([[g:immediate-object|immediate object]]) if its complete object has a constituent value that is consteval-only, or a constituent reference that refers to an immediate object or immediate function. A single non-null `std::meta::info` member anywhere deep inside a struct makes the whole complete object an immediate object.

¶3 Every immediate object must be one of the following:

- the object associated with a constexpr variable, or a subobject of it;
- a template parameter object ([[temp.param]]) or a subobject of it;
- an object whose lifetime begins and ends within the evaluation of a core constant expression.

All three exist only at compile time: the compiler knows the entire value of a constexpr variable, template arguments are part of a type, and temporaries inside an evaluation are gone when the evaluation ends.

Paragraph 3 also requires that an expression that odr-uses a variable declaring or referring to an immediate object be in an [[g:immediate-function-context|immediate function context]] ([[expr.const.imm#1]], for example inside an immediate function body or in the condition of a `static_assert`). A diagnostic is required only when the innermost declaration containing the expression and the definition of the variable are such that one is reachable from the other (3.4–3.5). With modules or multiple translation units, the compiler may not see the variable's definition at the point of use and cannot know that it refers to an immediate function.

```cpp
consteval int plus1(int x) { return x + 1; }
constexpr auto b = plus1;
int use(int n) { return b(n); }   // error: an immediate object used in an ordinary function
static_assert(b(1) == 2);         // OK: the condition of static_assert is an immediate function context
```

¶5 A constant expression is an **immediate constant expression** ([[g:immediate-constant-expression|immediate constant expression]]) if it is a glvalue referring to an immediate object or immediate function, or a prvalue whose result object is an immediate object. [[expr.const.imm#2]] uses it to decide immediate escalation: if a function such as a template instantiation contains an immediate constant expression that is not in an immediate function context, that function itself becomes an immediate function. `use` in the example above is not such an escalating function, so it is an error.

```cpp
consteval int f() { return 42; }
consteval auto g() { return f; }              // returns a pointer to an immediate function
consteval int h(int (*p)() = g()) { return p(); }
constexpr int r = h();                        // OK: the pointer is only passed around inside immediate functions
constexpr auto e = g();                       // marked error in the standard's example
```

`r` is valid because the result of the default argument `g()` is used only inside `h`, and the final result is an `int`.

!!! lawyer "`e` in Example 2"
    The comment on `e` in the standard's example says a pointer to an immediate function is not a permitted result of a constant expression. That is the C++23 terminology, and paragraph 4 no longer has the notion of permitted results. Reasoning by the C++26 rules: the initializer of a constexpr variable is manifestly constant-evaluated, and `g()` is in an immediate function context; the object associated with `e` is an immediate object, which item 3.1 allows to belong to a constexpr variable. This is the same reasoning that makes `constexpr auto b = plus1;` valid. The comment is most likely a leftover that was not updated when paragraphs 1–3 were rewritten.

!!! impl "Implementation status"
    None of the examples in this section can be verified with Clang 23. It doesn't implement reflection (`^^`), and it still rejects `constexpr auto b = plus1;`, `C<plus1>` and `e` under the C++23 rules, reporting `cannot take address of consteval function 'plus1' outside of an immediate invocation`.

## Implementation view

!!! impl "Address constants are symbolic values"
    `constexpr int* p = &global;` is a constant expression, but its value is not a number; it is the address of `global`. In the object file the initial bytes of `p` are usually 0, with a relocation record telling the linker or loader to fill in the final address of `global`; in position-independent executables and shared libraries, the address is determined only at load time. That is why a pointer cannot be converted to an integer in a constant expression (that would need `reinterpret_cast`, see [[expr.const.core#2.16]]): the integer isn't known at compile time.

## Common misconceptions

!!! pitfall "A `const int` can always be used as a constant"
    Whether `n` in `const int n = f();` can be used as an array bound depends on whether `f()` can be evaluated at compile time. Add one non-constexpr logging call to `f`, and a distant `int a[n];` turns into a variable-length array (a GCC and Clang extension) or a compile error. When you need a constant, write `constexpr`. See [[expr.const.init]].

## Questions

!!! question "Question 1"
    Which of the following template arguments are valid?

    ```cpp
    template<unsigned N> struct U {};
    U<-1> u1;
    U<'a'> u2;
    U<sizeof(int)> u3;
    U<true> u4;
    ```

<details markdown="1">
<summary>Answer</summary>

- `U<-1>` is invalid. `int` → `unsigned` is an integral conversion, and -1 cannot be represented as `unsigned`, so it is narrowing.
- `U<'a'>` is valid. `char` promotes to `int`, not `unsigned`, so this is an integral conversion; 97 is representable, so it is not narrowing.
- `U<sizeof(int)>` is valid. `std::size_t` → `unsigned` converts from a wider type, but the source is a constant expression whose value is representable, so it is not narrowing ([[dcl.init.list]]).
- `U<true>` is valid. `bool` → `unsigned` is an integral conversion, `true` becomes 1 ([[conv.integral#2]]), and it is not narrowing.

Clang 23 rejects only `U<-1>`.
</details>

!!! question "Question 2"
    Converted constant expressions allow `float` → `double`; why not `int` → `double`? Isn't every 32-bit `int` value exactly representable as `double`?

<details markdown="1">
<summary>Answer</summary>

The allowed conversions all stay within the same category: integer to integer, floating to floating, qualification adjustments of pointers. Conversions between integers and floating-point ([[conv.fpint]]) are not on the list, even when the value is exactly representable. The rule is simple and predictable: the template arguments `TD<1>` and `TD<1.0>` differ in spelling, and the standard requires the programmer to write `1.0`. Floating-to-floating conversions, by contrast, are allowed whenever the source value is exactly representable (item 8.9).
</details>

## Summary

| Name | Requirement | Used where |
|---|---|---|
| Constant expression | A core constant expression whose result contains no invalid pointers, indeterminate values or erroneous values | constexpr variables and other places that generally require constants |
| Converted constant expression | Only conversions that lose no information; references must bind directly | Array bounds, `case`, constant template arguments, enumerators with fixed underlying type, *splice-specifier* |
| Contextually converted constant expression of type bool | As above, with target type `bool` | `noexcept(...)`, `explicit(...)` |
| Integral constant expression | Integral or unscoped enumeration, a core constant expression suffices; class types need a unique constexpr conversion | Bit-field lengths, enumerators without fixed underlying type, `alignas` |
| Immediate constant expression {{c++26}} | The result is an immediate object or immediate function | Deciding immediate escalation ([[expr.const.imm]]) |
| Conditions of `static_assert` and `if constexpr` | A constant expression after conversion to `bool`; narrowing allowed | Since C++23 |
