---
title: 发送器工厂
summary: 发送器链的三个起点：schedule(sch) 跳到调度器上完成；just、just_error、just_stopped 在 start 中同步地以给定的结果完成；read_env(q) 以接收器环境中查询 q 的结果完成。
status: draft
covers: *
papers: P2300R10
related: exec.snd, exec.sched, exec.async.ops, exec.queries, exec.adapt, exec.let
tags: 标准库, std::execution, 发送器工厂
updated: 2026-10-19
---

!!! tldr
    - 工厂不接受发送器，只接受普通的值，返回一个发送器，是每条发送器链的起点。
    - `schedule(sch)` 就是 `sch.schedule()`：在调度器的执行资源上以 `set_value()` 完成。
    - `just(vs...)` 把值存进发送器，在 `start` 里同步地以右值发出；它没有 error 或 stopped 完成。`just_error` 要恰好一个实参，`just_stopped` 不能有实参。
    - `read_env(q)` 在 `start` 里读出接收器环境中查询 `q` 的结果，以它作为值完成。

本页的例子没有经过编译验证：本机 Clang 23 附带的 libc++ 还没有实现 `std::execution` 的发送器部分，所以不加判定标记。

## 三个起点

[[exec.async.ops#14]] 把发送器算法分成工厂、适配器、消费者三类。工厂（sender factory）从非发送器的实参造出发送器：

| 工厂 | 完成方式 | 何时完成 |
|---|---|---|
| `schedule(sch)` | `set_value()` | 在 `sch` 的执行资源上，通常是异步的 |
| `just(vs...)`、`just_error(e)`、`just_stopped()` | 对应的完成函数，带上给定的数据 | 在 `start` 内同步完成 |
| `read_env(q)` | `set_value(q(env))` | 在 `start` 内同步完成 |

后两个工厂的规范写成 *make-sender* 加一个 *impls-for* 特化的形式。读这两段之前，最好先看 [[exec.snd]] 介绍的这套骨架：每个标准发送器都是（标签, 数据, 子发送器...）三部分，算法只需说明 *start*、*complete* 等几个钩子和默认行为有什么不同。

## schedule [exec.schedule]

¶1 `schedule` 从[[g:scheduler|调度器]]取得一个[[g:schedule-sender|调度发送器]]（[[exec.async.ops#10]]）。

¶2 `schedule(sch)` 等价于 `sch.schedule()`。¶3 要求它的类型满足 `sender`（*Mandates*）。

调度器的全部能力都在 `schedule()` 成员里。调度发送器要满足的语义，比如值完成不带数据、值完成调度器就是原来的调度器，写在 [[exec.sched]]。

## just、just_error、just_stopped [exec.just]

```cpp title="just.cpp"
namespace ex = std::execution;

auto a = ex::just(1, 2.0);                 // set_value_t(int, double)
auto b = ex::just_error(std::make_error_code(std::errc::io_error));
                                           // set_error_t(std::error_code)
auto c = ex::just_stopped();               // set_stopped_t()
// ex::just_error();                       // error: 需要恰好一个实参
// ex::just_stopped(1);                    // error: 不接受实参
// int arr[3]; ex::just(arr);              // error: 数组不满足 movable-value
auto [x, y] = std::this_thread::sync_wait(a).value();   // x == 1, y == 2.0
```

¶1 这三个工厂产生的异步操作在启动操作内同步完成，分别以值、错误、取消完成。

¶2 下列情况下 *just-cpo*(ts...) 非良构 {{ill-formed}}（*just-cpo* 指三者之一）：

- ¶2.1 某个实参类型不满足 *movable-value*：退化（decay）后的类型不可移动构造或不能从实参构造，或者实参是数组（[[exec.general]]）；
- ¶2.2 `just_error` 的实参不是恰好一个；
- ¶2.3 `just_stopped` 有实参。

否则它等价于 *make-sender*(*just-cpo*, *product-type*{ts...})：实参被复制或移动进发送器里的一个元组。*impls-for* 只覆盖了 *start*：

```cpp
template<>
struct impls-for<decayed-typeof<just-cpo>> : default-impls {
  static constexpr auto start = [](auto& state, auto& rcvr) noexcept -> void {
    auto& [...ts] = state;
    set-cpo(std::move(rcvr), std::move(ts)...);
  };
};
```

*set-cpo* 分别是 `set_value`、`set_error`、`set_stopped`。从这几行可以读出 `just` 的几个性质：

- 值的流向是：构造时存进发送器，connect 时复制或移动进操作状态，`start` 时移动给接收器。所以 `just(std::string("hi"))` 的签名是 `set_value_t(std::string)`，以右值发出。
- 标准算法的签名由 `start` 中潜在求值的完成调用决定（[[exec.snd]]）。这里的实参是 xvalue，所以签名是 `set_value_t(decay_t<Ts>...)`。
- `just(1)` 的签名只有 `set_value_t(int)`，没有 error 和 stopped。`start` 不可能失败，数据在 connect 时就准备好了；复制数据如果抛异常，是 `connect` 抛出异常，而不是操作以错误完成。
- `just()` 不带值，签名是 `set_value_t()`，常用作什么也不做的起点。例如 `starts_on` 降级后的形式里就有 `continues_on(just(), sch)`（[[exec.on]]）。

`start(op)` 返回之前，接收器的 `set_value` 已经被调用并返回了。这就是 [[exec.async.ops#2]] 注 1 说的异步操作可以同步执行。因此 `just` 的属性回答完成调度器时，给出的是环境里的 `get_scheduler`：它在调用 `start` 的地方完成（*inline-attrs*，见 [[exec.snd]]）。

## read_env [exec.read.env]

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

¶1 `read_env` 产生的发送器在启动操作内同步完成，值完成的结果是从接收器的环境里读出的一个值。它让一条发送器链能看到自己的执行环境：调度器、停止令牌、分配器等。

¶2 `read_env(q)`（`q` 是查询对象）等价于 *make-sender*(read_env, q)。

¶3 *impls-for* 覆盖了 *start* 和 *check-types*：

```cpp
static constexpr auto start = [](auto query, auto& rcvr) noexcept -> void {
  TRY-SET-VALUE(rcvr, query(get_env(rcvr)));
};
```

*TRY-SET-VALUE* 在表达式可能抛异常时包一层 `try`，把异常变成 `set_error(exception_ptr)`。查询本身必须是 noexcept 的；可能抛异常的是把查询结果作为实参传给 `set_value` 时的复制。

¶4–5 *check-types* 检查查询能否回答：设 `Q` 是查询对象的类型，如果 `Q()(env)` 非良构或者类型为 `void`，就抛出一个未指定类型的异常，计算签名因此失败。

!!! lawyer "read_env 和依赖发送器"
    `read_env(get_scheduler)` 的值类型取决于环境，直觉上它应当是依赖发送器：不给环境时报告 `dependent_sender_error`（[[exec.async.ops#13]]）。按草案字面却不是这样。

    1. 不带环境调用 `get_completion_signatures<S>()` 时，转到 *basic-sender* 的静态成员（[[exec.getcomplsigs#3]]）。
    2. 该成员在没有环境时用 `env<>` 运行 *check-types*（[[exec.snd]] 的 *basic-sender* 部分，第 47 段）。
    3. `get_scheduler(env<>)` 非良构，按 ¶5 抛出的是一个普通的未指定异常，不是 `dependent_sender_error`。

    结果是这个发送器既不满足 `dependent_sender`，也不满足 `sender_in`，*make-sender* 的 *Mandates* 不成立，`read_env(get_scheduler)` 这个表达式本身就非良构。这与 `read_env` 的用途相违背，应当看作措辞上的缺口，实际行为以实现为准。

    `read_env(std::get_stop_token)` 有另一个问题：`get_stop_token(env<>)` 良构，返回 `never_stop_token`，于是无环境时报告的签名是 `set_value_t(never_stop_token)`。带环境时值类型可能是 `inplace_stop_token`，两者不构成 [[exec.getcomplsigs#4]] 要求的超集关系。

## 思考题

!!! question "1. just 的数据被复制几次？"
    `auto s = just(std::string(1000, 'x')); sync_wait(s);`（以左值 `s` 调用）。从构造 `s` 到 `sync_wait` 的接收器收到字符串，`std::string` 被复制或移动了几次？

<details markdown="1">
<summary>答案</summary>

按阐述代码推演（实现可以不同）：

1. `just(std::string(...))`：临时字符串移动进 *product-type*，再进入 *basic-sender*。借助直接列表初始化，实现可以把它合并为一次移动。
2. `sync_wait(s)` 以左值 connect：*get-state* 用 `forward_like<Sndr>(data)` 取出数据，`Sndr` 是左值引用类型，于是数据被复制一次进操作状态。
3. `start`：`set_value(std::move(rcvr), std::move(ts)...)` 以右值交给 `sync_wait` 的接收器，它再移动一次进 `optional<tuple<string>>`。

所以至少一次复制、若干次移动。改成 `sync_wait(std::move(s))`，第 2 步也变成移动，全程没有复制。
</details>

!!! question "2. just_error(42) 合法吗？"
    错误类型可以是 `int` 吗？`sync_wait(just_error(42))` 会怎样？

<details markdown="1">
<summary>答案</summary>

合法：错误完成的数据可以是任意对象类型（[[exec.cmplsig]]），签名是 `set_error_t(int)`。`sync_wait` 收到错误时用 *AS-EXCEPT-PTR*（[[exec.general]]）把它变成 `exception_ptr`：`int` 既不是 `exception_ptr` 也不是 `error_code`，所以得到 `make_exception_ptr(42)`，随后重新抛出。`sync_wait` 抛出一个 `int`，可以用 `catch (int)` 捕获。
</details>
