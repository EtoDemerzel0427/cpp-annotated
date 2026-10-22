---
title: Three-way comparison operator
summary: "Built-in <=> gives strong_ordering for integers and partial_ordering for floating-point; it rejects comparing bool with other types, signed/unsigned comparisons that need narrowing, two arrays, and function pointers; <compare> must be included before use."
updated: 2026-10-19
---

!!! tldr
    - `a <=> b` tells you in one comparison whether one side is less, equal, greater, or unordered; the result is a comparison category type from `<compare>`: integers and pointers give `std::strong_ordering`, floating-point gives `std::partial_ordering`.
    - Built-in `<=>` is stricter than `<`: `bool` cannot be compared with other types; if the usual arithmetic conversions would need a narrowing conversion (typically `int` against `unsigned`), the program is ill-formed. Integral-to-floating conversions are the exception.
    - Values of the same enumeration type compare by their underlying type, scoped enumerations included; object pointers compare via the composite pointer type, while two arrays, function pointers, pointers to members and `nullptr` are all rejected.
    - The comparison category types are not built into the language: using built-in `<=>` without including `<compare>` (or `import std;`) makes the program ill-formed.

`<=>` was introduced in C++20 by [[P0515R3]] and is often called the spaceship operator. Its main use is with class types: one line, `auto operator<=>(const T&) const = default;`, generates all the relational comparisons ([[class.spaceship]]), and `a < b` can be rewritten as `(a <=> b) < 0` ([[over.match.oper]]). This subclause covers only the built-in `<=>`, where the operands are arithmetic types, enumerations, or object pointers.

## What the result is (¶1, ¶2, ¶4)

```cpp run title="spaceship-arith.cpp" ok
#include <compare>
#include <limits>
#include <type_traits>

static_assert(std::is_same_v<decltype(1 <=> 2), std::strong_ordering>);
static_assert(std::is_same_v<decltype(1 <=> 2.0), std::partial_ordering>);
static_assert((-1 <=> 1L) < 0);
static_assert(std::is_eq(-0.0 <=> 0.0));                    // equivalent
static_assert((std::numeric_limits<double>::quiet_NaN() <=> 1.0)
              == std::partial_ordering::unordered);

int main() {}
```

¶2 `p <=> q` is a prvalue indicating whether `p` is less than, equal to, or greater than `q`, or that they are unordered. The type of the result is a **comparison category type** ([[g:comparison-category-type]], [[cmp.categories]]), determined by the operand types. To use it, compare the result against the literal `0`, or use helpers such as `std::is_lt` and `std::is_eq`.

¶4 If both operands have arithmetic types, the usual arithmetic conversions ([[expr.arith.conv]]) are applied first, and then:

- ¶4.2 For integral types the result is `std::strong_ordering`, giving `less`, `equal` or `greater` according to the mathematical values.
- ¶4.3 For floating-point types the result is `std::partial_ordering`, giving `less`, `greater`, `equivalent` or `unordered`. It is `unordered` when a NaN is involved, because a NaN cannot be compared with any value, including itself.

`partial_ordering` has no value called equal, only equivalent, so `-0.0 <=> 0.0` is `equivalent`. Built-in `<=>` never produces `std::weak_ordering`; that is left to user-defined types, such as case-insensitive strings.

¶1 `<=>` groups left-to-right, with precedence between the shift and relational operators. So `a <=> b < 0` parses as `(a <=> b) < 0`, which is exactly the idiomatic way of using the result.

## Where it is stricter than `<`

Built-in `<` inherited several error-prone mixed comparisons from C. The new operator has no compatibility baggage, so it simply rejects them.

### `bool` compares only with `bool` (¶3)

<div class="compare" markdown="1">

```cpp ok
#include <compare>
auto a = true <=> false;
// strong_ordering::greater
```

```cpp error
#include <compare>
auto b = true <=> 1;
// error: bool against non-bool
```

</div>

¶3 If one operand is `bool` and the other is not, the program is ill-formed. By contrast, `true < 2` is valid: `bool` is promoted to `int`. Such comparisons are almost always bugs, for example treating `a < b < c` as a chained comparison.

### No narrowing (¶4.1)

```cpp title="spaceship-narrowing.cpp" error
#include <compare>

int i = -1;
unsigned u = 1;
bool old = i < u;              // valid, but false: -1 is converted to UINT_MAX
auto r1 = i <=> u;             // error: int → unsigned is a narrowing conversion
auto r2 = -1 <=> 1u;           // error: the constant -1 doesn't fit in unsigned
```

¶4.1 If the usual arithmetic conversions would require a **narrowing conversion**, the program is ill-formed, except for conversions from integral to floating-point types. Narrowing is defined in list-initialization ([[dcl.init.list]]): roughly, the target type cannot represent all values of the source type, as with `int` to `unsigned` or `long long` to `int`.

Comparing signed with unsigned is the best-known trap inherited from C: the usual arithmetic conversions turn `-1` into `UINT_MAX`, so `-1 < 1u` is false. `<=>` rejects such comparisons. Clang's diagnostic is "argument to 'operator<=>' cannot be narrowed from type 'int' to 'unsigned int'".

The definition of narrowing has an exception: if the source is a constant expression whose value fits in the target type, it is not narrowing. Integral promotion may also bring both sides to the same type so that no conversion is needed at all. So all of the following are valid:

```cpp run title="spaceship-narrowing-ok.cpp" ok
#include <compare>

unsigned u = 1;
auto a = 1 <=> u;        // the constant 1 fits in unsigned: not narrowing
auto b = 'a' <=> 1u;     // 'a' is promoted to int, and the constant 97 fits in unsigned
unsigned char uc = 200;
auto c = uc <=> -1;      // uc is promoted to int, both sides are int
long long ll = 0;
auto d = u <=> ll;       // long long can represent every unsigned value, u becomes long long

int main() { return (c > 0 && d > 0) ? 0 : 1; }
```

Whether a conversion narrows depends on the result of the usual arithmetic conversions, which in turn depends on the widths of the types, so the same line can be valid on one platform and ill-formed on another. Take `unsigned long <=> long long`: on platforms where `long` is 64 bits, `long long` is converted to `unsigned long long`, which is narrowing; on platforms where `long` is 32 bits, `unsigned long` is converted to `long long`, which is valid.

Integral to floating-point also counts as narrowing in list-initialization, and `long long` to `double` may lose precision, but `<=>` deliberately lets it through. Mixed integer/floating comparisons are very common, and the converted result is roughly right, unlike `-1` turning into `UINT_MAX`, which changes the value entirely.

## Enumerations (¶4, ¶5)

¶5 If both operands have the same enumeration type, the result is that of converting both to the underlying type and applying `<=>`. Scoped enumerations cannot take part in arithmetic, but values of the same type can be compared this way. ¶4 also allows an unscoped enumeration to be compared with an integral type, handled by the usual arithmetic conversions.

```cpp run title="spaceship-enum.cpp" ok
#include <compare>

enum class Level { low, mid, high };
enum Plain { p0, p1 };

static_assert((Level::low <=> Level::high) < 0);   // same scoped enumeration (¶5)
static_assert((p1 <=> 0) > 0);                     // unscoped enumeration against integer (¶4)

int main() {}
```

Every other combination falls under paragraph 7, and the program is ill-formed:

```cpp title="spaceship-enum-bad.cpp" error
#include <compare>

enum A { a0 };
enum B { b0 };
enum class S { s0 };

auto r1 = a0 <=> b0;       // error: two different enumeration types
auto r2 = a0 <=> 1.0;      // error: ¶4 allows enumeration against integer, not against floating-point
auto r3 = S::s0 <=> 0;     // error: scoped enumeration against integer
```

With `<` instead, `r1` and `r2` were only deprecated in C++20/23 ([[P1120R0]]) and became ill-formed only in C++26 ([[diff.cpp23.expr]]); `<=>` disallowed them from the start.

## Pointers (¶6)

```cpp run title="spaceship-ptr.cpp" ok
#include <compare>

struct S { int a, b; };

constexpr bool f() {
    S s{};
    int arr[4]{};
    void* p = arr;          // void* is an object pointer type too
    void* q = arr + 1;
    int* pa = arr;
    return (&s.a <=> &s.b) < 0      // the later-declared member has the higher address ([expr.rel])
        && (p <=> q) < 0
        && (pa <=> arr) == 0;       // one side is a pointer, and the array on the other side decays
}
static_assert(f());

int main() {}
```

¶6 If at least one operand is an object pointer and the other is an object pointer or an array, array-to-pointer conversions, pointer conversions and qualification conversions are applied to both sides to bring them to their **composite pointer type** ([[expr.type]]), i.e. the common pointer type both can convert to. After conversion the two sides must have the same type. The result is `std::strong_ordering`:

- ¶6.1 If the two pointers are equal (per [[expr.eq]]), the result is `equal`.
- ¶6.2 If they are not equal, the result is `less` or `greater` according to the partial order of [[expr.rel]].
- ¶6.3 If [[expr.rel]] doesn't specify which is greater, for example for the addresses of two unrelated objects, the result is unspecified.

Note 1 points out that when both operands are arrays, no array-to-pointer conversion is applied, so two arrays cannot be compared and fall under paragraph 7. All of the following are ill-formed:

```cpp title="spaceship-ptr-bad.cpp" error
#include <compare>

void f(); void g();
struct S { int a, b; };
int x, y;
int arr1[2], arr2[2];

auto r1 = &f <=> &g;               // error: function pointers are not object pointers
auto r2 = nullptr <=> nullptr;     // error: nullptr_t is not a pointer type
auto r3 = &S::a <=> &S::b;         // error: pointers to members
auto r4 = arr1 <=> arr2;           // error: two arrays don't decay (Note 1)
constexpr bool r5 = (&x <=> &y) < 0;  // error: result unspecified, not a constant expression
```

The comparison in the last line is valid at run time: its result is unspecified, but it is not UB. It is only in constant evaluation that a comparison with an unspecified result stops the expression from being a constant expression ([[expr.const.core]]). When you need a consistent total order for arbitrary pointers, use `std::compare_three_way` ([[comparisons.three.way]]).

Function pointers are excluded because `<` already gives only an unspecified result for unequal function pointers ([[expr.rel#5]] Note 1), so ordering them has no meaning. Likewise, `p <=> nullptr` and `p <=> 0` are ill-formed, because a null pointer constant is neither an object pointer nor an array.

## `<compare>` must be included first (¶8)

```cpp title="spaceship-no-include.cpp" error
// no #include <compare>
auto r = 1 <=> 2;   // error: std::strong_ordering is not declared
```

¶8 `std::strong_ordering`, `std::weak_ordering` and `std::partial_ordering` are not predefined types; they are declared by `<compare>` ([[compare.syn]]) or by the standard library modules. If no standard library declaration of these types is reachable before they are used, the program is ill-formed. Implicit uses count too: using built-in `<=>`, or a defaulted `operator<=>` with return type `auto`, uses them implicitly.

Clang's diagnostic is "cannot use builtin operator '<=>' because type 'std::strong_ordering' was not found; include <compare>". Many standard headers include `<compare>` indirectly, so this error usually shows up only in stripped-down translation units.

With this design, the entire interface of the comparison categories (comparison with `0`, `is_eq` and so on) can be defined and evolved in the library, and the language is only responsible for choosing which category and which value. `std::initializer_list` and `std::type_info` are other examples of the language depending on library types.

## Implementation view

!!! impl
    - libstdc++ and libc++ both implement the comparison category types as classes with a single `signed char` member, with `sizeof` 1. After optimization, `(a <=> b) < 0` usually generates the same code as writing `a < b` directly.
    - Interfaces such as `r < 0` are implemented with a parameter type that can only be constructed from the literal `0`, so `r < 1` doesn't compile. That is a library convention, not a core language rule.

## History and evolution

!!! history
    - C++20: [[P0515R3]] introduced `<=>` and the comparison categories. Built-in `<=>` rejected narrowing signed/unsigned comparisons, mixed `bool` comparisons and array comparisons from the start. At the same time, [[P1120R0]] deprecated array comparisons with the old operators such as `==` and `<`, as well as arithmetic conversions between enumerations and floating-point and between different enumerations.
    - C++26: those deprecated uses became ill-formed for the old operators too ([[diff.cpp23.expr]]). `<` and `<=>` still differ: `-1 < 1u`, `true < 2`, and `<` on unequal function pointers are still valid, while the corresponding `<=>` are all ill-formed.
    - `<=>` is a new token, which changed lexing. C++17 code in which `<=` is immediately followed by `>`, such as the template argument `Y<operator<=> y;` (meaning `Y<operator<= > y;`), is tokenized as `<=>` in C++20 and becomes ill-formed ([[diff.cpp17.lex]]).

## Common misconceptions

!!! pitfall "`<=>` accepts the same operands as `<`"
    `<=>` rejects `int` against `unsigned` when that needs narrowing, `bool` against non-`bool`, and function pointers; `<` accepts all of them.

!!! pitfall "Floating-point `<=>` gives a total order"
    A NaN makes the result `unordered`. When you need a total order on floating-point values, use `std::strong_order` ([[cmp.alg]]), which orders by IEEE 754 totalOrder.

!!! pitfall "`<=>` on unrelated pointers is UB"
    It is not UB; the result is merely unspecified. In constant evaluation it is not a constant.

## Questions

!!! question "Question 1"
    Assume a 32-bit `int` and a 64-bit `long`. Which of these are well-formed?

    ```cpp
    #include <compare>
    short s = -1; unsigned short us = 1; unsigned int ui = 1; long l = -1;
    auto a = s <=> us;
    auto b = s <=> ui;
    auto c = l <=> ui;
    auto d = 1.0f <=> 1LL;
    ```

<details markdown="1">
<summary>Answer</summary>

- `a`: `short` and `unsigned short` are both promoted to `int`, and no further conversion is needed. Well-formed, `strong_ordering::less`.
- `b`: `s` is promoted to `int`; `int` against `unsigned int` converts `s` to `unsigned int`, and `s` is not a constant, so this is narrowing. Ill-formed.
- `c`: a 64-bit `long` can represent every `unsigned int` value, so `ui` is converted to `long` without narrowing. Well-formed, result `less`.
- `d`: `1LL` is converted to `float`; integral-to-floating narrowing is exempted by item 4.1. Well-formed, `partial_ordering`.
</details>

!!! question "Question 2"
    Why does paragraph 6 say "at least one is an object pointer and the other is an object pointer or an array" instead of "both are pointers"?

<details markdown="1">
<summary>Answer</summary>

To allow comparing a pointer with an array: `int* p; int a[3]; p <=> a`. The array undergoes the array-to-pointer conversion before the composite pointer type is determined. The case of two arrays is excluded by Note 1 and falls under paragraph 7.

The wording also excludes null pointer constants: `nullptr` has type `std::nullptr_t` and `0` is an `int`, neither of which is an object pointer or an array, so `p <=> nullptr` and `p <=> 0` are both ill-formed. This is consistent with `<`, since [[expr.rel]] likewise requires both sides to be pointers after conversion; only `==` accepts null pointer constants ([[expr.eq]]).
</details>

## Summary

| Operands | Result type | Restriction | Paragraph |
|---|---|---|---|
| `bool` against non-`bool` | | {{ill-formed}} | ¶3 |
| Integral, or integral against unscoped enumeration | `strong_ordering` | Ill-formed if narrowing is needed (except integral to floating) | ¶4 |
| Involving floating-point | `partial_ordering` | Same as above; NaN gives `unordered` | ¶4 |
| Same enumeration type | By underlying type | | ¶5 |
| Object pointers, or pointer against array | `strong_ordering` | Unrelated pointers give an unspecified result | ¶6 |
| Two arrays, function pointers, pointers to members, `nullptr`, different enumerations, enumeration against floating-point | | {{ill-formed}} | ¶6 Note 1, ¶7 |
| Comparison category types not declared | | {{ill-formed}} | ¶8 |
