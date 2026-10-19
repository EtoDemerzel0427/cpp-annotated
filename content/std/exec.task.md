---
title: task 与调度器亲和
summary: execution::task 是可以作协程返回类型的惰性发送器；协程里每次 co_await 之后都回到任务启动时所在的调度器（调度器亲和），错误可以用异常或 co_yield with_error 报告。本页一并讲 affine、inline_scheduler 和类型擦除的 task_scheduler。
status: draft
covers: *, exec.affine, exec.inline.scheduler, exec.task.scheduler
papers: P2300R10
related: exec.as.awaitable, dcl.fct.def.coroutine, exec.sched, exec.queries, exec.par.scheduler, exec.on, allocator.requirements
tags: 标准库, std::execution, 协程, task, 调度器
updated: 2026-10-19
---

!!! tldr
    - `task<T>` 是一个协程返回类型，它本身是发送器；调用协程函数只创建协程帧，连接并启动之后才开始执行。
    - 协程体里每个 `co_await` 都经过 `affine` 包装，完成后回到任务启动时所在的调度器，这叫调度器亲和；把启动调度器类型设为 `inline_scheduler` 可以关闭它。
    - 启动调度器来自接收器环境的 `get_start_scheduler`，默认存进类型擦除的 `task_scheduler`。
    - 错误有两条路：逃出协程体的异常（`error_types` 里要有 `exception_ptr`，否则 `terminate`），或者 `co_yield with_error{e}`；取消直接让整个任务以 stopped 完成。
    - 协程帧的内存可以通过 `allocator_arg` 形参或接收器环境中的分配器来分配。

本页的例子用到 C++26 的 `std::execution`。本机 Clang 23 附带的 libc++ 还没有实现这部分库，例子都没有经过编译验证，因此不加判定标记。

## 用协程写发送器

```cpp title="task.cpp"
namespace ex = std::execution;

ex::task<int> compute(int x) {
  co_return x * 2;
}

ex::task<int> pipeline() {
  int a = co_await compute(10);                // task 是发送器，可以被 co_await
  int b = co_await (ex::just(1)
                    | ex::then([](int v) { return v + 1; }));
  co_return a + b;                             // 22
}

int main() {
  auto [r] = std::this_thread::sync_wait(pipeline()).value();
}
```

[[exec.as.awaitable]] 提供了把[[g:sender|发送器]]接进协程的零件：在协程里 `co_await` 一个发送器，得到它的值。`std::execution::task` 是用这些零件组装好的成品。它是一个可以作协程返回类型的类模板，`task` 对象本身又是发送器，可以交给 `sync_wait`、`then` 等任何接受发送器的算法，也可以在另一个 `task` 里 `co_await`。

[task.overview] ¶1 `task<T, Environment>` 中 `T` 是成功完成时传出的值的类型，`void` 表示没有值；协程中 `co_return` 的操作数成为 `set_value` 的实参。`Environment` 用来定制 `task` 的行为，见下文。

## 调度器亲和：affine [exec.affine]

### 问题：co_await 之后在哪个线程上

一个协程如果 `co_await` 了一个在线程池上完成的发送器，它恢复执行的地方就是那个线程池线程。如果协程原本运行在 UI 线程，或者持有只能在特定线程上使用的资源，这就会出错。**调度器亲和**（scheduler affinity）是说：每次 `co_await` 之后，协程都回到它原来所在的调度器上继续执行。`task` 默认提供这个保证，实现手段是 `affine`。

¶1 `affine` 把一个发送器适配成在接收器的调度器上完成的发送器。如果能判断被适配的发送器本来就在正确的调度器上完成，可以省去这次调度。¶2–3 `affine(sndr)` 要求 `sndr` 是发送器，否则非良构。

### 实现：continues_on 回到启动调度器（¶4–5）

¶5 `affine` 的变换如下，其中 `ev` 是接收器的环境：

```cpp
auto& [_, _, child] = sndr;
if constexpr (requires { std::forward_like<Sndr>(child).affine(); }) {
  return std::forward_like<Sndr>(child).affine();
} else {
  return continues_on(std::forward_like<Sndr>(child),
                      UNSTOPPABLE-SCHEDULER(get_start_scheduler(ev)));
}
```

子发送器自己提供了 `affine()` 成员时就用它。否则用 `continues_on` 在子发送器完成后转移到接收器环境中的启动调度器上。¶6 建议实现给已知在启动处完成的发送器（`just`、`just_error`、`just_stopped`、`read_env`、`write_env`）提供 `affine` 成员，省掉没有必要的调度。

¶4 *UNSTOPPABLE-SCHEDULER*(sch) 是一个包装后的调度器：`schedule` 等价于 `unstoppable(schedule(sch))`，查询和比较都转给 `sch`。回程调度之所以不可取消，是因为取消请求可能在子操作完成之后才到达。如果回程调度被取消，它会以 `set_stopped` 完成，而这次完成发生在错误的线程上，正是亲和要避免的情况。

### 回程不能失败（¶7）

¶7 如果接收器环境没有 `get_start_scheduler`，或者得到的调度器不满足 *infallible-scheduler*（调度只能以 `set_value` 完成，可以被取消时还允许 `set_stopped`，见 [[exec.sched#8]]），那么计算完成签名时会抛出异常，在编译期表现为类型错误。

¶7 还说明，启动 `affine` 的操作会在当前执行代理上启动 `sndr`，在启动调度器的执行资源上完成；如果当前资源就是那个资源，完成可能在 `start` 返回之前发生。

## 两个辅助调度器

### inline_scheduler：不切换线程 [exec.inline.scheduler]

```cpp
class inline_scheduler {
public:
  using scheduler_concept = scheduler_tag;
  constexpr inline-sender schedule() noexcept { return {}; }
  constexpr bool operator==(const inline_scheduler&) const noexcept = default;
};
```

¶1 所有 `inline_scheduler` 对象都相等，查询的答案由 *inline-attrs* 给出：它的完成调度器就是环境里的当前调度器，调用者在哪里，它就在哪里。¶2–4 `schedule()` 返回的发送器只有 `set_value_t()` 一种完成方式，启动时直接对接收器调用 `set_value`。

换句话说，`schedule(inline_scheduler{})` 在当前线程立即完成。把 `task` 的启动调度器类型设为 `inline_scheduler`，就关闭了调度器亲和。

### task_scheduler：类型擦除的调度器 [exec.task.scheduler]

`task` 需要在运行时记住自己是在哪个调度器上启动的，而各种调度器的类型互不相同。`task_scheduler` 是一个类型擦除的调度器，也是 `task` 默认的启动调度器类型。

```cpp
class task_scheduler {
public:
  using scheduler_concept = scheduler_tag;
  template<class Sch, class Allocator = allocator<void>>
    requires (!same_as<task_scheduler, remove_cvref_t<Sch>>) && scheduler<Sch>
  explicit task_scheduler(Sch&& sch, Allocator alloc = {});
  task_scheduler(const task_scheduler&) = default;
  task_scheduler& operator=(const task_scheduler&) = default;
  see below schedule();
  // 与 task_scheduler、与具体调度器类型的 operator==
private:
  shared_ptr<parallel_scheduler_replacement::parallel_scheduler_backend> sch_;
};
```

它没有默认构造函数，必须从一个具体的调度器构造。

¶1 前进保证取自被擦除的调度器。¶2 被擦除的调度器必须满足 *infallible-scheduler*<env<>>，也就是在空环境下只能以 `set_value()` 完成。¶3–5 构造时用 `allocate_shared` 和给定的分配器分配内部对象，之后的分配都用这个分配器的副本；¶4 建议对小的调度器对象避免动态分配。

¶6–7 两个 `task_scheduler` 相等，当且仅当被擦除的调度器相等；与具体调度器 `Sch` 比较时，类型不同就是 false，类型相同再比较值。

有意思的是，它复用了[[exec.par.scheduler|并行调度器]]的后端接口 `parallel_scheduler_backend` 作为类型擦除的虚接口。内部的 *backend-for*<Sch> 派生自这个接口：

- ¶10 `schedule(r, s)` 把 `schedule(sched_)` 连接到包装了代理 `r` 的接收器上并启动；
- ¶11 `schedule_bulk_chunked(shape, r, s)` 选一个块大小，用 `bulk(just-sndr-like, par, num_chunks, fn)` 分块调用 `r.execute(b, e)`；
- ¶12 `schedule_bulk_unchunked(shape, r, s)` 用 `bulk(just-sndr-like, par, shape, fn)`，每次调用 `r.execute(i, i + 1)`。

¶9 *just-sndr-like* 是一个以 `set_value_t()` 完成、并把完成调度器报告为 `sched_` 的发送器。所以内部的 `bulk` 会按被擦除调度器的 domain 定制，后者的并行 `bulk` 实现得以保留。

¶13 `schedule()` 返回的发送器报告 `*this` 为完成调度器，启动时调用 `sch_->schedule(r, s)`。它的完成签名在不可停止的环境下只有 `set_value_t()`，否则还有 `set_stopped_t()`。¶14–15 *ts-domain* 把前驱在 `task_scheduler` 上完成的 `bulk_chunked`、`bulk_unchunked` 发送器改写成对后端 `schedule_bulk_chunked`、`schedule_bulk_unchunked` 的调用。这样经由 `task_scheduler` 调度的 `bulk` 仍然能用上被擦除调度器的并行实现。

## task 类模板 [task.class]

```cpp
template<class T = void, class Environment = env<>>
class task {
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
  coroutine_handle<promise_type> handle;   // 仅用于阐述
};
```

¶1 `T` 为 `void`、引用类型或 cv 无限定的非数组对象类型，并且 `Environment` 是类类型时，`task<T, Environment>` 模型化 `sender`；否则实例化它的定义的程序非良构。

`task` 只能移动，不能复制。`connect` 只有右值版本：一个 `task` 独占它的协程帧，只能连接一次。

### 用 Environment 定制（¶2–4）

¶2 几个嵌套类型从 `Environment` 中取，取不到就用默认值：

| 成员 | 取自 | 默认 |
|---|---|---|
| `allocator_type` | `Environment::allocator_type` | `allocator<byte>` |
| `start_scheduler_type` | `Environment::start_scheduler_type` | `task_scheduler` |
| `stop_source_type` | `Environment::stop_source_type` | `inplace_stop_source` |
| `error_types` | `Environment::error_types` | `completion_signatures<set_error_t(exception_ptr)>` |

¶3 `error_types` 必须是 `completion_signatures` 的特化，而且每个元素都形如 `set_error_t(E)`，否则非良构。¶4 `allocator_type` 要满足 *Cpp17Allocator*，调度器类型要模型化 `scheduler`，停止源类型要模型化 *stoppable-source*。（¶4 的原文把调度器类型写成 `scheduler_type`，指的就是 `start_scheduler_type`。）

### 成员 [task.members]

¶1–2 移动构造夺走源对象的协程句柄。析构时句柄非空就销毁协程帧：一个从未连接的 `task` 被销毁时，它的协程从未开始执行，帧随之销毁。

¶3–4 `get_completion_signatures` 返回 `set_value_t()`（`T` 为 `void`）或 `set_value_t(T)`、`error_types` 中的全部签名，以及 `set_stopped_t()`。结果与环境无关，所以 `task` 是[[g:non-dependent-sender|非依赖发送器]]。

¶5–7 `connect` 要求能从接收器环境的分配器或者默认构造得到 `allocator_type`；它把协程句柄的所有权转交给新建的操作状态 `state<Rcvr>`。

## 操作状态：task::state [task.state]

`state<Rcvr>` 是 `task` 的[[g:operation-state|操作状态]]。它持有协程句柄、接收器、一个可选的停止源、两个环境对象、结果 `optional<T>`（`T` 非 `void` 时）和一个 `exception_ptr`。结果和异常存在这里，而不是协程帧里，这一点在完成时很重要。

¶1–2 构造时先用接收器的环境构造 `own-env`（由 `Environment::env_type` 指定，没有就是 `env<>`），再用它构造 `Environment` 对象；都构造不了时非良构。¶3 析构时句柄非空就销毁协程帧。

¶4 `start()` 把这个状态对象、接收器和启动调度器与协程的承诺对象关联起来，然后恢复协程。启动调度器 *SCHED*(prom) 是 `start_scheduler_type(get_start_scheduler(get_env(rcvr)))`，取不到时默认构造，两者都不行则非良构。

默认的 `start_scheduler_type` 是 `task_scheduler`，它不能默认构造。所以 `task` 默认要求接收器的环境说明自己在哪里启动。`sync_wait` 的环境提供了 `get_start_scheduler`（[[exec.consumers]]）。

¶5 *get-stop-token* 决定协程内部看到的停止令牌。如果停止源的令牌类型与接收器环境的令牌类型相同，直接用接收器的令牌；否则按需构造一个停止源，让它的 `stop_requested()` 和 `stop_possible()` 反映接收器令牌的状态，返回它的令牌。

## 承诺类型 [task.promise]

```cpp
class task<T, Environment>::promise_type {
public:
  task get_return_object() noexcept;
  static constexpr suspend_always initial_suspend() noexcept { return {}; }
  auto final_suspend() noexcept;
  void unhandled_exception();
  coroutine_handle<> unhandled_stopped() noexcept;
  void return_void();                                  // 仅当 T 为 void
  template<class V = T> void return_value(V&& value);  // 仅当 T 不为 void
  template<class E> unspecified yield_value(with_error<E> error);
  template<sender Sender> auto await_transform(Sender&& sndr);
  unspecified get_env() const noexcept;
  // operator new / operator delete，见下文
};
```

`initial_suspend` 返回 `suspend_always`，所以 `task` 是惰性的：调用协程函数只创建协程帧，`start` 时才开始执行。¶2 `get_return_object` 返回持有本协程句柄的 `task`。

### 每个 co_await 都经过 affine（¶6）

¶6 `await_transform(sndr)`：`start_scheduler_type` 是 `inline_scheduler` 时返回 `as_awaitable(sndr, *this)`，否则返回 `as_awaitable(affine(sndr), *this)`。这一条实现了调度器亲和：协程里每个 `co_await` 都被 `affine` 包装，完成后回到启动调度器。

`await_transform` 只接受发送器，所以在 `task` 里 `co_await` 一个不是发送器的可等待对象，只有在它也被识别为发送器时才行。

¶12 `get_env()` 是协程内被 `co_await` 的发送器看到的环境：`get_start_scheduler` 返回启动调度器，`get_allocator` 返回由接收器环境的分配器转换来的分配器（取不到时默认构造），`get_stop_token` 返回 *get-stop-token* 的结果；其他查询如果是转发查询，并且 `Environment` 对象能回答，就转给它，否则非良构。

### 完成：先销毁帧，再通知接收器（¶3、¶10–11）

¶10–11 `return_void` 什么也不做；`return_value(v)` 把值存进状态对象的 `result`。

¶3 `final_suspend` 返回的可等待对象负责完成整个操作：先用 `destroy()` 销毁协程帧，再根据状态对象里是否存了异常，调用 `set_error(rcvr, error)` 或者 `set_value(rcvr[, *result])`。结果存在状态对象里，所以帧可以先销毁。为什么要这个顺序，见思考题 1。

### 错误和取消（¶4–5、¶7–9）

¶7 `unhandled_exception`：`error_types` 中有 `set_error_t(exception_ptr)` 时，把当前异常存进状态对象；没有时调用 `terminate()`。

¶4–5 `co_yield with_error{e}` 是不用异常的错误路径。`e` 必须恰好能转换为 `error_types` 中一个 `set_error_t` 的实参类型 *Cerr*，否则非良构。返回的可等待对象挂起协程、销毁帧，然后调用 `set_error(rcvr, Cerr(std::move(e)))`。

```cpp title="with-error.cpp"
struct env_t {
  using error_types =
    ex::completion_signatures<ex::set_error_t(std::error_code)>;
};

ex::task<int, env_t> parse(std::string_view s) {
  if (s.empty())
    co_yield ex::with_error{std::make_error_code(std::errc::invalid_argument)};
  co_return 42;
}
```

这个 `task` 的 `error_types` 里没有 `exception_ptr`，任何逃出协程体的异常都会导致 `terminate`。错误必须用 `co_yield with_error{...}` 报告。这让 `task` 可以用在禁用异常或者不想付出异常开销的代码里。

¶8–9 `unhandled_stopped`：被 `co_await` 的发送器以 stopped 完成时，协程不会恢复，而是调用这个函数。它销毁协程帧，对接收器调用 `set_stopped`，返回 `noop_coroutine()`。也就是说，`task` 把内部的取消直接变成整个任务的 stopped 完成（参见 [[exec.as.awaitable]]）。

### 协程帧的分配（¶13–19）

```cpp title="task-allocator.cpp"
ex::task<int> work(std::allocator_arg_t,
                   std::pmr::polymorphic_allocator<> a, int x) {
  co_return x;   // 协程帧通过 a 分配（转换为 allocator_type）
}
```

¶13 不带分配器的 `operator new(size)` 使用默认构造的 `allocator_type`。¶14–17 带 `allocator_arg_t, Alloc` 的重载使用给定的分配器；另一个以 `const This&` 开头的重载用于成员函数协程，第一个形参是对象本身。存储以一个大小和对齐都等于 `__STDCPP_DEFAULT_NEW_ALIGNMENT__` 的未指定类型为单位分配，并附带足够的信息，使 ¶18–19 的 `operator delete` 能用相等的分配器释放它。

## 常见误解

!!! pitfall "co_await schedule(pool) 之后就在线程池上了"
    默认的 `start_scheduler_type` 是 `task_scheduler`，`co_await` 的发送器会被 `affine` 包装。所以 `co_await schedule(pool)` 之后，协程不会留在线程池上，而是被带回启动调度器。要在线程池上做的工作，应当整体放进一个发送器再 `co_await`，例如 `co_await (schedule(pool) | then(f))`；或者使用 `start_scheduler_type` 为 `inline_scheduler` 的 `task` 关闭亲和。

!!! pitfall "error_types 不含 exception_ptr 时，异常不会变成错误完成"
    这样的 `task` 里，任何逃出协程体的异常都会导致 `terminate`（¶7）。这也包括 `co_await` 一个以 `exception_ptr` 错误完成的发送器时，由 `await_resume` 重新抛出的那个异常。

## 思考题

!!! question "1. final_suspend 为什么先销毁帧，再调用完成函数？"
    [task.promise] ¶3 规定先 `destroy()` 协程帧，再调用接收器的完成函数。反过来会怎样？

<details markdown="1">
<summary>答案</summary>

接收器的完成函数可能销毁 `task` 的操作状态 `state`（[[exec.async.ops#8]]），而 `state` 的析构函数会在句柄非空时销毁协程帧（[task.state] ¶3）。如果先完成、后销毁帧：完成函数里 `state` 被销毁，帧随之被销毁，控制回到 `final_suspend` 的可等待对象中（它就在那个已经销毁的帧里）再去销毁帧，访问的是已经释放的内存。先销毁帧，再从 `state` 中取出结果和接收器完成，就避开了这个问题；把结果和接收器存在 `state` 而不是帧里，正是为了允许这个顺序。

条文没有明说销毁帧之后要把 `st.handle` 置空，而 `state` 的析构函数会在句柄非空时再销毁一次。实现必须自己避免这种二次销毁，例如在 `destroy()` 之前用 `exchange` 取出句柄。
</details>

!!! question "2. affine 的回程为什么必须不会失败？"
    [exec.affine] ¶7 要求启动调度器满足 *infallible-scheduler*，否则计算完成签名时抛出异常。如果允许回程调度失败，`task` 会遇到什么问题？

<details markdown="1">
<summary>答案</summary>

回程调度失败会以 `set_error` 完成，而这次完成发生在调度失败的地方，一个未指定的执行代理上（参见 [[exec.on]] 中对 `continues_on` 的规定）。对 `task` 来说，这意味着 `co_await` 在一个不是启动调度器的线程上恢复并抛出异常。调度器亲和的保证被打破，而且恰好发生在错误处理路径上，最难察觉。要求回程不会失败，把这种情况变成了编译期错误。
</details>

<details class="fine" markdown="1"><summary>其余条文</summary>

[task.promise] ¶1 说明下文提到的 *STATE*(prom)、*RCVR*(prom)、*SCHED*(prom) 是在 `state<Rcvr>::start` 中与承诺对象关联的对象。

`task`、`affine`、`inline_scheduler`、`task_scheduler` 都不在 P2300 本身之中，而是由后续提案加入的；与 `affine` 和 `get_start_scheduler` 相关的措辞是更晚的修订。读博客或参考实现的旧版本时，要留意它们描述的可能是更早的设计。

</details>
