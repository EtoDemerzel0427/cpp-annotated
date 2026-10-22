---
title: "Iteration statements: while, do, for"
summary: "The execution rules of while, do and for: each iteration of the loop body is a new block scope, while is defined with if plus goto, and for is defined with while; since C++26 trivial infinite loops are no longer undefined behavior."
updated: 2026-10-19
---

!!! tldr
    - The loop body enters and leaves its own block scope once per iteration; local variables in the body are constructed and destroyed once per iteration.
    - `while` is defined by `if` plus `goto`, `for` by `while`, and range-based `for` in turn by `for`; variables declared in a condition are therefore recreated every iteration.
    - The *init-statement* of `for` is executed only once, and its variables are a single object shared by the whole loop; `continue` executes the iteration expression before testing the condition.
    - The parentheses of `do` can only hold an expression, and variables declared in the loop body are not visible in `while (...)`.
    - Since C++26, trivial infinite loops such as `while (true);` and `for (;;) {}` are replaced by repeated calls to `std::this_thread::yield()` and are no longer undefined behavior; an empty loop whose condition is not a constant can still be assumed to terminate.

C++ has four iteration statements: `while`, `do`, `for` and range-based `for`. Range-based `for` is covered in [[stmt.ranged]]. C++26's `template for` looks like a loop, but it is an expansion statement unrolled at compile time, not an iteration statement ([[stmt.expand]]).

The standard treats only `while` as primitive, defining it with `if` plus `goto`, and rewrites every other loop into a `while`. Understand the rewrite of `while`, and you know when objects are constructed and destroyed in every loop.

## Each iteration of the loop body is a new scope [stmt.iter.general]

```cpp run ok
#include <cstdio>
struct Noisy {
    int n;
    Noisy(int n) : n(n) { std::printf("ctor %d\n", n); }
    ~Noisy() { std::printf("dtor %d\n", n); }
};
int main() {
    for (int k = 0; k < 2; ++k) {
        Noisy x{k};
    }   // prints ctor 0, dtor 0, ctor 1, dtor 1
}
```

¶2 The substatement of an iteration statement implicitly defines a block scope, which is entered and exited once per iteration. So `x` is not the same variable assigned again and again, but a new object every iteration, destroyed at the end of that iteration.

If the substatement is a single statement rather than a compound statement, it is treated as if wrapped in a pair of braces (Example 1 in the standard). So a variable declared in the loop body is not visible after the loop:

```cpp error
void f(int x) {
    while (--x >= 0)
        int i = x;   // equivalent to { int i = x; }
    i = 0;           // error: i is not in scope
}
```

¶1 lists four syntactic forms:

```text
while ( condition ) statement
do statement while ( expression ) ;
for ( init-statement condition(opt) ; expression(opt) ) statement
for ( init-statement(opt) for-range-declaration : for-range-initializer ) statement
```

The parentheses of `while` and `for` hold a *condition*, which can be a declaration ([[stmt.pre]]); the parentheses of `do` can only hold an *expression*. The *init-statement* ends with its own semicolon, so the first semicolon in `for (;;)` is an empty expression statement.

## while [stmt.while]

¶1 `while` tests the condition before each execution of the loop body, until the condition is `false`.

¶2 `while ( condition ) statement` is equivalent to

```text
label :
{
    if ( condition ) {
        statement
        goto label ;
    }
}
```

This rewrite determines how long a variable declared in the condition lives. It belongs to the scope of the `if`; it is destroyed when `goto label` leaves that scope ([[stmt.dcl#2]]), and created again when control returns to `label` and the condition is re-evaluated:

```cpp run ok
#include <cstdio>
struct A {
    int val;
    A(int i) : val(i) { std::printf("A(%d)\n", i); }
    ~A() { std::printf("~A(%d)\n", val); }
    explicit operator bool() const { return val != 0; }
};
int main() {
    int i = 1;
    while (A a = i) {
        std::printf("body %d\n", a.val);
        i = 0;
    }
}
```

```text
A(1)
body 1
~A(1)
A(0)
~A(0)
```

The condition succeeds once and fails once, with two constructions and two destructions, which is exactly the example in Note 1 to ¶2. On the failing iteration, `a` is destroyed on leaving the `while`.

A `continue` in a `while` jumps to the end of the loop body ([[stmt.cont]]), that is, just before `goto label;` in the rewrite, so the next step is to test the condition again.

## do [stmt.do]

¶2 `do` tests after each execution of the loop body, so the body is executed at least once. ¶1 The expression in the parentheses is contextually converted to `bool`; if that conversion is ill-formed, the program is ill-formed.

`do` is not defined by a rewrite into `while`, and its parentheses cannot hold a declaration. The loop body is a block scope that ends at its `}`, so variables in the body are not visible in the condition:

<div class="compare" markdown="1">

```cpp error
int read();
void f() {
    do {
        int x = read();
    } while (x != 0);  // error
}
```

```cpp ok
int read();
void f() {
    int x;
    do {
        x = read();
    } while (x != 0);  // OK
}
```

</div>

`do { ... } while (0)` is a common idiom for macros: it wraps several statements into one statement that must end with a semicolon, so the macro still works when placed in `if (c) MACRO(); else ...`.

## for [stmt.for]

### Equivalence to while, with two exceptions

¶1 `for ( init-statement condition(opt) ; expression(opt) ) statement` is equivalent to

```text
{
    init-statement
    while ( condition ) {
        statement
        expression ;
    }
}
```

with two exceptions. First, the *init-statement* and the condition are in the same scope. Second, a `continue` in the loop body (not inside an inner loop) executes *expression* before re-evaluating the condition. Under the literal rewrite, `continue` would jump to the end of the `while` body, that is, after `expression ;`, skipping the increment, which is clearly not what is wanted.

```cpp run ok
int main() {
    int c = 0;
    for (int k = 0; k < 5; ++k) {
        if (k % 2) continue;   // ++k is still executed afterwards
        ++c;
    }
    return c == 3 ? 0 : 1;     // k = 0, 2, 4
}
```

¶2 Either or both of the condition and the iteration expression can be omitted. An omitted condition makes the implied `while` equivalent to `while (true)`.

### Scope and object lifetime

A name declared in the *init-statement* has the whole `for` statement as its scope, is in the same scope as names in the condition, and cannot be redeclared at the outermost level of the loop body ([[basic.scope.block]]):

```cpp error
void f() {
    for (int i = 0; i < 3; ++i) {
        int i = 5;              // error: conflicts with the outer i
    }
    for (int i = 0; int i = 1; ) { }  // error: same scope
}
```

A variable declared in the condition is recreated every iteration, as with `while`:

```cpp run ok
int main() {
    int s = 0;
    for (int k = 0; int j = 3 - k; ++k)   // j is 3, 2, 1, 0 in turn
        s += j;
    return s == 6 ? 0 : 1;
}
```

Variables in the *init-statement* are created only once, and the whole loop shares one object. Some languages (Go since 1.22, for example) give the loop variable a new object each iteration; C++ does not. This matters for lambda captures:

```cpp run ok
#include <functional>
#include <vector>
int main() {
    std::vector<std::function<int()>> fs;
    for (int i = 0; i < 3; ++i)
        fs.push_back([i] { return i; });   // captured by value: 0, 1, 2
    return fs[2]() == 2 ? 0 : 1;
}
```

Written as `[&i]`, all three lambdas would refer to the same `i`, and since `i` is destroyed when the loop ends, calling them would use a dangling reference.

The *init-statement* is one simple declaration with a single set of decl-specifiers, so `for (int i = 0, double d = 0; ...)` is a syntax error. Variables of different types can use a structured binding:

```cpp ok
#include <tuple>
void f(const int* a, int n) {
    for (int i = 0, *p = nullptr; i < n; ++i) { (void)p; }
    for (auto [i, p] = std::tuple{0, a}; i < n; ++i, ++p) { (void)*p; }
}
```

The first line works because `int` and `int*` share the decl-specifier `int`; the `*` belongs to the declarator.

## Trivial infinite loops {{c++26}}

### The problem: empty loops can be deleted

```cpp
void halt() { while (true) ; }
int  wait(int x) { while (x) ; return 1; }
```

Compiled with Clang 23 at `-O2`, `halt` becomes a real infinite loop, but `wait` is compiled to return 1 directly; the loop disappears entirely.

The reason is the **forward progress guarantee** ([[intro.progress#1]]): the implementation may assume that every thread eventually does one of the following: terminate, call `std::this_thread::yield`, call a library I/O function, access a volatile object, or perform an atomic or synchronization operation. A loop that neither terminates nor does any of these is undefined behavior, and the compiler may assume it does not exist. This lets compilers delete empty loops they cannot prove to terminate, such as a loop that walks a linked list looking for a node and does nothing else, without first proving the list finite.

The cost is that a deliberately written infinite loop such as `while (true) ;` also became undefined behavior. Embedded programs commonly spin in place after an error, waiting for a watchdog reset. C has excluded loops whose controlling expression is a constant from this assumption since C11, and C++26 followed with [[P2809R3]].

### The rule

¶3 A [[g:trivially-empty-iteration-statement|trivially empty iteration statement]] is one of the following six forms with an empty loop body:

| List item | Form |
|---|---|
| ¶3.1, ¶3.2 | `while ( expression ) ;`, `while ( expression ) { }` |
| ¶3.3, ¶3.4 | `do ; while ( expression ) ;`, `do { } while ( expression ) ;` |
| ¶3.5, ¶3.6 | `for ( init-statement expression(opt) ; ) ;`, `for ( init-statement expression(opt) ; ) { }` |

The condition must be an expression, not a declaration; a `for` may have an *init-statement* but no iteration expression. The expression in the parentheses is called the **controlling expression**; when a `for` omits its condition, the controlling expression is `true`.

If the controlling expression, converted to `bool`, is a constant expression with value `true`, the statement is a [[g:trivial-infinite-loop|trivial infinite loop]]. The loop body of a trivial infinite loop is replaced by a call to `std::this_thread::yield`. Calling `yield` itself satisfies the forward progress guarantee, so such a loop is no longer undefined behavior, and the program really does loop forever. Whether this replacement is made in a freestanding implementation (an environment without the full standard library) is implementation-defined.

```cpp ok
constexpr bool forever = true;
[[noreturn]] void halt1() { while (true) ; }           // ¶3.1
[[noreturn]] void halt2() { for (;;) { } }             // ¶3.6, controlling expression taken as true
[[noreturn]] void halt3() { do { } while (forever); }  // ¶3.4
```

None of the following is a trivial infinite loop; they remain subject to the forward progress guarantee: if they really never terminate and do nothing observable, the behavior is undefined.

```cpp
int flag;
void spin1() { while (flag) ; }            // the controlling expression is not a constant
void spin2() { for (int i = 0; ; ++i) ; }  // has an iteration expression
void spin3() { while (true) { int x = 0; (void)x; } }  // the loop body is not empty
```

!!! warning "`while (flag) ;` cannot be used to wait for another thread"
    Another thread writing `flag` while this one reads it is itself a data race, that is, undefined behavior. The compiler may also hoist the read out of the loop and then, by the forward progress guarantee, assume the loop terminates. To wait for another thread, make `flag` a `std::atomic<bool>` (atomic operations satisfy the forward progress guarantee), or use a condition variable.

## Implementation view

!!! impl "Destruction of loop body variables"
    The loop body entering and leaving its scope each iteration means that at the end of every iteration, and at `continue` and `break`, the local variables already constructed in the body must be destroyed. For trivially destructible types there is no cost; for types like `std::string`, hoisting the variable out of the loop to reuse its buffer is a common optimization, and what it changes is exactly the semantics ¶2 specifies.

!!! impl "The for scope of old MSVC"
    Before C++98, the scope of `i` in `for (int i = ...)` extended past the loop. Old versions of MSVC kept this behavior for a long time, with `/Zc:forScope` switching to the standard behavior.

## Questions

!!! question "1. Which of the following are trivial infinite loops?"
    ```cpp
    for (int i = 0; true; ) ;            // (a)
    while (1) {}                         // (b)
    do ; while (sizeof(int));            // (c)
    for (;;) { ; }                       // (d)
    while (bool b = true) ;              // (e)
    ```

<details markdown="1">
<summary>Answer</summary>

- (a) Yes: form ¶3.5, with an *init-statement*, no iteration expression, and the condition `true`.
- (b) Yes: `1` converted to `bool` is the constant `true`.
- (c) Yes: `sizeof(int)` is nonzero and converts to `true`.
- (d) No: the loop body `{ ; }` is neither `;` nor `{ }`. It is still an infinite loop without side effects, and therefore undefined behavior.
- (e) No: the condition is a declaration, not an expression.
</details>

!!! question "2. In the loop below, how many times is `S` constructed and destroyed?"
    ```cpp
    struct S { S(int); ~S(); explicit operator bool() const; };
    for (int i = 0; S s = i; ++i) { }   // assume S(3) converts to false and the others to true
    ```

<details markdown="1">
<summary>Answer</summary>

4 times each. By [[stmt.for#1]] it is rewritten as `while (S s = i)`, and by [[stmt.while#2]] into an `if` with a `goto`. `s` is constructed once each for `i` equal to 0, 1, 2 and 3, and destroyed each time on leaving the scope of the `if`; the last time the condition is false, and `s` is destroyed on leaving the loop.
</details>

## Summary

| Statement | When tested | In the parentheses | Key points |
|---|---|---|---|
| `while (c) s` | before each iteration | *condition* | equivalent to `L: { if (c) { s; goto L; } }`; the condition variable is recreated each iteration |
| `do s while (e);` | after each iteration | *expression* | executed at least once; body variables are not visible in the condition |
| `for (i c; e) s` | before each iteration | *init-statement*, *condition*, *expression* | equivalent to `{ i while (c) { s; e; } }`; i is executed only once; `continue` executes e first |
| All iteration statements | | | each iteration of the loop body is a new block scope |
| Trivial infinite loops {{c++26}} | | constant `true`, empty loop body | the loop body is replaced by `std::this_thread::yield()`; no longer undefined behavior |
