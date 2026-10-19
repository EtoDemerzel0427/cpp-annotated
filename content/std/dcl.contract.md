---
title: 函数契约说明符
summary: C++26 的前置条件 pre 与后置条件 post：写在哪里、何时检查、为什么属于函数而不属于声明或类型、重声明怎样保持一致，以及后置条件里的形参和结果绑定。
status: draft
covers: dcl.contract.func, dcl.contract.res
since: c++26
papers: P2900
related: basic.contract, stmt.contract.assert, expr.call, expr.prim.id.unqual, dcl.decl, dcl.fct.def.coroutine, class.temporary
tags: 契约, C++26, 前置条件, 后置条件
updated: 2026-10-19
---

!!! tldr
    - `pre(条件)` 在形参初始化之后、函数体之前检查；`post(r: 条件)` 在函数正常返回时检查，抛异常退出时不检查。
    - 契约属于函数，由函数的首次声明引入。重声明要么不写契约，要么写出含义完全相同的一组。
    - 后置条件用到的按值形参必须在函数的所有声明里都是 `const`，否则函数体改了它，后置条件读到的就不是调用者传入的值。
    - 契约不是函数类型的一部分，也不参与重载决议；通过函数指针调用时照样检查。
    - 截至写作时本机 Clang 23 还不支持契约语法，本页例子都按标准原文分析，没有经过编译验证，因此不标判定。

## 前置条件和后置条件

```cpp
#include <cstddef>
#include <vector>

// i 必须是合法下标；返回值不会超过 v 的元素个数
std::size_t count_from(const std::vector<int>& v,
                       std::size_t i)
  pre(i <= v.size())
  post(r: r <= v.size())
{
  return v.size() - i;
}
```

C++26 的**契约断言**（[[g:contract-assertion|contract assertion]]）有三种写法：写在函数声明上的 `pre` 和 `post`，以及函数体里的语句 `contract_assert`（[[stmt.contract.assert]]）。它们共同的规则放在 [[basic.contract]]：断言的条件叫做**谓词**，每次求值采用 ignore、observe、enforce、quick-enforce 四种语义之一，具体用哪种由实现决定，通常由编译选项控制；后三种会检查谓词，其中 enforce 和 quick-enforce 在违反时终止程序（[[basic.contract.eval]]）。

本页讲前两种作为声明一部分的规则。

¶1 **函数契约断言**（[[g:function-contract-assertion|function contract assertion]]）是与函数关联的契约断言。`pre` 引入**前置条件断言**，关联于进入函数；`post` 引入**后置条件断言**，关联于正常退出函数。注 1 说明，经由异常（[[expr.throw]]）或 `longjmp` 离开函数不算正常退出，不检查后置条件。后置条件描述的是函数成功时保证什么。

¶2 谓词是括号里的 *conditional-expression* 按语境转换为 `bool` 的结果。文法用的是 *conditional-expression* 而不是 *expression*，所以顶层不能有逗号运算符或赋值，需要时要再加一层括号。谓词中引用的外部变量和形参都是 const 的，`this` 是指向 const 的指针（[[basic.contract.general]]）。

### 写在哪里

```
precondition-specifier:   pre 属性(可选) ( 条件 )
postcondition-specifier:  post 属性(可选) ( 结果名:(可选) 条件 )
```

`pre` 和 `post` 不是保留关键字，只在这个位置有特殊含义，`int pre = 0;` 仍然合法。契约说明符写在声明符之后、函数体或分号之前；有尾置 requires 子句或 `override`、`final` 时，写在它们后面（[[dcl.decl]]、[[class.mem]]、[[dcl.fct.def.general]]）：

```cpp
#include <concepts>
int f(int x) pre(x > 0) post(r: r > x);

template<class T>
T g(T x) requires std::integral<T> pre(x != 0);

auto l = [](int n) pre(n > 0) { return n; };
```

注 2 说明，lambda 上的契约作用于闭包类型的函数调用运算符。[[dcl.decl.general#6]] 规定，只有声明函数的声明符才能带契约说明符。

### 何时检查

[[expr.call]] 规定了检查的时机：

- 前置条件在所有形参初始化之后、函数体开始之前求值；
- 后置条件在返回值初始化、局部变量销毁之后求值，在形参销毁之前（[[stmt.return]]）。如果实现为返回值引入了临时对象（[[class.temporary]]），后置条件与这些临时对象或结果对象的初始化之间的先后顺序不确定。

{{c++29}} 虚函数也可以带契约。通过类成员访问发生虚调用时，检查顺序是：静态选择的函数的前置条件，实际调用的函数的前置条件，函数体，实际调用的函数的后置条件，静态选择的函数的后置条件（[[expr.call#5]]）。所以通过基类引用调用时，基类和最终覆盖函数的契约都会检查。用限定名 `x.Base::f()` 做非虚调用时，只检查 `Base::f` 自己的契约。C++26 本身禁止虚函数带契约说明符，当前草案去掉了这条限制。

## 契约属于函数（¶3–5）

### 由首次声明引入（¶3）

一个声明如果没有同一实体的其他声明从它可达，它就是**首次声明**（first declaration，[[basic.def]]），否则是**重声明**。

¶3 函数某个首次声明上的契约说明符，为这个函数引入相应的契约断言。`pre`、`post` 后面的属性属于引入的契约断言。

所以契约是函数的属性，不是某个声明的属性。这与默认实参正相反（[[dcl.fct.default]]）：默认实参附在声明上，块作用域里的声明可以有另一套；契约一旦由首次声明给出，不论调用经由哪个声明找到函数，用的都是这一组。

### 重声明必须一致（¶4–5）

```cpp
bool b1, b2;

void f() pre (b1) pre ([]{ return b2; }());
void f();                    // OK：省略契约
void f() pre (b1) pre ([]{ return b2; }());
                             // IFNDR：两个闭包类型不同
void f() pre (b1);           // error: 只重复了一部分

int g() post(r : b1);
int g() post(b1);            // error: 一个有结果名，一个没有

namespace N {
  void h() pre (b1);         // ::b1
  bool b1;
  void h() pre (b1);         // error: 这里是 N::b1
}
```

¶4 重声明要么不写契约说明符，要么写出与从它可达的首次声明相同的一组。如果两者在不同的翻译单元，比如首次声明在模块接口里，只有重声明属于具名模块时才要求诊断。

两个翻译单元各自包含同一个头文件时，头文件里的声明在两边都是首次声明，彼此不可达。第 4 段要求这样的两个首次声明给出相同的契约说明符，违反时程序非良构但不要求诊断（IFNDR）：编译器和链接器都可能毫无提示。

¶5 规定什么叫相同：说明符相同、顺序相同，并且每对说明符满足：

- ¶5.1 把两边的谓词分别放进函数定义里时，满足 ODR（[[basic.def.odr]]），即记号相同且每个名字找到同一个实体。允许形参、外围模板的模板形参和结果名改名；
- ¶5.2 要么都有结果名，要么都没有。

所以相同指的是含义相同，不是文本相同。上例的 `N::h` 两次都写 `b1`，但查找到的实体不同，契约就不同。如果仅仅因为谓词里的两个 lambda 不同而不满足条件，不要求诊断，因为每个 lambda 表达式都有自己独有的闭包类型。

实践中，把契约写在头文件的声明上，源文件里的定义省略不写，这是第 4 段允许的，也免得维护两份。

## 不能带契约的地方（¶6、¶8）

¶6 弃置函数（[[dcl.fct.def.delete]]）和在首次声明上预置的函数（[[dcl.fct.def.default]]）不能有契约说明符。前者永远不会被调用；后者的行为由语言规定，而且可能是平凡的。

```cpp
struct S {
  S() pre(true) = default;          // error: 在首次声明上预置
  void f(int) pre(true) = delete;   // error: 弃置函数
  S(const S&);
};
S::S(const S&) pre(true) = default;
  // error: 这是重声明，与类内的首次声明（无契约）不一致
```

¶8 是注：通过函数指针或成员函数指针间接调用时，函数的契约照样求值。但函数指针、成员函数指针和函数类型别名本身不能带契约说明符，因为契约不是函数类型的一部分（[[dcl.fct#13]]）。

```cpp
int f(int x) pre(x > 0);
int (*pf)(int) = f;             // OK：pf(-1) 仍检查 f 的前置条件
int (*pg)(int) pre(true);       // error: pg 不是函数
using F = int(int) pre(true);   // error: 别名不能带契约
```

## 后置条件里的形参必须是 const（¶7）

后置条件在函数体执行之后求值，而函数体可以修改按值传入的形参：

```cpp
int next(int x) post(r: r == x + 1) {   // 假如允许
  x = 100;
  return 1;    // 后置条件读到的 x 是 100，不是调用者传入的值
}
```

调用者理解的 `x` 是传进去的值。所以第 7 段规定：如果后置条件的谓词 odr-use 了函数的某个非引用形参，这个形参以及它在函数所有声明中的对应形参都必须是 const 类型。const 保证函数体改不了它，后置条件看到的就是传入的值。

注 4 补充了两点：

- 这个要求也适用于没有写后置条件的那些声明，例如头文件里只写了 `int g(const int x);`，定义里写了后置条件，两处都要 `const`。顶层 const 本来不属于函数类型（[[dcl.fct#5]]），这里是额外的要求；
- 数组和函数类型的形参会调整成指针，指针本身不是 const，即使写了 const：

```cpp
int f(const int i[10])
  post(r: r == i[0]);   // error: i 的类型是 const int*，不是 int* const

int g(int x) post(r: r > x);         // error: x 不是 const
int h(const int x) post(r: r > x);   // OK
int k(int& x) post(x > 0);           // OK：引用形参不受限制
```

引用形参不受限制。它指代调用者的对象，后置条件读到的是函数返回时该对象的状态，这正是对引用形参想要表达的意思。

协程更进一步：它的形参被复制进协程帧，函数体改的是副本，所以协程的后置条件 odr-use 非引用形参一律非良构（[[dcl.fct.def.coroutine#6]]）。

## 结果绑定 [dcl.contract.res]

```cpp
int f()
  post(r : r == 1)      // r 指代 f() 返回的 int
{
  return 1;
}
int i = f();            // 检查通过
```

¶1 后置条件里的 `r :` 是一个声明，它把 `r` 引入为函数**结果绑定**（[[g:result-binding|result binding]]）的名字：

- 结果绑定指代这次调用返回的对象或引用本身，不是副本；类型是函数的返回类型；
- 返回类型是 cv `void` 时，不能写结果名；
- 注 1 说明，命名结果绑定的表达式是 const 左值（[[expr.prim.id.unqual#6]]）。

结果绑定指代返回的对象本身，这与 [[class.temporary]] 的一条许可有关：平凡可复制类型的返回值，实现可以先放进临时对象（例如经由寄存器返回）再复制到目标。标准例 2：

```cpp
struct A {};                          // 可能经由临时对象返回
struct B { B() {} B(const B&) {} };   // 不会引入临时对象

template <typename T>
T f(T* const ptr)
  post(r: &r == ptr)
{
  return {};
}

int main() {
  A a = f(&a);   // 检查可能失败：r 可能指代临时对象
  B b = f(&b);   // 检查必定通过：r 就是 b
}
```

实现引入了临时对象时，`r` 指代最近初始化的那个临时对象（[[expr.prim.id.unqual#14]]），它的地址不是 `&a`。

¶2 非模板化函数的返回类型含占位符（如 `auto`）时，带结果名的后置条件只能写在定义上。没有函数体就推导不出返回类型，结果绑定的类型也就无从确定。模板化函数不受此限制，实例化时总会有定义。

```cpp
auto g(auto&) post(r: r >= 0);   // OK：g 是函数模板
auto h()      post(r: r >= 0);   // error: 不是定义
auto k()      post(r: r >= 0)    // OK：定义
{
  return 0;
}
```

## 契约何时被需要（¶9）

¶9 函数被 odr-use 或被定义时，它的契约断言被认为是**需要的**（needed）。[[temp.inst]] 据此决定何时实例化函数模板特化的谓词。

注 6 说明，重载决议不考虑契约说明符。契约不像 requires 子句那样筛选候选：

```cpp
template <typename T> void f(T t) pre(t == "");
template <typename T> void f(T&& t);
void g() {
  f(5);   // error: 二义性，第一个的前置条件
          //   对 int 根本无法实例化也不影响
}
```

这是有意的设计。契约是运行时对正确性的检查，加上或去掉契约不应该改变调用的是哪个函数。想按条件排除重载，用 requires 子句。

## 实现视角

!!! impl
    - 标准允许在调用方或被调方插入检查代码。在被调函数入口和出口检查只需一份代码；在调用点检查则可以让不同翻译单元采用不同的求值语义（[[basic.contract.eval]]）。
    - 契约说明符不进入函数类型，不影响名字修饰。给已有函数的声明加上契约不改变 ABI。
    - 同一翻译单元内重声明的契约不一致必须诊断。跨翻译单元的不一致，典型情况是头文件在不同的宏配置下被包含，属于 IFNDR，链接器通常发现不了。

## 历史与演进

!!! history
    - C++20 的工作草案曾经以属性语法 `[[expects: …]]`、`[[ensures r: …]]`、`[[assert: …]]` 加入契约（[[P0542R5]]），因为设计上的分歧，在 C++20 发布前被整体移除。
    - 之后的设计以最小可行方案为目标重新开始，最终形成 [[P2900]]：改用 `pre`、`post`、`contract_assert`，并引入四种求值语义。C++26 采纳了它。
    - 当前草案在 C++26 之后允许虚函数带契约，并规定了检查顺序（[[expr.call#5]]）。

## 常见误解

!!! pitfall "抛异常也会检查后置条件"
    只有正常返回才检查后置条件。要表达无论如何都成立的性质，用 RAII 或在函数体里写 `contract_assert`。

!!! pitfall "只在写了后置条件的那个声明上加 const"
    `int f(int x) post(r: r > x)` 非良构，必须写成 `int f(const int x)`，而且所有声明都要写 `const`，包括头文件里没写后置条件的那一个。

!!! pitfall "谓词的副作用一定会发生"
    带检查的语义下，谓词可能根本不被真正求值，实现可以用一个没有副作用的等价计算得到它的值；ignore 语义下谓词不求值（[[basic.contract.eval]]）。不要依赖谓词的副作用。

## 思考题

!!! question "思考题 1"
    头文件 `a.h` 里有 `int f(int x) pre(x > LIMIT);`，`LIMIT` 是宏。一个源文件在包含前 `#define LIMIT 0`，另一个源文件 `#define LIMIT 1`。程序是否良构？

<details markdown="1">
<summary>答案</summary>

两个翻译单元里的声明都是首次声明，第 4 段要求它们的契约说明符相同。宏展开后谓词分别是 `x > 0` 和 `x > 1`，按第 5.1 项的 ODR 比较不同，所以程序非良构，不要求诊断。这和 inline 函数体在不同翻译单元里展开出不同的宏值违反 ODR 是同一类问题。
</details>

!!! question "思考题 2"
    为什么第 7 段只要求非引用形参是 const，`int& x` 却可以在后置条件里随便用？

<details markdown="1">
<summary>答案</summary>

非引用形参是函数自己的副本，调用者关心的是传入的值。函数体修改了副本，后置条件读到的值就和调用者理解的 `x` 不一致，要求 const 排除了这种情况。引用形参指代调用者的对象，修改它本来就是函数的效果之一，后置条件读取返回时的状态正是要表达的意思。
</details>
