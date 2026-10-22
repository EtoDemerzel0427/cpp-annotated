---
title: Execution control library
summary: "A guide to chapter 33, std::execution: a sender describes work, connect binds it to a receiver to form an operation state, and only start actually runs it."
updated: 2026-10-19
---

!!! tldr
    - `std::execution` (C++26, header `<execution>`) is one set of interfaces for describing where a piece of work runs and who receives the result when it finishes. It applies to thread pools, event loops, GPUs and coroutines.
    - A sender is only a description of work; `connect` combines it with a receiver into an operation state, and the work begins only after `start`.
    - Every started operation completes exactly once, with exactly one of `set_value`, `set_error` or `set_stopped`.
    - All customization goes through member functions: `rcvr.set_value(...)`, `sndr.connect(r)`, `env.query(q)`. Completion functions, `start` and queries must all be `noexcept`.
    - Clang 23's libc++ doesn't have the sender part yet, so none of the examples in this chapter were compiled in our tests.

## Why a new model

`std::async` plus `std::future` can move work onto another thread, but there are things it can't do: a `future` always allocates a shared state on the heap; `async` starts running as soon as it's called, so you can't describe first and start later; there is no cancellation; and the standard has no `then`-style chaining.

Chapter 33 answers these with four concepts {{c++26}}, mostly from [[P2300R10]]:

| Role | Concept | Purpose |
|---|---|---|
| Sender | `sender` | Describes a piece of asynchronous work; executes nothing itself |
| Receiver | `receiver` | The continuation after the work completes, with three entry points: `set_value`, `set_error`, `set_stopped` |
| Operation state | `operation_state` | The result of `connect(sndr, rcvr)`, holding everything this run needs; `start(op)` begins execution |
| Scheduler | `scheduler` | A handle to an execution resource; `schedule(sch)` gives a sender that moves onto that resource |

## A complete lifecycle

!!! note "About the examples in this chapter"
    In Clang 23's libc++, `<execution>` has only the execution policies, not sender facilities such as `std::execution::just`, and no reference implementation was installed in our tests. The examples in this chapter are written against the draft, have not been compiled, and carry no verdict.

```cpp title="hello-sender.cpp"
#include <execution>
#include <print>
#include <utility>
namespace ex = std::execution;

int main() {
  ex::parallel_scheduler sch = ex::get_parallel_scheduler();

  ex::sender auto work = ex::schedule(sch)                      // hop to the thread pool
                       | ex::then([] { return 6; })             // compute 6
                       | ex::then([](int x) { return x * 7; }); // multiply by 7

  // sync_wait connects and starts internally, blocking the current thread until completion
  auto [v] = std::this_thread::sync_wait(std::move(work)).value();
  std::println("{}", v);   // 42
}
```

What `sync_wait` does internally ([[exec.sync.wait]]) is the skeleton of the whole model:

1. **Build the sender**. `schedule(sch) | then(f) | then(g)` just packs `sch`, `f` and `g` into a nested object. [[exec.adapt.general#3]] requires that, before `connect` and `start`, an adaptor has no observable effects other than copying and moving its arguments.
2. **connect**. `connect(work, rcvr)` connects each sender layer to the receiver of the next layer, producing an operation state object. It usually lives right on the caller's stack and nests the states of all child operations, so no heap allocation is needed.
3. **start**. `start(op)` starts the outermost operation, which starts its children. A thread-pool thread executes `f`, the result 6 is handed via `set_value` to the receiver of `then(g)`, and after computing 42 it is handed to `sync_wait`'s receiver.
4. **Completion**. Each operation completes exactly once ([[exec.async.ops#8]]). After completion the operation state is done with, and only then does `sync_wait` let it go out of scope.

The terms these steps use (asynchronous operation, operation state, asynchronous lifetime and so on) are all defined in [[exec.async.ops]], and every later subclause builds on it.

## Map of the chapter

| Topic | Pages | Contents |
|---|---|---|
| Basic model | [[exec.async.ops]] | Definitions of asynchronous operation, operation state, receiver, sender, scheduler, completion signature |
| Queries and environments | [[exec.queryable]], [[exec.queries]] | Queryable objects, `prop`, `env`; queries such as `get_stop_token` and `get_scheduler` |
| Three core concepts | [[exec.sched]], [[exec.recv]], [[exec.opstate]] | `scheduler`, `receiver`, `operation_state`, plus `set_*` and `start` |
| Senders | [[exec.snd]] | The `sender` and `sender_in` concepts, the exposition-only skeleton of standard senders |
| Completion signatures | [[exec.cmplsig]] | `completion_signatures`, `get_completion_signatures`, dependent senders |
| Connecting and customizing | [[exec.connect]], [[exec.snd.transform]] | `connect`, treating awaitables as senders; domains and `transform_sender` |
| Factories | [[exec.factories]] | `schedule`, `just`, `read_env` |
| Adaptors | [[exec.adapt]], [[exec.on]], [[exec.let]], [[exec.bulk]], [[exec.when.all]] | `then`, `write_env`; switching schedulers; `let_*`; `bulk`; `when_all` |
| Consumers | [[exec.consumers]] | `sync_wait`, `sync_wait_with_variant` |
| Structured concurrency | [[exec.scope]], [[exec.spawn]] | `counting_scope`; `associate`, `spawn`, `spawn_future` |
| Execution contexts | [[exec.run.loop]], [[exec.par.scheduler]] | `run_loop`; `parallel_scheduler` and its replaceable backend |
| Coroutines | [[exec.as.awaitable]], [[exec.task]] | `co_await` on senders in coroutines; `task<T>`, `affine` and more |

A suggested reading order is [[exec.async.ops]] → [[exec.recv]], [[exec.opstate]] → [[exec.snd]] → [[exec.cmplsig]] → [[exec.connect]], then whichever algorithms interest you.

## Customization: member functions

Table 158 in [[exec.general#3]] divides the chapter's [[g:customization-point-object|customization point objects]] (CPOs, function objects whose behavior user types can customize) into four categories:

| Category | Purpose | Examples |
|---|---|---|
| Core | Connect components together | `connect`, `start` |
| Completion functions | Used by senders to announce success, error or cancellation | `set_value`, `set_error`, `set_stopped` |
| Sender algorithms | Customizable factories, adaptors and consumers | `just`, `then`, `continues_on`, `sync_wait` |
| Queries | Query various properties of an object | `get_stop_token`, `get_scheduler`, `get_completion_scheduler` |

User types take part in customization through ordinary member functions: `set_value(rcvr, vs...)` calls `rcvr.set_value(vs...)`, `connect(s, r)` looks for `s.connect(r)` first, and a query `q(env)` calls `env.query(q)`. In addition, a type declares a tag (such as `using receiver_concept = receiver_tag;`) to say it is a receiver, sender or scheduler.

!!! history "From tag_invoke to member functions"
    Early revisions of P2300 implemented customization with free functions like `tag_invoke`, written `tag_invoke(set_value, rcvr, v)`. The version merged into C++26 switched to member functions, which makes writing your own components much simpler.

## Exposition-only entities used throughout the chapter

The standard uses some exposition-only macros and concepts to shorten the wording; they aren't things you can call. The ones you'll meet most often in the later pages are:

¶5 *MANDATE-NOTHROW*(expr) is equivalent to `expr`, but requires `noexcept(expr)` to be `true`, otherwise the program is ill-formed. Almost every CPO wraps this layer: `set_value`, `start`, `get_env` and the various queries must all be non-throwing. The whole library is designed so that completion paths don't throw; errors must be delivered via `set_error`.

¶6 *movable-value*<T> requires `decay_t<T>` to be move constructible and constructible from `T`, and `T` not to be an array. The `ts` of `just(ts...)` and the `f` of `then(sndr, f)` must satisfy it, because they get stored in the sender.

¶7 *MATCHING-SIG*(F1, F2) compares two function types after first replacing each parameter type `A` with `A&&`. So `set_value_t(int)` and `set_value_t(int&&)` count as the same signature, while `set_value_t(int&)` is different. All matching of completion signatures uses it ([[exec.async.ops#13]]).

¶8 *AS-EXCEPT-PTR*(err) turns an error value into an `exception_ptr`: an `exception_ptr` is returned as is (it must not be null), an `error_code` is wrapped in a `system_error`, and other types go through `make_exception_ptr`. `sync_wait` and the coroutine integration use it when they need to throw an error.

¶9 *AS-CONST*(expr) accesses `expr` as a const lvalue reference. Queries always call `query` through it, so a `query` member must be const.

## Header &lt;execution&gt;

`<execution>` ([[execution.syn]]) holds both the C++17 execution policies ([[execpol]]) and everything in this chapter. Three things are worth noting:

- `forwarding_query`, `get_allocator` and `get_stop_token` are in namespace `std`, because other library components use them too; the remaining queries are in `std::execution`.
- `sync_wait` and `sync_wait_with_variant` are in `std::this_thread`, a reminder that they block the current thread.
- The types of `read_env`, `write_env` and `unstoppable` are unspecified, rather than having named `xxx_t` types like the other CPOs.

!!! history
    Algorithms from early revisions of P2300 that start eagerly or share their result, such as `ensure_started`, `start_detached` and `split`, don't exist in the current draft. Eager starting is now handled by async scopes: `spawn` and `spawn_future` must be attached to a scope ([[exec.spawn]]), so every started operation has someone responsible for waiting until it ends. `task`, `counting_scope`, `parallel_scheduler` and others were added by other proposals after P2300 was merged.

!!! impl "Implementation status"
    The authors of P2300 maintain a reference implementation, stdexec, where most of this chapter's design was implemented first. Its interface doesn't necessarily match the current draft word for word; watch for differences when you use it to check the examples.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

- [[exec.general]] ¶1–2: this clause describes components supporting execution of function objects; Table 157 lists only four subclauses (schedulers, receivers, operation states, senders), all in `<execution>`.
- [[execution.syn]] ¶1: *variant-or-empty*<Ts...> is the deduplicated `variant<decay_t<Ts>...>` when `Ts` is non-empty, and a type that can't be constructed when it is empty. That way a sender with no value completions still has a valid `value_types_of_t`.
- [[execution.syn]] ¶2–3: *single-sender-value-type* and *single-sender* describe senders with exactly one value completion signature: `decay_t<T>` for one datum, `void` for none, and `tuple<decay_t<Ts>...>` for several. `co_await` on a sender ([[exec.as.awaitable]]) requires a *single-sender*.
- [[execution.syn]] ¶4: *valid-completion-signatures* means a specialization of `completion_signatures`.

</details>
