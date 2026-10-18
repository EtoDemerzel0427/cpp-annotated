---
title: 发送器适配器
summary: 适配器的通用规则（惰性、属性与环境如何转发、exception_ptr 签名可省略）；管道语法 sndr | then(f) 背后的闭包对象；then / upon_error / upon_stopped；write_env 与 unstoppable；into_variant；stopped_as_optional 与 stopped_as_error
status: done
covers: exec.adapt.general, exec.adapt.obj, exec.write.env, exec.unstoppable, exec.then, exec.into.variant, exec.stopped.opt, exec.stopped.err
papers: P2300R10
related: exec.snd, exec.factories, exec.on, exec.let, exec.bulk, exec.when.all, exec.queries, exec.snd.transform
tags: 标准库, std::execution, 发送器适配器
updated: 2026-10-18
---

适配器（[[g:sender-adaptor]]）接受一个或多个发送器，返回一个新的发送器——它们是把小块异步工作**组合**成大块的工具。本页覆盖 [exec.adapt] 的总则、管道语法，以及几个较简单的适配器；换调度器的 `starts_on`/`continues_on`/`on` 见 [[exec.on]]，`let_*` 见 [[exec.let]]，`bulk*` 见 [[exec.bulk]]，`when_all` 见 [[exec.when.all]]，`associate`/`spawn_future` 见 [[exec.spawn]]。

## 通用规则（[exec.adapt.general]）

¶2 位或运算符 `|` 被重载用来构造发送器链；适配器也支持等价的函数调用语法：`then(sndr, f)` ≡ `sndr | then(f)`。

¶3 除非另有规定：

- ¶3.1 **惰性**：在返回的发送器被 connect 并且 start 之前，适配器不得产生除复制/移动实参以外的可观察效果。`then(sndr, f)` 不会调用 `f`，也不会"预先启动" `sndr`。
- ¶3.2 **单子发送器的属性**：父发送器的属性等于 *FWD-ENV*(get_env(sndr))——子发送器的转发查询原样透出；但 `get_completion_scheduler<Tag>`、`get_completion_domain<Tag>` 按 [[exec.snd.general#3]]–4 的规则重新计算（不能直接照搬，因为适配器可能改变完成发生的位置）。
- ¶3.3 **多子发送器的属性**：等于 `env<>{}`，完成调度器/domain 同上另算。
- ¶3.4 **环境向下传**：父发送器与接收器 `rcvr` connect 时，连接子发送器所用的接收器，其环境等于 *FWD-ENV*(get_env(rcvr))。
- ¶3.5 子发送器都是非依赖的（[[exec.async.ops#13]]），则适配器也是非依赖的。
- ¶3.6 这些要求也适用于实现所选择的任何函数（包括 domain 定制选中的实现）。
- ¶3.7 *Recommended practice*：实现应该用适配器的完成签名向用户报告类型错误，并传播子发送器的类型错误。

¶4 若某适配器被规定在签名中包含 `set_error_t(Err)`（`decay_t<Err>` 是 `exception_ptr`），但实现**不会**潜在求值带 `exception_ptr` 的 error 完成，实现可以省略这个签名。例如实现能证明 `then` 的回调不会抛异常时，就不必报告 `set_error_t(exception_ptr)`——这让下游少处理一种不可能的情况。

!!! note "¶3.1 的实际意义"
    惰性意味着发送器可以被**自由地构造、复制、丢弃**，没有副作用。一个函数可以返回一个"描述了很多工作"的发送器，调用者决定是 `sync_wait` 它、`spawn` 它，还是干脆丢弃它。这与 `std::async` 的返回值截然不同：丢弃一个 `async` 返回的 `future` 会在析构时阻塞等待已经开始的工作。

## 闭包对象与管道语法（[exec.adapt.obj]）

¶1 [[g:pipeable-sender-adaptor-closure-object|**可管道化发送器适配器闭包对象**]]：接受发送器、返回发送器的函数对象 `c`，使得 `c(sndr)` 与 `sndr | c` 等价。两个闭包 `c | d` 产生一个新闭包 `e`：它是一个完美转发调用包装器（[[func.require]]），目标对象是 `d` 的副本，绑定实参是 `c` 的副本，调用模式是 `d2(c2(arg))`——先 `c` 后 `d`。

¶2 类型 `T` 的对象是闭包对象，当 `T` 模型化 `derived_from<sender_adaptor_closure<T>>`、没有其他 `sender_adaptor_closure<U>` 基类，且 `T` **不**满足 `sender`。

¶3 `sender_adaptor_closure<D>` 的 `D` 可以不完整；但在 `D` 作为 `|` 的操作数出现之前必须完整。若重载决议选中了一个**程序定义**的 `operator|`，涉及 `D` 的 `|` 表达式行为未定义 {{ub}}——不要给自己的闭包类型再写 `operator|`。

¶4 **可管道化发送器适配器对象**：一个第一个实参是发送器、返回发送器的 CPO。只接受一个实参的，本身就是闭包对象。

¶5 接受多个实参的适配器对象 `adaptor`，`adaptor(args...)`（**少给**了发送器）产生一个闭包：目标对象是 `adaptor` 的副本，绑定实参是 `args...` 的 decay 副本，调用模式是 `adaptor(sndr, bound_args...)`。

```cpp title="pipe.cpp"
namespace ex = std::execution;

auto add1  = ex::then([](int x) { return x + 1; });   // 闭包：then 少给了发送器
auto twice = add1 | add1;                             // 闭包组合：先 add1 再 add1
auto s     = ex::just(40) | twice;                    // 等价于 then(then(just(40), f), f)

// 自定义闭包：派生 sender_adaptor_closure 即可获得 | 支持
struct log_t : ex::sender_adaptor_closure<log_t> {
  template<ex::sender S> auto operator()(S&& s) const {
    return std::forward<S>(s) | ex::then([](auto v) { std::println("{}", v); return v; });
  }
};
```

这套设计与 ranges 的范围适配器闭包（`views::transform(f)`，`range_adaptor_closure`）几乎一一对应。

## then、upon_error、upon_stopped（[exec.then]）

¶1 `then` 给输入发送器的 **value** 完成接一个可调用对象作为后续；`upon_error`、`upon_stopped` 对 error、stopped 完成做同样的事。三者都把可调用对象的结果作为 **value** 完成发出。

¶2–3 `decltype((sndr))` 不满足 `sender` 或 `decltype((f))` 不满足 *movable-value* 时非良构；否则等价于 *make-sender*(*then-cpo*, f, sndr)。

¶4 *impls-for* 只覆盖 *complete*：

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

- 子操作以**对应**的处置完成：调用 `fn`，把结果 `set_value` 出去；`fn` 返回 `void` 就 `set_value()`；`fn` 抛异常就 `set_error(exception_ptr)`。
- 其他处置：原样转发。

¶5 *check-types*：对子发送器每个对应处置的签名 `Tag(Ts...)`，若 `invocable<F, Ts...>` 为 false 就抛异常——类型错误在计算签名时报出（[[exec.snd]] 中构造即报错的机制）。

¶6 若 *then-cpo*(sndr, f) 返回的发送器不满足"对应处置调用 `f`（或其副本）并以其结果作 value 完成，其他完成原样转发"，行为未定义。这条约束的对象是**定制实现**：domain 若替换了 `then`，必须保持这一语义。

签名变换一览（`f` 可能抛异常时）：

| 子发送器签名 | `then(f)` | `upon_error(f)` | `upon_stopped(f)` |
|---|---|---|---|
| `set_value_t(int)` | `set_value_t(R)`，`R = invoke_result_t<F, int>`（`void` 则 `set_value_t()`） | 原样 | 原样 |
| `set_error_t(E)` | 原样 | `set_value_t(invoke_result_t<F, E>)` | 原样 |
| `set_stopped_t()` | 原样 | 原样 | `set_value_t(invoke_result_t<F>)` |
| 额外 | `set_error_t(exception_ptr)` | 同左 | 同左 |

注意 `upon_error` 把错误**变成了值**——它是"处理错误并恢复"的工具：

```cpp title="upon-error.cpp"
namespace ex = std::execution;

auto s = ex::just_error(std::make_error_code(std::errc::timed_out))
       | ex::upon_error([](std::error_code ec) { return -1; });   // set_value_t(int)
auto [v] = std::this_thread::sync_wait(std::move(s)).value();      // v == -1
```

!!! pitfall "then 的 f 被 std::move 后调用"
    `invoke(std::move(fn), ...)`：回调以**右值**被调用。一个只有 `&` 限定 `operator()` 的函数对象不能用于 `then`（*check-types* 中 `invocable<F, Ts...>` 检查的也是右值 `F`）。另外 `f` 只会被调用一次——这与"每次 connect 一次、每次完成一次"相符。

## write_env（[exec.write.env]）

¶1 `write_env(sndr, env)`：connect 时，把 `sndr` 与一个环境为"`env` 合并到 `get_env(rcvr)` 之上"的接收器 connect。

¶2 `sndr` 不是发送器或 `env` 不满足 *queryable* 时非良构；否则 *make-sender*(write_env, env, sndr)。

¶3–4 *impls-for* 覆盖 *get-env*：返回 *join-env*(state, *FWD-ENV*(get_env(rcvr)))，其中对查询 `q`，先问 `state`（即写入的 `env`），不行再问外部环境。**写入的环境优先**。

¶5 *check-types*：子发送器在合并后的环境下计算签名。

```cpp title="write-env.cpp"
namespace ex = std::execution;

std::pmr::monotonic_buffer_resource pool;
auto s = ex::write_env(work, ex::prop(std::get_allocator, std::pmr::polymorphic_allocator<>(&pool)));
// work 内部 get_allocator(get_env(rcvr)) 得到 pool 的分配器
```

注意两点：

- 写入的环境对子发送器可见，**不**改变 `write_env` 发送器自己的属性；
- 外部环境经过 *FWD-ENV*，只有转发查询能穿透；写入的环境则完整可见（包括非转发查询）。

## unstoppable（[exec.unstoppable]）

¶1–2 `unstoppable(sndr)` ≡ `write_env(sndr, prop(get_stop_token, never_stop_token{}))`。

子发送器看到的停止令牌永远是 `never_stop_token`，于是外部的取消请求不会传到它。用途：一段**必须做完**的工作（比如提交事务、释放资源），即使外部被取消也不能中途放弃。由于 `unstoppable_token<never_stop_token>` 为 true，子发送器还可能借此在类型上去掉 `set_stopped_t()` 签名（例如 `run_loop` 的调度发送器，[[exec.run.loop]]）。

## into_variant（[exec.into.variant]）

¶1 把有**多个** value 完成签名的发送器，变成只有**一个** value 签名、其值是 "variant of tuples" 的发送器。

¶3 *make-sender*(into_variant, {}, sndr)。¶5 *get-state* 只返回一个 `type_identity<value_types_of_t<child, FWD-ENV-T(env)>>`，用来携带类型。¶6 *complete*：value 完成时，`TRY-SET-VALUE(rcvr, variant_type(decayed-tuple<Args...>{args...}))`；其他完成原样转发。¶4 *check-types*：子发送器的结果数据必须都能 decay-copy。

子发送器签名 `set_value_t(int)`、`set_value_t(std::string, double)` → `into_variant` 签名 `set_value_t(std::variant<std::tuple<int>, std::tuple<std::string, double>>)`（可能还有 `set_error_t(exception_ptr)`，因为构造 variant 可能抛异常）。

`when_all` 要求每个子发送器只有一种 value 签名（[[exec.when.all]]），`sync_wait` 也一样（[[exec.consumers]]）；`into_variant` 是把多签名发送器喂给它们的适配层。`when_all_with_variant` 与 `sync_wait_with_variant` 就是在内部套了一层 `into_variant`。

## stopped_as_optional（[exec.stopped.opt]）

¶1 把 stopped 完成映射成值为**空 optional** 的 value 完成；原来的 value 完成也包进 `optional`。结果发送器**不会**以 stopped 完成。

¶2 *make-sender*(stopped_as_optional, {}, sndr)。¶3 *check-types*：除默认检查外，子发送器必须有 *single-sender-value-type* 且**不是** `void`——即恰好一种 value 签名、且带至少一个值。

¶4 它不直接实现，而是在 `transform_sender` 中降级（[[exec.snd.transform]]）：

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

子发送器在环境下根本没有签名时，变换结果是 *not-a-sender*()，错误推迟到签名计算时报出。

```cpp title="stopped-as-optional.cpp"
namespace ex = std::execution;

// 设 cancellable_read() 的签名是 set_value_t(int)、set_stopped_t()
auto s = cancellable_read() | ex::stopped_as_optional;      // set_value_t(optional<int>)
if (auto r = std::this_thread::sync_wait(std::move(s))) {
  auto [opt] = *r;     // opt 为空表示被取消；sync_wait 自己不会再因 stopped 返回空 optional
}
```

注意管道写法是 `| stopped_as_optional` 而不是 `| stopped_as_optional()`：它是只接受一个发送器的适配器对象，本身就是闭包对象（[exec.adapt.obj] ¶4），没有"少给发送器"的零实参形式。

还要注意 ¶3 的要求是"恰好一种 value 签名、且值类型非 `void`"。`just_stopped() | then([] { return 1; })` 不能拿来演示：`just_stopped()` 没有 value 完成，`then` 的回调分支根本不会被实例化，结果的签名只有 `set_stopped_t()`，*single-sender-value-type* 是 `void`，*check-types* 抛异常。

## stopped_as_error（[exec.stopped.err]）

¶1 把 stopped 完成映射成带自定义错误的 error 完成。结果不会以 stopped 完成。

¶2 `sndr` 不是发送器或 `err` 不满足 *movable-value* 时非良构；否则 *make-sender*(stopped_as_error, err, sndr)。

¶3 降级为：

```cpp
auto&& [_, err, child] = sndr;
using E = decltype(auto(err));
return let_stopped(
  std::forward_like<Sndr>(child),
  [err = std::forward_like<Sndr>(err)]() mutable noexcept(is_nothrow_move_constructible_v<E>) {
    return just_error(std::move(err));
  });
```

用途：调用者不区分"取消"与"失败"，或者需要把取消变成一个具体的错误码（比如 `errc::operation_canceled`）交给只处理错误的代码。

## 思考题

!!! question "1. then 和 upon_error 的组合"
    `just(1) | then([](int) -> int { throw 1; }) | upon_error([](std::exception_ptr) { return 0; })` 的签名是什么？`sync_wait` 得到什么？

<details markdown="1">
<summary>答案</summary>

`then` 的回调可能抛异常，所以中间发送器签名是 `set_value_t(int)`、`set_error_t(exception_ptr)`。`upon_error` 把 error 变成 value：`invoke_result_t<F, exception_ptr>` 是 `int`，于是得到 `set_value_t(int)`（两条来源的 `set_value_t(int)` 去重，*impls-for* 的签名集合是"潜在求值的完成"构成的集合）；回调也可能抛异常（未声明 noexcept），所以还有 `set_error_t(exception_ptr)`。运行时：`then` 的回调抛出 `int`，*TRY-SET-VALUE* 捕获并 `set_error(exception_ptr)`；`upon_error` 调用回调返回 0，`set_value(0)`；`sync_wait` 返回 `optional<tuple<int>>`，值为 0。
</details>

!!! question "2. write_env 能覆盖停止令牌吗？"
    外部接收器环境有停止令牌 `t1`，`write_env(sndr, prop(get_stop_token, t2))` 后 `sndr` 看到哪个？外部请求停止时 `sndr` 会被取消吗？

<details markdown="1">
<summary>答案</summary>

看到 `t2`：*join-env* 先问写入的环境（[exec.write.env] ¶4.2）。外部通过 `t1` 请求停止**不会**传到 `sndr`，因为 `sndr` 根本不知道 `t1`——`write_env` 是覆盖，不是合并。若想"两个令牌任一触发都取消"，需要把两个令牌合成一个，这正是 [[exec.spawn]] 中阐述用的 *stop-when* 所做的事。
</details>

## 小结

- 适配器是惰性的；单子适配器转发子发送器属性，多子适配器属性为空；环境以 *FWD-ENV* 传给子发送器。
- `c(sndr)` ≡ `sndr | c`；多参数适配器少给发送器时返回闭包；闭包可用 `|` 组合。
- `then`/`upon_error`/`upon_stopped`：对应处置调用回调，结果作 value 发出；回调抛异常则 `set_error(exception_ptr)`。
- `write_env`：写入的环境优先；`unstoppable` = 写入 `never_stop_token`。
- `into_variant`：多 value 签名 → 一个 variant-of-tuples 签名。
- `stopped_as_optional`、`stopped_as_error`：通过 `let_stopped` 降级实现，消除 stopped 完成。
