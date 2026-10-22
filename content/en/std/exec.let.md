---
title: let_value / let_error / let_stopped
summary: "When the predecessor completes, call the callback with its results to get a new sender, then immediately connect and start that sender; the results are kept until the second operation ends, so they can safely be used by reference."
updated: 2026-10-19
---

!!! tldr
    - `then(f)` attaches a synchronous function; `let_value(f)` attaches an asynchronous step: `f` returns a sender, and that sender's completion is the completion of the whole operation.
    - The predecessor's results are copied into `let_value`'s operation state, passed to `f` as lvalues, and live until the second operation completes, so the second sender can use them by reference.
    - The callback's parameters must be references to use this storage; taking them by value gives the callback local copies.
    - The operation states of the predecessor and of the second operation share one `variant`; the predecessor is destroyed inside its own completion function.
    - `let_error` and `let_stopped` do the same for error and stopped completions; `let_stopped`'s callback must take no arguments.

The examples on this page use C++26 `std::execution` senders. The libc++ shipped with Clang 23 doesn't implement this part of the library yet, so none of the examples have been verified by compiling, and they carry no verdict.

## The callback returns a sender

A [[g:sender|sender]] describes a piece of asynchronous work that hasn't started yet. `then(f)` calls `f` synchronously after the predecessor produces its values, and `f`'s return value becomes the new result. But the next step is often itself asynchronous, and what it should do is only known once the previous step's result is available: only after reading the request do you know which table to query.

`let_value(f)` solves this. `f` takes the predecessor's values and returns a sender; `let_value` connects that sender to a receiver and starts it, taking its completion as the completion of the whole operation. In functional programming terms, `then` is `map` and `let_value` is `flat_map`.

```cpp title="let-value.cpp"
namespace ex = std::execution;

ex::sender auto handle(connection& conn) {
  return read_request(conn)                    // completes with set_value(request)
       | ex::let_value([&conn](request& req) { // req is an lvalue reference
           return query_db(req.table)          // completes with set_value(rows)
                | ex::then([&req](rows r) {    // can safely refer to req
                    return make_response(req, r);
                  });
         });
}
```

The object `req` refers to is stored in `let_value`'s own [[g:operation-state|operation state]], and lives until the operation `query_db(...) | then(...)` completes. So it is safe for the inner lambda to capture `req` by reference. The section on the operation state below shows how this is guaranteed.

## Construction: let_value(sndr, f) (¶1–4)

¶1 The three adaptors turn the predecessor's value completion, error completion and stopped completion, respectively, into a new child asynchronous operation: the predecessor's result datums are passed to a user-provided callable, which returns a new sender, and that sender is then connected and started.

¶2 Below, *set-cpo* denotes the completion function corresponding to the adaptor: `set_value` for `let_value`, `set_error` for `let_error`, `set_stopped` for `let_stopped`. The other two kinds of completion don't go through the callback; they are forwarded unchanged to the outer receiver.

¶3 All three names are pipeable sender adaptor objects, so you can write either `let_value(sndr, f)` or `sndr | let_value(f)`. The expression is ill-formed if `sndr` isn't a sender, or if `f` can't be moved or copied into an independent value (doesn't satisfy *movable-value*).

In addition, `let_stopped(sndr, f)` requires `f` to be callable with zero arguments. A stopped completion carries no data, so this can be checked at construction, without waiting for connect.

¶4 When these conditions hold, the result is a sender with `f` as its data and `sndr` as its child sender (*make-sender*, see [[exec.snd]]).

## The operation state: store the results first, then switch operations (¶10–15)

After connect, the state of the whole operation is a *let-state* object with four main members:

```cpp
struct let-state {           // simplified
  Fn fn;                     // the user callback
  env_t env;                 // the second operation's environment, see the next section
  ArgsVariant args;          // variant<monostate, decayed-tuple<predecessor results>...>
  OpsVariant ops;            // variant<monostate, predecessor op, second op...>
};
```

¶12 `args` can hold the results of every corresponding completion of the predecessor. For example, if the predecessor may complete with `set_value(int)` or `set_value(string, int)`, `args` is `variant<monostate, tuple<int>, tuple<string, int>>`. The result types are all decayed, that is, references and cv-qualifiers are removed.

¶13 `ops` reserves room for both the predecessor's operation state and the second operation's operation state. The type of the second sender is the type obtained by calling the callback with lvalues, that is, the return type of `f(decay_t<Args>&...)`; there may be as many kinds of second sender as the predecessor has corresponding completions.

¶10 When the *let-state* is constructed, the predecessor's operation state is constructed in place in `ops`. ¶15 Starting the whole operation means starting this predecessor operation.

### What happens when the predecessor completes

When the predecessor completes with the corresponding completion function, *impl* performs the following five steps (the exposition code in ¶10, slightly simplified):

```cpp
try {
  auto& tuple = args.emplace<args_t>(std::forward<Ts>(ts)...); // 1
  ops.emplace<monostate>();                                    // 2
  auto&& sndr = apply(std::move(fn), tuple);                   // 3
  auto& op = ops.emplace<op_t>(                                // 4
      emplace-from{[&] { return connect(sndr, receiver2{rcvr, env}); }});
  start(op);                                                   // 5
} catch (...) {
  if constexpr (!nothrow) set_error(std::move(rcvr), current_exception());
}
```

1. Copy the results into `args`. The arguments the predecessor passes may refer to objects in its own operation state, and the next step destroys that operation state, so they must be copied first.
2. Destroy the predecessor's operation state, setting `ops` to `monostate`. This happens while the predecessor is calling its completion function. [[exec.async.ops#8]] allows an operation state's lifetime to end during the execution of the completion operation, and the predecessor doesn't access itself after calling the completion function.
3. Call the callback. `tuple` is an lvalue, so each result is passed as `decay_t<Args>&`, and the callback's parameters can be `T&`, `const T&` or by value.
4. Construct the second operation state in place where `ops` was. Operation states can't be moved ([[exec.opstate]]), so *emplace-from* is used to construct the return value of `connect` directly into the `variant`.
5. Start the second operation. When it completes, *receiver2* forwards the completion unchanged to the outer receiver.

The other two kinds of completion don't go through these five steps; they are forwarded directly to the outer receiver.

`ops` is a `variant` rather than two separate members because once the predecessor completes its operation state is of no further use. The two share one block of storage, so the size of the whole operation state is the larger of the two rather than their sum. A long chain of nested `let_value`s saves quite a bit of space this way.

### Exceptions

The `nothrow` in ¶10 is true only if three things can't throw: copying the results into `args`, calling the callback, and connecting the second sender. Otherwise the `catch` branch hands the exception to the outer receiver as `set_error(exception_ptr)`, and the whole sender's completion signatures gain a `set_error_t(exception_ptr)` entry.

Completion signatures have to be computed before connect, when only the receiver's environment type is known. [[exec.connect#6]] requires that whether connect is noexcept depend only on the environment type precisely so that computations like this work.

## Where the second operation runs (¶2, ¶8)

The callback is called where the predecessor completes, and the second sender is connected and started there too. If the predecessor completes on a thread pool, the callback runs on a thread-pool thread.

¶2 *let-env* writes this fact into the second operation's environment. It takes the first well-formed result of the following:

- ¶2.1 the predecessor's [[g:completion-scheduler|completion scheduler]] for the corresponding completion, as the second operation's `get_start_scheduler`;
- ¶2.2 failing that, just the predecessor's completion domain;
- ¶2.3 the empty environment `env<>{}`.

¶8 When *receiver2*, the receiver used by the second operation, answers an environment query, it looks in the result of *let-env* first; if not found there and the query is a [[g:forwarding-query|forwarding query]], it looks in the outer receiver's environment; otherwise the query is ill-formed. Senders like `on`, `affine_on` and `task` that need to know which scheduler they were started on can then make the right decision.

## Type checking (¶9)

¶9 When completion signatures are computed, *check-types* checks, for each corresponding completion `set-cpo(Ts...)` of the predecessor, that:

- ¶9.1 each `Ts` can be decay-copied;
- ¶9.2 the callback can be called with `decay_t<Ts>&...`;
- ¶9.3 the callback's return value is a sender;
- ¶9.4 with an environment, that sender's completion signatures can be computed in the second operation's environment.

If any of these fails, *check-types* throws an exception. It runs during constant evaluation, so this shows up as a compile error.

## let_error and let_stopped

`let_error(f)` continues with the sender returned by `f(err)` when the predecessor completes with an error, which suits retrying or falling back to a cache. `let_stopped(f)` continues with the sender returned by `f()` when the predecessor is cancelled. `stopped_as_optional` and `stopped_as_error` in [[exec.adapt]] are both implemented with `let_stopped`.

```cpp title="let-error-fallback.cpp"
namespace ex = std::execution;

auto fetch_with_fallback = fetch_remote()
  | ex::let_error([](auto&& err) {   // when the remote fails, read the local cache instead
      return read_cache();
    });
```

If the predecessor may complete with several error types, the callback must be callable with each of them (¶9.2). The sender types returned for different errors may differ; `ops` reserves an alternative for each.

## Common mistakes

### Taking by value, then returning a sender that refers to it

<div class="compare" markdown="1">

```cpp
| ex::let_value([](request req) {
    return ex::just()
         | ex::then([&req] { use(req); });
  })
// UB: req is the callback's local copy,
// destroyed when the callback returns
```

```cpp
| ex::let_value([](request& req) {
    return ex::just()
         | ex::then([&req] { use(req); });
  })
// OK: req refers to the object stored by let_value,
// which lives until the second operation completes
```

</div>

`let_value` only guarantees that the `decay_t<Args>` objects it stores itself live until the second operation ends.

### Thinking the callback is called at connect

The callback is called when the predecessor completes, and runs on the execution agent where the predecessor completed, the same as with `then`. The second sender is connected at that time too. Code in the callback has to consider which thread it runs on; the second sender can find this out from `get_start_scheduler` in its environment.

## Questions

!!! question "1. Why can the two operation states share storage?"
    The predecessor's operation state is destroyed inside its own completion function. Which rules allow this?

<details markdown="1">
<summary>Answer</summary>

[[exec.async.ops#7]]: the lifetime of an asynchronous operation ends when the completion operation begins executing, and from then on the predecessor's implementation can't access its own operation state. [[exec.async.ops#8]]: an operation state's lifetime can end during the execution of the completion operation. In addition, step 1 copies the results into `args` first, so even if the arguments the predecessor passed refer to objects inside its operation state, nothing dangles after it is destroyed.
</details>

!!! question "2. The callback throws"
    When `let_value`'s callback throws, what does the outer receiver get? What state are `args` and `ops` in at that point?

<details markdown="1">
<summary>Answer</summary>

Step 1 has already stored the results in `args`, step 2 has already set `ops` to `monostate`, and after step 3 throws, control enters the `catch`. When the callback isn't declared noexcept, `nothrow` is false, the outer receiver gets `set_error(exception_ptr)`, and the completion signatures include `set_error_t(exception_ptr)`. Afterwards `args` still holds the copies of the results and `ops` is `monostate`; they are destroyed along with the whole operation state.

If the callback is declared noexcept and copying and connect can't throw either, the `set_error` in the `catch` isn't instantiated, and the signatures don't include that entry.
</details>

## Summary

| Question | Answer |
|---|---|
| When is the callback called | When the predecessor completes with the corresponding completion function, on the execution agent where it completed |
| What does the callback receive | Copies of the results stored in the operation state, passed as lvalues |
| How long do the results live | Until the second operation completes |
| Storage cost | The predecessor and the second operation share one `variant` |
| Start scheduler of the second operation | The predecessor's completion scheduler (¶2.1) |
| Callback or connect throws | The outer receiver gets `set_error(exception_ptr)` |

<details class="fine" markdown="1"><summary>Remaining wording</summary>

¶5–6 Before connect, `let_value(sndr, f)` is rewritten into an internal sender: its tag is *let-tag* (a private empty type, one for each of the three adaptors), its data is *let-data*`{sndr, f}`, and it has no child senders. The child sender is moved into the data because `let` has to manage the predecessor's connect itself (putting it into the `ops` `variant`), rather than leaving it to the general *connect-all*.

¶7 *impls-for*<*let-tag*> customizes *get-state*, *start* and *check-types*, and uses the defaults for the rest.

¶11 *get-state* takes the child sender and the callback out of the *let-data* and constructs the *let-state*. ¶14 Its constraint is that both `args_variant_t` and `ops_variant_t` are well-formed. The draft writes `ops2_variant_t` here, a name that doesn't appear in ¶13; it is presumably a typo.

¶16 If `let_value(sndr, f)` is replaced by another implementation through domain customization, that implementation must still ensure that `f` is called when `sndr` completes with the corresponding completion function, that the whole operation's completion depends on the completion of the sender `f` returns, and that `sndr`'s other completions are propagated unchanged. Otherwise the behavior of connect is undefined.

</details>
