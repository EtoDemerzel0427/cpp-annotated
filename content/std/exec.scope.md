---
title: 异步作用域
summary: 结构化地管理"动态数量的并发工作"——scope_association（RAII 的关联）与 scope_token（try_associate + wrap）两个概念；simple_counting_scope 与 counting_scope 计数关联、close 拒绝新关联、join 等待计数归零，状态机 unused/open/closed/joining/joined；析构时未 join 即 terminate；counting_scope 还能 request_stop
status: done
covers: *
papers: P2300R10
related: exec.spawn, exec.async.ops, exec.consumers, exec.run.loop, thread.stoptoken, intro.multithread
tags: 标准库, std::execution, 结构化并发, async scope
updated: 2026-10-18
---

[[exec.async.ops#2]] 的结构化并发规则要求：子操作必须在父操作完成之前完成。`when_all` 这样的适配器满足它，但只能处理**编译期已知数量**的子操作。现实中经常需要"收到一个请求就启动一个处理任务"——任务数在运行时才知道，每个任务的生存期也互不相同。

早期 P2300 用 `start_detached`、`ensure_started` 解决这个问题，代价是被启动的工作**无人负责**：没有任何东西等待它结束，它可能比它引用的对象活得更久。当前草案中这两个算法已不存在，取而代之的是 **async scope**（[[g:async-scope]]）：

- 一个 scope 对象（如 `counting_scope`）**计数**与它关联的工作；
- 启动工作前，先通过 scope 的**令牌**（token）尝试建立**关联**（association）；scope 已关闭则失败；
- 工作结束时释放关联，计数减一；
- `scope.join()` 返回一个发送器，在计数归零时完成——这就是"等待所有动态启动的工作结束"。

scope 本身不启动任何工作；启动由 `spawn`、`spawn_future`、`associate` 完成（[[exec.spawn]]）。

```cpp title="counting-scope.cpp"
namespace ex = std::execution;

void serve(listener& l) {
  ex::counting_scope scope;
  auto pool = ex::get_parallel_scheduler();

  while (auto conn = l.accept()) {
    // handle(...) 以 set_value_t() 完成；spawn 不接受 error 完成，所以先把错误吞掉（或记日志）
    auto work = ex::starts_on(pool, handle(std::move(*conn)))
              | ex::upon_error([](auto&&) noexcept {});
    ex::spawn(std::move(work), scope.get_token());   // 动态启动
  }
  scope.close();                                                 // 不再接受新工作
  std::this_thread::sync_wait(scope.join());                     // 等所有 handle 结束
}                                                                // scope 析构：已 joined，OK
```

## 两个概念（[exec.scope.concepts]）

### scope_association（¶1–2）

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

¶1 `Assoc` 类型的对象当且仅当它**拥有**与某个 async scope 的一个关联时称为 **engaged**；那个 scope 称为它的关联 scope。

¶2 语义要求——它就是一个**只能移动的 RAII 句柄**（类似 `unique_ptr`，拥有的是"一份计数"）：

- ¶2.1 默认构造的对象不 engaged；
- ¶2.2 `bool(assoc)` 为 true 当且仅当 engaged；
- ¶2.3 两个不同对象不会拥有同一个关联；
- ¶2.4 析构时释放所拥有的关联（若有）；
- ¶2.5 被移动构造后，源对象不 engaged；
- ¶2.6 `a1 = std::move(a2)` 后，`a1` 原有的关联被释放，`a2` 不 engaged；
- ¶2.7 engaged 的 `assoc.try_associate()` 要么返回不 engaged 的对象，要么在同一 scope 中获得一个**新**关联并返回拥有它的 engaged 对象——"复制"一份关联（可能失败）；
- ¶2.8 不 engaged 的对象 `try_associate()` 返回不 engaged 的对象。

### scope_token（¶3–5）

```cpp
template<class Token>
  concept scope_token =
    copyable<Token> &&
    requires(const Token token) {
      { token.try_associate() } -> scope_association;
      { token.wrap(declval<test-sender>()) } -> sender_in<test-env>;
    };
```

¶3 令牌是用来在发送器与 async scope 之间建立关联的类型；每个令牌对象关联一个 scope。

¶5 语义要求：

- ¶5.1 复制/移动构造与赋值不抛异常——令牌是轻量句柄（通常就是一个指向 scope 的指针）；
- ¶5.2 `token.try_associate()` 要么返回不 engaged 的对象，要么获得一个新关联并返回 engaged 的对象；
- ¶5.3 对任何发送器 `sndr`，`token.wrap(sndr)` 合法，结果是发送器，并且在任何环境 `E` 下与 `sndr` 有**相同的完成签名**。

`wrap` 让 scope 有机会**修饰**交给它的发送器而不改变其类型层面的行为：`simple_counting_scope` 的 `wrap` 什么也不做；`counting_scope` 的 `wrap` 把 scope 的停止令牌织进去（见下）。

¶4 *test-sender* 与 *test-env* 是满足 `sender_in<test-sender, test-env>` 的未指定类型——用一个代表性的发送器检查 `wrap` 在语法上可用。

## 计数作用域的状态机（[exec.counting.scopes.general]）

¶1 `simple_counting_scope` 和 `counting_scope` 维护关联的计数。设 `scope` 是其中之一的对象，`tkn = scope.get_token()`，`jsndr = scope.join()`，`op` 是 `jsndr` connect 得到的操作状态。scope 在生存期中经历以下状态：

| 状态 | 进入条件 |
|---|---|
| *unused* | 新构造 |
| *open* | 在 *unused* 时调用 `tkn.try_associate()` |
| *open-and-joining* | 在 *unused* 或 *open* 时启动 `op` |
| *closed* | 在 *open* 时调用 `scope.close()` |
| *unused-and-closed* | 在 *unused* 时调用 `scope.close()` |
| *closed-and-joining* | 在 *open-and-joining* 时 `close()`；或在 *closed*、*unused-and-closed* 时启动 `op` |
| *joined* | 在 *open-and-joining* 或 *closed-and-joining* 时计数降到 0 |

¶2 *Recommended practice*：把状态和计数存进**同一个** `size_t` 成员（便于用一次原子操作同时更新两者）。

¶3–5 阐述用实体：*scope-join-t* 是 join 发送器的标签；*association-t*<Scope> 模型化 `scope_association`，含一个 `Scope* scope` 成员：非空即 engaged，`try_associate()` 转调 `scope->try-associate()`，释放时调用 `scope->disassociate()`。

¶4 join 发送器的 *impls-for*：

```cpp
template<class Scope, class Rcvr>
struct state {
  struct rcvr-t { /* 把完成转给外部接收器 rcvr */ };
  using sched-sender = decltype(schedule(get_start_scheduler(get_env(declval<Rcvr&>()))));
  using op-t = connect_result_t<sched-sender, rcvr-t>;

  Scope* scope;
  Rcvr& receiver;
  op-t op;     // 预先 connect 好：schedule 到接收器的启动调度器

  void complete() noexcept        { start(op); }                  // 计数归零时（在别的线程上）调用
  void complete-inline() noexcept { set_value(std::move(receiver)); }
};

static constexpr auto start = [](auto& s, auto&) noexcept {
  if (s.scope->start-join-sender(s))
    s.complete-inline();
};
```

两条完成路径：

- 启动 join 时计数**已经**是 0：*start-join-sender* 返回 true，就地 `set_value`——同步完成；
- 否则把 `s` 注册到 scope 上，返回 false；之后**最后一个**关联被释放时，scope 调用 `s.complete()`——它不直接 `set_value`，而是启动预先 connect 好的 `schedule(get_start_scheduler(env))`，**回到 join 发送器被启动的调度器上**再完成。

后者的原因：最后一个关联在哪个线程释放是不确定的（可能是线程池的某个线程），直接在那里完成 join 的接收器会让 `join()` 之后的代码跑到一个意料之外的线程上。注意这要求 join 的接收器环境回答 `get_start_scheduler`——否则 *sched-sender* 类型非良构。

## simple_counting_scope（[exec.scope.simple.counting]）

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
private:
  size_t count;
  scope-state-type state;
  assoc-t try-associate() noexcept;
  void disassociate() noexcept;
  template<class State> bool start-join-sender(State& state) noexcept;
};
```

[exec.scope.simple.counting.general] ¶1 为判断数据竞争，`get_token`、`close`、`join`、*try-associate*、*disassociate*、*start-join-sender* 表现为**原子操作**（[[intro.multithread]]），在同一对象上它们呈现单一全序。可以从任意线程并发地 spawn、close、join。

`max_associations` 是实现定义的 {{impl}} 最大关联数。

### 构造与析构（[exec.simple.counting.ctor]）

- ¶1 构造：*Postconditions*：`count` 为 0，状态为 *unused*。
- ¶2 析构：若状态**不是** *joined*、*unused*、*unused-and-closed* 之一，调用 `terminate`。

即：**用过的 scope 必须 join 完才能析构**。若还有关联的工作在跑就析构 scope，那些工作释放关联时会访问已销毁的 scope。用 `terminate` 而不是 UB 或阻塞等待，是为了把"忘了 join"变成一个立刻可见的错误。

### 成员（[exec.simple.counting.mem]）

- ¶1 `get_token()`：返回指向 `this` 的令牌。
- ¶2–3 `close()`：*unused* → *unused-and-closed*，*open* → *closed*，*open-and-joining* → *closed-and-joining*；其他无效果。*Postconditions*：此后的 *try-associate* 全部失败。
- ¶4 `join()`：返回 *make-sender*(*scope-join-t*(), this)。**`join()` 本身不改变状态**——状态在 join 发送器的操作被**启动**时才改变。
- ¶5–6 *try-associate*：若 `count == max_associations`，失败；否则 *unused* → 计数加一并转为 *open*；*open*、*open-and-joining* → 计数加一；其他（已关闭或已 joined）失败。成功返回 engaged 的 *assoc-t*，失败返回默认构造的。
- ¶7–8 *disassociate*：*Preconditions*：`count > 0`。计数减一；若降到 0 且状态为 *open-and-joining* 或 *closed-and-joining*，转为 *joined* 并对所有注册的对象调用 `complete()`。注 1：调用 `complete()` 可能导致 `*this` 被销毁（join 完成后，等待者可能立刻析构 scope）。
- ¶9 *start-join-sender*(st)：若 `count` 为 0，转为 *joined*，返回 true。否则 *open*/*open-and-joining* → *open-and-joining*，*closed*/*closed-and-joining* → *closed-and-joining*，注册 `st`，返回 false。

!!! note "join 不等于 close"
    从状态表看，在 *open-and-joining* 状态下 `try-associate` **仍然成功**：join 正在等待时，仍可以有新工作加入，join 会连它们一起等。这允许"一边处理一边等待全部结束"的模式（比如处理中又派生出子任务）。若要保证 join 之后不再有新工作，先 `close()`。另外，计数一旦归零并转为 *joined*，此后 *try-associate* 一律失败——joined 是终态。

!!! lawyer "close 的后置条件说\"返回 false\""
    [exec.simple.counting.mem] ¶3 写的是"any subsequent call to *try-associate*() on `*this` returns false"，但 *try-associate* 的返回类型是 *assoc-t*，不是 `bool`。显然意思是返回一个不 engaged 的（转换为 `bool` 为 false 的）*assoc-t*。

### 令牌（[exec.simple.counting.token]）

```cpp
struct simple_counting_scope::token {
  template<sender Sender> Sender&& wrap(Sender&& snd) const noexcept;
  assoc-t try_associate() const noexcept;
private:
  simple_counting_scope* scope;
};
```

- ¶1 `wrap(snd)`：原样返回 `std::forward<Sender>(snd)`；
- ¶2 `try_associate()`：`return scope->try-associate();`。

## counting_scope（[exec.scope.counting]）

¶1 `counting_scope` 在 `simple_counting_scope` 的基础上增加了**取消**支持。除下面说明的成员外，语义相同。

```cpp
class counting_scope {
public:
  struct token {
    template<sender Sender> sender auto wrap(Sender&& snd) const noexcept(see below);
    assoc-t try_associate() const noexcept;
  private:
    counting_scope* scope;
  };
  // ... 同 simple_counting_scope ...
  void request_stop() noexcept;
private:
  size_t count;
  scope-state-type state;
  inplace_stop_source s_source;
  // ...
};
```

- ¶3–4 `request_stop()`：等价于 `s_source.request_stop()`；并发调用不引入数据竞争。
- ¶7 `token::wrap(snd)`：`return stop-when(std::forward<Sender>(snd), scope->s_source.get_token());`——被包装的发送器 connect 时，看到的停止令牌是"外部令牌 **或** scope 的令牌"的组合（*stop-when*，[[exec.spawn]]）。于是 `scope.request_stop()` 可以一次性请求取消所有通过该 scope 启动的工作。

典型的关停流程：

```cpp title="shutdown.cpp"
scope.close();          // 1. 不再接受新工作
scope.request_stop();   // 2. 请求已有工作尽快结束
std::this_thread::sync_wait(scope.join());   // 3. 等它们真的结束
```

## 陷阱

!!! pitfall "忘了 join"
    ```cpp title="forgot-join.cpp"
    {
      ex::counting_scope scope;
      ex::spawn(work(), scope.get_token());
    }   // terminate：状态是 open，不是 joined/unused/unused-and-closed
    ```
    即使 `work()` 已经完成、计数已经回到 0，状态仍是 *open*（只有启动了 join 发送器、计数归零时才会进入 *joined*）。所以只要 spawn 过，就**必须**启动并等待一次 `join()`。

!!! pitfall "join 发送器需要启动调度器"
    join 的操作状态在构造时就 connect 了 `schedule(get_start_scheduler(get_env(rcvr)))`。把 `scope.join()` 交给一个环境里没有 `get_start_scheduler` 的接收器，程序非良构。`sync_wait`、`task` 的环境都提供它；自己写接收器时要注意。

## 思考题

!!! question "1. scope 可以在 join 的完成中被销毁吗？"
    `sync_wait(scope.join())` 返回后 `scope` 立刻析构。最后一个关联是在线程池线程上释放的，这时 *disassociate* 还在调用 `complete()`——会访问已销毁的 scope 吗？

<details markdown="1">
<summary>答案</summary>

注 1 明确承认"调用 `complete()` 可能导致 `*this` 被销毁"，所以实现必须保证在调用 `complete()` 之后不再访问 scope 的成员（例如先把注册列表取到局部变量）。在 `sync_wait` 的情形下，`complete()` 启动的是调度到 `sync_wait` 的 run_loop 上的操作——它只是入队，真正的 `set_value` 在 `sync_wait` 的线程上发生；之后 `sync_wait` 返回、scope 析构。此时状态已是 *joined*，析构合法。只要实现遵守"`complete()` 之后不碰 `this`"，就没有问题。
</details>

!!! question "2. 为什么 try_associate 可能失败？"
    列出 `simple_counting_scope` 中 *try-associate* 失败的所有情形，并说明 `spawn` 在失败时做什么。

<details markdown="1">
<summary>答案</summary>

(1) `count == max_associations`；(2) 状态为 *closed*、*unused-and-closed*、*closed-and-joining*（已关闭）；(3) 状态为 *joined*。`spawn` 在关联失败时不启动发送器，直接销毁为它分配的状态（[[exec.spawn]] 中 *spawn-state*::*run* 走 `complete()` 分支）——工作被静默丢弃，不报错。`associate` 在失败时以 `set_stopped` 完成；`spawn_future` 返回的发送器也以 `set_stopped` 完成。
</details>

## 小结

- `scope_association`：只移动的 RAII 关联句柄；`scope_token`：可复制，`try_associate()` + 不改变签名的 `wrap()`。
- 计数作用域：关联计数 + 状态机；`close()` 拒绝新关联；`join()` 发送器在计数归零时完成，并回到 join 被启动的调度器上。
- 析构时必须处于 *joined*、*unused* 或 *unused-and-closed*，否则 `terminate`。
- join 进行中仍可加入新关联；`joined` 是终态。
- `counting_scope` 额外提供 `request_stop()`，其令牌的 `wrap` 把 scope 的停止令牌织进被包装的发送器。
