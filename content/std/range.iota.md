---
title: iota 视图与 views::indices
summary: iota_view<W, Bound> 通过反复 ++ 生成序列——有界/无界、W 可以是整数也可以是迭代器；IOTA-DIFF-T 为何要选"更宽的有符号类型"、decrementable/advanceable 两个说明用概念、推导指引拒绝混合符号、前置条件"bound 从 value 可达"、size() 的防溢出写法，以及 C++26 的 views::indices。
status: done
covers: *
since: c++20
papers: P0896R4
related: range.factories, range.take, range.drop, iterator.concept.winc, iterator.concepts, unreachable.sentinel, range.enumerate
tags: 标准库, 范围, iota, 工厂
updated: 2026-10-18
---

`views::iota(a, b)` 是 Ranges 版的"`for (i = a; i != b; ++i)`"。它看起来简单，规范却是本章最精细的部分之一：要给 `int` 的序列一个**不会溢出的距离类型**，要让 `W` 可以是任何"能 `++` 的东西"（包括迭代器），还要防止 `iota(0, v.size())` 这种有符号/无符号混用的隐蔽 bug。

## 概览（[range.iota.overview]）

¶1 `iota_view` 通过反复递增一个初始值生成元素序列。¶2 `views::iota(E)` 与 `views::iota(E, F)` 分别表达式等价于 `iota_view<decay_t<decltype((E))>>(E)` 与 `iota_view(E, F)`（后者走类模板实参推导）。

¶4 {{c++26}} `views::indices(E)`：令 `T` 为 `remove_cvref_t<decltype((E))>`，若 *is-integer-like*`<T>` 则表达式等价于 `views::iota(T(0), E)`，否则非良构。它专门解决"从 0 数到 `v.size()`"时的类型匹配问题。

## 类模板（[range.iota.view]）

```cpp
template<weakly_incrementable W, semiregular Bound = unreachable_sentinel_t>
  requires weakly-equality-comparable-with<W, Bound> && copyable<W>
class iota_view : public view_interface<iota_view<W, Bound>> {
  W value_ = W();
  Bound bound_ = Bound();
  // ...
};

template<class W, class Bound>
  requires (!is-integer-like<W> || !is-integer-like<Bound> ||
            (is-signed-integer-like<W> == is-signed-integer-like<Bound>))
  iota_view(W, Bound) -> iota_view<W, Bound>;
```

- `Bound` 默认 `unreachable_sentinel_t`：**无限序列**（[[unreachable.sentinel]]）；
- `W` 只要 `weakly_incrementable` 且可复制——整数、指针、**任何迭代器**都行：`views::iota(v.begin(), v.end())` 产生的元素是迭代器本身；
- **推导指引**：两个都是整数类类型时，要求符号性相同。`views::iota(0, v.size())`（`int` 与 `size_t`）因此**无法推导**而编译失败——这是有意为之：混合符号时 `value_ == bound_` 的比较会经过算术转换，很容易得到"永远不相等"的无限循环。

```cpp run error
#include <ranges>
#include <vector>
int main() {
  std::vector<int> v{1, 2, 3};
  for (auto i : std::views::iota(0, v.size())) (void)i;   // error: int 与 size_t 符号不同
}
```

修复：`views::iota(0uz, v.size())`、`views::iota(std::size_t{0}, v.size())`，或 C++26 的 `views::indices(v.size())`。

### *IOTA-DIFF-T*：距离类型（¶1）

`iota_view<int, int>` 的两个迭代器之差应该是什么类型？`int` 不够：`iota(INT_MIN, INT_MAX)` 的长度超过 `INT_MAX`。¶1 规定 *IOTA-DIFF-T*(W)：

- ¶1.1 若 `W` 不是整数类型，或者 `iter_difference_t<W>` 比 `W` 宽：用 `iter_difference_t<W>`；
- ¶1.2 否则，若存在比 `W` **更宽的有符号整数类型**：用它；
- ¶1.3 否则：一个**未指明的有符号整数类**（signed-integer-like）类型，宽度不小于 `W`（[[iterator.concept.winc]]）。注 1：它是否满足 `weakly_incrementable` 是未指明的。

所以 `iota_view<int,int>` 的 `difference_type` 是某个更宽的标准类型，而 `iota_view<long long, long long>` 在没有更宽标准整数的平台上要用实现定义的整数类类型——libc++ 在本站环境中用的是 `__int128`。

### 两个说明用概念（¶2–¶5）

- ***decrementable***：`incrementable` 加上 `--i`（返回 `I&`）与 `i--`（返回 `I`），¶4 的语义要求保证 `++` 与 `--` 互逆；
- ***advanceable***：*decrementable* + `totally_ordered` + 能以 *IOTA-DIFF-T* 做 `+=`、`-=`、`+`、`-`，以及 `j - j`。¶5 后面一长串语义公理（`(a += n) == b`、`I(a + D(x + y)) == I(I(a + x) + y)`……）本质上说"加法与重复 `++` 一致"。

它们决定了迭代器的强度（[range.iota.iterator] ¶1）：

| `W` 建模 | `iterator_concept` |
|---|---|
| *advanceable* | `random_access_iterator_tag` |
| *decrementable* | `bidirectional_iterator_tag` |
| `incrementable` | `forward_iterator_tag` |
| 其他 | `input_iterator_tag` |

而 `iterator_category`（C++17 视角）**最多是 `input_iterator_tag`**，且只在 `W` 建模 `incrementable` 且距离类型是整数类型时才声明。原因是 `operator*` 按值返回 `W`，而 *Cpp17ForwardIterator* 要求 `reference` 是真引用。于是把 `iota` 的迭代器交给 C++17 算法时，它们只会按输入迭代器处理。

### 构造与前置条件（¶6–¶11）

- ¶6/¶8：`Bound` 是 `unreachable_sentinel_t`，或 `bound` 从 `value` **可达**（反复 `++` 能到达）；若 `W` 与 `Bound` 建模 `totally_ordered_with`，还要求 `value <= bound`。`views::iota(5, 0)` 违反前置条件——{{ub}}，而**不是**空范围。
- ¶10–¶11：可以从一对 `iota_view` 迭代器（或迭代器 + 哨位）构造，这让 `subrange` 式的切片能保持 `iota_view` 类型。

### `begin`/`end`/`size`（¶12–¶17）

`end()` 在 `W` 与 `Bound` 同类型时返回**迭代器**（common range），否则返回 *sentinel* 或 `unreachable_sentinel`。`empty()` 即 `value_ == bound_`。

`size()` 的写法（¶16）值得细看：

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

它在无符号域内分情况计算，避免了 `bound_ - value_` 在有符号域里溢出（例如 `iota(INT_MIN, INT_MAX)`）。¶17 约束：`(same_as<W, Bound> && advanceable<W>) || (两者都是整数类) || sized_sentinel_for<Bound, W>`。

## 迭代器与哨位（[range.iota.iterator]、[range.iota.sentinel]）

迭代器只存一个 `W value_`，`operator*` 返回 `value_` 的副本（按值！），`operator[](n)` 返回 `W(value_ + n)`。¶2 注 1：**有意不提供** `iter_move`/`iter_swap` 重载——元素是 prvalue，默认行为就对。¶5 注 2：`operator*` 的 `noexcept` 规范是为默认的 `iter_move` 服务的。

因为迭代器自带值，与 `iota_view` 对象无关，`iota_view` 是**借用范围**（[[ranges.syn]]）。

哨位存 `Bound bound_`，与迭代器比较 `x.value_ == y.bound_`；若 `Bound` 与 `W` 可求差则提供 `operator-`。

```cpp run ok
#include <ranges>
#include <vector>
#include <list>
#include <cstdio>
#include <type_traits>
int main() {
  using I = std::ranges::iota_view<int, int>;
  static_assert(sizeof(std::ranges::range_difference_t<I>) > sizeof(int));     // 比 int 更宽（本环境为 long）
  using L = std::ranges::iota_view<long long, long long>;
  using DL = std::ranges::range_difference_t<L>;
  static_assert(sizeof(DL) > sizeof(long long));  // libc++ 在本环境用 __int128
  static_assert(std::ranges::random_access_range<I> && std::ranges::sized_range<I>);
  static_assert(std::same_as<std::iterator_traits<std::ranges::iterator_t<I>>::iterator_category,
                             std::input_iterator_tag>);   // C++17 视角下只是输入迭代器
  std::vector<int> v{1, 2, 3};
  for (auto i : std::views::iota(0uz, v.size())) std::printf("%zu", i);   // 0uz：同为无符号
  std::list<int> l{7, 8};
  for (auto it : std::views::iota(l.begin(), l.end())) std::printf(" %d", *it);  // 元素是迭代器
  std::puts("");   // 012 7 8
}
```

```cpp run ok
#include <ranges>
#include <vector>
#include <cstdio>
int main() {
  std::vector<int> v{10, 20, 30};
  for (auto i : std::views::indices(v.size())) std::printf("%zu:%d ", i, v[i]);  // C++26
  std::puts("");
}
```

## 与 take/drop 的联动

`views::take(iota_view, n)` 在 `iota_view` 是 random access + sized 时，结果仍是 `iota_view`（[[range.take]] ¶2.4）；`views::drop` 同理（[[range.drop]]）。所以 `views::iota(0) | views::take(10)`……注意：无界 `iota(0)` **不是 sized**，这里得到的是 `take_view<iota_view<int>>`；而 `iota(0, 100) | take(10)` 得到 `iota_view<int, int>`。

## 常见误区

!!! pitfall "以为 `iota(5, 0)` 是空范围"
    它违反 ¶8 的前置条件 `value <= bound`。即使实现恰好让它表现为某种行为，也是未定义的。若上下界来自运行时，先 `std::min`/`std::max` 规范化。

!!! pitfall "无界 iota 与 filter"
    `views::iota(0) | views::filter(p)` 是无限序列；如果后面没有 `take` 之类的截断，或者谓词永远不再为真，`begin()`/`++` 会永远找下去。比如 `iota(0) | filter([](int x){ return x < 10; }) | take(20)` 在找第 11 个元素时进入无限循环（并最终有符号溢出，{{ub}}）。这时应使用 `take_while`。

## 小结

- `iota(a)` 无界，`iota(a, b)` 有界，`W` 可以是整数或迭代器；
- 混合符号的整数上下界在推导阶段被拒绝；`indices(n)` 是 C++26 的简洁写法；
- 距离类型选更宽的有符号类型，必要时用整数类类型；`size()` 在无符号域内防溢出计算；
- 迭代器强度由 *advanceable*/*decrementable* 决定，C++17 类别永远是 input；`iota_view` 是借用范围。
