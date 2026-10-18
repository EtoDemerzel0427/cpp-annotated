---
title: filter 视图
summary: filter_view 的完整契约与它最著名的三个坑——begin() 为满足"摊还 O(1)"而缓存，于是没有 const begin（最新草案只对"仅输入"的底层开放 const 迭代）、首次 begin 后修改底层会得到陈旧结果、通过迭代器把元素改成不满足谓词会导致 UB；迭代器最多双向、谓词必须保持相等性、并发调用 begin 是数据竞争。
status: done
covers: *
since: c++20
papers: P0896R4, P2494R2
related: range.adaptors, range.range, range.nonprop.cache, range.move.wrap, range.transform, range.drop, concepts.equality, concepts.callable, res.on.data.races, range.all
tags: 标准库, 范围, filter, 缓存, 陷阱
updated: 2026-10-18
---

`views::filter(pred)` 是最常用的适配器，也是把"惰性视图"与"`range` 的复杂度要求"之间的张力暴露得最彻底的一个。本页的主线是 `begin()` 的**缓存**（[[g:begin-caching]]）：它为什么存在、它让 `filter_view` 失去了什么、它在什么情况下会让你得到错误的结果。

## 概览（[range.filter.overview]）

¶1 `filter_view` 给出底层序列中满足谓词的元素的视图。¶2 `views::filter` 是范围适配器对象；`views::filter(E, P)` 表达式等价于 `filter_view(E, P)`。

## 类模板（[range.filter.view]）

```cpp
template<input_range V, indirect_unary_predicate<iterator_t<V>> Pred>
  requires view<V> && is_object_v<Pred>
class filter_view : public view_interface<filter_view<V, Pred>> {
  V base_ = V();
  movable-box<Pred> pred_;
  template<bool> class iterator;
  template<bool> class sentinel;
public:
  filter_view() requires default_initializable<V> && default_initializable<Pred> = default;
  constexpr explicit filter_view(V base, Pred pred);
  constexpr const Pred& pred() const;

  constexpr iterator<false> begin();
  constexpr iterator<true> begin() const
    requires (input_range<const V> && !forward_range<const V> &&
              indirect_unary_predicate<const Pred, iterator_t<const V>>);

  constexpr auto end();                 // common_range<V> 时返回 iterator<false>，否则 sentinel<false>
  constexpr sentinel<true> end() const requires /* 同上 */;
};
template<class R, class Pred>
  filter_view(R&&, Pred) -> filter_view<views::all_t<R>, Pred>;
```

- `indirect_unary_predicate<iterator_t<V>>`：谓词要能以 `iter_reference_t` 与 `iter_value_t&` 等多种形式调用（[[indirectcallable.indirectinvocable]]），而且它细化 `predicate` → `regular_invocable`，**要求保持相等性**（[[concepts.equality]]、[[concepts.callable]]）。
- 谓词存在 *movable-box* 中（[[range.move.wrap]]），所以带捕获的 lambda 也能用；C++23 起只可移动的谓词也行（[[P2494R2]]）。
- **没有 `size()`**：不遍历无法知道有多少元素满足谓词。所以 `filter_view` 永远不是 `sized_range`。

### `begin()` 与缓存（¶3–¶7）

¶3 前置条件：*pred_*`.has_value()`（*movable-box* 可能因为赋值时构造抛异常而变空）。¶4 返回 `{*this, ranges::find_if(base_, ref(*pred_))}`。

!!! std
    In order to provide the amortized constant time complexity required by the range concept when filter_view models forward_range, this function caches the result within the filter_view for use on subsequent calls.

    为了在 filter_view 建模 forward_range 时提供 range 概念要求的摊还常数时间复杂度，此函数把结果缓存在 filter_view 内，供后续调用使用。

[[range.range]] ¶2.2 要求 `begin()` 摊还 O(1)。但"第一个满足谓词的元素"要线性查找。唯一的办法：第一次找到后记住它。这句 *Remarks* 是**规范性的**——实现必须缓存，不是可选的优化。

缓存要写入 `filter_view` 对象，所以这个 `begin()` 是**非 const 的**。

¶6–¶7 是最新草案（C++26 之后的措辞调整）新增的 `const` 重载：只当 `const V` 是**输入但非前向**范围时才存在，并且注 1 明确它**不缓存**。理由是：输入范围只能遍历一次，`begin()` 本来就不必保持相等性，也就不需要缓存来满足"摊还 O(1)"。对 `vector`、`list` 这类前向底层，`const filter_view` **仍然不可迭代**。

!!! impl "libc++"
    libc++ 的 `filter_view` 只在 `forward_range<V>` 时才存放缓存（`__non_propagating_cache<iterator_t<V>>`，否则是一个空类型），与"只有 forward 时才需要缓存"的规范意图一致。截至编写时 libc++ 尚未提供上面那个面向"仅输入"底层的 `const begin()`，其迭代器也还不是 `template<bool Const>`。

### `end()`

底层是 common range 时，`end()` 返回一个指向底层末尾的 *iterator*，于是 `filter_view` 也是 common 的；否则返回 *sentinel*。

## 迭代器（[range.filter.iterator]）

迭代器保存底层迭代器 *current_* 和指向父视图的指针 *parent_*（要访问谓词），因此 `filter_view` **不是借用范围**。

- ¶2 `iterator_concept`：`Const` 为真时是 input；否则 V 为 bidirectional 则 **bidirectional**，forward 则 forward，否则 input。**永远不会是 random access**——跳过 n 个"满足谓词的元素"不可能 O(1)。
- ¶3 `iterator_category`（仅当底层 forward 时声明）同理最多到 `bidirectional_iterator_tag`。
- ¶10 `++`：`current_ = ranges::find_if(std::move(++current_), ranges::end(parent_->base_), ref(*parent_->pred_));`
- ¶12 `--`：`do --current_; while (!invoke(*parent_->pred_, *current_));`——注意这里**没有下界检查**：从 `begin()` 再往前退是越界（违反前置条件）。
- ¶8 `operator*` 直接返回底层的引用——**元素是可写的**。

¶1 注 1 给出了一条重要警告：

!!! std
    Modification of the element a filter_view::iterator denotes can result in undefined behavior if the underlying range is a forward_range and the resulting value does not satisfy the filter predicate when the predicate is next evaluated for that element.

    若底层是 forward_range，而通过 filter_view::iterator 修改元素后，该值在谓词下次对此元素求值时不再满足谓词，可能导致未定义行为。

机理：谓词是 `regular_invocable`，必须保持相等性——对"相等的输入"给出相等的结果。把元素改成不满足谓词之后，缓存的 `begin()`、或者正在使用的迭代器所"假定满足谓词"的位置就不再满足了；对同一元素再次求值的谓词给出了不同的结果——这违反了 `indirect_unary_predicate` 的语义要求，而违反库组件的语义要求即为未定义行为（[[res.on.requirements]]）。

## 坑点合集

### 1. const 的 filter_view 不是范围

```cpp run error
#include <ranges>
#include <vector>
void print(const auto& r) { for (int x : r) (void)x; }
int main() {
  std::vector<int> v{1, 2, 3, 4};
  auto ev = v | std::views::filter([](int x) { return x % 2 == 0; });
  print(ev);   // error: const filter_view 没有 begin()
}
```

修复方式：形参用转发引用 `auto&&`（或按值 `std::ranges::view auto`）；或者在调用处传 `ev` 的副本。这并非 `filter_view` 独有：`drop_view`（底层非随机访问+sized 时）、`drop_while_view`、`reverse_view`（底层非 common 时）、`split_view`、`chunk_by_view`、`slide_view` 等，只要有 `begin()` 缓存，就都没有可用的 const `begin`。

### 2. 第一次 begin() 之后修改底层：陈旧的缓存

```cpp run ok
#include <ranges>
#include <vector>
#include <cstdio>
int main() {
  std::vector<int> v{1, 2, 3, 4};
  auto ev = v | std::views::filter([](int x) { return x % 2 == 0; });
  auto copy = ev;              // 复制视图：缓存不随之复制（non-propagating）
  auto it = ev.begin();        // ev 缓存了指向 2 的迭代器
  v[0] = 0;
  std::printf("%d %d\n", *ev.begin(), *copy.begin());   // 2 0：副本重新查找
  (void)it;
}
```

`v[0] = 0` 之后，满足谓词的第一个元素其实是 `0`，但 `ev.begin()` 仍然给出 `2`。同一个视图、同样的底层数据，迭代结果取决于"之前有没有调用过 `begin()`"。复制出来的 `copy` 没有继承缓存（[[range.nonprop.cache]] 的"不传播"语义），于是得到 `0`。实践上的规则：**视图应当在创建后尽快一次性使用**；若底层可能变化，就重新创建视图。

若修改导致底层重新分配（`v.push_back(...)`），缓存的迭代器直接失效，再调用 `ev.begin()` 就是{{ub}}。

### 3. 通过 filter 把元素改得不再满足谓词

```cpp run ub
#include <ranges>
#include <vector>
#include <cstdio>
int main() {
  std::vector<int> v{2, 4, 6};
  auto ev = v | std::views::filter([](int x) { return x % 2 == 0; });
  for (int& x : ev) x += 1;     // 写成奇数：之后谓词对这些元素不再成立
  for (int x : ev) std::printf("%d ", x);   // UB：缓存的 begin 指向不满足谓词的 3
  std::puts("");
}
```

在本站环境中第二个循环输出 `3`——一个"过滤偶数"的视图吐出了奇数。按 ¶1 注 1 这是未定义行为。如果需要"修改匹配的元素使之不再匹配"，用 `std::ranges::for_each` 配合手写条件，或者先收集到容器里。

### 4. 有状态的谓词

```cpp
int n = 0;
auto first3 = v | views::filter([&n](int) { return n++ < 3; });   // 违反 regular_invocable 的语义要求
```

谓词在 `++`、`--` 时都可能被调用，`filter` 也不保证每个元素只调用一次（双向遍历时会再次调用）。有状态的谓词违反保持相等性，行为不受保证。要"取前 3 个"请用 `views::take(3)`。

### 5. 并发

标准库只保证**并发调用 const 成员函数**不产生数据竞争（[[res.on.data.races]]）。`filter_view::begin()` 是非 const 的、会写缓存，所以两个线程同时对**同一个** `filter_view` 对象调用 `begin()`（例如两个线程都在 `for` 遍历它）是数据竞争——{{ub}}。每个线程使用自己的视图副本即可（副本不共享缓存）。

### 6. 与 transform 组合时函数被调用两次

`transform | filter` 时，`filter` 判定要解引用一次（调用变换函数），你读取元素时又解引用一次。见 [[range.transform]]。

## 思考题

<details markdown="1">
<summary>1. 为什么标准不让 filter_view 用 mutable 成员实现缓存，从而提供 const begin()？</summary>

可以这么做，但那样 `const` 成员函数就会写共享状态，违背 [[res.on.data.races]] 的承诺——"并发调用库类型的 const 成员是安全的"。要么加锁（违背零开销），要么让 const 成员不再线程安全（破坏整个库的约定）。标准选择了第三条路：不提供 const 迭代，把"缓存属于这个对象"写进类型。
</details>

<details markdown="1">
<summary>2. 底层是 `istream_view` 时，`filter_view` 会缓存 begin 吗？</summary>

不会也不需要。¶5 只说"当 filter_view 建模 forward_range 时"缓存。输入范围只能遍历一次，`begin()` 本就不要求保持相等性（[[range.range]] ¶2.3）。最新草案还为 `const V` 是"仅输入"的情况补上了不缓存的 `const begin()`（¶6–¶7）。
</details>

## 小结

| 性质 | `filter_view` |
|---|---|
| 迭代器强度 | 最多 bidirectional |
| sized | 永不 |
| common | 底层 common 时是 |
| 借用 | 否 |
| const 可迭代 | 否（仅"仅输入"的底层在最新草案中例外） |
| `begin()` | 首次 O(n)，之后 O(1)，结果被缓存 |
| 元素可写 | 是，但写成不满足谓词是 UB |
