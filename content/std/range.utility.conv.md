---
title: 范围转换 ranges::to
summary: C++23 的 ranges::to<C>(r, args...) 如何把一个范围物化为容器——四条构造路径的优先级（直接构造、from_range 标签、迭代器对、默认构造后逐个追加并预留）、对范围的范围递归、模板模板形参版本的类型推导（DEDUCE_EXPR）、管道形式与常见编译错误。
status: done
covers: *
since: c++23
papers: P1206R7
related: range.utility, range.adaptor.object, range.req, range.access, containers, container.reqmts, func.require
tags: 标准库, 范围, ranges::to, 容器
updated: 2026-10-18
---

视图是惰性的，迟早要"落地"成容器。C++20 里这一步很别扭：

```cpp
auto r = v | std::views::filter(pred);
std::vector<int> out(r.begin(), r.end());          // 要求 common_range；否则编译失败
```

C++23 的 `ranges::to`（[[P1206R7]]）把它变成：

```cpp
auto out = v | std::views::filter(pred) | std::ranges::to<std::vector>();
```

## 总览（[range.utility.conv.general]）

¶1 转换函数用以下方式之一从范围构造对象（通常是容器）：接受范围的构造函数、带 `from_range_t` 标签的构造函数、接受一对迭代器的构造函数，或者默认构造后逐个插入。¶2 `ranges::to` 会**递归**应用，所以能转换"范围的范围"。¶2 例 1：

```cpp
auto words = views::split(str, ' ') | to<vector<string>>();
```

`split` 的每个元素是 `subrange<const char*>`，它本身是范围而 `string` 也是范围，于是对每个元素再调用 `to<string>`。

¶3–¶5 定义三个说明用的工具：

- *reservable-container*：`sized_range`，且有 `reserve(n)`、`capacity()`、`max_size()`（返回类型与 `n` 相同）；
- *container-appendable*：能用 `emplace_back` / `push_back` / `emplace_hint(c.end(), …)` / `insert(c.end(), …)` 之一追加；
- *container-append*：按上述顺序选择第一个可用的方式追加一个元素。

## `to<C>(r, args...)`（[range.utility.conv.to] ¶1–¶2）

```cpp
template<class C, input_range R, class... Args> requires (!view<C>)
  constexpr C to(R&& r, Args&&... args);
```

¶1 *Mandates*：`C` 是 cv 非限定的类类型。约束 `!view<C>`：`to` 是用来**物化**的，`to<string_view>` 不被接受（视图应该用视图适配器构造）。

¶2 返回值按如下顺序构造：

**情形 2.1**：`C` 不是 `input_range`，**或者** `range_reference_t<R>` 可以转换为 `range_value_t<C>`（即"元素可以直接放进去"）：

| 子条 | 条件 | 做法 |
|---|---|---|
| 2.1.1 | `constructible_from<C, R, Args...>` | `C(std::forward<R>(r), args...)` |
| 2.1.2 | `constructible_from<C, from_range_t, R, Args...>` | `C(from_range, std::forward<R>(r), args...)` |
| 2.1.3 | `common_range<R>`，且 `iterator_traits<iterator_t<R>>::iterator_category` 有效并派生自 `input_iterator_tag`，且 `constructible_from<C, iterator_t<R>, sentinel_t<R>, Args...>` | `C(ranges::begin(r), ranges::end(r), args...)` |
| 2.1.4 | `constructible_from<C, Args...>` 且 *container-appendable* | 默认构造（带 `args`）；若 `R` 是 `approximately_sized_range` 且 `C` 可预留，先 `reserve(reserve_hint(r))`；再逐个 *container-append* |
| 2.1.5 | 其他 | 程序非良构 |

**情形 2.2**：否则（元素不能直接转换），若 `range_reference_t<R>` 本身是 `input_range`：对每个元素递归调用 `to<range_value_t<C>>`：

```cpp
to<C>(ref_view(r) | views::transform([](auto&& elem) {
  return to<range_value_t<C>>(std::forward<decltype(elem)>(elem));
}), std::forward<Args>(args)...);
```

**情形 2.3**：其他，非良构。

几个要点：

- **2.1.3 检查的是 C++17 风格的 `iterator_category`**：老容器的迭代器对构造函数是按 *Cpp17InputIterator* 写的。C++20 视图的迭代器若没有 `iterator_category`（例如 `iota_view` 的迭代器在 `W` 不是整数时、`transform_view` 在某些情况下），这条就不适用，于是退到 2.1.4。
- **2.1.4 的预留**：C++23 时代用的是 `sized_range` 与 `ranges::size`；当前草案改成了更宽松的 `approximately_sized_range` 与 `ranges::reserve_hint`（{{c++26}}），这样连 `filter_view` 这类"知道上界"的视图也有机会预先分配。
- **2.1 的"或者 `C` 不是 `input_range`"**：允许转换成不是范围的东西，只要它能由范围构造，例如某个"接受范围的统计累加器"类。

## 模板模板形参版本：`to<vector>(r)`（¶3–¶5）

```cpp
template<template<class...> class C, input_range R, class... Args>
  constexpr auto to(R&& r, Args&&... args);
```

不写元素类型时，需要推导出完整的 `C<...>`。¶4 定义 *DEDUCE_EXPR*，依次尝试：

1. `C(declval<R>(), declval<Args>()...)`；
2. `C(from_range, declval<R>(), declval<Args>()...)`；
3. `C(declval<input-iterator>(), declval<input-iterator>(), declval<Args>()...)`——*input-iterator* 是 ¶3 定义的一个满足 *Cpp17InputIterator* 语法要求、`value_type` 为 `range_value_t<R>` 的说明用类型。

也就是说，借助各容器的**类模板实参推导**（CTAD）指引（C++23 为所有容器添加了 `from_range_t` 推导指引）。¶5 结果为 `to<decltype(DEDUCE_EXPR)>(r, args...)`。

```cpp run ok
#include <deque>
#include <list>
#include <ranges>
#include <set>
#include <string>
#include <vector>
#include <cstdio>
int main() {
  auto sq = std::views::iota(1, 5) | std::views::transform([](int i) { return i * i; });
  auto v = sq | std::ranges::to<std::vector>();                    // vector<int>（CTAD 推导）
  auto d = std::ranges::to<std::deque<long>>(sq);                  // 元素类型转换
  auto s = sq | std::ranges::to<std::set<int, std::greater<>>>();  // 带比较器类型
  // 嵌套：range of ranges → vector<vector<int>>（逐层递归调用 to）
  std::vector<std::list<int>> ll{{1, 2}, {3}};
  auto vv = ll | std::ranges::to<std::vector<std::vector<int>>>();
  // 非 common、非 sized 的输入：走 "默认构造 + 逐个追加" 分支
  auto tw = std::views::iota(0) | std::views::take_while([](int i) { return i < 3; });
  auto w = tw | std::ranges::to<std::vector<int>>();
  auto str = std::ranges::to<std::string>(std::views::repeat('x', 3));
  std::printf("%zu %zu %d %zu %zu %s\n", v.size(), d.size(), *s.begin(), vv[0].size(), w.size(), str.c_str());
  // 4 4 16 2 3 xxx
}
```

## 管道形式（[range.utility.conv.adaptors]）

```cpp
template<class C, class... Args> requires (!view<C>)
  constexpr auto to(Args&&... args);
template<template<class...> class C, class... Args>
  constexpr auto to(Args&&... args);
```

¶2 不带范围实参调用时，返回一个**范围适配器闭包对象**（[[range.adaptor.object]]），它是完美转发调用包装器（[[func.require]]）：无目标对象，绑定实参为 `decay_t<Args>...`（按值保存！），调用模式为 `to<C>(r, bound_args...)`。所以 `r | to<vector>(alloc)` 中的分配器会被**复制**进闭包。

注意 `to` 本身不是范围适配器对象（它不返回视图），但它的单参数形式返回的闭包对象可以参与 `|` 组合：`auto pipeline = views::filter(p) | ranges::to<vector>();` 是合法的，得到一个"过滤并物化"的闭包。

```cpp run error
#include <ranges>
#include <vector>
#include <string_view>
auto x = std::views::iota(0, 3) | std::ranges::to<std::string_view>();  // error: C 不能是视图
int main() {}
```

## 常见误区

!!! pitfall "`to<vector>()` 忘了括号"
    `r | std::ranges::to<std::vector>` 不能编译——`to<vector>` 是函数模板名，不是对象。必须写成 `to<std::vector>()`。这与 `views::join`（本身就是闭包对象，不带括号）不同。

!!! pitfall "从 `map` 物化需要 pair 而不是 tuple"
    `views::zip(keys, values) | to<std::map>()` 的元素是 `tuple<K&, V&>`；C++23 起 `pair` 可以从 *pair-like* 的 `tuple` 构造，所以能工作。但推导出来的 `map` 的键类型是什么，取决于 `map` 的 `from_range` 推导指引对 `range_value_t` 的处理——遇到意外类型时，显式写出 `to<std::map<K, V>>()` 最稳妥。

## 小结

- 选择顺序：范围构造 → `from_range` → 迭代器对（需 common 且有 C++17 类别）→ 默认构造 + 预留 + 逐个追加；
- 元素不能直接放入时递归 `to<range_value_t<C>>`；
- `to<C>` 要求 `C` 不是视图；`to<Template>` 通过 CTAD 推导完整类型；
- 无范围实参的形式返回闭包对象，参数按值保存。
