---
title: 成员模板
summary: 类或类模板中声明的模板；类外定义要写两层等价的 template-head；局部类不能有成员模板；析构函数不能是模板；同名同类型的非模板成员优先；成员函数模板不能是虚函数，其特化也不覆盖虚函数；转换函数模板的特化如何命名
status: done
covers: temp.mem
since: c++98
related: temp.class, temp.over.link, class.conv.fct, temp.deduct.conv, class.virtual, class.copy.ctor, expr.prim.lambda, temp.expl.spec
tags: 模板, 成员模板, 虚函数, 转换函数
updated: 2026-10-17
---

**成员模板**（member template）是在类或类模板**内部**声明的模板：成员函数模板、成员类模板、静态数据成员模板（变量模板）、成员别名模板。它们是"两层参数化"的典型来源——`std::vector<T>` 的范围构造函数 `template<class InputIt> vector(InputIt, InputIt)` 既依赖外层的 `T`，又有自己的 `InputIt`。

本节规定：类外定义的写法（¶1）、成员模板的几条禁令（¶2–3）、成员模板与虚函数的关系（¶4）、转换函数模板的命名（¶5）。

---

## 定义与类外定义（¶1）

¶1 可以在类或类模板中声明模板，这样的模板叫**成员模板**。成员模板可以在类定义内或外定义。**类模板**的成员模板在类外定义时，要写**两个** *template-head*：先是与类模板等价的，然后是与成员模板等价的（等价的含义见 [[temp.over.link#6]]）：

```cpp run ok
template<class T> struct string {
    template<class T2> int compare(const T2&);
    template<class T2> string(const string<T2>&) { }   // 类内定义的构造函数模板
    string() = default;
};

template<class T> template<class T2>
int string<T>::compare(const T2&) { return 0; }        // 外层 template-head 在前，内层在后

int main() {
    string<char> s;
    string<wchar_t> w(s);                              // 用构造函数模板转换
    return s.compare(w);
}
```

两层 *template-head* 的顺序与嵌套顺序一致，**不能合并**为 `template<class T, class T2>`：后者是"一个有两个形参的模板"，而我们要定义的是"一个单形参模板（类模板）的成员，这个成员本身又是单形参模板"。

约束同样要等价：

```cpp error
template<typename T> concept C1 = true;
template<typename T> concept C2 = sizeof(T) <= 4;

template<C1 T> struct S {
    template<C2 U> void f(U);
    template<C2 U> void g(U);
};

template<C1 T> template<C2 U>
void S<T>::f(U) { }             // OK
template<C1 T> template<typename U>
void S<T>::g(U) { }             // error: S<T> 中没有无约束的 g
```

非模板类的成员模板只需要一层：

```cpp run ok
struct Logger {
    template<class T> void log(const T&);
};
template<class T> void Logger::log(const T&) { }
int main() { Logger{}.log(42); }
```

## 几条禁令与规则（¶2）

¶2 包含四句话，各自独立：

### 局部类不能有成员模板

¶2 第一句：**非闭包类型**的局部类（[[class.local]]）不能有成员模板。

```cpp error
void f() {
    struct Local {
        template<class T> void g(T) { }   // error: 局部类中的成员模板
    };
}
```

为什么？历史原因是实现上的：成员模板可能在包含它的函数之外被实例化（实例化点在命名空间作用域，[[temp.point]]），而局部类的成员需要访问外层函数的局部上下文，两者结合会给实现带来大量复杂性。同理，局部类中也不能声明友元模板（[[temp.friend#6]]）。

"非闭包类型"这个限定是为**泛型 lambda** 开的口子：泛型 lambda 的闭包类型是局部类，它的函数调用运算符就是一个成员函数模板（[[expr.prim.lambda.closure]]），这是允许的：

```cpp run ok
int main() {
    auto id = [](auto x) { return x; };    // 闭包类型是局部类，operator() 是成员模板：OK
    return id(0);
}
```

### 访问控制适用

¶2 第二句：访问控制规则适用于成员模板的名字——`private` 的成员模板在类外不可访问，和普通成员一样（[[class.access]]）。

### 析构函数不能是模板

¶2 第三句：**析构函数不能是成员模板**。一个类只有一个析构函数（C++20 起可以有多个带不同约束的"预期析构函数"，但它们都不是模板，[[class.dtor]]），而析构函数没有参数，模板实参无从推导，也没有语法可以显式指定。

```cpp error
struct X {
    template<class T> ~X();       // error: 析构函数不能是模板
};
```

构造函数**可以**是模板，但有两个特性要牢记：

- 构造函数模板的模板实参必须全部可推导（或有默认值）：没有语法给构造函数显式指定模板实参（`X<int>::X<long>(...)` 中的 `<long>` 会被解析为类的实参，[[temp.arg.explicit]]）。
- 构造函数模板**永远不是**复制/移动构造函数（[[class.copy.ctor]]）：即使它实例化出 `X(const X&)` 签名，类仍会隐式声明复制构造函数。但在重载决议中，模板构造函数可能**比**复制构造函数**更好**：

```cpp run ok
#include <cstdio>
struct S {
    S() = default;
    S(const S&) { std::puts("copy ctor"); }
    template<class T> S(T&&) { std::puts("template ctor"); }   // 万能引用构造函数
};
int main() {
    S a;
    S b = a;          // 输出 "template ctor"：T = S&，形参 S&，比 const S& 更好的匹配
    const S c;
    S d = c;          // 输出 "copy ctor"：T = const S&，形参与复制构造函数相同，非模板优先
    (void)b; (void)d;
}
```

这就是"完美转发构造函数劫持复制构造"问题，通常用约束（`requires (!std::is_same_v<std::remove_cvref_t<T>, S>)`）解决。

### 非模板成员与成员模板同名同类型（¶2 末句）

¶2 末句：类中可以**同时**声明一个非模板成员函数和一个同名的成员函数模板，后者能生成与前者**同类型**的特化。两者并存时，对该名字和类型的使用指向**非模板成员**——除非提供了显式模板实参列表。

```cpp run ok
#include <cstdio>
template<class T> struct A {
    void f(int) { std::puts("non-template"); }
    template<class T2> void f(T2) { std::puts("template"); }
};

int main() {
    A<char> ac;
    ac.f(1);          // non-template：精确匹配平局时非模板优先（[over.match.best]）
    ac.f('c');        // template：T2 = char，精确匹配优于 char → int 的提升
    ac.f<>(1);        // template：显式模板实参列表（即使为空）排除了非模板
}
```

这条规则与 [[over.match.best]] 中"非模板优于模板特化"的平局规则一致，但它说的不只是调用：在**显式特化**等需要"指名某个函数"的地方，同样按此区分：

```cpp run ok
template<class T> struct A {
    void f(int);
    template<class T2> void f(T2);
};
template<> void A<int>::f(int) { }                  // 显式特化 A<int> 的非模板成员 f(int)
template<> template<> void A<int>::f<>(int) { }     // 显式特化成员模板 f<T2> 的 f<int>
int main() { A<int> a; a.f(1); a.f<>(1); }
```

两行的差别只在 `f` 后是否带 `<>`：带了就指名模板特化（并且需要再写一层 `template<>`，因为成员模板也被特化了）。

## 成员函数模板不能是虚函数（¶3）

¶3 **成员函数模板不能声明为 `virtual`**。

```cpp error
template<class T> struct AA {
    template<class C> virtual void g(C);   // error: 虚成员函数模板
    virtual void f();                      // OK: 类模板的普通虚成员函数
};
```

为什么？虚函数的典型实现是**虚表**：每个类的虚表在编译该类时就要确定大小和布局，每个虚函数占一个固定槽位。而成员函数模板的特化集合是**开放的**：任何 TU 都可能用新的模板实参实例化 `g<C>`，编译器在编译类定义时无法知道需要多少个槽位，也无法在分别编译的模型下汇总所有 TU 的实例化。标准索性禁止。

注意区分：**类模板的普通成员函数可以是虚函数**（`AA<T>::f`），因为对每个特化 `AA<int>`，它的虚函数集合是固定的。

需要"虚 + 泛型"时的常见解法：类型擦除（`std::function`、`std::any`）、访问者模式（把类型集合封闭起来）、或者 CRTP 静态多态。

## 成员模板的特化不覆盖虚函数（¶4）

¶4 成员函数模板的特化**不会覆盖**基类的虚函数：

```cpp run ok
#include <cstdio>
struct B {
    virtual void f(int) { std::puts("B::f"); }
    virtual ~B() = default;
};
struct D : B {
    template<class T> void f(T) { std::puts("D::f<T>"); }   // 不覆盖 B::f(int)
};
struct E : B {
    template<class T> void f(T) { std::puts("E::f<T>"); }
    void f(int i) override { f<>(i); }                       // 覆盖函数，转发到模板特化
};
int main() {
    D d; E e;
    B& rd = d; B& re = e;
    rd.f(1);          // B::f —— D 没有覆盖
    re.f(1);          // E::f<T> —— E::f(int) 覆盖并转发
}
```

这是 ¶3 的必然推论：如果模板特化能覆盖虚函数，就等于让模板特化进入虚表。注意 `D::f` 仍然会**隐藏**（hide）`B::f`——名字查找在 `D` 中找到 `f` 就停止（[[class.member.lookup]]），所以 `d.f(1)` 调用的是 `D::f<int>`；只是通过 `B&` 虚调用时不会派发到它。

## 转换函数模板的命名（¶5）

¶5 是一个注：**转换函数模板**的特化与转换到同一类型的**非模板转换函数**用同样的方式命名（[[class.conv.fct]]）：`operator char*` 既可以指非模板的转换函数，也可以指 `template<class T> operator T*()` 的 `T = char` 特化。

```cpp run ok
struct A {
    template<class T> operator T*();
};
template<class T> A::operator T*() { return nullptr; }
template<> A::operator char*() { return nullptr; }      // 显式特化：T = char
template A::operator void*();                           // 显式实例化：T = void

int main() {
    A a;
    int* ip = a.operator int*();       // 显式调用模板转换函数，T 从 int* 推导
    double* dp = a;                    // 隐式转换：T 从目标类型推导（[temp.deduct.conv]）
    return ip == nullptr && dp == nullptr ? 0 : 1;
}
```

转换函数模板的模板实参**只能推导**（从转换的目标类型，[[temp.deduct.conv]]），没有显式指定的语法：`a.operator int*<int>()` 之类的写法不存在——`operator T*` 后面的 `<` 不会被解析为模板实参列表（[[temp.names]] 中 `<` 的解释规则明确排除了 *conversion-function-id*）。

!!! std
    An expression designating a particular specialization of a conversion function template can only be formed with a *splice-expression*.

注的最后一句（{{c++26}}）：要构成一个**指称转换函数模板某个特化**的表达式，只能用 *splice-expression*（静态反射，[[expr.prim.splice]]）——例如对一个反射到该特化的值做 `[: r :]`。普通语法中没有对应的 *template-id* 形式。截至写作时，本机 Clang 23 尚未实现静态反射，无法验证这类代码。

!!! lawyer "转换函数模板与非模板转换函数共存"
    与 ¶2 末句类似：类中可以同时有 `operator int*()` 和 `template<class T> operator T*()`。对目标类型 `int*` 的转换，二者的转换序列相同，非模板优先（[[over.match.best]]）。偏序比较两个转换函数模板时，比较的是**返回类型**（[[temp.deduct.partial#3.2]]），而且若两模板返回类型不同则约束不参与平局（[[temp.func.order#8.3]]）。

---

## 实现视角

!!! impl "实现视角"
    - **mangling**：成员模板的特化在 Itanium ABI 中编码为"嵌套名 + 模板实参"，外层类模板的实参与成员模板自己的实参分别编码，例如 `string<char>::compare<string<wchar_t>>` 的两层实参都会出现在符号里。
    - **虚表**：类模板 `AA<T>` 的每个特化都有自己的虚表；禁止虚成员模板保证了虚表在类定义处就可以完整生成。
    - **泛型 lambda**：闭包类型的 `operator()` 模板在每个用到的实参类型上实例化，生成多个符号——这是局部类中唯一允许出现的成员模板。

## 陷阱

!!! pitfall "常见误解"
    - "模板构造函数可以充当复制构造函数"——不能，类仍会隐式声明复制构造函数；但模板构造函数可能在重载决议中**胜过**复制构造函数（对非 const 左值）。
    - "派生类的 `template<class T> void f(T)` 覆盖了基类的 `virtual void f(int)`"——不会覆盖，只会隐藏。
    - "可以写 `template<class T> virtual void visit(T)` 实现泛型访问者"——不行，虚函数与模板不能结合。
    - "`ac.f<>(1)` 与 `ac.f(1)` 等价"——前者只考虑模板，后者优先非模板。

## 思考题

!!! question "思考题 1"
    下面的调用各选择哪个函数？

    ```cpp
    struct X {
        void g(long);
        template<class T> void g(T);
    };
    X x;
    x.g(1);      // (a)
    x.g(1L);     // (b)
    x.g<long>(1);// (c)
    ```

<details markdown="1">
<summary>答案</summary>

(a) 模板 `g<int>`：模板推导出 `T = int`，精确匹配；非模板 `g(long)` 需要整型转换（int → long，是转换不是提升），精确匹配更好，模板胜出。"非模板优先"只在两者转换序列不分高下时才起作用。

(b) 非模板 `g(long)`：两者都是精确匹配（模板推导出 `T = long`），平局时非模板优先。

(c) 模板 `g<long>`：显式模板实参列表排除了非模板。
</details>

!!! question "思考题 2"
    类模板 `template<class T> struct Base { virtual void f(T); };` 的成员 `f` 是虚函数，这与 ¶3 的禁令矛盾吗？

<details markdown="1">
<summary>答案</summary>

不矛盾。¶3 禁止的是**成员函数模板**（自身带 *template-head* 的成员）为虚函数。`Base<T>::f` 不是函数模板，而是"类模板的成员函数"：对每个特化 `Base<int>`，它是一个普通的成员函数 `void f(int)`，虚函数集合在该特化的类定义中固定。虚表问题只在"同一个类中可能有无穷多个虚函数"时才出现。
</details>

!!! summary "小结"
    - 成员模板 = 类内声明的模板；类模板的成员模板在类外定义要写两层等价的 *template-head*（外层在前）。
    - 禁令：非闭包局部类不能有成员模板；析构函数不能是模板；成员函数模板不能是虚函数。
    - 成员函数模板的特化不覆盖虚函数（但会隐藏同名基类成员）。
    - 同名同类型的非模板成员优先；显式模板实参列表（哪怕是 `<>`）只选模板。
    - 构造函数模板永远不是复制/移动构造函数；转换函数模板的实参只能从目标类型推导，指称其特化的表达式只能用 splice（{{c++26}}）。
