---
title: std::execution (P2300)
summary: Why C++26's sender/receiver model replaced futures, coroutines and executors as the foundation of standard asynchrony. What laziness, three completion channels, allocation-free connect/start, stop tokens, structured concurrency and member-function customization each solve, and what each costs.
tags: std::execution, senders, receivers, asynchrony, concurrency, structured concurrency, proposal
group: C++26
updated: 2026-10-19
---

!!! tldr
    - C++11's `std::async`/`std::future` allocate shared state on the heap every time, can only be composed by blocking a thread, have no cancellation, and cannot choose where to run. P2300 argues these costs come from the future itself: it is a handle to work that has already started running.
    - P2300's foundation is a callback with three channels (a receiver) plus a lazy description of work (a sender): `connect` packages the two into an immovable operation state that lives on the caller's stack, and only `start` begins execution, so composition itself needs no memory allocation.
    - Each of the key trade-offs had a rejected rival: eager execution (whose destructor can only choose between UB, detaching and blocking), treating cancellation as an error, `start_detached`-style work that nobody waits for, and `tag_invoke`-style ADL customization.
    - The costs are a complex interface, heavy metaprogramming, hard-to-read error messages, and lifetime rules left to the caller. At the time of writing, the libc++ shipped with Clang 23 has no senders yet, so examples using the standard interface carry no verdict.

## What C++11's asynchronous interface lacks

The interface C++11 provides for asynchronous work is `std::async` and `std::future`. The problems appear as soon as you want to chain two steps:

```cpp title="chain.cpp" run ok
#include <future>
#include <cstdio>

int main() {
  std::future<int> a = std::async(std::launch::async,
                                  [] { return 6 * 7; });
  // to add 1 after a completes: another thread has to be tied up waiting
  std::future<int> b = std::async(std::launch::async,
      [a = std::move(a)]() mutable { return a.get() + 1; });
  std::printf("%d\n", b.get());
}
```

The standard `future` has no `then`. The second step must either `get()` on the caller's thread, or, as above, start another thread just to block waiting for the first step. Running with Clang 23 plus TSan prints `43` with no data race reported, but two threads were used up for one addition.

The `future` returned by `async` has another surprising behavior. The shared state is held jointly by the thread `async` started and the `future`, and the last `future` to release it waits for that thread to finish ([[futures.async#4]], Note 2 of [[futures.async#5]]):

```cpp title="dtor.cpp" run ok
#include <chrono>
#include <cstdio>
#include <future>
#include <thread>
using namespace std::chrono;

int main() {
  auto t0 = steady_clock::now();
  (void)std::async(std::launch::async, [] {
    std::this_thread::sleep_for(500ms);
  });  // the temporary future is destroyed here, and blocks
  auto ms = duration_cast<milliseconds>(steady_clock::now() - t0);
  std::printf("%lld ms\n", (long long)ms.count());
}
```

It prints about `506 ms`: what looks like a fire-and-forget call is actually synchronous. Without the `(void)`, Clang warns because of `async`'s `[[nodiscard]]`. Why `async`'s destructor behaves this way is covered in [[history/threads-and-memory-model]].

Finally, allocation. Wrap one `async` plus `get` in a counting global `operator new`:

```cpp title="alloc.cpp" run ok
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <future>
#include <new>

std::atomic<int> n{0};
void* operator new(std::size_t sz) {
  ++n;
  if (void* p = std::malloc(sz)) return p;
  throw std::bad_alloc();
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }

int main() {
  int before = n;
  std::future<int> f = std::async(std::launch::async,
                                  [] { return 42; });
  int v = f.get();
  std::printf("%d, %d allocations\n", v, n - before);
}
```

libc++ prints `42, 4 allocations` at both `-O0` and `-O2`. The exact count is an implementation detail, but the allocation of the shared state is unavoidable: it is referenced by two threads at once, and neither side alone determines its lifetime.

The motivation section of [[P2300R10]] (§1.1) sums these up as `async`/`future`/`promise` being inefficient, hard to use correctly, and lacking genericity. The rules themselves are in [[futures]].

## The design space: what to build asynchrony on

P2300 §1.9 discusses several candidate foundational abstractions one by one and explains why each falls short.

**Futures.** Even with a `then` added to `future` (as the Concurrency TS did), the costs remain. §1.9.1 argues: a future is a handle to work that has already been scheduled for execution, and the result may arrive before or after a continuation is attached, so there must be shared state, synchronization, and usually type erasure of the work and the continuation. These costs are inherent in the abstraction.

**Coroutines.** C++20 coroutines ([[topics/coroutines]]) are the most natural to write, and usually start suspended, needing no synchronization. But the coroutine frame usually has to be dynamically allocated, and calls go through an indirect jump because the frame's layout is hidden from the type system. §1.9.2 acknowledges that HALO (coroutine heap allocation elision) can remove these overheads, but points out that it needs many conditions to hold at once, and the authors' experience is that in real code it often doesn't kick in. For a set of generic algorithms that must be callable on hot paths, that is unacceptable.

**Callbacks.** Callbacks are the oldest and most efficient, but have no standard shape: how values and errors are passed, and with how many arguments, varies from library to library, leaving generic code nothing to work with; and most shapes leave no room for cancellation (§1.9.3).

**Executors.** An executor is an interface for handing a `void()` function object off to run somewhere; a series of proposals, represented by [[P0443R14]], argued over it for years. Its problem is that once the work is handed off, there is no standard channel for results, errors and cancellation to come back, and eager submission means every task's state has to live on the heap ([[P1525R1]]). This history is in [[history/executors-to-execution]].

P2300's answer is to start from callbacks and fix their two shortcomings:

- Give the callback a standard shape. A **receiver** ([[g:receiver]]) is a callback with three entry points: `set_value`, `set_error` and `set_stopped`, for success, failure and cancellation respectively.
- Don't let the callback be attached only after the work has started. A **sender** ([[g:sender]]) is a description of work that has not yet started; it is first combined with a receiver, and then started.

Most of the remaining design follows from these two points.

## A toy model to make connect and start clear

Below is a minimal model with only a value channel. It is not the `std::execution` interface, but the skeleton is the same: `just` produces a value, `then` calls a function on it, `connect` combines a sender and a receiver into an **operation state** ([[g:operation-state]]), and only `start` begins execution.

```cpp title="toy.cpp" run ok
#include <cstdio>
#include <utility>

// minimal model: value channel only, not the std::execution interface
template<class T>
struct just_sender {
  T v;
  template<class R> struct op {
    T v; R r;
    void start() { std::move(r).set_value(v); }
  };
  template<class R> op<R> connect(R r) && {
    return {std::move(v), std::move(r)};
  }
};

template<class S, class F>
struct then_sender {
  S s; F f;
  template<class R> struct rcvr {
    F f; R r;
    template<class... A> void set_value(A&&... a) && {
      std::move(r).set_value(f(std::forward<A>(a)...));
    }
  };
  template<class R> auto connect(R r) && {
    return std::move(s).connect(
        rcvr<R>{std::move(f), std::move(r)});
  }
};

struct print_rcvr {
  void set_value(int v) && { std::printf("value %d\n", v); }
};

int main() {
  auto snd = then_sender{just_sender{6}, [](int x) {
    std::puts("then runs");
    return x * 7;
  }};
  std::puts("built");
  auto op = std::move(snd).connect(print_rcvr{});
  std::puts("connected");
  op.start();
}
```

Clang 23 (ASan + UBSan) prints `built`, `connected`, `then runs`, `value 42`. Three things are worth noting:

1. Neither constructing the sender nor `connect` runs user code; the body of `then` runs only after `start`.
2. `then_sender::connect` wraps the downstream receiver in its own receiver and hands that to the upstream `connect`. The resulting `op` is a nested plain object holding all the state the whole chain needs, with a size known at compile time, sitting on `main`'s stack.
3. The whole chain consists of direct, inlinable calls. At `-O2`, all that remains in `main`'s assembly is three calls to `puts` and one call to `printf` with the constant `42` as its argument, with no allocation at all.

Compared with the 4 allocations of `async` above, this is why [[P2006R1]] split the single basic operation `submit(sndr, rcvr)` into two steps, `connect` and `start`: the caller decides where the operation state lives. The cost is also in point 2: the operation state must live until the operation completes. The standard further specifies that copying or moving an operation state produced from a library-provided sender is ill-formed ([[exec.opstate.general#3]]), so it can only be constructed in place and used in place.

## What the standard interface looks like

With the same structure in the standard interface, users usually deal only with sender algorithms and **schedulers** ([[g:scheduler]], lightweight handles to execution resources):

```cpp title="Per the current draft; libc++ does not provide senders yet, no verdict"
#include <execution>
#include <cstdio>
namespace ex = std::execution;

int main() {
  ex::scheduler auto sch = ex::get_parallel_scheduler();
  auto a = ex::schedule(sch) | ex::then([] { return 6; });
  auto b = ex::schedule(sch) | ex::then([] { return 7; });
  auto work = ex::when_all(std::move(a), std::move(b))
            | ex::then([](int x, int y) { return x * y; });
  auto [v] = std::this_thread::sync_wait(std::move(work)).value();
  std::printf("%d\n", v);
}
```

`schedule(sch)` produces a sender that completes on `sch`; `then` and `when_all` are **sender adaptors** ([[g:sender-adaptor]]); `sync_wait` does `connect` and `start` on the current thread and blocks waiting for the result. Receivers and operation states are generated internally by the algorithms; P2300 §5.1 and §5.2 say explicitly that they are aimed only at people writing sender algorithms. The full relationship between the four concepts is in [[exec]].

`sync_wait` returns `optional<tuple<...>>`: it has a value on value completion, is empty on stopped completion, and throws on error completion ([[exec.sync.wait#11]]). These three outcomes correspond directly to the receiver's three entry points.

## Trade-off one: lazy or eager

Some algorithms in P2300's early revisions could execute eagerly. §4.10 records why they were removed. The core question: if a sender already running on another thread is destroyed without having been `connect`ed and `start`ed, what should its destructor do?

| Strategy | Consequence | Precedent in the standard library |
|---|---|---|
| Make it undefined behavior | Very hard to guarantee every eager operation is waited for when exceptions occur | A variant of `std::thread`: `terminate` on destruction |
| Let it keep running in the background | No way to tell when the resources it uses can be safely destroyed, except with things like `shared_ptr` | `thread::detach` |
| Block waiting in the destructor | Stays structured, but can deadlock in a thread pool | `async`'s `future`; `jthread` requests stop and then waits |

§4.10.1 concludes that none of the three is satisfactory. Several further reasons are more implementation-oriented:

- If senders are always lazy, algorithms can assume `start` happens before work begins, and chaining several operations in sequence needs no synchronization; supporting eager senders would require defending against the worst case, or having every sender report whether it is eager (§4.10.2).
- An eager operation, at the time it starts, doesn't yet know whether the receiver it will later be connected to will request stopping, so it must reserve space for a type-erased stop callback and bear the run-time cost of cancellation (§4.10.3).
- Contextual information such as the stop token, the allocator and the current scheduler is passed down through the receiver at `connect` time, and an operation that has already started cannot get it (§4.10.4).

This decision lands in ¶3.1 of [[exec.adapt.general#3]]: unless otherwise specified, a sender adaptor has no observable effects, other than moving and copying its arguments, until the returned sender is `connect`ed and `start`ed.

Work that needs to start eagerly has not gone away; it is managed by async scopes instead, as described in the section on structured concurrency below.

## Trade-off two: why cancellation has its own channel

Given an error channel, why not treat cancellation as a kind of error? [[P1677R2]] discusses exactly this question (from R2 on, its title calls cancellation *serendipitous-success*, roughly: no result, but not a failure either). There are two main reasons.

First, algorithms react differently to errors and cancellation. A generic `retry` should retry on error and stop on cancellation; if cancellation also went through the error channel, `retry` would have to check every error to see whether it was a cancellation, and different libraries represent cancellation with different types. With the channels separated, `retry` only handles `set_error` and passes `set_stopped` through unchanged.

Second, cancellation is common in asynchronous code, and reporting it as exceptions would create lots of noise for logging, debugging and other analysis tools. P1677R2 also recounts how an earlier attempt to represent interruption with exceptions (`std::interrupted` in early revisions of `jthread`) was removed in committee.

This three-way split is written into the definition of an asynchronous operation: a started asynchronous operation eventually completes exactly once with one of three **dispositions**, success, failure or cancellation, where a cancellation completion carries no result data ([[exec.async.ops#2]] ¶2.3).

!!! std
    "After its start operation has begun executing, exactly one completion operation shall execute."
    After `start` begins executing, exactly one completion operation executes. ([[exec.async.ops#8]])

## Trade-off three: how a cancellation request reaches where it is needed

`set_stopped` is how a cancelled operation reports its outcome downstream. The other direction, how upstream requests that an already started operation stop, comes from [[P2175R0]]: the receiver's environment provides a stop token, which the operation queries when it needs to. This reuses C++20's `std::stop_token` family ([[thread.stoptoken]]), to which P2300 added the `stoppable_token` concept, the allocation-free `inplace_stop_token`, and `never_stop_token`, which never requests stopping.

A few details show the direction of this design:

- **Cancellation is optional.** When the receiver's environment provides no stop token, `get_stop_token` returns `never_stop_token` ([[exec.get.stop.token#2]] ¶2.2). Its `stop_possible()` is `false` at compile time, so code handling cancellation can be optimized away entirely (P2300 §4.9.2).
- **Users usually don't touch tokens.** `when_all` provides its own `inplace_stop_source` for its child operations and requests stopping as soon as any child completes with an error or stopped ([[exec.when.all#17]]). Sibling operations that query the token can finish early; those that don't run to completion as usual, and `when_all` reports downstream only after all children have completed.
- **Cancellation is inherently racy.** A stop request may arrive from another thread at any moment, and an implementation of `start` has to carefully order registering the stop callback and starting the operation (§4.9.3). [[exec.recv.concepts#3]] therefore specifies that the stop token need only be valid for the lifetime of the operation, and stop callbacks must be destroyed before the completion operation.

P2300R10 itself records an open concern: during SG1's initial review there were doubts about the run-time cost of this machinery in single-threaded scenarios (§4.9.4).

## Trade-off four: structured concurrency

Before being merged into the working draft, [[P2300R10]] removed `ensure_started`, `start_detached` and `execute`. The reason comes from [[P3187R1]]: they all start work eagerly without guaranteeing that anyone waits for it to finish, which brings back the same problem as in the table above. P3187R1 points out in particular that the sender returned by `ensure_started` seems to compose normally with other algorithms, and mostly it does work; the data races only show up on failure paths.

The replacement is async scopes ([[P3149R11]]): eagerly started work must first be associated with an **async scope** ([[g:async-scope]]), which is responsible for waiting for all associated work to complete before it ends.

```cpp title="Per the current draft; not provided by libc++ yet, no verdict"
#include <execution>
namespace ex = std::execution;

void serve(ex::scheduler auto sch, int requests) {
  ex::counting_scope scope;
  for (int i = 0; i < requests; ++i)
    ex::spawn(ex::schedule(sch) | ex::then([i] { /* handle request i */ }),
              scope.get_token());
  // scope can only be destroyed once all spawned work has finished
  std::this_thread::sync_wait(scope.join());
}
```

`spawn` tries to associate the sender with the scope, and if that succeeds, starts it eagerly ([[exec.spawn#1]]). Forgetting `join` doesn't silently leave dangling work behind: when a counting scope is destroyed, unless it has finished joining or was never used, `std::terminate` is called (for `simple_counting_scope`, see [[exec.simple.counting.ctor#2]]). This is the same choice as `std::thread`, except that there is now an explicit place to wait.

The same reasoning later also removed `split`. [[P3682R0]] points out that the senders produced by `split` share a state that has to be dynamically allocated when the sender is created, so it can't use the allocator from the receiver's environment; and for the second and later consumers, the operation has already been started by the first, making it eager again. There is no `split` in [[exec.adapt]] in the current draft.

## Trade-off five: how to customize

Standard algorithms need to be replaceable by execution resources (a GPU scheduler wants its own `bulk`), and users need to be able to write their own receivers and senders. P2300's customization mechanism changed twice.

### From tag_invoke to member functions

Early revisions of P2300 used `tag_invoke` ([[P1895R0]]): every customization is a [[g:hidden-friend|hidden friend]] named `tag_invoke`, found by [[g:argument-dependent-lookup|argument-dependent lookup]] (ADL), with the type of the first parameter distinguishing which operation is being customized. R9 switched to named member functions per [[P2855R1]]. P2300 §5.9 shows the same receiver written both ways:

<div class="compare" markdown="1">

```cpp title="R8 and earlier (tag_invoke)"
struct my_receiver {
  friend void tag_invoke(
      execution::set_value_t,
      my_receiver&& self,
      int value) noexcept {
    std::cout << value;
  }
};
```

```cpp title="R9 on (member functions)"
struct my_receiver {
  using receiver_concept =
      execution::receiver_tag;

  void set_value(int value)
      && noexcept {
    std::cout << value;
  }
};
```

</div>

The `receiver_tag` on the right is the current draft's name; in P2300R10 it was `receiver_t`. [[P3940R0]] proposed renaming the four concept tags of `<execution>` from `_t` to `_tag`, consistent with the naming of other concept tags in the standard library, and the current draft adopted the new names.

P2855R1 sums up its goal as not using ADL anywhere. Its reasons come mainly from implementation: ADL searches the associated namespaces of template arguments, so to control the size of overload sets, implementers had to put each algorithm's internal types in nested detail namespaces and wrap template parameters in generic code to keep their namespaces from being searched by ADL. With member functions, none of these techniques are needed. The general problems of ADL and customization points are covered in [[topics/name-lookup-and-customization]].

Queries are the only place that keeps the tag parameter: members of an environment such as `query(get_stop_token_t)` take the query object as their first parameter, so a wrapper type can forward every query it doesn't recognize with a single member template.

The trace of this decision in the wording is direct: the expression `set_value(rcvr, vs...)` is expression-equivalent to `rcvr.set_value(vs...)` and is required to be `noexcept` ([[exec.set.value#1]]); `connect(sndr, rcvr)` first tries `new_sndr.connect(rcvr)` ([[exec.connect#6]] ¶6.1). Since `receiver_adaptor` is gone, receiver adaptors are written with inheritance, so [[exec.recv.concepts#2]] specifies that `final` classes do not satisfy `receiver`.

### Algorithm customization and domains

Member functions solved customization of the basic operations; customizing algorithms (`then`, `bulk`) is a separate problem. P2300R7's approach was to ask the predecessor sender for its completion scheduler and dispatch on the scheduler. [[P2999R3]] points out that this is not enough: `just(42)` doesn't know where it will complete until it is started; where `when_all(s1, s2)` completes depends on which child finishes last at run time; and in `on(sch, then(just(), f))`, the `then` is constructed before the scheduler is specified.

P2999R3's solution is to have senders report a **domain** (a tag type for an execution domain), and, in addition to dispatching when the sender is constructed, to dispatch again at `connect` time using the receiver's environment. P2999's wording left out the second half, and [[P3303R1]] filled it in: `connect` and `get_completion_signatures` first transform the sender with `transform_sender`. Before C++26 was finalized, [[P3826R5]] changed how the completion domain is queried again; details are in [[exec.snd.transform]] and [[history/executors-to-execution]].

## Coroutines: not the foundation, but first-class citizens

P2300 does not make coroutines the foundation, but lets the two be used with each other (§4.15–4.17):

- Any awaitable type that doesn't depend on a particular promise type automatically satisfies `sender`, so `sync_wait` can accept a coroutine task directly.
- A coroutine's promise type, with the help of `with_awaitable_senders`, can `co_await` a sender that completes with a single value ([[exec.as.awaitable]]).
- When an awaited sender completes with `set_stopped`, the coroutine behaves as if an exception that `catch(...)` cannot catch were thrown, unwinding along the coroutine call chain until some level converts the stop into a value or error with an adaptor such as `stopped_as_optional`.

P2300 itself has no coroutine task type; `std::execution::task` was added to C++26 by [[P3552R3]], and how a task returns to the scheduler that started it is specified by [[P3941R4]] ([[exec.task]]).

## Wording: the [exec] clause

P2300R10 adds the [[exec]] clause (clause 33 of the current draft), and adds new stop token types in [[thread.stoptoken]]. The table below maps the design above to subclauses:

| Design | Subclause |
|---|---|
| An asynchronous operation completes exactly once with one of three dispositions | [[exec.async.ops#2]], [[exec.async.ops#8]] |
| Destroying the operation state before the asynchronous operation ends is UB | [[exec.async.ops#7]], [[exec.opstate.general#2]] |
| Copying or moving an operation state produced from a library-provided sender is ill-formed | [[exec.opstate.general#3]] |
| Completion functions accept only receiver rvalues and must be `noexcept` | [[exec.set.value#1]] |
| `connect` transforms the sender first, then calls the member `connect` | [[exec.connect#2]], [[exec.connect#6]] |
| Adaptors have no observable effects before `start` | [[exec.adapt.general#3]] |
| The stop token is queried from the receiver's environment, defaulting to `never_stop_token` | [[exec.get.stop.token#2]] |
| `final` classes are not receivers | [[exec.recv.concepts#2]] |
| Eager work must be associated with an async scope | [[exec.scope]], [[exec.spawn]] |

C++17 already has the header `<execution>` (execution policies, see [[execpol]]), and P2300 only adds to it, so Annex C's [[diff.cpp23]] has no related incompatibility entries. The feature-test macro `__cpp_lib_senders` is `202506L` in the current draft.

## Costs and criticism

**A complex interface.** Writing a new sender algorithm means dealing with operation states, receiver wrappers, environment forwarding and completion signatures. P2300's response is that most users only use ready-made algorithms; it also cites user feedback to the effect that senders/receivers are not simple, but are not the main source of complexity (§1.10.3).

**Heavy metaprogramming and hard-to-read error messages.** Every sender must compute its [[g:completion-signature|completion signatures]] at compile time. The introduction of [[P3557R3]] says plainly that this is the hardest part of writing sender algorithms, and using an algorithm wrongly produces long errors buried deep in metaprograms. Its solution is to report type errors by throwing exceptions during constant evaluation, which relies on C++26's [[papers/constexpr-exceptions]], so `get_completion_signatures` became a `consteval` function template with no arguments.

**Compile time.** A whole sender chain expands at compile time into one nested type, which is why the toy model could inline to a constant, but it also means the number of template instantiations grows with the length of the chain. No implementation was available here, so no measurements can be given.

**Lifetime is left to the caller.** The price of not allocating is that the operation state must live until the operation completes, otherwise the behavior is undefined ([[exec.opstate.general#2]]). Consumers like `sync_wait` and `spawn` manage this for the user; code that writes `connect`/`start` by hand must guarantee it itself.

**Needs not met.** Parallel algorithms still only accept execution policies and cannot be given a scheduler; the standard networking library did not make C++26. How these two relate to the executors debate is covered in [[history/executors-to-execution]].

## Follow-up proposals and implementation status

| Proposal | Contents | Current draft |
|---|---|---|
| [[P3187R1]] | Remove `ensure_started`, `start_detached` and `execute` | Removed in P2300R10 |
| [[P3149R11]] | Async scopes: `counting_scope`, `spawn`, `spawn_future` | Merged, [[exec.scope]] |
| [[P2079R10]] | `parallel_scheduler`, with a replaceable backend | Merged, [[exec.par.scheduler]] |
| [[P3552R3]] | The coroutine task type `task` | Merged, [[exec.task]] |
| [[P3682R0]] | Remove `split` | No `split` in the current draft |
| [[P3557R3]] | Report completion signature errors with constexpr exceptions | Merged, [[exec.getcomplsigs]] |
| [[P3826R5]] | Change the domain query for algorithm customization | Merged, [[exec.snd.transform]] |

**Implementations.** The practical experience P2300 §1.10 lists comes mainly from two libraries: Meta's libunifex, and NVIDIA's reference implementation stdexec. The latter was written to the specification, used to find errors in it, and later also provided schedulers for CUDA and others.

The libc++ of Homebrew Clang 23.1.3 under `-std=c++2c` (with or without `-fexperimental-library`) has no `std::execution::just`, no `std::inplace_stop_source`, and does not define `__cpp_lib_senders`. So no code using the standard interface carries a verdict. GCC and MSVC were not tested.

## Questions

!!! question "1. Hand-written connect/start"
    What is wrong with the function below?
    
    ```cpp
    void fire(ex::scheduler auto sch, auto rcvr) {
      auto op = ex::connect(ex::schedule(sch), std::move(rcvr));
      ex::start(op);
    }
    ```

<details markdown="1">
<summary>Answer</summary>

After `start`, the work may still be queued on `sch`, and `op` is destroyed when `fire` returns. Destroying the operation state during the lifetime of the asynchronous operation is undefined behavior ([[exec.opstate.general#2]], [[exec.async.ops#7]]). This is exactly the problem `start_detached` tried to solve, and was removed for because nobody waits. Use `spawn` to associate the work with an async scope, and `join` before the scope ends.

</details>

!!! question "2. Where does `just(42)` complete?"
    Why can't the implementation of `then` be chosen from the predecessor sender's completion scheduler alone?

<details markdown="1">
<summary>Answer</summary>

`just(42)` completes synchronously on whatever execution resource starts it, and when constructed it doesn't know who will start it, so it has no completion scheduler. `then(just(42), f)` only runs on the GPU once wrapped in `starts_on(gpu, ...)`, and the `then` was constructed before that. That is why [[P2999R3]] added a second dispatch at `connect` time, when the receiver's environment already says where the operation is started ([[exec.connect#2]]).

</details>

!!! question "3. Treating cancellation as an error"
    Imagine a design with only two channels, `set_value` and `set_error`, with cancellation represented by a special exception type. What more would a generic `retry` algorithm have to do?

<details markdown="1">
<summary>Answer</summary>

`retry` would have to check every error to see whether it is the kind that means cancellation, otherwise it would keep retrying after the user had already asked to stop. And as a generic algorithm, it doesn't know which library's cancellation type the upstream uses. Three channels turn this check into a dispatch at the type level: `retry` only customizes the error channel and forwards the stopped channel unchanged ([[P1677R2]]).

</details>
