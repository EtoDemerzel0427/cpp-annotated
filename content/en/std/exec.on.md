---
title: Switching execution resources
summary: "Three adaptors that control where work runs: starts_on(sch, s) starts s on sch; continues_on(s, sch) stores s's result when it completes, hops onto sch and hands it over there; on goes to sch, does the work and comes back; schedule_from is the hook through which a scheduler customizes how execution leaves it."
updated: 2026-10-19
---

!!! tldr
    - `starts_on(sch, s)` starts `s` on `sch`; wherever `s` completes, the whole operation completes there.
    - `continues_on(s, sch)` stores the result when `s` completes, schedules onto `sch`, and then hands it to the receiver. All three kinds of completion (value, error, stopped) go through this transfer, and results of reference type become values.
    - `on(sch, s)` goes to `sch`, finishes `s`, and comes back to where the operation was started; `s | on(sch, closure)` runs a closure on `sch` and then comes back to where `s` completed.
    - `on` needs to know the original scheduler; if it can't be obtained from the environment, the error is reported when signatures are computed.
    - `schedule_from` splits `continues_on` into a leaving half and an entering half, so the schedulers on the source side and the destination side can each customize their part.

The examples on this page have not been verified by compiling: the libc++ shipped with Clang 23 doesn't implement the sender part of `std::execution` yet, so they carry no verdict.

## Where to start, where to continue

An asynchronous operation can start on one execution resource and complete on another ([[exec.async.ops#2]]). This group of adaptors lets a program control that explicitly:

| Adaptor | Meaning |
|---|---|
| `starts_on(sch, s)` | Start `s` on `sch` |
| `continues_on(s, sch)` | After `s` completes, move to `sch` and hand over the result there |
| `on(sch, s)` | Finish `s` on `sch`, then come back to where we were |
| `on(s, sch, closure)` | After `s` completes, move to `sch` and run `closure`, then come back to where `s` completed |
| `schedule_from(s)` | For schedulers to customize how execution leaves them; users generally don't call it directly |

Note that the argument order follows the order of events: `starts_on` puts the scheduler first, `continues_on` puts the sender first.

```cpp title="on.cpp"
namespace ex = std::execution;

ex::sender auto handle(ex::scheduler auto pool) {
  return ex::just(load_request())
       | ex::on(pool, ex::then([](auto req) { return parse(req); }))  // parse on the thread pool, then come back
       | ex::then([](auto doc) { show(doc); });                        // back where just completed
}
```

`just` completes synchronously wherever `start` is called. `on` sends the parsing work to `pool` and comes back there once parsing is done, so `show` runs in the same place as `just`.

## starts_on [exec.starts.on]

¶1 `starts_on` adapts an input sender into a sender that will start on the execution resource of a [[g:scheduler|scheduler]].

¶2–3 Ill-formed if `sch` isn't a scheduler or `sndr` isn't a sender; otherwise equivalent to *make-sender*(starts_on, sch, sndr).

¶4 `starts_on` has no implementation of its own. At connect, `transform_sender` ([[exec.snd.transform]]) rewrites it into a composition of other adaptors:

```cpp
auto&& [_, sch, sndr] = out_sndr;
return let_value(
  continues_on(just(), sch),
  [sndr = std::forward_like<OutSndr>(sndr)]() mutable
    noexcept(is_nothrow_move_constructible_v<decay_t<OutSndr>>) {
    return std::move(sndr);
  });
```

`continues_on(just(), sch)` hops onto `sch` and then completes with `set_value()`. `let_value` then calls the callback to get `sndr`, and connects and starts it right where it is (that is, on `sch`) ([[exec.let]]). `let_value` also puts the predecessor's completion scheduler `sch` into `sndr`'s environment as the answer to `get_start_scheduler`, so `sndr` knows it was started on `sch`.

¶5 Semantic requirement: `start(op)` must start `sndr` on `sch`'s execution resource. If scheduling onto `sch` fails, an error completion is executed on the outer receiver on an unspecified execution agent.

`starts_on` isn't responsible for coming back: wherever `sndr` completes, `starts_on` completes there.

## continues_on [exec.continues.on]

¶1 `continues_on` schedules work that depends on the completion of a sender onto a scheduler's execution resource.

¶2–3 `continues_on(sndr, sch)` is equivalent to *make-sender*(continues_on, sch, schedule_from(sndr)): the child sender is wrapped in a layer of `schedule_from`, for reasons explained in the next section.

It is the only adaptor in this group with a full *impls-for* implementation (the hooks are explained in [[exec.snd]]), and its work happens in three steps.

¶5 Step one happens at connect: *get-state* connects `schedule(sch)` in advance, and the state has three members:

```cpp
struct state-type {
  Rcvr& rcvr;                 // the outer receiver
  variant_t async-result;     // the child sender's result
  operation_t op-state;       // the result of connect(schedule(sch), receiver_t{this})
};
```

¶8 `variant_t` is `variant<monostate, ...>`, with one `tuple<Tag, decay_t<Args>...>` for each completion signature `Tag(Args...)` of the child sender, duplicates removed. If decay-copying some result may throw, a `tuple<set_error_t, exception_ptr>` is added.

¶11 Step two happens when the child sender completes: *complete* first stores the completion tag and results in `async-result`, then starts the schedule operation connected in advance. An exception thrown while storing is caught and stored as `set_error` plus an `exception_ptr`.

¶9 Step three happens when the schedule operation completes, in its receiver:

- `set_value()`: scheduling succeeded, and we are now on `sch`. Take out the stored tag and results and do `tag(std::move(rcvr), std::move(args)...)`, completing the outer receiver;
- `set_error(err)`: scheduling failed; pass the error on to the outer receiver;
- `set_stopped()`: scheduling was cancelled; call `set_stopped` on the outer receiver.

¶6 *check-types* requires the schedule sender to have signatures in this environment, and the child sender's results all to be decay-copyable, since they have to be stored.

¶12 Semantic requirement: `start(op)` starts `sndr` on the current execution agent, and executes the completion operation on the outer receiver on `sch`'s execution resource. If scheduling fails, the error completion is executed on an unspecified execution agent.

The results must be stored: the child operation completes on resource A, and the results can only be handed over after scheduling onto B, but as soon as the child's completion function returns, references it passed may become invalid. So reference types in the signatures become value types: the child sender's `set_value_t(const std::string&)` becomes `set_value_t(std::string)` after `continues_on`.

Error and stopped completions are stored in `async-result` too, and forwarded only after scheduling onto `sch`. So apart from the case where scheduling itself fails, all of `continues_on`'s completions happen on `sch`.

## schedule_from [exec.schedule.from]

¶1 `schedule_from(sndr)` is equivalent to *make-sender*(schedule_from, {}, sndr). It has no dedicated *impls-for*; it uses the default implementation, which forwards the child sender's completions unchanged. Note 1 explains that it is for schedulers to control how execution leaves their execution context.

`continues_on(sndr, sch)` involves two execution resources: where `sndr` completes (the source) and `sch` (the destination). Execution domains choose implementations by completion domain ([[exec.snd.transform]]), and the two layers correspond exactly to the two ends:

- the completion domain of the outer `continues_on` is the domain of the destination `sch`, so the destination side can customize `continues_on` to control how execution enters;
- the completion domain of the inner `schedule_from(sndr)` is the domain of the source, so the source side can customize `schedule_from` to control how execution leaves.

For example, `sndr` completes on a GPU and needs to move to a CPU thread pool. The GPU side may need to synchronize the device stream first and copy the results back to host memory, which the GPU's domain does by customizing `schedule_from`; the thread pool side handles enqueuing. Each side takes care of its half without needing to know about the other.

## on [exec.on]

¶1 `on` has two forms:

- ¶1.1 `on(sch, sndr)`: starts `sndr` on `sch`, and after `sndr` completes, transfers execution back to the execution resource on which the `on` sender was started;
- ¶1.2 `on(sndr, sch, closure)`: after `sndr` completes, transfers to `sch`, runs the sender adaptor closure `closure` with `sndr`'s results, and then transfers back to the execution resource on which `sndr` completed.

¶2–4 `sch` must be a scheduler. In the first form `sndr` must be a sender or a closure object, but not both; in the second form `closure` must be a pipeable sender adaptor closure object ([[exec.adapt]]). `on` is a pipeable adaptor object, so `on(sch, closure)`, missing its sender, returns a closure, and `sndr | on(sch, closure)` is the second form.

¶6 Both forms are rewritten at connect:

```cpp
auto&& [_, data, child] = out_sndr;
if constexpr (scheduler<decltype(data)>) {
  auto orig_sch = call-with-default(get_start_scheduler, not-a-scheduler(), env);
  return continues_on(
    starts_on(std::forward_like<OutSndr>(data), std::forward_like<OutSndr>(child)),
    std::move(orig_sch));
} else {
  auto& [sch, closure] = data;
  auto orig_sch = call-with-default(
    get_completion_scheduler<set_value_t>, not-a-scheduler(), get_env(child), env);
  return continues_on(
    std::forward_like<OutSndr>(closure)(continues_on(std::forward_like<OutSndr>(child), sch)),
    orig_sch);
}
```

- The first is `continues_on(starts_on(sch, sndr), orig_sch)`, where `orig_sch` comes from `get_start_scheduler` on the receiver's environment, that is, where the operation was started.
- The second is `continues_on(closure(continues_on(sndr, sch)), orig_sch)`, where `orig_sch` is `sndr`'s value completion scheduler, that is, where `sndr` completes.

*call-with-default* returns the given default when the call is ill-formed ([[exec.snd]]). When the original scheduler can't be obtained, *not-a-scheduler* is used: its `schedule()` returns a *not-a-sender*, and computing the latter's signatures throws. So the fact that `on` doesn't know where to come back to is reported when signatures are computed, rather than being left until run time.

¶7 Semantic requirements of the first form: `start(op)` remembers the current scheduler (`get_start_scheduler(get_env(rcvr))`), starts `sndr` on `sch`, transfers back to the remembered scheduler after `sndr` completes, and then forwards the results to the outer receiver.

¶8 The second form is similar: remember `sndr`'s value completion scheduler; start `sndr` on the current agent; after it completes, transfer to `sch`; construct `closure(S)` and start it, where `S` is a sender that synchronously sends `sndr`'s results; after that completes, transfer back to the remembered scheduler and forward the results.

In both forms, any scheduling failure completes with an error on an unspecified execution agent.

!!! pitfall "on(sch, s) needs to know where it was"
    The first form requires the receiver's environment to answer `get_start_scheduler`. The environment of `sync_wait` does ([[exec.consumers]]), and so does `task`'s promise type ([[exec.task]]). If the environment of a receiver you wrote yourself doesn't provide it, `on(sch, s)` can't compute its signatures at connect because of *not-a-scheduler*.

## Questions

!!! question "1. Where does it complete after starts_on?"
    In `starts_on(pool, just(1) | then(f))`, where does `f` run? Where does the whole sender complete? How does it differ from `on(pool, just(1) | then(f))`?

<details markdown="1">
<summary>Answer</summary>

`just(1) | then(f)` is started on `pool`; `just` completes synchronously, `f` runs on the same thread, and the whole `starts_on` also completes on a `pool` thread. `on(pool, ...)` has one more step: after completion, it goes back through `continues_on` to the scheduler given by the outer `get_start_scheduler`, such as `sync_wait`'s `run_loop`, and the outer receiver gets the result on the original thread. The only difference is whether it comes back after completion.
</details>

!!! question "2. Does continues_on change the signatures?"
    A child sender's signature is `set_value_t(int&)`, sending an `int` by lvalue reference. What are the signatures of `continues_on(s, sch)`?

<details markdown="1">
<summary>Answer</summary>

`variant_t` stores a `tuple<set_value_t, int>`, and on completion `tag(std::move(rcvr), std::move(args)...)` sends an `int&&`, so the value signature is `set_value_t(int)`. Copying an `int` can't throw, so no extra `set_error_t(exception_ptr)` appears; on top of that come the error and stopped signatures of the schedule sender itself, which depend on `sch`. The reference became a value: that's the price of handing data across execution resources, and also what makes it safe.
</details>
