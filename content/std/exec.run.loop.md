---
title: run_loop
summary: 标准库里最简单的执行资源：一个线程安全的先进先出工作队列，由调用 run() 的线程执行；sync_wait 的默认实现就建立在它上面。
status: draft
covers: exec.ctx, exec.run.loop.general, exec.run.loop.types, exec.run.loop.ctor, exec.run.loop.members
papers: P2300R10
related: exec.sched, exec.consumers, exec.async.ops, exec.opstate, intro.races, defns.block
tags: 标准库, std::execution, 执行上下文, 调度器
updated: 2026-10-19
---

!!! tldr
    - `run_loop` 不创建线程，只维护一个工作队列；哪个线程调用 `run()`，哪个线程就执行队列里的工作。
    - 调度一项工作就是把它的操作状态挂到队尾，不需要分配内存，所以调度永远不会失败，调度发送器没有错误完成。
    - 环境的停止令牌可能被请求停止时，调度发送器才多一个 `set_stopped_t()`；取消在工作出队执行时检查。
    - 状态依次是 starting、running、finishing、finished。`finish()` 不丢弃已排队的工作，`run()` 在队列清空后才返回。
    - 析构时队列不空，或者还有线程在 `run()` 里，就调用 `std::terminate`。

本页的例子用到 C++26 的 `std::execution`。本机 Clang 23 附带的 libc++ 还没有实现这部分库，例子没有经过编译验证，因此不加判定标记。

## 一个由调用者驱动的队列

```cpp title="run-loop.cpp"
namespace ex = std::execution;

ex::run_loop loop;
auto sch = loop.get_scheduler();

std::jthread worker([&] { loop.run(); });   // worker 线程负责执行 loop 里的工作

auto s = ex::schedule(sch) | ex::then([] { return std::this_thread::get_id(); });
auto [id] = std::this_thread::sync_wait(std::move(s)).value();   // id 是 worker 的线程 id
loop.finish();                               // 队列清空后 run() 返回，worker 结束
```

[exec.ctx]（执行上下文）目前只有 `run_loop` 一个成员。[exec.run.loop.general] ¶1 它是一个可以调度工作的执行资源，维护一个线程安全的先进先出队列；`run` 成员函数在调用它的线程上循环地取出并执行队列里的工作。

`sync_wait` 的默认实现就是在栈上放一个 `run_loop`，启动操作，然后调用 `run()`（[[exec.consumers]]）。`run_loop` 也是理解调度器怎样实现的一个好样板：调度一个操作就是把操作状态挂进队列，执行就是取出它并调用它的完成函数。

## 成员与状态（[exec.run.loop.general]）

```cpp
class run_loop {
  struct run-loop-opstate-base {       // 阐述用
    virtual void execute() noexcept = 0;
    run_loop* loop;
    run-loop-opstate-base* next;       // 侵入式链表指针
  };
  run-loop-opstate-base* pop-front() noexcept;
  void push-back(run-loop-opstate-base*) noexcept;
public:
  run_loop() noexcept;
  run_loop(run_loop&&) = delete;
  ~run_loop();
  run-loop-scheduler get_scheduler() noexcept;
  void run() noexcept;
  void finish() noexcept;
};
```

¶4 标准建议实现用一个由操作状态组成的侵入式队列，让调度不需要分配内存。上面的 `next` 指针就是这个用途：每个被调度的操作状态自己就是链表的一个节点。

这样做的代价是操作状态在排队期间不能移动。标准库发送器的操作状态本来就不允许复制或移动（[[exec.opstate#3]]）。`run_loop` 自己也不能移动，因为排队的操作状态里存着指向它的 `loop` 指针。

¶2 每个 `run_loop` 有一个**计数**，即队列中工作项的个数，还有一个**状态**，是 *starting*、*running*、*finishing*、*finished* 之一：

```text
          run()              finish()             队列清空
starting ───────► running ───────────► finishing ──────────► finished
    │                                      ▲
    └──────────────── finish() ────────────┘
```

¶3 除 `run` 和析构函数之外，成员函数可以并发调用而不引起数据竞争。取出、放入队列和 `finish` 都是原子地执行的。

## 调度器与调度发送器（[exec.run.loop.types]）

### 调度器（¶1–5）

`get_scheduler()` 返回的调度器在产生它的 `run_loop` 销毁之前一直有效（¶2）。¶3 两个调度器相等当且仅当来自同一个 `run_loop`，比一般调度器只要求的单向条件更强（[[exec.sched]]）。

¶4–5 `schedule(sch)` 返回一个调度发送器。它的值完成和取消完成都发生在这个 loop 上，所以对这两种完成，[[g:completion-scheduler|完成调度器]]就是 `sch`。它没有错误完成，也就没有错误完成调度器。

### 完成签名取决于环境（¶6–8）

¶6 调度发送器的完成签名取决于接收器环境中的停止令牌：

| 环境的停止令牌 | 完成签名 |
|---|---|
| 永远不会被请求停止（满足 `unstoppable_token`，例如没有提供令牌） | `set_value_t()` |
| 可能被请求停止 | `set_value_t()`、`set_stopped_t()` |

没有错误完成，是因为把操作挂进队列不会失败。所以 `run_loop` 的调度器满足 *infallible-scheduler*（[[exec.sched#8]]），可以被 `task_scheduler` 包装（它要求被包装的调度器满足这个概念）。

¶8 `connect(sndr, rcvr)` 得到一个 *run-loop-opstate*，只在复制或移动接收器可能抛出异常时才可能抛出异常。

### 操作状态（¶9–10）

¶10 *run-loop-opstate* 的两个关键操作是：

- ¶10.3 `start(o)` 就是 `o.loop->push-back(addressof(o))`，把自己挂到队尾；
- ¶10.2 轮到它执行时，`execute()` 检查接收器的停止令牌：已请求停止就调用 `set_stopped`，否则调用 `set_value`。

所以取消在出队执行时检查，而不是在入队时。`run_loop` 不会因为停止请求把操作提前移出队列；已经排队的操作被请求停止后，仍要等轮到自己时才以 `set_stopped` 完成。

## 构造与析构（[exec.run.loop.ctor]）

¶1 新构造的 `run_loop` 计数为 0，状态为 starting。

¶2 析构时，如果计数不为 0，或者状态为 running，就调用 `std::terminate`；否则什么也不做。两种情形对应两类错误：

- 队列里还有工作。这些操作已经启动，必须完成；直接销毁 `run_loop` 意味着它们永远不会完成，违反 [[exec.async.ops#2]]。
- 状态为 running。这说明还有线程在 `run()` 里使用它。

从未 `run` 过（starting）或者 `finish` 了但没有 `run`（finishing），只要队列为空，析构都是合法的。

## run 与 finish（[exec.run.loop.members]）

¶1 内部的 *pop-front* 会阻塞（[[defns.block]]），直到下面两种情况之一发生：

- ¶1.1 计数为 0 且状态为 finishing：把状态设为 finished，返回空指针；
- ¶1.2 计数大于 0：从队首取出一项，计数减一，返回这一项。

¶2–3 *push-back* 把一项加到队尾，计数加一。它与取出这一项的那次 *pop-front* 同步（synchronizes with），所以入队之前对操作状态的写入，对执行它的线程可见（[[intro.races]]）。

¶5–6 `run()` 的前置条件是状态为 starting 或 finishing。它把 starting 改为 running（finishing 保持不变），然后不断取出并执行工作，直到 *pop-front* 返回空指针：

```cpp
while (auto* op = pop-front()) {
  op->execute();
}
```

¶8–10 `finish()` 的前置条件是状态为 starting 或 running，效果是把状态改为 finishing。它与返回空指针的那次 *pop-front* 同步。

由这些前置条件可以推出几条使用规则：

- `run()` 只能调用一次。有线程在 `run()` 里时状态是 running，此后状态只会变成 finishing、finished，再调用 `run()` 都违反前置条件。
- `finish()` 也只能调用一次。调用之后状态不再是 starting 或 running。`sync_wait` 的接收器在三种完成函数里都调用 `finish()`，但恰好只有一种完成会发生。
- `finish()` 不丢弃已排队的工作，`run()` 要把它们执行完才返回。
- 先 `finish()` 再 `run()` 是合法的。`sync_wait` 等待一个同步完成的发送器时就是这样：`start(op)` 期间接收器已经调用了 `finish()`，随后 `run()` 看到状态为 finishing、队列为空，立即返回。

## 常见错误

### 忘记 finish

没有人调用 `finish()`，`run()` 就会在队列空时永远阻塞在 *pop-front* 里。`sync_wait` 依靠接收器在完成时调用 `finish()`。自己使用 `run_loop` 时，要确保在所有工作提交之后，或者收到某个结束信号时，调用 `finish()`。

### finish 之后还往里调度

`finish()` 之后，`run()` 一看到队列为空就返回，状态变成 finished。此后再启动一个调度到这个 loop 的操作，它会被放进队列，但再也没有线程执行它：操作永远不会完成，`run_loop` 析构时计数也不为 0，于是 `terminate`。标准没有为 finished 状态下的入队规定任何错误处理，调用者要自己避免。

## 思考题

!!! question "1. 在 run() 里调度到同一个 loop"
    一项正在 loop 上执行的工作，又 `schedule(sch)` 到同一个 loop，并 connect、start 了另一个操作。会死锁吗？会递归吗？

<details markdown="1">
<summary>答案</summary>

都不会。`start` 只是 *push-back*，把新操作挂到队尾就返回。当前工作执行完之后，`run()` 的循环再从队列中取出它。递归调度因此变成了排队，栈深度不会增长。
</details>

!!! question "2. 为什么只在可停止时才有 set_stopped？"
    把调度发送器的签名做成依赖环境，而不是总包含 `set_stopped_t()`，有什么好处？

<details markdown="1">
<summary>答案</summary>

环境的停止令牌永远不会被请求停止时，`execute()` 里的 `set_stopped` 分支实际上永远不会执行。去掉这个签名，下游得到的类型更精确。例如 `sync_wait` 的环境没有停止令牌，`sync_wait(schedule(loop.get_scheduler()))` 等待的发送器就只有 `set_value_t()`。`task_scheduler` 要求被包装的调度器在空环境 `env<>` 下满足 *infallible-scheduler*，即签名恰好是 `completion_signatures<set_value_t()>`，`run_loop` 的调度器也正好满足。

这也是 [[exec.async.ops#13]] 所说的：签名由发送器类型和环境类型共同决定。
</details>

## 小结

| 问题 | 答案 |
|---|---|
| 谁执行工作 | 调用 `run()` 的线程 |
| 调度的代价 | 把操作状态挂进侵入式队列，不分配内存 |
| 完成签名 | `set_value_t()`，环境可停止时再加 `set_stopped_t()`，没有错误完成 |
| 取消何时生效 | 工作出队执行时 |
| `finish()` | 不丢弃已排队的工作；`run()` 在队列清空后返回 |
| 析构 | 队列不空或仍在 running 时 `terminate` |
