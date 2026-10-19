---
title: 算法结果类型
summary: std::ranges 算法返回的九个结果类模板（in_out_result、in_in_result、min_max_result 等）：为什么 ranges 算法要把输入走到的位置也返回，它们为什么是聚合，成员的 [[no_unique_address]]，以及只在同一个模板内进行的按成员转换。
status: done
papers: P0896R4
related: algorithms, algorithms.requirements, range.dangling, dcl.struct.bind, dcl.attr.nouniqueaddr, alg.nonmodifying, alg.modifying.operations
tags: 标准库, ranges, 结果类型, 结构化绑定
updated: 2026-10-19
---

!!! tldr
    - `ranges` 算法把算出来的有用信息都返回，所以 `ranges::copy` 返回输入和输出两个终点，而不只是输出终点。
    - 返回值是九个类模板之一，如 `in_out_result<I, O>`，成员名 `in`、`out` 是标准规定的，可以用结构化绑定拆开。
    - 它们是没有基类、没有多余成员的聚合；除 `found` 外的成员都带 `[[no_unique_address]]`，空的函数对象不占空间。
    - 实参是会被销毁的临时范围时，迭代器成员变成 `ranges::dangling`，误用它会编译失败。

```cpp run title="results.cpp" ok
#include <algorithm>
#include <cassert>
#include <ranges>
#include <type_traits>
#include <vector>

std::vector<int> make() { return {3, 1, 2}; }

int main() {
  std::vector<int> src{1, 2, 3}, dst(3);
  auto [in, out] = std::ranges::copy(src, dst.begin());
  assert(in == src.end() && out == dst.end());

  // 右值的非借用范围：返回 ranges::dangling
  auto it = std::ranges::max_element(make());
  static_assert(std::is_same_v<decltype(it), std::ranges::dangling>);
  // *it;   // error: dangling 不能解引用

  auto mm = std::ranges::minmax({3, 1, 4, 1, 5});   // min_max_result<int>
  assert(mm.min == 1 && mm.max == 5);

  // 按成员转换
  int a[2]{};
  std::ranges::in_out_result<int*, int*> r{a, a + 1};
  std::ranges::in_out_result<const int*, int*> r2 = r;
  assert(r2.in == a);
}
```

## 为什么要返回输入的终点

经典的 `std::copy(first, last, out)` 只返回输出的终点。在经典算法里这不算损失，因为调用方手里本来就有 `last`。

C++20 的算法允许终点是一个类型不同的**哨位**（sentinel），例如 `unreachable_sentinel_t`，或者一个"读到 0 就停"的条件。这时调用方只知道何时停，不知道停在哪个迭代器上。如果输入是 `istream_iterator` 这样只能遍历一趟的迭代器，信息丢了就再也拿不回来。所以 C++20 的 Ranges（[[P0896R4]]）采取的原则是：算法算出来的有用信息都要返回。`ranges::copy` 因此返回 `{in, out}` 两个迭代器，这就需要一组带具名成员的结果类型。

## 九个类模板（¶1）

| 类模板 | 成员 | 用它的 `ranges` 算法（别名） |
|---|---|---|
| `in_fun_result<I, F>` | `in`, `fun` | `for_each_result`、`for_each_n_result` |
| `in_in_result<I1, I2>` | `in1`, `in2` | `mismatch_result`、`swap_ranges_result` |
| `in_out_result<I, O>` | `in`, `out` | `copy_result`、`move_result`、`unary_transform_result`、`remove_copy_result`、`set_difference_result` 等 |
| `in_in_out_result<I1, I2, O>` | `in1`, `in2`, `out` | `binary_transform_result`、`merge_result`、`set_union_result`；C++26 的 `reverse_copy_truncated_result` 等 |
| `in_out_out_result<I, O1, O2>` | `in`, `out1`, `out2` | `partition_copy_result` |
| `min_max_result<T>` | `min`, `max` | `minmax_result`、`minmax_element_result` |
| `in_found_result<I>` | `in`, `found` | `next_permutation_result`、`prev_permutation_result` |
| `in_value_result<I, T>` | `in`, `value` | `fold_left_with_iter_result`、`fold_left_first_with_iter_result` |
| `out_value_result<O, T>` | `out`, `value` | `<numeric>` 的 `iota_result` |

!!! std
    Each of the class templates specified in this subclause has the template parameters, data members, and special members specified below, and has no base classes or members other than those specified.

没有基类、没有其他成员，保证了它们都是聚合。所以可以用结构化绑定拆开（[[dcl.struct.bind]]），条文里常见的 `return {last, result + N};` 也能直接用花括号构造。成员名是规范的一部分，`r.in`、`r.out` 在所有实现上都能用。

### `[[no_unique_address]]`

除了 `in_found_result::found`（一个 `bool`），所有成员都标了 `[[no_unique_address]]`（[[dcl.attr.nouniqueaddr]]）。迭代器和函数对象常常是空类，如无捕获的 lambda、`unreachable_sentinel_t`，这时结果对象不必为它们分配存储。本机 Clang 上，`for_each_result<int*, Lambda>` 与一个指针一样大，都是 8 字节。

### 按成员转换

每个模板都有一对转换函数模板。`const&` 版本复制成员，`&&` 版本移动成员，约束是每个成员都能转换为目标类型的对应成员：

```cpp
template<class I2, class O2>
  requires convertible_to<const I&, I2> && convertible_to<const O&, O2>
constexpr operator in_out_result<I2, O2>() const & { return {in, out}; }
```

于是 `in_out_result<int*, int*>` 可以转换成 `in_out_result<const int*, int*>`，如开头例子的最后几行。这里用的是转换函数而不是转换构造函数，因为聚合不能有用户声明的构造函数。转换只在同一个类模板内进行，`in_out_result` 不能变成 `in_in_result`。

## 与 `dangling` 的配合

结果类型本身没有安全机制。保护来自范围重载的返回类型：它们用 `borrowed_iterator_t<R>` 作为迭代器成员的类型。传入的是右值、而且不是借用范围（借用范围指迭代器不依赖范围对象存活的范围，如 `std::span`）时，这个类型是 `ranges::dangling`（[[range.dangling]]）。临时 `vector` 在完整表达式结束时就销毁了，指向它的迭代器必然悬垂，`dangling` 把这种错误提前到编译期。

!!! pitfall "`min_max_result` 的成员是值还是迭代器"
    `ranges::minmax` 返回 `min_max_result<T>`，成员是值（实参是左值时是 `const T&`）；`ranges::minmax_element` 返回 `min_max_result<I>`，成员是迭代器。成员名都叫 `min`、`max`，含义完全不同，见 [[alg.min.max]]。

## 思考题

!!! question "思考题"
    `ranges::set_difference` 返回 `in_out_result`，只有第一个输入的终点；`ranges::set_union` 返回 `in_in_out_result`。为什么？

<details markdown="1">
<summary>答案</summary>

`set_difference` 输出在第一个序列中、但不在第二个序列中的元素。第一个序列走完算法就结束，第二个序列可能没有走完，它停在哪里对调用方没有意义。`set_union` 则会把两个序列都走完。

C++26 的并行 `ranges` 版本有输出上界，可能在中途停下，所以返回 `set_difference_truncated_result`，也就是 `in_in_out_result`，告诉调用方两个输入各自处理到了哪里，见 [[alg.set.operations]]。
</details>
