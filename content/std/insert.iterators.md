---
title: 插入迭代器
summary: back_insert_iterator / front_insert_iterator / insert_iterator 把"*out++ = x"变成 push_back / push_front / insert；operator* 与 operator++ 都返回自身（no-op），赋值才是动作；只存容器指针（和 insert_iterator 的位置迭代器）；C++20 起 difference_type 为 ptrdiff_t，从而能用于 ranges:: 算法；insert_iterator 的 iter 每次插入后更新，所以对 set 也能连续插入。
status: done
covers: *
since: c++98
related: predef.iterators, output.iterators, iterator.concept.output, sequence.reqmts, associative.reqmts, iterator.range
tags: 标准库, 迭代器, 适配器, 输出迭代器
updated: 2026-10-18
---

[insert.iterators.general] ¶1 把动机讲得很清楚：对普通迭代器，

```cpp
while (first != last) *result++ = *first++;
```

把 `[first, last)` **覆写**到以 `result` 开头的范围；而当 `result` 是**插入迭代器**（[[g:insert-iterator]]）时，同样的代码会把元素**插入**容器。于是所有"复制类"算法都能在**插入模式**而非覆写模式下工作——不必预先 `resize` 目标容器。

¶2 概括了共同设计：插入迭代器由一个容器（以及可能的一个位置迭代器）构造；满足输出迭代器要求；`operator*` 返回插入迭代器自身；`operator=(const T&)` 在迭代器"所指位置"之前插入 `x`。三种插入迭代器与三个辅助函数：

| 类模板 | 赋值的效果 | 辅助函数 | 容器需要 |
|---|---|---|---|
| `back_insert_iterator<C>` | `container->push_back(value)` | `back_inserter(c)` | `push_back` |
| `front_insert_iterator<C>` | `container->push_front(value)` | `front_inserter(c)` | `push_front` |
| `insert_iterator<C>` | `iter = container->insert(iter, value); ++iter;` | `inserter(c, i)` | `insert(pos, value)` |

## 类定义（以 `back_insert_iterator` 为例）

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

要点：

- **只存一个指针**：构造函数以 `addressof(x)` 初始化 `container`（[back.insert.iter.ops] ¶1）——用 `addressof` 而非 `&`，防止容器类型重载了一元 `&`。所以插入迭代器复制代价极低，但它不拥有容器，容器必须活得比它长。
- **`operator*`、`operator++` 都是空操作**，返回 `*this`（¶6、¶7）。`*it = v`、`*it++ = v`、`it = v` 三者效果相同。这就是为什么它只能是**输出**迭代器：`*it` 返回的不是元素。
- **两个赋值重载**：`const value_type&` 版复制，`value_type&&` 版移动（¶2–¶5）。参数类型是容器的 `value_type`，所以对 `vector<string>` 写 `*it = "abc"` 会先构造一个临时 `string` 再移动进去，而不是 `emplace_back`。
- **`difference_type` 是 `ptrdiff_t`**：C++20 之前是 `void`。改为 `ptrdiff_t` 后插入迭代器才建模 `weakly_incrementable`，从而能作为 `ranges::copy` 等算法的输出迭代器（`output_iterator` 概念要求 `weakly_incrementable`）。
- 全部成员是 `constexpr`：C++20 起插入迭代器可以在常量求值中与 `constexpr` 的 `vector`、`string` 一起使用。

`front_insert_iterator` 完全平行，只是调用 `push_front`。注意 `back_insert_iterator::operator++(int)` 返回**值**，而下面 `insert_iterator` 的返回**引用**——两者在概要中写法不同，但因为都是空操作，用起来没有区别。

## `insert_iterator`（[insert.iterator]）

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

[insert.iter.ops] ¶2 规定赋值的效果：

```cpp
iter = container->insert(iter, value);
++iter;
```

两步都关键：

1. **用 `insert` 的返回值更新 `iter`**——插入可能使原来的 `iter` 失效（`vector` 扩容），而 `insert` 返回指向新元素的有效迭代器；
2. **再 `++iter`**——让下一次插入发生在刚插入元素**之后**，于是连续赋值保持原有顺序：向 `{10, 20}` 的 `20` 之前依次插入 `3, 1, 2`，结果是 `{10, 3, 1, 2, 20}`。

对**关联容器**，`insert(hint, value)` 把 `iter` 当作提示（*hint*），元素最终位置由键决定；更新后的 `iter` 仍是一个有效的提示。所以 `inserter(s, s.end())` 是把任意序列灌进 `std::set` 的惯用法。

成员 `iter` 的类型是 `ranges::iterator_t<Container>`（C++20 起，原先是 `typename Container::iterator`），辅助函数 `inserter(Container& x, ranges::iterator_t<Container> i)` 同样。

## 例子

```cpp run title="inserters.cpp" ok
#include <algorithm>
#include <cassert>
#include <deque>
#include <iterator>
#include <list>
#include <set>
#include <vector>

// C++20 起插入迭代器建模 output_iterator，可用于 ranges:: 算法
static_assert(std::output_iterator<std::back_insert_iterator<std::vector<int>>, int>);
static_assert(std::output_iterator<std::insert_iterator<std::set<int>>, int>);

int main() {
    std::vector<int> v{3, 1, 2};

    std::set<int> s;
    std::ranges::copy(v, std::inserter(s, s.end()));      // 位置只是提示
    assert((s == std::set{1, 2, 3}));

    std::deque<int> d;
    std::ranges::copy(v, std::front_inserter(d));         // 每次都插到最前：顺序反转
    assert((d == std::deque{2, 1, 3}));

    std::list<int> l{10, 20};
    std::ranges::copy(v, std::inserter(l, std::next(l.begin())));
    assert((l == std::list{10, 3, 1, 2, 20}));            // ++iter 保持了原顺序

    std::vector<int> out;
    std::ranges::transform(v, std::back_inserter(out), [](int x) { return x * x; });
    assert((out == std::vector{9, 1, 4}));
}
```

## 常见误区

!!! pitfall "`front_inserter` 会反转顺序"
    每次 `push_front` 都插到最前面，所以复制 `{3, 1, 2}` 得到 `{2, 1, 3}`。想保持顺序地插到开头，用 `inserter(c, c.begin())`。

!!! pitfall "对 `vector` 用 `front_inserter`"
    `vector` 没有 `push_front`，`front_insert_iterator<vector<int>>` 的赋值运算符实例化失败，编译报错——这是好事，`vector` 头部插入是线性时间。

!!! pitfall "以为 `back_inserter` 会先 `reserve`"
    插入迭代器看不到源范围的大小，只能逐个 `push_back`。性能敏感时先 `out.reserve(n)`，或直接用容器的范围插入成员（C++23 的 `append_range`、`insert_range`）。

!!! pitfall "插入迭代器比容器活得长"
    插入迭代器只存裸指针。把 `back_inserter(local_vec)` 存进一个比 `local_vec` 生命周期更长的对象里，是典型的悬垂指针。

## 思考题

!!! question "思考题"
    1. 为什么 `operator*` 返回插入迭代器自身而不是某种代理？
    2. `std::back_insert_iterator<std::vector<int>>` 是 `indirectly_writable<..., long>` 吗？`indirectly_writable<..., std::string>` 呢？

<details markdown="1">
<summary>展开查看答案与解析</summary>

1. 返回自身是最简单的让 `*it = v` 调用到"插入"的办法：赋值运算符就定义在插入迭代器上。返回代理也行，但多一个类型且没有好处。C++98 就这样设计，也意味着 `*it` 返回的引用指向迭代器对象本身——它不是任何元素。
2. 对 `long`：是。`long` 可隐式转换为 `int`，`*o = long_value` 经转换调用 `operator=(const int&)` 或 `operator=(int&&)`。概念中那两行 `const_cast<const iter_reference_t<Out>&&>(*o)` 也不构成障碍：`iter_reference_t<Out>` 是 `back_insert_iterator&`，对引用类型加 `const` 被忽略（[[dcl.ref]]），引用折叠后仍是 `back_insert_iterator&`，非 const 的赋值运算符照常可用。对 `std::string`：否，`string` 不能转换为 `int`。
</details>

## 小结

!!! summary
    - 插入迭代器把"写入"翻译成 `push_back`/`push_front`/`insert`；`*` 与 `++` 是空操作。
    - 只存容器指针（`insert_iterator` 另存位置）；构造用 `addressof`。
    - `insert_iterator` 用 `insert` 的返回值更新位置并 `++`，保持插入顺序；对关联容器位置只是提示。
    - C++20：`difference_type` 为 `ptrdiff_t`（可用于 `ranges::` 算法），成员全部 `constexpr`，位置类型为 `ranges::iterator_t<Container>`。
