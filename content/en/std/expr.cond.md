---
title: Conditional operator
summary: "How the result type and value category of c ? x : y are derived from the two branches: throw branches, lvalues of the same type, one-way conversions between class types, and the common type of arithmetic and pointer operands."
updated: 2026-10-19
---

!!! tldr
    - `?:` evaluates only the selected branch, but the whole expression has a single type and a single value category, which must be derived from both branches at compile time.
    - When both branches are glvalues of the same type and value category, the result is still that glvalue, so `(c ? a : b) = 1` is valid; with an lvalue on one side and an xvalue on the other, the result degrades to a prvalue.
    - When one side is a `throw` expression, the result takes the type and value category of the other side.
    - When class types are involved, the compiler tries to convert each side to the other: it is well-formed only if exactly one direction works, and ambiguous if both do.
    - In all other cases the result is a prvalue: arithmetic types undergo the usual arithmetic conversions (`c ? -1 : 0u` is `unsigned`), and pointers take the composite pointer type.

## One expression, two branches

```cpp
int a = 1, b = 2;
(flag ? a : b) = 10;    // OK: assigns to whichever variable was selected
auto x = flag ? 1 : "x"; // error: int and const char* cannot be merged into one type
```

`if` is a statement, so its two branches can each do their own thing. `?:` is an expression, and the compiler must determine its type and value category without knowing the value of `flag`, so the standard defines, in paragraphs 2–7, an algorithm for merging the two branches.

First a few terms. **Value categories** ([[g:value-category]]) divide expressions into three kinds: an **lvalue** refers to an object with identity (a variable name, `*p`); an **xvalue** also refers to an object, but one whose resources can be taken (`std::move(x)`); a **prvalue** is a pure value (`1`, `a + b`, `T{}`). Lvalues and xvalues together are **glvalues** ([[basic.lval]]).

Below, "second operand" and "third operand" mean the two branches after `?` and `:`. The algorithm checks the following in order, stopping at the first match:

| Step | Case | Result | Paragraph |
|---|---|---|---|
| 1 | A `void` branch | One side is a `throw` expression: take the other side; both `void`: `void` prvalue; otherwise ill-formed | 2 |
| 2 | Two bit-fields of the same value category differing only in cv | Treated as the same type | 3 |
| 3 | Different types involving a class type, or two glvalues of the same value category differing only in cv | Try implicit conversions in both directions; if exactly one works, apply it | 4 |
| 4 | Glvalues of the same type and value category | The result has that type and value category | 5 |
| 5 | Everything else | prvalue; with class types, overload resolution using built-in candidates | 6 |
| 6 | After array and function decay | Same type, usual arithmetic conversions, composite pointer type, or `std::nullptr_t` | 7 |

## Grammar and evaluation (¶1)

```text
conditional-expression:
    logical-or-expression
    logical-or-expression ? expression : assignment-expression
```

¶1 The first operand is contextually converted to `bool` ([[conv]]) and evaluated first; then only the selected one of the second and third operands is evaluated. The first operand is sequenced before the selected operand ([[intro.execution]]).

The grammar settles three points that are easy to misread:

- The conditional operator groups right-to-left: `a ? b : c ? d : e` is `a ? b : (c ? d : e)`, which can be written as an if-else chain.
- The middle operand is a full *expression* and may contain commas: in `c ? x = 1, y : z` the middle part is `(x = 1, y)`.
- The third operand is an *assignment-expression*, so `c ? a : b = 7` is `c ? a : (b = 7)`. In C the third operand is a *conditional-expression*, and the same code is an error in C, assigning to a non-lvalue.

```cpp run title="cond-grammar.cpp" ok
constexpr int sign(int n) { return n < 0 ? -1 : n == 0 ? 0 : 1; }   // right-to-left grouping
static_assert(sign(-5) == -1 && sign(0) == 0 && sign(9) == 1);

constexpr int f(bool c) {
    int a = 0, b = 0;
    c ? a : b = 7;            // i.e. c ? a : (b = 7): nothing is assigned when c is true
    return a * 10 + b;
}
static_assert(f(true) == 0 && f(false) == 7);

constexpr int g(bool c) {
    int x = 0, y = 2, z = 3;
    int r = c ? x = 1, y : z; // the middle operand is (x = 1, y)
    return r * 10 + x;
}
static_assert(g(true) == 21 && g(false) == 30);

int main() {}
```

Only one branch is evaluated, so the branch not selected doesn't affect constant evaluation. A C++11 constexpr function could contain only a single `return`, and argument checking relied on `?:` plus `throw`:

```cpp run title="cond-constexpr-throw.cpp" ok
#include <stdexcept>

constexpr int checked(int n) {
    return n >= 0 ? n : throw std::invalid_argument("negative");
}
static_assert(checked(3) == 3);        // OK: the throw branch is not evaluated
// static_assert(checked(-1) == 0);    // error: evaluates the throw, not a constant expression

int main() {}
```

## Glvalues of the same type stay glvalues (¶5)

¶5 If the two operands (after any conversions in the earlier steps) are glvalues of the same type and the same value category, the result has that type and value category. If either operand is a bit-field, the result is a bit-field.

This is one difference between C++ and C: a conditional expression in C++ can be an lvalue.

```cpp run title="cond-lvalue.cpp" ok
int main() {
    int a = 1, b = 2;
    bool pick_a = false;
    (pick_a ? a : b) = 10;             // OK: the result is an lvalue, assigns to b
    int& bigger = a > b ? a : b;       // OK: binds to an lvalue
    ++(a < b ? a : b);                 // OK
    return (b == 10 && &bigger == &b && a == 2) ? 0 : 1;
}
```

This paragraph is what lets the typical implementation of `std::max`, `return (a < b) ? b : a;`, return a `const T&`.

Note the condition "same value category". An lvalue and an xvalue of the same type do not satisfy paragraph 5; since the types are the same, paragraph 4 doesn't apply either, so it falls to paragraph 6, and the result is a prvalue:

```cpp title="cond-mixed-category.cpp" ok
#include <type_traits>
#include <utility>

int a = 0, b = 0;
static_assert(std::is_same_v<decltype((true ? a : std::move(b))), int>);       // prvalue
static_assert(std::is_same_v<decltype((true ? std::move(a) : std::move(b))), int&&>); // xvalue
```

For class types, `c ? obj : std::move(other)` therefore costs an extra copy or move.

## Common type of arithmetic, pointer and nullptr operands (¶7)

¶7 By this step the result is already a prvalue. The array-to-pointer and function-to-pointer conversions are applied to both operands first, and then one of the following must hold, or the program is ill-formed:

- ¶7.1 The types are the same: the result has that type and is copy-initialized from the selected operand.
- ¶7.2 Both have arithmetic or enumeration type: the **usual arithmetic conversions** ([[g:usual-arithmetic-conversions]], the same rules that find the common type for `a + b`, [[expr.arith.conv]]) are applied.
- ¶7.3 At least one is a pointer: both are converted to their **composite pointer type** ([[g:composite-pointer-type]], the pointer type both can be implicitly converted to, [[expr.type]]).
- ¶7.4 At least one is a pointer to member: likewise the composite pointer type.
- ¶7.5 Both are `std::nullptr_t`, or one is `std::nullptr_t` and the other a null pointer constant: the result is `std::nullptr_t`.

```cpp run title="cond-common-type.cpp" ok
#include <type_traits>
#include <cstddef>
#include <climits>

bool c = true;
int i = 0; long l = 0;
struct S { int x; };
enum E { e };

static_assert(std::is_same_v<decltype((c ? i : l)), long>);                // ¶7.2
static_assert(std::is_same_v<decltype((c ? 'a' : 1)), int>);               // ¶7.2: char is promoted
static_assert(std::is_same_v<decltype((c ? e : 1)), int>);                 // ¶7.2: enumerations take part too
static_assert(std::is_same_v<decltype((c ? "ab" : "cde")), const char*>);  // ¶7.3 after array decay
static_assert(std::is_same_v<decltype((c ? nullptr : &i)), int*>);        // ¶7.3
static_assert(std::is_same_v<decltype((c ? 0 : &i)), int*>);              // ¶7.3: null pointer constant
static_assert(std::is_same_v<decltype((c ? &S::x : nullptr)), int S::*>); // ¶7.4
static_assert(std::is_same_v<decltype((c ? nullptr : 0)), std::nullptr_t>); // ¶7.5

static_assert((true ? -1 : 0u) == UINT_MAX);   // the usual arithmetic conversions give unsigned

int main() {}
```

The last line is a common source of bugs: `c ? -1 : 0u` has type `unsigned int`, and `-1` becomes `UINT_MAX`.

```cpp title="cond-common-type-bad.cpp" error
enum E1 { e1 };
enum E2 { e2 };

void f(bool c, int* pi, long* pl) {
    auto a = c ? pi : pl;    // error: int* and long* have no composite pointer type
    auto b = c ? e1 : e2;    // error: two different enumeration types (ill-formed since C++26)
    auto d = c ? 1 : "x";    // error: int and const char* have no common type
}
```

The usual arithmetic conversions between different enumeration types were deprecated in C++20 ([[P1120R0]]) and made ill-formed in C++26 ([[P2864R2]], see [[diff.cpp23.expr]]).

## `void` branches and `throw` (¶2)

¶2 If the second or third operand has type `void`, one of the following must hold:

- ¶2.1 Exactly one operand is a (possibly parenthesized) *throw-expression* ([[expr.throw]]). The result has the type and value category of the other operand; if the other is a bit-field, the result is a bit-field.
- ¶2.2 Both have type `void`, and the result is a `void` prvalue. Note 1 points out that this includes the case where both are *throw-expression*s.

```cpp run title="cond-void.cpp" ok
#include <type_traits>

int x = 0;
bool c = true;

static_assert(std::is_same_v<decltype((c ? x : throw 0)), int&>);   // lvalue: taken from x
static_assert(std::is_same_v<decltype((c ? throw 0 : 1)), int>);    // prvalue: taken from 1
static_assert(std::is_same_v<decltype((c ? throw 0 : throw 1)), void>);
static_assert(std::is_same_v<decltype((c ? (void)x : (void)0)), void>);

int main() {
    (c ? x : throw 0) = 5;    // OK: the result is an lvalue
    return x == 5 ? 0 : 1;
}
```

A `throw` branch can borrow the other side's type because it never produces a value normally: once that branch is taken, control leaves the whole expression. Item 2.1 requires a syntactic *throw-expression*; an ordinary call to a `void` function won't do:

```cpp title="cond-void-bad.cpp" error
void log();
int f(bool c, int x) {
    return c ? x : log();          // error: one side is void (not a throw), the other is int
}
```

## Class types: trying both directions (¶4)

```cpp
struct B {}; struct D : B {};
D d; B b;
c ? d : b;       // what is the type?
```

The two branches have different types; `d` can be used as a `B`, but `b` cannot be used as a `D`. Paragraph 4's approach is to start from each side and try to form an implicit conversion sequence ([[over.best.ics]]) to a type related to the other side, and see which direction works.

¶4 applies in two cases: the two operands have different types and at least one is a class type; or both are glvalues of the same value category whose types differ only in cv-qualification (such as lvalues of `int` and `const int`).

### Target types (¶4.1–¶4.3)

Suppose operand `E1` (of type `T1`) is to be converted toward the other operand `E2` (of type `T2`):

- ¶4.1 If `E2` is an lvalue: the target is `T2&`, but this succeeds only if the reference can **bind directly** ([[g:bind-directly]], to the object itself rather than to a temporary, [[dcl.init.ref]]) to a glvalue.
- ¶4.2 If `E2` is an xvalue: the target is `T2&&`, again requiring direct binding.
- ¶4.3 If `E2` is a prvalue, or if neither of the above can be formed and at least one side is a class type:
    - ¶4.3.1 If `T1` and `T2` are the same class (ignoring cv): if `T2` is at least as cv-qualified as `T1`, the target is `T2`; otherwise no conversion is formed in this direction.
    - ¶4.3.2 If `T2` is a base class of `T1`: the target is `T2` with the cv-qualification of `T1`.
    - ¶4.3.3 Otherwise: the target is the type `E2` would have after the lvalue-to-rvalue, array-to-pointer and function-to-pointer conversions.

References are tried first to preserve glvalues where possible: if one side can become a reference to the other directly, the result can still be an lvalue or xvalue. Item 4.3 is the fallback, converting to the other side's value type.

Note 2 explains that when deciding whether a conversion can be formed, access control, whether an operand is a bit-field, and whether a conversion function is deleted are all ignored; only the types matter.

### The decision (¶4.4–¶4.6)

- ¶4.4 If conversions can be formed in both directions, or the one that can be formed is an ambiguous conversion sequence: ill-formed.
- ¶4.5 If no conversion can be formed in either direction: the operands are left unchanged and passed on to the later steps.
- ¶4.6 If exactly one conversion can be formed: it is applied to that operand, and the converted result is used in place of the operand from then on. Note 3 reminds us that being able to form a conversion sequence doesn't mean the actual conversion is well-formed.

When both directions work it is an error outright, because there is no reasonable basis for preferring one: `A → B` and `B → A` give entirely different result types, and picking one arbitrarily would leave readers unable to predict which.

### Examples

```cpp run title="cond-class.cpp" ok
#include <type_traits>
#include <string>
#include <utility>

struct B {};
struct D : B {};
struct X { operator int() const { return 1; } };

bool c = true;
int a = 0, b = 0;
const int ca = 0;
D d; B bb;
std::string s;
X x;

// lvalues differing only in cv: a → const int& binds directly, the reverse doesn't ⇒ const int lvalue
static_assert(std::is_same_v<decltype((c ? a : ca)), const int&>);

// derived and base lvalues: d → B& binds directly; bb → D& doesn't ⇒ B lvalue
static_assert(std::is_same_v<decltype((c ? d : bb)), B&>);

// derived prvalue and base lvalue: D{} → B& cannot bind to a glvalue, fall back to ¶4.3.2 target B ⇒ slicing, B prvalue
static_assert(std::is_same_v<decltype((c ? D{} : bb)), B>);

// string lvalue and string literal (const char[2] lvalue):
//   s → const char(&)[2] fails, and the ¶4.3.3 fallback const char* fails too;
//   "x" → std::string& cannot bind directly, the ¶4.3.3 fallback std::string works ⇒ string prvalue
static_assert(std::is_same_v<decltype((c ? s : "x")), std::string>);

// class and int: x → int works (conversion function); 1 → X doesn't ⇒ int prvalue
static_assert(std::is_same_v<decltype((c ? x : 1)), int>);

int main() {}
```

When both directions work:

```cpp title="cond-class-ambiguous.cpp" error
struct Q;
struct P { P(); P(const Q&); };
struct Q { Q(); Q(const P&); };

auto r = true ? P() : Q();   // error: both P → Q and Q → P work (¶4.4)
```

Clang's diagnostic is "conditional expression is ambiguous; 'P' can be converted to 'Q' and vice versa".

Access control is ignored in the decision and checked only in the actual conversion:

```cpp title="cond-class-access.cpp" error
struct Priv {
private:
    Priv(int);
};

void f(bool c, Priv& p) {
    auto x = c ? p : 1;      // error: the decision picks 1 → Priv, and the actual conversion calls a private constructor
}
```

With this design, access control never changes the type of the expression. In C++ access control never changes the meaning of a program; it only decides whether the program is well-formed.

## Bit-fields differing only in cv (¶3)

¶3 If the two operands are glvalue bit-fields of the same value category, with types *cv1* `T` and *cv2* `T`, then for the remaining steps of this subclause both are treated as having type *cv* `T`, where *cv* is the union of the two cv-qualifications.

Without this paragraph, two bit-fields differing only in cv would enter paragraph 4, which would try to bind one bit-field to a `const T&`. Binding a reference to a bit-field creates a temporary, which is not direct binding, so the result would degrade to a prvalue. With paragraph 3, they go straight to paragraph 5, and the result is a bit-field lvalue.

```cpp title="cond-bitfield.cpp" ok
struct BF { int b : 3; int c : 3; };

void f(bool cond) {
    BF s{};
    (cond ? s.b : s.c) = 1;          // OK: same type and value category, the result is a bit-field lvalue (¶5)
    (cond ? throw 1 : s.b) = 2;      // OK: ¶2.1, the result is a bit-field lvalue
    // &(cond ? s.b : s.c);          // error: the result is a bit-field, its address cannot be taken
}
```

!!! warning "Compiler status"
    For an `int` bit-field `s.b` and a `const int` bit-field `s.d`, by paragraphs 3 and 5, `cond ? s.b : s.d` should be a `const int` bit-field lvalue. Clang 23 gives an `int` prvalue (`decltype` is `int`), i.e. it doesn't implement paragraph 3 yet.

## Overload resolution with built-in candidates (¶6)

¶6 If none of the above applies, the result is a prvalue. If the two operands have different types and a class type is involved, overload resolution is borrowed to pick the conversions: the candidates are the ones [[over.built]] invents for `?:`, the **built-in candidates** ([[g:built-in-candidate]]), such as `LR operator?:(bool, L, R)` for every pair of promoted arithmetic types `L` and `R`, and `T operator?:(bool, T, T)` for every pointer, pointer-to-member or scoped enumeration type `T`. If overload resolution fails, the program is ill-formed.

`?:` cannot be overloaded by users, and these candidates cannot be called directly; only the mechanism for picking conversions is borrowed. The case it handles is two classes that cannot convert to each other but can both convert to the same built-in type.

```cpp run title="cond-overload.cpp" ok
#include <type_traits>

struct A { operator int() const { return 1; } };
struct B { operator int() const { return 2; } };

// ¶4: A and B cannot convert to each other; ¶6: overload resolution picks int operator?:(bool, int, int)
static_assert(std::is_same_v<decltype(true ? A{} : B{}), int>);

int main() { return (false ? A{} : B{}) == 2 ? 0 : 1; }
```

## Implementation view

!!! impl
    - Simple conditional expressions are often compiled into a branchless conditional move (x86 `cmov`, AArch64 `csel`), which computes both values and then picks one. The as-if rule allows this only when neither branch has side effects or can fail, so `p ? *p : 0` won't dereference `p` early when it is null.
    - The default implementation of `std::common_type` is `decltype(false ? std::declval<T>() : std::declval<U>())` ([[meta.trans.other]]), and `std::common_reference` is also built on the rules of `?:`. So the details of paragraph 4, such as a derived prvalue and a base lvalue merging into a sliced base prvalue, affect library components like Ranges too.
    - GCC and Clang support the extension `x ?: y` with the middle operand omitted, meaning `x ? x : y` with `x` evaluated only once. It is not standard C++, and Clang warns about it under `-pedantic`.

## History and evolution

!!! history
    - C++98 already had lvalue results and the two-way conversion attempt for class types, with wording based on the lvalue/rvalue dichotomy.
    - When C++11 introduced xvalues, item 4.2 (target an rvalue reference) was added, so the result of two xvalue branches can remain an xvalue.
    - The usual arithmetic conversions between different enumerations, and between enumerations and floating-point, were deprecated in C++20 and made ill-formed in C++26, tightening item 7.2 accordingly.

## Common misconceptions

!!! pitfall "Thinking `c ? a : b = 7` assigns to the selected one"
    The third operand is an *assignment-expression*, so this is `c ? a : (b = 7)`. To assign to the selected one, write `(c ? a : b) = 7`.

!!! pitfall "Thinking `c ? obj : std::move(other)` is a reference"
    Mixing an lvalue and an xvalue gives a prvalue, which costs a copy or move.

!!! pitfall "Thinking `?:` lets the two sides have different types, like `if`"
    The two sides must merge into a single type. `c ? 1 : "x"` is ill-formed; if you really need two types, use `std::variant` or rewrite it as an `if`.

## Questions

!!! question "Question 1"
    Given `struct B {}; struct D : B {}; const D cd; B b;`, what are the type and value category of `c ? cd : b`?

<details markdown="1">
<summary>Answer</summary>

The types differ and class types are involved, so paragraph 4 applies.

- `cd` (`const D` lvalue) toward `b` (lvalue): the item 4.1 target `B&` cannot bind to a `const D`; fails. Falling back to item 4.3.2, `B` is a base class of `const D`, so the target is `const B`, which can be formed (slicing on copy).
- `b` (`B` lvalue) toward `cd`: the item 4.1 target `const D&` cannot bind to a `B`; fails. The item 4.3.3 target is `D`, and `B` cannot convert to `D`; fails too.

Exactly one direction succeeds (item 4.6), and `cd` becomes a `const B` prvalue. Now one side is a `const B` prvalue and the other a `B` lvalue: paragraph 5 doesn't apply; in paragraph 6 the two types still differ (class prvalues keep their cv), so overload resolution with built-in candidates is needed, and `B` converts to no arithmetic or pointer type, so overload resolution fails. The program is ill-formed; Clang reports "incompatible operand types ('const D' and 'B')".

For comparison: if `b` is declared `const B`, `cd` → `const B&` binds directly and the result is a `const B` lvalue; if `cd` loses its `const`, the result is a `B` lvalue. When needed, write `static_cast<const B&>(cd)` explicitly.
</details>

!!! question "Question 2"
    When conversions work in both directions, why does paragraph 4 make it ill-formed instead of picking the better one as overload resolution does?

<details markdown="1">
<summary>Answer</summary>

Overload resolution compares conversions of the same argument to different parameter types, so there is a common basis for comparison. With `?:`, the two operands each convert toward the other: `A → B` has result type `B` and `B → A` has result type `A`, and there is no criterion to compare them. Requiring exactly one direction to work makes the result type uniquely determined; when really needed, the programmer can convert one side explicitly.
</details>

## Summary

| Two branches | Result |
|---|---|
| One side is a `throw` | Type and value category of the other side |
| Both `void` | `void` prvalue |
| Glvalues of the same type and value category | That type and value category (can be an lvalue) |
| Lvalues differing only in cv | Lvalue of the more cv-qualified type |
| Derived and base lvalues | Base lvalue |
| Class types, only one direction converts | The converted type |
| Class types, both directions convert | {{ill-formed}} |
| Both classes convert to some built-in type | Type chosen by overload resolution, prvalue |
| Arithmetic, enumeration | Type after the usual arithmetic conversions, prvalue |
| Pointers, pointers to members | Composite pointer type, prvalue |
| Lvalue and xvalue of the same type | prvalue |
