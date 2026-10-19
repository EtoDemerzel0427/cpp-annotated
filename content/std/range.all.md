---
title: all 视图：ref_view 与 owning_view
summary: views::all 决定一个范围以什么方式进入管道：本来是视图就复制，左值用 ref_view 借用，右值用 owning_view 接管；以及这两个视图的性质和由此得到的所有权规则。
status: done
covers: *
since: c++20
papers: P0896R4, P2325R3, P2415R2
related: range.adaptors, range.view, range.req, range.dangling, range.utility, range.as.const, initializer.list.syn
tags: 标准库, 范围, 视图, ref_view, owning_view, 生命周期
updated: 2026-10-19
---

!!! tldr
    - `views::all(E)` 有三种结果：`E` 本来是视图就复制一份；`E` 是左值就得到 `ref_view`；否则把 `E` 移进 `owning_view`。
    - 所有适配器的推导指引都经过 `views::all_t`，所以 `v | views::filter(p)` 借用 `v`，`std::move(v) | views::filter(p)` 拥有 `v` 的元素。
    - `ref_view` 只保存一个指针，可以复制，是借用范围；它的 const 不传到元素上。它拒绝一切右值，包括 `const R&` 能绑定的那种。
    - `owning_view` 只能移动，const 会传到元素上，是否借用随底层而定；它不接受 `initializer_list`。

## 管道里谁拥有元素

```cpp run ok
#include <ranges>
#include <vector>
using V = std::vector<int>;
V make() { return {1, 2, 3}; }
int main() {
  V v{1, 2, 3};
  const V cv{4, 5};
  auto a = std::views::all(v);        // ref_view<V>
  auto b = std::views::all(cv);       // ref_view<const V>
  auto c = std::views::all(make());   // owning_view<V>：临时量被移进来
  auto d = std::views::all(a);        // a 已是视图：复制一份
  static_assert(std::same_as<decltype(a), std::ranges::ref_view<V>>);
  static_assert(std::same_as<decltype(b), std::ranges::ref_view<const V>>);
  static_assert(std::same_as<decltype(c), std::ranges::owning_view<V>>);
  static_assert(std::same_as<decltype(d), std::ranges::ref_view<V>>);
  static_assert(sizeof(a) == sizeof(void*));
  return (c.size() == 3 && &a.base() == &v) ? 0 : 1;
}
```

每个适配器的底层都必须是视图（[[range.adaptors]]），而用户手里通常是 `vector` 这样的容器。`views::all` 决定一个范围以什么方式进入管道：借用（`ref_view`）、接管（`owning_view`），还是本来就是视图、直接复制。所有适配器的推导指引都写成 `xxx_view(R&&, ...) -> xxx_view<views::all_t<R>, ...>`，所以弄清 `views::all`，就弄清了管道中的所有权。

| 写法 | 底层类型 | 谁拥有元素 | 视图能否比原对象活得久 |
|---|---|---|---|
| `v \| views::filter(p)` | `ref_view<V>` | `v` | 不能 |
| `std::move(v) \| views::filter(p)` | `owning_view<V>` | 视图 | 能 |
| `make_vec() \| views::filter(p)` | `owning_view<V>` | 视图 | 能 |
| `std::span(v) \| views::filter(p)` | `span<int>` | `v` | 不能 |
| `std::as_const(v) \| views::filter(p)` | `ref_view<const V>` | `v` | 不能 |

## views::all [range.all.general]

¶1 `views::all` 返回一个包含范围实参全部元素的视图。¶2 它是范围适配器对象。给定子表达式 `E`，`views::all(E)` 依次尝试：

1. ¶2.1 如果 `E` 退化后的类型建模 `view`，结果是 `E` 的副本（*decay-copy*`(E)`）；
2. ¶2.2 否则，如果 `ref_view{E}` 良构，结果是它；
3. ¶2.3 否则，结果是 `owning_view{E}`。

`views::all_t<R>` 定义为 `decltype(views::all(declval<R>()))`（[[ranges.syn]]），要求 `R` 是 `viewable_range`（[[range.refinements#6]]）：本身是视图，或者是左值范围，或者是可移动且不是 `initializer_list` 的右值范围。

## ref_view [range.ref.view]

¶1 `ref_view` 是另一个范围的元素的视图：

```cpp
template<range R> requires is_object_v<R>
class ref_view : public view_interface<ref_view<R>> {
  R* r_;
public:
  template<different-from<ref_view> T> requires see below
    constexpr ref_view(T&& t);
  constexpr R& base() const { return *r_; }
  constexpr iterator_t<R> begin() const { return ranges::begin(*r_); }
  constexpr sentinel_t<R> end() const { return ranges::end(*r_); }
  // empty、size、reserve_hint、data 按 R 的能力转发
};
template<class R> ref_view(R&) -> ref_view<R>;
```

### 只接受左值（¶2–¶3）

¶3 构造函数的约束借助两个仅用于说明的函数 *FUN* 表达：

```cpp
void FUN(R&);
void FUN(R&&) = delete;
// 约束：convertible_to<T, R&> && requires { FUN(declval<T>()); }
```

为什么不直接写 `ref_view(R& r)`？因为 `R` 是 `const V` 时，`const V&` 能绑定到临时的 `V`，`ref_view<const V>` 就能从临时量构造，构造完立刻悬垂。加上被删除的 `FUN(R&&)` 后，右值实参与它匹配得更好，`FUN(declval<T>())` 选中被删除的函数，约束不成立，这条路就被堵死了。

构造函数写成模板 `T&&`，还能接受可以隐式转换为 `R&` 的类型。¶2 构造的效果是 `r_ = addressof(static_cast<R&>(std::forward<T>(t)))`。`different-from<ref_view>` 约束保证它不会抢走 `ref_view` 自己的复制构造（[[range.utility]]）。

```cpp run ok
#include <ranges>
#include <vector>
using V = std::vector<int>;
static_assert(!std::constructible_from<std::ranges::ref_view<V>, V>);
static_assert(!std::constructible_from<std::ranges::ref_view<const V>, V>);   // 被 FUN(R&&) 挡住
static_assert(std::constructible_from<std::ranges::ref_view<const V>, V&>);
int main() {}
```

### 性质

- 只保存一个指针，复制是 O(1)，所以是视图。
- const 不传到元素上：`begin() const` 返回 `iterator_t<R>`，而不是 `iterator_t<const R>`。通过 `const ref_view<vector<int>>` 仍然可以修改元素。它的行为像指针，而不像容器。
- 是借用范围：`enable_borrowed_range<ref_view<T>>` 恒为 `true`，迭代器指向 `*r_`，与 `ref_view` 对象无关。
- 没有默认构造函数，指针成员没有合理的默认值。C++20 最初要求视图可以默认构造，`ref_view` 当时把指针初始化为 `nullptr`；[[P2325R3]] 取消这一要求后，`ref_view` 的默认构造函数也被去掉了。

## owning_view [range.owning.view]

¶1 `owning_view` 是另一个范围的元素的只可移动视图：

```cpp
template<range R>
  requires movable<R> && (!is-initializer-list<R>)
class owning_view : public view_interface<owning_view<R>> {
  R r_ = R();
public:
  owning_view() requires default_initializable<R> = default;
  constexpr owning_view(R&& t);                 // ¶2：用 std::move(t) 初始化 r_
  owning_view(owning_view&&) = default;
  owning_view& operator=(owning_view&&) = default;
  constexpr R& base() & noexcept;               // 另有 const&、&&、const&& 三个重载
  constexpr iterator_t<R> begin();
  constexpr auto begin() const requires range<const R>;
  // end、empty、size、reserve_hint、data 同样分 const 与非 const
};
```

### 性质

- 只能移动。类声明了移动操作，复制构造和复制赋值被隐式删除。元素只存在于一个对象中，所以满足视图的复杂度要求：N 个副本的析构总代价是 O(N+M)（[[range.view]]）。
- const 会传到元素上：`begin() const` 使用 `const R`，与容器一致。
- 是否借用随底层而定：`enable_borrowed_range<owning_view<T>>` 等于 `enable_borrowed_range<T>`。对 `vector` 为假，所以算法对右值 `owning_view<vector<int>>` 返回 `dangling`（[[range.dangling]]）。
- 不接受 `initializer_list`。`initializer_list` 本身不拥有元素，它引用一个临时数组，拥有一个 `initializer_list` 并不能延长那个数组的生命周期，结果必然悬垂。

!!! history "把右值容器放进管道"
    C++20 最初没有 `owning_view`，`views::all` 对不是视图的右值直接非良构，所以 `make_vector() | views::filter(p)` 不能编译。[[P2415R2]]（What is a view?）作为对 C++20 的缺陷报告，重新定义了视图，允许只能移动、拥有元素的视图，并加入 `owning_view`。从此这种写法合法而且安全：临时 `vector` 被移进管道，和视图一起存活。

## 常见误解

!!! pitfall "从函数返回基于局部容器的视图"
    `return local_vec | views::transform(f);` 返回的是 `transform_view<ref_view<V>, F>`，`ref_view` 指向即将销毁的 `local_vec`，之后使用就是{{ub}}。改成 `return std::move(local_vec) | views::transform(f);`，底层就成了 `owning_view`。[[range.dangling]] 中有可以运行的对照例子。

!!! pitfall "owning_view 让整个管道只能移动"
    `auto p = make_vec() | views::filter(f);` 中的 `p` 只能移动。按值传给形参为 `auto r` 的函数时要写 `std::move(p)`；按 `const auto&` 传则会失败，因为 `filter_view` 没有 const 的 `begin`。泛型函数可以写成 `void consume(std::ranges::viewable_range auto&& r)`，在内部用 `views::all(std::forward<decltype(r)>(r))`。

## 思考题

!!! question "思考题 1"
    `views::all(std::initializer_list<int>{1, 2, 3})` 能编译吗？`auto il = {1, 2, 3}; views::all(il)` 呢？

<details markdown="1">
<summary>答案</summary>

前者不能：右值 `initializer_list` 不是 `viewable_range`（[[range.refinements#6]]），`owning_view` 也明确排除了它。后者可以：`il` 是左值，得到 `ref_view<std::initializer_list<int>>`，只要 `il` 还在作用域内就是安全的。
</details>

!!! question "思考题 2"
    `ref_view` 的 `begin()` 是 const 成员函数，却返回可变迭代器。这违反 const 正确性吗？

<details markdown="1">
<summary>答案</summary>

不违反。`ref_view` 的状态只是一个指针，`const ref_view` 表示这个指针不变，而不是被指向的对象不变，和 `int* const` 一样。视图普遍如此，`span` 也是。需要只读访问时，用 `views::as_const` 或 `ranges::cbegin`（[[range.as.const]]、[[range.access]]）。
</details>
