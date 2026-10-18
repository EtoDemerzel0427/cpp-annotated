---
title: chunk、slide、chunk_by、stride 视图
summary: C++23 的分组与步进视图——chunk(n) 不重叠分块（输入范围版本把状态存在视图里、前向版本的元素是 take(subrange, n)）、slide(n) 重叠窗口（slide-caches-nothing/first/last 三种缓存策略）、chunk_by(pred) 按相邻关系分段（begin 缓存，元素为 subrange）、stride(n) 每隔 n 个取一个（为支持反向迭代记录 missing_）；n 必须为正。
status: done
covers: range.chunk, range.chunk.overview, range.chunk.view.input, range.chunk.outer.iter, range.chunk.outer.value, range.chunk.inner.iter, range.chunk.view.fwd, range.chunk.fwd.iter, range.slide, range.slide.overview, range.slide.view, range.slide.iterator, range.slide.sentinel, range.chunk.by, range.chunk.by.overview, range.chunk.by.view, range.chunk.by.iter, range.stride, range.stride.overview, range.stride.view, range.stride.iterator
since: c++23
papers: P2442R1, P2443R1, P1899R3
related: range.adaptors, range.zip, range.split, range.take, range.nonprop.cache, range.counted, range.filter, range.drop
tags: 标准库, 范围, chunk, slide, chunk_by, stride
updated: 2026-10-18
---

四个"重新组织序列"的视图：

| 视图 | 结果 | 例（输入 `1 2 3 4 5`） |
|---|---|---|
| `chunk(2)` | 不重叠的块，最后一块可能不足 | `[1,2] [3,4] [5]` |
| `slide(2)` | 重叠的窗口，元素少于 n 时为空 | `[1,2] [2,3] [3,4] [4,5]` |
| `chunk_by(pred)` | 相邻元素满足 `pred` 就留在同一段 | `chunk_by(less)` → `[1,2,3,4,5]` |
| `stride(2)` | 每 n 个取第一个 | `1 3 5` |

`chunk`/`slide` 来自 [[P2442R1]]，`chunk_by` 来自 [[P2443R1]]，`stride` 来自 [[P1899R3]]。

!!! impl "实现现状"
    截至编写时 libc++ 提供了 `views::chunk_by` 与 `views::stride`，但**尚未提供** `views::chunk` 与 `views::slide`（其 `<version>` 中 `__cpp_lib_ranges_chunk`、`__cpp_lib_ranges_slide` 仍被注释掉）。下文 `chunk`/`slide` 的示例按标准编写，未经本站环境运行验证。

## `views::chunk`（[range.chunk]）

¶1 `chunk_view` 接受一个视图和数 N，产生由 N 个元素组成的、不重叠的、相继的块组成的范围；最后一块可以少于 N 个元素。¶2 `views::chunk(E, N)` 表达式等价于 `chunk_view(E, N)`。构造的前置条件是 `n > 0`——`chunk(0)` 是{{ub}}。

标准为它写了**两个**类模板定义（同一模板的约束不同的偏特化式定义）：

### 输入范围版本（[range.chunk.view.input] 至 [range.chunk.inner.iter]）

```cpp
template<view V> requires input_range<V>
class chunk_view : public view_interface<chunk_view<V>> {
  V base_;
  range_difference_t<V> n_;
  range_difference_t<V> remainder_ = 0;
  non-propagating-cache<iterator_t<V>> current_;
  class outer-iterator;
  class inner-iterator;
public:
  constexpr outer-iterator begin();     // current_ = begin(base_); remainder_ = n_;
  constexpr default_sentinel_t end() const noexcept;
  constexpr auto size() requires sized_range<V>;   // div-ceil(distance, n)
};
```

对单趟序列，"当前位置"只能有一个——所以它和"本块还剩几个"（`remainder_`）都存在**视图对象**里（[[range.nonprop.cache]]）。外层迭代器（[range.chunk.outer.iter]）与内层迭代器（[range.chunk.inner.iter]）都只是指向父视图的指针。后果：

- 只能单趟，没有 const `begin()`；
- 若没把一块读完就 `++` 外层迭代器，外层会把本块剩余元素**跳过**（消费掉），以便下一块从正确位置开始；
- 外层的 `value_type`（[range.chunk.outer.value]）是一个代表"当前块"的范围，其迭代器就是 *inner-iterator*。

### 前向范围版本（[range.chunk.view.fwd]、[range.chunk.fwd.iter]）

```cpp
template<view V> requires forward_range<V>
class chunk_view<V> : public view_interface<chunk_view<V>>;
```

迭代器存 `current_`、`end_`、`n_` 以及 `missing_`（最后一块缺多少，用于反向迭代时对齐）。`operator*` 返回 `views::take(subrange(current_, end_), n_)`——所以**元素类型是 `take` 作用在 `subrange` 上的结果**：对随机访问+sized 的底层，按 [[range.take]] 的规则它会退化成 `subrange`（若底层是 `span` 之类则为对应类型），可随机访问、有 `size()`。迭代器强度最高随机访问（`iterator_category` 固定为 input，因为元素是 prvalue）。借用性：`enable_borrowed_range<chunk_view<V>>` = `forward_range<V> && enable_borrowed_range<V>`。

```cpp run
#include <ranges>
#include <vector>
#include <cstdio>
int main() {
  std::vector<int> v{1, 2, 3, 4, 5};
  for (auto blk : v | std::views::chunk(2)) {       // 标准 C++23；libc++ 尚未提供
    std::printf("[");
    for (int x : blk) std::printf("%d", x);
    std::printf("]");
  }
  std::puts("");   // [12][34][5]
}
```

## `views::slide`（[range.slide]）

¶1 `slide_view` 产生一个视图，其第 M 个元素是原视图第 M 到第 M+N−1 个元素上的视图；原视图元素少于 N 时结果为空。¶2 `views::slide(E, N)` 表达式等价于 `slide_view(E, N)`。前置条件 `n > 0`。

与 `adjacent<N>`（[[range.zip]]）相比：窗口大小是**运行时**的，元素是**子范围**（`views::counted(current_, n_)`，对连续底层就是 `span`）而不是元组。要求**前向**底层。

`slide_view` 的规范引入了三个说明用概念，决定是否缓存：

```cpp
template<class V> concept slide-caches-nothing = random_access_range<V> && sized_range<V>;
template<class V> concept slide-caches-last =
  !slide-caches-nothing<V> && bidirectional_range<V> && common_range<V>;
template<class V> concept slide-caches-first =
  !slide-caches-nothing<V> && !slide-caches-last<V>;
```

- *caches-nothing*：随机访问+sized，`begin`/`end` 都能 O(1) 算出，有 const 迭代；
- *caches-first*：迭代器要同时记住窗口的首和尾（`last_ele_`），`begin()` 要走 n−1 步才能得到第一个窗口的尾——[range.slide.view] ¶4 规定缓存 `begin()`；
- *caches-last*：双向+common 时，`end()` 用 `ranges::prev(end, n-1)` 求得最后一个窗口的起点——¶7 规定缓存 `end()`。

后两种都没有 const 迭代。借用性随底层。

## `views::chunk_by`（[range.chunk.by]）

¶1 `chunk_by_view` 接受一个视图和一个谓词，在每一对使谓词为 `false` 的相邻元素之间切开。¶2 `views::chunk_by(E, F)` 表达式等价于 `chunk_by_view(E, F)`。

```cpp
template<forward_range V, indirect_binary_predicate<iterator_t<V>, iterator_t<V>> Pred>
  requires view<V> && is_object_v<Pred>
class chunk_by_view : public view_interface<chunk_by_view<V, Pred>>;
```

- 谓词是**二元**的，判断的是**相邻**两个元素，而不是"与本段第一个元素"——`chunk_by(less_equal{})` 把序列切成一段段**非递减的连续子序列**；
- 元素类型是 `subrange<iterator_t<V>>`；迭代器存当前段的首 `current_` 与下一段的首 `next_`（[range.chunk.by.iter]），最高双向；
- [range.chunk.by.view] ¶5：`begin()` 要找第一段的尾（线性），所以**缓存**；没有 const 迭代、不借用；
- 与 `split` 的区别：`split` 按固定的分隔符模式切、分隔符被丢弃；`chunk_by` 按相邻关系切、不丢弃任何元素。

## `views::stride`（[range.stride]）

¶1 `stride_view` 呈现底层序列的一个视图，每次前进 n 个元素而不是 1 个。¶2 `views::stride(E, N)` 表达式等价于 `stride_view(E, N)`。[range.stride.view] ¶1：构造的前置条件是 `stride > 0`。

- 迭代器存 `current_`、`end_`、`stride_` 与 `missing_`：`++` 用 `ranges::advance(current_, stride_, end_)` 以末尾为界前进，并记下最后一步"差了几个"（`missing_`）；`--` 时先补回这个差额，保证反向遍历落在与正向相同的位置上——这是标准例 1 中 `iota(0, 12) | stride(3) | reverse` 输出 `9 6 3 0` 而不是 `11 8 5 2` 的原因；
- 强度随底层（最高随机访问），`size()` = `div-ceil(size, n)`，借用性随底层，没有缓存。

```cpp run ok
#include <functional>
#include <ranges>
#include <vector>
#include <cstdio>
int main() {
  std::vector<int> v{1, 2, 2, 3, 0, 4, 5, 2};
  for (auto run : v | std::views::chunk_by(std::ranges::less_equal{})) {
    std::printf("[");
    for (int x : run) std::printf("%d", x);
    std::printf("]");
  }
  std::puts("");   // [1223][045][2]
  for (int x : std::views::iota(0, 10) | std::views::stride(3)) std::printf("%d ", x);
  for (int x : std::views::iota(0, 10) | std::views::stride(3) | std::views::reverse) std::printf("%d ", x);
  std::puts("");   // 0 3 6 9 9 6 3 0
  for (int x : std::views::repeat(7, 3)) std::printf("%d", x);
  std::puts("");   // 777
}
```

## 小结

| 视图 | 底层要求 | 元素 | begin/end 缓存 | 借用 |
|---|---|---|---|---|
| `chunk(n)` | input（单趟版本）/ forward | 块（forward 版为 `take(subrange, n)`） | 输入版状态在视图里 | forward 且底层借用时 |
| `slide(n)` | forward | `views::counted(it, n)` 子范围 | 视底层：不缓存 / 缓存 begin / 缓存 end | 随底层 |
| `chunk_by(p)` | forward | `subrange` | 缓存 begin | 否 |
| `stride(n)` | input | 底层元素 | 无 | 随底层 |
