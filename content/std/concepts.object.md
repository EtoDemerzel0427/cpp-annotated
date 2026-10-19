---
title: 对象概念
summary: movable、copyable、semiregular、regular 四个逐级加强的概念描述了像 int 一样行为的值类型；每一级加了什么要求，常见类型停在哪一级。
status: done
covers: *
since: c++20
related: concepts, concepts.lang, concepts.compare, concept.swappable, expr.prim.lambda.closure, range.view
tags: 标准库, 概念, 值语义, regular, semiregular
updated: 2026-10-19
---

!!! tldr
    - 四个概念逐级加强：`movable`（能移动、能交换）⊂ `copyable`（还能复制）⊂ `semiregular`（还能默认初始化）⊂ `regular`（还能用 `==` 比较）。
    - 只有对象类型能是 `movable`；引用、`const T`、有 const 成员的类都不是。
    - 有捕获的 lambda 不能赋值，连 `movable` 都不是；无捕获的 lambda 却是 `regular` 的。
    - 这四个概念没有自己的语义要求，语义全部来自它们组合的概念。

[concepts.object] ¶1 说，这些概念规定了标准库所依据的面向值的编程风格的基础。面向值，指的是对象像 `int` 一样行为：复制得到相等而独立的副本，赋值后两边相等，可以默认构造出一个之后再赋值的对象，可以用 `==` 判断相等。STL 从一开始就默认元素类型是这样的，这种类型被称为正则类型（regular type）。C++20 把它写成了四个概念。

## 常见类型停在哪一级

```cpp run title="object-concepts.cpp" ok
#include <concepts>
#include <functional>
#include <memory>
#include <string>

static_assert(!std::movable<int&>);      // 不是对象类型
static_assert(!std::movable<const int>); // 不能赋值

using UP = std::unique_ptr<int>;
static_assert(std::movable<UP> && !std::copyable<UP>);

using RW = std::reference_wrapper<int>;
static_assert(std::copyable<RW>);
static_assert(!std::semiregular<RW>);    // 不能默认构造

static_assert(std::regular<std::string>);

// 有捕获的 lambda：能复制构造，不能赋值
using WithCapture = decltype([x = 0] { return x; });
static_assert(std::copy_constructible<WithCapture>);
static_assert(!std::movable<WithCapture>);

// 无捕获的 lambda：regular
using NoCapture = decltype([] { return 1; });
static_assert(std::regular<NoCapture>);

int main() {}
```

| 概念 | 在上一级基础上增加 | 停在这一级的典型类型 |
|---|---|---|
| `movable` | 对象类型、移动构造、移动赋值、可交换 | `unique_ptr<T>`、`thread`、`ifstream` |
| `copyable` | 三种来源的复制构造和复制赋值 | `reference_wrapper<T>` |
| `semiregular` | 可默认初始化 | 没有 `==` 的简单聚合 |
| `regular` | 能用 `==` 比较，且 `==` 表示相等 | `int`、`string`、`vector<int>` |

两种 lambda 的结果值得解释。

有捕获的 lambda 的复制赋值运算符被定义为删除的（[[expr.prim.lambda.closure]]），移动赋值因此也不可用，所以它连 `movable` 都不是。ranges 库的视图要保存函数对象并且能被赋值，所以标准用一个说明专用的包装器 *movable-box* 存放它们，用先销毁再原地重建的方式模拟赋值。

无捕获的 lambda 自 C++20 起可以默认构造、可以赋值。它还能隐式转换为函数指针，于是 `a == b` 通过内建的指针比较变得合法。同一个闭包类型的两个对象没有状态，本来就相等，转换出的函数指针也比较为相等，所以它不只满足、也建模 `regular`。

## 四个定义

```cpp
template<class T>
  concept movable = is_object_v<T> && move_constructible<T> &&
                    assignable_from<T&, T> && swappable<T>;
template<class T>
  concept copyable = copy_constructible<T> && movable<T> && assignable_from<T&, T&> &&
                     assignable_from<T&, const T&> && assignable_from<T&, const T>;
template<class T>
  concept semiregular = copyable<T> && default_initializable<T>;
template<class T>
  concept regular = semiregular<T> && equality_comparable<T>;
```

### `movable`

- `is_object_v<T>`：值语义只谈对象，引用、函数类型、`void` 都不是 `movable`。`move_constructible<int&>` 为真，这一项正是为了排除它。
- `assignable_from<T&, T>`：移动赋值，返回 `T&`，并有公共引用（[[concept.assignable]]）。`const T` 因此不是 `movable`。
- `swappable<T>`：能用 `ranges::swap` 交换。满足前两项的类型总能用移动三步交换，所以这一项在语法上几乎总是成立。它的作用在语义上：如果类型提供了自定义的 `swap`，那个函数必须真的交换值（[[concept.swappable]]）。

### `copyable`

在 `movable` 之上，要求从 `T&`、`const T&`、`const T` 三种来源都能复制构造（`copy_constructible`）和复制赋值。三种来源要逐一列出，原因与 [[concept.copyconstructible]] 相同：这里组合的是概念而不是 requires 表达式，[[concepts.equality]] 的隐式表达式变体不起作用。

### `semiregular` 与 `regular`

¶2 注 1 说，`semiregular` 由行为类似 `int` 等基本类型、但不一定能用 `==` 比较的类型建模。¶3 注 2 说，`regular` 由行为类似 `int` 并且能用 `==` 比较的类型建模。

`semiregular` 的典型用户是迭代器的哨位：`sentinel_for<S, I>` 要求 `semiregular<S>`。`regular` 的典型用户是 `forward_iterator`，它要求迭代器能比较相等。

!!! note "为什么 `movable` 要包含 `swappable`"
    `sort`、`rotate`、`partition` 这些算法的基本操作是交换。如果 `movable` 只要求移动构造和移动赋值，用户写的高效 `swap`（比如只交换内部指针）要么不会被采用，要么被采用了却不受任何语义约束。把 `swappable` 放进来，既保证了 `ranges::swap` 可用，也要求用户的 `swap` 必须交换值。

!!! note "为什么 `regular` 不包含 `totally_ordered`"
    值语义离不开相等比较：要判断复制是否成功，要判断两个迭代器是否到了同一位置。顺序则不是必需的，复数、坐标、颜色都没有自然的全序。需要顺序时另加 `totally_ordered` 约束即可。

## 常见误解

!!! pitfall "`const` 数据成员让类型失去 `movable`"
    `struct S { const int id; };` 的赋值运算符被隐式删除，所以 `S` 不是 `movable`。`std::vector<S>` 不能交给 `ranges::sort`，因为排序要求元素能移动赋值（`sortable` 经 `permutable` 要求 `indirectly_movable_storable`）。引用数据成员同理。值类型不要用 const 或引用数据成员，这条经验规则在概念层面就体现在这里。

!!! pitfall "满足 `regular` 就说明 `==` 比较的是值"
    类型如果靠隐式转换（转为指针、转为 `bool`）获得 `==`，可能满足 `regular`，但比较的含义未必是值相等，那就是满足但不建模。无捕获的 lambda 碰巧没问题；一个有状态、能转换为 `bool` 的类型就不会这么幸运。

## 思考题

!!! question "思考题"
    1. `std::regular<int*>` 为真吗？无效指针值会不会让 `int*` 不建模 `regular`？
    2. `std::array<int, 0>` 是 `regular` 吗？`std::array<const int, 1>` 呢？
    3. `semiregular` 为什么用 `default_initializable`，而不是 `constructible_from<T>`？

<details markdown="1">
<summary>答案</summary>

1. 为真，也建模。复制和比较无效指针值不在这些操作的定义域内（[[structure.requirements#8]]），这不影响建模。
2. `array<int, 0>` 是 `regular`。`array<const int, 1>` 的元素是 const，复制赋值被删除，连 `movable` 都不是。
3. `constructible_from<T>` 只保证 `T()` 可用，泛型代码还会写 `T{}` 和 `T t;`（先声明后赋值）。`default_initializable` 三种都检查（[[concept.default.init]]），这才符合像 `int` 一样的直觉。
</details>
