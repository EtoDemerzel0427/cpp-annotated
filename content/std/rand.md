---
title: 随机数生成
summary: <random> 的总体设计——均匀随机比特生成器、引擎、引擎适配器、分布四类实体如何组合；result_type 的布尔/整数/浮点分类与"用实数计算"的约定；哪些部分跨实现可复现、哪些不可；为什么 mt19937 的默认构造和单个 32 位种子都不够；rand()/srand() 的地位
status: done
covers: rand.general, rand.synopsis, c.math.rand
papers: P2075R6, P1068R11
related: rand.req, rand.eng, rand.device, rand.util, rand.dist, alg.rand, numerics, res.on.data.races
tags: 标准库, 随机数, random, 可复现性
updated: 2026-10-18
---

C++11 的 `<random>` 把"产生随机数"拆成两个正交的问题：

1. **比特从哪来**——一个能反复调用、每次返回一个无符号整数、各值（理想情况下）等概率的对象。这叫**均匀随机比特生成器**（uniform random bit generator，URBG）。确定性的 URBG 叫**引擎**（engine），比如梅森旋转 `mt19937`；非确定性的有 `random_device`。
2. **要什么分布**——把均匀比特变成 [1, 6] 上的均匀整数、正态分布的 `double`、按权重抽样的下标……这叫**分布**（distribution）。

两者通过一个极简接口相连：分布的 `operator()(g)` 接受任意 URBG 的左值引用。这与 C 的 `rand() % 6 + 1` 形成对比——后者把比特来源（未指明的算法、全局状态）和分布变换（取模，带偏差）焊死在一起。

本页讲总体结构与使用上的结论。各部分的精确合同在：[[rand.req]]（四类实体的要求表）、[[rand.eng]]（四种引擎、三种适配器、预定义别名）、[[rand.device]]、[[rand.util]]（`seed_seq`、`generate_canonical`）、[[rand.dist]]（20 种分布）。

## 四类实体（[rand.general] ¶1–¶2）

¶2 列出四类：**均匀随机比特生成器**、**随机数引擎**、**随机数引擎适配器**、**随机数分布**。这些分类既适用于满足相应要求的类型，也适用于这些类型的对象，以及实例化后产生这些类型的模板。

它们是层层包含的关系：

| 类别 | 是什么 | 例子 |
|---|---|---|
| URBG | 函数对象：`g()` 返回无符号整数，有静态 `min()`/`max()` | `random_device`，以及下面所有引擎 |
| 引擎 | 有确定状态、可播种、可比较、可序列化的 URBG | `mt19937`、`minstd_rand`、`philox4x32` |
| 引擎适配器 | 包装另一个"基引擎"的引擎 | `discard_block_engine`、`shuffle_order_engine` |
| 分布 | 函数对象：`d(g)` 用 URBG 产生服从某分布的值 | `uniform_int_distribution`、`normal_distribution` |

¶2 的注释说，这样设计是为了让任何 URBG 对象 `e` 都能绑定到任何分布对象 `d` 上，得到 `bind(d, e)` 这样的零参函数对象。实际代码里更常见的是 lambda：`[&] { return d(e); }`。注意 `bind(d, e)` 会**复制** `e`——每次调用推进的是副本的状态；想共享引擎要写 `bind(d, ref(e))`。

## result_type 的分类与计算约定（¶3–¶5）

¶3：每个实体都有一个关联的算术类型 `result_type`，记为 `T`。按 `T` 把实体刻画为：

- ¶3.1 `T` 是 `bool` → **布尔**（boolean-valued），如 `bernoulli_distribution`；
- ¶3.2 否则若 `numeric_limits<T>::is_integer` → **整数**（integer-valued），并可再按 `is_signed` 分有符号/无符号；
- ¶3.3 否则 → **浮点**（real-valued）。

¶4：除非另有说明，[rand] 中所有计算描述都使用**数学实数**。这是理解后面各种公式的关键：[[rand.eng]] 里引擎的转移算法写作 (a·x + c) mod m，这是精确的数学运算，**不是** C++ 的 `UIntType` 算术——实现必须保证结果和数学公式一致，即使中间值会溢出 `UIntType`。例如 `linear_congruential_engine<uint32_t, 16807, 0, 2147483647>` 的 `a·x` 可能超过 32 位，实现需要用更宽的类型或 Schrage 方法来算。

¶5 定义了位运算记号：`bitand`、`bitor`、`xor` 是通常的按位运算；`rshift` 是高位补零的右移；`lshift_w` 是低位补零、结果对 2^w 取模的左移。

## 概要中的新东西（[rand.synopsis]）

概要按类别列出所有模板与别名。值得注意的几点：

- **C++20 起**：概念 `uniform_random_bit_generator`（定义在 [[rand.req]]）。
- **C++26 新增** {{c++26}}：
    - 计数器型引擎 `philox_engine` 及别名 `philox4x32`、`philox4x64`（[[P2075R6]]）；
    - `ranges::generate_random`（[[P1068R11]]）：用引擎或"引擎 + 分布"批量填充一个范围，允许引擎/分布提供更快的批量成员 `generate_random`（规范正文在算法章 [[alg.rand]]）。
- **freestanding 标注**：概念 `uniform_random_bit_generator` 标为 freestanding；`linear_congruential_engine`、`subtract_with_carry_engine`、`philox_engine`、`discard_block_engine`、`independent_bits_engine`、`uniform_int_distribution` 标为"部分 freestanding"（流插入/提取除外）；`minstd_rand`、`mt19937`、`ranlux24`、`philox4x32` 等预定义别名标为 freestanding。`shuffle_order_engine`、`knuth_b`、`default_random_engine`、`random_device`、`seed_seq`、`generate_canonical` 与其余分布没有标注。

!!! lawyer "一个标注上的不一致"
    概要中 `mersenne_twister_engine` 类模板本身**没有** freestanding 标注，而别名 `mt19937`、`mt19937_64` 却标为 freestanding。别名只是给模板特化起名字，独立实现要提供 `mt19937` 就必须提供那个特化——这看起来是标注上的疏漏，而不是有意的区分。

本机 libc++ 尚未提供 `philox_engine` 和 `ranges::generate_random`。

## 可复现性：什么能跨实现复现

这是 `<random>` 使用中最常见的误解来源，标准的态度非常明确：

| 组件 | 跨实现是否可复现 | 依据 |
|---|---|---|
| 引擎（`mt19937` 等） | **是**：转移算法与生成算法逐位规定，并有第 10000 个输出的 *Required behavior* | [[rand.eng]]、[rand.predef] |
| 引擎的流式表示 | 是：文本表示的内容有规定 | [[rand.req]] |
| `seed_seq::generate` | 是：算法逐步规定 | [[rand.util]] |
| `default_random_engine` | **否**：选择由实现定义 | [rand.predef] ¶10 |
| 所有分布 | **否**：产生分布的算法由实现定义 | [rand.dist.general] ¶3 |
| `random_device` | 否：非确定性（且来源由实现定义） | [[rand.device]] |
| `generate_canonical` | 是（按当前草案的新规格）；但实现不一定已跟进 | [[rand.util]] |

所以"同一个种子在 Linux 和 Windows 上跑出不同的骰子点数"不是 bug：`std::uniform_int_distribution<int>(1, 6)(g)` 在 libc++、libstdc++、MSVC STL 上用的拒绝采样算法不同，消耗引擎输出的方式也不同。需要跨平台复现（游戏回放、科学计算的可重复实验、测试用例）时，只能直接使用引擎的原始输出，自己写（或使用固定的第三方）分布变换。

## 播种：mt19937 的两个常见错误

### 默认构造：每次都一样

`std::mt19937 g;` 用 `default_seed`（5489）播种。程序每次运行产生完全相同的序列——对测试是优点，对"随机"是缺点。

### 单个 32 位种子：状态空间被压缩

`std::mt19937 g(std::random_device{}());` 看起来随机了，但：

- `mt19937` 的状态是 624 个 32 位字，约 19937 位；
- `explicit mersenne_twister_engine(result_type value)` 只接受一个 `result_type` 值（[rand.eng.mers] ¶6），用一个固定的递推把它展开成整个状态；
- 所以这样构造出的引擎**最多只有 2³² 种**不同的初始状态。

后果是可预见的：如果你用这种方式给 10 万个对象各自播种，按生日问题，出现两个对象序列完全相同的概率已经接近 69%（约为 1 − e^(−n²/2³³)）。更糟的是，任何人只要枚举 2³² 个种子就能找到你的初始状态。

正确做法是用**种子序列**（seed sequence，[[g:seed-sequence]]）提供足够多的熵：

```cpp run title="seed-mt19937.cpp" ok
#include <algorithm>
#include <array>
#include <functional>
#include <random>

std::mt19937 make_engine() {
  std::random_device rd;
  std::array<std::uint32_t, std::mt19937::state_size> data;
  std::ranges::generate(data, std::ref(rd));      // 624 个 32 位熵
  std::seed_seq seq(data.begin(), data.end());
  return std::mt19937(seq);                        // 调用 template<class Sseq> explicit X(Sseq&)
}

int main() {
  auto g = make_engine();
  std::uniform_int_distribution<int> die(1, 6);
  return die(g) >= 1 ? 0 : 1;
}
```

两点保留意见：

- `seed_seq` 的混合算法（[[rand.util]]）是固定的；标准没有要求它是单射，有分析指出对 `mt19937` 这种规模的输出它并不能到达全部状态。对绝大多数用途这无关紧要，但它说明 `seed_seq` 只是"足够好"的搅拌器，不是密码学构件。
- `random_device` 本身在某些实现上可能是确定性的（[rand.device] ¶2 允许"在实现受限时使用随机数引擎"），可以用 `entropy()` 粗略判断，但它的返回值也是实现定义的。

!!! warning "梅森旋转不是密码学安全的"
    `mt19937` 的生成算法是可逆的线性变换。观察到 624 个连续输出，就能恢复完整状态并预测此后所有输出。生成令牌、密钥、会话 ID 时不要用 `<random>` 的任何引擎；标准库目前没有提供密码学安全的生成器。

## rand 与 srand（[c.math.rand]）

¶1 注释：这两个函数由 `<cstdlib>` 声明。

¶2：`rand` 与 `srand` 的语义按 C 标准库规定——`srand(seed)` 设定伪随机序列的起点，未调用 `srand` 时如同 `srand(1)`；`rand()` 返回 [0, `RAND_MAX`] 内的伪随机整数，`RAND_MAX` 至少为 32767。

¶3：

- 实现可以规定某些库函数会调用 `rand`（于是你的序列可能被它们"偷走"几个值）；
- `rand` 是否会引入**数据竞争**由实现定义（[[res.on.data.races]]）——它通常有全局状态，多线程同时调用可能是 UB；
- 注释直白地说：[rand] 的其他设施通常更好，因为 `rand` 的底层算法未指明，使用它"依然不可移植，质量与性能不可预测且常常可疑"。

```cpp title="rand-modulo.cpp" ok
#include <cstdlib>

int roll_bad() { return std::rand() % 6 + 1; }   // 当 RAND_MAX + 1 不是 6 的倍数时有偏差
```

`RAND_MAX` 是 32767 时，`rand() % 6` 中 0 和 1 出现的次数比其他值各多一次（32768 = 6 × 5461 + 2）。偏差很小，但这是分布层面的错误；`uniform_int_distribution` 的规范要求每个值的概率严格是 1/(b−a+1)（[[rand.dist]]），实现必须用拒绝采样等手段消除这种偏差。

## 线程安全

`<random>` 没有为引擎或分布提供内部同步。按库的一般规则（[[res.on.data.races]]），两个线程同时调用同一个引擎的 `operator()`（非 `const` 成员）是数据竞争。惯用法是每个线程一个引擎：

```cpp title="thread-local-engine.cpp" ok
#include <random>

std::mt19937_64& local_engine() {
  thread_local std::mt19937_64 g{std::random_device{}()};   // 为简洁起见只用 32 位种子
  return g;
}
```

## 思考题

!!! question "1"
    `std::mt19937 a(1), b(1); std::normal_distribution<double> d; double x = d(a), y = d(b);` 中 `x == y` 一定成立吗？换到另一个标准库实现上，`x` 的值会变吗？

<details markdown="1">
<summary>答案</summary>

不一定。两个引擎的初始状态相等（[[rand.req]] 的 `==` 语义），但分布 `d` 是**同一个对象**。`normal_distribution` 常用 Box–Muller 或极坐标法，一次生成两个值并缓存一个；`d(a)` 之后 `d` 内部可能缓存了一个值，`d(b)` 直接返回缓存值而不消耗 `b`。[rand.req.dist] 的表允许分布有"附加内部数据"（流插入要写出它们）。本机 libc++ 正是如此：上面的代码得到 `x = -1.40287`、`y = -0.549746`，而且调用之后 `a != b`（`b` 一个值都没被消耗）。若要让 `x == y`，应使用两个分布对象，或在中间调用 `d.reset()`（[rand.req.dist] 表 128：`reset` 之后的使用不依赖之前引擎产生的值）。

换实现时 `x` 一般会变：[rand.dist.general] ¶3 规定分布的算法由实现定义。
</details>

## 小结

- URBG → 引擎/适配器 → 分布，接口只是 `g()` 与 `d(g)`。
- [rand] 中的公式按数学实数理解，实现负责避免溢出。
- 引擎跨实现可复现；分布、`default_random_engine`、`random_device` 不可复现。
- 单个 32 位种子只给 2³² 种初始状态；用 `seed_seq` 喂足熵。
- `rand()` 算法未指明、可能有数据竞争、取模有偏差；梅森旋转不是密码学安全的。
- C++26：`philox_engine`、`ranges::generate_random`。
