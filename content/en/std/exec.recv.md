---
title: Receivers
summary: "The receiver concept, receiver-of for checking completion signatures, the validity period of stop tokens, inlinable_receiver that can be rebuilt on demand, and the three completion functions set_value, set_error and set_stopped."
updated: 2026-10-19
---

!!! tldr
    - A receiver is the continuation of an asynchronous operation: it declares `receiver_concept`, can be moved without throwing, and `get_env` gives its environment. A `final` class can't be a receiver.
    - The `receiver` concept checks no `set_*` members; whether a receiver accepts a set of completion signatures is checked separately by *receiver-of*, which `connect` requires.
    - Completion functions accept only non-const rvalue receivers, and must return `void` and be `noexcept`, so completing a receiver is written `set_value(std::move(rcvr), ...)`.
    - The stop token in the environment is valid only during the async lifetime, and stop callbacks registered on it must be destroyed before the completion function is called.
    - `inlinable_receiver` is a space optimization: a receiver that can be rebuilt from the operation state's address, so the implementation needn't store it.

A receiver ([[exec.async.ops#5]]) is three completion handlers plus an environment: who gets the result when the operation completes, and what child operations can look up in the environment. Day-to-day use of `std::execution` rarely involves writing receivers directly; they mainly show up when writing sender algorithms.

Clang 23's libc++ doesn't implement this part of `std::execution` yet, and the examples on this page have not been compiled.

## A receiver

```cpp title="print-receiver.cpp"
namespace ex = std::execution;

struct print_receiver {
  using receiver_concept = ex::receiver_tag;

  void set_value(int v) && noexcept              { std::println("value {}", v); }
  void set_error(std::exception_ptr) && noexcept { std::println("error"); }
  void set_stopped() && noexcept                 { std::println("stopped"); }
  // no get_env: the environment is env<>{}
};
static_assert(ex::receiver<print_receiver>);
```

All three members are `&&`-qualified and `noexcept`; the reasons are under the completion functions below.

## The receiver concept ([exec.recv.concepts] ¶1–2)

```cpp
template<class Rcvr>
  concept receiver =
    derived_from<typename remove_cvref_t<Rcvr>::receiver_concept, receiver_tag> &&
    requires(const remove_cvref_t<Rcvr>& rcvr) {
      { get_env(rcvr) } -> queryable;
    } &&
    move_constructible<remove_cvref_t<Rcvr>> &&               // rvalues are movable, and
    constructible_from<remove_cvref_t<Rcvr>, Rcvr> &&         // lvalues are copyable, and
    is_nothrow_move_constructible_v<remove_cvref_t<Rcvr>>;    // no-throw-movable
```

¶1 Item by item:

- **The `receiver_concept` tag**: the type opts in to being a receiver. The concept checks no `set_*` members; a type that only declares the tag satisfies `receiver`.
- **`get_env(rcvr)`** works on a const receiver, and the result is a queryable object. Not having a `get_env` member is fine too; `get_env` defaults to returning `env<>{}` ([[exec.get.env]]).
- **Moving doesn't throw**: `connect` has to move the receiver into the operation state, and adaptors often need to move receivers on `noexcept` completion paths. If moving could throw, completion would produce errors with nowhere to report them.
- `constructible_from<remove_cvref_t<Rcvr>, Rcvr>` requires that a copy can be constructed from the value category `Rcvr`; for an lvalue, that means copyable.

¶2 A class marked `final` doesn't model `receiver`. This is a semantic requirement that the concept check can't detect: a `final` receiver passes `static_assert(receiver<R>)`, but the program doesn't meet the concept's requirements. The standard gives no rationale; one reasonable reading is that it leaves implementations room to derive from user receivers, for example to store stateless receivers using the empty base optimization.

### receiver-of: whether a set of completion signatures is accepted

```cpp
template<class Signature, class Rcvr>
  concept valid-completion-for =
    requires (Signature* sig) {
      []<class Tag, class... Args>(Tag(*)(Args...))
          requires callable<Tag, remove_cvref_t<Rcvr>, Args...>
      {}(sig);
    };

template<class Rcvr, class Completions>
  concept has-completions =
    requires (Completions* completions) {
      []<valid-completion-for<Rcvr>...Sigs>(completion_signatures<Sigs...>*)
      {}(completions);
    };

template<class Rcvr, class Completions>
  concept receiver-of = receiver<Rcvr> && has-completions<Rcvr, Completions>;
```

This uses immediately invoked generic lambdas for pattern matching:

1. *has-completions* passes `Completions*` to a lambda that accepts only `completion_signatures<Sigs...>*`, extracting `Sigs...`, and requires each signature to satisfy *valid-completion-for*;
2. *valid-completion-for* passes a pointer to the signature (such as `set_value_t(*)(int)`) to a lambda that accepts `Tag(*)(Args...)`, extracting `Tag` and `Args...`, and requires `Tag` to be callable with an rvalue receiver and `Args...`, that is, `set_value(std::move(rcvr), args...)` is well-formed.

So *receiver-of*<R, completion_signatures<set_value_t(int), set_stopped_t()>> checks that `set_value(R&&, int)` and `set_stopped(R&&)` can both be called. The *Mandates* of `connect` include this ([[exec.connect#6]]): the receiver must accept every kind of completion the sender may send.

These two exposition-only concepts can be copied into ordinary C++ code; paired with a hand-written mock of `set_value_t`, Clang 23 decides as described above: a receiver with only `set_value(int)` and `set_stopped()` members satisfies the set of signatures above, and an empty struct doesn't satisfy `completion_signatures<set_value_t()>`.

## The three completion functions ([exec.set.value], [exec.set.error], [exec.set.stopped])

```cpp title="set-value-rvalue.cpp"
void complete(print_receiver& r) {
  namespace ex = std::execution;
  ex::set_value(r, 1);              // error: r is an lvalue
  ex::set_value(std::move(r), 1);   // OK
  const print_receiver cr{};
  ex::set_value(std::move(cr), 1);  // error: const rvalue
}
```

The three completion functions are specified with the same structure:

| Completion function | Completion tag | Expression | Equivalent to |
|---|---|---|---|
| `set_value` | `set_value_t` | `set_value(rcvr, vs...)` | *MANDATE-NOTHROW*(rcvr.set_value(vs...)) |
| `set_error` | `set_error_t` | `set_error(rcvr, err)` | *MANDATE-NOTHROW*(rcvr.set_error(err)) |
| `set_stopped` | `set_stopped_t` | `set_stopped(rcvr)` | *MANDATE-NOTHROW*(rcvr.set_stopped()) |

Each also has two more rules:

1. If `rcvr` is an lvalue or a const rvalue, the expression is ill-formed {{ill-formed}}.
2. When the member call is well-formed, its type must be `void`; *MANDATE-NOTHROW* ([[exec.general#5]]) also requires it to be `noexcept`.

Rule 1 expresses "completes exactly once" ([[exec.async.ops#8]]) at the language level: completing a receiver consumes it, so you must write `std::move(rcvr)`. Using `rcvr` again after completion then becomes use of a moved-from object, which is easier for code review and static analysis to catch.

The member function is called on an rvalue `rcvr`, so a receiver's members can be `&&`-qualified (recommended) or unqualified, but not provided only in an `&`-qualified version.

`set_error` has exactly one error argument and `set_stopped` has no data arguments, matching the number of datums of the three kinds of completion in [[exec.async.ops#2]].

!!! pitfall "Throwing inside set_value"
    A receiver's `set_value` must be `noexcept`, otherwise the `set_value(...)` expression is ill-formed. If handling the value can fail, the receiver should catch the failure itself and call `set_error` on the downstream receiver it holds. *TRY-SET-VALUE* in [[exec.snd]] is this pattern.

## Validity period of the stop token ([exec.recv.concepts] ¶3)

```cpp title="stop-callback-order.cpp"
void complete_value(T v) noexcept {
  stop_cb_.reset();                                    // 1. deregister the stop callback first
  ex::set_value(std::move(rcvr_), std::move(v));       // 2. then complete
}
```

¶3 Let `token` be equal to `get_stop_token(get_env(rcvr))`; it must remain valid for the lifetime of the asynchronous operation ([[exec.async.ops#7]]). Note 1 points out two consequences: unless it's known that the receiver type gives further guarantees, the operation state can't use `token` after executing a completion operation; and stop callbacks registered on `token` must be destroyed before the completion operation is invoked.

Reversing the order above is wrong. As soon as `set_value` begins, the async lifetime ends, and whoever provides the token (such as the `inplace_stop_source` inside `when_all`) may be destroyed immediately; the destructor of `stop_cb_` would then access stop state that no longer exists. That's why the exposition code of the standard `when_all` writes `on_stop.reset();` first in every completion branch ([[exec.when.all]]).

## inlinable_receiver ([exec.recv.concepts] ¶4–9)

```cpp
template<class Rcvr, class ChildOp>
  concept inlinable_receiver = receiver<Rcvr> &&
    requires (ChildOp* child) {
      { remove_cvref_t<Rcvr>::make_receiver_for(child) } noexcept
        -> same_as<remove_cvref_t<Rcvr>>;
    };
```

Consider `then(then(then(s, f), g), h)`. The innermost operation state stores a receiver, which is usually just a pointer to the enclosing operation state, and the deeper the nesting the more is wasted. But the child operation state is embedded in the parent operation state anyway, so the parent's address can be computed from the child's. The receiver therefore doesn't need to be stored; it can be rebuilt from the child operation state's address when needed.

¶4 `inlinable_receiver<Rcvr, ChildOp>` describes such a receiver: `Rcvr::make_receiver_for(addressof(op))` must yield a receiver equal to the original one. Note 2 says that such a receiver need not be stored in `op` as a data member. `ChildOp` can be an incomplete type, because when the parent operation state declares its child operation state member, the child type is often still incomplete.

¶5–6 define two terms. An object obtained from another object by one copy followed by some number of moves is said to be **transitively constructed** from it. If all objects transitively constructed from `rcvr` during the evaluation of `connect(sndr, rcvr)` end their lifetimes within that evaluation, the expression is said to **inline the receiver** ([[g:inlines-the-receiver|inlines the receiver]]): the operation state doesn't store the receiver.

¶7 For senders defined by the standard, if connect inlines the receiver, then wherever the wording refers to an object transitively constructed from `rcvr`, it refers instead to a temporary built on the spot by `make_receiver_for(addressof(op))`. The `std::move(rcvr)` that appears all over this chapter then reads as "build a receiver on the spot".

¶8 Whether the standard library's own receiver types model `inlinable_receiver` is unspecified {{unspec}}. ¶9 If your receiver models `inlinable_receiver<StdOp>` (where `StdOp` is a standard operation state type), whether the connect that produces `StdOp` inlines it is implementation-defined {{impl}}.

!!! lawyer "Why is one unspecified and the other implementation-defined?"
    ¶8 is about whether standard receivers offer this ability, an implementation detail not worth requiring documentation for. ¶9 is about whether standard operation states take advantage of this ability in your receiver, which affects whether your receiver object is actually stored, and thus whether its side effects and address are stable, so the implementation is required to document it. Whoever writes `make_receiver_for` must ensure the behavior is the same whether it's stored or not; ¶4's requirement that the rebuilt receiver equal the original is that guarantee.

## Questions

!!! question "1. A receiver with no set_* members"
    Does `struct R { using receiver_concept = receiver_tag; };` satisfy `receiver`? Can it be connected with `just()`?

<details markdown="1">
<summary>Answer</summary>

It satisfies `receiver`: it has the tag, `get_env` defaults to returning `env<>{}`, and it can be moved without throwing.

But it can't be connected with `just()`. The completion signatures of `just()` are `completion_signatures<set_value_t()>`; *receiver-of* requires `set_value(R&&)` to be well-formed, but `R` has no `set_value` member, so the *Mandates* of [[exec.connect]] aren't met and the program is ill-formed. The same goes for `just_stopped()` and `just_error(x)`.
</details>

!!! question "2. Order of stop callback and completion"
    A sender constructs a stop callback object in `start`, and destroys it only in the operation state's destructor, after `set_value`. What does this violate? When does it actually cause trouble?

<details markdown="1">
<summary>Answer</summary>

It violates [exec.recv.concepts] ¶3: the token is valid only during the async lifetime, which ends when the completion operation begins, and Note 1 explicitly requires the callback to be destroyed before completion.

The trouble shows up when the token's provider destroys the stop source immediately after completion. For example, after the last child operation of `when_all` completes, `when_all` itself completes, and the enclosing code immediately destroys the whole operation state, including the `inplace_stop_source`. When the child operation state is then destroyed and deregisters its callback, it accesses stop state that has already been destroyed: a use after free.
</details>

## Summary

- `receiver`: the `receiver_concept` tag, a queryable `get_env`, nothrow move; `set_*` is not checked; can't be `final`.
- *receiver-of*: checks for each completion signature that `Tag(std::move(rcvr), args...)` can be called.
- `set_value`, `set_error` and `set_stopped` accept only non-const rvalue receivers, return `void`, and must be `noexcept`.
- The stop token is valid only during the async lifetime; callbacks must be deregistered before completion.
- `inlinable_receiver`: a receiver that can be rebuilt from the operation state's address, so the implementation needn't store it.
