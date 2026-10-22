---
title: Domains and sender transforms
summary: "How algorithms are customized: before connect, transform_sender rewrites the sender first by the domain where the predecessor completes and then by the domain where the operation starts, repeating each stage until nothing changes; default_domain calls the rewrite the sender's tag provides; indeterminate_domain means the domain can't be determined; apply_sender customizes consumers such as sync_wait."
updated: 2026-10-19
---

!!! tldr
    - An execution domain is an empty tag type associated with an execution resource, used to decide which implementation of a standard algorithm to use.
    - Customization happens at connect: `transform_sender(sndr, env)` first rewrites the sender by the predecessor's completion domain, then by the start domain of the receiver's environment; each stage rewrites repeatedly until the type stops changing.
    - `default_domain` calls the `transform_sender` provided by the sender's tag type. The standard uses it to rewrite `starts_on`, `on`, `bulk`, `stopped_as_optional` and others into more basic algorithms.
    - When some kind of completion can happen in several domains that can't be unified, the result is `indeterminate_domain`: only the default implementation can be used, and the program is ill-formed if some domain provides a different rewrite.
    - `apply_sender` customizes algorithms that don't return a sender, such as `sync_wait`.

The examples on this page have not been verified by compiling: the libc++ shipped with Clang 23 doesn't implement the sender part of `std::execution` yet, so they carry no verdict.

## Who decides which implementation to use

`then`, `bulk` and `when_all` all have default implementations ([[exec.snd]]), but the default isn't always the best. A GPU scheduler wants `bulk` to become a single kernel launch rather than a loop on one thread; a thread pool wants to split `bulk` into several tasks. The question is who chooses the implementation, and when:

- It can't be chosen when `bulk(sndr, ...)` is called: at that point it's not yet known where it will run.
- `bulk` can't choose for itself: it doesn't know every execution resource.

The draft's answer is the **execution domain** ([[g:execution-domain]]): each execution resource is associated with an empty tag type. At `connect`, `transform_sender(sndr, get_env(rcvr))` is called first, rewriting the sender into another sender according to the relevant domains, and then the result of the rewrite is connected ([[exec.connect]]). Customizing an algorithm means providing `transform_sender` in your own domain, recognizing senders such as `bulk_chunked`, and returning a sender you implemented yourself.

A sender deals with execution resources in two places, so there are two kinds of domain:

- **Completion domain**: where the predecessor completes. For `bulk(sndr, ...)`, that's where `sndr` completes, and `bulk`'s work starts right there. It is answered by the `get_completion_domain` query on the sender's attributes ([[exec.get.compl.domain]]).
- **Start domain**: where the sender itself is started. It is answered by the `get_domain` query on the receiver's environment ([[exec.get.domain]]).

`transform_sender` uses both.

## transform_sender [exec.snd.transform]

```cpp
template<sender Sndr, queryable Env>
  constexpr decltype(auto) transform_sender(Sndr&& sndr, const Env& env) noexcept(see below);
```

¶1 The start domain is the type of `get_domain(env)`; if that query is ill-formed, `default_domain` is used.

¶2 The completion domain of a sender `s` is the type of `get_completion_domain<>(get_env(s), env)`. With an empty template argument list it asks for the value completion domain. If the query is ill-formed, `default_domain` is used here too.

¶3 One rewrite step: first try `dom.transform_sender(tag, s, env)`, and if that is ill-formed fall back to `default_domain().transform_sender(tag, s, env)`. So a custom domain always comes before the default rewrite.

Repeated rewriting: if the result of this step has the same type as `s` (ignoring cv), stop; otherwise do another step on the result `s2`. The domain used for the next step is still the start domain in the start stage, and is `s2`'s completion domain in the completion stage.

The whole process has two stages:

```text
Stage 1 (tag set_value): rewrite sndr repeatedly by the predecessor's completion domain until it stops changing, giving tmp
Stage 2 (tag start)    : rewrite tmp repeatedly by the start domain of the receiver's environment until it stops changing, giving final
connect(final, rcvr)
```

¶4 Returns the result of stage 2. ¶5 Its noexcept matches that of the whole rewriting process.

The first argument, `tag`, is `set_value` or `start`, telling the domain which stage it's in; a domain can step in during only one of the stages. Most of the rewrites that come with standard algorithms accept only `set_value`, that is, they choose the implementation by where the predecessor completes.

The point of repeated rewriting is that the result of a rewrite can itself be rewritten. In the default domain `bulk` is first rewritten into `bulk_chunked` ([[exec.bulk#4]]), and in `parallel_scheduler`'s domain `bulk_chunked` is then rewritten into a sender that calls the backend ([[exec.par.scheduler#11]]). Thanks to this step, a GPU domain needn't know about `bulk` at all, only `bulk_chunked` and `bulk_unchunked`.

## default_domain [exec.domain.default]

```cpp
struct default_domain {
  template<class Tag, sender Sndr, queryable Env>
    static constexpr decltype(auto) transform_sender(Tag, Sndr&& sndr, const Env& env) noexcept(see below);
  template<class Tag, sender Sndr, class... Args>
    static constexpr decltype(auto) apply_sender(Tag, Sndr&& sndr, Args&&... args) noexcept(see below);
};
```

¶2–4 `transform_sender(tag, sndr, env)`: if `tag_of_t<Sndr>().transform_sender(Tag(), sndr, env)` is well-formed, return that; otherwise return `sndr` unchanged. `tag_of_t<Sndr>` is the sender's tag type, usually the type of the customization point object that created it, such as `bulk_t` ([[exec.snd]]).

That is, an algorithm's tag type can carry a `transform_sender` member providing a default rewrite. The standard uses this to express many algorithms as compositions of others:

| Algorithm | Rewritten to | Source |
|---|---|---|
| `starts_on(sch, s)` | `let_value(continues_on(just(), sch), [s]{ return s; })` | [[exec.on]] |
| `on(sch, s)` | `continues_on(starts_on(sch, s), original scheduler)` | [[exec.on]] |
| `bulk(s, pol, n, f)` | `bulk_chunked(s, pol, n, function calling f per element)` | [[exec.bulk]] |
| `when_all_with_variant(s...)` | `when_all(into_variant(s)...)` | [[exec.when.all]] |
| `stopped_as_optional(s)` | `let_stopped(then(s, wrap in optional), return empty optional)` | [[exec.adapt]] |
| `stopped_as_error(s, e)` | `let_stopped(s, return just_error(e))` | [[exec.adapt]] |
| `let_value(s, f)` etc. | Replaced by the internal *let-tag* sender | [[exec.let]] |
| `affine(s)` | `s.affine()` or `continues_on(s, start scheduler)` | [[exec.affine]] |

A custom domain that wants to implement `starts_on` directly only has to recognize `starts_on_t` first in its own `transform_sender`. ¶3 asks `dom` first and falls back to `default_domain` only if `dom` doesn't handle it.

¶5–8 `apply_sender(tag, sndr, args...)` is equivalent to `Tag().apply_sender(sndr, args...)`, and requires that expression to be well-formed (*Constraints*).

## indeterminate_domain [exec.domain.indeterminate]

```cpp
template<class... Domains>
struct indeterminate_domain {
  indeterminate_domain() = default;
  constexpr indeterminate_domain(auto&&) noexcept {}
  template<class Tag, sender Sndr, queryable Env>
    static constexpr decltype(auto) transform_sender(Tag, Sndr&& sndr, const Env& env) noexcept(see below);
};
```

`when_all(a, b)` completes wherever the last of `a` and `b` to complete is. If `a` is on a GPU and `b` on a thread pool, the completion domain of `when_all` can't be determined. In that case *COMMON-DOMAIN* ([[exec.snd]]) first tries the `common_type` of these domains; if there is no common type, the result is `indeterminate_domain<Ds...>`.

¶2 *Mandates*: for each `D` in `Domains...`, `D().transform_sender(Tag(), sndr, env)` is either ill-formed or has, after decay, the same type as the result of `default_domain`'s rewrite.

¶3 Returns `default_domain().transform_sender(Tag(), sndr, env)`.

Since it isn't known which domain the completion will happen in, only the default implementation can be used. If one of the domains has a different customization for this sender, the program is ill-formed {{ill-formed}}, rather than one being picked arbitrarily. This way the same program never takes different algorithm implementations depending on which child operation happens to finish first.

¶4 `indeterminate_domain` takes part in `common_type` computations: the common type of two `indeterminate_domain`s is the merged, deduplicated `indeterminate_domain`; the common type of the empty `indeterminate_domain<>` and any `D` is `D`; the common type of a non-empty one and `D` adds `D` to it. The converting constructor lets any domain convert to it.

## apply_sender [exec.snd.apply]

```cpp
template<class Domain, class Tag, sender Sndr, class... Args>
  constexpr decltype(auto) apply_sender(Domain dom, Tag, Sndr&& sndr, Args&&... args) noexcept(see below);
```

¶1–4 If `dom.apply_sender(Tag(), sndr, args...)` is well-formed, it is used; otherwise `default_domain().apply_sender(...)`, that is, `Tag().apply_sender(sndr, args...)`. The whole expression must be well-formed (*Constraints*).

`transform_sender` rewrites senders; `apply_sender` customizes consumers, algorithms that don't return a sender. `sync_wait(sndr)` is equivalent to `apply_sender(Domain(), sync_wait, sndr)`, where `Domain` is `sndr`'s value completion domain ([[exec.sync.wait#4]]). A GPU domain can therefore provide its own `sync_wait` that waits directly on a device stream synchronization instead of driving a `run_loop`.

## What a custom domain looks like

```cpp title="my-domain.cpp"
namespace ex = std::execution;

struct gpu_domain {
  template<class Sndr, class Env>
    requires std::same_as<ex::tag_of_t<Sndr>, ex::bulk_chunked_t>
  static auto transform_sender(ex::set_value_t, Sndr&& sndr, const Env& env) {
    auto&& [_, data, child] = sndr;
    auto&& [policy, shape, f] = data;
    return gpu_bulk_sender{std::forward_like<Sndr>(child), shape, f};   // a sender we implement ourselves
  }
};

class gpu_scheduler {
public:
  using scheduler_concept = ex::scheduler_tag;
  // have the scheduler report its value completion domain:
  auto query(ex::get_completion_domain_t<ex::set_value_t>) const noexcept { return gpu_domain{}; }
  // ...
};
```

At connect, `ex::schedule(gpu) | ex::bulk(ex::par, n, f)` is rewritten like this:

1. In stage 1, `bulk`'s completion domain is determined by the predecessor `schedule(gpu)`, and is `gpu_domain`. `gpu_domain` doesn't handle `bulk_t`, so it falls back to `default_domain`, and `bulk_t::transform_sender` rewrites it into `bulk_chunked`.
2. The type changed, so rewriting continues. `gpu_domain` recognizes `bulk_chunked` and rewrites it into `gpu_bulk_sender`.
3. One more rewrite leaves the type unchanged, and stage 1 ends.

!!! pitfall "Customization can't change value signatures"
    Per [[exec.snd.general#5]], when a user-provided implementation is selected, the only signatures it may add over the default implementation are error or stopped completions. So `gpu_bulk_sender` may add a `set_error_t(cuda_error)`, but can't change the value completion from `set_value_t(int)` to `set_value_t(long)`: downstream code has already done its type computations from the default implementation's signatures before connect.

!!! pitfall "Customization doesn't happen at construction"
    `auto s = bulk(sndr, par, n, f);` gives you the standard sender, and no domain is involved yet. Inspecting the type of `s`, or handing `s` to a consumer that bypasses `connect`, shows no effect of customization. Rewriting happens only inside `connect`, and also first when signatures are computed with an environment ([[exec.getcomplsigs#1]]).

<details class="fine" markdown="1"><summary>Remaining wording</summary>

When ¶3 defines repeated rewriting, it writes the result of one rewrite step as *transformed-sender*, which doesn't match the name *transformed-sndr* defined earlier; they obviously mean the same thing.

The rewrites of `let_*` and `affine` are written in their own subclauses in a form without a tag (`let-cpo.transform_sender(s, es...)`, see [[exec.let#6]] and [[exec.affine#5]]), which doesn't match the form `transform_sender(Tag(), sndr, env)` that `default_domain` calls; this is also a wording discrepancy.

The domain mechanism when P2300 was first merged (early customization, late customization) differs from the current wording. The current wording introduces completion domains, two-stage rewriting and `indeterminate_domain`; keep the difference in mind when reading older material.

</details>

## Questions

!!! question "1. Why rewrite first when computing signatures with an environment?"
    When an environment is given, [[exec.getcomplsigs#1]] first computes the type of `transform_sender(declval<Sndr>(), declval<Env>())` and then asks for its signatures. What would happen otherwise?

<details markdown="1">
<summary>Answer</summary>

What actually gets connected at connect time is the rewritten sender, whose signatures may include extra error or stopped completions compared with the original ([[exec.snd.general#5]] allows this). If signature computation didn't rewrite first, downstream code would prepare its receiver for the original sender's signatures, and at connect it couldn't accept the extra completions of the rewritten sender: *receiver-of* wouldn't hold. Rewriting first and then asking for signatures ensures that the reported signatures and the sender actually connected are the same thing.
</details>

!!! question "2. Two schedulers, one domain"
    In `when_all(schedule(pool_a) | then(f), schedule(pool_b) | then(g))`, `pool_a` and `pool_b` are two instances of the same kind of thread pool, both with domain `pool_domain`. What is the value completion domain of `when_all`? And its value completion scheduler?

<details markdown="1">
<summary>Answer</summary>

Completion domain: the value completions of both children happen on resources of `pool_domain`, so the *COMMON-DOMAIN* is `common_type_t<pool_domain, pool_domain>`, that is, `pool_domain`.

Completion scheduler: `when_all` completes wherever the last child to complete is, which may be `pool_a` or `pool_b`. No unique scheduler can be determined, so per [[exec.snd.general#4]] this query is ill-formed. A domain is coarser than a scheduler; when the scheduler is uncertain the domain can still be determined, and algorithm customization works just the same.
</details>
