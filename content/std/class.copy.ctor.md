---
title: 复制/移动构造函数
summary: 哪些构造函数算复制或移动构造函数（模板永远不算），编译器何时隐式声明它们、何时把它们删除、何时平凡，以及隐式定义的版本逐成员做了什么。
status: done
papers: P0593R6
related: special, class.copy.assign, class.ctor, class.copy.elision, class.prop, dcl.fct.def.default, depr.impldec, over.match.funcs
tags: 复制构造, 移动构造, 平凡, 完美转发
updated: 2026-10-19
---

!!! tldr
    - 第一个形参是 `cv X&` 的非模板构造函数是复制构造函数，`cv X&&` 的是移动构造函数，其余形参必须都有默认实参。构造函数模板永远不是复制或移动构造函数。
    - 隐式复制构造函数通常是 `X(const X&)`；某个子对象只能从非 const 左值复制时，它退化为 `X(X&)`。
    - 用户声明了复制构造、复制赋值、移动赋值、析构中的任何一个，就不会隐式声明移动构造函数，右值会改用复制构造函数。
    - 隐式定义的复制/移动构造函数按声明顺序逐个复制或移动基类和成员，忽略默认成员初始化器；联合体则按字节复制，并让目标里对应的成员开始生命周期。
    - 非 const 左值去匹配一个 `template<class T> X(T&&)` 时，它比复制构造函数更好，这就是转发构造函数劫持复制。

复制构造函数和移动构造函数决定了用一个同类型对象初始化另一个对象时发生什么：`T b = a;`、`T b(std::move(a));`、不能消除复制时的按值传参和按值返回、容器扩容。这一节与 [[class.copy.assign]] 的结构几乎完全平行；各种特殊成员函数的总览见 [[special]]。

## 哪些构造函数是复制/移动构造函数（¶1–¶3）

```cpp run title="copy-ctor-forms.cpp" ok
struct X {
    X(int) { }
    X(const X&, int = 1) { }   // 复制构造函数
};

int main() {
    X a(1);      // X(int)
    X b(a, 0);   // X(const X&, int)
    X c = b;     // X(const X&, int)，作为复制构造函数
    (void)c;
}
```

¶1 类 `X` 的一个**非模板**构造函数，如果第一个形参的类型是 `X&`、`const X&`、`volatile X&` 或 `const volatile X&`，并且没有别的形参或别的形参都有默认实参，它就是**复制构造函数**（copy constructor）。

¶2 把上面的左值引用换成右值引用 `X&&`、`const X&&` 等，就是**移动构造函数**（move constructor）。

```cpp run title="move-ctor.cpp" ok
#include <cstdio>
#include <utility>

struct Y {
    Y() { }
    Y(const Y&) { std::puts("copy"); }
    Y(Y&&)      { std::puts("move"); }
};

Y f(int) { return Y(); }

int main() {
    Y d(f(1));          // 都不调用：prvalue 直接初始化 d
    Y e = d;            // copy：d 是左值
    Y g = std::move(e); // move：xvalue
    (void)g;
}
```

标准例 2 对 `Y d(f(1));` 的注释仍是 calls Y(Y&&)。C++17 起 prvalue `f(1)` 直接初始化 `d`，复制和移动构造函数都不调用（[[dcl.init]]），本机输出也只有 `copy` 和 `move` 两行。

¶3 注 1 说明，各种形式可以在同一个类里同时声明。`X(const X&&)` 合法，但通常没有意义，因为不能从 const 对象里取走资源。它的少数用途之一是写成 `= delete`，禁止从 const 右值构造。

## 模板永远不是复制构造函数

¶1 和 ¶2 都要求非模板。构造函数模板即使某个特化的签名恰好是 `X(const X&)`，也不是复制构造函数。这有两个后果：

1. 构造函数模板不会抑制隐式复制构造函数的声明；
2. 但在重载决议中，模板特化可能比隐式复制构造函数匹配得更好，于是被选中。

第二点最常见的形式是转发引用构造函数：

```cpp run title="forwarding-hijack.cpp" ok
#include <cstdio>
#include <string>

struct P {
    std::string s;
    P(const char* p) : s(p) { }
    template<class T>
    P(T&&) { std::puts("template"); }
    P(const P& o) : s(o.s) { std::puts("copy"); }
};

int main() {
    P a("x");
    P b = a;          // template
    const P c("y");
    P d = c;          // copy
    (void)b; (void)d;
}
```

对非 const 左值 `a`，模板推导出 `T = P&`，得到 `P(P&)`。它不需要给实参加 const，比 `P(const P&)` 更匹配，所以被选中。对 const 左值 `c`，两者一样好，这时非模板优先（[[over.match.best]]）。

如果模板体里写的是 `s(std::forward<T>(t))`，用 `P&` 去初始化 `std::string` 就会编译失败；更糟的情况是能编译但语义错误。修复的办法是约束模板，把 `P` 自身排除掉：

```cpp
template<class T>
    requires (!std::is_same_v<std::remove_cvref_t<T>, P>)
P(T&& t);
```

如果要连 `P` 的派生类也排除，可以改用 `!std::is_base_of_v<P, std::remove_cvref_t<T>>`。

## 不能有 `X(X)`（¶5）

```cpp title="X-of-X.cpp" error
struct Bad {
    Bad(Bad);   // error: 第一个形参必须是引用
};
```

¶5 如果一个构造函数的第一个形参是按值的 `cv X`，并且没有别的形参或别的形参都有默认实参，这个声明是非良构的。按值接收 `X` 需要先复制实参，而复制又要调用这个构造函数本身。

成员函数模板也永远不会被实例化成这样的签名：

```cpp run title="no-X-of-X.cpp" ok
struct S {
    template<typename T> S(T) { }
    S() { }
};

S g;

int main() {
    S a(g);   // 不实例化 S::S<S>(S)，使用隐式复制构造函数
    (void)a;
}
```

没有这条规则，`S a(g);` 会推导出 `T = S`，得到 `S(S)`，按值接收 `g` 又要复制 `g`，又会选中这个模板。

## 隐式声明的复制构造函数（¶4、¶6–¶7）

¶6 类没有**用户声明**（[[g:user-declared]]）的复制构造函数，并且不是匿名联合体时，编译器隐式声明一个非 explicit 的复制构造函数：

- 类定义声明了移动构造函数或移动赋值运算符时，它**定义为弃置**（相当于 `= delete`）；
- 否则它是**预置**的（defaulted，由编译器生成定义，[[dcl.fct.def]]）。这时如果类有用户声明的复制赋值运算符或析构函数，这种隐式生成已被弃用（[[depr.impldec]]）。

¶7 隐式复制构造函数的形式通常是 `X::X(const X&)`。只有当某个类类型的**潜在构造子对象**（[[g:potentially-constructed-subobjects]]，直接基类、非静态数据成员和虚基类）没有接受 `const M&`（或 `const volatile M&`）的复制构造函数时，它才退化为 `X::X(X&)`。

```cpp title="implicit-copy-form.cpp" error
struct M { M() { } M(M&) { } };   // 只能从非 const 左值复制
struct X { M m; };                // 隐式复制构造函数是 X(X&)

X x1;
const X cx{};
X x2 = x1;      // OK
X x3 = cx;      // error: X(X&) 不能接收 const X
```

退化而不是删除，是因为逐成员复制 `m` 要调用 `M(M&)`，这只要求源对象不是 const。保留 `X(X&)`，就仍能从非 const 左值复制。

¶4 注 2 说的就是这种类：只有 `X(X&)` 的类，不能用 const 或 volatile 的初始化器复制。C++98 的 `std::auto_ptr` 就是这样，它的复制构造函数要修改源对象来转移所有权。C++11 的移动语义正是为这类需求设计的。

!!! lawyer "volatile 对象不能被隐式复制"
    脚注 82 指出，`const X&` 形参不能绑定 volatile 左值，所以 `volatile X vx; X y = vx;` 是非良构的。需要的话自己声明 `X(const volatile X&)`。C 允许从 volatile 结构体复制，这是 [[diff.class]] 列出的 C/C++ 不兼容之一。

## 隐式声明的移动构造函数（¶8–¶9）

¶8 类没有用户声明的移动构造函数时，当且仅当下面几条全部成立，才隐式声明一个非 explicit 的预置移动构造函数：

- ¶8.1 不是匿名联合体；
- ¶8.2 没有用户声明的复制构造函数；
- ¶8.3 没有用户声明的复制赋值运算符；
- ¶8.4 没有用户声明的移动赋值运算符；
- ¶8.5 没有用户声明的析构函数。

¶9 它的形式是 `X::X(X&&)`。

条件这么严，是因为用户声明了复制、赋值或析构中的任何一个，往往说明这个类管理着资源，逐成员移动很可能是错的。例如析构函数会 `delete` 一个原始指针成员，逐成员移动只是复制了指针，两个对象会重复释放。所以 C++11 只在用户什么都没自定义时才生成移动操作。

注 3 说明了不生成时的后果：原本会调用移动构造函数的地方，可能改为调用复制构造函数，因为 `const X&` 也能绑定右值。这样做慢，但正确。

## 何时定义为弃置（¶10–¶11）

¶10 隐式声明的复制/移动构造函数是类的 inline public 成员。类 `X` 有下列情况之一时，它的预置复制/移动构造函数定义为弃置：

- ¶10.1 某个潜在构造子对象 `M`（或其多维数组）无法复制/移动：为它选构造函数的重载决议找不到可用的候选；或者它是**变体成员**（[[g:variant-member]]，联合体的成员），而选中的函数非平凡。
- ¶10.2 某个潜在构造子对象的析构函数被删除，或者不可访问。
- ¶10.3 仅对复制构造函数：有右值引用类型的非静态数据成员。

```cpp title="copy-ctor-deleted.cpp" error
#include <string>
#include <utility>

union U {
    std::string s;
    int i;
    U() : i(0) { }
    ~U() { }
};
U u1;
U u2 = u1;               // error: ¶10.1

struct RR { int&& r; };
int g = 1;
RR r1{std::move(g)};
RR r2 = r1;              // error: ¶10.3
RR r3 = std::move(r1);   // OK
```

¶10.1 的变体成员条款是联合体的规则。联合体不知道哪个成员是活跃的，只能按字节复制（¶16），所以只要某个成员（如 `std::string`）的复制构造函数非平凡，联合体的复制构造函数就被删除。

¶10.2 的理由与默认构造函数相同（[[class.default.ctor#2]]）：构造中途抛出异常时要析构已经构造好的子对象。

¶10.3 的理由是：复制构造函数从 `const X&` 里读出的 `x.r` 是左值，不能直接初始化新对象的右值引用成员。移动构造函数则按 ¶15.2 用 `static_cast<T&&>(x.r)` 处理，所以 `r3` 合法。

注 4：定义为弃置的预置移动构造函数会被重载决议忽略（[[over.match]]、[[over.over]]）。否则它会挡住本可以由复制构造函数完成的右值初始化。例子见 [[special]] 的 `deleted-move-ignored.cpp`。

¶11 注 5：派生类 `C` 用 *using-declaration* 继承基类的构造函数，永远不会抑制 `C` 自己的复制/移动构造函数的隐式声明。而且，形参是基类引用的继承构造函数，不会被用来从单个同类对象构造 `C`（[[over.match.funcs.general#9]] 把它排除出候选）。

## 平凡的复制/移动构造函数（¶12）

```cpp run title="trivial-copy.cpp" ok
#include <type_traits>
#include <string>

struct A { int x; std::string* p; };
struct B { std::string s; };
struct C { virtual void f() { } };
struct D { D(const D&) = default; int x; };
struct E { E(const E&); int x; };
E::E(const E&) = default;   // 类外预置：用户提供

using std::is_trivially_copy_constructible_v;
static_assert( is_trivially_copy_constructible_v<A>);
static_assert(!is_trivially_copy_constructible_v<B>);
static_assert(!is_trivially_copy_constructible_v<C>);
static_assert( is_trivially_copy_constructible_v<D>);
static_assert(!is_trivially_copy_constructible_v<E>);
int main() { }
```

¶12 复制/移动构造函数**平凡**的前提是它不是**用户提供**（[[g:user-provided]]，用户声明了它，且没有在第一次声明处 `= default` 或 `= delete`）的，此外：

- ¶12.1 类没有虚函数和虚基类；
- ¶12.2 为复制/移动每个直接基类选中的构造函数，是那个基类自己的直接成员，并且平凡；
- ¶12.3 为复制/移动每个类类型（或其数组）的非静态数据成员选中的构造函数平凡。

平凡的复制构造函数相当于复制对象的字节。

虚函数使复制非平凡，原因在切片：`Derived d; Base b = d;` 如果按字节复制，`b` 的虚表指针会指向 `Derived` 的虚表，`b` 的动态类型就错了。所以复制构造函数必须把虚表指针设为 `Base` 的虚表，而不是从源对象复制。

¶12.2 和 ¶12.3 看的是实际选中的那个函数，而不是成员类型有没有某个平凡的构造函数。例如成员类型 `M` 有平凡的 `M(const M&)` 和用户提供的 `M(M&&)`，外层类的复制构造函数可以平凡，移动构造函数却不平凡。¶12.2 要求选中的是基类的直接成员，是为了排除基类从它自己的基类继承来的构造函数。

## 隐式定义（¶13–¶16）

### 何时定义（¶13–¶14）

¶13 注 6：即使实现消除了对复制/移动构造函数的使用（复制消除，[[class.copy.elision]]），它仍然会被隐式定义。所以隐式定义如果非良构，复制消除不能让程序变得合法，程序的良构性也就不会因编译器是否做了可选的消除而不同。

¶13 还规定隐式定义的复制/移动构造函数是 `constexpr` 的。

¶14 预置的复制/移动构造函数被隐式定义之前，它的潜在构造子对象的所有非用户提供的复制/移动构造函数先被隐式定义。隐式声明的版本有隐含的异常说明（注 7，[[except.spec]]）：它调用的构造函数都不抛出时，它就是 `noexcept` 的。

!!! tip "移动构造函数要标 `noexcept`"
    `std::vector` 扩容时，只有元素的移动构造函数是 `noexcept` 的（或者元素不可复制），才会移动元素；否则为了强异常安全保证，它会复制。隐式定义的移动构造函数自动推导 `noexcept`，手写时要自己标上。

### 非联合体：逐成员复制/移动（¶15）

```cpp run title="memberwise.cpp" ok
#include <string>
#include <utility>
#include <cassert>

struct X {
    int arr[3];
    std::string s;
    int& ref;
    int counter = 100;   // 复制时被忽略
};

int main() {
    int target = 7;
    X a{{1, 2, 3}, "hello", target, 5};
    X b = a;
    assert(b.arr[2] == 3 && b.s == "hello");
    assert(&b.ref == &target && b.counter == 5);

    X c = std::move(a);  // s 被移走
    assert(c.s == "hello");
}
```

¶15 非联合体类的隐式复制/移动构造函数，对基类和成员做逐成员复制/移动，顺序与普通构造函数初始化它们的顺序相同（[[class.base.init]]：虚基类，直接基类，然后成员按声明顺序）。默认成员初始化器被忽略（注 8），所以 `b.counter` 是 5 而不是 100。

设 `x` 是构造函数的形参；对移动构造函数，`x` 是指代形参的 xvalue。每个子对象按它的类型处理：

- ¶15.1 数组：每个元素用 `x` 中对应的元素直接初始化；
- ¶15.2 右值引用类型 `T&&` 的成员 `m`：用 `static_cast<T&&>(x.m)` 直接初始化；
- ¶15.3 其他基类或成员：用 `x` 中对应的基类或成员直接初始化。

虚基类子对象只初始化一次。

¶15.1 是复制数组的唯一隐式途径。数组本身不能复制初始化，但放在类里就能随类一起复制。¶15.3 对引用成员的效果，是让新对象的引用绑定到同一个对象（`&b.ref == &target`）。

### 联合体：复制对象表示（¶16）

```cpp run title="union-copy.cpp" ok
union U { int i; float f; };

int main() {
    U a;
    a.f = 1.5f;          // f 是活跃成员
    U b = a;             // b.f 成为 b 的活跃成员
    return b.f == 1.5f ? 0 : 1;
}
```

¶16 联合体的隐式复制/移动构造函数复制整个对象表示，也就是按字节复制（[[basic.types.general]]）。此外，对源对象里嵌套的每个对象，目标中对应的对象（子对象就找到它，否则创建一个）在复制之前开始生命周期。

后半句保证了活跃成员随之复制过去：上例中 `b.f` 是 `b` 的活跃成员，可以读取。没有它，按字节复制之后目标联合体里没有任何活跃成员，读哪个成员都是未定义行为。按 ¶10.1，只有所有变体成员的复制构造函数都平凡时，联合体才有可用的隐式复制构造函数。

## 实现视角

!!! impl "平凡复制与调用约定"
    平凡的复制/移动构造函数编译成 `memcpy` 或寄存器传送，`std::vector` 复制平凡元素时直接 `memmove`。Itanium C++ ABI 规定，类有非平凡的复制构造函数、移动构造函数或析构函数（或者复制和移动构造函数全部被删除）时，按值传递不能放在寄存器里，调用方要在内存里构造对象再传地址。所以给一个小类加上用户提供的复制构造函数，会改变它的调用约定，破坏 ABI 兼容。

    Clang 的 `[[clang::trivial_abi]]` 属性允许 `unique_ptr` 一类的类型仍按寄存器传递，代价是析构改在被调用方进行。它不改变标准意义上的平凡性。

## 历史与演进

!!! history
    - C++98 只有复制构造函数，`X(X&)` 退化规则当时就已存在。
    - C++11 引入移动构造函数及其严格的隐式声明条件；声明了移动操作时隐式复制被删除；有用户声明的复制赋值或析构时，隐式复制被弃用。弃置的预置移动构造函数被重载决议忽略，是 C++11 发布后不久以缺陷报告加入的。
    - C++17 的保证复制消除使 prvalue 初始化同类型对象不再需要可用的复制/移动构造函数。
    - C++20 规定联合体被隐式复制时，目标中对应的成员开始生命周期（[[P0593R6]]）。同期的条件平凡特殊成员函数（[[P0848R3]]）让同一个类模板可以按实参决定复制构造函数是否平凡。
    - C++23 起隐式定义的复制/移动构造函数无条件 `constexpr`。

## 常见误解

!!! pitfall "只写了析构函数，移动悄悄变成了复制"
    用户声明析构函数会使移动构造函数不再隐式声明（¶8.5），右值改用复制构造函数。自定义了析构函数的类，要检查是否需要显式 `= default` 移动操作，见 [[special]]。

!!! pitfall "移动后源对象的标量成员不变"
    隐式移动对 `int`、原始指针这样的标量成员就是复制，源对象里的值不变。用原始指针表示所有权的类必须自己写移动操作并把源指针置空，或者改用 `std::unique_ptr` 成员。

## 思考题

!!! question "思考题 1"
    ```cpp
    struct A {
        A() = default;
        A(A&) = default;
    };
    struct B { A a; };
    const B cb{};
    B b2 = cb;   // ?
    ```
    最后一行合法吗？`B` 的隐式复制构造函数是什么形式？

<details markdown="1">
<summary>答案</summary>

不合法。`A` 唯一的复制构造函数是 `A(A&)`，预置函数允许把 `const A&` 改成 `A&`（[[dcl.fct.def.default#2]]）。按 ¶7，成员 `a` 没有接受 `const A&` 的复制构造函数，所以 `B` 的隐式复制构造函数是 `B(B&)`，不能绑定 `const B` 类型的 `cb`。

</details>

!!! question "思考题 2"
    `struct S { template<class T> S(const T&); };` 中，`S s2 = s1;` 调用哪个构造函数？把模板改成 `template<class T> S(T&)`，而 `s1` 是非 const 左值呢？

<details markdown="1">
<summary>答案</summary>

第一种情况调用隐式复制构造函数 `S(const S&)`。模板不是复制构造函数，不抑制它；模板特化 `S(const S&)` 与它签名相同，非模板优先（[[over.match.best]]）。第二种情况推导出 `S(S&)`，比 `S(const S&)` 少一次限定转换，模板被选中。

</details>

## 小结

| | 复制构造函数 | 移动构造函数 |
|---|---|---|
| 识别 | 非模板；首形参 `cv X&`；其余有默认实参 | 非模板；首形参 `cv X&&`；其余有默认实参 |
| 隐式声明 | 没有用户声明的复制构造函数 | 没有用户声明的复制构造、复制赋值、移动赋值、析构 |
| 形式 | `X(const X&)`，必要时 `X(X&)` | `X(X&&)` |
| 弃置 | 声明了移动操作；子对象不可复制或不可析构；有右值引用成员 | 子对象不可移动或不可析构；弃置后被重载决议忽略 |
| 平凡 | 非用户提供，无虚函数和虚基类，选中的基类和成员构造函数都平凡 | 同左 |
| 隐式定义 | 逐成员直接初始化，忽略默认成员初始化器；联合体按字节复制 | 同左，源为 xvalue |
