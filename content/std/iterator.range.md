---
title: 范围访问函数
summary: std::begin、std::end、std::size、std::data 等非成员函数模板：对容器转发到成员函数，对内建数组给出指针和长度，让泛型代码对两者用同一种写法。
status: done
covers: iterator.range
since: c++11
related: iterators, range.access, reverse.iterators, const.iterators, support.initlist, basic.lookup.argdep, stmt.ranged, dcl.array
tags: 标准库, 迭代器, begin, end, size
updated: 2026-10-19
---

!!! tldr
    - `std::begin(c)` 就是 `c.begin()`，`std::size(c)` 就是 `c.size()`；它们的用处是对内建数组也给出同样的写法。
    - `std::ssize` 返回有符号类型，避免 `v.size() - 1` 在空容器上下溢。
    - `std::cbegin(c)` 只是 `std::begin` 加上 const，对 `span<int>` 这样的视图不能保证得到只读迭代器。
    - 这些函数都能绑定临时对象，返回的迭代器随临时对象一起失效；C++20 的 `std::ranges::begin` 等在编译期拒绝这种调用，新代码应优先使用它们。

## 为什么需要非成员版本

```cpp run title="range_access.cpp" ok
#include <cstdio>
#include <iterator>
#include <ranges>
#include <vector>

int main() {
  int a[4]{1, 2, 3, 4};
  static_assert(std::size(a) == 4 && std::ssize(a) == 4);
  static_assert(!std::empty(a));
  static_assert(std::same_as<decltype(std::rbegin(a)),
                             std::reverse_iterator<int*>>);

  std::vector<int> v{1, 2, 3};
  static_assert(std::same_as<decltype(std::ssize(v)), std::ptrdiff_t>);
  for (auto i = std::ssize(v) - 1; i >= 0; --i)  // 有符号：安全地倒序
    std::printf("%d", v[i]);
  std::puts("");

  std::initializer_list<int> il{1, 2, 3};
  auto r = std::rbegin(il);                      // initializer_list 重载
  std::printf("%d\n", *r);
}
```

内建数组没有成员函数，`a.begin()` 写不出来。泛型代码写 `std::begin(x)`，不管 `x` 是 `std::vector<int>` 还是 `int[4]` 都能工作。[iterator.range] 提供的就是这样一组非成员函数模板：对容器转发到同名成员函数，对数组直接给出指针和长度。

¶1 除了 `<iterator>`，包含 `<array>`、`<vector>`、`<string>`、`<string_view>`、`<span>`、`<optional>` 等 21 个头文件中的任何一个，也能使用这些函数。`<optional>` 在名单里，是因为 C++26 起 `optional` 本身是一个最多含一个元素的范围，有 `begin()` 和 `end()`。

## 函数一览

| 函数 | 返回 | 段落 |
|---|---|---|
| `begin(c)`、`end(c)` | `c.begin()`、`c.end()` | ¶2–¶3 |
| `begin(arr)`、`end(arr)` | `arr`、`arr + N` | ¶4–¶5 |
| `cbegin(c)`、`cend(c)` | `std::begin(c)`、`std::end(c)`，参数是 `const C&` | ¶6–¶7 |
| `rbegin(c)`、`rend(c)` | `c.rbegin()`、`c.rend()` | ¶8–¶9 |
| `rbegin(arr)`、`rend(arr)` | `reverse_iterator<T*>(arr + N)`、`reverse_iterator<T*>(arr)` | ¶10–¶11 |
| `rbegin(il)`、`rend(il)` | `initializer_list<E>` 的反向迭代器 | ¶12–¶13 |
| `crbegin(c)`、`crend(c)` | `std::rbegin(c)`、`std::rend(c)`，参数是 `const C&` | ¶14–¶15 |
| `size(c)`、`size(arr)` | `c.size()`、`N`（`size_t`） | ¶16–¶17 |
| `ssize(c)`、`ssize(arr)` | 有符号的长度 | ¶18–¶19 |
| `empty(c)`、`empty(arr)` | `c.empty()`、`false` | ¶20–¶21 |
| `data(c)`、`data(arr)` | `c.data()`、`arr` | ¶22–¶23 |

它们都是 constexpr 函数。容器版本的 noexcept 跟随对应的成员函数，例如 `noexcept(noexcept(c.begin()))`；数组版本无条件 noexcept。容器版本的返回类型都写成尾置的 `decltype(c.begin())` 之类，对没有相应成员的类型，替换失败只是让这个重载不参与重载决议。

## 值得注意的几个细节

¶21 `empty(arr)` 总是 `false`。C++ 的数组长度必须大于零（[[dcl.array]]），不存在空数组。

¶18 `ssize(c)` 返回 `ptrdiff_t` 与 `make_signed_t<decltype(c.size())>` 的公共类型，通常就是 `ptrdiff_t`。某个容器的 `size_type` 比 `ptrdiff_t` 更宽时，结果也随之变宽，不会截断。它的主要用途是做减法和与负数比较：

<div class="compare" markdown="1">

```cpp
// i 是无符号数，永远 >= 0：死循环
for (auto i = v.size() - 1; i >= 0; --i)
```

```cpp
// i 是 ptrdiff_t：正常结束
for (auto i = std::ssize(v) - 1; i >= 0; --i)
```

</div>

¶19 `ssize(arr)` 的模板参数写成 `ptrdiff_t N`。数组界的类型是 `size_t`，但模板实参推导允许用另一种整数类型的非类型模板参数接收它（[[temp.deduct.type]]），推出的值相同。

¶6 `cbegin(c)` 只有 `const C&` 一个重载，返回 `std::begin(c)`。它靠 const 拿到常量迭代器。`std::span<int>` 这类视图的 const 只管视图本身，`const span<int>` 的 `begin()` 仍返回可写的迭代器，`std::cbegin` 对它无效。C++23 的 `std::ranges::cbegin` 才保证得到常量迭代器（[[const.iterators]]）。

¶12–¶13 `initializer_list` 只剩 `rbegin`、`rend` 两个专门的重载。C++26 给 `initializer_list` 加上了 `data()` 和 `empty()` 成员（[[support.initlist]]），通用的 `std::data(c)`、`std::empty(c)` 因此可以直接用；原先 `<initializer_list>` 里针对它的 `begin`、`end` 非成员重载也删掉了，交给通用的 `begin(const C&)`。`initializer_list` 没有 `rbegin()` 成员，所以反向的两个重载还得保留。

!!! lawyer "crend 的异常规格"
    当前草案在 ¶15 前的声明里，`crend` 的异常规格写作 `noexcept(noexcept(c.crend()))`，而返回类型是 `decltype(std::rend(c))`；概要 [[iterator.synopsis]] 中则写作 `noexcept(noexcept(std::rend(c)))`。`crbegin` 用的是 `std::rbegin(c)`，按对称性前者看起来是笔误：内建数组根本没有 `crend()` 成员。理解意图时应以概要为准。

## `using std::begin; begin(x);` 与 ranges::begin

C++11 到 C++17 的泛型代码，要同时支持数组、有成员 `begin` 的类型和只提供非成员 `begin` 的用户类型，惯用的写法是：

```cpp
using std::begin;
auto it = begin(x);  // 非限定调用：普通查找找到 std::begin，
                     // 实参依赖查找再找到 x 所在命名空间的 begin
```

基于范围的 `for` 在核心语言里也是这样做的：先找成员 `begin`，找不到就用实参依赖查找（[[stmt.ranged]]、[[basic.lookup.argdep]]）。这种写法有两个问题：忘了写 `using` 就不支持数组；实参依赖查找可能找到一个无关的、没有约束的 `begin`。

C++20 的 `std::ranges::begin` 是一个**定制点对象**（customization point object）：一个函数对象，内部按固定顺序尝试数组、成员 `begin()`、实参依赖查找找到的 `begin()`（[[range.access]]）。它还要求结果建模 `input_or_output_iterator`，并在编译期拒绝对右值的非借用范围调用。新代码应优先使用 `ranges::begin`、`ranges::end`、`ranges::size`、`ranges::ssize`、`ranges::empty`、`ranges::data`。

## 常见误解

!!! pitfall "`std::begin(f())` 拿到的迭代器可以用"
    `std::begin(const C&)` 能绑定临时对象，返回的迭代器在完整表达式结束时随临时容器一起失效。`std::ranges::begin(std::vector<int>{1})` 则直接编译失败，本机 Clang 23 报告调用了被删除的函数。

!!! pitfall "`std::rbegin({1, 2, 3})` 可以保存下来"
    这个调用能编译，用的正是 `initializer_list<E>` 的重载。但 `{1, 2, 3}` 背后的数组（[[dcl.init.list]]）只活到完整表达式结束，`auto r = std::rbegin({1, 2, 3}); *r;` 在 AddressSanitizer 下报告 stack-use-after-scope。先把列表绑定到一个具名的 `initializer_list` 变量，背后数组的生命周期才会随之延长，就像上面完整例子里的 `il`。

## 思考题

!!! question "思考题"
    为什么 `std::cbegin` 只有 `const C&` 一个重载，而 `std::begin` 有 `C&` 和 `const C&` 两个？

<details markdown="1">
<summary>答案</summary>

`cbegin` 的全部意义就是以 const 方式调用 `begin`，参数只需要 `const C&`，它对左值和右值都能绑定。`begin` 需要 `C&` 重载，才能对非 const 容器返回可写的迭代器。
</details>
