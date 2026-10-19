---
title: 切换执行资源
summary: 三个控制工作在哪里运行的适配器：starts_on(sch, s) 在 sch 上启动 s；continues_on(s, sch) 在 s 完成后把结果存下、跳到 sch 上再交出；on 去 sch 上做完再回到原处；schedule_from 是供调度器定制如何离开自己的钩子。
status: draft
covers: exec.starts.on, exec.continues.on, exec.schedule.from
papers: P2300R10
related: exec.adapt, exec.sched, exec.let, exec.queries, exec.snd.transform, exec.task
tags: 标准库, std::execution, 发送器适配器, 调度器
updated: 2026-10-19
---

!!! tldr
    - `starts_on(sch, s)` 在 `sch` 上启动 `s`，`s` 在哪里完成，整个操作就在哪里完成。
    - `continues_on(s, sch)` 在 `s` 完成后把结果存起来，调度到 `sch` 上再交给接收器。值、错误、取消三种完成都经过这次中转，引用类型的结果会变成值。
    - `on(sch, s)` 去 `sch` 上做完 `s`，再回到操作被启动的地方；`s | on(sch, closure)` 在 `sch` 上执行一段闭包，再回到 `s` 完成的地方。
    - `on` 需要知道原来的调度器；环境里取不到时，在计算签名时就报错。
    - `schedule_from` 把 `continues_on` 拆成离开和进入两半，源一侧和目标一侧的调度器可以各自定制。

本页的例子没有经过编译验证：本机 Clang 23 附带的 libc++ 还没有实现 `std::execution` 的发送器部分，所以不加判定标记。

## 在哪里开始、在哪里继续

异步操作可以在一个执行资源上启动，在另一个上完成（[[exec.async.ops#2]]）。下面这组适配器让程序主动控制这一点：

| 适配器 | 含义 |
|---|---|
| `starts_on(sch, s)` | 在 `sch` 上启动 `s` |
| `continues_on(s, sch)` | `s` 完成后，转到 `sch` 上把结果交出去 |
| `on(sch, s)` | 在 `sch` 上做完 `s`，再回到原来的地方 |
| `on(s, sch, closure)` | `s` 完成后转到 `sch` 上执行 `closure`，再回到 `s` 完成的地方 |
| `schedule_from(s)` | 供调度器定制如何离开自己，一般用户不直接调用 |

注意实参顺序与先后一致：`starts_on` 调度器在前，`continues_on` 发送器在前。

```cpp title="on.cpp"
namespace ex = std::execution;

ex::sender auto handle(ex::scheduler auto pool) {
  return ex::just(load_request())
       | ex::on(pool, ex::then([](auto req) { return parse(req); }))  // 去线程池解析，再回来
       | ex::then([](auto doc) { show(doc); });                        // 回到 just 完成的地方
}
```

`just` 在调用 `start` 的地方同步完成。`on` 把解析工作送到 `pool` 上，解析完再回到那里，`show` 因此和 `just` 在同一处执行。

## starts_on [exec.starts.on]

¶1 `starts_on` 把输入发送器适配成一个将在某个[[g:scheduler|调度器]]的执行资源上启动的发送器。

¶2–3 `sch` 不是调度器或 `sndr` 不是发送器时非良构；否则等价于 *make-sender*(starts_on, sch, sndr)。

¶4 `starts_on` 没有自己的实现。connect 时，`transform_sender`（[[exec.snd.transform]]）把它改写成其他适配器的组合：

```cpp
auto&& [_, sch, sndr] = out_sndr;
return let_value(
  continues_on(just(), sch),
  [sndr = std::forward_like<OutSndr>(sndr)]() mutable
    noexcept(is_nothrow_move_constructible_v<decay_t<OutSndr>>) {
    return std::move(sndr);
  });
```

`continues_on(just(), sch)` 跳到 `sch` 上，然后以 `set_value()` 完成。`let_value` 接着调用回调取得 `sndr`，在当前位置（也就是 `sch` 上）connect 并 start 它（[[exec.let]]）。`let_value` 还会把前驱的完成调度器 `sch` 作为 `get_start_scheduler` 的答案放进 `sndr` 的环境，所以 `sndr` 知道自己是在 `sch` 上启动的。

¶5 语义要求：`start(op)` 必须在 `sch` 的执行资源上启动 `sndr`。如果调度到 `sch` 失败，在一个未指定的执行代理上对外部接收器执行错误完成。

`starts_on` 不负责回来：`sndr` 在哪里完成，`starts_on` 就在哪里完成。

## continues_on [exec.continues.on]

¶1 `continues_on` 把依赖于某个发送器完成的工作调度到一个调度器的执行资源上。

¶2–3 `continues_on(sndr, sch)` 等价于 *make-sender*(continues_on, sch, schedule_from(sndr))，子发送器外面包了一层 `schedule_from`，原因见下一节。

它是这一组里唯一有完整 *impls-for* 实现的适配器（钩子的含义见 [[exec.snd]]），工作分三步。

¶5 第一步在 connect 时完成：*get-state* 预先 connect 好 `schedule(sch)`，状态里有三个成员：

```cpp
struct state-type {
  Rcvr& rcvr;                 // 外部接收器
  variant_t async-result;     // 子发送器的结果
  operation_t op-state;       // connect(schedule(sch), receiver_t{this}) 的结果
};
```

¶8 `variant_t` 是 `variant<monostate, ...>`，子发送器的每一种完成签名 `Tag(Args...)` 对应一个 `tuple<Tag, decay_t<Args>...>`，重复的类型去掉。如果某个结果在退化复制时可能抛异常，再加一个 `tuple<set_error_t, exception_ptr>`。

¶11 第二步在子发送器完成时：*complete* 先把完成标签和结果存进 `async-result`，再启动预先 connect 好的调度操作。存储时抛出的异常被捕获，存成 `set_error` 加 `exception_ptr`。

¶9 第三步在调度操作完成时，它的接收器：

- `set_value()`：调度成功，现在已经在 `sch` 上了。取出存下的标签和结果，`tag(std::move(rcvr), std::move(args)...)`，完成外部接收器；
- `set_error(err)`：调度失败，把错误转给外部接收器；
- `set_stopped()`：调度被取消，对外部接收器调用 `set_stopped`。

¶6 *check-types* 要求调度发送器在该环境下有签名，子发送器的结果都能退化复制，因为要存起来。

¶12 语义要求：`start(op)` 在当前执行代理上启动 `sndr`，在 `sch` 的执行资源上对外部接收器执行完成操作。调度失败时，在未指定的执行代理上执行错误完成。

结果必须存起来：子操作在资源 A 上完成，结果要等调度到 B 之后才交出去，而子操作的完成函数一返回，它传来的引用就可能失效。所以签名里的引用类型会变成值类型，子发送器的 `set_value_t(const std::string&)` 经过 `continues_on` 变成 `set_value_t(std::string)`。

错误和取消完成也存进 `async-result`，等调度到 `sch` 之后才转发。因此除调度本身失败的情况外，`continues_on` 的所有完成都发生在 `sch` 上。

## schedule_from [exec.schedule.from]

¶1 `schedule_from(sndr)` 等价于 *make-sender*(schedule_from, {}, sndr)。它没有专门的 *impls-for*，用的是默认实现，原样转发子发送器的完成。注 1 说明，它供调度器控制如何离开自己的执行上下文。

`continues_on(sndr, sch)` 涉及两个执行资源：`sndr` 完成的地方（源）和 `sch`（目标）。执行 domain 按完成 domain 选择实现（[[exec.snd.transform]]），这两层恰好对应两端：

- 外层 `continues_on` 的完成 domain 是目标 `sch` 的 domain，目标一侧可以定制 `continues_on`，控制如何进入；
- 内层 `schedule_from(sndr)` 的完成 domain 是源的 domain，源一侧可以定制 `schedule_from`，控制如何离开。

例如 `sndr` 在 GPU 上完成，要转到 CPU 线程池。GPU 一侧可能需要先同步设备流、把结果拷回主机内存，这由 GPU 的 domain 定制 `schedule_from` 完成；线程池一侧负责入队。两边各管一半，不需要认识对方。

## on [exec.on]

¶1 `on` 有两种形式：

- ¶1.1 `on(sch, sndr)`：在 `sch` 上启动 `sndr`，`sndr` 完成后把执行转回 `on` 发送器被启动时所在的执行资源；
- ¶1.2 `on(sndr, sch, closure)`：`sndr` 完成后转到 `sch` 上，以 `sndr` 的结果执行发送器适配器闭包 `closure`，然后转回 `sndr` 完成时所在的执行资源。

¶2–4 `sch` 必须是调度器。第一种形式的 `sndr` 必须是发送器，或者是一个闭包对象，但不能两者都是；第二种形式的 `closure` 必须是可管道化发送器适配器闭包对象（[[exec.adapt]]）。`on` 是可管道化适配器对象，所以 `on(sch, closure)` 少给了发送器，返回一个闭包，`sndr | on(sch, closure)` 就是第二种形式。

¶6 两种形式都在 connect 时被改写：

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

- 第一种是 `continues_on(starts_on(sch, sndr), orig_sch)`，`orig_sch` 取自接收器环境的 `get_start_scheduler`，即操作被启动的地方。
- 第二种是 `continues_on(closure(continues_on(sndr, sch)), orig_sch)`，`orig_sch` 是 `sndr` 的值完成调度器，即 `sndr` 完成的地方。

*call-with-default* 在调用不良构时返回给定的默认值（[[exec.snd]]）。取不到原调度器时用的是 *not-a-scheduler*：它的 `schedule()` 返回 *not-a-sender*，计算后者的签名会抛异常。于是 `on` 不知道该回到哪里这件事，在计算签名时就被报告出来，而不是留到运行时。

¶7 第一种形式的语义要求：`start(op)` 记住当前调度器（`get_start_scheduler(get_env(rcvr))`），在 `sch` 上启动 `sndr`，`sndr` 完成后转回记住的调度器，再把结果转发给外部接收器。

¶8 第二种形式类似：记住 `sndr` 的值完成调度器；在当前代理上启动 `sndr`；完成后转到 `sch`；构造 `closure(S)` 并启动它，其中 `S` 是一个同步发出 `sndr` 结果的发送器；它完成后转回记住的调度器，转发结果。

两种形式中，任何一次调度失败都在未指定的执行代理上以错误完成。

!!! pitfall "on(sch, s) 需要知道原来在哪里"
    第一种形式要求接收器环境能回答 `get_start_scheduler`。`sync_wait` 的环境能回答（[[exec.consumers]]），`task` 的承诺类型也能（[[exec.task]]）。自己写的接收器环境如果不提供它，`on(sch, s)` 在 connect 时就会因为 *not-a-scheduler* 而无法计算签名。

## 思考题

!!! question "1. starts_on 之后在哪里完成？"
    `starts_on(pool, just(1) | then(f))` 中 `f` 在哪里执行？整个发送器在哪里完成？与 `on(pool, just(1) | then(f))` 有什么区别？

<details markdown="1">
<summary>答案</summary>

`just(1) | then(f)` 在 `pool` 上启动；`just` 同步完成，`f` 在同一个线程上执行，整个 `starts_on` 也在 `pool` 的线程上完成。`on(pool, ...)` 多了一步：完成后经 `continues_on` 回到外部 `get_start_scheduler` 给出的调度器，比如 `sync_wait` 的 `run_loop`，外部接收器在原来的线程上收到结果。区别只在完成后回不回来。
</details>

!!! question "2. continues_on 改变了签名吗？"
    子发送器的签名是 `set_value_t(int&)`，以左值引用发出一个 `int`。`continues_on(s, sch)` 的签名是什么？

<details markdown="1">
<summary>答案</summary>

`variant_t` 存的是 `tuple<set_value_t, int>`，完成时 `tag(std::move(rcvr), std::move(args)...)` 发出 `int&&`，所以值签名是 `set_value_t(int)`。复制 `int` 不会抛异常，不会多出 `set_error_t(exception_ptr)`；此外还要加上调度发送器本身的错误和取消签名，取决于 `sch`。引用变成了值：这是跨执行资源转交数据的代价，也是安全的保证。
</details>
