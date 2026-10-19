---
title: when_all
summary: 同时启动多个子发送器，全部完成后才完成；成功时按顺序拼接各子操作的值，任一子操作出错或被取消时请求其余子操作停止。
status: draft
covers: exec.when.all
papers: P2300R10
related: exec.adapt, exec.snd, exec.recv, exec.queries, thread.stoptoken, exec.into.variant
tags: 标准库, std::execution, 发送器适配器, 并发, 取消
updated: 2026-10-19
---

!!! tldr
    - `when_all(s1, s2, ...)` 同时启动所有子发送器，等它们全部完成后才完成；成功时把各子操作的值按顺序拼接成一个值完成。
    - 每个子发送器至多有一种值完成签名；有多种的要先套 `into_variant`，或者改用 `when_all_with_variant`。
    - 子操作看到的停止令牌来自 `when_all` 内部的 `inplace_stop_source`。外部的停止请求会转发进来，某个子操作出错或被取消时，`when_all` 也会自己发出停止请求。
    - 只保留第一个错误；错误优先于取消；一旦有子操作出错或被取消，其他子操作的值就被丢弃。
    - 停止请求只是请求，`when_all` 总要等每个子操作真正完成，不会有子操作在它完成之后还在运行。

本页的例子用到 C++26 的 `std::execution` 发送器。本机 Clang 23 附带的 libc++ 还没有实现这部分库，例子都没有经过编译验证，因此不加判定标记。

## fork-join

```cpp title="when-all.cpp"
namespace ex = std::execution;

auto pool = ex::get_parallel_scheduler();
auto a = ex::schedule(pool) | ex::then([] { return 1; });
auto b = ex::schedule(pool) | ex::then([] { return std::string("two"); });
auto [x, y] =
    std::this_thread::sync_wait(ex::when_all(std::move(a), std::move(b))).value();
// x == 1, y == "two"：值按子发送器的顺序拼接
```

¶1 `when_all` 是 fork-join：它把几个输入[[g:sender|发送器]]合成一个发送器，所有输入都完成后它才完成。成功时，它把所有子操作的值依次拼接，作为自己的值完成。上例中两个子发送器分别产生 `int` 和 `std::string`，`when_all` 就以 `set_value(int, std::string)` 完成。

子操作是 `when_all` 操作的[[g:child-operation|子操作]]（[[exec.async.ops#2]]）。`when_all` 一定在所有子操作都完成之后才完成，这是结构化并发的基本保证：调用者拿到结果时，不会有子操作还在后台运行。

¶2 没有实参，或者有实参不是发送器时，`when_all(sndrs...)` 非良构。¶3 否则结果是一个以 `sndrs...` 为子发送器、不带额外数据的发送器。

## 对子发送器的要求（¶8–9）

¶9 计算完成签名时，*check-types* 对每个子发送器检查两件事：

- 至多有一种值完成签名，否则报错；
- 所有结果数据都能 decay-copy，因为它们要先存起来，等其他子操作完成。

要求是至多一种，而不是恰好一种。没有值完成的子发送器（比如 `just_stopped()`）是允许的，只不过这样整个 `when_all` 不可能成功。有多种值签名的子发送器，比如可能以 `set_value(int)` 或 `set_value(string)` 完成，就要先用 `into_variant` 把它变成只有一种签名 `set_value(variant<tuple<int>, tuple<string>>)`，或者直接用下文的 `when_all_with_variant`。

## 取消兄弟操作：内部的停止令牌（¶5–7、¶10、¶16）

¶10 每个子操作的接收器环境由 *make-when-all-env* 生成。¶6 对这个环境查询 `get_stop_token`，得到的是 `when_all` 自己的 `inplace_stop_source` 的令牌，而不是外部接收器的令牌。其他查询中，[[g:forwarding-query|转发查询]]交给外部环境回答，其余的非良构。

¶16 启动时，`when_all` 先在外部令牌上注册一个回调，再依次启动所有子操作：

```cpp
state.on_stop.emplace(get_stop_token(get_env(rcvr)),
                      on-stop-request{state.stop_src});
(start(ops), ...);
```

外部请求停止时，回调调用 `stop_src.request_stop()`，所有子操作都会看到这个请求。某个子操作出错或被取消时，`when_all` 也直接调用 `stop_src.request_stop()`，通知其余子操作停下。用一个内部令牌而不是直接把外部令牌交给子操作，正是为了让 `when_all` 能自己发起停止。

## 子操作完成时（¶11–14、¶17）

¶11 `when_all` 的状态里有几个关键成员：

```cpp
atomic<size_t> count{sizeof...(sndrs)};          // 还没完成的子操作数
inplace_stop_source stop_src{};
atomic<disposition> disp{disposition::started};  // started、error 或 stopped
errors_variant errors{};                         // 保存第一个错误
values_tuple values{};                           // 每个子操作一个 optional<tuple<值...>>
optional<stop_callback> on_stop{nullopt};        // 外部令牌上的回调
```

¶13 `values` 为每个子发送器准备一个 `optional<tuple<值...>>`。如果某个子发送器没有值签名，这个类型就构不成，整个 `values` 退化为空的 `tuple<>`。¶14 `errors` 是一个 `variant`，能容纳所有子发送器可能的错误类型；¶12 如果复制结果数据可能抛异常，它还能容纳 `exception_ptr`。

¶17 每个子操作完成时，按完成的种类更新 `disp`，然后把 `count` 减一：

| 子操作的完成 | 处理 |
|---|---|
| 错误 | 用 `disp.exchange(error)` 把状态改成 error；如果之前不是 error，就请求停止，并保存这个错误 |
| 取消 | 只有 `disp` 仍是 started 时，才把它改成 stopped 并请求停止 |
| 值 | 只有 `disp` 仍是 started 时，才把值存进 `values` |
| 任何一种 | 把 `count` 减一，减到 0 时整体完成 |

由此得到三条规则：

- 错误优先于取消。`exchange` 无条件写入 error，即使之前已经是 stopped；而 stopped 只能从 started 变过来。
- 只保留第一个错误。后来的错误发现 `exchange` 返回的已经是 error，什么也不做。
- 一旦 `disp` 离开 started，后到的值不再保存，已经保存的值最后也不会用到。

保存值时如果复制抛出异常，处理函数会递归调用自己，把这次完成当作 `set_error(exception_ptr)` 处理，然后直接返回。递归调用里已经减过一次 `count`，所以这里不再减。

## 整体完成（¶15）

最后一个子操作把 `count` 减到 0 时，调用 *complete*：

- ¶15.1 `disp` 仍是 started：把每个 `optional<tuple<...>>` 解开、拼接，以 `set_value` 交给外部接收器。
- ¶15.2 `disp` 是 error：以保存的那个错误调用 `set_error`。
- ¶15.3 否则（stopped）：只要有一个子发送器可能以取消完成，就调用 `set_stopped`。

每个分支在完成之前都先 `on_stop.reset()`，注销外部令牌上的回调。[[exec.recv#3]] 只保证外部停止令牌在异步操作的生存期内有效，而生存期在调用完成函数时就结束了，所以注册在它上面的回调必须在此之前销毁。

`when_all` 在最后一个完成的子操作所在的执行代理上完成，事先无法确定是哪一个。所以它一般不报告[[g:completion-scheduler|完成调度器]]（[[exec.snd.general#4]]），只在各子操作的完成 domain 能统一时报告完成 domain（[[exec.snd.general#3]]）。

假设两个子发送器分别以 `set_value(A...)` 和 `set_value(B...)` 完成，`when_all` 的完成签名是：

- `set_value_t(decay_t<A>..., decay_t<B>...)`；
- 各子发送器的错误签名（错误类型经过 decay），需要时再加上 `set_error_t(exception_ptr)`；
- `set_stopped_t()`，当且仅当某个子发送器可能以取消完成。

外部的停止请求本身不会让 `when_all` 以取消完成。如果所有子操作都不理会请求、照常以值完成，`disp` 一直是 started，结果仍是 `set_value`。

## when_all_with_variant（¶18–19）

¶18–19 `when_all_with_variant(sndrs...)` 在 connect 时被改写为 `when_all(into_variant(sndrs)...)`，除非接收器的 domain 专门定制了它（注 1）。每个子发送器先被 `into_variant` 合成一种值签名，所以它可以接受有多种值签名的子发送器。

## 常见误解

### when_all 不是 when_any

`when_all` 等待所有子操作完成，标准里没有一完成就返回的 `when_any`。一个子操作出错后，其他子操作也不会立即停下：停止请求只是请求，子操作可以不理会它（例如 [[exec.bulk#10]] 明确允许 `bulk` 忽略取消请求）。`when_all` 会一直等到它们真正完成。

### 永远不会发生的值完成

`when_all(just(1), just_stopped())` 的第二个子发送器没有值签名，`values` 退化为 `tuple<>`。第二个子操作必然以取消完成，所以 `disp` 不可能停在 started，¶15.1 的 `set_value` 分支在运行时走不到。

但这个分支不在 `if constexpr` 里，仍然是潜在求值的。完成签名是按默认实现中潜在求值的完成操作计算的（[[exec.snd.general#1]]），所以结果的签名里会有一个 `set_value_t()`，代表一个永远不会发生的完成。

## 思考题

!!! question "1. 两个子操作同时出错"
    两个子操作几乎同时以不同的错误完成。外部接收器收到哪一个？有数据竞争吗？

<details markdown="1">
<summary>答案</summary>

收到的是 `disp.exchange(error)` 返回值不为 error 的那一个，也就是在 `disp` 的修改顺序中先完成 exchange 的那个。

没有数据竞争。`disp` 和 `count` 都是原子对象；`errors` 只由赢得 exchange 的那个子操作写入；读取 `errors` 的 *complete* 发生在最后一次递减 `count` 之后。`count` 的递减是默认 `seq_cst` 的读-改-写操作，建立了写 `errors` 与读 `errors` 之间的 happens-before 关系（[[intro.races]]）。
</details>

!!! question "2. 外部取消与子操作的取消"
    外部请求停止，两个子操作都以取消完成，`when_all` 以什么完成？如果其中一个在收到停止请求前已经以值完成了呢？

<details markdown="1">
<summary>答案</summary>

外部请求停止时，回调调用 `stop_src.request_stop()`，子操作看到停止请求。第一个以取消完成的子操作把 `disp` 从 started 改成 stopped，第二个的 `compare_exchange` 失败，什么也不做。最后 *complete* 走 ¶15.3，调用 `set_stopped`。

如果其中一个先以值完成，那时 `disp` 还是 started，值会存进 `values`。但最终 `disp` 是 stopped，存下的值被丢弃，`when_all` 仍以取消完成。
</details>

## 小结

| 问题 | 答案 |
|---|---|
| 何时完成 | 所有子操作都完成之后，在最后一个完成的子操作所在的执行代理上 |
| 成功的结果 | 各子操作的值按顺序拼接 |
| 对子发送器的要求 | 至多一种值签名，结果可 decay-copy |
| 子操作的停止令牌 | `when_all` 内部 `inplace_stop_source` 的令牌 |
| 多个子操作失败 | 第一个错误胜出；错误优先于取消 |
| 多种值签名 | 先 `into_variant`，或用 `when_all_with_variant` |

<details class="fine" markdown="1"><summary>其余条文</summary>

¶4 *impls-for*<when_all_t> 定制了 *get-env*、*get-state*、*start*、*complete* 和 *check-types*。

¶5–7 定义 *make-when-all-env* 和对应的类型别名 *when-all-env*<Env>。¶8 *check-types* 用 *indices-for*<Sndr> 遍历每个子发送器。

¶11 *get-state* 通过 *make-state* 构造上面列出的状态对象。¶14 的 `errors` 以一个空类型 *none-such* 作为默认的第一个备选，去掉重复类型。

</details>
