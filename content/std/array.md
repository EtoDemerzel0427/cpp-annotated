---
title: array
summary: std::array 是一个聚合——它如何满足容器要求却"默认构造不为空"、swap 为何线性且不让迭代器换容器、零大小数组的特殊规定、结构化类型与 NTTP、to_array、CTAD 的 Mandates，以及元组接口
status: done
covers: *, array.syn
related: sequence.reqmts, container.requirements, container.requirements.general, dcl.init.aggr, temp.param, dcl.struct.bind, inplace.vector, views.contiguous
tags: 标准库, 容器, array, 聚合, 结构化类型
updated: 2026-10-18
---

`std::array<T, N>` 是对内置数组 `T[N]` 的薄包装：一个只含一个 `T[N]` 成员的**聚合**。它给了内置数组值语义（能拷贝、能按值传递和返回、能比较）、容器接口和元组接口，同时不引入任何开销。理解它的关键是：几乎所有行为都由**核心语言的聚合规则**决定，而不是由库代码决定。

## 概述（[array.overview]）

¶1：`array` 是**连续容器**；`array<T, N>` 存储 N 个 `T`，`size() == N` 是不变式。

¶2：`array` 是**聚合**（[[dcl.init.aggr]]），可以用最多 N 个可转换为 `T` 的元素进行列表初始化。因为是聚合，它没有用户声明的构造函数，概要中写着"no explicit construct/copy/destroy for aggregate type"。

¶3：满足容器与可逆容器要求，**例外**是：默认构造的 `array`（N > 0 时）**不为空**。它只满足序列容器的**部分**要求（不能插入、擦除），也不是分配器感知容器。

¶4：若 `T` 是结构化类型，则 `array<T, N>` 是**结构化类型**（[[temp.param]]），因此可以作为非类型模板形参的类型；两个值模板实参等价当且仅当对应元素都模板实参等价。

¶5：迭代器满足 constexpr 迭代器要求。

`<array>` 头文件是"大部分 freestanding"的：`array` 本身部分 freestanding，只有会抛异常的 `at()` 被标为 *freestanding-deleted*（[[freestanding.item]]）。

```cpp title="array-basics.cpp" run ok
#include <array>
#include <type_traits>

std::array<int, 3> a = {1, 2, 3};          // 聚合初始化（花括号省略）
std::array<int, 3> b = {{1, 2, 3}};        // 完整的花括号形式
std::array c{1, 2, 3};                     // CTAD：array<int, 3>
auto d = std::to_array("abc");             // array<char, 4>
static_assert(std::is_same_v<decltype(d), std::array<char, 4>>);
static_assert(std::is_trivially_copyable_v<std::array<int, 3>>);
static_assert(std::is_aggregate_v<std::array<int, 3>>);

template<std::array<int, 2> P> int f() { return P[0] + P[1]; }   // 结构化类型：可作 NTTP

int main() {
  auto [x, y, z] = a;                      // 元组接口 → 结构化绑定
  return f<{3, 4}>() - 7 + (x + y + z - 6) + (b[0] - 1) + (c[2] - 3);
}
```

`{1, 2, 3}` 能直接初始化 `array<int, 3>`，靠的是聚合初始化的**花括号省略**（brace elision，[[dcl.init.aggr]]）：外层花括号对应 `array` 本身，内层对应 `T[N]` 成员，内层可以省略。

## 构造、复制与赋值（[array.cons]）

¶1：`array` 依靠**隐式声明**的特殊成员函数满足容器要求表；此外，隐式声明的移动构造函数和移动赋值运算符分别要求 `T` 是 *Cpp17MoveConstructible* / *Cpp17MoveAssignable*。

因此 `array<T, N>` 的平凡性完全继承自 `T`：`T` 平凡可复制则 `array` 平凡可复制，`T` 不可复制则 `array` 不可复制——不需要任何库代码。

¶2 推导指引 `array(T, U...) -> array<T, 1 + sizeof...(U)>` 的 *Mandates*：`(is_same_v<T, U> && ...)`。

```cpp title="array-ctad-mandates.cpp" error
#include <array>
std::array e{1, 2.0};    // error: Mandates (is_same_v<T, U> && ...)
```

标准把它写成 *Mandates*（选中后报错），libc++ 实际上把它实现成了推导指引上的约束：clang 报告 `no viable constructor or deduction guide for deduction of template arguments of 'std::array'`。两种做法对这个例子都是"非良构、必须诊断"，但在 SFINAE 语境下可以区分。

## 成员函数（[array.members]）

- `size()` 返回 N（¶1）——它是 `constexpr` 的，并且不需要读 `*this`。
- `data()` 返回的指针使 `[data(), data() + size())` 是有效区间；非空时 `data() == addressof(front())`（¶2）。
- `fill(u)` 如同 `fill_n(begin(), N, u)`（¶3）。
- `swap(y)` 等价于 `swap_ranges(begin(), end(), y.begin())`，`noexcept(is_nothrow_swappable_v<T>)`（¶4）。

!!! std
    Unlike the swap function for other containers, array::swap takes linear time, can exit via an exception, and does not cause iterators to become associated with the other container.

    与其他容器的 swap 不同，array::swap 是线性时间、可能以异常退出，并且不会让迭代器转而关联到另一个容器。

¶5 这条注把 `array` 和 [[container.requirements.general]] ¶65 的一般 `swap` 语义区分开：其他容器交换的是"内部指针"，迭代器跟着元素走到另一个容器；`array` 的元素就在对象内部，交换的是**值**，迭代器仍指向原 `array` 的同一位置——位置上现在是对方原来的值。

## 特化的算法与零大小数组（[array.special]、[array.zero]）

- 非成员 `swap(x, y)`：*Constraints* 为 `N == 0 || is_swappable_v<T>`（¶1），线性（¶3）。所以不可交换元素的 `array` 不参与 `swap` 重载决议，`is_swappable_v<array<T, N>>` 能正确反映这一点。
- [array.zero] ¶1：必须支持 `N == 0`。¶2：此时 `begin() == end() ==` 某个唯一值，`data()` 的返回值未指明。¶3：成员 `swap()` 必须有不抛出的异常规格。

零大小数组在核心语言中是非良构的（数组边界必须大于零，[[dcl.array]]），所以 `array<T, 0>` 不能简单地包一个 `T[0]`。{{impl}} 本机 libc++ 中 `sizeof(std::array<int, 0>) == 4`——它内部放了一个与 `T` 同大小、同对齐的占位成员，以保证对象有非零大小并让 `data()` 能返回一个"合适对齐"的指针。

## 创建函数 `to_array`（[array.creation]）

`to_array(T (&a)[N])` 与 `to_array(T (&&a)[N])`（C++20）把内置数组转成 `array<remove_cv_t<T>, N>`：

- *Mandates*：`T` 不是数组类型（多维数组不支持），且 `remove_cv_t<T>` 可从 `T&`（左值版）或 `T`（右值版）构造（¶1、¶4）；
- 左值版拷贝每个元素，右值版移动每个元素（¶3、¶6）。

`to_array` 的价值在于"让编译器数元素个数"并且能指定元素类型：`std::to_array<long>({1, 2, 3})` 得到 `array<long, 3>`，这是 CTAD 做不到的（CTAD 要么全部推导、要么全部指定）。对字符串字面量，`to_array("abc")` 得到含结尾空字符的 `array<char, 4>`。

## 元组接口（[array.tuple]）

`tuple_size<array<T, N>>` 为 N；`tuple_element<I, array<T, N>>::type` 为 `T`，`get<I>` 的四个重载返回对应引用；`tuple_element` 与 `get` 都有 *Mandates* `I < N`（¶1–¶3）。这使 `array` 能用于 `std::apply`、`std::tuple_cat`，以及结构化绑定（[[dcl.struct.bind]]——严格说，`array` 作为只有一个公开数组成员的聚合，其结构化绑定走的是"类似元组"的路径，因为 `tuple_size<array<…>>` 已特化）。

## 与内置数组、`inplace_vector`、`span` 的关系

| | `T[N]` | `array<T, N>` | `inplace_vector<T, N>` | `span<T, N>` |
|---|---|---|---|---|
| 拥有元素 | 是 | 是 | 是 | 否 |
| 元素个数 | 恒为 N | 恒为 N | 0…N 可变 | 恒为 N |
| 值语义（拷贝/比较/返回） | 否（退化为指针） | 是 | 是 | 浅拷贝 |
| 所有元素都已构造 | 是 | 是 | 只有前 `size()` 个 | — |
| 移动/`swap` 复杂度 | — | 线性 | 线性 | 常数 |

`inplace_vector`（[[inplace.vector]]）是"容量固定、大小可变"的 `array`；`span`（[[views.contiguous]]）则是对任意连续存储的非拥有视图。

## 思考题

!!! question "`std::array<std::string, 2> a; auto it = a.begin(); std::array<std::string, 2> b{"x", "y"}; a.swap(b);` 之后 `*it` 是什么？把 `a` 换成 `std::vector<std::string> a(2)`、`b` 换成同类型的 `{"x", "y"}` 呢？"

<details markdown="1">
<summary>展开查看答案与解析</summary>

对 `array`：`*it` 是 `"x"`。`array::swap` 交换的是值（¶4 的 `swap_ranges`），`it` 仍指向 `a[0]`，而 `a[0]` 现在持有原来 `b[0]` 的值（¶5 注）。对 `vector`：`*it` 是交换前 `a[0]` 的值（一个空字符串），但 `it` 现在是 **`b` 的**迭代器——[[container.requirements.general]] ¶65 规定迭代器继续指向同一元素，而该元素已随缓冲区一起归 `b` 所有。
</details>

## 小结

- `array` 是聚合：初始化、平凡性、可复制性全部来自核心语言规则；默认构造的 `array` 不为空。
- `swap` 线性、可能抛出、交换值而不转移迭代器；零大小特化的 `swap` 必须 `noexcept`。
- `array<T, 0>` 被强制支持；`begin() == end()`，`data()` 未指明。
- 若 `T` 是结构化类型，`array<T, N>` 可作非类型模板实参；`to_array` 让编译器数元素个数；元组接口支持结构化绑定。
