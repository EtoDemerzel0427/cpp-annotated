---
title: 概念库
summary: 第 18 章的总体设计：每个库概念都由编译器检查的语法要求和程序员担保的语义要求组成；满足只看语法，建模还要符合语义；贯穿整个库的语义要求是保持相等性。
status: done
covers: concepts.general, concepts.equality, concepts.syn
since: c++20
papers: P0898R3, P1754R1
related: concepts.lang, concepts.compare, concepts.object, concepts.callable, temp.constr, temp.constr.order, temp.concept, topics/concepts, res.on.requirements, structure.requirements
tags: 标准库, 概念, 语义要求, 保持相等性
updated: 2026-10-19
---

!!! tldr
    - 每个库概念都有两层要求：编译器检查的语法要求，和只写在条文里、由程序员担保的语义要求。
    - 只符合语法叫满足（satisfy），两层都符合叫建模（model）。程序依赖于某个概念被建模、而实际只是满足时，程序是 IFNDR。
    - 库的 requires 表达式里的表达式默认都要求保持相等性：相等的输入给出相等的输出，同一个对象两次求值结果相同。
    - 概念只写出 const 左值的形式，非 const 和右值的形式也被隐含要求，但编译器不一定检查它们。
    - 标准库概念按名字互相引用，这样包含关系才成立；只在语义上细化的概念（如 `regular_invocable`）不参与重载决议的排序。

## 能编译不等于符合要求

```cpp run title="stateful-predicate.cpp" ifndr
#include <cstdio>
#include <ranges>

int main() {
  int calls = 0;
  // 结果取决于调用次数：不保持相等性
  auto first_three = [&calls](int) { return calls++ < 3; };
  auto v = std::views::iota(0, 6) | std::views::filter(first_three);
  for (int i : v) std::printf("%d ", i);   // 第一遍
  std::puts("");
  for (int i : v) std::printf("%d ", i);   // 第二遍
  std::puts("");
}
```

`views::filter` 要求谓词满足 `indirect_unary_predicate`，它最终要求 `regular_invocable`：能用这些实参调用，返回能当作 `bool` 用的值。`first_three` 完全符合，所以程序顺利编译。

可是本机 libc++ 运行它，第一遍打印 `0 1 2`，第二遍只打印 `0`。原因是 `filter_view` 在第一次调用 `begin()` 时缓存了结果，而这个谓词对同一个元素两次调用给出不同的答案。`regular_invocable` 除了可调用，还要求调用保持相等性、不修改实参，这个谓词做不到。

核心语言的概念机制（[[temp.concept]]、[[temp.constr]]，另见专题 [[topics/concepts]]）只回答一个问题：给定的模板实参能否让约束表达式为 `true`，也就是能不能编译。它不知道 `==` 是不是真的在比较相等、`<` 是不是一个序。泛型算法依赖的恰恰是后者：`sort` 依赖比较器是严格弱序，`find` 依赖 `==` 是等价关系，`filter_view` 依赖谓词对同一个元素总给出同样的答案。

¶1 [concepts.general] 第 18 章给这些约定起了名字，并写成规范性的要求。

!!! std
    The purpose of these concepts is to establish a foundation for equational reasoning in programs.

**等式推理**（equational reasoning）指像代数那样以等代等地推导代码的行为：`a == b` 时，在合适的表达式里把 `a` 换成 `b`，结果不变。

## 满足与建模

本章的每个概念都由两部分组成：

- **语法要求**（syntactic requirements）：概念定义本身，即 `concept C = ...;` 那一行，编译器检查；
- **语义要求**（semantic requirements）：定义后面的文字，形如 "`T` models `C` only if ..."，编译器不检查，由程序员担保。

!!! std
    A sequence Args of template arguments is said to *model* a concept C if Args satisfies C and meets all semantic requirements (if any) given in the specification of C.

这条定义在库的总则 [[res.on.requirements#1]] 里。**满足**（[[g:constraint-satisfaction]]）是核心语言的概念：约束代入实参后求值为 `true`（[[temp.constr.atomic]]），编译器能判断。**建模**（[[g:models-concept]]）是库的概念：满足，并且符合全部语义要求，编译器原则上无法判断。

满足而不建模有什么后果，[[res.on.requirements]] 规定了两条：

- ¶2 程序的有效性或含义依赖于某组实参是否建模某个概念，而这个概念被满足、却没有被建模，程序是 IFNDR，即非良构但不要求诊断；
- ¶3 一个声明的约束带有语义要求，而在使用处这些要求没有被建模，程序也是 IFNDR。

[[structure.requirements#9]] 补充：库函数的约束引用了某个概念时，这个概念的语义要求也一并施加到对该函数的使用上。所以开头的程序是 IFNDR；同样，给 `std::ranges::sort` 传一个 `<=` 作比较器，语法上满足 `strict_weak_order`，语义上不是严格弱序，程序也是 IFNDR。后果不只是排序结果不对，而是整个程序失去了标准的任何保证。

!!! note "为什么是 IFNDR，而不是 UB"
    违反语义要求被看作程序本身不合规，是程序的静态性质，而不是某次执行做了非法操作。诊断它需要证明任意代码的数学性质，一般不可判定，所以标准不要求诊断。实践中效果与 UB 很接近：实现可以假设语义要求成立，据此设计算法和优化。

[[structure.requirements#8]] 还规定，概念要求的操作不必是全函数，也就是说不必对所有实参都符合语义。`double` 的 `<` 遇到 NaN 时不符合 `totally_ordered` 的语义要求，但这不影响 `double` 建模 `totally_ordered`。所以下面两句话同时成立：`double` 建模 `totally_ordered`；不要把含 NaN 的数据交给 `ranges::sort`。下一节的定义域说的就是这件事。

## 保持相等性 [concepts.equality]

本章几乎每个概念的语义要求，最终都落到某个表达式保持相等性上，`<iterator>` 和 `<ranges>` 里的概念也是如此。

### 输入和输出（¶1）

!!! std
    An expression is *equality-preserving* if, given equal inputs, the expression results in equal outputs.

¶1 表达式是**保持相等性的**（[[g:equality-preserving]]），如果给定相等的输入，它总产生相等的输出。这就是数学里函数的定义：自变量相同，函数值相同。

- 表达式的**输入**是它的操作数；
- 表达式的**输出**是它的结果，加上它修改了的所有操作数。

所以 `a = std::move(b)` 的输出不只是 `=` 的返回值，还包括修改后的 `a` 和 `b`。说赋值保持相等性，意思是从相等的 `a`、`b` 出发，执行之后得到相等的 `a`、相等的 `b` 和相等的返回值。

这里的操作数有专门的定义：只由下面两种成分组成的最大子表达式。

- ¶1.1 *id-expression*（[[expr.prim.id]]），也就是变量名；
- ¶1.2 对 `std::move`、`std::forward`、`std::declval` 的调用。

例 1：`a = std::move(b)` 的操作数是 `a` 和 `std::move(b)`。这样，requires 表达式里的变量连同它们值类别的变换，被看作自变量；运算符和成员调用这些其余部分，被看作要考察的函数。

!!! note "相等不是 `==`"
    这里的相等指抽象的值相等，即两个对象表示同一个值，而不是 `==` 返回 `true`。正因为如此，`equality_comparable` 的语义要求才有内容：它要求 `a == b` 为 `true` 当且仅当 `a` 和 `b` 相等（[[concept.equalitycomparable#2]]）。`==` 要反映相等，而不是定义相等。没有 `==` 的类型，例如某些 `semiregular` 类型，它的对象之间相等仍然有意义。

### 定义域（¶2）

¶2 并非所有输入都必须有效。例 2：整数的 `a / b` 在 `b == 0` 时没有良定义，但这不妨碍 `a / b` 保持相等性。表达式被要求有良定义的那些输入值的集合，叫做它的**定义域**（[[g:expression-domain]]）。

有了定义域，不是全函数的操作也能出现在概念里：NaN 不在 `double` 的 `<` 的定义域里；指向不同数组的两个指针不在 `<` 的定义域里（[[expr.rel]]）。`assignable_from` 的注 1 也说，如果给 `x` 赋值会改变 `y`，那么 `x = y` 很可能不在 `=` 的定义域里。

### 稳定性（¶3）

!!! std
    Expressions required to be equality-preserving are further required to be stable: two evaluations of such an expression with the same input objects are required to have equal outputs absent any explicit intervening modification of those input objects.

¶3 要求保持相等性的表达式还必须是**稳定的**：用同一批输入对象求值两次，只要中间没有显式修改这些对象，输出就必须相等。¶1 讲的是相等的输入，可以是不同的对象；¶3 讲的是同一个对象在不同时刻。

有了稳定性，泛型代码可以相信刚才看到的值，下次再看还是它。注 1 列出了稳定性实际禁止的几种情况：

- 对象的值自发变化；
- 对象被另一个线程修改；
- 对象作为不修改型表达式的副作用而改变，例如 const 成员函数改了一个能被观察到的 `mutable` 成员；
- 修改另一个对象时顺带改变了它（别名），而这种改变能被库函数通过保持相等性的表达式观察到。

### 默认都要求，除非注明（¶4）

!!! std
    Expressions declared in a *requires-expression* in the library clauses are required to be equality-preserving, except for those annotated with the comment "not required to be equality-preserving."

¶4 库条款中 requires 表达式声明的表达式，默认都要求保持相等性，只有注释了 not required to be equality-preserving 的除外。所以 `equality_comparable` 的定义里看不到 `==` 要保持相等性这句话，¶4 已经替它说了。

最常见的豁免是 `invocable`：

```cpp
template<class F, class... Args>
  concept invocable = requires(F&& f, Args&&... args) {
    invoke(std::forward<F>(f), std::forward<Args>(args)...);
      // not required to be equality-preserving
  };
```

所以随机数生成器可以建模 `invocable`（[[concept.invocable#2]]），但不能建模 `regular_invocable`（[[concept.regularinvocable#2]]），后者恰好撤销了这个豁免。输入迭代器的 `++i`、`*i` 也被豁免，因为单趟遍历本来就不稳定。

被豁免的表达式也可以保持相等性，只是不被要求。

### 哪些操作数可以被修改（¶5）

¶5 表达式**修改**一个输入，是指它以能被保持相等性的表达式观察到的方式改变了这个输入的值。读 requires 表达式时有一个约定：

- 非 const 的左值或右值操作数，可以被修改；
- const 的左值或右值操作数，不得被修改。

判断 const 与值类别时，假设每个模板类型形参都是无 cv 限定的、完整的、非数组的对象类型。所以在 `requires(T a, const T c)` 里，`a` 是可修改的左值，`c` 是不可修改的左值，`std::move(a)` 是可修改的右值。

### 隐式表达式变体（¶6–¶8）

概念的作者写 `c == d`（`c`、`d` 都是 `const T`），想表达的是 `T` 的对象可以用 `==` 比较，而不是只有 const 左值才能比较。如果每个概念都要列出 const 与非 const、左值与右值的所有组合，定义会膨胀好几倍。

!!! std
    Where a *requires-expression* declares an expression that is non-modifying for some constant lvalue operand, additional variations of that expression that accept a non-constant lvalue or (possibly constant) rvalue for the given operand are also required ...

¶6 所以标准规定：requires 表达式里某个表达式对一个 const 左值操作数不做修改时，把这个操作数换成非 const 左值，或者换成右值（const 与否均可）得到的变体，也同样被要求，而且必须符合同样的语义，包括不修改这个操作数。这些变体叫**隐式表达式变体**（[[g:implicit-expression-variation]]）。如果某个变体已经以不同的语义被显式要求，就不再隐式要求它。

¶7 例 3 演示了各种情形：

```cpp
template<class T> concept C = requires(T a, T b, const T c, const T d) {
  c == d;           // #1
  a = std::move(b); // #2
  a = c;            // #3
};
```

- ¶7.1 #1 不修改任何操作数，#2 修改两个操作数，#3 只修改 `a`。
- ¶7.2 #1 隐式要求 `c == b`、`std::move(c) == d`、`a == std::move(b)` 等其余 15 种组合，它们都不得修改操作数。
- ¶7.3 #3 隐式要求 `a = b` 和 `a = std::move(c)`，但不隐式要求第二个操作数是非 const 右值的版本，因为 #2 已经显式要求了它，而且语义不同：#2 允许修改 `b`。

¶6 的最后一句是：实现在多大程度上检查这些变体的语法，是未指定的。¶8 例 4 给出了后果：

```cpp
struct T {
  bool operator==(const T&) const { return true; }
  bool operator==(T&) = delete;
};
```

`T` 符合 `C` 显式写出的语法要求，但两个非 const 左值比较时会选中被删除的重载，隐式变体不成立。所以 `T` 满足但不建模 `C`，实现是否把要求 `C<T>` 的程序诊断为非良构，是未指定的。

这不只是纸面上的问题。libc++ 只检查显式写出的 const 左值形式，于是 `std::equality_comparable<T>` 为 `true`，`ranges::find` 的约束检查顺利通过，错误到了函数体内部用非 const 左值比较时才出现：

```cpp run title="implicit-variation.cpp" error
#include <algorithm>
#include <concepts>
#include <vector>

struct T {
  bool operator==(const T&) const { return true; }
  bool operator==(T&) = delete;
};
static_assert(std::equality_comparable<T>);   // 只检查了 const 左值形式

int main() {
  std::vector<T> v(3);
  T key;
  auto it = std::ranges::find(v, key);   // error: 库内部选中了被删除的 ==
  (void)it;
}
```

本机 Clang 23 的报错位于库头文件 `ranges_operations.h` 中（`overload resolution selected deleted operator '=='`），而不是在约束检查处。错误绕过了概念的检查，在模板深处才出现，这是满足但不建模的典型症状。

### 保持相等性带来的推理能力

把上面几条合在一起，泛型算法得到了三种推理能力：

1. **可以重复求值**。算法可以对同一个元素多次调用谓词或比较器，相信结果一致；`sort` 的实现就会反复比较同一对元素。
2. **可以缓存**。`range` 概念要求 `begin()` 的摊还复杂度是常数，`filter_view`、`drop_while_view` 为此缓存第一次 `begin()` 的结果。缓存之所以正确，是因为谓词被要求建模 `regular_invocable`。开头的例子就是破坏了这一点。
3. **可以以等代等**。`a == b` 为真时，在任何保持相等性的表达式里把 `a` 换成 `b`，结果不变。

## 本章的组成 [concepts.general] [concepts.syn]

¶2 [concepts.general] 本章按表 48 分为五部分，概念都在 `<concepts>` 中：

| 子条款 | 内容 |
|---|---|
| [concepts.equality] | 保持相等性，全章的语义基础（见上文） |
| [[concepts.lang]] | 语言相关概念：`same_as`、`derived_from`、`convertible_to`、`common_reference_with`、`integral`、`assignable_from`、`swappable`、`constructible_from` 等 |
| [[concepts.compare]] | 比较概念：*`boolean-testable`*、`equality_comparable`、`totally_ordered` |
| [[concepts.object]] | 对象概念：`movable`、`copyable`、`semiregular`、`regular` |
| [[concepts.callable]] | 可调用概念：`invocable`、`predicate`、`relation`、`strict_weak_order` 等 |

`<iterator>`、`<ranges>` 以及 `<compare>` 的 `three_way_comparable`（[[cmp.concept]]）都建立在本章之上。

[concepts.syn] 头文件 `<concepts>` 整个是 freestanding 的，独立实现（[[g:freestanding-implementation]]）也必须提供，因为它只有概念定义和一个定制点对象，不需要运行时支持。概要中唯一不是概念的是：

```cpp
namespace ranges {
  inline namespace unspecified {
    inline constexpr unspecified swap = unspecified;
  }
}
```

`ranges::swap` 是一个**定制点对象**（[[g:customization-point-object]]，[[customization.point.object]]），即一个按固定规则分派到用户定制或默认实现的函数对象，详见 [[concept.swappable]]。它放在一个名字未指定的内联命名空间里，是为了让 `std::ranges` 中的类型可以有名为 `swap` 的隐藏友元而不与它冲突：对象的名字在内层命名空间，隐藏友元的名字属于外层的 `std::ranges`，两者不在同一个作用域。

## 概念之间怎样细化

本章的概念按名字互相引用，形成一张细化（refinement）关系图：

```text
destructible ← constructible_from ← default_initializable
                                  ← move_constructible ← copy_constructible
movable     = object ∧ move_constructible ∧ assignable_from<T&, T> ∧ swappable
copyable    = copy_constructible ∧ movable ∧ assignable_from<T&, T&> ∧ …
semiregular = copyable ∧ default_initializable
regular     = semiregular ∧ equality_comparable

invocable ← regular_invocable ← predicate ← relation ← equivalence_relation
                                                    ← strict_weak_order
equality_comparable ← totally_ordered
```

按 [[temp.constr.order]]，两个约束只有来自同一个概念定义里的同一处，才能比较包含关系。所以标准库总是写 `concept B = A<T> && ...`，而不把 `A` 的定义抄一遍。这样 `regular<T>` 包含 `semiregular<T>`，`f(std::regular auto)` 比 `f(std::semiregular auto)` 更受约束，`f(1)` 选中前者。

几个为包含而设计、或者需要留意的定义：

- `same_as<T, U>` 写成 `same-as-impl<T, U> && same-as-impl<U, T>`，于是 `same_as<T, U>` 和 `same_as<U, T>` 互相包含（[[concept.same]]）。
- 直接写类型特征的地方都包了一层概念，例如用 `integral<T>` 而不直接写 `is_integral_v<T>`。原因同上：原子约束 `is_integral_v<T>` 只有出现在同一个概念定义里，才算同一个约束。
- 只在语义上细化的概念不参与排序。`regular_invocable<F>` 就定义为 `invocable<F>`，`strict_weak_order` 和 `equivalence_relation` 都定义为 `relation<R, T, U>`。规范化会把概念展开成它的定义（[[temp.constr.normal]]），所以它们和被细化的概念规范化后完全相同，互相包含，谁也不比谁更受约束。

<div class="compare" markdown="1">

```cpp run ok
#include <concepts>
int g(std::semiregular auto) { return 1; }
int g(std::regular auto) { return 2; }
int y = g(1);   // OK：选中 regular 版本
```

```cpp run error
#include <concepts>
template<std::invocable F>
int f(F) { return 1; }
template<std::regular_invocable F>
int f(F) { return 2; }
int x = f([]{});   // error: 有歧义
```

</div>

纯语义的细化只是写给程序员看的契约，不参与重载决议（另见 [[concepts.callable]]）。

!!! history
    概念库由 [[P0898R3]] 在 C++20 引入，来自 Ranges TS。保持相等性、语义要求、满足与建模的区分在 Ranges TS 中已经成形。概念最初用 `PascalCase` 命名（`EqualityComparable`），[[P1754R1]] 改成了现在的 `snake_case`。之后的主要变化集中在比较概念，例如 *`boolean-testable`* 和对仅可移动类型的支持，见 [[concepts.compare]]。

## 常见误解

!!! pitfall "`static_assert` 通过了，类型就可以放心使用"
    `static_assert(std::regular<T>)` 只证明了满足。`T` 的 `==` 可能不是等价关系，复制得到的对象可能与原对象不相等，这些都只能靠代码审查和测试。

!!! pitfall "只提供 const 版本的语义就够了"
    概念只显式写出 const 左值形式，但隐式变体要求非 const、右值形式也可用，而且语义相同。为 `T&` 提供语义不同的重载，或者删除它，类型就成了满足但不建模，错误可能在库实现深处才出现。

!!! pitfall "有状态的函数对象"
    凡是受 `predicate`、`regular_invocable`、`indirect_*` 约束的地方，结果依赖调用次数的函数对象都违反语义要求。旧的 `std::` 算法对函数对象通常也有不得修改实参之类的要求；ranges 算法把它们用概念写成了正式的要求。

## 思考题

!!! question "思考题 1"
    `requires(const T a, const T b) { a < b; }` 隐式要求了哪些表达式？如果 `T` 另有一个 `bool operator<(T&&) const`，它会取走右操作数的资源，`T` 建模这个概念吗？

<details markdown="1">
<summary>答案</summary>

隐式要求把 `a`、`b` 分别换成非 const 左值、const 右值、非 const 右值后的所有组合，而且它们都不得修改操作数（¶6）。右操作数是非 const 右值时会选中 `operator<(T&&)`，它修改了操作数，违反了不修改的语义要求。所以 `T` 满足但不建模这个概念。实现是否诊断是未指定的（¶6 末句）。
</details>

!!! question "思考题 2"
    `std::uniform_int_distribution<int>` 加上 `std::mt19937&` 能建模 `invocable` 吗？能建模 `regular_invocable` 吗？编译器能区分这两种情况吗？

<details markdown="1">
<summary>答案</summary>

能建模 `invocable`，它的调用表达式被豁免，不要求保持相等性（[[concept.invocable#2]]）。不能建模 `regular_invocable`（[[concept.regularinvocable#2]]）。编译器无法区分，两者的语法要求完全相同（[[concept.regularinvocable#3]]），`std::regular_invocable<...>` 照样为 `true`。
</details>

!!! question "思考题 3"
    稳定性的注 1 禁止对象被另一个线程修改。这和 [[intro.races]] 中数据竞争导致 UB 有什么不同？

<details markdown="1">
<summary>答案</summary>

稳定性是语义要求，违反它使程序成为 IFNDR（[[res.on.requirements]]）。即使另一个线程用原子操作修改对象，按 [[intro.races]] 不构成数据竞争，也同样违反稳定性。所以概念的要求比没有数据竞争更强：即使没有 UB，值在算法观察它的期间也不能改变。
</details>
