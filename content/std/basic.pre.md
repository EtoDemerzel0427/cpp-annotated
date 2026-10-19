---
title: 前言：名字、实体与变量
summary: 第 6 章的基础词汇：什么算名字，名字由哪些声明引入，哪些东西是实体，什么是变量和局部实体。
status: done
related: basic.def, basic.scope, basic.link, basic.lookup, dcl.struct.bind, dcl.contract.res
tags: 基本概念, 名字, 实体, 声明
updated: 2026-10-19
---

!!! tldr
    - 名字只有四种：标识符、`operator int` 这样的转换函数名、`operator+` 这样的运算符函数名、`operator""_km` 这样的字面量运算符名。标号、模块名、属性里的标识符不是名字，不参与名字查找。
    - 每个名字都由一个声明引入；名字指代的是实体，并且穿透别名：`using I = int;` 之后，名字 `I` 指代 `int`。
    - 变量是由声明引入的对象或引用。非静态数据成员和非类型模板形参都不是变量，所以 ODR 中关于变量的规则管不到它们。
    - 局部实体是自动存储期的变量、相应的结构化绑定、结果绑定和 `*this`。只有它们在 lambda 里使用时需要捕获，`static` 局部变量不需要。

## 什么算名字（¶3）

```cpp run ok
int f() {
  int x = 0;
x:                      // 标号 x 不是名字，不与变量 x 冲突
  if (++x < 3) goto x;  // goto 后面的 x 也不是名字
  return x;
}
int main() { return f() - 3; }
```

同一个函数里有一个变量 `x` 和一个标号 `x`，却不冲突。原因是标号的标识符根本不算**名字**（name），名字查找、作用域冲突这些规则都不适用于它。

¶3 规定名字只有四种形式：

| 形式 | 例子 |
|---|---|
| *identifier* 记号 | `x`、`std`、`vector` |
| *conversion-function-id*（转换函数名） | `operator int`、`operator bool` |
| *operator-function-id*（运算符函数名） | `operator+`、`operator()`、`operator new` |
| *literal-operator-id*（字面量运算符名） | `operator""_km` |

¶3.1 同时排除了三类标识符：标号的标识符和 *literal-operator-id* 里的后缀（`_km` 单独不是名字，整个 `operator""_km` 才是）；`goto` 后面的标识符；模块名（`export module my.lib;` 里的 `my`、`lib`）和属性记号（`[[gnu::always_inline]]` 里的 `gnu`、`always_inline`）里的标识符。

这三类各有自己的匹配方式：标号在函数内按标号规则匹配（[[stmt.label]]），模块名由模块系统解析（[[module.unit]]），属性记号由实现识别（[[dcl.attr.grammar]]）。把它们排除在名字之外，名字查找和链接的规则就不会误伤它们。

关键字不是标识符记号（[[lex.key]]），所以也不是名字。宏名在预处理阶段就被替换掉了（[[cpp.replace]]），编译器做语义分析时已经看不到它们。宏不受 ODR 约束，这就是同一个头文件在不同翻译单元里用不同 `-D` 选项编译时，可能悄悄违反 ODR 的原因之一（见 [[basic.def.odr]]）。

### 两个名字何时相同（¶4）

¶4 两个名字相同的条件按形式分别规定：标识符要求字符序列相同；转换函数名要求目标类型等价（[[temp.over.link]]），不要求写法相同；运算符函数名要求是同一个运算符；字面量运算符名要求后缀相同。

```cpp run ok
struct S { operator int() const { return 1; } };
using I = int;
int g(S s) {
  return s.operator I() + s.operator int();  // 同一个名字、同一个函数
}
int main() { return g({}) - 2; }
```

[[basic.scope.scope]] 判断两个声明是否对应（因而构成重声明、重载或冲突）时，第一步就是看它们的名字是否相同。

## 每个名字都由声明引入（¶5）

¶5 规定每个名字都由一个**声明**（declaration）引入。这里的声明是语义上的概念，比文法里的非终结符 *declaration* 宽（注 3）：函数形参、结构化绑定里的标识符、lambda 的 init-capture 也都算。

| ¶ | 声明的形式 | 例子 |
|---|---|---|
| 5.1 | *name-declaration*、*block-declaration*、*member-declaration* | `namespace N {}`、`using T = int;` |
| 5.2 | *init-declarator* | `int a = 1, *p;` 中的 `a = 1` 和 `*p` |
| 5.3 | 结构化绑定中的标识符 | `auto [x, y] = p;` 的 `x`、`y` |
| 5.4 | 后置条件里 *result-name-introducer* 的标识符 {{c++26}} | `post(r: r > 0)` 的 `r` |
| 5.5 | *init-capture* | `[n = 42]{}` 的 `n` |
| 5.6 | 带声明符的 *condition* | `if (int x = f())` |
| 5.7 | *member-declarator* | `struct S { int m : 3; };` 的 `m : 3` |
| 5.8 | *using-declarator* | `using std::swap;` |
| 5.9 | *parameter-declaration* | 函数形参、非类型模板形参 |
| 5.10–5.13 | 类型模板形参和三种模板模板形参 | `class T`、`template<class> class TT`，以及 C++26 的变量模板形参、概念模板形参 |
| 5.14 | 引入名字的 *elaborated-type-specifier* | `struct Fwd*` 里的 `struct Fwd` |
| 5.15 | *class-specifier* | `struct S { };` |
| 5.16 | *enum-specifier*、*enumerator-definition* | `enum E { a };` |
| 5.17 | *exception-declaration* | `catch (std::exception& e)` |
| 5.18 | 隐式的注入类名声明 | 类 `S` 内部的 `S` |

范围 `for` 的 *for-range-declaration* 会被改写成上面的一种或几种（注 4，[[stmt.ranged]]）。[[basic.scope.pdecl]] 逐一为这些形式规定了声明点。

反过来，不是每个声明都引入名字。`static_assert(true);`、空声明 `;`、`using namespace std;`、显式实例化 `template class X<int>;` 都是声明，但不引入任何名字（[[basic.def#1]]）。

!!! note "名字可能指代类型或模板（¶6）"
    ¶6 是一条注：解析程序时，遇到一个名字通常要先查找它，才知道它是不是类型或模板。C++ 文法依赖上下文就是这个原因：`T * p;` 是乘法还是指针声明，取决于 `T` 是不是类型；`a < b > c;` 是比较还是声明，取决于 `a` 是不是模板。模板里这个问题要等到实例化才能回答，所以要用 `typename` 和 `template` 消歧义（[[temp.res]]）。

## 实体与指代（¶8）

名字是源码里的记号，它所指的东西叫**实体**（entity）。¶8 列出了全部十五种实体：

> 变量、结构化绑定、结果绑定、函数、枚举项、类型、类型别名、非静态数据成员、位域、模板、命名空间、命名空间别名、模板形参、函数形参、init-capture。

对象和值都不在其中。变量是实体，变量所声明的那个对象不是；`new int` 创建的对象没有名字，也不是实体。表达式、语句、标号、宏、模块同样不是实体。C++26 的反射值（`std::meta::info`）既能表示实体，也能表示值、对象、数据成员描述这类非实体的东西（[[basic.fundamental]]），所以相关规则要分开说明。

每个实体有一个**底层实体**（underlying entity）。除非另有规定，底层实体就是它自己；类型别名和命名空间别名是例外，它们的底层实体是所代表的类型或命名空间（注 6）。

一个名字**指代**（denote）引入它的声明所声明的实体的底层实体。换句话说，名字穿透别名：

```cpp run ok
namespace very_long_name { int v = 1; }
namespace V = very_long_name;  // 命名空间别名，底层实体是 very_long_name
using I = int;                 // 类型别名，底层实体是 int

int main() {
  I i = V::v;  // V 指代 very_long_name，I 指代 int
  return i - 1;
}
```

别名本身算一个实体，所以它可以被声明、有自己的作用域、在反射里是一个独立的值。名字指代底层实体，所以别名在语义上是透明的：`I` 和 `int` 是同一个类型。[[basic.scope.scope#6]] 允许 `namespace B = A;` 重复出现、[[basic.link#8]] 判断两个别名声明是否为同一实体，都依赖这个区分。

一个名字可以由多个声明引入，例如重载的 `f(int)` 和 `f(double)` 都引入名字 `f`。这时名字查找得到一组声明（[[basic.lookup]]），再由重载决议从中选出一个函数。

## 变量（¶7）

¶7 规定，如果声明 D 声明了一个对象，或者声明了一个引用（但不是非静态数据成员），并且 D 不是模板形参的 *parameter-declaration*，那么 D 引入一个**变量**（variable）。

| 声明 | 是变量吗 | 原因 |
|---|---|---|
| `int x;`（任意作用域） | 是 | 声明一个对象 |
| `static int s;`（类内） | 是 | 静态数据成员是一个对象 |
| `int m;`（类内） | 否 | 非静态数据成员是另一种实体 |
| `int& r;`（类内） | 否 | 是引用，但属于非静态数据成员 |
| `int& r = x;`（块内） | 是 | 引用也可以是变量 |
| `void f(int p)` 的 `p` | 是 | 函数形参声明一个对象 |
| `template<int N>` 的 `N` | 否 | 模板形参的 *parameter-declaration* 被排除 |
| `auto [a, b] = t;` 的 `a` | 否 | 结构化绑定是另一种实体；这条声明另外引入了一个无名变量 |
| `[n = 1]{}` 的 `n` | 否 | init-capture 是另一种实体 |

非静态数据成员不是变量，因为它不对应一块单独存在的存储：每个类对象里各有一份，成员本身只描述类型和偏移。ODR 关于变量的规则、存储期、链接，对它都没有意义。静态数据成员则是全程序唯一的对象，所以算变量。

非类型模板形参 `N` 在实例化里只是一个值，标量的 `N` 是纯右值，不能取地址，所以也不算变量。

## 局部实体（¶9）

```cpp run error
int g = 1;
void f(int n) {
  static int s = 2;
  auto l = [] { return g + s; };  // OK：g、s 不是局部实体
  auto bad = [] { return n; };    // error: n 是局部实体，没有被捕获
  (void)l; (void)bad;
}
int main() { f(0); }
```

¶9 规定**局部实体**（local entity）有四种：自动存储期的变量（[[basic.stc.auto]]，即块内不带 `static`、`thread_local`、`extern` 的变量，以及函数形参）；对应变量是这种变量的结构化绑定；后置条件里的结果绑定（[[dcl.contract.res]]）{{c++26}}；以及 `*this`（[[expr.prim.this]]）。

局部实体的存储属于某一次函数调用。lambda 的函数体或局部类的成员函数可能在另一次调用中、甚至外层函数返回之后才执行，那时并没有一个确定的 `n` 可以访问。所以 [[basic.def.odr#10]] 规定，局部实体只在一定范围内可以直接使用，跨过 lambda 就要捕获。静态存储期的变量全程序只有一个，任何地方都能直接用。

`*this` 被列为局部实体，于是在 lambda 里访问成员要捕获 `this`，走的是和普通局部变量同一套规则。

## 跨翻译单元的同名（¶10）

¶10 同一个名字出现在多个翻译单元（单独编译的源文件连同它包含的头文件）里时，是否指代同一个实体，取决于它的**链接**（linkage）。具体规则在 [[basic.link]]：外部链接和模块链接的名字可以跨翻译单元指代同一实体，内部链接的名字在每个翻译单元里各是一个实体。

<details class="fine" markdown="1"><summary>其余条文</summary>

¶1–¶2 是两条注，说明第 6 章介绍语言的基本概念（对象与名字、值类别、声明与定义、类型、作用域、链接、存储期、程序的启动和终止、基础类型与复合类型），只影响语言某一部分的概念放在对应的章节。

</details>

## 历史与演进

!!! history
    - C++20 及以前，实体的清单里还有值和对象，名字被定义为指代实体或标号的标识符等的使用，所以标号也算在名字的讨论范围内。
    - C++23 的 [[P1787R6]]（Declarations and where to find them）重写了作用域和名字查找的模型，用声明引入名字的清单（今天的 ¶5）取代了旧的声明区描述（见 [[basic.scope]]）。
    - 当前草案的实体清单去掉了值和对象，加入了类型别名、命名空间别名、函数形参、模板形参等，并用底层实体处理别名。C++26 的契约带来了结果绑定，静态反射让 *splice-expression* 也能指称实体。

## 常见误解

!!! pitfall "对象就是变量"
    `new int` 创建的对象没有名字，不是变量。讨论生命周期（[[basic.life]]）时说的是对象；讨论链接、ODR、作用域时说的是变量和名字。

!!! pitfall "非静态数据成员也会被 odr-use"
    odr-use 是 [[basic.def.odr]] 定义的一种使用，它决定一个变量或函数是否必须有定义。`struct S { int m; };` 的 `m` 不是变量，变量的 odr-use 规则对它不适用。没有对象时也能写 `sizeof(S::m)`，与此有关（[[expr.prim.id]]）。

## 思考题

!!! question "思考题 1"
    下面引入了哪些变量？哪些实体不是变量？

    ```cpp
    struct P { int a; static int b; int& c; };
    template<int N, class T> void f(T t, int (&arr)[N]) {
      auto [x, y] = std::pair{1, 2};
      auto l = [z = t] { return z; };
    }
    ```

<details markdown="1">
<summary>答案</summary>

变量有：`P::b`（静态数据成员）、`t` 和 `arr`（函数形参，分别声明对象和引用）、`l`，以及结构化绑定声明引入的那个无名变量（[[dcl.struct.bind]]）。

不是变量的实体有：`P::a`、`P::c`（非静态数据成员，`c` 虽是引用也被 ¶7.1 排除）；`N`、`T`（模板形参）；`x`、`y`（结构化绑定）；`z`（init-capture）；还有类 `P` 和函数模板 `f`。
</details>

!!! question "思考题 2"
    `static` 局部变量是局部实体吗？为什么 lambda 不捕获也能用它？

<details markdown="1">
<summary>答案</summary>

不是。¶9 只把自动存储期的变量列为局部实体，`static` 局部变量具有静态存储期。[[basic.def.odr#10]] 的 odr-usable 限制只针对局部实体，所以 lambda 和局部类的成员函数都可以直接使用它。
</details>

## 小结

| 概念 | 一句话 |
|---|---|
| [[g:name|名字]] | 标识符（标号、goto 目标、模块名、属性记号除外）、`operator T`、`operator@`、`operator""_x` |
| 声明 | ¶5 的 18 种形式之一，不等于文法非终结符 *declaration* |
| [[g:entity|实体]] | 15 种，不含对象和值 |
| 指代 | 名字指代底层实体，穿透别名 |
| [[g:variable|变量]] | 由声明引入的对象或引用，不含非静态数据成员和模板形参 |
| [[g:local-entity|局部实体]] | 自动存储期变量、对应的结构化绑定、结果绑定、`*this` |
