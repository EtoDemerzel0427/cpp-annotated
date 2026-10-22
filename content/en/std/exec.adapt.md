---
title: Sender adaptors
summary: "The general rules for adaptors (laziness, how attributes and environments are forwarded, the exception_ptr signature that may be omitted); the closure objects behind sndr | then(f); then, upon_error, upon_stopped; write_env and unstoppable; into_variant; stopped_as_optional and stopped_as_error."
updated: 2026-10-19
---

!!! tldr
    - An adaptor takes senders and returns a new sender, and it is lazy: until the result is connected and started, it does nothing except copy and move its arguments.
    - `then(sndr, f)` and `sndr | then(f)` are equivalent; `then(f)`, missing its sender, is a closure object, and closures can be composed with `|` as well, the same design as range adaptors in ranges.
    - `then`, `upon_error` and `upon_stopped` call a callback on value, error and stopped completions respectively, and send the callback's result as a value; an exception thrown by the callback becomes `set_error(exception_ptr)`.
    - `write_env` gives the child sender a merged environment, with the written queries taking priority; `unstoppable` simply writes a stop token that never stops.
    - `into_variant` combines several value signatures into one variant; `stopped_as_optional` and `stopped_as_error` turn cancellation into an empty `optional` or into an error.

The `std::execution` examples on this page have not been verified by compiling: the libc++ shipped with Clang 23 doesn't implement the sender library yet, so they carry no verdict.

A [[g:sender-adaptor|sender adaptor]] takes one or more senders (called child senders) and returns a new sender (the parent sender); it is the tool for composing small pieces of asynchronous work into bigger ones. This page covers the general rules, the pipe syntax and a few of the simpler adaptors. The rest are elsewhere: `starts_on`, `continues_on` and `on`, which switch execution resources, are in [[exec.on]]; `let_*` in [[exec.let]]; `bulk*` in [[exec.bulk]]; `when_all` in [[exec.when.all]]; `associate` and `spawn_future` in [[exec.spawn]].

## Pipe syntax and closure objects [exec.adapt.obj]

```cpp title="pipe.cpp"
namespace ex = std::execution;

auto add1  = ex::then([](int x) { return x + 1; });   // no sender given: yields a closure
auto twice = add1 | add1;                             // compose two closures: add1, then add1
auto s     = ex::just(40) | twice;                    // equivalent to then(then(just(40), f), f)
```

This syntax corresponds almost one to one with range adaptors in ranges. Here is the same thing written with ranges:

```cpp run ok
#include <ranges>
#include <vector>
#include <print>

int main() {
  auto add1  = std::views::transform([](int x) { return x + 1; });
  auto twice = add1 | add1;          // compose two closures
  std::vector v{1, 2, 3};
  for (int x : v | twice) std::print("{} ", x);   // 3 4 5
}
```

¶1 A **pipeable sender adaptor closure object** ([[g:pipeable-sender-adaptor-closure-object|pipeable sender adaptor closure object]]) is a function object `c` that takes a sender and returns a sender, where `c(sndr)` and `sndr | c` are equivalent. Two closures `c | d` produce a new closure, and calling it amounts to `d(c(arg))`: first `c`, then `d`. The new closure stores copies of `c` and `d`.

¶2 For a type `T` to be the type of a closure object, it must derive from `sender_adaptor_closure<T>` (and have only one such base class), and must not itself satisfy `sender`. So a custom closure only needs to inherit from this base:

```cpp title="closure.cpp"
struct log_values_t : ex::sender_adaptor_closure<log_values_t> {
  template<ex::sender S> auto operator()(S&& s) const {
    return std::forward<S>(s)
         | ex::then([](auto v) { std::println("{}", v); return v; });
  }
};
inline constexpr log_values_t log_values;
// ex::just(1) | log_values | ex::then(...)
```

¶3 The `D` of `sender_adaptor_closure<D>` can be incomplete when the base class is declared, but must be complete before it appears as an operand of `|`. If overload resolution selects a program-defined `operator|` for such an operand, the behavior is undefined {{ub}}, so don't write another `operator|` for your own closure types.

¶4 A **pipeable sender adaptor object** is a customization point object whose first argument is a sender and that returns a sender; `then` and `write_env` are examples. One that takes only a single argument (such as `into_variant`) is itself a closure object.

¶5 When an adaptor object that takes several arguments is called without the sender, as in `then(f)`, it produces a closure: the closure stores the adaptor and decayed copies of the remaining arguments, and calling it with `sndr` amounts to `then(sndr, f)`.

## General rules [exec.adapt.general]

¶2 Adaptors support both the function-call form and the `|` form, with the same meaning.

¶3 Unless otherwise specified, all adaptors follow these rules:

- ¶3.1 Adaptors are **lazy**: until the returned sender is connected and started, they can have no observable effects, except copying and moving their arguments. `then(sndr, f)` doesn't call `f`, nor does it start `sndr` in advance.
- ¶3.2 When there is just one child sender, the parent sender's attributes are the child's attributes, exposing only [[g:forwarding-query|forwarding queries]] (*FWD-ENV*). The exceptions are the completion scheduler and completion domain queries, which are recomputed per [[exec.snd.general#3]] and [[exec.snd.general#4]], since the adaptor may change where completions happen.
- ¶3.3 When there are several child senders, the parent's attributes are the empty environment `env<>{}`, again with the completion scheduler and completion domain computed separately.
- ¶3.4 When the parent sender is connected with receiver `rcvr`, the environment child senders see is *FWD-ENV*(get_env(rcvr)), that is, the forwarding queries of the outer environment.
- ¶3.5 When the child senders are all [[g:non-dependent-sender|non-dependent senders]], the adaptor is non-dependent too.
- ¶3.6 These requirements also apply to any function the implementation selects, including implementations selected through domain customization.
- ¶3.7 *Recommended practice*: implementations should use the adaptor's completion signatures to report type errors to the user, and propagate type errors from child senders.

Laziness means senders can be freely constructed, copied and discarded with no side effects. A function can return a sender describing a lot of work, and the caller decides whether to `sync_wait` it, `spawn` it, or just throw it away. `std::async` is different: it starts working as soon as it is called, and discarding the returned `future` blocks waiting in its destructor.

¶4 Some adaptors specify that their signatures include `set_error_t(exception_ptr)`. If the implementation determines that no such error completion will be sent, it may omit this signature. For example, when the implementation can prove that `then`'s callback won't throw, it needn't report it, and downstream code has one fewer impossible case to handle.

## then, upon_error, upon_stopped [exec.then]

```cpp title="upon-error.cpp"
namespace ex = std::execution;

auto s = ex::just_error(std::make_error_code(std::errc::timed_out))
       | ex::upon_error([](std::error_code) { return -1; });   // set_value_t(int)
auto [v] = std::this_thread::sync_wait(std::move(s)).value();   // v == -1
```

¶1 `then` attaches a callable as the continuation of the input sender's value completion; `upon_error` and `upon_stopped` do the same for error and stopped completions. All three send the callable's result as a value completion. So `upon_error` turns an error into a value; it's the tool for handling an error and resuming execution.

¶2–3 Ill-formed if `sndr` isn't a sender or `f` doesn't satisfy *movable-value* (can be decay-copied into an independent value, see [[exec.general]]); otherwise equivalent to *make-sender*(*then-cpo*, f, sndr).

¶4 The *impls-for* overrides only *complete* (the hooks are explained in [[exec.snd]]):

```cpp
static constexpr auto complete =
  []<class Tag, class... Args>(auto, auto& fn, auto& rcvr, Tag, Args&&... args) noexcept -> void {
    if constexpr (same_as<Tag, decayed-typeof<set-cpo>>) {
      TRY-SET-VALUE(rcvr, invoke(std::move(fn), std::forward<Args>(args)...));
    } else {
      Tag()(std::move(rcvr), std::forward<Args>(args)...);
    }
  };
```

*set-cpo* is `set_value`, `set_error` and `set_stopped` for `then`, `upon_error` and `upon_stopped` respectively. When the child operation completes in the corresponding way, `fn` is called and its result is `set_value`d onward: `set_value()` if `fn` returns `void`, `set_error(exception_ptr)` if `fn` throws. Other completions are forwarded unchanged.

| Child sender's signature | `then(f)` | `upon_error(f)` | `upon_stopped(f)` |
|---|---|---|---|
| `set_value_t(int)` | `set_value_t(invoke_result_t<F, int>)` | Unchanged | Unchanged |
| `set_error_t(E)` | Unchanged | `set_value_t(invoke_result_t<F, E>)` | Unchanged |
| `set_stopped_t()` | Unchanged | Unchanged | `set_value_t(invoke_result_t<F>)` |
| Added when `f` may throw | `set_error_t(exception_ptr)` | Same | Same |

When the result type is `void`, the corresponding signature is `set_value_t()`.

The callback is called as an rvalue (`invoke(std::move(fn), ...)`), and only once. A function object whose `operator()` is only `&`-qualified can't be used with `then`.

¶5 *check-types* checks that the callback can be called with every set of arguments of the corresponding completion of the child sender, and throws if not, so computing the signatures fails. Since *make-sender* checks the signatures of non-dependent senders at construction, `then(just(1), [](std::string) {})` is ill-formed on the very line that constructs it ([[exec.snd]]).

¶6 If the sender returned by `then` doesn't work this way (calling `f`, or a copy of it, on the relevant completion and value-completing with its result, while forwarding other completions unchanged), the behavior is undefined. This constrains customized implementations: when a domain replaces the implementation of `then`, it must preserve these semantics.

## write_env and unstoppable

### write_env [exec.write.env]

```cpp title="write-env.cpp"
namespace ex = std::execution;

std::pmr::monotonic_buffer_resource pool;
auto s = ex::write_env(work, ex::prop(std::get_allocator,
                                      std::pmr::polymorphic_allocator<>(&pool)));
// inside work, get_allocator(get_env(rcvr)) gives an allocator that uses pool
```

¶1 When the sender returned by `write_env(sndr, env)` is connected with receiver `rcvr`, it connects `sndr` with a new receiver whose environment is the result of merging `env` on top of `get_env(rcvr)`.

¶2 Ill-formed if `sndr` isn't a sender or `env` isn't a [[g:queryable-object|queryable object]]; otherwise equivalent to *make-sender*(write_env, env, sndr).

¶3–4 The *impls-for* overrides *get-env*: for a query `q`, it asks the written `env` first, and if that can't answer, the outer environment (through *FWD-ENV*). The written environment takes priority.

¶5 *check-types* computes the child sender's signatures in the merged environment.

Two things to note. The written environment is visible only to the child sender; it doesn't change the attributes of the `write_env` sender itself. The outer environment goes through *FWD-ENV*, so only forwarding queries get through; the written environment, by contrast, is fully visible, including non-forwarding queries.

### unstoppable [exec.unstoppable]

¶1–2 `unstoppable(sndr)` is equivalent to `write_env(sndr, prop(get_stop_token, never_stop_token{}))`.

The stop token the child sender sees is always `never_stop_token`, so outer cancellation requests never reach it. This suits work that must run to completion, such as committing a transaction or releasing resources. `unstoppable_token<never_stop_token>` is true, so the child sender may also use this to drop the `set_stopped_t()` signature at the type level, as the schedule sender of `run_loop` does ([[exec.run.loop]]).

## into_variant [exec.into.variant]

¶1 `into_variant` turns a sender with several value completion signatures into a sender with only one value signature, whose value is a variant of tuples. For example:

| Child sender's value signatures | Value signature of `into_variant` |
|---|---|
| `set_value_t(int)`, `set_value_t(std::string, double)` | `set_value_t(std::variant<std::tuple<int>, std::tuple<std::string, double>>)` |

Constructing the variant may throw, so there may also be an extra `set_error_t(exception_ptr)`.

¶2–3 Ill-formed if `sndr` isn't a sender; otherwise equivalent to *make-sender*(into_variant, {}, sndr). ¶4 *check-types* requires all the child sender's results to be decay-copyable. ¶5 *get-state* is used only to carry the variant type. ¶6 *complete* constructs the variant and `set_value`s it on a value completion, forwarding other completions unchanged.

`when_all` requires each child sender to have only one value signature ([[exec.when.all]]), and so does `sync_wait` ([[exec.consumers]]). `into_variant` is the adapter layer for handing multi-signature senders to them; `when_all_with_variant` and `sync_wait_with_variant` simply wrap a layer of `into_variant` internally.

## stopped_as_optional and stopped_as_error

### stopped_as_optional [exec.stopped.opt]

```cpp title="stopped-as-optional.cpp"
namespace ex = std::execution;

// suppose cancellable_read() has signatures set_value_t(int), set_stopped_t()
auto s = cancellable_read() | ex::stopped_as_optional;   // set_value_t(optional<int>)
if (auto r = std::this_thread::sync_wait(std::move(s))) {
  auto [opt] = *r;     // an empty opt means it was cancelled
}
```

¶1 `stopped_as_optional` turns a stopped completion into a value completion whose value is an empty `optional`, and wraps the original values in an `optional` too. The resulting sender never completes with stopped.

In a pipeline it is written `| stopped_as_optional`, without parentheses: it takes only one sender, so it is itself a closure object ([exec.adapt.obj] ¶4).

¶2 Equivalent to *make-sender*(stopped_as_optional, {}, sndr). ¶3 *check-types* additionally requires the child sender to have exactly one value signature, and that signature to carry a value (not `set_value_t()`). So `just_stopped() | then([] { return 1; })` can't be used: `just_stopped()` has no value completion, `then`'s callback is never called, and the result's only signature is `set_stopped_t()`.

¶4 It has no implementation of its own; instead, in `transform_sender`, it is rewritten into a composition of other adaptors ([[exec.snd.transform]]):

```cpp
auto&& [_, _, child] = sndr;
using V = single-sender-value-type<child-type<Sndr>, FWD-ENV-T(Env)>;
return let_stopped(
  then(std::forward_like<Sndr>(child),
       []<class... Ts>(Ts&&... ts) noexcept(is_nothrow_constructible_v<V, Ts...>) {
         return optional<V>(in_place, std::forward<Ts>(ts)...);
       }),
  []() noexcept { return just(optional<V>()); });
```

Values are wrapped in an `optional` by `then`, and cancellation is replaced by `let_stopped` with a `just` that sends an empty `optional`. When the child sender's signatures can't be computed at all in that environment, the result of the rewrite is *not-a-sender*(), deferring the error until signatures are computed.

### stopped_as_error [exec.stopped.err]

¶1 `stopped_as_error(sndr, err)` turns a stopped completion into an error completion with `err` as its datum; the result never completes with stopped. This suits callers that don't distinguish cancellation from failure, or that need to turn cancellation into a specific error code (such as `errc::operation_canceled`) for code that handles only errors.

¶2 Ill-formed if `sndr` isn't a sender or `err` doesn't satisfy *movable-value*; otherwise equivalent to *make-sender*(stopped_as_error, err, sndr).

¶3 It too is rewritten into `let_stopped`:

```cpp
auto&& [_, err, child] = sndr;
using E = decltype(auto(err));
return let_stopped(
  std::forward_like<Sndr>(child),
  [err = std::forward_like<Sndr>(err)]() mutable noexcept(is_nothrow_move_constructible_v<E>) {
    return just_error(std::move(err));
  });
```

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[exec.adapt.general] ¶1 only says that this subclause specifies a set of sender adaptors.

[exec.adapt.obj] ¶1 and ¶5 specify that `c | d` and `adaptor(args...)` are well-formed only if all the state entities of the new closure can be initialized. ¶5.3 writes the call pattern as `adaptor(rcvr, bound_args...)`, where `rcvr` refers to the argument passed when the closure is called, that is, the sender.

</details>

## Questions

!!! question "1. Combining then and upon_error"
    What are the signatures of `just(1) | then([](int) -> int { throw 1; }) | upon_error([](std::exception_ptr) { return 0; })`? What does `sync_wait` get?

<details markdown="1">
<summary>Answer</summary>

`then`'s callback may throw, so the intermediate sender's signatures are `set_value_t(int)` and `set_error_t(exception_ptr)`. `upon_error` turns the error into a value; `invoke_result_t<F, exception_ptr>` is `int`, giving `set_value_t(int)`, which coincides with the value signature forwarded unchanged and counts only once. `upon_error`'s callback isn't declared noexcept, so there is also `set_error_t(exception_ptr)`.

At run time, `then`'s callback throws an `int`; *TRY-SET-VALUE* catches it and calls `set_error(exception_ptr)`; `upon_error`'s callback returns 0, so `set_value(0)`. `sync_wait` returns an `optional<tuple<int>>` holding 0.
</details>

!!! question "2. Can write_env override the stop token?"
    The outer receiver's environment has stop token `t1`. After `write_env(sndr, prop(get_stop_token, t2))`, which one does `sndr` see? When the outer side requests a stop, is `sndr` cancelled?

<details markdown="1">
<summary>Answer</summary>

It sees `t2`: the merged environment asks the written part first ([exec.write.env] ¶4.2). A stop requested through `t1` from outside doesn't reach `sndr`, because `sndr` can't get `t1` at all: `write_env` overrides rather than combining the two tokens. To cancel when either token fires, the two tokens have to be combined into one, which is what the exposition-only *stop-when* in [[exec.spawn]] does.
</details>
