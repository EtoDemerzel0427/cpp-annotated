---
title: 模板序言
summary: 模板声明的骨架：template-head 与 requires-clause 的受限文法、哪些声明可以被模板化、变量模板、一个模板声明只能有一个声明符、templated entity 的定义，以及"定义必须在实例化处可达"的 IFNDR 规则。
status: done
related: temp, temp.param, temp.constr.decl, temp.names, temp.spec, temp.inst, temp.explicit, basic.def.odr, dcl.decl
tags: 模板, templated entity, requires-clause, 变量模板
updated: 2026-10-17
---

[temp.pre] 是第 13 章的"总则"：它规定一个**模板声明**（*template-declaration*）由什么组成、能声明什么、不能声明什么，并定义了贯穿全章（乃至全标准）的一个关键术语——**templated entity**。

这一节的规则看似琐碎，但每一条背后都有一个工程上的理由：模板会在不同翻译单元、不同实例化点被反复"展开"，标准必须保证这种展开是**确定的**（同一个模板实参总是得到同一个实体）、**可解析的**（不需要语义信息就能切分记号）、**可链接的**（不同 TU 的特化能被视为同一个）。

## 模板是什么，模板声明长什么样（¶1）

¶1 **模板**（template）定义以下五种东西之一：

| 模板定义的是 | 名称 | 例子 |
|---|---|---|
| 一族类 | 类模板 | `template<class T> struct vector;` |
| 一族函数 | 函数模板 | `template<class T> T max(T, T);` |
| 一族变量 | 变量模板 {{c++14}} | `template<class T> constexpr T pi = T(3.14159L);` |
| 一族类型的别名 | 别名模板 {{c++11}} | `template<class T> using ptr = T*;` |
| 一个概念 | 概念 {{c++20}} | `template<class T> concept C = sizeof(T) > 1;` |

文法上，一个模板声明是 *template-head* 后面跟一个 *declaration* 或 *concept-definition*：

```text
template-declaration:
    template-head declaration
    template-head concept-definition
template-head:
    template < template-parameter-list > requires-clause(opt)
requires-clause:
    requires constraint-logical-or-expression
```

注意 *requires-clause* 是 *template-head* 的一部分。这意味着"模板头"本身就携带约束：两个模板声明要被视为同一个模板的重声明，它们的 *template-head* 必须**等价**——包括 *requires-clause*（[[temp.over.link]]）。

注 1 提醒：*template-parameter-list* 之后的 `>` 可以是把 `>>` 拆成两个 `>` 的产物（[[temp.names#8]]），所以 `template<template<class> class TT>` 这类写法从 C++11 起不必在 `>>` 之间加空格。

## 哪些声明可以被模板化（¶2）

¶2 模板声明中的 *declaration*（若有）必须是下列之一：

- ¶2.1 声明或定义一个**函数、类或变量**；
- ¶2.2 **定义**类模板（或嵌套在类模板中的类）的成员函数、成员类、成员枚举或静态数据成员——这是"在类外定义类模板的成员"的形式：`template<class T> void A<T>::f() {}`；
- ¶2.3 定义类或类模板的**成员模板**；
- ¶2.4 一个 *friend-type-declaration*；
- ¶2.5 一个**推导指引**（*deduction-guide*，[[temp.deduct.guide]]）；
- ¶2.6 一个 *alias-declaration*（别名模板）。

并且**不能**是链接规格说明（*linkage-specification*）。

反过来看清单之外的东西：**枚举、`typedef`、命名空间**都不能是模板。

```cpp title="not-templatable.cpp" error
template<class T> enum E { a };          // error: 枚举不能是模板（但类模板的成员枚举可以）
template<class T> typedef T X;           // error: typedef 不能是模板，请用别名模板
template<class T> using Y = T;           // OK: alias-declaration（¶2.6）
template<class T> extern "C++" void f(T);// error: 声明不能是 linkage-specification
```

为什么 `typedef` 不能模板化而 `using` 可以？历史原因：C++11 引入别名模板时，委员会选择了新语法 `using`，以免 `typedef` 的声明符语法（名字埋在中间）与模板头搅在一起。从此 `using` 成了别名的推荐写法。

为什么不能是 *linkage-specification*？`extern "C" { ... }` 块里的模板声明会让模板获得 C 语言链接，而 C 链接的名字不经过名字修饰（mangling），无法区分 `f<int>` 和 `f<double>`。[[dcl.link]] 也规定模板不能有 C 语言链接：

```cpp title="c-linkage.cpp" error
extern "C" {
    template<class T> void f(T);   // error: 模板不能具有 C 语言链接
}
```

!!! note "成员枚举可以 templated，但不能是模板"
    ¶2.2 允许在类外**定义**类模板的成员枚举：`template<class T> enum class A<T>::E : int { x };`。这个枚举是 templated entity（¶8.4），但它本身不是"枚举模板"——它只是随类模板一起被特化。

## 变量模板与静态数据成员模板（¶3）

¶3 模板声明本身也是一个声明。由变量的模板声明引入的声明是**变量模板**（variable template）；类作用域中的变量模板叫**静态数据成员模板**（static data member template）。

```cpp run title="variable-template.cpp" ok
#include <cstdio>

template<class T>
constexpr T pi = T(3.1415926535897932385L);

template<class T>
T circular_area(T r) { return pi<T> * r * r; }

struct S {
    template<class T>
    static constexpr int size = sizeof(T);   // 静态数据成员模板（constexpr ⇒ 隐式 inline）
};

int main() {
    std::printf("%f %d\n", circular_area(1.0), S::size<double>);
}
```

变量模板出现之前（C++11），人们用 `std::integral_constant<...>::value` 或 `constexpr` 函数模板来模拟"随类型变化的常量"。变量模板让 `std::is_same_v<T, U>` 这类 `_v` 后缀的库组件成为可能（C++17 引入）。变量模板可以部分特化（[[temp.spec.partial]]）——注 3 指出：用 *simple-template-id* 声明类模板或变量模板，就是在声明部分特化：

```cpp run title="var-partial.cpp" ok
template<class T> constexpr int rank = 0;
template<class T> constexpr int rank<T[]> = 1 + rank<T>;      // 部分特化
template<class T, int N> constexpr int rank<T[N]> = 1 + rank<T>;

static_assert(rank<int[2][3]> == 2);
static_assert(rank<int[][4]> == 2);
int main() {}
```

## 模板只能在命名空间或类作用域（¶4）

¶4 注 2：模板声明只能出现在**命名空间作用域或类作用域**。函数体内不能声明模板——包括局部类的成员模板（非闭包类型的局部类不能有成员模板，见 [[temp.mem#2]]）。

```cpp title="block-scope.cpp" error
void g() {
    template<class T> struct L {};   // error: 块作用域中不能声明模板
    auto lam = [](auto x) { return x; };   // OK: 泛型 lambda 的 operator() 是成员模板，
                                           //     但它属于闭包类型，由 lambda 表达式隐式声明
}
```

泛型 lambda 是"在函数体内得到一个模板"的唯一途径，它之所以合法，是因为闭包类型及其函数调用运算符模板由语言生成，而不是由一个出现在块作用域的 *template-declaration* 声明的。

¶4 的另外两条规范性要求：

1. 模板声明的 *declaration* 不能是 *export-declaration*。要导出一个模板，`export` 写在最外面：`export template<class T> void f(T);`，而不是 `template<class T> export void f(T);`。
2. 函数模板声明的 *declarator-id* 中，*unqualified-id* 必须是一个**名字**（name）——不能是 *template-id*。这条规则禁止了"函数模板部分特化"：

```cpp title="no-fn-partial-spec.cpp" error
template<class T> void f(T);
template<class T> void f<T*>(T*);   // error: 函数模板不能部分特化
template<class T> void f(T*);       // OK: 这是另一个重载的函数模板，交给偏序（[temp.func.order]）
```

"名字"在标准里（[[basic.pre]]）包括 *identifier*、*operator-function-id*、*conversion-function-id*、*literal-operator-id*，所以运算符模板、转换函数模板、字面量运算符模板都没问题。

## 一个模板声明只能有一个声明符（¶5）

¶5 在模板声明、显式特化或显式实例化中，*init-declarator-list* **至多有一个**声明符；声明类模板时则**不能有**声明符。

```cpp title="one-declarator.cpp" error
template<class T> T a, b;                 // error: 一个模板声明只能声明一个实体
template<class T> struct S {} s;          // error: 声明类模板时不能同时声明变量
```

为什么？因为 *template-head* 引入的形参作用域只对应一个实体：如果允许 `template<class T> T a, b;`，`a` 和 `b` 是两个变量模板还是一个？它们共享同一个 `T` 吗？对 `a<int>` 的显式特化是否也特化 `b`？标准选择直接禁止。

¶5 后半：如果模板声明的 *declaration* 是 *friend-type-declaration*，则它必须是单个 `friend friend-type-specifier ;` 形式——不能是 C++26 新增的"友元类型包展开"：

```cpp title="friend-pack.cpp" error
template<class...> struct C { struct Nested {}; };

template<class... Us>
struct S {
    template<class... Ts>
    friend class C<Ts>::Nested...;   // error: 模板声明里的 friend 不能是包展开
    friend class C<Us>::Nested...;   // OK（C++26）: 不是模板声明，展开的是外层包 Us
};
```

{{c++26}} `friend class C<Us>::Nested...;` 这种"多个友元一次声明"的语法是 C++26 新增的（*friend-type-specifier-list*）；在 C++23 中友元声明只能有一个类型。

## 特化彼此不同；默认实参是"定义"（¶6）

¶6 一个模板的特化（显式或隐式）与**任何其他模板**的特化都不相同。即使两个模板产生的类型"长得一模一样"：

```cpp run title="distinct.cpp" ok
#include <type_traits>
template<class T> struct A { T x; };
template<class T> struct B { T x; };
static_assert(!std::is_same_v<A<int>, B<int>>);   // 不同模板 ⇒ 不同类型

template<class T> using AA = A<T>;                 // 别名模板不产生新模板实体的特化
static_assert(std::is_same_v<AA<int>, A<int>>);    // 别名模板的特化等价于被替换后的类型（[temp.alias]）
int main() {}
```

注 4：函数模板与类模板成员函数的**默认实参**在模板实例化的意义上被视为定义（[[temp.decls]]），因此必须遵守 ODR——不同 TU 中同一函数模板的默认实参记号序列必须一致。

## 模板的名字与同作用域的其他名字（¶7）

¶7 是一个较长的注：模板不能与同一作用域中绑定的任何其他名字同名（[[basic.scope.scope]]），**例外**是函数模板可以与 *using-declarator*、类型、非模板函数、其他函数模板共享名字——这就是函数模板能参与重载的基础。

特化（包括部分特化）**不会**重新引入或绑定名字；它们的目标作用域就是主模板的目标作用域。

```cpp title="names.cpp" error
void f() {}
class f {};                                     // OK: 函数与类同名（类被隐藏）
template<typename> void f(long) {}              // #1 OK: 函数模板与函数同名
template<typename> void f(long) {}              // error: 重定义 #1
template<typename> void f(long long) {}         // OK: 另一个重载
template<>         void f<int>(long long) {}    // OK: 显式特化不绑定名字
template<typename> struct f2 {};
int f2;                                         // error: 类模板不能与变量同名
```

## templated entity（¶8）

¶8 是本节最重要的定义。一个实体是 **templated**（[[g:templated-entity]]），当且仅当它是：

| 列表项 | 情形 | 例子 |
|---|---|---|
| ¶8.1 | 模板本身 | `template<class T> void f(T);` |
| ¶8.2 {{c++26}} | 在**展开语句**（[[stmt.expand]]）的 *for-range-declaration* 或复合语句中定义或创建的实体 | `template for (auto x : tup) { struct L {}; }` 中的 `L` |
| ¶8.3 | 在 templated entity 中定义或创建的实体 | 函数模板中的局部类、局部变量、临时对象 |
| ¶8.4 | templated entity 的成员 | 类模板的成员函数（它们**不是**模板，但 templated） |
| ¶8.5 | 枚举是 templated entity 时，它的枚举器 | 类模板的成员枚举的枚举器 |
| ¶8.6 | 出现在 templated entity 声明中的 lambda 的闭包类型 | 函数模板体内 `[]{}` 的闭包类型 |

由此派生：**templated function** = 函数模板或 templated 的函数；**templated class**、**templated variable** 同理。注 6 举例：templated entity 中定义的局部类、局部变量、友元函数都是 templated。

```cpp run title="templated.cpp" ok
template<class T>
struct A {
    void f();            // A<T>::f 不是模板，但它是 templated function（¶8.4）
    enum E { e1 };       // E 是 templated，e1 也是（¶8.5）
    friend void g(A) {}  // 在 templated class 中定义的友元函数：templated（注 6）
};

template<class T>
void h() {
    struct Local { T t; };       // templated class（¶8.3）
    auto lam = [] {};            // 闭包类型是 templated（¶8.6）
    (void)lam; Local l{}; (void)l;
}

int main() { h<int>(); }
```

### 为什么需要"templated"这个概念？

因为许多规则需要一个比"模板"更宽的适用范围：

- **尾随 *requires-clause***：[[dcl.decl]] 规定只有声明 templated function 的声明符才能有 *requires-clause*。所以类模板的普通成员函数也能被约束：

    ```cpp title="member-requires.cpp" error
    template<class T>
    struct S {
        void f() requires (sizeof(T) > 1);   // OK: S<T>::f 是 templated function
    };
    S<char> s;                               // OK: 只是 s.f() 不可用
    void g() requires true;                  // error: 非 templated 函数不能有 requires-clause
    ```

- **弃置语句不被实例化**：`if constexpr` 的弃置分支只在"templated entity 内部"才不被实例化（[[stmt.if]]）；在普通函数里，弃置分支照样要求完全良构。
- **"不可能有有效特化"的 IFNDR**（[[temp.res]]）对所有 templated entity 都适用。
- **待决性**：只有在 templated entity 中，名字和表达式才可能是待决的。

¶8.2 是 C++26 随展开语句加入的：`template for` 的循环体会被"重复实例化"，所以其中定义的实体也必须被视为 templated，否则 `template for (auto x : tuple)` 体内 `x` 的类型无法每次不同。

## requires-clause 的受限文法（¶9）

¶9 模板声明是"用其模板形参写成的"。可选的 *requires-clause* 用来对模板实参指定约束（[[temp.constr.decl]]）。*requires-clause* 引入的 *constraint-expression*，就是把 *constraint-logical-or-expression* 解释为 *constraint-expression* 的结果；它是一个**不求值操作数**（[[expr.context]]）。

关键在文法：*constraint-logical-or-expression* 只允许用 `&&` 和 `||` 连接 **primary-expression**。也就是说，除了 `&&`/`||`，每个操作数都必须是：字面量、`this`、*id-expression*（包括 concept-id、`std::is_integral_v<T>` 这样的变量模板）、带括号的表达式、lambda、折叠表达式、*requires-expression*……而**不能**是 `sizeof(T) > 1`、`!C<T>`、`N == 0` 这样的任意表达式。

```cpp title="requires-grammar.cpp" error
#include <type_traits>
template<class T> concept C = true;

template<class T> requires C<T> && std::is_integral_v<T> void f1();   // OK: 都是 primary-expression
template<class T> requires (sizeof(T) > 1) void f2();                 // OK: 括号表达式是 primary-expression
template<class T> requires requires (T t) { t + t; } void f3();       // OK: requires-expression 是 primary-expression
template<class T> requires sizeof(T) > 1 void f4();                   // error: 需要括号
template<class T> requires !C<T> void f5();                           // error: ! 不是 primary-expression，需写成 (!C<T>)
```

为什么要限制？因为 *requires-clause* 后面紧跟的是声明的其余部分，而 C++ 的声明说明符可以长得像表达式。标准的例 4：

```cpp error
template<int N> requires N == sizeof new unsigned short
int f();            // error: 需要括号
```

如果允许任意表达式，`sizeof new unsigned short int f()` 中的 `int` 到底属于 *new-type-id*（`unsigned short int`）还是属于函数 `f` 的返回类型？解析器无法决定。限制为 *primary-expression* 之后，任何复杂表达式都必须加括号，边界一目了然。尾随 *requires-clause*（写在函数声明符之后）使用的是同一套受限文法（[[dcl.decl]]）。

!!! tip "`requires requires`"
    `template<class T> requires requires (T t) { ++t; }` 中，第一个 `requires` 开始 *requires-clause*，第二个 `requires` 开始 *requires-expression*。这不是笔误，但通常意味着应该把这个 *requires-expression* 起个名字，定义成一个概念——具名概念才能参与包含关系比较（见 [[temp.constr.order]]）。

### 约束操作数不求值，但会实例化

"不求值操作数"意味着 *requires-clause* 里的表达式不会产生运行期求值，不会 odr-use 任何东西。但判定**满足**时，需要对原子约束做替换和常量求值（[[temp.constr.atomic#3]]），这可能导致模板被隐式实例化。两者不矛盾：常量求值发生在编译期，不是程序执行的一部分。

## 定义必须在实例化处可达（¶10）

¶10 函数模板、类模板的成员函数、变量模板、类模板的静态数据成员——它们的**定义**必须从每个隐式实例化它的**定义域**（definition domain，[[basic.def.odr]]）的末尾**可达**，除非对应的特化在某个 TU 中被**显式实例化**；违反时 {{ifndr}}。

这就是"模板为什么要写在头文件里"的标准依据：

```cpp title="a.h"
template<class T> T twice(T x);   // 只有声明
```

```cpp title="a.cpp"
#include "a.h"
template<class T> T twice(T x) { return x + x; }
template int twice<int>(int);     // 显式实例化定义：twice<int> 在本 TU 生成
```

```cpp title="main.cpp" ok
#include "a.h"
int main() {
    return twice(21) == 42 ? 0 : 1;   // OK: twice<int> 被显式实例化（在 a.cpp 中）
    // twice(1.0) 则 IFNDR：twice<double> 既不可达定义，又没有显式实例化
}
```

为什么是 IFNDR 而不是"必须诊断"？因为编译 `main.cpp` 时编译器看不到 `a.cpp`，无从知道 `twice<double>` 有没有在别处被显式实例化。实践中，违反这条规则的典型症状是**链接错误**（未定义的符号 `twice<double>`），但标准不保证一定是链接错误——如果碰巧有别的 TU 隐式实例化了同一特化，链接器可能悄悄选用它，程序"看起来能用"。

!!! note "模块与'定义域'"
    ¶10 用的是"定义域的末尾可达"，而不是"同一个 TU 中可见"。在模块中，定义可以来自被导入的模块接口单元——只要可达（[[module.reach]]），隐式实例化就能找到它。这是模块化后"模板定义仍需放在接口里"的原因：放在实现单元里就不可达。

## 实现视角

!!! impl "实现视角"
    - **实例化的去重**：主流实现（Itanium ABI 下的 GCC/Clang、以及 MSVC）把隐式实例化的函数模板特化、静态数据成员等作为**COMDAT / 弱符号**放进每个用到它们的目标文件，由链接器合并。这就是 ¶10 的 IFNDR 在实践中常常"不出事"或"以链接错误出事"的原因。
    - **显式实例化声明**（`extern template`，[[temp.explicit]]）告诉编译器"别在这里实例化，别处有"，用于减少编译时间和目标文件体积。
    - **名字修饰**：模板特化的修饰名编码了模板实参（Itanium ABI 中是 `I ... E` 包围的实参列表，例如 `_Z5twiceIiET_S0_` 对应 `twice<int>`）；带有约束的模板，其约束也会进入修饰名（Clang 对 `template<class T> requires std::integral<T> void c1(T)` 的 `c1<int>` 生成 `_Z2c1IiQsr3stdE8integralIT_EEvS0_`，其中 `Q...` 编码了 *requires-clause*），以区分只靠约束区分的重载。
    - **requires-clause 的诊断**：Clang 对 ¶9 违例会提示需要加括号，而不是给出晦涩的语法错误。

## 历史与演进

!!! history "历史与演进"
    - **C++98**：模板只有类模板与函数模板。`export template` 允许把模板定义放在 `.cpp` 中、由实现负责跨 TU 实例化——这正是 ¶10 所禁止的模式的"官方解法"。只有基于 EDG 前端的实现真正支持过它。
    - **C++11**：`export` 模板被**删除**（关键字保留）；新增别名模板（¶2.6）、变参模板、`>>` 的拆分（注 1）、显式实例化声明 `extern template`。
    - **C++14**：变量模板（¶3）。
    - **C++17**：推导指引（¶2.5）。
    - **C++20**：概念与 *requires-clause*（¶1、¶9）；`export` 关键字被模块重新启用，于是 ¶4 补上"模板声明的 *declaration* 不能是 *export-declaration*"。
    - **C++26**：展开语句使其中的实体成为 templated（¶8.2）；友元类型包展开（¶5 例 2）。

## 陷阱

!!! pitfall "常见误解"
    - **"类模板的成员函数是函数模板"**——不是。`A<T>::f` 是 templated function（¶8.4），不是函数模板：不能对它做模板实参推导，不能给它写 `template<>` 以外的特化。它之所以"按需实例化"，是因为 [[temp.inst]] 对 templated entity 的成员作了专门规定。
    - **"`requires sizeof(T) > 1` 少了括号只是风格问题"**——不，是语法错误（¶9）。`requires !C<T>` 同理。
    - **"把模板定义放 `.cpp` 只是链接错误"**——标准上是 IFNDR（¶10）。如果其他 TU 碰巧实例化了同一特化，程序可能"能用"，换个链接顺序或优化级别又不能用。
    - **"函数模板可以部分特化"**——不能（¶4）。需要类似效果时用重载 + 偏序，或者把逻辑转发给一个可以部分特化的类模板。

## 思考题

!!! question "思考题 1"
    下面哪些声明是良构的？

    ```cpp
    template<class T> struct A { enum class E; };
    template<class T> enum class A<T>::E { x };   // (a)
    template<class T> int v1 = 1, v2 = 2;         // (b)
    template<class T> auto lam = [](T t) { return t; };   // (c)
    ```

<details markdown="1">
<summary>答案</summary>

- (a) 良构：¶2.2 允许在类外定义类模板的成员枚举。
- (b) 非良构：¶5，模板声明至多一个声明符。
- (c) 良构：这是一个变量模板，初始化器是 lambda。每个特化 `lam<int>`、`lam<double>` 有各自的闭包类型（闭包类型是 templated entity，¶8.6）。
</details>

!!! question "思考题 2"
    为什么 `template<class T> requires (sizeof(T) > 1) void f();` 合法，而把同一约束写成尾随形式 `template<class T> void f() requires sizeof(T) > 1;` 不合法？

<details markdown="1">
<summary>答案</summary>

两个位置使用同一套受限文法 *constraint-logical-or-expression*：操作数只能是 *primary-expression*。`(sizeof(T) > 1)` 是带括号的表达式，属于 *primary-expression*；`sizeof(T) > 1` 不是。所以第二种写法同样需要括号——它不合法不是因为位置，而是因为少了括号。
</details>

!!! question "思考题 3"
    函数模板 `template<class T> void g(T) {}` 的定义只出现在 `x.cpp` 中，`x.cpp` 里有 `g(1);`；`y.cpp` 里只有声明，也调用了 `g(1);`。这个程序良构吗？

<details markdown="1">
<summary>答案</summary>

严格说是 IFNDR（¶10）：`y.cpp` 隐式实例化了 `g<int>`，但它的定义从 `y.cpp` 的定义域末尾不可达，且 `g<int>` 没有在任何 TU 中**显式**实例化——`x.cpp` 中的只是**隐式**实例化。实践中通常能链接成功（`x.cpp` 生成了弱符号 `g<int>`），但这只是实现的偶然，而且在优化时 `x.cpp` 可能把 `g<int>` 内联后不再输出符号，于是出现链接错误。
</details>

## 小结

!!! summary "小结"
    | 规则 | 段落 | 违反后果 |
    |---|---|---|
    | 模板可以是类、函数、变量、别名、概念 | ¶1 | — |
    | 枚举、typedef、命名空间、linkage-specification 不能模板化 | ¶2 | ill-formed |
    | 模板声明只在命名空间/类作用域 | ¶4 | ill-formed |
    | 函数模板的声明符名不能是 template-id（无函数模板部分特化） | ¶4 | ill-formed |
    | 一个模板声明至多一个声明符 | ¶5 | ill-formed |
    | templated entity：模板、模板内定义的东西、成员、枚举器、闭包类型、展开语句内的实体 | ¶8 | — |
    | *requires-clause* 只接受 `&&`/`\|\|` 连接的 primary-expression | ¶9 | ill-formed |
    | 模板定义须在隐式实例化处可达，否则须显式实例化 | ¶10 | IFNDR |
