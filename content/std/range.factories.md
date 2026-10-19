---
title: 范围工厂：empty、single、repeat、istream
summary: 不需要底层范围就能创建视图的工厂：永远为空的 empty_view、自带一个元素的 single_view、重复同一个值的 repeat_view，以及从输入流读取元素的 basic_istream_view。iota 见专页。
status: done
covers: range.factories.general, range.empty, range.empty.overview, range.empty.view, range.single, range.single.overview, range.single.view, range.repeat, range.repeat.overview, range.repeat.view, range.repeat.iterator, range.istream, range.istream.overview, range.istream.view, range.istream.iterator
since: c++20
papers: P0896R4, P2474R2
related: range.iota, range.adaptors, range.move.wrap, range.view, range.take, range.drop, iterator.concepts, input.streams, unreachable.sentinel, default.sentinel
tags: 标准库, 范围, 工厂, repeat, istream
updated: 2026-10-19
---

!!! tldr
    - 范围工厂不接受底层范围，直接创建视图，是管道的起点。它们都在 `std::ranges::views` 中。
    - `views::empty<T>` 没有元素，迭代器是空的 `T*`，常在泛型代码中充当零。
    - `views::single(x)` 保存 `x` 的一份副本，修改视图里的元素不影响原对象。
    - `views::repeat(x)` 无限重复同一个对象，`views::repeat(x, n)` 重复 `n` 次；迭代器是随机访问的，所有元素是同一个对象。
    - `views::istream<T>(s)` 从流中读取元素，`begin()` 本身就会读走一个值，只能遍历一次。

```cpp run ok
#include <ranges>
#include <string>
#include <cstdio>
int main() {
  static_assert(std::ranges::empty(std::views::empty<int>));

  std::string s = "hi";
  auto one = std::views::single(s);            // 复制一份 s
  one.front() += "!";
  std::printf("%s %s\n", s.c_str(), one.front().c_str());   // hi hi!

  auto rp = std::views::repeat(std::string("ab"), 3);
  for (auto& x : rp) std::printf("%s", x.c_str());           // ababab
  std::printf(" %d\n", &rp[0] == &rp[2]);     // 1：所有元素是同一个对象
}
```

[range.factories] ¶1 定义了**范围工厂**（range factory，[[g:range-factory]]）：用来创建视图的工具。¶2 它们声明在 `std::ranges::views` 中。范围适配器（[[range.adaptors]]）接受一个底层范围再产生视图，工厂则不需要底层范围。本页讲 `empty`、`single`、`repeat`、`istream`；最常用的 `iota` 和 `indices` 见 [[range.iota]]。

下文的 `views::single` 等名字都是定制点对象（customization point object）：一个函数对象，调用它等价于标准规定的那个表达式（[[customization.point.object]]）。

## empty_view [range.empty]

¶1 `empty_view<T>` 产生一个元素类型为 `T`、没有任何元素的视图：

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

它的迭代器是 `T*`，所以它是连续（contiguous）、有大小（sized）、首尾同型（common）的范围。[[ranges.syn]] 把它声明为借用范围。`views::empty<T>` 是一个变量模板，值为 `empty_view<T>{}`。

它的主要用途是在泛型代码中充当零。例如 `views::zip()` 不带实参时返回 `views::empty<tuple<>>`（[[range.zip]]）；对 `empty_view` 应用 `views::take`，得到的还是这个 `empty_view`（[[range.take]]）。

## single_view [range.single]

¶1 `single_view` 产生恰好包含一个指定值的视图。¶2 `views::single(E)` 等价于 `single_view<decay_t<decltype((E))>>(E)`，也就是按值复制或移动 `E`。

```cpp
template<move_constructible T> requires is_object_v<T>
class single_view : public view_interface<single_view<T>> {
  movable-box<T> value_;
public:
  constexpr explicit single_view(const T& t) requires copy_constructible<T>;
  constexpr explicit single_view(T&& t);
  template<class... Args> requires constructible_from<T, Args...>
    constexpr explicit single_view(in_place_t, Args&&... args);
  constexpr T* begin() noexcept;
  constexpr const T* begin() const noexcept;
  constexpr T* end() noexcept;               // data() + 1
  static constexpr size_t size() noexcept;   // 1
  // ...
};
```

`single_view` 拥有它的元素。它仍然是视图，因为复制它只复制一个元素，代价是常数（[[range.view]]）。几个性质由此而来：

- 修改视图里的元素不影响原对象，见本页开头的例子；
- `const single_view` 的 `begin()` 返回 `const T*`，const 会传到元素上，这和容器一样，而和 `span` 不同；
- 它不是借用范围，迭代器指向视图对象内部；
- 元素存放在 *movable-box* 中（[[range.move.wrap]]）。视图必须可以移动赋值，而 `T` 可能不能赋值（例如捕获了引用的 lambda），*movable-box* 给它补上赋值操作。

## repeat_view [range.repeat] {{c++23}}

¶1 `repeat_view` 反复产生同一个值。¶2 `views::repeat(E)` 和 `views::repeat(E, F)` 分别等价于 `repeat_view<decay_t<decltype((E))>>(E)` 和 `repeat_view(E, F)`。它由 [[P2474R2]] 引入。

```cpp
template<move_constructible T, semiregular Bound = unreachable_sentinel_t>
  requires (is_object_v<T> && same_as<T, remove_cv_t<T>> &&
            (integer-like-with-usable-difference-type<Bound> ||
             same_as<Bound, unreachable_sentinel_t>))
class repeat_view;
```

- 省略第二个实参时，`Bound` 是 `unreachable_sentinel_t`，`end()` 返回一个永远不相等的哨位（[[unreachable.sentinel]]），序列是无限的。给出次数时，视图有大小，首尾同型。
- 迭代器是随机访问的。它只保存指向那个值的指针和当前下标，`it + n` 只改下标。
- 所有元素是同一个对象，`*it` 返回 `const T&`。
- ¶1、¶3 前置条件是次数 `bound >= 0`。¶5 用 `piecewise_construct` 分段构造时，得到负的次数是{{ub}}。
- `views::take` 和 `views::drop` 对 `repeat_view` 有专门的处理（[[range.take]]、[[range.drop]]）：`views::repeat(x) | views::take(n)` 的结果仍是一个 `repeat_view`，而不是包了一层的 `take_view`。

```cpp run ok
#include <ranges>
#include <string>
int main() {
  auto rp = std::views::repeat(std::string("ab"), 3);
  static_assert(std::ranges::random_access_range<decltype(rp)>);
  static_assert(std::ranges::sized_range<decltype(rp)>);

  auto inf = std::views::repeat(0);
  static_assert(!std::ranges::sized_range<decltype(inf)>);
  auto five = inf | std::views::take(5);
  static_assert(std::same_as<decltype(five), std::ranges::repeat_view<int, long>>);
}
```

`take` 的结果类型中，次数类型是 `long`：无界 `repeat_view` 的差类型是 `ptrdiff_t`，在本机（macOS arm64）上它就是 `long`。

## basic_istream_view [range.istream]

¶1 `basic_istream_view` 建模 `input_range`，用 `operator>>` 从输入流中依次读取元素。¶2 对类型为 `U` 的表达式 `E`，如果 `U` 派生自 `basic_istream<typename U::char_type, typename U::traits_type>`，`views::istream<T>(E)` 等价于 `basic_istream_view<T, typename U::char_type, typename U::traits_type>(E)`，否则非良构。`istream_view<T>` 和 `wistream_view<T>` 是 `char` 和 `wchar_t` 版本的别名。

```cpp
template<movable Val, class CharT, class Traits = char_traits<CharT>>
  requires default_initializable<Val> && stream-extractable<Val, CharT, Traits>
class basic_istream_view
    : public view_interface<basic_istream_view<Val, CharT, Traits>> {
public:
  constexpr explicit basic_istream_view(basic_istream<CharT, Traits>& stream);
  constexpr auto begin() { *stream_ >> value_; return iterator{*this}; }
  constexpr default_sentinel_t end() const noexcept;
private:
  basic_istream<CharT, Traits>* stream_;
  Val value_ = Val();
};
```

关键在于 `begin()` 会读取：它先执行 `*stream_ >> value_`，再返回迭代器。[range.istream.iterator] 规定了迭代器的行为：¶4 `*it` 返回视图里 `value_` 的引用；¶2 `++it` 再读一个值；¶5 与 `default_sentinel` 比较时检查 `!*stream_`，流进入失败状态就结束。

```cpp run ok
#include <ranges>
#include <sstream>
#include <cstdio>
int main() {
  std::istringstream in{"1 2 3 4"};
  auto v = std::views::istream<int>(in);
  auto it = v.begin();   // begin() 已经读走了 1
  int x = 0;
  in >> x;               // 读到的是 2
  std::printf("%d %d\n", *it, x);   // 1 2
}
```

由此可以推出几点：

- 只能遍历一次。迭代器只能移动，不能复制，视图也没有 const 的 `begin()`；
- 调用 `begin()` 本身就消耗输入。这正是 [[range.range]] 只对前向迭代器要求 `begin` 保持相等性的原因，也是 `ranges::empty` 只对前向范围才退而比较 `begin() == end()` 的原因（[[range.prim.empty]]）；
- 当前元素存放在视图对象里，所以它不是借用范围，视图销毁后不能再解引用迭代器。

!!! pitfall "与 take_while 组合时多读一个"
    [[range.take.while]] 的标准例子展示了这一点：`views::istream<int>(input) | views::take_while(small)` 在发现 `5` 不满足谓词时，`5` 已经从流里读出来了，循环结束后再 `input >> i` 读到的是 `6`。惰性求值并不意味着不多读，判断终止条件本身就要取出一个元素。

## 小结

| 工厂 | 元素来源 | 迭代器类别 | 借用 |
|---|---|---|---|
| `views::empty<T>` | 无 | contiguous，sized，common | 是 |
| `views::single(x)` | 视图内的一份副本 | contiguous，sized，common | 否 |
| `views::repeat(x[, n])` | 视图内的一个对象，反复引用 | random access；有界时 sized、common | 否 |
| `views::istream<T>(s)` | 流，`begin()` 时开始读 | input，迭代器只能移动 | 否 |
| `views::iota`、`views::indices` | 递增的值 | 见 [[range.iota]] | 是 |
