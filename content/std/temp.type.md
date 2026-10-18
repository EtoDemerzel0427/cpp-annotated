---
title: 类型等价
summary: 两个 template-id 何时指同一个实体；"模板实参等价"的逐类型定义（整数按值、浮点按 identical、指针按指针值、类类型逐子对象递归、闭包类型恒等价……）；待决 decltype 与包索引的身份规则。
status: done
papers: P1907R1
related: temp.param, temp.arg.nontype, temp.over.link, temp.alias, basic.def.odr, basic.compound, expr.eq
tags: 模板, 类型等价, 模板实参等价, 常量模板实参
updated: 2026-10-17
---

模板最根本的承诺是：**同样的实参得到同一个特化**。`std::vector<int>` 在一百个翻译单元里出现，必须是同一个类型；`std::array<int, 2*512>` 和 `std::array<int, 1024>` 也必须是同一个类型。否则 ODR、链接、函数重载全部无从谈起。

[temp.type] 给出"同一个"的精确定义。对类型实参和模板实参，"同一"是显然的；真正需要定义的是**常量模板实参的值**何时算"同一个"——这就是**模板实参等价**（template-argument-equivalent）。C++20 引入类类型和浮点类型的常量模板形参之后，这个定义变得相当精细。

## 两个 template-id 何时相同（¶1）

¶1 两个 *template-id* **相同**，当：

- ¶1.1 它们的 *template-name*（或 *operator-function-id*、*literal-operator-id*）指称**同一个模板**；
- ¶1.2 对应的类型模板实参是**同一类型**；
- ¶1.3 由对应的常量模板实参确定的模板形参值（[[temp.arg.nontype]]）是**模板实参等价**的；
- ¶1.4 对应的模板模板实参指称**同一个模板**。

相同的两个 *template-id* 指称同一个类、函数或变量。

注意 ¶1.3 比较的是**形参的值**（转换之后），而不是实参表达式：`X<2*512>` 与 `X<1024>`、`X<'A'>` 与 `X<65>`（对 `template<int>`）都是相同的。

```cpp run title="same-template-id.cpp" ok
#include <type_traits>

template<class E, int size> class buffer {};
static_assert(std::is_same_v<buffer<char, 2*512>, buffer<char, 1024>>);   // 值相同

template<int N> struct I {};
static_assert(std::is_same_v<I<'A'>, I<65>>);    // 'A' 转换为 int 后为 65

template<class T> struct X {};
template<class> struct Y {};
template<class T> using Z = Y<T>;
static_assert(std::is_same_v<X<Y<int>>, X<Z<int>>>);   // 别名模板的特化就是 Y<int>
int main() {}
```

最后一例中 `Z<int>` 不是"另一个模板的特化"：别名模板的特化**等价于**替换后的类型（[[temp.alias]]），所以 `X<Z<int>>` 的实参就是 `Y<int>`。

## 模板实参等价（¶2）

¶2 两个值**模板实参等价**（[[g:template-argument-equivalent]]），当它们**类型相同**，并且：

| 列表项 | 类型 | 等价条件 |
|---|---|---|
| ¶2.1 | 整型 | 值相同 |
| ¶2.2 | 浮点类型 | 值 **identical**（不是 `==`） |
| ¶2.3 | `std::nullptr_t` | 总是等价 |
| ¶2.4 {{c++26}} | `std::meta::info` | 按 `==` 比较相等（[[expr.eq]]） |
| ¶2.5 | 枚举类型 | 值相同（脚注 105：枚举器的身份不被保留） |
| ¶2.6 | 指针类型 | **指针值**相同 |
| ¶2.7 | 成员指针类型 | 指向同一个类成员，或都是空成员指针值 |
| ¶2.8 | 引用类型 | 引用同一个对象或函数 |
| ¶2.9 | 数组类型 | 对应元素要么都在生命周期内且模板实参等价，要么都不在生命周期内 |
| ¶2.10 | 联合类型 | 都没有活跃成员；或活跃成员相同且活跃成员的值模板实参等价 |
| ¶2.11 | 闭包类型 | 总是等价 |
| ¶2.12 | 类类型 | 对应的直接子对象和引用成员模板实参等价 |

### 第一前提：类型相同

"类型相同"是所有情况的前提。这意味着 `template<auto V>` 的 `V<1>` 与 `V<1L>` 不同（`int` 与 `long`），`V<0>` 与 `V<false>` 也不同。

### 浮点：identical 而非 `==`（¶2.2）

浮点的"identical"指的是值在**表示意义上**完全一致，而不是 `==` 意义上的相等。两个关键后果：

- `0.0 == -0.0`，但它们**不** identical ⇒ `F<0.0>` 与 `F<-0.0>` 是不同类型；
- `NaN != NaN`，但同一个 NaN 值与自身 identical ⇒ `F<nan>` 与 `F<nan>` 是**同一个**类型（否则 `F<nan>` 将不等于它自己）。

```cpp run title="float-identical.cpp" ok
#include <limits>
#include <type_traits>

template<double D> struct F {};
constexpr double nan = std::numeric_limits<double>::quiet_NaN();

static_assert(!std::is_same_v<F<0.0>, F<-0.0>>);   // 相等但不 identical
static_assert( std::is_same_v<F<nan>, F<nan>>);    // 不相等但 identical
static_assert(!std::is_same_v<F<nan>, F<-nan>>);   // 符号位不同
int main() {}
```

为什么不用 `==`？因为类型身份必须是一个**等价关系**（自反、对称、传递）。浮点 `==` 对 NaN 不自反，对 `±0` 又把两个可区分的值合并——如果 `F<0.0>` 与 `F<-0.0>` 是同一类型，那么 `F<0.0>` 中 `1.0 / D` 的值是 `+∞` 还是 `-∞`？取决于哪个 TU 先实例化——这破坏了 ODR。

### 枚举：按值（¶2.5）

脚注 105：枚举器的身份不被保留。两个值相同的不同枚举器给出相同的实参：

```cpp run title="enum-value.cpp" ok
#include <type_traits>
enum E { a = 1, b = 1 };
template<E e> struct Q {};
static_assert(std::is_same_v<Q<a>, Q<b>>);   // a 和 b 的值都是 1
int main() {}
```

### 指针：按指针值（¶2.6）

¶2.6 比较的是**指针值**（[[basic.compound]]），而不是地址。指针值区分"指向对象 *o*"与"指向 *o* 的尾后"——即使地址数值相同：

```cpp run title="pointer-value.cpp" ok
#include <type_traits>
struct S { int a[2]; int b; } s;
template<int* p> struct P {};

// &s.a[2] 是 s.a 的尾后指针；&s.b 指向 s.b。二者地址可能相同，但指针值不同
static_assert(!std::is_same_v<P<&s.a[2]>, P<&s.b>>);
int main() {}
```

这正是 language lawyer 关心的"指针不只是地址"的又一体现。

### 闭包类型：总是等价（¶2.11）

无捕获 lambda 的闭包类型没有任何非静态数据成员，同一个闭包类型的所有值都等价。但每个 *lambda-expression* 有**自己的**闭包类型，所以两个不同的 lambda 表达式给出不同的实参（前提"类型相同"不满足）：

```cpp run title="closure.cpp" ok
#include <type_traits>
template<auto L> struct Lam {};

constexpr auto l1 = [] {};
constexpr auto l2 = l1;                     // 同一个闭包类型
static_assert(std::is_same_v<Lam<l1>, Lam<l2>>);
static_assert(!std::is_same_v<Lam<[] {}>, Lam<[] {}>>);   // 两个不同的闭包类型
int main() {}
```

### 类类型：逐子对象递归（¶2.12）

¶2.12 把类类型的等价归结为**直接子对象**（基类子对象和非静态数据成员）与**引用成员**的逐个等价。**用户定义的 `operator==` 完全不参与**：

```cpp run title="class-equiv.cpp" ok
#include <type_traits>
struct V {
    int v;
    constexpr bool operator==(const V&) const { return true; }   // 声称一切都相等
};
template<V v> struct VV {};
static_assert(!std::is_same_v<VV<V{1}>, VV<V{2}>>);   // 仍按成员 v 比较：不同
int main() {}
```

这是 C++20 中 [[P1907R1]] 的关键决定：最初的设计（P0732R2）把类类型实参的等价绑定到默认的 `operator==`（要求"强结构化相等"），P1907R1 改为现在纯粹按成员递归的定义，与 `operator==` 脱钩。理由在 [[temp.param]] 中已述：类型身份不能依赖用户可定义、可能不一致的代码。

### 数组与联合（¶2.9–¶2.10）

数组（作为类类型的成员出现时）逐元素比较，并且考虑**生命周期**：两个元素要么都在生命周期内且等价，要么都不在生命周期内。这为 C++20 起常量表达式中"部分初始化"的数组留出了空间。脚注 106：作为模板形参，数组会退化为指针（[[temp.param#15]]），所以 ¶2.9 只在数组是类的成员（或 C++26 中数组类型的模板形参对象，[[temp.param#13]]）时才起作用。

联合比较**活跃成员**：活跃成员不同的两个联合值不等价，即使它们的对象表示相同：

```cpp run title="union-equiv.cpp" ok
#include <type_traits>
union U { int i; float f; };
template<U u> struct UU {};
static_assert(!std::is_same_v<UU<U{.i = 0}>, UU<U{.f = 0.0f}>>);   // 活跃成员不同
static_assert( std::is_same_v<UU<U{.i = 0}>, UU<U{.i = 0}>>);
int main() {}
```

## 标准例子（¶3）

¶3 例 1 除了上面的 `buffer` 与别名模板，还有函数指针实参：

```cpp
template<class T, void(*err_fct)()> class list {};
list<int, &error_handler1> x1;
list<int, &error_handler2> x2;
list<int, &error_handler2> x3;
list<char, &error_handler2> x4;
```

`x2` 与 `x3` 同类型；`x1`（函数不同）与 `x4`（类型实参不同）各自是不同的类型。

## 待决的 decltype（¶4）

¶4 若表达式 `e` 是**类型待决**的，`decltype(e)` 表示一个**唯一的待决类型**。两个这样的 *decltype-specifier* 仅当其表达式**等价**（[[temp.over.link]]）时才指称同一类型。注 1：这样的类型可以通过 *typedef-name* 起别名。

这条规则是函数模板重声明匹配的基础：

```cpp title="decltype-identity.cpp" error
template<class T> auto f(T t) -> decltype(t + 1);
template<class T> auto f(T t) -> decltype(t + 1) { return t + 1; }   // 重声明：表达式等价
template<class T> auto f(T t) -> decltype(1 + t) { return 1 + t; }   // 另一个函数模板！

int x = f(1);   // error: 歧义——两个不同的函数模板，特化签名相同
```

`decltype(t + 1)` 与 `decltype(1 + t)` 对任何 `T` 可能都得到同一个类型，但在模板层面它们是两个不同的"唯一待决类型"，所以第三行声明了一个新的重载。若二者"功能等价但不等价"并且程序的含义依赖于此，按 [[temp.over.link#7]] 是 IFNDR；此例中它们表达式不同、也不是在同一声明的重声明上下文中被要求等价，所以是两个不同的模板，调用歧义。

为什么不把 `decltype(t + 1)` 求出来再比较？因为在模板定义处无法求——`T` 未知；而重声明匹配必须在定义处完成。

## 包索引的身份（¶5–¶6）{{c++26}}

¶5 对类型模板形参包 `T`，`T...[constant-expression]` 表示一个**唯一的待决类型**。两个这样的 *pack-index-specifier* 指称同一类型，仅当：

- ¶5.1 它们的 *typedef-name* 指称同一个模板形参包；且
- ¶5.2 若两个索引都**不是**值待决的，它们的值相同；否则索引表达式**等价**。

¶6 对 *pack-index-template-name* 有完全平行的规则。

```cpp run title="pack-index.cpp" ok
template<class... Ts>
struct L {
    using first     = Ts...[0];
    using alsofirst = Ts...[1 - 1];   // 索引非值待决，值都为 0 ⇒ 同一类型
};
static_assert(__is_same(L<int, char>::first, L<int, char>::alsofirst));
int main() {}
```

## 实现视角

!!! impl "实现视角"
    - **修饰名就是身份**：在 Itanium ABI 下，两个特化是否相同，最终体现为它们的修饰名是否相同。模板实参等价的每一条规则都对应修饰名的编码规则：整数按值编码；浮点按**位模式**编码（所以 `±0`、不同 NaN 自然区分）；类类型按成员递归编码；指针编码为它所指的实体（加上子对象路径）。
    - **closure 类型**的修饰名包含 lambda 在其上下文中的序号，所以不同 lambda 表达式有不同的修饰名。
    - **编译器内部**：Clang 用 `APValue` 表示常量模板实参的值，类型等价的判断对应 `APValue` 的结构比较（而不是调用任何 `operator==`）。

## 历史与演进

!!! history "历史与演进"
    - **C++98**：常量模板实参只有整型、枚举、指针、成员指针、引用，等价规则简单。
    - **C++11**：加入 `std::nullptr_t`。
    - **C++17**：`auto` 形参使"类型相同"这一前提变得可观察（`V<1>` 与 `V<1L>`）。
    - **C++20**：浮点、类类型、联合、数组成员、闭包类型；"模板实参等价"成为正式术语（[[P1907R1]]）。
    - **C++26**：`std::meta::info`（¶2.4）；包索引的身份规则（¶5–¶6）。

## 陷阱

!!! pitfall "常见误解"
    - **"类类型实参按 `operator==` 比较"**——不，按成员递归比较（¶2.12）。
    - **"`F<0.0>` 与 `F<-0.0>` 相同，因为 `0.0 == -0.0`"**——不同（¶2.2）。
    - **"同一地址的两个指针实参相同"**——比较的是指针值，尾后指针与指向下一个对象的指针不同（¶2.6）。
    - **"两个值相同的枚举器给出不同特化"**——相同（¶2.5）。
    - **"`decltype(a + b)` 与 `decltype(b + a)` 在函数模板签名中可以互换"**——不行，它们是不同的待决类型（¶4）。

## 思考题

!!! question "思考题 1"
    `template<auto V> struct X {};` 中，`X<0>`、`X<0u>`、`X<'\0'>`、`X<false>`、`X<nullptr>` 有几个不同的类型？

<details markdown="1">
<summary>答案</summary>

五个。`auto` 分别推导为 `int`、`unsigned`、`char`、`bool`、`std::nullptr_t`，类型不同，模板实参等价的前提（类型相同）不满足。
</details>

!!! question "思考题 2"
    ```cpp
    struct A { int x; int& r; };
    int g1, g2;
    template<A a> struct T {};
    ```
    `T<A{1, g1}>` 与 `T<A{1, g2}>` 相同吗？`T<A{1, g1}>` 与 `T<A{1, g1}>` 呢？

<details markdown="1">
<summary>答案</summary>

前者不同：引用成员 `r` 分别引用 `g1` 与 `g2`，¶2.8 要求引用同一个对象。后者相同：`x` 都是 1，`r` 都引用 `g1`。注意引用成员比较的是"引用谁"，而不是"被引用对象的值"——即使 `g1 == g2`，也不同。
</details>

## 小结

!!! summary "小结"
    | 实参种类 | 相同的条件 |
    |---|---|
    | 类型 | 同一类型（别名透明） |
    | 模板 | 同一模板（别名模板不是"新模板的特化"来源） |
    | 常量（总前提） | 类型相同 |
    | 整型 / 枚举 | 值相同 |
    | 浮点 | 值 identical（区分 ±0，NaN 自等价） |
    | 指针 / 引用 / 成员指针 | 同一指针值 / 同一实体 / 同一成员 |
    | 类 / 联合 / 数组 | 逐子对象递归；联合看活跃成员；数组看生命周期 |
    | 闭包 | 同类型即等价 |
    | 待决 `decltype` / 包索引 | 表达式等价才相同 |
