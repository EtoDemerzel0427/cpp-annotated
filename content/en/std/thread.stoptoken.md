---
title: Stop tokens
summary: "The standard library's cooperative cancellation: stop_source issues stop requests, stop_token lets the code being cancelled query them, and stop_callback runs when a request arrives; which thread runs a callback, when destruction blocks, what synchronization is established, and C++26's never_stop_token and inplace_stop_* family."
updated: 2026-10-19
---

!!! tldr
    - Cancellation is cooperative: a stop request just sets a flag, and the code being cancelled must query its `stop_token` or register a `stop_callback` itself.
    - Callbacks run on the first stop request, synchronously on the thread calling `request_stop()`; if stop was already requested at registration, the callback runs immediately on the thread constructing the `stop_callback`.
    - When a `stop_callback` is destroyed while its callback is running on another thread, the destructor waits for it to return; a callback that destroys itself is not waited for.
    - A `request_stop()` that returns `true` synchronizes with a query that sees `stop_requested() == true`, so data written before the request is visible to the thread that observes it.
    - `stop_token` shares ownership of the stop state and can outlive the `stop_source`; C++26's `inplace_stop_token` does not own the state and cannot outlive its stop source.

## Three roles [thread.stoptoken.intro]

```cpp run title="cancel.cpp" ok
#include <chrono>
#include <cstdio>
#include <stop_token>
#include <thread>
using namespace std::chrono_literals;

void work(std::stop_token st) {
  int n = 0;
  while (!st.stop_requested()) {     // polling
    ++n;
    std::this_thread::sleep_for(1ms);
  }
  std::printf("stopped after %s\n", n > 0 ? "some work" : "no work");
}

int main() {
  std::stop_source src;
  std::stop_callback cb(src.get_token(), [] { std::puts("callback"); });
  std::thread t(work, src.get_token());
  std::this_thread::sleep_for(20ms);
  src.request_stop();                 // runs cb first, then returns
  t.join();
}
```

Before C++20, the usual way to make another thread stop was to write your own `atomic<bool>` flag. [thread.stoptoken] standardizes this pattern as three classes:

- `stop_source` issues a **stop request** ([[g:stop-request]]). The typical reason for a stop request is that the result of an operation is no longer needed (¶1).
- `stop_token` is handed to the code being cancelled, which polls it to see whether someone has requested a stop.
- `stop_callback` registers a function to run when a stop request arrives, commonly used to wake up a blocked wait.

¶3 They are connected through a shared **stop state** ([[g:stop-state]]); objects referring to the same stop state are called **associated** (¶2). A request made through a stop source is visible to all associated tokens and sources. Once made, a request cannot be withdrawn, and later requests have no effect.

This is cooperative cancellation. No mechanism forcibly terminates a thread; the code being cancelled must check its token or register a callback itself.

!!! pitfall "A stop request does not make blocking calls return on its own"
    A thread blocked in `std::condition_variable::wait`, a `read()` system call or `future::get()` is not woken by a stop request. The only native stop-token support in the standard library is the interruptible waits of `condition_variable_any` ([[thread.condition]]). In other cases, register a `stop_callback` yourself and close the socket or `notify_all` in the callback.

## Where callbacks run [stoptoken.concepts]

```cpp run title="callback-thread.cpp" ok
#include <cstdio>
#include <stop_token>
#include <thread>

int main() {
  std::stop_source src;
  auto main_id = std::this_thread::get_id();

  // 1. register first, request later: the callback runs on the thread calling request_stop
  std::stop_callback cb1(src.get_token(), [&] {
    std::puts(std::this_thread::get_id() == main_id ? "cb1: main" : "cb1: worker");
  });
  std::thread t([&] { src.request_stop(); });
  t.join();

  // 2. stop already requested, then register: the callback runs immediately on the constructing thread
  std::stop_callback cb2(src.get_token(), [&] {
    std::puts(std::this_thread::get_id() == main_id ? "cb2: main" : "cb2: worker");
  });
  std::printf("second request_stop returns %d\n", src.request_stop());
}
```

In our tests the output is `cb1: worker`, `cb2: main`, `second request_stop returns 0`.

### Registration (¶3.2)

Since C++26 these rules are written in the exposition-only concept *stoppable-callback-for* in [stoptoken.concepts], which both `stop_callback` and `inplace_stop_callback` must satisfy. Let the callback object `scb` be constructed with token `t` and initializer `init`, and `callback_fn` be the function object it stores. ¶3.2 specifies that construction performs a **stoppable callback registration**:

- ¶3.2.1 If `t.stop_possible()` is `true`, `callback_fn` is first direct-initialized with `init`. The constructor may throw only exceptions thrown by that initialization; the registration itself cannot fail (¶3.2.1.2).
- ¶3.2.1.3.1 If no stop has been requested at registration, the call `std::forward<CallbackFn>(callback_fn)()` is added to the stop state's list of callbacks, to be run when stop is requested.
- ¶3.2.1.3.2 Otherwise it is invoked immediately on the thread executing the constructor and not added to the list.
- Note 1: if `t.stop_possible()` is `false`, there is no requirement that `callback_fn` be initialized.

[[thread.stoptoken.intro#4]] specifies that callbacks are invoked only when a stop request is first made by any associated stop source. ¶12 specifies that the `request_stop()` that makes the request synchronously invokes all the callbacks in the list on its own thread before returning. Note 2 says the order of these invocations is not constrained. Putting it together:

| Situation | Where the callback runs |
|---|---|
| no stop requested yet at registration | the thread that later first calls `request_stop()`, inside `request_stop()` |
| stop already requested at registration | the thread constructing the `stop_callback`, inside the constructor |
| `t.stop_possible()` is `false` | never |

The callback is invoked as `std::forward<CallbackFn>(callback_fn)()`. When `CallbackFn` is not a reference type, the callback is invoked as an rvalue, so a function object providing only `operator() &&` works too.

!!! pitfall "A callback that throws terminates the program"
    ¶12 specifies that if a callback exits via an exception inside `request_stop`, `std::terminate` is called, because `request_stop` is `noexcept`. The immediate-invocation case at registration is not specified separately, but ¶3.2.1.2 allows the constructor to throw only exceptions from initializing `callback_fn`. libc++ wraps the callback invocation in a `noexcept` function, so both cases end in `std::terminate`.

### Deregistration (¶3.3)

¶3.3 Destroying `scb` performs a **stoppable callback deregistration**, in order:

- ¶3.3.1 if no callback was registered at construction, there is no effect other than destroying `callback_fn` if it was constructed;
- ¶3.3.2 otherwise the callback is removed from the stop state;
- ¶3.3.3 if `callback_fn` is concurrently executing on another thread, deregistration blocks ([[defns.block]]) until that invocation returns, so that the return from the callback strongly happens before the destruction of `callback_fn`;
- ¶3.3.4 if `callback_fn` is executing on the current thread, i.e. the callback destroys its own `stop_callback`, the destructor shall not wait for the callback to return, or it would be waiting on itself;
- ¶3.3.5 deregistration shall not wait for the completion of other callbacks registered on the same stop state;
- ¶3.3.6 finally `callback_fn` is destroyed.

¶3.3.3 is what makes `stop_callback` safe to use: once the destructor returns, everything the callback refers to may be destroyed.

```cpp run title="deregister-blocks.cpp" ok
#include <atomic>
#include <chrono>
#include <cstdio>
#include <functional>
#include <optional>
#include <stop_token>
#include <thread>
using namespace std::chrono_literals;

int main() {
  std::stop_source src;
  std::atomic<bool> entered{false};
  std::optional<std::stop_callback<std::function<void()>>> cb;
  int resource = 1;                                  // a resource the callback uses
  cb.emplace(src.get_token(), [&] {
    entered = true;
    std::this_thread::sleep_for(100ms);
    std::printf("callback uses resource = %d\n", resource);
  });
  std::jthread requester([&] { src.request_stop(); });   // the callback runs on the requester thread
  while (!entered) {}
  cb.reset();         // the callback is running on another thread: the destructor blocks until it returns
  resource = 0;       // OK: the callback's return strongly happens before the callback object's destruction
  std::puts("deregistered");
}
```

In our tests it always prints `callback uses resource = 1` before `deregistered`, and ThreadSanitizer reports no data race.

By ¶3.3.4, a callback can destroy itself from inside:

```cpp run title="self-deregister.cpp" ok
#include <cstdio>
#include <functional>
#include <optional>
#include <stop_token>

int main() {
  std::stop_source src;
  std::optional<std::stop_callback<std::function<void()>>> cb;
  cb.emplace(src.get_token(), [&] {
    std::puts("in callback");
    cb.reset();       // deregister itself from inside the callback: the destructor does not wait
    // from here on, the lambda's captures must not be accessed; they were destroyed with callback_fn
    std::puts("after self-deregistration");
  });
  src.request_stop();
}
```

!!! pitfall "Do not take locks in a callback that the requester may hold"
    A callback runs on the requesting thread, inside `request_stop()`. If thread A calls `request_stop()` while holding mutex `m`, and some callback also locks `m`, it deadlocks. Conversely, if thread B holds `m` and destroys a callback that is running on A and wants `m`, B waits for the callback to return per ¶3.3.3, the callback waits for `m`, and again it deadlocks. Keep callbacks short; usually they only call `cv.notify_all()` or set an atomic flag.

## Synchronization and atomicity (¶11–¶12)

!!! std
    A call to `request_stop` that returns `true` synchronizes with a call to `stop_requested` on an associated `stoppable_token` or *stoppable-source* object that returns `true`. Registration of a callback synchronizes with the invocation of that callback.

¶11 A `request_stop` that returns `true` synchronizes with a `stop_requested` on an associated object that returns `true`; the registration of a callback synchronizes with the invocation of that callback. In addition, concurrent calls to these member functions do not introduce data races.

The first sentence means that data the requesting thread wrote before `request_stop()`, such as the reason for cancellation, is visible to any thread that sees `stop_requested() == true`. The second means that data written before constructing the `stop_callback` and used by the callback is visible when the callback runs, even if it runs on another thread. A `request_stop` that returns `false` is not covered by the first sentence; it synchronizes nothing.

¶12 specifies the **stop request operation**: if the stop source has no stop state, `request_stop` has no effect and returns `false`. Otherwise, determining whether a request has been made and making one if not must be done atomically, as if by a read-modify-write operation ([[intro.races]]), so when several threads call `request_stop()` at once, exactly one returns `true`. The callbacks are then invoked synchronously (see above), and the return value says whether this call made the request. Note 3: a stop request also includes notifying any `condition_variable_any` temporarily registered during an interruptible wait ([[thread.condition]]).

## stop_token, stop_source, stop_callback

[[thread.stoptoken.intro#5]] specifies that these three implement shared ownership of the stop state; the last remaining owner releases it.

**stop_token** ([stoptoken]) internally holds a `shared_ptr` to the stop state; when it is empty, the token is **disengaged**. `callback_type<F>` is `stop_callback<F>`. [stoptoken.mem] ¶3 specifies that `stop_possible()` is `false` in two cases: the token is disengaged; or no stop request has ever been made and there are no associated `stop_source`s left. In the latter case nobody can ever request a stop.

```cpp run title="stop-possible.cpp" ok
#include <cassert>
#include <stop_token>

int main() {
  std::stop_token tok;
  assert(!tok.stop_possible());                 // default-constructed: disengaged
  {
    std::stop_source src;
    tok = src.get_token();
    assert(tok.stop_possible() && !tok.stop_requested());
  }                                             // last stop_source destroyed, and no stop was ever requested
  assert(!tok.stop_possible());
  {
    std::stop_source src;
    tok = src.get_token();
    src.request_stop();
  }
  assert(tok.stop_possible() && tok.stop_requested());   // stop was already requested
}
```

**stop_source** ([stopsource]) also holds a `shared_ptr`. Copying a `stop_source` gives another owner of the same stop state, not a new stop state. The default constructor allocates a new stop state and throws `bad_alloc` if allocation fails, so it is not `noexcept` ([stopsource.cons] ¶1–¶3). `stop_source(nostopstate)` constructs a disengaged stop source without allocating, suitable for a member that will be assigned later.

**stop_callback** ([stopcallback]) is neither copyable nor movable, because its address is registered in the stop state's callback list. The deduction guide `stop_callback(stop_token, CallbackFn) -> stop_callback<CallbackFn>` lets `std::stop_callback cb(tok, lambda);` omit the template argument. [stopcallback.general] ¶2 requires `CallbackFn` to model `invocable` and `destructible`. The constructor acquires shared ownership of the stop state if registration succeeds, and the destructor deregisters the callback and releases ownership ([stopcallback.cons]).

## C++26: never_stop_token and inplace_stop_* {{c++26}}

### The concept stoppable_token

C++26 abstracts the stop token interface into concepts for [[exec]] (the sender/receiver framework). `stoppable_token<Token>` in [[stoptoken.concepts#4]] requires: a member alias template `callback_type`; `stop_requested()` and `stop_possible()` that are `noexcept` and return `bool`; a non-throwing copy constructor; and the type being `copyable` and `equality_comparable`. The alias `stop_callback_for_t<T, F>` is `T::template callback_type<F>`, which generic code uses to find the callback type that goes with a token.

`unstoppable_token` additionally requires `!tok.stop_possible()` to be a constant expression with value `true`. Generic code that detects it can remove all cancellation logic at compile time.

### never_stop_token

`never_stop_token` ([[stoptoken.never#1]]) models `unstoppable_token`: both queries are `static constexpr` functions returning `false`, and its `callback_type` is a type that does nothing, discarding the initializer at construction.

### The inplace_stop_source family

[[thread.stoptoken.intro#6]] specifies that an `inplace_stop_source` is the sole owner of its stop state, and `inplace_stop_token` and `inplace_stop_callback` do not participate in ownership. Note 1 explains that they are for situations where all uses of the tokens and callbacks are nested within the stop source's lifetime. In exchange, there is no reference counting and no heap allocation.

| | `stop_source` family | `inplace_stop_source` family |
|---|---|---|
| where the stop state lives | on the heap, reference-counted | inside the `inplace_stop_source` object |
| can the stop source be copied or moved | copyable | neither |
| what the token stores | a `shared_ptr` | a `const inplace_stop_source*` |
| stop source default construction | may throw `bad_alloc` | `constexpr`, `noexcept` |
| token outliving the stop source | no problem | querying afterwards is a problem, see below |

Two notes in [stoptoken.inplace.mem] explain what happens when a token outlives its stop source:

- [[stoptoken.inplace.mem#3]] Note 1: unless the call to `stop_requested()` strongly happens before the start of the associated `inplace_stop_source`'s destructor, the behavior is undefined ([[basic.life]]), because it accesses the stop source object.
- [[stoptoken.inplace.mem#5]] Note 2: `stop_possible()` only compares a pointer against null without accessing the stop source, so it only requires the call to happen before the end of the stop source's storage duration; otherwise the behavior is implementation-defined. The reason is that after the storage duration ends the pointer becomes an invalid pointer value, and any use of it other than indirection or passing it to a deallocation function is implementation-defined ([[basic.stc.general]]).

!!! impl "Not yet in libc++"
    As of the libc++ shipped with Clang 23, `<stop_token>` has no `never_stop_token`, `inplace_stop_token`, `inplace_stop_source` or `inplace_stop_callback`, nor a `stoppable_token` concept, and `__cpp_lib_senders` is not defined. The content of this section has not been verified by compiling locally.

## The implementation's view

!!! impl "libc++'s stop state (`<__stop_token/stop_state.h>`)"
    - The stop state is an intrusively reference-counted object holding two `atomic<uint32_t>`. One is the reference count; the other packs three things together: the lowest bit means stop requested, the next bit is the lock for the callback list, and the remaining bits count the `stop_source`s (needed by `stop_token::stop_possible`). In our tests `sizeof(std::stop_token)` is 8.
    - The callback list is an intrusive doubly linked list whose nodes are the `stop_callback` objects themselves, which is why `stop_callback` cannot be moved.
    - `request_stop` sets the requested bit and the lock bit together with a single `acq_rel` CAS. The release half corresponds to the first sentence of ¶11, pairing with the acquire read in `stop_requested`; the acquire half corresponds to the second sentence, letting callbacks see data written at registration.
    - The list is unlocked before each callback runs, so other threads deregistering other callbacks meanwhile need not wait (¶3.3.5). The implementation records the requesting thread. At deregistration, if the callback may be running and the current thread is not the requesting thread, it `wait`s on an `atomic<bool>` in the node, which the requesting thread sets and `notify_all`s after running the callback; that is the blocking of ¶3.3.3. If it is the same thread, it only marks the node and does not wait (¶3.3.4).

## Questions

!!! question "1. Two threads call `request_stop()` on the same `stop_source` at the same time. How many times do the callbacks run, and on which thread?"

<details markdown="1">
<summary>Answer</summary>

Each callback runs exactly once. ¶12 requires determining and making the request to be as if one atomic read-modify-write, so exactly one call returns `true`, and the callbacks run synchronously on that thread. The other call returns `false`, and may return before the callbacks have finished: a `request_stop` returning `false` neither waits for callbacks nor establishes synchronization (¶11 speaks only of calls returning `true`).
</details>

!!! question "2. Can both the constructor and the destructor of `stop_callback` block?"

<details markdown="1">
<summary>Answer</summary>

The destructor can block: per ¶3.3.3, it waits for the callback to return when the callback is running on another thread. The constructor's specification says nothing about blocking, but if stop was already requested at registration, the callback runs synchronously inside the constructor (¶3.2.1.3.2), so the constructor's running time includes the callback's.
</details>

!!! question "3. Why is calling `inplace_stop_token::stop_possible()` after the stop source is destroyed implementation-defined, while `stop_requested()` is undefined?"

<details markdown="1">
<summary>Answer</summary>

`stop_possible()` is specified to return `stop-source != nullptr` ([stoptoken.inplace.mem] ¶4); it only compares the pointer and does not access the object it points to, so the object's lifetime is irrelevant. After the storage duration ends, the pointer value becomes an invalid pointer value, and comparing it is implementation-defined ([[basic.stc.general]]). `stop_requested()`, by contrast, calls a member function of the stop source through the pointer, and accessing an object outside its lifetime is undefined behavior ([[basic.life]]).
</details>
