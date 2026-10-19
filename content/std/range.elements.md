---
title: elements、keys、values 视图
summary: views::elements<N> 从每个元组式元素中取出第 N 个分量，views::keys 和 views::values 是 N 为 0 和 1 的简写；底层元素是引用时返回分量的引用，是临时对象时返回分量的副本，以免悬垂。
status: done
covers: *
since: c++20
papers: P0896R4
related: range.adaptors, range.transform, range.zip, range.enumerate, tuple.like, tuple, pair, associative
tags: 标准库, 范围, elements, keys, values
updated: 2026-10-19
---

!!! tldr
    - `views::elements<N>` 对每个元素取 `std::get<N>`；`views::keys` 是 `elements<0>`，`views::values` 是 `elements<1>`。
    - 元素必须是标准库的元组式类型：`pair`、`tuple`、`array`、`subrange`、`complex`。自己写的结构体即使特化了 `tuple_size` 和 `get` 也不行。
    - 底层元素是引用时（如 `map` 的元素），结果是分量的引用：`values` 可以写回，`keys` 只读，因为键是 `const`。
    - 底层元素是临时对象时，结果按值返回分量的副本，不会悬垂。
    - 迭代器类别、是否 sized、是否公共范围、是否借用，都与底层相同。

```cpp run ok
#include <cstdio>
#include <map>
#include <ranges>
#include <string>

int main() {
  std::map<std::string, int> m{{"x", 1}, {"y", 2}};
  for (auto& k : m | std::views::keys) std::printf("%s", k.c_str());   // xy
  for (int& v : m | std::views::values) v *= 10;                       // 写回 map
  std::printf(" %d\n", m["y"]);                                        // 20
}
```

取 `map` 的所有键、取 `vector<tuple<...>>` 的某一列，都是在把每个元素投影到它的第 N 个分量上。`transform([](auto& p) -> auto& { return std::get<N>(p); })` 也能做到，但这样手写的 lambda 在元素是临时对象时会返回悬垂引用；`elements_view` 的规则专门处理了这种情况。

## `views::elements<N>` [range.elements.overview]

¶1 `elements_view` 接受一个元素为元组式值的视图和一个 `size_t` 值 N，产生的视图的值类型是底层值类型的第 N 个分量。¶2 `views::elements<N>(E)` 等价于 `elements_view<views::all_t<decltype((E))>, N>{E}`。`views::elements<N>` 本身已经是一个可以直接放在 `|` 右边的对象，不需要加括号调用。

¶3 `keys_view<R>` 是 `elements_view<R, 0>` 的别名，¶4 `values_view<R>` 是 `elements_view<R, 1>` 的别名，对应的适配器是 `views::keys` 和 `views::values`。它们主要用于关联容器。¶2–¶4 的三个标准例子用的是同一个 `map`：

```cpp run ok
#include <algorithm>
#include <iostream>
#include <map>
#include <ranges>
#include <string_view>
using namespace std::literals;

int main() {
  auto historical_figures = std::map{
    std::pair{"Lovelace"sv, 1815}, {"Turing"sv, 1912},
    {"Babbage"sv, 1791}, {"Hamilton"sv, 1936}};
  for (auto&& name : historical_figures | std::views::keys)
    std::cout << name << ' ';          // Babbage Hamilton Lovelace Turing
  auto is_even = [](const auto x) { return x % 2 == 0; };
  std::cout << std::ranges::count_if(historical_figures | std::views::values, is_even)
            << '\n';                   // 2
}
```

## 哪些元素可以用 [range.elements.view]

`elements_view` 的约束用到两个说明用概念：

- *has-tuple-element*：类型是 *tuple-like*，N 小于 `tuple_size_v`，并且 `std::get<N>(t)` 可用。值类型和引用类型都要满足。
- *returnable-element*：底层元素是引用，或者第 N 个分量可以移动构造。元素不是引用时，分量要按值返回，所以必须能移动。

*tuple-like*（[[tuple.like]]）只认标准库列出的几个模板：`array`、`complex`、`pair`、`tuple`、`ranges::subrange`。用户自定义的类型即使特化了 `tuple_size`、`tuple_element` 并提供了 `get`，也不满足这个概念，不能用 `elements_view`。这时用 `transform` 加投影。

```cpp error
#include <ranges>
#include <vector>

struct P { int a; int b; };
template<> struct std::tuple_size<P> : std::integral_constant<std::size_t, 2> {};
template<std::size_t I> struct std::tuple_element<I, P> { using type = int; };
template<std::size_t I> int& get(P& p) { return I == 0 ? p.a : p.b; }

std::vector<P> v;
auto k = v | std::views::keys;   // error: P 不是 tuple-like
```

## 引用还是副本 [range.elements.iterator]

¶3 迭代器的解引用由说明用函数 *get-element* 完成：

```cpp
if constexpr (is_reference_v<range_reference_t<Base>>) {
  return std::get<N>(*i);
} else {
  using E = remove_cv_t<tuple_element_t<N, range_reference_t<Base>>>;
  return static_cast<E>(std::get<N>(*i));
}
```

底层元素是引用时，比如 `map` 的 `pair<const K, V>&`，返回 `std::get<N>` 得到的引用：值可以写回，键是 `const K`，只读。

底层元素是临时对象时，比如 `transform` 生成的 `pair`，`*i` 是一个临时元组。如果返回 `get<N>` 的引用，它会指向这个临时对象，完整表达式一结束就悬垂。所以这时按值返回分量的副本。C++20 最初的措辞没有这个分支，[[LWG3502]] 把它补上了。

```cpp run ok
#include <cstdio>
#include <ranges>
#include <utility>
#include <vector>

int main() {
  auto pairs = std::views::iota(0, 3)
             | std::views::transform([](int i) { return std::pair{i, i * i}; });
  auto sq = pairs | std::views::values;
  static_assert(std::same_as<std::ranges::range_reference_t<decltype(sq)>, int>);  // 副本
  for (int x : sq) std::printf("%d ", x);       // 0 1 4

  std::vector<int> a{1, 2};
  std::vector<char> b{'x', 'y'};
  auto vs = std::views::zip(a, b) | std::views::values;
  static_assert(std::same_as<std::ranges::range_reference_t<decltype(vs)>, char&>);
  for (char& c : vs) c = 'z';                    // 写回 b
  std::printf("%c%c\n", b[0], b[1]);             // zz
}
```

第二个例子是一个容易想错的情形。`zip(a, b)` 的元素是临时的 `tuple<int&, char&>`，走的是 else 分支；但 `E` 是 `remove_cv_t<char&>`，也就是 `char&`，于是返回的仍然是指向 `b` 中元素的引用。元组里装的是引用时，结果也是引用，不会悬垂，也能写回。

## 其他性质

- 迭代器只是包装底层迭代器，`++`、`+=` 等直接转发。¶1 迭代器类别与底层相同（连续降为随机访问）；是否 sized、是否公共范围也与底层相同。
- ¶2 `iterator_category`：`std::get<N>(*current_)` 是右值时为 `input_iterator_tag`，原因与 [[range.transform]] 相同，老式前向迭代器要求解引用得到左值引用。
- 底层是[[g:borrowed-range|借用范围]]时它也是，因为迭代器不需要访问视图对象。这是它比 `transform` 加 lambda 多出的一个好处：`ranges::find(views::keys(m), k)` 返回真正的迭代器，而 `transform_view` 从来不是借用范围，同样的调用只能得到 `ranges::dangling`。

## 小结

| | `elements<N>`、`keys`、`values` |
|---|---|
| 适用的元素 | 标准库元组式类型：`pair`、`tuple`、`array`、`subrange`、`complex` |
| 解引用结果 | 底层是引用：分量的引用；底层是临时对象：分量的副本（分量本身是引用时仍是引用） |
| 迭代器类别、sized、公共范围 | 与底层相同（连续降为随机访问） |
| 借用范围 | 底层是时 |

<details class="fine" markdown="1"><summary>其余条文</summary>

[range.elements.view] ¶1：构造函数保存底层视图。

[range.elements.iterator] ¶4–¶7 是构造函数和 `base()`，其余各段把 `++`、`--`、`+=`、比较、相减等运算直接转发给底层迭代器。[range.elements.sentinel] 的哨位保存底层终点，比较和相减同样转发给底层。

</details>
