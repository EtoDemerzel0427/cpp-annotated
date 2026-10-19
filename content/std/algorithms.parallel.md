---
title: 并行算法
summary: 传入执行策略之后，算法可以怎样执行你的代码：元素访问函数的概念，seq、unseq、par、par_unseq 下调用在哪个线程、按什么顺序进行，什么情况是数据竞争或未定义行为，元素访问函数抛出异常时为什么调用 terminate，以及并行重载的复杂度怎样放宽。
status: done
covers: algorithms.parallel.defns, algorithms.parallel.user, algorithms.parallel.exec, algorithms.parallel.exceptions, algorithms.parallel.overloads
papers: P0024R2, P1001R2, P3179R9
related: execpol, algorithms.requirements, intro.execution, intro.progress, intro.races, except.terminate, numeric.ops
tags: 标准库, 并行算法, 执行策略, 向量化, 数据竞争, forward progress
updated: 2026-10-19
---

!!! tldr
    - 并行算法的规则以元素访问函数为单位：迭代器的操作、对元素的操作、你传入的 lambda，以及对这个 lambda 的复制，都算。
    - `par` 允许在多个线程上调用它们，同一线程上的调用不会交错；`unseq` 和 `par_unseq` 还允许同一线程上的调用交错执行，此时在其中加锁是未定义行为。
    - 执行策略只是许可。实现可以退回到顺序执行，所以不能写依赖于另一个调用同时运行的代码。
    - 元素访问函数抛出异常时，四种标准策略都调用 `std::terminate`，异常不会传到调用方，即使用的是 `seq`。
    - 非并行版本"恰好 N 次""至多 N 次"的复杂度，在并行版本中一般放宽为 O(N)。

C++17 把 Parallelism TS 并入了标准（[[P0024R2]]）。大多数算法多了一个以**执行策略**（[[g:execution-policy]]）为第一个实参的重载：

```cpp
std::sort(std::execution::par, v.begin(), v.end());
```

本页讲的是：传入策略之后，算法可以怎样调用你的迭代器、元素和函数对象，你的代码又必须承受什么。策略类型和对象本身见 [[execpol]]。

¶1 [algorithms.parallel] 描述的是对容器和其他序列并行执行操作的组件。¶2 带有名为 `ExecutionPolicy` 的模板形参，或者受仅用于说明的概念 *execution-policy* 约束的函数模板，叫做**并行算法**（[[g:parallel-algorithm]]）。这样的模板形参叫**执行策略模板形参**（[[g:execution-policy-template-parameter]]）：

```cpp
template<class Ep>
  concept execution-policy = is_execution_policy_v<remove_cvref_t<Ep>>;   // 仅用于说明
```

经典的并行重载用 `class ExecutionPolicy`，C++26 新增的并行 `ranges` 重载（[[P3179R9]]）用 `execution-policy Ep`。

## 元素访问函数 [algorithms.parallel.defns]

¶3 并行算法通过调用下面几类函数，间接访问实参能触及的对象：

- ¶3.1 实例化算法所用的迭代器、哨位或 `mdspan` 类型所属类别的全部操作；
- ¶3.2 规范要求的、对序列元素的操作；
- ¶3.3 规范要求在执行中调用的、用户提供的可调用对象；
- ¶3.4 规范要求的、对这些可调用对象的操作，例如复制它们。

这些函数统称**元素访问函数**（[[g:element-access-function]]）。¶4 的例 1 以 `sort` 为例：随机访问迭代器的操作、对元素调用的 `swap`、用户提供的 `Compare`，都是元素访问函数。

后面关于在哪个线程执行、调用之间有没有顺序、抛出异常怎么办的规则，都以元素访问函数为单位。它不只包括你的 lambda：迭代器的 `operator++`、元素的移动赋值也在其中。一个在 `operator*` 里写日志、加锁的迭代器，同样受这些规则约束。

## 四种策略怎样执行 [algorithms.parallel.exec]

¶1 执行策略模板形参描述了并行算法可以怎样并行化，以及怎样调用元素访问函数。四种标准策略的规则如下：

| 策略 | 在哪些线程上调用 | 同一线程上的调用之间 | 段落 |
|---|---|---|---|
| `seq`（`sequenced_policy`） | 全部在调用线程 | 不交错 | ¶4 |
| `unseq`（`unsequenced_policy`） | 全部在调用线程 | 无序，可以交错 | ¶5 |
| `par`（`parallel_policy`） | 调用线程，或库为此创建的线程 | 顺序不确定，但不交错 | ¶6 |
| `par_unseq`（`parallel_unsequenced_policy`） | 未指定的线程 | 无序，可以交错 | ¶7 |

两个求值**顺序不确定**（[[g:indeterminately-sequenced]]），是说其中一个在另一个之前完成，但不确定哪个在前。两个求值**无序**（[[g:unsequenced]]），是说它们的执行可以重叠。普通代码里，函数调用之间至少是顺序不确定的，一个函数的执行不会与另一个交错（[[intro.execution]]）。

¶5 和 ¶7 的注 4、注 7 特意指出，`unseq` 和 `par_unseq` 推翻了这条通常的保证。这正是向量化需要的：编译器把四次循环迭代的指令合并成一组 SIMD 指令，四次调用的执行在同一个线程上交织在一起。

### `par`：数据竞争和死锁由调用者负责

¶6 注 6 说，`par` 下由调用者保证这些调用不引入数据竞争或死锁。三个标准例子说明了这一点：

```cpp
int a[] = {0, 1};
std::vector<int> v;
std::for_each(std::execution::par, std::begin(a), std::end(a), [&](int i) {
  v.push_back(i * 2 + 1);   // UB：两个线程可能同时修改 v，数据竞争
});
```

例 2 中，两次调用用一个 `atomic` 互相等待，自旋直到另一次调用改变它的值。这在 `par` 下不保证终止：实现完全可以在同一个线程上先后执行两次调用，第一次调用就会永远自旋。`par` 只是允许并行，不保证并行。

例 3 用 `std::mutex` 保护共享的计数器，在 `par` 下是正确的，只是可能很慢。

### `unseq` 与 `par_unseq`：不能加锁

```cpp
std::mutex m;
int x = 0;
int a[] = {1, 2};
std::for_each(std::execution::par_unseq, std::begin(a), std::end(a), [&](int) {
  std::lock_guard<std::mutex> guard(m);   // UB：lock_guard 的构造函数调用 m.lock()
  ++x;
});
```

两次调用可能交错在同一个线程上：第一次拿到锁，第二次在同一线程上再次调用 `m.lock()`，于是死锁。

[[algorithms.parallel.defns#5]] 定义了**向量化不安全**（[[g:vectorization-unsafe]]）的标准库函数：规定与另一个函数调用同步，或者另一个调用规定与它同步的函数，但内存分配和释放函数、无锁的原子读改写操作除外。`mutex::lock`、`mutex::unlock`、条件变量的等待都属于这一类。

按 [algorithms.parallel.exec] ¶5 和 ¶7，在 `unseq` 或 `par_unseq` 算法调用的用户代码中调用向量化不安全的函数，是{{ub}}。那里的注 2 同时要求实现保证，标准库函数内部的同步不妨碍只有弱并行进展保证的线程前进，所以在其中 `new` 和 `delete` 是可以的。

### 进展保证

¶6 规定，如果 `std::thread` 和 `std::jthread` 创建的线程提供并发进展保证，那么库为 `par` 隐式创建的线程提供**并行进展保证**（[[g:parallel-forward-progress]]）；否则由实现定义。¶7 `par_unseq` 下库创建的线程只提供**弱并行进展保证**（[[g:weakly-parallel-forward-progress]]）。这几个等级的含义见 [[intro.progress]]。

### 策略是许可，不是命令（¶8–¶9）

¶8 的注 9 说，`unseq`、`par`、`par_unseq` 的语义允许实现在无法并行化时退回到顺序执行，例如资源不足时。所以传了 `par` 不保证会用多个线程，只是意味着你的代码必须能承受多线程。

¶9 如果并行算法用了库创建的线程，调用线程要么带着**进展委托**（[[g:forward-progress-delegation]]）阻塞，等待这些线程完成，要么自己去执行元素访问函数，直到算法结束。直观地说，并行算法是同步调用：它返回时，所有工作都已经完成，没有任何调用还在后台运行。

## 对你的函数对象的要求

### 不能通过实参修改对象 [algorithms.parallel.user]

¶1 除非另有规定，传给并行算法的 `Predicate`、`BinaryPredicate`、`Compare`、`UnaryOperation`、`BinaryOperation`、`BinaryOperation1`、`BinaryOperation2`、`BinaryDivideOp` 类型的对象，以及受语义要求包含 `regular_invocable` 的概念约束的对象，都不得直接或间接地通过实参修改对象，也不得依赖所提供对象的身份。使用默认的谓词或运算时，对应的运算符也要满足同样的要求。

这比非并行版本更严格。非并行的 `std::transform` 只禁止 `op` 修改区间内的元素；并行版本的 `op` 不能通过实参修改任何对象。

另有规定的例子：并行的 `for_each` 和 `for_each_n` 中，`f` 可以通过实参修改对象（[[alg.foreach#19]]）；`generate` 的 `gen` 也可以（[[alg.generate#6]]）。

### 实现可以复制元素

[[algorithms.parallel.exec#3]] 给了实现一项自由：

!!! std
    Unless otherwise stated, implementations may make arbitrary copies of elements (with type `T`) from sequences where `is_trivially_copy_constructible_v<T>` and `is_trivially_destructible_v<T>` are true.

例如向量化的实现会把一批 `int` 装进 SIMD 寄存器，分块的实现会把元素复制到线程自己的缓冲区。注 2 指出，这意味着对这样的序列，函数对象不能依赖实参的对象身份，`&x == &v[i]` 这样的判断不再可靠。`for_each` 和 `for_each_n` 例外，它们的 *Remarks* 规定实现没有这个自由，因为 `for_each` 常常就是用来原地修改元素的。

[[algorithms.parallel.exec#2]] 是反方向的承诺：一个对象被某个元素访问函数修改时，算法不会对它进行其他未同步的访问。注 1 列出了修改性的操作：`swap`、`++`、`--`、`@=`、赋值（赋值和复合赋值只算左操作数）。所以 `std::sort(par, ...)` 内部不会让两个线程同时交换同一个元素。

## 异常 [algorithms.parallel.exceptions]

```cpp run title="parex.cpp" flags="-std=c++2c -fexperimental-library" ok
#include <algorithm>
#include <cstdio>
#include <execution>
#include <stdexcept>
#include <vector>

int main() {
  std::vector<int> v(1000, 1);
  try {
    std::for_each(std::execution::seq, v.begin(), v.end(), [](int x) {
      if (x == 1) throw std::runtime_error("boom");
    });
  } catch (...) {
    std::puts("caught");   // 到不了这里
  }
}
```

本机 Clang 23 + libc++ 运行时输出 `libc++abi: terminating due to uncaught exception of type std::runtime_error: boom`，进程以 SIGABRT 结束，`catch (...)` 没有机会执行。程序是良构的，只是它的行为就是终止。

¶2 元素访问函数以未捕获的异常退出时，行为由执行策略决定。四种标准策略在各自的 ¶2 都规定调用 `std::terminate`（[[execpol]]、[[except.terminate]]）。所以 `std::for_each(std::execution::seq, ...)` 并不等价于不带策略的 `std::for_each`：后者中 `f` 抛出的异常会正常传给调用方。

¶1 并行化需要的临时内存申请不到时，算法抛出 `std::bad_alloc`。这是并行算法唯一会向外抛出的异常。它指的是算法自己申请内存失败，与元素访问函数抛出的 `bad_alloc` 无关，后者同样导致 `terminate`。

!!! note "为什么不把异常收集起来"
    Parallelism TS 曾设计了 `exception_list`，用来收集多个线程抛出的多个异常。并入 C++17 时这个机制被去掉，改为一律调用 `terminate`。¶2 把行为交给执行策略决定，为将来用新的策略类型提供其他行为留了余地。

## 并行重载的一般规则 [algorithms.parallel.overloads]

¶1 每个并行重载都比对应的非并行重载多一个类型为 `T&&` 的第一个函数形参，`T` 是执行策略模板形参。注 1 提醒，并不是所有算法都有并行重载。`accumulate`、`partial_sum`、`iota`、`push_heap`、`lower_bound`、`next_permutation` 都没有。`accumulate` 和 `partial_sum` 规定了严格从左到右的计算顺序，本身就排斥并行，它们的并行替代是 `reduce` 和 `inclusive_scan`（[[numeric.ops]]）。

¶2 除非另有规定，调用并行重载的语义与去掉第一个实参、调用对应的非并行重载相同。另有规定的地方不少：

- 并行的 `for_each` 不返回函数对象：经典版返回 `void`，`ranges` 版只返回迭代器；
- 并行的 `adjacent_difference` 不允许输出区间与输入区间重叠，非并行版允许 `result == first`（[[numeric.ops]]）；
- 并行的 `shift_left` 不规定移动元素的顺序。

¶3 复杂度放宽：非并行版本的保证写作"至多 *expr*"或"恰好 *expr*"，没有规定赋值或交换的次数，而且 *expr* 不是 O() 形式时，并行版本的复杂度为 O(*expr*)。所以 `std::find(par, ...)` 可以比非并行版多做常数倍的比较，比如每个线程都在自己负责的块里找；`std::count(par, ...)` 不再承诺恰好 N 次。

有些算法单独规定了并行版本的复杂度：`nth_element` 为 O(N) 次谓词调用和 O(N log N) 次交换，`partition` 为 O(N log N) 次交换。`transform` 则写明恰好 N 次的要求同样适用于并行重载（[[alg.transform#5]]）。

¶4 带名为 `ExecutionPolicy` 的模板形参的并行算法，只有在这个形参满足 *execution-policy* 时才参与重载决议。没有这一条，`std::sort(first, last, comp)` 这个三实参的调用也会去匹配 `std::sort(policy, first, last)` 的模板。

经典并行重载的迭代器形参至少是 `ForwardIterator`，而不是 `InputIterator`，因为切分工作需要多趟遍历。C++26 的并行 `ranges` 重载要求 `random_access_iterator` 加 `sized_sentinel_for`，或者 *sized-random-access-range*（[[range.req]]），也就是能在常数时间内切成若干段。

## 实现现状

!!! impl "libc++（LLVM 23）"
    - 并行算法是实验性功能，需要 `-fexperimental-library`；不加这个选项，`std::execution::par` 根本不存在。`<version>` 中的 `__cpp_lib_parallel_algorithm` 没有定义。
    - 后端在构建 libc++ 时选定。本机 Homebrew 版的 `__config_site` 定义了 `_LIBCPP_PSTL_BACKEND_LIBDISPATCH`，即在 macOS 上用 GCD 调度。
    - 只实现了一部分算法的并行重载，如 `all_of`、`copy`、`count`、`equal`、`fill`、`find`、`for_each`、`generate`、`merge`、`replace`、`sort`、`stable_sort`、`transform`、`reduce`、`transform_reduce`。本机实测，`inclusive_scan`、`min_element`、`remove` 带 `par` 调用时找不到匹配的重载。
    - C++26 的并行 `ranges` 重载尚未实现，`std::ranges::sort(std::execution::par, v)` 报错。
    - 策略类型不可复制：`auto p = std::execution::par;` 报 call to deleted constructor of 'parallel_policy'。标准只说这些类的定义是 `{ unspecified }`，没有承诺可以复制，所以这不违反标准。要保存策略，用 `const auto& p = std::execution::par;`。

## 思考题

!!! question "思考题 1"
    在 `std::sort(std::execution::par, v.begin(), v.end(), comp)` 中，`comp` 用 `std::mutex` 保护一个外部计数器，统计自己被调用的次数。这合法吗？换成 `par_unseq` 呢？

<details markdown="1">
<summary>答案</summary>

`par` 下合法。同一线程上的调用不会交错，加锁不会自己等自己，这正是 [algorithms.parallel.exec] ¶6 例 3 的做法。计数器是外部对象，不是通过实参修改的，不违反 [algorithms.parallel.user] ¶1。

`par_unseq` 下 `mutex::lock` 是向量化不安全的函数，调用它是未定义行为（¶7）。可以改用无锁的 `std::atomic<int>::fetch_add`，无锁的原子读改写操作不属于向量化不安全。
</details>

!!! question "思考题 2"
    某个迭代器的 `operator++` 会按需加载数据块，可能抛出 `std::bad_alloc`。把它用于 `std::count(std::execution::par, ...)`，抛出时会发生什么？

<details markdown="1">
<summary>答案</summary>

迭代器的操作是元素访问函数（¶3.1），元素访问函数以异常退出，行为由策略决定，`par` 规定调用 `terminate`（[[execpol]]）。[algorithms.parallel.exceptions] ¶1 说的 `bad_alloc` 是算法自己为并行化申请内存失败，与这里无关。
</details>

!!! question "思考题 3"
    `std::reduce(std::execution::seq, v.begin(), v.end(), 0.0)` 的结果一定等于 `std::accumulate(v.begin(), v.end(), 0.0)` 吗？

<details markdown="1">
<summary>答案</summary>

不一定。`seq` 只规定元素访问函数都在调用线程上、不交错地执行。`reduce` 的结果按 *GENERALIZED_SUM* 定义（[[numerics.defns]]），允许任意分组和重排，这与策略无关。浮点加法不满足结合律，所以结果可能不同。
</details>

<details class="fine" markdown="1"><summary>其余条文</summary>

[algorithms.parallel.exec] ¶10：以实现定义类型的执行策略对象调用并行算法，语义由实现定义。这为厂商提供 GPU 策略之类的扩展留了口子，见 [[execpol]]。

</details>

## 小结

| 问题 | 结论 |
|---|---|
| 规则的单位 | 元素访问函数：迭代器操作、元素操作、用户可调用对象及对它的操作 |
| `seq` | 调用线程，不交错 |
| `par` | 多个线程，同一线程上不交错；数据竞争和死锁由调用者避免 |
| `unseq`、`par_unseq` | 同一线程上可以交错；调用向量化不安全的函数是 UB |
| 用户函数对象 | 不得通过实参修改对象，不得依赖对象身份 |
| 异常 | 临时内存不足抛 `bad_alloc`；元素访问函数抛出异常则 `terminate` |
| 复杂度 | "恰好 N""至多 N"一般放宽为 O(N) |
