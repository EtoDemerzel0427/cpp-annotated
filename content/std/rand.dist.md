---
title: 随机数分布
summary: 20 个分布类模板的统一合同与逐个要点——算法由实现定义因而跨实现不可复现；uniform_int_distribution 的闭区间与精确等概率、uniform_real_distribution 的半开区间与 b−a 的前置条件；各分布的参数、定义域、默认值和前置条件一览；离散/分段常数/分段线性分布的权重规则；常见误用
status: done
covers: *
related: rand, rand.req, rand.util, rand.eng, alg.random.shuffle, alg.random.sample
tags: 标准库, 随机数, 分布, uniform_int_distribution, 可复现性
updated: 2026-10-18
---

[rand.dist] 定义了 20 个分布，按数学族分为五组：均匀、伯努利族、泊松族、正态族、抽样分布。每个分布的规范结构都一样：一个概率函数公式、一个类概要（构造函数、`param_type`、`operator()`、参数访问器、`min`/`max`、流运算符）、构造函数的前置条件、访问器的返回值。共同的接口和语义在 [[rand.req]]（[[g:random-number-distribution]]）里，这里不重复。

本页先讲适用于全部分布的规则，然后重点讲两个均匀分布，再用一张表概括其余各分布，最后讲三个抽样分布。

## 共同规则（[rand.dist.general]）

- ¶1：实例化得到的类型满足分布要求。
- ¶2：概要中不列出复制、流、相等运算符。
- ¶3：**产生每个分布的算法由实现定义**。
- ¶4：概率函数在其所述定义域之外处处为 0。

¶3 是整个 `<random>` 最重要的可移植性限制：标准只规定**结果服从什么分布**，不规定**怎么从引擎输出变换过去**。正态分布可以用 Box–Muller、Marsaglia 极坐标法、Ziggurat；均匀整数可以用不同的拒绝采样策略。每种做法消耗引擎输出的数量和方式不同，于是同一个引擎、同一个种子，在不同标准库上得到不同的序列。

```cpp run title="dist-not-portable.cpp" impl
#include <cstdio>
#include <random>

int main() {
  std::mt19937 g(42);                          // 引擎：处处相同
  std::uniform_int_distribution<int> die(1, 6);
  for (int i = 0; i < 8; ++i) std::printf("%d ", die(g));
  // 本机 libc++ 输出：4 5 3 5 5 2 3 3
  // 换一个标准库实现，结果可以不同——这不是 bug
}
```

前面的引擎输出是可移植的：`mt19937(42)` 的前两个输出处处都是 1608637542、3421126067。需要跨平台复现时，只能用引擎的原始输出自己做变换。

## 均匀整数分布（[rand.dist.uni.int]）

¶1：产生 a ≤ i ≤ b 的随机整数，P(i | a, b) = 1/(b − a + 1)。

要点：

- **闭区间**。`uniform_int_distribution<int>(1, 6)` 产生 1 到 6，**包括** 6。
- **精确等概率**。概率函数是常数 1/(b − a + 1)，没有"近似"二字。只要引擎是理想均匀的，实现必须消除取模偏差——通常用拒绝采样（引擎值落在不能整除的尾部就重抽）。这正是它比 `rand() % n` 好的地方（见 [[rand]]）。
- **默认参数**。默认构造等价于 `(0)`，而 `b` 的默认实参是 `numeric_limits<IntType>::max()`——默认得到的是 [0, max]，不是 [0, 1]。
- ¶2 *Preconditions*：a ≤ b。`uniform_int_distribution<int>(6, 1)` 是 UB，不会自动交换。
- 全范围也可以：`uniform_int_distribution<long long>(LLONG_MIN, LLONG_MAX)` 合法，此时 b − a + 1 在数学上是 2⁶⁴，不能用 `long long` 表示，但 [rand.general] ¶4 说计算按数学实数理解，实现要正确处理。
- 结果类型 `IntType` 受 [rand.req.genl] 限制：`char`、`bool` 不行，`signed char`、`unsigned char` 可以（见 [[rand.req]]）。
- 它是当前草案中唯一被标注为"部分 freestanding"的分布。

## 均匀实数分布（[rand.dist.uni.real]）

¶1：产生 a ≤ x < b 的随机数，p(x | a, b) = 1/(b − a)。注释：这意味着 a == b 时 p(x | a, b) 无定义。

- **半开区间** [a, b)，与整数版的闭区间不同。
- 默认构造等价于 `(0.0)`，`b` 默认 1.0，即 [0, 1)。
- ¶2 *Preconditions*：a ≤ b，**且** b − a ≤ `numeric_limits<RealType>::max()`。第二条意味着 `uniform_real_distribution<double>(-DBL_MAX, DBL_MAX)` 是 UB：区间长度 2·DBL_MAX 不可表示。
- a == b 满足前置条件，但注释说概率密度无定义——标准没有说此时返回什么。本机 libc++ 对 `(2.0, 2.0)` 返回 2.0；不要依赖这一点。

!!! pitfall "半开区间并不总是半开"
    数学上 x < b，但实现通常计算 a + (b − a)·u，其中 u 来自 `generate_canonical`。即使 u < 1，乘法和加法的舍入也可能让结果等于 b；再加上 libc++ 的 `generate_canonical` 本身可能返回 1.0（见 [[rand.util]]），`uniform_real_distribution` 在实践中偶尔会返回 b。对 b 敏感的代码（例如把结果当作 `[0, n)` 的比例去下标）应当自己夹紧。

## 其余参数分布一览

下表概括伯努利族、泊松族、正态族共 16 个分布。"默认"指默认构造函数等价的参数；所有前置条件违反都是 UB。

| 分布 | 结果类型 | 参数（默认） | 取值范围 | 前置条件 |
|---|---|---|---|---|
| `bernoulli_distribution` | `bool` | p = 0.5 | {false, true} | 0 ≤ p ≤ 1 |
| `binomial_distribution` | `IntType` | t = 1, p = 0.5 | 0 ≤ i ≤ t | 0 ≤ p ≤ 1, 0 ≤ t |
| `geometric_distribution` | `IntType` | p = 0.5 | i ≥ 0 | 0 < p < 1 |
| `negative_binomial_distribution` | `IntType` | k = 1, p = 0.5 | i ≥ 0 | 0 < p ≤ 1, 0 < k |
| `poisson_distribution` | `IntType` | mean = 1.0 | i ≥ 0 | 0 < mean |
| `exponential_distribution` | `RealType` | λ = 1.0 | x > 0 | 0 < λ |
| `gamma_distribution` | `RealType` | α = 1.0, β = 1.0 | x > 0 | 0 < α, 0 < β |
| `weibull_distribution` | `RealType` | a = 1.0, b = 1.0 | x ≥ 0 | 0 < a, 0 < b |
| `extreme_value_distribution` | `RealType` | a = 0.0, b = 1.0 | 实数 | 0 < b |
| `normal_distribution` | `RealType` | μ = 0.0, σ = 1.0 | 实数 | 0 < σ |
| `lognormal_distribution` | `RealType` | m = 0.0, s = 1.0 | x > 0 | 0 < s |
| `chi_squared_distribution` | `RealType` | n = 1.0 | x > 0 | 0 < n |
| `cauchy_distribution` | `RealType` | a = 0.0, b = 1.0 | 实数 | 0 < b |
| `fisher_f_distribution` | `RealType` | m = 1.0, n = 1.0 | x ≥ 0 | 0 < m, 0 < n |
| `student_t_distribution` | `RealType` | n = 1.0 | 实数 | 0 < n |

各行对应的子条款依次是 [rand.dist.bern.bernoulli]、[rand.dist.bern.bin]、[rand.dist.bern.geo]、[rand.dist.bern.negbin]、[rand.dist.pois.poisson]、[rand.dist.pois.exp]、[rand.dist.pois.gamma]、[rand.dist.pois.weibull]、[rand.dist.pois.extreme]、[rand.dist.norm.normal]、[rand.dist.norm.lognormal]、[rand.dist.norm.chisq]、[rand.dist.norm.cauchy]、[rand.dist.norm.f]、[rand.dist.norm.t]，每个都由"公式 + 概要 + 构造函数 ¶2 前置条件 + 访问器"组成。

几处值得细读的地方：

- **`bernoulli_distribution` 不是模板**，结果固定是 `bool`，参数 p 固定是 `double`。同样，二项、几何、负二项、泊松分布的概率/均值参数也都是 `double`，与 `IntType` 无关。
- **几何分布从 0 开始计数**：P(i | p) = p·(1 − p)ⁱ，i 是"第一次成功之前失败的次数"，不是"第几次成功"。p = 1 被前置条件排除（0 < p < 1）。
- **负二项分布**：前置条件允许 p = 1，但公式中的注释说 p == 1 时 P(i | k, p) 无定义——又一处"满足前置条件、标准却不说结果"的边角。
- **正态分布的 σ 必须严格大于 0**：`normal_distribution<double>(mu, 0.0)` 是 UB，不是"总返回 mu"。需要退化情形时自己特判。
- **正态族的参数名与常见记法不同**：`lognormal_distribution(m, s)` 的 m、s 是**对数**的均值与标准差，不是分布本身的；`extreme_value_distribution` 的 a、b 是位置与尺度（Gumbel 分布）。脚注 225 说明极值分布也称 Gumbel 分布。
- **有内部状态的分布**：正态分布（及基于它的对数正态、χ²、t、F 分布）的典型实现一次产生两个值、缓存一个。所以 `reset()` 有实际作用，`d(g1)` 与 `d(g2)` 交替调用时，第二次调用可能根本不消耗 `g2`（见 [[rand]] 的思考题）。

```cpp run title="geometric-count.cpp" ok
#include <random>

int main() {
  std::mt19937 g(1);
  std::geometric_distribution<int> fails(0.25);     // 成功概率 1/4
  int sum = 0;
  for (int i = 0; i < 100000; ++i) sum += fails(g);
  double mean = sum / 100000.0;                     // 期望 (1 − p)/p = 3，不是 1/p = 4
  return (mean > 2.9 && mean < 3.1) ? 0 : 1;
}
```

## 抽样分布（[rand.dist.samp]）

### discrete_distribution（[rand.dist.samp.discrete]）

¶1：产生 0 ≤ i < n 的整数，P(i) = pᵢ。¶2：除非另有规定，pₖ = wₖ / S，其中**权重** wₖ 必须非负、非 NaN、非无穷，且 S = w₀ + … + wₙ₋₁ > 0。这些是对参数的要求，违反是 UB。

构造方式：

- ¶3 默认构造：n = 1，p₀ = 1——**总是返回 0**（注释）。
- ¶4–¶6 迭代器区间 `(firstW, lastW)`：*Mandates* 值类型可转换为 `double`；空区间等价于默认构造。
- ¶7 `initializer_list<double>`：同上。
- ¶8–¶11 `(nw, xmin, xmax, fw)`：把 [xmin, xmax] 等分成 n 段，权重取 fw 在每段中点的值；*Preconditions*：δ = (xmax − xmin)/n > 0；fw 的调用次数不超过 n。
- ¶12 `probabilities()`：返回归一化后的 pₖ。

```cpp run title="discrete.cpp" ok
#include <random>
#include <vector>

int main() {
  std::discrete_distribution<int> w{1.0, 0.0, 3.0};     // P(0)=1/4, P(1)=0, P(2)=3/4
  std::vector<double> p = w.probabilities();            // {0.25, 0, 0.75}
  std::mt19937 g(7);
  int c[3] = {};
  for (int i = 0; i < 100000; ++i) ++c[w(g)];
  return (c[1] == 0 && p[2] == 0.75) ? 0 : 1;           // 权重为 0 的下标永远不会出现
}
```

`discrete_distribution(il)` 接受 `initializer_list<double>`，所以 `discrete_distribution<int> d{3};` 是"一个权重为 3 的分布"（总是返回 0），而 `uniform_int_distribution<int> d{3};` 是 [3, INT_MAX]——同样的花括号，含义完全不同。

### piecewise_constant_distribution（[rand.dist.samp.pconst]）

¶1：在每个子区间 [bᵢ, bᵢ₊₁) 上均匀分布的随机数 x，b₀ ≤ x < bₙ，密度为 ρᵢ。¶2：区间边界必须严格递增；ρₖ = wₖ / (S·(bₖ₊₁ − bₖ))，权重要求同上。

- ¶3 默认构造：一个区间 [0, 1)，即 [0, 1) 上的均匀分布。
- ¶4–¶6 `(firstB, lastB, firstW)`：边界区间少于两个点时退化为默认；否则 n + 1 个边界、**至少** n 个权重（多余的被忽略）。注意权重只给了起始迭代器，长度由边界决定——给少了是越界读。
- ¶7–¶9 `(initializer_list<RealType> bl, fw)`：权重取 fw 在每个子区间**中点**的值。
- ¶10–¶13 `(nw, xmin, xmax, fw)`：等分区间，权重取 fw 在中点的值。
- ¶14–¶15 `intervals()`、`densities()`。

### piecewise_linear_distribution（[rand.dist.samp.plinear]）

与分段常数分布结构平行，区别是密度在每个子区间上**线性插值**：n + 1 个边界对应 n + 1 个权重（不是 n 个），密度在边界处取对应权重归一化后的值，中间线性变化。各构造函数中 fw 的调用次数上限因此是 n + 1。它可以用来近似任意连续密度：给出采样点上的密度值，得到折线近似。

## 常见误用

!!! pitfall "每次调用都新建分布对象"
    `int roll(G& g) { return std::uniform_int_distribution<int>(1, 6)(g); }` 是正确的——分布对象很轻，构造成本低。但对**有内部状态**的分布（正态分布）这样写，会丢掉缓存的第二个值，浪费一半的引擎输出。需要不同参数时，用 `d(g, param_type(...))`（[[rand.req]]）。

!!! pitfall "按值传递引擎"
    `int roll(std::mt19937 g)` 每次复制约 2.5 KB 的状态，调用方的引擎不推进，每次调用得到相同结果。引擎一律按引用传。

!!! pitfall "依赖分布的输出写测试"
    测试断言"种子 42 掷出 4"，换编译器或升级标准库就失败。要么只断言统计性质，要么直接断言引擎输出（[rand.predef] 给了标准值）。

## 小结

| 分布 | 关键事实 |
|---|---|
| 全体 | 算法由实现定义 → 跨实现不可复现；定义域外概率为 0 |
| `uniform_int_distribution` | 闭区间 [a, b]、严格等概率、默认 b 为 `max()`、a ≤ b |
| `uniform_real_distribution` | 半开区间 [a, b)、b − a 必须可表示、实践中可能返回 b |
| 参数分布 | 前置条件多为严格不等式（σ > 0、λ > 0…），违反即 UB |
| `discrete_distribution` | 权重非负有限、和为正；默认总返回 0 |
| 分段分布 | 边界严格递增；常数版 n 个权重，线性版 n + 1 个 |
