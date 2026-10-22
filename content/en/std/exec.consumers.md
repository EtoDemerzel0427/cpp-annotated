---
title: "Sender consumers: sync_wait"
summary: "this_thread::sync_wait blocks the current thread until a sender completes and returns the result as optional<tuple<values...>>; errors become exceptions and cancellation becomes an empty optional. sync_wait_with_variant handles senders with several value signatures."
updated: 2026-10-19
---

!!! tldr
    - `this_thread::sync_wait(s)` starts the sender `s` and blocks the current thread until it completes.
    - A value completion returns an `optional` holding a `tuple<values...>`; an error completion is thrown as an exception; a stopped completion returns an empty `optional`.
    - `sync_wait` requires the sender to have exactly one value signature; for several, use `sync_wait_with_variant`, which returns `optional<variant<tuple<...>...>>`.
    - The default implementation puts a `run_loop` on the stack, and while waiting, the calling thread itself executes work scheduled onto that `run_loop`.
    - Its environment has no stop token, so it can't be cancelled from outside; calling it inside asynchronous code easily leads to deadlock.

The examples on this page use C++26 `std::execution` senders. The libc++ shipped with Clang 23 doesn't implement this part of the library yet, so none of the examples have been verified by compiling, and they carry no verdict.

## The boundary between the synchronous and asynchronous worlds

```cpp title="sync-wait.cpp"
namespace ex = std::execution;

int main() {
  auto s = ex::schedule(ex::get_parallel_scheduler())
         | ex::then([] { return 42; });
  auto [v] = std::this_thread::sync_wait(std::move(s)).value();   // v == 42
}
```

A [[g:sender|sender]] is only a description of a piece of work and doesn't run by itself. [[exec.async.ops#14]] calls functions that accept a sender but don't return one **sender consumers**; they are what actually run the work. This page covers `sync_wait` and `sync_wait_with_variant`; the other consumer, `spawn`, is in [[exec.spawn]].

`sync_wait` turns an asynchronous result back into an ordinary return value, so it is the boundary between synchronous and asynchronous code. It is generally used once, in `main` or in tests.

## What it returns ([exec.sync.wait] ¶1, ¶3, ¶11)

¶11.2 `sync_wait` translates the sender's three kinds of completion into three kinds of result:

| Sender's completion | Result of `sync_wait` |
|---|---|
| `set_value(args...)` | Returns an engaged `optional` holding a `tuple<args...>` |
| `set_error(err)` | Throws an exception |
| `set_stopped()` | Returns an empty `optional` |

¶3 The return type is `optional<value_types_of_t<Sndr, sync-wait-env, decayed-tuple, type_identity_t>>`. `value_types_of_t` turns each value signature into a `decayed-tuple`, then hands those tuples to the last parameter to combine them. Here that is `type_identity_t`, which accepts only one argument.

¶1 So the return type is well-formed only if the sender has exactly one value signature. With two, use `sync_wait_with_variant` instead; with none at all (for example `just_stopped()`), it is ill-formed as well.

| Sender's value signatures | Return type of `sync_wait` |
|---|---|
| `set_value_t()` | `optional<tuple<>>` |
| `set_value_t(int)` | `optional<tuple<int>>` |
| `set_value_t(int&, std::string)` | `optional<tuple<int, std::string>>`, with the types decayed |
| Two value signatures | Ill-formed |

### Which exception an error becomes

*AS-EXCEPT-PTR* in [[exec.general#8]] determines how an error becomes an exception: an `exception_ptr` is rethrown as is; an `error_code` is wrapped in a `system_error` and thrown; an error of any other type `E` is thrown as that `E` object directly.

So `sync_wait(just_error(std::make_error_code(std::errc::timed_out)))` throws `std::system_error`, while `sync_wait(just_error(42))` throws an `int`.

## The default implementation (¶2, ¶6–10)

¶10 The default implementation of `sync_wait` is short:

```cpp
sync-wait-state<Sndr> state;   // run_loop, exception_ptr, optional result
auto op = connect(sndr, sync-wait-receiver<Sndr>{&state});
start(op);

state.loop.run();
if (state.error) {
  rethrow_exception(std::move(state.error));
}
return std::move(state.result);
```

¶7–9 The receiver's three completion functions respectively store the values in `result`, convert the error to an `exception_ptr` and store it in `error`, or store nothing; all of them then call `loop.finish()`.

¶2 The receiver's environment, *sync-wait-env*, answers only three queries, `get_scheduler`, `get_start_scheduler` and `get_delegation_scheduler`, and the answer to each is the scheduler of this [[exec.run.loop|run_loop]].

A few things are worth noting:

- After `start(op)`, `loop.run()` has the current thread execute the work in the run_loop's queue until the receiver calls `finish()` and the queue is empty. If the sender schedules work onto the scheduler the environment provides, that work is executed by the thread that called `sync_wait` itself.
- The state and the operation state are both local variables in `sync_wait`'s stack frame; no dynamic allocation is needed.
- connect uses `sndr` itself, preserving its value category. `sync_wait(s)` connects with an lvalue, which requires `s` to be copyable; `sync_wait(std::move(s))` connects with an rvalue.
- When `run()` returns, the completion function has already begun executing and the asynchronous operation's lifetime has ended ([[exec.async.ops#7]]), so destroying `op` at that point is safe.

¶7 A value completion can also turn into an exception. When the results are copied into the `optional<tuple<...>>`, if some value's copy constructor throws (for example, running out of memory while copying a `std::string` sent by lvalue reference), the receiver's `set_value` is noexcept, so it can only catch the exception and store it in `error`, after which `sync_wait` rethrows it.

## It must really block (¶4–5, ¶11)

¶4 `sync_wait(sndr)` first finds the domain where the sender's value completion happens, then calls that domain's implementation through `apply_sender` ([[exec.snd.transform]]). So a domain can provide a different `sync_wait` for its own senders. ¶5 Whatever the implementation, the return type must be exactly the *sync-wait-result-type* above.

¶11.1 Every implementation must block the current thread until the sender completes, with **forward progress guarantee delegation** ([[intro.progress#13]]). This means: when a thread P blocks waiting on a set of threads S, the implementation must ensure that while P is blocked, at least one thread in S has a forward progress guarantee no weaker than P's.

The default implementation does this very directly (Note 1): the calling thread doesn't sit idle but executes, inside `loop.run()`, the work scheduled onto the run_loop. As long as the awaited work schedules the parts that must run onto the scheduler given by `get_delegation_scheduler`, it can borrow the calling thread's own forward progress guarantee.

## sync_wait_with_variant ([exec.sync.wait.var])

```cpp title="sync-wait-variant.cpp"
// suppose s may complete with set_value(int) or set_value(std::string)
if (auto r = std::this_thread::sync_wait_with_variant(std::move(s))) {
  std::visit([](auto& tup) { /* tup is tuple<int> or tuple<std::string> */ }, *r);
}
```

¶2 The return type is `optional<value_types_of_t<Sndr, sync-wait-env>>`, that is, `optional<variant<tuple<...>, ...>>`. ¶1 Like `sync_wait`, it can be customized by a domain.

¶3 The default implementation first uses `into_variant` to merge the several value signatures into one, `set_value(variant<tuple<...>...>)`, hands that to `sync_wait`, and finally takes the single element out of the returned `optional<tuple<variant<...>>>`:

```cpp
if (auto opt_value = sync_wait(into_variant(sndr))) {
  return result_type(std::move(get<0>(*opt_value)));
}
return result_type(nullopt);
```

¶4 Its requirements on blocking and on the return value are the same as for `sync_wait`; the default implementation's forward progress guarantee delegation comes from the `sync_wait` it calls.

## Common mistakes

### Calling sync_wait on a worker thread

Calling `sync_wait(sndr)` on a worker thread of a thread pool, where `sndr` needs threads of the same pool to complete: if all the threads in the pool are blocked in `sync_wait`, it deadlocks. `sync_wait` lends only its own run_loop to the awaited work, and can do nothing about other execution resources.

Inside asynchronous code, compose the work with `let_value` or `when_all`, or `co_await` it in a coroutine ([[exec.as.awaitable]]).

### Thinking sync_wait can be cancelled

*sync-wait-env* doesn't answer `get_stop_token`, so the awaited work gets the default `never_stop_token` and never receives a stop request. When you need a cancellable synchronous wait, provide a stop token yourself with `write_env`:

```cpp title="cancellable-sync-wait.cpp"
std::inplace_stop_source src;
auto r = std::this_thread::sync_wait(
    ex::write_env(std::move(s), ex::prop(std::get_stop_token, src.get_token())));
// another thread calls src.request_stop()
```

## Questions

!!! question "Is all the work finished when sync_wait returns?"
    When `sync_wait` returns, has all the work started by the sender finished?

<details markdown="1">
<summary>Answer</summary>

The child operations started by `sndr` have all finished: item 2.5 of [[exec.async.ops#2]] requires child operations to complete before their parent completes, and `sync_wait` waited for `sndr` to complete.

But work handed to some async scope through `spawn` isn't a child operation of `sndr` and isn't bound by this rule; it has to be waited for by that scope's `join` ([[exec.scope]]).
</details>

## Summary

| Question | Answer |
|---|---|
| Value completion | Returns an engaged `optional<tuple<values...>>` |
| Error completion | Throws an exception; `error_code` is wrapped in `system_error` |
| Stopped completion | Returns an empty `optional` |
| Several value signatures | Use `sync_wait_with_variant` |
| While waiting | The calling thread drives the `run_loop` on the stack |
| Cancellation | No stop token in the environment; provide one with `write_env` when needed |
