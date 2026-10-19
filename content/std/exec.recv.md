---
title: 接收器
summary: receiver 概念、检查完成签名的 receiver-of、停止令牌的有效期、可按需重建的 inlinable_receiver，以及三个完成函数 set_value、set_error、set_stopped。
status: draft
covers: *
papers: P2300R10
related: exec.async.ops, exec.opstate, exec.snd, exec.connect, exec.cmplsig, exec.queries, thread.stoptoken
tags: 标准库, std::execution, 接收器, 概念
updated: 2026-10-19
---

!!! tldr
    - 接收器是异步操作的后续：声明 `receiver_concept`，可以无异常地移动，`get_env` 给出它的环境；`final` 类不能当接收器。
    - `receiver` 概念不检查任何 `set_*` 成员；能否接受某组完成签名由 *receiver-of* 另行检查，`connect` 要求它成立。
    - 完成函数只接受非 const 右值接收器，必须返回 `void` 且 `noexcept`，所以完成接收器要写 `set_value(std::move(rcvr), ...)`。
    - 环境里的停止令牌只在异步生存期内有效，在它上面注册的停止回调必须在调用完成函数之前销毁。
    - `inlinable_receiver` 是一项空间优化：接收器可以从操作状态的地址重建，实现可以不存储它。

接收器（[[exec.async.ops#5]]）是三个完成处理器加一个环境：操作完成后结果交给谁，子操作在环境里能查到什么。日常使用 `std::execution` 很少直接写接收器，它们主要出现在写发送器算法的时候。

Clang 23 的 libc++ 还没有实现 `std::execution` 的这部分，本页例子没有经过编译。

## 一个接收器

```cpp title="print-receiver.cpp"
namespace ex = std::execution;

struct print_receiver {
  using receiver_concept = ex::receiver_tag;

  void set_value(int v) && noexcept              { std::println("value {}", v); }
  void set_error(std::exception_ptr) && noexcept { std::println("error"); }
  void set_stopped() && noexcept                 { std::println("stopped"); }
  // 没有 get_env：环境是 env<>{}
};
static_assert(ex::receiver<print_receiver>);
```

三个成员都带 `&&` 限定和 `noexcept`，原因见下文的完成函数。

## receiver 概念（[exec.recv.concepts] ¶1–2）

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

¶1 逐项看：

- **`receiver_concept` 标签**：类型主动声明自己是接收器。概念不检查任何 `set_*` 成员，一个只声明了标签的类型也满足 `receiver`。
- **`get_env(rcvr)`** 对 const 接收器可用，结果是可查询对象。没有 `get_env` 成员也可以，`get_env` 默认返回 `env<>{}`（[[exec.get.env]]）。
- **移动不抛异常**：`connect` 要把接收器移进操作状态，适配器在 `noexcept` 的完成路径上也常要移动接收器。如果移动可能抛异常，完成过程中就会出现无处报告的错误。
- `constructible_from<remove_cvref_t<Rcvr>, Rcvr>` 要求能从 `Rcvr` 这个值类别构造出副本，左值就意味着可复制。

¶2 标记为 `final` 的类不模型化 `receiver`。这是语义要求，概念检查发现不了：`final` 的接收器能通过 `static_assert(receiver<R>)`，但程序没有满足概念的要求。标准没有说明理由，一个合理的解读是给实现留出从用户接收器派生的余地，例如用空基类优化存储无状态的接收器。

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

这里用立即调用的泛型 lambda 做模式匹配：

1. *has-completions* 把 `Completions*` 传给一个只接受 `completion_signatures<Sigs...>*` 的 lambda，拆出 `Sigs...`，并要求每个签名满足 *valid-completion-for*；
2. *valid-completion-for* 把签名指针（如 `set_value_t(*)(int)`）传给接受 `Tag(*)(Args...)` 的 lambda，拆出 `Tag` 和 `Args...`，要求 `Tag` 能用右值接收器和 `Args...` 调用，也就是 `set_value(std::move(rcvr), args...)` 良构。

所以 *receiver-of*<R, completion_signatures<set_value_t(int), set_stopped_t()>> 检查 `set_value(R&&, int)` 和 `set_stopped(R&&)` 都能调用。`connect` 的 *Mandates* 包括这一条（[[exec.connect#6]]）：接收器必须能接受发送器可能发出的每一种完成。

这两个阐述用概念可以照抄进普通 C++ 代码，配上自己写的 `set_value_t` 模拟，Clang 23 能按上面的描述判断：只有 `set_value(int)` 和 `set_stopped()` 成员的接收器满足前面那组签名，一个空结构体不满足 `completion_signatures<set_value_t()>`。

## 三个完成函数（[exec.set.value]、[exec.set.error]、[exec.set.stopped]）

```cpp title="set-value-rvalue.cpp"
void complete(print_receiver& r) {
  namespace ex = std::execution;
  ex::set_value(r, 1);              // error: r 是左值
  ex::set_value(std::move(r), 1);   // OK
  const print_receiver cr{};
  ex::set_value(std::move(cr), 1);  // error: const 右值
}
```

三个完成函数的规定结构相同：

| 完成函数 | 完成标签 | 表达式 | 等价于 |
|---|---|---|---|
| `set_value` | `set_value_t` | `set_value(rcvr, vs...)` | *MANDATE-NOTHROW*(rcvr.set_value(vs...)) |
| `set_error` | `set_error_t` | `set_error(rcvr, err)` | *MANDATE-NOTHROW*(rcvr.set_error(err)) |
| `set_stopped` | `set_stopped_t` | `set_stopped(rcvr)` | *MANDATE-NOTHROW*(rcvr.set_stopped()) |

每个都另有两条规则：

1. 如果 `rcvr` 是左值或 const 右值，表达式非良构 {{ill-formed}}。
2. 成员调用良构时，类型必须是 `void`；*MANDATE-NOTHROW*（[[exec.general#5]]）还要求它 `noexcept`。

第 1 条在语言层面体现了恰好完成一次（[[exec.async.ops#8]]）：完成一个接收器就是消耗它，所以必须写 `std::move(rcvr)`。完成之后又使用 `rcvr`，就成了使用已被移动的对象，审查和静态分析都更容易发现。

成员函数是在右值 `rcvr` 上调用的，所以接收器的成员可以带 `&&` 限定（推荐），也可以不带限定，但不能只提供 `&` 限定的版本。

`set_error` 恰好有一个错误实参，`set_stopped` 没有数据实参，对应 [[exec.async.ops#2]] 中三种完成的数据个数。

!!! pitfall "在 set_value 里抛异常"
    接收器的 `set_value` 必须是 `noexcept`，否则 `set_value(...)` 表达式非良构。如果处理值时可能出错，接收器应该自己捕获，并对它持有的下游接收器调用 `set_error`。[[exec.snd]] 中的 *TRY-SET-VALUE* 就是这个模式。

## 停止令牌的有效期（[exec.recv.concepts] ¶3）

```cpp title="stop-callback-order.cpp"
void complete_value(T v) noexcept {
  stop_cb_.reset();                                    // 1. 先注销停止回调
  ex::set_value(std::move(rcvr_), std::move(v));       // 2. 再完成
}
```

¶3 设 `token` 等于 `get_stop_token(get_env(rcvr))`，它必须在异步操作的生存期（[[exec.async.ops#7]]）内保持有效。注 1 指出两个推论：除非知道接收器类型有更多保证，操作状态在执行完成操作之后不能再使用 `token`；在 `token` 上注册的停止回调，必须在调用完成操作之前销毁。

上面的顺序反过来就错了。`set_value` 一开始，异步生存期就结束了，提供令牌的一方（比如 `when_all` 内部的 `inplace_stop_source`）可能立刻被销毁，之后 `stop_cb_` 的析构函数访问的是已不存在的停止状态。标准 `when_all` 的阐述代码在每个完成分支里都先写 `on_stop.reset();`（[[exec.when.all]]），原因就在这里。

## inlinable_receiver（[exec.recv.concepts] ¶4–9）

```cpp
template<class Rcvr, class ChildOp>
  concept inlinable_receiver = receiver<Rcvr> &&
    requires (ChildOp* child) {
      { remove_cvref_t<Rcvr>::make_receiver_for(child) } noexcept
        -> same_as<remove_cvref_t<Rcvr>>;
    };
```

考虑 `then(then(then(s, f), g), h)`。最内层的操作状态存着一个接收器，它通常只是一个指向外层操作状态的指针，嵌套越深浪费越多。但子操作状态本来就嵌在父操作状态里，父操作状态的地址可以从子操作状态的地址算出来。所以接收器不必存储，需要时用子操作状态的地址重建即可。

¶4 `inlinable_receiver<Rcvr, ChildOp>` 描述这种接收器：`Rcvr::make_receiver_for(addressof(op))` 必须得到一个与原接收器相等的接收器。注 2 说，这样的接收器不必作为数据成员存进 `op`。`ChildOp` 可以是不完整类型，因为父操作状态声明子操作状态成员时，子类型往往还不完整。

¶5–6 定义了两个术语。由同一个对象复制一次、再移动若干次得到的对象，称为由它**传递构造**（transitively constructed）。如果 `connect(sndr, rcvr)` 求值期间由 `rcvr` 传递构造的所有对象，生存期都在这次求值内结束，就说这个表达式**内联了接收器**（[[g:inlines-the-receiver|inlines the receiver]]），也就是操作状态里没有存接收器。

¶7 对标准定义的发送器，如果 connect 内联了接收器，条文中凡是指代由 `rcvr` 传递构造的对象的地方，都改为指代 `make_receiver_for(addressof(op))` 现场造出的临时对象。本章到处出现的 `std::move(rcvr)`，在这种情况下就读作现场造一个接收器。

¶8 标准库自己的接收器类型是否模型化 `inlinable_receiver`，未指定 {{unspec}}。¶9 如果你的接收器模型化了 `inlinable_receiver<StdOp>`（`StdOp` 是标准的操作状态类型），那么产生 `StdOp` 的 connect 是否内联它，由实现定义 {{impl}}。

!!! lawyer "为什么一个未指定、一个实现定义？"
    ¶8 关心标准接收器是否提供这种能力，这是实现细节，不值得要求写文档。¶9 关心标准操作状态是否利用你的接收器的这种能力，这会影响你的接收器对象是否真的被存储，从而影响它的副作用和地址是否稳定，所以要求实现说明。写 `make_receiver_for` 的人要保证无论存还是不存，行为都一样，¶4 要求重建出的接收器与原来的相等，就是这个保证。

## 思考题

!!! question "1. 一个没有任何 set_* 成员的接收器"
    `struct R { using receiver_concept = receiver_tag; };` 满足 `receiver` 吗？它能和 `just()` connect 吗？

<details markdown="1">
<summary>答案</summary>

满足 `receiver`：有标签，`get_env` 默认返回 `env<>{}`，可以无异常地移动。

但不能和 `just()` connect。`just()` 的完成签名是 `completion_signatures<set_value_t()>`，*receiver-of* 要求 `set_value(R&&)` 良构，而 `R` 没有 `set_value` 成员，[[exec.connect]] 的 *Mandates* 不满足，程序非良构。`just_stopped()`、`just_error(x)` 同理。
</details>

!!! question "2. 停止回调与完成的顺序"
    一个发送器在 `start` 里构造了停止回调对象，`set_value` 之后才在操作状态的析构函数里销毁它。这违反了什么？什么时候会真的出问题？

<details markdown="1">
<summary>答案</summary>

违反了 [exec.recv.concepts] ¶3：令牌只在异步生存期内有效，而异步生存期在完成操作开始时就结束了，注 1 明确要求回调在完成之前销毁。

当令牌的提供者在完成后立即销毁 stop source 时，问题就会出现。比如 `when_all` 的最后一个子操作完成后，`when_all` 自己完成，外层随即销毁整个操作状态，包括 `inplace_stop_source`。这时子操作状态析构、注销回调，访问的是已经销毁的停止状态，属于释放后使用。
</details>

## 小结

- `receiver`：`receiver_concept` 标签、可查询的 `get_env`、可无异常移动；不检查 `set_*`；不能是 `final`。
- *receiver-of*：对每个完成签名检查 `Tag(std::move(rcvr), args...)` 可以调用。
- `set_value`、`set_error`、`set_stopped` 只接受非 const 右值接收器，返回 `void`，必须 `noexcept`。
- 停止令牌只在异步生存期内有效，回调须在完成前注销。
- `inlinable_receiver`：可由操作状态地址重建的接收器，实现可以不存储它。
