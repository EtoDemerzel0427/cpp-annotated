---
title: Expressions preamble
summary: "How overloaded operators relate to built-in operators; undefined behavior when the mathematical result of an arithmetic expression is not representable (where signed overflow UB comes from); when an implementation may regroup operations; excess floating-point precision."
updated: 2026-10-19
---

!!! tldr
    - Overloaded operators keep the syntax and evaluation order of the built-in operators, but their operand requirements follow the rules for function calls; overloaded `&&` and `||` don't short-circuit.
    - You can't redefine operators for built-in types, but built-in operators take part in overload resolution as candidates.
    - For unary `+`, `-` and add, subtract, multiply, divide and remainder, any mathematical result the type can't represent is UB: signed overflow is UB, unsigned arithmetic is modular and never overflows, and for IEEE floating point only division by zero is UB.
    - Constant evaluation is stricter: finite operands may not produce ∞ or NaN.
    - An implementation may regroup operations only when they are truly associative; floating-point intermediate results may carry excess precision, but casts and assignments must round.

## What an expression is (¶1)

¶1 Note 1 gives the intuitive description: an expression is a sequence of operators and operands that specifies a computation; it can produce a value and can cause side effects. Neither is required: a call to a `void` function has no value, and `1 + 2` has no side effects.

An expression is a syntactic construct; its type and value category are static properties fixed at compile time ([[expr.prop]]). **Evaluation** is the run-time (or constant-evaluation-time) action, which includes value computation and initiating side effects ([[intro.execution]]).

## What overloaded operators obey (¶2)

```cpp run title="seq.cpp" ok
#include <iostream>

int main() {
    int i = 0;
    std::cout << i++ << ' ' << i++ << '\n';  // since C++17, guaranteed to print "0 1"
}
```

¶2 Note 2 explains that operands of class or enumeration type can use overloaded operators, in which case the expression is rewritten as a function call according to [[over.oper]]. After the rewrite, some rules are kept and some are not:

| Aspect | Overloaded operator |
|---|---|
| Syntax (precedence, associativity, number of operands) | Same as the built-in operator |
| Order of evaluation | Same as the built-in operator ([[over.match.oper#2]]) |
| Requirements on operand types and value categories | Determined by the rules for function calls instead, i.e. by the parameter types |
| Relations between operators, such as `++a` being equivalent to `a += 1` | Not guaranteed |

The same order of evaluation is a C++17 change. Before that, once `a << b` was rewritten as `operator<<(a, b)`, which of the two arguments was evaluated first was unspecified, and `std::cout << i++ << i++` was UB. C++17 specifies that the left operand of the built-in `<<` is evaluated before the right operand, and the overloaded version follows the same order, so the example above is guaranteed to print `0 1`.

The same order does not mean the same short-circuit behavior. Overloaded `&&` and `||` are ordinary function calls, and both operands are evaluated:

```cpp run title="no-short-circuit.cpp" ok
#include <cstdio>

struct B { bool v; };
B operator&&(B a, B b) { return {a.v && b.v}; }

B noisy(bool v) { std::puts("evaluated"); return {v}; }

int main() {
    B r = B{false} && noisy(true);   // still prints "evaluated"
    return r.v;
}
```

An example of operand requirements being determined by function calls instead is assignment. The built-in `=` requires its left operand to be a modifiable lvalue ([[expr.assign]]), but a class's `operator=` is an ordinary member function, so `std::string() = "x"` is valid: a member function is called on a prvalue, and the temporary object is materialized ([[conv.rval]]).

## Built-in operators can't be changed, but they take part in overload resolution (¶3)

¶3 [[expr.compound]] describes the effect of operators applied to types for which they have not been overloaded. Operator overloading cannot modify the rules for the **built-in operators**, that is, you can't redefine `+` for two `int`s. The actual guarantee is in [[over.oper]]: an operator function must have at least one parameter of class or enumeration type.

```cpp run error
int operator+(int, int);   // error: needs at least one parameter of class or enumeration type
```

Built-in operators do take part in overload resolution, though. [[over.built]] lists a set of hypothetical built-in candidate functions for each operator, such as `operator+(double, double)`. If an operand of class type can be turned into `double` by a user-defined conversion, a built-in candidate may be selected; in that case the user-defined conversion is applied to the operand first, and then the built-in rules of [[expr.compound]] take over.

```cpp run ok
struct Meters {
    double v;
    operator double() const { return v; }   // non-explicit conversion function
};

double total(Meters a, Meters b) {
    return a + b;    // selects the built-in candidate operator+(double, double);
                     // both operands are first converted by Meters::operator double()
}
```

!!! note
    This is also why giving a class an implicit `operator bool` brings so many surprises: expressions like `a + b` and `a < 1` may become valid through built-in candidates. C++11's `explicit operator bool` only takes effect where an expression is contextually converted to `bool` (the condition of `if`, `!`, `&&` and so on) ([[conv#4]]), which avoids the problem.

## UB in arithmetic expressions (¶4)

```cpp run title="overflow.cpp" ub
#include <climits>
#include <cstdio>

int main(int argc, char**) {
    int big = INT_MAX - 1 + argc;    // INT_MAX when argc == 1
    unsigned u = UINT_MAX;
    u = u + 1;                       // OK: unsigned arithmetic is modular, u == 0
    int bad = big + 1;               // UB: INT_MAX + 1 is not representable
    int q = INT_MIN / -argc;         // UB: 2^31 is not representable (argc == 1)
    std::printf("%u %d %d\n", u, bad, q);
}
```

Run with `-fsanitize=undefined` in our tests, UBSan reports signed integer overflow and "division of -2147483648 by -1 cannot be represented" at the two UB sites. The basis is ¶4.

¶4 first defines an **arithmetic expression** ([[g:arithmetic-expression|arithmetic expression]]): unary `+` and `-` ([[expr.unary.op]]), addition and subtraction ([[expr.add]]), multiplication, division and remainder ([[expr.mul]]), where each operand (possibly after conversions) has arithmetic type. So:

- Pointer arithmetic `p + 1` is not an arithmetic expression; its UB is specified separately by [[expr.add]].
- Shifts `<<` and `>>` are not included; the UB for a negative shift count or a count not less than the width is specified by [[expr.shift]].
- Compound assignment `+=` and increment `++` are not arithmetic expressions themselves, but they are defined in terms of arithmetic expressions (Note 3), so the same rule applies to them.

Then the rule itself:

!!! std
    The behavior of evaluating an arithmetic expression is undefined if the mathematical result is neither in the range of representable values for its type nor a negative infinity, positive infinity, or NaN that is among the values of the type.

That is, if the mathematical result is neither within the type's representable range nor a ±∞ or NaN that the type has, the behavior is undefined. By type:

| Type | Situation | Conclusion |
|---|---|---|
| Signed integer | Mathematical result outside `[min, max]` | {{ub}}; this is signed overflow |
| Unsigned integer | The operation itself is defined modulo 2<sup>N</sup> ([[basic.fundamental#2]]) | The result is always in range; no overflow |
| IEEE 754 floating point | Overflow rounds to ±∞, invalid operations give NaN; these are all values of the type | Only division by zero is UB (Note 4) |
| Non-IEEE floating point | Overflow | {{ub}} |
| Any type | Zero divisor | {{ub}}, specified separately by [[expr.mul#4]] |

!!! ub "Why signed overflow is UB rather than wrapping"
    Since C++20 signed integers must use two's complement representation ([[basic.fundamental]]), but overflow is still UB, and that is deliberate. Compilers can assume `i + 1 > i` is always true, can widen an `int` loop variable to a 64-bit index without emulating 32-bit wraparound, and can do strength reduction and vectorization. Use unsigned types when you need wrapping semantics, and functions such as `std::saturating_add` from `<numeric>` when you need saturation.

### IEEE floating point and constant expressions (Note 4)

Note 4 points out that if the operand types conform to ISO/IEC 60559 (i.e. IEEE 754), division by zero is the only UB case for arithmetic expressions; but some floating-point expressions that are defined at run time are not core constant expressions. [[expr.const.core#2.9]] excludes these three from constant expressions:

- all operands are finite but the result is not finite (overflow to ∞);
- an operand is a signaling NaN;
- no operand is a NaN but the result is a NaN (such as `inf * 0`, `inf - inf`).

In other words, ∞ and NaN can be produced at run time, but compile time can't create them out of nothing; an existing ∞ or quiet NaN can take part in operations and propagate. The following is adapted from Example 1 in the standard, which uses `std::float32_t`; here it uses `double` and assumes it conforms to IEEE binary64:

```cpp
#include <limits>
constexpr double mx  = std::numeric_limits<double>::max();
constexpr double inf = std::numeric_limits<double>::infinity();
constexpr double nan = std::numeric_limits<double>::quiet_NaN();

constexpr double inf2 = inf * 2;   // OK: propagation of ∞
constexpr double nan2 = nan * 2;   // OK: propagation of NaN (Clang rejects it, see below)
constexpr double tiny = std::numeric_limits<double>::min() / mx;  // OK: underflow rounds to 0
constexpr double oflo = mx * 2;    // error: finite operands give a non-finite result (Clang accepts it, see below)
constexpr double udef = inf * 0;   // error: a NaN result with no NaN operand
constexpr double div0 = mx / 0;    // error: division by zero is UB
```

!!! impl "Where Clang differs from the standard"
    Clang 23 differs from the standard in two places on this example: it rejects `nan2`, treating any operation involving a NaN as non-constant, and it accepts `oflo`, allowing constant evaluation to overflow to ∞. `udef` and `div0` are both rejected. This is a gap between newer standard wording and implementations; don't rely on these edge cases when writing compile-time floating-point code.

Note 5 reminds you that the treatment of division by zero, forming a remainder using a zero divisor, and all floating-point exceptions varies among machines, and is sometimes adjustable by a library function, such as the floating-point environment in `<cfenv>`.

## Limits on regrouping operations (¶5)

```cpp run title="assoc.cpp" ok
#include <cstdio>
int main() {
    double a = 1e16, b = -1e16, c = 1.0;
    std::printf("%g %g\n", (a + b) + c, a + (b + c));  // prints "1 0"
}
```

¶5 Note 6 explains that an implementation may regroup operators according to the usual mathematical rules only where the operators really are associative or commutative. The standard's example is `a = a + 32760 + b + 5;`: on a machine where overflow produces an exception and the range of `int` is [-32768, 32767], it must be computed as `((a + 32760) + b) + 5` and cannot be rewritten as `(a + b) + 32765`, because where the original expression doesn't overflow, the rewritten one might. On a machine where overflow produces no exception and the results are reversible, these rewrites are all allowed, because the result is the same. This is the as-if rule ([[intro.abstract]]) at work. Footnote 34 adds that an implementation may never assume that overloaded operators are associative or commutative.

The most practical consequence of this paragraph: floating-point addition is not associative, so in the default mode a compiler can't turn `(a + b) + c` into `a + (b + c)`, and therefore can't auto-vectorize a floating-point sum. GCC's and Clang's `-ffast-math` (specifically its `-fassociative-math` part) is what makes the compiler give up this guarantee.

## Excess floating-point precision (¶6)

¶6 The values of floating-point operands and the results of floating-point expressions may be represented in greater precision and range than required by the type; the types are not changed thereby. This exists for hardware like the x87, whose registers are 80-bit extended precision: `float` arithmetic can be done in 80-bit registers without rounding each intermediate result to `float`.

Footnote 35 adds that casts and assignments must still perform their specified conversion. So when you write `(float)x`, `static_cast<double>(e)`, or assign to a variable, the extra precision must be dropped, and programmers can use this to force rounding.

!!! impl "From the implementation side"
    - Modern x86-64 does scalar floating-point arithmetic with SSE2 by default, `FLT_EVAL_METHOD` is 0, and there is essentially no excess precision; 32-bit x86 using the x87 usually has `FLT_EVAL_METHOD` of 2.
    - On the x87, GCC by default doesn't strictly follow the requirement to drop excess precision on assignment; it needs `-ffloat-store` or `-fexcess-precision=standard`.
    - Fusing `a * b + c` into a single FMA instruction (floating-point contraction) is usually also regarded as using this latitude; Clang controls it with `-ffp-contract=`.

## History

!!! history
    - The old wording was: if during the evaluation of an expression the result is not mathematically defined or not in the range of representable values for its type, the behavior is undefined. That sentence applied to all expressions, was broad in scope, and didn't make the status of floating-point ∞ and NaN clear. The current draft restricts it to arithmetic expressions and explicitly allows ±∞ and NaN; at the same time [[expr.const.core]] added the rule that non-finite results are not constant expressions.
    - C++17's [[P0145R3]] refined the order of evaluation and specified that overloaded operators follow the order of the corresponding built-in operator, giving `std::cout << i++ << i++` a definite result.
    - C++20 requires two's complement representation for signed integers ([[P1236R1]]), but overflow is still UB.

## Common misconceptions

!!! pitfall "Using only unsigned types means no overflow"
    In `unsigned short a = 65535, b = 65535; auto c = a * b;`, both operands are first converted to `int` by integral promotion ([[conv.prom]]), and the product 4294836225 is outside the range of a 32-bit `int`. That is signed overflow and UB, even though not a single signed type appears in the source. In our tests UBSan reports "65535 * 65535 cannot be represented in type 'int'". Writing `1u * a * b` is safe.

!!! pitfall "Add first, then check for overflow"
    For a signed `x`, `if (x + 1 < x) handle_overflow();` is useless. The overflow itself is UB, so the compiler may assume it doesn't happen and fold the condition to `false`. Compare first, e.g. `if (x == INT_MAX)`, or use `__builtin_add_overflow` or `std::saturating_add`.

## Questions

!!! question "Question 1"
    Is `-INT_MIN` UB? What about `0u - 1`?

<details markdown="1">
<summary>Answer</summary>

`-INT_MIN` is UB. Unary `-` is an arithmetic expression (¶4.1), and the mathematical result 2<sup>31</sup> can't be represented by `int`. Incidentally, `-2147483648` is unary minus applied to the literal 2147483648; on platforms with a 32-bit `int` that literal has type `long` or `long long`, so that expression is actually fine.

`0u - 1` is defined. After the usual arithmetic conversions both operands are `unsigned`, unsigned arithmetic is performed modulo 2<sup>N</sup>, and the result is `UINT_MAX`.
</details>

!!! question "Question 2"
    On an implementation whose floating-point types conform to IEEE 754, is `double d = 1e308 * 10;` UB at run time? What about `constexpr double d = 1e308 * 10;`?

<details markdown="1">
<summary>Answer</summary>

It is not UB at run time. The values of an IEEE type include +∞, and the result rounds to +∞; per Note 4, only division by zero is UB.

As `constexpr`, it is ill-formed according to the standard: all operands are finite and the result is not finite, so it is not a core constant expression ([[expr.const.core#2.9]]). Clang 23 actually accepts it; see the implementation note above.
</details>

!!! question "Question 3"
    Why does C++17 guarantee that `std::cout << f() << g();` calls `f` before `g`, while `h(f(), g())` has no such guarantee?

<details markdown="1">
<summary>Answer</summary>

`std::cout << f() << g()` parses as `(std::cout << f()) << g()` and is rewritten as `operator<<(operator<<(std::cout, f()), g())`. C++17 specifies that the left operand of the built-in `<<` is evaluated before the right operand, and [[over.match.oper#2]] requires the operands of an overloaded operator to be evaluated in the order of the built-in operator, so the left operand containing `f()` is evaluated before `g()`.

`h(f(), g())` is an ordinary function call. [[expr.call]] only specifies that the initializations of the parameters are indeterminately sequenced with respect to each other: one definitely comes before the other, but it doesn't say which.
</details>

## Summary

!!! summary
    - Overloaded operators have the same syntax and order of evaluation as the built-in operators, but different operand requirements and no identities between operators; overloaded `&&` and `||` don't short-circuit.
    - Built-in operators can't be redefined, but they take part in overload resolution as candidates from [[over.built]].
    - An arithmetic expression whose mathematical result is not representable is UB: signed overflow is UB, unsigned arithmetic never overflows, and for IEEE floating point only division by zero is UB.
    - Constant evaluation is stricter: finite operands may not produce ∞ or NaN.
    - Operations may be regrouped only when they are truly associative; floating point may carry excess precision, but casts and assignments must round.
