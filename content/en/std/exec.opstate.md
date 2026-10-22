---
title: Operation states
summary: "The operation_state concept only requires that it can be started; destroying an operation state while the asynchronous operation is in progress is UB; copying or moving the operation state of a standard library sender is ill-formed; start(op) accepts only lvalues, can't throw, and must actually start the operation."
updated: 2026-10-19
---

!!! tldr
    - An operation state is the result of `connect(sndr, rcvr)` and holds all the data one asynchronous operation needs; only `start(op)` sets it running.
    - Destroying an operation state after the operation has started and before it completes is undefined behavior.
    - Operation states produced by standard library senders can be neither copied nor moved. Placing one somewhere relies on C++17's guaranteed copy elision.
    - `start(op)` rejects rvalues and must be noexcept; errors during start must be reported through the receiver's `set_error`.

The `std::execution` examples on this page have not been verified by compiling: the libc++ shipped with Clang 23 doesn't implement the sender library yet, so these examples carry no verdict. The examples that demonstrate language rules use a non-movable type to simulate an operation state, and were compiled with Clang 23.

## What an operation state is

A [[g:sender|sender]] is only a description of a piece of asynchronous work, and a [[g:receiver|receiver]] is where things go once the work completes. `connect(sndr, rcvr)` binds the two together, giving an [[g:operation-state|operation state]] object ([[exec.connect]]):

```cpp title="opstate.cpp"
namespace ex = std::execution;

auto op = ex::connect(ex::just(42), rcvr);   // nothing happens
ex::start(op);                               // only now does it start; just immediately calls rcvr's set_value
```

The receiver, the data the sender copied in, the states of all child operations, the linked-list pointers used for queuing: all of it lives inside the operation state. The caller owns it, and it can live on the stack, in a coroutine frame, or embedded in a parent operation's operation state. The shared state of a `std::future` must be allocated on the heap because the producer and the consumer each hold a share of it; an operation state has a single owner, so an entire sender chain can do without any dynamic allocation.

The price is that it must stay put. Once the operation starts, other places may hold pointers into it: it hangs in `run_loop`'s queue ([[exec.run.loop]]), a thread pool's work item points to it, and child operations' receivers store pointers to the parent operation state (*basic-receiver* in [[exec.snd]]). Moving it would leave all those pointers dangling. The rules below all follow from this.

## The operation_state concept [exec.opstate.general]

¶1 The concept itself has only two requirements: the type declares the `operation_state_concept` tag, and `start` can be called on an lvalue.

```cpp
template<class O>
  concept operation_state =
    derived_from<typename O::operation_state_concept, operation_state_tag> &&
    requires (O& o) {
      start(o);
    };
```

It doesn't require copyable, movable, or even destructible. Also, it checks `O::operation_state_concept` directly, rather than first removing references and cv-qualifiers as `sender` and `receiver` do: an operation state is always checked as the object type itself.

¶2 If an operation state object is destroyed during the lifetime of its asynchronous operation, the behavior is undefined {{ub}}. This is the same rule as [[exec.async.ops#7]], phrased in terms of the object. Note 1 adds that the concept places no requirements on operations other than destruction and `start` (including copying and moving), and invoking them on such an object may lead to UB.

¶3 If a program copies or moves (by construction or assignment) an operation state obtained by connecting a standard library sender, the program is ill-formed {{ill-formed}}. In practice these types simply delete their copy and move constructors.

| Operation state comes from | Copy, move |
|---|---|
| A standard library sender | Ill-formed, must be diagnosed |
| A sender you wrote yourself | Not the concept's business; even if the type allows moving, moving after start is very likely UB |

## How to hold a non-movable object

`connect` returns a prvalue. Since C++17, initializing an object of the same type from a prvalue doesn't create a temporary; the object is constructed directly at its destination. This is called guaranteed copy elision ([[class.copy.elision]]). So directly initializing a variable, or returning `connect(...)` from a function, needs no move constructor. The following uses a type with a deleted move constructor to simulate an operation state:

<div class="compare" markdown="1">

```cpp run ok
struct op_t {
  explicit op_t(int) {}
  op_t(op_t&&) = delete;
};
op_t connect(int x) { return op_t(x); }

op_t make() {
  return connect(1);   // OK: prvalue
}
int main() { [[maybe_unused]] op_t op = make(); }
```

```cpp run error
struct op_t {
  explicit op_t(int) {}
  op_t(op_t&&) = delete;
};
op_t connect(int x) { return op_t(x); }

op_t make() {
  op_t op = connect(1);
  return op;   // error: the move constructor is deleted
}
```

</div>

The right-hand version relies on named return value optimization (NRVO). NRVO is merely a copy the compiler is allowed to omit; the language still requires the move constructor to be usable, so it is ill-formed.

Putting one in a `std::optional` has the same problem. `opt.emplace(connect(...))` doesn't work: `emplace` takes its parameters by reference, so the argument is first materialized as a temporary, which is then used to move-construct the element. The *emplace-from* in the standard's exposition code ([[exec.snd]]) gets around this: what's passed in isn't an operation state but an object convertible to one. When `optional` constructs its element from it, the conversion function is called, and it returns a prvalue, bringing guaranteed copy elision back into play.

```cpp run ok
#include <optional>
struct op_t {
  explicit op_t(int) {}
  op_t(op_t&&) = delete;
};
op_t connect(int x) { return op_t(x); }

template<class F>
struct emplace_from {
  F fun;
  operator decltype(fun())() && { return static_cast<F&&>(fun)(); }
};
template<class F> emplace_from(F) -> emplace_from<F>;

int main() {
  std::optional<op_t> opt;
  // opt.emplace(connect(1));                       // error: needs move construction
  opt.emplace(emplace_from{[] { return connect(1); }});   // OK
}
```

`let_value` has to connect its second sender at run time, and this is how it puts the second operation state into a member ([[exec.let]]).

Likewise, `std::vector<op_t>` can't be used: growing it moves the existing elements, so neither `push_back` nor `emplace_back` compiles. When you need a group of operation states, use a fixed-size array, `std::list` or `std::deque` (whose `emplace_back` doesn't move existing elements), or, as `when_all` does, put all the child operation states in one aggregate and construct it in one go (*connect-all* in [[exec.snd]]).

## start [exec.opstate.start]

¶1 `start` is a customization point object (CPO) that starts the asynchronous operation associated with an operation state. There are three rules for `start(op)`:

- if `op` is an rvalue, `start(op)` is ill-formed {{ill-formed}};
- otherwise it is equivalent to `op.start()`, and the call is required not to throw (*MANDATE-NOTHROW*; ill-formed otherwise);
- the type of `op.start()` must be `void`.

Rvalues are banned because in `start(connect(s, r))` the temporary operation state is destroyed at the end of the full-expression, most likely before the operation has completed, which is exactly a violation of ¶2's lifetime rule. Stopping that at compile time beats leaving it as UB at run time.

noexcept is required because [[exec.async.ops#8]] requires an operation, once started, to complete exactly once. If `start` could throw, an operation could be started and never complete. Errors during start (a full thread-pool queue, a failed allocation) must be reported by calling `set_error` on the receiver.

¶2 If `op.start()` doesn't actually start the associated asynchronous operation, the behavior of calling `start(op)` is undefined {{ub}}. So a `start` member can't be an empty function, nor can it just make a note and wait for someone to call it again. Per [[exec.async.ops#7]], the async lifetime begins when the start operation begins executing, and from then on the operation must eventually complete.

After calling `start(op)`, there is only one thing left for the caller to do with `op`: destroy it once the completion operation has begun executing. It can't be `start`ed again ([[exec.async.ops#2]] says at most once), it can't be moved, and its internals can't be accessed after completion.

## Questions

!!! question "1. Starting twice"
    `auto op = connect(just(1), rcvr); start(op); start(op);` Which rule does this violate? Is it ill-formed or UB?

<details markdown="1">
<summary>Answer</summary>

It violates [[exec.async.ops#2]]: an operation is started at most once. On the first `start`, `just` has already completed synchronously, and the operation state became invalid along with it; the second `start` accesses an invalid operation state, which is UB per [[exec.async.ops#7]]. It can't be detected at compile time: both are valid `start` expressions on an lvalue.
</details>

!!! question "2. Why doesn't the concept require destructible?"
    `operation_state` doesn't require `destructible` the way `scheduler` does. Is that an oversight?

<details markdown="1">
<summary>Answer</summary>

No. The concept expresses only the interface "can be started". When it may be destroyed is a lifetime matter, constrained by ¶2 and [[exec.async.ops#7]]; a concept can't express "may only be destroyed after a certain point". Operation states are almost always destroyed implicitly as local variables or members, and `destructible` provides no useful information about them. In practice, operation states all have noexcept destructors.
</details>
