---
title: 异步作用域
summary: 运行时才知道数量的并发工作怎样纳入结构化并发：工作先通过令牌与一个计数作用域建立关联，close 拒绝新工作，join 等待计数归零；用过而没有 join 的作用域在析构时调用 terminate。
status: draft
covers: *
papers: P2300R10
related: exec.spawn, exec.async.ops, exec.consumers, exec.run.loop, thread.stoptoken, intro.multithread
tags: 标准库, std::execution, 结构化并发, async scope
updated: 2026-10-19
---

!!! tldr
    - 异步作用域用来管理运行时才知道数量的并发工作：每份工作先与作用域建立关联，作用域给关联计数，`join()` 返回的发送器在计数归零时完成。
    - 关联是只能移动的 RAII 句柄，令牌是可复制的轻量句柄；作用域已经关闭时，建立关联会失败，`spawn` 会静默丢弃这份工作。
    - `close()` 拒绝新的关联，`join()` 不拒绝：join 等待期间加入的工作也会被一起等待。
    - 作用域用过之后必须 join 完才能析构，否则调用 `terminate`。
    - `counting_scope` 比 `simple_counting_scope` 多一个 `request_stop()`，可以一次请求取消所有经它启动的工作。

本页的例子用到 C++26 的 `std::execution`。本机 Clang 23 附带的 libc++ 还没有实现这部分库，例子都没有经过编译验证，因此不加判定标记。

## 每来一个连接就启动一个任务

```cpp title="counting-scope.cpp"
namespace ex = std::execution;

void serve(listener& l) {
  ex::counting_scope scope;
  auto pool = ex::get_parallel_scheduler();

  while (auto conn = l.accept()) {
    // spawn 只接受以 set_value_t() 或 set_stopped_t() 完成的发送器，
    // 所以先把错误吞掉（或记日志）
    auto work = ex::starts_on(pool, handle(std::move(*conn)))
              | ex::upon_error([](auto&&) noexcept {});
    ex::spawn(std::move(work), scope.get_token());   // 动态启动
  }
  scope.close();                                   // 不再接受新工作
  std::this_thread::sync_wait(scope.join());       // 等所有 handle 结束
}                                                  // scope 析构：已经 join 完，OK
```

[[exec.async.ops#2]] 的结构化并发规则要求子操作在父操作完成之前完成。`when_all` 这样的适配器满足这个要求，但它的子操作数量在编译期就固定了。服务器每收到一个请求就启动一个处理任务，任务数量在运行时才知道，每个任务的生命期也各不相同。

**异步作用域**（[[g:async-scope]]）解决的就是这个问题。上例中 `scope` 记录有多少份工作还没结束；`close()` 之后不再接受新工作；`join()` 返回的发送器在所有工作都结束时完成。`serve` 返回时，它启动过的每个 `handle` 都已经结束，不会有任务在 `serve` 的局部变量销毁之后还在运行。

作用域本身不启动任何工作，启动由 `spawn`、`spawn_future`、`associate` 负责（[[exec.spawn]]）。早期的 P2300 用 `start_detached` 和 `ensure_started` 启动无人等待的工作，当前草案已经没有这两个算法。

## 关联和令牌 [exec.scope.concepts]

### scope_association：一份计数的所有权（¶1–2）

```cpp
template<class Assoc>
  concept scope_association =
    movable<Assoc> &&
    is_nothrow_move_constructible_v<Assoc> &&
    is_nothrow_move_assignable_v<Assoc> &&
    default_initializable<Assoc> &&
    requires(const Assoc assoc) {
      { static_cast<bool>(assoc) } noexcept;
      { assoc.try_associate() } -> same_as<Assoc>;
    };
```

¶1 `Assoc` 类型的对象拥有与某个异步作用域的一个**关联**（association）时，称它是 **engaged** 的，那个作用域叫它的关联作用域。

¶2 语义要求说明它是一个只能移动的 RAII 句柄，类似 `unique_ptr`，只是它拥有的是作用域计数中的一份：

- ¶2.1 默认构造的对象不是 engaged 的；
- ¶2.2 `bool(assoc)` 为 true 当且仅当它是 engaged 的；
- ¶2.3 两个不同的对象不会拥有同一个关联；
- ¶2.4 对象析构时释放它拥有的关联；
- ¶2.5、¶2.6 被移动之后源对象不再 engaged；移动赋值先释放目标原有的关联；
- ¶2.7 engaged 的对象调用 `try_associate()`，要么在同一作用域中获得一个新关联并返回拥有它的对象，要么失败，返回不 engaged 的对象；
- ¶2.8 不 engaged 的对象调用 `try_associate()`，总是返回不 engaged 的对象。

### scope_token：建立关联的入口（¶3–5）

```cpp
template<class Token>
  concept scope_token =
    copyable<Token> &&
    requires(const Token token) {
      { token.try_associate() } -> scope_association;
      { token.wrap(declval<test-sender>()) } -> sender_in<test-env>;
    };
```

¶3 **令牌**（[[g:scope-token]]）用来在发送器和异步作用域之间建立关联，每个令牌关联一个作用域。¶4 *test-sender* 和 *test-env* 是满足 `sender_in` 的未指定类型，用来检查 `wrap` 在语法上可用。

¶5 语义要求：

- ¶5.1 复制、移动令牌都不抛异常。令牌是轻量句柄，通常就是一个指向作用域的指针。
- ¶5.2 `token.try_associate()` 要么获得一个新关联并返回 engaged 的对象，要么返回不 engaged 的对象。
- ¶5.3 对任何发送器 `sndr`，`token.wrap(sndr)` 都是合法的发送器，并且在任何环境下与 `sndr` 有相同的完成签名。

`wrap` 让作用域有机会修饰交给它的发送器，但不能改变它可能怎样完成。`simple_counting_scope` 的 `wrap` 原样返回发送器，`counting_scope` 的 `wrap` 把作用域的停止令牌加进去（见下文）。

## 计数作用域的状态 [exec.counting.scopes.general]

¶1 `simple_counting_scope` 和 `counting_scope` 维护关联的计数，并在生命期中经历下面几个状态。设 `tkn` 是 `scope.get_token()` 得到的令牌，`op` 是把 `scope.join()` 连接到某个接收器得到的操作状态：

| 状态 | 进入条件 |
|---|---|
| *unused* | 刚构造 |
| *open* | 在 *unused* 时调用 `tkn.try_associate()` |
| *open-and-joining* | 在 *unused* 或 *open* 时启动 `op` |
| *closed* | 在 *open* 时调用 `scope.close()` |
| *unused-and-closed* | 在 *unused* 时调用 `scope.close()` |
| *closed-and-joining* | 在 *open-and-joining* 时调用 `close()`；或在 *closed*、*unused-and-closed* 时启动 `op` |
| *joined* | 在 *open-and-joining* 或 *closed-and-joining* 时计数降到 0 |

¶2 建议实现把状态和计数存进同一个 `size_t` 成员，这样一次原子操作就能同时更新两者。

¶5 阐述用的类模板 *association-t*<Scope> 模型化 `scope_association`，它只有一个 `Scope*` 成员：指针非空即 engaged，`try_associate()` 转调作用域的 *try-associate*，释放关联时调用作用域的 *disassociate*。

### join 回到启动它的调度器上完成（¶4）

¶4 join 发送器的操作状态在构造时就预先连接好一个操作：`schedule(get_start_scheduler(get_env(rcvr)))`，也就是调度到 join 的接收器所在的启动调度器。启动 join 时有两条完成路径：

- 如果此时计数已经是 0，就在原地调用 `set_value`，同步完成；
- 否则把操作状态登记到作用域上。之后最后一个关联被释放时，作用域调用它的 `complete()`，`complete()` 不直接 `set_value`，而是启动预先连接好的调度操作，回到 join 被启动的调度器上再完成。

第二条路径这样设计，是因为最后一个关联在哪个线程上释放是不确定的，可能是线程池的某个线程。如果直接在那里完成，`join()` 之后的代码就会跑在一个意料之外的线程上。代价是 join 的接收器环境必须能回答 `get_start_scheduler`，否则程序非良构。`sync_wait` 和 `task` 的环境都提供它。

## simple_counting_scope [exec.scope.simple.counting]

```cpp
class simple_counting_scope {
public:
  struct token;
  static constexpr size_t max_associations = implementation-defined;

  simple_counting_scope() noexcept;
  simple_counting_scope(simple_counting_scope&&) = delete;
  ~simple_counting_scope();

  token get_token() noexcept;
  void close() noexcept;
  sender auto join() noexcept;
};
```

[exec.scope.simple.counting.general] ¶1 判断数据竞争时，`get_token`、`close`、`join`、*try-associate*、*disassociate* 和 *start-join-sender* 都表现为原子操作（[[intro.multithread]]），同一个对象上的这些操作呈现单一的全序。所以可以从任意线程并发地 spawn、close 和 join。`max_associations` 是实现定义的最大关联数 {{impl}}。

### 析构前必须 join 完 [exec.simple.counting.ctor]

¶1 构造后计数为 0，状态为 *unused*。

¶2 析构时，如果状态不是 *joined*、*unused*、*unused-and-closed* 之一，调用 `terminate`。

还有工作没结束时析构作用域，那些工作结束时释放关联，就会访问已经销毁的作用域。标准选择 `terminate`，而不是未定义行为或在析构函数里阻塞等待，把忘了 join 变成一个立刻可见的错误。

```cpp title="forgot-join.cpp"
{
  ex::counting_scope scope;
  ex::spawn(work(), scope.get_token());
}   // terminate：状态是 open
```

即使 `work()` 已经结束、计数回到了 0，状态仍然是 *open*。只有启动了 join 并且计数归零，才会进入 *joined*。所以只要 spawn 过，就必须启动并等待一次 `join()`。

### 成员 [exec.simple.counting.mem]

¶1 `get_token()` 返回指向 `this` 的令牌。

¶2 `close()` 把 *unused* 变为 *unused-and-closed*，*open* 变为 *closed*，*open-and-joining* 变为 *closed-and-joining*，其他状态不变。¶3 之后的 *try-associate* 一律失败。条文写的是返回 false，但 *try-associate* 返回的是 *assoc-t*，意思是返回一个不 engaged 的对象。

¶4 `join()` 只返回一个发送器，本身不改变状态。状态在 join 发送器的操作被启动时才改变。

¶5–6 *try-associate*：计数已经等于 `max_associations` 时失败。否则，*unused* 状态下计数加一并转为 *open*；*open* 或 *open-and-joining* 状态下计数加一；其他状态（已关闭或已 joined）失败。成功时返回 engaged 的 *assoc-t*，失败时返回默认构造的 *assoc-t*。

¶7–8 *disassociate*：计数减一。如果减到 0，而且状态是 *open-and-joining* 或 *closed-and-joining*，就转为 *joined*，并对所有登记的 join 操作调用 `complete()`。注 1 提醒，调用 `complete()` 可能导致作用域本身被销毁。

¶9 *start-join-sender*：计数为 0 时转为 *joined* 并返回 true，join 原地完成。否则登记这个 join 操作，返回 false，状态按是否已经关闭转为 *open-and-joining* 或 *closed-and-joining*。

!!! note "join 不等于 close"
    在 *open-and-joining* 状态下 *try-associate* 仍然成功：join 正在等待时，新工作仍可以加入，join 会把它们一起等。这适合处理过程中又派生出子任务的情形。要保证 join 之后不再有新工作，先调用 `close()`。另一方面，*joined* 是终态，进入之后 *try-associate* 一律失败。

### 令牌 [exec.simple.counting.token]

¶1 `token::wrap(snd)` 原样返回 `std::forward<Sender>(snd)`。¶2 `token::try_associate()` 等价于 `scope->try-associate()`。

## counting_scope：增加取消 [exec.scope.counting]

¶1 `counting_scope` 在 `simple_counting_scope` 的基础上增加了取消支持，其余成员的语义相同。它多了一个 `inplace_stop_source` 成员和一个 `request_stop()` 成员函数。

¶3–4 `request_stop()` 等价于对内部的停止源调用 `request_stop()`，并发调用不会引入数据竞争。

¶7 `token::wrap(snd)` 返回 *stop-when*(snd, 作用域停止源的令牌)。被包装的发送器连接之后，它看到的停止令牌是外部令牌和作用域令牌的组合，任何一方请求停止都会生效（*stop-when* 见 [[exec.spawn]]）。于是 `scope.request_stop()` 可以一次性请求取消所有经这个作用域启动的工作。

典型的关停流程：

```cpp title="shutdown.cpp"
scope.close();                                // 1. 不再接受新工作
scope.request_stop();                         // 2. 请已有的工作尽快结束
std::this_thread::sync_wait(scope.join());    // 3. 等它们真的结束
```

## 思考题

!!! question "1. 作用域会在 join 完成的过程中被销毁吗？"
    `sync_wait(scope.join())` 返回后 `scope` 立即析构。最后一个关联是在线程池线程上释放的，这时 *disassociate* 还在调用 `complete()`。它会访问已经销毁的作用域吗？

<details markdown="1">
<summary>答案</summary>

注 1 明确承认调用 `complete()` 可能导致作用域被销毁，所以实现必须保证调用 `complete()` 之后不再访问作用域的成员，例如先把登记列表取到局部变量里。在 `sync_wait` 的情形下，`complete()` 启动的是调度到 `sync_wait` 内部 `run_loop` 的操作，它只是入队；真正的 `set_value` 在 `sync_wait` 的线程上发生，之后 `sync_wait` 返回，作用域析构。这时状态已经是 *joined*，析构合法。只要实现遵守调用 `complete()` 之后不再访问 `this`，就没有问题。
</details>

!!! question "2. try_associate 在什么情况下失败？失败了会怎样？"

<details markdown="1">
<summary>答案</summary>

`simple_counting_scope` 的 *try-associate* 在三种情况下失败：计数已经等于 `max_associations`；作用域已经关闭（*closed*、*unused-and-closed*、*closed-and-joining*）；作用域已经是 *joined*。`spawn` 在关联失败时不启动发送器，直接销毁为它分配的状态（[[exec.spawn]] 中 *spawn-state* 的 *run* 走 `complete()` 分支），工作被静默丢弃，不报错。`associate` 和 `spawn_future` 返回的发送器在关联失败时以 `set_stopped` 完成。
</details>
