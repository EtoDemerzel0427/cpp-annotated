---
title: 范围访问函数
summary: std::begin/end/cbegin/cend/rbegin/rend/crbegin/crend/size/ssize/empty/data——对成员函数的薄包装，外加数组重载与 initializer_list 的 rbegin/rend；除 <iterator> 外还可经 21 个头文件获得；ssize 返回有符号类型；数组的 empty 恒为 false；"using std::begin; begin(x);" 两步惯用法与 C++20 ranges::begin 定制点对象的对比；C++26 去掉了 initializer_list 的 begin/end/empty/data 专门重载。
status: done
covers: iterator.range
since: c++11
related: iterators, range.access, reverse.iterators, const.iterators, support.initlist, basic.lookup.argdep, stmt.ranged, dcl.array
tags: 标准库, 迭代器, begin, end, size
updated: 2026-10-18
---

[iterator.range] 提供一组**非成员**函数模板：`std::begin(c)` 等价于 `c.begin()`，`std::size(c)` 等价于 `c.size()`……它们存在的理由只有一个——**让内建数组和容器有统一的写法**。泛型代码写 `std::begin(x)`，`x` 是 `std::vector` 还是 `int[10]` 都能工作。

## 在哪里可用（¶1）

¶1：除了 `<iterator>`，包含下列任一头文件也能使用 [iterator.range] 中的函数模板：`<array>`、`<deque>`、`<flat_map>`、`<flat_set>`、`<forward_list>`、`<hive>`、`<inplace_vector>`、`<list>`、`<map>`、`<optional>`、`<regex>`、`<set>`、`<simd>`、`<span>`、`<stacktrace>`、`<string>`、`<string_view>`、`<unordered_map>`、`<unordered_set>`、`<valarray>`、`<vector>`。

名单里的新面孔反映了 C++26 的变化：`<hive>`、`<inplace_vector>`、`<simd>` 是新头文件；`<optional>` 在列，是因为 C++26 让 `optional` 成为了一个最多含一个元素的范围（有 `begin()`/`end()`）。

## 函数一览

| 函数 | 返回（¶） | 备注 |
|---|---|---|
| `begin(c)` / `end(c)` | `c.begin()` / `c.end()`（¶2–¶3） | `C&` 与 `const C&` 两个重载 |
| `begin(arr)` / `end(arr)` | `array` / `array + N`（¶4–¶5） | `T (&)[N]` |
| `cbegin(c)` / `cend(c)` | `std::begin(c)` / `std::end(c)`（¶6–¶7） | 只有 `const C&` 重载——靠 const 得到常量迭代器 |
| `rbegin(c)` / `rend(c)` | `c.rbegin()` / `c.rend()`（¶8–¶9） | |
| `rbegin(arr)` / `rend(arr)` | `reverse_iterator<T*>(array + N)` / `(array)`（¶10–¶11） | |
| `rbegin(il)` / `rend(il)` | `reverse_iterator<const E*>(il.end())` / `(il.begin())`（¶12–¶13） | `initializer_list<E>` 按值 |
| `crbegin(c)` / `crend(c)` | `std::rbegin(c)` / `std::rend(c)`（¶14–¶15） | `const C&` |
| `size(c)` | `c.size()`（¶16） | |
| `size(arr)` | `N`（¶17） | 返回 `size_t` |
| `ssize(c)` | `static_cast<common_type_t<ptrdiff_t, make_signed_t<decltype(c.size())>>>(c.size())`（¶18） | 有符号 |
| `ssize(arr)` | `N`（¶19） | 模板参数为 `ptrdiff_t N`，返回 `ptrdiff_t` |
| `empty(c)` | `c.empty()`（¶20） | |
| `empty(arr)` | `false`（¶21） | |
| `data(c)` | `c.data()`（¶22） | `C&` 与 `const C&` |
| `data(arr)` | `array`（¶23） | |

全部是 `constexpr` 函数；容器版本的 `noexcept` 跟随对应成员函数（如 `noexcept(noexcept(c.begin()))`），数组版本无条件 `noexcept`。返回类型都写成尾置的 `decltype(c.begin())` 等，所以它们对没有相应成员的类型是 SFINAE 友好的。

几个值得推敲的细节：

- **`empty(arr)` 恒为 `false`**：C++ 中数组的元素个数必须大于零（[[dcl.array]]），不存在空数组。
- **`ssize`**（C++20）：返回类型是 `ptrdiff_t` 与 `make_signed_t<size_type>` 的公共类型——通常就是 `ptrdiff_t`，但若某容器的 `size_type` 比 `ptrdiff_t` 宽，结果会更宽而不会截断。它的意义在于避免有符号/无符号混合比较，例如倒序循环 `for (auto i = std::ssize(v) - 1; i >= 0; --i)`；用 `size()` 写成 `for (auto i = v.size() - 1; i >= 0; --i)` 是一个永不结束的循环（无符号数永远 `>= 0`）。
- **`ssize(arr)` 的模板参数是 `ptrdiff_t N`**：从数组类型推导 `N` 时（[[temp.deduct.type]]），数组界的类型是 `size_t`，但推导允许以 `ptrdiff_t` 类型的非类型模板参数接收（结果值相同）。
- **`cbegin` 只是加了 const**：`std::cbegin(c)` 返回 `std::begin(const C&)`。对"浅 const"类型（`const std::span<int>` 的 `begin()` 仍返回可写迭代器），它**不能**保证得到常量迭代器。C++23 的 `std::ranges::cbegin` 才通过 `const_iterator` 保证这一点（[[const.iterators]]）。
- **`initializer_list` 只剩 `rbegin`/`rend` 重载**：C++26 中 `initializer_list` 自己获得了 `data()` 与 `empty()` 成员（[[support.initlist]]），于是通用的 `std::data(c)`、`std::empty(c)` 就能工作；原先 `<initializer_list>` 中针对它的 `begin`/`end` 非成员重载也被移除，交给通用的 `begin(const C&)`。剩下的 `rbegin(initializer_list<E>)`/`rend` 仍需专门重载，因为 `initializer_list` 没有 `rbegin()` 成员。

!!! lawyer "一处措辞不一致"
    当前草案中，`crend` 在概要（[[iterator.synopsis]]）里的异常规格是 `noexcept(noexcept(std::rend(c)))`，而在 [iterator.range] ¶15 前的详细声明里写作 `noexcept(noexcept(c.crend()))`，返回类型却仍是 `decltype(std::rend(c))`。按对称性，`crbegin` 用的是 `std::rbegin(c)`，所以后者看起来是编辑性笔误；详细声明的写法会去引用一个 `C` 未必拥有的 `crend()` 成员（内建数组就没有），与概要不符。阅读时应以概要和 `crbegin` 的对称写法理解其意图。

## `using std::begin; begin(x);`：两步惯用法

`std::begin` 是普通的函数模板，对用户类型，库作者若想支持"有非成员 `begin`、没有成员 `begin`"的类型，传统写法是：

```cpp
using std::begin;
auto it = begin(x);   // 非限定调用：普通查找找到 std::begin，ADL 再找到 x 所在命名空间的 begin
```

这是 C++11~17 泛型代码的标准姿势（基于范围的 `for` 在核心语言里用的也是"成员 `begin` 或 ADL 查找的 `begin`"，[[stmt.ranged]]）。它有两个问题：忘记写 `using` 就漏掉数组；ADL 可能找到不相关的、无约束的 `begin`。

C++20 的 `std::ranges::begin` 是定制点对象（[[range.access]]）：一次调用就完成"数组 → 成员 `begin()` → ADL 找到的 `begin()`"的选择，还要求返回值建模 `input_or_output_iterator`，并拒绝对**右值**非借用范围调用（防止悬垂）。新代码应优先使用 `ranges::begin`/`ranges::end`/`ranges::size`/`ranges::ssize`/`ranges::empty`/`ranges::data`。

```cpp run title="range_access.cpp" ok
#include <cstdio>
#include <iterator>
#include <ranges>
#include <vector>

int main() {
    int a[4]{1, 2, 3, 4};
    static_assert(std::size(a) == 4 && std::ssize(a) == 4 && !std::empty(a));
    static_assert(std::same_as<decltype(std::rbegin(a)), std::reverse_iterator<int*>>);

    std::vector<int> v{1, 2, 3};
    static_assert(std::same_as<decltype(std::ssize(v)), std::ptrdiff_t>);
    for (auto i = std::ssize(v) - 1; i >= 0; --i)   // 有符号：安全地倒序
        std::printf("%d", v[i]);
    std::puts("");

    std::initializer_list<int> il{1, 2, 3};         // 后备数组的生命周期随 il 延长
    auto r = std::rbegin(il);                        // initializer_list 重载
    std::printf("%d\n", *r);

    // std::begin 对右值容器也能调用（绑定到 const C&），结果迭代器立即悬垂；
    // ranges::begin 则在编译期拒绝：
    // auto bad = std::ranges::begin(std::vector<int>{1});   // error
}
```

## 常见误区

!!! pitfall "`std::rbegin({1, 2, 3})` 立即悬垂"
    这个调用能编译（正是 `initializer_list<E>` 重载在起作用），但 `{1, 2, 3}` 的后备数组（[[dcl.init.list]]）只活到完整表达式结束：`auto r = std::rbegin({1, 2, 3}); *r;` 在 AddressSanitizer 下报告 stack-use-after-scope。先把列表绑定到一个具名的 `initializer_list` 变量，后备数组的生命周期才随之延长。

!!! pitfall "`std::begin(f())` 的悬垂"
    `std::begin(const C&)` 能绑定临时对象，返回的迭代器在完整表达式结束时随临时容器一起失效。`std::ranges::begin` 对非借用范围的右值直接拒绝。

!!! pitfall "用 `std::size` 做有符号运算"
    `std::size` 返回无符号类型，`std::size(v) - 1` 在 `v` 为空时下溢为极大值。需要做减法或与负数比较时，用 `std::ssize`。

## 思考题

!!! question "思考题"
    1. 为什么 `std::cbegin` 只有 `const C&` 一个重载，而 `std::begin` 有两个？
    2. `std::data(std::string_view("abc"))` 合法吗？`std::data` 对右值 `std::vector<int>{}` 呢？

<details markdown="1">
<summary>展开查看答案与解析</summary>

1. `cbegin` 的全部意义就是"以 const 方式调用 `begin`"，所以参数只需要 `const C&`，它对左值和右值都能绑定。`begin` 需要 `C&` 重载，才能对非 const 容器返回可变迭代器。
2. 都合法：`data(const C&)` 可以绑定临时对象。前者返回指向字符串字面量的指针，有效；后者返回的指针随临时 `vector` 销毁而悬垂（若 `vector` 为空，`data()` 可能为空指针，也可能不是）。
</details>

## 小结

!!! summary
    - 非成员 `begin`/`end`/…/`data`：对容器转发成员函数，对数组给出指针、`N`、`false`；`noexcept` 跟随成员。
    - 除 `<iterator>` 外，21 个容器/视图类头文件也提供它们。
    - `ssize` 返回有符号类型；`cbegin` 只是 `begin(const C&)`，不保证常量迭代器。
    - C++26：`initializer_list` 只保留 `rbegin`/`rend` 非成员重载，其余靠其新增的成员。
    - 新代码优先用 `std::ranges::` 中的同名定制点对象。
