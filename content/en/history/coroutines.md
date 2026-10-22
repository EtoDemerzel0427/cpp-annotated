---
title: "Coroutines: from Simula to C++20/26"
summary: Why C++20 chose stackless coroutines, why the keywords have a co_ prefix, why allocating the frame is only something an implementation "may need" to do, and why the standard library's coroutine types only arrived in C++23 and C++26.
tags: coroutines, history, Coroutines TS, co_await
updated: 2026-10-19
---

!!! tldr
    - C++20 coroutines are stackless: suspending saves only the coroutine's own frame. The language only specifies how a function body is rewritten into a state machine; the return type is left entirely to libraries.
    - Stackful coroutines (with their own stack, able to suspend from arbitrarily deep calls) and stackless coroutines competed in the committee for years; in the end the performance argument won.
    - The keywords are `co_await`, `co_yield` and `co_return` because `yield` is too common a name in existing code; for the same reason a coroutine cannot use `return`.
    - The standard only says an implementation may need to allocate storage for the frame: whether the allocation can be elided is left to the optimizer, which is how the 2018 dispute with Core Coroutines was settled.
    - C++20 provided no ready-made coroutine types; `std::generator` arrived only in C++23, and `std::execution::task` for asynchronous code only in C++26.

Before reading this page it helps to know what the three roles of a coroutine ([[g:promise-type|the promise type]], the awaiter and `coroutine_handle`) are each responsible for; see [[topics/coroutines]] first.

## What coroutines are, and why early C++ had none

An ordinary function is always entered at the top and left at the bottom. A **coroutine** can give up control partway and continue next time from where it left off. The term comes from Melvin Conway (the 1963 paper *Design of a Separable Transition-Diagram Compiler*), who used it to make a compiler's lexical analysis and parsing run alternately: one side produces a word and the other consumes it immediately, without first writing out all the intermediate results. Simula 67 made it a language mechanism: an object could `detach` to give up control and later be `resume`d.

C++ had coroutines from the start, but as a library. The earliest important library of C with Classes was a task library supporting coroutine-style programming, and it was very efficient on the hardware of the time. But it was implemented with low-level stack switching and was hard to port to new architectures such as SPARC; after 1989 most implementations stopped providing it (HOPL IV §1.1). So C++98 had no coroutines.

This early history already contains the two core questions of the later debate: are coroutines a library or a language feature, and does suspending switch the whole stack?

## Two kinds of tricks outside the standard

Between C++98 and C++17, programmers who needed coroutines had only tricks outside the language. They correspond exactly to the two approaches later seen in the committee.

### Stackless: jump back with switch

A `switch`'s `case` labels can appear inside a loop body (which is also what Duff's device uses). Store the resumption point in a state variable, jump back to it with `switch` on each call, and you have a crude coroutine. Simon Tatham's article *Coroutines in C* wrapped this up in macros, and Boost.Asio's `asio::coroutine` (whose space overhead is a single `int`) is implemented the same way. Here it is without the macros:

```cpp run title="switch_coroutine.cpp" ok
#include <cstdio>

// jump back to where the last call returned with switch; the state lives in the object
struct Counter {
    int state = 0;
    int i = 0;
    // each call produces the next value; returns -1 when exhausted
    int next() {
        switch (state) {
        case 0:
            for (i = 0; i < 3; ++i) {
                state = 1;
                return i;          // equivalent to yield i
        case 1:;                   // the next call continues here
            }
        }
        state = 2;
        return -1;
    }
};

int main() {
    Counter c;
    for (int v; (v = c.next()) != -1;)
        std::printf("%d\n", v);    // 0 1 2
}
```

This already has all the elements of a stackless coroutine: variables still needed across a suspension point (`i`) must live in the object, not on the stack; suspending means recording the position and returning; resuming means calling again and jumping back to the recorded position. The difference is that the state object here is written by hand, and local variables cannot be declared freely (a `switch` cannot jump past a declaration with an initializer). C++20 has the compiler generate this object; it is the [[g:coroutine-state|coroutine frame]].

### Stackful: switch the whole stack

The other kind of trick gives each coroutine its own stack, and on suspension saves registers and switches the stack pointer. These are **stackful** coroutines, often also called fibers. The advantage is that they can suspend from arbitrarily deeply nested calls, and the called functions don't need to know they are running in a coroutine; the cost is that each coroutine needs a reserved stack, and switching depends on platform-specific assembly. Boost.Context and Boost.Coroutine (added to Boost in 2012–2013, later followed by Coroutine2) represent this approach:

```cpp
// a stackful coroutine with Boost.Coroutine2 (sketch; needs Boost, no verdict)
using coro_t = boost::coroutines2::coroutine<int>;

coro_t::pull_type fib([](coro_t::push_type& sink) {
    int a = 0, b = 1;
    for (int i = 0; i < 8; ++i) {
        sink(a);                 // suspend, handing a to the consumer
        int next = a + b;
        a = b;
        b = next;
    }
});

for (int v : fib) std::cout << v << ' ';
```

Note that `sink(a)` is an ordinary function call. It can appear in a function at any depth below the lambda, which stackless coroutines cannot do.

## Two approaches enter the committee (2012–2014)

### A stackless language feature and a stackful library

Both approaches were submitted to the committee at almost the same time. Microsoft's [[N3328]] (2012) proposed resumable functions: mark a function `resumable` and use `await` inside it to wait for a future, turning callback chains back into sequential code, much like the async/await C# was introducing at the time. [[N3708]] (2013) by Kowalke and Goodspeed proposed adding Boost.Coroutine to the standard library, with no language changes at all.

<div class="compare" markdown="1">

```cpp
// N3328 (2012), not standardized
future<int> f(stream str) resumable
{
    shared_ptr<char> buf = ...;
    int n = await str.read(512, buf);
    return n + 11;
}
```

```cpp
// C++20
task<int> f(stream str)
{
    shared_ptr<char> buf = ...;
    int n = co_await str.read(512, buf);
    co_return n + 11;
}
```

</div>

The difference can be summed up as: the await design was stackless and language-based; the Boost design was stackful and library-based. A stackless coroutine can only suspend in its own function body, not in functions it calls, so suspending saves only one frame. Stroustrup considered this a huge performance advantage (HOPL IV §9.3.2).

### Attempts at unification, and the performance argument

The committee's concurrency study group asked both sides to fit into a single conceptual framework ([[N4232]] records that discussion). Three ideas kept recurring over the next few years (HOPL IV §9.3.2):

1. Represent coroutines as a kind of lambda, so that they enter the type system naturally without the compiler doing much behind the scenes (for example [[N4244]] *Resumable Lambdas*);
2. Provide a common interface for stackful coroutines, stackless coroutines and even threads;
3. Get optimal performance for the simplest and most common cases, such as generators and pipelines; this requires stackless coroutines with compiler support, and an interface that does not compromise to accommodate advanced uses.

You cannot have all three. Stroustrup himself preferred a common interface, but the performance argument won in the end (HOPL IV §9.3.2).

### From an annotation to the function body deciding

In 2014 Gor Nishanov took over Microsoft's proposal and wrote [[N4134]] *Resumable Functions v.2*. It explicitly chose a stackless implementation, introduced the model of promises and `coroutine_traits`, and dropped the `resumable` annotation: whether a function is a coroutine depends only on whether its body has suspension points.

Today's [[dcl.fct.def.coroutine#1]] still defines it this way: if `co_await`, `co_yield` or `co_return` appears in the function body, it is a coroutine, and nothing in the declaration shows it. Callers don't need to know either, because a coroutine, like an ordinary function, returns an object of an ordinary type.

## Why the keywords have a co_ prefix

N4134 used `await` and `yield`. But making `yield` a keyword would break a lot of code: it is a common variable and function name in finance (yield rates) and agriculture (crop yield). EWG's answer was a firm no ([[P0071R0]]).

There were several candidate solutions: soft keywords (keywords only in certain contexts), functions in `std`, a different, obscure word, or a prefix. In the end the committee chose the `co_` prefix and replaced all three keywords, including `return`. HOPL IV explains that a coroutine's result has to be wrapped in an object the caller can wait on (such as a future), so `return` means something different in a coroutine than in an ordinary function, and also needed a different word.

This decision left two traces in today's rules. First, `yield` and `await` are still ordinary identifiers, while `co_await` and the others have been keywords since C++20 ([[lex.key]]; [[diff.cpp17.lex]] records the incompatibility):

<div class="compare" markdown="1">

```cpp run ok
double yield = 0.035;  // yield rate
int await(int x) { return x; }
int main() {
    return await(int(yield));
}
```

```cpp error
// valid in C++17, invalid since C++20
int co_await = 0;  // error: keyword
```

</div>

Second, a `return` statement cannot appear in a coroutine ([[stmt.return.coroutine#1]]), even in a discarded `if constexpr` branch. Ordinary functions use `return`, coroutines use `co_return`, and the same function body cannot mix them.

## Where the frame lives: the TS versus Core Coroutines

### A Technical Specification first

In 2016 the committee decided that coroutines would first be published as a Technical Specification (TS, a document that does not enter the standard proper and lets implementations try things out); it was published as the Coroutines TS in 2017. It did not go straight into the standard partly because many people still preferred the more general stackful coroutines, and partly because some hoped to find a design that covered both (HOPL IV §6.3). By 2018, both MSVC and Clang had implementations of the TS.

### Google's objections

In 2018, as the TS was about to be merged into C++20, authors from Google, after evaluating whether to adopt it internally, raised a series of problems ([[P0973R0]]). The most important: the frame usually has to be allocated on the heap, which violates the zero-overhead principle; parameters passed by `const&` may dangle after suspension; not being able to write `return` adds migration cost; and the name `co_await` is biased towards one use, asynchrony.

They were especially concerned with a scenario the TS authors discussed less: in environments with exceptions disabled, using coroutines instead of macros to propagate errors in return values like `expected<T>`. For that use, a heap allocation that might happen on every call is unacceptable.

### Two answers

The TS side's answer was HALO (Heap Allocation eLision Optimization, [[P0981R0]]): in the important cases, the optimizer can prove that the frame's lifetime does not exceed the caller's, and allocates it in the caller's frame, so the heap allocation disappears.

The Google side proposed a different design, Core Coroutines ([[P1063R0]]): expose the coroutine frame as an ordinary object which, like a lambda's closure object, has a type and a `sizeof`, and let the caller decide where to put it, guaranteeing through the type system that nothing is allocated. It also used an operator-like notation in place of `co_await`:

```cpp
// the unwrap operator proposed in P1063R0 (2018); never standardized, no verdict
optional<string> f();
string s = [<-] f();
```

### Why the TS won

The key is when the frame's size is known. A coroutine frame is essentially a stack frame, holding the local variables and temporaries that live across suspension points. Its size is only determined after the optimizer has run: the optimizer may remove variables and make it smaller, or add temporaries and make it bigger ([[P1492R0]], [[P1342R0]]).

| | Core Coroutines (early split) | Coroutines TS (late split) |
|---|---|---|
| What the frame is | A user-visible type with a `sizeof` | Private to the compiler, accessed indirectly through `coroutine_handle` |
| Frame size | Must be fixed by the front end before optimization; only a conservative estimate | Computed after optimization; usually smaller |
| Guarantee of no allocation | Guaranteed by the type system | No guarantee; up to the optimizer |
| Impact on compilers | The front end needs information only available after optimization | Consistent with existing compiler structure |

All mainstream optimizing compilers rely on one premise: a function's activation record is private to the implementation. Making it a complete type whose size is known early would mean feeding the optimizer's information back to the front end, which existing compilers cannot do ([[P1492R0]]). Besides, all three competing proposals were stackless, with small differences in notation, and the TS already had years of production use and two compiler implementations. In February 2019 the TS was merged into C++20 essentially as it was ([[P0912R5]]); the TS's `for co_await` loop was not merged.

## What it left in today's rules

| Today's rule | Which decision it came from | Clause |
|---|---|---|
| Whether a function is a coroutine depends only on its body; there is no marker in the declaration | N4134 dropped `resumable` | [[dcl.fct.def.coroutine#1]] |
| Keywords have the `co_` prefix; `yield` and `await` are still ordinary identifiers | Don't break code using `yield` as a name | [[lex.key]] |
| `return` must not appear in a coroutine | A coroutine's return has different semantics | [[stmt.return.coroutine#1]] |
| Storage for the frame "may need" to be allocated; the allocation function is looked up in the promise type first | The TS's compiler-private frame + HALO | [[dcl.fct.def.coroutine#9]] |
| The allocation function can see the coroutine's parameters | Parameter preview ([[P0914R1]]) | [[dcl.fct.def.coroutine#9]] |
| `await_suspend` can return a `coroutine_handle` | Symmetric transfer ([[P0913R1]]) | [[expr.await#5]] |
| Range-based `for` has no `co_await` form | Excluded at the merge | [[stmt.ranged]] |
| A coroutine cannot be a constexpr function | Not supported by the TS, still not lifted | [[dcl.constexpr#3]] |

### Allocation: may, not shall

[[dcl.fct.def.coroutine#9]] says an implementation may need to allocate additional storage for a coroutine. That "may" leaves room for HALO to elide the allocation, but the wording never guarantees the elision happens. The point P0973R0 made still holds today: a programmer cannot confirm at the language level that a given call does not allocate.

In compensation, the wording gives library authors ways to control allocation: the allocation function is looked up first in the scope of the promise type, and the coroutine's parameters are first tried as extra arguments to it (item 9.1), so a caller can pass in an allocator through the parameters; if the promise type provides `get_return_object_on_allocation_failure`, allocation uses the non-throwing form instead ([[dcl.fct.def.coroutine#10]]).

### Symmetric transfer

Originally, one coroutine could only resume another by calling `resume()` inside `await_suspend`. Each time, the call chain grew one level deeper on the thread's stack, and many `co_await`s that completed synchronously could overflow the stack. [[P0913R1]] allows `await_suspend` to return a `coroutine_handle`, which the implementation then resumes ([[expr.await#5]], item 5.1.1). An implementation can make this step a tail call, so the stack no longer grows.

The minimal task type below demonstrates both points: the promise takes over allocation of the frame, and `final_suspend` uses symmetric transfer to hand control straight back to the awaiter.

```cpp run title="task_halo.cpp" ok
#include <coroutine>
#include <cstddef>
#include <cstdio>
#include <exception>
#include <new>
#include <utility>

struct task {
    struct promise_type {
        int value = 0;
        std::coroutine_handle<> continuation = std::noop_coroutine();

        // the promise takes over frame allocation ([dcl.fct.def.coroutine]/9)
        static void* operator new(std::size_t n) {
            std::printf("allocate frame: %zu bytes\n", n);
            return ::operator new(n);
        }
        static void operator delete(void* p, std::size_t n) {
            ::operator delete(p, n);
        }

        task get_return_object() {
            return task{std::coroutine_handle<promise_type>::from_promise(*this)};
        }
        std::suspend_always initial_suspend() noexcept { return {}; }  // lazy start
        auto final_suspend() noexcept {
            struct awaiter {
                bool await_ready() noexcept { return false; }
                // symmetric transfer: return the next coroutine to resume ([expr.await]/5.1.1)
                std::coroutine_handle<> await_suspend(
                    std::coroutine_handle<promise_type> h) noexcept {
                    return h.promise().continuation;
                }
                void await_resume() noexcept {}
            };
            return awaiter{};
        }
        void return_value(int v) { value = v; }
        void unhandled_exception() { std::terminate(); }
    };

    // task itself is awaitable: when co_awaited, record the continuation and switch to it
    bool await_ready() const noexcept { return false; }
    std::coroutine_handle<> await_suspend(std::coroutine_handle<> caller) noexcept {
        h.promise().continuation = caller;
        return h;
    }
    int await_resume() { return h.promise().value; }

    explicit task(std::coroutine_handle<promise_type> h) : h(h) {}
    task(task&& o) noexcept : h(std::exchange(o.h, {})) {}
    ~task() { if (h) h.destroy(); }

    std::coroutine_handle<promise_type> h;
};

task answer() { co_return 42; }

task twice() {
    int x = co_await answer();
    co_return 2 * x;
}

int main() {
    task t = twice();
    t.h.resume();                                 // start the outer coroutine
    std::printf("%d\n", t.h.promise().value);     // 84
}
```

!!! impl "Observing HALO once"
    Compiled with Clang 23 at `-O0`, this program prints two `allocate frame` lines (64 and 40 bytes); at `-O2` it prints only one: the frame of the inner `answer()` has been folded into the outer frame and the allocation elided. Both the frame sizes and whether the allocation is elided depend on the implementation and optimization level, and the standard guarantees neither; this was exactly the focus of the 2018 dispute.

## The library came late

C++20 provides only the low-level facilities in `<coroutine>` ([[support.coroutine]]): `coroutine_traits`, `coroutine_handle`, `noop_coroutine`, `suspend_always` and `suspend_never`. There is no coroutine type that can be used directly as a return type, because there wasn't time to get one ready for C++20 (HOPL IV §9.3). C++20 users had to write the few dozen lines of `task` above themselves, or use third-party libraries such as cppcoro or Folly.

This is a direct consequence of the TS's design approach: the language only specifies the rewriting protocol and leaves return types to libraries, and library design, especially scheduling, cancellation and allocators, needs a consensus of its own.

### C++23: std::generator

Generators landed first. [[P2502R2]]'s `std::generator` ([[coro.generator]]) went into C++23. It is also a range view, so it can be piped straight into range adaptors, and `co_yield std::ranges::elements_of(...)` recursively yields the elements of another generator.

```cpp run title="generator.cpp"
#include <generator>
#include <iostream>

std::generator<int> fibonacci() {
    int a = 0, b = 1;
    while (true) {
        co_yield a;
        int next = a + b;
        a = b;
        b = next;
    }
}

int main() {
    int n = 0;
    for (int v : fibonacci()) {
        if (++n > 8) break;
        std::cout << v << ' ';     // 0 1 1 2 3 5 8 13
    }
    std::cout << '\n';
}
```

The libc++ we test with does not have a `<generator>` header yet; this example is written according to the standard and has not been compiled locally, so it has no verdict.

### C++26: std::execution::task

A task type for asynchronous code only arrived in C++26, tied to the sender/receiver model of `std::execution` ([[P3552R3]], [[exec.task]]). There were still a fair number of objections when it was accepted ([[P3801R0]]), including possible stack overflow in iterative code and surprising parameter lifetimes, in the same line as the problems P0973R0 raised in 2018.

Counting from N3328 in 2012, it took more than ten years for asynchronous coroutines to get their first ready-made return type in the standard library.

## Work still in progress

Several problems that kept coming up before 2019 can still be found in today's proposals:

- **Stackful coroutines.** The Kowalke and Goodspeed approach evolved into [[P0876R24]] *fiber_context*, which proposes a minimal stack-switching API without a scheduler, as a building block for stackful coroutines and user-space threads; it is still under review.
- **constexpr coroutines.** [[P3367R5]] proposes allowing coroutines to run during constant evaluation; because of concerns about implementation cost, its target has moved from C++26 to C++29. The current draft still specifies that a coroutine is not a constexpr-suitable function ([[dcl.constexpr#3]]).
- **Frame allocation.** Frame allocation does not take `std::align_val_t` into account, so an over-aligned frame may be misaligned; [[P2014R2]] proposes a fix, not yet adopted in the current draft. [[P2477R3]] proposes giving programmers explicit control over HALO, continuing the concerns of Core Coroutines.
- **Relaxing the promise protocol.** C++20 says a promise type cannot have both `return_void` and `return_value`. [[P3950R0]] removes that restriction (according to [[P4282R1]], it has been adopted); the current draft instead decides what happens when flowing off the end of the body by whether overload resolution for `p.return_void()` succeeds ([[stmt.return.coroutine#3]]).

## Timeline

| Date | Event |
|---|---|
| 1963 | Conway publishes the coroutine paper; in 1967 Simula 67 supports coroutines with `detach`/`resume` |
| 1980s | The C with Classes task library; abandoned by most implementations after 1989 because it was hard to port |
| 2000–2013 | Outside the standard: the `switch` macro trick, Asio stackless coroutines, Boost.Coroutine stackful coroutines |
| 2012–2013 | Two proposals: a stackless language feature ([[N3328]]) and a stackful library ([[N3708]]) |
| 2014 | [[N4134]]: stackless chosen, `resumable` annotation dropped |
| 2015 | Keywords settled as `co_await`, `co_yield`, `co_return` ([[P0071R0]]) |
| 2017 | Coroutines TS published |
| 2018 | Google's objections ([[P0973R0]]), HALO ([[P0981R0]]), Core Coroutines ([[P1063R0]]); symmetric transfer merged into the TS |
| 2019-02 | TS merged into C++20 ([[P0912R5]]) |
| 2022 | `std::generator` enters C++23 ([[P2502R2]]) |
| 2025 | `std::execution::task` enters C++26 ([[P3552R3]]) |

## References

- Bjarne Stroustrup, *Thriving in a Crowded and Changing World: C++ 2006–2020*, HOPL IV (2020): §1.1 (the task library), §6.3 (the TS decision), §9.3.2 (coroutines).
- Melvin E. Conway, *Design of a Separable Transition-Diagram Compiler*, CACM 6(7), 1963; Knuth, *The Art of Computer Programming* Vol. 1, §1.4.2.
- Simon Tatham, [*Coroutines in C*](https://www.chiark.greenend.org.uk/~sgtatham/coroutines.html); Boost.Asio documentation, [the `coroutine` class](https://www.boost.org/doc/libs/1_86_0/doc/html/boost_asio/reference/coroutine.html).
- The two approaches: [[N3328]], [[N3708]], [[N4232]], [[N4134]].
- Keywords: [[P0071R0]] *Coroutines: Keyword alternatives*.
- The debate before C++20: [[P0973R0]], [[P0981R0]], [[P1063R0]], [[P1342R0]], [[P1492R0]], [[P1493R0]], [[P0912R5]].
- Botond Ballo's trip reports on the 2018 Jacksonville, Rapperswil and San Diego meetings and the 2019 Kona meeting (botondballo.wordpress.com).
- Lewis Baker, [*C++ Coroutines: Understanding operator co_await*](https://lewissbaker.github.io/2017/11/17/understanding-operator-co-await) and the other articles in the series, among the most frequently cited material for understanding this protocol.
- Standard library: [[P2502R2]], [[P3552R3]], [[P3801R0]].
