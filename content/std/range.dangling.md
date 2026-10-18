---
title: 悬垂迭代器处理 dangling
summary: ranges 算法对"右值且非借用"的范围实参返回 ranges::dangling 而非迭代器——borrowed_iterator_t / borrowed_subrange_t 的选择规则、dangling 为何能从任意实参构造、它能挡住什么、挡不住什么（存储视图、修改容器后继续使用、范围 for 的临时量）。
status: done
since: c++20
papers: P0896R4
related: range.req, range.range, range.subrange, range.all, range.view, stmt.ranged, class.temporary, basic.life, topics/dangling-references
tags: 标准库, 范围, 悬垂, 生命周期
updated: 2026-10-18
---

经典的悬垂迭代器 bug：

```cpp
auto it = std::max_element(make_vector().begin(), make_vector().end());  // 两个不同的临时量！
```

Ranges 算法接受整个范围，这个错误变成了：

```cpp
auto it = std::ranges::max_element(make_vector());   // 临时 vector 在分号处销毁
```

后者至少只有一个临时量，但 `it` 仍会悬垂。[range.dangling] 的做法是：**让这种调用的返回类型变成一个什么也做不了的类型**，于是对 `it` 解引用直接编译失败。

## `dangling` 本身（¶1）

（[[g:ranges-dangling]]）

¶1 当一个"通常返回指向范围实参的迭代器或子范围"的算法以**不建模 `borrowed_range` 的右值**范围实参调用时，返回值可能引用一个生命周期已经结束的范围。此时返回 `dangling` 类型而不是迭代器或子范围。

```cpp
struct dangling {
  constexpr dangling() noexcept = default;
  constexpr dangling(auto&&...) noexcept {}
};
```

它能从**任意**实参构造并丢弃它们。这一点是为了实现上的统一：算法的实现总是先算出真正的迭代器，然后 `return {it};`——当返回类型是 `dangling` 时，这句同样能编译。`dangling` 没有 `operator*`、没有 `operator++`、不能与任何东西比较，因此任何"使用"它的代码都是编译错误。

## 选择规则（¶3）

对建模 `range` 的类型 `R`：

- 若 `R` 建模 `borrowed_range`：`borrowed_iterator_t<R>` 是 `iterator_t<R>`，`borrowed_subrange_t<R>` 是 `subrange<iterator_t<R>>`；
- 否则二者都是 `dangling`。

算法的签名形如：

```cpp
template<forward_range R, class Proj = identity, ...>
  constexpr borrowed_iterator_t<R> ranges::max_element(R&& r, Comp comp = {}, Proj proj = {});
```

`R` 由转发引用推导：左值实参推导为 `X&`（左值引用一律借用），右值实参推导为 `X`，此时就看 `enable_borrowed_range<X>`（[[range.req]]）。

¶2 例 1 给出了三种情况：

```cpp run ok
#include <algorithm>
#include <ranges>
#include <vector>
std::vector<int> make() { return {3, 1, 4, 1, 5}; }
int main() {
  auto r1 = std::ranges::max_element(make());
  static_assert(std::same_as<decltype(r1), std::ranges::dangling>);
  // int bad = *r1;                       // error: dangling 不能解引用
  auto v = make();
  auto r2 = std::ranges::max_element(v);  // 左值：真正的迭代器
  auto r3 = std::ranges::find(std::views::all(v), 4);  // ref_view 是借用范围
  return (*r2 == 5 && *r3 == 4) ? 0 : 1;
}
```

第三行说明了一个重要细节：`std::views::all(v)` 是一个**右值** `ref_view`，但 `ref_view` 借用，所以返回真正的迭代器——迭代器指向 `v`，与那个临时 `ref_view` 无关。同理，`std::string_view`、`std::span`、`subrange` 的右值都能得到真迭代器。

!!! tip "只要结果的\"值\"而非迭代器"
    对右值容器，若只是想知道最大值，可以用返回值而非迭代器的算法：`std::ranges::max(make())` 返回 `int`，与悬垂无关。`ranges::find` 之类返回迭代器的算法要么传左值，要么改用 `ranges::contains`（C++23）这类返回 `bool` 的算法。

## 它挡不住什么

`dangling` 只在**算法调用的那一刻**判断实参的值类别。下面这些都绕过了它：

### 1. 把视图存起来，或从函数返回

```cpp run ub
#include <ranges>
#include <vector>
#include <cstdio>
auto evens() {
  std::vector<int> v{1, 2, 3, 4};
  return v | std::views::filter([](int x) { return x % 2 == 0; });  // ref_view 指向局部 v
}
int main() {
  for (int x : evens()) std::printf("%d\n", x);   // UB：v 已销毁
}
```

`v` 是左值，`views::all(v)` 得到 `ref_view`，类型系统认为一切正常。在本站环境用 `-fsanitize=address` 运行，它在第一次解引用时崩溃（SEGV）。修复：`return std::move(v) | views::filter(...)`——右值容器会被移入 `owning_view`（[[range.all]]），视图拥有数据。

### 2. 修改底层容器后继续使用

```cpp
std::vector<int> v{1, 2, 3};
auto t = v | std::views::transform(f);
v.push_back(4);          // 可能重新分配：t 中缓存的迭代器（若有）以及之前取得的迭代器全部失效
```

视图持有的是 `ref_view`（指向 `v` 的指针），`ref_view` 本身不受影响；但视图**缓存的迭代器**（`filter`/`drop` 的 `begin` 缓存）以及你之前拿到的迭代器都会随重新分配失效（[[container.reqmts]] 的失效规则）。

### 3. 借用性是用户声明的

为一个其实拥有元素的类型特化 `enable_borrowed_range = true`，`dangling` 就不会出现了（见 [[range.req]] 中的警告）。

### 4. 范围 for 的老坑（C++23 前）

`for (auto x : get_obj().items())`：`get_obj()` 的临时量在 C++20 中于 *for-range-initializer* 求值后就销毁，`items()` 返回的引用悬垂。这与 `dangling` 无关（没有调用 ranges 算法）。C++23 起，范围 `for` 的初始化器中的临时量生命周期被延长到整个循环（[[stmt.ranged]]、[[class.temporary]]）。

## 思考题

<details markdown="1">
<summary>1. `std::ranges::find(std::string("hello"), 'l')` 与 `std::ranges::find(std::string_view("hello"), 'l')` 的返回类型分别是什么？</summary>

前者 `dangling`（`std::string` 右值，不借用）；后者 `string_view::const_iterator`（`string_view` 借用，迭代器指向字符串字面量的静态存储，确实安全）。
</details>

<details markdown="1">
<summary>2. 对右值 `owning_view<vector<int>>` 调用 `ranges::find`，返回什么？</summary>

`enable_borrowed_range<owning_view<T>>` 等于 `enable_borrowed_range<T>`，`vector` 不借用，所以返回 `dangling`。这是正确的：`owning_view` 拥有 `vector`，它死了迭代器就悬垂。
</details>

## 小结

- 右值 + 非借用 → `dangling`；左值或借用 → 真迭代器/`subrange`；
- `dangling` 可从任何东西构造、不能做任何事，把运行期悬垂变成编译错误；
- 它只保护"算法调用的那一个表达式"；存储视图、返回视图、修改容器后继续使用，仍需要程序员自己管理生命周期。
