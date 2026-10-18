---
title: 子范围 subrange
summary: subrange<I, S, K> 把一对迭代器/哨位打包成借用视图；subrange_kind 与"存储大小"的 StoreSize 优化、禁止切片的 convertible-to-non-slicing、与 pair-like 的互转和结构化绑定、next/prev/advance 的语义，以及 const begin 只在迭代器可复制时存在。
status: done
covers: *
since: c++20
papers: P0896R4
related: range.utility, range.dangling, range.view, range.req, range.counted, iterator.concepts, range.iter.ops, tuple.like, dcl.struct.bind
tags: 标准库, 范围, subrange, 借用范围
updated: 2026-10-18
---

C++98 用一对迭代器表示范围；C++20 想让一切都变成"一个对象"。`subrange` 就是两者之间的桥：把 `[i, s)` 打包成一个**借用的视图**，从而能交给 ranges 算法、放进管道、从函数返回。很多 ranges 算法本身也返回 `subrange`（如 `ranges::equal_range`、`ranges::search`），而 `views::counted`、`views::split` 的元素也是 `subrange`。

## 类模板概要（[range.subrange.general]）

¶1 `subrange` 把一个迭代器与一个哨位组合成一个建模 `view` 的对象；当最后一个模板实参为 `subrange_kind::sized` 时它还建模 `sized_range`。

```cpp
template<input_or_output_iterator I, sentinel_for<I> S = I, subrange_kind K =
    sized_sentinel_for<S, I> ? subrange_kind::sized : subrange_kind::unsized>
  requires (K == subrange_kind::sized || !sized_sentinel_for<S, I>)
class subrange : public view_interface<subrange<I, S, K>> {
  static constexpr bool StoreSize = K == subrange_kind::sized && !sized_sentinel_for<S, I>;
  I begin_ = I();
  S end_ = S();
  make-unsigned-like-t<iter_difference_t<I>> size_ = 0;   // 仅当 StoreSize 时存在
  // ...
};
```

### `subrange_kind` 与 *StoreSize*

- 若 `S - I` 能 O(1) 求差（`sized_sentinel_for`），`K` 默认就是 `sized`，大小随时算出，不需要存；
- 否则 `K` 默认 `unsized`。但你可以**显式**指定 `sized`，并在构造时给出大小 `n`——此时 *StoreSize* 为真，`subrange` 多存一个整数，从而对 `list` 迭代器这样的范围也能 O(1) 回答 `size()`（¶5 注 1）；
- `requires` 子句禁止"能算却声明为 unsized"：`K == sized || !sized_sentinel_for<S, I>`。

### 禁止切片：*convertible-to-non-slicing*

```cpp
template<class From, class To>
  concept uses-nonqualification-pointer-conversion =
    is_pointer_v<From> && is_pointer_v<To> &&
    !convertible_to<remove_pointer_t<From>(*)[], remove_pointer_t<To>(*)[]>;
template<class From, class To>
  concept convertible-to-non-slicing =
    convertible_to<From, To> && !uses-nonqualification-pointer-conversion<decay_t<From>, decay_t<To>>;
```

`Derived*` 可以隐式转换为 `Base*`，但用 `Base*` 遍历一个 `Derived` 数组会按错误的步长前进（[[expr.add]] 下是{{ub}}）。技巧在于"指向数组的指针"：`Derived(*)[]` → `Base(*)[]` 不可转换，而 `int(*)[]` → `const int(*)[]` 可以（仅限定转换）。于是 `subrange<const int*>` 能从 `int*` 构造，`subrange<Base*>` 却不能从 `Derived*` 构造：

```cpp run error
#include <ranges>
struct Base { int x; };
struct Derived : Base { int y; };
Derived arr[3];
std::ranges::subrange<Base*> s(arr, arr + 3);   // error: Derived* → Base* 会切片
int main() {}
```

### 推导指引

- `subrange(i, s)` → `subrange<I, S>`（`K` 按默认规则）；
- `subrange(i, s, n)` → `subrange<I, S, sized>`；
- `subrange(r)`（`r` 必须是 `borrowed_range`）→ 若 `sized_range<R>` 或可求差则 `sized`；
- `subrange(r, n)` → `sized`。

注意 `subrange(r)` 要求 **`borrowed_range`**：`subrange{std::vector<int>{}}` 非良构——否则就得到一个指向临时量的视图。

## 构造与转换（[range.subrange.ctor]）

- ¶1–¶2 `subrange(i, s)`（要求 `!StoreSize`）：前置条件 `[i, s)` 是有效范围。
- ¶3–¶4 `subrange(i, s, n)`：前置条件还要求 `n == to-unsigned-like(ranges::distance(i, s))`。**给错 `n` 是违反前置条件**，之后 `size()` 的结果没有保证——标准库不会去验证它。
- ¶6 `subrange(R&& r)`：若 *StoreSize* 则等价于 `subrange(r, ranges::size(r))`，否则 `subrange(ranges::begin(r), ranges::end(r))`。约束 `!StoreSize || sized_range<R>`：要存大小，就必须能拿到大小。
- ¶7 `operator PairLike() const`：转换为任何 *pair-like* 类型（`pair`、`tuple<I,S>`……），只要它不是范围、能从 `const I&, const S&` 构造且第一个元素无切片。这使得 `subrange` 能直接赋给旧代码里的 `std::pair<It, It>`。

```cpp run ok
#include <ranges>
#include <utility>
#include <vector>
#include <map>
int main() {
  std::vector<int> v{1, 2, 3};
  std::ranges::subrange sr(v);
  std::pair<std::vector<int>::iterator, std::vector<int>::iterator> p = sr;  // 转为 pair-like
  std::multimap<int, char> m{{1, 'a'}, {1, 'b'}, {2, 'c'}};
  auto [lo, hi] = m.equal_range(1);
  std::ranges::subrange eq(lo, hi);                          // 把老接口的 pair 变成范围
  return (p.first == v.begin() && std::ranges::distance(eq) == 2) ? 0 : 1;
}
```

## 访问器（[range.subrange.access]）

- ¶1–¶2 `begin() const`（要求 `copyable<I>`）返回副本；`begin()`（要求 `!copyable<I>`）返回 `std::move(begin_)`。对**只移动的迭代器**（如某些输入迭代器），`begin()` 只能调用一次，而且 `subrange` 此时不是 const 可迭代的。
- ¶3 `end() const` 返回 `end_` 的副本。
- ¶4 `empty()` 即 `begin_ == end_`；¶5 `size()` 在 *StoreSize* 时返回存的值，否则 `to-unsigned-like(end_ - begin_)`。
- ¶6–¶8 `next(n)`/`prev(n)` 返回前进/后退后的**副本**；`next() &&` 的右值重载就地推进再移出，可用于只移动迭代器。
- ¶9 `advance(n)`：对双向迭代器且 `n < 0` 时向后退（并相应增加存储的大小）；否则用 `ranges::advance(begin_, n, end_)` **以 `end_` 为界**前进，不会越过末尾，并按实际前进的距离减少存储的大小。
- ¶10 `get<0>`/`get<1>`：配合 [[ranges.syn]] 中 `tuple_size`/`tuple_element` 的特化，使 `auto [b, e] = sr;` 结构化绑定可用（[[dcl.struct.bind]]）。`get<0>` 对 const 左值要求 `copyable<I>`。

```cpp run ok
#include <ranges>
#include <list>
#include <vector>
#include <cstdio>
int main() {
  std::vector<int> v{1, 2, 3, 4, 5};
  std::ranges::subrange sr(v.begin() + 1, v.end() - 1);    // [2,3,4]
  auto [b, e] = sr;                                         // 元组式解构
  static_assert(std::ranges::sized_range<decltype(sr)>);
  std::list<int> l{1, 2, 3};
  std::ranges::subrange ls(l.begin(), l.end());             // 迭代器不支持减法
  static_assert(!std::ranges::sized_range<decltype(ls)>);
  std::ranges::subrange ls2(l.begin(), l.end(), l.size());  // 显式给出大小：存下来
  static_assert(std::ranges::sized_range<decltype(ls2)>);
  std::printf("%td %zu %zu\n", e - b, sr.next().size(), ls2.size());   // 3 2 3
}
```

## 借用性

[[ranges.syn]] 中 `enable_borrowed_range<subrange<I, S, K>>` 恒为 `true`（[[range.range#7]] 的例 1）——`subrange` 只是"借"别人的迭代器。因此 `ranges::find(ranges::subrange{vec}, 42)` 返回真正的迭代器（[[range.dangling]] 的例 1 #3）。

!!! pitfall "借用不等于安全"
    `subrange` 的借用性只说"迭代器的有效性不依赖 **subrange 对象**的生命周期"。如果它借的是一个临时 `vector` 的迭代器（例如 `subrange(make_vec().begin(), make_vec().end())`——还是两个不同的临时量！），照样悬垂。`subrange(r)` 的构造函数要求 `borrowed_range<R>`，就是为了在类型层面挡住最常见的那种情况。

## 小结

- `subrange<I, S, K>` = 迭代器 + 哨位 (+ 可选的存储大小)，是借用的视图；
- `sized` 而不能求差时才存大小；构造时提供的大小是**前置条件**，不被检查；
- *convertible-to-non-slicing* 挡住派生类指针到基类指针的危险转换；
- 能转换为 pair-like，也能结构化绑定；`advance` 以 `end` 为界。
