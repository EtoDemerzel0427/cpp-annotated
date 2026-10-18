---
title: 发送器消费者：sync_wait
summary: this_thread::sync_wait 阻塞当前线程直到发送器完成，并以 optional<tuple<值...>> 返回结果：value → 有值，error → 抛异常，stopped → 空 optional；内部用一个 run_loop 驱动，并通过环境提供调度器与前进保证委托；sync_wait_with_variant 处理多 value 签名
status: done
covers: exec.sync.wait, exec.sync.wait.var
papers: P2300R10
related: exec.run.loop, exec.queries, exec.snd.transform, exec.cmplsig, intro.progress, exec.spawn
tags: 标准库, std::execution, sync_wait, 阻塞
updated: 2026-10-18
---

发送器是惰性的描述，总要有人把它跑起来、拿到结果。**消费者**（[[exec.async.ops#14]] ¶14.3）就是做这件事的：接受发送器，返回的不是发送器。本页讲最基本的两个消费者 `sync_wait`、`sync_wait_with_variant`；另一个消费者 `spawn`（"发射后由 scope 负责"）在 [[exec.spawn]]。

`sync_wait` 是同步世界与异步世界的**边界**：典型地只在 `main` 或测试里用一次。在异步代码内部调用它会阻塞一个工作线程，通常是错误的（见陷阱）。

## sync_wait（[exec.sync.wait]）

¶1 `sync_wait` 与 `sync_wait_with_variant` 阻塞当前执行线程直到发送器完成，并返回其异步结果。`sync_wait` *Mandates* 输入发送器恰有一种 value 完成签名。

### 环境（¶2）

```cpp
struct sync-wait-env {
  execution::run_loop* loop;
  auto query(execution::get_scheduler_t) const noexcept            { return loop->get_scheduler(); }
  auto query(execution::get_start_scheduler_t) const noexcept      { return loop->get_scheduler(); }
  auto query(execution::get_delegation_scheduler_t) const noexcept { return loop->get_scheduler(); }
};
```

三个查询都回答为内部 `run_loop` 的调度器（[[exec.run.loop]]）。没有回答的查询：

- `get_stop_token` → 默认 `never_stop_token`：`sync_wait` 的发送器**不能从外部取消**；
- `get_allocator` → 非良构：没有分配器；
- `get_domain` → 由 `get_scheduler` 推出：run_loop 调度器的 domain（通常是 `default_domain`）。

### 返回类型（¶3）

```cpp
template<execution::sender_in<sync-wait-env> Sndr>
  using sync-wait-result-type =
    optional<execution::value_types_of_t<Sndr, sync-wait-env, decayed-tuple, type_identity_t>>;
```

`Variant` 位置是 `type_identity_t`：只接受一个实参，所以发送器有不止一种 value 签名时类型非良构——"恰好一种"就是这样被强制的。没有 value 签名时也非良构（`type_identity_t<>` 不成立）。结果：

| 发送器 value 签名 | `sync_wait` 返回 |
|---|---|
| `set_value_t()` | `optional<tuple<>>` |
| `set_value_t(int)` | `optional<tuple<int>>` |
| `set_value_t(int&, std::string)` | `optional<tuple<int, std::string>>`（decay） |
| 两种 value 签名 | 非良构；用 `sync_wait_with_variant` |

### 分派（¶4–5）

¶4 `sync_wait(sndr)` 等价于 `apply_sender(Domain(), sync_wait, sndr)`，`Domain` 是 `get_completion_domain<set_value_t>(get_env(sndr), sync-wait-env{})` 的类型——发送器 value 完成所在的 domain 可以定制 `sync_wait`（[[exec.snd.transform]]）。

¶5 *Mandates*：`sender_in<Sndr, sync-wait-env>`；*sync-wait-result-type*<Sndr> 良构；`apply_sender` 表达式的类型恰为 *sync-wait-result-type*<Sndr>——定制实现也必须返回这个类型。

### 默认实现（¶6–10）

```cpp
template<class Sndr>
struct sync-wait-state {
  execution::run_loop loop;
  exception_ptr error;
  sync-wait-result-type<Sndr> result;
};
```

接收器 *sync-wait-receiver*：

- ¶7 `set_value(args...)`：`try { state->result.emplace(args...); } catch (...) { state->error = current_exception(); }`，然后 `state->loop.finish()`；
- ¶8 `set_error(err)`：`state->error = AS-EXCEPT-PTR(err)`，然后 `finish()`；
- ¶9 `set_stopped()`：只 `finish()`，`result` 保持为空；
- `get_env()`：返回 `{&state->loop}`。

¶10 `sync_wait.apply_sender(sndr)`（*sender-to* 不成立时非良构）：

```cpp
sync-wait-state<Sndr> state;
auto op = connect(sndr, sync-wait-receiver<Sndr>{&state});
start(op);

state.loop.run();
if (state.error) {
  rethrow_exception(std::move(state.error));
}
return std::move(state.result);
```

注意几点：

- `connect(sndr, ...)` 传的是 `sndr` 本身（保持值类别）：`sync_wait(s)` 以左值 connect（要求 `s` 可复制），`sync_wait(std::move(s))` 以右值 connect。
- `start(op)` 之后调用 `loop.run()`：当前线程开始**执行 run_loop 队列里的工作**，直到接收器调用 `finish()` 且队列清空。如果发送器把工作调度到 `get_scheduler(env)`（即这个 run_loop）上，这些工作就由调用 `sync_wait` 的线程亲自执行。
- 状态、操作状态都在 `sync_wait` 的栈帧上——零分配。
- `run()` 返回意味着 `finish()` 已被调用，也就是完成操作已经开始执行；此后 `op` 离开作用域被销毁，符合 [[exec.async.ops#7]]。

### 语义要求（¶11）

¶11 `sync_wait(sndr)` 的行为未定义，除非：

- ¶11.1 它以**前进保证委托**（[[intro.progress]]）的方式阻塞当前线程（[[defns.block]]），直到发送器完成。注 1：默认实现通过环境的 `get_delegation_scheduler` 提供 run_loop 调度器来实现委托；run_loop 由当前线程驱动。
- ¶11.2 按如下方式返回结果：value → 结果数据装在 tuple 里、放进有值的 `optional`；error → 抛异常；stopped → 空 `optional`。

这一段约束的对象主要是**定制实现**（通过 `apply_sender` 替换的 `sync_wait`）：不管怎样实现，必须真的阻塞、必须提供前进保证委托、必须按这个约定返回。

!!! note "前进保证委托是什么意思"
    [[intro.progress#13]] 规定：线程 P 以前进保证委托的方式阻塞等待一组线程 S 时，在 P 阻塞的整个期间，实现必须保证 S 中**至少一个**线程的前进保证不弱于 P 的。`sync_wait` 的默认实现用一种很朴素的方式做到这一点：调用线程并不闲着，而是在 `loop.run()` 里执行被调度到 run_loop 上的工作——被等待的工作若把需要"一定能跑起来"的部分调度到 `get_delegation_scheduler` 给出的调度器上，它就由调用线程以调用线程自己的前进保证来执行。

## sync_wait_with_variant（[exec.sync.wait.var]）

¶1 `sync_wait_with_variant(sndr)` ≡ `apply_sender(Domain(), sync_wait_with_variant, sndr)`，`Domain` 同上。注意这里的 `Sndr` 被定义为 `decltype(into_variant(sndr))`。

¶2 *Mandates* 与 `sync_wait` 对应：结果类型是 *sync-wait-with-variant-result-type*<Sndr> = `optional<value_types_of_t<Sndr, sync-wait-env>>`，即 `optional<variant<tuple<...>, ...>>`。

¶3 默认实现：

```cpp
using result_type = sync-wait-with-variant-result-type<Sndr>;
if (auto opt_value = sync_wait(into_variant(sndr))) {
  return result_type(std::move(get<0>(*opt_value)));
}
return result_type(nullopt);
```

`into_variant` 把多种 value 签名合并成一种，于是可以交给 `sync_wait`；`sync_wait` 返回 `optional<tuple<variant<...>>>`，取出那个唯一的元素即可。

¶4 语义要求同 `sync_wait`；注 1：默认实现的前进保证委托依赖 `sync_wait` 提供的委托。

```cpp title="sync-wait-variant.cpp"
namespace ex = std::execution;

// 设 s 的签名为 set_value_t(int)、set_value_t(std::string)
if (auto r = std::this_thread::sync_wait_with_variant(std::move(s))) {
  std::visit([](auto& tup) { /* tup 是 tuple<int> 或 tuple<std::string> */ }, *r);
}
```

## 陷阱

!!! pitfall "在 run_loop 或线程池的工作线程里调用 sync_wait"
    在一个工作线程上 `sync_wait(sndr)`，而 `sndr` 需要同一个线程池的线程才能完成——若池里所有线程都在 `sync_wait` 里阻塞，就死锁了。`sync_wait` 只把它**自己的** run_loop 借给被等待的工作，对其他执行资源无能为力。在异步代码内部，用 `let_value`、`when_all` 组合，或者在协程里 `co_await`（[[exec.as.awaitable]]），而不是 `sync_wait`。

!!! pitfall "error 完成被包成了什么异常"
    *AS-EXCEPT-PTR*：`exception_ptr` 原样重新抛出；`error_code` 被包成 `system_error` 抛出；其他类型 `E` 直接抛出 `E` 类型的对象。所以 `sync_wait(just_error(std::make_error_code(...)))` 抛 `std::system_error`，而 `sync_wait(just_error(42))` 抛 `int`。

!!! pitfall "sync_wait 不能从外部取消"
    环境里没有停止令牌。需要可取消的同步等待时：
    ```cpp title="cancellable-sync-wait.cpp"
    std::inplace_stop_source src;
    auto r = std::this_thread::sync_wait(
      ex::write_env(std::move(s), ex::prop(std::get_stop_token, src.get_token())));
    // 另一线程调用 src.request_stop()
    ```

## 思考题

!!! question "1. sync_wait 返回之后"
    `sync_wait` 返回时，发送器创建的所有工作都结束了吗？

<details markdown="1">
<summary>答案</summary>

外部接收器的完成函数已经开始执行（`finish()` 在 `set_*` 内被调用），按结构化并发，所有已启动的**子操作**都已在其父操作完成前完成（[[exec.async.ops#2]] ¶2.5）。但有两个细节：(1) 接收器的 `set_value` 调用 `finish()` 之后到它返回之间，调用 `set_value` 的那个线程（可能是线程池线程）还在执行几条指令；`sync_wait` 的线程可能已经从 `run()` 返回并销毁了 `state`——这是被 [[exec.async.ops#8]] 允许的，前提是接收器在 `finish()` 之后不再访问 `state`。(2) 通过 `spawn` 交给某个 async scope 的工作不是 `sndr` 的子操作，不受此约束，需要由 scope 的 `join` 等待（[[exec.scope]]）。
</details>

!!! question "2. 为什么 set_value 也可能导致抛异常？"
    *sync-wait-receiver* 的 `set_value` 里有 `try/catch`。什么情况下会走到 `catch`？

<details markdown="1">
<summary>答案</summary>

`state->result.emplace(args...)` 要把结果 decay-copy 进 `optional<tuple<...>>`；若某个值类型的复制/移动构造会抛异常（比如以左值引用发出的 `std::string` 需要复制、分配内存失败），就会抛出。接收器的 `set_value` 必须是 noexcept 的，所以只能捕获并存进 `state->error`，之后 `sync_wait` 重新抛出它。于是一个"成功"的发送器，从 `sync_wait` 看也可能表现为异常。
</details>

## 小结

- `sync_wait(s)`：阻塞当前线程，返回 `optional<tuple<值...>>`；value → 有值，error → 抛异常（经 *AS-EXCEPT-PTR*），stopped → 空。
- 要求恰好一种 value 签名；多种时用 `sync_wait_with_variant`（返回 `optional<variant<tuple<...>...>>`）。
- 内部：栈上的 `run_loop` + 状态 + 操作状态；`start` 后 `loop.run()`，接收器 `finish()` 结束循环。
- 环境提供 `get_scheduler`/`get_start_scheduler`/`get_delegation_scheduler` = run_loop 调度器；没有停止令牌。
- 可通过 `apply_sender` 由发送器的 value 完成 domain 定制。
