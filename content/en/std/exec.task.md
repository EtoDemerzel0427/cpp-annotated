---
title: task and scheduler affinity
summary: "execution::task is a lazy sender that can be used as a coroutine return type; after every co_await the coroutine returns to the scheduler the task was started on (scheduler affinity), and errors can be reported with exceptions or co_yield with_error. This page also covers affine, inline_scheduler and the type-erased task_scheduler."
updated: 2026-10-19
---

!!! tldr
    - `task<T>` is a coroutine return type that is itself a sender; calling the coroutine function only creates the coroutine frame, and execution begins only after it is connected and started.
    - Every `co_await` in the coroutine body is wrapped in `affine`, so after it completes the coroutine returns to the scheduler the task was started on. This is called scheduler affinity; setting the start scheduler type to `inline_scheduler` turns it off.
    - The start scheduler comes from `get_start_scheduler` on the receiver's environment, and by default is stored in the type-erased `task_scheduler`.
    - Errors have two routes: an exception escaping the coroutine body (`error_types` must include `exception_ptr`, otherwise `terminate`), or `co_yield with_error{e}`; cancellation makes the whole task complete with stopped directly.
    - The memory for the coroutine frame can be allocated through an `allocator_arg` parameter or through the allocator in the receiver's environment.

The examples on this page use C++26 `std::execution`. The libc++ shipped with Clang 23 doesn't implement this part of the library yet, so none of the examples have been verified by compiling, and they carry no verdict.

## Writing senders with coroutines

```cpp title="task.cpp"
namespace ex = std::execution;

ex::task<int> compute(int x) {
  co_return x * 2;
}

ex::task<int> pipeline() {
  int a = co_await compute(10);                // a task is a sender and can be co_awaited
  int b = co_await (ex::just(1)
                    | ex::then([](int v) { return v + 1; }));
  co_return a + b;                             // 22
}

int main() {
  auto [r] = std::this_thread::sync_wait(pipeline()).value();
}
```

[[exec.as.awaitable]] provides the parts for plugging [[g:sender|senders]] into coroutines: `co_await` a sender in a coroutine and you get its value. `std::execution::task` is the finished product assembled from those parts. It is a class template that can be used as a coroutine return type, and a `task` object is itself a sender: it can be handed to `sync_wait`, `then` or any other algorithm that accepts senders, and it can be `co_await`ed in another `task`.

[task.overview] ¶1 In `task<T, Environment>`, `T` is the type of the value delivered on successful completion, with `void` meaning no value; the operand of `co_return` in the coroutine becomes the argument to `set_value`. `Environment` is used to customize the behavior of `task`; see below.

## Scheduler affinity: affine [exec.affine]

### The problem: which thread are we on after co_await?

If a coroutine `co_await`s a sender that completes on a thread pool, it resumes execution on that thread-pool thread. If the coroutine was originally running on the UI thread, or holds resources that may only be used on a particular thread, this goes wrong. **Scheduler affinity** means that after each `co_await` the coroutine returns to the scheduler it was on and continues there. `task` provides this guarantee by default, and the means of doing so is `affine`.

¶1 `affine` adapts a sender into one that completes on the receiver's scheduler. If it can determine that the adapted sender already completes on the right scheduler, it may skip this scheduling. ¶2–3 `affine(sndr)` requires `sndr` to be a sender, otherwise it is ill-formed.

### Implementation: continues_on back to the start scheduler (¶4–5)

¶5 The transformation of `affine` is as follows, where `ev` is the receiver's environment:

```cpp
auto& [_, _, child] = sndr;
if constexpr (requires { std::forward_like<Sndr>(child).affine(); }) {
  return std::forward_like<Sndr>(child).affine();
} else {
  return continues_on(std::forward_like<Sndr>(child),
                      UNSTOPPABLE-SCHEDULER(get_start_scheduler(ev)));
}
```

If the child sender provides an `affine()` member itself, that is used. Otherwise `continues_on` transfers to the start scheduler in the receiver's environment after the child completes. ¶6 recommends that implementations give senders known to complete where they are started (`just`, `just_error`, `just_stopped`, `read_env`, `write_env`) an `affine` member, saving unnecessary scheduling.

¶4 *UNSTOPPABLE-SCHEDULER*(sch) is a wrapped scheduler: `schedule` is equivalent to `unstoppable(schedule(sch))`, and queries and comparisons are forwarded to `sch`. The return trip is made non-cancellable because a cancellation request may arrive only after the child operation has completed. If the return scheduling were cancelled, it would complete with `set_stopped`, and that completion would happen on the wrong thread, exactly what affinity is meant to prevent.

### The return trip can't fail (¶7)

¶7 If the receiver's environment has no `get_start_scheduler`, or the scheduler obtained doesn't satisfy *infallible-scheduler* (scheduling can only complete with `set_value`, plus `set_stopped` if it can be cancelled; see [[exec.sched#8]]), then computing the completion signatures throws an exception, which shows up as a type error at compile time.

¶7 also explains that starting the `affine` operation starts `sndr` on the current execution agent and completes on the execution resource of the start scheduler; if the current resource is that resource, completion may happen before `start` returns.

## Two helper schedulers

### inline_scheduler: no thread switch [exec.inline.scheduler]

```cpp
class inline_scheduler {
public:
  using scheduler_concept = scheduler_tag;
  constexpr inline-sender schedule() noexcept { return {}; }
  constexpr bool operator==(const inline_scheduler&) const noexcept = default;
};
```

¶1 All `inline_scheduler` objects compare equal, and the answers to queries are given by *inline-attrs*: its completion scheduler is the current scheduler in the environment, wherever the caller is. ¶2–4 The sender returned by `schedule()` has only one way of completing, `set_value_t()`, and on start it calls `set_value` on the receiver directly.

In other words, `schedule(inline_scheduler{})` completes immediately on the current thread. Setting a `task`'s start scheduler type to `inline_scheduler` turns scheduler affinity off.

### task_scheduler: a type-erased scheduler [exec.task.scheduler]

`task` needs to remember at run time which scheduler it was started on, and different schedulers all have different types. `task_scheduler` is a type-erased scheduler, and is the default start scheduler type of `task`.

```cpp
class task_scheduler {
public:
  using scheduler_concept = scheduler_tag;
  template<class Sch, class Allocator = allocator<void>>
    requires (!same_as<task_scheduler, remove_cvref_t<Sch>>) && scheduler<Sch>
  explicit task_scheduler(Sch&& sch, Allocator alloc = {});
  task_scheduler(const task_scheduler&) = default;
  task_scheduler& operator=(const task_scheduler&) = default;
  see below schedule();
  // operator== with task_scheduler and with concrete scheduler types
private:
  shared_ptr<parallel_scheduler_replacement::parallel_scheduler_backend> sch_;
};
```

It has no default constructor; it must be constructed from a concrete scheduler.

¶1 The forward progress guarantee is taken from the erased scheduler. ¶2 The erased scheduler must satisfy *infallible-scheduler*<env<>>, that is, in an empty environment it can only complete with `set_value()`. ¶3–5 On construction the internal object is allocated with `allocate_shared` and the given allocator, and later allocations use copies of that allocator; ¶4 recommends avoiding dynamic allocation for small scheduler objects.

¶6–7 Two `task_scheduler`s compare equal if and only if the erased schedulers compare equal; when compared with a concrete scheduler `Sch`, a different type gives false, and the same type compares values.

Interestingly, it reuses the backend interface of the [[exec.par.scheduler|parallel scheduler]], `parallel_scheduler_backend`, as its virtual interface for type erasure. The internal *backend-for*<Sch> derives from this interface:

- ¶10 `schedule(r, s)` connects `schedule(sched_)` to a receiver wrapping the proxy `r`, and starts it;
- ¶11 `schedule_bulk_chunked(shape, r, s)` picks a chunk size and uses `bulk(just-sndr-like, par, num_chunks, fn)` to call `r.execute(b, e)` chunk by chunk;
- ¶12 `schedule_bulk_unchunked(shape, r, s)` uses `bulk(just-sndr-like, par, shape, fn)`, calling `r.execute(i, i + 1)` each time.

¶9 *just-sndr-like* is a sender that completes with `set_value_t()` and reports `sched_` as its completion scheduler. So the internal `bulk` is customized by the erased scheduler's domain, and the latter's parallel `bulk` implementation is preserved.

¶13 The sender returned by `schedule()` reports `*this` as its completion scheduler, and on start calls `sch_->schedule(r, s)`. Its completion signatures are just `set_value_t()` in an environment that can't be stopped, and additionally `set_stopped_t()` otherwise. ¶14–15 *ts-domain* rewrites `bulk_chunked` and `bulk_unchunked` senders whose predecessor completes on a `task_scheduler` into calls of the backend's `schedule_bulk_chunked` and `schedule_bulk_unchunked`. That way a `bulk` scheduled through `task_scheduler` can still use the erased scheduler's parallel implementation.

## The task class template [task.class]

```cpp
template<class T = void, class Environment = env<>>
class task {
public:
  using sender_concept = sender_tag;
  using allocator_type = see below;
  using start_scheduler_type = see below;
  using stop_source_type = see below;
  using stop_token_type = decltype(declval<stop_source_type>().get_token());
  using error_types = see below;
  class promise_type;

  task(task&&) noexcept;
  ~task();
  template<class Self, class... Env> static consteval auto get_completion_signatures();
  template<receiver Rcvr> state<Rcvr> connect(Rcvr&& rcvr) &&;
private:
  coroutine_handle<promise_type> handle;   // exposition only
};
```

¶1 When `T` is `void`, a reference type, or a cv-unqualified non-array object type, and `Environment` is a class type, `task<T, Environment>` models `sender`; otherwise a program that instantiates its definition is ill-formed.

`task` can only be moved, not copied. `connect` has only an rvalue version: a `task` owns its coroutine frame exclusively and can be connected only once.

### Customization through Environment (¶2–4)

¶2 Several nested types are taken from `Environment`, with defaults when not found:

| Member | Taken from | Default |
|---|---|---|
| `allocator_type` | `Environment::allocator_type` | `allocator<byte>` |
| `start_scheduler_type` | `Environment::start_scheduler_type` | `task_scheduler` |
| `stop_source_type` | `Environment::stop_source_type` | `inplace_stop_source` |
| `error_types` | `Environment::error_types` | `completion_signatures<set_error_t(exception_ptr)>` |

¶3 `error_types` must be a specialization of `completion_signatures` whose elements are all of the form `set_error_t(E)`, otherwise it is ill-formed. ¶4 `allocator_type` must meet *Cpp17Allocator*, the scheduler type must model `scheduler`, and the stop source type must model *stoppable-source*. (The text of ¶4 writes the scheduler type as `scheduler_type`; it means `start_scheduler_type`.)

### Members [task.members]

¶1–2 The move constructor takes the coroutine handle from the source object. The destructor destroys the coroutine frame if the handle is non-null: when a `task` that was never connected is destroyed, its coroutine never started executing, and the frame is destroyed with it.

¶3–4 `get_completion_signatures` returns `set_value_t()` (when `T` is `void`) or `set_value_t(T)`, all the signatures in `error_types`, and `set_stopped_t()`. The result doesn't depend on the environment, so `task` is a [[g:non-dependent-sender|non-dependent sender]].

¶5–7 `connect` requires that an `allocator_type` can be obtained from the allocator in the receiver's environment or by default construction; it transfers ownership of the coroutine handle to the newly created operation state `state<Rcvr>`.

## The operation state: task::state [task.state]

`state<Rcvr>` is the [[g:operation-state|operation state]] of `task`. It holds the coroutine handle, the receiver, an optional stop source, two environment objects, the result `optional<T>` (when `T` isn't `void`) and an `exception_ptr`. The result and the exception live here rather than in the coroutine frame, which matters at completion.

¶1–2 On construction, `own-env` (specified by `Environment::env_type`, or `env<>` if there is none) is first constructed from the receiver's environment, and the `Environment` object is then constructed from it; if neither can be constructed, it is ill-formed. ¶3 The destructor destroys the coroutine frame if the handle is non-null.

¶4 `start()` associates this state object, the receiver and the start scheduler with the coroutine's promise object, then resumes the coroutine. The start scheduler *SCHED*(prom) is `start_scheduler_type(get_start_scheduler(get_env(rcvr)))`, default-constructed if that can't be obtained; if neither works, it is ill-formed.

The default `start_scheduler_type` is `task_scheduler`, which can't be default-constructed. So by default `task` requires the receiver's environment to say where it is started. The environment of `sync_wait` provides `get_start_scheduler` ([[exec.consumers]]).

¶5 *get-stop-token* determines the stop token seen inside the coroutine. If the stop source's token type is the same as the token type of the receiver's environment, the receiver's token is used directly; otherwise a stop source is constructed on demand, its `stop_requested()` and `stop_possible()` reflecting the state of the receiver's token, and its token is returned.

## The promise type [task.promise]

```cpp
class task<T, Environment>::promise_type {
public:
  task get_return_object() noexcept;
  static constexpr suspend_always initial_suspend() noexcept { return {}; }
  auto final_suspend() noexcept;
  void unhandled_exception();
  coroutine_handle<> unhandled_stopped() noexcept;
  void return_void();                                  // only when T is void
  template<class V = T> void return_value(V&& value);  // only when T isn't void
  template<class E> unspecified yield_value(with_error<E> error);
  template<sender Sender> auto await_transform(Sender&& sndr);
  unspecified get_env() const noexcept;
  // operator new / operator delete, see below
};
```

`initial_suspend` returns `suspend_always`, so `task` is lazy: calling the coroutine function only creates the coroutine frame, and execution begins at `start`. ¶2 `get_return_object` returns a `task` holding this coroutine's handle.

### Every co_await goes through affine (¶6)

¶6 `await_transform(sndr)`: when `start_scheduler_type` is `inline_scheduler` it returns `as_awaitable(sndr, *this)`, otherwise `as_awaitable(affine(sndr), *this)`. This is what implements scheduler affinity: every `co_await` in the coroutine is wrapped in `affine`, and after completing it returns to the start scheduler.

`await_transform` accepts only senders, so `co_await`ing an awaitable that isn't a sender inside a `task` works only if it is also recognized as a sender.

¶12 `get_env()` is the environment seen by senders `co_await`ed in the coroutine: `get_start_scheduler` returns the start scheduler, `get_allocator` returns an allocator converted from the allocator of the receiver's environment (default-constructed if not available), and `get_stop_token` returns the result of *get-stop-token*; other queries, if they are forwarding queries and the `Environment` object can answer them, are forwarded to it, and are otherwise ill-formed.

### Completion: destroy the frame first, then notify the receiver (¶3, ¶10–11)

¶10–11 `return_void` does nothing; `return_value(v)` stores the value in the state object's `result`.

¶3 The awaitable returned by `final_suspend` is responsible for completing the whole operation: it first destroys the coroutine frame with `destroy()`, then, depending on whether an exception was stored in the state object, calls `set_error(rcvr, error)` or `set_value(rcvr[, *result])`. The result lives in the state object, so the frame can be destroyed first. For why this order is needed, see question 1.

### Errors and cancellation (¶4–5, ¶7–9)

¶7 `unhandled_exception`: when `error_types` contains `set_error_t(exception_ptr)`, it stores the current exception in the state object; otherwise it calls `terminate()`.

¶4–5 `co_yield with_error{e}` is the error route that doesn't use exceptions. `e` must be convertible to exactly one argument type *Cerr* of the `set_error_t`s in `error_types`, otherwise it is ill-formed. The returned awaitable suspends the coroutine, destroys the frame, and then calls `set_error(rcvr, Cerr(std::move(e)))`.

```cpp title="with-error.cpp"
struct env_t {
  using error_types =
    ex::completion_signatures<ex::set_error_t(std::error_code)>;
};

ex::task<int, env_t> parse(std::string_view s) {
  if (s.empty())
    co_yield ex::with_error{std::make_error_code(std::errc::invalid_argument)};
  co_return 42;
}
```

This `task`'s `error_types` doesn't include `exception_ptr`, so any exception escaping the coroutine body leads to `terminate`. Errors must be reported with `co_yield with_error{...}`. This lets `task` be used in code that disables exceptions or doesn't want to pay their cost.

¶8–9 `unhandled_stopped`: when a `co_await`ed sender completes with stopped, the coroutine isn't resumed; this function is called instead. It destroys the coroutine frame, calls `set_stopped` on the receiver, and returns `noop_coroutine()`. That is, `task` turns internal cancellation directly into a stopped completion of the whole task (see [[exec.as.awaitable]]).

### Allocating the coroutine frame (¶13–19)

```cpp title="task-allocator.cpp"
ex::task<int> work(std::allocator_arg_t,
                   std::pmr::polymorphic_allocator<> a, int x) {
  co_return x;   // the coroutine frame is allocated through a (converted to allocator_type)
}
```

¶13 `operator new(size)` without an allocator uses a default-constructed `allocator_type`. ¶14–17 The overload taking `allocator_arg_t, Alloc` uses the given allocator; another overload starting with `const This&` is for member function coroutines, whose first parameter is the object itself. Storage is allocated in units of an unspecified type whose size and alignment equal `__STDCPP_DEFAULT_NEW_ALIGNMENT__`, together with enough information for the `operator delete` of ¶18–19 to deallocate it with an equal allocator.

## Common misconceptions

!!! pitfall "After co_await schedule(pool) we're on the thread pool"
    The default `start_scheduler_type` is `task_scheduler`, and `co_await`ed senders are wrapped in `affine`. So after `co_await schedule(pool)` the coroutine doesn't stay on the thread pool; it is brought back to the start scheduler. Work that should run on the thread pool should be put entirely into one sender and then `co_await`ed, for example `co_await (schedule(pool) | then(f))`; or use a `task` whose `start_scheduler_type` is `inline_scheduler` to turn affinity off.

!!! pitfall "When error_types doesn't include exception_ptr, exceptions don't become error completions"
    In such a `task`, any exception escaping the coroutine body leads to `terminate` (¶7). This includes the exception rethrown by `await_resume` when `co_await`ing a sender that completes with an `exception_ptr` error.

## Questions

!!! question "1. Why does final_suspend destroy the frame before calling the completion function?"
    [task.promise] ¶3 specifies destroying the coroutine frame with `destroy()` first and then calling the receiver's completion function. What would happen the other way round?

<details markdown="1">
<summary>Answer</summary>

The receiver's completion function may destroy the `task`'s operation state `state` ([[exec.async.ops#8]]), and `state`'s destructor destroys the coroutine frame when the handle is non-null ([task.state] ¶3). If completion came first and frame destruction second: inside the completion function `state` is destroyed and the frame along with it; control then returns to the awaitable of `final_suspend` (which lives in that already-destroyed frame) to destroy the frame, accessing memory that has already been freed. Destroying the frame first and then taking the result and the receiver out of `state` to complete avoids this problem; storing the result and the receiver in `state` rather than in the frame is precisely what allows this order.

The wording doesn't say explicitly that `st.handle` must be set to null after the frame is destroyed, yet `state`'s destructor destroys the frame again when the handle is non-null. Implementations must avoid this double destruction themselves, for example by taking the handle out with `exchange` before calling `destroy()`.
</details>

!!! question "2. Why must affine's return trip be unable to fail?"
    [exec.affine] ¶7 requires the start scheduler to satisfy *infallible-scheduler*, otherwise computing the completion signatures throws. If the return scheduling were allowed to fail, what problem would `task` run into?

<details markdown="1">
<summary>Answer</summary>

A failed return scheduling completes with `set_error`, and that completion happens where scheduling failed, on an unspecified execution agent (see what [[exec.on]] specifies for `continues_on`). For `task`, this would mean `co_await` resuming on a thread other than the start scheduler and throwing an exception. The scheduler affinity guarantee is broken, and on the error-handling path of all places, where it is hardest to notice. Requiring the return trip to be infallible turns this situation into a compile-time error.
</details>

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[task.promise] ¶1 explains that *STATE*(prom), *RCVR*(prom) and *SCHED*(prom), mentioned below, are the objects associated with the promise object in `state<Rcvr>::start`.

`task`, `affine`, `inline_scheduler` and `task_scheduler` aren't part of P2300 itself; they were added by later proposals, and the wording around `affine` and `get_start_scheduler` is a later revision still. When reading blog posts or older versions of reference implementations, keep in mind that they may describe an earlier design.

</details>
