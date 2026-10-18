---
title: 特化的 <random> 算法
summary: C++26 的 ranges::generate_random——让随机数引擎与分布以“批量”方式填充一个 range：先尝试成员 generate_random，再对 sized_range 用 span 分批，最后退化为 ranges::generate；“效果必须等价于逐个调用 g()”这一不变量；libc++ 尚未实现
status: draft
covers: *
related: alg.modifying.operations, rand.req.urng, rand.req.eng, rand.req.dist, alg.random.shuffle
tags: 标准库, 算法, random, ranges, C++26
updated: 2026-10-18
---

随机数引擎的接口是一次产生一个值：`g()`。对需要大量随机数的程序（蒙特卡罗模拟、噪声生成），逐个调用有两个问题：每次调用都有状态读写开销，编译器难以向量化；而像 Philox 这类基于计数器的引擎、或硬件随机数生成器，本身就适合“一次产生一批”。C++26 的 `std::ranges::generate_random`（声明于 `<random>`，¶1 of [alg.rand.general]）为此提供了批量接口，同时**不改变**产生的值序列。

## 用引擎填充（[alg.rand.generate] ¶1–¶4）

```cpp
template<class R, class G>
  requires output_range<R, invoke_result_t<G&>> &&
           uniform_random_bit_generator<remove_cvref_t<G>>
  constexpr borrowed_iterator_t<R> ranges::generate_random(R&& r, G&& g);
```

¶1 *Effects* 是一个三级回退：

1. 若 `g.generate_random(std::forward<R>(r))` 良构，调用它——引擎自己提供了批量实现；
2. 否则，若 `R` model `sized_range`，以**未指明次数**的 `g()` 调用或 `g.generate_random(s)` 调用（`s` 是 `span<invoke_result_t<G&>, N>`，N 可以每次不同）填满 `ranges::size(r)` 个值——这允许实现按固定块大小分批、利用引擎的批量接口；
3. 否则调用 `ranges::generate(std::forward<R>(r), ref(g))`。

¶2：返回 `ranges::end(r)`。

关键不变量在 ¶3 *Remarks*：

!!! std
    The effects of `generate_random(r, g)` shall be equivalent to `ranges::generate(std::forward<R>(r), ref(g))`.

注 2：这意味着 `g.generate_random(a)` 必须用与逐次调用 `g()` **相同的值**填充 `a`。批量化只是性能优化，不允许改变随机序列——这保证了用固定种子的程序在换用批量接口后结果可复现。同时引擎的状态在调用后也必须与调用 N 次 `g()` 后相同（由“效果等价”推出）。

¶4：迭代器+哨位版等价于把它们包成 `subrange` 再调用。

## 用分布填充（¶5–¶8）

```cpp
template<class R, class G, class D>
  requires output_range<R, invoke_result_t<D&, G&>> && invocable<D&, G&> &&
           uniform_random_bit_generator<remove_cvref_t<G>> && is_arithmetic_v<invoke_result_t<D&, G&>>
  constexpr borrowed_iterator_t<R> ranges::generate_random(R&& r, G&& g, D&& d);
```

同样的三级回退：先试 `d.generate_random(r, g)`；再对 sized range 用 `invoke(d, g)` 或 `d.generate_random(s, g)` 分批；最后 `ranges::generate(r, [&d, &g] { return invoke(d, g); })`。

¶7 的等价要求与引擎版相同，但注 4 措辞值得注意：分布的批量版本要“fills `a` with the values **with the same random distribution**”——对分布只要求**分布相同**，没有要求逐值相同。这是因为分布的实现（例如 `normal_distribution` 的 Box–Muller 方法一次产生两个值）本身就可能因调用方式不同而消耗不同数量的引擎输出。不过 ¶7 的 *Remarks* 仍写着“effects … shall be equivalent to `ranges::generate(...)`”，两者的确切关系是一个精细的措辞问题，阅读时宜以规范性的 ¶7 为准、以注 4 理解意图。

## 用法

```cpp
#include <random>
#include <vector>

int main() {
    std::vector<double> v(1'000'000);
    std::philox4x32 g(42);                      // C++26 的计数器式引擎
    std::normal_distribution<double> d(0.0, 1.0);
    std::ranges::generate_random(v, g, d);      // 可能被实现批量化
}
```

!!! impl "实现状态"
    截至 LLVM 23，libc++ 尚未提供 `std::ranges::generate_random`（`no member named 'generate_random' in namespace 'std::ranges'`），因此上例未在本机验证。语义上它与 `std::ranges::generate(v, [&] { return d(g); })` 相同，可以用后者替代。

## 思考题

<details markdown="1">
<summary>一个用户自定义引擎提供了成员 `generate_random(span<uint32_t>)`，但它产生的值与逐次调用 `operator()` 不同（例如为了性能使用了不同的内部置换）。把它用于 `ranges::generate_random` 会怎样？</summary>

违反了 ¶3 *Remarks* 的等价要求（这是对程序提供的类型施加的要求），按 [[res.on.functions]] 行为未定义。更实际的后果是：同一程序在不同标准库实现上（有的走成员 `generate_random`、有的走逐个 `g()`）会得到不同的随机序列。
</details>

## 小结

- `ranges::generate_random` 是 `ranges::generate(r, ref(g))` 的可批量化版本，声明于 `<random>`。
- 回退顺序：成员 `generate_random` → sized range 分批 → `ranges::generate`。
- 引擎版：批量结果必须与逐个调用 `g()` 相同；分布版：分布相同。
- libc++ 尚未实现。
