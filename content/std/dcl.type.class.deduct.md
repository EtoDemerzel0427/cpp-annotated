---
title: 推导的类模板特化类型
summary: 类模板实参推导（CTAD）在声明层面的规则：推导类类型占位符只能出现在变量的初始化声明（且声明类型必须恰为 cv T）、new 表达式、函数式转换和模板参数中；多个声明符必须推导出相同类型
status: done
since: c++17
papers: P0091R3, P1814R0, P1816R0
related: over.match.class.deduct, temp.deduct.guide, dcl.type.simple, dcl.spec.auto, expr.type.conv, expr.new, temp.param
tags: 声明, 类型推导, CTAD
updated: 2026-10-17
---

**类模板实参推导**（class template argument deduction，CTAD，C++17，[[P0091R3]]）让我们写 `std::pair p(1, 2.0);` 而不必写 `std::pair<int, double>`。从语法上看，`std::pair` 在这里是一个**推导类类型的占位符**（placeholder for a deduced class type，[[g:deduced-class-type-placeholder]]，[[dcl.type.simple#3]]）：一个没有模板实参列表的模板名，出现在本该是类型的地方。

CTAD 涉及三处条款：

- [[dcl.type.simple#3]]：什么样的类型说明符是推导类类型占位符，什么是"可推导模板"；
- **本节** [dcl.type.class.deduct]：占位符**能出现在哪里**、被替换成什么；
- [[over.match.class.deduct]]：**推导算法本身**——从构造函数和推导指引（[[temp.deduct.guide]]）合成一组虚构的函数模板，做重载决议。

本页只讲第二部分。

## 变量声明中的占位符（¶1）

¶1 若推导类类型的占位符作为 *decl-specifier* 出现在**变量的初始化声明**（[[dcl.init]]）的说明符序列中，则：

1. 该变量的**声明类型必须是 cv T**（T 是占位符）——声明符中不能有 `*`、`&`、`[]`、函数参数列表等任何"包装"；
2. 占位符被替换为 [[over.match.class.deduct]] 中重载决议所选函数的**返回类型**；
3. 若说明符序列后有**多个**声明符，每次推导替换占位符的类型必须**相同**。

```cpp run ok
#include <utility>
#include <vector>
std::pair p(1, 2.0);                // std::pair<int, double>
const std::pair cp(1, 'c');         // OK: cv T
std::pair a(1, 2), b(3, 4);         // OK: 都是 std::pair<int, int>
std::vector v{1, 2, 3};             // std::vector<int>
int main() { return cp.first + a.first + b.second + int(v.size()) + int(p.second) - 13; }
```

```cpp error
template<class... T> struct A { A(T...) { } };
A x[29]{};                  // error: 不允许声明符运算符（数组）
const A& y{};               // error: 不允许声明符运算符（引用）
A* p = nullptr;             // error: 指针也不行
```

```cpp error
#include <utility>
std::pair a(1, 2), b(3, 4.0);   // error: pair<int, int> 与 pair<int, double> 不同
```

为什么禁止 `const A& y = …;`、`A* p = …;`？`auto` 允许 `const auto&`、`auto*`，那是因为 `auto` 的推导就是模板实参推导，`const U&`、`U*` 这样的模式天然可以匹配。CTAD 的推导是**重载决议**——它从构造函数推导出"构造的是什么类型的对象"。`A* p = new A(...)` 中被构造的是 `*p`，而不是 `p`；`const A& y{}` 中被构造的是一个临时对象。让占位符出现在这些位置，需要定义"对引用、指针、数组做 CTAD"是什么意思，而这并没有显然正确的答案（比如 `A* p = &existing;` 应当推导成什么？）。所以标准只允许最简单的 `cv T` 形式。

"初始化声明"这个条件意味着必须有初始化器：

```cpp error
#include <utility>
std::pair p;                // error: 没有初始化器，无从推导（pair 的默认构造函数无法推导出 T1、T2）
```

（严格地说，`std::pair p;` 也是初始化声明——默认初始化——只是重载决议找不到能推导出所有模板参数的候选。对于所有模板参数都有默认实参的类模板，如 `template<class T = int> struct D { };`，`D d;` 是合法的 CTAD。）

### 不能部分指定模板实参

CTAD 是"全有或全无"：只要写了 `<…>`，就不再是占位符，而是普通的 *simple-template-id*，必须给出所有（没有默认值的）模板实参：

```cpp error
#include <utility>
std::pair<int> p(1, 2);     // error: 模板实参太少，不会推导剩下的
```

这是有意的设计。C++17 的 CTAD 提案讨论过"部分推导"，但它会改变已有代码的含义：今天 `std::vector<int> v(…)` 的意思是明确的；如果允许 `std::tuple<int> t(1, 2.0)` 推导剩余参数，那么"带默认模板实参的类模板"在加上新参数时，现有的代码可能悄悄改变类型。

## 其他允许的位置（¶2）

¶2 推导类类型的占位符还可以用于：

- *new-expression* 的 *new-type-id* 或 *nofun-type-id* 中的类型说明符序列（[[expr.new]]）：`new std::pair(1, 2)`；
- 作为**显式类型转换（函数式记法）**的简单类型说明符（[[expr.type.conv]]）：`std::pair(1, 2)`、`std::vector{1, 2}`；
- 作为**模板参数**的 *parameter-declaration* 中的类型说明符（[[temp.param]]）：`template<Box B> struct K;`——常量模板参数的类型由模板实参推导（C++20）。

**其他任何位置都非良构**：函数参数、返回类型、非静态数据成员、`static_cast` 等具名转换的目标类型、`sizeof`、模板实参……

```cpp run ok
#include <utility>
template<class T> struct Box { T v; };
template<Box B> struct K { static constexpr auto value = B.v; };   // 模板参数中的 CTAD（C++20）
int main() {
    auto* np = new std::pair(1, 2);          // new 表达式
    auto fc = std::pair(3, 4.0);             // 函数式转换
    static_assert(K<Box{5}>::value == 5);    // Box{5} 本身也是 CTAD（聚合推导）
    int r = np->first + fc.first - 4;
    delete np;
    return r;
}
```

```cpp error
#include <utility>
void f(std::pair p);                                  // error: 函数参数
std::pair g();                                        // error: 返回类型
struct S { std::pair p{1, 2}; };                      // error: 非静态数据成员
auto q = static_cast<std::pair>(std::pair{1, 2});     // error: static_cast 的目标类型
```

```cpp run ok
#include <utility>
struct S { static inline std::pair p{1, 2}; };        // OK: 静态数据成员是变量，这是它的初始化声明
int main() { return S::p.first - 1; }
```

为什么函数参数不能用 CTAD 占位符？`void f(std::pair p)` 看起来很自然——"接受任意 pair"。但这需要把 `f` 变成模板（就像 `void f(auto p)`），而 CTAD 的语义是"从**构造函数实参**推导"，与"从函数调用实参推导参数类型"并不相同（例如对 `f({1, 2})`，一个是 CTAD，一个是模板推导的花括号规则）。C++20 的简写函数模板提供了 `void f(auto p)` 与概念约束，基本满足了这个需求。

## 推导的过程（概要）

本节只说"占位符被替换为重载决议所选函数的返回类型"。具体算法见 [[over.match.class.deduct]]，概要如下：

1. 对类模板的每个构造函数（以及若无构造函数时一个假想的默认构造函数），合成一个虚构的函数模板：模板参数 = 类模板参数 + 构造函数自身的模板参数，返回类型 = 类模板特化；
2. 加入**复制推导候选**（`template<class T> A(A<T>) -> A<T>;`）；
3. 加入用户写的**推导指引**（[[temp.deduct.guide]]）；
4. 若类是聚合体，加入**聚合推导候选**（C++20，[[P1816R0]]）；
5. 对初始化器做重载决议，选中的候选的返回类型就是推导结果。

标准的例子：

```cpp error
#include <vector>
#include <iterator>
template<class T> struct container {
    container(T t) { }
    template<class Iter> container(Iter beg, Iter end);
};
template<class Iter>
container(Iter b, Iter e) -> container<typename std::iterator_traits<Iter>::value_type>;
std::vector<double> v = { /* ... */ };

container c(7);                           // OK: 从 container(T) 推导 T = int
auto d = container(v.begin(), v.end());   // OK: 推导指引给出 container<double>
container e{5, 6};                        // error: 推导指引匹配 Iter = int，
                                          // 但 iterator_traits<int>::value_type 不存在
```

`e` 的推导中，构造函数 `container(Iter, Iter)` 合成的候选无法推导 `T`（`T` 不出现在参数中），被淘汰；推导指引以 `Iter = int` 参与，替换 `iterator_traits<int>::value_type` 失败（SFINAE），也被淘汰；`container(T)` 需要一个参数，也不可行。没有可行候选，于是非良构。

### 复制优先

复制推导候选导致了一个著名的"惊喜"：

```cpp run ok
#include <vector>
#include <type_traits>
std::vector v1{1, 2};
std::vector v2{v1};          // std::vector<int>：复制，而不是 vector<vector<int>>
std::vector v3{v1, v1};      // std::vector<std::vector<int>>：两个元素，initializer_list 构造
static_assert(std::is_same_v<decltype(v2), std::vector<int>>);
static_assert(std::is_same_v<decltype(v3), std::vector<std::vector<int>>>);
int main() { }
```

单个元素、类型就是该模板的特化（或其派生类）时，CTAD 偏好"复制"而不是"包装"：[[over.match.class.deduct#6]] 的 ¶6.1 规定此时跳过列表初始化中"考虑 initializer_list 构造函数"的第一阶段，于是复制推导候选胜出（它在其他条件相同时也优于普通候选，[[over.match.best]] ¶2.12）。这在泛型代码中可能令人意外：`std::tuple t{x};` 当 `x` 本身是 `std::tuple` 时，`t` 的类型就是 `x` 的类型。

## 与 auto 的比较

| | `auto x = e;` | `std::pair x(a, b);` |
|---|---|---|
| 推导依据 | 初始化器的类型（模板实参推导） | 构造函数 / 推导指引（重载决议） |
| 允许 `const`、`&`、`*` 等 | 允许 `const auto&`、`auto*` | 只允许 `cv T` |
| 结果类型 | 任意 | 一定是该模板的特化（或推导指引指定的特化） |
| 函数参数 | `void f(auto)` → 模板 | 不允许 |
| 返回类型 | 允许 | 不允许 |

!!! impl "实现视角"
    - Clang 对禁止位置的诊断形如"use of class template 'std::pair' requires template arguments; argument deduction not allowed in function prototype"，并会说明是哪类位置（function return type、non-static struct member……）。
    - CTAD 不影响 ABI：推导完成后，变量的类型就是普通的类模板特化，mangled 名中不留下任何痕迹。
    - Clang 提供 `-Wctad-maybe-unsupported` 警告：当对一个**没有**用户推导指引的类模板使用 CTAD 时提醒（因为该类的作者可能并未考虑 CTAD 的行为）。可以通过声明一个特殊的推导指引来表明"本类支持 CTAD"。

!!! history "历史与演进"
    - **C++17**：CTAD（[[P0091R3]]）：变量、`new`、函数式转换。
    - **C++20**：别名模板的 CTAD（[[P1814R0]]，见 [[dcl.type.simple#3]] 的"可推导模板"）；聚合体的 CTAD（[[P1816R0]]）；类类型的常量模板参数可用占位符声明（`template<Box B>`）。
    - **C++23**：从继承的构造函数推导。
    - **C++26**：推导类类型占位符可以是指代类模板的**拼接说明符**（[[dcl.type.simple#3]] ¶3.3）。

!!! pitfall "常见误解"
    - "`std::vector v{v1};` 是 `vector<vector<int>>`"——是复制，`vector<int>`。
    - "`std::pair<int> p(1, 2.0)` 会推导第二个参数"——不会，CTAD 不支持部分推导。
    - "CTAD 可以用在任何需要类型的地方"——只能用于变量初始化声明（`cv T`）、`new`、函数式转换、模板参数。
    - "加了 CTAD 就不需要 `make_pair`"——大多数情况下如此，但 `std::make_pair` 会对 `std::reference_wrapper` 做特殊处理（推导为引用），`std::pair` 的 CTAD 不会。

!!! summary "小结"
    - 推导类类型占位符 = 不带模板实参列表的类模板名（或可推导的别名模板、类型模板模板参数、拼接）。
    - 变量中：必须是初始化声明，声明类型恰为 `cv T`；多个声明符推导结果必须相同。
    - 另外只允许出现在 `new`、函数式转换、常量模板参数的类型中；其他位置非良构。
    - 推导结果 = [[over.match.class.deduct]] 中选中候选的返回类型。

!!! question "思考题"
    下面哪些声明是良构的？

    ```cpp
    template<class T> struct W { W(T) { } };
    W w1 = 1;
    W w2(1), w3(2u);
    const W w4{1.0};
    W w5(1), *pw = nullptr;
    W<int> w6 = W(1);
    ```

<details markdown="1">
<summary>答案</summary>

- `w1`：良构，`W<int>`。
- `w2(1), w3(2u)`：非良构——`w2` 推导出 `W<int>`，`w3` 推导出 `W<unsigned>`，不相同（¶1）。
- `w4`：良构，`const W<double>`，cv T 是允许的。
- `w5(1), *pw = nullptr`：非良构——第二个声明符是指针，声明类型不是 `cv T`（¶1 对每个声明符都适用）。
- `w6`：良构。`W<int>` 是普通类型；`W(1)` 是函数式转换中的 CTAD（¶2），产生 `W<int>` 的 prvalue。
</details>
