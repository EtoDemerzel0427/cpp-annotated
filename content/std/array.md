---
title: array
summary: std::array 是只含一个内置数组成员的聚合，它给内置数组加上值语义、容器接口和元组接口，行为几乎全部来自核心语言的聚合规则。
status: done
covers: *, array.syn
related: sequence.reqmts, container.requirements, container.requirements.general, dcl.init.aggr, temp.param, dcl.struct.bind, inplace.vector, views.contiguous
tags: 标准库, 容器, array, 聚合, 结构化类型
updated: 2026-10-19
---

!!! tldr
    - `array<T, N>` 是一个聚合，没有用户声明的构造函数；它的初始化、复制和平凡性都由核心语言的聚合规则决定，跟随 `T`。
    - 和其他容器不同，默认构造的 `array`（N > 0）不是空的，`size()` 恒为 N。
    - `array::swap` 逐个交换元素，是线性时间，可能抛异常，迭代器不会跟着元素换到另一个容器。
    - `array<T, 0>` 必须支持，此时 `begin() == end()`，`data()` 的返回值未指明。
    - `T` 是结构化类型时，`array<T, N>` 可以作为非类型模板形参的类型；`to_array` 可以让编译器数元素个数，同时指定元素类型。

`std::array<T, N>` 是对内置数组 `T[N]` 的薄包装。内置数组不能复制、不能按值传递和返回，一用就退化成指针；`array` 补上了这些值语义，同时提供容器接口和元组接口，而且没有额外开销。

## array 是聚合 [array.overview]

```cpp title="array-basics.cpp" run ok
#include <array>
#include <type_traits>

std::array<int, 3> a = {1, 2, 3};     // 省略内层花括号
std::array<int, 3> b = {{1, 2, 3}};   // 完整的花括号
std::array c{1, 2, 3};                // CTAD：array<int, 3>
auto d = std::to_array("abc");        // array<char, 4>
static_assert(std::is_same_v<decltype(d),
                             std::array<char, 4>>);
static_assert(std::is_aggregate_v<std::array<int, 3>>);
static_assert(
    std::is_trivially_copyable_v<std::array<int, 3>>);

template<std::array<int, 2> P>        // 结构化类型
int f() { return P[0] + P[1]; }

int main() {
  auto [x, y, z] = a;                 // 元组接口
  return f<{3, 4}>() - 7 + (x + y + z - 6)
       + (b[0] - 1) + (c[2] - 3);
}
```

¶2 `array` 是**聚合**（[[dcl.init.aggr]]），可以用最多 N 个能转换为 `T` 的元素进行列表初始化。它通常实现为只有一个 `T[N]` 成员的结构体。`{1, 2, 3}` 能直接初始化 `array<int, 3>`，靠的是聚合初始化的花括号省略（brace elision）：外层花括号对应 `array` 本身，内层对应 `T[N]` 成员，内层可以省略。

¶1 `array` 是连续容器，`array<T, N>` 存放 N 个 `T`，`size() == N` 是不变式。

¶3 `array` 满足容器和可逆容器的全部要求，只有一个例外：N > 0 时，默认构造的 `array` 不是空的。它只满足序列容器的一部分要求，因为不能插入和擦除；它也不是分配器感知容器。

¶4 如果 `T` 是结构化类型（[[temp.param]]），`array<T, N>` 也是结构化类型，因此可以作为非类型模板形参的类型。两个这样的模板实参等价，当且仅当对应元素两两等价。上例中的 `f<{3, 4}>()` 就用到了这一点。

¶5 `array` 的迭代器满足 constexpr 迭代器的要求。

## 复制与赋值来自隐式成员 [array.cons]

¶1 `array` 依靠隐式声明的特殊成员函数满足容器要求表。此外，隐式的移动构造函数和移动赋值运算符分别要求 `T` 满足 *Cpp17MoveConstructible* 和 *Cpp17MoveAssignable*。

所以 `array<T, N>` 的性质完全跟随 `T`：`T` 平凡可复制，`array` 也平凡可复制；`T` 不可复制，`array` 也不可复制。这些都不需要库写任何代码。

¶2 推导指引 `array(T, U...) -> array<T, 1 + sizeof...(U)>` 带有 *Mandates*：所有 `U` 都必须与 `T` 相同。

```cpp title="array-ctad-mandates.cpp" error
#include <array>
std::array e{1, 2.0};   // error: 元素类型不一致
```

Clang 报告 `no viable constructor or deduction guide for deduction of template arguments of 'std::array'`。标准把要求写成 *Mandates*，意思是选中这条推导指引后程序非良构；libc++ 则把它实现成推导指引上的约束，不满足时推导指引直接不参与重载决议。对这个例子两种做法都必须报错，只有在 SFINAE 语境里才能区分。

## 成员函数 [array.members]

- ¶1 `size()` 返回 N。
- ¶2 `data()` 返回的指针使 `[data(), data() + size())` 是有效区间；非空时 `data() == addressof(front())`。
- ¶3 `fill(u)` 如同 `fill_n(begin(), N, u)`。
- ¶4 `swap(y)` 等价于 `swap_ranges(begin(), end(), y.begin())`，异常规格是 `noexcept(is_nothrow_swappable_v<T>)`。

¶5 注 1 指出了 `array::swap` 与其他容器的区别：

!!! std
    Unlike the swap function for other containers, array::swap takes linear time, can exit via an exception, and does not cause iterators to become associated with the other container.

其他容器交换的是指向元素存储的内部指针，元素本身不动，迭代器跟着元素一起换到另一个容器（[[container.requirements.general#65]]）。`array` 的元素就在对象内部，只能逐个交换值，迭代器仍指向原来那个 `array` 的同一位置，位置上现在是对方原来的值。

## 非成员 swap [array.special]

¶1 非成员 `swap(x, y)` 的约束是 `N == 0 || is_swappable_v<T>`，¶2 效果如同 `x.swap(y)`，¶3 复杂度线性于 N。有了这个约束，元素不可交换的 `array` 不参与 `swap` 的重载决议，`is_swappable_v<array<T, N>>` 能如实反映这一点。

## 零大小的 array [array.zero]

核心语言不允许长度为 0 的数组（[[dcl.array]]），所以 `array<T, 0>` 不能简单地包一个 `T[0]`。标准仍然要求支持它：

- ¶1 必须支持 `N == 0` 的情况；
- ¶2 此时 `begin() == end()`，等于某个唯一的值，`data()` 的返回值未指明；
- ¶3 成员 `swap()` 必须有不抛出的异常规格。

!!! impl
    本机 libc++ 中 `sizeof(std::array<int, 0>)` 是 4。它在内部放了一个与 `T` 大小、对齐相同的占位成员，使对象大小不为 0，`data()` 也能返回一个对齐合适的指针。

## to_array [array.creation]

C++20 的 `to_array` 把内置数组转换成 `array<remove_cv_t<T>, N>`。左值版本 `to_array(T (&a)[N])` 复制每个元素，右值版本 `to_array(T (&&a)[N])` 移动每个元素（¶3、¶6）。两者都要求 `T` 本身不是数组类型，所以不支持多维数组（¶1、¶4）。

它的用处是让编译器数元素个数，同时还能指定元素类型。`std::to_array<long>({1, 2, 3})` 得到 `array<long, 3>`，CTAD 做不到这一点：CTAD 要么推导全部模板实参，要么全部显式写出。对字符串字面量，`to_array("abc")` 得到包含结尾空字符的 `array<char, 4>`。

## 元组接口 [array.tuple]

`tuple_size<array<T, N>>` 是 N，`tuple_element<I, array<T, N>>::type` 是 `T`，`get<I>` 返回第 I 个元素的引用；`tuple_element` 和 `get` 都要求 `I < N`（¶1–¶3）。所以 `array` 可以用于 `std::apply`、`std::tuple_cat`。

结构化绑定（[[dcl.struct.bind]]）发现 `tuple_size<array<…>>` 有定义，就按类元组的方式绑定，通过 `get<I>` 取元素，而不是直接绑定到数据成员。

## 与内置数组、inplace_vector、span 的比较

| | `T[N]` | `array<T, N>` | `inplace_vector<T, N>` | `span<T, N>` |
|---|---|---|---|---|
| 拥有元素 | 是 | 是 | 是 | 否 |
| 元素个数 | 恒为 N | 恒为 N | 0 到 N | 恒为 N |
| 能复制、比较、按值返回 | 否 | 是 | 是 | 浅复制 |
| 全部元素都已构造 | 是 | 是 | 只有前 `size()` 个 | 不适用 |
| `swap` 的复杂度 | 不适用 | 线性 | 线性 | 常数 |

`inplace_vector`（[[inplace.vector]]）是容量固定、大小可变的 `array`；`span`（[[views.contiguous]]）是对任意连续存储的非拥有视图。

## 思考题

!!! question "思考题"
    ```cpp
    std::array<std::string, 2> a;
    auto it = a.begin();
    std::array<std::string, 2> b{"x", "y"};
    a.swap(b);
    ```
    之后 `*it` 是什么？把两个 `array` 都换成 `std::vector<std::string>`（`a` 有两个空字符串）呢？

<details markdown="1">
<summary>答案</summary>

对 `array`，`*it` 是 `"x"`。`array::swap` 交换的是值（¶4），`it` 仍指向 `a[0]`，而 `a[0]` 现在持有原来 `b[0]` 的值。

对 `vector`，`*it` 是交换前 `a[0]` 的值，即空字符串，但 `it` 现在是 `b` 的迭代器。[[container.requirements.general#65]] 规定迭代器继续指向同一个元素，而这个元素已经随存储一起归 `b` 所有。
</details>

<details class="fine" markdown="1"><summary>其余条文</summary>

[array.syn] 中 `<array>` 头文件标为 mostly freestanding，`array` 本身标为 partially freestanding：会抛出异常的 `at()` 在独立实现中被删除（[[freestanding.item]]）。

</details>
