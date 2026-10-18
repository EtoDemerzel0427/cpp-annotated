---
title: 异常说明
summary: 异常说明是"函数不会以异常退出"这一谓词；noexcept-specifier 的语法；无说明时默认潜在抛出，但析构函数、释放函数、首次声明即预置的函数例外；虚函数覆盖的约束；潜在抛出表达式的精确定义；隐式声明/预置特殊成员如何推导异常说明；何时"需要"计算异常说明
status: done
since: c++11
papers: N3050, P0003R5, P0012R1, P1286R2
related: except.handle, except.terminate, expr.unary.noexcept, dcl.fct, conv.fctptr, class.virtual, class.dtor, basic.link, temp.explicit, toolchain/exception-implementation
tags: 异常, noexcept, 异常说明, 函数类型
updated: 2026-10-17
---

本节规定函数的**异常说明**（exception specification）：一个关于"这个函数**能否**以异常退出"的布尔谓词。它有两个用途：

1. **契约**：声明了"不会抛出"的函数若真的让异常逃出，程序调用 `std::terminate`（[[except.handle#7]]）——不是 UB，而是确定的终止。
2. **可查询的编译期信息**：通过 `noexcept` 运算符（[[expr.unary.noexcept]]）和类型特征，泛型代码可以根据"某个操作会不会抛"选择不同算法——最著名的是 `std::vector` 扩容时"移动构造不抛就移动，否则拷贝"，以维持强异常安全保证。

异常说明是**函数类型的一部分**（C++17 起，[[dcl.fct#13]]）。

## 异常说明是一个谓词（¶1–¶3）

¶1 "函数不能以异常退出"这个谓词称为函数的**异常说明**。谓词为假，函数具有**潜在抛出的异常说明**（[[g:potentially-throwing-exception-specification]]）；为真，具有**非抛出的异常说明**（[[g:non-throwing-exception-specification]]）。异常说明或者**隐式定义**，或者通过函数声明符后缀的 *noexcept-specifier* **显式定义**：

```text
noexcept-specifier:
    noexcept ( constant-expression )
    noexcept
```

注意这里的抽象层次：异常说明只区分"可能抛 / 不会抛"两种，**不**列出会抛哪些类型。这是 C++11 吸取 C++98 动态异常说明 `throw(A, B)` 教训后的选择（见"历史与演进"）。

¶2 *constant-expression* 必须是类型为 `bool` 的**按语境转换的常量表达式**（[[expr.const.const]]）——这意味着**不允许窄化**：

```cpp title="noexcept-narrowing.cpp" error
void f() noexcept(sizeof(char[2]));  // error: 值 2 转换到 bool 是窄化
void g() noexcept(sizeof(char));     // OK: 值 1 转换到 bool 不是窄化
```

为什么这么严格？因为 `noexcept(...)` 里常写的是复杂的条件表达式，`noexcept(sizeof(T))` 这类手误（本意可能是 `sizeof(T) > 4`）若被默默当成 `true`，会把一个本应潜在抛出的函数错标为不抛出，后果是运行时 terminate。

¶2 还有一句消歧规则：紧跟在 `noexcept` 之后的 `(` 属于 *noexcept-specifier*，**不会**开始一个初始化器。考虑函数指针变量的声明：

```cpp title="noexcept-paren.cpp" ok
void target() noexcept;
void (*p1)() noexcept (false);      // ( 属于 noexcept：p1 是潜在抛出函数的指针，没有初始化器
void (*p2)() noexcept = target;     // 要初始化，必须用 = 或 {}
void (*p3)() noexcept {target};
```

不加这条规则的话，`noexcept (false)` 中的 `(false)` 在语法上也可以被读作"用 `false` 直接初始化 `p1`"。

不带表达式的 `noexcept` 等价于 `noexcept(true)`。

¶3 若 *noexcept-specifier* 出现在函数类型中，其常量表达式就是该**类型**的异常说明。这为"函数类型带异常说明"（[[dcl.fct#1]]：`noexcept` 出现在函数类型中当且仅当异常说明是非抛出的）提供了语义。

## 没有 noexcept-specifier 时（¶4）

¶4 不带 *noexcept-specifier* 的函数声明具有**潜在抛出**的异常说明，**除非**它是：

- 析构函数（¶8）；
- 释放函数（¶10）；
- 在**首次声明**时就被预置（`= default`）的函数（¶7、¶9、¶11）。

对这三类，异常说明按下文规则**隐式**确定，并且该函数的**其他任何声明都不得**带 *noexcept-specifier*：

```cpp title="dtor-redecl.cpp" error
struct S { ~S(); };           // 隐式异常说明（这里是 noexcept(true)）
S::~S() noexcept {}           // error: 其他声明不得带 noexcept-specifier
```

本机 Clang 23 对此只给出**警告**（`-Wimplicit-exception-spec-mismatch`）。标准说的"必须诊断"只要求给出一条诊断信息（[[intro.compliance]]），警告在形式上满足这一要求；但它照样编译通过，读者不应把"能编译"当作"良构"。

!!! lawyer "反过来写呢？"
    `struct T { ~T() noexcept; }; T::~T() {}`——第二个声明没有 *noexcept-specifier*，是析构函数，于是"其他声明不得带 *noexcept-specifier*"，而第一个声明带了。按字面读法同样违规。Clang 23 对这种写法也只是警告。为避免争议：析构函数的 `noexcept` 要么所有声明都不写（依赖隐式），要么……也只能都不写——最稳妥的做法是只在需要 `noexcept(false)` 时才写，并且**只写在一处声明**上，不要分离定义。

¶4 后半处理**显式实例化**（[[temp.explicit]]）：显式实例化中**可以**写 *noexcept-specifier* 但不必写；若写了，异常说明必须与该函数所有其他声明的相同。只有在**同一个翻译单元内**不一致时才要求诊断（跨 TU 不一致是 IFNDR）。

```cpp title="explicit-inst.cpp" error
template<class T> void tf(T) noexcept(sizeof(T) > 1) {}

template void tf<int>(int) noexcept;     // OK: sizeof(int) > 1，一致
template void tf<char>(char);            // OK: 不写也行
template void tf<char>(char) noexcept;   // error: tf<char> 的异常说明是 noexcept(false)
```

对普通函数，各声明的异常说明不一致是**类型**不一致，由 [[basic.link#11]] 处理（"同一函数的两个声明必须有相同的类型"）：

```cpp title="redecl-mismatch.cpp" error
void k();
void k() noexcept;    // error: 与之前的声明类型不同
```

## 虚函数覆盖（¶5）

¶5 若虚函数具有非抛出的异常说明，则任何派生类中**覆盖**它的函数的所有声明（含定义）也必须是非抛出的——除非覆盖函数被定义为删除的。

```cpp title="virtual-noexcept.cpp" error
struct B {
    virtual void f() noexcept;
    virtual void g();
    virtual void h() noexcept = delete;
};

struct D : B {
    void f();              // error: B::f 不抛出，覆盖者却潜在抛出
    void g() noexcept;     // OK: 收紧是允许的
    void h() = delete;     // OK: 删除的函数例外
};
```

这是 **Liskov 替换原则**的体现：通过 `B&` 调用 `f()` 的代码依赖"不会抛出"的承诺（编译器甚至可能据此省掉调用点的清理代码），派生类不能悄悄放松它。反方向（基类可能抛、派生类保证不抛）是收紧承诺，安全。

最常见的触发场景是**虚析构函数**：析构函数默认不抛出，若某个成员的析构函数是 `noexcept(false)`，派生类的隐式析构函数就变成潜在抛出的，进而与基类的虚析构函数冲突（见 ¶12 的例子后半）。

## 潜在抛出的表达式（¶6）

¶6 定义表达式 `E` 是**潜在抛出的**（[[g:potentially-throwing-expression]]），当：

- ¶6.1 `E` 是函数调用，其后缀表达式的类型是**具有潜在抛出异常说明的**函数类型或函数指针类型；
- ¶6.2 `E` **隐式调用**了一个具有潜在抛出异常说明的函数——例如重载运算符、*new-expression* 中的分配函数、为函数实参调用的构造函数、析构函数；
- ¶6.3 `E` 是 *throw-expression*；
- ¶6.4 `E` 是转换到**引用**类型、且需要运行时检查的 `dynamic_cast`（失败时抛 `std::bad_cast`）；
- ¶6.5 `E` 是 `typeid` 应用于（可带括号的）内建一元 `*` 运算符，而该运算符作用于指向多态类类型的指针（空指针时抛 `std::bad_typeid`）；
- ¶6.6 `E` 的某个非未求值操作数的**直接子表达式**是潜在抛出的。

这是一个纯**静态**、**保守**的判断：它只看类型上的异常说明，不看函数实际会不会抛。`noexcept` 运算符（[[expr.unary.noexcept]]）的结果就是"操作数的完整表达式**不是**潜在抛出的"。

```cpp title="potentially-throwing.cpp" ok
#include <new>
#include <typeinfo>

struct Poly { virtual ~Poly(); };
struct Der : Poly {};
struct Thr { ~Thr() noexcept(false); };
Thr make_thr() noexcept;

void may();
int may_int();
void never() noexcept;
int x;
Poly* pp;

static_assert(!noexcept(may()));                    // 6.1
static_assert( noexcept(never()));
static_assert(!noexcept(new int));                  // 6.2: operator new 潜在抛出
static_assert( noexcept(new (&x) int));             // 6.2: 定位 operator new 是 noexcept
static_assert(!noexcept(throw 1));                  // 6.3
static_assert(!noexcept(dynamic_cast<Der&>(*pp)));  // 6.4
static_assert( noexcept(dynamic_cast<Der*>(pp)));   // 转换到指针：失败返回空指针，不抛
static_assert(!noexcept(typeid(*pp)));              // 6.5
static_assert( noexcept(typeid(pp)));               // 不是对多态 glvalue 解引用
static_assert(!noexcept(make_thr()));               // 6.2: 临时量的析构函数潜在抛出
static_assert( noexcept(x + 1));
static_assert( noexcept(sizeof(may_int())));        // sizeof 的操作数是未求值操作数（6.6）
```

两个容易忽略的点：

- **析构函数也算**：`make_thr()` 本身是 `noexcept` 的，但 `noexcept` 运算符对 prvalue 操作数施加临时量实质化（[[expr.unary.noexcept#1]]），由此产生的临时量在完整表达式结束时被析构，而 `Thr` 的析构函数潜在抛出。
- **未求值操作数不算**（¶6.6 的"不是未求值操作数"）：`noexcept(sizeof(may_int()))` 是 `true`。

（上面的代码在 Clang 下会对 `new`、`throw` 等出现在未求值操作数中给出"副作用无效"的警告，这是预期的。）

## 隐式声明与预置函数的异常说明（¶7–¶11）

对于编译器生成的函数，异常说明由它**实际会调用的函数**推导出来——"它会调用潜在抛出的函数吗？"

### 构造函数（¶7）

¶7 隐式声明的构造函数，或在首次声明时预置、且没有 *noexcept-specifier* 的构造函数，**当且仅当**下列构造中有潜在抛出的，具有潜在抛出的异常说明：

- ¶7.1 其隐式定义中，为初始化**潜在构造子对象**（基类、非静态成员，[[class.base.init]]）而经重载决议选中的构造函数的调用；
- ¶7.2 这种初始化的子表达式，例如默认实参表达式；
- ¶7.3 对默认构造函数：**默认成员初始化器**。

注 1 解释了一个看似遗漏的地方：构造函数中途抛出时，已构造子对象的**析构函数**会被调用（[[except.ctor#3]]），但它们的异常说明**不**参与构造函数异常说明的推导——因为那种情况下若析构函数再抛出，会直接 `std::terminate`（[[except.throw#9]]），异常不会逃出构造函数。

### 析构函数（¶8）

¶8 隐式声明的析构函数，或**没有** *noexcept-specifier* 的析构函数（包括用户提供的！），当且仅当以下情况之一时是潜在抛出的：

- 某个**潜在构造子对象**的析构函数具有潜在抛出的异常说明；
- 析构函数是**虚**的，且某个**虚基类**的析构函数具有潜在抛出的异常说明。

!!! std
    The exception specification for an implicitly-declared destructor, or a destructor without a *noexcept-specifier*, is potentially-throwing if and only if any of the destructors for any of its potentially constructed subobjects has a potentially-throwing exception specification …

这就是"**析构函数默认是 `noexcept` 的**"的准确含义：即使你自己写了函数体 `~T() { ... }`，只要没写 `noexcept(false)` 且所有子对象的析构函数都不抛，它就是 `noexcept(true)`——函数体里的 `throw` 会导致 `std::terminate`。

```cpp title="dtor-implicit-noexcept.cpp" ok
#include <type_traits>

struct User { ~User() { /* 即使这里有 throw，也是 noexcept */ } };
static_assert(std::is_nothrow_destructible_v<User>);

struct Loud { ~Loud() noexcept(false); };
struct Holder { Loud l; };                     // 隐式析构函数：子对象潜在抛出 ⇒ 潜在抛出
static_assert(!std::is_nothrow_destructible_v<Holder>);

struct Holder2 { Loud l; ~Holder2() {} };      // 用户提供、无说明：同样按子对象推导
static_assert(!std::is_nothrow_destructible_v<Holder2>);
```

为什么析构函数要默认不抛出？因为析构函数会在栈回溯中被调用，那时再抛出就是 `std::terminate`（[[except.throw#9]]）；标准库容器也要求元素类型的析构函数不抛出（[[res.on.exception.handling]]）。让"不抛出"成为默认值，绝大多数代码自动获得正确的语义，并让编译器省掉调用方的清理代码。C++11 引入这条规则时，它改变了旧代码中"析构函数抛出异常"的行为：从可捕获变成 terminate。

### 赋值运算符（¶9）

¶9 隐式声明的赋值运算符，或首次声明即预置且无 *noexcept-specifier* 的赋值运算符，当且仅当其隐式定义中调用的某个赋值运算符是潜在抛出的时，具有潜在抛出的异常说明。

### 释放函数（¶10）

¶10 没有显式 *noexcept-specifier* 的**释放函数**（`operator delete` 系列）具有非抛出的异常说明。释放函数在 `delete` 表达式、`new` 表达式失败回滚（[[except.ctor#5]]）中被调用，后者正处于异常传播当中，不允许再抛。

```cpp title="dealloc-noexcept.cpp" ok
#include <cstddef>

struct Pool {
    static void* operator new(std::size_t);
    static void  operator delete(void*);       // 隐式 noexcept
};
static_assert(noexcept(Pool::operator delete(nullptr)));
static_assert(!noexcept(Pool::operator new(1)));
```

### 比较运算符与后缀自增/自减（¶11）

¶11 首次声明即预置、无 *noexcept-specifier* 的**比较运算符函数**（[[class.compare]]：`==`、`<=>` 及由它们改写的 `!=`、`<` 等的预置版本）和**后缀自增/自减运算符函数**（C++23 之后可以预置，[[over.inc]]），当且仅当其隐式定义中有潜在抛出的表达式时，是潜在抛出的。

```cpp title="defaulted-compare.cpp" ok
#include <string>

struct P { int a, b; bool operator==(const P&) const = default; };
static_assert(noexcept(P{} == P{}));

struct Q {
    std::string s;
    auto operator<=>(const Q&) const = default;
    bool operator==(const Q&) const = default;
};
static_assert(noexcept(Q{} == Q{}) == noexcept(std::string{} == std::string{}));
```

### 标准的综合例子（¶12）

¶12 的例子把以上规则放在一起（适当改编并验证）：

```cpp title="except-spec-example.cpp" ok
#include <type_traits>

struct A {
    A(int = (A(5), 0)) noexcept;
    A(const A&) noexcept;
    A(A&&) noexcept;
    ~A();                                 // 隐式 noexcept(true)
};
struct B {
    B() noexcept;
    B(const B&) = default;                // 隐式说明为 noexcept(true)
    B(B&&, int = (throw 42, 0)) noexcept; // 默认实参会抛出
    ~B() noexcept(false);
};
int n = 7;
struct D : public A, public B {
    int* p = new int[n];
    // D::D()         潜在抛出：默认成员初始化器中的 new（bad_alloc/bad_array_new_length）
    // D::D(const D&) 非抛出
    // D::D(D&&)      潜在抛出：B(B&&, int) 的默认实参会抛出（¶7.2）
    // D::~D()        潜在抛出：B::~B 潜在抛出
};

static_assert(!std::is_nothrow_default_constructible_v<D>);
static_assert( noexcept(D(std::declval<const D&>())) == false);   // 见下方说明
static_assert(!std::is_nothrow_move_constructible_v<D>);
static_assert(!std::is_nothrow_destructible_v<D>);
```

注意第二个断言：`D(const D&)` 的异常说明本身是非抛出的，但 `noexcept(D(...))` 这个**表达式**还要算上临时量 `D` 的析构——`D::~D()` 潜在抛出——所以结果是 `false`。要单独查询构造函数，可以用 `noexcept(::new (ptr) D(...))` 这种不产生临时量的形式。这正是 ¶6 中"析构函数也算"的另一个例子。

例子的后半句：若 `A::~A()` 是**虚**的，程序非良构——`D::~D()`（因 `B::~B` 而潜在抛出）会覆盖一个非抛出的虚函数，违反 ¶5。

## 何时"需要"异常说明（¶13）

¶13 对预置函数（以及模板等），异常说明并不总是立即计算，而是在**需要**时计算。以下情况视为需要：

- ¶13.1 在表达式中，该函数被重载决议（[[over.match]]、[[over.over]]）选中；
- ¶13.2 该函数被 odr-use（[[basic.def.odr]]）；
- ¶13.3 要与另一个声明的异常说明比较（例如显式特化、覆盖的虚函数）；
- ¶13.4 该函数被定义；
- ¶13.5 该函数被一个**反射**表示 {{c++26}}（[[meta.reflection]]）；
- ¶13.6 一个调用该函数的预置函数需要异常说明。

注 2：预置的声明不需要立即计算基类成员函数的异常说明，直到派生类函数的隐式异常说明被需要时为止；而**显式**写出的 *noexcept-specifier* 需要隐式异常说明来比较。最后一句：预置函数的异常说明**只在需要时**按上述规则求值。

为什么要"延迟"？因为计算一个预置函数的异常说明可能需要**完整的类型**和**默认成员初始化器**。在类定义内部，这些可能还没准备好；若在声明时就急于计算，会出现循环依赖（例如嵌套类的默认构造函数的异常说明依赖外围类中尚未解析的默认成员初始化器）。延迟到"真的有人问"时再算，解决了大部分这类问题。

对显式预置并写了 `noexcept` 的函数，C++20 起两者不一致时**显式说明优先**（[[P1286R2]]）：

```cpp title="defaulted-explicit-noexcept.cpp" ok
#include <type_traits>

struct Base { Base() noexcept(false); };
struct D1 : Base { D1() = default; };              // 隐式推导：潜在抛出
struct D2 : Base { D2() noexcept = default; };     // 显式 noexcept：C++20 起允许，以显式为准
static_assert(!std::is_nothrow_default_constructible_v<D1>);
static_assert( std::is_nothrow_default_constructible_v<D2>);
```

（`D2` 的默认构造函数若真的从 `Base()` 收到异常，会 `std::terminate`。）

## 异常说明是函数类型的一部分

[[dcl.fct#13]] 规定异常说明是函数类型的一部分（C++17 起，[[P0012R1]]）。推论：

| 方面 | 后果 |
|---|---|
| 类型 | `void()` 与 `void() noexcept` 是不同的类型 |
| 转换 | "指向 `noexcept` 函数的指针" → "指向函数的指针"是一种隐式转换（**函数指针转换**，[[conv.fctptr]]）；反方向不行 |
| 重载 | 不能仅凭异常说明重载同名函数（那是同一函数的冲突声明），但可以按**形参**是否 `noexcept` 函数指针重载 |
| 模板推导 | `template<class F> void f(F)`：传入 `noexcept` 函数时 `F` 推导为 `void(*)() noexcept` |
| 名字修饰 | Itanium ABI 用 `Do` 标记 `noexcept` 函数类型，例如 `void take(void (*)() noexcept)` 修饰为 `_Z4takePDoFvvE` |
| `typedef`/别名 | C++17 之前 `typedef void (*fp)() noexcept;` 非良构，现在合法 |

```cpp title="noexcept-in-type.cpp" ok
#include <type_traits>

void g() noexcept;
void h();

static_assert(!std::is_same_v<decltype(g), decltype(h)>);

void (*p1)() = g;               // OK: 函数指针转换，丢弃 noexcept
// void (*p2)() noexcept = h;   // error: 不能凭空添加 noexcept

void take(void (*)());
void take(void (*)() noexcept); // OK: 形参类型不同，是两个重载

template<class F> constexpr bool is_nx(F) { return std::is_nothrow_invocable_v<F>; }
static_assert(is_nx(g) && !is_nx(h));
```

!!! impl "ABI 影响"
    由于 `noexcept` 进入了函数类型和名字修饰，C++14 与 C++17 编译的代码在涉及"`noexcept` 函数指针作为形参/模板实参"的接口上会产生不同的符号名（本机实测 `void take(void (*)() noexcept)` 修饰为 `_Z4takePDoFvvE`，而无 `noexcept` 版本是 `_Z5take2PFvvE` 这种形式）。GCC 在 C++17 推出时为此提供了 `-Wnoexcept-type` 警告来提示这类 ABI 变化。

## `noexcept` 对代码生成的影响

`noexcept` 不只是文档。编译器可以利用它：

1. **调用方**：调用 `noexcept` 函数的地方不需要为"它抛出时"准备着陆点。若一个函数调用的全是 `noexcept` 函数，它可能完全不需要 LSDA。
2. **被调方**：`noexcept` 函数本身需要一个"捕获一切 → `std::terminate`"的着陆点（Clang 生成对 `__clang_call_terminate` 的调用），但可以省掉内部对象的清理代码——因为 [[except.terminate#2]] 允许在这种情况下不回溯（或只部分回溯）。
3. **库**：`std::vector`、`std::optional` 等通过 `std::is_nothrow_move_constructible` 选择算法。

第 3 点的效果是最直观的：

```cpp run title="vector-move-if-noexcept.cpp" ok
#include <cstdio>
#include <vector>

template<bool NX>
struct W {
    W() = default;
    W(const W&) { std::puts("  copy"); }
    W(W&&) noexcept(NX) { std::puts("  move"); }
};

int main() {
    std::puts("noexcept move:");
    std::vector<W<true>> a(1);  a.reserve(2);    // 扩容时移动
    std::puts("potentially-throwing move:");
    std::vector<W<false>> b(1); b.reserve(2);    // 扩容时拷贝（维持强保证）
}
```

输出 `noexcept move: move` 与 `potentially-throwing move: copy`。忘记给移动构造函数加 `noexcept`，`vector` 就会默默地拷贝——对大对象是严重的性能问题。预置的移动构造函数会按 ¶7 自动推导，这是推荐写 `= default` 的又一个理由。

第 2 点见 [[toolchain/exception-implementation]] 中的汇编实例。

## 历史与演进

!!! history
    - **C++98/03：动态异常说明**。`void f() throw(A, B);` 声明 `f` 只抛出 `A` 或 `B`；违反时调用 `std::unexpected()`。`throw()` 表示不抛出。问题：检查在**运行时**进行（每个这样的函数都需要一个隐式的 try/catch），列出的类型组合在模板中几乎无法写对，且编译器无法据此优化。实践中几乎只有 `throw()` 被使用。
    - **C++11：`noexcept`**（[[N3050]]）。引入 `noexcept`/`noexcept(expr)` 说明符和 `noexcept` 运算符；违反时直接 `std::terminate`，不再调用 `unexpected`；析构函数默认 `noexcept`。动态异常说明被弃用。
    - **C++17**：异常说明成为函数类型的一部分（[[P0012R1]]）；删除动态异常说明 `throw(T...)`，只保留 `throw()` 作为 `noexcept(true)` 的弃用别名（[[P0003R5]]）；`std::unexpected` 等随之删除。
    - **C++20**：`throw()` 也被删除（随 C++17 弃用特性清理一并移除）。显式预置的函数可以带与隐式推导不同的异常说明（[[P1286R2]]）。
    - **C++23 之后**：预置的后缀自增/自减运算符纳入 ¶11；¶13 增加"被反射表示"的情形 {{c++26}}。

!!! impl "编译器对旧语法的现状"
    本机 Clang 23 在 `-std=c++2c` 下拒绝 `throw(int)`（诊断 "ISO C++17 does not allow dynamic exception specifications"，并建议改成 `noexcept(false)`），但对 `throw()` **静默接受**，即使加了 `-pedantic`，并把它当作 `noexcept(true)`。按当前标准，`throw()` 在语法上就不存在。

## 陷阱

!!! pitfall "以为 `noexcept` 会在编译期检查"
    `void f() noexcept { may_throw(); }` 完全合法（[[except.handle#7]] 注 3）。`noexcept` 是承诺，不是检查；违约的后果是运行时 `std::terminate`。

!!! pitfall "条件 `noexcept` 中漏掉析构"
    `noexcept(noexcept(T(std::declval<T>())))` 测的是"构造一个临时 `T` 并析构它"，而不仅仅是移动构造。对析构函数可能抛出的类型，这会给出出乎意料的 `false`。标准库的 `std::is_nothrow_move_constructible` 规定为 `is_nothrow_constructible_v<T, T>`，其定义同样包含析构（这是一个已知的标准库设计争议点）。

!!! pitfall "`noexcept(false)` 析构函数的传染性"
    一个成员的 `~M() noexcept(false)` 会让包含它的所有类的隐式析构函数都变成潜在抛出的（¶8），进而让这些类不能被放进要求 `noexcept` 析构的上下文、不能覆盖 `noexcept` 的虚析构函数（¶5）。

## 思考题

!!! question "思考题 1"
    下面的 `noexcept` 运算符结果是什么？

    ```cpp
    struct S { S(int) noexcept; ~S() noexcept(false); };
    void f(S) noexcept;
    bool b = noexcept(f(1));
    ```

<details markdown="1">
<summary>答案</summary>

`false`。`f(1)` 隐式调用构造函数 `S(int)` 初始化形参（不抛出），调用 `f`（不抛出），但形参对象最终要被析构，而 `~S()` 是潜在抛出的（¶6.2 明确把"为函数实参调用的构造函数"和"析构函数"都列为隐式调用的函数）。形参在哪里析构是实现定义的（[[expr.call]]），但不论在哪，它都是这个调用表达式隐式调用的析构函数。
</details>

!!! question "思考题 2"
    `struct X { virtual ~X(); }; struct Y : X { std::vector<int> v; };` 中 `Y` 的析构函数的异常说明是什么？若把 `std::vector<int>` 换成一个 `~M() noexcept(false)` 的类型 `M` 呢？

<details markdown="1">
<summary>答案</summary>

`X::~X()` 无说明 ⇒ 按 ¶8 推导：`X` 没有子对象 ⇒ 非抛出。`Y` 的隐式析构函数：子对象 `X` 和 `std::vector<int>` 的析构函数都不抛 ⇒ 非抛出。

换成 `M` 后，`Y::~Y()` 因 `M::~M()` 而潜在抛出；但它覆盖了 `X::~X()`——一个非抛出的虚函数——违反 ¶5，程序非良构。这正是 ¶12 例子后半句描述的情形。
</details>

## 小结

| 函数 | 默认异常说明 |
|---|---|
| 普通函数（无说明） | 潜在抛出 |
| `noexcept` / `noexcept(true)` | 非抛出 |
| 析构函数（无说明，含用户提供的） | 子对象（及虚基类）析构函数都不抛 ⇒ 非抛出 |
| 释放函数（无说明） | 非抛出 |
| 隐式声明 / 首次声明即预置的构造函数、赋值运算符 | 隐式定义中调用的函数（含默认实参、默认成员初始化器）都不抛 ⇒ 非抛出 |
| 首次声明即预置的比较运算符、后缀 `++`/`--` | 隐式定义中的表达式都不抛 ⇒ 非抛出 |
| 覆盖非抛出虚函数的函数 | 必须非抛出（删除的除外） |
