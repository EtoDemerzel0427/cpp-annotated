---
title: 模板特化的名字
summary: template-id 的文法；什么时候 < 被当作模板实参列表的开始（以及何时必须写 template 关键字）；>> 的拆分；template-id 何时"有效"、何时必须检查约束；concept-id 是 bool prvalue 而不是特化。
status: done
papers: N1757, P0846R0
related: temp.arg, temp.res, temp.dep.type, temp.constr.decl, basic.lookup, basic.lookup.qual, temp.variadic, basic.splice
tags: 模板, template-id, template 关键字, 解析, concept-id
updated: 2026-10-17
---

C++ 的文法有一个先天缺陷：`<` 既是小于号，又是模板实参列表的左括号；`>` 既是大于号，又是右括号。`a < b > c` 可以是"`(a < b) > c`"，也可以是"声明一个类型为 `a<b>` 的变量 `c`"。C 语言没有这个问题，C++ 引入模板时选择了尖括号，于是把**消歧**的负担交给了名字查找。

[temp.names] 就是这套消歧规则的法典。它回答：

1. *template-id* 的文法是什么（¶1–¶6）；
2. 一个 `<` 何时被解释为模板实参列表的开始（¶7）——这决定了你何时**必须**写 `template` 关键字；
3. 一个 `>` 或 `>>` 何时结束模板实参列表（¶8）；
4. 一个 *template-id* 何时**有效**，何时要检查约束（¶13–¶14）；
5. **concept-id** 是什么（¶15）。

## 文法（¶1–¶6）

¶1 模板特化通过 *template-id* 指称：

```text
simple-template-id:   template-name < template-argument-list(opt) >
template-id:          simple-template-id
                      operator-function-id < template-argument-list(opt) >     // operator+<int>
                      literal-operator-id  < template-argument-list(opt) >     // operator""_x<'a'>
template-name:        simple-template-name          // identifier
                      pack-index-template-name      // TTs...[0]   (C++26)
template-argument:    template-argument-name        // [nested-name-specifier] [template] identifier
                      constant-expression
                      type-id
                      braced-init-list              // X<{1, 2}>
```

几点说明：

- *template-argument-name* 是 {{c++26}} 引入的文法项：一个可能带限定的标识符作为模板实参时，先按名字解释，再由 [[temp.arg.general#3]] 根据查找结果决定它是模板、类型还是表达式。这是为了让概念、变量模板也能作为模板模板实参。
- *braced-init-list* 作模板实参：`C<{42}>`、`B<{1, 2}>`（初始化类类型的常量模板形参）。

¶2 *simple-template-id*、*template-id* 或 *template-name* 的**组成名字**（component name）是其中的第一个名字。

¶3–¶6 {{c++26}} **包索引模板名**（*pack-index-template-name*）：`P...[I]`，其中 `P` 必须指称一个包（¶3），`I` 是类型为 `std::size_t` 的转换常量表达式，取值 `0 ≤ I < sizeof...(P)`（¶4）；它本身是一个包展开（¶5），表示包中第 `I` 个 *template-name*（¶6 注）。

```cpp
template<template<class> class... TTs>
struct S {
    using first = TTs...[0]<int>;      // 第 0 个模板模板实参的特化
};
```

!!! impl "编译器现状"
    截至写作时，Clang 23 已支持类型与表达式的包索引（`Ts...[0]`、`vs...[0]`），但**尚不支持**上面的 *pack-index-template-name*，会报语法错误。

## `<` 何时开始模板实参列表（¶7）

¶7 是本节的核心。一个 `<` 被解释为 *template-argument-list* 的分隔符，当且仅当：

- ¶7.1 {{c++26}} 它跟在一个 *splice-specifier* 之后，而该 *splice-specifier* 处于仅类型语境，或前面有 `template`/`typename`；
- ¶7.2 {{c++26}} 它跟在一个 *pack-index-template-name* 之后；
- ¶7.3 它跟在一个名字（不是 *conversion-function-id*）之后，并且满足下列之一：
    - ¶7.3.1 该名字跟在 `template` 关键字或 `~` 之后，而这个 `template`/`~` 位于 *nested-name-specifier* 之后或类成员访问表达式中；
    - ¶7.3.2 对该名字的**名字查找**找到了类模板的注入类名，或找到了**任何模板的声明**；
    - ¶7.3.3 该名字是一个**非限定名**，名字查找找到一个或多个**函数**，或者**什么都没找到**；
    - ¶7.3.4 该名字是 *using-declarator* 中、*declarator-id* 中、或（*nested-name-specifier* 以外的）仅类型语境中的**终端名字**。

注 2：如果该名字是 *identifier*，它随后被解释为 *template-name*。`template` 关键字用于表明一个**待决的限定名**在可能出现表达式的地方指称模板。

### 规则背后的逻辑

¶7.3.2 是"正常情况"：查找找到模板，`<` 就是模板实参列表。问题出在**查找不到**的时候——在模板定义中，`p->alloc` 或 `T::adjust` 的查找要推迟到实例化（[[temp.dep]]），定义处无法知道 `alloc` 是否是模板，而解析器此刻就必须决定怎么切分记号。标准的选择是：**默认当作小于号**，需要模板时由程序员写 `template` 显式说明（¶7.3.1）。

```cpp title="template-keyword.cpp" error
#include <cstddef>
struct X {
    template<std::size_t> X* alloc();
    template<std::size_t> static X* adjust();
};

template<class T> void f(T* p) {
    T* p1 = p->alloc<200>();              // error: < 被解释为小于号
    T* p2 = p->template alloc<200>();     // OK: < 开始模板实参列表
    T::adjust<100>();                     // error: < 被解释为小于号
    T::template adjust<100>();            // OK
}
```

为什么 `p->alloc<200>()` 是错误而不仅仅是"语义不同"？因为按小于号解析，`p->alloc < 200 > ()` 中的 `()` 是一个空括号表达式，语法错误。在别的情况下，按小于号解析可能**恰好合法**，于是程序悄悄有了另一种含义——这比报错更危险。

!!! note "什么时候不需要 `template`"
    只有当名字是**待决的**（依赖模板形参、查找推迟）时才需要 `template`。如果对象表达式的类型不是待决的，查找立即进行，¶7.3.2 直接生效：

    ```cpp
    template<class T> int h(T t) {
        S s;
        return s.g<1>() + t.template g<1>();   // s 非待决：不需要 template；t 待决：需要
    }
    ```

### ¶7.3.3：ADL 与不可见的函数模板 {{c++20}}

¶7.3.3 是 C++20 加入的（[[P0846R0]]）。在此之前，下面的代码是非良构的：

```cpp run title="adl-template.cpp" ok
namespace N {
    struct A {};
    template<class T> int f(A) { return 1; }
}

int g() {
    return f<int>(N::A{});   // C++20 起 OK: 非限定名 f 查找什么都没找到 ⇒ < 是模板实参列表；
                             //             然后 ADL 在 N 中找到函数模板 f
}
int main() { return g() - 1; }
```

C++17 中，普通的非限定查找找不到 `f`，于是 `f < int > (N::A{})` 被解析为比较表达式——`int` 不是表达式，语法错误。这让"显式指定模板实参 + ADL"无法组合使用（典型受害者是 `get<0>(tuple)` 这种在没有 `using std::get` 时的调用）。C++20 的规则：只要非限定查找找到函数或什么都没找到，就假定 `<` 是模板实参列表，之后再由 ADL 找到真正的函数模板。

"找到函数"也被纳入，是因为：如果查找找到的是一个非模板函数 `f`，`f < x` 把函数和别的东西比较本来就几乎总是无意义的。

!!! lawyer "¶7.3.3 的代价"
    这条规则在极少数情况下改变了既有代码的含义：如果作用域中有一个名为 `f` 的**函数**，C++17 中 `f < 0 > (x)` 是比较表达式（函数指针比较），C++20 中变成模板实参列表然后通常报错。实践中这种代码几乎不存在。

### ¶7.3.4：声明语境

¶7.3.4 处理的是**声明**中的名字：*using-declarator*、*declarator-id*（被声明的名字）、仅类型语境中的终端名字。这些地方名字一定是类型或被声明的实体，不可能是比较表达式的左操作数，所以直接当作模板名。例如显式特化 `template<> void f<int>(int);` 中 `f<int>` 的 `<`。

## `>` 与 `>>`（¶8）

¶8 解析 *template-argument-list* 时，**第一个非嵌套的 `>`** 被当作结束分隔符，而不是大于号。同理，**第一个非嵌套的 `>>`** 被当作两个连续但独立的 `>`：第一个结束当前列表，第二个可以结束外层列表或成为别的构造的一部分。

"嵌套"由脚注定义：`dynamic_cast` 等四种转型中包围 *type-id* 的 `>`、以及后续 *template-id* 中包围其实参的 `>`，都被视为嵌套。圆括号里的 `>` 自然也不参与。

```cpp title="right-angle.cpp" error
template<int i> class X {};
template<class T> class Y {};

X< 1>2 > x1;              // error: 第一个 > 结束了列表，剩下 2 > x1 无法解析
X<(1>2)> x2;              // OK

Y<X<1>> x3;               // OK（C++11 起）: 等同于 Y<X<1> > x3;
Y<X<6>>1>> x4;            // error: >> 被拆分，结束 X 的列表
Y<X<(6>>1)>> x5;          // OK
```

C++03 中 `Y<X<1>>` 是语法错误（`>>` 是右移记号），必须写成 `Y<X<1> >`。C++11 通过 [[N1757]] 引入了 `>>` 拆分规则。代价是少数 C++03 代码含义改变：例如 `X< 1>>2 >` 在 C++03 中是 `X<(1>>2)>`，C++11 中变成语法错误。

!!! tip "经验法则"
    模板实参中出现 `>`、`>>`、`>=`、`>>=` 运算符时，一律加括号。

## `template` 关键字的限制（¶9–¶12）

¶9 `template` 关键字**不能**紧跟在**声明性的** *nested-name-specifier*（[[expr.prim.id.qual]]）之后——即被声明实体的限定名中不能出现 `template`：

```cpp title="declarative-template.cpp" error
struct S { template<class T> void f(); };
template<> void S::template f<int>() {}   // error: 声明性 nested-name-specifier 之后不能写 template
```

!!! impl "编译器现状"
    Clang 23 对上例只给出**警告**（`-Wtemplate-in-declaration-name`），而非错误。按 [[intro.compliance]]，警告也算诊断消息，所以这是合规的；但代码依然是非良构的。

¶10 {{c++26}} *template-argument* 的 *constant-expression* 不能是**不带括号的** *splice-expression*：`S<[:r:]>` 非法，`S<([:r:])>` 合法。原因是 `[:r:]` 在模板实参位置可能拼接出类型、模板或值，加括号强制它被解释为表达式。

¶11 前缀 `template` 的名字必须**后跟模板实参列表**，或者指称类模板/别名模板——后一种情况**已弃用**（[[depr.template.template]]）。`template` 不能紧挨在 `~` 之前（用来命名析构函数）。

```cpp title="template-prefix.cpp" error
template<class T> struct A {
    void f(int);
    template<class U> void f(U);
};

template<class T> void g(T t) {
    A<T> a;
    a.template f<>(t);       // OK: 调用模板
    a.template f(t);         // error: template 之后不是 template-id
}

template<class T> struct B { template<class T2> struct C {}; };
template<class T, template<class> class TT = T::template C>   // 已弃用：没有实参列表
struct D {};
D<B<int>> db;

template<class T> void k(T* p) { p->template ~T(); }   // error: template 不能出现在 ~ 之前
```

注 4：`template` 不能用于类模板的**非模板**成员。注 5：与 `typename` 前缀一样，即使名字查找本来就会找到模板，`template` 前缀也是良构的——可以"多写"，不能"少写"。

¶12 *template-argument-name* 的组成名字是其 *nested-name-specifier* 中的名字和其 *identifier*。

## template-id 的有效性（¶13）

¶13 一个 *template-id*（或 *splice-specialization-specifier*）是**有效的**（[[g:valid-template-id]]），当且仅当：

- ¶13.1 实参不多于形参，或某个形参是形参包；
- ¶13.2 每个**不可推导的非包形参**，若没有默认实参，都有对应实参；
- ¶13.3 每个实参都**匹配**对应的形参（[[temp.arg]]）；
- ¶13.4 将每个模板实参**替换进后续的模板形参**（若有）都成功；
- ¶13.5 若 *template-id* 是**非待决**的，其关联约束被满足（见 ¶14）。

*simple-template-id* 必须有效——**除非**它的 *template-name* 指称函数模板。函数模板的 *template-id* 可以"无效"，因为它会在模板实参推导中补全实参（¶13.2 中"不可推导"的限定也是为此），无效的情况由推导失败（SFINAE，[[temp.deduct]]）处理。

```cpp title="validity.cpp" error
template<class T, T::type n = 0> class X;
struct S { using type = int; };

using T1 = X<S, int, int>;   // error: 实参过多（¶13.1）
using T2 = X<>;              // error: 第一个形参没有默认实参（¶13.2）
using T3 = X<1>;             // error: 1 不匹配类型形参（¶13.3）
using T4 = X<int>;           // error: 替换进第二个形参失败，int::type 无效（¶13.4）
using T5 = X<S>;             // OK
```

¶13.4 值得注意：后续形参的类型可以依赖前面的形参（`T::type n`），替换失败使 *template-id* 无效。这是类模板版本的"SFINAE 前置检查"——但对类模板而言，无效就是**硬错误**。

## 约束检查（¶14）

¶14 当 *simple-template-id* 的 *template-name* 指称一个**受约束的非函数模板**（类模板、变量模板、别名模板）或**受约束的模板模板形参**，且所有模板实参都**非待决**（[[temp.dep.temp]]）时，该模板的关联约束必须被满足。

```cpp title="constraint-check.cpp" error
template<typename T> concept C1 = sizeof(T) != sizeof(int);

template<C1 T> struct S1 {};
template<C1 T> using Ptr = T*;

S1<int>* p;                    // error: 约束不满足——即使只是形成指针类型，不需要实例化 S1<int>
Ptr<int> q;                    // error: 约束不满足

template<typename T>
struct S3 { Ptr<T> x; };       // OK: 实参待决，此时不检查
S3<int> x;                     // error: 实例化 S3<int> 时检查 Ptr<int>
```

这条规则的要点：

1. **只是命名就要检查**。`S1<int>*` 不需要 `S1<int>` 完整，但仍然要求约束满足。这让约束成为类型系统的一部分："`S1<int>` 这个类型根本不存在"，而不是"`S1<int>` 存在但不能实例化"。
2. **待决时推迟**。模板定义中 `Ptr<T>` 不检查，实例化时才检查。
3. **非待决但在模板中**：如果模板定义中出现了约束不满足的非待决 `Ptr<int>`，则该模板没有任何有效特化——按 [[temp.res]] 是 IFNDR（标准例 6 中的 `S2`）。对模板模板形参 `X<int>`（`X` 是受约束的模板模板形参）同理。
4. **显式实例化与显式特化也要检查**：`template struct S<char[2]>;` 和 `template<> struct S<char[2]> {};` 在约束不满足时都是错误——不能用显式特化"绕过"约束。

```cpp title="explicit-spec-constraint.cpp" error
template<typename T> concept C2 = sizeof(T) == 1;
template<C2 T> struct S {};

template struct S<char[2]>;         // error: 约束不满足
template<> struct S<char[2]> {};    // error: 约束不满足
```

函数模板不在 ¶14 之列：函数模板的约束在**重载决议**中检查（[[over.match.viable]]），不满足只是让候选不可行，而不是错误。

## concept-id（¶15）

¶15 **concept-id** 是 *template-name* 为 *concept-name* 的 *simple-template-id*（[[g:concept-id]]）。它：

- 是 `bool` 类型的 **prvalue**；
- **不**指称模板特化（概念不会被实例化，[[temp.concept#5]]）；
- 当概念的**规范化后的约束表达式**被给定模板实参**满足**时求值为 `true`，否则为 `false`。

```cpp title="concept-id.cpp" error
template<typename T> concept C = sizeof(T) > 1;

static_assert(C<int>);              // OK
static_assert(!C<char>);            // OK: 不满足就是 false，不是错误
constexpr bool b = C<int> && C<long>;
auto p = &C<int>;                   // error: concept-id 是 prvalue，不能取地址
```

注 6：由于约束表达式是不求值操作数，出现在约束表达式中的 concept-id 并不会被"求值"，只在判定规范化约束是否满足所必需的范围内被检查——也就是说 `C<T> && D<T>` 作为约束时，是按 [[temp.constr.op]] 的合取规则检查的，而不是先求出两个 `bool` 再做 `&&`。

!!! lawyer "concept-id 在约束内外的区别"
    - 在 *requires-clause* 或概念定义中，`C<T>` 会被**规范化**——展开成 `C` 的原子约束，参与包含关系比较（[[temp.constr.normal]]）。
    - 在普通表达式中（`static_assert(C<int>)`、`if constexpr (C<T>)`），`C<int>` 就是一个 `bool` 值。
    - 把 concept-id 包进别的表达式（如 `(C<T> == true)`、`!C<T>`、`bool(C<T>)`）会让它变成一个**原子约束**的一部分，从而失去参与包含关系的能力。见 [[temp.constr.atomic]]。

## 实现视角

!!! impl "实现视角"
    - **解析与查找交织**：C++ 解析器不能是"纯"语法分析器。Clang 的 `Parser` 在遇到 `identifier <` 时会调用 `Sema` 做名字查找来决定 ¶7 的分支，这也是 C++ 解析难以并行化、难以写独立语法工具的根源之一。
    - **缺少 `template` 的诊断**：Clang 对 `p->alloc<200>()` 会直接提示 "missing 'template' keyword prior to dependent template name"，因为它能看出来按小于号解析不通。
    - **`>>` 拆分**：实现上是在解析模板实参列表时，遇到 `>>`/`>=`/`>>=` 记号就把它拆开，把剩余部分"放回"记号流。

## 历史与演进

!!! history "历史与演进"
    - **C++98**：确立 `template` 关键字消歧规则；`>>` 是右移记号，嵌套模板必须写 `> >`。
    - **C++11**：`>>` 拆分（[[N1757]]）。`template` 关键字允许在模板之外使用（多写不出错）。
    - **C++20**：¶7.3.3，非限定名查找找到函数或什么都没找到时视为模板名（[[P0846R0]]）；concept-id；¶14 约束检查。
    - **C++20 以后**：[[P0634R3]]（"Down with typename"）使若干语境中的待决限定名默认为类型；之后的修订把这些语境整理为"仅类型语境"（[[temp.res.general#4]]），本节 ¶7.3.4 引用了它。
    - **C++26**：*pack-index-template-name*；*splice-specifier* 后的 `<`（¶7.1、¶10）；`template` 后不跟实参列表指称类模板的写法被弃用（¶11）；*template-argument-name*。

## 陷阱

!!! pitfall "常见误解"
    - **"写不写 `template` 无所谓，编译器会猜"**——不会。待决名后面的 `<` 默认是小于号（¶7）。
    - **"`template` 只能在模板里用"**——C++11 起模板外也可以写，只是多余（注 5）。
    - **"`S<int>*` 只是指针，不需要满足约束"**——需要（¶14）。
    - **"显式特化可以为不满足约束的实参提供定义"**——不行（¶14 例 6 末尾）。
    - **"concept-id 是一种特化"**——不是，它是 `bool` prvalue（¶15）。

## 思考题

!!! question "思考题 1"
    在模板定义 `template<class T> void f(T t) { t.get<0>(); }` 中，如果全局作用域里**恰好**有一个函数模板 `template<int> void get();`，`<` 会被怎样解析？

<details markdown="1">
<summary>答案</summary>

按现行草案，`<` 被解析为**小于号**，`t.get<0>()` 非良构，必须写 `t.template get<0>()`。

`t.get` 中的 `get` 是**成员限定名**（member-qualified name，[[basic.lookup.qual.general#2]]），其查找语境是对象表达式 `t` 的类型——待决的，所以查找推迟（[[basic.lookup.qual.general#3]]）。现行规则只对 *nested-name-specifier* 的终端名在成员查找无果时补做非限定查找，`get` 不属于此列，所以全局的 `get` 模板**不会**被找到，¶7.3.2 不适用；`get` 也不是非限定名，¶7.3.3 不适用。Clang 23 报告 "missing 'template' keyword prior to dependent template name"。

较早的标准版本曾规定在"整个后缀表达式的语境"中再查一次，各编译器在此处的行为也不一致；现行规则消除了这种"取决于全局作用域里碰巧有什么"的脆弱性。
</details>

!!! question "思考题 2"
    `Y<X<1>>2>> y;`（`X` 是 `template<int>`，`Y` 是 `template<class>`）能编译吗？如何改？

<details markdown="1">
<summary>答案</summary>

不能。`X<1>>2` 中第一个非嵌套的 `>>` 被拆为两个 `>`：第一个结束 `X<1>`，第二个结束 `Y<X<1>>`，剩下 `2>> y;` 无法解析。改为 `Y<X<(1>>2)>> y;`。
</details>

!!! question "思考题 3"
    下面哪一行需要满足约束？

    ```cpp
    template<std::integral T> struct S {};
    template<class T> void f(S<T>*);       // (a)
    void g(S<double>*);                    // (b)
    ```

<details markdown="1">
<summary>答案</summary>

(a) 中 `S<T>` 实参待决，¶14 不要求此时满足。(b) 中 `S<double>` 实参非待决，必须满足约束——`std::integral<double>` 为假，所以 (b) 非良构，即使 `g` 从未被调用、`S<double>` 从未被实例化。
</details>

## 小结

!!! summary "小结"
    | 规则 | 段落 | 要点 |
    |---|---|---|
    | `<` 是模板实参列表 | ¶7 | 查找找到模板；或非限定名找到函数/什么都没找到（C++20）；或前有 `template`；或在声明语境 |
    | 待决名 | ¶7.3.1 | 待决的限定名/成员名后接 `<` 需要 `template` |
    | `>` / `>>` | ¶8 | 第一个非嵌套的 `>` 结束列表；`>>` 拆为两个 `>`；运算符需加括号 |
    | `template` 的限制 | ¶9、¶11 | 不能在声明性限定名中、不能在 `~` 前；须后接实参列表（否则弃用） |
    | 有效性 | ¶13 | 实参个数、匹配、后续形参替换、非待决时约束满足 |
    | 约束检查 | ¶14 | 非函数模板：命名即检查；待决时推迟；显式特化也不能绕过 |
    | concept-id | ¶15 | `bool` prvalue，不是特化 |
