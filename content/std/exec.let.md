---
title: let_value / let_error / let_stopped
summary: 前驱完成后，用它的结果调用回调得到一个新发送器，并立即 connect、start 这个发送器；结果被保存到第二个操作结束，可以安全地按引用使用。
status: draft
covers: exec.let
papers: P2300R10
related: exec.adapt, exec.on, exec.snd, exec.connect, exec.snd.transform, exec.opstate
tags: 标准库, std::execution, 发送器适配器, let_value
updated: 2026-10-19
---

!!! tldr
    - `then(f)` 接一个同步函数，`let_value(f)` 接一个异步步骤：`f` 返回一个发送器，它的完成就是整个操作的完成。
    - 前驱的结果被复制进 `let_value` 的操作状态，以左值传给 `f`，一直活到第二个操作完成，所以第二个发送器可以按引用使用它们。
    - 回调形参要写成引用才能用到这份存储；按值接收得到的是回调的局部副本。
    - 前驱与第二个操作的操作状态共用一个 `variant`，前驱在自己的完成函数内部就被销毁。
    - `let_error`、`let_stopped` 对错误、取消完成做同样的事；`let_stopped` 的回调必须是零参的。

本页的例子用到 C++26 的 `std::execution` 发送器。本机 Clang 23 附带的 libc++ 还没有实现这部分库，例子都没有经过编译验证，因此不加判定标记。

## 回调返回一个发送器

[[g:sender|发送器]]（sender）描述一项尚未开始的异步工作。`then(f)` 在前驱产生值之后同步地调用 `f`，`f` 的返回值就是新的结果。但下一步常常本身也是异步的，而且只有拿到上一步的结果才知道该做什么：读到请求之后才知道要查哪张表。

`let_value(f)` 解决这个问题。`f` 接受前驱的值，返回一个发送器；`let_value` 把这个发送器连接（connect）到一个接收器并启动（start），以它的完成作为整个操作的完成。用函数式编程的说法，`then` 相当于 `map`，`let_value` 相当于 `flat_map`。

```cpp title="let-value.cpp"
namespace ex = std::execution;

ex::sender auto handle(connection& conn) {
  return read_request(conn)                    // 完成为 set_value(request)
       | ex::let_value([&conn](request& req) { // req 是左值引用
           return query_db(req.table)          // 完成为 set_value(rows)
                | ex::then([&req](rows r) {    // 可以安全地引用 req
                    return make_response(req, r);
                  });
         });
}
```

`req` 引用的对象存放在 `let_value` 自己的[[g:operation-state|操作状态]]里，一直活到 `query_db(...) | then(...)` 这个操作完成。所以内层 lambda 按引用捕获 `req` 是安全的。后面讲操作状态时会看到这是怎么保证的。

## 构造：let_value(sndr, f)（¶1–4）

¶1 三个适配器分别把前驱的值完成、错误完成、取消完成变成一个新的子异步操作：把前驱的结果数据传给用户提供的可调用对象，由它返回一个新发送器，再 connect 并 start 这个发送器。

¶2 下文用 *set-cpo* 表示与适配器对应的完成函数：`let_value` 对应 `set_value`，`let_error` 对应 `set_error`，`let_stopped` 对应 `set_stopped`。其他两种完成不经过回调，原样转发给外部接收器。

¶3 这三个名字都是可管道的发送器适配器对象，既可以写 `let_value(sndr, f)`，也可以写 `sndr | let_value(f)`。`sndr` 不是发送器，或者 `f` 不能移动、复制成一个独立的值（不满足 *movable-value*）时，表达式非良构。

此外 `let_stopped(sndr, f)` 要求 `f` 能以零个实参调用。取消完成不携带数据，所以这一点在构造时就能检查，不必等到 connect。

¶4 满足以上条件时，结果是一个以 `f` 为数据、以 `sndr` 为子发送器的发送器（*make-sender*，见 [[exec.snd]]）。

## 操作状态：先存结果，再换操作（¶10–15）

connect 之后，整个操作的状态是一个 *let-state* 对象，主要有四个成员：

```cpp
struct let-state {           // 简化
  Fn fn;                     // 用户回调
  env_t env;                 // 第二个操作的环境，见下节
  ArgsVariant args;          // variant<monostate, decayed-tuple<前驱结果>...>
  OpsVariant ops;            // variant<monostate, 前驱操作, 第二个操作...>
};
```

¶12 `args` 能容纳前驱每一种对应完成的结果。例如前驱可能以 `set_value(int)` 或 `set_value(string, int)` 完成，`args` 就是 `variant<monostate, tuple<int>, tuple<string, int>>`。结果的类型都经过 decay，即去掉引用和 cv 限定。

¶13 `ops` 同时为前驱的操作状态和第二个操作的操作状态留了位置。第二个发送器的类型是用左值调用回调得到的类型，也就是 `f(decay_t<Args>&...)` 的返回类型；前驱有几种对应完成，就可能有几种第二个发送器。

¶10 构造 *let-state* 时，`ops` 里就地构造前驱的操作状态。¶15 启动整个操作，就是启动这个前驱操作。

### 前驱完成时发生了什么

前驱以对应的完成函数完成时，*impl* 依次执行下面五步（¶10 中的阐述代码，略作简化）：

```cpp
try {
  auto& tuple = args.emplace<args_t>(std::forward<Ts>(ts)...); // 1
  ops.emplace<monostate>();                                    // 2
  auto&& sndr = apply(std::move(fn), tuple);                   // 3
  auto& op = ops.emplace<op_t>(                                // 4
      emplace-from{[&] { return connect(sndr, receiver2{rcvr, env}); }});
  start(op);                                                   // 5
} catch (...) {
  if constexpr (!nothrow) set_error(std::move(rcvr), current_exception());
}
```

1. 把结果复制进 `args`。前驱传来的实参可能引用它自己操作状态里的对象，而下一步就要销毁那个操作状态，所以必须先复制。
2. 销毁前驱的操作状态，把 `ops` 置为 `monostate`。这一步发生在前驱调用完成函数的过程中。[[exec.async.ops#8]] 允许操作状态的生存期在完成操作执行期间结束，前驱调用完成函数之后也不再访问自己。
3. 调用回调。`tuple` 是左值，所以每个结果以 `decay_t<Args>&` 传入，回调的形参可以是 `T&`、`const T&` 或按值。
4. 在 `ops` 原来的位置上就地构造第二个操作状态。操作状态不能移动（[[exec.opstate]]），所以用 *emplace-from* 直接把 `connect` 的返回值构造到 `variant` 里。
5. 启动第二个操作。它完成时，*receiver2* 把完成原样转发给外部接收器。

其他两种完成不进入这五步，直接转发给外部接收器。

`ops` 用 `variant` 而不是两个独立成员，是因为前驱完成之后它的操作状态就没用了。两者共用一块存储，整个操作状态的大小是两者中较大的那个，而不是两者之和。一长串嵌套的 `let_value` 能因此省下不少空间。

### 异常

¶10 中的 `nothrow` 只有在三件事都不会抛异常时才为真：把结果复制进 `args`、调用回调、connect 第二个发送器。否则 `catch` 分支会把异常以 `set_error(exception_ptr)` 交给外部接收器，整个发送器的完成签名里也就多了一项 `set_error_t(exception_ptr)`。

完成签名在 connect 之前就要算出来，那时只知道接收器的环境类型。[[exec.connect#6]] 规定 connect 是否 noexcept 只能取决于环境类型，正是为了让这类计算成立。

## 第二个操作在哪里运行（¶2、¶8）

回调在前驱完成的地方被调用，第二个发送器也在那里 connect 和 start。如果前驱在线程池上完成，回调就在线程池的线程上运行。

¶2 *let-env* 把这一事实写进第二个操作的环境。它取下面第一个良构的结果：

- ¶2.1 前驱在对应完成上的[[g:completion-scheduler|完成调度器]]，作为第二个操作的 `get_start_scheduler`；
- ¶2.2 退而求其次，只提供前驱的完成 domain；
- ¶2.3 空环境 `env<>{}`。

¶8 第二个操作使用的接收器 *receiver2* 回答环境查询时，先查 *let-env* 的结果；查不到并且这是一个[[g:forwarding-query|转发查询]]，再查外部接收器的环境；否则查询非良构。于是 `on`、`affine_on`、`task` 这类需要知道自己在哪个调度器上启动的发送器，可以据此做出正确的决定。

## 类型检查（¶9）

¶9 计算完成签名时，*check-types* 对前驱每一种对应完成 `set-cpo(Ts...)` 检查：

- ¶9.1 每个 `Ts` 都能 decay-copy；
- ¶9.2 回调能以 `decay_t<Ts>&...` 调用；
- ¶9.3 回调的返回值是发送器；
- ¶9.4 有环境时，这个发送器在第二个操作的环境下能算出完成签名。

任何一项不满足，*check-types* 抛出异常。它在常量求值中执行，所以表现为编译错误。

## let_error 与 let_stopped

`let_error(f)` 在前驱以错误完成时，用 `f(err)` 返回的发送器继续，适合重试、降级到缓存。`let_stopped(f)` 在前驱被取消时，用 `f()` 返回的发送器继续。[[exec.adapt]] 中的 `stopped_as_optional` 和 `stopped_as_error` 都是用 `let_stopped` 实现的。

```cpp title="let-error-fallback.cpp"
namespace ex = std::execution;

auto fetch_with_fallback = fetch_remote()
  | ex::let_error([](auto&& err) {   // 远端失败时改读本地缓存
      return read_cache();
    });
```

如果前驱可能以几种错误类型完成，回调必须对每一种都能调用（¶9.2）。对不同错误返回的发送器类型可以不同，`ops` 为每一种都留了一个分支。

## 常见错误

### 按值接收，再返回引用它的发送器

<div class="compare" markdown="1">

```cpp
| ex::let_value([](request req) {
    return ex::just()
         | ex::then([&req] { use(req); });
  })
// UB：req 是回调的局部副本，
// 回调返回时就销毁了
```

```cpp
| ex::let_value([](request& req) {
    return ex::just()
         | ex::then([&req] { use(req); });
  })
// OK：req 引用 let_value 存储的对象，
// 活到第二个操作完成
```

</div>

`let_value` 只保证它自己存储的 `decay_t<Args>` 对象活到第二个操作结束。

### 以为回调在 connect 时调用

回调在前驱完成时调用，运行在前驱完成所在的执行代理上，这一点与 `then` 相同。第二个发送器的 connect 也发生在那时。回调里的代码需要考虑自己运行在哪个线程上；第二个发送器可以从环境的 `get_start_scheduler` 得知这一点。

## 思考题

!!! question "1. 两个操作状态为什么可以共用存储？"
    前驱的操作状态在它自己的完成函数内部被销毁。哪些规则允许这样做？

<details markdown="1">
<summary>答案</summary>

[[exec.async.ops#7]]：完成操作开始执行时，异步操作的生存期就结束了，前驱的实现此后不能再访问自己的操作状态。[[exec.async.ops#8]]：操作状态的生存期可以在完成操作执行期间结束。另外第 1 步先把结果复制进 `args`，即使前驱传来的实参引用了它操作状态内部的对象，销毁之后也不会悬空。
</details>

!!! question "2. 回调抛出异常"
    `let_value` 的回调抛出异常时，外部接收器收到什么？此时 `args` 和 `ops` 处于什么状态？

<details markdown="1">
<summary>答案</summary>

第 1 步已经把结果存进 `args`，第 2 步已经把 `ops` 置为 `monostate`，第 3 步抛出异常后进入 `catch`。回调没有声明 noexcept 时 `nothrow` 为假，外部接收器收到 `set_error(exception_ptr)`，完成签名里也有 `set_error_t(exception_ptr)`。之后 `args` 仍持有结果副本，`ops` 为 `monostate`，它们随整个操作状态一起销毁。

如果回调声明为 noexcept，复制和 connect 也都不抛异常，`catch` 中的 `set_error` 就不会被实例化，签名里也没有这一项。
</details>

## 小结

| 问题 | 答案 |
|---|---|
| 回调何时调用 | 前驱以对应完成函数完成时，在前驱完成的执行代理上 |
| 回调收到什么 | 存在操作状态里的结果副本，以左值传入 |
| 结果活多久 | 到第二个操作完成 |
| 存储开销 | 前驱与第二个操作共用一个 `variant` |
| 第二个操作的启动调度器 | 前驱的完成调度器（¶2.1） |
| 回调或 connect 抛异常 | 外部接收器收到 `set_error(exception_ptr)` |

<details class="fine" markdown="1"><summary>其余条文</summary>

¶5–6 connect 之前，`let_value(sndr, f)` 被改写为一个内部发送器：标签是 *let-tag*（三个适配器各有一个私有的空类型），数据是 *let-data*`{sndr, f}`，没有子发送器。子发送器被挪进数据，是因为 `let` 要自己管理前驱的 connect（放进 `ops` 这个 `variant`），而不是交给通用的 *connect-all*。

¶7 *impls-for*<*let-tag*> 定制了 *get-state*、*start* 和 *check-types*，其余沿用默认实现。

¶11 *get-state* 从 *let-data* 中取出子发送器和回调，构造 *let-state*。¶14 它的约束是 `args_variant_t` 和 `ops_variant_t` 都良构。草案在这里写的是 `ops2_variant_t`，¶13 中并没有这个名字，应当是笔误。

¶16 如果 `let_value(sndr, f)` 被 domain 定制替换成了别的实现，这个实现仍须满足：`sndr` 以对应完成函数完成时调用 `f`；整个操作的完成取决于 `f` 返回的发送器的完成；`sndr` 的其他完成原样传播。否则 connect 的行为未定义。

</details>
