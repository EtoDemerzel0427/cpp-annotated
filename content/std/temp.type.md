---
title: 类型等价
summary: 两个 template-id 何时是同一个类型、函数或变量：类型实参看类型，常量实参看模板实参等价（整数按值、浮点按位相同、指针按指针值、类类型逐个子对象比较），待决的 decltype 和包索引看表达式是否等价。
status: done
papers: P1907R1
related: temp.param, temp.arg.nontype, temp.over.link, temp.alias, basic.def.odr, basic.compound, expr.eq
tags: 模板, 类型等价, 模板实参等价, 常量模板实参
updated: 2026-10-19
---

!!! tldr
    - `buffer<char, 2*512>` 和 `buffer<char, 1024>` 是同一个类型：比较的是常量实参转换后的值，不是实参表达式。
    - 常量实参相同的前提是类型相同，所以 `template<auto V>` 下 `X<0>` 和 `X<0u>` 是两个类型。
    - 浮点实参按位比较：`0.0` 和 `-0.0` 给出不同的特化，同一个 NaN 与自己给出同一个特化。
    - 类类型实参逐个子对象比较，用户写的 `operator==` 不参与。
    - `decltype(t + 1)` 和 `decltype(1 + t)` 在函数模板签名里是两个不同的类型，因为表达式不等价。

## 什么时候是同一个特化（¶1）

```cpp run title="same-template-id.cpp" ok
#include <type_traits>

template<class E, int size> class buffer {};
static_assert(std::is_same_v<buffer<char, 2*512>, buffer<char, 1024>>);   // 值相同

template<int N> struct I {};
static_assert(std::is_same_v<I<'A'>, I<65>>);    // 'A' 转换为 int 后为 65

template<class T> struct X {};
template<class> struct Y {};
template<class T> using Z = Y<T>;
static_assert(std::is_same_v<X<Y<int>>, X<Z<int>>>);   // Z<int> 就是 Y<int>
int main() {}
```

同样的实参必须得到同一个特化，否则 `std::vector<int>` 在两个翻译单元里就可能是两个类型，ODR、链接和重载都无从谈起。

¶1 两个 *template-id* 在下面几条都成立时相同，相同的 *template-id* 指同一个类、函数或变量：

- ¶1.1 模板名（或 *operator-function-id*、*literal-operator-id*）指同一个模板；
- ¶1.2 对应的类型实参是同一个类型；
- ¶1.3 对应的常量实参确定的形参值**模板实参等价**（见下一节）；
- ¶1.4 对应的模板模板实参指同一个模板。

¶1.3 比较的是实参转换成形参类型之后的值（[[temp.arg.nontype]]），所以 `2*512` 和 `1024`、`'A'` 和 `65` 都没有区别。别名模板的特化就是替换后的类型（[[temp.alias]]），所以 `Z<int>` 不是另一个模板的特化，`X<Z<int>>` 的实参就是 `Y<int>`。

¶3 是标准的例子，除了上面的 `buffer` 和别名模板，还有一组函数指针实参：`list<int, &h2>` 与 `list<int, &h2>` 同类型，与 `list<int, &h1>`（函数不同）或 `list<char, &h2>`（类型实参不同）都不同类型。

## 模板实参等价（¶2）

¶2 两个值**模板实参等价**（[[g:template-argument-equivalent]]），要求它们类型相同，并且按类型满足下表的条件：

| 列表项 | 类型 | 等价条件 |
|---|---|---|
| ¶2.1 | 整型 | 值相同 |
| ¶2.2 | 浮点类型 | 值 identical（不是 `==`） |
| ¶2.3 | `std::nullptr_t` | 总是等价 |
| ¶2.4 {{c++26}} | `std::meta::info` | 用 `==` 比较相等（[[expr.eq]]） |
| ¶2.5 | 枚举类型 | 值相同 |
| ¶2.6 | 指针类型 | 指针值相同 |
| ¶2.7 | 成员指针类型 | 指向同一个类成员，或都是空成员指针值 |
| ¶2.8 | 引用类型 | 引用同一个对象或函数 |
| ¶2.9 | 数组类型 | 对应元素要么都在生命周期内且等价，要么都不在生命周期内 |
| ¶2.10 | 联合类型 | 都没有活跃成员，或活跃成员相同且其值等价 |
| ¶2.11 | 闭包类型 | 总是等价 |
| ¶2.12 | 类类型 | 对应的直接子对象和引用成员都等价 |

类型相同是所有情形的前提。`template<auto V>` 下，`V` 的类型由实参推导，于是 `X<1>` 与 `X<1L>`（`int` 与 `long`）、`X<0>` 与 `X<false>` 都是不同的特化。

### 浮点：按位相同，不按 `==`（¶2.2）

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

identical 指两个值在表示上完全一致。`0.0 == -0.0` 为真，但两者不 identical；`nan == nan` 为假，但同一个 NaN 与自己 identical。

类型身份必须是等价关系，每个值至少要和自己相同。浮点 `==` 对 NaN 不满足这一点，又把 `+0.0` 和 `-0.0` 这两个可以区分的值合并了。如果 `F<0.0>` 与 `F<-0.0>` 是同一个类型，那么其中 `1.0 / D` 是正无穷还是负无穷，就要看哪个翻译单元先实例化它。

### 枚举：按值（¶2.5）

```cpp run title="enum-value.cpp" ok
#include <type_traits>
enum E { a = 1, b = 1 };
template<E e> struct Q {};
static_assert(std::is_same_v<Q<a>, Q<b>>);   // a 和 b 的值都是 1
int main() {}
```

脚注 105 说明，枚举器本身的身份不保留。值相同的两个枚举器给出同一个特化。

### 指针：按指针值（¶2.6）

```cpp run title="pointer-value.cpp" ok
#include <type_traits>
struct S { int a[2]; int b; } s;
template<int* p> struct P {};

// &s.a[2] 是 s.a 的尾后指针，&s.b 指向 s.b。地址可能相同，指针值不同
static_assert(!std::is_same_v<P<&s.a[2]>, P<&s.b>>);
int main() {}
```

¶2.6 比较的是指针值（[[basic.compound]]），不是地址。指向对象的指针和尾后指针是不同的指针值，即使数值上地址相同。

### 闭包类型：类型相同即等价（¶2.11）

```cpp run title="closure.cpp" ok
#include <type_traits>
template<auto L> struct Lam {};

constexpr auto l1 = [] {};
constexpr auto l2 = l1;                     // 同一个闭包类型
static_assert(std::is_same_v<Lam<l1>, Lam<l2>>);
static_assert(!std::is_same_v<Lam<[] {}>, Lam<[] {}>>);   // 两个不同的闭包类型
int main() {}
```

能用作常量实参的闭包没有捕获，也就没有数据成员可比，同一个闭包类型的值总是等价的。但每个 lambda 表达式都有自己的闭包类型，两个 lambda 表达式不满足类型相同的前提。

### 类类型：逐个子对象比较（¶2.12）

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

¶2.12 把类类型的等价归结为每个直接子对象（基类子对象和非静态数据成员）和每个引用成员的等价。用户定义的 `operator==` 完全不参与，因为类型身份不能依赖用户写的、可能前后不一致的代码。

C++20 最初的设计要求类类型实参有默认的 `operator==`，并用它判断等价；[[P1907R1]] 改成了现在这种逐成员递归的定义，与 `operator==` 脱钩。

### 数组与联合（¶2.9–¶2.10）

```cpp run title="union-equiv.cpp" ok
#include <type_traits>
union U { int i; float f; };
template<U u> struct UU {};
static_assert(!std::is_same_v<UU<U{.i = 0}>, UU<U{.f = 0.0f}>>);   // 活跃成员不同
static_assert( std::is_same_v<UU<U{.i = 0}>, UU<U{.i = 0}>>);
int main() {}
```

联合比较的是活跃成员：活跃成员不同的两个值不等价，即使对象表示的每一位都相同。

数组逐元素比较，并且考虑生命周期：两个元素要么都在生命周期内且等价，要么都不在生命周期内。数组类型的模板形参会调整为指针（脚注 106，[[temp.param#15]]），所以 ¶2.9 主要用于类类型实参里的数组成员。

## 待决的 decltype 与包索引（¶4–¶6）

```cpp title="decltype-identity.cpp" error
template<class T> auto f(T t) -> decltype(t + 1);
template<class T> auto f(T t) -> decltype(t + 1) { return t + 1; }   // 重声明：表达式等价
template<class T> auto f(T t) -> decltype(1 + t) { return 1 + t; }   // 另一个函数模板

int x = f(1);   // error: 歧义，两个函数模板的特化签名相同
```

¶4 如果表达式 `e` 是类型待决的（依赖模板形参），`decltype(e)` 表示一个独有的待决类型。两个这样的 `decltype` 只有在表达式等价（[[temp.over.link]]）时才是同一个类型。注 1 补充，这样的类型可以用 typedef 起别名。

所以上例中 `decltype(t + 1)` 与 `decltype(1 + t)` 虽然对任何 `T` 都得到同一个类型，在模板层面却是两个类型，第三行声明了一个新的函数模板。调用时两个特化签名相同，偏序也分不出高下，于是歧义。

编译器不能先把 `decltype(t + 1)` 算出来再比较，因为在模板定义处 `T` 还未知，而判断两个声明是不是同一个函数模板必须在定义处完成。

¶5 {{c++26}} 包索引 `T...[N]`（[[dcl.type.pack.index]]）同理：对类型模板形参包 `T`，`T...[N]` 表示一个独有的待决类型。两个这样的类型相同，要求它们索引的是同一个形参包，并且索引相同：两个索引都不是值待决的，就比较它们的值，否则比较索引表达式是否等价。

```cpp run title="pack-index.cpp" ok
template<class... Ts>
struct L {
    using first     = Ts...[0];
    using alsofirst = Ts...[1 - 1];   // 索引不是值待决的，值都是 0：同一类型
};
static_assert(__is_same(L<int, char>::first, L<int, char>::alsofirst));
int main() {}
```

¶6 对模板名的包索引 *pack-index-template-name*（对模板模板形参包取第 N 个模板，[[temp.names]]）有平行的规则。这是比 C++26 类型包索引更新的措辞。

## 实现视角

!!! impl "修饰名就是身份"
    在 Itanium ABI 下，两个特化是否相同最终体现为修饰名是否相同，等价规则都能在编码规则里找到对应：整数按值编码；浮点按位模式编码，所以 `±0` 和不同的 NaN 自然区分；类类型按成员递归编码；指针编码为所指的实体及子对象路径。闭包类型的修饰名含有 lambda 在所在上下文中的序号，所以不同的 lambda 表达式修饰名不同。

## 常见误解

!!! pitfall "类类型实参按 `operator==` 比较"
    按成员逐个比较（¶2.12），`operator==` 写成什么样都不影响。

!!! pitfall "`0.0 == -0.0`，所以 `F<0.0>` 和 `F<-0.0>` 相同"
    它们是不同的类型（¶2.2）。

!!! pitfall "地址相同的两个指针实参相同"
    比较的是指针值，尾后指针与恰好在那里的下一个对象的指针不同（¶2.6）。

!!! pitfall "`decltype(a + b)` 和 `decltype(b + a)` 在函数模板签名里可以互换"
    不可以，它们是不同的待决类型（¶4）。声明和定义要逐字对应。

## 思考题

!!! question "思考题 1"
    `template<auto V> struct X {};` 中，`X<0>`、`X<0u>`、`X<'\0'>`、`X<false>`、`X<nullptr>` 是几个不同的类型？

<details markdown="1">
<summary>答案</summary>

五个。`V` 的类型分别推导为 `int`、`unsigned`、`char`、`bool`、`std::nullptr_t`，类型不同，不满足等价的前提。
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

前者不同：引用成员 `r` 分别引用 `g1` 和 `g2`，¶2.8 要求引用同一个对象。后者相同。引用成员比较的是引用了哪个对象，不是对象的值，所以即使 `g1 == g2`，前两者也不同。
</details>
