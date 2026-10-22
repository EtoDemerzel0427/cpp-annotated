---
title: Sender factories
summary: "The three starting points of a sender chain: schedule(sch) hops onto a scheduler and completes there; just, just_error and just_stopped complete synchronously in start with the given result; read_env(q) completes with the result of query q on the receiver's environment."
updated: 2026-10-19
---

!!! tldr
    - A factory takes no senders, only ordinary values, and returns a sender; it is the starting point of every sender chain.
    - `schedule(sch)` is just `sch.schedule()`: it completes with `set_value()` on the scheduler's execution resource.
    - `just(vs...)` stores the values in the sender and sends them synchronously as rvalues in `start`; it has no error or stopped completion. `just_error` takes exactly one argument, and `just_stopped` takes none.
    - `read_env(q)` reads the result of query `q` on the receiver's environment in `start`, and completes with it as a value.

The examples on this page have not been verified by compiling: the libc++ shipped with Clang 23 doesn't implement the sender part of `std::execution` yet, so they carry no verdict.

## Three starting points

[[exec.async.ops#14]] divides sender algorithms into three kinds: factories, adaptors and consumers. A sender factory builds a sender from non-sender arguments:

| Factory | How it completes | When it completes |
|---|---|---|
| `schedule(sch)` | `set_value()` | On `sch`'s execution resource, usually asynchronously |
| `just(vs...)`, `just_error(e)`, `just_stopped()` | The corresponding completion function, with the given data | Synchronously within `start` |
| `read_env(q)` | `set_value(q(env))` | Synchronously within `start` |

The specifications of the last two factories are written as *make-sender* plus an *impls-for* specialization. Before reading them, it helps to look at the skeleton introduced in [[exec.snd]]: every standard sender has three parts (tag, data, child senders...), and an algorithm only has to say how a few hooks, such as *start* and *complete*, differ from the default behavior.

## schedule [exec.schedule]

¶1 `schedule` takes a [[g:scheduler|scheduler]] and obtains a [[g:schedule-sender|schedule sender]] from it ([[exec.async.ops#10]]).

¶2 `schedule(sch)` is equivalent to `sch.schedule()`. ¶3 Its type is required to satisfy `sender` (*Mandates*).

All of a scheduler's capability lies in its `schedule()` member. The semantics a schedule sender must meet, such as its value completion carrying no data and its value completion scheduler being the original scheduler, are in [[exec.sched]].

## just, just_error, just_stopped [exec.just]

```cpp title="just.cpp"
namespace ex = std::execution;

auto a = ex::just(1, 2.0);                 // set_value_t(int, double)
auto b = ex::just_error(std::make_error_code(std::errc::io_error));
                                           // set_error_t(std::error_code)
auto c = ex::just_stopped();               // set_stopped_t()
// ex::just_error();                       // error: needs exactly one argument
// ex::just_stopped(1);                    // error: takes no arguments
// int arr[3]; ex::just(arr);              // error: an array doesn't satisfy movable-value
auto [x, y] = std::this_thread::sync_wait(a).value();   // x == 1, y == 2.0
```

¶1 The asynchronous operations these three factories produce complete synchronously within their start operation, with a value, an error and a stopped completion respectively.

¶2 *just-cpo*(ts...) is ill-formed {{ill-formed}} (where *just-cpo* is one of the three) if:

- ¶2.1 some argument type doesn't satisfy *movable-value*: the decayed type isn't move constructible or can't be constructed from the argument, or the argument is an array ([[exec.general]]);
- ¶2.2 `just_error` doesn't have exactly one argument;
- ¶2.3 `just_stopped` has arguments.

Otherwise it is equivalent to *make-sender*(*just-cpo*, *product-type*{ts...}): the arguments are copied or moved into a tuple inside the sender. The *impls-for* overrides only *start*:

```cpp
template<>
struct impls-for<decayed-typeof<just-cpo>> : default-impls {
  static constexpr auto start = [](auto& state, auto& rcvr) noexcept -> void {
    auto& [...ts] = state;
    set-cpo(std::move(rcvr), std::move(ts)...);
  };
};
```

*set-cpo* is `set_value`, `set_error` and `set_stopped` respectively. Several properties of `just` can be read from these few lines:

- The values flow like this: stored in the sender at construction, copied or moved into the operation state at connect, and moved to the receiver at `start`. So the signature of `just(std::string("hi"))` is `set_value_t(std::string)`, sent as an rvalue.
- The signatures of standard algorithms are determined by the completion calls potentially evaluated in `start` ([[exec.snd]]). The arguments here are xvalues, so the signature is `set_value_t(decay_t<Ts>...)`.
- The signatures of `just(1)` are just `set_value_t(int)`, with no error or stopped. `start` can't fail, because the data was ready at connect; if copying the data throws, it is `connect` that throws, not the operation that completes with an error.
- `just()` carries no values and has signature `set_value_t()`; it is often used as a do-nothing starting point. For example, the lowered form of `starts_on` contains `continues_on(just(), sch)` ([[exec.on]]).

Before `start(op)` returns, the receiver's `set_value` has already been called and returned. This is what Note 1 of [[exec.async.ops#2]] means by an asynchronous operation executing synchronously. Accordingly, when `just`'s attributes answer the completion scheduler, they give the `get_scheduler` from the environment: it completes wherever `start` was called (*inline-attrs*, see [[exec.snd]]).

## read_env [exec.read.env]

```cpp title="read-env.cpp"
namespace ex = std::execution;

// schedule more work on the current environment's scheduler
auto work = ex::read_env(ex::get_scheduler)
          | ex::let_value([](auto sch) {
              return ex::schedule(sch) | ex::then([] { return 42; });
            });

// get the stop token and check it in a long loop
auto loop = ex::read_env(std::get_stop_token)
          | ex::then([](auto token) {
              while (!token.stop_requested()) { /* ... */ }
            });
```

¶1 The sender `read_env` produces completes synchronously within its start operation, and its value completion result is a value read from the receiver's environment. It lets a sender chain see its own execution environment: scheduler, stop token, allocator and so on.

¶2 `read_env(q)` (where `q` is a query object) is equivalent to *make-sender*(read_env, q).

¶3 The *impls-for* overrides *start* and *check-types*:

```cpp
static constexpr auto start = [](auto query, auto& rcvr) noexcept -> void {
  TRY-SET-VALUE(rcvr, query(get_env(rcvr)));
};
```

*TRY-SET-VALUE* wraps the expression in a `try` when it may throw, turning the exception into `set_error(exception_ptr)`. The query itself must be noexcept; what may throw is the copy made when the query result is passed as an argument to `set_value`.

¶4–5 *check-types* checks whether the query can be answered: let `Q` be the type of the query object; if `Q()(env)` is ill-formed or has type `void`, an exception of unspecified type is thrown, and computing the signatures fails as a result.

!!! lawyer "read_env and dependent senders"
    The value type of `read_env(get_scheduler)` depends on the environment, so intuitively it should be a dependent sender: report `dependent_sender_error` when no environment is given ([[exec.async.ops#13]]). Read literally, the draft doesn't say so.

    1. Calling `get_completion_signatures<S>()` without an environment goes to the static member of *basic-sender* ([[exec.getcomplsigs#3]]).
    2. Without an environment, that member runs *check-types* with `env<>` (the *basic-sender* part of [[exec.snd]], paragraph 47).
    3. `get_scheduler(env<>)` is ill-formed, and per ¶5 what is thrown is an ordinary unspecified exception, not `dependent_sender_error`.

    The result is that this sender satisfies neither `dependent_sender` nor `sender_in`, the *Mandates* of *make-sender* don't hold, and the expression `read_env(get_scheduler)` is itself ill-formed. This contradicts the purpose of `read_env` and should be seen as a gap in the wording; for actual behavior, go by implementations.

    `read_env(std::get_stop_token)` has a different problem: `get_stop_token(env<>)` is well-formed and returns `never_stop_token`, so the signatures reported without an environment are `set_value_t(never_stop_token)`. With an environment the value type might be `inplace_stop_token`, and the two don't stand in the superset relationship required by [[exec.getcomplsigs#4]].

## Questions

!!! question "1. How many times is just's data copied?"
    `auto s = just(std::string(1000, 'x')); sync_wait(s);` (called with the lvalue `s`). From constructing `s` until `sync_wait`'s receiver gets the string, how many times is the `std::string` copied or moved?

<details markdown="1">
<summary>Answer</summary>

Working it through from the exposition code (implementations may differ):

1. `just(std::string(...))`: the temporary string is moved into the *product-type*, which then goes into the *basic-sender*. With direct-list-initialization, an implementation can merge these into a single move.
2. `sync_wait(s)` connects with an lvalue: *get-state* takes the data out with `forward_like<Sndr>(data)`; `Sndr` is an lvalue reference type, so the data is copied once into the operation state.
3. `start`: `set_value(std::move(rcvr), std::move(ts)...)` hands it as an rvalue to `sync_wait`'s receiver, which moves it once more into an `optional<tuple<string>>`.

So at least one copy and several moves. With `sync_wait(std::move(s))`, step 2 becomes a move too, and there are no copies at all.
</details>

!!! question "2. Is just_error(42) valid?"
    Can the error type be `int`? What happens with `sync_wait(just_error(42))`?

<details markdown="1">
<summary>Answer</summary>

It's valid: the datum of an error completion can be any object type ([[exec.cmplsig]]), and the signature is `set_error_t(int)`. When `sync_wait` receives an error it turns it into an `exception_ptr` with *AS-EXCEPT-PTR* ([[exec.general]]): `int` is neither `exception_ptr` nor `error_code`, so the result is `make_exception_ptr(42)`, which is then rethrown. `sync_wait` throws an `int`, which can be caught with `catch (int)`.
</details>
