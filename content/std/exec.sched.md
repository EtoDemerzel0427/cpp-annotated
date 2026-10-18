---
title: 调度器
summary: scheduler 概念——可复制、可比较、不抛异常的执行资源句柄，schedule(sch) 给出"跳到这里"的发送器；相等即同一资源；schedule 发送器的完成调度器就是它自己；析构不得阻塞；infallible-scheduler
status: done
papers: P2300R10
related: exec.async.ops, exec.queries, exec.factories, exec.on, exec.run.loop, exec.par.scheduler, exec.task
tags: 标准库, std::execution, 调度器, 概念
updated: 2026-10-18
---

[[exec.async.ops#10]] 把调度器定义为"执行资源的抽象，是发送器的工厂"。本节把这个定义落实成 `scheduler` 概念，并补上一组语义要求。读完你应该能回答：自己写一个调度器需要提供什么；两个调度器 `==` 意味着什么；调度器析构时能不能等工作做完。

标准库提供的调度器：`run_loop` 的调度器（[[exec.run.loop]]）、`parallel_scheduler`（[[exec.par.scheduler]]）、`inline_scheduler` 与类型擦除的 `task_scheduler`（[[exec.task]]）。

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

逐项看：

- **`scheduler_concept` 标签**：类型必须声明 `using scheduler_concept = scheduler_tag;`（或派生自它的类型）。这是**选择加入**（opt-in）：只有声明了标签的类型才是调度器，防止一个碰巧有 `schedule()` 成员的类型被误认。`sender`、`receiver`、`operation_state` 用的是同样的手法。
- **`schedule(sch)` 返回发送器**：`schedule` 是一个 CPO，`schedule(sch)` 等价于 `sch.schedule()`（[[exec.schedule]]）。有效的 `schedule` 调用就是 [[exec.async.ops]] 中说的 schedule-expression。
- **`get_forward_progress_guarantee(sch)`** 必须良构：每个调度器都要声明自己的代理提供哪一级前进保证（[[exec.get.fwd.progress]]）。
- **`equality_comparable` 与 `copyable`**：调度器是轻量**句柄**，像指针一样复制、比较。

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
// pool_sender 的属性须回答 get_completion_scheduler<set_value_t>，返回 pool_scheduler{*pool}（见 ¶5）
```

## 调度发送器的类型约束（¶2）

¶2 设 `Sch` 是调度器类型，`Env` 是使 `sender_in<schedule_result_t<Sch>, Env>` 成立的环境类型，则 *sender-in-of*<schedule_result_t<Sch>, Env> 必须被模型化。

*sender-in-of*<S, Env>（[[exec.snd.concepts#5]]，此处不带额外的值类型）的意思是：S 的 value 完成签名**恰好是 `set_value_t()`**——没有任何结果数据。这把 [[exec.async.ops#10]] 中"成功时以空数据集完成"落实到了类型上。schedule 发送器仍然可以有 error 和 stopped 完成（调度失败、被取消）。

## 不抛异常、无数据竞争（¶3）

¶3 两条：

- `copyable` 和 `equality_comparable` 所要求的操作（复制/移动构造与赋值、析构、`==`、`!=`）都**不得以异常退出**；
- 这些操作以及调度器类型的 `schedule` 函数，从不同线程**潜在并发**（[[intro.races]]）地调用时，不得引入数据竞争。

第二条很关键：调度器会被复制到各个操作状态里，在任意线程上被比较、被 `schedule`。一个调度器内部如果有可变状态（比如统计计数），必须自己同步。

## 相等的含义（¶4）

¶4 同一调度器类型的两个值 `sch1 == sch2` 返回 true，**仅当**二者共享同一个关联执行资源。

注意是"仅当"（only if），不是"当且仅当"：相等 ⇒ 同一资源；但同一资源的两个调度器**可以**不相等（比如带不同优先级参数的两个调度器指向同一个池）。所以 `==` 可以用来做"已经在目标资源上，可以省掉一次切换"这类判断，而不能用 `!=` 推出"一定在不同资源上"。

## 调度发送器的完成调度器（¶5–6）

¶5 若 `get_completion_scheduler<set_value_t>(get_env(schedule(sch)))` 良构，它必须与 `sch` **相等**。这把 [[exec.async.ops#12]] 的"调度发送器必须有等于原调度器的 value 完成调度器属性"写成了可检查的表达式。

¶6 对调度器 `sch`、类型 `T`、环境包 `envs`，下面两组表达式要么都非良构，要么都良构且类型相同（第二组还要求值相同）：

- `get_completion_domain<T>(sch, envs...)` 与 `get_completion_domain<T>(get_env(schedule(sch)), envs...)`；
- `get_completion_scheduler<T>(sch, envs...)` 与 `get_completion_scheduler<T>(get_env(schedule(sch)), envs...)`。

也就是说，**调度器本身**回答完成调度器/完成 domain 查询时，答案必须与它的调度发送器的属性一致。这让 [[exec.get.scheduler]] 可以直接拿环境里的调度器去问 `get_completion_scheduler`，而不必真的调用一次 `schedule`。

## 析构不得阻塞（¶7）

¶7 调度器类型的析构函数**不得阻塞**等待已与 `schedule` 返回的发送器相连的接收器完成。

调度器是句柄，析构一个句柄不应该"顺便等所有工作做完"。等待的职责属于执行资源本身（如 `run_loop` 的 `finish`/`run`）或者 async scope（[[exec.scope]]）的 `join`。这条也排除了一种常见的错误设计：用 `shared_ptr` 持有线程池、在最后一个调度器析构时 `join` 所有线程——如果最后一个调度器副本恰好在池里的某个工作线程上析构，就会自己等自己。

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

¶8 仅用于阐述的 *infallible-scheduler*<Sch, Env>：在环境 `Env` 下，`schedule(sch)` **只能**以 `set_value()` 完成——除非 `Env` 的停止令牌可能被请求停止，那时还允许 `set_stopped()`。总之**不会以 error 完成**。

注意它用 `same_as` 比较 `completion_signatures` 的特化，所以同一组签名换个顺序就是不同的类型——规范为此把两种顺序都列了出来。

谁需要它？需要"保证能回到某个调度器"的设施：

- `task_scheduler` 的构造函数要求被擦除的调度器满足 *infallible-scheduler*<env<>>（[[exec.task.scheduler]]）；
- `affine` 要求 `get_start_scheduler` 给出的调度器满足它，否则 `affine` 发送器的 `get_completion_signatures` 以异常退出（[[exec.affine]]）。

道理是一样的：如果"回到原调度器"这一步本身可能失败，那么失败时就**没有地方**可以报告这个错误——错误完成本该在原调度器上发生，而我们恰恰回不去。`run_loop` 的调度器满足它：它的调度发送器的完成签名被规定为 `set_value_t()`，或再加 `set_stopped_t()`（[[exec.run.loop]]）。`parallel_scheduler` 则不同：它的后端被允许以 `set_error` 结束一次调度（[[exec.parschedrepl.psb]]），所以不能指望它满足这个概念。

## 陷阱

!!! pitfall "把调度器当执行资源"
    调度器只是句柄。`run_loop loop; auto sch = loop.get_scheduler();` 之后，`loop` 析构时 `sch` 即失效（[[exec.async.ops#10]]），之后 `schedule(sch)` 得到的发送器和由它产生的操作状态都失效。像对待指针一样对待调度器：它不延长任何东西的生存期。

## 思考题

!!! question "1. 一个永远返回 true 的 =="
    写一个调度器，`operator==` 总返回 true，但实际上每个对象有自己的线程。违反了哪条规则？会出什么问题？

<details markdown="1">
<summary>答案</summary>

违反 ¶4：相等的调度器必须共享同一执行资源。后果是下游算法基于相等性做的推理全部失效：例如 [[exec.get.compl.sched]] 的 *RECURSE-QUERY* 以"同类型且相等"作为递归终止条件；`affine` 或某个 domain 定制可能判断"已经在目标调度器上"而省略调度，结果代码在错误的线程上运行。规范把这种情况归为程序没有满足概念的语义要求，后果由程序承担。
</details>

!!! question "2. 为什么 schedule 发送器不带值？"
    设计上为什么不让 `schedule(sch)` 直接接受一个函数、并以函数的返回值完成？

<details markdown="1">
<summary>答案</summary>

因为这样做是可组合的：`schedule(sch) | then(f)` 已经表达了"在 `sch` 上执行 `f` 并以其结果完成"，`then` 负责调用、异常转 `set_error`、返回 `void` 的处理（[[exec.adapt]]）。让 `schedule` 只做"转移到某处"这一件事，调度器的实现者只需实现最小的一块；而"转移到某处"本身还能被 `continues_on`、`starts_on`、`on` 等适配器复用（[[exec.on]]）。¶2 用 *sender-in-of* 把"无数据"写进了类型约束，正是为了让这些适配器能依赖它。
</details>

## 小结

- 声明 `scheduler_concept = scheduler_tag`，提供 `schedule()` 与 `query(get_forward_progress_guarantee_t)`，可复制、可比较。
- 复制、比较、析构不抛异常；并发调用 `schedule` 无数据竞争。
- `==` 为真 ⇒ 同一执行资源。
- 调度发送器：value 完成不带数据；value 完成调度器等于原调度器。
- 析构不得等待工作完成。
- *infallible-scheduler*：不会以 error 完成，"回到原处"类设施依赖它。
