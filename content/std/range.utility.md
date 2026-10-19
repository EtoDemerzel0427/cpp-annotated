---
title: 范围工具与 view_interface
summary: 自定义视图只写 begin 和 end，就能从 view_interface 得到 empty、size、front、back、operator[] 等成员；以及适配器规范中反复出现的 simple-view 等说明用概念。
status: done
covers: range.utility.general, range.utility.helpers, view.interface, view.interface.general, view.interface.members
since: c++20
papers: P0896R4
related: range.view, range.subrange, range.dangling, range.utility.conv, range.adaptors, range.access, temp.dep
tags: 标准库, 范围, view_interface, CRTP
updated: 2026-10-19
---

!!! tldr
    - 继承 `view_interface<D>` 的类只需提供 `begin()` 和 `end()`，就能按自己具备的能力得到 `empty`、`operator bool`、`data`、`size`、`front`、`back`、`operator[]`、`at`、`cbegin`、`cend`。
    - 每个成员都有 const 和非 const 两个版本，分别按 `D` 和 `const D` 的能力出现或消失。
    - `front()` 和 `back()` 的前置条件 `!empty()` 是加固前置条件，加固实现会检查它。
    - *simple-view* 表示 const 与非 const 下迭代器和哨位类型相同，适配器用它合并两套实现。

[range.utility] 收纳几件表示和操纵范围的通用工具：本页讲的 `view_interface`，以及 `subrange`（[[range.subrange]]）、`dangling`（[[range.dangling]]）、`elements_of`（随 [[coro.generator]] 讲）和 `ranges::to`（[[range.utility.conv]]）。

## 一个最小的自定义视图 [view.interface]

```cpp run ok
#include <ranges>
#include <algorithm>
#include <cstdio>

// 半开区间 [lo, hi) 中的整数
class ints : public std::ranges::view_interface<ints> {
  int lo_ = 0, hi_ = 0;
public:
  ints() = default;
  constexpr ints(int lo, int hi) : lo_(lo), hi_(hi) {}
  constexpr auto begin() const { return std::views::iota(lo_, hi_).begin(); }
  constexpr auto end() const { return std::views::iota(lo_, hi_).end(); }
};
template<>
inline constexpr bool std::ranges::enable_borrowed_range<ints> = true;

static_assert(std::ranges::view<ints>);   // 继承 view_interface 即 enable_view
static_assert(std::ranges::random_access_range<ints>);

int main() {
  constexpr ints r{3, 8};
  static_assert(r.size() == 5 && r.front() == 3 && r.back() == 7);
  static_assert(r[2] == 5 && !r.empty());
  auto it = std::ranges::find(ints{3, 8}, 6);   // 右值也返回真正的迭代器
  std::printf("%d %d\n", *it, bool(r));         // 6 1
}
```

`ints` 自己只写了 `begin` 和 `end`，`size`、`front`、`back`、`operator[]`、`empty` 和 `operator bool` 都来自基类。它的迭代器是 `iota_view<int, int>::iterator`，迭代器里直接存着当前值，不引用任何 `iota_view` 对象，所以把 `ints` 声明为借用范围（[[range.range]]）是真实的承诺。

¶1 `view_interface` 以派生类为模板实参，这种写法叫 CRTP（奇异递归模板模式）。基类通过 `static_cast<D&>(*this)` 拿到派生类对象，再调用它的 `begin` 和 `end`：

```cpp
template<class D>
  requires is_class_v<D> && same_as<D, remove_cv_t<D>>
class view_interface {
  constexpr D& derived() noexcept { return static_cast<D&>(*this); }
  // ...
};
```

## 基类提供哪些成员

每个成员按派生类实际具备的能力出现。下表列出非 const 版本的约束，const 版本把 `D` 换成 `const D`：

| 成员 | 约束 | 效果 |
|---|---|---|
| `empty()` | `sized_range<D> \|\| forward_range<D>` | 有大小就比较 `size() == 0`，否则比较 `begin() == end()` |
| `cbegin()`、`cend()` | `input_range<D>` | `ranges::cbegin(derived())` 等 |
| `explicit operator bool()` | `ranges::empty(derived())` 合法 | `!ranges::empty(derived())` |
| `data()` | `contiguous_iterator<iterator_t<D>>` | `to_address(ranges::begin(derived()))` |
| `size()` | `forward_range<D>`，且哨位与迭代器可相减 | `end - begin`，转成无符号类型 |
| `front()` | `forward_range<D>` | `*ranges::begin(derived())` |
| `back()` | `bidirectional_range<D> && common_range<D>` | `*ranges::prev(ranges::end(derived()))` |
| `operator[](n)` | `random_access_range<D>` | `ranges::begin(derived())[n]` |
| `at(n)` | `random_access_range<D> && sized_range<D>` | 越界时抛 `out_of_range` |

之所以要有 const 和非 const 两套，是因为派生类可能只有非 const 的 `begin()`，比如 `filter_view`（[[range.filter]]），也可能两者都有。两套成员各自检查约束，互不影响。

`operator[]` 和 `at` 写成了成员模板 `template<random_access_range R = D>`。它们的形参类型是 `range_difference_t<R>`，如果直接写成 `range_difference_t<D>`，这个类型会在基类实例化时就被计算，而 CRTP 的基类实例化时 `D` 还不完整，无法计算。写成默认实参为 `D` 的模板后，形参类型推迟到调用时才确定。其余成员的形参不依赖 `D`，约束写成尾随 *requires-clause*，只在使用时检查。

¶2 由此也得到 `D` 的要求：它可以是不完整类型；但在引用 `view_interface<D>` 的任何非特殊成员之前，`D` 必须完整，并且建模 `derived_from<view_interface<D>>` 和 `view`。

### front、back、at 的前置条件 [view.interface.members]

¶1、¶3 `front()` 和 `back()` 的前置条件是 `!empty()`，标准把它标为**加固前置条件**（hardened precondition）{{c++26}}：在加固实现中，违反它会被检查并终止程序；在非加固实现中仍是未定义行为（[[structure.specifications]]）。

¶5–¶6 `at(n)` 返回 `(*this)[n]`；如果 `n < 0` 或 `n >= ranges::distance(derived())`，抛出 `out_of_range`。`at` 在 freestanding 实现中是被删除的（freestanding-deleted），因为那里不一定有异常。

!!! impl "libc++"
    libc++ 的 `__ranges/view_interface.h` 在 `front()`、`back()` 中用 `_LIBCPP_ASSERT_VALID_ELEMENT_ACCESS` 检查非空，启用加固模式时生效。`operator[]` 没有检查。截至 Clang 23 附带的 libc++，`view_interface` 还没有 `at()` 成员。

!!! pitfall "CRTP 实参写错"
    写成 `class A : public view_interface<B>` 这样的笔误时，`A` 仍然恰好有一个 `view_interface<U>` 基类，所以 `enable_view<A>` 为真，`A` 被当作视图。如果 `B` 本身是一个合格的视图，调用 `a.empty()` 也能编译，基类会把一个 `A` 对象 `static_cast` 成 `B&`，这是{{ub}}。可以加一句 `static_assert(std::derived_from<A, std::ranges::view_interface<A>>)` 自检。

## 说明用的辅助概念 [range.utility.helpers]

¶1 后面几乎每个适配器的规范都会用到下面四个仅用于说明（exposition only）的概念。它们不是库的一部分，只是规范的写法：

```cpp
template<class R>
  concept simple-view =
    view<R> && range<const R> &&
    same_as<iterator_t<R>, iterator_t<const R>> &&
    same_as<sentinel_t<R>, sentinel_t<const R>>;

template<class I>
  concept has-arrow =
    input_iterator<I> &&
    (is_pointer_v<I> || requires(const I i) { i.operator->(); });

template<class T, class U>
  concept different-from = !same_as<remove_cvref_t<T>, remove_cvref_t<U>>;

template<class R>
  concept range-with-movable-references =
    input_range<R> && move_constructible<range_reference_t<R>> &&
    move_constructible<range_rvalue_reference_t<R>>;
```

***simple-view***（[[g:simple-view]]）表示一个视图在 const 和非 const 下的迭代器和哨位类型完全相同。`ref_view<vector<int>>`、`iota_view` 是 simple-view；`filter_view` 不是，它没有 const 的 `begin`。适配器常写成一对：

```cpp
constexpr auto begin() requires (!simple-view<V>);
constexpr auto begin() const requires range<const V>;
```

底层是 simple-view 时，非 const 版本被约束掉，只剩 const 版本。这样少实例化一套代码，而且外层适配器的 `iterator_t<X>` 和 `iterator_t<const X>` 也相同，外层仍然是 simple-view。

***has-arrow*** 判断迭代器是否支持 `->`。适配器的迭代器只在底层迭代器支持时才提供 `operator->`。

***different-from*** 用来约束转发构造函数，防止它劫持复制和移动构造。例如 `ref_view` 的构造函数写成 `template<different-from<ref_view> T> ref_view(T&&)`：实参本身就是 `ref_view` 时，这个模板不参与，复制构造函数照常被选中。

***range-with-movable-references*** 要求元素的引用类型和右值引用类型都可以移动构造。`enumerate_view` 这类要把引用装进 `tuple` 再传出去的视图需要它。
