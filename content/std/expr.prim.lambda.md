---
title: lambda 表达式
summary: lambda 表达式如何生成闭包类型与闭包对象：调用运算符的属性（const/mutable/static/constexpr/consteval、泛型、显式对象参数）、向函数指针的转换、特殊成员函数，以及捕获的全部规则——隐式与显式、按值与按引用、init-capture、*this、odr-usable 与悬垂。
status: draft
covers: expr.prim.lambda.general, expr.prim.lambda.closure, expr.prim.lambda.capture
papers: P0018R3, P0170R1, P0588R1, P0428R2, P0624R2, P0315R4, P0780R2, P0806R2, P1091R3, P1381R1, P1102R2, P1169R4, P0847R7, P2173R1, P2036R3
related: expr.prim.id, basic.def.odr, basic.scope.lambda, dcl.fct, dcl.spec.auto, class.copy.ctor, depr.capture.this, temp.variadic
tags: lambda, 闭包, 捕获, odr-use, 泛型编程
updated: 2026-10-17
---

lambda 表达式是 C++ 中"就地定义一个函数对象"的语法。标准对它的描述方式非常值得学习：**它不引入新的运行时概念**，而是规定一个 lambda 表达式等价于（a）定义一个独一无二的类——[[g:closure-type|**闭包类型**]]（closure type），并（b）创建该类的一个 prvalue 对象——[[g:closure-object|**闭包对象**]]（closure object）。几乎所有 lambda 的性质，都可以通过"想象编译器为你写了这个类"推出来：

```cpp
void demo() {
  int n = 10;
  auto add = [n](int x) { return x + n; };

  // 大致等价于：
  class __Closure {
    int __n;                                   // 按值捕获 → 一个无名非静态数据成员
  public:
    __Closure(int n) : __n(n) {}               // （仅为示意：闭包实际上没有这样的构造函数）
    auto operator()(int x) const { return x + __n; }   // 默认 const
  };
  auto add2 = __Closure{n};
}
```

本页对应标准的三个子条款：

- **[expr.prim.lambda.general]**：文法、lambda 说明符（`mutable`/`constexpr`/`consteval`/`static`）、返回类型推导、泛型 lambda。
- **[expr.prim.lambda.closure]**：闭包类型有哪些成员、性质、何时可转换为函数指针、特殊成员函数。
- **[expr.prim.lambda.capture]**：捕获——哪些实体被捕获、如何捕获、捕获之后名字指什么、何时初始化。

前置知识：**odr-use** 与 **odr-usable**（[[basic.def.odr#10]]）是理解捕获的钥匙；lambda 作用域（[[basic.scope.lambda]]）；显式对象参数（[[dcl.fct]]）；占位符类型推导（[[dcl.spec.auto]]）。

## 文法总览（[expr.prim.lambda.general]）

一个 lambda 表达式的完整形态（C++26）：

```text
[ 捕获 ] <模板形参>  requires-clause  属性  ( 形参 )  说明符  noexcept  属性  -> 返回类型  requires-clause  契约  { 函数体 }
  ①        ②           ③            ④      ⑤       ⑥       ⑦       ⑧       ⑨           ⑩            ⑪      ⑫
```

除了 ① 和 ⑫，其余全部可选。值得注意的细节：

- ② 模板形参列表 {{c++20}}：`[]<class T>(T a) {}`。
- ④ 位于 lambda 声明符**之前**的属性 {{c++23}} 作用于调用运算符本身（如 `[] [[nodiscard]] () { ... }`）；⑧ 位于声明符中的属性作用于调用运算符的**类型**（¶7）。
- ⑤ 形参列表可以省略。C++23 起，即使有说明符、`noexcept`、尾置返回类型，也可以省略 `()`：`[] mutable { }`、`[] noexcept { }` 都合法（C++20 中必须写 `[]() mutable { }`）。
- ⑪ 契约说明符 {{c++26}}：`[](int x) pre(x > 0) { ... }`。

### 闭包对象（¶1–2）

¶1 lambda 表达式提供了一种简洁的方式来创建简单的函数对象。¶2 lambda 表达式是一个 **prvalue**，其结果对象叫做**闭包对象**。因为是 prvalue，`auto f = [] {};` 中由于强制复制消除（[[dcl.init]]），`f` 就是那个闭包对象本身，不涉及拷贝或移动。

### 属性的歧义（¶3）

¶3 一个 *requires-clause* 可能以 *attribute-specifier-seq* 结尾（例如 `requires T::operator int [[attr]]`，其中 `[[attr]]` 可以被看成转换函数 id 的一部分），这与 lambda 声明符之前的属性冲突。规则：**一律当作 lambda 的属性**。注释指出这类歧义情形本来就没有合法语义（约束表达式类型不会是 `bool`），所以这个选择不会让任何有意义的程序变坏。

### lambda 说明符的组合规则（¶4）

¶4 *lambda-specifier-seq* 中：

- 每个说明符至多出现一次；`constexpr` 与 `consteval` 不能同时出现；
- 若有**显式对象参数**，不能有 `mutable` 或 `static`（`mutable` 的含义"调用运算符非 const"由 `self` 的类型表达，`static` 则与"有对象参数"矛盾）；
- `mutable` 与 `static` 不能同时出现；
- 有 `static` 时不能有任何捕获（静态成员函数没有对象，无从访问捕获成员）。

```cpp error
auto e1 = [](int) constexpr consteval {};   // error: constexpr 与 consteval 不能共存
auto e2 = [](this auto) mutable {};         // error: 显式对象参数 + mutable
auto e3 = [](this auto) static {};          // error: 显式对象参数 + static
auto e4 = [](int) mutable static {};        // error: mutable + static
void f() {
  int x = 0;
  auto e5 = [x](int) static { return x; };  // error: static lambda 不能有捕获
}
```

### 返回类型（¶5）

¶5 lambda 的形参子句就是其声明符中的形参子句（没有声明符时为空）。**没有尾置返回类型时，视为 `-> auto`**，于是返回类型按 [[dcl.spec.auto]] 从 `return` 语句推导——这意味着：

- 多个 `return` 推导出的类型必须一致；
- `return {1, 2};` 无法推导（花括号初始化列表不能推导 `auto` 返回类型）；
- 推导结果永远不是引用（`auto` 会退化）；想返回引用需写 `-> auto&`、`-> decltype(auto)` 等。

```cpp
void f() {
  auto x1 = [](int i) { return i; };       // OK：返回 int
  auto x2 = [] { return { 1, 2 }; };       // error: 不能从花括号初始化列表推导返回类型
  int j;
  auto x3 = [&]() -> auto&& { return j; }; // OK：返回 int&
}
```

!!! history "C++11 的返回类型推导"
    C++11 中，没有尾置返回类型的 lambda 只有在函数体**仅由一条 `return 表达式;`** 构成时才推导返回类型，否则返回 `void`。C++14 统一为普通函数的 `auto` 返回类型推导规则。

### 泛型 lambda（¶6）

¶6 一个 lambda 是[[g:generic-lambda|**泛型 lambda**]]（generic lambda），当且仅当它有泛型形参类型占位符（`auto` 形参，[[dcl.spec.auto]]），或者有模板形参列表。注意 `[](this auto self, int i)` 也是泛型 lambda——显式对象参数 `this auto` 本身就是一个 `auto` 占位符。

```cpp ok
auto x = [](int i, auto a) { return i; };           // 泛型：auto 形参
auto y = [](this auto self, int i) { return i; };   // 泛型：this auto
auto z = []<class T>(int i) { return i; };          // 泛型：模板形参列表（T 无法推导，调用需写 z.operator()<int>(0)）
```

## 闭包类型（[expr.prim.lambda.closure]）

### 独一无二的无名类（¶1–3）

¶1 lambda 表达式的类型（也就是闭包对象的类型）是一个**独一无二的、无名的、非联合体类类型**，叫做闭包类型。"独一无二"是字面意义的：**每个 lambda 表达式都有自己的类型**，即使两段代码逐字相同；同一个 lambda 表达式在模板的不同实例化中也会产生不同的类型。

¶2 闭包类型在其复合语句（函数体）结束前是**不完整**的。所以在 lambda 体内不能对闭包类型做 `sizeof` 之类需要完整类型的操作（不过 lambda 体内本来也无法直接命名闭包类型，除非借助 `this auto self` 的 `decltype(self)`）。

¶3 闭包类型被声明在包含该 lambda 表达式的**最小的块作用域、类作用域或命名空间作用域**中。注释说明这决定了 ADL 的关联命名空间和类（[[basic.lookup.argdep]]），而形参类型**不**影响关联命名空间。

```cpp run ok
#include <type_traits>

auto a = [] { return 1; };
auto b = [] { return 1; };
static_assert(!std::is_same_v<decltype(a), decltype(b)>);   // 每个 lambda 一个类型

using T1 = decltype([] {});     // C++20：lambda 可以出现在未求值操作数中
using T2 = decltype([] {});
static_assert(!std::is_same_v<T1, T2>);                     // 依然各不相同

int main() { }
```

### 不是聚合、不是 final、结构化类型（¶4）

¶4 闭包类型：

- **不是聚合**（[[dcl.init.aggr]]）——所以不能用 `{...}` 聚合初始化来"伪造"一个闭包对象并填入捕获成员；
- **不是 final**——可以从闭包类型派生，这正是著名的 `overloaded` 惯用法的基础；
- 是**结构化类型**（structural type，[[temp.param]]）当且仅当没有 *lambda-capture*——所以无捕获的 lambda 可以作为非类型模板实参。

!!! std
    The closure type is not an aggregate type and is not final; it is a structural type if and only if the lambda has no *lambda-capture*.

    闭包不是聚合、不是 final；无捕获时是结构化类型，可作 NTTP。

```cpp run ok
#include <cstdio>
#include <string>
#include <type_traits>
#include <variant>

template<class... Fs> struct overloaded : Fs... { using Fs::operator()...; };  // 从闭包类型派生

template<auto F> int call() { return F(); }      // 无捕获 lambda 作为 NTTP（C++20）

int main() {
  static_assert(!std::is_aggregate_v<decltype([] {})>);
  static_assert(!std::is_final_v<decltype([] {})>);

  std::variant<int, std::string> v = std::string("hi");
  std::visit(overloaded{[](int i) { std::printf("int %d\n", i); },
                        [](const std::string& s) { std::printf("str %s\n", s.c_str()); }}, v);

  std::printf("%d\n", call<[] { return 42; }>());
}
```

¶4 的后半给了实现很大的自由：实现可以用与下文描述**不同**的方式定义闭包类型，只要除了以下三点之外不改变可观察行为：

- (4.1) 闭包类型的大小和/或对齐；
- (4.2) 是否可平凡复制（trivially copyable）；
- (4.3) 是否是标准布局类。

但实现**不得**向闭包类型添加右值引用类型的成员。

换言之：**不要依赖** `sizeof(lambda)`、`std::is_trivially_copyable_v<闭包>`、`std::is_standard_layout_v<闭包>` 的结果在不同编译器之间一致。按引用捕获在实践中通常实现为存一个指针（或者对多个引用捕获只存一个栈帧指针），这都是允许的。

### 函数调用运算符（¶5–9）

¶5 闭包类型有一个 **public、inline** 的函数调用运算符（非泛型 lambda）或函数调用运算符**模板**（泛型 lambda），其形参与返回类型来自 lambda 的形参子句与尾置返回类型；模板形参列表就是写出的那个（再加上 `auto` 形参生成的发明模板形参——它是一个**简写函数模板**，[[dcl.fct]]）。`<...>` 之后的 *requires-clause* 成为模板的 requires-clause；声明符末尾的 *requires-clause* 成为尾置 requires-clause。调用运算符是闭包类型的**直接成员**。

标准例子展示了泛型 lambda 的嵌套与包展开（`[=](auto&&... ts)` 中 `ts` 是函数形参包，内层 `[=]` 隐式按值捕获整个包），以及用显式对象参数实现递归：

```cpp run ok
#include <iostream>
#include <utility>

int main() {
  auto vglambda = [](auto printer) {
    return [=](auto&&... ts) {                       // ts 是函数形参包
      printer(std::forward<decltype(ts)>(ts)...);
      return [=]() { printer(ts...); };              // 隐式按值捕获 printer 和整个包 ts
    };
  };
  auto p = vglambda([](auto v1, auto v2, auto v3) { std::cout << v1 << v2 << v3; });
  auto q = p(1, 'a', 3.14);    // 输出 1a3.14
  q();                         // 再次输出 1a3.14

  auto fact = [](this auto self, int n) -> int {     // C++23：显式对象参数实现递归
    return (n <= 1) ? 1 : n * self(n - 1);
  };
  std::cout << '\n' << fact(5) << '\n';              // 120
}
```

!!! note "为什么递归 lambda 需要 deducing this"
    在 C++23 之前，lambda 体内没有办法命名"自己"：闭包类型无名，`this` 指的是外层对象（¶16）。常见的变通是 `std::function` 自引用（有类型擦除开销）或 Y 组合子（`auto fact = [](auto& self, int n) {...}; fact(fact, 5);`）。显式对象参数让 `self` 直接就是闭包对象本身。

¶6 若 lambda **有捕获**，其显式对象参数的类型（实例化之后）只能是：(6.1) 闭包类型本身，(6.2) 公开且无歧义地派生自闭包类型的类，或 (6.3) 指向这些类型（可带 cv）的引用。为什么？因为调用运算符体内访问捕获，本质上是访问 `self` 的闭包成员——若 `self` 是一个与闭包无关的类型（例如能从任何东西构造的 `C`），这些访问就无从谈起。无捕获的 lambda 不访问任何成员，所以不受此限。

```cpp
struct C {
  template <typename T> C(T);       // 可以从任何类型构造
};

void func(int i) {
  int x = [=](this auto&&) { return i; }();   // OK：self 推导为闭包类型的引用
  int y = [=](this C) { return i; }();        // error: 有捕获，但对象参数类型 C 与闭包无关
  int z = [](this C) { return 42; }();        // OK：无捕获，C 可以从闭包构造
}
```

¶7 调用运算符的属性：

| lambda 写法 | 调用运算符 |
|---|---|
| `[]() static { }` {{c++23}} | **静态**成员函数（模板） |
| `[]() { }` | 非静态，**`const`** |
| `[]() mutable { }` | 非静态，非 const |
| `[](this auto&& self) { }` {{c++23}} | 显式对象成员函数（无 cv，由 `self` 的类型决定） |

此外：调用运算符永远不是 `virtual`，也不是 `volatile`。`noexcept` 说明与契约说明符作用于调用运算符。声明符中的属性属于调用运算符的**类型**；声明符之前的属性属于调用运算符本身。

**constexpr 是隐式的**：若写了 `constexpr`/`consteval`，或者调用运算符满足 constexpr 函数的要求（*constexpr-suitable*，[[dcl.constexpr]]），它就是 constexpr 函数——C++17 起无需显式标注。`consteval` 让它成为立即函数。

```cpp run ok
#include <type_traits>

auto ID = [](auto a) { return a; };
static_assert(ID(3) == 3);                              // 隐式 constexpr

constexpr auto sq = [](int i) { return i * i; };
static_assert(sq(4) == 16);

auto ce = [](int i) consteval { return i + 1; };        // 立即函数
static_assert(ce(1) == 2);

auto sl = [](int i) static { return i * 2; };           // C++23 static lambda
static_assert(decltype(sl)::operator()(3) == 6);        // 无需对象即可调用

int main() { }
```

```cpp error
auto ID = [](auto a) { return a; };
struct NonLiteral {
  NonLiteral(int n) : n(n) { }   // 非 constexpr 构造函数
  int n;
};
static_assert(ID(NonLiteral{3}).n == 3);   // error: NonLiteral{3} 不是常量表达式
```

!!! tip "static lambda 的价值"
    无捕获 lambda 的非静态 `operator()` 仍需要一个（空的）对象参数，被传给标准算法时，即使优化后也可能多出一个无用的寄存器参数；在 `std::function` 等类型擦除包装器中也需要保留对象。`static` 让调用运算符成为真正的静态函数，函数指针转换（¶11）直接返回指向它的指针，不需要额外的转发函数。

¶8 是一个关于 constexpr lambda 的长例子。要点在最后几行：

```cpp
auto monoid = [](auto v) { return [=] { return v; }; };
constexpr auto one = monoid(1);
auto two = monoid(2);                          // 不是 constexpr 变量
static_assert(add(one)(one)() == two());       // error: two() 读取了非 constexpr 对象的成员
static_assert(add(one)(one)() == monoid(2)()); // OK
```

`two` 的调用运算符是 constexpr 函数，但调用它需要对 `two` 的捕获成员做左值到右值转换，而 `two` 不是 constexpr 对象——"函数是 constexpr"不等于"任何调用都是常量表达式"。

¶9（注释）调用运算符可以用类型约束、`<...>` 后的 requires-clause、尾置 requires-clause 三种方式约束，与普通函数模板完全一致（[[temp.constr.decl]]）。

### 契约与隐式捕获 {{c++26}}（¶10）

¶10 若一个被 lambda `L` **隐式捕获**的局部实体，其全部潜在引用都出现在 `L` 的调用运算符的**函数契约断言**中，或 `L` 体内的 `contract_assert` 中，程序非良构。设计意图写在注释里：**给现有程序添加契约断言不应导致额外的捕获**——否则加一句 `contract_assert(i > 0)` 就可能改变闭包的大小、布局，甚至延长或改变对象的生命周期语义。解决办法是显式捕获，或者在别处也引用该实体。

### 转换为函数指针（¶11–15）

¶11 满足以下全部条件的闭包类型有一个**到函数指针的转换函数**：

- 非泛型；
- **无捕获**；
- 无显式对象参数；
- 约束（若有）被满足。

转换的目标是"指向具有 C++ 语言链接的函数的指针"，形参与返回类型与调用运算符相同；调用运算符为 non-throwing 时，目标是"指向 noexcept 函数的指针"。转换返回的值：

- 若调用运算符是**静态**的，就是指向调用运算符本身的指针；
- 否则是指向某个函数 `F` 的指针，调用 `F` 的效果如同在一个**默认构造**的闭包对象上调用调用运算符。`F` 在调用运算符是 constexpr（立即）函数时也是 constexpr（立即）函数。

为什么必须无捕获？函数指针只是一个地址，没有地方存放捕获的状态。为什么排除显式对象参数？因为那时调用运算符的"第一个参数"是闭包对象自身，函数指针的签名无法自然表达。

```cpp run ok
int (*fp)(int) = [](int i) { return i; };             // 隐式转换
void (*fnp)() noexcept = []() noexcept {};            // noexcept 函数指针
auto p = +[](int i) { return i * 2; };                // 一元 + 强制转换，p 的类型是 int(*)(int)

int main() { return fp(0) + p(0); }
```

¶12–13 **泛型**无捕获 lambda 有一个**转换函数模板**，其发明模板形参列表与调用运算符模板相同；函数指针的返回类型如同 `decltype` 调用运算符模板对应特化的返回类型。注释 5 用一个等价类说明它的行为——转换函数模板从目标函数指针类型推导模板实参，然后实例化调用运算符得到返回类型。标准的例子很好地展示了推导的边界：

```cpp
void f1(int (*)(int))   { }
void f2(char (*)(int))  { }
void g(int (*)(int))    { }     // #1
void g(char (*)(char))  { }     // #2
void h(int (*)(int))    { }     // #3
void h(char (*)(int))   { }     // #4

auto glambda = [](auto a) { return a; };
void test() {
  f1(glambda);                  // OK：T 推导为 int，返回 int，匹配
  f2(glambda);                  // error: T = int 时返回 int，不是 char
  g(glambda);                   // error: #1 与 #2 都可行，歧义
  h(glambda);                   // OK：只有 #3 可行
}
int& (*fpi)(int*) = [](auto* a) -> auto& { return *a; };   // OK
```

¶14 转换函数模板特化返回的值规则与 ¶11 平行：静态时指向调用运算符模板的特化；否则指向一个转发函数。注释 6 提醒：这会触发泛型 lambda 函数体的**隐式实例化**。

¶15 转换函数（模板）是 **public、constexpr、非 virtual、非 explicit、const、non-throwing** 的。因为它总是 constexpr，所以可以在常量表达式中完成转换；但能否在常量表达式中**调用**所得函数指针，取决于对应的调用运算符是否是 constexpr 函数：

```cpp
auto Fwd = [](int (*fp)(int), auto a) { return fp(a); };
auto C  = [](auto a) { return a; };
static_assert(Fwd(C, 3) == 3);    // OK

auto NC = [](auto a) { static int s; return a; };   // 含 static 局部变量 → 不可能是 constexpr
static_assert(Fwd(NC, 3) == 3);   // error: 不是常量表达式
```

### 函数体的作用域（¶16）

¶16 lambda 的复合语句成为调用运算符的函数体，**但它不在闭包类型的作用域内**。这条短短的规定影响巨大：

- 在 lambda 体内，名字查找**不会**找到闭包类型的成员——你不能写 `operator()` 来调用 lambda 自身（会找到外层类的 `operator()`）；
- `this` 指向**外层**对象（[[expr.prim.this#2]]：lambda 不引入类作用域）；
- 捕获产生的成员是**无名**的，在体内只能通过原变量名间接访问（由捕获的变换规则实现，见 [expr.prim.lambda.capture] ¶11）。

```cpp ok
struct S1 {
  int x, y;
  int operator()(int);
  void f() {
    [=, this]() -> int {
      return operator()(this->x + y);   // 即 S1::operator()(this->x + (*this).y)；this 的类型是 S1*
    };
  }
};
```

另外，除了 `consteval` 块（{{c++26}}）的情形，lambda 体开头会隐式定义 `__func__`（[[dcl.fct.def.general]]），其内容是实现定义的（Clang 给出 `"operator()"`）。

### 特殊成员函数（¶17–19）

¶17 闭包类型的特殊成员：

| | 有捕获 | 无捕获 |
|---|---|---|
| 默认构造函数 | **无** | 预置（defaulted）{{c++20}} |
| 拷贝/移动构造函数 | 预置 | 预置 |
| 拷贝赋值运算符 | **弃置**（deleted） | 预置 {{c++20}} |
| 移动赋值运算符 | 不声明（因而赋值总是落到弃置的拷贝赋值上） | 预置 {{c++20}} |

注释 7：这些函数照常隐式定义，因此可能被定义为弃置——例如按值捕获了一个 `std::unique_ptr`，拷贝构造函数就被弃置，闭包只能移动。

C++20 之前，**所有**闭包类型的默认构造函数和拷贝赋值运算符都被规定为弃置（deleted）。C++20 让无捕获 lambda 可以默认构造和赋值，配合"lambda 可出现在未求值操作数中"，就可以把 lambda 的**类型**当作比较器、删除器传给模板：

```cpp run ok
#include <cstdio>
#include <memory>
#include <set>

int main() {
  using Cmp = decltype([](int a, int b) { return a > b; });
  std::set<int, Cmp> s{1, 3, 2};          // set 默认构造 Cmp —— C++20 起无捕获闭包可默认构造
  std::printf("%d\n", *s.begin());        // 3

  std::unique_ptr<int, decltype([](int* p) { delete p; })> up(new int(1));
  static_assert(sizeof(up) == sizeof(int*));   // 空删除器不占空间（实现通常如此）
}
```

¶18 闭包类型有一个隐式声明的析构函数。

¶19 闭包类型的成员不得被显式实例化、显式特化，也不得在友元声明中被命名——闭包类型是实现细节，你只能通过 lambda 表达式本身来与它交互。

## 捕获（[expr.prim.lambda.capture]）

### 文法

```text
lambda-capture:  capture-default | capture-list | capture-default , capture-list
capture-default: &  |  =
simple-capture:  x  |  x...  |  &x  |  &x...  |  this  |  *this
init-capture:    x = e  |  ...x = e  |  &x = e  |  &...x = e    （初始化器也可以是 (e) 或 {e}）
```

¶1 lambda 体可以通过**捕获**来引用外围作用域的局部实体。

### 捕获列表的形式约束（¶2）

¶2

- 默认捕获为 `&` 时，简单捕获中的标识符不能再带 `&`（`[&, &i]` 冗余，被禁止）；
- 默认捕获为 `=` 时，简单捕获只能是 `&x`、`this` 或 `*this`（`[=, i]` 冗余，被禁止）；
- 除 init-capture 的初始化器内部之外，同一标识符或 `this` 不能出现两次。

注释 1：`[&, this]` 是冗余的，但为了与 C++14 兼容仍被接受。而 `[=, this]` 是 C++20 引入的写法，用来替代被弃用的"`[=]` 隐式捕获 `this`"。

```cpp
struct S2 { void f(int i); };
void S2::f(int i) {
  [&, i]{ };        // OK
  [&, this, i]{ };  // OK，等价于 [&, i]
  [&, &i]{ };       // error: 默认为 & 时 i 前面不能再有 &
  [=, *this]{ };    // OK
  [=, this]{ };     // OK，等价于 [=]（且不触发弃用）
  [i, i]{ };        // error: i 重复
  [this, *this]{ }; // error: this 出现两次
}
```

### 哪里可以有捕获（¶3–5）

¶3 只有以下情形的 lambda 才能有**默认捕获或简单捕获**：

- (3.1) 最内层外围作用域是**块作用域**（函数体内）；
- (3.2) 位于默认成员初始化器中，最内层外围作用域是对应的类作用域；
- (3.3) {{c++26}} 位于契约断言中，最内层外围作用域是契约断言作用域。

命名空间作用域的 lambda 不能写 `[=]`、`[&]` 或 `[x]`——那里没有局部实体可捕获。但 **init-capture 不受此限**：`auto counter = [i = 0]() mutable { return i++; };` 在命名空间作用域完全合法。

¶4 简单捕获中的标识符必须指代一个**局部实体**（[[basic.pre]]：自动存储期变量、结构化绑定、`*this` 等）；`this` 和 `*this` 指代局部实体 `*this`。被简单捕获指名的实体称为[[g:explicitly-captured|**显式捕获**]]。

所以全局变量、静态局部变量**不能**也**无需**捕获：

```cpp
int g;
void f() {
  static int s;
  auto l1 = [g] {};    // error: g 不是局部实体
  auto l2 = [] { return g + s; };   // OK：直接引用，无需捕获
}
```

¶5 捕获的标识符不能与 lambda 的形参同名，也不能与 lambda 的模板形参同名：

```cpp
void f() {
  int x = 0;
  auto g = [x](int x) { return 0; };                // error: 形参与捕获同名
  auto h = [y = 0]<typename y>(y) { return 0; };    // error: 模板形参与捕获同名
}
```

### init-capture（¶6）

¶6 init-capture 位于 lambda 的 **lambda 作用域**（[[basic.scope.lambda]]）中。不带 `...` 的 init-capture **如同**声明并显式捕获一个形如 `auto init-capture;` 的变量，但有两点不同：

- (6.1) 若按值捕获，闭包中的非静态数据成员与那个"变量"是**同一个对象的两种称呼**，其生命周期就是成员的生命周期，不会有额外的拷贝与析构；
- (6.2) 若按引用捕获（`[&r = x]`），那个引用变量的生命周期在闭包对象生命周期结束时结束。

注释 2：这使 `[x = std::move(x)]` 成为可能——等号右边的 `x` 必须绑定到外围的声明，因为 init-capture 的名字在初始化器中**尚未**可见（与普通变量 `int x = x;` 不同！）。

```cpp run ok
#include <cstdio>

int main() {
  int x = 4;
  auto y = [&r = x, x = x + 1]() -> int {   // r 引用外部 x；内部 x 是 5
    r += 2;
    return x + 2;
  }();                                      // 外部 x 变为 6，y 初始化为 7
  std::printf("%d %d\n", x, y);

  auto counter = [i = 0]() mutable -> decltype(i) { return i++; };   // 返回 int
  counter();
  std::printf("%d\n", counter());           // 1
}
```

注意 `decltype(i)` 出现在尾置返回类型中——init-capture 的名字在那里已可见（lambda 作用域包含整个声明符），这是 C++23 的规则（[[P2036R3]]）。

### 什么被隐式捕获（¶7）

这是捕获规则的核心。¶7 先定义"**潜在引用**"（potentially references）：

- (7.1) 命名局部实体的 id 表达式潜在引用该实体；命名一个或多个**非静态类成员**、且不构成成员指针的 id 表达式潜在引用 `*this`（注释 3：即使重载决议最终选中了静态成员函数也是如此）；
- (7.2) `this` 表达式潜在引用 `*this`；
- (7.3) lambda 表达式潜在引用它的简单捕获所指名的局部实体（这让外层 lambda 能"看到"内层的显式捕获）。

然后：

!!! std
    If an expression potentially references a local entity within a scope in which it is odr-usable, and the expression would be potentially evaluated if the effect of any enclosing `typeid` expressions were ignored, the entity is said to be *implicitly captured* by each intervening *lambda-expression* with an associated *capture-default* that does not explicitly capture it.

    在实体 odr-usable 的作用域中潜在引用它、且（忽略 typeid 后）潜在求值，就会被每个带默认捕获、且未显式捕获它的中间 lambda 隐式捕获。

逐个拆解这句话：

1. **"潜在求值"**：`sizeof(x)`、`decltype(x)` 中的 `x` 不会触发捕获。
2. **"忽略 typeid"**：`typeid(a + x)` 是否求值取决于操作数是否为多态类类型的 glvalue，在泛型 lambda 中可能直到实例化才知道。为了让捕获集合在**定义时**就确定，标准规定一律当作求值来处理——**宁多勿少**。
3. **"潜在引用"而非"odr-use"**（这就是 [[g:implicitly-captured|隐式捕获]] 的定义）：注意这里**不要求** odr-use！`const int x = 17;` 在 `[=]{ f(x); }` 中若 `f` 按值接收 `int`，`x` 并未被 odr-use（常量的左值到右值转换，[[basic.def.odr#5]]），但依然被**隐式捕获**——因为对泛型 lambda 而言，是否 odr-use 可能要到实例化（选中哪个重载）时才知道。标准例子的注释说：实现可以把未被 odr-use 的捕获**优化掉**。
4. **捕获集合由语法决定**：注释 4 强调，即使表达式位于被丢弃的语句（`if constexpr` 的假分支）中，实体也会被捕获。

!!! history "从 odr-use 到\"潜在引用\""
    C++11/14 的隐式捕获规则以 odr-use 为基础，并为泛型 lambda 另设了一条复杂的特殊规则（在"可能 odr-use"的表达式中也要捕获）。C++20 通过 [[P0588R1]]（简化隐式 lambda 捕获）改为基于语法的规则：只要潜在引用、潜在求值就捕获，不再追问是否真的 odr-use；此后的措辞又引入"潜在引用""odr-usable"等术语整理成现在的样子。

```cpp ok
#include <typeinfo>

void f(int, const int (&)[2] = {});         // #1
void f(const int&, const int (&)[1]);       // #2

void test() {
  const int x = 17;
  auto g = [](auto a) {
    f(x);                       // OK：调用 #1（按值），x 未被 odr-use → 无需捕获，也没有默认捕获
  };
  auto g1 = [=](auto a) {
    f(x);                       // OK：调用 #1，x 被（语法上）隐式捕获；实现可优化掉
  };
  auto g2 = [=](auto a) {
    int selector[sizeof(a) == 1 ? 1 : 2]{};
    f(x, selector);             // OK：捕获 x；视 a 的类型可能调用 #1 或 #2（#2 按引用接收，会 odr-use）
  };
  auto g3 = [=](auto a) {
    typeid(a + x);              // 无论 a + x 是否为未求值操作数，都捕获 x
  };
}
```

```cpp ok
template<bool B>
void f(int n) {
  [=](auto a) {
    if constexpr (B && sizeof(a) > 4) {
      (void)n;                  // 无论 B 与 sizeof(int) 如何，都会捕获 n
    }
  }(0);
}
```

!!! warning "隐式捕获 this 的弃用 {{deprecated}}"
    ¶7 末尾：当默认捕获是 `=` 时，隐式捕获 `*this`（按引用！）**已弃用**（[[depr.capture.this]]）。原因在于 `[=]` 给人"所有东西都被复制"的错觉，而成员访问 `x` 实际上是 `this->x`——复制的是**指针**，对象本身并未被复制。若 lambda 比对象活得久，就悬垂了。C++20 起推荐写 `[=, this]`（明确按引用）或 `[=, *this]`（真正复制对象）。

```cpp ok
struct X {
  int x;
  void foo(int n) {
    auto f = [=]() { x = n; };          // 弃用：x 是 this->x，并非副本（Clang 会警告）
    auto g = [=, this]() { x = n; };    // 推荐的替代写法
  }
};
```

### 捕获即 odr-use（¶8–9）

¶8 被捕获（显式或隐式）的实体被该 lambda 表达式 **odr-use**。注释 5 推出：若显式捕获一个**不是 odr-usable** 的实体，程序非良构（[[basic.def.odr#10]]）。

**odr-usable** 的直觉：局部实体从声明点到使用点之间，若隔着一个**没有捕获它**的 lambda 作用域，或隔着一个函数形参作用域/类作用域（嵌套函数、局部类），它就不是 odr-usable 的。在不 odr-usable 的地方 odr-use 局部实体是非良构的。这就是"lambda 必须捕获才能用外部变量"的规范来源。

标准例子（有删节）值得逐行理解：

```cpp
void f1(int i) {
  int const N = 20;
  auto m1 = [=]{
    int const M = 30;
    auto m2 = [i]{
      int x[N][M];              // OK：N、M 未被 odr-use（常量，作为数组边界只取值）
      x[0][0] = i;              // OK：i 被 m2 显式捕获，被 m1 隐式捕获（经由 ¶7.3）
    };
  };
  struct s1 {
    int f;
    void work(int n) {
      int m = n*n;
      int j = 40;
      auto m3 = [this,m] {
        auto m4 = [&,j] {       // error: j 在此处不是 odr-usable（m3 没有捕获它，也没有默认捕获）
          int x = n;            // error: n 被 odr-use，但因 m3 的阻隔不是 odr-usable
          x += m;               // OK：m 被 m4 隐式捕获、被 m3 显式捕获
          x += i;               // error: i 被局部类 s1 与成员函数 work 的作用域阻隔
          x += f;               // OK：this 被 m4 隐式捕获、被 m3 显式捕获
        };
      };
    }
  };
}
```

`m2` 那一行揭示了 ¶7.3 的作用：内层 lambda 显式捕获 `i`，这个 lambda 表达式本身"潜在引用" `i`，从而外层带 `[=]` 的 `m1` 隐式捕获了 `i`——捕获沿嵌套层层"向外传播"。

`*this` 同理：

```cpp
struct s2 {
  double ohseven = .007;
  auto f() {
    return [this] {
      return [*this] {
        return ohseven;         // OK：内层复制了外层所指的对象
      };
    }();
  }
  auto g() {
    return [] {
      return [*this] { };       // error: 外层 lambda 没有捕获 *this
    }();
  }
};
```

¶9（注释）局部实体在**默认实参**中不是 odr-usable 的（[[basic.def.odr#10]]：函数形参作用域阻隔），所以默认实参里的 lambda 不能隐式或显式捕获任何局部实体；但可以有 init-capture，只要其初始化器满足默认实参的限制（[[dcl.fct.default]]：不能引用局部变量）。

```cpp
void f2() {
  int i = 1;
  void g1(int = ([i]{ return i; })());          // error: 不能捕获
  void g2(int = ([i]{ return 0; })());          // error: 即使不用也不能捕获
  void g3(int = ([=]{ return i; })());          // error: 隐式捕获 i
  void g4(int = ([=]{ return 0; })());          // OK：什么都没捕获
  void g5(int = ([]{ return sizeof i; })());    // OK：未求值，不需要捕获
  void g6(int = ([x=1]{ return x; })());        // OK：init-capture，初始化器不涉及局部变量
  void g7(int = ([x=i]{ return x; })());        // error: 初始化器引用了局部变量 i
}
```

### 按值捕获（¶10–11）

¶10 一个实体[[g:captured-by-copy|**按值捕获**]]（captured by copy），当：

- (10.1) 它被隐式捕获、默认捕获是 `=`、且实体不是 `*this`（`[=]` 隐式捕获的 `*this` 是**按引用**的——这正是弃用的原因）；或
- (10.2) 它被显式捕获，且捕获形式**不是** `this`、`&x`、`&x...`、`&x = e`。

对每个按值捕获的实体，闭包类型中声明一个**无名非静态数据成员**，类型为：

- 若实体是**对象的引用**：被引用的类型（捕获引用 = 复制被引用对象）；
- 若实体是**函数的引用**：指向该函数类型的左值引用（函数无法复制）；
- 否则：实体的类型（`const` 会被保留！）。

匿名联合体的成员不能按值捕获。

!!! pitfall "按值捕获保留 const，mutable 也救不了"
    ```cpp
    const std::string s = "x";
    auto l = [s]() mutable { s += "y"; };   // error: 成员类型是 const std::string
    ```
    同理，在 `const` 成员函数中 `[*this]() mutable { v = 1; }` 也不行：`*this` 的类型是 `const X`，复制出的成员是 `const X`。想要可修改的副本，用 init-capture：`[s = s]() mutable { s += "y"; }`（init-capture 按 `auto` 推导，丢掉顶层 const）。

¶11 lambda 体中**每个是 odr-use** 的、指代按值捕获实体的 id 表达式，被变换为对闭包对应无名数据成员的访问。注释 7 是关键：**不是 odr-use 的 id 表达式指代原实体，永远不是闭包成员**——但它仍可能引起隐式捕获。若 `*this` 被按值捕获，每个 odr-use `*this` 的表达式都改为引用对应成员。

```cpp ok
void f(const int*);
void g() {
  const int N = 10;
  [=] {
    int arr[N];     // OK：不是 odr-use，指代外部那个自动变量 N（读取其常量值）
    f(&N);          // OK：取地址是 odr-use，导致 N 被捕获；&N 指向闭包中的成员
  };
}
```

这条规则是"lambda 中可以直接使用常量而无需捕获"的规范依据：`const int N = 10; [] { return N; }` 良构，因为 `N` 的使用是对常量的左值到右值转换，不是 odr-use；但 `[] { const int& r = N; }` 非良构——绑定引用是 odr-use。

```cpp error
void f(int n) {
  [] { n = 1; };                        // error: n 未被捕获，在此处不是 odr-usable
  const int N = 10;
  [] { return N; };                     // OK：不是 odr-use
  [] { const int& r = N; (void)r; };    // error: 绑定引用是 odr-use，N 需要被捕获
}
```

### 按引用捕获（¶12–13）

¶12 被捕获但不是按值捕获的实体[[g:captured-by-reference|**按引用捕获**]]。是否为按引用捕获的实体在闭包中声明额外的无名数据成员是**未指定**的 {{unspec}}；若声明了，它们必须是字面类型。**位域和匿名联合体成员不能按引用捕获**（没有办法形成指向它们的引用）。

标准的例子说明了"必须是字面类型"的意图：按引用捕获的 lambda 要能在常量表达式中使用。

```cpp ok
static_assert([](int n) { return [&n] { return ++n; }(); }(3) == 4);
```

¶13 lambda 体中 odr-use 一个**按引用捕获的引用**时，它指代该引用所绑定的实体，而不是那个引用本身。注释 8：所以按引用捕获引用是否有效，取决于**被引用对象**的生命周期，而不是引用变量的生命周期：

```cpp ok
auto h(int& r) {
  return [&] {
    ++r;            // 在 h 返回后仍然有效——只要 r 所绑定的对象还活着
  };
}
```

这条规则使"按引用捕获引用形参"成为安全的常见模式，而按引用捕获**局部对象**则不是。

### 嵌套 lambda 的捕获（¶14）

¶14 若内层 lambda `m2` 捕获了一个实体，而直接外层的 lambda `m1` 也捕获了它：

- (14.1) `m1` 按值捕获 → `m2` 捕获的是 `m1` 闭包中对应的**数据成员**；若 `m1` 不是 mutable，该成员视为 const；
- (14.2) `m1` 按引用捕获 → `m2` 捕获的是 `m1` 所捕获的**同一个实体**。

标准的例子会输出 `123234`，值得手推一遍：

```cpp run ok
#include <iostream>

int main() {
  int a = 1, b = 1, c = 1;
  auto m1 = [a, &b, &c]() mutable {
    auto m2 = [a, b, &c]() mutable {
      std::cout << a << b << c;    // 输出 123，推导见下文
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

推导：`m1` 创建时复制 `a = 1`（成员 `m1.a`），按引用持有 `b`、`c`。之后外部赋值为 2。调用 `m1()`：**在 `m1` 体内创建 `m2`**——`m2` 按值捕获 `a`（即 `m1.a`，此时为 1）和 `b`（`m1` 按引用捕获了外部 `b`，所以 `m2` 复制外部 `b` 的当前值 2），按引用捕获 `c`（即外部 `c`）。随后 `m1.a = 3`、外部 `b = 3`、外部 `c = 3`。调用 `m2()` 输出 `m2.a`(1)、`m2.b`(2)、外部 `c`(3) → `123`；然后改的是 `m2` 自己的副本和外部 `c = 4`。最后输出外部 `a`(2)、`b`(3)、`c`(4) → `234`。

### 成员的声明顺序与初始化（¶15–16）

¶15 闭包中非静态数据成员的声明顺序**未指定** {{unspec}}，但**显式捕获**对应的成员按与捕获列表一致的顺序声明。

¶16 按值捕获的实体用来**直接初始化**对应成员；init-capture 的成员（及不对应成员的引用变量）按其初始化器初始化（可能是拷贝初始化或直接初始化）；数组成员的元素按下标递增顺序直接初始化。这些初始化在**求值 lambda 表达式时**进行，顺序与成员的声明顺序（部分未指定）以及显式捕获的顺序一致。注释 9：这保证了析构顺序与构造顺序相反。

```cpp ok
#include <utility>
#include <vector>

void f(std::vector<int>&& v) {
  [size = v.size(), own = std::move(v)] {};   // size 先于 own 初始化，因此拿到的是原始大小
}
```

!!! note "显式捕获的顺序保证"
    显式捕获按书写顺序初始化这一保证，让 `[a = x.get(), b = std::move(x)]` 这类依赖顺序的写法变得可靠。隐式捕获的成员之间、以及它们与显式捕获之间的相对顺序仍然未指定——因此不要让隐式捕获的副作用依赖于顺序（通常也没有副作用：隐式捕获只是复制）。

### 悬垂（¶17）

¶17（注释）若非引用实体被按引用捕获（隐式或显式），在该实体生命周期结束之后调用闭包的调用运算符，**很可能**导致未定义行为。"很可能"——因为只有真正访问那个已死对象时才是 UB（[[basic.life]]）；若调用路径不触及它，就没事。

```cpp run ub
#include <cstdio>
#include <functional>

std::function<int()> make() {
  int local = 42;
  return [&] { return local; };   // 按引用捕获局部变量
}

int main() {
  auto f = make();
  std::printf("%d\n", f());        // UB: local 的生命周期已结束
}
```

用 `-fsanitize=address` 并设置 `ASAN_OPTIONS=detect_stack_use_after_return=1` 运行，AddressSanitizer 会报告 `stack-use-after-return`。

### 包展开（¶18）

¶18 带 `...` 的简单捕获（`args...`、`&args...`）是包展开；带 `...` 的 init-capture（`...xs = std::move(args)`、`&...rs = args`）是声明了一个 **init-capture 包**的包展开 {{c++20}}。

```cpp run ok
#include <cstdio>
#include <utility>

template<class... Args> int sum(Args... args) {
  auto l1 = [args...] { return (0 + ... + args); };                 // 按值捕获整个包
  auto l2 = [...xs = std::move(args)] { return (0 + ... + xs); };   // C++20：init-capture 包
  auto l3 = [&...rs = args] { return (0 + ... + rs); };             // C++20：按引用的 init-capture 包
  return l1() + l2() + l3();
}

int main() { std::printf("%d\n", sum(1, 2, 3)); }   // 18
```

注意 `...` 的位置：simple-capture 中 `...` 在**后**（`args...`，与包展开的一般习惯一致），init-capture 中 `...` 在**前**（`...xs = e`，与声明包的习惯 `class... Ts` 一致——它是在**声明**一个新包）。

### 捕获结构化绑定 {{c++20}}

[[basic.pre]] 把结构化绑定列为局部实体，所以它们可以像变量一样被捕获。C++17 中这是非良构的（结构化绑定不是变量）；C++20 允许按值和按引用捕获结构化绑定。但若结构化绑定指代**位域**，就不能按引用捕获（¶12）：

```cpp ok
#include <utility>

void sb() {
  auto [p, q] = std::pair{1, 2};
  auto l  = [p, &q] { return p + q; };   // C++20 起 OK
  auto l2 = [=] { return p; };           // 隐式捕获也 OK
}
```

```cpp error
struct B { int bf : 3; };
void g(B b) {
  auto& [x] = b;
  [&x] { return x; };      // error: x 指代位域，不能按引用捕获
}
```

## 实现视角

!!! impl
    - **闭包布局**：主流实现把按值捕获实现为普通数据成员；按引用捕获通常每个存一个指针（本机 Clang 上，按引用捕获两个 `int` 的闭包 `sizeof` 为 16）。¶4 与 ¶12 允许实现采用别的表示（例如只存一个栈帧指针）。无捕获闭包是空类，`sizeof` 为 1。
    - **名字修饰**：Itanium C++ ABI 为 lambda 规定了修饰方式（`UlvE_` 之类，形如 `{lambda()#1}`），使得出现在**内联函数、类定义、变量模板**等"可在多个 TU 中重复定义"位置的 lambda 在各个 TU 中得到**相同**的闭包类型名——这是 ODR 能成立的前提（[[basic.def.odr]] 要求这些定义在各 TU 中"相同"）。出现在非内联函数中的 lambda，Clang 会给出 `$_0` 之类的局部名字（ASan 报告中可以看到 `make()::$_0::operator()()`）。
    - **函数指针转换**：对非 static 的无捕获 lambda，编译器生成一个静态的"调用器"（invoker）函数，在其中构造一个闭包对象（空类）再调用 `operator()`——即 ¶11 中的 `F`。C++23 static lambda 省掉了这一层。
    - **`__func__`**：Clang 在 lambda 体内给出 `"operator()"`，GCC 同样如此；这是实现定义的。
    - **诊断**：Clang 的 `-Wdeprecated-this-capture` 对应 [[depr.capture.this]]；`-Wunused-lambda-capture` 提示显式捕获了但未 odr-use 的实体（例如常量）。

## 历史与演进

!!! history
    - **C++11**：引入 lambda 表达式；返回类型推导仅限单一 return 语句；只能捕获自动变量与 `this`。
    - **C++14**：泛型 lambda（`auto` 形参）；init-capture（解决 move-only 对象的捕获）；返回类型推导与普通函数统一。
    - **C++17**：`constexpr` lambda 与隐式 constexpr（[[P0170R1]]）；`[*this]` 按值捕获当前对象（[[P0018R3]]）。
    - **C++20**：lambda 的模板形参列表（[[P0428R2]]）；无捕获 lambda 可默认构造与赋值（[[P0624R2]]）；lambda 可出现在未求值操作数中（[[P0315R4]]）；init-capture 中的包展开（[[P0780R2]]）；允许 `[=, this]`、弃用 `[=]` 隐式捕获 `this`（[[P0806R2]]）；可捕获结构化绑定（[[P1091R3]]、[[P1381R1]]）；`consteval` lambda。
    - **C++23**：省略 `()` 的规则放宽（[[P1102R2]]）；`static` lambda（[[P1169R4]]）；显式对象参数（[[P0847R7]]）；lambda 声明符前的属性（[[P2173R1]]）；尾置返回类型中捕获名字的作用域调整（[[P2036R3]]，即 [[expr.prim.id.unqual#4]] 的现行规则）。
    - **C++26**：契约说明符可用于 lambda，以及"契约不得引起隐式捕获"（¶10）；`consteval` 块不定义 `__func__`。

## 陷阱

!!! pitfall "`[=]` 不复制 *this"
    `[=] { return member; }` 捕获的是 `this` 指针。若闭包被存起来（异步回调、`std::function` 成员），对象销毁后调用即悬垂。C++20 起要么写 `[=, this]` 表明意图，要么写 `[=, *this]` 真正复制。

!!! pitfall "按引用捕获的生命周期"
    `[&]` 在 lambda 只在当前作用域内同步使用时是安全且高效的；一旦闭包逃逸（返回、存储、传给另一个线程），按引用捕获的局部变量就会悬垂。规则：**逃逸的 lambda 只按值捕获，或按引用捕获生命周期确定更长的对象**。

!!! pitfall "每个 lambda 一个类型"
    `auto g = cond ? [k] { return 1; } : [k] { return 2; };` 非良构：两个分支是不同的类类型，彼此无法转换。有趣的是，把捕获去掉后 `cond ? [] { return 1; } : [] { return 2; }` 却是**良构**的：[[expr.cond]] 在两个操作数类类型不同时会对内置候选做重载决议，而两个无捕获闭包都能转换为 `int(*)()`，于是结果类型就是函数指针。`std::vector<decltype(lam)>` 也只能装这一个 lambda 的对象。

!!! pitfall "init-capture 与 const"
    `[x]` 保留 `x` 的 const；`[x = x]` 按 `auto` 推导，丢弃顶层 const；`[&x = x]` 按 `auto&` 推导，保留 const。

!!! pitfall "常量不需要捕获——直到你取它的地址"
    `const int N = 10; [] { return N * 2; }` OK；`[] { return &N; }`、`[] { std::max(N, 1); }`（`std::max` 按 `const T&` 接收 → 绑定引用 → odr-use）都非良构。后者是很多人第一次遇到"为什么常量要捕获"时的困惑来源。

## 思考题

!!! question "思考题 1"
    下面的 lambda 是否良构？若良构，闭包对象的 `sizeof` 是多少（在常见 64 位实现上）？
    ```cpp
    void f() {
      const int N = 10;
      auto l = [=] { return N + 1; };
    }
    ```

<details markdown="1">
<summary>答案</summary>

良构。`N` 在 lambda 体内潜在被引用、潜在求值，且在此处 odr-usable，因此按 ¶7 被**隐式捕获**（隐式捕获不要求 odr-use）。但由于 `N + 1` 中对 `N` 的使用不是 odr-use，按 ¶11 它指代外部的 `N`（编译期常量），而不是闭包成员；标准例子的注释说实现可以优化掉这个捕获。实践中 Clang 的 `sizeof(l)` 为 1（空闭包）。注意：标准并没有**保证**这个大小——¶4 允许实现改变闭包大小。
</details>

!!! question "思考题 2"
    为什么有捕获的 lambda 的拷贝赋值运算符被弃置，而拷贝构造函数却是预置的？

<details markdown="1">
<summary>答案</summary>

历史上的考虑是：按引用捕获可能被实现为引用成员，而带引用成员的类无法合理地赋值（引用不能重新绑定）；同时，"对闭包赋值"在语义上意味着替换捕获的状态，这不是 lambda 设计的使用方式。拷贝构造则是把闭包传给算法、存入 `std::function` 所必需的。C++20 放开的只是**无捕获**的情形——那里没有状态，赋值是平凡的，而允许它让闭包类型可以作为 `std::set` 比较器、`unique_ptr` 删除器等需要默认构造/赋值的模板实参。
</details>

!!! question "思考题 3"
    下面代码输出什么？
    ```cpp
    int x = 1;
    auto l = [x]() mutable { return ++x; };
    auto l2 = l;
    l(); l();
    std::cout << l() << l2() << x;
    ```

<details markdown="1">
<summary>答案</summary>

输出 `421`。`l` 被调用三次，其成员依次变为 2、3、4，最后一次返回 4；`l2` 是在任何调用之前复制的，成员仍为 1，调用后返回 2；外部 `x` 从未被修改，是 1。（C++17 起 `<<` 的左操作数先于右操作数求值，所以输出顺序确定。）这道题说明闭包对象就是一个普通对象：复制闭包就复制了它的所有捕获状态。
</details>

## 小结

!!! summary
    | 主题 | 要点 |
    |---|---|
    | 本质 | lambda = 定义一个独一无二的无名类（闭包类型）+ 创建它的 prvalue 对象 |
    | 闭包类型 | 非聚合、非 final；无捕获时是结构化类型；大小/平凡可复制/标准布局可能因实现而异 |
    | 调用运算符 | 默认 `const`；`mutable` 去掉 const；`static` 变静态（不能有捕获）；显式对象参数下由 `self` 决定；满足条件时隐式 constexpr |
    | 函数指针转换 | 仅限无捕获、无显式对象参数；泛型 lambda 有转换函数模板；转换函数本身总是 constexpr、noexcept |
    | 特殊成员 | 有捕获：无默认构造、拷贝赋值弃置；无捕获（C++20）：可默认构造、可赋值 |
    | 隐式捕获 | 在 odr-usable 处潜在引用且潜在求值即被捕获（不要求 odr-use）；语法决定，丢弃语句中也算 |
    | 按值 vs 按引用 | `[=]` 隐式捕获 `*this` 是按引用（已弃用）；按值成员类型保留 const；位域/匿名联合体成员不能按引用捕获 |
    | 名字指向 | odr-use → 闭包成员；非 odr-use（如常量取值）→ 原实体 |
    | 初始化 | 求值 lambda 表达式时进行；显式捕获按书写顺序；其余顺序未指定 |
    | 悬垂 | 按引用捕获的对象死后再访问是 UB；捕获的引用看其绑定对象的生命周期 |
