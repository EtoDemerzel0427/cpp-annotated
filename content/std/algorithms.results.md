---
title: 算法结果类型
summary: std::ranges 算法返回的九个聚合类模板 in_fun_result、in_in_result、in_out_result、in_in_out_result、in_out_out_result、min_max_result、in_found_result、in_value_result、out_value_result——为什么 ranges 算法要“把输入终点也还给你”、成员的 [[no_unique_address]]、按成员转换的转换函数、与 dangling 的配合
status: done
papers: P0896R4
related: algorithms, algorithms.requirements, range.dangling, dcl.struct.bind, dcl.attr.nouniqueaddr, alg.nonmodifying, alg.modifying.operations
tags: 标准库, ranges, 结果类型, 结构化绑定
updated: 2026-10-18
---

经典 `std::copy(first, last, out)` 只返回输出终点。如果输入是 `istream_iterator` 这类单趟迭代器，或者用的是哨位（C++20 中 `last` 的类型可以与 `first` 不同、甚至是 `unreachable_sentinel_t`），调用者就**永远拿不回**“输入走到了哪里”这个算法已经算出来的信息。C++20 Ranges（[[P0896R4]]）的原则是：**算法计算出的有用信息都要返回**。于是 `ranges::copy` 返回 `{in, out}` 两个迭代器——这就需要一组有名字成员的结果类型。

## 九个类模板（¶1）

!!! std
    Each of the class templates specified in this subclause has the template parameters, data members, and special members specified below, and has no base classes or members other than those specified.

| 类模板 | 成员 | 典型用户（`ranges::` 下的别名） |
|---|---|---|
| `in_fun_result<I, F>` | `in`, `fun` | `for_each_result`、`for_each_n_result` |
| `in_in_result<I1, I2>` | `in1`, `in2` | `mismatch_result`、`swap_ranges_result` |
| `in_out_result<I, O>` | `in`, `out` | `copy_result`、`move_result`、`unary_transform_result`、`remove_copy_result`、`unique_copy_result`、`partial_sort_copy_result`、`set_difference_result` |
| `in_in_out_result<I1, I2, O>` | `in1`, `in2`, `out` | `binary_transform_result`、`merge_result`、`set_union_result`、`set_intersection_result`；C++26 的 `reverse_copy_truncated_result` 等 |
| `in_out_out_result<I, O1, O2>` | `in`, `out1`, `out2` | `partition_copy_result` |
| `min_max_result<T>` | `min`, `max` | `minmax_result`、`minmax_element_result` |
| `in_found_result<I>` | `in`, `found` | `next_permutation_result`、`prev_permutation_result` |
| `in_value_result<I, T>` | `in`, `value` | `fold_left_with_iter_result`、`fold_left_first_with_iter_result` |
| `out_value_result<O, T>` | `out`, `value` | `iota_result` |

“没有基类、没有其他成员”保证了它们都是**聚合**，因而：

- 可以用结构化绑定解构：`auto [in, out] = ranges::copy(r, o);`（[[dcl.struct.bind]]）；
- 可以用花括号构造：条文中大量出现的 `return {last, result + N};` 就依赖于此；
- 成员名是规范性的：`r.in`、`r.out` 可移植，不必依赖 `get<0>`。

## `[[no_unique_address]]`

除 `in_found_result::found`（`bool`）外，所有成员都标了 `[[no_unique_address]]`（[[dcl.attr.nouniqueaddr]]）。用意是：迭代器和函数对象常常是**空类**（如无捕获 lambda、`unreachable_sentinel_t`），这时结果对象可以不为它们占用存储。例如 `for_each_result<int*, Lambda>` 在主流 ABI 上与一个指针一样大。

## 按成员的转换函数

每个模板都有一对转换函数模板（`const&` 版复制成员，`&&` 版移动成员），约束为对应成员 `convertible_to`：

```cpp
template<class I2, class O2>
  requires convertible_to<const I&, I2> && convertible_to<const O&, O2>
constexpr operator in_out_result<I2, O2>() const & { return {in, out}; }
```

这让同一“形状”的结果在迭代器类型不同时也能互相赋值，例如把 `in_out_result<int*, int*>` 转为 `in_out_result<const int*, int*>`。它们是转换函数而不是转换构造函数，是为了保持聚合性。注意它只在**同一个类模板**内转换：`in_out_result` 不能变成 `in_in_result`。

## 与 `dangling` 的配合

结果类型本身没有特别的安全机制，但 range 重载的返回类型中用的是 `borrowed_iterator_t<R>`：若传入非 borrowed range 的右值（如临时 `vector`），对应成员变成 `ranges::dangling`（[[range.dangling]]），任何解引用都会编译失败。

```cpp run title="results.cpp" ok
#include <algorithm>
#include <cassert>
#include <ranges>
#include <type_traits>
#include <vector>

std::vector<int> make() { return {3, 1, 2}; }

int main() {
    std::vector<int> src{1, 2, 3}, dst(3);
    auto [in, out] = std::ranges::copy(src, dst.begin());   // in_out_result<I, O>
    assert(in == src.end() && out == dst.end());

    // 按成员转换
    std::ranges::in_out_result<const int*, int*> r{nullptr, nullptr};
    std::ranges::in_out_result<const void*, void*> r2 = r;
    (void)r2;

    // 右值非 borrowed 范围：得到 ranges::dangling，而不是悬垂迭代器
    auto it = std::ranges::max_element(make());
    static_assert(std::is_same_v<decltype(it), std::ranges::dangling>);
    // *it;   // error: dangling 不能解引用

    auto mm = std::ranges::minmax({3, 1, 4, 1, 5});        // min_max_result<int>
    assert(mm.min == 1 && mm.max == 5);
}
```

!!! pitfall "`min_max_result` 的成员是值还是迭代器"
    `ranges::minmax` 返回 `min_max_result<T>`（**值**的副本，或在左值实参时是 `const T&`），`ranges::minmax_element` 返回 `min_max_result<I>`（**迭代器**）。名字相同的成员 `min`/`max` 含义完全不同，见 [[alg.min.max]]。

## 思考题

<details markdown="1">
<summary>为什么 `set_difference` 的经典 ranges 版返回 `in_out_result`（只有第一个输入的终点），而 `set_union` 返回 `in_in_out_result`？</summary>

`set_difference` 输出的是“在第一个序列但不在第二个序列中”的元素；一旦第一个序列耗尽算法就结束，第二个序列可能没走完，而它的位置对调用者没有用处（不像 `set_union` 那样两个序列都会被走完并消费）。C++26 并行 ranges 版本因为输出有界、可能中途停下，返回的是 `set_difference_truncated_result`（即 `in_in_out_result`），需要告诉调用者两个输入分别消费到哪里，见 [[alg.set.operations]]。
</details>

## 小结

- ranges 算法“算出来的都还给你”，因此返回带具名成员的聚合。
- 九个类模板没有基类、没有多余成员；成员带 `[[no_unique_address]]`（`found` 除外）。
- 有按成员的 `const&`/`&&` 转换函数，只能在同一类模板的不同实参之间转换。
- range 重载对右值非 borrowed range 返回 `ranges::dangling`。
