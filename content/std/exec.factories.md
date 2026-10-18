---
title: 发送器工厂
summary: 从非发送器造出发送器的三个起点——schedule(sch) 跳到调度器上；just / just_error / just_stopped 在 start 中同步地以给定结果完成；read_env(q) 以接收器环境中查询 q 的结果完成
status: done
covers: *
papers: P2300R10
related: exec.snd, exec.sched, exec.async.ops, exec.queries, exec.adapt, exec.let
tags: 标准库, std::execution, 发送器工厂
updated: 2026-10-18
---

[[exec.async.ops#14]] 把发送器算法分成工厂、适配器、消费者三类。**工厂**是一切发送器链的起点：它不接受发送器，只接受普通值，返回一个发送器。标准提供三组：

| 工厂 | 完成方式 | 何时完成 |
|---|---|---|
| `schedule(sch)` | `set_value()` | 在 `sch` 的执行资源上（异步） |
| `just(vs...)`、`just_error(e)`、`just_stopped()` | 对应的 `set_*`，带给定的数据 | 在 `start` 内同步完成 |
| `read_env(q)` | `set_value(q(env))` | 在 `start` 内同步完成 |

阅读本页之前最好先看 [[exec.snd]] 中的 *make-sender* / *impls-for* 骨架：后两个工厂的规范就是"特化 *impls-for* 的 *start*"。

## schedule（[exec.schedule]）

¶1 `schedule` 从调度器取得一个调度发送器（[[exec.async.ops#10]]）。

¶2 `schedule(sch)` 表达式等价于 `sch.schedule()`。

¶3 *Mandates*：`sch.schedule()` 的类型满足 `sender`。

这是本章最简单的 CPO：调度器的全部能力都在它的 `schedule()` 成员里。调度发送器的语义要求（value 完成不带数据、value 完成调度器等于原调度器）在 [[exec.sched]] 中。

## just、just_error、just_stopped（[exec.just]）

¶1 三者是发送器工厂，其异步操作在**启动操作中同步完成**，分别以 value、error、stopped 完成操作。

¶2 设 *just-cpo* 是三者之一，`Ts` 是 `decltype((ts))...`。*just-cpo*(ts...) 在下列情况下非良构：

- ¶2.1 某个 `Ts` 不满足 *movable-value*（[[exec]] 中的 [exec.general] ¶6：可 decay 后移动构造、不是数组）；
- ¶2.2 `just_error` 的实参不是恰好一个；
- ¶2.3 `just_stopped` 有实参。

否则等价于 *make-sender*(*just-cpo*, *product-type*{ts...})。对应的 *set-cpo* 分别是 `set_value`、`set_error`、`set_stopped`，*impls-for* 只覆盖 *start*：

```cpp
template<>
struct impls-for<decayed-typeof<just-cpo>> : default-impls {
  static constexpr auto start = [](auto& state, auto& rcvr) noexcept -> void {
    auto& [...ts] = state;
    set-cpo(std::move(rcvr), std::move(ts)...);
  };
};
```

几个推论：

- **值被存进发送器**：`just(s)` 把 `s` decay-copy 进 *product-type*。connect 时（*default-impls*::*get-state*）再复制或移动进操作状态；`start` 时**移动**给接收器。所以 `just(std::string("hi"))` 的签名是 `set_value_t(std::string)`——以右值发出。
- **签名由 start 中潜在求值的调用决定**（[[exec.snd]] ¶47）：`set_value(std::move(rcvr), std::move(ts)...)` 中实参是 `Ts` 的 xvalue，所以签名是 `set_value_t(decay_t<Ts>...)`（*MATCHING-SIG* 把 `T` 与 `T&&` 视为一致）。
- **没有 error、没有 stopped**：`just(1)` 的签名只有 `set_value_t(int)`。`start` 不可能失败，因为数据早已在 connect 时准备好；如果复制数据会抛异常，那发生在 `connect` 里（`connect` 抛异常，而不是以 error 完成）。
- `just()` 不带值：签名 `set_value_t()`，常用作"什么也不做的起点"，比如 `starts_on` 的降级形式里用到的 `continues_on(just(), sch)`（[[exec.on]]）。

```cpp title="just.cpp"
namespace ex = std::execution;

auto a = ex::just(1, 2.0);                       // set_value_t(int, double)
auto b = ex::just_error(std::make_error_code(std::errc::io_error)); // set_error_t(std::error_code)
auto c = ex::just_stopped();                     // set_stopped_t()
// ex::just_error();                             // error: just_error 需要恰好一个实参
// ex::just_stopped(1);                          // error: just_stopped 不接受实参
// int arr[3]; ex::just(arr);                    // error: 数组不满足 movable-value
auto [x, y] = std::this_thread::sync_wait(a).value();   // x == 1, y == 2.0
```

!!! note "just 是同步完成的"
    `start(op)` 返回之前，接收器的 `set_value` 已经被调用并返回了。这正是 [[exec.async.ops#2]] 注 1 所说的"异步操作可以同步执行"。所以 `just` 的属性用 *inline-attrs*（[[exec.snd]]）回答完成调度器：它在"调用 `start` 的那个调度器"上完成，也就是环境里的 `get_scheduler`。

## read_env（[exec.read.env]）

¶1 `read_env` 产生一个发送器，其操作在启动操作中同步完成，value 完成的结果等于从**接收器环境**中读出的一个值。

¶2 `read_env(q)`（`q` 是查询对象）等价于 *make-sender*(read_env, q)。

¶3 *impls-for* 特化：

```cpp
template<>
struct impls-for<decayed-typeof<read_env>> : default-impls {
  static constexpr auto start = [](auto query, auto& rcvr) noexcept -> void {
    TRY-SET-VALUE(rcvr, query(get_env(rcvr)));
  };
  template<class Sndr, class Env> static consteval void check-types();
};
```

¶4–5 *check-types*：设 `Q` 是 `decay_t<data-type<Sndr>>`，若 `Q()(env)`（`env` 是 `Env` 类型的左值）非良构或类型为 `void`，抛出 *unspecified-exception*。

用途：让一条发送器链"看到"它的执行环境。

```cpp title="read-env.cpp"
namespace ex = std::execution;

// 在当前环境的调度器上再调度一段工作
auto work = ex::read_env(ex::get_scheduler)
          | ex::let_value([](auto sch) {
              return ex::schedule(sch) | ex::then([] { return 42; });
            });

// 取出停止令牌，在长循环里检查
auto loop = ex::read_env(std::get_stop_token)
          | ex::then([](auto token) {
              while (!token.stop_requested()) { /* ... */ }
            });
```

*TRY-SET-VALUE*：若查询可能抛异常就包一层 `try`——但查询被 *MANDATE-NOTHROW* 包裹、必然是 noexcept 的；可能抛异常的是把结果作为实参传给 `set_value` 时的复制。

!!! lawyer "read_env 是依赖发送器吗？按字面读，不是"
    直觉上 `read_env(get_scheduler)` 的值类型取决于环境，应当是**依赖发送器**（[[exec.async.ops#13]]）。但按草案字面：
    
    1. 不带环境调用 `get_completion_signatures<S>()` 时，[exec.getcomplsigs] ¶3.1 调用 *basic-sender* 的静态成员；
    2. [[exec.snd]] ¶47 规定此时 `E` 取 `env<>`，于是 *CHECK-TYPES* 是 `check-types<S, env<>>()`；
    3. 上面的 ¶5 规定 `get_scheduler(env<>&)` 非良构时抛出的是 *unspecified-exception*，不是 `dependent_sender_error`。
    
    结果是 `dependent_sender<S>` 为 false、`sender_in<S>` 也为 false，*make-sender* 的 *Mandates* ¶24.4 不成立——`read_env(get_scheduler)` 这个表达式本身就非良构。这显然违背 `read_env` 存在的目的。较合理的读法是：`read_env` 在不带环境时应当报告依赖（抛 `dependent_sender_error`）。在草案修正之前，这是一处值得记下的措辞缺口；实际行为以实现为准。对 `read_env(std::get_stop_token)` 则没有这个问题：`get_stop_token(env<>&)` 良构（返回 `never_stop_token`），所以按同样的字面推演，它被当作非依赖发送器，签名是 `set_value_t(never_stop_token)`——这又引出另一个微妙之处：带环境 connect 时，真正的值类型可能是 `stop_token` 或 `inplace_stop_token`，与无环境时报告的签名不同，违反 [[exec.getcomplsigs#4]]"无环境签名集须是有环境签名集超集、且差别只能是 error/stopped"的要求。

## 思考题

!!! question "1. just 的数据被复制几次？"
    `auto s = just(std::string(1000, 'x')); sync_wait(s);`（以左值 `s` 调用）。从构造 `s` 到 `sync_wait` 的接收器收到字符串，`std::string` 被复制/移动了几次？

<details markdown="1">
<summary>答案</summary>

按阐述代码推演（实现可能不同）：
1. `just(std::string(...))`：临时字符串移动进 *product-type*，再移动进 *basic-sender*（实践中通过保证复制消除和直接列表初始化，可能合并为一次移动）；
2. `sync_wait(s)` 以左值 connect：*get-state* 用 `forward_like<Sndr>(data)` 取出数据，`Sndr` 是左值引用类型，于是 *allocator-aware-forward* 返回左值引用，`state-type` 是 `decay_t<...>`，**复制**一次进操作状态；
3. `start`：`set_value(std::move(rcvr), std::move(ts)...)`，以右值交给 *sync-wait-receiver*，后者 `result.emplace(...)` 再**移动**一次进 `optional<tuple<string>>`。

所以至少一次复制、若干次移动。若写 `sync_wait(std::move(s))`，第 2 步也变成移动，整个过程没有复制。
</details>

!!! question "2. just_error(42) 合法吗？"
    `just_error` 的错误类型可以是 `int` 吗？`sync_wait(just_error(42))` 会怎样？

<details markdown="1">
<summary>答案</summary>

合法：error 完成的数据可以是任何对象类型（[[exec.cmplsig]] ¶4.2），签名是 `set_error_t(int)`。`sync_wait` 收到错误时用 *AS-EXCEPT-PTR*（[[exec]] 中的 [exec.general] ¶8）把它变成 `exception_ptr`：`int` 既不是 `exception_ptr` 也不是 `error_code`，所以是 `make_exception_ptr(42)`，随后 `rethrow_exception`——`sync_wait` 抛出一个 `int` 类型的异常，可以用 `catch (int)` 捕获。
</details>

## 小结

- `schedule(sch)` = `sch.schedule()`：跳到调度器上，以 `set_value()` 完成。
- `just(vs...)` / `just_error(e)` / `just_stopped()`：数据存进发送器，在 `start` 中同步以右值发出；`just_error` 恰好一个实参，`just_stopped` 无实参，数组不行。
- `read_env(q)`：在 `start` 中以 `q(get_env(rcvr))` 完成，是让发送器链读取环境的标准方式；它与依赖发送器机制的配合在草案字面上存在缺口。
