---
title: Exam 5 · Expressions, evaluation order and constant evaluation
summary: 25 questions on evaluation order, integral promotions and arithmetic conversions, shifts and out-of-range conversions, pointer comparison, the conditional operator, lambda captures and closure types, structured bindings, constant evaluation, immediate functions and static initialization order, with the emphasis on telling UB, unspecified behavior and implementation-defined behavior apart.
tags: evaluation order, arithmetic conversions, UB, lambdas, structured bindings, constant evaluation, exam
updated: 2026-10-20
---

!!! tldr
    - Scope: sequenced, indeterminately sequenced and unsequenced evaluations in [[intro.execution]]; integral promotions, the usual arithmetic conversions, shifts, division, floating-point and enumeration conversions; pointer comparison; the value categories of the conditional and comma operators; lambda captures, closure types, structured bindings; core constant expressions in [[expr.const]], `consteval` and immediate escalation, `constinit`, `std::is_constant_evaluated`, dynamic allocation at compile time; dynamic initialization order across translation units.
    - Question types: 15 verdict, 7 multiple choice, 3 open-ended, roughly increasing in difficulty.
    - For verdict questions, answer with the most severe property of the whole program. Unless a question says otherwise, assume `short` is 16 bits and `int` is 32 bits.
    - Suggested time: 90 minutes. After answering, write down the clause numbers yourself before opening the explanation to check.

## 1. Evaluation order

<div class="quiz" data-kind="verdict" data-answer="ok" markdown="1">

Judge this program.

```cpp run
int main() {
    int i = 0;
    i = i++ + 1;
    return i;
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: well-formed with well-defined behavior; `main` returns 1.**

1. [[intro.execution#10]] says that if a side effect on a memory location is unsequenced relative to another side effect on the same location or to a value computation using it, the behavior is undefined. There are two side effects on `i` here: the increment of `i++` and the write of `=`.
2. [[expr.assign#1]] says the right operand of an assignment is sequenced before the left operand, and the assignment itself happens after the value computations of both operands. By the last sentence of [[intro.execution#8]], the right operand being sequenced before the left means all of its value computations and side effects come first. So the increment of `i++` completes first, and only then is `0 + 1` written.
3. Example 3 in [[intro.execution#10]] contains exactly this line, with the comment "the value of i is incremented".

`ub` is the C++14 answer. Back then the side effect of the assignment was sequenced only after the value computations of the operands, with no ordering relative to the side effect of `i++`. C++17 added the right-before-left rule through [[P0145R3]].

One change makes it UB: read `i` once more in the right operand. The two operands of `+` are still unsequenced, so the modification by `i++` conflicts with the read of `i` on the other side.

```cpp ub
int main() {
    int i = 0;
    i = i++ + i;
    return i;
}
```

For more examples see [[topics/order-of-evaluation]].

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="unspecified" markdown="1">

Judge this program.

```cpp run
#include <cstdio>

void f(int a, int b) { std::printf("%d %d\n", a, b); }

int main() {
    int i = 0;
    f(i++, i++);
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: unspecified behavior. It prints `0 1` or `1 0`; it is not UB.**

1. [[expr.call#8]]: the initialization of each parameter, including every associated value computation and side effect, is indeterminately sequenced with respect to that of any other parameter.
2. [[intro.execution#8]]: of two indeterminately sequenced evaluations, one always happens before the other; it is just unspecified which, and they do not interleave.
3. So the two `i++` are not unsequenced, and the UB condition of [[intro.execution#10]] does not hold. What remains is an unspecified order, which is unspecified behavior in the sense of [[intro.abstract#3]].

Clang 23 prints `0 1` and also gives a `-Wunsequenced` warning (multiple unsequenced modifications). Under the rules since C++17, that warning is a false positive: the two modifications are not unsequenced. In C++14 the arguments really were unsequenced, and this line was UB.

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="D" markdown="1">

Each of the four lines below appears on its own in `test` (with `i` initially 0). Which line has undefined behavior?

```cpp
void f(int, int) {}

void test() {
    int i = 0;
    int a[4]{};
    a[i] = i++;                       // A
    i = (i++, i);                     // B
    f(i = 1, i = 2);                  // C
    (void)((i = 1, 0) + (i = 2, 0));  // D
}
```

- A. `a[i] = i++;`
- B. `i = (i++, i);`
- C. `f(i = 1, i = 2);`
- D. `(i = 1, 0) + (i = 2, 0)`

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: D.**

- D: the comma operator only guarantees left-before-right within each pair of parentheses ([[expr.comma#1]]). The two operands of `+` are unsequenced (first sentence of [[intro.execution#10]]), so the two assignments to `i` are unsequenced relative to each other: UB. The `(u.x = 1, 0) + (u.y = 2, 0)` in example 3 of [[intro.execution#10]] has the same structure, where the two union members occupy the same memory location.
- A: per [[expr.assign#1]] the right operand is evaluated first; `i++` yields 0 and `i` becomes 1; then the left operand `a[1]` is evaluated and 0 is written. Well-defined.
- B: the comma operator sequences the side effect of `i++` before the read of `i` on its right ([[expr.comma#1]]), and the whole comma expression is the right operand of the assignment, sequenced before the assignment. The result is `i == 1`.
- C: the argument initializations are indeterminately sequenced ([[expr.call#8]]) and do not interleave; whether `i` ends up 1 or 2 is unspecified, but it is not UB.

Clang gives `-Wunsequenced` for both C and D, and for C it is a false positive. Going by the warnings alone, you would judge C to be UB as well.

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ok" markdown="1">

Judge this program.

```cpp run
constexpr int f() {
    int i = 0;
    return i++ + i++;
}
static_assert(f() == 1);

int main() {}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: well-formed.**

1. The condition of `static_assert` is a constant expression, and `f()` is evaluated as a core constant expression.
2. [[intro.execution#16]] says that when evaluated as a core constant expression, operands and subexpressions that would otherwise be unsequenced or indeterminately sequenced are evaluated in lexical order. So the left `i++` completes first (value 0, `i` becomes 1), then the right `i++` is evaluated (value 1), and the result is 1.
3. The two modifications are now ordered, the UB of [[intro.execution#10]] does not arise, and so there is no undefined operation for [[expr.const.core#2.8]] to diagnose.

The tempting answer is `error`: normally, constant evaluation that hits UB is not a constant expression. But here there is no UB in constant evaluation at all. The lexical-order rule is new wording added after C++23.

Clang 23 accepts this code and gives a `-Wunsequenced` warning on the `return` line. The warning is justified: when the same function is called at run time, [[intro.execution#16]] does not apply, and `i++ + i++` is still UB.

```cpp ub
constexpr int f() {
    int i = 0;
    return i++ + i++;
}

int main() { return f(); }   // not a manifestly constant-evaluated context; evaluated by run-time rules
```

</details>
</div>

<div class="quiz" data-kind="open" markdown="1">

What does this program return since C++17? Derive the result step by step from the rules of [[expr.assign]], and explain why it was UB in C++14.

```cpp run
int main() {
    int x = 3, y = 5;
    x ^= y ^= x ^= y;
    return x * 10 + y;
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: it returns 53, that is, `x == 5` and `y == 3`.**

1. Assignment operators group right to left ([[expr.assign#1]]), so the expression is `x ^= (y ^= (x ^= y))`.
2. For the outermost `^=`: the whole right operand `y ^= (x ^= y)` is sequenced before the left operand `x`, and the compound assignment itself happens after the value computations of both operands ([[expr.assign#1]]). [[expr.assign#6]] says `E1 op= E2` is equivalent to `E1 = E1 op E2` except that `E1` is evaluated only once; the compound assignment reads the old value of `x` at this step, so it reads the value already modified by the inner levels.
3. The same reasoning applies level by level going inward:
    - innermost `x ^= y`: `x = 3 ^ 5 = 6`;
    - middle `y ^= 6`: `y = 5 ^ 6 = 3`;
    - outermost `x ^= 3`: `x = 6 ^ 3 = 5`.
4. In our tests it returns 53.

C++14 only specified that the side effect of an assignment is sequenced after the value computations of its operands, not that the side effects of the right operand come before the left operand. The two writes to `x` were in fact ordered (the side effect of the inner assignment precedes the inner value computation, and the outer assignment comes after it); the problem was the read: the outermost `^=` reading the old value of `x` was unsequenced relative to the innermost modification of `x`, which was UB under the [[intro.execution]] rules of the time. C++17's [[P0145R3]] gave assignment its right-before-left ordering, and only then did this line acquire a definite result.

</details>
</div>

## 2. Integral promotions, arithmetic conversions and out-of-range values

<div class="quiz" data-kind="choice" data-answer="B" markdown="1">

What does this program print?

```cpp run
#include <cstdio>

int main() {
    unsigned short us = 1;
    std::printf("%d %d %d\n", -1 < 0u, -1 < us, us - 2 < 0);
}
```

- A. `0 0 0`
- B. `0 1 1`
- C. `1 1 1`
- D. `0 1 0`

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: B; it prints `0 1 1`.**

1. `-1 < 0u`: relational operators apply the usual arithmetic conversions to arithmetic operands ([[expr.rel#3]]). `int` and `unsigned int` have the same rank, so per [[expr.arith.conv#1.5.3.1]] the common type is `unsigned int`. `-1` is converted modulo 2^N per [[conv.integral#3]] to `UINT_MAX`, and the comparison is false.
2. `-1 < us`: integral promotion comes first. `int` can represent every value of `unsigned short`, so `us` is promoted to `int` ([[conv.prom#2]]); two `int`s are compared, and the result is true.
3. `us - 2 < 0`: `us` is likewise promoted to `int`, `1 - 2` gives `-1`, which is less than 0: true.

Items 2 and 3 depend on the widths of the integer types, which are implementation-defined ([[basic.fundamental#4]]). On a platform where `int` is only 16 bits, `int` cannot hold every value of `unsigned short`, `us` is promoted to `unsigned int`, and the output becomes `0 0 0`. Clang 23 prints `0 1 1` and gives a `-Wtautological-constant-out-of-range-compare` warning for the second item.

To compare signed and unsigned numbers mathematically, use `std::cmp_less`; see [[topics/arithmetic]].

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ub" markdown="1">

Judge this program.

```cpp run
unsigned mul(unsigned short a, unsigned short b) {
    return a * b;
}

int main() {
    return mul(65535, 65535) == 4294836225u;
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: undefined behavior.**

1. `a` and `b` are both `unsigned short` and are promoted to `int` before `*` per [[conv.prom#2]] (`int` can represent every value of `unsigned short`). After the usual arithmetic conversions of [[expr.mul#2]], the multiplication is performed in `int`.
2. The mathematical result 4294836225 is outside the range of `int`. [[expr.pre#4]]: if the mathematical result of an arithmetic expression is not in the range of representable values for its type, the behavior is undefined.
3. That the return type is `unsigned` does not matter; the conversion happens after the multiplication.

The tempting answer is `ok`: both operands are unsigned, so it looks as if arithmetic should wrap modulo 2^N. But wrapping is only a rule of integral conversions ([[conv.integral#3]]), and this multiplication is not done in an unsigned type at all.

Make the function `constexpr` and put it in a `static_assert`, and Clang reports value 4294836225 is outside the range of representable values of type 'int'; at run time UBSan reports signed integer overflow. Converting one operand to `unsigned` first makes it defined:

```cpp run ok
constexpr unsigned mul(unsigned short a, unsigned short b) {
    return 1u * a * b;
}
static_assert(mul(65535, 65535) == 4294836225u);

int main() {}
```

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="C" markdown="1">

Which of the four declarations below is ill-formed?

```cpp
#include <climits>

constexpr int a = -1 << 31;        // A
constexpr int b = 1 << 31;         // B
constexpr unsigned c = 1u << 32;   // C
constexpr int d = -8 >> 1;         // D
```

- A. `a`
- B. `b`
- C. `c`
- D. `d`

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: C.**

1. C: [[expr.shift#1]] says the behavior is undefined if the right operand is negative, or greater than or equal to the width of the promoted left operand. `unsigned int` is 32 bits wide, so shifting by 32 is UB, regardless of whether the left operand is unsigned. UB in constant evaluation makes the expression not a core constant expression ([[expr.const.core#2.8]]), and a `constexpr` variable must be constant-initializable ([[dcl.constexpr#6]]), so the declaration of `c` is ill-formed. Clang's note is shift count 32 >= width of type 'unsigned int'.
2. A and B: since C++20, the value of `E1 << E2` is the unique value congruent to E1×2^E2 modulo 2^N ([[expr.shift#2]]), where N is the width of the result type. Both give `INT_MIN`. Shifts are not among the arithmetic expressions covered by [[expr.pre#4]], so there is no overflow UB.
3. D: [[expr.shift#3]] says `E1 >> E2` is E1/2^E2 rounded toward negative infinity, giving -4.

Before C++20, A was UB (left-shifting a negative number) and the result of D was implementation-defined. C++20 specified two's complement for signed integers ([[P1236R1]]), and the shift rules were rewritten accordingly. Clang 23 with `-pedantic` gives no warning for A, B or D:

```cpp run ok
#include <climits>

constexpr int a = -1 << 31;
constexpr int b = 1 << 31;
constexpr int d = -8 >> 1;
static_assert(a == INT_MIN && b == INT_MIN && d == -4);

int main() {}
```

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ub" markdown="1">

Judge this program.

```cpp run
#include <climits>

int rem(int a, int b) { return a % b; }

int main() {
    return rem(INT_MIN, -1);
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: undefined behavior.**

The last sentence of [[expr.mul#4]]: if the quotient `a/b` is not representable in the type of the result, the behavior of both `a/b` and `a%b` is undefined. The mathematical result of `INT_MIN / -1` is 2^31, which does not fit in `int`, so `INT_MIN % -1` is UB too.

The tempting answer is `ok`: mathematically the remainder is 0, which is perfectly representable. The standard ties the two together because common hardware computes quotient and remainder with the same division instruction, and the instruction itself faults when the quotient overflows; x86 `idiv`, for example, raises an exception.

In our tests UBSan reports division of -2147483648 by -1 cannot be represented in type 'int'. In a `static_assert`, Clang rejects it and notes that 2147483648 is outside the range of `int`. With a divisor of 1 there is no problem:

```cpp run ok
#include <climits>

constexpr int rem(int a, int b) { return a % b; }
static_assert(rem(INT_MIN, 1) == 0);

int main() {}
```

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ub" markdown="1">

Judge this program.

```cpp run
unsigned to_u(double d) { return d; }

int main() {
    return to_u(-1.0) == 0xFFFFFFFFu;
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: undefined behavior.**

1. `return d;` implicitly converts `double` to `unsigned`, a floating-integral conversion. [[conv.fpint#1]]: the fractional part is truncated first, and if the truncated value cannot be represented in the destination type, the behavior is undefined.
2. `-1.0` truncates to -1, which `unsigned` cannot represent.

The tempting answer is `ok`, expecting `UINT_MAX`. The modular rule belongs only to conversions between integer types ([[conv.integral#3]]); it does not apply when the source is floating-point.

The boundary is after truncation: `to_u(-0.5)` truncates to 0, which is representable, so the result is defined.

```cpp run ok
constexpr unsigned to_u(double d) { return d; }
static_assert(to_u(-0.5) == 0);

int main() {}
```

Put `to_u(-1.0)` in the initializer of a `constexpr` variable and Clang reports value -1 is outside the range of representable values of type 'unsigned int'; at run time UBSan gives the same diagnostic.

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ok" markdown="1">

Judge this program.

```cpp run
enum E { A = 1, B = 4 };
enum G { M = -1, N = 1 };

constexpr E e = static_cast<E>(7);
constexpr G g = static_cast<G>(-2);

int main() { return int(e) + int(g); }
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: well-formed; `main` returns 5.**

1. Neither enumeration has a fixed underlying type. [[dcl.enum#8]] says their values are those of the hypothetical integer type with minimal width that can represent all the enumerators; values other than the enumerators themselves also belong to the enumeration.
2. The enumerators of `E` are 1 and 4, both non-negative, so a 3-bit unsigned type suffices, and the range is 0 to 7.
3. The enumerators of `G` are -1 and 1, which need a signed type; 2-bit two's complement represents -2 to 1, and those four values are the range.
4. [[expr.static.cast#8]]: if the value is within the range of the enumeration it is unchanged; otherwise the behavior is undefined. Both 7 and -2 are within range, so both initializations are constant expressions.

The tempting answers are `error` or `ub`, on the grounds that there is no enumerator with value 7 or -2. The range is computed from bit width, not from the list of enumerators.

One step outside the range is UB, and in constant evaluation that makes it ill-formed. Clang's note is integer value 8 is outside the valid range of values [0, 7] for the enumeration type 'E':

```cpp error
enum E { A = 1, B = 4 };
enum G { M = -1, N = 1 };

constexpr E e = static_cast<E>(8);     // error: outside [0, 7]
constexpr G g = static_cast<G>(-3);    // error: outside [-2, 1]
```

Written as `enum E : int { ... }`, the underlying type is fixed and the range is every value of `int` (first sentence of [[dcl.enum#8]]).

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

Judge this program against the current draft.

```cpp run
enum Color { Red, Green };
enum Fruit { Apple, Banana };

int main() {
    return Red + Apple;
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: ill-formed.**

`+` applies the usual arithmetic conversions to its two operands ([[expr.add]]). [[expr.arith.conv#1.3]]: if one operand is of enumeration type and the other is of a different enumeration type or a floating-point type, the expression is ill-formed.

This was deprecated in C++20 and removed in C++26 by [[P2864R2]]; it is now a hard error. `ok` is the answer for C++17 and earlier, when both enumerations were first promoted to `int`. Clang 23 with `-std=c++2c` reports invalid arithmetic between different enumeration types; the diagnostic group is `-Wenum-enum-conversion`, but in this mode it is an error by default.

The rule only blocks enumeration with a different enumeration, and enumeration with floating-point:

```cpp run ok
enum Color { Red, Green };
enum Fruit { Apple, Banana };

int a = Red + 1;         // enumeration and integer: promoted, then added
int b = +Red + Apple;    // unary + performs integral promotion first, so the left operand is already int

int main() { return a + b; }
```

Unary `+` performs integral promotion on an enumeration ([[expr.unary.op#7]]), so the second line is `int` plus enumeration, not restricted by 1.3. `Red == Apple` and `Red + 1.0` are ill-formed too; the equality operators also perform the usual arithmetic conversions ([[expr.eq#9]]).

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="impl" markdown="1">

Judge the return value of this program.

```cpp run
int main() {
    char c = 200;
    return c < 0;
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: implementation-defined behavior.**

1. [[basic.fundamental#7]]: whether the underlying type of `char` is `signed char` or `unsigned char` is chosen by the implementation.
2. `char c = 200;` is an integral conversion from `int` to `char`. [[conv.integral#3]] says the result is the unique value congruent to 200 modulo 2^N. If `char` is signed, that is -56 and the function returns 1; if unsigned, it is 200 and the function returns 0.
3. The conversion itself can never be UB. Since C++20, integral conversions are defined modulo 2^N for signed destination types too.

The tempting answer is `ub`, treating this conversion as signed overflow. Overflow UB applies only to the results of arithmetic expressions ([[expr.pre#4]]), and there is no arithmetic here.

On Apple arm64, where we tested, `char` is signed and the program returns 1, with Clang warning that the conversion changes value from 200 to -56; compiled with `-funsigned-char`, it returns 0.

</details>
</div>

## 3. Pointer comparison, the conditional operator, lambdas and structured bindings

<div class="quiz" data-kind="open" markdown="1">

For each of the four comparisons below, answer: is the run-time result true, false or unspecified? Can it appear in a constant expression?

```cpp
struct S {
    int x;
private:
    int y = 0;
public:
    constexpr bool f() const { return &x < &y; }
};

int a[2];
int b;

// (1) &a[0] < &a[1]
// (2) S{}.f()
// (3) &a[0] < &b
// (4) &a[2] == &b
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: (1) true, constant; (2) true, constant; (3) unspecified, not constant; (4) unspecified, not constant.**

1. Of two different elements of the same array, the one with the larger subscript compares greater ([[expr.rel#4.1]]).
2. Of two different non-static data members of the same object, the one declared later compares greater ([[expr.rel#4.2]]), under just two conditions: neither member is a subobject of zero size, and the class is not a union. The old rule also required both members to have the same access control; C++23 removed that condition through [[P1847R4]], so the result is definitely true and may appear in a constant expression. Clang 23 still applies the old rule during constant evaluation and reports comparison of address of fields 'x' and 'y' of 'S' with differing access specifiers (public vs private) has unspecified value; the compiler has not caught up with the current draft.
3. `a` and `b` are unrelated complete objects; [[expr.rel#4.3]] does not require either to compare greater, and [[expr.rel#5]] says the result of `<` is then unspecified. Unspecified is not UB, and the program runs normally. But a relational operation with an unspecified result is not a core constant expression ([[expr.const.core#2.28]]). For a total order across objects, use `std::less<int*>`.
4. `&a[2]` is the past-the-end pointer of `a`, and `&b` points to another complete object. [[expr.eq#4.1]] says the result of an equality comparison in this case is unspecified, because `b` might happen to sit right after `a`. It cannot appear in a constant expression either.

For comparison: `&a[0] != &b` is definitely true and can go in a `static_assert`. When two pointers point to different objects and neither is past-the-end, they compare unequal per [[expr.eq#4.3]].

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="C" markdown="1">

Which line is ill-formed?

```cpp
void test(bool c) {
    int i = 0;
    long l = 0;
    (c ? i : i) = 1;        // A
    (c ? i : throw 0) = 2;  // B
    (c ? i : l) = 3;        // C
    (c, i) = 4;             // D
}
```

- A. Line A
- B. Line B
- C. Line C
- D. Line D

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: C.**

Assignment requires a modifiable lvalue as its left operand ([[expr.assign#1]]), so the question becomes the value category of each expression.

- A: the second and third operands are glvalues of the same type and the same value category, so the result is an lvalue of that type ([[expr.cond#5]]).
- B: when one operand is a *throw-expression*, the result has the type and value category of the other operand ([[expr.cond#2.1]]), here an `int` lvalue.
- C: `int` and `long` are different types and neither is a class type, so the conversion attempt of [[expr.cond#4]] does not apply and [[expr.cond#5]] is not satisfied either; we fall through to [[expr.cond#6]], and the result is a prvalue; the usual arithmetic conversions are then applied per [[expr.cond#7.2]], giving a `long` prvalue. A prvalue cannot be assigned to.
- D: a comma expression has the value category of its right operand ([[expr.comma#1]]), an `int` lvalue. Clang only warns that the left operand has no effect.

The tempting wrong answer is B, on the belief that `throw` makes the whole expression `void` or a prvalue. [[expr.cond#2.1]] exists precisely to preserve lvalueness for code like `c ? x : throw e`.

One more case: if the third operand were a `const int` lvalue, [[expr.cond#4]] would convert `i` to a `const int` lvalue, the result would be a non-modifiable lvalue, and the assignment would also be ill-formed, for a different reason.

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

Judge this program.

```cpp run
int main() {
    int x = 0;
    auto l = [=] { return sizeof(x); };
    decltype(l) m;
    return m();
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: ill-formed.**

1. The operand of `sizeof` is an unevaluated operand ([[expr.sizeof#1]]). [[expr.prim.lambda.capture#7]] captures implicitly only when the expression is potentially evaluated, so `x` is not captured and the closure object has no data members.
2. But whether the closure type has a default constructor depends not on what is captured but only on whether there is a *lambda-capture* syntactically. [[expr.prim.lambda.closure#17]]: the closure type of a lambda with a *lambda-capture* has no default constructor, and its copy assignment operator is deleted. `[=]` is a capture-default and counts as a *lambda-capture*.
3. So `decltype(l) m;` finds no default constructor.

The tempting answer is `ok`, reasoning that nothing is captured, so the closure is as stateless as `[]`. Drop the `=` and it works: since C++20, a closure type without a *lambda-capture* is default-constructible and assignable ([[P0624R2]]).

```cpp run ok
int main() {
    int x = 0;
    auto l = [] { return sizeof(x); };   // x in an unevaluated operand needs no capture
    decltype(l) m;
    m = l;
    return m();
}
```

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

Judge this program.

```cpp run
struct S {
    int a : 4;
    int b;
};

int sum() {
    S s{1, 2};
    auto [x, y] = s;
    return [&] { return x + y; }();
}

int main() { return sum(); }
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: ill-formed.**

1. Since C++20 structured bindings can be captured by lambdas: they are local entities as defined in [[basic.pre#9]] ([[P1091R3]], [[P1381R1]]).
2. `S` is bound by data member. [[dcl.struct.bind#8]]: `x` is an lvalue referring to `e.a`, and `a` is a bit-field, so that lvalue is a bit-field too.
3. `[&]` implicitly captures both `x` and `y` by reference ([[expr.prim.lambda.capture#7]], [[expr.prim.lambda.capture#12]]). The last sentence of [[expr.prim.lambda.capture#12]]: a bit-field shall not be captured by reference.

Clang 23 rejects this code with the note non-const reference cannot bind to bit-field 'a'. Capturing `x` by copy, or capturing only `y` by reference, both work:

```cpp run ok
struct S {
    int a : 4;
    int b;
};

int sum() {
    S s{1, 2};
    auto [x, y] = s;
    return [=] { return x + y; }() + [&y] { return y; }();
}

int main() { return sum(); }   // returns 5
```

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ub" markdown="1">

Judge this program.

```cpp run
struct X {
    int v = 7;
    auto get() { return [=] { return v; }; }
};

int main() {
    auto l = X{}.get();
    return l();
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: undefined behavior.**

1. In a member function, `v` means `this->v`. [[expr.prim.lambda.capture#7]]: an *id-expression* naming a non-static member potentially references `*this`, so `*this` is implicitly captured.
2. Item 10.1 of [[expr.prim.lambda.capture#10]] explicitly excludes `*this` from capture by copy, so it is captured by reference ([[expr.prim.lambda.capture#12]]): the closure stores the `this` pointer, not a copy of `v`. This implicit capture is deprecated ([[depr.capture.this#1]]), but the program is still well-formed.
3. `X{}` is a temporary, destroyed at the end of the full-expression ([[class.temporary#4]]). Afterward `l()` accesses `v` through the dangling `this`, which is UB per item 7.2 of [[basic.life#7]].

The tempting answer is `ok`, assuming `[=]` copied `v`. Clang gives the warning implicit capture of 'this' with a capture default of '=' is deprecated, and ASan reports stack-use-after-scope.

Capturing the whole object by value (C++17) or copying just the member both make it defined:

```cpp run ok
struct X {
    int v = 7;
    auto get() { return [*this] { return v; }; }
};

int main() {
    auto l = X{}.get();
    return l();   // returns 7
}
```

For the full treatment of lambda captures see [[topics/lambdas]].

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="B" markdown="1">

What does this program print?

```cpp run
#include <cstdio>
#include <tuple>

int main() {
    int i = 2;
    std::tuple<int, int&> t{1, i};
    auto [a, b] = t;
    a = 10;
    b = 20;
    std::printf("%d %d\n", std::get<0>(t), i);
}
```

- A. `10 20`
- B. `1 20`
- C. `1 2`
- D. `10 2`

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: B; it prints `1 20`.**

1. With no ref-qualifier, [[dcl.struct.bind#1]] introduces a hidden variable `e` as if by `auto e = t;`. `e` is a copy of `t` and still has type `std::tuple<int, int&>`: its first element is a new `int`, and its second element still refers to `i`.
2. `std::tuple` is a tuple-like type, handled per [[dcl.struct.bind#7]]. `e` is not an lvalue reference, so it is passed to `get` as an xvalue.
    - Element 0: T₀ is `int`, `get<0>` returns `int&&`, and an `int&& r0` bound to the first element of `e` is introduced. `a` refers to that object, so `a = 10` modifies `e`, not `t`.
    - Element 1: T₁ is `int&`, `get<1>` returns `int&`, an lvalue, and an `int& r1` bound to `i` is introduced. `b = 20` modifies `i` itself.
3. So `std::get<0>(t)` is still 1, and `i` becomes 20.

A is wrong because it assumes the structured bindings bind directly to `t`; that would need `auto& [a, b] = t;`. C is wrong because it assumes copying severs the reference member from `i`, but copying a reference member yields a reference to the same object.

[[dcl.struct.bind#7]] also says the referenced types of `a` and `b` are T₀ and T₁, so `decltype(a)` is `int` and `decltype(b)` is `int&`.

</details>
</div>

## 4. Constant evaluation and static initialization

<div class="quiz" data-kind="verdict" data-answer="ok" markdown="1">

Judge this program.

```cpp run
#include <cstddef>

template <class T, std::size_t N>
constexpr std::size_t count(const T (&)[N]) { return N; }

void f(const int (&arr)[3]) {
    static_assert(count(arr) == 3);
}

int main() {}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: well-formed.**

1. `arr` is a function parameter; the object it refers to lies outside the constant evaluation and cannot be used in constant expressions. In C++20 and earlier, the mere appearance of such a reference in a constant expression made it non-constant, and this code was rejected.
2. C++23 changed this through [[P2280R4]]. [[expr.const.core#9]]: during constant evaluation, a reference whose lifetime did not begin within the evaluation is treated as bound to an unspecified object whose lifetime spans the entire evaluation.
3. `count` only binds `arr` to its own parameter and returns `N`, deduced from the type; it never reads an element's value, so it does not trigger the lvalue-to-rvalue conversion forbidden by [[expr.const.core#2.10]]. So `count(arr)` is a constant expression.

The standard gives the same pattern in example 7 of [[expr.const.core#9]] (`use_array`). Clang 23 accepts it.

As soon as a value is actually read, it fails. Both places below are rejected: the first performs an lvalue-to-rvalue conversion on an object not usable in constant expressions; the second reads the value of the non-`constexpr` pointer variable `p`.

```cpp error
#include <cstddef>

template <class T, std::size_t N>
constexpr std::size_t count(const T (&)[N]) { return N; }

void f(const int (&arr)[3]) {
    static_assert(arr[0] == 0);       // error: reads arr[0]
}

void g(const int (&arr)[3]) {
    const int (*p)[3] = &arr;
    static_assert(count(*p) == 3);    // error: reads p
}
```

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="impl" markdown="1">

Judge this program.

```cpp run
constexpr int f(int x) {
    [[assume(x > 0)]];
    return x;
}

constexpr int v = f(-1);

int main() { return v; }
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: implementation-defined behavior. Whether the program is well-formed is up to the implementation.**

1. [[dcl.attr.assume#1]]: if the assumed expression would not evaluate to true, evaluating the assumption has runtime-undefined behavior.
2. [[intro.defs]] defines the term: outside constant evaluation it is undefined behavior; during constant evaluation, whether the expression is thereby considered non-constant is implementation-defined, and it has no other effect.
3. [[expr.const.core#3]] says the same thing: if an expression satisfies the constraints of a core constant expression but its evaluation has runtime-undefined behavior, it is implementation-defined whether it is a core constant expression.
4. If the implementation considers `f(-1)` not a constant expression, `v` cannot be constant-initialized and is ill-formed per [[dcl.constexpr#6]]; if it does consider it constant, `v` has the value -1 and the program is well-formed.

Clang 23 chooses the former and reports assumption evaluated to false. Choosing `error` because the compiler reports an error ignores the other, equally conforming, implementation.

Constant evaluation treats three kinds of undefined operations differently:

| Source of the undefined operation | Core constant expression? | Clause |
|---|---|---|
| UB in the language clauses (4 through 15), such as `x / 0` | never; must be diagnosed | [[expr.const.core#2.8]] |
| runtime-undefined behavior, such as a failed assumption | implementation-defined | [[expr.const.core#3]] |
| UB specified in the library clauses | unspecified | [[expr.const.core#4]] |

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="B" markdown="1">

Which of the four function definitions labeled A through D makes the program ill-formed?

```cpp
consteval int id(int x) { return x; }

template <class T>
constexpr int a(T t) { return id(t); }            // A
static_assert(a(3) == 3);

constexpr int b(int t) { return id(t); }          // B

auto c = [](int t) { return id(t); };             // C
static_assert(c(3) == 3);

constexpr int d(int t) {                          // D
    if consteval { return id(t); }
    return t;
}
```

- A. `a`
- B. `b`
- C. `c`
- D. `d`

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: B.**

1. In all four, the argument of `id(t)` is a function parameter whose value is unknown, so `id(t)` is not a constant expression.
2. An `id(t)` not in an immediate function context is an immediate invocation ([[expr.const.imm#1]]). An immediate invocation that is not a constant expression is an immediate-escalating expression (item 2.2 of [[expr.const.imm#2]]).
3. The last sentence of [[expr.const.imm#3]]: an immediate-escalating expression shall appear only in an immediate-escalating function. There are three kinds of immediate-escalating function: the call operator of a lambda not declared `consteval`, a defaulted function that is not user-provided, and a function instantiated from a templated entity declared `constexpr`. An immediate-escalating function containing such an expression becomes an immediate function itself (item 4.2 of [[expr.const.imm#4]]).

Item by item:

- A: `a<int>` is instantiated from a function template, so it is an immediate-escalating function and escalates to an immediate function. The condition of `static_assert` is manifestly constant-evaluated and is in an immediate function context, so `a(3)` is fine.
- B: `b` is an ordinary non-template `constexpr` function, not an immediate-escalating function, so `id(t)` appearing in it is ill-formed. Clang reports call to consteval function 'id' is not a constant expression.
- C: the lambda's call operator is an immediate-escalating function and escalates to an immediate function; `c(3)` in the `static_assert` is constant.
- D: the compound statement of `if consteval` is an immediate function context (item 1.3 of [[expr.const.imm#1]]), so the `id(t)` in it is not an immediate invocation. `d` remains an ordinary `constexpr` function that can also be called at run time.

These immediate-escalation rules come from C++23's [[P2564R3]]. Escalation propagates outward along the call chain: in A, if `main` contained `int n = 1; a(n);`, then `a<int>` is already an immediate function, `a(n)` is an immediate invocation that is not a constant expression, and `main` is not an immediate-escalating function, so the error is reported at the call. Clang's note is 'a<int>' is an immediate function because its body contains a call to a consteval function 'id' and that call is not a constant expression.

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

Judge this program.

```cpp run
#include <cstddef>
#include <vector>

constexpr std::size_t n = std::vector{1, 2, 3}.size();
constexpr std::vector<int> v{1, 2, 3};

int main() { return n + v.size(); }
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: ill-formed; the problem is `v`.**

1. Dynamic allocation is allowed at compile time, but it must be transient: [[expr.const.core#2.22]] says that a call to `std::allocator<T>::allocate` makes the evaluation E not a core constant expression unless the allocated storage is deallocated within that same evaluation E. `new` expressions have the corresponding [[expr.const.core#2.20]].
2. In the initializer of `n`, the temporary `vector` is destroyed at the end of the full-expression, and the memory it allocated is freed within this evaluation, so `n` is fine.
3. When the initialization of `v` completes, its memory has not been freed; the allocation would have to persist into run time. The initializer is not a constant expression, and a `constexpr` variable must be constant-initializable ([[dcl.constexpr#6]]), so it is ill-formed.

Clang 23's note is pointer to subobject of heap-allocated object is not a constant expression, pointing out that the allocation happened in `allocator.h`.

Compile-time dynamic allocation was introduced by C++20's [[P0784R7]]. It is easy to assume that since all of `std::vector`'s member functions are `constexpr`, a `constexpr std::vector` variable can exist. When a result needs to survive into run time, compute the size at compile time and then copy into a `std::array`. On libc++, an empty `constexpr std::vector<int> v{};` compiles, because default construction does not allocate.

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="A" markdown="1">

What does this program print?

```cpp run
#include <cstdio>
#include <type_traits>

constexpr int f() {
    if constexpr (std::is_constant_evaluated()) return 1;
    else return 2;
}

constexpr int g() {
    if (std::is_constant_evaluated()) return 1;
    return 2;
}

int main() {
    int a = f();
    int b = g();
    const int c = g();
    std::printf("%d %d %d\n", a, b, c);
}
```

- A. `1 2 1`
- B. `1 2 2`
- C. `2 2 1`
- D. `1 1 1`

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: A; it prints `1 2 1`.**

`std::is_constant_evaluated()` is equivalent to `if consteval { return true; } else { return false; }` ([[meta.const.eval#1]]), and `if consteval` takes the first branch only in a manifestly constant-evaluated context ([[stmt.if#5]]). So for each call site we need to decide whether it is manifestly constant-evaluated.

- `a`: the `std::is_constant_evaluated()` in `f` is the condition of `if constexpr`, which is itself manifestly constant-evaluated ([[expr.const.defns#1.2]]) and so always true. `f` is compiled to unconditionally return 1, regardless of the call site. Clang warns on this line: 'std::is_constant_evaluated' will always evaluate to 'true' in a manifestly constant-evaluated expression.
- `b`: `int b` is not `const`, so it is not a potentially-constant variable ([[expr.const.init#6]]) and cannot be used in constant expressions; it has automatic storage duration, so constant initialization does not come into it either ([[basic.start.static#2]] covers only static and thread storage duration). None of the conditions of [[expr.const.defns#1.6]] hold, `g()` is evaluated at run time, and it returns 2.
- `c`: a `const int` is a potentially-constant variable. When deciding whether it can be constant-initialized, `std::is_constant_evaluated()` is taken to be true (note 1 in [[expr.const.init#4]]); `g()` returns 1 and is a constant expression, so `c` is constant-initialized and usable in constant expressions ([[expr.const.init#7]]). Hence its initializer is manifestly constant-evaluated ([[expr.const.defns#1.6]]), and its value is 1.

Example 1 in [[expr.const.defns#1]] has the same contrast: in `const int n = std::is_constant_evaluated() ? 13 : 17;`, `n` is 13, while a non-`const` variable `m` written the same way may be 13 or 17. In our tests both `-O0` and `-O2` print `1 2 1`.

To branch between compile time and run time, write `if consteval` directly since C++23; then you cannot accidentally write `if constexpr`.

</details>
</div>

<div class="quiz" data-kind="open" markdown="1">

The two translation units are linked together. (1) According to the standard, what is the value of `copy`? (2) Give two modifications that make `copy` always `"hello, world"`, and justify them.

```cpp title="a.cpp"
#include <string>

std::string make_greeting() { return "hello, world"; }
std::string greeting = make_greeting();
```

```cpp title="b.cpp"
#include <string>

extern std::string greeting;
std::string copy = greeting;

int main() { return copy.size(); }
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: (1) the order of the two dynamic initializations is unspecified; if `copy` is initialized first, the behavior is undefined. (2) See below: for example, switch to constant initialization, use a function-local static, or use an inline variable in a header.**

(1) Analysis:

1. `make_greeting` is not `constexpr`, so `greeting` cannot be constant-initialized; it is zero-initialized first and then dynamically initialized ([[basic.start.static#2]]). `copy` is dynamically initialized too.
2. Neither is an inline variable or a template specialization, so both have ordered initialization ([[basic.start.dynamic#1]]). But they are in different translation units, so there is no appearance order between them ([[basic.start.dynamic#2]]). If the program starts no other threads, by item 3.3 of [[basic.start.dynamic#3]] the two initializations are indeterminately sequenced. In addition, whether initialization is deferred until after `main` starts is implementation-defined ([[basic.start.dynamic#5]]).
3. If `greeting` is initialized first, `copy` gets `"hello, world"`. If `copy` is initialized first, `std::string`'s copy constructor reads an object whose constructor has not run and whose lifetime has not begun, which is UB per [[basic.life#8]].
4. The implementation executes one of the possible executions ([[intro.abstract#6]]), so the result cannot be relied on. In our tests, linking in the order `a.cpp b.cpp` returns 12, and in the order `b.cpp a.cpp` returns 0.

(2) Fixes; pick any two:

- Switch to constant initialization: for example, declare `constexpr std::string_view greeting = "hello, world";` in a header and change `b.cpp` to direct-initialize `std::string copy(greeting);` (the `std::string` constructor from `string_view` is `explicit`, so the original `= greeting` form does not compile). Constant initialization is static initialization and strongly happens before any dynamic initialization ([[basic.start.static#2]]). To keep a mutable global, write `constinit`: if the initialization is not constant initialization, the program is ill-formed ([[dcl.constinit#2]]), so the problem surfaces at compile time. That requires the initializer to be a constant expression, so `make_greeting()` must become `constexpr`. For `std::string`, whether this works also depends on whether the standard library allocates during constant evaluation: if allocated memory is not freed within the initialization, the initializer is not a constant expression ([[expr.const.core#2.22]]).
- Use a function-local static: `const std::string& greeting() { static const std::string s = make_greeting(); return s; }`. A block-scope static variable is initialized the first time control passes through its declaration ([[stmt.dcl#3]]), so `copy = greeting()` always reads an initialized object.
- Use an inline variable: write `inline std::string greeting = make_greeting();` in a header and include it in `b.cpp` before the definition of `copy`. `greeting` has partially-ordered initialization, and every definition of `copy` is preceded by a definition of `greeting`, so by item 3.1 of [[basic.start.dynamic#3]], in a single-threaded program the initialization of `greeting` comes before that of `copy`. In our tests it returns 12 with both link orders.

This problem is usually called the static initialization order fiasco; for more background see [[basic.start]] and [[topics/initialization]].

</details>
</div>

## Clauses at a glance

| No. | Topic | Clauses |
|---|---|---|
| 1 | Right-before-left in assignment; `i = i++ + 1` | [[intro.execution#10]], [[expr.assign#1]] |
| 2 | Arguments are indeterminately sequenced | [[expr.call#8]], [[intro.execution#8]] |
| 3 | Unsequenced versus indeterminately sequenced | [[intro.execution#10]], [[expr.comma#1]], [[expr.call#8]] |
| 4 | Lexical order in constant evaluation | [[intro.execution#16]], [[expr.const.core#2.8]] |
| 5 | Evaluation order of a chain of compound assignments | [[expr.assign#1]], [[expr.assign#6]] |
| 6 | Integral promotions and the usual arithmetic conversions | [[conv.prom#2]], [[expr.arith.conv#1.5]], [[conv.integral#3]] |
| 7 | Signed overflow after promotion | [[conv.prom#2]], [[expr.pre#4]] |
| 8 | Width limits of shifts and C++20 semantics | [[expr.shift#1]], [[expr.shift#2]], [[expr.shift#3]] |
| 9 | `INT_MIN % -1` | [[expr.mul#4]] |
| 10 | Out-of-range floating-point to unsigned conversion | [[conv.fpint#1]] |
| 11 | The range of an enumeration | [[dcl.enum#8]], [[expr.static.cast#8]] |
| 12 | Arithmetic between different enumerations | [[expr.arith.conv#1.3]] |
| 13 | The signedness of `char` | [[basic.fundamental#7]], [[conv.integral#3]] |
| 14 | Relational and equality comparison of pointers | [[expr.rel#4]], [[expr.rel#5]], [[expr.eq#4]], [[expr.const.core#2.28]] |
| 15 | Value categories of the conditional and comma operators | [[expr.cond#2]], [[expr.cond#5]], [[expr.cond#6]], [[expr.comma#1]] |
| 16 | A closure with a capture-default has no default constructor | [[expr.prim.lambda.closure#17]], [[expr.prim.lambda.capture#7]] |
| 17 | A bit-field structured binding cannot be captured by reference | [[dcl.struct.bind#8]], [[expr.prim.lambda.capture#12]] |
| 18 | `[=]` implicitly captures `this` by reference | [[expr.prim.lambda.capture#10]], [[depr.capture.this#1]], [[basic.life#7]] |
| 19 | What tuple-like structured bindings bind to | [[dcl.struct.bind#1]], [[dcl.struct.bind#7]] |
| 20 | Unknown references in constant evaluation | [[expr.const.core#9]], [[expr.const.core#2.10]] |
| 21 | Runtime-undefined behavior and constant evaluation | [[dcl.attr.assume#1]], [[expr.const.core#3]] |
| 22 | Immediate invocations and immediate-escalating functions | [[expr.const.imm#1]], [[expr.const.imm#2]], [[expr.const.imm#3]], [[expr.const.imm#4]] |
| 23 | Compile-time dynamic allocation must be transient | [[expr.const.core#2.22]], [[dcl.constexpr#6]] |
| 24 | `std::is_constant_evaluated` and manifest constant evaluation | [[expr.const.defns#1]], [[expr.const.init#7]], [[meta.const.eval#1]] |
| 25 | Dynamic initialization order across translation units | [[basic.start.dynamic#3]], [[basic.start.static#2]], [[basic.life#8]] |
