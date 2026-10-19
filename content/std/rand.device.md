---
title: random_device
summary: 非确定性随机数源 random_device：标准允许它退化成确定性引擎，token 的含义和 entropy() 的准确性都由实现决定；它适合提供种子，不适合直接用来大量生成随机数。
status: done
related: rand, rand.req, rand.util, rand.eng
tags: 标准库, 随机数, random_device, 熵
updated: 2026-10-19
---

!!! tldr
    - `random_device` 是 `<random>` 中唯一预期为非确定性的 URBG，通常从操作系统的熵源读取比特。
    - 实现受限时，标准允许它改用确定性的引擎，此时 `entropy()` 返回 0。反过来，`entropy()` 返回 0 不一定说明它是确定性的。
    - 构造函数的 token 实参是什么意思由实现定义，可移植的代码只用默认构造函数。
    - 构造和调用都可能抛出派生自 `std::exception` 的异常。
    - 惯用法是用它给引擎提供种子，再由引擎生成大量随机数。

## 用它做种子

```cpp run title="seed-from-device.cpp" ok
#include <array>
#include <random>

int main() {
  std::random_device rd;                  // 熵源
  std::array<unsigned, 8> e;
  for (auto& x : e) x = rd();
  std::seed_seq seq(e.begin(), e.end());
  std::mt19937_64 g(seq);                 // 主力引擎
  std::uniform_real_distribution<double> u(0.0, 1.0);
  double sum = 0;
  for (int i = 0; i < 1000; ++i) sum += u(g);
  return sum > 0 ? 0 : 1;
}
```

`random_device` 只提供 8 个 32 位的种子值，此后的 1000 个随机数都由引擎产生。这样分工有几个理由：

1. 每次 `rd()` 可能是一次系统调用，比引擎推进一步慢得多；
2. 记录下 `e` 就能重放整个运行，`random_device` 本身无法重放；
3. `random_device` 的 `operator()` 可能抛异常，引擎的不会；
4. 标准对 `random_device` 的保证很弱，见下文。

## 类的形状

- `result_type` 是 `unsigned int`，`min()` 和 `max()` 是覆盖它全部范围的 `static constexpr` 函数，所以它满足 `uniform_random_bit_generator` 概念（[[rand.req]]）；
- 默认构造函数委托给 `random_device(实现定义的 token)`，另有 `explicit random_device(const string& token)`；
- 成员函数只有 `operator()` 和 `double entropy() const noexcept`；
- 复制构造和复制赋值被删除，也没有声明移动操作，所以它既不能复制也不能移动。它代表一个外部资源，例如文件描述符或设备句柄。

它不是引擎：没有播种、没有 `==`、没有文本表示、没有 `discard`，只能用在要求 URBG 的地方。

## 标准保证了什么（¶1–¶7）

¶1 `random_device` 产生非确定性的随机数。但 ¶2 紧接着放宽了这一点：

!!! std
    If implementation limitations prevent generating nondeterministic random numbers, the implementation may employ a random number engine.

    如果实现的限制使它无法产生非确定性随机数，实现可以使用一个随机数引擎。

所以一个符合标准的 `random_device` 可以在每次运行时都输出同样的序列。这曾经真实发生过：早期 MinGW 平台上的 libstdc++ 就是这样实现的，用 `random_device` 播种的程序每次运行结果都相同。

¶5 `entropy()` 是标准留下的探测手段。如果实现使用了引擎，它返回 0.0；否则返回对 `operator()` 输出的熵的估计，范围是 `min()` 到 log₂(`max()` + 1)，对 32 位的 `unsigned int` 上界是 32。脚注 223 给出熵的定义：有 n 个状态、概率分别为 P₀ … Pₙ₋₁ 的设备，熵 S = −Σ Pᵢ·log Pᵢ。

这只是一个估计，标准对它的准确性没有要求。实现完全可以对一切情况都报 0，即使它是非确定性的；返回非零值时，标准也没有办法检验。所以 `entropy() == 0` 只能当作可能是确定性的警示，不是可靠的判据。

¶4 token 参数的含义，以及默认构造函数使用的 token 值，都由实现定义。脚注 222 说明意图是让实现区分不同的随机源。各实现常把 token 解释为设备路径或熵源名，例如 `"/dev/urandom"`、`"rdrand"`，但接受的字符串各不相同。

¶3、¶7 构造时无法初始化、调用时无法取得随机数，都会抛出实现定义类型的异常，该类型派生自 `exception`。¶6 每次调用返回 `min()` 到 `max()` 之间均匀分布的非确定性值，怎样生成由实现定义。

!!! impl "libc++ 在 macOS 上"
    本机 libc++ 的默认构造函数委托给 `random_device("/dev/urandom")`，但在 Apple 平台上实际调用 `arc4random()`，token 被忽略：传 `"/dev/random"`、`"rdrand"` 甚至 `"foo"` 都能构造成功，`entropy()` 都返回 32。

## 它不是密码学构件

标准对 `random_device` 的安全性没有任何要求，它甚至可以是确定性的（¶2）。需要密码学安全的随机数时，应直接使用操作系统提供的接口。
