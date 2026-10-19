---
title: 推导的类模板特化类型
summary: std::pair p(1, 2.0) 中不带实参的模板名能写在哪里：变量的初始化声明（声明类型只能是 cv T）、new 表达式、函数式转换和模板参数；多个声明符必须推导出同一个类型。
status: done
since: c++17
papers: P0091R3, P1814R0, P1816R0
related: over.match.class.deduct, temp.deduct.guide, dcl.type.simple, dcl.spec.auto, expr.type.conv, expr.new, temp.param
tags: 声明, 类型推导, CTAD
updated: 2026-10-19
---

!!! tldr
    - 写 `std::pair p(1, 2.0);` 时，`std::pair` 是一个推导类类型的占位符，编译器从初始化器推导出 `std::pair<int, double>`。这叫类模板实参推导（CTAD）。
    - 用于变量时，声明类型只能是 `cv T`：不能写 `const std::pair&`、`std::pair*`，也不能声明数组。
    - 此外只能用在 `new`、函数式转换 `std::pair(1, 2)` 和模板参数里；函数形参、返回类型、非静态数据成员都不行。
    - CTAD 要么全部推导，要么不推导：写了 `<…>` 就是普通的模板特化，不会推导剩下的实参。
    - 只有一个元素、而且它本身就是这个模板的特化时，CTAD 选择复制：`std::vector v2{v1};` 是 `vector<int>`，不是 `vector<vector<int>>`。

**类模板实参推导**（class template argument deduction，CTAD，C++17，[[P0091R3]]）让我们可以省略类模板的实参，由初始化器推导出来。省略了实参的模板名叫做**推导类类型的占位符**（[[g:deduced-class-type-placeholder]]），什么样的名字算占位符由 [[dcl.type.simple#3]] 规定；推导算法由 [[over.match.class.deduct]] 规定：用构造函数和推导指引（[[temp.deduct.guide]]）合成一组虚构的函数模板，再做一次重载决议。本节只规定占位符能出现在哪里，以及最终替换成什么。

## 变量：声明类型只能是 cv T（¶1）

<div class="compare" markdown="1">

```cpp run ok
#include <utility>
std::pair p(1, 2.0);
const std::pair cp(1, 'c');
std::pair a(1, 2), b(3, 4);
int main() {
  return cp.first + a.first - 2;
}
```

```cpp error
#include <utility>
const std::pair& r{1, 2};  // error
std::pair* q = nullptr;    // error
std::pair arr[2]{};        // error
int main() {}
```

</div>

¶1 推导类类型的占位符作为说明符出现在变量的初始化声明（[[dcl.init]]）里时，变量的声明类型必须是 `cv T`，T 就是占位符。声明符里不能有 `&`、`*`、`[]` 这类修饰。占位符被替换为重载决议所选函数的返回类型。

`auto` 允许 `const auto&`、`auto*`，因为 `auto` 的推导就是模板实参推导，`const U&`、`U*` 这样的模式本来就能匹配。CTAD 的推导却是对构造函数做重载决议，它回答的是这里构造了一个什么类型的对象。`std::pair* q = …` 构造的是 `*q` 还是别的什么？`const std::pair& r{1, 2}` 构造的是一个临时对象。对引用、指针、数组做 CTAD 该是什么意思，没有显然正确的答案，所以标准只允许 `cv T`。

¶1 最后一句规定，一个声明里有多个声明符时，每次替换占位符的类型必须相同：

```cpp error
#include <utility>
std::pair a(1, 2), b(3, 4.0);   // error: pair<int, int> 与 pair<int, double>
```

初始化声明的要求意味着需要能从初始化器推导出所有模板参数。`std::pair p;` 执行默认初始化，但默认构造函数推导不出 `T1`、`T2`，所以非良构。如果类模板的所有模板参数都有默认实参，如 `template<class T = int> struct D { };`，那么 `D d;` 是合法的 CTAD。

### 不能只推导一部分

只要写了 `<…>`，它就不再是占位符，而是普通的模板特化，必须给出所有没有默认值的模板实参：

```cpp error
#include <utility>
std::pair<int> p(1, 2);   // error: 模板实参太少，不会推导剩下的
```

这是有意的。如果允许部分推导，一个带默认模板实参的类模板加上新参数之后，`std::tuple<int> t(1, 2.0)` 这类现有代码的类型可能会悄悄改变。

## 其他允许的位置（¶2）

¶2 推导类类型的占位符还可以用在三个地方：

- `new` 表达式的类型里（[[expr.new]]）：`new std::pair(1, 2)`；
- 函数式记法的显式类型转换（[[expr.type.conv]]）：`std::pair(1, 2)`、`std::vector{1, 2}`；
- 模板参数的类型里（[[temp.param]]）：`template<Box B> struct K;`，常量模板参数的类型从模板实参推导（C++20）。

出现在其他任何位置都非良构。

```cpp run ok
#include <utility>
template<class T> struct Box { T v; };
template<Box B> struct K { static constexpr auto value = B.v; };
int main() {
    auto* np = new std::pair(1, 2);         // new 表达式
    auto fc = std::pair(3, 4.0);            // 函数式转换
    static_assert(K<Box{5}>::value == 5);   // 模板参数；Box{5} 本身也是 CTAD
    int r = np->first + fc.first - 4;
    delete np;
    return r;
}
```

<div class="compare" markdown="1">

```cpp error
#include <utility>
void f(std::pair p);   // error
std::pair g();         // error
struct S {
  std::pair p{1, 2};   // error
};
```

```cpp run ok
#include <utility>
struct S {
  // 静态数据成员是变量
  static inline std::pair
      p{1, 2};
};
int main() {}
```

</div>

`static_cast<std::pair>(…)` 这样的具名转换也不行。函数形参不能用 CTAD 占位符，是因为那需要把函数变成模板，而 CTAD 从构造函数实参推导的语义和从函数调用实参推导形参类型并不相同。C++20 的简写函数模板 `void f(auto p)` 加上概念约束，基本满足了这个需求。

## 推导过程概要

本节只说占位符替换为所选函数的返回类型，算法在 [[over.match.class.deduct]]。大致如下：

1. 为类模板的每个构造函数合成一个虚构的函数模板，模板参数是类模板的参数加上构造函数自己的模板参数，返回类型是类模板的特化。类没有声明构造函数时，用一个假想的默认构造函数。
2. 加入**复制推导候选**，相当于 `template<class T> A(A<T>) -> A<T>;`。
3. 加入用户写的推导指引。
4. 类是聚合体时，加入聚合推导候选（C++20，[[P1816R0]]）。
5. 用初始化器对这组候选做重载决议，选中候选的返回类型就是推导结果。

¶3 的标准例子：

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

container c(7);                           // OK: T = int
auto d = container(v.begin(), v.end());   // OK: 推导指引给出 container<double>
container e{5, 6};                        // error: int 不是迭代器
```

推导 `e` 时，由 `container(Iter, Iter)` 合成的候选推导不出 `T`（`T` 不出现在形参里），被排除；推导指引以 `Iter = int` 参与，替换 `iterator_traits<int>::value_type` 失败，也被排除；剩下的候选只接受一个实参。没有可行的候选，所以非良构。

### 一个元素时优先复制

```cpp run ok
#include <vector>
#include <type_traits>
std::vector v1{1, 2};
std::vector v2{v1};       // 复制：std::vector<int>
std::vector v3{v1, v1};   // 两个元素：std::vector<std::vector<int>>
static_assert(std::is_same_v<decltype(v2), std::vector<int>>);
static_assert(std::is_same_v<decltype(v3), std::vector<std::vector<int>>>);
int main() {}
```

花括号里只有一个元素、它的类型又是这个模板的特化（或其派生类）时，[[over.match.class.deduct#6]] 第 6.1 项规定跳过列表初始化中考虑 initializer_list 构造函数的阶段，于是复制推导候选胜出；其他条件相同时，它也优于普通候选（[[over.match.best]] 第 2.12 项）。在泛型代码里这可能出乎意料：如果 `x` 本身是一个 `std::tuple`，`std::tuple t{x};` 中 `t` 的类型就是 `x` 的类型，而不是嵌套的 tuple。

## 与 auto 的比较

| | `auto x = e;` | `std::pair x(a, b);` |
|---|---|---|
| 推导依据 | 初始化器的类型（模板实参推导） | 构造函数和推导指引（重载决议） |
| `const`、`&`、`*` | 允许 `const auto&`、`auto*` | 只允许 `cv T` |
| 结果类型 | 任意 | 这个模板的某个特化 |
| 函数形参 | `void f(auto)` 使函数成为模板 | 不允许 |
| 返回类型 | 允许 | 不允许 |

## 实现视角

!!! impl "诊断与警告"
    - 对 `W w5(1), *pw = nullptr;`，本机 Clang 23 报告 "cannot form pointer to deduced class template specialization type"。
    - CTAD 不影响 ABI。推导完成后变量的类型就是普通的类模板特化，修饰后的名字里不留痕迹。
    - Clang 的 `-Wctad-maybe-unsupported` 在一个类模板没有任何用户推导指引、却被用于 CTAD 时给出警告，因为作者可能没有考虑过 CTAD 的行为。类的作者只要声明任意一个推导指引，就不会再触发这个警告。

## 历史与演进

!!! history
    - C++17 引入 CTAD（[[P0091R3]]），可用于变量、`new` 和函数式转换。
    - C++20 加入别名模板的 CTAD（[[P1814R0]]，见 [[dcl.type.simple#3]] 中的可推导模板）、聚合体的 CTAD（[[P1816R0]]），并允许用占位符声明类类型的常量模板参数（`template<Box B>`）。
    - C++23 允许从继承的构造函数推导。
    - C++26 允许用指代类模板的拼接 `[: r :]` 作为占位符（[[dcl.type.simple#3]] 第 3.3 项）。

## 常见误解

!!! pitfall "有了 CTAD 就不需要 `make_pair`"
    大多数情况下确实如此，但 `std::make_pair` 会把 `std::reference_wrapper<T>` 展开成 `T&`，`std::pair` 的 CTAD 不会，推导出的成员类型仍然是 `reference_wrapper`。

## 思考题

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
- `w4`：良构，`const W<double>`，`cv T` 是允许的。
- `w5(1), *pw = nullptr`：非良构。第二个声明符是指针，声明类型不是 `cv T`，¶1 对每个声明符都适用。
- `w6`：良构。`W<int>` 是普通类型，`W(1)` 是函数式转换中的 CTAD（¶2），得到 `W<int>` 的 prvalue。
</details>
