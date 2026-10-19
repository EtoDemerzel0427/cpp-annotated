---
title: domain 与发送器变换
summary: 算法怎样被定制：connect 前，transform_sender 先按前驱完成所在的 domain、再按操作启动所在的 domain 改写发送器，每一阶段反复改写到不再变化；default_domain 调用发送器标签自带的改写；indeterminate_domain 表示无法确定 domain；apply_sender 定制 sync_wait 这类消费者。
status: draft
covers: exec.domain.indeterminate, exec.domain.default, exec.snd.apply
papers: P2300R10
related: exec.connect, exec.snd, exec.queries, exec.bulk, exec.par.scheduler, exec.consumers, exec.task.scheduler
tags: 标准库, std::execution, 定制, domain
updated: 2026-10-19
---

!!! tldr
    - 执行 domain 是执行资源关联的一个空标签类型，用来决定标准算法用哪个实现。
    - 定制发生在 connect 时：`transform_sender(sndr, env)` 先按前驱的完成 domain 改写发送器，再按接收器环境的启动 domain 改写，每一阶段反复改写，直到类型不再变化。
    - `default_domain` 调用发送器标签类型自带的 `transform_sender`。标准用它把 `starts_on`、`on`、`bulk`、`stopped_as_optional` 等改写成更基本的算法。
    - 某种完成可能发生在几个无法统一的 domain 上时，得到 `indeterminate_domain`：只能用默认实现，有 domain 给出不同的改写时程序非良构。
    - `apply_sender` 定制的是不返回发送器的算法，比如 `sync_wait`。

本页的例子没有经过编译验证：本机 Clang 23 附带的 libc++ 还没有实现 `std::execution` 的发送器部分，所以不加判定标记。

## 谁来决定用哪个实现

`then`、`bulk`、`when_all` 都有默认实现（[[exec.snd]]），但默认实现不总是最好的。GPU 调度器希望 `bulk` 变成一次 kernel 启动，而不是在一个线程上循环；线程池希望把 `bulk` 拆成多个任务。问题是由谁、在什么时候选择实现：

- 不能在调用 `bulk(sndr, ...)` 时选：那时还不知道它会在哪里运行。
- 不能由 `bulk` 自己选：它不认识所有的执行资源。

草案的做法是**执行 domain**（execution domain，[[g:execution-domain]]）：每个执行资源关联一个空的标签类型。`connect` 时先调用 `transform_sender(sndr, get_env(rcvr))`，按相关的 domain 把发送器改写成另一个发送器，再 connect 改写的结果（[[exec.connect]]）。定制一个算法，就是在自己的 domain 里提供 `transform_sender`，认出 `bulk_chunked` 这类发送器，返回一个自己实现的发送器。

发送器在两处与执行资源打交道，所以有两种 domain：

- **完成 domain**：前驱在哪里完成。对 `bulk(sndr, ...)` 来说就是 `sndr` 完成的地方，`bulk` 的工作接着在那里开始。它由发送器属性上的 `get_completion_domain` 查询回答（[[exec.get.compl.domain]]）。
- **启动 domain**：发送器自己在哪里被启动。它由接收器环境上的 `get_domain` 查询回答（[[exec.get.domain]]）。

`transform_sender` 两种都用。

## transform_sender [exec.snd.transform]

```cpp
template<sender Sndr, queryable Env>
  constexpr decltype(auto) transform_sender(Sndr&& sndr, const Env& env) noexcept(see below);
```

¶1 启动 domain 取 `get_domain(env)` 的类型；这个查询不良构时用 `default_domain`。

¶2 发送器 `s` 的完成 domain 取 `get_completion_domain<>(get_env(s), env)` 的类型。模板实参为空时查的是值完成的 domain。查询不良构时同样用 `default_domain`。

¶3 改写一步：先试 `dom.transform_sender(tag, s, env)`，不良构就退回 `default_domain().transform_sender(tag, s, env)`。所以自定义 domain 总是先于默认改写。

反复改写：如果这一步的结果与 `s` 类型相同（忽略 cv），就停下；否则对结果 `s2` 再做一步。下一步用的 domain，在启动阶段仍是启动 domain，在完成阶段是 `s2` 的完成 domain。

整个过程分两阶段：

```text
阶段 1（标签 set_value）：按前驱的完成 domain 反复改写 sndr，直到不再变化，得到 tmp
阶段 2（标签 start）    ：按接收器环境的启动 domain 反复改写 tmp，直到不再变化，得到 final
connect(final, rcvr)
```

¶4 返回阶段 2 的结果。¶5 它的 noexcept 与整个改写过程一致。

第一个实参 `tag` 是 `set_value` 或 `start`，告诉 domain 当前处于哪个阶段，domain 可以只在其中一个阶段介入。标准算法自带的改写大多只接受 `set_value`，也就是按前驱完成的位置选择实现。

反复改写的意义在于，改写的结果可以再被改写。`bulk` 在默认 domain 下先被改写成 `bulk_chunked`（[[exec.bulk#4]]），`bulk_chunked` 在 `parallel_scheduler` 的 domain 下又被改写成调用后端的发送器（[[exec.par.scheduler#11]]）。有了这一步，GPU 的 domain 不必认识 `bulk`，只需认识 `bulk_chunked` 和 `bulk_unchunked`。

## default_domain [exec.domain.default]

```cpp
struct default_domain {
  template<class Tag, sender Sndr, queryable Env>
    static constexpr decltype(auto) transform_sender(Tag, Sndr&& sndr, const Env& env) noexcept(see below);
  template<class Tag, sender Sndr, class... Args>
    static constexpr decltype(auto) apply_sender(Tag, Sndr&& sndr, Args&&... args) noexcept(see below);
};
```

¶2–4 `transform_sender(tag, sndr, env)`：如果 `tag_of_t<Sndr>().transform_sender(Tag(), sndr, env)` 良构就返回它，否则原样返回 `sndr`。`tag_of_t<Sndr>` 是发送器的标签类型，通常是创建它的定制点对象的类型，比如 `bulk_t`（[[exec.snd]]）。

也就是说，算法的标签类型可以带一个 `transform_sender` 成员，提供默认的改写。标准用这种方式把很多算法表示成其他算法的组合：

| 算法 | 改写成 | 出处 |
|---|---|---|
| `starts_on(sch, s)` | `let_value(continues_on(just(), sch), [s]{ return s; })` | [[exec.on]] |
| `on(sch, s)` | `continues_on(starts_on(sch, s), 原调度器)` | [[exec.on]] |
| `bulk(s, pol, n, f)` | `bulk_chunked(s, pol, n, 逐元素调用 f 的函数)` | [[exec.bulk]] |
| `when_all_with_variant(s...)` | `when_all(into_variant(s)...)` | [[exec.when.all]] |
| `stopped_as_optional(s)` | `let_stopped(then(s, 包成 optional), 返回空 optional)` | [[exec.adapt]] |
| `stopped_as_error(s, e)` | `let_stopped(s, 返回 just_error(e))` | [[exec.adapt]] |
| `let_value(s, f)` 等 | 换成内部的 *let-tag* 发送器 | [[exec.let]] |
| `affine(s)` | `s.affine()` 或 `continues_on(s, 启动调度器)` | [[exec.affine]] |

自定义 domain 想直接实现 `starts_on`，只需在自己的 `transform_sender` 里先认出 `starts_on_t`。¶3 先问 `dom`，`dom` 不处理才退回 `default_domain`。

¶5–8 `apply_sender(tag, sndr, args...)` 等价于 `Tag().apply_sender(sndr, args...)`，要求这个表达式良构（*Constraints*）。

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

`when_all(a, b)` 在 `a`、`b` 中最后完成的那个所在处完成。如果 `a` 在 GPU 上、`b` 在线程池上，`when_all` 的完成 domain 就无法确定。这时 *COMMON-DOMAIN*（[[exec.snd]]）先试这几个 domain 的 `common_type`；没有公共类型，结果就是 `indeterminate_domain<Ds...>`。

¶2 *Mandates*：对 `Domains...` 中的每个 `D`，`D().transform_sender(Tag(), sndr, env)` 要么不良构，要么与 `default_domain` 的改写结果退化后类型相同。

¶3 返回 `default_domain().transform_sender(Tag(), sndr, env)`。

既然不知道会在哪个 domain 上完成，就只能用默认实现。如果其中某个 domain 对这个发送器有不同的定制，程序非良构 {{ill-formed}}，而不是随便挑一个。这样同一个程序不会因为哪个子操作先完成而走不同的算法实现。

¶4 `indeterminate_domain` 参与 `common_type` 的计算：两个 `indeterminate_domain` 的公共类型是合并去重后的 `indeterminate_domain`；空的 `indeterminate_domain<>` 与任意 `D` 的公共类型是 `D`；非空的与 `D` 的公共类型是把 `D` 加进去。转换构造函数让任何 domain 都能转换成它。

## apply_sender [exec.snd.apply]

```cpp
template<class Domain, class Tag, sender Sndr, class... Args>
  constexpr decltype(auto) apply_sender(Domain dom, Tag, Sndr&& sndr, Args&&... args) noexcept(see below);
```

¶1–4 如果 `dom.apply_sender(Tag(), sndr, args...)` 良构就用它，否则用 `default_domain().apply_sender(...)`，也就是 `Tag().apply_sender(sndr, args...)`。整个表达式必须良构（*Constraints*）。

`transform_sender` 改写的是发送器；`apply_sender` 定制的是消费者，即不返回发送器的算法。`sync_wait(sndr)` 就等价于 `apply_sender(Domain(), sync_wait, sndr)`，`Domain` 是 `sndr` 的值完成 domain（[[exec.sync.wait#4]]）。GPU 的 domain 因此可以提供自己的 `sync_wait`，直接等待设备流同步，而不是驱动一个 `run_loop`。

## 自定义 domain 的样子

```cpp title="my-domain.cpp"
namespace ex = std::execution;

struct gpu_domain {
  template<class Sndr, class Env>
    requires std::same_as<ex::tag_of_t<Sndr>, ex::bulk_chunked_t>
  static auto transform_sender(ex::set_value_t, Sndr&& sndr, const Env& env) {
    auto&& [_, data, child] = sndr;
    auto&& [policy, shape, f] = data;
    return gpu_bulk_sender{std::forward_like<Sndr>(child), shape, f};   // 自己实现的发送器
  }
};

class gpu_scheduler {
public:
  using scheduler_concept = ex::scheduler_tag;
  // 让调度器报告值完成的 domain：
  auto query(ex::get_completion_domain_t<ex::set_value_t>) const noexcept { return gpu_domain{}; }
  // ...
};
```

`ex::schedule(gpu) | ex::bulk(ex::par, n, f)` 在 connect 时这样改写：

1. 阶段 1，`bulk` 的完成 domain 由前驱 `schedule(gpu)` 决定，是 `gpu_domain`。`gpu_domain` 不处理 `bulk_t`，退回 `default_domain`，`bulk_t::transform_sender` 把它改写成 `bulk_chunked`。
2. 类型变了，继续改写。`gpu_domain` 认出 `bulk_chunked`，改写成 `gpu_bulk_sender`。
3. 再改写一次，类型不再变化，阶段 1 结束。

!!! pitfall "定制不能改变值签名"
    按 [[exec.snd.general#5]]，选用了用户提供的实现时，它比默认实现多出来的签名只能是错误或取消完成。所以 `gpu_bulk_sender` 可以多一个 `set_error_t(cuda_error)`，但不能把值完成从 `set_value_t(int)` 改成 `set_value_t(long)`：下游在 connect 之前就已经按默认实现的签名做了类型计算。

!!! pitfall "定制不发生在构造时"
    `auto s = bulk(sndr, par, n, f);` 得到的就是标准的发送器，此时还没有任何 domain 介入。检查 `s` 的类型，或者把 `s` 交给一个绕过 `connect` 的消费者，都看不到定制的效果。改写只在 `connect` 里发生，带环境计算签名时也会先做一次（[[exec.getcomplsigs#1]]）。

<details class="fine" markdown="1"><summary>其余条文</summary>

¶3 在定义反复改写时，把改写一步的结果写成了 *transformed-sender*，与前文定义的名字 *transformed-sndr* 不一致，显然指的是同一个东西。

`let_*` 与 `affine` 的改写在各自的条款里写成不带标签的形式（`let-cpo.transform_sender(s, es...)`，见 [[exec.let#6]]、[[exec.affine#5]]），与 `default_domain` 调用的 `transform_sender(Tag(), sndr, env)` 形式对不上，也属于措辞上的出入。

P2300 最初并入时的 domain 机制（早期定制、晚期定制）与当前措辞不同。当前措辞引入了完成 domain、两阶段改写和 `indeterminate_domain`，阅读较早的资料时要注意区分。

</details>

## 思考题

!!! question "1. 为什么带环境计算签名时也要先改写？"
    [[exec.getcomplsigs#1]] 在给出环境时，先计算 `transform_sender(declval<Sndr>(), declval<Env>())` 的类型，再问它的签名。如果不这样做会怎样？

<details markdown="1">
<summary>答案</summary>

connect 时真正被连接的是改写后的发送器，它的签名可能比原来的多出错误或取消完成（[[exec.snd.general#5]] 允许这样）。如果签名计算不先改写，下游会按原发送器的签名准备接收器，connect 时遇到改写后多出来的完成就接不住，*receiver-of* 不成立。先改写再问签名，保证报告的签名和实际 connect 的发送器是同一个东西。
</details>

!!! question "2. 两个调度器，同一个 domain"
    `when_all(schedule(pool_a) | then(f), schedule(pool_b) | then(g))`，`pool_a`、`pool_b` 是同一类线程池的两个实例，domain 都是 `pool_domain`。`when_all` 的值完成 domain 是什么？值完成调度器呢？

<details markdown="1">
<summary>答案</summary>

完成 domain：两个子操作的值完成都发生在 `pool_domain` 的资源上，*COMMON-DOMAIN* 是 `common_type_t<pool_domain, pool_domain>`，也就是 `pool_domain`。

完成调度器：`when_all` 在最后完成的子操作所在处完成，可能是 `pool_a`，也可能是 `pool_b`。无法确定唯一的调度器，按 [[exec.snd.general#4]]，这个查询不良构。domain 比调度器粗，调度器不确定时 domain 仍可以确定，算法定制照样能进行。
</details>
