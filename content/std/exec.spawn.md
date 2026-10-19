---
title: spawn、spawn_future 与 associate
summary: 把发送器交给异步作用域管理：spawn 立即启动并丢弃结果，spawn_future 立即启动并返回一个可以取回结果的发送器，associate 只建立关联、不启动；关联失败时工作不会运行。
status: draft
covers: exec.associate, exec.stop.when, exec.spawn.future
papers: P2300R10
related: exec.scope, exec.consumers, exec.async.ops, exec.adapt, thread.stoptoken, allocator.requirements
tags: 标准库, std::execution, 结构化并发, async scope, spawn
updated: 2026-10-19
---

!!! tldr
    - `spawn(sndr, token)` 立即启动 `sndr`，不返回结果。`sndr` 只能以 `set_value()` 或 `set_stopped()` 完成，带值或可能出错的发送器要先显式处理。
    - `spawn_future(sndr, token)` 立即启动 `sndr`，返回一个发送器，以后可以从它取回结果。丢弃这个发送器会请求停止那份工作，而不是阻塞等待。
    - `associate(sndr, token)` 不启动任何东西，只让作用域知道这个发送器的存在；关联失败时，它产生的操作以 `set_stopped` 完成。
    - 作用域关闭后关联会失败，这时 `spawn` 静默放弃工作，`spawn_future` 的结果是取消完成。
    - 状态对象先销毁、关联后释放，所以作用域的 `join` 完成时，被启动的工作连同它的状态都已经不存在了。

本页的例子用到 C++26 的 `std::execution` 发送器。本机 Clang 23 附带的 libc++ 还没有实现这部分库，例子都没有经过编译验证，因此不加判定标记。

## 交给作用域的三种方式

[[g:async-scope|异步作用域]]（async scope，[[exec.scope]]）记录有多少工作与它关联，并提供 `join()`，等这些工作全部结束。工作通过作用域的**令牌**（scope token）与它关联：`token.try_associate()` 尝试把计数加一，成功时返回一个关联对象，这个对象析构时计数减一；作用域关闭后，`try_associate()` 返回一个表示失败的空关联。

本页的三个算法负责把发送器交给作用域：

| 算法 | 返回 | 何时启动 | 结果 | 关联失败时 |
|---|---|---|---|---|
| `spawn(sndr, token[, env])` | `void` | 立即 | 丢弃 | 不启动，静默放弃 |
| `spawn_future(sndr, token[, env])` | 发送器 | 立即 | 从返回的发送器取回 | 返回的发送器以取消完成 |
| `associate(sndr, token)` | 发送器 | 随返回的发送器一起启动 | 原样转发 | 以取消完成 |

`spawn` 和 `spawn_future` 是急切的（eager）：调用时就开始工作。它们取代了早期 P2300 草案中的 `start_detached` 和 `ensure_started`，区别在于必须有一个作用域为被启动的工作负责，工作不会脱离所有人的视线。

```cpp title="spawn.cpp"
namespace ex = std::execution;

ex::counting_scope scope;
auto pool = ex::get_parallel_scheduler();

ex::spawn(ex::starts_on(pool, ex::just() | ex::then([] { do_work(); }))
            | ex::upon_error([](std::exception_ptr) noexcept { /* 记日志 */ }),
          scope.get_token());
// ...
std::this_thread::sync_wait(scope.join());   // 等所有被 spawn 的工作结束
```

## spawn（[exec.spawn]）

### 只接受不带值、不会出错的发送器（¶2–4）

¶1 `spawn` 尝试把发送器与令牌所属的作用域关联，成功就立即启动它。¶2 `sndr` 不是发送器、令牌不满足 `scope_token`，或者 `env` 不是可查询对象时，`spawn(sndr, token, env)` 非良构。

¶4 `spawn` 用来接收完成的接收器只有两个完成函数：

```cpp
struct spawn-receiver {
  using receiver_concept = receiver_tag;
  spawn-state-base* state;
  void set_value() && noexcept   { state->complete(); }
  void set_stopped() && noexcept { state->complete(); }
};
```

所以被 spawn 的发送器只能以 `set_value_t()` 或 `set_stopped_t()` 完成。带值的完成或任何错误完成都会让 connect 的 *Mandates*（接收器必须能接受发送器的所有完成）不成立，程序非良构。

这样设计是因为 spawn 之后没有人接收结果，错误也无处报告。与其让错误被悄悄吞掉，标准要求调用者显式处理：用 `upon_error(...)` 记录错误，用 `then([](auto&&...) {})` 丢弃值。

<div class="compare" markdown="1">

```cpp
ex::spawn(ex::just(42), tok);
// error：spawn-receiver
// 没有 set_value(int)
```

```cpp
ex::spawn(ex::just(42)
            | ex::then([](int) {}),
          tok);
// OK：值已被显式丢弃
```

</div>

### 状态对象与销毁顺序（¶5–8）

¶5 `spawn` 在堆上（通过分配器）创建一个 *spawn-state*，里面有分配器、操作状态 `op` 和关联 `assoc`：

- ¶6 构造时先 connect 得到 `op`，再调用 `token.try_associate()` 得到 `assoc`。
- ¶7 `run()`：关联成功就 `start(op)`，失败就直接调用 `complete()`。
- ¶8 `complete()`：先把 `assoc` 移到一个局部变量，再用分配器销毁并释放整个状态对象；函数返回时局部的 `assoc` 析构，释放关联。

¶8 的顺序很重要。如果先释放关联，计数可能归零，`join()` 随之完成，等待者接着就可能销毁作用域和程序里的其他对象，而这时 *spawn-state* 还没销毁完，操作状态的析构函数可能访问已经不存在的东西。按 ¶8 的顺序，作用域的计数覆盖了状态对象的整个生存期，而不只是工作运行的那段时间。

### 分配器与环境（¶9–11）

¶9 设 `new_sender` 为 `token.wrap(sndr)`，`spawn` 按下面的顺序选择分配器 `alloc` 和环境 `senv`：

- ¶9.1 `env` 提供了分配器（`get_allocator(env)` 良构）：用它，`senv` 就是 `env`；
- ¶9.2 否则，如果发送器的属性提供了分配器：用它，并把它加进环境，`senv` 是 *JOIN-ENV*(prop(get_allocator, alloc), env)；
- ¶9.3 否则用 `allocator<void>()`，`senv` 就是 `env`。

¶10 `spawn(sndr, token, env)` 的类型是 `void`。它用 `alloc` 分配并构造 *spawn-state*，被 connect 的发送器是 `write_env(token.wrap(sndr), senv)`，然后调用 `run()`。构造过程中抛出异常时，已构造的对象被销毁，已分配的内存被释放。

`token.wrap` 让作用域修饰发送器，例如 `counting_scope` 用它织入自己的停止令牌。`write_env(..., senv)` 把调用者提供的环境交给发送器。

被 spawn 的工作没有可以继承环境的上层接收器，它看到的环境只有 `senv`。¶11 `spawn(sndr, token)` 等价于 `spawn(sndr, token, env<>())`，这时环境几乎是空的：没有调度器，除了作用域的 `wrap` 织入的之外也没有停止令牌。在协程或发送器链里 spawn 时，如果希望子工作使用某个调度器，要通过第三个实参传入，例如 `spawn(work, tok, env{prop(get_scheduler, sch)})`。

## spawn_future（[exec.spawn.future]）

```cpp title="spawn-future.cpp"
namespace ex = std::execution;

ex::counting_scope scope;
auto fut = ex::spawn_future(ex::starts_on(pool, compute()),
                            scope.get_token());   // 已经开始计算
do_something_else();
auto [v] = std::this_thread::sync_wait(std::move(fut)).value();   // 取回结果
std::this_thread::sync_wait(scope.join());
```

¶1 `spawn_future` 尝试关联，成功就立即启动输入发送器，然后返回一个发送器。返回的发送器被 connect 并启动后，以那个已经启动的发送器的结果完成；如果输入发送器根本没有启动（关联失败），就以 `set_stopped` 完成。¶2 合法性要求与 `spawn` 相同。

### 保存结果（¶4–8）

结果要从工作完成的那一刻保存到有人来取的那一刻，而这两件事谁先谁后是不确定的。所以 `spawn_future` 同样在堆上创建一个状态对象 *spawn-future-state*。

¶4–5 状态里的 `result` 是一个 `variant`，能存放输入发送器的任何一种完成：例如 `tuple<set_value_t, int>`、`tuple<set_stopped_t>`。如果有结果在 decay-copy 时可能抛出异常，它还能存放 `tuple<set_error_t, exception_ptr>`。

¶6 与 `spawn` 不同，*spawn-future-receiver* 接受所有种类的完成，因为结果有人要。它把结果 decay-copy 进 `result`，复制抛出异常时改存 `exception_ptr`，然后调用 `complete()`。

¶7–8 状态里还有一个自己的停止源 `ssource`。真正被 connect 的发送器是 `write_env(stop-when(sndr, ssource.get_token()), env)`，其中 *stop-when* 把 `ssource` 的令牌合并进发送器（见本页最后一节）。构造时先 connect，再 `try_associate()`；成功就启动，失败就直接以 `set_stopped` 完成，把取消结果存进 `result`。

### 工作与取结果的一方如何汇合（¶9–14）

¶9 状态对象上有四个操作。判断数据竞争时它们表现为原子操作，在同一个对象上有唯一的全序：

| 操作 | 何时发生 | 含义 |
|---|---|---|
| *complete* | 输入发送器完成 | 结果已经就绪 |
| *consume*(rcvr) | 返回的发送器被启动 | 有人来取结果，登记接收器 `rcvr` |
| *try-set-stopped* | 取结果的一方收到停止请求 | 取消等待 |
| *abandon* | 返回的发送器被丢弃，从未启动 | 没人要结果了 |

它们按发生的先后决定结果交给谁、状态由谁销毁：

- ¶10 *complete* 先于其他三者发生时什么也不做，等人来取。如果已经有接收器登记、并且没有被取消，就把结果交给它。否则（等待已被取消，或结果已被放弃）销毁状态。
- ¶11 *consume* 先于 *complete* 发生、并且没有被取消时，登记接收器，等结果。如果等待已被取消而结果还没到，以 `set_stopped` 完成接收器。否则结果已经在了，立即把它交给接收器，然后销毁状态。
- ¶12 *try-set-stopped* 在已有接收器登记而结果未到时，以 `set_stopped` 完成那个接收器，然后销毁状态；否则什么也不做。
- ¶13 *abandon* 先于 *complete* 发生时，调用 `ssource.request_stop()` 请求停止仍在运行的工作，状态留给之后的 *complete* 销毁；否则结果已在、没人要，直接销毁状态。
- ¶14 *destroy* 与 `spawn` 一样，先销毁并释放状态对象，再释放关联。

### 丢弃即取消（¶15–21）

¶20 `spawn_future` 返回的发送器持有一个指向状态的 `unique_ptr`，它的删除器调用 *abandon*。所以丢弃 `spawn_future` 返回的发送器，就是请求取消那份工作。

这与 `std::future`（`std::async` 返回的那种）析构时阻塞等待完全不同：既不阻塞，也不泄漏。工作被请求停止，最终完成时由 *complete* 清理状态，作用域的 `join()` 会一直等到这一刻。

¶15–18 返回的发送器被 connect 后得到一个 *future-operation*。启动时，它先在外部接收器的停止令牌上注册一个回调，再把状态的所有权交出去并调用 *consume*。回调调用 *try-cancel*，也就是 `ssource.request_stop()` 加上 *try-set-stopped*。所以外部接收器被请求停止时，正在运行的工作和等待本身会一起被取消。

¶19 分配器和环境的选择方式与 `spawn` 的 ¶9 相同。¶21 `spawn_future(sndr, token)` 等价于 `spawn_future(sndr, token, env<>())`。

## associate（[exec.associate]）

¶1 `associate` 尝试把发送器与作用域关联，让作用域能跟踪由这个发送器创建的所有异步操作的生存期。

与 `spawn` 不同，它不启动任何东西，而是返回一个惰性的发送器。适用的场景是：调用者会自己启动这个发送器（例如交给一个不了解作用域的第三方组件），但希望作用域知道它的存在，在 `join()` 时等它结束。

¶2 关联在调用 `associate` 时就尝试建立，由返回的发送器持有，直到它产生的操作完成。它的数据 *associate-data* 的构造过程是：先 `sndr = token.wrap(s)`，再 `try_associate()`；关联失败时，立即销毁刚包装好的发送器，只在成功时保留它。

¶4–8 *associate-data* 的复制和移动有自己的规则：

- ¶4–5 复制时（要求包装后的发送器可复制），对源对象的关联再调用一次 `try_associate()`，成功才复制发送器。所以复制一个 `associate` 发送器会再占用一份作用域计数。
- ¶6、¶8 移动时，关联和发送器一起转移给新对象。
- ¶7 析构时，如果持有关联，就销毁发送器，关联随成员一起析构而释放。

¶9 `sndr` 不是发送器或令牌不满足 `scope_token` 时，`associate(sndr, token)` 非良构；否则结果是以 *associate-data* 为数据的发送器。

¶11 connect 时，如果持有关联，就把包装后的发送器 connect 到接收器；否则只记下接收器的地址。¶13 启动时，有关联就启动内部操作，否则直接 `set_stopped`。

¶14 求值 `associate(sndr, token)` 可能产生可以通过作用域观察到的副作用，即计数加一。[[exec.adapt.general#3]] 规定适配器在 connect 并 start 之前不得产生可观察的效果，这一段是明确的例外。

## stop-when：合并两个停止令牌（[exec.stop.when]）

¶1 *stop-when*(sndr, token) 是标准内部使用的适配器，不对用户公开。它把一个额外的停止令牌 `token` 合并进发送器：connect 到接收器 `r` 之后，操作既响应 `token` 的停止请求，也响应 `r` 的环境里的停止令牌。

`counting_scope` 的 `wrap` 和 `spawn_future` 都用到它：被管理的工作既要响应调用者的取消，也要响应作用域或 future 自己发出的取消。

¶2 它按令牌的情况分别处理：

- ¶2.1 `sndr` 不是发送器或 `token` 不是停止令牌时，非良构；
- ¶2.2 `token` 永远不会被请求停止（满足 `unstoppable_token`）时，结果就是 `sndr` 本身，没有合并的必要；
- ¶2.3.1 接收器的令牌永远不会被请求停止时，直接用 `write_env` 把 `token` 作为停止令牌交给 `sndr`；
- ¶2.3.2 否则交给 `sndr` 一个合成的令牌：只要两个令牌之一被请求停止，它就报告已请求停止；在它上面注册的回调，在任一令牌触发时被调用，最多调用一次（注 1）。

## 思考题

!!! question "1. 关联失败时的 spawn"
    作用域已经关闭，调用 `spawn(sndr, scope.get_token())`。会分配内存吗？`sndr` 会被 connect 吗？

<details markdown="1">
<summary>答案</summary>

都会。¶10 先用分配器分配并构造 *spawn-state*，¶6 的构造过程先 connect（初始化 `op`），再调用 `try_associate()`，这时失败。随后 `run()` 发现没有关联，调用 `complete()` 销毁并释放状态。

所以即使关联失败，`sndr` 也被 connect 过，只是从未启动；操作状态被构造又被销毁。
</details>

!!! question "2. 丢弃一个永不停止的 spawn_future"
    `auto f = spawn_future(never_ending_work(), tok);` 然后丢弃 `f`，会怎样？

<details markdown="1">
<summary>答案</summary>

`f` 析构时删除器调用 *abandon*。工作还没完成，于是调用 `ssource.request_stop()`。如果工作不理会停止请求、永远不完成，状态就永远不会被销毁，关联永远不会释放，`scope.join()` 永远不会完成。

这不是 `spawn_future` 的缺陷。每个被启动的异步操作最终都必须完成（[[exec.async.ops#2]]），作用域只是把谁来等待这件事明确了出来。
</details>

## 小结

| 算法 | 启动 | 结果 | 关联失败 | 要点 |
|---|---|---|---|---|
| `spawn` | 立即 | 丢弃 | 静默放弃 | 只接受 `set_value_t()`、`set_stopped_t()` |
| `spawn_future` | 立即 | 返回的发送器 | 以取消完成 | 四个操作汇合；丢弃返回值即请求停止 |
| `associate` | 随返回的发送器 | 原样转发 | 以取消完成 | 调用时就关联；复制即再关联一次 |

三者都先销毁状态、后释放关联；被启动工作的环境只来自显式传入的 `env`，加上作用域的 `wrap` 和分配器。

<details class="fine" markdown="1"><summary>其余条文</summary>

[exec.spawn] ¶3 *spawn-state-base* 只有一个纯虚函数 `complete()`，让接收器不必知道状态对象的具体类型。

[exec.spawn.future] ¶3 *try-cancelable* 同样是一个只有纯虚函数 *try-cancel* 的基类，供 *future-operation* 的停止回调使用。¶16–18 *impls-for*<spawn_future_t> 定制了 *start*（调用 *future-operation*::*run*）和 *get-state*（构造 *future-operation*）。¶14 的阐述代码移动的是 `this->associated`，而 ¶8 中这个成员叫 `assoc`，应当是草案的笔误。

[exec.associate] ¶10 *check-types* 计算包装后发送器的完成签名。¶12 *get-state* 的 noexcept 取决于数据能否无异常地移动或复制，以及 connect 是否会抛出异常。

</details>
