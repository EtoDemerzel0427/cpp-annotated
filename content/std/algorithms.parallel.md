---
title: 并行算法
summary: 带执行策略的算法重载的法律框架——什么是并行算法与元素访问函数、用户函数对象不得经实参修改对象、seq/unseq/par/par_unseq 下元素访问函数在哪个线程以何种顺序执行、何时是 UB、forward progress 的委托、临时内存不足抛 bad_alloc 而元素访问函数抛异常则 terminate、复杂度从“恰好 N”放宽为 O(N)，以及 libc++ 的实现状况
status: done
covers: algorithms.parallel.defns, algorithms.parallel.user, algorithms.parallel.exec, algorithms.parallel.exceptions, algorithms.parallel.overloads
papers: P0024R2, P1001R2
related: execpol, algorithms.requirements, intro.execution, intro.progress, intro.races, except.terminate, numeric.ops
tags: 标准库, 并行算法, 执行策略, 向量化, 数据竞争, forward progress
updated: 2026-10-18
---

C++17 把 Parallelism TS 并入标准（[[P0024R2]]）：大多数算法多了一个以**执行策略**（[[g:execution-policy]]）为第一个形参的重载，`std::sort(std::execution::par, v.begin(), v.end())`。本节回答的问题是：传入策略之后，算法对你的迭代器、元素和函数对象**可能做什么**，你的代码**必须忍受什么**。

执行策略类型和对象本身（`seq`、`par`、`par_unseq`、`unseq`，`is_execution_policy`，各策略下异常即 `terminate`）在 [[execpol]] 一页讲；本页是它们的语义基础。前置知识：求值顺序中“无序”与“不确定顺序”的区别（[[intro.execution]]）、数据竞争（[[intro.races]]）、forward progress 的三个等级（[[intro.progress]]）。

## 什么是并行算法（[algorithms.parallel.defns] ¶1–¶2）

¶2：**并行算法**（[[g:parallel-algorithm]]）是本文件中列出的、带有名为 `ExecutionPolicy` 的模板形参，或受仅用于说明的概念约束的函数模板：

```cpp
template<class Ep>
  concept execution-policy = is_execution_policy_v<remove_cvref_t<Ep>>;   // exposition only
```

这样的形参叫**执行策略模板形参**（[[g:execution-policy-template-parameter]]）。经典并行重载用 `class ExecutionPolicy`（靠 [algorithms.parallel.overloads] ¶4 的“不参与重载决议”来过滤），C++26 新增的并行 ranges 重载直接写 `execution-policy Ep`。

## 元素访问函数（¶3–¶4）

!!! std
    These functions are herein called *element access functions*.

¶3 列出了并行算法“通过实参间接访问对象”时调用的四类函数，统称**元素访问函数**（[[g:element-access-function]]）：

1. 算法实例化所用的迭代器、哨位或 `mdspan` 类型的该类别的所有操作（¶3.1）；
2. 规范要求的、对序列元素的操作（¶3.2）；
3. 规范要求在执行中调用的用户提供的可调用对象（¶3.3）；
4. 规范要求的、对这些可调用对象的操作（¶3.4）——比如复制它们。

¶4 例 1 以 `sort` 为例：随机访问迭代器的操作、元素上的 `swap`、用户的 `Compare`。

这个概念之所以重要，是因为后面所有关于“在哪个线程执行”“是否有序”“抛异常怎么办”的规则都是**以元素访问函数为单位**表述的。注意它不止包含你的 lambda——迭代器的 `operator++`、元素的移动赋值也都算。一个在 `operator*` 里打日志、加锁的迭代器，在 `par_unseq` 下同样受约束。

## 向量化不安全（¶5）

¶5 定义**向量化不安全**（[[g:vectorization-unsafe]]）：规定会与其他调用**同步**（synchronize with）的标准库函数——但内存分配/释放函数和无锁原子读改写除外。例 2：在 `par_unseq` 的 `for_each` 里使用 `lock_guard` 是错误的，因为两次 lambda 调用可能交错在**同一个**执行线程上，第二次 `m.lock()` 会在同一线程上二次加锁而死锁。注 2 同时要求实现：库内部的同步不得妨碍弱并行 forward progress 线程的进展。详细讨论见 [[execpol]]。

## 对用户函数对象的要求（[algorithms.parallel.user]）

¶1：除非另有规定，传给并行算法的 `Predicate`、`BinaryPredicate`、`Compare`、`UnaryOperation`、`BinaryOperation`、`BinaryOperation1/2`、`BinaryDivideOp` 类型的对象，或受语义要求含 `regular_invocable` 的概念约束的对象，以及（当使用默认谓词/运算时）对应的运算符，**不得直接或间接地经实参修改对象，也不得依赖所提供对象的身份**。

两点比非并行版本更严：

- 非并行的 `std::transform` 只禁止修改**区间内**元素；并行版的 `op` 连经实参修改**任何**对象都不行。
- “不得依赖对象身份”：下文 [algorithms.parallel.exec] ¶3 允许实现复制元素，`&x == &v[i]` 这类判断不再可靠。

“另有规定”的例子：`for_each`/`for_each_n` 的 `f` **可以**修改实参（[[alg.foreach#19]] 的 Remarks 明确写了 “`f` may modify objects via its arguments”），`generate` 的 `gen` 也可以（[[alg.generate#6]]）。

## 执行策略对执行方式的影响（[algorithms.parallel.exec]）

### 被修改的对象不会被并发访问（¶2）

若一个对象被某个元素访问函数修改，算法不会对该对象进行其他**未同步**的访问。注 1 列出“修改性”的元素访问函数：`swap`、`++`、`--`、`@=`、赋值（对赋值和复合赋值只算左操作数）。这是实现对你的承诺：`std::sort(par, ...)` 内部不会让两个线程同时 `swap` 同一个元素。

### 实现可以复制可平凡复制的元素（¶3）

!!! std
    Unless otherwise stated, implementations may make arbitrary copies of elements (with type `T`) from sequences where `is_trivially_copy_constructible_v<T>` and `is_trivially_destructible_v<T>` are true.

例如向量化实现把一批 `int` 装进 SIMD 寄存器，或者分块时把元素复制到线程局部缓冲区。注 2：于是用户函数对象不能依赖实参的对象身份。`for_each`/`for_each_n` 是“另有规定”的例外：它们的 Remarks 明确说实现**没有**这个自由——毕竟 `for_each` 的意义常常就是原地修改元素。

### 四种策略的执行模型（¶4–¶7）

| 策略 | 在哪执行 | 同一线程内的调用之间 | 能否用 `mutex` | 段落 |
|---|---|---|---|---|
| `sequenced_policy` | 全在调用线程 | 不交错（按 [[intro.execution]] 的通常规则） | 能 | ¶4 |
| `unsequenced_policy` | 全在调用线程 | **无序**，可以交错 | 调用向量化不安全函数是 {{ub}} | ¶5 |
| `parallel_policy` | 调用线程或库创建的线程 | **不确定顺序**（[[g:indeterminately-sequenced]]） | 能，但要自己避免数据竞争与死锁 | ¶6 |
| `parallel_unsequenced_policy` | 未指明的线程 | **无序**（[[g:unsequenced]]），可以交错 | 调用向量化不安全函数是 {{ub}} | ¶7 |

“无序且可以交错”覆盖了 [[intro.execution]] 中“函数执行彼此不重叠”的通常保证（注 4、注 7）——这正是 SIMD 化所需的许可：编译器把四次循环迭代的指令揉进一组向量指令里。

¶6 的 forward progress 规定：若 `std::thread`/`std::jthread` 创建的线程提供并发 forward progress 保证，则库为并行算法隐式创建的线程提供**并行** forward progress 保证（[[g:parallel-forward-progress]]）；否则由实现定义。¶7：`par_unseq` 下库创建的线程只提供**弱并行**保证（[[g:weakly-parallel-forward-progress]]）。

¶6 的三个例子把“调用者的责任”讲得很具体：

```cpp
int a[] = {0, 1};
std::vector<int> v;
std::for_each(std::execution::par, std::begin(a), std::end(a), [&](int i) {
    v.push_back(i * 2 + 1);   // UB: 数据竞争
});
```

例 2 更微妙：两次迭代用 `atomic` 互相等待（自旋直到对方改变 `x`）。在 `par` 下这**不保证终止**——实现完全可以在同一线程上依次执行两次调用，第一次就永远在自旋。这说明 `par` 只是**允许**并行，而非**保证**并行；不能写依赖于“另一个元素访问函数会同时运行”的代码。例 3 则说明在 `par` 下用 `mutex` 保护共享状态是正确的（只是可能很慢）。

### 允许回退为顺序执行（¶8）

注 9：`unseq`、`par`、`par_unseq` 的语义允许实现在无法并行化时（例如资源不足）回退为顺序执行。所以“传了 `par` 就会多线程”从来不是标准承诺；只是“传了 `par`，你就要忍受多线程”。

### 调用线程会阻塞并委托进展（¶9）

若并行算法使用了库隐式创建的线程，调用线程要么**带 forward progress 委托地阻塞**（[[g:forward-progress-delegation]]）等待这些线程完成，要么自己最终去执行元素访问函数，直到算法结束。注 10：在此语境下，库线程只要执行完调用线程逻辑上依赖的那个元素访问函数，就视为“已完成”。直观地说：并行算法是**同步**调用——返回时所有工作都做完了，不存在“后台还在跑”。

### 实现定义的策略（¶10）

用实现定义类型的执行策略对象调用并行算法，语义由实现定义。这为厂商扩展（如 GPU 策略）留了口子，见 [[execpol]] 中 `is_execution_policy` 的说明。

## 异常（[algorithms.parallel.exceptions]）

¶1：并行化所需的临时内存资源不可用时，算法抛出 `bad_alloc`。这是并行算法唯一“正常”向外抛出的异常源（当然，算法开始执行之前的实参复制等仍按常规）。

¶2：元素访问函数以未捕获异常退出时，行为**由执行策略决定**。对全部四种标准策略，[execpol.seq] 至 [execpol.unseq] 的 ¶2 都规定调用 `terminate`（[[except.terminate]]）。这与非并行算法截然不同——`std::for_each(first, last, f)` 中 `f` 抛出的异常会正常传播。

```cpp run title="parex.cpp" flags="-std=c++2c -fexperimental-library" ok
#include <algorithm>
#include <cstdio>
#include <execution>
#include <stdexcept>
#include <vector>

int main() {
    std::vector<int> v(1000, 1);
    try {
        std::for_each(std::execution::par, v.begin(), v.end(), [](int x) {
            if (x == 1) throw std::runtime_error("boom");
        });
    } catch (...) {
        std::puts("caught");   // 永远到不了：[execpol.par]/2 要求调用 terminate
    }
}
```

本机 Clang 23 + libc++ 运行输出 `libc++abi: terminating due to uncaught exception of type std::runtime_error: boom`，进程以 `SIGABRT` 结束——`catch (...)` 没有机会执行。注意即便是 `seq` 也一样：`std::for_each(std::execution::seq, ...)` 并不等价于不带策略的 `std::for_each`。

!!! history "为什么不聚合异常"
    Parallelism TS 曾设计 `exception_list` 来收集多个线程抛出的异常；并入 C++17 时这一机制被去掉，改为一律 `terminate`。理由是多线程下可能有多个异常、聚合后难以使用，且可以在将来以新的策略类型提供其他行为——[algorithms.parallel.exceptions] ¶2 把行为交给“执行策略决定”就是为此留下的扩展点。

## 并行重载的一般规则（[algorithms.parallel.overloads]）

¶1：每个并行重载都多一个类型为 `T&&` 的**第一个**函数形参 `P`，`T` 是执行策略模板形参。注 1：并非所有算法都有并行重载——例如 `accumulate`、`partial_sum`、`iota`、`push_heap`、`lower_bound`、`next_permutation` 都没有（`accumulate`/`partial_sum` 的严格从左到右语义本身就排斥并行，并行版是 `reduce`/`inclusive_scan`，见 [[numeric.ops]]）。

¶2：除非另有规定，调用并行重载的语义等同于去掉 `P` 调用对应的非并行重载。“另有规定”的地方不少，读条文时要留意：

- `for_each` 的并行版返回 `void`（经典并行版）/迭代器（ranges 并行版），不返回函数对象；
- `adjacent_difference` 的并行版不允许 `result == first`（[[numeric.ops]]）；
- `shift_left` 的并行版不保证移动顺序；
- 复杂度（下一段）。

¶3：**复杂度放宽**。当非并行版的保证写作“至多 *expr*”或“恰好 *expr*”，且不涉及赋值/交换次数、*expr* 也不是 O() 形式时，并行版的复杂度为 O(*expr*)。所以 `std::find(par, ...)` 可以做比非并行版多常数倍的比较（例如各线程都在自己的块里找）；`std::count(par, ...)` 不再承诺“恰好 N 次”。有些算法在并行版中复杂度另有规定，例如 `nth_element` 并行版为 O(N) 次谓词调用与 O(N log N) 次交换，`partition` 并行版为 O(N log N) 次交换，`transform` 则特意写明“恰好 N 次”**同样适用于**并行重载（[[alg.transform#5]]）。

¶4：带名为 `ExecutionPolicy` 的模板形参的并行算法，仅当该形参满足 *execution-policy* 时才参与重载决议。没有这一条，`std::sort(first, last, comp)` 和 `std::sort(policy, first, last)` 都是三个实参，后者的模板就会去“匹配”前者的调用。

### 迭代器类别要求更高

经典并行重载的迭代器形参是 `ForwardIterator`（而非 `InputIterator`），C++26 的并行 ranges 重载更要求 `random_access_iterator` + `sized_sentinel_for`，或 *sized-random-access-range*（[[range.req]]）。前者是因为切分工作需要多趟遍历，后者是因为 ranges 并行版在设计上直接面向可 O(1) 切分的数据。

## 实现视角：libc++ 的现状

!!! impl "libc++（LLVM 23）"
    - 并行算法属于**实验性库功能**，需要 `-fexperimental-library` 才可用；否则 `std::execution::par` 根本不存在。`__cpp_lib_parallel_algorithm` 在 `<version>` 中仍被注释掉，未定义。
    - 后端在配置时选定，Homebrew 版 macOS 构建使用 libdispatch 后端（`__config_site` 中 `_LIBCPP_PSTL_BACKEND_LIBDISPATCH`）。
    - 只实现了部分算法的并行重载：`all_of`/`any_of`/`none_of`、`copy`/`copy_n`/`move`、`count`/`count_if`、`equal`、`fill`/`fill_n`、`find`/`find_if`/`find_if_not`、`for_each`/`for_each_n`、`generate`/`generate_n`、`is_partitioned`、`merge`、`replace` 系列与 `replace_copy` 系列、`rotate_copy`、`sort`/`stable_sort`、`transform`、`reduce`、`transform_reduce`。其余（如 `inclusive_scan`、`partition`、`unique`、`nth_element`、`min_element`、`remove`）调用时找不到匹配重载。
    - C++26 的并行 ranges 重载（`std::ranges::sort(std::execution::par, v)`）尚未实现。
    - libc++ 的策略类型**不可复制**：`auto p = std::execution::par;` 报 “call to deleted constructor of 'parallel_policy'”。标准只说类定义为 `{ unspecified }`，没有承诺可复制，所以要用 `const auto& p = std::execution::par;` 或直接传对象本身。

## 思考题

<details markdown="1">
<summary>1. `std::sort(std::execution::par, v.begin(), v.end(), comp)` 中 `comp` 内部用 `std::mutex` 记录调用次数，合法吗？换成 `par_unseq` 呢？</summary>

`par` 下合法：元素访问函数在不同线程上执行，同一线程内的调用不确定顺序但不交错，加锁不会自锁（[algorithms.parallel.exec] ¶6 例 3）。但 [algorithms.parallel.user] ¶1 要求 `Compare` 不得经实参修改对象——记录次数修改的是外部计数器而非实参，不违反。`par_unseq` 下 `mutex::lock` 是向量化不安全函数，调用它是 {{ub}}（¶7）；可以改用无锁原子 `fetch_add`，它不属于向量化不安全。
</details>

<details markdown="1">
<summary>2. 一个迭代器类型的 `operator++` 可能抛 `std::bad_alloc`（例如惰性加载数据块）。把它用于 `std::count(std::execution::par, ...)`，抛出时会发生什么？</summary>

迭代器操作是元素访问函数（¶3.1）；元素访问函数以异常退出 → 由策略决定 → `terminate`（[execpol.par] ¶2）。[algorithms.parallel.exceptions] ¶1 的 `bad_alloc` 指的是**算法自身**为并行化申请临时内存失败，与元素访问函数抛出的 `bad_alloc` 无关。
</details>

<details markdown="1">
<summary>3. `std::reduce(std::execution::seq, v.begin(), v.end(), 0.0)` 的结果一定等于 `std::accumulate(v.begin(), v.end(), 0.0)` 吗？</summary>

不一定。`seq` 只规定元素访问函数都在调用线程中不交错地执行；`reduce` 的**数学**定义是 *GENERALIZED_SUM*（[[numerics.defns]]），允许任意分组与重排，这与策略无关。浮点加法不结合，因此结果可以不同。
</details>

## 小结

- 规则的单位是**元素访问函数**：迭代器操作、元素操作、用户可调用对象及其操作。
- 用户函数对象在并行算法中不得经实参修改任何对象、不得依赖对象身份；实现可复制可平凡复制的元素（`for_each` 除外）。
- `seq`：调用线程、不交错；`par`：多线程、不确定顺序；`unseq`/`par_unseq`：可交错，调用向量化不安全函数是 UB。
- 策略是许可不是命令，实现可以回退为顺序执行；并行算法是同步调用。
- 临时内存不足 → `bad_alloc`；元素访问函数抛异常 → `terminate`（四种标准策略皆然）。
- 并行重载的“恰好/至多 N”放宽为 O(N)；要求至少前向迭代器（ranges 版要求随机访问 + sized）。
