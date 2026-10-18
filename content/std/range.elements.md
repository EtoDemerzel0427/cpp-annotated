---
title: elements、keys、values 视图
summary: elements_view<V, N> 从"元组式"元素中取第 N 个分量；has-tuple-element 与 returnable-element 约束、keys/values 是 N=0/1 的别名；get-element 对引用元素返回 get<N> 的引用、对 prvalue 元素按值返回以防悬垂；map 的 keys 不可写（键是 const）而 values 可写。
status: done
covers: *
since: c++20
papers: P0896R4
related: range.adaptors, range.transform, range.zip, range.enumerate, tuple.like, tuple, pair, associative
tags: 标准库, 范围, elements, keys, values
updated: 2026-10-18
---

对 `map<K, V>` 取所有键、对 `vector<tuple<…>>` 取某一列——`elements_view` 是"投影到第 N 个分量"的专用适配器。用 `transform([](auto& p) -> auto& { return std::get<N>(p); })` 也能做到，但手写 lambda 很容易在 prvalue 元素上返回悬垂引用，而 `elements_view` 的规范把这一点处理好了。

## 概览（[range.elements.overview]）

¶1 `elements_view` 接受一个元素为元组式值的视图和一个 `size_t`，产生一个值类型为底层值类型第 N 个元素的视图。¶2 `views::elements<N>(E)` 表达式等价于 `elements_view<views::all_t<decltype((E))>, N>{E}`。¶3–¶4 `keys_view<R>` 是 `elements_view<R, 0>` 的别名，`values_view<R>` 是 `elements_view<R, 1>` 的别名；对应 `views::keys`、`views::values`。

## 约束（[range.elements.view]）

```cpp
template<class T, size_t N>
concept has-tuple-element =
  tuple-like<T> && N < tuple_size_v<T> &&
  requires(T t) { { std::get<N>(t) } -> convertible_to<const tuple_element_t<N, T>&>; };

template<class T, size_t N>
concept returnable-element =
  is_reference_v<T> || move_constructible<tuple_element_t<N, T>>;

template<input_range V, size_t N>
  requires view<V> && has-tuple-element<range_value_t<V>, N> &&
           has-tuple-element<remove_reference_t<range_reference_t<V>>, N> &&
           returnable-element<range_reference_t<V>, N>
class elements_view;
```

- *tuple-like*（[[tuple.like]]）：`tuple`、`pair`、`array`、`subrange`、`complex`（C++26）等标准库中的元组式类型。**用户自定义的、只特化了 `tuple_size`/`get` 的类型不是 *tuple-like***——这个说明用概念只认标准库列出的那些模板，所以 `elements_view` 不能用于自定义结构体；
- *returnable-element*：元素不是引用时，要按值返回第 N 个分量，所以它必须可移动构造。

## *get-element*：何时返回引用（[range.elements.iterator] ¶3）

```cpp
if constexpr (is_reference_v<range_reference_t<Base>>) {
  return std::get<N>(*i);
} else {
  using E = remove_cv_t<tuple_element_t<N, range_reference_t<Base>>>;
  return static_cast<E>(std::get<N>(*i));
}
```

- 底层元素是引用（`map` 的 `pair<const K, V>&`）：返回 `std::get<N>` 的引用——可以写回（值），或只读（键是 `const K`）；
- 底层元素是 prvalue（`transform` 生成的 `pair`）：`*i` 是一个临时元组，若返回 `get<N>` 的引用（会是 `T&&`），完整表达式结束后就悬垂。所以**按值**返回一个副本。

C++20 最初的措辞没有这个分支，在 prvalue 元素上会返回悬垂的右值引用；这一缺陷通过后来的库缺陷修正补上。

```cpp run ok
#include <map>
#include <ranges>
#include <string>
#include <tuple>
#include <vector>
#include <cstdio>
int main() {
  std::map<std::string, int> m{{"x", 1}, {"y", 2}};
  for (auto& k : m | std::views::keys) std::printf("%s", k.c_str());
  for (int& v : m | std::views::values) v *= 10;                     // 引用：可写回
  std::printf(" %d\n", m["y"]);                                       // xy 20
  std::vector<std::tuple<int, double, char>> t{{1, 2.5, 'a'}, {2, 3.5, 'b'}};
  for (char c : t | std::views::elements<2>) std::printf("%c", c);   // ab
  // 底层元素是 prvalue pair：get-element 按值返回
  auto pairs = std::views::iota(0, 3) | std::views::transform([](int i) { return std::pair{i, i * i}; });
  auto sq = pairs | std::views::values;
  static_assert(std::same_as<std::ranges::range_reference_t<decltype(sq)>, int>);   // 不是 int&&：避免悬垂
  for (int x : sq) std::printf(" %d", x);                             // 0 1 4
  std::puts("");
}
```

## 其他性质

- 迭代器强度、common、sized 均随底层（迭代器只包装底层迭代器，`++`、`+=` 直接转发）；
- `iterator_category`：底层元素是 prvalue 时为 `input_iterator_tag`（与 [[range.transform]] 同理），否则取底层类别（contiguous 降为 random access）；
- **借用性随底层**——迭代器不需要访问视图对象。这是它相对 `transform(lambda)` 的另一个优势：`ranges::find(views::keys(m), "x")` 在 `m` 为左值时返回真迭代器，而 `transform_view` 永远不借用；
- `views::elements<N>` 中 `N` 是模板实参，`views::elements<N>` 本身是一个闭包对象（不需要括号）。

!!! pitfall "对 zip 的结果用 keys/values"
    `views::zip(a, b)` 的元素是 `tuple<A&, B&>` **prvalue**——是 prvalue 的元组，里面装着引用。`zip(a, b) | views::values` 走 *get-element* 的 else 分支，`E` = `remove_cv_t<B&>` = `B&`，于是返回 `static_cast<B&>(get<1>(t))`——仍然是指向 `b` 中元素的引用，不会悬垂、也能写回。规则对"元组里装引用"的情形恰好正确。

## 小结

| | `elements<N>` / `keys` / `values` |
|---|---|
| 适用 | 标准库的 *tuple-like* 元素（`pair`、`tuple`、`array`、`subrange`……） |
| 引用类型 | 底层是引用 → `get<N>` 的引用；底层是 prvalue → 分量的副本 |
| 强度 / sized / common | 随底层 |
| 借用 | 随底层 |
