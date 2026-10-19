---
title: 重载运算符
summary: 哪些运算符可以重载，运算符函数要怎样声明：形参个数、能否是成员或静态成员、能否有默认实参，以及 ->、后缀 ++ 这几种特殊形式。
status: draft
covers: *
since: c++98
papers: P0145R3, P0847R7, P1169R4, P2589R1, P2128R6, P1161R3, P3668R4
related: over.match.oper, over.built, over.call.object, class.copy.assign, class.compare.default, expr.unary.op, expr.sub, expr.ref, expr.post.incr, basic.stc.dynamic, expr.await
tags: 重载, 运算符
updated: 2026-10-19
---

!!! tldr
    - 运算符函数是名字形如 `operator@` 的函数。表达式 `a @ b` 选中它之后，改写成 `a.operator@(b)` 或 `operator@(a, b)` 这样的普通调用。
    - 运算符函数至少要有一个类或枚举类型（或其引用）的形参，所以 `int + int` 的含义永远不能改；优先级、结合性和操作数个数也不能改。
    - `.`、`.*`、`::`、`?:` 不能重载。`&&`、`||`、`,` 可以重载，但重载之后不再短路。
    - `=`、`()`、`[]`、`->` 必须是成员函数。只有 `()` 和 `[]` 可以有默认实参和任意多个形参，C++23 起还可以是静态成员。
    - `x->m` 会对 `operator->` 的返回值反复套用 `->`，直到得到原生指针；后缀 `++` 靠一个 `int` 哑形参与前缀 `++` 区分。

这一页讲运算符函数的声明：形参该有几个，能不能是成员、静态成员，能不能有默认实参。表达式 `a @ b` 出现时，怎样在成员、非成员和内建运算符之间选择，由 [[over.match.oper]] 规定；参与竞争的内建运算符清单在 [[over.built]]。

## 运算符函数 [over.oper.general]

```cpp run ok
struct V { int x, y; };
V operator+(V a, V b) { return {a.x + b.x, a.y + b.y}; }
int main() {
  V a{1, 2}, b{3, 4};
  V c = a + b;             // 改写为 operator+(a, b)
  V d = operator+(a, b);   // 也可以直接按函数名调用
  return c.x - d.x;        // 0
}
```

¶1 声明符名字是 *operator-function-id*（关键字 `operator` 加一个运算符）的声明，必须声明函数、函数模板，或者函数模板的显式实例化、显式特化。这样声明的函数叫**运算符函数**（[[g:operator-function|operator function]]），函数模板叫运算符函数模板，它的特化也是运算符函数。所以 `int operator+;` 这样的变量声明是非良构的。

可以跟在 `operator` 后面的运算符一共 44 个：

```text
new  delete  new[]  delete[]  co_await  ()  []  ->  ->*
~  !  +  -  *  /  %  ^  &  |  =  +=  -=  *=  /=  %=  ^=  &=  |=
==  !=  <  >  <=  >=  <=>  &&  ||  <<  >>  <<=  >>=  ++  --  ,
```

其中 `new[]`、`delete[]`、`()`、`[]` 由不止一个记号组成（注 1），所以 `operator ( )` 中间可以有空白。¶2 规定 `+`、`-`、`*`、`&` 的一元和二元形式都可以重载，两者同名，靠形参个数区分。

¶4 运算符函数通常由运算符表达式隐式调用，也可以像上面的 `operator+(a, b)` 那样显式调用。显式调用是普通的函数调用（[[over.call.func]]），不经过 [[over.match.oper]]，所以没有内建候选，也没有 C++20 的改写候选。

¶5 `operator new`、`operator new[]`、`operator delete`、`operator delete[]` 完全由 [[basic.stc.dynamic]] 规定，¶6 `co_await` 完全由 [[expr.await]] 规定。本节其余的限制对它们不适用。例如 `operator new(std::size_t)` 没有任何类类型形参，类内的 `operator new` 隐式是静态成员。

### 不能重载的运算符

¶3 的注 2 列出了不能重载的运算符：`.`、`.*`、`::`、`?:`，以及预处理运算符 `#`、`##`。`sizeof`、`typeid`、各种 `*_cast`、反射运算符 `^^` 等根本不在 ¶1 的清单里，自然也不能重载。

这几个运算符各有不能重载的理由：

- `::` 在编译期解析名字，它的左边不是一个值。
- 如果 `.` 和 `.*` 可以重载，就没有可靠的办法访问对象本身的成员了。
- `?:` 只求值两个分支中的一个，而函数调用会求值所有实参。

### 不能改变内建类型上的运算（¶7）

<div class="compare" markdown="1">

```cpp error
// error: 没有类或枚举类型的形参
int operator+(int, int);
```

```cpp ok
enum class C {};
C operator~(C);   // OK：枚举
struct S {};
S operator-(S, int);   // OK：类
```

</div>

¶7 运算符函数至少要有一个函数形参或隐式对象形参，类型是类、枚举，或者它们的引用。指针不算：`int operator+(C*, int)` 同样非良构。成员函数自动满足这一条，因为它的隐式对象形参是 `X&` 一类的类型。

这条规则和 [[over.match.oper#1]] 一起保证，只要所有操作数都不是类或枚举类型，运算符就一定是内建的。函数模板 `template<class T> int operator-(T*, T*);` 本身可以声明，但 `p - p`（`int*`）根本不做重载决议，这个模板永远用不上。

¶7 接着规定，运算符的优先级、结合性和操作数个数都不能改。`=`、一元 `&`、`,` 对每种类型都有预定义的含义，可以为特定的类重新定义；一元 `&` 和 `,` 也可以为特定的枚举重新定义。枚举的 `=` 不能重新定义，因为 `operator=` 必须是成员，而枚举没有成员。

运算符函数和其他成员函数一样会被派生类继承。唯一的例外在效果上是 `operator=`，它总被派生类隐式声明的复制赋值隐藏（见下文 [over.assign]）。

!!! lawyer "显式对象形参与 ¶7"
    ¶7 说的是函数形参或隐式对象形参。C++23 的显式对象成员函数没有隐式对象形参，`this` 形参只是普通的函数形参。所以 `struct S { int operator+(this int, int); };` 的两个形参都是 `int`，按 ¶7 非良构。截至写作时，Clang 23 不诊断这一点。

### 形参个数与默认实参（¶8–¶11）

¶8 运算符函数必须是以下几种之一：前缀一元、二元、函数调用、下标、类成员访问、自增、自减运算符函数，后面各小节分别定义它们。`!` 和 `~` 没有二元形式，所以 `operator!(S, S)` 非良构。

¶10 形参个数必须恰好是运算符需要的个数，而且不能有默认实参，例外只有 `operator()` 和 `operator[]`。如果允许默认实参，`operator-(S = S{})` 既可以当一元也可以当零元，后缀 `operator++(int = 0)` 也会和前缀版本分不清。

```cpp
struct S {
  void operator+(int = 0);    // error: 不能有默认实参
  void operator()(int = 0);   // OK：函数调用运算符例外
  int  operator[](int = 0);   // OK：下标运算符例外
  void operator-(int, int);   // error: 成员二元 - 只能有一个非对象形参
};
```

¶11 后面没有单独规定的运算符，都按普通一元、二元运算符处理。所以 `->*`、`&&`、`||`、`,`、复合赋值 `+=` 等、`<=>` 都可以是非成员。单独规定、要求是成员的只有 `=`、`()`、`[]`、`->`。

¶9 的注 3 提醒，内建运算符之间的恒等关系对运算符函数不必成立。语言不会从 `+` 推出 `+=`；对基本类型 `++a` 等价于 `a += 1`，对类类型不一定。内建 `+=` 要求左操作数是左值，运算符函数也没有这个要求。

## 一元与二元运算符 [over.unary] [over.binary]

### 成员还是非成员

```cpp run ok
struct Num {
  int v;
  Num(int x) : v(x) {}
  friend Num operator+(Num a, Num b) {
    return a.v + b.v;
  }
};
int main() {
  Num a = 1;
  Num b = 2 + a;   // OK：两边都可以经 Num(int) 转换
  return b.v - 3;
}
```

[over.unary] ¶1 **前缀一元运算符函数**（[[g:prefix-unary-operator-function|prefix unary operator function]]）是没有非对象形参的非静态成员函数，或者恰有一个形参的非成员函数。`@x` 选中成员时解释为 `x.operator@()`，选中非成员时解释为 `operator@(x)`。

[over.binary.general] ¶1 **二元运算符函数**（[[g:binary-operator-function|binary operator function]]）是恰有一个非对象形参的非静态成员函数，或者恰有两个形参的非成员函数。`x @ y` 选中成员时解释为 `x.operator@(y)`，选中非成员时解释为 `operator@(x, y)`。这里的非静态成员也包括 C++23 的显式对象成员函数（[[P0847R7]]），它的 `this` 形参算对象形参。

成员版本的左操作数对应对象形参，不允许经用户定义转换得到（[[over.best.ics#9]]）。如果上例把 `operator+` 写成成员，`a + 2` 可以编译，`2 + a` 就不行。需要两边对称转换的运算符应写成非成员，最好像上例那样写成**隐藏友元**：只在类内定义的友元函数，只能经实参依赖查找（ADL）找到，不会混进外层作用域的重载集。

二元运算符不能是静态成员函数。静态成员没有对象形参，只剩一个形参，左操作数无处安放。

```cpp
struct S {
  static int operator+(S, S);   // error: 不能是静态成员
  int operator+(this S, int);   // OK：显式对象形参
};
```

### 一元和二元同名

[over.unary] ¶2 的注 2 指出，同一个运算符的一元形式和二元形式同名，所以一元版本可以隐藏外层作用域的二元版本，反之亦然：

```cpp error
namespace A { struct S {}; }
A::S operator-(A::S, A::S);     // 全局的二元 -
namespace B {
  void operator-(A::S);         // B 中的一元 -
  void f(A::S x) { x - x; }     // error: 非限定查找停在 B，只找到一元版本
}
```

非限定查找在命名空间 `B` 找到 `operator-` 就停下了，全局的二元版本被隐藏；ADL 只查找 `S` 所在的命名空间 `A`，那里什么也没有。把二元 `operator-` 放进 `A`，ADL 就能找到它。这是把运算符和类型放在同一个命名空间的理由之一。

### 比较运算符函数

[over.binary.general] ¶2 定义了几个术语，供 [[class.compare.default]] 等处使用：实现 `==`、`!=` 的是相等运算符函数，实现 `<`、`>`、`<=`、`>=` 的是关系运算符函数，实现 `<=>` 的是三路比较运算符函数，三者合称**比较运算符函数**（[[g:comparison-operator-function|comparison operator function]]）。除了特殊成员函数，只有比较运算符函数和下文的后缀自增、自减可以 `= default`。

### `&&`、`||`、`,` 和一元 `&`

这几个运算符的内建版本有特殊语义：`&&` 和 `||` 短路，`,` 先求值左操作数再丢弃它，一元 `&` 取地址。重载之后，表达式变成一次函数调用，两个操作数都会求值：

```cpp run ok
#include <cstdio>
struct B { bool v; };
bool operator&&(B a, B b) { return a.v && b.v; }
B make(bool v, const char* s) { std::puts(s); return {v}; }
int main() {
  bool r = make(false, "left") && make(true, "right");   // 打印 left、right：没有短路
  return r;
}
```

C++17 起，重载运算符的操作数按对应内建运算符的规则排序（[[P0145R3]]，[[over.match.oper#2]]），所以至少左操作数先于右操作数求值。

一元 `&` 被重载之后，`&obj` 不再能取得地址，标准库为此提供了 `std::addressof`。泛型代码里的 `a, b` 也可能调用到用户的 `operator,`，惯用的防御写法是 `(void)a, b`：`void` 类型的操作数不能传给任何函数，只能使用内建逗号（[[over.match.oper#13]]）。

```cpp run ok
#include <memory>
struct Evil { int operator&() const { return 0; } };
int main() {
  Evil e;
  auto a = &e;                   // 调用 Evil::operator&，a 是 int
  Evil* p = std::addressof(e);   // 真正的地址
  static_assert(__is_same(decltype(a), int));
  return p ? 0 : 1;
}
```

## 赋值 [over.assign]

¶1 **简单赋值运算符函数**是名为 `operator=` 的二元运算符函数，必须是非静态成员函数。

为什么不能是非成员？每个类都隐式声明复制赋值运算符。如果允许非成员的 `operator=`，同一个 `a = b` 在它声明之前和之后可能调用不同的函数，类的作者也就无法掌控自己类型的赋值语义。

注 1 补充，赋值的左操作数只考虑标准转换序列（[[over.match.oper#5]]），所以左操作数是类类型时，`x = y` 总是解释为 `x.operator=(y)`，内建赋值永远选不中：

```cpp
struct S {};
void operator=(S&, int);              // error: 必须是非静态成员函数
struct T { static T& operator=(int); };   // error: 不能是静态成员
struct R { operator int&(); };
void g(R r) { r = 5; }                // error: 内建 int& = int 不可行，R 也没有接受 int 的 operator=
```

¶2 的注 2：派生类总会隐式声明自己的复制赋值运算符，它隐藏了基类所有的 `operator=`。要用基类的版本，必须写 `using Base::operator=;`。

```cpp
struct B { B& operator=(int); };
struct D : B {};
struct D2 : B { using B::operator=; };
void f(D d, D2 d2) {
  d2 = 1;   // OK：B::operator=(int) 经 using 声明可见
  d = 1;    // error: 被 D 的隐式复制、移动赋值隐藏，而 1 不能转换为 D
}
```

¶3 的注 3：任何赋值运算符，包括复制、移动赋值，都可以是虚函数。但派生类 `D` 的复制赋值不会覆盖基类 `B` 的虚复制赋值，因为前者的形参是 `const D&`，后者是 `const B&`：

```cpp run ok
#include <cstdio>
struct B {
  virtual int operator=(int) { return 0; }
  virtual B& operator=(const B&) { std::puts("B::operator=(const B&)"); return *this; }
};
struct D : B {
  int operator=(int) override { std::puts("D::operator=(int)"); return 1; }
  D& operator=(const B&) override { std::puts("D::operator=(const B&)"); return *this; }
};
int main() {
  D d1, d2;
  B* bp = &d1;
  *bp = 99;   // 虚调用 D::operator=(int)
  *bp = d2;   // 虚调用 D::operator=(const B&)
  d1 = d2;    // 隐式声明的 D::operator=(const D&)，它对基类子对象调用 B::operator=(const B&)
}
```

最后一行打印 `B::operator=(const B&)`：`d1 = d2` 选中的是隐式声明的 `D::operator=(const D&)`，绕过了专门写好的虚函数。多态的赋值很容易出这种意外。

## 函数调用 [over.call]

¶1 **函数调用运算符函数**是名为 `operator()` 的成员函数，形参个数任意，可以有默认实参。对类类型的 `f(args)`，由 [[over.call.object]] 做重载决议。

候选除了 `operator()`，还有**代理调用函数**（surrogate call function）：类如果有到函数指针或函数引用的转换函数，每个这样的转换函数都会生成一个候选。选中代理调用函数时，先调用转换函数得到 `e`，表达式解释为 `e(args)`；否则解释为 `f.operator()(args)`。

```cpp run ok
#include <cstdio>
using F = int (*)(int);
int twice(int x) { return 2 * x; }
struct Conv { operator F() const { return twice; } };   // 产生代理调用函数
struct Adder { int operator()(int a, int b = 10) const { return a + b; } };
struct Stateless { static int operator()(int x) { return x + 1; } };   // C++23
int main() {
  auto inc = [](int v) static { return v + 1; };   // C++23 static lambda
  std::printf("%d %d %d %d %d\n",
              Conv{}(21),                 // (c.operator F())(21)：42
              Adder{}(1),                 // 默认实参：11
              Stateless{}(1),             // 2
              Stateless::operator()(1),   // 静态成员可以用类名调用
              inc(1));                    // 2
}
```

¶1 说的是成员函数，没有说非静态成员函数。C++23 的 [[P1169R4]] 借此允许 `static operator()`，无捕获的 lambda 也可以声明为 `static`。静态的 `operator()` 不需要传递 `this`，适合比较器、哈希、投影这类无状态的函数对象。

代理调用函数和真正的 `operator()` 平等竞争，可能产生歧义：

```cpp error
using F = int (*)(int);
int twice(int x) { return 2 * x; }
struct Both {
  operator F() const { return twice; }
  int operator()(long) const { return -1; }
};
int x = Both{}(1);   // error: 歧义
```

`operator()(long)` 的对象实参不需要转换，`1` 要从 `int` 转换成 `long`。代理调用函数的对象实参要经用户定义转换，`1` 不需要转换。两个候选各在一个实参上更好，所以有歧义。

## 下标 [over.sub]

¶1 **下标运算符函数**是名为 `operator[]` 的成员函数，形参个数任意，可以有默认实参。`a[args]` 选中它时解释为 `a.operator[](args)`。

```cpp run ok
struct Matrix {
  int d[3][4]{};
  int& operator[](int i, int j) { return d[i][j]; }   // 多维下标
  static int operator[]() { return 42; }              // 零个实参，静态成员
};
int main() {
  Matrix m;
  m[1, 2] = 7;
  return m[1, 2] + Matrix{}[] - 49;
}
```

方括号里是一个 *expression-list*，可以有零个、一个或多个实参，这是 C++23 的多维下标（[[P2128R6]]），`std::mdspan` 就用这种写法。为了给它让路，C++20 先弃用了下标里没有括号的逗号表达式（[[P1161R3]]）：`a[1, 2]` 在 C++20 中是带弃用警告的 `a[(1, 2)]`，C++23 起是两个实参的下标。同在 C++23，[[P2589R1]] 允许了 `static operator[]`。

¶2 的例子说明内建下标仍然只接受一个下标：

```cpp
#include <initializer_list>
struct Z {};
struct X {
  Z operator[](std::initializer_list<int>);
  Z operator[](auto...);
};
X x;
void f() {
  x[{1,2,3}] = Z{};   // OK：x.operator[]({1,2,3})
  x[1,2,3] = Z{};     // OK：x.operator[](1,2,3)
  int a[10];
  a[{1,2,3}] = 7;     // error: 内建下标运算符
  a[1,2,3] = 7;       // error: 内建下标运算符只接受一个下标
}
```

要表达旧的逗号表达式含义，给它加括号：`a[(i, j)]`。

## 成员访问 `->` [over.ref]

¶1 **类成员访问运算符函数**是名为 `operator->`、没有非对象形参的非静态成员函数。`x->m` 选中它时，解释为

```text
(x.operator->())->m
```

`x->` 后面跟 C++26 的拼接表达式时也一样。

关键在于结果会再套上一个 `->`。如果 `operator->()` 返回的是类类型而不是指针，新的 `->` 又是一次运算符表达式，于是再调用它的 `operator->()`。这样一层层下去，直到得到原生指针，最后应用内建的 `->`：

```cpp run ok
struct T { int v = 7; };
struct Inner { T t; T* operator->() { return &t; } };
struct Outer { Inner i; Inner& operator->() { return i; } };   // 返回类类型：继续下去
int main() {
  Outer o;
  return o->v - 7;   // o.operator->() 得到 Inner&，再 .operator->() 得到 T*，再用内建 ->
}
```

`x->m` 的右边是成员名，不是可以求值的表达式，没法作为实参传给函数，所以 `operator->` 定义成没有非对象形参的函数，只负责给出可以继续套用 `->` 的结果。

`operator->` 的返回类型本身不受限制，返回 `int` 也可以声明，只是 `b->x` 在最后一步失败，因为内建 `->` 需要指针。返回自身类型会无限下去，标准没有为此写专门的规则，实际碰到的是实现限制，Clang 报告 `circular pointer delegation detected`。

```cpp
struct Bad { int operator->() { return 0; } };
struct Self { Self operator->() { return *this; } int x; };
void f(Bad b, Self s) {
  (void)b.operator->();   // OK：普通的成员函数调用
  (void)b->x;             // error: 结果是 int，不能再应用 ->
  (void)s->x;             // error: 无限下去
}
```

## 自增与自减 [over.inc]

### 前缀与后缀（[over.inc.general]）

```cpp run ok
struct X {
  int n = 0;
  X& operator++() { ++n; return *this; }            // 前缀 ++a
  X  operator++(int) { X t = *this; ++n; return t; } // 后缀 a++
};
struct Y { int n = 0; };
Y& operator++(Y& y) { ++y.n; return y; }             // 前缀 ++b
Y  operator++(Y& y, int) { Y t = y; ++y.n; return t; }   // 后缀 b++
int main() {
  X a; Y b;
  ++a; a++;   // a.operator++(); a.operator++(0);
  ++b; b++;   // operator++(b); operator++(b, 0);
  return a.n + b.n - 4;
}
```

¶1 **自增运算符函数**是名为 `operator++` 的函数。没有非对象形参的非静态成员函数，或者只有一个形参的非成员函数，定义前缀 `++`。有一个非对象形参的非静态成员函数，或者有两个形参的非成员函数，定义后缀 `++`，这个多出来的形参必须是 `int`。¶2 **自减运算符函数** `operator--` 同理。

`int` 哑形参的唯一作用是让前缀和后缀的签名不同。经 `a++` 调用时实参是 0；脚注说明显式调用 `a.operator++(2)` 没有什么特别，实参就是 2。这个形参必须正好是 `int`，写成 `long` 不行，加默认实参 `int = 0` 也不行（¶10）。

```cpp
struct S {
  S operator++(long);      // error: 后缀 ++ 的形参必须是 int
  S operator--(int = 0);   // error: 不能有默认实参
};
```

惯例上前缀返回引用，后缀返回旧值的副本。语言并不强制这一点（¶9），但违反它会让使用者意外。后缀版本要复制，所以泛型代码习惯写 `++it`。

### 预置的后缀自增、自减（[over.inc.default]）{{c++29}}

后缀 `++` 的写法几乎总是一样的：复制一份，调用前缀版本，返回副本。C++26 之后并入草案的 [[P3668R4]] 允许直接把它声明为 `= default`。

¶1 类型 `C` 的预置后缀自增、自减运算符必须是非模板函数，并且满足：

- ¶1.1 第一个形参的类型是 `C&` 或 `volatile C&`。成员函数的隐式对象形参算作第一个形参。
- ¶1.2 在 `C` 内，或者在 `C` 是完整类型的地方定义为预置。
- ¶1.3 声明的返回类型是 `C`。

隐式定义中的名字查找和访问检查，在相当于函数体的语境中进行。在类内定义为预置时，这必须是该函数的第一个声明。

¶3 没有被删除时，隐式定义相当于下面的代码，其中 `c` 代表 `*this` 或第一个形参：

```cpp
C tmp(c);
++c;          // 自减版本是 --c
return tmp;
```

¶2 下列情况下，预置的后缀运算符被定义为删除：`C` 是类类型而不能从 `C` 的左值直接初始化（不可复制，¶2.1）；`C` 的析构函数被删除或不可访问（¶2.2）；对 `C` 的左值 `c`，`++c`（或 `--c`）没有可用的候选（¶2.3）。

¶4 的例子：

```cpp
struct S {
  S(const S&) = default;
  S& operator++() { return *this; }
};
S operator++(S, int) = default;      // error: 第一个形参必须是引用

struct T {
  T operator++(int) = default;       // OK，定义为删除：T 没有前缀 ++
};

enum class E1 {};
E1 operator++(E1&, int) = default;   // OK，定义为删除：枚举没有内建 ++

enum E2 {};
E2& operator++(E2& e);
E2 operator++(E2&, int) = default;   // OK，没有删除：调用用户的前缀 ++
```

即使是无作用域枚举也没有内建的 `++`。[[over.built#4]] 只为算术类型和对象指针类型提供 `++` 候选，枚举提升成整数得到的是纯右值，不能绑定到 `int&`。

截至写作时，Clang 23 还没有实现这一规则，上面所有的 `= default` 都报 `only special member functions and comparison operators may be defaulted`。按当前草案，标注 OK 的几行是良构的。

## 汇总

| 运算符 | 可以是非成员 | 可以是静态成员 | 默认实参 | 形参个数（成员 / 非成员） |
|---|---|---|---|---|
| 一元 `+ - * & ! ~` | 是 | 否 | 否 | 0 / 1 |
| 二元（含 `->*`、`&&`、`,`、复合赋值、比较） | 是 | 否 | 否 | 1 / 2 |
| `=` | 否 | 否 | 否 | 1 |
| `()` | 否 | 是（C++23） | 是 | 任意 |
| `[]` | 否 | 是（C++23） | 是 | 任意（C++23 前恰好 1） |
| `->` | 否 | 否 | 否 | 0 |
| 前缀 `++ --` | 是 | 否 | 否 | 0 / 1 |
| 后缀 `++ --` | 是 | 否 | 否 | 1 / 2，最后一个是 `int` |
| `new delete new[] delete[]` | 见 [[basic.stc.dynamic]] | 类内隐式静态 | | |
| `co_await` | 见 [[expr.await]] | | | |

成员的形参个数指非对象形参，C++23 的显式对象形参不计在内。

!!! impl
    - 在 Itanium C++ ABI 中，运算符函数的名字修饰用两个字母表示运算符，如 `operator+` 是 `pl`，`operator()` 是 `cl`，`operator[]` 是 `ix`，`operator->` 是 `pt`，`operator<=>` 是 `ss`。`S::operator+(int)` 修饰为 `_ZN1SplEi`。
    - 静态 `operator()` 省掉的是 `this` 参数。调用被内联时，非静态版本的 `this` 通常也会被优化掉；经 `std::function` 或跨翻译单元调用时，静态版本少传一个参数。无捕获 lambda 加 `static` 后，到函数指针的转换可以直接返回 `operator()` 的地址，不必另外生成转发函数。
    - Clang 对违反本节约束的诊断多以 `overloaded 'operator@' must` 或 `cannot` 开头，例如 `must have at least one parameter of class or enumeration type`、`must be a non-static member function`、`cannot have a default argument`。

## 历史与演进

!!! history
    - C++98 就有本节的基本框架：可重载运算符的清单，至少一个类或枚举形参，`=`、`()`、`[]`、`->` 必须是非静态成员，后缀的 `int` 哑形参，`->` 的逐层套用。
    - C++11 允许用花括号列表作下标（`x[{1,2,3}]`），用户定义字面量另立 [[over.literal]]。
    - C++17 的 [[P0145R3]] 让重载运算符的操作数沿用内建运算符的求值顺序。
    - C++20 加入了 `<=>`、预置的比较运算符和可以重载的 `co_await`，并弃用了下标中的逗号表达式（[[P1161R3]]）。
    - C++23 加入了显式对象形参（[[P0847R7]]）、`static operator()`（[[P1169R4]]）、多维下标（[[P2128R6]]）和 `static operator[]`（[[P2589R1]]）。
    - C++26 之后，[[P3668R4]] 加入了预置的后缀自增、自减。

## 常见误解

!!! pitfall "派生类继承了基类的 `operator=`"
    其他运算符函数都能继承，`operator=` 总被派生类隐式声明的复制赋值隐藏，需要 `using Base::operator=;`。

!!! pitfall "成员形式的对称运算符"
    `x + 1` 能编译而 `1 + x` 不能，因为左操作数对应对象形参，不做用户定义转换。对称的运算符写成隐藏友元。

!!! pitfall "在泛型代码里直接写 `&x` 或 `a, b`"
    操作数的类型可能重载了一元 `&` 或 `,`。取地址用 `std::addressof(x)`，逗号写成 `(void)a, b`。

## 思考题

!!! question "1. 下面哪些声明非良构？"
    ```cpp
    struct S {};
    enum E { e };
    S& operator+=(S&, int);          // (a)
    int operator,(E, E);             // (b)
    E* operator&(E&);                // (c)
    void operator=(E&, int);         // (d)
    int operator->*(S, int S::*);    // (e)
    struct T { static int operator[](int, int); };   // (f)
    struct U { static bool operator==(U, U); };      // (g)
    ```

<details markdown="1">
<summary>答案</summary>

- (a) 良构。复合赋值不是 [over.assign] 所说的简单赋值，按 ¶11 是普通的二元运算符，可以是非成员。
- (b)(c) 良构。¶7 明确允许为枚举重新定义 `,` 和一元 `&`。
- (d) 非良构。`operator=` 必须是非静态成员函数，枚举没有成员，所以枚举的赋值不能重新定义。
- (e) 良构。`->*` 是普通的二元运算符，可以是非成员，这一点和 `->` 不同。
- (f) 良构（C++23）。静态的、两个形参的下标运算符。
- (g) 非良构。二元运算符函数必须是非静态成员或非成员，`static` 只对 `()` 和 `[]` 开放。

Clang 23 只对 (d) 和 (g) 报错。
</details>

!!! question "2. 为什么 `operator()` 和 `operator[]` 可以是静态的，`operator+` 不行？"

<details markdown="1">
<summary>答案</summary>

`f(args)` 和 `a[args]` 的实参都写在括号里，`f`、`a` 只是被调用或被索引的对象。静态成员版本把这个对象当作隐含的对象实参，匹配之后丢弃（[[over.match.funcs.general#4]]），括号里的实参列表仍然完整。`a + b` 的两个操作数地位相同，成员形式里左操作数就是对象实参。静态成员没有对象形参，左操作数无处可放，形参个数对不上 [over.binary] 的要求。
</details>
