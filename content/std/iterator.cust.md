---
title: ranges::iter_move 与 ranges::iter_swap
summary: 泛型代码怎样从迭代器移出元素、交换两个迭代器所指的元素：两个定制点对象先找用户经 ADL 提供的版本，再退回默认做法；返回代理对象的迭代器要靠它们才能被算法正确地移动和交换。
status: done
covers: *
since: c++20
papers: P0896R4
related: iterator.assoc.types, iterator.concept.readable, alg.req, customization.point.object, concept.swappable, basic.lookup.argdep, temp.func.order, reverse.iterators, move.iterators
tags: 标准库, 迭代器, CPO, 代理迭代器, ADL
updated: 2026-10-19
---

!!! tldr
    - 在泛型代码里，从迭代器移出元素写 `ranges::iter_move(it)`，交换两个迭代器所指的元素写 `ranges::iter_swap(a, b)`，不要写 `std::move(*it)` 或 `std::swap(*a, *b)`。
    - `iter_move(E)` 先找只经 ADL 找到的用户定制；没有时，`*E` 是左值就返回 `std::move(*E)`，否则直接返回 `*E`。
    - `iter_swap(E1, E2)` 先找 ADL 定制，再试 `ranges::swap(*E1, *E2)`，最后用三次移动完成交换。
    - 定制只能改变怎样取出或交换，不能改变结果的值；违反时程序 {{ifndr}}。
    - `iter_rvalue_reference_t<I>` 由 `iter_move` 的返回类型定义。

## 代理迭代器的问题

C++11 的泛型算法这样移出一个元素：`T tmp = std::move(*it);`。这对 `vector<int>::iterator` 没有问题。但有些迭代器的 `*it` 返回的不是引用，而是一个临时的**代理对象**，它代表底层元素，例如 `vector<bool>::iterator` 和 `views::zip` 的迭代器。对这种迭代器，`std::move(*it)` 只是把代理对象变成右值，并没有移动底层元素；`std::swap(*a, *b)` 交换的也只是两个临时代理。

C++20 把这两个操作变成可定制的：`ranges::iter_move` 和 `ranges::iter_swap`。它们是**定制点对象**（[[customization.point.object]]），即这样一种函数对象：先尝试用户提供的版本，没有时退回合理的默认实现。

它们的结果也参与定义关联类型：`iter_rvalue_reference_t<I>` 就是 `decltype(ranges::iter_move(declval<I&>()))`，而 `indirectly_readable` 要求 `iter_reference_t` 与 `iter_rvalue_reference_t` 有公共引用（[[iterator.concept.readable]]）。

## `ranges::iter_move` [iterator.cust.move]

¶1 对子表达式 `E`，`ranges::iter_move(E)` [[g:expression-equivalent]]于下面第一个适用的表达式：

1. （1.1）`E` 是类或枚举类型，并且 `iter_move(E)` 作为不求值操作数时良构，其中名字 `iter_move` 只经实参依赖查找（ADL，[[basic.lookup.argdep]]）确定：`iter_move(E)`。
2. （1.2）否则，如果 `*E` 良构：`*E` 是左值时为 `std::move(*E)`，否则为 `*E`。
3. （1.3）否则非良构。注 1 指出，这种情况出现在模板实例化的直接语境中时会导致替换失败，所以 `ranges::iter_move` 对不可解引用的类型可以安全地用于 SFINAE。

只经 ADL 意味着普通的非限定查找不参与。在全局命名空间写一个 `iter_move` 模板不会被找到，只有与 `E` 的类型关联的命名空间里的声明（包括隐藏友元）才算。

```cpp run title="iter_move_types.cpp" ok
#include <iterator>
#include <string>
#include <utility>

int* p;
static_assert(std::same_as<decltype(std::ranges::iter_move(p)), int&&>);
static_assert(std::same_as<std::iter_rvalue_reference_t<int*>, int&&>);

struct X {   // operator* 返回亡值
  using value_type = std::string;
  using difference_type = long;
  std::string* s;
  std::string&& operator*() const { return std::move(*s); }
  X& operator++();
  X operator++(int);
};
static_assert(std::same_as<std::iter_rvalue_reference_t<X>, std::string&&>);

int main() {}
```

`int*` 不是类类型，（1.1）不适用；`*p` 是左值，所以结果是 `std::move(*p)`，类型 `int&&`。`X` 的 `*x` 是亡值，不是左值，（1.2）直接返回 `*x`，类型仍是 `std::string&&`。

¶2 定制还要守一条语义规则：

!!! std
    If ranges::iter_move(E) is not equal to *E, the program is ill-formed, no diagnostic required.

    如果 `ranges::iter_move(E)` 与 `*E` 不相等，程序 {{ifndr}}。

也就是说，定制只能改变怎样把值拿出来（移动还是复制、返回什么类型），不能改变拿出来的值是什么。

!!! impl "libc++ 的实现"
    libc++ 在内部命名空间里声明 `void iter_move() = delete;`，再用三个互斥的概念分别对应（1.1）和（1.2）的两种情况，各配一个 `operator()` 重载。那个被删除的无参声明让非限定查找在这个命名空间里就停下，不会继续向外找到别的 `iter_move`，实际效果是只剩 ADL。

## `ranges::iter_swap` [iterator.cust.swap]

¶1 `ranges::iter_swap` 交换两个实参所指的值（交换值的含义见 [[concept.swappable]]）。

¶2–¶3 先定义一个仅用于说明的函数模板 *iter-exchange-move*`(x, y)`：

```cpp
iter_value_t<X> old_value(iter_move(x));
*x = iter_move(y);
return old_value;
```

它把 `*x` 移出到一个临时值，把 `*y` 移入 `*x`，返回旧值。它是否 `noexcept` 由这两步决定。

¶4 `ranges::iter_swap(E1, E2)` 与下面第一个适用的表达式等价：

1. （4.1）`E1` 或 `E2` 是类或枚举类型，并且 `iter_swap(E1, E2)` 良构：`(void)iter_swap(E1, E2)`。这里的重载决议在一个特殊的语境中进行：它包含声明 `template<class I1, class I2> void iter_swap(I1, I2) = delete;`，不包含 `ranges::iter_swap` 本身。如果选中的函数并不交换两者所指的值，程序 {{ifndr}}。
2. （4.2）否则，如果两者的类型都建模 `indirectly_readable`，并且它们的引用类型建模 `swappable_with`：`ranges::swap(*E1, *E2)`。
3. （4.3）否则，如果两者的类型 `T1`、`T2` 互相建模 `indirectly_movable_storable`（[[alg.req]]）：`(void)(*E1 = iter-exchange-move(E2, E1))`，但 `E1` 只求值一次。
4. （4.4）否则非良构。与 `iter_move` 一样，可以导致替换失败。

### 被删除的 `iter_swap` 模板有什么用

（4.1）里那个被删除的模板没有约束、按值接受两个参数，形状与 `std::iter_swap(ForwardIt1, ForwardIt2)` 相同。如果迭代器类型关联到命名空间 `std`（比如它是 `std::vector<MyType>::iterator`，或者模板实参来自 `std`），ADL 会找到同样没有约束的 `std::iter_swap`。被删除的模板与它一样匹配，重载决议因歧义而失败，（4.1）不成立，于是转入（4.2）。

注 1 指出了另一面：被删除的模板可行时，用户的定制必须比它更特化（[[temp.func.order]]）才能被选中。写成参数为具体类型的隐藏友元，或者参数有具体类型的模板，都满足这一点。

## 例子：一个 zip 式代理迭代器

```cpp run title="iter_move_swap.cpp" ok
#include <cassert>
#include <iterator>
#include <utility>

namespace lib {
struct Ref {                       // *it 返回的代理
  int* a; int* b;
  operator std::pair<int, int>() const { return {*a, *b}; }
};
struct It {
  int* a; int* b;
  using value_type = std::pair<int, int>;
  using difference_type = std::ptrdiff_t;
  Ref operator*() const { return {a, b}; }
  It& operator++() { ++a; ++b; return *this; }
  It operator++(int) { auto t = *this; ++*this; return t; }
  bool operator==(const It&) const = default;
  // 隐藏友元：只能经 ADL 找到
  friend std::pair<int, int> iter_move(const It& i) { return {*i.a, *i.b}; }
  friend void iter_swap(const It& x, const It& y) {
    std::swap(*x.a, *y.a);
    std::swap(*x.b, *y.b);
  }
};
}

static_assert(std::same_as<std::iter_rvalue_reference_t<lib::It>,
                           std::pair<int, int>>);

int main() {
  int a[]{1, 2}, b[]{3, 4};
  lib::It x{a, b}, y{a + 1, b + 1};
  std::ranges::iter_swap(x, y);    // 经 (4.1) 调用隐藏友元
  assert(a[0] == 2 && a[1] == 1 && b[0] == 4 && b[1] == 3);
}
```

如果去掉这两个隐藏友元，`It` 仍然是 `indirectly_readable`：`Ref` 能转换为 `pair<int, int>`，二者的公共引用类型是 `pair<int, int>`。但是：

- `ranges::iter_move(x)` 走（1.2）的第二种情况，返回 `Ref` 纯右值本身。算法里 `iter_value_t<I> tmp(ranges::iter_move(it));` 得到的是复制而不是移动；元素是 `pair<std::string, std::string>` 时，这就是实际的性能差别。
- `ranges::iter_swap(x, y)` 的三条路都走不通。`Ref` 纯右值之间不能 `ranges::swap`；（4.3）要求能把 `pair<int, int>` 赋给 `*x`，而 `Ref` 不能从 `pair` 赋值。于是 `indirectly_swappable<It>` 为假，`ranges::sort` 这类需要 `permutable` 的算法会拒绝它。

本机 Clang 23 证实了这几点：去掉两个友元后，`indirectly_readable<It>` 为真，`iter_rvalue_reference_t<It>` 是 `Ref`，`indirectly_swappable<It>` 为假。

标准库的 `vector<bool>::iterator` 没有定制 `iter_move`。它的 `*it` 返回 `vector<bool>::reference` 纯右值，`iter_rvalue_reference_t` 就是这个代理类型，与 `bool&` 的公共引用是 `bool`。它能被交换，是因为这个代理可以从 `bool` 赋值，并且库为它提供了 `swap` 重载。

## 适配器怎样转发

迭代器适配器都以隐藏友元的形式提供 `iter_move` 和 `iter_swap`，把操作转发给底层迭代器，让用户的定制穿透包装：

- `reverse_iterator` 先复制底层迭代器并递减，再对它调用 `ranges::iter_move`（[[reverse.iterators]]）；
- `move_iterator`、`counted_iterator`、`common_iterator`、`basic_const_iterator` 直接转发（[[move.iterators]]、[[iterators.counted]]、[[iterators.common]]、[[const.iterators]]）。

## 常见误解

!!! pitfall "在泛型算法里写 `std::move(*it)`"
    `std::move(*it)`、`std::swap(*a, *b)`、`std::iter_swap(a, b)` 对代理迭代器要么没有真正移动或交换，要么编译不过。`std::ranges::sort` 能排序 `views::zip(a, b)`，因为它用的是 `ranges::iter_move` 和 `ranges::iter_swap`。`std::sort` 要求 *Cpp17RandomAccessIterator*，zip 的迭代器不满足（`*it` 不是引用），按标准不能这样用；本机 libc++ 碰巧能编译并正确排序，这不受标准保证。

!!! pitfall "用无约束模板做定制"
    ```cpp
    namespace mine {
      template<class I> void iter_swap(I a, I b);   // 不比被删除的模板更特化
    }
    ```
    对关联到 `std` 的迭代器，这样的定制会和被删除的模板产生歧义，于是被跳过。照注 1 的建议，写成参数为具体类型的隐藏友元。

## 思考题

!!! question "思考题"
    （4.1）为什么要求 `E1` 或 `E2` 是类或枚举类型？

<details markdown="1">
<summary>答案</summary>

指针这样的标量类型没有关联类，ADL 找不到任何用户定制，没有必要尝试；同时也不应该允许用户改变指针的交换语义。`ranges::swap` 有同样的限制（[[concept.swappable]]）。
</details>
