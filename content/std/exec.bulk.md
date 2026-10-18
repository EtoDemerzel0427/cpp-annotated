---
title: bulk、bulk_chunked、bulk_unchunked
summary: 对 [0, shape) 中每个下标执行一次 f(i, values...)，带执行策略；bulk 降级为 bulk_chunked；默认实现在前驱完成的线程上顺序执行——并行只来自调度器 domain 的定制（如 parallel_scheduler）；chunked 与 unchunked 的调用契约；f 适用并行算法元素访问函数的规则
status: done
covers: exec.bulk
papers: P2300R10
related: exec.adapt, exec.snd.transform, exec.par.scheduler, algorithms.parallel.exec, execpol
tags: 标准库, std::execution, 发送器适配器, 并行
updated: 2026-10-18
---

`bulk` 是 `std::execution` 中的"数据并行"原语：前驱完成后，对一个整数下标空间 `[0, shape)` 的每个 `i` 调用一次 `f(i, values...)`，然后把前驱的值原样传下去。它对应于并行 `for_each`，但嵌在发送器链里，可以与调度、取消、错误传播组合。

```cpp title="bulk.cpp"
namespace ex = std::execution;

std::vector<double> v(1'000'000);
auto s = ex::schedule(ex::get_parallel_scheduler())
       | ex::bulk(ex::par, v.size(), [&v](std::size_t i) { v[i] = std::sqrt(double(i)); });
std::this_thread::sync_wait(std::move(s));
```

## 三个算法（¶1–3）

¶1 三者都对下标空间中的每个下标重复执行一个任务。

¶2 `bulk-algo(sndr, policy, shape, f)` 在下列情况下非良构：

- ¶2.1 `sndr` 不是发送器；
- ¶2.2 `is_execution_policy_v<Policy>` 为 false（[[execpol]]）；
- ¶2.3 `Shape`（`decltype(auto(shape))`）不满足 `integral`；
- ¶2.4 `Func`（`decay_t<decltype((f))>`）不模型化 `copy_constructible`。

¶3 否则等价于 *make-sender*(bulk-algo, product-type<P, Shape, Func>{policy, shape, f}, sndr)，`P` 是 `Policy`（可复制时）或 `const Policy&`（否则）——实现定义的执行策略可能不可复制，那就存引用。

三者的区别在 `f` 的调用形式：

| 算法 | `f` 的调用 | 契约（成功时） |
|---|---|---|
| `bulk` | `f(i, args...)` | 每个 `i ∈ [0, shape)` 恰好一次 |
| `bulk_unchunked` | `f(i, args...)` | 同上；*Recommended practice*：每次迭代在**不同的执行代理**上执行 |
| `bulk_chunked` | `f(b, e, args...)` | 若干次，`0 ≤ b < e ≤ shape`，且每个 `i` 恰好落在一次调用的 `[b, e)` 中 |

`bulk_chunked` 让 `f` 一次处理一段连续区间，摊薄调用开销、便于向量化；`bulk_unchunked` 则表达"每个下标是一个独立的任务"，适合每个元素工作量大、或需要每个迭代有自己的执行代理（例如迭代之间要用 barrier 同步）的场景。`bulk` 不指定，交给实现。

## bulk 降级为 bulk_chunked（¶4）

¶4 `bulk.transform_sender(set_value, sndr, env)`：

```cpp
auto [_, data, child] = sndr;
auto& [policy, shape, f] = data;
auto new_f = [func = std::move(f)](Shape begin, Shape end, auto&&... vs)
    noexcept(noexcept(f(begin, vs...))) {
  while (begin != end) func(begin++, vs...);
};
return bulk_chunked(std::move(child), policy, shape, std::move(new_f));
```

注 1：这让 `bulk` 在 connect 到一个其执行 domain 不定制 `bulk` 的接收器时，被表达为 `bulk_chunked`。所以定制者只需实现 `bulk_chunked` 和 `bulk_unchunked`：`bulk` 自动通过 chunked 版本获益（[[exec.snd.transform]] 的递归变换）。

## 默认实现是顺序的（¶5–8）

¶5 `impls-for<bulk_chunked_t>` 的 *complete*：

```cpp
if constexpr (same_as<Tag, set_value_t>) {
  auto& [policy, shape, f] = state;
  constexpr bool nothrow = noexcept(f(auto(shape), auto(shape), args...));
  TRY-EVAL(rcvr, [&]() noexcept(nothrow) {
    f(static_cast<decltype(auto(shape))>(0), auto(shape), args...);
    Tag()(std::move(rcvr), std::forward<Args>(args)...);
  }());
} else {
  Tag()(std::move(rcvr), std::forward<Args>(args)...);
}
```

¶7 `impls-for<bulk_unchunked_t>` 的 *complete* 类似，只是循环：`for (i = 0; i < shape; ++i) f(auto(i), args...);`。

!!! warning "没有定制时，bulk 不并行"
    默认的 `bulk_chunked` 只调用**一次** `f(0, shape, args...)`；默认的 `bulk_unchunked` 是一个普通的 `for` 循环。二者都在**前驱完成的那个执行代理上**同步执行，不会产生任何新的执行代理。执行策略 `par` 只是**允许**并行，不是**要求**并行。

    真正的并行来自 domain 定制：`parallel_scheduler` 的 domain 把 `bulk_chunked`/`bulk_unchunked` 改写成调用其后端的 `schedule_bulk_chunked`/`schedule_bulk_unchunked`（[[exec.par.scheduler]]），`task_scheduler` 同样转发给被擦除调度器的后端（[[exec.task.scheduler]]）。所以 `just() | bulk(par, n, f)` 在 `sync_wait` 下是单线程的；`schedule(get_parallel_scheduler()) | bulk(par, n, f)` 才会分发到线程池。

¶6、¶8 *check-types*：对前驱每个 value 签名 `set_value_t(Ts...)`，要求 `f` 能以 `(Shape, [Shape,] Ts&...)` 调用——注意 `Ts&`：前驱的值以**左值**传给 `f`，所有迭代共享同一份值。

## 语义要求（¶9–10）

¶9 若 connect 出的异步操作启动后不满足下列要求，`connect(out_sndr, rcvr)` 行为未定义——同样主要约束定制实现：

- ¶9.1 若 `sndr` 成功完成，设 `args` 是指代其 value 结果数据的左值（或者，可复制时，它们的 decay 副本）：
  - ¶9.1.1 若 `out_sndr` 也成功完成：`bulk`、`bulk_unchunked` 对每个 `i` 调用 `f(i, args...)`；`bulk_chunked` 以覆盖每个 `i` 恰好一次的区间调用 `f(b, e, args...)`。
  - ¶9.1.2 若 `out_sndr` 以 `set_error(rcvr, eptr)` 完成：可能已经执行了一部分 `f` 的调用；`eptr` 包含 `f` 抛出的异常、或资源分配失败时的 `bad_alloc`、或派生自 `runtime_error` 的异常。
  - ¶9.1.3 若以 `set_stopped` 完成：可能已经执行了一部分 `f` 的调用。
- ¶9.2 `sndr` 不以 value 完成时，完成被转发给接收器。
- ¶9.3 `policy` 描述执行可以如何并行化、`f` 可以如何被应用；**并行算法元素访问函数的许可与要求**（[[algorithms.parallel.exec]]）适用于 `f`。

¶10 注 2：`bulk-algo` 的操作可以在请求取消时以 `set_stopped` 完成，也可以忽略取消请求。

¶9.3 的意义：用 `par_unseq` 时，`f` 不能获取锁、不能做同步操作（因为迭代可能在同一线程上交错执行），和并行算法完全一样。用 `seq` 时，定制实现必须保证调用是顺序的——即使在 GPU 上。

!!! note "错误时 f 被调用的次数不确定"
    ¶9.1.2–9.1.3 明确允许"部分完成"：一个迭代抛异常后，实现可以停止分发剩余迭代，也可以不停止（其他线程上已经在跑的迭代无法撤回）。所以 `f` 不应依赖"出错时其他迭代一定没有执行"或"一定都执行了"。

## 思考题

!!! question "1. bulk 之后的值"
    `just(std::vector<int>(100)) | bulk(par, 100, [](std::size_t i, std::vector<int>& v) { v[i] = i; }) | then([](std::vector<int> v) { return v[99]; })`——`then` 收到的 vector 是 bulk 修改过的那一个吗？

<details markdown="1">
<summary>答案</summary>

是。`bulk` 以左值把前驱的值传给 `f`（*check-types* 检查 `Ts&`），所有迭代修改的是同一个对象；然后 `Tag()(std::move(rcvr), std::forward<Args>(args)...)` 把同一组值继续传给下游。默认实现中 `args` 就是前驱 `set_value` 的实参，`just` 以右值发出它存储的 vector，所以 `bulk` 收到的 `args` 是那个 vector 的右值引用；`f` 通过左值访问修改它，再被转发给 `then`。注意 `f` 的形参写成 `std::vector<int>&`（非 const 左值引用）正是可行的——如果写成按值，每次调用会复制整个 vector。另外各迭代写不同元素，没有数据竞争。
</details>

!!! question "2. shape 为 0"
    `bulk_chunked(s, par, 0, f)` 会调用 `f` 吗？默认实现呢？

<details markdown="1">
<summary>答案</summary>

按 ¶9.1.1.3 的契约，`f(b, e, ...)` 要求 `b < e`，`shape` 为 0 时空区间不需要被覆盖，所以符合契约的实现**零次**调用 `f`。但默认实现（¶5）无条件调用一次 `f(0, shape, args...)`，即 `f(0, 0, args...)`——`b == e`，与 ¶9.1.1.3 的 `b < e` 不一致。由于 ¶9 的语义要求针对 connect 的结果，严格地读，这是默认实现与契约之间的一处小出入；`f` 若写成 `for (i = b; i < e; ++i)`，两种情况的效果相同。写 `f` 时应当容忍空区间。
</details>

## 小结

- `bulk(s, policy, shape, f)`：对每个 `i ∈ [0, shape)` 调用 `f(i, values...)`，然后转发 `s` 的值。
- `bulk` → `bulk_chunked`（降级）；定制者实现 `bulk_chunked`、`bulk_unchunked` 即可。
- 默认实现在前驱完成处**顺序**执行；并行来自调度器 domain 的定制。
- `f` 受并行算法元素访问函数规则约束；出错/取消时可能只执行了部分迭代。
