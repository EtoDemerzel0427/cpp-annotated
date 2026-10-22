---
title: Futures and async
summary: "How to hand the result of a computation (a value or an exception) from one thread to another: making a shared state ready, abandoning and releasing it, the rules for promise, future, shared_future and packaged_task, the launch policies of async and deferred functions, and why the future returned by async blocks in its destructor."
updated: 2026-10-19
---

!!! tldr
    - The writing side (`promise`, `packaged_task`, `async`) and the reading side (`future`, `shared_future`) refer to a common shared state. The writer stores a result and makes the state ready; the reader's `get()` waits for it and retrieves the result. Writes made before the store are visible after `get()` returns.
    - If the writer is destroyed without storing a result, a `broken_promise` error is stored in the shared state, so the reader does not wait forever.
    - `future::get()` can be called only once; afterwards `valid()` is false and calling member functions is UB. Use `shared_future` when the result has to be read in several places.
    - The default policy of `async` lets the implementation choose deferred execution: the function then runs in the caller's thread only at the first `get()`/`wait()`. Pass `launch::async` explicitly when you need concurrency.
    - For a shared state created with `launch::async`, the destructor of the last future waits for the thread to finish, so discarding the return value of `async` makes the code serial.

## Handing a result to another thread [futures.overview]

```cpp run title="promise-basic.cpp" ok
#include <cstdio>
#include <future>
#include <stdexcept>
#include <thread>

int main() {
  std::promise<int> p;
  std::future<int> f = p.get_future();
  std::jthread t([&p] {
    try {
      throw std::runtime_error("disk full");
    } catch (...) {
      p.set_exception(std::current_exception());   // exceptions can be passed along too
    }
  });
  try {
    (void)f.get();                                  // waits and rethrows
  } catch (const std::exception& e) {
    std::printf("caught: %s\n", e.what());
  }
}
```

¶1 The components described in [futures] let a program retrieve, in one thread, the result of a function that may run in the same thread or another one; the result can be a value or an exception. Note 1 adds that they are not only for multithreaded programs.

Without these components you would have to set up a mutex, a condition variable, an `optional<T>` and an `exception_ptr` yourself. `<future>` packages them into a shared state.

## Shared state [futures.state]

This subclause defines the terms used throughout [futures].

¶1 A **[[g:shared-state|shared state]]** consists of some state information and a **result** that may not yet have been evaluated; the result is a value (possibly `void`) or an exception. ¶2 Note 2 points out that the result can also be a function that computes the result, as with the deferred policy of `async`.

¶3 An **[[g:asynchronous-return-object|asynchronous return object]]** reads the result from a shared state, e.g. `future`. Its **waiting functions** are those that may block to wait for the shared state to become ready, e.g. `wait` and `get`. Those that may return early because of a timeout are **timed waiting functions**, e.g. `wait_for`; the rest are **non-timed waiting functions**.

¶4 An **[[g:asynchronous-provider|asynchronous provider]]** provides a result to a shared state, e.g. `promise` and `packaged_task`.

### Ready (¶6, ¶8)

¶8 A shared state is **ready** only if it holds a value or an exception ready for retrieval. ¶6 When an asynchronous provider **makes its shared state ready**, it first marks it as ready, then unblocks all execution agents waiting for it to become ready.

### Synchronization (¶9)

!!! std
    The storage of the result (whether normal or exceptional) into the shared state synchronizes with the successful return from a call to a waiting function on the shared state.

¶9 Calls that successfully set the result of a shared state [[g:synchronizes-with|synchronize with]] calls that successfully detect the resulting ready state; storing the result (normal or exceptional) into the shared state synchronizes with the successful return of a waiting function on that shared state. So all writes before `p.set_value(x)` are visible after `f.get()` returns.

¶10 Some functions (such as `promise::set_value_at_thread_exit`) delay making the shared state ready until the current thread exits; then the destruction of each of the thread's `thread_local` objects is sequenced before making the state ready.

¶11 Accesses to the result of the same shared state may conflict ([[intro.races]]). Note 3 gives an example: concurrent accesses to the result through references returned by `shared_future::get()` must be read-only or otherwise synchronized.

### Abandoning and releasing (¶5, ¶7)

¶7 When an asynchronous provider **[[g:abandon-shared-state|abandons]]** its shared state, it means:

- ¶7.1 if the state is not yet ready, store a `future_error` exception with error condition `broken_promise` and make the state ready;
- ¶7.2 then release the shared state.

The destructors of `promise` and `packaged_task` both abandon the shared state, so when the writer forgets to store a result, the reader gets an exception instead of blocking forever.

¶5 When an asynchronous return object or asynchronous provider **releases** its shared state, it means:

- ¶5.1 if it holds the last reference, the shared state is destroyed;
- ¶5.2 it gives up its reference to the shared state;
- ¶5.3 these actions do not block waiting for the shared state to become ready, with one exception: they may block if the shared state was created by `std::async`, is not yet ready, and this is the last reference.

¶5.3 is one source of the blocking destructor of the future returned by `async`; the `async` section below covers the other half.

## promise [futures.promise]

`promise` is the most basic asynchronous provider: the program stores a value or exception into it by hand.

```cpp run title="promise-broken.cpp" ok
#include <cstdio>
#include <future>

int main() {
  std::future<int> f;
  {
    std::promise<int> p;
    f = p.get_future();
  }                                   // ~promise abandons the shared state, storing broken_promise
  try {
    (void)f.get();
  } catch (const std::future_error& e) {
    std::puts(e.code() == std::future_errc::broken_promise ? "broken_promise" : "other");
  }
}
```

¶1 For the primary template, `R` must be an object type that meets *Cpp17Destructible*. ¶2 There are also two specializations, `promise<R&>` and `promise<void>`.

¶3 `set_value`, `set_exception` and their `_at_thread_exit` versions behave as if they acquire a single mutex associated with the promise while updating it. So two threads calling `set_value` at the same time is not a data race; the second one throws.

¶4 The constructor creates the shared state. ¶7 The destructor abandons the shared state.

¶13–¶15 `get_future()` returns a `future<R>` sharing the shared state of `*this`. It throws `no_state` if there is no shared state, and `future_already_retrieved` if `get_future` has already been called; one promise corresponds to only one `future`. ¶12 It does not introduce data races with calls such as `set_value`.

¶16–¶18 `set_value` atomically stores the value and makes the state ready. It throws `promise_already_satisfied` if there is already a result and `no_state` if there is no shared state; exceptions thrown when copying or moving `R` propagate too. ¶19–¶22 `set_exception(p)` is similar, with the precondition that `p` is not null {{ub}}.

¶23–¶29 `set_value_at_thread_exit` and `set_exception_at_thread_exit` store the result immediately but make the state ready only when the current thread exits, after all `thread_local` objects have been destroyed.

## future [futures.unique.future]

¶1 `future` is an asynchronous return object that does not share its shared state with other asynchronous return objects. A default-constructed `future` has no shared state. ¶2 Note 1 points out that the member functions of `future` do not synchronize with each other, so a `future` object must be used by only one thread.

### get can be called only once (¶3, ¶15–¶19)

¶16–¶19 `get()` first waits until the shared state is ready, retrieves the result, then releases the shared state. The primary template returns the value moved out, `future<R&>` returns the stored reference, and `future<void>` returns nothing; if an exception is stored, it is thrown. ¶17 Afterwards `valid()` is false.

¶3 Calling any member function other than the destructor, move assignment, `share` or `valid` on a `future` with `valid() == false` is undefined {{ub}}. So a second `get()` is UB.

```cpp title="future-get-twice.cpp" ub
#include <future>
int main() {
  std::promise<int> p;
  auto f = p.get_future();
  p.set_value(1);
  (void)f.get();
  (void)f.get();   // UB: valid() == false
}
```

¶3 recommends that implementations detect this case and throw `no_state`. libc++ does not: with Clang 23 + libc++ this program simply segfaults, because the shared-state pointer has already been nulled out.

### Other members

- ¶10 The destructor releases the shared state and may block per [futures.state] ¶5.3. ¶11 Move assignment first releases its own original shared state.
- ¶13–¶14 `share()` returns `shared_future<R>(std::move(*this))`; afterwards `valid()` is false.
- ¶20 `valid()` returns whether it refers to a shared state. ¶21 `wait()` blocks until the shared state is ready.
- ¶22–¶27 `wait_for`, `wait_until`: if the shared state contains a deferred function, they do nothing and return `future_status::deferred`; otherwise they block until ready or timeout and return `ready` or `timeout`.

## shared_future [futures.shared.future]

```cpp run title="shared-future.cpp" ok
#include <cstdio>
#include <future>
#include <thread>

int main() {
  std::promise<int> p;
  std::shared_future<int> sf = p.get_future().share();
  std::jthread a([sf] { std::printf("a: %d\n", sf.get()); });   // one copy per thread
  std::jthread b([sf] { std::printf("b: %d\n", sf.get()); });
  p.set_value(7);
}
```

¶1 `shared_future` may share its shared state with other asynchronous return objects. It is copyable and is usually obtained from `future::share()`.

¶2 Note 1 points out that the member functions of `shared_future` do not synchronize with each other, but do synchronize with the shared state. So it is safe for several threads to each hold their own copy and call `get()`; calling member functions on the same `shared_future` object from several threads has no such guarantee, e.g. a copy assignment to it concurrent with `get()` is a data race. The lambdas in the example capture `sf` by value precisely so that each thread has its own copy.

¶3 As with `future`, calling any member other than the destructor, move assignment, copy assignment or `valid()` when `valid()` is false is UB.

¶19–¶20 `get()` does not release the shared state and may be called many times. The primary template returns a `const R&` to the value in the shared state:

- ¶18 Note 5 points out that access to this value object is not synchronized, so operations on `R` may introduce data races. Several threads reading it is fine; if `R` has `mutable` members, or someone modifies it after a `const_cast`, that is a data race.
- ¶20.1 Note 6 points out that accessing it through this reference after the shared state has been destroyed is UB. Do not store the reference anywhere that outlives the `shared_future` it came from.

The remaining members (construction and assignment in ¶6–¶16; `valid`, `wait`, `wait_for`, `wait_until` in ¶22–¶29) correspond to those of `future`.

## async [futures.async]

```cpp
template<class F, class... Args>
  future<invoke_result_t<decay_t<F>, decay_t<Args>...>> async(F&& f, Args&&... args);
template<class F, class... Args>
  future<invoke_result_t<decay_t<F>, decay_t<Args>...>> async(launch policy, F&& f, Args&&... args);
```

¶1 `async` may launch a function in a new thread and provides the function's result through a `future` that shares a shared state with it. ¶2 The decayed types of `f` and the arguments must be constructible from the arguments and invocable.

### Launch policies (¶3)

¶3 The first overload is equivalent to calling the second with `launch::async | launch::deferred`. The second overload creates a shared state associated with the returned `future`; what happens next depends on `policy`, and when more than one condition applies, the implementation may pick any of them:

- ¶3.1 If `launch::async` is set, it is as if `invoke(auto(std::forward<F>(f)), auto(std::forward<Args>(args))...)` were called in a new thread represented by a `thread` object. The copies of the arguments are created in the thread that calls `async`. The return value or the exception thrown is stored in the shared state. The `thread` object is stored in the shared state.
- ¶3.2 If `launch::deferred` is set, copies of `f` and the arguments are stored in the shared state; together they form a **[[g:deferred-function|deferred function]]**. The first call to a non-timed waiting function on an asynchronous return object referring to this shared state invokes the deferred function in the thread that called the waiting function, and stores the result in the shared state. Once the invocation starts, the function is no longer considered deferred.
- ¶3.3 If `policy` sets nothing, or sets a value specified by neither the standard nor the implementation, the behavior is undefined {{ub}}.

This paragraph has three consequences:

- The default policy lets the implementation choose `deferred`. Then the function does not run concurrently at all; it runs synchronously in your thread only when you call `get()` or `wait()`. The recommended practice in ¶3.2 also says implementations should defer the invocation or the policy choice when no more concurrency can be effectively exploited.
- "As if in a new thread" does not mean a new thread is necessarily created. The implementation may reuse threads as long as they behave like new ones, e.g. `thread_local` variables are fresh.
- A timed wait does not start a deferred function. When `wait_for` or `wait_until` meets a deferred shared state, it returns `future_status::deferred` immediately without invoking the function ([futures.unique.future] ¶22).

¶8 The standard's example illustrates the first point:

```cpp
int work1(int value);
int work2(int value);
int work(int value) {
  auto handle = std::async([=]{ return work2(value); });
  int tmp = work1(value);
  return tmp + handle.get();    // #1
}
```

Note 3 points out that there may be no concurrency at all at `#1`: the default policy may choose `deferred`, the lambda is then invoked only at `get()`, and `work1` and `work2` run one after the other in the same thread. When concurrency must be guaranteed, pass `launch::async` explicitly.

### Synchronization and the blocking destructor (¶4)

¶4 The call to `async` synchronizes with the invocation of `f`; the completion of `f` is sequenced before the shared state is made ready. Note 1 points out that this holds regardless of the policy chosen and whether the future is moved to another thread; but `f` might never be invoked at all (deferred and never waited on), in which case its completion never happens.

If the implementation chooses the `launch::async` policy:

- ¶4.1 a call to a waiting function on an asynchronous return object sharing this state must block until the associated thread has completed, as if joined, or else time out;
- ¶4.2 the completion of the associated thread synchronizes with the return from the first function that successfully detects the ready state of the shared state, or with the return from the last function that releases the shared state, whichever happens first.

¶4.1 together with [futures.state] ¶5.3 gives the rule for the blocking destructor of the future returned by `async`: when the last `future` referring to a `launch::async` shared state is destroyed and the thread has not finished, the destructor waits for it. This keeps `async` from leaving unmanaged threads behind, but it also sets a trap:

```cpp run title="async-blocking-dtor.cpp" ok
#include <chrono>
#include <cstdio>
#include <future>
#include <thread>
using namespace std::chrono;

int main() {
  auto t0 = steady_clock::now();
  (void)std::async(std::launch::async, [] { std::this_thread::sleep_for(200ms); });  // the temporary future is destroyed at the semicolon and waits
  (void)std::async(std::launch::async, [] { std::this_thread::sleep_for(200ms); });  // so the two calls run serially
  auto ms = duration_cast<milliseconds>(steady_clock::now() - t0).count();
  std::printf("%lld ms\n", static_cast<long long>(ms));   // about 400 ms, not 200 ms
}
```

The temporary `future` returned by `std::async(...)` is destroyed at the end of the full-expression, and its destructor waits for the thread to finish. So fire-and-forget code written with `async` actually runs serially. libc++ marks `async` `[[nodiscard]]`, so discarding the return value produces a warning; the example ignores it explicitly with `(void)`. ¶5 Note 2 also warns that if a `future` obtained from `async` is moved out of the local scope, its destructor may still block.

¶6–¶7 If `policy` is exactly `launch::async` and a new thread cannot be started, `system_error` (`resource_unavailable_try_again`) is thrown; if allocating internal data structures fails, `bad_alloc` is thrown. Throwing is required only for plain `launch::async`: under the default policy the implementation may fall back to `deferred`.

!!! impl "async in libc++"
    Under the default policy, libc++ always tries to create a new thread first and falls back to `deferred` only if thread creation throws. So on libc++ an `async` with the default policy is in practice always concurrent, but that is an implementation choice, not a guarantee of the standard.

    Each `launch::async` creates a new `std::thread` and immediately `detach`es it. When the shared state's reference count drops to zero, it first waits for the state to be ready, then destroys it.

!!! impl "libc++ does not achieve \"as if joined\""
    libc++ waits for the shared state to become ready, not for the thread to finish. As soon as the result is stored in the shared state, `get()` and the destructor may return, while the detached thread may still be destroying its `thread_local` objects. The following program prints `0` on libc++; under ¶4.1 it should print `1`:

    ```cpp run title="async-thread-local.cpp" ok
    #include <atomic>
    #include <chrono>
    #include <cstdio>
    #include <future>
    #include <thread>

    std::atomic<bool> tl_destroyed{false};
    struct TL {
      ~TL() {
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
        tl_destroyed = true;
      }
    };
    thread_local TL tl;

    int main() {
      auto f = std::async(std::launch::async, [] { (void)&tl; return 1; });
      (void)f.get();   // per ¶4.1 the thread should already be as if joined, with thread_local destroyed
      std::printf("%d\n", tl_destroyed.load());
    }
    ```

    So on libc++, after `get()` returns you cannot assume that the side effects of destroying `thread_local` objects in the `async` thread (such as flushing a thread-local log buffer) have happened.

## packaged_task [futures.task]

```cpp run title="packaged-task.cpp" ok
#include <cstdio>
#include <future>
#include <thread>

int main() {
  std::packaged_task task([](int a, int b) { return a * b; });   // deduced as packaged_task<int(int, int)>
  std::future<int> f = task.get_future();
  std::jthread worker(std::move(task), 6, 7);    // invoked in another thread
  std::printf("%d\n", f.get());                  // 42
}
```

[futures.task.general] ¶1 `packaged_task` wraps a function or callable object and, when invoked, stores the return value in a future. ¶2 When it is invoked, it invokes the stored task and stores the result (normal or exceptional) in the shared state.

It combines a callable object with an asynchronous provider and is commonly used to hand tasks to a thread pool: the pool only invokes it, and the result is delivered to the future automatically. It is move-only and is defined only for function types `R(ArgTypes...)`.

Key points of [futures.task.members]:

- ¶1 A default-constructed object has no shared state and no task. ¶2–¶7 Constructing from a callable `f` requires `f` to be invocable with `ArgTypes...` with a result convertible to `R`; the allocator version uses the allocator to allocate the shared state.
- ¶8–¶9 The deduction guide deduces `packaged_task<R(A...)>` from the type of `&F::operator()`, so the example does not need template arguments.
- ¶14 The destructor abandons the shared state: if the task is destroyed without ever being invoked, the future gets `broken_promise`.
- ¶18–¶21 `get_future()` is as for promise: it can be called only once.
- ¶22–¶24 `operator()(args...)` is as if *INVOKE*`<R>(f, args...)`, storing the return value or exception and making the shared state ready. It throws `no_state` if there is no shared state and `promise_already_satisfied` if the task has already been invoked.
- ¶25–¶27 `make_ready_at_thread_exit(args...)` invokes the task and stores the result immediately, but makes the state ready only when the thread exits.
- ¶28–¶29 `reset()` throws `no_state` if `!valid()`; otherwise it constructs a new shared state with the same task and allocator, and the old state is abandoned (Note 2). You must then call `get_future()` again.

## Common misconceptions

!!! pitfall "Polling an async future with wait_for always eventually sees ready"
    ```cpp
    auto f = std::async(work);                    // default policy: may be deferred
    while (f.wait_for(0s) != std::future_status::ready) {   // when deferred, always returns deferred
      do_other_things();
    }
    ```
    A timed wait does not start a deferred function, so this loop may never end. Check for `future_status::deferred`, or use `launch::async` explicitly.

!!! pitfall "future::get can be called many times"
    The second call is UB (¶3). When the result has to be read in several places, convert to `shared_future` with `share()`.

!!! pitfall "The reference returned by shared_future::get can be held for a long time"
    The reference points into the shared state. After the last `shared_future` is destroyed the shared state is destroyed, and the reference dangles.

!!! pitfall "async always starts a new thread"
    The default policy may be `deferred`, in which case assumptions about `thread_local` variables and about running in another thread do not hold. libc++ happens to always start a new thread; other implementations need not.

## Questions

!!! question "Question 1"
    What happens with `promise<int> p; auto f = p.get_future(); p.set_value(1); p.set_value(2);`?

<details markdown="1">
<summary>Answer</summary>

The second `set_value` throws `future_error` with error condition `promise_already_satisfied` ([futures.promise] ¶17–¶18). This is a defined error, not UB. The value in the shared state is still 1.
</details>

!!! question "Question 2"
    A `launch::deferred` `future` is turned into a `shared_future` with `share()`, and three threads, each holding a copy, call `get()` at the same time. How many times does the deferred function run, and in which thread?

<details markdown="1">
<summary>Answer</summary>

Once. Per [futures.async] ¶3.2, the thread that first calls a non-timed waiting function invokes the deferred function; once the invocation has started, the function is no longer deferred, and the other threads' `get()` simply waits for it to become ready. Which thread is first is unspecified.
</details>

## Summary

| Role | Type | Key points |
|---|---|---|
| Asynchronous provider | `promise`, `packaged_task`, inside `async` | Abandons the shared state on destruction, storing `broken_promise` if not ready |
| Asynchronous return object | `future` (exclusive), `shared_future` (shared) | Calling members when `valid()` is false is UB; `future::get` can be called only once |
| Synchronization | Storing the result synchronizes with the successful return of a waiting function | [futures.state] ¶9 |
| `async(launch::async)` | As if run in a new thread | The last future's destructor waits for the thread to finish |
| `async(launch::deferred)` | Deferred function | Runs in the waiting thread at the first non-timed wait; timed waits return `deferred` |
| Default policy | `async \| deferred` | Chosen by the implementation; libc++ always picks `async` |

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[future.syn] `<future>` declares `future_errc` (`broken_promise`, `future_already_retrieved`, `promise_already_satisfied`, `no_state`), the bitmask type `launch` (`async`, `deferred` and implementation-defined bits), `future_status` (`ready`, `timeout`, `deferred`), and the class templates and `async` covered on this page. ¶1 Note 1 allows implementations to provide additional `launch` bits. ¶2 The enumerators of `future_errc` are distinct and nonzero, because zero means "no error" in `error_code`.

[futures.errors] ¶1–¶2 `future_category()` returns a reference to an object of a class derived from `error_category`, whose `name()` returns `"future"`. ¶3–¶4 `make_error_code` and `make_error_condition` use it to construct an `error_code` and an `error_condition`.

[futures.future.error] `future_error` derives from `logic_error`. ¶1 The constructor initializes the internal `error_code` with `make_error_code(e)`, ¶2 `code()` returns it, and ¶3 `what()` returns a string that contains `code().message()`.

[futures.task.nonmembers] ¶1 and [futures.promise] ¶30 are the non-member `swap`s.

</details>
