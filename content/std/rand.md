---
title: 随机数生成
summary: <random> 把随机数拆成比特来源（引擎）和分布变换两半；哪些部分跨实现可复现，怎样正确播种，以及 rand()/srand() 的地位。
status: done
covers: rand.general, rand.synopsis, c.math.rand
papers: P2075R6, P1068R11
related: rand.req, rand.eng, rand.device, rand.util, rand.dist, alg.rand, numerics, res.on.data.races
tags: 标准库, 随机数, random, 可复现性
updated: 2026-10-19
---

!!! tldr
    - `<random>` 把随机数分成两步：引擎产生均匀的无符号整数，分布把它们变换成需要的形式。两者通过 `d(g)` 组合。
    - 引擎的算法逐位规定，同一种子在任何实现上产生相同序列；分布的算法由实现定义，换一个标准库结果就可能不同。
    - `std::mt19937 g(seed)` 只用一个 32 位整数播种，最多只有 2³² 种初始状态。需要更多熵时用 `seed_seq`。
    - `<random>` 中的公式按数学实数计算，实现负责避免中间结果溢出。
    - `rand()` 的算法未指明、可能有数据竞争，`rand() % n` 还有偏差；`<random>` 的引擎也都不是密码学安全的。

## 从 rand() % 6 说起

```cpp run title="dice.cpp" ok
#include <cstdlib>
#include <random>

int roll_c() { return std::rand() % 6 + 1; }    // 有偏差

int roll_cpp(std::mt19937& g) {
  std::uniform_int_distribution<int> die(1, 6);
  return die(g);                                // 每个点数概率严格为 1/6
}

int main() {
  std::mt19937 g(2024);
  return roll_c() + roll_cpp(g) > 0 ? 0 : 1;
}
```

C 的写法把两件事焊在了一起：比特从哪里来（`rand` 用什么算法、状态放在哪里，都没有规定），以及怎样把比特变成 1 到 6 的点数（取模，有偏差，见下文）。

`<random>` 把这两件事拆开。产生比特的一方叫**均匀随机比特生成器**（uniform random bit generator，URBG）：一个可以反复调用的对象，每次返回一个无符号整数，取值范围内每个值的概率（理想情况下）相等。其中状态确定、可以播种的叫**随机数引擎**（random number engine），例如梅森旋转引擎 `mt19937`。负责变换的一方叫**随机数分布**（random number distribution），例如 `uniform_int_distribution`。

两者之间的接口只有一个：分布的 `operator()` 接受任意 URBG 的左值引用。所以任何引擎都能和任何分布搭配，用户自己写的引擎或分布也一样。

## 四类实体（[rand.general] ¶2）

¶2 标准把 `<random>` 的组件分成四类。这些分类名既指满足相应要求的类型，也指这些类型的对象，以及实例化后得到这些类型的模板。

| 类别 | 是什么 | 例子 |
|---|---|---|
| URBG | 函数对象：`g()` 返回无符号整数，有静态的 `min()`/`max()` | `random_device`，以及下面所有引擎 |
| 引擎 | 状态确定、可以播种、比较、序列化的 URBG | `mt19937`、`minstd_rand`、`philox4x32` |
| 引擎适配器 | 包装另一个引擎（基引擎）的引擎 | `discard_block_engine`、`shuffle_order_engine` |
| 分布 | 函数对象：`d(g)` 用 URBG 产生服从某个分布的值 | `uniform_int_distribution`、`normal_distribution` |

每一类的精确要求在 [[rand.req]]，具体的引擎和适配器在 [[rand.eng]]，分布在 [[rand.dist]]。

¶2 的注释说，这样设计的目的是任何 URBG 对象 `e` 都能绑定到任何分布对象 `d`，得到 `bind(d, e)` 这样的零参函数对象。今天更常写成 lambda `[&] { return d(e); }`。用 `bind` 时要注意它会复制 `e`，每次调用推进的是副本；想共享原引擎要写 `bind(d, ref(e))`。

## result_type 与计算约定（¶3–¶5）

¶3 每个实体都有一个关联的算术类型 `result_type`，记为 `T`。按 `T` 可以把实体分成三种：

- ¶3.1 `T` 是 `bool`：**布尔值**（boolean-valued）实体，例如 `bernoulli_distribution`；
- ¶3.2 否则，`numeric_limits<T>::is_integer` 为真：**整数值**（integer-valued）实体，还可以按 `is_signed` 再分为有符号和无符号；
- ¶3.3 其余情况：**实数值**（real-valued）实体，例如 `normal_distribution<double>`。

¶4 除非另有说明，[rand] 中所有计算都按数学上的实数进行。后面引擎的转移算法写成 (a·x + c) mod m，这是精确的数学运算，不是 `UIntType` 上的 C++ 算术。例如 `minstd_rand0` 是 `linear_congruential_engine<uint_fast32_t, 16807, 0, 2147483647>`，a·x 可能超过 32 位，实现必须用更宽的类型或 Schrage 方法算出正确的模结果。

¶5 规定了位运算的记号：`bitand`、`bitor`、`xor` 是通常的按位运算；`rshift` 是高位补零的右移；`lshift`<sub>w</sub> 是低位补零、结果对 2ʷ 取模的左移。

## 哪些结果能跨实现复现

同一个种子在 Linux 和 Windows 上掷出不同的骰子点数，这不是缺陷。标准对各部分的规定程度不同：

| 组件 | 跨实现可复现 | 依据 |
|---|---|---|
| 引擎（`mt19937` 等） | 是。算法逐位规定，还给出了第 10000 个输出的规定值 | [[rand.eng]] |
| 引擎的文本表示 | 是 | [[rand.req]] |
| `seed_seq::generate` | 是。算法逐步规定 | [[rand.util]] |
| `generate_canonical` | 按当前规格是，但实现不一定已经跟进 | [[rand.util]] |
| `default_random_engine` | 否。选哪个引擎由实现定义 | [[rand.eng]] |
| 所有分布 | 否。算法由实现定义 | [[rand.dist]] |
| `random_device` | 否。它是非确定性的 | [[rand.device]] |

`uniform_int_distribution<int>(1, 6)(g)` 在 libc++、libstdc++、MSVC STL 上使用不同的拒绝采样算法，消耗引擎输出的方式也不同。游戏回放、可重复的科学实验、测试用例这类需要跨平台复现的场合，只能直接使用引擎的原始输出，再自己写分布变换（或者使用固定的第三方实现）。

## 播种 mt19937

### 默认构造每次都一样

`std::mt19937 g;` 用固定的默认种子 5489 播种。程序每次运行都产生完全相同的序列，这对测试有用，但不是随机。

### 一个 32 位种子不够

`std::mt19937 g(std::random_device{}());` 看起来随机了，但 `mt19937` 的状态是 624 个 32 位字，约 19937 位，而这个构造函数只接受一个 `result_type` 值，再用固定的递推把它展开成整个状态（[[rand.eng]]）。所以这样构造出的引擎最多只有 2³² 种初始状态。

后果可以估算出来。如果用这种方式给 10 万个对象各自播种，按生日问题，至少有两个对象序列完全相同的概率约为 1 − e^(−n²/2³³)，接近 69%。而且任何人枚举 2³² 个种子就能找出你的初始状态。

要提供更多的熵，用**种子序列**（seed sequence，[[g:seed-sequence]]）：一个接收一串整数、再按需要产生任意多个 32 位值的对象。标准提供的种子序列是 `seed_seq`。

```cpp run title="seed-mt19937.cpp" ok
#include <algorithm>
#include <array>
#include <functional>
#include <random>

std::mt19937 make_engine() {
  std::random_device rd;
  std::array<std::uint32_t, std::mt19937::state_size> data;
  std::ranges::generate(data, std::ref(rd));   // 624 个 32 位值
  std::seed_seq seq(data.begin(), data.end());
  return std::mt19937(seq);                     // 用种子序列构造
}

int main() {
  auto g = make_engine();
  std::uniform_int_distribution<int> die(1, 6);
  return die(g) >= 1 ? 0 : 1;
}
```

这种做法仍有两点局限。`seed_seq` 的混合算法是固定的，标准没有要求它是单射，有分析指出对 `mt19937` 这种规模的输出它到达不了全部状态（[[rand.util]]）。另外，`random_device` 在某些实现上可以是确定性的（[[rand.device]]）。对绝大多数用途这些都无关紧要。

!!! warning "梅森旋转不是密码学安全的"
    `mt19937` 的输出是状态的可逆线性变换。观察到 624 个连续输出，就能恢复完整状态并预测之后的所有输出。生成令牌、密钥、会话 ID 时不要使用 `<random>` 的任何引擎；标准库目前没有密码学安全的生成器。

## 线程安全

引擎和分布都没有内部同步。按库的一般规则（[[res.on.data.races]]），两个线程同时调用同一个引擎的 `operator()` 是数据竞争。常见的做法是每个线程一个引擎：

```cpp run title="thread-local-engine.cpp" ok
#include <random>

std::mt19937_64& local_engine() {
  // 为简洁起见只用了一个 32 位种子
  thread_local std::mt19937_64 g{std::random_device{}()};
  return g;
}

int main() { (void)local_engine()(); }
```

## rand 与 srand（[c.math.rand]）

¶2 这两个函数在 `<cstdlib>` 中声明，语义与 C 标准库相同：`srand(seed)` 设定伪随机序列的起点，没有调用 `srand` 时如同调用了 `srand(1)`；`rand()` 返回 0 到 `RAND_MAX` 之间的整数，`RAND_MAX` 至少是 32767。

¶3 标准对它们的保证很少：

- 实现可以规定某些库函数会调用 `rand`，于是你的序列可能被它们消耗掉几个值；
- `rand` 会不会引入数据竞争由实现定义（[[res.on.data.races]]）。它通常有全局状态，多线程同时调用可能是 UB；
- 注释直接建议使用 [rand] 的其他设施，因为 `rand` 的算法未指明，质量和性能都无法预测。

`rand() % 6` 的偏差可以算出来。`RAND_MAX` 为 32767 时共有 32768 = 6 × 5461 + 2 个可能值，所以余数 0 和 1 各比其他余数多出现一次。偏差很小，但分布是错的。`uniform_int_distribution` 要求每个值的概率严格等于 1/(b − a + 1)（[[rand.dist]]），实现必须用拒绝采样之类的办法消除这种偏差。

## C++26 新增的组件 {{c++26}}

- 计数器型引擎 `philox_engine` 和别名 `philox4x32`、`philox4x64`（[[P2075R6]]，见 [[rand.eng]]）。
- `ranges::generate_random`（[[P1068R11]]）：用引擎，或引擎加分布，批量填充一个范围。引擎或分布可以提供更快的批量成员函数 `generate_random`，规范正文在 [[alg.rand]]。

本机 libc++ 还没有提供这两项。

<details class="fine" markdown="1"><summary>其余条文</summary>

¶1 [rand] 定义了产生（伪）随机数的设施。

[rand.synopsis] 的 freestanding 标注：概念 `uniform_random_bit_generator` 和预定义别名 `minstd_rand0`、`minstd_rand`、`mt19937`、`mt19937_64`、`ranlux24_base`、`ranlux48_base`、`ranlux24`、`ranlux48`、`philox4x32`、`philox4x64` 标为 freestanding；`linear_congruential_engine`、`subtract_with_carry_engine`、`philox_engine`、`discard_block_engine`、`independent_bits_engine`、`uniform_int_distribution` 标为部分 freestanding（流运算符除外）。`mersenne_twister_engine` 模板本身没有标注，而它的别名 `mt19937` 却是 freestanding 的；提供别名就必须提供那个特化，所以这看起来是标注上的疏漏。`shuffle_order_engine`、`knuth_b`、`default_random_engine`、`random_device`、`seed_seq`、`generate_canonical` 和其余分布都没有标注。

</details>

## 思考题

!!! question "1"
    `std::mt19937 a(1), b(1); std::normal_distribution<double> d; double x = d(a), y = d(b);` 中 `x == y` 一定成立吗？换一个标准库实现，`x` 的值会变吗？

<details markdown="1">
<summary>答案</summary>

不一定。两个引擎的初始状态相同，但分布 `d` 是同一个对象。`normal_distribution` 常用 Box–Muller 或极坐标法，一次算出两个值并缓存一个，[[rand.req]] 允许分布有这种内部状态。`d(a)` 之后 `d` 里可能缓存了一个值，`d(b)` 直接返回它而不消耗 `b`。

本机 libc++ 正是如此：`x = -1.40287`、`y = -0.549746`，调用之后 `a != b`，因为 `b` 一个值都没被消耗。要让 `x == y`，应使用两个分布对象，或在两次调用之间调用 `d.reset()`。

换实现时 `x` 一般会变，因为分布的算法由实现定义（[[rand.dist]]）。
</details>
