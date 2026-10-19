---
title: 比较
summary: C++20 预置比较运算符：哪些函数可以 = default；== 与 <=> 如何按展开的子对象列表逐个比较；auto <=> 的返回类型为公共比较类别；没有 <=> 的成员如何用 == 与 < 合成三路比较；预置的 != 和 < 等如何借助重写候选实现；何时被定义为删除
status: done
since: c++20
covers: class.compare.default, class.eq, class.spaceship, class.compare.secondary
papers: P0515R3, P1185R2, P1186R3, P2002R1, P2468R2
related: over.match.oper, over.match.best, expr.spaceship, expr.eq, expr.rel, cmp.categories, dcl.fct.def.default, over.binary
tags: 比较, 三路比较, operator<=>, 预置函数, C++20
updated: 2026-10-17
---

C++20 之前，给一个类写全套比较运算符意味着六个函数（`==` `!=` `<` `>` `<=` `>=`），而且它们之间的一致性完全靠手工维护。C++20 用两个机制解决这个问题：

1. **重写候选**（rewritten candidates，[[over.match.oper]]）：编译器为 `a < b` 做重载决议时，也会考虑 `(a <=> b) < 0` 和 `0 < (b <=> a)`；为 `a != b` 考虑 `!(a == b)`；为 `a == b` 考虑 `b == a`。于是只要写 `==` 和 `<=>` 两个运算符，就能得到全部六个关系与相等比较，且参数顺序可以对调。
2. **预置比较**（defaulted comparison，本节）：`==` 和 `<=>` 本身也可以 `= default`，由编译器按成员逐个比较生成。

本节 [[class.compare]] 包含四个子条款：

| 子条款 | 内容 |
|---|---|
| [class.compare.default] | 什么样的函数可以预置；何时删除；可用的定义；隐式声明的 `==`；展开的子对象列表 |
| [class.eq] | 预置 `==` 的定义 |
| [class.spaceship] | 合成三路比较；预置 `<=>` 的定义与返回类型推导；公共比较类型 |
| [class.compare.secondary] | 预置 `!=`、`<`、`>`、`<=`、`>=` |

前置知识：`<=>` 运算符本身（[[expr.spaceship]]）以及三种比较类别 `std::strong_ordering`、`std::weak_ordering`、`std::partial_ordering`（[[cmp.categories]]）。

## 一个例子看全貌

```cpp run title="overview.cpp" ok
#include <compare>
#include <string>

struct Point {
    int x;
    int y;
    auto operator<=>(const Point&) const = default;   // 预置 <=>；同时隐式声明预置的 ==
};

struct Person {
    std::string name;
    int age;
    bool operator==(const Person&) const = default;    // 只要相等比较
};

int main() {
    Point a{1, 2}, b{1, 3};
    bool r1 = a < b;     // 重写为 (a <=> b) < 0：先比 x（相等），再比 y（2 < 3）→ true
    bool r2 = a != b;    // 重写为 !(a == b)
    bool r3 = a >= b;    // 重写为 (a <=> b) >= 0
    Person p{"Ann", 30}, q{"Ann", 30};
    bool r4 = p == q;    // 逐成员 ==
    bool r5 = p != q;    // 重写为 !(p == q)
    // bool r6 = p < q;  // error: Person 没有 <=>，也没有 <
    return (r1 && r2 && !r3 && r4 && !r5) ? 0 : 1;
}
```

## 什么函数可以预置（[class.compare.default] ¶1）

¶1 一个预置的比较运算符函数（[[over.binary]]）必须是非模板函数，并且：

- ¶1.1 是某个类 `C` 的非静态成员或友元；
- ¶1.2 在 `C` 中定义为预置，或在 `C` 完整的语境中定义为预置；
- ¶1.3 有两个类型为 `const C&` 的形参，或者两个类型为 `C` 的形参，隐式对象形参（若有）视为第一个形参。

满足这些条件的称为类 `C` 的[[g:defaulted-comparison-operator-function|预置比较运算符函数]]。另外：

- 隐式定义中的名字查找与访问检查，在与其函数体等价的语境中进行，所以可以访问 `C` 的私有成员（作为成员或友元本来就可以）；
- 在类内定义为预置的比较运算符，必须是该函数的第一个声明。

标准例 1 与更多边界情形：

```cpp title="which-can-default.cpp" error
#include <compare>

struct S;
bool operator==(S, S) = default;                      // error: S 不完整

struct S2 {
    friend bool operator==(S2, const S2&) = default;  // error: 两个形参类型不同
};

enum E {};
bool operator==(E, E) = default;                      // error: 不是类的成员或友元

struct M1 { int x; bool operator==(const M1&) = default; };  // error: 非 const 成员——
                                                             // 隐式对象形参是 M1&，不是 const M1&
struct M2 { int x; bool operator==(M2) const = default; };   // error: 隐式对象形参是 const M2&，
                                                             // 与 M2 类型不同
```

¶1.3 规定隐式对象形参算作第一个形参，因此成员形式只能写成 `bool operator==(const C&) const`（两个都是 `const C&`）。想要两个都按值传递，可以用友元，或者 C++23 的显式对象形参：

```cpp run title="valid-forms.cpp" ok
#include <compare>

struct A { int x; bool operator==(const A&) const = default; };           // 成员，const C&
struct B { int x; friend bool operator==(const B&, const B&) = default; };// 友元，const C&
struct C { int x; friend auto operator<=>(C, C) = default; };             // 友元，按值
struct D { int x; bool operator==(this D, D) = default; };                // 显式对象形参，按值

struct F { int x; friend bool operator==(const F&, const F&); };
bool operator==(const F&, const F&) = default;   // 类外预置：此处 F 完整，且是 F 的友元

struct G { int x; bool operator==(const G&) const; };
bool G::operator==(const G&) const = default;    // 类外预置成员

int main() {
    static_assert(A{1} == A{1} && B{1} == B{1} && C{1} < C{2} && D{1} == D{1});
    return F{1} == F{1} && G{1} == G{1} ? 0 : 1;
}
```

类外预置的形式（`F`、`G`）有一个实际用途：把比较运算符的定义放进 `.cpp` 文件，避免在头文件中实例化成员类型的比较（这与 [[dcl.fct.def.default]] 中类外预置的函数属于用户提供的规则有关）。注意 `C` 按值传参的版本也会隐式声明一个按值传参的 `==`（见下文 ¶4），所以 `C{1} == C{1}` 同样可用。

## 何时被定义为删除（[class.compare.default] ¶2）

¶2 若类 `C` 有引用类型的非静态数据成员，或者有变体成员（[[class.union.anon]]，即 `C` 是联合体或含匿名联合体），则 `C` 的预置 `<=>` 或 `==` 定义为删除。

```cpp title="deleted-cases.cpp" error
struct Ref {
    int& r;
    bool operator==(const Ref&) const = default;  // 定义为删除（Clang 发出 -Wdefaulted-function-deleted 警告）
};

struct HasUnion {
    union { int i; float f; };
    bool operator==(const HasUnion&) const = default;  // 定义为删除
};

bool f(Ref a, Ref b) { return a == b; }   // error: 使用了被删除的函数
```

为什么？对引用成员来说，比较有两种同样合理的含义：比较引用指向的值，或者比较引用是否绑定到同一个对象。标准不替程序员做这个选择。对联合体，编译器不知道哪个成员是活跃的，无法比较。

## 可用的定义（[class.compare.default] ¶3）

¶3 后文反复用到一个术语：二元运算符表达式 `a @ b` 是[[g:usable-comparison|可用的]]（usable），如果

- ¶3.1 `a` 或 `b` 是类或枚举类型，且对 `a @ b` 的重载决议（[[over.match]]）得到一个可用的候选（usable candidate，即选出了一个未被删除的最佳函数，[[over.match.general]]）；或
- ¶3.2 `a` 和 `b` 都不是类或枚举类型，且 `a @ b` 是合法表达式。

这个定义把能否比较的判定完全交给普通的重载决议，包括重写候选。所以一个只定义了 `<=>` 的成员类型，`xi == xi` 不可用（`==` 不会被重写为 `<=>`），`xi < xi` 却是可用的。

## 隐式声明的 `==`（[class.compare.default] ¶4）

¶4 如果类的 *member-specification* 没有显式声明任何名为 `operator==` 的成员或友元，那么对 *member-specification* 中每个定义为预置的三路比较运算符函数，都隐式声明一个 `==` 运算符函数：访问权限、*function-definition*、所在类作用域都与那个三路比较运算符相同，只是返回类型换成 `bool`，*declarator-id* 换成 `operator==`。

注 1 补充细节：

- 隐式声明的 `==` 在类定义中被定义为预置，具有相同的 *parameter-declaration-clause* 与尾随 *requires-clause*；
- 三路比较运算符若是 `friend`、`virtual`、`constexpr`、`consteval`，隐式的 `==` 也是；
- 若三路比较运算符没有 *noexcept-specifier*，隐式的 `==` 有自己的隐式异常说明，可能与 `<=>` 的不同（例如成员的 `==` 是 `noexcept` 而 `<=>` 不是）。

标准例 2：

```cpp run title="implicit-eq.cpp" ok
#include <compare>

template<typename T> struct X {
    friend constexpr std::partial_ordering operator<=>(X, X) requires (sizeof(T) != 1) = default;
    // 隐式声明：friend constexpr bool operator==(X, X) requires (sizeof(T) != 1) = default;

    [[nodiscard]] virtual std::strong_ordering operator<=>(const X&) const = default;
    // 隐式声明：[[nodiscard]] virtual bool operator==(const X&) const = default;
};

int main() {
    X<char> a, b;          // sizeof(char) == 1：友元版本的约束不满足，只剩成员版本
    (void)(a <=> b);       // 成员 <=>，strong_ordering
    (void)(a == b);        // 隐式声明的成员 ==
    // 若换成 X<int>：友元（按值）与成员（const&）两个 <=>、两个 == 对左值实参匹配得同样好，
    // a <=> b 与 a == b 都是二义的（本机 Clang 证实）。标准例只演示声明，并不打算让人这样用。
}
```

注 2：即使预置的三路比较运算符被定义为删除，`==` 仍然会被隐式声明（它自己是否删除，按 [class.eq] 独立判断）。

### 为什么 `<=>` 不顺便提供 `==` 的实现

C++20 最初的设计（[[P0515R3]]）让 `a == b` 也可以重写为 `(a <=> b) == 0`。后来 [[P1185R2]] 发现这有严重的性能问题：对 `std::vector`、`std::string` 这样的类型，`==` 可以先比较长度、长度不同立即返回 `false`；而 `<=>` 必须按字典序逐元素比较才能给出大小关系。如果 `==` 一律经由 `<=>` 实现，所有逐成员比较的类都会在不知不觉中变慢。

于是规则改为：`==` 永远不会重写为 `<=>`；预置的 `<=>` 会额外隐式声明一个预置的 `==`，后者**逐成员调用 `==`**（而不是 `<=>`）。这就是 ¶4 存在的理由。

¶4 要求没有显式声明任何 `operator==`，这个条件很关键：只要自己写了一个 `operator==`（哪怕参数类型完全不同），隐式的就不会出现。

```cpp title="no-implicit-eq.cpp" error
#include <compare>

struct U {
    int x;
    std::strong_ordering operator<=>(const U& o) const { return x <=> o.x; }  // 用户提供，不是预置
};

struct V {
    int x;
    auto operator<=>(const V&) const = default;
    bool operator==(int) const;   // 显式声明了一个 operator==（参数是 int）
};

bool t1(U a, U b) { return a < b; }    // OK：重写为 (a <=> b) < 0
bool t2(U a, U b) { return a == b; }   // error: U 的 <=> 不是预置的，不会隐式声明 ==
bool t3(V a, V b) { return a == b; }   // error: V 显式声明了 operator==，不再隐式声明 V == V
```

## 展开的子对象列表（[class.compare.default] ¶5）

¶5 预置比较的核心数据结构是对象 `x` 的[[g:expanded-list-of-subobjects|展开的子对象列表]]：

1. 先是 `C` 的直接基类子对象，按 *base-specifier-list* 中的声明顺序；
2. 然后是 `C` 的直接成员子对象（非静态数据成员），按 *member-specification* 中的声明顺序；
3. 其中数组类型的子对象递归展开为其元素序列，下标递增。

记 x<sub>i</sub> 为列表中第 *i* 个元素的左值，它通过对 `x` 施加派生类到基类的转换、类成员访问、数组下标得到。

需要注意以下几点：

- 只有直接基类与直接成员，基类的成员由基类自己的比较运算符负责（逐层递归由重载决议自然完成）；
- 静态数据成员不在列表中；
- 基类先于成员，与构造顺序（[[class.base.init#15]]）一致，因而比较的字典序首先由基类决定。

```cpp run title="subobject-order.cpp" ok
#include <compare>
#include <cstdio>

struct Loud {
    int v;
    bool operator==(const Loud& o) const { std::printf("==%d ", v); return v == o.v; }
    std::strong_ordering operator<=>(const Loud& o) const { std::printf("<=>%d ", v); return v <=> o.v; }
};

struct B { Loud b; auto operator<=>(const B&) const = default; };
struct D : B {
    Loud m1, m2;
    auto operator<=>(const D&) const = default;
};

int main() {
    D x{{{0}}, {1}, {2}}, y{{{0}}, {9}, {2}};
    bool e = x == y;   std::printf("-> %d\n", e);    // ==0 ==1 -> 0：先基类，再 m1，m1 不等即停止
    bool l = x < y;    std::printf("-> %d\n", l);    // <=>0 <=>1 -> 1
    bool n = x != y;   std::printf("-> %d\n", n);    // ==0 ==1 -> 1：!= 重写为 !(x == y)
}
```

## 预置的 `==`（[class.eq]）

¶1 预置的相等运算符函数的声明返回类型必须是 `bool`。

¶2 若对 `C` 类型对象 `x` 的展开子对象列表中的某个 x<sub>i</sub>，`xi == xi` 不可用，则 `C` 的预置 `==` 定义为删除。

¶3 返回值：按下标递增顺序比较对应元素 x<sub>i</sub> 与 y<sub>i</sub>，直到第一个使 `xi == yi` 的结果（按语境转换为 `bool`）为 `false` 的下标。若存在这样的下标，返回 `false`，否则返回 `true`。

换句话说，就是短路的逐成员 `&&`。空类（列表为空）的预置 `==` 总是返回 `true`。

¶4 标准例 1：

```cpp run title="eq-example.cpp" ok
struct D {
    int i;
    friend bool operator==(const D& x, const D& y) = default;   // OK，返回 x.i == y.i
};

int main() { return D{1} == D{1} ? 0 : 1; }
```

## 合成三路比较（[class.spaceship] ¶1）

预置 `<=>` 要比较每个成员，但很多既有类型只有 `==` 和 `<`、没有 `<=>`。[[P1186R3]] 为此引入[[g:synthesized-three-way-comparison|合成三路比较]]：对同类型的 glvalue `a`、`b`，类型 `R`（一个比较类别）的合成三路比较定义如下：

- ¶1.1 若 `a <=> b` 可用，且能用 `static_cast` 显式转换为 `R`：结果是 `static_cast<R>(a <=> b)`；
- ¶1.2 否则，若 `a <=> b` 可用，或者对 `a <=> b` 的重载决议找到了至少一个可行候选：合成三路比较无定义；
- ¶1.3 否则，若 `R` 不是比较类别类型，或者 `a == b`、`a < b` 之一不可用：无定义；
- ¶1.4 否则，若 `R` 是 `strong_ordering`：`a == b ? equal : a < b ? less : greater`；
- ¶1.5 否则，若 `R` 是 `weak_ordering`：同上，`equal` 换成 `equivalent`；
- ¶1.6 否则（`R` 是 `partial_ordering`）：`a == b ? equivalent : a < b ? less : b < a ? greater : unordered`。

注 1：若重载决议找到了可用的候选，但它们不满足上述表达式隐含的其他要求（例如 `a < b` 的结果无法转换为 `bool`），合成三路比较是非良构的。

这里有几个设计要点：

- ¶1.2 防止擅自回退：只要类型有 `<=>`（哪怕返回的类型无法转换为 `R`，或者调用会二义），就不退回到用 `==`/`<` 合成。类型作者显然对三路比较有自己的设计，静默绕过它是危险的。
- 合成只在 `R` 是具体的比较类别时发生：如果预置 `<=>` 的返回类型是 `auto`，编译器无从知道该合成哪一种类别，所以 `auto` 不使用合成（见下文 ¶2.1）。
- `partial_ordering` 需要多比一次 `b < a`，才能区分 `greater` 与 `unordered`。

```cpp run title="synthesized.cpp" ok
#include <compare>

struct Legacy {                  // C++20 之前写的类型：只有 == 与 <
    int v;
    constexpr bool operator==(const Legacy& o) const { return v == o.v; }
    constexpr bool operator<(const Legacy& o) const  { return v < o.v; }
};

struct W {
    Legacy l;
    std::strong_ordering operator<=>(const W&) const = default;   // OK：用 == 与 < 合成
};

struct W2 {
    Legacy l;
    auto operator<=>(const W2&) const = default;   // 定义为删除：auto 不合成，Legacy 没有 <=>
};

static_assert(W{{1}} < W{{2}});
static_assert(W{{1}} == W{{1}});   // 隐式声明的 ==，逐成员调用 Legacy::operator==

int main() {}
```

## 预置的 `<=>`（[class.spaceship] ¶2–¶3）

### 何时删除、返回类型是什么（¶2）

¶2 设 `R` 是预置三路比较运算符函数的声明返回类型，x<sub>i</sub> 是展开子对象列表的元素：

- ¶2.1 若 `R` 是 `auto`：设 *cv<sub>i</sub>* R<sub>i</sub> 为 `xi <=> xi` 的类型。若该表达式不可用，或任何 R<sub>i</sub> 不是比较类别类型，函数定义为删除。否则返回类型推导为 R<sub>0</sub>, R<sub>1</sub>, …, R<sub>n−1</sub> 的公共比较类型；
- ¶2.2 否则，`R` 不得含占位符类型（例如不能写 `decltype(auto)`）。若任一 x<sub>i</sub> 与自身的类型 `R` 的合成三路比较无定义，函数定义为删除。

### 公共比较类型（¶4）

¶4 一组（可能为空的）比较类别类型 T<sub>0</sub>, …, T<sub>n−1</sub> 的[[g:common-comparison-type|公共比较类型]] `U`：

- ¶4.1 只要有一个 T<sub>i</sub> 是 `std::partial_ordering`，`U` 就是 `std::partial_ordering`；
- ¶4.2 否则，只要有一个是 `std::weak_ordering`，`U` 就是 `std::weak_ordering`；
- ¶4.3 否则 `U` 是 `std::strong_ordering`。注 2：特别地，*n* 为 0 时也是这个结果。

直观地说，结果取其中最弱的类别。`strong` 可以转换为 `weak`，`weak` 可以转换为 `partial`，反之不行。标准库的 `std::common_comparison_category` 实现同样的计算（[[cmp.common]]）。

```cpp run title="common-category.cpp" ok
#include <compare>
#include <string>
#include <type_traits>

struct Weak {
    int v;
    std::weak_ordering operator<=>(const Weak&) const = default;
};

struct A { int i; std::string s; auto operator<=>(const A&) const = default; };
struct B { int i; Weak w;        auto operator<=>(const B&) const = default; };
struct C { int i; Weak w; double d; auto operator<=>(const C&) const = default; };
struct E { auto operator<=>(const E&) const = default; };   // 空类
struct F { int a[3]; auto operator<=>(const F&) const = default; };  // 数组逐元素

static_assert(std::is_same_v<decltype(A{} <=> A{}), std::strong_ordering>);
static_assert(std::is_same_v<decltype(B{} <=> B{}), std::weak_ordering>);
static_assert(std::is_same_v<decltype(C{} <=> C{}), std::partial_ordering>);  // double 的 <=> 是 partial
static_assert(std::is_same_v<decltype(E{} <=> E{}), std::strong_ordering>);   // n == 0
static_assert(F{{1, 2, 3}} < F{{1, 2, 4}});

int main() {}
```

### 返回值（¶3）

¶3 返回值：按下标递增顺序，对 x<sub>i</sub> 与 y<sub>i</sub> 做类型 `R` 的合成三路比较，直到第一个结果 v<sub>i</sub> 使 `vi != 0`（按语境转换为 `bool`）为真的下标。若存在这样的下标，返回 v<sub>i</sub> 的副本；否则返回 `static_cast<R>(std::strong_ordering::equal)`。

这正是字典序比较。对 `partial_ordering` 而言，`unordered != 0` 为真，所以遇到 NaN 这类无序元素会立即返回 `unordered`。

```cpp run title="nan.cpp" ok
#include <cmath>
#include <compare>

struct P {
    double x;
    int y;
    auto operator<=>(const P&) const = default;
};

int main() {
    P a{NAN, 1}, b{NAN, 2};
    auto r = a <=> b;                                   // 第一个成员就是 unordered，立即返回
    bool ok = (r == std::partial_ordering::unordered)
              && !(a < b) && !(a > b) && !(a == b);     // 四者皆假
    return ok ? 0 : 1;
}
```

## 预置的次级比较运算符（[class.compare.secondary]）

¶1 [[g:secondary-comparison-operator|次级比较运算符]]指关系运算符（`<` `>` `<=` `>=`，[[expr.rel]]）和 `!=`。预置的次级比较运算符函数的声明返回类型必须是 `bool`。

¶2 对形参 `x`、`y`，若出现以下情形，该运算符函数定义为删除：

- ¶2.1 对 `x @ y` 的第一次重载决议
    - ¶2.1.1 没有得到可用的候选，或
    - ¶2.1.2 选中的候选不是重写候选；
- ¶2.2 对用选中的重写候选解释 `x @ y` 所得的表达式（例如 `(x <=> y) @ 0`）做第二次重载决议，没有得到可用的候选；
- ¶2.3 `x @ y` 不能隐式转换为 `bool`。

在这两次重载决议中，这个预置的运算符函数自身不作为候选（否则它会选中自己）。如果不删除，函数返回 `x @ y`。

换句话说，预置的 `<` 相当于用 `<=>` 实现 `<`，预置的 `!=` 相当于用 `==` 实现 `!=`。既然重写候选已经自动提供了这些，为什么还需要预置它们？主要用于需要一个真实存在的函数的场合：取函数地址、作为虚函数在派生类中覆盖、显式控制可见性或 ABI。

¶3 标准例 1：

```cpp run title="secondary.cpp" ok
#include <compare>

struct HasNoLessThan {};

struct C {
    friend HasNoLessThan operator<=>(const C&, const C&);
    bool operator<(const C&) const = default;   // OK：函数被定义为删除——
                                                // (x <=> y) < 0 中 HasNoLessThan < int 不可用（¶2.2）
};

template<class T> concept LessComparable = requires(T a) { a < a; };
static_assert(!LessComparable<C>);   // 被删除的函数使 a < a 不可用

struct Good {
    int v;
    auto operator<=>(const Good&) const = default;
    bool operator<(const Good&) const = default;   // 返回 (x <=> y) < 0
};
static_assert(Good{1} < Good{2});
static_assert(&Good::operator< != nullptr);       // 可以取地址——这是写它的理由之一

int main() {}
```

!!! note "Clang 的诊断"
    若真的调用 `C` 的 `<`（如 `c1 < c2`），按标准，结果是使用了被删除的函数；本机 Clang 23 报告的错误却位于预置函数内部，说 `HasNoLessThan` 与 `int` 的操作数无效。两者都是诊断，程序非良构的结论一致；在 `requires` 等 SFINAE 语境中，Clang 也正确地把它当作删除（上例的 `static_assert` 通过）。类似地，预置 `<=>` 的声明返回类型为 `R`、而成员的 `<=>` 结果无法 `static_cast` 为 `R` 时（¶1.1 失败、¶1.2 使合成无定义、¶2.2 使函数删除），Clang 在使用处报告 `static_cast` 失败，而不是报告使用了被删除的函数。

## 与重写候选的交互

预置比较只负责生成 `==` 和 `<=>`；让它们自动支持六种运算符和参数对调的，是 [[over.match.oper]] 的重写机制。简要回顾（详见那一页）：

| 表达式 | 额外考虑的重写候选 | 选中后的解释 |
|---|---|---|
| `x < y`（及 `>` `<=` `>=`） | 所有 `x <=> y` 的候选；以及参数对调的 `y <=> x` 的候选 | `(x <=> y) < 0` 或 `0 < (y <=> x)` |
| `x <=> y` | 参数对调的 `y <=> x` 的候选 | `0 <=> (y <=> x)` |
| `x != y` | `x == y` 的候选（须为重写目标）；以及对调的 `y == x` | `!(x == y)` 或 `!(y == x)` |
| `x == y` | 对调的 `y == x` 的候选（须为重写目标） | `y == x` |

再加上 [[over.match.best]] 的两条决胜规则：同等条件下非重写候选优先于重写候选（¶2.8），非对调的重写候选优先于对调的（¶2.9）。

### 对调带来的 C++20 兼容性问题

对调候选让 `1 == s` 自动可用，但也带来了一个广为人知的兼容性问题：过去随手写成非 const 的成员 `operator==`，在 C++20 中会和自己的对调版本产生二义。

```cpp run title="reversed-ambiguity.cpp" ok
struct S {
    int x;
    bool operator==(const S& o) { return x == o.x; }   // 非 const 成员：C++17 风格的"小错误"
};

bool f(S a, S b) { return a == b; }
// 候选 1：a.operator==(b)        —— 隐式对象形参 S&，第二形参 const S&
// 候选 2（对调）：b.operator==(a) —— 对 a 是 const S&（需要加 const），对 b 是 S&（精确）
// 两者各有一个实参更好，严格按规则是二义的

int main() { S a{1}, b{1}; return f(a, b) ? 0 : 1; }
```

严格按标准，这是二义的（非良构）。但为了不让大量既有代码在升级到 C++20 后无法编译，Clang 与 GCC 都选择接受它（选非对调的那个）并给出警告。本机 Clang 23 报告 `-Wambiguous-reversed-operator`："ISO C++20 considers use of overloaded operator '==' ... to be ambiguous despite there being a unique best viable function"。正确的修复是把成员 `operator==` 声明为 `const`。

### `operator!=` 阻止 `==` 被重写（C++23）

[[over.match.oper#4]] 规定，名为 `operator==` 的函数 *F* 是以 *o* 为第一操作数的**重写目标**，除非在相应作用域中能找到一个与 *F* 对应（如果改名为 `operator==` 就会对应）的 `operator!=`。这条规则来自 [[P2468R2]]（作为 C++20 的缺陷报告），目的是兼容那些成对定义 `==` 与 `!=` 的旧代码：既然作者自己写了 `!=`，编译器就不再替他把 `==` 对调或用来实现 `!=`。

```cpp title="rewrite-target.cpp" error
struct A {
    int x;
    bool operator==(int i) const { return x == i; }
    bool operator!=(int i) const { return x != i; }   // 与 operator==(int) 对应
};
struct B {
    int x;
    bool operator==(int i) const { return x == i; }   // 没有对应的 !=
};

bool f1(A a) { return 1 == a; }   // error: A::operator== 不是重写目标，不能对调
bool f2(B b) { return 1 == b; }   // OK：对调为 b == 1
bool f3(B b) { return 1 != b; }   // OK：重写为 !(b == 1)
```

## 实现视角

!!! impl "生成的代码"
    预置 `<=>` 生成的代码就是 ¶3 的直译：对每个子对象依次比较，结果非零即返回；预置 `==` 是短路的逐成员 `&&`。优化器能看到全部成员比较，因此通常与手写的同等逻辑生成相同的代码，预置并不意味着更慢。

    预置比较运算符满足条件时是隐式 `constexpr` 的（[[dcl.fct.def.default]]），异常说明也是隐式的（[[except.spec]]）：只有当用到的子对象比较都不抛出时才是 `noexcept`。

!!! impl "诊断"
    - `-Wdefaulted-function-deleted`（Clang，默认开启）：显式预置的比较运算符被隐式定义为删除，并说明原因（如引用成员、某成员没有可行的三路比较函数）；
    - `-Wambiguous-reversed-operator`（Clang）：见上文对调二义。

## 历史与演进

!!! history "历史与演进"
    - C++20：
        - [[P0515R3]] 引入 `<=>`、比较类别，以及预置 `<=>`；
        - [[P1185R2]]：`==` 不再重写为 `<=>`；预置 `<=>` 隐式声明预置 `==`（¶4）；
        - [[P1186R3]]：合成三路比较，允许对只有 `==`/`<` 的成员预置 `<=>`（须写出具体返回类型）；
        - [[P2002R1]] 等：澄清预置比较的规格（可预置的形式、删除条件、查找语境等）。
    - C++23（作为 C++20 的缺陷报告）：[[P2468R2]] 引入重写目标的概念（[[over.match.oper#4]]），存在对应 `operator!=` 时不再对 `operator==` 做重写。
    - C++23 显式对象形参（deducing this）也可用于预置比较：`bool operator==(this C, C) = default;`。

## 陷阱

!!! pitfall "自己写了 `<=>` 就以为有 `==`"
    只有预置的 `<=>` 才会隐式声明 `==`。手写 `<=>` 时要再写 `bool operator==(const T&) const = default;`（或手写）。

!!! pitfall "随手加了一个 `operator==(int)`，结果同类比较消失了"
    ¶4 的条件是没有显式声明任何名为 `operator==` 的成员或友元。任何重载都会抑制隐式 `==`；此时需要显式 `bool operator==(const T&) const = default;`。

!!! pitfall "`auto operator<=>` 遇到只有 `<` 的旧类型"
    `auto` 不做合成（¶2.1），整个 `<=>` 被删除，`<`、`>` 等也随之不可用。把返回类型写成具体的类别（如 `std::weak_ordering`），让编译器用 `==` 与 `<` 合成。

!!! pitfall "浮点成员让 `<=>` 变成 `partial_ordering`"
    含 `double` 成员的类的 `auto <=>` 返回 `partial_ordering`。若外层类把预置 `<=>` 的返回类型写成 `std::strong_ordering` 或 `std::weak_ordering`，`partial_ordering` 无法 `static_cast` 为它们，合成三路比较无定义（¶1.1、¶1.2），外层的 `<=>` 被删除。需要全序时手写比较（例如对浮点成员使用 `std::strong_order`）。

!!! pitfall "指针成员的预置比较"
    对指针成员，预置比较比较的是地址，而不是指向的内容；对不相关对象的指针，内置 `<=>` 的结果未指定（[[expr.spaceship]]）。需要按内容比较时，手写。

## 思考题

!!! question "思考题 1"
    以下代码中 `a == b` 与 `a < b` 各调用了哪些函数？

    ```cpp
    struct Str {
        bool operator==(const Str&) const;
        std::strong_ordering operator<=>(const Str&) const;
    };
    struct T {
        int n;
        Str s;
        auto operator<=>(const T&) const = default;
    };
    T a, b;
    ```

<details markdown="1">
<summary>答案</summary>

`a == b`：调用隐式声明的预置 `T::operator==`（¶4），它依次计算 `a.n == b.n`（内置）和 `a.s == b.s`（`Str::operator==`），前者为假时短路。不会调用任何 `<=>`。

`a < b`：没有 `T::operator<`，重写为 `(a <=> b) < 0`，调用预置的 `T::operator<=>`，它依次计算 `a.n <=> b.n`（内置，`strong_ordering`）和 `a.s <=> b.s`（`Str::operator<=>`），第一个非零结果即返回。返回类型推导为 `strong_ordering`。
</details>

!!! question "思考题 2"
    `struct X { int v; bool operator<(const X&) const; bool operator==(const X&) const; };`，下面三个类中哪些的 `<=>` 可用？

    ```cpp
    struct Y1 { X x; auto operator<=>(const Y1&) const = default; };
    struct Y2 { X x; std::weak_ordering operator<=>(const Y2&) const = default; };
    struct Y3 { X x; std::partial_ordering operator<=>(const Y3&) const = default; };
    ```

<details markdown="1">
<summary>答案</summary>

`Y1` 的 `<=>` 被定义为删除：返回类型是 `auto`，`x <=> x` 不可用（¶2.1）。

`Y2` 可用：类型 `weak_ordering` 的合成三路比较走到 ¶1.5，`x == y ? equivalent : x < y ? less : greater`。

`Y3` 可用：走 ¶1.6，会多调用一次 `y < x` 以区分 `greater` 与 `unordered`。

另外，三者都会隐式声明预置的 `==`，它调用 `X::operator==`。
</details>

!!! question "思考题 3"
    为什么 ¶1.2 规定，只要 `a <=> b` 的重载决议找到了可行候选（哪怕最后是二义的），合成三路比较就无定义，而不是退回到用 `==` 和 `<` 合成？

<details markdown="1">
<summary>答案</summary>

因为这说明类型作者确实为该类型（或某个可转换到的类型）提供了三路比较，只是这次调用有问题（二义、返回类型不对、被删除等）。此时静默地改用 `==`/`<` 合成，可能得到与作者设计不一致的语义，而且错误被掩盖了。让预置 `<=>` 变成删除，会在使用处暴露问题。只有类型完全没有三路比较（旧类型）时才回退，这是 [[P1186R3]] 的设计意图。
</details>

## 小结

| 主题 | 要点 |
|---|---|
| 可预置的形式 | 非模板；`C` 的成员或友元；在 `C` 中或 `C` 完整处预置；两个 `const C&` 或两个 `C`（隐式对象形参算第一个） |
| 删除条件（共同） | 引用成员；变体成员 |
| 子对象列表 | 直接基类（声明序）→ 直接成员（声明序），数组展开 |
| `==` | 返回 `bool`；逐个 `xi == yi`，第一个假即返回假；某个 `xi == xi` 不可用则删除 |
| 隐式 `==` | 没有任何用户声明的 `operator==` 时，为每个预置 `<=>` 隐式声明一个预置 `==` |
| `auto <=>` | 每个 `xi <=> xi` 须可用且为比较类别；返回类型为公共比较类型；不做合成 |
| `R <=>` | 使用类型 `R` 的合成三路比较（有 `<=>` 用之；否则 `==` + `<` 合成） |
| 公共比较类型 | 有 partial → partial；否则有 weak → weak；否则 strong（含空列表） |
| 次级运算符 | 预置的 `!=` `<` 等返回经重写候选得到的 `x @ y`；第一次决议须选中重写候选 |
| 交互 | 重写候选、对调候选、非重写优先、非对调优先、重写目标（C++23） |
