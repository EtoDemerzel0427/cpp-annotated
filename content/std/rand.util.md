---
title: seed_seq 与 generate_canonical
summary: 标准种子序列 seed_seq 的合同——输入按 2³² 取模（64 位种子被截断）、逐步规定的 generate 混合算法、param/size、不可复制；generate_canonical 的新规格：按"尝试"拒绝采样、结果严格小于 1，与 libc++ 仍在使用、可能返回 1.0 的旧算法对比
status: done
covers: *
papers: P0952R2
related: rand, rand.req, rand.eng, rand.dist, rand.device
tags: 标准库, 随机数, seed_seq, generate_canonical
updated: 2026-10-18
---

[rand.util] 有两个工具：把任意长度的整数种子"搅拌"成引擎所需初始状态的 `seed_seq`，以及把 URBG 的整数输出变成 [0, 1) 浮点数的 `generate_canonical`。后者是所有浮点分布的基础构件；它在当前草案中的规格与 C++11 原版不同，修正了一个让分布偶尔返回区间右端点的老问题。

## seed_seq（[rand.util.seedseq]）

`seed_seq` 满足种子序列要求（[[rand.req]]，[[g:seed-sequence]]）。概要中：`result_type` 是 `uint_least32_t`；唯一的数据成员是仅用于说明的 `vector<result_type> v`；复制构造与复制赋值被删除。

### 构造（¶1–¶6）

- ¶1：默认构造后 `v` 为空。
- ¶2–¶3：`template<class T> seed_seq(initializer_list<T> il)`，*Constraints*：`T` 是整数类型；效果同迭代器版本。
- ¶4–¶6：`template<class InputIterator> seed_seq(InputIterator begin, InputIterator end)`，*Mandates*：值类型是整数类型；*Preconditions*：满足 *Cpp17InputIterator*。效果是对每个元素执行 `v.push_back((*s) mod 2³²)`。

两个注意点。

**其一，输入按 2³² 取模**。给 `seed_seq` 一个 64 位整数，高 32 位被直接丢弃。下面两个种子序列的状态完全相同：

```cpp run title="seed-seq-truncate.cpp" ok
#include <cassert>
#include <cstdint>
#include <iterator>
#include <random>
#include <vector>

int main() {
  std::seed_seq a{std::uint64_t{0x1'0000'0001}}, b{1u};
  std::vector<std::uint32_t> pa, pb;
  a.param(std::back_inserter(pa));
  b.param(std::back_inserter(pb));
  assert(pa == pb);                       // 都是 {1}
  std::mt19937 g1(a), g2(b);
  assert(g1 == g2);                       // 引擎也一样
}
```

要用 64 位种子，应自己拆成两个 32 位值传入。

**其二，`initializer_list` 构造函数用 *Constraints*，迭代器构造函数用 *Mandates***。所以 `seed_seq s{1.5};` 是"没有可行的构造函数"（`T = double` 不满足约束，迭代器版本也推导不出），而 `std::vector<double> d; seed_seq s(d.begin(), d.end());` 是选中了迭代器版本后在 *Mandates* 处被拒绝——两种都是编译错误，但前者可以被 `is_constructible` 之类的检测静默探知，后者不行。

### generate（¶7–¶10）

¶7 *Mandates*：目标迭代器的值类型是能容纳 32 位量的无符号整数类型。¶8：随机访问、可变迭代器。

¶9 逐步规定了算法（所有运算模 2³²，`begin` 的下标模 n，T(x) = x xor (x rshift 27)）：

1. 把输出范围全部置为 `0x8b8b8b8b`；按 n 的大小选 t（n ≥ 623 时为 11，依次递减），令 p = (n − t)/2、q = p + t；
2. 对 k = 0 … m−1（m = max(s+1, n)，s = `v.size()`）做第一轮混合，把 `v` 的元素逐个注入；
3. 对 k = m … m+n−1 做第二轮混合。

这个算法与 Mersenne Twister 作者给出的 `init_by_array` 初始化程序同源。由于它**只读 `v`**，不依赖之前的 `generate` 调用，标准的 `seed_seq` 对同一个对象多次调用 `generate` 得到相同结果——但种子序列的一般要求允许依赖历史，通用代码不应依赖这一点。

¶10：只在迭代器操作抛异常时抛出。

!!! note "seed_seq 的局限"
    `generate` 是一个固定的、确定性的混合函数。它把 s 个 32 位输入映射为 n 个 32 位输出；当 n 很大（如 `mt19937` 的 624）时，标准没有要求这个映射是单射，有分析指出它在某些尺寸下确实不是——不同的输入可能得到相同的引擎状态，某些状态永远无法到达。对模拟、游戏等用途这无关紧要；但它说明 `seed_seq` 是"把少量熵均匀铺开"的工具，而不是一个高质量的哈希。

### size 与 param（¶11–¶16）

`size()` 返回 `param()` 会写出的 32 位单元个数（即 `v.size()`），常数时间；`param(dest)` 如同 `copy(v.begin(), v.end(), dest)`。它们让种子序列可以被保存和重建：用 `param` 写出的序列构造新 `seed_seq`，得到等价的对象。

## generate_canonical（[rand.util.canonical]）

```cpp
template<class RealType, size_t digits, class URBG>
  RealType generate_canonical(URBG& g);
```

它从 `g` 取足够多的比特，产生一个在 [0, 1) 内尽可能均匀的 `RealType` 值。`uniform_real_distribution` 等浮点分布通常以它为基础。

### 当前规格（¶1–¶7）

¶1 定义：

- r = `numeric_limits<RealType>::radix`（通常是 2）；
- R = g.max() − g.min() + 1（URBG 值域大小）；
- d = min(`digits`, `numeric_limits<RealType>::digits`)——脚注 224：避免产生 `RealType` 装不下的随机位；
- k 为使 Rᵏ ≥ rᵈ 的最小整数；
- x = ⌊Rᵏ / rᵈ⌋。

一次**尝试**（attempt）是调用 k 次 `g()` 得到 g₀ … gₖ₋₁，并计算 S = Σ (gᵢ − g.min())·Rⁱ。

¶2 *Effects*：反复尝试，直到 S < x·rᵈ。注释：R 是 r 的幂时恰好只需一次尝试。

¶3 *Returns*：⌊S / x⌋ / rᵈ。注释：返回值 c 满足 0 ≤ c < 1。

¶4–¶5：抛出 `g` 所抛的异常；每次尝试恰好调用 k 次 `g`。¶6–¶7 注释：若 `g` 均匀，结果尽可能均匀；R 是 r 的幂时，实现可以不用比输出更宽的算术类型来计算 S。

直观理解：S 是一个 [0, Rᵏ) 内的均匀整数；只接受落在 [0, x·rᵈ) 内的 S（拒绝采样），再整除 x 得到 [0, rᵈ) 内的**均匀整数**，最后除以 rᵈ——这一步对二进制浮点是**精确**的（只改指数），所以结果严格小于 1，且是 rᵈ 个等距值之一，每个概率完全相同。

### 旧规格的问题

C++11 的规格是：取 b = min(digits, 尾数位数)，k = max(1, ⌈b / log₂R⌉)，**在浮点类型中**计算 S，返回 S / Rᵏ。S 和 Rᵏ 都要先转换成 `RealType`，而 Rᵏ − 1 这样的数在 `float` 中不可精确表示、会被舍入成 Rᵏ，于是当 S 接近最大值时 S / Rᵏ 舍入为 **1.0**——违反旧规格自己在注释中给出的 [0, 1) 承诺。这个问题由 [[LWG2524]] 报告，新的规格来自 [[P0952R2]]。

本机 libc++ 仍是旧算法。用一个总是返回最大值的 URBG 就能触发：

```cpp run title="canonical-one.cpp" impl
#include <cstdint>
#include <cstdio>
#include <random>

struct MaxGen {
  using result_type = std::uint32_t;
  static constexpr result_type min() { return 0; }
  static constexpr result_type max() { return UINT32_MAX; }
  result_type operator()() { return max(); }
};

int main() {
  MaxGen g;
  float c = std::generate_canonical<float, 32>(g);
  std::printf("%.9g\n", c);   // 新规格：1 − 2⁻²⁴ ≈ 0.99999994；libc++ 实测输出 1
}
```

按新规格手算：r = 2，R = 2³²，d = min(32, 24) = 24，k = 1，x = ⌊2³² / 2²⁴⌋ = 256。S = 2³² − 1 < 256·2²⁴ = 2³²，一次尝试即接受；返回 ⌊(2³² − 1)/256⌋ / 2²⁴ = (2²⁴ − 1)/2²⁴，在 `float` 中可精确表示，小于 1。

真实的 `mt19937` 输出最大值的概率是 2⁻³²，看起来可以忽略；但在大规模模拟里调用几十亿次是常态，而下游代码（`log(1 − u)`、把 u 当数组下标比例等）恰恰可能在 u = 1 时出错。这也是 `uniform_real_distribution(a, b)` 偶尔返回 b 的根源之一。

## 小结

| 规则 | 出处 | 要点 |
|---|---|---|
| `seed_seq` 输入 | ¶6 | 每个元素对 2³² 取模，64 位种子被截断 |
| 构造约束 | ¶2、¶4 | `initializer_list<T>`：*Constraints*；迭代器：*Mandates* |
| `generate` | ¶9 | 逐步规定，可跨实现复现；只依赖 `v` |
| 复制 | 概要 | 删除 |
| `generate_canonical` | ¶1–¶3 | 按尝试拒绝采样，结果严格在 [0, 1) |
| 旧规格 | [[LWG2524]] | 浮点舍入可能得到 1.0；libc++ 仍如此 |
