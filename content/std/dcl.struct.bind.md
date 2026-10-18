---
title: 结构化绑定声明
summary: 结构化绑定先引入一个隐藏变量 e，再按数组、tuple-like（get<i> 成员优先）、数据成员三种协议把名字绑定到 e 的元素；结构化绑定不是变量；C++26 的绑定包、条件中的结构化绑定、属性与 constexpr
status: done
papers: P0217R3, P0961R1, P0969R0, P1091R3, P1381R1, P0609R3, P0963R3, P1061R10, P2686R5
related: dcl.pre, dcl.type.decltype, temp.variadic, stmt.pre, stmt.expand, expr.prim.lambda.capture, expr.prim.id.unqual, class.member.lookup, basic.lookup.argdep, tuple.helper
tags: 声明, 结构化绑定, tuple, 参数包
updated: 2026-10-17
---

```cpp
auto [x, y] = point;
```

这一行看起来像"声明两个变量 `x` 和 `y`，分别用 `point.x`、`point.y` 初始化"。标准说的完全不是这样：它**只声明了一个变量**——一个没有名字的变量 *e*，用 `point` 初始化；`x` 和 `y` 则是**结构化绑定**（structured binding），它们是"指向 *e* 的某个部分"的**名字**，本身既不是变量，也不是引用。

理解这个"一个隐藏变量 + 若干别名"的模型，几乎所有关于结构化绑定的"怪现象"都能直接推出来：

- `auto [x, y] = p;` 修改 `x` 不影响 `p`——因为改的是 *e* 的副本；
- `decltype(x)` 给出的类型和你想象的不一样——因为它报告的是"被引用类型"（referenced type），而不是某个变量的声明类型；
- `return x;` 不会隐式移动——因为 `x` 不是变量（[[expr.prim.id.unqual#15]]）；
- `auto& [a, b] = f();` 不能绑定纯右值——因为 *e* 是 `auto&` 引用，而左值引用不能绑定纯右值；
- 一个 `static` 结构化绑定声明只产生**一个**静态对象。

本节（[dcl.struct.bind]）规定 *e* 怎么声明、三种"拆解协议"如何选择、每个名字到底指什么。语法与说明符限制在 [[dcl.pre#7]]，`decltype` 的特殊规则在 [[dcl.type.decltype#1]]，绑定包展开在 [[temp.variadic]]。

## 语法与允许的说明符（[[dcl.pre#7]]）

```text
structured-binding-declaration:
    attribute-specifier-seq(opt) decl-specifier-seq ref-qualifier(opt) [ sb-identifier-list ]
sb-identifier:
    ...(opt) identifier attribute-specifier-seq(opt)
```

结构化绑定声明出现在三种地方：*simple-declaration*（加初始化器）、*condition*（{{c++26}}）、范围 `for` 的 *for-range-declaration*。[[dcl.pre#7]] 给出了约束：

| 约束 | 内容 |
|---|---|
| 说明符 | 只能是 `constexpr`、`constinit`、`static`、`thread_local`、`auto`、cv 限定符 |
| 类型 | 必须是**不受约束的** `auto`：`C auto [x, y] = ...` 非良构，`decltype(auto)` 也不行 |
| 包 | 至多一个 *sb-identifier* 带 `...`，而且有包时该声明必须声明一个**模板化实体**（templated entity） |
| 初始化器 | `= expr`、`{ expr }`、`( expr )` 三选一，都只能有**一个**表达式 |
| 初始化表达式类型 | 数组或非联合类类型；出现在 condition 中时只能是非联合类类型 |

```cpp title="sb-specifiers.cpp" error
#include <utility>
template<class T> concept C = true;

void f() {
    auto [a, b] = std::pair{1, 2};               // OK
    const auto& [c, d] = std::pair{1, 2};        // OK: e 是 const 引用，延长临时对象生命周期
    static auto [e1, e2] = std::pair{1, 2};      // OK (C++20)
    C auto [g, h] = std::pair{1, 2};             // error: 受约束的占位符
    int [i, j] = std::pair{1, 2};                // error: 必须用 auto
    auto [k, l] = {1, 2};                        // error: 初始化器必须是单个表达式（不是花括号列表）
    auto [m] = 42;                               // error: int 既不是数组也不是类
}
```

注意 `auto [k, l] = {1, 2};`：等号右边必须是 *assignment-expression*，花括号列表不是表达式。而 `auto [k, l]{p};` 是允许的——花括号里只有**一个**表达式，等价于直接初始化。（Clang 23 对 `= {1, 2}` 的处理是先把 *e* 推导成 `std::initializer_list<int>`，再报告无法绑定其私有成员——结论相同，但诊断的理由与标准不同。）

## 隐藏变量 *e*（¶1）

¶1 是整节的骨架。先给出几个记号：

- *cv*：*decl-specifier-seq* 中的 cv 限定符；
- *S*：*decl-specifier-seq* 中的 `constexpr`、`constinit` 和存储类说明符（`static`、`thread_local`）；
- `volatile` 出现在 *cv* 中已弃用（[[depr.volatile.type]]）{{deprecated}}。

然后：**先引入一个名字唯一的变量 *e***。它的声明分两种情况：

1. 初始化表达式是**数组类型** `cv1 A`、且没有 *ref-qualifier*（即按值拆数组）：*e* 被定义为 `attribute-specifier-seq S cv A e;`，然后**逐元素**复制初始化或直接初始化（取决于初始化器的形式）。这是为了绕开"数组不能整体复制"的限制——`auto` 推导会把数组退化成指针，所以必须特殊处理。
2. 其他情况：*e* "如同"由 `attribute-specifier-seq decl-specifier-seq ref-qualifier e initializer;` 定义，即把方括号部分换成 *e*，其余照抄。这个声明**永远不会被解释成函数声明**（避免 `auto [a, b](x);` 被读成什么奇怪东西）。

*id-expression* `e` 的类型记作 **E**。注 1 指出 E 永远不是引用类型——因为 id-expression 的类型会去掉引用（[[expr.prop]]）。所以 `auto& [a, b] = p;` 中 *e* 是 `P&`，但 E 是 `P`。

```cpp run title="hidden-e.cpp" ok
#include <cassert>

struct P { int x, y; };

int main() {
    P p{1, 2};

    auto [a, b] = p;        // e 是 P 的副本：P e = p;
    a = 100;
    assert(p.x == 1);       // 原对象不变

    auto& [c, d] = p;       // e 是 P&：P& e = p;
    c = 100;
    assert(p.x == 100);     // 通过 e 修改了 p

    int arr[2] = {3, 4};
    auto [u, v] = arr;      // e 是 int[2]，逐元素复制
    u = 0;
    assert(arr[0] == 3);
}
```

结构化绑定声明里的 `auto`、`const`、`&` 修饰的是 ***e***，**不是**各个名字。这是最常见的误解来源：

```cpp title="const-applies-to-e.cpp" ok
#include <type_traits>

struct S { int& r; int v; };

void f(int& i) {
    const auto [r, v] = S{i, 1};     // const 加在 e 上：const S e = S{i, 1};
    static_assert(std::is_same_v<decltype(v), const int>);   // e.v 是 const int
    static_assert(std::is_same_v<decltype(r), int&>);        // 引用成员：声明类型 int&
    r = 42;                           // OK: const 不传递到引用所指之物
}

int main() { int i = 0; f(i); }
```

`const auto [r, v]` 并没有让 `r` 变成 const——`r` 指的是 *e*.r，一个 `int&` 成员，而"const 对象的引用成员"仍然可以通过它修改被引用者。

### 生命周期延长与 *ref-qualifier*

由于 *e* 是一个普通的变量（或引用），[[class.temporary]] 的规则直接适用：

```cpp title="lifetime-ext.cpp" error
#include <string>
#include <utility>

std::pair<std::string, int> make();

void f() {
    auto&& [s1, n1] = make();        // OK: e 是右值引用，临时对象生命周期延长到 e 的作用域结束
    const auto& [s2, n2] = make();   // OK: 同理
    auto& [s3, n3] = make();         // error: 非 const 左值引用不能绑定纯右值
}
```

## 结构化绑定的个数（¶2–¶3）

¶2 定义 E 的**结构化绑定大小**（structured binding size）：E 需要引入的绑定个数，由后面三种协议分别给出（数组元素数 / `tuple_size` / 数据成员数）。

- 没有绑定包时，方括号里的名字个数必须**恰好等于**结构化绑定大小；
- 有绑定包时，非包名字的个数**不能超过**它，剩下的全部归入包（可能为零个）。

¶3 引入记号 SB*ᵢ*：展开绑定包之后的第 *i* 个结构化绑定。标准例 1 展示了包可以出现在任意位置：

```cpp title="sb-pack-positions.cpp" ok
struct C { int x, y, z; };

template<class T>
void now_i_know_my() {
    auto [a, b, c] = C();          // SB0=a, SB1=b, SB2=c
    auto [d, ...e] = C();          // e 是包，含 SB1、SB2
    auto [...f, g] = C();          // f 含 SB0、SB1；g 是 SB2
    auto [h, i, j, ...k] = C();    // k 是空包
    // auto [l, m, n, o, ...p] = C();   // error: 结构化绑定大小太小
}

int main() { now_i_know_my<int>(); }
```

### 结构化绑定包 {{c++26}}

¶1 第二句：带省略号的 *sb-identifier* 引入**结构化绑定包**（structured binding pack，[[temp.variadic#4]]）。包的元素就是一个个结构化绑定，可以像函数参数包一样展开、用 `sizeof...` 计数、用于折叠表达式：

```cpp run title="sb-pack.cpp" ok
#include <tuple>
#include <cstdio>

template<class Tuple>
auto sum(const Tuple& t) {
    const auto& [...xs] = t;          // xs 是结构化绑定包
    return (0 + ... + xs);
}

template<class T>
void print_all(const T& agg) {
    const auto& [first, ...rest] = agg;
    std::printf("first=%d, rest has %zu elements\n", first, sizeof...(rest));
}

struct Triple { int a, b, c; };

int main() {
    std::printf("%d\n", sum(std::tuple{1, 2, 3}));   // 6
    print_all(Triple{1, 2, 3});                       // first=1, rest has 2 elements
}
```

[[dcl.pre#7]] 要求含绑定包的声明**必须声明模板化实体**——也就是说它只能出现在模板（或泛型 lambda 等模板化上下文）中。原因是包展开的整个机制建立在"实例化时才确定元素数"之上：在非模板代码中引入一个包，意味着编译器要在非模板代码里处理包展开，这对实现是很大的负担。提案在演进中因此收窄了范围。

```cpp title="sb-pack-nontemplate.cpp" error
struct P { int x, y; };
void f() {
    auto [...xs] = P{};   // error: 含绑定包的声明必须是模板化实体
}
```

Clang 23 对此报告"pack declaration outside of template"。

## 结构化绑定作为条件（¶4）{{c++26}}

¶4：结构化绑定声明出现在 *condition* 中时，条件的**判定变量**（decision variable，[[stmt.pre]]）是 *e*。换句话说，`if (auto [a, b] = expr)` 判断的是 *e* 被上下文转换为 `bool` 的结果，而**不是**某个绑定的值。

```cpp run title="sb-condition.cpp" ok
#include <cstddef>
#include <cstdio>
#include <utility>

struct Parsed {
    int value;
    bool ok;
    explicit operator bool() const { std::puts("operator bool"); return ok; }
    template<std::size_t I> auto get() const {
        std::printf("get<%zu>\n", I);
        if constexpr (I == 0) return value; else return ok;
    }
};
template<> struct std::tuple_size<Parsed> { static constexpr std::size_t value = 2; };
template<> struct std::tuple_element<0, Parsed> { using type = int; };
template<> struct std::tuple_element<1, Parsed> { using type = bool; };

Parsed parse(const char*) { return {42, true}; }

int main() {
    if (auto [v, ok] = parse("42"))      // 判定的是 e（调用 operator bool）
        std::printf("v=%d ok=%d\n", v, ok);
}
// 输出：operator bool / get<0> / get<1> / v=42 ok=1
```

输出顺序不是巧合：¶7 末尾规定，*e* 的初始化**以及**把 *e* 作为判定变量做的转换，都**按顺序先于**任何 *rᵢ* 的初始化。这样设计的动机是：像 `std::from_chars` 结果、`expected` 之类的类型，往往只有"成功"时才能安全地取出各个分量；先判断再拆解，`get` 就不会在失败状态下被调用。

[[dcl.pre#7]] 规定条件中的初始化表达式只能是**非联合类类型**——数组不能被上下文转换为 `bool`，放进条件没有意义。

## 初始化器不能引用自己引入的名字（¶5）

¶5：如果初始化器引用了本声明引入的名字，程序非良构。

```cpp title="sb-self-ref.cpp" error
struct P { int x, y; };
void f() {
    auto [a, b] = (a, P{});   // error: 初始化器中使用了 a
}
```

为什么不按普通变量的规则（[[basic.scope.pdecl]]：变量的声明点在其声明符之后，`int x = x;` 是良构的，只是读了未初始化的值）？因为结构化绑定的名字指向 *e* 的部分，而 *e* 正是在初始化器求值之后才存在的——在初始化器中引用它没有任何可能的合理语义，于是直接禁止。

## 协议一：数组（¶6）

¶6：E 不能是**未知边界数组**；E 是其他数组类型（元素类型 T）时，结构化绑定大小就是元素个数，每个 SB*ᵢ* 是一个**左值**的名字，指向数组的第 *i* 个元素，类型是 T；**被引用类型**（referenced type）也是 T。注 3：T 的顶层 cv 限定就是 *cv*。

```cpp title="sb-array.cpp" ok
#include <cstddef>

auto f() -> int(&)[2];
auto g() -> int(&)[4];

void k() {
    auto [x, y] = f();       // e 是 int[2]，从 f() 返回的数组逐元素复制
    auto& [xr, yr] = f();    // e 是 int(&)[2]，xr/yr 指向 f 返回的那个数组
    (void)x; (void)y; (void)xr; (void)yr;
}

template<std::size_t N>
void h(int (&arr)[N]) {
    auto [a, ...b, c] = arr;   // a: 第 1 个元素；b: 第 2、3 个；c: 第 4 个
    auto& [...e] = arr;        // e: 指向全部 4 个元素的包
    (void)a; (void)c;
}

void call_h() { h(g()); }

int main() {}
```

```cpp title="sb-array-unknown.cpp" error
extern int arr[];
void f() {
    auto& [a, b] = arr;   // error: E 不能是未知边界数组
}
```

## 协议二：tuple-like（¶7）

只要 E 不是数组，而 `std::tuple_size<E>` 是一个**完整的类类型并且有名为 `value` 的成员**，就走 tuple-like 协议。这是用户自定义类型接入结构化绑定的唯一途径（对于想隐藏数据成员、或者想暴露"计算出来的"分量的类型）。

### 大小

`std::tuple_size<E>::value` 必须是良构的整型常量表达式，值非负；它就是结构化绑定大小。

注意判断条件的精确措辞："完整类类型 **且有成员 `value`**"。只声明了 `tuple_size<E>` 主模板（未定义）或特化里没有 `value`，都**不会**进入 tuple-like 协议，而是落到 ¶8 的数据成员协议。这让"一个类恰好特化了个空的 `tuple_size`"不至于破坏它的结构化绑定。

### `get` 的查找：成员优先，但只认"首个模板形参是常量形参"的成员模板

令 *i* 为 `std::size_t` 类型的索引纯右值。

- 在 E 的作用域中**搜索**名字 `get`（[[class.member.lookup]]），如果找到**至少一个**"首个模板形参是常量模板形参（非类型模板形参）的函数模板"，初始化器就是 `e.get<i>()`；
- 否则，初始化器是 `get<i>(e)`，其中 `get` **只**通过 ADL 查找（[[basic.lookup.argdep]]）。注 4 强调：**不做普通的无限定查找**。

无论哪种，`get<i>` 都被当作 *template-id* 解析（所以不必担心 `<` 被当成小于号）。

```cpp run title="sb-tuple-like.cpp" ok
#include <cstddef>
#include <tuple>
#include <type_traits>
#include <utility>

namespace lib {
    struct Point {
        int x, y;
        int get() const { return 42; }   // 非模板的成员 get：不算数，不会阻止 ADL
    };
    template<std::size_t I> int& get(Point& p) { return I == 0 ? p.x : p.y; }
    template<std::size_t I> const int& get(const Point& p) { return I == 0 ? p.x : p.y; }
    template<std::size_t I> int&& get(Point&& p) { return std::move(I == 0 ? p.x : p.y); }
}
template<> struct std::tuple_size<lib::Point> : std::integral_constant<std::size_t, 2> {};
template<std::size_t I> struct std::tuple_element<I, lib::Point> { using type = int; };

int main() {
    lib::Point p{1, 2};
    auto& [a, b] = p;                 // ADL 找到 lib::get<0>(e)，e 是左值
    a = 10;
    static_assert(std::is_same_v<decltype(a), int>);   // 被引用类型 Ti = int
    return p.x == 10 ? 0 : 1;
}
```

这条"成员优先、但要求首个模板形参是常量"的规则是 C++20 时修订的（[[P0961R1]]）。C++17 的原始规则是"只要在类中找到**任何**名为 `get` 的成员，就用成员形式"。这导致一个现实问题：许多类本来就有一个与 tuple 无关的成员 `get`（智能指针的 `get()`、某些 `std::shared_ptr` 包装器……），它们一旦想支持结构化绑定，就会被这个无关的 `get` 劫持，而 `e.get<0>()` 编译失败。现在的规则只认"看起来像 tuple 的 `get<I>`"的成员模板。

!!! lawyer "`template<class T> T get()` 的成员也不算"
    `std::variant` 风格的 `get<T>()`（首个模板形参是类型形参）不满足条件，所以不会阻止 ADL。但只要类里**有一个**满足条件的成员模板 `get`，就会用成员形式——哪怕那个模板对当前的 *i* 根本无法调用，也不会退回 ADL。查找结果是"全有或全无"。

### *e* 的值类别与 *rᵢ*

- 如果 *e* 实体的类型是**左值引用**，表达式 *e* 是**左值**；否则是 **xvalue**。

所以 `auto [a, b] = t;`（*e* 是对象）会以 xvalue 调用 `get`——这让 `get(T&&)` 重载可以把成员**移走**；而 `auto& [a, b] = t;` 以左值调用 `get`。

然后，令 T*ᵢ* = `std::tuple_element<i, E>::type`，U*ᵢ* 按初始化器 `get<i>(...)` 的值类别决定：

| 初始化器的值类别 | U*ᵢ* |
|---|---|
| 纯右值 | T*ᵢ* |
| 左值 | T*ᵢ*& |
| xvalue | T*ᵢ*&& |

引入一组名字唯一的**变量** `S Uᵢ rᵢ = initializer;`。每个 SB*ᵢ* 是一个**左值**的名字，类型是 T*ᵢ*，指向绑定到 *rᵢ* 的对象；被引用类型是 T*ᵢ*。

关键点：

1. 在 tuple-like 协议下，标准**确实创建了变量** *rᵢ*（通常是引用）。数组和数据成员协议下则没有额外变量，名字直接指向 *e* 的子对象。
2. 当 `get` 返回纯右值时，*rᵢ* 是 T*ᵢ* 类型的对象，从 `get` 的结果初始化——这时 SB*ᵢ* 指的是一个**独立的对象**而不是 *e* 的一部分。
3. *S*（`static`、`thread_local`、`constexpr`、`constinit`）同样施加于每个 *rᵢ*。
4. 求值顺序：*e* 的初始化先于所有 *rᵢ*；*rᵢ* 按下标从小到大依次初始化。

```cpp run title="sb-tuple-ref.cpp" ok
#include <string>
#include <tuple>
#include <type_traits>

int main() {
    int i = 0;
    std::tuple<int&, std::string> t{i, "hi"};
    auto [r, s] = t;      // e 是 t 的副本；e 的第 0 个元素仍然引用 i
    static_assert(std::is_same_v<decltype(r), int&>);          // T0 = int&
    static_assert(std::is_same_v<decltype(s), std::string>);   // T1 = std::string
    r = 99;               // 修改的是 i
    return i == 99 ? 0 : 1;
}
```

### `decltype` 的特殊规则

[[dcl.type.decltype#1]] 第 1.1 项：`decltype(x)`（x 是**不带括号**的、命名结构化绑定的 id-expression）给出的是**被引用类型**。所以上面 `decltype(s)` 是 `std::string` 而不是 `std::string&&`（*r₁* 的类型），尽管底层确实是一个右值引用变量。加括号 `decltype((s))` 则按普通左值规则得到 `std::string&`。

## 协议三：数据成员（¶8）

既不是数组，也没有可用的 `tuple_size`，就走数据成员协议。条件：

1. E 的**所有**非静态数据成员都必须是 E 的**直接成员**，或者都是 E 的**同一个**基类的直接成员；
2. 每个成员在结构化绑定所在的上下文中以 `e.name` 命名时都是良构的——也就是说要**可访问**（C++20 起；C++17 要求全部 public）；
3. E 不能有**匿名联合**成员；
4. 结构化绑定大小 = 非静态数据成员的个数。

按声明顺序把成员记为 m₀, m₁, …，每个 SB*ᵢ* 是一个**左值**的名字，指向 *e* 的成员 m*ᵢ*，类型是 `e.mᵢ` 的类型（[[expr.ref]]，所以会合并 *e* 的 cv 与成员的 `mutable`）。被引用类型：若 m*ᵢ* 声明为引用类型，就是该声明类型；否则是 `e.mᵢ` 的类型。若成员是位域，这个左值也是**位域**。

```cpp title="sb-members.cpp" ok
#include <type_traits>

struct S { mutable int x1 : 2; volatile double y1; };
S f();

void g() {
    const auto [x, y] = f();
    static_assert(std::is_same_v<decltype(x), int>);                    // mutable 抵消了 const
    static_assert(std::is_same_v<decltype(y), const volatile double>);
}

int main() {}
```

各条约束的边界：

```cpp title="sb-members-errors.cpp" error
struct B { int a; };
struct D : B { int b; };
struct OnlyBase : B { };
class Priv { int x; public: int y; friend void friend_ok(); };
struct Anon { union { int u; float f; }; int v; };
union U { int i; };

void f() {
    auto [a1] = OnlyBase{};    // OK: 所有成员都来自同一个基类 B
    auto [a2, b2] = D{};       // error: 成员分散在 D 和 B 中
    auto [x, y] = Priv{};      // error: x 在这里不可访问
    auto [u, v] = Anon{};      // error: 有匿名联合成员
    auto [i] = U{};            // error: 联合不能拆（[dcl.pre]/7）
}

void friend_ok() {
    auto [x, y] = Priv{};      // OK (C++20): 友元中 x 可访问
}
```

为什么要求"同一个类"？因为"按声明顺序编号"只有在所有成员都在同一个类中声明时才有明确含义；跨越基类和派生类时，"第 0 个成员是谁"要依赖某种布局约定，标准不愿意规定。

!!! note "位域与引用"
    绑定到位域成员的名字本身就是位域左值，所以 `&x` 非良构，`int& r = x;` 也非良构；但读写 `x` 完全正常。这是"结构化绑定不是引用"的又一个直接后果——如果标准把它定义成 `auto& x = e.x1;`，位域根本无法被绑定。

## 结构化绑定不是变量

[[basic.pre#8]] 把结构化绑定列为一种**独立的实体**，与变量并列。这在很多地方产生可观察的差异：

| 情形 | 普通变量 | 结构化绑定 |
|---|---|---|
| `decltype(x)` | 声明类型 | 被引用类型（[[dcl.type.decltype#1]]） |
| `return x;` 隐式移动 | 是（自动存储期的非 volatile 对象） | **否**：不是"变量"，不满足 [[expr.prim.id.unqual#15]] |
| `extern` 声明 | 可以 | 不可以（说明符只能是上表那几个） |
| lambda 捕获 | 可以 | C++20 起可以（[[P1091R3]]、[[P1381R1]]） |
| 取地址 | 可以 | 可以，除非绑定到位域 |

```cpp title="sb-no-implicit-move.cpp" error
#include <memory>

struct H { std::unique_ptr<int> p; int n; };
H make();

std::unique_ptr<int> f() {
    auto [p, n] = make();
    return p;               // error: p 不是隐式可移动实体，尝试复制 unique_ptr
}

std::unique_ptr<int> g() {
    auto [p, n] = make();
    return std::move(p);    // OK
}
```

### lambda 捕获

C++17 中，结构化绑定**不能被 lambda 捕获**——标准只允许捕获变量。C++20 允许捕获；[[expr.prim.lambda.capture]] 对位域另有一条限制："位域或匿名联合的成员不得按引用捕获"。

```cpp title="sb-capture.cpp" error
struct S { int bf : 3; int v; };

int main() {
    auto [bf, v] = S{1, 2};
    auto l1 = [bf, &v] { return bf + v; };   // OK (C++20)
    auto l2 = [&bf] { return bf; };          // error: 位域不能按引用捕获
    return l1() + l2();
}
```

!!! impl "Clang 的一个偏差"
    上例中 Clang 23 对 `[&bf]` 的诊断是"non-const reference cannot bind to bit-field"。但如果把结构化绑定声明为 `const auto [bf, v]`，Clang 23 会**接受** `[&bf]`——标准的规则不区分 const，按引用捕获位域一律非良构。

## 说明符：`static`、`thread_local`、`constexpr`、`constinit`、属性

### `static` / `thread_local`（C++20）

*S* 中的存储类说明符施加于 *e*（以及 tuple 协议下的各 *rᵢ*）。由于只有 *e* 是对象，一个 `static auto [a, b] = ...;` 只会创建一个静态对象，初始化一次。

```cpp run title="sb-static.cpp" ok
#include <cstdio>
#include <utility>

std::pair<int, int> next() {
    static int n = 0;
    ++n;
    return {n, n * 10};
}

void f() {
    static auto [a, b] = next();   // 只在第一次调用 f 时初始化
    std::printf("%d %d\n", a, b);
}

int main() { f(); f(); }   // 两次都打印 1 10
```

### `constexpr` 与 `constinit` {{c++26}}

[[dcl.constexpr#1]] 允许 `constexpr` 用于结构化绑定声明（[[P2686R5]]）。`constexpr` 施加于 *e*（和各 *rᵢ*），于是 *e* 必须是常量初始化的；结构化绑定随后可以用于常量表达式。

```cpp title="sb-constexpr.cpp" ok
#include <array>
#include <utility>

constexpr auto [a, b] = std::pair{1, 2.5};      // C++26
static_assert(a == 1 && b == 2.5);

constinit auto [c, d] = std::pair{3, 4};        // C++26

constexpr std::array<int, 3> arr{1, 2, 3};
constexpr auto& [x, y, z] = arr;
static_assert(y == 2);

struct P { int x, y; };
void f() {
    constexpr auto [p, q] = P{1, 2};            // 数据成员协议：名字直接指向 e 的成员
    static_assert(p + q == 3);
}

int main() {}
```

在 C++26 之前，唯一的选择是先 `constexpr auto t = ...;` 再逐个取。

!!! impl "块作用域 + tuple 协议"
    在块作用域中写 `constexpr auto [p, q] = std::pair{1, 2};`，tuple 协议会引入 `constexpr int&& r0 = get<0>(xvalue e);` 这样的**引用**，指向一个自动存储期对象。C++26 同一提案修改了常量表达式中引用/指针的规则：自动对象若对当前程序点是**可被 constexpr 引用**的（[[expr.const.init#2]]，大意是位于同一次函数调用中），就可以作为常量表达式结果所引用的对象。因此按当前草案这是良构的。截至写作时，Clang 23 拒绝它（诊断"address of non-static constexpr variable may differ on each invocation"，并建议加 `static`）；把声明改成 `static constexpr` 可以通过。数组和数据成员协议不引入引用，Clang 接受。

### 属性 {{c++26}}

¶1：每个 *sb-identifier* 后可以跟 *attribute-specifier-seq*，它**属于对应的结构化绑定**（[[P0609R3]]）。最典型的用途是对单个名字标 `[[maybe_unused]]`：

```cpp title="sb-attr.cpp" ok
#include <map>
#include <string>

int count_values(const std::map<std::string, int>& m) {
    int total = 0;
    for (const auto& [key [[maybe_unused]], value] : m)
        total += value;
    return total;
}

int main() {}
```

在此之前只能把 `[[maybe_unused]]` 加在整个声明上（[[dcl.attr.unused#2]] 允许它用于结构化绑定声明），压制全部警告。[[dcl.attr.unused#4]] 还建议：未标记的结构化绑定声明，只有当**所有**绑定都未使用时才应警告。

C++26 还引入了占位符名 `_`（名字无关声明，[[basic.scope.scope]]），在结构化绑定中可以重复使用：`auto [_, value, _] = triple;`。

## 与其他特性的配合

- **范围 `for`**：`for (auto& [k, v] : map)`——*for-range-declaration* 可以是结构化绑定声明，每次迭代用 `*__begin` 初始化一个新的 *e*（[[stmt.ranged]]）。
- **展开语句** {{c++26}}：`template for (auto x : tup)` 中解构式展开用的是结构化绑定大小及同样的协议（[[stmt.expand]]）。
- **标准库的 tuple-like 类型**：`std::pair`、`std::tuple`、`std::array`、`std::subrange`、`std::complex`（C++26）都提供了 `tuple_size` / `tuple_element` / `get`。

## 实现视角

!!! impl "*e* 在目标代码中"
    - *e* 是一个真实的对象（或引用）。在 Itanium C++ ABI 中，命名空间作用域的结构化绑定声明的 *e* 需要一个链接名；GCC 和 Clang 用 `_ZDC` 开头的"分解声明"（decomposition declaration）修饰名为其编码，例如 `auto [a, b] = ...;` 在全局作用域会产生形如 `_ZDC1a1bE` 的符号。函数内的 `static` 结构化绑定也有链接名（Clang 生成 `_ZZ1fvEDC1c1dE` 这样的局部静态名），若需要动态初始化还会配一个守卫变量。
    - 对数据成员协议，绑定名在编译器内部是"指向 *e* 成员的表达式"的别名，不分配任何额外存储；调试器中通常能看到 *e*（以合成名字显示）和各个绑定。
    - 对 tuple 协议，*rᵢ* 是真实的引用变量；优化后通常与直接调用 `get` 没有区别。

## 历史与演进

!!! history "C++17 → C++26"
    - **C++17**：引入结构化绑定（[[P0217R3]]；提案阶段曾称为"decomposition declaration"，ABI 的 `DC` 修饰名即源于此）。限制：说明符只有 `auto` 和 cv、引用；数据成员必须全部 public；不能 `static`/`thread_local`/`constexpr`；不能被 lambda 捕获；任何名为 `get` 的成员都会触发成员形式。
    - **C++20**：放宽 `get` 成员查找规则（[[P0961R1]]）；数据成员只需在上下文中**可访问**（[[P0969R0]]）；允许 `static`、`thread_local` 和 lambda 捕获（[[P1091R3]]、[[P1381R1]]）。
    - **C++26**：结构化绑定可以带属性（[[P0609R3]]）；可以作为 `if`/`while`/`switch` 的条件（[[P0963R3]]）；引入结构化绑定包（[[P1061R10]]）；允许 `constexpr`（[[P2686R5]]）；占位符 `_` 可以在同一声明中重复出现。
    - 特性测试宏 `__cpp_structured_bindings`：Clang 23 在 `-std=c++2c` 下报告 `202411L`。

## 陷阱

!!! pitfall "`const auto& [a, b]` 并不保证 a、b 不可修改"
    cv 和引用修饰的是 *e*。引用成员（数据成员协议）或 `tuple_element` 本身是引用类型（如 `std::tuple<int&>`）时，绑定仍然可以写穿到外部对象。

!!! pitfall "按值拆 tuple 时 get 收到的是 xvalue"
    `auto [s] = std::tuple<std::string>{...};` 中 *e* 是对象，以 xvalue 调用 `get`，得到 `std::string&&`，*r₀* 是右值引用——但它引用的是 *e* 内部的字符串，并没有发生移动。只有当你自己的 `get(T&&)` 返回**纯右值**（即在 `get` 中移动构造一个新对象）时，才会真正移走分量。

!!! pitfall "结构化绑定不能直接 `return` 移动"
    见上面的 `unique_ptr` 例子：要么 `return std::move(p);`，要么改用普通变量。

!!! pitfall "`auto [a, b] = {1, 2};` 不是 initializer_list 的拆解"
    初始化器不允许是花括号列表；`auto [a, b]{x}` 中花括号里只能有一个表达式。

## 思考题

!!! question "思考题 1"
    下面的程序输出什么？为什么？

    ```cpp
    #include <cstdio>
    struct P { int x, y; };
    int main() {
        P p{1, 2};
        auto [a, b] = p;
        auto& [c, d] = p;
        a = 10; c = 20;
        std::printf("%d %d %d\n", p.x, a, c);
    }
    ```

<details markdown="1">
<summary>答案</summary>

输出 `20 10 20`。第一个声明的 *e* 是 `p` 的副本，`a` 指向副本的 `x`；第二个声明的 *e* 是 `P&`，`c` 指向 `p.x` 本身。所以 `a = 10` 只改副本，`c = 20` 改了 `p.x`。
</details>

!!! question "思考题 2"
    一个类 `Handle` 有成员函数 `int* get() const;`，作者又为它特化了 `std::tuple_size` / `std::tuple_element`，并在同一命名空间里提供了自由函数模板 `template<std::size_t I> auto get(const Handle&)`。在 C++17 和 C++20 中 `auto [a, b] = h;` 分别会怎样？

<details markdown="1">
<summary>答案</summary>

C++17：在 `Handle` 中找到名为 `get` 的成员，于是使用 `e.get<i>()`；但成员 `get` 不是模板，`e.get<0>()` 非良构。C++20 起（¶7）：成员查找必须找到"首个模板形参是常量模板形参的函数模板"才用成员形式；`int* get() const` 不是模板，于是退回 `get<i>(e)` + ADL，找到自由函数模板，良构。
</details>

!!! question "思考题 3"
    `struct S { int a; }; const S s{1};` 之后，`auto& [x] = s; x = 2;` 是否良构？`auto [y] = s; y = 2;` 呢？

<details markdown="1">
<summary>答案</summary>

`auto& [x] = s;`：*e* 是 `auto&` 推导出的 `const S&`，`x` 是 `e.a`，类型 `const int`，所以 `x = 2` 非良构。`auto [y] = s;`：*e* 是 `S` 的**非 const 副本**（`auto` 推导丢弃顶层 const），`y` 的类型是 `int`，`y = 2` 良构，修改的是副本。
</details>

## 小结

!!! summary "要点"
    - 只有一个真实变量 *e*；cv、`&`/`&&`、`static`、`constexpr` 等全部作用于 *e*（tuple 协议下也作用于各 *rᵢ*）。
    - 三种协议按顺序尝试：**数组** → **tuple-like**（`tuple_size<E>` 完整且有 `value`）→ **数据成员**（全部在同一个类、可访问、无匿名联合）。
    - tuple-like 协议中 `get` 先找"首个模板形参为常量形参"的成员模板，否则 **仅 ADL**；*e* 为非引用时以 xvalue 调用。
    - 绑定名是左值；`decltype` 给出被引用类型；不是变量，所以不隐式移动。
    - C++26：属性、条件、绑定包（只能在模板化实体中）、`constexpr`/`constinit`。

| 协议 | 触发条件 | SB*ᵢ* 指向 | 被引用类型 | 额外变量 |
|---|---|---|---|---|
| 数组 | E 是有界数组 | *e*[*i*] | T | 无 |
| tuple-like | `tuple_size<E>::value` 存在 | *rᵢ* 绑定的对象 | `tuple_element<i,E>::type` | *rᵢ* |
| 数据成员 | 其他类类型 | *e*.m*ᵢ* | 成员声明类型（引用）或 `e.mᵢ` 的类型 | 无 |
