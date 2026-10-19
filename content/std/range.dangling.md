---
title: 悬垂迭代器处理 dangling
summary: 以非借用的右值范围调用返回迭代器的 ranges 算法时，返回类型变成 ranges::dangling，使用结果的代码无法编译；以及它挡不住的几类悬垂。
status: done
since: c++20
papers: P0896R4
related: range.req, range.range, range.subrange, range.all, range.view, stmt.ranged, class.temporary, basic.life, topics/dangling-references
tags: 标准库, 范围, 悬垂, 生命周期
updated: 2026-10-19
---

!!! tldr
    - 返回迭代器或子范围的 ranges 算法，如果收到的范围实参是右值且不是借用范围，就返回 `ranges::dangling`。
    - `dangling` 可以从任何实参构造，但不能解引用、递增或比较，所以使用这个结果的代码会编译失败。
    - 左值范围和借用范围（`string_view`、`span`、`subrange`、`ref_view` 等）的右值都得到真正的迭代器。
    - 它只检查算法调用这一个表达式。把视图存起来、从函数返回视图、修改容器后继续使用，仍然可能悬垂。

## 把悬垂变成编译错误

```cpp
auto it = std::ranges::max_element(make_vector());
// make_vector() 返回的临时 vector 在分号处销毁，it 悬垂
```

如果 `max_element` 在这里返回 `vector<int>::iterator`，`it` 指向的是已经销毁的临时对象，之后解引用是未定义行为。标准的做法是让这种调用的返回类型变成一个什么也做不了的类型 `dangling`，于是 `*it` 直接编译失败。

```cpp run ok
#include <algorithm>
#include <ranges>
#include <vector>
std::vector<int> make() { return {3, 1, 4, 1, 5}; }
int main() {
  auto r1 = std::ranges::max_element(make());
  static_assert(std::same_as<decltype(r1), std::ranges::dangling>);
  // int bad = *r1;                        // error: dangling 不能解引用

  auto v = make();
  auto r2 = std::ranges::max_element(v);   // 左值：真正的迭代器
  auto r3 = std::ranges::find(std::views::all(v), 4);   // 右值 ref_view：借用
  return (*r2 == 5 && *r3 == 4) ? 0 : 1;
}
```

`r3` 一行值得注意：`std::views::all(v)` 是一个右值 `ref_view`，但 `ref_view` 是借用范围，返回的迭代器指向 `v` 的元素，与那个临时 `ref_view` 无关，所以是安全的。

## dangling 类型（¶1）

¶1 一个通常返回迭代器或子范围的算法，以不建模 `borrowed_range`（[[range.range]]）的右值范围实参调用时，返回值可能指向生命周期已经结束的范围。这时返回 `dangling`（[[g:ranges-dangling]]），而不是迭代器或子范围：

```cpp
struct dangling {
  constexpr dangling() noexcept = default;
  constexpr dangling(auto&&...) noexcept {}
};
```

它能从任意实参构造并丢弃这些实参。这样算法的实现不必区分两种情况：总是先算出真正的迭代器，再 `return {it};`，返回类型是 `dangling` 时这句同样能编译。`dangling` 没有 `operator*`、`operator++`，也不能与任何东西比较。

## 返回类型怎样选择（¶3）

¶3 对建模 `range` 的类型 `R`：

- 如果 `R` 建模 `borrowed_range`，`borrowed_iterator_t<R>` 是 `iterator_t<R>`，`borrowed_subrange_t<R>` 是 `subrange<iterator_t<R>>`；
- 否则二者都是 `dangling`。

算法用这两个别名作为返回类型，例如：

```cpp
template<forward_range R, class Proj = identity, /* ... */>
  constexpr borrowed_iterator_t<R>
    ranges::max_element(R&& r, Comp comp = {}, Proj proj = {});
```

`R` 由转发引用推导。实参是左值时 `R` 推导为 `X&`，左值引用一律算借用范围；实参是右值时 `R` 推导为 `X`，这时看 `enable_borrowed_range<X>`。

¶2 例 1 给出了三种情况：`ranges::find(f(), 42)` 以右值 `vector` 调用，返回 `dangling`；`ranges::find(vec, 42)` 以左值调用，返回迭代器；`ranges::find(ranges::subrange{vec}, 42)` 以右值 `subrange` 调用，`subrange` 是借用范围，同样返回迭代器（[[range.subrange]]）。

!!! tip "只需要值时"
    对右值容器，如果只想知道最大值，用返回值的算法即可：`std::ranges::max(make())` 返回 `int`，没有悬垂问题。只想知道元素是否存在，可以用 C++23 的 `ranges::contains`，它返回 `bool`。

## 它挡不住什么

`dangling` 只在算法调用的那一刻根据实参的值类别作判断。下面几种情况都绕过了它。

### 把视图存起来或从函数返回

```cpp run ub
#include <ranges>
#include <vector>
#include <cstdio>
auto evens() {
  std::vector<int> v{1, 2, 3, 4};
  return v | std::views::filter([](int x) { return x % 2 == 0; });
  // 视图里的 ref_view 指向局部变量 v
}
int main() {
  for (int x : evens()) std::printf("%d\n", x);   // UB：v 已销毁
}
```

`v` 是左值，`views::all(v)` 得到 `ref_view`，类型系统认为一切正常。本机 Clang 23 用 `-fsanitize=address` 运行，在 `filter_view::begin` 中读取 `v` 时就报告错误（stack-buffer-overflow：读的是已经销毁的局部变量所在的栈内存）。修复方法是 `return std::move(v) | views::filter(...)`：右值容器会被移进 `owning_view`（[[range.all]]），视图自己拥有数据。

### 修改底层容器后继续使用

```cpp
std::vector<int> v{1, 2, 3};
auto f = v | std::views::filter(pred);
auto it = f.begin();     // filter_view 会缓存 begin 的结果
v.push_back(4);          // 可能重新分配内存
```

视图里的 `ref_view` 只保存指向 `v` 的指针，不受影响。但 `push_back` 重新分配内存后，`it` 和 `filter_view` 内部缓存的 `begin` 迭代器都失效了（迭代器失效规则见 [[container.reqmts]]），再次调用 `f.begin()` 返回的仍是那个失效的缓存值。

### 借用性由类型作者声明

为一个其实拥有元素的类型特化 `enable_borrowed_range` 为 `true`，`dangling` 就不会出现，悬垂由类型作者负责（见 [[range.range]]）。

### 范围 for 的临时量（C++23 前）

`for (auto x : get_obj().items())` 中，C++20 及以前 `get_obj()` 返回的临时对象在初始化器求值完毕后就销毁，`items()` 返回的引用悬垂。这与 `dangling` 无关，因为这里没有调用 ranges 算法。C++23 起，范围 `for` 初始化器中的临时对象生命周期延长到整个循环（[[stmt.ranged]]、[[class.temporary]]）。

## 思考题

!!! question "思考题 1"
    `std::ranges::find(std::string("hello"), 'l')` 和 `std::ranges::find(std::string_view("hello"), 'l')` 的返回类型分别是什么？

<details markdown="1">
<summary>答案</summary>

前者是 `dangling`：`std::string` 的右值不是借用范围。后者是 `string_view::const_iterator`：`string_view` 是借用范围，迭代器指向字符串字面量所在的静态存储，确实安全。
</details>

!!! question "思考题 2"
    以右值 `owning_view<vector<int>>` 调用 `ranges::find`，返回什么？

<details markdown="1">
<summary>答案</summary>

`enable_borrowed_range<owning_view<T>>` 等于 `enable_borrowed_range<T>`（[[range.owning.view]]），`vector` 不是借用范围，所以返回 `dangling`。这是正确的结果：`owning_view` 拥有那个 `vector`，它销毁后迭代器就悬垂了。
</details>

<details class="fine" markdown="1"><summary>elements_of [range.elementsof]</summary>

同在 [range.utility] 中的 `elements_of<R, Allocator>` 是一个标签类型，保存一个范围和一个分配器。在 `std::generator` 中写 `co_yield ranges::elements_of(r);` 表示逐个产生 `r` 的元素，写 `co_yield r;` 则把 `r` 当作一个值产生。详见 [[coro.generator]]。

</details>
