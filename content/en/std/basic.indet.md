---
title: Indeterminate and erroneous values
summary: "What value is in uninitialized storage, and what happens when you read it: since C++26, ordinary local variables hold erroneous values and reading them is erroneous behavior; dynamically allocated memory and variables marked [[indeterminate]] still hold indeterminate values, and reading them is undefined behavior."
updated: 2026-10-19
---

!!! tldr
    - Since C++26, an uninitialized local variable holds an **erroneous value** chosen by the implementation. Reading it is erroneous behavior: the behavior is defined, but the implementation may report it or terminate the program.
    - Memory obtained from `new`/`malloc`, and variables marked `[[indeterminate]]`, hold **indeterminate values**. Reading them is still undefined behavior.
    - Variables with static and thread storage duration are always zero-initialized first and never have either kind of value.
    - `unsigned char` and `std::byte` are an exception: operations that merely move a value, such as initialization and assignment, do not count as reading, so objects with uninitialized parts can be copied byte by byte.
    - An erroneous value can also be invalid for the type (say, some bit pattern for `bool`), in which case reading it is still UB. The right practice remains: always initialize.

## What is in an uninitialized variable (¶1)

```cpp run title="initial-values.cpp" ok
int g;                       // static storage duration: zero-initialized, value 0

void f() {
    int a;                   // automatic storage duration: erroneous value
    int b [[indeterminate]]; // marked [[indeterminate]]: indeterminate value
    int* p = new int;        // dynamic storage duration: *p is an indeterminate value
    static int s;            // static storage duration: 0
    (void)a; (void)b; (void)s;   // discarded-value expressions don't read the value; no erroneous behavior here
    delete p;
}

int main() { f(); return g; }
```

¶1 specifies the initial value of the bytes when storage for an object with automatic or dynamic storage duration is obtained:

- ¶1.1 if the object has dynamic storage duration, or is the object associated with a variable or function parameter whose first declaration is marked `[[indeterminate]]`, the bytes have **indeterminate values**.
- ¶1.2 otherwise, the bytes have **erroneous values**, where each value is determined by the implementation independently of the state of the program. Ordinary local variables, function parameters and temporary objects fall into this category.

If the object (including its subobjects) is not initialized, the bytes keep their initial values until replaced by assignment or initialization.

The value of a whole object is determined bit by bit. If any bit in the value representation (the bits of the object that actually take part in representing the value, see [[basic.types.general]]) has an indeterminate value, the object has an indeterminate value; otherwise, if any bit has an erroneous value, the object has an erroneous value. Indeterminate takes precedence.

Note 2 reminds us that objects with static or thread storage duration are always zero-initialized first ([[basic.start.static]]), so they never have either kind of value.

!!! note "Why dynamically allocated memory still holds indeterminate values"
    Giving `new int` an erroneous value would require the allocator to fill memory on every allocation, which is too expensive. Allocators also reuse memory blocks, so the value could not be independent of program state. C++26 deals only with automatic variables, where the cost is lowest: when the variable is then fully assigned, the compiler can usually eliminate the fill.

## Erroneous behavior and undefined behavior

Reading an indeterminate value is **undefined behavior** (UB): the standard places no requirements on the entire execution, and the optimizer may assume it never happens. Reading an erroneous value is the new C++26 **erroneous behavior** (EB). [[defns.erroneous]] defines it as well-defined behavior that the implementation is recommended to diagnose. [[intro.abstract#6]] further allows the implementation to issue a diagnostic or terminate the program when erroneous behavior is executed.

| | Undefined behavior | Erroneous behavior |
|---|---|---|
| Is the program correct? | no | no |
| After it is executed | no requirements at all, it can even affect earlier behavior | a specified result (here, that erroneous value) is produced and execution continues |
| The implementation may | do anything | diagnose, terminate, or continue |
| Can the optimizer assume it doesn't happen? | yes | no |
| In constant evaluation | makes the expression not a constant expression | likewise not a constant expression ([[expr.const]]) |

C++26 did not simply specify uninitialized variables as 0, for three reasons:

1. If the language guaranteed 0, forgetting to initialize would become legitimately relying on 0, and static analysis and sanitizers could no longer report it as an error. Erroneous behavior is still an error, and tools can keep reporting it.
2. Implementations get a choice: fill with 0 for safety, fill with a pattern like `0xAA` to help debugging, or terminate outright in debug builds.
3. Since reading is no longer UB, compilers cannot use it as a reason to delete code paths. The erroneous value is independent of program state, so data left on the stack (say, a key from a previous call) cannot be read out.

!!! warning "An erroneous value can also be an invalid value"
    Note 1 in ¶1 points out that if the erroneous value is not valid for the object's type, the lvalue-to-rvalue conversion (reading the object's value) is UB ([[conv.lval]]). For example, `bool` has only two valid value representations, 0 and 1; if the implementation chooses the pattern `0xAA`, reading an uninitialized `bool` is UB. For types with invalid bit patterns, erroneous behavior is hardly safer than UB.

## Consequences of reading (¶2)

### The general rule

¶2 specifies that, apart from the exceptions in the next section, if an evaluation produces an indeterminate value the behavior is undefined; if it produces an erroneous value the behavior is erroneous, and the result of the evaluation is that erroneous value. The typical place where a value is produced is the lvalue-to-rvalue conversion, that is, reading a variable's value.

Erroneous values propagate through operations. For a built-in operator producing a prvalue, if an evaluated operand that is not a discarded-value expression produces an erroneous value, the result of the operation is also erroneous. If `x` is erroneous, so is `x + 1`.

```cpp run title="eb-vs-ub.cpp" eb
void use(int) {}

void g() {
    int x;               // erroneous value
    use(x);              // erroneous behavior (UB in C++23)
    int y [[indeterminate]];
    // use(y);           // UB: reads an indeterminate value
    int* p = new int;
    // use(*p);          // UB: dynamic storage duration, indeterminate value
    delete p;
}

int main() { g(); }
```

Clang 23 gives a `-Wuninitialized` warning for `use(x)`, and gives an unknown attribute warning for `[[indeterminate]]` and ignores it (see below).

### The exception for `unsigned char` and `std::byte`

Naive implementations of `memcpy`, serialization and hashing code often copy objects byte by byte, and objects may contain padding bits or uninitialized parts. If copying each such byte were UB or EB, such code could not be written.

So for **unsigned ordinary character types** and `std::byte`, operations that merely move a value are not errors; they just pass the indeterminate or erroneous value along. The standard does not define this term separately; it is usually understood as `unsigned char`, plus `char` on platforms where its underlying type is `unsigned char` ([[basic.fundamental#7]]).

| Item | Indeterminate or erroneous value appears in | Result |
|---|---|---|
| ¶2.1.1 | the second or third operand of a conditional expression | the result of the operation is the same indeterminate or erroneous value |
| ¶2.1.2 | the right operand of a comma expression | same as above |
| ¶2.1.3 | the operand of a conversion to an unsigned ordinary character type or `std::byte` | same as above |
| ¶2.1.4 | a discarded-value expression | same as above |
| ¶2.2 | the right operand of a simple assignment whose left operand is an lvalue of one of these types | the object on the left gets the value |
| ¶2.3 | the initializer of an object of unsigned ordinary character type | that object gets the value |
| ¶2.4 | the initializer of a `std::byte` object | same as above |

As soon as moving turns into using, for example promotion to `int`, arithmetic, or serving as an `if` condition, the general rule applies again. Here is Example 1 from the standard; the comments are ours:

```cpp title="indet-example.cpp"
#include <cassert>
#include <cstring>

int f(bool b) {
    unsigned char* c = new unsigned char;  // *c is an indeterminate value
    unsigned char d = *c;    // OK: ¶2.3, d gets an indeterminate value
    int e = d;               // UB: promotion to int produces an indeterminate value
    return b ? d : 0;        // UB if b is true: the result type is int, so ¶2.1.1 does not apply
}

int g(bool b) {
    unsigned char c;         // erroneous value
    unsigned char d = c;     // no erroneous behavior (¶2.3); d gets the same erroneous value
    assert(c == d);          // holds: both promotions are erroneous behavior
    int e = d;               // erroneous behavior
    return b ? d : 0;        // erroneous behavior if b is true
}

void h() {
    int d1, d2;
    int e1 = d1;             // erroneous behavior
    int e2 = d1;             // erroneous behavior
    assert(e1 == e2);        // holds
    assert(e1 == d1);        // holds; reading d1 is erroneous behavior
    std::memcpy(&d2, &d1, sizeof(int));   // no erroneous behavior; d2 gets the same erroneous value
    assert(e1 == d2);        // holds, erroneous behavior
}
```

This example shows the fundamental difference between the two kinds of value. An erroneous value is a real, stable value: two reads are always equal; it is just an error to use it. An indeterminate value is not guaranteed to be any definite value, and two reads may differ. LLVM's `undef` has this property: after optimization, `x == x` may be false.

## `[[indeterminate]]`: opting out on demand

Sometimes leaving something uninitialized is intentional, for example a large buffer that is about to be filled completely, where filling it first would be pure waste:

```cpp run title="indeterminate-attr.cpp" ok
#include <cstddef>
#include <cstring>

std::size_t fill(unsigned char* p, std::size_t n) {
    std::memset(p, 1, n);
    return n;
}

int main() {
    [[indeterminate]] unsigned char buf[4096];   // the implementation is not asked to fill it
    std::size_t n = fill(buf, sizeof buf);       // filled right away
    return buf[n - 1] == 1 ? 0 : 1;
}
```

[[dcl.attr.indet]] specifies that this attribute can be applied to the definition of a block variable with automatic storage duration, or to a parameter of a function declaration. On a parameter it must appear on the first declaration of the function; if a parameter is marked in its first declaration in one translation unit and not in another, the program is ill-formed, no diagnostic required. A variable marked with it reverts to C++23 semantics: its initial value is indeterminate, and reading an uninitialized part is UB.

Safe by default, with an explicit opt-out where performance requires it; the opt-out points are clearly visible in the code and easy to review.

## Implementation view

!!! impl "How compilers provide erroneous values"
    - The most direct means is automatic variable initialization. GCC and Clang both have `-ftrivial-auto-var-init=zero` and `=pattern`, which fill every automatic variable without an explicit initializer with 0 or a fixed pattern. With `=pattern`, an uninitialized `int` reads as `-1431655766`, i.e. `0xAAAAAAAA`, on Clang 23. Large projects such as browsers and operating system kernels used such options long before C++26; [[P2795R5]] essentially standardizes the practice and gives its behavior a name.
    - Clang's `__attribute__((uninitialized))` exempts a single variable from automatic initialization, and `[[indeterminate]]` is its standardized version. At the time of writing, Clang 23 does not recognize `[[indeterminate]]` yet; it only warns about an unknown attribute and ignores it, so the example above still compiles.
    - For variables that are fully assigned afterward, the optimizer can eliminate the redundant fill at almost no cost; for large arrays and variables whose address escapes, the cost is noticeable, which is exactly what `[[indeterminate]]` is for.
    - `-Wuninitialized` and `-Wmaybe-uninitialized` report at compile time, and MemorySanitizer (`-fsanitize=memory`) at run time. The standard recommends diagnosing erroneous behavior, so these checks can be more aggressive without violating the standard.

## History

!!! history
    - C++11 and earlier: the value of an uninitialized automatic variable was indeterminate and using it was UB, but there were no fine-grained per-byte rules.
    - C++14: defined per-byte rules for indeterminate values and added the `unsigned char` exception, making byte-by-byte copying a valid operation ([[CWG1787]]).
    - C++17: the exception was extended to the newly added `std::byte`.
    - C++26: [[P2795R5]] introduced erroneous values and erroneous behavior; automatic variables hold erroneous values by default, and `[[indeterminate]]` was added; dynamic storage duration keeps indeterminate values.

## Common misconceptions

!!! pitfall "After C++26, uninitialized variables are safe"
    Erroneous behavior is still an error. The implementation may terminate the program; the value is a pattern chosen by the implementation, not necessarily 0; for types with invalid bit patterns such as `bool` and some enumerations, reading can still be UB; and dynamic storage duration is still UB.

!!! pitfall "`unsigned char` can use indeterminate values freely"
    The exception covers only operations that move values: initialization, assignment, conditional and comma expressions, conversion to byte types, and discarded values. `if (c)`, `c + 1` and `printf("%d", c)` all promote it to `int`, which immediately brings back the general rule.

!!! pitfall "Constructors initialize members automatically"
    The user-provided constructor of `struct T { T() {} int x; };` does not initialize `x`. For `T t;` (automatic storage duration), `t.x` is an erroneous value; for `new T`, `->x` is an indeterminate value.

## Questions

!!! question "Question 1"
    In C++26, how does the function below behave?

    ```cpp
    bool flag() {
        bool b;
        return b;
    }
    ```

<details markdown="1">
<summary>Answer</summary>

`b` has automatic storage duration and holds an erroneous value. `return b;` reads `b`: if the erroneous value the implementation chose is valid for `bool` (for example 0), this is erroneous behavior and that value is returned; if it is invalid (for example `0xAA`), it is undefined behavior per [[conv.lval#3]] (note 1 in ¶1). Whether it is EB or UB depends on the value the implementation chose. Either way, the code is wrong.
</details>

!!! question "Question 2"
    Does `unsigned char a; unsigned char b = true ? a : a;` have erroneous behavior? What if `b`'s type is changed to `int`?

<details markdown="1">
<summary>Answer</summary>

In the first case, both branches of the conditional expression are `unsigned char` lvalues and the result type is also `unsigned char`, so ¶2.1.1 applies and the result is an erroneous value; initializing `unsigned char b` with it is covered by ¶2.3. There is no erroneous behavior, and `b` gets the erroneous value.

In the second case, the conditional expression itself still does not trigger erroneous behavior, but initializing an `int` from an `unsigned char` erroneous value requires integral promotion, which is not among the exceptions, so it is erroneous behavior.
</details>

## Summary

| Storage duration or marker | Initial value of uninitialized bytes | Consequence of reading |
|---|---|---|
| static, thread | does not arise: zero-initialized first | none |
| automatic (default) | erroneous value | erroneous behavior {{c++26}} (C++23: UB) |
| automatic, marked `[[indeterminate]]` | indeterminate value | UB |
| dynamic (`new`, `malloc`) | indeterminate value | UB |
| any, moved as `unsigned char`/`std::byte` | passed along as is | no UB, no EB |
| erroneous value invalid for the type (e.g. `bool`) | erroneous value | UB ([[conv.lval]]) |
