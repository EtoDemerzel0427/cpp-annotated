---
title: 概念全景
summary: 从定义概念到按约束重载：requires 表达式与 requires 子句的区别，约束的满足与包含，四种写约束的位置，标准库概念的层次，从 enable_if 迁移，以及最常见的陷阱。
status: draft
since: c++20
order: 55
papers: P0734R0, P1141R2, P2963R3, P2841
related: temp.concept, temp.constr, temp.constr.order, expr.prim.req, temp.names, temp.param, over.match.best, over.match.viable, temp.deduct, topics/two-phase-lookup
tags: 概念, 约束, 泛型编程, SFINAE, 重载决议
updated: 2026-10-19
---

!!! tldr
    - 概念是给一组编译期要求起的名字。约束要回答两个独立的问题：这个声明对给定的实参是否可用（满足），两个都可用的声明哪个更特殊（包含）。
    - 满足按实参逐个检查原子约束：从左到右短路，替换失败只算不满足，但原子约束的结果必须恰好是 `bool`。
    - 包含只比较约束的结构：两个原子约束只有出自源代码中同一处表达式才算相同。想让重载按约束排序，就把条件定义成具名概念，并让强的概念通过名字引用弱的概念。
    - 同一个约束在程序不同位置的满足结果必须相同，否则程序非良构且不要求诊断；Clang 会缓存第一次的结果。
    - 从 `enable_if` 迁移到约束，除了可读性，还换来了按包含关系排序重载的能力和更清楚的错误信息。

概念的规则分布在几个条款中：概念定义在 [[temp.concept]]，*requires* 表达式在 [[expr.prim.req]]，约束的规范化与满足在 [[temp.constr]]，包含关系在 [[temp.constr.order]]，它们在重载决议中的作用在 [[over.match.viable]] 和 [[over.match.best]]。

## 同一个条件写两遍，为什么会歧义

<div class="compare" markdown="1">

```cpp error
#include <type_traits>
template<class T>
int g(T) requires
  std::is_integral_v<T>
{ return 1; }
template<class T>
int g(T) requires
  std::is_integral_v<T> &&
  std::is_signed_v<T>
{ return 2; }
int r = g(1);  // error: 歧义
```

```cpp ok
#include <concepts>
template<class T>
int g(T) requires
  std::integral<T>
{ return 1; }
template<class T>
int g(T) requires
  std::signed_integral<T>
{ return 2; }
int r = g(1);  // OK：选第二个
```

</div>

两边的意思一样：第二个重载的条件比第一个更严格。左边被 Clang 判为歧义，右边选中了第二个重载。

区别在于编译器怎样判断哪个约束更严格。它不理解 `is_integral_v<T>` 的含义，只比较约束的结构，而左边两个 `is_integral_v<T>` 是源代码里两处不同的表达式，被当作两个互不相干的条件。右边的 `std::signed_integral` 在定义里通过名字引用了 `std::integral`，展开后两边含有同一处表达式，编译器由此知道第二个约束蕴含第一个。下面先把这套机制讲清楚。

## 满足与包含是两个问题

约束首先被**规范化**（normalization，[[temp.constr.normal]]）：去掉括号，把 `&&` 和 `||` 拆成合取和析取，把概念的使用替换成它的定义，直到剩下不能再分的部分。这些不能再分的部分叫**原子约束**（atomic constraint，[[g:atomic-constraint]]）。例如 `std::integral<T> && (sizeof(T) > 2)` 规范化后是 `std::is_integral_v<T>` 和 `sizeof(T) > 2` 两个原子约束的合取。

在此基础上，约束要回答两个独立的问题：

| 问题 | 机制 | 输入 | 条款 |
|---|---|---|---|
| 这个声明对给定的实参可用吗 | **满足**（satisfaction） | 约束和具体的模板实参 | [[temp.constr.op]]、[[temp.constr.atomic]] |
| 两个都可用的声明，哪个更特殊 | **包含**（subsumption） | 两个约束的结构，不看实参 | [[temp.constr.order]] |

满足检查把实参代入每个原子约束并求值，所以替换失败只意味着不满足。包含检查只比较结构，所以语义相同但出处不同的约束互不包含，这就是开头那个歧义的来源。概念的大多数令人意外的行为，都可以从这两点得到解释。

## 定义概念

```cpp run title="define.cpp" ok
#include <concepts>
#include <cstddef>

// 基于类型特征
template<class T>
concept Arithmetic = std::integral<T> || std::floating_point<T>;

// 基于 requires 表达式：列出哪些表达式必须合法、结果是什么类型
template<class T>
concept Container = requires (T c, const T cc) {
  typename T::value_type;                              // 类型要求
  { cc.size() } -> std::convertible_to<std::size_t>;   // 复合要求
  c.begin(); c.end();                                  // 简单要求
};

// 组合：通过名字引用更弱的概念，这一点决定了重载能否排序
template<class T>
concept SizedRandomContainer = Container<T> && requires (T c) {
  { c[0] } -> std::same_as<typename T::value_type&>;
};

int main() {}
```

概念定义的限制（[[temp.concept]]）：

- 只能写在命名空间作用域，不能先声明后定义，不能重载；
- 概念本身不能带约束，`template<std::integral T> concept C = ...` 是非良构的，条件要写进等号右边；
- 不能特化。需要让用户定制时，让概念依赖一个可以特化的变量模板，例如 `std::ranges::enable_view`；
- 不能引用自身。

`C<Args...>` 是一个 `bool` 类型的 prvalue（[[temp.names#15]]），可以用在 `static_assert`、`if constexpr` 等任何需要 `bool` 常量的地方。

## requires 表达式与 requires 子句

两者都用关键字 `requires`，但完全是两回事：

| | *requires* 表达式（[[expr.prim.req]]） | *requires* 子句（[[temp.pre#9]]） |
|---|---|---|
| 是什么 | 一个类型为 `bool` 的表达式 | 声明的一部分，给声明加上约束 |
| 写在哪里 | 任何需要 `bool` 常量的地方，最常见于概念定义中 | 模板形参列表之后，或者函数声明符之后 |
| 要求不合法时 | 在模板中，结果为 `false` | |
| 在约束中的地位 | 一个原子约束，不再拆分 | 引入一个约束表达式 |

```cpp run ok
template<class T>
  requires requires (T x) { x + x; }   // 第一个 requires 是子句，第二个是表达式
T twice(T x) { return x + x; }
int main() { return twice(0); }
```

`requires requires` 是合法的，但通常说明这个条件应该提取成具名概念，原因见下文的包含关系。

!!! warning "模板之外的 requires 表达式"
    只有替换模板实参时产生的无效表达式才会让 *requires* 表达式得到 `false`。在模板之外写 `requires (std::vector<int> v) { v.foo(); }`，`v.foo()` 是一个普通的非良构表达式，程序非良构（[[expr.prim.req.general#5]] 注 1）。

## 四种写约束的位置

```cpp run title="four-ways.cpp" ok
#include <concepts>

template<std::integral T> T f1(T x) { return x; }                    // (1) 类型约束
template<class T> requires std::integral<T> T f2(T x) { return x; }  // (2) requires 子句
template<class T> T f3(T x) requires std::integral<T> { return x; }  // (3) 尾随 requires 子句
std::integral auto f4(std::integral auto x) { return x; }            // (4) 带约束的占位符

int main() { return f1(0) + f2(0) + f3(0) + f4(0); }
```

四个函数的约束规范化后都是 `std::integral<T>`（[[temp.constr.decl]]）。但它们的模板头写法不同，同一个函数模板的声明和定义必须用同一种写法（[[temp.over.link]]）。

一个声明同时有多处约束时，它们按固定顺序组成合取（[[temp.constr.decl#3]]）：模板形参列表中的类型约束，模板形参列表后的 *requires* 子句，函数形参中的 `C auto`，最后是尾随 *requires* 子句。这个顺序也是满足检查的短路顺序。

写法 (4) 叫**缩写函数模板**（abbreviated function template，[[g:abbreviated-function-template]]，[[P1141R2]]）：每个 `C auto` 形参引入一个虚构的类型模板形参。返回类型上的 `std::integral auto` 不是模板形参，而是对推导出的返回类型的检查，不满足时是硬错误。带约束的占位符也可以用于变量：`std::integral auto n = 1.0;` 推导出 `double`，不满足约束，是错误。

尾随 *requires* 子句只能用于模板化函数（[[dcl.decl.general#5]]），类模板的非模板成员函数也算。所以成员函数可以按约束重载，而不必变成模板。

## 满足怎样检查

满足检查（[[temp.constr]]）有五条要点：

1. 合取从左到右检查。左边不满足时，右边根本不做替换。
2. 原子约束的替换失败等于不满足。这只限于原子约束本身的直接语境；如果替换引发了某个函数模板体的实例化，而错误出在那里，就是硬错误。
3. 原子约束替换之后的类型必须恰好是 `bool`，不做转换。
4. `!E` 是一个原子约束。`!` 不会把替换失败翻转成满足。
5. 同一原子约束、同一组实参，在程序不同位置的满足结果必须相同，否则程序 IFNDR（非良构，不要求诊断，见 [[ifndr]]）。

第 1 条和第 3 条可以放在一起看：

<div class="compare" markdown="1">

```cpp ok
struct S {
  static constexpr int value = 1;
};
template<class T>
  requires (sizeof(T) > 100)
        && (T::value)
int f(T) { return 1; }
int f(...) { return 2; }
int r = f(S{});  // 2
```

```cpp error
struct S {
  static constexpr int value = 1;
};
template<class T>
  requires (sizeof(T) > 0)
        && (T::value)
int f(T) { return 1; }
int f(...) { return 2; }
int r = f(S{});  // error
```

</div>

`T::value` 的类型是 `int`，不是 `bool`。左边的第一个原子约束不满足，第二个不做替换，什么也没有发生，调用选 `f(...)`。右边的第一个原子约束满足，第二个被替换，Clang 报错 `atomic constraint must be of type 'bool' (found 'const int')`。

## 包含怎样比较

包含关系（[[temp.constr.order]]）把原子约束看作命题变量：约束 P 包含约束 Q，当且仅当按与或结构，P 能推出 Q。原子约束之间只比较身份：两个原子约束相同，当且仅当它们出自源代码中同一个表达式，并且参数映射等价（[[temp.constr.atomic#2]]）。

由此得到使用概念时最重要的一条经验：想让约束参与重载排序，就把它定义成具名概念，并让更强的概念通过名字引用更弱的概念。标准库的迭代器概念就是这样组织的，`random_access_iterator` 的定义中有 `bidirectional_iterator<I> && ...`，所以逐层包含：

```cpp run title="subsumption.cpp" ok
#include <concepts>
#include <iterator>
#include <cstdio>
#include <list>
#include <vector>

template<std::input_iterator I>
void walk(I) { std::puts("input"); }
template<std::bidirectional_iterator I>
void walk(I) { std::puts("bidirectional"); }
template<std::random_access_iterator I>
void walk(I) { std::puts("random access"); }

int main() {
  std::vector<int> v; std::list<int> l;
  walk(v.begin());   // random access
  walk(l.begin());   // bidirectional
}
```

开头左边的例子之所以歧义，是因为两个 `is_integral_v<T>` 出自不同的表达式。同理，各写一遍的两个 *requires* 表达式、各写一遍的两个 `!C<T>`、包了一层的 `(C<T> && D<T>) == true`，都无法参与包含比较。

C++26 补上了参数包的情形：`(C<Ts> && ...)` 形式的折叠表达式成为**折叠展开约束**（fold expanded constraint，[[temp.constr.fold]]，[[P2963R3]]），可以和 `(D<Ts> && ...)` 比较包含关系。在 C++23 中它们是互不相干的原子约束。

```cpp run ok
#include <concepts>
template<class... T> requires (std::integral<T> && ...)
int f(T...) { return 1; }
template<class... T> requires (std::signed_integral<T> && ...)
int f(T...) { return 2; }
int main() { return f(1, 2); }   // 2
```

本机 Clang 23 已经实现了这条规则，程序返回 2。

## 约束在哪些地方影响选择

| 场景 | 规则 | 条款 |
|---|---|---|
| 函数模板之间 | 偏序：按推导一样特殊时，约束更强的更特殊 | [[temp.func.order]] |
| 非模板函数之间，如类模板的成员函数 | 形参类型相同时，约束更强的胜出 | [[over.match.best]]、[[temp.constr.order#6]] |
| 类模板的偏特化 | 约束更强的偏特化更特殊 | [[temp.spec.partial.order]] |
| 模板模板实参 | 形参必须至少和实参一样特殊，约束也算在内；形参没有约束时忽略实参的约束 | [[temp.arg.template#4]] |
| 特殊成员函数 | 可以声明多个带不同约束的析构函数、复制构造函数，按约束选用，从而实现条件平凡 | [[class.dtor]] |

```cpp run title="partial-spec.cpp" ok
#include <concepts>
#include <cstdio>

template<class T> struct Printer { static void print() { std::puts("generic"); } };
template<std::integral T> struct Printer<T> { static void print() { std::puts("integral"); } };
template<std::signed_integral T> struct Printer<T> { static void print() { std::puts("signed"); } };

int main() {
  Printer<double>::print();     // generic
  Printer<unsigned>::print();   // integral
  Printer<int>::print();        // signed：signed_integral 包含 integral
}
```

## 标准库概念

标准库概念集中在 `<concepts>`、`<iterator>`、`<ranges>` 中，按层次组织。下表中箭头表示细化：右边的概念通过名字引用左边的概念，因此包含它，可以据此排序重载。

| 头文件 | 类别 | 层次 |
|---|---|---|
| `<concepts>` | 核心语言 | `same_as`、`derived_from`、`convertible_to`、`common_with`；`integral` → `signed_integral`、`unsigned_integral`；`floating_point`；`destructible` → `constructible_from` → `default_initializable`、`move_constructible` → `copy_constructible` |
| `<concepts>` | 比较 | `equality_comparable`、`totally_ordered`，以及 `_with` 版本 |
| `<concepts>` | 对象 | `movable` → `copyable` → `semiregular` → `regular` |
| `<concepts>` | 可调用 | `invocable` → `predicate` → `relation` |
| `<iterator>` | 迭代器 | `input_or_output_iterator` → `input_iterator` → `forward_iterator` → `bidirectional_iterator` → `random_access_iterator` → `contiguous_iterator`；`sentinel_for`、`sized_sentinel_for` |
| `<iterator>` | 算法要求 | `indirectly_readable`、`indirectly_copyable`、`sortable`、`mergeable`、`permutable` |
| `<ranges>` | 范围 | `range` → `input_range` → … → `contiguous_range`；`sized_range`、`view`、`borrowed_range`、`viewable_range` |

`regular_invocable` 与 `invocable`、`equivalence_relation` 和 `strict_weak_order` 与 `relation`，定义完全相同，区别只在语义要求上。它们互相包含，不能用来区分重载。

标准库概念通常还有编译器无法检查的**语义要求**，例如 `equality_comparable` 要求 `==` 是等价关系。一个类型满足了语法要求却违反语义要求时，叫做满足但不建模（satisfies but does not model，[[g:models-concept]]）。如果程序的合法性或含义取决于一组实参是否建模某个概念，而它们满足却不建模，程序 IFNDR（[[res.on.requirements]]）。

## 从 enable_if 迁移

| C++17 写法 | C++20 写法 | 说明 |
|---|---|---|
| `template<class T, std::enable_if_t<cond<T>, int> = 0>` | `template<class T> requires cond<T>` | 或者把 `cond` 定义成概念 |
| `void_t` 检测惯用法加特征类 | *requires* 表达式加概念 | 可读性好得多 |
| 按 `iterator_category` 做标签分派 | 按约束重载 | 需要概念逐层包含 |
| 用条件基类实现条件平凡 | 多个带约束的特殊成员函数 | 代码更少，编译更快 |
| 成员函数模板 `template<class U = T, enable_if_t<...>>` | 尾随 *requires* 子句 | 成员函数不必再是模板 |
| 用 `std::enable_if_t<...>* = nullptr` 控制偏特化 | 带约束的偏特化 | |

`enable_if` 的条件对编译器来说是一个不透明的布尔值。两个条件重叠的 `enable_if` 重载，只能靠手工构造互斥的条件来消除歧义：

```cpp title="enable-if-overlap.cpp" error
#include <type_traits>
template<class T, std::enable_if_t<std::is_integral_v<T>, int> = 0>
int f(T) { return 1; }
template<class T, std::enable_if_t<std::is_integral_v<T> && std::is_signed_v<T>, int> = 0>
int f(T) { return 2; }

int a = f(1);   // error: 歧义，enable_if 无法表达哪个更特殊
```

改用具名概念，就是开头右边的写法。

迁移时要注意的差别：

- SFINAE（[[g:sfinae]]）在模板实参推导期间起作用，约束在推导成功之后检查。约束不满足的候选被排除出可行函数集（[[over.match.viable]]）。
- `enable_if` 无法约束类模板本身，只能借助一个额外的默认模板形参。`template<std::integral T> struct S;` 让 `S<double>` 在被命名时就是错误（[[temp.names#14]]）。
- 硬错误的边界没有变化。约束中的表达式如果引发函数体的实例化而出错，仍然是硬错误，与 SFINAE 的直接语境规则一致。

## 错误信息

约束不满足时，编译器沿着规范化后的结构指出哪个原子约束失败、为什么失败：

```cpp title="diagnostic.cpp" error
#include <concepts>
template<class T>
concept Addable = requires (T a, T b) { a + b; };

template<Addable T> T sum(T a, T b) { return a + b; }

struct P {};
int main() { sum(P{}, P{}); }   // error: 约束不满足
```

本机 Clang 23 的诊断依次是：`no matching function for call to 'sum'`；`candidate template ignored: constraints not satisfied [with T = P]`；`because 'P' does not satisfy 'Addable'`；`because 'a + b' would be invalid: invalid operands to binary expression ('P' and 'P')`。在 C++17 中，同样的错误往往报在 `sum` 的函数体深处，或者在 `enable_if` 处只说没有名为 `type` 的成员。

让诊断更有用的几个习惯：

- 概念的粒度要适中，名字要说明意图，诊断会把概念名打印出来；
- 把复杂的要求拆成几个具名概念的合取，诊断能定位到失败的那一个；
- 对不应被调用的重载，可以写成带约束的 `= delete`，而不是让它从候选中消失，后者有时让诊断更难懂。

## 常见陷阱

!!! pitfall "包含只认同一处表达式"
    两处写同样的表达式不构成包含，必须经由同一个具名概念（[[temp.constr.atomic#2]]）。反过来，两个名字不同的概念如果展开到同一处表达式，它们的原子约束就相同：`template<class T> concept D = C<T>;` 与 `C` 规范化的结果一样，分别用 `C` 和 `D` 约束的两个重载互相包含，调用时歧义。

!!! pitfall "原子约束必须恰好是 bool"
    `requires (T::value)`（类型为 `int`）、`requires (std::tuple_size<T>{})`（类类型，虽然可以转换为 `bool`）都是非良构，而不是不满足（[[temp.constr.atomic#3]]）。需要时写 `requires (bool(T::value))` 或 `requires (T::value != 0)`。

!!! pitfall "否定不会翻转替换失败"
    `requires (!std::integral<typename T::type>)` 对没有 `type` 成员的 `T` 不满足。要表达没有符合要求的嵌套类型，把否定放在概念外面：先定义 `template<class T> concept HasIntegralType = std::integral<typename T::type>;`，再写 `requires (!HasIntegralType<T>)`。

!!! pitfall "满足结果被缓存"
    ```cpp
    template<class T> concept Complete = requires { sizeof(T); };
    struct S;
    static_assert(!Complete<S>);
    struct S {};
    static_assert(Complete<S>);   // IFNDR；Clang 复用缓存的结果，这条断言失败
    ```
    满足结果依赖于当前位置的概念，都会碰到 [[temp.constr.atomic#3]] 的 IFNDR：检测类型是否完整，检测某个重载是否已经声明，依赖 ADL 找到之后才声明的函数。

!!! pitfall "requires 表达式是一个整体"
    `requires { a; b; }` 和 `requires { a; }` 互不包含。公共部分要提取成概念。

!!! pitfall "约束检查的时机"
    函数模板的约束在重载决议时检查，不满足的候选不可行。类模板、别名模板、变量模板的约束在命名时就检查，即使只写 `S<double>*` 也必须满足。也不能为不满足约束的实参提供显式特化（[[temp.names#14]]）。

!!! pitfall "无约束的模板模板形参接受带约束的模板"
    `template<template<class> class TT>` 可以接受 `template<std::integral T> class X`（[[temp.arg.template#4]]），约束要到实例化 `TT<double>` 时才报错。

!!! pitfall "约束检查依赖自身"
    ```cpp
    template<class T> concept Printable = requires (T t) { print(t); };
    template<Printable T> void print(T);
    ```
    检查 `Printable<S>` 时，要对 `print(t)` 做重载决议，这又要检查 `Printable<S>`。Clang 23 报错 `satisfaction of constraint 'requires (T t) { print(t); }' depends on itself`。设计概念时，不要让它依赖用它约束的函数。

## C++26 的变化

**概念模板形参**（[[P2841]]）让概念可以作为模板实参传递，于是可以写接受概念的概念：

```cpp run ok
#include <concepts>
template<template<class> concept C, class... Ts>
concept all_satisfy = (C<Ts> && ...);
static_assert(all_satisfy<std::integral, int, long>);
static_assert(!all_satisfy<std::integral, int, double>);
int main() {}
```

本机 Clang 23 已经支持这一特性。在模板定义处还不知道 `C` 是哪个概念，规范化只能推迟到实例化时进行，这样的约束叫做**概念依赖约束**（concept-dependent constraint，[[temp.constr.concept]]），它们不参与包含比较。

折叠展开约束（[[P2963R3]]）见上文的包含一节。

## 思考题

!!! question "思考题 1"
    下面的调用选哪个重载？

    ```cpp
    template<class T> concept Small = sizeof(T) <= 4;
    template<class T> concept Tiny  = sizeof(T) <= 1;
    template<Small T> int f(T) { return 1; }
    template<Tiny T>  int f(T) { return 2; }
    int x = f('a');
    ```

<details markdown="1">
<summary>答案</summary>

歧义。两个约束都满足。`sizeof(T) <= 1` 确实蕴含 `sizeof(T) <= 4`，但它们是两个不同的原子约束，包含关系不看语义，所以谁也不包含谁。改法是 `template<class T> concept Tiny = Small<T> && sizeof(T) <= 1;`。
</details>

!!! question "思考题 2"
    `template<class T> requires (sizeof(T) > 1) && (T::value)` 对 `T = char` 不出错。写成 `requires (sizeof(T) > 1 && T::value)` 呢？

<details markdown="1">
<summary>答案</summary>

也不出错。规范化时括号是透明的（[[temp.constr.normal]] ¶1.1），`(sizeof(T) > 1 && T::value)` 同样被拆成两个原子约束的合取，短路照样生效。只有把它变成不以 `&&`、`||` 为顶层运算符的表达式，例如 `bool(sizeof(T) > 1 && T::value)`，才成为单个原子约束。这时 `char::value` 的替换失败让整个原子约束不满足，仍然不是硬错误，只是不再短路。
</details>

!!! question "思考题 3"
    下面的 `W<int>{}.f()` 调用哪个成员函数？`W<unsigned>{}.f()` 呢？

    ```cpp
    template<class T> struct W {
      int f() requires std::integral<T>;
      int f() requires std::signed_integral<T>;
    };
    ```

<details markdown="1">
<summary>答案</summary>

`W<int>`：两个都可行。它们是同一个类的直接成员，形参类型列表相同，第二个的约束更强（`signed_integral` 包含 `integral`），按 [[over.match.best]] ¶2.6 调用第二个。`W<unsigned>`：只有第一个满足约束，调用第一个。
</details>
