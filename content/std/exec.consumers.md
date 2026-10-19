---
title: 发送器消费者：sync_wait
summary: this_thread::sync_wait 阻塞当前线程直到发送器完成，以 optional<tuple<值...>> 返回结果，错误变成异常、取消变成空 optional；sync_wait_with_variant 处理有多种值签名的发送器。
status: draft
covers: exec.sync.wait, exec.sync.wait.var
papers: P2300R10
related: exec.run.loop, exec.queries, exec.snd.transform, exec.cmplsig, intro.progress, exec.spawn
tags: 标准库, std::execution, sync_wait, 阻塞
updated: 2026-10-19
---

!!! tldr
    - `this_thread::sync_wait(s)` 启动发送器 `s` 并阻塞当前线程，直到它完成。
    - 值完成返回装着 `tuple<值...>` 的 `optional`；错误完成变成异常抛出；取消完成返回空的 `optional`。
    - `sync_wait` 要求发送器恰好有一种值签名；有多种的用 `sync_wait_with_variant`，它返回 `optional<variant<tuple<...>...>>`。
    - 默认实现在栈上放一个 `run_loop`，等待期间调用线程亲自执行调度到这个 `run_loop` 上的工作。
    - 它的环境里没有停止令牌，所以不能从外部取消；在异步代码内部调用它容易造成死锁。

本页的例子用到 C++26 的 `std::execution` 发送器。本机 Clang 23 附带的 libc++ 还没有实现这部分库，例子都没有经过编译验证，因此不加判定标记。

## 同步世界与异步世界的边界

```cpp title="sync-wait.cpp"
namespace ex = std::execution;

int main() {
  auto s = ex::schedule(ex::get_parallel_scheduler())
         | ex::then([] { return 42; });
  auto [v] = std::this_thread::sync_wait(std::move(s)).value();   // v == 42
}
```

[[g:sender|发送器]]只是对一项工作的描述，不会自己运行。[[exec.async.ops#14]] 把接受发送器、但不返回发送器的函数叫做**发送器消费者**（sender consumer），它负责真正运行这项工作。本页讲 `sync_wait` 和 `sync_wait_with_variant`；另一个消费者 `spawn` 见 [[exec.spawn]]。

`sync_wait` 把异步的结果变回普通的返回值，所以它是同步代码与异步代码的边界。一般只在 `main` 或测试里用一次。

## 返回什么（[exec.sync.wait] ¶1、¶3、¶11）

¶11.2 `sync_wait` 把发送器的三种完成翻译成三种结果：

| 发送器的完成 | `sync_wait` 的结果 |
|---|---|
| `set_value(args...)` | 返回有值的 `optional`，里面是 `tuple<args...>` |
| `set_error(err)` | 抛出异常 |
| `set_stopped()` | 返回空的 `optional` |

¶3 返回类型是 `optional<value_types_of_t<Sndr, sync-wait-env, decayed-tuple, type_identity_t>>`。`value_types_of_t` 把每种值签名变成一个 `decayed-tuple`，再把这些 tuple 交给最后一个参数组合起来。这里用的是 `type_identity_t`，它只接受一个实参。

¶1 所以发送器恰好有一种值签名时，返回类型才良构。有两种就要改用 `sync_wait_with_variant`；一种也没有（例如 `just_stopped()`）同样非良构。

| 发送器的值签名 | `sync_wait` 的返回类型 |
|---|---|
| `set_value_t()` | `optional<tuple<>>` |
| `set_value_t(int)` | `optional<tuple<int>>` |
| `set_value_t(int&, std::string)` | `optional<tuple<int, std::string>>`，类型经过 decay |
| 两种值签名 | 非良构 |

### 错误变成什么异常

[[exec.general#8]] 的 *AS-EXCEPT-PTR* 决定错误如何变成异常：`exception_ptr` 原样重新抛出；`error_code` 包装成 `system_error` 抛出；其他类型 `E` 的错误直接抛出那个 `E` 对象。

所以 `sync_wait(just_error(std::make_error_code(std::errc::timed_out)))` 抛出 `std::system_error`，而 `sync_wait(just_error(42))` 抛出一个 `int`。

## 默认实现（¶2、¶6–10）

¶10 `sync_wait` 的默认实现很短：

```cpp
sync-wait-state<Sndr> state;   // run_loop、exception_ptr、optional 结果
auto op = connect(sndr, sync-wait-receiver<Sndr>{&state});
start(op);

state.loop.run();
if (state.error) {
  rethrow_exception(std::move(state.error));
}
return std::move(state.result);
```

¶7–9 接收器的三个完成函数分别把值存进 `result`、把错误转成 `exception_ptr` 存进 `error`、或者什么也不存，然后都调用 `loop.finish()`。

¶2 接收器的环境 *sync-wait-env* 只回答三个查询，`get_scheduler`、`get_start_scheduler`、`get_delegation_scheduler`，答案都是这个 [[exec.run.loop|run_loop]] 的调度器。

几点值得注意：

- `start(op)` 之后，`loop.run()` 让当前线程执行 run_loop 队列里的工作，直到接收器调用 `finish()` 并且队列清空。如果发送器把工作调度到环境给出的调度器上，这些工作就由调用 `sync_wait` 的线程亲自执行。
- 状态和操作状态都是 `sync_wait` 栈帧上的局部变量，不需要动态分配。
- connect 用的是 `sndr` 本身，保持它的值类别。`sync_wait(s)` 以左值 connect，要求 `s` 能被复制；`sync_wait(std::move(s))` 以右值 connect。
- `run()` 返回时，完成函数已经开始执行，异步操作的生存期已经结束（[[exec.async.ops#7]]），这时销毁 `op` 是安全的。

¶7 值完成也可能变成异常。把结果复制进 `optional<tuple<...>>` 时，如果某个值的复制构造抛出异常（例如复制一个以左值引用发出的 `std::string` 时内存不足），接收器的 `set_value` 是 noexcept 的，只能捕获异常并存进 `error`，之后由 `sync_wait` 重新抛出。

## 必须真的阻塞（¶4–5、¶11）

¶4 `sync_wait(sndr)` 先找到发送器值完成所在的 domain，再通过 `apply_sender` 调用这个 domain 的实现（[[exec.snd.transform]]）。所以一个 domain 可以为自己的发送器提供另一种 `sync_wait`。¶5 无论哪种实现，返回类型都必须恰好是上面的 *sync-wait-result-type*。

¶11.1 无论哪种实现都必须阻塞当前线程直到发送器完成，并且带有**前进保证委托**（forward progress guarantee delegation，[[intro.progress#13]]）。意思是：线程 P 阻塞等待一组线程 S 时，实现要保证在 P 阻塞期间，S 中至少有一个线程的前进保证不弱于 P。

默认实现的做法很直接（注 1）：调用线程不闲着，而是在 `loop.run()` 里执行被调度到 run_loop 上的工作。被等待的工作只要把必须执行的部分调度到 `get_delegation_scheduler` 给出的调度器上，就能借用调用线程自己的前进保证。

## sync_wait_with_variant（[exec.sync.wait.var]）

```cpp title="sync-wait-variant.cpp"
// 设 s 可能以 set_value(int) 或 set_value(std::string) 完成
if (auto r = std::this_thread::sync_wait_with_variant(std::move(s))) {
  std::visit([](auto& tup) { /* tup 是 tuple<int> 或 tuple<std::string> */ }, *r);
}
```

¶2 返回类型是 `optional<value_types_of_t<Sndr, sync-wait-env>>`，也就是 `optional<variant<tuple<...>, ...>>`。¶1 和 `sync_wait` 一样，可以由 domain 定制。

¶3 默认实现先用 `into_variant` 把多种值签名合并成一种 `set_value(variant<tuple<...>...>)`，再交给 `sync_wait`，最后从返回的 `optional<tuple<variant<...>>>` 中取出那个唯一的元素：

```cpp
if (auto opt_value = sync_wait(into_variant(sndr))) {
  return result_type(std::move(get<0>(*opt_value)));
}
return result_type(nullopt);
```

¶4 它对阻塞和返回值的要求与 `sync_wait` 相同；默认实现的前进保证委托就来自它调用的 `sync_wait`。

## 常见错误

### 在工作线程里调用 sync_wait

在线程池的一个工作线程上调用 `sync_wait(sndr)`，而 `sndr` 需要同一个线程池的线程才能完成。如果池里所有线程都在 `sync_wait` 里阻塞，就会死锁。`sync_wait` 只把它自己的 run_loop 借给被等待的工作，对其他执行资源无能为力。

在异步代码内部，应当用 `let_value`、`when_all` 把工作组合起来，或者在协程里 `co_await` 它（[[exec.as.awaitable]]）。

### 以为 sync_wait 能被取消

*sync-wait-env* 不回答 `get_stop_token`，被等待的工作得到的是默认的 `never_stop_token`，永远不会收到停止请求。需要可取消的同步等待时，用 `write_env` 自己提供一个停止令牌：

```cpp title="cancellable-sync-wait.cpp"
std::inplace_stop_source src;
auto r = std::this_thread::sync_wait(
    ex::write_env(std::move(s), ex::prop(std::get_stop_token, src.get_token())));
// 另一个线程调用 src.request_stop()
```

## 思考题

!!! question "sync_wait 返回之后，工作都结束了吗？"
    `sync_wait` 返回时，发送器启动的所有工作是否都已经结束？

<details markdown="1">
<summary>答案</summary>

`sndr` 启动的子操作都已结束：[[exec.async.ops#2]] 第 2.5 项规定子操作在父操作完成之前完成，而 `sync_wait` 等到了 `sndr` 的完成。

但通过 `spawn` 交给某个异步作用域（async scope）的工作不是 `sndr` 的子操作，不受这条约束，要由那个作用域的 `join` 来等待（[[exec.scope]]）。
</details>

## 小结

| 问题 | 答案 |
|---|---|
| 值完成 | 返回有值的 `optional<tuple<值...>>` |
| 错误完成 | 抛出异常；`error_code` 包装成 `system_error` |
| 取消完成 | 返回空 `optional` |
| 多种值签名 | 用 `sync_wait_with_variant` |
| 等待期间 | 调用线程驱动栈上的 `run_loop` |
| 取消 | 环境里没有停止令牌；需要时用 `write_env` 提供 |
