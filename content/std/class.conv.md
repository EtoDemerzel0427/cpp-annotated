---
title: 转换
summary: 用户定义转换的两种来源（转换构造函数与转换函数）、"至多一个隐式用户定义转换"、explicit 构造函数与 explicit 转换函数（explicit operator bool 与按语境转换）、转换函数的声明形式、隐藏规则、虚转换函数与转换函数模板
status: draft
covers: class.conv.general, class.conv.ctor, class.conv.fct
related: conv, over.best.ics, over.match.copy, over.match.conv, dcl.init, dcl.fct.spec, expr.static.cast, class.member.lookup
tags: 用户定义转换, explicit, 转换函数, operator bool
updated: 2026-10-18
---

内置类型之间有标准转换（[[conv]]）：`int` 到 `double`、数组到指针……类类型则通过**用户定义转换**（user-defined conversions）参与隐式转换。本节规定这种转换的两种来源和基本限制：

- **转换构造函数**：从别的类型转换**到**本类；
- **转换函数**（`operator T()`）：从本类转换**到**别的类型。

本页覆盖 11.4.8 的三个子条款：[[class.conv.general]]（总则，下文 ¶ 编号默认指此条款）、[[class.conv.ctor]]、[[class.conv.fct]]。用户定义转换在重载决议中如何排名，见 [[over.best.ics]] 与 [[over.ics.user]]。

## 用户定义转换是什么（¶1–¶3）

¶1：类对象的类型转换可以由**构造函数**和**转换函数**指定。这些转换称为**用户定义转换**，用于：

- 隐式类型转换（[[conv]]），如函数实参、返回值、赋值；
- 初始化（[[dcl.init]]）；
- 显式类型转换（[[expr.type.conv]]、[[expr.cast]]、[[expr.static.cast]]）。

¶2：用户定义转换**只在无二义时**才被应用（[[class.member.lookup]]、[[class.conv.fct]]）。转换遵守访问控制规则（[[class.access]]），**访问控制在二义性决议之后**进行（[[basic.lookup]]）——一个私有的转换函数仍会参与决议，若被选中才报"不可访问"，而不是被悄悄忽略。

¶3 注 1：函数调用中转换的使用见 [[over.match]]。

## 至多一个用户定义转换（¶4）

¶4：**对单个值，至多隐式应用一个用户定义转换**（构造函数或转换函数）。

这是整个隐式转换体系中最重要的一条限制。一个**隐式转换序列**（[[over.best.ics]]）的完整形态是：

```text
标准转换序列  →  一个用户定义转换  →  标准转换序列
```

即"用户定义转换"两侧可以各有一串标准转换，但中间只能有**一个**用户定义转换。标准例 1：

```cpp title="one-udc.cpp" error
struct X { operator int(); };
struct Y { operator X(); };

Y a;
int b = a;          // error: 需要 Y→X→int 两个用户定义转换，不予考虑
int c = X(a);       // OK: X(a) 是显式转换（调用 a.operator X()），之后 X→int 只有一个
```

为什么要限制？

1. **可预测性**：若允许链式转换，`a` 可以经过任意长的类型链到达目标，读代码的人无法判断发生了什么；
2. **可判定性与效率**：编译器无需在类型图上搜索路径——只要看源类型的转换函数和目标类型的构造函数；
3. **避免二义的爆炸**：两条不同的转换链极易并存。

注意"对单个值"：函数调用的**每个实参**各自可以有一个用户定义转换；而一个转换构造函数的**实参**也可以再经过一个用户定义转换，只要那是**直接初始化**语境（构造函数的形参初始化本身是新的"单个值"）：

```cpp title="udc-per-value.cpp" error
struct A { A(int) { } };
struct B { B(A) { } };

B b1(1);        // OK: 直接初始化，考虑 B 的构造函数 B(A)；实参 1 → A 用一次用户定义转换
B b2 = 1;       // error: 复制初始化要求 int → B 的一个隐式转换序列，而 int→A→B 需要两个
void g(B);
void h() {
    g(1);       // error: 同 b2，实参到形参的隐式转换只能有一个用户定义转换
    g(A(1));    // OK: A→B 只需一个
}
```

`b1` 与 `b2` 的差别在 [[over.match.ctor]] 与 [[over.match.copy]]：直接初始化把 `B` 的构造函数当作普通函数做重载决议，实参 `1` 到形参 `A` 的转换是一个"新的"隐式转换序列；复制初始化则要求一个从 `int` 到 `B` 的隐式转换（[[over.best.ics#4]] 还专门禁止在这种情况下对构造函数的实参再次使用用户定义转换）。

---

# 通过构造函数转换（[class.conv.ctor]）

## 转换构造函数（[class.conv.ctor] ¶1）

[[class.conv.ctor#1]]：一个**不是 `explicit` 的**构造函数指定了一个从其形参类型到其类类型的转换。这样的构造函数习惯上称为**转换构造函数**（converting constructor）。

C++11 之前，只有"能用单个实参调用"的构造函数才被叫作转换构造函数；C++11 起，因为**列表初始化**也可以隐式调用多参数构造函数，任何非 explicit 构造函数都是转换构造函数。标准例 1：

```cpp run title="converting-ctor.cpp" ok
struct X {
    X(int) { }
    X(const char*, int = 0) { }
    X(int, int) { }
};

void f(X) { }

int main() {
    X a = 1;          // a = X(1)
    X b = "Jessie";   // b = X("Jessie", 0)
    a = 2;            // a = X(2)：先转换出临时 X，再赋值
    f(3);             // f(X(3))
    f({1, 2});        // f(X(1, 2))：复制列表初始化，使用两参数的转换构造函数
    (void)b;
}
```

## explicit 构造函数（[class.conv.ctor] ¶2）

[[class.conv.ctor#2]] 注 1：`explicit` 构造函数与非 explicit 构造函数一样构造对象，但**只在**使用了**直接初始化语法**（[[dcl.init]]）或**显式转换**（[[expr.static.cast]]、[[expr.cast]]）时才会被使用；另见 [[over.match.copy]]。默认构造函数也可以是 explicit 的，它会被用于默认初始化和值初始化。标准例 2：

```cpp title="explicit-ctor.cpp" error
struct Z {
    explicit Z();
    explicit Z(int);
    explicit Z(int, int);
};

Z a;                        // OK: 默认初始化
Z b{};                      // OK: 直接列表初始化
Z c = {};                   // error: 复制列表初始化不能用 explicit 构造函数
Z a1 = 1;                   // error: 没有隐式转换
Z a3 = Z(1);                // OK: Z(1) 是直接初始化（显式转换）
Z a2(1);                    // OK: 直接初始化
Z* p = new Z(1);            // OK: 直接初始化
Z a4 = (Z)1;                // OK: 显式转换
Z a5 = static_cast<Z>(1);   // OK: 显式转换
Z a6 = { 3, 4 };            // error: 复制列表初始化，没有隐式转换
```

关于复制列表初始化的一个细节：`Z c = {};` 和 `Z a6 = {3, 4};` 中，重载决议**会考虑** explicit 构造函数，但如果选中的是 explicit 的，程序非良构（[[over.match.list]]）。这与复制初始化 `Z a1 = 1;`（explicit 构造函数根本不是候选）不同，在存在多个重载时会产生差别。

### 什么时候应该写 explicit

经验法则：**单参数构造函数默认写 `explicit`**，除非这个转换是"无损的、语义相同的"（如 `std::string(const char*)`、`std::complex<double>(double)`、`std::chrono::duration` 之间的无损转换）。

隐式转换构造函数的危险在于它会**悄悄**参与重载决议：

```cpp title="implicit-danger.cpp" error
#include <vector>

struct Buffer {
    explicit Buffer(std::size_t n) : data(n) { }   // explicit：防止 Buffer b = 42;
    std::vector<char> data;
};

void send(const Buffer&) { }

void use() {
    send(Buffer(1024));   // OK: 意图明确
    send(1024);           // error: 若构造函数不是 explicit，这会悄悄分配 1024 字节的缓冲区
}
```

### 条件 explicit：`explicit(bool)` {{c++20}}

C++20 允许 `explicit(常量表达式)`（[[dcl.fct.spec]]），这让包装类型能"转发"被包装类型的 explicit 性——`std::pair`、`std::tuple`、`std::optional` 的转换构造函数都用它取代了过去成对的 SFINAE 重载：

```cpp run title="conditional-explicit.cpp" ok
#include <type_traits>
#include <string>

template<class T>
struct Wrapper {
    T value;
    template<class U>
    explicit(!std::is_convertible_v<U, T>)      // U→T 能隐式转换时，Wrapper 的转换也是隐式的
    Wrapper(U&& u) : value(static_cast<U&&>(u)) { }
};

int main() {
    Wrapper<std::string> w1 = "hello";          // OK: const char* → std::string 是隐式的
    Wrapper<std::string> w2(std::string_view("hi")); // OK: 直接初始化
    // Wrapper<std::string> w3 = std::string_view("hi");  // error: string_view → string 是 explicit 的
    return static_cast<int>(w1.value.size() + w2.value.size()) - 7;
}
```

---

# 转换函数（[class.conv.fct]）

## 声明形式（[class.conv.fct] ¶1–¶2）

```text
conversion-function-id:  operator conversion-type-id
conversion-type-id:      type-specifier-seq conversion-declarator(可选)
conversion-declarator:   ptr-operator conversion-declarator(可选)
```

[[class.conv.fct#1]]：*declarator-id* 的 *unqualified-id* 是 *conversion-function-id*（`operator T`）的声明，声明一个**转换函数**。其声明符形如 `noptr-declarator parameters-and-qualifiers`（即后面紧跟形参列表与限定符），*id-expression* 在类内非友元声明中是 *conversion-function-id*（¶1.1），否则是以它结尾的 *qualified-id*（¶1.2，如类外定义 `X::operator int() { ... }`）。

[[class.conv.fct#2]]：转换函数**没有非对象形参**，必须是类或类模板 `X` 的**非静态成员函数**；它的声明返回类型就是 *conversion-type-id*，指定一个从 `X` 到该类型的转换。*decl-specifier-seq*（若有）中**不能**有定义类型说明符——返回类型**只**写在 `operator` 之后。

```cpp title="conv-fct-decl.cpp" error
struct X {
    operator int();                  // OK
    explicit operator double() const;// OK
    operator const char*() const;    // OK: conversion-type-id 可以含 ptr-operator
    int operator long();             // error: 不能在前面写返回类型
    operator auto() -> short;        // error: 不能有尾随返回类型
    static operator char();          // error: 转换函数必须是非静态成员
    operator bool(int);              // error: 转换函数不能有形参
};
```

由于"没有非对象形参"的措辞，C++23 起转换函数可以有**显式对象形参**（`operator int(this const X& self)`）。

## 永不调用的转换函数（[class.conv.fct] ¶3）

[[class.conv.fct#3]] 注 1：转换函数**永远不会**被调用来把对象转换为**同一对象类型**（或其引用）、其**基类**类型（或引用）、或 `cv void`。这些转换由其他机制完成（复制构造、派生到基类的标准转换、弃值）。注 1 也指出，这样的转换函数**可以声明**，并可能通过基类中的**虚**转换函数被间接调用到。

例 1 说明三种写法都调用 `X::operator int()`：`int(a)`、`(int)a`、`i = a`。

## explicit 转换函数（[class.conv.fct] ¶4）

[[class.conv.fct#4]]：转换函数可以是 `explicit` 的（C++11 起），此时它**只在直接初始化**中被视为用户定义转换（[[dcl.init]]）。非 explicit 的则不限于赋值和初始化——它可以出现在任何需要隐式转换的地方（算术运算的操作数、函数实参……）。

```cpp title="explicit-conv-fct.cpp" error
class Y { };
struct Z {
    explicit operator Y() const;
};

void h(Z z) {
    Y y1(z);          // OK: 直接初始化
    Y y2 = z;         // error: 复制初始化中 explicit 转换函数不是候选
    Y y3 = (Y)z;      // OK: 强制转换记法
}
```

### `explicit operator bool` 与按语境转换

explicit 转换函数最重要的用途是 **`explicit operator bool`**——"安全 bool"惯用法的现代形式。关键在于：`if`、`while`、`for` 的条件，`!`、`&&`、`||` 的操作数，`?:` 的第一个操作数，`static_assert` 和 `noexcept(...)` 的操作数等处，表达式被**按语境转换为 `bool`**（contextually converted to bool，[[conv.general#4]]），其定义是"`bool t(e);` 良构"——这是**直接初始化**，所以会考虑 explicit 转换函数：

```cpp title="explicit-bool.cpp" error
struct S {
    explicit operator bool() const { return true; }
};

void use(S s) {
    if (s) { }                  // OK: 按语境转换
    bool b1 = s ? true : false; // OK
    bool b2 = !s;               // OK
    bool b3(s);                 // OK: 直接初始化
    bool b4 = s;                // error: 复制初始化，explicit 转换函数不可用
    int  i  = s + 1;            // error: 不会悄悄转换成 bool 再提升为 int
}
```

C++98 中如果写 `operator bool()`，`s + 1`、`s1 == s2`（两个都转 `bool` 再比较）、`int x = s;` 都会编译——这就是为什么当年的智能指针要用"指向成员的指针"实现"安全 bool"惯用法。C++11 的 `explicit operator bool` 让这一切变得简单。标准例 2 的 `g(X a, X b)`（`X` 有非 explicit 的 `operator int()`）中，`(a) ? 1+a : 0`、`(a&&b) ? a+b : i`、`if (a)` 都调用 `operator int()` 后再转换——非 explicit 的转换函数无处不在。

## 转换类型标识的最长匹配（[class.conv.fct] ¶5）

[[class.conv.fct#5]]：*conversion-type-id* 不能表示函数类型或数组类型（要返回数组的引用或函数指针，用别名：`using Arr = int[3]; operator Arr&();`）。*conversion-function-id* 中的 *conversion-type-id* 是**能构成 *conversion-type-id* 的最长记号序列**。注 2：这消除了声明符 `*` 与表达式中乘号的歧义：

```cpp
&ac.operator int*i;   // 语法错误：被解析为 &(ac.operator int*) i，而不是 &(ac.operator int) * i
```

同理也消除了属性的歧义：`operator int [[noreturn]] ();` 中 `[[noreturn]]` 归属于类型 `int`（被解析为 *conversion-type-id* 的一部分），而 `noreturn` 不能用于类型——错误。

## 隐藏与二义（[class.conv.fct] ¶6）

[[class.conv.fct#6]] 注 3：派生类中的转换函数**只隐藏**基类中**转换到同一类型**的转换函数。（因为转换函数的"名字"是 `operator T`，类型不同就是不同的名字。）具有依赖返回类型的转换函数模板只隐藏基类中与之**对应**的模板；否则它与非模板函数一样隐藏和被隐藏。函数重载决议（[[over.match.best]]）选出最好的转换函数。标准例 5：

```cpp title="conv-ambiguous.cpp" error
struct X { operator int(); };
struct Y : X { operator char(); };

void f(Y& a) {
    if (a) { }    // error: X::operator int() 与 Y::operator char() 二义
}
```

`Y::operator char` 没有隐藏 `X::operator int`（名字不同），两者都可行；转换到 `bool` 时，`int→bool` 与 `char→bool` 都是布尔转换，排名相同——二义。

## 虚转换函数（[class.conv.fct] ¶7）

[[class.conv.fct#7]]：转换函数可以是虚函数。

```cpp run title="virtual-conv.cpp" ok
struct Base {
    virtual operator int() const { return 1; }
    virtual ~Base() = default;
};
struct Derived : Base {
    operator int() const override { return 2; }
};

int main() {
    Derived d;
    const Base& b = d;
    int v = b;           // 虚分派：调用 Derived::operator int
    return v - 2;
}
```

## 转换函数模板（[class.conv.fct] ¶8）

转换函数可以是**模板**：`template<class T> operator T() const;`。模板实参从**目标类型**推导（[[temp.deduct.conv]]）——这是"返回类型推导模板实参"的唯一场合。典型用途是"万能的空值/默认值"代理：

```cpp run title="conv-template.cpp" ok
struct Default {
    template<class T>
    operator T() const { return T{}; }
};

int main() {
    int i = Default{};          // T = int
    double d = Default{};       // T = double
    const char* p = Default{};  // T = const char*
    return i + static_cast<int>(d) + (p == nullptr ? 0 : 1);
}
```

[[class.conv.fct#8]]：**转换函数模板不能有推导的返回类型**（[[dcl.spec.auto]]）：

```cpp title="conv-template-auto.cpp" error
struct S {
    template<class T>
    operator auto() const { return 1.2; }   // error: 转换函数模板不能用 auto
};
```

理由：转换函数模板的模板实参要从目标类型推导出来，而 `auto` 返回类型又要从函数体推导——两个方向的推导无法同时进行。（非模板的 `operator auto()` 是允许的：`struct S { operator auto() { return 1; } };` 定义了一个到 `int` 的转换函数。）

## 实现视角

!!! impl "名字修饰"
    Itanium ABI 中转换函数的名字修饰为 `cv` 后跟目标类型，例如 `X::operator int()` 是 `_ZN1XcviEv`。所以转换到不同类型的转换函数是不同的符号——这也是 ¶6"只隐藏同一目标类型"的直观体现。

!!! impl "诊断"
    GCC/Clang 在"差一个用户定义转换"时通常给出 `no viable conversion from 'Y' to 'int'` 这类诊断（Clang），而不会解释"需要两个用户定义转换"。遇到这种错误时，检查是否需要把一个转换写成显式的 `X(a)`。

## 历史与演进

!!! history "历史与演进"
    - **C++98**：转换构造函数（单参数）、`explicit` 构造函数、转换函数、转换函数模板；"至多一个用户定义转换"。
    - **C++11**：**explicit 转换函数**；列表初始化使多参数非 explicit 构造函数也成为转换构造函数；"按语境转换为 bool"的定义使 `explicit operator bool` 可用于条件。
    - **C++14**：非模板转换函数可以用 `auto` 推导返回类型；转换函数模板不行。
    - **C++20**：`explicit(bool)` 条件 explicit。
    - **C++23**：转换函数可以有显式对象形参（[[P0847R7]]）。

## 陷阱

!!! pitfall "隐式转换构造函数与重载决议的意外"
    `void f(std::string); void f(bool);` 调用 `f("hi")` 选的是 `f(bool)`：指针到 `bool` 是标准转换，优于 `const char*` 到 `std::string` 的用户定义转换。

!!! pitfall "以为 `explicit` 能阻止所有隐式使用"
    `explicit operator bool` 在 `if`/`!`/`&&` 中仍会被调用（按语境转换）；`explicit` 构造函数在复制列表初始化中仍会**参与**重载决议，被选中时报错，这可能让原本能选中另一个非 explicit 构造函数的代码变成错误。

!!! pitfall "同时提供转换构造函数与转换函数"
    若 `A` 有 `A(const B&)`，而 `B` 有 `operator A()`，则 `A a = b;` 二义。两个方向的转换只定义一个。

## 思考题

!!! question "思考题 1"
    ```cpp
    struct A { A(int); };
    struct B { operator int(); };
    void f(A);
    void g() { B b; f(b); }
    ```
    `f(b)` 合法吗？

<details markdown="1">
<summary>答案</summary>

**不合法**。实参 `b` 到形参 `A` 需要 `B → int`（`B::operator int`）和 `int → A`（`A::A(int)`）两个用户定义转换，违反 ¶4。改成 `f(A(b))` 即可：直接初始化 `A(b)` 中，`b` 到构造函数形参 `int` 只用一个用户定义转换。
</details>

!!! question "思考题 2"
    为什么 `Z c = {};`（`Z` 只有 `explicit Z();`）是错误，而 `Z b{};` 和 `Z a;` 都可以？

<details markdown="1">
<summary>答案</summary>

`Z a;` 是默认初始化，`Z b{};` 是直接列表初始化（值初始化），二者都是"直接"语境，explicit 构造函数可用。`Z c = {};` 是**复制**列表初始化：[[over.match.list]] 规定重载决议会考虑所有构造函数，但若选中 explicit 构造函数，程序非良构。这样设计是为了让 `= {...}` 形式与 `= expr` 形式的复制初始化在"不调用 explicit 构造函数"这一点上保持一致，同时避免 explicit 构造函数"消失"后静默选中另一个重载。
</details>

!!! question "思考题 3"
    `struct X { operator X&(); operator void(); };` 合法吗？这两个函数会在什么时候被调用？

<details markdown="1">
<summary>答案</summary>

声明合法（编译器可能给出"永远不会被使用"的警告）。按 [[class.conv.fct#3]] 注 1，转换到同一类型（的引用）或 `void` 的转换函数**永远不会**被隐式或显式转换调用：`X& r = x;` 直接绑定，`(void)x` 是弃值。它们只能被**显式调用**（`x.operator X&()`），或者——若在基类中声明为虚函数——通过基类的虚转换函数被间接调用到。
</details>

## 小结

| 主题 | 规则 |
|---|---|
| 来源 | 非 explicit 构造函数（到本类）；转换函数 `operator T()`（从本类） |
| 数量限制 | 每个值至多隐式应用**一个**用户定义转换，两侧可以有标准转换 |
| 二义与访问 | 只在无二义时应用；先决议，后检查访问 |
| explicit 构造函数 | 只用于直接初始化与显式转换；复制列表初始化选中则非良构 |
| explicit 转换函数 | 只用于直接初始化；按语境转换为 `bool` 也算（`if (s)`） |
| 转换函数形式 | 非静态成员；无非对象形参；返回类型写在 `operator` 后；不能是函数/数组类型 |
| 永不调用 | 到自身类型、基类类型（或引用）、`void` |
| 隐藏 | 只隐藏基类中转换到同一类型的转换函数 |
| 虚 / 模板 | 可以是虚函数；可以是模板（目标类型推导 T），但模板不能用 `auto` 返回类型 |
