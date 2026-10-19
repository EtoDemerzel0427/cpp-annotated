---
title: 常量迭代器：basic_const_iterator
summary: C++23 的 basic_const_iterator 给任意输入迭代器套上一层，使解引用结果不能用来修改元素，同时保留原来的遍历类别；它是 ranges::cbegin 和 views::as_const 的基础。
status: done
covers: *
since: c++23
related: predef.iterators, iterator.requirements, iterator.concepts, iterator.assoc.types, iterator.cust, iterator.range, move.iterators
tags: 标准库, 迭代器, 适配器, const, C++23
updated: 2026-10-19
---

!!! tldr
    - `std::cbegin` 对 `span<int>` 这类 const 不传递到元素的类型无效，返回的迭代器仍然可写；C++23 的 `std::ranges::cbegin` 改用 `basic_const_iterator`，才真正得到只读迭代器。
    - `iter_const_reference_t<It>` 是 `const iter_value_t<It>&&` 与原引用类型的公共引用；它与原引用类型相同，迭代器就已经是常量迭代器。
    - `const_iterator<I>` 对已经是常量迭代器的 `I` 原样返回，否则返回 `basic_const_iterator<I>`。
    - `basic_const_iterator` 保留底层的全部类别，包括 contiguous，并能隐式转换回 `const int*` 这类原生常量迭代器。
    - 截至写作时，Clang 23 自带的 libc++ 还没有实现这一节，本页例子需用 GCC 验证。

## 为什么需要它

`std::span<int>` 是一个视图，`const span<int>` 只表示视图本身不能改指向，元素仍然可写。所以 C++11 的 `std::cbegin(s)`，也就是 `std::begin(std::as_const(s))`，返回的迭代器照样能写元素：

```cpp run ok
#include <iterator>
#include <span>
int main() {
  int a[3]{1, 2, 3};
  std::span<int> s(a);
  *std::cbegin(s) = 42;   // OK：cbegin 没能阻止写入
  return a[0] == 42 ? 0 : 1;
}
```

C++23 的办法是提供一个通用的包装：给任意输入迭代器套一层，只改变解引用的结果类型，使它不能用来修改元素。这就是 `basic_const_iterator`。`std::ranges::cbegin`、`views::as_const` 都建立在它上面（[[range.access]]）。

¶1 [const.iterators.general] 用**常量迭代器**（constant iterator）描述目标：通过它不能修改所指的元素（[[iterator.requirements]]）。`basic_const_iterator` 的行为与底层迭代器相同，只是间接运算符把底层的解引用结果转换成一个使它成为常量迭代器的类型。¶2 它的所有特化都是常量迭代器。

## 怎样判断一个迭代器已经是常量的 [const.iterators.alias]

```cpp
template<indirectly_readable It>
  using iter_const_reference_t =
    common_reference_t<const iter_value_t<It>&&,
                       iter_reference_t<It>>;

template<class It>
  concept constant-iterator =        // 说明专用
    input_iterator<It> &&
    same_as<iter_const_reference_t<It>, iter_reference_t<It>>;
```

`iter_const_reference_t<It>` 回答的问题是：给这个迭代器的引用类型加上 const，应该得到什么类型。它的做法是拿值类型的 const 右值引用与原引用类型求**公共引用**（两个引用类型都能转换到的那个类型，见 [[meta.trans.other]] 的 `common_reference`）。如果结果与原引用类型相同，加 const 什么也没改变，这个迭代器就已经是常量迭代器。

| `iter_reference_t<It>` | `iter_value_t<It>` | `iter_const_reference_t<It>` | 常量迭代器？ |
|---|---|---|---|
| `int&` | `int` | `const int&` | 否 |
| `const int&` | `int` | `const int&` | 是 |
| `int&&` | `int` | `const int&&` | 否 |
| `int`（纯右值） | `int` | `int` | 是 |
| `vector<bool>::reference` | `bool` | `bool` | 否 |
| `tuple<int&, int&>`（zip） | `tuple<int, int>` | `tuple<const int&, const int&>` | 否 |

纯右值一行是常量迭代器，因为解引用得到的是一个副本，改它不会影响原元素。最后两行是代理引用（行为像引用的类对象）：公共引用要么是值类型本身，要么是每个成员都加了 const 的代理，同样不能再修改原元素。

¶1 `const_iterator<I>` 对建模 *`constant-iterator`* 的 `I` 就是 `I` 本身，不会多套一层；否则是 `basic_const_iterator<I>`。

¶2 `const_sentinel<S>` 对本身是输入迭代器的 `S`（首尾同类型的范围）等于 `const_iterator<S>`，否则就是 `S`。纯哨位不能解引用，不需要包装。概要里另有 `make_const_iterator(it)`、`make_const_sentinel(s)`，分别返回这两个类型的对象。

## basic_const_iterator 的接口 [const.iterators.iterator]

```cpp
template<input_iterator Iterator>
class basic_const_iterator {
  Iterator current_ = Iterator();                      // 说明专用
  using reference = iter_const_reference_t<Iterator>;  // 说明专用
  using rvalue-reference =                             // 说明专用
    iter-const-rvalue-reference-t<Iterator>;
public:
  using iterator_type = Iterator;
  using iterator_concept = see below;
  using iterator_category = see below;  // 不总是存在
  using value_type = iter_value_t<Iterator>;
  using difference_type = iter_difference_t<Iterator>;
  // 构造、base()、*、->、++、--、+=、-=、[]、比较、+、-、
  // 转换运算符、iter_move
};
```

`reference` 和 `rvalue-reference` 都是说明专用的私有别名，公开接口里没有 `reference` 成员。`iterator_traits` 经由 `iter_reference_t` 推导出引用类型。*`iter-const-rvalue-reference-t<I>`* 是 `common_reference_t<const iter_value_t<I>&&, iter_rvalue_reference_t<I>>`，给 `iter_move` 用。

### 类别全部保留 [const.iterators.types]

¶1 `iterator_concept` 按底层依次判断 contiguous、random access、bidirectional、forward，都不满足时为 input。连续迭代器也保留下来，这与 `move_iterator`、`reverse_iterator` 不同：加 const 不改变元素在内存里的位置，所以 `basic_const_iterator<int*>` 仍然是连续迭代器。

¶2 只有底层建模 `forward_iterator` 时才声明 `iterator_category`，取底层的 `iterator_traits<Iterator>::iterator_category`。

### 常量化发生在解引用处 [const.iterators.ops]

¶6 `operator*` 等价于 `return static_cast<reference>(*current_);`。¶13 `operator[]` 同样经过 `static_cast<reference>`。适配器其余部分只是把操作转发给 `current_`。

- ¶1–¶3 构造：从 `Iterator` 构造（移入）；从 `basic_const_iterator<U>` 转换（`U` 能转换为 `Iterator`）；从任何能转换为 `Iterator` 的 `T&&` 构造。最后一种让 `basic_const_iterator<vector<int>::const_iterator>` 可以直接用 `vector<int>::iterator` 构造。默认构造只在底层可默认初始化时存在。
- ¶4–¶5 `base() const&` 返回 `const Iterator&`，`base() &&` 把底层迭代器移出。
- ¶7 `operator->` 只在底层引用是左值引用、去掉 cvref 后就是值类型时提供，返回 `const auto*`。底层是连续迭代器时返回 `to_address(current_)`，否则返回 `addressof(*current_)`。
- ¶9 对单遍的输入迭代器，后置 `++` 返回 `void`。对前向及以上的迭代器，后置 `++` 和 `--` 声明为 `= default`，效果是复制、前置递增或递减、返回副本（[[over.inc.default]]）。
- ¶14 与哨位比较 `==`；¶17–¶18 与同类型比较大小和 `<=>`；¶19–¶22 与底层迭代器能比较的其他类型 `I` 双向比较。最后一组让 `basic_const_iterator<It>` 能直接与 `It` 比较。
- ¶23–¶26 随机访问时提供 `+`、`-`，以及与 sized 哨位的距离。

### 转换回原生常量迭代器（¶15–¶16）

```cpp
template<not-a-const-iterator CI>
  requires constant-iterator<CI> &&
           convertible_to<Iterator const&, CI>
constexpr operator CI() const &;
template<not-a-const-iterator CI>
  requires constant-iterator<CI> &&
           convertible_to<Iterator, CI>
constexpr operator CI() &&;
```

只要底层迭代器能转换到某个常量迭代器类型 `CI`，`basic_const_iterator` 就能隐式转换过去。例如 `basic_const_iterator<int*>` 能转换为 `const int*`，`basic_const_iterator<vector<int>::iterator>` 能转换为 `vector<int>::const_iterator`。这样 `ranges::cbegin(v)` 的结果仍然能交给只接受原生常量迭代器的旧接口。

[const.iterators.iterator] ¶1 定义的 *`not-a-const-iterator<CI>`* 排除 `CI` 是 `basic_const_iterator` 特化的情形，避免与转换构造函数形成二义。

概要还特化了 `common_type`：`basic_const_iterator<T>` 与 `U` 的公共类型是 `basic_const_iterator<common_type_t<T, U>>`。一端经过常量化、另一端没有的两个迭代器因此能统一成一个类型。

## 例子

```cpp run title="const_iterator.cpp" ok cc=gsnapshot
#include <cassert>
#include <iterator>
#include <ranges>
#include <span>

using std::basic_const_iterator;
static_assert(std::same_as<
    std::iter_const_reference_t<int*>, const int&>);
// 已是常量迭代器：不包装
static_assert(std::same_as<
    std::const_iterator<const int*>, const int*>);
static_assert(std::same_as<
    std::const_iterator<int*>, basic_const_iterator<int*>>);
// 类别保留
static_assert(std::contiguous_iterator<
    basic_const_iterator<int*>>);

int main() {
  int a[3]{1, 2, 3};
  std::span<int> s(a);
  auto it = std::ranges::cbegin(s);
  // *it = 42;                  // error：*it 是 const int&
  assert(*it == 1);

  basic_const_iterator<int*> ci = a;
  const int* p = ci;           // 转换回原生常量迭代器
  assert(p == a);
}
```

本机 Clang 23 的 libc++ 还没有 `basic_const_iterator`、`const_iterator`、`iter_const_reference_t`，`<version>` 里的 `__cpp_lib_ranges_as_const` 仍被注释掉，所以这段代码在本地无法编译。libstdc++ 和 MSVC STL 已经实现，可以用 godbolt 按钮在 GCC 上运行。上面表格中的公共引用已在本地用 `std::common_reference_t` 逐项核对。

## 常见误解

!!! pitfall "`std::cbegin` 和 `std::ranges::cbegin` 是一回事"
    `std::cbegin(c)` 仍是 C++11 的定义 `std::begin(std::as_const(c))`（[[iterator.range]]），对 `span<int>` 这样的视图返回可写的迭代器。需要真正只读的迭代器时，用 `std::ranges::cbegin` 或 `views::as_const`。

!!! pitfall "常量化会让迭代器降级"
    `move_iterator` 最高只到随机访问，`basic_const_iterator` 却保留 contiguous。所以 `std::span<const int>(ranges::cbegin(s), ranges::cend(s))` 是合法的。

## 思考题

!!! question "思考题 1"
    `iter_const_reference_t` 为什么用 `const iter_value_t<It>&&`，而不是 `const iter_value_t<It>&`，参与求公共引用？

<details markdown="1">
<summary>答案</summary>

为了不把右值引用变成左值引用。如果 `iter_reference_t` 是 `int&&`（例如 `move_iterator<int*>`），它与 `const int&&` 的公共引用是 `const int&&`，仍然是右值；与 `const int&` 求公共引用则会得到 `const int&`。对左值引用 `int&`，两种写法的结果都是 `const int&`。
</details>

!!! question "思考题 2"
    `const_iterator<std::istreambuf_iterator<char>>` 是什么类型？

<details markdown="1">
<summary>答案</summary>

`istreambuf_iterator<char>` 的引用类型是 `char`（纯右值），`iter_const_reference_t` 也是 `char`，它已经满足 *`constant-iterator`*。所以按 [const.iterators.alias] ¶1，结果就是 `istreambuf_iterator<char>` 本身。
</details>
