---
title: 转换
summary: 类类型怎样参与隐式转换：转换构造函数和转换函数这两种用户定义转换，一次隐式转换至多用一个，以及 explicit 怎样限制它们。
status: done
covers: class.conv.general, class.conv.ctor, class.conv.fct
related: conv, over.best.ics, over.match.copy, over.match.conv, dcl.init, dcl.fct.spec, expr.static.cast, class.member.lookup
tags: 用户定义转换, explicit, 转换函数, operator bool
updated: 2026-10-19
---

!!! tldr
    - 用户定义转换有两种来源：非 explicit 的构造函数把别的类型转换为本类，转换函数 `operator T()` 把本类转换为 `T`。
    - 对同一个值，至多隐式应用一个用户定义转换；它前后可以各有一串标准转换。
    - explicit 构造函数和 explicit 转换函数只用于直接初始化和显式转换。`if (x)` 这类按语境转换为 `bool` 的场合算直接初始化，所以 `explicit operator bool` 在条件里照样生效。
    - 转换函数没有形参，返回类型写在 `operator` 后面；它可以是虚函数，也可以是模板，但模板不能用 `auto` 返回类型。
    - 转换到自身类型、基类或 `void` 时，永远不会调用转换函数。

## 用户定义转换 [class.conv.general]

```cpp
struct Meters {
    Meters(double v);              // double → Meters
    operator double() const;       // Meters → double
};
```

内置类型之间靠标准转换（[[conv]]）互相转换，例如 `int` 到 `double`。¶1 类类型则通过构造函数和转换函数指定转换，这两种转换统称**用户定义转换**（user-defined conversions）。它们用在隐式转换（传参、返回、赋值等）、初始化（[[dcl.init]]）和显式转换（[[expr.type.conv]]、[[expr.cast]]、[[expr.static.cast]]）中。上面的 `Meters` 两个方向都有：构造函数从 `double` 转换过来，转换函数转换回 `double`。

¶2 用户定义转换只在无二义时才会应用。它们遵守访问控制（[[class.access]]），而且访问检查在消除二义之后进行。所以一个私有的转换函数照样参与选择，被选中之后才报告不可访问，不会被悄悄跳过。

¶3 注 1 指出，函数调用中怎样使用这些转换，由重载决议决定（[[over.match]]）。

### 一次至多一个（¶4）

¶4 对同一个值，至多隐式应用一个用户定义转换，不论它是构造函数还是转换函数。标准例 1：

```cpp title="one-udc.cpp" error
struct X { operator int(); };
struct Y { operator X(); };

Y a;
int b = a;      // error: Y→X→int 要两个用户定义转换
int c = X(a);   // OK: X(a) 是显式转换，之后 X→int 只需一个
```

所以一个隐式转换序列（[[over.best.ics]]）最多是这样的形状：

```text
标准转换序列 → 一个用户定义转换 → 标准转换序列
```

这样限制有两个好处。读代码的人不用猜一个值经过了多长的类型链；编译器也不用在类型之间搜索路径，只需查看源类型的转换函数和目标类型的构造函数，二义的情况也少得多。

限制针对的是单个值。在直接初始化里，构造函数的形参本身是一个新的值，它可以再用一次用户定义转换：

```cpp title="udc-per-value.cpp" error
struct A { A(int) { } };
struct B { B(A) { } };

B b1(1);        // OK: 选中 B(A)，实参 1 → A 用一次
B b2 = 1;       // error: 需要 int→A→B 两次
void g(B);
void h() {
    g(1);       // error: 同 b2
    g(A(1));    // OK: A→B 只需一次
}
```

`b1` 是直接初始化：`B` 的构造函数像普通函数一样参与重载决议（[[over.match.ctor]]），实参 `1` 到形参 `A` 是一个独立的隐式转换。`b2` 是复制初始化，要求从 `int` 直接到 `B` 的一个隐式转换（[[over.match.copy]]），[[over.best.ics#4]] 还专门禁止此时在构造函数的实参上再用一次用户定义转换。

## 转换构造函数 [class.conv.ctor]

¶1 不是 explicit 的构造函数，指定了从它的形参类型到它的类类型的转换。这样的构造函数叫**转换构造函数**（converting constructor）。标准例 1：

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
    a = 2;            // a = X(2)：先转换出临时对象，再赋值
    f(3);             // f(X(3))
    f({1, 2});        // f(X(1, 2))：复制列表初始化
    (void)b;
}
```

最后一行说明转换构造函数不限于单个形参。C++11 之前只有能用一个实参调用的构造函数才叫转换构造函数；有了列表初始化以后，`{1, 2}` 也能隐式转换为 `X`，所以任何非 explicit 构造函数都算。

### explicit 构造函数（¶2）

¶2 注 1 说明，explicit 构造函数和普通构造函数一样构造对象，但只在使用直接初始化语法（[[dcl.init]]）或显式转换（[[expr.static.cast]]、[[expr.cast]]）时才会用到。默认构造函数也可以是 explicit 的，默认初始化和值初始化会用到它。标准例 2：

```cpp title="explicit-ctor.cpp" error
struct Z {
    explicit Z();
    explicit Z(int);
    explicit Z(int, int);
};

Z a;                        // OK: 默认初始化
Z b{};                      // OK: 直接列表初始化
Z c = {};                   // error: 复制列表初始化
Z a1 = 1;                   // error: 没有隐式转换
Z a3 = Z(1);                // OK: Z(1) 是显式转换
Z a2(1);                    // OK: 直接初始化
Z* p = new Z(1);            // OK: 直接初始化
Z a4 = (Z)1;                // OK: 显式转换
Z a5 = static_cast<Z>(1);   // OK: 显式转换
Z a6 = { 3, 4 };            // error: 复制列表初始化
```

`Z a1 = 1;` 和 `Z c = {};` 失败的方式不同。在复制初始化 `Z a1 = 1;` 中，explicit 构造函数根本不是候选。在复制列表初始化 `Z c = {};`、`Z a6 = {3, 4};` 中，explicit 构造函数仍然参与重载决议，但如果选中的是它，程序非良构（[[over.match.list]]）。有多个重载时，这个差别会改变结果：explicit 构造函数可能抢走本来会选中的非 explicit 构造函数，然后报错。

一般的做法是单参数构造函数默认写 `explicit`，除非这个转换不丢信息、含义也不变，比如 `std::string(const char*)`。隐式转换构造函数会在不知不觉中参与重载决议：

```cpp title="implicit-danger.cpp" error
#include <vector>

struct Buffer {
    explicit Buffer(std::size_t n) : data(n) { }
    std::vector<char> data;
};

void send(const Buffer&) { }

void use() {
    send(Buffer(1024));   // OK: 意图明确
    send(1024);           // error: 没有 explicit 的话，这里会悄悄分配 1024 字节
}
```

### 条件 explicit {{c++20}}

C++20 起可以写 `explicit(常量表达式)`（[[dcl.fct.spec]]），让包装类型的转换是否 explicit 跟随被包装的类型。`std::pair`、`std::tuple`、`std::optional` 都用它取代了过去成对的重载：

```cpp run title="conditional-explicit.cpp" ok
#include <type_traits>
#include <string>

template<class T>
struct Wrapper {
    T value;
    template<class U>
    explicit(!std::is_convertible_v<U, T>)   // U→T 隐式，Wrapper 也隐式
    Wrapper(U&& u) : value(static_cast<U&&>(u)) { }
};

int main() {
    // OK: const char* → std::string 是隐式的
    Wrapper<std::string> w1 = "hello";
    // OK: 直接初始化
    Wrapper<std::string> w2(std::string_view("hi"));
    // error: string_view → string 是 explicit 的
    // Wrapper<std::string> w3 = std::string_view("hi");
    return static_cast<int>(w1.value.size() + w2.value.size()) - 7;
}
```

## 转换函数 [class.conv.fct]

### 声明形式（¶1–¶2）

```text
conversion-function-id:  operator conversion-type-id
conversion-type-id:      type-specifier-seq conversion-declarator(opt)
conversion-declarator:   ptr-operator conversion-declarator(opt)
```

¶1 名字形如 `operator T` 的函数声明声明了一个**转换函数**（conversion function）。在类内声明时直接写 `operator T`（¶1.1）；在类外定义或在友元声明中，要写成限定名，如 `X::operator int()`（¶1.2）。

¶2 转换函数必须是类的非静态成员函数，没有非对象形参。它的返回类型就是 `operator` 后面的类型，不能再在前面写返回类型。

```cpp title="conv-fct-decl.cpp" error
struct X {
    operator int();                   // OK
    explicit operator double() const; // OK
    operator const char*() const;     // OK: 类型里可以有 *
    int operator long();              // error: 前面不能写返回类型
    operator auto() -> short;         // error: 不能有尾随返回类型
    static operator char();           // error: 必须是非静态成员
    operator bool(int);               // error: 不能有形参
};
```

措辞是没有非对象形参，所以 C++23 起转换函数可以有显式对象形参，如 `operator int(this const X& self)`。

¶3 例 1 说明，`int(a)`、`(int)a`、`i = a` 这三种写法都调用 `X::operator int()`。

### explicit 转换函数（¶4）

¶4 转换函数可以是 explicit 的（C++11 起），这时它只在直接初始化中才被当作用户定义转换。非 explicit 的转换函数则可以出现在任何需要隐式转换的地方，不限于赋值和初始化。

```cpp title="explicit-conv-fct.cpp" error
class Y { };
struct Z {
    explicit operator Y() const;
};

void h(Z z) {
    Y y1(z);          // OK: 直接初始化
    Y y2 = z;         // error: 复制初始化中它不是候选
    Y y3 = (Y)z;      // OK: 强制转换
}
```

#### explicit operator bool

explicit 转换函数最重要的用途是 `explicit operator bool`。`if`、`while`、`for` 的条件，`!`、`&&`、`||` 的操作数，`?:` 的第一个操作数等位置，会把表达式[[g:contextually-converted-to-bool|按语境转换为 bool]]：如果 `bool t(e);` 良构，就用它的结果（[[conv.general#4]]）。`bool t(e);` 是直接初始化，所以 explicit 转换函数在这些位置可以使用：

```cpp title="explicit-bool.cpp" error
struct S {
    explicit operator bool() const { return true; }
};

void use(S s) {
    if (s) { }                  // OK: 按语境转换
    bool b1 = s ? true : false; // OK
    bool b2 = !s;               // OK
    bool b3(s);                 // OK: 直接初始化
    bool b4 = s;                // error: 复制初始化
    int  i  = s + 1;            // error: 不会转成 bool 再参与运算
}
```

如果写的是非 explicit 的 `operator bool()`，`s + 1`、`s1 == s2`（两边都转成 `bool` 再比较）、`int x = s;` 都能编译。标准例 2 的 `g` 展示了同样的现象：`X` 只有非 explicit 的 `operator int()`，`(a) ? 1+a : 0`、`(a&&b) ? a+b : i` 和 `if (a)` 里处处在调用它。C++11 之前，智能指针为了避免这些意外，要借助指向成员的指针来模拟一个安全的 bool；有了 `explicit operator bool`，就不再需要了。

### 哪些转换不会调用转换函数（¶3）

¶3 注 1 指出，把对象转换为它自己的类型（或其引用）、它的基类（或其引用）或 `void` 时，永远不会调用转换函数。这些转换各有别的机制：复制构造、派生类到基类的转换、弃值。这样的转换函数仍然可以声明；如果基类里有同名的虚转换函数，它可能经由虚调用被调用到。

### 目标类型的写法（¶5）

¶5 `operator` 后面的类型不能是函数类型或数组类型。要返回数组的引用或函数指针，先定义别名：`using Arr = int[3]; operator Arr&();`。

¶5 还规定，`operator` 后面的类型取尽可能长的记号序列。注 2 说明这消除了声明符 `*` 和乘号之间的歧义：

```cpp
&ac.operator int*i;   // 语法错误：解析为 &(ac.operator int*) i
                      // 而不是 &(ac.operator int) * i
```

属性也一样：`operator int [[noreturn]] ();` 中的 `[[noreturn]]` 被当成类型 `int` 的一部分，而 `noreturn` 不能用于类型，所以是错误。

### 隐藏与二义（¶6）

¶6 注 3 指出，派生类的转换函数只隐藏基类中转换到同一类型的转换函数。转换函数的名字就是 `operator T`，目标类型不同，名字也就不同。返回类型依赖于模板形参的转换函数模板只隐藏基类中与之对应的模板；其他情况下它和非模板函数一样参与隐藏。最后由重载决议（[[over.match.best]]）选出最好的转换函数。标准例 5：

```cpp title="conv-ambiguous.cpp" error
struct X { operator int(); };
struct Y : X { operator char(); };

void f(Y& a) {
    if (a) { }    // error: X::operator int 与 Y::operator char 二义
}
```

`Y::operator char` 没有隐藏 `X::operator int`，两者都可行。转换到 `bool` 时，`int→bool` 和 `char→bool` 都是布尔转换，排名相同，所以有二义。

### 虚转换函数与转换函数模板（¶7–¶8）

¶7 转换函数可以是虚函数：

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
    int v = b;           // 虚调用 Derived::operator int
    return v - 2;
}
```

转换函数也可以是模板。它的模板实参从转换的目标类型推导（[[temp.deduct.conv]]），常用来写一个能转换为任意类型的代理：

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

¶8 转换函数模板不能用推导的返回类型（[[dcl.spec.auto]]）。它的模板实参要从目标类型推导，而 `auto` 又要求从函数体推导返回类型，两个方向不能同时进行。非模板的 `operator auto()` 是允许的，`struct S { operator auto() { return 1; } };` 定义了一个到 `int` 的转换函数。

```cpp title="conv-template-auto.cpp" error
struct S {
    template<class T>
    operator auto() const { return 1.2; }   // error
};
```

## 实现视角

!!! impl
    在 Itanium ABI 中，转换函数修饰名里的名字部分是 `cv` 加目标类型，例如 `X::operator int()` 是 `_ZN1XcviEv`。转换到不同类型的转换函数是不同的符号，正对应 ¶6 中只隐藏同一目标类型的规则。

    转换需要两个用户定义转换时，Clang 只报告 `no viable conversion from 'Y' to 'int'`，不会说明原因。遇到这种错误，可以检查是否需要把其中一步写成显式的 `X(a)`。

## 历史与演进

!!! history
    - C++98 已有转换构造函数、explicit 构造函数、转换函数和转换函数模板，以及至多一个用户定义转换的限制。
    - C++11 引入 explicit 转换函数和按语境转换为 bool；列表初始化让多参数的非 explicit 构造函数也成为转换构造函数。
    - C++14 起非模板转换函数可以用 `auto` 返回类型。
    - C++20 引入 `explicit(bool)`。
    - C++23 起转换函数可以有显式对象形参（[[P0847R7]]）。

## 常见误解

!!! pitfall "`f(\"hi\")` 会调用 `f(std::string)`"
    对 `void f(std::string); void f(bool);`，`f("hi")` 选中的是 `f(bool)`。指针到 `bool` 是标准转换，优于 `const char*` 到 `std::string` 的用户定义转换。

!!! pitfall "explicit 能阻止所有隐式使用"
    `explicit operator bool` 在 `if`、`!`、`&&` 中仍会被调用。explicit 构造函数在复制列表初始化中仍参与重载决议，被选中时报错。

!!! pitfall "两个方向的转换可以同时提供"
    如果 `A` 有 `A(const B&)`，`B` 又有 `operator A() const`，`A a = b;` 是二义的：两个候选的实参都是绑定到 `const B&`。去掉 `const`，`b` 是非 const 左值时会选中转换函数，因为绑定到 `B&` 优于绑定到 `const B&`，结果取决于实参的 cv 限定，同样不可取。同一对类型之间只在一个方向上定义转换。

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

不合法。`b` 到 `A` 需要 `B::operator int` 和 `A::A(int)` 两个用户定义转换，违反 [class.conv.general] ¶4。改成 `f(A(b))` 就可以：直接初始化 `A(b)` 中，`b` 到构造函数形参 `int` 只用一个用户定义转换。
</details>

!!! question "思考题 2"
    `struct X { operator X&(); operator void(); };` 合法吗？这两个函数什么时候会被调用？

<details markdown="1">
<summary>答案</summary>

声明合法，Clang 会警告它们永远不会被使用。按 ¶3 注 1，转换到自身类型的引用或 `void` 时从不调用转换函数：`X& r = x;` 直接绑定，`(void)x` 是弃值。它们只能被显式调用，如 `x.operator X&()`，或者在覆盖了基类的虚转换函数时经由虚调用到达。
</details>
