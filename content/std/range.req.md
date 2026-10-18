---
title: 范围要求
summary: range、borrowed_range、approximately_sized_range、sized_range 以及 input…contiguous/common/viewable/constant_range 的语法定义与语义要求：begin/end 摊还 O(1) 且不修改、forward 时保持相等性；借用的精确含义与 enable_borrowed_range；disable_sized_range；viewable_range 为什么排除 const 右值与 initializer_list。
status: done
covers: range.req.general, range.range, range.approximately.sized, range.sized, range.refinements
since: c++20
papers: P0896R4, P2017R1, P2415R2, P2278R4
related: range.access, range.view, range.all, range.dangling, iterator.concepts, iterator.requirements.general, concepts.equality, namespace.std, ranges
tags: 标准库, 范围, 概念, 借用范围
updated: 2026-10-18
---

[range.req] 把"范围"从直觉变成了一组**概念**。它们的语法部分由 [[range.access]] 的 CPO 支撑，语义部分（"models only if …"）则是程序员对库作出的承诺——违反了，程序的行为不再由标准保证（[[res.on.requirements]]）。视图概念 `view` 篇幅较大，单独见 [[range.view]]。

## 总览（[range.req.general]）

¶1 范围让程序能"一致地"操作各种数据结构的元素：`ranges::begin` 返回建模 `input_or_output_iterator` 的对象，`ranges::end` 返回与之构成 `sentinel_for` 的对象。¶2–¶3 给出概念家族：

```text
range ──┬─ approximately_sized_range ── sized_range
        ├─ input_range ── forward_range ── bidirectional_range ── random_access_range ── contiguous_range
        ├─ output_range<R, T>
        ├─ common_range        （begin/end 同类型）
        ├─ borrowed_range      （迭代器不随对象一起失效）
        ├─ view                （见 [range.view]）
        ├─ viewable_range      （能安全转成 view）
        └─ constant_range      （元素不可修改）
```

## `range`（[range.range] ¶1–¶3）

术语见 [[g:range-concept]]。

```cpp
template<class T>
  concept range = requires(T& t) {
    ranges::begin(t);         // sometimes equality-preserving (see below)
    ranges::end(t);
  };
```

注意 `requires(T& t)`：语法检查总是**在左值上**进行。因此 `range<vector<int>>` 为 `true`——尽管 `ranges::begin(vector<int>{})` 非良构——它问的是"这种类型的对象（作为左值）能否被迭代"。右值能否直接交给 `begin` 由 `borrowed_range` 另行回答。

¶2 语义要求，对 `decltype((t))` 为 `T&` 的表达式 `t`：

- ¶2.1 `[ranges::begin(t), ranges::end(t))` 表示一个范围（[[iterator.requirements.general]]）；
- ¶2.2 `begin` 与 `end` 都是**摊还常数时间**且**不修改**（non-modifying）的；
- ¶2.3 若 `begin` 的类型建模 `forward_iterator`，则 `ranges::begin(t)` **保持相等性**（[[concepts.equality]]）。

!!! std
    both ranges::begin(t) and ranges::end(t) are amortized constant time and non-modifying

    `begin` 和 `end` 都必须是摊还常数时间、且不修改范围。

这一句是整章"缓存"设计的根源。`filter_view::begin()` 要线性地找第一个满足谓词的元素，为了满足"摊还 O(1)"，它只能在第一次调用时找、然后缓存（[[range.filter]]）。而"不修改"指的是**不修改可观察的范围内容**——往视图里的 *non-propagating-cache* 写缓存不算修改元素序列。

¶3 注 1 解释 ¶2.3 的意义：对 forward 范围，多次调用 `begin`/`end` 得到相等的结果，所以可以把同一个范围交给多个算法、做多趟遍历。**对输入范围则不要求**——再次调用 `begin` 可能得到不同的值，甚至"不是良定义的"。`std::generator` 就是例子：对同一个 generator 调用两次 `begin` 是未定义行为（[[coro.generator]]）。

## `borrowed_range` 与 `enable_borrowed_range`（[range.range] ¶4–¶7）

```cpp
template<class T>
  concept borrowed_range =
    range<T> && (is_lvalue_reference_v<T> || enable_borrowed_range<remove_cvref_t<T>>);
```

¶4 语义：令 `U` 为 `T` 去掉右值引用后的类型，给定 `U` 类型的变量 `u`，`T` 建模 `borrowed_range` 仅当**从 `u` 获得的迭代器的有效性不与该变量的生命周期绑定**。

术语见 [[g:borrowed-range]]。直观地说：

- 任何**左值引用**类型都是借用的——变量 `u` 是引用，它"死"了不影响被引用的对象；
- `string_view`、`span`、`subrange`、`ref_view`、`iota_view`、`empty_view` 是借用的——迭代器指向的是**别人**的存储（或者迭代器自带值）；
- `vector`、`string`、`owning_view`（底层非借用时）不是借用的——销毁它们，迭代器就悬垂；
- `filter_view`、`transform_view` 不是借用的——它们的迭代器保存着指向**视图对象本身**的指针（要用里面的谓词/函数）。

¶5 注 2：因此形参类型建模 `borrowed_range` 的函数，可以安全地返回从该形参得到的迭代器——这正是 [[range.dangling]] 的 `borrowed_iterator_t` 机制的基础。

¶6 用户可以为**cv 非限定的程序定义类型**特化 `enable_borrowed_range`（[[namespace.std]]），特化必须可用于常量表达式且类型为 `const bool`。¶7 例 1：`subrange` 的每个特化都通过特化 `enable_borrowed_range` 为 `true` 建模 `borrowed_range`。

!!! history "条件借用"
    C++20 的初版只有少数视图是借用的。[[P2017R1]]（"Conditionally borrowed ranges"，作为 C++20 DR）让 `take_view`、`drop_view`、`reverse_view` 等"只是转发底层迭代器"的视图在底层借用时也借用。完整清单见 [[ranges]] 的头文件概要一节。

!!! pitfall "特化 `enable_borrowed_range` 是一份承诺"
    编译器不会验证你的类型是否真的满足 ¶4。若为一个持有 `std::vector` 的类型特化为 `true`，`ranges::find(make_it(), x)` 就会返回指向已销毁临时量的迭代器——这是{{ub}}，而且标准库的所有防护都会被绕过。

## `approximately_sized_range`（[range.approximately.sized]）{{c++26}}

```cpp
template<class T>
  concept approximately_sized_range =
    range<T> && requires(T& t) { ranges::reserve_hint(t); };
```

¶2 语义：`reserve_hint(t)` 摊还 O(1)、不修改 `t`、值非负且可由 `range_difference_t<T>` 表示；若迭代器是 forward 的，则无论是否先调用过 `begin` 都良定义。它只是一个**估计**——用来让 `ranges::to` 等预先 `reserve`，结果不必等于实际元素数。

## `sized_range` 与 `disable_sized_range`（[range.sized]）

（[[g:sized-range]]）

```cpp
template<class T>
  concept sized_range =
    approximately_sized_range<T> && requires(T& t) { ranges::size(t); };
```

（C++26 的措辞让 `sized_range` 细化 `approximately_sized_range`；由于 `reserve_hint` 在 `size` 可用时就退化为 `size`，这不会让任何旧的 `sized_range` 失格。）

¶2 语义：

- ¶2.1 `ranges::size(t)` 摊还 O(1)、不修改 `t`，并**等于** `ranges::distance(ranges::begin(t), ranges::end(t))`；
- ¶2.2 若迭代器是 forward 的，`size(t)` 无论在 `begin` 之前还是之后调用都良定义。注 1：对非 forward 的 `sized_range`，`size` 可能只在第一次 `begin` **之前**才良定义。

¶3 用户可为程序定义类型特化 `disable_sized_range`。¶4 注 2：它允许"**满足**但不**建模** `sized_range`"的类型与库协作——典型是一个 `size()` 成员是 O(n) 的类型。特化为 `true` 后 `ranges::size` 会跳过成员和 ADL 版本（[[range.access]]）。

## 其他细化（[range.refinements]）

### 迭代器强度系列（¶1–¶3）

```cpp
template<class R, class T>
  concept output_range = range<R> && output_iterator<iterator_t<R>, T>;
template<class T>
  concept input_range = range<T> && input_iterator<iterator_t<T>>;
// forward_range / bidirectional_range / random_access_range 同理逐级细化
template<class T>
  concept contiguous_range =
    random_access_range<T> && contiguous_iterator<iterator_t<T>> &&
    requires(T& t) {
      { ranges::data(t) } -> same_as<add_pointer_t<range_reference_t<T>>>;
    };
```

¶3 `contiguous_range` 的语义要求：`to_address(ranges::begin(t)) == ranges::data(t)`。注意 `data` 的返回类型必须**恰好**是 `add_pointer_t<range_reference_t<T>>`——所以 `vector<bool>` 不是连续范围（它的引用是代理类），`const vector<int>` 的 `data()` 返回 `const int*`，与 `const int&` 吻合。

### `common_range`（¶4）

（[[g:common-range]]）

```cpp
template<class T>
  concept common_range = range<T> && same_as<iterator_t<T>, sentinel_t<T>>;
```

标准容器都是 common range。很多视图不是（`take_while`、无界的 `iota`、`istream`……）。旧式接口（`vector(first, last)` 构造、C++17 算法）需要 common range，可以用 `views::common` 转换（[[range.common]]）。

### `viewable_range`（¶5–¶6）

（[[g:viewable-range]]）

```cpp
template<class T>
  concept viewable_range =
    range<T> &&
    ((view<remove_cvref_t<T>> && constructible_from<remove_cvref_t<T>, T>) ||
     (!view<remove_cvref_t<T>> &&
      (is_lvalue_reference_v<T> || (movable<remove_reference_t<T>> && !is-initializer-list<T>))));
```

它恰好刻画了 `views::all` 能处理的实参（[[range.all]]）：

| 实参 | 是否 viewable | `views::all` 的结果 |
|---|---|---|
| 视图（可从实参构造） | ✓ | 视图自身的副本 |
| 非视图左值 `vector<int>&` | ✓ | `ref_view` |
| 非视图可移动右值 `vector<int>&&` | ✓ | `owning_view`（移进来） |
| `const vector<int>&&` | ✗ | ——不能从 const 右值移动 |
| 右值 `initializer_list<int>` | ✗ | ——它只是借用着一块临时数组，`owning_view` 一个 `initializer_list` 必然悬垂 |
| 只能移动的视图的左值 | ✗ | ——`constructible_from<V, V&>` 为假，不能复制 |

```cpp run ok
#include <ranges>
#include <span>
#include <string>
#include <string_view>
#include <vector>
#include <initializer_list>
namespace r = std::ranges;
using V = std::vector<int>;
static_assert(r::view<std::string_view> && r::view<std::span<int>>);
static_assert(!r::view<V>);                                   // 复制是 O(N)
static_assert(r::borrowed_range<std::string_view> && r::borrowed_range<V&>);
static_assert(!r::borrowed_range<V> && !r::borrowed_range<std::string>);
static_assert(r::viewable_range<V> && r::viewable_range<V&>);  // 右值容器 -> owning_view
static_assert(!r::viewable_range<const V>);                    // const 右值不能移动
static_assert(!r::viewable_range<std::initializer_list<int>>); // 右值 init-list 被排除
static_assert(std::same_as<std::views::all_t<V&>, r::ref_view<V>>);
static_assert(std::same_as<std::views::all_t<V>, r::owning_view<V>>);
static_assert(std::same_as<std::views::all_t<std::string_view&>, std::string_view>);
static_assert(r::borrowed_range<r::owning_view<V>> == false);
static_assert(r::borrowed_range<decltype(std::declval<V&>() | std::views::take(2))>);
static_assert(!std::copyable<r::owning_view<V>>);              // 只能移动
int main() {}
```

### `constant_range`（¶7）

（[[g:constant-range]]）

```cpp
template<class T>
  concept constant_range = input_range<T> && constant-iterator<iterator_t<T>>;
```

C++23（[[P2278R4]]）引入：元素**不可通过迭代器修改**的范围。*constant-iterator* 要求迭代器的 `iter_const_reference_t` 与 `iter_reference_t` 相同。`const vector<int>&` 是，`span<int>` 不是（浅 const），`views::as_const` 能把后者变成前者（[[range.as.const]]）。

### *sized-random-access-range*（¶8）

仅用于说明：`random_access_range<T> && sized_range<T>`。注 1：它用来约束第 26 章中一些带执行策略的（并行）算法的范围重载——并行切分需要随机访问和事先已知的长度。

## 常见误区

!!! pitfall "\"满足\"不等于\"建模\""
    `range<T>` 为 `true` 只说明语法上能调用。若 `begin()` 是 O(n)、`size()` 与实际元素数不一致、forward 范围的 `begin()` 两次返回不同位置，类型只是**满足**而没有**建模**这些概念，把它交给标准库组件的行为不受保证（[[concepts]] 对"满足/建模"有详细讨论）。

## 思考题

<details markdown="1">
<summary>1. `range<const std::ranges::filter_view<…>>` 为什么通常是 false？这违反了 ¶2.2 的"non-modifying"吗？</summary>

`filter_view` 的 `begin()` 要缓存结果，于是没有声明 `const` 版本（只在底层为"仅输入"时才有 `const begin`，见 [[range.filter]]）；`requires(T& t) { ranges::begin(t); }` 中 `t` 是 `const filter_view&`，调不了非 const 成员，于是不满足。这不违反 ¶2.2：缓存不改变范围所表示的元素序列，"non-modifying" 指的是可观察的序列，而不是对象的每一个比特。
</details>

<details markdown="1">
<summary>2. `borrowed_range<std::vector<int>&>` 为 true，那么 `ranges::find(get_ref(), 0)`（`get_ref` 返回某全局 vector 的引用）会返回 `dangling` 吗？</summary>

不会。实参类型是 `vector<int>&`，左值引用一律借用，返回真正的迭代器。只有右值且非借用（如函数按值返回的 `vector`）才得到 `dangling`。至于那个全局 vector 是否还活着，是程序员的责任。
</details>

## 小结

| 概念 | 语法核心 | 关键语义 |
|---|---|---|
| `range` | 左值上可调 `begin`/`end` | 二者摊还 O(1)、不修改；forward 时 `begin` 保持相等性 |
| `borrowed_range` | 左值引用或 `enable_borrowed_range` | 迭代器有效性不依赖范围对象的生命周期 |
| `approximately_sized_range` {{c++26}} | `reserve_hint` | O(1) 的非负估计 |
| `sized_range` | `ranges::size` | O(1)、等于 `distance(begin, end)`；可用 `disable_sized_range` 退出 |
| `common_range` | `iterator_t == sentinel_t` | —— |
| `viewable_range` | 视图、或非视图的左值/可移动非 init-list 右值 | 能被 `views::all` 安全包装 |
| `constant_range` | 常量迭代器 | 元素不可经迭代器修改 |
