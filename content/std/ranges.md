---
title: 范围库
summary: 第 25 章导读——"范围 = 迭代器 + 哨位"的抽象，CPO 组成的访问层、概念组成的要求层、视图/工厂/适配器组成的组合层，以及惰性求值、begin() 缓存、借用与悬垂这几条贯穿全章的设计主线。
status: done
covers: ranges.general, ranges.syn
since: c++20
papers: P0896R4, P2415R2, P2387R3, P1206R7
related: range.access, range.req, range.view, range.utility, range.factories, range.adaptors, coro.generator, iterators, iterator.concepts, concepts, customization.point.object, stmt.ranged
tags: 标准库, 范围, 视图, 导读
updated: 2026-10-18
---

C++98 的算法接口是一对迭代器：`std::sort(v.begin(), v.end())`。这有三个老毛病：

1. **啰嗦且易错**：两个迭代器可以来自不同容器，编译器不会说什么；
2. **首尾必须同类型**：要表达"遇到 `'\0'` 为止"或"无限序列"，只能先数出长度或者造一个假的尾迭代器；
3. **不可组合**：想"过滤再变换再取前 10 个"，要么写手工循环，要么造中间容器。

C++20 的 Ranges（[[P0896R4]]，"One Ranges Proposal"）在第 25 章 [ranges] 里系统地回答了这三个问题。本章与第 24 章迭代器库（[[iterators]]、[[iterator.concepts]]）和第 26 章算法库里的 `std::ranges::` 算法是一个整体：迭代器概念定义"能怎样走"，本章定义"一段可以走的东西是什么"，算法再把两者用起来。

## 本章的版图（[ranges.general]）

¶1–¶2 本章描述"处理元素范围的组件"，按表 84 分为六块。按**抽象层次**来读更清楚：

| 层次 | 子条款 | 内容 | 头文件 |
|---|---|---|---|
| 访问层 | [[range.access]] | `ranges::begin/end/size/data/empty…` 等定制点对象 | `<ranges>`（也随 `<iterator>` 提供） |
| 要求层 | [[range.req]]、[[range.view]] | `range`、`sized_range`、`view`、`borrowed_range`、`viewable_range`……一组概念 | `<ranges>` |
| 工具层 | [[range.utility]]、[[range.subrange]]、[[range.dangling]]、[[range.utility.conv]] | `view_interface`、`subrange`、`dangling`、`ranges::to` | `<ranges>` |
| 来源 | [[range.factories]]、[[range.iota]] | 凭空造视图：`empty`、`single`、`iota`、`repeat`、`istream` | `<ranges>` |
| 组合层 | [[range.adaptors]] 及各视图页 | `filter`、`transform`、`take`、`join`、`zip`…… 与管道 `|` | `<ranges>` |
| 协程 | [[coro.generator]] | `std::generator`：用协程写出一个 `input_range` | `<generator>` |

## 核心抽象：迭代器 + 哨位

范围（range）在标准里没有一个"基类"，它只是一个**概念**（[[range.range]]）：

```cpp
template<class T>
  concept range = requires(T& t) { ranges::begin(t); ranges::end(t); };
```

`ranges::begin` 必须给出一个迭代器，`ranges::end` 给出一个**哨位**（sentinel）——它只需要能与迭代器比较相等，类型可以与迭代器不同（[[iterator.concept.sentinel]]）。这一个放宽解决了上面的第 2 个问题：C 字符串的尾可以是"一个与 `char*` 比较时检查 `*p == '\0'` 的空类"，无限序列的尾可以是 `unreachable_sentinel_t`（永远不相等）。

在此之上，标准用一串**细化概念**刻画范围的能力：`input_range ⊂ forward_range ⊂ bidirectional_range ⊂ random_access_range ⊂ contiguous_range`（对应迭代器的强度），加上正交的 `sized_range`（能 O(1) 求长度）、`common_range`（首尾同类型）、`borrowed_range`（迭代器不随范围对象一起失效）、`view`（复制/移动/析构廉价）等。见 [[range.req]]。

## 三条贯穿全章的设计主线

### 1. 定制点对象（CPO）取代"两步式 ADL"

`ranges::begin(r)` 不是函数，而是一个**定制点对象**（[[g:customization-point-object]]，[[customization.point.object]]）：一个按固定顺序尝试"数组 → 成员 `.begin()` → ADL 找到的 `begin(t)`"并**检查返回类型是迭代器**的函数对象。这让"一个类型是不是 range"可以被概念精确判定，也让 SFINAE 友好的失败成为可能。见 [[range.access]]。

### 2. 视图：惰性、廉价复制、可组合

**视图**（view）是"移动 O(1)、析构代价与元素数无关"的范围（[[range.view]]），典型如 `string_view`、`span`、以及所有适配器的结果。适配器（[[range.adaptors]]）接受一个范围、返回一个视图，**不做任何计算**；元素在迭代时才被逐个算出。用管道运算符组合：

```cpp run ok
#include <ranges>
#include <vector>
#include <cstdio>
int main() {
  std::vector<int> v{1, 2, 3, 4, 5, 6, 7, 8};
  auto r = v | std::views::filter([](int x) { return x % 2 == 0; })
             | std::views::transform([](int x) { return x * x; })
             | std::views::take(3);
  for (int x : r) std::printf("%d ", x);   // 4 16 36
  std::puts("");
}
```

构造 `r` 的那一行没有访问任何元素；`for` 循环每走一步，`take` 向 `transform` 要一个元素，`transform` 向 `filter` 要一个，`filter` 在 `v` 上前进直到遇到偶数。

### 3. 生命周期：借用、悬垂与 `owning_view`

视图通常**不拥有**元素，因此"视图比底层数据活得久"是本章最大的一类 bug 来源。标准在类型层面做了三重防护：

- 算法对右值的**非借用**范围返回 `ranges::dangling`，而不是会悬垂的迭代器（[[range.dangling]]）；
- `views::all` 对左值生成 `ref_view`（引用），对右值容器生成 `owning_view`（把容器移进视图里），见 [[range.all]]；
- `viewable_range` 拒绝无法安全转为视图的东西（如 `const` 右值容器、右值 `initializer_list`）。

但这些只能挡住"在一个表达式里"的错误。把视图存起来、从函数里返回、跨越修改底层容器的操作继续使用，都可能悬垂或失效——各视图页的"坑点"小节会反复回到这个主题。

### 附：begin() 的缓存

[[range.range#2]] 要求 `ranges::begin` **摊还常数时间**。`filter_view` 的第一个元素要线性查找才能确定，于是标准规定它在第一次 `begin()` 时**缓存**结果。同样的缓存出现在 `drop_view`、`drop_while_view`、`reverse_view`、`split_view`、`chunk_by_view`、`slide_view` 等处。缓存带来了两条反直觉的后果：

- 这些视图的 `begin()` **不是 `const` 成员**（要写缓存），所以 `const` 的 `filter_view` 不是 `range`，`void f(const auto& r)` 收不了它；
- 第一次 `begin()` 之后再修改底层数据，视图可能给出**陈旧**的结果。

详见 [[range.filter]]、[[range.drop]]。

## 头文件概要（[ranges.syn]）

`<ranges>` 的概要里有几处值得 language lawyer 留意的细节：

- **"mostly freestanding"**：大部分组件在独立实现中可用；`basic_istream_view` / `istream_view` / `views::istream` 和 `elements_of` 标注为 hosted，`view_interface` 是"partially freestanding"（其 `at()` 会抛 `out_of_range`，标为 freestanding-deleted）。
- **CPO 放在 `inline namespace unspecified` 中**：`ranges::begin` 等变量与 `std::ranges` 里视图迭代器声明的隐藏友元（如 `iter_move`）可能同名；内联命名空间避免了"同一命名空间中变量与函数同名"的冲突。原理见 [[conventions]]。
- **`enable_borrowed_range` 的特化**：`subrange`、`empty_view`、`iota_view`、`ref_view` 恒为 `true`；`owning_view`、`take_view`、`drop_view`、`drop_while_view`、`common_view`、`reverse_view`、`as_const_view`、`as_rvalue_view`、`elements_view`、`enumerate_view`、`zip_view`（全部为借用时）、`adjacent_view`、`chunk_view`（且须为 forward）、`slide_view`、`stride_view`、`as_input_view` 则"继承"底层视图的借用性。不在此列的（如 `filter_view`、`transform_view`）一律不是借用范围——因为它们的迭代器回指视图对象本身（要访问谓词/函数）。
- **¶1–¶2 *make-unsigned-like-t* / *to-unsigned-like* / *make-signed-like-t***：本章到处出现的"整数类类型"的有/无符号对应（[[iterator.concept.winc]]）。`ranges::size` 返回无符号、`ranges::ssize` 返回有符号，就是靠它们定义的。
- **`from_range_t` / `from_range`**：C++23 起容器的"从范围构造"标签（[[P1206R7]]），`ranges::to` 会优先使用它。

```cpp run ok
#include <ranges>
#include <vector>
#include <span>
static_assert(std::ranges::enable_borrowed_range<std::ranges::iota_view<int, int>>);
static_assert(std::ranges::borrowed_range<std::span<int>>);
using F = decltype(std::declval<std::vector<int>&>()
                   | std::views::filter([](int) { return true; }));
static_assert(!std::ranges::borrowed_range<F>);   // filter_view 的迭代器指回视图本身
int main() {}
```

## 版本演进一览

!!! history "Ranges 的三次扩张"
    - **C++20**（[[P0896R4]]）：概念、CPO、`subrange`、`dangling`、`view_interface`、工厂 `empty/single/iota/istream`、适配器 `all/filter/transform/take/take_while/drop/drop_while/join/split/counted/common/reverse/elements/keys/values`。此后多篇论文以缺陷报告（DR）形式回溯修改了 C++20：视图不再要求可默认构造（[[P2325R3]]）、引入 `owning_view` 并重定义"视图"（[[P2415R2]]）、`split` 改为面向字符串的新语义并把旧的改名为 `lazy_split`（[[P2210R2]]）。
    - **C++23**：`ranges::to`（[[P1206R7]]）、用户自定义管道（`range_adaptor_closure`，[[P2387R3]]）、`zip` 家族与 `adjacent`（[[P2321R2]]）、`chunk`/`slide`（[[P2442R1]]）、`chunk_by`（[[P2443R1]]）、`join_with`（[[P2441R2]]）、`stride`（[[P1899R3]]）、`cartesian_product`（[[P2374R4]]）、`enumerate`（[[P2164R9]]）、`as_rvalue`（[[P2446R2]]）、`repeat`（[[P2474R2]]）、`as_const` 与 `cbegin` 返回常量迭代器（[[P2278R4]]），以及 `std::generator`（[[P2502R2]]）。
    - **C++26**：`concat`（[[P2542R8]]）、`optional` 成为视图（[[P3168R2]]）、`views::indices`、`cache_latest`、`as_input`、`approximately_sized_range` 与 `ranges::reserve_hint`，以及 `filter_view` 对"仅输入"底层的 `const` 迭代支持等较新的措辞调整。

## 实现现状（本站验证环境）

本站示例使用 Clang 23 + libc++ 验证。截至编写时，libc++ **尚未提供**：`views::as_const`、`views::chunk`、`views::slide`、`views::cartesian_product`、`views::cache_latest`、`views::as_input`、`ranges::reserve_hint`、`<generator>`，`ranges::cbegin` 等也尚未按 [[P2278R4]] 返回常量迭代器，`optional` 也还不是 `range`。涉及这些设施的示例在对应页面中注明"按标准编写、未经本地运行验证"。

## 阅读路线

1. 先读 [[range.access]] 与 [[range.req]]：搞清楚"什么是 range"是被 CPO 精确定义的；
2. 再读 [[range.view]] 与 [[range.all]]：视图的语义要求、`ref_view` 与 `owning_view`；
3. [[range.adaptors]]：适配器对象、闭包对象与管道 `|` 的精确规则；
4. 重点视图：[[range.filter]]（缓存与 const）、[[range.transform]]、[[range.join]]、[[range.split]]、[[range.zip]]；
5. 工具：[[range.subrange]]、[[range.dangling]]、[[range.utility.conv]]（`ranges::to`）。
