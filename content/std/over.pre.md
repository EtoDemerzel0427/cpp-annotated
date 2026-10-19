---
title: 重载：序言
summary: 什么叫重载，重载决议在何时介入；哪些同名声明不能共存，当前草案用 [basic.scope.scope] 的对应声明统一表达这些规则。
status: draft
papers: P1787R6, P0847R7
related: over.match, basic.scope.scope, basic.link, dcl.fct
tags: 重载决议, 声明
updated: 2026-10-17
---

[[over.pre]] 本身只有两段，而且第一段还只是注释。它给重载和重载决议下定义，并把读者指向 [[over.match]]。

但读这一节时最常问到的问题，即哪些同名函数能共存、哪些不能，在当前草案里已经不在这里了。C++20 及以前，这些规则在 `[over.load]`（Overloadable declarations）里逐条列出；C++23 起经 [[P1787R6]]（*Declarations and where to find them*）重构，统一并入 [[basic.scope.scope]] 的**对应**（correspond）概念和 [[basic.link]] 中关于同一实体的规则。本页把两部分都讲清楚。

## 什么是重载（¶1）

¶1 这是一条注释：同一作用域中两个或多个同名实体，若都是函数或函数模板，通常就称为重载（overload）。

注意两个限定：

- 同一作用域。不同作用域的同名函数不构成重载，而是**隐藏**（hiding）：内层的名字挡住外层的名字，名字查找根本不会把外层的函数交给重载决议。
- 必须都是函数或函数模板。一个变量和一个函数同名、同作用域，按 [[basic.scope.scope#6]] 就是冲突，不是重载。

```cpp run ok
struct B {
  int f(int) { return 1; }
};
struct D : B {
  int f(double) { return 2; }   // 隐藏 B::f，而不是与之重载
};
struct E : B {
  using B::f;                   // 把 B::f 引入 E 的作用域，现在二者一起参与重载决议
  int f(double) { return 2; }
};

int main() {
  D d;
  E e;
  int a = d.f(1);   // 2：类成员查找在 D 中找到 f 就停下，B::f(int) 根本不是候选
  int b = e.f(1);   // 1：B::f(int) 与 E::f(double) 同时是候选，int→int 是精确匹配
  return a * 10 + b == 21 ? 0 : 1;
}
```

这是查找先于决议的直接后果：[[class.member.lookup]] 在 `D` 的作用域里找到了 `f`，就不会继续去基类找。想让基类版本参与竞争，必须用 *using-declaration* 显式引入（[[namespace.udecl]]）。

## 重载决议的定义（¶2）

¶2 调用中指名了一个函数时，引用的是哪一个函数声明、调用是否合法，都通过比较使用点上实参的类型与重载集中各声明的形参类型来决定。这一选择过程叫重载决议，定义在 [[over.match]]。

!!! std
    "This function selection process is called *overload resolution* and is defined in [over.match]."

    这一函数选择过程称为重载决议。

这句话有两个要点：

1. 决定的是哪一个声明，而不只是哪一个函数。这对默认实参很重要：默认实参附着在声明上，[[over.match.viable#2]] 要求能找到唯一的作用域来提供它们。
2. 同时决定调用是否合法。如果没有可行函数，或者有多个同样好的函数（歧义），调用就非良构。

注 2 指出重载集由命名函数/函数模板的 *id-expression* 形成，{{c++26}} 起也可以由指代同类实体的 *splice-expression*（反射里的 `[:r:]`）形成。在 C++23 及以前，只有 *id-expression*（以及成员访问中的名字）能形成重载集。

```cpp run ok
double abs(double x) { return x < 0 ? -x : x; }
int    abs(int x)    { return x < 0 ? -x : x; }

int main() {
  auto a = abs(1);     // 调用 abs(int)：int→int 精确匹配，int→double 是转换
  auto b = abs(1.0);   // 调用 abs(double)
  static_assert(sizeof(a) == sizeof(int) && sizeof(b) == sizeof(double));
}
```

## 哪些声明不能构成重载

这是本页的主体。规则分散在三处，组合起来才是完整答案：

| 问题 | 规则所在 |
|---|---|
| 两个同名函数声明什么时候对应？ | [[basic.scope.scope#3]]、[[basic.scope.scope#4]] |
| 对应的声明在同一作用域出现会怎样？ | [[basic.scope.scope#6]]（潜在冲突）、[[basic.link#8]]（声明同一实体） |
| 声明同一实体时，类型必须相同 | [[basic.link#11]] |
| 形参类型怎样调整（数组→指针、顶层 cv…） | [[dcl.fct]] |

### 思路：先判断是不是同一个函数

当前草案不再列一张不可重载的声明清单，而是换了一个角度：同一作用域里出现两个同名函数声明时，先判断它们是否对应。

- 不对应：它们声明不同的函数，构成重载。
- 对应：按 [[basic.link#8]]，（在满足链接条件时）它们声明同一个实体，于是 [[basic.link#11]] 要求二者类型相同；如果类型不同（比如只有返回类型不同），程序非良构。

### 对应的精确定义

按 [[basic.scope.scope#4]]，两个（非模板）函数声明**声明对应的重载**（declare corresponding overloads），当且仅当：

- 它们的非对象形参类型列表（non-object-parameter-type-list）相同；
- 尾随 *requires-clause*（如果有）等价；
- 如果二者都是非静态成员函数，它们的对象形参对应（[[basic.scope.scope#3]]）。

对函数模板，还要求 *template-head* 等价、返回类型等价（这一点与非模板函数不同，见下文）。

对象形参对应的规则（[[basic.scope.scope#3]]）用来处理 ref-qualifier 和显式对象形参（*deducing this*）：

- 若恰好一个是没有 *ref-qualifier* 的隐式对象成员函数，则比较两者的对象形参类型去掉引用之后是否相同；
- 否则，比较对象形参类型本身是否相同。

### 逐条看：哪些看起来不同的声明其实相同

**1. 只有返回类型不同。** 返回类型不在对应的判定条件里，所以两个声明对应，声明的是同一实体，而类型不同，因此非良构。

```cpp error
int    f(int);
double f(int);   // error: 与上一行对应，声明同一实体，但类型不同
```

为什么这样设计？因为调用 `f(1)` 时，表达式本身不携带期望的返回类型（C++ 的类型推导是自底向上的），重载决议无法依据返回类型做选择。允许这种重载只会制造永远歧义的调用。

**2. 形参类型经调整后相同。** [[dcl.fct]] 在形成函数类型时会：数组形参调整为指针、函数形参调整为函数指针、删除形参类型的顶层 cv 限定。调整后相同，就是同一个形参类型列表。typedef/别名当然也不引入新类型。

```cpp run ok
typedef int Int;
void f(int);
void f(Int);          // 重声明同一个 f
void g(int*);
void g(int[]);        // 重声明：int[] 调整为 int*
void g(int[10]);      // 仍是重声明：数组界被丢掉（Clang 会给 -Warray-parameter 警告）
void h(int());        // 形参是函数类型，调整为 int(*)()
void h(int (*)());    // 重声明
void k(int);
void k(const int);    // 重声明：顶层 const 不属于函数类型

void k(const int x) { (void)x; }   // 这是 k(int) 的定义；x 在函数体内是 const
int main() { k(1); }
```

而非顶层的 cv 会区分重载：`void m(int&)` 与 `void m(const int&)`、`void m(int*)` 与 `void m(const int*)` 都是不同函数。枚举类型与其底层类型也是不同类型：

```cpp run ok
enum E : int { a };
void f(int)  {}
void f(E)    {}      // OK，另一个重载
void g(char) {}
void g(signed char) {}
void g(unsigned char) {}   // char、signed char、unsigned char 是三个不同的类型
int main() { f(a); g('x'); }
```

**3. 默认实参不区分重载。** 默认实参不是函数类型的一部分。下面两个声明不对应（形参个数不同），所以能共存，但 `f(1)` 歧义：

```cpp
void f(int);
void f(int, int = 0);
void use() {
  f(1, 2);   // OK：只有第二个可行
  f(1);      // error: 歧义，两个都是精确匹配
}
```

**4. 异常规格不区分重载。** `noexcept` 自 C++17 起是函数类型的一部分，但它不在对应的条件里。于是 `void f() noexcept;` 与 `void f();` 对应、声明同一实体，而 [[except.spec]] 要求同一函数的各声明异常规格一致，所以非良构。

```cpp error
void f() noexcept;
void f();          // error: 同一函数的异常规格不一致
```

**5. 静态与非静态成员函数，形参相同。** 静态成员函数没有对象形参；[[basic.scope.scope#4.4]] 只在二者都是非静态成员时才比较对象形参，所以一个静态、一个非静态，且非对象形参列表相同时，二者对应，因而冲突。

```cpp
struct X {
  static void f();
  void f() const;     // error: 与 static f() 对应，构成重声明
};
```

为什么禁止？因为 `x.f()` 对二者都能调用（静态成员函数可以通过对象调用，[[over.match.funcs#4]] 规定其隐式对象形参匹配任何对象），而且对静态函数来说，对象实参的匹配既不更好也不更差（[[over.best.ics#8]]），这种重载在大多数调用下注定歧义。

**6. 有 ref-qualifier 与无 ref-qualifier 的声明不能混用。** 对象形参对应规则 ¶3.1 规定：恰好一个没有 *ref-qualifier* 时，比较去掉引用后的对象形参类型。

```cpp
struct X {
  void g();
  void g() const;      // OK：对象形参 X& 与 const X& 去掉引用后不同
  void g() &;          // error: 与 g() 对应——去掉引用后都是 X
  void h() &;
  void h() &&;         // OK：二者都有 ref-qualifier，对象形参 X& 与 X&& 不同
  void k() const;
  void k() const &&;   // error: 与 k() const 对应
};
```

这条规则在 C++11 引入 ref-qualifier 时就存在（当时的表述是：如果有一个带 ref-qualifier，则所有同名同参的都必须带）。动机是避免不分左右值的版本与只接受右值的版本在左值上产生含糊：无 ref-qualifier 的版本对左值、右值都能调用（[[over.match.funcs#5]]），和 `&&` 版本放在一起只会让规则变复杂，却很少有用。

**7. 显式对象形参（C++23）。** [[P0847R7]] 引入了 `this` 形参。它与隐式对象形参之间用同一套对象形参对应规则比较：

```cpp
struct X {
  void k();
  void k(this X&);              // error: 对象形参都是 X&（前者无 ref-qualifier，去引用比较也相同）
  void j(this const X&);
  void j() const &;             // error: 对象形参类型都是 const X&
  void h(this X&, int);
  void h(int) &&;               // OK：对象形参 X& 与 X&& 不同（后者有 ref-qualifier，直接比较）
  void m(this X);               // 按值的对象形参
  void m() const;               // OK：X 与 const X& 去掉引用后不同
};
```

### 函数模板：返回类型参与区分

对函数模板，[[basic.scope.scope#3]] 的对应签名要求返回类型等价。所以下面两个模板不对应，是合法的两个重载，只是绝大多数调用都会歧义：

```cpp
template<class T> int    g(T);
template<class T> double g(T);   // OK：返回类型不同的两个函数模板可以共存
void use() {
  g(1);                          // error: 歧义
  int (*p)(int) = &g<int>;       // OK：按目标类型选中第一个（[over.over]）
}
```

为什么模板要不同？因为模板的返回类型可以依赖模板形参，参与 SFINAE（`template<class T> auto f(T t) -> decltype(t.foo())`），它必须是模板身份的一部分，否则无法区分实际上不同的模板。这也与 Itanium ABI 一致：函数模板特化的修饰名编码了返回类型，而普通函数不编码。

### 约束也是身份的一部分

两个声明的尾随 *requires-clause* 不等价时不对应，因此可以共存，由 [[over.match.best#2.6]] 按更受约束的规则决胜：

```cpp run ok
#include <concepts>
template<class T>
struct Box {
  int get() const requires std::integral<T> { return 1; }
  int get() const { return 2; }        // 不对应：一个有约束、一个没有
};
int main() {
  return Box<int>{}.get() == 1 && Box<double>{}.get() == 2 ? 0 : 1;
}
```

### 在不同作用域找到的对应声明

[[basic.scope.scope#6]] 的注 4 提醒：重载决议可能同时看到来自不同作用域的、彼此对应的声明（经 *using-directive*、ADL、运算符的成员/非成员查找）。这些声明并不在同一作用域里冲突，所以声明本身合法，但调用时往往歧义：

```cpp
namespace A { int f(int); }
namespace B { int f(int); }
using namespace A;
using namespace B;
void use() {
  f(1);   // error: 歧义——A::f 与 B::f 都是候选，且形参完全相同
}
```

## 实现视角

!!! impl
    - 名字修饰：Itanium C++ ABI 下，非模板函数的修饰名只编码（经 [[dcl.fct]] 调整后的）形参类型，不编码返回类型，`int f(int)` 与 `double f(int)` 都修饰成 `_Z1fi`。所以跨 TU 的返回类型不一致即使没有被编译器发现，链接器也会把它们连到一起，造成 ODR 违规。函数模板特化则编码返回类型。
    - ref-qualifier 与 const：修饰名里分别编码（如 `R`/`O` 与 `K` 限定）。
    - `noexcept` 不编码进普通函数的修饰名，但编码进函数指针类型（例如作为模板实参时）。

## 历史与演进

!!! history
    - C++98：`[over.load]` 列出不可重载的声明：仅返回类型不同；静态与非静态成员同参；typedef 等价；指针与数组、指针与函数形参等价；仅顶层 cv 不同；仅默认实参不同。
    - C++11：加入 ref-qualifier，并规定同名同参的成员函数要么都有 ref-qualifier，要么都没有。
    - C++17：`noexcept` 进入函数类型，但不能据此重载。
    - C++20：约束（*requires-clause*）成为区分声明的要素。
    - C++23：[[P1787R6]] 用对应的概念重写了所有这些规则，删除了 `[over.load]`；[[P0847R7]] 加入显式对象形参，并用对象形参对应的规则把它与 ref-qualifier 规则统一起来。
    - C++26：{{c++26}} 反射的 *splice-expression* 也能形成重载集（¶2 注 2）。

## 陷阱

!!! pitfall "以为 `const` 形参能构成重载"
    `void f(int)` 与 `void f(const int)` 是同一个函数。你可以在声明里写 `int`、在定义里写 `const int`，这是合法且常见的风格。

!!! pitfall "以为派生类的同名函数会与基类的重载"
    它会隐藏基类所有同名函数（无论参数如何）。要合并重载集，用 `using Base::f;`。

!!! pitfall "以为默认实参能消除歧义"
    默认实参只影响可行性（让少传实参的调用变得可行），不影响排序；`f(int)` 和 `f(int, int = 0)` 对 `f(1)` 永远歧义。

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

\#1、#2、#3 两两之间都有 *ref-qualifier*，直接比较对象形参类型：`S&`、`const S&`、`S&&` 互不相同，所以三者可以共存。#4 没有 *ref-qualifier*，与 #1 比较时去掉引用，`S` 与 `S` 相同，二者对应，因此非良构。(#4 与 #2 去引用后是 `S` 与 `const S`，不对应；但只要与任何一个冲突就已经非良构了。)
</details>

!!! question "2. `void f(int[3]);` 与 `void f(int(&)[3]);` 呢？"

<details markdown="1">
<summary>答案</summary>

不对应。第一个调整为 `void f(int*)`，第二个的形参是到 3 个 int 的数组的左值引用，类型不同，可以共存。对 `int a[3]; f(a);`，前者需要数组到指针转换（左值变换，Exact Match），后者是直接引用绑定（恒等）。按 [[over.ics.rank#3.2.1]] 比较标准转换序列时不考虑左值变换，所以二者都视为恒等转换，无法区分，结果是歧义。
</details>

## 小结

!!! summary
    - 重载指同一作用域内的多个同名函数/函数模板；不同作用域之间是隐藏，不是重载。
    - 能否共存取决于是否对应（[[basic.scope.scope#4]]）：非对象形参类型列表（调整后）、尾随 *requires-clause*、（双方都是非静态成员时）对象形参。
    - 对应的声明是同一实体，类型必须完全相同；因此仅返回类型不同、仅 `noexcept` 不同都非良构。
    - 函数模板的返回类型参与对应签名的判定，所以模板可以仅按返回类型重载（但调用多半歧义）。
    - 有无 *ref-qualifier* 不能混用；静态与非静态同参不能共存；显式对象形参用同一套规则比较。
