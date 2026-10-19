---
title: 子范围 subrange
summary: subrange 把一个迭代器和一个哨位打包成借用的视图：怎样构造、何时额外存储大小、怎样禁止派生类到基类的切片转换，以及与 pair 的互转、结构化绑定和 next/prev/advance。
status: done
covers: *
since: c++20
papers: P0896R4
related: range.utility, range.dangling, range.view, range.req, range.counted, iterator.concepts, range.iter.ops, tuple.like, dcl.struct.bind
tags: 标准库, 范围, subrange, 借用范围
updated: 2026-10-19
---

!!! tldr
    - `subrange<I, S, K>` 把迭代器 `I` 和哨位 `S` 组合成一个视图，它总是借用范围。
    - 迭代器和哨位不能相减时（如 `list`），可以在构造时给出元素个数，`subrange` 把它存下来，于是 `size()` 仍是 O(1)。这个个数是前置条件，库不检查。
    - 从 `Derived*` 构造 `subrange<Base*>` 是非良构的，标准专门挡住了这种会按错误步长遍历数组的转换。
    - `subrange` 可以转换成 `std::pair` 一类的 pair-like 类型，也可以用结构化绑定拆开。
    - `advance(n)` 前进时以 `end` 为界，不会越过末尾。

## 一对迭代器变成一个对象

```cpp run ok
#include <ranges>
#include <map>
#include <cstdio>
int main() {
  std::multimap<int, char> m{{1, 'a'}, {1, 'b'}, {2, 'c'}};
  auto [lo, hi] = m.equal_range(1);       // 老接口：一对迭代器
  std::ranges::subrange eq(lo, hi);        // 变成一个范围
  for (auto& [k, c] : eq) std::printf("%c ", c);
  std::printf("%td\n", std::ranges::distance(eq));   // a b 2
}
```

C++98 的接口用一对迭代器表示范围，ranges 库的算法和适配器则接受一个范围对象。`subrange` 把 `[i, s)` 打包成一个对象，让两者可以互通。反方向也常见：`ranges::equal_range`、`ranges::search` 等算法的返回值就是 `subrange`，`views::counted` 和 `views::split` 也产生 `subrange`。

¶1 `subrange` 建模 `view`（[[range.view]]），最后一个模板实参为 `subrange_kind::sized` 时还建模 `sized_range`。它的概要大致如下：

```cpp
template<input_or_output_iterator I, sentinel_for<I> S = I,
         subrange_kind K = sized_sentinel_for<S, I>
                             ? subrange_kind::sized : subrange_kind::unsized>
  requires (K == subrange_kind::sized || !sized_sentinel_for<S, I>)
class subrange : public view_interface<subrange<I, S, K>> {
  static constexpr bool StoreSize =
    K == subrange_kind::sized && !sized_sentinel_for<S, I>;
  I begin_ = I();
  S end_ = S();
  make-unsigned-like-t<iter_difference_t<I>> size_ = 0;  // 仅当 StoreSize 为真时存在
  // ...
};
```

[[ranges.syn]] 把 `enable_borrowed_range<subrange<I, S, K>>` 特化为 `true`。`subrange` 只是借用别人的迭代器，它的迭代器在 `subrange` 对象销毁后仍然有效，所以 `ranges::find(ranges::subrange{vec}, 42)` 返回真正的迭代器，而不是 `dangling`（[[range.dangling]]）。

## 什么时候存储大小

`subrange_kind` 有两个值，`sized` 和 `unsized`，决定 `subrange` 是否提供 `size()`：

- 如果 `S - I` 可以在常数时间内算出（`sized_sentinel_for<S, I>`，例如 `vector` 的迭代器），`K` 默认为 `sized`，`size()` 随时用 `end_ - begin_` 算出，不需要存；
- 否则 `K` 默认为 `unsized`。这时可以显式指定 `sized`，并在构造时给出个数 `n`。*StoreSize* 为真，`subrange` 多存一个整数，对 `list` 迭代器这样的范围也能 O(1) 回答 `size()`（[range.subrange.ctor] ¶5 的注 1）；
- `requires` 子句禁止能相减却声明为 `unsized` 的组合。

```cpp run ok
#include <ranges>
#include <list>
#include <vector>
#include <cstdio>
int main() {
  std::vector<int> v{1, 2, 3, 4, 5};
  std::ranges::subrange sr(v.begin() + 1, v.end() - 1);    // 2 3 4
  static_assert(std::ranges::sized_range<decltype(sr)>);    // 迭代器可相减

  std::list<int> l{1, 2, 3};
  std::ranges::subrange ls(l.begin(), l.end());
  static_assert(!std::ranges::sized_range<decltype(ls)>);   // 不可相减
  std::ranges::subrange ls2(l.begin(), l.end(), l.size());  // 给出个数，存下来
  static_assert(std::ranges::sized_range<decltype(ls2)>);

  auto [b, e] = sr;                                          // 结构化绑定
  std::printf("%td %zu %zu\n", e - b, sr.next().size(), ls2.size());   // 3 2 3
}
```

## 构造与推导 [range.subrange.ctor]

¶1–¶2 `subrange(i, s)` 要求 *StoreSize* 为假，前置条件是 `[i, s)` 是有效范围。

¶3–¶4 `subrange(i, s, n)` 要求 `K` 为 `sized`。前置条件还要求 `n` 等于 `ranges::distance(i, s)`。库不会验证这个值，给错 `n` 就是违反前置条件，之后 `size()` 的结果没有保证。

¶6 `subrange(r)` 从一个借用范围构造。*StoreSize* 为真时，它等价于 `subrange(r, ranges::size(r))`，所以此时要求 `sized_range<R>`；否则等价于 `subrange(ranges::begin(r), ranges::end(r))`。

推导指引的结果如下：

| 写法 | 推导结果 |
|---|---|
| `subrange(i, s)` | `subrange<I, S>`，`K` 按默认规则 |
| `subrange(i, s, n)` | `subrange<I, S, sized>` |
| `subrange(r)` | `r` 是 `sized_range` 或迭代器可相减时为 `sized`，否则 `unsized` |
| `subrange(r, n)` | `sized` |

从范围构造的两种写法都要求 `r` 是借用范围（[[range.range]]）。`subrange{std::vector<int>{}}` 是非良构的，否则就会得到一个指向已销毁临时量的视图。

### 禁止切片

```cpp run error
#include <ranges>
struct Base { int x; };
struct Derived : Base { int y; };
Derived arr[3];
std::ranges::subrange<Base*> s(arr, arr + 3);   // error: Derived* 到 Base* 会切片
int main() {}
```

`Derived*` 可以隐式转换为 `Base*`，但用 `Base*` 遍历 `Derived` 数组时，每次 `++` 只前进 `sizeof(Base)` 字节，从第二步起指向的就不再是一个 `Base` 对象，行为未定义{{ub}}（[[expr.add]]）。所以构造函数的迭代器形参用下面的概念约束：

```cpp
template<class From, class To>
  concept uses-nonqualification-pointer-conversion =
    is_pointer_v<From> && is_pointer_v<To> &&
    !convertible_to<remove_pointer_t<From>(*)[], remove_pointer_t<To>(*)[]>;
template<class From, class To>
  concept convertible-to-non-slicing =
    convertible_to<From, To> &&
    !uses-nonqualification-pointer-conversion<decay_t<From>, decay_t<To>>;
```

判断的方法是借用指向数组的指针：`Derived(*)[]` 不能转换为 `Base(*)[]`，而 `int(*)[]` 可以转换为 `const int(*)[]`，因为后者只增加了 cv 限定。于是 `subrange<const int*>` 可以从 `int*` 构造，`subrange<Base*>` 不能从 `Derived*` 构造。

### 转换为 pair-like

¶7 `subrange` 可以转换为任何 pair-like 类型（`std::pair`、两个元素的 `std::tuple` 等，见 [[tuple.like]]），条件是目标类型不是范围、不是引用、能从 `const I&, const S&` 构造，并且第一个元素的转换不切片。这样 `subrange` 可以直接交给仍然接受 `std::pair<It, It>` 的旧代码：

```cpp run ok
#include <ranges>
#include <utility>
#include <vector>
int main() {
  std::vector<int> v{1, 2, 3};
  std::ranges::subrange sr(v);
  using It = std::vector<int>::iterator;
  std::pair<It, It> p = sr;
  return p.first == v.begin() ? 0 : 1;
}
```

## 访问器 [range.subrange.access]

¶1–¶2 `begin() const` 在 `I` 可复制时返回 `begin_` 的副本。`I` 只能移动时（某些输入迭代器），只有非 const 的 `begin()`，它返回 `std::move(begin_)`，所以只能调用一次，`subrange` 也不能在 const 下迭代。

¶3 `end()` 返回 `end_` 的副本。¶4 `empty()` 返回 `begin_ == end_`。¶5 `size()` 在 *StoreSize* 为真时返回存储的值，否则返回 `end_ - begin_` 转成的无符号数。

¶6–¶8 `next(n)` 和 `prev(n)` 返回前进或后退 `n` 步后的副本。`next` 还有一个右值版本 `next(n) &&`，它就地推进再把自己移出，可以用于只能移动的迭代器。

¶9 `advance(n)` 的行为分两种情况：

- 迭代器是双向的且 `n < 0` 时，`begin_` 后退 `-n` 步，存储的大小相应增加；
- 否则用 `ranges::advance(begin_, n, end_)` 前进，以 `end_` 为界，不会越过末尾，存储的大小按实际前进的步数减少。

¶10 `get<0>` 返回 `begin()`，`get<1>` 返回 `end()`。配合 [[ranges.syn]] 中 `tuple_size` 和 `tuple_element` 的特化，`auto [b, e] = sr;` 这样的结构化绑定可以使用（[[dcl.struct.bind]]）。对 const 左值调用 `get<0>` 要求 `I` 可复制。

## 常见误解

!!! pitfall "借用范围就不会悬垂"
    借用只表示迭代器的有效性不依赖 `subrange` 对象本身的生命周期。如果 `subrange` 借的是一个临时 `vector` 的迭代器，`vector` 销毁后照样悬垂。`subrange(r)` 要求 `r` 是借用范围，挡住的只是从临时容器直接构造这一种最常见的情况；`subrange(tmp.begin(), tmp.end())` 这样从迭代器构造，类型系统检查不出来。
