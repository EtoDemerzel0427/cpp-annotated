---
title: seed_seq 与 generate_canonical
summary: 标准种子序列 seed_seq 怎样处理输入（每个值按 2³² 取模）和产生种子；generate_canonical 怎样把整数变成 [0, 1) 内的浮点数，以及新规格修正的返回 1.0 的问题。
status: done
covers: *
papers: P0952R2
related: rand, rand.req, rand.eng, rand.dist, rand.device
tags: 标准库, 随机数, seed_seq, generate_canonical
updated: 2026-10-19
---

!!! tldr
    - `seed_seq` 把每个输入值按 2³² 取模后保存，64 位种子的高 32 位会被直接丢弃。
    - `seed_seq::generate` 的混合算法逐步规定，跨实现可复现，而且只依赖构造时的输入。
    - `seed_seq` 不能复制，接受它的引擎构造函数要求非 const 左值。
    - `generate_canonical` 现行规格先用拒绝采样得到一个均匀整数，再除以 2 的幂，结果严格小于 1。
    - 旧规格在浮点里做除法，可能舍入成 1.0；本机 libc++ 仍是旧算法。

## seed_seq（[rand.util.seedseq]）

`seed_seq` 是标准提供的**种子序列**（[[g:seed-sequence]]）：它保存一串整数，需要时把它们搅拌成任意多个 32 位值，用来初始化引擎的状态（[[rand.req]]）。用法见 [[rand]] 的播种一节。

### 输入按 2³² 取模（¶1–¶6）

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
  assert(pa == pb);              // 都是 {1}
  std::mt19937 g1(a), g2(b);
  assert(g1 == g2);              // 引擎状态也相同
}
```

概要中 `seed_seq` 只有一个仅用于说明的数据成员 `vector<result_type> v`，`result_type` 是 `uint_least32_t`。¶1 默认构造后 `v` 为空。¶6 迭代器构造函数对每个输入元素执行 `v.push_back((*s) mod 2³²)`，所以上例中 `0x1'0000'0001` 只留下了 1。要使用 64 位种子，应自己拆成两个 32 位值传入。

两个构造函数对元素类型的检查方式不同。¶2 `initializer_list<T>` 版本用 *Constraints* 要求 `T` 是整数类型，¶4 迭代器版本用 *Mandates* 要求值类型是整数类型。*Constraints* 不满足时，该重载退出重载决议；*Mandates* 不满足时，选中该重载后程序非良构。

<div class="compare" markdown="1">

```cpp error
#include <random>
// 没有可行的构造函数：
// initializer_list<double> 不满足约束
std::seed_seq s{1.5};
```

```cpp error
#include <random>
#include <vector>
std::vector<double> d{1.5};
// 选中迭代器版本，再违反 Mandates
std::seed_seq s(d.begin(), d.end());
```

</div>

两者都是编译错误。区别在于前者能被 `std::is_constructible` 之类的检测静默探知，后者不能：`is_constructible_v<seed_seq, double*, double*>` 为真。

### generate 的算法（¶7–¶9）

¶9 逐步规定了 `generate(begin, end)` 的算法。记 s = `v.size()`、n = `end - begin`，所有运算模 2³²：

1. 把输出范围全部置为 `0x8b8b8b8b`，按 n 的大小选定两个偏移 p、q；
2. 第一轮混合，把 `v` 的元素逐个注入，共 max(s + 1, n) 步；
3. 第二轮混合，再做 n 步。

这个算法与梅森旋转作者给出的 `init_by_array` 初始化程序同源。它只读 `v`，不依赖之前的调用，所以同一个 `seed_seq` 多次调用 `generate` 得到相同的结果。种子序列的一般要求允许依赖调用历史（[[rand.req]]），通用代码不应依赖这一点。

¶7 要求目标迭代器的值类型是能容纳 32 位的无符号整数类型。

!!! note "seed_seq 的局限"
    `generate` 是一个固定的确定性函数，把 s 个 32 位输入映射为 n 个 32 位输出。n 很大时（`mt19937` 需要 624 个），标准没有要求这个映射是单射，有分析指出在某些尺寸下它确实不是：不同的输入可能得到相同的引擎状态，某些状态永远无法到达。对模拟、游戏之类的用途这无关紧要，但 `seed_seq` 的作用只是把少量熵均匀铺开，不是高质量的哈希。

### 保存与重建（¶11–¶15）

`size()` 返回 `param()` 会写出的 32 位单元个数，即 `v.size()`。`param(dest)` 如同 `copy(v.begin(), v.end(), dest)`。用写出的序列构造新的 `seed_seq`，就得到一个等价的对象，上面的例子就用 `param` 比较了两个种子序列。

`seed_seq` 的复制构造和复制赋值被删除。

## generate_canonical（[rand.util.canonical]）

```cpp
template<class RealType, size_t digits, class URBG>
  RealType generate_canonical(URBG& g);
```

它从 `g` 取足够多的比特，产生一个在 [0, 1) 内尽可能均匀的 `RealType` 值。`uniform_real_distribution` 等浮点分布通常以它为基础。当前规格来自 [[P0952R2]]，与 C++11 的原始规格不同。

### 现行规格（¶1–¶5）

¶1 先定义几个量：

- r = `numeric_limits<RealType>::radix`，通常是 2；
- R = `g.max() - g.min() + 1`，URBG 值域的大小；
- d = min(`digits`, `numeric_limits<RealType>::digits`)。脚注 224 说明这是为了不产生 `RealType` 装不下的随机位；
- k 是使 Rᵏ ≥ rᵈ 的最小整数；
- x = ⌊Rᵏ / rᵈ⌋。

一次**尝试**（attempt）是调用 k 次 `g()` 得到 g₀, …, gₖ₋₁，并计算 S = Σ (gᵢ − g.min())·Rⁱ。

¶2 反复尝试，直到 S < x·rᵈ。注释指出 R 是 r 的幂时恰好只需一次尝试。¶3 返回 ⌊S / x⌋ / rᵈ，注释说明结果 c 满足 0 ≤ c < 1。¶5 每次尝试恰好调用 k 次 `g`。

直观地说，S 是 [0, Rᵏ) 内的均匀整数。只接受落在 [0, x·rᵈ) 内的 S，再整除 x，就得到 [0, rᵈ) 内的均匀整数。最后除以 rᵈ 对二进制浮点是精确的，只改变指数。所以结果是 rᵈ 个等距值之一，每个概率完全相同，最大也只到 1 − r⁻ᵈ。

### 旧规格为什么会返回 1.0

C++11 的规格在 `RealType` 里计算 S，然后返回 S / Rᵏ。像 Rᵏ − 1 这样的整数在 `float` 中不能精确表示，会被舍入成 Rᵏ，于是 S 接近最大值时 S / Rᵏ 舍入为 1.0。这违反了旧规格自己在注释中给出的 [0, 1) 承诺。问题由 [[LWG2524]] 报告。

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
  std::printf("%.9g\n", c);   // libc++ 输出 1；现行规格要求 0.99999994
}
```

按现行规格手算：r = 2，R = 2³²，d = min(32, 24) = 24，k = 1，x = ⌊2³² / 2²⁴⌋ = 256。S = 2³² − 1 < 256·2²⁴，一次尝试就被接受；返回 ⌊(2³² − 1)/256⌋ / 2²⁴ = (2²⁴ − 1)/2²⁴ ≈ 0.99999994，小于 1。

真实的 `mt19937` 输出最大值的概率只有 2⁻³²，但大规模模拟调用几十亿次很常见，而 `log(1 - u)` 这类下游代码恰好在 u = 1 时出错。这也是 `uniform_real_distribution(a, b)` 偶尔返回 b 的原因之一（[[rand.dist]]）。

<details class="fine" markdown="1"><summary>其余条文</summary>

[rand.util.seedseq]：¶5 迭代器构造函数要求输入迭代器；¶8 `generate` 要求可变的随机访问迭代器；¶10、¶16 只在迭代器操作抛异常时抛出；¶12 `size()` 是常数时间；¶13–¶14 `param` 要求 `result_type` 的值可写入 `dest`，`dest` 是输出迭代器。

[rand.util.canonical]：¶4 抛出 `g` 抛出的异常。¶6 注释说明：`g` 均匀时结果尽可能均匀，这是把 URBG 的输出变换成分布结果的有用一步。¶7 注释说明：R 是 r 的幂时，实现计算 S 不必使用比输出更宽的算术类型。

</details>
