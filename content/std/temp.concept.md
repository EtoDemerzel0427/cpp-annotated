---
title: 概念定义
summary: 怎样定义一个概念，以及概念受到的限制：只能定义在命名空间作用域，不能带约束，不能被实例化或特化，不能引用自身；哪些概念能写成 type-constraint。
status: done
since: c++20
papers: P0734R0, P2841
related: temp.constr, temp.constr.order, temp.names, temp.param, expr.prim.req, basic.scope.pdecl, topics/concepts
tags: 概念, concept, 约束
updated: 2026-10-19
---

!!! tldr
    - 概念是给一组约束起的名字：`template<class T> concept C = 约束表达式;`。`C<int>` 不是一个特化，而是一个值为 `true` 或 `false` 的 `bool` 表达式。
    - 概念只能定义在命名空间作用域，不能只声明不定义，不能带 requires 子句或 type-constraint。
    - 概念不能被实例化、显式特化或部分特化。需要让用户定制时，让概念依赖一个可以特化的变量模板。
    - 概念的定义不能引用它自己，所以把概念层层展开一定会结束。
    - 只有第一个模板形参是类型形参的概念（类型概念）才能写成 `template<C T>` 或 `C auto`。

## 定义和使用一个概念（¶1–¶2）

```cpp run title="concept-def.cpp" ok
#include <concepts>

template<typename T>
concept EqualityComparable = requires(T x) {
  { x == x } -> std::convertible_to<bool>;
};

template<typename T>
  requires EqualityComparable<T>      // 用在 requires 子句里
T f1(T x) { return x; }

template<EqualityComparable T>        // 用作 type-constraint
T f2(T x) { return x; }

auto f3(EqualityComparable auto x) { return x; }   // 用作受约束的占位符

int main() { return f1(0) + f2(0) + f3(0); }
```

¶1 **概念**（concept）是一个模板，它为自己的模板实参定义约束。定义的文法是：

```text
concept-definition:
    concept concept-name attribute-specifier-seq(opt) = constraint-expression ;
```

前面还要加上 `template<...>`（[[temp.pre]]）。¶2 这个定义声明了一个概念，标识符在其作用域内成为指称它的概念名。可选的属性属于这个概念，例如可以写 `concept Old [[deprecated]] = ...;`。

概念和其他模板很不一样：它不产生任何实体，没有类型、函数或对象。写出 `C<int>` 得到的是一个 `bool` 类型的纯右值，它不是某个模板的特化（[[temp.names#15]]）。记住这一点，本节的各条限制就好理解了。

从文法可以直接看出几件事：

- 概念只能定义，不能只声明。`template<class T> concept C;` 是语法错误，所以也不存在声明和定义不一致的问题。
- 同一作用域里再定义一个同名概念，是重定义。
- 概念可以有多个形参、默认模板实参、形参包和常量形参：

```cpp run title="concept-params.cpp" ok
template<class T, class U = int>
concept AtLeastAsBig = sizeof(T) >= sizeof(U);   // 默认模板实参
static_assert(AtLeastAsBig<long>);

template<class... Ts>
concept AllNonEmpty = ((sizeof(Ts) > 0) && ...); // 形参包

template<int N>
concept Positive = N > 0;                        // 常量形参
static_assert(Positive<1> && !Positive<0>);
int main() {}
```

## 只能定义在命名空间作用域（¶3）

¶3 概念定义必须位于命名空间作用域（[[basic.scope.namespace]]）。

```cpp title="concept-scope.cpp" error
struct S {
  template<class T> concept C = true;   // error: 概念不能是类成员
};
```

模板声明本来就不能出现在块作用域里，所以剩下要排除的只有类作用域。成员概念会受访问控制影响，还可能依赖外层类模板的形参，于是同一个概念在外层的不同特化里可能有不同的定义，比较约束时判断两处是不是同一个概念也会变复杂。标准选了最简单的方案：概念只能是命名空间的成员。别的命名空间里的概念可以用 using 声明引入。

## 不能带约束（¶4）

¶4 概念不能有关联约束，也就是不能有 requires 子句，也不能用 type-constraint 声明形参：

```cpp title="constrained-concept.cpp" error
#include <concepts>
template<class T> requires std::integral<T>
concept C1 = sizeof(T) == 4;    // error: 概念不能有 requires 子句

template<std::integral T>
concept C2 = sizeof(T) == 4;    // error: type-constraint 同样引入关联约束
```

如果允许，`C1<double>` 就说不清了：是约束不满足所以写法非良构，还是值为 `false`？更深的原因在规范化：比较约束时，概念名会被替换成它的约束表达式（[[temp.constr.normal]]），额外一层关联约束没有合适的位置安放。应该把要求直接写进约束表达式：

```cpp run title="fix-constrained.cpp" ok
#include <concepts>
template<class T>
concept C = std::integral<T> && sizeof(T) == 4;
static_assert(C<int> && !C<double>);
int main() {}
```

这样写还有一个好处：`C` 包含了 `std::integral`，能参与比较哪个约束更强（[[temp.constr.order]]）。

## 不被实例化，不能特化（¶5）

¶5 概念不被实例化（[[temp.spec]]）。注 1 说明，概念名加实参（concept-id）是作为表达式求值的；概念不能被显式实例化、显式特化或部分特化。

```cpp title="no-specialization.cpp" error
template<class T> concept C = true;

template<> concept C<int> = false;          // error: 不能显式特化
template concept C<int>;                    // error: 不能显式实例化
template<class T> concept C<T*> = false;    // error: 不能部分特化
```

如果允许特化，会出两个问题。一是 `C<int>` 的结果取决于特化是否可见，同一个约束在程序不同位置会得出不同结论。二是规范化时不能再简单地把 `C<T>` 换成 `C` 的约束表达式，因为某些 `T` 用的是另一份定义，约束之间的包含关系就无从比较。

需要让用户定制时，让概念依赖一个可以特化的变量模板：

```cpp run title="customizable.cpp" ok
template<class T> constexpr bool enable_my_view = false;   // 用户可以特化它
template<class T> concept MyView = enable_my_view<T>;

struct V {};
template<> constexpr bool enable_my_view<V> = true;

static_assert(MyView<V> && !MyView<int>);
int main() {}
```

标准库的 `std::ranges::enable_view`、`std::ranges::enable_borrowed_range` 就是这样做的。

## 约束表达式是不求值操作数（¶6）

¶6 概念定义里的约束表达式是不求值操作数（[[expr.context]]），所以它不会 odr-use 任何东西，可以引用只有声明没有定义的函数，例如 `std::declval`。

不求值不等于不检查。判断约束是否满足时，每个原子约束代入实参后要作为常量表达式求值（[[temp.constr.atomic#3]]）：

```cpp error
int f();                                       // 不是 constexpr
template<class T> concept C = (f(), true);     // 定义本身没问题
static_assert(C<int>);                         // error: 原子约束不是常量表达式
```

## 原型形参与类型概念（¶7）

¶7 概念定义中第一个声明的模板形参叫它的[[g:prototype-parameter|**原型形参**]]（prototype parameter）。原型形参是类型形参的概念叫[[g:type-concept|**类型概念**]]（type concept）。

只有类型概念能用作 type-constraint（[[temp.param#9]]）或写成 `C auto`（[[dcl.spec.auto]]）。这两种写法都会把被约束的类型插进去当作第一个实参：`template<C<int> T>` 表示 `C<T, int>`。

```cpp title="type-concept.cpp" error
#include <concepts>
template<int N> concept Positive = N > 0;                     // 原型形参是常量形参
template<class T, class U> concept Same = std::same_as<T, U>; // 类型概念

template<Same<int> T> struct A {};    // OK: 约束是 Same<T, int>
template<Positive T> struct B {};     // error: Positive 不是类型概念
```

C++26 的概念模板形参也遵循这个规则：作为 type-constraint 使用时，它的第一个形参必须是类型形参（[[P2841]]）。

```cpp run ok
#include <concepts>
template<template<class> concept C, class T> requires C<T>
int f(T) { return 1; }

template<template<class> concept C>
int g(C auto x) { return x; }

int main() { return f<std::integral>(1) + g<std::integral>(1) - 2; }
```

## 概念不能引用自身

```cpp title="recursive.cpp" error
template<class T> concept C = C<T*>;   // error: 概念定义不能引用自身
```

这一条不在本节，而在 [[basic.scope.pdecl#14]]：概念定义的声明点紧跟在概念名之后，那里的注说明约束表达式不能使用这个概念名。

把声明点放在名字之后，约束表达式里的 `C` 就一定找到这个概念本身并报错，而不会悄悄找到外层作用域里某个同名的东西。没有递归，规范化时把概念名一层层替换成约束表达式就一定会结束，只剩下原子约束，比较约束的包含关系才是可判定的。

## 实现视角

!!! impl
    - Clang 对本节的违规有专门的诊断：`concept declarations may only appear in global or namespace scope`、`concept cannot have associated constraints`、`a concept definition cannot refer to itself`、`concept named in type constraint is not a type concept`。对显式特化概念的写法，它报告的是语法层面的错误。
    - 概念本身不生成任何代码或符号。

## 历史与演进

!!! history
    - Concepts TS 有两种写法：变量概念 `template<class T> concept bool C = ...;` 和函数概念 `template<class T> concept bool C() { return ...; }`，函数概念还可以重载。
    - C++20 合并概念（[[P0734R0]] 及后续修订）时只保留了 `concept C = ...;` 一种形式，去掉了 `bool`，禁止重载和特化，要求定义在命名空间作用域。
    - C++26 允许概念作为模板实参传递（概念模板形参，[[P2841]]）。

## 常见误解

!!! pitfall "可以为某个类型特化概念的结果"
    不能（¶5）。让概念依赖一个可以特化的变量模板。

!!! pitfall "`template<std::integral T> concept C = ...;` 只是给 `T` 加个限制"
    这是非良构的（¶4）。把 `std::integral<T>` 用 `&&` 写进约束表达式。

!!! pitfall "`C<T>` 是一个类型或特化"
    它是 `bool` 类型的纯右值（[[temp.names#15]]）。

!!! pitfall "约束表达式不求值，所以写什么都行"
    检查是否满足时，每个原子约束都必须是常量表达式，类型必须恰好是 `bool`。

## 思考题

!!! question "思考题 1"
    标准禁止特化概念，却允许特化变量模板。`template<class T> constexpr bool C_v = ...;` 和 `template<class T> concept C = ...;` 用在约束里，根本区别是什么？

<details markdown="1">
<summary>答案</summary>

`C_v<T>` 在约束里是一个不透明的原子约束，编译器不看它内部，也就不在乎它有没有被特化。concept-id 在规范化时会展开成概念的约束表达式，这要求 `C<X>` 对所有 `X` 用的是同一份定义；特化会破坏这一点，进而破坏包含关系的比较。所以：想要可定制，用变量模板，但它不参与包含关系；想参与重载排序，用概念，但它不能特化。
</details>

!!! question "思考题 2"
    有 `template<class T, class U> concept C = ...;`。`template<C<int> T>` 约束的是 `C<T, int>` 还是 `C<int, T>`？

<details markdown="1">
<summary>答案</summary>

`C<T, int>`。被约束的类型总是插在第一个实参的位置（[[temp.param#9]]），这也是 `C` 必须是类型概念的原因。
</details>
