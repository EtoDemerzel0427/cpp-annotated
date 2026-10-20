---
title: 模板特化的名字
summary: 编译器怎样判断 < 是小于号还是模板实参列表的开始，什么时候必须写 template 关键字，>> 怎样拆开；一个 template-id 什么时候有效，什么时候要检查约束；concept-id 为什么是 bool 值。
status: done
papers: N1757, P0846R0, P0634R3, P3670R4
related: temp.arg, temp.res, temp.dep.type, temp.constr.decl, basic.lookup, basic.lookup.qual, temp.variadic, basic.splice
tags: 模板, template-id, template 关键字, 解析, concept-id
updated: 2026-10-19
---

!!! tldr
    - 名字后面的 `<` 只有在编译器知道这个名字是模板时才开始模板实参列表，否则就是小于号。
    - 在模板里，`p->alloc<200>()`、`T::adjust<100>()` 这类依赖模板形参的名字查不到，必须写成 `p->template alloc<200>()`。
    - C++20 起，非限定名查找什么都没找到或只找到函数时，`<` 也算模板实参列表，所以 `get<0>(t)` 可以靠 ADL 找到函数模板。
    - 模板实参列表里第一个不在括号内的 `>` 结束列表，`>>` 会拆成两个 `>`。在尖括号里用 `>` 运算符要加括号。
    - 类模板、别名模板的约束只要写出名字就要检查，`S<int>*` 也不例外；concept-id 如 `C<int>` 是一个 `bool` 值，不是特化。

模板的一个**特化**（specialization）用模板名加尖括号里的实参来指称，如 `std::vector<int>`、`f<double>`、`operator+<int>`。这种写法叫做 **template-id**。

## `<` 是小于号还是尖括号（¶7）

```cpp title="template-keyword.cpp" error
#include <cstddef>
struct X {
    template<std::size_t> X* alloc();
    template<std::size_t> static X* adjust();
};

template<class T> void f(T* p) {
    T* p1 = p->alloc<200>();            // error: < 是小于号
    T* p2 = p->template alloc<200>();   // OK
    T::adjust<100>();                   // error: < 是小于号
    T::template adjust<100>();          // OK
}
```

C++ 用尖括号写模板实参，而 `<` 和 `>` 同时也是比较运算符。`a < b > c` 可以是 `(a < b) > c`，也可以是声明一个类型为 `a<b>` 的变量 `c`。解析器读到 `<` 时必须马上决定是哪一种，标准的回答是：看前面的名字是不是模板。

在模板 `f` 的定义里，`p` 的类型 `T*` 依赖模板形参，`p->alloc` 要等到实例化时才知道指的是什么（[[temp.dep]]）。解析器在定义处看不到 `alloc` 是模板，就把 `<` 当作小于号。需要模板时，由程序员在名字前写 `template` 说明。

`p->alloc<200>()` 报错，是因为按小于号解析，`p->alloc < 200 > ()` 中的 `()` 是一对空括号，不是合法的表达式。在别的情况下，按小于号解析可能恰好合法，程序就悄悄有了另一种含义。本机 Clang 23 对上面两处错误都提示 "missing 'template' keyword prior to dependent template name"。

### 完整的规则

¶7 满足下面任一条件时，`<` 开始模板实参列表：

- ¶7.1 {{c++26}} 它跟在一个反射拼接 `[:r:]`（*splice-specifier*）之后，并且这个拼接处在只能出现类型的语境中，或者前面写了 `template` 或 `typename`；
- ¶7.2 {{c++29}} 它跟在包索引模板名 `TTs...[I]` 之后（见文末）；
- ¶7.3 它跟在一个名字之后（转换函数名除外），并且：
    - ¶7.3.1 这个名字前面有 `template` 或 `~`，而它们出现在限定名的 `::` 之后或成员访问 `.`、`->` 之后；
    - ¶7.3.2 名字查找找到了一个模板，或者类模板的注入类名（类模板内部用来指称自身的名字）；
    - ¶7.3.3 这是一个非限定名，查找只找到函数，或者什么都没找到；
    - ¶7.3.4 这个名字是 using 声明、声明符中被声明的名字，或者只能出现类型的语境中的最后一个名字。

¶7.3.2 是通常的情况。¶7.3.1 就是上面的 `template` 关键字。¶7.3.4 处理声明里的名字：例如显式特化 `template<> void f<int>(int);` 中的 `f`，被声明的名字不可能是比较表达式的左操作数，所以直接当模板名。

只有查找被推迟的名字才需要 `template`。如果成员访问的对象类型不依赖模板形参，查找马上进行，¶7.3.2 直接适用：

```cpp run title="nondependent.cpp" ok
struct S { template<int> int g() { return 0; } };

template<class T> int h(T t) {
    S s;
    return s.g<1>()                // s 不依赖 T：不需要 template
         + t.template g<1>();      // t 依赖 T：需要
}
int main() { return h(S{}); }
```

### 查找什么都没找到时（¶7.3.3）{{c++20}}

```cpp run title="adl-template.cpp" ok
namespace N {
    struct A {};
    template<class T> int f(A) { return 1; }
}

int g() {
    return f<int>(N::A{});   // 普通查找找不到 f，ADL 在 N 里找到
}
int main() { return g() - 1; }
```

在 C++17 中，普通的非限定查找找不到 `f`，于是 `f < int > (N::A{})` 被解析成比较表达式，`int` 不是表达式，程序非良构。这样一来，显式模板实参和实参依赖查找（ADL，按实参类型所在的命名空间查找函数）就不能一起用。典型的例子是没有 `using std::get` 时写 `get<0>(t)`。

C++20 的 [[P0846R0]] 加入了 ¶7.3.3：非限定名查找什么都没找到，或者只找到函数时，也把 `<` 当作模板实参列表的开始，之后再由 ADL 找到真正的函数模板。只找到函数的情形也包括进来，是因为拿一个函数和别的东西比大小几乎总是没有意义的。本机 Clang 23 在 `-std=c++17` 下也接受上面的代码，只给出一条 `-Wc++20-extensions` 警告。

这条规则在极少数情况下改变了旧代码的含义：作用域里有一个名为 `f` 的普通函数时，C++17 中的 `f < 0 > (x)` 是比较表达式，C++20 中变成了模板实参列表，通常会报错。

## `>` 与 `>>`（¶8）

```cpp title="right-angle.cpp" error
template<int i> class X {};
template<class T> class Y {};

X< 1>2 > x1;        // error: 第一个 > 结束了列表
X<(1>2)> x2;        // OK

Y<X<1>> x3;         // OK：等同于 Y<X<1> > x3;
Y<X<6>>1>> x4;      // error: >> 被拆开，结束了 X 的列表
Y<X<(6>>1)>> x5;    // OK
```

¶8 解析模板实参列表时，第一个不嵌套的 `>` 是列表的结束，而不是大于号。第一个不嵌套的 `>>` 被当作两个独立的 `>`：前一个结束当前列表，后一个可以结束外层列表，也可以属于别的构造。

括号里的 `>` 是嵌套的。按脚注，`static_cast<T>` 等四种转型中的 `>`，以及列表中另一个 template-id 的 `>`，也算嵌套的。

C++03 中 `>>` 总是右移运算符，`Y<X<1>>` 是语法错误，必须写成 `Y<X<1> >`。C++11 的 [[N1757]] 引入了拆分规则。代价是少数 C++03 代码的含义变了：`X< 1>>2 >` 在 C++03 中是 `X<(1>>2)>`，在 C++11 中是语法错误。

所以在模板实参里出现 `>`、`>>`、`>=`、`>>=` 运算符时，一律加括号。

## `template` 关键字的其他规则（¶9、¶11）

<div class="compare" markdown="1">

```cpp ok
template<class T> struct A {
  void f(int);
  template<class U> void f(U);
};
template<class T> void g(T t) {
  A<T> a;
  a.template f<>(t);  // 调用模板
}
```

```cpp error
template<class T> struct A {
  void f(int);
  template<class U> void f(U);
};
template<class T> void g(T t) {
  A<T> a;
  a.template f(t);  // error
}
```

</div>

¶11 写了 `template` 的名字后面必须跟模板实参列表，哪怕是空的 `<>`。另一种情况是名字指称类模板或别名模板、后面不带实参列表，如模板模板实参 `T::template C`，这种写法已弃用（[[depr.template.template]]）。`template` 也不能直接写在 `~` 前面去命名析构函数，`p->template ~T()` 是错误的。

注 5：与 `typename` 一样，即使查找本来就能找到模板，加上 `template` 也是良构的。这个关键字多写无妨，少写不行；C++11 起在模板外面也可以写。注 4：类模板的非模板成员前面不能加 `template`。

¶9 被声明的实体的限定名里不能出现 `template`：

```cpp title="declarative-template.cpp" error
struct S { template<class T> void f(); };
template<> void S::template f<int>() {}   // error: 违反 ¶9
```

本机 Clang 23 对此只给出警告（`-Wtemplate-in-declaration-name`）。警告也是一条诊断，这符合标准（[[intro.compliance]]），但代码仍然是非良构的。

## template-id 何时有效（¶13）

```cpp title="validity.cpp" error
template<class T, T::type n = 0> class X;
struct S { using type = int; };

using T1 = X<S, int, int>;   // error: 实参过多
using T2 = X<>;              // error: T 没有默认实参
using T3 = X<1>;             // error: 1 不能对应类型形参
using T4 = X<int>;           // error: int::type 无效
using T5 = X<S>;             // OK
```

¶13 一个 template-id 是**有效的**（[[g:valid-template-id]]），需要满足：

- ¶13.1 实参不多于形参，或者有一个形参是形参包；
- ¶13.2 每个没有默认实参、不是包、也不能推导的形参都有实参；
- ¶13.3 每个实参都和对应的形参匹配（[[temp.arg]]）；
- ¶13.4 把实参替换进后面的形参都能成功，如上例中 `T::type`；
- ¶13.5 如果 template-id 不依赖模板形参，模板的约束得到满足（见下一节）。

指称类模板、别名模板、变量模板的 template-id 必须有效，否则程序非良构。指称函数模板的 template-id 可以暂时不完整，剩下的实参由模板实参推导补上；推导或替换失败只是让这个候选被丢掉（SFINAE，[[temp.deduct]]），不是错误。¶13.2 说不能推导的形参，也是因为这个。

## 约束在写出名字时就要检查（¶14）

```cpp title="constraint-check.cpp" error
template<typename T> concept C1 = sizeof(T) != sizeof(int);

template<C1 T> struct S1 {};
template<C1 T> using Ptr = T*;

S1<int>* p;               // error: 约束不满足
Ptr<int> q;               // error: 约束不满足

template<typename T>
struct S3 { Ptr<T> x; };  // OK：实参依赖 T，现在不检查
S3<int> x;                // error: 实例化时检查 Ptr<int>
```

¶14 一个 template-id 指称带约束的类模板、别名模板、变量模板，或者带约束的模板模板形参，并且所有实参都不依赖模板形参（[[temp.dep.temp]]）时，模板的约束必须满足。

`S1<int>*` 只是一个指针类型，不需要 `S1<int>` 是完整类型，也不会实例化它，但约束照样要满足。约束因此成了类型系统的一部分：`S1<int>` 这个类型根本不存在，而不是存在但无法实例化。

实参依赖模板形参时，检查推迟到实例化。如果模板定义里写了一个约束不满足、又不依赖模板形参的名字，比如在 `S2<T>` 里写 `Ptr<int>`，这个模板就不可能有合法的特化，按 [[temp.res]] 属于非良构、不要求诊断。本机 Clang 23 仍然报了错。

显式实例化和显式特化同样要满足约束，不能用显式特化给不满足约束的实参补一个定义：

```cpp title="explicit-spec-constraint.cpp" error
template<typename T> concept C2 = sizeof(T) == 1;
template<C2 T> struct S {};

template struct S<char[2]>;         // error: 约束不满足
template<> struct S<char[2]> {};    // error: 约束不满足
```

函数模板不在 ¶14 之列。函数模板的约束在重载决议中检查（[[over.match.viable]]），不满足只是让这个候选不可行。

## concept-id 是 `bool` 值（¶15）

```cpp title="concept-id.cpp" error
template<typename T> concept C = sizeof(T) > 1;

static_assert(C<int>);           // OK
static_assert(!C<char>);         // OK：不满足就是 false
constexpr bool b = C<int> && C<long>;
auto p = &C<int>;                // error: 不能对 prvalue 取地址
```

¶15 模板名是概念名的 template-id 叫做 **concept-id**（[[g:concept-id]]）。它是一个 `bool` 类型的 prvalue，不指称任何特化，因为概念不会被实例化（[[temp.concept#5]]）。实参满足概念规范化后的约束表达式时，它的值是 `true`，否则是 `false`。

注 6：约束表达式是不求值操作数，所以出现在约束表达式里的 concept-id 不会像普通表达式那样求出 `bool` 再做运算。`C<T> && D<T>` 作为约束时，按 [[temp.constr.op]] 的合取规则逐项检查，只检查判断是否满足所需的部分。

!!! lawyer "concept-id 在约束内外的区别"
    - 在 *requires-clause* 或概念定义中，`C<T>` 会被规范化，展开成 `C` 的原子约束，参与约束之间的包含关系比较（[[temp.constr.normal]]）。
    - 在普通表达式中，如 `static_assert(C<int>)`、`if constexpr (C<T>)`，`C<int>` 就是一个 `bool` 值。
    - 把 concept-id 包进别的表达式，如 `!C<T>`、`(C<T> == true)`、`bool(C<T>)`，整个表达式就成了一个原子约束，不再展开，也就不能参与包含关系比较（[[temp.constr.atomic]]）。

## 历史与演进

!!! history
    - C++98 确立了 `template` 关键字的消歧规则；`>>` 是右移记号，嵌套模板必须写成 `> >`。
    - C++11 引入 `>>` 拆分（[[N1757]]），并允许在模板外写 `template` 关键字。
    - C++20 加入 ¶7.3.3（[[P0846R0]]）和 concept-id，以及 ¶14 的约束检查。同一版本的 [[P0634R3]] 让若干语境中依赖模板形参的限定名默认是类型，不必写 `typename`。这些语境后来整理为只能出现类型的语境（[[temp.res.general#4]]），¶7.3.4 引用的就是它。
    - C++26 加入了拼接后的 `<`（¶7.1、¶10）、*template-argument-name*，并弃用了 `template` 后面不跟实参列表的写法。C++26 定稿之后，[[P3670R4]] 又加入了包索引模板名（¶3–¶6、¶7.2）。

## 常见误解

!!! pitfall "编译器会自己判断要不要 `template`"
    不会。依赖模板形参的名字后面的 `<` 默认是小于号（¶7）。

!!! pitfall "`S<int>*` 只是个指针，不需要满足约束"
    需要。只要写出了不依赖模板形参的 `S<int>`，约束就必须满足（¶14）。显式特化也不能绕过约束。

## 思考题

!!! question "思考题 1"
    在模板定义 `template<class T> void f(T t) { t.get<0>(); }` 中，如果全局作用域里恰好有一个函数模板 `template<int> void get();`，`<` 会怎样解析？

<details markdown="1">
<summary>答案</summary>

解析为小于号，`t.get<0>()` 非良构，必须写 `t.template get<0>()`。

`t.get` 中的 `get` 是成员名，查找在 `t` 的类型里进行（[[basic.lookup.qual.general#2]]）。这个类型依赖 `T`，查找推迟到实例化（[[basic.lookup.qual.general#3]]），全局的 `get` 不参与，所以 ¶7.3.2 不适用；`get` 也不是非限定名，¶7.3.3 不适用。本机 Clang 23 报告 "missing 'template' keyword prior to dependent template name"。

较早的标准曾规定在整个后缀表达式的语境中再查一次，各编译器的行为也不一致。现行规则让结果不再取决于全局作用域里碰巧有什么。
</details>

!!! question "思考题 2"
    `Y<X<1>>2>> y;`（`X` 是 `template<int>`，`Y` 是 `template<class>`）能编译吗？怎样改？

<details markdown="1">
<summary>答案</summary>

不能。`X<1>>2` 中的 `>>` 被拆成两个 `>`：第一个结束 `X<1>`，第二个结束 `Y<X<1>>`，剩下的 `2>> y;` 无法解析。改成 `Y<X<(1>>2)>> y;`。
</details>

!!! question "思考题 3"
    下面哪一个声明要求约束得到满足？

    ```cpp
    template<std::integral T> struct S {};
    template<class T> void f(S<T>*);       // (a)
    void g(S<double>*);                    // (b)
    ```

<details markdown="1">
<summary>答案</summary>

(a) 中 `S<T>` 的实参依赖 `T`，¶14 不要求此时满足。(b) 中 `S<double>` 不依赖模板形参，必须满足约束。`std::integral<double>` 为假，所以 (b) 非良构，即使 `g` 从未被调用、`S<double>` 从未被实例化。
</details>

<details class="fine" markdown="1"><summary>其余条文</summary>

¶1 给出 template-id 的文法。除了 `模板名<实参列表>`（*simple-template-id*），运算符函数名和字面量运算符名后面也可以跟实参列表，如 `operator+<int>`、`operator""_x<'a'>`。模板实参可以是类型（*type-id*）、常量表达式、花括号列表（如 `C<{42}>`，用于初始化常量形参），或者一个可能带限定的名字（*template-argument-name*）{{c++26}}。名字形式的实参先按名字查找，再由 [[temp.arg.general#3]] 根据查找结果决定它是模板、类型还是表达式，这样概念和变量模板也能作为模板模板实参。

¶2、¶12 规定组成名字（component name）：template-id 的组成名字是其中第一个名字；*template-argument-name* 的组成名字是其限定部分中的名字和最后的标识符。其他条款用这个说法规定查找。

¶3–¶6 {{c++29}} 包索引模板名 `P...[I]`：`P` 必须是一个模板模板形参包，`I` 是 `std::size_t` 类型的转换常量表达式，满足 `0 ≤ I < sizeof...(P)`。它本身是一个包展开，指称包中第 `I` 个模板名，例如 `TTs...[0]<int>`。截至写作时，本机 Clang 23 支持类型和表达式的包索引，但还不支持这种写法。

¶10 {{c++26}} 模板实参不能是不带括号的拼接表达式：`S<[:r:]>` 非良构，`S<([:r:])>`、`S<[:r:] + 1>` 合法。在模板实参的位置，`[:r:]` 可能拼出类型、模板或值，加括号强制把它当表达式。

</details>
