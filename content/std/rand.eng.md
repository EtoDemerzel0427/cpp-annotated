---
title: 随机数引擎与引擎适配器
summary: 四种引擎模板（线性同余、梅森旋转、带借位减法、C++26 的 Philox）与三种适配器（丢弃块、独立比特、洗牌）的状态、转移算法、生成算法和播种规则；参数关系不成立即非良构；Sseq 构造函数何时退出重载决议；预定义别名及其"第 10000 个输出"的规定行为；default_random_engine 由实现定义
status: done
covers: *, rand.adapt, rand.adapt.general, rand.adapt.disc, rand.adapt.ibits, rand.adapt.shuf, rand.predef
papers: P2075R6
related: rand, rand.req, rand.util, rand.device, over.match
tags: 标准库, 随机数, 引擎, mt19937, philox
updated: 2026-10-18
---

[[rand.req]] 规定了"引擎"必须满足的接口；本节给出标准提供的具体引擎。它们的共同特点是**完全确定**：状态的含义、每一步的转移、每个输出的计算、用单个整数或种子序列播种的过程、文本表示的格式，全部逐位规定。这正是引擎能跨实现复现的原因，也是 [rand.predef] 能用"默认构造后第 10000 次调用必须得到某个值"来做一致性检验的前提。

本页覆盖三个子条款：引擎模板 [rand.eng]、适配器模板 [rand.adapt]、预定义别名 [rand.predef]。

## 共同规则（[rand.eng.general]、[rand.adapt.general]）

两个 general 子条款的内容几乎相同：

- ¶1：实例化得到的类型满足引擎（或适配器）要求。
- ¶2：除非另有规定，每个函数的复杂度是常数。
- ¶3：除非另有规定，函数不抛异常。
- ¶4：形参为 `Sseq& q`、且 `Sseq` 不是 `seed_seq` 的函数，在 `q.generate` 抛异常时、抛出它所抛的异常。
- ¶5：概要中不列出复制构造/赋值、流运算符、相等运算符，它们的语义在 [[rand.req]]。
- ¶6：每个模板都要求其常量模板形参之间满足某些关系；**不满足时程序非良构**。

### Sseq 构造函数的重载约束（[rand.eng.general] ¶7）

每个引擎和适配器 `X` 都有

```cpp
template<class Sseq> explicit X(Sseq& q);
template<class Sseq> void seed(Sseq& q);
```

¶7：若以一个**不够格作为种子序列**的类型调用它们，它们不参与重载决议。多大程度上判断"不够格"是**未指明**的，但最低限度是：能**隐式转换为 `X::result_type`** 的类型不够格。

为什么需要这条？看这段代码：

```cpp run title="sseq-overload.cpp" ok
#include <random>

int main() {
  int s = 42;
  std::mt19937 g(s);     // 候选：mt19937(result_type)  —— int → uint_fast32_t，需要转换
                         //       mt19937(Sseq&) [Sseq = int] —— 精确匹配，本来更好！
  std::mt19937 h(42u);
  return g == h ? 0 : 1; // 两者相等：选中的是 result_type 版本
}
```

如果没有 ¶7，模板 `X(Sseq&)` 以 `Sseq = int` 推导成功，`int&` 绑定 `int` 左值是精确匹配，比 `int → unsigned` 的整数转换更好（[[over.ics.rank]]），重载决议会选中它，然后在 `q.generate(...)` 处编译失败。¶7 把"可转换为 `result_type`"的类型排除出去，`mt19937 g(s)` 才能按直觉工作。实现通常用 SFINAE 或 `requires` 实现这个约束（libc++ 有内部特征 `__is_seed_sequence`）。

## 线性同余引擎（[rand.eng.lcong]）

`linear_congruential_engine<UIntType, a, c, m>`

- ¶1：状态大小为 1，是一个整数 xᵢ；转移算法 TA(xᵢ) = (a·xᵢ + c) mod m；生成算法 GA(xᵢ) = xᵢ₊₁（返回新状态）。
- `min()` 在 `c == 0` 时为 1，否则为 0；`max()` 为 m − 1；`default_seed` 为 1。`c == 0` 时状态 0 是不动点，引擎永远不会产生 0，所以最小值是 1。
- ¶2：模板实参 `m` 为 0 时，模数取 `numeric_limits<result_type>::max() + 1`（注释：它不必能用 `result_type` 表示）。这样 `m = 0` 可以表达"对 2ʷ 取模"。
- ¶3：`m != 0` 时要求 `a < m` 且 `c < m`（否则非良构，按 ¶6）。
- ¶4：文本表示就是 xᵢ。
- ¶5：`explicit linear_congruential_engine(result_type s)`：若 `c mod m == 0` 且 `s mod m == 0`，状态设为 1，否则设为 `s mod m`。这一步专门避开 `c == 0` 时的不动点 0：`minstd_rand(0)` 与 `minstd_rand(2147483647)` 都等价于 `minstd_rand(1)`。
- ¶6：用种子序列播种：k = ⌈log₂ m / 32⌉，取 k + 3 个 32 位值，用**后** k 个（跳过前 3 个）拼成 S = (Σ aⱼ₊₃·2³²ʲ) mod m，同样对 0 做替换。

计算 a·xᵢ 时中间结果可能超过 `UIntType` 的范围；[rand.general] ¶4 规定公式按数学实数理解，所以实现必须得到数学上正确的模结果。

## 梅森旋转引擎（[rand.eng.mers]）

`mersenne_twister_engine<UIntType, w, n, m, r, a, u, d, s, b, t, c, l, f>`

- ¶1：产生 [0, 2ʷ − 1] 内的无符号整数。状态大小为 n，由 n 个值的序列 X 组成，下标对 n 取模。脚注 221 解释名字：参数选得好时，周期与一个大的梅森素数密切相关（`mt19937` 的周期是 2¹⁹⁹³⁷ − 1）。
- ¶2 转移算法（"扭转的广义反馈移位寄存器"）：
    1. 把 Xᵢ₋ₙ 的高 w − r 位与 Xᵢ₊₁₋ₙ 的低 r 位拼成 Y；
    2. α = a·(Y bitand 1)，置 Xᵢ = Xᵢ₊ₘ₋ₙ xor (Y rshift 1) xor α。
- ¶3 生成算法（**回火**，tempering）：对 Xᵢ 依次做四步移位-掩码-异或得到 z₄。回火是可逆的线性变换，作用是改善输出的均匀性——这也意味着从输出可以还原 Xᵢ（见 [[rand]] 的安全警告）。
- ¶4：一组参数关系，例如 `0 < m <= n`、`2u < w`、`r, u, s, t, l <= w`、`w <= numeric_limits<UIntType>::digits`、各掩码 `<= 2ʷ − 1`。
- ¶5：文本表示是 Xᵢ₋ₙ, …, Xᵢ₋₁ 共 n 个数。
- ¶6–¶7：`explicit mersenne_twister_engine(result_type value)`：X₋ₙ = value mod 2ʷ，然后对 i = 1−n … −1 递推 Xᵢ = [f·(Xᵢ₋₁ xor (Xᵢ₋₁ rshift (w−2))) + i mod n] mod 2ʷ。复杂度 O(n)。**整个 19937 位的状态都由这一个 `value` 决定**——这是单整数播种只能得到 2³² 种状态（对 `mt19937`）的根源。
- ¶8：用种子序列播种：k = ⌈w/32⌉，请求 n·k 个 32 位值，每 k 个拼成一个 Xᵢ。最后，若 X₋ₙ 的高 w − r 位为零、且其余 Xᵢ 全为零（全零状态是不动点），把 X₋ₙ 改为 2ʷ − 1。

## 带借位减法引擎（[rand.eng.sub]）

`subtract_with_carry_engine<UIntType, w, s, r>`，即 Marsaglia–Zaman 的 lagged Fibonacci 变体，`ranlux` 系列的基础。

- ¶2：状态是 r 个整数 0 ≤ Xᵢ < m = 2ʷ，加一个**借位**（carry）c ∈ {0, 1}；状态大小为 O(r)。
- ¶3：Y = Xᵢ₋ₛ − Xᵢ₋ᵣ − c；Xᵢ = Y mod m；Y < 0 时 c = 1，否则 c = 0。注释指出这等价于一个模数巨大的乘同余生成器。
- ¶4：GA 返回刚算出的 y。
- ¶5：`0 < s < r`、`0 < w <= digits`。
- ¶7–¶8：`explicit subtract_with_carry_engine(result_type value)`：先构造一个 `linear_congruential_engine<uint_least32_t, 40014u, 0u, 2147483563u>`，种子为 `value == 0 ? default_seed : value % 2147483563u`（`default_seed` 是 19780503），用它的输出拼出 X₋ᵣ … X₋₁；若 X₋₁ 为 0 则 c = 1。
- 注意：默认构造函数委托给 `subtract_with_carry_engine(0u)`，`seed()` 的默认实参也是 `0u`——0 在 ¶7 中被映射为 `default_seed`。而且这里的 `default_seed` 类型是 `uint_least32_t`，不是 `result_type`。
- ¶9：种子序列播种与梅森旋转类似。

## Philox 引擎（[rand.eng.philox]）{{c++26}}

`philox_engine<UIntType, w, n, r, consts...>` 由 [[P2075R6]] 引入，来自 Salmon 等人的"计数器型"随机数生成器（Random123）。与前三种"状态递推"引擎不同，它的输出是**计数器**经过一个 r 轮代换-置换网络的函数：

- ¶1：状态包括：n 个 w 位值组成的计数器 X（解释为一个 n·w 位整数 Z）、n/2 个密钥 K（由种子生成，除非重新播种否则不变）、一批 n 个缓存输出 Y，和下标 i。
- ¶2–¶3：每次调用 i 加 1；i 到达 n 时，Y = Philox(K, X)、Z 加 1、i 归零；返回 Yᵢ。
- ¶4–¶5：一轮 Philox：按表 129 置换 X 得到 V，然后对每一对做 mulhi/mullo 乘法并与轮密钥异或；轮密钥 key_q,k = (Kₖ + q·Cₖ) mod 2ʷ。r 轮之后的结果即 Y。
- ¶6 *Mandates*：`sizeof...(consts) == n`、`n` 为 2 或 4、`0 < r`、`0 < w <= digits`。这里用的是 *Mandates*，与其他引擎"关系不成立即非良构"效果相同。
- ¶7：`consts` 按 [M₀, C₀, M₁, C₁, …] 排列：乘数与轮常数交替。
- ¶8：文本表示是 K、X、i；Y 不写出，读入时可由 K 和 X 重建（注释）。
- ¶9–¶10：播种只设置密钥 K，计数器 X 清零，i = n − 1。
- ¶11 `set_counter(c)`：直接设置计数器（注意 `c` 的元素顺序与 X 相反：Xⱼ = c[n−1−j]）。

计数器型设计带来两个好处：`discard(z)` 可以是 O(1)（只要加计数器）；多个线程或 GPU 线程可以用相同密钥、不同计数器区间得到互不重叠的流，无需传递巨大的状态。本机 libc++ 尚未实现 `philox_engine`。

## 引擎适配器（[rand.adapt]）

### discard_block_engine（[rand.adapt.disc]）

`discard_block_engine<Engine, p, r>`：从基引擎每产生的 p 个值中只用前 r 个，丢掉其余 p − r 个。

- ¶1：状态是基引擎状态加一个计数 n；大小为基引擎状态大小加 1。
- ¶2：若 n ≥ r，先把基引擎推进 p − r 步、n 置 0；然后 n 加 1、基引擎推进一步。
- ¶3：返回最后一次 `e()` 的值。
- ¶4：`0 < r <= p`。¶6：非复制构造函数都把 n 置 0。

这是 Lüscher 的 RANLUX 做法：带借位减法引擎的短程相关性较强，丢掉大部分输出可以换来很好的统计质量（代价是速度）。`ranlux24` = `discard_block_engine<ranlux24_base, 223, 23>`，每 223 个值只用 23 个。

### independent_bits_engine（[rand.adapt.ibits]）

`independent_bits_engine<Engine, w, UIntType>`：把基引擎的输出拼成恰好 w 位的结果。

- ¶1：状态就是基引擎的状态。
- ¶2–¶4：设基引擎值域大小 R = e.max() − e.min() + 1、m = ⌊log₂ R⌋。算法决定调用基引擎 n 次，每次取低 w₀ 或 w₀ + 1 位，并对超出 y₀、y₁ 的值**拒绝重取**，保证每一位都是均匀独立的——即使基引擎的值域不是 2 的幂（例如 `minstd_rand` 的 [1, 2³¹ − 2]）。
- ¶5：`0 < w <= numeric_limits<result_type>::digits`。

一个用法：从 32 位引擎得到均匀的随机字节。因为 `UIntType` 至少要和 `short` 一样宽（[rand.req.genl] ¶1.7），不能写 `independent_bits_engine<mt19937, 8, unsigned char>`，要用更宽的类型装 8 位：

```cpp run title="random-bytes.cpp" ok
#include <algorithm>
#include <random>
#include <vector>

int main() {
  std::independent_bits_engine<std::mt19937, 8, unsigned short> bytes(1);
  static_assert(bytes.min() == 0 && bytes.max() == 255);
  std::vector<unsigned char> buf(16);
  std::ranges::generate(buf, [&] { return static_cast<unsigned char>(bytes()); });
}
```

### shuffle_order_engine（[rand.adapt.shuf]）

`shuffle_order_engine<Engine, k>`：产生与基引擎**相同的值**，但以不同顺序交付（Bays–Durham 洗牌）。

- ¶1：状态是基引擎状态、一个值 Y、一个 k 元表 V；大小为基引擎加 k + 1。
- ¶2：用 Y 计算下标 j = ⌊k·(Y − e_min)/(e_max − e_min + 1)⌋，令 Y = Vⱼ，再用 `e()` 填回 Vⱼ。
- ¶3：返回 Y。¶4：`0 < k`。¶6：非复制构造函数依次用 `e()` 填充 V[0..k−1] 和 Y。

`knuth_b` = `shuffle_order_engine<minstd_rand0, 256>`。

## 预定义别名（[rand.predef]）

每个别名都附有一条 *Required behavior*：默认构造的对象，**第 10000 次**连续调用必须产生给定值。这是最简单的一致性测试——本机 libc++ 下全部通过：

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

```cpp run title="required-behavior.cpp" ok
#include <cassert>
#include <random>

template<class E> auto nth10000() { E e; e.discard(9999); return e(); }

int main() {
  assert(nth10000<std::mt19937>() == 4123659995u);
  assert(nth10000<std::mt19937_64>() == 9981545732273789042u);
  assert(nth10000<std::minstd_rand>() == 399268537u);
  assert(nth10000<std::ranlux24>() == 9901578u);
}
```

注意 `result_type` 是 `uint_fast32_t`，在 64 位 Linux 上通常是 64 位的 `unsigned long`。`mt19937` 的 `w` 仍是 32，所以输出仍在 [0, 2³² − 1] 内，但对象中每个状态字可能占 8 字节。

¶10：`default_random_engine` 的选择**由实现定义**。注释说明实现可以按性能、大小、质量或其组合来选，以便为"相对随意、非专业、轻量"的使用提供至少可以接受的行为；不同实现可以选不同的引擎，所以用它的代码不能期望跨实现产生相同序列。本机 libc++ 中它是 `minstd_rand`——一个周期约 2³¹、统计质量很一般的 LCG。需要质量或可复现性时，应当显式写出引擎类型。

## 选型参考

| 引擎 | 状态大小 | 速度 | 质量 | 备注 |
|---|---|---|---|---|
| `minstd_rand` | 4–8 字节 | 快 | 差 | 低位周期短，值域不是 2 的幂 |
| `mt19937`/`mt19937_64` | ~2.5 KB | 快 | 好（但有已知的线性特征） | 最常用；播种要喂足熵 |
| `ranlux24`/`ranlux48` | 小 | 慢 | 很好 | 物理模拟传统选择 |
| `knuth_b` | ~1 KB | 中 | 一般 | 历史意义为主 |
| `philox4x32`/`philox4x64` | 小 | 快，可并行 | 好 | C++26；`discard` 可 O(1) |

以上质量评价是领域常识的概括，标准本身不对质量作任何规定——它只规定算法。

## 思考题

!!! question "1"
    `std::linear_congruential_engine<std::uint32_t, 5, 3, 4> e;` 良构吗？`<std::uint32_t, 5, 3, 0>` 呢？

<details markdown="1">
<summary>答案</summary>

第一个：`m = 4 != 0`，[rand.eng.lcong] ¶3 要求 `a < m`，而 5 ≥ 4，关系不成立，按 [rand.eng.general] ¶6 非良构。

第二个：`m = 0` 表示模数为 2³²（¶2），¶3 的关系只在 `m != 0` 时要求，良构。
</details>

!!! question "2"
    为什么 `std::mt19937 g(std::seed_seq{1, 2, 3});` 不能编译？

<details markdown="1">
<summary>答案</summary>

种子序列构造函数的形参是 `Sseq&`（非 const 左值引用），不能绑定到临时对象 `std::seed_seq{1, 2, 3}`。`result_type` 构造函数也不可行（`seed_seq` 不能转换为整数）。要先声明一个具名的 `seed_seq` 变量再传入。这样设计是因为 `generate` 是非 const 的，可以依赖调用历史（[rand.req.seedseq]）。
</details>

## 小结

- 引擎由状态、TA、GA 完全规定；参数关系不成立即非良构。
- `X(Sseq&)` 对可转换为 `result_type` 的类型不参与重载决议。
- LCG 播种避开 0 不动点；MT 的单整数播种决定整个状态；MT 的种子序列播种避开全零状态。
- 适配器：丢弃块（RANLUX）、独立比特（拒绝采样拼位）、洗牌（Bays–Durham）。
- 预定义别名有第 10000 个输出的规定行为；`default_random_engine` 由实现定义（libc++ 为 `minstd_rand`）。
- C++26 的 `philox_engine`：计数器型，适合并行；libc++ 尚未实现。
