---
title: connect
summary: "connect(sndr, rcvr) first applies transform_sender to the sender using the receiver's environment, then calls the result's connect member; when the object is only an awaitable, an exposition-only coroutine wraps it into an operation state; whether connect throws may depend only on the environment type."
updated: 2026-10-19
---

!!! tldr
    - `connect(sndr, rcvr)` first calls `transform_sender(sndr, get_env(rcvr))`, giving the execution domain a chance to replace the algorithm's implementation, and then calls the `connect` member of the transformed result.
    - The sender must have definite completion signatures in the receiver's environment, and the receiver must accept every kind of completion; otherwise `connect` is ill-formed.
    - For two receivers with the same environment type, the noexcept-ness of `connect` must agree; otherwise the program is ill-formed, no diagnostic required.
    - An awaitable without a `connect` member is wrapped in a coroutine whose frame is the operation state; it suspends before completing, because the receiver may destroy it on completion.

The `std::execution` examples on this page have not been verified by compiling: the libc++ shipped with Clang 23 doesn't implement the sender library yet. The example that uses only coroutine language features was compiled with Clang 23.

## What connect does (¶1–2, ¶6)

¶1 `connect` connects a [[g:sender|sender]] with a [[g:receiver|receiver]], giving an [[g:operation-state|operation state]] ([[exec.async.ops#9]]). This is the step where a description becomes a runnable entity.

¶2 Let `new_sndr` be the result of `transform_sender(sndr, get_env(rcvr))`. `transform_sender` rewrites the sender according to the execution domains associated with the sender and the receiver's environment, for example replacing `bulk` with an implementation on a GPU ([[exec.snd.transform]]).

¶6 `connect(sndr, rcvr)` is equivalent to:

- ¶6.1 `new_sndr.connect(rcvr)`, if that is well-formed. The result type must satisfy `operation_state` (*Mandates*).
- ¶6.2 Otherwise, *connect-awaitable*(new_sndr, rcvr); see below.

`rcvr` is evaluated only once. There are two more *Mandates*:

- ¶6.8 `sender_in<Sndr, env_of_t<Rcvr>>`: the sender's completion signatures can be computed in the receiver's environment;
- ¶6.9 *receiver-of*<Rcvr, completion_signatures_of_t<Sndr, env_of_t<Rcvr>>>: the receiver accepts every completion signature.

When a *Mandates* isn't met, the program is ill-formed, rather than `connect` dropping out of overload resolution. When a user connects a sender to a mismatched receiver, the diagnostic they see comes from these two.

Why is `transform_sender` done here? Which implementation to pick depends on two things: where the predecessor completes (from the sender's attributes) and where the operation starts (from the receiver's environment). The latter isn't known when `then(...)` is called to construct the sender; only at connect are both available at once.

## connect's noexcept may depend only on the environment (¶6.3–6.7)

The second half of ¶6 is an ill-formed, no diagnostic required (IFNDR) {{ifndr}} rule. If there is another rvalue receiver `rcvr2` such that

- ¶6.3 `decltype(rcvr2)` models `receiver`;
- ¶6.4 `noexcept(rcvr2)` is true;
- ¶6.5 `get_env(rcvr2)` has the same type as `get_env(rcvr)`;
- ¶6.6 `noexcept(connect(sndr, rcvr))` is true;
- ¶6.7 `noexcept(connect(sndr, rcvr2))` is well-formed and false,

then the program is ill-formed, no diagnostic required. In other words, whether `connect` may throw can be determined only by the receiver's environment type, and can't vary with the type of the receiver itself. ¶6.4 excludes cases that differ merely because evaluating `rcvr2` itself throws.

Note 1 explains the motivation: this way, in places where only the environment is known, such as inside `get_completion_signatures`, one can still tell whether `connect` will throw. `let_value` needs exactly this: if connecting the sender returned by the callback may throw, its signatures must include an extra `set_error_t(exception_ptr)`, and when computing signatures only the environment is known, not the final receiver type ([[exec.let]]).

## Awaitables as senders: connect-awaitable (¶3–5)

By the definition in [[exec.snd]], every awaitable (an object that can be `co_await`ed in a coroutine) automatically satisfies `sender`, so existing coroutine task types can be used as senders without modification. Such types usually have no `connect` member, so they take ¶6.2: the standard writes a coroutine that turns `co_await x` into calling `set_value(rcvr, result)` on completion, and the coroutine frame itself serves as the operation state.

### The operation state is the coroutine (¶4)

```cpp
struct operation-state-task {
  using operation_state_concept = operation_state_tag;
  using promise_type = connect-awaitable-promise;
  explicit operation-state-task(coroutine_handle<> h) noexcept : coro(h) {}
  operation-state-task(operation-state-task&&) = delete;
  ~operation-state-task() { coro.destroy(); }
  void start() & noexcept { coro.resume(); }
private:
  coroutine_handle<> coro;
};
```

`start` resumes the coroutine, destruction destroys the coroutine frame, and the move constructor is deleted.

### The promise type (¶3)

¶3 *connect-awaitable-promise* is this coroutine's promise type. A few members determine the coroutine's behavior:

- The constructor takes `(DS&, DR& rcvr)`, matching the coroutine's parameters. Per [[dcl.fct.def.coroutine]], when the promise type has a constructor callable with the coroutine's parameters, that constructor is used to build the promise object, so the promise directly gets a reference to the receiver in the coroutine frame.
- `initial_suspend` returns `suspend_always`: the coroutine suspends immediately after creation and isn't resumed until `start`.
- `final_suspend`, `unhandled_exception` and `return_void` all call `terminate()`. The coroutine body guarantees these paths are never taken; see the next section.
- `unhandled_stopped` calls `set_stopped` on the receiver: this is the path taken when the awaited sender ends with cancellation ([[exec.as.awaitable]]).
- `get_env` returns the receiver's environment, so senders `co_await`ed inside the coroutine see the outer environment.

### The coroutine body and suspend-complete (¶5)

```cpp
operation-state-task connect-awaitable(DS sndr, DR rcvr) requires receiver-of<DR, Sigs> {
  exception_ptr ep;
  try {
    if constexpr (same_as<V, void>) {
      co_await std::move(sndr);
      co_await suspend-complete(set_value, std::move(rcvr));
    } else {
      co_await suspend-complete(set_value, std::move(rcvr), co_await std::move(sndr));
    }
  } catch(...) {
    ep = current_exception();
  }
  co_await suspend-complete(set_error, std::move(rcvr), std::move(ep));
}
```

`V` is the result type of `co_await sndr`, and `Sigs` is the three signatures `set_value_t(V)` (`set_value_t()` when `V` is `void`), `set_error_t(exception_ptr)` and `set_stopped_t()`.

The completion functions aren't called directly; they are wrapped in the awaiter returned by *suspend-complete*: its `await_ready` returns false, so the coroutine suspends first, and then `set_value` or `set_error` is called in `await_suspend`. `await_resume` is marked `unreachable()`; the coroutine is never resumed from there.

Suspending before completing is necessary because [[exec.async.ops#8]] allows a receiver to destroy the operation state, that is, this coroutine frame, inside the completion function. And `destroy` has the precondition that the coroutine is suspended ([[coroutine.handle.resumption#4]]). The following program simulates this process, and runs without errors under AddressSanitizer:

```cpp run ok
#include <coroutine>
#include <cstdio>
#include <exception>

struct task {
  struct promise_type {
    task get_return_object() {
      return {std::coroutine_handle<promise_type>::from_promise(*this)};
    }
    std::suspend_always initial_suspend() noexcept { return {}; }
    std::suspend_always final_suspend() noexcept { std::terminate(); }
    void return_void() { std::terminate(); }
    void unhandled_exception() { std::terminate(); }
  };
  std::coroutine_handle<> h;
};

struct complete_then_destroy {
  bool await_ready() noexcept { return false; }
  void await_suspend(std::coroutine_handle<> h) noexcept {
    std::puts("set_value");   // stands in for calling the receiver's completion function
    h.destroy();              // OK: the coroutine is suspended at this point
  }
  [[noreturn]] void await_resume() noexcept { std::terminate(); }
};

task op() { co_await complete_then_destroy{}; }

int main() {
  task t = op();   // lazy: initial_suspend suspends
  t.h.resume();    // stands in for start(op)
  std::puts("done");
}
```

The lambda inside *suspend-complete* captures the arguments `as` by reference. In `co_await suspend-complete(set_value, std::move(rcvr), co_await std::move(sndr))`, the result of the inner `co_await` is a temporary that isn't destroyed until the end of its full-expression. When the outer `co_await` suspends, that full-expression hasn't ended yet, so the reference stays valid throughout.

!!! lawyer "Why set_error is outside the try block"
    `co_await` can't appear in an exception handler ([[expr.await#2]]), so the `catch` block can only store the exception in `ep` first, and `co_await suspend-complete(set_error, ...)` comes after leaving it. If the `try` block runs normally, the coroutine suspends at the `set_value` point and is never resumed, so the last line is never reached.

## Questions

!!! question "1. Can a std::suspend_always be connected?"
    `std::suspend_always` is an awaitable. What happens with `sync_wait(std::suspend_always{})`?

<details markdown="1">
<summary>Answer</summary>

It satisfies `sender`, with signatures `set_value_t()`, `set_error_t(exception_ptr)` and `set_stopped_t()`. connect takes the *connect-awaitable* path: the coroutine suspends on `co_await suspend_always{}`, and `suspend_always::await_suspend` does nothing, so no one will ever resume the coroutine and the operation never completes. The `run_loop` driven by `sync_wait` never sees a completion, and `sync_wait` blocks forever.

This is perfectly valid at the type level, but it violates the requirement of [[exec.async.ops#2]] that a started operation eventually completes. That awaitables automatically become senders doesn't mean every awaitable is a meaningful sender.
</details>

!!! question "2. How do connect's Mandates differ from sender-to?"
    The exposition-only concept *sender-to*<Sndr, Rcvr> ([[exec.snd]]) already includes `sender_in` and *receiver-of*. Why does `connect` spell out separate *Mandates*?

<details markdown="1">
<summary>Answer</summary>

*sender-to* is a concept; when used in a constraint, not being satisfied only makes a `requires` false or removes a function from overload resolution, without an error. `connect`'s *Mandates* guarantee that whenever someone writes `connect(s, r)` directly and the two don't match, the program is ill-formed and the implementation must issue a diagnostic.
</details>
