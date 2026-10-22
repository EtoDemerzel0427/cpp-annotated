---
title: Asynchronous operations
summary: "The basic vocabulary of std::execution: asynchronous operations, operation states, receivers, senders, schedulers, completion signatures, and the rules of async lifetime."
updated: 2026-10-19
---

!!! tldr
    - An asynchronous operation is created explicitly, started at most once, and once started completes exactly once: a value completion (any number of values), an error completion (one error) or a stopped completion (no data).
    - A child operation, if started, must complete before its parent completes. This is the basis of structured concurrency and of zero allocation.
    - The async lifetime begins when the start operation begins executing and ends when the completion operation begins executing. Destroying the operation state during it is undefined behavior, and so is accessing it after completion.
    - A sender is a factory of asynchronous operations, and a scheduler is a factory of senders; a receiver's environment describes the caller, and a sender's attributes describe the sender itself.
    - Completion signatures are determined only by the sender type and the environment type, independent of the receiver type.

[exec.async.ops] sets up the vocabulary of chapter 33; every later piece of specification uses its terms. It revolves around a simple state machine: an asynchronous operation is created (connect), started at most once (start), and once started completes exactly once (one of `set_value`, `set_error`, `set_stopped`).

None of the examples on this page have been compiled: Clang 23's libc++ doesn't yet implement the sender part of `std::execution`.

## Asynchronous operations (¶2)

¶2 An **asynchronous operation** ([[g:asynchronous-operation|asynchronous operation]]) is a distinct unit of program execution that:

- ¶2.1 is explicitly created;
- ¶2.2 can be explicitly started at most once;
- ¶2.3 once started, eventually completes exactly once, with a (possibly empty) set of result datums and in exactly one of three dispositions:
    - ¶2.3.1 success, called a **value completion**, which can have any number of result datums;
    - ¶2.3.2 failure, called an **error completion**, which has exactly one result datum;
    - ¶2.3.3 cancellation, called a **stopped completion**, which has no result datum.

    The disposition and the result datums together are called the **async result** ([[g:async-result|async result]]).
- ¶2.4 can complete on a different execution resource than the one on which it started;
- ¶2.5 can create and start other asynchronous operations, called **child operations** ([[g:child-operation|child operation]]). A child operation, if started, must complete before its parent completes.

Note 1 adds that an asynchronous operation can execute synchronously, that is, complete during `start` on the thread that started it. `just(1)` does this ([[exec.factories]]).

Comparing with `std::future` makes the differences clear:

| | `std::async` + `future` | Asynchronous operation |
|---|---|---|
| When it starts | When `async` is called | On an explicit `start` |
| Result | One value or one exception | Any number of values, one error of any type, or cancellation |
| Cancellation | None | Stopped completion |
| Nesting | Work may continue after the `future` is discarded | A child must complete before its parent completes |

The last row is called **structured concurrency**: the lifetimes of parent and child operations nest strictly like function calls, so a child operation can safely refer to its parent's state. The library's promises of no heap allocation and of being able to refer to stack objects all come from this rule.

An error completion corresponds to a thrown exception, and is always exactly one object, but its type isn't limited to `exception_ptr`; it can be an `error_code`, without paying the cost of an exception. A stopped completion means neither a result nor an error: a cancellation the caller asked for shouldn't be treated as a failure.

## Execution resources (¶1)

¶1 An **execution resource** ([[g:execution-resource|execution resource]]) is a program entity that manages a set of execution agents to execute parallel work on behalf of callers. Example 1 gives the current thread, a system thread pool, and an API for a hardware accelerator. Execution resources execute asynchronous operations, and have two states: valid and invalid.

The invalid state is there for schedulers: when an execution resource becomes invalid, the schedulers referring to it, and the senders and operation states obtained from those schedulers, become invalid with it (¶10). For example, after a `run_loop` is destroyed, schedulers obtained from it can no longer be used ([[exec.run.loop]]).

## Operation states, environments, receivers (¶3–5)

¶3 Each asynchronous operation has associated state known as its **operation state** ([[g:operation-state|operation state]]).

¶4 An asynchronous operation has an associated **environment** ([[g:execution-environment|environment]]). It is a [[g:queryable-object|queryable object]] ([[exec.queryable]], a read-only collection that can be queried by key) describing execution-time properties of the caller, such as which allocator the caller wants used, what its stop token is, and which scheduler it runs on. The caller is the parent operation or the function that created the operation.

¶5 An asynchronous operation also has an associated **receiver** ([[g:receiver|receiver]]), which aggregates three handlers, one each for value, error and stopped completions. A receiver has its own environment. The operation state owns the receiver, and the environment of the asynchronous operation is that of its receiver.

So the environment isn't a separate parameter passed around; it hangs off the receiver and flows to child operations through connect. The receiver a parent operation passes when it connects a child sender carries the environment the parent wants the child to see, usually a forwarding version of the parent's environment ([[exec.adapt.general#3]]).

## Completion functions (¶6)

¶6 Each disposition has a corresponding **completion function** ([[g:completion-function|completion function]]). It is a customization point object whose first argument is a receiver and whose remaining arguments are the result datums: `set_value`, `set_error`, `set_stopped`.

The unqualified type of a completion function is its **completion tag** ([[g:completion-tag|completion tag]]), namely `set_value_t`, `set_error_t`, `set_stopped_t`. A valid invocation of a completion function is called a **completion operation**.

## Async lifetime (¶7–8)

```cpp title="opstate-after-complete.cpp"
struct my_op {
  using operation_state_concept = std::execution::operation_state_tag;
  Rcvr rcvr;
  int  value;
  void start() & noexcept {
    std::execution::set_value(std::move(rcvr), value);
    value = 0;   // UB: the completion operation has executed, *this is invalid
  }
};
```

After `set_value` has executed, `*this` may already have been destroyed: for example, the receiver wakes a waiting thread inside `set_value`, and that thread immediately lets the operation state on its stack go out of scope. So writing `value` after completion is undefined behavior.

¶7 The **lifetime of an asynchronous operation**, also called its **async lifetime** ([[g:async-lifetime|async lifetime]]), begins when its start operation begins executing and ends when its completion operation begins executing.

!!! std
    If the lifetime of an asynchronous operation's associated operation state ends before the lifetime of the asynchronous operation, the behavior is undefined.

In other words, destroying the operation state during the async lifetime is {{ub}}. After the completion operation executes, the operation state is invalid, and accessing any part of an invalid operation state is also {{ub}}.

¶8 It further specifies: a completion operation can't happen before the start operation begins executing; after starting, exactly one completion operation executes; and the lifetime of the operation state can end during the execution of the completion operation.

```text
connect ──► the operation state exists; the asynchronous operation hasn't started
start begins ──► async lifetime begins; the operation state must stay alive
completion operation begins ──► async lifetime ends; the operation state is now invalid and may be destroyed inside the completion function
```

The async lifetime ends when the completion operation begins, not when it returns. This is precisely to allow a receiver to destroy the operation state that holds it from inside `set_value`. `sync_wait` waking the waiting thread and `spawn`'s state object deleting itself on completion ([[exec.spawn]]) both rely on this.

For implementers the rule reads the other way round: after calling a completion function, don't access any member of the operation state.

!!! pitfall "Exactly once cuts both ways"
    ¶8 forbids completing twice, and it also forbids never completing. When writing an algorithm, every code path (including the path where constructing an internal object throws) must end in some `set_*`. That's why the exposition code of standard algorithms often has `try { ... } catch (...) { set_error(std::move(rcvr), current_exception()); }`; see *TRY-EVAL* in [[exec.snd]].

## Senders (¶9)

¶9 A **sender** ([[g:sender|sender]]) is a factory for one or more asynchronous operations. **Connecting** a sender and a receiver creates an asynchronous operation whose receiver is the one passed in and whose environment is that receiver's environment.

!!! std
    The lifetime of an asynchronous operation's associated operation state does not depend on the lifetimes of either the sender or the receiver from which it was created.

After connect, the original sender and receiver objects can both be destroyed; the operation state must be self-contained. So at connect time an adaptor must connect its child sender into its own operation state, rather than keeping a pointer to the child sender: the parent operation state nests the child operation states. The structure of *basic-operation* in [[exec.snd]] is exactly this.

The other definitions in this paragraph: a sender is said to be **started** when it is connected to a receiver and the resulting operation is started; a sender's async result is the async result of the operation it produced; and a sender becomes invalid when its parent sender becomes invalid.

## Schedulers (¶10)

¶10 A **scheduler** ([[g:scheduler|scheduler]]) is an abstraction of an execution resource with a uniform interface for scheduling work onto that resource. It is a factory for senders whose operations execute value completions on an execution agent of that resource.

The expression that obtains a sender from a scheduler (that is, `schedule(sch)`) is a **schedule-expression**, and its result is a **schedule sender** ([[g:schedule-sender|schedule sender]]). On success a schedule sender executes a value completion with no data, `set_value(rcvr)`. Several schedulers can refer to the same execution resource.

A scheduler doesn't execute functions directly; it gives you a sender that moves onto that resource. Executing `f` on `sch` is written `schedule(sch) | then(f)`.

## Completion schedulers and attributes (¶11–12)

¶11 An asynchronous operation has one or more **completion schedulers** ([[g:completion-scheduler|completion scheduler]]) for each of its dispositions: the completion operations for that disposition execute on its execution resource.

¶12 A sender has an associated queryable object called its **attributes** ([[g:sender-attributes|attributes]]), describing properties of the sender and of the operations it produces. For each disposition there is a query object that reads the completion scheduler out of the attributes, for example `get_completion_scheduler<set_value_t>` ([[exec.get.compl.sched]]).

If a completion scheduler query is well-formed, then for any operation created by that sender the completion scheduler for that disposition is unique. A schedule sender must have a value completion scheduler attribute whose value equals the scheduler that produced it.

!!! warning "Environments and attributes flow in opposite directions"
    A receiver's environment describes the caller's side and flows downward; a sender's attributes describe the sender itself and flow upward. Both are obtained with `get_env` ([[exec.get.env]]) and both are queryable objects, but don't mix them up: asking a sender's attributes for `get_scheduler`, or a receiver's environment for `get_completion_scheduler`, makes no sense.

## Completion signatures (¶13)

¶13 A **completion signature** ([[g:completion-signature|completion signature]]) is a function type describing a completion operation. The possible completion signatures of an asynchronous operation form a finite set, corresponding to the completion operations it may execute (in the sense of potentially evaluated in [[basic.def.odr]]).

The precise correspondence is: the actual signature of a completion operation `set(rcvr, args...)` is `F = decltype(auto(set))(decltype((args))...)`, and a signature `Sig` is associated with it if and only if *MATCHING-SIG*(Sig, F) is `true`. *MATCHING-SIG* ([[exec.general#7]]) adds `&&` to each parameter type before comparing.

For example, the actual signature of `set_value(std::move(rcvr), 42)` is `set_value_t(int)`, which matches a declared `set_value_t(int)`. The actual signature of `int x; set_value(std::move(rcvr), x)` is `set_value_t(int&)`, which doesn't match `set_value_t(int)`, because the latter promises an rvalue `int`; to pass an lvalue you declare `set_value_t(int&)`.

The last sentences of this paragraph determine the architecture of the type computations: the sender type plus the environment type determine the set of completion signatures. The receiver type itself plays no part; only the receiver's environment type does. A sender type whose completion signatures can be determined without the environment is a **non-dependent sender** ([[g:non-dependent-sender|non-dependent sender]]).

Why exclude the receiver? Because a sender often has to answer how it will complete before there is any receiver. `when_all` must check that each child sender has at most one kind of value completion, and `let_value` must know the predecessor's value types before it can compute the type of the successor sender. If signatures depended on the receiver type, there would be a cycle. The environment, on the other hand, can be known in advance; for example, the value type of `read_env(get_scheduler)` depends on the type of the scheduler in the environment, which makes it a dependent sender. See [[exec.cmplsig]] for details.

## Three kinds of sender algorithm (¶14)

¶14 Functions that accept or return senders are called sender algorithms, and come in three kinds:

- ¶14.1 A **sender factory** takes non-sender arguments and returns a sender, such as `schedule`, `just`, `read_env` ([[exec.factories]]).
- ¶14.2 A **sender adaptor** ([[g:sender-adaptor|sender adaptor]]) constructs and returns a parent sender from one or more child senders and other arguments, such as `then`, `let_value`, `when_all` ([[exec.adapt]]). The operations created by the parent sender are parent operations of those created by the child senders.
- ¶14.3 A **sender consumer** takes a sender and returns something that isn't a sender, such as `sync_wait` ([[exec.consumers]]) and `spawn` ([[exec.spawn]]).

¶14.2 ties parent and child senders to the parent and child operations of ¶2.5: operations nest the same way the adaptor expressions nest, and the guarantees of structured concurrency follow.

## Common misconceptions

!!! pitfall "An operation state can be moved"
    ¶9 says only that the operation state doesn't depend on the lifetimes of the sender and the receiver; it doesn't say it can be moved. [[exec.opstate.general#3]] makes it ill-formed to copy or move an operation state connected from a standard library sender. Once the operation is started, other threads may hold pointers into it (a thread-pool queue, for instance), and moving it would leave those pointers dangling. So operation states are usually constructed in place by guaranteed copy elision: `auto op = connect(...)`.

!!! pitfall "A child operation can run detached from its parent"
    ¶2.5 requires a started child to complete before its parent completes; there's no such thing as a child running on its own after detaching from its parent. When you really need fire-and-forget work, the standard way is to associate it with an async scope ([[exec.spawn]]), whose `join` is responsible for waiting.

## Questions

!!! question "1. Synchronous completion and lifetime"
    The operation of `just(1)` calls `set_value` inside `start(op)`. Can the implementation of `start` still access `*this` after calling `set_value`?

<details markdown="1">
<summary>Answer</summary>

No. ¶8 allows the lifetime of the operation state to end during the completion operation, and the receiver's `set_value` may well destroy `op`. So `start` can't access `*this` after calling the completion function. The standard *just* implementation ([[exec.factories]]) ends its `start` with `set-cpo(std::move(rcvr), std::move(ts)...)` and does nothing afterwards.

For the caller, destroying `op` after `start(op)` returns, while it isn't yet known whether the operation has completed, is UB for a sender that completes asynchronously (¶7). Only once you know the completion operation has begun executing may you destroy it.
</details>

!!! question "2. References in signatures"
    A sender executes `set_value(std::move(rcvr), s)` in `start`, where `s` is a `std::string` member of the operation state. Is it enough to declare only `set_value_t(std::string)`?

<details markdown="1">
<summary>Answer</summary>

No. `s` is an lvalue, so the actual signature is `set_value_t(std::string&)`. *MATCHING-SIG* treats `set_value_t(std::string)` as `set_value_t(std::string&&)`, which is different, violating [[exec.getcomplsigs#5]]: completion operations that may be executed must have a matching signature.

Either declare `set_value_t(std::string&)`, or change it to `set_value(std::move(rcvr), std::move(s))`. The latter is more common, since the operation is about to complete and there's no need to keep the value in the state.
</details>

## Summary

| Term | Key point |
|---|---|
| Asynchronous operation | Created explicitly, started at most once, completes exactly once after starting |
| Child operation | If started, completes before its parent completes |
| Operation state | Owns the receiver; destroying it during the async lifetime is UB; invalid after completion |
| Async lifetime | From when start begins executing to when the completion operation begins executing |
| Environment | Queryable object on the receiver, describing the caller |
| Attributes | Queryable object on the sender, describing the sender itself |
| Completion signature | Determined by the sender type and environment type, independent of the receiver type |
| Sender algorithms | Factories, adaptors, consumers |
