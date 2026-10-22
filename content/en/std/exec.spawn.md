---
title: spawn, spawn_future and associate
summary: "Handing senders over to an async scope: spawn starts immediately and discards the result, spawn_future starts immediately and returns a sender from which the result can be retrieved, associate only establishes an association without starting anything; when association fails, the work doesn't run."
updated: 2026-10-19
---

!!! tldr
    - `spawn(sndr, token)` starts `sndr` immediately and returns no result. `sndr` may only complete with `set_value()` or `set_stopped()`; senders that carry values or may fail must be dealt with explicitly first.
    - `spawn_future(sndr, token)` starts `sndr` immediately and returns a sender from which the result can be retrieved later. Discarding that sender requests that the work stop, rather than blocking to wait for it.
    - `associate(sndr, token)` starts nothing; it only makes the scope aware of the sender. When association fails, the operation it produces completes with `set_stopped`.
    - Once the scope is closed, association fails: `spawn` then silently abandons the work, and the result of `spawn_future` is a stopped completion.
    - The state object is destroyed first and the association released afterwards, so when the scope's `join` completes, the started work and its state no longer exist.

The examples on this page use C++26 `std::execution` senders. The libc++ shipped with Clang 23 doesn't implement this part of the library yet, so none of the examples have been verified by compiling, and they carry no verdict.

## Three ways of handing work to a scope

An [[g:async-scope|async scope]] ([[exec.scope]]) keeps track of how much work is associated with it and provides `join()`, which waits until all that work has ended. Work is associated with a scope through the scope's **token**: `token.try_associate()` tries to increment the count, and on success returns an association object whose destruction decrements the count; once the scope is closed, `try_associate()` returns an empty association representing failure.

The three algorithms on this page hand senders over to a scope:

| Algorithm | Returns | When it starts | Result | When association fails |
|---|---|---|---|---|
| `spawn(sndr, token[, env])` | `void` | Immediately | Discarded | Not started; silently abandoned |
| `spawn_future(sndr, token[, env])` | A sender | Immediately | Retrieved from the returned sender | The returned sender completes with stopped |
| `associate(sndr, token)` | A sender | Along with the returned sender | Forwarded unchanged | Completes with stopped |

`spawn` and `spawn_future` are eager: work begins when they are called. They replace `start_detached` and `ensure_started` from early P2300 drafts, the difference being that there must be a scope responsible for the started work, so work never drops out of everyone's sight.

```cpp title="spawn.cpp"
namespace ex = std::execution;

ex::counting_scope scope;
auto pool = ex::get_parallel_scheduler();

ex::spawn(ex::starts_on(pool, ex::just() | ex::then([] { do_work(); }))
            | ex::upon_error([](std::exception_ptr) noexcept { /* log it */ }),
          scope.get_token());
// ...
std::this_thread::sync_wait(scope.join());   // wait for all spawned work to end
```

## spawn ([exec.spawn])

### Only senders without values that can't fail (¶2–4)

¶1 `spawn` tries to associate the sender with the scope the token belongs to, and on success starts it immediately. ¶2 `spawn(sndr, token, env)` is ill-formed if `sndr` isn't a sender, the token doesn't satisfy `scope_token`, or `env` isn't a queryable object.

¶4 The receiver `spawn` uses to receive the completion has only two completion functions:

```cpp
struct spawn-receiver {
  using receiver_concept = receiver_tag;
  spawn-state-base* state;
  void set_value() && noexcept   { state->complete(); }
  void set_stopped() && noexcept { state->complete(); }
};
```

So a spawned sender can only complete with `set_value_t()` or `set_stopped_t()`. Any completion with values, or any error completion, makes the *Mandates* of connect (the receiver must accept all the sender's completions) fail, and the program is ill-formed.

It's designed this way because after spawning nobody receives the result, and errors have nowhere to be reported. Rather than letting errors be silently swallowed, the standard requires the caller to handle them explicitly: log errors with `upon_error(...)`, discard values with `then([](auto&&...) {})`.

<div class="compare" markdown="1">

```cpp
ex::spawn(ex::just(42), tok);
// error: spawn-receiver
// has no set_value(int)
```

```cpp
ex::spawn(ex::just(42)
            | ex::then([](int) {}),
          tok);
// OK: the value is explicitly discarded
```

</div>

### The state object and destruction order (¶5–8)

¶5 `spawn` creates a *spawn-state* on the heap (through an allocator), holding the allocator, the operation state `op` and the association `assoc`:

- ¶6 On construction it first connects to get `op`, then calls `token.try_associate()` to get `assoc`.
- ¶7 `run()`: if association succeeded, `start(op)`; if it failed, call `complete()` directly.
- ¶8 `complete()`: first move `assoc` into a local variable, then destroy and deallocate the whole state object with the allocator; when the function returns, the local `assoc` is destroyed, releasing the association.

The order in ¶8 matters. If the association were released first, the count could reach zero, `join()` would then complete, and the waiter might go on to destroy the scope and other objects in the program while the *spawn-state* is still being destroyed, so the operation state's destructor could access things that no longer exist. With ¶8's order, the scope's count covers the entire lifetime of the state object, not just the time the work is running.

### Allocator and environment (¶9–11)

¶9 Let `new_sender` be `token.wrap(sndr)`; `spawn` chooses the allocator `alloc` and environment `senv` in this order:

- ¶9.1 if `env` provides an allocator (`get_allocator(env)` is well-formed), use it, and `senv` is `env`;
- ¶9.2 otherwise, if the sender's attributes provide an allocator, use it and add it to the environment: `senv` is *JOIN-ENV*(prop(get_allocator, alloc), env);
- ¶9.3 otherwise use `allocator<void>()`, and `senv` is `env`.

¶10 The type of `spawn(sndr, token, env)` is `void`. It allocates and constructs a *spawn-state* with `alloc`; the sender that gets connected is `write_env(token.wrap(sndr), senv)`; then it calls `run()`. If an exception is thrown during construction, the objects already constructed are destroyed and the memory already allocated is deallocated.

`token.wrap` lets the scope decorate the sender; `counting_scope`, for example, uses it to weave in its own stop token. `write_env(..., senv)` hands the caller-provided environment to the sender.

Spawned work has no upstream receiver to inherit an environment from; the only environment it sees is `senv`. ¶11 `spawn(sndr, token)` is equivalent to `spawn(sndr, token, env<>())`, in which case the environment is almost empty: no scheduler, and no stop token other than what the scope's `wrap` weaves in. When spawning inside a coroutine or a sender chain, if you want the child work to use some scheduler, pass it through the third argument, for example `spawn(work, tok, env{prop(get_scheduler, sch)})`.

## spawn_future ([exec.spawn.future])

```cpp title="spawn-future.cpp"
namespace ex = std::execution;

ex::counting_scope scope;
auto fut = ex::spawn_future(ex::starts_on(pool, compute()),
                            scope.get_token());   // already computing
do_something_else();
auto [v] = std::this_thread::sync_wait(std::move(fut)).value();   // retrieve the result
std::this_thread::sync_wait(scope.join());
```

¶1 `spawn_future` tries to associate, starts the input sender immediately on success, and then returns a sender. When the returned sender is connected and started, it completes with the result of the already-started sender; if the input sender was never started (association failed), it completes with `set_stopped`. ¶2 The validity requirements are the same as for `spawn`.

### Storing the result (¶4–8)

The result has to be kept from the moment the work completes until the moment someone comes to collect it, and which of those happens first is uncertain. So `spawn_future` also creates a state object on the heap, a *spawn-future-state*.

¶4–5 The state's `result` is a `variant` that can hold any of the input sender's completions, for example `tuple<set_value_t, int>` or `tuple<set_stopped_t>`. If decay-copying some result may throw, it can also hold `tuple<set_error_t, exception_ptr>`.

¶6 Unlike with `spawn`, the *spawn-future-receiver* accepts every kind of completion, since someone wants the result. It decay-copies the result into `result`, stores an `exception_ptr` instead if the copy throws, and then calls `complete()`.

¶7–8 The state also has its own stop source, `ssource`. The sender actually connected is `write_env(stop-when(sndr, ssource.get_token()), env)`, where *stop-when* merges `ssource`'s token into the sender (see the last section of this page). On construction it connects first, then calls `try_associate()`; on success it starts, and on failure it completes directly with `set_stopped`, storing the stopped result in `result`.

### How the work and the collecting side meet (¶9–14)

¶9 There are four operations on the state object. For the purposes of determining data races they behave as atomic operations, and on a given object they occur in a single total order:

| Operation | When it happens | Meaning |
|---|---|---|
| *complete* | The input sender completes | The result is ready |
| *consume*(rcvr) | The returned sender is started | Someone has come for the result; register receiver `rcvr` |
| *try-set-stopped* | The collecting side gets a stop request | Cancel the wait |
| *abandon* | The returned sender is discarded without ever being started | Nobody wants the result any more |

The order in which they happen decides who gets the result and who destroys the state:

- ¶10 If *complete* happens before the other three, it does nothing and waits for someone to collect. If a receiver has already registered and hasn't been cancelled, it hands the result to that receiver. Otherwise (the wait was cancelled, or the result was abandoned) it destroys the state.
- ¶11 If *consume* happens before *complete* and hasn't been cancelled, it registers the receiver and waits for the result. If the wait has been cancelled and the result hasn't arrived, it completes the receiver with `set_stopped`. Otherwise the result is already there, and it hands it to the receiver immediately and then destroys the state.
- ¶12 *try-set-stopped*, when a receiver has registered and the result hasn't arrived, completes that receiver with `set_stopped` and then destroys the state; otherwise it does nothing.
- ¶13 If *abandon* happens before *complete*, it calls `ssource.request_stop()` to ask the still-running work to stop, and leaves the state for the later *complete* to destroy; otherwise the result is there and nobody wants it, so it destroys the state directly.
- ¶14 *destroy*, as with `spawn`, first destroys and deallocates the state object, then releases the association.

### Discarding means cancelling (¶15–21)

¶20 The sender returned by `spawn_future` holds a `unique_ptr` to the state whose deleter calls *abandon*. So discarding the sender returned by `spawn_future` is a request to cancel that work.

This is completely different from `std::future` (the kind `std::async` returns) blocking to wait in its destructor: it neither blocks nor leaks. The work is asked to stop, and when it eventually completes, *complete* cleans up the state; the scope's `join()` waits until that moment.

¶15–18 Connecting the returned sender gives a *future-operation*. On start, it first registers a callback on the outer receiver's stop token, then hands over ownership of the state and calls *consume*. The callback calls *try-cancel*, which is `ssource.request_stop()` plus *try-set-stopped*. So when the outer receiver is asked to stop, the running work and the wait itself are cancelled together.

¶19 The allocator and environment are chosen the same way as in ¶9 of `spawn`. ¶21 `spawn_future(sndr, token)` is equivalent to `spawn_future(sndr, token, env<>())`.

## associate ([exec.associate])

¶1 `associate` tries to associate a sender with a scope, so that the scope can track the lifetimes of all asynchronous operations created from this sender.

Unlike `spawn`, it starts nothing; it returns a lazy sender. The use case is a caller who will start this sender themselves (handing it to a third-party component that knows nothing about scopes, say), but wants the scope to know about it and wait for it to end at `join()`.

¶2 The association is attempted when `associate` is called, and is held by the returned sender until the operation it produces completes. Its data, *associate-data*, is constructed like this: first `sndr = token.wrap(s)`, then `try_associate()`; if association fails, the freshly wrapped sender is destroyed immediately, and it is kept only on success.

¶4–8 Copying and moving *associate-data* have their own rules:

- ¶4–5 On copy (which requires the wrapped sender to be copyable), `try_associate()` is called again on the source object's association, and the sender is copied only if that succeeds. So copying an `associate` sender takes up another unit of the scope's count.
- ¶6, ¶8 On move, the association and the sender are transferred together to the new object.
- ¶7 On destruction, if it holds an association, the sender is destroyed, and the association is released as the member is destroyed.

¶9 `associate(sndr, token)` is ill-formed if `sndr` isn't a sender or the token doesn't satisfy `scope_token`; otherwise the result is a sender with *associate-data* as its data.

¶11 At connect, if it holds an association, the wrapped sender is connected to the receiver; otherwise only the receiver's address is recorded. ¶13 At start, with an association the inner operation is started; otherwise it calls `set_stopped` directly.

¶14 Evaluating `associate(sndr, token)` may have side effects observable through the scope, namely the count being incremented. [[exec.adapt.general#3]] requires adaptors to have no observable effects before connect and start; this paragraph is an explicit exception.

## stop-when: merging two stop tokens ([exec.stop.when])

¶1 *stop-when*(sndr, token) is an adaptor used internally by the standard and not exposed to users. It merges an extra stop token `token` into a sender: after connecting to a receiver `r`, the operation responds both to stop requests on `token` and to the stop token in `r`'s environment.

`counting_scope`'s `wrap` and `spawn_future` both use it: the managed work must respond both to cancellation by the caller and to cancellation issued by the scope or the future itself.

¶2 It handles the tokens case by case:

- ¶2.1 ill-formed if `sndr` isn't a sender or `token` isn't a stop token;
- ¶2.2 when `token` can never have a stop requested (it satisfies `unstoppable_token`), the result is just `sndr`, with no need to merge;
- ¶2.3.1 when the receiver's token can never have a stop requested, `token` is given to `sndr` directly as its stop token through `write_env`;
- ¶2.3.2 otherwise `sndr` is given a synthesized token: it reports that a stop has been requested as soon as either token has a stop requested, and callbacks registered on it are invoked when either token fires, at most once (Note 1).

## Questions

!!! question "1. spawn when association fails"
    The scope is already closed, and `spawn(sndr, scope.get_token())` is called. Is memory allocated? Is `sndr` connected?

<details markdown="1">
<summary>Answer</summary>

Both. ¶10 first allocates and constructs the *spawn-state* with the allocator, and the construction in ¶6 connects first (initializing `op`) and then calls `try_associate()`, which fails at this point. Then `run()` finds there is no association and calls `complete()`, which destroys and deallocates the state.

So even when association fails, `sndr` has been connected, just never started; the operation state is constructed and then destroyed.
</details>

!!! question "2. Discarding a spawn_future that never stops"
    `auto f = spawn_future(never_ending_work(), tok);` and then `f` is discarded. What happens?

<details markdown="1">
<summary>Answer</summary>

When `f` is destroyed, the deleter calls *abandon*. The work hasn't completed, so `ssource.request_stop()` is called. If the work ignores the stop request and never completes, the state is never destroyed, the association is never released, and `scope.join()` never completes.

This isn't a defect of `spawn_future`. Every started asynchronous operation must eventually complete ([[exec.async.ops#2]]); the scope merely makes explicit who does the waiting.
</details>

## Summary

| Algorithm | Starts | Result | Association fails | Key points |
|---|---|---|---|---|
| `spawn` | Immediately | Discarded | Silently abandoned | Accepts only `set_value_t()` and `set_stopped_t()` |
| `spawn_future` | Immediately | The returned sender | Completes with stopped | Four operations meet; discarding the return value requests a stop |
| `associate` | With the returned sender | Forwarded unchanged | Completes with stopped | Associates when called; copying associates again |

All three destroy the state first and release the association afterwards; the environment of started work comes only from the explicitly passed `env`, plus the scope's `wrap` and the allocator.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[exec.spawn] ¶3 *spawn-state-base* has just one pure virtual function, `complete()`, so the receiver doesn't need to know the state object's concrete type.

[exec.spawn.future] ¶3 *try-cancelable* is likewise a base class with only a pure virtual function *try-cancel*, used by the stop callback of *future-operation*. ¶16–18 *impls-for*<spawn_future_t> customizes *start* (calling *future-operation*::*run*) and *get-state* (constructing the *future-operation*). The exposition code in ¶14 moves `this->associated`, but in ¶8 this member is called `assoc`; this is presumably a typo in the draft.

[exec.associate] ¶10 *check-types* computes the completion signatures of the wrapped sender. ¶12 The noexcept of *get-state* depends on whether the data can be moved or copied without throwing, and whether connect may throw.

</details>
