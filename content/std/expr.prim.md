---
title: 基本表达式
summary: 表达式文法的"原子"：字面量、this、括号表达式、名字、lambda、折叠表达式、requires 表达式与 splice 表达式；本页讲总览、字面量、this 与括号。
status: draft
covers: expr.prim.grammar, expr.prim.literal, expr.prim.this, expr.prim.paren
related: expr.prim.id, expr.prim.lambda, expr.prim.fold, expr.prim.req, expr.prim.splice, basic.lval, dcl.type.decltype
tags: 表达式, 值类别, this
updated: 2026-10-17
---

**基本表达式**（primary expression）是表达式文法里最底层的一层：后缀表达式（[[expr.post]]）、一元表达式（[[expr.unary]]）……一路往上，最终都要落到某个 *primary-expression* 上。它们是"不再由别的运算符组合出来"的表达式——或者说，是一切运算符的操作数的起点。

这一节（[expr.prim]，7.5）把八种完全不同的东西放在一起：

| 文法分支 | 例子 | 本站页面 |
|---|---|---|
| *literal* | `42`、`"abc"`、`1.5_km` | 本页 |
| `this` | `this` | 本页 |
| `( expression )` | `(x)` | 本页 |
| *id-expression* | `x`、`N::x`、`~T`、`p...[0]` | [[expr.prim.id]] |
| *lambda-expression* | `[&](int i) { return i + n; }` | [[expr.prim.lambda]] |
| *fold-expression* | `(... + args)` | [[expr.prim.fold]] |
| *requires-expression* | `requires (T t) { t + t; }` | [[expr.prim.req]] |
| *splice-expression* {{c++26}} | `[: ^^x :]` | [[expr.prim.splice]] |

它们共同的"基本"之处只在文法上：它们都可以直接作为后缀运算符（`()`、`[]`、`.`、`->`、`++`）的左操作数而无需加括号。一个 lambda 可以立刻被调用（`[]{ return 1; }()`），一个折叠表达式自带括号，`requires { ... }` 可以直接放进 `&&` 两侧——都源于这一点。

阅读本页前最好熟悉 **值类别**（[[basic.lval]]）：本节几乎每一条规则都在回答同一个问题——"这个表达式的**类型**和**值类别**是什么"。

## 文法（[expr.prim.grammar]）

¶ 文法只有一条产生式，列出上表八个分支。几个值得注意的地方：

- *id-expression* 在这里只是"一种可能"：它同样会出现在 `.` 与 `->` 之后（[[expr.ref]]），那时它不是 primary-expression，而是成员访问的一部分——这就是为什么 [[expr.prim.id]] 的许多规则要特意排除"作为类成员访问的 *id-expression*"。
- 折叠表达式的括号是**文法的一部分**，不是 `( expression )` 分支。`... + args` 不加括号根本不是表达式。
- *requires-expression* 是 primary-expression，所以 `requires { ... } && C<T>` 无需括号；但在 *requires-clause* 中能直接出现的 primary-expression 受 [[temp.pre]] 的限制，这是 `requires requires` 这个怪异写法的来源（见 [[expr.prim.req]]）。

## 字面量（[expr.prim.literal]）

¶1 字面量的**类型**由它的书写形式决定，细节全在词法章节 [[lex.literal]]：`42` 是 `int`、`42u` 是 `unsigned int`、`'a'` 是 `char`、`1.0f` 是 `float`、`nullptr` 是 `std::nullptr_t`、`true` 是 `bool`……本条只补充**值类别**：

| 字面量 | 值类别 | 说明 |
|---|---|---|
| *string-literal* | **lvalue** | 指代一个具有静态存储期的数组对象（[[lex.string]]） |
| *user-defined-literal* | 与对应的 `operator""` 调用表达式相同 | 由 [[lex.ext]] 改写成函数调用，返回引用就可能是 lvalue/xvalue |
| 其他一切字面量 | **prvalue** | 整数、浮点、字符、布尔、`nullptr` |

为什么字符串字面量偏偏是 lvalue？因为它确实**是一个对象**：`"abc"` 是一个 `const char[4]` 数组，有地址、可以绑定到 `const char(&)[4]`。而 `42` 只是一个值，在被物化（[[conv.rval]]）之前不占存储——这正是 C++17 后 prvalue 的含义。

```cpp run ok
#include <type_traits>

static_assert(std::is_same_v<decltype("ab"), const char(&)[3]>);  // lvalue → decltype 给出 T&
static_assert(std::is_same_v<decltype(42), int>);                  // prvalue → 不带引用
static_assert(std::is_same_v<decltype(u8"x"), const char8_t(&)[2]>);
static_assert(std::is_same_v<decltype(nullptr), std::nullptr_t>);

const char (*p)[4] = &"abc";   // OK：可以对字符串字面量取地址
// int* q = &42;               // error: 不能对 prvalue 取地址

int main() { }
```

!!! note "同一个字面量是不是同一个对象？"
    "abc" 求值两次是否得到同一个对象、两个不同的字符串字面量是否共享存储（例如 `"abc"` 与 `"bc"` 尾部重叠），都是**未指定**的（[[lex.string]]）。因此不要比较字符串字面量的地址。

用户定义字面量的值类别"跟随"它被改写成的函数调用：

```cpp run ok
#include <type_traits>

struct Reg { int v; };
Reg  table[4];
Reg& operator""_reg(unsigned long long i) { return table[i]; }
Reg  operator""_val(unsigned long long i) { return Reg{int(i)}; }

static_assert(std::is_same_v<decltype(2_reg), Reg&>);  // lvalue：operator"" 返回左值引用
static_assert(std::is_same_v<decltype(2_val), Reg>);   // prvalue

int main() { (3_reg).v = 7; }   // 对 lvalue 的成员赋值，OK
```

!!! lawyer "为什么要写 `(3_reg).v`"
    如果写成 `3_reg.v = 7;`，预处理记号化时 `3_reg.v` 会被整体当作**一个** pp-number（pp-number 可以包含 `.` 和标识符字符，[[lex.ppnumber]]），于是变成一个"后缀为 `_reg.v`"的用户定义字面量，找不到对应的字面量运算符而报错。这与 [[expr.prim.id.dtor]] 中 `0.T::~T()` 的陷阱同源。加括号或空格（`3_reg .v`）即可。

## this（[expr.prim.this]）

### this 指向谁（¶1）

¶1 关键字 `this` 命名一个指针，指向

- 正在被调用的**隐式对象成员函数**（implicit object member function，即传统的非静态成员函数，见 [[class.mfct.non.static]]）所作用的对象，或
- 正在对其求值**非静态数据成员初始化器**（default member initializer，[[class.mem]]）的对象。

注意"命名一个指针"：`this` 是 **prvalue**，不是变量。你不能 `this = nullptr;`，也不能 `&this`。这与早期 C++（Cfront 时代 `this` 可以被赋值来实现自定义分配）不同。

### 当前类（¶2）

¶2 [[g:current-class|**当前类**]]（current class）：某程序点处，包含该点的最内层类作用域所关联的类。注释特意强调：**lambda 表达式不引入类作用域**。所以在成员函数里写的 lambda，其函数体中的"当前类"仍是外层类，而**不是**闭包类型——这就是为什么 lambda 体内的 `this` 指向外层对象（[[expr.prim.lambda.closure#16]]）。

与之对照，局部类（在成员函数内部定义的 `struct Inner`）**会**引入新的类作用域，所以在 `Inner` 的成员里，`this` 是 `Inner*`。

### 契约断言中的 this {{c++26}}（¶3）

¶3 如果 `this` 出现在契约断言（[[basic.contract.general]]，`pre`/`post`/`contract_assert`）的谓词中，且当前类包围该断言，那么用来生成 `this` 类型的 cv 限定**额外加上 `const`**。这包括隐式变换产生的 `this`（谓词里写 `m` 实际上是 `(*this).m`，见 [[expr.prim.id.general#2]]）以及嵌套 lambda 体内的 `this`。

动机：契约谓词应当是"只读的观察"。C++26 契约设计里把谓词中引用的外部变量都视为 const（见 [[expr.prim.id.unqual#7]]），`*this` 也不例外——即便在非 const 成员函数里，`pre(this->mutate())` 也会因为调用了非 const 成员函数而非良构。在 C++23 及以前没有契约，也就没有这条规则。

### 成员函数中 this 的类型（¶4）

¶4 若声明是类 `X` 的成员函数（或成员函数模板），那么从**可选 cv-qualifier-seq 之后**直到函数定义/声明符结束，`this` 是"指向 *cv* `X` 的指针"类型的 prvalue：

!!! std
    the expression `this` is a prvalue of type "pointer to *cv-qualifier-seq* `X`" wherever `X` is the current class between the optional *cv-qualifier-seq* and the end of the *function-definition*, *member-declarator*, or *declarator*.

    `this` 的有效区间从 cv 限定符之后开始——因此能出现在尾置返回类型、noexcept 说明、函数体里，但不能出现在参数列表（例如默认实参）里。

几个要点：

1. **只有 cv，没有引用限定**。`void f() const &&` 里 `this` 仍是 `const X*`。引用限定符只影响重载决议中隐式对象参数的类型（[[over.match.funcs]]），`*this` 本身永远是 lvalue。
2. **有效区间从 cv 之后开始**，所以可以写 `auto f() -> decltype(this)`、`void f() noexcept(noexcept(this->g()))`；但不能写 `void f(X* p = this)`——默认实参在 cv 之前（[[dcl.fct.default]] 也另行禁止了这一点）。
3. **静态成员函数和显式对象成员函数**（[[dcl.fct]] 中的 explicit object parameter，即 C++23 "deducing this"）的声明中**不得出现 `this`**。标准用了一个有趣的说法：在这些函数里 `this` 的类型与值类别"如同在隐式对象成员函数中一样有定义"，只是不允许出现。为什么要先定义再禁止？注释 2 解释：**声明匹配要等整个声明符看完才发生**——编译器读到 `auto f() -> decltype(this)` 时还不知道 `f` 是不是静态函数（`static` 可能只出现在类内首次声明上，类外定义没有 `static`），所以 `this` 的类型必须先按普通成员函数来确定，之后再检查"不得出现"的约束。

```cpp run ok
#include <type_traits>

struct X {
  void f()                { static_assert(std::is_same_v<decltype(this), X*>); }
  void g() const          { static_assert(std::is_same_v<decltype(this), const X*>); }
  void h() volatile &     { static_assert(std::is_same_v<decltype(this), volatile X*>); }  // & 不影响
  auto k() -> decltype(this) { return this; }   // OK：尾置返回类型在 cv 之后
  int  n = sizeof(*this);                       // OK：默认成员初始化器（¶5）
  X*   self = this;                             // OK
};
static_assert(std::is_same_v<decltype(&X::k), X* (X::*)()>);

int main() { }
```

```cpp error
struct Y {
  static void s() { (void)this; }        // error: 静态成员函数中不能出现 this
  void e(this Y& self) { (void)this; }   // error: 显式对象成员函数中不能出现 this，应使用 self
  void d(Y* p = this);                   // error: 默认实参在 cv-qualifier-seq 之前
  static auto t() -> decltype(this);     // error: 静态成员函数的声明中
};
```

!!! note "deducing this 为什么禁用 this"
    显式对象成员函数 `void f(this Self&& self)` 本质上更像一个"第一个参数特殊的静态函数"：调用对象经由 `self` 传入，且 `Self` 可能被推导为派生类类型。若同时允许 `this`，它应该是 `X*` 还是 `Self*`？对派生类对象调用时 `this` 与 `&self` 会不一致。禁止 `this`、强制通过 `self` 访问，是唯一不会产生歧义的选择。同理，函数体里的裸成员名 `m` 也**不会**被变换成 `this->m`——[[expr.prim.id.general#2]] 的注释说这种访问非良构，必须写 `self.m`。

注释 3 的例子说明了尾置返回类型中的特殊性：类在那里尚不完整，但成员访问仍然允许（不要求完整类），只是**还没声明的成员不可见**。

```cpp ok
struct A {
  char g();
  template<class T> auto f(T t) -> decltype(t + g())   // g() 即 this->g()，A 此时不完整也 OK
    { return t + g(); }
};
template auto A::f(int t) -> decltype(t + g());        // 类外显式实例化：g 同样可用
```

### 默认成员初始化器中的 this（¶5）

¶5 非静态数据成员的**默认成员初始化器**里，`this` 是 `X*`（没有 cv——构造过程中对象还不是 const，[[class.ctor]]）。这使得 `X* self = this;`、`std::size_t n = sizeof(*this);`、`Callback cb{this};` 之类的写法合法。

注意它只覆盖"初始化器"部分。数组边界 `int a[sizeof(*this)];` 不在初始化器内，不合法。

### 其余位置一律禁止（¶6）

¶6 除 ¶4、¶5 列出的位置外，`this` 不得出现。标准的例子值得仔细读：

```cpp error
class Outer {
  int a[sizeof(*this)];               // error: 不在成员函数内（数组边界不是初始化器）
  unsigned int sz = sizeof(*this);    // OK：默认成员初始化器

  void f() {
    int b[sizeof(*this)];             // OK：在 Outer::f 内，this 是 Outer*

    struct Inner {
      int c[sizeof(*this)];           // error: 当前类是 Inner，而这里不在 Inner 的成员函数内
    };
  }
};
```

`Inner` 那一行最有教学意义：虽然它在 `Outer::f` 的函数体里，但"当前类"（¶2）已经变成了 `Inner`，而 `Inner` 的数组边界不是 ¶4/¶5 中的任何位置。¶4 说的是"`X` 是当前类时"——`Outer::f` 的 `this` 不会"穿透"进局部类。

lambda 就不一样了——它不引入类作用域，所以 lambda 体里的 `this` 仍然"来自"外层成员函数，但需要被**捕获**（[[expr.prim.lambda.capture]]）：

```cpp
struct Z {
  int v = 0;
  void f() {
    auto l1 = [this] { return v; };        // OK：this 是 Z*，v 即 this->v
    auto l2 = []     { return v; };        // error: this 未被捕获
    struct Inner { int x = sizeof(*this); };  // OK：this 是 Inner*
  }
};
```

## 括号表达式（[expr.prim.paren]）

¶1 `(E)` 是一个基本表达式，其**类型、结果、值类别**与 `E` 完全相同；可以用在 `E` 能用的一切上下文中、含义相同——"除非另有说明"。

这条规则本身平淡无奇——括号只改变**分组**，不改变表达式本身。真正值得 language lawyer 关注的是那句"除非另有说明"。以下是标准中括号会改变含义的地方（不完全列表）：

| 上下文 | `E` | `(E)` | 出处 |
|---|---|---|---|
| `decltype` | `decltype(x)`：变量 `x` 的**声明类型** | `decltype((x))`：按表达式规则，lvalue → `T&` | [[dcl.type.decltype]] |
| `decltype(auto)` 推导 | `return x;` → `T` | `return (x);` → `T&`（常见悬垂引用来源） | [[dcl.type.auto.deduct]] |
| 取成员指针 | `&S::m` → `int S::*` | `&(S::m)` → 不是成员指针；在 `S` 的成员函数内是 `int*`（即 `&this->m`），否则非良构 | [[expr.unary.op]]、[[expr.prim.id.general#2]] |
| 函数调用中的 ADL | `f(a)` 进行实参依赖查找 | `(f)(a)` **不**进行 ADL | [[basic.lookup.argdep]] |
| 模板实参中的 `>` | `A<1>2>` 解析失败 | `A<(1>2)>` OK | [[temp.names]] |
| splice 作模板实参 {{c++26}} | `e<[:r:]>` 非良构 | `e<([:r:])>` OK | [[expr.prim.splice#1]] |
| 结构化绑定 / 位域 | — | 括号**不会**去掉位域属性：`(b.bf)` 仍是位域 | 本条 |

而**不**改变含义的典型例子（正因为 ¶1）：

- **隐式移动**：`return (x);` 中 `(x)` 依然是 move-eligible 的——[[expr.prim.id.unqual#15]] 明确写了"possibly parenthesized"。
- **值类别**：`(x)` 和 `x` 都是 lvalue；`(std::move(x))` 依然是 xvalue。
- **位域**：`int& r = (b.bf);` 和 `int& r = b.bf;` 一样非良构。

```cpp run ok
#include <type_traits>

int x = 0;
static_assert(std::is_same_v<decltype(x),   int>);    // 实体的声明类型
static_assert(std::is_same_v<decltype((x)), int&>);   // 表达式 (x) 是 int 类型 lvalue

decltype(auto) r1() { return x; }     // int
decltype(auto) r2() { return (x); }   // int&  —— 若 x 是局部变量就悬垂了
static_assert(std::is_same_v<decltype(r1()), int>);
static_assert(std::is_same_v<decltype(r2()), int&>);

struct S {
  int m;
  void k() {
    auto p = &(S::m);                               // 在成员函数中：等价于 &(this->m)
    static_assert(std::is_same_v<decltype(p), int*>);
  }
};
int S::* pm = &S::m;                                // 不带括号：成员指针

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
auto q = &(S::m);   // error: 非成员上下文中，S::m 不能这样使用（不是成员指针）
```

!!! tip "为什么 `(std::max)(a, b)`"
    Windows 头文件把 `max` 定义为函数式宏。函数式宏只有在名字**后面紧跟** `(` 时才会展开，写成 `(std::max)(a, b)` 就绕开了宏。这是预处理层面的技巧，不是 [expr.prim.paren] 的规则，但顺带也会抑制 ADL（对限定名本来就不做 ADL）。

!!! lawyer "括号与声明"
    "最令人烦恼的解析"（most vexing parse）里加括号消歧，例如 `T x((T()));`，处理的是**声明/表达式歧义**（[[stmt.ambig]]、[[dcl.ambig.res]]），不是本条的内容：多一层括号让它不可能被解析为参数声明。一旦确定它是表达式，括号就回到"什么都不改变"。

## 实现视角

!!! impl
    - **this 的传递**：在 Itanium C++ ABI（GCC/Clang 在 Linux/macOS 上）和 MSVC x64 中，隐式对象成员函数的 `this` 都作为第一个（隐藏）参数传递；在 x86-64 System V 中即 `rdi`。显式对象成员函数的 `self` 是一个**普通**的第一个参数，可以按值传递（`this Self self`）——这时调用约定与 `this` 指针完全不同，是 deducing this 带来的一个可观察的 ABI 差异。
    - **字符串字面量合并**：GCC/Clang 默认把相同内容的字符串字面量放进可合并的只读段（`.rodata.str1.1`，带 `SHF_MERGE`），因此链接后往往同址；但这只是实现选择，标准不保证（[[lex.string]]）。
    - **诊断**：Clang 对 `this` 的误用会区分"静态成员函数中""显式对象参数函数中""未捕获"等不同情形分别报错，这正好对应本条 ¶4、¶6 与 [[expr.prim.lambda.capture]] 的不同规则。

## 历史与演进

!!! history
    - **C++98**：`this` 只能出现在非静态成员函数体和 mem-initializer 中；没有默认成员初始化器，也没有尾置返回类型。
    - **C++11**：引入**默认成员初始化器**（`this` 可出现其中）和**尾置返回类型**（`this` 可出现在 cv 之后的 `-> decltype(this->x)` 中）；引入 lambda，`this` 需要捕获。`decltype((x))` 与 `decltype(x)` 的区分也是 C++11 的设计。
    - **C++14**：`decltype(auto)` 让"`return (x);` 返回引用"这个括号陷阱进入日常代码。
    - **C++23**：显式对象参数（deducing this）——这些函数中禁止 `this`。
    - **C++26**：契约断言谓词中 `this` 额外 const 化（¶3）；splice 表达式加入文法，并新增"作为模板实参时须加括号"的要求。

## 陷阱

!!! pitfall "decltype(auto) + 括号 = 悬垂引用"
    ```cpp
    decltype(auto) get() {
      int local = 42;
      return (local);   // 返回 int&，指向已销毁的局部变量；调用方读取即 UB
    }
    ```
    Clang/GCC 通常会对此发出"返回局部变量的引用"警告，但别指望每次都能检出（比如经过结构化绑定或成员访问后）。

!!! pitfall "`*this` 永远是 lvalue"
    即使在 `&&` 限定的成员函数里，`*this` 也是 lvalue。想把自身当右值转发出去，要写 `std::move(*this)`；在 C++23 之后更好的办法是用 deducing this：`void f(this Self&& self)` 再 `std::forward<Self>(self)`。

!!! pitfall "局部类不继承外层的 this"
    在成员函数里定义的局部类、局部类的默认成员初始化器中，`this` 指向**局部类**对象。想访问外层对象，需要显式传入指针。

## 思考题

!!! question "思考题 1"
    下面哪几行良构？
    ```cpp
    struct A {
      int v;
      auto f() const -> decltype((v));           // #1
      auto g() -> decltype(this->v);              // #2
      static auto h() -> decltype(sizeof(v));     // #3
    };
    ```

<details markdown="1">
<summary>答案</summary>

- `#1` 良构：`v` 被变换为 `(*this).v`（[[expr.prim.id.general#2]]），在 `const` 成员函数的 cv 之后，`this` 是 `const A*`，于是 `decltype((v))` 是 `const int&`。
- `#2` 良构：`decltype(this->v)` 是成员访问表达式的 decltype，给出成员的声明类型 `int`。
- `#3` 是一个**标准措辞与实现有分歧**的点。按当前草案 [[expr.prim.id.general#2]]：`v` 是当前类 `A` 自己的非静态成员，条件 (2.1) 的后半"C 是 X"成立，所以即使在未求值操作数里也会被变换成 `(*this).v`；而注释 2 明说在静态成员函数中这种类成员访问非良构（¶4 也说 `this` 不得出现在静态成员函数的声明中）。因此按字面 `#3` **非良构**。Clang 拒绝 `#3`（报告不能在静态成员函数**声明**中隐式使用 `this`），但对**函数体**中的 `static int h2() { return sizeof(v); }` 却接受——后者对应 C++11 的旧措辞"仅在可以使用 `this` 的上下文中才做变换"。注意改用限定名 `sizeof(A::v)` 并不能绕开（(2.4) 只豁免作为 `&` 操作数的限定名）；无争议的写法是 `sizeof(std::declval<A&>().v)`，或直接写类型。详见 [[expr.prim.id]] 页的讨论。
</details>

!!! question "思考题 2"
    `(E)` 与 `E` "类型、结果、值类别都相同"，那为什么 `decltype((x))` 与 `decltype(x)` 会不同？这和 ¶1 矛盾吗？

<details markdown="1">
<summary>答案</summary>

不矛盾。`decltype` 有两套规则（[[dcl.type.decltype]]）：当操作数是**不加括号的** *id-expression* 或类成员访问时，给出所命名实体的**声明类型**；否则按表达式的类型与值类别计算（lvalue → `T&`）。`x` 与 `(x)` 作为表达式确实完全相同（都是 `int` 类型的 lvalue），区别在于 `decltype` 这个上下文**查看了语法形式**——这正是 ¶1 "除非另有说明"所预留的例外。
</details>

## 小结

!!! summary
    - 基本表达式是表达式文法的叶子：字面量、`this`、`(E)`、名字、lambda、折叠、requires、splice。
    - 字符串字面量是 **lvalue**（它是数组对象）；用户定义字面量跟随其 `operator""` 调用；其余字面量是 prvalue。
    - `this` 是 **prvalue**，类型为"指向 cv `X` 的指针"（只有 cv，没有引用限定）；只能出现在隐式对象成员函数的 cv 之后到声明结束、以及默认成员初始化器中。静态成员函数与显式对象成员函数中禁止使用 `this`。{{c++26}} 契约谓词中 `this` 额外加 const。
    - lambda 不引入类作用域，局部类会——这决定了 `this` 指向谁。
    - `(E)` 与 `E` 在类型、值类别上完全相同；差别只出现在"另有说明"的上下文：`decltype`、`decltype(auto)`、`&(S::m)`、`(f)(a)` 抑制 ADL、模板实参中的 `>` 与 splice。
