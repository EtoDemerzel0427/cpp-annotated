---
title: domain 与发送器变换
summary: 算法怎样被定制——transform_sender 在 connect 前分两阶段改写发送器：先按"前驱在哪里完成"的完成 domain（标签 set_value），再按"在哪里启动"的启动 domain（标签 start），直到不动点；default_domain 调用发送器标签自带的 transform_sender；indeterminate_domain 表示多个 domain 无法统一；apply_sender 定制 sync_wait 这类消费者
status: draft
covers: exec.domain.indeterminate, exec.domain.default, exec.snd.apply
papers: P2300R10
related: exec.connect, exec.snd, exec.queries, exec.bulk, exec.par.scheduler, exec.consumers, exec.task.scheduler
tags: 标准库, std::execution, 定制, domain
updated: 2026-10-18
---

`then`、`bulk`、`when_all` 都有默认实现（[[exec.snd]]），但默认实现不总是最好的：GPU 调度器希望 `bulk` 变成一次 kernel 启动，而不是在一个线程上循环；线程池希望把 `bulk` 拆成多个任务。问题是：**由谁、在什么时候**决定用哪个实现？

- 不能在调用 `bulk(sndr, ...)` 时决定：那时还不知道它会在哪里运行（`sndr` 可能依赖环境）。
- 不能由 `bulk` 自己决定：它不认识所有执行资源。

当前草案的回答是 **domain**（执行 domain，[[g:execution-domain]]）：每个执行资源关联一个空的**标签类型**；`connect` 时（[[exec.connect]]）调用 `transform_sender(sndr, get_env(rcvr))`，按照相关的 domain 把发送器**改写**成另一个发送器，然后再 connect 改写后的结果。定制一个算法，就是在自己的 domain 里提供 `transform_sender`，识别出 `bulk_chunked` 这类发送器，返回一个自己实现的发送器。

!!! history "domain 机制几经修改"
    P2300 合入时的 domain 机制（`get_domain`、"早期/晚期"定制）与本页所据的草案措辞并不相同：当前措辞引入了完成 domain（`get_completion_domain`）、两阶段变换和 `indeterminate_domain`。具体由哪些提案、在哪次会议引入，本站不在此给出编号。阅读其他资料时要注意它们描述的可能是旧机制。

## 两个 domain：完成 domain 与启动 domain

一个发送器在两处与执行资源打交道：

- 它的**前驱完成**在哪里——对 `bulk(sndr, ...)` 来说就是 `sndr` 在哪里完成，`bulk` 的工作接着在那里开始。这由**发送器属性**上的 `get_completion_domain` 回答（[[exec.get.compl.domain]]），称为**完成 domain**。
- 它自己被**启动**在哪里——由**接收器环境**上的 `get_domain` 回答（[[exec.get.domain]]），称为**启动 domain**。

`transform_sender` 两个都用。

## transform_sender（[exec.snd.transform]）

```cpp
template<sender Sndr, queryable Env>
  constexpr decltype(auto) transform_sender(Sndr&& sndr, const Env& env) noexcept(see below);
```

¶1 *start-domain*：`get_domain(env)` 良构时为其类型的默认构造值，否则 `default_domain()`。

¶2 *completion-domain*(s)：`get_completion_domain<>(get_env(s), env)`（标签 `void`，即 value 完成）良构时为其类型的值，否则 `default_domain()`。

¶3 *transformed-sndr*(dom, tag, s)：`dom.transform_sender(tag, s, env)` 良构就用它，否则 `default_domain().transform_sender(tag, s, env)`。

*transform-recurse*(dom, tag, s)：若 *transformed-sndr*(dom, tag, s) 与 `s` 类型相同（忽略 cv），就是它（到达不动点）；否则对变换结果 `s2` 递归，新的 domain 为：`tag` 是 `start` 时用 *start-domain*，否则用 *completion-domain*(s2)。

最后：

```text
tmp-sndr   = transform-recurse(completion-domain(sndr), set_value, sndr)
final-sndr = transform-recurse(start-domain,            start,     tmp-sndr)
```

¶4 返回 *final-sndr*。¶5 noexcept 与之一致。

画成流程：

```text
sndr ──[阶段 1：标签 set_value，问"前驱在哪完成"的 domain]──► 反复变换到不动点 ──► tmp
tmp  ──[阶段 2：标签 start，问"我在哪启动"的 domain]────────► 反复变换到不动点 ──► final
connect(final, rcvr)
```

第一个实参 `tag`（`set_value` 或 `start`）告诉 domain 当前是哪个阶段，于是 domain 可以只在其中一个阶段介入。标准算法自带的变换（见下）大多写成 `xxx.transform_sender(set_value, out_sndr, env)`，即只在阶段 1 生效，"按前驱完成的位置决定实现"。（`let_*` 与 `affine` 的变换在规范中写成不带标签的形式 `transform_sender(s, …)`，与 `default_domain` 的调用形式对不上，属于措辞上的小出入。）

!!! note "递归的意义"
    变换可以产生另一个**可以再变换**的发送器。`bulk` 在默认 domain 下先被改写为 `bulk_chunked`（[[exec.bulk#4]]），而 `bulk_chunked` 在 `parallel_scheduler` 的 domain 下又被改写为调用后端的发送器（[[exec.par.scheduler#11]]）。若没有递归，GPU domain 就得同时识别 `bulk`、`bulk_chunked`、`bulk_unchunked` 三种形式；有了递归，它只需识别后两者。

## default_domain（[exec.domain.default]）

```cpp
struct default_domain {
  template<class Tag, sender Sndr, queryable Env>
    static constexpr decltype(auto) transform_sender(Tag, Sndr&& sndr, const Env& env) noexcept(see below);
  template<class Tag, sender Sndr, class... Args>
    static constexpr decltype(auto) apply_sender(Tag, Sndr&& sndr, Args&&... args) noexcept(see below);
};
```

¶2–4 `transform_sender(tag, sndr, env)`：若 `tag_of_t<Sndr>().transform_sender(Tag(), std::forward<Sndr>(sndr), env)` 良构就返回它，否则 `static_cast<Sndr>(std::forward<Sndr>(sndr))`（原样返回）。

也就是说，**发送器的标签类型**（如 `bulk_t`、`starts_on_t`）可以带一个 `transform_sender` 成员，提供"默认的改写"。标准算法大量使用这种方式把自己**降级**成别的算法的组合：

| 算法 | `xxx_t::transform_sender(set_value, …)` 改写为 | 出处 |
|---|---|---|
| `starts_on(sch, s)` | `let_value(continues_on(just(), sch), [s]{ return s; })` | [[exec.on]] |
| `on(sch, s)` | `continues_on(starts_on(sch, s), 原调度器)` | [[exec.on]] |
| `bulk(s, pol, n, f)` | `bulk_chunked(s, pol, n, 逐元素调用 f 的函数)` | [[exec.bulk]] |
| `when_all_with_variant(s...)` | `when_all(into_variant(s)...)` | [[exec.when.all]] |
| `stopped_as_optional(s)` | `let_stopped(then(s, 包成 optional), 返回空 optional)` | [[exec.adapt]] |
| `stopped_as_error(s, e)` | `let_stopped(s, 返回 just_error(e))` | [[exec.adapt]] |
| `let_value(s, f)` 等 | 换成内部的 *let-tag* 发送器 | [[exec.let]] |
| `affine(s)` | `s.affine()` 或 `continues_on(s, 启动调度器)` | [[exec.affine]] |

这些改写都在 `default_domain` 下发生；一个自定义 domain 若想直接实现 `starts_on`，只需在它的 `transform_sender` 里先识别 `starts_on_t`——由于 *transformed-sndr* 先问 `dom`、`dom` 不处理才回落到 `default_domain`，自定义 domain 的优先级更高。

¶5–8 `apply_sender(tag, sndr, args...)`：等价于 `Tag().apply_sender(std::forward<Sndr>(sndr), std::forward<Args>(args)...)`，*Constraints* 要求其良构。

## indeterminate_domain（[exec.domain.indeterminate]）

```cpp
template<class... Domains>
struct indeterminate_domain {
  indeterminate_domain() = default;
  constexpr indeterminate_domain(auto&&) noexcept {}
  template<class Tag, sender Sndr, queryable Env>
    static constexpr decltype(auto) transform_sender(Tag, Sndr&& sndr, const Env& env) noexcept(see below);
};
```

当一个发送器的某种完成可能在**多个**不同 domain 的执行资源上发生、而这些 domain 又没有公共类型时，*COMMON-DOMAIN*（[[exec.snd]] ¶8）给出 `indeterminate_domain<Ds...>`。例如 `when_all(a, b)` 在 `a`、`b` 中最后完成的那个所在处完成；`a` 在 GPU 上、`b` 在线程池上，那么 `when_all` 的完成 domain 就是"不确定"的。

¶2 *Mandates*：对 `Domains...` 中每个 `D`，`D().transform_sender(Tag(), sndr, env)` 要么非良构，要么与 `default_domain().transform_sender(...)` 的退化类型**相同**。

¶3 返回 `default_domain().transform_sender(Tag(), std::forward<Sndr>(sndr), env)`。

意思是：既然不知道会在哪个 domain 完成，就只能用默认实现；如果其中某个 domain 对这个发送器有**不同**的定制，程序非良构——不允许"随机地"选一个实现。这比"随便挑一个"安全：同一个程序在不同运行中不会因为谁先完成而走不同的算法实现。

¶4 *Remarks*：`indeterminate_domain` 参与 `common_type` 计算：两个 `indeterminate_domain` 的公共类型是合并去重后的 `indeterminate_domain`；`indeterminate_domain<>`（空）与任意 `D` 的公共类型是 `D`；非空的与 `D` 的公共类型是把 `D` 加进去。构造函数 `indeterminate_domain(auto&&)` 让任何 domain 都能转换成它。

## apply_sender（[exec.snd.apply]）

```cpp
template<class Domain, class Tag, sender Sndr, class... Args>
  constexpr decltype(auto) apply_sender(Domain dom, Tag, Sndr&& sndr, Args&&... args) noexcept(see below);
```

¶1–3 `dom.apply_sender(Tag(), sndr, args...)` 良构就用它，否则 `default_domain().apply_sender(...)`（即调用 `Tag().apply_sender(sndr, args...)`）；*Constraints*：结果表达式良构。

`transform_sender` 改写的是**发送器**；`apply_sender` 定制的是**消费者**——那些不返回发送器的算法。`sync_wait(sndr)` 就是 `apply_sender(Domain(), sync_wait, sndr)`，`Domain` 是 `sndr` 在 *sync-wait-env* 下的 value 完成 domain（[[exec.sync.wait#4]]）。于是一个 GPU domain 可以提供自己的 `sync_wait`：比如直接等待设备流同步，而不是驱动一个 `run_loop`。

## 自定义 domain 的样子

```cpp title="my-domain.cpp"
namespace ex = std::execution;

struct gpu_domain {
  template<ex::sender Sndr, class Env>
    requires ex::sender-for<Sndr, ex::bulk_chunked_t>   // 阐述用概念，实际代码需自行检查 tag_of_t
  static auto transform_sender(ex::set_value_t, Sndr&& sndr, const Env& env) {
    auto&& [_, data, child] = sndr;
    auto&& [policy, shape, f] = data;
    return gpu_bulk_sender{std::forward_like<Sndr>(child), shape, f};   // 自己实现的发送器
  }
};

class gpu_scheduler {
public:
  using scheduler_concept = ex::scheduler_tag;
  // 让调度发送器（及调度器本身）报告 value 完成 domain：
  auto query(ex::get_completion_domain_t<ex::set_value_t>) const noexcept { return gpu_domain{}; }
  // ...
};
```

之后 `ex::schedule(gpu) | ex::bulk(ex::par, n, f)` 在 connect 时：阶段 1，`bulk` 的完成 domain 由前驱 `schedule(gpu)` 决定，是 `gpu_domain`；`gpu_domain` 不处理 `bulk_t`，回落到 `default_domain`，`bulk_t::transform_sender` 把它改写为 `bulk_chunked`；递归，`gpu_domain` 识别 `bulk_chunked`，改写为 `gpu_bulk_sender`；再递归，类型不再变化，阶段 1 结束。

## 陷阱

!!! pitfall "定制不能改变 value 签名"
    [[exec.snd.general#5]] ¶5.1 规定：选用了用户提供的实现时，它比默认实现**多出来**的签名只能是 error 或 stopped。所以 `gpu_bulk_sender` 可以多一个 `set_error_t(cuda_error)`，但不能把 value 完成从 `set_value_t(int)` 改成 `set_value_t(long)`。原因很直接：下游在 connect 之前就已经按默认实现的签名做了类型计算。

!!! pitfall "以为定制发生在构造时"
    `auto s = bulk(sndr, par, n, f);` 得到的就是标准的 *basic-sender*，此时还没有任何 domain 介入。如果你检查 `s` 的类型、或者把 `s` 交给一个自己写的、绕过 `connect` 的消费者，就看不到定制效果。所有定制都只在 `connect`（以及 `get_completion_signatures` 带环境时）里发生。

## 思考题

!!! question "1. 为什么 get_completion_signatures 带环境时也要 transform？"
    [[exec.getcomplsigs#1]] 在 `Env` 非空时先计算 `transform_sender(declval<Sndr>(), declval<Env>())` 的类型，再问签名。如果不这样做会怎样？

<details markdown="1">
<summary>答案</summary>

connect 时真正被连接的是变换后的发送器，它的签名可能比原发送器多出 error/stopped 完成（[[exec.snd.general#5]] 允许）。如果签名计算不先变换，下游就会按"原发送器"的签名准备接收器，connect 时再遇到"变换后发送器"多出来的完成，接收器接不住——*receiver-of* 失败。先变换再问签名，保证"报告的签名"和"实际 connect 的发送器"是同一个东西。
</details>

!!! question "2. 两个调度器，同一个 domain"
    `when_all(schedule(pool_a) | then(f), schedule(pool_b) | then(g))`，`pool_a`、`pool_b` 是同一类线程池的两个实例，其 domain 都是 `pool_domain`。`when_all` 的 value 完成 domain 是什么？value 完成调度器呢？

<details markdown="1">
<summary>答案</summary>

完成 domain：两个子操作的 value 完成都在 `pool_domain` 的资源上，*COMMON-DOMAIN*<pool_domain, pool_domain> 就是 `pool_domain`（`common_type_t<D, D>` 是 `D`）。完成调度器：`when_all` 在最后完成的那个子操作所在处完成，可能是 `pool_a` 也可能是 `pool_b`；不能确定唯一的调度器，所以按 [[exec.snd.general#4]]，`get_completion_scheduler<set_value_t>` 非良构。这正是 domain 比调度器"粗"的用处：调度器不确定时，domain 仍可以确定，算法定制仍能进行。
</details>

## 小结

- domain 是执行资源关联的空标签类型，决定算法用哪个实现。
- `transform_sender(sndr, env)`：阶段 1 用前驱的**完成 domain**（标签 `set_value`），阶段 2 用接收器环境的**启动 domain**（标签 `start`），每阶段递归到不动点。
- `default_domain` 调用发送器标签的 `transform_sender`：标准用它把 `starts_on`、`on`、`bulk`、`let_*` 等降级为更基本的算法。
- `indeterminate_domain`：多个 domain 无法统一时只能用默认实现；若有 domain 定制了不同结果，非良构。
- `apply_sender`：定制 `sync_wait` 这类消费者。
