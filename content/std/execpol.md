---
title: 执行策略
summary: <execution> 中的四个执行策略对象 seq、par、par_unseq、unseq 及其类型，类型特征 is_execution_policy，以及四种策略共同的规定：元素访问函数抛出异常时调用 terminate。
status: done
covers: *, execpol.general, execpol.type, execpol.seq, execpol.par, execpol.parunseq, execpol.unseq, execpol.objects
papers: P0024R2, P1001R2
related: algorithms.parallel, intro.progress, intro.execution, intro.races, except.terminate
tags: 标准库, 并行算法, execution, 向量化
updated: 2026-10-19
---

!!! tldr
    - 标准定义了四个执行策略对象：`seq`、`par`、`par_unseq`、`unseq`，它们是标签，用来选中算法的并行重载。
    - 策略表示允许哪种并行，不表示一定并行。每种策略下调用在哪个线程、按什么顺序进行，规定在 [[algorithms.parallel]]。
    - 四种策略都规定：元素访问函数抛出异常时调用 `std::terminate`。
    - `is_execution_policy<T>` 判断 `T` 是否为执行策略类型，用户不能特化它。策略对象是 `const` 的，泛型代码里要先去掉 cv 限定和引用。

```cpp run title="execpol.cpp" ok flags="-std=c++2c -fexperimental-library"
#include <algorithm>
#include <cassert>
#include <execution>
#include <functional>
#include <numeric>
#include <type_traits>
#include <vector>

namespace ex = std::execution;
static_assert(std::is_execution_policy_v<ex::parallel_policy>);
static_assert(!std::is_execution_policy_v<decltype(ex::par)>);  // const parallel_policy
static_assert(std::is_execution_policy_v<
                std::remove_cvref_t<decltype(ex::par)>>);

int main() {
  std::vector<int> v(100000);
  std::iota(v.begin(), v.end(), 0);
  std::sort(ex::par, v.begin(), v.end(), std::greater<>{});
  long long sum = std::reduce(ex::par_unseq, v.begin(), v.end(), 0LL);
  assert(v.front() == 99999 && sum == 99999LL * 100000 / 2);
  std::for_each(ex::unseq, v.begin(), v.end(), [](int& x) { x *= 2; });
  assert(v.front() == 199998);
}
```

本机 libc++ 需要 `-fexperimental-library` 才提供这些名字，见 [[algorithms.parallel]] 页尾的实现现状。

## 四种策略 [execpol.general]

¶1 执行策略类型的对象表示算法执行时允许哪种并行，以及由此对**元素访问函数**（[[g:element-access-function]]：迭代器操作、元素操作、用户提供的函数对象等）提出的要求。这些类型声明在 `<execution>` 中。

[execpol.objects] 为每个类型声明了一个 `inline constexpr` 对象。各类型的定义都是 `{ unspecified }`，标准对它们的唯一用途是作为一个独特的类型，在重载决议中选中并行重载：

| 对象 | 类型 | 允许 | 执行方式 |
|---|---|---|---|
| `seq` | `sequenced_policy` | 不并行 | 全部在调用线程，不交错 |
| `par` | `parallel_policy` | 多线程 | 可以在多个线程上；同一线程上不交错 |
| `par_unseq` | `parallel_unsequenced_policy` | 多线程和向量化 | 可以在多个线程上；同一线程上可以交错 |
| `unseq` {{c++20}} | `unsequenced_policy` | 单线程向量化 | 全部在调用线程，可以交错 |

最后一列的精确规定在 [[algorithms.parallel.exec]] ¶4–¶7。同一线程上的调用可以交错，意味着在其中加锁是未定义行为，`unseq` 和 `par_unseq` 都是如此。

`par` 的意思是：调用者保证这些元素访问可以并行而不出错，实现可以并行。实现也可以不并行，资源不足时退回到顺序执行完全符合标准（[[algorithms.parallel.exec#8]]）。

注 1 说，实现可以提供标准之外的执行策略，作为针对特殊并行架构的扩展。

## 抛出异常即终止（各节 ¶2）

!!! std
    During the execution of a parallel algorithm with the `execution::parallel_policy` policy, if the invocation of an element access function exits via an exception, `terminate` is invoked.

[execpol.seq]、[execpol.par]、[execpol.parunseq]、[execpol.unseq] 的 ¶2 写法相同，四种策略一律调用 `terminate`（[[except.terminate]]）。不带策略的 `std::sort(first, last, comp)` 中，比较函数抛出的异常会传给调用方；带上 `seq` 之后就不会了。多个线程上可能同时抛出多个异常，标准没有设计把它们收集起来的机制。

## `is_execution_policy` [execpol.type]

¶2 `is_execution_policy<T>` 是一个一元类型特征。`T` 是标准的或实现定义的执行策略类型时，它派生自 `true_type`，否则派生自 `false_type`。¶1 说明它的用途：把执行策略与其他实参区分开，避免重载决议出现歧义。`sort(policy, first, last)` 和 `sort(first, last, comp)` 都是三个实参，靠它才能分开（[[algorithms.parallel.overloads#4]]）。

¶3 程序为 `is_execution_policy` 添加特化是{{ub}}。注 1 说，这保留了只有实现能创建非标准执行策略的特权。

!!! pitfall "`decltype(std::execution::par)` 带 `const`"
    策略对象声明为 `inline constexpr`，所以 `decltype(std::execution::par)` 是 `const parallel_policy`，而 `is_execution_policy_v<const parallel_policy>` 为 `false`。泛型代码里要先用 `remove_cvref_t`，标准的 *execution-policy* 概念就是这样写的（[[algorithms.parallel.defns#2]]）。

## 演进

C++17 的 [[P0024R2]] 把 Parallelism TS 并入标准，引入 `seq`、`par`、`par_unseq` 和 `is_execution_policy`。C++20 的 [[P1001R2]] 加入了 `unseq`。C++26 的并行 `ranges` 重载沿用这四个策略，没有改变它们。

[[exec]] 中 C++26 的 sender/receiver 框架也在命名空间 `std::execution` 和头文件 `<execution>` 中，但与这里的执行策略是两套独立的设施。

## 思考题

!!! question "思考题"
    在 `par_unseq` 的 lambda 里调用 `new` 和 `delete` 是未定义行为吗？调用 `std::atomic<int>::fetch_add` 呢？调用 `std::mutex::lock` 呢？

<details markdown="1">
<summary>答案</summary>

`new` 和 `delete` 可以：向量化不安全的定义明确排除了内存分配和释放函数（[[algorithms.parallel.defns#5]]）。

`std::atomic<int>` 无锁时，`fetch_add` 可以：无锁的原子读改写操作也被排除了。

`mutex::lock` 与之前的 `unlock` 同步，属于向量化不安全的函数，在 `par_unseq` 中调用是未定义行为（[[algorithms.parallel.exec#7]]）。
</details>
