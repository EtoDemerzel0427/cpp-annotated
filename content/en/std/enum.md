---
title: Enumerations
summary: "The difference between scoped and unscoped enumerations, when the underlying type is fixed and who chooses it, which values an enumeration can hold and when a conversion is UB, opaque declarations, and C++17 brace initialization and C++20 using enum."
updated: 2026-10-19
---

!!! tldr
    - The enumerators of an `enum class` live only in the enumeration's own scope and don't convert implicitly to integers; the enumerators of a plain `enum` leak into the enclosing scope and promote to integers.
    - An enumeration with `: T`, or any `enum class`, has a fixed underlying type and can be opaquely declared first with enumerators given later; for a plain `enum` without `: T`, the implementation chooses the underlying type based on the enumerator values.
    - With a fixed underlying type, an enumeration can hold every value of the underlying type; without one, only the values of the smallest bit-field that can hold all enumerators, and a `static_cast` outside that range is UB.
    - Since C++17, an enumeration with a fixed underlying type can be written `E{42}`; C++20's `using enum E;` is like writing a using-declaration for each enumerator.
    - Since C++26, arithmetic and comparisons between two different enumeration types, or between an enumeration and a floating-point type, are ill-formed.

## Two kinds of enumeration (¶2)

<div class="compare" markdown="1">

```cpp ok
enum color { red, green };
int i = green;       // OK: promotes to 1
color c = red;       // red is in the enclosing scope
int red_count = 0;   // can't be called red any more
```

```cpp error
enum class Col { red, green };
int i = Col::green;  // error: no conversion
Col c = Col::red;    // must write Col::
int red = 0;         // OK: no conflict
```

</div>

An **enumeration** is a distinct type with a set of named constants ([[basic.compound]]); the constants are called **enumerators**. The `enum` inherited from C has three problems: enumerators leak into the enclosing scope, enumerations convert implicitly to integers, and the underlying integer type is chosen by the implementation, so it can't be forward-declared.

¶2 Since C++11, `enum class` and `enum struct` (exactly equivalent) declare a [[g:scoped-enumeration|scoped enumeration]], and plain `enum` declares an [[g:unscoped-enumeration|unscoped enumeration]]. The differences:

| | Unscoped enumeration `enum` | Scoped enumeration `enum class` |
|---|---|---|
| Scope of enumerators | The enumeration's scope and the enclosing scope (¶12) | Only the enumeration's scope |
| Implicit conversion to integer | Yes, via integral promotion (¶11) | No, and no contextual conversion to `bool` either |
| Name can be omitted | Yes (anonymous enumeration) | No |
| Underlying type without `: T` | Not fixed, chosen by the implementation (¶7) | Fixed as `int` (¶5) |
| Opaque declaration | Must have `: T` | Can omit it |

¶2 also specifies the enumerator values. One with `=` takes the value of that constant expression; one without takes 0 if it is first, and otherwise the previous value plus 1. Names can't repeat within an enumeration, but values can:

```cpp title="enum-values.cpp" ok
enum { a, b, c = 0 };          // a=0, b=1, c=0
enum { d, e, f = e + 2 };      // d=0, e=1, f=3
enum B : bool { no, yes };     // OK: bool is an integral type
static_assert(a == c && f == 3 && yes == true);

int main() {}
```

The `: T` part is called the *enum-base*; `T` must be an integral type, and cv-qualification is ignored (`: const int` is `: int`). `bool` is an integral type too ([[basic.fundamental]]), so `enum B : bool` is valid; floating-point types and other non-integral types aren't.

## The underlying type (¶5, ¶7)

¶5 Each enumeration is a type distinct from all other types and has an [[g:underlying-type|underlying type]], the integral type it actually uses in memory. If there is an enum-base, or it is a scoped enumeration without an enum-base (in which case it is `int`), the underlying type is [[g:fixed-underlying-type|fixed]].

¶7 If the underlying type is not fixed, it is some integral type that can represent all the enumerator values; which one is implementation-defined {{impl}}. There is only one restriction: the underlying type can't be larger than `int` unless some enumerator value doesn't fit in `int` or `unsigned int`. If no integral type can represent all the values, the enumeration is ill-formed. If the enumerator list is empty, it is treated as having a single enumerator with value 0.

```cpp run title="underlying-unfixed.cpp" impl
#include <cstdio>
#include <type_traits>

enum E6 { i1 = 0x7fffffff, i2 };          // i2 = 2^31: doesn't fit int, fits unsigned int
enum E7 { m = -1, n = 0x80000000u };      // must represent both -1 and 2^31: neither int nor unsigned works

int main() {
    std::printf("E6: size=%zu signed=%d\n", sizeof(E6), std::is_signed_v<std::underlying_type_t<E6>>);
    std::printf("E7: size=%zu\n", sizeof(E7));
}
// Clang 23 (arm64): E6: size=4 signed=0; E7: size=8
```

### The type of enumerators before the closing brace

¶5 After the closing brace, each enumerator has the enumeration type. Inside the braces, a later enumerator's initializer may use earlier enumerators, and their types are specified differently:

- With a fixed underlying type, an enumerator has the underlying type, and its initializer must be a converted constant expression of the underlying type ([[expr.const.const]]), so narrowing isn't allowed;
- Without a fixed underlying type (¶5.1–¶5.3): one with an initializer has the type of the initializer expression (if that expression has an unscoped enumeration type, the underlying type of that enumeration); the first enumerator without an initializer has an unspecified signed integral type; the rest have the same type as the previous one, unless adding 1 doesn't fit, in which case an unspecified integral type that fits is used, and if there is none, the enumeration is ill-formed.

```cpp title="enumerator-types.cpp" error
#include <type_traits>

enum E1 : unsigned char { a = 255, b };   // error: b = 256 can't be represented as unsigned char
enum E2 : unsigned { c = -1 };            // error: a converted constant expression doesn't allow narrowing -1 → unsigned
enum E3 { d = 1u, e = sizeof(d) };        // OK: inside the braces d has type unsigned int
static_assert(std::is_same_v<decltype(d), E3>);   // after the closing brace d has type E3
```

## Opaque declarations (¶3, ¶4, ¶6)

With a fixed underlying type, the size of an enumeration is known without seeing its enumerators. So it can be declared first and its enumerators given later:

```cpp title="opaque-enum.cpp" error
enum class Color : unsigned char;            // opaque declaration, already a complete type
static_assert(sizeof(Color) == 1);           // OK: no enumerators seen yet
enum class Color : unsigned char { red, green };   // OK: enumerators added

enum class W;                                // OK: underlying type defaults to int
enum U : int;                                // OK
enum V;                                      // error: an unscoped enumeration must have an enum-base
enum W2 : long;
enum class W2 : long;                        // error: previously declared as unscoped
enum class Color : int;                      // error: different underlying type
```

A declaration without an enumerator list, ending in a semicolon, is an [[g:opaque-enum-declaration|opaque-enum-declaration]]. ¶3 says it either redeclares an enumeration in the current scope or declares a new one. Note 2 points out that an enumeration declared this way has a fixed underlying type and is already a complete type: you can apply `sizeof`, define objects, and pass by value; you just don't know the enumerators yet.

The second half of ¶3 requires redeclarations to agree. A scoped enumeration can't be redeclared as unscoped or with a different underlying type; an unscoped enumeration can't be redeclared as scoped, and every redeclaration must have an enum-base specifying the same underlying type.

`enum V;` is forbidden because a non-fixed underlying type can only be determined after seeing all the enumerators, while the whole point of an opaque declaration is to make the type complete before the enumerators are seen. If it were allowed, different translation units could make different assumptions about the size of `V`.

¶6 correspondingly specifies when an enumeration is complete. With a fixed underlying type, it is complete immediately after the enum-base (or after the name if there is no enum-base), so `sizeof(E)` can already be used in enumerator initializers; without one, it is complete only at the closing brace `}`.

¶4 The name of an enumeration can be qualified, to complete a previously declared enumeration outside its class or namespace. Such a declaration can't appear at class scope and must correspond to an existing declaration in that class or namespace:

```cpp title="enum-out-of-class.cpp" ok
struct X {
    enum class State;               // only opaquely declared in the class
};
enum class X::State { idle, busy }; // completed outside the class (e.g. in an implementation file)

namespace N { enum class E : int; }
enum class N::E : int { x };        // OK

int main() { return static_cast<int>(X::State::busy) - 1; }
```

A class in a header can expose just `enum class State;`, and the actual list of states can live in the implementation file. ¶1 also says that an opaque declaration with a qualified name (such as `enum class X::State;`) can only be an explicit specialization, used for member enumerations of class templates.

## Which values an enumeration can hold (¶8)

```cpp title="enum-range-ub.cpp" error
#include <cstdint>

enum A { a = 1, b = 4 };                  // value set 0..7
constexpr A x1 = static_cast<A>(7);       // OK: within the value set, even with no matching enumerator
constexpr A x2 = static_cast<A>(8);       // error: out of range is UB, which must be diagnosed in constant evaluation

enum class S : std::uint8_t { };          // fixed underlying type: the value set is all of uint8_t
constexpr S s = static_cast<S>(255);      // OK
```

¶8 specifies the [[g:enumeration-values|values of the enumeration]]:

- With a fixed underlying type, they are all the values of the underlying type. `enum class E : int {}` can represent any `int`.
- Without one, they are the values representable by the smallest bit-field that can hold all the enumerators. Let that smallest width be M: with no negative enumerators, the range is 0 to 2<sup>M</sup>−1; with negative enumerators, in two's complement, −2<sup>M−1</sup> to 2<sup>M−1</sup>−1.
- An enumeration can hold values that correspond to no enumerator; combinations of bit flags are like this. An empty enumeration is treated as having a single enumerator with value 0.

| Enumeration | Enumerators | M | Range of values |
|---|---|---|---|
| `enum A { a = 1, b = 4 };` | 1, 4 | 3 | 0 … 7 |
| `enum B { c = -1, d = 2 };` | −1, 2 | 3 | −4 … 3 |
| `enum C { };` | Treated as 0 | 1 | 0 … 1 |
| `enum D : int { };` | Fixed | — | All of `int` |

Footnote 75 explains that this value set is only used to define the semantics of promotions and conversions; it doesn't guarantee that expressions of enumeration type always fall within the range. What really has consequences is [[expr.static.cast#8]]:

!!! std
    If the enumeration type does not have a fixed underlying type, the value is unchanged if the original value is within the range of the enumeration values, and otherwise, the behavior is undefined.

So `static_cast<A>(8)` at run time is {{ub}}. This lets implementations represent enumerations in narrower storage and lets the optimizer use the value range: for a value that can only be 0…7, a `switch` can omit the range check. GCC and Clang optimize this way under `-fstrict-enums` (off by default); UBSan's `-fsanitize=enum` detects loading an enumeration value outside its range.

!!! tip "To store arbitrary integers, fix the underlying type"
    The value set of `enum Flags : unsigned { A = 1, B = 2, C = 4 };` is all of `unsigned`, so converting `A | B | C | 1024` back to `Flags` is never UB. `std::byte` is defined as `enum class byte : unsigned char {}`, fixing the underlying type for the same reason.

## Size and representation (¶9–¶10)

¶9 An enumeration has the same size, value representation and alignment requirements as its underlying type, and the representation of each value is the same as that of the corresponding value of the underlying type. So `memcpy`ing an object of `enum E : int` into an `int` gives exactly that integer value.

¶10 Two enumerations with the same underlying type and the same value set are [[g:layout-compatible-enumerations|layout-compatible enumerations]]. The definition of layout-compatible types in [[basic.types.general]] uses this concept, which in turn affects the common initial sequence rules.

## Conversion to integers (¶11)

¶11 An enumerator or object of unscoped enumeration type is converted to an integer by integral promotion ([[conv.prom]]):

- Without a fixed underlying type: it promotes to the first of `int`, `unsigned`, `long`, `unsigned long`, `long long`, `unsigned long long` that can represent all its values ([[conv.prom#3]]);
- With a fixed underlying type: it can be converted to the underlying type, and if the underlying type itself can be promoted, also to the promoted type ([[conv.prom#4]]).

Scoped enumerations have no implicit conversions at all: they don't become `int` and can't be contextually converted to `bool`; only `static_cast` works ([[expr.static.cast]]):

```cpp title="enum-conversions.cpp" error
enum color { red, yellow, green = 20, blue };
enum class Col { red, yellow, green };

void f() {
    color c1 = 1;            // error: int doesn't convert implicitly to an enumeration
    int i = yellow;          // OK: integral promotion, i == 1
    int x = Col::red;        // error: a scoped enumeration doesn't convert to int
    Col y = Col::red;
    if (y) { }               // error: can't be contextually converted to bool
    int j = static_cast<int>(Col::green);   // OK: explicit conversion
    bool same = (y == Col::red);            // OK: comparison of the same type
    (void)i; (void)j; (void)same;
}
```

### Mixed arithmetic: deprecated in C++20, ill-formed in C++26

Although unscoped enumerations promote to integers, arithmetic and comparisons between two different enumerations, or between an enumeration and a floating-point type, are usually mistakes. Items 1.2 and 1.3 of [[expr.arith.conv#1]] say that if one operand is a scoped enumeration, the other must be of the same type; if one is an enumeration and the other is a different enumeration type or a floating-point type, it is ill-formed {{c++26}}:

```cpp title="enum-arith.cpp" error
enum A { a }; enum B { b };
int x = a + b;          // error (C++26); deprecated in C++20/23
double y = a + 1.0;     // error (C++26); deprecated in C++20/23
bool z = (a == b);      // error (C++26): comparison also performs the usual arithmetic conversions
int w = a + 1;          // OK: enumeration and integer
int v = a | a;          // OK: the same enumeration
```

C++20's [[P1120R0]] deprecated these forms, and C++26's [[P2864R2]] made them ill-formed. Clang 23 reports errors with `-std=c++2c` and deprecation warnings with `-std=c++23`.

## Constructing from integers with braces ([[dcl.init.list#3.8]]) {{c++17}}

`enum class Handle : int {};` is a zero-overhead strongly typed integer: different handle types can't be mixed. But in C++14 the only way to construct one was `static_cast<Handle>(7)`.

C++17's [[P0138R2]] added a rule: for an enumeration with fixed underlying type `U`, direct-list-initialization from a list with a single scalar implicitly convertible to `U` initializes the object to that value; if narrowing is required, it is ill-formed.

```cpp title="enum-brace-init.cpp" error
enum byte : unsigned char { };
byte b { 42 };           // OK (C++17)
byte c = { 42 };         // error: doesn't apply to copy-list-initialization
byte d = byte{ 42 };     // OK: same as b
byte e { 256 };          // error: narrowing

enum class Handle : int { };
Handle h { 7 };          // OK
Handle h2 ( 7 );         // error: not list-initialization
```

The brace form forbids narrowing and only applies to fixed underlying types (so that `U` is known), so it is safe. `std::byte b{42};` relies on exactly this rule.

## Enumerator names and linkage (¶12)

¶12 The names of unscoped enumerators are also bound in the scope that directly contains the enumeration. So you can write either `left` or `direction::left` (qualifying unscoped enumerators with the enumeration name is allowed since C++11). Scoped enumerators can only be used with qualified names:

```cpp title="enum-scope.cpp" error
enum direction { left = 'l', right = 'r' };
enum class altitude { high = 'h', low = 'l' };

void g() {
    direction d;
    d = left;                 // OK
    d = direction::right;     // OK
    altitude a;
    a = high;                 // error: high is not in scope
    a = altitude::low;        // OK
    (void)d; (void)a;
}
```

The second half of ¶12 handles linkage. When an unnamed enumeration like `enum { A, B };` in a header is included by several translation units, are they the same type? The ODR ([[basic.def.odr]]) requires the definitions to be the same everywhere, but what matches up an unnamed type across translation units? The rule: an unnamed enumeration that has no typedef name for linkage purposes ([[dcl.typedef]]) but has enumerators is identified for linkage by its underlying type plus its first enumerator, which is said to be its name for linkage purposes (C++20, [[P2115R0]]). Note 3 points out that each unnamed enumeration with no enumerators is a distinct type.

## using enum ([enum.udecl]) {{c++20}}

```cpp title="using-enum.cpp" ok
enum class Color { red, green, blue };

const char* name(Color c) {
    switch (c) {
        using enum Color;           // only in effect inside the switch body
        case red:   return "red";
        case green: return "green";
        case blue:  return "blue";
    }
    return "?";
}

int main() { return name(Color::green)[0] == 'g' ? 0 : 1; }
```

¶2 `using enum E;` is equivalent to a using-declaration for each enumerator of `E` ([[namespace.udecl]]). Its conflict rules, member lookup at class scope, and access control all follow those of using-declarations. It doesn't change the type of the enumerators and doesn't make a scoped enumeration implicitly convertible to integers.

¶1 The name after `using enum` undergoes type-only lookup ([[basic.lookup.general]]), ignoring non-type declarations with the same name. It can be an alias, a specialization of an alias template, and since C++26 a reflection *splice-type-specifier* ([[dcl.type.splice]]). It must designate a non-dependent enumeration type whose definition is reachable:

```cpp title="using-enum-lookup.cpp" ok
enum E { x };
void f() {
    int E = 0;
    using enum E;                   // OK: type-only lookup ignores int E
    (void)E;
}

using F = E;
using enum F;                       // OK: through an alias
template<class T> using EE = T;
void g() { using enum EE<E>; }      // OK

int main() {}
```

Dependent types and enumerations with only an opaque declaration are forbidden because the compiler must know which names to introduce as soon as it sees the `using enum`. Name lookup in a template definition happens at definition time ([[temp.res]]), and the set of introduced names can't wait until instantiation.

¶4 (note) Two `using enum` declarations that introduce enumerators with the same name conflict, because this amounts to two using-declarations naming non-functions introducing the same name ([[namespace.udecl#10]]):

```cpp title="using-enum-errors.cpp" error
enum class fruit { orange, apple };
enum class color { red, orange };

void f() {
    using enum fruit;          // OK
    using enum color;          // error: color::orange conflicts with fruit::orange
}

template<class T> void h() {
    using enum T;              // error: can't be a dependent type
}

enum class Fwd;
void m() {
    using enum Fwd;            // error: only an opaque declaration, enumerators unknown
}
```

¶3 (note) With `using enum` at class scope, the enumerators can be accessed through member lookup:

```cpp title="using-enum-class.cpp" ok
enum class fruit { orange, apple };
struct S {
    using enum fruit;          // brings orange and apple into S
};
void f() {
    S s;
    (void)s.orange;            // OK: fruit::orange
    (void)S::orange;           // OK
}

int main() {}
```

This makes it easy to move an enumeration nested in a class out of the class. If the enumeration was defined inside `S` and code wrote `S::orange`, then after moving the enumeration to namespace scope, adding one line `using enum fruit;` in `S` leaves that code unchanged.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

¶1 Attributes written after the `enum` keyword or in an opaque declaration appertain to the enumeration itself, and every later use of the enumeration is considered to carry them. For example, after `enum [[deprecated]] E { };`, every use of `E` should trigger a deprecation warning. Attributes written after an enumerator appertain only to that enumerator (¶2).

¶1 In a class member declaration, a `:` following `enum E` is always parsed as an enum-base. This removes the ambiguity between an enumeration declaration with an enum-base and an unnamed bit-field of enumeration type:

```cpp title="enum-base-ambiguity.cpp" error
struct S {
    enum E : int {};
    enum E : int {};      // error: redefinition of the enumeration (": int" is parsed as an enum-base, not a bit-field)
};
```

¶1 The name of an enumeration is not looked up where it is declared; it is introduced by that declaration.

</details>

## Implementation notes

!!! impl "Choice of underlying type and the ABI"
    - For enumerations without a fixed underlying type, GCC and Clang on Itanium ABI platforms choose `unsigned int` (when all values are non-negative and fit) or `int`, switching to a 64-bit type if they don't fit. `-fshort-enums` makes them choose the smallest type that can hold all values, which changes the ABI and must be consistent across the whole program.
    - MSVC usually just uses `int` for unscoped enumerations without a fixed underlying type, which differs from GCC and Clang. In headers shared across compilers, enumerations whose size matters should fix their underlying type.
    - In Itanium mangled names, an enumeration is encoded by name only, like a class; the underlying type doesn't appear. So changing the underlying type doesn't cause link errors, but silently changes object sizes and breaks the ABI.

## History

!!! history
    - C++98 had only unscoped enumerations, with the underlying type chosen by the implementation and no forward declarations. The value set was already defined by the smallest-bit-field rule.
    - C++11 added scoped enumerations, fixed underlying types and opaque declarations, allowed qualifying unscoped enumerators as `E::enumerator`, and added `std::underlying_type` to the library.
    - C++17 allowed enumerations with a fixed underlying type to be direct-list-initialized from integers ([[P0138R2]]) and added `std::byte`.
    - C++20 added `using enum` ([[P1099R5]]), deprecated arithmetic and comparisons between different enumerations and between enumerations and floating-point types ([[P1120R0]]), and specified that an unnamed enumeration uses its first enumerator as its name for linkage purposes ([[P2115R0]]).
    - C++23 added `std::to_underlying` and `std::is_scoped_enum` to the library.
    - C++26 made the mixed arithmetic above ill-formed ([[P2864R2]]), and `using enum` can take a reflection splice.

## Common misconceptions

!!! pitfall "An enumeration can only hold the values of its enumerators"
    `enum A { a = 1, b = 4 };` can legitimately hold 0, 2, 3, 5, 6 and 7. `-Wswitch` only checks that all enumerators are covered; it doesn't mean other values can't occur, and a `switch` still needs to consider `default`.

!!! pitfall "An unscoped enumeration can hold any int"
    For the `A` above, `static_cast<A>(100)` is UB. Enumerations used as bit flags should fix their underlying type.

!!! pitfall "`E e = {1};` is the same as `E e{1};`"
    The C++17 rule only applies to direct-list-initialization; `E e = {1};` is still ill-formed.

## Questions

!!! question "Question 1"
    What is the value set of `enum E { a = -3, b = 3 };`? Which of `static_cast<E>(4)` and `static_cast<E>(-4)` is UB?

<details markdown="1">
<summary>Answer</summary>

There are negative values, so the computation uses signed two's complement. A signed bit-field of width 3 has range −4…3, which holds −3 and 3, so M = 3 and the value set is −4…3. `static_cast<E>(-4)` is within the value set and valid; `static_cast<E>(4)` is out of range and UB, and is diagnosed in constant evaluation (¶8, [[expr.static.cast#8]]).
</details>

!!! question "Question 2"
    Is the code below well-formed? What is the type of `S::apple`?

    ```cpp
    enum class fruit { orange, apple };
    struct S { using enum fruit; };
    auto v = S::apple;
    ```

<details markdown="1">
<summary>Answer</summary>

It is well-formed. `using enum fruit;` is equivalent to `using fruit::orange; using fruit::apple;` ([enum.udecl]/2), and using-declarations naming enumerators are allowed at class scope ([[namespace.udecl#3]]). Member lookup of `S::apple` finds this using-declaration and thus `fruit::apple`, whose type is `fruit`; it doesn't become an integer.
</details>
