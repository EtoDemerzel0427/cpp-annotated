---
title: 类模板实参推导
summary: CTAD 怎样工作：把类模板的构造函数、推导指引等变成一组函数模板，在它们上面做一次普通的推导和重载决议，胜出者的返回类型就是推导结果。
status: done
since: c++17
papers: P0091R3, P1814R0, P1816R0, P2082R1, P2582R1
related: dcl.type.class.deduct, temp.deduct.guide, temp.deduct.call, over.match.best, over.match.list, dcl.init.aggr
tags: 重载决议, 模板, CTAD
updated: 2026-10-19
---

!!! tldr
    - CTAD 没有自己的推导算法：每个构造函数被翻译成一个返回 `C<…>` 的函数模板，在这组函数模板上做普通的模板实参推导和重载决议，胜出者的返回类型就是推导结果。
    - 这组函数模板叫做指引，来源有：构造函数、拷贝推导候选 `C(C<T>)`、用户写的推导指引、C++20 的聚合推导候选、C++23 的继承构造函数。
    - 构造函数里的 `T&&`（`T` 是类模板的形参）在 CTAD 中不是转发引用，不能从左值推导。
    - `std::vector v{other_vector}` 是拷贝，不是嵌套：花括号里只有一个同类对象时，跳过 `initializer_list` 阶段。
    - 用户写的推导指引在平局时优先于隐式指引，写得不小心会把拷贝变成嵌套。

```cpp run ok
#include <utility>
#include <vector>
#include <type_traits>
int main() {
  std::pair p(1, 2.0);
  std::vector v{1, 2, 3};
  static_assert(std::is_same_v<decltype(p), std::pair<int, double>>);
  static_assert(std::is_same_v<decltype(v), std::vector<int>>);
}
```

`std::pair p(1, 2.0)` 没写模板实参，编译器推出了 `std::pair<int, double>`。这就是 C++17 引入的**类模板实参推导**（class template argument deduction，CTAD，[[P0091R3]]）。什么时候会触发 CTAD，见 [[dcl.type.class.deduct]]；推导指引的语法见 [[temp.deduct.guide]]。

CTAD 复用了已有的机制。它把类模板的构造函数翻译成一组函数模板，称为**指引**（guides），然后对它们做普通的函数模板实参推导和重载决议。胜出的那个函数模板的返回类型，就是推导出的类型。所以 CTAD 自动继承了重载决议的全部规则，包括其中不直观的地方。

## 指引从哪里来（¶1）

¶1 推导类型占位符（不带模板实参的类模板名，或 {{c++26}} *splice-type-specifier*）指代主类模板 `C` 时，`C` 的指引包括下面几类。

### 每个构造函数一个函数模板（¶1.1）

¶1.1 如果 `C` 已经定义，它的每个构造函数生成一个函数模板：

- 模板形参是 `C` 的模板形参，后面接构造函数自己的模板形参（包括默认模板实参）；
- 关联约束是 `C` 的约束与构造函数的约束的合取，`C` 的约束先检查（注 1）；
- 形参列表就是构造函数的形参列表；
- 返回类型是以 `C` 的模板形参为实参的 `C<…>`。

```cpp
template<class T, class U> struct pair {
  pair(const T&, const U&);
  template<class X, class Y> pair(X&&, Y&&);
};
// 对应的指引（示意）：
template<class T, class U>                   auto G1(const T&, const U&) -> pair<T, U>;
template<class T, class U, class X, class Y> auto G2(X&&, Y&&)         -> pair<T, U>;
```

`G2` 的 `T`、`U` 不出现在形参里，无法从实参推导，所以它对 `pair p(1, 2.0)` 推导失败，不成为候选。`G1` 对 `pair p("a", 1)` 会推出带数组类型的 `pair<char[2], int>`。标准库因此另外提供了推导指引 `pair(T1, T2) -> pair<T1, T2>`，按值传参让数组退化成指针，推出 `pair<const char*, int>`。

### 默认构造与拷贝推导候选（¶1.2–¶1.3）

¶1.2 如果 `C` 没有定义，或者没有声明任何构造函数，就按同样的方法从一个假想的构造函数 `C()` 生成一个指引。

¶1.3 此外，总会从假想的构造函数 `C(C)` 生成一个指引，称为**拷贝推导候选**（[[g:copy-deduction-candidate|copy deduction candidate]]）：

```cpp
template<class T> auto G_copy(C<T>) -> C<T>;
```

有了它，用一个 `C<X>` 初始化时推出的是 `C<X>`，而不是 `C<C<X>>`。

### 用户写的推导指引（¶1.4）

¶1.4 每个**推导指引**（*deduction-guide*）生成一个函数（模板），模板头和形参列表取自推导指引，返回类型是 `->` 后面的类型。

```cpp run ok
#include <vector>
#include <type_traits>
int main() {
  std::vector<int> src{1, 2, 3};
  std::vector v(src.begin(), src.end());
  static_assert(std::is_same_v<decltype(v), std::vector<int>>);
}
```

构造函数 `vector(InputIt, InputIt)` 生成的指引里，元素类型 `T` 无从推导。标准库提供了推导指引 `vector(It, It) -> vector<iter-value-type<It>>`，CTAD 才能成功。

### 聚合推导候选 {{c++20}}

```cpp run ok
#include <type_traits>
template<class T> struct Agg { T a; T b; };
template<class T, class U> struct Two { T a; U b; };
int main() {
  Agg x{1, 2};     // 相当于指引 template<class T> Agg<T> G(T, T)
  Two y{1, 2.0};   // 相当于 template<class T, class U> Two<T, U> G(T, U)
  static_assert(std::is_same_v<decltype(x), Agg<int>>);
  static_assert(std::is_same_v<decltype(y), Two<int, double>>);
}
```

聚合类没有构造函数，C++17 中要对它使用 CTAD，必须手写推导指引。C++20 的 [[P1816R0]] 和 [[P2082R1]] 加入了**聚合推导候选**（[[g:aggregate-deduction-candidate|aggregate deduction candidate]]）。

¶1 后半段规定，满足以下全部条件时加入这个候选：`C` 已经定义，满足聚合类的条件（假设依赖的基类没有虚函数和虚基类），初始化器是非空的花括号列表或圆括号表达式列表，并且 `C` 没有推导指引。

构造方法是：对初始化列表的每个元素 `xi`，找出它按聚合初始化（[[dcl.init.aggr]]）会初始化的元素 `ei`，然后从假想的构造函数 `C(T1, …, Tn)` 生成指引，`Ti` 一般就是 `ei` 的声明类型（¶1.10）。如果某个 `xi` 找不到对应的元素，就不加这个候选。找对应元素时有几条特殊规定：

- ¶1.5 依赖于模板形参的非数组类型、界值依赖的数组类型、元素类型依赖且 `xi` 是字符串字面量的数组类型，这三种元素不做大括号省略；
- ¶1.6、¶1.7 包展开的元素，不在末尾时视为不对应任何初始化器，在末尾时对应所有剩下的初始化器；
- ¶1.8 `ei` 是数组而 `xi` 是花括号列表时，`Ti` 是到 `ei` 声明类型的右值引用；
- ¶1.9 `ei` 是数组而 `xi` 是字符串字面量时，`Ti` 是到 const 限定的 `ei` 声明类型的左值引用。

不做大括号省略的规定会带来下面的结果（改编自标准例子）：

```cpp error
template <typename T> struct S { T x; T y; };
template <typename T> struct C { S<T> s; T t; };
template <typename T> struct D { S<int> s; T t; };

C c1 = {1, 2};          // error: s 是依赖类型，不省略大括号，1 对应 s，无法从 1 推导 S<T>
C c3 = {{1u, 2u}, 3};   // OK：T 从 3 推导为 int，{1u, 2u} 是非推导语境
D d1 = {1, 2};          // error: S<int> 不依赖 T，省略大括号后 1、2 初始化 s，没有元素对应 t
D d2 = {1, 2, 3};       // OK：1、2 初始化 s，3 初始化 t，推出 D<int>
```

数组元素和字符串字面量：

```cpp error
#include <cstddef>
template<class T, std::size_t N> struct H { T array[N]; };
template<class T, std::size_t N> struct I { volatile T array[N]; };
template<std::size_t N> struct J { unsigned char array[N]; };

H h = { "abc" };   // OK：形参 const T(&)[N]，推出 H<char, 4>，T 不是 const char
I i = { "def" };   // OK：形参 const volatile T(&)[N]，推出 I<char, 4>
J j = { "ghi" };   // error: const unsigned char(&)[N] 不能绑定到 const char[4]
```

### 继承的构造函数 {{c++23}}

¶1 最后一部分规定：如果 `C` 已经定义，并且用 *using-declaration* 从直接基类 `B` 继承了构造函数，那么 `B` 的指引经过变换后也加入 `C` 的指引（[[P2582R1]]）。

```cpp error
template <typename T> struct B { B(T); };
template <typename T> struct C : public B<T> { using B<T>::B; };
template <typename T> struct D : public B<T> {};

C c(42);   // OK：经继承的 B(T) 推出 C<int>
D d(42);   // error: D 没有继承构造函数，没有可用的指引
```

变换方法是：设 `A` 是一个别名模板，模板形参列表与 `C` 相同，代表的类型是 `B`。如果 `A` 是可推导的（[[dcl.type.simple]]），就取 `A` 的指引（按下文别名模板的规则构造），再把每个指引的返回类型从 `B` 的特化映射回相应的 `C` 的特化。标准用一个辅助类模板 `CC` 的偏特化描述这个映射（注 2）。

!!! impl "实现状态"
    本机 Clang 23 还没有实现继承构造函数的 CTAD，上例中 `C c(42);` 也报 no viable constructor or deduction guide。

附录 [[diff.cpp20.over]] 记录了这项改动的兼容性影响：原来使用其他指引的代码，可能推出不同的类型。

## 别名模板上的 CTAD（¶4–¶5）{{c++20}}

```cpp run ok
#include <vector>
#include <type_traits>
template<class T> using Vec = std::vector<T>;
int main() {
  Vec v{1, 2, 3};   // 推出 std::vector<int>
  static_assert(std::is_same_v<decltype(v), std::vector<int>>);
}
```

C++20 的 [[P1814R0]] 允许在别名模板上使用 CTAD。

¶4 占位符指代别名模板 `A` 时，`A` 代表的类型必须形如 `C<…>`，即一个 *simple-template-id*，前面可以有限定（[[dcl.type.simple]]）。`A` 的指引由 `C` 的每个指引 `f` 变换而来：

1. 用 `A` 代表的类型去推导 `f` 返回类型中的模板实参（[[temp.deduct.type]]）。推不全也不算失败；因为别的原因失败时，按什么都没推出继续。
2. 把推导结果代入 `f`，得到 `g`。如果代入成功，就构造一个新指引 `f''`：函数类型同 `g`（¶4.1）；模板形参是 `A` 中出现在上述推导结果里的模板形参，加上 `f` 中没推出来的模板形参（¶4.2）；关联约束是 `g` 的约束，再加上一条：`A` 的模板实参能从返回类型推导出来（¶4.3）。
3. `f` 是拷贝推导候选、来自推导指引、带 `explicit` 这几项性质，`f''` 都原样保留（¶4.4–¶4.6）。

¶5 能从类型 `T` 推导出 `A` 的模板实参，指的是：设辅助类模板 `AA` 只有一个偏特化 `AA<A<模板形参…>>`，`AA<T>` 能匹配这个偏特化。

关键是 ¶4.3 加上的那条约束。它保证推出的类型确实是 `A` 的某个特化，而不只是 `C` 的某个特化：

```cpp error
#include <concepts>
#include <type_traits>
template <class T, class U> struct C {
  C(T, U);                                    // #1
};
template<class T, class U>
  C(T, U) -> C<T, std::type_identity_t<U>>;   // #2

template<class V> using A = C<V*, V*>;
template<std::integral W> using B = A<W>;

int i{};
double d{};
A a1(&i, &i);   // OK：推出 A<int>，即 C<int*, int*>
A a2(i, i);     // error: 无法从 int 推导 V*
A a3(&i, &d);   // error: #1 无法从 (int*, double*) 推导 (V*, V*)；#2 推出的 C<int*, double*> 不是 A<V>
B b1(&i, &i);   // OK：推出 B<int>
B b2(&d, &d);   // error: C<double*, double*> 是 A<double>，但 double 不满足 std::integral
```

标准的例 3 给出了一种可能的实现：把 #1 变换成

```cpp
template<class V> requires deduces_A<C<V*, V*>>
  auto f1_prime(V*, V*) -> C<V*, V*>;
```

其中 `deduces_A<T>` 用上面 `AA` 偏特化的方法检查 `T` 是不是 `A` 的特化。

### 模板模板形参上的 CTAD（¶3）

¶3 占位符是一个类型模板模板形参 `P` 时，对应的模板实参必须是可推导的模板。设 `A` 是一个别名模板，模板形参列表与 `P` 的相同，代表 实参模板<`P` 的模板实参>；然后用 `A` 代替原来的名字，按别名模板的规则处理。

```cpp error
template<typename ... Ts>
struct Y {
  Y();
  Y(Ts ...);
};
template<template<typename T = char> class X>
void f() {
  X x;          // OK：推出 Y<char>
  X x1{1};      // OK：推出 Y<int>
  X x2{1, 2};   // error: 不能从 Y<int, int> 推导 X<T>
}
template void f<Y>();
```

这里 `A` 相当于 `template<typename T = char> using A = Y<T>;`。`X x` 时，由 `Y()` 生成的指引经变换后带上了 `A` 的模板形参 `T = char`，所以推出 `Y<char>`。`X x2{1, 2}` 推出的 `Y<int, int>` 不是 `A` 的特化，被 ¶4.3 的约束排除。

!!! impl "Clang 的偏离"
    本机 Clang 23 对 `X x1{1}` 的处理与标准一致。但它把 `X x;` 推导成 `Y<>`，没有用上 `P` 的默认模板实参，进而因为 `Y<>` 的两个构造函数签名相同而报错；同时它接受了 `X x2{1, 2}`。两处都与标准例子不符。

## 在指引上做重载决议（¶6）

¶6 推导时，把指引当作一个假想类的构造函数，按 [[dcl.init]] 以及 [[over.match.ctor]]、[[over.match.copy]] 或 [[over.match.list]]（视初始化形式而定）做初始化和重载决议。有两个例外：

- ¶6.1 如果初始化列表只有一个表达式，类型是 `cv U`，而 `U` 是占位符所指类模板的特化或其派生类，就跳过 [[over.match.list]] 的第一阶段（`initializer_list` 构造函数）。
- ¶6.2 对聚合推导候选做推导时，末尾形参包的元素个数只在其他方式推不出来时，才由剩余实参的个数决定。

由带 `explicit` 的构造函数或推导指引生成的指引，对应的假想构造函数也是 explicit 的。所有假想构造函数都视为 public 成员。

### 花括号里的单个同类对象是拷贝（¶6.1）

```cpp run ok
#include <vector>
#include <type_traits>
int main() {
  std::vector v1{1, 2};
  std::vector v2{v1};       // 跳过 initializer_list 阶段，拷贝推导候选推出 vector<int>
  std::vector v3{v1, v1};   // 两个元素，¶6.1 不适用，推出 vector<vector<int>>
  static_assert(std::is_same_v<decltype(v2), std::vector<int>>);
  static_assert(std::is_same_v<decltype(v3), std::vector<std::vector<int>>>);
}
```

没有 ¶6.1，`std::vector v2{v1}` 会在第一阶段选中 `vector(initializer_list<T>)` 生成的指引，推出 `vector<vector<int>>`，与花括号包一个同类对象就是拷贝的直觉相反。代价是 `v2` 与 `v3` 的行为不一致，泛型代码里 `std::vector v{args...}` 的类型会随 `args` 的个数而变。

### 构造函数里的 `T&&` 不是转发引用

```cpp error
template<class T> struct W { W(T&&); };
int n;
W w1{0};   // OK：W<int>
W w2{n};   // error: T&& 不是转发引用，不能从左值推导
```

由构造函数生成的指引中，`T` 是类模板的模板形参。[[temp.deduct.call]] 规定这种 `T&&` 在 CTAD 中不是转发引用。

如果它是转发引用，`W w2{n}` 会推出 `W<int&>`，构造函数随之变成 `W(int&)`。作者写的是接受右值的构造函数，CTAD 却悄悄造出一个以引用类型为实参的特化，这几乎总是错的。需要转发语义时，写推导指引 `template<class U> W(U&&) -> W<std::decay_t<U>>;`。

### explicit 会传递到指引

在拷贝初始化或拷贝列表初始化中，如果推导时选中了 explicit 的指引，推导本身就非良构，即使随后真正用来初始化的构造函数不是 explicit 的（¶7 例 2）：

```cpp error
template <class T> struct A {
  explicit A(const T&, ...) noexcept;   // #1
  A(T&&, ...);                          // #2
};
int i;
A a1 = { i, i };   // error: 推导时选中了 explicit 的 #1（#2 不能从左值 i 推导）
A a2{i, i};        // OK：直接列表初始化，#1 推出 A<int>，并用 #1 初始化
A a3{0, i};        // OK：#2 推出 A<int>（0 是右值）
A a4 = {0, i};     // OK：同上，#2 不是 explicit
```

## 平局时的决胜规则

CTAD 专用的决胜规则是 [[over.match.best#2.10]] 到 [[over.match.best#2.13]]，排在转换序列比较、模板偏序和约束之后：

| 规则 | 内容 |
|---|---|
| 2.10 | 不是由继承构造函数生成的指引，优于由继承构造函数生成的（对应形参类型都相同时） |
| 2.11 | 由推导指引生成的，优于不是由推导指引生成的 |
| 2.12 | 拷贝推导候选优于其他 |
| 2.13 | 由非模板构造函数生成的，优于由构造函数模板生成的 |

```cpp ok
#include <type_traits>
template <class T> struct A {
  using value_type = T;
  A(value_type);    // #1
  A(const A&);      // #2
  A(T, T, int);     // #3
  template<class U>
    A(int, T, U);   // #4
  // #5 是拷贝推导候选 A(A)
};

A x(1, 2, 3);       // 用 #3：#3 与 #4 同样好，2.13 选非模板构造函数生成的 #3

template <class T>
A(T) -> A<T>;       // #6

A a(42);            // 用 #6 推出 A<int>，再用 #1 初始化
A b = a;            // 用 #5 推出 A<int>：#5 比 #6 更特殊，偏序先于 2.11 起作用

template <class T>
A(A<T>) -> A<A<T>>; // #7，与 #5 同样特殊

A b2 = a;           // 用 #7 推出 A<A<int>>：偏序打平，2.11 让推导指引胜出
static_assert(std::is_same_v<decltype(b), A<int>>);
static_assert(std::is_same_v<decltype(b2), A<A<int>>>);
```

`A a(42)` 为什么不用 #1？#1 的形参是 `value_type`，也就是 `typename A<T>::value_type`，属于非推导语境，从 `42` 推不出 `T`，所以 #1 生成的指引推导失败，只有 #6 能用。

`b2` 是一个常见的陷阱：用户写的 #7 与拷贝推导候选 #5 的形参都是 `A<T>`，偏序打平，2.11 让推导指引胜出，`b2` 成了 `A<A<int>>`。

<details class="fine" markdown="1"><summary>其余条文</summary>

¶2、¶7、¶8、¶9 都是例子段落，正文已经引用了其中的主要部分。¶2 还有几个继承构造函数的例子：在 `C` 继承 `B(T)` 之后再声明推导指引 `B(int) -> B<char>`，`C c2(42)` 推出 `C<char>`；基类不依赖于 `C` 的模板形参时（`struct E : B<int>`），继承来的指引推不出 `E` 的模板实参。

</details>

## 实现视角

!!! impl
    - 编译器确实生成这些指引。Clang 为每个构造函数生成隐式的推导指引声明，`-Xclang -ast-dump` 能看到它们；CTAD 失败时，诊断里列出的 candidate template ignored 就是这些隐式指引。
    - 推导指引只参与类型推导，不产生代码或符号。

## 历史与演进

!!! history
    - C++17：[[P0091R3]] 引入 CTAD，包括隐式指引、拷贝推导候选、用户推导指引，以及构造函数中 `T&&` 不是转发引用的规则。¶6.1 的单元素例外后来由缺陷报告加入。
    - C++20：聚合推导候选（[[P1816R0]]、[[P2082R1]]）；别名模板上的 CTAD（[[P1814R0]]）。
    - C++23：继承构造函数的 CTAD（[[P2582R1]]）。
    - C++26：*splice-type-specifier* 也可以作为推导类型占位符。

## 常见误解

!!! pitfall "构造函数的 `T&&` 在 CTAD 中是转发引用"
    不是。需要转发语义时写推导指引，标准库的 `std::optional`、`std::tuple` 等都为此提供了推导指引。

!!! pitfall "CTAD 可以只指定一部分模板实参"
    不行。`std::pair<int> p(1, 2.0);` 非良构：写了模板实参列表就不再是推导类型占位符，必须写全。

## 思考题

!!! question "思考题 1"
    `std::tuple t{std::tuple{1}};` 推出什么类型？`std::tuple t{std::tuple{1}, 2};` 呢？

<details markdown="1">
<summary>答案</summary>

第一个是 `std::tuple<int>`。花括号里只有一个 `std::tuple` 的特化，¶6.1 跳过初始化列表阶段（`tuple` 本来也没有 `initializer_list` 构造函数）。主要的竞争者有三个：拷贝推导候选 `tuple(tuple<Ts...>) -> tuple<Ts...>`，推出 `tuple<int>`；标准库的推导指引 `tuple(Ts...) -> tuple<Ts...>`，推出 `tuple<tuple<int>>`；构造函数 `tuple(const Types&...)` 生成的指引，也推出 `tuple<tuple<int>>`。三者的转换序列都是恒等，进入决胜规则。模板偏序（[[over.match.best#2.5]]）排在 2.11 之前，拷贝推导候选的形参 `tuple<Ts...>` 比 `Ts...`、`const Ts&...` 更特殊，所以它胜出。

第二个有两个元素，拷贝推导候选不可行，推出 `std::tuple<std::tuple<int>, int>`。本机 Clang 23 的结果与此一致。
</details>

!!! question "思考题 2"
    为什么只有在 `C` 没有推导指引时才加入聚合推导候选？

<details markdown="1">
<summary>答案</summary>

为聚合写了推导指引，说明作者想精确控制推导结果。这时再加入自动生成的聚合推导候选，它可能凭借转换序列比较或模板偏序胜过用户的指引（这两步都排在 2.11 之前），使用户的指引失效。另外，C++17 时为聚合写的推导指引到了 C++20 应当保持原来的含义，有指引就不生成，是最简单的兼容办法。
</details>
