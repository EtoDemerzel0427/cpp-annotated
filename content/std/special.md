---
title: 特殊成员函数
summary: 六种特殊成员函数是什么、何时被隐式声明（用户声明 X 对隐式 Y 的影响总表）、何时被定义为弃置、何时隐式定义；"同类"与"合格"、预期析构函数、潜在构造的子对象
status: draft
papers: P0848R3
related: class.ctor, class.copy.ctor, class.copy.assign, class.dtor, class.prop, dcl.fct.def.default, dcl.fct.def.delete, depr.impldec
tags: 特殊成员函数, Rule of five, 弃置函数, 平凡性
updated: 2026-10-17
---

C++ 类的一个核心特性是：**即使你一行代码都不写，编译器也会为类准备好构造、复制、移动、赋值、析构这些操作**。这些"编译器可以替你声明和定义"的成员函数就是**特殊成员函数**（special member functions）。本节是它们的总则；每种函数的细节在各自的子条款里：

| 特殊成员函数 | 典型签名 | 细节 |
|---|---|---|
| 默认构造函数 | `X()` | [[class.default.ctor]]（本站 [[class.ctor]]） |
| 复制构造函数 | `X(const X&)` | [[class.copy.ctor]] |
| 移动构造函数 | `X(X&&)` | [[class.copy.ctor]] |
| 复制赋值运算符 | `X& operator=(const X&)` | [[class.copy.assign]] |
| 移动赋值运算符 | `X& operator=(X&&)` | [[class.copy.assign]] |
| （预期）析构函数 | `~X()` | [[class.dtor]] |

注意**不在**表里的：转换构造函数、转换函数（[[class.conv]]）、预置的比较运算符（[[class.compare.default]]）——后者虽然也可以 `= default`，但不是特殊成员函数，不会被隐式声明（`operator==` 例外地会随 `operator<=>` 的预置而隐式声明，但那是 [[class.compare.default]] 的独立规则）。

## 哪些是特殊的、何时隐式声明（¶1）

¶1：默认构造函数、复制构造函数、移动构造函数、复制赋值运算符、移动赋值运算符和**预期析构函数**（prospective destructor）是特殊成员函数。

注 1：当程序没有显式声明它们时，实现会为某些类**隐式声明**它们，并在需要时**隐式定义**（[[dcl.fct.def.default]]）。

两条规范性规定：

1. **隐式声明的特殊成员函数在 *class-specifier* 的闭花括号 `}` 处声明**。这意味着在类定义内部（声明部分），它们"还不存在"；而在完整类上下文（如成员函数体）中则可以使用，因为那些部分在 `}` 之后才处理。
2. **程序不得定义隐式声明的特殊成员函数**。要提供自己的定义，必须先在类内**声明**它。

```cpp title="no-define-implicit.cpp" error
struct S { int x; };
S::S() : x(0) { }      // error: S::S() 是隐式声明的，不能在类外定义
```

## 可以显式引用（¶2）

¶2：程序可以**显式引用**隐式声明的特殊成员函数——调用它、对它取成员指针。标准例 1 展示了在派生类的赋值运算符中调用基类隐式声明的赋值运算符：

```cpp run title="call-implicit.cpp" ok
struct A { int a = 1; };                 // 隐式声明 A::operator=
struct B : A {
    int b = 2;
    B& operator=(const B& s);
};
B& B::operator=(const B& s) {
    this->A::operator=(s);               // OK: 调用隐式声明的 A::operator=
    b = s.b;
    return *this;
}

int main() {
    B x, y;
    y.a = 10;
    x = y;
    A& (A::*pm)(const A&) = &A::operator=;   // 也可以对隐式声明的复制赋值取成员指针
    (void)pm;
    return x.a - 10;
}
```

¶3 注 2：特殊成员函数影响类对象的创建、复制、移动、销毁方式，以及值如何转换为其他类型；它们往往被**隐式调用**。

¶4：特殊成员函数遵守通常的访问规则。标准例 2：把构造函数声明为 `protected`，就只有派生类和友元能用它创建对象——这是"只能被继承的基类"的惯用法；把析构函数声明为 `private`，就禁止了栈上对象（只能通过工厂 + 自定义删除来管理）。

## 隐式声明总表

这是本节最有用的一张表（它常被称为"Howard Hinnant 的表"，下面按当前草案的规则自己推导一遍）。行：用户**声明**了什么（`= default`、`= delete` 都算用户声明）；列：编译器对其他特殊成员函数的处理。

| 用户声明了 ↓ / 隐式的 → | 默认构造 | 析构 | 复制构造 | 复制赋值 | 移动构造 | 移动赋值 |
|---|---|---|---|---|---|---|
| （什么都没有） | 预置 | 预置 | 预置 | 预置 | 预置 | 预置 |
| 任意构造函数（非复制/移动） | **不声明** | 预置 | 预置 | 预置 | 预置 | 预置 |
| 默认构造函数 | — | 预置 | 预置 | 预置 | 预置 | 预置 |
| 析构函数 | 预置 | — | 预置（**弃用**） | 预置（**弃用**） | **不声明** | **不声明** |
| 复制构造函数 | **不声明** | 预置 | — | 预置（**弃用**） | **不声明** | **不声明** |
| 复制赋值运算符 | 预置 | 预置 | 预置（**弃用**） | — | **不声明** | **不声明** |
| 移动构造函数 | **不声明** | 预置 | **弃置** | **弃置** | — | **不声明** |
| 移动赋值运算符 | 预置 | 预置 | **弃置** | **弃置** | **不声明** | — |

每一格的出处：

- **默认构造函数**：若类没有**任何**用户声明的构造函数或构造函数模板，则隐式声明（[[class.default.ctor#1]]）。复制/移动构造函数也是构造函数，所以它们也会抑制默认构造函数。
- **析构函数**：若没有用户声明的预期析构函数，则隐式声明（[[class.dtor#2]]）。**没有任何东西能抑制它**。
- **复制构造函数**：若没有用户声明的复制构造函数，则隐式声明；若类声明了移动构造函数**或**移动赋值运算符，它被定义为**弃置**；否则预置——若类有用户声明的复制赋值运算符或析构函数，这种情形**已弃用**（[[class.copy.ctor#6]]、[[depr.impldec]]）。
- **复制赋值运算符**：对称地，有用户声明的移动构造或移动赋值时为弃置；有用户声明的复制构造或析构时预置但弃用（[[class.copy.assign#2]]）。
- **移动构造函数**：当且仅当没有用户声明的复制构造、复制赋值、移动赋值、析构函数时才隐式声明（[[class.copy.ctor#8]]）。
- **移动赋值运算符**：当且仅当没有用户声明的复制构造、移动构造、复制赋值、析构函数时才隐式声明（[[class.copy.assign#4]]）。

!!! note "\"不声明\"与\"弃置\"的区别"
    这两者在重载决议中的效果完全不同：

    - **不声明**移动构造函数时，用右值初始化会**退回到复制构造函数**（`const X&` 能绑定右值）——"移动"悄悄变成复制，程序依然能编译。
    - **弃置**的复制构造函数仍然**参与重载决议**，被选中就报错——这就是"声明了移动操作的类默认不可复制"（如 `std::unique_ptr`）。

```cpp run title="hinnant-table.cpp" ok
#include <type_traits>
using namespace std;

struct Dtor { ~Dtor() { } };                          // 用户声明析构函数
static_assert(is_copy_constructible_v<Dtor>);          // 复制：预置（弃用）
static_assert(is_move_constructible_v<Dtor>);          // "可移动"——但实际调用的是复制构造！
static_assert(!is_trivially_move_constructible_v<Dtor>);

struct CC { CC(const CC&) = default; };               // 用户声明复制构造
static_assert(!is_default_constructible_v<CC>);        // 默认构造不声明

struct MC { MC(MC&&) = default; };                    // 用户声明移动构造
static_assert(!is_copy_constructible_v<MC>);           // 复制构造：弃置
static_assert(!is_copy_assignable_v<MC>);              // 复制赋值：弃置
static_assert(!is_move_assignable_v<MC>);              // 移动赋值：不声明，而复制赋值弃置 ⇒ 不可移动赋值

struct MA { MA& operator=(MA&&) = default; };         // 用户声明移动赋值
static_assert(is_default_constructible_v<MA>);         // 默认构造仍然预置
static_assert(!is_move_constructible_v<MA>);           // 移动构造不声明，复制构造弃置

int main() { }
```

### 由此得出的编程准则

- **Rule of zero**：能不写就不写。让成员（`std::string`、`std::vector`、`std::unique_ptr`……）自己管理资源，类的六个特殊成员函数全部由编译器生成，自动正确、自动 `noexcept`、自动平凡（如果可能）。
- **Rule of five**：一旦需要自定义析构、复制或移动中的任何一个，通常需要**全部五个**都显式声明（可以 `= default` 或 `= delete`）。原因见上表：只写析构函数会让移动操作消失（移动退化为复制），而且隐式的复制是弃用的。
- **Rule of three**（C++98 的版本）：自定义析构、复制构造、复制赋值之一，就要三个都自定义。表中"弃用"的格子就是 C++11 为最终贯彻这条规则埋下的伏笔——[[depr.impldec]] 说未来可能把这些隐式定义改为弃置。

!!! pitfall "只加了一个析构函数，性能悄悄下降"
    `struct Big { std::vector<int> v; ~Big() { log(); } };`——用户声明析构函数使移动构造/移动赋值不再隐式声明，`std::vector<Big>` 扩容时、函数返回时（不能 NRVO 的情形），都会**复制**整个 `v`。修复：加上 `Big(Big&&) = default; Big& operator=(Big&&) = default;`（以及复制操作，否则它们变成弃置）。

## 同类的特殊成员函数（¶5）

¶5：两个特殊成员函数是**同类的**（of the same kind），若：

- ¶5.1 都是默认构造函数；
- ¶5.2 都是复制或移动构造函数，且第一个形参类型相同；
- ¶5.3 都是复制或移动赋值运算符，且第一个形参类型相同、cv 限定与引用限定（若有）相同。

这个概念只用于下面的"合格"定义：只有同类的函数才相互比较"谁更受约束"。`X(const X&)` 和 `X(X&)` 不是同类（形参类型不同），它们可以同时合格。

## 合格的特殊成员函数（¶6）

¶6：**合格的特殊成员函数**（eligible special member function）满足：

- ¶6.1 未被弃置；
- ¶6.2 关联约束（若有）得到满足；
- ¶6.3 不存在约束得到满足且**更受约束**（[[temp.constr.order]]）的同类特殊成员函数。

C++20 的 [[P0848R3]] 引入这个概念，是为了让特殊成员函数可以**按条件**平凡——通过 *requires-clause* 写多个版本，由约束挑选。"合格"被用在：

- **平凡可复制**的定义（[[class.prop#1]]）：只看合格的复制/移动操作；
- **隐式生存期类**（[[class.prop#8]]）：至少一个平凡的合格构造函数；
- [[dcl.fct.def.default#5]]：**预置的特殊成员函数如果既不是预期析构函数、也不是合格的，就被定义为弃置**。

### 预期析构函数与析构函数选择

析构函数不能重载（它没有形参），那么"带约束的多个版本"怎么办？C++20 的答案是：类中可以声明多个**预期析构函数**，在类定义结束时通过重载决议（空实参列表）**选出**一个作为真正的**析构函数**（[[class.dtor#4]]）。约束不满足的被淘汰，满足的里面选最受约束的：

```cpp run title="prospective-dtor.cpp" ok
#include <string>
#include <type_traits>

template<class T>
struct Holder {
    ~Holder() requires std::is_trivially_destructible_v<T> = default;   // 预期析构函数 #1
    ~Holder() { /* 非平凡清理 */ }                                       // 预期析构函数 #2
    T t;
};

static_assert(std::is_trivially_destructible_v<Holder<int>>);          // 选中 #1：平凡
static_assert(!std::is_trivially_destructible_v<Holder<std::string>>); // 选中 #2

int main() { Holder<std::string> h{"x"}; (void)h; }
```

`std::optional`、`std::variant`、`std::expected` 的现代实现都用这个机制在一个类模板里同时提供平凡与非平凡版本，而不再需要层层基类。

## 潜在构造的子对象（¶7）

¶7：一个类的**直接非静态数据成员**、**非虚直接基类**，以及（若类**不是抽象类**）**虚基类**，统称为它的**潜在构造的子对象**（potentially constructed subobjects）。

这个术语在"预置的 X 何时被定义为弃置"的规则中反复出现（[[class.default.ctor#2]]、[[class.copy.ctor#10]]、[[class.dtor#7]]）：只有当某个潜在构造的子对象"构造不了/析构不了"时，预置的特殊成员函数才被删除。

为什么抽象类要排除虚基类？虚基类子对象只由**最派生类**的构造函数初始化（[[class.base.init]]）。抽象类永远不可能是最派生类（不能创建抽象类的完整对象），所以它的构造函数**永远不会**真正去构造虚基类——即使虚基类没有可用的默认构造函数，抽象类的默认构造函数也没有理由被删除。

```cpp run title="abstract-vbase.cpp" ok
struct V { V(int) { } };                 // 没有默认构造函数
struct A : virtual V {                   // 抽象类
    virtual void f() = 0;
};                                       // A 的预置默认构造不因 V 而被删除（V 不是 A 的潜在构造子对象）
struct C : A {
    C() : V(42) { }                      // 最派生类负责构造虚基类
    void f() override { }
};

int main() { C c; (void)c; }
```

## 预置为弃置：总览

把各子条款的"defined as deleted"条件汇总如下（细节见各页）。共同的模式是：**如果编译器写出来的那个函数本身会是非良构的，就让它被删除，而不是报错**。这样类可以照常定义，只有真正使用那个操作时才报错。

| 预置的函数 | 被定义为弃置的主要条件 |
|---|---|
| 默认构造函数 | 有无默认成员初始化器的引用成员；有无初始化器且非 const-default-constructible 的 `const` 成员（非联合体）；某个潜在构造子对象（无初始化器）没有可用的默认构造函数；某个子对象的析构函数被删除或不可访问 |
| 复制/移动构造函数 | 某个潜在构造子对象的对应构造函数不可用（或变体成员的那个函数非平凡）；某个子对象的析构函数被删除或不可访问；复制构造函数且有右值引用成员 |
| 复制/移动赋值运算符 | 有 `const` 非类类型成员；有引用成员；某个直接成员或直接基类的对应赋值运算符不可用（或变体成员的非平凡） |
| 析构函数 | （非联合体）某个潜在构造子对象的析构函数被删除或不可访问；联合体的若干条件；虚析构函数找不到可用的 `operator delete` |
| 任意 | 既不是预期析构函数也不是合格的；或预置的预期析构函数没被选为析构函数（[[dcl.fct.def.default#5]]） |
| 复制构造/复制赋值 | 类声明了移动构造或移动赋值（[[class.copy.ctor#6]]、[[class.copy.assign#2]]） |

```cpp title="defaulted-deleted.cpp" error
struct R { int& r; };          // 默认构造：弃置；复制赋值：弃置；复制构造：OK
struct C { const int c; };     // 默认构造：弃置（const int 不是 const-default-constructible）；复制赋值：弃置

void f(R& a, R& b, C& x, C& y) {
    R r;        // error: 默认构造函数被隐式删除
    C c;        // error: 同上
    a = b;      // error: 复制赋值被隐式删除（引用成员不能"重新绑定"）
    x = y;      // error: 复制赋值被隐式删除（const 成员不能赋值）
    R r2 = a;   // OK: 复制构造没问题
}
```

### 被删除的预置移动操作被重载决议忽略

[[class.copy.ctor#10]] 注 4 与 [[class.copy.assign#7]] 注 4：**被定义为弃置的预置移动构造函数/移动赋值运算符会被重载决议忽略**（[[over.match.funcs]]）。否则，一个成员不可移动但可复制的类，其预置的移动构造函数被删除后会在右值初始化时被选中然后报错，而本来复制构造函数完全可以胜任。注意这只针对"**预置**后被定义为弃置"的移动操作；**显式** `= delete` 的移动操作仍参与重载决议：

```cpp run title="deleted-move-ignored.cpp" ok
#include <utility>

struct NM { NM() { } NM(const NM&) { } NM(NM&&) = delete; };   // 显式删除移动

struct Y {
    NM n;
    Y() = default;
    Y(const Y&) = default;
    Y(Y&&) = default;    // 因 n 的移动构造被删除而被定义为弃置 —— 被重载决议忽略
};

int main() {
    Y a;
    Y b = std::move(a);  // OK: 忽略弃置的 Y(Y&&)，选择 Y(const Y&)
    (void)b;
    // NM m = NM();      // OK（C++17 起复制消除，不调用移动构造）
    // NM m2 = std::move(m);   // error: 显式删除的 NM(NM&&) 参与决议并被选中
}
```

（Clang 会对 `Y(Y&&) = default;` 给出 `-Wdefaulted-function-deleted` 警告，提示它实际被删除了。）

## 预置函数何时被隐式定义

[[dcl.fct.def.default#5]]：非用户提供的预置函数（隐式声明的，或在类内首次声明处 `= default` 的），若未被定义为弃置，则在被 **odr-use** 或**常量求值需要**时**隐式定义**。类外 `= default`（即首次声明之后才预置）的函数是**用户提供的**，在预置处立即隐式定义——它因此**不是平凡的**：

```cpp run title="user-provided-default.cpp" ok
#include <type_traits>

struct A { A() = default; };       // 首次声明即预置：非用户提供 ⇒ 可以平凡
struct B { B(); };
B::B() = default;                  // 类外预置：用户提供 ⇒ 非平凡

static_assert(std::is_trivially_default_constructible_v<A>);
static_assert(!std::is_trivially_default_constructible_v<B>);

int main() { }
```

类外预置的用处（[[dcl.fct.def.default#5]] 注 2）：让函数定义留在 .cpp 中，从而保持**二进制接口稳定**（Pimpl 类的析构函数常这样做：`~Widget();` 在头文件中，`Widget::~Widget() = default;` 在 `Impl` 完整的 .cpp 中）。

隐式定义的特殊成员函数**都是 `constexpr` 的**（[[class.default.ctor#4]]、[[class.copy.ctor#13]]、[[class.copy.assign#10]]、[[class.dtor#9]]）——当然，能否在常量求值中实际调用，仍取决于它所做的事情是否满足常量求值的要求。

## 实现视角

!!! impl "编译器何时真正生成代码"
    隐式声明在 `}` 处发生，但**隐式定义是惰性的**：只有 odr-use 时才生成函数体。所以一个有不可复制成员的类，只要你不复制它，就不会因"复制构造函数生成失败"而报错——这正是"定义为弃置"机制的意义。Clang 用 `-Xclang -ast-dump` 可以看到隐式成员在类的 AST 中被标记为 `implicit`，并带有"needs implicit"之类的懒生成标志。

!!! impl "平凡的特殊成员函数不生成代码"
    平凡的复制构造/赋值被编译为 `memcpy`（或寄存器复制），平凡的默认构造和析构不生成任何代码。Itanium ABI 中，有非平凡复制构造、移动构造或析构函数的类（或复制移动构造全部被删除的类）在传参/返回时不能用寄存器，必须通过隐藏指针传递——这是"一个析构函数让性能下降"的 ABI 层面原因。

## 历史与演进

!!! history "历史与演进"
    - **C++98**：四个特殊成员函数（默认构造、复制构造、复制赋值、析构），规则简单：用户不声明就隐式声明。
    - **C++11**：加入**移动构造**与**移动赋值**；引入 `= default`、`= delete`；确立上面那张表，包括"声明移动操作则复制操作被删除"与"隐式复制在有用户声明的析构/复制时弃用"。
    - **C++20**：**合格**、**预期析构函数**与条件平凡（[[P0848R3]]）；隐式定义的特殊成员函数可以是 `constexpr` 的条件放宽，析构函数可以是 `constexpr` 的。
    - **C++23**：允许预置的复制赋值运算符使用显式对象形参（[[dcl.fct.def.default#2]]）。
    - **C++26 草案**：联合体的默认构造/析构不再因变体成员非平凡而被删除（"平凡联合体"）；"弃用的隐式复制"至今仍未改为删除。

## 陷阱

!!! pitfall "以为 `= default` 一定意味着\"能用\""
    `= default` 只是请求编译器按规则生成；如果规则要求删除（比如有引用成员的类的复制赋值），它就会被删除。Clang 的 `-Wdefaulted-function-deleted`（默认开启）能提示这种情况。

!!! pitfall "以为声明了构造函数模板就不会有隐式复制构造函数"
    模板永远不是复制/移动构造函数（[[class.copy.ctor#1]]）。`template<class T> X(T&&);` 不会抑制隐式复制构造函数——但它在重载决议中可能比 `X(const X&)` 更匹配非 const 左值，这是"完美转发构造函数劫持复制"的经典问题，见 [[class.copy.ctor]]。

!!! pitfall "预置函数的形参 const 与隐式版本不一致"
    [[dcl.fct.def.default#2]] 只允许预置的特殊成员函数与"本应隐式声明的版本"在少数方面不同。其中关于 `const` 的两条：若隐式版本的形参是 `const C&`，你可以预置一个形参为 `C&` 的版本（¶2.4）；反过来，若隐式版本是 `C&`（因为某个成员只有 `M(M&)` 形式的复制构造函数），你预置一个 `const C&` 版本时——在首次声明处预置则它被**定义为弃置**，在类外预置则程序**非良构**（¶2.5）。

## 思考题

!!! question "思考题 1"
    下面这个类有哪些可用的特殊成员函数？

    ```cpp
    #include <string>
    struct S {
        S(int);
        S& operator=(const S&) = default;
        std::string s;
    };
    ```

<details markdown="1">
<summary>答案</summary>

- 默认构造函数：有用户声明的构造函数 `S(int)` ⇒ **不声明**。
- 复制构造函数：隐式声明并预置，但由于有用户声明的复制赋值运算符，**已弃用**（Clang `-Wdeprecated-copy` 会警告）。
- 复制赋值：用户声明（预置）。
- 移动构造、移动赋值：有用户声明的复制赋值 ⇒ **都不声明**。`S b = std::move(a);` 会调用复制构造函数，`s` 被复制而不是移动。
- 析构函数：隐式预置。
</details>

!!! question "思考题 2"
    为什么"声明了析构函数"不会让复制操作被删除，而"声明了移动操作"会？这两条规则在 C++11 中不对称的原因是什么？

<details markdown="1">
<summary>答案</summary>

**向后兼容**。C++98 代码中大量存在"只写了析构函数"的类（违反 Rule of three 但能工作，或者析构函数只是打日志），如果 C++11 让它们的复制操作被删除，海量既有代码会突然无法编译。所以只能把它标为"弃用"，留待将来。而移动操作是 C++11 新增的：声明了移动操作的类一定是新代码，新代码的作者显然在思考资源语义，此时自动生成的逐成员复制很可能是错的（比如对独占资源的浅复制），所以可以安全地默认删除。
</details>

!!! question "思考题 3"
    `struct A { int a; };` 之后写 `auto pm = &A::operator=;` 能编译吗？

<details markdown="1">
<summary>答案</summary>

不能。`A` 隐式声明了**两个** `operator=`：复制赋值 `A& operator=(const A&)` 和移动赋值 `A& operator=(A&&)`，`&A::operator=` 是一个重载集，用 `auto` 接收无法推导出唯一的类型。需要像 `call-implicit.cpp` 那样指定目标类型：`A& (A::*pm)(const A&) = &A::operator=;`。这也说明 ¶2 所说的"可以对隐式声明的特殊成员函数取成员指针"与普通重载函数取地址的规则（[[over.over]]）完全一样。
</details>

## 小结

| 概念 | 要点 |
|---|---|
| 特殊成员函数 | 默认构造、复制构造、移动构造、复制赋值、移动赋值、（预期）析构 |
| 隐式声明时机 | 类定义的 `}` 处；不能在类外定义隐式声明的函数 |
| 抑制关系 | 任意构造函数抑制默认构造；复制/析构抑制移动；移动使复制被删除；复制/析构使另一复制操作"弃用" |
| 同类 | 同为默认构造；或同为复制/移动构造且首形参类型相同；或同为赋值且首形参与限定相同 |
| 合格 | 未弃置、约束满足、无更受约束的同类函数；决定平凡可复制等性质 |
| 预期析构函数 | 可有多个，类结束时按重载决议选出析构函数 |
| 潜在构造的子对象 | 直接数据成员、非虚直接基类、（非抽象类的）虚基类 |
| 预置为弃置 | 编译器生成的版本会非良构时被删除；被删除的预置移动操作被重载决议忽略 |
| 隐式定义 | 惰性：odr-use 或常量求值需要时；隐式定义的都是 `constexpr` |
