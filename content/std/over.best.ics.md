---
title: 隐式转换序列
summary: 重载决议用来"度量"实参与形参匹配程度的工具：标准转换序列（及其类别与等级表）、用户定义转换序列、省略号转换序列、引用绑定、列表初始化序列，以及禁止两次用户定义转换、歧义转换序列等特殊规则。
status: draft
covers: over.best.ics.general, over.ics.scs, over.ics.user, over.ics.ellipsis, over.ics.ref, over.ics.list
papers: P0388R4
related: over.ics.rank, over.match.best, conv, class.conv, dcl.init.ref, dcl.init.list, over.match.list
tags: 重载决议, 转换, 初始化
updated: 2026-10-17
---

[[over.match.best]] 的主规则是"逐实参比较隐式转换序列"。本页定义被比较的对象：**隐式转换序列**（implicit conversion sequence，ICS）是什么、有哪几种、各自由什么组成、各有什么等级。比较规则本身在 [[over.ics.rank]]。

一个核心思想贯穿全页：**ICS 是对"用实参拷贝初始化形参"的建模**。它不是另一套独立的转换规则，而是把 [[dcl.init]]、[[dcl.init.ref]]、[[dcl.init.list]] 中的初始化规则"抽象"成可以比较的序列。不过它**只**关心类型、cv 限定和值类别，所以会刻意忽略一些初始化中实际存在的限制——这些限制在选中之后才检查。

| 子条款 | 内容 | 本页小节 |
|---|---|---|
| [over.best.ics.general] | 定义、三种形式、禁止二次用户定义转换、恒等与派生到基类、歧义转换序列 | §1 |
| [over.ics.scs] | 标准转换序列：类别、等级表、规范顺序 | §2 |
| [over.ics.user] | 用户定义转换序列：前序 SCS + 用户定义转换 + 后序 SCS | §3 |
| [over.ics.ellipsis] | 省略号转换序列 | §4 |
| [over.ics.ref] | 引用绑定 | §5 |
| [over.ics.list] | 列表初始化序列 | §6 |

## §1 总则 [over.best.ics.general]

### 定义（¶1–¶2）

¶1 隐式转换序列是把函数调用中的实参转换到被调用函数对应形参类型所用的一系列转换。它是 [[conv]] 意义上的隐式转换，即受"用单个表达式初始化对象或引用"的规则约束（[[dcl.init]]、[[dcl.init.ref]]）。

¶2 隐式转换序列只关心实参的**类型、cv 限定和值类别**，以及如何把它们转换得与形参相应性质匹配。

!!! std
    "Other properties, such as the lifetime, storage duration, linkage, alignment, accessibility of the argument, whether the argument is a bit-field, and whether a function is deleted, are ignored."

    其他性质——生存期、存储期、链接、对齐、可访问性、是否位域、函数是否被删除——一概忽略。

所以，即使为某对实参/形参定义出了 ICS，最终的转换仍可能非良构（注 1）。这一设计在 [[over.match.viable]] 中已经看到效果：位域、访问性、deleted 都不影响可行性。

### 三种形式（¶3）

¶3 良构的隐式转换序列是以下三种形式之一：

1. **标准转换序列**（standard conversion sequence，§2）；
2. **用户定义转换序列**（user-defined conversion sequence，§3）；
3. **省略号转换序列**（ellipsis conversion sequence，§4）。

[[over.ics.rank#2]] 规定三者之间的基本序：标准 > 用户定义 > 省略号。

### 禁止"二次"用户定义转换（¶4）

¶4 若目标是

- ¶4.1 构造函数的第一形参，或
- ¶4.2 用户定义转换函数的对象形参，

且该构造函数/转换函数是由以下途径成为候选的：

- ¶4.3 [[over.match.ctor]]，实参是类拷贝初始化第二步中的临时对象；
- ¶4.4 [[over.match.copy]]、[[over.match.conv]] 或 [[over.match.ref]]（所有情况）；
- ¶4.5 [[over.match.list]] 的第二阶段，初始化列表恰好有一个本身是初始化列表的元素，目标是类 `X` 构造函数的第一形参，且转换的目标是 `X` 或到 `cv X` 的引用，

则**不考虑**用户定义转换序列。注 2 点明意图：这些规则防止在重载决议中应用多于一次的用户定义转换，从而避免无限递归。

```cpp
struct Y { Y(int); };
struct A { operator int(); };
Y y1 = A();      // error: A::operator int() 不是候选——需要 A→int→Y 两次用户定义转换

struct X { X(); };
struct B { operator X(); };
B b;
X x{{b}};        // error: B::operator X() 不是候选
```

`Y y1 = A()`：拷贝初始化 `Y`，候选（[[over.match.copy]]）是 `Y` 的非 explicit 构造函数 `Y(int)` 和 `Y` 的拷贝/移动构造函数，以及 `A` 的产生 `Y` 或其派生类的转换函数（没有）。`Y(int)` 要求 `A() → int`，而按 ¶4.1 + ¶4.4，这里不考虑用户定义转换序列，于是 `Y(int)` 不可行。

`X x{{b}}`：第二阶段，`{b}` 作为唯一元素去匹配 `X` 的拷贝/移动构造函数的第一形参 `const X&`/`X&&`，目标是 `X` 的引用，¶4.5 适用，`b → X` 的用户定义转换不考虑。否则 `X x{{b}}` 就成了"用 `{b}` 构造临时 `X`（这已经是一次用户定义转换），再拷贝到 `x`"。

!!! note "为什么只说'第一形参'？"
    多实参构造函数 `T(A, B)` 的每个形参都可以独立地接受一次用户定义转换——它们是不同的实参，"一次"的限制是**每个**实参只能有一次。¶4 只关心那些"本身就是一次用户定义转换的一部分"的调用：拷贝初始化里被当作转换来调用的构造函数，以及转换函数的对象形参。

### 非引用形参：建模拷贝初始化（¶5–¶7）

¶5 形参是引用时见 §5。

¶6 形参不是引用时，ICS 建模的是从实参表达式**拷贝初始化**该形参；ICS 就是把实参表达式转换成形参类型的 prvalue 所需的序列。注 3：形参是类类型时，这是为 [over] 定义的**概念上的**转换——真正的初始化是用构造函数完成的，并不是"转换"。

¶7 实参表达式类型的 cv 非限定版本与形参类型**相同**时，ICS 是**恒等转换**。形参是类类型、实参是（可能 cv 限定的）**派生类**类型时，ICS 是**派生到基类转换**，具有 **Conversion 等级**。注 4：没有这样的标准转换，派生到基类转换只存在于 ICS 的描述中。

```cpp
struct A {
  A();
  A(A&);            // 只有非 const 的拷贝构造函数
};
void f(A);
void f(...);
void use(const A ca) {
  f(ca);            // error: ICS 是恒等（选中 f(A)），但实际初始化时找不到能接受 const A 的构造函数
}
```

这正是标准例 2 想说明的：从 `const A` 到 `A` 形参的 ICS 是恒等序列（它不包含任何"转换"），即使对 `A` 做拷贝初始化时找不到可行的构造函数。所以 `f(A)` 依然可行，而且以恒等胜过省略号，被选中后才在初始化形参时出错。

为什么不在计算 ICS 时就去做一次完整的构造函数重载决议？因为那会让 ICS 的计算依赖于构造函数的可访问性、是否删除等等，与 ¶2 的"只看类型"原则冲突；更实际的原因是，按值传递同类对象的 ICS 应该是"恒等"，否则 `f(A)` 与 `f(const A&)` 之类的比较会完全乱套。

### 静态成员函数的隐式对象形参（¶8）

¶8 形参是静态成员函数的隐式对象形参时，ICS 是一个标准转换序列，它**既不比任何其他标准转换序列好，也不比它差**。

这使得静态与非静态成员函数可以在同一个候选集里公平地比较：对象实参在比较中被"中性化"，结果完全取决于其余实参。

### 隐式对象形参与赋值左操作数：只允许标准转换（¶9）

¶9 在所有语境下，转换到**隐式对象形参**或**赋值操作的左操作数**时，只允许标准转换序列。注 5：转换到**显式对象形参**时可以包含用户定义转换序列。

```cpp
struct C {
  void k(this int);           // 显式对象形参是 int
  operator int() const { return 0; }
  void m(this const C& c) {
    c.k();                    // OK：c → int 经用户定义转换
  }
};
```

这是显式对象形参（*deducing this*）与隐式对象形参的一个真实差别：`this` 形参是"普通形参"，可以经用户定义转换匹配；隐式对象形参不行。不允许隐式对象形参做用户定义转换是 C++98 起的原则——否则 `x.f()` 可能会先把 `x` 转换成某个完全不相关的类型再调用其成员，名字查找与对象的对应关系就失去了意义。

### 恒等、无法形成、歧义（¶10–¶13）

¶10 若无需任何转换，ICS 是只含恒等转换的标准转换序列。

¶11 若找不到任何转换序列，ICS 无法形成（该候选不可行）。

¶12 若有**多个**良构的 ICS 能把实参转换到形参类型，与该形参关联的 ICS 定义为唯一的**歧义转换序列**（ambiguous conversion sequence）。在排序时，它被视为与任何其他用户定义转换序列都不分优劣的用户定义转换序列。若使用歧义转换序列的函数被选为最佳可行函数，调用非良构。

```cpp
class B;
class A { A(B&); };
class B { operator A(); };
class C { C(B&); };
void f(A) { }
void f(C) { }
B b;
void use() {
  f(b);           // error: 歧义——b→C（经构造函数）与 b→A（歧义转换：构造函数或转换函数）不分优劣
}
```

（`A(B&)` 是 `private` 的——但 ICS 不看访问性，它依然构成了 `b → A` 的一条路径。）

注 6 解释了设计意图：这条规则防止一个函数**仅仅因为**某个形参的转换序列有歧义就变得不可行。为什么？设想把歧义当作"无法转换"：`f(A)` 会不可行，于是 `f(b)` **无歧义地**选中 `f(C)`。但这个结论是脆弱的：只要 `A` 的作者删掉其中一条转换路径，`f(A)` 就"复活"并可能改变调用结果。把歧义当作一个"普通的用户定义转换"，可以让重载决议的结果对这类修改更稳定，并在真正选中它时报告歧义。

```cpp ok
class B;
class A { public: A(B&); };
class B { public: operator A(); };
class C { public: C(B&); };
void f(A);
void f(C);
void f(B);       // 新增
void use(B& b) {
  f(b);          // OK：f(B) 是恒等，胜过两个用户定义（含歧义）转换
}
```

¶13 三种形式在下面的子条款中定义。

## §2 标准转换序列 [over.ics.scs]

### 类别与等级（¶1–¶3）

¶1 表 19 总结了 [[conv]] 中定义的转换，把它们划分为四个互不相交的**类别**：左值变换（Lvalue Transformation）、限定调整（Qualification Adjustment）、提升（Promotion）、转换（Conversion）。注 1：这些类别在值类别、cv 限定、数据表示三个维度上正交——左值变换不改变 cv 与表示；限定调整不改变值类别与表示；提升与转换不改变值类别与 cv。

¶3 每个转换还有一个**等级**（rank）：精确匹配（Exact Match）、提升（Promotion）或转换（Conversion）。

| 转换 | 类别 | 等级 | 子条款 |
|---|---|---|---|
| 无需转换 | 恒等 | **Exact Match** | — |
| 左值到右值转换 | 左值变换 | **Exact Match** | [[conv.lval]] |
| 数组到指针转换 | 左值变换 | **Exact Match** | [[conv.array]] |
| 函数到指针转换 | 左值变换 | **Exact Match** | [[conv.func]] |
| 限定转换 | 限定调整 | **Exact Match** | [[conv.qual]] |
| 函数指针转换（去掉 `noexcept`） | 限定调整 | **Exact Match** | [[conv.fctptr]] |
| 整型提升 | 提升 | **Promotion** | [[conv.prom]] |
| 浮点提升（`float→double`） | 提升 | **Promotion** | [[conv.fpprom]] |
| 整型转换 | 转换 | **Conversion** | [[conv.integral]] |
| 浮点转换 | 转换 | **Conversion** | [[conv.double]] |
| 浮点-整型转换 | 转换 | **Conversion** | [[conv.fpint]] |
| 指针转换（含空指针转换、到 `void*`、派生到基类） | 转换 | **Conversion** | [[conv.ptr]] |
| 成员指针转换 | 转换 | **Conversion** | [[conv.mem]] |
| 布尔转换 | 转换 | **Conversion** | [[conv.bool]] |

（另外，§1 中的"派生到基类转换"——类类型的按值形参接受派生类实参——也是 Conversion 等级。）

¶2（注 2）：标准转换序列要么是单独的恒等转换，要么由其他四个类别中的**一到三个**转换组成，并按**规范顺序**排列：左值变换 → 提升或转换 → 限定调整。

¶3 **序列的等级**由序列中每个转换的等级以及**任何引用绑定的等级**决定：有 Conversion 则为 Conversion；否则有 Promotion 则为 Promotion；否则为 Exact Match。即"最差的那一环决定整条链"。

一些常被误判的等级：

```cpp
void f(int);   void f(long);    // short → int 是提升；short → long 是整型转换
void g(double); void g(long double);  // float → double 是提升；float → long double 是浮点转换
void h(int);   void h(unsigned);      // char → int 是提升；char → unsigned 是转换
void p(void*); void p(const int*);    // int* → const int* 是 Exact Match（限定调整）；int* → void* 是 Conversion
void q(int*);  void q(long);          // 0 → int* 是 Conversion（空指针转换）；0 → long 也是 Conversion
void use(short s, float fl, char c, int* ip) {
  f(s);     // f(int)
  g(fl);    // g(double)
  h(c);     // h(int)
  p(ip);    // p(const int*)
  q(0);     // error: 歧义——两者都是 Conversion 等级
}
```

`q(0)` 正是 `NULL` 时代的经典陷阱，也是 C++11 引入 `nullptr` 的动机之一：`nullptr` 的类型 `std::nullptr_t` 能转换到任何指针类型（空指针转换），但不能转换到 `long`，于是 `q(nullptr)` 无歧义地选中 `q(int*)`。

几个要点：

- **只有 `float → double` 是浮点提升**。`float → long double`、`double → long double` 都是浮点转换。
- **整型提升的目标只有 `int`、`unsigned int`**（以及对字符类型、无作用域枚举、位域的特殊规定，见 [[conv.prom]]）。`short → long`、`char → long`、`int → long` 都是整型转换。`bool → int` 是提升。
- **限定转换是 Exact Match**，所以 `int* → const int*` 与恒等同等级；它们靠 [[over.ics.rank#3.2.1]]（真子序列）分出高下。
- **函数指针转换**（`void(*)() noexcept → void(*)()`）自 C++17 起存在，也是 Exact Match（限定调整）。

### 序列的结构

```text
  左值变换            提升 / 转换            限定调整
  (lvalue→rvalue,    (integral promotion,  (qualification,
   array→pointer,     floating conversion,  function pointer
   function→pointer)  pointer conversion…)  conversion)
      ≤1                  ≤1                   ≤1
```

例如 `const char[4]`（字符串字面量）到 `const void*`：数组到指针（左值变换）→ 指针转换 `const char* → const void*`（转换），等级为 Conversion。`int[3]` 到 `const int*`：数组到指针 → 限定转换，等级为 Exact Match。

## §3 用户定义转换序列 [over.ics.user]

¶1 **用户定义转换序列**由三部分组成：

```text
  初始标准转换序列  →  用户定义转换（[class.conv]）  →  第二标准转换序列
```

- 若用户定义转换由**构造函数**指定（[[class.conv.ctor]]），初始 SCS 把源类型转换到该构造函数**第一形参**的类型；
- 若由**转换函数**指定，初始 SCS 把源类型转换到该转换函数**对象形参**的类型。

¶2 第二 SCS 把用户定义转换的结果转换到序列的目标类型；任何引用绑定都包含在第二 SCS 中。由于 ICS 是一种初始化，挑选最佳用户定义转换时适用"由用户定义转换进行初始化"的特殊规则（[[over.match.best#2.2]]、¶4 的二次转换禁令）。

```cpp run ok
#include <string>
void f(std::string);
int main() {
  f("hello");
  // 初始 SCS：const char[6] → const char*（数组到指针，Exact Match）
  // 用户定义转换：std::string(const char*)（构造函数）
  // 第二 SCS：恒等（结果就是 std::string prvalue）
}
void f(std::string) {}
```

¶3 若用户定义转换由**转换函数模板**的特化指定，第二 SCS 必须是 **Exact Match** 等级。

原因：转换函数模板 `template<class T> operator T()` 能"变成"任何类型；若允许在它之后再接一个提升或转换，它就会对几乎所有目标类型都可行，而且往往与其他候选形成大面积歧义。模板实参推导（[[temp.deduct.conv]]）通常会直接推出目标类型本身，使第二 SCS 为恒等；¶3 堵住了其余的情形。

¶4 把类类型的表达式转换到**同一个**类类型，给予 **Exact Match** 等级；转换到其**基类**，给予 **Conversion** 等级——尽管这两种情形实际上调用的是构造函数（即用户定义转换函数）。

这与 §1 ¶7 呼应：传值 `f(A)` 接受 `A` 实参时，概念上调用了拷贝构造函数，但 ICS 被视为标准转换，等级 Exact Match，**而不是**用户定义转换。否则，`f(A)` 对 `A` 实参会是"用户定义转换"，比 `f(const A&)`（恒等引用绑定）差一大截——那将是灾难性的。

## §4 省略号转换序列 [over.ics.ellipsis]

¶1 当实参与被调用函数的省略号形参规范匹配时（见 [[expr.call]]），就形成省略号转换序列。

它是三种形式中**最差**的。由于对省略号实参只做默认实参提升（[[expr.call]]），几乎任何实参都能"匹配"省略号——这使得 `f(...)` 成为一个"兜底"重载，这一技巧曾广泛用于 C++11 之前的 SFINAE 检测：

```cpp run ok
#include <type_traits>
template<class T> std::true_type  has_size_impl(decltype(&T::size));
template<class T> std::false_type has_size_impl(...);
struct A { int size(); };
struct B {};
static_assert(decltype(has_size_impl<A>(nullptr))::value);   // 第一个可行，nullptr→成员指针是 Conversion，优于省略号
static_assert(!decltype(has_size_impl<B>(nullptr))::value);  // 第一个推导失败，只剩省略号
int main() {}
```

注意：对类类型实参传给省略号，若该类类型有非平凡的拷贝/移动构造函数或析构函数，是**条件支持**的（[[expr.call]]）。但在不求值语境（如 `decltype`）中这不是问题。

## §5 引用绑定 [over.ics.ref]

### 直接绑定（¶1）

¶1 当"到 `cv T` 的引用"形参**直接绑定**（[[dcl.init.ref]]）到实参表达式时：

- ¶1.1 若实参类型 `D` 是 `T` 的派生类：ICS 是从 `D` 到 `T` 的**派生到基类转换**（Conversion 等级）；
- ¶1.2 否则，若实参类型是（可能 cv 限定的）`T`，或 `T` 是元素类型为 `U` 的**未知边界数组**而实参是元素类型为（可能 cv 限定的）`U` 的已知边界数组：ICS 是**恒等转换**；
- ¶1.3 否则，若 `T` 是函数类型：ICS 是**函数指针转换**（即实参是 `noexcept` 函数、形参是非 `noexcept` 函数引用）；
- ¶1.4 否则：ICS 是**限定转换**。

```cpp nocheck
#include <cstdio>
struct A {};
struct B : public A {} b;
int f(A&) { return 1; }
int f(B&) { return 2; }

void g() noexcept {}
int h(void (&)() noexcept) { return 1; }  // #1
int h(void (&)())          { return 2; }  // #2

int main() {
  std::printf("%d %d\n", f(b), h(g));     // 2 1：f(B&) 恒等胜过派生到基类；h #1 恒等胜过函数指针转换
}
```

!!! impl "Clang 的偏离"
    截至写作时，Clang 23 对 `h(g)` 报"call to 'h' is ambiguous"，没有把"函数指针转换"作为比恒等更差的 ICS 来区分 #1 与 #2。按标准（这正是 [over.ics.ref] 的例 1），应调用 #1。`f(b)` 部分与标准一致。

¶1.2 的要点：`const int&` 绑定到 `int` 左值是**恒等**（"可能 cv 限定的 `T`"指的是实参可以比形参少 cv）。cv 的差异不算转换——它通过 [[over.ics.rank#3.2.6]] 另行比较。

¶1.2 中"未知边界数组"那半句来自 C++20 的 [[P0388R4]]（允许 `int(&)[]` 绑定到 `int[3]`）。

¶1.4 的限定转换出现在"多级指针的 cv"之类场合：`const int* const&` 可以直接绑定到 `int*` 左值（两者是引用兼容的，[[dcl.init.ref]]），这时 ICS 是限定转换。

¶1 末句：若形参直接绑定到对实参应用**转换函数**的结果，ICS 是用户定义转换序列，其第二 SCS 按上面的规则确定。

### 非直接绑定（¶2）

¶2 引用形参不直接绑定时，ICS 就是按 [[over.best.ics]] 把实参转换到**被引用类型**所需的序列。概念上，它对应于用实参拷贝初始化一个被引用类型的临时对象。顶层 cv 的差异被初始化本身吸收，不构成转换。

```cpp
void f(const long&);
void use(int i) {
  f(i);    // 非直接绑定：int → long 的整型转换（Conversion），然后绑定到临时 long
}
```

### 左右值限制（¶3–¶4）

¶3 除隐式对象形参外（见 [[over.match.funcs#5]]），若要求把**非 const 左值引用**（准确地说：除"到非 volatile const 类型的引用"以外的左值引用）绑定到右值，或把**右值引用**绑定到**对象类型**的左值，ICS 无法形成。

注 1：这意味着有非 const 左值引用形参（隐式对象形参除外）的候选，若对应实参需要创建临时对象，就不可行。

两个细节：

- `const volatile int&` 也**不能**绑定到右值（只有"非 volatile 的 const"才行）。
- 右值引用**可以**绑定到**函数**左值（函数没有右值，`void(&&)()` 绑定 `g` 是允许的）——所以 ¶3 只说"对象类型的左值"。

```cpp
void f(const volatile int&);
void g(int&&);
void h(void(&&)());
void fn();
void use(int i) {
  f(1);    // error: const volatile 左值引用不能绑定到右值
  g(i);    // error: 右值引用不能绑定到对象类型的左值
  h(fn);   // OK：右值引用可以绑定到函数左值
}
```

¶4 其他**不基于引用和实参类型**的绑定限制，不影响 ICS 的形成。例 2：对"到 `int` 的左值引用"形参，`int` 位域实参也被当作 `int` 左值，得到精确匹配；若该函数被选中，调用仍因禁止把非 const 左值引用绑定到位域（[[dcl.init.ref]]）而非良构。

## §6 列表初始化序列 [over.ics.list]

¶1 实参是初始化列表（[[dcl.init.list]]）时，它**不是表达式**，有专门的转换规则。下面各条按顺序尝试，第一条适用的即为结果（"否则"）：

| 段落 | 形参类型 | 条件 | ICS |
|---|---|---|---|
| ¶2 | 非引用 | 列表是指派初始化列表 | 若形参是能由它聚合初始化的聚合：用户定义转换序列（第二 SCS 恒等）；否则不可能转换 |
| ¶3 | 聚合类 `X` | 单个元素，类型 `cv U`，`U` 是 `X` 或其派生类 | 把该元素转换到形参类型所需的序列 |
| ¶4 | 字符数组 | 单个元素，是适当类型的字符串字面量 | 恒等 |
| ¶5 | `std::initializer_list<X>` | 所有元素都能隐式转换为 `X` | 元素转换中**最差**的那个；空列表为恒等 |
| ¶6 | `X[N]` 或 `X[]` | 每个元素（以及 `N` 超出时的 `{}`）都能转换为 `X` | 其中最差的 |
| ¶7 | 非聚合类 `X` | [[over.match.list]] 选出唯一最佳构造函数 `C` | 单个同类元素且 `C` 非初始化列表构造函数：Exact Match/Conversion；否则用户定义转换序列；多个同样好：歧义转换序列 |
| ¶8 | 聚合 | 能按聚合初始化规则初始化 | 用户定义转换序列（第二 SCS 恒等） |
| ¶9 | 引用 | — | 见 §5（规则作用于底层临时对象） |
| ¶10 | 非类类型 | 一个非列表元素：该元素的转换；空列表：恒等 | |
| ¶11 | 其他 | — | 不可能转换 |

### 指派初始化列表（¶2）{{c++20}}

¶2 只能转换到能由它聚合初始化的聚合类型。注 1：聚合初始化不要求指派符按成员声明顺序出现——**可行性**不检查顺序；若选中的重载顺序不符，初始化非良构。

```cpp nocheck
struct A { int x, y; };
struct B { int y, x; };
void f(A a, int);               // #1
void f(B b, ...);               // #2
void g(A a);                    // #3
void g(B b);                    // #4
void h() {
  f({.x = 1, .y = 2}, 0);       // OK：#1（第二个实参匹配 int 优于匹配省略号）
  f({.y = 2, .x = 1}, 0);       // error: 选中 #1，但 A 的成员顺序是 x、y，指派顺序不符
  g({.x = 1, .y = 2});          // error: #3 与 #4 歧义——两者都能"不看顺序地"初始化
}
```

（Clang 23 对第二个调用只给出 `-Wreorder-init-list` 警告——它把乱序的指派初始化器作为扩展接受；按 C++20 标准这是非良构的。另两个调用与标准一致。）

为什么不让顺序影响可行性？设计上，指派初始化器只是"按名字聚合初始化"，重载决议里用名字匹配做分派会让规则非常复杂（还要考虑嵌套、基类……）；C++20 选择了最简单的方案：可行性只看"这些名字是否都是该聚合的成员"。

### 单元素的同类聚合（¶3）

```cpp run ok
struct Agg { int a; int b; };
struct D : Agg {};
int f(Agg) { return 1; }
int main() {
  Agg x{1, 2};
  D d{};
  return f({x}) + f({d}) == 2 ? 0 : 1;   // {x}：恒等；{d}：派生到基类
}
```

没有这一条，`{x}` 会被当作"用 `x` 初始化 `Agg` 的第一个成员 `a`"——`Agg → int` 不可能，转换失败。C++11 中确实如此，后来由一个缺陷报告加入这一条（并同步修改 [[dcl.init.list#3.2]]）。

### `initializer_list<X>`（¶5）

¶5 所有元素都能**隐式转换**为 `X` 时，ICS 是转换单个元素所需的**最差**转换；空列表为恒等。这里的转换**可以是用户定义转换**，即使在调用初始化列表构造函数的语境中。

```cpp
#include <initializer_list>
#include <string>
#include <complex>
void f(std::initializer_list<int>);
void use() {
  f({});              // OK：恒等
  f({1, 2, 3});       // OK：恒等
  f({'a', 'b'});      // OK：整型提升
  f({1.0});           // error: 窄化（ICS 存在——浮点-整型转换；选中后才检查窄化）
}

struct A {
  A(std::initializer_list<double>);                  // #1
  A(std::initializer_list<std::complex<double>>);    // #2
  A(std::initializer_list<std::string>);             // #3
};
A a{1.0, 2.0};               // OK：#1（恒等）优于 #2（用户定义转换）；#3 不可行
void g(A);
void use2() {
  g({"foo", "bar"});         // OK：#3
}
```

`f({1.0})` 再次说明**窄化不影响 ICS**：`double → int` 是浮点-整型转换，ICS 存在，`f` 可行并被选中；选中后按 [[dcl.init.list]] 检查到窄化，非良构。

### 数组（¶6）{{c++20}}

¶6 形参是"`N` 个 `X` 的数组"或"`X` 的未知边界数组"时（这只会出现在引用形参的被引用类型中——脚注 99：没有数组类型的形参），若每个元素（以及 `N` 超过元素个数时的 `{}`）都有到 `X` 的 ICS，结果是其中最差的。

```cpp
typedef int IA[3];
void h(const IA&);
void use() {
  h({1, 2, 3});     // OK：恒等
  h({1, 2});        // OK：第三个元素由 {} 初始化，{} → int 是恒等
}
```

到未知边界数组的转换与"元素更少者优先"的排序规则来自 C++20 的 [[P0388R4]]，详见 [[over.ics.rank#3.1]]。

### 非聚合类（¶7）

¶7 形参是非聚合类 `X`，且 [[over.match.list]] 为用初始化列表初始化 `X` 选出唯一最佳构造函数 `C`：

- ¶7.1 若 `C` **不是**初始化列表构造函数，且列表只有一个类型为 `cv U` 的元素（`U` 是 `X` 或其派生类）：`U` 是 `X` 时为 **Exact Match** 等级，是派生类时为 **Conversion** 等级。
- ¶7.2 否则：用户定义转换序列，第二 SCS 为恒等。

若有多个构造函数可行但没有一个更好，ICS 是歧义转换序列。除 ¶4（§1）所述的情况外，初始化列表元素到构造函数形参类型的转换**允许**用户定义转换。

```cpp
#include <initializer_list>
#include <string>
struct A { A(std::initializer_list<int>); };
void f(A);
struct B { B(int, double); };
void g(B);
void use() {
  f({'a', 'b'});        // OK：A(initializer_list<int>)，用户定义转换
  g({'a', 'b'});        // OK：B(int, double)，用户定义转换
  g({1.0, 1.0});        // error: 窄化
}
void f(B);
void use2() {
  f({'a', 'b'});        // error: f(A) 与 f(B) 歧义——两者都是用户定义转换，且转换函数不同
}
struct C { C(std::string); };
void h(C);
struct D { D(A, C); };
void i(D);
void use3() {
  h({"foo"});           // OK：C(std::string("foo"))——元素 "foo" → string 是用户定义转换，这是允许的
  i({{1, 2}, {"bar"}}); // OK：D(A({1,2}), C(std::string("bar")))
}
```

`h({"foo"})` 值得注意：列表 → `C` 是用户定义转换（构造函数 `C(std::string)`），而其中元素 `"foo"` → `std::string` 又是一次用户定义转换——"列表初始化中可以有多于一次用户定义转换"正是 [[over.match.funcs#6]] 所说的例外。

### 聚合（¶8）与引用（¶9）

¶8 形参是能由该列表聚合初始化的聚合类型时，ICS 是用户定义转换序列（第二 SCS 恒等）：

```cpp
struct A { int m1; double m2; };
void f(A);
void g(const A&);
void k(const double&);
void use() {
  f({'a', 'b'});     // OK：聚合初始化，用户定义转换
  f({1.0});          // error: 窄化
  g({'a', 'b'});     // OK：¶9——引用形参，对底层临时对象适用本节规则
  k({1});            // OK：与 int → double 相同的转换
}
```

### 非类类型（¶10）

¶10 形参不是类类型时：

- ¶10.1 列表只有一个**不是初始化列表**的元素：ICS 是把该元素转换到形参类型所需的序列；
- ¶10.2 列表为空：恒等。

```cpp
void f(int);
void use() {
  f({'a'});     // OK：与 char → int 相同的转换（提升）
  f({1.0});     // error: 窄化
  f({});        // OK：恒等（值初始化）
}
```

¶11 其余情况一律不可能转换——例如 `f({1, 2})` 对 `f(int)`，或 `f({{1}})` 对 `f(int)`（元素本身是列表）。

## 实现视角

!!! impl
    - Clang 用 `ImplicitConversionSequence` 表示 ICS，其 `Kind` 正是标准、用户定义、省略号、歧义、坏转换五种；标准转换序列 `StandardConversionSequence` 有 `First`（左值变换）、`Second`（提升/转换）、`Third`（限定调整）三个槽，与 [over.ics.scs] 的规范顺序完全对应，此外还记录 `ReferenceBinding`、`DirectBinding`、`BindsToRvalue` 等供 [[over.ics.rank]] 使用的位。
    - 列表初始化序列在 Clang 中有专门的 `StdInitializerListElement`、`isInitializerListOfIncompleteArray` 等标志，用于实现 [[over.ics.rank#3.1]]。
    - 许多"在 ICS 阶段刻意忽略、选定后才检查"的错误（窄化、位域、访问），在编译器里也确实是分两遍实现的：先算 ICS 并选择，再用正式的初始化代码（`InitializationSequence`）对选中的函数执行一次完整初始化，在那时报错。

## 历史与演进

!!! history
    - **C++98**：标准/用户定义/省略号三种形式、等级表、二次用户定义转换禁令、歧义转换序列。
    - **C++11**：列表初始化序列；右值引用的绑定限制。
    - **C++11 之后（缺陷报告）**：单元素同类聚合（¶3）、非聚合类的单元素同类列表的 Exact Match 等级（¶7.1）。
    - **C++17**：函数指针转换（`noexcept` 进入类型系统）作为限定调整，Exact Match 等级。
    - **C++20**：指派初始化列表（¶2）；到未知边界数组的转换（[[P0388R4]]）。
    - **C++23**：显式对象形参可以经用户定义转换匹配（¶9 注 5）。

## 陷阱

!!! pitfall "以为 `int → long` 是提升"
    整型提升只到 `int`/`unsigned int`。`int → long` 是整型转换，与 `int → double` 同为 Conversion 等级，所以 `f(long)`/`f(double)` 对 `f(1)` 歧义。

!!! pitfall "以为 `0` 优先匹配指针"
    `0 → T*` 是 Conversion 等级的空指针转换，与 `0 → long` 不分优劣。用 `nullptr`。

!!! pitfall "以为窄化会让重载不可行"
    窄化只在选定后报错。`f({1.5})` 对 `f(int)` 是非良构，而不是"不可行于是去选别的"——除非别的重载本身就更好（比如 `f(double)` 的恒等）。

!!! pitfall "以为按值传递同类对象是'用户定义转换'"
    `f(A)` 接受 `A` 实参的 ICS 是恒等（¶7、[over.ics.user]/4），哪怕实际要调用拷贝构造函数。

## 思考题

!!! question "1. `void f(const char*); void f(std::string);`，`f(“abc”)` 调用哪个？`void g(bool); void g(std::string);`，`g(“abc”)` 呢？"

<details markdown="1">
<summary>答案</summary>

`f("abc")`：`const char[4] → const char*` 是数组到指针（Exact Match）；`→ std::string` 是用户定义转换。标准转换序列胜，选 `f(const char*)`。

`g("abc")`：`const char[4] → bool` 是数组到指针 + 布尔转换，等级 Conversion，但它仍是**标准**转换序列；`→ std::string` 是用户定义转换序列。按 [[over.ics.rank#2.1]]，任何标准转换序列都优于用户定义转换序列，于是选 `g(bool)`——这是著名的反直觉结果。修补办法通常是加一个 `g(const char*)` 重载。详见 [[topics/overload-resolution-walkthrough]]。
</details>

!!! question "2. 为什么 [over.best.ics]/¶12 要把歧义转换序列当作'用户定义转换序列'参与排序，而不是当作'无法转换'？举一个两种处理会给出不同结果的例子。"

<details markdown="1">
<summary>答案</summary>

正文的 `A`/`B`/`C` 例子就是：若把 `b → A` 的歧义当作"无法转换"，`f(A)` 不可行，`f(b)` 会无歧义地选中 `f(C)`；按标准的处理，`f(A)` 可行且其 ICS 与 `f(C)` 的不分优劣，调用歧义。标准选择后者，是为了不让"恰好存在两条转换路径"这种偶然情况把一个函数从候选中静默剔除——那样的话，修改 `A` 或 `B`（增删一条转换路径）会悄悄改变 `f(b)` 的调用目标，而不是报错。
</details>

## 小结

!!! summary
    - ICS 是对"用实参拷贝初始化形参"的建模，只关心类型、cv、值类别。
    - 三种形式：标准（Exact Match / Promotion / Conversion）、用户定义（SCS + 构造函数或转换函数 + SCS）、省略号。
    - 标准转换序列最多三步，按"左值变换 → 提升/转换 → 限定调整"排列，等级取最差的一环（含引用绑定）。
    - 同类按值传递是恒等，派生到基类是 Conversion，尽管实际调用了构造函数。
    - 隐式对象形参与赋值左操作数只允许标准转换；显式对象形参可以用户定义转换。
    - 在作为"用户定义转换的一部分"而被调用的构造函数/转换函数上，不考虑第二次用户定义转换。
    - 多条转换路径 → 歧义转换序列（按用户定义转换排序，选中则非良构）。
    - 列表初始化序列有十条规则；窄化、指派顺序、explicit 都不影响可行性。
