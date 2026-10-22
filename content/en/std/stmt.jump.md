---
title: "Jump statements: break, continue, return, co_return, goto"
summary: "How jump statements transfer control and which objects are destroyed when a scope is left; how return initializes the return value, when it moves implicitly, and why returning a reference bound to a temporary is ill-formed in C++26; the rules for co_return and goto."
updated: 2026-10-19
---

!!! tldr
    - Whichever jump leaves a scope, the local objects already constructed in it are destroyed in reverse order of construction; `std::exit` and `std::abort` do not destroy local objects.
    - `break` ends only the innermost loop or `switch`; `continue` jumps to the end of the current iteration of the loop body, and in a `for` the iteration expression is executed first.
    - `return x;` constructs the return value by copy-initialization; since C++23 a returned local variable is treated directly as an xvalue, so moving is preferred, and returning it by lvalue reference is a compile error.
    - Since C++26, a `return` that binds the returned reference to a temporary (as in `const std::string& f() { return "abc"; }`) is ill-formed.
    - Flowing off the end of a non-`void` function is undefined behavior (except for `main` and coroutines); a coroutine cannot contain `return` and must use `co_return`.

¶1 Jump statements unconditionally transfer control. There are five: `break;`, `continue;`, `return operand(opt);`, `co_return operand(opt);` and `goto label;`.

## Destroying objects on leaving a scope [stmt.jump.general]

```cpp run ok
#include <cstdio>
struct T { const char* n; ~T() { std::printf("~%s ", n); } };
int f() {
    T a{"a"};
    for (int i = 0; ; ++i) {
        T b{"b"};
        {
            T c{"c"};
            if (i == 1) return i;   // destroys c, b, a in turn
        }                           // iteration 0: destroys c
    }                               // iteration 0: destroys b
}
int main() { f(); std::printf("\n"); }   // ~c ~b ~c ~b ~a
```

¶2 However a scope is exited, the objects with automatic storage duration (ordinary local variables) already constructed in it are destroyed in reverse order of construction. The normative rule is in [[stmt.dcl#2]]; for temporaries see [[class.temporary]]. This is the language foundation of RAII: when `break`, `continue`, `return` or `goto` jumps out of several blocks at once, the objects at every level are properly destroyed.

Note 1 reminds us that a program can terminate without going through this step: `std::exit()` destroys only objects with static storage duration and calls the functions registered with `atexit`, and `std::abort()` destroys nothing ([[support.start.term]]). Note 2 explains that suspending a coroutine ([[expr.await]]) does not count as leaving a scope; while suspended, the local variables are kept in the coroutine frame and are not destroyed.

## break and continue [stmt.break] [stmt.cont]

[[stmt.break#1]] A `break` must be within some iteration statement, expansion statement ([[stmt.expand]]) or `switch`; it ends the innermost such statement, and control passes to the statement following the one ended.

Because it ends the innermost one, a `break` in a `switch` inside a loop leaves only the `switch`:

```cpp run ok
int main() {
    int i = 0;
    for (; i < 10; ++i) {
        switch (i) {
        case 3:
            break;      // ends only the switch
        default:
            continue;
        }
        break;          // this break is the one that ends the for
    }
    return i == 3 ? 0 : 1;
}
```

C++ has no labeled `break`. To leave several nested loops, use `goto`, move the loops into a function and `return`, or use a flag variable.

[[stmt.cont#1]] A `continue` must be within an iteration statement or expansion statement; a `switch` does not count. Let X be the innermost such statement:

- If X is an iteration statement, control passes to the end of X's loop body. Next, `while` and `do` test the condition; `for` first executes the iteration expression ([[stmt.for#1]]); range-based `for` executes `++begin`.
- If X is an expansion statement, control passes to the end of the current copy of the loop body, moving on to the next copy ([[stmt.expand]]).

Passing to the end of the loop body means the local objects in the body are destroyed as usual, the same as completing an iteration normally.

```cpp error
void f(int k) {
    switch (k) {
    case 0:
        continue;   // error: not in a loop
    }
}
```

## return [stmt.return]

### The operand

¶1 A function returns control to its caller with `return`. ¶2 The expression or braced list after `return` is called its **operand**.

| Operand | Only allowed in |
|---|---|
| none | functions returning (possibly cv-qualified) `void`, constructors, destructors |
| an expression of type `void` | functions returning `void` |
| anything else | functions whose return type is not `void` |

The second row lets generic code forward a call that might return `void` unchanged:

```cpp ok
void log();
void wrapper() { return log(); }   // OK
template<class F> decltype(auto) call(F f) {
    return f();                    // works even when F returns void
}
```

### Copy-initialization

In the third case, `return` initializes the result of the function call, that is, the returned reference or the result object of the prvalue, from the operand by **copy-initialization** (initialization of the form `T x = e;`, see [[dcl.init]]). Three consequences follow.

First, copy-initialization does not use `explicit` constructors, so `return {1};` is ill-formed when it selects an explicit constructor:

```cpp error
struct E { explicit E(int); };
E ee() { return {1}; }   // error: explicit constructor
```

Second, when the return type is not a reference, the result object is the one the caller prepared. Since C++17 ([[P0135R1]]), when the operand is a prvalue of the same type, it initializes the result object directly, with no intermediate temporary, so no copy or move constructor is needed. This is called guaranteed copy elision:

```cpp ok
struct NoMove {
    NoMove(int);
    NoMove(const NoMove&) = delete;
    NoMove(NoMove&&) = delete;
};
NoMove make()  { return NoMove(1); }  // OK
NoMove make2() { return 1; }          // OK
```

Third, when the operand is a local variable, the compiler may construct that variable directly in the result object (named return value optimization, NRVO), but this is not guaranteed. When it does not, a move is attempted instead of a copy; the rules are in the next section.

¶3 The destructor of the result object is potentially invoked ([[class.dtor]]): even if it will never actually be called, it must be accessible and not deleted.

```cpp error
class A {
    ~A() {}               // private
};
A f() { return A(); }     // error: the destructor is private
```

When the function definition is compiled, it is not known how the caller will use the result; it may be discarded or bound to a reference. Also, if destroying some local variable after the `return` throws an exception, the already-constructed result object must be destroyed ([[except.ctor]]). So the destructor is required to be usable across the board.

### Implicit move

```cpp ok
#include <memory>
std::unique_ptr<int> take(std::unique_ptr<int>&& p) {
    return p;     // p is an rvalue reference variable: moved
}
struct B {}; struct D : B {};
std::unique_ptr<B> up() {
    auto d = std::make_unique<D>();
    return d;     // moved even though the types differ
}
```

`unique_ptr` cannot be copied, yet both functions compile, because the names in `return p;` and `return d;` are treated as rvalues. Note 2 in ¶2 points to [[class.copy.elision]], and the detailed rules are in [[expr.prim.id.unqual#15]]. A name is **move-eligible** if it satisfies three conditions:

- it names an implicitly movable entity: a non-volatile object with automatic storage duration, or an rvalue reference variable to a non-volatile object type;
- it is the operand of `return`, `co_return` or `throw`, possibly parenthesized;
- only block scopes lie between the entity's declaration and this expression.

[[expr.prim.id.unqual#12]] specifies that a move-eligible name is an xvalue. So the `x` in `return x;` takes part in overload resolution like `std::move(x)`, preferring the move constructor.

[[P2266R3]] in C++23 simplified things to this form. The earlier rule was a two-phase overload resolution: first treat the operand as an rvalue, and if that fails, redo it as an lvalue. The two rules give different results in a few cases:

| Case | C++20 | Since C++23 |
|---|---|---|
| Returning `T&` with a local variable as the operand | compiles, returns a dangling reference | ill-formed: an lvalue reference cannot bind to an xvalue |
| The type has only a `T(T&)` copy constructor | falls back to an lvalue and calls `T(T&)` | ill-formed |
| `return (x);` in a `decltype(auto)` function | deduces `T&` | deduces `T&&`, still dangling |

<div class="compare" markdown="1">

```cpp error
struct Weird {
    Weird();
    Weird(Weird&);
};
Weird g(bool b) {
    static Weird w1;
    Weird w2;
    if (b) return w1;  // OK: static variable
    return w2;         // error: xvalue
}
```

```cpp error
int& h(int i) {
    return i;   // error: i is an xvalue
}
```

</div>

Before this, [[P1825R0]] in C++20 had already extended implicit move, within the two-phase framework, to cases such as rvalue reference variables.

!!! pitfall "`return std::move(x);` is usually slower"
    The operand of `return std::move(x);` is no longer a name, so NRVO cannot happen, and only a move is possible. `return x;` moves anyway when NRVO is not done. Clang and GCC have a `-Wpessimizing-move` warning for this. `std::move` helps only when returning entities that are not implicitly movable, such as members or global variables.

### Flowing off the end of a function

¶4 When execution reaches the end of the function body without encountering a `return` (flowing off the end):

- constructors, destructors, and non-coroutine functions returning `void`: equivalent to `return;`;
- `main`: equivalent to `return 0;` ([[basic.start.main]]);
- coroutines: see `co_return` below;
- any other function: undefined behavior {{ub}}.

The undefined behavior happens when the end is actually reached, not when it might be reached. So a compiler cannot reject such a function, only warn (`-Wreturn-type`):

<div class="compare" markdown="1">

```cpp ok
int sign(int x) {
    if (x > 0) return 1;
    if (x < 0) return -1;
    if (x == 0) return 0;
}   // never reached, but there will be a warning
```

```cpp run ub
int f(bool b) {
    if (b) return 1;
}   // f(false) flows off the end
int main() {
    return f(false);
}
```

</div>

At both `-O0` and `-O2`, Clang 23 places a trap instruction at the end of `f`, and the program on the right terminates with `SIGTRAP`. This is only one possible outcome: the optimizer may conclude that the path never happens and delete it along with the code before it. Enabling `-Werror=return-type` is recommended.

### Order of destruction

¶5 specifies the order of three things in a `return` statement: first the result is copy-initialized, then the temporaries in the operand's full-expression are destroyed, and finally the local variables of the block containing the `return` are destroyed. Note 3 continues outward: then the local variables of the enclosing blocks are destroyed, then the function's postcondition assertions are evaluated ([[dcl.contract.func]], {{c++26}}), and finally the function parameters are destroyed ([[expr.call]]).

Because the result is constructed before the local variables are destroyed, the return value can safely be computed from local variables, for example copying data under the protection of a lock:

```cpp run ok
#include <mutex>
#include <vector>
std::mutex m;
std::vector<int> data{1, 2, 3};
std::vector<int> snapshot() {
    std::lock_guard lk(m);
    return data;   // the result is copied first, then lk is destroyed (unlocking)
}
int main() { return snapshot().size() == 3 ? 0 : 1; }
```

### Returned references bound to temporaries {{c++26}}

```cpp error
#include <string>
auto&& f1() {
    return 42;     // error: binds to the temporary materialized from 42
}
const double& f2() {
    static int x = 42;
    return x;      // error: int → double creates a temporary
}
const std::string& f3() {
    return "abc";  // error: constructs a temporary std::string
}
struct R { const int& r; };
R f4() {
    return {42};   // error: the member reference r binds to a temporary
}
```

All of these functions compile in C++23 and earlier, but every call necessarily returns a dangling reference: the temporary is destroyed at the end of the `return`'s full-expression, and a reference bound to the return value does not extend its lifetime ([[class.temporary]]). [[P2748R5]] in C++26 made them compile errors.

¶6 Specifically, if a `return` statement binds one of these two kinds of reference to a temporary, the program is ill-formed:

- ¶6.1 the returned reference;
- ¶6.2 a constituent reference ([[intro.object]]) of the returned object, that is, its members of reference type, and recursively such members of its subobjects.

`f2` is easy to misread: `x` is a static variable, but `const double&` cannot bind directly to an `int`; a `double` temporary has to be created by conversion first.

The rule looks only at the binding the `return` makes directly. A temporary returned through an intervening function call is not covered (Example 2 in the standard):

```cpp ok
auto&& id(auto&& r) { return static_cast<decltype(r)&&>(r); }
auto&& f3() {
    return id(42);   // well-formed, but returns a dangling reference
}
```

¶6 makes an exception for `std::is_convertible`. [[meta.rel]] defines `is_convertible<From, To>` by whether a hypothetical function `To test() { return std::declval<From>(); }` is well-formed; without the exception, `is_convertible_v<int, const double&>` would become `false`, changing the behavior of existing code.

!!! impl "How return values are passed in the ABI"
    The Itanium C++ ABI (used by GCC and Clang on Unix-like platforms) specifies that a class-type return value that is not trivially copyable or not trivially destructible is stored in memory allocated by the caller, whose address is passed as a hidden argument, and the callee constructs it directly there. This is what "the result object is provided by the caller" looks like at the machine level, and why guaranteed copy elision has no extra cost. Small trivial types are returned in registers.

## co_return [stmt.return.coroutine]

¶1 `co_return` returns control to the caller or resumer of a coroutine ([[dcl.fct.def.coroutine]]). A coroutine shall not contain a `return` statement; Note 1 adds that this holds even if the `return` is in a discarded branch of `if constexpr`.

```cpp error
#include <coroutine>
struct T {
    struct promise_type {
        T get_return_object() { return {}; }
        std::suspend_never initial_suspend() noexcept { return {}; }
        std::suspend_never final_suspend() noexcept { return {}; }
        void return_void() {}
        void unhandled_exception() {}
    };
};
T d() {
    if constexpr (false) { return T{}; }   // error
    co_return;
}
```

Whether a function is a coroutine is determined by whether its body contains `co_await`, `co_yield` or `co_return`. Because `return` is forbidden even in discarded statements, whether a function is a coroutine, and whether it can contain `return`, does not vary with template arguments.

¶2 Let *p* be an lvalue naming the coroutine promise object. A `co_return` statement is equivalent to `{ S; goto final-suspend; }`, where *final-suspend* is the exposition-only label defined in [[dcl.fct.def.coroutine]], located after the coroutine body and before `co_await p.final_suspend()`. S is:

- ¶2.1 if the operand is a braced list or a non-`void` expression, `p.return_value(operand)`;
- ¶2.2 otherwise, `{ expression(opt); p.return_void(); }`.

In both cases the call must be a prvalue of type `void`. It follows that the `x` in `co_return x;` is likewise move-eligible and selects `return_value(T&&)`; and that `goto final-suspend` leaves the scope of the coroutine body, so the local variables of the coroutine body are destroyed before `final_suspend`, while the coroutine frame itself is freed later.

```cpp run ok
#include <coroutine>
#include <exception>
struct Task {
    struct promise_type {
        int value = 0;
        Task get_return_object() {
            return Task{std::coroutine_handle<promise_type>::from_promise(*this)};
        }
        std::suspend_never initial_suspend() noexcept { return {}; }
        std::suspend_always final_suspend() noexcept { return {}; }
        void return_value(int v) { value = v; }   // called by co_return e;
        void unhandled_exception() { std::terminate(); }
    };
    std::coroutine_handle<promise_type> h;
    ~Task() { if (h) h.destroy(); }
    int get() const { return h.promise().value; }
};
Task answer(bool b) {
    if (b) co_return 42;
    co_return 0;
}
int main() { return answer(true).get() == 42 ? 0 : 1; }
```

¶3 If overload resolution for `p.return_void()` succeeds, flowing off the end of the coroutine body is equivalent to `co_return;`; otherwise (the promise has only `return_value`) the behavior is undefined {{ub}}. This corresponds to ordinary functions: a coroutine that returns a value must explicitly `co_return` one.

## goto [stmt.goto]

¶1 `goto` unconditionally jumps to the statement marked by the label. The label must be in the current function; a `goto` cannot jump out to an enclosing function or out of a lambda.

`goto` itself has only this one rule, but other subclauses add quite a few restrictions:

| Restriction | Source |
|---|---|
| Cannot pass the declaration of a local variable with initialization into its scope (except vacuous initialization such as `int x;`) | [[stmt.dcl#2]] |
| Cannot jump into a branch of `if constexpr` or `if consteval` or into the body of an expansion statement | [[stmt.label#3]] |
| Cannot jump into a `try` block or a handler | [[except.pre#3]] |
| An expansion statement cannot contain labels | [[stmt.label#4]] |
| If a `goto` is executed during constant evaluation, the expression is not a constant expression | [[expr.const.core#2.36]] |

Jumping backward destroys the variables passed over, then initializes them again (Example 1 in [[stmt.dcl#2]]):

```cpp run ok
#include <cstdio>
struct X {
    int n;
    X(int n) : n(n) { std::printf("X(%d) ", n); }
    ~X() { std::printf("~X(%d) ", n); }
};
int main() {
    int k = 0;
ly:
    X a = ++k;          // every goto ly destroys a first, then constructs it again
    if (k < 3) goto ly;
    std::printf("done ");
}   // X(1) ~X(1) X(2) ~X(2) X(3) done ~X(3)
```

```cpp error
void f() {
    goto l1;   // error: cannot jump into a try block
    try {
    l1: ;
    } catch (...) { }
}
```

Since C++23 ([[P2242R3]]), `goto` and labels can appear in `constexpr` functions, but if a `goto` is actually executed during constant evaluation, the evaluation is not a constant expression. The standard uses `goto` to define statements such as `while`, and the note in [[expr.const.core]] explains that the `goto`s in those rewrites do not count.

```cpp error
constexpr int f(int n) {
    if (n < 0) goto fail;
    return n;
fail:
    return -1;
}
static_assert(f(3) == 3);   // OK: no goto executed
constexpr int y = f(-1);    // error: a goto is executed
```

## History

!!! history
    - C++98: `return` copy-initializes the return value; eliding the copy is allowed but not guaranteed; flowing off the end of a non-`void` function is undefined behavior.
    - C++11: the operand can be a braced list; implicit move introduced (two-phase overload resolution).
    - C++17: guaranteed copy elision ([[P0135R1]]).
    - C++20: coroutines and `co_return`; implicit move extended to rvalue reference variables and other cases ([[P1825R0]]).
    - C++23: move-eligible names are xvalues directly ([[P2266R3]]); `goto` and labels allowed in `constexpr` functions ([[P2242R3]]).
    - C++26: a returned reference bound to a temporary is ill-formed ([[P2748R5]]); postconditions are evaluated after local variables are destroyed and before parameters are; `break` and `continue` can be used in expansion statements.

## Questions

!!! question "1. What type does the function below return in C++20 and in C++23?"
    ```cpp
    decltype(auto) f() { int x = 0; return (x); }
    ```

<details markdown="1">
<summary>Answer</summary>

In C++20 it is `int&`: `(x)` is an lvalue, and `decltype((x))` is `int&`. Since C++23 it is `int&&`: `x` is move-eligible, and `(x)` is the parenthesized operand of `return`, so it is an xvalue. In both cases it returns a dangling reference to a local variable. This is not binding to a temporary, so ¶6 does not apply, and Clang gives only a `-Wreturn-stack-address` warning.
</details>

!!! question "2. Does `struct S { const int& r; }; S g() { return S{42}; }` violate ¶6?"

<details markdown="1">
<summary>Answer</summary>

By the wording, it should. Because of guaranteed copy elision, `S{42}` initializes the returned object itself, and its constituent reference `r` is bound in this `return` to the temporary materialized from `42`, which falls under ¶6.2. However, Clang 23 reports an error only for `return {42};`, not for `return S{42};`, and gives no warning either. Whether or not the compiler diagnoses it, the `r` the caller gets is dangling.
</details>

!!! question "3. Why must `return` initialize the result before destroying local variables? Give an example that would go wrong the other way round."

<details markdown="1">
<summary>Answer</summary>

Because the operand often reads local variables. For example, in `std::string s = ...; return s.substr(1);`, if `s` were destroyed first, `substr` would read a destroyed object. In `snapshot` above, if the `lock_guard` were destroyed before `data` is copied, the copy would happen outside the lock and could race with other threads. ¶5 guarantees that the result is constructed first, then the temporaries are destroyed, then the local variables.
</details>

## Summary

| Statement | Key points |
|---|---|
| All jumps | on leaving a scope, constructed local objects are destroyed in reverse order; `std::exit` and `std::abort` are exceptions; suspending a coroutine does not count as leaving |
| `break` | within a loop, expansion statement or `switch`; ends the innermost one |
| `continue` | within a loop or expansion statement; passes to the end of the current loop body |
| `return` | copy-initializes the result; move-eligible local variables are xvalues (C++23); the result object's destructor must be usable; the result is initialized first, then temporaries and local variables are destroyed |
| Returning a binding to a temporary | ill-formed since C++26 |
| Flowing off the end | `void` functions, constructors and destructors: `return;`; `main`: `return 0;`; coroutines: depends on `return_void`; anything else: undefined behavior |
| `co_return` | `{ p.return_value(e) or p.return_void(); goto final-suspend; }`; a coroutine cannot contain `return` |
| `goto` | only to labels in the current function; cannot pass a declaration with initialization, and cannot jump into control-flow-limited statements or `try` blocks |
