---
title: 广义数值运算
summary: <numeric> 的序列算法——GENERALIZED_SUM / GENERALIZED_NONCOMMUTATIVE_SUM 的精确定义；accumulate（严格左折叠、累加器类型即 init 类型）与 reduce（任意分组任意顺序、非结合/非交换运算结果不确定）的本质区别；inner_product 与 transform_reduce；partial_sum、inclusive_scan、exclusive_scan 及其 transform 版本；adjacent_difference 的并行版差异；iota 与 ranges::iota
status: done
covers: numeric.ops.overview, numeric.ops.general, numerics.defns, accumulate, reduce, inner.product, transform.reduce, partial.sum, exclusive.scan, inclusive.scan, transform.exclusive.scan, transform.inclusive.scan, adjacent.difference, numeric.iota
papers: P0024R2, P0616R0, P1645R1
related: numeric.sat, algorithms.parallel, alg.nonmodifying, algorithms.requirements
tags: 标准库, 算法, numeric, reduce, accumulate, scan, 浮点
updated: 2026-10-18
---

`<numeric>` 里的算法是“数值风味”的序列算法：求和、内积、前缀和、差分、递增填充。它们分两代：

- **C++98 一代**：`accumulate`、`inner_product`、`partial_sum`、`adjacent_difference`、`iota`（C++11）——严格的**从左到右**语义，没有并行版本；
- **C++17 一代**（随并行算法引入，[[P0024R2]]）：`reduce`、`transform_reduce`、`inclusive_scan`、`exclusive_scan` 及 transform 版——数学上用 *GENERALIZED_SUM* 定义，**允许任意分组和重排**，因而可以并行。

两代算法的区别不是“快慢”，而是**语义不同**：对浮点数或不满足结合律/交换律的运算，它们会给出不同的结果。

¶1（[numeric.ops.general] 注 1）：本节的要求中同时使用闭区间与半开区间是**有意**的——如 `accumulate` 要求 `binary_op` 不得使闭区间 `[first, last]` 中的迭代器失效，即连 `last` 也不能失效。

## 两个“广义和”（[numerics.defns]）

¶1：*GENERALIZED_NONCOMMUTATIVE_SUM*(op, a1, …, aN)：

- N 为 1 时是 a1；
- 否则是 `op(GNSUM(op, a1, …, aK), GNSUM(op, aM, …, aN))`，对**任意** 1 < K + 1 = M ≤ N。

也就是说：**保持元素顺序，但括号可以任意加**。`((a1 op a2) op a3)` 和 `(a1 op (a2 op a3))` 都是合法结果——这只对**结合**的 `op` 是唯一值。

¶2：*GENERALIZED_SUM*(op, a1, …, aN) 是对 a1…aN 的**任意排列** b1…bN 的 *GENERALIZED_NONCOMMUTATIVE_SUM*——顺序也可以打乱，只对**结合且交换**的 `op` 是唯一值。

这两个定义是并行化的数学许可证：把区间切成块，各块独立求和，再合并部分和——这需要可以重新加括号；向量化时把 a1、a5、a9… 放在同一个 SIMD 通道里——这需要可以重排。

## `accumulate`：严格的左折叠（[accumulate]）

¶2：用 `init` 初始化累加器 `acc`，然后对 `[first, last)` 中的每个 `i` **按顺序**执行 `acc = std::move(acc) + *i`（或 `binary_op(std::move(acc), *i)`）。

两个后果：

1. **累加器的类型就是 `T`（`init` 的类型）**。`std::accumulate(v.begin(), v.end(), 0)` 对 `vector<double>` 会逐步截断成 `int`——最经典的数值 bug 之一。C++23 的 `ranges::fold_left` 改为由运算结果决定类型，见 [[alg.nonmodifying]]。
2. 由于是严格的从左到右，**任何** `binary_op` 都有确定结果，包括 `minus`、字符串拼接、浮点加法。

`std::move(acc)` 是 C++20 加入的（[[P0616R0]]）：在 C++17 之前写的是 `acc = acc + *i`，用 `accumulate` 拼接 `std::string` 是 O(N²) 的；加上 `move` 后，`operator+(string&&, const string&)` 可以复用左操作数的缓冲区。

¶1 *Preconditions*：`T` 满足 *Cpp17CopyConstructible* 与 *Cpp17CopyAssignable*；`binary_op` 不修改元素、不使闭区间 `[first, last]` 中的迭代器或子区间失效。脚注 185：`accumulate` 总是要求初值，从而回避了“空序列的归约结果是什么”这个问题。

## `reduce`：可重排的归约（[reduce]）

¶7 *Returns*：*GENERALIZED_SUM*(binary_op, init, *i, …)。注意 `init` 也参与重排——它可能出现在任何位置。

¶1–¶4 是便利重载：无 `init` 时 `init` 为值类型的**值初始化**（`typename iterator_traits<I>::value_type{}`）——这是与 `accumulate` 的又一个区别，`reduce(v.begin(), v.end())` 对 `vector<double>` 得到 `double`；无 `binary_op` 时为 `plus<>()`。

¶5 *Mandates*：`binary_op(init, *first)`、`binary_op(*first, init)`、`binary_op(init, init)`、`binary_op(*first, *first)` **四种组合**都可转换为 `T`。这正是“可以任意重排”的语法后果：`reduce` 内部可能把两个元素相加，也可能把两个部分和相加。而对 `accumulate` 只需要 `binary_op(T, 元素)` 一种。

¶9 注 1 点明要害：

!!! std
    The difference between `reduce` and `accumulate` is that `reduce` applies `binary_op` in an unspecified order, which yields a nondeterministic result for non-associative or non-commutative `binary_op` such as floating-point addition.

对 `minus` 这样的运算，`reduce` 的结果是 {{unspec}}——并非 UB，但不保证等于 `accumulate` 的结果，也不保证每次运行相同。浮点加法虽然交换但**不结合**，同样受影响：

```cpp run title="reduce_fp.cpp" flags="-std=c++2c -O2 -fexperimental-library" impl
#include <cstdio>
#include <execution>
#include <numeric>
#include <vector>

int main() {
    std::vector<float> v(10'000'000, 0.1f);
    float a = std::accumulate(v.begin(), v.end(), 0.0f);
    float r = std::reduce(std::execution::par_unseq, v.begin(), v.end(), 0.0f);
    std::printf("accumulate=%.1f reduce=%.1f\n", a, r);
}
```

本机输出 `accumulate=1087937.0 reduce=1000374.1`（数学上的精确值是 1000000）。逐个从左往右加时，累加器很快变得远大于 0.1f，每次加法的舍入误差都朝同一方向累积；分块求和再合并的 `reduce` 反而误差小得多。两者都“正确”，只是标准对 `reduce` 不承诺具体值。

¶8：O(N) 次 `binary_op` 应用（不是“恰好 N 次”——分块合并会多做若干次）。

!!! tip "什么时候该用哪一个"
    - 运算结合且交换（整数加法、`max`、按位或）：`reduce` 与 `accumulate` 结果相同，`reduce` 可并行；
    - 浮点求和：两者都不精确，`reduce` 通常误差更小但不可复现；需要可复现就用 `accumulate`（或 Kahan 求和）；
    - 非交换运算（字符串拼接、矩阵乘法）：只能用 `accumulate`/`fold_left`，或者保证结合性后用 `inclusive_scan` 的思路自行分块。

## `inner_product` 与 `transform_reduce`（[inner.product]、[transform.reduce]）

`inner_product(first1, last1, first2, init)`：严格从左到右计算 `acc = std::move(acc) + (*i1) * (*i2)`（或 `binary_op1(std::move(acc), binary_op2(*i1, *i2))`）。

`transform_reduce` 是它的可重排版本，有两种形式：

- 二元：¶5 返回 *GENERALIZED_SUM*(binary_op1, init, binary_op2(*i, *(first2 + (i − first1))), …)；默认 `plus<>()` 与 `multiplies<>()`，即内积；
- 一元：¶9 返回 *GENERALIZED_SUM*(binary_op, init, unary_op(*i), …)，即 map-reduce；¶11 注 1：**不对 `init` 应用 `unary_op`**。

¶3、¶7 的 *Mandates* 与 `reduce` 同理要求四种组合可转换为 `T`。

## 前缀和：`partial_sum` 与 scan 系列

| 算法 | 第 K 个输出 | 顺序 | 并行版 |
|---|---|---|---|
| `partial_sum` | x0 + … + xK（累加器为输入值类型） | 严格从左到右 | 无 |
| `inclusive_scan` | [init +] x0 + … + xK | *GENERALIZED_NONCOMMUTATIVE_SUM* | 有 |
| `exclusive_scan` | init + x0 + … + x(K−1) | 同上 | 有 |
| `transform_inclusive_scan` / `transform_exclusive_scan` | 对 `unary_op(xi)` 求上述和 | 同上 | 有 |

要点：

- scan 用的是 ***NONCOMMUTATIVE*** 广义和——**保持顺序**、只允许重新加括号。所以 scan 只要求 `binary_op` **结合**，不要求交换；矩阵乘法、字符串拼接这类结合但不交换的运算可以用 scan 并行化，却不能用 `reduce`。各节注 1 都写着“若 `binary_op` 在数学上不结合，scan 的行为可能是不确定的”。
- `exclusive_scan` **必须**给 `init`（第 0 个输出就是 `init`）；`inclusive_scan` 的 `init` 是可选的，而且参数顺序是 `(first, last, result, binary_op, init)`——`init` 在 `binary_op` **之后**，与 `exclusive_scan(first, last, result, init, binary_op)` 相反。这是有意为之：`inclusive_scan(f, l, r, init)` 若允许，会与 `inclusive_scan(f, l, r, binary_op)` 产生歧义。
- `partial_sum` 的累加器类型是**输入迭代器的值类型**（¶3），不是输出类型，也没有 `init`——对 `vector<char>` 求前缀和会在 `char` 里溢出。
- 所有这些都允许 `result == first`（原地，各节 *Remarks*）。
- transform 版本**不对 `init` 应用 `unary_op`**（各节注 1）。

```cpp run title="scan.cpp" ok
#include <cassert>
#include <numeric>
#include <vector>

int main() {
    std::vector<int> v{1, 2, 3, 4};
    std::vector<int> ex(4), in(4);
    std::exclusive_scan(v.begin(), v.end(), ex.begin(), 0);
    std::inclusive_scan(v.begin(), v.end(), in.begin());
    assert((ex == std::vector{0, 1, 3, 6}));     // 第 i 个和“不含”第 i 个元素
    assert((in == std::vector{1, 3, 6, 10}));    // 第 i 个和“包含”第 i 个元素

    int dot = std::transform_reduce(v.begin(), v.end(), v.begin(), 0);  // 默认 plus / multiplies
    assert(dot == 30);
}
```

## `adjacent_difference`（[adjacent.difference]）

输出 `*result = *first`，此后每个位置输出 `binary_op(*i, *(i − 1))`（默认 `minus<>`，注意是“当前减前一个”）。

¶4–¶5 揭示了非并行版与并行版的**实现模型差异**：

- 非并行版：维护累加器 `acc`（保存前一个输入值），每步创建 `val = *i`，输出 `binary_op(val, std::move(acc))`，再 `acc = std::move(val)`。正因为先把前一个值保存在 `acc` 里，¶8 允许 `result == first`（原地）。
- 并行版：直接计算 `*(result + d) = binary_op(*(first + d), *(first + (d − 1)))`，各位置独立——所以 ¶8 规定输入输出**不得重叠**（原地写会破坏其他线程要读的值）。

这是 [[algorithms.parallel.overloads#2]]“除非另有规定，并行版语义同非并行版”的一个“另有规定”的例子。

## `iota` 与 `ranges::iota`（[numeric.iota]）

`iota(first, last, value)`：依次赋值 `value, ++value, ++value…`。¶1 *Mandates*：`T` 可转换为值类型、`++val` 良构——只需要 `++`，所以可以用于迭代器类型（`iota(its.begin(), its.end(), v.begin())` 生成一组迭代器）。

`ranges::iota`（C++23）¶4：返回 `out_value_result{last, value}`——**把递增后的 value 也还给你**，可以接着填下一段。注意它赋值时用的是 `as_const(value)`。

`iota` 自 C++20 起是 `constexpr`（[[P1645R1]] 让 `<numeric>` 中的算法整体 `constexpr`）；并行算法版本则都不是 `constexpr`。

## 思考题

<details markdown="1">
<summary>1. `std::reduce(v.begin(), v.end(), std::string{}, std::plus<>())` 对 `vector<std::string>` 合法吗？结果确定吗？</summary>

合法：*Mandates* 的四种组合都可转换为 `std::string`。但字符串拼接**不交换**，*GENERALIZED_SUM* 允许任意排列，所以结果是 {{unspec}}——可能是任意顺序的拼接。需要按顺序拼接用 `accumulate` 或 `ranges::fold_left`；需要并行且有序，可以把它表述为 scan 的最后一个元素（scan 只要求结合）。
</details>

<details markdown="1">
<summary>2. 为什么 `inclusive_scan` 不带 `init` 时对 *Cpp17MoveConstructible* 的要求落在输入值类型 `U` 上，带 `init` 时落在 `T` 上？</summary>

因为部分和的类型不同：不带 `init` 时部分和从 `*first` 开始，是 `U`；带 `init` 时从 `init` 开始，是 `T`（[inclusive.scan] ¶3–¶5）。实现需要在内部移动这些部分和（例如把各块的前缀合并），所以对承载部分和的那个类型提出可移动要求。
</details>

## 小结

| 算法 | 数学定义 | 对 op 的要求（结果确定） | 并行版 |
|---|---|---|---|
| `accumulate` / `inner_product` / `partial_sum` | 严格左折叠 | 无 | 无 |
| `reduce` / `transform_reduce` | *GENERALIZED_SUM* | 结合 + 交换 | 有 |
| `inclusive_scan` / `exclusive_scan`（及 transform 版） | *GENERALIZED_NONCOMMUTATIVE_SUM* | 结合 | 有 |
| `adjacent_difference` | 逐对 `op(cur, prev)` | 无 | 有（不得原地） |
| `iota` | `++value` | — | 无 |

- `accumulate` 的累加器类型是 `init` 的类型；`reduce` 无 `init` 时用值类型的值初始化。
- 浮点求和用 `reduce` 结果不可复现，标准只说是“不确定的”。
- `inclusive_scan` 与 `exclusive_scan` 的 `init` 参数位置相反。
