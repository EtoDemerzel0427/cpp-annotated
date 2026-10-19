---
title: chunk、slide、chunk_by、stride 视图
summary: C++23 的四个分组与步进视图：chunk(n) 切成不重叠的块，slide(n) 给出重叠的窗口，chunk_by(pred) 按相邻元素的关系分段，stride(n) 每隔 n 个取一个；n 必须为正，几个视图在必要时缓存 begin() 或 end()。
status: done
covers: range.chunk, range.chunk.overview, range.chunk.view.input, range.chunk.outer.iter, range.chunk.outer.value, range.chunk.inner.iter, range.chunk.view.fwd, range.chunk.fwd.iter, range.slide, range.slide.overview, range.slide.view, range.slide.iterator, range.slide.sentinel, range.chunk.by, range.chunk.by.overview, range.chunk.by.view, range.chunk.by.iter, range.stride, range.stride.overview, range.stride.view, range.stride.iterator
since: c++23
papers: P2442R1, P2443R1, P1899R3
related: range.adaptors, range.zip, range.split, range.take, range.nonprop.cache, range.counted, range.filter, range.drop
tags: 标准库, 范围, chunk, slide, chunk_by, stride
updated: 2026-10-19
---

!!! tldr
    - 对 `1 2 3 4 5`：`chunk(2)` 得 `[1,2] [3,4] [5]`，`slide(2)` 得 `[1,2] [2,3] [3,4] [4,5]`，`stride(2)` 得 `1 3 5`。
    - `chunk_by(pred)` 对每一对相邻元素调用 `pred`，结果为 `false` 的地方切开；`chunk_by(less_equal{})` 把序列切成一段段非递减的子序列。
    - `chunk`、`slide`、`stride` 的 n 必须大于 0，否则是未定义行为。
    - `chunk` 在输入范围上把读取位置保存在视图里，只能单趟遍历；没读完一块就前进，剩下的元素会被跳过。
    - `stride` 记住最后一步少走了几个，所以反向遍历落在与正向相同的元素上。

| 视图 | 结果 | 输入 `1 2 3 4 5` |
|---|---|---|
| `chunk(2)` | 不重叠的块，最后一块可以不满 | `[1,2] [3,4] [5]` |
| `slide(2)` | 重叠的窗口，元素少于 n 个时为空 | `[1,2] [2,3] [3,4] [4,5]` |
| `chunk_by(less{})` | 相邻元素使谓词为 `true` 就留在同一段 | `[1,2,3,4,5]` |
| `stride(2)` | 每 n 个取第一个 | `1 3 5` |

`chunk` 和 `slide` 来自 [[P2442R1]]，`chunk_by` 来自 [[P2443R1]]，`stride` 来自 [[P1899R3]]。

!!! impl "实现现状"
    截至写作时，本机 libc++ 提供了 `views::chunk_by` 和 `views::stride`，还没有 `views::chunk` 和 `views::slide`（`<version>` 中的 `__cpp_lib_ranges_chunk`、`__cpp_lib_ranges_slide` 被注释掉）。下文 `chunk` 的代码按标准原文编写，没有经过编译验证。

## `views::chunk`：不重叠的块 [range.chunk]

```cpp
#include <cstdio>
#include <ranges>
#include <vector>

int main() {
  std::vector<int> v{1, 2, 3, 4, 5};
  for (auto blk : v | std::views::chunk(2)) {
    std::printf("[");
    for (int x : blk) std::printf("%d", x);
    std::printf("]");
  }
  std::puts("");                              // [12][34][5]
}
```

[range.chunk.overview] ¶1 `chunk_view` 接受一个视图和一个数 N，按顺序给出由原视图元素组成、每块 N 个、互不重叠的视图；最后一块可以少于 N 个。¶2 `views::chunk(E, N)` 等价于 `chunk_view(E, N)`。构造函数的前置条件是 `n > 0`，所以 `chunk(0)` 是{{ub}}。

标准为 `chunk_view` 写了两份定义：底层只是输入范围时用一份，底层是前向范围时用另一份。

### 输入范围：状态在视图里 [range.chunk.view.input]

单趟序列只有一个读取位置，不可能让两个迭代器各自停在不同的地方。所以这一版把当前位置 `current_`（一个 [[range.nonprop.cache|non-propagating-cache]]）和本块还剩几个元素 `remainder_` 都存在视图对象里，外层迭代器（[range.chunk.outer.iter]）和内层迭代器（[range.chunk.inner.iter]）都只保存一个指向视图的指针。¶3 `begin()` 设置 `current_` 为底层的起点，`remainder_` 为 n。

由此得到几个性质：

- 只能单趟遍历，没有 const 版本的 `begin()`。
- 外层迭代器的 `value_type`（[range.chunk.outer.value]）表示当前这一块，遍历它就是从流中继续读取。
- 一块没有读完就前进外层迭代器时，外层会先把这一块剩下的元素读掉，下一块才能从正确的位置开始。

### 前向范围：每块是底层的一段 [range.chunk.view.fwd]

底层是前向范围时，迭代器（[range.chunk.fwd.iter]）自己保存当前块的起点 `current_`、底层终点 `end_`、块长 n，以及最后一块缺了几个元素 `missing_`，后者用于反向遍历时对齐。

解引用返回 `views::take(subrange(current_, end_), n)`。按 [[range.take]] 的规则，底层随机访问且 sized 时，这就是一个 `subrange`，可以随机访问，也有 `size()`。迭代器类别与底层相同，最高到随机访问；`iterator_category` 固定为 `input_iterator_tag`，因为解引用得到的是纯右值。

两份定义的 `size()` 都是底层大小除以 n 向上取整。`chunk_view` 在底层是前向范围且是借用范围时也是[[g:borrowed-range|借用范围]]。

## `views::slide`：重叠的窗口 [range.slide]

¶1 `slide_view` 的第 M 个元素是原视图第 M 到第 M+N−1 个元素上的一个视图；原视图不足 N 个元素时结果为空。¶2 `views::slide(E, N)` 等价于 `slide_view(E, N)`。[range.slide.view] ¶1 前置条件是 `n > 0`。

和 [[range.zip]] 中的 `adjacent<N>` 相比，`slide` 的窗口长度在运行时给出，元素是一个子范围而不是 tuple：[range.slide.iterator] ¶6 解引用返回 `views::counted(current_, n)`（[[range.common]]），底层连续时就是一个 `span`。底层必须是前向范围。

### 缓存起点还是终点

窗口迭代器常常需要知道窗口的最后一个元素在哪里。标准用三个说明用概念决定怎样处理：

| 概念 | 条件 | 做法 |
|---|---|---|
| *slide-caches-nothing* | 底层随机访问且 sized | `begin()`、`end()` 都能 O(1) 算出，不缓存，可以 const 遍历 |
| *slide-caches-last* | 不满足上一条，底层双向且是公共范围 | ¶6 `end()` 用 `ranges::prev(end, n - 1)` 求最后一个窗口的起点；¶7 缓存 `end()` |
| *slide-caches-first* | 其他 | 迭代器还记着当前窗口的最后一个元素；¶3 `begin()` 要先走 n−1 步，¶4 缓存 `begin()` |

后两种情况都要修改视图对象，所以没有 const 版本的遍历。`slide_view` 的借用性与底层相同。¶9 `size()` 是底层大小减 n 加 1，最小为 0。

## `views::chunk_by`：按相邻关系分段 [range.chunk.by]

¶1 `chunk_by_view` 接受一个视图和一个谓词，在每一对使谓词返回 `false` 的相邻元素之间切开。¶2 `views::chunk_by(E, F)` 等价于 `chunk_by_view(E, F)`。

```cpp run ok
#include <cstdio>
#include <functional>
#include <ranges>
#include <vector>

int main() {
  std::vector<int> v{1, 2, 2, 3, 0, 4, 5, 2};
  for (auto run : v | std::views::chunk_by(std::ranges::less_equal{})) {
    std::printf("[");
    for (int x : run) std::printf("%d", x);
    std::printf("]");
  }
  std::puts("");                                // [1223][045][2]
}
```

谓词是二元的，比较的是相邻的两个元素，而不是当前元素和本段的第一个元素。上例在 `3, 0` 和 `5, 2` 之间切开，因为 `3 <= 0` 和 `5 <= 2` 都不成立。

- 底层必须是前向范围；元素类型是 `subrange<iterator_t<V>>`；迭代器（[range.chunk.by.iter]）保存当前段的起点和下一段的起点，最高是双向迭代器。
- [range.chunk.by.view] ¶8 下一段的起点由 `adjacent_find(current, end, not_fn(pred))` 再前进一步得到。¶4 `begin()` 要先找出第一段的终点，¶5 因此缓存结果，没有 const 版本的 `begin()`。
- `chunk_by_view` 不是借用范围。

它与 [[range.split]] 的区别：`split` 按固定的分隔符切，分隔符本身被丢掉；`chunk_by` 按相邻元素的关系切，不丢任何元素。

## `views::stride`：每隔 n 个取一个 [range.stride]

¶1 `stride_view` 遍历底层序列时，每次前进 n 个元素而不是 1 个。¶2 `views::stride(E, N)` 等价于 `stride_view(E, N)`。[range.stride.view] ¶1 前置条件是 `n > 0`。

```cpp run ok
#include <cstdio>
#include <ranges>

int main() {
  auto input = std::views::iota(0, 12) | std::views::stride(3);
  for (int x : input) std::printf("%d ", x);                         // 0 3 6 9
  for (int x : input | std::views::reverse) std::printf("%d ", x);   // 9 6 3 0
  for (int x : std::views::iota(0, 10) | std::views::stride(3) | std::views::reverse)
    std::printf("%d ", x);                                           // 9 6 3 0
  std::puts("");
}
```

前两行是 [range.stride.overview] ¶3 的例 1。第三行的底层是 `0..9`，从 9 往前每次退 3 恰好也是 `9 6 3 0`；关键在于反向遍历的起点不是底层最后一个元素，而是正向遍历最后到达的那个元素。

为了做到这一点，迭代器（[range.stride.iterator]）除了当前位置、底层终点和步长，还保存 `missing_`：`++` 用 `ranges::advance(current_, n, end_)` 前进，遇到终点就停，并记下这一步少走了几个。`--` 时先把少走的补回来，再按步长后退，所以反向遍历的位置与正向完全一致。

`stride_view` 的迭代器类别与底层相同，最高到随机访问；¶4 `size()` 是底层大小除以 n 向上取整；不做缓存；借用性与底层相同。

## 小结

| 视图 | 底层要求 | 元素 | 缓存 | 借用范围 |
|---|---|---|---|---|
| `chunk(n)` | 输入或前向 | 一块；前向时是 `take(subrange, n)` | 输入版的状态在视图里 | 底层前向且借用时 |
| `slide(n)` | 前向 | `views::counted(it, n)` | 视底层而定：不缓存、缓存 `begin()` 或缓存 `end()` | 底层是时 |
| `chunk_by(p)` | 前向 | `subrange` | 缓存 `begin()` | 否 |
| `stride(n)` | 输入 | 底层元素 | 无 | 底层是时 |

<details class="fine" markdown="1"><summary>其余条文</summary>

[range.chunk.view.input] ¶2、[range.chunk.view.fwd] ¶2、[range.slide.view] ¶2、[range.stride.view] ¶2：构造函数保存底层视图和 n。[range.chunk.view.input] ¶4 `end()` 返回 `default_sentinel`。各视图的 `reserve_hint()` 用与 `size()` 相同的公式。

[range.chunk.by.view] ¶1–3、¶7、¶9–¶10：构造函数、`pred()`、谓词存在的前置条件，以及反向查找上一段起点的 *find-prev*。[range.slide.sentinel] 的哨位只在底层既属于 *slide-caches-first*、又不是公共范围时使用（[range.slide.view] ¶6.4）。[range.stride.view] ¶3 `stride()` 返回步长。

</details>
