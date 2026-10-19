---
title: 视图
summary: 什么样的范围可以被适配器廉价地按值持有：view 概念的定义、它的复杂度要求，以及用 view_base、view_interface 或 enable_view 声明一个类型是视图。
status: done
since: c++20
papers: P0896R4, P1456R1, P2325R3, P2415R2
related: range.req, range.range, range.all, view.interface, range.adaptors, concepts.object, namespace.std, views.contiguous, string.view
tags: 标准库, 范围, 视图, 概念
updated: 2026-10-19
---

!!! tldr
    - `view` 是可以被廉价地按值传递的范围，范围适配器按值保存的底层范围都是视图。
    - 定义是 `range<T> && movable<T> && enable_view<T>`。视图和普通容器在语法上无法区分，所以类型要主动声明自己是视图。
    - 语义要求全部是复杂度承诺：移动构造 O(1)，可复制时复制构造 O(1)，N 个副本的析构总代价 O(N+M)。
    - 视图可以拥有元素，只要不会因为复制而重复拥有。`owning_view`、`single_view`、`std::generator` 都是视图。
    - 声明方式有三种：公开继承 `view_base`，公开继承唯一的 `view_interface<D>`，或者特化 `enable_view`。

## 为什么需要 view 概念

```cpp
std::vector<int> v = /* 一百万个元素 */;
auto r = v | std::views::filter(pred)
           | std::views::transform(f);
```

适配器把它的底层范围按值保存起来（[[range.adaptors]]）。如果 `filter` 保存的是 `vector` 的一份副本，管道的每一级都可能复制整个数据集，惰性求值就失去了意义。实际上 `v` 先被 `views::all` 包装成 `ref_view`，它只保存一个指针（[[range.all]]）。

所以适配器需要一个概念来回答：哪些范围可以放心地按值保存？这个概念就是 `view`，术语见 [[g:range-view]]。

## 定义（¶1、¶5）

¶1 `view` 由三个条件组成：

```cpp
template<class T>
  concept view = range<T> && movable<T> && enable_view<T>;
```

`range<T>` 要求有 `begin` 和 `end`（[[range.range]]）。`movable<T>` 要求 `T` 是可以移动构造、移动赋值和交换的对象类型（[[concepts.object]]）。

¶5 第三个条件 `enable_view<T>` 是一个变量模板，由类型自己声明。原因是 `vector` 和 `span` 都有 `begin`、`end`，都可以移动，语法上看不出区别；两者的差别在复制和析构的代价上，这只能由类型作者来承诺。

## 复杂度要求（¶2–¶4）

¶2 一个类型满足上面的概念，还要符合下面五条才算建模（model）`view`，也就是真正是一个视图：

- ¶2.1 移动构造是 O(1)；
- ¶2.2 移动赋值不比先析构再移动构造更复杂；
- ¶2.3 从一个含 M 个元素的对象复制或移动出 N 个对象后，析构这 N 个对象的总代价是 O(N+M)；
- ¶2.4 要么不可复制构造，要么复制构造是 O(1)；
- ¶2.5 要么不可复制，要么复制赋值不比先析构再复制构造更复杂。

¶3 注 1 指出，由这些条件可以推出：被移出的对象，析构是 O(1)。

¶2.3 的写法允许视图拥有元素，只要这些元素总共只被析构一次。下面三种类型可以对照着看：

| 类型 | N 个副本的析构 | 是否符合 |
|---|---|---|
| `owning_view<vector<int>>`：只能移动，被移出的对象为空 | 一个对象析构 M 个元素，其余 N−1 个是空的 | O(N+M)，符合 |
| 用 `shared_ptr` 共享元素 | 最后一个副本析构 M 个元素，其余只减引用计数 | O(N+M)，符合 |
| 可复制，每份副本都深复制元素 | 每份都析构 M 个元素 | 复制本身就违反 ¶2.4 |

¶4 例 1 列出了三种典型的视图：包装一对迭代器的类型；用 `shared_ptr` 持有元素、所有副本共享所有权的类型；按需生成元素的类型。`vector<string>` 不是视图，因为复制它要复制全部元素，不能在常数时间内完成。

## 怎样声明一个视图（¶5–¶7）

```cpp
template<class T>
  constexpr bool enable_view =
    derived_from<T, view_base> || is-derived-from-view-interface<T>;
```

¶6 *is-derived-from-view-interface*`<T>` 是一个仅用于说明的变量模板。当且仅当 `T` 恰好有一个公开基类 `view_interface<U>`，并且没有其他 `view_interface<V>` 基类时，它为 `true`。

因此一个类型有三种方式成为视图：

1. 公开继承 `std::ranges::view_base`，这是一个空的标签类；
2. 公开继承 `std::ranges::view_interface<Derived>`（[[view.interface]]），同时得到 `empty()`、`size()`、`front()`、`operator[]` 等成员。通常推荐这种做法；
3. 特化 `enable_view`。¶7 允许用户为 cv 非限定的程序定义类型特化它：建模 `view` 的类型特化为 `true`，不建模的特化为 `false`。特化必须能用于常量表达式，类型为 `const bool`。

特化为 `false` 有实际用途：一个类型因为继承了某个从 `view_interface` 派生的基类而被误判为视图时，可以这样关掉。标准库的 `basic_string_view` 和 `span` 用的是第 3 种方式，它们在各自的头文件概要（[[string.view.synop]]、[[span.syn]]）里把 `enable_view` 和 `enable_borrowed_range` 都特化为 `true`。

```cpp run ok
#include <memory>
#include <ranges>
#include <vector>
#include <cstdio>

// 共享所有权：复制只增加引用计数，O(1)
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

// 只能移动的视图
struct once : std::ranges::view_interface<once> {
  std::unique_ptr<int[]> data{new int[3]{1, 2, 3}};
  int* begin() const { return data.get(); }
  int* end() const { return data.get() + 3; }
};
static_assert(std::ranges::view<once> && !std::copyable<once>);

// 满足概念，但复制是 O(M)，不建模 view
struct fat : std::ranges::view_base {
  std::vector<int> v;
  auto begin() const { return v.begin(); }
  auto end() const { return v.end(); }
};
static_assert(std::ranges::view<fat>);

int main() {
  auto r = shared_ints({1, 2, 3, 4})
         | std::views::transform([](int x) { return x * 10; });
  for (int x : r) std::printf("%d ", x);
  for (int x : once{} | std::views::reverse) std::printf("%d ", x);
  std::puts("");   // 10 20 30 40 3 2 1
}
```

编译器只检查概念是否满足。`fat` 声称自己是视图，`static_assert` 通过，但它的复制是深复制，违反了 ¶2.4。把它放进管道，程序照样能运行，只是每一级适配器复制它时都会复制整个 `vector`。严格地说，这时程序已经违反了库的要求（[[res.on.requirements]]），标准对它的行为不再作任何保证。

!!! pitfall "必须恰好一个 view_interface 基类"
    如果一个类同时从 `view_interface<X>` 和 `view_interface<Y>` 派生，例如继承了两个各自用 CRTP 定义的视图，*is-derived-from-view-interface* 为假。两个基类各自提供 `empty()`、`size()` 等成员，本来就会造成歧义。

## 历史与演进

!!! history "视图的定义放宽了三次"
    1. C++20 最初的 Ranges 提案（[[P0896R4]]）要求视图是 `semiregular`（可复制、可默认构造），复制、移动、析构都是 O(1)。这实际上禁止了视图拥有元素。
    2. [[P1456R1]]（进入 C++20）把 `semiregular` 放宽为 `movable`，允许只能移动的视图，比如持有 `unique_ptr` 或协程句柄的类型。
    3. [[P2325R3]] 把可默认构造从 `view` 中去掉，标准视图的默认构造函数都改成有条件的（`requires default_initializable<V>`）。
    4. [[P2415R2]] 把析构 O(1) 改成今天 ¶2.3 的 O(N+M)，允许只能移动、拥有元素的视图，并据此新增了 `owning_view`，让 `views::all(std::move(vec))` 合法（[[range.all]]）。

    后两项都作为对 C++20 的缺陷报告（DR）处理，所以主流实现在 `-std=c++20` 下也采用新的规则。

## 常见误解

!!! pitfall "视图就是不拥有元素的范围"
    今天的定义只关心代价，不关心所有权。`owning_view`、`single_view`（自带一个元素）、`std::generator`（拥有协程帧）都是视图。更准确的理解是：按值传递一个视图，不会让总代价超过与元素个数成线性的范围。

!!! pitfall "视图都可以复制"
    `owning_view`、`generator`，以及底层是只移动视图的适配器结果，都只能移动。泛型代码用 `std::ranges::view auto v` 按值接收视图后，应当用 `std::move(v)` 继续传递，而不是复制。

## 思考题

!!! question "思考题 1"
    为 `std::vector<int>` 显式特化 `enable_view` 为 `true`，合法吗？

<details markdown="1">
<summary>答案</summary>

不合法。¶7 只允许为程序定义类型特化（[[namespace.std]]），`std::vector<int>` 不是程序定义类型。即使允许，它的复制是 O(N)，也不建模 `view`。
</details>

!!! question "思考题 2"
    ¶2.2 为什么不直接要求移动赋值是 O(1)？

<details markdown="1">
<summary>答案</summary>

移动赋值要先销毁左操作数原有的内容。视图拥有元素时（如 `owning_view`），销毁旧内容是 O(M)，不可能是 O(1)。所以措辞改成不比析构加移动构造更复杂：析构的代价已经由 ¶2.3 的 O(N+M) 总量控制，移动构造是 O(1)。
</details>
