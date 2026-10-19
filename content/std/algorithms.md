---
title: 算法库
summary: 第 26 章导读：算法只通过迭代器和范围接触数据；同一个算法为什么有经典版、std::ranges 版和并行版几种重载；读一个算法的条文时要看哪几项；本章各页讲什么。
status: draft
covers: algorithms.general, algorithm.syn
papers: P0896R4, P0024R2, P2562R1, P2248R8, P3179R9, P3136R1
related: algorithms.requirements, algorithms.parallel, algorithms.results, alg.req, iterator.requirements, range.req, structure.specifications
tags: 标准库, 算法, ranges, 导读
updated: 2026-10-19
---

!!! tldr
    - 第 26 章的算法不认识任何容器，只通过迭代器（或 C++20 的范围）读写元素，所以对自定义的数据结构同样适用。
    - 同一个算法往往有几组重载：经典的 `std::find`，C++20 的 `std::ranges::find`，以及以执行策略为第一个实参的并行版本。
    - 经典版本把要求写在模板形参的名字里，违反了是未定义行为；`ranges` 版本把语法要求写成概念约束，违反了是编译错误。
    - 每个算法的条文都按 *Constraints*、*Mandates*、*Preconditions*、*Effects*、*Returns*、*Complexity* 排列。复杂度条款是规范性的，常常决定谓词被调用几次。

## 同一个算法的几种写法

```cpp run ok
#include <algorithm>
#include <cassert>
#include <vector>
struct P { int id; };
int main() {
  std::vector<int> v{4, 7, 1, 7};
  auto a = std::find(v.begin(), v.end(), 7);  // 经典版本
  auto b = std::ranges::find(v, 7);           // 接受整个范围
  std::vector<P> ps{{1}, {2}};
  auto c = std::ranges::find(ps, 2, &P::id);  // 投影：比较 p.id
  assert(a == b && c == ps.begin() + 1);
}
```

¶1 第 26 章描述对容器和其他序列执行算法操作的组件。算法从不直接接触容器：`find` 拿到的是一对迭代器，或者一个范围，它只知道怎样移动迭代器、怎样读出元素。所以一个算法写一次，就能用于数组、`vector`、链表，以及任何提供了合适迭代器的自定义结构（[[algorithms.requirements#1]]）。

打开 `<algorithm>` 的概要（[algorithm.syn]），同一个算法通常有四到六个声明。以 `find` 为例：

| 写法 | 引入 | 要求怎样表达 | 违反要求时 |
|---|---|---|---|
| `std::find(first, last, v)` | C++98，C++20 起 `constexpr` | 模板形参名 `InputIterator` | {{ub}} |
| `std::find(std::execution::par, first, last, v)` | C++17 | 形参名 `ForwardIterator` | {{ub}} |
| `std::ranges::find(first, last, v, proj)`、`std::ranges::find(r, v, proj)` | C++20 | 概念约束 `input_iterator` 等 | 编译错误 |
| `std::ranges::find(std::execution::par, r, v, proj)` | C++26 | `random_access_iterator` 加 `sized_sentinel_for` | 编译错误 |

几点说明：

- 经典版本的模板形参不带约束，`InputIterator`、`ForwardIterator` 这些名字按 [[algorithms.requirements#4]] 带有规范含义。传入不满足要求的迭代器，编译器不保证诊断。
- `ranges` 版本的要求直接写成约束，不满足就不参与重载决议。它们一般多一个**投影**（[[g:projection]]）形参：比较或调用谓词之前，先对每个元素调用投影，上面的 `&P::id` 就是一个投影。它们也不是函数，而是对象，ADL 找不到它们，见 [[algorithms.requirements]]。
- 并行重载以执行策略为第一个实参，不是 `constexpr`，对迭代器的要求更高：经典并行版至少要前向迭代器，因为切分工作需要多趟遍历；C++26 的并行 `ranges` 版（[[P3179R9]]）要求能在常数时间内求出长度并随机访问。详见 [[algorithms.parallel]]。

!!! note "为什么 `ranges` 算法另起一套"
    C++20 的 Ranges（[[P0896R4]]）没有修改经典算法，而是在 `std::ranges` 里新增了一套。经典算法要求 `first` 和 `last` 类型相同，没有投影，返回值丢掉了一些已经算出的信息（`std::copy` 不返回输入走到了哪里），要求也只能靠文字表述。直接改签名会破坏既有代码，所以选择两套并存。

## 本章的版图

¶2 本章按表 85 分成下面几组。注意头文件并不都是 `<algorithm>`：

| 子条款 | 头文件 | 内容 |
|---|---|---|
| [[algorithms.requirements]] | | 全章通用的约定：形参名即要求、谓词的契约、算法函数对象 |
| [[algorithms.parallel]] | `<execution>` | 并行算法的语义；执行策略本身见 [[execpol]] |
| [[algorithms.results]] | `<algorithm>` | `ranges` 算法的返回类型 `in_out_result` 等 |
| [[alg.nonmodifying]] | `<algorithm>` | `find`、`count`、`equal`、`search`、`fold_left` 等 |
| [[alg.modifying.operations]] | `<algorithm>` | `copy`、`transform`、`remove`、`unique`、`rotate`、`shuffle` 等 |
| [[alg.sorting]] | `<algorithm>` | 排序、[[alg.binary.search\|二分查找]]、[[alg.set.operations\|集合运算]]、[[alg.heap.operations\|堆]]、[[alg.min.max\|最值]] |
| [[numeric.ops]] | `<numeric>` | `accumulate`、`reduce`、各种 scan |
| [[specialized.algorithms]] | `<memory>` | `uninitialized_copy`、`construct_at`、`destroy` |
| [[alg.rand]] | `<random>` | `ranges::generate_random` |
| [[alg.c.library]] | `<cstdlib>` | `qsort`、`bsearch` |

## 读一个算法的条文

本章的条文大多套用同一个格式（[[structure.specifications]]）。先用 "Let *E* be …" 定义一个条件表达式，让经典版和 `ranges` 版、有谓词和没有谓词的版本共用一段描述，然后依次列出：

| 元素 | 违反时的后果 | 典型内容 |
|---|---|---|
| *Constraints* | 不参与重载决议 | 多见于 `ranges` 版本 |
| *Mandates* | 非良构，必须诊断 | `Size` 能转换为整数类型；`*first` 能写入 `result` |
| *Preconditions* | {{ub}} | 区间有效、互不重叠、已经排序；`comp` 是严格弱序 |
| *Effects*、*Returns* | | 做什么、返回什么 |
| *Complexity* | 实现不符合标准 | 恰好 N 次赋值；至多 log₂N + O(1) 次比较 |
| *Remarks* | | 是否稳定（[[algorithm.stable]]），能否原地操作 |

复杂度条款值得细读，它常常是可以观察到的承诺。`std::count` 规定恰好调用 `last - first` 次谓词，`std::find` 规定至多这么多次。所以带副作用的谓词在 `count` 里被调用的次数是确定的，在 `find` 里则取决于在哪里找到。`adjacent_find` 规定恰好 `min((i - first) + 1, (last - first) - 1)` 次，实现不能为了加速而多比较。

注意 `ranges` 版本只把语法要求变成了约束。比较函数是否真的是严格弱序这类语义要求，编译器检查不了，违反了仍然是未定义行为。

## 独立实现中的算法

概要的第一行注释是 `// mostly freestanding`：独立实现（没有操作系统支持的实现，见 [[intro.compliance]]）也要提供本章的大部分算法。少数可能需要分配临时缓冲区的算法，如 `stable_sort`、`stable_partition`、`inplace_merge`，标注了 `// hosted`，只在宿主实现中提供。

并行重载标注了 `// freestanding-deleted`。按 [[freestanding.item#3]]，独立实现可以把这样的重载定义为弃置的，也可以照常提供，由实现决定。定义为弃置而不是直接去掉，是为了让同一个调用在两种实现上选中同一个重载。

## 演进

| 版本 | 主要变化 |
|---|---|
| C++98 | STL 算法整体并入标准；`sort` 只要求平均 O(N log N) |
| C++11 | `sort` 要求最坏 O(N log N)；新增 `all_of`/`any_of`/`none_of`、`is_sorted`、`minmax`、`move`、`shuffle` 等 |
| C++17 | 并行算法与执行策略（[[P0024R2]]）；`reduce` 与 scan 系列；`sample`、`clamp` |
| C++20 | 大部分算法成为 `constexpr`；`std::ranges` 算法（[[P0896R4]]）；`shift_left`/`shift_right` |
| C++23 | `ranges::fold_left` 等、`ranges::contains`、`ranges::starts_with`/`ends_with`、`ranges::find_last` |
| C++26 | `stable_sort` 等成为 `constexpr`（[[P2562R1]]）；值实参可以写成花括号列表（[[P2248R8]]）；并行 `ranges` 重载（[[P3179R9]]）；算法函数对象改为定制点对象（[[P3136R1]]） |
