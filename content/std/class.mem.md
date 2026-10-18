---
title: 类成员
summary: 成员规格的语法与约束、直接成员与用户声明、完整类上下文、默认成员初始化器、数据成员的布局顺序、公共初始序列与布局兼容、首成员地址；成员函数（隐式 inline、引用限定、显式对象形参）、静态成员、位域、类专属分配函数、嵌套类
status: draft
covers: class.mem.general, class.mfct, class.mfct.non.static, class.static, class.static.general, class.static.mfct, class.static.data, class.bit, class.free, class.nest
papers: P0847R7, P1847R4
related: class.pre, class.prop, special, class.union, basic.scope.class, expr.prim.this, over.match.funcs, dcl.fct, class.access.nest, basic.def.odr
tags: 类, 成员, 布局, 位域, 静态成员, deducing this
updated: 2026-10-17
---

[[class.pre]] 给出了类定义的外壳 `class-head { member-specification }`；本节规定花括号里面的东西：**成员规格**（member-specification）能声明什么、各种成员的身份与限制、数据成员在对象里如何摆放、以及在类定义内部"类到底完整没有"。

本页覆盖 11.4 中除特殊成员函数和转换以外的全部子条款：

| 子条款 | 内容 | 本页小节 |
|---|---|---|
| [[class.mem.general]] | 成员总则（下文 ¶ 编号均指此条款） | 前半部分 |
| [[class.mfct]]、[[class.mfct.non.static]] | 成员函数、非静态成员函数（以及 [[dcl.fct]] 中的显式对象形参） | "成员函数" |
| [[class.static]] | 静态成员 | "静态成员" |
| [[class.bit]] | 位域 | "位域" |
| [[class.free]] | 类专属的分配/解分配函数 | "类专属 operator new/delete" |
| [[class.nest]] | 嵌套类 | "嵌套类" |

特殊成员函数见 [[special]] 及其子页；转换函数见 [[class.conv]]；联合体见 [[class.union]]。

## 成员规格的语法（¶1–¶2、¶12–¶14）

```text
member-specification:  member-declaration member-specification(可选)
                       access-specifier : member-specification(可选)

member-declaration:    属性(可选) decl-specifier-seq(可选) member-declarator-list(可选) ;
                       function-definition
                       friend-type-declaration          ← friend T; / friend Ts...;
                       using-declaration | using-enum-declaration
                       static_assert-declaration | consteval-block-declaration
                       template-declaration | explicit-specialization | deduction-guide
                       alias-declaration | opaque-enum-declaration | empty-declaration

member-declarator:     declarator virt-specifier-seq(可选) 契约说明符(可选) pure-specifier(可选)
                       declarator requires-clause 契约说明符(可选)
                       declarator brace-or-equal-initializer
                       identifier(可选) 属性(可选) : constant-expression brace-or-equal-initializer(可选)   ← 位域
```

和命名空间作用域的 *simple-declaration* 相比，*member-declarator* 多了几样东西：`override`/`final`（*virt-specifier*）、纯说明符 `= 0`、尾随 *requires-clause*（约束非模板成员函数）、位域宽度。C++26 又加了**函数契约说明符**（`pre`/`post`）{{c++26}}——¶2 规定它只能出现在声明函数的 *member-declarator* 中；以及 *consteval-block-declaration*（`consteval { ... }`）{{c++26}}。

### `= 0` 是纯说明符还是初始化器？（¶1、¶13）

`= 0` 在语法上可以是纯说明符，也可以是 *brace-or-equal-initializer*。¶1 与 ¶13 用**类型**来消歧：若 *declarator-id* 的类型是**函数类型**，`=` 引入纯说明符；否则引入初始化器。标准例 1：

```cpp run title="pure-or-init.cpp" ok
struct S {
    using T = void();
    T * p = 0;          // OK: p 是指针，"= 0" 是初始化器
    virtual T f = 0;    // OK: f 是函数（用函数类型的 typedef 声明），"= 0" 是纯说明符
};

int main() { }
```

注 1 补充：如果成员声明是通过**模板实例化**才获得函数类型的（如 `template<class T> struct X { T m = 0; };` 用 `T = void()` 实例化），程序非良构（[[temp.spec.general]]）——不能指望模板替换把一个初始化器"变成"纯说明符。

### 友元类型声明（¶12）

*friend-type-declaration* 是 `friend` 后跟一个或多个类型说明符的声明，例如 `friend class X;`、`friend T;`。¶12 规定：凡语法上能匹配 *friend-type-declaration* 的成员声明都按它解析。C++26 允许**包展开**：`friend Ts...;` {{c++26}}，一次性把一个模板形参包中的所有类型声明为友元（C++23 及以前只能逐个列出，或借助递归继承）。

```cpp run title="variadic-friend.cpp" ok
template<class... Ts>
class Passkey {
    friend Ts...;           // C++26：包中的每个类型都是友元
    Passkey() = default;
};

struct Alice { static Passkey<Alice, struct Bob> key() { return {}; } };

int main() { (void)Alice::key(); }
```

### 位域宽度的"最长匹配"（¶14）

C++20 允许位域带默认成员初始化器（`int x : 8 = 42;`），这带来了解析歧义：`:` 后面的常量表达式到哪里结束？¶14 规定：取**能在语法上构成 *constant-expression* 的最长记号序列**。标准例 2 改编：

```cpp title="bitfield-parse.cpp" error
int a;
const int b = 0;
struct S {
    int x1 : 8 = 42;               // OK: "= 42" 是初始化器
    int x2 : 8 { 42 };             // OK: "{ 42 }" 是初始化器
    int y1 : true ? 8 : a = 42;    // OK: 整个 "true ? 8 : a = 42" 是宽度，没有初始化器
    int y2 : true ? 8 : b = 42;    // error: 同上被当作宽度，而 b = 42 是给 const int 赋值
    int y3 : (true ? 8 : b) = 42;  // OK: 加括号后 "= 42" 才是初始化器
    int z : 1 || new int { 0 };    // OK: "{ 0 }" 被 new 表达式吞掉，没有初始化器
};
```

`y1` 能通过是因为条件运算符的第三个操作数是 *assignment-expression*，`a = 42` 整个被吞进宽度表达式；它是常量表达式，因为求值走 `true` 分支，根本不会执行 `a = 42`。

## 成员的全集与"直接成员"（¶3–¶6）

¶3：类定义中的 *member-specification* 声明了该类的**全部成员**；**不能在别处添加成员**。这是 C++ 类与某些语言的"开放类"（Ruby 的 monkey patching、C# 的扩展方法、Objective-C 的 category）的根本区别：类的完整成员集合在 `}` 处一次确定，于是布局、虚表、隐式成员都能在此确定。

**直接成员**（direct member）是首先声明于 *X* 的 *member-specification* 中的成员，包括匿名联合体的成员（[[class.union.anon]]）及其直接成员——继承来的成员不是直接成员。成员的种类：数据成员、成员函数（[[class.mfct]]）、嵌套类型、枚举项、成员模板（[[temp.mem]]）及其特化。注 2：静态数据成员模板的特化是静态数据成员，成员函数模板的特化是成员函数，成员类模板的特化是嵌套类。

¶4：以下 *member-declaration* **不**声明新成员：友元声明、推导指引、上述两者的模板声明、`static_assert`、`consteval` 块、*using-declaration*、空声明。（*using-declaration* 把基类成员引入派生类作用域，但不使其成为派生类的**直接**成员。）除此之外的成员声明，所声明的每个实体（无名位域除外）都是类的成员，而且每个这样的声明**必须**至少声明一个成员名或一个无名位域——所以 `struct S { int; };` 是非良构的。

¶4 最后定义了**用户声明的**（user-declared）：由某个 *member-declaration* 声明的直接成员或友元。这个术语是特殊成员函数规则的基石——"如果类没有**用户声明的**复制构造函数……"（[[class.copy.ctor#6]]），注意 `= default` 和 `= delete` 也算用户声明。

```cpp title="member-decls.cpp" error
struct S {
    int;                 // error: 没有声明任何成员名
    int : 4;             // OK: 无名位域
    static_assert(true); // OK: 不声明成员
    ;                    // OK: 空声明
};
```

（Clang 对 `int;` 只给出 `declaration does not declare anything` **警告**——按标准这是非良构的，警告也满足"必须诊断"的要求。）

¶5：**数据成员**是由 *member-declarator* 引入的非函数成员，或匿名联合体的成员；**成员函数**是作为函数的成员；**嵌套类型**是类中声明的类、枚举，以及用 `typedef`/别名声明的任意类型；类中定义的无作用域枚举的**枚举项**也是类的成员。

¶6：用 `static` 声明的数据成员或成员函数是**静态成员**（见下文"静态成员"），其余是**非静态成员**。

## 成员子对象与引用成员（¶7）

¶7 第一句：每个类类型的对象都有一个**唯一的**成员子对象对应它的每个直接非静态数据成员。

第二部分处理**引用成员**的布局：引用本身是否占存储一般是未指定的（[[dcl.ref]]），但作为类成员时，当前草案规定——设想一个与 `C` 相同、只是把每个"`T` 的引用"成员换成"`T` 的指针"的类 `D`；`C` 的完整对象中每个成员子对象的大小、对齐、偏移都与 `D` 中对应的相同，`C` 的大小和对齐也与 `D` 相同。换句话说，**引用成员占的空间与指针完全一样**。这把所有实现事实上的做法写进了标准，使含引用成员的类的 `sizeof` 和布局可以推断。

```cpp run title="ref-member-layout.cpp" ok
struct C { int& r; char c; };
struct D { int* r; char c; };

static_assert(sizeof(C) == sizeof(D));
static_assert(alignof(C) == alignof(D));
int main() { }
```

## 成员不能声明两次（¶8–¶9）

¶8：同一个成员在 *member-specification* 中**不能声明两次**，例外只有：

- ¶8.1 嵌套类或成员类模板可以先声明、后定义；
- ¶8.2 枚举可以先用 *opaque-enum-declaration*（`enum E : int;`）引入，再用 *enum-specifier* 重声明。

这与命名空间作用域不同：在命名空间中，函数可以随意重复声明。注 3 提醒，同一个名字可以表示多个成员函数，只要类型"足够不同"（重载，[[basic.scope.scope]]）。

```cpp title="no-redecl.cpp" error
struct S {
    void f();
    void f();            // error: 成员不能重复声明
    struct N;
    struct N { };        // OK: ¶8.1
    enum E : int;
    enum E : int { A };  // OK: ¶8.2
};
```

¶9：在类定义**外部**对类成员的重声明必须是**定义**、显式特化或显式实例化；且该成员**不能是非静态数据成员**。所以你不能在类外"再声明一次"成员函数（只能定义它），也不能在类外定义非静态数据成员。

```cpp title="out-of-class.cpp" error
struct S {
    void f();
    static int s;
    int m;
};
void S::f() { }          // OK: 定义
int S::s = 0;            // OK: 静态数据成员的定义
void S::f();             // error: 类外重声明必须是定义
int S::m;                // error: 不能在类外重声明非静态数据成员
```

## 完整类上下文（¶10–¶11）

这是本节最重要、也最常被问到的规则。

¶10：类（模板）的**完整类上下文**（complete-class context）是其 *member-specification* 中的：

- ¶10.1 函数体；
- ¶10.2 默认实参；
- ¶10.3 默认模板实参；
- ¶10.4 *noexcept-specifier*；
- ¶10.5 函数契约说明符 {{c++26}}；
- ¶10.6 默认成员初始化器。

注 4：嵌套类（在外围类的 *member-specification* 内定义时）的完整类上下文，也是外围类的完整类上下文。

¶11：类 `C` 在程序点 P 是**完整的**，若 `C` 的定义从 P **可达**（[[module.reach]]），**或者 P 位于 `C` 的完整类上下文中**；否则 `C` 在 P 是不完整的。

### 为什么成员函数体能"看到后面"

直觉上，编译器处理类定义时分两遍：**第一遍**只看成员的**声明**（类型、名字、签名），构造出类的完整成员表；**第二遍**再回头处理那些被"推迟"的部分——即完整类上下文。所以在完整类上下文中：

1. 名字查找能找到**整个类**中的成员，包括在该点之后才声明的（[[basic.scope.class]]、[[class.member.lookup]]）；
2. 类被视为**完整类型**（可以 `sizeof(*this)`、可以定义该类型的局部变量）。

```cpp run title="complete-class-context.cpp" ok
struct S {
    int f() { return g() + sizeof(S); }       // 函数体：可调用后面的 g，S 是完整的
    void h(int x = k) { (void)x; }            // 默认实参：可用后面的静态成员 k
    void n() noexcept(noexcept(g())) { }      // noexcept 说明符：可用后面的 g
    int m = g();                              // 默认成员初始化器：可用后面的 g
    int g() const { return 1; }
    static constexpr int k = 42;
};

int main() { S s; return s.f() == 1 + static_cast<int>(sizeof(S)) ? 0 : 1; }
```

### 不是完整类上下文的地方

成员的**声明部分**——返回类型、形参类型、数据成员的类型、尾随返回类型中的 `decltype`、静态数据成员的初始化器（非默认成员初始化器）、基类子句——都**不是**完整类上下文。在这些地方只能看到**之前**声明的成员，类也不完整：

```cpp title="not-complete-context.cpp" error
struct S {
    auto f() -> decltype(g());        // error: 尾随返回类型不是完整类上下文，g 尚未声明
    int g();
    char buf[sizeof(S)];              // error: S 在此不完整
    static constexpr int v = w;       // error: 静态数据成员的初始化器不是完整类上下文，w 尚未声明
    static constexpr int w = 1;
};
```

为什么不能让这些地方也"看到后面"？因为它们决定了类的**形状**：数据成员的类型决定布局，返回类型决定签名（进而决定重载、虚函数覆盖关系）。如果它们可以依赖后面的声明，就可能出现循环依赖（`A` 的类型依赖 `B` 的 `sizeof`，`B` 的类型依赖 `A`）。函数体、默认实参这些"不影响形状"的部分则可以安全地推迟。

!!! warning "默认模板实参（¶10.3）：Clang 尚未按此实现"
    ¶10.3 把成员模板的**默认模板实参**列为完整类上下文。但截至写作时，Clang 23 对 `template<class U = decltype(T::m)> void z(); int m;` 这类写法仍报"`T` 中没有成员 `m`"——它没有把默认模板实参推迟处理。依赖这一点的代码目前不可移植。

### 内部类、默认成员初始化器与"鸡生蛋"问题

完整类上下文的推迟处理引出了一个著名的难题。嵌套类 `B` 的默认成员初始化器是**外围类** `A` 的完整类上下文，要到 `A` 的 `}` 才被处理；而在 `A` 的 `}` 之前，如果有什么东西需要知道"`B` 能否默认构造""`B` 的默认构造是否 `noexcept`"，答案就取决于一个还没被解析的初始化器：

```cpp title="nested-dmi.cpp"
#include <type_traits>

struct A {
    struct B { int n = 0; };
    // 在 A 的定义内部询问 B 能否默认构造：B 的默认成员初始化器还没被解析
    static constexpr bool v = std::is_default_constructible_v<B>;
};

// Clang 23 实测：A::v == false；而且由于模板特化的结果被缓存，
// 在类外再问 std::is_default_constructible_v<A::B> 也得到 false！
int main() { return A::v; }
```

¶15 中"默认成员初始化器不得直接或间接导致外围类的预置默认构造函数被隐式定义，或其异常说明被需要"就是针对这一问题的约束，但具体到"类型特征在类内被求值"这种间接情形，各编译器的处理并不一致（有的报错，有的像 Clang 这样静默给出 `false`），这是核心语言中长期悬而未决的领域。**实践建议**：不要在外围类定义内部对含默认成员初始化器的嵌套类使用类型特征或依赖其默认构造；把嵌套类移到外面，或者给它一个用户声明的默认构造函数。

## 默认成员初始化器（¶15）

¶15：*brace-or-equal-initializer* **只能**出现在数据成员的声明中。对非静态数据成员，它指定该成员的**默认成员初始化器**（default member initializer，俗称 NSDMI），当构造函数的成员初始化列表没有提到该成员时使用（[[class.base.init]]），也被聚合初始化使用（[[dcl.init.aggr]]）。对静态数据成员，见下文"静态成员"。

两条附加约束：

1. 默认成员初始化器不得直接或间接导致外围类的预置默认构造函数被隐式定义，或其异常说明被需要（上一小节）。
2. 默认成员初始化器中潜在求值的**立即调用**（immediate invocation，如 `consteval` 函数调用）**不在**初始化器出现处求值，也不在那里检查是否为常量表达式——而是在实际使用该初始化器的构造函数（或聚合初始化）处。这使 `std::source_location::current()`（一个 `consteval` 函数）在默认成员初始化器中能报告**构造函数**的位置，而不是成员声明的位置：

```cpp run title="dmi-source-location.cpp" ok
#include <source_location>

struct S {
    std::source_location loc = std::source_location::current();
    S() { }          // 第 5 行
    S(int) { }       // 第 6 行
};

int main() {
    S a, b(1);
    return (a.loc.line() == 5 && b.loc.line() == 6) ? 0 : 1;   // 报告的是构造函数所在行
}
```

默认成员初始化器可以用 `this`（[[expr.prim.this#5]]），可以引用其他成员（包括后声明的，但读取未初始化的成员仍是错误/UB，取决于类型），但**不能**用圆括号形式：`int x(5);` 在类中会被解析成函数声明（"最令人烦恼的解析"的变体），所以语法上只允许 `= expr` 和 `{ ... }`。

## 存储类说明符与说明符的省略（¶16–¶19）

- ¶16：成员不能声明为 `extern`。在类定义内，成员不能声明为 `thread_local`，除非同时声明为 `static`（非静态数据成员是对象的一部分，"每线程一份"对它没有意义）。
- ¶17：只有构造函数、析构函数和转换函数可以省略 *decl-specifier-seq*；其他成员的 *decl-specifier-seq* 必须包含一个不是 cv 限定符的类型说明符（所以 `struct S { const x; };` 是非良构的——C 风格的"隐式 int"不存在）。*member-declarator-list* 只能在 *class-specifier*/*enum-specifier* 之后或友元声明中省略。纯说明符只能用于**非友元**的**虚函数**声明。
- ¶18：*member-declaration* 开头的属性归属于每个被声明的实体；省略 *member-declarator-list* 时不能有属性。
- ¶19：*virt-specifier-seq* 中每种至多出现一次，且只能出现在虚成员函数的**首次**声明中（类外定义不能再写 `override`）。

```cpp title="specifiers.cpp" error
struct S {
    extern int e;                 // error: ¶16
    thread_local int t;           // error: ¶16，须为 static thread_local
    static thread_local int ok;   // OK
    const x;                      // error: ¶17，缺少类型说明符
    void f() = 0;                 // error: ¶17，纯说明符只能用于虚函数
    virtual void g() override;    // error: g 没有覆盖任何函数（[class.virtual]）
};
```

## 非静态数据成员的类型（¶20–¶23）

¶20：非静态数据成员的类型不能是**不完整类型**、**抽象类类型**，或它们的（多维）数组。注 5：所以类 `C` 不能包含 `C` 类型的非静态成员，但可以包含指向 `C` 的指针或引用。

这条规则也排除了 C99 的**柔性数组成员**（`struct S { int n; int data[]; };`）：`int[]` 是不完整类型。GCC 和 Clang 作为扩展接受它，`-pedantic` 下给出警告；在可移植的 C++ 中它是非良构的。

¶21–¶23 是注和例：非静态成员的使用限制见 [[expr.prim.id]]；非静态成员函数的类型就是普通函数类型，非静态数据成员的类型就是普通对象类型——**没有特殊的"成员函数类型"或"数据成员类型"**（成员指针类型 `int S::*` 是另一回事，[[dcl.mptr]]）。

## 数据成员的分配顺序（¶24）

¶24 注 8：非变体的、非零大小的非静态数据成员，按"**后声明的成员地址更高**"的方式分配（地址比较的规则在 [[expr.rel]]）。对齐要求可能使相邻成员之间有填充；虚函数和虚基类的管理信息（vptr 等）也可能占用空间。

```cpp run title="member-order.cpp" ok
#include <cstdio>

struct S {
    char a;      // 偏移 0
    int  b;      // 偏移 4（主流实现：a 之后 3 字节填充）
    char c;      // 偏移 8，之后尾部填充到 12
public:
    int  d;
private:
    int  e;      // C++23 起：即使跨访问区段，e 也一定在 d 之后
};

int main() {
    S s{};
    bool ordered = &s.a < static_cast<void*>(&s.b) && &s.b < static_cast<void*>(&s.c);
    std::printf("sizeof(S) = %zu\n", sizeof(S));
    return ordered ? 0 : 1;
}
```

!!! history "C++23：不再允许按访问区段重排（P1847）"
    C++98 到 C++20 只保证**同一访问控制区段内**（两个访问说明符之间）的成员按声明顺序递增；不同区段之间的相对顺序未指定，理论上实现可以把 `private` 成员挪到 `public` 成员前面。实际上没有任何主流编译器这样做过。C++23 的 [[P1847R4]] 删除了这项许可，现在顺序只取决于声明顺序。

"非零大小"和"非变体"两个限定的含义：`[[no_unique_address]]` 的空成员可以零大小，可能与其他成员共享地址，不参与排序；联合体（变体）成员都在同一地址。

成员的**最佳排列**（按对齐从大到小排以减少填充）仍然是程序员的责任——编译器不会替你重排。`-Wpadded`（GCC/Clang）可以报告插入的填充。

## 成员名不能与类同名（¶25–¶26）

¶25：若 `T` 是类名，以下都必须与 `T` 不同名：静态数据成员、成员函数（构造函数没有名字，不受影响）、类型成员、成员模板、无作用域枚举成员的枚举项、匿名联合体成员。¶26：若 `T` 有用户声明的构造函数，非静态数据成员也不能叫 `T`。

为什么？因为注入类名 `T`（[[class.pre#2]]）已经绑定在类作用域里了，同名成员会与之冲突；而构造函数的声明语法 `T(...)` 也依赖于 `T` 在类内指类本身。¶26 中"非静态数据成员只有在有用户声明的构造函数时才禁止"是 C 兼容的妥协：C 代码里 `struct stat { int stat; };` 这种写法是合法的。

```cpp title="same-name.cpp" error
struct T1 { int T1; };              // OK: 没有用户声明的构造函数（C 兼容）
struct T2 { T2(); int T2; };        // error: ¶26
struct T3 { static int T3; };       // error: ¶25.1
struct T4 { void T4(); };           // error: ¶25.2（这不是构造函数：构造函数不能有返回类型）
```

## 公共初始序列与布局兼容（¶27–¶30）

### 公共初始序列（¶27）

两个**标准布局 struct**（[[class.prop#4]]）类型的**公共初始序列**（common initial sequence），是从各自第一个非静态数据成员（含位域）开始、按声明顺序的最长一段成员序列，使得对应的成员：

- ¶27.1 类型**布局兼容**（[[basic.types.general]]）；
- ¶27.2 对齐要求相同；
- ¶27.3 若实现支持 `[[no_unique_address]]`（`__has_cpp_attribute(no_unique_address)` 非 0），则都没有用该属性声明；
- ¶27.4 要么都是同宽度的位域，要么都不是位域。

标准例 4：

```cpp run title="cis.cpp" ok
struct A { int a; char b; };
struct B { const int b1; volatile char b2; };   // 与 A：全部成员（cv 不影响布局兼容）
struct C { int c; unsigned : 0; char b; };      // 与 A：只有第一个（无名位域打断）
struct D { int d; char b : 4; };                // 与 A：只有第一个（位域 vs 非位域）
struct E { unsigned int e; char b; };           // 与 A：空（int 与 unsigned int 不布局兼容）
int main() { }
```

¶27.2 的"对齐相同"是为了排除 `alignas` 制造的差异：`struct X { alignas(8) int a; }` 与 `struct Y { int a; }` 的首成员类型相同，但偏移以后的成员可能不同。

### 布局兼容的类（¶28–¶29）

¶28：两个标准布局 struct 是**布局兼容的类**，若它们的公共初始序列包含两者的全部成员和位域。¶29：两个标准布局 union 是布局兼容的，若它们的非静态数据成员数量相同，并且对应的成员（**任意顺序**）类型布局兼容。C++20 起可以用 `std::is_layout_compatible` 查询。

### 通过联合体读取公共初始序列（¶30）

¶30 是公共初始序列存在的理由：在一个活跃成员为 struct 类型 `T1` 的标准布局 union 中，**允许读取**另一个 struct 类型成员 `T2` 的非静态数据成员 `m`，只要 `m` 属于 `T1` 与 `T2` 的公共初始序列；行为如同指名了 `T1` 中的对应成员。

```cpp run title="union-cis.cpp" ok
struct T1 { int a, b; };
struct T2 { int c; double d; };
union U { T1 t1; T2 t2; };

int f() {
    U u = { { 1, 2 } };   // 活跃成员是 t1
    return u.t2.c;        // OK: c 在公共初始序列中，如同读取 u.t1.a
    // return (int)u.t2.d;   // UB: d 不在公共初始序列中，t2 不是活跃成员
}

int main() { return f() - 1; }
```

这条规则让"带标签的联合体"惯用法合法：

```cpp run title="tagged-union.cpp" ok
enum Kind { Int, Dbl };
struct IntNode { Kind k; int v; };
struct DblNode { Kind k; double v; };
union Node { IntNode i; DblNode d; };

int value(const Node& n) {
    switch (n.i.k) {            // 无论哪个成员活跃，都可以通过 n.i.k 读标签（公共初始序列）
        case Int: return n.i.v;
        case Dbl: return static_cast<int>(n.d.v);
    }
    return -1;
}

int main() {
    Node n; n.d = {Dbl, 2.5};
    return value(n) - 2;
}
```

注 10 提醒：通过非 `volatile` 类型的 glvalue 读取 `volatile` 对象是 UB（[[dcl.type.cv]]）——例 4 中 `A` 与 `B` 的公共初始序列包含 `volatile char b2`，但通过 `A::b` 去读它仍然是 UB。

## 首成员地址（¶31）

¶31：若标准布局类对象有非静态数据成员，它的地址与其**第一个非静态数据成员**的地址相同（若该成员不是位域）；它的地址也与它的**每个基类子对象**的地址相同。

注 11：因此标准布局 struct 中可以有实现插入的无名填充，但**不在开头**。注 12：对象与其第一个子对象**指针可互转换**（[[basic.compound#7]]），可以用 `reinterpret_cast`（或 `static_cast` 经 `void*`）在两者的指针之间转换，结果指向对方（[[expr.static.cast]]）。

```cpp run title="pointer-interconvertible.cpp" ok
struct Base { int tag; };
struct Wrapper : Base { };              // 标准布局：成员都在 Base 中
struct Outer { Base first; int extra; }; // 标准布局

int main() {
    Wrapper w{{1}};
    Outer o{{2}, 3};
    Base* b1 = reinterpret_cast<Base*>(&w);   // 等价于 static_cast<Base*>(&w)
    Base* b2 = reinterpret_cast<Base*>(&o);   // OK: o 与 o.first 指针可互转换
    return b1->tag + b2->tag - 3;
}
```

注意数组与其首元素**不是**指针可互转换的（[[basic.compound#7]] 注 7），尽管地址相同。

## 数据成员描述（¶32）{{c++26}}

¶32 为静态反射引入了一个抽象：**数据成员描述**（data member description）是一个六元组 (T, N, A, W, NUA, ANN)，分别是类型、名字（或 ⊥ 表示无名）、对齐（或 ⊥）、位域宽度（或 ⊥）、是否 `[[no_unique_address]]`、注解序列。两个描述相等当且仅当各分量相同。

注 13 说明其用途：`std::meta::data_member_spec` 返回表示数据成员描述的反射，`std::meta::define_aggregate` 据此为一个不完整的类**生成**成员定义（[[meta.reflection.define.aggregate]]）。这是 C++26 反射中"由代码生成类"的入口。C++23 及以前没有对应物。

---

## 成员函数（[class.mfct]）

### 类内定义即隐式 inline——在全局模块中（[class.mfct] ¶1）

[[class.mfct#1]]：若成员函数**附属于全局模块**，并且在类定义**内**被定义，则它是 `inline` 的（[[dcl.inline]]）。注 1：声明为 `inline`、`constexpr` 或 `consteval` 的成员函数也是 inline 的。

"附属于全局模块"是 C++20 加上的限定：在**具名模块**（`export module M;`）的接口中，类内定义的成员函数**不再隐式 inline**。原因是隐式 inline 的唯一目的是让头文件中的类定义可以被多个 TU 包含而不违反 ODR；在模块中，类定义只编译一次，函数体可以只生成一份代码，而不是在每个导入者中内联展开——这样修改函数体时不必让所有导入者重新编译（ABI 隔离）。如果确实希望在模块中内联，需要显式写 `inline`。

### 类外定义的作用域（[class.mfct] ¶2）

[[class.mfct#2]] 的例子说明：类外定义 `void X::f(T t = count) { }` 中，`X::` 之后的部分（形参类型 `T`、默认实参 `count`、函数体）都在类 `X` 的作用域内查找。但**返回类型**在 `X::f` 之前，不在类作用域内——这就是为什么返回嵌套类型时要写 `X::T X::g()`，或者用尾随返回类型 `auto X::g() -> T`。

```cpp run title="out-of-class-scope.cpp" ok
struct X {
    typedef int T;
    static T count;
    T g();
    void f(T);
};
X::T X::count = 1;

X::T X::g() { return count; }          // 返回类型须限定：X::g 之前不在类作用域
void X::f(T t = count) { (void)t; }     // 形参类型与默认实参在类作用域中查找

int main() { X x; x.f(); return x.g() - 1; }
```

### 局部类与 typedef 声明成员函数（[class.mfct] ¶3–¶4）

[[class.mfct#3]]：局部类的成员函数如果要定义，必须在类定义内定义（没有地方可以在类外定义它们——函数内不能嵌套函数定义）。

[[class.mfct#4]] 注 2：可以用函数类型的 typedef **声明**（但不能定义）成员函数，结果的类型与直接写出函数声明符完全相同，包括 `const` 限定的函数类型 `typedef void fvc() const;`——这种"带 cv 的函数类型"（abominable function type）只能用在这类场合。

## 非静态成员函数（[class.mfct.non.static]）

[[class.mfct.non.static#1]]：非静态成员函数可以通过类成员访问语法（`obj.f()`、`p->f()`）为其类或派生类的对象调用；也可以在类（或派生类）的成员内部用普通函数调用语法直接调用（`f()` 被隐式变换为 `(*this).f()`，[[expr.prim.id]]）。

### 隐式对象成员函数：cv 与引用限定（[class.mfct.non.static] ¶2）

C++23 起，非静态成员函数分为两类（[[dcl.fct#8]]）：

- **隐式对象成员函数**（implicit object member function）：传统写法，对象通过隐式的 `this` 传入；
- **显式对象成员函数**（explicit object member function）：第一个形参以 `this` 修饰（"deducing this"），对象作为显式形参传入。

[[class.mfct.non.static#2]] 注 1：隐式对象成员函数可以带 *cv-qualifier*（影响 `this` 的类型，[[expr.prim.this]]）和/或 *ref-qualifier*（[[dcl.fct]]），两者都影响重载决议。

在重载决议中，隐式对象成员函数被视为有一个额外的第一形参——**隐式对象形参**（implicit object parameter），其类型是（[[over.match.funcs.general#4]]）：

| 声明 | 隐式对象形参类型 | `this` 的类型 |
|---|---|---|
| `void f();` | `X&`（但也能绑定右值，见下） | `X*` |
| `void f() const;` | `const X&` | `const X*` |
| `void f() &;` | `X&` | `X*` |
| `void f() &&;` | `X&&` | `X*` |
| `void f() const &&;` | `const X&&` | `const X*` |

一个历史包袱：**没有** *ref-qualifier* 的成员函数，其隐式对象形参虽然是左值引用，却也能绑定右值（[[over.match.funcs.general#5]]）——所以 `std::string().size()` 能调用。这就是为什么 C++98 中 `X().nonconst_member()` 能编译：临时对象可以调用非 const 成员函数。引用限定符（C++11）让你可以区分：

```cpp run title="ref-qualifiers.cpp" ok
#include <string>
#include <utility>

struct Buf {
    std::string s;
    std::string&       get() &       { return s; }             // 左值对象：返回引用
    const std::string& get() const & { return s; }
    std::string        get() &&      { return std::move(s); }  // 右值对象：把内容移走
};

Buf make() { return {"hello"}; }

int main() {
    Buf b{"abc"};
    std::string& r = b.get();          // 调用 & 版本
    std::string  v = make().get();     // 调用 && 版本：避免悬垂引用 + 免复制
    return (r.size() == 3 && v.size() == 5) ? 0 : 1;
}
```

规则：同名同形参的重载中，**要么都有引用限定，要么都没有**（[[over.load]]）——不能 `void f() &;` 和 `void f();` 并存：

```cpp title="ref-qual-mix.cpp" error
struct C {
    void f() &;
    void f();     // error: 不能与有引用限定的同签名重载并存
};
```

### `this` 的类型

在 cv 限定为 *cv* 的隐式对象成员函数中，`this` 是"指向 *cv* `X` 的指针"类型的 prvalue（[[expr.prim.this#4]]）。注意 `this` 永远是 prvalue，不能对它赋值、不能取地址；`this` 的类型不受 *ref-qualifier* 影响（`&&` 成员函数里 `*this` 仍是**左值**）。C++26 起，在契约断言的谓词中 `this` 会额外加上 `const`（[[expr.prim.this#3]]）{{c++26}}。

### 虚函数（[class.mfct.non.static] ¶3）

[[class.mfct.non.static#3]]：隐式对象成员函数可以声明为 `virtual`（[[class.virtual]]）或纯虚（[[class.abstract]]）。**显式对象成员函数不能是虚函数**（[[dcl.fct#7]]）。

### 显式对象成员函数（"deducing this"）{{c++23}}

C++23 的 [[P0847R7]] 允许把对象形参写成显式的第一个形参，前缀 `this`（[[dcl.fct#7]]）：

```cpp run title="deducing-this.cpp" ok
#include <utility>
#include <string>

struct S {
    std::string name = "s";

    // 一个模板替代 &、const&、&&、const&& 四个重载
    template<class Self>
    auto&& get(this Self&& self) { return std::forward<Self>(self).name; }

    // 按值接收对象：调用时复制（或移动）
    std::size_t len(this S self) { return self.name.size(); }
};

int main() {
    S s;
    const S cs;
    std::string& a = s.get();                 // Self = S&
    const std::string& b = cs.get();          // Self = const S&
    std::string c = std::move(s).get();       // Self = S：返回 std::string&&，c 由移动构造
    (void)a; (void)b;
    return (c == "s" && cs.len() == 1) ? 0 : 1;
}
```

它解决的问题：

1. **消除 cv/ref 重载的样板代码**（上例的 `get`）；
2. **CRTP 的替代**：基类中的 `template<class Self> void f(this Self& self)` 能拿到派生类的真实类型；
3. **递归 lambda**：`auto fib = [](this auto self, int n) -> int { return n < 2 ? n : self(n-1) + self(n-2); };`；
4. **按值传递 `*this`**：对小类型可以减少一次间接访问。

限制（[[dcl.fct#7]]、[[dcl.fct#8]]、[[expr.prim.this#4]]）：

- 显式对象形参只能是第一个形参，不能是函数形参包；
- 这样的成员函数**不能**再带 cv 限定、引用限定，不能是 `static` 或 `virtual`；
- 函数体内**不能用 `this`**，也不能隐式访问成员（必须写 `self.name`）——因为根本没有隐式对象；
- 构造函数不能有显式对象形参（[[class.ctor.general#7]]）；
- 取地址得到的是**普通函数指针**而不是成员函数指针：`&S::len` 的类型是 `std::size_t(*)(S)`。

```cpp title="deducing-this-errors.cpp" error
struct D {
    void g(this D) const;          // error: 不能有 cv 限定
    static void h(this D);         // error: 不能是 static
    virtual void i(this D&);       // error: 不能是 virtual
    void j(this D& self) { this->j(); }   // error: 不能使用 this
};
```

## 静态成员（[class.static]）

### 总则（[class.static.general]）

[[class.static.general#1]]：类 `X` 的静态成员 `s` 可以用限定名 `X::s` 指称，**不需要对象**。也可以用成员访问语法 `obj.s`——此时**对象表达式仍会被求值**（副作用照常发生），只是结果不被使用：

```cpp run title="static-member-access.cpp" ok
#include <cstdio>

struct process {
    static void reschedule() { }
};

process& g() { std::puts("g() called"); static process p; return p; }

int main() {
    process::reschedule();   // OK: 不需要对象
    g().reschedule();        // g() 被调用（会打印）
}
```

[[class.static.general#2]]：静态成员遵守通常的访问规则；`static` 说明符只能用在类定义内部的成员声明中，类外定义时不能再写 `static`（那里的 `static` 会是"内部链接"的意思，与成员身份冲突）。

### 静态成员函数（[class.static.mfct]）

[[class.static.mfct#1]]、[[class.static.mfct#2]]（都是注）：[[class.mfct]] 的规则适用于静态成员函数；静态成员函数**没有 `this` 指针**，不能是 `const`、`volatile`、`virtual`。在重载决议中，静态成员函数的隐式对象形参"匹配任何对象"（[[over.match.funcs.general#4]]），所以 `obj.static_f()` 可以和非静态重载一起参与决议。

C++23 起，`operator()` 和 `operator[]` 可以是静态成员函数（[[over.call]]、[[over.sub]]），无捕获 lambda 也可以声明为 `static`——这让无状态函数对象调用时省掉一个 `this` 参数。

### 静态数据成员（[class.static.data]）

[[class.static.data#1]]：静态数据成员**不是类子对象的一部分**。非 `thread_local` 的静态数据成员只有一份，被所有对象共享；`thread_local` 的每个线程一份。

[[class.static.data#2]]：静态数据成员不能是 `mutable`；不能是**无名类**、**局部类**（或它们（间接）嵌套的类）的直接成员——这些类没有链接，无法在类外提供定义，而且局部类的静态成员的生命周期与函数调用的关系也说不清。

```cpp title="static-data-restrictions.cpp" error
void f() {
    struct Local { static int x; };   // error: 局部类不能有静态数据成员
}
struct { static int y; } anon;        // error: 无名类不能有静态数据成员
struct M { static mutable int z; };   // error: 静态数据成员不能是 mutable
```

#### 声明与定义（[class.static.data] ¶3）

[[class.static.data#3]]：**非 inline** 静态数据成员在类定义中的声明**不是定义**，并且可以是**不完整类型**（`cv void` 除外）。它的定义在命名空间作用域中给出，定义中的初始化器处在类的作用域中（可以直接用类的其他成员，无需限定）：

```cpp run title="static-data-def.cpp" ok
struct Node;
struct List {
    static Node sentinel;        // OK: 声明时 Node 可以不完整
    static int count;
    static int limit;
};
struct Node { int v; };

Node List::sentinel{0};          // 定义：此时 Node 必须完整
int  List::count = 0;
int  List::limit = count + 10;   // 初始化器在类作用域中：count 即 List::count

int main() { return List::limit - 10; }
```

注 2：一旦被定义，静态数据成员就存在，即使程序从未创建过该类的对象。它的初始化与销毁遵循 [[basic.start.static]]、[[basic.start.dynamic]]、[[basic.start.term]]。

#### 类内初始化器的三种情形（[class.static.data] ¶4）

[[class.static.data#4]] 规定了何时可以在类内写初始化器：

| 情形 | 类内初始化器 | 类外定义 |
|---|---|---|
| 非 volatile、非 inline 的 **`const` 整型/枚举** | 可以，须为常量表达式 | 若被 **odr-use** 则必须在命名空间作用域定义，且定义**不能**再带初始化器 |
| **`inline`** 静态数据成员（C++17）| 可以（声明即定义） | 不需要 |
| **`constexpr`** 静态数据成员 | 必须（`constexpr` 蕴含 `inline`，C++17 起）| 可以在命名空间作用域无初始化器地重声明，但**已弃用**（[[depr.static.constexpr]]） |
| 其他 | **不能** | 必须在类外定义（若被 odr-use） |

```cpp run title="static-init-kinds.cpp" ok
#include <string>

struct S {
    static const int N = 3;                    // const 整型：类内常量初始化器
    static inline std::string name = "S";      // C++17 inline：任意类型，声明即定义
    static constexpr double pi = 3.14159;      // constexpr ⇒ inline
    // static double e = 2.718;                // error: 非 const、非 inline 不能类内初始化
    int arr[N];                                // N 可用于常量表达式（不是 odr-use）
};

int main() { S s{}; return static_cast<int>(sizeof(s.arr) / sizeof(int)) - S::N; }
```

`const` 整型静态成员的经典陷阱：它在类内有初始化器，于是看起来"已经定义了"，但它的类内声明**不是定义**。如果它被 **odr-use**（例如绑定到引用、取地址、传给 `const int&` 形参的函数如 `std::max`），就必须在某个 TU 中提供定义，否则违反 ODR——这是 IFNDR，表现通常是**链接错误**，而且取决于优化级别：

```cpp title="odr-use-static-const.cpp" ifndr
struct S { static const int N = 3; };

int main() {
    const int& r = S::N;   // odr-use：把 N 绑定到引用
    return r;              // 缺少 S::N 的定义 —— IFNDR；-O0 下常见链接错误，-O2 下可能"碰巧"链接成功
}
```

修复：C++17 起把它改成 `static constexpr int N = 3;` 或 `static inline const int N = 3;`——inline 变量的类内声明就是定义。这也是 C++17 引入 inline 变量的主要动机之一：在头文件中定义"类的全局常量/单例"不再需要在某个 .cpp 中补一行定义。

[[class.static.data#5]] 注 3：一个被 odr-use 的静态数据成员在合法程序中恰有一个定义（inline 的则在每个使用它的 TU 中各有一个"相同的"定义，[[basic.def.odr]]）。[[class.static.data#6]] 注 4：命名空间作用域中的类的静态数据成员具有该类名的链接（[[basic.link]]）。

## 位域（[class.bit]）

### 声明与基本限制（[class.bit] ¶1）

[[class.bit#1]]：形如 `标识符(可选) 属性(可选) : 常量表达式 初始化器(可选)` 的 *member-declarator* 声明一个**位域**（bit-field）。要点：

- 位域不能是静态成员；
- 类型必须是**整型或（可 cv 限定的）枚举类型**；
- "是位域"这一语义属性**不是成员类型的一部分**：`struct S { int x : 3; };` 中 `S::x` 的类型就是 `int`，`decltype(s.x)` 是 `int`；
- 宽度必须是值 ≥ 0 的整型常量表达式；
- 若宽度大于类型（对枚举是其底层类型）的宽度，多出的位是**填充位**（padding bits）；
- 位域在类对象内如何分配、如何对齐，是**实现定义的** {{impl}}；位域被装进某个可寻址的分配单元中。

注 1：有的机器上位域可以跨越分配单元，有的不行；有的机器从右向左分配，有的从左向右。这就是为什么**用位域描述硬件寄存器或网络协议格式是不可移植的**——位的顺序由 ABI 决定（Itanium/x86-64 SysV 上小端从低位开始分配，MSVC 有自己的规则，尤其是相邻位域类型不同时是否共享分配单元）。

```cpp run title="bitfield-basics.cpp" ok
#include <type_traits>

struct Flags {
    unsigned ready : 1;
    unsigned mode  : 3;
    unsigned       : 4;    // 无名位域：占 4 位作为填充
    unsigned count : 8;
};

Flags f{};
static_assert(std::is_same_v<decltype(f.mode), unsigned>);   // 位域性不是类型的一部分

int main() {
    f.mode = 5;
    f.count = 200;
    return (f.mode == 5 && f.count == 200) ? 0 : 1;
}
```

### 无名位域与零宽位域（[class.bit] ¶2）

[[class.bit#2]]：省略标识符的位域是**无名位域**。无名位域**不是成员**，不能被初始化，不能带 cv 限定。注 2：无名位域用于按外部规定的布局填充。

特殊情形：**宽度为 0 的无名位域**使下一个位域对齐到分配单元的边界。**只有**无名位域可以宽度为 0。

```cpp run title="zero-width.cpp" ok
#include <cstdio>

struct A { unsigned a : 3; unsigned : 0; unsigned b : 3; };   // b 从新的 unsigned 单元开始
struct B { unsigned a : 3;               unsigned b : 3; };   // a、b 共享一个单元

int main() {
    // 主流实现（x86-64/AArch64 Itanium ABI）：sizeof(A) == 8，sizeof(B) == 4 —— 实现定义
    std::printf("%zu %zu\n", sizeof(A), sizeof(B));
}
```

```cpp title="bitfield-errors.cpp" error
struct C {
    static int s : 3;     // error: 位域不能是静态成员
    const int : 2;        // error: 无名位域不能 cv 限定
    int z : 0;            // error: 只有无名位域可以宽度为 0
    double d : 4;         // error: 位域必须是整型或枚举类型
};
```

零宽位域在**内存模型**上也有用：相邻的位域属于同一个**内存位置**（memory location，[[intro.memory]]），两个线程分别写同一内存位置中的不同位域会构成数据竞争；用零宽位域隔开后它们成为不同的内存位置。

### 不能取地址、不能绑定非 const 引用（[class.bit] ¶3）

[[class.bit#3]]：不能对位域使用 `&`，所以**没有指向位域的指针**；非 `const` 引用不能绑定到位域。注 3：`const T&` 引用若用指代位域的左值初始化，会绑定到一个保存位域值的**临时对象**，而不是位域本身——之后修改位域，引用看不到：

```cpp run title="bitfield-ref.cpp" ok
struct C { int x : 4; };

int main() {
    C c{3};
    const int& r = c.x;   // 绑定到临时量（复制了 3），不是绑定到位域
    c.x = 1;
    return r == 3 ? 0 : 1;   // r 仍是 3
    // int* p = &c.x;     // error: 不能取位域地址
    // int& nr = c.x;     // error: 非 const 引用不能绑定位域
}
```

为什么？内存的最小可寻址单位是字节（[[intro.memory]]），指针只能指向字节边界；一个 3 位宽、从第 5 位开始的位域没有"地址"可言。这也是为什么 `std::vector<bool>` 不能返回真正的 `bool&`，只能返回代理对象。

### 值的保持（[class.bit] ¶4）

[[class.bit#4]] 规定什么时候"存进去的值能原样读回来"：

- 整型值（非 `bool`）：若该值能被一个宽度为 N、符号性与位域类型相同的假想整数类型表示，存入后读出相等；
- `bool` 位域（任意宽度，包括 1 位）：存入 `true`/`false`，读出相等；
- 枚举值存入同类型的枚举位域：若宽度足以容纳该枚举的所有值（[[dcl.enum]]），读出相等。

存入不能表示的值时，位域的结果值是**实现定义的**（[[expr.assign#4]]）{{impl}}。主流实现按二进制补码截断：

```cpp run title="bitfield-value.cpp" impl
struct C { int x : 4; };    // 有符号 4 位：可表示 -8..7

int main() {
    C c{};
    c.x = 7;                // 能表示：读出 7
    c.x = 8;                // 不能表示：结果实现定义（Clang/GCC：-8，并给出警告）
    return c.x;
}
```

注意 **`int` 位域的符号性**：C++14 之前，`int x : 4` 是有符号还是无符号是实现定义的（与 C 相同）；C++14 起明确为有符号。C 中至今仍是实现定义——这是在 C/C++ 共享头文件中用位域时的一个坑：需要无符号就明确写 `unsigned`。

标准例 1 演示了枚举位域：`enum BOOL { FALSE=0, TRUE=1 }; struct A { BOOL b:1; };` 中 `BOOL` 的值范围是 0..1（[[dcl.enum]]），1 位足够，所以 `a.b = TRUE; a.b == TRUE` 为真。

## 类专属 operator new/delete（[class.free]）

[[class.free#1]]、[[class.free#3]]：类 `T` 的任何**分配函数**（`operator new`/`operator new[]`）和**解分配函数**（`operator delete`/`operator delete[]`）都是**静态成员**，即使没有显式写 `static`。理由显而易见：调用分配函数时对象还不存在，调用解分配函数时对象已经销毁，不可能有 `this`。

[[class.free#2]] 的例子说明名字**隐藏**：类中声明了任何 `operator new`，就会隐藏全局的 `::operator new` 的**所有**形式（查找规则见 [[expr.new]]：*new-expression* 先在类作用域查找）：

```cpp title="class-new-hiding.cpp" error
#include <cstddef>
#include <new>

class Arena;
struct B {
    void* operator new(std::size_t, Arena*);   // 只声明了带 Arena* 的放置形式
};
struct D1 : B { };

Arena* ap;
void foo(int i) {
    new (ap) D1;      // 调用 B::operator new(std::size_t, Arena*)
    new D1[i];        // 调用 ::operator new[](std::size_t)：数组形式没被隐藏
    new D1;           // error: ::operator new(std::size_t) 被 B 的同名函数隐藏
}
```

### 不能是虚函数，但效果"如同"虚函数（[class.free] ¶4–¶5）

[[class.free#4]]：既然是静态的，分配/解分配函数**不能是虚函数**。注 1：但当 *delete-expression* 的操作数指向一个**有虚析构函数**的类对象时，解分配函数是由**动态类型**的析构函数选择的（[[class.dtor#15]]），效果和虚函数一样：

```cpp run title="virtual-delete.cpp" ok
#include <new>
#include <cstdio>

struct B {
    virtual ~B() = default;
    void operator delete(void* p, std::size_t) { std::puts("B::delete"); ::operator delete(p); }
};
struct D : B {
    int payload[10];
    void operator delete(void* p) { std::puts("D::delete"); ::operator delete(p); }
};
struct E : B {
    void log() { std::puts("E: about to be destroyed"); }
    // C++20 销毁型 operator delete：自己负责调用析构函数
    void operator delete(E* p, std::destroying_delete_t) {
        p->log();
        p->~E();
        ::operator delete(p);
    }
};

int main() {
    B* bp = new D;
    delete bp;        // 打印 D::delete：由 D 的（虚）析构函数选择
    bp = new E;
    delete bp;        // 先调用 E 的销毁型 operator delete，由它析构并释放
}
```

实现上（Itanium ABI）这正是通过**删除析构函数**（deleting destructor，D0）完成的：`delete bp` 虚调用 D0，D0 先执行完整对象析构（D1），再调用**它所在类**选定的 `operator delete`。详见 [[class.dtor]]。

**销毁型 operator delete**（destroying operator delete，C++20）的第二个形参是 `std::destroying_delete_t`，第一个形参是类指针而不是 `void*`；*delete-expression* 遇到它时**不调用析构函数**，由它自己负责。用途：可变长对象（对象后面紧跟数据，需要先读出大小再释放）、对象池等。

注 2：对**数组** `delete[]`，虚析构函数不起作用：用基类指针 `delete[]` 一个派生类数组是 **UB**（[[expr.delete]]），因为数组的元素大小不同，指针算术本身就错了：

```cpp title="array-delete-ub.cpp" ub
struct B { virtual ~B() = default; };
struct D : B { int extra[4]; };

int main() {
    B* bp = new D[3];
    delete[] bp;      // UB: 静态类型与动态类型不同的数组 delete[]
}
```

[[class.free#5]]：对解分配函数的访问检查是**静态**进行的，即使实际执行的是另一个。在上面的 `virtual-delete.cpp` 中，若 `B::operator delete` 是 `private`，`delete bp;` 就是非良构的——尽管运行时实际调用的是 `D::operator delete`。

[[class.free#6]] 注 3：没有显式 *noexcept-specifier* 的解分配函数具有不抛出的异常说明。

## 嵌套类（[class.nest]）

[[class.nest#1]]：在另一个类中声明的类称为**嵌套类**。嵌套类是外围类的成员（所以受访问控制，也拥有对外围类私有成员的访问权，见 [[class.access.nest]]），但**嵌套类的对象与外围类的对象没有任何关系**——它不像 Java 的非静态内部类那样隐式持有外围对象的引用。标准例 1 改编：

```cpp title="nested-access.cpp" error
int x;
int y;

struct enclose {
    int x;
    static int s;

    struct inner {
        void f(int i) {
            int a = sizeof(x);   // OK: sizeof 的操作数是未求值操作数
            x = i;               // error: 给 enclose::x 赋值——没有 enclose 对象
            s = i;               // OK: 给 enclose::s 赋值
            ::x = i;             // OK: 全局 x
            y = i;               // OK: 全局 y
            (void)a;
        }
        void g(enclose* p, int i) {
            p->x = i;            // OK: 通过对象访问 enclose::x
        }
    };
};

inner* p = 0;                    // error: 在全局作用域找不到 inner，须写 enclose::inner
```

`sizeof(x)` 能通过是因为 [[expr.prim.id]] 允许在未求值操作数中不带对象地指名非静态数据成员。`x = i` 中的 `x` 通过名字查找找到 `enclose::x`（嵌套类的作用域在外围类之内），但无法隐式变换为 `this->x`——`this` 是 `inner*`，不是 `enclose*`。

[[class.nest#2]] 注 2：嵌套类可以在外围类中定义，也可以在外围命名空间中定义（`class E::I2 { };`）；嵌套类的成员函数和静态数据成员可以在嵌套类中或外围命名空间作用域中定义。这让"接口头文件中只前置声明私有嵌套类、实现文件中再定义"的 Pimpl 变体成为可能。

[[class.nest#3]]：嵌套类中定义的**友元函数**对外围类的成员没有特殊访问权——友元关系不传递，也不因定义位置而"继承"。

## 实现视角

!!! impl "成员函数与 ABI"
    - 非静态成员函数在 Itanium ABI 中就是一个以 `this` 为第一个参数的普通函数；修饰名中编码了 cv 和引用限定（如 `_ZNK1S3getEv` 中的 `K` 表示 `const`；引用限定符分别编码为 `R`/`O`）。
    - 显式对象成员函数的修饰方式与隐式对象成员函数不同，而且它本质上就是以对象为第一个参数的函数——`&S::f` 是普通函数指针。
    - 静态数据成员是普通的全局变量，名字被修饰为 `_ZN1S1NE` 之类；`inline` 的静态数据成员在 ELF 上以 COMDAT/弱符号发出，由链接器去重。

!!! impl "位域的代码生成"
    读写位域需要"读-改-写"整个分配单元（加载、移位、掩码、存回）。这就是为什么位域与多线程不能混用：两个线程写同一分配单元中的不同位域，会互相覆盖。零宽位域（或把位域放进不同的成员之间）是标准承认的隔离方式。

## 历史与演进

!!! history "历史与演进"
    - **C++98**：只有 `static const` 整型/枚举成员可以类内初始化；成员函数类内定义即 inline；位域与 C 相同（`int` 位域符号性实现定义）。
    - **C++11**：非静态数据成员的**默认成员初始化器**；引用限定符；`constexpr` 静态数据成员（须类内初始化）；`final`/`override`；嵌套类成为"成员"，获得访问外围类私有成员的权利。
    - **C++14**：`int` 位域明确为有符号；聚合可以有默认成员初始化器。
    - **C++17**：**inline 变量**，`static inline` 数据成员可以类内定义任意类型；`constexpr` 静态数据成员隐式 inline，类外重声明被弃用。
    - **C++20**：位域的默认成员初始化器；`[[no_unique_address]]`；销毁型 `operator delete`；模块中类内定义的成员函数不再隐式 inline；*requires-clause* 约束非模板成员函数。
    - **C++23**：**显式对象成员函数**（[[P0847R7]]）；成员布局不再按访问区段重排（[[P1847R4]]）；静态 `operator()`/`operator[]`。
    - **C++26 草案**：`friend Ts...;` 包友元；契约说明符、`consteval` 块进入成员声明；数据成员描述（反射）。当前草案还明确了引用成员的布局与指针相同（¶7）。

## 陷阱

!!! pitfall "类内 `static const int` 不等于定义"
    被 odr-use（绑定引用、取地址、传给 `std::max`/`std::min` 等按引用接受实参的函数）时需要类外定义，否则 IFNDR（典型表现为链接错误）。C++17 起用 `static constexpr` 或 `static inline`。

!!! pitfall "以为默认成员初始化器可以用圆括号"
    `struct S { std::vector<int> v(10); };` 会被当作声明一个名为 `v` 的成员函数，然后因 `10` 不是类型而报错。用 `v = std::vector<int>(10);` 或 `v{...}`（注意花括号会优先选择 `initializer_list` 构造函数）。

!!! pitfall "用位域描述硬件寄存器"
    位的分配顺序、跨单元规则、对齐都是实现定义的。跨编译器、跨架构的代码应该用显式的移位和掩码。

!!! pitfall "在类内对嵌套类使用类型特征"
    见"内部类、默认成员初始化器与'鸡生蛋'问题"：结果可能被缓存成错误的值。

!!! pitfall "以为 `&&` 成员函数里 `*this` 是右值"
    `*this` 永远是左值。要转发对象的值类别，用 `std::move(*this)`，或者改用显式对象形参 `this Self&& self` 配合 `std::forward<Self>(self)`。

## 思考题

!!! question "思考题 1"
    下面的类定义哪些行有问题？

    ```cpp
    struct S {
        using F = int(int) const;
        F f;                              // (1)
        static constexpr int n = m();     // (2)
        static constexpr int m() { return 1; }
        int g(int x = m()) { return x; }  // (3)
        int arr[m()];                     // (4)
    };
    ```

<details markdown="1">
<summary>答案</summary>

- (1) OK：用带 cv 限定的函数类型 typedef 声明成员函数，等价于 `int f(int) const;`（[[class.mfct#4]]）。
- (2) **错误**：静态数据成员的初始化器不是完整类上下文；在这里调用 `m()` 时 `m` 尚未声明（即使把 `m` 挪到前面，`constexpr` 函数 `m` 的函数体是完整类上下文，要到类结束才被处理，所以在类内用它求常量表达式仍会报"函数未定义"）。
- (3) OK：默认实参是完整类上下文，可以使用 `m`。
- (4) **错误**：数组边界不是完整类上下文；且同 (2)，`m` 的定义在类结束前不可用于常量求值。
</details>

!!! question "思考题 2"
    `struct A { int a; char b; }; struct B { int x; char y; short z; };` 放在一个 union 里，`B` 是活跃成员时读 `u.a.b` 合法吗？读 `u.a.a` 呢？如果 `A` 的第一个成员改成 `alignas(8) int a;` 呢？

<details markdown="1">
<summary>答案</summary>

`A` 与 `B` 的公共初始序列是 `{a, b}` 与 `{x, y}`（`int`/`int`、`char`/`char` 布局兼容且对齐相同），所以 `u.a.a`、`u.a.b` 都可以读（¶30），如同读 `u.b.x`、`u.b.y`。若 `A::a` 是 `alignas(8) int`，¶27.2 要求对齐相同，第一个成员就不满足，公共初始序列为空——两者都不能读（UB）。另外，`alignas(8)` 也会改变 `A` 的布局，所以这条规则并非多余。
</details>

!!! question "思考题 3"
    为什么类专属的 `operator delete` 要做**静态**访问检查（[[class.free#5]]），而不是检查运行时实际调用的那个？

<details markdown="1">
<summary>答案</summary>

访问控制是编译期机制：编译器在 `delete bp;` 处只知道 `bp` 的静态类型 `B*`，不可能知道运行时动态类型是哪个派生类、会选中哪个解分配函数。所以只能按静态类型查找到的那个函数（`B::operator delete`）检查访问权。实际被调用的 `D::operator delete` 是从 `D` 的虚析构函数里调用的，那是 `D` 的成员在访问 `D` 自己的成员，当然可访问。这与虚函数的访问规则（[[class.access.virt]]：按调用点的静态类型检查）一致。
</details>

## 小结

| 主题 | 规则 |
|---|---|
| 成员集合 | 由 *member-specification* 一次确定，不能在别处添加；成员不能重复声明（嵌套类、不透明枚举除外） |
| 完整类上下文 | 函数体、默认实参、默认模板实参、`noexcept`、契约说明符、默认成员初始化器：可见全类、类视为完整 |
| 默认成员初始化器 | 只能 `=` 或 `{}`；其中的 consteval 调用在使用处求值 |
| 布局 | 后声明的成员地址更高（C++23 起与访问控制无关）；引用成员布局同指针 |
| 公共初始序列 | 标准布局 struct 的布局兼容前缀；可经 union 的非活跃成员读取 |
| 首成员地址 | 标准布局类对象与首个非位域成员、各基类子对象指针可互转换 |
| 成员函数 | 全局模块中类内定义即 inline；cv/引用限定决定隐式对象形参；C++23 显式对象形参 |
| 静态成员 | 无 `this`；静态数据成员非 inline 时类内声明不是定义；`inline`/`constexpr` 可类内定义 |
| 位域 | 整型/枚举；布局实现定义；无地址；无名位域不是成员；零宽位域对齐到下一单元 |
| 类专属 new/delete | 隐式静态；虚析构使 delete 按动态类型选择；访问静态检查；数组 delete 不多态 |
| 嵌套类 | 是外围类的成员，但对象间无隐式关联 |
