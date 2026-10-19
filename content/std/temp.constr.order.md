---
title: 按约束的偏序
summary: 两个声明都满足约束时谁更受约束：包含关系怎样用析取范式和合取范式定义，原子约束为什么只在相同时包含，至少一样受约束与更受约束的区别，以及类模板的非模板成员函数怎样仅凭约束重载。
status: done
since: c++20
papers: P2963R3, P2841
related: temp.constr, temp.concept, over.match.best, temp.func.order, temp.spec.partial.order, temp.arg.template, over.over, topics/concepts
tags: 概念, 约束, 包含关系, subsumption, 重载决议
updated: 2026-10-19
---

!!! tldr
    - 两个重载都满足约束时，约束更强的胜出；更强的意思是它的约束包含（subsume）对方的约束。
    - 包含是纯粹的命题逻辑：合取越多越强，析取越多越弱，原子约束之间只看是否相同，不看语义。
    - 原子约束只有来自同一处表达式才相同，所以要让约束参与排序，就把较弱的约束写成概念，在较强的概念里引用它。
    - 没有约束的声明最弱；两个互不包含的约束谁也不比谁强，调用歧义。
    - 类模板里签名相同的非模板成员函数也能按约束排序，C++20 起据此可以写多个析构函数，按条件选出平凡的那个。

## 按约束重载

```cpp run title="overload-by-constraint.cpp" ok
#include <iterator>
#include <list>
#include <vector>
#include <cstdio>

template<std::forward_iterator I>       void advance_impl(I) { std::puts("forward"); }
template<std::bidirectional_iterator I> void advance_impl(I) { std::puts("bidirectional"); }
template<std::random_access_iterator I> void advance_impl(I) { std::puts("random access"); }

int main() {
    std::vector<int> v; std::list<int> l;
    advance_impl(v.begin());   // random access：三个都满足，选约束最强的
    advance_impl(l.begin());   // bidirectional
}
```

`vector` 的迭代器同时满足三个概念，编译器选了 `random_access_iterator` 那个，因为 `random_access_iterator` 的定义里引用了 `bidirectional_iterator`，后者又引用了 `forward_iterator`。C++20 之前做到这一点要靠标签分派（`iterator_category`），或者手工写出互斥的 SFINAE 条件。

[[temp.constr]] 讲了约束怎样规范化成由合取（∧）、析取（∨）和原子约束组成的结构，以及原子约束什么时候相同。本页讲怎样用这些结构比较两个约束的强弱。

## 包含（¶1）

¶1 约束 `P` **包含**（[[g:subsumes|subsumes]]）约束 `Q`，当且仅当 `P` 的析取范式中的每个子句，都包含 `Q` 的合取范式中的每个子句。其中：

- ¶1.1 一个析取子句包含一个合取子句，当且仅当前者中有某个原子约束包含后者中的某个原子约束；
- ¶1.2 原子约束 `A` 包含原子约束 `B`，当且仅当两者相同（[[temp.constr.atomic#2]]）；
- ¶1.3 {{c++26}} 折叠展开约束 `A` 包含 `B`，要求两者适于比较包含（[[temp.constr.fold#5]]）、折叠运算符相同，并且 `A` 的约束包含 `B` 的约束。

两种范式在脚注 103、104 中定义。**析取范式**（DNF）是若干子句的析取，每个子句是原子约束（或折叠展开约束）的合取；**合取范式**（CNF）反过来，是若干析取子句的合取。以 `A ∧ (B ∨ C)` 为例：

| 范式 | 写法 | 子句 |
|---|---|---|
| DNF | `(A ∧ B) ∨ (A ∧ C)` | `A ∧ B`、`A ∧ C` |
| CNF | `A ∧ (B ∨ C)` | `A`、`B ∨ C` |

### 为什么这样定义就是蕴含

把每个原子约束看成一个独立的命题变量。`P` 蕴含 `Q`，就是 `P` 的每一种成立方式（DNF 的每个子句，一组同时成立的原子）都使 `Q` 的每个必要条件（CNF 的每个子句，一组原子中至少一个成立）成立。原子之间没有任何逻辑关系时，一组同时成立的原子能使一个析取成立，当且仅当两者有共同的原子。这就是 ¶1.1。

原子之间没有任何关系，是理解包含的关键。`sizeof(T) > 4` 在语义上蕴含 `sizeof(T) > 2`，但对包含规则来说，它们是两个毫不相干的命题变量。

### 例子（例 1）

设 `A`、`B` 是原子约束：

| 关系 | 是否包含 | 原因 |
|---|---|---|
| `A ∧ B` 包含 `A` | 是 | DNF 子句 `A ∧ B` 与 CNF 子句 `A` 有共同的 `A` |
| `A` 包含 `A ∧ B` | 否 | DNF 子句 `A` 与 CNF 子句 `B` 没有共同的原子 |
| `A` 包含 `A ∨ B` | 是 | CNF 只有一个子句 `A ∨ B`，含有 `A` |
| `A ∨ B` 包含 `A` | 否 | DNF 子句 `B` 与 CNF 子句 `A` 没有共同的原子 |
| 任何约束包含它自己 | 是 | |

要求 A 且 B 比只要求 A 更严，要求 A 或 B 比只要求 A 更宽：

```cpp run title="subsume-basic.cpp" ok
template<class T> concept P = sizeof(T) >= 1;
template<class T> concept Q = alignof(T) >= 1;

template<class T> constexpr int g(T) requires P<T> || Q<T> { return 1; }
template<class T> constexpr int g(T) requires P<T>         { return 2; }

template<class T> constexpr int h(T) requires P<T> && Q<T> { return 1; }
template<class T> constexpr int h(T) requires P<T>         { return 2; }

static_assert(g(1) == 2);   // P 包含 P ∨ Q：第二个更受约束
static_assert(h(1) == 1);   // P ∧ Q 包含 P：第一个更受约束
int main() {}
```

### 同样的表达式写两遍不构成包含

<div class="compare" markdown="1">

```cpp error
#include <type_traits>
template<class T> int f(T)
  requires std::is_integral_v<T>
{ return 1; }
template<class T> int f(T)
  requires std::is_integral_v<T>
        && std::is_signed_v<T>
{ return 2; }

int r = f(1);   // error: 歧义
```

```cpp run ok
#include <type_traits>
template<class T> concept Integral =
  std::is_integral_v<T>;
template<class T> concept SignedIntegral =
  Integral<T> && std::is_signed_v<T>;

template<class T> int f(T)
  requires Integral<T>       { return 1; }
template<class T> int f(T)
  requires SignedIntegral<T> { return 2; }

int main() { return f(1) == 2 ? 0 : 1; }
```

</div>

按 ¶1.2，原子约束只在相同时包含，而相同要求来自同一个表达式的同一次出现。左边的两个 `std::is_integral_v<T>` 是两次出现，第二个声明的约束不包含第一个的，调用歧义。右边的两个 `std::is_integral_v<T>` 都来自 `Integral` 定义中的那一处，`SignedIntegral` 包含 `Integral`。

所以想让约束参与重载排序，就把它定义成概念，并在更强的概念里通过名字引用更弱的概念。标准库的概念层次，如 `std::integral` 与 `std::signed_integral`、`std::forward_iterator` 与 `std::bidirectional_iterator`，都是这样搭起来的。

requires 表达式也是一个整体的原子约束。`requires (T t) { t.a(); t.b(); }` 与 `requires (T t) { t.a(); }` 之间没有包含关系；要让它们可比较，把 `t.a()` 提取成概念 `HasA`，再定义 `HasAB = HasA<T> && requires (T t) { t.b(); }`。

### 折叠展开约束的包含（¶1.3）{{c++26}}

```cpp run title="fold-order.cpp" ok
#include <concepts>

template<class... Ts> requires (std::integral<Ts> && ...)
constexpr int k(Ts...) { return 1; }
template<class... Ts> requires (std::signed_integral<Ts> && ...)
constexpr int k(Ts...) { return 2; }

static_assert(k(1, 2) == 2);   // signed_integral 的折叠包含 integral 的折叠
int main() {}
```

两个折叠展开的是同一个包 `Ts`，运算符都是 `&&`，`std::signed_integral<Ts>` 又包含 `std::integral<Ts>`，所以第二个更受约束。C++23 中两个折叠表达式都是普通的原子约束，彼此不包含，这个调用是歧义的。

## 至少一样受约束与更受约束（¶3–¶5）

```cpp run title="more-constrained.cpp" ok
#include <cstdio>
template<typename T> concept C1 = requires(T t) { --t; };
template<typename T> concept C2 = C1<T> && requires(T t) { *t; };

template<C1 T> void f(T) { std::puts("#1"); }
template<C2 T> void f(T) { std::puts("#2"); }
template<typename T> void g(T) { std::puts("#3"); }
template<C1 T> void g(T) { std::puts("#4"); }

int main() {
    f(0);           // #1：int 不满足 C2
    f((int*)0);     // #2：两者都满足，C2 包含 C1
    g(true);        // #3：bool 不能 --，C1<bool> 不满足
    g(0);           // #4：两者都满足，#4 有约束而 #3 没有
}
```

包含是约束之间的关系，重载决议比较的是声明。¶4 声明 `D1` **至少和** `D2` **一样受约束**（at least as constrained），如果：

- ¶4.1 两者都有约束，`D1` 的关联约束适于包含（见下），并且包含 `D2` 的关联约束；或者
- ¶4.2 `D2` 没有关联约束。

¶5 `D1` 至少和 `D2` 一样受约束，而 `D2` 不至少和 `D1` 一样受约束时，`D1` **比** `D2` **更受约束**（[[g:more-constrained|more constrained]]）。上例中 `g(0)` 选 #4，用的就是 ¶4.2：任何声明都至少和无约束的声明一样受约束。两个都没有约束的声明互相至少一样受约束，谁也不比谁更受约束。

¶3 {{c++26}} 声明的关联约束含有概念依赖约束（[[temp.constr.concept]]，形如 `X<T>`，`X` 是概念模板形参）时，**不适于包含**（not eligible for subsumption），否则适于包含。`X<T>` 在模板定义处无法展开，将来可能是任何概念，无法与别的约束比较。

### 标准例 3：条文与例子不一致

```cpp
template<template<typename T> concept CT, typename T>
struct S {};
template<typename T>
concept A = true;

template<template<typename T> concept X, typename T>
int f(S<X, T>) requires A<T> { return 42; }      // #1
template<template<typename T> concept X, typename T>
int f(S<X, T>) requires X<T> { return 43; }      // #2

int r = f(S<A, int>{});   // 标准注释：OK，选 #1，因为 #2 不适于包含
```

!!! lawyer "按字面推导是歧义"
    #1 要至少和 #2 一样受约束，按 ¶4.1 需要 #1 的约束（`A` 定义中的原子约束 `true`）包含 #2 的约束（概念依赖约束 `X<T>`）。按 ¶1.2，原子约束只在相同时包含，`true` 与 `X<T>` 并不相同。另一方面，#2 的约束不适于包含，#2 也不至少和 #1 一样受约束。照字面，两者都不更受约束，调用歧义。

    例子的意图显然是让不适于包含的声明在比较中吃亏，但规范性条文没有写出这一点。本机 Clang 23 对这个调用报告歧义。依赖这一行为之前，应当查阅最新草案和相关的核心语言 issue。

## 非模板函数按约束排序（¶6）

¶6 两个非模板函数 `F1`、`F2` 在下面几条都成立时，`F1` 比 `F2` **更偏序受约束**（more partial-ordering-constrained）：

- ¶6.1 两者的非对象形参类型列表相同（[[dcl.fct]]）；
- ¶6.2 如果是成员函数，两者都是同一个类的直接成员；
- ¶6.3 如果都是非静态成员函数，两者的对象形参类型相同；
- ¶6.4 `F1` 的声明比 `F2` 的更受约束。

非模板函数怎么会有约束？类模板的成员函数不是模板，但它是模板化的实体，可以带尾随 *requires-clause*。两个这样的候选转换序列不分高下时，更偏序受约束者胜出（[[over.match.best#2.6]]）；取函数地址时也按同样的规则挑选（[[over.over]]）。

```cpp run title="non-template.cpp" ok
#include <string>
#include <type_traits>

template<class T>
struct W {
    int f() requires std::is_integral_v<T> { return 1; }
    int f() { return 2; }       // 无约束
};
int a = W<int>{}.f();       // 1：两者都可行，第一个更偏序受约束
int b = W<double>{}.f();    // 2：第一个不满足

// 按约束选择析构函数
template<class T>
struct Box {
    T t;
    ~Box() requires std::is_trivially_destructible_v<T> = default;
    ~Box() {}
};
static_assert(std::is_trivially_destructible_v<Box<int>>);
static_assert(!std::is_trivially_destructible_v<Box<std::string>>);
int main() {}
```

`Box` 是这条规则最重要的用途。`std::optional`、`std::variant` 要求 `T` 平凡可析构时自身也平凡可析构。C++20 之前只能继承一个按条件特化的基类来实现；C++20 允许一个类声明多个**预期析构函数**（prospective destructor，[[class.dtor]]），由重载决议按约束选出真正的析构函数。复制、移动构造函数和赋值运算符也可以这样按条件做成平凡的。

¶6.1–¶6.3 把比较限制在签名相同、只有约束不同的函数之间。否则 `void f(int) requires A` 与 `void f(long) requires B` 也要按约束排序，参数类型匹配得更差的函数可能因为约束更多而胜出。

## 这个偏序用在哪里（¶2）

¶2 注 1 列出了包含关系的用途：

- ¶2.1 非模板函数之间选最佳可行函数（[[over.match.best]]）；
- ¶2.2 取非模板函数的地址（[[over.over]]）；
- ¶2.3 模板模板实参的匹配（[[temp.arg.template]]）；
- ¶2.4 类模板部分特化的偏序（[[temp.spec.partial.order]]）；
- ¶2.5 函数模板的偏序（[[temp.func.order]]）。

## 实现视角

!!! impl "范式的代价与诊断"
    - 范式转换在最坏情况下是指数级的。`(A1 ∨ B1) ∧ (A2 ∨ B2) ∧ ... ∧ (An ∨ Bn)` 的 DNF 有 2ⁿ 个子句。实际代码里的约束很少复杂到这个程度。
    - 本机 Clang 23 报告歧义时，如果发现两个原子约束写法相同但不相同，会附加一条说明：相似的约束表达式不视为等价，除非它们来自同一个概念。

## 历史与演进

!!! history
    - C++20 随概念一起引入了基于 DNF、CNF 的包含规则，以及非模板函数按约束排序（用于预期析构函数等）。
    - C++26 加入折叠展开约束之间的包含（¶1.3，[[P2963R3]]），以及随概念模板形参而来的适于包含的限制（¶3，[[P2841]]）。

## 常见误解

!!! pitfall "语义上更强的约束就更受约束"
    包含只看结构和身份，`sizeof(T) > 4` 不包含 `sizeof(T) > 2`。

!!! pitfall "加括号或包一层会不会影响包含"
    `(C<T> && D<T>)` 和 `C<T> && D<T>` 一样包含 `C<T>`，括号在规范化时不起作用。但 `bool(C<T> && D<T>)` 或 `(C<T> && D<T>) == true` 整体变成了一个原子约束，不再包含任何别的约束。

!!! pitfall "编译器会利用 `!A<T>` 与 `A<T>` 互斥"
    不会。包含关系里没有否定，`!A<T>` 只是另一个原子约束。

!!! pitfall "两个互不包含的约束，选条件多的那个"
    约束的条数没有意义。互不包含就是歧义。

## 思考题

!!! question "思考题 1"
    设 `A`、`B`、`C` 是原子约束。`(A ∨ B) ∧ C` 是否包含 `A ∨ (B ∧ C)`？反过来呢？

<details markdown="1">
<summary>答案</summary>

`P = (A ∨ B) ∧ C` 的 DNF 是 `(A ∧ C) ∨ (B ∧ C)`。`Q = A ∨ (B ∧ C)` 的 CNF 是 `(A ∨ B) ∧ (A ∨ C)`。

- `A ∧ C` 与 `A ∨ B` 有共同的 `A`，与 `A ∨ C` 也有；
- `B ∧ C` 与 `A ∨ B` 有共同的 `B`，与 `A ∨ C` 有共同的 `C`。

所以 `P` 包含 `Q`。

反过来，`Q` 的 DNF 子句是 `A` 和 `B ∧ C`，`P` 的 CNF 子句是 `A ∨ B` 和 `C`。子句 `A` 与 `C` 没有共同的原子，所以 `Q` 不包含 `P`。这与命题逻辑的结论一致：`P` 成立时 `C` 成立且 `A`、`B` 至少一个成立，于是 `A` 或 `B ∧ C` 成立。
</details>

!!! question "思考题 2"
    下面的调用选哪个？

    ```cpp
    template<class T> concept C = true;
    template<class T> concept D = C<T>;
    template<class T> int f(T) requires C<T>;
    template<class T> int f(T) requires D<T>;
    int x = f(0);
    ```

<details markdown="1">
<summary>答案</summary>

歧义。`D<T>` 规范化后就是 `C<T>` 的范式，即 `C` 定义中的原子约束 `true`；`C<T>` 规范化也是同一个 `true`。两个声明的关联约束相同，互相包含，谁也不比谁更受约束。概念的名字不同，不代表约束不同。
</details>

!!! question "思考题 3"
    为什么 ¶6 要求两个非模板函数的非对象形参类型列表相同，才按约束比较？

<details markdown="1">
<summary>答案</summary>

约束只应在其他条件都相同时用来决胜。如果参数类型不同的函数也按约束排序，就可能出现参数匹配更差、但约束更多的函数胜出的情况，也与函数模板偏序不一致：函数模板只有在按推导互相一样特殊时才比较约束（[[temp.func.order]]）。¶6.1–¶6.3 把比较限定在同一个类中签名相同的函数之间，这正是预期析构函数和按条件平凡的特殊成员函数所需要的。
</details>
