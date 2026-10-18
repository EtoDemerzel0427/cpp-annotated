---
title: run_loop
summary: 标准里最简单的执行资源——一个线程安全的 FIFO 工作队列，由调用 run() 的线程执行；四种状态 starting / running / finishing / finished；调度发送器在停止令牌可能被请求时多一个 set_stopped；析构时队列非空或仍在运行就 terminate；sync_wait 用它实现
status: done
covers: exec.ctx, exec.run.loop.general, exec.run.loop.types, exec.run.loop.ctor, exec.run.loop.members
papers: P2300R10
related: exec.sched, exec.consumers, exec.async.ops, exec.opstate, intro.races, defns.block
tags: 标准库, std::execution, 执行上下文, 调度器
updated: 2026-10-18
---

[exec.ctx]（执行上下文）目前只有一个成员：`run_loop`。它是标准提供的最小执行资源：**不创建线程**，只维护一个队列；谁调用 `run()`，谁就成为执行队列中工作的那个线程。`sync_wait` 的默认实现就是"在栈上放一个 `run_loop`、启动操作、然后 `run()`"（[[exec.consumers]]）。

它也是理解调度器实现的最好样板：schedule 一个操作 = 把操作状态挂进队列；执行 = 从队列取出、调用它的完成。整个过程不分配内存。

```cpp title="run-loop.cpp"
namespace ex = std::execution;

ex::run_loop loop;
auto sch = loop.get_scheduler();

std::jthread worker([&] { loop.run(); });          // worker 线程成为 loop 的执行代理

auto s = ex::schedule(sch) | ex::then([] { return std::this_thread::get_id(); });
auto [id] = std::this_thread::sync_wait(std::move(s)).value();   // id == worker 的线程 id
loop.finish();                                      // 让 run() 在队列清空后返回
```

## 概述（[exec.run.loop.general]）

¶1 `run_loop` 是可以调度工作的执行资源。它维护一个**线程安全的先进先出**工作队列；`run` 成员函数在调用它的线程上循环地取出并执行队列元素。

¶2 每个 `run_loop` 实例有一个关联的**计数**（队列中工作项的个数）和一个**状态**：*starting*、*running*、*finishing*、*finished* 之一。

¶3 除 `run` 和析构函数外，成员函数的并发调用不引入数据竞争。*pop-front*、*push-back*、`finish` **原子地**执行。

¶4 *Recommended practice*：实现应使用操作状态的**侵入式队列**保存工作项，使调度不需要分配。

```cpp
class run_loop {
  class run-loop-scheduler;          // exposition only
  class run-loop-sender;             // exposition only
  struct run-loop-opstate-base {     // exposition only
    virtual void execute() noexcept = 0;
    run_loop* loop;
    run-loop-opstate-base* next;     // 侵入式链表指针
  };
  template<class Rcvr> using run-loop-opstate = unspecified;
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

`run-loop-opstate-base` 里的 `next` 指针就是 ¶4 所说的侵入式队列：每个被调度的操作状态**自己**就是一个链表节点。队列不需要为节点分配内存，代价是操作状态在排队期间绝不能移动——这正是 [[exec.opstate]] ¶3 禁止移动操作状态的原因之一。`run_loop` 本身不可移动（移动构造被删除），因为队列中的操作状态存着 `loop` 指针。

状态机：

```text
        run()              finish()            队列空
starting ─────► running ───────────► finishing ────────► finished
    │                                   ▲
    └───────────── finish() ────────────┘
```

## 关联类型（[exec.run.loop.types]）

### run-loop-scheduler（¶1–5）

- ¶1 未指定类型，模型化 `scheduler`；
- ¶2 在产生它的 `run_loop` 生存期结束前一直有效；
- ¶3 两个实例相等**当且仅当**来自同一个 `run_loop`（比 [[exec.sched#4]] 的一般要求"仅当"更强）；
- ¶4 `schedule(sch)` 的类型是 *run-loop-sender*，`sch` 不抛时它也不抛；
- ¶5 对 `set_error_t` 以外的完成标签，`get_completion_scheduler<Tag>(get_env(schedule(sch))) == sch`。value 和 stopped 完成都在这个 loop 上发生；没有 error 完成，所以也没有 error 完成调度器。

### run-loop-sender（¶6–8）

¶6 签名取决于环境：

- `unstoppable_token<stop_token_of_t<E>>` 为 true（例如环境没有停止令牌）：`completion_signatures<set_value_t()>`；
- 否则：`completion_signatures<set_value_t(), set_stopped_t()>`。

**没有 error 完成**：把操作挂进队列不会失败（侵入式，无分配）。因此 run_loop 的调度器满足 *infallible-scheduler*（[[exec.sched#8]]），可以被 `task_scheduler` 包装、被 `affine` 用作"回到原处"的目标。

¶7 有效期同 `run_loop`。

¶8 `connect(sndr, rcvr)` 的类型是 *run-loop-opstate*<decay_t<decltype((rcvr))>>，仅当复制/移动接收器可能抛异常时才可能抛异常。value 与 stopped 的完成调度器都等于产生它的 *run-loop-scheduler*。

### run-loop-opstate（¶9–10）

¶9 私有地、无歧义地派生自 *run-loop-opstate-base*。

¶10 设 `o` 是这样一个非 const 左值，`REC(o)` 是它所持有的接收器：

- ¶10.1 `REC(o)` 所指对象在 `o` 的生存期内有效；
- ¶10.2 `o.execute()` 等价于
  ```cpp
  if (get_stop_token(REC(o)).stop_requested()) {
    set_stopped(std::move(REC(o)));
  } else {
    set_value(std::move(REC(o)));
  }
  ```
- ¶10.3 `start(o)` 等价于 `o.loop->push-back(addressof(o));`。

所以取消检查发生在**出队执行时**，而不是入队时：已经排队的工作被请求停止后，轮到它时以 `set_stopped` 完成。注意 run_loop 不会因为停止请求而把操作从队列中**提前移除**——取消只是让它在被执行时选择 stopped 分支。

## 构造与析构（[exec.run.loop.ctor]）

¶1 构造：*Postconditions*：计数为 0，状态为 *starting*。

¶2 析构：若计数不为 0，**或者**状态为 *running*，调用 `terminate`；否则无效果。

两种 terminate 的情形分别对应两类错误：

- 队列里还有工作：这些操作状态已经 `start` 了，必须完成；直接析构 `run_loop` 意味着它们永远不会完成，违反 [[exec.async.ops#2]]。
- 状态为 running：某个线程还在 `run()` 里使用它。

注意状态为 *starting*（从没 `run` 过）且队列为空时，析构是合法的；状态为 *finishing*（`finish` 了但没 `run`）且队列为空也是合法的。

## 成员函数（[exec.run.loop.members]）

¶1 *pop-front*：**阻塞**（[[defns.block]]）直到下列之一成立：

- ¶1.1 计数为 0 且状态为 *finishing*：将状态设为 *finished*，返回 `nullptr`；
- ¶1.2 计数大于 0：从队首取出一项，计数减一，返回它。

¶2–3 *push-back*：把 `item` 加到队尾，计数加一。*Synchronization*：它与取得该 `item` 的 *pop-front* 同步（synchronizes with）——入队之前对操作状态的写入，对执行它的线程可见（[[intro.races]]）。

¶4 `get_scheduler()`：返回可以把工作调度到本实例的 *run-loop-scheduler*。

¶5 `run()` *Preconditions*：状态为 *starting* 或 *finishing*。

¶6 效果：若状态为 *starting*，设为 *running*（*finishing* 则保持不变），然后

```cpp
while (auto* op = pop-front()) {
  op->execute();
}
```

¶7 状态变化不引入数据竞争。

¶8 `finish()` *Preconditions*：状态为 *starting* 或 *running*。¶9 效果：状态设为 *finishing*。¶10 *Synchronization*：`finish` 与返回 `nullptr` 的那次 *pop-front* 同步。

几点推论：

- **`run()` 只能被一个线程调用一次**（前置条件：*starting* 或 *finishing*；一旦有线程在 `run`，状态是 *running*，第二个线程再调用 `run` 就违反前置条件，UB）。
- **`run()` 在 `finish()` 之后、队列清空时才返回**。`finish()` 不会丢弃已排队的工作：它们照样被执行完。
- **先 `finish()` 再 `run()` 是合法的**：`run()` 把排队的工作执行完就返回。这正是 `sync_wait` 中同步完成的发送器的情形：`start(op)` 期间接收器已经调用了 `finish()`，随后 `run()` 发现状态为 *finishing*、队列为空，立即返回。
- **`finish()` 只能调用一次**（前置条件排除了在 *finishing*/*finished* 状态下再调用）。`sync_wait` 的接收器在三种完成中各调用一次，因为恰好一种完成会发生，所以恰好调用一次。
- `run()` 和 `finish()` 都是 `noexcept`。

## 陷阱

!!! pitfall "忘记 finish"
    没有人调用 `finish()`，`run()` 就会在队列空时永远阻塞在 *pop-front* 里。`sync_wait` 依赖接收器在完成时调用 `finish()`；自己用 `run_loop` 时，要确保所有工作都提交后、或者在某个"结束"信号到来时调用 `finish()`。

!!! pitfall "finish 之后还往里调度"
    `finish()` 之后 `run()` 一旦看到队列为空就返回、状态变为 *finished*。此后再 `start` 一个调度到这个 loop 的操作，它被 `push-back` 进队列但再也没有人执行——操作永不完成，而且 `run_loop` 析构时计数非 0，`terminate`。规范没有为"*finished* 状态下 push-back"规定错误处理；调用者要自己保证不会这样做。

## 思考题

!!! question "1. 在 run() 内部调度到同一个 loop"
    一个在 loop 上执行的工作，又 `schedule(sch)` 到同一个 loop 并 connect/start 了另一个操作。会死锁吗？会递归吗？

<details markdown="1">
<summary>答案</summary>

都不会。`start` 只是 *push-back*，把新操作挂到队尾就返回；当前工作执行完之后，`run()` 的循环再从队首取出它。所以 run_loop 天然地把"递归调度"变成"排队"，栈深度不会增长。这也是 `sync_wait` 中可以安全地把大量工作调度回 run_loop 的原因。
</details>

!!! question "2. 为什么 run-loop-sender 在可停止时才有 set_stopped？"
    把签名做成依赖环境，而不是总包含 `set_stopped_t()`，有什么好处？

<details markdown="1">
<summary>答案</summary>

环境的停止令牌是 `never_stop_token` 时，`get_stop_token(REC(o)).stop_requested()` 永远为 false，`set_stopped` 分支实际上不会执行。去掉这个签名后，下游类型更精确：比如 `sync_wait` 环境没有停止令牌，于是 `sync_wait(schedule(loop.get_scheduler()))` 的发送器只有 `set_value_t()`；`affine`/`task_scheduler` 要求的 *infallible-scheduler* 在不可停止的环境下要求签名恰为 `completion_signatures<set_value_t()>`，也正好满足。这体现了 [[exec.async.ops#13]]"签名由发送器类型和环境类型共同决定"。
</details>

## 小结

- `run_loop`：线程安全 FIFO 队列 + 调用 `run()` 的线程；侵入式、无分配。
- 状态：starting → running → finishing → finished；`finish()` 不丢弃已排队工作。
- 调度发送器：`set_value_t()`，环境可停止时再加 `set_stopped_t()`；无 error，满足 *infallible-scheduler*。
- 取消在出队执行时检查。
- 析构时队列非空或仍在 running → `terminate`。
