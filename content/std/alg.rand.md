---
title: 特化的 <random> 算法
summary: C++26 的 ranges::generate_random 用随机数引擎或分布批量填充一个范围；它依次尝试引擎自己的批量接口、分批调用、逐个调用，但结果必须与逐个调用 g() 相同。
status: draft
covers: *
papers: P1068R11, P2075R6
related: alg.modifying.operations, rand.req.urng, rand.req.eng, rand.req.dist, alg.random.shuffle
tags: 标准库, 算法, random, ranges, C++26
updated: 2026-10-19
---

!!! tldr
    - `std::ranges::generate_random(r, g)` 用引擎 `g` 填满范围 `r`，效果必须与 `ranges::generate(r, ref(g))` 逐个调用 `g()` 相同，只是允许批量生成。
    - 它先尝试引擎的成员函数 `g.generate_random(r)`，再对已知大小的范围分批生成，最后退化为逐个调用。
    - 用分布填充的版本 `generate_random(r, g, d)` 结构相同；注释对批量版本的要求只是分布相同。
    - 截至写作时，本机 libc++ 还没有提供这个函数。

{{c++26}} 随机数引擎的接口一次只产生一个值：`g()`。需要大量随机数的程序（蒙特卡罗模拟、噪声生成）逐个调用时，每次都要读写引擎状态，编译器也难以向量化。另一方面，像 Philox 这样基于计数器的引擎（[[P2075R6]]）、硬件随机数生成器，天然适合一次产生一批。

`std::ranges::generate_random`（[[P1068R11]]）提供了批量接口，同时不改变产生的值序列。[alg.rand.general] ¶1 说明它声明在 `<random>` 中。

```cpp
#include <random>
#include <vector>

int main() {
    std::vector<double> v(1'000'000);
    std::philox4x32 g(42);                      // C++26 的计数器式引擎
    std::normal_distribution<double> d(0.0, 1.0);
    std::ranges::generate_random(v, g, d);      // 实现可以批量生成
}
```

截至写作时，本机 libc++ 既没有 `std::philox4x32`，也没有 `std::ranges::generate_random`，上例按标准原文写成，没有经过编译验证。在支持之前，可以用语义相同的 `std::ranges::generate(v, [&] { return d(g); })` 代替。

## 用引擎填充（[alg.rand.generate] ¶1–¶4）

```cpp
template<class R, class G>
  requires output_range<R, invoke_result_t<G&>> &&
           uniform_random_bit_generator<remove_cvref_t<G>>
  constexpr borrowed_iterator_t<R> ranges::generate_random(R&& r, G&& g);
```

¶1 的效果按顺序尝试三种做法：

1. ¶1.1 如果 `g.generate_random(std::forward<R>(r))` 良构，就调用它，由引擎自己提供批量实现；
2. ¶1.2 否则，如果 `R` 是 `sized_range`，就通过未指定次数的 `g()` 调用或 `g.generate_random(s)` 调用填满 `ranges::size(r)` 个值，其中 `s` 是 `span<invoke_result_t<G&>, N>`。注 1 说明每次调用的 N 可以不同，所以实现可以按固定大小分块，利用引擎接受 `span` 的批量接口；
3. ¶1.3 否则调用 `ranges::generate(std::forward<R>(r), ref(g))`，逐个生成。

¶2 返回 `ranges::end(r)`。¶4 迭代器加哨兵的版本等价于把它们包成 `subrange` 再调用。

!!! std
    The effects of `generate_random(r, g)` shall be equivalent to `ranges::generate(std::forward<R>(r), ref(g))`.

¶3 是这一节最关键的要求。注 2 指出，这意味着 `g.generate_random(a)` 必须用与逐次调用 `g()` 相同的值填充 `a`。效果等价也意味着调用之后引擎的状态与调用 N 次 `g()` 之后相同。

批量生成只是性能优化，不能改变随机序列。所以使用固定种子的程序改用 `generate_random` 之后，结果仍可复现。

## 用分布填充（¶5–¶8）

```cpp
template<class R, class G, class D>
  requires output_range<R, invoke_result_t<D&, G&>> && invocable<D&, G&> &&
           uniform_random_bit_generator<remove_cvref_t<G>> &&
           is_arithmetic_v<invoke_result_t<D&, G&>>
  constexpr borrowed_iterator_t<R> ranges::generate_random(R&& r, G&& g, D&& d);
```

¶5 的三种做法与引擎版本相同：先尝试 `d.generate_random(r, g)`；再对已知大小的范围分批调用 `invoke(d, g)` 或 `d.generate_random(s, g)`；最后 `ranges::generate(r, [&d, &g] { return invoke(d, g); })`。

¶7 同样要求效果等价于逐个调用 `invoke(d, g)`。但注 4 的措辞有所不同：分布的批量版本用与逐个调用具有相同随机分布的值填充 `a`，没有说逐值相同。分布的实现可能因调用方式不同而消耗不同数量的引擎输出，例如 `normal_distribution` 常用的方法一次产生两个值。规范性的 ¶7 和说明性的注 4 之间存在这点出入，读的时候应以 ¶7 为准，借注 4 理解设计意图。

## 思考题

!!! question "思考题"
    一个用户定义的引擎提供了成员函数 `generate_random(span<uint32_t>)`，但为了性能，它产生的值与逐次调用 `operator()` 不同。把它用于 `ranges::generate_random` 会怎样？

<details markdown="1">
<summary>答案</summary>

它违反了 ¶3 的等价要求。这是对程序提供的类型提出的要求，违反时行为未定义（[[res.on.functions]]）。更实际的后果是：有的标准库实现调用成员 `generate_random`，有的逐个调用 `g()`，同一程序在不同实现上会得到不同的随机序列。
</details>
