---
title: 范围工具与 view_interface
summary: [range.utility] 导读与 view_interface 的 CRTP 设计——只写 begin/end 就能免费得到 empty、operator bool、data、size、front、back、operator[]、at、cbegin；每个成员的约束为何分 const/非 const 两套；以及 simple-view、has-arrow、different-from 等贯穿适配器的说明用概念。
status: done
covers: range.utility.general, range.utility.helpers, view.interface, view.interface.general, view.interface.members
since: c++20
papers: P0896R4
related: range.view, range.subrange, range.dangling, range.utility.conv, range.adaptors, range.access, temp.dep
tags: 标准库, 范围, view_interface, CRTP
updated: 2026-10-18
---

[range.utility] 收纳了几件"表示和操纵范围"的通用工具：`view_interface`（本页）、`subrange`（[[range.subrange]]）、`dangling` 与 `borrowed_iterator_t`（[[range.dangling]]）、`elements_of`（随 [[coro.generator]] 讲）以及 `ranges::to`（[[range.utility.conv]]）。¶1 只是一句总述。

## 说明用的辅助概念（[range.utility.helpers]）

后面几乎每个适配器的规范都会用到这四个仅用于说明（exposition only）的概念：

```cpp
template<class R>
  concept simple-view =
    view<R> && range<const R> &&
    same_as<iterator_t<R>, iterator_t<const R>> &&
    same_as<sentinel_t<R>, sentinel_t<const R>>;

template<class I>
  concept has-arrow =
    input_iterator<I> && (is_pointer_v<I> || requires(const I i) { i.operator->(); });

template<class T, class U>
  concept different-from = !same_as<remove_cvref_t<T>, remove_cvref_t<U>>;

template<class R>
  concept range-with-movable-references =
    input_range<R> && move_constructible<range_reference_t<R>> &&
    move_constructible<range_rvalue_reference_t<R>>;
```

- ***simple-view***（[[g:simple-view]]）：视图在 `const` 与非 `const` 下迭代器/哨位类型完全相同。像 `ref_view<vector<int>>`、`iota_view` 都是；`filter_view` 不是（没有 const begin）。适配器常写 `begin() requires (!simple-view<V>)` 加 `begin() const`：若底层是 simple-view，非 const 的版本就被约束掉，只留一套 const 实现，**减少模板实例化**并保证 `iterator_t<X>` 与 `iterator_t<const X>` 也相同（从而外层仍是 simple-view）。
- ***has-arrow***：迭代器是否支持 `->`。适配器的迭代器只有在底层支持时才提供 `operator->`。
- ***different-from***：用来约束"转发构造函数"不劫持复制/移动构造（`template<different-from<ref_view> T> ref_view(T&&)`）。
- ***range-with-movable-references***：`enumerate_view`、`zip` 一类要把引用装进 `tuple` 再移动的视图需要它。

## `view_interface`（[view.interface]）

¶1 `view_interface` 是帮助定义"带容器式接口的视图类型"的类模板，以派生类为模板形参——典型的 CRTP（奇异递归模板模式）：

```cpp
template<class D>
  requires is_class_v<D> && same_as<D, remove_cv_t<D>>
class view_interface {
  constexpr D& derived() noexcept { return static_cast<D&>(*this); }
  // ...
};
```

派生类只需提供 `begin()` 和 `end()`，`view_interface` 就根据派生类**实际具备的能力**有条件地提供：

| 成员 | 约束（非 const 版本，const 版本以 `const D` 替换） | 实现 |
|---|---|---|
| `empty()` | `sized_range<D> \|\| forward_range<D>` | 有大小就 `size()==0`，否则 `begin()==end()` |
| `cbegin()` / `cend()` | `input_range<D>` | `ranges::cbegin(derived())` |
| `explicit operator bool()` | `ranges::empty(derived())` 合法 | `!ranges::empty(derived())` |
| `data()` | `contiguous_iterator<iterator_t<D>>` | `to_address(ranges::begin(derived()))` |
| `size()` | `forward_range<D>` 且 `sized_sentinel_for<sentinel_t<D>, iterator_t<D>>` | `to-unsigned-like(end - begin)` |
| `front()` | `forward_range<D>` | `*ranges::begin(derived())` |
| `back()` | `bidirectional_range<D> && common_range<D>` | `*ranges::prev(ranges::end(derived()))` |
| `operator[](n)` | `random_access_range<D>` | `ranges::begin(derived())[n]` |
| `at(n)` | `random_access_range<D> && sized_range<D>` | 越界抛 `out_of_range`；freestanding-deleted |

几处细节：

- **为什么有 const 和非 const 两套**：派生类可能只有非 const 的 `begin()`（如 `filter_view`），也可能两者都有。两套成员分别以 `D` 与 `const D` 检查能力，各自独立地存在或消失。
- **`operator[]` 写成模板 `template<random_access_range R = D>`**：在类模板被实例化时 `D` 还是不完整类型（CRTP 的基类在派生类定义完成前实例化），而成员函数声明上的约束在类模板实例化时就要检查。把约束挂在一个**默认模板实参为 `D`** 的成员模板上，检查就推迟到调用时。`empty()` 等成员用尾随 *requires-clause*，同样只在使用时检查（[[temp.inst]]）。
- **`front()`/`back()` 有"加固前置条件"**（hardened preconditions，¶1、¶3）：`!empty()`。在加固实现中违反它会被检测并终止，而不是任意的未定义行为（C++26 的标准库加固机制，见 [[structure.specifications]]）。
- **`at()`**（¶5–¶6）是较新加入的成员：`n < 0` 或 `n >= ranges::distance(derived())` 时抛 `out_of_range`。

¶2 模板形参 `D` 可以是不完整类型；但在引用 `view_interface<D>` 除特殊成员外的任何成员之前，`D` 必须完整，并且建模 `derived_from<view_interface<D>>` 与 `view`。

```cpp run ok
#include <ranges>
#include <cstdio>
// 一个最小的自定义视图：半开区间 [lo, hi) 中的整数，借用式（不拥有任何东西）
class ints : public std::ranges::view_interface<ints> {
  int lo_ = 0, hi_ = 0;
public:
  ints() = default;
  constexpr ints(int lo, int hi) : lo_(lo), hi_(hi) {}
  constexpr auto begin() const { return std::views::iota(lo_, hi_).begin(); }
  constexpr auto end() const { return std::views::iota(lo_, hi_).end(); }
};
template<> inline constexpr bool std::ranges::enable_borrowed_range<ints> = true;

static_assert(std::ranges::view<ints>);                // 经由 view_interface 自动 enable_view
static_assert(std::ranges::random_access_range<ints>);
static_assert(std::ranges::borrowed_range<ints>);
int main() {
  constexpr ints r{3, 8};
  static_assert(r.size() == 5 && r.front() == 3 && r.back() == 7 && r[2] == 5 && !r.empty());
  auto it = std::ranges::find(ints{3, 8}, 6);          // 右值也返回真迭代器
  std::printf("%d %d\n", *it, bool(r));                // 6 1
}
```

这里 `ints` 的迭代器是 `iota_view<int,int>::iterator`，它自带值、不引用任何 `iota_view` 对象，所以把 `ints` 声明为借用范围是**真实的**承诺。

!!! pitfall "CRTP 写错派生类"
    `class A : public view_interface<B>` 这样的笔误不会在定义处报错（¶2 只在使用成员时才要求 `D` 派生自 `view_interface<D>`），而 `A` 也不会被 `enable_view` 认为是视图——前提是 `A` 恰好有一个 `view_interface<U>` 基类这一条仍成立，所以 `A` **会**被当作视图，而 `empty()` 等成员则会把 `*this` 静态转换成 `B&`——{{ub}}。用 `static_assert(std::derived_from<A, view_interface<A>>)` 自检。

!!! impl "libc++"
    libc++ 的 `__ranges/view_interface.h` 在 `front()`/`back()` 中用 `_LIBCPP_ASSERT_VALID_ELEMENT_ACCESS(!empty(), ...)` 检查非空，在启用加固模式时生效，正好对应"加固前置条件"的规范意图；`operator[]` 没有检查。截至编写时 libc++ 的 `view_interface` 还没有 `at()` 成员。

## 小结

- `view_interface<D>` 让自定义视图只写 `begin`/`end`，其余容器式成员按能力自动出现；
- 成员的约束都是"延迟检查"的，以容忍 CRTP 中 `D` 的不完整；
- *simple-view* 是适配器规范中"合并 const/非 const 实现"的开关，*different-from* 防止转发构造劫持复制构造。
