---
title: lambda 表达式
summary: 一个 lambda 表达式定义一个无名的闭包类并创建它的对象：调用运算符的性质（const、mutable、static、constexpr、泛型、显式对象形参），捕获什么、怎样捕获、捕获后名字指向哪里，以及向函数指针的转换和特殊成员函数。
status: done
covers: expr.prim.lambda.general, expr.prim.lambda.closure, expr.prim.lambda.capture
papers: P0018R3, P0170R1, P0588R1, P0428R2, P0624R2, P0315R4, P0780R2, P0806R2, P1091R3, P1381R1, P1102R2, P1169R4, P0847R7, P2173R1, P2036R3
related: expr.prim.id, basic.def.odr, basic.scope.lambda, dcl.fct, dcl.spec.auto, class.copy.ctor, depr.capture.this, temp.variadic
tags: lambda, 闭包, 捕获, odr-use, 泛型编程
updated: 2026-10-19
---

!!! tldr
    - 每个 lambda 表达式都定义一个独一无二的无名类（闭包类型），并创建这个类的一个对象（闭包对象）；按值捕获的变量成为它的数据成员。
    - 调用运算符默认是 `const` 成员函数；`mutable` 去掉 const，`static` 让它成为静态成员函数，满足条件时它自动是 `constexpr`。
    - 写了 `[=]` 或 `[&]` 时，lambda 体里潜在求值地引用了哪些外层局部变量，就隐式捕获哪些，由语法决定，不看是否真的 odr-use；`[=]` 隐式捕获的 `this` 是指针，不是对象的副本，已弃用。
    - 读一个常量的值不算 odr-use，所以不捕获也能用；取地址、绑定引用就必须捕获。
    - 只有没有捕获、没有显式对象形参的 lambda 能转换为函数指针（泛型 lambda 得到一个转换函数模板）；C++20 起无捕获的闭包类型还可以默认构造和赋值。

## lambda 是一个类加一个对象

```cpp
void demo() {
  int n = 10;
  auto add = [n](int x) { return x + n; };
}
```

标准没有为 lambda 引入新的运行时概念。它规定 `[n](int x) { return x + n; }` 做两件事：定义一个无名的类，并创建这个类的一个对象。编译器替你写出的类大致是这样（仅为示意，真正的闭包类型没有这样的构造函数，成员也没有名字）：

```cpp
class __Closure {
  int __n;                                            // 按值捕获的 n
public:
  __Closure(int n) : __n(n) {}
  auto operator()(int x) const { return x + __n; }    // 默认是 const
};
auto add = __Closure{n};
```

lambda 的大多数性质都可以从这个模型推出来。

lambda 表达式是一个纯右值（[[expr.prim.lambda.general#2]]），它的结果对象叫做**闭包对象**（[[g:closure-object|closure object]]）。因为是纯右值，`auto f = [] {};` 里的 `f` 就是那个闭包对象本身，没有拷贝或移动（[[dcl.init]]）。

lambda 表达式的类型叫做**闭包类型**（[[g:closure-type|closure type]]），是一个独一无二的无名非联合类类型（[[expr.prim.lambda.closure#1]]）。独一无二是字面意义上的：两个逐字相同的 lambda 也是两个类型。

```cpp run ok
#include <type_traits>

auto a = [] { return 1; };
auto b = [] { return 1; };
static_assert(!std::is_same_v<decltype(a), decltype(b)>);

using T1 = decltype([] {});   // C++20 起 lambda 可以出现在未求值操作数中
using T2 = decltype([] {});
static_assert(!std::is_same_v<T1, T2>);

int main() {}
```

闭包类型声明在包含这个 lambda 的最小的块作用域、类作用域或命名空间作用域里。这决定了实参依赖查找（ADL）时它关联哪些命名空间（[[expr.prim.lambda.closure#3]]、[[basic.lookup.argdep]]）。

## 文法 [expr.prim.lambda.general]

一个 lambda 依次由这些部分组成，除了开头的 `[捕获]` 和最后的函数体，都可以省略：

```text
[捕获]  <模板形参> requires子句  属性  (形参)  说明符  noexcept  属性  -> 返回类型  requires子句  契约  { 函数体 }
```

- `<模板形参>` {{c++20}}：`[]<class T>(T a) {}`。
- `(形参)` 之前的属性 {{c++23}} 作用于调用运算符本身，例如 `[] [[nodiscard]] () { return 1; }`；`(形参)` 之后的属性作用于调用运算符的类型。
- 说明符是 `mutable`、`constexpr`、`consteval`、`static` 中的若干个。
- 没有形参时 `()` 可以省略。C++23 起，即使后面有说明符、`noexcept` 或尾置返回类型也能省略：`[] mutable {}` 合法，C++20 要写 `[]() mutable {}`。
- 契约 {{c++26}}：`[](int x) pre(x > 0) { … }`。

¶4 说明符的组合有几条限制：每个说明符最多出现一次；`constexpr` 和 `consteval` 不能同时出现；`mutable` 和 `static` 不能同时出现；有显式对象形参（`this auto self`）时不能写 `mutable` 或 `static`；写了 `static` 就不能有任何捕获。

```cpp error
auto e1 = [](int) constexpr consteval {};   // error: constexpr 与 consteval 不能共存
auto e2 = [](this auto) mutable {};         // error: 显式对象形参与 mutable
auto e3 = [](this auto) static {};          // error: 显式对象形参与 static
auto e4 = [](int) mutable static {};        // error: mutable 与 static
void f() {
  int x = 0;
  auto e5 = [x](int) static { return x; };  // error: static lambda 不能有捕获
}
```

这些限制都来自上面的类模型。`mutable` 的作用是让调用运算符不再是 const，有显式对象形参时这一点改由 `self` 的类型表达；静态成员函数没有对象，也就无从访问捕获成员。

## 调用运算符

### 返回类型 [expr.prim.lambda.general]

¶5 没有尾置返回类型时，lambda 视为写了 `-> auto`，返回类型按 [[dcl.spec.auto]] 从 `return` 语句推导。所以多个 `return` 推导出的类型必须一致，`return {1, 2};` 无法推导，推导结果也不会是引用。要返回引用，写 `-> auto&` 或 `-> decltype(auto)`。

```cpp error
void f() {
  auto x1 = [](int i) { return i; };       // OK：返回 int
  auto x2 = [] { return { 1, 2 }; };       // error: 不能从花括号列表推导返回类型
  int j;
  auto x3 = [&]() -> auto&& { return j; }; // OK：返回 int&
}
```

C++11 中，只有函数体只含一条 `return 表达式;` 的 lambda 才推导返回类型，其余返回 `void`。C++14 改为与普通函数的 `auto` 返回类型相同的规则。

### const、mutable、static [expr.prim.lambda.closure]

¶5 闭包类型有一个 public、inline 的函数调用运算符。形参和返回类型来自 lambda 的形参列表和返回类型。¶7 规定了它是哪一种成员函数：

| lambda 写法 | 调用运算符 |
|---|---|
| `[]() { }` | 非静态成员函数，`const` |
| `[]() mutable { }` | 非静态成员函数，非 const |
| `[]() static { }` {{c++23}} | 静态成员函数 |
| `[](this auto&& self) { }` {{c++23}} | 显式对象成员函数，cv 和引用由 `self` 的类型决定 |

调用运算符从来不是 `virtual`，也不是 `volatile`。lambda 上写的 `noexcept` 和契约都作用于调用运算符。

¶7 还规定，满足以下任一条件时调用运算符是 constexpr 函数：写了 `constexpr` 或 `consteval`，或者它本身满足 constexpr 函数的要求（[[dcl.constexpr]]）。后者意味着 C++17 起大多数 lambda 不用标注就能在常量表达式里调用。写了 `consteval` 的是立即函数，只能在编译期调用。

```cpp run ok
auto ID = [](auto a) { return a; };
static_assert(ID(3) == 3);                          // 隐式 constexpr

auto ce = [](int i) consteval { return i + 1; };    // 立即函数
static_assert(ce(1) == 2);

auto sl = [](int i) static { return i * 2; };       // C++23
static_assert(decltype(sl)::operator()(3) == 6);    // 不需要对象就能调用

int main() {}
```

调用运算符是 constexpr 函数，不代表每次调用都是常量表达式。¶8 的例子里，`auto two = monoid(2);` 中的 `two` 不是 constexpr 变量，调用 `two()` 要读取它的捕获成员，所以 `static_assert(two() == 2)` 非良构。

!!! tip "static lambda 有什么用"
    无捕获 lambda 的非静态 `operator()` 仍然要接收一个对象参数，哪怕这个对象是空的。`static` 让调用运算符成为真正的静态函数，省掉这个参数；转换为函数指针时（见下文）也直接得到它的地址，不需要中间的转发函数。

### 泛型 lambda 与显式对象形参

¶6 lambda 有 `auto` 形参或者有模板形参列表时，叫做**泛型 lambda**（[[g:generic-lambda|generic lambda]]）。`[](this auto self, int i)` 也是泛型 lambda，因为 `this auto` 也是一个 `auto` 形参（[expr.prim.lambda.general]）。

按 [[expr.prim.lambda.closure#5]]，泛型 lambda 的调用运算符是一个成员函数模板，模板形参由写出的 `<…>` 和每个 `auto` 形参生成的模板形参组成。`<…>` 之后的 *requires-clause* 和形参列表之后的 *requires-clause* 都成为这个模板的约束。

标准例 1 演示了泛型 lambda 的嵌套、形参包的捕获，以及用显式对象形参写递归：

```cpp run ok
#include <iostream>
#include <utility>

int main() {
  auto vglambda = [](auto printer) {
    return [=](auto&&... ts) {                   // ts 是函数形参包
      printer(std::forward<decltype(ts)>(ts)...);
      return [=]() { printer(ts...); };          // 隐式按值捕获 printer 和整个包 ts
    };
  };
  auto p = vglambda([](auto v1, auto v2, auto v3) { std::cout << v1 << v2 << v3; });
  auto q = p(1, 'a', 3.14);    // 输出 1a3.14
  q();                         // 再次输出 1a3.14

  auto fact = [](this auto self, int n) -> int {
    return (n <= 1) ? 1 : n * self(n - 1);
  };
  std::cout << '\n' << fact(5) << '\n';         // 120
}
```

C++23 之前，lambda 体里没有办法指代 lambda 自己：闭包类型没有名字，`this` 指的是外层对象（见下一节）。显式对象形参 `self` 就是闭包对象本身。

[[expr.prim.lambda.closure#6]] 规定，有捕获的 lambda，其显式对象形参的类型只能是闭包类型、公开且无歧义地派生自闭包类型的类，或者指向这些类型的引用。访问捕获就是访问 `self` 的成员，`self` 的类型与闭包无关时这无从谈起。

```cpp error
struct C {
  template <typename T> C(T);   // 可以从任何类型构造
};

void func(int i) {
  int x = [=](this auto&&) { return i; }();   // OK
  int y = [=](this C) { return i; }();        // error: 有捕获，C 与闭包类型无关
  int z = [](this C) { return 42; }();        // OK：无捕获
}
```

### 函数体不在闭包类型的作用域里 [expr.prim.lambda.closure]

¶16 lambda 的函数体成为调用运算符的函数体，但它不在闭包类型的作用域里。所以在 lambda 体里，名字查找找不到闭包类型的成员；`this` 指向外层的对象（[[expr.prim.this]]）；写 `operator()` 找到的是外层类的 `operator()`。

```cpp ok
struct S1 {
  int x, y;
  int operator()(int);
  void f() {
    [=, this]() -> int {
      return operator()(this->x + y);   // 即 S1::operator()(this->x + (*this).y)
    };
  }
};
```

除了 `consteval` 块（{{c++26}}）的函数体，lambda 体开头都会隐式定义 `__func__`（[[dcl.fct.def.general]]），内容由实现定义，Clang 和 GCC 给出 `"operator()"`。

## 捕获 [expr.prim.lambda.capture]

¶1 lambda 体通过捕获来使用外层作用域里的局部实体。**局部实体**（[[g:local-entity|local entity]]，[[basic.pre]]）指自动存储期的变量、结构化绑定，以及成员函数里的 `*this`。全局变量和静态局部变量不是局部实体，不能也不需要捕获，直接用名字就行。

### 捕获列表的写法（¶2–¶5）

```text
[=]  [&]                     默认捕获（capture-default）
[x]  [&x]  [this]  [*this]   简单捕获，x 可以带 ...（包展开）
[x = e]  [&r = e]            init-capture，也可以写 ...x = e
```

¶2 有几条防止冗余的规则：默认捕获是 `&` 时，简单捕获不能再带 `&`；默认捕获是 `=` 时，简单捕获只能是 `&x`、`this` 或 `*this`；同一个名字或 `this` 不能出现两次。

```cpp error
struct S2 { void f(int i); };
void S2::f(int i) {
  [&, i]{ };        // OK
  [&, this, i]{ };  // OK，等价于 [&, i]
  [&, &i]{ };       // error: 默认是 & 时 i 前不能再有 &
  [=, *this]{ };    // OK
  [=, this]{ };     // OK，等价于 [=]，但不会触发弃用警告
  [i, i]{ };        // error: i 重复
  [this, *this]{ }; // error: this 出现两次
}
```

`[&, this]` 是冗余的，为了与 C++14 兼容仍然接受（注 1）。`[=, this]` 是 C++20 加入的写法，用来明确表达按引用捕获 `*this`。

¶3 只有当 lambda 的最内层外围作用域是块作用域（在函数体里），或者它位于默认成员初始化器里、或位于契约断言里时，才能有默认捕获或简单捕获。命名空间作用域的 lambda 不能写 `[=]`、`[&]` 或 `[x]`，那里没有局部实体。init-capture 不受这条限制，命名空间作用域的 `auto counter = [i = 0]() mutable { return i++; };` 是合法的。

¶4 简单捕获里的名字必须指代局部实体，`this` 和 `*this` 都指代局部实体 `*this`。被简单捕获指名的实体称为被**显式捕获**（[[g:explicitly-captured|explicitly captured]]）。¶5 捕获的名字不能与 lambda 的形参或模板形参同名：`[x](int x) {}` 非良构。

### 先要知道：odr-use 与 odr-usable

捕获规则建立在 [[basic.def.odr]] 的两个概念上。

**odr-use**（[[g:odr-use]]）大致是指以需要这个变量本身存在的方式使用它：取地址、绑定引用、读取一个非常量的值。读取一个常量的值（`const int N = 10;` 中的 `N` 用作数组长度、参与算术）不算 odr-use，编译器直接用它的值。

一个局部实体在某处是 **odr-usable**（[[g:odr-usable]]）的，要求它的声明与这个位置之间没有隔着函数形参作用域或类作用域（例如局部类的成员函数），并且隔着的每个 lambda 都捕获了它。在不是 odr-usable 的地方 odr-use 一个局部实体，程序非良构（[[basic.def.odr#10]]）。lambda 要捕获才能使用外层变量，依据就在这里。

### 隐式捕获（¶7）

写了默认捕获 `[=]` 或 `[&]` 时，哪些实体被捕获？¶7 先定义表达式**潜在引用**哪些局部实体：

- (7.1) 命名一个局部实体的 *id-expression* 潜在引用它；命名非静态成员（且不是在取成员指针）的 *id-expression* 潜在引用 `*this`，即使重载决议最后选中的是静态成员函数（注 3）；
- (7.2) `this` 潜在引用 `*this`；
- (7.3) 一个 lambda 表达式潜在引用它的简单捕获所指名的实体，这样外层 lambda 就能感知内层 lambda 的显式捕获。

然后是隐式捕获的定义：

!!! std
    If an expression potentially references a local entity within a scope in which it is odr-usable, and the expression would be potentially evaluated if the effect of any enclosing `typeid` expressions were ignored, the entity is said to be *implicitly captured* by each intervening *lambda-expression* with an associated *capture-default* that does not explicitly capture it.

也就是说，表达式在某处潜在引用一个局部实体，这个实体在那里 odr-usable，并且表达式会被**潜在求值**（[[g:potentially-evaluated|potentially evaluated]]，不在 `sizeof`、`decltype` 这类未求值操作数里），那么中间每个带默认捕获、又没有显式捕获它的 lambda 都**隐式捕获**（[[g:implicitly-captured|implicitly captured]]）它。

这个定义有三处值得注意。

第一，它不要求 odr-use。泛型 lambda 里同一个表达式是不是 odr-use，可能要等实例化、选定了重载才知道；捕获集合却要在定义 lambda 时就确定下来，所以标准只看语法。标准例 4：

```cpp ok
#include <typeinfo>

void f(int, const int (&)[2] = {});   // #1：按值接收
void f(const int&, const int (&)[1]); // #2：按引用接收，会 odr-use

void test() {
  const int x = 17;
  auto g = [](auto a) {
    f(x);              // OK：调用 #1，不是 odr-use，没有默认捕获也能用
  };
  auto g1 = [=](auto a) {
    f(x);              // OK：调用 #1，x 被隐式捕获；实现可以把这个捕获优化掉
  };
  auto g2 = [=](auto a) {
    int selector[sizeof(a) == 1 ? 1 : 2]{};
    f(x, selector);    // OK：捕获 x，根据 a 的类型调用 #1 或 #2
  };
  auto g3 = [=](auto a) {
    typeid(a + x);     // 无论 a + x 是否被求值，都捕获 x
  };
}
```

第二，忽略 `typeid`。`typeid(e)` 是否求值 `e`，取决于 `e` 是不是多态类类型的左值，在泛型 lambda 里可能要实例化后才知道。标准一律按求值处理，宁可多捕获。

第三，捕获集合由语法决定，即使表达式位于 `if constexpr` 被丢弃的分支里，实体也会被捕获（注 4）：

```cpp ok
template<bool B>
void f(int n) {
  [=](auto a) {
    if constexpr (B && sizeof(a) > 4) {
      (void)n;         // 无论 B 和 sizeof(int) 是多少，都捕获 n
    }
  }(0);
}
```

!!! warning "`[=]` 隐式捕获 this 已弃用 {{deprecated}}"
    ¶7 最后一句规定，默认捕获是 `=` 时隐式捕获 `*this` 已弃用（[[depr.capture.this]]）。在成员函数里，`[=] { x = n; }` 中的 `x` 是 `this->x`，被捕获的是指针 `this`，对象本身没有被复制。`[=]` 让人以为一切都复制了，lambda 活得比对象久时就会悬垂。C++20 起应写 `[=, this]`（明确按引用）或 `[=, *this]`（复制整个对象）。Clang 对旧写法给出 `-Wdeprecated-this-capture` 警告。

### 被捕获就是被 odr-use（¶8–¶9）

¶8 被捕获（显式或隐式）的实体被这个 lambda 表达式 odr-use。注 5 由此推出：显式捕获一个在此处不是 odr-usable 的实体，程序非良构。

捕获就这样沿着嵌套的 lambda 一层层向外传播。标准例 6 的前半：

```cpp error
void f1(int i) {
  int const N = 20;
  auto m1 = [=]{
    int const M = 30;
    auto m2 = [i]{
      int x[N][M];         // OK：N、M 未被 odr-use
      x[0][0] = i;         // OK：i 被 m2 显式捕获，被 m1 隐式捕获
    };
  };
  struct s1 {
    int f;
    void work(int n) {
      int m = n*n;
      int j = 40;
      auto m3 = [this,m] {
        auto m4 = [&,j] {  // error: m3 没有捕获 j，j 在这里不是 odr-usable
          int x = n;       // error: 同理，n 被 m3 阻隔
          x += m;          // OK：m 被 m4 隐式捕获，被 m3 显式捕获
          x += i;          // error: i 被局部类 s1 和成员函数 work 的作用域阻隔
          x += f;          // OK：this 被 m4 隐式捕获，被 m3 显式捕获
        };
      };
    }
  };
}
```

`m2` 那一行用到了 ¶7.3：`m2` 显式捕获 `i`，于是 lambda 表达式 `m2` 本身潜在引用 `i`，外层带 `[=]` 的 `m1` 就隐式捕获了 `i`。

¶9 注 6 补充，局部实体在默认实参里不是 odr-usable 的，所以默认实参里的 lambda 不能捕获任何局部实体；init-capture 可以有，只要它的初始化器不引用局部变量。

### 按值捕获（¶10–¶11）

¶10 下面两种情形是**按值捕获**（[[g:captured-by-copy|captured by copy]]）：默认捕获是 `=` 时隐式捕获的实体（`*this` 除外），以及显式捕获时没有用 `&` 和 `this` 写法的实体。

每个按值捕获的实体在闭包类型里对应一个无名的非静态数据成员，它的类型是：

- 实体是对象的引用时，是被引用的类型，也就是复制被引用的对象；
- 实体是函数的引用时，是指向该函数类型的左值引用，函数无法复制；
- 否则就是实体本身的类型，包括 `const`。

匿名联合的成员不能按值捕获。

!!! pitfall "按值捕获保留 const，mutable 也去不掉"
    ```cpp
    const std::string s = "x";
    auto l = [s]() mutable { s += "y"; };   // error: 成员的类型是 const std::string
    ```
    `mutable` 只让调用运算符不再是 const，成员本身的 `const` 仍在。要一个可修改的副本，用 init-capture `[s = s]`：它按 `auto` 推导，去掉了顶层 const。

¶11 lambda 体里，对按值捕获实体的每个 odr-use 都改写成对闭包中对应成员的访问。不构成 odr-use 的使用指代的是原来的那个实体，从来不是闭包成员（注 7）。

```cpp ok
void f(const int*);
void g() {
  const int N = 10;
  [=] {
    int arr[N];   // 不是 odr-use：指代外层的 N，只读它的常量值
    f(&N);        // 取地址是 odr-use：N 被捕获，&N 指向闭包里的成员
  };
}
```

所以没有任何捕获的 lambda 也可以使用常量的值，但不能取它的地址或绑定引用：

```cpp error
#include <algorithm>

void f(int n) {
  [] { n = 1; };                         // error: n 未被捕获
  const int N = 10;
  [] { return N; };                      // OK：读常量的值，不是 odr-use
  [] { return std::max(N, 1); };         // error: max 按 const int& 接收，绑定引用是 odr-use
}
```

### 按引用捕获（¶12–¶13）

¶12 被捕获、但不是按值捕获的实体是**按引用捕获**（[[g:captured-by-reference|captured by reference]]）的。闭包类型是否为它们声明数据成员是未指定的 {{unspec}}；如果声明了，必须是字面类型，这保证按引用捕获的 lambda 也能在常量表达式里使用：

```cpp ok
static_assert([](int n) { return [&n] { return ++n; }(); }(3) == 4);
```

位域和匿名联合的成员不能按引用捕获，因为无法形成指向它们的引用。

¶13 lambda 体里使用一个按引用捕获的引用时，指代的是这个引用所绑定的对象，而不是引用本身。所以这样的捕获是否有效，看的是那个对象的生命周期（注 8）：

```cpp ok
auto h(int& r) {
  return [&] {
    ++r;   // h 返回后仍然有效，只要 r 绑定的对象还活着
  };
}
```

### 悬垂（¶17）

¶17 注 10：一个不是引用的实体被按引用捕获，在它的生命周期结束后再调用闭包，很可能导致未定义行为。说"很可能"，是因为只有真的访问了那个不存在的对象才是 UB（[[basic.life]]）。

```cpp run ub
#include <cstdio>
#include <functional>

std::function<int()> make() {
  int local = 42;
  return [&] { return local; };   // 按引用捕获局部变量
}

int main() {
  auto f = make();
  std::printf("%d\n", f());        // UB: local 已经不存在
}
```

本机用 `-fsanitize=address` 编译、设置 `ASAN_OPTIONS=detect_stack_use_after_return=1` 运行，AddressSanitizer 报告 `stack-use-after-return`。闭包只在当前作用域内同步使用时，`[&]` 安全且高效；一旦闭包被返回、存储或交给别的线程，就只应按值捕获，或者只按引用捕获确定活得更久的对象。

### init-capture（¶6）

¶6 init-capture `[x = e]` 如同声明一个变量 `auto x = e;` 并显式捕获它；`[&r = e]` 如同 `auto& r = e;`。它位于 lambda 的 lambda 作用域里（[[basic.scope.lambda]]），与普通变量相比有两点不同：按值时，这个变量和闭包里的成员是同一个对象，没有额外的拷贝和析构；按引用时，这个引用变量的生命周期在闭包对象的生命周期结束时结束。

注 2 指出，这使 `[x = std::move(x)]` 成为可能：等号右边的 `x` 指的是外层的变量，因为 init-capture 的名字在自己的初始化器里还不可见（这一点与普通变量 `int x = x;` 不同）。

```cpp run ok
#include <cstdio>

int main() {
  int x = 4;
  auto y = [&r = x, x = x + 1]() -> int {   // r 引用外部 x；内部 x 是 5
    r += 2;
    return x + 2;
  }();                                      // 外部 x 变为 6，y 初始化为 7
  std::printf("%d %d\n", x, y);             // 6 7

  auto counter = [i = 0]() mutable -> decltype(i) { return i++; };   // 返回 int
  counter();
  std::printf("%d\n", counter());           // 1
}
```

`decltype(i)` 写在尾置返回类型里也能找到 init-capture 的 `i`，因为 lambda 作用域包含整个声明符。这是 C++23 的 [[P2036R3]] 确立的规则。

init-capture 的 const 规则与简单捕获不同：`[x]` 保留 `x` 的 const，`[x = x]` 按 `auto` 推导去掉顶层 const，`[&x = x]` 按 `auto&` 推导保留 const。

### 嵌套 lambda（¶14）

¶14 内层 lambda `m2` 捕获了一个实体，而紧邻的外层 lambda `m1` 也捕获了它时：如果 `m1` 按值捕获，`m2` 捕获的是 `m1` 闭包里的那个成员（`m1` 不是 `mutable` 时这个成员视为 const）；如果 `m1` 按引用捕获，`m2` 捕获的是同一个原始实体。

标准例 11 输出 `123234`：

```cpp run ok
#include <iostream>

int main() {
  int a = 1, b = 1, c = 1;
  auto m1 = [a, &b, &c]() mutable {
    auto m2 = [a, b, &c]() mutable {
      std::cout << a << b << c;
      a = 4; b = 4; c = 4;
    };
    a = 3; b = 3; c = 3;
    m2();
  };
  a = 2; b = 2; c = 2;
  m1();
  std::cout << a << b << c << '\n';
}
```

推导过程如下：

1. 创建 `m1` 时，它复制了 `a`（值为 1），按引用持有外部的 `b`、`c`。随后外部的三个变量都变成 2。
2. 调用 `m1()`，在其中创建 `m2`。`m2` 的 `a` 复制自 `m1` 的成员（1）；`m1` 按引用捕获 `b`，所以 `m2` 复制的是外部 `b` 的当前值（2）；`c` 仍是外部的 `c`。
3. `m1` 把自己的 `a` 和外部的 `b`、`c` 改为 3，然后调用 `m2()`，输出 `m2` 的 `a`(1)、`b`(2) 和外部的 `c`(3)，即 `123`；再把自己的副本和外部的 `c` 改为 4。
4. 最后输出外部的 `a`(2)、`b`(3)、`c`(4)，即 `234`。

### 初始化顺序（¶15–¶16）

¶15 闭包成员的声明顺序是未指定的 {{unspec}}，但显式捕获对应的成员按捕获列表的顺序声明。¶16 求值 lambda 表达式时，按值捕获的实体用来直接初始化对应的成员，init-capture 按自己的初始化器初始化，顺序与成员的声明顺序一致。因此显式捕获按书写顺序初始化，析构顺序与之相反（注 9）。

```cpp ok
#include <utility>
#include <vector>

void f(std::vector<int>&& v) {
  [size = v.size(), own = std::move(v)] {};   // size 先初始化，拿到的是原来的大小
}
```

### 包和结构化绑定（¶18）

¶18 带 `...` 的简单捕获（`args...`、`&args...`）是包展开；带 `...` 的 init-capture（`...xs = std::move(args)`）是声明了一个 init-capture 包的包展开 {{c++20}}。

```cpp run ok
#include <cstdio>
#include <utility>

template<class... Args> int sum(Args... args) {
  auto l1 = [args...] { return (0 + ... + args); };                 // 按值捕获整个包
  auto l2 = [...xs = std::move(args)] { return (0 + ... + xs); };   // C++20：init-capture 包
  auto l3 = [&...rs = args] { return (0 + ... + rs); };             // C++20：按引用
  return l1() + l2() + l3();
}

int main() { std::printf("%d\n", sum(1, 2, 3)); }   // 18
```

`...` 的位置有规律：简单捕获里它在后面（`args...`），与一般的包展开一致；init-capture 里它在前面（`...xs = e`），与声明一个新包（`class... Ts`）一致。

结构化绑定是局部实体，C++20 起可以像变量一样按值或按引用捕获。指代位域的结构化绑定不能按引用捕获（¶12）。

```cpp ok
#include <utility>

void sb() {
  auto [p, q] = std::pair{1, 2};
  auto l  = [p, &q] { return p + q; };   // C++20 起 OK
  auto l2 = [=] { return p; };           // 隐式捕获也可以
}
```

### 契约断言不能引起捕获 [expr.prim.lambda.closure] {{c++26}}

¶10 如果一个被隐式捕获的局部实体，它的所有潜在引用都出现在调用运算符的契约断言（`pre`、`post`）或 lambda 体里的 `contract_assert` 中，程序非良构。注 4 说明了目的：给现有程序加上契约断言，不应导致额外的捕获，否则加一句断言就可能改变闭包的大小和布局。

```cpp
void test() {
  int i = 1;
  auto f2 = [=] pre(i > 0) {};   // error: 不能在这里隐式捕获 i
  auto f3 = [i] pre(i > 0) {};   // OK：显式捕获
  auto f5 = [=] {
    contract_assert(i > 0);      // OK：下面还引用了 i
    (void)i;
  };
}
```

本机 Clang 23 尚不支持契约语法，这段代码没有标判定。

## 转换为函数指针 [expr.prim.lambda.closure]

¶11 一个 lambda 如果不是泛型的、没有捕获、没有显式对象形参，并且约束（如果有）得到满足，它的闭包类型就有一个转换到函数指针的转换函数。函数指针的形参和返回类型与调用运算符相同；调用运算符不会抛出异常时，转换到 `noexcept` 函数指针。

调用运算符是静态成员函数时，转换得到的就是它的地址。否则得到某个函数 F 的地址，调用 F 的效果等同于在一个默认构造的闭包对象上调用调用运算符。

只有无捕获的 lambda 可以转换，因为函数指针只是一个地址，没有地方存放捕获的状态。

```cpp run ok
int (*fp)(int) = [](int i) { return i; };     // 隐式转换
void (*fnp)() noexcept = []() noexcept {};    // 转为 noexcept 函数指针
auto p = +[](int i) { return i * 2; };        // 一元 + 触发转换，p 的类型是 int(*)(int)

int main() { return fp(0) + p(0); }
```

¶12 无捕获的泛型 lambda 有一个转换函数模板。它从目标函数指针类型推导模板实参，再用推导出的特化确定返回类型（注 5，¶13）。标准例 7 展示了推导的边界：

```cpp error
void f1(int (*)(int))   { }
void f2(char (*)(int))  { }
void g(int (*)(int))    { }     // #1
void g(char (*)(char))  { }     // #2
void h(int (*)(int))    { }     // #3
void h(char (*)(int))   { }     // #4

auto glambda = [](auto a) { return a; };
void test() {
  f1(glambda);   // OK：a 推导为 int，返回 int
  f2(glambda);   // error: a 推导为 int 时返回 int，不是 char
  g(glambda);    // error: #1 和 #2 都可行，有歧义
  h(glambda);    // OK：只有 #3 可行
}
int& (*fpi)(int*) = [](auto* a) -> auto& { return *a; };   // OK
```

¶14 泛型 lambda 转换得到的函数也遵循 ¶11 的规则：静态时指向调用运算符模板的特化，否则指向一个转发函数。这会触发 lambda 函数体的实例化（注 6）。

¶15 转换函数是 public、constexpr、非 virtual、非 explicit、const 的，并且不抛出异常。转换本身总能在常量表达式里进行，但得到的函数指针能不能在常量表达式里调用，取决于调用运算符是不是 constexpr 函数：

```cpp error
auto Fwd = [](int (*fp)(int), auto a) { return fp(a); };
auto C  = [](auto a) { return a; };
static_assert(Fwd(C, 3) == 3);    // OK

auto NC = [](auto a) { static int s; return a; };   // 有静态局部变量，不可能是 constexpr
static_assert(Fwd(NC, 3) == 3);   // error: 不是常量表达式
```

## 特殊成员函数 [expr.prim.lambda.closure]

¶17 闭包类型的特殊成员函数：

| | 有捕获 | 无捕获 |
|---|---|---|
| 默认构造函数 | 没有 | 预置（defaulted）{{c++20}} |
| 拷贝、移动构造函数 | 预置 | 预置 |
| 拷贝赋值运算符 | 弃置（deleted） | 预置 {{c++20}} |
| 移动赋值运算符 | 不声明，赋值会选中弃置的拷贝赋值 | 预置 {{c++20}} |

这些函数照常隐式定义，因此可能被定义为弃置的（注 7）。例如按值捕获了一个 `std::unique_ptr`，拷贝构造函数就是弃置的，闭包只能移动。¶18 闭包类型有一个隐式声明的析构函数。

C++20 之前，所有闭包类型都不能默认构造和赋值。C++20 放开了无捕获的情形，再加上 lambda 可以出现在 `decltype` 里，就能把 lambda 的类型直接用作比较器或删除器：

```cpp run ok
#include <cstdio>
#include <memory>
#include <set>

int main() {
  using Cmp = decltype([](int a, int b) { return a > b; });
  std::set<int, Cmp> s{1, 3, 2};          // set 默认构造一个 Cmp
  std::printf("%d\n", *s.begin());        // 3

  std::unique_ptr<int, decltype([](int* p) { delete p; })> up(new int(1));
}
```

## 闭包类型的其他性质 [expr.prim.lambda.closure]

¶4 闭包类型不是聚合，所以不能用花括号初始化伪造一个闭包对象。它不是 final，所以可以从闭包类型派生，常见的 `overloaded` 写法就依赖这一点。当且仅当 lambda 没有任何捕获时，它是**结构化类型**（[[g:structural-type|structural type]]，[[temp.param]]），可以用作非类型模板实参。

!!! std
    The closure type is not an aggregate type and is not final; it is a structural type if and only if the lambda has no *lambda-capture*.

```cpp run ok
#include <cstdio>
#include <string>
#include <variant>

template<class... Fs> struct overloaded : Fs... { using Fs::operator()...; };

template<auto F> int call() { return F(); }   // 无捕获 lambda 作非类型模板实参

int main() {
  std::variant<int, std::string> v = std::string("hi");
  std::visit(overloaded{[](int i) { std::printf("int %d\n", i); },
                        [](const std::string& s) { std::printf("str %s\n", s.c_str()); }}, v);
  std::printf("%d\n", call<[] { return 42; }>());
}
```

¶4 后半段允许实现用不同于上述描述的方式定义闭包类型，只要可观察行为不变，例外是下面三项可以不同：闭包类型的大小和对齐、是否可平凡复制、是否是标准布局类。实现不能给闭包类型添加右值引用类型的成员。所以 `sizeof` 一个闭包、`std::is_trivially_copyable_v` 的结果，在不同编译器之间不保证一致。

<details class="fine" markdown="1"><summary>其余条文</summary>

¶3（[expr.prim.lambda.general]）*requires-clause* 可以以属性结尾，与 lambda 声明符前的属性冲突，例如 `[]<class T> requires T::operator int [[attr]] (int) {}`。标准规定这时属性一律归 lambda。注 2 指出，这样的歧义写法本来就没有合法语义，因为约束表达式的类型不会是 `bool`。

¶2（[expr.prim.lambda.closure]）闭包类型在 lambda 的函数体结束前是不完整的。

¶8（[expr.prim.lambda.closure]）是一个关于 constexpr lambda 的长例子，要点已在前文说明。

¶9（[expr.prim.lambda.closure]）注 3 说明，调用运算符可以用类型约束、`<…>` 后的 *requires-clause* 和尾置 *requires-clause* 加约束，与普通函数模板相同（[[temp.constr.decl]]）。

¶19（[expr.prim.lambda.closure]）闭包类型的成员不能被显式实例化、显式特化，也不能在友元声明中被指名。

</details>

## 实现视角

!!! impl
    - 主流实现把按值捕获实现为普通数据成员，按引用捕获通常每个存一个指针。本机 Clang 23 上，按引用捕获两个 `int` 的闭包 `sizeof` 为 16；无捕获的闭包是空类，`sizeof` 为 1。¶4 和 ¶12 也允许别的表示，例如只存一个栈帧指针。
    - Itanium C++ ABI 为 lambda 规定了名字修饰方式，使出现在 inline 函数、类定义等可以在多个翻译单元中重复定义的位置上的 lambda，在各个翻译单元里得到相同的闭包类型，这是满足 ODR 的前提（[[basic.def.odr]]）。
    - 对非静态的无捕获 lambda，编译器生成一个静态的转发函数，在里面构造一个空的闭包对象再调用 `operator()`，这就是 ¶11 里的 F。
    - Clang 的 `-Wunused-lambda-capture` 提示显式捕获了却没有 odr-use 的实体，例如常量。

## 历史与演进

!!! history
    - C++11 引入 lambda。返回类型推导只限单条 `return` 语句，只能捕获自动变量和 `this`。
    - C++14：泛型 lambda（`auto` 形参）；init-capture，用来捕获只能移动的对象；返回类型推导与普通函数统一。
    - C++17：constexpr lambda 和隐式 constexpr（[[P0170R1]]）；`[*this]` 按值捕获整个对象（[[P0018R3]]）。
    - C++20：模板形参列表（[[P0428R2]]）；无捕获 lambda 可以默认构造和赋值（[[P0624R2]]）；lambda 可以出现在未求值操作数中（[[P0315R4]]）；init-capture 包（[[P0780R2]]）；`[=, this]` 和弃用 `[=]` 隐式捕获 `this`（[[P0806R2]]）；捕获结构化绑定（[[P1091R3]]、[[P1381R1]]）；隐式捕获改为基于语法的规则（[[P0588R1]]），此前的规则以 odr-use 为基础，并为泛型 lambda 另设了复杂的特殊规则。
    - C++23：省略 `()` 的限制放宽（[[P1102R2]]）；`static` lambda（[[P1169R4]]）；显式对象形参（[[P0847R7]]）；声明符前的属性（[[P2173R1]]）；尾置返回类型可以看到捕获的名字（[[P2036R3]]）。
    - C++26：lambda 可以带契约，契约断言不得引起隐式捕获。

## 常见错误

!!! pitfall "每个 lambda 是不同的类型"
    `auto g = cond ? [k] { return 1; } : [k] { return 2; };` 非良构，两个分支是不同的类，互相不能转换。去掉捕获后 `cond ? [] { return 1; } : [] { return 2; }` 却是良构的：操作数是不同的类类型时，[[expr.cond]] 会尝试转换，而两个无捕获闭包都能转换为 `int(*)()`，结果类型就是这个函数指针。

!!! pitfall "常量不需要捕获，除非取地址或绑定引用"
    `const int N = 10; [] { return N * 2; }` 没有问题；`[] { return &N; }` 和 `[] { return std::max(N, 1); }` 都非良构，后者因为 `std::max` 按 `const T&` 接收参数。

## 思考题

!!! question "思考题 1"
    下面的 lambda 是否良构？在 Clang 上闭包对象的 `sizeof` 是多少？
    ```cpp
    void f() {
      const int N = 10;
      auto l = [=] { return N + 1; };
    }
    ```

<details markdown="1">
<summary>答案</summary>

良构。`N` 在 lambda 体里被潜在引用、潜在求值，并且在这里 odr-usable，所以按 [[expr.prim.lambda.capture#7]] 被隐式捕获，隐式捕获不要求 odr-use。但 `N + 1` 只读常量的值，不是 odr-use，按 [[expr.prim.lambda.capture#11]] 它指代外层的 `N`，而不是闭包成员，实现可以把这个捕获优化掉。本机 Clang 23 上 `sizeof(l)` 为 1。标准不保证这个大小（[[expr.prim.lambda.closure#4]]）。
</details>

!!! question "思考题 2"
    下面的代码输出什么？
    ```cpp
    int x = 1;
    auto l = [x]() mutable { return ++x; };
    auto l2 = l;
    l(); l();
    std::cout << l() << l2() << x;
    ```

<details markdown="1">
<summary>答案</summary>

输出 `421`。`l` 被调用三次，它的成员依次变为 2、3、4，第三次返回 4。`l2` 是在任何调用之前复制的，成员仍是 1，调用后返回 2。外部的 `x` 没有被修改，是 1。C++17 起 `<<` 的左操作数先于右操作数求值，所以顺序是确定的。闭包对象就是一个普通对象，复制它就复制了全部捕获的状态。
</details>
