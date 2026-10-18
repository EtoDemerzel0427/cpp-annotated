---
title: 对象概念
summary: movable ⊂ copyable ⊂ semiregular ⊂ regular——值语义编程风格的四级阶梯；每一级加了什么、为什么 movable 要求是对象类型并且可交换、哪些常见类型停在哪一级（unique_ptr、reference_wrapper、lambda、视图）。
status: done
covers: *
since: c++20
related: concepts, concepts.lang, concepts.compare, concept.swappable, expr.prim.lambda.closure, range.view
tags: 标准库, 概念, 值语义, regular, semiregular
updated: 2026-10-18
---

[concepts.object] 只有一段规范文字和四个概念定义，却是整个标准库"值语义"风格的骨架。¶1 说：

!!! std
    This subclause describes concepts that specify the basis of the value-oriented programming style on which the library is based.

    本节描述的概念规定了**面向值的编程风格**的基础——标准库正是建立在这种风格之上的。

"值语义"指的是：对象像 `int` 一样行为——复制得到相等且独立的副本、赋值后两边相等、可以默认构造出一个可赋值的对象、可以用 `==` 比较相等。这个想法来自 Alexander Stepanov 对"正则类型"（regular type）的刻画，STL 的设计从一开始就默认元素类型是这样的。C++20 把它写成了四个概念。

## 四级阶梯

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

| 概念 | 在上一级基础上增加 | 典型"停在这一级"的类型 |
|---|---|---|
| `movable` | 对象类型、可移动构造、可移动赋值、可交换 | `unique_ptr<T>`、`thread`、`ifstream` |
| `copyable` | 可复制构造（三种源）、可复制赋值（三种源） | `reference_wrapper<T>`；含捕获的 lambda？——不，见下文 |
| `semiregular` | 可默认初始化 | 无 `==` 的简单聚合；无捕获 lambda？——不，见下文 |
| `regular` | 可 `==` 比较且 `==` 反映相等 | `int`、`string`、`vector<int>` |

（表中两个"不"是故意留的伏笔，下面的例子会揭晓。）

### `movable`

- **`is_object_v<T>`**：引用类型、函数类型、`void` 都不是 `movable`。这是与 `move_constructible`（引用类型满足）的关键区别——值语义只谈"对象"。
- **`assignable_from<T&, T>`**：移动赋值，且返回 `T&`、有公共引用（[[concept.assignable]]）。由此 `const T` 不是 `movable`（不能赋值）。
- **`swappable<T>`**：可以用 `ranges::swap` 交换。对于满足前两项的类型，¶2.3 的兜底实现总是可用，所以这一项通常自动成立；它的真正作用是把**语义**纳入——如果类型提供了自定义 `swap`，它必须真的交换值（[[concept.swappable]]）。

### `copyable`

在 `movable` 基础上，要求从 `T&`、`const T&`、`const T` 三种源都能复制构造（`copy_constructible`）与复制赋值。和 `copy_constructible` 一样，三种源之所以要手动列出，是因为这里写的是概念组合而不是 requires 表达式，[[concepts.equality]] ¶6 的隐式表达式变体规则不适用。

### `semiregular` 与 `regular`

¶2 注 1：`semiregular` 被"行为类似 `int` 等基本类型、只是不一定能用 `==` 比较"的类型建模。¶3 注 2：`regular` 被"行为类似 `int` 且能用 `==` 比较"的类型建模。

`semiregular` 的典型用户是**迭代器的哨位**和**视图**：`ranges::sentinel_for<S, I>` 要求 `semiregular<S>`；早期 C++20 的 `view` 要求 `semiregular`（后来放宽为 `movable`，以支持仅可移动的视图）。`regular` 的典型用户是 `forward_iterator`（迭代器必须可比较相等）和 `regular_invocable` 所要求的"值"。

## 例子：常见类型停在哪一级

```cpp run title="object-concepts.cpp" ok
#include <concepts>
#include <functional>
#include <memory>
#include <string>

static_assert(!std::movable<int&>);                    // 不是对象类型
static_assert(!std::movable<const int>);               // 不可赋值
static_assert(std::movable<std::unique_ptr<int>> && !std::copyable<std::unique_ptr<int>>);
static_assert(std::copyable<std::reference_wrapper<int>> &&
              !std::semiregular<std::reference_wrapper<int>>);   // 不能默认构造
static_assert(std::regular<std::string>);

// 无捕获 lambda：C++20 起可默认构造、可赋值；
// 而且它能隐式转换为函数指针，于是 a == b 比较的是两个函数指针——regular！
using NoCapture = decltype([] { return 1; });
static_assert(std::regular<NoCapture>);

// 有捕获 lambda：可复制构造，但复制赋值运算符被删除
using WithCapture = decltype([x = 0] { return x; });
static_assert(std::copy_constructible<WithCapture> && !std::copyable<WithCapture>);
static_assert(!std::movable<WithCapture>);

int main() {}
```

最后两组揭晓了表格里的伏笔：

- **有捕获的 lambda 连 `movable` 都不是**——闭包类型的复制赋值运算符被定义为删除的（[[expr.prim.lambda.closure]]），移动赋值也因此不可用。这就是为什么 ranges 库需要一个说明专用的包装器来存放视图中的函数对象（历史上先后叫 *`semiregular-box`*、*`copyable-box`*，C++23 起为 *`movable-box`*）：它用"销毁再原地重建"的方式模拟赋值。
- **无捕获 lambda 是 `regular` 的**，这多半出乎意料。无捕获闭包类型有到函数指针的隐式转换函数，于是 `a == b` 经内建的指针比较变得合法。从语义上看，两个同类型的无捕获闭包对象确实"相等"（它们没有状态），而函数指针比较对同一个闭包类型的转换结果给出真——所以它不只是满足，也确实建模 `regular`。

## 设计要点

!!! note "为什么 `movable` 要求 `swappable`"
    值语义的算法（`sort`、`rotate`、`partition`）的基本操作是交换。如果只要求移动构造 + 移动赋值，算法只能用"三次移动"实现交换，自定义的高效 `swap`（例如只交换内部指针）就不会被采用，或者会被采用但不受任何语义约束。把 `swappable` 纳入 `movable`，既保证了 `ranges::swap` 可用，也给用户自定义的 `swap` 施加了"必须交换值"的语义要求。

!!! note "为什么 `regular` 不包含 `totally_ordered`"
    相等比较是值语义的必需品（判断复制是否成功、判断两个迭代器是否到达同一位置），但"有序"不是：复数、坐标、颜色都没有自然的全序。需要有序时另外加 `totally_ordered` 约束即可。

## 陷阱

!!! pitfall "`const` 成员让类型失去 `movable`"
    `struct S { const int id; };` 的赋值运算符被隐式删除，于是 `S` 不是 `movable`，不能放进需要 `movable` 的 ranges 视图（例如作为 `views::single` 的元素）。引用成员同理。这是"值类型不要用 const/引用数据成员"这条经验规则在概念层面的体现。

!!! pitfall "\"满足 `regular`\" 不代表 `==` 比较的是你以为的东西"
    如果一个类型通过隐式转换（转为指针、转为 `bool`）获得 `==`，它可能满足 `regular`，但比较的语义未必是值相等——那就是满足但不建模。无捕获 lambda 恰好"歪打正着"；一个有状态却能转换为 `bool` 的类型则不会这么幸运。

## 思考题

!!! question "思考题"
    1. `std::regular<int*>` 为真吗？它是否建模 `regular`（考虑无效指针值）？
    2. `std::array<int, 0>` 是 `regular` 吗？`std::array<const int, 1>` 呢？
    3. 为什么 `semiregular` 用的是 `default_initializable` 而不是 `constructible_from<T>`？

<details markdown="1">
<summary>展开查看答案与解析</summary>

1. 为真。建模与否取决于定义域：对无效指针值做复制本身就是由实现定义的（[[basic.stc]]），比较也不保证有意义——这些值不在相关表达式的定义域内（[[structure.requirements#8]]），不影响 `int*` 建模 `regular`。
2. `array<int, 0>` 是 `regular`。`array<const int, 1>` 不是：它含有 const 元素，复制赋值被删除，连 `movable` 都不是。（它也不是 `default_initializable`：`array<const int, 1> a;` 会默认初始化一个 const int 元素，非良构。）
3. 泛型代码会写 `T t;`（例如先声明再赋值的模式），`constructible_from<T>` 只保证 `T()` 可用。`default_initializable` 额外保证 `T{}` 与 `T t;` 都可用（[[concept.default.init]]），这才符合"像 `int` 一样"的直觉——`int i;` 总是合法的。
</details>

## 小结

!!! summary
    - `movable` = 对象类型 + 移动构造 + 移动赋值 + 可交换；引用、`const` 类型、有捕获的 lambda 都不是。
    - `copyable` = `movable` + 三种源的复制构造与复制赋值。
    - `semiregular` = `copyable` + `default_initializable`："像 `int`，但不一定能比较"。
    - `regular` = `semiregular` + `equality_comparable`："像 `int`"。
    - 这四个概念没有额外的语义段落——语义全部来自它们所组合的概念（`assignable_from`、`swappable`、`copy_constructible`、`equality_comparable`……）。
