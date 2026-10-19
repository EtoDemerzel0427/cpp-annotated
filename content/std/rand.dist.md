---
title: 随机数分布
summary: 标准的 20 个分布：算法由实现定义，所以结果跨实现不可复现；两个均匀分布的区间和前置条件；其余分布的参数、默认值和前置条件；按权重抽样的三个分布；常见误用。
status: done
covers: *
related: rand, rand.req, rand.util, rand.eng, alg.random.shuffle, alg.random.sample
tags: 标准库, 随机数, 分布, uniform_int_distribution, 可复现性
updated: 2026-10-19
---

!!! tldr
    - 标准只规定每个分布的结果服从什么概率分布，变换算法由实现定义。同一引擎、同一种子，换一个标准库就可能得到不同的结果。
    - `uniform_int_distribution(a, b)` 是闭区间 [a, b]，每个值概率严格相等；默认构造得到 [0, `max()`]，不是 [0, 1]。
    - `uniform_real_distribution(a, b)` 名义上是半开区间 [a, b)，但实践中可能返回 b。
    - 各分布的前置条件多是严格不等式，例如正态分布要求 σ > 0。违反前置条件是 UB，不会退化成常数。
    - `discrete_distribution` 按权重抽取下标，权重必须非负、有限，且总和为正。

## 同一个种子，不同的点数

```cpp run title="dist-not-portable.cpp" impl
#include <cstdio>
#include <random>

int main() {
  std::mt19937 g(42);            // 引擎：处处相同
  std::uniform_int_distribution<int> die(1, 6);
  for (int i = 0; i < 8; ++i) std::printf("%d ", die(g));
  // 本机 libc++ 输出：4 5 3 5 5 2 3 3
  // 其他标准库可以输出不同的序列
}
```

`mt19937(42)` 的输出是规定好的，前两个在任何实现上都是 1608637542 和 3421126067（[[rand.eng]]）。但 [rand.dist.general] ¶3 规定，产生各个分布的算法由实现定义。正态分布可以用 Box–Muller、Marsaglia 极坐标法或 Ziggurat 算法；均匀整数可以用不同的拒绝采样策略。它们消耗引擎输出的数量和方式不同，结果自然不同。

所以需要跨平台复现时，只能使用引擎的原始输出，自己写分布变换。测试也不应断言某个种子掷出某个点数。

分布的共同接口，例如 `param_type`、`reset()`、`d(g, p)`，在 [[rand.req]] 中规定（[[g:random-number-distribution]]）。本页讲每个分布特有的内容：概率函数、参数、前置条件。

## 均匀整数分布（[rand.dist.uni.int]）

¶1 `uniform_int_distribution<IntType>` 产生 a ≤ i ≤ b 的整数，P(i | a, b) = 1/(b − a + 1)。

- 区间是闭的。`uniform_int_distribution<int>(1, 6)` 产生 1 到 6，包括 6。
- 概率严格相等。只要引擎是均匀的，实现就必须消除 `rand() % n` 那样的取模偏差，通常用拒绝采样：引擎值落在不能整除的尾部时重抽（[[rand]]）。
- 默认构造等价于 `(0)`，而 `b` 的默认实参是 `numeric_limits<IntType>::max()`，所以默认得到的是 [0, `max()`]。
- ¶2 前置条件是 a ≤ b。`uniform_int_distribution<int>(6, 1)` 是 UB，不会自动交换。
- 全范围也可以：`uniform_int_distribution<long long>(LLONG_MIN, LLONG_MAX)` 合法。此时 b − a + 1 在数学上是 2⁶⁴，`long long` 表示不了，但 [rand] 的计算按数学实数进行（[[rand]]），实现要正确处理。
- `IntType` 不能是 `char` 或 `bool`，可以是 `signed char` 或 `unsigned char`（[[rand.req]]）。

## 均匀实数分布（[rand.dist.uni.real]）

¶1 `uniform_real_distribution<RealType>` 产生 a ≤ x < b 的数，概率密度 p(x | a, b) = 1/(b − a)。注释指出，这意味着 a == b 时密度无定义。

- 区间名义上是半开的 [a, b)，与整数版的闭区间不同。
- 默认构造等价于 `(0.0)`，`b` 默认为 1.0，即 [0, 1)。
- ¶2 前置条件是 a ≤ b，并且 b − a ≤ `numeric_limits<RealType>::max()`。所以 `uniform_real_distribution<double>(-DBL_MAX, DBL_MAX)` 是 UB，因为区间长度不可表示。
- a == b 满足前置条件，但标准没有说此时返回什么。本机 libc++ 对 `(2.0, 2.0)` 返回 2.0，不要依赖这一点。

!!! pitfall "半开区间并不总是半开"
    实现通常计算 a + (b − a)·u，其中 u 来自 `generate_canonical`。即使 u < 1，乘法和加法的舍入也可能让结果等于 b。再加上 libc++ 的 `generate_canonical` 本身可能返回 1.0（[[rand.util]]），`uniform_real_distribution` 实际上偶尔会返回 b。对 b 敏感的代码，例如把结果乘以 n 当作数组下标，应当自己把结果限制在范围内。

## 其余参数分布

除了两个均匀分布和三个抽样分布，其余 15 个分布按数学族分在伯努利族 [rand.dist.bern]、泊松族 [rand.dist.pois] 和正态族 [rand.dist.norm] 三个子条款里。每个分布的规范结构都一样：¶1 给出概率函数，然后是类概要，¶2 是构造函数的前置条件，后面几段是参数访问器。

下表的默认参数是默认构造函数等价的参数；违反前置条件都是 UB。

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

几处容易弄错的地方：

- `bernoulli_distribution` 不是模板，结果固定是 `bool`，参数 p 是 `double`。二项、几何、负二项、泊松分布的概率或均值参数也都是 `double`，与 `IntType` 无关。
- 几何分布从 0 开始计数：P(i | p) = p·(1 − p)ⁱ，i 是第一次成功之前失败的次数，不是第几次成功。下面的例子验证了均值是 (1 − p)/p 而不是 1/p。
- 负二项分布的前置条件允许 p = 1，但注释说 p == 1 时概率函数无定义。这又是一处满足前置条件、标准却没说结果的情形。
- 正态分布的 σ 必须严格大于 0。`normal_distribution<double>(mu, 0.0)` 是 UB，不是总返回 mu；需要退化情形时自己特判。
- `lognormal_distribution(m, s)` 的 m、s 是对数的均值和标准差，不是分布本身的。`extreme_value_distribution` 的 a、b 是位置和尺度，脚注 225 说明它也叫 Gumbel 分布。
- 正态分布以及基于它的对数正态、χ²、t、F 分布，典型实现一次算出两个值、缓存一个，所以 `reset()` 有实际作用（[[rand]] 的思考题）。

```cpp run title="geometric-count.cpp" ok
#include <random>

int main() {
  std::mt19937 g(1);
  std::geometric_distribution<int> fails(0.25);   // 成功概率 1/4
  int sum = 0;
  for (int i = 0; i < 100000; ++i) sum += fails(g);
  double mean = sum / 100000.0;     // 期望 (1 − p)/p = 3
  return (mean > 2.9 && mean < 3.1) ? 0 : 1;
}
```

## 按权重抽样（[rand.dist.samp]）

### discrete_distribution（[rand.dist.samp.discrete]）

```cpp run title="discrete.cpp" ok
#include <random>
#include <vector>

int main() {
  // P(0) = 1/4, P(1) = 0, P(2) = 3/4
  std::discrete_distribution<int> w{1.0, 0.0, 3.0};
  std::vector<double> p = w.probabilities();   // {0.25, 0, 0.75}
  std::mt19937 g(7);
  int c[3] = {};
  for (int i = 0; i < 100000; ++i) ++c[w(g)];
  return (c[1] == 0 && p[2] == 0.75) ? 0 : 1;  // 下标 1 从不出现
}
```

¶1 `discrete_distribution` 产生 0 ≤ i < n 的整数，P(i) = pᵢ。¶2 除非另有规定，pₖ = wₖ / S，其中**权重** wₖ 必须非负、不是 NaN、不是无穷，并且总和 S > 0。违反这些要求是 UB。

构造方式有四种：

- ¶3 默认构造：n = 1，p₀ = 1。注释说这样的对象总是返回 0。
- ¶4–¶6 迭代器区间 `(firstW, lastW)`：值类型必须可转换为 `double`；空区间等价于默认构造。
- ¶7 `initializer_list<double>`：同上，例子用的就是这种。
- ¶8–¶11 `(nw, xmin, xmax, fw)`：把 [xmin, xmax] 等分成 n 段，每段的权重取 `fw` 在该段中点的值。前置条件是每段宽度 δ = (xmax − xmin)/n > 0，`fw` 最多调用 n 次。

¶12 `probabilities()` 返回归一化后的 pₖ。

`discrete_distribution` 接受 `initializer_list<double>`，所以 `discrete_distribution<int> d{3};` 是一个只有一个权重 3 的分布，总是返回 0。而 `uniform_int_distribution<int> d{3};` 调用 `(a, b)` 构造函数，得到 [3, `INT_MAX`]。同样的花括号，含义完全不同。

### piecewise_constant_distribution（[rand.dist.samp.pconst]）

¶1 `piecewise_constant_distribution` 产生 b₀ ≤ x < bₙ 的数，在每个子区间 [bᵢ, bᵢ₊₁) 上均匀分布，密度为 ρᵢ。¶2 区间边界必须严格递增；ρₖ = wₖ / (S·(bₖ₊₁ − bₖ))，权重要求与 `discrete_distribution` 相同。

- ¶3 默认构造：一个区间 [0, 1)，即 [0, 1) 上的均匀分布。
- ¶4–¶6 `(firstB, lastB, firstW)`：边界少于两个时退化为默认；否则 n + 1 个边界对应至少 n 个权重，多余的忽略。权重只给了起始迭代器，长度由边界决定，给少了就是越界读。
- ¶7–¶9 `(initializer_list<RealType> bl, fw)`：权重取 `fw` 在每个子区间中点的值。
- ¶10–¶13 `(nw, xmin, xmax, fw)`：等分区间，权重取 `fw` 在中点的值。
- ¶14–¶15 `intervals()`、`densities()` 返回边界和密度。

### piecewise_linear_distribution（[rand.dist.samp.plinear]）

结构与分段常数分布平行。区别在于密度在每个子区间上线性插值：n + 1 个边界对应 n + 1 个权重，密度在边界处取对应权重归一化后的值，中间线性变化。各构造函数中 `fw` 的调用次数上限因此是 n + 1。给出若干采样点上的密度值，就能得到任意连续密度的折线近似。

## 常见误用

!!! pitfall "每次调用都新建分布对象"
    `int roll(G& g) { return std::uniform_int_distribution<int>(1, 6)(g); }` 是正确的，分布对象很轻，构造成本低。但对有内部状态的分布（例如正态分布）这样写，会丢掉缓存的第二个值，浪费一半的引擎输出。需要不同参数时，用 `d(g, param_type(...))`（[[rand.req]]）。

!!! pitfall "按值传递引擎"
    `int roll(std::mt19937 g)` 每次复制约 2.5 KB 的状态，而且调用方的引擎不会推进，每次调用得到相同的结果。引擎应当按引用传递。

!!! pitfall "用分布的输出写测试"
    断言种子 42 掷出 4 的测试，换编译器或升级标准库就会失败。要么只断言统计性质，要么直接断言引擎的输出，[[rand.eng]] 给出了标准规定的值。

<details class="fine" markdown="1"><summary>其余条文</summary>

[rand.dist.general]：¶1 实例化得到的类型满足分布要求；¶2 概要中不列出复制、流运算符和相等运算符；¶4 概率函数在所述定义域之外处处为 0。

各分布的 ¶3 *Remarks* 说明构造函数的实参对应哪个参数，其后的 *Returns* 段规定访问器（如 `a()`、`mean()`、`stddev()`）返回构造时的参数值。

</details>
