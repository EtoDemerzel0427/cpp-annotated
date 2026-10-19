---
title: 调度器
summary: scheduler 概念：可复制、可比较、不抛异常的执行资源句柄，schedule(sch) 给出一个转到该资源上执行的发送器。
status: draft
papers: P2300R10
related: exec.async.ops, exec.queries, exec.factories, exec.on, exec.run.loop, exec.par.scheduler, exec.task
tags: 标准库, std::execution, 调度器, 概念
updated: 2026-10-19
---

!!! tldr
    - 调度器是执行资源的轻量句柄：声明 `scheduler_concept`，提供 `schedule()` 和前进保证查询，可复制、可比较，这些操作都不抛异常。
    - `schedule(sch)` 返回的发送器成功时不带任何值，它的 value 完成调度器就是 `sch` 本身。
    - `sch1 == sch2` 为真意味着两者指向同一个执行资源，反过来不成立。
    - 调度器析构时不能阻塞等待工作完成；它不延长执行资源的生存期。
    - 不会以 error 完成的调度器（*infallible-scheduler*）是回到原调度器这类设施的前提。

[[exec.async.ops#10]] 把调度器定义为执行资源的抽象、发送器的工厂。本节把这个定义写成 `scheduler` 概念，并补上一组语义要求。标准库提供的调度器有 `run_loop` 的调度器（[[exec.run.loop]]）、`parallel_scheduler`（[[exec.par.scheduler]]），以及 `inline_scheduler` 和类型擦除的 `task_scheduler`（[[exec.task]]）。

Clang 23 的 libc++ 还没有实现 `std::execution` 的这部分，本页例子没有经过编译。

## 写一个调度器

```cpp title="thread-pool-scheduler.cpp"
namespace ex = std::execution;

class pool_scheduler {
  thread_pool* pool_;
public:
  using scheduler_concept = ex::scheduler_tag;

  explicit pool_scheduler(thread_pool& p) noexcept : pool_(&p) {}

  pool_sender schedule() const noexcept { return pool_sender{pool_}; }

  auto query(ex::get_forward_progress_guarantee_t) const noexcept {
    return ex::forward_progress_guarantee::parallel;
  }

  bool operator==(const pool_scheduler&) const noexcept = default;   // 同一个池即相等
};
// pool_sender 的属性须回答 get_completion_scheduler<set_value_t>，返回 pool_scheduler{*pool_}
```

`thread_pool` 和 `pool_sender` 是假想的类型。调度器本身只是一个指针大小的句柄，真正的工作由 `pool_sender` connect 出来的操作状态完成：它的 `start` 把自己挂到线程池队列上，被某个工作线程取出后调用 `set_value(rcvr)`。

## scheduler 概念（¶1）

```cpp
template<class Sch>
  concept scheduler =
    derived_from<typename remove_cvref_t<Sch>::scheduler_concept, scheduler_tag> &&
    queryable<Sch> &&
    requires(Sch&& sch) {
      { schedule(std::forward<Sch>(sch)) } -> sender;
      { get_forward_progress_guarantee(sch) } -> same_as<forward_progress_guarantee>;
    } &&
    equality_comparable<remove_cvref_t<Sch>> &&
    copyable<remove_cvref_t<Sch>>;
```

¶1 逐项看：

- **`scheduler_concept` 标签**：类型必须声明 `using scheduler_concept = scheduler_tag;`（或派生自它的类型）。只有主动声明的类型才是调度器，碰巧有 `schedule()` 成员的类型不会被误认。`sender`、`receiver`、`operation_state` 用同样的手法。
- **`schedule(sch)` 返回发送器**：`schedule` 是一个定制点对象，调用 `sch.schedule()`（[[exec.schedule]]）。有效的 `schedule` 调用就是 schedule-expression。
- **`get_forward_progress_guarantee(sch)` 必须良构**：每个调度器都要声明它的执行代理提供哪一级前进保证（[[exec.get.fwd.progress]]）。
- **可比较、可复制**：调度器像指针一样复制和比较。

## 调度发送器不带值（¶2）

¶2 设 `Sch` 是调度器类型，`Env` 是使 `sender_in<schedule_result_t<Sch>, Env>` 成立的环境类型，那么必须模型化 *sender-in-of*<schedule_result_t<Sch>, Env>。

*sender-in-of*（[[exec.snd.concepts#5]]）在这里的意思是：调度发送器唯一的 value 完成签名是 `set_value_t()`，不带任何数据。它仍然可以有 error 和 stopped 完成，比如调度失败或被取消。

为什么不让 `schedule(sch)` 直接接受一个函数？因为 `schedule(sch) | then(f)` 已经表达了在 `sch` 上执行 `f`，调用、异常转 `set_error` 都由 `then` 负责（[[exec.adapt]]）。`schedule` 只做转到某处这一件事，调度器作者只需实现最小的一块，`continues_on`、`starts_on`、`on` 等适配器（[[exec.on]]）也能复用它。

## 不抛异常，没有数据竞争（¶3）

¶3 有两条要求：

- `copyable` 和 `equality_comparable` 要求的操作（复制和移动、析构、`==`、`!=`）都不能以异常退出；
- 从不同线程[[intro.races|潜在并发]]地调用这些操作或 `schedule`，不能引入数据竞争。

调度器会被复制进各个操作状态，在任意线程上被比较、被 `schedule`。如果调度器内部有可变状态（比如统计计数），必须自己同步。

## 相等意味着同一个资源（¶4）

¶4 同一调度器类型的两个值，`sch1 == sch2` 返回 `true` 仅当二者共享同一个执行资源。

这里是仅当，不是当且仅当。相等能推出同一个资源，但同一个资源的两个调度器可以不相等，比如两个带不同优先级参数、指向同一个池的调度器。所以 `==` 可以用来判断已经在目标资源上、可以省掉一次切换，而不能用 `!=` 推出一定在不同资源上。

## 调度发送器的完成调度器（¶5–6）

¶5 如果 `get_completion_scheduler<set_value_t>(get_env(schedule(sch)))` 良构，它必须与 `sch` 相等。这把 [[exec.async.ops#12]] 的要求写成了可以检查的表达式。

¶6 对任意 `T` 和环境包 `envs`，直接问调度器和问它的调度发送器的属性，结果必须一致：

- `get_completion_domain<T>(sch, envs...)` 与 `get_completion_domain<T>(get_env(schedule(sch)), envs...)` 要么都非良构，要么类型相同；
- `get_completion_scheduler<T>(sch, envs...)` 与 `get_completion_scheduler<T>(get_env(schedule(sch)), envs...)` 要么都非良构，要么类型和值都相同。

有了这条，[[exec.get.scheduler]] 可以直接拿环境里的调度器问完成调度器，而不必真的调用一次 `schedule`。

## 析构不得阻塞（¶7）

¶7 调度器类型的析构函数不能阻塞，等待与 `schedule` 返回的发送器相连的接收器完成。

调度器是句柄，析构句柄不应顺便等所有工作做完。等待是执行资源本身（如 `run_loop` 的 `finish` 和 `run`）或 async scope 的 `join`（[[exec.scope]]）的职责。

这条也排除了一种常见的错误设计：用 `shared_ptr` 持有线程池，最后一个调度器析构时 `join` 所有线程。如果最后一个副本恰好在池里的工作线程上析构，这个线程就会等待自己。

!!! pitfall "调度器不延长执行资源的生存期"
    `run_loop loop; auto sch = loop.get_scheduler();` 之后，`loop` 析构时 `sch` 就失效了（[[exec.async.ops#10]]），之后 `schedule(sch)` 得到的发送器和由它产生的操作状态也都失效。把调度器当作指针看待。

## infallible-scheduler（¶8）

```cpp
template<class Sch, class Env>
  concept infallible-scheduler =
    scheduler<Sch> &&
    (same_as<completion_signatures<set_value_t()>,
             completion_signatures_of_t<decltype(schedule(declval<Sch>())), Env>> ||
     (!unstoppable_token<stop_token_of_t<Env>> &&
      (same_as<completion_signatures<set_value_t(), set_stopped_t()>, …> ||
       same_as<completion_signatures<set_stopped_t(), set_value_t()>, …>)));
```

¶8 仅用于阐述的 *infallible-scheduler*<Sch, Env> 表示：在环境 `Env` 下，`schedule(sch)` 只能以 `set_value()` 完成；如果 `Env` 的停止令牌可能被请求停止，还允许 `set_stopped()`。总之不会以 error 完成。

它用 `same_as` 比较 `completion_signatures` 的特化，同一组签名换个顺序就是不同的类型，所以条文把两种顺序都列了出来。

需要它的是保证能回到某个调度器的设施：

- `task_scheduler` 的构造函数要求被擦除的调度器满足 *infallible-scheduler*<Sch, env<>>（[[exec.task.scheduler]]）；
- `affine` 要求接收器环境能回答 `get_start_scheduler`，且答案满足它，否则 `affine` 发送器的 `get_completion_signatures` 以异常退出（[[exec.affine]]）。

道理相同：如果回到原调度器这一步本身可能失败，失败时就没有地方报告错误，因为错误完成本该在原调度器上发生，而我们恰恰回不去。`run_loop` 的调度器满足它，其调度发送器的完成签名只有 `set_value_t()`，或再加 `set_stopped_t()`（[[exec.run.loop]]）。`parallel_scheduler` 的后端允许以 `set_error` 结束一次调度（[[exec.parschedrepl.psb]]），所以不能指望它满足这个概念。

## 思考题

!!! question "一个永远返回 true 的 =="
    写一个调度器，`operator==` 总是返回 `true`，但每个对象实际有自己的线程。违反了哪条规则？会出什么问题？

<details markdown="1">
<summary>答案</summary>

违反了 ¶4：相等的调度器必须共享同一个执行资源。

下游基于相等性的推理都会出错。[[exec.get.compl.sched]] 的 *RECURSE-QUERY* 以类型相同且相等作为递归终点；某个算法也可能判断已经在目标调度器上而省掉调度，结果代码在错误的线程上运行。程序没有满足概念的语义要求，后果由程序承担。
</details>

## 小结

- 声明 `scheduler_concept = scheduler_tag`，提供 `schedule()` 和 `query(get_forward_progress_guarantee_t)`，可复制、可比较。
- 复制、比较、析构不抛异常；并发调用 `schedule` 不引入数据竞争。
- `==` 为真意味着同一执行资源。
- 调度发送器的 value 完成不带数据，value 完成调度器等于原调度器。
- 析构不得等待工作完成。
- *infallible-scheduler* 不会以 error 完成，回到原调度器的设施依赖它。
