---
title: as_const 与 as_rvalue 视图
summary: 两个只改变元素引用类型的视图：views::as_const 让元素只读，弥补视图浅 const 的问题，能加 const 解决时直接返回加了 const 的同类视图；views::as_rvalue 让元素成为右值，把复制算法变成移动算法。
status: done
covers: range.as.const, range.as.const.overview, range.as.const.view, range.as.rvalue, range.as.rvalue.overview, range.as.rvalue.view
since: c++23
papers: P2278R4, P2446R2
related: range.access, range.req, range.all, range.adaptors, const.iterators, move.iterators, views.span
tags: 标准库, 范围, as_const, as_rvalue, 常量迭代器
updated: 2026-10-19
---

!!! tldr
    - 视图是浅 const 的：`const std::span<int>` 照样能修改元素。`views::as_const` 得到一个元素只读的视图。
    - 能靠加 const 解决时，`as_const` 不造新类型：`span<int>` 变成 `span<const int>`，容器左值变成 `ref_view<const C>`；只有其余情况才用 `as_const_view`，它的迭代器来自 `ranges::cbegin`。
    - `views::as_rvalue` 把元素变成右值引用，迭代器是 `move_iterator`；交给 `ranges::copy` 就成了逐个移动。
    - `as_rvalue` 本身不移动任何东西，移动发生在算法使用元素时，所以只能交给每个元素只读一次的算法。
    - 本机 libc++ 还没有实现 `views::as_const`；`views::as_rvalue` 可用。

```cpp run ok
#include <algorithm>
#include <cstdio>
#include <iterator>
#include <ranges>
#include <string>
#include <vector>

int main() {
  std::vector<std::string> words{"the", "quick", "brown", "fox"};
  std::vector<std::string> new_words;
  std::ranges::copy(words | std::views::as_rvalue, std::back_inserter(new_words));
  std::printf("%zu [%s] [%s]\n", new_words.size(), new_words[0].c_str(), words[0].c_str());
  // 4 [the] []：words 中的字符串已被移走
}
```

这是 [range.as.rvalue.overview] ¶3 的例子：`ranges::copy` 从 `as_rvalue` 视图读出的每个元素都是 `std::string&&`，所以 `back_inserter` 做的是移动构造。被移走的字符串处于有效但未指明的状态，本机 libc++ 上它们变成了空串。

这两个视图都不改变元素的个数和顺序，只改变解引用得到的类型：`as_const` 换成常量引用，`as_rvalue` 换成右值引用。

## `views::as_const`：只读的视图 [range.as.const]

视图是浅 const 的（[[range.all]]）：`const std::span<int>` 和 `const ref_view<vector<int>>` 都还能修改元素，因为 const 只作用于视图对象本身，而不作用于它指向的元素。C++20 里想把一个范围以只读方式交出去没有好办法，`std::as_const(sp)` 什么也改变不了。C++23 的 [[P2278R4]] 加入了 `views::as_const`，同时让 `ranges::cbegin` 保证返回常量迭代器（[[range.access]]）。

¶1 `as_const_view` 把底层序列呈现为常量，它的元素不能被修改。

### 能加 const 就不包装（¶2）

¶2 令 `T` 为 `decltype((E))`，`U` 为去掉引用和 cv 限定后的类型。`views::as_const(E)` 依次检查：

| 段 | 条件 | 结果 |
|---|---|---|
| ¶2.1 | `views::all_t<T>` 已经是[[g:constant-range|常量范围]] | `views::all(E)` |
| ¶2.2 | `U` 是 `empty_view<X>` | `views::empty<const X>` 的副本 |
| ¶2.3 | `U` 是 `optional<X&>` {{c++26}} | `optional<const X&>(E)` |
| ¶2.4 | `U` 是 `span<X, Extent>` | `span<const X, Extent>(E)` |
| ¶2.5 | `U` 是 `ref_view<X>`，且 `const X` 是常量范围 | `ref_view(static_cast<const X&>(E.base()))` |
| ¶2.6 | `E` 是左值，`const U` 是常量范围，`U` 不是视图 | `ref_view(static_cast<const U&>(E))` |
| ¶2.7 | 其他 | `as_const_view(E)` |

常量范围指迭代器解引用得到的是只读引用的范围。前六条的思路相同：如果给某个类型加上 const 就能得到只读的范围，就直接返回加了 const 的同类视图。例如 `vector<int>` 左值得到 `ref_view<const vector<int>>`，`span<int>` 得到 `span<const int>`。只有 `transform_view`、`filter_view` 这类本身无法变成只读的视图，才需要 `as_const_view`。

¶3 例 1 展示了典型用法：

```cpp
template<constant_range R>
void cant_touch_this(R&&);

std::vector<char> hammer = {'m', 'c'};
std::span<char> beat = hammer;
cant_touch_this(std::views::as_const(beat));   // ¶2.4：span<const char>，不会修改 hammer
```

### as_const_view [range.as.const.view]

`as_const_view` 的 `begin()` 和 `end()` 就是对底层调用 `ranges::cbegin` 和 `ranges::cend`。它们返回常量迭代器：底层迭代器已经是常量迭代器时原样返回，否则包装成 `basic_const_iterator`（[[const.iterators]]）。后者把解引用的结果从 `int&` 换成 `const int&`；如果底层解引用得到的是纯右值，就保持不变，因为纯右值本来就改不到原元素。

`size()`、`reserve_hint()` 转发给底层，借用性也与底层相同。¶1 构造函数保存底层视图。

!!! impl "实现现状"
    截至写作时，本机 libc++ 尚未实现 [[P2278R4]]：没有 `views::as_const` 和 `basic_const_iterator`，`<version>` 中的 `__cpp_lib_ranges_as_const` 被注释掉了。本节的代码按标准原文编写，没有经过编译验证。

需要 `as_const` 的典型场合：类把内部数据以范围的形式暴露给调用者，又不想被修改，可以返回 `std::views::as_const(data_)`；泛型代码要求实参满足 `constant_range`；或者在管道的最后一步防止下游通过视图写回底层。

## `views::as_rvalue`：元素变成右值 [range.as.rvalue]

¶1 `as_rvalue_view` 的行为与底层序列相同，只是元素是右值。有些泛型算法配合它可以把复制换成移动。

¶2 `views::as_rvalue(E)` 在底层是输入范围、且它的右值引用类型与引用类型相同时，等价于 `views::all(E)`；否则是 `as_rvalue_view(E)`。前一种情况指元素本来就是右值，比如 `iota` 每次解引用产生一个纯右值，再包装没有意义。

`as_rvalue_view` 的 `begin()` 返回 `move_iterator(ranges::begin(base_))`（[[move.iterators]]），它的 `operator*` 返回 `ranges::iter_move(it)`。底层是公共范围时 `end()` 也是 `move_iterator`，否则是 `move_sentinel`。`move_iterator` 的类别跟随底层，最高到随机访问，不会是连续迭代器。借用性与底层相同。

```cpp run ok
#include <ranges>
#include <string>
#include <vector>

std::vector<std::string> src{"alpha", "beta"};
using MV = decltype(src | std::views::as_rvalue);
static_assert(std::same_as<std::ranges::range_reference_t<MV>, std::string&&>);

using Keep = decltype(std::views::iota(0, 3) | std::views::as_rvalue);
static_assert(std::same_as<Keep, std::ranges::iota_view<int, int>>);   // ¶2.1：不包装

int main() {}
```

!!! pitfall "交给会读两遍的算法"
    `as_rvalue` 只是改变了引用类型，本身不移动任何东西；元素在算法用这个右值初始化另一个对象时才被移走。如果把 `src | views::as_rvalue` 交给一个会把同一元素读两遍的算法，第二次读到的就是已经移走的对象。只把它交给每个元素恰好消费一次的操作，如 `ranges::copy`、`ranges::to` 或容器的范围构造。

## 小结

| | `as_const` | `as_rvalue` |
|---|---|---|
| 解引用的结果 | 常量引用 | 右值引用 |
| 不包装的情况 | 已经只读；`empty_view`、`optional<X&>`、`span`、`ref_view`、容器左值改为加 const 的同类视图 | 元素已经是右值 |
| 迭代器 | `ranges::cbegin` 返回的常量迭代器 | `move_iterator` |
| 借用范围 | 底层是时 | 底层是时 |
| 本机 libc++ | 未实现 | 已实现 |

<details class="fine" markdown="1"><summary>其余条文</summary>

[range.as.rvalue.view] ¶1：构造函数保存底层视图。两个视图都有推导指引，把 `R` 经 `views::all_t` 包成视图。

</details>
