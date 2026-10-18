---
title: 算法库
summary: 第 26 章导读——<algorithm>/<numeric>/<memory>/<random>/<cstdlib> 中“迭代器参数化”的通用算法：三代接口（经典 std::、C++20 受约束的 std::ranges::、并行重载）如何共存，读每个算法条文时应盯住的 Constraints/Mandates/Preconditions/Complexity 四要素，以及本章各页的阅读路线
status: draft
covers: algorithms.general, algorithm.syn
papers: P0896R4, P0024R2
related: algorithms.requirements, algorithms.parallel, algorithms.results, alg.req, iterator.requirements, range.req, structure.specifications
tags: 标准库, 算法, ranges, 导读
updated: 2026-10-18
---

第 26 章是 STL 的“A”。容器（第 23 章）负责**存**，迭代器（第 24 章）负责**走**，本章负责**算**——而且算法对容器一无所知，只通过迭代器（或 C++20 的 range）接触元素。这条设计纪律决定了本章几乎所有条文的写法：每个算法的契约都表述为“对迭代器类型、对函数对象、对区间内容”的要求，外加一个**复杂度保证**。

读懂本章需要先掌握：

- 迭代器类别与两套要求体系：*Cpp17* 具名要求（[[iterator.requirements]]）与 C++20 迭代器概念（[[iterator.concepts]]）；
- 算法专用的概念：`indirectly_copyable`、`sortable`、`mergeable` 等（[[alg.req]]），以及 `projected`、`indirect_strict_weak_order` 等间接可调用概念（[[indirectcallable]]）；
- range 与 sentinel（[[range.req]]）、borrowed range 与 `ranges::dangling`；
- 库条文的描述格式：*Constraints* / *Mandates* / *Preconditions* / *Effects* / *Returns* / *Complexity* / *Remarks*（[[structure.specifications]]）。

## 本章的版图（[algorithms.general]）

¶1–¶2 只是目录：本章描述对容器和其他序列执行算法操作的组件，按表 85 分组。值得注意的是**头文件归属**并不都是 `<algorithm>`：

| 子条款 | 头文件 | 本站页面 |
|---|---|---|
| [[algorithms.requirements]] 通用约定 | — | 深度页：模板形参名即要求、谓词规则、niebloid |
| [[algorithms.parallel]] 并行算法 | `<execution>` | 深度页：元素访问函数、执行策略语义、异常即 terminate；执行策略本身见 [[execpol]] |
| [[algorithms.results]] 结果类型 | `<algorithm>` | `in_out_result` 等 |
| [[alg.nonmodifying]] 不修改序列的操作 | `<algorithm>` | `find`、`count`、`equal`、`search`、`fold_left`… |
| [[alg.modifying.operations]] 修改序列的操作 | `<algorithm>` | `copy`、`transform`、`remove`、`unique`、`rotate`、`sample`、`shuffle`… |
| [[alg.sorting]] 排序及相关 | `<algorithm>` | 拆为 [[alg.sorting\|排序]]、[[alg.binary.search\|二分与划分]]、[[alg.set.operations\|归并与集合]]、[[alg.heap.operations\|堆]]、[[alg.min.max\|最值/比较/排列]] |
| [[numeric.ops]] 广义数值运算 | `<numeric>` | `accumulate` vs `reduce`、scan 系列；另见 [[numeric.sat\|gcd/lcm/midpoint/饱和算术]] |
| [[specialized.algorithms]] | `<memory>` | `uninitialized_*`、`construct_at`、`destroy` |
| [[alg.rand]] | `<random>` | `ranges::generate_random` |
| [[alg.c.library]] | `<cstdlib>` | `qsort`、`bsearch` |

## 三代接口并存（[algorithm.syn]）

打开 `<algorithm>` 概要会看到同一个算法往往有**四到六个**声明。以 `find` 为例：

```cpp
// 1. 经典版本（C++98 起；C++20 起 constexpr）
template<class InputIterator, class T = iterator_traits<InputIterator>::value_type>
  constexpr InputIterator find(InputIterator first, InputIterator last, const T& value);
// 2. 并行重载（C++17）
template<class ExecutionPolicy, class ForwardIterator, class T = ...>
  ForwardIterator find(ExecutionPolicy&& exec, ForwardIterator first, ForwardIterator last,
                       const T& value);
namespace ranges {
  // 3./4. 受约束版本（C++20）：迭代器+哨位 / 整个 range，支持投影
  template<input_iterator I, sentinel_for<I> S, class Proj = identity, class T = ...>
    requires indirect_binary_predicate<ranges::equal_to, projected<I, Proj>, const T*>
    constexpr I find(I first, S last, const T& value, Proj proj = {});
  template<input_range R, class Proj = identity, class T = ...> ...
    constexpr borrowed_iterator_t<R> find(R&& r, const T& value, Proj proj = {});
  // 5./6. 并行 ranges 版本（C++26）：要求随机访问 + sized
  template<execution-policy Ep, random_access_iterator I, sized_sentinel_for<I> S, ...>
    I find(Ep&& exec, I first, S last, const T& value, Proj proj = {});
  template<execution-policy Ep, sized-random-access-range R, ...> ...
}
```

几条读概要时的要点：

1. **经典版本的要求写在模板形参名里**。`InputIterator`、`ForwardIterator` 这些名字不是装饰，它们按 [[algorithms.requirements#4]] 被赋予了法律含义；违反是“未满足前置条件”，{{ub}}，编译器不保证诊断。
2. **`ranges::` 版本的要求写在约束里**，并普遍多一个**投影**（[[g:projection]]）形参。不满足就不参与重载决议，得到的是编译错误。另外它们不是函数而是**算法函数对象**（[[alg.func.obj]]），ADL 找不到、不能显式给模板实参，见 [[algorithms.requirements]]。
3. **并行重载没有 `constexpr`**，而且对迭代器类别的要求更高：经典并行版至少 `ForwardIterator`（输入迭代器的单趟性与切分工作不相容），并行 ranges 版要求 `random_access_iterator` + `sized_sentinel_for`（概念 *sized-random-access-range* 定义在 [[range.req]]）。
4. **freestanding**：概要首行注释为 `// mostly freestanding`。逐个声明上标注了 `// hosted`（如 `stable_sort`、`inplace_merge`、`stable_partition`——它们可能需要分配临时缓冲区）或 `// freestanding-deleted`（并行重载）。后者的含义是：在独立实现中该重载**存在但被定义为弃置**，这样重载决议结果在 hosted 与 freestanding 实现之间保持一致（规则见 [[freestanding.item]]）。
5. **C++26 的并行 ranges 重载**常带一个**有界输出**：`ranges::copy(exec, r, out_r)` 的输出也是一个 range，写满即停。为此结果类型里多了 `reverse_copy_truncated_result`、`set_difference_truncated_result` 这样的别名，*Returns* 也多了“若 N 等于 M……否则……”的分支（例如 [[alg.copy#23]]）。

!!! note "为什么 `ranges::` 算法要另起炉灶"
    C++20 Ranges（[[P0896R4]]）没有修改 `std::sort` 等经典算法，而是在 `std::ranges` 中新增一套：经典算法的签名要求 `first`、`last` 同类型、没有投影、返回值信息不全（`std::copy` 丢掉了输入的终点），且要求只能靠文字表述无法检查。改签名会破坏 ABI 和既有代码，所以选择并存。

## 读每个算法条文时盯住什么

本章条文大多是同一个模板：先 “Let *E* be …” 定义一个统一的条件表达式（让 `std::`/`ranges::`、有无谓词、有无投影的多个版本共用一段描述），然后是：

| 元素 | 违反时的后果 | 典型内容 |
|---|---|---|
| *Constraints* | 不参与重载决议 | 多出现在 `ranges::` 版本和 `midpoint` 之类 |
| *Mandates* | 非良构（必须诊断） | “`Size` 可转换为整数类型”“`*first` 可写入 `result`” |
| *Preconditions* | {{ub}} | 区间有效、不重叠、已排序/已划分、`comp` 是严格弱序 |
| *Complexity* | 实现不符合标准 | “恰好 N 次赋值”“至多 log₂N + O(1) 次比较” |
| *Remarks* | — | 稳定性（[[algorithm.stable]]）、是否允许原地 |

复杂度条款值得认真读：它常常是**可观察**的承诺。例如 `std::count` 规定“恰好 `last - first` 次谓词调用”，`std::find` 规定“至多”——所以带副作用的谓词在 `find` 中被调用的次数取决于命中位置，在 `count` 中则是确定的。又如 `adjacent_find` 的非并行版本规定恰好 `min((i - first) + 1, (last - first) - 1)` 次——实现不能“预读”。

## 本章的历史脉络

- **C++98**：STL 算法整体并入，`sort` 只要求平均 O(N log N)；
- **C++11**：`sort` 改为最坏 O(N log N)（现行 ¶5 只写 O(N log N)，不再说“平均”），新增 `all_of`/`any_of`/`none_of`、`is_sorted`、`is_partitioned`、`minmax`、`move`、`shuffle` 等；
- **C++17**：并行算法与执行策略（[[P0024R2]]），`reduce`/scan 系列，`sample`、`clamp`、`gcd`/`lcm`；
- **C++20**：大批算法 `constexpr`、`std::ranges` 受约束算法（[[P0896R4]]）、`shift_left`/`shift_right`、`midpoint`、`lexicographical_compare_three_way`；
- **C++23**：`ranges::fold_*`、`ranges::contains`、`ranges::starts_with`/`ends_with`、`ranges::find_last`、`ranges::iota`；
- **C++26**：`constexpr stable_sort` 等（[[P2562R1]]）、饱和算术、`ranges::generate_random`、算法支持花括号初始化的值实参（[[P2248R8]]）、并行 ranges 重载，以及把算法函数对象重新定义为定制点对象。

## 核心要点

- 算法只通过迭代器/range 与数据交互；要求写在模板形参名（经典）或概念约束（ranges）里。
- 经典算法违反要求是 UB，ranges 算法违反语法要求是编译错误（但语义要求如“严格弱序”仍是 UB）。
- 复杂度条款是规范性承诺，常常决定了谓词被调用的确切次数。
- 并行重载不是 `constexpr`、要求更强的迭代器、元素访问函数抛异常即 `terminate`。
