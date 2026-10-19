---
title: 单一定义规则（ODR）
summary: 一个翻译单元里每样东西至多定义一次；被 odr-use 的普通函数和变量在整个程序里恰好定义一次；类、inline 函数、模板这些可以在多处定义的东西，各处定义必须相同。本页还定义了潜在求值、潜在结果集、odr-use 和 odr-usable。
status: done
papers: P0386R2, P1787R6, P2686R5, P2996R13
related: basic.def, basic.link, topics/value-categories, basic.pre, basic.scope, expr.const, dcl.inline, expr.prim.lambda.capture, module.reach, temp.point
tags: ODR, odr-use, 链接, inline, 模板, IFNDR
updated: 2026-10-19
---

!!! tldr
    - 一个翻译单元里，同一个类、函数、变量至多定义一次，违反时编译器必须报错。
    - 一个普通（非 inline、非模板）的函数或变量如果被 odr-use，整个程序里必须恰好有一个定义。odr-use 大致是需要它的地址或函数体的使用；只读一个编译期已知的常量值不算。
    - 类、枚举、inline 函数和变量、模板可以在每个翻译单元里各定义一次，但各处的定义必须由相同的记号组成，并且含义相同。违反时不要求诊断，链接器会悄悄只留下一份。
    - 自动变量和 `*this` 只能在同一次函数调用的范围里 odr-use，跨过 lambda 要捕获，跨过局部类不行。
    - inline 函数里的 `static` 局部变量在整个程序里只有一个，这是 ODR 把多处定义视为同一个定义的结果。

## 链接器不检查的约定

```cpp title="a.cpp"
inline int version() { return 1; }
int from_a() { return version(); }
```

```cpp title="b.cpp" ifndr
inline int version() { return 2; }  // 与 a.cpp 的定义不同：违反 ODR
int from_b() { return version(); }
```

`main` 打印 `from_a()` 和 `from_b()`。本机 Clang 23 编译和链接都没有任何提示：`-O0` 下输出 `1 1`，调换两个文件的链接顺序后输出 `2 2`，`-O2` 下输出 `1 2`。

C++ 程序由许多**翻译单元**（translation unit，TU，单独编译的一个源文件连同它包含的头文件）分别编译，再由链接器拼起来。链接器只看得到符号名，看不到类型和源码。inline 函数在每个包含它的 TU 里都有一份，链接器只留其中一份，至于两份是否相同，它不比较。

**单一定义规则**（One-Definition Rule，ODR）就是让这套模型成立的约定。它有三层：

1. 一个 TU 里每样东西至多定义一次（¶2）。编译器看得到整个 TU，违反时必须报错。
2. 被用到的普通函数和变量，整个程序里恰好一个定义（¶12、¶16.1）。少了或多了都是 IFNDR（ill-formed, no diagnostic required，非良构但不要求诊断，见 [[intro.compliance]]），通常表现为链接错误，但标准不作保证。
3. 可以在多个 TU 里定义的东西，各处定义必须相同（¶16）。违反时同样是 IFNDR，而且几乎从来不会被报告，上面的例子就是这样。

## 可定义项与每个 TU 至多一个定义（¶1–¶2）

¶1 ODR 管的东西叫**可定义项**（definable item），共七种：类类型（包括闭包类型）、枚举类型、函数、变量（[[basic.pre#7]]，不含非静态数据成员）、模板化实体（模板、模板里定义的实体等，[[temp.pre]]）、某个作用域中函数形参的默认实参、默认模板实参。

不在清单里的有命名空间（所以可以反复打开）、类型别名、using 声明、宏和标号。

默认实参单独列出，是因为它是一段在调用点代入的代码，可能在不同 TU 里写得不一样，ODR 要把它也纳入必须一致的范围（¶16.11）。加上在给定作用域中的限定，是因为同一个函数在不同块作用域里的重声明可以各自给出默认实参（[[dcl.fct.default]]）。

¶2 任何 TU 都不能包含同一个可定义项的多于一个定义。

```cpp error
struct S { int a; };
struct S { int a; };  // error: 同一 TU 中重复定义，哪怕完全相同
inline void f() { }
inline void f() { }   // error: inline 也不行
```

同一个头文件被一个 TU 间接包含两次，里面的类就被定义了两次，头文件保护（include guard 或 `#pragma once`）就是为此存在的。¶2 只管定义：`extern int x; extern int x;`、`typedef int I; typedef int I;` 都是合法的重复声明。

## 什么时候需要定义：odr-use

只是在代码里提到一个变量，并不一定需要它的定义：

```cpp run ok
extern int e;          // 从未定义
int main() {
  e;                   // 不需要定义
  (void)e;             // 不需要定义
  (void)sizeof(e);     // 不需要定义
  decltype(e) k = 0;   // 不需要定义
  return k;
}                      // 链接成功
```

标准用 **odr-use** 描述需要定义的那种使用。定义它要先准备两个概念：潜在求值和潜在结果集。

### 潜在求值（¶3）

¶3 一个表达式或转换是**潜在求值**（potentially evaluated）的，除非它是不求值操作数（[[expr.context]]）或其中的一部分。不求值操作数出现在 `sizeof`、`decltype`、`noexcept` 运算符、*requires-expression* 里，以及非多态类类型的 `typeid` 操作数里。上例中 `sizeof(e)` 和 `decltype(e)` 里的 `e` 就不是潜在求值的。

潜在的意思是可能被求值，标准不做控制流分析。`if (false) g();` 里的 `g()` 仍是潜在求值的。`if constexpr` 中被丢弃的分支（[[stmt.if]]）也仍是潜在求值的，但 ¶12、¶13 规定其中的 odr-use 不要求定义。

### 潜在结果集（¶3）

ODR 关心的是：一个变量的名字出现在表达式里时，是否需要这个变量真的有一块存储。只读它的值，而值在编译期已知，编译器把值代进去就行；需要它的地址，比如取址或绑定引用，就必须有定义。

难点是名字往往包在别的运算里：`(c ? x : y) + 1` 只读值，`&(c ? x : y)` 要的却是地址。**潜在结果集**（set of potential results）穿过那些不改变对象身份的运算，找出最终作为对象本身被使用的名字。表达式 E 的潜在结果集如下：

| ¶ | E 的形式 | 潜在结果集 |
|---|---|---|
| 3.1 | *id-expression*（名字），或 *splice-expression* {{c++26}} | {E} |
| 3.2 | 数组的下标 `a[i]` | `a` 的潜在结果集 |
| 3.3 | 访问非静态数据成员或直接基类 `E1.m` | `E1` 的潜在结果集 |
| 3.4 | 访问静态数据成员 `E1.s` | 指称该成员的 *id-expression* |
| 3.5 | 成员指针 `E1 .* E2` | `E1` 的潜在结果集 |
| 3.6 | 括号 `(E1)` | `E1` 的潜在结果集 |
| 3.7 | 结果是 glvalue 的条件表达式 `c ? E2 : E3` | `E2`、`E3` 的潜在结果集之并 |
| 3.8 | 逗号表达式 `E1, E2` | `E2` 的潜在结果集 |
| 3.9 | 其他 | 空集 |

函数调用、取址、算术运算都属于 3.9。`f(x)` 的潜在结果集是空的，`x` 只在实参 `x` 自己的潜在结果集里，所以要看这个实参怎样初始化形参：按值传递时读值，按引用传递时绑定引用。

下标只穿过数组：`p[i]`（`p` 是指针）等价于 `*(p+i)`，访问的是另一个对象。条件表达式只有在结果是 glvalue 时才穿过；如果两边需要转换、结果是纯右值，两个操作数已经各自被读值。逗号表达式只取右操作数，左操作数是一个丢弃值表达式，单独判断。

### 变量的 odr-use（¶5）

¶5 如果一个表达式是指称变量 x 的 *id-expression* 或 *splice-expression*，就说它**命名**了 x。出现在程序点 P 的潜在求值表达式 N 命名了 x，就 **odr-use** 了 x，除非：

- ¶5.1 x 是一个在 P 处可用于常量表达式的引用；或
- ¶5.2 N 在某个表达式 E 的潜在结果集里，并且
    - ¶5.2.1 E 是丢弃值表达式，而且没有对它做左值到右值转换；或
    - ¶5.2.2 x 是在 P 处可用于常量表达式的非 volatile 对象，没有 mutable 子对象，并且
        - ¶5.2.2.1 E 访问的是引用类型的非静态数据成员，对象表达式的类型不带 volatile；或
        - ¶5.2.2.2 对 E 做了左值到右值转换，E 的类型是非 volatile 的非类类型。

这里的**左值到右值转换**（[[conv.lval]]）就是从一个对象里把值读出来（背景见 [[topics/value-categories]]）。**可用于常量表达式**（[[expr.const.init]]）的变量大致是：`constexpr` 变量，或者用常量初始化的 `const` 整型或枚举变量，或者引用，并且它的初始化在 P 处可见。

概括地说，**变量被潜在求值的表达式命名就是 odr-use，除非实际只需要它的值而这个值在编译期已知，或者根本没用到它**。各条例外的理由：

- ¶5.2.2.2 是最常见的情形。`constexpr int N = 3;` 在 `int a[N];`、`return N + 1;`、按值传参 `f(N)` 里都只被读值，编译器直接代入 3。要求非类类型，是因为读取类对象要调用拷贝构造函数，需要对象的地址；要求没有 mutable 子对象，是因为 mutable 成员在运行时可能改变。
- ¶5.2.2.1：设 `constexpr B b = {x};`，`B` 有引用成员 `int& r`。`b.r` 绑定到哪个对象在编译期就知道，不需要 `b` 本身的存储。
- ¶5.1：引用绑定到哪个对象在编译期已知时，使用它不需要引用本身的存储。
- ¶5.2.1：`e;`、`(void)e;` 既不读值也不取址，所以开头的例子能链接成功。但对 volatile 变量，这样的表达式会做左值到右值转换（[[expr.context#2]]），因而构成 odr-use：

```cpp
extern volatile int ev;  // 从未定义
int main() { ev; }       // 读取 volatile 变量：odr-use，链接失败
```

下面是静态数据成员的典型例子。`static const` 成员在类内只是声明（[[basic.def#2.3]]），所以用法决定了程序能否链接：

```cpp
struct S { static const int x = 0; };  // 类内只是声明
const int& f(const int& r) { return r; }
int g(int v) { return v; }
int main(int argc, char**) {
  bool b = argc > 1;
  int n = b ? (1, S::x) : S::x;  // 只读值：不 odr-use
  int a = g(S::x);               // 按值传参，读值：不 odr-use
  const int& r = f(S::x);        // 绑定引用：odr-use
  return n + a + r;              // 本机 -O0 链接失败："S::x" 未定义
}
```

标准的例 1 有同样的结构，并加上了 C++26 的 splice：`int o = [:^^S::x:];` 中的 splice 表达式本身就是潜在结果，读值不 odr-use `S::x`。

可用于常量表达式这一条件决定了 lambda 里哪些变量可以不捕获就读：

```cpp error
void k() {
  constexpr int n = 3;
  const int m = 4;       // const 整型，常量初始化
  const double d = 1.5;  // 不是整型，不可用于常量表达式
  auto l1 = [] { return n + m; };               // OK：只读值
  auto l2 = [] { int a[m]; return sizeof a; };  // OK
  auto l3 = [] { return &n; };  // error: 取址 odr-use n
  auto l4 = [] { return d; };   // error: 读 d 也是 odr-use
}
```

!!! note "标准的例 2"
    ¶5 的例 2 用自动存储期的 `constexpr` 对象演示 ¶5.2.2.1，例如 `constexpr B b1 = {x};`，其中 `x` 是同一函数里的局部变量。这依赖 C++26 的 [[P2686R5]]：`constexpr` 引用或指针可以指向同一函数里的自动变量（[[expr.const.init]] 中的 constexpr-referenceable）。本机 Clang 23 还没有实现这一点，对 `r`、`b1`、`b2` 的初始化报 "must be initialized by a constant expression"。

    例子的要点是：`g(cond ? b1.r : b2.r)` 只通过引用成员取得 `x` 或 `y`，不 odr-use `b1`、`b2`。而在 lambda 里，`b1.r` 引用的 `x` 不再是 constexpr-referenceable 的，`b1` 在那里不可用于常量表达式，于是 `return b1.r;` odr-use 了 `b1`，又没有捕获，所以是错误（见 ¶10）。

### 结构化绑定与 `*this`（¶6–¶7）

¶6 结构化绑定只要被潜在求值的表达式命名，就是 odr-use，没有变量那样的常量例外。所以在 lambda 里使用结构化绑定就要捕获它（C++20 起允许捕获结构化绑定）。

¶7 `this` 作为潜在求值表达式出现时，`*this` 被 odr-use。成员函数里写的 `m` 会被隐式改写成 `(*this).m`（[[expr.prim.id.general]]），这也算。结合 ¶10，这就是 lambda 里访问成员要捕获 `this` 的依据：

```cpp error
struct W {
  int m = 0;
  auto get() { return [] { return m; }; }      // error: 没有捕获 this
  auto ok() { return [this] { return m; }; }   // OK
};
```

### 函数的 odr-use（¶4、¶8–¶9）

¶8 函数被潜在求值的表达式或转换命名，就被 odr-use。¶4 规定了函数被**命名**的方式。

¶4.1 最主要的方式是被重载决议选中：取函数地址、调用函数、使用重载运算符、用户定义转换、*new-expression* 选中的分配函数、构造函数，都属于这一类（注 2）。纯虚函数是例外，只有用显式限定名、且不形成成员指针时才算被命名。

纯虚函数的例外有实际意义。通过 `p->f()` 虚调用时，重载决议选中的是纯虚的 `B::f`，但运行时调用的是最终覆盖函数，所以不需要 `B::f` 有定义。写成 `B::f()` 就是非虚调用，确实会调用 `B::f`：

```cpp
struct B { virtual void f() = 0; };          // 纯虚函数，没有定义
struct D : B { void f() override { B::f(); } };  // 限定名调用：odr-use B::f
int main() { D d; d.f(); }                   // 本机链接失败："B::f()" 未定义
```

`&B::f` 虽然也用了限定名，但它形成成员指针，通过成员指针调用仍然是虚调用，所以被排除。

注 2 还说明，被选中用来拷贝或移动的构造函数，即使调用被省略，也算被命名。所以 NRVO 这类非强制省略不能绕过对拷贝构造函数的要求。C++17 起由纯右值直接初始化的强制省略则根本不选择拷贝构造函数：

```cpp run ok
struct M { M() {} M(const M&) = delete; };
M make() { return M{}; }      // OK：纯右值直接初始化返回对象

struct N { N() {} N(const N&) {} };
N make2() { N n; return n; }  // N(const N&) 被选中，即使被省略也被 odr-use
                              // 若它是 deleted 的，这里就是错误
int main() { }
```

¶4.2–¶4.3 类的 `operator delete` 在两种情况下被命名：它是 *new-expression* 所选分配函数唯一匹配的释放函数（构造函数抛出异常时用它回收内存，[[expr.new]]）；或者它是 *delete-expression* 选中的常规释放函数（[[expr.delete]]）。

¶8 另外三条规则与调用无关：

- 非纯虚的虚函数总是被 odr-use，无论是否被调用。vtable 要填入每个虚函数的地址，构造函数又会引用 vtable，所以声明了虚函数却不定义就违反 ODR。实践中的表现是 `undefined reference to vtable for X`。
- 类的非 placement 分配和释放函数被该类构造函数的定义 odr-use；非 placement 释放函数被析构函数的定义 odr-use，或者在虚析构函数的定义处被查找选中而 odr-use（[[class.dtor]]）。脚注 13 说明实现不必真的在构造或析构函数里调用它们，但允许这样实现。Itanium ABI 的删除析构函数（deleting destructor）就在虚析构函数里调用 `operator delete`，让 `delete p` 能通过 vtable 找到正确的释放函数。

¶9 隐式定义的拷贝或移动赋值函数逐个成员赋值，因此 odr-use 成员类的赋值运算符（[[class.copy.assign]]）；构造函数按 [[dcl.init]] 的规定被 odr-use；析构函数在被**潜在调用**（potentially invoked）时被 odr-use，例如自动变量离开作用域、临时对象销毁（[[class.dtor]]）。

```cpp
struct S { ~S(); };           // 声明但不定义
void f(bool c) { if (c) { S s; } }
int main() { f(false); }      // ~S 被潜在调用：链接失败，尽管从未执行

struct B { virtual void v(); virtual void p() = 0; };
struct D : B { void p() override { } };
int g() { D d; return 0; }    // B::v 非纯虚，总被 odr-use：链接失败
```

## 定义必须存在（¶12–¶14）

¶12 程序里每个被 odr-use 的函数或变量（被丢弃语句里的除外）都必须至少有一个定义，不要求诊断。定义可以写在程序里，可以来自标准库或其他库，也可以是隐式定义的特殊成员函数。

为什么不要求诊断？定义可能在任何一个 TU 或库里，编译器看不到全局。链接器通常能发现缺失的符号，但标准不把链接器诊断写进语言规则，而且有些情况链接器也发现不了：

<div class="compare" markdown="1">

```cpp run ok
void never_defined();
template<class T> void h() {
  if constexpr (sizeof(T) > 100)
    never_defined();  // 被丢弃
}
int main() { h<int>(); }
```

```cpp run ifndr
void never_defined();
int main() {
  if (false)
    never_defined();  // odr-use
}
```

</div>

左边被丢弃的语句里的调用不要求定义，程序良构。右边按标准是 odr-use 却没有定义，属于 IFNDR；本机 Clang 23 即使在 `-O0` 下也删掉了 `if (false)` 分支，链接成功。这就是 IFNDR 的典型表现：看起来没事，但没有任何保证。

¶12 的例 5 是编译器能看出来的情形：

```cpp error
auto f() {
  struct A {};
  return A{};
}
decltype(f()) g();  // g 返回局部类 A
auto x = g();       // odr-use g
```

`g` 被 odr-use，本 TU 没有定义它，别的 TU 也不可能定义它，因为局部类 `A` 在别处写不出来。Clang 直接报错："function 'g' is used but not defined in this translation unit, and cannot be defined in any other translation unit because its type does not have linkage"。

¶13 inline 函数和变量还有更强的要求。**定义域**（definition domain）是一个 TU 中除去私有模块片段（`module :private;` 之后的部分）的部分，或者那个私有模块片段本身。inline 函数或变量在某个定义域里被 odr-use，它的定义就必须从这个定义域的末尾可到达。

这就是 inline 函数必须在每个用到它的 TU 里都有定义的现代表述，也是头文件库要把 inline 函数的实现写在头文件里的原因：编译器要在调用点内联展开，就得看到函数体。要求的是从末尾可到达，所以调用可以出现在定义之前。

私有模块片段自成一个定义域，导入者看不到其中的内容。如果私有片段之前的 inline 函数调用了只在私有片段里定义的 inline 函数，就违反了本条。

¶14 在每个要求类类型完整的地方，类的定义都必须可到达。例 6 说明只用作指针的类不需要定义：

```cpp run ok
struct X;       // 声明 X
struct X* x1;   // 形成指针，不需要 X 完整
X* x2;
int main() { }
```

注 3 列出了需要类 `T` 完整的场合：定义 `T` 类型的对象或非静态数据成员，`new T`，读取 `T` 类型的值，转换到 `T`，把表达式转换为 `T*` 或 `T&`（空指针常量和 `void*` 除外），对 `T` 类型的表达式做成员访问，`sizeof`、`alignof`、`typeid` 作用于 `T`，定义或调用以 `T` 为形参或返回类型的函数，定义以 `T` 为基类的类，对 `T` 类型的左值赋值，`catch` 的类型是 `T`、`T&` 或 `T*`。

## 局部实体能在哪里用：odr-usable（¶10–¶11）

```cpp error
void f(int n) {
  [] { n = 1; };              // error: lambda 没有捕获 n
  struct A {
    void f() { n = 2; }       // error: 跨过了 A::f 的形参作用域
  };
  void g(int = n);            // error: 跨过了 g 的形参作用域
  [=](int k = n) {};          // error: 默认实参不在 lambda 函数体内
  [&] { [n]{ return n; }; };  // OK
}
```

这是标准的例 3。局部实体（[[basic.pre#9]]：自动变量、对应的结构化绑定、结果绑定、`*this`）属于某一次函数调用。块作用域、契约断言、lambda 的形参列表都还在同一次调用里，可以直接穿过；局部类的成员函数、嵌套函数声明的形参作用域属于另一个函数，穿不过去。lambda 像一扇门，有捕获时才打开，而且要进到 lambda 的函数体里才算过了门，所以 lambda 形参的默认实参仍在门外。

¶10 精确的规则是：局部实体在某个作用域中是 **odr-usable** 的，当且仅当

- ¶10.1 如果它是 `*this`，必须存在一个外围的类作用域或非 lambda 的函数形参作用域，并且如果最内层的这种作用域是函数形参作用域，它属于非静态成员函数；
- ¶10.2 从引入该实体的地方到这个作用域之间，每个介于其间的作用域（intervening scope，[[basic.scope.scope#1]]）都是下面之一：块作用域；契约断言作用域（[[basic.scope.contract]]）{{c++26}}；*lambda-expression* 或 *requires-expression* 的函数形参作用域；捕获了该实体（显式捕获或有默认捕获）的 lambda 的 lambda 作用域，且这个 lambda 的函数体也在介于其间的作用域之中。

局部实体在它不是 odr-usable 的作用域里被 odr-use，程序非良构。

这些错误只在 odr-use 时出现。只读一个可用于常量表达式的变量的值不构成 odr-use，是否 odr-usable 也就无关紧要：`constexpr int n = 3; [] { return n; }` 是合法的。

¶11 的例 4 把这一点推到模板里。是否 odr-use 要到实例化时才知道，所以同一个泛型 lambda 的不同特化可以一个合法、一个非法：

```cpp
void g() {
  constexpr int x = 1;
  auto lambda = [] <typename T, int = ((T)x, 0)> {};  // OK
  lambda.operator()<int, 1>();      // OK：根本不用默认模板实参
  lambda.operator()<int>();         // OK：(int)x 只读值
  lambda.operator()<const int&>();  // error: 绑定引用，odr-use x
}

void h() {
  constexpr int x = 1;
  auto lambda = [] <typename T> { (T)x; };  // OK
  lambda.operator()<int>();         // OK：读值
  lambda.operator()<void>();        // OK：丢弃值表达式（¶5.2.1）
  lambda.operator()<const int&>();  // error: odr-use x
}
```

!!! impl "Clang 与例 4"
    本机 Clang 23 与标准有出入：在 `g()` 里，它对 lambda 的定义本身（默认模板实参 `((T)x, 0)`）就报 "variable 'x' cannot be implicitly captured in a lambda with no capture-default specified"；在 `h()` 里，它接受 `<int>`，却对 `<void>` 报同样的错误。按标准，只有两行 `<const int&>` 是错误。非模板的情形（`[] { return x; }`）Clang 处理正确。

## 多个 TU 中的定义（¶16）

¶16 是 ODR 的主体，说的是在多个 TU 里都有定义的可定义项 D：

- ¶16.1 如果 D 是非 inline、非模板化的函数或变量，程序非良构。它在整个程序里至多一个定义，加上 ¶12 的至少一个，被 odr-use 时就是恰好一个。
- ¶16.2 如果各 TU 的定义不满足下面的要求，程序非良构。

只有当 D 附属于具名模块、而且后一个定义处能看到前一个定义时，才要求诊断。传统的头文件代码违反这些规则，全部是 {{ifndr}}。

不属于 ¶16.1 的可定义项都可以在每个 TU 里各定义一次：类、枚举、inline 函数和变量、模板化实体、默认实参。这正是可以写在头文件里的东西的完整清单。

| 可定义项 | 每个 TU | 整个程序 |
|---|---|---|
| 非 inline、非模板化的函数和变量 | ≤ 1 | 被 odr-use 时恰好 1，否则 ≤ 1 |
| inline 函数和变量 | ≤ 1，在 odr-use 它的定义域末尾可到达 | 每个 TU 可各有一个，必须相同 |
| 类、枚举 | ≤ 1，在需要完整类型处可到达 | 每个 TU 可各有一个，必须相同 |
| 模板化实体 | ≤ 1 | 每个 TU 可各有一个，必须相同 |
| 默认实参、默认模板实参 | ≤ 1（在给定作用域中） | 必须相同（¶16.11） |

各处定义必须满足的要求如下。如果 D 是无名枚举，要求只针对在同一程序点都可到达的那些定义。

### 记号相同，含义也相同（¶16.3–¶16.5）

¶16.3 这样的定义不能附属于具名模块（[[module.unit]]）。具名模块里的实体只有一个定义，导入者通过可到达性看到它，不需要也不允许在别处重复。只有附属于全局模块的实体，也就是传统头文件代码，才适用多处定义、必须一致的规则。

¶16.4 每个定义必须由相同的记号序列组成，闭包类型的定义视为由对应 lambda 表达式的记号组成。这里的记号是预处理之后的记号（[[lex.phases]]），所以空白和注释的差异没有影响，宏展开的结果不同则会违反这条。同一个头文件在两个 TU 里用不同的 `-D` 选项编译，就可能出问题。

¶16.5 记号相同还不够，每个定义里对应的名字经过名字查找、重载决议和偏特化匹配之后，必须指代相同的实体。有两个例外：

- ¶16.5.1 名字可以指代一个具有内部链接或无链接的非 volatile `const` 对象，只要它在所有定义里类型相同（字面类型）、用常量表达式初始化、值相同，并且在任何定义里都没有被 odr-use；
- ¶16.5.2 名字可以指代一个具有内部链接或无链接、用常量表达式初始化的引用，只要它在所有定义里引用同一个对象或函数。

最常见的头文件写法靠 ¶16.5.1 才合法：

```cpp title="config.h"
const int kBufSize = 4096;     // 内部链接：每个 TU 一个独立的对象
inline int buffer_bytes() {
  return kBufSize * 2;         // 各 TU 中指代不同的对象，但只读值：OK
}
inline const int* buffer_addr() {
  return &kBufSize;            // 取址是 odr-use：违反 ODR（IFNDR）
}
```

`buffer_addr` 在不同 TU 里本该返回不同的地址，链接器却只留下一个定义，留哪个取决于链接顺序。改成 `inline constexpr int kBufSize = 4096;` 就没有问题：inline 变量有外部链接，全程序只有一个对象。

!!! tip "头文件常量为什么推荐 `inline constexpr`"
    命名空间作用域的 `constexpr` 变量隐含 `const`，因而具有内部链接（[[basic.link#3]]），每个包含该头文件的 TU 都有一个副本。加上 `inline` 后它有外部链接，全程序只有一个对象，取址和在 inline 函数里 odr-use 都安全。C++17 标准库把 `std::is_same_v` 这类变量模板定义为 `inline constexpr`，也是出于这个考虑。

### 编译器隐式选择的东西也要相同（¶16.6–¶16.12）

源码相同、名字指代的实体相同，编译器在背后做的选择仍可能不同。下面几条逐项堵住这些缺口。

¶16.6 对应的 lambda 表达式必须有相同的闭包类型（D 的默认实参和默认模板实参里的除外，见 ¶18）。通常每个 lambda 表达式都有独一无二的闭包类型，但 inline 函数的多处定义视为同一个定义，里面的 lambda 也必须是同一个类型。实现为此要给它们相同的修饰名，Itanium ABI 用所在实体加序号编码，例如 `f()::{lambda()#1}`。

¶16.7 对应的实体必须有相同的语言链接（`extern "C"` 或 `extern "C++"`，[[dcl.link]]）。

¶16.8 静态或线程存储期的 `const` 对象如果在某个定义里是常量初始化的，就必须在所有定义里都是常量初始化的。常量初始化的对象在编译期写进程序映像，动态初始化的对象在运行时由初始化代码填入，两种混在一起，初始化的时机和值都会出问题。

¶16.9 对应的、不依赖模板参数的显然常量求值表达式（数组边界、`static_assert`、`if constexpr` 的条件、模板实参等，[[expr.const]]）必须有相同的值。这针对的是记号和名字都相同、常量值却不同的情况，例如依赖实现定义的值。

¶16.10 引用的重载运算符，以及对转换函数、构造函数、`operator new`、`operator delete` 的隐式调用，必须是同一个函数。这些调用在源码里没有名字，¶16.5 管不到。典型的违反方式是某个重载只在一部分 TU 里可见：

```cpp title="a.cpp"
struct P { int v; };
bool operator==(P, long);
inline bool is_zero(P p) { return p == 0; }  // 选中 operator==(P, long)
```

```cpp title="b.cpp" ifndr
struct P { int v; };
bool operator==(P, long);
bool operator==(P, int);                     // 只有 b.cpp 有这个更好的重载
inline bool is_zero(P p) { return p == 0; }  // 选中 operator==(P, int)
```

¶16.11 函数调用用到的默认实参、模板标识用到的默认模板实参，视为其记号出现在 D 的定义里，递归地满足以上所有要求。默认实参是在调用点代入的：设有 `inline void f() { g(); }`，而 `g` 声明为 `void g(int = N);`，`f` 的定义实际上包含了 `g(N)`。

¶16.12 {{c++26}} 对应的反射表达式 `^^x` 必须得到等价的值（[[expr.eq]]）。如果两个 TU 里 `x` 指代不同的实体，反射值不同，由反射驱动生成的代码也会不同。

### 隐式定义和模板（¶17）

¶17.1 如果 D 是有隐式声明的构造函数的类，就当作该构造函数在每个 odr-use 它的 TU 里都被隐式定义，各处的隐式定义必须为 D 的子对象调用相同的构造函数。例 7：

```cpp title="tu1.cpp"
struct X {
  X(int, int);
  X(int, int, int);
};
X::X(int, int = 0) { }  // tu1 中 X(int, int) 有默认实参
class D {
  X x = 0;              // 选 X(int, int)
};
D d1;
```

```cpp title="tu2.cpp" ifndr
struct X {
  X(int, int);
  X(int, int, int);
};
X::X(int, int = 0, int = 0) { }  // tu2 中 X(int, int, int) 有默认实参
class D {
  X x = 0;              // 选 X(int, int, int)：违反 ODR
};
D d2;
```

`D` 的两个定义记号完全相同，名字 `X` 也指代同一个类，但类外定义追加的默认实参不同，`X x = 0` 的重载决议结果也就不同。从 `D` 自己的记号看不出这个差别，所以要单独规定。

¶17.2 默认的三路比较运算符（`operator<=>` 声明为 `= default`，[[class.spaceship]]）也一样：各 TU 中的隐式定义必须为每个子对象调用相同的比较运算符。

¶17.3 如果 D 是模板，要求既适用于模板定义中来自外围作用域的名字，也适用于实例化点处的依赖名（[[temp.dep]]、[[temp.point]]）。不同 TU 在实例化点看到的东西不同（ADL 找到的函数、显式特化），就违反 ODR。这也是显式特化必须在第一次使用之前声明的原因（[[temp.expl.spec]]）。

### 视为同一个实体（¶18–¶19）

¶18 上述要求同样适用于在 D 的每个定义里定义的对应实体，包括 lambda 的闭包类型，但不包括定义在 D 的默认实参里、或者定义在不属于 D 的实体的默认实参里的实体。对这些实体和 D 本身，**行为如同只有一个实体、一个定义**。

由此可得：

- inline 函数里的 `static` 局部变量在整个程序里只有一个。`inline int& counter() { static int c = 0; return c; }` 被 10 个 TU 包含，所有 TU 共享同一个 `c`，Meyers 单例因此可以写在头文件里。
- inline 函数里的 lambda 闭包类型、局部类在各 TU 中是同一个类型；对 inline 函数取地址，各 TU 得到相同的地址。
- 字符串字面量不在其中。字面量不是实体，它求值得到的数组对象在不同求值之间是否是同一个，标准规定为未指定（[[lex.string#9]] 的注，[[CWG1823]]）。所以不能假设 inline 函数在不同 TU 里返回的 `"hello"` 指针相等。

注 4 补充：这些实体仍然在多个 TU 里被声明，[[basic.link]] 照样适用于这些声明。出现在 D 的类型里的 lambda 可能让不同的声明有不同的类型，出现在 D 的默认实参里的 lambda 在不同 TU 里仍可能是不同的类型。

¶19 的例 8 显示了排除条款的细微之处：

```cpp
inline void f(bool cond, void (*p)()) {
  if (cond) f(false, []{});
}
inline void g(bool cond, void (*p)() = []{}) {
  if (cond) g(false);
}
struct X {
  void h(bool cond, void (*p)() = []{}) {
    if (cond) h(false);
  }
};
```

- `f`：lambda 在函数体里，各 TU 中是同一个闭包类型，没有问题。
- `g`：lambda 在 `g` 自己的默认实参里，被排除在同一闭包类型的要求之外，每个 TU 中是不同的类型。但 `g` 的函数体通过 `g(false)` 用到了这个默认实参，按 ¶16.11 它算作 `g` 定义的一部分，于是 `g` 的各个定义用到了不同的实体，{{ifndr}}。
- `X::h`：对 D = `X` 来说，`h` 是在 `X` 里定义的实体，它的默认实参里的 lambda 也是在 `X` 里定义的，不在排除之列，各 TU 中是同一个闭包类型，`X` 可以出现在多个 TU 里。

<details class="fine" markdown="1"><summary>其余条文</summary>

¶15 {{c++26}} 如果可定义项 D 在某个 TU 里由注入声明 X 定义（C++26 静态反射在常量求值中生成的定义，例如 `std::meta::define_aggregate`，[[expr.const.reflect]]），而另一个 TU 也有 D 的定义，那个定义也必须是注入声明，并且特征序列（生成定义所用的那些反射值）与 X 相同。注入的定义没有源码记号，¶16.4 无从适用，所以改用特征序列比较。只有 D 附属于具名模块、且前一个定义可到达时才要求诊断。

¶20 如果在程序的某一点，同一作用域中有多于一个可到达的无名枚举定义，它们的第一个枚举项同名，又都没有用于链接的 typedef 名，那么它们必须是同一个类型，不要求诊断。无名枚举靠第一个枚举项在链接上被认定为同一实体（[[dcl.enum]]）；有了模块之后，同一个 TU 里可能同时看到多个这样的定义（例如来自不同的头单元），¶20 要求把它们视为同一个类型。

</details>

## 实现视角

!!! impl "链接器如何合并多份定义"
    inline 函数、inline 变量、模板实例化、vtable、typeinfo、inline 函数里的静态局部变量及其守卫变量，在目标文件中都标记为可合并：

    - ELF（Linux）：放进 COMDAT 组，链接器对同名组只保留一份，符号通常是 `W`（weak）。
    - Mach-O（macOS）：标记为 weak definition。本机 `nm -m` 对 `inline int version()` 显示 `weak external __Z7versionv`。
    - PE/COFF（Windows）：COMDAT 节，选择策略通常是任选一个。

    Itanium C++ ABI 把这种发射方式叫做 vague linkage。链接器只按符号名合并，从不比较内容，它假定程序遵守了 ODR。这就是 ¶16 的违规几乎从不被报告的原因。开头 `version()` 的例子中，`-O0` 下两处调用都通过符号，链接器保留先看到的那份；`-O2` 下调用被内联，各自用自己的定义。

!!! impl "同名类的不同定义：内存越界"
    两个 .cpp 各自定义了一个自以为私有的同名类：

    ```cpp title="a.cpp"
    struct Node { int v; Node() : v(1) {} };   // 4 字节
    int from_a() { Node n; return n.v; }
    ```
    ```cpp title="b.cpp" ifndr
    struct Node { double d[4]; Node() : d{1, 2, 3, 4} {} };  // 32 字节
    double from_b() { Node n; return n.d[3]; }
    ```

    类内定义的构造函数隐含 inline，两个 `Node::Node()` 修饰名相同，链接器只留一个。本机实验：链接顺序为 b、a 时，`from_a` 里 4 字节的 `n` 被 b 版本的构造函数写入 32 字节，ASan 报 `stack-buffer-overflow ... WRITE of size 32`，不开 ASan 时段错误；顺序为 a、b 时，`from_b` 读到垃圾值。修复办法是把只在一个 .cpp 里用的类型放进无名命名空间，让它具有内部链接（[[basic.link#4]]），各 TU 的 `Node` 就成了不同的实体。

!!! impl "vtable 与 key function"
    Itanium ABI 只在定义了 key function（第一个非 inline、非纯虚的虚函数）的 TU 里发射 vtable；没有 key function 的类，在每个需要它的 TU 里以 vague linkage 发射。忘记定义 key function，vtable 在哪里都不会生成，链接器报 `undefined reference to vtable for X`。这与 ¶8 非纯虚的虚函数总被 odr-use 的规则一致。

!!! impl "检测 ODR 违规的工具"
    - GCC 的 `-Wodr` 配合 LTO（`-flto`），能比较不同 TU 中同名类型的定义，对布局不一致给出警告，上面 `Node` 的情形正是它要抓的。
    - AddressSanitizer 的 `detect_odr_violation` 选项检测插桩过的全局变量在多个模块（如主程序和动态库）中的重复定义，不检查类型或 inline 函数的差异。
    - 对具名模块中的实体，¶16 要求在先前定义可到达时诊断；Clang 合并模块中的定义时会比较定义的哈希。

    这些工具都只能抓住一部分。可靠的预防办法是：一个实体只在一个头文件里定义，TU 私有的东西放进无名命名空间，整个程序用一致的编译选项和宏。MSVC 的标准库用 `#pragma detect_mismatch` 把 `_ITERATOR_DEBUG_LEVEL` 等配置写进目标文件，链接时发现不一致就报 LNK2038，这是针对预处理配置不一致的工程补救。

| ODR 违规的来源 | 违反的条款 | 例子 |
|---|---|---|
| 不同的 `-D` 选项 | ¶16.4 | 一部分 TU 定义了调试宏，头文件里的类多了一个字段 |
| 同名的 TU 私有类型 | ¶16.4 | 两个 .cpp 各自定义 `struct Node` |
| 头文件里的非 inline 定义 | ¶16.1 | 头文件里写 `int counter = 0;` 或普通函数的函数体 |
| 头文件常量被取址 | ¶16.5.1 | inline 函数返回 `&kConst`，或把它传给 `std::max` |
| 实例化点看到的东西不同 | ¶17.3 | 显式特化只在部分 TU 中声明 |
| 默认实参不一致 | ¶16.11、¶17.1 | 不同 TU 的类外定义追加了不同的默认实参 |
| 头文件与库二进制不匹配 | ¶16.4 | 用 v2 的头文件链接 v1 的库 |

## 历史与演进

!!! history
    - C++98 的 ODR 已经有今天的骨架：每个 TU 一个定义；被使用的非 inline 函数或对象恰好一个定义；类、inline 函数、模板的多处定义记号相同、含义相同。那时的使用比较粗糙，名字出现在潜在求值表达式里就算使用；C++03 通过缺陷修正 [[CWG48]] 加了一个例外：满足常量表达式要求、并且立即被读值的对象。
    - C++11 把术语改为 odr-use，与日常意义上的使用区分开；例外条款随 `constexpr` 改写。
    - 潜在结果集来自缺陷修正 [[CWG712]]，它把立即读值的情形推广到穿过 `?:`、逗号、成员访问等运算，并加入丢弃值表达式的例外。
    - C++17 的 inline 变量（[[P0386R2]]）让变量也可以在每个 TU 里各定义一次。
    - C++20 引入模块：用可到达取代出现在本 TU 中，具名模块中的实体只能有一个定义，可见的违规要求诊断。
    - C++23 的 [[P1787R6]] 引入新的作用域模型，odr-usable 改用介于其间的作用域表述。
    - C++26 的静态反射（[[P2996R13]]）让 splice 表达式也能命名变量和函数，并带来了 ¶15 和 ¶16.12；契约断言作用域可以直接穿过（¶10.2）；[[P2686R5]] 允许 `constexpr` 引用指向自动变量，影响了 ¶5 例 2 的写法。

## 常见误解

!!! pitfall "IFNDR 就是链接错误"
    不是。多余的定义可能被链接器悄悄合并（inline、weak 符号）；缺少的定义可能因为优化删掉了调用而不报错；定义不一致几乎从不报错。IFNDR 的程序没有任何行为保证，链接成功不说明没有问题。

!!! pitfall "`if (false)` 里的调用不算使用"
    算。odr-use 是按语法判定的，不做控制流分析。只有不求值操作数里的使用不算，`if constexpr` 被丢弃的分支则不要求定义。析构函数也一样，`if (c) { S s; }` 会 odr-use `~S`。

!!! pitfall "C++17 之后 `static const int` 成员不再需要类外定义"
    只有 `static constexpr` 和显式 `static inline` 的数据成员是 inline 的。`static const int N = 0;` 被 odr-use 时（传给形参为 `const int&` 的 `std::max`、`std::vector::push_back` 等）仍需要类外定义。而且表现随优化级别变化：`-O2` 下调用被内联、常量被折叠，可能碰巧链接成功。

!!! pitfall "在 inline 函数里用命名空间常量会违反 ODR"
    通常不会，¶16.5.1 专门豁免了只读值的内部链接常量。一旦取址或绑定引用，豁免就失效了。

## 思考题

!!! question "思考题 1"
    下面每一处 `S::x` 或 `s.x`，是否 odr-use 了 `S::x`？

    ```cpp
    struct S { static const int x = 1; int m; };
    void take(int);
    void take_ref(const int&);
    void t(bool c, S s) {
      take(c ? S::x : 2);          // (a)
      take_ref(c ? S::x : 2);      // (b)
      take(s.x);                   // (c)
      int arr[S::x];               // (d)
      take_ref(+S::x);             // (e)
    }
    ```

<details markdown="1">
<summary>答案</summary>

都不 odr-use。

- (a) `S::x` 是 `const int` 左值，`2` 是 `int` 纯右值，条件表达式的结果是纯右值，¶3.7 不适用。`S::x` 作为第二操作数自己被读值，E 就是 `S::x` 本身，它可用于常量表达式，¶5.2.2.2 适用。
- (b) 同 (a)。条件表达式先得到一个值，再由临时对象绑定到 `const int&`。
- (c) `s.x` 访问静态数据成员，按 ¶3.4 潜在结果是指称该成员的名字；按值传参时读值，¶5.2.2.2 适用。
- (d) 数组边界只读值。
- (e) 一元 `+` 读取操作数的值，结果是纯右值。`std::max(+S::x, y)` 是避免 odr-use 的常用写法。
</details>

!!! question "思考题 2"
    头文件 `h.h` 中有 `const int N = 10; inline int f() { static int calls = 0; return ++calls + N; }`，被 `a.cpp`、`b.cpp` 包含。有几个 `N` 对象？几个 `calls` 对象？这符合 ODR 吗？

<details markdown="1">
<summary>答案</summary>

`N` 有两个（如果没被优化掉）：命名空间作用域的非 volatile `const` 变量具有内部链接（[[basic.link#3]]），每个 TU 各一个。

`calls` 只有一个：按 ¶18，行为如同只有一个 `f`、一个定义，其中的静态局部变量也只有一个。

符合 ODR。`f` 的两个定义记号相同；名字 `N` 在两个 TU 中指代不同的对象，但满足 ¶16.5.1：字面类型 `const int`，常量初始化，只读值没有被 odr-use，值都是 10。
</details>

!!! question "思考题 3"
    为什么 ¶16.1 不允许非 inline 函数有多个相同的定义，inline 函数却可以？

<details markdown="1">
<summary>答案</summary>

非 inline 函数编译成强符号，链接器遇到同名强符号就报重复定义，这能发现在头文件里不小心写了函数体的错误。inline 明确表示这个函数会出现在多个 TU 里，编译器把它发射成可合并的弱符号或 COMDAT。如果允许非 inline 函数多处定义，所有函数都得这样发射，链接器就失去了检查重复定义的能力。写 `inline` 等于程序员承诺所有定义一致。
</details>

## 小结

| 概念 | 要点 |
|---|---|
| [[g:definable-item|可定义项]] | 类、枚举、函数、变量、模板化实体、默认实参、默认模板实参 |
| 每个 TU 至多一个定义 | ¶2，必须诊断 |
| [[g:potentially-evaluated|潜在求值]] | 不在 `sizeof`、`decltype`、`noexcept`、非多态 `typeid`、requires 表达式里；`if (false)` 里仍算 |
| [[g:potential-results|潜在结果集]] | 穿过括号、数组下标、非静态成员访问、`.*`、glvalue 的 `?:`、逗号右操作数 |
| 变量的 [[g:odr-use]] | 潜在求值地命名它，除非只读一个编译期已知的值，或根本没用到 |
| 函数的 odr-use | 被重载决议选中（纯虚函数仅限限定名调用）；非纯虚的虚函数总是；析构函数被潜在调用时 |
| [[g:odr-usable]] | 局部实体跨 lambda 要捕获，跨局部类或嵌套函数的形参作用域不可用 |
| 恰好一个定义 | 被 odr-use 的非 inline、非模板化函数和变量（IFNDR） |
| 每个 TU 一个，处处相同 | 类、枚举、inline 函数和变量、模板化实体：记号、名字、重载、闭包类型、语言链接等都要相同 |
| 实现 | COMDAT 和 weak 符号；链接器不比较内容；`-Wodr` 加 LTO、ASan 只能抓一部分 |
