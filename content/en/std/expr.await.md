---
title: The co_await expression
summary: How a co_await expression gets an awaiter from its operand, then uses the results of await_ready, await_suspend and await_resume to decide whether to suspend, where control goes, and what value it yields; and where it may appear.
updated: 2026-10-19
---

!!! tldr
    - `co_await e` first turns `e` into an awaiter object: if the promise has `await_transform`, that is called first, then `operator co_await` is looked for.
    - Then the awaiter's three members are called in turn: if `await_ready()` is true, there is no suspension; otherwise `await_suspend(h)` is called, and its return type (`void`, `bool`, `coroutine_handle`) decides who gets control; after resumption, the result of `await_resume()` is the value of the whole expression.
    - The coroutine already counts as suspended before `await_suspend` is called, so `await_suspend` may hand the handle to another thread to resume.
    - When `await_suspend` returns the handle of another coroutine, that coroutine is resumed directly (symmetric transfer); implementations can make this a tail call, so long chains of awaits don't exhaust the stack.
    - `co_await` cannot appear in a `catch` block, a default argument, the initializer of a static local variable, or a contract predicate.

{{c++20}} A function whose body contains `co_await`, `co_yield` or `co_return` is a **coroutine** ([[g:coroutine]]), see [[dcl.fct.def.coroutine]]. A coroutine can pause partway through, give control back to its caller, and later continue from where it paused. Being a coroutine is a property of the function definition; callers can't tell from the declaration.

Every coroutine has an associated **promise object** ([[g:promise-object]]), whose type is determined by the coroutine's return type and is used to customize the coroutine's behavior. A suspended coroutine is designated by a `std::coroutine_handle`; calling `resume()` on the handle makes it continue ([[coroutine.handle]]).

`co_await` is the expression that makes a coroutine pause. Its behavior is almost entirely determined by library code: the standard only specifies a fixed procedure that calls user-provided functions at a few points.

## A minimal example

```cpp run ok
#include <coroutine>
#include <cstdio>

struct task {
  struct promise_type {
    task get_return_object() { return {}; }
    std::suspend_never initial_suspend() noexcept { return {}; }
    std::suspend_never final_suspend() noexcept { return {}; }
    void return_void() {}
    void unhandled_exception() {}
  };
};

struct ready {
  int v;
  bool await_ready() const noexcept { return true; }       // already ready: don't suspend
  void await_suspend(std::coroutine_handle<>) noexcept {}  // never called
  int await_resume() const noexcept { return v; }          // result of co_await
};

struct maybe {
  bool await_ready() const noexcept { return false; }
  bool await_suspend(std::coroutine_handle<>) noexcept {
    return false;                                           // changed its mind: resume immediately
  }
  const char* await_resume() const noexcept { return "resumed immediately"; }
};

task co() {
  int x = co_await ready{42};
  std::printf("%d\n", x);
  std::printf("%s\n", co_await maybe{});
}

int main() { co(); }
```

The program prints `42` and `resumed immediately`. `task::promise_type` is the promise type of the coroutine `co`; `ready` and `maybe` are **awaiters**, that is, objects that provide the three members `await_ready`, `await_suspend` and `await_resume`. The standard library's `std::suspend_always` and `std::suspend_never` are the two simplest awaiters: their `await_ready` returns `false` and `true` respectively, and the other two functions do nothing.

¶1 The grammar of an *await-expression* is `co_await cast-expression`, so `co_await` has the same precedence as the other unary operators: `co_await a + b` is `(co_await a) + b`.

## Getting the awaiter from the operand (¶3.1–¶3.4)

The `x` in `co_await x` isn't necessarily an awaiter itself. ¶3 defines a series of auxiliary entities, in this order:

1. ¶3.1 *p* is the promise object of the enclosing coroutine, and `P` is its type.
2. ¶3.2 The name `await_transform` is looked up in the scope of `P`. If any declaration is found, *a* is `p.await_transform(x)`; otherwise *a* is `x`.
3. ¶3.3 With *a* as the argument, overload resolution is performed for `operator co_await` as for any other overloadable unary operator ([[over.match.oper]]). If it is ambiguous, the program is ill-formed; if there is no viable function, *o* is *a*; otherwise *o* is a call to the selected function.
4. ¶3.4 If *o* is a prvalue, temporary materialization is applied. *e* is an lvalue referring to the result, that is, the awaiter. The three calls that follow all act on the same object *e*.

```cpp run ok
#include <coroutine>
#include <cstdio>

struct awaiter_int {
  int v;
  bool await_ready() const noexcept { return true; }
  void await_suspend(std::coroutine_handle<>) noexcept {}
  int await_resume() const noexcept { return v; }
};

struct Seconds { int n; };
awaiter_int operator co_await(Seconds s) { return {s.n * 1000}; }   // step 3

struct task {
  struct promise_type {
    task get_return_object() { return {}; }
    std::suspend_never initial_suspend() noexcept { return {}; }
    std::suspend_never final_suspend() noexcept { return {}; }
    void return_void() {}
    void unhandled_exception() {}
    Seconds await_transform(int n) { return {n}; }                  // step 2
  };
};

task co() {
  int ms = co_await 3;   // a = p.await_transform(3)   → Seconds{3}
                         // o = operator co_await(a)    → awaiter_int{3000}
  std::printf("%d\n", ms);
}

int main() { co(); }
```

Step 2 is a name lookup, not a check of whether the call works. Once the promise declares `await_transform`, every user-written `co_await x` is rewritten to `p.await_transform(x)`; if no overload accepts `x`, compilation simply fails, with no fallback to no transformation. In the example above, writing `co_await Seconds{1}` fails, because the only `await_transform` accepts only `int`. A promise type can use this as an allow-list for what may be awaited in the coroutine body. C++23's `std::generator` declares `await_transform` as deleted ([[coro.generator.promise]]), so `co_await` cannot be used in a generator.

The `co_await` expressions implicitly produced by `co_yield`, the initial suspend and the final suspend don't go through step 2. Their operands are `p.yield_value(v)`, `p.initial_suspend()` and `p.final_suspend()`, which the promise controls already.

Step 4 means the awaiter is a real temporary object. It is destroyed at the end of the full-expression containing the `co_await`, and that full-expression spans the suspension, so the awaiter stays alive while the coroutine is suspended and, like local variables that live across the suspension, is stored in the coroutine state ([[g:coroutine-state]]). The awaiter can therefore hand `this` to someone else in `await_suspend`, for example so that the I/O completion writes the result into its members, which `await_resume` then reads.

## The three member functions and the order of evaluation (¶3.5–¶5)

¶3.5–¶3.8 define the expressions to be called: *h* is a `std::coroutine_handle<P>` referring to the enclosing coroutine; *await-ready* is `e.await_ready()`, contextually converted to `bool`; *await-suspend* is `e.await_suspend(h)`, whose type must be `void`, `bool` or some `std::coroutine_handle<Z>`; *await-resume* is `e.await_resume()`.

All three are written as member function calls; there is no non-member form. The parameter of `await_suspend` is usually written as `std::coroutine_handle<>`, implicitly converted from `coroutine_handle<P>`; it can also be written as `coroutine_handle<P>` to get access to the promise.

¶4 The whole `co_await` expression has the same type and value category as `await_resume()`: if it returns `int`, it is an `int` prvalue; if it returns `T&`, it is an lvalue; if it returns `void`, it is a `void` expression.

¶5 Evaluation first evaluates *o*, then `await_ready()`. The whole procedure can be written as the following pseudocode (this code isn't in the standard):

```text
if (!e.await_ready()) {
    <the coroutine is considered suspended>
    depending on the return type of await_suspend(h):
      coroutine_handle  → call it, then call .resume() on the returned handle
      bool              → call it; if it returns false, resume the current coroutine immediately
      void              → call it, then return to the caller or resumer
    <continue from here after resumption>
}
result = e.await_resume();
```

### Suspension (¶5.1)

¶5.1 When `await_ready()` is `false`, the coroutine is considered suspended, and this happens before `await_suspend` is called. So inside `await_suspend`, another thread may already resume this coroutine through `h` without violating the rule that resuming a coroutine that isn't suspended is UB ([[dcl.fct.def.coroutine#8]]).

What follows depends on the return type of `await_suspend`, in three cases:

- ¶5.1.1 It returns `std::coroutine_handle<Z>`: it is called, then `.resume()` is called on the returned handle. This is called **symmetric transfer**, see the next section. Note 1 points out that any number of coroutines can be resumed in succession this way, with control eventually returning to the caller or resumer of the current coroutine.
- ¶5.1.2 It returns `bool`: it is called; if the result is `false`, the current coroutine is resumed immediately and `await_resume` follows; if `true`, it stays suspended. The use case is an `await_suspend` that finds the operation already complete before it can register a callback and returns `false`, saving a suspend and a resume.
- ¶5.1.3 It returns `void`: it is called, then control returns to the caller or resumer of the current coroutine, without exiting any scopes, so local variables aren't destroyed. The point just before returning is called the **suspend point** ([[g:suspend-point]]).

¶5.1.3 also specifies that if `await_suspend` exits via an exception, the exception is caught, the coroutine is resumed, and the exception is immediately rethrown. The effect is as if the exception were thrown from the `co_await` expression itself, so a `try` in the coroutine body around it can catch it:

```cpp run ok
#include <coroutine>
#include <cstdio>
#include <stdexcept>

struct task { struct promise_type {
  task get_return_object() { return {}; }
  std::suspend_never initial_suspend() noexcept { return {}; }
  std::suspend_never final_suspend() noexcept { return {}; }
  void return_void() {}
  void unhandled_exception() { std::puts("unhandled"); }
}; };

struct throwing {
  bool await_ready() { return false; }
  void await_suspend(std::coroutine_handle<>) { throw std::runtime_error("boom"); }
  void await_resume() { std::puts("never printed"); }
};

task t() {
  try { co_await throwing{}; }
  catch (const std::exception& e) { std::printf("caught in coroutine: %s\n", e.what()); }
}

int main() { t(); }
```

The program prints `caught in coroutine: boom`, and `await_resume` isn't called. Read literally, this rule is written only for the `void` case; in our tests Clang 23 handles an exception from an `await_suspend` returning `bool` or `coroutine_handle` the same way.

### After resumption (¶5.2)

¶5.2 When `await_ready()` is `true`, or the coroutine is resumed (other than by the resumption due to an exception from `await_suspend`), `await_resume()` is evaluated, and its result is the result of the whole `co_await` expression.

Note 2: with respect to the order of evaluation, `co_await` is indivisible ([[intro.execution]]). In `f(co_await a, g())`, `g()` is evaluated either before the whole `co_await a` (including suspension and resumption) or after it, never during the suspension.

When `await_ready()` returns `true`, `await_suspend` isn't called, but it still has to compile: the type requirement in ¶3.7 is a compile-time check, independent of whether that branch is taken at run time.

## Symmetric transfer

When one coroutine awaits another, a common pattern is that the parent suspends and resumes the child, and the child resumes the parent when it finishes. With a `void`-returning `await_suspend` that calls `h.resume()` directly, every await adds a few more calls to the stack, and a loop of a million iterations can overflow the stack.

When `await_suspend` returns a handle, the current coroutine suspends first, and then the expansion of `co_await` resumes the returned coroutine. Implementations can compile this resumption as a tail call: the current coroutine's resume function returns first and then jumps to the target coroutine, so the stack depth stays constant. When there is no target to transfer to, return `std::noop_coroutine()`; resuming it does nothing and control goes straight back to the caller.

```cpp run ok
#include <coroutine>
#include <cstdio>
#include <exception>
#include <utility>

struct task {
  struct promise_type {
    std::coroutine_handle<> cont = std::noop_coroutine();
    int value = 0;
    task get_return_object() {
      return task{std::coroutine_handle<promise_type>::from_promise(*this)};
    }
    std::suspend_always initial_suspend() noexcept { return {}; }   // lazy start
    struct final_awaiter {
      bool await_ready() noexcept { return false; }
      std::coroutine_handle<>
      await_suspend(std::coroutine_handle<promise_type> h) noexcept {
        return h.promise().cont;     // on completion, transfer back to the awaiter
      }
      void await_resume() noexcept {}
    };
    final_awaiter final_suspend() noexcept { return {}; }
    void return_value(int v) { value = v; }
    void unhandled_exception() { std::terminate(); }
  };

  std::coroutine_handle<promise_type> h;
  explicit task(std::coroutine_handle<promise_type> h) : h(h) {}
  task(task&& o) noexcept : h(std::exchange(o.h, {})) {}
  ~task() { if (h) h.destroy(); }

  // task itself is the awaiter
  bool await_ready() const noexcept { return false; }
  std::coroutine_handle<> await_suspend(std::coroutine_handle<> caller) noexcept {
    h.promise().cont = caller;
    return h;                        // ¶5.1.1: resume the child directly
  }
  int await_resume() const noexcept { return h.promise().value; }
};

task leaf(int i) { co_return i; }

task sum(int n) {
  int s = 0;
  for (int i = 0; i < n; ++i)
    s += co_await leaf(1);
  co_return s;
}

int main() {
  task t = sum(1'000'000);
  t.h.resume();
  std::printf("%d\n", t.h.promise().value);   // 1000000
}
```

The standard only requires evaluating `await_suspend` and then calling `.resume()`; it doesn't require a tail call, which is a matter of quality of implementation. But symmetric transfer was designed precisely to make the tail call possible ([[P0913R1]]), and the major implementations all do it. In our tests Clang 23 completes the million iterations even at `-O0 -fsanitize=address`.

## Where it may appear (¶2)

¶2 `co_await` may appear only as a potentially evaluated expression within the compound statement of a function body or lambda body, and:

- not in an exception handler (a `catch` block);
- in a declaration statement, and in the init-statement of `if`, `for` and similar statements, only in an initializer;
- not in a default argument;
- not in the initializer of a block-scope variable with static or thread storage duration;
- {{c++26}} not as a potentially-evaluated subexpression of a contract assertion predicate ([[basic.contract]]).

A position that satisfies these conditions is called a **suspension context** of the function ([[g:suspension-context]]).

```cpp error
#include <coroutine>
struct task { struct promise_type {
  task get_return_object() { return {}; }
  std::suspend_never initial_suspend() noexcept { return {}; }
  std::suspend_never final_suspend() noexcept { return {}; }
  void return_void() {}
  void unhandled_exception() {}
}; };

task ok() {
  try { co_await std::suspend_never{}; }            // OK: allowed in a try block
  catch (...) {}
  int x = (co_await std::suspend_never{}, 1);       // OK: initializer
  (void)x;
}
task a() { try {} catch (...) { co_await std::suspend_never{}; } }   // error: in a handler
void c(int = (co_await std::suspend_never{}, 1));                    // error: default argument
task d() { decltype(co_await std::suspend_never{})* p = nullptr; co_return; }  // error: unevaluated
task b() { static int s = (co_await std::suspend_never{}, 1); }      // error: static local variable
```

Clang 23 diagnoses the first three errors but accepts the last one (the initializer of a static local variable), which is a Clang bug.

Each restriction has a reason:

- Suspension is a run-time action, and is meaningless in unevaluated positions such as `sizeof` and `decltype`.
- Inside a `catch` block there is an exception being handled, which `throw;` and `std::current_exception` rely on, and that state is tied to the thread. The coroutine may be resumed on another thread, and suspending would make this state hard to define. The usual approach is to record the information inside the `catch` and `co_await` after leaving it.
- Initialization of a static local variable is guaranteed to happen once and be thread-safe ([[stmt.dcl]]), usually implemented with a lock. Suspending while holding the lock would block other threads indefinitely.
- Default arguments are evaluated by the caller, and the caller isn't necessarily a coroutine.
- A contract assertion may not be evaluated at all, or may be evaluated several times ([[basic.contract]]); suspending inside it would make control flow depend on the contract's evaluation semantic.

## Implementation view

!!! impl "Coroutine frames and how co_await is compiled"
    - Clang, GCC and MSVC all split a coroutine into a ramp function for the initial call, a resume function and a destroy function. Local variables and awaiters that live across suspend points are placed in the coroutine frame, which records the index of the current suspend point; the resume function jumps based on it. A `std::coroutine_handle` is just a pointer to the coroutine frame, and `h.resume()` is an indirect call.
    - When `await_ready()` returns `true`, no state needs to be saved. After inlining, awaiting an already-ready awaiter is as cheap as an ordinary function call.
    - The coroutine frame is usually heap-allocated. If the coroutine's lifetime is strictly nested within its caller's, LLVM can place the frame on the caller's stack and avoid the heap allocation (HALO). The basis for this is that [[dcl.fct.def.coroutine]] allows the allocation of the coroutine state to be elided.

## History

!!! history
    - Coroutines were first published as the Coroutines TS and merged into C++20 by [[P0912R5]].
    - Symmetric transfer and `std::noop_coroutine` come from [[P0913R1]], which was added to the TS before the merge into the standard.
    - When C++26 introduced contracts, ¶2 gained the restriction against appearing in contract predicates.

## Common misconceptions

!!! pitfall "Touching the awaiter after handing off the handle"
    The coroutine counts as suspended before `await_suspend` is called. Once `await_suspend` hands `h` to another thread, that thread may resume the coroutine immediately; the coroutine may run to completion and destroy the coroutine frame, and the awaiter with it. Any access to members of `this` in `await_suspend` after that point is UB. Handing off the handle should be the last thing `await_suspend` does that touches the awaiter or the coroutine frame.

!!! pitfall "Assuming a declared `operator co_await` is always used"
    As soon as the promise declares `await_transform`, `operator co_await` applies to the result of `await_transform`, not to the original operand.

!!! pitfall "The two bools point in opposite directions"
    `await_ready()` returning `true` means ready, don't suspend; `await_suspend` returning `true` means stay suspended. If `h` has already been handed to another thread and `await_suspend` then returns `false`, both sides may resume the same coroutine at the same time, which is UB.

## Questions

!!! question "Question 1"
    The promise has no `await_transform`. Given `struct X { std::suspend_never operator co_await(); };` and also a non-member `std::suspend_never operator co_await(X);`, what happens with `co_await X{}`?

<details markdown="1">
<summary>Answer</summary>

Ill-formed: overload resolution is ambiguous. ¶3.3 collects both member and non-member candidates per [[over.match.oper]]. The argument is a prvalue of type `X`: the member candidate's implicit object parameter is `X&`, and a member function without a ref-qualifier allows binding an rvalue ([[over.match.funcs]]), an identity conversion; the non-member candidate takes it by value, also an identity conversion. Neither is better. Clang 23 reports `use of overloaded operator 'co_await' is ambiguous`.
</details>

!!! question "Question 2"
    Why don't `co_yield` and the `co_await` expressions produced by the initial and final suspends go through `await_transform`? What would happen if they did?

<details markdown="1">
<summary>Answer</summary>

Their operands are already calls to the promise's own members, so the promise already fully controls the returned value, and transforming again would be redundant. If they did go through it, a design like `std::generator`, which forbids `co_await` with a deleted `await_transform`, would also forbid its own `co_yield` and its initial and final suspends.
</details>
