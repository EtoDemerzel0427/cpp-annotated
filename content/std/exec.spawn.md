---
title: spawn、spawn_future 与 associate
summary: 把工作交给 async scope——spawn 急切启动、不返回结果，只接受不会 error 的发送器；spawn_future 急切启动并返回一个可以取回结果的发送器，丢弃它会请求停止；associate 惰性地把发送器与 scope 关联，关联失败即以 stopped 完成；阐述用的 stop-when 合并两个停止令牌
status: done
covers: exec.associate, exec.stop.when, exec.spawn.future
papers: P2300R10
related: exec.scope, exec.consumers, exec.async.ops, exec.adapt, thread.stoptoken, allocator.requirements
tags: 标准库, std::execution, 结构化并发, async scope, spawn
updated: 2026-10-18
---

[[exec.scope]] 提供了计数和等待；本页的三个算法负责把发送器**交给** scope：

| 算法 | 类别 | 何时启动 | 结果 | 关联失败时 |
|---|---|---|---|---|
| `spawn(sndr, token[, env])` | 消费者，返回 `void` | **立即** | 丢弃 | 不启动，静默丢弃 |
| `spawn_future(sndr, token[, env])` | 适配器（返回发送器） | **立即** | 通过返回的发送器取回 | 返回的发送器以 stopped 完成 |
| `associate(sndr, token)` | 适配器 | 惰性（随返回的发送器一起 start） | 原样转发 | 以 stopped 完成 |

前两者是"急切"（eager）的：调用时就启动工作，替代了早期 P2300 中的 `start_detached` 与 `ensure_started`，但多了一个强制要求——必须有一个 scope 为被启动的工作负责。

## spawn（[exec.spawn]）

¶1 `spawn` 尝试把输入发送器与令牌的 async scope 关联，成功则**急切地**启动它。

¶2 `sndr` 不是发送器、`Token` 不满足 `scope_token`、或 `Env` 不满足 *queryable* 时，`spawn(sndr, token, env)` 非良构。

¶3–4 接收器：

```cpp
struct spawn-state-base { virtual void complete() noexcept = 0; };

struct spawn-receiver {
  using receiver_concept = receiver_tag;
  spawn-state-base* state;
  void set_value() && noexcept   { state->complete(); }
  void set_stopped() && noexcept { state->complete(); }
};
```

**只有** `set_value()`（无参）和 `set_stopped()`。这意味着：被 spawn 的发送器**必须**只以 `set_value_t()` 或 `set_stopped_t()` 完成——带值的完成、任何 error 完成都会让 connect 的 *Mandates*（*receiver-of*）失败，程序非良构。

理由：spawn 之后没有人接收结果，错误也无处报告。与其让错误被悄悄吞掉，不如强迫调用者**显式**处理：`| upon_error(...)` 记日志、`| then([](auto&&...) {})` 丢弃值。

¶5–8 状态：

```cpp
template<class Alloc, scope_token Token, sender Sender>
struct spawn-state : spawn-state-base {
  using op-t = connect_result_t<Sender, spawn-receiver>;
  spawn-state(Alloc alloc, Sender&& sndr, Token token);   // alloc, op = connect(sndr, spawn-receiver(this)), assoc = token.try_associate()
  void complete() noexcept override;
  void run() noexcept;                                     // if (assoc) start(op); else complete();
private:
  Alloc alloc; op-t op; assoc-t assoc;
};
```

- ¶6 构造：先 **connect**，再 **try_associate**。
- ¶7 `run()`：关联成功就 `start(op)`；失败就直接 `complete()`。
- ¶8 `complete()`：把 `assoc` **移到局部变量**，然后用分配器销毁并释放 `*this`；局部的 `assoc` 在函数结束时析构，**释放关联**。

¶8 的顺序很关键：先销毁状态对象（包括其中的操作状态），**再**释放关联。若顺序反过来，关联释放 → 计数归零 → join 完成 → 等待者析构 scope 乃至整个程序的相关对象，而此时 `spawn-state` 还没销毁完——操作状态的析构函数可能访问已经不存在的东西。scope 的计数精确地覆盖了"spawn 出去的对象的整个生存期"，而不仅仅是"工作运行的时间"。

¶9 分配器与环境：设 `new_sender` 为 `token.wrap(sndr)`：

- ¶9.1 `get_allocator(env)` 良构：用它，`senv` 为 `env`；
- ¶9.2 否则 `get_allocator(get_env(new_sender))` 良构（发送器**属性**提供了分配器）：用它，`senv` 为 *JOIN-ENV*(prop(get_allocator, alloc), env)；
- ¶9.3 否则 `allocator<void>()`，`senv` 为 `env`。

¶10 `spawn(sndr, token, env)` 类型为 `void`，效果：用 `alloc` 分配并构造 `spawn-state(alloc, write_env(token.wrap(sndr), senv), token)`，然后调用 `o.run()`。抛出异常时，已构造的对象被销毁、已分配的内存被释放。

注意被启动的是 `write_env(token.wrap(sndr), senv)`：

- `token.wrap` 让 scope 修饰发送器（`counting_scope` 织入它的停止令牌）；
- `write_env(..., senv)` 让发送器看到调用者提供的环境，以及在 ¶9.2 情形下发送器自己声明的分配器。

被 spawn 的工作的环境**只有** `senv`——它没有"调用者的接收器"可以继承。所以 `spawn(sndr, token)`（¶11：等价于 `spawn(sndr, token, env<>())`）启动的发送器看到的是一个几乎空的环境：没有调度器、没有停止令牌（除非 scope 的 `wrap` 提供）。需要的话通过第三个实参传入。

```cpp title="spawn.cpp"
namespace ex = std::execution;

ex::counting_scope scope;
auto pool = ex::get_parallel_scheduler();

ex::spawn(ex::starts_on(pool, ex::just() | ex::then([] { do_work(); }))
            | ex::upon_error([](std::exception_ptr) noexcept { /* 记日志 */ }),
          scope.get_token());
// ...
std::this_thread::sync_wait(scope.join());
```

## spawn_future（[exec.spawn.future]）

¶1 `spawn_future` 尝试关联，成功则**急切地**启动输入发送器；返回一个发送器，connect 并启动后，以急切启动的那个发送器的结果完成——或者，若输入发送器根本没有被启动（关联失败），以 `set_stopped` 完成。

它是"先开始做，结果以后再取"：

```cpp title="spawn-future.cpp"
namespace ex = std::execution;

ex::counting_scope scope;
auto fut = ex::spawn_future(ex::starts_on(pool, compute()), scope.get_token());  // 已经开始计算
do_something_else();
auto [v] = std::this_thread::sync_wait(std::move(fut)).value();                   // 取结果
std::this_thread::sync_wait(scope.join());
```

¶2 合法性同 `spawn`。

### 状态与共享（¶3–14）

结果要在"工作完成"与"有人来取"两个独立事件之间传递，二者先后不定。规范为此定义了 *spawn-future-state*（堆上分配）：

- ¶4–5 *spawn-future-state-base*<completion_signatures<Sigs...>> 有一个 `variant<monostate, tuple<set_stopped_t>, [tuple<set_error_t, exception_ptr>,] as-tuple<Sigs>...>` 存放结果（`as-tuple<Tag(Args...)>` = `decayed-tuple<Tag, Args...>`；若某些结果不能无异常 decay-copy，加上 `exception_ptr` 那一项）。
- ¶6 *spawn-future-receiver*：接收输入发送器的完成，把它 decay-copy 进 `result`（失败则存 `exception_ptr`），然后调用 `complete()`。它**接受所有**完成——与 `spawn` 不同，结果有人要。
- ¶7 被启动的实际是 *future-spawned-sender* = `write_env(stop-when(sndr, ssource.get_token()), env)`：状态里有一个自己的停止源 `ssource`，用 *stop-when* 把它织进去。
- ¶8 构造：connect，然后 `try_associate()`；成功就 `start(op)`，失败就直接 `set_stopped(receiver-t(this))`。

¶9 *complete*、*consume*、*try-set-stopped*、*abandon* 四个操作在判断数据竞争时表现为原子操作，在同一对象上呈现单一全序。它们实现了一个小型的"汇合"协议：

| 操作 | 由谁调用 | 含义 |
|---|---|---|
| *complete* | 输入发送器完成时 | 结果已就绪 |
| *consume*(rcvr) | 返回的发送器被 start 时 | 有人来取结果了 |
| *try-set-stopped* | 取结果的一方被请求停止时 | 取消等待 |
| *abandon* | 返回的发送器被**丢弃**（从未 start）时 | 没人要结果了 |

- ¶10 *complete*：若先于 *consume*/*try-set-stopped*/*abandon* 发生，无效果（等人来取）；若已有 *consume* 注册了接收器（且未被 *try-set-stopped*），以结果完成那个接收器；否则（已被放弃）*destroy*。
- ¶11 *consume*(rcvr)：若先于 *complete*，注册 `rcvr`，等结果；若已 *try-set-stopped*，`set_stopped(rcvr)`；否则（结果已在）立即用结果完成 `rcvr` 并 *destroy*。
- ¶12 *try-set-stopped*：若已注册接收器而结果未到，以 `set_stopped` 完成那个接收器并 *destroy*；否则无效果。
- ¶13 *abandon*：若先于 *complete*，`ssource.request_stop()`——**请求停止**仍在运行的工作，状态留给 *complete* 去销毁；否则（结果已在、没人要）*destroy*。
- ¶14 *destroy*：把关联移到局部变量，用分配器销毁并释放状态，再让局部关联析构（与 `spawn` 相同的顺序）。

¶20 `spawn_future` 返回 *make-sender*(spawn_future, std::move(u))，`u` 是一个 `unique_ptr`，其删除器调用 *abandon*（¶20.2）。所以：**丢弃 `spawn_future` 返回的发送器 = 请求取消那份工作**。这与 `std::future` 的"析构时阻塞等待"截然不同：既不阻塞，也不泄漏——工作被请求停止，最终完成时由 *complete* 清理状态，scope 的 join 会等到这一刻。

¶15–18 返回的发送器 connect 得到 *future-operation*：start 时（`run`）先在接收器的停止令牌上注册回调（回调调用 *try-cancel*：`ssource.request_stop()` 加 *try-set-stopped*），然后 `state.release()->consume(inner)`。接收器被请求停止时，会**同时**取消正在运行的工作和"等待"本身。

¶19 分配器与环境的确定方式同 `spawn` ¶9。¶21 `spawn_future(sndr, token)` ≡ `spawn_future(sndr, token, env<>())`。

## associate（[exec.associate]）

¶1 `associate` 尝试把发送器与 async scope 关联，使 scope 能跟踪由该发送器创建的任何异步操作的生存期。

与 `spawn` 不同，它**不启动**任何东西：`associate(sndr, token)` 返回一个惰性的发送器。关联在**调用 `associate` 时**就尝试建立（¶2 *associate-data* 的构造函数），并由返回的发送器持有，直到它产生的操作完成。

¶2–8 *associate-data*<Token, Sender>：

- 构造：`sndr = t.wrap(s)`，然后 `assoc = t.try_associate()`；若关联失败，立即销毁刚包装好的发送器（只有成功时才保留它——用一个 `unique_ptr` 守卫加 `union` 成员实现）。
- ¶4–5 复制构造（仅当 *wrap-sender* 可复制）：对源对象的关联调用 `try_associate()` 再建立一个关联；成功才复制发送器。复制一个 associate 发送器 = 再占用一份 scope 计数。
- 移动构造：通过 `release()` 转移关联与发送器。
- ¶7 析构：关联存在就销毁发送器（关联随成员析构释放）。

¶9 `associate(sndr, token)`：`sndr` 不是发送器或令牌类型不满足 `scope_token` 时非良构；否则 *make-sender*(associate, *associate-data*(token, sndr))。

¶11 connect 时 *get-state* 构造 *op_state*：若有关联，就地 `connect(std::move(*sender), rcvr)`；否则只记下接收器指针。¶13 *start*：有关联就 `start(op)`，否则 `set_stopped(std::move(*rcvr))`。

¶14 `associate(sndr, token)` 的求值可能产生可以通过令牌关联的 scope 对象观察到的副作用（计数加一）。这是对 [[exec.adapt.general#3]] ¶3.1"适配器在 connect+start 前不得产生可观察效果"的明确例外。

`associate` 适合"我会自己启动它，但希望 scope 知道它的存在"的场景，比如把工作交给一个不了解 scope 的第三方执行器；`spawn` 实际上就是"associate + 立即启动 + 丢弃结果"的特化（虽然规范是分别写的）。

## stop-when（[exec.stop.when]）

¶1 阐述用的 *stop-when*(sndr, token) 把一个额外的停止令牌 `t` **融合**进发送器：connect 到接收器 `r` 后，产生的操作状态既接收 `t` 的停止请求，也接收 `get_stop_token(get_env(r))` 的停止请求。

¶2：

- ¶2.1 `sndr` 不是发送器或 `token` 不是 `stoppable_token`：非良构；
- ¶2.2 `token` 是 `unstoppable_token`：直接就是 `sndr`（`token` 与 `sndr` 的求值顺序不确定）——不可能停止的令牌没有融合的必要；
- ¶2.3 否则返回 `osndr`；connect 到 `r` 时，设 `rtoken = get_stop_token(get_env(r))`：
  - ¶2.3.1 `rtoken` 不可停止：等价于 `connect(write_env(sndr, prop(get_stop_token, token)), r)`；
  - ¶2.3.2 否则用一个合成令牌 `stoken`：`stop_requested()` 为二者之或，`stop_possible()` 也为二者之或，在它上面注册的回调在**任一**令牌触发时被调用（至多一次，注 1）。

`counting_scope::token::wrap` 和 `spawn_future` 的内部都使用它：被管理的工作既响应调用者的取消，也响应 scope / future 自己的取消。

## 陷阱

!!! pitfall "spawn 一个有返回值的发送器"
    `ex::spawn(ex::just(42), tok);` 非良构：*spawn-receiver* 没有 `set_value(int)`。必须显式丢弃值：`ex::spawn(ex::just(42) | ex::then([](int) {}), tok);`。同样，任何可能以 error 完成的发送器都要先处理错误。

!!! pitfall "spawn 不传环境"
    被 spawn 的工作看不到 spawn 调用者所在发送器链的环境（调度器、分配器、停止令牌）。在协程或发送器链中 spawn 时，若希望子工作继承某些环境，要通过第三个实参显式传入，例如 `spawn(work, tok, env{prop(get_scheduler, sch)})`。

## 思考题

!!! question "1. 关联失败时 spawn 的状态对象"
    `scope` 已关闭，`spawn(sndr, scope.get_token())`。按 ¶6–¶10，会分配内存吗？`sndr` 会被 connect 吗？

<details markdown="1">
<summary>答案</summary>

会分配：¶10.1 先用分配器分配并构造 `spawn-state`；¶6 的构造过程会 connect（`op` 成员初始化）并调用 `try_associate()`（失败）。随后 `run()` 发现没有关联，调用 `complete()` 销毁并释放状态。所以即使关联失败，`sndr` 也被 connect 过（但从未 start），操作状态被构造又被销毁。connect 本身若有副作用（标准发送器没有），在这里也会发生。
</details>

!!! question "2. spawn_future 的发送器被丢弃，而工作永不响应停止"
    `auto f = spawn_future(never_ending_work(), tok);` 然后丢弃 `f`。会怎样？

<details markdown="1">
<summary>答案</summary>

`f` 析构时删除器调用 *abandon*：工作尚未完成，于是 `ssource.request_stop()`。若工作忽略停止请求、永不完成，状态永不被销毁，关联永不释放，`scope.join()` 永不完成，而 scope 在 join 之前不能析构（否则 `terminate`）。这不是 `spawn_future` 的缺陷，而是结构化并发的诚实体现：每个被启动的工作都必须最终完成（[[exec.async.ops#2]]），scope 只是把"谁来等"这件事显式化了。
</details>

## 小结

- `spawn`：急切启动、无结果；只接受 `set_value_t()`/`set_stopped_t()` 的发送器；关联失败静默丢弃；先销毁状态再释放关联。
- `spawn_future`：急切启动，返回可取结果的发送器；*complete* / *consume* / *try-set-stopped* / *abandon* 四方汇合；丢弃返回值即请求停止。
- `associate`：惰性；调用时即尝试关联；失败则以 `set_stopped` 完成；复制即再关联一次。
- 被启动工作的环境只来自显式传入的 `env`（加上 scope 的 `wrap` 与分配器）。
- *stop-when*：把额外的停止令牌与接收器的令牌按"或"合并。
