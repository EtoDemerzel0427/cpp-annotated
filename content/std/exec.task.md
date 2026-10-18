---
title: task 与调度器亲和
summary: execution::task<T, Environment> 是可作协程返回类型的惰性发送器；co_await 的发送器经 affine 适配，完成后回到任务的启动调度器（调度器亲和）；co_yield with_error{e} 以错误完成；Environment 定制分配器、启动调度器类型、停止源、错误类型；以及 affine、inline_scheduler、类型擦除的 task_scheduler
status: draft
covers: *, exec.affine, exec.inline.scheduler, exec.task.scheduler
papers: P2300R10
related: exec.as.awaitable, dcl.fct.def.coroutine, exec.sched, exec.queries, exec.par.scheduler, exec.on, allocator.requirements
tags: 标准库, std::execution, 协程, task, 调度器
updated: 2026-10-18
---

[[exec.as.awaitable]] 给了把发送器接进协程的**零件**；本页的 `std::execution::task` 是用这些零件组装好的**成品**：一个协程返回类型，它本身是发送器，协程体内可以 `co_await` 任意单值发送器。

```cpp title="task.cpp"
namespace ex = std::execution;

ex::task<int> compute(int x) {
  co_return x * 2;
}

ex::task<int> pipeline() {
  int a = co_await compute(10);                                       // task 是发送器，也可以被 co_await
  int b = co_await (ex::just(1) | ex::then([](int v) { return v + 1; }));
  co_return a + b;                                                    // 22
}

int main() {
  auto [r] = std::this_thread::sync_wait(pipeline()).value();
}
```

围绕 `task` 有三个辅助设施，也在本页一并讲：

- `affine`（[exec.affine]）：让发送器"完成后回到启动它的调度器"——`task` 中每个 `co_await` 都套了它；
- `inline_scheduler`（[exec.inline.scheduler]）：在当前线程立即"调度"的调度器，用于关闭调度器亲和；
- `task_scheduler`（[exec.task.scheduler]）：类型擦除的调度器，`task` 默认的启动调度器类型。

## 调度器亲和：affine（[exec.affine]）

先讲 `affine`，因为它决定了 `task` 最重要的行为。

协程的一个常见陷阱是：`co_await` 一个在线程池上完成的发送器之后，协程就**在线程池线程上**继续执行了。如果协程原本运行在 UI 线程、或者持有只能在特定线程使用的资源，这会出错。**调度器亲和**（scheduler affinity）指的是：每次 `co_await` 之后，协程都回到它原来所在的调度器上继续。

¶1 `affine` 把发送器适配成"在接收器的调度器上完成"的发送器；若算法能判断被适配的发送器已经在正确的调度器上完成，就可以省略调度。

¶2–3 `affine(sndr)` ≡ *make-sender*(affine, env<>(), sndr)；`sndr` 不是发送器时非良构。

¶4 *UNSTOPPABLE-SCHEDULER*(sch)：一个调度器 `e`，`schedule(e)` ≡ `unstoppable(schedule(sch))`，查询和比较都转给 `sch`。即"不可被取消地调度回去"。

¶5 变换：

```cpp
auto& [_, _, child] = sndr;
if constexpr (requires { std::forward_like<Sndr>(child).affine(); }) {
  return std::forward_like<Sndr>(child).affine();
} else {
  return continues_on(std::forward_like<Sndr>(child),
                      UNSTOPPABLE-SCHEDULER(get_start_scheduler(ev)));
}
```

- 子发送器自己提供 `affine()` 成员（[[exec.snd]] ¶1 允许标准发送器这样做）就用它；
- 否则 `continues_on` 回到**接收器环境中的启动调度器**，并且这次调度不可取消。

为什么回程要不可取消？取消请求可能在子操作完成之后才到达；若回程调度被取消，就会以 `set_stopped` 在**错误的**线程上完成——这正是亲和要防止的。

¶6 *Recommended practice*：对已知会在启动处完成的发送器（`just`、`just_error`、`just_stopped`、`read_env`、`write_env`）提供 `affine` 成员，省掉无谓的调度。

¶7 若 `get_start_scheduler(get_env(out_rcvr))` 非良构，或不满足 *infallible-scheduler*<Env>（[[exec.sched#8]]），`get_completion_signatures<OutSndr, Env>()` 以异常退出——**类型错误**。原因：回程调度若可能失败，就没法保证在正确的地方报告失败。`start(op)` 在当前代理上启动 `sndr`，在 `sch` 的资源上完成；若当前资源就是 `sch` 的资源，完成可以在 `start(op)` 返回前发生。

## inline_scheduler（[exec.inline.scheduler]）

```cpp
class inline_scheduler {
  class inline-sender;
  template<receiver R> class inline-state;
public:
  using scheduler_concept = scheduler_tag;
  constexpr inline-sender schedule() noexcept { return {}; }
  constexpr bool operator==(const inline_scheduler&) const noexcept = default;
};
```

¶1 模型化 `scheduler`；所有对象相等；查询通过 *inline-attrs*<set_value_t> 回答——它的完成调度器是环境中的 `get_scheduler`，即"调用者在哪就在哪"。

¶2 *inline-sender* 的签名只有 `set_value_t()`。¶3–4 `connect` 的结果在 `start` 时直接 `set_value(std::move(rcvr))`。

即：`schedule(inline_scheduler{})` 在当前线程**立即**完成。它是"不切换"的调度器。把 `task` 的启动调度器类型设为 `inline_scheduler`，就关掉了调度器亲和（见下文 `await_transform`）。

## task_scheduler（[exec.task.scheduler]）

`task` 需要在**运行时**记住"我是在哪个调度器上启动的"，而调度器类型各不相同。`task_scheduler` 是一个类型擦除的调度器：

```cpp
class task_scheduler {
  class ts-domain;
  template<scheduler Sch> class backend-for;
public:
  using scheduler_concept = scheduler_tag;
  template<class Sch, class Allocator = allocator<void>>
    requires (!same_as<task_scheduler, remove_cvref_t<Sch>>) && scheduler<Sch>
  explicit task_scheduler(Sch&& sch, Allocator alloc = {});
  see below schedule();
  friend bool operator==(const task_scheduler&, const task_scheduler&) noexcept;
  template<class Sch> requires (!same_as<task_scheduler, Sch>) && scheduler<Sch>
  friend bool operator==(const task_scheduler&, const Sch&) noexcept;
private:
  shared_ptr<parallel_scheduler_replacement::parallel_scheduler_backend> sch_;
};
```

¶1 模型化 `scheduler`。*SCHED*(s) 是 `s.sch_` 指向的对象。前进保证取自被擦除的调度器；`get_completion_domain<set_value_t>(s)` 是 *ts-domain*。

¶2 构造 *Mandates*：`Sch` 满足 *infallible-scheduler*<env<>>——被擦除的调度器在空环境下只能以 `set_value()` 完成。

¶3 用 `allocate_shared<backend-for<remove_cvref_t<Sch>>>(alloc, sch)` 初始化。¶4 *Recommended practice*：小调度器对象应避免动态分配。¶5 后续分配使用 `alloc` 的副本。

有意思的是它**复用**了 `parallel_scheduler` 的后端接口（[[exec.par.scheduler]]）作为类型擦除的虚接口：*backend-for*<Sch> 派生自 `parallel_scheduler_backend`，

- ¶10 `schedule(r, s)`：`connect(schedule(sched_), WRAP-RCVR(r))` 并 `start`；
- ¶11 `schedule_bulk_chunked(shape, r, s)`：选一个 `chunk_size`，用 `bulk(just-sndr-like, par, num_chunks, fn)` 分块调用 `r.execute(b, e)`；
- ¶12 `schedule_bulk_unchunked(shape, r, s)`：`bulk(just-sndr-like, par, shape, fn)`，`fn(i)` 调用 `r.execute(i, i+1)`。

其中 *just-sndr-like* 是一个以 `set_value_t()` 完成、完成调度器报告为 `sched_` 的发送器（¶9）——于是内部的 `bulk` 会按 `sched_` 的 domain 被定制，被擦除调度器的并行 `bulk` 实现得以保留。

¶6–7 比较：`task_scheduler == task_scheduler` 比较两个被擦除的调度器；与具体调度器 `Sch` 比较时，类型不同为 false，否则比较值。

¶13 `schedule()` 返回的发送器：value 完成调度器是 `*this`，完成 domain 是 *ts-domain*；启动时调用 `sch_->schedule(r, s)`（`r` 是接收器代理，`s` 是预分配的后端存储）；签名在不可停止环境下是 `set_value_t()`，否则再加 `set_stopped_t()`。

¶14–15 *ts-domain*：把 `bulk_chunked`/`bulk_unchunked` 发送器改写成调用 `sch_->schedule_bulk_chunked/unchunked` 的发送器（前驱的完成调度器不是 `task_scheduler` 时为 *not-a-sender*）。这样，通过 `task_scheduler` 调度的 `bulk` 依然能用上被擦除调度器的并行实现。

## task 概览与类模板（[task.overview]、[task.class]）

[task.overview] ¶1 `task` 表示可用作协程返回类型的发送器。`T` 是 value 完成的数据类型（`void` 则无数据）；协程中 `co_return` 的操作数成为 `set_value` 的实参。`Environment` 用于定制 `task` 的行为。

```cpp
template<class T = void, class Environment = env<>>
class task {
  template<receiver Rcvr> class state;
public:
  using sender_concept = sender_tag;
  using allocator_type = see below;
  using start_scheduler_type = see below;
  using stop_source_type = see below;
  using stop_token_type = decltype(declval<stop_source_type>().get_token());
  using error_types = see below;
  class promise_type;
  task(task&&) noexcept;
  ~task();
  template<class Self, class... Env> static consteval auto get_completion_signatures();
  template<receiver Rcvr> state<Rcvr> connect(Rcvr&& rcvr) &&;
private:
  coroutine_handle<promise_type> handle;
};
```

[task.class] ¶1 若 `T` 是 `void`、引用类型或 cv 无限定的非数组对象类型，且 `E` 是类类型，`task<T, E>` 模型化 `sender`；否则实例化其定义的程序非良构。

¶2 嵌套类型从 `Environment` 中取，取不到用默认值：

| 成员 | 取自 | 默认 |
|---|---|---|
| `allocator_type` | `Environment::allocator_type` | `allocator<byte>` |
| `start_scheduler_type` | `Environment::start_scheduler_type` | `task_scheduler` |
| `stop_source_type` | `Environment::stop_source_type` | `inplace_stop_source` |
| `error_types` | `Environment::error_types` | `completion_signatures<set_error_t(exception_ptr)>` |

¶3 `error_types` 必须是 `completion_signatures` 的特化，且每个元素形如 `set_error_t(E)`，否则非良构。¶4 `allocator_type` 满足 *Cpp17Allocator*，调度器类型模型化 `scheduler`，`stop_source_type` 模型化 *stoppable-source*。

注意 `connect` 只有 `&&` 版本：`task` 只能 connect **一次**（它独占协程帧）。`task` 只能移动，不能复制。

## task 成员（[task.members]）

- ¶1–2 移动构造夺取 `handle`；析构时若 `handle` 非空则 `destroy()`——一个从未 connect 的 task 被销毁时，其协程帧随之销毁（协程从未开始执行，因为 `initial_suspend` 是 `suspend_always`）。
- ¶3–4 `get_completion_signatures`：`set_value_t()`（`T` 为 `void`）或 `set_value_t(T)`、`error_types` 中的所有签名、`set_stopped_t()`。**与环境无关**，所以 `task` 是非依赖发送器。
- ¶5 `connect` *Mandates*：`allocator_type(get_allocator(get_env(rcvr)))` 或 `allocator_type()` 至少一个良构。
- ¶6–7 *Preconditions*：`bool(handle)`；效果：`return state<Rcvr>(exchange(handle, {}), std::forward<Rcvr>(recv));`——协程句柄的所有权转移给操作状态。

## task::state（[task.state]）

`state<Rcvr>` 是 `task` 的**操作状态**：持有协程句柄、接收器、可选的停止源、`own-env`、`environment`、结果 `optional<T>`（`T` 非 `void` 时）和 `exception_ptr error`。

- ¶1 `own-env-t` 是 `Environment::template env_type<decltype(get_env(declval<Rcvr>()))>`（若有），否则 `env<>`。
- ¶2 构造：用接收器环境构造 `own-env`，再用 `own-env`（或接收器环境、或默认构造）构造 `environment`；都不行则非良构。
- ¶3 析构：若 `handle` 非空则 `destroy()`。
- ¶4 `start()`：把 *STATE*(prom) = `*this`、*RCVR*(prom) = `rcvr`、*SCHED*(prom) = `start_scheduler_type(get_start_scheduler(get_env(rcvr)))`（不行则默认构造；都不行非良构）关联到承诺对象，然后 `handle.resume()`。
- ¶5 *get-stop-token*：若停止源的令牌类型与接收器环境的令牌类型相同，直接返回接收器的令牌；否则惰性地构造一个 `source`，使其 `stop_requested()`/`stop_possible()` 反映接收器令牌的状态，返回 `source->get_token()`。

¶4 的 *SCHED*(prom) 就是"任务的启动调度器"：从接收器环境的 `get_start_scheduler` 取得，转换成 `start_scheduler_type`（默认 `task_scheduler`，即类型擦除）。没有 `get_start_scheduler` 的环境下，`task_scheduler` 不可默认构造（它只有接受调度器的构造函数），于是非良构——**`task` 默认要求接收器告诉它"你在哪里启动"**。`sync_wait` 的环境提供了它（[[exec.consumers]]）。

## promise_type（[task.promise]）

```cpp
class task<T, Environment>::promise_type {
public:
  task get_return_object() noexcept;
  static constexpr suspend_always initial_suspend() noexcept { return {}; }
  auto final_suspend() noexcept;
  void unhandled_exception();
  coroutine_handle<> unhandled_stopped() noexcept;
  void return_void();                                // 仅当 is_void_v<T>
  template<class V = T> void return_value(V&& value);// 仅当 !is_void_v<T>
  template<class E> unspecified yield_value(with_error<E> error);
  template<sender Sender> auto await_transform(Sender&& sndr);
  unspecified get_env() const noexcept;
  void* operator new(size_t size);
  template<class Alloc, class... Args>
    void* operator new(size_t size, allocator_arg_t, Alloc alloc, Args&&...);
  template<class This, class Alloc, class... Args>
    void* operator new(size_t size, const This&, allocator_arg_t, Alloc alloc, Args&&...);
  void operator delete(void* pointer, size_t size) noexcept;
};
```

逐个看：

- `initial_suspend` 是 `suspend_always`：**惰性**，调用协程函数只创建帧，`start` 时才开始执行。
- ¶2 `get_return_object`：返回持有本协程句柄的 `task`。
- ¶3 `final_suspend`：返回一个 awaiter，安排异步操作的完成：**先**用 `st.handle.destroy()` 销毁协程帧，**再**调用 `set_error(rcvr, error)`（若有异常）或 `set_value(rcvr[, *result])`。注意结果存在 `state` 里而不是协程帧里，所以可以先销毁帧再发出结果。
- ¶4–5 `yield_value(with_error<Err> err)`：*Mandates*：`err.error` 可转换为 `error_types` 中**恰好一个** `set_error_t` 的实参类型 *Cerr*；返回的 awaiter 挂起协程、销毁帧、调用 `set_error(rcvr, Cerr(std::move(err.error)))`。这是 `task` 中**以非异常的错误完成**的方式：`co_yield with_error{ec};`。
- ¶6 `await_transform(sndr)`：若 `start_scheduler_type` 是 `inline_scheduler`，返回 `as_awaitable(sndr, *this)`；**否则返回 `as_awaitable(affine(sndr), *this)`**——每个 `co_await` 都被 `affine` 包裹，完成后回到启动调度器。注意 `await_transform` 只接受 `sender`：在 `task` 里 `co_await` 一个非发送器的可等待体，只有在它被发送器概念识别（可在空环境协程里被等待）时才行。
- ¶7 `unhandled_exception`：若 `error_types` 不含 `set_error_t(exception_ptr)`，调用 `terminate()`；否则把 `current_exception()` 存进 `state.error`。
- ¶8–9 `unhandled_stopped`：销毁协程帧，调用 `set_stopped(rcvr)`，返回 `noop_coroutine()`。这就是 [[exec.as.awaitable]] 中"stopped 不恢复协程、交给承诺类型"的落点：`task` 把取消直接变成整个任务的 stopped 完成。
- ¶10–11 `return_void` 什么也不做；`return_value(v)`：`result.emplace(std::forward<V>(v))`。
- ¶12 `get_env()`：协程内被 `co_await` 的发送器看到的环境：
  - `get_start_scheduler` → `start_scheduler_type(SCHED(*this))`；
  - `get_allocator` → 由接收器环境的分配器转换，或默认 `allocator_type()`；
  - `get_stop_token` → *STATE*(*this).*get-stop-token*()；
  - 其他查询：若 `forwarding_query(q)` 为 true 且 `environment.query(q, a...)` 良构，转给 `environment`；否则非良构。
- ¶13–19 分配：`operator new(size)` 用默认构造的 `allocator_type`；带 `allocator_arg_t, Alloc` 的重载（`This` 版本用于成员函数协程，第一个形参是对象本身）用给定的分配器。存储以一个大小和对齐都是 `__STDCPP_DEFAULT_NEW_ALIGNMENT__` 的未指定类型 `U` 为单位分配，并附带足够的信息，使 `operator delete` 能用相等的分配器释放（¶16、¶19）。

```cpp title="task-allocator.cpp"
namespace ex = std::execution;

ex::task<int> work(std::allocator_arg_t, std::pmr::polymorphic_allocator<> a, int x) {
  co_return x;            // 协程帧通过 a 分配（a 被转换为 allocator_type）
}
```

!!! note "with_error：不用异常的错误路径"
    `error_types` 可以声明任意错误类型，例如 `completion_signatures<set_error_t(std::error_code)>`。这时 `unhandled_exception` 会 `terminate()`（因为没有 `exception_ptr`），错误必须通过 `co_yield with_error{ec};` 报告。这让 `task` 可以用在禁用异常或不希望异常开销的代码里。

!!! history
    `task`、`affine`、`inline_scheduler`、`task_scheduler` 都不在 P2300 本身之中，而是由后续提案加入的；`affine` 与 `get_start_scheduler` 相关的措辞看起来是更晚的修订。本站不在此给出具体提案编号。读其他资料（博客、参考实现的旧版本）时，要留意它们描述的可能是更早的措辞。

## 陷阱

!!! pitfall "task 在 co_await 之后回到了哪里？"
    默认 `start_scheduler_type` 是 `task_scheduler`，所以 `co_await schedule(pool)` 之后——协程**不会**留在线程池上，而是被 `affine` 带回启动调度器。想"切换到线程池继续执行"，在 `task` 里这样写是做不到的；要么把需要在池上做的工作放进一个发送器整体 `co_await`（`co_await (schedule(pool) | then(f))`），要么使用 `start_scheduler_type = inline_scheduler` 的 `task` 关闭亲和。

!!! pitfall "error_types 不含 exception_ptr 时抛异常"
    `error_types` 为 `completion_signatures<set_error_t(std::error_code)>` 的 `task` 里，任何逃出协程体的异常都会导致 `terminate`（¶7）——包括 `co_await` 一个以 `exception_ptr` 错误完成的发送器时，`await_resume` 重新抛出的异常。

## 思考题

!!! question "1. 为什么 final_suspend 先销毁帧再完成？"
    [task.promise] ¶3 规定先 `destroy()` 协程帧，再调用接收器的完成函数。反过来会怎样？

<details markdown="1">
<summary>答案</summary>

接收器的完成函数可能销毁 `task` 的操作状态 `state`（[[exec.async.ops#8]]），而 `state` 的析构函数会在 `handle` 非空时 `destroy()` 协程帧（[task.state] ¶3）。若先完成再销毁帧：完成函数里 `state` 被销毁 → 帧随之被销毁 → 控制回到 `final_suspend` 的 awaiter 中（它就在那个已销毁的帧里）再去执行"销毁帧"——访问已释放的内存。先销毁帧、再从 `state` 中取出结果与接收器完成，就避开了这一点；结果和接收器都存在 `state` 里而不是帧里，正是为了允许这种顺序。

顺带一提：规范没有明说 `final_suspend` 销毁帧之后要把 `st.handle` 置空，而 `state` 的析构函数会在 `handle` 非空时再次 `destroy()`。实现显然必须避免这种二次销毁（例如在 `destroy()` 前 `exchange` 出句柄）；字面上这是一处需要实现者自行补全的细节。
</details>

!!! question "2. affine 的回程为什么必须 infallible？"
    [exec.affine] ¶7 要求启动调度器满足 *infallible-scheduler*，否则签名计算抛异常。如果允许回程调度失败，`task` 会遇到什么问题？

<details markdown="1">
<summary>答案</summary>

回程调度失败会以 `set_error` 完成，而这个完成发生在"调度失败"的地方——未指定的执行代理上（参见 [[exec.on]] 中 `continues_on` 的规定）。对 `task` 来说，`co_await` 会在一个**不是**启动调度器的线程上恢复，并抛出异常——调度器亲和的承诺被打破，而且恰好是在错误处理路径上，最难察觉。要求 infallible 把这种情况变成编译期错误。
</details>

## 小结

- `task<T, Env>`：惰性的协程发送器，只能移动、只能 connect 一次；签名 `set_value_t(T)` + `error_types` + `set_stopped_t()`，与环境无关。
- 启动调度器来自接收器环境的 `get_start_scheduler`；每个 `co_await` 经 `affine` 回到它（`inline_scheduler` 关闭亲和）。
- 错误：异常（需要 `exception_ptr` 在 `error_types` 中）或 `co_yield with_error{e}`；取消：`unhandled_stopped` 直接以 stopped 完成整个任务。
- 分配器：`allocator_arg` 形参或接收器环境；协程帧按 `__STDCPP_DEFAULT_NEW_ALIGNMENT__` 粒度分配。
- `affine`：`continues_on(sndr, 不可取消的启动调度器)`，要求 infallible；`inline_scheduler`：立即完成的调度器；`task_scheduler`：借用 `parallel_scheduler_backend` 接口的类型擦除调度器。
