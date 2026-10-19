---
title: 最值、clamp、字典序比较与排列生成
summary: min、max、minmax 返回引用带来的悬垂问题，等价时各返回哪一个；min_element 系列、clamp 的前置条件；lexicographical_compare 与三路版本；next_permutation 与 prev_permutation 在最后一个排列之后回到第一个。
status: done
covers: alg.clamp, alg.lex.comparison, alg.three.way, alg.permutation.generators
papers: P0896R4, P0025R1
related: alg.sorting, algorithms.results, algorithms.requirements, cmp, class.temporary
tags: 标准库, 算法, min, max, clamp, 字典序, 排列
updated: 2026-10-19
---

!!! tldr
    - 两个实参的 `min`、`max`、`minmax` 以及 `clamp` 返回指向实参的引用，实参是临时对象时，结果在完整表达式结束后悬垂。
    - 两个实参等价时，`min` 和 `max` 都返回第一个；`minmax(a, b)` 返回 `{a, b}`，所以它的 max 是第二个实参。
    - `max_element` 返回最左边的最大元素，`minmax_element` 返回最右边的最大元素。
    - `clamp(v, lo, hi)` 要求 `lo` 不大于 `hi`，否则是未定义行为。
    - `next_permutation` 在最后一个排列之后把序列变回升序并返回 `false`。

## `min`、`max`、`minmax`（[alg.min.max] ¶1–¶24）

### 返回引用：临时对象会悬垂

```cpp run title="min_dangle.cpp" flags="-std=c++2c -O0 -fsanitize=address" ub
#include <algorithm>
#include <cstdio>
#include <string>

int main() {
    const std::string& r =
        std::min(std::string("apple"), std::string("banana"));
    std::printf("%s\n", r.c_str());   // UB：r 绑定到已销毁的临时对象
}
```

两个实参的 `min` 和 `max` 返回 `const T&`，`minmax` 返回 `pair<const T&, const T&>`，引用的都是实参本身。实参是临时对象时，临时对象在完整表达式结束时销毁，引用随之悬垂（[[class.temporary]]）。`const T&` 绑定到函数返回的引用上，不会延长那两个临时对象的生命期。

本机 Clang 23 对这段代码给出 `-Wdangling` 警告，因为 libc++ 在这些函数上标注了 `[[clang::lifetimebound]]`；运行时 AddressSanitizer 报告 `stack-use-after-scope`。改成 `auto r = std::min(...)`，复制一份结果即可。`ranges::min`、`ranges::max` 的两实参版本同样返回 `const T&`，有同样的问题。

### 等价时返回哪一个

- ¶2 `min` 在两个实参等价时返回第一个；
- ¶10 `max` 在两个实参等价时也返回第一个；
- ¶18 `minmax(a, b)` 在 `b` 小于 `a` 时返回 `{b, a}`，否则返回 `{a, b}`。

于是两个实参等价时，`minmax(a, b).second` 是 `b`，而 `max(a, b)` 是 `a`。`minmax` 的结果正好是对 `{a, b}` 做稳定排序的结果：等价时保持原来的顺序。`max` 返回第一个实参的规则从 C++98 起就是如此，无法再改。

### 区间版本：返回值，区间不能为空

`min(initializer_list<T>)`、`ranges::min(r)` 等接受一组值的版本返回值而不是引用，类型是 `T` 或 `range_value_t<R>`。¶5 要求区间非空（`ranges::distance(r) > 0`），违反时是 {{ub}}。

有多个等价的最值时，¶6 和 ¶14 规定 `min` 和 `max` 都返回最左边那个元素的副本，¶22 规定 `minmax` 返回最左边的最小值和最右边的最大值。

### 可以显式指定模板实参

¶4、¶8 等各段的 *Remarks* 规定，调用 `std` 中的这些重载时可以显式指定 `T`。一般情况下，对标准算法显式指定模板实参的效果是未指定的（[[algorithms.requirements#15]]），这里是明文的例外。

典型用途是实参类型不同的情况：`std::max(1, 2L)` 中 `T` 推导冲突，编译失败；`std::max<long>(1, 2L)` 合法。

## `min_element`、`max_element`、`minmax_element`（¶25–¶32）

这三个函数返回迭代器，空区间时返回 `last`（`minmax_element` 返回 `{first, first}`）。

- ¶26 `min_element` 返回第一个最小元素；
- ¶29 `max_element` 返回第一个最大元素；
- ¶31 `minmax_element` 返回第一个最小元素和最后一个最大元素。脚注 183 特意说明，这与 `max_element` 不同是有意的，理由与 `minmax` 相同：和稳定排序后的首尾元素一致。

¶32 `minmax_element` 至多做 max(⌊3(N − 1)/2⌋, 0) 次比较。它成对处理元素：每对元素先互相比较一次，较小的再和当前最小值比，较大的再和当前最大值比。分别调用 `min_element` 和 `max_element` 需要 2(N − 1) 次。

```cpp run title="minmax.cpp" ok
#include <algorithm>
#include <cassert>
#include <vector>

int main() {
    std::vector<int> v{3, 1, 5, 1, 5};
    auto mx = std::max_element(v.begin(), v.end());
    auto [mn, mx2] = std::minmax_element(v.begin(), v.end());
    assert(mx - v.begin() == 2);    // max_element：最左边的最大值
    assert(mx2 - v.begin() == 4);   // minmax_element：最右边的最大值
    assert(mn - v.begin() == 1);    // 最左边的最小值

    long m = std::max<long>(1, 2L); // 显式模板实参：标准明确允许
    assert(m == 2);
}
```

## `clamp`（[alg.clamp]）{{c++17}}

`clamp(v, lo, hi)` 把 `v` 限制在 `[lo, hi]` 之内，由 [[P0025R1]] 引入。

¶2 前置条件是 `comp(hi, lo)` 为假，即 `lo` 不大于 `hi`。`clamp(v, 10, 0)` 是 {{ub}}，不会返回某个边界。

¶3 `v` 小于 `lo` 时返回 `lo`，`hi` 小于 `v` 时返回 `hi`，否则返回 `v`。返回的同样是 `const T&`，同样有悬垂的风险。¶5 至多两次比较。

¶4 注 1 说明，只要避开 NaN，`T` 可以是浮点类型。NaN 会使 `<` 不再是严格弱序。

## 字典序比较（[alg.lex.comparison]）

`lexicographical_compare` 判断第一个序列是否按字典序小于第二个序列。¶3 给出字典序的定义：

- 两个序列长度相同、对应元素都等价时，谁也不小于谁；
- 一个序列是另一个的真前缀时，较短的那个更小；
- 否则结果由第一对不等价的元素决定。

¶5 注 1 补充：空序列小于任何非空序列，但不小于空序列。

¶2 至多 2·min(N1, N2) 次比较。每对元素最多比较两次：`comp(a, b)` 判断小于，`comp(b, a)` 判断大于。¶4 的示例实现就是这样写的。

## 三路字典序比较（[alg.three.way]）{{c++20}}

`lexicographical_compare_three_way(b1, e1, b2, e2, comp)` 一次给出小于、等于、大于三种结果之一：

- ¶2 *Mandates*：`decltype(comp(*b1, *b2))` 必须是比较类别类型（[[cmp.categories]]），不满足时编译失败；
- ¶3 返回第一个使 `comp(*(b1 + i), *(b2 + i)) != 0` 的结果；对应元素都相等时，返回 `(e1 - b1) <=> (e2 - b2)`，即比较长度；
- ¶4 至多 N 次 `comp` 调用，N 是两个长度中较小的那个。

每对元素只比较一次，这是它比 `lexicographical_compare` 省的地方。¶5 不带 `comp` 的版本使用 `compare_three_way()`。标准容器的 `operator<=>` 也用它定义，只是比较器换成了仅用于说明的 *synth-three-way*：元素类型没有 `<=>` 时，退回用 `<` 合成三路结果，见 [[container.opt.reqmts]]。

```cpp run title="lex.cpp" ok
#include <algorithm>
#include <cassert>
#include <compare>
#include <vector>

int main() {
    std::vector a{1, 2, 3}, b{1, 2};
    assert(!std::lexicographical_compare(a.begin(), a.end(),
                                         b.begin(), b.end()));
    auto c = std::lexicographical_compare_three_way(
        a.begin(), a.end(), b.begin(), b.end());
    assert(c == std::strong_ordering::greater);   // b 是 a 的真前缀
}
```

## 排列生成（[alg.permutation.generators]）

¶3 `next_permutation` 把序列变成按 `comp` 字典序排列的下一个排列。不存在下一个排列时，即序列已经是降序，它把序列变成第一个排列，也就是升序，并返回 `false`。¶8 `prev_permutation` 与之对称，回到降序。¶5、¶10 至多 (last − first)/2 次交换，只需要双向迭代器。

这样设计之后，经典的 `do { ... } while (std::next_permutation(...))` 循环结束时，序列恰好回到升序。要枚举全部排列，起点必须是升序，否则只会枚举当前排列之后的那些。序列含有重复元素时，`next_permutation` 只生成不同的排列，因为它是按字典序前进的。`ranges` 版本返回 `in_found_result`，即 `{last, 是否找到}`。

```cpp run title="perm.cpp" ok
#include <algorithm>
#include <cassert>
#include <vector>

int main() {
    std::vector p{1, 2, 3};
    int n = 1;
    while (std::next_permutation(p.begin(), p.end())) ++n;
    assert(n == 6);
    assert((p == std::vector{1, 2, 3}));   // 返回 false 时已回到升序

    std::vector q{1, 1, 2};
    int k = 1;
    while (std::next_permutation(q.begin(), q.end())) ++k;
    assert(k == 3);                        // 重复元素：只有 3 个不同的排列
}
```

## 思考题

!!! question "思考题 1"
    `f()` 和 `g()` 返回 `int`。`const auto& [lo, hi] = std::minmax(f(), g());` 之后使用 `lo`、`hi` 安全吗？

<details markdown="1">
<summary>答案</summary>

不安全。`minmax` 返回 `pair<const int&, const int&>`，两个引用指向两个临时 `int`。结构化绑定的 `const auto&` 只延长了那个 `pair` 临时对象的生命期，不延长它引用的两个 `int` 临时对象。完整表达式结束后，`lo`、`hi` 都悬垂了。

可以写成 `auto [lo, hi] = std::minmax({f(), g()});`：`initializer_list` 版本返回 `pair<int, int>`，里面是值。也可以先把 `f()`、`g()` 的结果存进变量。
</details>

!!! question "思考题 2"
    `std::clamp(x, 0.0, 1.0)` 中 `x` 是 NaN，会发生什么？

<details markdown="1">
<summary>答案</summary>

¶2 的前置条件 `comp(hi, lo)` 为假是满足的，因为 `1.0 < 0.0` 为假。但 `clamp` 属于 [alg.sorting]，[[alg.sorting#3]] 要求比较器在实际比较的值上构成严格弱序。NaN 与 `0.0`、`1.0` 都等价，而 `0.0 < 1.0`，等价关系不可传递，所以按标准这是 {{ub}}。¶4 的注提醒避开 NaN，说的就是这一点。

实际的实现按 ¶3 的写法比较：`x < 0.0` 和 `1.0 < x` 都为假，于是返回 `x`，也就是 NaN。本机 libc++ 就是这个结果，但这不是标准的保证。
</details>

## 小结

| 函数 | 返回 | 等价时 | 注意 |
|---|---|---|---|
| `min(a, b)`、`max(a, b)` | `const T&` | 都返回第一个 | 实参是临时对象时悬垂 |
| `minmax(a, b)` | `pair<const T&, const T&>` | `{a, b}`，max 是 `b` | 同上 |
| `min(il)`、`max(il)` | 值 | 最左边的那个 | 空区间是 UB |
| `max_element`、`minmax_element` | 迭代器 | 最左边的最大值、最右边的最大值 | 空区间返回 `last` |
| `clamp` | `const T&` | 不适用 | `hi < lo` 是 UB；避开 NaN |
| `lexicographical_compare` | `bool` | 不适用 | ≤ 2·min(N1, N2) 次比较 |
| `lexicographical_compare_three_way` | 比较类别 | 不适用 | ≤ min(N1, N2) 次 |
| `next_permutation` | `bool` | 不适用 | 回到升序并返回 `false` |
