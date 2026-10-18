---
title: 间接可调用要求与 projected
summary: 约束"接受函数对象的算法"的六个概念——indirectly_unary_invocable、indirectly_regular_unary_invocable、indirect_unary_predicate、indirect_binary_predicate、indirect_equivalence_relation、indirect_strict_weak_order；它们要求可调用对象同时能接受 indirect-value-t<I>（值的左值）与 iter_reference_t<I>；projected<I, Proj> 把"迭代器 + 投影"打包成新的 indirectly_readable 类型，C++23 起经 projected-impl 防止 ADL 污染，indirect-value-t 让投影链上的值类型正确传递。
status: done
covers: *
since: c++20
papers: P0896R4
related: iterator.concepts, alg.req, concepts.callable, iterator.assoc.types, func.identity, defns.projection, basic.lookup.argdep
tags: 标准库, 迭代器, 概念, 投影, 谓词
updated: 2026-10-18
---

`std::ranges::find_if(r, pred)`、`ranges::sort(r, comp, proj)`——C++20 的算法几乎都接受可调用对象，很多还接受**投影**（*projection*，[[defns.projection]]：在比较/判断前先对元素施加的变换）。[indirectcallable] 定义用来约束这些参数的概念。

"间接"（*indirect*）一词的意思是：约束对象不是可调用对象 `F` 与某个**值类型**的关系，而是 `F` 与某个**迭代器**（更准确地说，`indirectly_readable` 类型）**解引用后**的关系。

¶1 of [indirectcallable.general] 只有一句：有若干概念把"接受可调用对象作为参数的算法"的要求组合起来。

## *`indirect-value-t`*（[indirectcallable.traits]）

¶1 定义说明专用别名 *`indirect-value-t<T>`*：

- 若 `T` 是 `projected<I, Proj>`：`invoke_result_t<Proj&, indirect-value-t<I>>`；
- 否则：`iter_value_t<T>&`。

也就是说，对普通迭代器它就是"值类型的左值引用"；对投影过的迭代器，它**递归地**把投影施加到底层迭代器的 *`indirect-value-t`* 上。这个别名是 C++23 期间加入的修正：C++20 原始设计对投影迭代器直接检查 `iter_value_t<projected<I, Proj>>&`，即"投影结果去 cvref 之后的值"的左值；而算法实际可能做的是把投影施加到底层元素的**值**上。当投影返回引用、代理或只能移动的类型时，两者类型不同，一些完全正确的可调用对象会被拒绝。*`indirect-value-t`* 让概念检查的正是算法实际会使用的那个类型。

`iter_common_reference_t<T>` 也用它定义：`common_reference_t<iter_reference_t<T>, indirect-value-t<T>>`（[[iterator.synopsis]]）。

## 六个间接可调用概念（[indirectcallable.indirectinvocable]）

它们的形状高度一致，以一元为例：

```cpp
template<class F, class I>
concept indirectly_unary_invocable =
  indirectly_readable<I> &&
  copy_constructible<F> &&
  invocable<F&, indirect-value-t<I>> &&
  invocable<F&, iter_reference_t<I>> &&
  common_reference_with<
    invoke_result_t<F&, indirect-value-t<I>>,
    invoke_result_t<F&, iter_reference_t<I>>>;
```

| 概念 | 对 `F&` 的要求（以 `indirect-value-t` 与 `iter_reference_t` 两种实参） | 典型使用者 |
|---|---|---|
| `indirectly_unary_invocable<F, I>` | `invocable`，两种结果有公共引用 | `ranges::for_each` |
| `indirectly_regular_unary_invocable<F, I>` | `regular_invocable`（保持相等性），同上 | 投影 `Proj`、`views::transform` 的函数 |
| `indirect_unary_predicate<F, I>` | `predicate` | `find_if`、`count_if`、`all_of` |
| `indirect_binary_predicate<F, I1, I2>` | 四种实参组合下都是 `predicate` | `find_first_of`、`equal` 经 `indirectly_comparable` |
| `indirect_equivalence_relation<F, I1, I2 = I1>` | 四种组合下都是 `equivalence_relation` | `unique`、`adjacent_find` |
| `indirect_strict_weak_order<F, I1, I2 = I1>` | 四种组合下都是 `strict_weak_order` | `sort`、`lower_bound` 经 `sortable` 等 |

三个共同点：

1. **都要求 `copy_constructible<F>`**——算法可以按值复制函数对象；
2. **都以 `F&`（左值）调用**——算法内部持有一个具名的函数对象并反复调用它，所以对右值才能调用的 `operator() &&` 不被接受；
3. **都同时测试两种实参**：值的左值 `indirect-value-t<I>`（算法可能把元素复制成临时值，再拿临时值去调用——例如 `unique_copy` 对输入迭代器）与引用 `iter_reference_t<I>`（直接对 `*it` 调用）。二元版本则测试 2×2 = 4 种组合。

这些概念的**语义**要求全部继承自 [[concepts.callable]]：`predicate`、`equivalence_relation`、`strict_weak_order` 各自的数学性质（例如严格弱序要求非自反、传递、不可比较关系传递）。给 `ranges::sort` 传一个满足语法但不是严格弱序的比较器（典型如 `<=`）是 {{ifndr}}（[[res.on.requirements]]）。

`indirect_result_t<F, Is...>` 是配套的结果类型别名：`invoke_result_t<F, iter_reference_t<Is>...>`，要求每个 `Is` 可读且 `F` 可以用它们的引用调用。

## `projected`（[projected]）

¶1：`projected` 把一个 `indirectly_readable` 类型 `I` 与可调用类型 `Proj` 组合成一个**新的** `indirectly_readable` 类型，其引用类型是把 `Proj` 施加到 `iter_reference_t<I>` 的结果。

```cpp
template<class I, class Proj>
struct projected-impl {
  struct type {
    using value_type = remove_cvref_t<indirect_result_t<Proj&, I>>;
    using difference_type = iter_difference_t<I>;   // 仅当 I 建模 weakly_incrementable
    indirect_result_t<Proj&, I> operator*() const;   // 不定义
  };
};

template<indirectly_readable I, indirectly_regular_unary_invocable<I> Proj>
  using projected = projected-impl<I, Proj>::type;
```

`projected` 是一个**纯类型层面的工具**：`operator*` 只声明不定义，没人会真的创建这种迭代器。它的唯一用途是让算法把"先投影再比较"写成一个组合约束：

```cpp
template<random_access_iterator I, sentinel_for<I> S,
         class Comp = ranges::less, class Proj = identity>
  requires sortable<I, Comp, Proj>     // 其中含 indirect_strict_weak_order<Comp, projected<I, Proj>>
constexpr I ranges::sort(I first, S last, Comp comp = {}, Proj proj = {});
```

!!! note "为什么要包一层 *`projected-impl`*"
    C++20 原先把 `projected` 定义为类模板 `projected<I, Proj>` 本身。问题在于 ADL：以 `projected<I, Proj>` 为实参类型时，`I` 与 `Proj` 的关联命名空间和关联类都会参与查找——若 `I` 或 `Proj` 是不完整类型，或关联了"会引发硬错误的"类模板，单是检查约束就可能出错。改为"别名指向一个嵌套类 `projected-impl<I, Proj>::type`"后，嵌套类的模板实参不再是它的关联实体（[[basic.lookup.argdep]]），ADL 被隔离。这一改动是 C++23 期间以提案形式完成的。

## 例子

```cpp run title="indirect.cpp" ok
#include <algorithm>
#include <cassert>
#include <iterator>
#include <string>
#include <vector>

struct Person { std::string name; int age; };

// 只接受非 const 左值引用的谓词
struct NeedsMutable { bool operator()(int&) const { return true; } };
static_assert(std::indirect_unary_predicate<NeedsMutable, int*>);
// const int* 的 iter_reference_t 是 const int&，iter_value_t<...>& 是 int&：
// 前者调用不了 → 不满足
static_assert(!std::indirect_unary_predicate<NeedsMutable, const int*>);

int main() {
    std::vector<Person> v{{"bob", 30}, {"alice", 25}, {"carol", 35}};
    // 投影：按 age 排序；comp 实际作用于 projected<vector<Person>::iterator, int Person::*>
    std::ranges::sort(v, std::ranges::less{}, &Person::age);
    assert(v.front().name == "alice");

    auto it = std::ranges::find(v, "carol", &Person::name);   // 投影后与 "carol" 比较
    assert(it != v.end() && it->age == 35);
}
```

## 常见误区

!!! pitfall "谓词只能接受引用、不能接受值（或反之）"
    概念同时测试 `indirect-value-t<I>`（`iter_value_t<I>&`）和 `iter_reference_t<I>`。对普通容器二者常常相同；但对代理迭代器或 `const` 迭代器，二者不同。例如对 `vector<bool>::iterator`，`indirect-value-t` 是 `bool&`，`iter_reference_t` 是代理类 `vector<bool>::reference`：只写 `bool operator()(bool&)` 的谓词接不住代理，只写 `operator()(std::vector<bool>::reference)` 的谓词接不住 `bool&`——两者都不满足 `indirect_unary_predicate`。请用 `const auto&` 或泛型 lambda。

!!! pitfall "投影必须是 `regular_invocable`"
    `projected` 要求 `Proj` 建模 `indirectly_regular_unary_invocable`：投影必须保持相等性——同样的输入给出同样的输出，且不能修改实参。带随机数、带计数器的"投影"只是满足语法，不建模概念。

## 思考题

!!! question "思考题"
    1. 为什么二元概念要测试四种组合，而不是只测试 `(iter_reference_t<I1>, iter_reference_t<I2>)`？
    2. `projected<int*, std::identity>` 的 `value_type` 是什么？`iter_reference_t` 是什么？

<details markdown="1">
<summary>展开查看答案与解析</summary>

1. 算法可能把一侧的元素先存成值，再与另一侧的引用比较。例如 `ranges::unique_copy` 对输入迭代器要把"上一个元素"存为 `iter_value_t` 的临时对象，再与 `*it` 比较，于是比较器的实参是 (值的左值, 引用)。为了让算法实现有选择的自由，概念要求所有组合都可用，且（经 `strict_weak_order` 等）语义一致。
2. `identity` 对 `int&` 返回 `int&`，所以 `iter_reference_t` 是 `int&`，`value_type` 是 `remove_cvref_t<int&>` 即 `int`。
</details>

## 小结

!!! summary
    - 六个间接可调用概念 = `indirectly_readable` + 可复制的 `F` + `F&` 能以值左值与引用两种形式调用 + 对应的可调用概念（invocable/predicate/relation/strict_weak_order）。
    - *`indirect-value-t`* 在投影链上递归传递"值左值上的投影结果"（C++23 期间的修正）。
    - `projected<I, Proj>` 是只用于约束的类型：引用类型 = 投影结果；经 *`projected-impl`* 嵌套类隔离 ADL。
    - 语义要求全部继承自 [concepts.callable]；比较器不是严格弱序即 IFNDR。
