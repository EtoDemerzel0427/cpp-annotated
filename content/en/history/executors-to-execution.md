---
title: "A decade of executors: from executors to std::execution"
summary: Why C++26's std::execution has no executor but has senders, receivers, operation states and schedulers; how the flaws of early executor designs shaped today's [exec] step by step, and why networking did not make it into the standard as a result.
tags: history, concurrency, parallelism, std::execution, networking
updated: 2026-10-19
---

!!! tldr
    - C++26's [[exec]] has no executor concept: work starts from a sender produced by a scheduler, `connect` yields an operation state, `start` starts it, and the result is delivered through one of the receiver's three completion functions.
    - Early executors did one thing: hand a `void()` closure to something else to run. Once submitted, there was no standard channel for results, errors or cancellation to come back, which is the main technical reason they were eventually abandoned.
    - Senders being lazy, `connect`/`start` being two steps, and operation states being immovable all serve to keep the state of an asynchronous operation off the heap.
    - C++17 execution policies only say how an algorithm call may be parallelized, not where it runs, which is why parallel algorithms still cannot be told to use a thread pool.
    - The Networking TS was built on the old executor model, and because of the dispute over asynchronous models it did not make it into C++26.

## The problem: hand work off to run elsewhere, and get the result back

C++11 brought `std::thread` and `std::async`, but no thread pool, and no general interface for handing a piece of work to some execution resource (a thread pool, an event loop, a GPU) to run. **Executor** is the name given to that interface.

The earliest executor proposal came from Google ([[N3562]], 2013). Its design was straightforward: an executor is an abstract base class, and work is type-erased with `std::function<void()>`.

```cpp title="N3562 style (historical proposal, never standardized; simplified)"
class executor {
public:
  virtual ~executor();
  virtual void add(std::function<void()> closure) = 0;
};

thread_pool pool(4);
std::promise<int> p;
std::future<int> f = p.get_future();
pool.add([&p] { p.set_value(6 * 7); });
int v = f.get();
```

The executor only runs the closure. The user has to pass the result out with `promise`/`future`, catch exceptions thrown in the closure themselves, and there is no agreed behavior for when the executor decides not to run the work. For coarse-grained tasks on a thread pool, the cost of a virtual call and a type erasure is negligible, and the design is good enough.

The debate over the next ten years revolved almost entirely around what is missing from this code.

## Three needs, three designs (2013–2015)

Besides Google's thread pool interface, two other kinds of users needed executors, and their needs were very different.

**Asynchronous I/O.** Christopher Kohlhoff's Asio (in Boost since 2005) is full of completion callbacks for asynchronous operations, each of them small. In [[N4046]] (2014) he pointed out that virtual interfaces and `std::function` prevent compilers from inlining layered callbacks, and that `std::function` requires copyability, ruling out move-only function objects. His alternative can be summed up in one sentence:

!!! history "N4046, §1"
    "An executor is to function execution as an allocator is to allocation."
    Executors should be lightweight, template-based policy objects, the way allocators are for memory allocation.

N4046 separated the **execution context** (the thread pool or event loop itself) from the executor (a lightweight handle to the context), and distinguished three ways of submitting, `dispatch`, `post` and `defer`, by whether immediate execution on the caller's thread is allowed.

```cpp title="Asio / N4046 style (historical proposal, never standardized)"
asio::io_context ctx;
auto ex = ctx.get_executor();      // a handle to the context
asio::post(ex, [] { /* ... */ });  // not executed on the caller's stack
```

**Bulk parallelism.** NVIDIA and others cared about parallel algorithms and GPUs: a single call has to create thousands of execution agents, so they needed a **bulk execution** interface ([[P0058R1]]).

By 2015 WG21 had three executor designs, each with its own emphasis. SG1, the study group for concurrency, asked the authors to unify them (Hoberock, [[P2033R0]]).

## Execution policies got in first (C++17)

While executors were still being argued over, parallel algorithms went into C++17 first ([[P0024R2]]). They take an **execution policy** argument:

```cpp run ok flags="-std=c++2c -fexperimental-library"
#include <algorithm>
#include <execution>
#include <vector>

int main() {
  std::vector<int> v{3, 1, 2};
  std::sort(std::execution::par, v.begin(), v.end());       // parallelism allowed
  std::sort(std::execution::par_unseq, v.begin(), v.end()); // parallelism and vectorization allowed
  return v.front() == 1 ? 0 : 1;
}
```

Clang 23 with libc++ only provides these policy objects with `-fexperimental-library`.

Execution policies and executors are often confused, but they answer different questions. A policy is a permit: it says how the implementation may schedule [[g:element-access-function|element access functions]], and what that requires of user code as a result, such as no locking under `par_unseq` ([[execpol]], [[algorithms.parallel]]). Which threads the work runs on is not the policy's business. NVIDIA's authors pointed out in [[N4406]] that this should be decided by an executor, and proposed combining them like this:

```cpp title="N4406 style (historical proposal, never standardized)"
std::sort(par.on(my_exec), data.begin(), data.end());
```

This combination depended on the executor design, so it never made it into the standard. Today, which threads `std::sort(std::execution::par, ...)` runs on is entirely up to the implementation. Proposals to let parallel algorithms accept a scheduler (such as [[P2500R2]]) had not entered the draft at the time of writing.

## P0443: three sets of needs in one proposal (2016–2020)

### Combinatorial explosion and properties

The unified proposal [[P0443R0]] (2016) handled this by including everyone's needs. By [[P2033R0]]'s count, R0 had seven executor categories and fifteen execution functions, with the function names themselves encoding three dimensions: blocking or not, returning a future or not, single or bulk. `execute`, `post`, `defer`, `async_execute`, `then_execute`, `bulk_then_execute`… the combinations grew quickly.

Later revisions ([[P0688R0]]) took these dimensions out of the function names and turned them into **properties** that could be required of an executor:

```cpp title="Property syntax after P0443R2 (historical proposal, never standardized)"
// require: must be satisfied, or compilation fails; prefer: satisfy if possible
auto ex2 = execution::require(ex, execution::oneway,
                              execution::never_blocking);
ex2.execute(f);
auto ex3 = execution::prefer(ex2, execution::continuation);
```

The property mechanism never made it into the standard. Only half of it remains in today's [[exec]]: you can ask about an object's properties through environment queries ([[exec.queryable]], [[exec.env]]), but there are no operations like require/prefer that change the object.

### Missing C++20

P0443 was originally expected to make C++20, but it didn't, and the networking library that depended on it was postponed with it. Stroustrup called this an example of "the best is the enemy of the good" (HOPL IV, §8.8.1).

## Why one-way execute didn't work (2018–2020)

By the last few revisions of P0443, the core operation was the one-way `execute(ex, f)`: eagerly submit a `void()` function object and return `void`. Another group of authors criticized this basis operation from practical experience; the systematic argument is in [[P1525R1]] (*One-Way execute is a Poor Basis Operation*). Its conclusion:

!!! history "P1525R1, §1"
    "The scheduler concept is a more foundational abstraction than the executor concept."
    A scheduler that produces senders is more fundamental than an executor with a one-way `execute`.

P1525R1 gives three technical reasons.

1. **Errors cannot be propagated.** Errors at submission time might be reported with exceptions, but errors that happen after submission and before execution (for example, an executor that creates threads lazily failing to create one, or an executor with deadlines dropping work that has timed out) have no channel back. How each executor handles them is up to the implementation, and generic code has no way to respond.
2. **Cancellation cannot be propagated.** When an executor decides not to run submitted work, it has no way to signal this other than destroying the function object, and destruction is not a suitable way to express cancellation.
3. **Dynamic allocation is required.** Eager submission means the state of every asynchronous task has to be allocated on the heap, because the caller does not know in advance how much storage is needed.

The paper also points out that `execute` can be implemented with a scheduler, but not faithfully the other way round.

<div class="compare" markdown="1">

```cpp title="P0443's execute (historical proposal)"
// returns void
execution::execute(ex, [] {
  int v = 6 * 7;
  // who gets v?
  // who is told about errors?
  // if ex doesn't run it, who knows?
});
```

```cpp title="A C++26 receiver"
struct print_receiver {
  using receiver_concept =
      ex::receiver_tag;
  void set_value(int) && noexcept;
  void set_error(std::exception_ptr)
      && noexcept;
  void set_stopped() && noexcept;
};
```

</div>

The right side is today's answer: when the work completes, exactly one of the receiver's three completion functions is called, with one channel each for values, errors and stopping ([[exec.recv]], [[exec.async.ops]]). This three-channel receiver first appeared in [[P1194R0]], a 2018 proposal for changes to P0443, where the third channel was called `set_done`; it was later renamed `set_stopped` ([[exec.set.stopped]]).

## How senders and receivers answer these questions

[[P2300R0]] (*std::execution*) in 2021 made a fundamental change on top of P0443: remove the executor concept and build everything on schedulers and senders. In 2024 its R10 was merged into C++26. Almost all the main rules in today's [[exec]] can be traced back to the three criticisms in the previous section.

### The full flow of a piece of work

```cpp title="Per the current draft (C++26); libc++ doesn't provide senders yet, so no verdict"
#include <execution>
#include <exception>
#include <print>
namespace ex = std::execution;

struct print_receiver {
  using receiver_concept = ex::receiver_tag;
  void set_value(int v) && noexcept { std::println("value {}", v); }
  void set_error(std::exception_ptr) && noexcept { std::println("error"); }
  void set_stopped() && noexcept { std::println("stopped"); }
};

int main() {
  auto sch = ex::get_parallel_scheduler();
  auto work = ex::schedule(sch) | ex::then([] { return 6 * 7; });

  // go through connect / start by hand; normal code lets sync_wait or spawn do it
  auto op = ex::connect(std::move(work), print_receiver{});
  ex::start(op);
  // op must live until the operation completes; the wait is omitted here
}
```

`schedule(sch)` produces a **sender**, which describes a piece of work that has not started yet; `then` wraps it into another sender. Nothing has run up to this point. `connect` combines the sender and a receiver into an **operation state**, and only `start` actually starts it.

### Laziness: avoiding a dilemma in the destructor

P0443's executors were eager: work started as soon as it was submitted. P2300 chose a purely lazy model, and one reason is destructors (§4.10): if an eager operation that has already started is discarded, the only options are to make that undefined behavior or to block and wait in the destructor, and neither is satisfactory. So [[exec.adapt]] specifies that sender adaptors must have no observable effects before `connect` and `start`.

### connect and start: no memory allocation

The first senders had a single basis operation, `submit(sndr, rcvr)`, which, like the eager `execute`, needed to put its state on the heap. [[P2006R1]] split it into two steps: `connect` returns an immovable operation state object, and the caller decides where to put it (usually on the stack, or embedded in the state of an enclosing operation); `start` then starts the work.

That is the origin of [[exec.connect]] and [[exec.opstate]]. The cost is that lifetime becomes the caller's responsibility: the comment on the last line of the example above is about exactly that, and [[exec.async.ops]] and [[exec.scope]] spend a lot of text specifying how long operation states must live.

### Completion signatures: knowing the result types in advance

Every sender must declare which types it may complete with; these are its [[g:completion-signature|completion signatures]] ([[exec.cmplsig]]). The reason is that handling results efficiently requires knowing the types in advance: `when_all` has to reserve storage in its operation state for each child operation's result, and `sync_wait` has to know what kind of `optional<tuple<...>>` to return.

Completion signatures can also depend on the environment provided by the receiver, which is why the concept in [[exec.snd]] is written `sender_in<Sndr, Env>`. Before C++26 was finalized, the way they are computed changed again, to a `consteval` function template with no arguments, `get_completion_signatures<Sndr, Env...>()`, with type errors reported by exceptions thrown during constant evaluation ([[P3557R3]], [[exec.getcomplsigs]]).

### Cancellation: a stop token in the environment

The cancellation design comes from [[P2175R0]]: the receiver provides a stop token through its environment, the sender queries it when needed, and on seeing a stop request it calls `set_stopped`. This reuses C++20's `std::stop_token` family ([[thread.stoptoken]]), to which P2300 added the non-allocating `inplace_stop_token`. See [[exec.get.stop.token]].

## Changes around the merge

P2300 changed many more times between its publication and the finalization of C++26. The changes below left visible marks in today's wording.

**Customization with member functions.** Early revisions implemented customization points with `tag_invoke`; later, following [[P2855R1]], they switched to member functions. So today `ex::set_value(rcvr, v)` is equivalent to calling `rcvr.set_value(v)`, and the receiver above can simply define member functions.

**Removing algorithms nobody waits for.** Work started by `ensure_started` and `start_detached` has nobody responsible for waiting until it finishes, and it may outlive the objects it refers to ([[P3187R1]]). They were removed and replaced by async scopes ([[P3149R11]]): eagerly started work must be associated with some scope via `spawn`, and the scope waits for all its work to finish before it ends. The rules are in [[exec.scope]] and [[exec.spawn]].

**A standard thread pool.** Following the direction of the library evolution group, P2300 did not include a thread pool. The later [[P2079R10]] added `parallel_scheduler`, with a replaceable backend ([[exec.par.scheduler]], [[exec.parschedrepl]]).

**Algorithm customization and domains.** Execution resources such as GPUs need to replace algorithms like `then` and `bulk` with specialized implementations, which is done through domain selection ([[P2999R3]]). One difficulty is that a sender like `just()` cannot know which domain it completes on before it knows where it is started, so the `then` after `starts_on(gpu, just())` could pick the CPU implementation. [[P3826R5]], just before C++26 was finalized, changed this to pass the receiver's environment when querying the completion domain, introducing `get_completion_domain` and `indeterminate_domain` ([[exec.get.compl.domain]], [[exec.domain.indeterminate]], [[exec.snd.transform]]).

**A bridge to coroutines.** Every awaitable type is automatically a sender; `as_awaitable` lets a coroutine `co_await` a sender ([[exec.as.awaitable]]). C++20 had only the language machinery for coroutines and no coroutine types; C++26 added `std::execution::task` through [[P3552R3]], and [[P3941R4]] specified how a `task` returns to the scheduler that started it ([[exec.affine]], [[exec.task]]).

```cpp title="Per the current draft; not yet provided by libc++, so no verdict"
#include <execution>
namespace ex = std::execution;

ex::task<int> compute(ex::scheduler auto sch) {
  int a = co_await (ex::schedule(sch) | ex::then([] { return 20; }));
  int b = co_await ex::just(22);
  co_return a + b;
}

int main() {
  auto sch = ex::get_parallel_scheduler();
  auto [v] = std::this_thread::sync_wait(compute(sch)).value();
  return v == 42 ? 0 : 1;
}
```

## Why networking didn't make it in

The Networking TS was published in 2018. Its asynchronous model is Kohlhoff's Asio model, with executors at its core. Once executors were replaced by senders, should the networking library change too? Two papers from 2021 represent the two positions.

[[P2464R0]] (Voutilainen) argued that P0443-style executors are merely work submitters, with no way to know whether submitted work succeeded or failed. The Networking TS assumes an executor will not fail between submission and invoking the continuation, but a standardized executor abstraction would have many implementations outside networking that are not bound by that assumption. It recommended finishing senders/receivers first and then building networking on top of them.

[[P2469R0]] (Kohlhoff et al.) took the opposite position: Asio's model has seen years of production use and has a mature way of composing based on completion tokens; P2300 is a DSL for composing operations on top of some asynchronous model, not an asynchronous model itself, and it should be built on top of Asio's model.

The library evolution group's subsequent poll ([[P2453R0]]) supported senders/receivers as the basis for most asynchronous use cases, with standard networking also built on them, but there was no consensus on whether to abandon the Networking TS. Networking did not make it into C++26 in the end. Proposals to rewrite the networking interface with senders (such as [[P2762R2]]) were still in progress at the time of writing.

## Where the rules of [exec] come from

| Design in [exec] | Problem it solves | Clauses |
|---|---|---|
| No `executor`, only `scheduler` | One-way `execute` cannot report errors or cancellation (P1525) | [[exec.sched]] |
| Receivers have three completion functions; exactly one is called | Values, errors and stopping each need a channel | [[exec.recv]], [[exec.async.ops]] |
| `connect` returns an operation state; only `start` starts it | Asynchronous state is not allocated on the heap (P2006) | [[exec.connect]], [[exec.opstate]] |
| Adaptors have no observable effects before `start` | Destruction cannot deal with a discarded eager operation | [[exec.adapt]] |
| Senders declare completion signatures, which can depend on the environment | Composite algorithms must reserve storage for results in advance | [[exec.cmplsig]], [[exec.getcomplsigs]] |
| Cancellation travels through a stop token in the environment | Cancellation needs an in-band channel | [[exec.get.stop.token]] |
| Only environment queries, no require/prefer | Only the query half of the property mechanism survived | [[exec.queryable]], [[exec.env]] |
| Customization through member functions | Replaces `tag_invoke` | [[exec]] |
| No `start_detached`; scopes instead | Work nobody waits for can dangle | [[exec.scope]], [[exec.spawn]] |
| Domains and `transform_sender` | Specialized execution resources replace algorithm implementations | [[exec.snd.transform]] |

The problems P0443 cared about that [exec] did not pick up are also clear: parallel algorithms still accept only execution policies and cannot be given a scheduler, and the interface of a standard networking library is not settled.

## Timeline

| Year | Event |
|---|---|
| 2013–2014 | Google's executors ([[N3562]]); Kohlhoff's template-based executors ([[N4046]]) |
| 2015 | Parallel algorithms need executors ([[N4406]]); SG1 asks for the three designs to be unified |
| 2016 | Parallel algorithms and execution policies merged into C++17; the unified proposal [[P0443R0]] |
| 2017 | P0443 simplified with properties ([[P0688R0]]) |
| 2018 | Networking TS published; first form of senders/receivers ([[P1194R0]]) |
| 2019 | Executors miss C++20; P0443 adds schedulers and senders |
| 2020 | `connect`/`start` replace `submit` ([[P2006R1]]); P1525R1 |
| 2021 | [[P2300R0]] removes executors; the networking dispute |
| 2024 | [[P2300R10]] merged into C++26 |
| 2025–2026 | Async scopes, `parallel_scheduler` and `task` merged; domains revised before finalization |

<details class="fine" markdown="1"><summary>Other sources</summary>

HOPL IV in the text is Bjarne Stroustrup, *Thriving in a Crowded and Changing World: C++ 2006–2020* (2020), §8.8.1. Merge dates are based on Herb Sutter's trip reports (herbsutter.com, March 2016, July 2024, June 2025).

Two blog posts by Eric Niebler help in understanding the motivation for the sender design: [Structured Concurrency](https://ericniebler.com/2020/11/08/structured-concurrency/) (2020) and [What are Senders Good For, Anyway?](https://ericniebler.com/2024/02/04/what-are-senders-good-for-anyway/) (2024).

Differing views on the 2021 dispute persist, and in 2026 several informational papers revisited this history (such as [[P4094R1]] and [[P4099R1]]). These papers represent their authors' own views.
</details>
