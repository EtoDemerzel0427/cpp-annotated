---
title: 间接可调用要求与 projected
summary: 约束算法中谓词、比较器和投影的六个概念，以及把迭代器和投影合成一个新迭代器类型的 projected。
status: done
covers: *
since: c++20
papers: P0896R4, P2538R1, P2609R3
related: iterator.concepts, alg.req, concepts.callable, iterator.assoc.types, func.identity, defns.projection, basic.lookup.argdep
tags: 标准库, 迭代器, 概念, 投影, 谓词
updated: 2026-10-19
---

!!! tldr
    - 间接可调用概念检查的是可调用对象与迭代器解引用结果之间的关系，而不是与某个值类型的关系。
    - 每个概念都要求 `F` 可复制，以左值 `F&` 调用，并且同时接受两种实参：值类型的左值和 `*it` 的结果。
    - 所以对 `vector<bool>` 的谓词，只接 `bool&` 或只接代理类都不行；写 `const auto&` 或泛型 lambda 最稳妥。
    - `projected<I, Proj>` 是一个只用于约束的类型，它的引用类型是投影的结果，让算法能把先投影再比较写成一个约束。
    - 比较器不是严格弱序（例如用 `<=`）时只是满足而不建模，交给 `ranges::sort` 是 {{ifndr}}。

```cpp run title="indirect.cpp" ok
#include <algorithm>
#include <cassert>
#include <string>
#include <vector>

struct Person { std::string name; int age; };

int main() {
    std::vector<Person> v{{"bob", 30}, {"alice", 25}, {"carol", 35}};
    std::ranges::sort(v, std::ranges::less{}, &Person::age);   // 按 age 排序
    assert(v.front().name == "alice");

    auto it = std::ranges::find(v, "carol", &Person::name);    // 投影后比较
    assert(it != v.end() && it->age == 35);
}
```

C++20 的算法大多接受可调用对象，很多还接受**投影**（projection，[[defns.projection]]）：比较或判断之前先施加到每个元素上的变换，比如上面的 `&Person::age`。这一节定义约束这些参数的概念。

¶1 [indirectcallable.general] 只有一句话：下面这些概念汇集了接受可调用对象的算法的要求。名字里的间接（indirect）指的是，`F` 要能用在迭代器解引用之后的结果上。

## 六个概念 [indirectcallable.indirectinvocable]

¶1 六个概念的形状几乎一样，以一元的为例：

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

对普通迭代器，*`indirect-value-t<I>`* 就是 `iter_value_t<I>&`，值类型的左值（下一节给出完整定义）。`iter_reference_t<I>` 是 `*it` 的类型（[[iterator.assoc.types]]）。

| 概念 | 对 `F&` 的要求 | 例如谁在用 |
|---|---|---|
| `indirectly_unary_invocable<F, I>` | `invocable`，两种结果有公共引用 | `ranges::for_each` |
| `indirectly_regular_unary_invocable<F, I>` | `regular_invocable`，同上 | 投影（经由 `projected`） |
| `indirect_unary_predicate<F, I>` | `predicate` | `find_if`、`count_if`、`all_of` |
| `indirect_binary_predicate<F, I1, I2>` | 四种实参组合下都是 `predicate` | `adjacent_find`；经 `indirectly_comparable` 用于 `equal`、`search` |
| `indirect_equivalence_relation<F, I1, I2 = I1>` | 四种组合下都是 `equivalence_relation` | `unique`、`unique_copy` |
| `indirect_strict_weak_order<F, I1, I2 = I1>` | 四种组合下都是 `strict_weak_order` | `lower_bound`；经 `sortable` 用于 `sort` |

这些要求各有原因：

1. `copy_constructible<F>`：算法可以按值复制函数对象。
2. 以 `F&` 调用：算法内部持有一个具名的函数对象，反复调用它。只有 `operator() &&` 的函数对象不被接受。
3. 两种实参都要测：算法可能直接对 `*it` 调用，也可能先把元素复制成一个值再调用。`ranges::unique_copy` 处理输入迭代器时，就要把上一个元素存成 `iter_value_t` 对象，再与当前的 `*it` 比较。二元概念因此要测 2×2 = 4 种组合，让算法实现可以自由选择。

语义要求全部来自 [[concepts.callable]]：`predicate` 要保持相等性，`equivalence_relation` 要自反、对称、传递，`strict_weak_order` 要非自反、传递、不可比较关系也传递。`<=` 能通过语法检查，但不是严格弱序。

两种实参在大多数容器上是同一个类型，差别出现在代理迭代器上：

```cpp run ok
#include <iterator>
#include <vector>

using VB = std::vector<bool>::iterator;
// indirect-value-t<VB> 是 bool&，iter_reference_t<VB> 是代理类 vector<bool>::reference
struct A { bool operator()(bool&) const; };
struct B { bool operator()(std::vector<bool>::reference) const; };
struct C { bool operator()(const bool&) const; };

static_assert(!std::indirect_unary_predicate<A, VB>);   // 接不住代理
static_assert(!std::indirect_unary_predicate<B, VB>);   // 接不住 bool&
static_assert( std::indirect_unary_predicate<C, VB>);   // 代理能转换为 bool

int main() {}
```

`indirect_result_t<F, Is...>` 是配套的结果类型别名，即 `invoke_result_t<F, iter_reference_t<Is>...>`，要求每个 `Is` 可读，并且 `F` 能用它们的引用调用（[[iterator.synopsis]]）。

## `projected` [projected]

¶1 `projected` 把一个可读类型 `I` 和一个投影类型 `Proj` 组合成一个新的可读类型，它的引用类型是把 `Proj` 施加到 `iter_reference_t<I>` 上的结果：

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

`operator*` 只声明不定义，没有人会真的创建这种对象。它只用来写约束，例如：

```cpp
template<random_access_iterator I, sentinel_for<I> S,
         class Comp = ranges::less, class Proj = identity>
  requires sortable<I, Comp, Proj>   // 含 indirect_strict_weak_order<Comp, projected<I, Proj>>
constexpr I ranges::sort(I first, S last, Comp comp = {}, Proj proj = {});
```

比较器面对的不是 `I`，而是投影之后的 `projected<I, Proj>`，于是上一节的六个概念不用为投影另写一套。

`projected` 要求投影建模 `indirectly_regular_unary_invocable`，也就是保持相等性：同样的输入给出同样的输出。带随机数或计数器的投影只是满足语法而不建模。

`projected<int*, std::identity>` 的引用类型是 `int&`，`value_type` 是 `int`。

### 为什么套一层嵌套类

C++20 最初直接把 `projected<I, Proj>` 定义为类模板。问题出在实参依赖查找（ADL，[[basic.lookup.argdep]]）：以它为实参类型调用函数时，`I` 和 `Proj` 的关联命名空间和关联类都会被查找；如果其中某个是不完整类型，或者会触发硬错误的类模板，仅仅检查约束就可能出错。

C++23 改为别名，指向类模板的嵌套类 `projected-impl<I, Proj>::type`（[[P2538R1]]）。嵌套类所在的外围类模板的模板实参不再是它的关联实体，ADL 就看不到 `I` 和 `Proj` 了。

## *`indirect-value-t`* [indirectcallable.traits]

¶1 实现带投影的算法时，需要知道迭代器的值经过投影后是什么类型。*`indirect-value-t<T>`* 定义为：

- 如果 `T` 是 `projected<I, Proj>`，取 `invoke_result_t<Proj&, indirect-value-t<I>>`；
- 否则取 `iter_value_t<T>&`。

对投影过的迭代器，它递归地把投影施加到底层迭代器的值左值上，这正是算法先复制出一个值再投影时实际会得到的类型。

C++20 原先在这里直接用 `iter_value_t<T>&`。对 `projected<I, Proj>` 来说，那是投影结果去掉 cv 和引用之后的类型的左值；当投影返回代理或者不可复制的类型时，它与算法实际使用的类型不一致，一些正确的可调用对象会被拒绝。C++23 的 [[P2609R3]] 引入了 *`indirect-value-t`*，修正了这一点。`iter_common_reference_t<T>` 也随之改用它定义（[[iterator.synopsis]]）。

## 思考题

!!! question "思考题 1"
    下面的谓词为什么不满足 `indirect_unary_predicate<NeedsMutable, const int*>`，却满足 `indirect_unary_predicate<NeedsMutable, int*>`？
    ```cpp
    struct NeedsMutable { bool operator()(int&) const { return true; } };
    ```

<details markdown="1">
<summary>答案</summary>

对 `const int*`，*`indirect-value-t`* 是 `iter_value_t<const int*>&`，即 `int&`（值类型会去掉 const），而 `iter_reference_t` 是 `const int&`。`NeedsMutable` 接得住前者，接不住后者，所以不满足。对 `int*`，两者都是 `int&`。
</details>

!!! question "思考题 2"
    为什么二元概念要测四种组合，而不是只测 `(iter_reference_t<I1>, iter_reference_t<I2>)`？

<details markdown="1">
<summary>答案</summary>

算法可能把一侧的元素先存成值，再与另一侧的引用比较。`ranges::unique_copy` 对输入迭代器就是这样，比较器拿到的实参是（值的左值，引用）。概念要求所有组合都可用，并通过 `strict_weak_order` 等要求它们在语义上一致，算法实现就可以按需要选择其中任何一种。
</details>
