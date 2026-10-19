---
title: 随机数引擎与引擎适配器
summary: 标准提供的四种引擎（线性同余、梅森旋转、带借位减法、Philox）和三种适配器各自怎样工作、怎样播种；mt19937 等预定义别名的规定输出；为什么 mt19937 g(s) 不会误选种子序列构造函数。
status: done
covers: *, rand.adapt, rand.adapt.general, rand.adapt.disc, rand.adapt.ibits, rand.adapt.shuf, rand.predef
papers: P2075R6
related: rand, rand.req, rand.util, rand.device, over.match
tags: 标准库, 随机数, 引擎, mt19937, philox
updated: 2026-10-19
---

!!! tldr
    - 标准引擎的状态、转移算法、输出算法、播种过程和文本表示都逐位规定，所以同一种子在任何实现上产生相同序列。每个预定义别名都规定了第 10000 个输出的值。
    - 模板参数之间要满足一定关系（例如线性同余引擎要求 `a < m`），不满足时程序非良构。
    - `mt19937` 只用一个整数播种时，整个约 19937 位的状态都由这个整数决定。
    - `X(Sseq&)` 构造函数对能隐式转换为 `result_type` 的类型不参与重载决议，所以 `std::mt19937 g(s)` 对 `int s` 也能按预期工作。
    - `default_random_engine` 是哪个引擎由实现定义（libc++ 是 `minstd_rand`）。需要质量或可复现性时，应写出具体的引擎类型。

## 引擎的输出是规定好的（[rand.predef]）

```cpp run title="required-behavior.cpp" ok
#include <cassert>
#include <random>

template<class E> auto nth10000() {
  E e;               // 默认构造
  e.discard(9999);
  return e();        // 第 10000 次调用
}

int main() {
  assert(nth10000<std::mt19937>() == 4123659995u);
  assert(nth10000<std::mt19937_64>() == 9981545732273789042u);
  assert(nth10000<std::minstd_rand>() == 399268537u);
  assert(nth10000<std::ranlux24>() == 9901578u);
}
```

[rand.predef] 给每个预定义别名都附了一条 *Required behavior*：默认构造的对象，第 10000 次调用必须产生给定的值。这条规定能成立，是因为引擎的一切都是确定的：状态的含义、每一步的转移、每个输出的计算、播种过程、文本表示的格式，全部逐位规定。本机 libc++ 通过了所有已实现别名的这项检验。

| 别名 | 定义 | 第 10000 个输出 |
|---|---|---|
| `minstd_rand0` | `linear_congruential_engine<uint_fast32_t, 16807, 0, 2147483647>` | 1043618065 |
| `minstd_rand` | 同上，a = 48271 | 399268537 |
| `mt19937` | `mersenne_twister_engine<uint_fast32_t, 32, 624, 397, 31, …>` | 4123659995 |
| `mt19937_64` | `mersenne_twister_engine<uint_fast64_t, 64, 312, 156, 31, …>` | 9981545732273789042 |
| `ranlux24_base` | `subtract_with_carry_engine<uint_fast32_t, 24, 10, 24>` | 7937952 |
| `ranlux48_base` | `subtract_with_carry_engine<uint_fast64_t, 48, 5, 12>` | 61839128582725 |
| `ranlux24` | `discard_block_engine<ranlux24_base, 223, 23>` | 9901578 |
| `ranlux48` | `discard_block_engine<ranlux48_base, 389, 11>` | 249142670248501 |
| `knuth_b` | `shuffle_order_engine<minstd_rand0, 256>` | 1112339016 |
| `philox4x32` {{c++26}} | `philox_engine<uint_fast32_t, 32, 4, 10, …>` | 1955073260 |
| `philox4x64` {{c++26}} | `philox_engine<uint_fast64_t, 64, 4, 10, …>` | 3409172418970261260 |

`result_type` 是 `uint_fast32_t`，在 64 位 Linux 上通常是 64 位的 `unsigned long`。`mt19937` 的字宽 w 仍是 32，输出仍在 [0, 2³² − 1] 内，只是对象中每个状态字可能占 8 字节。

¶10 `default_random_engine` 是哪个引擎由实现定义。注释说实现可以按性能、大小、质量来选，目的是给随意、轻量的用途提供至少可以接受的行为；不同实现可以选不同的引擎，所以用它的代码不能期望跨实现得到相同的序列。本机 libc++ 中它是 `minstd_rand`，一个周期约 2³¹、统计质量一般的线性同余引擎。

下面依次介绍四种引擎模板。读它们之前需要知道 [[rand.req]] 的模型：引擎有一个状态，每次调用先用**转移算法** TA 把状态推进一步，再用**生成算法** GA 从状态算出输出。[rand] 中的公式都按数学实数计算（[[rand]]）。

## 线性同余引擎（[rand.eng.lcong]）

`linear_congruential_engine<UIntType, a, c, m>` 是最简单的引擎。

¶1 状态只有一个整数 xᵢ。转移算法是 TA(xᵢ) = (a·xᵢ + c) mod m，生成算法 GA(xᵢ) = xᵢ₊₁，返回的就是新状态。`max()` 为 m − 1；`min()` 在 `c == 0` 时为 1，否则为 0。原因是 `c == 0` 时状态 0 是不动点，引擎永远不会产生 0。

¶2 模板实参 `m` 为 0 时，模数取 `numeric_limits<result_type>::max() + 1`，这个值不必能用 `result_type` 表示。所以 `m = 0` 表示对 2ʷ 取模。

¶3 `m` 不为 0 时，必须有 `a < m` 且 `c < m`。

¶5 `explicit linear_congruential_engine(result_type s)`：如果 `c mod m` 和 `s mod m` 都是 0，状态设为 1，否则设为 `s mod m`。这一步专门避开 `c == 0` 时的不动点 0，所以 `minstd_rand(0)` 与 `minstd_rand(1)` 等价。

¶6 用种子序列播种时，令 k = ⌈log₂ m / 32⌉，请求 k + 3 个 32 位值，跳过前 3 个，用后 k 个拼成状态，同样把 0 替换成 1。

a·xᵢ 可能超过 `UIntType` 的范围，但公式按数学实数计算，实现必须得到数学上正确的模结果。

## 梅森旋转引擎（[rand.eng.mers]）

`mersenne_twister_engine<UIntType, w, n, m, r, a, u, d, s, b, t, c, l, f>` 是最常用的引擎，`mt19937` 就是它的一个特化。

¶1 它产生 [0, 2ʷ − 1] 内的整数，状态是 n 个 w 位的值组成的序列 X，下标对 n 取模。脚注 221 解释了名字：参数选得合适时，周期与一个大的梅森素数密切相关，`mt19937` 的周期是 2¹⁹⁹³⁷ − 1。

¶2 转移算法是一个扭转的广义反馈移位寄存器：

1. 把 Xᵢ₋ₙ 的高 w − r 位与 Xᵢ₊₁₋ₙ 的低 r 位拼成 Y；
2. 令 α = a·(Y bitand 1)，置 Xᵢ = Xᵢ₊ₘ₋ₙ xor (Y rshift 1) xor α。

¶3 生成算法对 Xᵢ 依次做四步移位、掩码、异或，称为**回火**（tempering），用来改善输出的均匀性。回火是可逆的线性变换，所以从输出可以还原状态，这就是它不能用于密码学的原因（[[rand]]）。

¶4 列出了参数之间的关系，例如 `0 < m <= n`、`2u < w`、`w <= numeric_limits<UIntType>::digits`，各个掩码不超过 2ʷ − 1。

¶6 `explicit mersenne_twister_engine(result_type value)` 先置 X₋ₙ = value mod 2ʷ，再对 i = 1 − n, …, −1 用固定的递推算出其余 Xᵢ。整个约 19937 位的状态都由这一个值决定，所以用单个整数播种的 `mt19937` 最多只有 2³² 种初始状态。

¶8 用种子序列播种时，令 k = ⌈w/32⌉，请求 n·k 个 32 位值，每 k 个拼成一个 Xᵢ。全零状态是不动点，所以如果拼出的状态（除去 X₋ₙ 低 r 位以外）全是 0，就把 X₋ₙ 改成 2ʷ − 1。

## 带借位减法引擎（[rand.eng.sub]）

`subtract_with_carry_engine<UIntType, w, s, r>` 是一种滞后斐波那契生成器，`ranlux` 系列的基础。

¶2–¶4 状态是 r 个整数 0 ≤ Xᵢ < m = 2ʷ，外加一个**借位**（carry）c ∈ {0, 1}。每一步计算 Y = Xᵢ₋ₛ − Xᵢ₋ᵣ − c，令 Xᵢ = Y mod m，Y < 0 时 c = 1，否则 c = 0，然后返回新的 Xᵢ。注释指出这等价于一个模数巨大的乘同余生成器。

¶5 参数要求 `0 < s < r`、`0 < w <= digits`。

¶7 `explicit subtract_with_carry_engine(result_type value)` 先构造一个 `linear_congruential_engine<uint_least32_t, 40014u, 0u, 2147483563u>`，种子为 `value == 0 ? default_seed : value % 2147483563u`，再用它的输出拼出初始状态。默认构造函数和 `seed()` 的默认实参都是 `0u`，所以默认播种实际使用 `default_seed`（19780503）。这里的 `default_seed` 类型是 `uint_least32_t`，不是 `result_type`。

## Philox 引擎（[rand.eng.philox]）{{c++26}}

`philox_engine<UIntType, w, n, r, consts...>` 由 [[P2075R6]] 引入，是一种**计数器型**生成器。前三种引擎靠递推推进状态，Philox 则把一个计数器经过 r 轮代换置换网络加密，输出就是加密的结果。

¶1 状态包括：n 个 w 位值组成的计数器 X（看作一个 n·w 位整数 Z）、n/2 个密钥 K、一批 n 个缓存的输出 Y，以及下标 i。密钥由种子生成，除非重新播种否则不变。

¶2–¶3 每次调用先把 i 加 1；i 到达 n 时，计算 Y = Philox(K, X)，计数器 Z 加 1，i 归零。然后返回 Yᵢ。

¶4–¶5 一轮 Philox 先按表 129 置换 X，再对每一对值做乘法取高位和低位，并与轮密钥异或。r 轮之后的结果就是 Y。

¶6 *Mandates*：`sizeof...(consts) == n`，n 为 2 或 4，`0 < r`，`0 < w <= digits`。¶7 `consts` 按乘数、轮常数交替排列：[M₀, C₀, M₁, C₁, …]。

¶9–¶10 播种只设置密钥 K，计数器清零，i 置为 n − 1。¶11 `set_counter(c)` 直接设置计数器，注意 `c` 的元素顺序与 X 相反。

计数器型设计有两个好处。`discard(z)` 只需给计数器加 z，是常数时间。多个线程或 GPU 线程可以用相同的密钥、不同的计数器区间，得到互不重叠的流，而不必传递大块状态。本机 libc++ 尚未实现 `philox_engine`。

## 引擎适配器（[rand.adapt]）

**引擎适配器**包装另一个引擎（**基引擎**），改变它输出序列的性质（[[rand.req]]）。

### discard_block_engine（[rand.adapt.disc]）

`discard_block_engine<Engine, p, r>` 从基引擎每产生的 p 个值中只用前 r 个，丢掉其余 p − r 个。

¶1–¶3 状态是基引擎的状态加一个计数 n。每次调用时，如果 n ≥ r，先让基引擎空转 p − r 步并把 n 置 0；然后 n 加 1，返回基引擎的下一个输出。¶4 要求 `0 < r <= p`。

这是 RANLUX 的做法。带借位减法引擎相邻输出之间相关性较强，丢掉大部分输出能换来很好的统计质量，代价是速度。`ranlux24` 每 223 个值只用 23 个。

### independent_bits_engine（[rand.adapt.ibits]）

`independent_bits_engine<Engine, w, UIntType>` 把基引擎的输出拼成恰好 w 位的结果。

¶1 状态就是基引擎的状态。¶2–¶4 设基引擎值域大小为 R，算法决定调用基引擎几次、每次取多少低位，并拒绝重取落在值域尾部的值。这样即使 R 不是 2 的幂（例如 `minstd_rand` 的值域 [1, 2³¹ − 2]），结果的每一位也是均匀独立的。¶5 要求 `0 < w <= numeric_limits<result_type>::digits`。

用它从 32 位引擎得到均匀的随机字节时，`UIntType` 至少要和 `short` 一样宽（[[rand.req]]），不能直接写 `unsigned char`：

```cpp run title="random-bytes.cpp" ok
#include <algorithm>
#include <random>
#include <vector>

int main() {
  std::independent_bits_engine<std::mt19937, 8, unsigned short>
      bytes(1);
  static_assert(bytes.min() == 0 && bytes.max() == 255);
  std::vector<unsigned char> buf(16);
  std::ranges::generate(buf, [&] {
    return static_cast<unsigned char>(bytes());
  });
}
```

### shuffle_order_engine（[rand.adapt.shuf]）

`shuffle_order_engine<Engine, k>` 产生与基引擎相同的值，但打乱交付的顺序（Bays–Durham 洗牌）。

¶1 状态是基引擎的状态、一个值 Y 和一张 k 项的表 V。¶2–¶3 每次调用用 Y 算出下标 j，令 Y = Vⱼ，再用基引擎的下一个输出填回 Vⱼ，然后返回 Y。¶4 要求 `0 < k`。`knuth_b` 是 `shuffle_order_engine<minstd_rand0, 256>`。

## 用整数播种时不会选中 Sseq 构造函数（[rand.eng.general] ¶7）

每个引擎和适配器 `X` 都有一个接受种子序列的构造函数和 `seed` 重载：

```cpp
template<class Sseq> explicit X(Sseq& q);
template<class Sseq> void seed(Sseq& q);
```

看下面的代码：

```cpp run title="sseq-overload.cpp" ok
#include <random>

int main() {
  int s = 42;
  std::mt19937 g(s);   // 选中 mt19937(result_type)
  std::mt19937 h(42u);
  return g == h ? 0 : 1;
}
```

`mt19937(result_type)` 需要把 `int` 转换为 `uint_fast32_t`；而模板 `X(Sseq&)` 以 `Sseq = int` 推导成功，`int&` 绑定 `int` 左值是精确匹配，按 [[over.ics.rank]] 更好。重载决议本应选中它，然后在调用 `q.generate(...)` 处编译失败。

¶7 规定：用不能作为种子序列的类型调用这两个函数时，它们不参与重载决议。实现判断到什么程度是未指明的，但至少要把能隐式转换为 `X::result_type` 的类型排除。有了这条，`std::mt19937 g(s)` 才能按直觉工作。实现通常用 SFINAE 或 `requires` 子句来做这项检查。

## 参数关系与选型

[rand.eng.general] ¶6 和 [rand.adapt.general] ¶6 规定：每个模板都要求它的常量模板参数之间满足某些关系，不满足时程序非良构。前面各节列出的 `a < m`、`0 < s < r`、`0 < r <= p` 都属于此类。

各引擎的大致特点如下。这些质量评价是领域内的常识，标准本身只规定算法，不评价质量。

| 引擎 | 状态大小 | 速度 | 质量 | 备注 |
|---|---|---|---|---|
| `minstd_rand` | 4–8 字节 | 快 | 差 | 低位周期短，值域不是 2 的幂 |
| `mt19937`、`mt19937_64` | 约 2.5 KB | 快 | 好，但有已知的线性特征 | 最常用；播种要提供足够的熵 |
| `ranlux24`、`ranlux48` | 小 | 慢 | 很好 | 物理模拟的传统选择 |
| `knuth_b` | 约 1 KB | 中 | 一般 | 主要是历史意义 |
| `philox4x32`、`philox4x64` | 小 | 快，易于并行 | 好 | C++26；`discard` 是常数时间 |

<details class="fine" markdown="1"><summary>其余条文</summary>

[rand.eng.general] 与 [rand.adapt.general] 的 ¶1–¶5 内容相同：实例化得到的类型满足引擎（或适配器）要求；除非另有规定，每个函数是常数复杂度、不抛异常；形参为 `Sseq& q` 且 `Sseq` 不是 `seed_seq` 的函数，在 `q.generate` 抛异常时抛出同样的异常；概要中不列出复制、流运算符和相等运算符，它们的语义见 [[rand.req]]。

各引擎的文本表示：线性同余引擎是 xᵢ（[rand.eng.lcong] ¶4）；梅森旋转是 Xᵢ₋ₙ, …, Xᵢ₋₁（[rand.eng.mers] ¶5）；带借位减法是 Xᵢ₋ᵣ, …, Xᵢ₋₁ 后接 c（[rand.eng.sub] ¶6）；Philox 是 K、X、i，Y 不写出，读入时由 K 和 X 重建（[rand.eng.philox] ¶8）。适配器的文本表示包含基引擎的表示，再加上各自的额外状态。

[rand.adapt.disc] ¶6 与 [rand.adapt.shuf] ¶6：除复制构造函数外，各构造函数在初始化基引擎之后，分别把计数 n 置 0、依次用基引擎的输出填充 V 和 Y。

[rand.eng.sub] ¶8–¶9：用整数播种恰好调用辅助引擎 n·r 次；用种子序列播种与梅森旋转类似。

</details>

## 思考题

!!! question "1"
    `std::linear_congruential_engine<std::uint32_t, 5, 3, 4> e;` 良构吗？`<std::uint32_t, 5, 3, 0>` 呢？

<details markdown="1">
<summary>答案</summary>

第一个非良构。`m = 4` 不为 0，[rand.eng.lcong] ¶3 要求 `a < m`，而 5 ≥ 4，按 [rand.eng.general] ¶6 程序非良构。

第二个良构。`m = 0` 表示模数是 2³²（¶2），¶3 的关系只在 `m != 0` 时要求。
</details>

!!! question "2"
    为什么 `std::mt19937 g(std::seed_seq{1, 2, 3});` 不能编译？

<details markdown="1">
<summary>答案</summary>

种子序列构造函数的形参是 `Sseq&`，非 const 左值引用不能绑定到临时对象。`result_type` 构造函数也不可行，因为 `seed_seq` 不能转换为整数。要先声明一个具名的 `seed_seq` 变量再传入。形参设计成非 const 引用，是因为 `generate` 不是 const 成员，允许依赖调用历史（[[rand.req]]）。
</details>
