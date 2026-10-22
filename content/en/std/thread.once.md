---
title: Call once
summary: "How once_flag and call_once guarantee that a piece of initialization succeeds exactly once: attempts that throw do not count, the synchronization between attempts, every caller seeing the result of the initialization, and the trade-off against function-local static variables."
updated: 2026-10-19
---

!!! tldr
    - `std::call_once(flag, f)` guarantees that `f` succeeds at most once for the same `once_flag`; when several threads call it at once, the others wait for it to finish.
    - Only a normal return counts as completion. If `f` throws, the exception propagates to the caller, and the next `call_once` tries again.
    - The executions on one `once_flag` form a total order, and the successful one synchronizes with every later call that returns directly, so data written by `f` can be read without extra locking.
    - The constructor of `once_flag` is `constexpr`, so it can be constant-initialized; but construction itself does not synchronize.
    - When initializing just one variable, a function-local static variable is simpler, and its initialization is equally thread-safe.

## Initializing only once

```cpp run title="call-once-init.cpp" ok
#include <cassert>
#include <mutex>
#include <thread>
#include <vector>

struct Config { int port = 0; };
Config* cfg = nullptr;
std::once_flag cfg_once;

const Config& get_config() {
  std::call_once(cfg_once, [] { cfg = new Config{8080}; });   // only one thread runs the lambda
  return *cfg;                                                  // readable without locking
}

int main() {
  std::vector<std::jthread> ts;
  for (int i = 0; i < 8; ++i) ts.emplace_back([] { assert(get_config().port == 8080); });
}
```

Eight threads call `get_config` at the same time; the lambda runs only once, the other threads wait for it to finish before returning, and after returning all of them can see `cfg`. Hand-written check-lock-check (double-checked locking) needs atomic variables and correct memory orders to achieve this; `call_once` packages it up.

## once_flag [thread.once.onceflag]

¶1 `once_flag` is an opaque data structure that `call_once` uses to initialize data without causing a data race or deadlock. It is neither copyable nor movable.

¶3 The default constructor sets the internal state to indicate that no function has been called. This constructor is `constexpr`, so a namespace-scope `once_flag` is constant-initialized and ready before any dynamic initialization runs ([[basic.start.static]]). The thing used to guard other initialization cannot itself have an initialization order problem.

¶2 Construction of a `once_flag` is not synchronized. If a `once_flag` is a member of some dynamically created object, that object itself must first be handed safely to other threads; `call_once` does not take care of that step.

## call_once [thread.once.callonce]

```cpp
template<class Callable, class... Args>
  void call_once(once_flag& flag, Callable&& func, Args&&... args);
```

¶1 `func` must be invocable with `args...`, otherwise the program is ill-formed.

### Four kinds of execution (¶2)

¶2 The standard calls each call to `call_once` an execution and divides them into categories:

- an execution that does not call `func` is a **passive execution**;
- an execution that calls `func` is an **active execution**, which evaluates *INVOKE*`(std::forward<Callable>(func), std::forward<Args>(args)...)` ([[func.require]]);
- among active executions, one where `func` throws is **exceptional**, and the exception propagates to the caller of `call_once`; otherwise it is **returning**.

For all the executions on the same `once_flag`, paragraph 2 makes three rules:

1. at most one is a returning execution;
2. if there is a returning execution, it is the last active execution;
3. there are passive executions only if there is a returning execution.

So "once" means "succeeds once". Exceptional executions do not count, and the next caller calls `func` again. The third rule guarantees that no call returns passively before the initialization has succeeded.

```cpp run title="call-once-retry.cpp" ok
#include <cstdio>
#include <mutex>
#include <stdexcept>

std::once_flag flag;
int attempts = 0;

void init() {
  ++attempts;
  std::printf("active execution #%d\n", attempts);
  if (attempts < 3) throw std::runtime_error("init failed");   // exceptional execution
}

int main() {
  for (int i = 0; i < 5; ++i) {
    try {
      std::call_once(flag, init);
      std::puts("returned");
    } catch (const std::exception& e) {
      std::printf("caught: %s\n", e.what());
    }
  }
}
```

The first two are exceptional executions, the third is the returning execution, and the last two are passive executions that no longer print `active execution`.

### Synchronization (¶3)

!!! std
    For any given `once_flag`: all active executions occur in a total order; completion of an active execution synchronizes with the start of the next one in this total order; and the returning execution synchronizes with the return from all passive executions.

¶3 Its three clauses guarantee three things:

1. Active executions form a total order and never run concurrently. At most one thread is executing `func` at any time, so `func` can write ordinary variables directly.
2. The completion of one active execution [[g:synchronizes-with|synchronizes with]] the start of the next. Side effects left behind by a failed attempt are visible to the next attempt, which can clean up or continue accordingly.
3. The returning execution synchronizes with the return from all passive executions. After a thread with a passive execution returns from `call_once`, reading data written by `func` is not a data race. The `return *cfg;` in `get_config` above relies on exactly this clause.

¶4 `call_once` throws `system_error` when required ([[thread.req]]), and also propagates any exception thrown by `func`.

### Binding member functions (¶5)

The standard's example in ¶5 shows three kinds of `once_flag`: global, function-local static, and class member. The last one uses *INVOKE* to call a member function:

```cpp run ok
#include <mutex>

class information {
  std::once_flag verified;
  void verifier() {}
public:
  void verify() { std::call_once(verified, &information::verifier, *this); }
};

int main() {
  information a, b;
  a.verify(); a.verify();   // a.verifier runs only once
  b.verify();               // b has its own flag
}
```

`call_once` takes its arguments by forwarding reference; `*this` is an lvalue, so what is passed is a reference, and the object is not copied.

## Comparison with function-local static variables

Since C++11, the initialization of a function-local static variable is itself thread-safe ([[stmt.dcl]]): when several threads pass the declaration for the first time simultaneously, only one performs the initialization and the others wait for it to finish; if the initialization throws, the next pass retries. This matches the semantics of `call_once`, so `get_config` is usually written as:

```cpp
const Config& get_config() {
  static const Config cfg{8080};
  return cfg;
}
```

`call_once` is still needed in these cases:

- what needs doing is an action rather than initializing a variable, such as registering a callback or initializing a third-party library;
- each object needs its own lazy one-time initialization, so the `once_flag` must be a member, while a function-local static exists only once in the whole program;
- the initialization needs arguments known only at the time of the call.

!!! impl "libc++'s implementation"
    libc++'s `once_flag` holds just an integer state: 0 means not called, 1 means in progress, all ones means complete. `call_once` first does an acquire read in the header, and returns immediately if the state is already complete, so a passive execution costs only that one read.

    Otherwise it enters `__call_once` in the library, which uses one global mutex and one global condition variable to coordinate the slow path of all `once_flag`s. The thread that changes the state to in-progress calls `func`, and other threads wait on the condition variable; if `func` throws, the state is reset to 0 and the waiters are woken. On completion, the release write of the state pairs with the acquire read on the fast path, implementing the last clause of ¶3.

## Common misconceptions

!!! pitfall "`func` can call `call_once` on the same `once_flag` again"
    The inner call sees the state as in progress and waits for the outer execution to finish, while the outer one waits for the inner call to return. The standard makes no special provision for this case, and in actual implementations it is a deadlock.

!!! pitfall "Throwing an exception counts as having been called"
    After `func` throws, the `once_flag` is still incomplete, and the next `call_once` calls again. And the next call may be with a different callable: `call_once` looks only at the flag and does not care which function is passed.

## Questions

!!! question "Question"
    Two threads call `call_once(flag, f)` and `call_once(flag, g)` respectively on the same `once_flag`, and both f and g return normally. How many times does each of f and g run?

<details markdown="1">
<summary>Answer</summary>

Exactly one of them runs once, and the other does not run. By paragraph 2, there is at most one returning execution, and after a returning execution there can only be passive executions. Once the call that becomes the active execution first returns normally, the other call is a passive execution. Which one runs first is unspecified.
</details>
