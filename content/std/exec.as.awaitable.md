---
title: 发送器与协程
summary: 发送器与协程之间的两座桥：可等待体自动被当作发送器；as_awaitable 把发送器变成可以 co_await 的对象，with_awaitable_senders 让一个协程类型能直接 co_await 发送器。
status: draft
covers: exec.coro.util, exec.awaitable, exec.with.awaitable.senders
papers: P2300R10
related: dcl.fct.def.coroutine, expr.await, support.coroutine, exec.connect, exec.task, exec.queries, exec.snd.concepts
tags: 标准库, std::execution, 协程, co_await
updated: 2026-10-19
---

!!! tldr
    - 能被 `co_await` 的对象自动就是发送器，完成签名固定为 `set_value_t(await 的结果)`、`set_error_t(exception_ptr)`、`set_stopped_t()`。
    - 反过来，`as_awaitable(sndr, promise)` 把一个值完成至多一种的发送器包装成 awaiter：值完成时 `co_await` 返回这个值，错误完成时 `co_await` 抛出异常。
    - 取消完成不恢复协程，而是调用承诺对象的 `unhandled_stopped()`，效果像一个不能被 `catch` 的取消异常沿调用链向上传播。
    - 被 `co_await` 的发送器看到的环境，就是协程承诺对象的 `get_env()`。
    - 承诺类型继承 `with_awaitable_senders<Promise>` 后，协程体里的每个 `co_await x` 都先经过 `as_awaitable`；没有用 `set_continuation` 注册调用者时，取消会导致 `std::terminate`。

本页的例子用到 C++26 的 `std::execution`。本机 Clang 23 附带的 libc++ 还没有实现这部分库，例子没有经过编译验证，因此不加判定标记。阅读本页前，最好先了解协程的**承诺类型**（promise type，[[dcl.fct.def.coroutine]]）和 `co_await` 的求值步骤（[[expr.await]]）。

## 两个方向

协程和[[g:sender|发送器]]描述的是同一件事：等某件事做完再继续。`std::execution` 在两个方向上把它们接了起来：

| 方向 | 机制 | 条款 |
|---|---|---|
| 可等待体当作发送器用 | 发送器概念承认可等待体；`connect` 用一个内部协程包装它 | [exec.awaitable]、[[exec.connect]] |
| 发送器当作可等待体用 | `as_awaitable(sndr, promise)` 返回一个 awaiter；`with_awaitable_senders` 让 `await_transform` 自动调用它 | [exec.as.awaitable]、[exec.with.awaitable.senders] |

[[exec.task]] 中的 `task<T>` 就是建立在这些设施上、可以直接使用的协程类型。

```cpp title="co-await-sender.cpp"
namespace ex = std::execution;

ex::task<int> f(ex::scheduler auto sch) {
  co_await ex::schedule(sch);                       // 转到 sch 上继续执行
  int v = co_await (ex::just(20) | ex::then([](int x) { return x + 1; }));
  co_return v;                                      // 21
}
```

## 可等待体就是发送器（[exec.awaitable]）

¶1 在 [exec] 中，[[g:exec-awaitable|可等待体]]（awaitable）指在给定上下文中可以作为 `co_await` 操作数的表达式。发送器概念把可等待体也当作发送器。

### 怎样判断一个类型可以被 co_await（¶2–4）

`co_await c` 并不是直接对 `c` 调用 `await_ready` 等函数。[[expr.await]] 规定要先经过一系列变换：如果承诺类型有 `await_transform`，先调用它；再按重载决议找 `operator co_await`；最后得到一个对象，叫 **awaiter**，`await_ready`、`await_suspend`、`await_resume` 都是对它调用的。

¶2 标准把这一串变换记作 *GET-AWAITER*(c, p)，`p` 是协程的承诺对象。*GET-AWAITER*(c) 表示在一个没有 `await_transform` 的空承诺类型下做同样的变换。

¶3 在此基础上定义两个阐述用的概念：

```cpp
template<class A, class... Promise>
concept is-awaiter = requires (A& a, coroutine_handle<Promise...> h) {
  a.await_ready() ? 1 : 0;
  { a.await_suspend(h) } -> await-suspend-result;   // void、bool 或 coroutine_handle
  a.await_resume();
};

template<class C, class... Promise>
concept is-awaitable = requires (C (*fc)() noexcept, Promise&... p) {
  { GET-AWAITER(fc(), p...) } -> is-awaiter<Promise...>;
};
```

*is-awaitable* 用一个返回 `C` 的函数指针来构造一个 `C` 类型的表达式 `fc()`，这样能如实保留 `C` 的值类别。¶4 *await-result-type*<C, Promise> 是 `co_await c` 的结果类型，即 awaiter 的 `await_resume()` 的返回类型。

### 只用于类型计算的承诺类型（¶5–6）

¶5 *with-await-transform*<Derived> 是一个基类，提供 `await_transform`：如果被等待的对象有成员 `as_awaitable(p)`，就调用它；否则原样返回。这给了对象一个自定义被 `co_await` 方式的钩子。

¶6 *env-promise*<Env> 是一个只用于类型计算的承诺类型，它的成员不必定义（注 2）。它继承 *with-await-transform*，`get_env()` 返回 `const Env&`。发送器概念用它判断一个类型是不是可等待体；[[exec.getcomplsigs]] 用它计算可等待体在环境 `Env` 下的结果类型。

可等待体作为发送器时，完成签名是固定的：

```cpp
completion_signatures<SET-VALUE-SIG(await-result-type<S, env-promise<Env>>),
                      set_error_t(exception_ptr),
                      set_stopped_t()>
```

`co_await` 的结果对应值完成，`co_await` 抛出的异常对应错误完成，取消完成来自 `connect` 内部协程的承诺类型的 `unhandled_stopped`（[[exec.connect]]）。

## 把发送器变成 awaiter（[exec.as.awaitable]）

### 哪些发送器能被 co_await（¶1）

¶1 *awaitable-sender* 概念要求三件事：

- 发送器是 *single-sender*：值完成至多一种，`co_await` 只能产生一个结果。只有一个值时结果就是那个值的类型（decay 后），没有值完成或者值是空的时结果是 `void`，一种完成带多个值时结果是 `tuple`（[[execution.syn]]）；
- 发送器能连接到下文的 *awaitable-receiver*；
- 承诺类型有 `unhandled_stopped()`，返回值能转换为 `coroutine_handle<>`，用来处理取消完成。

### sender-awaitable：awaiter 里装着操作状态（¶2–6）

¶2 通用的包装类型是 *sender-awaitable*：

```cpp
template<class Sndr, class Promise>
class sender-awaitable {
  using result-type = /* 值类型；void 时用一个空的 unit 代替 */;
  variant<monostate, result-type, exception_ptr> result{};
  connect_result_t<Sndr, awaitable-receiver> state;   // 操作状态

public:
  sender-awaitable(Sndr&& sndr, Promise& p);
  static constexpr bool await_ready() noexcept { return false; }
  void await_suspend(coroutine_handle<Promise>) noexcept { start(state); }
  value-type await_resume();
};
```

awaiter 自己就容纳了[[g:operation-state|操作状态]]和结果存储。awaiter 是 `co_await` 求值过程中的临时对象，存放在协程帧里，在协程挂起期间一直存在。操作状态在异步操作期间必须保持有效、不能移动（[[exec.async.ops#7]]），这里自然满足，而且除了协程帧本身之外不需要任何额外的堆分配。

¶5 构造 awaiter 时就 connect 发送器，接收器里记着结果存储的地址和当前协程的句柄。¶2 `await_suspend` 在协程已经挂起之后才 `start` 操作。

### 三种完成怎样回到协程（¶4、¶6）

¶4 *awaitable-receiver* 对三种完成的处理不同：

- ¶4.1 值完成：把值存进 `result`（构造抛出异常时改存 `current_exception()`），然后恢复协程。
- ¶4.2 错误完成：把错误转成 `exception_ptr`（规则见 [[exec.general#8]]）存进 `result`，然后恢复协程。
- ¶4.3 取消完成：不恢复当前协程，而是调用承诺对象的 `unhandled_stopped()`，恢复它返回的那个协程句柄。

¶6 协程恢复后，`await_resume()` 检查 `result`：存的是异常就重新抛出，否则返回值。所以错误完成在协程里表现为 `co_await` 抛出异常。

¶4 中的 `resume()` 都包在一个 noexcept lambda 里（*MAKE-NOEXCEPT*），恢复的过程中如果有异常逃出，直接 `terminate`。

¶4.4 *awaitable-receiver* 的环境把所有[[g:forwarding-query|转发查询]]交给承诺对象的 `get_env()` 回答。被 `co_await` 的发送器看到的环境，就是这个协程的环境。

### 取消不是异常

¶4.3 是这套设计里最特别的一点。发送器以取消完成时，被挂起的协程永远不会被恢复。控制交给承诺类型的 `unhandled_stopped()`，由它决定接下来恢复谁。通常它会调用调用者协程的 `unhandled_stopped()`，一层层向上，直到某个能处理取消的地方，例如 `connect` 内部的协程对接收器调用 `set_stopped`。

[exec.with.awaitable.senders] ¶1 对此的描述是：如同从 `co_await` 表达式抛出了一个不能被捕获的 stopped 异常。沿途的协程帧不会被恢复，由各自的拥有者销毁。

### as_awaitable 的选择顺序（¶7–8）

¶7 `as_awaitable(expr, p)` 要求 `p` 是左值，否则非良构。它依次尝试：

| 条件 | 结果 |
|---|---|
| ¶7.1 `expr.as_awaitable(p)` 良构 | 对象自定义的结果（必须是可等待体） |
| ¶7.2 `expr` 是单值发送器，变换后的发送器有 `.as_awaitable(p)` | 变换后的发送器自定义的结果 |
| ¶7.3 `expr` 本身已经是这个承诺类型下的 awaiter | `expr` 原样返回 |
| ¶7.4 `expr` 是单值发送器 | *sender-awaitable*，通用路径 |
| ¶7.5 都不是 | `expr` 原样返回，交给 `co_await` 的普通规则 |

¶7.2 和 ¶7.4 中的变换是：先按协程环境的 domain 变换发送器（`transform_sender`，见 [[exec.snd.transform]]），再经过 ¶8 的 *adapt-for-await-completion*：如果发送器的环境提供了 `get_await_completion_adaptor`，就用它再包装一次，否则不变。

¶7.3 排在 ¶7.4 前面。一个类型如果既是 awaiter 又是发送器，`as_awaitable` 优先把它当 awaiter 用，保留它原生的协程语义，不绕道 connect。

## with_awaitable_senders（[exec.with.awaitable.senders]）

¶1 `with_awaitable_senders<Promise>` 用作协程承诺类型的基类，使发送器在这个协程里可以被 `co_await`；它还提供 `unhandled_stopped` 的默认实现。

```cpp title="with-awaitable-senders.cpp"
namespace ex = std::execution;

struct my_task {
  struct promise_type : ex::with_awaitable_senders<promise_type> {
    my_task get_return_object();
    std::suspend_always initial_suspend() noexcept { return {}; }
    auto final_suspend() noexcept;   // 返回一个恢复 continuation() 的 awaiter
    void return_value(int);
    void unhandled_exception();
  };
  // ...
};
```

`Promise` 模板参数是派生的承诺类型本身（CRTP），因为 `await_transform` 要把 `*this` 转成 `Promise&` 交给 `as_awaitable`。它的成员是：

- ¶3 `await_transform(value)` 返回 `as_awaitable(std::forward<Value>(value), static_cast<Promise&>(*this))`。协程体里的每个 `co_await x` 都先经过这一步。
- ¶2 `set_continuation(h)` 记住调用者协程 `h`。如果调用者的承诺类型有 `unhandled_stopped()`，就记下一个函数，它从地址还原出 `coroutine_handle<OtherPromise>`，再调用调用者的 `unhandled_stopped()`，这样取消就传播给了调用者。否则记下默认处理函数，它调用 `terminate()`。
- `unhandled_stopped()` 调用上面记下的函数。`continuation()` 返回调用者的句柄。

`set_continuation` 用一个函数指针加 `void*` 保存调用者，这是一种手写的类型擦除：`with_awaitable_senders<Promise>` 不需要知道调用者的承诺类型。

### 没有注册调用者时被取消

处理函数的初值就是调用 `terminate()` 的默认函数。如果协程的拥有者没有用 `set_continuation` 注册一个能处理取消的调用者，那么在这个协程里被 `co_await` 的任何发送器以取消完成，都会导致 `std::terminate`。自己写协程类型时，必须在启动协程之前设置好 continuation。

## 思考题

!!! question "1. co_await 一个有两种值签名的发送器"
    `s` 的签名是 `set_value_t(int)` 和 `set_value_t(std::string)`。在继承 `with_awaitable_senders` 的协程里 `co_await s` 会怎样？

<details markdown="1">
<summary>答案</summary>

`await_transform` 调用 `as_awaitable(s, p)`。¶7.2 和 ¶7.4 都要求 *single-sender-value-type* 良构，有两种值签名时它非良构（[[execution.syn]]），所以这两条都不适用。`s` 也不是 awaiter（¶7.3）。于是走 ¶7.5，原样返回 `s`。

接着 `co_await` 在 `s` 上找 `operator co_await` 或 awaiter 成员，找不到，程序非良构。解决办法是先合并签名：`co_await into_variant(s)` 得到 `variant<tuple<int>, tuple<std::string>>`。
</details>

!!! question "2. 为什么先把结果存进 variant？"
    *awaitable-receiver* 的 `set_value` 为什么先把值存进 `result`，再恢复协程，而不是直接把值交给协程？

<details markdown="1">
<summary>答案</summary>

协程恢复后只能通过 `await_resume()` 取得 `co_await` 的结果，这是 [[expr.await]] 固定的协议，没有别的通道。所以值必须先存放在 `await_resume` 能读到的地方，也就是 awaiter 自己的成员 `result`。

另外，`set_value` 的实参可能引用发送器操作状态内部的数据。协程恢复后会继续运行，可能很快结束这个 `co_await` 表达式、销毁 awaiter 以及其中的操作状态。先把值复制进 `result`，`await_resume` 读到的才是有效的数据。
</details>

## 小结

| 问题 | 答案 |
|---|---|
| 可等待体作为发送器的签名 | `set_value_t(await 结果)`、`set_error_t(exception_ptr)`、`set_stopped_t()` |
| 哪些发送器能被 `co_await` | 值完成至多一种，且承诺类型有 `unhandled_stopped()` |
| 值完成 | `await_resume()` 返回这个值 |
| 错误完成 | `await_resume()` 重新抛出异常 |
| 取消完成 | 不恢复协程，调用 `promise.unhandled_stopped()` |
| 发送器看到的环境 | 承诺对象的 `get_env()` |
| `with_awaitable_senders` | `await_transform` 统一调用 `as_awaitable`；未注册调用者时取消导致 `terminate` |
