---
title: 部分特化
summary: 类模板与变量模板的部分特化：声明位置与可达性、同一性、对实参列表的四条限制（特化的常量实参不能依赖于部分特化的形参、必须比主模板更特化、无默认实参、包展开只能在最后）；匹配 = 从实际实参推导部分特化的形参 + 约束满足；多个匹配时改写为函数模板做偏序；部分特化的成员与主模板的成员无关；成员模板的部分特化
status: done
covers: temp.spec.partial.general, temp.spec.partial.match, temp.spec.partial.order, temp.spec.partial.member
since: c++98
related: temp.decls, temp.func.order, temp.deduct.type, temp.constr.order, temp.class, temp.expl.spec, temp.inst, temp.arg.nontype
tags: 模板, 部分特化, 偏序, void_t
updated: 2026-10-18
---

[[g:partial-specialization|**部分特化**]]（partial specialization）为模板提供一个替代定义：当特化的模板实参与部分特化给出的实参模式匹配时，就用它代替主模板的定义。`std::vector<bool>`（那是显式特化）之外，标准库里到处是部分特化：`std::unique_ptr<T[]>`、`std::is_pointer<T*>`、`std::tuple_size<std::array<T, N>>`……

只有类模板和变量模板可以部分特化（[[temp.decls#2]]）；函数模板用重载与偏序代替（[[temp.func.order]]）；别名模板不能特化（[[temp.decls#4]]）。

本页覆盖 13.7.6 全部四个小节：

| 小节 | 问题 |
|---|---|
| 13.7.6.1 [temp.spec.partial.general] | 怎样声明；有哪些限制 |
| 13.7.6.2 [temp.spec.partial.match] | 给定 `A<int*, char>`，哪些部分特化匹配 |
| 13.7.6.3 [temp.spec.partial.order] | 多个匹配时选谁 |
| 13.7.6.4 [temp.spec.partial.member] | 部分特化的成员；成员模板的部分特化 |

---

## 13.7.6.1 概述

### 替代定义；先有主模板；必须可达（¶1）

¶1 包含三条规则：

1. 部分特化提供替代定义，当特化的实参与部分特化的实参匹配时使用（匹配规则见下文 [temp.spec.partial.match]）。
2. 主模板的声明必须出现在它的任何部分特化之前。
3. 如果某个隐式或显式实例化在部分特化可见时会使用它，那么部分特化在该实例化处必须可达，否则 {{ifndr}}。

第 3 条是一个隐蔽的 ODR 陷阱：

```cpp title="a.cpp"
template<class T> struct Traits { static constexpr int v = 0; };
int use() { return Traits<int*>::v; }        // 实例化 Traits<int*>：此时只看得到主模板 → v = 0
template<class T> struct Traits<T*> { static constexpr int v = 1; };   // IFNDR：部分特化在使用之后才声明
```

编译器在 `use()` 中已经用主模板实例化了 `Traits<int*>`，后面再出现的部分特化无法追溯生效。标准不要求诊断，因为在多 TU 情形下（一个 TU 看见部分特化、另一个看不见）根本无法诊断。唯一稳妥的做法是把部分特化与主模板放在同一个头文件里。

### 同一性（¶2）

¶2 两个部分特化声明是同一实体，当且仅当它们是同一模板的部分特化，并且有等价的 *template-head* 和模板实参列表（等价的定义见 [[temp.over.link]]）。**每个部分特化都是一个独立的模板**，有自己的模板形参、自己的成员，可以有自己的部分特化成员定义（[temp.spec.partial.member]）。

### 例子（¶3）

¶3 第一个声明是主模板，其余是部分特化：

```cpp run ok
template<class T1, class T2, int I> class A             { };   // 主模板
template<class T, int I>            class A<T, T*, I>   { };   // #2
template<class T1, class T2, int I> class A<T1*, T2, I> { };   // #3
template<class T>                   class A<int, T*, 5> { };   // #4
template<class T1, class T2, int I> class A<T1, T2*, I> { };   // #5
int main() { }
```

部分特化的模板形参个数与主模板无关（#4 只有一个形参），只要求它的实参列表与主模板的形参列表对得上（[temp.spec.partial.match] ¶4）。

### 带约束的部分特化（¶4）

¶4 部分特化可以带约束（[[temp.constr]]）：

```cpp run ok
template<typename T> concept C = true;

template<typename T> struct X { static constexpr int v = 0; };
template<typename T> struct X<T*> { static constexpr int v = 1; };   // #1
template<C T> struct X<T> { static constexpr int v = 2; };           // #2

static_assert(X<int>::v == 2);
static_assert(X<int*>::v == 1);   // 见下文
int main() { }
```

两个部分特化都比主模板更特化。#1 是因为结构更具体：用主模板的实参推导 #1 的形参失败，反方向则成功。#2 的实参列表与主模板相同（都是 `<T>`），但 #2 更受约束（[[temp.constr.order]]）。这就是 C++20 的约束式部分特化：实参列表可以与主模板完全一样，只要更受约束即可。（`X<int*>` 同时匹配 #1 和 #2，结果选 #1。改写成函数模板后，用 #1 的变换 `X<U*>` 推导 #2 的 `X<T>` 成功，反过来用 #2 的变换 `X<U>` 推导 #1 的 `X<T*>` 失败。只有一个方向成功时，结构上的特化程度就决定了结果，约束根本不参与比较；只有双向推导都成功时，约束才作为平局裁决，[[temp.func.order#2]]。）

### 实参列表（¶5）与声明位置（¶6）

¶5 部分特化的模板实参列表就是模板名后面的 *template-argument-list*。

¶6 凡是可以定义主模板的作用域，都可以声明部分特化（[[dcl.meaning]]、[[class.mem]]、[[temp.mem]]）。特别地，成员模板的部分特化可以在类内声明，也可以在类外声明：

```cpp run ok
template<class T> struct A {
    struct C {
        template<class T2> struct B { static constexpr int v = 1; };
        template<class T2> struct B<T2**> { static constexpr int v = 2; };   // 类内部分特化 #1
    };
};

template<class T> template<class T2>
struct A<T>::C::B<T2*> { static constexpr int v = 3; };                    // 类外部分特化 #2

static_assert(A<short>::C::B<int*>::v == 3);    // 用 #2
static_assert(A<short>::C::B<int**>::v == 2);   // #1 与 #2 都匹配，#1 更特化
int main() { }
```

### 部分特化不引入名字（¶7）

¶7 部分特化声明不引入名字。使用主模板名时，所有可达的部分特化都会被考虑。注 1 指出由此得到的推论：指向类模板的 *using-declaration* 不限制通过它能找到的部分特化，即使部分特化在 using-declaration 之后才声明也是如此：

```cpp run ok
namespace N {
    template<class T1, class T2> class A { public: static constexpr int v = 0; };
}
using N::A;                                     // 引用主模板

namespace N {
    template<class T> class A<T, T*> { public: static constexpr int v = 1; };   // 之后才声明的部分特化
}

static_assert(A<int, int*>::v == 1);            // 经 using-declaration 使用，仍然用到部分特化
int main() { }
```

作为对比，函数重载集合经 using-declaration 引入时相当于一份快照，只引入当时可见的重载（[[namespace.udecl]]）。部分特化不是重载，而是附属于主模板的定义，总是跟着主模板走。

### 特化的与非特化的常量实参（¶8）

¶8 如果一个常量模板实参就是某个常量模板形参的名字，它称为[[g:non-specialized-argument|**非特化的**]]（non-specialized）；其他常量模板实参都是特化的（specialized）。`A<T, T*, I>` 中的 `I` 是非特化的；`A<int, T*, 5>` 中的 `5` 是特化的。这个分类服务于下面的 ¶9.1。

### 四条限制（¶9）

¶9 在部分特化的实参列表中：

**¶9.1 特化的常量实参所对应的模板形参，其类型不能依赖于部分特化的形参。**

```cpp error
template<class T, T t> struct C { };
template<class T> struct C<T, 1>;               // error: 形参 t 的类型 T 依赖于部分特化的形参 T

template<int X, int (*array_ptr)[X]> class A { };
int array[5];
template<int X> class A<X, &array> { };         // error: array_ptr 的类型 int(*)[X] 依赖于 X
```

为什么？匹配时要从实际实参推导部分特化的形参。对 `C<T, 1>` 来说，`1` 要与实际的第二个实参比较，而实际的第二个实参的类型是 `T`，在 `T` 推导出来之前，无法确定 `1` 应该转换成什么类型再比较（`C<char, 1>` 中的 `char(1)` 与 `C<long, 1>` 中的 `long(1)` 是不同的值）。标准选择直接禁止。如果该常量实参是非特化的（就是一个形参名），就没有这个问题。

**¶9.2 部分特化必须比主模板更特化**（按 [temp.spec.partial.order] 的规则）。最常见的违反是写出一个与主模板完全相同的部分特化：

```cpp error
template<class T> struct P { };
template<class T> struct P<T> { };              // error: 与主模板相同，没有特化任何东西
```

（带约束时例外：¶4 的 `template<C T> struct X<T>` 通过约束变得更特化。）

**¶9.3 部分特化的模板形参列表不能有默认模板实参。** 脚注给出的理由是没有任何语境会用到它们，因为部分特化的形参总是推导出来的，从来不会显式指定。

**¶9.4 实参中不能有未展开的包；若某个实参是包展开，它必须是实参列表中的最后一个。**

```cpp error
template<class T, class U> struct Q { };
template<class T, class U = int> struct Q<T*, U> { };   // error: ¶9.3 默认实参

template<class... Ts> struct R { };
template<class... Ts> struct R<Ts> { };                 // error: ¶9.4 未展开的包
template<class... Ts, class T> struct R<Ts..., T> { };  // error: ¶9.4 包展开不在最后
```

对最后一行，Clang 报告的是形参无法推导、该部分特化永远不会被使用（这条诊断在 Clang 中默认是错误），角度不同，但结论一致。

### 访问检查豁免（¶10）

¶10 部分特化的 *simple-template-id* 中，用来指定模板实参的非依赖名字不受通常的访问检查：模板实参可以是平时不可访问的私有类型或对象。依赖名在声明时无法检查，要到代入部分特化时才检查。

```cpp run ok
class Outer { struct Priv { }; };     // Priv 是私有的

template<class T> struct Trait { static constexpr int v = 0; };
template<class T> struct Trait<T(*)(Outer::Priv)> { static constexpr int v = 1; };   // OK: 不检查 Outer::Priv 的访问
template<> struct Trait<Outer::Priv> { static constexpr int v = 2; };               // 显式特化同理（[[temp.expl.spec]]）
int main() { }
```

这个豁免让库可以为自己的私有实现类型特化公共 trait，也让一些访问私有成员的元编程技巧成为可能（显式实例化有同样的豁免，[[temp.explicit]]）。

---

## 13.7.6.2 部分特化的匹配

### 三种结果（¶1）

¶1 在需要实例化的语境中使用模板时，要决定用主模板还是某个部分特化来生成实例，方法是把特化的模板实参与各部分特化的实参列表进行匹配。

- ¶1.1 恰好有一个匹配时，就用它。
- ¶1.2 有多个匹配时，用偏序规则（[temp.spec.partial.order]）找出最特化的那个；找不到就是歧义，程序非良构。
- ¶1.3 没有匹配时，用主模板。

这里说的是需要实例化的语境。仅仅指名 `A<int*, int>`（例如声明指针 `A<int*, int>* p;`）不需要选择定义，需要完整类型时才进行匹配。

### 匹配：推导加约束（¶2）

¶2 部分特化匹配给定的实际模板实参列表，当且仅当部分特化的模板实参可以从实际实参列表推导出来，并且推导出的实参满足部分特化的关联约束（如果有）。

推导用的是 [[temp.deduct.type]] 中从类型推导的规则：把部分特化的实参列表 `<T, T*, I>` 当作 P，实际实参 `<int, int*, 1>` 当作 A，逐个推导。

```cpp error
template<class T1, class T2, int I> class A             { };    // #1
template<class T, int I>            class A<T, T*, I>   { };    // #2
template<class T1, class T2, int I> class A<T1*, T2, I> { };    // #3
template<class T>                   class A<int, T*, 5> { };    // #4
template<class T1, class T2, int I> class A<T1, T2*, I> { };    // #5

A<int, int, 1>   a1;            // 用 #1：没有部分特化匹配
A<int, int*, 1>  a2;            // 用 #2（T = int, I = 1）；#5 也匹配，但 #2 更特化
A<int, char*, 5> a3;            // 用 #4（T = char）；#5 也匹配，但 #4 更特化
A<int, char*, 1> a4;            // 用 #5（T1 = int, T2 = char, I = 1）
A<int*, int*, 2> a5;            // error: #3 与 #5 都匹配，互不更特化 → 歧义
```

逐个分析 `a2`：

| 部分特化 | P | 推导 | 结果 |
|---|---|---|---|
| #2 | `<T, T*, I>` | 第 1 位 `T = int`；第 2 位 `T* ↔ int*` 得 `T = int`，一致；`I = 1` | 匹配 |
| #3 | `<T1*, T2, I>` | 第 1 位 `T1* ↔ int` 失败 | 不匹配 |
| #4 | `<int, T*, 5>` | 第 3 位 `5 ↔ 1` 不等 | 不匹配 |
| #5 | `<T1, T2*, I>` | `T1 = int`，`T2 = int`，`I = 1` | 匹配 |

#2 与 #5 都匹配，于是进入偏序。#2 要求第二个实参是指向第一个实参类型的指针，比 #5 更特化（见下文）。

带约束时的匹配如下：

```cpp run ok
template<typename T> concept C = requires (T t) { t.f(); };

template<typename T> struct S { static constexpr int v = 1; };    // #1
template<C T> struct S<T> { static constexpr int v = 2; };        // #2

struct Arg { void f(); };

static_assert(S<int>::v == 1);   // #2 的约束不满足 → 只有主模板
static_assert(S<Arg>::v == 2);   // 约束满足；#2 比主模板更特化（更受约束）
int main() { }
```

### 无法推导的部分特化（¶3）

¶3 如果由于部分特化的 *template-parameter-list* 与 *template-id* 的结构，其模板实参无法推导，程序非良构：

```cpp error
template<int I, int J> struct A { };
template<int I> struct A<I+5, I*2> { };         // error: I 出现在非推导语境中
template<int I> struct A<I, I> { };             // OK

template<int I, int J, int K> struct B { };
template<int I> struct B<I, I*2, 2> { };        // OK: I 可从第一个实参推导，I*2 只是被核对
```

`I+5` 是非推导语境（[[temp.deduct.type]]：含有模板形参的非平凡表达式）。如果 `I` 出现的每一处都是非推导语境，`I` 就永远推不出来，这个部分特化也永远不会匹配，所以标准要求在声明处就报错。而 `B<I, I*2, 2>` 中 `I` 能从第一位推出，第二位只是在推导完成后检查 `J == 2*I`。

### 实参列表对着主模板（¶4）

¶4 在指称类模板或变量模板特化的名字中（如 `A<int, int, 1>`），实参列表必须与主模板的形参列表匹配。部分特化的模板实参是从主模板的实参推导出来的。

由此得到一个关键推论：**先填入主模板的默认模板实参，然后才做匹配**。这就是 `void_t` 检测惯用法的工作原理：

```cpp run ok
#include <type_traits>
template<class T, class = void>                              // 主模板：第二个形参默认 void
struct has_type : std::false_type { };

template<class T>
struct has_type<T, std::void_t<typename T::type>> : std::true_type { };

struct Yes { using type = int; };
static_assert(has_type<Yes>::value);       // has_type<Yes, void>：部分特化推导成功（void_t<int> = void）
static_assert(!has_type<int>::value);      // has_type<int, void>：代入 int::type 失败 → 不匹配，用主模板
int main() { }
```

`has_type<Yes>` 先变成 `has_type<Yes, void>`（主模板的默认实参），然后与部分特化 `<T, void_t<typename T::type>>` 匹配：第一位推出 `T = Yes`；第二位是非推导语境，代入得 `void_t<int>` 即 `void`，与实际实参 `void` 一致，匹配。对 `int`，代入 `int::type` 失败，这个失败是 SFINAE（推导失败），部分特化不匹配。（为什么 `void_t` 的未使用形参能参与 SFINAE？见 [[temp.alias#3]]。）

---

## 13.7.6.3 部分特化的偏序

### 改写为函数模板（¶1）

¶1 对两个部分特化，第一个比第二个[[g:more-specialized|**更特化**]]（more specialized），当且仅当按下述方式改写得到的两个函数模板中，第一个比第二个更特化（按函数模板的偏序规则 [[temp.func.order]]）：

- ¶1.1 每个函数模板的模板形参和关联约束与对应的部分特化相同；
- ¶1.2 每个函数模板只有一个函数形参，其类型是一个类模板特化，模板实参就是部分特化的 *simple-template-id* 的实参列表。

换句话说，把 `template<P...> class X<args>` 改写成 `template<P...> void f(X<args>)`，再用函数模板偏序判断哪个更特化。这样部分特化的偏序完全复用函数模板的机制（合成唯一类型或值，双向推导），不需要另起一套。

### 例子（¶2）

```cpp run ok
template<int I, int J, class T> struct X { static constexpr int v = 0; };
template<int I, int J> struct X<I, J, int> { static constexpr int v = 1; };   // #1
template<int I>        struct X<I, I, int> { static constexpr int v = 2; };   // #2

// 改写：
template<int I0, int J0> void f(X<I0, J0, int>);   // A
template<int I0>         void f(X<I0, I0, int>);   // B

static_assert(X<3, 3, int>::v == 2);   // #1、#2 都匹配，#2 更特化
static_assert(X<1, 2, int>::v == 1);
int main() { }
```

A 与 B 的偏序：

| 方向 | 用变换后的 ... 作实参 | 对另一个作形参推导 | 结果 |
|---|---|---|---|
| B → A | B 变换：`X<u, u, int>`（u 是合成值） | A 的 `X<I0, J0, int>`：`I0 = u, J0 = u` | 成功 |
| A → B | A 变换：`X<u1, u2, int>`（两个不同的合成值） | B 的 `X<I0, I0, int>`：`I0 = u1` 与 `I0 = u2` 冲突 | 失败 |

所以 B 至少与 A 一样特化，反之则不成立。B 更特化，因此 #2 更特化。

`auto` 常量形参的例子：

```cpp run ok
template<auto v>    struct Y { static constexpr int k = 0; };
template<auto* p>   struct Y<p> { static constexpr int k = 1; };     // #3
template<auto** pp> struct Y<pp> { static constexpr int k = 2; };    // #4

int i; int* ip = &i;
static_assert(Y<&i>::k == 1);       // 只匹配 #3
static_assert(Y<&ip>::k == 2);      // #3、#4 都匹配，#4 更特化
static_assert(Y<1>::k == 0);
int main() { }
```

改写为 `template<auto* p0> void g(Y<p0>)`（C）与 `template<auto** pp0> void g(Y<pp0>)`（D）。偏序时为常量形参合成的值，其类型中的占位符也替换为合成的唯一类型（[[temp.func.order#3]]）：D 变换后的值类型是 `U**`，能匹配 C 的 `auto*`（`auto = U*`）；C 变换后的值类型是 `V*`，不能匹配 D 的 `auto**`。所以 D 更特化。

带约束的例子：

```cpp run ok
template<typename T> concept C = requires (T t) { t.f(); };
template<typename T> concept D = C<T> && requires (T t) { t.f(); };

template<typename T> class S { public: static constexpr int v = 0; };
template<C T> class S<T> { public: static constexpr int v = 1; };   // #1
template<D T> class S<T> { public: static constexpr int v = 2; };   // #2

struct Arg { void f(); };
static_assert(S<Arg>::v == 2);   // #2 更受约束（D 包含 C）
int main() { }
```

改写后的 `template<C T> void f(S<T>)` 与 `template<D T> void f(S<T>)` 双向推导都成功，于是进入 [[temp.func.order#8]] 的约束比较：`D` 的规范形式包含 `C` 的（[[temp.constr.order]]），B 更受约束，故 #2 更特化。

---

## 13.7.6.4 类模板部分特化的成员

### 成员彼此无关（¶1）

¶1 类模板部分特化的成员与主模板的成员无关。部分特化中以需要定义的方式使用的成员必须有定义；主模板成员的定义永远不会用作部分特化成员的定义。部分特化成员的显式特化，与主模板成员的显式特化写法相同。

```cpp
// 主模板
template<class T, int I> struct A {
    void f();
};
template<class T, int I> void A<T, I>::f() { }      // 主模板的成员

// 部分特化
template<class T> struct A<T, 2> {
    void f();
    void g();
    void h();
};
template<class T> void A<T, 2>::g() { }              // 部分特化的成员
template<> void A<char, 2>::h() { }                  // 部分特化成员的显式特化

int main() {
    A<char, 0> a0;
    A<char, 2> a2;
    a0.f();      // OK: 主模板成员的定义
    a2.g();      // OK: 部分特化成员的定义
    a2.h();      // OK: 显式特化的定义
    a2.f();      // 错误：A<T, 2>::f 没有定义；主模板的 f 在这里不被使用
}
```

最后一行 odr-use 了一个没有定义的函数，程序非良构，不要求诊断（[[basic.def.odr]]），实践中表现为链接错误（`A<char, 2>::f()` 未定义）。**部分特化是一个完整的替代类定义**，而不是在主模板上打补丁，需要的每个成员都要重新声明、重新定义。想要共享实现，就把公共部分抽到基类里。

### 成员模板的部分特化（¶2）

¶2 如果类模板的成员模板有部分特化，这些部分特化也是外围类模板的成员模板；外围类模板实例化时，每个成员模板部分特化的声明也随之实例化。此外：

- 如果针对外围类模板的某个（隐式）特化显式特化了主成员模板，那么对这个外围特化而言，该成员模板的部分特化都被忽略；
- 如果显式特化的是成员模板的某个部分特化，那么主成员模板和其他部分特化仍然会被考虑。

```cpp run ok
template<class T> struct A {
    template<class T2> struct B { static constexpr int v = 1; };          // #1
    template<class T2> struct B<T2*> { static constexpr int v = 2; };     // #2
};

template<> template<class T2> struct A<short>::B { static constexpr int v = 3; };   // #3：对 A<short> 显式特化主成员模板

static_assert(A<char>::B<int*>::v == 2);    // 用 #2
static_assert(A<short>::B<int*>::v == 3);   // 用 #3：A<short> 的主成员模板被显式特化，#2 被忽略
static_assert(A<char>::B<int>::v == 1);     // 用 #1
int main() { }
```

为什么对 `A<short>` 忽略 #2？因为 `A<short>::B` 重新定义成了一个全新的成员模板 #3。原来的部分特化 #2 是针对主模板 #1 写的，#1 既然已被替换，#2 也就失去了意义。

---

## 变量模板的部分特化

变量模板的部分特化遵循本节的全部规则（[[temp.decls#2]] 明确它们可以部分特化）：

```cpp run ok
template<class T> constexpr int ptr_depth = 0;
template<class T> constexpr int ptr_depth<T*> = 1 + ptr_depth<T>;
template<class T> constexpr int ptr_depth<T* const> = 1 + ptr_depth<T>;

static_assert(ptr_depth<int> == 0);
static_assert(ptr_depth<int**> == 2);
static_assert(ptr_depth<int* const*> == 2);
int main() { }
```

部分特化的变量可以有与主模板不同的类型（例如主模板 `int`、部分特化 `long`），因为每个部分特化是独立的模板。

---

## 实现视角

!!! impl "实现视角"
    - **匹配的成本**：编译器在需要类模板特化的定义时，对每个可达的部分特化做一次推导，再对所有匹配者两两做偏序。部分特化很多的 trait（例如对几十种类型逐一特化）主要靠显式特化而非部分特化来避免这一开销。
    - **诊断**：对永远不会被使用的部分特化（¶3、¶9.4），Clang 给出 `-Wunusable-partial-specialization`，默认是错误；对 ¶9.2 的违反，它报告部分特化没有特化任何模板实参。
    - **可达性 IFNDR**：编译器通常不会发现对 ¶1 第 3 条的违反。其后果是同一个特化在不同 TU 中有不同定义，即 ODR 违反，链接后可能表现为难以解释的行为差异。

## 历史与演进

!!! history "历史与演进"
    - **C++98**：类模板部分特化。
    - **C++14**：变量模板及其部分特化。
    - **C++17**：`auto` 常量模板形参使得 ¶2 例中 `Y<auto* p>` 这样的部分特化成为可能；`std::void_t` 入库，检测惯用法流行。
    - **C++20**：带约束的部分特化（¶4），实参列表可以与主模板相同，只要更受约束；非类型模板实参的规则随类类型 NTTP 一起更新。
    - **C++26**：术语"非类型模板形参"改称"常量模板形参"，¶8 中特化的与非特化的常量实参随之改写。

## 陷阱

!!! pitfall "常见误解"
    - 误以为部分特化继承主模板的成员。它不继承，它是完整的替代定义。
    - 误以为部分特化可以在使用之后声明。它必须在每个会用到它的实例化之前可达，否则 IFNDR。
    - 误以为对 `template<class T, T t> struct C` 可以写 `template<class T> struct C<T, 1>`。这不合法（¶9.1）。
    - 误以为部分特化可以有默认模板实参。这不允许（¶9.3），默认值应该放在主模板上，`void_t` 惯用法正是这样做的。
    - 误以为两个都匹配时编译器会选看起来更具体的那个。编译器按严格的偏序规则选择，互不更特化就是歧义错误。

## 思考题

!!! question "思考题 1"
    下面的 `T<int*, int*>` 用哪个定义？

    ```cpp
    template<class A, class B> struct T { };          // #0
    template<class A>          struct T<A, A> { };    // #1
    template<class A, class B> struct T<A*, B*> { };  // #2
    ```

<details markdown="1">
<summary>答案</summary>

歧义，非良构。#1（`A = int*`）与 #2（`A = int, B = int`）都匹配。做偏序时改写为 `f(T<A, A>)` 与 `g(T<A*, B*>)`。用 #1 的变换 `T<U, U>` 推导 #2 的 `T<A*, B*>`：`U` 不是指针，失败。用 #2 的变换 `T<U1*, U2*>` 推导 #1 的 `T<A, A>`：`A = U1*` 与 `A = U2*` 冲突，失败。双向都失败，互不更特化，歧义。解决办法是再加一个 `template<class A> struct T<A*, A*>`，它比两者都更特化。
</details>

!!! question "思考题 2"
    为什么 `void_t` 检测惯用法要求主模板的第二个形参默认为 `void`，而不是别的类型（比如 `int`）？

<details markdown="1">
<summary>答案</summary>

由 ¶4，`has_type<X>` 先用主模板的默认实参补全为 `has_type<X, Default>`，再与部分特化 `<T, void_t<typename T::type>>` 匹配。部分特化的第二个实参代入成功时总是 `void`。如果 `Default` 是 `int`，匹配就要求 `void == int`，永远失败，于是部分特化永远不会被选中，trait 恒为 false。默认值必须与 `void_t` 的结果一致。
</details>

!!! summary "小结"
    - 部分特化要求主模板先声明，在用到它的实例化处必须可达（否则 IFNDR）；它不引入名字，总是随主模板一起被考虑。
    - 限制包括：特化的常量实参的形参类型不能依赖部分特化的形参；必须比主模板更特化；无默认实参；包展开只能在最后；部分特化的形参必须可推导。
    - 匹配是指能从（补全默认实参后的）实际实参推导出部分特化的形参，并且约束得到满足。没有匹配时用主模板，一个匹配时用它，多个匹配时做偏序，没有最优者就是歧义。
    - 偏序的做法是改写为单参函数模板，再用 [[temp.func.order]] 比较；约束作为平局裁决。
    - 部分特化的成员与主模板无关；显式特化主成员模板时，它的部分特化被忽略。
