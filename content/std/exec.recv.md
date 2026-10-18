---
title: 接收器
summary: receiver 概念（选择加入的标签、可查询的环境、可无异常移动、非 final）；receiver-of 检查完成签名；停止令牌在异步生存期内有效；inlinable_receiver 与"内联接收器"；set_value / set_error / set_stopped 只接受非 const 右值且必须 noexcept
status: done
covers: *
papers: P2300R10
related: exec.async.ops, exec.opstate, exec.snd, exec.connect, exec.cmplsig, exec.queries, thread.stoptoken
tags: 标准库, std::execution, 接收器, 概念
updated: 2026-10-18
---

接收器是异步操作的**后续**（continuation）：操作做完了，结果交给谁、在环境里能查到什么。[[exec.async.ops#5]] 把它定义为"三个完成处理器的聚合，外加一个环境"。本节给出 `receiver` 概念、检查完成签名的 *receiver-of*、一条关于停止令牌生存期的要求、`inlinable_receiver` 这一较晚加入的空间优化，以及三个完成函数 `set_value`、`set_error`、`set_stopped`。

日常写代码很少直接写接收器——它们主要出现在**写发送器算法**的时候。但理解接收器的约束，才能看懂为什么发送器要那样写。

## receiver 概念（[exec.recv.concepts] ¶1）

```cpp
template<class Rcvr>
  concept receiver =
    derived_from<typename remove_cvref_t<Rcvr>::receiver_concept, receiver_tag> &&
    requires(const remove_cvref_t<Rcvr>& rcvr) {
      { get_env(rcvr) } -> queryable;
    } &&
    move_constructible<remove_cvref_t<Rcvr>> &&               // rvalues are movable, and
    constructible_from<remove_cvref_t<Rcvr>, Rcvr> &&         // lvalues are copyable, and
    is_nothrow_move_constructible_v<remove_cvref_t<Rcvr>>;    // no-throw-movable
```

- **`receiver_concept` 标签**：选择加入。注意概念**不检查**任何 `set_*` 成员——一个只声明了标签、什么完成都不接受的类型也满足 `receiver`。能接受哪些完成由 *receiver-of* 另行检查。
- **`get_env(rcvr)`** 对 const 接收器可用，结果可查询。没有 `get_env` 成员也没关系：`get_env` 默认返回 `env<>{}`（[[exec.get.env]]）。
- **可移动，且移动不抛异常**。为什么必须 nothrow？`connect` 要把接收器移进操作状态；适配器在完成路径上（noexcept 的 `set_value` 里）也常常需要移动接收器。如果移动可能抛异常，就会出现"完成过程中抛异常"——而这时已经无处报告错误了。
- `constructible_from<remove_cvref_t<Rcvr>, Rcvr>`：用 `Rcvr` 这个值类别能构造出一个副本（左值就要求可复制）。

```cpp title="print-receiver.cpp"
namespace ex = std::execution;

struct print_receiver {
  using receiver_concept = ex::receiver_tag;

  void set_value(int v) && noexcept           { std::println("value {}", v); }
  void set_error(std::exception_ptr) && noexcept { std::println("error"); }
  void set_stopped() && noexcept               { std::println("stopped"); }
  // 没有 get_env：环境是 env<>{}
};
static_assert(ex::receiver<print_receiver>);
```

注意三个成员都是 `&&` 限定、`noexcept`——这两点由下面的完成函数强制。

### receiver-of：能否接受一组完成签名

```cpp
template<class Signature, class Rcvr>
  concept valid-completion-for =
    requires (Signature* sig) {
      []<class Tag, class... Args>(Tag(*)(Args...))
          requires callable<Tag, remove_cvref_t<Rcvr>, Args...>
      {}(sig);
    };

template<class Rcvr, class Completions>
  concept has-completions =
    requires (Completions* completions) {
      []<valid-completion-for<Rcvr>...Sigs>(completion_signatures<Sigs...>*)
      {}(completions);
    };

template<class Rcvr, class Completions>
  concept receiver-of = receiver<Rcvr> && has-completions<Rcvr, Completions>;
```

用了两个"立即调用的泛型 lambda"技巧来做模式匹配：

1. *has-completions*：把 `Completions*` 传给一个只接受 `completion_signatures<Sigs...>*` 的 lambda，从而**拆出** `Sigs...`，并要求每个 `Sig` 满足 *valid-completion-for*；
2. *valid-completion-for*：把 `Sig*`（一个函数指针类型，如 `set_value_t(*)(int)`）传给接受 `Tag(*)(Args...)` 的 lambda，拆出 `Tag` 和 `Args...`，要求 `callable<Tag, remove_cvref_t<Rcvr>, Args...>`——即 `set_value(std::move(rcvr), args...)` 良构。

所以 *receiver-of*<R, completion_signatures<set_value_t(int), set_stopped_t()>> 检查的是 `set_value(R&&, int)` 和 `set_stopped(R&&)` 都能调用。这是 `connect` 的 *Mandates* 之一（[[exec.connect#6]]）：接收器必须能接受发送器可能发出的**每一种**完成。

¶2 被标记为 `final` 的类类型不模型化 `receiver`。这是**语义**要求，概念检查本身发现不了。标准没有说明理由；一个合理的解读是给实现留出**派生**自用户接收器的余地（例如利用空基类优化存储无状态的接收器），`final` 会堵死这条路。

## 停止令牌的有效期（[exec.recv.concepts] ¶3）

¶3 设 `token` 等于 `get_stop_token(get_env(rcvr))`。`token` 必须在异步操作的**生存期**（[[exec.async.ops#7]]）内保持有效。

注 1 指出两个推论：

- 除非知道 `rcvr` 的类型提供了更多保证，操作状态在执行完成操作**之后**不能再使用 `token`；
- 在 `token` 上注册的停止回调，必须在调用完成操作**之前**销毁。

第二条是实现者最容易踩的坑。典型写法：

```cpp title="stop-callback-order.cpp"
void complete_value(T v) noexcept {
  stop_cb_.reset();                                    // 1. 先注销回调
  ex::set_value(std::move(rcvr_), std::move(v));       // 2. 再完成
}
```

顺序反过来就错了：`set_value` 一开始，异步生存期就结束了，提供令牌的那一方（比如 `when_all` 的 `inplace_stop_source`，或 `sync_wait` 的调用者）可能立刻销毁 stop source，此时 `stop_cb_` 的析构函数去访问一个已经不存在的 stop state。标准的 `when_all` 阐述代码在每个完成分支里都先写 `on_stop.reset();`（[[exec.when.all]]），就是这个原因。

## inlinable_receiver 与内联接收器（[exec.recv.concepts] ¶4–9）

```cpp
template<class Rcvr, class ChildOp>
  concept inlinable_receiver = receiver<Rcvr> &&
    requires (ChildOp* child) {
      { remove_cvref_t<Rcvr>::make_receiver_for(child) } noexcept
        -> same_as<remove_cvref_t<Rcvr>>;
    };
```

这是一项**空间优化**。考虑 `then(then(then(s, f), g), h)`：最内层的操作状态存着一个接收器，这个接收器通常就是一个指向外层操作状态的指针。一层一个指针，嵌套越深浪费越多。而子操作状态**就嵌在**父操作状态里——父操作状态的地址可以从子操作状态的地址算出来。所以接收器其实**不必存**：需要时用子操作状态的地址现场重建即可。

¶4 `inlinable_receiver<Rcvr, ChildOp>` 描述这种可以"由操作状态地址按需重建"的接收器：`Rcvr::make_receiver_for(addressof(op))` 必须得到一个与原接收器**相等**（[[concepts.equality]]）的接收器。注 2：这样的接收器不必作为数据成员存在 `op` 里。`ChildOp` 可以是不完整类型（父操作状态在定义子操作状态成员时，子类型往往还不完整）。

¶5 **传递构造**（transitively constructed）：`On` 由 `O0` 传递构造，指类型相同，且 `O1` 由 decay-copy `O0` 的引用初始化，之后每个 `Ok` 都由前一个的非 const 右值引用初始化。直白地说：`O0` 被复制一次、再被移动若干次得到的所有对象。

¶6 [[g:inlines-the-receiver|**内联接收器**]]：若 `connect(sndr, rcvr)` 求值期间由 `rcvr` 传递构造出的所有对象，其生存期都在该求值内结束，则称这个 connect 表达式内联了接收器 `rcvr`。注 3：即操作状态里不存接收器。

¶7 若 `sndr` 是**标准定义**的发送器类型，且 `connect(sndr, rcvr)` 内联了接收器，那么在描述该操作的规范文字中，凡是指代"由 `rcvr` 传递构造的对象"的 glvalue，都改为指代对 `remove_cvref_t<decltype(rcvr)>::make_receiver_for(addressof(op))` 做临时量实质化转换的结果。也就是说，本章到处写的 `std::move(rcvr)`，在内联情况下读作"现场造一个接收器"。

¶8 对标准库定义的接收器类型，它是否模型化 `inlinable_receiver<Op>` 是**未指定**的 {{unspec}}。

¶9 若 `Rcvr` 模型化 `inlinable_receiver<StdOp>`（`StdOp` 是标准的操作状态类型），那么产生 `StdOp` 的 connect 是否内联接收器，是**实现定义**的 {{impl}}。

!!! lawyer "为什么 ¶8 是 unspecified 而 ¶9 是 implementation-defined？"
    ¶8 关心的是标准**接收器**是否提供这种能力：这是实现细节，不值得要求实现写文档，所以是 unspecified。¶9 关心的是你**自己的**接收器满足了 `inlinable_receiver` 之后，标准**操作状态**会不会利用它：这会影响你的接收器对象是否真的被存储（从而影响它的副作用、地址是否稳定），所以要求实现说明。写 `make_receiver_for` 的人要保证：无论实现选择存还是不存，行为都一样——因为 ¶4 要求重建出的接收器与原来的**相等**。

## 三个完成函数（[exec.set.value]、[exec.set.error]、[exec.set.stopped]）

三者的规定结构完全一样：

| CPO | 完成标签 | 表达式 | 等价于 |
|---|---|---|---|
| `set_value` | `set_value_t` | `set_value(rcvr, vs...)` | *MANDATE-NOTHROW*(rcvr.set_value(vs...)) |
| `set_error` | `set_error_t` | `set_error(rcvr, err)` | *MANDATE-NOTHROW*(rcvr.set_error(err)) |
| `set_stopped` | `set_stopped_t` | `set_stopped(rcvr)` | *MANDATE-NOTHROW*(rcvr.set_stopped()) |

每一个都有两条附加规则：

1. **若 `rcvr` 是左值或 const 右值，表达式非良构** {{ill-formed}}。
2. *Mandates*：成员调用若良构，类型是 `void`；并且（*MANDATE-NOTHROW*）必须是 noexcept 的。

第 1 条在语言层面编码了"恰好完成一次"（[[exec.async.ops#8]]）：完成一个接收器就是**消耗**它，所以必须写 `std::move(rcvr)`。这样一来，"完成之后又用了 `rcvr`"会表现为"使用了已被移动的对象"，代码审查和静态分析都更容易发现。

```cpp title="set-value-rvalue.cpp"
void complete(print_receiver& r) {
  namespace ex = std::execution;
  ex::set_value(r, 1);              // error: r 是左值
  ex::set_value(std::move(r), 1);   // OK
  const print_receiver cr{};
  ex::set_value(std::move(cr), 1);  // error: const 右值
}
```

由于成员 `set_value` 是通过一个右值 `rcvr` 调用的，接收器的成员可以写成 `&&` 限定（推荐），也可以不加限定；但不能只提供 `&` 限定的版本。

!!! note "set_error 只有一个错误实参"
    `set_error(rcvr, err)` 恰好两个实参，对应 [[exec.async.ops#2]] 中"error 完成恰有一个结果数据"。`set_stopped(rcvr)` 只有接收器，对应"stopped 完成没有数据"。`set_value` 可以带任意多个值。

## 陷阱

!!! pitfall "在 set_value 里抛异常"
    接收器的 `set_value` 必须是 noexcept（否则 `set_value(...)` 表达式非良构）。如果处理值的过程中可能出错，接收器应该自己捕获并转发：对自己持有的下游接收器调用 `set_error`。标准的 *TRY-SET-VALUE*（[[exec.snd]]）就是这个模式的阐述版本。

!!! pitfall "把接收器标记为 final"
    `struct my_rcvr final { using receiver_concept = receiver_tag; ... };` 能通过 `static_assert(receiver<my_rcvr>)`，但违反 ¶2 的语义要求——程序没有满足概念的模型要求，标准对此不保证任何东西。

## 思考题

!!! question "1. 一个没有任何 set_* 成员的接收器"
    `struct R { using receiver_concept = receiver_tag; };` 满足 `receiver` 吗？它能和 `just()` connect 吗？

<details markdown="1">
<summary>答案</summary>

满足 `receiver`：标签有了，`get_env` 默认返回 `env<>{}`，可无异常移动。但不能和 `just()` connect：`just()` 的完成签名是 `completion_signatures<set_value_t()>`，*receiver-of*<R, ...> 要求 `set_value(R&&)` 良构，而 `R` 没有 `set_value` 成员。[[exec.connect]] 的 *Mandates* 不满足，程序非良构。它可以和 `just_stopped()`、`just_error(x)` connect 吗？同样不行，它没有对应成员。只有一个永远不完成的发送器才会接受它——而按 [[exec.async.ops#8]]，启动后的操作必须完成，所以这样的组合没有实际用途。
</details>

!!! question "2. 停止回调与完成的顺序"
    一个发送器在 `start` 里构造了 `stop_callback_for_t<Token, F>`，在 `set_value` 之后才在操作状态的析构函数里销毁它。这违反了什么？什么时候会真的出问题？

<details markdown="1">
<summary>答案</summary>

违反 [exec.recv.concepts] ¶3：令牌只保证在异步生存期内有效，而异步生存期在完成操作**开始**时就结束了；注 1 明确要求回调在完成之前销毁。问题会在令牌的提供者于完成之后立即销毁 stop source 时暴露：比如 `when_all` 的最后一个子操作完成后，`when_all` 自己完成，外层随即销毁整个操作状态（包括 `inplace_stop_source`）。此时子操作状态析构时注销回调，访问的是已经销毁的 stop state——典型的 use-after-free。
</details>

## 小结

- `receiver`：`receiver_concept` 标签 + 可查询的 `get_env` + 可无异常移动；不检查 `set_*`；不能是 `final`。
- *receiver-of*：对每个完成签名检查 `Tag(std::move(rcvr), args...)` 可调用。
- 停止令牌只在异步生存期内有效；回调须在完成前注销。
- `inlinable_receiver`：可由操作状态地址重建的接收器，实现可以不存储它。
- `set_value`/`set_error`/`set_stopped`：只接受非 const 右值接收器，返回 `void`，必须 noexcept。
