---
title: 复制/移动赋值运算符
summary: 哪些 operator= 算复制或移动赋值运算符，编译器何时隐式声明、何时删除它们（const 成员、引用成员），派生类为什么总是隐藏基类的 operator=，以及隐式定义的逐成员赋值。
status: done
papers: P0593R6, P0847R7
related: special, class.copy.ctor, over.assign, expr.assign, dcl.fct.def.default, depr.impldec, class.prop, basic.life
tags: 赋值运算符, 复制赋值, 移动赋值, 平凡, 自赋值
updated: 2026-10-19
---

!!! tldr
    - 复制赋值运算符是只有一个非对象形参、类型为 `X`、`cv X&` 的非模板 `operator=`；形参是 `cv X&&` 的是移动赋值运算符。与构造函数不同，按值形参 `X` 也可以。
    - 移动赋值运算符的隐式声明条件和移动构造函数一样严：用户声明了复制构造、移动构造、复制赋值、析构中的任何一个，它就不存在，右值改用复制赋值。
    - 有 `const` 标量成员或引用成员的类，预置的赋值运算符被删除，因为引用不能重新绑定，const 成员不能修改。
    - 派生类总有自己的 `operator=`（隐式或显式），所以基类的所有 `operator=` 重载都会被隐藏，要用 using 声明才能引入。
    - 隐式定义的赋值运算符先按声明顺序赋值直接基类，再赋值成员，返回 `*this`；虚基类可能被赋值不止一次。

赋值与构造的区别在于，构造把一块存储变成对象，赋值则替换一个已经存在的对象的值。所以手写赋值运算符要处理旧值：释放旧资源、应对自赋值、保证异常安全。这一节的结构与 [[class.copy.ctor]] 平行。

## 哪些 `operator=` 是复制/移动赋值运算符（¶1、¶3）

```cpp title="copy-assign-X-ref.cpp" error
struct X {
    X();
    X& operator=(X&);   // 复制赋值运算符
};
const X cx;
X x;
void f() {
    x = cx;   // error: X& 不能绑定 const X
}
```

¶1 **复制赋值运算符**（copy assignment operator）是类 `X` 的非静态、非模板成员函数 `X::operator=`，恰有一个非对象形参，类型是 `X`、`X&`、`const X&`、`volatile X&` 或 `const volatile X&` 之一。

¶3 **移动赋值运算符**（move assignment operator）的定义相同，只是形参类型是 `X&&`、`const X&&`、`volatile X&&` 或 `const volatile X&&`。

和复制构造函数比，有两点不同：

1. 允许按值形参 `X`。`X& operator=(X other)` 是复制赋值运算符，复制并交换惯用法就这样写（见下文）。构造函数不能这样写（[[class.copy.ctor#5]]），因为按值接收实参要先复制构造；赋值运算符没有这个递归问题。
2. 只数非对象形参。C++23 起赋值运算符可以有显式对象形参（[[P0847R7]]），如 `X& operator=(this X& self, const X& o)`，`self` 不算在恰有一个之内。

脚注 83 指出，模板赋值运算符和形参为右值引用的赋值运算符都不是复制赋值运算符，所以它们不会抑制复制赋值运算符的隐式声明。它们与复制赋值运算符一起参与重载决议，选中了就用来赋值。

注 1 和注 3 说明同一个类可以声明多种形式。注 2 说的就是上面的例子：只有 `X&` 形参的复制赋值运算符时，不能把 const 对象赋给 `X`。

## 隐式声明（¶2、¶4–¶6）

### 复制赋值（¶2）

¶2 类没有**用户声明**（[[g:user-declared]]）的复制赋值运算符，并且不是匿名联合体时，编译器隐式声明一个：

- 类有用户声明的移动构造函数或移动赋值运算符时，它**定义为弃置**（相当于 `= delete`）；
- 否则它是**预置**的（defaulted，由编译器生成定义）。这时如果类有用户声明的复制构造函数或析构函数，这种隐式生成已被弃用（[[depr.impldec]]）。

它的形式通常是 `X& X::operator=(const X&)`，条件是：

- ¶2.1 每个直接基类 `B` 都有形参为 `const B&`、`const volatile B&` 或 `B` 的复制赋值运算符；
- ¶2.2 每个类类型 `M`（或其数组）的非静态数据成员，都有形参为 `const M&`、`const volatile M&` 或 `M` 的复制赋值运算符。

否则形式是 `X& X::operator=(X&)`。脚注 84 指出，隐式版本的引用形参因此不能绑定 volatile 左值（[[diff.class]]）。

这里只看直接基类和非静态数据成员，而复制构造函数看的是包括虚基类在内的所有潜在构造子对象。原因是赋值不区分最派生对象和基类子对象，虚基类由各个直接基类的赋值运算符顺带处理（见 ¶12）。

### 移动赋值（¶4–¶5）

¶4 类定义没有显式声明移动赋值运算符时，当且仅当下面几条全部成立，才隐式声明一个预置的移动赋值运算符：

- ¶4.1 不是匿名联合体；
- ¶4.2 没有用户声明的复制构造函数；
- ¶4.3 没有用户声明的移动构造函数；
- ¶4.4 没有用户声明的复制赋值运算符；
- ¶4.5 没有用户声明的析构函数。

¶5 它的形式是 `X& X::operator=(X&&)`。

```cpp run title="explicit-default-move.cpp" ok
#include <type_traits>

struct S1 {
    int a;
    S1& operator=(const S1&) = default;
};   // 没有移动赋值，右值赋值调用复制赋值

struct S2 {
    int a;
    S2& operator=(const S2&) = default;
    S2& operator=(S2&&) = default;   // 显式预置
};

static_assert(std::is_move_assignable_v<S1>);
static_assert(std::is_move_assignable_v<S2>);
int main() { }
```

标准例 2 说明，`= default` 也算用户声明，所以 `S1` 没有隐式移动赋值运算符，需要的话像 `S2` 那样显式预置。`std::is_move_assignable_v<S1>` 仍然为真，因为它只检查能否用右值赋值，而右值可以绑定 `const S1&`。

写了 `X& operator=(X)` 的类同理：它是用户声明的复制赋值运算符，移动赋值运算符不会隐式声明（¶4.4）。不过右值赋值依然高效，实参会被移动构造到形参里。

¶6 隐式声明的复制/移动赋值运算符的返回类型是 `X&`，是类的 inline public 成员。

## 何时定义为弃置（¶7）

```cpp title="assign-deleted.cpp" error
#include <string>

struct C  { const int c; };
struct R  { int& r; };
struct CS { const std::string s; };
union  U  { std::string s; int i; U() : i(0) { } ~U() { } };

void f(C& c1, C& c2, R& r1, R& r2,
       CS& s1, CS& s2, U& u1, U& u2) {
    c1 = c2;   // error: ¶7.1
    r1 = r2;   // error: ¶7.2
    s1 = s2;   // error: ¶7.3
    u1 = u2;   // error: ¶7.3
}
```

¶7 类 `X` 有下列情况之一时，它的预置复制/移动赋值运算符定义为弃置：

- ¶7.1 有 const 非类类型（或其多维数组）的非静态数据成员；
- ¶7.2 有引用类型的非静态数据成员；
- ¶7.3 有直接的类类型 `M`（或其多维数组）的非静态数据成员或直接基类 `M`，它无法复制/移动：为它找赋值运算符的重载决议找不到可用的候选；或者它是**变体成员**（[[g:variant-member]]，联合体的成员），而选中的函数非平凡。

每一条都有直接的理由：

- ¶7.1：const 标量不能赋值。const 类类型的成员（如 `CS::s`）由 ¶7.3 处理，`operator=` 不是 const 成员函数，对 const 对象调用它的重载决议会失败。
- ¶7.2：引用不能重新绑定。逐成员赋值 `r = other.r` 只会把一个被引用对象的值赋给另一个被引用对象，而不会让 `r` 改指别处。这几乎不会是用户想要的语义，所以干脆删除。复制构造没有这个问题，新对象的引用直接绑定同一个对象。
- ¶7.3 的变体成员条款：联合体不知道哪个成员活跃，只能按字节复制（¶13），某个成员的赋值非平凡时就只能删除。

注 4：定义为弃置的预置移动赋值运算符会被重载决议忽略，右值赋值可以改用复制赋值。

!!! tip "有引用或 const 成员，又想可赋值"
    把引用成员换成 `std::reference_wrapper<T>` 或指针；把 const 成员换成私有的非 const 成员，配一个只读访问器。

## 派生类总会隐藏基类的 `operator=`（¶8）

```cpp title="assign-hidden.cpp" error
struct B { B& operator=(int); };
struct D : B { };
struct E : B { using B::operator=; };

void k(D& d, E& e) {
    d = 1;   // error: D::operator= 隐藏了 B::operator=(int)
    e = 1;   // OK
}
```

¶8 用户不声明时编译器总会隐式声明复制/移动赋值运算符，所以基类的复制/移动赋值运算符总是被派生类相应的赋值运算符隐藏（[[over.assign]]）。

名字隐藏按名字进行，所以 `D` 隐式声明的 `operator=` 把基类的所有 `operator=` 都隐藏了，包括 `B::operator=(int)`。要在派生类里使用它们，就像 `E` 那样写 using 声明。

注 5 补充，这样的 using 声明永远不会抑制派生类自己的赋值运算符的隐式声明，即使引入的基类运算符放在派生类里看起来像复制或移动赋值运算符。

## 平凡的赋值运算符（¶9）

```cpp run title="trivial-assign.cpp" ok
#include <type_traits>

struct S {
    S& operator=(const S&) & = default;
    int x;
};
struct T {
    T& operator=(this T&, const T&) = default;
    int x;
};

static_assert(std::is_trivially_copy_assignable_v<S>);
static_assert(std::is_trivially_copy_assignable_v<T>);
int main() { }
```

¶9 复制/移动赋值运算符**平凡**的前提是它不是**用户提供**（[[g:user-provided]]，用户声明了它，且没有在第一次声明处 `= default` 或 `= delete`）的，此外：

- ¶9.1 类没有虚函数和虚基类；
- ¶9.2 为每个直接基类选中的赋值运算符是那个基类自己的直接成员，并且平凡；
- ¶9.3 为每个类类型（或其数组）的非静态数据成员选中的赋值运算符平凡。

平凡的赋值运算符相当于复制对象的字节。上例说明，预置时加上 `&` 限定符或改用显式对象形参（[[dcl.fct.def.default#2]] 允许这两种差异），不影响平凡性。

虚函数使赋值非平凡，原因与复制构造类似：`Base& b = derived; b = other_base;` 如果按字节复制，就会把 `derived` 的虚表指针覆盖掉。赋值运算符必须保留目标对象的虚表指针，只复制数据成员。

## 隐式定义（¶10–¶14）

¶10 隐式定义的复制/移动赋值运算符是 `constexpr` 的。

¶11 预置的赋值运算符被隐式定义之前，它的直接基类和非静态数据成员的所有非用户提供的复制/移动赋值运算符先被隐式定义。隐式声明的版本有隐含的异常说明（注 6，[[except.spec]]）。

### 非联合体：逐成员赋值（¶12）

¶12 非联合体类的隐式赋值运算符，先按 *base-specifier-list* 中的顺序赋值直接基类，再按声明顺序赋值直接非静态数据成员。设 `x` 是函数的形参；对移动赋值，`x` 是指代形参的 xvalue。每个子对象按它的类型处理：

- ¶12.1 类类型：如同以该子对象为对象表达式、以 `x` 中的对应子对象为实参调用 `operator=`，并且如同带显式限定，即不经虚分派；
- ¶12.2 数组：逐元素赋值；
- ¶12.3 标量：用内置赋值运算符。

虚基类子对象是否被赋值不止一次，是未指定的 {{unspec}}：

```cpp run title="vbase-assign.cpp" unspecified
#include <cstdio>

struct V {
    V& operator=(const V&) {
        std::puts("V::operator=");
        return *this;
    }
};
struct A : virtual V { };
struct B : virtual V { };
struct C : B, A { };

int main() {
    C c1, c2;
    c1 = c2;   // V::operator= 调用一次还是两次？
}
```

本机 Clang 23 打印了两次：`C` 的隐式赋值依次调用 `B::operator=` 和 `A::operator=`，二者都赋值了 `V`。构造没有这个问题，因为构造函数有完整对象和基类子对象两个版本，虚基类只由最派生类构造一次（[[class.base.init]]）；赋值运算符只有一个版本。要避免重复赋值只能手写，这也是虚基类最好不含数据的理由之一。

### 联合体：复制对象表示（¶13）

```cpp run title="union-assign.cpp" ok
union U { int i; float f; };

int main() {
    U a, b;
    a.i = 1;
    b.f = 2.0f;
    b = a;          // b.i 成为 b 的活跃成员
    return b.i - 1;
}
```

¶13 联合体的隐式赋值运算符复制整个对象表示。如果源和目标不是同一个对象，那么对源里嵌套的每个对象，在目标中创建一个对应的对象，它的生命周期在复制之前开始。

这与复制构造函数（[[class.copy.ctor#16]]）的区别只在于自赋值：`u = u` 时活跃成员本来就在，不需要创建。

¶14 隐式定义的赋值运算符返回被赋值的对象，即 `*this`。

## 手写赋值运算符：自赋值与异常安全

标准对用户写的赋值运算符没有要求，但有两个经典问题。逐成员赋值天然对自赋值安全，每个成员都赋给了自己；手写的资源管理代码则容易出错：

```cpp title="self-assign-bug.cpp" ub
#include <cstring>

struct Str {
    char* p;
    explicit Str(const char* s)
        : p(new char[std::strlen(s) + 1]) { std::strcpy(p, s); }
    ~Str() { delete[] p; }
    Str(const Str& o) : Str(o.p) { }
    Str& operator=(const Str& o) {
        delete[] p;   // 自赋值时 o.p 也被释放了
        p = new char[std::strlen(o.p) + 1];   // UB: 读已释放的内存
        std::strcpy(p, o.p);
        return *this;
    }
};

int main() {
    Str s("hello");
    Str& alias = s;
    s = alias;
}
```

AddressSanitizer 在这里报告 heap-use-after-free。复制并交换同时解决了自赋值和强异常安全：

```cpp run title="copy-and-swap.cpp" ok
#include <cstring>
#include <utility>

struct Str {
    char* p;
    explicit Str(const char* s)
        : p(new char[std::strlen(s) + 1]) { std::strcpy(p, s); }
    ~Str() { delete[] p; }
    Str(const Str& o) : Str(o.p) { }
    Str(Str&& o) noexcept : p(std::exchange(o.p, nullptr)) { }
    Str& operator=(Str o) noexcept {   // 复制赋值运算符（¶1）
        std::swap(p, o.p);             // 不会失败
        return *this;                  // 旧资源随 o 析构
    }
};

int main() {
    Str s("hello"), t("world");
    s = t;            // 复制构造形参，然后交换
    s = Str("tmp");   // 移动构造形参，然后交换
    return std::strcmp(s.p, "tmp");
}
```

按值形参的 `operator=` 同时承担复制赋值和移动赋值，代价是每次多一次移动构造。性能敏感的类通常分别写 `const X&` 和 `X&&` 两个版本。

手写派生类的赋值运算符时，要显式调用 `B::operator=(o)`。编译器不会替你补上基类部分的赋值，这一点和构造函数会自动默认构造基类不同。

## 禁止给右值赋值

内置赋值要求左操作数是可修改的左值，但类的隐式赋值运算符没有引用限定符，所以 `f() = x;`、`std::string("a") = "b";` 都能编译。预置的赋值运算符可以加 `&` 限定符（[[dcl.fct.def.default#2]]），只允许对左值赋值：

```cpp title="ref-qualified-assign.cpp" error
struct S {
    S& operator=(const S&) & = default;
    int x;
};
S f();

void g() {
    S a{};
    a = S{};     // OK
    f() = S{};   // error: & 限定的 operator= 要求左值
}
```

标准库为了兼容没有这样做。新设计的值类型给赋值运算符加上 `&`，就能在编译期发现给临时对象赋值这类错误。

## 实现视角

!!! impl "平凡赋值与尾部填充"
    平凡的复制/移动赋值在代码生成上就是复制字节，但有一个 ABI 细节。Itanium C++ ABI 允许派生类的成员放进基类的尾部填充里，基类的数据大小 dsize 可以小于 `sizeof`。所以被赋值的对象可能是**潜在重叠子对象**（[[g:potentially-overlapping-subobject]]）时，编译器只复制 dsize 个字节，否则会覆盖派生类的成员。[[basic.types.trivial]] 中按字节复制能保持值的保证也只针对非潜在重叠的对象，自己调用 `memcpy` 时要遵守同样的前提。

## 历史与演进

!!! history
    - C++98 已有复制赋值运算符及其 `X&` 退化形式。那时 const 成员或引用成员使隐式赋值在使用时非良构。
    - C++11 引入移动赋值，用定义为弃置取代了隐式定义非良构；声明了移动操作时隐式复制赋值被删除；有用户声明的复制构造函数或析构函数时，隐式复制赋值被弃用；允许预置的赋值运算符带 `&` 限定符。
    - C++20 规定联合体被隐式赋值时，目标中对应的成员开始生命周期（[[P0593R6]]）。
    - C++23 引入显式对象形参（[[P0847R7]]），预置的赋值运算符也可以用；隐式定义的赋值运算符改为无条件 `constexpr`。

## 常见误解

!!! pitfall "以为 const 成员只影响赋值"
    const 成员使赋值被删除，而 `std::vector` 的 `insert`、`erase` 和 `std::sort` 都要求元素可以移动赋值，于是这个类型也不能用在这些地方。需要值语义的类应避免 const 数据成员。

!!! pitfall "虚赋值运算符"
    把 `operator=` 声明为 `virtual` 几乎总是错误的设计。派生类的 `operator=(const Derived&)` 形参类型不同，并不覆盖基类的 `operator=(const Base&)`。多态类型通常应禁止赋值（`= delete`），另外提供 `clone()`。

## 思考题

!!! question "思考题 1"
    ```cpp
    struct A { A& operator=(A); };   // 按值
    struct B { A a; };
    ```
    `B` 的隐式复制赋值运算符是什么形式？对 `B` 做移动赋值时，`a` 是被移动还是被复制？

<details markdown="1">
<summary>答案</summary>

`A::operator=(A)` 的形参类型是 `A`，满足 ¶2.2，所以 `B` 的隐式复制赋值是 `B& operator=(const B&)`。`B` 没有任何用户声明的特殊成员函数，按 ¶4 也有隐式移动赋值 `B& operator=(B&&)`。

它移动赋值 `a` 时选中 `A::operator=(A)`，实参是 xvalue，形参 `A` 本应由移动构造函数初始化。但 `A` 有用户声明的复制赋值运算符，所以没有隐式移动构造函数（[[class.copy.ctor#8]]），形参只能复制构造。结果是移动 `B` 实际上复制了 `a`。

</details>

!!! question "思考题 2"
    ¶7 删除了有引用成员的类的赋值运算符，却不删除它的复制构造函数。为什么？

<details markdown="1">
<summary>答案</summary>

复制构造创建新对象，新对象的引用成员绑定到源对象的引用所绑定的那个对象，语义清楚。赋值修改已有对象，而引用一经绑定就不能改变，`r = o.r` 只会修改被引用对象的值。赋值之后两个对象并不相等，还顺带改了第三方对象，所以默认删除，让用户自己决定语义。

</details>

## 小结

| | 复制赋值 | 移动赋值 |
|---|---|---|
| 识别 | 非静态非模板；一个非对象形参：`X` 或 `cv X&` | 非静态非模板；一个非对象形参：`cv X&&` |
| 隐式声明 | 没有用户声明的复制赋值 | 没有用户声明的复制构造、移动构造、复制赋值、析构 |
| 形式 | `X& operator=(const X&)`，必要时 `X& operator=(X&)` | `X& operator=(X&&)` |
| 弃置 | 声明了移动操作；const 标量成员；引用成员；直接成员或基类不可赋值 | 后三条同左；弃置后被重载决议忽略 |
| 平凡 | 非用户提供，无虚函数和虚基类，选中的基类和成员赋值都平凡 | 同左 |
| 隐式定义 | 先基类后成员，按声明顺序；虚基类可能赋值多次；返回 `*this` | 同左，源为 xvalue |
