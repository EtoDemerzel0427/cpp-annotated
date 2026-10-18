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

**类模板实参推导**（class template argument deduction，CTAD，C++17，[[P0091R3]]）让我们可以写 `std::pair p(1, 2.0);`，而不必写 `std::pair<int, double>`。从语法上看，这里的 `std::pair` 是一个**推导类类型的占位符**（placeholder for a deduced class type，[[g:deduced-class-type-placeholder]]，[[dcl.type.simple#3]]），也就是出现在本该写类型的位置、却没有模板实参列表的模板名。

CTAD 涉及三处条款：

- [[dcl.type.simple#3]]：什么样的类型说明符是推导类类型占位符，什么是可推导模板；
- 本节 [dcl.type.class.deduct]：占位符能出现在哪里，最终替换成什么；
- [[over.match.class.deduct]]：推导算法本身，即从构造函数和推导指引（[[temp.deduct.guide]]）合成一组虚构的函数模板，再做重载决议。

本页只讲第二部分。

## 变量声明中的占位符（¶1）

¶1 如果推导类类型的占位符作为 *decl-specifier* 出现在变量的初始化声明（[[dcl.init]]）的说明符序列中，那么：

1. 该变量的声明类型必须是 cv T（T 是占位符），声明符中不能有 `*`、`&`、`[]`、函数参数列表等任何修饰；
2. 占位符替换为 [[over.match.class.deduct]] 中重载决议所选函数的返回类型；
3. 如果说明符序列后面有多个声明符，每次推导出来替换占位符的类型必须相同。

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

为什么禁止 `const A& y = …;`、`A* p = …;`？`auto` 之所以允许 `const auto&`、`auto*`，是因为 `auto` 的推导就是模板实参推导，`const U&`、`U*` 这样的模式本来就能匹配。CTAD 的推导则是重载决议，它根据构造函数推导出构造的是什么类型的对象。`A* p = new A(...)` 中构造的是 `*p` 而不是 `p`；`const A& y{}` 中构造的是一个临时对象。要让占位符出现在这些位置，就得先定义对引用、指针、数组做 CTAD 是什么意思，而这个问题没有显然正确的答案（比如 `A* p = &existing;` 应当推导成什么？）。所以标准只允许最简单的 `cv T` 形式。

初始化声明这个条件意味着必须有初始化器：

```cpp error
#include <utility>
std::pair p;                // error: 没有初始化器，无从推导（pair 的默认构造函数无法推导出 T1、T2）
```

（严格地说，`std::pair p;` 也是初始化声明，执行的是默认初始化，只是重载决议找不到能推导出所有模板参数的候选。如果类模板的所有模板参数都有默认实参，如 `template<class T = int> struct D { };`，那么 `D d;` 是合法的 CTAD。）

### 不能部分指定模板实参

CTAD 要么全部推导，要么完全不推导。只要写了 `<…>`，它就不再是占位符，而是普通的 *simple-template-id*，必须给出所有（没有默认值的）模板实参：

```cpp error
#include <utility>
std::pair<int> p(1, 2);     // error: 模板实参太少，不会推导剩下的
```

这是有意的设计。C++17 的 CTAD 提案讨论过部分推导，但它会改变已有代码的含义。今天 `std::vector<int> v(…)` 的意思是明确的；如果允许 `std::tuple<int> t(1, 2.0)` 推导剩余参数，那么带默认模板实参的类模板在加上新参数时，现有代码的类型可能在不知不觉中改变。

## 其他允许的位置（¶2）

¶2 推导类类型的占位符还可以用于：

- *new-expression* 的 *new-type-id* 或 *nofun-type-id* 中的类型说明符序列（[[expr.new]]）：`new std::pair(1, 2)`；
- 作为显式类型转换（函数式记法）的简单类型说明符（[[expr.type.conv]]）：`std::pair(1, 2)`、`std::vector{1, 2}`；
- 作为模板参数的 *parameter-declaration* 中的类型说明符（[[temp.param]]）：`template<Box B> struct K;`，此时常量模板参数的类型由模板实参推导（C++20）。

出现在其他任何位置都非良构，包括函数参数、返回类型、非静态数据成员、`static_cast` 等具名转换的目标类型、`sizeof`、模板实参等。

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

为什么函数参数不能用 CTAD 占位符？`void f(std::pair p)` 看起来很自然，意思是接受任意 pair。但这需要把 `f` 变成模板（就像 `void f(auto p)`），而 CTAD 的语义是从构造函数实参推导，与从函数调用实参推导参数类型并不相同（例如对 `f({1, 2})`，前者走 CTAD，后者走模板推导的花括号规则）。C++20 的简写函数模板提供了 `void f(auto p)` 和概念约束，基本满足了这个需求。

## 推导的过程（概要）

本节只规定占位符替换为重载决议所选函数的返回类型。具体算法见 [[over.match.class.deduct]]，概要如下：

1. 为类模板的每个构造函数（没有构造函数时，为一个假想的默认构造函数）合成一个虚构的函数模板，其模板参数是类模板参数加上构造函数自身的模板参数，返回类型是类模板特化；
2. 加入复制推导候选（`template<class T> A(A<T>) -> A<T>;`）；
3. 加入用户写的推导指引（[[temp.deduct.guide]]）；
4. 如果类是聚合体，加入聚合推导候选（C++20，[[P1816R0]]）；
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

推导 `e` 时，由构造函数 `container(Iter, Iter)` 合成的候选无法推导 `T`（`T` 不出现在参数中），因而淘汰；推导指引以 `Iter = int` 参与，替换 `iterator_traits<int>::value_type` 失败（SFINAE），同样淘汰；`container(T)` 只接受一个参数，也不可行。没有可行候选，所以非良构。

### 复制优先

复制推导候选带来了一个常让人意外的结果：

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

如果只有一个元素，且其类型就是该模板的特化（或其派生类），CTAD 会选择复制而不是包装。[[over.match.class.deduct#6]] 的 ¶6.1 规定，此时跳过列表初始化中考虑 initializer_list 构造函数的第一阶段，于是复制推导候选胜出（在其他条件相同时，它也优于普通候选，[[over.match.best]] ¶2.12）。这在泛型代码中可能出乎意料：如果 `x` 本身是 `std::tuple`，`std::tuple t{x};` 中 `t` 的类型就是 `x` 的类型。

## 与 auto 的比较

| | `auto x = e;` | `std::pair x(a, b);` |
|---|---|---|
| 推导依据 | 初始化器的类型（模板实参推导） | 构造函数 / 推导指引（重载决议） |
| 允许 `const`、`&`、`*` 等 | 允许 `const auto&`、`auto*` | 只允许 `cv T` |
| 结果类型 | 任意 | 一定是该模板的特化（或推导指引指定的特化） |
| 函数参数 | `void f(auto)` → 模板 | 不允许 |
| 返回类型 | 允许 | 不允许 |

!!! impl "实现视角"
    - Clang 对禁止位置的诊断形如"use of class template 'std::pair' requires template arguments; argument deduction not allowed in function prototype"，并会说明是哪类位置（function return type、non-static struct member 等）。
    - CTAD 不影响 ABI。推导完成后，变量的类型就是普通的类模板特化，mangled 名中不留任何痕迹。
    - Clang 提供 `-Wctad-maybe-unsupported` 警告：对没有用户推导指引的类模板使用 CTAD 时给出提醒，因为该类的作者可能并未考虑 CTAD 的行为。类的作者可以声明一个特殊的推导指引，表明这个类支持 CTAD。

!!! history "历史与演进"
    - C++17：CTAD（[[P0091R3]]），可用于变量、`new`、函数式转换。
    - C++20：别名模板的 CTAD（[[P1814R0]]，见 [[dcl.type.simple#3]] 中的可推导模板）；聚合体的 CTAD（[[P1816R0]]）；类类型的常量模板参数可以用占位符声明（`template<Box B>`）。
    - C++23：可以从继承的构造函数推导。
    - C++26：推导类类型占位符可以是指代类模板的拼接说明符（[[dcl.type.simple#3]] ¶3.3）。

!!! pitfall "常见误解"
    - 误以为 `std::vector v{v1};` 是 `vector<vector<int>>`。实际上这是复制，类型是 `vector<int>`。
    - 误以为 `std::pair<int> p(1, 2.0)` 会推导第二个参数。不会，CTAD 不支持部分推导。
    - 误以为 CTAD 可以用在任何需要类型的地方。它只能用于变量的初始化声明（`cv T`）、`new`、函数式转换和模板参数。
    - 误以为有了 CTAD 就不需要 `make_pair`。大多数情况下确实如此，但 `std::make_pair` 会对 `std::reference_wrapper` 做特殊处理（推导为引用），`std::pair` 的 CTAD 不会。

!!! summary "小结"
    - 推导类类型占位符是不带模板实参列表的类模板名（或可推导的别名模板、类型模板模板参数、拼接）。
    - 用于变量时，必须是初始化声明，声明类型恰为 `cv T`，多个声明符的推导结果必须相同。
    - 此外只允许出现在 `new`、函数式转换和常量模板参数的类型中，其他位置非良构。
    - 推导结果是 [[over.match.class.deduct]] 中选中候选的返回类型。

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
- `w2(1), w3(2u)`：非良构。`w2` 推导出 `W<int>`，`w3` 推导出 `W<unsigned>`，两者不同（¶1）。
- `w4`：良构，`const W<double>`，cv T 是允许的。
- `w5(1), *pw = nullptr`：非良构。第二个声明符是指针，声明类型不是 `cv T`（¶1 对每个声明符都适用）。
- `w6`：良构。`W<int>` 是普通类型；`W(1)` 是函数式转换中的 CTAD（¶2），产生 `W<int>` 的 prvalue。
</details>
