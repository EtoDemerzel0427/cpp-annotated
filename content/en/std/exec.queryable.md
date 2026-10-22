---
title: Queries and queryables
summary: "Environments and sender attributes are queryable objects: read-only tables keyed by query objects. q(env) calls env.query(q), prop builds a single key-value pair, and env merges several queryables in order."
updated: 2026-10-19
---

!!! tldr
    - A queryable object is a read-only key-value table whose keys are query objects (such as `get_stop_token`), looked up by type at compile time.
    - Writing a `query(Tag) const noexcept` member is enough to answer a query: `q(env)` is equivalent to `env.query(q)`.
    - A query's result can't be `void`, can't modify the environment, and stays valid as long as the queryable object is valid.
    - `prop(q, v)` makes an environment that answers only `q`; `env{a, b}` looks up in order, so queries `a` can answer shadow those of `b`.
    - Initialize `env` with braces; neither `prop` nor `env` is assignable.

A receiver's environment and a sender's attributes ([[exec.async.ops]]) are both queryable objects. They follow the same protocol ([exec.queryable]), and the standard also provides two tools for building them, `prop` and `env` ([exec.envs]). Clang 23's libc++ doesn't implement these facilities yet, and the examples below have not been compiled.

## What an environment looks like

```cpp title="my-env.cpp"
#include <execution>
#include <memory>
#include <stop_token>

struct my_env {
  std::stop_token token;
  std::allocator<int> alloc;

  auto query(std::get_stop_token_t) const noexcept { return token; }
  auto query(std::get_allocator_t) const noexcept { return alloc; }
};

void f(const my_env& e) {
  auto t = std::get_stop_token(e);     // calls e.query(get_stop_token)
  auto a = std::get_allocator(e);      // calls e.query(get_allocator)
  // std::execution::get_scheduler(e); // ill-formed: my_env doesn't answer this query
}
```

An environment doesn't use the fixed members of an ordinary struct because it has to be arbitrarily extensible. The library defines queries for stop tokens, allocators, schedulers and so on; users can define their own queries; and adaptors need to add one entry to an existing environment, or forward only some of its entries. A table keyed by query object type meets all these needs, and lookup happens at compile time.

A `query` member must be const and `noexcept`: standard queries always call it as const and require the call not to throw ([[exec.queries]]). A non-const `query` is never found at all, and a non-`noexcept` one makes the program ill-formed.

## Rules for queryable objects ([exec.queryable.general])

¶1 A **queryable object** ([[g:queryable-object|queryable object]]) is a read-only collection of key-value pairs where each key is a [[g:customization-point-object|customization point object]] known as a **query object**. A **query** is an invocation of a query object with a queryable object as its first argument and a (possibly empty) set of additional arguments. Each query can impose its own syntactic and semantic requirements on the invocation; for example, `get_stop_token` requires the result to satisfy `stoppable_token`.

¶2 Let `env` denote a queryable object `o` of type `O`, and let `cenv` denote the same object as `const O&`. Then `q(env, args...)` and `q(cenv, args...)` must give equal results. Querying through a non-const reference can't give a different answer.

¶3 The type of a query expression can't be `void`.

¶4 Queries are equality-preserving (the same inputs give equal results) and don't modify the query object or the arguments.

¶5 If `env.query(q, args...)` is well-formed, it is [[g:expression-equivalent]] to `q(env, args...)`. This is the customization mechanism: write a `query` member whose first parameter is the query object's type.

¶6 Unless otherwise specified, a query's result stays valid as long as the queryable object is valid. So a query can return a reference to data inside the queryable object.

## The queryable concept ([exec.queryable.concept])

```cpp
template<class T>
  concept queryable = destructible<T>;   // exposition only
```

¶1 Syntactically, the exposition-only *queryable* concept requires only `destructible`, which almost every object type satisfies.

¶2 The semantic requirement is: for any callable object `q`, whenever `q(env, args...)` is well-formed, the result satisfies the semantic requirements imposed by `q`.

What can be asked is decided entirely by the individual query objects; the concept itself lists no queries that must be supported. An empty struct is a valid environment too: queries on it are either ill-formed or take the query's default (for example, `get_stop_token` defaults to returning `never_stop_token`). The standard's empty environment is `env<>`.

## prop: one key-value pair ([exec.prop])

```cpp
template<class QueryTag, class ValueType>
struct prop {
  QueryTag query_;            // exposition only
  ValueType value_;           // exposition only

  constexpr const ValueType& query(QueryTag, auto&&...) const noexcept { return value_; }
};

template<class QueryTag, class ValueType>
  prop(QueryTag, ValueType) -> prop<QueryTag, unwrap_reference_t<ValueType>>;
```

¶1 `prop` builds a queryable object from a query object and a value. `prop(get_allocator, my_alloc{})` answers only `get_allocator`, and the answer is `my_alloc{}`. Example 1 in ¶3 passes it to `write_env` ([[exec.adapt]]) so that the environment a sender sees gains an allocator:

```cpp
template<sender Sndr>
sender auto parameterize_work(Sndr sndr) {
  auto e = prop(get_allocator, my_alloc{});
  return write_env(sndr, e);
}
```

A few details:

- `query` returns `const ValueType&`, referring to the value inside the `prop`, so the query result is valid as long as the `prop` is.
- The deduction guide uses `unwrap_reference_t`, so `prop(get_stop_token, std::ref(tok))` yields `prop<get_stop_token_t, inplace_stop_token&>`, which stores a reference rather than a copy (`tok` is an `inplace_stop_token`).
- `query` accepts and ignores any extra arguments.

¶2 `prop` requires that the query object can accept such a value: the *Mandates* is *callable*<QueryTag, *prop-like*<ValueType>>, where *prop-like* is a class with only `const ValueType& query(auto) const noexcept;`. So `prop(get_scheduler, 42)` is ill-formed {{ill-formed}}: `get_scheduler` requires the result to be a scheduler ([[exec.get.scheduler]]), and `int` isn't one. The error is reported where the `prop` is constructed, not much later when some algorithm queries it.

¶4 Specializations of `prop` are not assignable. Environments are read-only, so assignment makes no sense, and `ValueType` may be a reference.

## env: merging several queryables ([exec.env])

```cpp title="env-shadow.cpp"
namespace ex = std::execution;

auto base   = ex::env{ex::prop(ex::get_scheduler, sch_a), ex::prop(std::get_allocator, alloc)};
auto merged = ex::env{ex::prop(ex::get_scheduler, sch_b), base};

// ex::get_scheduler(merged) returns sch_b: the first subobject answers first
// std::get_allocator(merged) returns alloc: the first subobject doesn't answer, so base does
```

¶1 `env` builds one queryable object from several, and a query tries each subobject in turn, in lexical order.

¶6–8 Precisely, let *fe* be the first element among the subobjects for which `fe.query(q, args...)` is well-formed. The `query` member is constrained on at least one such element existing (¶7), and its effect is to return `fe.query(q, std::forward<Args>(args)...)` (¶8). ¶9 makes its `noexcept` match that of `fe.query(...)`.

So in `env{a, b}`, a query both can answer takes `a`'s answer. This is exactly the semantics needed to override one entry of an existing environment. Example 1 in ¶4 uses `env{prop(get_allocator, my_alloc{}), prop(get_scheduler, my_sched{})}` to provide two queries at once.

¶2 Specializations of `env` are not assignable.

¶3 Except for copy or move construction from another `env`, it is unspecified {{unspec}} whether `env` supports initialization with parentheses. `env` is described as a class with some members; an implementation may make it an aggregate (aggregates support parenthesized initialization since C++20), or may not. In practice, use braces: `env{a, b}`.

`env<>` is the empty environment with no subobjects. When an object has no `get_env` member, `get_env(o)` returns `env<>{}` ([[exec.get.env]]); the default environment argument of aliases such as `value_types_of_t<Sndr>` is also `env<>` ([[exec.cmplsig]]).

When specifying adaptors, the wording more often uses a few exposition-only operations from [[exec.snd]]: *FWD-ENV*(env) forwards only the queries for which `forwarding_query(q)` is true, *MAKE-ENV*(q, v) is like `prop(q, v)`, and *JOIN-ENV*(e1, e2) is like `env{e1, e2}`. `prop` and `env` are the public versions for users.

## Questions

!!! question "1. Why does env's query require at least one subobject to answer?"
    If the constraint in ¶7 were removed, what would happen with `env<>{}.query(get_scheduler)`?

<details markdown="1">
<summary>Answer</summary>

With the constraint, a query no subobject can answer doesn't take part in overload resolution, and `env.query(q)` is ill-formed. The query object can then fall back to its default behavior (such as `get_stop_token` returning `never_stop_token{}`), or the whole query is ill-formed in a way a `requires` expression can detect.

Without the constraint, `query` would always exist as a declaration and would only fail when its body is instantiated. Every way an adaptor has of detecting whether, say, a scheduler is in the environment would stop working.
</details>

!!! question "2. Can a query return a dangling reference?"
    `prop`'s `query` returns `const ValueType&`. Is it safe for an algorithm to write `auto& s = get_scheduler(get_env(rcvr));` and then store `s`?

<details markdown="1">
<summary>Answer</summary>

Not necessarily. ¶6 only guarantees that the result is valid as long as the queryable object is, and [[exec.get.env]] ¶2 only guarantees that the value of `get_env(o)` is valid as long as `o` is. If `get_env(rcvr)` returns a temporary environment object by value, `s` dangles once that full-expression ends.

The safe way is to store it by value: `auto s = get_scheduler(get_env(rcvr));`. Schedulers are required to be copyable ([[exec.sched]]), and copying one is cheap.
</details>
