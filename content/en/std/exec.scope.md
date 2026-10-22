---
title: Async scopes
summary: "How concurrent work whose amount is known only at run time is brought under structured concurrency: work first associates with a counting scope through a token, close rejects new work, and join waits for the count to reach zero; a scope that was used but not joined calls terminate when destroyed."
updated: 2026-10-19
---

!!! tldr
    - An async scope manages concurrent work whose amount is known only at run time: each piece of work first associates with the scope, the scope counts the associations, and the sender returned by `join()` completes when the count reaches zero.
    - An association is a move-only RAII handle, and a token is a copyable lightweight handle; once the scope is closed, establishing an association fails, and `spawn` silently drops that work.
    - `close()` rejects new associations; `join()` doesn't: work added while join is waiting is waited for as well.
    - Once a scope has been used, it must be fully joined before it is destroyed; otherwise `terminate` is called.
    - `counting_scope` has one more thing than `simple_counting_scope`, `request_stop()`, which requests cancellation of all work started through it in one go.

The examples on this page use C++26 `std::execution`. The libc++ shipped with Clang 23 doesn't implement this part of the library yet, so none of the examples have been verified by compiling, and they carry no verdict.

## One task per incoming connection

```cpp title="counting-scope.cpp"
namespace ex = std::execution;

void serve(listener& l) {
  ex::counting_scope scope;
  auto pool = ex::get_parallel_scheduler();

  while (auto conn = l.accept()) {
    // spawn only accepts senders that complete with set_value_t() or set_stopped_t(),
    // so swallow (or log) the errors first
    auto work = ex::starts_on(pool, handle(std::move(*conn)))
              | ex::upon_error([](auto&&) noexcept {});
    ex::spawn(std::move(work), scope.get_token());   // start dynamically
  }
  scope.close();                                   // accept no more new work
  std::this_thread::sync_wait(scope.join());       // wait for every handle to end
}                                                  // scope destroyed: fully joined, OK
```

The structured concurrency rule of [[exec.async.ops#2]] requires child operations to complete before their parent completes. Adaptors like `when_all` meet this requirement, but their number of children is fixed at compile time. A server starts a handler task for each request it receives; the number of tasks is known only at run time, and each task has its own lifetime.

The **async scope** ([[g:async-scope]]) solves exactly this problem. In the example, `scope` keeps track of how many pieces of work haven't ended yet; after `close()` it accepts no new work; and the sender returned by `join()` completes when all the work has ended. When `serve` returns, every `handle` it started has ended, so no task is still running after `serve`'s local variables are destroyed.

The scope itself starts no work; starting is the job of `spawn`, `spawn_future` and `associate` ([[exec.spawn]]). Early P2300 used `start_detached` and `ensure_started` to start work nobody waited for; the current draft no longer has these two algorithms.

## Associations and tokens [exec.scope.concepts]

### scope_association: ownership of one unit of the count (¶1–2)

```cpp
template<class Assoc>
  concept scope_association =
    movable<Assoc> &&
    is_nothrow_move_constructible_v<Assoc> &&
    is_nothrow_move_assignable_v<Assoc> &&
    default_initializable<Assoc> &&
    requires(const Assoc assoc) {
      { static_cast<bool>(assoc) } noexcept;
      { assoc.try_associate() } -> same_as<Assoc>;
    };
```

¶1 An object of type `Assoc` is said to be **engaged** when it owns an **association** with some async scope, which is called its associated scope.

¶2 The semantic requirements say it is a move-only RAII handle, similar to `unique_ptr`, except that what it owns is one unit of a scope's count:

- ¶2.1 a default-constructed object isn't engaged;
- ¶2.2 `bool(assoc)` is true if and only if it is engaged;
- ¶2.3 two distinct objects never own the same association;
- ¶2.4 an object releases the association it owns when destroyed;
- ¶2.5, ¶2.6 after being moved from, the source object is no longer engaged; move assignment first releases the target's existing association;
- ¶2.7 calling `try_associate()` on an engaged object either obtains a new association with the same scope and returns an object owning it, or fails and returns an object that isn't engaged;
- ¶2.8 calling `try_associate()` on an object that isn't engaged always returns an object that isn't engaged.

### scope_token: the entry point for establishing associations (¶3–5)

```cpp
template<class Token>
  concept scope_token =
    copyable<Token> &&
    requires(const Token token) {
      { token.try_associate() } -> scope_association;
      { token.wrap(declval<test-sender>()) } -> sender_in<test-env>;
    };
```

¶3 A **token** ([[g:scope-token]]) is used to establish associations between senders and an async scope; each token is associated with one scope. ¶4 *test-sender* and *test-env* are unspecified types satisfying `sender_in`, used to check that `wrap` is syntactically usable.

¶5 Semantic requirements:

- ¶5.1 copying and moving a token don't throw. A token is a lightweight handle, usually just a pointer to the scope.
- ¶5.2 `token.try_associate()` either obtains a new association and returns an engaged object, or returns an object that isn't engaged.
- ¶5.3 for any sender `sndr`, `token.wrap(sndr)` is a valid sender with the same completion signatures as `sndr` in any environment.

`wrap` gives the scope a chance to decorate the sender handed to it, but it can't change how the sender may complete. `simple_counting_scope`'s `wrap` returns the sender unchanged; `counting_scope`'s `wrap` adds the scope's stop token (see below).

## The states of a counting scope [exec.counting.scopes.general]

¶1 `simple_counting_scope` and `counting_scope` maintain a count of associations, and go through the following states over their lifetime. Let `tkn` be the token obtained from `scope.get_token()`, and `op` the operation state obtained by connecting `scope.join()` to some receiver:

| State | Entered when |
|---|---|
| *unused* | Just constructed |
| *open* | `tkn.try_associate()` is called in *unused* |
| *open-and-joining* | `op` is started in *unused* or *open* |
| *closed* | `scope.close()` is called in *open* |
| *unused-and-closed* | `scope.close()` is called in *unused* |
| *closed-and-joining* | `close()` is called in *open-and-joining*; or `op` is started in *closed* or *unused-and-closed* |
| *joined* | The count drops to 0 in *open-and-joining* or *closed-and-joining* |

¶2 recommends that implementations store the state and the count in a single `size_t` member, so that one atomic operation can update both at once.

¶5 The exposition-only class template *association-t*<Scope> models `scope_association`; it has just one `Scope*` member: a non-null pointer means engaged, `try_associate()` forwards to the scope's *try-associate*, and releasing the association calls the scope's *disassociate*.

### join completes back on the scheduler that started it (¶4)

¶4 The operation state of the join sender connects an operation in advance when it is constructed: `schedule(get_start_scheduler(get_env(rcvr)))`, that is, scheduling onto the start scheduler where join's receiver is. Starting the join has two completion paths:

- if the count is already 0 at that point, it calls `set_value` in place, completing synchronously;
- otherwise it registers the operation state with the scope. Later, when the last association is released, the scope calls its `complete()`, and `complete()` doesn't call `set_value` directly; instead it starts the schedule operation connected in advance, returning to the scheduler on which the join was started before completing.

The second path is designed this way because which thread releases the last association is uncertain; it might be some thread-pool thread. If completion happened right there, the code after `join()` would run on an unexpected thread. The price is that the environment of join's receiver must be able to answer `get_start_scheduler`; otherwise the program is ill-formed. The environments of `sync_wait` and `task` both provide it.

## simple_counting_scope [exec.scope.simple.counting]

```cpp
class simple_counting_scope {
public:
  struct token;
  static constexpr size_t max_associations = implementation-defined;

  simple_counting_scope() noexcept;
  simple_counting_scope(simple_counting_scope&&) = delete;
  ~simple_counting_scope();

  token get_token() noexcept;
  void close() noexcept;
  sender auto join() noexcept;
};
```

[exec.scope.simple.counting.general] ¶1 For the purpose of determining data races, `get_token`, `close`, `join`, *try-associate*, *disassociate* and *start-join-sender* behave as atomic operations ([[intro.multithread]]), and these operations on the same object occur in a single total order. So spawning, closing and joining can be done concurrently from any thread. `max_associations` is the implementation-defined maximum number of associations {{impl}}.

### It must be fully joined before destruction [exec.simple.counting.ctor]

¶1 After construction, the count is 0 and the state is *unused*.

¶2 On destruction, if the state isn't one of *joined*, *unused* or *unused-and-closed*, `terminate` is called.

If a scope is destroyed while some work hasn't ended, that work would access the destroyed scope when it releases its association on ending. The standard chooses `terminate`, rather than undefined behavior or blocking to wait in the destructor, turning a forgotten join into an immediately visible error.

```cpp title="forgot-join.cpp"
{
  ex::counting_scope scope;
  ex::spawn(work(), scope.get_token());
}   // terminate: the state is open
```

Even if `work()` has already ended and the count is back to 0, the state is still *open*. Only when a join has been started and the count reaches zero is *joined* entered. So once you have spawned anything, you must start and wait for a `join()`.

### Members [exec.simple.counting.mem]

¶1 `get_token()` returns a token referring to `this`.

¶2 `close()` changes *unused* to *unused-and-closed*, *open* to *closed*, and *open-and-joining* to *closed-and-joining*; other states are unchanged. ¶3 After that, every *try-associate* fails. The wording says it returns false, but *try-associate* returns an *assoc-t*; what is meant is that it returns an object that isn't engaged.

¶4 `join()` only returns a sender and doesn't change the state itself. The state changes only when the join sender's operation is started.

¶5–6 *try-associate*: fails if the count already equals `max_associations`. Otherwise, in the *unused* state it increments the count and moves to *open*; in the *open* or *open-and-joining* state it increments the count; in other states (closed or already joined) it fails. On success it returns an engaged *assoc-t*, and on failure a default-constructed *assoc-t*.

¶7–8 *disassociate*: decrements the count. If it reaches 0 and the state is *open-and-joining* or *closed-and-joining*, it moves to *joined* and calls `complete()` on every registered join operation. Note 1 warns that calling `complete()` may cause the scope itself to be destroyed.

¶9 *start-join-sender*: when the count is 0, moves to *joined* and returns true, and the join completes in place. Otherwise it registers this join operation and returns false, and the state moves to *open-and-joining* or *closed-and-joining* depending on whether it has already been closed.

!!! note "join is not close"
    In the *open-and-joining* state *try-associate* still succeeds: while a join is waiting, new work can still be added, and the join waits for it too. This suits cases where processing spawns further subtasks along the way. To guarantee that no new work arrives after join, call `close()` first. On the other hand, *joined* is a final state; once it is entered, every *try-associate* fails.

### The token [exec.simple.counting.token]

¶1 `token::wrap(snd)` returns `std::forward<Sender>(snd)` unchanged. ¶2 `token::try_associate()` is equivalent to `scope->try-associate()`.

## counting_scope: adding cancellation [exec.scope.counting]

¶1 `counting_scope` adds cancellation support on top of `simple_counting_scope`; the other members have the same semantics. It has an extra `inplace_stop_source` member and a `request_stop()` member function.

¶3–4 `request_stop()` is equivalent to calling `request_stop()` on the internal stop source, and concurrent calls introduce no data races.

¶7 `token::wrap(snd)` returns *stop-when*(snd, token of the scope's stop source). Once the wrapped sender is connected, the stop token it sees is the combination of the outer token and the scope's token, and a stop requested by either takes effect (*stop-when* is in [[exec.spawn]]). So `scope.request_stop()` can request cancellation of all work started through this scope in one go.

A typical shutdown sequence:

```cpp title="shutdown.cpp"
scope.close();                                // 1. accept no more new work
scope.request_stop();                         // 2. ask existing work to finish as soon as possible
std::this_thread::sync_wait(scope.join());    // 3. wait until it has really finished
```

## Questions

!!! question "1. Can the scope be destroyed while join is completing?"
    `scope` is destroyed immediately after `sync_wait(scope.join())` returns. The last association was released on a thread-pool thread, and *disassociate* is still calling `complete()` at this point. Does it access the destroyed scope?

<details markdown="1">
<summary>Answer</summary>

Note 1 explicitly acknowledges that calling `complete()` may cause the scope to be destroyed, so implementations must ensure they don't access the scope's members after calling `complete()`, for example by first moving the list of registrations into a local variable. In the `sync_wait` case, what `complete()` starts is an operation scheduled onto `sync_wait`'s internal `run_loop`, which merely enqueues it; the actual `set_value` happens on `sync_wait`'s thread, after which `sync_wait` returns and the scope is destroyed. By then the state is already *joined*, so destruction is valid. As long as the implementation honors "don't access `this` after calling `complete()`", there's no problem.
</details>

!!! question "2. When does try_associate fail? What happens when it does?"

<details markdown="1">
<summary>Answer</summary>

`simple_counting_scope`'s *try-associate* fails in three cases: the count already equals `max_associations`; the scope is already closed (*closed*, *unused-and-closed*, *closed-and-joining*); or the scope is already *joined*. When association fails, `spawn` doesn't start the sender and directly destroys the state allocated for it (the *run* of *spawn-state* in [[exec.spawn]] takes the `complete()` branch); the work is silently dropped, without an error. The senders returned by `associate` and `spawn_future` complete with `set_stopped` when association fails.
</details>
