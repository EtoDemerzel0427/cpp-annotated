---
title: bulk, bulk_chunked, bulk_unchunked
summary: "After the predecessor completes, call f(i, values...) once for each index in [0, shape), then pass the predecessor's values on; the default implementation is sequential, and parallelism comes from scheduler customization."
updated: 2026-10-19
---

!!! tldr
    - After the predecessor completes successfully, `bulk(sndr, policy, shape, f)` calls `f(i, values...)` once for each `i ∈ [0, shape)`, then passes the predecessor's values on to downstream unchanged.
    - The predecessor's values are passed to `f` as lvalues; all iterations share the same values.
    - `bulk_chunked` has `f` handle a range `[b, e)` at a time, while `bulk_unchunked` handles only one index per call; `bulk` is rewritten into `bulk_chunked` before connect.
    - Without scheduler customization, all three run sequentially on the thread where the predecessor completed. Parallelism comes from customization by the scheduler's domain, for example `parallel_scheduler`.
    - `f` must obey the requirements parallel algorithms place on element access functions; on error or cancellation, only some of the iterations may have run.

The examples on this page use C++26 `std::execution` senders. The libc++ shipped with Clang 23 doesn't implement this part of the library yet, so none of the examples have been verified by compiling, and they carry no verdict.

## A parallel for in a sender chain

```cpp title="bulk.cpp"
namespace ex = std::execution;

std::vector<double> v(1'000'000);
auto s = ex::schedule(ex::get_parallel_scheduler())
       | ex::bulk(ex::par, v.size(),
                  [&v](std::size_t i) { v[i] = std::sqrt(double(i)); });
std::this_thread::sync_wait(std::move(s));
```

`bulk` is the data-parallel primitive of `std::execution`, playing the role of a parallel `for_each`. The difference is that it is a [[g:sender-adaptor|sender adaptor]]: it attaches after another [[g:sender|sender]] (here `schedule(...)`), and can be combined with scheduling, cancellation and error propagation.

This code distributes a million iterations onto a thread pool. As shown below, if `schedule(get_parallel_scheduler())` is replaced with `just()`, the same `bulk(par, ...)` runs sequentially on a single thread.

## Three algorithms (¶1–3)

¶1 All three algorithms repeat the same task for every index in an index space. They differ only in how `f` is called:

| Algorithm | How `f` is called | Guarantee on successful completion (¶9.1.1) |
|---|---|---|
| `bulk` | `f(i, args...)` | Called exactly once for each `i ∈ [0, shape)` |
| `bulk_unchunked` | `f(i, args...)` | Same as above; each iteration should run on a different execution agent |
| `bulk_chunked` | `f(b, e, args...)` | Called some number of times with `0 ≤ b < e ≤ shape`, each `i` falling in the `[b, e)` of exactly one call |

`bulk_chunked` lets `f` handle a contiguous range at a time, amortizing call overhead and making vectorization easier. `bulk_unchunked` says each index is an independent task, suitable when each element is a lot of work, or when iterations need to synchronize with each other (with a barrier, say) and so must each have their own execution agent. `bulk` makes no such demand, and the implementation chooses.

¶2 `bulk-algo(sndr, policy, shape, f)` is ill-formed if:

- ¶2.1 `sndr` isn't a sender;
- ¶2.2 `policy` isn't an execution policy (`is_execution_policy_v` is false, see [[execpol]]);
- ¶2.3 the type of `shape` isn't an integral type;
- ¶2.4 the type of `f` isn't copy constructible.

¶3 Otherwise, the result is a sender with `{policy, shape, f}` as its data and `sndr` as its child sender. An execution policy is stored by value if it's copyable; an implementation-defined execution policy might not be copyable, in which case only a const reference to it is stored.

## The default implementation is sequential (¶4–8)

¶4 `bulk` is rewritten into `bulk_chunked` before connect, with the callback wrapped in a loop that handles indices one at a time:

```cpp
auto new_f = [func = std::move(f)](Shape begin, Shape end, auto&&... vs)
    noexcept(noexcept(f(begin, vs...))) {
  while (begin != end) func(begin++, vs...);
};
return bulk_chunked(std::move(child), policy, shape, std::move(new_f));
```

Note 1 explains the intent: if the receiver's execution domain doesn't specifically customize `bulk`, `bulk` is handled as `bulk_chunked`. So a scheduler that wants to provide a parallel implementation only needs to customize two algorithms, `bulk_chunked` and `bulk_unchunked` (the rewriting mechanism is in [[exec.snd.transform]]).

¶5 Without customization, the default implementation of `bulk_chunked` calls `f(0, shape, args...)` just once after the predecessor completes with values, handing the whole range to `f`, and then forwards the values to the receiver. An exception thrown by `f` is caught and handed to the receiver as `set_error(exception_ptr)`. Error and stopped completions are forwarded directly.

¶7 The default implementation of `bulk_unchunked` is a plain loop `for (i = 0; i < shape; ++i) f(i, args...);`; the rest is the same as `bulk_chunked`.

!!! warning "Without customization, bulk doesn't run in parallel"
    Both default implementations execute synchronously on the execution agent where the predecessor completed, creating no new execution agents. The execution policy `par` only permits parallelism; it doesn't require it.

    Parallelism comes from domain customization. `parallel_scheduler`'s domain rewrites `bulk_chunked` and `bulk_unchunked` into calls to the backend's `schedule_bulk_chunked` and `schedule_bulk_unchunked` ([[exec.par.scheduler]]); `task_scheduler` also forwards them to the erased scheduler ([[exec.task.scheduler]]). So `just() | bulk(par, n, f)` handed to `sync_wait` uses only one thread, while `schedule(get_parallel_scheduler()) | bulk(par, n, f)` is what distributes to the thread pool.

¶6, ¶8 When completion signatures are computed, *check-types* checks, for each value completion `set_value(Ts...)` of the predecessor, whether `f` can be called with `(Shape, Ts&...)` (`(Shape, Shape, Ts&...)` for `bulk_chunked`), and reports an error if not. Note that the parameters are `Ts&`: the predecessor's values are passed to `f` as lvalues, and all iterations access the same values.

## Requirements on implementations (¶9–10)

¶9 This paragraph specifies behavior that any implementation (including a scheduler's customization) must have; otherwise the behavior of the result of connect is undefined:

- ¶9.1.1 When the whole operation completes successfully, `f` has been called as described in the table above.
- ¶9.1.2 When it completes with `set_error(eptr)`, `f` may have been called for some of the indices. `eptr` holds the exception thrown by `f`, a `bad_alloc` when allocating resources failed, or an exception derived from `runtime_error`.
- ¶9.1.3 When it completes with `set_stopped`, `f` may also have been called for some of the indices.
- ¶9.2 When the predecessor doesn't complete with a value, its completion is forwarded directly to the receiver.
- ¶9.3 The execution policy describes how the iterations may be parallelized. The permissions and requirements that [[algorithms.parallel.exec]] places on element access functions of parallel algorithms apply to `f` as well.

The consequences of ¶9.3 are the same as for parallel algorithms: with `par_unseq`, iterations on the same thread may be interleaved, so `f` can't acquire locks or perform other synchronization; with `seq`, a customized implementation must ensure the calls happen one after another, even on a GPU.

¶9.1.2 and ¶9.1.3 permit partial completion: after one iteration throws, the implementation may stop dispatching the remaining iterations, or may not, and iterations already running on other threads can't be taken back. So `f` can't assume that on error the other iterations definitely didn't run, nor that they definitely all ran.

¶10 Note 2 adds: when cancellation is requested, these operations may complete with `set_stopped`, or may ignore the request.

## Questions

!!! question "1. The values after bulk"
    ```cpp
    just(std::vector<int>(100))
      | bulk(par, 100, [](std::size_t i, std::vector<int>& v) { v[i] = i; })
      | then([](std::vector<int> v) { return v[99]; })
    ```
    Is the vector `then` receives the one `bulk` modified?

<details markdown="1">
<summary>Answer</summary>

Yes. `bulk` passes the predecessor's values to `f` as lvalues, all iterations modify the same object, and afterwards the same values are forwarded downstream. `just` sends the vector it stores as an rvalue, `f` modifies it through an lvalue reference, and `then` then move-constructs its own parameter from that rvalue.

Writing `f`'s parameter as `std::vector<int>&` is exactly right; taking it by value would copy the whole vector on every call, and the modifications wouldn't reach downstream. Each iteration writes a different element, so there's no data race.
</details>

!!! question "2. shape is 0"
    Does `bulk_chunked(s, par, 0, f)` call `f`? What about the default implementation?

<details markdown="1">
<summary>Answer</summary>

Per ¶9.1.1.3, every call must satisfy `b < e`. When `shape` is 0 there are no indices to cover, so a conforming implementation should not call `f` at all.

But the default implementation in ¶5 unconditionally calls `f(0, shape, args...)` once, that is, `f(0, 0, args...)`, where `b == e`, which is inconsistent with ¶9.1.1.3, which requires `b < e`. This is a small discrepancy in the draft between the default implementation and the contract. Writing `f` in the form `for (i = b; i < e; ++i)` tolerates an empty range, and the effect is the same either way.
</details>

## Summary

| Question | Answer |
|---|---|
| What `f` receives | An index (or range) plus lvalues of the predecessor's values |
| Values after `bulk` | The predecessor's values, forwarded unchanged |
| Who parallelizes | Customization by the scheduler's domain; the default implementation is sequential |
| Which algorithms to customize | `bulk_chunked` and `bulk_unchunked`; `bulk` is rewritten into the former |
| On error or cancellation | Only some of the iterations may have run |
