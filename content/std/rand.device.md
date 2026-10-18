---
title: random_device
summary: 非确定性随机数源 random_device——实现受限时允许退化为确定性引擎、token 与默认 token 的含义由实现定义、entropy() 的估计值、构造与调用失败时抛异常；不可复制；在 libc++/macOS 上的实际行为；适合做种子而不适合做主力生成器的原因
status: done
related: rand, rand.req, rand.util, rand.eng
tags: 标准库, 随机数, random_device, 熵
updated: 2026-10-18
---

`random_device` 是 `<random>` 中唯一的**非确定性**均匀随机比特生成器。它通常从操作系统的熵源（`/dev/urandom`、`getrandom`、`arc4random`、`BCryptGenRandom`、CPU 的 `RDRAND` 指令等）读取比特。标准对它的规定非常宽松，几乎所有细节都是"实现定义"——这一节读下来，最重要的收获是知道标准**没有**保证什么。

## 类的形状

概要（摘要）：

- `result_type` 是 `unsigned int`；`min()`/`max()` 为 `unsigned int` 的全范围，是 `static constexpr`，所以它满足 `uniform_random_bit_generator` 概念（[[rand.req]]）；
- 默认构造函数委托给 `random_device(implementation-defined)`，另有 `explicit random_device(const string& token)`；
- `result_type operator()()`、`double entropy() const noexcept`；
- 复制构造与复制赋值被删除——它代表一个外部资源（文件描述符、设备句柄），不能复制。也没有声明移动操作，所以同样不可移动。

它**不是**随机数引擎：没有播种、没有 `==`、没有流式表示、没有 `discard`。所以它只能用在要求 URBG 的地方。

## 非确定性与退化（¶1–¶2）

¶1：`random_device` 产生非确定性随机数。

¶2：

!!! std
    If implementation limitations prevent generating nondeterministic random numbers, the implementation may employ a random number engine.

    如果实现的限制使其无法产生非确定性随机数，实现可以使用一个随机数引擎。

也就是说，一个符合标准的 `random_device` 可以每次程序运行都输出同样的序列。这不是理论上的担忧：历史上确有 Windows 平台的 GCC 标准库实现这样做，导致"用 `random_device` 播种"的程序每次运行结果都一样。标准为此留了一个探测口：`entropy()`。

## 构造与 token（¶3–¶4）

¶3：构造失败时抛出一个**实现定义类型**的异常，该类型派生自 `exception`。

¶4：`token` 形参的语义、以及默认构造函数所用的 token 值，都由实现定义。脚注 222 说明意图：让实现区分不同的随机源。

各实现常见的做法是把 token 解释为设备路径或熵源名（如 `"/dev/urandom"`、`"rdrand"`），但这完全是约定，不同实现接受的字符串不同。可移植代码应该只用默认构造函数。

!!! impl "libc++ on macOS"
    本机 libc++ 的默认构造函数委托给 `random_device("/dev/urandom")`，但在 Apple 平台上实际调用 `arc4random()`，**token 被忽略**：传 `"/dev/random"`、`"rdrand"`，甚至 `"foo"`，都能成功构造，`entropy()` 都返回 32。为了保持与早期基于文件描述符的实现的 ABI 兼容，对象里仍保留了一个不再使用的 `int` 填充成员。

## entropy（¶5）

¶5：若实现使用随机数引擎（即 ¶2 的退化情形），返回 0.0；否则返回 `operator()` 所返回随机数的**熵估计**，范围在 `min()` 到 log₂(`max()` + 1) 之间。脚注 223 给出熵的定义：有 n 个状态、概率分别为 P₀ … Pₙ₋₁ 的设备，熵 S = −Σ Pᵢ·log Pᵢ。

对 32 位 `unsigned int`，上界是 32。读这条规则要注意两点：

- 它是**估计**，标准对估计的准确性没有任何要求。返回 0 的实现**可能**仍然是非确定性的（实现完全可以图省事，对一切情况都报 0）；返回非零的实现，标准也没有办法检验。
- 它是 `noexcept` 的，所以可以安全地在任何地方调用。

所以 `entropy() == 0` 可以作为"可能是确定性的"警示信号，但不是可靠的判据。

## 生成（¶6–¶7）

¶6：返回 `min()` 到 `max()`（含）之间均匀分布的非确定性随机值；**如何**生成由实现定义。

¶7：无法获得随机数时，抛出实现定义类型的异常（派生自 `exception`）。

与引擎不同，`operator()` 可能抛异常——例如熵源被关闭、读取失败。这意味着依赖 `random_device` 的初始化代码要考虑异常路径。

## 为什么用它做种子，而不是直接用它生成

```cpp run title="seed-from-device.cpp" ok
#include <array>
#include <functional>
#include <random>

int main() {
  std::random_device rd;                                    // 熵源
  std::array<unsigned, 8> e;
  for (auto& x : e) x = rd();
  std::seed_seq seq(e.begin(), e.end());
  std::mt19937_64 g(seq);                                   // 快速、可复现（若记录 e）的主力引擎
  std::uniform_real_distribution<double> u(0.0, 1.0);
  double sum = 0;
  for (int i = 0; i < 1000; ++i) sum += u(g);
  return sum > 0 ? 0 : 1;
}
```

理由：

1. **性能**：每次 `rd()` 可能是一次系统调用或一次硬件指令，比引擎的一次状态更新慢得多；
2. **可复现**：记录下种子数据就能复现整个运行，`random_device` 本身不能重放；
3. **可抛异常**：引擎的 `operator()` 不抛，`random_device` 的可能抛；
4. **标准保证薄弱**：它甚至可以是确定性的（¶2）。

需要密码学安全的随机数时，标准库的 `random_device` 也不是可靠的选择——标准没有对它的安全性作任何要求。应该直接使用操作系统提供的接口。

## 小结

| 方面 | 标准的规定 |
|---|---|
| 是否非确定性 | 预期如此，但实现受限时可以用引擎（¶2） |
| token 语义、默认 token | 实现定义（¶4） |
| 构造/生成失败 | 抛实现定义类型、派生自 `exception` 的异常（¶3、¶7） |
| `entropy()` | 退化时 0.0，否则为 [0, 32] 内的估计（对 32 位 `unsigned`）；准确性无保证 |
| 复制 | 删除 |
| 用途 | 给引擎提供种子熵 |
