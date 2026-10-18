---
title: as_const 与 as_rvalue 视图
summary: 两个只改变"元素引用类型"的包装视图——views::as_const 让元素只读（对已是 constant_range、empty_view、optional<X&>、span、ref_view 及 const 可迭代的左值走捷径，否则用 cbegin/cend 产生 basic_const_iterator），解决视图浅 const 的问题；views::as_rvalue 用 move_iterator 让元素成为右值，把复制算法变成移动算法。
status: done
covers: range.as.const, range.as.const.overview, range.as.const.view, range.as.rvalue, range.as.rvalue.overview, range.as.rvalue.view
since: c++23
papers: P2278R4, P2446R2
related: range.access, range.req, range.all, range.adaptors, const.iterators, move.iterators, views.span
tags: 标准库, 范围, as_const, as_rvalue, 常量迭代器
updated: 2026-10-18
---

视图是**浅 const** 的：`const std::span<int>` 仍能修改元素，`const ref_view<vector<int>>` 也一样（[[range.all]]）。要把一个范围以"只读"方式交给别人，C++20 没有好办法——`std::as_const(sp)` 什么也不改变。C++23 的 [[P2278R4]] 补上了 `views::as_const` 与 `ranges::cbegin` 的常量迭代器保证（[[range.access]]）。与之对称，[[P2446R2]] 加入了 `views::as_rvalue`，让元素以右值形式出现。

## `views::as_const`（[range.as.const]）

¶1 `as_const_view` 把底层序列呈现为常量——它的元素不能被修改。

¶2 令 `T` = `decltype((E))`，`U` = `remove_cvref_t<T>`。`views::as_const(E)` 表达式等价于：

| 条 | 条件 | 结果 |
|---|---|---|
| 2.1 | `views::all_t<T>` 建模 `constant_range` | `views::all(E)`（已经只读） |
| 2.2 | `U` 是 `empty_view<X>` | `auto(views::empty<const X>)` |
| 2.3 | `U` 是 `optional<X&>`（{{c++26}}） | `optional<const X&>(E)` |
| 2.4 | `U` 是 `span<X, Extent>` | `span<const X, Extent>(E)` |
| 2.5 | `U` 是 `ref_view<X>` 且 `const X` 建模 `constant_range` | `ref_view(static_cast<const X&>(E.base()))` |
| 2.6 | `E` 是左值、`const U` 建模 `constant_range`、`U` 不是视图 | `ref_view(static_cast<const U&>(E))` |
| 2.7 | 其他 | `as_const_view(E)` |

规则的精神：**能通过"加 const"解决的就不造新类型**。`vector<int>&` → `ref_view<const vector<int>>`；`span<int>` → `span<const int>`。只有当底层本身无法变成只读（例如 `transform` 产生的视图、`filter_view`）时才使用 `as_const_view`。

```cpp
template<view V> requires input_range<V>
class as_const_view : public view_interface<as_const_view<V>> {
  V base_ = V();
public:
  constexpr auto begin() requires (!simple-view<V>) { return ranges::cbegin(base_); }
  constexpr auto begin() const requires range<const V> { return ranges::cbegin(base_); }
  constexpr auto end() requires (!simple-view<V>) { return ranges::cend(base_); }
  constexpr auto end() const requires range<const V> { return ranges::cend(base_); }
  // size / reserve_hint 转发
};
```

`ranges::cbegin` 返回 `const_iterator<I>`：若 `I` 已经是常量迭代器就是 `I` 本身，否则是 `basic_const_iterator<I>`（[[const.iterators]]），后者把 `iter_reference_t` 换成 `iter_const_reference_t`——`int&` 变 `const int&`，prvalue 保持不变。借用性随底层。

¶3 例 1 的意图：

```cpp
template<constant_range R> void cant_touch_this(R&&);
std::vector<char> hammer = {'m', 'c'};
std::span<char> beat = hammer;
cant_touch_this(views::as_const(beat));   // 2.4：span<const char>，不会修改 hammer
```

!!! impl "实现现状"
    截至编写时，libc++ 尚未实现 [[P2278R4]]：没有 `views::as_const`、`basic_const_iterator`，`ranges::cbegin` 也还不保证返回常量迭代器（`__cpp_lib_ranges_as_const` 在其 `<version>` 中被注释掉）。本节示例按标准编写，未在本站环境运行验证。

!!! tip "什么时候用"
    - 函数要把内部数据以范围形式暴露给调用者、又不想被修改：返回 `std::views::as_const(data_)`；
    - 泛型代码需要 `constant_range` 约束的实参；
    - 作为管道的最后一步，防止下游通过视图写回底层。

## `views::as_rvalue`（[range.as.rvalue]）

¶1 `as_rvalue_view` 与底层行为相同，只是元素是右值。一些泛型算法配合它可以把复制换成移动。¶2 `views::as_rvalue(E)` 表达式等价于：

- ¶2.1 `views::all(E)`，若 `T` 建模 `input_range` 且 `range_rvalue_reference_t<T>` 与 `range_reference_t<T>` 相同（元素本来就是右值/prvalue，如 `iota`）；
- ¶2.2 否则 `as_rvalue_view(E)`。

```cpp
template<view V> requires input_range<V>
class as_rvalue_view : public view_interface<as_rvalue_view<V>> {
  V base_ = V();
public:
  constexpr auto begin() requires (!simple-view<V>) { return move_iterator(ranges::begin(base_)); }
  constexpr auto end() requires (!simple-view<V>) {
    if constexpr (common_range<V>) return move_iterator(ranges::end(base_));
    else return move_sentinel(ranges::end(base_));
  }
  // const 版本同理；size / reserve_hint 转发
};
```

迭代器是 `move_iterator`（[[move.iterators]]），`operator*` 返回 `ranges::iter_move(it)`。`move_iterator` 的 `iterator_concept` 跟随底层，最高到 random access（不会是 contiguous）。非 common 底层的尾用 `move_sentinel` 包装。借用性随底层。

```cpp run ok
#include <algorithm>
#include <iterator>
#include <ranges>
#include <string>
#include <vector>
#include <cstdio>
int main() {
  std::vector<std::string> src{"alpha", "beta"}, dst;
  auto mv = src | std::views::as_rvalue;
  static_assert(std::same_as<std::ranges::range_reference_t<decltype(mv)>, std::string&&>);
  std::ranges::copy(mv, std::back_inserter(dst));          // 移动而非复制
  auto keep = std::views::iota(0, 3) | std::views::as_rvalue;   // 元素已是 prvalue：直接 views::all
  static_assert(std::same_as<decltype(keep), std::ranges::iota_view<int, int>>);
  std::printf("%zu [%s] [%s]\n", dst.size(), dst[0].c_str(), src[0].c_str());
  // 2 [alpha] [] —— src 中的字符串处于"有效但未指明"的被移出状态，libc++ 上为空
}
```

!!! pitfall "as_rvalue 之后的多趟遍历"
    `as_rvalue` 只是改变引用类型，本身不移动任何东西；真正移动发生在算法**使用**这些右值时。把 `src | views::as_rvalue` 交给一个会读两遍元素的算法（例如先比较再复制），第二次读到的就是已被移出的对象。只把它交给"每个元素恰好消费一次"的算法（`ranges::copy`、`ranges::to`、构造容器）。

## 小结

| | `as_const` | `as_rvalue` |
|---|---|---|
| 改变 | 引用 → 常量引用 | 引用 → 右值引用 |
| 捷径 | 已只读、`empty_view`、`optional<X&>`、`span`、`ref_view`、const 可迭代的左值 | 元素已是右值 |
| 迭代器 | `const_iterator<I>`（`basic_const_iterator`） | `move_iterator<I>` |
| 借用 | 随底层 | 随底层 |
| libc++（本站环境） | 未实现 | 已实现 |
