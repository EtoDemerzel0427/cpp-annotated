---
title: 切换执行资源
summary: 三个"换地方"的适配器——starts_on(sch, s) 在 sch 上启动 s；continues_on(s, sch) 在 s 完成后跳到 sch 上再完成（结果先存下来）；on 两种形式：去 sch 上做完再回来、或者先跳过去做一段闭包再回来；schedule_from 是供调度器定制"离开"方式的钩子
status: done
covers: exec.starts.on, exec.continues.on, exec.schedule.from
papers: P2300R10
related: exec.adapt, exec.sched, exec.let, exec.queries, exec.snd.transform, exec.task
tags: 标准库, std::execution, 发送器适配器, 调度器
updated: 2026-10-18
---

[[exec.async.ops#2]] ¶2.4 说异步操作可以在与启动处**不同**的执行资源上完成。这一组适配器就是用来**主动**控制"在哪里开始、在哪里继续"的。

| 适配器 | 含义 | 一句话 |
|---|---|---|
| `starts_on(sch, s)` | 在 `sch` 上**启动** `s` | 去那里干活 |
| `continues_on(s, sch)` | `s` 完成后，**转到** `sch` 上把结果交出去 | 干完活跳到那里 |
| `on(sch, s)` | 在 `sch` 上做完 `s`，再**回到**原来的地方 | 去那里干完活再回来 |
| `on(s, sch, closure)` | `s` 完成后跳到 `sch` 上执行 `closure`，再回到 `s` 完成的地方 | 中途借用一下别处 |
| `schedule_from(s)` | 供调度器定制"离开"自己的方式 | 实现者用的钩子 |

注意实参顺序：`starts_on` 调度器在前，`continues_on` 发送器在前，与"先后"一致。

## starts_on（[exec.starts.on]）

¶1 把一个输入发送器适配成"将在某调度器的执行资源的执行代理上**启动**"的发送器。

¶2–3 `sch` 不是调度器或 `sndr` 不是发送器时非良构；否则 *make-sender*(starts_on, sch, sndr)。

¶4 `starts_on` 没有自己的 *impls-for*；它在 `transform_sender` 的 `set_value` 阶段（[[exec.snd.transform]]）降级为：

```cpp
auto&& [_, sch, sndr] = out_sndr;
return let_value(
  continues_on(just(), sch),
  [sndr = std::forward_like<OutSndr>(sndr)]() mutable
    noexcept(is_nothrow_move_constructible_v<decay_t<OutSndr>>) {
    return std::move(sndr);
  });
```

拆开读：`continues_on(just(), sch)` 是"跳到 `sch` 上，然后以 `set_value()` 完成"；`let_value` 在那之后调用回调得到 `sndr`，并在**当前位置**（即 `sch` 上）connect、start 它（[[exec.let]]）。于是 `sndr` 在 `sch` 上被启动。`let_value` 还会把前驱的完成调度器 `sch` 通过 *SCHED-ENV* 作为 `get_start_scheduler` 放进 `sndr` 的环境——`sndr` 知道自己在 `sch` 上启动。

¶5 语义要求：`start(op)` 必须在 `sch` 的执行资源的代理上启动 `sndr`。若调度到 `sch` 失败，在**未指定**的执行代理上对外部接收器执行 error 完成。

`starts_on` **不**负责完成后回来：`sndr` 在哪完成，整个 `starts_on` 就在哪完成。

## continues_on（[exec.continues.on]）

¶1 把依赖于某个发送器完成的工作调度到一个调度器的执行资源上。

¶2–3 `continues_on(sndr, sch)` 等价于 *make-sender*(continues_on, sch, **schedule_from(sndr)**)——子发送器被包了一层 `schedule_from`（见下）。

它是这组适配器里唯一一个有完整 *impls-for* 实现的，值得细看：

¶5 *get-state* 在 connect 时**预先** connect 好 `schedule(sch)`：

```cpp
struct state-type {
  Rcvr& rcvr;                 // 外部接收器
  variant_t async-result;     // 存子发送器的结果
  operation_t op-state;       // connect(schedule(sch), receiver_t{this}) 的结果
};
```

¶8 `variant_t` 是 `variant<monostate, as-tuple<Sigs>..., error-completion...>`（去重）：子发送器每种可能的完成，都对应一个 `tuple<Tag, decay_t<Args>...>`；若某些结果数据的 decay-copy 可能抛异常，再加一个 `tuple<set_error_t, exception_ptr>`。

¶11 *complete*：子发送器完成时

```cpp
try {
  state.async-result.template emplace<decayed-tuple<Tag, Args...>>(Tag(), std::forward<Args>(args)...);
} catch (...) {
  if constexpr (!nothrow)
    state.async-result.template emplace<tuple<set_error_t, exception_ptr>>(set_error, current_exception());
}
start(state.op-state);
```

先把结果（连同完成标签）**存下来**，再启动预先 connect 好的调度操作。

¶9 调度操作的接收器 *receiver-type*：

- `set_value()`（调度成功，现在在 `sch` 上了）：`visit` 存下的结果，`auto& [tag, ...args] = result; tag(std::move(state->rcvr), std::move(args)...);`——用存下的标签和数据完成外部接收器；
- `set_error(err)`：调度失败，直接把错误转给外部接收器；
- `set_stopped()`：调度被取消，直接 `set_stopped` 外部接收器。

注意 visit 里 `if constexpr (!same_as<monostate, Tuple>)`：理论上 `async-result` 此时不会是 `monostate`，因为调度操作只在子发送器完成之后才被启动。

¶6 *check-types*：调度发送器在环境下要有签名；子发送器的结果数据必须都能 decay-copy（因为要存起来）。

¶12 语义要求：`start(op)` 在**当前**执行代理上启动 `sndr`，在 `sch` 的执行资源的代理上执行对外部接收器的完成。调度失败时，在未指定的代理上执行 error 完成。

!!! note "结果在中转时被复制了一次"
    `continues_on` 必须把子发送器的结果**存起来**：子操作在资源 A 上完成，结果要等到 B 上的调度操作完成后才交出去，而子操作的完成函数一返回，它传过来的引用就可能失效。所以签名里的引用类型会变成值类型：子发送器的 `set_value_t(const std::string&)`，经过 `continues_on` 后变成 `set_value_t(std::string)`（`std::move(args)...` 发出右值）。这也是 *check-types* 要求结果可 decay-copy 的原因。

!!! warning "error 与 stopped 也会经过一次调度"
    子发送器以 error 或 stopped 完成时，同样被存进 `async-result`，等调度到 `sch` 之后才转发。也就是说 `continues_on` 保证**所有**完成都在 `sch` 上发生（调度本身失败的情况除外）。这让 `continues_on` 的三种完成调度器都可以报告为 `sch`——只要调度本身是 *infallible* 的。

## schedule_from（[exec.schedule.from]）

¶1 `schedule_from(sndr)` 等价于 *make-sender*(schedule_from, {}, sndr)。它没有专门的 *impls-for*，用的是 *default-impls*——即**原样透传**子发送器的完成。

注 1：`schedule_from` 供调度器控制"如何**离开**其执行上下文"。

为什么需要它？`continues_on(sndr, sch)` 涉及**两个**执行资源：`sndr` 完成的地方（源）和 `sch`（目标）。domain 定制按"完成 domain"选择实现（[[exec.snd.transform]]）：

- `continues_on` 外层发送器的完成 domain 是**目标** `sch` 的 domain——目标调度器可以定制 `continues_on`，控制"如何**进入**"；
- 内层 `schedule_from(sndr)` 的完成 domain 是**源**的 domain——源一侧的调度器可以定制 `schedule_from`，控制"如何**离开**"。

例如，`sndr` 在 GPU 上完成，转到 CPU 线程池：GPU 一侧可能需要先同步设备流、把结果拷回主机内存，这件事由 GPU domain 对 `schedule_from` 的定制来完成；线程池一侧负责入队。两边各管一半，互不需要认识对方。

## on（[exec.on]）

¶1 两种形式：

- ¶1.1 `on(sch, sndr)`：在 `sch` 的执行资源上启动 `sndr`，`sndr` 完成后**把执行转回** `on` 发送器被启动时所在的执行资源；
- ¶1.2 `on(sndr, sch, closure)`：`sndr` 完成后，转到 `sch` 上，以 `sndr` 的异步结果执行发送器适配器闭包 `closure`，然后转回 `sndr` 完成时所在的执行资源。

¶2–4 合法性检查：`sch` 必须是调度器；第一种形式的 `sndr` 必须是发送器、且**不能同时**是闭包对象；第二种形式的 `closure` 必须是可管道化发送器适配器闭包对象（[[exec.adapt]]）。第一种形式的 `sndr` 也可以是一个闭包对象而非发送器——这时 `on(sch, closure)` 本身返回一个闭包（`on` 是可管道化适配器对象），配合管道写成 `sndr | on(sch, closure)`，即第二种形式。

¶6 降级（`set_value` 阶段的 `transform_sender`）：

```cpp
auto&& [_, data, child] = out_sndr;
if constexpr (scheduler<decltype(data)>) {
  auto orig_sch = call-with-default(get_start_scheduler, not-a-scheduler(), env);
  return continues_on(
    starts_on(std::forward_like<OutSndr>(data), std::forward_like<OutSndr>(child)),
    std::move(orig_sch));
} else {
  auto& [sch, closure] = data;
  auto orig_sch = call-with-default(
    get_completion_scheduler<set_value_t>, not-a-scheduler(), get_env(child), env);
  return continues_on(
    std::forward_like<OutSndr>(closure)(continues_on(std::forward_like<OutSndr>(child), sch)),
    orig_sch);
}
```

- 第一种：`continues_on(starts_on(sch, sndr), orig_sch)`，`orig_sch` 来自**接收器环境**的 `get_start_scheduler`——"我被启动的地方"。
- 第二种：`continues_on(closure(continues_on(sndr, sch)), orig_sch)`，`orig_sch` 是 `sndr` 的 **value 完成调度器**——"`sndr` 完成的地方"。

取不到原调度器时用 *not-a-scheduler*：它的 `schedule()` 返回 *not-a-sender*，后者的 `get_completion_signatures` 抛异常——于是在计算签名时报错（"`on` 不知道要回到哪里"），而不是在运行时。

¶7 第一种形式的语义：`start(op)` 应当
- ¶7.1 记住当前调度器 `get_start_scheduler(get_env(rcvr))`；
- ¶7.2 在 `sch` 上启动 `sndr`；
- ¶7.3 `sndr` 完成后把执行转回 ¶7.1 记住的调度器；
- ¶7.4 把 `sndr` 的异步结果转发给外部接收器。

¶8 第二种形式类似：记住 `sndr` 的 value 完成调度器；在当前代理上启动 `sndr`；完成后转到 `sch`；以"同步地发出 `sndr` 结果的发送器 S"构造 `closure(S)` 并启动；完成后转回记住的调度器并转发结果。任何调度失败都在未指定的代理上以 error 完成。

```cpp title="on.cpp"
namespace ex = std::execution;

ex::sender auto ui_task(ex::scheduler auto ui, ex::scheduler auto pool) {
  return ex::just(load_request())
       | ex::on(pool, ex::then([](auto req) { return parse(req); }))   // 去线程池解析，再回来
       | ex::then([](auto doc) { show(doc); });                         // 回到 load_request 完成的地方
}
```

!!! pitfall "on(sch, s) 需要知道“原地”"
    第一种形式依赖接收器环境回答 `get_start_scheduler`。`sync_wait` 的环境回答它（[[exec.consumers]]），`task` 的承诺类型也回答（[[exec.task]]）；但若你自己写的接收器环境不提供它，`on(sch, s)` 在 connect 时就会因 *not-a-scheduler* 而在签名计算阶段失败。这正是"不知道该回到哪里"在类型层面的体现。

## 思考题

!!! question "1. starts_on 之后在哪完成？"
    `starts_on(pool, just(1) | then(f))`，`f` 在哪执行？整个发送器在哪里完成？与 `on(pool, just(1) | then(f))` 有何区别？

<details markdown="1">
<summary>答案</summary>

`just(1) | then(f)` 在 `pool` 上被启动；`just` 同步完成，`f` 在同一个线程上执行，整个 `starts_on` 也就在 `pool` 的线程上完成。`on(pool, ...)` 多了一步：完成后 `continues_on` 回到外部 `get_start_scheduler` 给出的调度器（比如 `sync_wait` 的 `run_loop`），于是外部接收器在原线程上收到结果。区别只在"完成后回不回来"。
</details>

!!! question "2. continues_on 改变了签名吗？"
    子发送器签名 `set_value_t(int&)`（以左值引用发出一个 int）。`continues_on(s, sch)` 的签名是什么？

<details markdown="1">
<summary>答案</summary>

`variant_t` 存的是 `decayed-tuple<set_value_t, int&>` = `tuple<set_value_t, int>`，完成时 `tag(std::move(rcvr), std::move(args)...)` 发出 `int&&`，于是 value 签名是 `set_value_t(int)`。若 decay-copy 可能抛异常还会多 `set_error_t(exception_ptr)`（`int` 不会）；再加上调度发送器本身的 error/stopped 签名（取决于 `sch`）。引用被"值化"了——这正是跨执行资源中转数据的代价，也是安全的保证。
</details>

## 小结

- `starts_on(sch, s)`：降级为 `let_value(continues_on(just(), sch), [s]{ return s; })`；`s` 在 `sch` 上启动，在哪完成就在哪交出结果。
- `continues_on(s, sch)`：预先 connect 调度操作；子发送器完成时**存下**结果，调度到 `sch` 后再交出；所有处置都经过这次中转。
- `schedule_from(s)`：透传；供源一侧的 domain 定制"如何离开"。
- `on(sch, s)` = `continues_on(starts_on(sch, s), 启动调度器)`；`on(s, sch, closure)` = `continues_on(closure(continues_on(s, sch)), s 的完成调度器)`。
