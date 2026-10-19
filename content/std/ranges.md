---
title: 范围库
summary: 第 25 章导读：范围是迭代器加哨位，ranges::begin 等定制点对象负责访问，一组概念刻画能力，视图和适配器负责惰性组合；贯穿全章的是惰性求值、begin() 缓存和悬垂这几个问题。
status: done
covers: ranges.general, ranges.syn
since: c++20
papers: P0896R4, P2415R2, P2387R3, P1206R7
related: range.access, range.req, range.view, range.utility, range.factories, range.adaptors, coro.generator, iterators, iterator.concepts, concepts, customization.point.object, stmt.ranged
tags: 标准库, 范围, 视图, 导读
updated: 2026-10-19
---

!!! tldr
    - 范围（range）不是一个基类，而是一个概念：能用 `ranges::begin` 得到迭代器、用 `ranges::end` 得到哨位的类型。哨位只需能与迭代器比较，类型可以不同。
    - `ranges::begin`、`ranges::size` 等是定制点对象：按固定顺序查找实现，并检查结果类型。
    - 视图是复制和移动都廉价的范围；适配器返回视图，不立即计算，元素在迭代时才逐个算出。
    - 视图通常不拥有元素。标准用 `dangling`、`owning_view` 等挡住一部分悬垂，但存下来的视图仍可能悬垂或给出陈旧结果。
    - 本机 libc++ 还缺 `views::as_const`、`views::chunk`、`views::slide`、`<generator>` 等，相关例子在各页注明。

## 范围库要解决的问题

C++98 的算法接口是一对迭代器，例如 `std::sort(v.begin(), v.end())`。这有三个问题：

1. 两个迭代器可以来自不同的容器，编译器发现不了；
2. 首尾必须是同一类型，要表达遇到 `'\0'` 为止或者无限序列，只能先数出长度，或者造一个假的尾迭代器；
3. 不能组合，想先过滤、再变换、再取前 3 个，要么手写循环，要么造中间容器。

C++20 的范围库（[[P0896R4]]）回答了这三个问题：

```cpp run ok
#include <cstdio>
#include <ranges>
#include <vector>

int main() {
  std::vector<int> v{1, 2, 3, 4, 5, 6, 7, 8};
  auto r = v | std::views::filter([](int x) { return x % 2 == 0; })
             | std::views::transform([](int x) { return x * x; })
             | std::views::take(3);
  for (int x : r) std::printf("%d ", x);   // 4 16 36
  std::puts("");
}
```

构造 `r` 的那一行没有访问任何元素。`for` 循环每走一步，`take` 向 `transform` 要一个元素，`transform` 向 `filter` 要一个，`filter` 在 `v` 上前进，直到遇到偶数。

本章与第 24 章的迭代器库（[[iterators]]、[[iterator.concepts]]）和第 26 章的 `std::ranges::` 算法是一体的：迭代器概念规定能怎样移动，本章规定什么是一段可以遍历的东西，算法把两者用起来。

## 本章的结构 [ranges.general]

¶1–¶2 本章描述处理元素范围的组件，表 84 把它们分成六个子条款。按抽象层次排列如下：

| 层次 | 子条款 | 内容 |
|---|---|---|
| 访问 | [[range.access]] | `ranges::begin`、`end`、`size`、`data`、`empty` 等定制点对象 |
| 要求 | [[range.req]] | `range`、`sized_range`、`view`、`borrowed_range` 等概念 |
| 工具 | [[range.utility]] | `view_interface`、`subrange`、`dangling`、`ranges::to` |
| 来源 | [[range.factories]] | 凭空生成视图：`empty`、`single`、`iota`、`repeat`、`istream` |
| 组合 | [[range.adaptors]] | `filter`、`transform`、`take`、`join`、`zip` 等，以及管道运算符 |
| 协程 | [[coro.generator]] | `std::generator`，用协程写一个输入范围，在 `<generator>` 中 |

除最后一项外，这些组件都在 `<ranges>` 中。

## 核心抽象：迭代器加哨位

`range` 是一个概念（[[range.range]]）：

```cpp
template<class T>
  concept range = requires(T& t) {
    ranges::begin(t);
    ranges::end(t);
  };
```

`ranges::begin` 给出一个迭代器，`ranges::end` 给出一个**哨位**（sentinel）。哨位只需要能与迭代器比较相等，类型可以与迭代器不同（[[iterator.concept.sentinel]]）。这就解决了上面的第 2 个问题：C 字符串的终点可以是一个空类，与 `char*` 比较时检查 `*p == '\0'`；无限序列的终点可以是 `unreachable_sentinel_t`，与任何迭代器都不相等。

在此之上，一串细化概念描述范围的能力。`input_range`、`forward_range`、`bidirectional_range`、`random_access_range`、`contiguous_range` 逐级加强，对应迭代器的强度。另有几个与之正交的：`sized_range` 能在常数时间求长度，`common_range` 首尾同类型，`borrowed_range` 的迭代器不随范围对象一起失效，`view` 的复制和移动都廉价。详见 [[range.req]]。

## 三条设计主线

### 定制点对象

`ranges::begin(r)` 不是函数，而是一个**定制点对象**（[[g:customization-point-object]]）：一个函数对象，按固定顺序尝试数组、成员 `begin()`、实参依赖查找找到的 `begin()`，并检查结果是不是迭代器（[[range.access]]）。

C++17 的泛型代码要写 `using std::begin; begin(x);` 两步，忘了 `using` 就不支持数组。定制点对象把选择逻辑收在一处，于是一个类型是不是范围可以用概念精确判断，判断失败也只是概念不满足，不会硬报错。

### 视图：惰性、廉价、可组合

**视图**（view）是移动为常数时间、析构代价与元素个数无关的范围（[[range.view]]），例如 `string_view`、`span` 和所有适配器的结果。适配器（[[range.adaptors]]）接受一个范围，返回一个视图，本身不做计算。上面例子里的管道 `|` 就是把这些适配器串起来。

### 生命周期：借用与悬垂

视图通常不拥有元素，视图比底层数据活得久是本章最常见的一类错误。标准在类型层面做了三重防护：

- 对右值的非借用范围，算法返回 `ranges::dangling` 而不是会悬垂的迭代器（[[range.dangling]]）；
- `views::all` 对左值生成引用它的 `ref_view`，对右值容器生成 `owning_view`，把容器移进视图里（[[range.all]]）；
- `viewable_range` 拒绝无法安全转成视图的东西，例如 const 的右值容器。

这些只能挡住单个表达式里的错误。把视图存起来、从函数返回，或者在修改底层容器之后继续使用，仍然可能悬垂或失效。各视图页会反复回到这个问题。

### begin() 的缓存

[[range.range#2]] 要求 `ranges::begin` 摊还常数时间。`filter_view` 要线性查找才能确定第一个元素，所以标准规定它在第一次调用 `begin()` 时缓存结果。`drop_view`、`drop_while_view`、`reverse_view`、`split_view`、`chunk_by_view`、`slide_view` 在某些情况下也这样做。缓存带来两个出人意料的后果：

- 这些视图的 `begin()` 一般不是 const 成员函数，因为要写缓存。所以底层是前向范围时，const 的 `filter_view` 不是 `range`，`void f(const auto& r)` 不能接收它；
- 第一次调用 `begin()` 之后再修改底层数据，视图可能给出陈旧的结果。

详见 [[range.filter]]、[[range.drop]]。

```cpp run ok
#include <ranges>
#include <span>
#include <vector>

using std::ranges::borrowed_range;
static_assert(borrowed_range<std::span<int>>);
static_assert(borrowed_range<std::ranges::iota_view<int, int>>);
static_assert(!borrowed_range<std::vector<int>>);

using F = decltype(std::declval<std::vector<int>&>()
                   | std::views::filter([](int) { return true; }));
// filter_view 的迭代器指回视图本身（要用里面的谓词）
static_assert(!borrowed_range<F>);
static_assert(!std::ranges::range<const F>);   // begin() 不是 const 成员
int main() {}
```

## 头文件 `<ranges>` [ranges.syn]

概要里有几处值得留意：

- **大部分在独立实现中可用。** 概要开头标注 mostly freestanding。`basic_istream_view`、`views::istream` 和 `elements_of` 标为 hosted；`view_interface` 是 partially freestanding，因为它的 `at()` 会抛 `out_of_range`。
- **定制点对象放在 `inline namespace unspecified` 里。** `ranges::begin` 这些变量可能与视图迭代器的隐藏友元（例如 `iter_move`）同名，内联命名空间避免了同一命名空间里变量与函数同名的冲突。原理见 [[customization.point.object]]。
- **哪些视图是借用范围。** 概要逐个特化了 `enable_borrowed_range`：`subrange`、`empty_view`、`iota_view`、`ref_view` 总是借用范围；`owning_view`、`take_view`、`drop_view`、`common_view`、`reverse_view`、`elements_view`、`zip_view` 等随底层视图而定。不在名单上的，例如 `filter_view`、`transform_view`，都不是借用范围，因为它们的迭代器要回到视图对象里取谓词或函数。
- **整数类类型的有无符号版本。** ¶1 定义 *`make-unsigned-like-t<X>`* 和 *`to-unsigned-like(x)`*，¶2 定义 *`make-signed-like-t<X>`*：`X` 是整数类型时就是 `make_unsigned_t`、`make_signed_t`，`X` 是整数类类型（行为像整数的类类型，[[iterator.concept.winc]]）时是同宽度的对应类型。`ranges::size` 返回无符号、`ranges::ssize` 返回有符号，就是靠它们定义的。
- **`from_range_t` 和 `from_range`。** C++23 起容器从范围构造时用的标签（[[P1206R7]]），`ranges::to` 会优先使用它。

## 演进

!!! history
    - C++20（[[P0896R4]]）引入概念、定制点对象、`subrange`、`dangling`、`view_interface`，以及 `iota`、`filter`、`transform`、`take`、`drop`、`join`、`split`、`reverse`、`elements` 等基本的工厂和适配器。此后几篇论文以缺陷报告的形式回头修改了 C++20，最重要的是引入 `owning_view` 并重新定义视图（[[P2415R2]]），让右值容器也能放进管道。
    - C++23 补上了 `ranges::to`（[[P1206R7]]）、用户自定义的管道适配器（[[P2387R3]]）、`zip`、`chunk`、`slide`、`join_with`、`enumerate`、`as_const` 等适配器，以及 `std::generator`。
    - C++26 加入了 `concat`、`views::indices`、`cache_latest`、`as_input`、`ranges::reserve_hint`，并让 `optional` 成为最多含一个元素的范围。

## 本机的实现状态

本站例子用 Clang 23 加 libc++ 验证。截至写作时，libc++ 还没有提供 `views::as_const`、`views::chunk`、`views::slide`、`views::cartesian_product`、`views::cache_latest`、`views::as_input`、`ranges::reserve_hint` 和 `<generator>`；`ranges::cbegin` 还不返回常量迭代器，`optional` 也还不是 `range`。涉及这些设施的例子在对应页面注明没有在本地运行。

## 阅读顺序

1. [[range.access]] 与 [[range.req]]：范围是怎样由定制点对象和概念精确定义的；
2. [[range.view]] 与 [[range.all]]：视图的语义要求，`ref_view` 与 `owning_view`；
3. [[range.adaptors]]：适配器对象、闭包对象和管道 `|` 的规则；
4. 重点视图：[[range.filter]]、[[range.transform]]、[[range.join]]、[[range.split]]、[[range.zip]]；
5. 工具：[[range.subrange]]、[[range.dangling]]、[[range.utility.conv]]。
