---
title: split 与 lazy_split 视图
summary: views::split 按分隔符把前向范围切成若干段，每段是底层的一个 subrange，切字符串时可以直接得到 string_view；views::lazy_split 保留 C++20 最初的设计，能作用于输入范围，但每一段只是一个惰性的内层范围。
status: done
covers: range.split, range.split.overview, range.split.view, range.split.iterator, range.split.sentinel, range.lazy.split, range.lazy.split.overview, range.lazy.split.view, range.lazy.split.outer, range.lazy.split.outer.value, range.lazy.split.inner
since: c++20
papers: P0896R4, P2210R2
related: range.join, range.subrange, range.adaptors, range.utility.conv, range.chunk, range.nonprop.cache, string.view
tags: 标准库, 范围, split, lazy_split, 字符串
updated: 2026-10-19
---

!!! tldr
    - `views::split(sep)` 要求底层是前向范围，每一段都是 `subrange<iterator_t<V>>`；切 `string_view` 时每段可以直接转成 `string_view`。
    - `split_view` 缓存第一段的位置，所以没有 const 版本的 `begin()`。
    - 以分隔符结尾会多出一个空段，连续两个分隔符之间也有一个空段，空输入则一段也没有；空模式把序列切成单个元素。
    - `views::lazy_split` 可以作用于 `istream_view` 这类输入范围（分隔符只能是单个元素），代价是每一段只是一个惰性的前向范围。
    - 分隔符不要写成字符串字面量，写成字符或 `string_view`。

```cpp run ok
#include <iostream>
#include <ranges>
#include <string>
#include <string_view>

int main() {
  std::string str{"the quick brown fox"};
  for (auto word : std::views::split(str, ' '))
    std::cout << std::string_view(word) << '*';
  std::cout << '\n';                            // the*quick*brown*fox*
}
```

这是 [range.split.overview] ¶3 的例子。每个 `word` 是 `str` 中的一对迭代器，`std::string_view(word)` 直接引用原字符串里的字符，不复制。

C++20 最初的 `views::split` 不是这样：为了支持输入范围，每一段被设计成一个惰性的内层范围，连 `std::string(word.begin(), word.end())` 都写不出来，因为它的 `begin()` 和 `end()` 类型不同。[[P2210R2]] 作为 C++20 的缺陷报告修正了这一点：旧设计改名为 `lazy_split`，`split` 换成了今天面向前向范围的设计。

## `views::split` [range.split]

¶1 `split_view` 接受一个视图和一个分隔符，在分隔符处把视图切成子范围。分隔符可以是单个元素，也可以是元素组成的视图。¶2 `views::split(E, F)` 等价于 `split_view(E, F)`。

### 每一段都是一个 subrange [range.split.view]

`split_view` 的元素类型是 `subrange<iterator_t<V>>`，也就是底层视图中的一对迭代器（[[range.subrange]]）。这带来两个要求和一个好处：

- 底层必须是前向范围。找到下一个分隔符要往前看，而这一段的起点还要保留，所以要能多趟遍历。
- 模式也必须是前向范围，并且元素能和底层的元素比较相等（`indirectly_comparable`）。
- 底层随机访问时，每一段也是随机访问、sized 的范围；底层是连续的字符串时，每一段可以直接构造 `string_view`（C++23 起 `string_view` 有从连续范围构造的显式构造函数）。

分隔符是单个元素时，推导指引和 ¶2 的构造函数把它包进 `single_view`。

### begin() 缓存第一段（¶3–¶5）

¶3 `begin()` 返回的迭代器保存当前段的起点，以及下一个分隔符的位置；后者由说明用函数 *find-next* 求出。¶4 求第一段需要搜索一次，为了满足 `range` 概念对 `begin()` 摊还常数时间的要求，结果被缓存在视图里。所以 `split_view` 只有非 const 的 `begin()`。

¶5 *find-next* 用 `ranges::search` 找下一次出现的模式。如果模式是空的，`search` 总是在当前位置匹配成功，这样会得到无穷多个空段；所以这时把找到的位置往后挪一个元素。结果是空模式把序列切成一个个单元素段。

```cpp run ok
#include <cstdio>
#include <ranges>
#include <string_view>
using namespace std::literals;

int main() {
  for (auto w : "a,bb,,c"sv | std::views::split(','))
    std::printf("[%.*s]", int(std::string_view(w).size()), std::string_view(w).data());
  std::puts("");                                              // [a][bb][][c]

  using Split = decltype("x"sv | std::views::split(','));
  static_assert(std::ranges::forward_range<Split>);
  static_assert(!std::ranges::range<const Split>);           // 没有 const begin()
}
```

### 首尾和空输入 [range.split.iterator]

迭代器除了当前段的位置，还有一个标志 *trailing_empty_*。序列以分隔符结尾时，`++` 越过最后一个分隔符后先置位这个标志，再产生一个空段（¶4）；与哨位比较时，只有到达底层终点且标志未置位才算结束（[range.split.sentinel] ¶2）。

```cpp run ok
#include <cstdio>
#include <ranges>
#include <string_view>
using namespace std::literals;

int count(auto&& r) { int n = 0; for (auto&& x : r) { (void)x; ++n; } return n; }

int main() {
  std::printf("%d ", count("a,b,"sv | std::views::split(',')));    // 3：a、b、空
  std::printf("%d ", count("a,,b"sv | std::views::split(',')));    // 3：a、空、b
  std::printf("%d ", count("abc"sv | std::views::split(""sv)));    // 3：空模式逐个切
  std::printf("%d\n", count(""sv | std::views::split(',')));       // 0：空输入没有段
}
```

空输入得到 0 段，而不是 1 个空段。这一点与很多语言的 `split` 函数不同。

## `views::lazy_split`：可以切输入范围 [range.lazy.split]

¶1–2 `lazy_split_view` 的语义描述与 `split_view` 相同，`views::lazy_split(E, F)` 等价于 `lazy_split_view(E, F)`。区别在于它的底层可以只是输入范围：

```cpp run ok
#include <cstdio>
#include <ranges>
#include <sstream>

int main() {
  std::istringstream in{"1 2 0 3 0 4 5"};
  for (auto grp : std::views::istream<int>(in) | std::views::lazy_split(0)) {
    std::printf("{");
    for (int x : grp) std::printf("%d", x);
    std::printf("}");
  }
  std::puts("");                                 // {12}{3}{45}
}
```

### 输入范围上模式只能是一个元素 [range.lazy.split.view]

底层是输入范围时，模式必须满足说明用概念 *tiny-range*：它的大小是编译期常量，并且不超过 1。原因是输入序列不能回头：如果模式有多个元素，部分匹配失败时，已经读走的元素无法放回去。

*tiny-range* 用 `require-constant<R::size()>` 检查 `size()` 能否作为模板实参，也就是它是不是一个静态的 constexpr 成员函数。`single_view` 和 `empty_view` 的 `size()` 正是这样（[[range.factories]]），所以单个元素的分隔符可以用。

底层是输入范围时，当前位置存放在视图的 `current_` 里，这是一个 [[range.nonprop.cache|non-propagating-cache]]。底层是前向范围时，`lazy_split_view` 还有 const 版本的 `begin()`，这一点与 `split_view` 不同。

### 每一段是惰性的内层范围

外层迭代器（[range.lazy.split.outer]）的 `value_type`（[range.lazy.split.outer.value]）不是 `subrange`，而是一个特殊的内层范围。它的迭代器（[range.lazy.split.inner]）在遍历时一边前进一边与模式比较，走到下一个分隔符为止。

所以这个内层范围不是公共范围，最多是前向范围，不能直接构造 `string_view`。想得到字符串，要写 `word | ranges::to<std::string>()` 或逐个复制字符。

```cpp run ok
#include <ranges>
#include <string_view>
using namespace std::literals;

using LS = decltype("x"sv | std::views::lazy_split(','));
using Inner = std::ranges::range_reference_t<LS>;
static_assert(std::ranges::forward_range<Inner>);
static_assert(!std::ranges::common_range<Inner>);
static_assert(!std::ranges::contiguous_range<Inner>);

int main() {}
```

`lazy_split` 在首尾、空输入、空模式上的结果与 `split` 相同。

## 常见误解

!!! pitfall "模式写成字符串字面量"
    管道写法 `str | views::split(" ")` 编译失败：按值保存实参时数组退化成 `const char*`（[[range.adaptor.object#8]]），它既不是范围，也不是 `char`。

    函数调用写法 `views::split(str, " ")` 能编译，但模式是 `const char[2]` 的两个字符 `{' ', '\0'}`，几乎永远匹配不到。写成 `' '` 或 `" "sv`。`join_with` 有同样的问题，见 [[range.join]]。

## 怎么选

| 需求 | 用 |
|---|---|
| 切 `string` 或 `string_view`，每段想要 `string_view` | `split` |
| 底层是 `istream_view` 之类的输入范围 | `lazy_split`，分隔符用单个元素 |
| 每段还要随机访问或 `size()` | `split`（底层随机访问时，段也是） |
| 按相邻元素的关系分段，而不是按固定的分隔符 | `chunk_by`（[[range.chunk]]） |
| 把各段重新连起来 | `join` 或 `join_with`（[[range.join]]） |

<details class="fine" markdown="1"><summary>其余条文</summary>

[range.split.view] ¶1–2：两个构造函数，第二个把单个元素包进 `single_view`。`end()` 在底层是公共范围时返回迭代器，否则返回哨位。

[range.split.iterator] ¶1–5：构造函数保存视图指针、当前位置和下一个分隔符；`base()` 返回当前段起点；`*it` 返回 `{当前起点, 分隔符起点}`；`++` 跳过分隔符并查找下一个；相等比较同时比较位置和 *trailing_empty_*。

[range.split.sentinel] ¶1：哨位保存底层的终点。

[range.lazy.split.view] ¶1–2 是 `lazy_split_view` 的两个构造函数。[range.lazy.split.outer]、[range.lazy.split.outer.value]、[range.lazy.split.inner] 逐一规定外层迭代器、段对象和内层迭代器的成员。

</details>
