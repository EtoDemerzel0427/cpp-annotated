---
title: join 与 join_with 视图
summary: join_view 把"范围的范围"展平：ref-is-glvalue 决定一切——内层是引用时可前向/双向且 const 可迭代，内层是 prvalue 时用 non-propagating-cache 暂存、退化为输入范围；外层为输入范围时外层迭代器也存进视图；satisfy() 跳过空内层；join_with 在相邻内层之间插入分隔符（单个元素或范围），与 concat 共用 concatable 约束。
status: done
covers: range.join, range.join.overview, range.join.view, range.join.iterator, range.join.sentinel, range.join.with, range.join.with.overview, range.join.with.view, range.join.with.iterator, range.join.with.sentinel
since: c++20
papers: P0896R4, P2441R2, P2770R0
related: range.adaptors, range.nonprop.cache, range.split, range.concat, range.transform, range.utility.conv, range.utility
tags: 标准库, 范围, join, join_with, 展平
updated: 2026-10-18
---

`views::join` 是 `flatten`：`vector<vector<int>>` 变成一串 `int`，`vector<string>` 变成一串 `char`。它是 `split` 的逆运算（把切开的东西再连起来），也是"一对多变换"（`transform` 产生范围，再 `join`，即 `flat_map`）的基础。它的规范复杂度主要来自一个问题：**内层范围活在哪里？**

## `join_view`（[range.join]）

¶1 `join_view` 把范围组成的视图展平成一个视图。¶2 `views::join(E)` 表达式等价于 `join_view<views::all_t<decltype((E))>>{E}`。

```cpp
template<input_range V>
  requires view<V> && input_range<range_reference_t<V>>
class join_view : public view_interface<join_view<V>> {
  using InnerRng = range_reference_t<V>;
  V base_ = V();
  non-propagating-cache<iterator_t<V>> outer_;          // 仅当 !forward_range<V>
  non-propagating-cache<remove_cv_t<InnerRng>> inner_;  // 仅当 !is_reference_v<InnerRng>
public:
  constexpr auto begin();
  constexpr auto begin() const
    requires forward_range<const V> && is_reference_v<range_reference_t<const V>> &&
             input_range<range_reference_t<const V>>;
  constexpr auto end();
  constexpr auto end() const requires /* 同上 */;
};
```

### *ref-is-glvalue*：内层是引用还是临时量

迭代器内部定义 *ref-is-glvalue* = `is_reference_v<range_reference_t<Base>>`。两种情况截然不同：

**内层是引用**（`vector<vector<int>>` 的元素 `vector<int>&`）：内层范围就在外层容器里，迭代器可以同时持有外层迭代器和内层迭代器，随时回到外层。此时：

- [range.join.iterator] ¶1：外层双向、内层双向且 **common** → 双向；都是前向 → 前向；
- 有 `const begin()`（只要 `const V` 也满足条件）；
- `end()` 在外层前向+common、内层前向+common 时返回迭代器（common range）。

**内层是 prvalue**（例如 `transform` 返回 `std::string`）：每次解引用外层得到一个**新的临时范围**，内层迭代器指向它；临时量必须被存在某处，否则一解引用就悬垂。规范把它存在视图对象的 `inner_`（*non-propagating-cache*，[[range.nonprop.cache]]）里，每进入一个新的外层元素就 *emplace-deref* 一次。后果：

- 迭代器状态的一部分在视图里，两个迭代器不可能独立地处在不同的内层范围——所以**只能是输入范围**（¶1.3）；
- 没有 `const begin()`（要写 `inner_`）；
- 视图不能被复制后继续用原来的迭代器（缓存不传播）。

```cpp run ok
#include <ranges>
#include <string>
#include <vector>
#include <cstdio>
int main() {
  std::vector<int> v{1, 2, 3};
  // 内层是 prvalue（每次解引用造一个新 string）
  auto j = v | std::views::transform([](int i) { return std::string(i, 'x'); })
             | std::views::join;
  static_assert(std::ranges::input_range<decltype(j)>);
  static_assert(!std::ranges::forward_range<decltype(j)>);
  static_assert(!std::ranges::range<const decltype(j)>);
  for (char c : j) std::putchar(c);   // xxxxxx
  std::puts("");
}
```

### 外层是输入范围

若外层 `V` 只是输入范围，外层迭代器也被存进视图的 `outer_` 缓存（`begin()` 中 `outer_ = ranges::begin(base_)`），视图的迭代器不再自己持有外层迭代器。这是 C++23 期间由 [[P2770R0]]（作为 DR）引入的修正：原先的设计在外层迭代器是"stashing"（解引用返回指向自身内部的引用）时会产生悬垂。

### `satisfy()`：跳过空内层

迭代器构造与 `++` 之后都调用说明用函数 *satisfy*：如果当前内层范围已经走完（或为空），就前进外层并进入下一个内层，直到找到非空内层或外层结束。因此 `{{1,2},{},{3}}` 展平为 `1 2 3`，空内层不产生任何元素。这也意味着 `++` 不是严格 O(1)——连续很多空内层时会一直跳。

### 性质

- **永不 sized**：总长度要遍历外层才能知道；
- **不借用**；
- 双向时可以 `| views::reverse`（需要内层 common，因为反向进入内层要从它的 `end()` 往回走）。

```cpp run ok
#include <ranges>
#include <string>
#include <string_view>
#include <vector>
#include <cstdio>
int main() {
  std::vector<std::vector<int>> vv{{1, 2}, {}, {3}};
  auto flat = vv | std::views::join;
  static_assert(std::ranges::bidirectional_range<decltype(flat)>);   // 内外都双向且内层 common
  static_assert(!std::ranges::sized_range<decltype(flat)>);          // 不遍历不知道总数
  for (int x : flat | std::views::reverse) std::printf("%d", x);    // 321
  std::vector<std::string> words{"a", "bc", "d"};
  auto csv = words | std::views::join_with(std::string_view(", "));
  auto s = csv | std::ranges::to<std::string>();
  auto zeros = vv | std::views::join_with(0);                        // 单个元素作分隔符
  std::printf(" [%s] ", s.c_str());                                  // [a, bc, d]
  for (int x : zeros) std::printf("%d", x);                          // 12003
  std::puts("");
}
```

## `join_with_view`（[range.join.with]）{{c++23}}

¶1 `join_with_view` 接受一个视图和一个分隔符，展平视图，并在相邻元素（内层范围）之间插入分隔符的每个元素。分隔符可以是单个元素或元素组成的视图。¶2 `views::join_with(E, F)` 表达式等价于 `join_with_view(E, F)`。来自 [[P2441R2]]。

```cpp
template<input_range V, forward_range Pattern>
  requires view<V> && input_range<range_reference_t<V>>
        && view<Pattern>
        && concatable<range_reference_t<V>, Pattern>
class join_with_view;

template<class R, class P>
  join_with_view(R&&, P&&) -> join_with_view<views::all_t<R>, views::all_t<P>>;
template<input_range R>
  join_with_view(R&&, range_value_t<range_reference_t<R>>)
    -> join_with_view<views::all_t<R>, single_view<range_value_t<range_reference_t<R>>>>;
```

- 分隔符是单个元素时，推导指引把它包进 `single_view`；
- 约束用的是 *concatable*（与 [[range.concat]] 共用）：内层元素与分隔符元素必须有公共引用类型、公共值类型等——迭代器的 `operator*` 返回二者的 `common_reference_t`；
- 内部迭代器用一个 `variant` 在"分隔符迭代器"与"内层迭代器"之间切换；
- 与 `join` 一样有 *ref-is-glvalue* 的区分（prvalue 内层 → 输入范围、无 const `begin`），外层为输入时同样缓存外层迭代器（`outer_it_`）；
- 首尾**不**加分隔符；空内层之间仍会插入分隔符（`{{1,2},{},{3}}` 以 `0` 连接得 `1 2 0 0 3`，见上例输出 `12003`）。

!!! tip "join_with 实现 CSV 拼接"
    `words | views::join_with(", "sv) | ranges::to<std::string>()` 是 C++23 中最简洁的字符串 `join`。分隔符请写成 `string_view`（或单个字符），不要直接用字符串字面量，见下面的坑点。

## 坑点

!!! pitfall "flat_map 写法的输入退化"
    `v | views::transform(f) | views::join`，若 `f` 返回容器（prvalue），结果是**输入范围**：不能 `reverse`、不能多趟遍历、不能 const 迭代、`ranges::to<vector>` 时不能预先知道大小。若后续需要更强的能力，先 `| ranges::to<std::vector>()` 物化，或者让 `f` 返回某种视图（如 `views::iota(0, n)`，它本身仍是 prvalue，但轻量）。

!!! pitfall "字符串字面量当分隔符：两种写法、两种错误"
    - **管道写法** `w | views::join_with("--")` **编译失败**：按 [[range.adaptor.object]] ¶8，部分应用时绑定实参的类型是 `decay_t`，`"--"` 退化成 `const char*`——它不是范围，也不是 `char`。
    - **函数调用写法** `views::join_with(w, "--")` **能编译但结果错误**：此时实参不退化，`views::all` 把 `const char(&)[3]` 变成 `ref_view<const char[3]>`，分隔符包含结尾的 `'\0'`。

    ```cpp run ok
    #include <ranges>
    #include <string>
    #include <vector>
    #include <cstdio>
    int main() {
      std::vector<std::string> w{"a", "b"};
      auto s = std::views::join_with(w, "--") | std::ranges::to<std::string>();
      std::printf("%zu\n", s.size());   // 5：a - - \0 b
    }
    ```

## 小结

| 情形 | 迭代器强度 | const 可迭代 | 状态存放 |
|---|---|---|---|
| 内层引用，外层/内层双向且内层 common | bidirectional | ✓ | 迭代器内 |
| 内层引用，前向 | forward | ✓ | 迭代器内 |
| 内层 prvalue | input | ✗ | 视图的 `inner_` 缓存 |
| 外层仅输入 | input | ✗ | 视图的 `outer_` 缓存 |
