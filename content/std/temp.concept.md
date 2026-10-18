---
title: 概念定义
summary: concept-definition 的文法与限制：只能在命名空间作用域、不能有关联约束、不能被实例化或特化、不能引用自身；约束表达式是不求值操作数；原型形参与"类型概念"。
status: done
since: c++20
papers: P0734R0, P2841
related: temp.constr, temp.constr.order, temp.names, temp.param, expr.prim.req, basic.scope.pdecl, topics/concepts
tags: 概念, concept, 约束
updated: 2026-10-18
---

**概念**（concept）是一个模板，它为其模板实参定义约束（¶1）。它是 C++20 概念特性的"命名机制"：把一组要求起一个名字，在 *type-constraint*、*requires-clause*、`C auto` 占位符中使用。

概念与其他模板截然不同：它**不产生任何实体**——没有类型、没有函数、没有对象。`C<int>` 不是"概念的特化"，而是一个值为 `true` 或 `false` 的 `bool` prvalue（[[temp.names#15]]）。理解这一点，本节的所有限制就都顺理成章了。

[temp.concept] 位于 13.7 模板声明（[[temp.decls]]）之下，篇幅很短，但它的每条限制都直接服务于 [[temp.constr]] 的规范化与包含关系机制。

## 文法与声明（¶1–¶2）

¶1 文法：

```text
concept-definition:
    concept concept-name attribute-specifier-seq(opt) = constraint-expression ;
concept-name:
    identifier
```

它必须出现在 *template-head* 之后（[[temp.pre#1]]）：`template<class T> concept C = ...;`。

¶2 *concept-definition* **声明**一个概念，其标识符在其作用域内成为指称该概念的 *concept-name*。可选的属性说明符序列属于该概念（例如 `[[deprecated]]`）。

```cpp run title="concept-def.cpp" ok
#include <concepts>

template<typename T>
concept EqualityComparable = requires(T x) {
    { x == x } -> std::convertible_to<bool>;
};

template<typename T>
  requires EqualityComparable<T>      // 在 requires-clause 中使用
T f1(T x) { return x; }

template<EqualityComparable T>        // 作为 type-constraint
T f2(T x) { return x; }

auto f3(EqualityComparable auto x) { return x; }   // 约束占位符（缩写函数模板）

template<class T> concept Old [[deprecated("use EqualityComparable")]] = EqualityComparable<T>;

int main() { return f1(0) + f2(0) + f3(0); }
```

几个从文法直接推出的事实：

- **概念只能定义，不能"仅声明"**：`template<class T> concept C;` 是语法错误。没有前置声明，也就没有"声明与定义不一致"的问题。
- **不能重定义**：同一作用域中第二个同名 *concept-definition* 是重定义错误。
- **概念可以有多个模板形参、默认模板实参、形参包、常量模板形参**：

```cpp run title="concept-params.cpp" ok
template<class T, class U = int>
concept AtLeastAsBig = sizeof(T) >= sizeof(U);   // 默认模板实参
static_assert(AtLeastAsBig<long>);

template<class... Ts>
concept AllNonEmpty = ((sizeof(Ts) > 0) && ...); // 变参概念

template<int N>
concept Positive = N > 0;                        // 常量模板形参
static_assert(Positive<1> && !Positive<0>);
int main() {}
```

## 只能在命名空间作用域（¶3）

¶3 *concept-definition* 必须**栖身于命名空间作用域**（[[basic.scope.namespace]]）。

```cpp title="concept-scope.cpp" error
struct S {
    template<class T> concept C = true;   // error: 概念不能是类成员
};
void f() {
    // 块作用域中更不行：模板声明只能出现在命名空间或类作用域（[temp.pre]/4）
}
```

为什么不允许成员概念？成员概念会受到类的访问控制、可能依赖外层类模板的形参——这样在规范化时，概念的定义就可能随外层特化而变化，"同一出现"的身份比较也变得复杂。委员会选择了最简单的方案：概念是命名空间级别的实体。（可以用 *using-declaration* 把其他命名空间的概念引入。）

## 概念不能有关联约束（¶4）

¶4 **概念不能有关联约束**。即不能这样写：

```cpp title="constrained-concept.cpp" error
#include <concepts>
template<class T> requires std::integral<T>
concept C1 = sizeof(T) == 4;               // error: 概念不能有 requires-clause

template<std::integral T>
concept C2 = sizeof(T) == 4;               // error: type-constraint 也引入关联约束
```

为什么？想象 `C1<double>`：是"不满足约束，所以 `C1<double>` 非良构"，还是"`false`"？两种语义都会让概念的使用变得令人困惑。更深层的原因是规范化：concept-id 在规范化时被**内联展开**为其约束表达式（[[temp.constr.normal]]）；若概念还有一层"守门的"关联约束，内联时该把它放在哪里？标准的回答是：把要求直接写进约束表达式本身：

```cpp run title="fix-constrained.cpp" ok
#include <concepts>
template<class T>
concept C = std::integral<T> && sizeof(T) == 4;   // 正确写法：合取
static_assert(C<int> && !C<double>);
int main() {}
```

这样做还有一个额外好处：`C` 现在包含 `std::integral`（[[temp.constr.order]]），能参与重载排序。

## 概念不被实例化（¶5）

¶5 概念**不被实例化**（[[temp.spec]]）。注 1：concept-id 作为表达式被求值；概念不能被显式实例化、显式特化或部分特化。

```cpp title="no-specialization.cpp" error
template<class T> concept C = true;

template<> concept C<int> = false;    // error: 不能显式特化概念
template concept C<int>;              // error: 不能显式实例化概念
template<class T> concept C<T*> = false;   // error: 不能部分特化概念
```

不能特化是概念的**核心性质**。如果允许 `template<> concept C<int> = false;`，那么：

1. `C<int>` 的值将取决于特化是否可见——满足结果在程序不同点不同（[[temp.constr.atomic#3]] 的 IFNDR）；
2. 规范化不能再简单地把 `C<T>` 替换成"`C` 的约束表达式"，因为对某些 `T` 定义是另一个——包含关系的比较将无从进行。

如果确实需要"可定制的"判断，标准做法是让概念基于一个**可特化的特征**（trait）：

```cpp run title="customizable.cpp" ok
template<class T> constexpr bool enable_my_view = false;   // 用户可以特化这个变量模板
template<class T> concept MyView = enable_my_view<T>;

struct V {};
template<> constexpr bool enable_my_view<V> = true;

static_assert(MyView<V> && !MyView<int>);
int main() {}
```

标准库的 `std::ranges::enable_view`、`enable_borrowed_range` 正是这种模式。

## 约束表达式是不求值操作数（¶6）

¶6 *concept-definition* 的 *constraint-expression* 是**不求值操作数**（[[expr.context]]）。所以它不 odr-use 任何东西，可以引用只声明未定义的函数（如 `std::declval`）。

注意"不求值"不等于"不检查"：判定满足时，原子约束被替换并作为**常量表达式**求值（[[temp.constr.atomic#3]]）。`template<class T> concept C = (f(), true);`（`f` 非 constexpr）在定义时合法，但使用 `C<int>` 时原子约束不是常量表达式，程序非良构。

## 原型形参与类型概念（¶7）

¶7 概念定义中**第一个声明的模板形参**是它的**原型形参**（prototype parameter，[[g:prototype-parameter]]）。原型形参是类型模板形参的概念叫**类型概念**（type concept，[[g:type-concept]]）。

只有类型概念才能用作 *type-constraint*（[[temp.param#9]]）和约束占位符 `C auto`（[[dcl.spec.auto]]）——因为这两种语法都把被约束的类型**插入为第一个实参**：

```cpp title="type-concept.cpp" error
#include <concepts>
template<int N> concept Positive = N > 0;           // 原型形参是常量形参：不是类型概念
template<class T, class U> concept Same = std::same_as<T, U>;   // 类型概念（第一个形参是类型）

template<Same<int> T> struct A {};                  // OK: Same<T, int>
template<Positive T> struct B {};                   // error: Positive 不是类型概念
```

{{c++26}} 对**概念模板形参**也有原型的概念：`template<template<class> concept C>` 中的 `C` 可以用作 *type-constraint*（如 `C auto x`），前提是它的第一个形参是类型形参。

## 概念不能引用自身

¶1 的文法没有直接说，但 [[basic.scope.pdecl#14]] 规定 *concept-definition* 的声明点紧跟在 *concept-name* 之后，并以注说明：约束表达式**不能使用** *concept-name*。所以递归概念是非良构的：

```cpp title="recursive.cpp" error
template<class T> concept C = C<T*>;   // error: 概念定义不能引用自身
```

把声明点设在名字之后，是为了让约束表达式中的 `C` 一定找到**这个概念本身**（从而必然报错），而不是悄悄找到外层作用域中某个同名实体。

没有递归，规范化就一定终止：把 concept-id 不断内联展开，最终只剩原子约束。这是包含关系可判定的前提。

## 实现视角

!!! impl "实现视角"
    - **诊断**：Clang 对本节的违规有专门的诊断，例如"concept cannot have associated constraints"、"a concept definition cannot refer to itself"、"concept declarations may only appear in global or namespace scope"。
    - **概念不产生符号**：概念没有任何目标代码或修饰名意义上的实体；但当受约束的函数模板的 *requires-clause* 引用概念时，概念名会出现在该函数模板的修饰名中（Itanium 的约束编码）。
    - **规范化的缓存**：实现会为每个概念缓存其约束表达式的范式，在每次内联展开时只做参数映射的复合。

## 历史与演进

!!! history "历史与演进"
    - **Concepts TS（2015）**：概念有两种形式——**变量概念** `template<class T> concept bool C = ...;` 和**函数概念** `template<class T> concept bool C() { return ...; }`。函数概念可以重载。
    - **C++20**（[[P0734R0]] 及后续修订）：只保留一种形式 `concept C = ...;`，去掉了 `bool`；禁止重载与特化；要求在命名空间作用域。
    - **C++26**：概念可以作为模板实参传递（概念模板形参，[[P2841]]），从而出现"高阶概念"。

## 陷阱

!!! pitfall "常见误解"
    - **"可以为某个类型特化概念的结果"**——不能（¶5）。用一个可特化的变量模板作为概念的一部分。
    - **"`template<std::integral T> concept C = ...;` 只是给 `T` 加个限制"**——非良构（¶4）。
    - **"可以在类里定义辅助概念"**——不能（¶3）。
    - **"`C<T>` 是一个类型/特化"**——是 `bool` prvalue（[[temp.names#15]]）。
    - **"概念的约束表达式不求值，所以随便写"**——满足检查时原子约束必须是常量表达式且恰好为 `bool`。

## 思考题

!!! question "思考题 1"
    为什么标准禁止概念被特化，却允许变量模板被特化？`template<class T> constexpr bool C_v = ...;` 和 `template<class T> concept C = ...;` 的根本区别是什么？

<details markdown="1">
<summary>答案</summary>

变量模板的特化是一个**对象**，`C_v<T>` 的值是该对象的值，在约束中它是一个**不透明的原子约束**——编译器不看它内部，也就不在乎它是否被特化。概念的 concept-id 在约束中会被**规范化展开**为其定义的约束表达式；这一展开要求"`C<X>` 的定义对所有 `X` 都是同一个"。特化会破坏这一点，进而破坏包含关系比较。所以：想要可定制性就用变量模板（但失去包含关系）；想要参与偏序就用概念（但不能特化）。
</details>

!!! question "思考题 2"
    `template<class T, class U> concept C = ...;` 中，`template<C<int> T>` 约束的是 `C<T, int>` 还是 `C<int, T>`？

<details markdown="1">
<summary>答案</summary>

`C<T, int>`：被约束的类型总是插入为**第一个**实参（[[temp.param#9]]）。这正是 `C` 必须是类型概念（原型形参为类型形参）的原因。
</details>

## 小结

!!! summary "小结"
    | 规则 | 段落 | 违反后果 |
    |---|---|---|
    | `template<...> concept C = constraint-expression;`，只有定义没有声明 | ¶1–¶2 | 语法错误 |
    | 只能在命名空间作用域 | ¶3 | ill-formed |
    | 不能有关联约束 | ¶4 | ill-formed |
    | 不实例化、不能显式实例化/显式特化/部分特化 | ¶5 | ill-formed |
    | 约束表达式是不求值操作数 | ¶6 | — |
    | 原型形参为类型形参 ⇒ 类型概念，才能作 type-constraint | ¶7 | ill-formed |
    | 不能引用自身 | [basic.scope.pdecl]/14 | ill-formed |
