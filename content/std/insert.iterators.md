---
title: 插入迭代器
summary: back_insert_iterator、front_insert_iterator 和 insert_iterator 把对迭代器的写入变成 push_back、push_front 和 insert，让复制类算法以插入方式工作。
status: done
covers: *
since: c++98
related: predef.iterators, output.iterators, iterator.concept.output, sequence.reqmts, associative.reqmts, iterator.range
tags: 标准库, 迭代器, 适配器, 输出迭代器
updated: 2026-10-19
---

!!! tldr
    - 对插入迭代器赋值就是向容器插入元素：分别调用 `push_back`、`push_front`、`insert`；`*` 和 `++` 什么也不做，返回迭代器自身。
    - 插入迭代器只保存指向容器的指针，不拥有容器，容器必须比它活得长。
    - `insert_iterator` 每次插入后用 `insert` 的返回值更新位置并前进一格，所以连续插入保持原来的顺序；对 `std::set`，位置只是一个提示。
    - `front_inserter` 会把元素顺序反过来；`back_inserter` 不会预先 `reserve`。
    - C++20 起 `difference_type` 是 `ptrdiff_t`，插入迭代器因此建模 `output_iterator`，可以用于 `ranges::` 算法。

```cpp run title="inserters.cpp" ok
#include <algorithm>
#include <cassert>
#include <deque>
#include <iterator>
#include <list>
#include <set>
#include <vector>

// C++20 起插入迭代器建模 output_iterator，可以用于 ranges:: 算法
static_assert(std::output_iterator<std::back_insert_iterator<std::vector<int>>, int>);
static_assert(std::output_iterator<std::insert_iterator<std::set<int>>, int>);

int main() {
    std::vector<int> v{3, 1, 2};

    std::set<int> s;
    std::ranges::copy(v, std::inserter(s, s.end()));      // 位置只是提示
    assert((s == std::set{1, 2, 3}));

    std::deque<int> d;
    std::ranges::copy(v, std::front_inserter(d));         // 每次插到最前：顺序反转
    assert((d == std::deque{2, 1, 3}));

    std::list<int> l{10, 20};
    std::ranges::copy(v, std::inserter(l, std::next(l.begin())));
    assert((l == std::list{10, 3, 1, 2, 20}));            // 保持了原来的顺序

    std::vector<int> out;
    std::ranges::transform(v, std::back_inserter(out), [](int x) { return x * x; });
    assert((out == std::vector{9, 1, 4}));
}
```

## 插入模式 [insert.iterators.general]

¶1 对普通迭代器，下面的循环把 `[first, last)` 覆写到从 `result` 开始的范围：

```cpp
while (first != last) *result++ = *first++;
```

如果 `result` 是一个**插入迭代器**（[[g:insert-iterator]]），同样的代码会把元素插入容器。这样，库里所有复制类的算法都可以在插入模式下工作，目标容器不必预先 `resize`。

¶2 插入迭代器由一个容器构造，`insert_iterator` 还需要一个指明插入位置的迭代器。它满足输出迭代器的要求；`operator*` 返回插入迭代器自身；对它赋值会在它所指的位置之前插入值。可以把它想成一个停在容器里的光标。

| 类模板 | 赋值的效果 | 辅助函数 | 容器需要 |
|---|---|---|---|
| `back_insert_iterator<C>` | `container->push_back(value)` | `back_inserter(c)` | `push_back` |
| `front_insert_iterator<C>` | `container->push_front(value)` | `front_inserter(c)` | `push_front` |
| `insert_iterator<C>` | `iter = container->insert(iter, value); ++iter;` | `inserter(c, i)` | `insert(pos, value)` |

## `back_insert_iterator` 与 `front_insert_iterator` [back.insert.iterator] [front.insert.iterator]

```cpp
template<class Container>
class back_insert_iterator {
protected:
  Container* container;
public:
  using iterator_category = output_iterator_tag;
  using value_type        = void;
  using difference_type   = ptrdiff_t;
  using pointer           = void;
  using reference         = void;
  using container_type    = Container;

  constexpr explicit back_insert_iterator(Container& x);
  constexpr back_insert_iterator& operator=(const typename Container::value_type& value);
  constexpr back_insert_iterator& operator=(typename Container::value_type&& value);
  constexpr back_insert_iterator& operator*();
  constexpr back_insert_iterator& operator++();
  constexpr back_insert_iterator  operator++(int);
};
```

[back.insert.iter.ops] 的各段规定了这些成员：

- ¶1 构造函数用 `addressof(x)` 初始化 `container`。用 `addressof` 而不用 `&`，是为了防止容器类型重载了一元 `&`。迭代器里只有一个指针，复制很便宜，但它不拥有容器。
- ¶2–¶5 两个赋值运算符分别调用 `push_back(value)` 和 `push_back(std::move(value))`。参数类型是容器的 `value_type`，所以对 `vector<string>` 写 `*it = "abc"`，会先构造一个临时 `string` 再移动进去，而不是原地构造。
- ¶6–¶7 `operator*` 和两个 `operator++` 都只返回 `*this`。于是 `*it = v`、`*it++ = v`、`it = v` 效果完全相同。`*it` 得到的不是元素，这也是插入迭代器只能是输出迭代器的原因。

`difference_type` 在 C++20 之前是 `void`。改成 `ptrdiff_t` 之后，插入迭代器才建模 `weakly_incrementable`，进而建模 `output_iterator`，可以作为 `ranges::copy` 等算法的输出（[[iterator.concept.output]]）。所有成员也在 C++20 中成为 `constexpr`，可以在常量求值中配合 `constexpr` 的 `vector` 使用。

`front_insert_iterator` 与它完全平行，只是调用 `push_front`。`vector` 没有 `push_front`，所以对 `front_inserter(v)` 赋值会在实例化赋值运算符时编译失败，这倒是好事，因为在 `vector` 头部插入是线性时间。

`back_inserter(x)` 和 `front_inserter(x)` 分别返回 `back_insert_iterator<Container>(x)` 和 `front_insert_iterator<Container>(x)`。

## `insert_iterator` [insert.iterator]

```cpp
template<class Container>
class insert_iterator {
protected:
  Container* container;
  ranges::iterator_t<Container> iter;
public:
  // 成员类型同上
  constexpr insert_iterator(Container& x, ranges::iterator_t<Container> i);
  constexpr insert_iterator& operator=(const typename Container::value_type& value);
  constexpr insert_iterator& operator=(typename Container::value_type&& value);
  constexpr insert_iterator& operator*();
  constexpr insert_iterator& operator++();
  constexpr insert_iterator& operator++(int);
};
```

¶2 [insert.iter.ops] 规定赋值的效果如同：

```cpp
iter = container->insert(iter, value);
++iter;
```

两步都不能少：

1. 用 `insert` 的返回值更新 `iter`。插入可能让原来的 `iter` 失效，例如 `vector` 扩容；`insert` 返回的是指向新元素的有效迭代器。
2. 再 `++iter`，让下一次插入发生在刚插入的元素之后。所以连续赋值会保持原来的顺序：在 `{10, 20}` 的 `20` 之前依次插入 `3, 1, 2`，结果是 `{10, 3, 1, 2, 20}`。

对关联容器，`insert(hint, value)` 把 `iter` 当作提示，元素的最终位置由键决定，更新后的 `iter` 仍然是一个有效的提示。所以 `inserter(s, s.end())` 是把任意序列放进 `std::set` 的惯用写法。

成员 `iter` 和辅助函数 `inserter(Container& x, ranges::iterator_t<Container> i)` 的位置参数，类型都是 `ranges::iterator_t<Container>`，C++20 之前是 `typename Container::iterator`。

## 常见误解

!!! pitfall "`front_inserter` 保持顺序"
    每次 `push_front` 都插到最前面，复制 `{3, 1, 2}` 得到 `{2, 1, 3}`。想按原顺序插到开头，用 `inserter(c, c.begin())`。

!!! pitfall "`back_inserter` 会先 `reserve`"
    插入迭代器看不到源范围有多大，只能逐个 `push_back`。性能敏感时先 `out.reserve(n)`，或者直接用容器的范围插入成员，例如 C++23 的 `append_range`、`insert_range`。

!!! pitfall "插入迭代器比容器活得长"
    插入迭代器只保存裸指针。把 `back_inserter(local_vec)` 存进一个比 `local_vec` 活得更久的对象，就会留下悬垂指针。

## 思考题

!!! question "思考题"
    `std::back_insert_iterator<std::vector<int>>` 建模 `indirectly_writable<..., long>` 吗？`indirectly_writable<..., std::string>` 呢？

<details markdown="1">
<summary>答案</summary>

对 `long`，建模。`long` 可以隐式转换为 `int`，`*o = long_value` 经过转换调用 `operator=(int&&)`。概念里那两行 `const_cast<const iter_reference_t<Out>&&>(*o)` 也不构成障碍（[[iterator.concept.writable]]）：`iter_reference_t<Out>` 是 `back_insert_iterator&`，给引用类型加 const 会被忽略，引用折叠后仍是 `back_insert_iterator&`，非 const 的赋值运算符照常可用。

对 `std::string`，不建模，`string` 不能转换为 `int`。
</details>
