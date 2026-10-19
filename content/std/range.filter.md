---
title: filter 视图
summary: filter_view 只保留满足谓词的元素。为了让 begin() 是摊还常数时间，它缓存第一次的结果，由此带来没有 const begin、修改底层后结果陈旧、并发调用 begin 是数据竞争等问题；把元素改得不再满足谓词还可能导致未定义行为。
status: done
covers: *
since: c++20
papers: P0896R4, P2494R2
related: range.adaptors, range.range, range.nonprop.cache, range.move.wrap, range.transform, range.drop, concepts.equality, concepts.callable, res.on.data.races, range.all
tags: 标准库, 范围, filter, 缓存, 陷阱
updated: 2026-10-19
---

!!! tldr
    - `views::filter(pred)` 只保留满足 `pred` 的元素。迭代器最多是双向的，视图没有 `size()`，也不是借用范围。
    - 第一次调用 `begin()` 要线性查找，标准要求把结果缓存在视图里，之后的调用是 O(1)。
    - 缓存要写入视图，所以 `begin()` 不是 const 成员：底层是前向范围时，`const filter_view` 不能遍历。
    - 第一次 `begin()` 之后修改底层，同一个视图会给出陈旧的结果；两个线程同时对同一个视图调用 `begin()` 是数据竞争。
    - 通过迭代器把元素改得不再满足谓词，可能导致未定义行为。谓词必须保持相等性，不能有状态。

## 基本用法 [range.filter.overview]

```cpp run ok
#include <ranges>
#include <vector>
#include <cstdio>
int main() {
  std::vector<int> is{0, 1, 2, 3, 4, 5, 6};
  auto evens = std::views::filter(is, [](int i) { return i % 2 == 0; });
  for (int i : evens) std::printf("%d ", i);   // 0 2 4 6
  std::puts("");
}
```

¶1 `filter_view` 给出底层序列中满足谓词的那些元素。¶2 `views::filter` 是范围适配器对象（[[range.adaptors]]），`views::filter(E, P)` 等价于 `filter_view(E, P)`。¶3 例 1 就是上面的代码。

## 类模板 [range.filter.view]

```cpp
template<input_range V, indirect_unary_predicate<iterator_t<V>> Pred>
  requires view<V> && is_object_v<Pred>
class filter_view : public view_interface<filter_view<V, Pred>> {
  V base_ = V();
  movable-box<Pred> pred_;
  template<bool> class iterator;
  template<bool> class sentinel;
public:
  constexpr explicit filter_view(V base, Pred pred);
  constexpr const Pred& pred() const;

  constexpr iterator<false> begin();
  constexpr iterator<true> begin() const
    requires (input_range<const V> && !forward_range<const V> &&
              indirect_unary_predicate<const Pred, iterator_t<const V>>);

  constexpr auto end();       // 底层是 common_range 时返回迭代器，否则返回哨位
  constexpr sentinel<true> end() const requires /* 同上 */;
};
template<class R, class Pred>
  filter_view(R&&, Pred) -> filter_view<views::all_t<R>, Pred>;
```

- 谓词的约束 `indirect_unary_predicate` 要求它能以底层迭代器的引用类型和值类型的左值调用（[[indirectcallable.indirectinvocable]]）。它细化了 `regular_invocable`，所以谓词必须保持相等性：对相等的输入总是给出相等的结果（[[concepts.equality]]、[[concepts.callable]]）。
- 谓词存放在 *movable-box* 中（[[range.move.wrap]]），所以带捕获的 lambda 也能用。C++23 起只能移动的谓词也可以（[[P2494R2]]）。
- 没有 `size()`：不遍历就不知道有多少元素满足谓词，所以 `filter_view` 永远不是 `sized_range`。
- 底层是 common range 时，`end()` 返回一个指向底层末尾的迭代器，`filter_view` 也是 common 的；否则返回哨位。

## begin() 的缓存（¶3–¶7）

¶3 `begin()` 的前置条件是 `pred_.has_value()`：*movable-box* 在赋值时如果构造抛出异常，可能变空。¶4 它返回指向 `ranges::find_if(base_, ref(*pred_))` 的迭代器，也就是第一个满足谓词的元素。

[[range.range]] ¶2.2 要求 `begin()` 是摊还常数时间，而找第一个满足谓词的元素需要线性时间。唯一的办法是第一次找到后记下来，¶5 正是这样规定的：

!!! std
    In order to provide the amortized constant time complexity required by the range concept when filter_view models forward_range, this function caches the result within the filter_view for use on subsequent calls.

这句 *Remarks* 是规范性的，实现必须缓存（[[g:begin-caching]]）。缓存写在 `filter_view` 对象里，所以这个 `begin()` 不是 const 成员函数。

¶6–¶7 是 C++23 之后的新措辞：只有当 `const V` 是输入范围而不是前向范围时，才有一个 const 的 `begin()`，注 1 说明它不缓存。输入范围只能遍历一次，`begin()` 本来就不要求保持相等性（[[range.range]] ¶2.3），也就不需要靠缓存满足复杂度要求。对 `vector`、`list` 这类前向底层，`const filter_view` 仍然不能遍历。

!!! impl "libc++"
    libc++ 的 `filter_view` 只在底层是前向范围时才存放缓存（`__non_propagating_cache<iterator_t<V>>`，否则是一个空类型），与规范的意图一致。截至 Clang 23 附带的 libc++，还没有提供面向输入底层的 const `begin()`，迭代器也还不是 `template<bool Const>`。

## 迭代器 [range.filter.iterator]

迭代器保存底层迭代器 `current_`，还保存一个指向父视图的指针 `parent_`，因为 `++` 时要用到谓词。迭代器依赖视图对象，所以 `filter_view` 不是借用范围。

¶2 `iterator_concept` 的规则是：`Const` 为真时是输入迭代器；否则底层是双向范围时为双向，底层是前向范围时为前向，其余为输入。它永远不会是随机访问的，因为跳过 n 个满足谓词的元素不可能是常数时间。¶3 C++17 风格的 `iterator_category` 只在底层是前向范围时声明，同样最多到 `bidirectional_iterator_tag`。

¶8 `operator*` 直接返回底层元素的引用，所以元素是可以写的。¶10 `++` 从下一个位置开始找下一个满足谓词的元素：

```cpp
current_ = ranges::find_if(std::move(++current_), ranges::end(parent_->base_),
                           ref(*parent_->pred_));
```

¶12 `--` 一直后退，直到遇到满足谓词的元素：`do --current_; while (!invoke(*parent_->pred_, *current_));`。这里没有下界检查，从 `begin()` 再往前退就越过了底层的开头，违反前置条件。

¶1 注 1 给出了一条警告：

!!! std
    Modification of the element a filter_view::iterator denotes can result in undefined behavior if the underlying range is a forward_range and the resulting value does not satisfy the filter predicate when the predicate is next evaluated for that element

原因在于，缓存的 `begin()` 和正在使用的迭代器都假定自己指向满足谓词的元素。把元素改成不满足谓词后，这个假定不再成立，算法的前提被破坏了。

## 常见陷阱

### const 的 filter_view 不能遍历

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

修复方法是把形参改成转发引用 `auto&&`，或者按值接收 `std::ranges::view auto`。这不是 `filter_view` 独有的问题，凡是缓存 `begin()` 的视图都有：`drop_while_view`、`split_view`、`chunk_by_view` 没有 const 的 `begin`；`drop_view` 在底层不是随机访问且有大小时、`reverse_view` 在底层不是 common 时，也没有。

### 第一次 begin() 之后修改底层

```cpp run ok
#include <ranges>
#include <vector>
#include <cstdio>
int main() {
  std::vector<int> v{1, 2, 3, 4};
  auto ev = v | std::views::filter([](int x) { return x % 2 == 0; });
  auto copy = ev;           // 复制视图：缓存不会跟着复制
  (void)ev.begin();         // ev 缓存了指向 2 的迭代器
  v[0] = 0;
  std::printf("%d %d\n", *ev.begin(), *copy.begin());   // 2 0
}
```

`v[0] = 0` 之后，第一个满足谓词的元素其实是 `0`，但 `ev.begin()` 仍然给出缓存的 `2`。同一个视图、同样的底层数据，遍历结果取决于之前有没有调用过 `begin()`。`copy` 没有继承缓存（缓存不传播，见 [[range.nonprop.cache]]），重新查找，得到 `0`。

所以视图最好在创建后尽快使用一次就丢掉；底层可能变化时，就重新创建视图。如果修改导致底层重新分配内存（例如 `v.push_back(...)`），缓存的迭代器就失效了，再调用 `ev.begin()` 是{{ub}}。

### 通过 filter 把元素改得不再满足谓词

```cpp run ub
#include <ranges>
#include <vector>
#include <cstdio>
int main() {
  std::vector<int> v{2, 4, 6};
  auto ev = v | std::views::filter([](int x) { return x % 2 == 0; });
  for (int& x : ev) x += 1;     // 全部改成奇数
  for (int x : ev) std::printf("%d ", x);   // UB：缓存的 begin 指向不满足谓词的 3
  std::puts("");
}
```

本机 Clang 23 运行时第二个循环输出 `3`：一个过滤偶数的视图给出了奇数。按 ¶1 注 1，这是未定义行为。需要把匹配的元素改得不再匹配时，可以用 `std::ranges::for_each` 加手写的条件，或者先把元素收集到容器里。

### 有状态的谓词

```cpp
int n = 0;
auto first3 = v | views::filter([&n](int) { return n++ < 3; });
// 违反 regular_invocable 的语义要求
```

谓词在 `++`、`--` 时都可能被调用，`filter` 也不保证每个元素只调用一次，双向遍历时会再次调用。有状态的谓词不保持相等性，行为没有保证。想取前 3 个元素，用 `views::take(3)`。

### 并发调用 begin()

标准库只保证并发调用 const 成员函数不会产生数据竞争（[[res.on.data.races]]）。`filter_view::begin()` 不是 const 的，它会写缓存。两个线程同时对同一个 `filter_view` 对象调用 `begin()`，例如都用范围 `for` 遍历它，就是数据竞争，行为未定义{{ub}}。每个线程使用自己的视图副本即可，副本之间不共享缓存。

### 与 transform 组合时函数被调用两次

`transform | filter` 中，`filter` 判断时解引用一次，调用一次变换函数；读取元素时又解引用一次，再调用一次。见 [[range.transform]]。

## 思考题

!!! question "思考题 1"
    为什么标准不用 `mutable` 成员实现缓存，从而提供 const 的 `begin()`？

<details markdown="1">
<summary>答案</summary>

那样 const 成员函数就会写共享状态，违背 [[res.on.data.races]] 的约定：并发调用库类型的 const 成员是安全的。要么加锁，带来额外开销；要么让 const 成员不再线程安全，破坏整个库的约定。标准选择不提供 const 遍历，把缓存属于这个对象写进类型。
</details>

!!! question "思考题 2"
    底层是 `istream_view` 时，`filter_view` 会缓存 `begin()` 吗？

<details markdown="1">
<summary>答案</summary>

不会，也不需要。¶5 只要求 `filter_view` 建模 `forward_range` 时缓存。输入范围只能遍历一次，`begin()` 本来就不要求保持相等性（[[range.range]] ¶2.3）。当前草案还为 `const V` 是输入但非前向范围的情况提供了不缓存的 const `begin()`（¶6–¶7）。
</details>

## 小结

| 性质 | `filter_view` |
|---|---|
| 迭代器强度 | 最多双向 |
| sized | 永远不是 |
| common | 底层 common 时是 |
| 借用 | 否 |
| const 可遍历 | 否；输入但非前向的底层例外 |
| `begin()` | 第一次 O(n)，之后 O(1)，结果被缓存 |
| 元素可写 | 是，但改得不满足谓词可能是 UB |
