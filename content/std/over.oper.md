---
title: 重载运算符
summary: 哪些运算符可以重载、运算符函数必须长什么样：至少一个类/枚举形参、元数固定、不得有默认实参；=、()、[]、-> 只能是成员；static operator() 与多参数 operator[]（C++23）；-> 的逐层下钻；后缀 ++ 的 int 形参与预置的后缀自增。
status: draft
covers: *
since: c++98
papers: P0145R3, P0847R7, P1169R4, P2589R1, P2128R6, P1161R3
related: over.match.oper, over.built, over.call.object, class.copy.assign, class.compare.default, expr.unary.op, expr.sub, expr.ref, expr.post.incr, basic.stc.dynamic, expr.await
tags: 重载, 运算符
updated: 2026-10-17
---

本节回答的是声明层面的问题：一个名为 `operator@` 的函数，形参该有几个、能不能是成员、能不能是静态的、能不能有默认实参。至于 `a @ b` 出现时怎样在成员、非成员、内建候选之间做选择，那由 [[over.match.oper]] 规定；内建候选的清单在 [[over.built]]。三节合起来才是完整的运算符重载。

本页一并覆盖 [over.oper] 的全部子条款：

| 子条款 | 内容 |
|---|---|
| [over.oper.general] | 可重载的运算符清单、运算符函数的通用约束 |
| [over.unary] | 前缀一元运算符 |
| [over.binary] | 二元运算符；比较运算符函数的分类 |
| [over.assign] | 简单赋值 `=`：只能是非静态成员 |
| [over.call] | 函数调用 `()`：可以是静态成员（C++23），可有默认实参 |
| [over.sub] | 下标 `[]`：任意个形参（C++23），可以是静态成员 |
| [over.ref] | 成员访问 `->`：逐层下钻 |
| [over.inc] | 自增自减：前缀/后缀之分，`int` 哑形参，预置的后缀版本 |

## §1 通则 [over.oper.general]

### 什么是运算符函数（¶1）

¶1 *declarator-id* 为 *operator-function-id*（`operator` 后跟一个运算符）的声明，必须声明一个函数、函数模板，或者函数模板的显式实例化/特化。这样声明的函数是**运算符函数**（[[g:operator-function|operator function]]），这样声明的函数模板是**运算符函数模板**；运算符函数模板的特化也是运算符函数。运算符函数实现（implements）其名字中的运算符。

可以出现在 `operator` 之后的运算符一共 42 个：

```
new  delete  new[]  delete[]  co_await  ()  []  ->  ->*
~  !  +  -  *  /  %  ^  &  |  =  +=  -=  *=  /=  %=  ^=  &=  |=
==  !=  <  >  <=  >=  <=>  &&  ||  <<  >>  <<=  >>=  ++  --  ,
```

注 1：`new[]`、`delete[]`、`()`、`[]` 由多个记号组成，所以 `operator ( )` 中间可以有空白。

必须声明函数这一要求，排除了诸如 `int operator+;` 这样的变量声明：

```cpp error
struct S {};
int operator+;     // error: operator+ 不能是变量名
```

### 一元/二元同形，以及不可重载的运算符（¶2–¶3）

¶2 `+`、`-`、`*`、`&` 的一元与二元形式都可以重载，它们共用同一个名字，靠形参个数区分（见 [[over.unary]] 的注 2）。

¶3 注 2：`.`、`.*`、`::`、`?:` 不能重载，预处理符号 `#`、`##` 也不能。

为什么是这四个？

- `::` 是纯编译期的作用域解析，左边根本不是值。
- `.` 和 `.*` 若可重载，就再也没有可靠的办法访问对象本身的成员。智能引用的需求曾多次以 operator dot 提案的形式出现，但从未被采纳。
- `?:` 只对其中一个分支求值，而函数调用会对所有实参求值，语义无法保持。（`&&`、`||` 也有同样的问题，但它们历史上就可以重载，见 §3。）

清单之外的运算符，如 `sizeof`、`alignof`、`typeid`、`noexcept`、各种 `*_cast`、C++26 的反射运算符 `^^`，也都不能重载，因为它们根本不在 ¶1 的文法里。

```cpp error
struct S {};
S operator.(S);    // error: . 不是可重载的运算符
S operator?:(S);   // error
```

### 显式调用（¶4）与三个例外（¶5–¶6）

¶4 运算符函数通常由运算符表达式隐式调用，但也可以用 *operator-function-id* 作为函数名显式调用：`a.operator+(b)`、`operator+(a, b)`、`operator new(n)`。

显式调用走的是普通的函数调用决议（[[over.call.func]]），不经过 [[over.match.oper]]：没有内建候选、没有改写候选，非限定查找还可能被同名成员隐藏（见 [[over.match.oper]] 末尾的注 3）。

```cpp run ok
struct S { int v; };
int operator+(S a, S b) { return a.v + b.v; }
int main() {
  S a{1}, b{2};
  return operator+(a, b) - (a + b);   // 两者调用同一函数
}
```

¶5 分配/释放函数 `operator new`、`operator new[]`、`operator delete`、`operator delete[]` 的规则完全由 [[basic.stc.dynamic]] 规定；本节其余的属性和限制对它们不适用，除非那里明确引用。¶6 `co_await` 同理，由 [[expr.await]] 完整规定。

因此 `operator new(std::size_t)` 可以没有任何类类型形参（违反下面的 ¶7），类内的 `operator new` 隐式是静态成员，`operator delete` 可以有 `std::destroying_delete_t` 形参等等。

### 至少一个类或枚举形参（¶7）

¶7 运算符函数必须至少有一个函数形参或隐式对象形参，其类型是类、类的引用、枚举或枚举的引用。

这条规则与 [[over.match.oper#1]] 一起保证了 `int + int`、`指针 + 整数` 的含义永远是内建的，用户无法改变。成员函数自动满足这一要求（隐式对象形参的类型是 `cv X&` 或 `cv X&&`）。

```cpp
int operator+(int, int);              // error: 没有类或枚举形参
enum class C {};
C operator~(C);                       // OK：枚举
int operator+(C*, int);               // error: C* 是指针，不是枚举
struct S {};
template<class T> int operator-(T*, T*);   // OK：模板本身不受检查；它的特化永远不会被 int* - int* 用到
```

最后一行：模板声明本身合法；[[over.match.oper#1]] 规定所有操作数都不是类/枚举类型时根本不做重载决议，所以 `p - p`（`int*`）永远是内建减法，这个模板永远不会为指针实例化。

!!! lawyer "显式对象形参与 ¶7"
    ¶7 说的是"函数形参或隐式对象形参"。显式对象成员函数（C++23）没有隐式对象形参，它的 `this` 形参是一个普通的函数形参，所以 `struct S { int operator+(this int, int); };` 的两个形参都是 `int`，按 ¶7 非良构。截至写作时，Clang 23 不诊断这一点。

¶7 后半规定，不能改变运算符的优先级、结合性和操作数个数。`=`、一元 `&`、`,` 对每种类型都有预定义含义，可以为特定类类型重新定义；一元 `&` 和 `,` 还可以为特定枚举类型重新定义（枚举不能有成员，而 `=` 只能是成员，所以枚举的赋值无法重定义）。运算符函数像其他基类函数一样会被继承，但 `operator=` 总会被派生类隐式声明的拷贝赋值隐藏（见 §4）。

```cpp run ok
struct B { int operator+(int) const { return 1; } };
struct D : B {};
int main() { D d; return (d + 1) - 1; }   // B::operator+ 被继承
```

### 运算符函数的种类、元数与默认实参（¶8–¶11）

¶8 运算符函数必须是以下之一：前缀一元、二元、函数调用、下标、类成员访问、自增、自减运算符函数（后续各小节分别定义）。因此 `operator!(S, S)`、`operator~(S, S)` 都非良构，因为 `!`、`~` 没有二元形式。

¶9 注 3：内建运算符之间的恒等关系（如对基本类型 `++a` 等价于 `a += 1`）对运算符函数不必成立；有些内建运算符要求操作数是左值（如 `+=`），运算符函数没有这个要求。换句话说，语言不会从 `+` 推出 `+=`，也不会阻止 `a == b` 与 `!(a != b)` 不一致。（C++20 的 `!=` 改写只在没有声明 `operator!=` 时才起作用，见 [[over.match.oper]]。）

¶10 运算符函数不能有默认实参，除非下文明确允许（只有 `operator()` 和 `operator[]`）；形参个数必须恰好等于相应运算符所需的个数。

为什么禁止默认实参？因为运算符表达式的操作数个数由文法固定，默认实参只会制造歧义：`operator-(S = S{})` 难道既能当一元又能当零元？`operator++(int = 0)` 则让前缀与后缀无法区分。

```cpp
struct S {
  void operator+(int = 0);        // error: 运算符函数不能有默认实参
  void operator()(int = 0);       // OK：函数调用运算符例外
  int  operator[](int = 0);       // OK：下标运算符例外（C++23 起可有任意个形参）
  void operator-(int, int);       // error: 二元 - 作为成员只能有一个非对象形参
};
```

¶11 [[over.assign]] 到 [[over.inc]] 没有特别提到的运算符，按 [[over.unary]] 或 [[over.binary]] 的普通规则处理。也就是说：`->*`、`&&`、`||`、`,`、复合赋值 `+=` 等、`<=>` 都是普通的二元运算符，可以是非成员。只有 `=`、`()`、`[]`、`->` 是单独列出的，要求是成员。

## §2 一元运算符 [over.unary]

¶1 **前缀一元运算符函数**（[[g:prefix-unary-operator-function|prefix unary operator function]]）是名为 `operator@` 的函数，`@` 是前缀 *unary-operator*（[[expr.unary.op]] 中的 `*`、`&`、`+`、`-`、`!`、`~`），它要么是没有非对象形参的非静态成员函数，要么是恰有一个形参的非成员函数。对 `@ cast-expression`，由 [[over.match.oper]] 选择；选中成员函数则解释为 `(cast-expression).operator@()`，选中非成员则为 `operator@(cast-expression)`。

注 1：`++`、`--` 另见 [[over.inc]]。

"没有非对象形参的非静态成员函数"同时涵盖了两种写法：

```cpp run ok
struct S {
  int operator-() const { return -1; }      // 隐式对象成员函数
  int operator!(this S) { return 2; }       // 显式对象成员函数：this 形参是对象形参
};
struct T {};
int operator~(T) { return 3; }              // 非成员，一个形参
int main() { S s; return -s + !s + ~T{} - 4; }
```

¶2 注 2：一元与二元形式同名，所以一元运算符函数可以隐藏外层作用域的二元运算符函数，反之亦然。这只在非限定查找停在内层作用域时才显现：

```cpp error
namespace A { struct S {}; }
A::S operator-(A::S, A::S);       // 全局的二元 -
namespace B {
  void operator-(A::S);           // B 中的一元 -：隐藏了全局的 operator-
  void f(A::S x) { x - x; }       // error: 非限定查找在 B 中停下，只找到一元版本；ADL 只看命名空间 A
}
```

把二元 `operator-` 放进 `A`（`S` 的关联命名空间），ADL 就能找到它。这是把运算符与类型放在同一命名空间这一惯例的又一个理由。

## §3 二元运算符 [over.binary]

### 通则（[over.binary.general] ¶1）

¶1 **二元运算符函数**（[[g:binary-operator-function|binary operator function]]）是名为 `operator@` 的函数（`@` 为二元运算符），要么是恰有一个非对象形参的非静态成员函数，要么是恰有两个形参的非成员函数。`x @ y` 选中成员则解释为 `x.operator@(y)`，选中非成员则为 `operator@(x, y)`。

注意其中的"非静态"：二元运算符不能是静态成员函数，因为静态成员没有对象形参，就只剩一个操作数了。（与之对照，`operator()` 和 `operator[]` 从 C++23 起可以是静态的，因为它们的左操作数本来就不是作为普通实参传递的。）

```cpp
struct S {
  static int operator+(S, S);     // error: 二元运算符函数不能是静态成员
  int operator+(this S, int);     // OK：显式对象成员函数，一个非对象形参
};
```

成员还是非成员？成员版本的左操作数是对象形参，不允许用户定义转换（[[over.best.ics#9]]），所以 `1 + x` 不会通过 `x` 的成员 `operator+` 进行（C++20 的反转候选只对 `==` 与 `<=>` 生效）。需要两侧对称转换时，应写成非成员，最好是**隐藏友元**（只在类内定义的友元）。它只能经 ADL 找到，不污染外层作用域的重载集。

```cpp run ok
struct Num {
  int v;
  Num(int x) : v(x) {}
  friend Num operator+(Num a, Num b) { return a.v + b.v; }   // 隐藏友元
};
int main() {
  Num a = 1;
  Num b = 2 + a;    // OK：非成员，两侧都能经 Num(int) 转换
  return b.v - 3;
}
```

### 比较运算符函数（[over.binary.general] ¶2）

¶2 定义了几个术语，供 [[class.compare.default]] 等处使用：

| 术语 | 实现的运算符 |
|---|---|
| 相等运算符函数（equality operator function） | `==`、`!=` |
| 关系运算符函数（relational operator function） | `<`、`>`、`<=`、`>=` |
| 三路比较运算符函数（three-way comparison operator function） | `<=>` |
| **比较运算符函数**（[[g:comparison-operator-function|comparison operator function]]） | 以上全部 |

只有比较运算符函数可以 `= default`（另加特殊成员函数与下文 §8 的后缀自增/自减）。

### `&&`、`||`、`,`：能重载，但最好不要

这三个运算符的内建版本有特殊的求值规则：`&&`/`||` 短路，`,` 先求值并丢弃左操作数。一旦重载，表达式就变成一次函数调用，**两个操作数都会求值**，短路语义随之丧失。C++17 起（[[P0145R3]]），重载运算符的操作数按内建运算符的规定定序（[[over.match.oper#2]]），所以至少左操作数先于右操作数求值；C++14 及以前连这一点都没有保证。

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

一元 `&` 被重载后，`&obj` 不再能取得地址，`std::addressof` 正是为此而存在。泛型代码里写 `a, b` 也可能意外调用用户的 `operator,`；惯用的防御写法是 `(void)a, b`，因为 `void` 类型的操作数不能传给任何函数，于是只能使用内建逗号（[[over.match.oper#13]]）。

```cpp run ok
#include <memory>
struct Evil { int operator&() const { return 0; } };
int main() {
  Evil e;
  auto a = &e;                    // 调用 Evil::operator&，a 是 int
  Evil* p = std::addressof(e);    // 真正的地址
  static_assert(__is_same(decltype(a), int));
  return p ? 0 : 1;
}
```

## §4 简单赋值 [over.assign]

¶1 **简单赋值运算符函数**是名为 `operator=` 的二元运算符函数，必须是非静态成员函数。

注 1：转换到赋值的左操作数时只考虑标准转换序列（[[over.best.ics#9]]），所以左操作数 `x` 是类类型时，`x = y` 总是解释为 `x.operator=(y)`，内建的 `operator=` 永远不会被选中。（对类类型 `x`，内建候选的第一个形参只能经用户定义转换得到，而这被禁止了。）

为什么 `operator=` 不能是非成员？因为每个类都会隐式声明拷贝赋值（以及在条件满足时的移动赋值）。如果允许非成员的 `operator=`，那么在它声明之前和之后，同一个 `a = b` 可能调用不同的函数，而且类的作者无法控制自己类型的赋值语义。`()`、`[]`、`->` 要求是成员，理由类似：它们与对象本身的关系过于紧密，标准选择把定义权留给类本身。

```cpp
struct S {};
void operator=(S&, int);          // error: operator= 必须是非静态成员函数
struct T { static T& operator=(int); };   // error: 不能是静态成员
struct R { operator int&(); };
void g(R r) { r = 5; }            // error: 内建 int& = int 不可行（左操作数不允许用户定义转换），R 也没有接受 int 的 operator=
```

¶2 注 2：由于拷贝赋值运算符总会被隐式声明，**基类的赋值运算符函数总被派生类的拷贝赋值运算符隐藏**。要继承它，必须写 `using Base::operator=;`。

```cpp
struct B { B& operator=(int); };
struct D : B {};
struct D2 : B { using B::operator=; };
void f(D d, D2 d2) {
  d2 = 1;      // OK：B::operator=(int) 经 using 声明可见
  d = 1;       // error: D 的隐式拷贝/移动赋值隐藏了 B::operator=(int)，而 1 不能转换为 D
}
```

¶3 注 3：任何赋值运算符函数，包括拷贝、移动赋值，都可以是虚函数。但对派生类 `D` 与声明了虚拷贝/移动赋值的基类 `B`，`D` 的拷贝/移动赋值运算符不会覆盖 `B` 的：`D` 的拷贝赋值形参是 `const D&`，`B` 的是 `const B&`，签名不同。

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
  *bp = 99;      // D::operator=(int)：虚调用
  *bp = d2;      // D::operator=(const B&)：虚调用
  d1 = d2;       // 隐式声明的 D::operator=(const D&)，它对基类子对象做 B::operator=(const B&)（非虚的限定调用）
}
```

这个例子说明，多态赋值几乎从来不是好主意：`d1 = d2` 绕过了专门写好的虚函数。

## §5 函数调用 [over.call]

¶1 **函数调用运算符函数**是名为 `operator()` 的成员函数，形参个数任意，可以有默认实参。

对 `postfix-expression ( expression-list_opt )`（*postfix-expression* 是类类型），由 [[over.call.object]] 进行重载决议：

- 若选中代理调用函数（surrogate call function，由转换到函数指针/引用的转换函数生成），设 `e` 为对 *postfix-expression* 调用对应转换函数的结果，表达式解释为 `e(expression-list)`；
- 否则解释为 `postfix-expression.operator()(expression-list)`。

注意措辞是"成员函数"而不是"非静态成员函数"，C++23 的 [[P1169R4]] 正是借此引入了 `static operator()`。无捕获 lambda 也可以声明为 `static`。静态的 `operator()` 不需要传递 `this`，对无状态函数对象（比较器、哈希、投影）可以省掉一个寄存器和一次间接访问。

```cpp run ok
#include <cstdio>
using F = int (*)(int);
int twice(int x) { return 2 * x; }
struct Conv { operator F() const { return twice; } };      // 代理调用函数的来源
struct Adder { int operator()(int a, int b = 10) const { return a + b; } };   // 默认实参 OK
struct Stateless { static int operator()(int x) { return x + 1; } };          // C++23
int main() {
  Conv c;
  auto fact = [](this auto self, int n) -> int { return n <= 1 ? 1 : n * self(n - 1); };  // 显式对象形参
  auto inc  = [](int v) static { return v + 1; };                                         // static lambda
  std::printf("%d %d %d %d %d %d\n",
              c(21),                       // 选中代理调用函数：解释为 (c.operator F())(21)
              Adder{}(1),                  // 11
              Stateless{}(1),              // 2
              Stateless::operator()(1),    // 静态成员可以直接用类名调用
              fact(5),                     // 120
              inc(1));                     // 2
}
```

代理调用函数与真正的 `operator()` 一起竞争，可能产生歧义：

```cpp error
using F = int (*)(int);
int twice(int x) { return 2 * x; }
struct Both {
  operator F() const { return twice; }
  int operator()(long) const { return -1; }
};
int x = Both{}(1);   // error: 歧义
```

`operator()(long)`：对象实参恒等，`1 → long` 整型转换。代理调用函数 `int call(F, int)`：对象实参需要用户定义转换，`1 → int` 恒等。两个候选各在一个实参上更好，因此歧义。

`operator()` 不能是非成员：

```cpp error
struct S {};
void operator()(S);    // error: operator() 必须是成员函数
```

## §6 下标 [over.sub]

¶1 **下标运算符函数**是名为 `operator[]` 的成员函数，形参个数任意，可以有默认实参。对 `postfix-expression [ expression-list_opt ]`，由 [[over.match.oper]] 选择；选中成员函数则解释为 `postfix-expression.operator[](expression-list_opt)`。

这一段包含了 C++23 的两项改动：

- 多维下标（[[P2128R6]]）：方括号内是 *expression-list*，可以有零个、一个或多个实参。`m[i, j]` 终于可以表示 `m.operator[](i, j)`，`std::mdspan` 就使用这种写法。此前 C++20 已先行弃用下标中顶层的逗号表达式（[[P1161R3]]），为这次改变含义做准备：`a[1, 2]` 在 C++20 里是 `a[(1, 2)]`（带弃用警告），C++23 起是两个实参的下标。
- `static operator[]`（[[P2589R1]]）：与 `static operator()` 对称。

```cpp run ok
struct Matrix {
  int d[3][4]{};
  int& operator[](int i, int j) { return d[i][j]; }   // 多维下标
  static int operator[]() { return 42; }              // 零个实参，静态
};
int main() {
  Matrix m;
  m[1, 2] = 7;
  return m[1, 2] + Matrix{}[] - 49;
}
```

¶2 标准的例子：

```cpp
#include <initializer_list>
struct Z {};
struct X {
  Z operator[](std::initializer_list<int>);
  Z operator[](auto...);
};
X x;
void f() {
  x[{1,2,3}] = Z{};    // OK：x.operator[]({1,2,3})
  x[1,2,3] = Z{};      // OK：x.operator[](1,2,3)
  int a[10];
  a[{1,2,3}] = 7;      // error: 内建下标运算符
  a[1,2,3] = 7;        // error: 内建下标运算符只接受一个下标
}
```

内建的 `[]`（[[expr.sub]]）仍然恰好要一个下标；要表达旧含义，给逗号表达式加括号：`a[(i, j)]`。注意 `[]` 的非成员候选集为空（[[over.match.oper#3.2]]），而内建候选是 `T& operator[](T*, std::ptrdiff_t)` 与 `T& operator[](std::ptrdiff_t, T*)`（[[over.built#13]]），所以类对象若能转换为指针，`p[1]` 和 `1[p]` 都能工作。

## §7 类成员访问 [over.ref]

¶1 **类成员访问运算符函数**是名为 `operator->` 的、没有非对象形参的非静态成员函数。对 `postfix-expression -> template_opt id-expression`，由 [[over.match.oper]] 选择，表达式解释为

```
( postfix-expression . operator -> () ) -> template_opt id-expression
```

对 `postfix-expression -> splice-expression`（C++26 反射）同理。

关键在于结果会再次套上 `->`。如果 `operator->()` 返回的是类类型（而非指针），这个新的 `->` 又是一次运算符表达式，于是再调用它的 `operator->()`。如此**逐层下钻**，直到得到一个原生指针，最后应用内建 `->`（[[over.match.oper#12]] 的脚注）。这使得代理对象可以层层包装：

```cpp run ok
struct T { int v = 7; };
struct Inner { T t; T* operator->() { return &t; } };
struct Outer { Inner i; Inner& operator->() { return i; } };   // 返回类类型：继续下钻
int main() {
  Outer o;
  return o->v - 7;   // o.operator->() → Inner& → .operator->() → T* → 内建 ->
}
```

`operator->` 的返回类型本身不受限制，可以是 `int`。这样的声明合法，显式调用 `b.operator->()` 也合法；只是 `b->x` 会在最后一步失败，因为内建 `->` 需要指针。

```cpp
struct Bad { int operator->() { return 0; } };
void f(Bad b) {
  (void)b.operator->();   // OK：普通的成员函数调用
  (void)b->x;             // error: 结果是 int，不能再应用 ->
}
```

```cpp error
struct Self { Self operator->() { return *this; } int x; };
void h(Self s) { (void)s->x; }   // error: 无限下钻
```

标准没有为无限下钻写专门的规则（每一步都只是按 ¶1 改写），实际触发的是实现限制；Clang 诊断为 "circular pointer delegation detected"。

`operator->` 不能是非成员，也不能是静态成员；显式对象形参可以：

```cpp run ok
struct T { int v; };
struct S { T t; T* operator->(this S& s) { return &s.t; } };
int main() { S s{{5}}; return s->v - 5; }
```

## §8 自增与自减 [over.inc]

### 前缀与后缀（[over.inc.general] ¶1–¶2）

¶1 **自增运算符函数**是名为 `operator++` 的函数：

| 形式 | 成员 | 非成员 | 定义 |
|---|---|---|---|
| 前缀 `++a` | 非静态，无非对象形参 | 一个形参 | 前缀自增 |
| 后缀 `a++` | 非静态，一个非对象形参，类型必须是 `int` | 两个形参，第二个类型必须是 `int` | 后缀自增 |

经 `++` 运算符调用后缀版本时，`int` 实参的值为 0。脚注：显式调用 `a.operator++(2)` 没有什么特殊之处，实参就是 2。

¶2 **自减运算符函数** `operator--` 同理。

```cpp run ok
struct X {
  int n = 0;
  X& operator++()   { ++n; return *this; }           // 前缀
  X  operator++(int k) { X t = *this; n += k ? k : 1; return t; }   // 后缀
};
struct Y { int n = 0; };
Y& operator++(Y& y)      { ++y.n; return y; }        // 前缀
Y  operator++(Y& y, int) { Y t = y; ++y.n; return t; }   // 后缀
int main() {
  X a; Y b;
  ++a; a++;              // a.operator++(); a.operator++(0);
  ++b; b++;              // operator++(b); operator++(b, 0);
  a.operator++(5);       // 显式调用：k == 5
  return a.n + b.n - 9;  // 1 + 1 + 5 = 7，加上 b 的 2
}
```

`int` 哑形参是 Stroustrup 在 C++ 早期为区分前后缀而采用的约定，它唯一的作用是让两种形式的签名不同。它必须正好是 `int`，`long`、`int = 0` 都不行（后者违反 ¶10 不得有默认实参的规定）。

```cpp
struct S {
  S operator++(long);       // error: 后缀 ++ 的形参必须是 int
  S operator--(int = 0);    // error: 不得有默认实参
};
```

惯例上前缀返回引用、后缀返回旧值的副本。这只是惯例（¶9 说恒等关系不必成立），但违反它会出乎使用者的预期。也正因为后缀要拷贝，泛型代码里习惯写 `++it`。

### 预置的后缀自增/自减（[over.inc.default]）

这是 C++26 之后并入草案的新规则。后缀 `++`/`--` 的常规写法千篇一律（拷贝、调用前缀版本、返回副本），现在可以直接 `= default`。

¶1 类型 `C` 的预置后缀自增/自减运算符函数必须是非模板函数，并且：

- ¶1.1 第一形参类型是"`C` 的引用"或"`volatile C` 的引用"（若有隐式对象形参，把它视为第一形参）；
- ¶1.2 在 `C` 内部、或在 `C` 完整的语境中定义为预置；
- ¶1.3 声明的返回类型是 `C`。

（注 1 提醒：后缀版本总有一个 `int` 形参。）隐式定义中的名字查找和访问检查，在等价于其函数体的语境中进行。在类内定义为预置的，必须是该函数的首次声明。

```cpp error
struct S;
S operator++(S&, int) = default;   // error: S 不完整
```

¶2 在以下情况，预置的后缀运算符定义为删除：

- ¶2.1 `C` 是类类型，而用 `C` 的左值直接初始化 `C` 变量的重载决议没有得到可用候选（不可拷贝）；
- ¶2.2 `C` 的析构函数被删除或从函数体语境不可访问；
- ¶2.3 对 `C` 的左值 `c`，`++c`（或 `--c`）的重载决议没有得到可用候选（没有前缀版本）。

¶3 未被删除时，隐式定义等价于（`c` 是代表 `*this` 或第一形参的左值）：

```cpp
C tmp(c);
++c;          // 自减版本为 --c
return tmp;
```

¶4 标准的例子：

```cpp
struct S {
  S(const S&) = default;
  S& operator++() { return *this; }
};
S operator++(S, int) = default;        // error: 第一形参必须是引用

struct T {
  T operator++(int) = default;         // OK，定义为删除：T 没有前缀 ++
};

enum class E1 {};
E1 operator++(E1&, int) = default;     // OK，定义为删除：枚举没有内建 ++

enum E2 {};
E2& operator++(E2& e);
E2 operator++(E2&, int) = default;     // OK，未删除：调用用户的前缀 ++
```

注意 `E1`：即使是无作用域枚举，也没有内建的 `++`（[[over.built#4]] 只给算术类型和对象指针类型提供 `++` 候选；枚举到整数的提升产生纯右值，绑不到 `vq T&`）。

!!! impl "实现状况"
    截至写作时，Clang 23 尚未实现预置后缀自增/自减：上面这些 `= default` 一律报 "only special member functions and comparison operators may be defaulted"。按当前草案，标注为 OK 的几行是良构的。

## 汇总：各运算符的声明形式

| 运算符 | 可非成员 | 可静态成员 | 默认实参 | 非对象形参个数（成员）/ 形参个数（非成员） |
|---|---|---|---|---|
| 一元 `+ - * & ! ~` | ✓ | ✗ | ✗ | 0 / 1 |
| 二元（含 `->*`、`&&`、`,`、复合赋值、比较） | ✓ | ✗ | ✗ | 1 / 2 |
| `=` | ✗ | ✗ | ✗ | 1 |
| `()` | ✗ | ✓（C++23） | ✓ | 任意 |
| `[]` | ✗ | ✓（C++23） | ✓ | 任意（C++23 前恰好 1） |
| `->` | ✗ | ✗ | ✗ | 0 |
| 前缀 `++ --` | ✓ | ✗ | ✗ | 0 / 1 |
| 后缀 `++ --` | ✓ | ✗ | ✗ | 1 / 2（最后一个为 `int`） |
| `new delete new[] delete[]` | 见 [[basic.stc.dynamic]] | 类内隐式静态 | — | — |
| `co_await` | 见 [[expr.await]] | — | — | — |

"非静态成员"包括 C++23 的显式对象成员函数：显式对象形参是对象形参，不计入非对象形参。

## 实现视角

!!! impl
    - 名字修饰：运算符函数在 Itanium C++ ABI 中有专门的两字母编码，如 `operator+` 为 `pl`、`operator()` 为 `cl`、`operator[]` 为 `ix`、`operator->` 为 `pt`、`operator<=>` 为 `ss`。所以 `S::operator+(int)` 修饰为 `_ZN1SplEi`。
    - `static operator()` 的收益：对于 `std::sort(first, last, Cmp{})`，非静态 `operator()` 即使不访问成员，也要在调用约定里传 `this`；内联后通常会被优化掉，但不内联（例如经 `std::function` 或跨 TU）时就会多一个参数。静态版本从根本上消除了它。无捕获 lambda 加 `static` 后，实现可以让它到函数指针的转换直接返回 `operator()` 本身的地址，而不必另外生成一个转发函数。
    - 诊断：Clang 对违反本节约束的诊断多以 "overloaded 'operator@' must …" 开头，例如 "must have at least one parameter of class or enumeration type"、"must be a non-static member function"、"cannot have a default argument"。
    - ¶7 与显式对象形参：如上文所述，Clang 23 不检查显式对象形参为非类/枚举类型时的 ¶7 违例。

## 历史与演进

!!! history
    - **C++98**：本节框架成型：可重载运算符清单、至少一个类/枚举形参、`=`/`()`/`[]`/`->` 必须是非静态成员、后缀 `int` 哑形参、`->` 下钻。
    - **C++11**：用户定义字面量另立 [[over.literal]]；`x[{1,2,3}]` 允许花括号初始化列表作下标。
    - **C++17**：[[P0145R3]] 让重载运算符的操作数按内建运算符的顺序定序（`<<`、`>>`、`=`、`&&`、`||`、`,` 等从此有确定的左右顺序）。
    - **C++20**：`<=>` 加入可重载清单；比较运算符函数可以预置；`co_await` 可以重载；下标中的顶层逗号被弃用（[[P1161R3]]）。
    - **C++23**：显式对象形参（[[P0847R7]]）可用于运算符；`static operator()`（[[P1169R4]]）；多维下标（[[P2128R6]]）；`static operator[]`（[[P2589R1]]）。
    - **C++26 之后**：预置的后缀自增/自减（[over.inc.default]）。

## 陷阱

!!! pitfall "重载 `&&`、`||`、`,` 会丢失特殊求值语义"
    重载后不再短路，两侧都会求值。表达式模板库（如某些 DSL）有意这样做；普通代码不应这样做。

!!! pitfall "成员二元运算符导致不对称"
    `x + 1` 能编译而 `1 + x` 不能，因为左操作数是对象形参，不做用户定义转换。对称运算符写成隐藏友元。

!!! pitfall "以为派生类继承了基类的 `operator=`"
    其他运算符都能继承，唯独 `operator=` 总被派生类隐式声明的拷贝赋值隐藏，需要 `using Base::operator=;`。

!!! pitfall "后缀形参写成 `long` 或给默认值"
    后缀 `++`/`--` 的哑形参必须恰好是 `int`，且不得有默认实参。

!!! pitfall "在泛型代码中使用 `&x` 或 `a, b`"
    操作数类型可能重载了一元 `&` 或 `,`。用 `std::addressof(x)` 与 `(void)a, b`。

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

- (a) OK：复合赋值不是 [[over.assign]] 意义下的简单赋值，按 ¶11 是普通二元运算符，可以是非成员。
- (b)(c) OK：¶7 明确允许为枚举重定义 `,` 与一元 `&`。
- (d) 非良构：`operator=` 必须是非静态成员函数，而枚举不能有成员，所以枚举的赋值语义无法改变。
- (e) OK：`->*` 是普通二元运算符，可以是非成员（与 `->` 不同）。
- (f) OK（C++23）：静态、多参数的下标运算符。
- (g) 非良构：二元运算符函数必须是非静态成员或非成员；`static` 只对 `()` 和 `[]` 开放。
</details>

!!! question "2. 为什么 `operator()` 和 `operator[]` 可以是静态的，而 `operator+` 不行？"

<details markdown="1">
<summary>答案</summary>

在 `f(args)` 与 `a[args]` 中，左边的 `f`、`a` 只是被调用或被索引的对象，实参列表是圆括号或方括号里的那些表达式。静态成员版本把对象当作隐含对象实参，与静态成员函数的隐式对象形参匹配后丢弃（[[over.match.funcs.general#4]]），实参列表依然完整。而 `a + b` 的两个操作数地位对等，成员形式中左操作数就是对象形参所代表的实参；静态成员没有对象形参，左操作数就无处安放，元数对不上 [[over.binary]] 的要求。
</details>

!!! question "3. `x->m` 看起来有两个操作数，为什么 [over.ref] 把 `operator->` 定义为没有非对象形参的函数，而不是像 `->*` 那样的二元运算符？"

<details markdown="1">
<summary>答案</summary>

`->` 的右侧是成员名（*id-expression*），不是一个能求值、能作实参的表达式，把它当作 `operator->` 的实参毫无意义。所以 [[over.ref]] 把 `x->m` 改写为 `(x.operator->())->m`：`operator->` 只负责给出一个可以继续应用 `->` 的结果，成员名留到最后由内建 `->` 处理（[[over.match.oper#12]] 也规定在选择 `operator->` 时忽略第二操作数）。这也是 `operator->` 的返回类型最终必须下钻到原生指针的原因。
</details>

## 小结

!!! summary
    - 运算符函数至少要有一个类/枚举（或其引用）类型的形参或隐式对象形参，因此内建类型上的运算无法被改变。
    - 优先级、结合性、元数都不能改；除 `()`、`[]` 外不得有默认实参。
    - `.`、`.*`、`::`、`?:` 不能重载；`&&`、`||`、`,`、一元 `&` 能重载但会失去内建的特殊语义。
    - `=`、`()`、`[]`、`->` 只能是成员；其中 `()`、`[]` 从 C++23 起可以是静态成员、可以有任意多个形参。
    - `->` 逐层下钻到原生指针；后缀 `++`/`--` 以 `int` 哑形参区分，经运算符调用时实参为 0；C++26 之后可以 `= default`。
