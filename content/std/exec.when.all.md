---
title: when_all
summary: 并发启动多个子发送器、全部完成后再完成；成功时拼接所有子操作的值；任一出错或取消就通过内部 inplace_stop_source 请求其余子操作停止，error 优先于 stopped；每个子发送器至多一种 value 签名；when_all_with_variant 降级为 when_all(into_variant(s)...)
status: done
covers: exec.when.all
papers: P2300R10
related: exec.adapt, exec.snd, exec.recv, exec.queries, thread.stoptoken, exec.into.variant
tags: 标准库, std::execution, 发送器适配器, 并发, 取消
updated: 2026-10-18
---

`when_all(s1, s2, ...)` 是 fork-join：同时启动所有子发送器，等它们**全部**完成后才完成。它是本章展示"结构化并发 + 取消"最完整的一个算法：子操作是 `when_all` 操作的子操作（[[exec.async.ops#2]]），一个失败时其余的被**请求停止**，并且 `when_all` 一定等到所有子操作都完成之后才完成——不会有子操作在 `when_all` 完成之后还在跑。

```cpp title="when-all.cpp"
namespace ex = std::execution;

auto pool = ex::get_parallel_scheduler();
auto a = ex::schedule(pool) | ex::then([] { return 1; });
auto b = ex::schedule(pool) | ex::then([] { return std::string("two"); });
auto [x, y] = std::this_thread::sync_wait(ex::when_all(std::move(a), std::move(b))).value();
// x == 1, y == "two"：值按子发送器的顺序拼接
```

## 定义（¶1–3）

¶1 `when_all` 和 `when_all_with_variant` 把多个输入发送器适配成一个"所有输入都完成后才完成"的发送器。`when_all` 只接受**只有一种 value 完成签名**的子发送器，成功时把所有子操作的 value 结果数据**拼接**成自己的 value 完成。`when_all_with_variant(sndrs...)` 语义上等价于 `when_all(into_variant(sndrs)...)`。

¶2 没有实参，或者有实参不是发送器时，二者都非良构。

¶3 `when_all(sndrs...)` ≡ *make-sender*(when_all, {}, sndrs...)。

## 类型检查（¶8–9）

¶9 *check-types*：对每个子发送器 `Child`，在 *when-all-env*<Env> 下取其签名 `cs`：

```cpp
if constexpr (cs.count-of(set_value) >= 2)
  throw unspecified-exception();
decay-copyable-result-datums(cs);
```

两条：**至多一种 value 签名**；所有结果数据**能 decay-copy**（因为要存起来等其他子操作）。

"至多一种"而不是"恰好一种"：没有 value 完成的子发送器（比如 `just_stopped()`）是允许的——它只会让整个 `when_all` 不可能成功。有多种 value 签名的子发送器则必须先套 `into_variant`，或者直接用 `when_all_with_variant`。

## 子操作的环境：自己的停止令牌（¶5–7、¶10）

¶5–6 *make-when-all-env*(stop_src, env) 返回一个环境 `e`：

- `e.query(get_stop_token)` 是 `stop_src.get_token()`——`when_all` **自己的** `inplace_stop_source` 的令牌；
- 其他查询，若是转发查询则转给外部环境，否则非良构。

¶10 *get-env*：每个子接收器的环境都是 *make-when-all-env*(state.stop-src, get_env(rcvr))。

所以子操作看到的停止令牌**不是**外部的，而是 `when_all` 内部的。外部的停止请求通过一个回调转发进来（见 *start*）；内部也可以自己发起停止请求（某个子操作失败时）。这就是"取消兄弟操作"的机制。

## 状态（¶11–14）

```cpp
enum class disposition { started, error, stopped };

struct state-type {
  void arrive(Rcvr& rcvr) noexcept { if (0 == --count) complete(rcvr); }
  void complete(Rcvr& rcvr) noexcept;

  atomic<size_t> count{sizeof...(sndrs)};
  inplace_stop_source stop_src{};
  atomic<disposition> disp{disposition::started};
  errors_variant errors{};
  values_tuple values{};
  optional<stop_callback> on_stop{nullopt};
};
```

- `count`：还没完成的子操作数，原子递减；
- `disp`：当前整体处置，原子；
- ¶13 `values`：`tuple<value_types_of_t<Sndrs, FWD-ENV-T(env_of_t<Rcvr>), decayed-tuple, optional>...>`——每个子发送器一个 `optional<tuple<值...>>`（*Variant* 位置用的是 `optional`，于是"恰好一种签名"成了 `optional<tuple<...>>`；如果某个子发送器没有 value 签名，`optional<>` 非良构，整个类型退化为 `tuple<>`）；
- ¶14 `errors`：`variant<none-such, copy-fail, Es...>`，`Es` 是所有子发送器可能的错误类型（decay 后），*copy-fail* 是 `exception_ptr`（若复制结果数据可能抛异常）否则 *none-such*。

## 启动（¶16）

```cpp
state.on_stop.emplace(get_stop_token(get_env(rcvr)), on-stop-request{state.stop_src});
(start(ops), ...);
```

先在**外部**令牌上注册回调：外部请求停止时，调用 `stop_src.request_stop()`，进而通知所有子操作。然后依次启动所有子操作。

## 子操作完成（¶17）

```cpp
if constexpr (same_as<Set, set_error_t>) {
  if (disposition::error != state.disp.exchange(disposition::error)) {   // 第一个错误
    state.stop_src.request_stop();
    TRY-EMPLACE-ERROR(state.errors, std::forward<Args>(args)...);
  }
} else if constexpr (same_as<Set, set_stopped_t>) {
  auto expected = disposition::started;
  if (state.disp.compare_exchange_strong(expected, disposition::stopped)) {
    state.stop_src.request_stop();
  }
} else if constexpr (!same_as<decltype(State::values), tuple<>>) {
  if (state.disp == disposition::started) {
    auto& opt = get<Index::value>(state.values);
    TRY-EMPLACE-VALUE(complete, opt, std::forward<Args>(args)...);
  }
}
state.arrive(rcvr);
```

把这段代码的语义整理成规则：

| 子操作完成为 | 动作 |
|---|---|
| error | 若之前不是 error：请求停止，保存**这个**错误。之后的错误被忽略 |
| stopped | 若之前是 started：改为 stopped，请求停止。若已经是 error，**不覆盖** |
| value | 若仍是 started：保存值。否则丢弃 |
| （任何） | `arrive`：计数减一，到 0 时整体完成 |

于是：

- **error 优先于 stopped**：`exchange(error)` 无条件写入 error，哪怕之前是 stopped；而 stopped 只能从 started 转换过来。
- **只保留第一个错误**：后来的错误看到 `exchange` 返回 error，什么也不做。
- 保存值时若复制抛异常（*TRY-EMPLACE-VALUE*），递归调用 `complete` 自己，把它当作一个 `set_error(exception_ptr)` 处理，然后 `return`——注意这里 `return` 跳过了 `arrive`，因为递归调用里已经 `arrive` 过一次。

## 整体完成（¶15）

最后一个子操作 `arrive` 时调用 `complete(rcvr)`：

- ¶15.1 `disp` 为 started：`on_stop.reset()`，然后把每个 `optional<tuple<...>>` 解开、`tuple_cat` 拼成一个大 tuple，`set_value(std::move(rcvr), std::move(值)...)`。
- ¶15.2 为 error：`on_stop.reset()`，`visit` 错误 variant，`set_error(std::move(rcvr), std::move(error))`。
- ¶15.3 否则（stopped）：若有子发送器的签名包含 `set_stopped_t()`，`on_stop.reset()` 后 `set_stopped(std::move(rcvr))`。

每个分支都**先** `on_stop.reset()` 再完成——这是 [[exec.recv]] ¶3 的要求：外部令牌上的回调必须在完成之前注销。

`when_all` 在**最后一个**子操作完成的那个执行代理上完成。所以它一般不能报告完成调度器（[[exec.snd.general#4]]），只在所有子操作的完成 domain 能统一时报告完成 domain（[[exec.snd.general#3]] 的 *COMMON-DOMAIN*）。

签名总结（设子发送器签名分别为 `set_value_t(A...)`、`set_value_t(B...)`）：

- `set_value_t(decay_t<A>..., decay_t<B>...)`
- 各子发送器的 `set_error_t(decay_t<E>)`，必要时加 `set_error_t(exception_ptr)`
- `set_stopped_t()`：当且仅当某个子发送器在 *when-all-env* 下的签名含 `set_stopped_t()`（¶15.3 的 *sends-stopped*）。外部请求停止本身不会让 `when_all` 以 stopped 完成：若所有子操作都忽略请求、以 value 完成，`disp` 始终是 started，结果仍是 `set_value`。

## when_all_with_variant（¶18–19）

¶18 `when_all_with_variant(sndrs...)` ≡ *make-sender*(when_all_with_variant, {}, sndrs...)。

¶19 在 `transform_sender` 的 `set_value` 阶段降级为 `when_all(into_variant(child)...)`。注 1：这使它在 connect 到不定制 `when_all_with_variant` 的 domain 时变成 `when_all(into_variant(sndrs)...)`。

## 陷阱

!!! pitfall "when_all 不提供“任一完成即返回”"
    `when_all` 等**所有**子操作；没有标准的 `when_any`。也不要指望"一个出错，其他立即停下"：请求停止只是一个请求，子操作可以忽略它（[[exec.bulk]] 注 2 就明确允许）。`when_all` 会耐心等到所有子操作真的完成。

!!! pitfall "子发送器没有 value 签名"
    `when_all(just(1), just_stopped())`：第二个子发送器没有 value 签名，`values_tuple` 退化为 `tuple<>`。¶15.1 的 `set_value` 分支此时调用 `set_value(std::move(rcvr))`——但由于第二个子操作必然以 stopped 完成，`disp` 不可能保持 started，这个分支运行时不会走到。签名计算按"潜在求值"进行，结果的签名里仍可能出现 `set_value_t()`——一个永远不会发生的完成。

## 思考题

!!! question "1. 两个子操作同时出错"
    两个子操作几乎同时以不同的错误完成。外部接收器收到哪个？有数据竞争吗？

<details markdown="1">
<summary>答案</summary>

收到 `disp.exchange(error)` 时返回值不是 error 的那一个——即在原子变量 `disp` 的修改顺序中先完成 exchange 的那个。没有数据竞争：`disp`、`count` 都是原子的；`errors` 只被"赢得 exchange 的那一个"写入；最终读取 `errors` 的 `complete` 在最后一个 `arrive` 之后执行，`count` 的原子递减（默认 `seq_cst`）建立了写 `errors` 与读 `errors` 之间的 happens-before 关系（[[intro.races]]）。
</details>

!!! question "2. 外部取消与子操作的 stopped"
    外部请求停止，两个子操作都以 stopped 完成。`when_all` 以什么完成？如果其中一个在收到停止请求前已经以 value 完成了呢？

<details markdown="1">
<summary>答案</summary>

外部请求停止 → 回调 `stop_src.request_stop()` → 子操作看到停止请求。第一个以 stopped 完成的子操作把 `disp` 从 started 改为 stopped；第二个看到 `compare_exchange` 失败，什么也不做。最后 `complete` 走 ¶15.3：`set_stopped`。若其中一个先以 value 完成，它的值被存进 `values`（那时 `disp` 还是 started），但最终 `disp` 是 stopped，存下的值被**丢弃**，整体仍以 stopped 完成。
</details>

## 小结

- `when_all(s...)`：同时启动、全部完成后完成；值按顺序拼接。
- 每个子发送器至多一种 value 签名，结果须可 decay-copy；多签名用 `into_variant` / `when_all_with_variant`。
- 子操作的停止令牌来自 `when_all` 内部的 `inplace_stop_source`；外部停止请求经回调转发进来。
- 第一个 error 胜出并请求停止兄弟；error 优先于 stopped；`disp` 一旦离开 started，后续的值被丢弃。
- 完成前先注销外部令牌上的回调。
