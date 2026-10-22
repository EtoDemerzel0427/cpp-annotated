---
title: Handling an exception
summary: "Which catch clause catches a thrown exception: there are only four ways to match, and the first in order wins; std::terminate is called when no handler is found or when a noexcept function is left; what the currently handled exception is; how the handler's parameter is initialized; and the special rules for function-try-blocks of constructors and destructors."
updated: 2026-10-19
---

!!! tldr
    - Matching catch clauses is not overload resolution: only the same type, an unambiguous public base class, a few pointer conversions and `nullptr_t` are accepted; there are no integral promotions, arithmetic conversions or user-defined conversions.
    - The handlers of a try block are tried in written order, and the first match wins; `catch (...)` must come last.
    - An exception leaving a `noexcept` function, or never finding a handler, calls `std::terminate`; whether the stack is unwound when no handler is found is implementation-defined, and mainstream implementations do not unwind.
    - Catching by value copies from the exception object and slices; catching by reference can modify the exception object, and the modification is visible to `throw;`.
    - In a function-try-block of a constructor or destructor, members cannot be accessed, and flowing off the end of the handler rethrows automatically.

A **handler** is a catch clause: `catch (` *exception-declaration* `)` followed by a compound statement. The *exception-declaration* is the declaration in the parentheses, such as `const std::exception& e`, or `...`. The object created by `throw` is called the [[g:exception-object]] (see [[except.throw]]); this page answers which handler catches it as it propagates outward along the call chain.

## The matching rules (¶3)

```cpp run title="matherr.cpp" ok
#include <cstdio>

class Matherr { public: virtual ~Matherr() = default; };
class Overflow   : public Matherr {};
class Underflow  : public Matherr {};
class Zerodivide : public Matherr {};

void g(int k) {
    if (k == 0) throw Overflow{};
    if (k == 1) throw Underflow{};
    throw Zerodivide{};
}

int main() {
    for (int k = 0; k < 3; ++k) {
        try {
            g(k);
        } catch (const Overflow&) {
            std::puts("Overflow");
        } catch (const Matherr&) {        // catches Underflow and Zerodivide
            std::puts("other Matherr");
        }
    }
}
```

This is an adaptation of Example 1 in the standard, and also the most common usage: exception classes form an inheritance hierarchy, and handlers catch a whole category of exceptions by base class. The original example in the standard catches by value, `catch (Matherr mm)`, which slices derived-class objects down to `Matherr`; in practice, catch by `const&`.

¶3 Let `E` be the type of the exception object. A handler matches it if and only if one of the following four cases holds:

| Item | Handler type | Condition |
|---|---|---|
| ¶3.1 | cv `T` or cv `T&` | `E` and `T` are the same type (ignoring top-level cv) |
| ¶3.2 | cv `T` or cv `T&` | `T` is an unambiguous public base class of `E` |
| ¶3.3 | cv `T` or `const T&`, where `T` is a pointer or pointer-to-member type | `E` is also a pointer or pointer-to-member type that can be converted to `T` by a combination of: a standard pointer conversion not involving private, protected or ambiguous base classes (¶3.3.1); a function pointer conversion that drops `noexcept` (¶3.3.2); a qualification conversion that adds cv (¶3.3.3) |
| ¶3.4 | cv `T` or `const T&`, where `T` is a pointer or pointer-to-member type | `E` is `std::nullptr_t` |

No conversion absent from the table takes part in matching, including integral promotions, arithmetic conversions, `bool` conversions, user-defined conversions, and derived-to-private-base conversions.

### Testing it

Below, a function template tests each case: `test<E, H>` throws an object of type `E` and checks whether `catch (H)` catches it:

```cpp run title="match-matrix.cpp" ok
#include <cstdio>
#include <cstddef>

struct B { virtual ~B() = default; };
struct D : B {};
struct P : private B {};
struct B1 : B {}; struct B2 : B {};
struct Amb : B1, B2 {};    // contains two B subobjects: B is an ambiguous base

template<class E, class H>
const char* test(E e) {
    try { throw e; }
    catch (H) { return "match"; }
    catch (...) { return "no match"; }
}

void fn() noexcept {}
using fp = void (*)();
using nfp = void (*)() noexcept;

int main() {
    std::puts(test<int, long>(1));                 // no match: no arithmetic conversions
    std::puts(test<char, int>('a'));               // no match: no integral promotions
    std::puts(test<int, const int&>(1));           // match: 3.1
    std::puts(test<D, B&>(D{}));                   // match: 3.2
    std::puts(test<P, B&>(P{}));                   // no match: private base
    std::puts(test<Amb, B&>(Amb{}));               // no match: ambiguous base
    std::puts(test<D*, const B*>(nullptr));        // match: 3.3.1 + 3.3.3
    std::puts(test<D*, void*>(nullptr));           // match: 3.3.1
    std::puts(test<int**, const int* const*>(nullptr)); // match: 3.3.3
    std::puts(test<nfp, fp>(fn));                  // match: 3.3.2
    std::puts(test<fp, nfp>(nullptr));             // no match: cannot add noexcept
    std::puts(test<std::nullptr_t, int*>(nullptr)); // match: 3.4
    std::puts(test<int, int*>(0));                 // no match: Note 1
}
```

The output of Clang 23 (libc++abi) agrees with the comments. Some of the lines are explained below.

`throw 1;` is not caught by `catch (long)`, and `throw 'a';` is not caught by `catch (int)`. Matching happens at run time, and the run-time library has only the type information of the exception object (`std::type_info` and the class hierarchy description supplied by the ABI); it cannot perform overload resolution. If arithmetic conversions were allowed, the run-time library would have to implement conversions between every pair of arithmetic types, and also decide which handler to pick when several could convert. C++ chose a simpler model: find, in order, the first handler that matches by type (¶4).

Note 1 points out that `throw 0;` does not match a pointer handler. The literal `0` is a null pointer constant at compile time, but once thrown, the exception object is just an `int`. To be caught by a pointer handler, throw `nullptr` (¶3.4). The result of `throw NULL;` depends on whether `NULL` is defined as `0`, `0L` or `nullptr`, and is not portable.

The base class must be unambiguous and public regardless of access at the throw point. Even if a `P` is thrown inside a member function of `P`, where the conversion from `P` to `B` is accessible, `catch (B&)` does not catch it. Matching looks only at the inheritance relationships of the types themselves.

### Pointer handlers can only be `T` or `const T&`

¶3.1 and ¶3.2 allow any reference, but ¶3.3 and ¶3.4 allow only by value or `const T&`. The reason is that a pointer conversion produces a new pointer value; converting `D*` to `B*`, for example, may adjust the address. The new value can only be copied, or bound to a const reference. If `catch (B*& r)` were allowed to bind to a `D*` exception object, `r = new B;` would write a `B*` into an object of type `D*`.

!!! impl "libc++abi and `B*&`"
    Per the standard, `throw (D*)p;` should not match `catch (B*& r)`: `B*&` is not `const T&`, and `D*` and `B*` are not the same type. libc++abi matches it anyway (add a line `test<D*, B*&>` to the test above to see this). The Itanium ABI records the handler's type with the reference removed in the exception table, so the run time apparently cannot distinguish `catch (B*)` from `catch (B*&)`. This is a nonconformance in the implementation; portable code should not rely on it.

!!! lawyer "Only some conversions work for pointers to members"
    ¶3.3 allows `T` to be a pointer-to-member type, but ¶3.3.1 speaks of standard pointer conversions ([[conv.ptr]]). The conversion of a pointer to member from `int B::*` to `int D::*` belongs to a different subclause, [[conv.mem]]. Read literally, this conversion does not take part in matching, so `throw (int B::*)nullptr;` is not caught by `catch (int D::*)`. Testing shows that it indeed does not match. Pointer-to-member handlers can therefore match only through the same type, qualification conversions, function pointer conversions of pointers to member functions, and `nullptr_t`.

## Tried in written order (¶4–¶5)

¶4 The handlers of a try block are tried in order of appearance, and the first that matches wins, not the best match. Note 2 points out that this makes it possible to write handlers that can never be executed, for example a handler for a derived class placed after a handler for its base class.

¶5 `catch (...)` matches any exception. If present, it must be the last handler of its try block.

<div class="compare" markdown="1">

```cpp ok
struct B {};
struct D : B {};
void f() {
  try {
  } catch (B&) {
  } catch (D&) {  // never reached
  }
}
```

```cpp error
void g() {
  try {
  } catch (...) {
  } catch (int) {  // error
  }
}
```

</div>

The left side is well-formed; Clang 23 only warns `exception of type 'D &' will be caught by earlier handler`. The right side violates ¶5, and Clang reports `catch-all handler must come last`.

In `catch (...)` there is no name for the exception object, but it can be rethrown with `throw;`, or an `exception_ptr` obtained with `std::current_exception()` ([[propagation]]).

!!! warning "MSVC's `/EHa`"
    When MSVC compiles with `/EHa`, `catch (...)` also catches structured exceptions (SEH), such as access violations; the default `/EHsc` does not. This is an MSVC extension unrelated to the standard.

## What types a handler can declare (¶1–¶2)

¶1 An *exception-declaration* shall not denote an incomplete type, an abstract class type, or an rvalue reference type, nor a pointer or reference to an incomplete type, except for pointers to cv `void`.

```cpp title="bad-handlers.cpp" error
struct Abs { virtual void f() = 0; };
struct Inc;

void f() {
    try {} catch (int&&) {}     // error: rvalue reference
    try {} catch (Abs) {}       // error: abstract class, by value
    try {} catch (Inc&) {}      // error: reference to an incomplete type
    try {} catch (Inc*) {}      // error: pointer to an incomplete type
    try {} catch (Abs&) {}      // OK: reference to an abstract class
    try {} catch (void*) {}     // OK: void* is excepted
}
```

Incomplete types are excluded because the run time needs complete type information to determine inheritance relationships. Rvalue references are excluded because the exception object is always an lvalue: after `throw;` other handlers still need it, so resources should not be moved out of it. Use `T&` when the exception object needs to be modified.

¶2 A handler of array or function type is adjusted to the corresponding pointer type, as with function parameters ([[dcl.fct]]). When an array or function is thrown, the exception object is already the decayed pointer ([[expr.throw]]), so the two sides line up:

```cpp run title="array-handler.cpp" ok
#include <cstdio>

void callback() {}

int main() {
    int a[3] = {1, 2, 3};
    try { throw a; }                       // the exception object has type int*
    catch (int x[3]) { std::printf("%d\n", x[1]); }   // adjusted to int*

    try { throw callback; }                // the exception object has type void(*)()
    catch (void f()) { std::puts("function -> pointer"); }
}
```

Conversely, a handler of reference-to-array or reference-to-function type never matches any exception object (Note 1), since an exception object can never be an array or a function.

## When no handler matches (¶6–¶8)

¶6 If no handler of a try block matches, the search continues in a dynamically surrounding try block of the same thread. Dynamically surrounding means a try block earlier in the call chain that has been entered and not yet exited.

¶7 If the search exits the function body of a function with a non-throwing exception specification ([[except.spec]], such as `noexcept`), `std::terminate` is called. Note 3 and Example 2 stress that an implementation shall not reject an expression merely because it might throw from a `noexcept` function:

```cpp run title="noexcept-boundary.cpp" ok
#include <cstdio>
#include <cstdlib>
#include <exception>

extern void f();             // potentially throwing

void g() noexcept {
    f();                     // well-formed, even if f throws
    throw 42;                // well-formed; the effect is as if std::terminate were called
}

void f() {}

int main() {
    std::set_terminate([] { std::fputs("terminate\n", stderr); std::abort(); });
    g();
}
```

For `throw 42;`, Clang 23 warns `'g' has a non-throwing exception specification but can still throw`, but does not report an error. When run, the program prints `terminate`.

C++ does not make this a compile-time check because the compiler cannot know whether a function without `noexcept` actually throws. C functions, old code and virtual function calls mostly lack accurate exception specifications; if `noexcept` functions could only call `noexcept` functions, code could hardly be written at all. `noexcept` is a run-time promise: the consequence of breaking it is guaranteed termination, which the compiler can rely on to optimize callers.

The rule is about the search exiting the function body. An exception caught inside a `noexcept` function is no problem:

```cpp title="noexcept-internal-catch.cpp" ok
void may_throw();

void safe() noexcept {
    try { may_throw(); }
    catch (...) {}           // the exception does not leave the function body
}
```

¶8 If no matching handler is ever found, `std::terminate` is called. Whether the stack is unwound before that ([[g:stack-unwinding]], destroying the automatic objects at each level of the call chain) is implementation-defined; see [[except.terminate]].

```cpp run title="no-handler.cpp" impl
#include <cstdio>
#include <cstdlib>
#include <exception>

struct D {
    const char* n;
    ~D() { std::printf("~%s\n", n); std::fflush(stdout); }
};

void g() { D d{"g-local"}; throw 1; }

int main() {
    std::set_terminate([] { std::puts("terminate"); std::fflush(stdout); std::_Exit(0); });
    D m{"main-local"};
    g();                     // no handler at all
}
```

With Clang 23 and libc++abi, at both `-O0` and `-O2`, this prints only `terminate`; neither local object is destroyed. The Itanium ABI first does a read-only search pass and terminates immediately if the search fails, so the core dump keeps the complete call stack at the throw point. Code that relies on an uncaught exception to trigger destructors is not portable; when cleanup is needed, put a `catch (...)` in `main` and in every thread's entry function.

## The currently handled exception (¶9–¶10)

¶9 A handler becomes [[g:active-handler|active]] when the initialization of its catch clause's parameter is complete. Note 4 points out that the stack has been unwound by then. A handler is no longer active when the catch clause exits. When `std::terminate` is entered because of a throw, an implicit handler is also considered active.

¶10 The exception handled by the most recently activated handler that is still active is called the [[g:currently-handled-exception]]. It is what `throw;` rethrows and what `std::current_exception()` returns.

A handler can contain another try/catch, so several handlers can be active at once. The currently handled exception is like the top of a stack:

```cpp run title="currently-handled.cpp" ok
#include <cstdio>

void show() {
    try { throw; }                         // rethrows the currently handled exception
    catch (int i)    { std::printf("int %d\n", i); }
    catch (double d) { std::printf("double %g\n", d); }
}

int main() {
    try { throw 1; }
    catch (int) {
        show();                            // int 1
        try { throw 2.5; }
        catch (double) { show(); }         // double 2.5: the inner handler was activated most recently
        show();                            // int 1: the inner handler has exited
    }
}
```

The implicit handler lets a terminate handler obtain the exception that caused termination too. libstdc++'s default handler can print the type of an uncaught exception, and this is what it relies on:

```cpp run title="terminate-handler.cpp" ok
#include <cstdio>
#include <cstdlib>
#include <exception>
#include <stdexcept>

int main() {
    std::set_terminate([] {
        if (auto p = std::current_exception()) {
            try { std::rethrow_exception(p); }
            catch (const std::exception& e) { std::fprintf(stderr, "uncaught: %s\n", e.what()); }
            catch (...) { std::fputs("uncaught: unknown\n", stderr); }
        }
        std::abort();
    });
    throw std::runtime_error("disk on fire");   // prints uncaught: disk on fire
}
```

## Initializing the handler's parameter (¶15–¶16)

¶15 Let the variable declared by the handler have type cv `T` or cv `T&`, and let `E` be the type of the exception object:

- ¶15.1 if `T` is a base class of `E`, the variable is copy-initialized from an lvalue of type `T` designating the corresponding base class subobject of the exception object;
- ¶15.2 otherwise, the variable is copy-initialized from an lvalue of type `E` designating the exception object.

The lifetime of this variable ends when the handler exits, after the destruction of all automatic objects within the handler.

Several things follow:

- Catching by value is a copy. The source is an lvalue, so no move constructor is called, and catching a move-only type by value is ill-formed.
- Catching a base class by value slices (¶15.1).
- The copy can be elided: [[class.copy.elision#1]] allows the handler's variable to be treated as an alias for the exception object. Clang does not do this elision.
- The exception is not yet caught during the copy, so if the copy constructor throws, `std::terminate` is called ([[except.throw]]).

¶16 Note 5 explains the difference between by value and by reference: if the handler declares an object, modifying it does not affect the exception object; if it declares a reference, what is modified is the exception object itself, and a subsequent `throw;` rethrows the modified object.

```cpp run title="modify-exception.cpp" ok
#include <cstdio>

struct E { int v; };

int main() {
    try {
        try { throw E{1}; }
        catch (E& e) { e.v = 2; throw; }        // modifies the exception object
    } catch (E e) { std::printf("%d\n", e.v); }  // 2

    try {
        try { throw E{1}; }
        catch (E e) { e.v = 2; throw; }         // modifies a copy
    } catch (E e) { std::printf("%d\n", e.v); }  // 1
}
```

## function-try-block (¶11–¶14)

A **function-try-block** wraps the whole function body in a try: `void f() try { ... } catch (...) { ... }`. On a constructor, it can also catch exceptions thrown in the member initializer list; see [[except.pre]].

¶11 Referring to any non-static member or base class of the object in a handler of a function-try-block of a constructor or destructor is undefined behavior. Before the handler is entered, the subobjects already constructed have been destroyed ([[except.ctor]]), so there is nothing left to access.

```cpp title="ctor-handler-member.cpp" ub
#include <cstdio>
#include <string>

struct Thrower { Thrower() { throw 0; } };

struct S {
    std::string name;
    Thrower t;
    S() try : name("widget"), t() {
    } catch (...) {
        std::puts(name.c_str());   // UB: name has already been destroyed
    }
};
```

Clang 23 warns `cannot refer to a non-static member from the handler of a constructor function try block`, but still accepts it. The standard does not require UB to be diagnosed.

¶13 A `return` statement in a handler of a function-try-block of a constructor makes the program ill-formed. Clang reports `return in the catch of a function try block of a constructor is illegal`.

¶14 When control reaches the end of a handler of a function-try-block of a constructor or destructor, the currently handled exception is rethrown. An object whose construction failed does not exist, so the constructor cannot return as if it had succeeded; the handler can only replace the exception with another, or let the original continue propagating.

```cpp run title="ctor-rethrow.cpp" ok
#include <cstdio>

struct U {
    U() try { throw 7; }
    catch (int) { std::puts("U handler"); }   // rethrows automatically at the end
};

int main() {
    try { U u; }
    catch (int i) { std::printf("rethrown %d\n", i); }
}
```

For other functions, flowing off the end of a handler of a function-try-block is equivalent to flowing off the end of the function body ([[stmt.return]]). For a function whose return type is not `void`, that is UB, except for `main`:

```cpp title="ftb-flow-off.cpp" ub
int parse(const char* s) try {
    return s[0] - '0';
} catch (...) {
    // flowing off the end: UB for a function returning int
}
```

¶12 Exceptions thrown in the constructors (for non-block variables) or destructors of objects with static storage duration are not caught by a function-try-block on `main`. Likewise, the corresponding cases for thread storage duration are not caught by a function-try-block on the thread's initial function. These constructions happen before `main` begins and these destructions after `main` returns, when `main`'s try block is not in the entered state. The exception leads directly to `std::terminate` ([[except.terminate]]):

```cpp run title="static-init-throw.cpp" ok
#include <cstdio>

struct S { S() { throw 1; } };
S s;                          // constructed before main; throwing calls std::terminate

int main() try {
    return 0;
} catch (...) {
    std::puts("never");       // main's handler cannot catch it
    return 1;
}
```

When run, it prints `libc++abi: terminating due to uncaught exception of type int` and ends with SIGABRT.

## Common misconceptions

!!! pitfall "Catching polymorphic exceptions by value"
    `catch (std::exception e)` slices: `e.what()` calls `std::exception::what()`, and there is an extra copy. Write `catch (const std::exception& e)`.

!!! pitfall "Handler matching is like overload resolution"
    `throw std::string("x");` is not caught by `catch (const char*)`, and `throw 1.0f;` is not caught by `catch (double)`. The only conversions available are derived to public base, and a few pointer conversions.

!!! pitfall "Uncaught exceptions also trigger destructors"
    Whether the stack is unwound when no handler is found is implementation-defined, and mainstream implementations do not unwind. Cleanup such as flushing logs or deleting temporary files must rely on a `catch (...)` in the entry functions.

## Questions

!!! question "Question 1"
    Which handler is selected below?

    ```cpp
    struct B {};
    struct D : B {};
    try { throw D{}; }
    catch (const B&) { /* #1 */ }
    catch (D&)       { /* #2 */ }
    ```

<details markdown="1">
<summary>Answer</summary>

#1. Handlers are tried in order of appearance (¶4), and `const B&` already matches (¶3.2: `B` is an unambiguous public base class of `D`), so #2 can never be reached. If this were overload resolution, `D&` would be the better match.
</details>

!!! question "Question 2"
    Can `throw (char*)buf;` be caught by `catch (const char* const& p)`? By `catch (const char*& p)`?

<details markdown="1">
<summary>Answer</summary>

`const char* const&` can. `T = const char*` is a pointer type, the handler has the form `const T&`, and `char*` becomes `const char*` by a qualification conversion (¶3.3.3).

`const char*&` cannot, per the standard. It is a non-const reference, which does not satisfy the cv `T` or `const T&` that ¶3.3 requires; and by ¶3.1, `char*` and `const char*` are not the same type. If binding were allowed, `p = "literal";` would write a `const char*` into an exception object of type `char*`, and a later `catch (char* q)` could modify the string literal through `q`. [[conv.qual]] forbids the implicit conversion from `char**` to `const char**` for the same reason. (As with `B*&`, some run-time libraries may actually match it; see the implementation note above.)
</details>

!!! question "Question 3"
    `main` only calls `f()`. Compare `void f() noexcept { throw 1; }` with `void f() { throw 1; }` at the level of the standard.

<details markdown="1">
<summary>Answer</summary>

Both call `std::terminate`, but on different grounds, and with different rules for stack unwinding.

The `noexcept` version relies on ¶7: the search exits the function body of a non-throwing function. Whether the stack is unwound is implementation-defined, and it may be only partially unwound ([[except.terminate#2]]). The version without `noexcept` relies on ¶8: no handler is found, which is also implementation-defined, but the stack can only be either fully unwound or not unwound at all.

In the Itanium implementation, a `noexcept` function has a landing pad that catches everything and calls terminate, and the search phase treats it as a handler, so unwinding proceeds up to the frame of `f`, and `f`'s own local objects are not destroyed. The latter finds no handler at all in the search phase and terminates immediately, without unwinding at all.
</details>
