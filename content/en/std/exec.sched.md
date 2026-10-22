---
title: Schedulers
summary: "The scheduler concept: a copyable, comparable, non-throwing handle to an execution resource; schedule(sch) gives a sender that moves execution onto that resource."
updated: 2026-10-19
---

!!! tldr
    - A scheduler is a lightweight handle to an execution resource: it declares `scheduler_concept`, provides `schedule()` and the forward progress query, and is copyable and comparable, with none of these operations throwing.
    - The sender returned by `schedule(sch)` carries no values on success, and its value completion scheduler is `sch` itself.
    - `sch1 == sch2` being true means both refer to the same execution resource; the converse doesn't hold.
    - A scheduler's destructor can't block waiting for work to finish; a scheduler doesn't extend the lifetime of its execution resource.
    - A scheduler that never completes with an error (*infallible-scheduler*) is a prerequisite for facilities that return to the original scheduler.

[[exec.async.ops#10]] defines a scheduler as an abstraction of an execution resource and a factory of senders. This subclause writes that definition as the `scheduler` concept and adds a set of semantic requirements. The schedulers the standard library provides are the scheduler of `run_loop` ([[exec.run.loop]]), `parallel_scheduler` ([[exec.par.scheduler]]), and `inline_scheduler` and the type-erased `task_scheduler` ([[exec.task]]).

Clang 23's libc++ doesn't implement this part of `std::execution` yet, and the examples on this page have not been compiled.

## Writing a scheduler

```cpp title="thread-pool-scheduler.cpp"
namespace ex = std::execution;

class pool_scheduler {
  thread_pool* pool_;
public:
  using scheduler_concept = ex::scheduler_tag;

  explicit pool_scheduler(thread_pool& p) noexcept : pool_(&p) {}

  pool_sender schedule() const noexcept { return pool_sender{pool_}; }

  auto query(ex::get_forward_progress_guarantee_t) const noexcept {
    return ex::forward_progress_guarantee::parallel;
  }

  bool operator==(const pool_scheduler&) const noexcept = default;   // equal if same pool
};
// pool_sender's attributes must answer get_completion_scheduler<set_value_t>, returning pool_scheduler{*pool_}
```

`thread_pool` and `pool_sender` are hypothetical types. The scheduler itself is just a pointer-sized handle; the real work is done by the operation state connected from `pool_sender`: its `start` puts itself on the thread pool's queue, and once a worker thread picks it up it calls `set_value(rcvr)`.

## The scheduler concept (¶1)

```cpp
template<class Sch>
  concept scheduler =
    derived_from<typename remove_cvref_t<Sch>::scheduler_concept, scheduler_tag> &&
    queryable<Sch> &&
    requires(Sch&& sch) {
      { schedule(std::forward<Sch>(sch)) } -> sender;
      { get_forward_progress_guarantee(sch) } -> same_as<forward_progress_guarantee>;
    } &&
    equality_comparable<remove_cvref_t<Sch>> &&
    copyable<remove_cvref_t<Sch>>;
```

¶1 Item by item:

- **The `scheduler_concept` tag**: the type must declare `using scheduler_concept = scheduler_tag;` (or a type derived from it). Only types that opt in are schedulers; a type that happens to have a `schedule()` member isn't mistaken for one. `sender`, `receiver` and `operation_state` use the same technique.
- **`schedule(sch)` returns a sender**: `schedule` is a customization point object that calls `sch.schedule()` ([[exec.schedule]]). A valid call of `schedule` is a schedule-expression.
- **`get_forward_progress_guarantee(sch)` must be well-formed**: every scheduler has to declare which level of forward progress its execution agents provide ([[exec.get.fwd.progress]]).
- **Comparable and copyable**: schedulers are copied and compared like pointers.

## Schedule senders carry no values (¶2)

¶2 Let `Sch` be a scheduler type and `Env` an environment type for which `sender_in<schedule_result_t<Sch>, Env>` holds; then *sender-in-of*<schedule_result_t<Sch>, Env> must be modeled.

*sender-in-of* ([[exec.snd.concepts#5]]) means here that the only value completion signature of a schedule sender is `set_value_t()`, carrying no data. It can still have error and stopped completions, for instance when scheduling fails or is cancelled.

Why not let `schedule(sch)` take a function directly? Because `schedule(sch) | then(f)` already expresses executing `f` on `sch`, and `then` takes care of the call and of turning exceptions into `set_error` ([[exec.adapt]]). `schedule` does just one thing, moving somewhere, so scheduler authors only implement the smallest piece, and adaptors such as `continues_on`, `starts_on` and `on` ([[exec.on]]) can reuse it.

## No exceptions, no data races (¶3)

¶3 There are two requirements:

- the operations required by `copyable` and `equality_comparable` (copy and move, destruction, `==`, `!=`) can't exit via an exception;
- calling these operations or `schedule` [[intro.races|potentially concurrently]] from different threads can't introduce data races.

Schedulers get copied into all sorts of operation states and compared and `schedule`d on arbitrary threads. If a scheduler has mutable internal state (say, statistics counters), it must synchronize it itself.

## Equality means the same resource (¶4)

¶4 For two values of the same scheduler type, `sch1 == sch2` returns `true` only if both share the same execution resource.

This is "only if", not "if and only if". Equality implies the same resource, but two schedulers for the same resource can compare unequal, for instance two schedulers that refer to the same pool with different priority parameters. So `==` can be used to decide that you're already on the target resource and can skip a transition, but `!=` can't be used to conclude that you're definitely on a different resource.

## The completion scheduler of a schedule sender (¶5–6)

¶5 If `get_completion_scheduler<set_value_t>(get_env(schedule(sch)))` is well-formed, it must compare equal to `sch`. This writes the requirement of [[exec.async.ops#12]] as a checkable expression.

¶6 For any `T` and pack of environments `envs`, asking the scheduler directly and asking its schedule sender's attributes must agree:

- `get_completion_domain<T>(sch, envs...)` and `get_completion_domain<T>(get_env(schedule(sch)), envs...)` are either both ill-formed or have the same type;
- `get_completion_scheduler<T>(sch, envs...)` and `get_completion_scheduler<T>(get_env(schedule(sch)), envs...)` are either both ill-formed or have the same type and value.

With this, [[exec.get.scheduler]] can ask the scheduler in the environment for its completion scheduler directly, without actually calling `schedule`.

## Destruction must not block (¶7)

¶7 The destructor of a scheduler type can't block pending completion of any receivers connected to the senders returned by `schedule`.

A scheduler is a handle, and destroying a handle shouldn't wait for all the work to finish along the way. Waiting is the job of the execution resource itself (such as `run_loop`'s `finish` and `run`) or of an async scope's `join` ([[exec.scope]]).

This also rules out a common bad design: holding the thread pool in a `shared_ptr` and `join`ing all its threads when the last scheduler is destroyed. If the last copy happens to be destroyed on a worker thread of the pool, that thread would wait for itself.

!!! pitfall "A scheduler doesn't extend the lifetime of its execution resource"
    After `run_loop loop; auto sch = loop.get_scheduler();`, `sch` becomes invalid when `loop` is destroyed ([[exec.async.ops#10]]), and so do senders obtained from `schedule(sch)` afterwards and the operation states produced from them. Think of a scheduler as a pointer.

## infallible-scheduler (¶8)

```cpp
template<class Sch, class Env>
  concept infallible-scheduler =
    scheduler<Sch> &&
    (same_as<completion_signatures<set_value_t()>,
             completion_signatures_of_t<decltype(schedule(declval<Sch>())), Env>> ||
     (!unstoppable_token<stop_token_of_t<Env>> &&
      (same_as<completion_signatures<set_value_t(), set_stopped_t()>, …> ||
       same_as<completion_signatures<set_stopped_t(), set_value_t()>, …>)));
```

¶8 The exposition-only *infallible-scheduler*<Sch, Env> says: in environment `Env`, `schedule(sch)` can only complete with `set_value()`; if `Env`'s stop token might have a stop requested, `set_stopped()` is also allowed. Either way it never completes with an error.

It compares specializations of `completion_signatures` with `same_as`, and the same set of signatures in a different order is a different type, so the wording lists both orders.

It is needed by facilities that guarantee they can return to some scheduler:

- the constructor of `task_scheduler` requires the erased scheduler to satisfy *infallible-scheduler*<Sch, env<>> ([[exec.task.scheduler]]);
- `affine` requires the receiver's environment to answer `get_start_scheduler` with a scheduler that satisfies it; otherwise the `get_completion_signatures` of the `affine` sender exits with an exception ([[exec.affine]]).

The reasoning is the same in both cases: if the step of returning to the original scheduler could itself fail, there would be nowhere to report the failure, because the error completion ought to happen on the original scheduler, which is exactly where we can't get back to. The scheduler of `run_loop` satisfies it: the completion signatures of its schedule sender are just `set_value_t()`, possibly plus `set_stopped_t()` ([[exec.run.loop]]). The backend of `parallel_scheduler` is allowed to end a schedule with `set_error` ([[exec.parschedrepl.psb]]), so it can't be counted on to satisfy this concept.

## Questions

!!! question "An == that always returns true"
    Write a scheduler whose `operator==` always returns `true`, though each object actually has its own thread. Which rule does it violate? What goes wrong?

<details markdown="1">
<summary>Answer</summary>

It violates ¶4: equal schedulers must share the same execution resource.

All downstream reasoning based on equality goes wrong. The *RECURSE-QUERY* of [[exec.get.compl.sched]] stops recursing when the type is the same and the values compare equal; an algorithm might also decide it's already on the target scheduler and skip the scheduling, with the result that code runs on the wrong thread. The program doesn't meet the concept's semantic requirements, and the consequences are on the program.
</details>

## Summary

- Declare `scheduler_concept = scheduler_tag`, provide `schedule()` and `query(get_forward_progress_guarantee_t)`, and be copyable and comparable.
- Copying, comparison and destruction don't throw; concurrent calls of `schedule` don't introduce data races.
- `==` being true means the same execution resource.
- A schedule sender's value completion carries no data, and its value completion scheduler equals the original scheduler.
- Destruction must not wait for work to finish.
- An *infallible-scheduler* never completes with an error; facilities that return to the original scheduler depend on it.
