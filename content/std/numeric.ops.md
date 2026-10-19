---
title: 广义数值运算
summary: <numeric> 的序列算法：accumulate 严格从左到右折叠、累加器类型就是初值的类型；reduce 与 scan 系列按 GENERALIZED_SUM 定义，允许重新分组和重排，因而可以并行，但对浮点和非交换运算结果不确定；inner_product、transform_reduce、partial_sum、adjacent_difference 与 iota。
status: done
covers: numeric.ops.overview, numeric.ops.general, numerics.defns, accumulate, reduce, inner.product, transform.reduce, partial.sum, exclusive.scan, inclusive.scan, transform.exclusive.scan, transform.inclusive.scan, adjacent.difference, numeric.iota
papers: P0024R2, P0616R0, P1645R1
related: numeric.sat, algorithms.parallel, alg.nonmodifying, algorithms.requirements
tags: 标准库, 算法, numeric, reduce, accumulate, scan, 浮点
updated: 2026-10-19
---

!!! tldr
    - `accumulate` 严格从左到右计算，累加器的类型就是初值的类型：对 `vector<double>` 写 `accumulate(..., 0)` 会把每一步截断成 `int`。
    - `reduce` 允许任意分组、任意顺序，所以可以并行；运算不结合或不交换时（包括浮点加法），结果不确定。
    - scan 系列只允许重新分组、不允许重排，因此只要求运算可结合，不要求可交换。
    - `exclusive_scan` 的 `init` 是必填的、在 `binary_op` 之前；`inclusive_scan` 的 `init` 是可选的、在 `binary_op` 之后。
    - `adjacent_difference` 的并行版本不允许原地计算，非并行版本允许。

## `accumulate` 与 `reduce` 算出了不同的结果

```cpp run title="reduce_fp.cpp" flags="-std=c++2c -O2 -fexperimental-library" impl
#include <cstdio>
#include <execution>
#include <numeric>
#include <vector>

int main() {
    std::vector<float> v(10'000'000, 0.1f);
    float a = std::accumulate(v.begin(), v.end(), 0.0f);
    float r = std::reduce(std::execution::par_unseq,
                          v.begin(), v.end(), 0.0f);
    std::printf("accumulate=%.1f reduce=%.1f\n", a, r);
}
```

本机输出 `accumulate=1087937.0 reduce=1000374.1`，数学上的精确值是 1000000。

`accumulate` 从左往右逐个相加，累加器很快就远大于 0.1f，每次加法的舍入误差都朝同一个方向积累。`reduce` 把区间分成块分别求和，再合并部分和，误差反而小得多。两个结果都符合标准：`accumulate` 规定了计算顺序，而标准对 `reduce` 的具体结果不作承诺。

`<numeric>` 的序列算法可以分成两组：

- C++98 就有的 `accumulate`、`inner_product`、`partial_sum`、`adjacent_difference`，以及 C++11 的 `iota`：严格从左到右计算，没有并行版本；
- C++17 随并行算法一起加入的 `reduce`、`transform_reduce`、`inclusive_scan`、`exclusive_scan` 及其 transform 版本（[[P0024R2]]）：用下面的广义和定义，允许重新分组和重排，所以能够并行。

两组算法的区别在语义上，不只是速度。

## 两个广义和（[numerics.defns]）

¶1 *GENERALIZED_NONCOMMUTATIVE_SUM*(op, a1, …, aN) 定义为：N 为 1 时是 a1；否则是

op(*GENERALIZED_NONCOMMUTATIVE_SUM*(op, a1, …, aK), *GENERALIZED_NONCOMMUTATIVE_SUM*(op, aM, …, aN))

其中 K 可以任取，只要满足 1 < K + 1 = M ≤ N。也就是说，元素的顺序保持不变，括号可以随意加。`(a1 op a2) op a3` 和 `a1 op (a2 op a3)` 都是合法的结果，只有 `op` 可结合时它们才相等。

¶2 *GENERALIZED_SUM*(op, a1, …, aN) 是对 a1, …, aN 的任意一个排列求 *GENERALIZED_NONCOMMUTATIVE_SUM*。顺序也可以打乱，只有 `op` 既可结合又可交换时结果才唯一。

这两个定义是并行化的依据。把区间切成块，各块独立求和再合并，需要能重新加括号；向量化时把 a1、a5、a9 等放进同一个 SIMD 通道，需要能重排。

## `accumulate`（[accumulate]）

¶2 `accumulate` 用 `init` 初始化累加器 `acc`，然后按顺序对每个 `i` 执行 `acc = std::move(acc) + *i`，或者 `acc = binary_op(std::move(acc), *i)`。

这有两个后果。第一，累加器的类型就是 `T`，即 `init` 的类型。`std::accumulate(v.begin(), v.end(), 0)` 对 `vector<double>` 会在每一步把和截断成 `int`，这是很常见的数值 bug。C++23 的 `ranges::fold_left` 改为由运算结果决定类型，见 [[alg.nonmodifying]]。

第二，计算顺序完全确定，所以任何 `binary_op` 都有确定的结果，包括减法、字符串拼接和浮点加法。

`std::move(acc)` 是 C++20 加入的（[[P0616R0]]）。此前写的是 `acc = acc + *i`，用 `accumulate` 拼接 `std::string` 每一步都要复制整个累加器，总代价是 O(N²)。加上 `move` 之后，`operator+(string&&, const string&)` 可以复用左操作数的缓冲区。

¶1 要求 `T` 可以复制构造和复制赋值，`binary_op` 不修改元素，也不使闭区间 `[first, last]` 中的迭代器失效。这里有意用了闭区间，连 `last` 也不能失效；[numeric.ops.general] 的注 1 说明本节混用闭区间和半开区间是有意的。脚注 185 说明，`accumulate` 总是要求初值，就避开了空序列的归约结果是什么这个问题。

## `reduce`（[reduce]）

¶7 `reduce` 返回 *GENERALIZED_SUM*(binary_op, init, *i, …)。`init` 也参与重排，可能出现在任何位置。

¶1–¶4 是几个简化的重载。不给 `init` 时，`init` 是元素类型的值初始化结果 `iterator_traits<I>::value_type{}`，所以 `reduce(v.begin(), v.end())` 对 `vector<double>` 得到 `double`，不会出现 `accumulate` 的截断问题。不给 `binary_op` 时使用 `plus<>()`。

¶5 *Mandates* 要求 `binary_op(init, *first)`、`binary_op(*first, init)`、`binary_op(init, init)`、`binary_op(*first, *first)` 四种组合都能转换为 `T`。这是允许任意重排在语法上的后果：`reduce` 内部可能把两个元素相加，也可能把两个部分和相加。`accumulate` 只需要 `binary_op(T, 元素)` 这一种。

!!! std
    The difference between `reduce` and `accumulate` is that `reduce` applies `binary_op` in an unspecified order, which yields a nondeterministic result for non-associative or non-commutative `binary_op` such as floating-point addition.

¶9 注 1 是本节的要点。对减法这样的运算，`reduce` 的结果不确定：不是未定义行为，但不保证等于 `accumulate` 的结果，也不保证每次运行都相同。浮点加法可交换但不可结合，同样不确定，开头的例子就是这样。

¶8 复杂度是 O(N) 次 `binary_op` 调用，没有要求恰好 N 次，因为分块合并部分和要多算几次。

!!! tip "用哪一个"
    - 运算可结合且可交换（整数加法、`max`、按位或）：`reduce` 与 `accumulate` 结果相同，`reduce` 可以并行；
    - 浮点求和：两者都有舍入误差，`reduce` 通常更准但结果不可复现，需要可复现时用 `accumulate`（或 Kahan 求和）；
    - 不可交换的运算（字符串拼接、矩阵乘法）：用 `accumulate` 或 `ranges::fold_left`；运算可结合时也可以用 scan 系列并行。

## `inner_product` 与 `transform_reduce`（[inner.product]、[transform.reduce]）

[inner.product] ¶2 `inner_product(first1, last1, first2, init)` 严格从左到右计算 `acc = std::move(acc) + (*i1) * (*i2)`，或 `acc = binary_op1(std::move(acc), binary_op2(*i1, *i2))`。

`transform_reduce` 是它可以重排的版本，有两种形式：

- 两个区间：[transform.reduce] ¶5 返回 *GENERALIZED_SUM*(binary_op1, init, binary_op2(*i, *(first2 + (i − first1))), …)。默认的两个运算是 `plus<>()` 和 `multiplies<>()`，即内积；
- 一个区间：¶9 返回 *GENERALIZED_SUM*(binary_op, init, unary_op(*i), …)，即先映射再归约。¶11 注 1 指出 `unary_op` 不作用于 `init`。

¶3、¶7 的 *Mandates* 与 `reduce` 同理，要求四种组合都能转换为 `T`。

## 前缀和：`partial_sum` 与 scan 系列

| 算法 | 第 K 个输出 | 计算方式 | 并行版本 |
|---|---|---|---|
| `partial_sum` | x0 + … + xK，累加器为输入的元素类型 | 严格从左到右 | 无 |
| `inclusive_scan` | [init +] x0 + … + xK | *GENERALIZED_NONCOMMUTATIVE_SUM* | 有 |
| `exclusive_scan` | init + x0 + … + x(K−1) | 同上 | 有 |
| `transform_inclusive_scan`、`transform_exclusive_scan` | 对 `unary_op(xi)` 求上述和 | 同上 | 有 |

scan 用的是保持顺序的广义和，只允许重新加括号。所以 scan 只要求 `binary_op` 可结合，不要求可交换。矩阵乘法、字符串拼接这类可结合但不可交换的运算，可以用 scan 并行，却不能用 `reduce`。[inclusive.scan] ¶10 和 [exclusive.scan] ¶9 的注都提醒，`binary_op` 在数学上不可结合时，结果可能不确定。

`exclusive_scan(first, last, result, init, binary_op)` 必须给 `init`，第 0 个输出就是 `init`。`inclusive_scan(first, last, result, binary_op, init)` 的 `init` 可选，而且位置在 `binary_op` 之后，与 `exclusive_scan` 相反。如果允许 `inclusive_scan(first, last, result, init)`，它就无法与 `inclusive_scan(first, last, result, binary_op)` 区分。

[partial.sum] ¶3 `partial_sum` 没有 `init`，累加器的类型是输入的元素类型，不是输出的元素类型。对 `vector<char>` 求前缀和会在 `char` 里溢出。

这几个算法都允许 `result == first`，即原地计算（各节的 *Remarks*）。transform 版本同样不对 `init` 调用 `unary_op`。

```cpp run title="scan.cpp" ok
#include <cassert>
#include <numeric>
#include <vector>

int main() {
    std::vector<int> v{1, 2, 3, 4};
    std::vector<int> ex(4), in(4);
    std::exclusive_scan(v.begin(), v.end(), ex.begin(), 0);
    std::inclusive_scan(v.begin(), v.end(), in.begin());
    assert((ex == std::vector{0, 1, 3, 6}));   // 第 i 个和不含第 i 个元素
    assert((in == std::vector{1, 3, 6, 10}));  // 第 i 个和包含第 i 个元素

    // 默认运算是 plus 与 multiplies，即内积
    int dot = std::transform_reduce(v.begin(), v.end(), v.begin(), 0);
    assert(dot == 30);
}
```

## `adjacent_difference`（[adjacent.difference]）

`adjacent_difference` 先输出 `*first`，之后每个位置输出 `binary_op(*i, *(i − 1))`。默认运算是 `minus<>`，注意是当前元素减前一个元素。

非并行版本和并行版本的规定不同：

- ¶4 非并行版本维护一个累加器 `acc`，保存前一个输入值。每一步创建 `val = *i`，输出 `binary_op(val, std::move(acc))`，再把 `val` 移动赋值给 `acc`。前一个值已经存在 `acc` 里，所以 ¶8 允许 `result == first`；
- ¶5 并行版本直接计算 `*(result + d) = binary_op(*(first + d), *(first + (d − 1)))`，每个位置独立计算。原地写入会改掉其他位置要读的值，所以 ¶8 规定输入和输出不得重叠。

并行算法的语义一般与对应的非并行版本相同（[[algorithms.parallel.overloads#2]]），这里是一个另有规定的例子。

## `iota` 与 `ranges::iota`（[numeric.iota]）

¶2 `iota(first, last, value)` 依次赋值 `value`、`++value`、`++value`……。¶1 *Mandates* 只要求 `T` 能转换为元素类型、`++val` 良构，所以 `T` 也可以是迭代器：`iota(its.begin(), its.end(), v.begin())` 生成一组指向 `v` 各元素的迭代器。

¶4 `ranges::iota`（C++23）返回 `{last, value}`，把递增后的 `value` 也交还给调用者，方便接着填下一段。它赋值时用的是 `as_const(value)`。

`iota` 自 C++20 起是 `constexpr`，[[P1645R1]] 把 `<numeric>` 中的这些算法都改成了 `constexpr`。并行版本都不是 `constexpr`。

## 思考题

!!! question "思考题 1"
    对 `vector<std::string>` 调用 `std::reduce(v.begin(), v.end(), std::string{}, std::plus<>())`，合法吗？结果确定吗？

<details markdown="1">
<summary>答案</summary>

合法，*Mandates* 要求的四种组合都能转换为 `std::string`。但字符串拼接不可交换，而 *GENERALIZED_SUM* 允许任意排列，所以结果不确定，可能按任何顺序拼接。需要按顺序拼接时用 `accumulate` 或 `ranges::fold_left`。拼接是可结合的，所以需要并行又要保持顺序时，可以取 `inclusive_scan` 的最后一个输出。
</details>

!!! question "思考题 2"
    为什么 `inclusive_scan` 不带 `init` 时要求输入的元素类型 `U` 可移动构造，带 `init` 时却要求 `T` 可移动构造？

<details markdown="1">
<summary>答案</summary>

因为部分和的类型不同。不带 `init` 时，部分和从 `*first` 开始，类型是 `U`；带 `init` 时从 `init` 开始，类型是 `T`（[inclusive.scan] ¶3–¶5）。实现需要在内部移动部分和，例如合并各块的前缀，所以对承载部分和的类型提出可移动构造的要求。
</details>

## 小结

| 算法 | 定义方式 | 结果确定需要运算满足 | 并行版本 |
|---|---|---|---|
| `accumulate`、`inner_product`、`partial_sum` | 严格从左到右 | 无要求 | 无 |
| `reduce`、`transform_reduce` | *GENERALIZED_SUM* | 可结合、可交换 | 有 |
| `inclusive_scan`、`exclusive_scan` 及 transform 版本 | *GENERALIZED_NONCOMMUTATIVE_SUM* | 可结合 | 有 |
| `adjacent_difference` | 逐对计算 `op(当前, 前一个)` | 无要求 | 有，不得原地 |
| `iota` | 反复 `++value` | 不适用 | 无 |
