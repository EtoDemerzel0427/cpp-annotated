---
title: 查询
summary: 标准定义的全部查询对象：它们问谁、默认值是什么、结果要满足什么，以及 forwarding_query 如何决定适配器转发哪些查询。
status: draft
covers: *
papers: P2300R10
related: exec.queryable, exec.async.ops, exec.sched, exec.snd.transform, intro.progress, thread.stoptoken
tags: 标准库, std::execution, 环境, 查询, 调度器
updated: 2026-10-19
---

!!! tldr
    - 查询分三类：问接收器的环境（分配器、停止令牌、调度器等），问调度器（前进保证），问发送器的属性（在哪个调度器、哪个 domain 上完成）。
    - 只有派生自 `forwarding_query_t` 或声明自己可转发的查询，才会被适配器转发给子操作；标准的环境查询都是可转发的。
    - `get_stop_token` 默认返回 `never_stop_token`，`get_env` 默认返回 `env<>{}`，`get_domain` 默认是 `default_domain`；`get_allocator`、`get_scheduler` 没有默认值。
    - 报告了完成调度器或完成 domain，就必须真的在那里完成，否则是未定义行为。
    - 所有查询都以 const 方式调用 `query` 并要求 `noexcept`；忘了 const 的 `query` 不会被找到，取消会悄悄失效。

[[exec.queryable]] 规定了可查询对象的通用协议：`q(env)` 调用 `env.query(q)`。标准自带的查询对象如下表；Clang 23 的 libc++ 还没有实现它们，下面的例子没有经过编译。

| 问谁 | 查询 | 用途 |
|---|---|---|
| 接收器的环境 | `get_allocator`、`get_stop_token`、`get_scheduler`、`get_start_scheduler`、`get_delegation_scheduler`、`get_domain` | 调用者希望子操作使用的资源 |
| 调度器 | `get_forward_progress_guarantee` | 调度器的执行代理提供哪一级前进保证 |
| 发送器的属性 | `get_completion_scheduler<Tag>`、`get_completion_domain<Tag>`、`get_await_completion_adaptor` | 发送器在哪里完成、被协程等待时怎样适配 |
| 任何对象 | `get_env` | 取得接收器的环境或发送器的属性 |
| 查询对象 | `forwarding_query` | 这个查询是否应该被转发 |

## 哪些查询会被转发（[exec.fwd.env]）

```cpp title="my-query.cpp"
struct get_priority_t : std::forwarding_query_t {   // 派生即成为可转发查询
  template<class Env>
    requires requires (const Env& e) { e.query(get_priority_t{}); }
  int operator()(const Env& e) const noexcept { return e.query(*this); }
};
inline constexpr get_priority_t get_priority{};
```

用 `write_env(sndr, prop(get_priority, 5))` 注入优先级后，`sndr` 内部经过 `then` 等适配器，更深的子操作能不能看到它？取决于 `forwarding_query(get_priority)`。

¶1 `forwarding_query` 问一个查询对象：适配器是否应该把它转发下去。¶2 规定，对类型为 `Q` 的查询对象 `q`：

- ¶2.1 如果 `q.query(forwarding_query)` 良构，结果就是它（类型必须是 `bool`，且 `q` 是核心常量表达式时它也是）；
- ¶2.2 否则，如果 `Q` 派生自 `forwarding_query_t`，结果是 `true`；
- ¶2.3 否则是 `false`。

适配器 connect 子发送器时，给子接收器的环境是 *FWD-ENV*(get_env(rcvr))（[[exec.adapt.general#3]]），只包含可转发的查询。上面的 `get_priority_t` 如果不派生 `forwarding_query_t`，优先级只有 `sndr` 自己的接收器能看到。

默认不转发是更安全的选择。有些查询只对直接调用者有意义，比如一个假想的你是第几个子操作，它不应该穿过任意多层适配器被深处的发送器看到。标准的所有环境查询和完成调度器查询都声明为可转发。

## 阐述用工具（[exec.queries.expos]）

后面的条文用到两个阐述用工具：

¶2 *TRY-QUERY*(q, tag, args...) 先尝试 `AS-CONST(q).query(tag, args...)`，不行再尝试 `AS-CONST(q).query(tag)`（`args...` 仍被求值）。这让 `query` 成员可以不理会它不关心的额外实参。*AS-CONST* 以 const 左值访问对象（[[exec.general#9]]）。

¶3 *HIDE-SCHED*(q) 是一个包装对象，对 `get_scheduler_t` 和 `get_domain_t` 的查询非良构，其余查询转发给 `q`。它用来防止递归，用法见下面的 `get_scheduler`。

## 环境查询

### get_stop_token（[exec.get.stop.token]）

¶2 如果 `AS-CONST(env).query(get_stop_token)` 良构，结果就是它，类型必须满足 `stoppable_token`；否则结果是 `never_stop_token{}`。

这是整个库取消机制的入口，停止令牌本身见 [[thread.stoptoken]]。发送器在 `start` 时取出接收器环境的停止令牌，在上面注册回调；调用者通过对应的 stop source 请求停止，操作尽快以 `set_stopped` 完成。

默认的 `never_stop_token` 表示不可能被请求停止。`unstoppable_token<never_stop_token>` 为真，许多发送器借此在类型层面去掉 `set_stopped_t()` 签名，例如 `run_loop` 的调度发送器（[[exec.run.loop]]）。

### get_allocator（[exec.get.allocator]）

¶2 `get_allocator(env)` 调用 `AS-CONST(env).query(get_allocator)`，结果须满足 *simple-allocator*。它没有默认值，环境不回答就非良构。需要默认值的地方，规范会显式回落到 `allocator<void>` 之类（如 [[exec.spawn]]）。

### get_scheduler（[exec.get.scheduler]）

¶1 `get_scheduler` 问可查询对象关联的调度器，也就是调用者希望后续工作在哪里运行。¶2 规定 `get_scheduler(env)` 等价于

```cpp
get_completion_scheduler<set_value_t>(
  MANDATE-NOTHROW(AS-CONST(env).query(get_scheduler)),
  HIDE-SCHED(env))
```

结果须满足 `scheduler`，没有默认值。

外面多套的一层 `get_completion_scheduler` 是规范化：环境报告的调度器 `s` 可能是一个包装调度器，它的调度发送器实际在另一个调度器上完成。按下文 *RECURSE-QUERY* 的规则，`get_scheduler` 最终给出真正执行工作的那个调度器。环境用 *HIDE-SCHED* 包一层再传给调度器，是为了不让那个调度器反过来又从同一个环境里查 `get_scheduler`，绕回原点。

### get_start_scheduler（[exec.get.start.scheduler]）

¶1–2 `get_start_scheduler` 问一个操作将在或已在哪个调度器上被启动。它调用 `AS-CONST(env).query(get_start_scheduler)`，结果须满足 `scheduler`，没有默认值。

¶4 对调用者的行为提出了要求：

!!! std
    an operation state that is the result of calling connect(sndr, rcvr) shall, if it is started, be started on an execution agent associated with the scheduler get_start_scheduler(get_env(rcvr)).

这是对调用者的要求：谁在环境里声称你在 X 上被启动，谁就必须真的在 X 的执行代理上调用 `start`。发送器因此可以信任这个信息。例如 `affine`（[[exec.task]]）用它决定完成后回到哪里，`let_value`（[[exec.let]]）把前驱的完成调度器作为后继的启动调度器传下去。

`get_scheduler` 是一种偏好：如果你需要一个调度器来运行东西，就用这个。`get_start_scheduler` 是一个事实：你正在这里被启动。`sync_wait` 的环境对两者都回答它内部 `run_loop` 的调度器（[[exec.sync.wait]]），因为它确实在驱动 `run_loop` 的线程上调用 `start`。

### get_delegation_scheduler（[exec.get.delegation.scheduler]）

¶1–2 问一个可以把工作委托过去的调度器，用于[[g:forward-progress-delegation|前进保证委托]]（[[intro.progress]]）。结果须满足 `scheduler`，没有默认值。

使用场景：`sync_wait` 阻塞调用线程时，在环境里通过这个查询提供它的 `run_loop` 调度器。被等待的工作如果需要一个一定能运行的执行代理，可以把任务调度到那里，由被阻塞的线程亲自执行（[[exec.sync.wait#11]] 注 1）。

### get_domain（[exec.get.domain]）

¶1 `get_domain` 问可查询对象关联的执行 domain 标签。domain 是一个空的标签类型，用来选择发送器算法的实现，见 [[exec.snd.transform]]。

¶2 结果是某个类型 `D` 的默认构造值，`D` 取下列第一个良构表达式的类型：

- ¶2.1 环境直接回答：`auto(AS-CONST(env).query(get_domain))`；
- ¶2.2 环境里有调度器，就问那个调度器的 value 完成 domain：`get_completion_domain<set_value_t>(get_scheduler(env), HIDE-SCHED(env))`；
- ¶2.3 `default_domain()`。

所以 `get_domain` 总有答案。

## 调度器查询：get_forward_progress_guarantee（[exec.get.fwd.progress]）

```cpp
enum class forward_progress_guarantee { concurrent, parallel, weakly_parallel };
```

¶1–2 这个查询只能问调度器，`sch` 不满足 `scheduler` 时非良构。它调用 `AS-CONST(sch).query(get_forward_progress_guarantee)`，结果类型必须是 `forward_progress_guarantee`。

¶3 返回 `concurrent` 时，该执行资源创建的所有执行代理都必须提供[[g:concurrent-forward-progress|并发前进保证]]；返回 `parallel` 时至少提供[[g:parallel-forward-progress|并行前进保证]]；返回 `weakly_parallel` 不附加要求。前进保证的含义见 [[intro.progress]]。

`scheduler` 概念（[[exec.sched]]）要求这个查询良构，所以每个调度器都必须实现 `query(get_forward_progress_guarantee_t)`。

## 发送器属性查询

### get_completion_scheduler（[exec.get.compl.sched]）

¶1–3 `get_completion_scheduler<Tag>` 是一个查询对象模板，`get_completion_scheduler<Tag>(get_env(sndr), envs...)` 从发送器的属性中读出 `Tag` 处置的[[g:completion-scheduler|完成调度器]]。`Tag` 只能是 `set_value_t`、`set_error_t`、`set_stopped_t`。可以附带接收器的环境作为额外实参，因为有些发送器只有知道环境才能回答，例如 `just()` 在调用者所在的调度器上完成。

¶4 定义了一个递归规则 *RECURSE-QUERY*(sch1, envs...)：再问 `sch1` 它自己的 value 完成调度器 `sch2`。如果问不出来，或者 `sch2` 与 `sch1` 类型相同且相等，结果就是 `sch1`；否则继续对 `sch2` 递归。也就是说，调度器也可以回答我的完成调度器是谁，查询会一直追到不动点。

¶5 `get_completion_scheduler<Tag>(q, envs...)` 依次尝试：

- ¶5.1 从 `q` 中查询，再对结果做 *RECURSE-QUERY*；
- ¶5.2 如果 `q` 本身是调度器且 `envs` 非空，结果是 `auto(q)`，即调度器不回答时，它就是自己的完成调度器；
- ¶5.3 否则非良构。

¶6 如果这个查询良构，但发送器的完成签名里根本没有 `Tag` 签名，程序非良构 {{ill-formed}}：不能报告一个不会发生的完成在哪里发生。

¶7 如果发送器报告了完成调度器 `sch`，而它产生的操作在不属于 `sch` 执行资源的执行代理上调用了该处置的完成函数，行为未定义 {{ub}}。

!!! warning "完成调度器不是提示"
    下游代码依赖它：domain 的选择（[[exec.snd.transform]]）、`on` 记住回到哪里（[[exec.on]]）、`affine` 判断是否已在正确的调度器上（[[exec.task]]）都会读它。错误报告完成调度器会让下游代码在错误的线程上运行，这是发送器作者的未定义行为。拿不准时就不要报告，让查询非良构总是安全的。

### get_completion_domain（[exec.get.compl.domain]）

¶1–2 `get_completion_domain<Tag>(attrs, envs...)` 读出 `Tag` 处置的完成 domain，`Tag` 可以是 `void`、`set_value_t`、`set_error_t`、`set_stopped_t`。结果是类型 `D` 的默认构造值，`D` 依次取：

- ¶2.1 属性直接回答的类型；
- ¶2.2 `Tag` 为 `void` 时，取 `set_value_t` 的完成 domain；
- ¶2.3 先问 `Tag` 的完成调度器，再问那个调度器的 value 完成 domain；
- ¶2.4 `attrs` 本身是调度器且 `envs` 非空时，取 `default_domain`；
- ¶2.5 否则非良构。

¶3–4 与完成调度器一样：报告了 domain 却没有该处置的完成签名，程序非良构；报告了 domain `D`，却在 domain 不是 `D` 的执行资源上完成，行为未定义。它也是可转发查询。

完成 domain 比完成调度器更粗。`when_all` 可能不知道自己会在哪个调度器上完成（它在最后完成的那个子操作所在处完成），但可能知道这些调度器都属于同一个 domain。

### get_await_completion_adaptor（[exec.get.await.adapt]）

¶1–2 问可查询对象关联的 await 完成适配器，没有默认值。¶3 它是可转发查询。

`as_awaitable` 使用它（[[exec.as.awaitable#8]]）：发送器的属性如果提供了适配器 `a`，协程 `co_await sndr` 时实际等待的是 `a(sndr)`。发送器作者可以借此在被协程等待之前对自己做一次变换。

## get_env（[exec.get.env]）

¶1 `get_env(o)` 调用 `AS-CONST(o).get_env()`，结果须满足 *queryable*；没有这个成员时返回 `env<>{}`。注意这里的定制点是成员函数 `get_env()`，不是 `query`。

¶2 `get_env(o)` 的值在 `o` 有效期间有效。

¶3 注 1 说明：对发送器，`get_env` 返回它的属性；对接收器，返回它的执行环境。

## 陷阱

!!! pitfall "query 成员忘了 const 或 noexcept"
    标准查询都通过 *AS-CONST* 调用 `query`，并要求调用 `noexcept`。非 const 的 `query` 成员根本不会被找到，查询要么回落到默认值，要么非良构。前一种情况最隐蔽：`get_stop_token` 回落到 `never_stop_token`，没有任何诊断，取消就是不起作用。const 但非 `noexcept` 的 `query` 则让程序非良构。

## 思考题

!!! question "1. sync_wait 中的发送器能被取消吗？"
    `sync_wait` 的环境（[[exec.sync.wait]]）只回答 `get_scheduler`、`get_start_scheduler`、`get_delegation_scheduler` 三个查询。

<details markdown="1">
<summary>答案</summary>

不能从外部取消。环境不回答 `get_stop_token`，所以子操作拿到的是 `never_stop_token{}`（[exec.get.stop.token] ¶2.2），没有人能请求停止。

发送器内部仍可能以 `set_stopped` 完成，例如 `just_stopped()`，这时 `sync_wait` 返回空的 `optional`。想让 `sync_wait` 可以取消，可以用 `write_env(sndr, prop(get_stop_token, src.get_token()))` 注入一个令牌。
</details>

!!! question "2. 为什么 forwarding_query 默认是 false？"

<details markdown="1">
<summary>答案</summary>

有些查询的答案只对直接调用者成立。设想一个 `get_child_index`，外层适配器告诉它的第 0 个子操作答案是 0。如果它默认被转发，穿过一层 `then` 之后，`then` 的子操作也会以为自己是第 0 个子操作，而它并不是外层适配器的直接子操作。

默认不转发，迫使查询的作者显式声明这个答案对所有后代都成立。
</details>

## 小结

| 查询 | 问谁 | 默认值 |
|---|---|---|
| `forwarding_query` | 查询对象 | 派生自 `forwarding_query_t` 则为 `true`，否则 `false` |
| `get_stop_token` | 环境 | `never_stop_token{}` |
| `get_allocator` | 环境 | 无 |
| `get_scheduler` | 环境 | 无，结果经完成调度器规范化 |
| `get_start_scheduler` | 环境 | 无；回答了就必须在那里启动 |
| `get_delegation_scheduler` | 环境 | 无 |
| `get_domain` | 环境 | 调度器的 value 完成 domain，再退到 `default_domain` |
| `get_forward_progress_guarantee` | 调度器 | 无，调度器必须回答 |
| `get_completion_scheduler<Tag>` | 属性或调度器 | 调度器加非空环境时为自身；报告了就必须在那里完成 |
| `get_completion_domain<Tag>` | 属性或调度器 | 经由完成调度器；调度器加非空环境时为 `default_domain` |
| `get_await_completion_adaptor` | 属性 | 无 |
| `get_env` | 发送器或接收器 | `env<>{}` |

除 `get_env`、`forwarding_query`、`get_forward_progress_guarantee` 外，表中所有查询都是可转发的。
