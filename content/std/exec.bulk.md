---
title: bulk、bulk_chunked、bulk_unchunked
summary: 前驱完成后，对 [0, shape) 中的每个下标调用一次 f(i, values...)，再把前驱的值传下去；默认实现是顺序执行的，并行来自调度器的定制。
status: draft
covers: exec.bulk
papers: P2300R10
related: exec.adapt, exec.snd.transform, exec.par.scheduler, algorithms.parallel.exec, execpol
tags: 标准库, std::execution, 发送器适配器, 并行
updated: 2026-10-19
---

!!! tldr
    - `bulk(sndr, policy, shape, f)` 在前驱成功完成后，对每个 `i ∈ [0, shape)` 调用一次 `f(i, values...)`，然后把前驱的值原样传给下游。
    - 前驱的值以左值传给 `f`，所有迭代共享同一份值。
    - `bulk_chunked` 让 `f` 一次处理一段区间 `[b, e)`，`bulk_unchunked` 每次只处理一个下标；`bulk` 在 connect 前被改写为 `bulk_chunked`。
    - 没有调度器定制时，三者都在前驱完成的线程上顺序执行。并行来自调度器 domain 的定制，例如 `parallel_scheduler`。
    - `f` 要遵守并行算法对元素访问函数的要求；出错或取消时，可能只执行了一部分迭代。

本页的例子用到 C++26 的 `std::execution` 发送器。本机 Clang 23 附带的 libc++ 还没有实现这部分库，例子都没有经过编译验证，因此不加判定标记。

## 发送器链里的并行 for

```cpp title="bulk.cpp"
namespace ex = std::execution;

std::vector<double> v(1'000'000);
auto s = ex::schedule(ex::get_parallel_scheduler())
       | ex::bulk(ex::par, v.size(),
                  [&v](std::size_t i) { v[i] = std::sqrt(double(i)); });
std::this_thread::sync_wait(std::move(s));
```

`bulk` 是 `std::execution` 中的数据并行原语，作用相当于并行的 `for_each`。不同之处在于它是一个[[g:sender-adaptor|发送器适配器]]：它接在另一个[[g:sender|发送器]]（这里是 `schedule(...)`）后面，可以和调度、取消、错误传播组合在一起。

这段代码会把一百万次迭代分发到线程池上。下文会看到，把 `schedule(get_parallel_scheduler())` 换成 `just()`，同样的 `bulk(par, ...)` 就只会在一个线程上顺序执行。

## 三个算法（¶1–3）

¶1 三个算法都对一个下标空间里的每个下标重复执行同一个任务。它们只在 `f` 的调用方式上不同：

| 算法 | `f` 的调用形式 | 成功完成时的保证（¶9.1.1） |
|---|---|---|
| `bulk` | `f(i, args...)` | 每个 `i ∈ [0, shape)` 恰好调用一次 |
| `bulk_unchunked` | `f(i, args...)` | 同上；建议每次迭代在不同的执行代理上执行 |
| `bulk_chunked` | `f(b, e, args...)` | 调用若干次，`0 ≤ b < e ≤ shape`，每个 `i` 恰好落在一次调用的 `[b, e)` 里 |

`bulk_chunked` 让 `f` 一次处理一段连续区间，摊薄调用开销，也便于向量化。`bulk_unchunked` 表示每个下标是一个独立的任务，适合单个元素工作量大、或者迭代之间需要同步（例如用 barrier）而必须各占一个执行代理的场景。`bulk` 不作要求，由实现选择。

¶2 下列情况下 `bulk-algo(sndr, policy, shape, f)` 非良构：

- ¶2.1 `sndr` 不是发送器；
- ¶2.2 `policy` 不是执行策略（`is_execution_policy_v` 为假，见 [[execpol]]）；
- ¶2.3 `shape` 的类型不是整数类型；
- ¶2.4 `f` 的类型不可复制构造。

¶3 否则，结果是一个发送器，以 `{policy, shape, f}` 为数据、以 `sndr` 为子发送器。执行策略可复制时按值保存；实现自定义的执行策略可能不可复制，这时只保存它的 const 引用。

## 默认实现是顺序的（¶4–8）

¶4 `bulk` 在 connect 之前被改写为 `bulk_chunked`，回调包装成一个逐个处理下标的循环：

```cpp
auto new_f = [func = std::move(f)](Shape begin, Shape end, auto&&... vs)
    noexcept(noexcept(f(begin, vs...))) {
  while (begin != end) func(begin++, vs...);
};
return bulk_chunked(std::move(child), policy, shape, std::move(new_f));
```

注 1 说明了用意：如果接收器的执行 domain 没有专门定制 `bulk`，`bulk` 就按 `bulk_chunked` 处理。所以想提供并行实现的调度器只需定制 `bulk_chunked` 和 `bulk_unchunked` 两个算法（改写机制见 [[exec.snd.transform]]）。

¶5 没有定制时，`bulk_chunked` 的默认实现在前驱以值完成后只调用一次 `f(0, shape, args...)`，把整个区间交给 `f`，然后把值转发给接收器。`f` 抛出的异常被捕获，以 `set_error(exception_ptr)` 交给接收器。错误完成和取消完成直接转发。

¶7 `bulk_unchunked` 的默认实现是一个普通循环 `for (i = 0; i < shape; ++i) f(i, args...);`，其余与 `bulk_chunked` 相同。

!!! warning "没有定制时，bulk 不会并行"
    两个默认实现都在前驱完成的那个执行代理上同步执行，不产生新的执行代理。执行策略 `par` 只是允许并行，并不要求并行。

    并行来自 domain 定制。`parallel_scheduler` 的 domain 把 `bulk_chunked`、`bulk_unchunked` 改写为调用后端的 `schedule_bulk_chunked`、`schedule_bulk_unchunked`（[[exec.par.scheduler]]）；`task_scheduler` 也会把它们转发给被擦除的调度器（[[exec.task.scheduler]]）。所以 `just() | bulk(par, n, f)` 交给 `sync_wait` 时只用一个线程，`schedule(get_parallel_scheduler()) | bulk(par, n, f)` 才会分发到线程池。

¶6、¶8 计算完成签名时，*check-types* 对前驱的每一种值完成 `set_value(Ts...)` 检查 `f` 能否以 `(Shape, Ts&...)`（`bulk_chunked` 是 `(Shape, Shape, Ts&...)`）调用，不能就报错。注意形参是 `Ts&`：前驱的值以左值传给 `f`，所有迭代访问的是同一份值。

## 对实现的要求（¶9–10）

¶9 这一段规定了任何实现（包括调度器的定制）都必须满足的行为，否则 connect 的结果行为未定义：

- ¶9.1.1 整个操作成功完成时，`f` 按上面表格中的方式被调用。
- ¶9.1.2 以 `set_error(eptr)` 完成时，`f` 可能已经被调用了一部分。`eptr` 中是 `f` 抛出的异常、分配资源失败时的 `bad_alloc`，或者一个派生自 `runtime_error` 的异常。
- ¶9.1.3 以 `set_stopped` 完成时，`f` 也可能已经被调用了一部分。
- ¶9.2 前驱没有以值完成时，它的完成直接转发给接收器。
- ¶9.3 执行策略描述迭代可以怎样并行。[[algorithms.parallel.exec]] 对并行算法元素访问函数的许可与要求同样适用于 `f`。

¶9.3 的后果与并行算法相同：用 `par_unseq` 时，同一线程上的迭代可能交错执行，`f` 不能获取锁或做其他同步操作；用 `seq` 时，定制实现必须保证调用依次进行，即使在 GPU 上也一样。

¶9.1.2 和 ¶9.1.3 允许部分完成：一次迭代抛出异常后，实现可以停止分发剩余的迭代，也可以不停止，已经在其他线程上运行的迭代也无法撤回。所以 `f` 不能假设出错时其他迭代一定没有执行，也不能假设它们一定都执行了。

¶10 注 2 补充：请求取消时，这些操作可以以 `set_stopped` 完成，也可以不理会取消请求。

## 思考题

!!! question "1. bulk 之后的值"
    ```cpp
    just(std::vector<int>(100))
      | bulk(par, 100, [](std::size_t i, std::vector<int>& v) { v[i] = i; })
      | then([](std::vector<int> v) { return v[99]; })
    ```
    `then` 收到的 vector 是被 `bulk` 修改过的那一个吗？

<details markdown="1">
<summary>答案</summary>

是。`bulk` 以左值把前驱的值传给 `f`，所有迭代修改的是同一个对象，之后同一组值被转发给下游。`just` 以右值发出它保存的 vector，`f` 通过左值引用修改它，`then` 再从这个右值移动构造自己的形参。

`f` 的形参写成 `std::vector<int>&` 正合适；写成按值的话，每次调用都会复制整个 vector，修改也不会传到下游。各迭代写的是不同元素，没有数据竞争。
</details>

!!! question "2. shape 为 0"
    `bulk_chunked(s, par, 0, f)` 会调用 `f` 吗？默认实现呢？

<details markdown="1">
<summary>答案</summary>

按 ¶9.1.1.3，每次调用都要满足 `b < e`。`shape` 为 0 时没有下标需要覆盖，符合要求的实现应该一次也不调用 `f`。

但 ¶5 的默认实现无条件调用一次 `f(0, shape, args...)`，也就是 `f(0, 0, args...)`，这里 `b == e`，与 ¶9.1.1.3 的 `b < e` 不一致。这是草案中默认实现与契约之间的一处小出入。`f` 写成 `for (i = b; i < e; ++i)` 的形式就能容忍空区间，两种情况效果相同。
</details>

## 小结

| 问题 | 答案 |
|---|---|
| `f` 收到什么 | 下标（或区间）加上前驱值的左值 |
| `bulk` 之后的值 | 前驱的值，原样转发 |
| 谁来并行 | 调度器 domain 的定制；默认实现顺序执行 |
| 定制哪些算法 | `bulk_chunked`、`bulk_unchunked`；`bulk` 被改写为前者 |
| 出错或取消时 | 可能只执行了部分迭代 |
