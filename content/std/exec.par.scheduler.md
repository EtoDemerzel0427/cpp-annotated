---
title: 并行调度器
summary: get_parallel_scheduler() 返回整个程序共享的并行调度器；它的全部工作经由一个可替换的虚接口 parallel_scheduler_backend 完成，bulk 在 par 策略下才会被拆分到多个线程。
status: draft
covers: exec.parschedrepl, exec.parschedrepl.general, exec.parschedrepl.recvproxy, exec.parschedrepl.query, exec.parschedrepl.psb
papers: P2300R10
related: exec.sched, exec.bulk, exec.snd.transform, exec.task, intro.progress, dcl.fct.def.replace, algorithms.parallel
tags: 标准库, std::execution, 调度器, 线程池, 可替换函数
updated: 2026-10-19
---

!!! tldr
    - `get_parallel_scheduler()` 返回标准库提供的、整个程序共享的线程池调度器，它的执行代理提供并行前进保证。
    - 实现藏在虚接口 `parallel_scheduler_backend` 后面。程序可以定义自己的 `query_parallel_scheduler_backend()` 替换默认实现，就像替换 `operator new` 一样。
    - 后端看不到具体的接收器类型：接收器被包装成带虚函数的代理，错误统一为 `exception_ptr`，簿记数据放在调用者预先提供的存储里，调度本身不需要分配内存。
    - `bulk` 只有在执行策略是 `par` 或 `par_unseq` 时才会被拆分；用 `seq` 时全部迭代作为一个整体，在一个线程上顺序执行。

本页的例子用到 C++26 的 `std::execution`。本机 Clang 23 附带的 libc++ 还没有实现这部分库，例子都没有经过编译验证，因此不加判定标记。

## 标准库自带的线程池

```cpp title="parallel-scheduler.cpp"
namespace ex = std::execution;

auto sch = ex::get_parallel_scheduler();
static_assert(ex::scheduler<decltype(sch)>);

std::vector<float> v(n);
std::this_thread::sync_wait(
  ex::schedule(sch)
  | ex::bulk(ex::par, n, [&](std::size_t i) { v[i] = f(i); }));
```

在 `std::execution` 里，[[g:scheduler|调度器]]代表一个可以安排工作的执行资源。`run_loop` 不创建线程，`inline_scheduler` 就在当前线程执行，它们都不是线程池。`parallel_scheduler` 补上了这一块：一个由实现提供、整个程序共享的并行执行资源。

它的设计有两个目标。第一是共享：程序里的各个库如果各建一个线程池，线程数会远超核心数，互相争抢；`parallel_scheduler` 让大家默认用同一个系统级资源。第二是可替换：嵌入式系统、游戏引擎、已有线程池的框架需要把它接到自己的实现上。

## parallel_scheduler [exec.par.scheduler]

`parallel_scheduler` 的类定义是未指定的，标准只描述它的行为。

¶1 它模型化 `scheduler` 概念。

¶2 每个 `parallel_scheduler` 对象关联一个后端对象，记作 *BACKEND-OF*(sch)。

¶3 `get_forward_progress_guarantee(sch)` 的值是 `forward_progress_guarantee::parallel`。并行前进保证（[[intro.progress]]）是说一个执行代理一旦开始执行就会持续前进，但不保证它一定会开始。所以不要在这个调度器上做等待另一个尚未开始的任务这类阻塞同步，那需要更强的并发前进保证。

¶4 两个 `parallel_scheduler` 相等，当且仅当它们的后端是同一个对象。

¶13 `get_parallel_scheduler()` 先调用 `parallel_scheduler_replacement::query_parallel_scheduler_backend()` 得到后端指针 `eb`。`eb` 为空时调用 `terminate`，否则返回关联 `eb` 的调度器。

### 接收器代理和预分配存储（¶5–6）

后端是一个虚接口，不能是模板，所以它看不到具体的[[g:receiver|接收器]]类型。标准用两个概念跨过这道类型擦除的边界。

¶5 接收器 `rcvr` 的**代理**（proxy）是一个以某个类 `B` 为类型的左值 `r`：`r.set_value()`、`r.set_error(e)`（`e` 是 `exception_ptr`）、`r.set_stopped()` 分别等价于对 `rcvr` 调用相应的完成函数。代理用虚函数擦除了三个完成函数的具体类型。

¶6 代理的**预分配后端存储**（preallocated backend storage）是一个 `span<byte>`，在代理上调用任一完成函数之前一直有效，后端可以改写它。注 1 说明，后端可以把它当作临时存储，用于经由后端接口启动的操作。

这块存储位于[[g:operation-state|操作状态]]之中，后端可以把自己的簿记数据（比如队列节点）放在里面。于是即使经过了类型擦除，整个调度过程仍然可以不分配内存。

¶7 `schedule(sch)` 返回的发送器连接到 `rcvr` 并启动后，调用 `b.schedule(r, s)`，其中 `r` 是以 `receiver_proxy` 为基类的代理，`s` 是预分配存储；其他完成原样转发。条文的字面写法是如果 `sndr` 成功完成，则调用 `b.schedule(r, s)`，读起来像是因果颠倒，因为正是 `b.schedule` 让发送器完成。按意图理解即可：启动后调用后端，由后端通过 `r` 完成。

### bulk 的定制（¶8–12）

`bulk(policy, shape, f)` 对 `[0, shape)` 中的每个下标调用一次 `f`（[[exec.bulk]]）。它的默认实现是顺序执行的，并行来自调度器的定制。

¶8 `get_domain(sch)` 返回阐述用的类型 *parallel-scheduler-domain*，它有两个 `transform_sender` 重载，分别改写 `bulk_chunked` 和 `bulk_unchunked` 发送器。`bulk` 本身先被 `default_domain` 改写为 `bulk_chunked`（[[exec.bulk#4]]），再被这个 domain 改写，这是 [[exec.snd.transform]] 中递归变换的典型例子。

¶9–10 改写时从发送器中取出执行策略 `pol`、形状 `shape` 和函数 `f`，并定义一个布尔值 `p`：`pol` 是 `parallel_policy` 或 `parallel_unsequenced_policy`（可带 cv 限定）时为 true，是实现定义的执行策略时由实现决定 {{impl}}，否则（`seq`、`unseq`）为 false。

¶11 对 `bulk_chunked`，前驱以值 `vals` 完成后，调用 `b.schedule_bulk_chunked(p ? shape : 1, r, s)`。后端每调用一次 `r.execute(i, j)`，`p` 为 true 时等价于 `f(i, j, args...)`，为 false 时等价于 `f(0, shape, args...)`。

¶12 对 `bulk_unchunked`，调用 `b.schedule_bulk_unchunked(p ? shape : 1, r, s)`。`r.execute(i, i + 1)` 在 `p` 为 true 时等价于 `f(i, args...)`，为 false 时等价于按顺序对全部下标调用一遍 `f`。

`p` 为 false 时形状缩成 1。`seq` 和 `unseq` 不允许并行执行 `f`，于是全部工作作为一次迭代交给后端，由一个执行代理顺序完成。工作仍然在线程池上执行，只是不拆分。这也是 `bulk` 必须带执行策略实参的原因：它决定了定制实现能否拆分。

!!! lawyer "¶8 用的是 get_domain"
    [[exec.snd.transform]] 查找的是发送器属性的完成 domain（`get_completion_domain`），而 ¶8 写的是 `get_domain(sch)`。两者通过 [[exec.get.compl.domain]] 的 ¶2.3 连接起来：完成 domain 可以经由完成调度器去查询该调度器的 value 完成 domain。条文没有逐字说明两个查询的答案如何保持一致，按意图理解为 `parallel_scheduler` 的 domain 就是 *parallel-scheduler-domain* 即可。

## 替换实现 [exec.parschedrepl]

[exec.parschedrepl.general] ¶1 命名空间 `parallel_scheduler_replacement` 中的设施让用户可以替换 `parallel_scheduler` 的默认实现。

### 入口：query_parallel_scheduler_backend [exec.parschedrepl.query]

```cpp title="replace-backend.cpp"
namespace std::execution::parallel_scheduler_replacement {
  shared_ptr<parallel_scheduler_backend> query_parallel_scheduler_backend() {
    static auto backend = make_shared<my_engine_backend>();   // 接到引擎自己的任务系统
    return backend;
  }
}
```

¶3 这个函数是**可替换函数**（[[g:replaceable-function]]，[[dcl.fct.def.replace]]）：程序在任何一个翻译单元里定义它，就替换了实现提供的默认版本。替换版本不应返回空指针，否则 `get_parallel_scheduler()` 会调用 `terminate`。

¶1–2 它返回并行调度器的实现对象 `p`：`p.get()` 指向某个处于生命期内的最终派生对象 `o` 的 `parallel_scheduler_backend` 基类子对象，只要还有某个 `shared_ptr` 与 `p` 共享所有权，`o` 就不会被销毁。

### 后端接口 [exec.parschedrepl.psb]

```cpp
struct parallel_scheduler_backend {
  virtual ~parallel_scheduler_backend() = default;
  virtual void schedule(receiver_proxy&, span<byte>) noexcept = 0;
  virtual void schedule_bulk_chunked(size_t, bulk_item_receiver_proxy&,
                                     span<byte>) noexcept = 0;
  virtual void schedule_bulk_unchunked(size_t, bulk_item_receiver_proxy&,
                                       span<byte>) noexcept = 0;
};
```

三个纯虚函数都是 `noexcept`，失败只能通过代理的 `set_error` 报告。

¶1 三个函数有同样的前置条件（另见 ¶4、¶7）：后端对象、代理 `r` 和存储 `s` 都要活到在 `r` 上开始调用完成函数之后。也就是说，后端在调用完成函数之前可以放心使用这三者，开始调用之后就不能再碰。

¶2 `schedule(r, s)` 必须恰好调用 `r.set_value()`（成功）、`r.set_error(eptr)`（出错）、`r.set_stopped()`（被取消）之一，而且 `set_value` 必须在这个后端所代表的执行上下文的执行代理上调用。¶3 `s` 可以在操作期间用作临时存储。

¶5 `schedule_bulk_chunked(n, r, s)` 的要求：

- ¶5.1 最终恰好调用一个完成函数；
- ¶5.2 每次调用 `r.execute(b, e)` 都满足 `0 ≤ b < e ≤ n`；
- ¶5.3 每个下标 `i ∈ [0, n)` 至多落在一次 `execute` 调用的区间里；
- ¶5.4 如果调用了 `set_value`，每个下标恰好落在一次调用的区间里；
- ¶5.5 所有 `execute` 调用都先于完成函数的调用发生（happens before）；
- ¶5.6 所有 `execute` 和 `set_value` 调用都在该执行上下文的执行代理上进行。

¶8 `schedule_bulk_unchunked(n, r, s)` 的要求相同，只是每次调用都是 `execute(i, i + 1)` 的形式。

这些要求对应 [[exec.bulk#9]] 对 `bulk` 的语义要求：成功时每个下标恰好执行一次；出错或取消时可能只执行了一部分，但不会重复执行。

### 代理类 [exec.parschedrepl.recvproxy]

```cpp
namespace std::execution::parallel_scheduler_replacement {
  struct receiver_proxy {
  protected:
    virtual bool query-env(unspecified) noexcept = 0;   // 仅用于阐述
  public:
    virtual void set_value() noexcept = 0;
    virtual void set_error(exception_ptr) noexcept = 0;
    virtual void set_stopped() noexcept = 0;
    template<class P, class-type Query>
      optional<P> try_query(Query q) const noexcept;
  };

  struct bulk_item_receiver_proxy : receiver_proxy {
    virtual void execute(size_t, size_t) noexcept = 0;
  };
}
```

¶1 `receiver_proxy` 代表一个接收器，后端通过它触发完成。`bulk_item_receiver_proxy` 多了 `execute(b, e)`，后端用它执行 bulk 的一段迭代。错误完成只能是 `exception_ptr`，因为经过类型擦除之后，后端只能使用一种统一的错误类型。

¶2–3 后端可以用 `try_query<P>(q)` 查询被代理接收器的环境。`P` 必须是 cv 无限定的非数组对象类型。实现只支持一组由实现定义的查询和结果类型；查询不受支持或者 `q(env)` 非良构时返回 `nullopt`，`q(env)` 的类型正好是 cv `P` 时返回它的值，否则返回一个由实现定义的值。

¶4 停止令牌查询 `get_stop_token_t` 一定受支持，而且一定可以得到 `inplace_stop_token`。¶5 建议接收器的令牌是其他 `stoppable_token` 类型时，`try_query` 也把它适配成 `inplace_stop_token`，并在完成之前每次返回等价的令牌。这样后端只需要支持一种令牌类型，就能响应任何来源的取消请求。

## 常见误解

!!! pitfall "parallel_scheduler 上的 bulk 一定是并行的"
    只有执行策略为 `par` 或 `par_unseq`（或者实现定义的、允许并行的策略）时，domain 才把形状交给后端拆分。`bulk(seq, n, f)` 被缩成一次 `execute`，在一个线程上顺序执行全部迭代（¶10–12）。

!!! pitfall "后端在调用完成函数之后继续使用存储"
    ¶1 只保证 `r` 和 `s` 活到完成函数开始执行。完成函数可能立即销毁整个操作状态，`s` 所在的内存随之释放。后端如果在调用 `r.set_value()` 之后还要访问 `s` 中的节点，比如把它从内部队列中摘除，就会访问已释放的内存。所有簿记工作必须在调用完成函数之前做完。

## 思考题

!!! question "1. 为什么后端接口用虚函数而不是模板？"

<details markdown="1">
<summary>答案</summary>

后端要由一个可替换函数提供（[exec.parschedrepl.query] ¶3），也就是在链接时由另一个翻译单元甚至另一个库决定。模板必须在使用点可见，做不到链接时替换；虚接口只需要一个稳定的 ABI。代价是类型擦除：接收器要包装成 `receiver_proxy`，错误统一为 `exception_ptr`，环境只能通过 `try_query` 有限地访问。预分配存储则是为了在类型擦除的同时保住不分配内存的性质。`task_scheduler` 也复用了这个接口作为类型擦除的边界（[[exec.task]]）。
</details>

!!! question "2. 两次调用 get_parallel_scheduler() 的结果一定相等吗？"

<details markdown="1">
<summary>答案</summary>

不一定。¶4 规定两个调度器相等当且仅当后端是同一个对象，这取决于两次调用 `query_parallel_scheduler_backend()` 是否返回同一个对象。默认实现和上面那种用 `static` 局部变量的替换实现都会返回同一个对象，于是相等。但规范没有要求每次返回同一个对象，每次创建新后端的替换实现也是合法的，那时两个调度器不相等，而且确实代表两个执行资源。
</details>
