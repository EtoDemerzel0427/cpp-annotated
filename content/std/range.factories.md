---
title: 范围工厂：empty、single、repeat、istream
summary: 凭空造出视图的工厂——empty_view（连续、借用、永远为空）、single_view（自带一个元素，靠 movable-box 存放）、repeat_view（同一对象重复 N 次或无限次，随机访问）、basic_istream_view（begin() 会读取、只能单趟）；各自的 CPO 定义与坑点。iota 另见专页。
status: done
covers: range.factories.general, range.empty, range.empty.overview, range.empty.view, range.single, range.single.overview, range.single.view, range.repeat, range.repeat.overview, range.repeat.view, range.repeat.iterator, range.istream, range.istream.overview, range.istream.view, range.istream.iterator
since: c++20
papers: P0896R4, P2474R2
related: range.iota, range.adaptors, range.move.wrap, range.view, range.take, range.drop, iterator.concepts, input.streams, unreachable.sentinel, default.sentinel
tags: 标准库, 范围, 工厂, repeat, istream
updated: 2026-10-18
---

[range.factories] ¶1：**范围工厂**（range factory，[[g:range-factory]]）是创建视图的工具；¶2 它们声明在 `std::ranges::views` 中。与适配器（[[range.adaptors]]）不同，工厂不接受底层范围——它们是管道的**源头**。本页讲 `empty`、`single`、`repeat`、`istream`；最常用的 `iota`/`indices` 篇幅较大，见 [[range.iota]]。

## `empty_view`（[range.empty]）

```cpp
template<class T> requires is_object_v<T>
class empty_view : public view_interface<empty_view<T>> {
public:
  static constexpr T* begin() noexcept { return nullptr; }
  static constexpr T* end() noexcept { return nullptr; }
  static constexpr T* data() noexcept { return nullptr; }
  static constexpr size_t size() noexcept { return 0; }
  static constexpr bool empty() noexcept { return true; }
};
```

¶1 产生某个特定类型的、没有元素的视图。迭代器是 `T*`，所以它是 **contiguous、sized、common** 的，而且是借用的（[[ranges.syn]] 中特化 `enable_borrowed_range` 为 `true`）。`views::empty<T>` 是一个变量模板，值为 `empty_view<T>{}`。

它的主要用途是**泛型代码中的"零"**：例如 `views::zip()` 不带实参时就返回 `views::empty<tuple<>>`（[[range.zip]]），`views::take(empty, n)` 直接返回空视图本身（[[range.take]]）。

## `single_view`（[range.single]）

¶1 产生恰好包含一个指定值的视图。¶2 `views::single(E)` 表达式等价于 `single_view<decay_t<decltype((E))>>(E)`。

```cpp
template<move_constructible T> requires is_object_v<T>
class single_view : public view_interface<single_view<T>> {
  movable-box<T> value_;
public:
  single_view() requires default_initializable<T> = default;
  constexpr explicit single_view(const T& t) requires copy_constructible<T>;
  constexpr explicit single_view(T&& t);
  template<class... Args> requires constructible_from<T, Args...>
    constexpr explicit single_view(in_place_t, Args&&... args);
  constexpr T* begin() noexcept;  constexpr const T* begin() const noexcept;
  constexpr T* end() noexcept;    constexpr const T* end() const noexcept;   // data() + 1
  static constexpr bool empty() noexcept;   // false
  static constexpr size_t size() noexcept;  // 1
  constexpr T* data() noexcept;   constexpr const T* data() const noexcept;
};
```

要点：

- **它拥有元素**：`views::single(s)` 复制 `s`。修改视图里的元素不影响原对象。它是视图，因为复制它只复制一个元素——O(1)。
- **深 const**：`const single_view` 的 `begin()` 返回 `const T*`，与容器一致，而不同于 `ref_view`/`span` 的浅 const。
- **不是借用的**：迭代器指向视图内部的元素。
- 存储使用 *movable-box*（[[range.move.wrap]]）：为了让元素类型 `T` 即使不可赋值（例如捕获了引用的 lambda）也能放进一个必须 `movable` 的视图。

## `repeat_view`（[range.repeat]）{{c++23}}

¶1 通过反复产生同一个值来生成序列。¶2 `views::repeat(E)` 与 `views::repeat(E, F)` 分别表达式等价于 `repeat_view<decay_t<decltype((E))>>(E)` 与 `repeat_view(E, F)`。来自 [[P2474R2]]。

```cpp
template<move_constructible T, semiregular Bound = unreachable_sentinel_t>
  requires (is_object_v<T> && same_as<T, remove_cv_t<T>> &&
            (integer-like-with-usable-difference-type<Bound> ||
             same_as<Bound, unreachable_sentinel_t>))
class repeat_view;
```

- 第二个参数省略时是**无限**序列（`end()` 返回 `unreachable_sentinel`，[[unreachable.sentinel]]）；给定次数时是 sized、common 的。
- 迭代器是 **random access**（`iterator_concept = random_access_iterator_tag`）：它只存"指向值的指针 + 当前下标"，`it + n` 只是改下标。
- 所有元素是**同一个对象**：`*it` 返回 `const T&`，指向视图里那唯一的值。
- ¶1/¶3 前置条件：`bound >= 0`。¶5 分段构造（`piecewise_construct`）版本若得到负的 `bound` 是{{ub}}。
- 与 `take`/`drop` 有专门的联动（[[range.take]]、[[range.drop]]）：`views::repeat(x) | views::take(n)` 的结果仍是一个 `repeat_view`，而不是 `take_view<repeat_view>`。

```cpp run ok
#include <ranges>
#include <string>
#include <cstdio>
int main() {
  static_assert(std::ranges::empty(std::views::empty<int>));
  static_assert(std::ranges::contiguous_range<std::ranges::empty_view<int>>);
  std::string s = "hi";
  auto one = std::views::single(s);           // 复制一份 s
  one.front() += "!";
  std::printf("%s %s\n", s.c_str(), one.front().c_str());   // hi hi!
  auto rp = std::views::repeat(std::string("ab"), 3);
  static_assert(std::ranges::random_access_range<decltype(rp)> && std::ranges::sized_range<decltype(rp)>);
  auto inf = std::views::repeat(0);
  static_assert(!std::ranges::sized_range<decltype(inf)>);
  for (auto& x : rp) std::printf("%s", x.c_str());           // ababab
  std::puts("");
  std::printf("%d\n", &rp[0] == &rp[2]);                     // 1：三个"元素"是同一个对象
}
```

## `basic_istream_view`（[range.istream]）

¶1 `basic_istream_view` 建模 `input_range`，从对应的输入流中读取（用 `operator>>`）相继的元素。¶2 对 `views::istream<T>(E)`：令 `U` 为 `remove_reference_t<decltype((E))>`，若 `U` 派生自某个 `basic_istream<typename U::char_type, typename U::traits_type>`，则表达式等价于 `basic_istream_view<T, typename U::char_type, typename U::traits_type>(E)`；否则非良构。`istream_view<T>`、`wistream_view<T>` 是 `char`/`wchar_t` 的别名。整个组件是 hosted 的。

```cpp
template<movable Val, class CharT, class Traits = char_traits<CharT>>
  requires default_initializable<Val> && stream-extractable<Val, CharT, Traits>
class basic_istream_view : public view_interface<basic_istream_view<Val, CharT, Traits>> {
public:
  constexpr explicit basic_istream_view(basic_istream<CharT, Traits>& stream);
  constexpr auto begin() { *stream_ >> value_; return iterator{*this}; }
  constexpr default_sentinel_t end() const noexcept;
private:
  basic_istream<CharT, Traits>* stream_;
  Val value_ = Val();
};
```

关键在于 **`begin()` 会读取**：它先执行 `*stream_ >> value_`，再返回迭代器。迭代器的 `operator*` 返回 `value_` 的引用（存在视图里），`++` 再读一个，与 `default_sentinel` 比较时检查 `!*stream_`（流失败即结束）。

后果：

- 只能单趟（input），迭代器只能移动（不可复制），没有 `const begin()`；
- 调用 `begin()` 本身就消耗输入——这正是 [[range.req]] 中 `range` 只对 forward 迭代器要求 `begin` 保持相等性、而 [[range.access]] 中 `ranges::empty` 的兜底只对 forward 迭代器使用 `begin() == end()` 的原因；
- 元素存储在视图对象里，所以视图不是借用的，也不能在视图销毁后解引用迭代器。

```cpp run ok
#include <ranges>
#include <sstream>
#include <cstdio>
int main() {
  std::istringstream in{"1 2 3 4"};
  auto v = std::views::istream<int>(in);
  auto it = v.begin();         // begin() 已经读走了 1
  int x = 0;
  in >> x;                     // 读到的是 2
  std::printf("%d %d\n", *it, x);   // 1 2
}
```

!!! pitfall "与 take_while 组合时多读一个"
    [[range.take]] 中 take_while 的标准示例展示了这一点：`views::istream<int>(input) | views::take_while(small)` 在判定 `5` 不满足谓词时，`5` 已经从流里读出来了；循环结束后再 `input >> i` 读到的是 `6`。惰性视图并不意味着"不多读"——判断终止条件本身就要消费元素。

## 小结

| 工厂 | 元素来源 | 类别 | 借用 | 备注 |
|---|---|---|---|---|
| `views::empty<T>` | 无 | contiguous, sized, common | ✓ | 泛型代码的"零" |
| `views::single(x)` | 视图内的一个副本 | contiguous, sized, common | ✗ | 深 const |
| `views::repeat(x[, n])` | 视图内的一个对象，重复引用 | random access；有界时 sized、common | ✗ | C++23 |
| `views::istream<T>(s)` | 流，`begin()` 时开始读 | input，只移动迭代器 | ✗ | hosted |
| `views::iota` / `indices` | 递增的值 | 见 [[range.iota]] | ✓ | |
