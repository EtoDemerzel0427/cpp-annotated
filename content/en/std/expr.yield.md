---
title: Yielding a value (co_yield)
summary: "co_yield e is equivalent to co_await p.yield_value(e): it may appear only in a suspension context, its operand may be a braced list, it bypasses await_transform, and it can have a value."
updated: 2026-10-19
---

!!! tldr
    - The meaning of `co_yield e` is given entirely by a rewrite: it is equivalent to `co_await p.yield_value(e)`, where `p` is the promise object of the current coroutine.
    - The value of `co_yield` is determined by the awaiter that `yield_value` returns. If it returns `std::suspend_always`, it is `void`; with a custom awaiter it can pass a value from the caller back into the coroutine.
    - The operand can be a braced list: `co_yield {i, i};` is valid, while `co_await {1, 2}` is not.
    - The rewritten `co_await` bypasses `await_transform`, so a generator that forbids `co_await` can still `co_yield`.
    - `co_yield` can appear only inside a function body and outside `catch` blocks, and has the same precedence as assignment.

## `co_yield` is just a `co_await` (¶1)

A function whose body contains `co_await`, `co_yield` or `co_return` is a **coroutine** ([[g:coroutine]]): it can suspend partway through, give control back to its caller, and later resume from the suspension point. Every coroutine has a **promise object** ([[g:promise-object]]), whose type is determined by the return type and through which the coroutine exchanges data with the outside world ([[dcl.fct.def.coroutine]]).

¶1 Let `e` be the operand of the *yield-expression* and `p` an lvalue naming the promise object of the enclosing coroutine; then:

!!! std
    the *yield-expression* is equivalent to the expression `co_await p.yield_value(e)`.

So `co_yield` does two things. First it calls the promise object's `yield_value`, which usually stores the value for the caller to read; then it applies `co_await` ([[expr.await]]) to the return value of `yield_value`. If that returns `std::suspend_always`, the coroutine suspends and control returns to the caller or resumer.

The value of a `co_await` expression comes from the awaiter's `await_resume`. `std::suspend_always::await_resume()` returns `void`, so the most common form, `co_yield x;`, is a `void` expression. With a custom awaiter, `co_yield` has a value, and the coroutine can use it to receive data passed back by the caller:

```cpp run title="yield-two-way.cpp" ok
#include <coroutine>
#include <cstdio>
#include <utility>

struct Gen {
    struct promise_type {
        int current = 0;    // coroutine → caller
        int received = 0;   // caller → coroutine
        Gen get_return_object() {
            return Gen{std::coroutine_handle<promise_type>::from_promise(*this)};
        }
        std::suspend_always initial_suspend() noexcept { return {}; }
        std::suspend_always final_suspend() noexcept { return {}; }
        struct Awaiter {
            promise_type* p;
            bool await_ready() noexcept { return false; }
            void await_suspend(std::coroutine_handle<>) noexcept {}
            int await_resume() noexcept { return p->received; }   // the value of co_yield
        };
        Awaiter yield_value(int v) { current = v; return {this}; }
        void return_void() {}
        void unhandled_exception() {}
    };
    std::coroutine_handle<promise_type> h;
    explicit Gen(std::coroutine_handle<promise_type> h) : h(h) {}
    Gen(Gen&& o) : h(std::exchange(o.h, {})) {}
    ~Gen() { if (h) h.destroy(); }
};

Gen accumulate() {
    int total = 0;
    for (int i = 1; i <= 3; ++i) {
        int got = co_yield i;   // yields i; on resumption, gets the value the caller put in
        total += got;
    }
    co_yield total;
}

int main() {
    Gen g = accumulate();
    for (int k = 0; k < 4; ++k) {
        g.h.promise().received = 10 * k;
        g.h.resume();
        std::printf("%d ", g.h.promise().current);   // prints 1 2 3 60
    }
}
```

## Grammar: precedence and braced lists

```text
yield-expression:
    co_yield assignment-expression
    co_yield braced-init-list
```

A *yield-expression* is a kind of *assignment-expression* ([[expr.assign]]), at the same level as assignment and `throw`. So `co_yield a + b` yields `a + b`; `co_yield a, b` is `(co_yield a), b`; and `1 + co_yield 2` is a syntax error that has to be written `1 + (co_yield 2)`. It can appear on the right of an assignment and in initializers, such as `int got = co_yield i;` in the example above.

The operand can be a braced list. `co_yield {i, i};` is rewritten as `co_await p.yield_value({i, i})`, and the braced list initializes the parameter of `yield_value` ([[dcl.init.list]]). Example 1 in the standard uses this to yield a `pair<int, int>`. The operand of `co_await` is a *cast-expression* and cannot be a braced list.

## Bypassing `await_transform`

If the promise type declares `await_transform`, a user-written `co_await x` first becomes `p.await_transform(x)`. But [[expr.await#3.2]] excludes a `co_await` produced by a *yield-expression*, so the `co_await p.yield_value(e)` that `co_yield` rewrites to does not call `await_transform` again.

This lets a promise type forbid `co_await` without affecting `co_yield`. The promise type of `std::generator` declares `void await_transform() = delete;` ([[coro.generator.promise]]): name lookup always finds it, and it accepts no arguments, so any `co_await x` in a generator is ill-formed, while `co_yield` works as usual.

Conversely, if you want to intercept `co_yield`, do it in `yield_value`; `await_transform` has no say.

## Only in a suspension context

The first sentence of ¶1 says that a *yield-expression* shall appear only in a **suspension context** ([[g:suspension-context]]) of a function. Suspension contexts are defined in [[expr.await#2]]: within a function body or lambda body, outside an exception handler (`catch` block), and not in a default argument, the initializer of a block variable with static or thread storage duration, or the predicate of a contract assertion.

```cpp title="yield-context.cpp" error
#include <coroutine>

auto f(int x = co_yield 5);     // error: a default argument is not a suspension context
int a[] = { co_yield 1 };       // error: not within a function body
```

```cpp title="yield-in-handler.cpp" error
#include <coroutine>
struct Gen { struct promise_type; };   // details omitted

Gen g() {
    try { throw 1; }
    catch (...) { co_yield 1; }        // error: cannot suspend in a catch block
}
```

While a `catch` block executes there is a currently handled exception, and both `throw;` and `std::current_exception` depend on this thread-bound state. If a coroutine suspended here and later resumed on another thread, that state could not be maintained.

A function whose body contains `co_yield` becomes a coroutine and must meet all the requirements for coroutines: the return type must have a suitable `promise_type`, an ordinary `return` cannot be used, and it cannot be `main`. A coroutine also cannot be a constexpr function, and a *yield-expression* cannot appear in constant evaluation ([[expr.const.core#2.27]]).

!!! impl
    The compiler splits a coroutine into a coroutine frame (usually allocated on the heap; the allocation can be elided when its lifetime is provably bounded) and a number of resumption points. Each `co_yield` is a suspension point: it first calls `yield_value`, then decides whether to suspend according to the awaiter's `await_ready` and `await_suspend`, and records the number of this resumption point in the coroutine frame. Each iteration of a generator is therefore just an indirect jump, with overhead comparable to a hand-written state machine.

!!! history
    Coroutines were first published as the Coroutines TS and merged into C++20 by [[P0912R5]]. `std::generator` ([[coro.generator]]), added in C++23, is built on `co_yield`: its `yield_value` stores only the address of the yielded object, because that object stays alive throughout the suspension; `co_yield std::ranges::elements_of(r)` yields all the elements of another range or generator in turn.

## Questions

!!! question "Question"
    A promise type `P` has both `yield_value(int)` and `await_transform`. Are `co_yield 1;` and a hand-written `co_await p.yield_value(1);` (assuming `p` is accessible in the coroutine) exactly the same?

<details markdown="1">
<summary>Answer</summary>

Not exactly. The former is a `co_await` produced by a *yield-expression*, which by [[expr.await#3.2]] does not look up `await_transform`. The latter is a user-written `co_await`, which looks up `await_transform` and calls `p.await_transform(p.yield_value(1))`; if `await_transform` doesn't accept the return type of `yield_value`, it is even ill-formed. So the equivalence the standard describes means evaluating as that `co_await` expression, while keeping its identity as something produced by `co_yield`.
</details>

## Summary

| Aspect | Rule |
|---|---|
| Meaning | `co_yield e` ≡ `co_await p.yield_value(e)` |
| Operand | *assignment-expression* or braced list |
| Precedence | Same level as assignment; `1 + co_yield 2` needs parentheses |
| Where it may appear | Suspension context: within a function body, outside `catch` blocks, not in default arguments and the like |
| `await_transform` | Does not apply |
| Value | Determined by the awaiter's `await_resume` |
| Constant evaluation | Cannot appear |
