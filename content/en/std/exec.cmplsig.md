---
title: Completion signatures
summary: "completion_signatures encodes a sender's possible completions as a type; get_completion_signatures is a consteval function that reports type errors, or the need for an environment, by throwing; aliases such as value_types_of_t extract types from the set of signatures."
updated: 2026-10-19
---

!!! tldr
    - How a sender may complete is written down at compile time as the type `completion_signatures<...>`, each entry being `set_value_t(Vs...)`, `set_error_t(E)` or `set_stopped_t()`.
    - `value_types_of_t`, `error_types_of_t` and `sends_stopped` extract types from the set of signatures by kind; this is how the return type of `sync_wait` is computed.
    - `get_completion_signatures<Sndr, Env>()` is a `consteval` function: it first transforms the sender by domain, then calls the sender's static member function template, and throws an exception when no signatures can be obtained.
    - When no signatures can be obtained without an environment, it throws `dependent_sender_error`, meaning the sender depends on the environment; when they still can't be obtained with an environment, that's a genuine type error.
    - The declared signatures must cover every potentially evaluated completion; the set obtained without an environment may be larger than the one with an environment, but the extras can only be error or stopped completions.

This page covers the type level of `std::execution`. Examples that use the C++26 sender library have not been verified by compiling, because the libc++ shipped with Clang 23 doesn't implement this part of the library yet; examples that only demonstrate language mechanisms were verified with Clang 23.

## Why the completions need to be known at the type level

[[exec.async.ops#13]] specifies that all the possible completions of an asynchronous operation are determined jointly by the sender type and the type of the receiver's environment. Each possible completion is written as a function type, called a [[g:completion-signature|completion signature]].

Almost every algorithm needs to know these signatures at compile time:

- `sync_wait` has to decide to return `optional<tuple<what>>`;
- `when_all` has to decide what kind of tuple to store each child's results in;
- `let_value` has to know what the callback will receive and which kind of sender it will return, to reserve space in the operation state;
- `connect` has to check that the receiver accepts every kind of completion.

All of this happens at compile time, with no type erasure at run time.

## completion_signatures ([exec.cmplsig])

¶1 `completion_signatures` is a class template that encodes a set of completion signatures. ¶2 Example 1 is a sender that declares five kinds of completion:

```cpp
struct my_sender {
  using sender_concept = sender_tag;
  using completion_signatures =
    execution::completion_signatures<
      set_value_t(), set_value_t(int, float),
      set_error_t(exception_ptr), set_error_t(error_code),
      set_stopped_t()>;
};
```

This means: for a receiver `rcvr`, it will call one of `set_value(rcvr)`, `set_value(rcvr, int{…}, float{…})`, `set_error(rcvr, exception_ptr{…})`, `set_error(rcvr, error_code{…})` and `set_stopped(rcvr)`.

¶3–4 Only function types of three forms can be template arguments:

- ¶4.1 `set_value_t(Vs...)`, where `Vs` are object types or reference types;
- ¶4.2 `set_error_t(Err)`, where `Err` is an object type or reference type;
- ¶4.3 `set_stopped_t()`.

### Iterating over signatures: count-of and for-each (¶8–9)

¶8 `completion_signatures` has two exposition-only static members; user code can't call them, but the specifications of standard algorithms use them heavily.

¶9 *count-of*(tag) counts how many signatures have return type `Tag`. *for-each*(fn) calls `fn(static_cast<Fn*>(nullptr))` once for each signature `Fn`, passing a null function pointer. This is a way of passing types as values: write `fn`'s parameter as `set_value_t(*)(Ts...)`, and template argument deduction extracts `Ts...`.

```cpp
// then's type checking ([exec.then]), slightly simplified
auto cs = get_completion_signatures<child-type<Sndr>, FWD-ENV-T(Env)...>();
auto fn = []<class... Ts>(set_value_t(*)(Ts...)) {
  if constexpr (!invocable<remove_cvref_t<data-type<Sndr>>, Ts...>)
    throw unspecified-exception();
};
cs.for-each(overload-set(fn, [](auto){}));   // check only value signatures, ignore the rest
```

### Extracting types by kind (¶5–8)

¶8 The standard provides three public tools for extracting types from a set of signatures by kind:

```cpp
template<class Sndr, class Env = env<>,
         template<class...> class Tuple = decayed-tuple,
         template<class...> class Variant = variant-or-empty>
  using value_types_of_t = /* each value signature's arguments put into Tuple, all of those into Variant */;

template<class Sndr, class Env = env<>,
         template<class...> class Variant = variant-or-empty>
  using error_types_of_t = /* each error type put into Variant */;

template<class Sndr, class Env = env<>>
  constexpr bool sends_stopped = /* whether there is a set_stopped_t() */;
```

`decayed-tuple<Ts...>` is `tuple<decay_t<Ts>...>`. *variant-or-empty*<Ts...> is `variant<decay_t<Ts>...>` with duplicate types removed; with no types at all, it is an empty class that can't be constructed ([[execution.syn]]).

Taking the signatures of `my_sender` as an example (assuming its signatures can be read correctly; see below):

| Expression | Result |
|---|---|
| `value_types_of_t<S>` | `variant<tuple<>, tuple<int, float>>` |
| `value_types_of_t<S, env<>, tuple, type_list>` | `type_list<tuple<>, tuple<int, float>>` |
| `error_types_of_t<S>` | `variant<exception_ptr, error_code>` |
| `sends_stopped<S>` | `true` |

`sync_wait` computes its return type with `value_types_of_t<Sndr, sync-wait-env, decayed-tuple, type_identity_t>` ([[exec.consumers]]). `type_identity_t` accepts only one template argument, so when the sender has more than one value signature this type is ill-formed; that's how `sync_wait`'s requirement of exactly one value completion is enforced.

¶5–7 All three aliases are based on the exposition-only *gather-signatures*<Tag, Completions, Tuple, Variant>: it picks out the signatures whose return type is `Tag`, hands the parameter type pack `Tsn` of the n-th signature to `Tuple`, then hands all the results to `Variant`, giving `Variant<Tuple<Ts0...>, Tuple<Ts1...>, ...>`. Note 1 explains that it instantiates the templates indirectly through *META-APPLY* so that non-variadic templates such as `optional` and `type_identity_t` can serve as `Tuple` or `Variant`.

## get_completion_signatures ([exec.getcomplsigs])

```cpp
template<class Sndr, class... Env>
  consteval auto get_completion_signatures() -> valid-completion-signatures auto;

template<class Sndr, class... Env>
  requires sender_in<Sndr, Env...>
using completion_signatures_of_t = decltype(get_completion_signatures<Sndr, Env...>());
```

This is a `consteval` function template with no function arguments, returning an object of a specialization of `completion_signatures` (an empty object; all the information is in its type). ¶2 There is at most one environment.

### Reporting errors by throwing

Writing signature computation as a `consteval` function means ordinary `if constexpr` and loops can be used, and, more importantly, exceptions can be thrown. C++26 allows throwing exceptions during constant evaluation; when an exception isn't caught, the evaluation isn't a constant expression ([[expr.const]]), and concepts such as `sender_in` are false as a result ([[exec.snd]]). Compilers can also show the information carried by the exception object in the diagnostic.

The following example doesn't depend on the sender library; it only demonstrates the language mechanism:

```cpp run ok
#include <exception>
#include <type_traits>

struct needs_env : std::exception {};

template<class... Env>
consteval int signatures() {
  if constexpr (sizeof...(Env) == 0)
    throw needs_env();   // no environment: report "needs an environment"
  else
    return 1;
}

template<class... Env>
concept known = requires {
  typename std::integral_constant<int, signatures<Env...>()>;
};

static_assert(!known<>);     // a call that throws is not a constant expression
static_assert(known<int>);
int main() {}
```

### Lookup order (¶1, ¶3)

¶1 First some notation:

- *get-complsigs*<Sndr, Env...>() calls the sender's static member function template `remove_reference_t<Sndr>::template get_completion_signatures<Sndr, Env...>()`. The first template argument is the sender type itself, complete with reference and cv-qualifiers, so the same sender can give different signatures for lvalues and rvalues.
- `NewSndr`: with an environment, the type of `transform_sender(declval<Sndr>(), declval<Env>()...)`, that is, the sender transformed by domain first ([[exec.snd.transform]]). What this gives is the signatures of the sender that will actually be connected. Without an environment it's just `Sndr`.
- *CHECKED-COMPLSIGS*(e): if `e` is a core constant expression whose type is a valid set of signatures, it is `e` itself; otherwise `e` is evaluated first (any exception it throws propagates as usual), and if that doesn't throw, an unspecified exception derived from `exception` is thrown.

¶3 `get_completion_signatures` tries, in order:

- ¶3.1 calling the sender's static member with the environment;
- ¶3.2 calling the sender's static member without the environment, for senders whose signatures don't depend on the environment;
- ¶3.3 if `NewSndr` is an awaitable (can be `co_await`ed), the signatures are fixed as `set_value_t(result of await)`, `set_error_t(exception_ptr)`, `set_stopped_t()` ([[exec.as.awaitable]]);
- ¶3.4 if none of these works and no environment was provided: throw `dependent_sender_error` (or a type publicly and unambiguously derived from it);
- ¶3.5 if none of these works but an environment was provided: throw an unspecified exception.

¶3.4 and ¶3.5 both mean the signatures can't be obtained, but they mean different things. Failing without an environment may just be because the signatures depend on the environment and can be determined once one is given; failing even with an environment is a genuine error.

### Senders that depend on the environment

`dependent_sender_error` is the only public exception type in this chapter, used specifically to express "needs an environment" during signature computation. A sender of your own that depends on the environment can be written like this:

```cpp title="dependent-sender.cpp"
namespace ex = std::execution;

struct current_scheduler_sender {   // completes with the environment's scheduler, like read_env(get_scheduler)
  using sender_concept = ex::sender_tag;

  template<class Self, class... Env>
  static consteval auto get_completion_signatures() {
    if constexpr (sizeof...(Env) == 0) {
      throw ex::dependent_sender_error();   // environment unknown, can't determine the value type
    } else {
      using Sch = decltype(ex::get_scheduler(std::declval<const Env&>()...));
      return ex::completion_signatures<ex::set_value_t(Sch)>{};
    }
  }
  // ... connect ...
};
```

`if constexpr` instantiates only one branch. When `Env` is empty, the instantiated branch has no `return`, and the return type is deduced as `void`. That doesn't matter: this call always ends with an exception, and *CHECKED-COMPLSIGS* lets the exception propagate unchanged.

### Discrepancy between Example 1 and the normative text

Example 1 declares its signatures with a member type alias `completion_signatures`. But the normative text of ¶1 and ¶3 only looks for a static member function template `get_completion_signatures`, not a type alias. Working it through literally, `my_sender` has no such member function template and isn't an awaitable, so `get_completion_signatures<my_sender>()` reaches ¶3.4 and throws `dependent_sender_error`.

Examples aren't normative. In new code, provide the static member function template:

```cpp
struct my_sender {
  using sender_concept = std::execution::sender_tag;
  template<class Self, class... Env>
  static consteval auto get_completion_signatures() {
    return std::execution::completion_signatures<
      std::execution::set_value_t(int), std::execution::set_stopped_t()>{};
  }
  // ... connect ...
};
```

## Two requirements on signatures (¶4–5)

¶4 If `completion_signatures_of_t<Sndr>` and `completion_signatures_of_t<Sndr, Env>` are both well-formed, the former must be a superset of the latter, and the extras can only be error or stopped completions. Without knowing the environment only a conservative estimate is possible; once the environment is known some possibilities can be ruled out. For example, if the environment's stop token is `never_stop_token`, `set_stopped_t()` can be dropped, but no new value types may appear.

¶5 If a sender or its operation state makes some completion call `CSO(rcvr, args...)` **potentially evaluated** ([[basic.def.odr]]: it appears in code that will be instantiated, whether or not it is actually reached at run time), the set of signatures must contain a matching signature. In other words, the declared signatures must cover every completion that can happen; this is the sender author's side of the obligation for the permissible completions in [[exec.snd.concepts#3]].

"Potentially evaluated" is broader than what actually executes at run time. Even if a `set_error` is in a branch that is never reached at run time, as long as the code containing it is instantiated, there must be a corresponding signature. Conversely, using `if constexpr` to keep impossible branches from being instantiated shrinks the set of signatures. That is exactly why the exposition code of standard algorithms has so many `if constexpr (!nothrow)`: only when some operation may throw does `set_error(..., current_exception())` appear, and only then do the signatures include `set_error_t(exception_ptr)`.

## Questions

!!! question "1. Why does the first template argument carry a reference?"
    *get-complsigs* passes `Sndr` (which may be `S&`, `const S&` or `S`) unchanged to the sender's static member. What is that for?

<details markdown="1">
<summary>Answer</summary>

The same sender may send its results differently when connected as an lvalue and as an rvalue. For example, a sender that stores a `std::string` can move the string into the operation state when connected as an rvalue; when connected as an lvalue it can only copy it, or send a `const std::string&` referring to its own storage. For the signatures to reflect these differences faithfully, they have to know the value category with which the sender is connected.

In addition, [[exec.snd.concepts#9]] specifies that standard library senders provide lvalue connect only when they are copyable, in which case computing signatures for `S&` should also fail.
</details>

!!! question "2. Can the set of signatures be larger than reality?"
    A sender declares `set_error_t(exception_ptr)`, but in fact never completes with an error. Does that break the rules?

<details markdown="1">
<summary>Answer</summary>

Not for a user-written sender. ¶5 only requires that the completions that can happen be covered, a one-way inclusion. The cost falls downstream: `sync_wait` still has to be ready to handle an exception, `when_all`'s error `variant` gains an alternative, and `spawn` doesn't accept senders that may complete with an error at all ([[exec.spawn]]).

The default implementations of standard algorithms are held to a stricter requirement: [[exec.snd.general#2]] requires the set of signatures to correspond exactly to the potentially evaluated completions. [[exec.adapt.general#4]] also explicitly allows implementations to omit the `exception_ptr` error signature when they determine it won't be sent.
</details>

## Summary

| Facility | Purpose |
|---|---|
| `completion_signatures<Fns...>` | A set of signatures, each `set_value_t(Vs...)`, `set_error_t(E)` or `set_stopped_t()` |
| `value_types_of_t`, `error_types_of_t`, `sends_stopped` | Extract types by kind; `Tuple` and `Variant` are replaceable |
| `get_completion_signatures<Sndr, Env>()` | Transforms the sender first, asks its static member, then falls back to the environment-less version and to awaitables |
| `dependent_sender_error` | Thrown when the signatures can't be obtained without an environment, meaning the sender depends on it |
| ¶4 | The environment-less set of signatures is a superset of the one with an environment; the difference can only be errors or stopped |
| ¶5 | The signatures must cover every potentially evaluated completion |
