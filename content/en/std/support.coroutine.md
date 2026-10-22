---
title: Coroutine support
summary: "The header <coroutine> is the library part that the language rules for coroutines depend on: the compiler finds the promise type through coroutine_traits and resumes and destroys coroutines through coroutine_handle; plus the noop coroutine for symmetric transfer, and suspend_always and suspend_never."
updated: 2026-10-19
---

!!! tldr
    - The compiler finds a coroutine's promise type through `std::coroutine_traits<R, ParamTypes...>::promise_type`, which by default is the `R::promise_type` nested in the return type.
    - `std::coroutine_handle` is a non-owning pointer to a coroutine: copying it doesn't copy the coroutine, destroying it doesn't destroy the coroutine, and the coroutine frame is released only by `destroy()` or when the coroutine itself finishes.
    - `resume()` requires the coroutine to be suspended and not at its final suspend point, and `destroy()` and `done()` require it to be suspended; violations are undefined behavior.
    - Resuming a coroutine on a different thread is guaranteed among `std::thread`, `std::jthread` and the main thread; on other execution agents it is implementation-defined.
    - `noop_coroutine()` returns a handle that does nothing when resumed, for symmetric transfer when there is no next coroutine to resume.

## The language depends on this header

The language rules for C++20 coroutines ([[dcl.fct.def.coroutine]], [[expr.await]], [[expr.yield]]) specify a transformation: if `co_await`, `co_yield` or `co_return` appears in a function body, the function is a **coroutine**, and the compiler rewrites its body into a series of calls on a **promise object**. The promise object lives in the **coroutine frame**, the storage the compiler allocates for the coroutine to hold its local variables and suspension point.

The core language hands two things over to `<coroutine>`:

- What type the promise is. Starting from the coroutine's return type and parameter types, the compiler finds it through `std::coroutine_traits`.
- How to resume a suspended coroutine from outside. The compiler passes a handle to the coroutine frame, as a `std::coroutine_handle`, to the awaiter's `await_suspend`, and users resume and destroy the coroutine and access the promise through it.

So `<coroutine>` must be included before defining a coroutine; otherwise these names can't be found and the program is ill-formed:

```cpp error
struct R { struct promise_type; };
R f() { co_return; }   // error: <coroutine> not included
```

Clang 23's diagnostic is `std::coroutine_traits type was not found; include <coroutine> before defining a coroutine`. The core language rarely depends on the library; the other places are `<initializer_list>`, `<compare>` and `<typeinfo>`.

¶1 [support.coroutine.general] `<coroutine>` defines several types providing compile-time and run-time support for coroutines. The whole header is freestanding, and it includes `<compare>`, because `coroutine_handle`'s `<=>` returns `strong_ordering`.

## Finding the promise type [coroutine.traits]

For a coroutine with return type `R` and parameter types `P1, ..., Pn`, the promise type is `std::coroutine_traits<R, P1, ..., Pn>::promise_type` ([[dcl.fct.def.coroutine#3]]). If the coroutine is a non-static member function, the type of the object parameter is prepended to the parameter type list, for example `C&` for an implicit object member function.

[coroutine.traits.primary] ¶1 specifies the primary template: if `R::promise_type` is a valid type name, `coroutine_traits<R, ArgTypes...>` has a public member

```cpp
using promise_type = R::promise_type;
```

otherwise it has no members, and the coroutine definition is ill-formed. "Valid" here is judged in the sense of template argument deduction ([[temp.deduct]]), so an `R` without `promise_type` doesn't cause a hard error. This is why `promise_type` is usually nested in the return type (`Task`, `Generator`).

¶2 Programs may also specialize `coroutine_traits`, and the specialization must have a public nested type `promise_type`. This is the way to go when the return type isn't a class you can modify, such as `void`. By [[namespace.std]], a specialization of a standard library template must depend on at least one program-defined type, which can be satisfied through a parameter type:

```cpp run title="coroutine-traits.cpp" ok
#include <coroutine>
#include <cstdio>
#include <exception>

struct Detached {};   // a program-defined type used as a tag parameter

template<class... Args>
struct std::coroutine_traits<void, Detached, Args...> {
  struct promise_type {
    void get_return_object() {}
    std::suspend_never initial_suspend() noexcept { return {}; }
    std::suspend_never final_suspend() noexcept { return {}; }
    void return_void() {}
    void unhandled_exception() { std::terminate(); }
  };
};

void task(Detached, int x) {   // a coroutine returning void
  std::printf("running %d\n", x);
  co_return;
}

int main() { task(Detached{}, 42); }
```

`final_suspend` returns `suspend_never`, so the frame is destroyed automatically when the coroutine finishes, and there is no handle to manage.

## Coroutine handles [coroutine.handle]

### A generator

```cpp run title="generator.cpp" ok
#include <coroutine>
#include <exception>
#include <utility>

template<class T>
class Generator {
public:
  struct promise_type {
    T current;
    Generator get_return_object() {
      return Generator{
        std::coroutine_handle<promise_type>::from_promise(*this)};
    }
    // suspend right after creation: lazy
    std::suspend_always initial_suspend() noexcept { return {}; }
    // suspend at the end: the frame is destroyed by Generator
    std::suspend_always final_suspend() noexcept { return {}; }
    std::suspend_always yield_value(T v) {
      current = std::move(v);
      return {};
    }
    void return_void() {}
    void unhandled_exception() { std::terminate(); }
  };

  explicit Generator(std::coroutine_handle<promise_type> h) : h_(h) {}
  Generator(Generator&& o) noexcept : h_(std::exchange(o.h_, {})) {}
  ~Generator() { if (h_) h_.destroy(); }  // requires: suspended

  bool next() {
    h_.resume();         // requires: suspended and not at the final suspend point
    return !h_.done();   // whether it stopped at the final suspend point
  }
  const T& value() const { return h_.promise().current; }

private:
  std::coroutine_handle<promise_type> h_;
};

Generator<int> iota(int n) {
  for (int i = 0; i < n; ++i) co_yield i;
}

int main() {
  auto g = iota(4);
  int sum = 0;
  while (g.next()) sum += g.value();   // 0 + 1 + 2 + 3
  return sum == 6 ? 0 : 1;
}
```

`get_return_object` gets a handle from the promise with `from_promise` and gives it to the return object `Generator` to keep. `Generator` then uses the handle to resume the coroutine (`resume`), check whether it has finished (`done`), read the value in the promise (`promise`), and finally destroy the coroutine in its destructor (`destroy`). The specification of each of these operations follows.

C++23's `std::generator` (`<generator>`) is a production-quality implementation, supporting recursive `co_yield` and allocators.

### Two kinds of handle

```cpp
template<class Promise = void> struct coroutine_handle;   // knows the promise type
template<> struct coroutine_handle<void>;                 // type-erased: coroutine_handle<>
```

`coroutine_handle<>` (i.e. `coroutine_handle<void>`) can refer to any coroutine but can't access the promise. `coroutine_handle<Promise>` adds `from_promise` and `promise()`, and converts implicitly to `coroutine_handle<>` ([coroutine.handle.conv]). There is no conversion in the other direction; when needed, write `coroutine_handle<P>::from_address(h.address())`, with the program responsible for the promise type being right.

Both have a single exposition-only member `void* ptr`, the address of the coroutine frame.

[coroutine.handle.general] ¶1 An object of type `coroutine_handle<T>` is called a **coroutine handle** ([[g:coroutine-handle]]) and refers to a suspended or executing coroutine. A handle whose `address()` returns a null pointer doesn't refer to any coroutine. Two handles refer to the same coroutine if and only if their `address()` return the same non-null value.

A handle doesn't own its coroutine: copying the handle doesn't copy the coroutine, and destroying the handle doesn't affect the coroutine. The coroutine frame is released only in two cases: someone calls `destroy()`, or the coroutine finishes and `final_suspend` doesn't suspend. So coroutine return types almost always manage the handle like a `unique_ptr`, as `Generator` above does.

¶2 If a program declares an explicit or partial specialization of `coroutine_handle`, the behavior is undefined. Note that this is UB, whereas the analogous rules for `initializer_list` ([[support.initlist]]) and `type_order` ([[cmp]]) make it ill-formed.

### Construction [coroutine.handle.con]

| Member | Specification |
|---|---|
| Default constructor, `coroutine_handle(nullptr_t)` | ¶1 `address() == nullptr` |
| `static from_promise(Promise& p)` | ¶2 requires `p` to be the promise object of a coroutine; ¶3–¶4 returns a handle `h` referring to that coroutine, with `addressof(h.promise()) == addressof(p)` |
| `operator=(nullptr_t)` | ¶5 `address() == nullptr` |

`from_promise` is the only way back from a promise to a handle. It can be implemented because the promise object is at a fixed position in the coroutine frame, so the implementation can get the frame's address by subtracting an offset from the promise's address. Passing an object that isn't a coroutine's promise violates the precondition, and the behavior is undefined.

### Exporting and importing addresses [coroutine.handle.export.import]

- ¶1 `address()` returns `ptr`.
- ¶2 `coroutine_handle<>::from_address(addr)` requires `addr` to have been obtained by a prior call to `address()` on an object of some specialization of `coroutine_handle`.
- ¶4 `coroutine_handle<Promise>::from_address(addr)` is stricter: `addr` must come from a `coroutine_handle<Promise>` with the same `Promise`.

This pair of functions lets handles pass through C interfaces that accept only `void*`, such as `epoll_event.data.ptr` or the `void* context` of operating system callbacks.

### Observers [coroutine.handle.observers]

¶1 `explicit operator bool()` returns `address() != nullptr`.

¶2–¶3 `done()` requires the handle to refer to a suspended coroutine; it returns `true` if the coroutine is suspended at its **final suspend point** (the suspension point when executing `co_await promise.final_suspend()`), and `false` otherwise.

So `done()` can't be used to ask whether a coroutine still exists. Calling `done()` on a null handle, a destroyed coroutine or an executing coroutine all violate the precondition.

### Resumption and destruction [coroutine.handle.resumption]

| Operation | Precondition | Effect |
|---|---|---|
| `resume()`, `operator()()` | ¶2 refers to a suspended coroutine that isn't at its final suspend point | ¶3 resumes execution of the coroutine |
| `destroy()` | ¶4 refers to a suspended coroutine, possibly at its final suspend point | ¶5 destroys the coroutine: destroys objects in scope, the promise and the parameter copies, and frees the coroutine frame ([[dcl.fct.def.coroutine]]) |

¶1 deals with resuming on a different thread:

!!! std
    Resuming a coroutine via `resume`, `operator()`, or `destroy` on an execution agent other than the one on which it was suspended has implementation-defined behavior unless each execution agent either is an instance of `std::thread` or `std::jthread`, or is the thread that executes `main`.

An **execution agent** is an entity executing a thread of control, threads being the most common kind ([[thread.req.lockable.general]]). Suspending a coroutine on one execution agent and resuming it on another is guaranteed only when both are `std::thread`, `std::jthread` or the main thread; between other execution agents, such as the work units of parallel algorithms or fibers on some platforms, it is implementation-defined.

Note 1 warns that a coroutine resumed on another execution agent should avoid relying on consistent thread identity, for example holding a mutex across a suspension point, since a `std::mutex` must be unlocked by the thread that locked it. The same reasoning applies to `thread_local` variables. Note 2 warns that concurrently resuming the same coroutine may cause a data race.

### Accessing the promise [coroutine.handle.promise]

¶1–¶2 `promise()` requires the handle to refer to a coroutine and returns a reference to its promise. It doesn't require the coroutine to be suspended; the promise can be accessed through the handle while the coroutine is executing.

### Comparison and hashing [coroutine.handle.compare] [coroutine.handle.hash]

¶1 `==` compares `address()`. ¶2 `<=>` returns `compare_three_way()(x.address(), y.address())`. `compare_three_way` is used rather than the built-in `<` because it gives a total order even for unrelated pointers ([[comparisons.three.way]]). Both operators take `coroutine_handle<>` parameters, so any `coroutine_handle<P>` can use them through implicit conversion.

`hash<coroutine_handle<P>>` is enabled ([[unord.hash]]), so handles can go directly into an `unordered_set`.

!!! impl "The Clang and libc++ implementation"
    libc++'s `coroutine_handle` is a thin wrapper around Clang built-ins: `resume()` calls `__builtin_coro_resume`, `destroy()` calls `__builtin_coro_destroy`, `done()` calls `__builtin_coro_done`, and `promise()` and `from_promise()` call `__builtin_coro_promise`, converting between the frame address and the promise address using the promise's alignment. In Clang's implementation, a coroutine frame starts with two function pointers, resume and destroy, and `resume()` is just an indirect call through the function pointer in the frame. That is how `coroutine_handle<>` can resume any coroutine without knowing the promise type.

## The noop coroutine and symmetric transfer [coroutine.noop]

### Symmetric transfer needs an empty target

`await_suspend` can return a `coroutine_handle<>`, meaning: suspend the current coroutine and immediately resume the returned one ([[expr.await]]). This is called **symmetric transfer**. The compiler implements it as a tail call, so a long chain of `co_await`s resuming one another doesn't keep deepening the stack.

But sometimes there is no next coroutine to resume, for example when a task finishes and nobody is waiting for it. Then `await_suspend` needs to return a handle that does nothing, and that is `noop_coroutine()`:

```cpp run title="symmetric-transfer.cpp" ok
#include <coroutine>
#include <exception>
#include <utility>

struct Task {
  struct promise_type {
    int value = 0;
    std::coroutine_handle<> continuation;   // the coroutine awaiting this task
    Task get_return_object() {
      return Task{
        std::coroutine_handle<promise_type>::from_promise(*this)};
    }
    std::suspend_always initial_suspend() noexcept { return {}; }
    struct FinalAwaiter {
      bool await_ready() noexcept { return false; }
      std::coroutine_handle<>
      await_suspend(std::coroutine_handle<promise_type> h) noexcept {
        auto c = h.promise().continuation;
        // resume the awaiter if there is one; otherwise transfer to the noop coroutine,
        // and control returns to the caller of resume()
        return c ? c : std::noop_coroutine();
      }
      void await_resume() noexcept {}
    };
    FinalAwaiter final_suspend() noexcept { return {}; }
    void return_value(int v) { value = v; }
    void unhandled_exception() { std::terminate(); }
  };

  bool await_ready() { return false; }
  std::coroutine_handle<> await_suspend(std::coroutine_handle<> awaiting) {
    h_.promise().continuation = awaiting;
    return h_;   // symmetric transfer: resume the awaited task directly
  }
  int await_resume() { return h_.promise().value; }

  explicit Task(std::coroutine_handle<promise_type> h) : h_(h) {}
  Task(Task&& o) noexcept : h_(std::exchange(o.h_, {})) {}
  ~Task() { if (h_) h_.destroy(); }
  std::coroutine_handle<promise_type> h_;
};

Task leaf() { co_return 20; }
Task root() {
  int a = co_await leaf();
  int b = co_await leaf();
  co_return a + b + 2;
}

int main() {
  Task t = root();
  t.h_.resume();   // starts root; when everything is done, returns here via the noop coroutine
  return (t.h_.done() && t.h_.promise().value == 42) ? 0 : 1;
}
```

When `root` awaits `leaf`, `Task::await_suspend` records the awaiter and returns `leaf`'s handle, transferring directly into `leaf`. When `leaf` finishes, `FinalAwaiter` returns the handle of the awaiter `root`, transferring back to `root`. When `root` itself finishes there is no awaiter, so it returns `noop_coroutine()`, and control returns to the `resume()` call in `main`.

### Specification of the noop coroutine

[coroutine.promise.noop] ¶1 `noop_coroutine_promise` is an empty struct used as the promise type of noop coroutines. `coroutine_handle<noop_coroutine_promise>` (alias `noop_coroutine_handle`) is an explicit specialization whose members differ from the general version in several ways:

| Member | Specification in the noop version |
|---|---|
| `explicit operator bool()` | Always `true` |
| `done()` | Always `false`, `constexpr noexcept`, no precondition |
| `resume()`, `operator()()`, `destroy()` | No effect, `constexpr noexcept`; calling them after converting to `coroutine_handle<>` likewise has no observable effect |
| `promise()` | Returns the promise object associated with this handle |
| `address()` | Returns `ptr`, which is always non-null |
| Constructor | Private; obtainable only through `noop_coroutine()` |

[coroutine.noop.coroutine] ¶1 `noop_coroutine()` returns a handle to a coroutine that has no observable effects when resumed or destroyed. ¶2 Handles returned by two calls may or may not compare equal.

!!! impl
    Clang provides the built-in `__builtin_coro_noop()`, which returns a static coroutine frame whose resume and destroy functions are both empty, and libc++ uses it to construct `noop_coroutine_handle`. GCC has no such built-in, so under GCC libc++ constructs a static fake frame itself. The frame is static, so `address()` is never null.

## Trivial awaitables [coroutine.trivial.awaitables]

```cpp
struct suspend_never {
  constexpr bool await_ready() const noexcept { return true; }
  constexpr void await_suspend(coroutine_handle<>) const noexcept {}
  constexpr void await_resume() const noexcept {}
};
struct suspend_always {
  constexpr bool await_ready() const noexcept { return false; }
  constexpr void await_suspend(coroutine_handle<>) const noexcept {}
  constexpr void await_resume() const noexcept {}
};
```

The note in ¶1 says they make a `co_await` never suspend and always suspend respectively, and neither produces a value. Their most common use is as the return values of `initial_suspend()` and `final_suspend()`:

| | Returns `suspend_always` | Returns `suspend_never` |
|---|---|---|
| `initial_suspend()` | Lazy: suspended after creation, starts running on the first `resume()` | Eager: runs immediately after creation |
| `final_suspend()` | Stops at the final suspend point after finishing; the holder of the handle is responsible for `destroy()` | The frame is destroyed automatically at the end, and all handles dangle afterwards |

[[dcl.fct.def.coroutine#15]] requires `co_await promise.final_suspend()` not to be potentially-throwing. That is why the members of these two types are all `noexcept`, and a custom final awaiter must be entirely `noexcept` as well.

!!! history
    Coroutines were first published as a Technical Specification (the Coroutines TS), and [[P0912R5]] merged them into C++20. Symmetric transfer and `noop_coroutine` were added by [[P0913R1]], solving the problem in the early design that every `co_await` resuming another coroutine took up one more stack frame.

## Common mistakes

!!! pitfall "Calling `resume()` on a coroutine that has finished"
    Once a coroutine stops at its final suspend point, the precondition of `resume()` no longer holds, and calling it is UB. A generator must check with `done()` before resuming, or check after resuming as `Generator::next` above does.

!!! pitfall "`final_suspend` doesn't suspend, and `destroy()` is called afterwards"
    When `final_suspend` returns `suspend_never`, the frame is released automatically when the coroutine finishes, and the handle dangles. If the return object's destructor then calls `destroy()`, the same frame is freed twice.

!!! pitfall "Using the awaiter after `await_suspend` hands off the handle"
    Before `await_suspend` is called, the coroutine is already considered suspended ([[expr.await#5.1]]), so after `await_suspend` hands the handle to another thread, that thread may `resume()` it immediately. But once the coroutine resumes elsewhere, the awaiter object and the local variables in the coroutine frame may be modified or destroyed; if `await_suspend` touches them after handing off the handle, it races with the other thread or even accesses destroyed objects. Handing off the handle should be the last thing `await_suspend` does.
