---
title: 执行策略
summary: <execution> 中的 seq、par、par_unseq、unseq 四种执行策略及 is_execution_policy；它们只是“允许”并行/向量化的许可证，真正的语义在 [algorithms.parallel.exec]；向量化不安全函数的含义；元素访问函数抛异常一律 terminate；libc++ 的实现状态
status: draft
covers: *, execpol.general, execpol.type, execpol.seq, execpol.par, execpol.parunseq, execpol.unseq, execpol.objects
papers: P0024R2, P1001R2
related: algorithms.parallel.defns, algorithms.parallel.exec, intro.progress, intro.execution, intro.races, except.terminate
tags: 标准库, 并行算法, execution, 向量化
updated: 2026-10-18
---

执行策略（[[g:execution-policy]]）是并行算法重载的第一个实参：`std::sort(std::execution::par, v.begin(), v.end())`。本节（当前位于 [algorithms] 的 26.3.6）只定义了这几个**类型和对象**本身；它们对算法执行方式的真实影响——在哪个线程上调用、调用之间是否有序、什么行为是 UB——写在 [[algorithms.parallel.exec]]，术语（元素访问函数、向量化不安全）写在 [[algorithms.parallel.defns]]。

一个核心观念：执行策略是**许可**而不是**命令**。`par` 的意思是“我（调用者）保证这些元素访问可以并行而不出错，你（实现）**可以**并行”，实现完全可以顺序执行（[algorithms.parallel.exec] ¶8 注 9 明说资源不足时可回退为顺序执行）。

## 总述（[execpol.general]）

¶1：执行策略对象表示算法执行时允许的并行种类，以及由此对**元素访问函数**（[[g:element-access-function]]：迭代器操作、元素操作、用户函数对象等）提出的要求。注 1：实现可以提供额外的、标准之外的执行策略。

## 类型特征 `is_execution_policy`（[execpol.type]）

¶1–¶2：`is_execution_policy<T>` 是 *Cpp17UnaryTypeTrait*，当 `T` 是标准或实现定义的执行策略类型时为 `true_type`。它的用途是在重载决议中把并行重载与非并行重载区分开（`sort(policy, first, last)` 与 `sort(first, last, comp)` 都是三个实参）。并行算法用仅用于说明的概念 *execution-policy* 约束：`is_execution_policy_v<remove_cvref_t<Ep>>`（[[algorithms.parallel.defns#2]]）。

¶3：用户特化 `is_execution_policy` 是 {{ub}}——注 1 说得明白：创建非标准执行策略是实现的特权。

!!! pitfall "`decltype(std::execution::par)` 是 `const` 类型"
    策略对象声明为 `inline constexpr`，所以 `decltype(std::execution::par)` 是 `const parallel_policy`，而 `is_execution_policy_v<const parallel_policy>` 为 `false`。自己写泛型代码时要先 `remove_cvref_t`，正如标准中 *execution-policy* 概念所做的那样。

## 四种策略（[execpol.seq] 至 [execpol.unseq]）与对象（[execpol.objects]）

每个类的定义都是 `{ unspecified }`，每个都“used as a unique type to disambiguate parallel algorithm overloading”——它们本质上是**标签类型**。[execpol.objects] 声明了对应的 `inline constexpr` 对象。

| 对象 | 类型 | 允许 | 调用在哪里执行（[algorithms.parallel.exec]） |
|---|---|---|---|
| `seq` | `sequenced_policy` | 不并行化 | ¶4：全部在调用线程，且不交错 |
| `par` | `parallel_policy` | 多线程 | ¶6：调用线程或库创建的线程；同一线程内的调用**不确定顺序**（[[g:indeterminately-sequenced]]），不会交错 |
| `par_unseq` | `parallel_unsequenced_policy` | 多线程 + 向量化 | ¶7：未指明的线程；同一线程内的调用**无序**（[[g:unsequenced]]），可以交错 |
| `unseq` {{c++20}} | `unsequenced_policy` | 单线程向量化 | ¶5：调用线程内，彼此无序，可以交错 |

注意 `seq` 并不等于“不带策略的老算法”：它仍是并行算法重载，仍受下面“异常即 terminate”的规则约束，而且实现可以复制元素（[algorithms.parallel.exec] ¶3）。

### 元素访问函数抛异常 → `terminate`（各节 ¶2）

!!! std
    During the execution of a parallel algorithm with the `execution::parallel_policy` policy, if the invocation of an element access function exits via an exception, `terminate` is invoked.

四种标准策略**一律如此**（[[except.terminate]]）。这与非并行算法形成鲜明对比——`std::sort(first, last, comp)` 中比较器抛出的异常会正常传播给调用者。原因是：多个线程上可能同时有多个异常，标准没有设计异常聚合机制（Parallelism TS 曾有 `exception_list`，合入 C++17 时被去掉了）。

## “无序”与向量化不安全

`par` 与 `par_unseq` 的区别不在“几个线程”，而在**同一线程内**的调用能否交错。向量化把多次循环迭代合并到一条 SIMD 指令里，于是第 1 次和第 2 次调用的指令是交织执行的——这推翻了 [[intro.execution]] 中“函数执行彼此不交错”的通常保证。

在这种模型下，任何**阻塞式同步**都是灾难：第 1 次调用拿到锁，第 2 次调用在同一线程上交错执行、等待同一把锁——自己等自己，死锁。标准用**向量化不安全**（[[g:vectorization-unsafe]]）这个概念精确划线：

!!! std
    A standard library function is *vectorization-unsafe* if it is specified to synchronize with another function invocation, or another function invocation is specified to synchronize with it, and if it is not a memory allocation or deallocation function or lock-free atomic modify-write operation.

即：规定会建立同步关系（[[g:synchronizes-with]]）的库函数——`mutex::lock`/`unlock`、条件变量、`atomic` 的非无锁操作等——都是向量化不安全的；**例外**是内存分配/释放函数和无锁原子读改写。[algorithms.parallel.exec] ¶5、¶7：在 `unseq` 或 `par_unseq` 算法调用的用户代码中调用向量化不安全函数是 {{ub}}。

```cpp
std::mutex m;
int x = 0;
std::for_each(std::execution::par_unseq, a, a + 2, [&](int) {
    std::lock_guard g(m);   // UB：lock_guard 的构造调用 m.lock()，向量化不安全
    ++x;
});
std::for_each(std::execution::par, a, a + 2, [&](int) {
    std::lock_guard g(m);   // OK：par 下可以用锁同步
    ++x;
});
```

而 `par` 下的数据竞争（[[intro.races]]）、依赖执行顺序的自旋等待则是调用者的责任（[algorithms.parallel.exec] ¶6 例 1、例 2）。`par` 下库创建的线程，若 `std::thread` 提供并发前向进展保证，则提供**并行**前向进展保证（[[g:parallel-forward-progress]]）；`par_unseq` 只提供**弱并行**前向进展保证（[[intro.progress]]）——所以 `par_unseq` 中自旋等待另一次迭代可能永不结束。

## 例子

```cpp run title="execpol.cpp" ok flags="-std=c++2c -fexperimental-library"
#include <algorithm>
#include <cassert>
#include <execution>
#include <functional>
#include <numeric>
#include <type_traits>
#include <vector>

static_assert(std::is_execution_policy_v<std::execution::parallel_policy>);
static_assert(!std::is_execution_policy_v<decltype(std::execution::par_unseq)>);  // const 限定！
static_assert(std::is_execution_policy_v<std::remove_cvref_t<decltype(std::execution::par_unseq)>>);

int main() {
    std::vector<int> v(100000);
    std::iota(v.begin(), v.end(), 0);
    std::sort(std::execution::par, v.begin(), v.end(), std::greater<>{});
    long long sum = std::reduce(std::execution::par_unseq, v.begin(), v.end(), 0LL);
    assert(v.front() == 99999 && sum == 99999LL * 100000 / 2);
    std::for_each(std::execution::unseq, v.begin(), v.end(), [](int& x) { x *= 2; });
    assert(v.front() == 199998);
}
```

!!! impl "libc++ 的实现状态"
    - libc++ 的并行算法（PSTL）仍是**实验性**的：`<execution>` 中的内容受 `_LIBCPP_HAS_EXPERIMENTAL_PSTL` 控制，需要用 `-fexperimental-library` 编译，否则 `std::execution::par` 等名字根本不存在。
    - `<version>` 中 `__cpp_lib_execution` 与 `__cpp_lib_parallel_algorithm` 在 libc++ 23 中都**没有定义**（被注释掉）。
    - 后端在构建 libc++ 时选定（`__config_site` 中的 `_LIBCPP_PSTL_BACKEND_*`）。本机 Homebrew LLVM 23 的配置是 `_LIBCPP_PSTL_BACKEND_LIBDISPATCH`，即在 macOS 上用 GCD 调度；其他可选后端有 `serial` 和 `std_thread`（见 `__pstl/backends/`）。
    - 向量化（`unseq`）在 clang 下通过 `#pragma clang loop vectorize(enable)` 提示实现（`__configuration/pstl.h`），在开启 OpenMP 时改用 `omp simd`。
    - libstdc++ 的并行算法依赖 Intel TBB；MSVC STL 自带线程池实现。

## 历史

- C++17：[[P0024R2]] 把 Parallelism TS 并入标准，引入 `seq`、`par`、`par_unseq` 与 `is_execution_policy`。
- C++20：[[P1001R2]] 增加 `unseq`（单线程向量化）。
- C++23 之后：草案加入了 range 版本的并行算法（以 *execution-policy* 概念约束），执行策略本身未变。注意 [[exec]] 中的 `std::execution` 是 C++26 的 sender/receiver 框架，与这里的执行策略同在 `std::execution` 命名空间、同一个 `<execution>` 头文件中，但概念上无关。

## 思考题

!!! question "1"
    在 `par_unseq` 的 lambda 里调用 `new`/`delete` 是 UB 吗？用 `std::atomic<int>::fetch_add` 呢？用 `std::atomic<BigStruct>` 的 `store` 呢？

<details markdown="1">
<summary>展开查看答案与解析</summary>

`new`/`delete`：不是 UB——向量化不安全的定义明确排除了内存分配/释放函数（实现必须保证其内部同步不妨碍弱并行前向进展，见 [algorithms.parallel.defns] ¶5 注 2）。

`atomic<int>::fetch_add`：在 `atomic<int>` 无锁的平台上不是 UB——无锁的原子读改写操作被明确排除。

`atomic<BigStruct>::store`：大结构体的 `atomic` 通常不是无锁的（内部用锁实现），而且 `store` 本身就可能与读到该值的 `load` 建立同步关系，它又不属于“无锁原子读改写”的豁免范围，因此是向量化不安全的 → UB。
</details>

## 小结

| 策略 | 线程 | 同线程内调用关系 | 可用锁？ | 异常 |
|---|---|---|---|---|
| `seq` | 调用线程 | 有序，不交错 | 可以 | `terminate` |
| `par` | 多线程 | 不确定顺序，不交错 | 可以 | `terminate` |
| `par_unseq` | 多线程 | 无序，可交错 | 不可以（UB） | `terminate` |
| `unseq` | 调用线程 | 无序，可交错 | 不可以（UB） | `terminate` |
