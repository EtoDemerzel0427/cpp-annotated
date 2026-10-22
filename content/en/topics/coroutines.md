---
title: How C++20 coroutines work
summary: "The complete mechanism of C++20 coroutines: the three roles of promise, awaiter and handle, how co_await expands, how the compiler turns a coroutine into a state machine, why symmetric transfer is needed, and the most common lifetime mistakes."
tags: coroutines, co_await, state machines, symmetric transfer, lifetime
updated: 2026-10-19
---

!!! tldr
    - A coroutine is a function that can suspend at a `co_await` and resume later. C++ coroutines are stackless: local variables live in a separately allocated coroutine state, and only the coroutine body itself can suspend.
    - The language specifies only a set of rewrite rules, and every step of suspension and resumption calls hooks supplied by the user: the promise decides the policy for the whole coroutine, the awaiter decides the policy for one suspension, and `coroutine_handle` is used to resume and destroy the coroutine.
    - `co_await e` first calls `await_ready`; only if not ready does it suspend and call `await_suspend(h)`, and after resumption the result of `await_resume()` is the value of the expression. The coroutine already counts as suspended before `await_suspend` is called.
    - When `await_suspend` returns a handle, that coroutine is resumed next (symmetric transfer); implementations compile it as a tail call, so coroutines resuming each other don't grow the stack without bound.
    - A call to a coroutine returns at the first suspension, yet the body keeps running afterwards. Reference parameters, lambda captures and `this` may all be invalid by the time it resumes.

## What a coroutine is

A function whose body contains `co_await`, `co_yield` or `co_return` is a [[g:coroutine|coroutine]] ([[dcl.fct.def.coroutine#1]]). From the caller's point of view it is no different from an ordinary function; the difference is that it can pause at a `co_await`, hand control back to the caller, and later continue from where it paused. At the start of [[dcl.fct.def.coroutine]] there is a minimal `generator` example: `fib` suspends at every `co_yield`, and each time `main` calls `next()` it computes the next term.

A coroutine can pause because its local variables and copies of its parameters are not on the call stack but in a separately allocated [[g:coroutine-state|coroutine state]] (commonly called the coroutine frame). Suspending is like returning from the function, except that the coroutine state stays around and is used again at the next resumption.

C++ coroutines are **stackless**: only the coroutine body itself can suspend. An ordinary function called by the coroutine can't suspend on its behalf; to suspend inside a called function, that function must also be a coroutine, and the caller must `co_await` it.

The standard library provides no ready-made coroutine types such as `task` (`std::generator` is the only exception); what the language specifies is a rewrite protocol. Through the three roles below, the author of the return type tells the compiler how to handle suspension, resumption and return values.

## The three roles

| Role | What it is | Provided by | Responsible for |
|---|---|---|---|
| promise | An object in the coroutine state, of type `std::coroutine_traits<R, Args...>::promise_type`, which by default is `R::promise_type` | The author of return type `R` | Policy for the whole coroutine: whether to suspend at the start, where results and exceptions go, what to do at the end, what `co_yield` means, how to build the object returned to the caller |
| awaiter | The object obtained from `e` in `co_await e`, with three members `await_ready`, `await_suspend`, `await_resume` | The author of the awaited type | Policy for one suspension: whether to suspend, who gets the handle after suspending, what to return after resumption |
| `coroutine_handle` | A non-owning pointer to the coroutine state | The standard library ([[coroutine.handle]]) | `resume()`, `destroy()`, `done()`, `promise()`, `from_promise()` |

An object of the [[g:promise-type|promise type]] is called the **promise object**. It lives inside the coroutine state and is the coroutine's controller. The object returned to the caller (`task<T>`, `generator<T>`) usually holds a `coroutine_handle` and is responsible for destroying the coroutine state in its destructor. The awaiter is a temporary object that exists only for each `co_await`.

### The promise's hooks

The compiler replaces the coroutine's body with the following form ([[dcl.fct.def.coroutine#5]], details omitted):

```cpp
{
    promise_type promise(/* parameter copies, if a matching constructor exists */);
    /* object returned to the caller = */ promise.get_return_object();   // before initial_suspend, called once
    try {
        co_await promise.initial_suspend();
        /* the original body, in which:
           co_yield e    →  co_await promise.yield_value(e)
           co_return e;  →  promise.return_value(e); goto final_suspend;
           co_return;    →  promise.return_void();   goto final_suspend;
           flowing off the end  →  same as co_return; if return_void exists, otherwise UB */
    } catch (...) {
        if (!initial_await_resume_called) throw;   // body hasn't started; the exception goes straight to the caller
        promise.unhandled_exception();
    }
final_suspend:
    co_await promise.final_suspend();              // this expression must not throw
}
```

The order of the `get_return_object` call is in [[dcl.fct.def.coroutine#7]], the rule for flowing off the end in [[stmt.return.coroutine#3]], and the no-throw requirement on `final_suspend` in [[dcl.fct.def.coroutine#15]].

The return values of `initial_suspend` and `final_suspend` determine the basic behavior of a coroutine type:

| `initial_suspend` | `final_suspend` | Behavior | Example |
|---|---|---|---|
| `suspend_always` | `suspend_always` | Suspends right after creation and waits for the caller to resume it; at the end it stops at the final suspend point and the owner calls `destroy()` | `generator`, lazy `task` |
| `suspend_never` | `suspend_never` | Runs immediately; at the end the coroutine state is destroyed automatically and the handle becomes invalid | Fire-and-forget coroutines |
| `suspend_always` | An awaiter returning the awaiting coroutine's handle | Lazy start; at the end it transfers to resume the coroutine waiting for it | Composable `task` (see symmetric transfer below) |

## How `co_await` expands

### Getting the awaiter from the operand

[[expr.await#3]] turns the operand of `co_await expr` into an awaiter `e` in three steps:

1. If the promise type has a member named `await_transform`, `a = promise.await_transform(expr)`; otherwise `a = expr`. The implicit `co_await`s produced by `initial_suspend`, `final_suspend` and `yield_value` skip this step. This lets the promise intercept every `co_await` in the coroutine, for example to allow awaiting only certain types, or to insert cancellation checks.
2. Overload resolution is performed on `a` to look up `operator co_await` (member or non-member). If found, `o = operator co_await(a)`; otherwise `o = a`. This lets a type provide a separate awaiter instead of implementing the three member functions itself. The standard's example defines `operator co_await` for `std::chrono::duration`, so you can write `co_await 10ms;`.
3. If `o` is a prvalue it is materialized into a temporary, and `e` is an lvalue referring to it.

### Suspension and resumption

Then it is evaluated according to [[expr.await#5]]:

```cpp
if (!e.await_ready()) {
    // from here on the coroutine counts as suspended
    // depending on the return type of await_suspend:
    //   void                : e.await_suspend(h); then return to the caller or resumer
    //   bool                : if true, return to the caller or resumer; if false, resume this coroutine immediately
    //   coroutine_handle<Z> : e.await_suspend(h).resume();   symmetric transfer, see below
    // <suspend point>
}
// after resumption, or directly when await_ready is true:
result = e.await_resume();   // the value of the co_await expression
```

`h` is a `coroutine_handle<P>` referring to the current coroutine. The evaluation that calls `h.resume()` is called the [[g:resumer|resumer]]. A few points to note:

- When `await_ready()` returns `true` there is no suspension at all. When the result is already available, this fast path saves the cost of suspending.
- The coroutine counts as suspended before `await_suspend` is called. So `await_suspend` can hand `h` to another thread, and that thread can call `h.resume()` immediately, even before `await_suspend` has returned. If it were the other way round, and the coroutine only counted as suspended after `await_suspend` returned, that resumption would hit the UB of "resuming a coroutine that is not suspended" ([[dcl.fct.def.coroutine#8]]).
- If `await_suspend` throws, the coroutine is resumed and the exception is immediately rethrown.
- `co_await` may only appear in a function body, and not in a `catch` block, a default argument, the initializer of a static or thread-local variable, or the predicate of a contract assertion ([[expr.await#2]]).

### Resuming on another thread

```cpp run title="resume-on-thread.cpp" ok
#include <coroutine>
#include <cstdio>
#include <exception>
#include <thread>

struct fire_and_forget {
    struct promise_type {
        fire_and_forget get_return_object() { return {}; }
        std::suspend_never initial_suspend() noexcept { return {}; }
        std::suspend_never final_suspend() noexcept { return {}; }
        void return_void() { }
        void unhandled_exception() { std::terminate(); }
    };
};

struct resume_on_new_thread {
    std::jthread* out;
    bool await_ready() const noexcept { return false; }
    void await_suspend(std::coroutine_handle<> h) {
        std::jthread* o = out;                  // read the member into a local first
        *o = std::jthread([h] { h.resume(); }); // once the new thread starts, this awaiter may already be destroyed
    }
    void await_resume() const noexcept { }
};

fire_and_forget hop(std::jthread& t) {
    auto before = std::this_thread::get_id();
    co_await resume_on_new_thread{&t};
    auto after = std::this_thread::get_id();
    std::printf("switched thread: %s\n", before != after ? "yes" : "no");
}

int main() {
    std::jthread t;
    hop(t);
}   // t joins here
```

Reading `out` into a local in `await_suspend` avoids a real bug. The awaiter is a temporary in the coroutine state. As soon as the new thread resumes the coroutine, the coroutine may run to completion before `await_suspend` returns, destroying the coroutine state; reading `this->out` at that point reads a destroyed object.

Writing `*out = std::jthread(...)` directly runs into exactly this problem: since C++17 the right operand of an assignment is evaluated before the left, so `out` is read only after the thread has started. So after `await_suspend` has handed off the handle, it must not access the awaiter itself or anything in the coroutine state.

## How compilers implement coroutines

The standard specifies only the behavior. What follows is what Clang actually does; GCC is broadly the same. Knowing it helps in understanding the handle's interface and the cost of coroutines.

### Split into three functions

Clang splits a coroutine `fib(int)` into three functions. Compile the generator example from [[dcl.fct.def.coroutine]] with `clang++ -O1 -c` and `nm | c++filt` shows the three symbols:

- `fib(int)`, also called the ramp function: allocates the coroutine state, copies the parameters, constructs the promise, calls `get_return_object` and `initial_suspend`, and returns at the first suspension;
- `fib(int) (.resume)`: continues execution from the saved suspend point;
- `fib(int) (.destroy)`: destroys the local variables still alive at the current suspend point, the promise and the parameter copies, then frees the coroutine state.

The body of the resume function is a `switch` that jumps back to where it last stopped, by suspend point number:

```cpp
// the conceptual result (pseudocode, not a form specified by the standard)
struct fib_frame {
    void (*resume)(fib_frame*);     // offset 0
    void (*destroy)(fib_frame*);    // offset 8
    generator<int>::promise_type promise;
    int n, a, b, i;                 // parameter copies, and locals that live across suspend points
    unsigned char index;            // number of the current suspend point
};

void fib_resume(fib_frame* f) {
    switch (f->index) {
    case 0: goto initial_resumed;   // resuming from the initial suspend point
    case 1: goto after_yield;       // resuming from co_yield
    }
initial_resumed:
    f->a = 0; f->b = 1;
    for (f->i = 0; f->i < f->n; ++f->i) {
        f->promise.yield_value(f->a);
        f->index = 1;
        return;                     // suspending is returning to the resumer
after_yield:
        f->a = std::exchange(f->b, f->a + f->b);
    }
    f->promise.return_void();
    f->resume = nullptr;            // final suspend point reached: resume pointer set to null
    return;
}
```

### Layout of the coroutine state

In both Clang and GCC the coroutine state starts with two function pointers, to the resume function and the destroy function, followed by the promise object, then the parameter copies, the locals that live across suspend points, and the suspend point number. This explains the interface of `coroutine_handle`:

- `resume()` and `destroy()` need only the address of the coroutine state; through the two leading pointers they reach the code of the specific coroutine, a kind of hand-written type erasure;
- `done()` checks whether the resume pointer is null;
- `promise()` and `from_promise()` convert between the coroutine state's address and the promise's address by a fixed offset. The offset depends on the size and alignment of the promise, so only `coroutine_handle<P>` provides them; `coroutine_handle<>` does not.

Only variables that live across suspend points need to go into the coroutine state, so the size and layout of the coroutine state vary with the optimization level.

### Eliding the heap allocation

[[dcl.fct.def.coroutine#9]] says an implementation may need to allocate storage for the coroutine state. If the compiler can prove that the coroutine state's lifetime is entirely nested within the caller (created, used and destroyed in the caller, with the handle not escaping), it can put it in the caller's stack frame and skip `operator new` and `operator delete`. This optimization is called HALO (heap allocation elision optimization).

Compiling the generator example above at `-O2` in our tests, `main` contains no call to `operator new` at all. But HALO is unreliable: if the handle is stored in a container, passed out as a return value, or the coroutine's definition is in another translation unit and not visible, the optimization fails. Code that needs predictable memory behavior can provide its own `operator new` in the promise; see the example in [[dcl.fct.def.coroutine]].

## Symmetric transfer

Consider a lazy `task`: on `co_await child`, child is started in `await_suspend`; when child finishes, the coroutine waiting for it is resumed in child's `final_suspend`. The most direct way to write it is to call `resume()` inside `await_suspend`:

```cpp run title="asymmetric-overflow.cpp"
#include <coroutine>
#include <cstdio>
#include <utility>

struct task {
    struct promise_type {
        std::coroutine_handle<> cont;
        task get_return_object() { return task{std::coroutine_handle<promise_type>::from_promise(*this)}; }
        std::suspend_always initial_suspend() noexcept { return {}; }
        auto final_suspend() noexcept {
            struct A {
                bool await_ready() noexcept { return false; }
                void await_suspend(std::coroutine_handle<promise_type> h) noexcept {
                    if (h.promise().cont) h.promise().cont.resume();   // resumes parent inside child's stack frame
                }
                void await_resume() noexcept { }
            };
            return A{};
        }
        void return_void() { }
        void unhandled_exception() { }
    };
    std::coroutine_handle<promise_type> h;
    explicit task(std::coroutine_handle<promise_type> h) : h(h) { }
    task(task&& o) noexcept : h(std::exchange(o.h, {})) { }
    ~task() { if (h) h.destroy(); }
    bool await_ready() { return false; }
    void await_suspend(std::coroutine_handle<> c) { h.promise().cont = c; h.resume(); }  // starts child inside parent's stack frame
    void await_resume() { }
};

task leaf() { co_return; }
task loop(int n) { for (int i = 0; i < n; ++i) co_await leaf(); }

int main() {
    auto t = loop(1000000);
    t.h.resume();
    std::puts("done");
}
```

At `-O0` in our tests this program crashes with a stack overflow (exit code 139). On each iteration, `loop`'s resume function calls `leaf`'s resume function from `await_suspend`; when `leaf` finishes, it calls `loop`'s resume function from the `await_suspend` of `final_suspend`. None of these calls return, so stack frames pile up layer after layer: a million iterations means several million frames.

**Symmetric transfer** works like this: `await_suspend` doesn't call `resume()` itself; it returns the handle to resume, and the implementation calls `resume()` on it ([[expr.await#5.1.1]]). The standard doesn't say "tail call" directly, but its Note 1 says any number of coroutines can be resumed in succession this way, eventually returning to the caller. Implementations compile this call as a tail call that first pops the current coroutine's stack frame: Clang uses `musttail` in LLVM IR, even at `-O0`.

The example above needs only two changes:

```cpp
// the awaiter returned by final_suspend:
std::coroutine_handle<> await_suspend(std::coroutine_handle<promise_type> h) noexcept {
    return h.promise().cont ? h.promise().cont : std::noop_coroutine();
}
// task itself as the awaiter:
std::coroutine_handle<> await_suspend(std::coroutine_handle<> c) { h.promise().cont = c; return h; }
```

After the change the same loop prints `done` normally at `-O0`. `std::noop_coroutine()` ([[coroutine.noop]]) returns a handle that does nothing when resumed, used when there is no coroutine to transfer to and you just want to return to the caller.

## `std::generator` {{c++23}}

The C++23 standard library provides `std::generator<Ref, V = void, Allocator = void>` ([[coro.generator]], [[P2502R2]]), which is also a `std::ranges::view`:

```cpp title="std-generator.cpp"
#include <generator>
#include <print>
#include <ranges>

std::generator<int> iota(int n) {
    for (int i = 0; i < n; ++i) co_yield i;
}

std::generator<int> twice(int n) {
    co_yield std::ranges::elements_of(iota(n));   // delegate to another generator instead of forwarding one by one
    co_yield std::ranges::elements_of(iota(n));
}

int main() {
    for (int x : twice(3) | std::views::transform([](int v) { return v * 10; }))
        std::print("{} ", x);                       // 0 10 20 0 10 20
}
```

The libc++ that ships with Clang 23 doesn't have the `<generator>` header yet (libstdc++ has implemented it), so this example wasn't compiled locally. Delegation through `elements_of` is implemented with symmetric transfer, so no matter how deep the nesting, the stack doesn't grow.

## Common lifetime mistakes

Most coroutine bugs are lifetime bugs. A call to a coroutine returns at the first suspension, yet the body keeps running afterwards. By the time the coroutine resumes, temporaries in the call expression and the caller's local variables may all be gone.

| # | Code | Problem | Fix |
|---|---|---|---|
| 1 | `task f(const std::string& s)`, called as `f("literal")` | The temporary `string` is destroyed at the end of the full-expression containing the call; the coroutine state holds only a reference ([[dcl.fct.def.coroutine#13]]) | Take it by value: `task f(std::string s)` |
| 2 | `task f(std::string_view sv)` | The `string_view` is copied into the coroutine state, but the characters it points to aren't | Same as above |
| 3 | `[&x]() -> task { co_await …; use(x); }()` | The closure object is a temporary and isn't copied into the coroutine state, so the captures disappear with the closure | Don't capture in coroutine lambdas; or pass the closure in by value with C++23's `[x](this auto self) -> task { … }` |
| 4 | `task C::run() { co_await …; use(m); }` | The coroutine state holds only the `this` pointer, and the object is destroyed before resumption | Use `shared_from_this`, or make sure the object outlives the coroutine |
| 5 | `final_suspend` returns `suspend_never`, while the return object's destructor still calls `h.destroy()` | The coroutine state was already destroyed automatically and is destroyed again | Choose only one of the two ownership models |
| 6 | `await_suspend` accesses `this` after handing `h` to another thread | The coroutine may already have finished on the other thread | Don't access the awaiter or the coroutine state after handing off the handle |
| 7 | `task<int> f() { if (c) co_return 1; }` | Flowing off the end when the promise has no `return_void` is UB ([[stmt.return.coroutine#3]]) | Enable `-Werror=return-type` |
| 8 | Calling `resume()` on another coroutine directly inside `await_suspend` | Unbounded stack growth | Symmetric transfer: return the handle |
| 9 | Holding a `std::lock_guard` across a `co_await` | The coroutine may resume on another thread, and unlocking there a mutex that thread doesn't own is UB | Release the lock before the `co_await` |

A full demonstration of case 1 with the ASan report is in section 8 of [[topics/dangling-references]].

## Designing a coroutine type

When writing a coroutine return type, answer these questions in order:

1. Who owns the coroutine state? Does the return object hold the handle and `destroy()` it in its destructor, or is it destroyed automatically when the coroutine finishes? This decides `final_suspend`.
2. Does it run immediately when called? This decides `initial_suspend`. A lazy start composes more easily, and avoids the coroutine running to completion before the return object has even been constructed.
3. Where do results and exceptions go? This decides `return_value` or `return_void`, and `unhandled_exception`.
4. How does it connect when it is `co_await`ed? Make the return type itself an awaiter, and use symmetric transfer to start child coroutines and return to the awaiter.
5. What may the coroutine await? Control it with `await_transform`.
6. Where does the memory come from? Provide `operator new` in the promise (it may take allocator parameters), and `get_return_object_on_allocation_failure` if needed.

## Questions

!!! question "Question 1"
    How do `co_await std::suspend_always{};` and `co_await std::suspend_never{};` each expand? Which one creates a suspend point?

<details markdown="1">
<summary>Answer</summary>

`suspend_always::await_ready()` returns `false`, so the `void`-returning `await_suspend(h)` is called and control returns to the caller or resumer; this creates a suspend point. After resumption `await_resume()` is called, with no value. `suspend_never::await_ready()` returns `true`, so `await_resume()` is called directly, without suspending.

Both are trivial awaiters defined in [[support.coroutine]], with all members `constexpr` and `noexcept`, so they can be used as the return value of `final_suspend` ([[dcl.fct.def.coroutine#15]] requires that expression not to throw).
</details>

!!! question "Question 2"
    `std::coroutine_handle<>` doesn't know the promise type. How can it still `resume()` and `destroy()`? Why can't it `promise()`?

<details markdown="1">
<summary>Answer</summary>

Implementations agree that the coroutine state begins with two function pointers, resume and destroy; given only the address of the coroutine state, `resume()` and `destroy()` can reach the code of the specific coroutine through those pointers. `promise()` needs to know the offset and type of the promise object within the coroutine state, and the offset depends on the size and alignment of the promise, so only `coroutine_handle<P>` can provide it.
</details>
