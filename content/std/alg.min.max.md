---
title: 最值、clamp、字典序比较与排列生成
summary: min/max/minmax 返回 const T& 带来的悬垂引用、等价时返回哪一个（max 返回第一个、minmax 的 max 却是第二个、minmax_element 取最右的最大值）、允许显式模板实参的例外、min_element 系列、clamp 的前置条件、lexicographical_compare 与 lexicographical_compare_three_way，以及 next_permutation/prev_permutation 的“回绕”语义
status: done
covers: alg.clamp, alg.lex.comparison, alg.three.way, alg.permutation.generators
papers: P0896R4, P0025R1
related: alg.sorting, algorithms.results, algorithms.requirements, cmp, class.temporary
tags: 标准库, 算法, min, max, clamp, 字典序, 排列
updated: 2026-10-18
---

[alg.sorting] 的最后几个子条款都是“小算法”，但每个都藏着一两个值得 language lawyer 记住的精确规定：返回的是引用还是值、等价时取左边的还是右边的、空区间怎么办。

## `min`、`max`、`minmax`（[alg.min.max] ¶1–¶24）

### 两个实参的形式：返回 `const T&`

```cpp
template<class T> constexpr const T& min(const T& a, const T& b);
template<class T> constexpr const T& max(const T& a, const T& b);
template<class T> constexpr pair<const T&, const T&> minmax(const T& a, const T& b);
```

返回的是**引用**，指向实参之一。若实参是临时对象，引用在完整表达式结束时悬垂（[[class.temporary]]）：

```cpp run title="min_dangle.cpp" flags="-std=c++2c -O0 -fsanitize=address" ub
#include <algorithm>
#include <cstdio>
#include <string>

int main() {
    const std::string& r = std::min(std::string("apple"), std::string("banana"));
    std::printf("%s\n", r.c_str());   // UB：r 绑定到已销毁的临时对象
}
```

本机 Clang 23 对此给出 `-Wdangling` 警告（libc++ 在这些函数上标注了 `[[clang::lifetimebound]]`），运行时 ASan 报 `stack-use-after-scope`。用 `auto r = std::min(...)`（复制）即可。`ranges::min`/`ranges::max` 的双实参版同样返回 `const T&`，有同样的问题。

### 等价时返回哪个

- ¶2：`min` 在两实参等价时返回**第一个**；
- ¶10：`max` 在两实参等价时**也返回第一个**；
- ¶18：`minmax(a, b)` 在 `b` 小于 `a` 时返回 `{b, a}`，否则返回 `{a, b}`——所以等价时 `.first` 是 `a`、`.second` 是 `b`：**`minmax` 的 max 是第二个实参**，与 `max(a, b)` 不同！

这样设计是为了让 `minmax` 成为“稳定的二元素排序”：`{min, max}` 正是 `stable_sort({a, b})` 的结果。

### 区间形式：返回值，前置条件非空

`min(initializer_list<T>)`、`ranges::min(r)` 等返回**值**（`T` 或 `range_value_t<R>`），¶5 要求区间非空（`ranges::distance(r) > 0`），违反为 {{ub}}。¶6/¶14：多个等价最值时，`min` 和 `max` 都返回**最左**元素的副本。¶22：`minmax` 返回 `{最左的最小值, 最右的最大值}`。

### 允许显式模板实参

¶4、¶8 等的 *Remarks*：调用 `std` 中的这些重载时**可以**显式指定 `T`。这是 [[algorithms.requirements#15]]“显式模板实参的行为未指明”的明文例外。典型用途是混合类型：`std::max(1, 2L)` 推导冲突无法编译，`std::max<long>(1, 2L)` 合法。

## `min_element`、`max_element`、`minmax_element`（¶25–¶32）

返回**迭代器**；空区间返回 `last`（`minmax_element` 返回 `{first, first}`）。

- `min_element`：第一个最小元素；`max_element`：**第一个**最大元素；
- `minmax_element`：`{第一个最小, 最后一个最大}`，脚注 183 明说“This behavior intentionally differs from `max_element`”。理由同上：与稳定排序后的首尾一致。¶32：至多 max(⌊3(N−1)/2⌋, 0) 次比较——成对处理元素，每对先互比，再分别与当前最小、最大比较，比分别调用 `min_element` 与 `max_element` 的 2(N−1) 次少。

```cpp run title="minmax.cpp" ok
#include <algorithm>
#include <cassert>
#include <compare>
#include <vector>

int main() {
    std::vector<int> v{3, 1, 5, 1, 5};
    auto mx = std::max_element(v.begin(), v.end());
    auto [mn, mx2] = std::minmax_element(v.begin(), v.end());
    assert(mx - v.begin() == 2);       // max_element：最左的最大值
    assert(mx2 - v.begin() == 4);      // minmax_element：最右的最大值
    assert(mn - v.begin() == 1);       // 最左的最小值
    long m = std::max<long>(1, 2L);    // 显式模板实参：标准明确允许
    assert(m == 2);
    assert(std::clamp(15, 0, 10) == 10);
    std::vector a{1, 2, 3}, b{1, 2};
    auto c = std::lexicographical_compare_three_way(a.begin(), a.end(), b.begin(), b.end());
    assert(c == std::strong_ordering::greater);
    std::vector p{1, 2, 3};
    int n = 1;
    while (std::next_permutation(p.begin(), p.end())) ++n;
    assert(n == 6 && (p == std::vector{1, 2, 3}));   // 返回 false 时已回到升序
}
```

## `clamp`（[alg.clamp]）{{c++17}}

由 [[P0025R1]] 引入。¶2 *Preconditions*：`comp(hi, lo)` 为 `false`——即 `lo` 不大于 `hi`；`clamp(v, 10, 0)` 是 {{ub}}，不是“返回某个边界”。¶3：`v < lo` 返回 `lo`，`hi < v` 返回 `hi`，否则返回 `v`——返回的同样是 `const T&`，同样有悬垂风险。¶4 注 1：只要避开 NaN，`T` 可以是浮点类型（NaN 使 `<` 不再是严格弱序）。¶5：至多两次比较。

## 字典序比较（[alg.lex.comparison]）

¶3 的 *Remarks* 给出字典序的定义：长度相同且对应元素都等价 → 互不小于；一个是另一个的真前缀 → 短的更小；否则由第一对不等价元素决定。注 1：空序列小于任何非空序列，但不小于空序列。

¶2：至多 2·min(N1, N2) 次比较——每对元素最多比两次（`comp(a, b)` 判小于，`comp(b, a)` 判大于）。¶4 的示例实现正是如此。

## 三路比较（[alg.three.way]）{{c++20}}

`lexicographical_compare_three_way(b1, e1, b2, e2, comp)`：

- ¶2 *Mandates*：`decltype(comp(*b1, *b2))` 是比较类别类型（[[cmp.categories]]）——编译期检查；
- ¶3 *Returns*：第一个使 `comp(*(b1 + i), *(b2 + i)) != 0` 的结果；都相等则返回 `(e1 - b1) <=> (e2 - b2)`（长度比较）；
- ¶4：至多 N 次 `comp` 应用——每对只比一次，这正是三路比较相对 `lexicographical_compare` 的优势。

不带 `comp` 的版本使用 `compare_three_way()`。标准容器的 `operator<=>` 也是用它定义的，只是比较器换成了仅用于说明的 *synth-three-way*（对没有 `<=>` 的元素类型退回用 `<` 合成），见 [[container.opt.reqmts]]。

## 排列生成（[alg.permutation.generators]）

`next_permutation`：把序列变为按 `comp` 字典序的**下一个**排列；¶3：不存在时（已是最大排列，即降序）变为**第一个**排列（升序）并返回 `false`。`prev_permutation` 对称。¶5、¶10：至多 (last − first)/2 次交换。只需双向迭代器。

“回绕”语义使得经典循环 `do { ... } while (next_permutation(...))` 结束后，序列恰好回到升序。要枚举全部排列，起点必须是升序（已排序），否则只会枚举当前排列之后的那些。对含重复元素的序列，`next_permutation` 只生成**不同**的排列（因为它基于字典序）。ranges 版返回 `in_found_result`：`{last, found}`。

## 思考题

<details markdown="1">
<summary>1. `const auto& [lo, hi] = std::minmax(f(), g());` 中 `f()`、`g()` 返回 `int`，安全吗？</summary>

不安全。`minmax` 返回 `pair<const int&, const int&>`，引用的是两个临时 `int`；结构化绑定的 `const auto&` 只延长了**那个 `pair` 临时对象**的生命期，不延长它所引用的 `int` 临时对象。完整表达式结束后 `lo`、`hi` 悬垂。应写 `auto [lo, hi] = std::minmax({f(), g()});`（`initializer_list` 版返回 `pair<T, T>` 值）或先存到变量里。
</details>

<details markdown="1">
<summary>2. `std::max(a, b)` 与 `std::minmax(a, b).second` 在 `a`、`b` 等价时分别返回谁？为什么不统一？</summary>

前者返回 `a`（¶10），后者返回 `b`（¶18）。`max` 的规则源自 C++98（返回第一个），已无法改动；`minmax` 是 C++11 新增的，按稳定排序的语义设计：`{min, max}` 应当等于对 `{a, b}` 做 `stable_sort` 的结果，等价时保持原顺序 `{a, b}`。
</details>

## 小结

| 函数 | 返回 | 等价时 | 坑 |
|---|---|---|---|
| `min(a, b)` / `max(a, b)` | `const T&` | 都返回第一个 | 临时对象 → 悬垂 |
| `minmax(a, b)` | `pair<const T&, const T&>` | `{a, b}`（max 是 b） | 同上 |
| `min(il)` / `max(il)` | 值 | 最左者 | 空区间 UB |
| `max_element` / `minmax_element` | 迭代器 | 最左的最大 / 最右的最大 | — |
| `clamp` | `const T&` | — | `hi < lo` 是 UB；NaN |
| `lexicographical_compare` | `bool` | — | ≤ 2·min(N1,N2) 次比较 |
| `lexicographical_compare_three_way` | 比较类别 | — | ≤ min(N1,N2) 次 |
| `next_permutation` | `bool` | — | 回绕到升序并返回 false |
