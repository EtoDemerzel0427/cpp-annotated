---
title: 复制/移动赋值运算符
summary: 什么是复制/移动赋值运算符（含按值形参与显式对象形参）、隐式声明的条件与形式、何时被定义为弃置（const/引用成员、变体成员非平凡）、何时平凡、隐式定义的逐成员赋值与联合体按字节复制；自赋值与引用限定的赋值
status: draft
related: special, class.copy.ctor, over.assign, expr.assign, dcl.fct.def.default, depr.impldec, class.prop, basic.life
tags: 赋值运算符, 复制赋值, 移动赋值, 平凡, 自赋值
updated: 2026-10-17
---

赋值与构造的根本区别在于：构造把原始存储变成对象，**赋值则替换一个已经存在的对象的值**。所以赋值运算符必须处理旧值，包括释放旧资源、处理自赋值、保证异常安全。本节的结构与 [[class.copy.ctor]] 平行：识别（¶1、¶3）、隐式声明（¶2、¶4–¶6）、弃置（¶7）、隐藏（¶8）、平凡（¶9）、隐式定义（¶10–¶14）。

## 复制赋值运算符的识别（¶1）

¶1 规定，用户声明的**复制赋值运算符** `X::operator=` 是类 `X` 的非静态、非模板成员函数，恰有一个非对象形参，其类型为 `X`、`X&`、`const X&`、`volatile X&` 或 `const volatile X&`。

与复制构造函数相比，有两点不同：

1. 允许按值形参 `X`。`X& operator=(X other)` 是复制赋值运算符，复制并交换（copy-and-swap）惯用法就是这样写的。构造函数不能这样写（[[class.copy.ctor#5]]），因为按值传参需要复制构造，会递归调用自己；赋值运算符则不存在这个问题。
2. 计数的是非对象形参。C++23 起赋值运算符可以有显式对象形参（`X& operator=(this X& self, const X& other)`），这个 `this` 形参不计入"恰有一个"。

脚注 83 指出，模板赋值运算符或形参为右值引用的赋值运算符永远不是复制赋值运算符，所以**它们的存在不会抑制复制赋值运算符的隐式声明**；它们与复制赋值运算符一起参与重载决议，选中时就用来赋值。

注 1 说明一个类可以声明多种形式的复制赋值运算符。注 2 说明，如果 `X` 只有形参为 `X&` 的复制赋值运算符，就不能把 `const X` 类型的表达式赋给 `X` 对象。

```cpp title="copy-assign-X-ref.cpp" error
struct X {
    X();
    X& operator=(X&);
};
const X cx;
X x;
void f() {
    x = cx;          // error: X::operator=(X&) 不能接收 cx
}
```

## 隐式声明的复制赋值运算符（¶2）

¶2 规定，如果类没有用户声明的复制赋值运算符，并且不是匿名联合体，就隐式声明一个。

- 如果类有用户声明的移动构造函数或移动赋值运算符，**它定义为弃置**；
- 否则它是预置的。如果类有用户声明的复制构造函数或析构函数，这种预置是弃用的（[[depr.impldec]]）。

满足以下条件时，隐式声明的复制赋值运算符的形式是 `X& X::operator=(const X&)`：

- ¶2.1 每个直接基类 `B` 都有非对象形参类型为 `const B&`、`const volatile B&` 或 `B` 的复制赋值运算符；
- ¶2.2 每个类类型 `M`（或其数组）的非静态数据成员都有非对象形参类型为 `const M&`、`const volatile M&` 或 `M` 的复制赋值运算符。

否则形式是 `X& X::operator=(X&)`。脚注 84 指出，这意味着隐式复制赋值运算符的引用形参不能绑定 `volatile` 左值（[[diff.class]]）。

注意这里考察的是直接基类和非静态数据成员，而复制构造函数考察的是潜在构造的子对象（含虚基类）。原因是赋值不区分最派生对象和基类子对象，虚基类由各直接基类的赋值运算符顺带处理（见 ¶12 关于虚基类可能被赋值多次的规定）。

## 移动赋值运算符的识别与隐式声明（¶3–¶5）

¶3 规定，用户声明的**移动赋值运算符**是非静态、非模板成员函数，恰有一个非对象形参，其类型为 `X&&`、`const X&&`、`volatile X&&` 或 `const volatile X&&`。注 3 说明可以声明多种形式。

注意，按值形参 `X` 的赋值运算符是复制赋值运算符，不是移动赋值运算符，但它也能处理右值（实参移动构造到形参中）。所以一个类写了 `X& operator=(X)`，就等于用户声明了复制赋值运算符，移动赋值运算符不会隐式声明（¶4.4），但右值赋值依然高效。

¶4 规定，如果类 `X` 的定义没有显式声明移动赋值运算符，那么**当且仅当**以下条件全部成立时，隐式声明一个预置的移动赋值运算符：

- ¶4.1 `X` 不是匿名联合体；
- ¶4.2 没有用户声明的复制构造函数；
- ¶4.3 没有用户声明的移动构造函数；
- ¶4.4 没有用户声明的复制赋值运算符；
- ¶4.5 没有用户声明的析构函数。

标准例 2 说明，只预置了复制赋值运算符的类没有隐式移动赋值运算符（复制赋值是用户声明的），但可以显式预置移动赋值：

```cpp run title="explicit-default-move.cpp" ok
#include <type_traits>

struct S1 {
    int a;
    S1& operator=(const S1&) = default;
};                                          // 没有移动赋值；右值赋值调用复制赋值

struct S2 {
    int a;
    S2& operator=(const S2&) = default;
    S2& operator=(S2&&) = default;          // 显式预置移动赋值
};

static_assert(std::is_move_assignable_v<S1>);    // "可移动赋值"——经由复制赋值
static_assert(std::is_move_assignable_v<S2>);
int main() { }
```

¶5 规定，隐式声明的移动赋值运算符的形式是 `X& X::operator=(X&&)`。

¶6 规定，隐式声明的复制/移动赋值运算符的返回类型是 `X&`，它是类的 inline public 成员。

## 何时被定义为弃置（¶7）

¶7 规定，如果类 `X` 有以下情况之一，`X` 的预置复制/移动赋值运算符定义为弃置：

- ¶7.1 有 `const` 非类类型（或其多维数组）的非静态数据成员；
- ¶7.2 有引用类型的非静态数据成员；
- ¶7.3 有类类型 `M`（或其多维数组）的直接非静态数据成员，或有直接基类 `M`，而 `M` 无法复制/移动：为找到 `M` 的相应赋值运算符所做的重载决议没有得到可用的候选，或者对变体成员选中了非平凡函数。

注 4 指出，定义为弃置的预置移动赋值运算符会被重载决议忽略。

为什么是这三条？

- ¶7.1：`const` 成员不能赋值，逐成员赋值无从进行。`const` 类类型成员则由 ¶7.3 处理：在 `const M` 对象上调用 `M::operator=` 的重载决议通常会失败，因为赋值运算符不是 `const` 成员函数。
- ¶7.2：**引用不能重新绑定**。逐成员赋值 `r = other.r` 会把 `other.r` 所指对象的值赋给 `r` 所指的对象，而不是让 `r` 指向别处。这几乎肯定不是用户想要的复制对象的语义，所以干脆删除。复制构造则没有这个问题，新对象的引用直接绑定到同一个对象。
- ¶7.3 中关于变体成员的规则：联合体不知道哪个成员是活跃的，只能按字节复制（¶13），所以只要有一个变体成员的赋值是非平凡的，联合体的赋值就必须删除。

```cpp title="assign-deleted.cpp" error
#include <string>

struct C  { const int c; };
struct R  { int& r; };
struct CS { const std::string s; };
union  U  { std::string s; int i; U() : i(0) { } ~U() { } };

void f(C& c1, C& c2, R& r1, R& r2, CS& s1, CS& s2, U& u1, U& u2) {
    c1 = c2;     // error: ¶7.1，const int 成员
    r1 = r2;     // error: ¶7.2，引用成员
    s1 = s2;     // error: ¶7.3，const std::string 不能调用 operator=
    u1 = u2;     // error: ¶7.3，变体成员 s 的赋值非平凡
}
```

!!! tip "有引用或 const 成员的类如何可赋值"
    把引用成员换成 `std::reference_wrapper<T>` 或指针，把 `const` 成员换成非 const 的私有成员加只读访问器。C++20 起 `const` 成员和引用成员不再妨碍透明替换（[[basic.life]]），所以也可以写 `this->~X(); new (this) X(other);` 这样的赋值，但它有异常安全问题，通常不推荐。

## 基类赋值运算符总被隐藏（¶8）

¶8 指出，由于用户不声明时复制/移动赋值运算符会隐式声明，**基类的复制/移动赋值运算符总会被派生类相应的赋值运算符隐藏**（[[over.assign]]）。注 5 说明，在派生类 `C` 中用 *using-declaration* 指名基类的赋值运算符，永远不会抑制 `C` 的赋值运算符的隐式声明。

进一步说，名字隐藏是按名字进行的，所以基类中任何 `operator=` 重载都会被派生类隐式声明的 `operator=` 隐藏：

```cpp title="assign-hidden.cpp" error
struct B { B& operator=(int); };
struct D : B { };
struct E : B { using B::operator=; };

void k(D& d, E& e) {
    d = 1;      // error: D 的隐式 operator= 隐藏了 B::operator=(int)
    e = 1;      // OK: using-declaration 把 B::operator=(int) 引入 E
}
```

`E` 中的 *using-declaration* 引入了 `B::operator=(int)`，`E` 的隐式复制/移动赋值运算符照样会声明（注 5）。

## 平凡的赋值运算符（¶9）

¶9 规定，如果类 `X` 的复制/移动赋值运算符不是用户提供的，并且满足以下条件，它就是**平凡的**：

- ¶9.1 `X` 没有虚函数和虚基类；
- ¶9.2 为复制/移动每个直接基类子对象所选中的赋值运算符是该基类的直接成员，并且是平凡的；
- ¶9.3 对每个类类型（或其数组）的非静态数据成员，选中的赋值运算符是平凡的。

否则它是非平凡的。平凡的赋值运算符相当于用 `memcpy`（或 `memmove`）复制对象表示。

```cpp run title="trivial-assign.cpp" ok
#include <type_traits>

struct S { S& operator=(const S&) & = default; int x; };          // 允许 & 限定（[dcl.fct.def.default]）
struct T { T& operator=(this T&, const T&) = default; int x; };   // C++23：显式对象形参

static_assert(std::is_trivially_copy_assignable_v<S>);
static_assert(std::is_trivially_copy_assignable_v<T>);
int main() { }
```

虚函数使赋值非平凡的原因与复制构造类似：在 `Base& b = derived; b = other_base;` 中，如果按字节复制，就会覆盖 `derived` 的 vptr。所以赋值运算符必须保留目标对象的 vptr，只复制数据成员。

## 隐式定义（¶10–¶14）

¶10 规定，**隐式定义的复制/移动赋值运算符是 `constexpr` 的**。

¶11 规定，预置的赋值运算符隐式定义之前，其直接基类和非静态数据成员的所有非用户提供的复制/移动赋值运算符要先隐式定义。注 6 指出，隐式声明的赋值运算符带有隐含的异常说明（[[except.spec]]）。

### 非联合体：逐成员赋值（¶12）

¶12 规定，非联合体类 `X` 的隐式定义的复制/移动赋值运算符对其子对象执行**逐成员复制/移动赋值**：先按 *base-specifier-list* 中的声明顺序赋值直接基类，再按类定义中的声明顺序赋值直接非静态数据成员。设 `x` 是函数的形参，对移动运算符而言则是指代形参的 xvalue。各子对象的赋值方式如下：

- ¶12.1 类类型：如同以该子对象为对象表达式、以 `x` 的对应子对象为唯一实参调用 `operator=`，并且如同带显式限定，即不考虑更派生类中可能存在的虚覆盖函数；
- ¶12.2 数组：逐元素赋值；
- ¶12.3 标量类型：使用内置赋值运算符。

**虚基类子对象是否被赋值多次是未指定的** {{unspec}}。标准例 3：

```cpp run title="vbase-assign.cpp" unspecified
#include <cstdio>

struct V {
    V& operator=(const V&) { std::puts("V::operator="); return *this; }
};
struct A : virtual V { };
struct B : virtual V { };
struct C : B, A { };

int main() {
    C c1, c2;
    c1 = c2;    // V::operator= 被调用一次还是两次（经由 B 和 A 的隐式赋值）是未指定的
}
```

这与构造的情形不同。构造时虚基类只由最派生类构造一次（构造函数有完整对象和基类子对象两个版本，[[class.ctor]]）；赋值运算符却只有一个版本，`C` 的隐式赋值调用 `B::operator=` 和 `A::operator=`，二者都会赋值 `V`。要避免重复赋值，只能手写赋值运算符，这也是虚基类最好不含数据的理由之一。

### 联合体：复制对象表示（¶13）

¶13 规定，联合体 `X` 的隐式定义的复制/移动赋值运算符**复制 `X` 的对象表示**。如果赋值的源和目标不是同一个对象，那么对源中嵌套的每个对象，都要在目标中创建一个对应的嵌套对象 *o*，*o* 的生命周期在复制之前开始。

与复制构造函数（[[class.copy.ctor#16]]）相比，区别在于多了源和目标不是同一对象的限定：自赋值 `u = u` 时什么都不需要创建，活跃成员本来就在那里。

```cpp run title="union-assign.cpp" ok
union U { int i; float f; };

int main() {
    U a, b;
    a.i = 1;
    b.f = 2.0f;
    b = a;               // 按字节复制；b.i 成为 b 的活跃成员（b.f 的生命周期结束）
    return b.i - 1;      // OK
}
```

### 返回值（¶14）

¶14 规定，隐式定义的复制/移动赋值运算符返回被赋值的对象（`*this`）。

## 自赋值与异常安全

标准对用户编写的赋值运算符没有任何要求。但有两个经典问题值得在这里说明，它们解释了为什么隐式赋值的逐成员语义通常是对的，以及什么时候不对。

先看自赋值 `x = x`。逐成员赋值天然对自赋值安全，因为每个成员都是对自己赋值。手写的资源管理代码则容易出错：

```cpp title="self-assign-bug.cpp" ub
#include <cstring>

struct Str {
    char* p;
    explicit Str(const char* s) : p(new char[std::strlen(s) + 1]) { std::strcpy(p, s); }
    ~Str() { delete[] p; }
    Str(const Str& o) : Str(o.p) { }
    Str& operator=(const Str& o) {
        delete[] p;                                   // 若 &o == this，o.p 也被释放了
        p = new char[std::strlen(o.p) + 1];           // UB: 读取已释放的内存
        std::strcpy(p, o.p);
        return *this;
    }
};

int main() {
    Str s("hello");
    Str& alias = s;
    s = alias;                                        // 自赋值
}
```

复制并交换可以同时解决自赋值和强异常安全两个问题：

```cpp run title="copy-and-swap.cpp" ok
#include <cstring>
#include <utility>

struct Str {
    char* p;
    explicit Str(const char* s) : p(new char[std::strlen(s) + 1]) { std::strcpy(p, s); }
    ~Str() { delete[] p; }
    Str(const Str& o) : Str(o.p) { }
    Str(Str&& o) noexcept : p(std::exchange(o.p, nullptr)) { }
    Str& operator=(Str o) noexcept {      // 按值：复制或移动发生在调用方；是复制赋值运算符（¶1）
        std::swap(p, o.p);                // 不会失败
        return *this;                     // 旧资源随 o 析构
    }
};

int main() {
    Str s("hello"), t("world");
    s = s;                 // 自赋值：安全（多一次复制）
    s = t;                 // 复制
    s = Str("tmp");        // 移动构造形参，然后交换
    return std::strcmp(s.p, "tmp");
}
```

按值形参的 `operator=` 同时承担复制赋值和移动赋值的工作，代价是每次赋值都多一次移动构造，自赋值时还多一次复制。性能敏感的类通常分别写 `const X&` 和 `X&&` 两个版本。

## 引用限定的赋值运算符

内置赋值要求左操作数是可修改的左值，但类类型的隐式赋值运算符没有引用限定符，所以**可以对右值赋值**：`f() = x;`、`std::string("a") = "b";` 都能编译。这是 C++98 遗留下来的不一致。[[dcl.fct.def.default#2]] 允许预置的赋值运算符带 `&` 限定符，借此禁止对右值赋值：

```cpp title="ref-qualified-assign.cpp" error
struct S {
    S& operator=(const S&) & = default;   // 只能对左值赋值
    int x;
};
S f();

void g() {
    S a{};
    a = S{};       // OK: a 是左值（S 没有移动赋值：有用户声明的复制赋值，右值实参绑定到 const S&）
    f() = S{};     // error: 对象实参是右值，& 限定的 operator= 不可行
}
```

标准库为了兼容没有这样做。但对新设计的值类型，给赋值运算符加 `&` 限定，就能在编译期发现给临时量赋值这类 bug。

## 实现视角

!!! impl "平凡赋值与尾部填充"
    平凡的复制/移动赋值在代码生成上就是复制对象表示。但有一个 ABI 细节：在 Itanium ABI 中，派生类的成员可能放进基类的尾部填充里（基类的数据大小 dsize 可以小于 `sizeof`）。所以当被赋值的对象可能是**潜在重叠子对象**时，编译器不能直接复制 `sizeof(X)` 个字节，否则会覆盖派生类的成员。正因如此，[[basic.types.trivial]] 中按字节复制能保持值的保证只针对非潜在重叠的对象，用户自己调用 `memcpy` 时也必须遵守这一前提。

## 历史与演进

!!! history "历史与演进"
    - **C++98**：有复制赋值运算符；隐式声明的形式是 `X& operator=(const X&)` 或 `X& operator=(X&)`；`const` 成员或引用成员使隐式赋值非良构（使用时报错）。
    - **C++11**：引入移动赋值；以定义为弃置取代隐式定义非良构；声明了移动操作时复制赋值被删除；有用户声明的复制构造函数或析构函数时，隐式复制赋值被弃用；允许 `&` 限定的预置赋值。
    - **C++20**：联合体赋值时在目标中创建对应的活跃成员对象；隐式定义的赋值运算符可以是 `constexpr`。
    - **C++23**：引入显式对象形参（[[P0847R7]]），预置的赋值运算符可以使用 `this X&` 形参；隐式定义的赋值运算符无条件是 `constexpr`。

## 陷阱

!!! pitfall "派生类的手写赋值忘了赋值基类"
    手写 `D& D::operator=(const D& o)` 时，必须显式调用 `B::operator=(o)`，否则基类部分不会被赋值。编译器不会替你补上，这一点与构造函数会自动默认构造基类不同。

!!! pitfall "以为 `const` 成员只影响赋值"
    `const` 成员使赋值被删除，进而导致这个类型不能在 `std::vector` 中 `erase`/`insert`（需要移动赋值），也不能 `std::sort`。需要值语义的类应避免 `const` 数据成员。

!!! pitfall "虚赋值运算符"
    把 `operator=` 声明为 `virtual` 几乎总是错误的设计，因为派生类的 `operator=(const Derived&)` 形参类型不同，并不覆盖基类的 `operator=(const Base&)`。多态类型通常应禁止赋值（`= delete`），并提供 `clone()`。

## 思考题

!!! question "思考题 1"
    ```cpp
    struct A { A& operator=(A); };   // 按值
    struct B { A a; };
    ```
    `B` 的隐式复制赋值运算符是什么形式？`B` 有隐式移动赋值运算符吗？

<details markdown="1">
<summary>答案</summary>

`A` 有一个非对象形参类型为 `A` 的复制赋值运算符，满足 ¶2.2（形参类型可以是 `M`），所以 `B` 的隐式复制赋值是 `B& operator=(const B&)`。`B` 本身没有任何用户声明的特殊成员函数，所以按 ¶4 会隐式声明移动赋值运算符 `B& operator=(B&&)`。它移动赋值 `a` 时，对 `A` 的重载决议选中 `A::operator=(A)`，实参是 xvalue，形参 `A` 本应由移动构造函数初始化。但 `A` 有隐式移动构造函数吗？`A` 有用户声明的复制赋值运算符，所以**没有**隐式移动构造函数，形参由复制构造函数初始化。因此，"移动"`B` 实际上复制了 `a`。
</details>

!!! question "思考题 2"
    为什么 ¶7 删除有引用成员的类的赋值，却不删除它的复制构造？

<details markdown="1">
<summary>答案</summary>

复制构造是创建一个新对象，新对象的引用成员绑定到源对象的引用所绑定的同一个对象，这种语义自然而且没有歧义。赋值则是修改已有的对象。引用一经绑定就不能改变，逐成员赋值 `r = o.r` 只会修改被引用对象的值，不能让 `this->r` 改为指向 `o.r` 所指的对象。赋值之后两个对象并不相等，还顺带修改了第三方对象，这种语义几乎从来不是用户想要的，所以默认删除，迫使用户自己考虑清楚。
</details>

## 小结

| 主题 | 复制赋值 | 移动赋值 |
|---|---|---|
| 识别 | 非静态非模板；一个非对象形参：`X`、`cv X&` | 非静态非模板；一个非对象形参：`cv X&&` |
| 隐式声明 | 没有用户声明的复制赋值时 | 没有用户声明的复制构造、移动构造、复制赋值、析构时 |
| 形式 | `X& operator=(const X&)`，必要时 `X& operator=(X&)` | `X& operator=(X&&)` |
| 弃置 | 声明了移动操作；`const` 非类成员；引用成员；直接成员/基类不可赋值；变体成员非平凡 | 后三条同左（弃置后被重载决议忽略） |
| 平凡 | 非用户提供 + 无虚 + 选中的基类/成员赋值平凡 | 同左 |
| 隐式定义 | 先基类后成员，按声明顺序逐个赋值；虚基类可能赋值多次（未指定）；`constexpr`；返回 `*this` | 同左 |
| 联合体 | 复制对象表示；非自赋值时在目标中创建对应对象 | 同左 |
| 隐藏 | 派生类的隐式 `operator=` 总是隐藏基类的所有 `operator=` | 同左 |
