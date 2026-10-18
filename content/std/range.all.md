---
title: all 视图：ref_view 与 owning_view
summary: views::all 把任意 viewable_range 变成视图的三分支规则；ref_view 用 FUN(R&)/FUN(R&&)=delete 技巧只接受左值、浅 const 且借用；owning_view 只能移动、深 const、借用性随底层；all_t 是所有适配器推导指引的入口——以及"把右值容器放进管道"从 C++20 初版的编译错误变成合法的历史。
status: done
covers: *
since: c++20
papers: P0896R4, P2415R2
related: range.adaptors, range.view, range.req, range.dangling, range.utility, range.as.const, initializer.list.syn
tags: 标准库, 范围, 视图, ref_view, owning_view, 生命周期
updated: 2026-10-18
---

每个适配器的底层都必须是视图（[[range.adaptors]]），可用户手里通常是 `vector`。`views::all` 就是那道"入口闸门"：它决定一个范围以什么方式进入管道——**借用**（`ref_view`）还是**接管**（`owning_view`），或者原样复制（本来就是视图）。所有适配器的推导指引都写成 `xxx_view(R&&, ...) -> xxx_view<views::all_t<R>, ...>`，所以理解了 `views::all` 就理解了管道里的所有权。

## `views::all`（[range.all.general]）

¶1 `views::all` 返回包含其范围实参全部元素的视图。¶2 它是范围适配器对象；给定子表达式 `E`，`views::all(E)` 表达式等价于：

1. ¶2.1 *decay-copy*`(E)`，若 `E` 退化后的类型建模 `view`；
2. ¶2.2 否则，`ref_view{E}`，若该表达式良构；
3. ¶2.3 否则，`owning_view{E}`。

`views::all_t<R>` 定义为 `decltype(views::all(declval<R>()))`（[[ranges.syn]]），约束 `viewable_range R`（[[range.req]]）。

```cpp run ok
#include <ranges>
#include <vector>
#include <string>
using V = std::vector<int>;
V make() { return {1, 2, 3}; }
int main() {
  V v{1, 2, 3};
  const V cv{4, 5};
  auto a = std::views::all(v);              // ref_view<V>
  auto b = std::views::all(cv);             // ref_view<const V>
  auto c = std::views::all(make());         // owning_view<V>：临时量被移进来
  auto d = std::views::all(a);              // a 已是视图：复制一份 ref_view
  static_assert(std::same_as<decltype(a), std::ranges::ref_view<V>>);
  static_assert(std::same_as<decltype(b), std::ranges::ref_view<const V>>);
  static_assert(std::same_as<decltype(c), std::ranges::owning_view<V>>);
  static_assert(std::same_as<decltype(d), std::ranges::ref_view<V>>);
  static_assert(!std::constructible_from<std::ranges::ref_view<V>, V>);   // FUN(R&&) = delete 挡住右值
  static_assert(sizeof(a) == sizeof(void*));
  return (c.size() == 3 && &a.base() == &v) ? 0 : 1;
}
```

## `ref_view`（[range.ref.view]）

¶1 `ref_view` 是另一个范围的元素的视图。

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
  // empty / size / reserve_hint / data：按 R 的能力转发
};
template<class R> ref_view(R&) -> ref_view<R>;
```

### 只接受左值：*FUN* 技巧（¶2–¶3）

¶3 构造函数的约束等价于：

```cpp
void FUN(R&);
void FUN(R&&) = delete;
// requires: convertible_to<T, R&> && requires { FUN(declval<T>()); }
```

为什么不直接写 `ref_view(R& r)`？因为那样的话，`ref_view<const V>` 能从临时 `V` 构造（`const V&` 绑定右值），视图立刻悬垂。用两个重载：右值实参会更好地匹配被删除的 `FUN(R&&)`，于是 `requires { FUN(declval<T>()); }` 不成立——**连 `const R&` 绑定右值的路也被堵死了**。同时这个构造函数是模板（`T&&`），还能接受"可以隐式转换为 `R&`"的类型。¶2 构造的效果是 `r_ = addressof(static_cast<R&>(std::forward<T>(t)))`。

`different-from<ref_view>` 约束则保证它不会劫持 `ref_view` 自己的复制构造（[[range.utility]]）。

### 性质

- **只存一个指针**：复制 O(1)，是视图；
- **浅 const**：`begin() const` 返回 `iterator_t<R>`（不是 `iterator_t<const R>`）。`const ref_view<vector<int>>` 仍能修改元素——它像指针，而不像容器；
- **借用**：`enable_borrowed_range<ref_view<T>>` 恒为 `true`（迭代器指向 `*r_`，与 `ref_view` 对象无关）；
- **没有默认构造**：指针成员没有合理的默认值（C++20 初版曾要求视图可默认构造，`ref_view` 当时用 `nullptr` 初始化，[[P2325R3]] 去掉了这一要求）。

## `owning_view`（[range.owning.view]）

¶1 `owning_view` 是另一个范围的元素的**只可移动**视图。

```cpp
template<range R>
  requires movable<R> && (!is-initializer-list<R>)
class owning_view : public view_interface<owning_view<R>> {
  R r_ = R();
public:
  owning_view() requires default_initializable<R> = default;
  constexpr owning_view(R&& t);                  // ¶2：r_ 用 std::move(t) 初始化
  owning_view(owning_view&&) = default;
  owning_view& operator=(owning_view&&) = default;
  constexpr R& base() & noexcept;                // 四种值类别的 base() 重载
  constexpr iterator_t<R> begin();
  constexpr auto begin() const requires range<const R>;
  // end / empty / size / reserve_hint / data 同样分 const 与非 const
};
```

### 性质

- **只能移动**：复制构造/赋值被隐式删除（声明了移动成员）。这使它满足 [[range.view]] ¶2.3 的"N 份副本 O(N+M) 析构"——元素只存在于一个对象里；
- **深 const**：`begin() const` 用 `const R`，与容器一致；
- **借用性随底层**：`enable_borrowed_range<owning_view<T>>` = `enable_borrowed_range<T>`；对 `vector` 来说为假，所以算法对右值 `owning_view<vector>` 仍返回 `dangling`（[[range.dangling]]）；
- **排除 `initializer_list`**：`initializer_list` 本身不拥有元素（它引用一个临时数组），"拥有一个 `initializer_list`"是假的所有权，必然悬垂。

!!! history "\"把右值容器放进管道\"的转变"
    C++20 初版没有 `owning_view`：`views::all` 对非视图右值直接非良构，所以 `make_vector() | views::filter(p)` 不能编译——这在当时被看作一种"安全"。[[P2415R2]]（"What is a view?"，作为 C++20 的 DR）重新定义了视图（允许只移动的拥有型视图），并加入 `owning_view`，让这种写法合法且安全：临时 vector 被**移入**管道，跟着视图一起活。

## 所有权的心智模型

| 写法 | `all_t` | 谁拥有元素 | 视图能否比原对象活得久 |
|---|---|---|---|
| `v \| views::filter(p)` | `ref_view<V>` | `v` | ✗（悬垂） |
| `std::move(v) \| views::filter(p)` | `owning_view<V>` | 视图 | ✓ |
| `make_vec() \| views::filter(p)` | `owning_view<V>` | 视图 | ✓ |
| `std::span(v) \| views::filter(p)` | `span<int>` | `v` | ✗ |
| `std::as_const(v) \| views::filter(p)` | `ref_view<const V>` | `v` | ✗ |

!!! pitfall "从函数返回基于局部容器的视图"
    `return local_vec | views::transform(f);` 返回的是 `transform_view<ref_view<V>, F>`，`ref_view` 指向即将销毁的 `local_vec`——{{ub}}。改成 `return std::move(local_vec) | views::transform(f);` 即可（`owning_view`）。[[range.dangling]] 中有可运行的对照例子。

!!! pitfall "owning_view 让管道只能移动"
    `auto p = make_vec() | views::filter(f);` 中 `p` 只能移动；把它按值传给一个形参为 `auto r` 的函数时要 `std::move(p)`，按 `const auto&` 传则会因 `filter_view` 无 const `begin` 而失败。泛型函数推荐写成 `void consume(std::ranges::viewable_range auto&& r)`，内部再 `views::all(std::forward<decltype(r)>(r))`。

## 思考题

<details markdown="1">
<summary>1. `views::all(std::initializer_list<int>{1,2,3})` 能编译吗？`auto il = {1,2,3}; views::all(il)` 呢？</summary>

前者不能：右值 `initializer_list` 不是 `viewable_range`（[[range.req]] ¶6），`owning_view` 也明确排除它。后者可以：`il` 是左值，得到 `ref_view<std::initializer_list<int>>`——只要 `il` 还活着就安全。
</details>

<details markdown="1">
<summary>2. 为什么 `ref_view` 的 `begin()` 是 const 成员却返回可变迭代器，而这不违反"const 正确性"？</summary>

`ref_view` 的状态只是一个指针；`const ref_view` 意味着"这个指针不变"，而不是"被指向的对象不变"——和 `int* const` 一样。视图普遍是浅 const 的（`span` 也是），要得到只读访问应使用 `views::as_const` 或 `ranges::cbegin`（[[range.as.const]]、[[range.access]]）。
</details>

## 小结

- `views::all`：视图 → 复制；左值 → `ref_view`；可移动右值 → `owning_view`；
- `ref_view`：一个指针，浅 const，借用，*FUN* 技巧拒绝一切右值；
- `owning_view`：只移动，深 const，借用性随底层，拒绝 `initializer_list`；
- 所有适配器经由 `views::all_t` 决定底层是借用还是拥有——这是管道生命周期分析的起点。
