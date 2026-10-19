---
title: 结构化绑定声明
summary: auto [x, y] = expr 只声明了一个隐藏变量 e，x、y 是指向 e 的各部分的名字；e 按数组、tuple-like、数据成员三种方式之一拆开。
status: done
papers: P0217R3, P0961R1, P0969R0, P1091R3, P1381R1, P0609R3, P0963R3, P1061R10, P2686R5
related: dcl.pre, dcl.type.decltype, temp.variadic, stmt.pre, stmt.expand, expr.prim.lambda.capture, expr.prim.id.unqual, class.member.lookup, basic.lookup.argdep, tuple.helper
tags: 声明, 结构化绑定, tuple, 参数包
updated: 2026-10-19
---

!!! tldr
    - `auto [x, y] = p;` 只声明了一个变量：无名的 *e*，用 `p` 初始化。`x`、`y` 是指向 *e* 的各部分的名字，既不是变量也不是引用。
    - 声明里的 `auto`、`const`、`&`、`static`、`constexpr` 都作用于 *e*，不作用于各个名字。
    - *e* 按顺序尝试三种拆法：数组；`std::tuple_size<E>` 有 `value` 时按 tuple-like 拆，用 `get<i>`；否则按非静态数据成员拆。
    - `decltype(x)` 给出被引用类型；`return x;` 不会隐式移动，因为 `x` 不是变量。
    - C++26 起可以写 `constexpr`、给单个名字加属性、放进 `if` 的条件，还可以在模板里用 `[first, ...rest]` 这样的绑定包。

## 隐藏变量 *e*（¶1）

```cpp run title="hidden-e.cpp" ok
#include <cassert>

struct P { int x, y; };

int main() {
    P p{1, 2};

    auto [a, b] = p;        // e 是 p 的副本：P e = p;
    a = 100;
    assert(p.x == 1);       // 原对象不变

    auto& [c, d] = p;       // e 是引用：P& e = p;
    c = 100;
    assert(p.x == 100);     // 通过 e 修改了 p

    int arr[2] = {3, 4};
    auto [u, v] = arr;      // e 是 int[2]，逐元素复制
    u = 0;
    assert(arr[0] == 3);
}
```

`auto [a, b] = p;` 看起来像声明了两个变量，用 `p.x` 和 `p.y` 初始化。标准的规定不是这样。

¶1 结构化绑定声明先引入一个名字唯一、程序里写不出来的变量 *e*。它的声明就是把方括号部分换成 *e*，其余照抄：`auto [a, b] = p;` 相当于 `auto e = p;`，`auto& [c, d] = p;` 相当于 `auto& e = p;`。这个声明永远不会被解释成函数声明，所以 `auto [a, b](x);` 也没有歧义。

然后，方括号里的每个名字成为一个[[g:structured-binding|结构化绑定]]（structured binding），指代 *e* 的一个元素或成员。所以上面改 `a` 不影响 `p`：改的是副本 *e*。

按值拆数组是例外。数组不能整体复制，`auto` 推导又会让数组退化成指针，所以初始化表达式是数组且没有 `&` 时，*e* 直接声明为同样的数组类型，逐个元素初始化。

*e* 这个 id-expression 的类型记作 E。注 1 指出，E 永远不是引用类型，因为表达式的类型会去掉引用（[[expr.prop]]）：`auto& [c, d] = p;` 里 *e* 是 `P&`，E 是 `P`。

### 修饰符作用于 *e*

¶1 把 *decl-specifier-seq* 里的 cv 限定记作 *cv*，把 `constexpr`、`constinit`、`static`、`thread_local` 记作 *S*。它们和 `&`、`&&` 一样，修饰的都是 *e*：

```cpp title="const-applies-to-e.cpp" ok
#include <type_traits>

struct S { int& r; int v; };

void f(int& i) {
    const auto [r, v] = S{i, 1};     // const 加在 e 上：const S e = S{i, 1};
    static_assert(std::is_same_v<decltype(v), const int>);   // e.v 是 const int
    static_assert(std::is_same_v<decltype(r), int&>);        // 引用成员
    r = 42;                           // OK: const 不传到引用所指的对象
}

int main() { int i = 0; f(i); }
```

`const auto [r, v]` 没有让 `r` 变成 const。`r` 指代 *e* 的引用成员 `r`，通过 const 对象的引用成员仍然可以修改被引用的对象。`volatile` 出现在 *cv* 里已经弃用（[[depr.volatile.type]]）。

*e* 是普通的变量或引用，所以临时对象的生命周期规则（[[class.temporary]]）照常适用：

```cpp title="lifetime-ext.cpp" error
#include <string>
#include <utility>

std::pair<std::string, int> make();

void f() {
    auto&& [s1, n1] = make();        // OK: e 是右值引用，临时对象活到 e 的作用域结束
    const auto& [s2, n2] = make();   // OK: 同理
    auto& [s3, n3] = make();         // error: 非 const 左值引用不能绑定纯右值
}
```

### 能写哪些说明符（[[dcl.pre#7]]）

| 约束 | 内容 |
|---|---|
| 说明符 | 只能是 `constexpr`、`constinit`、`static`、`thread_local`、`auto`、cv 限定 |
| 类型 | 必须是不受约束的 `auto`，不能写 `C auto`、`decltype(auto)` 或具体类型 |
| 初始化器 | `= expr`、`{ expr }`、`( expr )` 三种之一，都只能有一个表达式 |
| 初始化表达式 | 数组或非联合类类型；放在条件里时只能是非联合类类型 |

```cpp title="sb-specifiers.cpp" error
#include <utility>
template<class T> concept C = true;

void f() {
    auto [a, b] = std::pair{1, 2};               // OK
    static auto [e1, e2] = std::pair{1, 2};      // OK (C++20)
    C auto [g, h] = std::pair{1, 2};             // error: 受约束的占位符
    int [i, j] = std::pair{1, 2};                // error: 必须用 auto
    auto [k, l] = {1, 2};                        // error: 初始化器不能是花括号列表
    auto [m] = 42;                               // error: int 既不是数组也不是类
}
```

`auto [k, l]{p};` 是允许的，花括号里只有一个表达式。`= {1, 2}` 不行，因为 `=` 后面必须是一个表达式。Clang 23 的处理是先把 *e* 推导成 `std::initializer_list<int>`，再报告无法绑定它的私有成员，结论相同，理由与标准不同。

## 三种拆法

E 决定 *e* 怎样拆开，按下面的顺序尝试：

| 拆法 | 条件 | SB*ᵢ* 指代 | 被引用类型 | 额外变量 |
|---|---|---|---|---|
| 数组（¶6） | E 是有界数组 | *e* 的第 *i* 个元素 | 元素类型 | 无 |
| tuple-like（¶7） | `tuple_size<E>` 有成员 `value` | *rᵢ* 绑定的对象 | `tuple_element<i, E>::type` | *rᵢ* |
| 数据成员（¶8） | 其他类类型 | *e* 的第 *i* 个成员 | 成员的声明类型（引用）或 `e.mᵢ` 的类型 | 无 |

每种拆法都给出 E 的[[g:structured-binding-size|结构化绑定大小]]（structured binding size），即要引入几个绑定（¶2）。没有绑定包时，方括号里的名字个数必须恰好等于它。SB*ᵢ* 表示第 *i* 个结构化绑定（¶3）。

每个绑定还有一个[[g:referenced-type|被引用类型]]（referenced type）。不带括号的 `decltype(x)` 给出的就是它（[[dcl.type.decltype#1]] 第 1.1 项），而不是某个变量的声明类型。

### 数组（¶6）

¶6 E 不能是未知边界数组。E 是其他数组类型时，绑定大小就是元素个数，SB*ᵢ* 是指代第 *i* 个元素的左值，类型和被引用类型都是元素类型 T。注 3 指出，T 的顶层 cv 就是声明里的 *cv*。

```cpp title="sb-array.cpp" ok
auto f() -> int(&)[2];

void k() {
    auto [x, y] = f();       // e 是 int[2]，从 f() 返回的数组逐元素复制
    auto& [xr, yr] = f();    // e 是 int(&)[2]，xr、yr 指代 f 返回的那个数组
    (void)x; (void)y; (void)xr; (void)yr;
}

int main() {}
```

```cpp title="sb-array-unknown.cpp" error
extern int arr[];
void f() {
    auto& [a, b] = arr;   // error: E 不能是未知边界数组
}
```

### tuple-like（¶7）

用户自定义的类想隐藏数据成员，或者想暴露计算出来的分量，就走这一条。

¶7 E 不是数组，而 `std::tuple_size<E>` 是一个完整的类类型、并且有名为 `value` 的成员时，使用 tuple-like 协议。`tuple_size<E>::value` 必须是非负的整型常量表达式，它就是绑定大小。只声明了主模板、或者特化里没有 `value`，都不会进入这条路，而是落到数据成员协议。

每个元素的初始化器这样确定（*i* 是 `std::size_t` 类型的下标）：

- 在 E 的作用域里查找名字 `get`。如果找到至少一个函数模板，它的第一个模板形参是常量模板形参（非类型模板形参），初始化器就是 `e.get<i>()`；
- 否则初始化器是 `get<i>(e)`，`get` 只通过实参依赖查找（ADL，[[basic.lookup.argdep]]）找，不做普通的无限定查找（注 4）。

两种情况下 `get<i>` 都按模板名解析，`<` 不会被当成小于号。

```cpp run title="sb-tuple-like.cpp" ok
#include <cstddef>
#include <tuple>
#include <type_traits>
#include <utility>

namespace lib {
    struct Point {
        int x, y;
        int get() const { return 42; }   // 非模板的成员 get：不算数，不妨碍 ADL
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
    static_assert(std::is_same_v<decltype(a), int>);   // 被引用类型 int
    return p.x == 10 ? 0 : 1;
}
```

C++17 的规则是只要类里有任何名为 `get` 的成员就用成员形式。许多类本来就有一个与 tuple 无关的 `get()`，比如智能指针，它们一旦想支持结构化绑定，`e.get<0>()` 就编译失败。C++20 的 [[P0961R1]] 改成只认形如 `get<I>` 的成员模板。

!!! lawyer "`template<class T> T get()` 也不算"
    第一个模板形参是类型形参的成员 `get`（像 `std::get<T>` 那样）不满足条件，不妨碍 ADL。反过来，只要类里有一个满足条件的成员模板 `get`，就用成员形式，即使它对当前的 *i* 根本调用不了，也不会退回 ADL。

接下来确定每个元素绑在什么上。如果实体 *e* 的类型是左值引用，表达式 *e* 是左值，否则是 xvalue。所以 `auto [a, b] = t;` 以 xvalue 调用 `get`，`auto& [a, b] = t;` 以左值调用。

令 T*ᵢ* 为 `std::tuple_element<i, E>::type`。标准引入一组变量 `S Uᵢ rᵢ = 初始化器;`，U*ᵢ* 由初始化器的值类别决定：纯右值时是 T*ᵢ*，左值时是 `Tᵢ&`，xvalue 时是 `Tᵢ&&`。SB*ᵢ* 是类型为 T*ᵢ* 的左值，指代 *rᵢ* 绑定的对象，被引用类型是 T*ᵢ*。

和另外两种拆法不同，这里确实创建了变量 *rᵢ*，通常是引用。`get` 返回纯右值时，*rᵢ* 是一个独立的对象，SB*ᵢ* 指代它而不是 *e* 的一部分。*S* 里的 `static`、`constexpr` 等也施加于每个 *rᵢ*。*e* 先初始化，然后 *r₀*、*r₁*…… 依次初始化。

```cpp run title="sb-tuple-ref.cpp" ok
#include <string>
#include <tuple>
#include <type_traits>

int main() {
    int i = 0;
    std::tuple<int&, std::string> t{i, "hi"};
    auto [r, s] = t;      // e 是 t 的副本，但它的第 0 个元素仍然引用 i
    static_assert(std::is_same_v<decltype(r), int&>);          // T0 = int&
    static_assert(std::is_same_v<decltype(s), std::string>);   // T1 = std::string
    static_assert(std::is_same_v<decltype((s)), std::string&>);
    r = 99;               // 修改的是 i
    return i == 99 ? 0 : 1;
}
```

`decltype(s)` 是被引用类型 `std::string`，不是 *r₁* 的类型 `std::string&&`。加了括号的 `decltype((s))` 按普通左值表达式处理，得到 `std::string&`。

### 数据成员（¶8）

¶8 既不是数组也没有可用的 `tuple_size` 时，按非静态数据成员拆。条件是：

1. E 的所有非静态数据成员都是 E 的直接成员，或者都是 E 的同一个基类的直接成员；
2. 每个成员在结构化绑定所在的位置写成 `e.name` 都是良构的，也就是可以访问；
3. E 没有匿名联合成员。

绑定大小就是非静态数据成员的个数。按声明顺序记成员为 m₀、m₁……，SB*ᵢ* 是指代 *e* 的成员 m*ᵢ* 的左值，类型是 `e.mᵢ` 的类型（[[expr.ref]]），所以会合并 *e* 的 cv 和成员的 `mutable`。被引用类型在成员声明为引用时是那个声明类型，否则是 `e.mᵢ` 的类型。成员是位域时，这个左值也是位域。

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
    auto [x, y] = Priv{};      // OK: 友元中 x 可以访问
}
```

成员必须集中在同一个类里，是因为只有这样按声明顺序编号才有明确的含义。成员分散在基类和派生类里时，谁是第 0 个就要依赖某种布局约定，标准没有规定这种约定。可访问性的要求是 C++20 的 [[P0969R0]] 放宽的，C++17 要求所有成员都是 public。

## 结构化绑定不是变量

[[basic.pre#8]] 把结构化绑定列为与变量并列的另一种实体。这在几处有看得见的差别：

| 情形 | 普通变量 | 结构化绑定 |
|---|---|---|
| `decltype(x)` | 声明类型 | 被引用类型 |
| `return x;` 隐式移动 | 会（自动存储期的非 volatile 对象） | 不会，它不是[[expr.prim.id.unqual#15\|隐式可移动实体]] |
| lambda 捕获 | 可以 | C++20 起可以（[[P1091R3]]、[[P1381R1]]） |
| 取地址、绑定引用 | 可以 | 可以，绑定到位域时不行 |

```cpp title="sb-no-implicit-move.cpp" error
#include <memory>

struct H { std::unique_ptr<int> p; int n; };
H make();

std::unique_ptr<int> f() {
    auto [p, n] = make();
    return p;               // error: 不会隐式移动，尝试复制 unique_ptr
}

std::unique_ptr<int> g() {
    auto [p, n] = make();
    return std::move(p);    // OK
}
```

位域的情况也来自同一个模型。如果标准把绑定定义成 `auto& x = e.x1;`，位域根本绑不上；现在绑定名本身就是一个位域左值，读写正常，只是不能取地址，也不能绑定到非 const 引用。

lambda 按引用捕获位域是非良构的（[[expr.prim.lambda.capture]]），对结构化绑定同样适用：

```cpp title="sb-capture.cpp" error
struct S { int bf : 3; int v; };

int main() {
    auto [bf, v] = S{1, 2};
    auto l1 = [bf, &v] { return bf + v; };   // OK (C++20)
    auto l2 = [&bf] { return bf; };          // error: 位域不能按引用捕获
    return l1() + l2();
}
```

!!! impl "Clang 的偏差"
    Clang 23 对上例 `[&bf]` 的诊断是 "non-const reference cannot bind to bit-field"。如果声明改成 `const auto [bf, v]`，Clang 23 会接受 `[&bf]`。标准的规则不区分 const，按引用捕获位域一律非良构。

## 初始化器不能用自己引入的名字（¶5）

¶5 初始化器里用到了本声明引入的名字，程序非良构。

```cpp title="sb-self-ref.cpp" error
struct P { int x, y; };
void f() {
    auto [a, b] = (a, P{});   // error: 初始化器中使用了 a
}
```

普通变量的声明点在声明符之后，`int x = x;` 能编译（[[basic.scope.pdecl]]）。结构化绑定指代的是 *e* 的一部分，而 *e* 要等初始化器求值完才存在，在初始化器里使用它没有合理的含义，所以直接禁止。

## 结构化绑定包（¶1–¶3）{{c++26}}

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

¶1 名字前带 `...` 时，它引入一个[[g:structured-binding-pack|结构化绑定包]]（[[temp.variadic#4]]），包里的每个元素是一个结构化绑定。它和函数形参包一样，可以展开、用 `sizeof...` 计数、用在折叠表达式里。

¶2 有绑定包时，其余名字的个数不能超过绑定大小，剩下的全归入包，包可以是空的。包可以出现在任何位置（¶3 的标准例子）：

```cpp title="sb-pack-positions.cpp" ok
struct C { int x, y, z; };

template<class T>
void now_i_know_my() {
    auto [a, b, c] = C();          // SB0=a, SB1=b, SB2=c
    auto [d, ...e] = C();          // 包 e 含 SB1、SB2
    auto [...f, g] = C();          // 包 f 含 SB0、SB1；g 是 SB2
    auto [h, i, j, ...k] = C();    // k 是空包
    // auto [l, m, n, o, ...p] = C();   // error: 结构化绑定大小不够
}

int main() { now_i_know_my<int>(); }
```

[[dcl.pre#7]] 规定，一个声明里最多一个包，而且含包的声明必须声明一个[[g:templated-entity|模板化实体]]，也就是只能出现在模板、泛型 lambda 这类模板化的上下文里。包展开的整套机制建立在实例化时才确定元素个数的前提上，在非模板代码里支持它对实现的负担很大，提案在演进中因此收窄了范围。

```cpp title="sb-pack-nontemplate.cpp" error
struct P { int x, y; };
void f() {
    auto [...xs] = P{};   // error: 含绑定包的声明必须是模板化实体
}
```

Clang 23 对此报告 "pack declaration outside of template"。

## 放在条件里（¶4）{{c++26}}

¶4 结构化绑定声明作为 `if`、`while`、`switch` 的条件时，条件的[[g:decision-variable|判定变量]]是 *e*（[[stmt.pre]]）。`if (auto [a, b] = expr)` 判断的是 *e* 按上下文转换成 `bool` 的结果，而不是某个绑定的值。

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
    if (auto [v, ok] = parse("42"))      // 判定的是 e，调用 operator bool
        std::printf("v=%d ok=%d\n", v, ok);
}
// 输出：operator bool / get<0> / get<1> / v=42 ok=1
```

输出的顺序由 ¶7 末尾保证：*e* 的初始化和把 *e* 当作判定变量的转换，都先于任何 *rᵢ* 的初始化。`expected` 这类类型往往只有在成功时才能安全地取出分量，先判断再拆就不会在失败状态下调用 `get`。条件里的初始化表达式只能是非联合类类型，数组不能转换成 `bool`。

## static、constexpr 与属性

### static 与 thread_local

C++20 起，`static` 和 `thread_local` 施加于 *e* 以及 tuple-like 协议下的各个 *rᵢ*。只有 *e* 是对象，所以 `static auto [a, b] = ...;` 只创建一个静态对象，只初始化一次：

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

### constexpr 与 constinit {{c++26}}

C++26 起（[[P2686R5]]），`constexpr` 和 `constinit` 同样施加于 *e* 和各 *rᵢ*，于是 *e* 必须常量初始化，绑定随后可以用在常量表达式里。此前只能先写 `constexpr auto t = ...;` 再逐个取。

```cpp title="sb-constexpr.cpp" ok
#include <array>
#include <utility>

constexpr auto [a, b] = std::pair{1, 2.5};
static_assert(a == 1 && b == 2.5);

constinit auto [c, d] = std::pair{3, 4};

constexpr std::array<int, 3> arr{1, 2, 3};
constexpr auto& [x, y, z] = arr;
static_assert(y == 2);

struct P { int x, y; };
void f() {
    constexpr auto [p, q] = P{1, 2};            // 数据成员协议：名字直接指代 e 的成员
    static_assert(p + q == 3);
}

int main() {}
```

!!! impl "块作用域里按 tuple-like 协议拆"
    在函数里写 `constexpr auto [p, q] = std::pair{1, 2};`，tuple-like 协议会引入 `constexpr int&& r0 = get<0>(std::move(e));` 这样的引用，指向一个自动存储期对象。同一提案修改了常量表达式里引用的规则：自动对象如果从当前位置看是 constexpr-referenceable 的（[[expr.const.init#2]]，大致是同一次函数调用之内），就可以被常量表达式的结果引用。所以按当前草案这是良构的。

    Clang 23 拒绝它，提示 "address of non-static constexpr variable may differ on each invocation" 并建议加 `static`；改成 `static constexpr` 可以通过。数组和数据成员协议不引入引用，Clang 接受。

### 属性 {{c++26}}

C++26 起（[[P0609R3]]），每个名字后面可以跟一个属性列表，只属于那一个绑定。最常见的用法是只给不用的那个名字标 `[[maybe_unused]]`：

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

此前只能把 `[[maybe_unused]]` 加在整个声明上（[[dcl.attr.unused#2]]），所有名字一起压制。[[dcl.attr.unused#4]] 还建议，没有标记的结构化绑定声明只在所有绑定都没用到时才警告。C++26 的占位符名 `_` 也可以在同一个结构化绑定声明里重复出现：`auto [_, value, _] = triple;`（[[basic.scope.scope]]）。

## 与其他特性的配合

- 范围 `for`：`for (auto& [k, v] : m)` 每次迭代都用 `*__begin` 初始化一个新的 *e*（[[stmt.ranged]]）。
- 展开语句 {{c++26}}：`template for` 按解构方式展开时，用的是同样的结构化绑定大小和拆法（[[stmt.expand]]）。
- 标准库的 `std::pair`、`std::tuple`、`std::array`、`std::ranges::subrange`，以及 C++26 起的 `std::complex`，都提供了 `tuple_size`、`tuple_element` 和 `get`。

!!! impl "*e* 在目标代码中"
    - *e* 是真实的对象或引用。在 Itanium C++ ABI 中，命名空间作用域的 *e* 需要一个链接名，以 `_ZDC` 开头，后面是各个绑定名：本机 Clang 23 对全局的 `auto [ga, gb] = ...;` 生成 `_ZDC2ga2gbE`。DC 来自提案阶段的名字 decomposition declaration。
    - 数据成员协议下，绑定名只是指向 *e* 成员的别名，不占额外存储；调试器里通常能看到 *e*（显示为合成的名字）和各个绑定。
    - tuple-like 协议下，*rᵢ* 是真实的引用变量，优化后与直接调用 `get` 没有区别。

## 历史与演进

!!! history
    - C++17 引入结构化绑定（[[P0217R3]]）。最初只能用 `auto`、cv 和引用；数据成员必须全部 public；不能 `static`、`thread_local`、`constexpr`；不能被 lambda 捕获；类里有任何名为 `get` 的成员都会触发成员形式。
    - C++20 修正了 `get` 的查找（[[P0961R1]]），数据成员只需可以访问（[[P0969R0]]），允许 `static`、`thread_local` 和 lambda 捕获（[[P1091R3]]、[[P1381R1]]）。
    - C++26 允许给单个绑定加属性（[[P0609R3]]）、放进条件（[[P0963R3]]）、使用绑定包（[[P1061R10]]）、声明为 `constexpr`（[[P2686R5]]）。本机 Clang 23 在 `-std=c++2c` 下的 `__cpp_structured_bindings` 是 `202411L`。

## 常见误解

!!! pitfall "`const auto& [a, b]` 保证 a、b 不可修改"
    cv 和引用修饰的是 *e*。成员本身是引用（数据成员协议），或者 `tuple_element` 是引用类型（如 `std::tuple<int&>`）时，通过绑定仍然可以写到外部对象。

!!! pitfall "按值拆 tuple 时分量会被移走"
    `auto [s] = std::tuple<std::string>{...};` 中 *e* 是对象，以 xvalue 调用 `get`，得到 `std::string&&`，*r₀* 是右值引用。它引用的是 *e* 里面的字符串，没有发生任何移动。只有自己写的 `get(T&&)` 返回纯右值、在里面移动构造新对象时，分量才真的被移走。

!!! pitfall "`return x;` 会像普通局部变量那样移动"
    结构化绑定不是变量，不会隐式移动。要移动就写 `return std::move(x);`，或者改用普通变量。

## 思考题

!!! question "思考题 1"
    下面的程序输出什么？

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

输出 `20 10 20`。第一个声明的 *e* 是 `p` 的副本，`a` 指代副本的 `x`；第二个声明的 *e* 是 `P&`，`c` 指代 `p.x` 本身。所以 `a = 10` 只改副本，`c = 20` 改了 `p.x`。
</details>

!!! question "思考题 2"
    类 `Handle` 有成员函数 `int* get() const;`，作者又为它特化了 `std::tuple_size`、`std::tuple_element`，并在同一命名空间里提供了自由函数模板 `template<std::size_t I> auto get(const Handle&)`。在 C++17 和 C++20 中，`auto [a, b] = h;` 分别会怎样？

<details markdown="1">
<summary>答案</summary>

C++17 中，在 `Handle` 里找到了名为 `get` 的成员，于是用 `e.get<i>()`；但成员 `get` 不是模板，`e.get<0>()` 非良构。C++20 起（¶7），只有找到第一个模板形参是常量模板形参的成员函数模板才用成员形式；`int* get() const` 不是模板，于是改用 `get<i>(e)` 并通过 ADL 找到自由函数模板，良构。
</details>

!!! question "思考题 3"
    `struct S { int a; }; const S s{1};` 之后，`auto& [x] = s; x = 2;` 良构吗？`auto [y] = s; y = 2;` 呢？

<details markdown="1">
<summary>答案</summary>

`auto& [x] = s;` 中 *e* 推导为 `const S&`，`x` 指代 `e.a`，类型是 `const int`，所以 `x = 2` 非良构。`auto [y] = s;` 中 `auto` 推导丢掉顶层 const，*e* 是非 const 的 `S` 副本，`y` 的类型是 `int`，`y = 2` 良构，改的是副本。
</details>
