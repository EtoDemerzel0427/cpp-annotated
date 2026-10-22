---
title: when_all
summary: "Starts several child senders at once and completes only when all of them have completed; on success it concatenates the children's values in order, and when any child fails or is cancelled it asks the rest to stop."
updated: 2026-10-19
---

!!! tldr
    - `when_all(s1, s2, ...)` starts all child senders at once and completes only after all of them have completed; on success it concatenates the children's values, in order, into one value completion.
    - Each child sender has at most one value completion signature; one with several must first be wrapped in `into_variant`, or `when_all_with_variant` used instead.
    - The stop token child operations see comes from an `inplace_stop_source` inside `when_all`. Outer stop requests are forwarded into it, and when some child fails or is cancelled, `when_all` issues a stop request itself.
    - Only the first error is kept; errors take priority over cancellation; once some child fails or is cancelled, the other children's values are discarded.
    - A stop request is only a request: `when_all` always waits for every child to actually complete, so no child is still running after it completes.

The examples on this page use C++26 `std::execution` senders. The libc++ shipped with Clang 23 doesn't implement this part of the library yet, so none of the examples have been verified by compiling, and they carry no verdict.

## fork-join

```cpp title="when-all.cpp"
namespace ex = std::execution;

auto pool = ex::get_parallel_scheduler();
auto a = ex::schedule(pool) | ex::then([] { return 1; });
auto b = ex::schedule(pool) | ex::then([] { return std::string("two"); });
auto [x, y] =
    std::this_thread::sync_wait(ex::when_all(std::move(a), std::move(b))).value();
// x == 1, y == "two": values are concatenated in the order of the child senders
```

¶1 `when_all` is fork-join: it combines several input [[g:sender|senders]] into one sender that completes only after all inputs have completed. On success, it concatenates all the children's values in order as its own value completion. In the example, the two child senders produce an `int` and a `std::string`, so `when_all` completes with `set_value(int, std::string)`.

The children are [[g:child-operation|child operations]] of the `when_all` operation ([[exec.async.ops#2]]). `when_all` always completes only after all its children have completed, which is the basic guarantee of structured concurrency: when the caller gets the result, no child is still running in the background.

¶2 `when_all(sndrs...)` is ill-formed if there are no arguments or some argument isn't a sender. ¶3 Otherwise the result is a sender with `sndrs...` as its child senders and no extra data.

## Requirements on child senders (¶8–9)

¶9 When completion signatures are computed, *check-types* checks two things for each child sender:

- it has at most one value completion signature, otherwise it's an error;
- all its result datums can be decay-copied, because they must be stored until the other children complete.

The requirement is at most one, not exactly one. A child sender with no value completion (such as `just_stopped()`) is allowed; it just means the whole `when_all` can never succeed. A child sender with several value signatures, for instance one that may complete with `set_value(int)` or `set_value(string)`, must first be turned by `into_variant` into one with the single signature `set_value(variant<tuple<int>, tuple<string>>)`, or you can use `when_all_with_variant`, described below.

## Cancelling siblings: the internal stop token (¶5–7, ¶10, ¶16)

¶10 The environment of each child's receiver is produced by *make-when-all-env*. ¶6 Querying `get_stop_token` on this environment gives the token of `when_all`'s own `inplace_stop_source`, not the outer receiver's token. Among other queries, [[g:forwarding-query|forwarding queries]] are answered by the outer environment, and the rest are ill-formed.

¶16 At start, `when_all` first registers a callback on the outer token, then starts all the children in turn:

```cpp
state.on_stop.emplace(get_stop_token(get_env(rcvr)),
                      on-stop-request{state.stop_src});
(start(ops), ...);
```

When the outer side requests a stop, the callback calls `stop_src.request_stop()`, and all children see the request. When some child fails or is cancelled, `when_all` also calls `stop_src.request_stop()` directly, telling the remaining children to stop. Using an internal token, rather than handing the outer token straight to the children, is precisely what lets `when_all` initiate a stop itself.

## When a child completes (¶11–14, ¶17)

¶11 The state of `when_all` has a few key members:

```cpp
atomic<size_t> count{sizeof...(sndrs)};          // number of children not yet completed
inplace_stop_source stop_src{};
atomic<disposition> disp{disposition::started};  // started, error or stopped
errors_variant errors{};                         // holds the first error
values_tuple values{};                           // one optional<tuple<values...>> per child
optional<stop_callback> on_stop{nullopt};        // callback on the outer token
```

¶13 `values` has an `optional<tuple<values...>>` for each child sender. If some child sender has no value signature, that type can't be formed, and the whole of `values` degenerates to an empty `tuple<>`. ¶14 `errors` is a `variant` that can hold every error type the children may produce; ¶12 if copying result datums may throw, it can also hold an `exception_ptr`.

¶17 When each child completes, `disp` is updated according to the kind of completion, and then `count` is decremented:

| Child's completion | Handling |
|---|---|
| Error | Set the state to error with `disp.exchange(error)`; if it wasn't error before, request a stop and save this error |
| Stopped | Only if `disp` is still started, change it to stopped and request a stop |
| Value | Only if `disp` is still started, store the values in `values` |
| Any | Decrement `count`; when it reaches 0, complete the whole operation |

Three rules follow from this:

- Errors take priority over cancellation. `exchange` writes error unconditionally, even if the state was already stopped, whereas stopped can only be reached from started.
- Only the first error is kept. A later error finds that `exchange` returned error already, and does nothing.
- Once `disp` leaves started, values arriving later aren't stored, and values already stored end up unused.

If copying throws while storing values, the handler calls itself recursively, treating this completion as `set_error(exception_ptr)`, and then returns directly. The recursive call has already decremented `count` once, so it isn't decremented again here.

## Completing the whole operation (¶15)

When the last child decrements `count` to 0, *complete* is called:

- ¶15.1 `disp` is still started: unwrap and concatenate each `optional<tuple<...>>`, and hand them to the outer receiver with `set_value`.
- ¶15.2 `disp` is error: call `set_error` with the saved error.
- ¶15.3 Otherwise (stopped): call `set_stopped`, as long as some child sender may complete with stopped.

Each branch first does `on_stop.reset()` before completing, deregistering the callback on the outer token. [[exec.recv#3]] only guarantees that the outer stop token is valid during the lifetime of the asynchronous operation, and that lifetime ends when the completion function is called, so the callback registered on it must be destroyed before then.

`when_all` completes on the execution agent of whichever child completes last, and which one that is can't be known in advance. So it generally doesn't report a [[g:completion-scheduler|completion scheduler]] ([[exec.snd.general#4]]), and reports a completion domain only when the children's completion domains can be unified ([[exec.snd.general#3]]).

Suppose two child senders complete with `set_value(A...)` and `set_value(B...)` respectively; the completion signatures of `when_all` are:

- `set_value_t(decay_t<A>..., decay_t<B>...)`;
- each child sender's error signatures (with the error types decayed), plus `set_error_t(exception_ptr)` when needed;
- `set_stopped_t()`, if and only if some child sender may complete with stopped.

An outer stop request by itself doesn't make `when_all` complete with stopped. If all children ignore the request and complete with values as usual, `disp` stays started, and the result is still `set_value`.

## when_all_with_variant (¶18–19)

¶18–19 `when_all_with_variant(sndrs...)` is rewritten at connect into `when_all(into_variant(sndrs)...)`, unless the receiver's domain specifically customizes it (Note 1). Each child sender is first collapsed by `into_variant` into a single value signature, so it accepts child senders with several value signatures.

## Common misconceptions

### when_all is not when_any

`when_all` waits for all children to complete; the standard has no `when_any` that returns as soon as one completes. After one child fails, the other children don't stop immediately either: a stop request is only a request, and children may ignore it (for example, [[exec.bulk#10]] explicitly allows `bulk` to ignore cancellation requests). `when_all` waits until they have actually completed.

### A value completion that never happens

In `when_all(just(1), just_stopped())`, the second child sender has no value signature, so `values` degenerates to `tuple<>`. The second child necessarily completes with stopped, so `disp` can't remain started, and the `set_value` branch of ¶15.1 is never reached at run time.

But this branch isn't inside an `if constexpr`, so it is still potentially evaluated. Completion signatures are computed from the completion operations potentially evaluated in the default implementation ([[exec.snd.general#1]]), so the result's signatures include a `set_value_t()`, representing a completion that never happens.

## Questions

!!! question "1. Two children fail at the same time"
    Two children complete with different errors at almost the same time. Which one does the outer receiver get? Is there a data race?

<details markdown="1">
<summary>Answer</summary>

It gets the one for which `disp.exchange(error)` didn't return error, that is, the one whose exchange comes first in the modification order of `disp`.

There's no data race. `disp` and `count` are both atomic objects; `errors` is written only by the child that wins the exchange; and *complete*, which reads `errors`, happens after the last decrement of `count`. The decrements of `count` are read-modify-write operations with the default `seq_cst`, which establish a happens-before relationship between the write of `errors` and its read ([[intro.races]]).
</details>

!!! question "2. Outer cancellation and children's cancellation"
    The outer side requests a stop and both children complete with stopped. What does `when_all` complete with? What if one of them had already completed with a value before receiving the stop request?

<details markdown="1">
<summary>Answer</summary>

When the outer side requests a stop, the callback calls `stop_src.request_stop()`, and the children see the stop request. The first child to complete with stopped changes `disp` from started to stopped; the second one's `compare_exchange` fails, and it does nothing. Finally *complete* takes ¶15.3 and calls `set_stopped`.

If one of them completed with a value first, `disp` was still started at that time, and the values were stored in `values`. But `disp` ends up stopped, the stored values are discarded, and `when_all` still completes with stopped.
</details>

## Summary

| Question | Answer |
|---|---|
| When does it complete | After all children have completed, on the execution agent of the last one to complete |
| Result on success | The children's values concatenated in order |
| Requirements on child senders | At most one value signature; results decay-copyable |
| Children's stop token | The token of `when_all`'s internal `inplace_stop_source` |
| Several children fail | The first error wins; errors take priority over cancellation |
| Several value signatures | `into_variant` first, or use `when_all_with_variant` |

<details class="fine" markdown="1"><summary>Remaining wording</summary>

¶4 *impls-for*<when_all_t> customizes *get-env*, *get-state*, *start*, *complete* and *check-types*.

¶5–7 define *make-when-all-env* and the corresponding type alias *when-all-env*<Env>. ¶8 *check-types* iterates over each child sender using *indices-for*<Sndr>.

¶11 *get-state* constructs the state object listed above through *make-state*. ¶14's `errors` has an empty type *none-such* as its default first alternative, with duplicate types removed.

</details>
