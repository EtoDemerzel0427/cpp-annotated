---
title: 基本表达式
summary: 表达式文法最底层的成分，以及其中三种的规则：字面量的值类别、this 能出现在哪里和它的类型、括号表达式。
status: done
covers: expr.prim.grammar, expr.prim.literal, expr.prim.this, expr.prim.paren
related: expr.prim.id, expr.prim.lambda, expr.prim.fold, expr.prim.req, expr.prim.splice, basic.lval, dcl.type.decltype
tags: 表达式, 值类别, this
updated: 2026-10-19
---

!!! tldr
    - 字符串字面量是 lvalue，因为它指代一个真实存在的数组对象；用户定义字面量的值类别取决于对应的 `operator""` 返回什么；其余字面量都是 prvalue。
    - `this` 是一个 prvalue 指针，类型是指向 cv `X` 的指针：只跟成员函数的 cv 限定符有关，与引用限定符无关。
    - `this` 只能出现在隐式对象成员函数中 cv 限定符之后的部分，以及默认成员初始化器里；静态成员函数和显式对象成员函数中不能出现。
    - lambda 不引入类作用域，局部类会引入，这决定了 `this` 指向哪个对象。
    - `(E)` 与 `E` 的类型和值类别完全相同，只在少数上下文里含义不同，最常见的是 `decltype((x))` 和 `return (x);`。

**基本表达式**（primary expression）是表达式文法的最底层：后缀表达式（[[expr.post]]）、一元表达式（[[expr.unary]]）层层往上，最终都落到某个基本表达式上。它们不由运算符组合而成，是所有运算符的操作数的起点。

[expr.prim] 一节把八种不同的东西放在一起：

| 文法分支 | 例子 | 讲解 |
|---|---|---|
| *literal* | `42`、`"abc"`、`1.5_km` | 本页 |
| `this` | `this` | 本页 |
| `( expression )` | `(x)` | 本页 |
| *id-expression* | `x`、`N::x`、`~T`、`ts...[0]` | [[expr.prim.id]] |
| *lambda-expression* | `[&](int i) { return i + n; }` | [[expr.prim.lambda]] |
| *fold-expression* | `(... + args)` | [[expr.prim.fold]] |
| *requires-expression* | `requires (T t) { t + t; }` | [[expr.prim.req]] |
| *splice-expression* {{c++26}} | `[: ^^x :]` | [[expr.prim.splice]] |

它们的共同点只在文法上：都能直接作为 `()`、`[]`、`.`、`->` 等后缀运算符的左操作数，不必加括号。所以 lambda 可以写完立刻调用（`[]{ return 1; }()`），`requires { ... } && C<T>` 也不需要括号。

本页的规则大多在回答两个问题：这个表达式是什么类型，属于哪种值类别。值类别（[[basic.lval]]）把表达式分成 lvalue（指代一个有身份的对象或函数，可以取地址）、xvalue（即将被移走的对象）和 prvalue（只是一个值，用来初始化对象）。

## 文法 [expr.prim.grammar]

文法只有一条产生式，列出上表的八个分支。有三点值得注意。

*id-expression* 也会出现在 `.` 和 `->` 之后（[[expr.ref]]），那时它是成员访问的一部分，不是独立的基本表达式。所以 [[expr.prim.id]] 的许多规则要特意排除这种情形。

折叠表达式的括号是它自身文法的一部分，不属于 `( expression )` 分支，`... + args` 不加括号不是表达式。

*requires-clause* 中只能直接写某些基本表达式（[[temp.pre]]），所以写一个临时的约束时要用 `requires requires { ... }`：第一个 `requires` 引入子句，第二个开始一个 *requires-expression*（见 [[expr.prim.req]]）。

## 字面量 [expr.prim.literal]

¶1 字面量的类型由它的写法决定，规则在词法一章 [[lex.literal]]：`42` 是 `int`，`42u` 是 `unsigned int`，`'a'` 是 `char`，`1.0f` 是 `float`，`nullptr` 是 `std::nullptr_t`。本条补充的是值类别：

| 字面量 | 值类别 |
|---|---|
| 字符串字面量 | lvalue，指代一个静态存储期的数组对象（[[lex.string]]） |
| 用户定义字面量 | 与 [[lex.ext]] 改写成的 `operator""` 调用相同 |
| 其他字面量 | prvalue |

字符串字面量是 lvalue，因为它确实是一个对象：`"abc"` 是一个 `const char[4]` 数组，有地址，可以绑定到 `const char(&)[4]`。`42` 只是一个值，在被物化为临时对象（[[conv.rval]]）之前不占存储。

```cpp run ok
#include <type_traits>

static_assert(std::is_same_v<decltype("ab"), const char(&)[3]>);  // lvalue：decltype 给出 T&
static_assert(std::is_same_v<decltype(42), int>);                  // prvalue：不带引用
static_assert(std::is_same_v<decltype(u8"x"), const char8_t(&)[2]>);
static_assert(std::is_same_v<decltype(nullptr), std::nullptr_t>);

const char (*p)[4] = &"abc";   // OK：可以对字符串字面量取地址
// int* q = &42;               // error: 不能对 prvalue 取地址

int main() { }
```

两次求值同一个字符串字面量是否得到同一个对象，两个不同的字符串字面量是否共享存储（例如 `"abc"` 与 `"bc"` 的尾部重叠），都是未指定的（[[lex.string]]）。所以不要比较字符串字面量的地址。GCC 和 Clang 默认把内容相同的字面量合并到一处，这只是实现的选择。

用户定义字面量会被改写成对 `operator""` 的函数调用，值类别就是那次调用的值类别：

```cpp run ok
#include <type_traits>

struct Reg { int v; };
Reg  table[4];
Reg& operator""_reg(unsigned long long i) { return table[i]; }
Reg  operator""_val(unsigned long long i) { return Reg{int(i)}; }

static_assert(std::is_same_v<decltype(2_reg), Reg&>);  // 返回左值引用：lvalue
static_assert(std::is_same_v<decltype(2_val), Reg>);   // 返回值：prvalue

int main() { (3_reg).v = 7; }   // 对 lvalue 的成员赋值
```

!!! pitfall "`3_reg.v` 不是成员访问"
    预处理数（pp-number，[[lex.ppnumber]]）可以包含 `.` 和标识符字符，所以 `3_reg.v` 整个被切成一个记号，成了后缀为 `_reg.v` 的用户定义字面量，找不到对应的字面量运算符而报错。写成 `(3_reg).v` 或 `3_reg .v` 即可。伪析构调用 `0.T::~T()` 是同一个问题（[[expr.prim.id.dtor]]）。

## this [expr.prim.this]

```cpp error
struct Y {
  static void s() { (void)this; }        // error: 静态成员函数
  void e(this Y& self) { (void)this; }   // error: 显式对象成员函数，应使用 self
  void d(Y* p = this);                   // error: 默认实参
  static auto t() -> decltype(this);     // error: 静态成员函数的声明
};
```

`this` 能出现的位置很少，下面先说它指向谁，再说它在哪里有效、是什么类型。

### this 指向谁

¶1 关键字 `this` 是一个指针，指向两种对象之一：正在调用的**隐式对象成员函数**（implicit object member function，即传统的非静态成员函数，[[class.mfct.non.static]]）所作用的对象，或者正在求值其默认成员初始化器（[[class.mem]]）的对象。

`this` 是 prvalue，不是变量：不能给它赋值，也不能写 `&this`。

¶2 某一点的[[g:current-class|**当前类**]]（current class）是包含该点的最内层类作用域所属的类。注 1 指出，lambda 表达式不引入类作用域。所以成员函数里的 lambda，函数体中的当前类仍是外层的类，不是闭包类型，lambda 体内捕获的 `this` 指向外层对象（[[expr.prim.lambda.closure]]）。局部类则会引入新的类作用域，在成员函数内定义的 `struct Inner` 中，`this` 是 `Inner*`。

### 在成员函数中的类型和有效范围

¶4 在类 `X` 的成员函数（或成员函数模板）的声明里，如果 `X` 是当前类，那么从可选的 cv 限定符之后，到函数定义或声明符结束，`this` 是类型为指向 cv `X` 的指针的 prvalue。

```cpp run ok
#include <type_traits>

struct X {
  void f()            { static_assert(std::is_same_v<decltype(this), X*>); }
  void g() const      { static_assert(std::is_same_v<decltype(this), const X*>); }
  void h() volatile & { static_assert(std::is_same_v<decltype(this), volatile X*>); }  // & 不影响
  auto k() -> decltype(this) { return this; }   // OK：尾置返回类型在 cv 之后
  int  n = sizeof(*this);                       // OK：默认成员初始化器
  X*   self = this;                             // OK
};
static_assert(std::is_same_v<decltype(&X::k), X* (X::*)()>);

int main() { }
```

`this` 的类型只带 cv 限定，不带引用限定：`void f() const &&` 里 `this` 仍是 `const X*`。引用限定符只影响重载决议时隐式对象形参的类型（[[over.match.funcs]]），`*this` 本身总是 lvalue。

有效范围从 cv 限定符之后开始，所以尾置返回类型和 `noexcept` 说明里可以用 `this`，形参列表里不行，`void d(Y* p = this)` 非良构（[[dcl.fct.default]] 也另行禁止在默认实参中使用 `this`）。

¶4 还规定，`this` 不得出现在当前类的静态成员函数或显式对象成员函数（[[dcl.fct]]，即 C++23 的 deducing this）的声明中。条文先说 `this` 在这些函数中的类型和值类别有定义，再禁止它出现。注 2 解释了原因：要读完整个声明符才能匹配到之前的声明。类外定义 `auto X::f() -> decltype(this)` 不带 `static`，编译器读到 `decltype(this)` 时还不知道 `f` 是不是静态函数，只能先按普通成员函数确定类型，事后再检查。

!!! note "显式对象成员函数为什么禁止 this"
    `void f(this Self&& self)` 中，调用的对象经 `self` 传入，`Self` 可能推导为派生类。如果同时允许 `this`，它该是 `X*` 还是 `Self*`？对派生类对象调用时两者会不一致。禁止 `this`、一律通过 `self` 访问，就没有歧义。同理，函数体里的裸成员名 `m` 也不会变成 `this->m`，必须写 `self.m`（[[expr.prim.id.general#2]]）。

注 3 说明了尾置返回类型的一个细节：这时类还不完整，但仍可以做成员访问，只是看不到后面才声明的成员。

```cpp ok
struct A {
  char g();
  template<class T> auto f(T t) -> decltype(t + g())  // g() 即 this->g()
    { return t + g(); }
};
template auto A::f(int t) -> decltype(t + g());       // 类外显式实例化
```

### 在默认成员初始化器中

¶5 在非静态数据成员的默认成员初始化器里，`this` 是 `X*`，不带 cv，因为构造期间对象还不是 const（[[class.ctor]]）。所以 `X* self = this;`、`Callback cb{this};` 都合法。范围只限于初始化器，数组边界 `int a[sizeof(*this)];` 不在其中。

### 其余位置一律禁止

¶6 除了上面两种位置，`this` 不得出现。标准的例子：

```cpp error
class Outer {
  int a[sizeof(*this)];               // error: 不在成员函数内
  unsigned int sz = sizeof(*this);    // OK：默认成员初始化器

  void f() {
    int b[sizeof(*this)];             // OK：在 Outer::f 内

    struct Inner {
      int c[sizeof(*this)];           // error: 不在 Inner 的成员函数内
    };
  }
};
```

`Inner` 虽然写在 `Outer::f` 的函数体里，但当前类已经变成 `Inner`，`Inner` 的数组边界不属于上面两种位置。¶4 只在 `X` 是当前类时给出 `this`，所以 `Outer::f` 的 `this` 不会延伸到局部类里。

lambda 不引入类作用域，lambda 体里的 `this` 仍来自外层成员函数，但必须捕获（[[expr.prim.lambda.capture]]）：

```cpp error
struct Z {
  int v = 0;
  void f() {
    auto l1 = [this] { return v; };            // OK：v 即 this->v
    auto l2 = []     { return v; };            // error: this 未被捕获
    struct Inner { int x = sizeof(*this); };   // OK：this 是 Inner*
  }
};
```

### 契约断言中的 this {{c++26}}

¶3 C++26 的契约断言（[[basic.contract.general]]，即 `pre`、`post` 和 `contract_assert`）只应观察程序状态，不应修改它。所以如果 `this` 出现在契约断言的谓词中，并且当前类包围这个断言，`this` 的类型要额外加上 `const`。隐式变换出来的 `this` 也算（谓词里写 `m` 实际上是 `(*this).m`，见 [[expr.prim.id.general#2]]），嵌套 lambda 体内的也算。

于是即便在非 const 成员函数中，`pre(mutate())` 也非良构，因为它通过 `const X*` 调用了非 const 成员函数。谓词中命名的外部变量同样按 const 处理，见 [[expr.prim.id.unqual#7]]。截至写作时，本机 Clang 23 还不支持契约，这条规则无法在本地验证。

## 括号表达式 [expr.prim.paren]

¶1 `(E)` 是一个基本表达式，类型、结果和值类别都与 `E` 相同，能用 `E` 的地方都能用它，含义也相同，除非另有说明。

括号只改变分组，不改变表达式本身。所以 `(x)` 和 `x` 都是 lvalue，`(std::move(x))` 仍是 xvalue，`return (x);` 仍会隐式移动（[[expr.prim.id.unqual#15]] 明确写了可以加括号）。位域也一样，`int& r = (b.bf);` 和 `int& r = b.bf;` 同样非良构。

值得记住的是那句除非另有说明。下面是括号会改变含义的几个地方：

| 上下文 | 不加括号 | 加括号 | 出处 |
|---|---|---|---|
| `decltype` | `decltype(x)`：`x` 的声明类型 | `decltype((x))`：按表达式算，lvalue 得 `T&` | [[dcl.type.decltype]] |
| `decltype(auto)` | `return x;` 推导为 `T` | `return (x);` 推导为 `T&` | [[dcl.type.auto.deduct]] |
| 成员指针 | `&S::m` 是 `int S::*` | `&(S::m)` 在 `S` 的成员函数内是 `int*`，在其他地方非良构 | [[expr.unary.op]] |
| 函数调用 | `f(a)` 做实参依赖查找（ADL） | `(f)(a)` 不做 ADL | [[basic.lookup.argdep]] |
| 模板实参 | `A<1>2>` 解析失败 | `A<(1>2)>` OK | [[temp.names]] |
| splice 作模板实参 {{c++26}} | `e<[:r:]>` 非良构 | `e<([:r:])>` OK | [[expr.prim.splice#1]] |

```cpp run ok
#include <type_traits>

int x = 0;
static_assert(std::is_same_v<decltype(x),   int>);    // 实体的声明类型
static_assert(std::is_same_v<decltype((x)), int&>);   // (x) 是 int 类型的 lvalue

decltype(auto) r1() { return x; }     // int
decltype(auto) r2() { return (x); }   // int&
static_assert(std::is_same_v<decltype(r1()), int>);
static_assert(std::is_same_v<decltype(r2()), int&>);

struct S {
  int m;
  void k() {
    auto p = &(S::m);                 // 等价于 &(this->m)
    static_assert(std::is_same_v<decltype(p), int*>);
  }
};
int S::* pm = &S::m;                  // 不带括号：成员指针

int main() { }
```

```cpp error
namespace N { struct A {}; void f(A) {} }
struct S { int m; };

void g() {
  N::A a;
  f(a);        // OK：ADL 找到 N::f
  (f)(a);      // error: 括号抑制 ADL，普通查找找不到 f
}
auto q = &(S::m);   // error: 不在成员函数中，S::m 不能这样用
```

!!! tip "`(std::max)(a, b)`"
    Windows 头文件把 `max` 定义成函数式宏，而函数式宏只在名字后面紧跟 `(` 时展开。写成 `(std::max)(a, b)` 就避开了宏。这是预处理层面的效果，不是本条的规则。

!!! lawyer "括号与声明"
    在最令人烦恼的解析（most vexing parse）中，`T x((T()));` 多加一层括号，是为了让它不可能被解析为函数声明（[[stmt.ambig]]、[[dcl.ambig.res]]）。这解决的是声明与表达式之间的歧义；一旦确定是表达式，括号就不再改变任何东西。

## 实现视角

!!! impl
    Itanium C++ ABI（Linux、macOS 上的 GCC 和 Clang）和 MSVC 都把 `this` 当作隐藏的第一个参数传递，x86-64 System V 中就是 `rdi`。显式对象成员函数的 `self` 是普通的第一个参数，可以按值传递（`this Self self`），这时调用方式与传 `this` 指针完全不同。

## 历史

!!! history
    早期的 C++ 允许给 `this` 赋值来自定义对象的分配，后来由重载 `operator new` 取代，`this` 也就成了不可赋值的 prvalue。C++11 引入默认成员初始化器、尾置返回类型和 lambda，`this` 能出现的位置随之增加，`decltype((x))` 与 `decltype(x)` 的区分也始于 C++11。C++14 的 `decltype(auto)` 让 `return (x);` 的区别进入日常代码。C++23 引入显式对象成员函数并禁止其中出现 `this`。C++26 让契约谓词中的 `this` 带 const，并加入 splice 表达式。

## 常见误解

!!! pitfall "`return (local);` 返回悬垂引用"
    ```cpp
    decltype(auto) get() {
      int local = 42;
      return (local);   // 推导为 int&，指向已销毁的局部变量
    }
    ```
    Clang 对这个简单情形会给出 `-Wreturn-stack-address` 警告，但经过成员访问或结构化绑定之后就不一定能发现。

!!! pitfall "`&&` 限定的成员函数里 `*this` 也是 lvalue"
    想把自身作为右值转发出去，要写 `std::move(*this)`。C++23 起可以改用显式对象形参：`void f(this Self&& self)`，再 `std::forward<Self>(self)`。

## 思考题

!!! question "1. 下面哪几行良构？"
    ```cpp
    struct A {
      int v;
      auto f() const -> decltype((v));            // #1
      auto g() -> decltype(this->v);              // #2
      static auto h() -> decltype(sizeof(v));     // #3
    };
    ```

<details markdown="1">
<summary>答案</summary>

`#1` 良构。`v` 变换为 `(*this).v`（[[expr.prim.id.general#2]]），位于 `const` 之后，`this` 是 `const A*`，所以 `decltype((v))` 是 `const int&`。

`#2` 良构。`decltype` 作用于不加括号的成员访问，给出成员的声明类型 `int`。

`#3` 按当前草案非良构。`v` 是当前类 `A` 自己的成员，[[expr.prim.id.general#2]] 的条件 (2.1) 成立，即使在未求值操作数里也会变换成 `(*this).v`，而这在静态成员函数中非良构。Clang 23 拒绝 `#3`，却接受函数体中的 `static int h2() { return sizeof(v); }`，详见 [[expr.prim.id]]。没有争议的写法是 `sizeof(std::declval<A&>().v)`，或者直接写类型。
</details>

!!! question "2. 既然 `(E)` 与 `E` 的类型和值类别都相同，为什么 `decltype((x))` 与 `decltype(x)` 不同？"

<details markdown="1">
<summary>答案</summary>

`decltype` 有两套规则（[[dcl.type.decltype]]）：操作数是不加括号的 *id-expression* 或类成员访问时，给出所命名实体的声明类型；否则按表达式的类型和值类别计算，lvalue 得 `T&`。`x` 与 `(x)` 作为表达式完全相同，都是 `int` 类型的 lvalue；区别在于 `decltype` 看的是语法形式。这正是 ¶1 中除非另有说明所指的例外。
</details>
