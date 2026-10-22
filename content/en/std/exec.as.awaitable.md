---
title: Senders and coroutines
summary: "The two bridges between senders and coroutines: awaitables are automatically treated as senders; as_awaitable turns a sender into something that can be co_awaited, and with_awaitable_senders lets a coroutine type co_await senders directly."
updated: 2026-10-19
---

!!! tldr
    - An object that can be `co_await`ed is automatically a sender, with completion signatures fixed as `set_value_t(result of await)`, `set_error_t(exception_ptr)`, `set_stopped_t()`.
    - Conversely, `as_awaitable(sndr, promise)` wraps a sender with at most one kind of value completion into an awaiter: on a value completion `co_await` returns the value, and on an error completion `co_await` throws.
    - A stopped completion doesn't resume the coroutine; instead it calls the promise's `unhandled_stopped()`, with an effect like a cancellation exception that can't be `catch`ed propagating up the call chain.
    - The environment a `co_await`ed sender sees is the coroutine promise's `get_env()`.
    - When a promise type inherits from `with_awaitable_senders<Promise>`, every `co_await x` in the coroutine body goes through `as_awaitable` first; if no caller has been registered with `set_continuation`, cancellation leads to `std::terminate`.

The examples on this page use C++26 `std::execution`. The libc++ shipped with Clang 23 doesn't implement this part of the library yet, so the examples haven't been verified by compiling, and they carry no verdict. Before reading this page, it helps to know about coroutine **promise types** ([[dcl.fct.def.coroutine]]) and the evaluation steps of `co_await` ([[expr.await]]).

## Two directions

Coroutines and [[g:sender|senders]] describe the same thing: wait for something to finish, then continue. `std::execution` connects them in both directions:

| Direction | Mechanism | Subclauses |
|---|---|---|
| Using awaitables as senders | The sender concept accepts awaitables; `connect` wraps them in an internal coroutine | [exec.awaitable], [[exec.connect]] |
| Using senders as awaitables | `as_awaitable(sndr, promise)` returns an awaiter; `with_awaitable_senders` makes `await_transform` call it automatically | [exec.as.awaitable], [exec.with.awaitable.senders] |

The `task<T>` in [[exec.task]] is a ready-to-use coroutine type built on these facilities.

```cpp title="co-await-sender.cpp"
namespace ex = std::execution;

ex::task<int> f(ex::scheduler auto sch) {
  co_await ex::schedule(sch);                       // continue execution on sch
  int v = co_await (ex::just(20) | ex::then([](int x) { return x + 1; }));
  co_return v;                                      // 21
}
```

## Awaitables are senders ([exec.awaitable])

¶1 In [exec], an [[g:exec-awaitable|awaitable]] is an expression that can be the operand of `co_await` in a given context. The sender concept treats awaitables as senders too.

### How to tell whether a type can be co_awaited (¶2–4)

`co_await c` doesn't call `await_ready` and friends on `c` directly. [[expr.await]] specifies a series of transformations first: if the promise type has `await_transform`, call it; then find `operator co_await` by overload resolution; what you end up with is an object called the **awaiter**, and `await_ready`, `await_suspend` and `await_resume` are all called on it.

¶2 The standard writes this chain of transformations as *GET-AWAITER*(c, p), where `p` is the coroutine's promise object. *GET-AWAITER*(c) means the same transformations under an empty promise type with no `await_transform`.

¶3 On top of this, two exposition-only concepts are defined:

```cpp
template<class A, class... Promise>
concept is-awaiter = requires (A& a, coroutine_handle<Promise...> h) {
  a.await_ready() ? 1 : 0;
  { a.await_suspend(h) } -> await-suspend-result;   // void, bool or coroutine_handle
  a.await_resume();
};

template<class C, class... Promise>
concept is-awaitable = requires (C (*fc)() noexcept, Promise&... p) {
  { GET-AWAITER(fc(), p...) } -> is-awaiter<Promise...>;
};
```

*is-awaitable* uses a function pointer returning `C` to build an expression `fc()` of type `C`, which faithfully preserves `C`'s value category. ¶4 *await-result-type*<C, Promise> is the result type of `co_await c`, that is, the return type of the awaiter's `await_resume()`.

### Promise types used only for type computations (¶5–6)

¶5 *with-await-transform*<Derived> is a base class providing `await_transform`: if the awaited object has a member `as_awaitable(p)`, call it; otherwise return the object unchanged. This gives objects a hook for customizing how they are `co_await`ed.

¶6 *env-promise*<Env> is a promise type used only for type computations; its members needn't be defined (Note 2). It inherits from *with-await-transform*, and `get_env()` returns `const Env&`. The sender concept uses it to decide whether a type is an awaitable; [[exec.getcomplsigs]] uses it to compute an awaitable's result type in environment `Env`.

When an awaitable is used as a sender, its completion signatures are fixed:

```cpp
completion_signatures<SET-VALUE-SIG(await-result-type<S, env-promise<Env>>),
                      set_error_t(exception_ptr),
                      set_stopped_t()>
```

The result of `co_await` corresponds to the value completion, an exception thrown by `co_await` to the error completion, and the stopped completion comes from `unhandled_stopped` of the promise type of `connect`'s internal coroutine ([[exec.connect]]).

## Turning a sender into an awaiter ([exec.as.awaitable])

### Which senders can be co_awaited (¶1)

¶1 The *awaitable-sender* concept requires three things:

- the sender is a *single-sender*: it has at most one kind of value completion, since `co_await` can produce only one result. With exactly one value the result is that value's type (decayed); with no value completion or an empty value it is `void`; with several values in one completion it is a `tuple` ([[execution.syn]]);
- the sender can be connected to the *awaitable-receiver* described below;
- the promise type has `unhandled_stopped()`, whose return value is convertible to `coroutine_handle<>`, for handling stopped completions.

### sender-awaitable: the awaiter holds the operation state (¶2–6)

¶2 The general wrapper type is *sender-awaitable*:

```cpp
template<class Sndr, class Promise>
class sender-awaitable {
  using result-type = /* the value type; an empty unit stands in for void */;
  variant<monostate, result-type, exception_ptr> result{};
  connect_result_t<Sndr, awaitable-receiver> state;   // the operation state

public:
  sender-awaitable(Sndr&& sndr, Promise& p);
  static constexpr bool await_ready() noexcept { return false; }
  void await_suspend(coroutine_handle<Promise>) noexcept { start(state); }
  value-type await_resume();
};
```

The awaiter itself holds the [[g:operation-state|operation state]] and the result storage. The awaiter is a temporary in the evaluation of `co_await`, stored in the coroutine frame, and it lives for as long as the coroutine is suspended. The operation state must stay valid and unmoved during the asynchronous operation ([[exec.async.ops#7]]), which is naturally satisfied here, and no heap allocation beyond the coroutine frame itself is needed.

¶5 The sender is connected when the awaiter is constructed, and the receiver records the address of the result storage and the current coroutine's handle. ¶2 `await_suspend` starts the operation only after the coroutine has been suspended.

### How the three completions get back to the coroutine (¶4, ¶6)

¶4 *awaitable-receiver* handles the three completions differently:

- ¶4.1 Value completion: store the value in `result` (storing `current_exception()` instead if construction throws), then resume the coroutine.
- ¶4.2 Error completion: convert the error to an `exception_ptr` (rules in [[exec.general#8]]) and store it in `result`, then resume the coroutine.
- ¶4.3 Stopped completion: don't resume the current coroutine; instead call the promise's `unhandled_stopped()` and resume the coroutine handle it returns.

¶6 After the coroutine resumes, `await_resume()` checks `result`: if it holds an exception it rethrows it, otherwise it returns the value. So in the coroutine, an error completion appears as `co_await` throwing an exception.

The `resume()` calls in ¶4 are all wrapped in a noexcept lambda (*MAKE-NOEXCEPT*); if an exception escapes during resumption, `terminate` is called directly.

¶4.4 The environment of *awaitable-receiver* has all [[g:forwarding-query|forwarding queries]] answered by the promise's `get_env()`. The environment a `co_await`ed sender sees is this coroutine's environment.

### Cancellation is not an exception

¶4.3 is the most distinctive point of this design. When a sender completes with stopped, the suspended coroutine is never resumed. Control passes to the promise type's `unhandled_stopped()`, which decides whom to resume next. Usually it calls the caller coroutine's `unhandled_stopped()`, level by level upward, until reaching some place that can handle cancellation, such as `connect`'s internal coroutine calling `set_stopped` on its receiver.

[exec.with.awaitable.senders] ¶1 describes this as if an uncatchable "stopped" exception were thrown from the `co_await` expression. The coroutine frames along the way are not resumed; their owners destroy them.

### The order in which as_awaitable chooses (¶7–8)

¶7 `as_awaitable(expr, p)` requires `p` to be an lvalue, otherwise it is ill-formed. It tries, in order:

| Condition | Result |
|---|---|
| ¶7.1 `expr.as_awaitable(p)` is well-formed | The object's custom result (must be an awaitable) |
| ¶7.2 `expr` is a single-value sender and the transformed sender has `.as_awaitable(p)` | The transformed sender's custom result |
| ¶7.3 `expr` is already an awaiter under this promise type | `expr` returned unchanged |
| ¶7.4 `expr` is a single-value sender | *sender-awaitable*, the general path |
| ¶7.5 None of the above | `expr` returned unchanged, left to the ordinary rules of `co_await` |

The transformation in ¶7.2 and ¶7.4 is: first transform the sender by the domain of the coroutine's environment (`transform_sender`, see [[exec.snd.transform]]), then pass it through *adapt-for-await-completion* from ¶8: if the sender's environment provides `get_await_completion_adaptor`, wrap it once more with that; otherwise leave it as is.

¶7.3 comes before ¶7.4 in this order. If a type is both an awaiter and a sender, `as_awaitable` prefers to use it as an awaiter, keeping its native coroutine semantics rather than detouring through connect.

## with_awaitable_senders ([exec.with.awaitable.senders])

¶1 `with_awaitable_senders<Promise>` is used as a base class of a coroutine promise type so that senders can be `co_await`ed in that coroutine; it also provides a default implementation of `unhandled_stopped`.

```cpp title="with-awaitable-senders.cpp"
namespace ex = std::execution;

struct my_task {
  struct promise_type : ex::with_awaitable_senders<promise_type> {
    my_task get_return_object();
    std::suspend_always initial_suspend() noexcept { return {}; }
    auto final_suspend() noexcept;   // returns an awaiter that resumes continuation()
    void return_value(int);
    void unhandled_exception();
  };
  // ...
};
```

The `Promise` template parameter is the derived promise type itself (CRTP), because `await_transform` has to convert `*this` to `Promise&` to hand it to `as_awaitable`. Its members are:

- ¶3 `await_transform(value)` returns `as_awaitable(std::forward<Value>(value), static_cast<Promise&>(*this))`. Every `co_await x` in the coroutine body goes through this step first.
- ¶2 `set_continuation(h)` remembers the caller coroutine `h`. If the caller's promise type has `unhandled_stopped()`, it records a function that recovers a `coroutine_handle<OtherPromise>` from the address and then calls the caller's `unhandled_stopped()`, so cancellation propagates to the caller. Otherwise it records the default handler, which calls `terminate()`.
- `unhandled_stopped()` calls the function recorded above. `continuation()` returns the caller's handle.

`set_continuation` stores the caller as a function pointer plus a `void*`, a hand-written form of type erasure: `with_awaitable_senders<Promise>` doesn't need to know the caller's promise type.

### Cancelled with no caller registered

The handler's initial value is the default function that calls `terminate()`. If the coroutine's owner hasn't registered a caller able to handle cancellation with `set_continuation`, then any sender `co_await`ed in this coroutine that completes with stopped leads to `std::terminate`. When writing your own coroutine type, you must set up the continuation before starting the coroutine.

## Questions

!!! question "1. co_await on a sender with two value signatures"
    `s` has signatures `set_value_t(int)` and `set_value_t(std::string)`. What happens with `co_await s` in a coroutine that inherits from `with_awaitable_senders`?

<details markdown="1">
<summary>Answer</summary>

`await_transform` calls `as_awaitable(s, p)`. ¶7.2 and ¶7.4 both require *single-sender-value-type* to be well-formed, and with two value signatures it is ill-formed ([[execution.syn]]), so neither applies. `s` isn't an awaiter either (¶7.3). So ¶7.5 applies, and `s` is returned unchanged.

Then `co_await` looks for `operator co_await` or awaiter members on `s`, finds none, and the program is ill-formed. The fix is to merge the signatures first: `co_await into_variant(s)` gives a `variant<tuple<int>, tuple<std::string>>`.
</details>

!!! question "2. Why store the result in a variant first?"
    Why does *awaitable-receiver*'s `set_value` first store the value in `result` and then resume the coroutine, rather than handing the value to the coroutine directly?

<details markdown="1">
<summary>Answer</summary>

After resuming, a coroutine can obtain the result of `co_await` only through `await_resume()`; that's the fixed protocol of [[expr.await]], and there is no other channel. So the value must first be stored somewhere `await_resume` can read it, namely the awaiter's own member `result`.

In addition, the arguments of `set_value` may refer to data inside the sender's operation state. After resuming, the coroutine continues running and may soon end this `co_await` expression, destroying the awaiter and the operation state inside it. Copying the value into `result` first ensures that what `await_resume` reads is valid data.
</details>

## Summary

| Question | Answer |
|---|---|
| Signatures of an awaitable used as a sender | `set_value_t(result of await)`, `set_error_t(exception_ptr)`, `set_stopped_t()` |
| Which senders can be `co_await`ed | At most one kind of value completion, and the promise type has `unhandled_stopped()` |
| Value completion | `await_resume()` returns the value |
| Error completion | `await_resume()` rethrows the exception |
| Stopped completion | The coroutine isn't resumed; `promise.unhandled_stopped()` is called |
| Environment the sender sees | The promise's `get_env()` |
| `with_awaitable_senders` | `await_transform` uniformly calls `as_awaitable`; cancellation with no caller registered leads to `terminate` |
