---
title: connect
summary: connect(sndr, rcvr) 先用接收器环境做 transform_sender，再调用发送器的 connect 成员；不是发送器而是可等待体时，用一个阐述用协程 connect-awaitable 把它包成操作状态；noexcept 只能取决于环境类型（否则 IFNDR）
status: done
covers: exec.connect
papers: P2300R10
related: exec.async.ops, exec.snd, exec.snd.transform, exec.opstate, exec.recv, exec.as.awaitable, dcl.fct.def.coroutine, expr.await
tags: 标准库, std::execution, connect, 协程, IFNDR
updated: 2026-10-18
---

`connect` 是"描述"变成"运行实体"的那一步：输入一个发送器和一个接收器，输出一个操作状态（[[exec.async.ops#9]]）。它看起来只是转调 `sndr.connect(rcvr)`，但规范在前后各加了一道工序：

1. **之前**：用接收器的环境对发送器做 `transform_sender`——这是 domain 定制介入的地方（[[exec.snd.transform]]）；
2. **兜底**：发送器没有 `connect` 成员、但它是一个可等待体时，用一个协程把它包起来。

## 定义（¶1–2、¶6）

¶2 设 `new_sndr` 为 `transform_sender(sndr, get_env(rcvr))`，`DS`、`DR` 分别为 `decay_t<decltype((new_sndr))>` 与 `decay_t<Rcvr>`。

¶6 `connect(sndr, rcvr)` 表达式等价于：

- ¶6.1 `new_sndr.connect(rcvr)`，若良构。*Mandates*：其类型满足 `operation_state`。
- ¶6.2 否则，*connect-awaitable*(new_sndr, rcvr)。

`rcvr` 只求值一次。*Mandates*（¶6.8–6.9）：

- `sender_in<Sndr, env_of_t<Rcvr>>`——发送器在接收器的环境下有确定的签名；
- *receiver-of*<Rcvr, completion_signatures_of_t<Sndr, env_of_t<Rcvr>>>——接收器能接住每一种完成。

这两条是用户遇到"发送器与接收器不匹配"时看到的诊断来源。它们是 *Mandates* 而不是 *Constraints*：不匹配时 `connect` 不是"不参与重载决议"，而是**非良构**——实现通常给出一条 `static_assert` 式的诊断。

!!! note "为什么 transform_sender 用的是 rcvr 的环境"
    domain 的选择依赖"操作在哪里启动"（启动 domain，来自接收器环境的 `get_domain`/调度器）和"前驱在哪里完成"（完成 domain，来自发送器属性）。只有到 connect 时，这两个信息才同时可得。所以算法的定制统一推迟到 connect 时进行，而不是在 `then(...)` 被调用时——那时还不知道它会在哪里运行。

## 不得依赖接收器类型的 noexcept（¶6.3–6.7）

¶6 的后半段是一条 IFNDR {{ifndr}}：若存在一个右值表达式 `rcvr2`，满足

- ¶6.3 `decltype(rcvr2)` 模型化 `receiver`；
- ¶6.4 `noexcept(rcvr2)` 为 true（构造/求值它不抛）；
- ¶6.5 `get_env(rcvr2)` 与 `get_env(rcvr)` 类型相同；
- ¶6.6 `noexcept(execution::connect(sndr, rcvr))` 为 true；
- ¶6.7 `noexcept(execution::connect(sndr, rcvr2))` 良构且为 false，

则程序非良构，不要求诊断。

翻译成人话：**`connect` 是否抛异常，只能取决于接收器的环境类型，不能取决于接收器本身的类型**——对于两个环境类型相同的接收器，不能一个 connect 是 noexcept、另一个不是（"可能抛"一侧以 `noexcept(rcvr2)` 为 true 排除了"仅仅是接收器自身构造会抛"的情况）。

注 1 说明动机：这样在只有环境信息的上下文里——比如 `get_completion_signatures` 内部——就能判断 `connect` 会不会抛。`let_value` 需要这一点：它要在计算签名时决定是否加上 `set_error_t(exception_ptr)`，而那个错误恰恰来自"connect 回调返回的发送器时可能抛异常"（[[exec.let]] 中 `noexcept(connect(declval<sender_type>(), receiver_type{rcvr, env}))`）。签名计算只知道环境，不知道最终的接收器类型，若 noexcept 性随接收器变化，签名就会算错。

## 可等待体当发送器：connect-awaitable（¶3–5）

[[exec.snd.concepts]] 让任何可等待体自动满足 `sender`。连接这样的"发送器"需要把 `co_await x` 变成"完成时调用 `set_value(rcvr, 结果)`"。规范的做法是写一个**协程**，由协程帧充当操作状态。

¶3 *connect-awaitable-promise*：协程的承诺类型。

```cpp
struct connect-awaitable-promise : with-await-transform<connect-awaitable-promise> {
  connect-awaitable-promise(DS&, DR& rcvr) noexcept : rcvr(rcvr) {}
  suspend_always initial_suspend() noexcept { return {}; }
  [[noreturn]] suspend_always final_suspend() noexcept { terminate(); }
  [[noreturn]] void unhandled_exception() noexcept { terminate(); }
  [[noreturn]] void return_void() noexcept { terminate(); }
  coroutine_handle<> unhandled_stopped() noexcept {
    set_stopped(std::move(rcvr));
    return noop_coroutine();
  }
  operation-state-task get_return_object() noexcept { … }
  env_of_t<DR> get_env() const noexcept { return execution::get_env(rcvr); }
private:
  DR& rcvr;
};
```

几个要点：

- 构造函数接受协程的**形参** `(DS&, DR& rcvr)`——[[dcl.fct.def.coroutine]] 规定，若承诺类型有可以用协程形参左值调用的构造函数，就用它构造承诺对象。于是承诺对象直接拿到了协程帧里那份接收器的引用。
- `initial_suspend` 返回 `suspend_always`：协程创建后立刻挂起，**惰性**——直到 `start` 才恢复。
- `final_suspend`、`unhandled_exception`、`return_void` 都 `terminate()`：协程**永远不会**正常走到结尾（见下面的协程体），这些路径不可达。
- `unhandled_stopped`：被 await 的东西若以"stopped"结束（这是 `with_awaitable_senders` 那一套协议，见 [[exec.as.awaitable]]），就对接收器 `set_stopped`。
- `get_env` 转发接收器的环境，于是在这个协程里 `co_await` 的发送器能看到外部环境。

¶4 *operation-state-task*：协程的返回类型，即操作状态。

```cpp
struct operation-state-task {
  using operation_state_concept = operation_state_tag;
  using promise_type = connect-awaitable-promise;
  explicit operation-state-task(coroutine_handle<> h) noexcept : coro(h) {}
  operation-state-task(operation-state-task&&) = delete;
  ~operation-state-task() { coro.destroy(); }
  void start() & noexcept { coro.resume(); }
private:
  coroutine_handle<> coro;
};
```

`start` = 恢复协程；析构 = 销毁协程帧。不可移动。

¶5 协程本体：

```cpp
template<class Fun, class... Ts>
auto suspend-complete(Fun fun, Ts&&... as) noexcept {
  auto fn = [&, fun]() noexcept { fun(std::forward<Ts>(as)...); };
  struct awaiter {
    decltype(fn) fn;
    static constexpr bool await_ready() noexcept { return false; }
    void await_suspend(coroutine_handle<>) noexcept { fn(); }
    [[noreturn]] void await_resume() noexcept { unreachable(); }
  };
  return awaiter{fn};
}

operation-state-task connect-awaitable(DS sndr, DR rcvr) requires receiver-of<DR, Sigs> {
  exception_ptr ep;
  try {
    if constexpr (same_as<V, void>) {
      co_await std::move(sndr);
      co_await suspend-complete(set_value, std::move(rcvr));
    } else {
      co_await suspend-complete(set_value, std::move(rcvr), co_await std::move(sndr));
    }
  } catch(...) {
    ep = current_exception();
  }
  co_await suspend-complete(set_error, std::move(rcvr), std::move(ep));
}
```

其中 `V` 是 *await-result-type*<DS, *connect-awaitable-promise*>，`Sigs` 是 `completion_signatures<SET-VALUE-SIG(V), set_error_t(exception_ptr), set_stopped_t()>`。

*suspend-complete* 是整个设计最精巧的一处：它返回一个 awaiter，`await_ready` 为 false，于是协程**先挂起**，然后在 `await_suspend` 里调用完成函数。为什么要先挂起？因为 [[exec.async.ops#8]] 允许接收器在完成操作中**销毁操作状态**——也就是销毁这个协程帧。只有在协程已经挂起的状态下，销毁协程帧才是合法的（[[coroutine.handle.resumption#4]]：`destroy` 的前置条件是 `*this` 指代一个**已挂起**的协程）。`await_resume` 标记为 `unreachable()`：协程永远不会从这里恢复。

另外注意 lambda 按**引用**捕获 `as`（`[&, fun]`）：`co_await suspend-complete(set_value, std::move(rcvr), co_await std::move(sndr))` 中，内层 `co_await` 的结果是一个临时对象，它活到包含它的完整表达式结束——而外层 `co_await` 挂起时，这个完整表达式还没有结束，所以引用有效。

!!! lawyer "error 完成在 try 块外面"
    `set_error` 那一句写在 `catch` 之后、`try` 块之外。若写在 `catch` 块里，`catch` 块内挂起协程会出问题：[[expr.await#2]] 要求 *await-expression* 只能出现在 *handler* 之外。所以必须先把异常存进 `ep`，离开 `catch` 再 `co_await`。还要注意：如果 `try` 块成功完成，控制流在 `co_await suspend-complete(set_value, ...)` 处挂起并永不恢复，因此永远不会走到最后一行的 `set_error`。

## 思考题

!!! question "1. 一个 std::suspend_always 能被 connect 吗？"
    `std::suspend_always` 是一个可等待体。`sync_wait(std::suspend_always{})` 会发生什么？

<details markdown="1">
<summary>答案</summary>

它满足 `sender`（*enable-sender* 的可等待体分支），签名是 `set_value_t()`、`set_error_t(exception_ptr)`、`set_stopped_t()`。connect 时走 *connect-awaitable*：协程 `co_await suspend_always{}` 挂起，`await_suspend` 什么也不做（`suspend_always::await_suspend` 是空的），于是**没有任何人**会恢复这个协程——操作永远不完成。`sync_wait` 驱动的 `run_loop` 队列为空且未 `finish`，`run` 会一直阻塞。这在类型上完全合法，但违反了 [[exec.async.ops#2]]"启动后终将完成"的要求。教训是：可等待体自动成为发送器，并不意味着每个可等待体都是**有意义**的发送器。
</details>

!!! question "2. connect 的 Mandates 和 sender-to 有什么区别？"
    *sender-to*<Sndr, Rcvr>（[[exec.snd.concepts]]）里已经包含了 `sender_in` 和 *receiver-of*。为什么 `connect` 还要单独写 *Mandates*？

<details markdown="1">
<summary>答案</summary>

*sender-to* 是一个**概念**，用在约束里时不满足就是"不参与重载决议"或 `requires` 为 false，不会报错。`connect` 的 *Mandates* 则保证：只要有人直接写了 `connect(s, r)` 而二者不匹配，程序就**非良构**，实现必须诊断。</details>

## 小结

- `connect(s, r)` = `transform_sender(s, get_env(r)).connect(r)`，不行就把可等待体包成协程。
- *Mandates*：发送器在接收器环境下有签名，接收器能接住所有签名。
- connect 的 noexcept 性只能取决于环境类型（IFNDR）。
- *connect-awaitable*：协程帧即操作状态；完成前先挂起，因为接收器可能在完成时销毁它。
