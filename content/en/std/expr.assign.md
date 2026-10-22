---
title: Assignment and compound assignment operators
summary: "= and op= require a modifiable lvalue and yield an lvalue; since C++17 the right operand is sequenced before the left; compound assignment is equivalent to E1 = E1 op E2 except that E1 is evaluated only once; plus the rules for bit-fields, volatile, partial overlap and a braced list on the right."
updated: 2026-10-19
---

!!! tldr
    - The left operand of an assignment must be a modifiable lvalue; the result is an lvalue referring to the left operand, so `(a = b) = c` is valid in C++.
    - Since C++17 the right operand is sequenced before the left operand, so `a[i] = i++` and `m[k] = m.size()` have determined results.
    - `E1 op= E2` is equivalent to `E1 = E1 op E2`, except that `E1` is evaluated only once; the implicit conversion in between has no narrowing check, so `i /= 2.0` silently truncates.
    - The right side of an assignment can be a braced list: for scalars it forbids narrowing, and for class types it is passed as the argument to `operator=`.
    - Assigning from a partially overlapping object is UB; when a signed bit-field cannot hold the assigned value, the result is implementation-defined; using the result of a volatile assignment is deprecated.

## Grammar: right-to-left, the result is an lvalue (¶1)

```text
assignment-expression:
    conditional-expression
    yield-expression
    throw-expression
    logical-or-expression assignment-operator initializer-clause

assignment-operator: one of
    =  *=  /=  %=  +=  -=  >>=  <<=  &=  ^=  |=
```

*assignment-expression* is the level of the expression grammar just above the comma expression, and `co_yield` ([[expr.yield]]) and `throw` ([[expr.throw]]) are placed here too. Three things can be read from the grammar:

- Assignment groups right-to-left: `a = b = c` is `a = (b = c)`.
- The left operand is a *logical-or-expression*, so `c ? a : b = 1` can only be parsed as `c ? a : (b = 1)` ([[expr.cond]]).
- The right operand is an *initializer-clause*, which can be an expression or a braced list (see paragraph 8).

¶1 All assignment operators require the left operand to be a **modifiable lvalue** ([[g:modifiable-lvalue]], an lvalue whose type is neither const-qualified nor a function type, [[basic.lval#10]]). The result is an lvalue of the type of the left operand, referring to the left operand; if the left operand is a bit-field, the result is a bit-field.

```cpp run title="assign-lvalue.cpp" ok
#include <type_traits>

int a, b, c;
static_assert(std::is_same_v<decltype(a = b), int&>);      // the result is an int lvalue
static_assert(std::is_same_v<decltype(a += 1.5), int&>);   // same for compound assignment

int main() {
    a = 1; b = 2; c = 3;
    (a = b) = c;          // OK: first a = b, then assign c to the result (i.e. a)
    a = b = c;            // right-to-left
    return (a == 3 && b == 3) ? 0 : 1;
}
```

```cpp title="assign-not-modifiable.cpp" error
void f() {
    const int k = 0;
    int arr[2], arr2[2];
    k = 1;          // error: a const object is not a modifiable lvalue
    arr = arr2;     // error: arr2 cannot be implicitly converted to int[2] (¶3)
    1 = k;          // error: the left operand is not an lvalue
}
```

An array lvalue is modifiable by definition; arrays can't be assigned because of paragraph 3: the right operand must first be implicitly converted to the type of the left operand, which requires `int t[2] = arr2;` to be well-formed, and an array cannot be initialized from another array expression.

In C, the result of an assignment expression is not an lvalue. C++ makes it an lvalue, and the convention that `operator=` returns `T&` is there to stay consistent with built-in assignment.

The modifiable-lvalue requirement applies only to built-in assignment. Assignment of class types usually calls a member `operator=` ([[class.copy.assign]], [[over.assign]]), which is just a member function call, so `S() = s;` is valid even on a prvalue, unless `operator=` has a `&` qualifier.

## Evaluation order (¶1)

```cpp run title="assign-order.cpp" ok
#include <map>
#include <cstddef>

int main() {
    int i = 0;
    i = i++ + 1;         // the right side is fully evaluated first (value 0 + 1, i becomes 1), then assigned → i == 1
    int a[4]{};
    a[i] = i++;          // first the right side i++ (value 1, i becomes 2), then a[i] → a[2] = 1
    std::map<int, std::size_t> m;
    m[0] = m.size();     // first m.size() (0), then m[0] inserts → m[0] == 0
    return (i == 2 && a[2] == 1 && m[0] == 0) ? 0 : 1;
}
```

¶1 specifies three layers of ordering for assignment:

1. The side effect of writing to the left operand is sequenced after the value computations of the left and right operands, and before the value computation of the assignment expression.
2. The right operand is **sequenced before** ([[g:sequenced-before]]) the left operand. This sentence was added in C++17 by [[P0145R3]].
3. With respect to an indeterminately-sequenced function call, a compound assignment is a single evaluation. Note 1 explains that a function call cannot intervene between the read and the write-back of a compound assignment.

Rule 2 gives all three lines of the example above determined results in C++17. In C++14, the first two lines are UB (there is no ordering between the modification of `i` and another access to it), and the result of the third line is unspecified and may be 1. Clang's `-Wunsequenced` warns about the first two lines under `-std=c++14`, and not under `-std=c++17`.

Right before left was chosen because the target of an assignment often depends on side effects of the right side, as in `*p = alloc()` and `m[k] = compute()`; it also matches the intuition of chained assignment `a = b = c`: compute the value first, then decide where to put it. Through [[over.match.oper]], this order also applies to an overloaded `operator=` invoked with operator syntax. See [[topics/order-of-evaluation]] for the full discussion.

Rule 3 guarantees that `x += f()` doesn't become UB because `f` modifies `x` internally: reading `x`, adding, and writing back `x` happen as a whole either before or after `f()`, and `f()` doesn't intervene. Postfix `++` has the same rule ([[expr.post.incr]]).

## What simple assignment stores (¶2–¶3)

¶3 If the right operand is an expression, it is first implicitly converted ([[conv]]) to the cv-unqualified type of the left operand.

¶2 Let `V` be the result of the right operand; the object referred to by the left operand is modified, and its new value is:

- ¶2.1 if the object has integer type: the value congruent to `V` ([[basic.fundamental]]), i.e. stored modulo 2<sup>N</sup>;
- ¶2.2 if the left operand is a glvalue of volatile-qualified pointer type `T` and `V` is a pointer value that is invalid in the context of the evaluation ([[basic.compound]]): `reinterpret_cast<T>(reinterpret_cast<std::uintptr_t>(V))`;
- ¶2.3 otherwise: `V`.

¶2.2 is new wording after C++23. It handles writing an already invalidated pointer (for example, one whose object has been deallocated) into a `volatile` pointer object. Using an invalid pointer value is usually implementation-defined or undefined ([[basic.compound#6]]); here it is made explicit that what is written is the address value after a round trip through an integer, giving code that stores addresses unchanged into hardware registers or shared memory semantics it can rely on.

## Compound assignment (¶6)

```cpp run title="assign-compound.cpp" ok
int main() {
    char c = 'a';
    c += 1;            // c = c + 1: computed in int, then converted back to char
    short s = 300;
    s *= 2;            // int arithmetic gives 600, then converted back to short
    int i = 7;
    i /= 2.0;          // i = i / 2.0: double arithmetic gives 3.5, converted back to int gives 3
    int arr[4]{};
    int* p = arr;
    p += 3;            // += on a pointer is valid
    return (c == 'b' && s == 600 && i == 3 && p == arr + 3) ? 0 : 1;
}
```

¶6 The behavior of a [[g:compound-assignment|compound assignment]] `E1 op= E2` is equivalent to `E1 = E1 op E2`, except that `E1` is evaluated only once. Note 2 points out that the object designated by `E1` is still accessed twice, once to read and once to write.

- For `+=` and `-=`, `E1` can have arithmetic type, or be a pointer to a completely-defined object type;
- for the other compound assignments, `E1` must have arithmetic type.

```cpp title="assign-compound-bad.cpp" error
enum E { e0, e1 };

void f(int* p, E e) {
    p *= 2;        // error: except for += and -=, E1 must have arithmetic type
    e |= e1;       // error: the result of e | e1 is int, which doesn't convert back to E implicitly
}
```

Being equivalent to `E1 = E1 op E2` means the operation applies the usual arithmetic conversions according to the rules of `op`, and the result is then implicitly converted back to the type of `E1`. That step is an ordinary implicit conversion with no narrowing check: `i /= 2.0` silently truncates to 3. Only if you write `i = {i / 2.0}` do the narrowing rules for braced lists (paragraph 8) reject it.

`E1` being evaluated only once is visible only when `E1` has side effects: `a[i++] += 1` increments `i` only once. Writing `a[i++] = a[i++] + 1` is a different matter: the two `i++` belong to the right and left operands respectively, and since C++17 right comes before left, so the right side reads `a[0]`, the left side writes `a[1]`, and `i` is incremented twice. It is defined in C++17, but almost never what you want.

## A braced list on the right (¶8)

```cpp run title="assign-braced.cpp" ok
#include <complex>
#include <vector>

int main() {
    int a = 5, b = 0;
    a = {};                       // a = 0 (value-initialization)
    a = b = {1};                  // a = (b = 1)
    std::complex<double> z;
    z = {1, 2};                   // z.operator=({1, 2})
    std::vector<int> v;
    v = {1, 2, 3};                // vector::operator=(initializer_list<int>)
    return (a == 1 && z.imag() == 2 && v.size() == 3) ? 0 : 1;
}
```

¶8 A braced list `B` may appear on the right of two kinds of assignment:

- ¶8.1 Assignment to an object of scalar type `T`: `B` has at most one element, and `x = B` means `x = t`, where `t` is an invented temporary variable `T t = B;`. So narrowing conversions are rejected, and an empty `{}` gives value-initialized zero.
- ¶8.2 Assignment to an object of class type: `B` is passed as the argument to the assignment operator function selected by overload resolution.

```cpp title="assign-braced-bad.cpp" error
void f() {
    int a = 0, b = 0;
    a = {1.5};       // error: narrowing, T t = {1.5} is ill-formed
    a = {1, 2};      // error: a scalar takes at most one element
    a = {1} = b;     // error: a braced list cannot be the left operand of an assignment
}
```

!!! lawyer "Compound assignment and braced lists"
    The grammar allows `x += {1}`, because the right operand is always an *initializer-clause*. But item 8.1 only defines the meaning of `x = B`; expanding `x += B` into `x = x + B` per paragraph 6 gives `x + {1}`, which is not itself a valid expression. This is a gap in the wording; Clang 23 accepts `int a = 0; a += {1};`.

    The standard's example also contains `z += { 1, 2 }`, saying it means `z.operator+=({1,2})`. Per the declarations in [[complex.member.ops]], that call doesn't actually match: `operator+=(const double&)` cannot be initialized from `{1, 2}`, and the template `operator+=(const complex<X>&)` cannot deduce `X` from a braced list. libc++ does reject it. Examples are not normative.

## Bit-fields (¶4)

¶4 If the left operand is a bit-field that cannot represent the value being assigned, the resulting value of the bit-field is implementation-defined {{impl}}.

```cpp run title="assign-bitfield.cpp" impl
#include <cstdio>

struct S { int b : 3; unsigned u : 3; };

int main() {
    S s{};
    s.b = 7;     // implementation-defined: a 3-bit signed bit-field only holds -4..3; GCC and Clang give -1
    s.u = 9;     // unsigned bit-field: 1 is stored, modulo 2^3
    std::printf("%d %u\n", s.b, s.u);
}
```

Unsigned bit-fields store modulo, with the result determined by the integral conversion rules; it is not implementation-defined. Paragraph 4 applies only when a signed bit-field cannot hold the value. Clang gives a `-Wbitfield-constant-conversion` warning in the constant case.

## Using the result of a volatile assignment is deprecated (¶5) {{deprecated}}

¶5 An assignment whose left operand has volatile-qualified type is deprecated unless the (possibly parenthesized) assignment is a **discarded-value expression** ([[g:discarded-value-expression]], an expression whose result is not used, such as a standalone expression statement) or an unevaluated operand. In other words, assigning to a `volatile` object is fine in itself; what is deprecated is using the result of that assignment expression.

```cpp title="assign-volatile.cpp" ok
volatile int reg;
int x, y;

void f() {
    reg = x;         // OK: the result is discarded
    y = reg;         // OK: this is an assignment to y; reg is only read
    reg += x;        // OK
    reg |= 0x1;      // OK
    y = reg = x;     // deprecated: uses the result of a volatile assignment
}
```

`y = reg = x` writes `x` into `reg` and then writes the value of the assignment expression into `y`. If `reg` is a hardware register, a reader may think `y` gets its value from re-reading `reg`, and the standard has never specified whether it is re-read. Clang diagnoses this line with `-Wdeprecated-volatile`.

!!! history "Back and forth on volatile compound assignment"
    C++20's [[P1152R4]] deprecated a batch of `volatile` uses, including all compound assignments to `volatile` objects, on the grounds that read-modify-write is easily mistaken for being atomic. Embedded code operates on registers with `REG |= BIT` all the time, and vendors' C headers must also compile as C++, so [[P2327R1]] undeprecated the bitwise compound assignments, and [[CWG2654]] undeprecated the rest. What remains deprecated: using the result of a volatile assignment, `++` and `--` on `volatile` objects, `volatile` parameters and return types, and `volatile` structured bindings ([[depr.volatile.type]]).

## Partially overlapping objects (¶7)

¶7 If the value being stored in an object is read from another object that overlaps in any way the storage of the first object, then the overlap shall be exact and the two objects shall have the same type; otherwise the behavior is undefined {{ub}}. Note 3 explains that this only constrains the relationship between the two sides of the assignment; it is not a general aliasing rule (for that, see [[basic.lval]]).

This rule gives implementations freedom: assignment of trivial class types can move bytes in any order and any width, like `memcpy`, without having to handle partial overlap like `memmove`. Exact overlap (self-assignment) is fine, each byte copied onto itself; partial overlap might read bytes that have already been overwritten.

Partial overlap can basically only arise through unions:

```cpp title="assign-overlap.cpp" ub
struct A { int a, b; };
struct B { int pad; A in; };   // B::in is at offset sizeof(int) from the start of the union
union U { A x; B y; };

int main() {
    U u{.x = {1, 2}};
    u.y.in = u.x;     // UB: the source u.x and the target u.y.in partially overlap
    return u.y.in.a;
}
```

Running this code with `-fsanitize=address` in our tests, AddressSanitizer reports `memcpy-param-overlap`: Clang compiled this assignment into exactly a `memcpy`. The correct way is to copy into a temporary first: `A tmp = u.x; u.y.in = tmp;`.

!!! impl
    Built-in assignment compiles to a single store instruction, with a type conversion first if needed. For ordinary memory, compound assignment is three steps, read, modify, write, and not an atomic operation; even though x86's `add [mem], reg` is a single instruction, without a `lock` prefix it is not guaranteed to be atomic. For atomicity use `std::atomic`, whose `+=` is an atomic read-modify-write operation.

## Common misconceptions

!!! pitfall "Thinking `x += 1` is atomic"
    It is a read-modify-write; across threads, use `std::atomic`.

!!! pitfall "Thinking `i = i++ + 1` is defined in C++14 too"
    Before C++17 it is UB. Since C++17 it is defined, but still hard to read; don't write it.

## Questions

!!! question "Question 1"
    In C++17, what is `i` after `int i = 0; i += i++;`?

<details markdown="1">
<summary>Answer</summary>

The right operand is evaluated first: the value of `i++` is 0, and its side effect makes `i` 1. Then the compound assignment reads `i` (now 1), adds the right operand's value 0, and writes back 1. The result is `i == 1`, defined. In C++14, there is no ordering between the side effect of `i++` and the compound assignment's read and write of `i`, so it is UB.
</details>

!!! question "Question 2"
    What is `s.v` after `struct S { int v; S& operator=(int x) { v = x; return *this; } }; S s; int i = 0; s = i++, i;`?

<details markdown="1">
<summary>Answer</summary>

The comma has lower precedence than assignment, so this is `(s = i++), i;`. `s = i++` calls `s.operator=(i++)`; the value of `i++` is 0, so `s.v == 0`, and then `i` is evaluated and discarded. To give `s` the value of the comma expression, write `s = (i++, i)`, in which case `s.v == 1`.
</details>

## Summary

| Aspect | Rule | Paragraph |
|---|---|---|
| Left operand | Modifiable lvalue | ¶1 |
| Result | Lvalue of the left operand's type; a bit-field stays a bit-field | ¶1 |
| Evaluation order | Right before left (C++17); the write comes after the value computations of both sides | ¶1 |
| Compound assignment and function calls | A single evaluation | ¶1 |
| Value stored | Congruent value for integer types; an invalid value stored into a volatile pointer round-trips through `uintptr_t` | ¶2 |
| Signed bit-field can't hold the value | {{impl}} | ¶4 |
| Using the result of a volatile assignment | {{deprecated}} | ¶5 |
| `E1 op= E2` | Equivalent to `E1 = E1 op E2`, with `E1` evaluated only once | ¶6 |
| Partially overlapping assignment | {{ub}} | ¶7 |
| Braced list on the right | Scalar: at most one element, no narrowing; class: passed to `operator=` | ¶8 |
