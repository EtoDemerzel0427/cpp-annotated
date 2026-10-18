---
title: 并行调度器
summary: get_parallel_scheduler() 返回系统提供的并行调度器（前进保证为 parallel）；所有操作经由一个可替换的后端 parallel_scheduler_backend（虚接口：schedule / schedule_bulk_chunked / schedule_bulk_unchunked，配合接收器代理与预分配存储）；其 domain 把 bulk_chunked / bulk_unchunked 改写为后端调用；用户可通过替换 query_parallel_scheduler_backend 换掉整个实现
status: done
covers: exec.parschedrepl, exec.parschedrepl.general, exec.parschedrepl.recvproxy, exec.parschedrepl.query, exec.parschedrepl.psb
papers: P2300R10
related: exec.sched, exec.bulk, exec.snd.transform, exec.task, intro.progress, dcl.fct.def.replace, algorithms.parallel
tags: 标准库, std::execution, 调度器, 线程池, 可替换函数
updated: 2026-10-18
---

`run_loop` 不创建线程，`inline_scheduler` 不切换线程——到此为止，标准库还没有提供一个"真正的线程池"。`parallel_scheduler` 补上了这一块：一个由实现提供、整个程序共享的并行执行资源，用 `get_parallel_scheduler()` 取得。

它的设计有两个目标：

1. **共享**：程序里不同的库各自创建线程池，会导致线程数远超核心数、互相争抢。`parallel_scheduler` 让所有人默认使用同一个系统级执行资源。
2. **可替换**：嵌入式系统、游戏引擎、已有自己线程池的框架需要把它接到自己的实现上。为此标准把实现隔离在一个**虚接口**（后端）后面，并让"取得后端"的函数成为**可替换函数**（[[dcl.fct.def.replace]]），就像 `operator new` 一样。

```cpp title="parallel-scheduler.cpp"
namespace ex = std::execution;

auto sch = ex::get_parallel_scheduler();
static_assert(ex::scheduler<decltype(sch)>);
// ex::get_forward_progress_guarantee(sch) == ex::forward_progress_guarantee::parallel

std::vector<float> v(n);
std::this_thread::sync_wait(
  ex::schedule(sch) | ex::bulk(ex::par, n, [&](std::size_t i) { v[i] = f(i); }));
```

## parallel_scheduler（[exec.par.scheduler]）

类定义的内容是 *unspecified* 的；规范只描述它的行为。

- ¶1 模型化 `scheduler`。
- ¶2 每个对象关联一个后端对象，*BACKEND-OF*(sch) 是 `*ptr`。
- ¶3 `get_forward_progress_guarantee(sch)` 为 `forward_progress_guarantee::parallel`：它的执行代理提供**并行**前进保证（[[intro.progress]]）——一旦开始执行就会持续前进，但不保证"一定会开始执行"。所以不要在它上面做"等待另一个尚未开始的任务"这类依赖并发前进保证的阻塞同步。
- ¶4 两个对象相等当且仅当它们的后端是同一个对象。

¶5 **接收器代理**：对接收器 `rcvr`，"以 `B` 为基类的 `rcvr` 的代理"是一个 `B` 类型的左值 `r`，`r.set_value()`、`r.set_error(e)`（`e` 为 `exception_ptr`）、`r.set_stopped()` 分别等价于对 `rcvr` 调用相应的完成函数。

¶6 **预分配后端存储**：一个 `span<byte>` `s`，在 `r` 上调用任一完成函数之前一直有效、可被改写。注 1：后端可以把它当作临时存储，用于通过后端接口启动的操作。

这两个概念是类型擦除的关键：后端是虚接口，不能是模板，所以它看不到具体的接收器类型；代理用虚函数把三个完成函数擦除掉。而预分配存储让后端可以把自己的簿记数据（比如队列节点）放在**调用者提供**的内存里——这块内存就在操作状态中，于是整个调度过程仍然可以不分配。

¶7 `schedule(sch)` 返回的发送器连接到 `rcvr` 并启动后：

- ¶7.1 原文写作"若 `sndr` 成功完成，则调用 `b.schedule(r, s)`"（`r` 是以 `receiver_proxy` 为基类的代理，`s` 是预分配存储）。字面上像是因果颠倒——`b.schedule` 才是让 `sndr` 完成的那一步；按意图理解为：启动后调用 `b.schedule(r, s)`，由后端通过 `r` 完成；
- ¶7.2 其他完成原样转发。

### 定制 bulk（¶8–12）

¶8 `get_domain(sch)` 返回阐述用类型 *parallel-scheduler-domain* 的值，它有两个 `transform_sender(set_value_t, sndr, env)` 重载，分别匹配 `bulk_chunked` 和 `bulk_unchunked` 发送器。

¶9 对传入的 `sndr`：`auto& [_, data, child] = sndr; auto& [pol, shape, f] = data;`。

¶10 `p`：执行策略为 cv `parallel_policy` 或 cv `parallel_unsequenced_policy` 时为 true；实现定义的执行策略为实现定义 {{impl}}；否则（`seq`、`unseq`）为 false。

¶11 `bulk_chunked` 的改写：`child` 以值 `vals` 完成时，调用 `b.schedule_bulk_chunked(p ? shape : 1, r, s)`，代理 `r` 的 `r.execute(i, j)` 等价于 `f(i, j, args...)`（`p` 为 true）或 `f(0, shape, args...)`（`p` 为 false）；其他完成原样转发。

¶12 `bulk_unchunked` 的改写类似：`b.schedule_bulk_unchunked(p ? shape : 1, r, s)`，`r.execute(i, i + 1)` 等价于 `f(i, args...)`（`p` 为 true）或对所有 `i` 顺序执行一遍循环（`p` 为 false）。

`p` 为 false 时把形状缩成 1：`seq`/`unseq` 不允许并行执行 `f`，于是整个工作被当作**一个**迭代交给后端，由一个执行代理顺序完成——仍然是在线程池上执行，只是不拆分。这也是为什么 [[exec.bulk]] 的执行策略实参必不可少：它决定了定制实现是否可以拆分。

`bulk(...)` 本身先由 `default_domain` 降级为 `bulk_chunked`（[[exec.bulk#4]]），再被这个 domain 改写——[[exec.snd.transform]] 中递归变换的典型例子。

¶13 `get_parallel_scheduler()`：设 `eb` 为 `parallel_scheduler_replacement::query_parallel_scheduler_backend()` 的结果。`eb == nullptr` 时调用 `terminate`；否则返回关联 `eb` 的 `parallel_scheduler`。

!!! lawyer "¶8 说的是 get_domain"
    ¶8 用的是 `get_domain(sch)`，而 [[exec.snd.transform]] 在阶段 1 查的是发送器属性的**完成 domain**（`get_completion_domain`）。二者通过 [[exec.get.compl.domain]] ¶2.3 连接：完成 domain 可以经由完成调度器去问"该调度器的 value 完成 domain"。调度器如何把 `get_domain` 与 `get_completion_domain` 的答案保持一致，这一段并没有逐字写出；读的时候按意图理解为"`parallel_scheduler` 的 domain 是 *parallel-scheduler-domain*"即可。

## 命名空间 parallel_scheduler_replacement（[exec.parschedrepl]）

[exec.parschedrepl.general] ¶1 其中的设施允许用户替换 `parallel_scheduler` 的默认实现。

### 接收器代理（[exec.parschedrepl.recvproxy]）

```cpp
namespace std::execution::parallel_scheduler_replacement {
  struct receiver_proxy {
  protected:
    virtual bool query-env(unspecified) noexcept = 0;   // exposition only
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

¶1 `receiver_proxy` 代表一个接收器，后端通过它触发完成操作；`bulk_item_receiver_proxy` 增加了 `execute(b, e)`，后端用它执行 bulk 的各个迭代区间。

注意 error 完成只能是 `exception_ptr`：类型擦除之后，后端只能用一种统一的错误类型。

¶2–3 `try_query<P>(q)`：在被代理接收器的环境上执行查询。*Mandates*：`P` 是 cv 无限定的非数组对象类型。若 `Query` 不在实现定义的受支持查询集合中、或 `P` 不在该查询受支持的结果类型集合中、或 `q(env)` 非良构，返回 `nullopt`；否则若 `q(env)` 的类型就是 cv `P`，返回它；否则返回一个实现定义的 `optional<P>` 值。

¶4 *Remarks*：`get_stop_token_t` 一定在受支持集合中，`inplace_stop_token` 一定是它受支持的结果类型。

¶5 *Recommended practice*：若 `P` 是 `inplace_stop_token`，而接收器的令牌是别的 `stoppable_token` 类型，`try_query` 应当返回一个 `inplace_stop_token`，在完成之前所有调用返回等价的令牌。即：实现应当把任意停止令牌**适配**成 `inplace_stop_token` 交给后端，让后端只需要支持一种令牌类型就能响应取消。

### query_parallel_scheduler_backend（[exec.parschedrepl.query]）

```cpp
shared_ptr<parallel_scheduler_backend> query_parallel_scheduler_backend();
```

¶1 返回并行调度器的实现对象。

¶2 *Returns*：对象 `p`，`p.get()` 指向某个生存期内的最终派生对象 `o` 的 `parallel_scheduler_backend` 基类子对象；只要存在某个 `q.owner_equal(p)` 为 true 的 `shared_ptr` 对象 `q`，`o` 的生存期就不会结束。

¶3 *Remarks*：此函数是**可替换的**（[[dcl.fct.def.replace]]）。

程序可以在任何一个翻译单元中定义自己的 `std::execution::parallel_scheduler_replacement::query_parallel_scheduler_backend()`，替换实现的默认版本——链接器选用程序的定义。这是"全局替换整个系统线程池"的入口：

```cpp title="replace-backend.cpp"
namespace std::execution::parallel_scheduler_replacement {
  shared_ptr<parallel_scheduler_backend> query_parallel_scheduler_backend() {
    static auto backend = make_shared<my_engine_backend>();   // 接到引擎自己的任务系统
    return backend;
  }
}
```

（`get_parallel_scheduler` 在结果为空指针时调用 `terminate`——替换版本不应返回空。）

### parallel_scheduler_backend（[exec.parschedrepl.psb]）

```cpp
struct parallel_scheduler_backend {
  virtual ~parallel_scheduler_backend() = default;
  virtual void schedule(receiver_proxy&, span<byte>) noexcept = 0;
  virtual void schedule_bulk_chunked(size_t, bulk_item_receiver_proxy&, span<byte>) noexcept = 0;
  virtual void schedule_bulk_unchunked(size_t, bulk_item_receiver_proxy&, span<byte>) noexcept = 0;
};
```

三个纯虚函数都是 `noexcept`：失败只能通过代理的 `set_error` 报告。

**`schedule(r, s)`**（¶1–3）：

- ¶1 *Preconditions*：`*this` 的生存期、`r` 所指对象的生存期、`s` 引用的存储期，都在 `r` 上完成函数**开始求值之后**才结束——后端在完成之前可以安全地使用这三者。
- ¶2 派生类必须保证：恰好求值 `r.set_value()`（成功）、`r.set_error(eptr)`（出错）或 `r.set_stopped()`（被取消）之一；对 `r.set_value()` 的调用发生在 `*this` 所代表的执行上下文的执行代理上。
- ¶3 `s` 可在操作期间用作临时存储。

**`schedule_bulk_chunked(n, r, s)`**（¶4–6）：

- ¶5.1 **最终**恰好调用一个完成函数；
- ¶5.2 若调用 `r.execute(b, e)`，则 `b`、`e` 在 `[0, n]` 中且 `b < e`；
- ¶5.3 对每个 `i ∈ [0, n)`，**至多**一次 `execute` 调用的区间包含 `i`；
- ¶5.4 若调用了 `r.set_value()`，则对每个 `i` **恰好**一次调用的区间包含 `i`；
- ¶5.5 所有 `execute` 调用都**发生在**完成函数调用之前（happens before）；
- ¶5.6 所有 `execute` 与 `set_value` 调用都在该执行上下文的代理上进行。

**`schedule_bulk_unchunked(n, r, s)`**（¶7–9）：同上，但每次 `execute(b, e)` 都满足 `e == b + 1`，每个 `i` 至多（成功时恰好）一次 `execute(i, i + 1)`。

这些契约精确对应 [[exec.bulk#9]] 对 `bulk` 结果的语义要求：成功时全覆盖；出错/取消时可能只执行了一部分，但不会重复执行。

## 陷阱

!!! pitfall "以为 parallel_scheduler 的 bulk 一定并行"
    只有执行策略为 `par` 或 `par_unseq`（或实现定义的允许并行的策略）时，domain 才会把形状交给后端拆分；`bulk(seq, n, f)` 被缩成一次 `execute`，在一个线程上顺序执行全部迭代（¶10–12）。

!!! pitfall "后端在完成之后继续使用存储"
    ¶1 的前置条件只保证 `r` 和 `s` 活到完成函数**开始**求值。后端实现若在调用 `r.set_value()` 之后还要访问 `s` 中的节点（例如把它从内部队列摘除），就是在使用可能已被释放的内存。必须先做完所有簿记工作，最后一步才调用完成函数。

## 思考题

!!! question "1. 为什么后端接口用虚函数而不是模板？"
    把 `parallel_scheduler_backend` 设计成带虚函数的类，而不是一个调度器概念，有什么必然性？

<details markdown="1">
<summary>答案</summary>

后端要能被**可替换函数**提供（¶3），也就是在链接时由另一个翻译单元（甚至另一个库）决定。模板必须在使用点可见，无法做到"链接时替换"；而虚接口只需要一个稳定的 ABI。代价是类型擦除：接收器必须被包装成 `receiver_proxy`，错误统一为 `exception_ptr`，环境只能通过 `try_query` 有限地访问。预分配存储 `span<byte>` 则是为了在类型擦除的同时保住"不分配"的性质。`task_scheduler` 复用这个接口（[[exec.task]]），也是看中了它是一个现成的、对 bulk 友好的类型擦除边界。
</details>

!!! question "2. 两个 get_parallel_scheduler() 的结果相等吗？"
    在同一个程序里调用两次 `get_parallel_scheduler()`，得到的两个调度器一定 `==` 吗？

<details markdown="1">
<summary>答案</summary>

取决于两次调用 `query_parallel_scheduler_backend()` 是否返回指向同一个后端对象的 `shared_ptr`。¶4 规定相等当且仅当后端是同一对象。默认实现与上面那种 `static` 局部变量的替换实现都会返回同一对象，于是相等；但规范没有要求每次返回同一对象——一个每次创建新后端的替换实现也是合法的，那样两个调度器就不相等，并且确实代表两个执行资源。
</details>

## 小结

- `get_parallel_scheduler()`：系统级共享并行调度器，前进保证 `parallel`；后端为空则 `terminate`。
- 所有操作都经过虚接口 `parallel_scheduler_backend`：接收器代理擦除接收器类型，预分配存储避免分配。
- domain 把 `bulk_chunked`/`bulk_unchunked` 改写为后端调用；`par`/`par_unseq` 才拆分，否则整体作为一个迭代。
- `query_parallel_scheduler_backend()` 是可替换函数：程序可以换掉整个实现。
- 后端契约：恰好一次完成；bulk 迭代不重复、成功时全覆盖；所有 `execute` 先于完成。
