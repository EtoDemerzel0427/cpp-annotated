---
title: split 与 lazy_split 视图
summary: split_view（C++20 DR 后的新语义）要求前向底层、元素是 subrange<iterator_t<V>>——对字符串可直接构造 string_view，begin() 缓存第一段；lazy_split_view 保留旧设计，可作用于输入范围（模式须为 tiny-range），内层是一个惰性的前向范围而非 subrange；尾部分隔符产生空段、空输入产生零段、空模式逐元素切分。
status: done
covers: range.split, range.split.overview, range.split.view, range.split.iterator, range.split.sentinel, range.lazy.split, range.lazy.split.overview, range.lazy.split.view, range.lazy.split.outer, range.lazy.split.outer.value, range.lazy.split.inner
since: c++20
papers: P0896R4, P2210R2
related: range.join, range.subrange, range.adaptors, range.utility.conv, range.chunk, range.nonprop.cache, string.view
tags: 标准库, 范围, split, lazy_split, 字符串
updated: 2026-10-18
---

"按分隔符切字符串"是 Ranges 设计史上翻车最明显的地方：C++20 最初的 `views::split` 为了支持输入范围，把每一段做成了一个惰性的"内层范围"，结果连 `std::string(word.begin(), word.end())` 都写不出来（内层不是 common range，迭代器也只是前向）。[[P2210R2]]（"Superior String Splitting"，作为 C++20 的 DR）把旧设计改名为 `lazy_split`，并给出了一个面向前向范围、元素就是 `subrange` 的新 `split`。

## `split_view`（[range.split]）

¶1 `split_view` 接受一个视图和一个分隔符，在分隔符处把视图切成子范围。分隔符可以是单个元素或元素组成的视图。¶2 `views::split(E, F)` 表达式等价于 `split_view(E, F)`。

```cpp
template<forward_range V, forward_range Pattern>
  requires view<V> && view<Pattern> &&
           indirectly_comparable<iterator_t<V>, iterator_t<Pattern>, ranges::equal_to>
class split_view : public view_interface<split_view<V, Pattern>> {
  V base_ = V();
  Pattern pattern_ = Pattern();
  struct iterator;
  struct sentinel;
public:
  template<forward_range R>
    requires constructible_from<V, views::all_t<R>> &&
             constructible_from<Pattern, single_view<range_value_t<R>>>
  constexpr explicit split_view(R&& r, range_value_t<R> e);   // 单元素分隔符
  constexpr iterator begin();                                  // 只有非 const 版本
  constexpr auto end();
  constexpr subrange<iterator_t<V>> find-next(iterator_t<V>);  // 说明用
};
template<class R, class P>
  split_view(R&&, P&&) -> split_view<views::all_t<R>, views::all_t<P>>;
template<forward_range R>
  split_view(R&&, range_value_t<R>) -> split_view<views::all_t<R>, single_view<range_value_t<R>>>;
```

要点：

- **底层必须是前向范围**：每一段都表示为底层的一对迭代器 `subrange<iterator_t<V>>`，需要多趟；
- **元素类型就是 `subrange<iterator_t<V>>`**：对 `string_view` 底层，它是一个 contiguous、sized 的 `subrange<const char*>`，于是可以直接 `std::string_view(word)`（C++23 起 `string_view` 有从连续范围构造的显式构造函数）；
- ¶3–¶4 `begin()` 返回 `{*this, ranges::begin(base_), find-next(ranges::begin(base_))}`，并**缓存结果**以满足摊还 O(1)——于是 `split_view` 没有 const `begin()`；
- ¶5 *find-next* 用 `ranges::search` 找下一个模式；若模式为空，则把找到的位置往后挪一个，从而**空模式把序列切成单个元素**；
- 迭代器是 forward 的（每段的起点与"下一段"的位置都要记住）；迭代器内部有一个 *trailing_empty_* 标志，用来在序列以分隔符结尾时再产生一个空段。

```cpp run ok
#include <ranges>
#include <string_view>
#include <sstream>
#include <cstdio>
using namespace std::literals;
int main() {
  // split：元素是 subrange<const char*>，可直接构造 string_view
  for (auto w : "a,bb,,c"sv | std::views::split(','))
    std::printf("[%.*s]", int(std::string_view(w).size()), std::string_view(w).data());
  std::puts("");   // [a][bb][][c]
  using Split = decltype("x"sv | std::views::split(','));
  static_assert(std::ranges::forward_range<Split>);
  static_assert(!std::ranges::range<const Split>);            // begin() 缓存 → 无 const begin
  // lazy_split：可以作用于 input range
  std::istringstream in{"1 2 0 3 0 4 5"};
  for (auto grp : std::views::istream<int>(in) | std::views::lazy_split(0)) {
    std::printf("{");
    for (int x : grp) std::printf("%d", x);
    std::printf("}");
  }
  std::puts("");   // {12}{3}{45}
}
```

### 边界情况

```cpp run ok
#include <ranges>
#include <string_view>
#include <cstdio>
using namespace std::literals;
int main() {
  int n = 0;
  for (auto w : "a,b,"sv | std::views::split(',')) { (void)w; ++n; }
  int m = 0;
  for (auto w : "a,b,"sv | std::views::lazy_split(',')) { (void)w; ++m; }
  int k = 0;
  for (auto w : "abc"sv | std::views::split(""sv)) { (void)w; ++k; }   // 空模式：逐元素切
  int e = 0;
  for (auto w : ""sv | std::views::split(',')) { (void)w; ++e; }
  std::printf("%d %d %d %d\n", n, m, k, e);   // 3 3 3 0
  using LS = decltype("x"sv | std::views::lazy_split(','));
  using Inner = std::ranges::range_reference_t<LS>;
  static_assert(!std::ranges::contiguous_range<Inner>);   // lazy_split 的内层不是 subrange
  static_assert(std::ranges::forward_range<Inner>);
}
```

- `"a,b,"` 切成 **3** 段：`a`、`b`、空——尾部分隔符产生一个空段；
- 连续分隔符 `",,"` 之间产生空段（前面例子中的 `[]`）；
- **空输入产生 0 段**（而不是 1 个空段）——这一点与很多语言的 `split` 不同；
- 空模式把 `"abc"` 切成 3 个单字符段。

!!! pitfall "模式写成字符串字面量"
    `str | views::split(" ")`：在管道写法中，绑定实参退化为 `const char*`，不是范围也不是 `char`，编译失败；函数调用写法 `views::split(str, " ")` 则会把 `const char[2]` 当作两个字符的模式 `{' ', '\0'}`，基本永远匹配不到。请使用 `' '` 或 `" "sv`（同样的机理见 [[range.join]] 的 `join_with` 坑点）。

## `lazy_split_view`（[range.lazy.split]）

¶1–¶2 语义描述与 `split` 相同：`views::lazy_split(E, F)` 表达式等价于 `lazy_split_view(E, F)`。

```cpp
template<auto> struct require-constant;
template<class R>
concept tiny-range =
  sized_range<R> &&
  requires { typename require-constant<remove_reference_t<R>::size()>; } &&
  (remove_reference_t<R>::size() <= 1);

template<input_range V, forward_range Pattern>
  requires view<V> && view<Pattern> &&
           indirectly_comparable<iterator_t<V>, iterator_t<Pattern>, ranges::equal_to> &&
           (forward_range<V> || tiny-range<Pattern>)
class lazy_split_view;
```

- **底层可以是输入范围**，但此时模式必须是 *tiny-range*：大小是**编译期常量**且不超过 1（典型就是 `single_view` 或 `empty_view`）。原因：对输入序列无法回溯，多元素模式部分匹配失败后，已经读掉的元素没法"还回去"；
- *tiny-range* 用 `require-constant<R::size()>` 这个技巧检测 `size()` 是不是一个**静态 constexpr 成员函数**——`single_view::size()` 正是 `static constexpr`（[[range.factories]]）；
- 底层为输入范围时，当前位置存在视图的 *non-propagating-cache* `current_` 里（[[range.nonprop.cache]]）；
- 外层迭代器（*outer-iterator*，[range.lazy.split.outer]）的 `value_type`（[range.lazy.split.outer.value]）是一个特殊的内层范围，它的 *inner-iterator*（[range.lazy.split.inner]）在遍历时逐个比较模式——**内层是惰性的**：它不是 `subrange`，不是 common，最多是前向；
- 因此不能直接 `std::string_view(word)`，要构造字符串得 `word | ranges::to<std::string>()` 或逐字符复制。

## 选择指南

| 需求 | 用 |
|---|---|
| 切 `string` / `string_view`，想得到 `string_view` 段 | `split` |
| 底层是 `istream_view` 之类的输入范围 | `lazy_split`（单元素分隔符） |
| 想对每段继续用随机访问、`size()` | `split`（底层随机访问时，段也是） |
| 按谓词而非固定模式分段 | `chunk_by`（[[range.chunk]]） |
| 把段再连接回去 | `join` / `join_with`（[[range.join]]） |

## 小结

- `split`：前向底层，段为 `subrange<iterator_t<V>>`，`begin()` 缓存，无 const 迭代；
- `lazy_split`：可用于输入底层（需 tiny 模式），段为惰性内层范围；
- 两者都：尾部分隔符产生空段、空输入零段、空模式逐元素切分；
- C++20 的 DR [[P2210R2]] 交换了名字：今天的 `split` 是新设计，旧的叫 `lazy_split`。
