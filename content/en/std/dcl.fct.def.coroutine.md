---
title: Coroutine definitions
summary: "A function whose body contains co_await, co_yield or co_return is a coroutine; the compiler rewrites the body into a fixed skeleton driven by the promise type, and the standard specifies how the coroutine state is allocated, how parameters are copied, and when it is destroyed."
updated: 2026-10-19
---

!!! tldr
    - If `co_await`, `co_yield` or `co_return` appears in a function body, the function is a coroutine. Callers can't tell from the declaration.
    - The language only specifies a skeleton: create the promise object, `initial_suspend`, the function body, `final_suspend`. Whether it runs lazily or eagerly, where the result goes and who destroys it are all decided by the `promise_type` in the return type.
    - Parameters are copied into the coroutine state when the coroutine starts. By-value parameters are moved in; reference parameters only have the reference copied, and may be dangling by the time the coroutine resumes.
    - The coroutine state is destroyed when control flows off the end or `destroy()` is called. Calling `resume()` or `destroy()` on a coroutine that isn't suspended is UB.
    - If the promise only has `return_value`, flowing off the end of the body is UB, not a compile error; `co_await promise.final_suspend()` must not throw.

## A minimal coroutine

```cpp run title="generator.cpp" ok
#include <coroutine>
#include <cstdio>
#include <utility>

template<class T>
class generator {
public:
    struct promise_type {
        T current;
        generator get_return_object() {
            return generator{std::coroutine_handle<promise_type>::from_promise(*this)};
        }
        std::suspend_always initial_suspend() noexcept { return {}; }  // suspend right after creation
        std::suspend_always final_suspend() noexcept { return {}; }    // stop at the end; generator destroys it
        std::suspend_always yield_value(T v) { current = std::move(v); return {}; }
        void return_void() { }
        void unhandled_exception() { throw; }
    };
    explicit generator(std::coroutine_handle<promise_type> h) : h_(h) { }
    generator(generator&& o) noexcept : h_(std::exchange(o.h_, {})) { }
    ~generator() { if (h_) h_.destroy(); }

    bool next() { h_.resume(); return !h_.done(); }
    const T& value() const { return h_.promise().current; }
private:
    std::coroutine_handle<promise_type> h_;
};

generator<int> fib(int n) {
    int a = 0, b = 1;
    for (int i = 0; i < n; ++i) {
        co_yield a;                      // hand out a, then suspend
        a = std::exchange(b, a + b);
    }
}

int main() {
    auto g = fib(10);
    while (g.next()) std::printf("%d ", g.value());   // 0 1 1 2 3 5 8 13 21 34
    std::printf("\n");
}
```

`fib` looks like an ordinary function returning `generator<int>`. What's special is `co_yield`: each time it executes, `fib` suspends and gives control back to `main`; when `main` calls `g.next()`, it continues from where it suspended, with the local variables `a`, `b` and `i` still there.

If a function can suspend and resume, its local variables can't live on the caller's stack. They are kept in a separately allocated piece of storage called the [[g:coroutine-state|coroutine state]] (often called the coroutine frame). C++ coroutines are **stackless**: they can only suspend in their own body, not inside an ordinary function they call.

Both `generator` and its `promise_type` are user-written. The language has no built-in task, generator or scheduler; it only specifies how the compiler rewrites a coroutine body into a sequence of calls on the promise. The details of `co_await` are in [[expr.await]], `co_yield` in [[expr.yield]], `co_return` in [[stmt.return.coroutine]], and library components such as `coroutine_handle` in [[support.coroutine]]; for a full introduction see [[topics/coroutines]]. Since C++23 the standard library provides a full-featured `std::generator` ([[coro.generator]]).

## Which functions are coroutines (¶1–¶2)

¶1 A function is a [[g:coroutine|coroutine]] if its function body contains a `co_return` statement, a `co_await` expression or a `co_yield` expression.

This is a purely syntactic test, unrelated to the return type, and invisible from the declaration. The caller just sees a function returning `generator<int>`; being a coroutine is an implementation detail. The test doesn't reach through lambdas: a `co_await` inside a lambda in the function body makes that lambda a coroutine, not the enclosing function.

¶1 also says a coroutine's parameter list can't end with a C-style `...`; the `...` of a pack expansion is not restricted (the standard example in ¶2). Other clauses rule out several more kinds of function:

- `main` ([[basic.start.main]]), constructors ([[class.ctor]]), destructors ([[class.dtor]]);
- functions whose return type contains a placeholder such as `auto` or `decltype(auto)` ([[dcl.spec.auto#18]]), because the promise type is found through the return type;
- non-template constexpr functions (including consteval functions). [[dcl.constexpr#3]] says a coroutine is not constexpr-suitable, and a non-template constexpr function must be constexpr-suitable. An instantiation of a constexpr function template that is a coroutine doesn't violate the rules, it just can't be called during constant evaluation; but Clang 23 rejects even such function templates outright.

```cpp title="not-coroutine.cpp" error
#include <coroutine>
struct r {
    struct promise_type {
        r get_return_object() { return {}; }
        std::suspend_never initial_suspend() noexcept { return {}; }
        std::suspend_never final_suspend() noexcept { return {}; }
        void return_value(int) { }
        void unhandled_exception() { }
    };
};
r g(int, ...) { co_return 1; }         // error: C-style varargs
r h() { return r{}; co_return 1; }     // error: a coroutine can't contain a return statement
auto k() { co_return 1; }              // error: placeholder return type
constexpr r c() { co_return 1; }       // error: a non-template constexpr function can't be a coroutine
```

## The promise type (¶3–¶4)

¶3 The [[g:promise-type|promise type]] of a coroutine is

```cpp
std::coroutine_traits<R, P1, ..., Pn>::promise_type
```

where `R` is the return type and `P1 … Pn` are the parameter types. For a non-static member function, the type of the object parameter, such as `C&` or `const C&` ([[dcl.fct]]), is added at the front. The promise type must be a class type.

The primary template of `std::coroutine_traits` simply takes `R::promise_type` ([[coroutine.traits]]), so the usual approach is the one above: nest a `promise_type` in the return type. When the return type can't be changed (say, to make functions returning `std::future<T>` coroutines), you can specialize `coroutine_traits`. The parameter types are template arguments too, so the same return type can choose a different promise depending on the parameters, e.g. a promise with an allocator when the first parameter is an allocator.

```cpp title="traits-specialize.cpp" error
#include <coroutine>
struct NP { int x; };
template<> struct std::coroutine_traits<NP, int> { using promise_type = int; };
NP g(int) { co_return; }     // error: the promise type int is not a class type
```

¶4 defines two sets of notation for what follows. `p_i` denotes the original parameters passed by the caller, and `q_i` denotes the copies of the parameters inside the coroutine (see ¶13). For an implicit object member function, `p_1` is the object parameter and `q_1` denotes `*this` itself: the object is not copied.

## What the compiler rewrites the body into (¶5)

¶5 A coroutine behaves as if the top-level cv-qualifiers were first removed from its parameter declarations and its function body were then replaced by the following **replacement body**:

```text
{
    promise-type promise promise-constructor-arguments ;
    try {
        co_await promise.initial_suspend() ;
        function-body
    } catch ( ... ) {
        if (!initial-await-resume-called)
            throw ;
        promise.unhandled_exception() ;
    }
final-suspend :
    co_await promise.final_suspend() ;
}
```

This skeleton determines most of a coroutine's behavior:

- `promise` is the coroutine's [[g:promise-object|promise object]]. ¶5.7 says that if the promise has a constructor callable with the parameter copies `(q_1, …, q_n)`, that constructor is used; otherwise it is default-constructed. This is how the promise can get at the coroutine's arguments, such as an allocator, a scheduler or a cancellation token.
- The `co_await` containing `initial_suspend()` is the **initial await expression**, and the one containing `final_suspend()` is the **final await expression**. Stopping at the former is being suspended at the **initial suspend point**; stopping at the latter, or exiting because `unhandled_exception()` threw (¶14), is being suspended at the **final suspend point** (¶5.8–¶5.9).
- *initial-await-resume-called* is set to `true` immediately before the evaluation of `await_resume` of the initial await expression. So exceptions thrown by `initial_suspend()` itself or its awaiter propagate directly to the caller and aren't given to `unhandled_exception`: the body hasn't started yet, and the caller should see the exception.
- `final-suspend` is an exposition-only label; `co_return` ends up jumping here ([[stmt.return.coroutine]]).

Matching the skeleton against the promise's members gives every decision you make when writing a coroutine type:

| Promise member | When it is called | Common choice |
|---|---|---|
| Constructor | After the parameters are copied | Default-constructed, or takes the parameters |
| `get_return_object()` | After the promise is constructed, before `initial_suspend` (¶7) | Construct the return object with `coroutine_handle::from_promise(*this)` |
| `initial_suspend()` | Before the body | `suspend_always` (lazy) or `suspend_never` (eager) |
| `yield_value(e)` | Each `co_yield e` | Store the value and suspend |
| `return_value(e)` / `return_void()` | `co_return e;` / `co_return;` or flowing off the end | Store the result |
| `unhandled_exception()` | The body throws an uncaught exception | Store it with `std::current_exception()`, or rethrow with `throw;` |
| `final_suspend()` | After the body ends | `suspend_always` (destroyed by the owner) or transfer to the awaiter; must not throw (¶15) |
| `await_transform(e)` (optional) | Each user-written `co_await e` | Rewrite the awaited object; not applied to the initial and final await expressions |

¶6 is a note: odr-using a non-reference parameter in a postcondition assertion of a coroutine is ill-formed ([[dcl.contract.func]]). An ordinary function can use a parameter in a postcondition by declaring it `const`; a coroutine can't, because the body uses a copy, and the original parameter no longer exists after the first suspension.

## get_return_object before initial_suspend (¶7)

¶7 The result of `promise.get_return_object()` is used to initialize the return value of the coroutine call. It is called before `initial_suspend`, and at most once.

The order can't be reversed. If `initial_suspend` doesn't suspend, the body runs immediately and may run to completion; if `final_suspend` doesn't suspend either, the coroutine state, promise included, has already been destroyed. The return object usually needs to hold a handle to the coroutine, which must be obtained before anything starts.

## Resumption (¶8)

¶8 A suspended coroutine is resumed through its handle's `resume()` or `operator()` ([[coroutine.handle]]); the evaluation that invoked it is called the **resumer**. When the coroutine suspends, control returns to the caller the first time, and to the resumer thereafter.

Invoking a resumption member on a coroutine that is not suspended is undefined behavior {{ub}}. This covers a running coroutine (e.g. calling `resume()` on its own handle inside the coroutine) and one that has finished and whose state has been destroyed. A coroutine stopped at the final suspend point is suspended, but [[coroutine.handle.resumption]] separately says resuming it is also UB; at that point `done()` is true.

## Parameters are copied into the coroutine state (¶13)

¶13 When a coroutine is invoked, the replacement body begins by creating a copy of each parameter. Let the original declared type of a parameter be cv `T`:

- ¶13.1 if `T` is a reference type, the copy is a reference of the same type bound to the same object;
- ¶13.2 otherwise, the copy is an automatic variable of type cv `T`, direct-initialized from an xvalue of type `T` referring to the original parameter. By-value parameters are therefore moved into the coroutine state.

Uses of a parameter's name in the body refer to the copy (Note 2). The copies are initialized before the promise is constructed, indeterminately sequenced with respect to each other; their lifetimes end immediately after the lifetime of the promise object ends. [[class.copy.elision]] ¶1.3 allows this copy to be elided as long as the program's meaning is unchanged apart from the construction and destruction of the copy.

The original parameters live where the caller set them up for this call; after the coroutine first suspends and the call returns, they are gone, while the coroutine body may resume much later, so copying is necessary. For a reference parameter only the reference is copied, which extends no lifetimes. Note 3 points out that resuming the coroutine after the referred-to entity's lifetime has ended is likely to result in undefined behavior:

```cpp run title="coro-dangling.cpp" ub
#include <coroutine>
#include <cstdio>
#include <string>
#include <utility>

struct lazy {
    struct promise_type {
        lazy get_return_object() { return lazy{std::coroutine_handle<promise_type>::from_promise(*this)}; }
        std::suspend_always initial_suspend() noexcept { return {}; }   // lazy: the body doesn't run at the call
        std::suspend_always final_suspend() noexcept { return {}; }
        void return_void() { }
        void unhandled_exception() { throw; }
    };
    std::coroutine_handle<promise_type> h;
    explicit lazy(std::coroutine_handle<promise_type> h) : h(h) { }
    lazy(lazy&& o) noexcept : h(std::exchange(o.h, {})) { }
    ~lazy() { if (h) h.destroy(); }
};

lazy print(const std::string& s) {        // the copy is still the same reference
    std::printf("%s\n", s.c_str());
    co_return;
}

int main() {
    lazy t = print(std::string(40, 'x')); // the temporary string is destroyed at the end of this full-expression
    t.h.resume();                          // UB: the body only runs now, and s dangles
}
```

In our tests AddressSanitizer reports `stack-use-after-scope`. Taking the parameter by value (`lazy print(std::string s)`) makes it safe. Borrowing types such as `std::string_view`, `std::span` and iterators are the same: they themselves are copied by value, but the data they point to isn't in the coroutine state.

`*this` of a member function coroutine isn't copied either (`q_1` is `*this`). The closure object of a lambda coroutine is the same: in `[x]() -> task<> { co_await …; use(x); }()`, the temporary closure is destroyed at the end of the full-expression, and reading `x` after resuming the coroutine is UB. Since C++23 you can take the closure by value with an explicit object parameter: `[x](this auto self) -> task<> { … }`; `self` is an ordinary by-value parameter and is moved into the coroutine state.

## Allocating the coroutine state (¶9–¶10)

¶9 An implementation may need to allocate storage for a coroutine; that storage is the coroutine state. It is obtained by calling a non-array allocation function ([[basic.stc.dynamic.allocation]]). The allocation function is first looked up in the scope of the promise type:

- ¶9.1 if found, overload resolution is first performed with `(size, p_1, …, p_n)`, passing the original parameters with their original cv; if there is no viable function, it is tried again with just `(size)`;
- ¶9.2 if not found, the global `operator new(size)` is used.

The wording says "may need". When the compiler can prove that the coroutine state doesn't outlive the caller, it can place it in the caller's stack frame and avoid the heap allocation; this is called **heap allocation elision** (HALO).

¶10 If the name `get_return_object_on_allocation_failure` is found in the scope of the promise type, allocation failure is no longer reported by an exception:

- the allocation function returns `nullptr` on failure; if a global allocation function is selected, `::operator new(size_t, nothrow_t)` is used instead;
- the allocation function used must be declared non-throwing;
- if the allocation function returns `nullptr`, the coroutine returns to the caller immediately, and the return value is the result of `T::get_return_object_on_allocation_failure()` (where `T` is the promise type). The promise is never constructed and the body never runs.

This gives environments that don't use exceptions a way to handle allocation failure. The promise below gets an arena from the coroutine's arguments and allocates the coroutine state in it:

```cpp run title="coro-alloc.cpp" ok
#include <coroutine>
#include <cstddef>
#include <cstdio>
#include <exception>

struct arena { char buf[1024]; std::size_t used = 0; };

struct job {
    struct promise_type {
        // ¶9.1: the extra arguments are the coroutine's original parameters (arena&, int)
        static void* operator new(std::size_t n, arena& a, int) noexcept {
            std::printf("arena alloc %zu bytes\n", n);
            if (a.used + n > sizeof a.buf) return nullptr;
            void* p = a.buf + a.used;
            a.used += n;
            return p;
        }
        // ¶12: deallocation only receives the address and size
        static void operator delete(void*, std::size_t n) noexcept { std::printf("free %zu bytes\n", n); }
        // ¶10: declaring this makes the allocation function signal failure with nullptr
        static job get_return_object_on_allocation_failure() { std::puts("allocation failed"); return job{nullptr}; }

        promise_type(arena&, int id) { std::printf("promise ctor sees id=%d\n", id); }  // ¶5.7

        job get_return_object() { return job{std::coroutine_handle<promise_type>::from_promise(*this)}; }
        std::suspend_never initial_suspend() noexcept { return {}; }
        std::suspend_never final_suspend() noexcept { return {}; }   // the coroutine state is destroyed automatically at the end
        void return_void() { }
        void unhandled_exception() { std::terminate(); }
    };
    std::coroutine_handle<promise_type> h;
    explicit job(std::coroutine_handle<promise_type> h) : h(h) { }
};

job work(arena&, int id) {
    std::printf("body runs, id=%d\n", id);
    co_return;
}

int main() {
    arena a;
    work(a, 7);
}
```

In our tests (Clang 23, arm64, `-O0`) it prints `arena alloc 32 bytes`, `promise ctor sees id=7`, `body runs, id=7`, `free 32 bytes` in that order. With `buf` changed to 16 bytes, the output becomes `arena alloc 32 bytes`, `allocation failed`, and neither the promise constructor nor the body runs. The size of the coroutine state is an implementation detail and varies with the optimization level.

Why does `operator new` receive the original parameters `p_i` while the promise constructor receives the copies `q_i`? Because allocation comes before copying: the copies are placed in the newly allocated storage and don't exist yet at allocation time. The promise is constructed after copying, when referring to the copies is safe, since the copies live as long as the coroutine.

## Destroying the coroutine state (¶11–¶12)

¶11 The coroutine state is destroyed in two cases:

1. control flows off the end of the coroutine, i.e. the final await expression doesn't suspend (`final_suspend()` returns an awaiter like `suspend_never`) and the replacement body finishes;
2. `destroy()` is called on a handle referring to it. This is treated as control leaving the function ([[stmt.dcl]]): live automatic variables (including the parameter copies and the promise object) are destroyed in reverse order of construction.

The storage is freed by calling a non-array deallocation function. Calling `destroy()` on a coroutine that is not suspended is undefined behavior {{ub}}.

This yields two ownership models for coroutine types, and you can only choose one:

- `final_suspend` returns `suspend_never`: the coroutine destroys itself at the end, after which the handle is immediately invalid, and `h.done()`, `h.destroy()` and `h.promise()` are all UB;
- `final_suspend` returns `suspend_always`: the coroutine stops at the final suspend point, and the owner must call `destroy()` or it leaks. The `generator` above uses this model.

¶12 The deallocation function is likewise looked up first in the promise type and then globally. If both forms exist, the one with two parameters `(void*, size_t)` is selected and passed the size of the block; otherwise the one with just a pointer parameter is selected. If no usual deallocation function is found, the program is ill-formed.

Unlike ¶9, the deallocation function doesn't receive the coroutine's parameters; the copies have already been destroyed by then. So when allocating in an arena, either the arena must be recoverable from the address, or the arena pointer must be stored at the start of the block during allocation.

## Flowing off the end and exceptions (¶14–¶15)

What happens when flowing off the end of the user-written body is decided by [[stmt.return.coroutine#3]]: if `promise.return_void()` can be called, it is equivalent to `co_return;`; otherwise the behavior is undefined {{ub}}. So in a coroutine whose promise only has `return_value` (such as `task<int>`), forgetting `co_return x;` on some path is UB rather than a compile error. Clang gives a `-Wreturn-type` warning for it:

```cpp title="flow-off.cpp" ub
#include <coroutine>
struct r {
    struct promise_type {
        r get_return_object() { return {}; }
        std::suspend_never initial_suspend() noexcept { return {}; }
        std::suspend_never final_suspend() noexcept { return {}; }
        void return_value(int) { }
        void unhandled_exception() { }
    };
};
r f(bool b) {
    if (b) co_return 1;
}              // with b false, control flows off the end: no return_void, UB
int main() { f(false); }
```

¶14 If `promise.unhandled_exception()` itself exits by throwing, the coroutine is considered suspended at the final suspend point, and the exception propagates to the caller or resumer. So writing `throw;` in `unhandled_exception` is a valid strategy: when the body of the `generator` above throws, the exception comes out of `h_.resume()` in `g.next()`, the coroutine stops at the final suspend point, and calling `destroy()` later in `~generator()` is still valid.

¶15 The whole expression `co_await promise.final_suspend()` must not be potentially-throwing ([[except.spec]]). This covers `final_suspend()` itself, the awaiter's `await_ready`, `await_suspend` and `await_resume`, and the awaiter's destructor. The final await expression is outside the `try` block, and an exception thrown there would have nowhere to be caught.

```cpp title="final-noexcept.cpp" error
#include <coroutine>
struct r {
    struct promise_type {
        r get_return_object() { return {}; }
        std::suspend_never initial_suspend() { return {}; }
        std::suspend_never final_suspend() { return {}; }   // missing noexcept
        void return_void() { }
        void unhandled_exception() { }
    };
};
r f() { co_return; }   // error: co_await promise.final_suspend() must not throw
```

## Example: a task awaiting another task

A `generator` is driven by an ordinary function. A task type instead lets one coroutine `co_await` another, and when the awaited coroutine finishes, control transfers straight back to the awaiter:

```cpp run title="task.cpp" ok
#include <coroutine>
#include <cstdio>
#include <exception>
#include <utility>

template<class T>
class task {
public:
    struct promise_type {
        T value{};
        std::exception_ptr error;
        std::coroutine_handle<> continuation = std::noop_coroutine();   // the awaiter

        task get_return_object() {
            return task{std::coroutine_handle<promise_type>::from_promise(*this)};
        }
        std::suspend_always initial_suspend() noexcept { return {}; }   // lazy start
        auto final_suspend() noexcept {
            struct final_awaiter {
                bool await_ready() noexcept { return false; }
                std::coroutine_handle<> await_suspend(std::coroutine_handle<promise_type> h) noexcept {
                    return h.promise().continuation;    // transfer back to the awaiter
                }
                void await_resume() noexcept { }
            };
            return final_awaiter{};
        }
        void return_value(T v) { value = std::move(v); }
        void unhandled_exception() { error = std::current_exception(); }
    };

    explicit task(std::coroutine_handle<promise_type> h) : h_(h) { }
    task(task&& o) noexcept : h_(std::exchange(o.h_, {})) { }
    ~task() { if (h_) h_.destroy(); }

    // makes task co_await-able ([expr.await])
    bool await_ready() const noexcept { return false; }
    std::coroutine_handle<> await_suspend(std::coroutine_handle<> awaiting) noexcept {
        h_.promise().continuation = awaiting;
        return h_;                                      // start the awaited task
    }
    T await_resume() {
        if (h_.promise().error) std::rethrow_exception(h_.promise().error);
        return std::move(h_.promise().value);
    }

    T run() {                 // drive synchronously from an ordinary function (all awaits here complete synchronously)
        h_.resume();
        return await_resume();
    }
private:
    std::coroutine_handle<promise_type> h_;
};

task<int> leaf(int x) { co_return x * 2; }

task<int> sum() {
    int a = co_await leaf(10);   // suspend sum and transfer to leaf; when leaf ends, transfer back to sum
    int b = co_await leaf(11);
    co_return a + b;
}

int main() {
    std::printf("%d\n", sum().run());   // 42
}
```

`sum().run()` resumes `sum`. `co_await leaf(10)` first calls `leaf`, which stops at its initial suspend point; `task::await_suspend` records `sum` as the continuation and returns `leaf`'s handle, which the compiler then resumes ([[expr.await#5]]). After `leaf` executes `co_return`, `final_awaiter` returns the continuation and control transfers back to `sum`. `sum`'s continuation is `noop_coroutine()`, so when `sum` ends, control returns to `run()`.

Returning a handle from `await_suspend` is called **symmetric transfer**. The compiler resumes the returned handle as a tail call, so switching back and forth between two coroutines doesn't make the stack grow deeper.

!!! impl "How Clang implements coroutines"
    - LLVM splits a coroutine into three functions. The ramp function is the one callers see: it allocates the coroutine state, copies the parameters, constructs the promise, calls `get_return_object` and `initial_suspend`, and returns at the first suspension. The resume and destroy functions jump to the right place according to the suspend point index saved in the state.
    - The coroutine state begins with two function pointers, resume and destroy, followed by the promise object, then the local variables that live across suspend points, the parameter copies and the suspend point index. GCC uses the same convention. That's why `coroutine_handle<>` can resume and destroy a coroutine without knowing the promise type, and why `from_promise` and `promise()` convert between the two addresses with a fixed offset.
    - When optimizing (e.g. `-O2`), if the coroutine state doesn't escape the caller, for example when the caller creates a generator and uses it up and destroys it within the same function, Clang eliminates `operator new` and `operator delete` and puts the state in the caller's stack frame; this is the HALO mentioned earlier.

## History

!!! history
    - Coroutines were first published as the Coroutines TS (ISO/IEC TS 22277:2017), implemented for years in MSVC and Clang under `std::experimental`, and merged into C++20 by [[P0912R5]].
    - C++23 added `std::generator` to the standard library ([[coro.generator]]).
    - C++26 introduced contracts and correspondingly forbade odr-using non-reference parameters in coroutine postconditions (¶6); `std::execution` gained the coroutine task type `std::execution::task` ([[exec.task]]).

## Common misconceptions

!!! pitfall "You can tell from the declaration whether a function is a coroutine"
    You can't. Being a coroutine is a property of the function body. The same declaration `task<int> f(int);` can have a definition that is a coroutine or an ordinary function returning a ready-made `task`.

!!! pitfall "const reference parameters are safe in coroutines too"
    A temporary bound to a reference parameter lives only until the end of the full-expression containing the call ([[class.temporary]]). By the time a lazy coroutine resumes, that temporary is long gone. Coroutines that suspend should take parameters by value.

!!! pitfall "The compiler rejects a missing co_return"
    If the promise has no `return_void`, flowing off the end of the body is UB, and the compiler only warns. Consider `-Werror=return-type`.

## Questions

!!! question "Question 1"
    In what order do things happen when the coroutine below is called?
    ```cpp
    task<int> f(Widget w);   // promise_type has a constructor promise_type(Widget&)
    ```

<details markdown="1">
<summary>Answer</summary>

1. The caller constructs the argument `w`, the original parameter;
2. The allocation function is called to obtain the coroutine state (¶9; if the promise has `operator new(size_t, Widget&)`, the original parameter is passed as the extra argument);
3. The original `w` is move-constructed into the coroutine state from an xvalue referring to it (¶13.2);
4. The promise is constructed from the parameter copies; `promise_type(Widget&)` is viable, so it gets the copy as its argument (¶5.7);
5. `get_return_object()` is called, and its result initializes the `task<int>` returned to the caller (¶7);
6. `co_await promise.initial_suspend()` is evaluated; if it suspends, control returns to the caller;
7. The caller destroys the original parameter `w` at the end of the full-expression; the copy in the coroutine state is unaffected.
</details>

!!! question "Question 2"
    What happens if a coroutine calls `h.resume()` on its own handle inside its body? And if `final_suspend` returns `suspend_never`, what about calling `h.done()` after the coroutine ends?

<details markdown="1">
<summary>Answer</summary>

Both are undefined behavior. The former invokes a resumption member on a coroutine that is running, not suspended (¶8). In the latter, the coroutine state has already been destroyed by flowing off the end (¶11), the handle no longer refers to any coroutine, and [[coroutine.handle.observers]] requires the handle to refer to a suspended coroutine when `done()` is called.
</details>
