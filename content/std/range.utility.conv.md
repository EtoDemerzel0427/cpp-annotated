---
title: 范围转换 ranges::to
summary: C++23 的 ranges::to 把一个范围物化成容器：它按什么顺序尝试四种构造方式，怎样递归处理范围的范围，to<vector> 这种不写元素类型的形式怎样推导，以及管道形式。
status: done
covers: *
since: c++23
papers: P1206R7
related: range.utility, range.adaptor.object, range.req, range.access, containers, container.reqmts, func.require
tags: 标准库, 范围, ranges::to, 容器
updated: 2026-10-19
---

!!! tldr
    - `ranges::to<C>(r, args...)` 或 `r | ranges::to<C>(args...)` 用范围 `r` 的元素构造一个 `C`，`C` 不能是视图。
    - 依次尝试：直接用范围构造，用 `from_range` 标签构造，用一对迭代器构造，默认构造后逐个追加（能预留时先 `reserve`）。
    - 元素不能直接放进 `C` 而本身又是范围时，`to` 对每个元素递归调用，所以能把范围的范围转成 `vector<vector<int>>` 或 `vector<string>`。
    - `to<std::vector>()` 不写元素类型，靠容器的类模板实参推导得到完整类型。
    - 管道形式必须带括号：`to<std::vector>()`；额外实参按值保存在闭包里。

## 从视图到容器

视图是惰性的，最终常常要变成一个容器。C++20 只能借助迭代器对：

<div class="compare" markdown="1">

```cpp
// C++20
auto r = v | std::views::take_while(pred);
std::vector<int> out(r.begin(), r.end());
// error: take_while_view 不是 common_range，
// begin 和 end 的类型不同
```

```cpp
// C++23
auto out = v
  | std::views::take_while(pred)
  | std::ranges::to<std::vector>();
```

</div>

C++23 的 `ranges::to`（[[P1206R7]]）把这一步变成管道的最后一级。下面的例子展示了它的几种用法：

```cpp run ok
#include <deque>
#include <list>
#include <ranges>
#include <set>
#include <string>
#include <vector>
#include <cstdio>
int main() {
  auto sq = std::views::iota(1, 5)
          | std::views::transform([](int i) { return i * i; });
  auto v = sq | std::ranges::to<std::vector>();          // 推导为 vector<int>
  auto d = std::ranges::to<std::deque<long>>(sq);        // 元素类型转换
  auto s = sq | std::ranges::to<std::set<int, std::greater<>>>();

  std::vector<std::list<int>> ll{{1, 2}, {3}};           // 范围的范围：逐层递归
  auto vv = ll | std::ranges::to<std::vector<std::vector<int>>>();

  auto tw = std::views::iota(0)                          // 不是 common_range
          | std::views::take_while([](int i) { return i < 3; });
  auto w = tw | std::ranges::to<std::vector<int>>();     // 默认构造后逐个追加

  auto str = std::ranges::to<std::string>(std::views::repeat('x', 3));
  std::printf("%zu %zu %d %zu %zu %s\n",
              v.size(), d.size(), *s.begin(), vv[0].size(), w.size(), str.c_str());
  // 4 4 16 2 3 xxx
}
```

## 四种构造方式 [range.utility.conv.general]

¶1 转换函数用以下方式之一从范围构造对象（通常是容器）：接受范围的构造函数；带 `from_range_t` 标签的构造函数，这是 C++23 给所有标准容器加上的；接受一对迭代器的构造函数；或者默认构造后把元素逐个插入。

¶3–¶5 为了描述最后一种方式，标准定义了三个仅用于说明的工具：

- *reservable-container*：`C` 是 `sized_range`，并且有 `reserve(n)`、`capacity()` 和 `max_size()`；
- *container-appendable*：能用 `emplace_back`、`push_back`、`emplace_hint(c.end(), x)`、`insert(c.end(), x)` 之一追加元素；
- *container-append*：按上面的顺序选第一个可用的方式追加一个元素。

### 选择顺序 [range.utility.conv.to]

```cpp
template<class C, input_range R, class... Args> requires (!view<C>)
  constexpr C to(R&& r, Args&&... args);
```

¶1 `C` 必须是 cv 非限定的类类型。约束 `!view<C>` 表示 `to` 只用来物化：`to<std::string_view>(r)` 不被接受，视图应当由视图适配器构造。

¶2 返回值按下面的规则构造。

¶2.1 如果 `C` 不是 `input_range`，或者 `r` 的元素可以转换为 `C` 的元素类型（`convertible_to<range_reference_t<R>, range_value_t<C>>`），依次尝试：

| 条款 | 条件 | 做法 |
|---|---|---|
| ¶2.1.1 | `C` 可以由 `R, Args...` 构造 | `C(std::forward<R>(r), args...)` |
| ¶2.1.2 | `C` 可以由 `from_range_t, R, Args...` 构造 | `C(from_range, std::forward<R>(r), args...)` |
| ¶2.1.3 | `R` 是 `common_range`，迭代器有 C++17 风格的 `iterator_category`，且 `C` 可以由迭代器对加 `Args...` 构造 | `C(ranges::begin(r), ranges::end(r), args...)` |
| ¶2.1.4 | `C` 可以由 `Args...` 构造，且可以追加元素 | 默认构造，能预留时先预留，再逐个追加 |
| ¶2.1.5 | 以上都不满足 | 非良构 |

¶2.2 否则，如果 `r` 的元素本身是范围，就对每个元素递归调用 `to<range_value_t<C>>`，再把结果交给外层的 `to<C>`：

```cpp
to<C>(ref_view(r) | views::transform([](auto&& elem) {
  return to<range_value_t<C>>(std::forward<decltype(elem)>(elem));
}), std::forward<Args>(args)...);
```

¶2.3 再否则，程序非良构。

¶2 例 1 说明了递归的用途：

```cpp
string_view str = "the quick brown fox";
auto words = views::split(str, ' ') | to<vector<string>>();
// {"the", "quick", "brown", "fox"}
```

`split` 的每个元素是一个表示一段字符的 `subrange`，它不能隐式转换为 `string`，但它本身是范围，于是走 ¶2.2：对每个元素调用 `to<string>`，后者再走 ¶2.1.2 的 `from_range` 构造。

### 几处细节

¶2.1.3 检查的是 C++17 风格的 `iterator_category`，因为旧容器的迭代器对构造函数是按 *Cpp17InputIterator* 要求写的。C++20 视图的迭代器不一定定义它，例如 `transform_view` 的底层不是 `forward_range` 时，迭代器就没有 `iterator_category`。这时 ¶2.1.3 不适用，退到 ¶2.1.4。

¶2.1.4 的预留条件是 `approximately_sized_range<R> && reservable-container<C>`，预留的大小来自 `ranges::reserve_hint(r)`。C++23 原来的写法是 `sized_range` 和 `ranges::size`；当前草案放宽成只要能给出元素个数的估计即可 {{c++26}}，这样大小不确定但可以估计上界的范围也能预先分配。

¶2.1 开头的条件 `C` 不是 `input_range` 允许转换成不是范围的类型，只要它能由范围构造，例如一个接受范围的统计累加器类。

## 不写元素类型：to<vector>（¶3–¶5）

```cpp
template<template<class...> class C, input_range R, class... Args>
  constexpr auto to(R&& r, Args&&... args);
```

`to<std::vector>(r)` 只给了类模板，需要推导出完整的 `vector<int>`。¶4 定义 *DEDUCE_EXPR*，依次尝试三个表达式，用的都是容器的类模板实参推导（CTAD）：

1. `C(declval<R>(), declval<Args>()...)`；
2. `C(from_range, declval<R>(), declval<Args>()...)`；
3. `C(declval<input-iterator>(), declval<input-iterator>(), declval<Args>()...)`。

¶3 第 3 项中的 *input-iterator* 是一个仅用于说明的迭代器类型，它满足 *Cpp17InputIterator* 的语法要求，`value_type` 为 `range_value_t<R>`，用来套用容器的迭代器对推导指引。

¶5 推导出的类型记作 `decltype(DEDUCE_EXPR)`，结果就是 `to<decltype(DEDUCE_EXPR)>(r, args...)`。例如 `views::zip(keys, values) | to<std::map>()` 的元素是 `tuple`，`map` 的迭代器对推导指引从 `tuple` 的第 0、1 个元素得到键和值的类型，本机 Clang 23 推导出 `map<int, std::string>`（键为 `int`、值为 `string` 时）。

## 管道形式 [range.utility.conv.adaptors]

```cpp
template<class C, class... Args> requires (!view<C>)
  constexpr auto to(Args&&... args);
template<template<class...> class C, class... Args>
  constexpr auto to(Args&&... args);
```

¶2 不带范围实参调用 `to` 时，返回一个范围适配器闭包对象（[[range.adaptor.object]]），所以可以写在 `|` 右边。闭包把 `args` 以 `decay_t<Args>` 类型按值保存，调用时执行 `to<C>(r, bound_args...)`（[[func.require]]）。因此 `r | to<std::vector>(alloc)` 会把分配器复制进闭包。

`to` 本身不是范围适配器，它不返回视图，但它返回的闭包可以和其他闭包组合：`auto pipeline = views::filter(p) | ranges::to<std::vector>();` 得到一个先过滤再物化的闭包。

<div class="compare" markdown="1">

```cpp run error
#include <ranges>
#include <string_view>
auto x = std::views::iota(0, 3)
  | std::ranges::to<std::string_view>();
// error: C 不能是视图
int main() {}
```

```cpp run error
#include <ranges>
#include <vector>
auto x = std::views::iota(0, 3)
  | std::ranges::to<std::vector>;
// error: 少了 ()，右边是函数模板
int main() {}
```

</div>

!!! pitfall "to<vector> 忘了括号"
    `r | std::ranges::to<std::vector>` 不能编译。`to<std::vector>` 是函数模板的名字，不是对象，必须调用它得到闭包：`to<std::vector>()`。`views::join` 则不同，它本身就是闭包对象，不带括号。
