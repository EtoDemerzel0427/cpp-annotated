---
title: take 与 take_while 视图
summary: views::take(n) 的表达式等价规则（对 empty_view、optional、span、string_view、subrange、iota_view、repeat_view 直接返回同类视图以避免模板膨胀），take_view 根据底层能力选择原生迭代器或 counted_iterator；n 超出长度时安全截断；输入范围上会多读一个元素；take_while 的哨位每次比较都调用谓词、永不 common、永不 sized。
status: done
covers: range.take, range.take.overview, range.take.view, range.take.sentinel, range.take.while, range.take.while.overview, range.take.while.view, range.take.while.sentinel
since: c++20
papers: P0896R4, P1739R4, P3168R2
related: range.drop, range.adaptors, range.counted, range.factories, range.iota, counted.iterator, range.common, range.req
tags: 标准库, 范围, take, take_while
updated: 2026-10-18
---

`take` 取前 n 个元素，`take_while` 取"直到谓词第一次不成立"为止的前缀。二者都是"截断"——对无限序列（`iota(0)`、`repeat(x)`）尤其重要，它们是让无限序列变得可用的标准手段。

## `views::take` 的表达式等价规则（[range.take.overview]）

¶1 `take_view` 产生另一个视图的前 N 个元素；若被适配的视图元素少于 N，则产生全部元素——**n 大于长度不会越界**。

¶2 令 `T` 为 `remove_cvref_t<decltype((E))>`，`D` 为 `range_difference_t<decltype((E))>`。若 `decltype((F))` 不建模 `convertible_to<D>`，`views::take(E, F)` 非良构。否则表达式等价于：

| 条 | `T` 是 | 结果 |
|---|---|---|
| 2.1 | `empty_view` 的特化 | `((void)F, decay-copy(E))`（E 与 F 求值顺序不定） |
| 2.2 | `optional` 的特化且建模 `view`（{{c++26}}） | `static_cast<D>(F) == D() ? ((void)E, T()) : decay-copy(E)` |
| 2.3 | random access + sized 的 `span` / `basic_string_view` / `subrange` | `U(ranges::begin(E), ranges::begin(E) + std::min<D>(ranges::distance(E), F))`（E 只求值一次）；`span` 得 `span<element_type>`（动态 extent），`string_view` 得自身类型，`subrange` 得 `subrange<iterator_t<T>>` |
| 2.4 | random access + sized 的 `iota_view` | `iota_view(*ranges::begin(E), *(ranges::begin(E) + std::min<D>(ranges::distance(E), F)))` |
| 2.5 | `repeat_view` | 有界：`views::repeat(*E.value_, std::min<D>(ranges::distance(E), F))`；无界：`views::repeat(*E.value_, static_cast<D>(F))` |
| 2.6 | 其他 | `take_view(E, F)` |

这些特例的意义：**结果类型与输入同类**。`span | take(3)` 仍是 `span`，可以传给只接受 `span` 的接口；而且避免了 `take_view<take_view<span<…>>>` 这样的模板层层嵌套。这一设计来自 [[P1739R4]]；`optional` 一行来自让 `optional` 成为视图的 [[P3168R2]]。

```cpp run ok
#include <ranges>
#include <span>
#include <string_view>
#include <vector>
using namespace std::literals;
std::vector<int> v{1, 2, 3, 4, 5};
auto s = std::span(v) | std::views::take(3);
static_assert(std::same_as<decltype(s), std::span<int>>);          // 不是 take_view
auto sv = "hello"sv | std::views::drop(1);
static_assert(std::same_as<decltype(sv), std::string_view>);
auto io = std::views::iota(0, 10) | std::views::take(3);
static_assert(std::same_as<decltype(io), std::ranges::iota_view<int, int>>);
auto rr = v | std::views::reverse | std::views::reverse;
static_assert(std::same_as<decltype(rr), std::ranges::ref_view<std::vector<int>>>);
int main() {}
```

注意规则只检查 `T` 本身：`vector | take(3)` 中 `T` 是 `vector<int>`，不是 `span`，所以仍得到 `take_view<ref_view<vector<int>>>`。若想要 `span`，就先写 `std::span(v)`。

## `take_view`（[range.take.view]）

```cpp
template<view V>
class take_view : public view_interface<take_view<V>> {
  V base_ = V();
  range_difference_t<V> count_ = 0;
  template<bool> class sentinel;
public:
  constexpr explicit take_view(V base, range_difference_t<V> count);  // 前置条件：count >= 0
  constexpr auto begin() requires (!simple-view<V>);
  constexpr auto begin() const requires range<const V>;
  constexpr auto end() requires (!simple-view<V>);
  constexpr auto end() const requires range<const V>;
  constexpr auto size() requires sized_range<V>;        // min(size(base_), count_)
  constexpr auto size() const requires sized_range<const V>;
  constexpr auto reserve_hint();                         // {{c++26}}：无论底层如何都能给出 count_ 作为上界
};
```

`begin()`/`end()` 根据底层能力在三种实现中选择：

| 底层 | `begin()` | `end()` | 结果 common? |
|---|---|---|---|
| sized + random access | 底层迭代器 | `begin + min(size, n)` | ✓ |
| sized，非 random access | `counted_iterator(begin, min(size, n))` | `default_sentinel` | ✗ |
| 非 sized，但 `end - begin` 可求 | `counted_iterator(begin, min(n, end - begin))` | `default_sentinel` | ✗ |
| 其他 | `counted_iterator(begin, n)` | *sentinel*：当计数归零**或**底层到达末尾时相等 | ✗ |

[[counted.iterator]] 是一个"带剩余计数的迭代器包装"。由于计数已经被预先截到 `min(size, n)`，前三种情况下尾部只需比较计数（`default_sentinel`）。

`take_view` **没有 begin 缓存**，const 可迭代性随底层；`enable_borrowed_range<take_view<T>>` = `enable_borrowed_range<T>`。

¶2 中的 *Remarks* 之外，有一个"`reserve_hint` 永远存在"的细节（C++26）：即使底层不知道长度，`count_` 也是一个上界，所以 `iota(0) | take(1000) | ranges::to<vector>()` 可以预留 1000。

```cpp run ok
#include <list>
#include <ranges>
#include <vector>
#include <cstdio>
int main() {
  std::vector<int> v{1, 2, 3, 4, 5};
  auto t = v | std::views::take(10);          // n 大于长度：只给 5 个，不越界
  static_assert(std::ranges::random_access_range<decltype(t)> && std::ranges::common_range<decltype(t)>);
  std::list<int> l{1, 2, 3};
  auto tl = l | std::views::take(2);
  static_assert(!std::ranges::common_range<decltype(tl)>);   // 迭代器是 counted_iterator，尾是 default_sentinel
  auto tw = v | std::views::take_while([](int x) { return x < 3; });
  static_assert(!std::ranges::common_range<decltype(tw)> && !std::ranges::sized_range<decltype(tw)>);
  std::printf("%zu %zu\n", t.size(), tl.size());   // 5 2
}
```

### 哨位（[range.take.sentinel]）

只在"非 sized 且不可求差"的情况下使用。它存底层哨位 `end_`，与 `counted_iterator` 比较时：`y.count() == 0 || y.base() == x.end_`——数够了或者底层到头了都算结束。

!!! pitfall "在输入范围上会多读一个"
    `take_view` 的迭代器是 `counted_iterator`，它的 `++` 会先推进底层迭代器、再减计数。取完第 n 个元素后，循环的最后一次 `++` 仍会推进底层——对 `istream_view` 而言就是**再读一个值**：

    ```cpp run ok
    #include <ranges>
    #include <sstream>
    #include <cstdio>
    int main() {
      std::istringstream in{"1 2 3 4 5"};
      for (int x : std::views::istream<int>(in) | std::views::take(3)) std::printf("%d ", x);
      int next = 0;
      in >> next;
      std::printf("| next=%d\n", next);   // 5：第 4 个值被 take 的最后一次 ++ 读走了
    }
    ```

    对于从网络、管道读数据的场景，这会"吞掉"一条消息。需要精确消费时，手写循环或使用 `ranges::copy_n` 这类按计数执行的算法。

## `take_while`（[range.take.while]）

¶1 给定一元谓词 `pred` 和视图 `r`，`take_while_view` 产生范围 `[ranges::begin(r), ranges::find_if_not(r, pred))`。¶2 `views::take_while(E, F)` 表达式等价于 `take_while_view(E, F)`。

```cpp
template<view V, class Pred>
  requires input_range<V> && is_object_v<Pred> &&
           indirect_unary_predicate<const Pred, iterator_t<V>>
class take_while_view : public view_interface<take_while_view<V, Pred>> {
  V base_ = V();
  movable-box<Pred> pred_;
public:
  constexpr auto begin() requires (!simple-view<V>) { return ranges::begin(base_); }
  constexpr auto begin() const requires range<const V> &&
    indirect_unary_predicate<const Pred, iterator_t<const V>>;
  constexpr auto end() requires (!simple-view<V>) { return sentinel<false>(ranges::end(base_), addressof(*pred_)); }
  constexpr auto end() const requires /* 同上 */;
};
```

要点：

- **谓词以 `const Pred` 调用**（约束是 `indirect_unary_predicate<const Pred, …>`）：`mutable` lambda 不能用；
- **迭代器就是底层迭代器**，结束判断全部放在哨位里（[range.take.while.sentinel]）：`x == end_ || !invoke(*pred_, *x)`。每一次与哨位的比较都会**调用谓词**——在范围 `for` 里，每步一次；
- **永不 common、永不 sized**：不遍历不知道在哪里停；
- **不是借用范围**：哨位里存着指向视图内谓词的指针；
- **没有缓存**：`begin()` 就是底层的 `begin()`。

[range.take.while.overview] ¶3 例 1 展示了与 `istream` 组合时的"多读"：读到 `5` 时谓词失败、循环结束，但 `5` 已经离开了流，之后 `input >> i` 读到 `6`。这与 `take` 的多读原因不同：`take_while` 必须**看到**第一个不满足的元素才能知道该停。

!!! tip "take_while 与 views::common"
    老式接口要迭代器对时，`take_while` 的结果需要先经过 `views::common`（[[range.common]]）。

## 小结

| | `take(n)` | `take_while(p)` |
|---|---|---|
| 特化返回同类视图 | `empty`、`optional`、`span`、`string_view`、`subrange`、`iota`、`repeat` | 无 |
| 迭代器 | 底层或 `counted_iterator` | 底层 |
| sized | 底层 sized 时 | 否 |
| common | 底层 sized+random access 时 | 否 |
| 借用 | 随底层 | 否 |
| 输入范围上的副作用 | 多推进一次底层 | 读到第一个失败元素才停 |
