---
title: Throwing an exception
summary: "Throwing an exception means initializing an exception object: how its type is determined, which types cannot be thrown, where it lives, when it is destroyed, and why it must be copyable; when an exception counts as uncaught; why throwing again while handling an exception terminates the program; and, since C++26, throwing and catching exceptions in constant evaluation."
updated: 2026-10-19
---

!!! tldr
    - `throw e;` copy-initializes a new **exception object** from `e` according to its static type; `throw;` creates no new object and rethrows the one currently being handled.
    - The way storage for the exception object is allocated is unspecified, and the global `operator new` is not used. It is destroyed only after the last active handler exits other than by rethrowing and the last `std::exception_ptr` referring to it is destroyed.
    - The type of the exception object must be copy-constructible from a `const T` lvalue; per the standard, move-only types cannot be thrown (Clang does not currently check this).
    - From the completion of the exception object's initialization until the handler's parameter is initialized, the exception is uncaught. If a function called by the exception handling mechanism during this window (a destructor during unwinding, the copy constructor of a handler parameter) throws, the program calls `std::terminate`.
    - C++26 allows throwing exceptions in constant evaluation, provided they are caught and destroyed within the same evaluation.

## What is thrown is an object (¶1–¶2)

```cpp run title="throw-types.cpp" ok
#include <cstdio>

struct Overflow { char op; double a, b; };

void f(double x) { throw Overflow{'+', x, 3.45e107}; }

int main() {
    try { throw "Help!"; }                  // the exception object has type const char*
    catch (const char* p) { std::puts(p); }

    try { f(1.2); }
    catch (Overflow& o) { std::printf("%c %g\n", o.op, o.a); }
}
```

¶1 Throwing an exception transfers control to a handler and passes along an object, whose type determines which handlers can catch it. Besides `throw` expressions, a few other places throw exceptions:

| Source | Example | Type thrown |
|---|---|---|
| allocation functions ([[basic.stc.dynamic.allocation]]) | `operator new` fails | a type that a `std::bad_alloc` handler can catch |
| `dynamic_cast` ([[expr.dynamic.cast]]) | a conversion to a reference fails | `std::bad_cast` |
| `typeid` ([[expr.typeid]]) | `typeid(*p)` where `p` is a null pointer to a polymorphic type | `std::bad_typeid` |
| *new-expression* ([[expr.new]]) | an invalid array length | `std::bad_array_new_length` |
| standard library functions | `std::vector::at` out of range | see each function's *Throws:* |

¶2 Control passes to the **nearest** handler with a matching type. Nearest is in terms of execution history: among all try blocks that have been entered and not yet exited, the one entered most recently. The same `throw` can land in different handlers on different call paths:

```cpp run title="nearest.cpp" ok
#include <cstdio>

void thrower() { throw 1; }

void middle() {
    try {
        thrower();                    // the most recently entered try block
    } catch (const char*) {           // type does not match; keep searching outward
        std::puts("middle");
    }
}

int main() {
    try {
        middle();
    } catch (int) {                   // matches
        std::puts("main");
    }
}
```

If none of the entered try blocks has a matching handler, `std::terminate` is called ([[except.handle#8]]).

## The type of the exception object (¶3)

¶3 Throwing an exception initializes an object with dynamic storage duration, called the [[g:exception-object]]. Its type is specified by [[expr.throw#2]]: apply the array-to-pointer and function-to-pointer conversions to the operand, remove top-level cv-qualifiers, and copy-initialize it from the operand. So `const int x = 1; throw x;` throws an `int`, and `throw "abc";` throws a `const char*`.

The type of the exception object comes from the static type of the operand; `throw` does not know which derived-class object a reference is actually bound to:

```cpp run title="rethrow-vs-throw-e.cpp" ok
#include <cstdio>

struct B { virtual const char* who() const { return "B"; } };
struct D : B { const char* who() const override { return "D"; } };

int main() {
    try {
        try { throw D{}; }
        catch (B& b) { throw b; }      // a new exception object of type B: slicing
    } catch (B& b) { std::printf("throw b; -> %s\n", b.who()); }

    try {
        try { throw D{}; }
        catch (B&) { throw; }          // rethrows the original D object
    } catch (B& b) { std::printf("throw;   -> %s\n", b.who()); }
}
```

It prints `throw b; -> B` and `throw;   -> D`. A `throw;` without an operand rethrows the **currently handled exception**, that is, the exception handled by the most recently activated handler that is still active ([[except.handle#10]]). It creates no new object. Executing `throw;` when no exception is being handled calls `std::terminate`.

`throw;` need not be written within the braces of a handler; functions called from a handler can use it too. This lets one function centralize the classification of exceptions:

```cpp run title="dispatcher.cpp" ok
#include <cstdio>
#include <stdexcept>

int to_error_code() {          // may only be called (directly or indirectly) from a handler
    try { throw; }
    catch (const std::invalid_argument&) { return 1; }
    catch (const std::exception&)        { return 2; }
    catch (...)                          { return 3; }
}

int main() {
    try { throw std::invalid_argument("x"); }
    catch (...) { std::printf("%d\n", to_error_code()); }
}
```

¶3 also specifies that if the type of the exception object would be an incomplete type, an abstract class type, or a pointer to an incomplete type other than cv `void`, the program is ill-formed:

```cpp title="bad-exception-types.cpp" error
struct Abs { virtual void f() = 0; };
struct Inc;

void a(Abs& r) { throw r; }     // error: the exception object type is Abs, an abstract class
void b(Inc* p) { throw p; }     // error: pointer to an incomplete type
void c(void* p) { throw p; }    // OK: void* is excepted
```

Pointers to incomplete types are excluded too because a handler can match through a derived-to-base pointer conversion ([[except.handle#3]]), so the implementation must record the class hierarchy in the run-time type information at the throw point, and for an incomplete type that information does not exist yet. `void*` takes no part in such conversions.

## Where it lives and when it is destroyed (¶4)

¶4 The memory for the exception object is allocated in an unspecified way. [[basic.stc.dynamic.allocation]] adds one point: the global allocation function `operator new` is not called for it. If you replace the global `operator new` to count memory, exception objects are not counted. The Itanium C++ ABI allocates them with `__cxa_allocate_exception`, usually via `malloc`, falling back on failure to a reserved emergency buffer, which guarantees that `std::bad_alloc` can still be thrown when memory is exhausted ([[toolchain/exception-implementation]]).

When a handler exits by rethrowing, control passes to another handler for the same exception object. When the exception object is destroyed is decided by two kinds of **potential destruction points**:

- ¶4.1 an active handler exits by any means other than rethrowing, immediately after the destruction of the handler's parameter;
- ¶4.2 a `std::exception_ptr` referring to the exception object is destroyed, before its destructor returns.

Among all potential destruction points there is an unspecified last one, where the exception object is destroyed; all the others happen before it. This is specified because `std::exception_ptr` can make the exception object outlive the handler, or even hand it to another thread:

```cpp run title="exception-ptr-lifetime.cpp" ok
#include <cstdio>
#include <exception>
#include <stdexcept>
#include <thread>

int main() {
    std::exception_ptr p;
    try {
        throw std::runtime_error("from main thread");
    } catch (...) {
        p = std::current_exception();   // now there are two potential destruction points
    }                                   // handler exits: not the last one, the object survives

    std::thread t([p] {                 // another thread holds another copy
        try { std::rethrow_exception(p); }
        catch (const std::exception& e) { std::printf("thread: %s\n", e.what()); }
    });
    t.join();
}                                       // the last exception_ptr is destroyed, and the exception object with it
```

Implementations usually use an atomic reference count, and the moment the count reaches zero is the last destruction point. Note 2 explains that beyond this, exception handling implies no thread synchronization. Note 3 explains that exceptions do not propagate to other threads by themselves; they must first be caught and stored, and then rethrown with library functions ([[propagation]], [[futures]]).

The `exception_ptr` returned by `std::current_exception()` may refer to the current exception itself or to a copy of it, and whether two calls yield the same object is unspecified ([[propagation#9]]). This leaves room for implementations that put exception objects on the stack. libc++abi puts them on the heap and never copies:

```cpp run title="current-exception-same.cpp" unspecified
#include <cstdio>
#include <exception>

int main() {
    std::exception_ptr p1, p2;
    try { throw 42; }
    catch (int& r) {
        p1 = std::current_exception();
        p2 = std::current_exception();
        r = 7;                                  // modifies the exception object itself
    }
    std::printf("p1 == p2: %d\n", p1 == p2);    // unspecified; 1 with libc++abi
    try { std::rethrow_exception(p1); }
    catch (int v) { std::printf("%d\n", v); }   // unspecified whether 7; 7 with libc++abi
}
```

## Exception types must be copyable (¶5)

¶5 Let `T` be the type of the exception object. Copy-initialization of a `T` from an lvalue of type `const T` in a context unrelated to `T` must be well-formed; if `T` is a class type, the selected constructor is odr-used and the destructor is potentially invoked ([[class.dtor]]).

This requirement comes from the freedom to copy described in the previous section: `std::current_exception` and `std::rethrow_exception` may copy the exception object at run time, in library code unrelated to the throw point, so the throw point must ensure the copy constructor exists and is usable. The qualifier "a context unrelated to `T`" means access checking does not borrow the throw point's privileges: in a member function of `T`, `throw *this;` does not count a private copy constructor as usable.

```cpp title="move-only-throw.cpp" error
#include <memory>

struct MoveOnly {
    MoveOnly() = default;
    MoveOnly(MoveOnly&&) = default;      // the copy constructor is implicitly deleted
};

void f() { throw MoveOnly{}; }           // ill-formed per ¶5
void g() { throw std::make_unique<int>(1); }   // likewise
```

!!! impl "Compiler status"
    Clang 23 accepts the code above without a diagnostic, which does not conform to the standard. Throwing a move-only type works at run time with libc++abi, because its `current_exception` never copies. Portable code should not rely on this.

## Uncaught and caught (¶6–¶8)

¶6 An exception is **uncaught** from the completion of the initialization of the exception object until the completion of the activation of some handler (the handler's parameter has been initialized, [[except.handle#9]]). Note 4 points out that it remains uncaught throughout the stack unwinding it causes.

¶7 A rethrown exception is uncaught again from the point of rethrow until it is caught again. ¶8 An exception is considered caught when a handler for it becomes active. After a rethrow, the original handler has not yet exited and is still active, while the exception is again looking for a new handler, so an exception can have active handlers and still be uncaught (Note 6).

`std::uncaught_exceptions()` returns the number of uncaught exceptions in the current thread:

```cpp run title="uncaught-window.cpp" ok
#include <cstdio>
#include <exception>

struct Probe {
    const char* where;
    ~Probe() { std::printf("%-8s uncaught=%d\n", where, std::uncaught_exceptions()); }
};

struct E {
    E() = default;
    E(const E&) { std::printf("copy     uncaught=%d\n", std::uncaught_exceptions()); }
};

int main() {
    try {
        Probe p{"unwind"};        // during unwinding: 1
        throw E{};                // E{} initializes the exception object directly, no copy constructor call
    } catch (E e) {               // copy-initializing the handler parameter: activation incomplete, still 1
        Probe p{"handler"};       // handler active: 0
    }
}
```

Output:

```text
unwind   uncaught=1
copy     uncaught=1
handler  uncaught=0
```

The uncaught window begins when the initialization of the exception object completes. An exception thrown while constructing the exception object (say, an allocation failure in `throw std::string(...)`) is just an ordinary throw; the original `throw` never happened at all.

The typical use of the count is a scope guard: the destructor compares the count at construction with the count at destruction to determine whether it is being destroyed because of stack unwinding, and decides to commit or roll back accordingly.

```cpp run title="scope-guard.cpp" ok
#include <cstdio>
#include <exception>

struct Transaction {
    int on_entry = std::uncaught_exceptions();
    ~Transaction() {
        std::puts(std::uncaught_exceptions() > on_entry ? "rollback" : "commit");
    }
};

struct Inner {
    ~Inner() {
        try { Transaction t; } catch (...) {}   // a transaction started during unwinding: commit
    }
};

int main() {
    { Transaction t; }                               // commit
    try { Transaction t; throw 1; } catch (int) {}   // rollback
    try { Inner i; throw 2; } catch (int) {}         // commit
}
```

Before C++17 there was only `std::uncaught_exception()`, returning `bool`, which returns `true` in the third case, so a transaction started during unwinding would be wrongly rolled back. So C++17 added the counting version, and C++20 removed the old function ([[uncaught.exceptions]]).

## Throwing again while handling: terminate (¶9)

```cpp run title="throw-during-unwind.cpp" ok
#include <cstdio>
#include <cstdlib>
#include <exception>

struct Bomb { ~Bomb() noexcept(false) { throw 2; } };

int main() {
    std::set_terminate([] { std::fputs("terminate\n", stderr); std::abort(); });
    try {
        Bomb b;
        throw 1;          // during unwinding ~Bomb throws 2: std::terminate is called
    } catch (...) {
        std::puts("never reached");
    }
}
```

The program itself is well-formed, and at run time it always ends with `std::terminate`.

¶9 If, while an uncaught exception is being handled, a function directly invoked by the exception handling mechanism exits via an exception, `std::terminate` is called. There are two kinds of such functions: destructors during stack unwinding (Note 7), and the copy constructor used to initialize a handler's parameter. The language has no way to propagate two exceptions at once: a handler can take only one object, and unwinding can only go in one direction, so it terminates outright.

The second kind is more subtle. When a handler catches by value, the mechanism calls the copy constructor to initialize the parameter, and the exception is still uncaught at that point:

```cpp run title="copy-into-handler.cpp" ok
#include <cstdio>
#include <cstdlib>
#include <exception>

struct C {
    C() { }
    C(const C&) {
        if (std::uncaught_exceptions())
            throw 0;      // throws while being copied into the handler parameter
    }
};

int main() {
    std::set_terminate([] { std::fputs("terminate\n", stderr); std::abort(); });
    try {
        throw C();        // if this copy is not elided, std::terminate is called
    } catch (C) { std::puts("caught"); }
}
```

[[class.copy.elision#1]] allows the handler parameter to be treated as an alias for the exception object, eliding this copy. Clang 23 does not elide it, and the program calls `std::terminate`.

The key word is directly. If a destructor does `try { throw ...; } catch (...) {}` internally, the exception is fully handled inside the destructor, the destructor does not exit via an exception, and there is no problem; the `Inner` example above is like this. Constructors called while initializing the exception object itself are not covered either, since the exception has not yet become uncaught at that point.

## Exceptions in constant evaluation {{c++26}}

Before C++26, if a `throw` expression was evaluated during constant evaluation, the whole expression was not a constant expression. C++26 ([[P3068R6]]) relaxed this; [[expr.const.core#2]] now only requires that:

- the exception object, and any copies made by `std::current_exception` or `std::rethrow_exception`, are destroyed within the evaluation, that is, the exception must be caught and fully handled at compile time and cannot leak to run time;
- a `throw;` without an operand can only rethrow an exception constructed within the evaluation.

`std::exception_ptr`, `std::make_exception_ptr`, `std::rethrow_exception` and so on became `constexpr` as well ([[propagation]]).

```cpp title="constexpr-exceptions.cpp"
struct ParseError { int pos; };

constexpr int parse_digit(char c) {
    if (c < '0' || c > '9') throw ParseError{0};
    return c - '0';
}

constexpr int safe_parse(char c) {
    try { return parse_digit(c); }
    catch (ParseError) { return -1; }   // caught and destroyed within the constant evaluation
}

static_assert(safe_parse('7') == 7);
static_assert(safe_parse('x') == -1);   // C++26: OK; C++23: not a constant expression

constexpr int bad = parse_digit('x');   // error: the exception escapes the constant evaluation
```

Clang 23 does not implement this feature yet and rejects the second `static_assert`, so this code carries no verdict. Per the standard, only the last line is an error.

## Common misconceptions

!!! pitfall "Thinking `throw e;` preserves the dynamic type"
    `void report(const std::exception& e) { throw e; }` throws a `std::exception`, not the `std::runtime_error` the caller passed in. To preserve the dynamic type, use `throw;` in a handler, or `std::rethrow_exception(std::current_exception())`.

!!! pitfall "Throwing a pointer to a local object"
    `throw &local;` is valid, but the exception object is just a pointer. After unwinding, the local object it points to has been destroyed; the lifetime of the exception object does not cover what it points to.

## Questions

!!! question "Question 1"
    Does the following program call `std::terminate`?

    ```cpp
    struct S {
        ~S() noexcept(false) {
            if (std::uncaught_exceptions() == 0) throw 1;
        }
    };
    int main() {
        try { S s; } catch (int) {}
    }
    ```

<details markdown="1">
<summary>Answer</summary>

No. `s` is destroyed normally because the scope of the try block is left; there is no uncaught exception, so the `1` thrown by the destructor is an ordinary throw, caught by `catch (int)`. ¶9 concerns only functions directly invoked by the exception handling mechanism while handling an uncaught exception.

The destructor must be written `noexcept(false)`. Otherwise it is implicitly `noexcept` ([[except.spec#8]]), and the search for a handler leaving that function would call `std::terminate` per [[except.handle#7]].
</details>

!!! question "Question 2"
    Does the `throw;` below rethrow `1` or `2.0`?

    ```cpp
    try { throw 1; }
    catch (int) {
        try { throw 2.0; }
        catch (double) { }
        throw;
    }
    ```

<details markdown="1">
<summary>Answer</summary>

It rethrows `1`. `throw;` rethrows the exception handled by the most recently activated handler that is still active ([[except.handle#10]]). `catch (double)` has already exited; the one still active is `catch (int)`. Only if `throw;` is moved into `catch (double)` does it rethrow `2.0`.
</details>

<details class="fine" markdown="1"><summary>Remaining wording</summary>

The copy requirement of ¶5 has been revised several times. Before C++11 it only required the copy constructor to be accessible even if the copy was elided; later, to support copying by `current_exception`, it was changed to require that the constructor selected when treating the operand as an lvalue be usable (CWG1863); the current draft rewrites it as copy-initialization from a `const T` lvalue in an unrelated context.

</details>
