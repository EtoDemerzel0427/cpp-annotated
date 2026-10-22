---
title: Threads
summary: "std::thread and std::jthread: on which thread the arguments are copied, the two synchronization relations established by construction and join, why destroying a joinable thread calls terminate, how jthread requests stop and joins automatically, and thread::id, thread attributes and this_thread."
updated: 2026-10-19
---

!!! tldr
    - The arguments of the thread function are always copied or moved, and the copies are constructed in the thread that creates the new thread; to pass a reference, use `std::ref`.
    - Two synchronization relations: the completion of the constructor synchronizes with the start of the thread function, and the completion of the thread synchronizes with the return from `join()`. The new thread sees data written before it started, and data the thread wrote is visible after `join()`.
    - Destroying or move-assigning to a `std::thread` while it is joinable calls `std::terminate`; `std::jthread` instead requests stop and then joins.
    - If a `jthread`'s callable can be invoked with a `stop_token` as its first argument, it automatically receives a stop token.
    - `sleep_for` and `yield` provide no synchronization; the value of a `thread::id` may be reused after the thread ends.

[[intro.multithread]] says a thread can create another thread but not how. The answer is here: construct a `std::thread` or `std::jthread`. [[thread.threads.general]] Note 1 explains that these threads are intended to map one-to-one with operating system threads. So creating a thread is not cheap (system calls, stack allocation), `thread` is not copyable, and `hardware_concurrency()` refers to the number of hardware threads.

## Creating a thread [thread.thread.constr]

### Where the arguments are copied

```cpp run title="thread-ref.cpp" ok
#include <cstdio>
#include <functional>
#include <thread>

void inc(int& x) { ++x; }

int main() {
  int n = 0;
  // std::thread t0(inc, n);        // error: the copy is an rvalue and cannot bind to int&
  std::thread t1(inc, std::ref(n));  // OK: pass a reference explicitly
  t1.join();
  std::printf("%d\n", n);            // 1
}
```

`template<class... Args> explicit thread(Args&&... args)` is the constructor that creates a thread. ¶3 requires `Args` to be non-empty and the first argument, with references and cv-qualifiers removed, not to be `thread`; otherwise it would take the place of the move constructor.

¶4 After C++23, a few thread attributes may come at the front of the argument list (see below). The constructor takes the first argument whose decayed type is not a thread attribute type as the callable `f`; those before it are attributes, and those after it are the arguments `fargs` passed to `f`.

¶6 The new thread executes

```cpp
invoke(auto(std::forward<F>(f)), auto(std::forward<FArgs>(fargs))...)
```

where the values produced by `auto(...)` are materialized in the constructing thread ([[conv.rval]]), and the return value is ignored. Two things follow:

1. The arguments are always copied or moved, and the new thread uses the copies. In the example above, `inc`'s parameter is `int&`; `std::thread t0(inc, n)` passes a copy of `n`, which moreover is an rvalue and cannot bind to `int&`. The *Mandates* in ¶5 require `is_invocable_v<decay_t<F>, decay_t<FArgs>...>`, and the program is ill-formed otherwise. To pass a reference, use `std::ref`.
2. The copies are created in the constructing thread and already exist when the constructor returns, so the original arguments may then be destroyed. Note 1 points out that exceptions thrown while copying `f` and the arguments are therefore thrown from the constructor, not in the new thread. Only if `invoke` itself exits via an exception is `std::terminate` called.

Uncomment the `t0` line in the example above, and libc++ reports a `static_assert` failure in `<__thread/thread.h>`, pointing out that `__is_invocable_v<void (*)(int &), int>` does not hold.

### The first synchronization relation

!!! std
    The completion of the invocation of the constructor synchronizes with the beginning of the invocation of the copy of `f`.

¶7 The completion of the constructor invocation synchronizes with the beginning of the invocation of the copy of `f`. So every write made before creating the thread is visible to the new thread. Preparing data first and then starting a thread to process it needs no additional synchronization.

¶8 After successful construction, `get_id() != id()` and `*this` represents the new thread. ¶9–¶10 If the thread cannot be started, `system_error` is thrown with the error condition `resource_unavailable_try_again`, meaning resources are lacking or the per-process limit on threads would be exceeded.

¶1–¶2 A default-constructed `thread` represents no thread. ¶11 After move construction, `*this` takes over the thread `x` used to represent, and `x` no longer represents any thread.

### One object represents one thread [thread.thread.class.general]

¶1 A `thread` object uniquely represents a thread of execution. That representation can be transferred to another `thread` object, but at no time do two `thread` objects represent the same thread. A thread not represented by any `thread` object is called **detached**.

So `thread`, like `unique_ptr`, is movable but not copyable. Note 1 lists three cases where a `thread` represents no thread: after default construction, after being moved from, and after a successful call to `detach()` or `join()`.

## Waiting for a thread to finish [thread.thread.member]

### join and the second synchronization relation

¶3 `join()` blocks until the thread represented by `*this` has completed. ¶4 The completion of that thread synchronizes with the corresponding successful return from `join()`. All the side effects of the thread, including the destruction of `thread_local` objects, are visible after `join()`.

Note 1 adds that operations on `*this` itself are not synchronized: two threads calling `join()` on the same `thread` object at the same time is a data race.

¶5 After return, `get_id() == id()`. ¶6–¶7 list three error conditions: `resource_deadlock_would_occur` (a deadlock is detected, or a thread joins itself), `no_such_process` (the thread is not valid), and `invalid_argument` (not joinable). ¶2 `joinable()` is just `get_id() != id()`.

### detach

¶8 `detach()` lets the thread keep running without blocking the caller; `*this` no longer represents the thread, and the implementation releases its resources when it finishes. A detached thread has no join synchronization; to read data it wrote, you need some other synchronization, such as an atomic variable, a `promise`, or `notify_all_at_thread_exit`.

```cpp title="detach-dangling.cpp" ub
#include <thread>
void start() {
  int local = 0;
  std::thread([&local] { ++local; }).detach();   // UB: the thread may access local after start returns and it is destroyed
}
int main() { start(); }
```

!!! pitfall "Detached threads and program exit"
    After `main` returns, objects with static storage duration begin to be destroyed ([[basic.start.term]]). If a detached thread that is still running accesses such objects, including `std::cout`, global containers and singletons, the behavior is undefined.

¶12 `get_id()` returns a default-constructed `id` if no thread is represented, otherwise the value `this_thread::get_id()` would return in that thread.

### Destruction and assignment: joinable means terminate

```cpp run title="joinable-dtor.cpp" ok
#include <thread>
int main() {
  std::thread t([] {});
}   // ~thread: t is still joinable, std::terminate is called
```

[thread.thread.destr] ¶1: on destruction, if `joinable()`, `std::terminate` is called; otherwise nothing happens. This program's behavior is defined; the result is simply termination, and in our tests it prints `libc++abi: terminating`.

Note 1 explains why the destructor neither joins nor detaches automatically. Detaching automatically would bring correctness problems that are hard to debug: the thread might still be accessing local variables that have been destroyed. Joining automatically would bring performance problems that are hard to debug: unexpected blocking during stack unwinding. And both problems would surface only when an exception is thrown. So the standard requires the programmer to deal with it explicitly before destruction.

[thread.thread.assign] ¶1: move assignment likewise calls `std::terminate` if `*this` is joinable; otherwise it takes over `x`'s thread and sets `x` to the default-constructed state.

!!! pitfall "An exception between construction and join"
    ```cpp
    void f() {
      std::thread t(work);
      do_something();   // if this throws, ~thread finds t joinable during unwinding and calls terminate
      t.join();
    }
    ```
    This is the most common misuse of `std::thread`. Since C++20, use `std::jthread` instead.

## jthread {{c++20}}

[thread.jthread.class.general] ¶1: `jthread` has the same functionality as `thread`, plus the ability to provide a stop token ([[thread.stoptoken]]) to the new thread, to issue stop requests, and to join automatically on destruction. The class has an exposition-only member `stop_source ssource`.

### On destruction, request stop and then join [thread.jthread.cons]

```cpp run title="jthread-stop.cpp" ok
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <deque>
#include <mutex>
#include <thread>

std::mutex m;
std::condition_variable_any cv;
std::deque<int> q;

int main() {
  std::jthread worker([](std::stop_token st) {
    std::unique_lock lk(m);
    while (true) {
      // returns when there is work or stop is requested; returns the final value of the predicate
      if (!cv.wait(lk, st, [] { return !q.empty(); }))
        break;                      // stop requested and the queue is empty
      int x = q.front(); q.pop_front();
      lk.unlock();
      std::printf("got %d\n", x);
      lk.lock();
    }
    std::puts("worker: stop requested");
  });
  {
    std::lock_guard lk(m);
    q.push_back(1);
  }
  cv.notify_one();
  std::this_thread::sleep_for(std::chrono::milliseconds(50));
}   // ~jthread: request_stop() wakes cv.wait, then join()
```

¶12 On destruction, if `joinable()`, it first calls `request_stop()` and then `join()`. The order matters: the thread function checks the stop token in its loop, the stop request makes it leave the loop, and only then does `join()` not wait forever. A thread function that does not check its token makes `~jthread` wait until it finishes on its own.

In the example above, the interruptible wait of `condition_variable_any` is woken by the stop request ([[thread.condition]]). With `std::condition_variable`, which has no `wait` taking a `stop_token`, the thread would sleep on the condition variable forever.

¶13 Move assignment is the same: if `*this` is joinable, it requests stop and joins first, then takes over `x`'s state. If `&x == this`, it does nothing. This differs from `thread`'s move assignment, which terminates directly.

### Passing the stop token automatically [thread.jthread.cons]

¶6 The `jthread` constructor initializes `ssource` first. If

```cpp
invoke(auto(std::forward<F>(f)), get_stop_token(), auto(std::forward<FArgs>(fargs))...)
```

is well-formed, the new thread executes it; otherwise it executes the version without the stop token. So when the callable can be invoked with a `stop_token` as its first argument, it receives the token automatically. ¶5 correspondingly relaxes the invocability requirement so that either of the two invocations being valid suffices. ¶7's synchronization rule is the same as for `thread`.

!!! lawyer "If it is well-formed, it takes the first argument"
    ¶6 looks only at whether the call with the token is well-formed, not at your intent. A generic callable can easily make it well-formed by accident:

    ```cpp run title="jthread-generic.cpp" ok
    #include <cstdio>
    #include <stop_token>
    #include <thread>
    #include <type_traits>
    int main() {
      auto f = [](auto x, int y = 0) {
        std::printf("x is stop_token: %d, y = %d\n",
                    (int)std::is_same_v<decltype(x), std::stop_token>, y);
      };
      std::jthread t(f, 42);   // prints "x is stop_token: 1, y = 42"
    }
    ```

    `invoke(f, stop_token, 42)` is well-formed, with `x` deduced as `stop_token` and `y` taking 42, so that is what gets selected.

¶8 After construction, `ssource.stop_possible()` is `true`. Note 3 points out that the calling thread can make a stop request only once, because it cannot replace this stop token. ¶1–¶2 A default-constructed `jthread` allocates no stop state, and `ssource.stop_possible()` is `false`. ¶11 After move construction, `x`'s stop source becomes disengaged.

### Other members

`swap`, `joinable`, `join`, `detach` and `get_id` in [thread.jthread.mem] are the same as for `thread`, including `join`'s synchronization rule and error conditions. [thread.jthread.stop] provides `get_stop_source()` (returns a copy of `ssource`; whoever receives it can request stop too), `get_stop_token()` and `request_stop()`. After `detach()`, the `jthread` still holds `ssource`, so a stop request can still be issued to the detached thread.

## thread::id [thread.thread.id]

```cpp run title="thread-id.cpp" ok
#include <format>
#include <iostream>
#include <thread>
#include <type_traits>

int main() {
  static_assert(std::is_trivially_copyable_v<std::thread::id>);
  std::cout << std::format("[{:>20}]\n", std::this_thread::get_id());
  std::cout << std::format("[{}]\n", std::thread::id{});   // the value that represents no thread
}
```

In our tests, the first line with libc++ prints an integer converted from the `pthread_t`, right-aligned to 20 columns; the second prints `[0]`. The exact text is unspecified; do not parse it.

¶1 `thread::id` provides a unique identifier for each thread of execution, and all `thread` objects that represent no thread share another distinct value. ¶2 The text representation of an id is an unspecified character sequence, guaranteed only to be the same for equal ids and different for unequal ones.

¶3 `thread::id` is a trivially copyable class. The library may reuse the id value of a thread that has terminated and can no longer be joined. So when using `thread::id` as a key to record what each thread did, after an old thread ends its id may be taken by a new thread.

¶5–¶8 A default-constructed id represents no thread; `==` tests whether both represent the same thread or both represent no thread; `<=>` is based on an unspecified total order and returns `strong_ordering`, and Note 1 points out that this lets `thread::id` be used as an associative container key. ¶9–¶14 also provide `operator<<`, a `formatter` (accepting only fill, alignment and width, with right alignment by default) and `hash`.

## Thread attributes [thread.attributes]

```cpp
std::jthread t(std::thread::name_hint("io-worker"),
               std::thread::stack_size_hint(1 << 20),
               worker_fn, arg1, arg2);
```

This feature was added to the draft after C++23 ([[P2019R8]]). [thread.attributes.general] ¶1–¶3: **thread attributes** can define additional, implementation-defined behavior for a `thread` or `jthread`; the thread attribute types include `thread::name_hint`, `thread::stack_size_hint` and other implementation-defined types; passing an attribute object to the constructor may affect the new thread's behavior. They are all only hints. Attributes are written before the callable.

`name_hint<T>` requires `T` to be `char`, stores a `basic_string_view<T>`, and is neither copyable nor movable. [thread.attributes.hint] ¶1 explains that it is for setting a thread's name for debugging or platform display purposes; the *recommended practice* is not to store the name in the `thread` object, so as not to increase `sizeof(thread)`.

`stack_size_hint` stores a `size_t` representing the desired number of bytes of platform-specific storage the thread needs; Note 1 says this is typically the stack where automatic variables live ([thread.attributes.size] ¶1). The implementation may adjust it up or down to meet platform requirements (¶2), and ignores it if the value is zero (¶3).

!!! impl "Not yet implemented in libc++"
    In the libc++ shipped with Clang 23, `std::thread` has no `name_hint` or `stack_size_hint` members, and the snippet above has not been verified by compiling. Currently on macOS, a thread name can only be set by calling `pthread_setname_np` from inside the thread.

## this_thread and other functions [thread.thread.this]

- ¶1 `get_id()` returns an id that uniquely identifies the current thread; repeated calls in the same thread return the same value, which is not equal to a default-constructed id.
- ¶2–¶3 `yield()` offers the implementation an opportunity to reschedule. *Synchronization*: None.
- ¶4–¶6 `sleep_until(abs_time)` blocks until the absolute timeout ([[thread.req]]). *Synchronization*: None. It may throw timeout-related exceptions.
- ¶7–¶9 `sleep_for(rel_time)` blocks for a relative timeout, likewise without synchronization.

The three *Synchronization*: None rule out reasoning like "sleep a bit and the other thread will have finished writing". `yield()` is not a synchronization primitive either; it does not even guarantee giving up the CPU. When spin-waiting, the loop condition itself must be an atomic read.

[thread.thread.static] ¶1 `hardware_concurrency()` returns the number of hardware thread contexts. Note 1 says it is only a hint and the implementation should return 0 if the value cannot be computed, so the common idiom is `std::max(1u, std::thread::hardware_concurrency())`.

## The implementation's view

!!! impl "libc++ on macOS"
    - `sizeof(std::thread)` is 8, just a `pthread_t`; `sizeof(std::jthread)` is 16, with an extra `stop_source`.
    - The `std::thread` constructor packs a `unique_ptr<__thread_struct>` (thread-local bookkeeping data) together with copies of `f` and the arguments into a heap-allocated `tuple`, and hands the pointer to `pthread_create`. The new thread's entry point `__thread_proxy` retrieves the `tuple` and invokes it. The materialization in the constructing thread that ¶6 speaks of happens when this `tuple` is constructed.
    - In our tests (12-core Apple Silicon), `hardware_concurrency()` returns 12.

## History and evolution

!!! history "From thread to jthread"
    - C++11 introduced `std::thread`; the rule that destroying a joinable thread terminates was there from the start.
    - C++20's [[P0660R10]] introduced `jthread` and stop tokens, settling on cooperative cancellation plus automatic join.
    - Argument copying used to be described with the exposition-only *decay-copy*; the current draft uses `auto(...)` plus materialization in the constructing thread, with the same meaning.
    - After C++23, thread attributes entered the draft, and the constructor's specification changed to first find the first non-attribute argument.

## Questions

!!! question "1. Does the following program have a data race?"
    ```cpp
    int x = 0;
    int main() {
      x = 1;
      std::thread t([] { x = 2; });
      t.join();
      return x;
    }
    ```

<details markdown="1">
<summary>Answer</summary>

No; it returns 2. `x = 1` is sequenced before the completion of the constructor, and the completion of the constructor synchronizes with the start of the lambda ([thread.thread.constr] ¶7), so `x = 1` happens before `x = 2`. The completion of the thread synchronizes with the return from `join()` ([thread.thread.member] ¶4), so `x = 2` happens before `return x`. All three accesses are ordered by happens before.
</details>

!!! question "2. In `std::thread t(f, std::string("abc"));`, on which thread does the move of the `std::string` happen? Where is the exception thrown if memory runs out?"

<details markdown="1">
<summary>Answer</summary>

Per [thread.thread.constr] ¶6, the values produced by `auto(std::forward<FArgs>(fargs))` are materialized in the constructing thread, so the move construction happens in the thread that calls the constructor. Any exception, including `bad_alloc` when allocating memory to hold the copies, is thrown from the constructor, and the new thread never starts. Only exceptions thrown while `f` runs happen in the new thread, and they lead to `terminate`.
</details>

## Summary

| | `thread` | `jthread` |
|---|---|---|
| destroyed while joinable | `std::terminate` | `request_stop()` then `join()` |
| move-assigned to while joinable | `std::terminate` | `request_stop()` then `join()` |
| stop token | none | passed automatically if the callable accepts a `stop_token` as its first argument |
| synchronization | constructor completion → thread function start; thread completion → `join()` returns | same |
| arguments | copied or moved in the constructing thread; use `std::ref` to pass references | same |
