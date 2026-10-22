---
title: Senders
summary: "The sender, sender_in and dependent_sender concepts; which completion signatures the default implementations of standard algorithms report, and on which domain and scheduler they complete; and the exposition-only skeleton needed to read every standard algorithm's specification: make-sender, basic-sender, basic-operation, basic-receiver, impls-for, plus helpers such as FWD-ENV and TRY-SET-VALUE."
updated: 2026-10-19
---

!!! tldr
    - `sender` only requires that a type declare itself a sender (or be an awaitable), have attributes, and be movable; `sender_in<S, Env>` is what says that the completion signatures can be computed at compile time in environment `Env`.
    - A sender whose signatures can't be computed without an environment is a dependent sender; it throws `dependent_sender_error` when no environment is given.
    - The signatures a standard algorithm reports are exactly the completions it may actually send, no more and no fewer; non-dependent senders check for type errors when they are constructed.
    - Conceptually, every standard sender has three parts (tag, data, child senders...) and can be taken apart with a structured binding; the type of the first element is `tag_of_t`.
    - Each algorithm's specification only needs to write the hooks in which `impls-for<Tag>` differs from the default implementation: *get-env*, *get-state*, *start*, *complete*, *check-types*.

The `std::execution` examples on this page have not been verified by compiling: the libc++ shipped with Clang 23 doesn't implement the sender library yet. The examples that demonstrate language rules were compiled with Clang 23.

[exec.snd] is the largest second-level subclause in chapter 33, and this site splits it into several pages. This page covers the sender concepts [exec.snd.concepts], the general rules [exec.snd.general] and the exposition-only entities [exec.snd.expos]; for the rest see:

- [[exec.cmplsig]]: `get_completion_signatures` and `completion_signatures`;
- [[exec.connect]]: `connect`;
- [[exec.snd.transform]]: domains, `transform_sender`, `apply_sender`;
- [[exec.as.awaitable]]: awaitable-related facilities;
- [[exec.factories]], [[exec.adapt]], [[exec.on]], [[exec.let]], [[exec.bulk]], [[exec.when.all]], [[exec.spawn]], [[exec.consumers]]: specific algorithms.

## Sender concepts [exec.snd.concepts]

### sender: a very weak concept (¶1, ¶4)

```cpp
template<class Sndr>
  concept is-sender = derived_from<typename Sndr::sender_concept, sender_tag>;

template<class Sndr>
  concept enable-sender = is-sender<Sndr> || is-awaitable<Sndr, env-promise<env<>>>;

template<class Sndr>
  inline constexpr bool enable_sender = enable-sender<Sndr>;

template<class Sndr>
  concept sender =
    enable_sender<remove_cvref_t<Sndr>> &&
    requires (const remove_cvref_t<Sndr>& sndr) { { get_env(sndr) } -> queryable; } &&
    move_constructible<remove_cvref_t<Sndr>> &&
    constructible_from<remove_cvref_t<Sndr>, Sndr>;
```

¶1 `sender` checks only three things: the type opts in (it declares a `sender_concept` member type, or it is an awaitable), `get_env` can obtain its attributes, and it can be moved. It doesn't check whether it can be connected, nor how it will complete.

The second branch of *enable-sender* makes every awaitable a sender automatically, as long as it can be `co_await`ed in a coroutine with an empty environment (*env-promise* is covered in [[exec.as.awaitable]]). Existing coroutine task types can therefore be used as senders without modification; at connect time they are wrapped by a coroutine ([[exec.connect]]).

¶4 Users can specialize `enable_sender` for types they define: true for a specialization that models `sender`, false for one that doesn't. The specialization must be usable in constant expressions and have type `const bool`. This is meant for third-party types to which a `sender_concept` member can't easily be added.

### sender_in: senders whose signatures can be computed

```cpp
template<class Sndr, class... Env>
  concept sender_in =
    sender<Sndr> && (sizeof...(Env) <= 1) && (queryable<Env> &&...) &&
    is-constant<get_completion_signatures<Sndr, Env...>()>;
```

`sender_in<Sndr, Env>` says that in environment `Env`, `get_completion_signatures<Sndr, Env>()` can be evaluated successfully at compile time. *is-constant* is a concept that accepts any non-type template argument and is always true; putting the call into a template argument forces it to be a constant expression.

`get_completion_signatures` is a `consteval` function that throws an exception when it hits a type error ([[exec.cmplsig]]). A call that throws isn't a constant expression, so `sender_in` is false. There is at most one environment; `sender_in<S>` means the signatures can be determined without an environment.

¶3 `sender_in` also has a semantic requirement. After connect and start, every completion operation that may be invoked must be a **permissible completion** ([[g:permissible-completion|permissible completion]]), that is, a completion whose signature appears in `completion_signatures_of_t<Sndr, Env>`. The declared set of signatures must cover the completions that can actually happen: declaring extra is fine, declaring too few isn't.

### dependent_sender (¶2)

```cpp
template<class Sndr>
  consteval bool is-dependent-sender-helper() try {
    get_completion_signatures<Sndr>();
    return false;
  } catch (dependent_sender_error&) {
    return true;
  }

template<class Sndr>
  concept dependent_sender =
    sender<Sndr> && bool_constant<is-dependent-sender-helper<Sndr>()>::value;
```

A sender that throws `dependent_sender_error` when `get_completion_signatures<Sndr>()` is called without an environment is a **dependent sender**. ¶2 A type that satisfies `sender` but not `dependent_sender` is a [[g:non-dependent-sender|non-dependent sender]] ([[exec.async.ops#13]]).

- The signature of `just(1)` is always `set_value_t(int)`; it is non-dependent, and `sender_in<decltype(just(1))>` is true.
- A user sender whose value type depends on the type of the scheduler in the environment should `throw dependent_sender_error()` from its environment-less `get_completion_signatures`, and return concrete signatures only from the version with an environment. It is a dependent sender: `sender_in<S>` is false, `sender_in<S, Env>` is true.
- `read_env(get_scheduler)`, read literally, is not a dependent sender; see [[exec.factories]].

### sender-to, sender-of, tag_of_t (¶1, ¶5–9)

```cpp
template<class Sndr, class Rcvr>
  concept sender-to =
    sender_in<Sndr, env_of_t<Rcvr>> &&
    receiver-of<Rcvr, completion_signatures_of_t<Sndr, env_of_t<Rcvr>>> &&
    requires (Sndr&& sndr, Rcvr&& rcvr) { connect(std::forward<Sndr>(sndr), std::forward<Rcvr>(rcvr)); };
```

The exposition-only concept *sender-to* is the full condition for being able to connect: the sender has signatures in the receiver's environment, the receiver accepts all of them, and `connect` is well-formed.

¶5 *sender-of*<Sndr, Values...> and *sender-in-of*<Sndr, Env, Values...> require the sender to have exactly one value completion signature, matching `set_value_t(Values...)`. For example, [[exec.sched#2]] uses *sender-in-of*<schedule_result_t<Sch>, Env> to require that a schedule sender complete with `set_value_t()`.

¶6 If `auto&& [tag, data, ...children] = sndr;` is well-formed, `tag_of_t<Sndr>` is `decltype(auto(tag))`; otherwise it is ill-formed. Every standard sender can be taken apart this way, and the first element is its **tag**, usually the type of the customization point object that created it, such as `then_t`. ¶7 *sender-for*<Sndr, Tag> says that `Sndr` is a sender produced by algorithm `Tag`; this is how domain customization recognizes senders ([[exec.snd.transform]]).

The following program simulates this layout with two plain structs, and uses a C++26 structured binding pack to collect the child senders into a pack:

```cpp run ok
#include <cstdio>

struct just_t {};
struct then_t {};
struct just_sender { just_t tag; int data; };
template<class F, class Child>
struct then_sender { then_t tag; F data; Child child; };

template<class Sndr>
void inspect(const Sndr& sndr) {
  auto& [tag, data, ...children] = sndr;   // structured binding introduces a pack
  (void)tag; (void)data;
  std::printf("%zu\n", sizeof...(children));
}

int main() {
  just_sender j{{}, 1};
  then_sender<int (*)(int), just_sender> t{{}, [](int x) { return x + 1; }, j};
  inspect(j);   // 0
  inspect(t);   // 1
}
```

¶8 *SET-VALUE-SIG*(T): `set_value_t()` if `T` is cv `void`, otherwise `set_value_t(T)`.

¶9 Standard library senders always provide a `connect` member that accepts an rvalue sender; only copyable senders provide a version that accepts an lvalue. So whether a sender can be reused depends on whether it can be copied: `just(std::make_unique<int>(1))` can only be connected once, after `std::move`.

## Completion behavior of standard algorithms [exec.snd.general]

### No more and no fewer signatures (¶1–2)

¶1 The algorithms in [[exec.factories]] and [[exec.adapt]] are all customizable, and each has a default implementation. Let `sndr` be the result of some algorithm's default implementation, and `rcvr` a receiver whose environment is `env`, such that *sender-to* holds. After connect and start, a set of completion operations with `rcvr` as their first argument will necessarily be invoked (in the potentially-evaluated sense).

¶2 Let `Sigs` be the signatures corresponding to those completion operations. The type of `get_completion_signatures<Sndr, Env>()` is exactly `completion_signatures` with `Sigs` as its arguments. If none of `Sigs` depends on `Env`, the version without an environment is also well-formed and gives the same result.

In other words, the signatures a standard algorithm reports are exactly the ones it may actually send. Downstream code relies on this entirely: `when_all` must check whether child senders have only one kind of value completion, and `sync_wait` computes its return type from them.

### Completion domains and completion schedulers (¶3–4)

¶3 Each kind of completion may happen on several different execution agents, depending on the algorithm's semantics, the receiver's environment and the completions of the child senders. For a completion tag `T` (`set_value_t` and so on), collect the domains associated with all agents that may execute a `T` completion, written `DsT`. If there is no `T` completion at all, `get_completion_domain<T>(get_env(sndr), env)` is ill-formed; otherwise its type is *COMMON-DOMAIN*<DsT...> (see below).

Example 1: the value completion domain of `sndr2 = then(sndr, fn)` is the same as that of `sndr`. If `fn` may throw, `sndr2`'s error completions have two sources: forwarding `sndr`'s error completions, or catching an exception thrown by `fn` where `sndr` completes with a value. So its error completion domain is the *COMMON-DOMAIN* of `sndr`'s value completion domain and error completion domain.

¶4 If `sndr` can determine that all `T` completions happen on execution agents of some scheduler `sch`, `get_completion_scheduler<T>(get_env(sndr), env)` is well-formed and has the type and value of `sch`; otherwise it is ill-formed.

Example 2: continuing the previous example, the value completion scheduler of `sndr2` is the value completion scheduler of `sndr` (if any). But `sndr2` can report an error completion scheduler only if `fn` can't throw or `sndr` has no error completions. Otherwise the error may happen on `sndr`'s value completion scheduler (when `fn` throws) or on its error completion scheduler, and those need not be the same.

### Constraints on customized implementations (¶5–6)

¶5 If a user-provided implementation is selected (through domain customization, [[exec.snd.transform]]) rather than the default implementation:

- ¶5.1 unless otherwise specified, any signature present that isn't in `Sigs` can only be an error or stopped completion. A customized implementation can't introduce new value completion types.
- ¶5.2 if `Sigs` doesn't depend on `Env`, the signatures obtained with and without an environment must be the same.

¶6 Some function templates in this subclause throw an *unspecified-exception*: its type is unspecified, and it can be caught by `catch (exception&)` but not by `catch (dependent_sender_error&)`. Note 1 adds that two such exceptions need not have the same type. They are thrown in the `consteval` `get_completion_signatures` to report type errors, such as a callback that can't be called with these values ([[exec.cmplsig]]).

## The exposition-only skeleton [exec.snd.expos]

The standard doesn't write out a sender class, receiver class and operation state class for each algorithm one by one. It first defines a general skeleton, *basic-sender*, and then has each algorithm specialize just one *impls-for*<Tag> to say how it differs from the default behavior. Once you understand this skeleton, each algorithm's specification is only a dozen or so lines.

### make-sender and basic-sender (¶23–26, ¶43–46)

```cpp
template<class Tag, class Data = see below, class... Child>
  constexpr auto make-sender(Tag tag, Data&& data, Child&&... child);
```

¶25 *make-sender* returns a prvalue of *basic-sender*<Tag, decay_t<Data>, decay_t<Child>...>, direct-list-initialized with the forwarded arguments. ¶26 Algorithms that need no data use the default `Data`: an unspecified, trivially copyable empty class.

¶43 The definition of *basic-sender*:

```cpp
template<class Tag, class Data, class... Child>
struct basic-sender : product-type<Tag, Data, Child...> {
  using sender_concept = sender_tag;
  using indices-for = index_sequence_for<Child...>;

  decltype(auto) get_env() const noexcept {
    auto& [_, data, ...child] = *this;
    return impls-for<Tag>::get-attrs(data, child...);
  }

  template<decays-to<basic-sender> Self, receiver Rcvr>
  auto connect(this Self&& self, Rcvr rcvr) noexcept(see below) -> basic-operation<Self, Rcvr> {
    return {std::forward<Self>(self), std::move(rcvr)};
  }

  template<decays-to<basic-sender> Self, class... Env>
  static constexpr auto get_completion_signatures();
};
```

So conceptually every standard sender is a three-part tuple (tag, data, child senders...). `then(sndr, f)` is `{then, f, sndr}`, `just(1, 2)` is `{just, product-type{1, 2}}`, and `when_all(a, b)` is `{when_all, {}, a, b}`. ¶44 Whether it is an aggregate is unspecified, ¶45 but it can always be used as the initializer of a structured binding, which `tag_of_t` relies on.

¶24 The *Mandates* of *make-sender* has four parts: `Tag` is `semiregular`; `Data` satisfies *movable-value*; each `Child` is a sender; and the result type `Sndr` satisfies `dependent_sender<Sndr> || sender_in<Sndr>`.

The last one means that non-dependent senders check for type errors when they are constructed. `then(just(1), [](std::string) {})` is ill-formed on the very line that calls `then`, rather than producing a template error dozens of levels deep at connect time. ¶24 also recommends that when `get_completion_signatures` fails because of an exception, the implementation include the exception's information in the diagnostic. C++26 allows throwing exceptions during constant evaluation, so a type error can be reported as an exception object carrying an explanation.

### Operation states: basic-state, basic-receiver, basic-operation (¶27–34)

`basic-sender::connect` returns a *basic-operation*. The skeletons of the three class templates are as follows (noexcept specifications and constraints omitted):

```cpp
template<class Sndr, class Rcvr>
struct basic-state {
  basic-state(Sndr&& sndr, Rcvr&& rcvr)
    : rcvr(std::move(rcvr)),
      state(impls-for<tag_of_t<Sndr>>::get-state(std::forward<Sndr>(sndr), rcvr)) {}
  Rcvr rcvr;
  state-type<Sndr, Rcvr> state;
};

template<class Sndr, class Rcvr, class Index>
struct basic-receiver {
  using receiver_concept = receiver_tag;
  template<class... Args> void set_value(Args&&... args) && noexcept {
    complete(Index(), op->state, op->rcvr, set_value_t(), std::forward<Args>(args)...);
  }
  // likewise for set_error and set_stopped
  auto get_env() const noexcept -> env-type<Index, Sndr, Rcvr> {
    return impls-for<tag-t>::get-env(Index(), op->state, op->rcvr);
  }
  basic-state<Sndr, Rcvr>* op;
};

template<class Sndr, class Rcvr>
struct basic-operation : basic-state<Sndr, Rcvr> {
  using operation_state_concept = operation_state_tag;
  connect-all-result<Sndr, Rcvr> inner-ops;
  basic-operation(Sndr&& sndr, Rcvr&& rcvr)
    : basic-state<Sndr, Rcvr>(std::forward<Sndr>(sndr), std::move(rcvr)),
      inner-ops(connect-all(this, std::forward<Sndr>(sndr), indices-for<Sndr>())) {}
  void start() & noexcept {
    auto& [...ops] = inner-ops;
    impls-for<tag-t>::start(this->state, this->rcvr, ops...);
  }
};
```

Taking `then` as an example, the memory layout looks like this:

```text
basic-operation<then's sender, R>
├── rcvr      : R                    outer receiver, moved in
├── state     : result of get-state  for then, just a copy of f
└── inner-ops : product-type<
        connect(child sender, basic-receiver<..., Index = 0>{this})   child operation state, embedded here
    >
```

- ¶30 *connect-all* connects the `i`-th child sender with `basic-receiver<..., integral_constant<size_t, i>>{op}` and collects the results in a *product-type*. A child receiver holds only one pointer, `op`, pointing back to the parent operation state; `Index` tells the parent which child completed.
- When a child operation completes it calls `basic-receiver::set_value(args...)`, which in turn calls `impls-for<Tag>::complete(Index, state, rcvr, set_value_t(), args...)`; what to do is up to the parent algorithm.
- When a child operation queries its environment, `basic-receiver::get_env` in turn calls `impls-for<Tag>::get-env(Index, state, rcvr)`; which environment the child sees is also up to the parent algorithm.

Storing only a pointer in the child receiver is safe: the child operation state is embedded in the parent operation state, and the parent operation state isn't moved or destroyed while the operation is in progress ([[exec.opstate]]).

!!! lawyer "In basic-state's initializer, rcvr refers to the parameter"
    *basic-state*'s constructor first initializes the member `rcvr` with `std::move(rcvr)`, then passes `rcvr` to *get-state*. The intent is clearly to pass the member that has already been moved into the operation state, so that references *get-state* keeps point inside the operation state; `continues_on`'s state, for example, stores an `Rcvr&` ([[exec.on]]). But in the expression of a member initializer, the name `rcvr` finds the constructor's parameter first, the very object that was moved from. Read literally, *get-state* gets a reference to the parameter, which dangles once the constructor returns.

    ```cpp run ok
    #include <cstdio>
    #include <utility>
    struct R { int id; };
    struct S {
      R* saved;
      explicit S(R& r) : saved(&r) {}
    };
    struct basic_state {
      basic_state(R&& rcvr) : rcvr(std::move(rcvr)), state(rcvr) {}
      R rcvr;
      S state;
    };
    int main() {
      basic_state b(R{1});
      std::printf("%d\n", b.state.saved == &b.rcvr);   // prints 0
    }
    ```

    Writing `this->rcvr` would match the intent. The exposition code only describes behavior, and implementations won't copy this defect.

### impls-for and default-impls (¶35–42)

¶35 *impls-for*<Tag> inherits from *default-impls* by default, which provides the default behavior of five hooks (some signature details omitted):

```cpp
struct default-impls {
  static constexpr auto get-env   = [](auto, auto&, const auto& rcvr) noexcept -> decltype(auto) {
    return FWD-ENV(get_env(rcvr));
  };
  static constexpr auto get-state = []<class Sndr, class Rcvr>(Sndr&& sndr, Rcvr& rcvr) noexcept -> decltype(auto) {
    auto& [_, data, ...child] = sndr;
    return allocator-aware-forward(std::forward_like<Sndr>(data), rcvr);
  };
  static constexpr auto start     = [](auto&, auto&, auto&... ops) noexcept -> void {
    (execution::start(ops), ...);
  };
  static constexpr auto complete  = []<class Index, class Rcvr, class Tag, class... Args>(
      Index, auto& state, Rcvr& rcvr, Tag, Args&&... args) noexcept -> void
      requires callable<Tag, Rcvr, Args...> {
    static_assert(Index::value == 0);
    Tag()(std::move(rcvr), std::forward<Args>(args)...);
  };
  template<class Sndr, class... Env> static consteval void check-types();
};
template<class Tag> struct impls-for : default-impls {};
```

The default behavior is plain pass-through:

| Hook | Default behavior | Typical override |
|---|---|---|
| *get-env* (¶36) | Pass the outer environment to children through *FWD-ENV* | `when_all` substitutes its own stop token; `write_env` merges in a new environment |
| *get-state* (¶37) | Store the data in the state, constructing with the allocator if there is one | `continues_on` connects the schedule sender in advance; `let_value` reserves space for the second operation |
| *start* (¶38) | Start all child operations in order | `just` completes directly; `when_all` registers a stop callback first |
| *complete* (¶39) | Forward the single child's completion unchanged to the outer receiver | `then` calls the callback; `when_all` counts |
| *check-types* (¶40–41) | Check that every child sender has signatures under *FWD-ENV-T*(Env) | `then` checks that the callback can be called |

¶41 The default *check-types* calls `get_completion_signatures` on each child sender in turn; if a child sender has a type error, so does the parent (the exception propagates upward). ¶42 Note 4 explains that *check-types* is either ill-formed, throws an exception, or is a core constant expression; when it is a core constant expression, the sender and environment types uniquely determine one set of signatures.

Every algorithm's specification reads "`impls-for<xxx_t>` inherits from *default-impls* and overrides a few of these". `just` overrides only *start* ([[exec.factories]]); `then` overrides only *complete* and *check-types* ([[exec.adapt]]).

### Signatures are read off the exposition code (¶47–49)

¶47 `basic-sender::get_completion_signatures` takes the first of `Env...` as the environment `E`, or `env<>` if there is none, and then evaluates *CHECK-TYPES*(), that is, `impls-for<Tag>::check-types<Sndr, E>()`:

- ¶47.1 if that is a core constant expression, the set of signatures is the signatures of the completion operations that are potentially evaluated when `op.start()` is called after connect;
- ¶47.2 otherwise the set of signatures is the empty `completion_signatures<>`. ¶49 In that case the function executes *CHECK-TYPES*() first, and the exception propagates, so the actual result is that computing the signatures fails.

¶48 *CHECK-TYPES*() must be a well-formed expression (*Constraints*).

This is an unusual way of specifying: the set of signatures isn't given by a type formula, but determined by which `set_*` calls the exposition code may actually make. Reading `then`'s *impls-for* and seeing `TRY-SET-VALUE(rcvr, invoke(fn, args...))`, you know it produces `set_value_t(result of invoke)`, plus `set_error_t(exception_ptr)` when `invoke` may throw.

!!! lawyer "env<> is used when no environment is given"
    Per ¶47, the environment-less `get_completion_signatures<Sndr>()` of a standard adaptor actually runs *check-types* with the empty environment `env<>`, and child senders are checked under *FWD-ENV-T*(env<>) as well. Yet ¶2 and [[exec.adapt.general#3]] ¶3.5 both suggest that dependence should propagate from child senders to the parent sender.

    Read literally, if a child sender throws an ordinary exception rather than `dependent_sender_error` in the empty environment, the parent sender is neither dependent nor satisfies `sender_in`. This is exactly the problem with `read_env` in [[exec.factories]]. Where dependent senders combine with standard adaptors, go by what implementations actually do and by later drafts.

!!! lawyer "Where did get-attrs go?"
    `basic-sender::get_env` calls `impls-for<Tag>::get-attrs`, but the *default-impls* of ¶35 has no such member, and the whole draft mentions it only in this one place. The attributes of a parent sender are actually specified by [[exec.adapt.general#3]] ¶3.2–3.3 and by [exec.snd.general] ¶3–4 on this page; go by those when reading the specification.

### Environment operations (¶4–10)

| Entity | Meaning | Used for |
|---|---|---|
| *FWD-ENV*(env) (¶4) | Answers only [[g:forwarding-query|forwarding queries]]; other queries are ill-formed. Its type is written *FWD-ENV-T*(Env) | Adaptors passing the environment to children |
| *MAKE-ENV*(q, v) (¶5) | Answers only query `q`, with result equal to `v` | Building a one-entry environment |
| *JOIN-ENV*(e1, e2) (¶6) | Asks `e1` first, then `e2` if `e1` can't answer | Overriding or extending an environment |
| *SCHED-ENV*(sch) (¶10) | `get_start_scheduler` returns a copy of `sch`; `get_domain` asks `sch` | Telling a child it is started on `sch` |

¶7 The results of the first three may vary with context: the same arguments can yield expressions of different types and value categories in different places. This leaves implementations latitude, for example whether to store a reference or a value.

¶8 *COMMON-DOMAIN*(domains...): if these domains have a common type (`common_type_t` is well-formed, for instance because one derives from another or the user specialized `common_type`), it is a value of the common type; otherwise it is the deduplicated `indeterminate_domain<Ds...>()`, meaning it can't be determined ([[exec.snd.transform]]).

¶9 *COMPL-DOMAIN*(Tag, sndr, envs): when `get_completion_domain<Tag>(get_env(sndr), envs...)` is well-formed or `envs` is empty, a default-constructed value of its type; otherwise `indeterminate_domain()`.

### Plugging ordinary calls into senders (¶11)

- *SET-VALUE*(rcvr, expr): `(expr, set_value(std::move(rcvr)))` if `expr` is `void`, otherwise `set_value(std::move(rcvr), expr)`.
- *TRY-EVAL*(rcvr, expr): if `expr` may throw, it is

    ```cpp
    try { expr; } catch(...) { set_error(std::move(rcvr), current_exception()); }
    ```

    otherwise just `expr`.
- *TRY-SET-VALUE*(rcvr, expr): *TRY-EVAL*(rcvr, *SET-VALUE*(rcvr, expr)), with `rcvr` evaluated only once.

This is the standard way of plugging an ordinary function call into a sender: compute the result and send it with `set_value`; if the computation throws, send it with `set_error(exception_ptr)`. The implementation of `then` is a single *TRY-SET-VALUE* ([[exec.adapt]]). `expr` is an argument of `set_value`, so evaluating it is part of that call and the `try` covers the whole call; `set_value` itself must be noexcept ([[exec.set.value]]), so any exception caught can only come from `expr`.

### Other helpers

¶12–14 *query-with-default*(tag, env, value): `tag(env)` if well-formed, otherwise `value`. ¶56–58 *call-with-default*(fn, value, args...): `fn(args...)` if well-formed, otherwise `value`. When the environment doesn't have something, a default is used; for example, when `on` gets the original scheduler and can't find one, it uses *not-a-scheduler* ([[exec.on]]).

¶15 *emplace-from*:

```cpp
template<callable Fun>
  requires is_nothrow_move_constructible_v<Fun>
struct emplace-from {
  Fun fun;
  using type = call-result-t<Fun>;
  constexpr operator type() && noexcept(nothrow-callable<Fun>) { return std::move(fun)(); }
  constexpr type operator()() && noexcept(nothrow-callable<Fun>) { return std::move(fun)(); }
};
```

Note 1: it is used to place non-movable types into a `tuple`, `optional` or `variant` in place. When the container constructs its element from the argument, the conversion function is called; it returns a prvalue, and guaranteed copy elision constructs the element directly. [[exec.opstate]] has a demonstration that compiles with Clang 23.

¶16 *on-stop-request*: holds an `inplace_stop_source&` and calls `request_stop()` when invoked. It is used as a stop callback: when the outer token has a stop requested, the request is forwarded to the inner stop source. `when_all` uses it to pass outer cancellation to all its children ([[exec.when.all]]).

¶17–22 *product-type*<T0, ..., Tn> is a lightweight tuple that supports structured bindings; its members `get<I>` and `apply` are implemented with C++26 structured binding packs:

```cpp
auto& [...ts] = self;                          // ¶19: structured binding introduces a pack
return std::forward_like<Self>(ts...[I]);      //      pack indexing
```

Note 2 explains that it is pseudo-code; an implementation in standard C++ must keep it an aggregate that can be used as a structured binding initializer. `auto& [_, data, ...child] = sndr;` is the most common unpacking idiom in all of [exec]; `_` is the C++26 placeholder name, which can be declared repeatedly.

¶54–55 *allocator-aware-forward*: when storing data in the operation state, if the receiver's environment provides an allocator (`get_allocator(get_env(rcvr))` is valid), the copy is created by uses-allocator construction (`make_obj_using_allocator`), element by element for a *product-type*; otherwise the data is forwarded unchanged. So when `just(std::vector<int>{...})` is connected in an environment that provides a pmr allocator, the vector in the operation state uses that allocator.

The rest:

- ¶50 *overload-set*<Fns...>: combines several lambdas into one overload set, commonly used to handle just one kind of signature and ignore the others.
- ¶51 *not-a-sender*: a sender that always throws when its signatures are computed. Transformation functions use it to say "can't be used here", with the error reported later when signatures are computed.
- ¶52 *not-a-scheduler*: a scheduler whose `schedule()` returns a *not-a-sender*, used as a placeholder default when no scheduler can be found.
- ¶53 *decay-copyable-result-datums*(cs): throws if some result datum can't be decay-copied. Algorithms that need to store results (`continues_on`, `when_all`, `into_variant`) use it as a check.
- ¶59–61 *inline-attrs*<Tag>: an attributes object that answers the completion scheduler with `get_scheduler(env)` and the completion domain with `get_domain(env)`, meaning "completes wherever the caller is". Senders that complete synchronously (`just`, the schedule sender of `inline_scheduler`) use it.

¶1–2 Whether standard library senders provide `affine()` and `as_awaitable(p)` members is unspecified; if they do, those must meet the semantics of the `affine` ([[exec.affine]]) and `as_awaitable` ([[exec.as.awaitable]]) algorithms. This lets implementations provide more efficient versions for specific senders; `just`, for example, never needs to switch schedulers.

## Questions

!!! question "1. An error at construction"
    At which step, and by which rule, does `auto s = then(just(1), [](std::string) {});` become ill-formed?

<details markdown="1">
<summary>Answer</summary>

`then` calls *make-sender*, and ¶24.4 requires `dependent_sender<Sndr> || sender_in<Sndr>`. `just(1)` is non-dependent; `then`'s *check-types* finds that the callback can't be called with an `int` (`int` doesn't implicitly convert to `std::string`) and throws an *unspecified-exception* ([[exec.adapt]]). So `get_completion_signatures<Sndr>()` isn't a constant expression, and `sender_in<Sndr>` is false. Nor is it a dependent sender, because what's thrown isn't `dependent_sender_error` ([exec.snd.general] ¶6). The *Mandates* isn't met, and the error appears on the line that constructs the sender, not at connect.
</details>

!!! question "2. Why does a child receiver store just one pointer?"
    *basic-receiver* has only one `basic-state*` member. Which guarantees of [[exec.async.ops]] does this rely on?

<details markdown="1">
<summary>Answer</summary>

Two. First, the child operation state is embedded in the parent operation state (*inner-ops* is a member of *basic-operation*), and the parent operation state isn't moved or destroyed during the async lifetime ([[exec.async.ops#7]], [[exec.opstate]]), so the pointer is valid for the child operation's entire lifetime. Second, a child operation, if started, always completes before its parent completes ([[exec.async.ops#2]] ¶2.5), so the parent is still alive when the child receiver is invoked.
</details>
