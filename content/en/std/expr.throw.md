---
title: Throwing an exception
summary: "throw is an expression of type void; the exception object takes the static type of the operand and is copy-initialized from it; throw; rethrows the original exception object, and calls std::terminate when no exception is being handled."
updated: 2026-10-19
---

!!! tldr
    - `throw` is an expression of type `void`, so it can appear in one branch of `?:`.
    - `throw e` creates a new exception object whose type is the static type of `e` with top-level cv removed, after arrays and functions decay to pointers. Throwing through a base class reference slices.
    - `throw;` rethrows the currently handled exception, using the original object: no copy, no slicing. To forward an exception unchanged from a handler, write `throw;`.
    - Executing `throw;` when no exception is being handled calls `std::terminate`.
    - Since C++26, an exception may be thrown during constant evaluation, as long as it is caught within the same evaluation.

This subclause covers only the properties of `throw` as an expression: its type, how the exception object is initialized, and what `throw;` does. How exceptions propagate, how handlers are matched and how the stack is unwound are the business of Clause 14, [[except.throw]] and [[except.handle]].

## `throw` is a `void` expression (¶1)

```cpp run title="throw-expression.cpp" ok
#include <stdexcept>
#include <type_traits>

int x = 0;
static_assert(std::is_void_v<decltype(throw 1)>);
static_assert(std::is_same_v<decltype((true ? x : throw 1)), int&>);   // still an lvalue

int checked_div(int a, int b) {
    return b != 0 ? a / b : throw std::domain_error("division by zero");
}

int main() { return checked_div(6, 3) == 2 ? 0 : 1; }
```

¶1 A *throw-expression* is of type `void`. Its evaluation never completes normally: it either transfers control to a handler or calls `std::terminate`, so giving it a value would be meaningless. [[expr.cond#2]] makes a special exception for it: if one side of a conditional operator is a *throw-expression*, the result takes the type and value category of the other side.

```text
throw-expression:
    throw assignment-expression(opt)
```

A *throw-expression* belongs to the *assignment-expression* level ([[expr.assign]]), so `throw a, b` is `(throw a), b`: it throws `a`, and `b` is never evaluated. Only `throw (a, b)` throws `b`.

## The exception object is initialized from the operand (¶2)

¶2 A *throw-expression* with an operand throws an exception. The **exception object** ([[g:exception-object]]) is the object newly created by `throw`, and it is what handlers catch. It is determined in three steps:

1. The array-to-pointer and function-to-pointer conversions are applied to the operand;
2. the type of the exception object is the type of the converted operand with top-level cv-qualifiers removed;
3. the exception object is copy-initialized from the converted operand ([[dcl.init.general]]).

```cpp run title="throw-type.cpp" ok
#include <cstdio>

void fn() {}

int main() {
    try { throw "Help!"; }                       // const char[6] → const char*
    catch (const char* p) { std::puts(p); }

    try { const int c = 1; throw c; }            // top-level const removed: the exception object is an int
    catch (int& e) { std::puts("caught int&"); } // can be caught by non-const reference

    try { throw fn; }                            // function → function pointer
    catch (void (*)()) { std::puts("caught function pointer"); }
}
```

### The type is the static type

The type of the operand means the **static type** ([[g:static-type]]) of the expression, the type seen at compile time, not the actual type of the object at run time. If a derived class object is thrown through a base class reference, the exception object has the base class type and the derived part is sliced off:

```cpp run title="throw-static-type.cpp" ok
#include <cstdio>

struct Base { virtual ~Base() = default; virtual const char* name() const { return "Base"; } };
struct Derived : Base { const char* name() const override { return "Derived"; } };

int main() {
    try {
        Derived d;
        Base& r = d;
        throw r;                       // the exception object has type Base: slicing
    } catch (Base& e) {
        std::puts(e.name());           // prints Base
    }
}
```

To throw the complete derived object through a base class interface, the usual approach is to declare a virtual function `virtual void raise() const { throw *this; }` in the base class and override it in every derived class, so that the static type of `*this` is the derived class. Many such needs can now be met with `std::exception_ptr` ([[propagation]]).

### Copy, move and elision

Copy-initialization follows the general initialization rules:

- When the operand is a prvalue (such as `throw MyError(...)`), since C++17 it is constructed directly in the exception object's storage, with no copy or move.
- When the operand names a local variable whose scope does not extend beyond the innermost enclosing `try` block, it is an **implicitly movable entity** ([[g:implicitly-movable-entity]]), and a move is tried first. [[class.copy.elision#1.2]] also allows that move to be omitted entirely.
- Otherwise it is copied.

```cpp run title="throw-move.cpp" ok
#include <string>
#include <cstdio>

struct Err {
    std::string msg;
    Err(std::string m) : msg(std::move(m)) {}
    Err(const Err& o) : msg(o.msg) { std::puts("copy"); }
    Err(Err&& o) noexcept : msg(std::move(o.msg)) { std::puts("move"); }
};

int main() {
    try {
        Err e("boom");
        throw e;                 // prints move (or it is elided and prints nothing)
    } catch (const Err&) {}
}
```

### Requirements on the exception type

[[except.throw]] places two more compile-time requirements on the type `T` of the exception object:

- `T` cannot be an incomplete type, an abstract class, or a pointer to an incomplete type other than `cv void` ([[except.throw#3]]).
- Copy-initializing a `T` from a `const T` lvalue must be well-formed ([[except.throw#5]]), even if this particular `throw` moves. The exception object may be copied by `std::current_exception`, and the implementation needs a usable copy constructor.

```cpp title="throw-requirements.cpp" error
struct Incomplete;
struct Abstract { virtual void f() = 0; };

void f(Incomplete* p, Abstract& a) {
    throw p;          // error: pointer to an incomplete type
    throw a;          // error: the exception object type Abstract is an abstract class
}
```

!!! warning "Compiler status: move-only exception types"
    Under [[except.throw#5]] in the current draft, `throw std::make_unique<int>(1);` is ill-formed, because a `std::unique_ptr` cannot be copied from a `const` lvalue. Clang 23 still accepts it. Portable code should not throw move-only objects.

## `throw;` rethrows the original object (¶3)

```cpp run title="rethrow.cpp" ok
#include <cstdio>

struct Base { virtual ~Base() = default; virtual const char* name() const { return "Base"; } };
struct Derived : Base { const char* name() const override { return "Derived"; } };

int main() {
    try {
        try { throw Derived{}; }
        catch (Base& e) { throw e; }   // new exception object of type Base: slicing
    } catch (Base& e) { std::puts(e.name()); }      // Base

    try {
        try { throw Derived{}; }
        catch (Base&) { throw; }       // the original object, dynamic type still Derived
    } catch (Base& e) { std::puts(e.name()); }      // Derived
}
```

¶3 A *throw-expression* with no operand [[g:rethrow|rethrows]] the **currently handled exception** ([[g:currently-handled-exception]]), i.e. the exception caught by the most recently entered handler that has not yet exited ([[except.handle#10]]).

- If no exception is being handled, `std::terminate` is called ([[except.terminate]]).
- Otherwise the exception is reactivated with the existing exception object, and no new object is created; the exception is no longer considered to be caught.

So to forward an exception unchanged from a handler, write `throw;`. `throw e;` creates a new exception object according to the static type of `e`, which may slice and costs an extra copy.

The currently handled exception is not limited to code syntactically inside a `catch` block. `throw;` in a function called from a `catch` block works just as well, and the common exception-dispatching functions are built on this:

```cpp run title="rethrow-terminate.cpp" ok
#include <exception>
#include <cstdio>

void handle_current() {      // may only be called (directly or indirectly) from a catch block
    try { throw; }           // rethrows the currently handled exception
    catch (int i) { std::printf("int %d\n", i); }
    catch (...)   { std::puts("other"); }
}

int main() {
    try { throw 42; } catch (...) { handle_current(); }   // prints int 42
    // handle_current();     // called here: no exception being handled → std::terminate
}
```

Calling `std::terminate` when no exception is being handled is defined behavior, not UB: the program terminates in an implementation-defined way, by default by calling `std::abort`.

## Exceptions in constant evaluation {{c++26}}

In C++23 and earlier, evaluating any *throw-expression* during constant evaluation made the expression not a constant expression, so `throw` could only be placed in branches that were not evaluated. C++26's [[P3068]] relaxed this restriction: an exception object may be constructed as long as it, and all copies produced by `std::current_exception` and the like, are destroyed within the same constant evaluation ([[expr.const.core#2.24]]). `throw;` rethrowing an exception constructed within the current evaluation is also allowed ([[expr.const.core#2.25]]).

```cpp title="throw-constexpr.cpp"
struct NotDigit { char c; };

constexpr int parse_digit(char c) {
    if (c < '0' || c > '9') throw NotDigit{c};
    return c - '0';
}

constexpr int safe_parse(char c) {
    try { return parse_digit(c); }
    catch (const NotDigit&) { return -1; }   // caught during constant evaluation
}

static_assert(safe_parse('7') == 7);
static_assert(safe_parse('x') == -1);   // OK since C++26
```

!!! warning "Compiler status"
    Clang 23 doesn't implement [[P3068]] yet and rejects the second `static_assert` above, which is why the example carries no verdict label. By the standard it is well-formed.

An exception that escapes constant evaluation still makes the expression non-constant. An exception not caught at compile time is a compile error, so `throw` can serve as a compile-time assertion.

## Implementation view

!!! impl
    - Itanium C++ ABI (used by GCC and Clang on Linux and macOS): `throw x` first calls `__cxa_allocate_exception` to allocate storage (usually on the heap, falling back to an emergency buffer reserved by the runtime on failure), constructs the exception object there, and then calls `__cxa_throw` to start the table-driven two-phase stack unwinding: first find a handler, then clean up frame by frame. `throw;` compiles to `__cxa_rethrow()`, which calls `std::terminate` when there is no caught exception.
    - MSVC compiles `throw` to `_CxxThrowException`, implemented on top of SEH.
    - Neither ABI has run-time overhead when no exception is thrown; the cost is that throwing requires table lookups and unwinding, which is slow, and the binary carries unwind tables.
    - Code after a `throw` is unreachable, and compilers can optimize on that basis, similar to a call to a `[[noreturn]]` function.

## Common misconceptions

!!! pitfall "Forwarding with `throw e;` in a catch"
    This creates a new exception object whose type is the static type of `e`, which may slice and costs an extra copy. Write `throw;`.

!!! pitfall "Throwing a pointer to a local object"
    The exception object is only a copy of the pointer, and the local object it points to has already been destroyed during stack unwinding. Throw by value, catch by reference.

## Questions

!!! question "Question"
    What does the following program print?

    ```cpp
    try {
        try { throw 1; }
        catch (int& i) { i = 2; throw; }
    } catch (int i) { std::printf("%d\n", i); }
    ```

<details markdown="1">
<summary>Answer</summary>

It prints `2`. `catch (int& i)` binds to the exception object itself, so modifying `i` modifies the exception object. `throw;` rethrows the same object (¶3), and the outer handler, catching by value, copies the modified value.

Rewriting the inner part as `throw i;` also prints 2, but by a different mechanism: it copies a new exception object from `i`. If the inner handler catches by value, `catch (int i)`, only the copy is modified, and the outer handler prints `1`.
</details>

## Summary

| Aspect | Rule | Basis |
|---|---|---|
| Type | `void` | ¶1 |
| Exception object type | Static type of the operand after decay, with top-level cv removed | ¶2 |
| Initialization | Copy-initialized from the operand; prvalues constructed directly, local variables tried for a move first | ¶2, [[class.copy.elision]] |
| Type requirements | Complete, not abstract, not a pointer to an incomplete type; copyable from a `const T` lvalue | [[except.throw]] |
| `throw;` | Rethrows the currently handled exception (the same object); `std::terminate` if there is none | ¶3 |
| Constant evaluation | Allowed since C++26, as long as the exception is caught and destroyed within the evaluation | [[expr.const.core]] |
