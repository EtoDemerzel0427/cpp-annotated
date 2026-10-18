---
title: 概念全景
summary: 从定义概念到按约束重载的完整路线：requires 表达式与 requires 子句、满足与包含是两个独立的问题、四种约束写法与缩写函数模板、标准库概念地图、从 SFINAE/enable_if 迁移、诊断，以及最常见的坑——包含关系只认同名概念、原子约束必须恰好是 bool、满足结果缓存导致的 IFNDR。
status: draft
since: c++20
order: 55
papers: P0734R0, P1141R2, P2963R3, P2841
related: temp.concept, temp.constr, temp.constr.order, expr.prim.req, temp.names, temp.param, over.match.best, over.match.viable, temp.deduct, topics/two-phase-lookup
tags: 概念, 约束, 泛型编程, SFINAE, 重载决议
updated: 2026-10-18
---

概念（concepts）是 C++20 最大的语言特性之一。它的规则散落在至少五个地方：概念定义在 [[temp.concept]]，*requires* 表达式在 [[expr.prim.req]]，约束的满足与规范化在 [[temp.constr]]，包含关系在 [[temp.constr.order]]，它们在重载决议中的作用在 [[over.match.viable]] 与 [[over.match.best]]。本专题把这些碎片拼成一条完整的路线，侧重**方法**与**陷阱**；精确的条文请沿链接回到各条款页。

## 一、一句话模型

> **概念 = 给一组编译期要求起的名字。约束要回答两个独立的问题：这个声明对这些实参"可用"吗（满足）？两个都可用的声明，哪个"更特殊"（包含）？**

| 问题 | 机制 | 输入 | 条款 |
|---|---|---|---|
| 可用吗？ | **满足**（satisfaction） | 约束 + 具体模板实参 | [[temp.constr.op]]、[[temp.constr.atomic]] |
| 谁更特殊？ | **包含**（subsumption） | 两个约束的**结构**，不看实参 | [[temp.constr.order]] |

两者都建立在**规范化**（[[temp.constr.normal]]）之上：约束表达式被拆成由合取 ∧、析取 ∨ 连接的**原子约束**，concept-id 被内联展开。

把这两个问题分开想，概念的绝大多数"怪异行为"就都能解释了：满足检查是**按实参求值**，所以替换失败只是"不满足"；包含检查是**按结构比较**，所以语义相同但写法来源不同的约束互不包含。

## 二、定义概念

```cpp run title="define.cpp" ok
#include <concepts>
#include <cstddef>

// 1. 基于类型特征
template<class T>
concept Arithmetic = std::integral<T> || std::floating_point<T>;

// 2. 基于 requires 表达式：描述"哪些表达式要合法、结果是什么类型"
template<class T>
concept Container = requires (T c, const T cc) {
    typename T::value_type;                              // 类型要求
    { cc.size() } -> std::convertible_to<std::size_t>;   // 复合要求
    c.begin(); c.end();                                  // 简单要求
};

// 3. 组合：通过名字引用更弱的概念（这一点对重载排序至关重要）
template<class T>
concept SizedRandomContainer = Container<T> && requires (T c) {
    { c[0] } -> std::same_as<typename T::value_type&>;
};

int main() {}
```

规则要点（[[temp.concept]]）：

- 只能在**命名空间作用域**定义，不能有前置声明，不能重载；
- **不能有关联约束**（`template<std::integral T> concept C = ...` 非法），要把条件写进约束表达式；
- **不能特化**——需要可定制性时，让概念依赖一个可特化的变量模板（如 `std::ranges::enable_view`）；
- 不能引用自身（无递归概念）；
- `C<Args...>` 是一个 `bool` prvalue（[[temp.names#15]]），可以用在 `static_assert`、`if constexpr` 中。

## 三、requires 表达式 vs requires 子句

两个都叫 `requires`，但完全是两回事：

| | *requires-expression*（[[expr.prim.req]]） | *requires-clause*（[[temp.pre#9]]） |
|---|---|---|
| 是什么 | 一个**表达式**，类型为 `bool` | 声明的一部分，给声明加**约束** |
| 写在哪 | 任何需要 `bool` 常量的地方（最常见于概念定义内） | 模板形参列表之后，或函数声明符之后（尾随） |
| 无效表达式的后果 | 在模板中：结果为 `false` | — |
| 在约束中的地位 | 一个**原子约束**（不可再分） | 引入一个约束表达式 |

```cpp
template<class T>
  requires requires (T x) { x + x; }   // 第一个 requires：子句；第二个：表达式
T twice(T x) { return x + x; }
```

`requires requires` 合法但通常是"应该提取成命名概念"的信号——原因见下文"包含只认同一出现"。

!!! warning "模板之外的 requires 表达式"
    *requires-expression* 只有在其要求依赖模板形参时，替换失败才"安静地"变成 `false`。在模板之外写 `requires (std::vector<int> v) { v.foo(); }`，`v.foo()` 是普通的非良构表达式，程序**非良构**（[[expr.prim.req]]）。

## 四、四种写约束的位置与缩写函数模板

```cpp run title="four-ways.cpp" ok
#include <concepts>

template<std::integral T> T f1(T x) { return x; }                  // (1) type-constraint
template<class T> requires std::integral<T> T f2(T x) { return x; }// (2) requires-clause
template<class T> T f3(T x) requires std::integral<T> { return x; }// (3) 尾随 requires-clause
std::integral auto f4(std::integral auto x) { return x; }          // (4) 约束占位符（缩写函数模板）

int main() { return f1(0) + f2(0) + f3(0) + f4(0); }
```

- 四个函数的关联约束都是 `std::integral<T>` 的范式（[[temp.constr.decl]]）。但它们是**不同写法的模板头**，同一个函数模板的声明与定义必须用同一种写法（[[temp.over.link]]）。
- 多个来源同时存在时，关联约束按固定顺序组成合取：形参列表中的 type-constraint → *requires-clause* → 函数形参中的 `C auto` → 尾随 *requires-clause*。顺序决定满足检查的**短路**次序。
- (4) 是**缩写函数模板**（abbreviated function template，[[P1141R2]]）：每个 `C auto` 形参引入一个虚构的类型模板形参。返回类型上的 `std::integral auto` 不是模板形参，而是对推导出的返回类型的**检查**——不满足时是硬错误。
- 约束占位符也可用于变量：`std::integral auto n = 1.0;` 是错误（推导出 `double`，不满足）。
- 尾随 *requires-clause* 只能用于 **templated 函数**（[[temp.pre#8]]）——包括类模板的非模板成员函数，这让"按约束重载成员函数"成为可能。

## 五、满足：怎么检查

满足检查（[[temp.constr]]）的要点：

1. **短路**：合取从左到右，左边不满足就不再检查右边——而且右边**根本不被替换**。
2. **替换失败 ⇒ 不满足**：只限原子约束的**直接语境**。若替换引发了某个函数模板体的实例化而在那里出错，是硬错误。
3. **原子约束必须恰好是 `bool`**：`requires (T::value)` 当 `value` 是 `int` 时非良构，而不是"转换为 bool"。
4. **`!E` 是一个原子**：`requires (!C<typename T::type>)` 在 `T::type` 不存在时**不满足**——`!` 不能翻转替换失败。
5. **结果必须稳定**：同一原子约束 + 同一实参在不同程序点结果不同 ⇒ IFNDR。

```cpp run title="satisfaction.cpp" ok
#include <cstdio>
template<class T> requires (sizeof(T) > 1) && (T::value)   // 第二个操作数对 int 无效
void f(T) { std::puts("template"); }
void f(char) { std::puts("non-template"); }

int main() {
    f('a');    // sizeof(char) > 1 不满足 ⇒ 第二个操作数不替换 ⇒ 选 f(char)
}
```

## 六、包含：怎么比较

包含关系（[[temp.constr.order]]）把原子约束当作命题变量：`P` 包含 `Q` ⇔ `P` 逻辑蕴含 `Q`（只看与或结构）。**原子约束之间只比较身份**：两个原子约束相同，当且仅当它们来自**源代码中同一个表达式的同一次出现**，且参数映射等价（[[temp.constr.atomic#2]]）。

后果是这个专题最重要的一条经验：

> **想让约束参与重载排序，就把它定义成具名概念，并让更强的概念通过名字引用更弱的概念。**

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

标准库迭代器概念层层引用（`random_access_iterator` 的定义中有 `bidirectional_iterator<I> && ...`），所以层层包含。反例——同样的条件直接写两遍：

```cpp title="no-subsumption.cpp" error
#include <type_traits>
template<class T> int g(T) requires std::is_integral_v<T> { return 1; }
template<class T> int g(T) requires std::is_integral_v<T> && std::is_signed_v<T> { return 2; }
int r = g(1);   // error: 歧义——两个 is_integral_v<T> 来自不同的出现
```

同理，两个各写一遍的 *requires-expression*、两个各写一遍的 `!C<T>`、`(C<T> && D<T>) == true` 这类被包了一层的表达式，都无法参与包含。

C++26 补上了一块拼图：`(C<Ts> && ...)` 形式的折叠表达式变成**折叠展开约束**，可以与 `(D<Ts> && ...)` 比较包含关系（[[temp.constr.fold]]、[[P2963R3]]）。C++23 中它们只是互不相干的原子。

## 七、用概念重载：在哪些地方起作用

| 场景 | 规则 | 条款 |
|---|---|---|
| 函数模板之间 | 偏序：推导上一样特殊时，更受约束者更特殊 | [[temp.func.order]] |
| 非模板函数之间（如类模板成员） | 同签名时，"更偏序受约束"者胜出 | [[over.match.best]]、[[temp.constr.order#6]] |
| 类模板部分特化 | 更受约束的部分特化更特殊 | [[temp.spec.partial.order]] |
| 模板模板实参 | 形参的约束须包含实参的约束（形参无约束时忽略） | [[temp.arg.template]] |
| 特殊成员函数 | 多个预期析构函数/复制构造函数按约束选择，实现"条件平凡" | [[class.dtor]] |

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

## 八、标准库概念地图

标准库概念集中在 `<concepts>`、`<iterator>`、`<ranges>`，按层次组织（每一层通过**名字**引用上一层，因而可以按包含关系重载）：

| 头文件 | 类别 | 代表概念 |
|---|---|---|
| `<concepts>` | 核心语言 | `same_as`、`derived_from`、`convertible_to`、`common_with`、`integral` ⊃ `signed_integral`/`unsigned_integral`、`floating_point`、`assignable_from`、`swappable`、`destructible` ⊃ `constructible_from` ⊃ `default_initializable`/`move_constructible` ⊃ `copy_constructible` |
| `<concepts>` | 比较 | `equality_comparable`、`totally_ordered`（及 `_with` 版本） |
| `<concepts>` | 对象 | `movable` ⊃ `copyable` ⊃ `semiregular` ⊃ `regular` |
| `<concepts>` | 可调用 | `invocable` ⊃ `regular_invocable` ⊃ `predicate` ⊃ `relation` ⊃ `equivalence_relation`/`strict_weak_order` |
| `<iterator>` | 迭代器 | `input_or_output_iterator` ⊃ `input_iterator` ⊃ `forward_iterator` ⊃ `bidirectional_iterator` ⊃ `random_access_iterator` ⊃ `contiguous_iterator`；`sentinel_for`、`sized_sentinel_for` |
| `<iterator>` | 算法要求 | `indirectly_readable`、`indirectly_copyable`、`sortable`、`mergeable`、`permutable` |
| `<ranges>` | 范围 | `range` ⊃ `input_range` ⊃ ... ⊃ `contiguous_range`；`sized_range`、`view`、`borrowed_range`、`viewable_range` |

（表中"⊃"读作"被……细化"，即右边的概念包含左边的。）

标准库概念除了语法要求，通常还有**语义要求**（如 `equality_comparable` 要求 `==` 是等价关系）。语义要求不能被编译器检查——满足语法要求而违反语义要求的类型"满足但不建模"（satisfies but does not model）；若程序的有效性或含义依赖于它是否建模，程序 IFNDR（[[res.on.requirements]]）。这是概念与"纯语法检查"之间的重要区别。

## 九、从 SFINAE / enable_if 迁移

| C++17 写法 | C++20 写法 | 备注 |
|---|---|---|
| `template<class T, std::enable_if_t<cond<T>, int> = 0>` | `template<class T> requires cond<T>` | 或给 `cond` 命名为概念 |
| `void_t` 检测习惯用法 + 特征类 | `requires` 表达式 + 概念 | 可读性大幅提升 |
| 标签分派（`iterator_category`） | 按约束重载 | 需要概念层层包含 |
| 条件基类实现"条件平凡" | 多个受约束的特殊成员函数 | 编译更快、代码更少 |
| 成员函数模板 `template<class U = T, enable_if_t<...>>` | 尾随 `requires` 子句 | 成员不必再是模板 |
| `std::enable_if_t<...>* = nullptr` 的部分特化开关 | 受约束的部分特化 | |

迁移带来的不只是可读性。`enable_if` 的条件是**不透明的布尔值**，两个互相重叠的 `enable_if` 重载只能靠手工构造互斥条件：

```cpp title="enable-if-overlap.cpp" error
#include <type_traits>
template<class T, std::enable_if_t<std::is_integral_v<T>, int> = 0>
int f(T) { return 1; }
template<class T, std::enable_if_t<std::is_integral_v<T> && std::is_signed_v<T>, int> = 0>
int f(T) { return 2; }

int a = f(1);   // error: 歧义——enable_if 没有"更特殊"的概念
```

而用具名概念，上面的意图可以直接表达（见第六节）。

迁移时需要注意的差别：

- **SFINAE 只在推导期起作用，约束在推导之后检查**：约束不满足的候选被排除出可行集（[[over.match.viable]]），但前提是推导已经成功。
- **类模板**：`enable_if` 无法约束类模板本身（只能借助一个额外的默认模板形参），而 `template<std::integral T> struct S;` 让 `S<double>` 在**命名时**就是错误（[[temp.names#14]]）。
- **硬错误边界没有变**：约束中的表达式若触发函数体实例化而出错，仍是硬错误，与 SFINAE 的"直接语境"规则一致。

## 十、诊断质量

约束的最大工程收益之一是错误消息。约束不满足时，编译器会沿着规范化树指出**哪个原子约束失败、为什么失败**：

```cpp title="diagnostic.cpp" error
#include <concepts>
template<class T>
concept Addable = requires (T a, T b) { a + b; };

template<Addable T> T sum(T a, T b) { return a + b; }

struct P {};
int main() { sum(P{}, P{}); }   // error: 约束不满足
```

Clang 对此大致报告：没有匹配的 `sum`；候选模板被忽略，因为约束不满足；`P` 不满足 `Addable`；因为 `a + b` 无效（`P` 没有 `operator+`）。对比 C++17 中同样的错误往往会深入到 `sum` 的函数体内部，或者在 `enable_if` 处只说"no type named 'type'"。

改善诊断的几个习惯：

- 概念的粒度要适中，名字要描述"意图"，诊断会把概念名打印出来；
- 把复杂的要求拆成多个具名概念的合取，诊断能精确定位到失败的那一个；
- 对于"不该被调用"的重载，可以用 `= delete` 加约束，而不是让它从候选集中消失（后者有时让诊断变得更难懂）。

## 十一、常见陷阱

!!! pitfall "1. 包含只认同一出现（同名概念）"
    两处写同样的表达式不构成包含——必须经由同一个具名概念（[[temp.constr.atomic#2]]）。反过来，两个**不同名**的概念若展开到同一处出现，它们的原子约束**是**相同的：`template<class T> concept D = C<T>;` 与 `C` 规范化结果相同，按 `C` 与按 `D` 约束的两个重载会歧义。

!!! pitfall "2. 原子约束必须恰好是 bool"
    `requires (T::value)`（`int`）、`requires (std::tuple_size<T>{})`（类类型，有 `operator bool`）都是**非良构**，不是"不满足"（[[temp.constr.atomic#3]]）。需要时写 `requires (bool(T::value))` 或 `requires (T::value != 0)`。

!!! pitfall "3. 否定不会翻转替换失败"
    `requires (!std::integral<typename T::type>)` 对没有 `type` 的 `T` 不满足。要表达"没有符合 X 的嵌套类型"，把否定放在**概念之外**：`template<class T> concept HasIntegralType = std::integral<typename T::type>;` 然后 `requires (!HasIntegralType<T>)`。

!!! pitfall "4. 满足结果缓存与 IFNDR"
    ```cpp
    template<class T> concept Complete = requires { sizeof(T); };
    struct S;
    static_assert(!Complete<S>);
    struct S {};
    static_assert(Complete<S>);   // IFNDR；Clang 复用缓存结果，此断言失败
    ```
    满足结果依赖"当前程序点"的概念——检测完整性、检测某个重载是否已声明、依赖 ADL 找到之后才声明的函数——都会撞上 [[temp.constr.atomic#3]] 的 IFNDR。

!!! pitfall "5. requires 表达式是一个整体"
    `requires { a; b; }` 与 `requires { a; }` 互不包含。把公共部分提取为概念。

!!! pitfall "6. 约束检查时机"
    函数模板：重载决议时检查（不满足 ⇒ 不可行）。类模板/别名模板/变量模板：**命名时**就检查（非待决的 `S<double>*` 也要满足）。显式特化不能为不满足约束的实参提供定义（[[temp.names#14]]）。

!!! pitfall "7. 无约束的模板模板形参接受受约束的模板"
    `template<template<class> class TT>` 可以接受 `template<std::integral T> class X`（[[temp.arg.template#4]]），约束只在实例化 `TT<double>` 时才报错。

!!! pitfall "8. 递归约束检查"
    类似 `template<class T> concept Printable = requires (T t) { print(t); };`，若 `print` 本身又受 `Printable` 约束，满足检查会递归到自身。例如 `print` 声明为 `template<Printable T> void print(T);` 时，检查 `Printable<S>` 要对 `print(t)` 做重载决议，而这又要检查 `Printable<S>`——Clang 23 报告 "satisfaction of constraint '...' depends on itself"。设计概念时避免让它依赖于用它约束的函数。

## 十二、C++26 的新东西

- **概念模板形参**（[[P2841]]）：`template<template<class> concept C>`，概念可以作为实参传递，于是可以写"高阶概念"：

    ```cpp
    template<template<class> concept C, class... Ts>
    concept all_satisfy = (C<Ts> && ...);
    static_assert(all_satisfy<std::integral, int, long>);
    ```

    相应地出现了**概念依赖约束**（[[temp.constr.concept]]）：在模板定义处不知道 `C` 是什么，规范化推迟到实例化；这样的约束不参与包含关系比较。

- **折叠展开约束**（[[P2963R3]]）：`(C<Ts> && ...)` 可以参与包含关系。

## 思考题

!!! question "思考题 1"
    下面的调用选哪个？为什么？

    ```cpp
    template<class T> concept Small = sizeof(T) <= 4;
    template<class T> concept Tiny  = sizeof(T) <= 1;
    template<Small T> int f(T) { return 1; }
    template<Tiny T>  int f(T) { return 2; }
    int x = f('a');
    ```

<details markdown="1">
<summary>答案</summary>

歧义。两个约束都满足；但 `sizeof(T) <= 1` 与 `sizeof(T) <= 4` 是两个不同的原子约束，包含关系不看语义（尽管 `<= 1` 蕴含 `<= 4`），所以谁也不包含谁。修正：`template<class T> concept Tiny = Small<T> && sizeof(T) <= 1;`。
</details>

!!! question "思考题 2"
    为什么 `template<class T> requires (sizeof(T) > 1) && (T::value)` 对 `T = char` 不出错，而 `template<class T> requires (sizeof(T) > 1 && T::value)` 呢？

<details markdown="1">
<summary>答案</summary>

两者都不出错。括号在规范化中是透明的（[[temp.constr.normal]] ¶1.1），`(sizeof(T) > 1 && T::value)` 同样被拆成合取 `sizeof(T) > 1 ∧ T::value`，短路照样生效。只有把它变成**非 `&&`/`||` 的表达式**——例如 `bool(sizeof(T) > 1 && T::value)`——才会成为单个原子约束；此时 `char::value` 的替换失败使整个原子不满足（仍然不是硬错误，只是不再短路）。
</details>

!!! question "思考题 3"
    `template<class T> struct W { void f() requires std::integral<T>; void f() requires std::signed_integral<T>; };` 中，`W<int>{}.f()` 调用哪个？`W<unsigned>{}.f()` 呢？

<details markdown="1">
<summary>答案</summary>

`W<int>`：两个都可行，它们是同一个类的直接成员、非对象形参类型列表相同，第二个更受约束（`signed_integral` 包含 `integral`），按 [[over.match.best]] ¶2.6 调用第二个。`W<unsigned>`：只有第一个满足，调用第一个。
</details>

## 小结

!!! summary "小结"
    | 主题 | 一句话 |
    |---|---|
    | 概念 | 命名空间级、不可约束、不可特化、不可递归的约束名；`C<X>` 是 `bool` |
    | requires 表达式 | 原子约束；模板内无效要求 ⇒ `false` |
    | requires 子句 | 受限文法；只能用在模板与 templated 函数上 |
    | 满足 | 规范化后逐原子检查；短路；直接语境的替换失败 ⇒ 不满足；必须恰好 `bool`；结果须稳定 |
    | 包含 | 只按结构与原子身份（同一出现）；想排序就用具名概念层层引用 |
    | 重载 | 函数模板偏序、非模板成员、部分特化、模板模板实参、特殊成员函数 |
    | 迁移 | `enable_if` → `requires`；标签分派 → 概念层次；条件基类 → 受约束的特殊成员 |
