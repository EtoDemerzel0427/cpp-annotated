---
title: 按约束的偏序
summary: 包含关系（subsumption）的精确定义——P 的析取范式的每个子句包含 Q 的合取范式的每个子句；原子约束只在"相同"时包含；"至少一样受约束"与"更受约束"；含概念依赖约束的声明不适于包含；非模板函数的"更偏序受约束"。
status: done
since: c++20
papers: P2963R3, P2841
related: temp.constr, temp.concept, over.match.best, temp.func.order, temp.spec.partial.order, temp.arg.template, over.over, topics/concepts
tags: 概念, 约束, 包含关系, subsumption, 重载决议
updated: 2026-10-17
---

[[temp.constr]] 回答"约束是否被满足"；本节回答另一个问题：**两个声明都满足时，谁更受约束？**这是概念最有价值的能力——按约束重载：

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
    advance_impl(v.begin());   // random access：三个都满足，random_access 最受约束
    advance_impl(l.begin());   // bidirectional
}
```

在 C++20 之前，这种"选最特殊的那个"需要标签分派（`iterator_category`）或精心构造的 SFINAE 互斥条件。概念让编译器**自动**判断：`random_access_iterator` 的定义包含了 `bidirectional_iterator`，后者又包含 `forward_iterator`，所以前者"更受约束"。

判断"包含"的方法就是本节的内容。它是纯粹的**命题逻辑**：把约束看成原子命题的与或组合，问"P 是否蕴含 Q"——而原子命题之间**只按身份**比较（[[temp.constr.atomic#2]]），不看语义。

## 包含（¶1）

¶1 约束 `P` **包含**（subsumes，[[g:subsumes]]）约束 `Q`，当且仅当：对 `P` 的**析取范式**（DNF）中的每个析取子句 `Pi`，`Pi` 包含 `Q` 的**合取范式**（CNF）中的每个合取子句 `Qj`。其中：

- ¶1.1 析取子句 `Pi` 包含合取子句 `Qj`，当且仅当 `Pi` 中**存在**原子约束 `Pia`，`Qj` 中**存在**原子约束 `Qjb`，使 `Pia` 包含 `Qjb`；
- ¶1.2 原子约束 `A` 包含原子约束 `B`，当且仅当 `A` 与 `B` **相同**（按 [[temp.constr.atomic]] 的规则）；
- ¶1.3 {{c++26}} 折叠展开约束 `A` 包含折叠展开约束 `B`，当它们适于比较包含（[[temp.constr.fold#5]]）、折叠运算符相同、且 `A` 的约束包含 `B` 的约束。

脚注 103/104 解释了两种范式：

- **析取范式**：若干子句的析取，每个子句是（折叠展开或原子）约束的合取。`A ∧ (B ∨ C)` 的 DNF 是 `(A ∧ B) ∨ (A ∧ C)`，析取子句为 `(A ∧ B)` 和 `(A ∧ C)`。
- **合取范式**：若干子句的合取，每个子句是约束的析取。`A ∧ (B ∨ C)` 本身就是 CNF，合取子句为 `A` 和 `(B ∨ C)`。

### 为什么这个定义等价于"蕴含"？

把原子约束看成独立的命题变量，`P ⇒ Q` 在命题逻辑中成立，当且仅当：`P` 的每一种"成立方式"（DNF 的每个子句，一个合取）都能使 `Q` 的每个"必要条件"（CNF 的每个子句，一个析取）成立。而"一个合取使一个析取成立"——在原子之间没有任何逻辑关系的前提下——当且仅当它们**共享一个原子**。这就是 ¶1.1。

这里的关键前提是"原子之间没有任何逻辑关系"：`sizeof(T) > 4` 与 `sizeof(T) > 2` 在语义上有蕴含关系，但对包含规则来说它们是两个毫不相干的命题变量。

### 例子（例 1）

设 `A`、`B` 是原子约束：

| 关系 | 是否包含 | 原因 |
|---|---|---|
| `A ∧ B` 包含 `A` | 是 | DNF 子句 `(A ∧ B)` 与 CNF 子句 `A` 共享 `A` |
| `A` 包含 `A ∧ B` | 否 | DNF 子句 `A` 与 CNF 子句 `B` 不共享原子 |
| `A` 包含 `A ∨ B` | 是 | CNF 只有一个子句 `(A ∨ B)`，与 `A` 共享 `A` |
| `A ∨ B` 包含 `A` | 否 | DNF 子句 `B` 与 CNF 子句 `A` 不共享 |
| 任何约束包含它自己 | 是 | |

直觉：**合取越多越强，析取越多越弱**。"要求 A 且 B"比"要求 A"更严；"要求 A 或 B"比"要求 A"更宽。

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

### 经典陷阱：相同的表达式写两遍不构成包含

¶1.2 说原子约束只在**相同**时包含，而"相同"要求来自**同一表达式的同一出现**（[[temp.constr.atomic#2]]）。所以：

```cpp title="spelled-twice.cpp" error
#include <type_traits>

template<class T> int f(T) requires std::is_integral_v<T> { return 1; }
template<class T> int f(T) requires std::is_integral_v<T> && std::is_signed_v<T> { return 2; }

int r = f(1);   // error: 歧义——两个 std::is_integral_v<T> 是不同的出现，第二个不包含第一个
```

修正方法是**给约束命名**：

```cpp run title="named.cpp" ok
#include <type_traits>

template<class T> concept Integral = std::is_integral_v<T>;
template<class T> concept SignedIntegral = Integral<T> && std::is_signed_v<T>;

template<class T> int f(T) requires Integral<T>       { return 1; }
template<class T> int f(T) requires SignedIntegral<T> { return 2; }

int main() { return f(1) == 2 ? 0 : 1; }   // OK: SignedIntegral 包含 Integral
```

两个 `std::is_integral_v<T>` 现在都来自 `Integral` 定义中的**同一出现**，于是相同。这条规则的工程含义：**想让约束参与重载排序，就把它定义成概念，并在更强的概念中通过名字引用更弱的概念**。标准库的概念层次（`std::integral` → `std::signed_integral`，`std::input_iterator` → `std::forward_iterator` → ...）就是这样搭起来的。

!!! pitfall "requires 表达式也是原子"
    `requires (T t) { t.a(); t.b(); }` 与 `requires (T t) { t.a(); }` 之间**没有**包含关系：每个 *requires-expression* 都是一个不可分解的原子约束（[[temp.constr.normal]]）。要让它们可比较，把 `t.a()` 提取成概念 `HasA`，再定义 `HasAB = HasA<T> && requires (T t) { t.b(); }`。

### 折叠展开约束的包含（¶1.3）{{c++26}}

¶1.3 让 `(C<Ts> && ...)` 与 `(D<Ts> && ...)` 之间可以比较：若 `D` 包含 `C`，则后者包含前者——前提是两者展开的是**等价的同一个包**，且折叠运算符相同。

```cpp run title="fold-order.cpp" ok
#include <concepts>

template<class... Ts> requires (std::integral<Ts> && ...)
constexpr int k(Ts...) { return 1; }
template<class... Ts> requires (std::signed_integral<Ts> && ...)
constexpr int k(Ts...) { return 2; }

static_assert(k(1, 2) == 2);   // C++26：signed_integral 的折叠包含 integral 的折叠
int main() {}
```

在 C++23 中，两个折叠表达式都是普通的原子约束（不同出现），彼此不包含，上面的调用歧义。

## 偏序的用途（¶2）

¶2 注 1：包含关系定义了约束上的一个偏序，它用于决定：

- ¶2.1 非模板函数的最佳可行候选（[[over.match.best]] ¶2.6）；
- ¶2.2 非模板函数的地址（[[over.over]]）；
- ¶2.3 模板模板实参的匹配（[[temp.arg.template]]）；
- ¶2.4 类模板部分特化的偏序（[[temp.spec.partial.order]]）；
- ¶2.5 函数模板的偏序（[[temp.func.order]]）。

注意 ¶2.1 和 ¶2.2 中的"**非模板**函数"——例如类模板的成员函数（它们是 templated 但不是模板），可以仅凭尾随 *requires-clause* 重载。

## 适于包含（¶3）{{c++26}}

¶3 声明 `D` 的关联约束 `C` **适于包含**（eligible for subsumption），除非 `C` 含有**概念依赖约束**（[[temp.constr.concept]]）。

原因：概念依赖约束 `X<T>`（`X` 是概念模板形参）在模板定义处无法展开，它将来可能展开成任何东西，因而无法与其他约束做有意义的比较。

## 至少一样受约束；更受约束（¶4–¶5）

¶4 声明 `D1` **至少和** `D2` **一样受约束**（at least as constrained），如果：

- ¶4.1 `D1` 和 `D2` 都是受约束的声明，且 `D1` 的关联约束适于包含并包含 `D2` 的关联约束；或
- ¶4.2 `D2` 没有关联约束。

¶5 `D1` **比** `D2` **更受约束**（more constrained，[[g:more-constrained]]），当 `D1` 至少和 `D2` 一样受约束，而 `D2` 不至少和 `D1` 一样受约束。

注意 ¶4.2：**任何声明都至少和无约束的声明一样受约束**——包括另一个无约束的声明。所以两个无约束的声明互相"至少一样受约束"，谁也不比谁更受约束。

标准例 2：

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
    g(true);        // #3：C1<bool> 不满足（bool 不能 --）
    g(0);           // #4：两者都满足，#4 受约束而 #3 不受约束
}
```

`g(true)` 值得一说：`bool` 从来不支持 `--`（`bool` 的 `++` 也在 C++17 中被移除），所以 `C1<bool>` 不满足。

### 例 3：概念依赖约束不参与

标准例 3 展示 ¶3 的效果：

```cpp
template<template<typename T> concept CT, typename T>
struct S {};
template<typename T>
concept A = true;

template<template<typename T> concept X, typename T>
int f(S<X, T>) requires A<T> { return 42; }      // #1
template<template<typename T> concept X, typename T>
int f(S<X, T>) requires X<T> { return 43; }      // #2

f(S<A, int>{});    // 标准注释：OK，选 #1，因为 #2 不适于包含
```

!!! lawyer "这个例子值得推敲"
    按 ¶4.1 的字面，`#1` 至少和 `#2` 一样受约束，需要 `#1` 的约束（来自 `A` 的原子约束 `true`）**包含** `#2` 的约束（概念依赖约束 `X<T>`）。而按 ¶1.2，原子约束只在相同时包含，`true` 与 `X<T>` 显然不相同。另一方面，`#2` 的约束不适于包含，所以 `#2` 也不至少和 `#1` 一样受约束。字面推导的结果似乎是"两者都不更受约束"，即调用歧义。

    标准例子的结论是选择 `#1`，其意图显然是"不适于包含的声明在比较中处于劣势"。截至写作时，Clang 23 对此调用报告**歧义**。这是一个值得关注的条文与示例之间的张力；读者在依赖此行为前应查阅最新草案与相关核心语言 issue。

## 非模板函数的"更偏序受约束"（¶6）

¶6 非模板函数 `F1` 比非模板函数 `F2` **更偏序受约束**（more partial-ordering-constrained），如果：

- ¶6.1 它们有相同的**非对象形参类型列表**（[[dcl.fct]]）；
- ¶6.2 若是成员函数，两者都是同一个类的**直接成员**；
- ¶6.3 若都是非静态成员函数，它们的对象形参类型相同；
- ¶6.4 `F1` 的声明比 `F2` 的声明更受约束。

这是 [[over.match.best]] ¶2.6 的依据：两个非模板函数（例如类模板的成员函数）的转换序列不分高下时，更偏序受约束者胜出。¶6.1–¶6.3 的限制保证只在"签名相同、仅约束不同"的函数之间按约束比较——否则两个参数类型不同的函数按约束排序没有意义。

```cpp run title="non-template.cpp" ok
#include <string>
#include <type_traits>

template<class T>
struct W {
    int f() requires std::is_integral_v<T> { return 1; }
    int f() { return 2; }       // 无约束
};

static_assert(std::is_same_v<decltype(W<int>{}.f()), int>);
int a = W<int>{}.f();       // 1：两者都可行，第一个更偏序受约束
int b = W<double>{}.f();    // 2：第一个不满足

// C++20 "预期析构函数"：按约束选择析构函数
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

`Box` 展示了这条规则最重要的应用：`std::optional`、`std::variant` 需要"当 `T` 平凡可析构时自身也平凡可析构"。C++20 之前要靠继承一个按条件特化的基类来实现；C++20 允许声明多个**预期析构函数**（prospective destructor，[[class.dtor]]），由重载决议按约束选出真正的析构函数。复制/移动构造函数、赋值运算符同理（"条件平凡的特殊成员函数"）。

## 实现视角

!!! impl "实现视角"
    - **范式转换的代价**：DNF/CNF 转换在最坏情况下是指数级的。`(A1 ∨ B1) ∧ (A2 ∨ B2) ∧ ... ∧ (An ∨ Bn)` 的 DNF 有 2ⁿ 个子句。实现通常设有上限并在超出时报错；实践中约束很少如此复杂。
    - **诊断**：Clang 在歧义时若发现两个原子约束"记号相同但不相同"，会附加提示说明它们必须来自同一个概念才能被视为等价。这条提示是理解 ¶1.2 的最好老师。

## 历史与演进

!!! history "历史与演进"
    - **Concepts TS**：已有基于 DNF/CNF 的包含定义。早期设计中原子约束的相同性按表达式**等价**判断，C++20 最终版改为"同一出现"，以避免比较任意表达式的困难与脆弱性。
    - **C++20**：本节成形；非模板函数可按约束重载（用于预期析构函数等）。
    - **C++26**：折叠展开约束的包含（¶1.3，[[P2963R3]]）；"适于包含"（¶3）随概念模板形参引入（[[P2841]]）。

## 陷阱

!!! pitfall "常见误解"
    - **"语义上更强的约束就更受约束"**——包含只看结构和身份。`sizeof(T) > 4` 不包含 `sizeof(T) > 2`。
    - **"写两遍相同的表达式就行"**——必须通过同一个具名概念（同一出现）。
    - **"`C<T> && D<T>` 包含 `C<T>`，那 `(C<T> && D<T>)` 加了括号也一样"**——一样，括号在规范化中透明。但 `bool(C<T> && D<T>)` 或 `(C<T> && D<T>) == true` 就变成了一个原子，不再包含任何东西。
    - **"`!A<T>` 与 `A<T>` 互斥，编译器会利用这一点"**——不会。包含关系里没有否定。
    - **"两个都受约束但互不包含的重载，选约束多的那个"**——不，"约束多"没有意义。互不包含 ⇒ 歧义。

## 思考题

!!! question "思考题 1"
    设 `A`、`B`、`C` 是原子约束。`(A ∨ B) ∧ C` 是否包含 `A ∨ (B ∧ C)`？反过来呢？

<details markdown="1">
<summary>答案</summary>

`P = (A ∨ B) ∧ C`，DNF：`(A ∧ C) ∨ (B ∧ C)`。`Q = A ∨ (B ∧ C)`，CNF：`(A ∨ B) ∧ (A ∨ C)`。

- `(A ∧ C)` vs `(A ∨ B)`：共享 `A` ✓；vs `(A ∨ C)`：共享 ✓。
- `(B ∧ C)` vs `(A ∨ B)`：共享 `B` ✓；vs `(A ∨ C)`：共享 `C` ✓。

所以 `P` 包含 `Q`。

反过来，`Q` 的 DNF：`A ∨ (B ∧ C)`，子句 `A` 与 `(B ∧ C)`。`P` 的 CNF：`(A ∨ B) ∧ C`，子句 `(A ∨ B)` 与 `C`。子句 `A` vs `C`：不共享 ✗。所以 `Q` 不包含 `P`。

（语义上：`P` 成立 ⇒ `C` 成立且 `A` 或 `B` 成立 ⇒ 要么 `A`、要么 `B ∧ C` ⇒ `Q` 成立。命题逻辑的结论与包含规则一致。）
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

歧义。`D<T>` 规范化为 `C<T>` 的范式，即 `C` 定义中的原子约束 `true`（空映射）；`C<T>` 规范化也是同一个 `true`。两者的关联约束相同，互相包含，谁也不比谁更受约束。

"概念名字不同"不意味着约束不同——包含关系看的是规范化后的原子。
</details>

!!! question "思考题 3"
    为什么 ¶6 要求两个非模板函数有"相同的非对象形参类型列表"才比较约束？

<details markdown="1">
<summary>答案</summary>

因为"更受约束"只应在其他条件都相同时作为决胜规则。如果 `void f(int) requires A` 与 `void f(long) requires B` 也按约束排序，就会出现"参数类型更差但约束更多的函数胜出"的诡异结果，且与函数模板偏序（只有当两个模板在推导意义上互为一样特殊时才看约束，[[temp.func.order]]）不一致。¶6.1–¶6.3 把比较限定在"同一个类的、签名相同的"函数之间，这正是预期析构函数和条件平凡特殊成员函数所需要的。
</details>

## 小结

!!! summary "小结"
    | 概念 | 定义 |
    |---|---|
    | P 包含 Q | P 的 DNF 每个子句与 Q 的 CNF 每个子句共享一个相同的原子（或可比的折叠展开约束） |
    | 原子包含 | 仅当相同：同一表达式的同一出现 + 等价映射 |
    | 适于包含 | 不含概念依赖约束 {{c++26}} |
    | 至少一样受约束 | 都受约束且（适于包含并）包含；或对方无约束 |
    | 更受约束 | 至少一样受约束，且反之不成立 |
    | 更偏序受约束 | 非模板函数：同签名、同类直接成员、同对象形参类型、更受约束 |
