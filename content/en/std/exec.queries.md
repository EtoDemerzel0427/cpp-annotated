---
title: Queries
summary: "Every query object the standard defines: whom it asks, what its default is, what its result must satisfy, and how forwarding_query decides which queries adaptors forward."
updated: 2026-10-19
---

!!! tldr
    - Queries come in three kinds: those that ask a receiver's environment (allocator, stop token, scheduler and so on), those that ask a scheduler (its forward progress guarantee), and those that ask a sender's attributes (which scheduler or domain it completes on).
    - Only queries that derive from `forwarding_query_t`, or declare themselves forwardable, are forwarded by adaptors to child operations; the standard environment queries are all forwardable.
    - `get_stop_token` defaults to `never_stop_token`, `get_env` defaults to `env<>{}`, and `get_domain` defaults to `default_domain`; `get_allocator` and `get_scheduler` have no default.
    - If you report a completion scheduler or completion domain, you must actually complete there; otherwise the behavior is undefined.
    - Every query calls `query` as const and requires `noexcept`; a `query` that forgets const isn't found, and cancellation silently stops working.

[[exec.queryable]] sets out the general protocol for queryable objects: `q(env)` calls `env.query(q)`. The query objects the standard provides are listed below; Clang 23's libc++ doesn't implement them yet, and the examples below have not been compiled.

| Whom it asks | Queries | Purpose |
|---|---|---|
| A receiver's environment | `get_allocator`, `get_stop_token`, `get_scheduler`, `get_start_scheduler`, `get_delegation_scheduler`, `get_domain` | Resources the caller wants child operations to use |
| A scheduler | `get_forward_progress_guarantee` | Which level of forward progress the scheduler's execution agents provide |
| A sender's attributes | `get_completion_scheduler<Tag>`, `get_completion_domain<Tag>`, `get_await_completion_adaptor` | Where the sender completes, and how to adapt it when a coroutine awaits it |
| Any object | `get_env` | Get a receiver's environment or a sender's attributes |
| A query object | `forwarding_query` | Whether this query should be forwarded |

## Which queries get forwarded ([exec.fwd.env])

```cpp title="my-query.cpp"
struct get_priority_t : std::forwarding_query_t {   // deriving makes it a forwarding query
  template<class Env>
    requires requires (const Env& e) { e.query(get_priority_t{}); }
  int operator()(const Env& e) const noexcept { return e.query(*this); }
};
inline constexpr get_priority_t get_priority{};
```

After a priority is injected with `write_env(sndr, prop(get_priority, 5))`, and `sndr` internally goes through adaptors like `then`, can deeper child operations see it? That depends on `forwarding_query(get_priority)`.

¶1 `forwarding_query` asks a query object whether adaptors should forward it. ¶2 specifies, for a query object `q` of type `Q`:

- ¶2.1 if `q.query(forwarding_query)` is well-formed, the result is that (its type must be `bool`, and it must be a core constant expression if `q` is one);
- ¶2.2 otherwise, if `Q` derives from `forwarding_query_t`, the result is `true`;
- ¶2.3 otherwise it is `false`.

When an adaptor connects a child sender, the environment it gives the child receiver is *FWD-ENV*(get_env(rcvr)) ([[exec.adapt.general#3]]), which contains only forwardable queries. If the `get_priority_t` above didn't derive from `forwarding_query_t`, only `sndr`'s own receiver could see the priority.

Not forwarding by default is the safer choice. Some queries only make sense for the immediate caller: a hypothetical "which child are you" query shouldn't pass through arbitrarily many layers of adaptors to be seen by senders deep inside. All the standard environment queries and completion scheduler queries are declared forwardable.

## Exposition-only tools ([exec.queries.expos])

Later wording uses two exposition-only tools:

¶2 *TRY-QUERY*(q, tag, args...) first tries `AS-CONST(q).query(tag, args...)`, and failing that tries `AS-CONST(q).query(tag)` (`args...` are still evaluated). This lets a `query` member ignore extra arguments it doesn't care about. *AS-CONST* accesses the object as a const lvalue ([[exec.general#9]]).

¶3 *HIDE-SCHED*(q) is a wrapper object for which queries of `get_scheduler_t` and `get_domain_t` are ill-formed, and other queries are forwarded to `q`. It is used to prevent recursion; see `get_scheduler` below.

## Environment queries

### get_stop_token ([exec.get.stop.token])

¶2 If `AS-CONST(env).query(get_stop_token)` is well-formed, the result is that, and its type must satisfy `stoppable_token`; otherwise the result is `never_stop_token{}`.

This is the entry point to the whole library's cancellation mechanism; stop tokens themselves are covered in [[thread.stoptoken]]. A sender takes the stop token from its receiver's environment at `start` and registers a callback on it; the caller requests a stop through the corresponding stop source, and the operation completes with `set_stopped` as soon as it can.

The default `never_stop_token` means a stop can never be requested. `unstoppable_token<never_stop_token>` is true, and many senders use it to drop the `set_stopped_t()` signature at the type level, for example the schedule sender of `run_loop` ([[exec.run.loop]]).

### get_allocator ([exec.get.allocator])

¶2 `get_allocator(env)` calls `AS-CONST(env).query(get_allocator)`, and the result must satisfy *simple-allocator*. It has no default; if the environment doesn't answer, it's ill-formed. Where a default is needed, the specification falls back explicitly to something like `allocator<void>` (as in [[exec.spawn]]).

### get_scheduler ([exec.get.scheduler])

¶1 `get_scheduler` asks for the scheduler associated with a queryable object, that is, where the caller would like subsequent work to run. ¶2 makes `get_scheduler(env)` equivalent to

```cpp
get_completion_scheduler<set_value_t>(
  MANDATE-NOTHROW(AS-CONST(env).query(get_scheduler)),
  HIDE-SCHED(env))
```

The result must satisfy `scheduler`; there is no default.

The extra outer layer of `get_completion_scheduler` is a normalization: the scheduler `s` the environment reports may be a wrapper scheduler whose schedule sender actually completes on another scheduler. By the *RECURSE-QUERY* rule below, `get_scheduler` ends up giving the scheduler that really executes the work. The environment is wrapped in *HIDE-SCHED* before being passed to the scheduler so that the scheduler can't turn round and query `get_scheduler` from the same environment, going back to where it started.

### get_start_scheduler ([exec.get.start.scheduler])

¶1–2 `get_start_scheduler` asks on which scheduler an operation will be, or has been, started. It calls `AS-CONST(env).query(get_start_scheduler)`, and the result must satisfy `scheduler`; there is no default.

¶4 places a requirement on the caller's behavior:

!!! std
    an operation state that is the result of calling connect(sndr, rcvr) shall, if it is started, be started on an execution agent associated with the scheduler get_start_scheduler(get_env(rcvr)).

This is a requirement on the caller: whoever claims in the environment that you're started on X must actually call `start` on an execution agent of X. Senders can therefore trust this information. For example, `affine` ([[exec.task]]) uses it to decide where to return after completion, and `let_value` ([[exec.let]]) passes the predecessor's completion scheduler down as the successor's start scheduler.

`get_scheduler` is a preference: if you need a scheduler to run something, use this one. `get_start_scheduler` is a fact: you are being started here. The environment of `sync_wait` answers both with the scheduler of its internal `run_loop` ([[exec.sync.wait]]), because it really does call `start` on the thread that drives the `run_loop`.

### get_delegation_scheduler ([exec.get.delegation.scheduler])

¶1–2 Asks for a scheduler to which work can be delegated, used for [[g:forward-progress-delegation|forward progress delegation]] ([[intro.progress]]). The result must satisfy `scheduler`; there is no default.

The use case: when `sync_wait` blocks the calling thread, it provides its `run_loop` scheduler in the environment through this query. If the awaited work needs an execution agent that is sure to run, it can schedule a task there, and the blocked thread executes it itself ([[exec.sync.wait#11]], Note 1).

### get_domain ([exec.get.domain])

¶1 `get_domain` asks for the execution domain tag associated with a queryable object. A domain is an empty tag type used to select the implementation of sender algorithms; see [[exec.snd.transform]].

¶2 The result is a default-constructed value of some type `D`, where `D` is the type of the first well-formed expression of the following:

- ¶2.1 the environment answers directly: `auto(AS-CONST(env).query(get_domain))`;
- ¶2.2 if there is a scheduler in the environment, ask that scheduler's value completion domain: `get_completion_domain<set_value_t>(get_scheduler(env), HIDE-SCHED(env))`;
- ¶2.3 `default_domain()`.

So `get_domain` always has an answer.

## Scheduler query: get_forward_progress_guarantee ([exec.get.fwd.progress])

```cpp
enum class forward_progress_guarantee { concurrent, parallel, weakly_parallel };
```

¶1–2 This query can only be asked of a scheduler; it is ill-formed if `sch` doesn't satisfy `scheduler`. It calls `AS-CONST(sch).query(get_forward_progress_guarantee)`, and the result type must be `forward_progress_guarantee`.

¶3 If it returns `concurrent`, all execution agents created by that execution resource must provide the [[g:concurrent-forward-progress|concurrent forward progress guarantee]]; if `parallel`, at least the [[g:parallel-forward-progress|parallel forward progress guarantee]]; `weakly_parallel` adds no requirement. What forward progress guarantees mean is covered in [[intro.progress]].

The `scheduler` concept ([[exec.sched]]) requires this query to be well-formed, so every scheduler must implement `query(get_forward_progress_guarantee_t)`.

## Sender attribute queries

### get_completion_scheduler ([exec.get.compl.sched])

¶1–3 `get_completion_scheduler<Tag>` is a query object template; `get_completion_scheduler<Tag>(get_env(sndr), envs...)` reads the [[g:completion-scheduler|completion scheduler]] for the `Tag` disposition out of the sender's attributes. `Tag` can only be `set_value_t`, `set_error_t` or `set_stopped_t`. The receiver's environment can be passed as extra arguments, because some senders can only answer once they know the environment; for example, `just()` completes on the scheduler the caller is on.

¶4 defines a recursive rule *RECURSE-QUERY*(sch1, envs...): ask `sch1` in turn for its own value completion scheduler `sch2`. If that can't be answered, or `sch2` has the same type as `sch1` and compares equal to it, the result is `sch1`; otherwise recurse on `sch2`. In other words, a scheduler can also answer "who is my completion scheduler", and the query follows the chain to a fixed point.

¶5 `get_completion_scheduler<Tag>(q, envs...)` tries, in order:

- ¶5.1 querying `q`, then applying *RECURSE-QUERY* to the result;
- ¶5.2 if `q` itself is a scheduler and `envs` is non-empty, the result is `auto(q)`: when a scheduler doesn't answer, it is its own completion scheduler;
- ¶5.3 otherwise it is ill-formed.

¶6 If this query is well-formed but the sender's completion signatures contain no `Tag` signature at all, the program is ill-formed {{ill-formed}}: you can't report where a completion that never happens takes place.

¶7 If a sender reports completion scheduler `sch`, and an operation it produces calls the completion function for that disposition on an execution agent that doesn't belong to `sch`'s execution resource, the behavior is undefined {{ub}}.

!!! warning "A completion scheduler is not a hint"
    Downstream code relies on it: choosing the domain ([[exec.snd.transform]]), `on` remembering where to return ([[exec.on]]), and `affine` deciding whether it's already on the right scheduler ([[exec.task]]) all read it. Misreporting the completion scheduler makes downstream code run on the wrong thread, and it is undefined behavior on the sender author's part. When in doubt, don't report one; leaving the query ill-formed is always safe.

### get_completion_domain ([exec.get.compl.domain])

¶1–2 `get_completion_domain<Tag>(attrs, envs...)` reads the completion domain for the `Tag` disposition; `Tag` can be `void`, `set_value_t`, `set_error_t` or `set_stopped_t`. The result is a default-constructed value of type `D`, where `D` is, in order:

- ¶2.1 the type the attributes answer directly;
- ¶2.2 when `Tag` is `void`, the completion domain of `set_value_t`;
- ¶2.3 the value completion domain of `Tag`'s completion scheduler, asked of that scheduler;
- ¶2.4 `default_domain`, when `attrs` itself is a scheduler and `envs` is non-empty;
- ¶2.5 otherwise ill-formed.

¶3–4 As with completion schedulers: reporting a domain without a completion signature for that disposition makes the program ill-formed; reporting domain `D` but completing on an execution resource whose domain isn't `D` is undefined behavior. It is also a forwarding query.

A completion domain is coarser than a completion scheduler. `when_all` may not know which scheduler it will complete on (it completes wherever the last child operation to finish is), but it may know that those schedulers all belong to the same domain.

### get_await_completion_adaptor ([exec.get.await.adapt])

¶1–2 Asks for the await completion adaptor associated with a queryable object; there is no default. ¶3 It is a forwarding query.

`as_awaitable` uses it ([[exec.as.awaitable#8]]): if a sender's attributes provide an adaptor `a`, then when a coroutine does `co_await sndr`, what is actually awaited is `a(sndr)`. A sender author can use this to apply a transformation to the sender before it is awaited by a coroutine.

## get_env ([exec.get.env])

¶1 `get_env(o)` calls `AS-CONST(o).get_env()`, and the result must satisfy *queryable*; without that member it returns `env<>{}`. Note that the customization point here is the member function `get_env()`, not `query`.

¶2 The value of `get_env(o)` is valid as long as `o` is valid.

¶3 Note 1 explains: for a sender, `get_env` returns its attributes; for a receiver, it returns its execution environment.

## Pitfalls

!!! pitfall "A query member missing const or noexcept"
    Standard queries all call `query` through *AS-CONST* and require the call to be `noexcept`. A non-const `query` member is never found at all, so the query either falls back to its default or is ill-formed. The former is the most insidious: `get_stop_token` falls back to `never_stop_token` with no diagnostic, and cancellation just doesn't work. A const but non-`noexcept` `query` makes the program ill-formed.

## Questions

!!! question "1. Can a sender inside sync_wait be cancelled?"
    The environment of `sync_wait` ([[exec.sync.wait]]) answers only three queries: `get_scheduler`, `get_start_scheduler` and `get_delegation_scheduler`.

<details markdown="1">
<summary>Answer</summary>

Not from outside. The environment doesn't answer `get_stop_token`, so child operations get `never_stop_token{}` ([exec.get.stop.token] ¶2.2), and no one can request a stop.

The sender can still complete with `set_stopped` internally, for example `just_stopped()`, in which case `sync_wait` returns an empty `optional`. To make `sync_wait` cancellable, inject a token with `write_env(sndr, prop(get_stop_token, src.get_token()))`.
</details>

!!! question "2. Why does forwarding_query default to false?"

<details markdown="1">
<summary>Answer</summary>

The answer to some queries holds only for the immediate caller. Imagine a `get_child_index` for which the outer adaptor tells its child number 0 that the answer is 0. If it were forwarded by default, then after passing through a layer of `then`, `then`'s child operation would also believe it is child number 0, even though it isn't an immediate child of the outer adaptor.

Not forwarding by default forces the query's author to declare explicitly that the answer holds for all descendants.
</details>

## Summary

| Query | Whom it asks | Default |
|---|---|---|
| `forwarding_query` | Query object | `true` if derived from `forwarding_query_t`, otherwise `false` |
| `get_stop_token` | Environment | `never_stop_token{}` |
| `get_allocator` | Environment | None |
| `get_scheduler` | Environment | None; the result is normalized through the completion scheduler |
| `get_start_scheduler` | Environment | None; if answered, the operation must be started there |
| `get_delegation_scheduler` | Environment | None |
| `get_domain` | Environment | The scheduler's value completion domain, then `default_domain` |
| `get_forward_progress_guarantee` | Scheduler | None; schedulers must answer |
| `get_completion_scheduler<Tag>` | Attributes or scheduler | Itself, for a scheduler with a non-empty environment; if reported, must complete there |
| `get_completion_domain<Tag>` | Attributes or scheduler | Via the completion scheduler; `default_domain` for a scheduler with a non-empty environment |
| `get_await_completion_adaptor` | Attributes | None |
| `get_env` | Sender or receiver | `env<>{}` |

All the queries in the table except `get_env`, `forwarding_query` and `get_forward_progress_guarantee` are forwardable.
