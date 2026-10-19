---
title: iota 视图与 views::indices
summary: views::iota 通过反复递增生成序列：有界与无界、元素可以是整数或迭代器、为什么拒绝符号不同的上下界、距离类型为何更宽、迭代器强度怎样确定，以及 C++26 的 views::indices。
status: done
covers: *
since: c++20
papers: P0896R4
related: range.factories, range.take, range.drop, iterator.concept.winc, iterator.concepts, unreachable.sentinel, range.enumerate
tags: 标准库, 范围, iota, 工厂
updated: 2026-10-19
---

!!! tldr
    - `views::iota(a)` 产生 `a, a+1, a+2, …` 的无限序列，`views::iota(a, b)` 产生 `[a, b)`。元素可以是整数，也可以是指针或任何迭代器。
    - 两个上下界都是整数时符号必须相同，`views::iota(0, v.size())` 编译失败。改用 `views::iota(0uz, v.size())` 或 C++26 的 `views::indices(v.size())`。
    - `views::iota(5, 0)` 不是空范围，而是违反前置条件，行为未定义。
    - `iota_view<int, int>` 的距离类型比 `int` 更宽，`size()` 在无符号域中计算，`iota(INT_MIN, INT_MAX)` 不会溢出。
    - 迭代器按值返回元素，C++17 视角下只是输入迭代器；`iota_view` 是借用范围。

## 从 0 数到 n

```cpp run ok
#include <ranges>
#include <vector>
#include <list>
#include <cstdio>
int main() {
  for (int i : std::views::iota(1, 4)) std::printf("%d ", i);    // 1 2 3

  std::vector<int> v{10, 20, 30};
  for (auto i : std::views::iota(0uz, v.size()))                  // 0uz：同为无符号
    std::printf("%d ", v[i]);                                       // 10 20 30

  std::list<int> l{7, 8};
  for (auto it : std::views::iota(l.begin(), l.end()))            // 元素是迭代器
    std::printf("%d ", *it);                                        // 7 8
  std::puts("");
}
```

[range.iota.overview] ¶1 `iota_view` 通过反复递增一个初始值来生成序列。¶2 `views::iota(E)` 和 `views::iota(E, F)` 分别等价于 `iota_view<decay_t<decltype((E))>>(E)` 和 `iota_view(E, F)`，后者通过类模板实参推导确定类型。

```cpp
template<weakly_incrementable W, semiregular Bound = unreachable_sentinel_t>
  requires weakly-equality-comparable-with<W, Bound> && copyable<W>
class iota_view : public view_interface<iota_view<W, Bound>> {
  W value_ = W();
  Bound bound_ = Bound();
  // ...
};
```

`W` 只需要能递增（`weakly_incrementable`）、能复制，并且能和 `Bound` 比较是否相等。整数、指针、迭代器都满足。`Bound` 默认是 `unreachable_sentinel_t`，一个和任何值都不相等的哨位（[[unreachable.sentinel]]），所以只给一个实参时序列是无限的。

## 符号不同的上下界被拒绝

```cpp run error
#include <ranges>
#include <vector>
int main() {
  std::vector<int> v{1, 2, 3};
  for (auto i : std::views::iota(0, v.size())) (void)i;
  // error: int 与 size_t 符号不同，无法推导
}
```

`iota_view` 的推导指引带有约束：

```cpp
template<class W, class Bound>
  requires (!is-integer-like<W> || !is-integer-like<Bound> ||
            (is-signed-integer-like<W> == is-signed-integer-like<Bound>))
  iota_view(W, Bound) -> iota_view<W, Bound>;
```

两个实参都是整数类型时，要求符号性相同。原因是混合符号时，循环终止依赖的 `value_ == bound_` 要经过算术转换，很容易出现永远不相等的情况，循环跑过头直到溢出。所以标准让它在推导阶段就失败。

修复的写法有三种：`views::iota(0uz, v.size())`，`views::iota(std::size_t{0}, v.size())`，或者用 `views::indices`。

### views::indices {{c++26}}

¶4 `views::indices(E)` 中，令 `T` 为 `E` 去掉引用和 cv 限定后的类型。如果 `T` 是整数类类型，它等价于 `views::iota(T(0), E)`，否则非良构。它专门用来从 0 数到一个容器的大小，起点的类型自动和 `E` 一致。

```cpp run ok
#include <ranges>
#include <vector>
#include <cstdio>
int main() {
  std::vector<int> v{10, 20, 30};
  for (auto i : std::views::indices(v.size()))
    std::printf("%zu:%d ", i, v[i]);      // 0:10 1:20 2:30
  std::puts("");
}
```

## 构造的前置条件 [range.iota.view]

¶6、¶8 构造 `iota_view(value, bound)` 的前置条件是：`Bound` 是 `unreachable_sentinel_t`，或者从 `value` 反复递增能到达 `bound`。如果 `W` 和 `Bound` 能比较大小（`totally_ordered_with`），还要求 `value <= bound`。

所以 `views::iota(5, 0)` 不是空范围，而是违反前置条件，行为未定义。上下界来自运行时数据时，先用 `std::min`、`std::max` 整理好。

¶10–¶11 `iota_view` 还可以从自己的一对迭代器（或迭代器加哨位）构造。`views::take` 和 `views::drop` 借此把切片的结果仍然表示成 `iota_view`，见下文。

## 距离类型：IOTA-DIFF-T（¶1）

`iota_view<int, int>` 的两个迭代器相减，结果用什么类型？`int` 不够用：`iota(INT_MIN, INT_MAX)` 的长度超过了 `INT_MAX`。¶1 定义的 *IOTA-DIFF-T*(W) 按顺序选择：

- ¶1.1 如果 `W` 不是整数类型，或者 `iter_difference_t<W>` 比 `W` 宽，用 `iter_difference_t<W>`；
- ¶1.2 否则，如果有比 `W` 更宽的有符号整数类型，用它；
- ¶1.3 否则，用一个未指定的有符号整数类（signed-integer-like）类型，宽度不小于 `W`（[[iterator.concept.winc]]）。注 1 说明，这个类型是否满足 `weakly_incrementable` 是未指定的。

所以 `iota_view<int, int>` 的距离类型是一个更宽的标准类型；`iota_view<long long, long long>` 在没有更宽标准整数的平台上，要用实现提供的整数类类型。本机 libc++ 用的是 `__int128`。

¶16 `size()` 也避免了溢出。上下界都是整数时，它先按符号分情况，再在无符号域中相减或相加：

```cpp
if constexpr (is-integer-like<W> && is-integer-like<Bound>)
  return (value_ < 0)
    ? ((bound_ < 0)
      ? to-unsigned-like(-value_) - to-unsigned-like(-bound_)
      : to-unsigned-like(bound_) + to-unsigned-like(-value_))
    : to-unsigned-like(bound_) - to-unsigned-like(value_);
else
  return to-unsigned-like(bound_ - value_);
```

直接写 `bound_ - value_` 时，`iota(INT_MIN, INT_MAX)` 会在有符号域里溢出。¶17 规定 `size()` 在以下任一条件成立时存在：`W` 与 `Bound` 同类型且 `W` 是 *advanceable*（见下文）；两者都是整数类类型；或者 `Bound` 与 `W` 可以相减（`sized_sentinel_for`）。

¶12–¶15 `begin()` 返回指向 `value_` 的迭代器。`W` 与 `Bound` 同类型时 `end()` 也返回迭代器，视图是首尾同型的；否则返回哨位或 `unreachable_sentinel`。`empty()` 返回 `value_ == bound_`。

## 迭代器强度 [range.iota.iterator]

迭代器支持多少操作取决于 `W`。¶2–¶5 定义了两个仅用于说明的概念来描述 `W` 的能力：

- ***decrementable***：在 `incrementable` 之上还支持 `--i` 和 `i--`，并且 `++` 和 `--` 互为逆运算；
- ***advanceable***：在 *decrementable* 之上还能比较大小，能和距离类型做 `+=`、`-=`、`+`、`-`，两个值能相减。¶5 后面一长串语义要求，归结起来就是加上 `n` 与递增 `n` 次结果相同。

[range.iota.iterator] ¶1 据此确定迭代器的 `iterator_concept`：

| `W` 建模 | `iterator_concept` | 例子 |
|---|---|---|
| *advanceable* | `random_access_iterator_tag` | 整数、指针、`vector` 迭代器 |
| *decrementable* | `bidirectional_iterator_tag` | `list` 迭代器 |
| `incrementable` | `forward_iterator_tag` | `forward_list` 迭代器 |
| 其他 | `input_iterator_tag` | 只满足 `weakly_incrementable` 的类型 |

迭代器只保存一个 `W value_`。¶4 `operator*` 按值返回 `value_` 的副本，`operator[](n)` 返回 `W(value_ + n)`。正因为按值返回，C++17 风格的 `iterator_category` 最多是 `input_iterator_tag`，而且只在 `W` 是 `incrementable` 且距离类型是整数类型时才声明：*Cpp17ForwardIterator* 要求 `reference` 是真正的引用。把 `iota` 的迭代器交给只认 C++17 类别的旧算法时，它们只会按输入迭代器处理。

¶2 注 1 指出，迭代器有意不提供 `iter_move` 和 `iter_swap` 的重载：元素本来就是纯右值，默认行为就是对的。¶5 注 2 说明 `operator*` 的 `noexcept` 规范是给默认的 `iter_move` 用的。

迭代器自带值，与 `iota_view` 对象无关，所以 `iota_view` 是借用范围（[[ranges.syn]]）。[range.iota.sentinel] 中的哨位保存 `Bound bound_`，与迭代器比较 `value_ == bound_`；`Bound` 与 `W` 能相减时，哨位和迭代器之间也能相减。

```cpp run ok
#include <ranges>
#include <iterator>
int main() {
  using I = std::ranges::iota_view<int, int>;
  static_assert(sizeof(std::ranges::range_difference_t<I>) > sizeof(int));
  using L = std::ranges::iota_view<long long, long long>;
  static_assert(sizeof(std::ranges::range_difference_t<L>) > sizeof(long long));
  static_assert(std::ranges::random_access_range<I> && std::ranges::sized_range<I>);
  static_assert(std::same_as<
      std::iterator_traits<std::ranges::iterator_t<I>>::iterator_category,
      std::input_iterator_tag>);          // C++17 视角下只是输入迭代器
  static_assert(std::ranges::borrowed_range<I>);
}
```

## 与 take、drop 的配合

`iota_view` 既是随机访问的又有大小时，`views::take` 和 `views::drop` 的结果仍是 `iota_view`，而不是外面再包一层（[[range.take]]、[[range.drop]]）。无界的 `iota(0)` 没有大小，所以 `iota(0) | take(10)` 得到的是 `take_view<iota_view<int>>`；`iota(0, 100) | take(10)` 得到的是 `iota_view<int, int>`。

```cpp run ok
#include <ranges>
int main() {
  auto a = std::views::iota(0) | std::views::take(10);
  auto b = std::views::iota(0, 100) | std::views::take(10);
  static_assert(std::same_as<decltype(a),
      std::ranges::take_view<std::ranges::iota_view<int, std::unreachable_sentinel_t>>>);
  static_assert(std::same_as<decltype(b), std::ranges::iota_view<int, int>>);
}
```

## 常见误解

!!! pitfall "无界 iota 加 filter 会停下来"
    `views::iota(0) | views::filter(p)` 是无限序列。如果谓词在某个点之后永远不再为真，求下一个元素时会一直找下去。例如 `iota(0) | filter([](int x) { return x < 10; }) | take(20)` 在找第 11 个元素时进入无限循环，最终有符号溢出，行为未定义{{ub}}。想表达到某处为止，应当用 `views::take_while`。

## 思考题

!!! question "思考题"
    `views::iota(0, 10u)` 能编译吗？`views::iota(0L, 10)` 呢？

<details markdown="1">
<summary>答案</summary>

前者不能：`int` 是有符号的，`unsigned int` 是无符号的，推导指引的约束不满足。后者能：`long` 和 `int` 都是有符号的，推导出 `iota_view<long, int>`。两者类型不同，所以 `end()` 返回哨位而不是迭代器，视图不是首尾同型的；`size()` 仍然存在，因为两者都是整数类型。
</details>
