---
title: run_loop
summary: "The simplest execution resource in the standard library: a thread-safe first-in-first-out work queue executed by whichever thread calls run(); the default implementation of sync_wait is built on it."
updated: 2026-10-19
---

!!! tldr
    - `run_loop` creates no threads; it only maintains a work queue, and whichever thread calls `run()` executes the work in the queue.
    - Scheduling a piece of work means hanging its operation state at the back of the queue, with no memory allocation, so scheduling never fails and the schedule sender has no error completion.
    - The schedule sender has an extra `set_stopped_t()` only when the environment's stop token might have a stop requested; cancellation is checked when the work is dequeued and executed.
    - The states are starting, running, finishing, finished, in that order. `finish()` doesn't discard queued work; `run()` returns only after the queue is empty.
    - If the queue isn't empty, or some thread is still in `run()`, when it's destroyed, `std::terminate` is called.

The examples on this page use C++26 `std::execution`. The libc++ shipped with Clang 23 doesn't implement this part of the library yet, so the examples haven't been verified by compiling, and they carry no verdict.

## A queue driven by its caller

```cpp title="run-loop.cpp"
namespace ex = std::execution;

ex::run_loop loop;
auto sch = loop.get_scheduler();

std::jthread worker([&] { loop.run(); });   // the worker thread executes the work in loop

auto s = ex::schedule(sch) | ex::then([] { return std::this_thread::get_id(); });
auto [id] = std::this_thread::sync_wait(std::move(s)).value();   // id is the worker's thread id
loop.finish();                               // run() returns once the queue is empty, and worker ends
```

[exec.ctx] (execution contexts) currently has only one member, `run_loop`. [exec.run.loop.general] ¶1 It is an execution resource on which work can be scheduled, maintaining a thread-safe first-in-first-out queue; the `run` member function repeatedly takes work out of the queue and executes it on the thread that called it.

The default implementation of `sync_wait` simply puts a `run_loop` on the stack, starts the operation, and then calls `run()` ([[exec.consumers]]). `run_loop` is also a good model for understanding how schedulers are implemented: scheduling an operation means hanging its operation state in the queue, and executing it means taking it out and calling its completion function.

## Members and state ([exec.run.loop.general])

```cpp
class run_loop {
  struct run-loop-opstate-base {       // exposition only
    virtual void execute() noexcept = 0;
    run_loop* loop;
    run-loop-opstate-base* next;       // intrusive list pointer
  };
  run-loop-opstate-base* pop-front() noexcept;
  void push-back(run-loop-opstate-base*) noexcept;
public:
  run_loop() noexcept;
  run_loop(run_loop&&) = delete;
  ~run_loop();
  run-loop-scheduler get_scheduler() noexcept;
  void run() noexcept;
  void finish() noexcept;
};
```

¶4 The standard recommends that implementations use an intrusive queue of operation states, so that scheduling needs no memory allocation. The `next` pointer above serves this purpose: each scheduled operation state is itself a node of the list.

The price is that operation states can't be moved while queued. The operation states of standard library senders aren't allowed to be copied or moved anyway ([[exec.opstate#3]]). `run_loop` itself can't be moved either, because the queued operation states store a `loop` pointer to it.

¶2 Each `run_loop` has a **count**, the number of work items in the queue, and a **state**, which is one of *starting*, *running*, *finishing*, *finished*:

```text
          run()              finish()             queue empty
starting ───────► running ───────────► finishing ─────────────► finished
    │                                      ▲
    └──────────────── finish() ────────────┘
```

¶3 Except for `run` and the destructor, member functions can be called concurrently without introducing data races. Taking from and putting into the queue, and `finish`, are all performed atomically.

## The scheduler and the schedule sender ([exec.run.loop.types])

### The scheduler (¶1–5)

The scheduler returned by `get_scheduler()` remains valid until the `run_loop` that produced it is destroyed (¶2). ¶3 Two schedulers compare equal if and only if they come from the same `run_loop`, a stronger condition than the one-way requirement for schedulers in general ([[exec.sched]]).

¶4–5 `schedule(sch)` returns a schedule sender. Its value completion and stopped completion both happen on this loop, so for these two kinds of completion the [[g:completion-scheduler|completion scheduler]] is `sch`. It has no error completion, and so no error completion scheduler.

### The completion signatures depend on the environment (¶6–8)

¶6 The completion signatures of the schedule sender depend on the stop token in the receiver's environment:

| The environment's stop token | Completion signatures |
|---|---|
| Can never have a stop requested (satisfies `unstoppable_token`, e.g. no token provided) | `set_value_t()` |
| Might have a stop requested | `set_value_t()`, `set_stopped_t()` |

There is no error completion because hanging an operation in the queue can't fail. So `run_loop`'s scheduler satisfies *infallible-scheduler* ([[exec.sched#8]]) and can be wrapped by `task_scheduler` (which requires the wrapped scheduler to satisfy that concept).

¶8 `connect(sndr, rcvr)` gives a *run-loop-opstate*, and can throw only if copying or moving the receiver may throw.

### The operation state (¶9–10)

¶10 The two key operations of *run-loop-opstate* are:

- ¶10.3 `start(o)` is just `o.loop->push-back(addressof(o))`, hanging itself at the back of the queue;
- ¶10.2 when its turn comes, `execute()` checks the receiver's stop token: if a stop has been requested it calls `set_stopped`, otherwise `set_value`.

So cancellation is checked when the operation is dequeued and executed, not when it is enqueued. `run_loop` doesn't take operations out of the queue early because of a stop request; an already-queued operation that has been asked to stop still waits for its turn before completing with `set_stopped`.

## Construction and destruction ([exec.run.loop.ctor])

¶1 A newly constructed `run_loop` has count 0 and state starting.

¶2 On destruction, if the count isn't 0 or the state is running, `std::terminate` is called; otherwise it does nothing. The two cases correspond to two kinds of error:

- There is still work in the queue. Those operations have been started and must complete; destroying the `run_loop` outright means they never will, violating [[exec.async.ops#2]].
- The state is running. That means some thread is still using it inside `run()`.

Destroying it is fine if it was never `run` (starting), or was `finish`ed but not `run` (finishing), as long as the queue is empty.

## run and finish ([exec.run.loop.members])

¶1 The internal *pop-front* blocks ([[defns.block]]) until one of the following happens:

- ¶1.1 the count is 0 and the state is finishing: it sets the state to finished and returns a null pointer;
- ¶1.2 the count is greater than 0: it removes the item at the front of the queue, decrements the count, and returns that item.

¶2–3 *push-back* adds an item at the back of the queue and increments the count. It synchronizes with the *pop-front* that removes that item, so writes to the operation state before it was enqueued are visible to the thread that executes it ([[intro.races]]).

¶5–6 The precondition of `run()` is that the state is starting or finishing. It changes starting to running (finishing stays as is), then repeatedly removes and executes work until *pop-front* returns a null pointer:

```cpp
while (auto* op = pop-front()) {
  op->execute();
}
```

¶8–10 The precondition of `finish()` is that the state is starting or running, and its effect is to change the state to finishing. It synchronizes with the *pop-front* that returns a null pointer.

Several usage rules follow from these preconditions:

- `run()` can be called only once. While a thread is in `run()` the state is running, and from then on the state only becomes finishing and finished, so calling `run()` again violates the precondition.
- `finish()` can also be called only once. After it is called the state is no longer starting or running. `sync_wait`'s receiver calls `finish()` in all three completion functions, but exactly one completion happens.
- `finish()` doesn't discard queued work; `run()` executes all of it before returning.
- Calling `finish()` before `run()` is fine. That's what happens when `sync_wait` waits for a sender that completes synchronously: the receiver has already called `finish()` during `start(op)`, and then `run()` sees the state finishing and the queue empty, and returns immediately.

## Common mistakes

### Forgetting finish

If nobody calls `finish()`, `run()` blocks forever in *pop-front* once the queue is empty. `sync_wait` relies on its receiver calling `finish()` on completion. When using a `run_loop` yourself, make sure to call `finish()` after all work has been submitted, or on receiving some end signal.

### Scheduling onto it after finish

After `finish()`, `run()` returns as soon as it sees the queue empty, and the state becomes finished. If an operation scheduled onto this loop is started after that, it is put into the queue, but no thread will ever execute it: the operation never completes, and when the `run_loop` is destroyed the count isn't 0, so `terminate` is called. The standard specifies no error handling for enqueuing in the finished state; callers have to avoid it themselves.

## Questions

!!! question "1. Scheduling onto the same loop inside run()"
    A piece of work executing on the loop does `schedule(sch)` onto the same loop again, and connects and starts another operation. Does it deadlock? Does it recurse?

<details markdown="1">
<summary>Answer</summary>

Neither. `start` is just *push-back*: it hangs the new operation at the back of the queue and returns. After the current work finishes, `run()`'s loop takes it out of the queue. Recursive scheduling thus becomes queuing, and the stack depth doesn't grow.
</details>

!!! question "2. Why is there set_stopped only when stoppable?"
    What's the benefit of making the schedule sender's signatures depend on the environment, rather than always including `set_stopped_t()`?

<details markdown="1">
<summary>Answer</summary>

When the environment's stop token can never have a stop requested, the `set_stopped` branch in `execute()` never actually runs. Dropping that signature gives downstream code more precise types. For example, `sync_wait`'s environment has no stop token, so the sender `sync_wait(schedule(loop.get_scheduler()))` waits for has just `set_value_t()`. `task_scheduler` requires the wrapped scheduler to satisfy *infallible-scheduler* in the empty environment `env<>`, that is, to have signatures exactly `completion_signatures<set_value_t()>`, and `run_loop`'s scheduler satisfies this exactly.

This is also what [[exec.async.ops#13]] says: signatures are determined jointly by the sender type and the environment type.
</details>

## Summary

| Question | Answer |
|---|---|
| Who executes the work | The thread that calls `run()` |
| Cost of scheduling | Hanging the operation state in an intrusive queue, no memory allocation |
| Completion signatures | `set_value_t()`, plus `set_stopped_t()` when the environment is stoppable; no error completion |
| When cancellation takes effect | When the work is dequeued and executed |
| `finish()` | Doesn't discard queued work; `run()` returns once the queue is empty |
| Destruction | `terminate` if the queue isn't empty or it is still running |
