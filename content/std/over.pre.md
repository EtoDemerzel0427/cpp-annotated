---
title: 重载：序言
summary: 什么是重载，什么是重载决议；两个同名函数声明什么时候能共存，什么时候是同一个函数的重复声明。
status: done
papers: P1787R6, P0847R7
related: over.match, basic.scope.scope, basic.link, dcl.fct, over
tags: 重载决议, 声明
updated: 2026-10-19
---

!!! tldr
    - 同一作用域里两个以上同名的函数或函数模板称为重载；派生类里的同名函数会隐藏基类的，而不是与之重载。
    - 两个同名函数声明能否共存，看它们是否对应：形参类型列表（调整后）、尾随约束、对象形参都相同的两个声明对应，声明的是同一个函数。
    - 对应的声明类型必须完全相同，所以只差返回类型、只差 `noexcept` 的两个声明是错误；只差顶层 `const` 或默认实参的声明是同一个函数的重复声明。
    - 函数模板的返回类型参与判断，所以两个只差返回类型的模板可以共存。
    - 同名同参的成员函数不能一个有引用限定符（`&`/`&&`）、一个没有，也不能一个静态、一个非静态。

## 重载与隐藏（¶1）

```cpp run ok
struct B {
  int f(int) { return 1; }
};
struct D : B {
  int f(double) { return 2; }   // 隐藏 B::f
};
struct E : B {
  using B::f;                   // 把 B::f 引入 E 的作用域
  int f(double) { return 2; }
};

int main() {
  D d;
  E e;
  int a = d.f(1);   // 2：查找在 D 里找到 f 就停下，B::f(int) 不是候选
  int b = e.f(1);   // 1：B::f(int) 和 E::f(double) 都是候选，前者是精确匹配
  return a * 10 + b == 21 ? 0 : 1;
}
```

¶1 标准用一条注说明：同一作用域里的两个或多个同名实体，如果都是函数或函数模板，通常就称为**重载**（overload）。

两个条件都要满足。`D::f` 和 `B::f` 不在同一作用域，所以不是重载：类成员查找（[[class.member.lookup]]）在 `D` 里找到 `f` 就不再查基类，`B::f(int)` 根本进不了候选集。要让基类版本参与竞争，必须用 *using-declaration*（[[namespace.udecl]]）把它引入派生类，像 `E` 那样。

另外，同名同作用域的一个变量和一个函数也不是重载，而是冲突，程序非良构（[[basic.scope.scope#6]]）。

## 重载决议（¶2）

¶2 调用中指名一个函数时，调用的是哪个声明、调用是否合法，都通过比较实参类型与重载集中各声明的形参类型来决定。这个选择过程叫**重载决议**（[[g:overload-resolution|overload resolution]]），由 [[over.match]] 规定。

注 2 说明**重载集**由指名函数或函数模板的 *id-expression* 形成，{{c++26}} 起也可以由反射的 *splice-expression*（`[:r:]`）形成。

决定的是哪一个声明，而不只是哪一个函数。默认实参附着在声明上，同一个函数在不同作用域里可以有不同的默认实参，所以需要知道用的是哪个声明（[[over.match.viable#2]]）。

## 哪些同名声明不能共存

<div class="compare" markdown="1">

```cpp error
int    f(int);
double f(int);  // error: 只差返回类型
```

```cpp ok
template<class T> int    g(T);
template<class T> double g(T);  // OK
```

</div>

左边两个声明冲突，右边两个模板却可以共存。规则散在三个地方：[[basic.scope.scope#3]] 和 [[basic.scope.scope#4]] 定义两个声明何时**对应**，[[basic.link#8]] 说对应的声明声明同一个实体，[[basic.link#11]] 要求同一实体的各个声明类型相同。合起来是：

- 不对应的两个同名函数声明，声明不同的函数，构成重载；
- 对应的两个声明声明同一个函数，类型必须相同，否则非良构。

### 对应的定义

非静态成员函数有一个**对象形参**，即调用时 `*this` 绑定的那个形参。传统写法里它是隐式的（类型是 `X&`、`const X&` 等），C++23 起也可以用 `this` 显式写出来。**非对象形参类型列表**就是除去对象形参之外的形参类型列表。

按 [[basic.scope.scope#4]]，两个非模板函数声明**对应**，当且仅当：

- 非对象形参类型列表相同；
- 尾随 *requires-clause*（如果有）等价；
- 如果两者都是非静态成员函数，对象形参也对应。

对象形参对应的规则（[[basic.scope.scope#3]]）专为**引用限定符**（*ref-qualifier*，成员函数声明末尾的 `&` 或 `&&`）设计：如果恰好有一个是不带引用限定符的隐式对象成员函数，就去掉引用后比较两者的对象形参类型；否则直接比较对象形参类型。

两个函数模板对应，还要求模板头等价、返回类型等价。返回类型这一条是模板与普通函数的区别。

### 按此判断的几种情形

**只差返回类型**：返回类型不在对应的条件里，两个声明对应，类型却不同，非良构。这样设计是因为 `f(1)` 这个调用本身不带期望的返回类型，重载决议无从选择。

**形参类型调整后相同**：[[dcl.fct]] 形成函数类型时，数组形参调整为指针，函数形参调整为函数指针，形参的顶层 cv 限定被丢掉。调整后相同的就是同一个形参类型列表。

```cpp run ok
typedef int Int;
void f(int);
void f(Int);          // 重复声明同一个 f：别名不引入新类型
void g(int*);
void g(int[]);        // 重复声明：int[] 调整为 int*
void h(int());        // 形参是函数类型，调整为 int(*)()
void h(int (*)());    // 重复声明
void k(int);
void k(const int);    // 重复声明：顶层 const 不属于函数类型

void k(const int x) { (void)x; }   // k(int) 的定义；x 在函数体内是 const
int main() { k(1); }
```

非顶层的 cv 限定会区分重载：`m(int&)` 与 `m(const int&)`、`m(int*)` 与 `m(const int*)` 都是不同的函数。`char`、`signed char`、`unsigned char` 是三个不同的类型，枚举类型和它的底层类型也是不同的类型，都可以分别重载。

**只差默认实参**：默认实参不属于函数类型。`void f(int);` 与 `void f(int, int = 0);` 形参个数不同，不对应，可以共存，但调用 `f(1)` 时两个都是精确匹配，歧义。

**只差 `noexcept`**：`noexcept` 自 C++17 起是函数类型的一部分，但不在对应的条件里。于是 `void f() noexcept;` 与 `void f();` 对应，声明同一个函数，类型却不同，按 [[basic.link#11]] 非良构。

**一个静态、一个非静态**：静态成员函数没有对象形参，而 [[basic.scope.scope#4.4]] 只在两者都是非静态成员时才比较对象形参。所以形参相同的静态与非静态成员函数对应，二者冲突。

```cpp error
struct X {
  static void f();
  void f() const;     // error: 与 static f() 对应
};
```

禁止它是因为 `x.f()` 对两者都能调用（静态成员函数的隐式对象形参能匹配任何对象，[[over.match.funcs#4]]），而且对象实参对静态函数的匹配既不更好也不更差，这样的重载几乎总是歧义。

**引用限定符**：有引用限定符和没有引用限定符的同名同参成员函数不能共存。

```cpp error
struct X {
  void g();
  void g() const;      // OK: 去掉引用后 X 与 const X 不同
  void g() &;          // error: 与 g() 对应
  void h() &;
  void h() &&;         // OK: 两者都有限定符，X& 与 X&& 不同
  void k() const;
  void k() const &&;   // error: 与 k() const 对应
};
```

`g()` 不带引用限定符，对左值和右值都能调用，和 `g() &` 放在一起只会让左值调用产生歧义。C++11 引入引用限定符时就规定了同名同参的成员函数要么都带、要么都不带，现在的对应规则表达的是同一件事。

**显式对象形参**{{c++23}}：[[P0847R7]] 引入的 `this` 形参与隐式对象形参用同一套规则比较。

```cpp error
struct X {
  void k();
  void k(this X&);     // error: 对象形参都是 X&
  void j(this const X&);
  void j() const &;    // error: 对象形参都是 const X&
  void h(this X&, int);
  void h(int) &&;      // OK: X& 与 X&& 不同
  void m(this X);
  void m() const;      // OK: 去引用后 X 与 const X 不同
};
```

### 模板：返回类型参与区分

本节开头右边的两个 `g` 模板返回类型不同，按 [[basic.scope.scope#3]] 不对应，所以合法。调用 `g(1)` 会歧义，但可以按目标类型取出其中一个：

```cpp ok
template<class T> int    g(T);
template<class T> double g(T);
int (*p)(int) = &g<int>;       // OK: 选中第一个（[over.over]）
```

模板的返回类型可以依赖模板形参，并参与替换失败（如 `auto f(T t) -> decltype(t.foo())`），所以它必须是模板身份的一部分。Itanium C++ ABI 也因此把返回类型编码进函数模板特化的修饰名，而普通函数的修饰名不含返回类型。

### 约束也区分声明

尾随 *requires-clause* 不等价的两个声明不对应，可以共存，由 [[over.match.best#2.6]] 让约束更强的一方胜出：

```cpp run ok
#include <concepts>
template<class T>
struct Box {
  int get() const requires std::integral<T> { return 1; }
  int get() const { return 2; }   // 不对应：一个有约束、一个没有
};
int main() {
  return Box<int>{}.get() == 1 && Box<double>{}.get() == 2 ? 0 : 1;
}
```

### 来自不同作用域的对应声明

对应的声明只在同一作用域里才冲突。经由 *using-directive* 或 ADL，重载决议可能同时看到来自不同作用域的对应声明，声明本身合法，调用却往往歧义（[[basic.scope.scope#6]] 注 4）：

```cpp error
namespace A { int f(int); }
namespace B { int f(int); }
using namespace A;
using namespace B;
void use() {
  f(1);   // error: A::f 与 B::f 形参完全相同，歧义
}
```

!!! impl "名字修饰"
    Itanium C++ ABI 下，`int f(int)` 和 `double f(int)` 都修饰为 `_Z1fi`，返回类型不进符号。所以两个翻译单元对同一函数的返回类型不一致时，链接器照样把它们连在一起，这是一个不要求诊断的 ODR 违规。`const` 和引用限定符会进入成员函数的修饰名（`K`、`R`、`O`）。

!!! history
    C++20 及以前，不能重载的声明逐条列在 `[over.load]` 里：只差返回类型、静态与非静态同参、只差顶层 cv、数组与指针形参等价、只差默认实参等。C++23 的 [[P1787R6]] 删除了这一节，改用 [[basic.scope.scope]] 的对应概念统一表达，结论基本不变。

## 常见误解

!!! pitfall "`const` 形参能构成重载"
    `void f(int)` 与 `void f(const int)` 是同一个函数。在声明里写 `int`、在定义里写 `const int` 是合法的常见写法。

!!! pitfall "派生类的同名函数会和基类的重载"
    它会隐藏基类所有同名函数，不论形参如何。要合并重载集，写 `using Base::f;`。

!!! pitfall "默认实参能消除歧义"
    默认实参只让少传实参的调用变得可行，不影响排序。`f(int)` 和 `f(int, int = 0)` 对 `f(1)` 总是歧义。

## 思考题

!!! question "1. 下面哪些声明可以出现在同一个类里？"
    ```cpp nocheck
    struct S {
      void a() &;        // #1
      void a() const &;  // #2
      void a() &&;       // #3
      void a();          // #4
    };
    ```

<details markdown="1">
<summary>答案</summary>

\#1、#2、#3 都带引用限定符，直接比较对象形参类型：`S&`、`const S&`、`S&&` 互不相同，可以共存。#4 不带引用限定符，与 #1 比较时去掉引用，都是 `S`，二者对应，程序非良构（[[basic.scope.scope#3]]）。
</details>

!!! question "2. `void f(int[3]);` 与 `void f(int(&)[3]);` 能共存吗？`int a[3]; f(a);` 选哪个？"

<details markdown="1">
<summary>答案</summary>

能共存。前者调整为 `void f(int*)`，后者的形参是数组的引用，类型不同。调用 `f(a)` 时，前者需要数组到指针的转换，后者是直接绑定，两者都属于精确匹配；比较时不考虑数组到指针这类左值变换（[[over.ics.rank#3.2.1]]），所以无法区分，调用歧义。Clang 也报告 `call to 'f' is ambiguous`。
</details>
