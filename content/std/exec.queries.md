---
title: 查询
summary: 标准定义的全部查询对象——forwarding_query 决定适配器转发哪些查询；环境查询 get_allocator / get_stop_token / get_scheduler / get_start_scheduler / get_delegation_scheduler / get_domain；调度器查询 get_forward_progress_guarantee；发送器属性查询 get_completion_scheduler / get_completion_domain；以及 get_env 本身
status: done
covers: *
papers: P2300R10
related: exec.queryable, exec.async.ops, exec.sched, exec.snd.transform, intro.progress, thread.stoptoken
tags: 标准库, std::execution, 环境, 查询, 调度器
updated: 2026-10-18
---

[[exec.queryable]] 规定了"可查询对象"的通用协议，本节列出标准自带的每一个**查询对象**：它问什么、谁来回答、回答不了时默认取什么、结果要满足什么。

按"问谁"分三类：

| 问谁 | 查询 | 结果 |
|---|---|---|
| 接收器的**环境** | `get_allocator`、`get_stop_token`、`get_scheduler`、`get_start_scheduler`、`get_delegation_scheduler`、`get_domain`、`get_await_completion_adaptor` | 调用者希望子操作使用的资源 |
| **调度器** | `get_forward_progress_guarantee`（也可问 `get_completion_scheduler`、`get_completion_domain`） | 调度器的属性 |
| 发送器的**属性** | `get_completion_scheduler<Tag>`、`get_completion_domain<Tag>` | 这个发送器在哪里完成 |
| 任何对象 | `get_env`、`forwarding_query` | 取得环境/属性；问查询对象自己 |

## 阐述用工具（[exec.queries.expos]）

¶2 ***TRY-QUERY*(q, tag, args...)**：先试 *AS-CONST*(q).query(tag, args...)，不行再试 *AS-CONST*(q).query(tag)（此时 `args...` 仍会被求值）。这让一个 `query` 成员可以忽略它不关心的额外实参。

¶3 ***HIDE-SCHED*(q)**：一个包装对象，对 `get_scheduler_t`、`get_domain_t` 两个查询**非良构**，其余查询转发给 `q`。它用来**防止递归**：`get_scheduler(env)` 拿到调度器后，还要以环境为额外实参问"这个调度器的完成调度器是谁"（见下文），这时把环境包一层 *HIDE-SCHED*，免得那个调度器反过来又从环境里查 `get_scheduler`，绕回原点。

## forwarding_query（[exec.fwd.env]）

¶1 `forwarding_query` 问一个**查询对象**：适配器是否应该把它转发下去。

¶2 对类型为 `Q` 的查询对象 `q`，`forwarding_query(q)`：

- ¶2.1 若 `q.query(forwarding_query)` 良构，就是它（*Mandates*：类型为 `bool`，且 `q` 是核心常量表达式时它也是）；
- ¶2.2 否则，若 `Q` 派生自 `forwarding_query_t`，为 `true`；
- ¶2.3 否则为 `false`。

为什么需要这个？适配器 connect 子发送器时，给子接收器的环境是 *FWD-ENV*(get_env(rcvr))（[[exec.adapt.general#3]]），只转发 `forwarding_query(q)` 为 true 的查询。**默认不转发**是安全的选择：一个只对"直接调用者"有意义的查询（比如"你是第几个子操作"）不应该穿过任意多层适配器被深处的发送器看到。标准的所有环境查询都声明自己是转发查询（下文每个查询的最后一段都是"`forwarding_query(xxx)` 是值为 true 的核心常量表达式"）。

!!! tip "自定义查询别忘了 forwarding_query"
    ```cpp title="my-query.cpp"
    struct get_priority_t : std::forwarding_query_t {   // 派生即可成为转发查询
      template<class Env>
        requires requires (const Env& e) { e.query(get_priority_t{}); }
      int operator()(const Env& e) const noexcept { return e.query(*this); }
    };
    inline constexpr get_priority_t get_priority{};
    ```
    如果不派生 `forwarding_query_t`，你用 `write_env(sndr, prop(get_priority, 5))` 注入的优先级，只有 `sndr` 自己的接收器能看到；`sndr` 内部经过 `then` 之类的适配器之后，再往下的子操作就看不到了。

## get_allocator（[exec.get.allocator]）

¶2 `get_allocator(env)` 等价于 *MANDATE-NOTHROW*(*AS-CONST*(env).query(get_allocator))。*Mandates*：结果满足 *simple-allocator*。**没有默认值**：环境不回答就是非良构。需要默认值的地方，规范会显式写 `query-with-default`（[[exec.snd]]）或回落到 `allocator<void>`（如 [[exec.spawn]]）。

¶3 转发查询。

## get_stop_token（[exec.get.stop.token]）

¶2 `get_stop_token(env)`：

- ¶2.1 若 *AS-CONST*(env).query(get_stop_token) 良构，取它（noexcept，*Mandates*：满足 `stoppable_token`）；
- ¶2.2 否则 `never_stop_token{}`。

这是整个库**取消**机制的入口（停止令牌本身在 [[thread.stoptoken]]）：发送器在 start 时取接收器环境的停止令牌，在上面注册回调；调用者通过对应的 stop source 请求停止，操作尽快以 `set_stopped` 完成。默认 `never_stop_token` 表示"不可能被请求停止"——这时 `unstoppable_token<never_stop_token>` 为 true，许多发送器借此在**类型层面**去掉 `set_stopped_t()` 签名（例如 `run_loop` 的调度发送器，[[exec.run.loop]]）。

¶3 转发查询。

## get_env（[exec.get.env]）

¶1 `execution::get_env(o)`：

- ¶1.1 若 *AS-CONST*(o).get_env() 良构，取它（noexcept，*Mandates*：满足 *queryable*）；
- ¶1.2 否则 `env<>{}`。

¶2 `get_env(o)` 的值在 `o` 有效期间有效。

¶3 注 1：对发送器，`get_env` 返回它的**属性**；对接收器，返回它的**执行环境**。

注意定制点是成员函数 `get_env()`，而不是 `query`。

## get_domain（[exec.get.domain]）

¶1 `get_domain` 问可查询对象关联的**执行 domain 标签**（[[g:execution-domain]]，用法见 [[exec.snd.transform]]）。

¶2 `get_domain(env)` 是 *MANDATE-NOTHROW*(D())，`D` 是下列第一个良构表达式的类型：

- ¶2.1 `auto(AS-CONST(env).query(get_domain))`——环境直接回答；
- ¶2.2 `get_completion_domain<set_value_t>(get_scheduler(env), HIDE-SCHED(env))`——环境里有调度器，就问那个调度器的 value 完成 domain；
- ¶2.3 `default_domain()`。

所以 domain 总有一个答案，并且结果是 domain 类型的**默认构造值**：domain 只是一个用来选重载的标签，不携带状态。

¶3 转发查询。

## get_scheduler（[exec.get.scheduler]）

¶1 问可查询对象关联的调度器——"调用者希望后续工作在哪里跑"。

¶2 `get_scheduler(env)` 等价于

```cpp
get_completion_scheduler<set_value_t>(
  MANDATE-NOTHROW(AS-CONST(env).query(get_scheduler)),
  HIDE-SCHED(env))
```

*Mandates*：若良构，结果满足 `scheduler`。

外面多套的一层 `get_completion_scheduler` 是一个**规范化**步骤：环境报告的调度器 `s` 可能是一个"包装"调度器，它的调度发送器实际在另一个调度器 `s2` 上完成（比如一个把工作转交给线程池的调度器适配器）。按 [[exec.get.compl.sched]] 的递归规则，`get_scheduler` 最终给出的是**真正执行工作**的那个调度器。

¶3 转发查询。

## get_start_scheduler（[exec.get.start.scheduler]）

¶1 问"一个操作将要或已经在哪个调度器上被**启动**"。

¶2 `get_start_scheduler(env)` 等价于 *MANDATE-NOTHROW*(*AS-CONST*(env).query(get_start_scheduler))；若良构，*Mandates* 结果满足 `scheduler`。没有默认值。

¶3 转发查询。

¶4 这是本节唯一一条对**行为**施加要求的段落：

!!! std
    an operation state that is the result of calling connect(sndr, rcvr) shall, if it is started, be started on an execution agent associated with the scheduler get_start_scheduler(get_env(rcvr)).

即：如果接收器的环境回答了 `get_start_scheduler`，那么 connect 出来的操作状态若被启动，**必须**在该调度器的执行代理上启动。这是一条**对调用者的要求**：谁在环境里声称"你在 X 上被启动"，谁就得真的在 X 上调用 `start`。发送器因此可以信任这个信息，例如 `affine`（[[exec.task]]）用它决定"完成后要回到哪里"，`on`（[[exec.on]]）用它记住"出发地"，`let_value` 把前驱的完成调度器作为后继的 start 调度器传下去（[[exec.let]]）。

!!! note "get_scheduler 与 get_start_scheduler"
    `get_scheduler` 是一个**偏好**："如果你需要一个调度器来跑东西，用这个"。`get_start_scheduler` 是一个**事实**："你正在这里被启动"。`sync_wait` 的环境两者都回答为它内部 `run_loop` 的调度器（[[exec.consumers]]），因为它确实在驱动 run_loop 的那个线程上调用 `start`。

## get_delegation_scheduler（[exec.get.delegation.scheduler]）

¶1 问一个可以把工作**委托**过去的调度器，用于[[g:forward-progress-delegation|前进保证委托]]（[[intro.progress]]）。

¶2 等价于 *MANDATE-NOTHROW*(*AS-CONST*(env).query(get_delegation_scheduler))；*Mandates* 结果满足 `scheduler`。

¶3 转发查询。

场景：一个只提供弱并行前进保证的执行资源（比如 GPU）在执行中需要阻塞等待某件事，按 [[intro.progress]] 的规则，阻塞的代理要把前进保证委托给某个能保证并发前进的代理。`sync_wait` 阻塞调用线程时，就在环境里通过这个查询提供它的 `run_loop` 调度器：被等待的工作可以把需要"一定能跑起来"的任务调度到那里，由被阻塞的线程亲自执行（[[exec.sync.wait#11]] 注 1）。

## get_forward_progress_guarantee（[exec.get.fwd.progress]）

```cpp
enum class forward_progress_guarantee { concurrent, parallel, weakly_parallel };
```

¶1 问调度器：其执行资源创建的执行代理提供哪一级前进保证（[[intro.progress]]）。

¶2 只能问调度器：`decltype((sch))` 不满足 `scheduler` 时非良构。等价于 *MANDATE-NOTHROW*(*AS-CONST*(sch).query(get_forward_progress_guarantee))，*Mandates* 类型为 `forward_progress_guarantee`。

¶3 返回 `concurrent`，则所有代理必须提供[[g:concurrent-forward-progress|并发前进保证]]；返回 `parallel`，则至少提供[[g:parallel-forward-progress|并行前进保证]]。返回 `weakly_parallel` 不施加额外要求。

[[exec.sched]] 的 `scheduler` 概念把 `get_forward_progress_guarantee(sch)` 良构列为必要条件，所以**每个调度器都必须实现 `query(get_forward_progress_guarantee_t)`**——这是调度器唯一一个没有默认值、又必须回答的查询。

## get_completion_scheduler（[exec.get.compl.sched]）

¶1–3 `get_completion_scheduler<Tag>` 是查询对象**模板**；`get_completion_scheduler<Tag>(get_env(sndr), envs...)` 从发送器的**属性**中读出 `Tag` 处置的[[g:completion-scheduler|完成调度器]]。可以附带接收器环境作为额外实参：有些发送器只有知道了环境才能回答（例如 `just()` 在调用者所在的调度器上完成，见 [[exec.snd]] 的 *inline-attrs*）。

¶4 ***RECURSE-QUERY*(sch1, envs...)**：令 `sch2` 为 *TRY-QUERY*(sch1, get_completion_scheduler<set_value_t>, envs...)；若 `sch2` 非良构，或与 `sch1` 同类型且相等，结果是 `sch1`；否则递归 *RECURSE-QUERY*(sch2, envs...)。也就是说，**调度器也可以回答"我的完成调度器是谁"**，查询会一直追下去，直到不动点。

¶5 `Tag` 不是 `set_value_t`/`set_error_t`/`set_stopped_t` 之一时非良构。否则 `get_completion_scheduler<Tag>(q, envs...)`：

- ¶5.1 *RECURSE-QUERY*(*TRY-QUERY*(q, get_completion_scheduler<Tag>, envs...), envs...)，若良构（`envs` 只求值一次）；
- ¶5.2 否则，若 `q` 本身是调度器且 `envs` **非空**，取 `auto(q)`；
- ¶5.3 否则非良构。

*Mandates*：良构时结果满足 `scheduler`。

¶5.2 解释了为什么 `get_scheduler`（上文）可以把调度器直接塞给 `get_completion_scheduler<set_value_t>(sch, HIDE-SCHED(env))`：调度器不回答时，它就是自己的完成调度器。

¶6 若 `get_completion_scheduler<Tag>(get_env(sndr), envs...)` 良构，但发送器的完成签名里**没有**任何 `Tag` 签名（*count-of*(Tag()) == 0），程序非良构 {{ill-formed}}。不能报告一个根本不会发生的完成在哪里发生。

¶7 若发送器报告了完成调度器 `sch`，而它 connect 出来的操作在**不属于** `sch` 执行资源的执行代理上调用了该处置的完成函数，行为未定义 {{ub}}。

!!! warning "¶7 是一条强承诺"
    完成调度器不是"提示"。下游会**依赖**它：domain 的选择（[[exec.snd.transform]]）、`on` 记住"回到哪里"（[[exec.on]]）都读它；`affine` 在确认已经处于正确调度器上时允许省掉调度（[[exec.task]]）。一个错误报告完成调度器的发送器会让下游代码在错误的线程上运行，而这在标准看来是你的 UB，不是库的 bug。拿不准时，**不要报告**——让查询非良构永远是安全的。

¶8 `forwarding_query(get_completion_scheduler<Tag>)` 为 true。

## get_completion_domain（[exec.get.compl.domain]）

¶1–2 `get_completion_domain<Tag>(attrs, envs...)` 读出 `Tag` 处置的**完成 domain**。`Tag` 可以是 `void`、`set_value_t`、`set_error_t`、`set_stopped_t`，否则非良构。结果是 *MANDATE-NOTHROW*(D())，`D` 依次取：

- ¶2.1 *TRY-QUERY*(attrs, get_completion_domain<Tag>, envs...) 的类型（属性直接回答）；
- ¶2.2 `Tag` 为 `void` 时，`get_completion_domain<set_value_t>(attrs, envs...)` 的类型（`void` 就是"value 的"）；
- ¶2.3 先问 `Tag` 的完成调度器，再问那个调度器的 value 完成 domain；
- ¶2.4 `attrs` 本身是调度器且 `envs` 非空时，`default_domain`；
- ¶2.5 否则非良构。

¶3 与 `get_completion_scheduler` 一样：报告了 domain 却根本没有该处置的完成签名，非良构。

¶4 报告了完成 domain `D`，而完成函数在某个关联 domain 不是 `D` 的执行资源的代理上被调用，行为未定义。同时它是转发查询。

完成 domain 比完成调度器**更粗**：一个发送器可能不知道自己会在哪个具体调度器上完成（比如 `when_all` 在最后一个完成的子操作所在处完成），但知道那些调度器都属于同一个 domain（[[exec.snd.general#3]] 用 *COMMON-DOMAIN* 合并）。domain 决定"用哪个算法实现"，见 [[exec.snd.transform]]。

## get_await_completion_adaptor（[exec.get.await.adapt]）

¶1–2 问可查询对象关联的"await 完成适配器"：*MANDATE-NOTHROW*(*AS-CONST*(env).query(get_await_completion_adaptor))，无默认值。

¶3 转发查询。

它在 `as_awaitable` 中使用（[[exec.as.awaitable#8]]）：发送器的**属性**若提供了这个适配器 `a`，那么协程 `co_await sndr` 时实际 await 的是 `a(sndr)`。这给发送器作者一个钩子，在被协程等待前对自己做一次变换（例如调整完成方式以适应协程的恢复语义）。

## 陷阱

!!! pitfall "查询函数忘了 const 或 noexcept"
    所有标准查询都通过 *AS-CONST* 调用 `query`，并套上 *MANDATE-NOTHROW*。所以：
    - 非 const 的 `query` 成员根本不会被找到，查询要么回落到默认值（`get_stop_token` → `never_stop_token`，取消悄无声息地失效），要么非良构；
    - const 但非 noexcept 的 `query`，程序非良构。

    第一种尤其隐蔽：没有任何诊断，只是取消不起作用了。

## 思考题

!!! question "1. 没有 get_stop_token 的环境"
    `sync_wait` 的环境（[[exec.consumers]]）只回答三个调度器查询。`sync_wait(sndr)` 中的 `sndr` 能被取消吗？

<details markdown="1">
<summary>答案</summary>

不能从外部取消。*sync-wait-env* 不回答 `get_stop_token`，所以 `get_stop_token(get_env(rcvr))` 是 `never_stop_token{}`（[exec.get.stop.token] ¶2.2），没有任何人能请求停止。`sndr` 内部仍可能以 `set_stopped` 完成（例如 `just_stopped()`，或 `when_all` 的某个子操作自己选择停止），此时 `sync_wait` 返回空的 `optional`。想要可取消的 `sync_wait`，可以用 `write_env(sndr, prop(get_stop_token, src.get_token()))` 注入一个令牌。
</details>

!!! question "2. 为什么 forwarding_query 默认是 false？"
    如果默认为 true，会出什么问题？

<details markdown="1">
<summary>答案</summary>

`when_all` 会把它的接收器环境中的 `get_stop_token` 替换为自己内部 `inplace_stop_source` 的令牌（[[exec.when.all]]），这是"覆盖"而不是"转发"。但有些查询的含义是"关于直接调用者"的，比如一个假想的 `get_child_index`：外层适配器给它的第 0 个子操作回答 0；若这个查询默认被转发，那么穿过一层 `then` 后，`then` 的子操作也会以为自己是"第 0 个子操作"，而它根本不是 `when_all` 的直接子操作。默认不转发，迫使查询的作者显式声明"我的答案对所有后代都成立"。
</details>

## 小结

| 查询 | 问谁 | 默认值 | 转发 |
|---|---|---|---|
| `forwarding_query` | 查询对象 | 派生自 `forwarding_query_t` 则 true，否则 false | — |
| `get_allocator` | 环境 | 无 | 是 |
| `get_stop_token` | 环境 | `never_stop_token{}` | 是 |
| `get_env` | 发送器/接收器 | `env<>{}` | — |
| `get_domain` | 环境 | 调度器的 value 完成 domain，再退到 `default_domain` | 是 |
| `get_scheduler` | 环境 | 无（结果经完成调度器规范化） | 是 |
| `get_start_scheduler` | 环境 | 无；回答了就**必须**在那里启动 | 是 |
| `get_delegation_scheduler` | 环境 | 无 | 是 |
| `get_forward_progress_guarantee` | 调度器 | 无（调度器必须回答） | — |
| `get_completion_scheduler<Tag>` | 发送器属性/调度器 | 调度器 + 非空环境时为自身；报告了就必须在那里完成 | 是 |
| `get_completion_domain<Tag>` | 发送器属性/调度器 | 经由完成调度器；调度器 + 非空环境时为 `default_domain` | 是 |
| `get_await_completion_adaptor` | 发送器属性 | 无 | 是 |
