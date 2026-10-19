---
title: 类模板实参推导
summary: CTAD 的本质：从构造函数、拷贝推导候选、用户推导指引、聚合推导候选（以及继承构造函数、别名模板）构造一组作为指引的函数模板，在一个假想类上做一次构造函数重载决议，用胜出者的返回类型作为推导结果。
status: draft
since: c++17
papers: P0091R3, P1814R0, P1816R0, P2082R1, P2582R1
related: dcl.type.class.deduct, temp.deduct.guide, temp.deduct.call, over.match.best, over.match.list, dcl.init.aggr
tags: 重载决议, 模板, CTAD
updated: 2026-10-17
---

`std::pair p(1, 2.0);` 为什么能推出 `std::pair<int, double>`？C++17 的**类模板实参推导**（class template argument deduction，CTAD，[[P0091R3]]）给出的答案几乎完全复用了已有机制：它不发明新的推导算法，而是把类模板的构造函数翻译成一组函数模板（称为**指引**，guides），再对它们做一次普通的函数模板实参推导和重载决议。胜出的那个函数模板的返回类型，就是推导出的类型。

这一设计让 CTAD 自动继承了重载决议的全部语义：转发引用、`explicit`、约束、偏序、列表初始化的两阶段……代价是，这些规则中不直观的地方也一并继承了下来。

本节回答两个问题：指引从哪里来（第 1–5 段），以及怎么在指引上做决议（第 6 段）。触发 CTAD 的语法与语境在 [[dcl.type.class.deduct]]，用户编写推导指引的语法在 [[temp.deduct.guide]]。

## 指引的来源（¶1）

¶1 当推导类型占位符（[[dcl.type.class.deduct]]）的 *template-name*（或 {{c++26}} *splice-type-specifier*）指代主类模板 `C` 时，构造 `C` 的指引集合：

### ① 每个构造函数一个函数模板（¶1.1）

若 `C` 已定义，对 `C` 的每个构造函数，生成一个函数模板：

- 模板形参 = `C` 的模板形参 + 构造函数自己的模板形参（含默认模板实参）；
- 关联约束 = `C` 的约束 ∧ 构造函数的约束（注 1：`C` 的 *template-head* 中的约束先检查）；
- 形参列表 = 构造函数的形参列表；
- 返回类型 = `C<C 的模板形参…>`。

```cpp nocheck
template<class T, class U> struct pair {
  pair(const T&, const U&);
  template<class X, class Y> pair(X&&, Y&&);
};
// 对应的指引（示意）：
template<class T, class U>                   auto G1(const T&, const U&) -> pair<T, U>;
template<class T, class U, class X, class Y> auto G2(X&&, Y&&)         -> pair<T, U>;
```

`G2` 中 `T`、`U` 无法从实参推导，所以它对 `pair p(1, 2.0)` 推导失败，不成为候选。这就是标准库还需要用户推导指引 `pair(T1, T2) -> pair<T1, T2>` 的原因（它让 `pair p("a", 1)` 推出 `pair<const char*, int>` 而不是带数组类型的 `pair`）。

### ② 无构造函数时的 `C()`（¶1.2）

若 `C` 未定义或没有声明任何构造函数，额外加入由假想构造函数 `C()` 派生的指引。

### ③ 拷贝推导候选（¶1.3）

额外加入由假想构造函数 `C(C)` 派生的指引，称为**拷贝推导候选**（copy deduction candidate）：

```cpp nocheck
template<class T> auto G_copy(C<T>) -> C<T>;
```

它保证用一个 `C<X>` 去初始化时推出 `C<X>`，而不是 `C<C<X>>`。

### ④ 用户编写的推导指引（¶1.4）

每个 *deduction-guide* 产生一个函数（模板），其 *template-head* 与形参列表取自推导指引，返回类型是推导指引的 *simple-template-id*。

```cpp run ok
#include <vector>
#include <type_traits>
int main() {
  std::vector<int> src{1, 2, 3};
  std::vector v(src.begin(), src.end());   // 标准库提供的指引：
                                           // template<class It> vector(It, It) -> vector<iter_value_t<It>>
  static_assert(std::is_same_v<decltype(v), std::vector<int>>);
}
```

没有这个指引的话，构造函数 `vector(InputIt, InputIt)` 生成的指引中 `T` 无从推导，CTAD 会失败。

### ⑤ 聚合推导候选（¶1 后半）{{c++20}}

若 `C` 已定义且满足聚合类的条件（假设任何依赖基类没有虚函数和虚基类），初始化器是非空的花括号列表或圆括号表达式列表，并且 `C` 没有推导指引，则加入一个**聚合推导候选**（aggregate deduction candidate）。

构造方法：设初始化列表元素为 `x1…xn`，对每个 `xi` 找出它（按 [[dcl.init.aggr]]）会初始化的聚合元素 `ei`，但对以下元素不考虑大括号省略（¶1.5）：依赖的非数组类型、界值依赖的数组类型、元素类型依赖且 `xi` 是字符串字面量的数组类型。非尾随的包展开元素视为不对应任何初始化器（¶1.6），尾随的包展开元素对应所有剩余初始化器（¶1.7）。若某个 `xi` 没有对应元素，不加该候选。然后用假想构造函数 `C(T1, …, Tn)` 生成指引，其中：

- ¶1.8 `ei` 是数组且 `xi` 是花括号列表 → `Ti` 是到 `ei` 声明类型的右值引用；
- ¶1.9 `ei` 是数组且 `xi` 是字符串字面量 → `Ti` 是到 const 限定的 `ei` 声明类型的左值引用；
- ¶1.10 否则 `Ti` 是 `ei` 的声明类型。

```cpp run ok
#include <type_traits>
template<class T> struct Agg { T a; T b; };
template<class T, class U> struct Two { T a; U b; };
int main() {
  Agg x{1, 2};          // 聚合推导候选：template<class T> Agg<T> G(T, T)
  Two y{1, 2.0};        // template<class T, class U> Two<T,U> G(T, U)
  static_assert(std::is_same_v<decltype(x), Agg<int>>);
  static_assert(std::is_same_v<decltype(y), Two<int, double>>);
}
```

在 C++17 中，聚合没有构造函数，要使用 CTAD 必须手写推导指引。C++20 的 [[P1816R0]] 与 [[P2082R1]] 引入了聚合推导候选。

大括号省略的限制会带来一些微妙的结果（改编自标准例子）：

```cpp
template <typename T> struct S { T x; T y; };
template <typename T> struct C { S<T> s; T t; };
template <typename T> struct D { S<int> s; T t; };

C c1 = {1, 2};            // error: e1 = s（依赖的非数组类型，不做大括号省略），1 无法推导 S<T>
C c3 = {{1u, 2u}, 3};     // OK：{1u,2u} 对应 S<T>（T 从 3 推导为 int；{1u,2u} 是非推导语境）
D d1 = {1, 2};            // error: S<int> 是非依赖类型，做大括号省略：1→s.x，2→s.y，没有元素对应 t
D d2 = {1, 2, 3};         // OK：大括号省略后 1、2 初始化 s，3 初始化 t，推出 D<int>
```

数组元素与字符串字面量：

```cpp
#include <cstddef>
template<class T, std::size_t N> struct H { T array[N]; };
template<class T, std::size_t N> struct I { volatile T array[N]; };
template<std::size_t N> struct J { unsigned char array[N]; };

H h = { "abc" };    // OK：形参 const T(&)[N]，推出 H<char, 4>（T 是 char 而不是 const char）
I i = { "def" };    // OK：形参 const volatile T(&)[N]，推出 I<char, 4>
J j = { "ghi" };    // error: 形参 const unsigned char(&)[N] 不能绑定到 const char[4]
```

### ⑥ 继承的构造函数（¶1 末尾）{{c++23}}

若 `C` 已定义并从直接基类 `B`（在 *base-specifier-list* 中以 *class-or-decltype* 指代）继承构造函数，设 `A` 是一个模板形参列表与 `C` 相同、*defining-type-id* 为 `B` 的别名模板。若 `A` 是可推导模板，则 `A` 的指引（见下文第 4 段）也加入 `C` 的指引，但返回类型 `R` 替换为 `typename CC<R>::type`。`CC` 是一个辅助类模板，其唯一的偏特化把 `B` 形式的特化映射回对应的 `C` 特化（注 2）。这是 C++23 的 [[P2582R1]]。

```cpp nocheck
template <typename T> struct B { B(T); };
template <typename T> struct C : public B<T> { using B<T>::B; };
template <typename T> struct D : public B<T> {};

C c(42);       // OK：推出 C<int>（经继承的 B(T)）
D d(42);       // error: D 没有继承构造函数，没有可用的指引
```

!!! impl "实现状态"
    截至写作时，本机的 Clang 23 尚未实现继承构造函数的 CTAD：上例中 `C c(42);` 也会报 "no viable constructor or deduction guide"。各编译器的支持情况请以其文档为准。

附录 [[diff.cpp20.over]] 记录了这项改动的兼容性影响：原来走别的指引的代码可能推出不同的类型。

## 模板模板形参上的 CTAD（¶3）

¶3 当推导类型占位符的 *template-name* 指代一个类型模板模板形参 `P` 时，对应的模板模板实参必须是可推导模板。设 `A` 是一个别名模板：其模板形参列表就是 `P` 的，*defining-type-id* 是"实参模板<`P` 的模板实参列表>"。然后用 `A` 代替原 *template-name* 解析占位符，也就是按下文的别名模板规则处理。

```cpp nocheck
template<typename ... Ts>
struct Y {
  Y();
  Y(Ts ...);
};
template<template<typename T = char> class X>
void f() {
  X x;          // OK：推出 Y<char>（P 的默认模板实参参与推导）
  X x1{1};      // OK：推出 Y<int>
  X x2{1, 2};   // error: 无法从 Y<int, int> 推导 X<T>
}
template void f<Y>();
```

这里 `A` 相当于 `template<typename T = char> using A = Y<T>;`。`X x` 时，`Y()` 生成的指引经第 4 段的变换后带上了 `A` 的模板形参 `T = char`，于是推出 `Y<char>`。

!!! impl
    Clang 23 对 `X x1{1}` 的处理与标准一致；但 `X x;` 会推出 `Y<>`（没有利用 `P` 的默认模板实参），进而因 `Y<>` 的两个默认构造函数冲突而报错，与标准例子不符。

## 别名模板上的 CTAD（¶4–¶5）{{c++20}}

¶4 当占位符的 *template-name* 指代别名模板 `A` 时，`A` 的 *defining-type-id* 必须形如 `typename(可选) 嵌套名(可选) template(可选) simple-template-id`（[[dcl.type.simple]]）。`A` 的指引构造如下：对 *simple-template-id* 所指模板的每个指引 `f`：

1. 从 `A` 的 *defining-type-id* 推导 `f` 返回类型的模板实参（按 [[temp.deduct.type]]），允许不推出全部实参；若因其他原因失败，以空的推导结果继续。
2. 把推导结果代入 `f` 得到 `g`。若代入成功，构造 `f''`：
    - ¶4.1 函数类型同 `g`；
    - ¶4.2 若 `f` 是模板，`f''` 的模板形参 = `A` 中在上述推导里出现过（或经其默认模板实参递归出现）的模板形参，加上 `f` 中未推导出的模板形参；
    - ¶4.3 关联约束 = `g` 的约束 ∧ "`A` 的实参可以从返回类型推导"；
    - ¶4.4–¶4.6 拷贝推导候选、来自推导指引、*explicit-specifier* 的性质都保留。

¶5 "`A` 的实参可从类型 `T` 推导"的定义：设辅助类模板 `AA` 有一个偏特化，其模板形参列表是 `A` 的、模板实参列表是 `A` 的特化（[[temp.dep.type]]）；`AA<T>` 能匹配该偏特化即可。

这套机制的关键是 ¶4.3 的那个额外约束：它保证推出的类型确实是 `A` 的某个特化，而不只是原模板的某个特化。

```cpp
#include <concepts>
#include <type_traits>
template <class T, class U> struct C {
  C(T, U);                                      // #1
};
template<class T, class U>
  C(T, U) -> C<T, std::type_identity_t<U>>;     // #2

template<class V> using A = C<V*, V*>;
template<std::integral W> using B = A<W>;

int i{};
double d{};
A a1(&i, &i);   // OK：推出 A<int>，即 C<int*, int*>
A a2(i, i);     // error: 无法从 int 推导 V*
A a3(&i, &d);   // error: #1 无法从 (int*, double*) 推导 (V*, V*)；#2 推出的 C<int*, double*> 不是 A<V>
B b1(&i, &i);   // OK：推出 B<int>
B b2(&d, &d);   // error: C<double*, double*> 虽是 A<double>，但 double 不满足 std::integral
```

标准在例 3 中给出了一种可能的实现：把 `#1` 变换为 `template<class V> requires deduces_A<C<V*, V*>> auto f1_prime(V*, V*) -> C<V*, V*>;`，其中 `deduces_A` 用上面 `AA` 偏特化技巧实现。理解了这个变换，也就理解了别名模板 CTAD 的整套机制。

```cpp run ok
#include <vector>
#include <type_traits>
template<class T> using Vec = std::vector<T>;
int main() {
  Vec v{1, 2, 3};     // C++20：别名模板 CTAD，推出 std::vector<int>
  static_assert(std::is_same_v<decltype(v), std::vector<int>>);
}
```

别名模板 CTAD 由 C++20 的 [[P1814R0]] 引入。

## 在指引上做重载决议（¶6）

¶6 按 [[dcl.init]] 以及 [[over.match.ctor]]、[[over.match.copy]] 或 [[over.match.list]]（视初始化的形式而定）对一个假想类类型的对象做初始化和重载决议：把占位符所指模板的指引当作该假想类的构造函数，初始化器由 CTAD 所在的语境提供。例外：

- ¶6.1 若初始化列表由单个表达式组成，其类型为 `cv U`，`U` 是占位符（直接或间接）指代的类模板的特化或其派生类，则跳过 [[over.match.list]] 的第一阶段（初始化列表构造函数）。
- ¶6.2 对聚合推导候选做模板实参推导时，只有当尾随形参包的元素个数没有通过其他方式推出时，才由剩余实参个数决定。

若函数（模板）由带 *explicit-specifier* 的构造函数或推导指引生成，对应的假想构造函数具有相同的 *explicit-specifier*。所有假想构造函数都视为假想类的 public 成员。

### ¶6.1：`vector v{other}` 是拷贝

```cpp run ok
#include <vector>
#include <type_traits>
int main() {
  std::vector v1{1, 2};
  std::vector v2{v1};          // ¶6.1：跳过 initializer_list 阶段 → 拷贝推导候选 → vector<int>
  std::vector v3{v1, v1};      // 两个元素，不适用 ¶6.1 → initializer_list<T> 指引 → vector<vector<int>>
  static_assert(std::is_same_v<decltype(v2), std::vector<int>>);
  static_assert(std::is_same_v<decltype(v3), std::vector<std::vector<int>>>);
}
```

没有 ¶6.1，`std::vector v2{v1}` 会在第一阶段选中由 `vector(initializer_list<T>)` 生成的指引，推出 `vector<vector<int>>`，这与花括号包一个同类对象就是拷贝的普遍直觉相反。这条规则的代价是 `v2` 与 `v3` 的行为不一致，这在泛型代码中仍可能令人意外。

### explicit 的传递

指引保留构造函数或推导指引的 `explicit`。在拷贝初始化或拷贝列表初始化中，若推导阶段就选中了 explicit 的指引，推导本身就非良构，即使随后真正用于初始化的构造函数不是 explicit 的：

```cpp
template <class T> struct A {
  explicit A(const T&, ...) noexcept;   // #1
  A(T&&, ...);                          // #2
};
int i;
A a1 = { i, i };   // error: 推导时选中 explicit #1（#2 的 T&& 不是转发引用，不能从左值 i 推导）
A a2{i, i};        // OK：直接列表初始化，#1 推出 A<int>，并用 #1 初始化
A a3{0, i};        // OK：#2 推出 A<int>（0 是右值）
A a4 = {0, i};     // OK：同上，#2 不是 explicit
```

注意 `#2` 的形参 `T&&`：由构造函数生成的指引中，`T` 是类模板的模板形参，[[temp.deduct.call]] 明确规定这种 `T&&` 在 CTAD 中**不是转发引用**。所以 `#2` 对左值 `i` 推导失败：

```cpp
template<class T> struct W { W(T&&); };
int n;
W w1{0};    // OK：W<int>
W w2{n};    // error: T&& 不是转发引用，不能从左值推导
```

为什么这样规定？若 `T&&` 是转发引用，`W w2{n}` 会推出 `W<int&>`，构造函数随之变成 `W(int&)`。用户写的是接受右值的构造函数，CTAD 却悄悄造出一个以引用类型为实参的特化，这几乎总是错的。用户若想要转发语义，应写推导指引 `template<class U> W(U&&) -> W<std::decay_t<U>>;`。

## 平局时的决胜规则

CTAD 专用的决胜规则在 [[over.match.best#2.10]] 到 [[over.match.best#2.13]]，在 ICS 比较、模板偏序、约束之后才使用：

| 规则 | 内容 |
|---|---|
| 2.10 | 不是由继承构造函数生成的指引，优于由继承构造函数生成的（若对应形参类型都相同） |
| 2.11 | 由推导指引（*deduction-guide*）生成的，优于不是的 |
| 2.12 | 拷贝推导候选，优于其他 |
| 2.13 | 由非模板构造函数生成的，优于由构造函数模板生成的 |

```cpp
template <class T> struct A {
  using value_type = T;
  A(value_type);    // #1
  A(const A&);      // #2
  A(T, T, int);     // #3
  template<class U>
    A(int, T, U);   // #4
  // #5 是拷贝推导候选 A(A)
};

A x(1, 2, 3);       // 用 #3：#3 与 #4 推导结果同样好，2.13 选非模板构造函数生成的 #3

template <class T>
A(T) -> A<T>;       // #6，不如 #5 特殊

A a(42);            // 用 #6 推出 A<int>，再用 #1 初始化
A b = a;            // 用 #5 推出 A<int>（#5 比 #6 更特殊，偏序先于 2.11 起作用），再用 #2 初始化

template <class T>
A(A<T>) -> A<A<T>>; // #7，与 #5 同样特殊

A b2 = a;           // 用 #7 推出 A<A<int>>（偏序打平后，2.11 推导指引优先），再用 #1 初始化
```

`A a(42)` 为何不用 #1？#1 的形参是 `value_type`，即 `typename A<T>::value_type`，属于非推导语境，从 `42` 推不出 `T`，所以 #1 生成的指引推导失败，只有 #6 能推。

`b2` 是一个常见的陷阱：用户写的 #7 与拷贝推导候选 #5 形参都是 `A<T>`，偏序打平，于是 2.11 让推导指引胜出，`b2` 变成了 `A<A<int>>`。

## 实现视角

!!! impl
    - 主流编译器确实会实际生成这些指引：Clang 在 AST 中为每个构造函数生成隐式的 `CXXDeductionGuideDecl`（`-Xclang -ast-dump` 能看到 "implicit deduction guide"），GCC 也类似。诊断中的 "candidate template ignored" 列表列出的就是这些隐式指引。
    - 别名模板 CTAD 的可推导约束在 Clang 中实现为一个内部的类型特征（`__is_deducible`），正对应 ¶5 的 `AA` 偏特化技巧。
    - 推导指引不产生任何代码或符号，它们只参与类型推导。

## 历史与演进

!!! history
    - **C++17**：[[P0091R3]] 引入 CTAD：隐式指引、拷贝推导候选、用户推导指引；`T&&` 不是转发引用的规则；¶6.1 的单元素拷贝例外随后由缺陷报告加入。
    - **C++20**：聚合推导候选（[[P1816R0]]、[[P2082R1]]）；别名模板 CTAD（[[P1814R0]]）。
    - **C++23**：继承构造函数的 CTAD（[[P2582R1]]）。
    - **C++26**：{{c++26}} *splice-type-specifier* 也可以作为推导类型占位符的模板名。
    - 当前草案还有 ¶3 关于模板模板形参的规则。

## 陷阱

!!! pitfall "`std::vector v{x}` 与 `std::vector v{x, y}` 的类型完全不同"
    单个同类元素是拷贝，多个元素是嵌套。泛型代码里 `std::vector v{args...}` 会因 `args` 的个数而改变类型。

!!! pitfall "构造函数的 `T&&` 在 CTAD 中不是转发引用"
    需要转发语义时写推导指引。标准库的 `std::optional`、`std::tuple` 等都为此提供了推导指引。

!!! pitfall "用户推导指引压过拷贝推导候选"
    `template<class T> A(A<T>) -> A<A<T>>;` 这类指引会把原本的拷贝变成嵌套。

!!! pitfall "CTAD 不支持部分指定"
    `std::pair<int> p(1, 2.0);` 非良构：只要写了模板实参列表就不是推导类型占位符，必须写全。

## 思考题

!!! question "1. `std::tuple t{std::tuple{1}};` 推出什么类型？`std::tuple t{std::tuple{1}, 2};` 呢？"

<details markdown="1">
<summary>答案</summary>

第一个：`std::tuple<int>`。单个元素，类型是 `std::tuple` 的特化，¶6.1 跳过初始化列表阶段（`tuple` 本来也没有 `initializer_list` 构造函数）。竞争者主要有：拷贝推导候选 `template<class... Ts> tuple(tuple<Ts...>) -> tuple<Ts...>`（推得 `tuple<int>`），标准库的推导指引 `template<class... Ts> tuple(Ts...) -> tuple<Ts...>`（推得 `tuple<tuple<int>>`），以及构造函数 `tuple(const Types&...)` 生成的指引（同样推得 `tuple<tuple<int>>`）。三者的 ICS 都是恒等，于是进入决胜规则：[[over.match.best#2.5]] 的偏序排在 2.11（推导指引优先）之前，而拷贝推导候选的形参 `tuple<Ts...>` 比 `Ts...` / `const Ts&...` 更特殊，所以它胜出。

第二个：两个元素，拷贝推导候选不可行，推出 `std::tuple<std::tuple<int>, int>`。
</details>

!!! question "2. 为什么聚合推导候选要求'`C` 没有推导指引'？"

<details markdown="1">
<summary>答案</summary>

作者为聚合编写了推导指引，就表明他想精确控制推导结果。此时若再加入自动生成的聚合推导候选，它可能与用户指引竞争，并凭借 2.11 之前的 ICS 比较或偏序胜出，使用户指引失效。另外，C++17 时代为聚合写的推导指引在 C++20 中应当保持原有含义，有指引就不生成是最简单的兼容办法。
</details>

## 小结

!!! summary
    - CTAD 把构造函数翻译成函数模板（指引），做一次模板实参推导和重载决议，取胜者的返回类型。
    - 指引来源：每个构造函数；无构造函数时的 `C()`；拷贝推导候选 `C(C)`；用户推导指引；（C++20）聚合推导候选；（C++23）继承构造函数。
    - 别名模板（C++20）与模板模板形参：先把原模板的指引变换为别名的指引，并加上可推导约束。
    - ¶6.1：花括号里单个同类（或派生类）对象 → 跳过 `initializer_list` 阶段 → 拷贝。
    - 构造函数生成的指引里 `T&&` 不是转发引用；`explicit` 会传递到指引。
    - 平局时：非继承 > 继承、推导指引 > 隐式指引、拷贝推导候选 > 其他、非模板构造函数 > 构造函数模板。
