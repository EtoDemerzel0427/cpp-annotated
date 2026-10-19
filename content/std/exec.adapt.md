---
title: 发送器适配器
summary: 适配器的通用规则（惰性、属性和环境怎样转发、可省略的 exception_ptr 签名）；sndr | then(f) 背后的闭包对象；then、upon_error、upon_stopped；write_env 与 unstoppable；into_variant；stopped_as_optional 与 stopped_as_error。
status: draft
covers: exec.adapt.general, exec.adapt.obj, exec.write.env, exec.unstoppable, exec.then, exec.into.variant, exec.stopped.opt, exec.stopped.err
papers: P2300R10
related: exec.snd, exec.factories, exec.on, exec.let, exec.bulk, exec.when.all, exec.queries, exec.snd.transform
tags: 标准库, std::execution, 发送器适配器
updated: 2026-10-19
---

!!! tldr
    - 适配器接受发送器、返回新的发送器，并且是惰性的：在结果被 connect 并 start 之前，除了复制、移动实参之外什么也不做。
    - `then(sndr, f)` 和 `sndr | then(f)` 等价；少给发送器的 `then(f)` 是一个闭包对象，闭包之间也能用 `|` 组合，设计与 ranges 的范围适配器相同。
    - `then`、`upon_error`、`upon_stopped` 分别在值、错误、取消完成时调用回调，把回调的结果作为值发出；回调抛出的异常变成 `set_error(exception_ptr)`。
    - `write_env` 给子发送器换上一个合并后的环境，写入的查询优先；`unstoppable` 就是写入一个永不停止的停止令牌。
    - `into_variant` 把多种值签名合成一个 variant；`stopped_as_optional`、`stopped_as_error` 把取消变成空 `optional` 或一个错误。

本页的 `std::execution` 例子没有经过编译验证：本机 Clang 23 附带的 libc++ 还没有实现发送器库，所以不加判定标记。

[[g:sender-adaptor|发送器适配器]]（sender adaptor）接受一个或多个发送器（称为子发送器），返回一个新的发送器（父发送器），是把小块异步工作组合成大块的工具。本页讲通用规则、管道语法和几个较简单的适配器。其余的在别处：切换执行资源的 `starts_on`、`continues_on`、`on` 见 [[exec.on]]，`let_*` 见 [[exec.let]]，`bulk*` 见 [[exec.bulk]]，`when_all` 见 [[exec.when.all]]，`associate`、`spawn_future` 见 [[exec.spawn]]。

## 管道语法与闭包对象 [exec.adapt.obj]

```cpp title="pipe.cpp"
namespace ex = std::execution;

auto add1  = ex::then([](int x) { return x + 1; });   // 少给了发送器：得到闭包
auto twice = add1 | add1;                             // 组合两个闭包：先 add1 再 add1
auto s     = ex::just(40) | twice;                    // 等价于 then(then(just(40), f), f)
```

这套语法和 ranges 的范围适配器几乎一一对应。下面是 ranges 里的同样写法：

```cpp run ok
#include <ranges>
#include <vector>
#include <print>

int main() {
  auto add1  = std::views::transform([](int x) { return x + 1; });
  auto twice = add1 | add1;          // 组合两个闭包
  std::vector v{1, 2, 3};
  for (int x : v | twice) std::print("{} ", x);   // 3 4 5
}
```

¶1 **可管道化发送器适配器闭包对象**（[[g:pipeable-sender-adaptor-closure-object|pipeable sender adaptor closure object]]）是接受发送器、返回发送器的函数对象 `c`，`c(sndr)` 与 `sndr | c` 等价。两个闭包 `c | d` 产生一个新闭包，调用它相当于 `d(c(arg))`：先 `c` 后 `d`。新闭包里存的是 `c` 和 `d` 的副本。

¶2 一个类型 `T` 要成为闭包对象的类型，需要派生自 `sender_adaptor_closure<T>`（并且只有这一个这样的基类），同时自己不能满足 `sender`。所以自定义闭包只需继承这个基类：

```cpp title="closure.cpp"
struct log_values_t : ex::sender_adaptor_closure<log_values_t> {
  template<ex::sender S> auto operator()(S&& s) const {
    return std::forward<S>(s)
         | ex::then([](auto v) { std::println("{}", v); return v; });
  }
};
inline constexpr log_values_t log_values;
// ex::just(1) | log_values | ex::then(...)
```

¶3 `sender_adaptor_closure<D>` 的 `D` 在声明基类时可以不完整，但在作为 `|` 的操作数出现之前必须完整。如果重载决议对这样的操作数选中了程序自己定义的 `operator|`，行为未定义 {{ub}}，所以不要给自己的闭包类型再写 `operator|`。

¶4 **可管道化发送器适配器对象**是第一个实参为发送器、返回发送器的定制点对象，`then`、`write_env` 都是。只接受一个实参的（如 `into_variant`），本身就是闭包对象。

¶5 接受多个实参的适配器对象，少给发送器调用时，比如 `then(f)`，产生一个闭包：它存着适配器和其余实参的退化副本，以 `sndr` 调用时相当于 `then(sndr, f)`。

## 通用规则 [exec.adapt.general]

¶2 适配器同时支持函数调用写法和 `|` 写法，两者含义相同。

¶3 除非另有规定，所有适配器都遵守以下规则：

- ¶3.1 适配器是**惰性**的：在返回的发送器被 connect 并 start 之前，它不能产生可观察的效果，复制、移动实参除外。`then(sndr, f)` 不调用 `f`，也不会预先启动 `sndr`。
- ¶3.2 只有一个子发送器时，父发送器的属性就是子发送器的属性，只透出[[g:forwarding-query|转发查询]]（*FWD-ENV*）。完成调度器和完成 domain 两个查询除外，它们按 [[exec.snd.general#3]]、[[exec.snd.general#4]] 重新计算，因为适配器可能改变完成发生的位置。
- ¶3.3 有多个子发送器时，父发送器的属性是空环境 `env<>{}`，完成调度器和完成 domain 同样另算。
- ¶3.4 父发送器与接收器 `rcvr` connect 时，子发送器看到的环境是 *FWD-ENV*(get_env(rcvr))，也就是外部环境中的转发查询。
- ¶3.5 子发送器都是[[g:non-dependent-sender|非依赖发送器]]时，适配器也是非依赖的。
- ¶3.6 这些要求同样适用于实现选用的任何函数，包括通过 domain 定制选中的实现。
- ¶3.7 建议（*Recommended practice*）实现用适配器的完成签名向用户报告类型错误，并把子发送器的类型错误传播上来。

惰性意味着发送器可以被自由地构造、复制、丢弃，没有副作用。一个函数可以返回一个描述了很多工作的发送器，由调用者决定是 `sync_wait`、`spawn`，还是直接丢掉。`std::async` 则不同：它一调用就开始工作，丢弃返回的 `future` 会在析构时阻塞等待。

¶4 有些适配器规定签名中包含 `set_error_t(exception_ptr)`。如果实现确定不会发出这种错误完成，可以省略这个签名。例如实现能证明 `then` 的回调不会抛异常时，就不必报告它，下游也就少处理一种不可能发生的情况。

## then、upon_error、upon_stopped [exec.then]

```cpp title="upon-error.cpp"
namespace ex = std::execution;

auto s = ex::just_error(std::make_error_code(std::errc::timed_out))
       | ex::upon_error([](std::error_code) { return -1; });   // set_value_t(int)
auto [v] = std::this_thread::sync_wait(std::move(s)).value();   // v == -1
```

¶1 `then` 给输入发送器的值完成接上一个可调用对象作为后续；`upon_error`、`upon_stopped` 对错误、取消完成做同样的事。三者都把可调用对象的结果作为值完成发出。所以 `upon_error` 把错误变成了值，是处理错误并恢复执行的工具。

¶2–3 `sndr` 不是发送器，或者 `f` 不满足 *movable-value*（能退化复制成独立的值，见 [[exec.general]]）时非良构；否则等价于 *make-sender*(*then-cpo*, f, sndr)。

¶4 *impls-for* 只覆盖 *complete*（钩子的含义见 [[exec.snd]]）：

```cpp
static constexpr auto complete =
  []<class Tag, class... Args>(auto, auto& fn, auto& rcvr, Tag, Args&&... args) noexcept -> void {
    if constexpr (same_as<Tag, decayed-typeof<set-cpo>>) {
      TRY-SET-VALUE(rcvr, invoke(std::move(fn), std::forward<Args>(args)...));
    } else {
      Tag()(std::move(rcvr), std::forward<Args>(args)...);
    }
  };
```

*set-cpo* 对 `then`、`upon_error`、`upon_stopped` 分别是 `set_value`、`set_error`、`set_stopped`。子操作以对应的方式完成时，调用 `fn`，把结果 `set_value` 出去：`fn` 返回 `void` 就是 `set_value()`，`fn` 抛异常就是 `set_error(exception_ptr)`。其他完成原样转发。

| 子发送器的签名 | `then(f)` | `upon_error(f)` | `upon_stopped(f)` |
|---|---|---|---|
| `set_value_t(int)` | `set_value_t(invoke_result_t<F, int>)` | 原样 | 原样 |
| `set_error_t(E)` | 原样 | `set_value_t(invoke_result_t<F, E>)` | 原样 |
| `set_stopped_t()` | 原样 | 原样 | `set_value_t(invoke_result_t<F>)` |
| `f` 可能抛异常时追加 | `set_error_t(exception_ptr)` | 同左 | 同左 |

结果类型为 `void` 时，对应的签名是 `set_value_t()`。

回调是以右值调用的（`invoke(std::move(fn), ...)`），而且只调用一次。只有 `&` 限定 `operator()` 的函数对象不能用于 `then`。

¶5 *check-types* 检查回调能否用子发送器对应完成的每一组实参调用，不能就抛异常，签名计算因此失败。由于 *make-sender* 会在构造时检查非依赖发送器的签名，`then(just(1), [](std::string) {})` 在构造这一行就非良构（[[exec.snd]]）。

¶6 如果 `then` 返回的发送器不是这样工作的：对相应的完成调用 `f`（或其副本）并以其结果作为值完成，其他完成原样转发，行为未定义。这一条约束的是定制实现：domain 换掉 `then` 的实现时，必须保持这一语义。

## write_env 与 unstoppable

### write_env [exec.write.env]

```cpp title="write-env.cpp"
namespace ex = std::execution;

std::pmr::monotonic_buffer_resource pool;
auto s = ex::write_env(work, ex::prop(std::get_allocator,
                                      std::pmr::polymorphic_allocator<>(&pool)));
// work 内部 get_allocator(get_env(rcvr)) 得到使用 pool 的分配器
```

¶1 `write_env(sndr, env)` 返回的发送器与接收器 `rcvr` connect 时，用一个新的接收器连接 `sndr`，新接收器的环境是把 `env` 合并到 `get_env(rcvr)` 之上的结果。

¶2 `sndr` 不是发送器或 `env` 不是[[g:queryable-object|可查询对象]]时非良构；否则等价于 *make-sender*(write_env, env, sndr)。

¶3–4 *impls-for* 覆盖 *get-env*：对查询 `q`，先问写入的 `env`，回答不了再问外部环境（经过 *FWD-ENV*）。写入的环境优先。

¶5 *check-types* 在合并后的环境下计算子发送器的签名。

有两点要注意。写入的环境只对子发送器可见，不改变 `write_env` 发送器自己的属性。外部环境要经过 *FWD-ENV*，只有转发查询能穿透；写入的环境则完整可见，包括非转发查询。

### unstoppable [exec.unstoppable]

¶1–2 `unstoppable(sndr)` 等价于 `write_env(sndr, prop(get_stop_token, never_stop_token{}))`。

子发送器看到的停止令牌永远是 `never_stop_token`，外部的取消请求不会传到它。这适合必须做完的工作，比如提交事务、释放资源。`unstoppable_token<never_stop_token>` 为 true，所以子发送器还可能借此在类型上去掉 `set_stopped_t()` 签名，例如 `run_loop` 的调度发送器（[[exec.run.loop]]）。

## into_variant [exec.into.variant]

¶1 `into_variant` 把有多种值完成签名的发送器变成只有一种值签名的发送器，值是一个由 tuple 组成的 variant。例如：

| 子发送器的值签名 | `into_variant` 的值签名 |
|---|---|
| `set_value_t(int)`、`set_value_t(std::string, double)` | `set_value_t(std::variant<std::tuple<int>, std::tuple<std::string, double>>)` |

构造 variant 可能抛异常，所以还可能多一个 `set_error_t(exception_ptr)`。

¶2–3 `sndr` 不是发送器时非良构；否则等价于 *make-sender*(into_variant, {}, sndr)。¶4 *check-types* 要求子发送器的结果都能退化复制。¶5 *get-state* 只用来携带 variant 的类型。¶6 *complete* 在值完成时构造 variant 并 `set_value`，其他完成原样转发。

`when_all` 要求每个子发送器只有一种值签名（[[exec.when.all]]），`sync_wait` 也一样（[[exec.consumers]]）。`into_variant` 是把多签名发送器交给它们的转接层，`when_all_with_variant`、`sync_wait_with_variant` 就是在内部套了一层 `into_variant`。

## stopped_as_optional 与 stopped_as_error

### stopped_as_optional [exec.stopped.opt]

```cpp title="stopped-as-optional.cpp"
namespace ex = std::execution;

// 设 cancellable_read() 的签名是 set_value_t(int)、set_stopped_t()
auto s = cancellable_read() | ex::stopped_as_optional;   // set_value_t(optional<int>)
if (auto r = std::this_thread::sync_wait(std::move(s))) {
  auto [opt] = *r;     // opt 为空表示被取消
}
```

¶1 `stopped_as_optional` 把取消完成变成一个值为空 `optional` 的值完成，原来的值也包进 `optional`。结果发送器不会以取消完成。

管道里写的是 `| stopped_as_optional`，没有括号：它只接受一个发送器，本身就是闭包对象（[exec.adapt.obj] ¶4）。

¶2 等价于 *make-sender*(stopped_as_optional, {}, sndr)。¶3 *check-types* 额外要求子发送器恰好有一种值签名，并且这种签名带有值（不是 `set_value_t()`）。因此 `just_stopped() | then([] { return 1; })` 不能用：`just_stopped()` 没有值完成，`then` 的回调根本不会被调用，结果的签名只有 `set_stopped_t()`。

¶4 它没有自己的实现，而是在 `transform_sender` 中改写成其他适配器的组合（[[exec.snd.transform]]）：

```cpp
auto&& [_, _, child] = sndr;
using V = single-sender-value-type<child-type<Sndr>, FWD-ENV-T(Env)>;
return let_stopped(
  then(std::forward_like<Sndr>(child),
       []<class... Ts>(Ts&&... ts) noexcept(is_nothrow_constructible_v<V, Ts...>) {
         return optional<V>(in_place, std::forward<Ts>(ts)...);
       }),
  []() noexcept { return just(optional<V>()); });
```

值经过 `then` 包进 `optional`，取消经过 `let_stopped` 换成一个发出空 `optional` 的 `just`。子发送器在该环境下根本算不出签名时，改写的结果是 *not-a-sender*()，错误推迟到计算签名时报出。

### stopped_as_error [exec.stopped.err]

¶1 `stopped_as_error(sndr, err)` 把取消完成变成以 `err` 为数据的错误完成，结果不会以取消完成。适合调用者不区分取消和失败，或者需要把取消变成一个具体错误码（如 `errc::operation_canceled`）交给只处理错误的代码。

¶2 `sndr` 不是发送器或 `err` 不满足 *movable-value* 时非良构；否则等价于 *make-sender*(stopped_as_error, err, sndr)。

¶3 它同样改写成 `let_stopped`：

```cpp
auto&& [_, err, child] = sndr;
using E = decltype(auto(err));
return let_stopped(
  std::forward_like<Sndr>(child),
  [err = std::forward_like<Sndr>(err)]() mutable noexcept(is_nothrow_move_constructible_v<E>) {
    return just_error(std::move(err));
  });
```

<details class="fine" markdown="1"><summary>其余条文</summary>

[exec.adapt.general] ¶1 只说明本子条款规定了一组发送器适配器。

[exec.adapt.obj] ¶1 和 ¶5 规定，`c | d` 以及 `adaptor(args...)` 只有在新闭包的各个状态实体都能初始化时才良构。¶5.3 把调用模式写成 `adaptor(rcvr, bound_args...)`，这里的 `rcvr` 指的是调用闭包时传入的那个实参，也就是发送器。

</details>

## 思考题

!!! question "1. then 和 upon_error 的组合"
    `just(1) | then([](int) -> int { throw 1; }) | upon_error([](std::exception_ptr) { return 0; })` 的签名是什么？`sync_wait` 得到什么？

<details markdown="1">
<summary>答案</summary>

`then` 的回调可能抛异常，所以中间发送器的签名是 `set_value_t(int)` 和 `set_error_t(exception_ptr)`。`upon_error` 把错误变成值，`invoke_result_t<F, exception_ptr>` 是 `int`，所以得到 `set_value_t(int)`，和原样转发来的值签名重合，只算一个。`upon_error` 的回调没有声明 noexcept，所以还有 `set_error_t(exception_ptr)`。

运行时，`then` 的回调抛出 `int`，*TRY-SET-VALUE* 捕获后调用 `set_error(exception_ptr)`；`upon_error` 的回调返回 0，于是 `set_value(0)`。`sync_wait` 返回 `optional<tuple<int>>`，值为 0。
</details>

!!! question "2. write_env 能覆盖停止令牌吗？"
    外部接收器环境里有停止令牌 `t1`，`write_env(sndr, prop(get_stop_token, t2))` 之后 `sndr` 看到哪个？外部请求停止时 `sndr` 会被取消吗？

<details markdown="1">
<summary>答案</summary>

看到 `t2`：合并后的环境先问写入的部分（[exec.write.env] ¶4.2）。外部通过 `t1` 请求停止不会传到 `sndr`，因为 `sndr` 根本拿不到 `t1`：`write_env` 是覆盖，不是合并两个令牌。想要任一令牌触发都取消，需要把两个令牌合成一个，[[exec.spawn]] 中阐述用的 *stop-when* 做的就是这件事。
</details>
