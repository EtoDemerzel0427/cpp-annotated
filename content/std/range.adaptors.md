---
title: 范围适配器总论
summary: 范围适配器对象、范围适配器闭包对象与管道运算符 | 的精确规则（C(R) ≡ R | C；C | D 产生调用模式为 d(c(arg)) 的完美转发包装器；adaptor(args...) 按值绑定实参）；C++23 range_adaptor_closure 让用户适配器加入管道及其 UB 边界；movable-box 与 non-propagating-cache 两个说明用组件为何存在；惰性求值的代价模型。
status: done
covers: range.adaptors.general, range.adaptor.object, range.move.wrap, range.nonprop.cache, range.adaptor.helpers
since: c++20
papers: P0896R4, P2387R3, P2494R2
related: ranges, range.all, range.view, range.filter, range.transform, range.utility.conv, customization.point.object, func.require, concepts.object, optional
tags: 标准库, 范围, 适配器, 管道, range_adaptor_closure
updated: 2026-10-18
---

[range.adaptors] 是本章最大的子条款，下面挂着三十多种视图。本页讲它们共用的"语法与基础设施"：适配器对象怎样被调用、`|` 怎样组合、闭包对象如何按值保存实参，以及两个反复出现的说明用类模板。各个视图分页讲解（见文末索引）。

## 什么是范围适配器（[range.adaptors.general]）

¶1 **范围适配器**（range adaptor，[[g:range-adaptor]]）是把一个范围变换成具有自定义行为的视图的工具。它们可以串联成管道，**在结果视图被迭代时惰性求值**。¶2 声明在 `std::ranges::views`（别名 `std::views`）中。¶3 按位或运算符被重载用于构造适配器链；适配器也支持语义等价的函数调用语法。¶4 例 1：

```cpp
for (int i : ints | views::filter(even) | views::transform(square)) ...
assert(ranges::equal(ints | views::filter(even), views::filter(ints, even)));
```

## 适配器对象与闭包对象（[range.adaptor.object]）

### 闭包对象与 `|`（¶1）

**范围适配器闭包对象**（range adaptor closure object，[[g:range-adaptor-closure-object]]）是接受一个范围实参的一元函数对象。对闭包对象 `C` 与满足 `range` 的表达式 `R`，下面两个表达式等价：

```cpp
C(R)
R | C
```

给定另一个闭包对象 `D`，`C | D` 产生一个新的闭包对象 `E`，它是一个**完美转发调用包装器**（[[func.require]]）：

- ¶1.1 目标对象是 `decay_t<decltype((D))>` 类型的 `d`，用 `D` 直接非列表初始化；
- ¶1.2 一个绑定实参实体：`decay_t<decltype((C))>` 类型的 `c`，用 `C` 直接非列表初始化；
- ¶1.3 调用模式为 `d(c(arg))`。

`C | D` 良构当且仅当这些状态实体的初始化都良构。

!!! std
    The expression C | D produces another range adaptor closure object E. ... Its call pattern is d(c(arg))

    `C | D` 产生另一个闭包对象 E，调用 E(arg) 等于 d(c(arg))。

几个推论：

- **`|` 左结合**：`r | C | D` 是 `(r | C) | D`，先产生视图再适配；而 `C | D` 单独出现时产生一个"待用的管道"，可以存成变量反复使用。二者结果相同。
- **闭包对象按值保存**（`decay_t`）：`auto p = views::filter(pred) | views::transform(f);` 把 `pred` 和 `f` 都**复制**进 `p`。若谓词按引用捕获了局部变量，`p` 比那个局部变量活得久就会悬垂。
- **完美转发调用包装器**：调用 `E` 时，`E` 自身的值类别会转发到 `c` 和 `d` 上（左值包装器以左值调用，右值包装器以右值调用）。

### 用户自定义闭包：`range_adaptor_closure`（¶2–¶5）{{c++23}}

C++20 里用户写的函数对象无法参与 `|`——`operator|` 的实现细节没有公开。C++23（[[P2387R3]]）提供了一个 CRTP 基类：

```cpp
template<class D>
  requires is_class_v<D> && same_as<D, remove_cv_t<D>>
class range_adaptor_closure { };
```

¶2 给定 `T` 类型的对象 `t`，若

- ¶2.1 `t` 是接受一个范围实参的一元函数对象，
- ¶2.2 `T` 建模 `derived_from<range_adaptor_closure<T>>`，
- ¶2.3 `T` 没有其他 `range_adaptor_closure<U>` 基类，且
- ¶2.4 `T` 不建模 `range`，

则实现保证 `t` 是一个范围适配器闭包对象——也就是说，它能用于 `r | t` 与 `t | other`。

¶3–¶5 是三条 UB 红线：

- ¶3 `D` 可以不完整；但若 `cv D` 类型的表达式用作 `|` 的操作数，`D` 必须完整并建模 `derived_from<range_adaptor_closure<D>>`。**若重载决议为这样的表达式选中了程序定义的 `operator|`，行为未定义**——不要给自己的闭包类再写一个 `operator|`；
- ¶4 若 `U` 有一个 `range_adaptor_closure<T>` 基类（`T` 不是 `U`），把 `cv U` 用作 `|` 的操作数是{{ub}}——CRTP 写错派生类的情形；
- ¶5 为 `range_adaptor_closure` 添加特化是{{ub}}。

¶2.4 排除范围类型：否则一个"既是范围又是闭包"的类型会让 `a | b` 产生歧义。

```cpp run ok
#include <ranges>
#include <vector>
#include <cstdio>
// 一个用户自定义的范围适配器闭包对象：取每个元素的平方
struct square_fn : std::ranges::range_adaptor_closure<square_fn> {
  template<std::ranges::viewable_range R>
  constexpr auto operator()(R&& r) const {
    return std::forward<R>(r) | std::views::transform([](auto x) { return x * x; });
  }
};
inline constexpr square_fn square;

int main() {
  std::vector<int> v{1, 2, 3, 4, 5};
  auto pipeline = std::views::filter([](int x) { return x % 2; }) | square;  // 闭包 | 闭包
  for (int x : v | pipeline) std::printf("%d ", x);   // 1 9 25
  for (int x : square(v | std::views::take(2))) std::printf("%d ", x);  // 1 4
  std::puts("");
}
```

### 适配器对象与部分应用（¶6–¶8）

¶6 **范围适配器对象**（range adaptor object，[[g:range-adaptor-object]]）是一个定制点对象（[[customization.point.object]]），**第一个实参接受 `viewable_range`**，并返回一个视图。¶7 只接受一个实参的适配器对象本身就是闭包对象（如 `views::reverse`、`views::join`、`views::all`）。

¶8 接受多个实参的适配器对象 `adaptor`（如 `views::filter`、`views::take`）：若 `adaptor(range, args...)` 良构，则 `adaptor(args...)` 产生一个闭包对象 `f`，它是完美转发调用包装器：

- ¶8.1 目标对象是 `adaptor` 的副本；
- ¶8.2 绑定实参 `bound_args` 是 `decay_t<decltype((args))>...` 类型的对象，用 `std::forward<decltype((args))>(args)...` 直接非列表初始化；
- ¶8.3 调用模式为 `adaptor(r, bound_args...)`。

这就是 `views::filter(pred)` 能单独写出来的原因：它是 `filter` 的**部分应用**（partial application），类似 `std::bind_back(views::filter, pred)`。¶8 末句：`adaptor(args...)` 良构当且仅当绑定实参的初始化都良构——注意这里**并不检查**之后能否用某个范围调用它，类型错误要到 `r | f` 时才暴露。

```cpp run ok
#include <ranges>
#include <vector>
#include <cstdio>
int main() {
  std::vector<int> v{1, 2, 3};
  auto f = std::views::transform([](int x) { return x + 1; });   // 部分应用：闭包对象
  auto a = f(v);          // C(R)
  auto b = v | f;         // R | C —— 与上面等价
  static_assert(std::same_as<decltype(a), decltype(b)>);
  auto ab = std::views::take(2) | f;     // C | D：新的闭包，调用模式为 d(c(arg))
  for (int x : v | ab) std::printf("%d ", x);    // 2 3
  std::puts("");
}
```

带参数的用户适配器，可以仿照 ¶8 自己写"完整调用 + 部分应用"两个重载：

```cpp run ok
#include <ranges>
#include <vector>
#include <cstdio>
// 带参数的自定义适配器 every_nth：既能 every_nth(r, n)，也能 r | every_nth(n)
struct every_nth_closure : std::ranges::range_adaptor_closure<every_nth_closure> {
  std::ptrdiff_t n;
  constexpr explicit every_nth_closure(std::ptrdiff_t k) : n(k) {}
  template<std::ranges::viewable_range R>
  constexpr auto operator()(R&& r) const {
    return std::forward<R>(r) | std::views::stride(n);
  }
};
struct every_nth_fn {
  template<std::ranges::viewable_range R>
  constexpr auto operator()(R&& r, std::ptrdiff_t n) const {    // 完整调用：adaptor(range, args...)
    return every_nth_closure(n)(std::forward<R>(r));
  }
  constexpr auto operator()(std::ptrdiff_t n) const {           // 部分应用：adaptor(args...) → 闭包
    return every_nth_closure(n);
  }
};
inline constexpr every_nth_fn every_nth;

int main() {
  std::vector<int> v{0, 1, 2, 3, 4, 5, 6};
  for (int x : v | every_nth(3)) std::printf("%d ", x);              // 0 3 6
  for (int x : every_nth(v, 2)) std::printf("%d ", x);               // 0 2 4 6
  auto pipe = std::views::reverse | every_nth(2);                    // 标准闭包 | 自定义闭包
  for (int x : v | pipe) std::printf("%d ", x);                      // 6 4 2 0
  std::puts("");
}
```

（C++23 的 `std::bind_back` 也可以用来生成部分应用，但它的结果不派生自 `range_adaptor_closure`，不能直接放到 `|` 右边，需要再包一层。）

!!! impl "libc++ 的实现"
    `__ranges/range_adaptor.h` 中，libc++ 用内部 CRTP 基类 `__range_adaptor_closure<T>` 实现管道，`range_adaptor_closure` 只是公开派生自它的空类。两个 `operator|` 都是受约束的非成员模板：`range | closure` 调用 `std::invoke(closure, range)`；`closure | closure` 返回 `__pipeable(__compose(c2, c1))`——正是 ¶1.3 的 `d(c(arg))`。判断"是不是闭包"时同样排除了 `ranges::range` 类型（¶2.4）。

## 各视图的公共形态

几乎所有适配器视图都按下面的模板写成，读懂一个就读懂了大半：

```cpp
template<input_range V, ...> requires view<V> && ...
class xxx_view : public view_interface<xxx_view<V, ...>> {
  V base_ = V();                       // 按值持有底层视图
  movable-box<F> fun_;                 // 若有函数对象
  template<bool Const> class iterator; // Const = true 时以 const V 为底层
  template<bool Const> class sentinel;
public:
  xxx_view() requires default_initializable<V> = default;
  constexpr explicit xxx_view(V base, ...);
  constexpr V base() const & requires copy_constructible<V>;
  constexpr V base() &&;
  constexpr auto begin() requires (!simple-view<V>);
  constexpr auto begin() const requires range<const V> && ...;
  ...
};
template<class R, ...> xxx_view(R&&, ...) -> xxx_view<views::all_t<R>, ...>;
```

- **底层总是视图 `V`**，通过推导指引 `views::all_t<R>` 把任意 `viewable_range` 变成视图（[[range.all]]）；
- 构造函数是 `explicit` 的（多参数构造函数在 C++23 被统一改为 `explicit`，[[P2711R1]]）；
- **`template<bool Const>` 的迭代器**：一份代码同时服务于非 const 与 const 迭代（*maybe-const*`<Const, V>`）。`iterator<false>` 能隐式转换成 `iterator<true>`；
- `begin() requires (!simple-view<V>)` 与 `begin() const` 的搭配见 [[range.utility]]。

## *movable-box*（[range.move.wrap]）

¶1 *movable-box*`<T>`（[[g:movable-box]]）的行为**与 `optional<T>` 完全相同**，除了：

- ¶1.1 约束 `move_constructible<T> && is_object_v<T>`；
- ¶1.2 默认构造函数在 `T` 可默认初始化时**构造一个值**（`movable-box{in_place}`），而不是空；
- ¶1.3 若 `copyable<T>` 不成立，复制赋值改为"若对方有值则 `emplace(*that)`，否则 `reset()`"；
- ¶1.4 若 `movable<T>` 不成立，移动赋值同理用 `emplace`。

它解决的问题：**lambda 不可赋值**。带捕获的 lambda（以及捕获了引用的任何闭包）有复制/移动构造函数，但赋值运算符被删除。而视图必须 `movable`（[[range.view]]），`filter_view` 若直接存一个 lambda 成员，它就不可赋值、不是视图了。*movable-box* 用"析构旧值再就地构造新值"模拟赋值，代价是多了一个"空"状态——若构造抛异常，盒子就空了，这也是 `filter_view::begin()` 有前置条件 "*pred_*`.has_value()`" 的原因（[[range.filter]] ¶3）。

¶2 建议实践：在不需要空状态时（例如 `T` 已经 `copyable`，或复制/移动构造不抛异常），*movable-box*`<T>` 应只存一个 `T`，不加额外的"是否有值"标志，从而零开销。

!!! history "从 copyable-box 到 movable-box"
    C++20 中它叫 *copyable-box*，要求 `T` 可复制构造。C++23 的 [[P2494R2]] 把它放宽为 *movable-box*，从此 `views::transform`、`views::filter` 等可以接受**只能移动**的函数对象（例如捕获了 `unique_ptr` 的 lambda）。libc++ 的 `__ranges/movable_box.h` 注释里记录了这次改名，并在 C++23 之前的模式下保留旧行为。

## *non-propagating-cache*（[range.nonprop.cache]）

¶1 *non-propagating-cache*`<T>`（[[g:non-propagating-cache]]）也"表现得完全像 `optional<T>`"，除了：

- ¶1.2 复制构造：**什么也不复制**，新对象为空；
- ¶1.3 移动构造：新对象为空，并把源对象 `reset()`；
- ¶1.4–¶1.5 复制/移动赋值：把自身清空（移动赋值还清空源对象）；
- ¶1.6 额外的 *emplace-deref*`(i)`：清空后用 `*i` 直接初始化所含值——注意 `*i` 若是 prvalue，可以**保证复制消除**地构造不可移动的对象。

¶2 注：*non-propagating-cache* 使输入视图能在迭代时**临时缓存值**。

"不传播"是关键语义：缓存只属于**这一个**视图对象。复制视图得到一个没有缓存的新视图；它的第一次 `begin()` 会重新计算。原因有二：缓存的迭代器指向的可能是原视图内部的东西（例如 `join_view` 缓存的内层范围），复制过去就成了悬垂指针；而且缓存的内容（"第一个满足谓词的位置"）对新视图来说可能已经不对了。

使用它的地方：`join_view`/`join_with_view` 缓存 prvalue 内层范围与输入外层迭代器、`lazy_split_view`、`chunk_view`（输入版）缓存当前迭代器、`cache_latest_view` 缓存最近的元素。（`filter_view` 等的 `begin()` 缓存在标准里只写成 "Remarks: caches the result"，实现通常也用同样语义的类型实现。）

## 辅助设施（[range.adaptor.helpers]）

仅用于说明的 *tuple-transform*（对元组的每个元素调用函数，结果组成新 `tuple`）、*tuple-for-each*、*as-lvalue*（把右值当左值用），以及 *all-random-access*、*all-bidirectional*、*all-forward* 三个概念（检查一组视图在 *maybe-const* 下是否都满足某强度）。它们主要服务于 `zip`、`zip_transform`、`cartesian_product`、`concat` 等多视图适配器。

## 惰性求值的代价模型

- **构造视图 O(1)**：只是把底层视图和函数对象存起来；
- **每一步 `++` 可能做非常数的工作**：`filter` 要跳过不满足的元素，`join` 要跳过空的内层范围；整个遍历的总代价仍与底层元素数成线性；
- **解引用可能重复计算**：`transform` 的 `operator*` 每次都调用函数。`transform | filter` 会对通过过滤的元素调用两次函数（一次在 `filter` 判定，一次在你读取），见 [[range.transform]]。C++26 的 `views::cache_latest` 就是为此设计的（[[range.cache.latest]]）；
- **`begin()` 可能 O(n) 一次、之后 O(1)**：`filter`/`drop_while`/`split`/`chunk_by`/`slide` 等的缓存。

## 视图索引

| 类别 | 视图 |
|---|---|
| 包装 | [[range.all\|all / ref_view / owning_view]]、[[range.common\|common、counted]]、[[range.as.const\|as_const、as_rvalue]]、[[range.cache.latest\|cache_latest、as_input]] |
| 选择 | [[range.filter\|filter]]、[[range.take\|take、take_while]]、[[range.drop\|drop、drop_while]]、[[range.chunk\|stride]] |
| 变换 | [[range.transform\|transform]]、[[range.elements\|elements / keys / values]]、[[range.enumerate\|enumerate]] |
| 顺序 | [[range.reverse\|reverse]] |
| 展平/拼接 | [[range.join\|join、join_with]]、[[range.concat\|concat]] |
| 切分 | [[range.split\|split、lazy_split]]、[[range.chunk\|chunk、slide、chunk_by]] |
| 多序列 | [[range.zip\|zip、zip_transform、adjacent、adjacent_transform]]、[[range.cartesian\|cartesian_product]] |
