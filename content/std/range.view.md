---
title: 视图
summary: view = range + movable + enable_view；O(1) 移动构造、移动赋值不贵于"析构+移动构造"、N 个副本的析构为 O(N+M)、可复制时复制 O(1)——语义要求的精确措辞与它在 C++20 期间的两次修改；enable_view、view_base 与 view_interface 的判定规则。
status: done
since: c++20
papers: P0896R4, P1456R1, P2325R3, P2415R2
related: range.req, range.range, range.all, view.interface, range.adaptors, concepts.object, namespace.std, views.contiguous, string.view
tags: 标准库, 范围, 视图, 概念
updated: 2026-10-18
---

什么样的范围可以放进适配器管道？如果 `views::filter` 收到一个 `vector<int>` 就复制一份，管道的每一级都可能复制整个数据集——惰性求值就失去了意义。[range.view] 用一个概念 `view` 回答"哪些范围可以被**廉价地按值持有**"，所有适配器都**按值**存储它们的底层视图（[[range.adaptors]]）。

## 定义（¶1）

```cpp
template<class T>
  concept view = range<T> && movable<T> && enable_view<T>;
```

（术语见 [[g:range-view]]。）三部分：是范围；是可移动的对象类型（[[concepts.object]]）；并且通过 `enable_view` **主动声明**自己是视图。语义要求无法从语法上区分（`vector` 和 `span` 都有 `begin/end`、都可移动），所以要靠"选择加入"（opt-in）。

## 语义要求（¶2–¶4）

¶2 `T` 建模 `view` 仅当：

- ¶2.1 `T` 有 **O(1) 移动构造**；
- ¶2.2 `T` 的移动赋值**不比"析构后再移动构造"更复杂**；
- ¶2.3 若从一个含 **M** 个元素的 `T` 对象做了 **N** 次复制和/或移动，这 N 个对象的析构总代价为 **O(N+M)**；
- ¶2.4 `copy_constructible<T>` 为假，或者 `T` 有 O(1) 复制构造；
- ¶2.5 `copyable<T>` 为假，或者复制赋值不比"析构后再复制构造"更复杂。

!!! std
    if N copies and/or moves are made from an object of type T that contained M elements, then those N objects have O(N+M) destruction

    若从含 M 个元素的 T 对象做了 N 次复制和/或移动，则这 N 个对象的析构总共为 O(N+M)。

¶3 注 1：这些约束意味着**被移出的** `T` 对象的析构是 O(1)。

¶2.3 是 C++20 之后的措辞（[[P2415R2]]），值得逐字体会。它允许视图**拥有**元素——只要元素只被析构一次：

- `owning_view<vector<int>>` 只能移动，N 次移动后只有一个对象真正持有 M 个元素，其余 N−1 个是空壳：总析构 O(N+M) ✓；
- `shared_ptr` 持有的数据被 N 个副本共享，最后一个副本析构 M 个元素，其余只减引用计数：O(N+M) ✓；
- 一个**可复制**且每份副本都深复制元素的类型：复制本身就违反 ¶2.4，N 份副本析构是 O(N·M) ✗。

¶4 例 1 列举了典型的视图：包装一对迭代器的类型、用 `shared_ptr` 持有元素并与所有副本共享所有权的类型、按需生成元素的类型。`vector<string>` 不是视图，因为复制它要复制所有元素，无法在常数时间内完成。

```cpp run ok
#include <memory>
#include <ranges>
#include <vector>
#include <cstdio>
// 共享所有权的视图：复制只增加引用计数，O(1)
class shared_ints : public std::ranges::view_interface<shared_ints> {
  std::shared_ptr<std::vector<int>> p_ = std::make_shared<std::vector<int>>();
public:
  shared_ints() = default;
  explicit shared_ints(std::vector<int> v)
    : p_(std::make_shared<std::vector<int>>(std::move(v))) {}
  auto begin() const { return p_->begin(); }
  auto end() const { return p_->end(); }
};
static_assert(std::ranges::view<shared_ints>);

// 一个"看起来像视图"但其实拥有元素的类型：语法上满足 view，语义上不建模
struct fat : std::ranges::view_base {
  std::vector<int> v;
  auto begin() const { return v.begin(); }
  auto end() const { return v.end(); }
};
static_assert(std::ranges::view<fat>);   // 满足，但复制是 O(N)：违反 [range.view]/2.4

// 只能移动的视图
struct once : std::ranges::view_interface<once> {
  std::unique_ptr<int[]> data{new int[3]{1, 2, 3}};
  int* begin() const { return data.get(); }
  int* end() const { return data.get() + 3; }
};
static_assert(std::ranges::view<once> && !std::copyable<once>);

int main() {
  auto r = shared_ints({1, 2, 3, 4}) | std::views::transform([](int x) { return x * 10; });
  for (int x : r) std::printf("%d ", x);
  for (int x : once{} | std::views::reverse) std::printf("%d ", x);
  std::puts("");   // 10 20 30 40 3 2 1
}
```

`fat` 的例子说明：编译器只检查**满足**；它声称自己是视图，就要对语义负责。把 `fat` 放进管道，每一级适配器复制它时都会深复制 `vector`——程序仍然"能跑"，只是标准不再保证任何复杂度，且严格说来程序已违反库的要求（[[res.on.requirements]]）。

## `enable_view`（¶5–¶7）

```cpp
template<class T>
  constexpr bool is-derived-from-view-interface = see below;   // exposition only
template<class T>
  constexpr bool enable_view =
    derived_from<T, view_base> || is-derived-from-view-interface<T>;
```

¶6 *is-derived-from-view-interface*`<T>` 为 `true` 当且仅当 `T` **恰好有一个**公开基类 `view_interface<U>`（对某个 `U`），且没有其他 `view_interface<V>` 基类。

所以有三种方式成为视图：

1. 公开继承 `std::ranges::view_base`（一个空标签类）；
2. 公开继承 `std::ranges::view_interface<Derived>`（[[view.interface]]，同时还能免费得到 `empty()`、`size()`、`front()`、`operator[]` 等成员）——这是推荐做法；
3. 为自己的类型特化 `enable_view`。¶7：用户可以对**cv 非限定的程序定义类型**特化为 `true`（若它建模 `view`）或 `false`（若它不建模），特化须可用于常量表达式且类型为 `const bool`。

第 3 条的"`false`"方向有实际用途：一个类型因为继承了某个从 `view_interface` 派生的基类而被误判为视图时，可以显式关掉。

标准库自己的 `basic_string_view`、`span` 并不继承 `view_base`，而是在各自的头文件概要（[[string.view.synop]]、[[span.syn]]）中把 `ranges::enable_view` 与 `ranges::enable_borrowed_range` 都特化为 `true`。

!!! pitfall "\"恰好一个\" view_interface 基类"
    如果一个类从两个不同的 `view_interface<X>`、`view_interface<Y>` 派生（例如继承了两个各自用 CRTP 定义的视图），*is-derived-from-view-interface* 为假。这不是吹毛求疵：两个 CRTP 基类各自提供 `empty()`、`size()` 等成员会造成歧义。

## 历史：视图的定义改过三次

!!! history "从 semiregular 到 movable，再到 \"允许拥有\""
    1. **C++20 初版**（[[P0896R4]]）：`view` 要求 `semiregular`（可复制、可默认构造），并要求复制、移动、析构都是 O(1)。这实际上禁止了视图拥有元素。
    2. **只可移动的视图**（[[P1456R1]]，进入 C++20）：把 `semiregular` 放宽为 `movable`，允许仅可移动的视图（如持有 `unique_ptr`、或者持有只能移动的协程句柄的生成器）。
    3. **不要求可默认构造**（[[P2325R3]]，C++23 但作为 C++20 的 DR）：`default_initializable` 被移出 `view`；各标准视图的默认构造函数改成有条件的（`requires default_initializable<V>`）。
    4. **"什么是视图？"**（[[P2415R2]]，同样作为 C++20 DR）：把"析构 O(1)"改成今天 ¶2.3 的 O(N+M) 措辞，从而允许**拥有元素但只能移动**的视图，并据此新增了 `owning_view`，让 `views::all(std::move(vec))` 合法（[[range.all]]）。

    因为后三者都是对 C++20 的 DR，主流实现在 `-std=c++20` 下也采用了新语义。

## 常见误区

!!! pitfall "以为视图就是\"不拥有元素\""
    今天的定义只关心**代价**，不关心所有权。`owning_view`、`single_view`（自带一个元素）、`std::generator`（拥有协程帧）都是视图。正确的心智模型是："按值传递它不会让总代价超出与元素数成线性的范围"。

!!! pitfall "以为视图都是可复制的"
    `owning_view`、`generator`、以及底层为只移动视图的适配器结果都**只能移动**。泛型代码应以 `std::ranges::view auto v` 按值接收后 `std::move(v)` 继续传递，而不是到处复制。

## 思考题

<details markdown="1">
<summary>1. `std::vector<int>` 显式特化 `enable_view` 为 true 是合法的吗？</summary>

不合法。¶7 只允许为**程序定义类型**特化（[[namespace.std]]），`std::vector<int>` 不是程序定义类型；而且即便允许，它的复制是 O(N)，也不建模 `view`。
</details>

<details markdown="1">
<summary>2. 为什么 ¶2.2 不直接要求"移动赋值 O(1)"？</summary>

移动赋值要先销毁左操作数原有的状态。若视图拥有元素（如 `owning_view`），销毁旧内容是 O(M)，不可能是 O(1)。所以措辞改成"不比析构加移动构造更复杂"：析构的代价已经由 ¶2.3 的 O(N+M) 总量控制，移动构造是 O(1)。
</details>

## 小结

- `view` = `range` + `movable` + `enable_view`；语义要求全是**复杂度**承诺；
- 成为视图的三种方式：继承 `view_base`、继承唯一的 `view_interface<D>`、特化 `enable_view`；
- C++20 的 DR 序列把视图从"semiregular、O(1) 析构"放宽为"movable、N 份副本 O(N+M) 析构"，从而允许只移动的、拥有元素的视图。
