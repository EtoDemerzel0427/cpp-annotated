---
title: Parallel scheduler
summary: "get_parallel_scheduler() returns a parallel scheduler shared by the whole program; all its work goes through a replaceable virtual interface, parallel_scheduler_backend, and bulk is split across threads only under the par policies."
updated: 2026-10-19
---

!!! tldr
    - `get_parallel_scheduler()` returns a thread-pool scheduler provided by the standard library and shared by the whole program; its execution agents provide the parallel forward progress guarantee.
    - The implementation is hidden behind the virtual interface `parallel_scheduler_backend`. A program can define its own `query_parallel_scheduler_backend()` to replace the default implementation, just as it can replace `operator new`.
    - The backend never sees the concrete receiver type: the receiver is wrapped in a proxy with virtual functions, errors are unified as `exception_ptr`, and bookkeeping data lives in storage the caller provides in advance, so scheduling itself needs no memory allocation.
    - `bulk` is split only when the execution policy is `par` or `par_unseq`; with `seq`, all the iterations run as one unit, sequentially on one thread.

The examples on this page use C++26 `std::execution`. The libc++ shipped with Clang 23 doesn't implement this part of the library yet, so none of the examples have been verified by compiling, and they carry no verdict.

## The standard library's own thread pool

```cpp title="parallel-scheduler.cpp"
namespace ex = std::execution;

auto sch = ex::get_parallel_scheduler();
static_assert(ex::scheduler<decltype(sch)>);

std::vector<float> v(n);
std::this_thread::sync_wait(
  ex::schedule(sch)
  | ex::bulk(ex::par, n, [&](std::size_t i) { v[i] = f(i); }));
```

In `std::execution`, a [[g:scheduler|scheduler]] represents an execution resource on which work can be arranged. `run_loop` creates no threads and `inline_scheduler` executes right on the current thread, so neither is a thread pool. `parallel_scheduler` fills that gap: a parallel execution resource provided by the implementation and shared by the whole program.

Its design has two goals. The first is sharing: if every library in a program created its own thread pool, the number of threads would far exceed the number of cores, and they would fight each other; `parallel_scheduler` makes everyone use the same system-wide resource by default. The second is replaceability: embedded systems, game engines and frameworks that already have a thread pool need to plug it into their own implementation.

## parallel_scheduler [exec.par.scheduler]

The class definition of `parallel_scheduler` is unspecified; the standard only describes its behavior.

¶1 It models the `scheduler` concept.

¶2 Each `parallel_scheduler` object is associated with a backend object, written *BACKEND-OF*(sch).

¶3 The value of `get_forward_progress_guarantee(sch)` is `forward_progress_guarantee::parallel`. The parallel forward progress guarantee ([[intro.progress]]) says that once an execution agent starts executing it keeps making progress, but not that it is guaranteed to start. So don't do blocking synchronization on this scheduler such as waiting for another task that hasn't started yet; that needs the stronger concurrent forward progress guarantee.

¶4 Two `parallel_scheduler`s compare equal if and only if their backends are the same object.

¶13 `get_parallel_scheduler()` first calls `parallel_scheduler_replacement::query_parallel_scheduler_backend()` to get a backend pointer `eb`. If `eb` is null it calls `terminate`; otherwise it returns a scheduler associated with `eb`.

### Receiver proxies and preallocated storage (¶5–6)

The backend is a virtual interface and can't be a template, so it can't see the concrete [[g:receiver|receiver]] type. The standard uses two notions to cross this type-erasure boundary.

¶5 A **proxy** for a receiver `rcvr` is an lvalue `r` of some class type `B` such that `r.set_value()`, `r.set_error(e)` (where `e` is an `exception_ptr`) and `r.set_stopped()` are equivalent to calling the corresponding completion function on `rcvr`. The proxy erases the concrete types of the three completion functions with virtual functions.

¶6 The **preallocated backend storage** of a proxy is a `span<byte>` that stays valid until any completion function is called on the proxy, and that the backend may overwrite. Note 1 explains that the backend can use it as scratch storage for operations started through the backend interface.

This storage lives inside the [[g:operation-state|operation state]], and the backend can put its own bookkeeping data (queue nodes, for example) in it. So even across type erasure, the whole scheduling process can still be allocation-free.

¶7 When the sender returned by `schedule(sch)` is connected to `rcvr` and started, it calls `b.schedule(r, s)`, where `r` is a proxy with `receiver_proxy` as a base class and `s` is the preallocated storage; other completions are forwarded unchanged. The literal wording is "if `sndr` completes successfully, then `b.schedule(r, s)` is called", which reads as if cause and effect were reversed, since it is `b.schedule` that makes the sender complete. Read it by its intent: after start, call the backend, and the backend completes through `r`.

### Customizing bulk (¶8–12)

`bulk(policy, shape, f)` calls `f` once for each index in `[0, shape)` ([[exec.bulk]]). Its default implementation is sequential; parallelism comes from scheduler customization.

¶8 `get_domain(sch)` returns the exposition-only type *parallel-scheduler-domain*, which has two `transform_sender` overloads that rewrite `bulk_chunked` and `bulk_unchunked` senders respectively. `bulk` itself is first rewritten by `default_domain` into `bulk_chunked` ([[exec.bulk#4]]) and then rewritten by this domain, a typical example of the recursive transformation in [[exec.snd.transform]].

¶9–10 The rewrite takes the execution policy `pol`, the shape `shape` and the function `f` out of the sender, and defines a boolean `p`: true when `pol` is `parallel_policy` or `parallel_unsequenced_policy` (possibly cv-qualified), up to the implementation when it is an implementation-defined execution policy {{impl}}, and false otherwise (`seq`, `unseq`).

¶11 For `bulk_chunked`, after the predecessor completes with values `vals`, it calls `b.schedule_bulk_chunked(p ? shape : 1, r, s)`. Each call the backend makes to `r.execute(i, j)` is equivalent to `f(i, j, args...)` when `p` is true, and to `f(0, shape, args...)` when it is false.

¶12 For `bulk_unchunked`, it calls `b.schedule_bulk_unchunked(p ? shape : 1, r, s)`. `r.execute(i, i + 1)` is equivalent to `f(i, args...)` when `p` is true, and to calling `f` for all the indices in order when it is false.

When `p` is false the shape shrinks to 1. `seq` and `unseq` don't allow `f` to be executed in parallel, so all the work is handed to the backend as a single iteration and completed sequentially by one execution agent. The work still runs on the thread pool; it just isn't split. This is also why `bulk` must take an execution policy argument: it decides whether a customized implementation may split the work.

!!! lawyer "¶8 uses get_domain"
    [[exec.snd.transform]] looks up the completion domain of the sender's attributes (`get_completion_domain`), while ¶8 is written in terms of `get_domain(sch)`. The two are connected by ¶2.3 of [[exec.get.compl.domain]]: the completion domain can be found via the completion scheduler by querying that scheduler's value completion domain. The wording doesn't spell out how the answers of the two queries are kept consistent; read it by its intent, that the domain of `parallel_scheduler` is *parallel-scheduler-domain*.

## Replacing the implementation [exec.parschedrepl]

[exec.parschedrepl.general] ¶1 The facilities in namespace `parallel_scheduler_replacement` let users replace the default implementation of `parallel_scheduler`.

### The entry point: query_parallel_scheduler_backend [exec.parschedrepl.query]

```cpp title="replace-backend.cpp"
namespace std::execution::parallel_scheduler_replacement {
  shared_ptr<parallel_scheduler_backend> query_parallel_scheduler_backend() {
    static auto backend = make_shared<my_engine_backend>();   // hooked up to the engine's own task system
    return backend;
  }
}
```

¶3 This function is a **replaceable function** ([[g:replaceable-function]], [[dcl.fct.def.replace]]): a program that defines it in any one translation unit replaces the default version provided by the implementation. The replacement shouldn't return a null pointer, otherwise `get_parallel_scheduler()` calls `terminate`.

¶1–2 It returns the parallel scheduler's implementation object `p`: `p.get()` points to the `parallel_scheduler_backend` base class subobject of some most derived object `o` within its lifetime, and `o` isn't destroyed as long as some `shared_ptr` shares ownership with `p`.

### The backend interface [exec.parschedrepl.psb]

```cpp
struct parallel_scheduler_backend {
  virtual ~parallel_scheduler_backend() = default;
  virtual void schedule(receiver_proxy&, span<byte>) noexcept = 0;
  virtual void schedule_bulk_chunked(size_t, bulk_item_receiver_proxy&,
                                     span<byte>) noexcept = 0;
  virtual void schedule_bulk_unchunked(size_t, bulk_item_receiver_proxy&,
                                       span<byte>) noexcept = 0;
};
```

All three pure virtual functions are `noexcept`; failure can only be reported through the proxy's `set_error`.

¶1 The three functions have the same preconditions (see also ¶4 and ¶7): the backend object, the proxy `r` and the storage `s` all live until after a completion function starts being called on `r`. That is, the backend can safely use all three before it calls a completion function, and must not touch them once that call has begun.

¶2 `schedule(r, s)` must call exactly one of `r.set_value()` (success), `r.set_error(eptr)` (error) and `r.set_stopped()` (cancelled), and `set_value` must be called on an execution agent of the execution context this backend represents. ¶3 `s` may be used as scratch storage during the operation.

¶5 The requirements on `schedule_bulk_chunked(n, r, s)`:

- ¶5.1 eventually exactly one completion function is called;
- ¶5.2 each call `r.execute(b, e)` satisfies `0 ≤ b < e ≤ n`;
- ¶5.3 each index `i ∈ [0, n)` falls in the range of at most one call to `execute`;
- ¶5.4 if `set_value` is called, each index falls in the range of exactly one call;
- ¶5.5 all calls to `execute` happen before the call to the completion function;
- ¶5.6 all calls to `execute` and `set_value` are made on execution agents of that execution context.

¶8 The requirements on `schedule_bulk_unchunked(n, r, s)` are the same, except that every call has the form `execute(i, i + 1)`.

These requirements correspond to the semantic requirements on `bulk` in [[exec.bulk#9]]: on success each index is executed exactly once; on error or cancellation only some may have been executed, but none is executed twice.

### The proxy classes [exec.parschedrepl.recvproxy]

```cpp
namespace std::execution::parallel_scheduler_replacement {
  struct receiver_proxy {
  protected:
    virtual bool query-env(unspecified) noexcept = 0;   // exposition only
  public:
    virtual void set_value() noexcept = 0;
    virtual void set_error(exception_ptr) noexcept = 0;
    virtual void set_stopped() noexcept = 0;
    template<class P, class-type Query>
      optional<P> try_query(Query q) const noexcept;
  };

  struct bulk_item_receiver_proxy : receiver_proxy {
    virtual void execute(size_t, size_t) noexcept = 0;
  };
}
```

¶1 `receiver_proxy` represents a receiver, through which the backend triggers completion. `bulk_item_receiver_proxy` adds `execute(b, e)`, which the backend uses to execute a range of bulk iterations. The error completion can only be an `exception_ptr`, because after type erasure the backend can only use one uniform error type.

¶2–3 The backend can query the proxied receiver's environment with `try_query<P>(q)`. `P` must be a cv-unqualified non-array object type. Implementations support only an implementation-defined set of queries and result types; if the query isn't supported or `q(env)` is ill-formed it returns `nullopt`, if the type of `q(env)` is exactly cv `P` it returns its value, and otherwise it returns an implementation-defined value.

¶4 The stop token query `get_stop_token_t` is always supported, and an `inplace_stop_token` can always be obtained. ¶5 recommends that when the receiver's token is some other `stoppable_token` type, `try_query` also adapt it into an `inplace_stop_token`, returning an equivalent token each time until completion. That way a backend only needs to support one token type to respond to cancellation requests from any source.

## Common misconceptions

!!! pitfall "bulk on parallel_scheduler is always parallel"
    Only when the execution policy is `par` or `par_unseq` (or an implementation-defined policy that allows parallelism) does the domain hand the shape to the backend for splitting. `bulk(seq, n, f)` is collapsed into a single `execute`, running all iterations sequentially on one thread (¶10–12).

!!! pitfall "The backend keeps using the storage after calling the completion function"
    ¶1 only guarantees that `r` and `s` live until the completion function begins executing. The completion function may destroy the whole operation state immediately, freeing the memory `s` lives in. If the backend still accesses a node in `s` after calling `r.set_value()`, say to unlink it from an internal queue, it accesses freed memory. All bookkeeping must be done before the completion function is called.

## Questions

!!! question "1. Why does the backend interface use virtual functions rather than templates?"

<details markdown="1">
<summary>Answer</summary>

The backend has to be provided by a replaceable function ([exec.parschedrepl.query] ¶3), that is, decided at link time by another translation unit or even another library. A template has to be visible at the point of use, so it can't be replaced at link time; a virtual interface only needs a stable ABI. The price is type erasure: receivers have to be wrapped as `receiver_proxy`, errors are unified as `exception_ptr`, and the environment can only be accessed in a limited way through `try_query`. The preallocated storage is there to keep the allocation-free property despite type erasure. `task_scheduler` also reuses this interface as its type-erasure boundary ([[exec.task]]).
</details>

!!! question "2. Do two calls to get_parallel_scheduler() always give equal results?"

<details markdown="1">
<summary>Answer</summary>

Not necessarily. ¶4 says two schedulers compare equal if and only if their backends are the same object, which depends on whether the two calls to `query_parallel_scheduler_backend()` return the same object. The default implementation, and a replacement that uses a `static` local variable like the one above, return the same object, so they compare equal. But the specification doesn't require returning the same object every time; a replacement that creates a new backend on each call is also valid, in which case the two schedulers compare unequal, and really do represent two execution resources.
</details>
