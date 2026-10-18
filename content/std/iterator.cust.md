---
title: ranges::iter_move 与 ranges::iter_swap
summary: 两个迭代器定制点对象——iter_move(E) 先找 ADL 定制，否则对左值 *E 做 std::move、对纯右值原样返回，结果必须等于 *E；iter_swap(E1, E2) 先找 ADL 定制（用删除的毒丸模板屏蔽 std::iter_swap），否则 ranges::swap(*E1, *E2)，再否则借 iter-exchange-move 三次移动；它们是代理迭代器（zip、vector<bool>）能被泛型算法正确移动与交换的关键。
status: done
covers: *
since: c++20
papers: P0896R4
related: iterator.assoc.types, iterator.concept.readable, alg.req, customization.point.object, concept.swappable, basic.lookup.argdep, temp.func.order, reverse.iterators, move.iterators
tags: 标准库, 迭代器, CPO, 代理迭代器, ADL
updated: 2026-10-18
---

泛型算法要移动一个元素，C++11 的写法是 `T tmp = std::move(*it);`。这对 `vector<int>::iterator` 没问题，但对**代理迭代器**——`*it` 返回的是一个临时"引用对象"而不是真引用，例如 `vector<bool>::iterator`、`views::zip` 的迭代器——`std::move(*it)` 只是把那个代理对象变成右值，根本没有移动底层元素。交换也一样：`std::swap(*a, *b)` 交换的是两个临时代理。

C++20 的解决方案是把"从迭代器移出元素"和"交换两个迭代器所指元素"变成两个**可定制**的操作：`ranges::iter_move` 和 `ranges::iter_swap`。它们是**定制点对象**（[[customization.point.object]]）：函数对象，先尝试用户经 ADL 提供的定制，否则退回合理的默认实现。

它们的结果类型参与定义迭代器的关联类型：`iter_rvalue_reference_t<I>` 就是 `decltype(ranges::iter_move(declval<I&>()))`，而 `indirectly_readable` 要求 `iter_reference_t` 与 `iter_rvalue_reference_t` 有公共引用（[[iterator.concept.readable]]）。

## `ranges::iter_move`（[iterator.cust.move]）

¶1：对子表达式 `E`，`ranges::iter_move(E)` [[g:expression-equivalent]]于：

1. **（1.1）ADL 定制**：若 `E` 是类或枚举类型，且把 `iter_move(E)` 作为不求值操作数时良构——其中名字 `iter_move` **只经实参依赖查找**（[[basic.lookup.argdep]]）确定——则为 `iter_move(E)`。
2. **（1.2）默认**：否则若 `*E` 良构：
    - `*E` 是左值 → `std::move(*E)`；
    - 否则（`*E` 是纯右值或亡值）→ `*E`。
3. **（1.3）**否则非良构；注 1 提示这种情况在模板实例化的直接语境中会导致替换失败——也就是说 `ranges::iter_move` 对不可解引用的类型是 SFINAE 友好的。

"只经 ADL"意味着普通的非限定查找被排除：你在全局写一个 `iter_move` 模板不会被 `ranges::iter_move` 捡到，只有与 `E` 的类型关联的命名空间（或隐藏友元）里的声明才算。

¶2 是一条语义红线：

!!! std
    If ranges::iter_move(E) is not equal to *E, the program is ill-formed, no diagnostic required.

    如果 `ranges::iter_move(E)` 与 `*E` 不**相等**，程序 {{ifndr}}。

定制 `iter_move` 只能改变"怎么拿出来"（移动 vs 复制、返回什么类型），不能改变"拿出来的值是什么"。

!!! impl "libc++ 的实现"
    libc++ 在 `ranges::__iter_move` 命名空间里声明 `void iter_move() = delete;`，然后用三个互斥的概念 `__unqualified_iter_move`、`__move_deref`、`__just_deref` 对应 (1.1)、(1.2) 的两支，各配一个 `operator()` 重载。那个删除的无参声明是"毒丸"：它让该命名空间内的非限定查找找到一个不可用的声明，从而阻止查找继续向外找到其他 `iter_move`，实际效果就是"只剩 ADL"。

## `ranges::iter_swap`（[iterator.cust.swap]）

¶1：`ranges::iter_swap` 交换其实参所指的值（"交换值"的含义见 [[concept.swappable]]）。

### *`iter-exchange-move`*（¶2–¶3）

说明专用函数模板 *`iter-exchange-move(x, y)`*：

```cpp
iter_value_t<X> old_value(iter_move(x));
*x = iter_move(y);
return old_value;
```

即"把 `*x` 移出存到临时值，把 `*y` 移入 `*x`，返回旧值"。它的 `noexcept` 由这两步的 `noexcept` 决定。

### 四个分支（¶4）

`ranges::iter_swap(E1, E2)` 表达式等价于：

1. **（4.1）ADL 定制**：若 `E1` 或 `E2` 是类或枚举类型，且 `iter_swap(E1, E2)` 良构——重载决议所在语境**包含**声明 `template<class I1, class I2> void iter_swap(I1, I2) = delete;`、且**不包含** `ranges::iter_swap` 自身——则为 `(void)iter_swap(E1, E2)`。若选中的函数并不交换两者所指的值，程序 {{ifndr}}。
2. **（4.2）**否则，若两者类型都建模 `indirectly_readable`，且其引用类型建模 `swappable_with`，则为 `ranges::swap(*E1, *E2)`。
3. **（4.3）**否则，若 `T1`、`T2` 互相建模 `indirectly_movable_storable`（[[alg.req]]），则为 `(void)(*E1 = iter-exchange-move(E2, E1))`，但 `E1` 只求值一次。
4. **（4.4）**否则非良构（同样 SFINAE 友好）。

!!! note "注 1：毒丸为什么是两参数的模板"
    (4.1) 中那个删除的 `iter_swap(I1, I2)` 是**无约束、按值**的函数模板，与 `std::iter_swap(ForwardIt1, ForwardIt2)` 的形状相同。若用户的迭代器类型关联命名空间 `std`（比如它是 `std::vector<MyType>::iterator`，或模板实参来自 `std`），ADL 会找到无约束的 `std::iter_swap`；毒丸与之同样匹配，重载决议因歧义失败——于是 (4.1) 不成立，转入 (4.2)。注 1 指出，这也意味着**用户定制必须比毒丸更特化**（[[temp.func.order]]）才能被选中：写成非模板的隐藏友元，或参数有具体类型的模板，都满足这一点。

## 例子：一个"zip"式代理迭代器

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
    // 隐藏友元定制：只能经 ADL 找到
    friend std::pair<int, int> iter_move(const It& i) { return {*i.a, *i.b}; }
    friend void iter_swap(const It& x, const It& y) {
        std::swap(*x.a, *y.a);
        std::swap(*x.b, *y.b);
    }
};
}

static_assert(std::same_as<std::iter_rvalue_reference_t<lib::It>, std::pair<int, int>>);
static_assert(std::same_as<std::iter_rvalue_reference_t<int*>, int&&>);

int main() {
    int a[]{1, 2}, b[]{3, 4};
    lib::It x{a, b}, y{a + 1, b + 1};
    std::ranges::iter_swap(x, y);           // 经 (4.1) 调用隐藏友元
    assert(a[0] == 2 && a[1] == 1 && b[0] == 4 && b[1] == 3);
}
```

若不提供这两个定制会怎样？`It` 仍然是 `indirectly_readable`——`Ref` 能转换为 `pair<int,int>`，`common_reference_t<Ref&&, pair<int,int>&>` 经条件表达式规则得到 `pair<int,int>`，公共引用要求成立。但：

- `ranges::iter_move(x)` 走 (1.2) 第二支，返回 `Ref` 纯右值本身——"移出"的只是一个指向原元素的代理，算法里 `iter_value_t<I> tmp(ranges::iter_move(it));` 得到的是复制而非移动；对 `pair<std::string, std::string>` 这类元素，这就是性能乃至语义上的差别；
- `ranges::iter_swap(x, y)` 三个分支全部落空：`Ref` 纯右值不是 `swappable_with` 的（不能对两个右值调用 `ranges::swap`），(4.3) 要求 `*E1 = ...` 能写入，而 `Ref` 没有赋值运算符——所以 `indirectly_swappable<It>` 为假，`ranges::sort` 等需要 `permutable` 的算法直接拒绝它。

这就是代理迭代器必须定制这两个操作（并让代理可以赋值）的原因。

标准库的 `vector<bool>::iterator` 则是"不定制"路线的样本：`*it` 返回 `vector<bool>::reference` 纯右值，`ranges::iter_move(it)` 就是那个代理本身（`iter_rvalue_reference_t` 为 `vector<bool>::reference`）；`common_reference_t<vector<bool>::reference, bool&>` 同样经条件表达式规则得到 `bool`。它能被交换，是因为该代理类型可赋值、且库为它提供了 `swap` 重载。

## 适配器如何转发

迭代器适配器都以隐藏友元的形式提供 `iter_move`/`iter_swap`，把操作转发给底层迭代器，使定制能够"穿透"包装：

- `reverse_iterator`：先复制底层迭代器再 `--`，然后调用 `ranges::iter_move`（[[reverse.iterators]]）；
- `move_iterator`、`counted_iterator`、`common_iterator`、`basic_const_iterator`：直接转发（[[move.iterators]]、[[iterators.counted]]、[[iterators.common]]、[[const.iterators]]）。

## 常见误区

!!! pitfall "在算法里写 `std::move(*it)`"
    在泛型代码里，从迭代器移出元素应写 `ranges::iter_move(it)`，交换应写 `ranges::iter_swap(a, b)`，而不是 `std::move(*it)`、`std::swap(*a, *b)` 或 `std::iter_swap(a, b)`。后三者对代理迭代器要么无效、要么编译不过。这也是为什么 `std::ranges::sort` 能排序 `views::zip(a, b)`，而 `std::sort` 不能。

!!! pitfall "用无约束模板做定制"
    ```cpp
    namespace mine {
        template<class I> void iter_swap(I a, I b);   // 与毒丸一样不特化，可能导致歧义
    }
    ```
    这样的定制在关联到 `std` 的迭代器上会与毒丸构成歧义而落空。按 (4.1) 注 1 的建议，写成具体类型的隐藏友元。

## 思考题

!!! question "思考题"
    1. 对 `int* p`，`ranges::iter_move(p)` 与 `ranges::iter_move(std::move(p))` 的类型分别是什么？
    2. 一个类型的 `operator*` 返回 `std::string&&`（亡值），`iter_rvalue_reference_t` 是什么？
    3. 为什么 (4.1) 要求 `E1` 或 `E2` 是类或枚举类型？

<details markdown="1">
<summary>展开查看答案与解析</summary>

1. 都是 `int&&`。`int*` 不是类类型，(1.1) 不适用；`*p` 是左值，取 `std::move(*p)`。`E` 自身的值类别不影响 `*E` 的值类别。
2. `std::string&&`：`*E` 不是左值，(1.2) 第二支直接返回 `*E`，`decltype` 得 `std::string&&`。
3. 对标量类型（指针）没有关联类，ADL 找不到任何用户定制，不必尝试；而且对指针也不应允许用户劫持交换语义。这一限制与 `ranges::swap` 的同类规定一致（[[concept.swappable]]）。
</details>

## 小结

!!! summary
    - `iter_move(E)`：ADL 定制 → 左值 `*E` 时 `std::move(*E)` → 否则 `*E`；结果必须与 `*E` 相等，否则 IFNDR。
    - `iter_swap(E1, E2)`：ADL 定制（毒丸屏蔽无约束的 `std::iter_swap`）→ `ranges::swap(*E1, *E2)` → 经 *`iter-exchange-move`* 三次移动；定制必须真的交换值。
    - `iter_rvalue_reference_t` 由 `iter_move` 定义；代理迭代器靠这两个定制与 `basic_common_reference` 融入概念体系。
    - 适配器以隐藏友元转发两者，使定制穿透包装。
