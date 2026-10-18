---
title: 程序与链接
summary: 程序由翻译单元组成；名字有外部、模块、内部或无链接；哪些规则决定链接；两个声明何时声明同一实体、它们必须如何一致；以及 C++20 模块带来的 TU-local 实体与暴露（exposure）规则。
status: done
papers: P1103R3, P1815R2, P1787R6
related: basic.pre, basic.def.odr, basic.scope, dcl.link, dcl.typedef, module.unit, module.interface, module.reach, lex.phases
tags: 链接, 模块, TU-local, 翻译单元
updated: 2026-10-17
---

本节回答一个看似简单的问题：两个 TU 里都写了 `f`，它们是同一个东西吗？

答案取决于名字的**链接**（linkage）。链接是 C++ 从 C 继承的概念，本义是链接器能否把这个名字与别的 TU 中的同名名字连接起来。C++20 模块把它扩展成四种，并加上了一套关于 **TU-local** 实体的规则，防止模块接口把只属于本 TU 的东西泄漏给导入者。

[[basic.pre#10]] 说，同一名字在不同 TU 中是否指代同一实体取决于链接，本节给出完整的规则。[[basic.def.odr]] 要求整个程序中只有一个定义，这一要求要有意义，前提就是本节定义的"同一实体"。

阅读前需要了解 [[basic.scope]]（目标作用域、对应）与 [[basic.pre]]（实体、名字）。涉及模块的部分需要 [[module.unit]] 的基本概念：具名模块、模块单元、附属（attached）、全局模块。

## 程序与翻译单元（¶1）

¶1 **程序**由一个或多个翻译单元（[[lex.phases]]）组成，它们分别翻译后链接在一起。翻译单元由声明序列组成：

```text
translation-unit:
    declaration-seq(opt)
    global-module-fragment(opt) module-declaration declaration-seq(opt) private-module-fragment(opt)
```

第二种形式是**模块单元**（`module;` … `export module M;` … `module :private;` …）。

## 四种链接（¶2）

¶2 名字具有以下之一：

| 链接 | 含义 | 典型例子 |
|---|---|---|
| **外部链接**（external linkage） | 可以被其他 TU（包括其他模块的 TU）中的同名声明指代 | 普通全局函数、全局变量、导出的模块实体 |
| **模块链接**（module linkage）{{c++20}} | 只能被同一模块的其他 TU 指代 | 具名模块中未导出的命名空间作用域实体 |
| **内部链接**（internal linkage） | 只能在本 TU 中被（不同作用域的声明）指代 | `static` 函数/变量、命名空间作用域的 `const` 变量、无名命名空间的成员 |
| **无链接**（no linkage） | 只能被同一作用域中的声明指代 | 局部变量、局部类、函数形参 |

注 1：具有内部链接的实体，其所有声明都出现在同一个 TU 中；具有模块链接的实体，其所有声明都附属于同一个模块。

!!! note "链接属于名字，还是属于实体？"
    标准的措辞是名字具有链接。我们常说的实体的链接，指的是声明它的名字的链接。无名实体（如无名类、lambda 闭包类型）没有名字，也就没有链接，除非通过 typedef 等方式获得用于链接的名字（¶4.3–¶4.5）。

## 内部链接（¶3）

¶3 属于命名空间作用域的实体，其名字在以下情况具有**内部链接**：

- **¶3.1** 变量、变量模板、函数或函数模板显式声明为 `static`；或
- **¶3.2** 非模板变量具有非 volatile 的 const 限定类型，除非：
    - **¶3.2.1** 它声明在模块接口单元（私有片段之外）或模块分区的管辖范围（purview）中；或
    - **¶3.2.2** 它显式声明为 `extern`；或
    - **¶3.2.3** 它是 `inline` 的；或
    - **¶3.2.4** 它之前被声明过，且之前的声明不具有内部链接；或
- **¶3.3** 匿名联合体的数据成员。

注 2：具有 const 限定类型的变量模板实例化，即使没有声明为 `extern`，也可以有外部链接或模块链接。

### 为什么 `const` 变量默认是内部链接

这是 C++ 与 C 之间一个广为人知的差异（在 C 中，`const int x = 1;` 具有外部链接）。C++ 的设计意图是让 `const` 常量取代宏：

```cpp title="limits.h"
const int kMaxUsers = 1000;   // 内部链接：每个包含此头文件的 TU 一个独立的对象
```

如果 `const` 变量具有外部链接，这一行出现在多个 TU 中，就成了同一个变量的多个定义，违反 ODR（[[basic.def.odr#16]]）。内部链接让每个 TU 各有一份，互不相干；而且由于 `kMaxUsers` 可用于常量表达式，只读取值时不构成 odr-use，优化后通常根本不占存储。

几条例外各有道理：

- `extern`（¶3.2.2）：程序员明确要求外部链接，`extern const int x = 1;` 是定义外部链接常量的标准写法。
- `inline`（¶3.2.3）：`inline const`/`inline constexpr` 变量本来就是可以在多个 TU 中定义的同一个变量（C++17），必须具有外部链接才有意义。
- 之前声明过（¶3.2.4）：`extern const int z;` 之后的 `const int z = 5;` 是前者的定义，链接随首次声明。
- 模块接口（¶3.2.1）：模块接口单元只编译一次，不存在被多个 TU 包含的问题。如果其中的 `const` 变量仍是内部链接，就无法 `export`，接口中引用它的 inline 函数也会构成对 TU-local 实体的暴露（¶14）。所以在模块接口中，`const` 不再自动意味着内部链接。
- 模板（条文限定为非模板变量）：变量模板 `template<class T> const T zero = T();` 不受 ¶3.2 影响，因为它的特化需要在各 TU 之间是同一个实体。

```cpp run ok
const int c1 = 1;                 // 内部链接（¶3.2）
extern const int c2 = 2;          // 外部链接（¶3.2.2）
inline const int c3 = 3;          // 外部链接（¶3.2.3）
const volatile int c4 = 4;        // 外部链接：volatile 不满足 ¶3.2
constexpr int c5 = 5;             // 内部链接：constexpr 隐含 const
const int* p1 = &c1;              // 外部链接：p1 本身不是 const（指向 const 的指针）
const int* const p2 = &c1;        // 内部链接：p2 本身是 const
extern const int z;
const int z = 5;                  // 外部链接（¶3.2.4）
static int s = 1;                 // 内部链接（¶3.1）
extern int s;                     // 重声明，仍是内部链接（见 ¶4 与 [dcl.stc]）
int main() { return c1+c2+c3+c4+c5+*p1+*p2+z+s - 23; }
```

初学者常在 `const int* p1` 上出错：`const` 修饰的是所指向的对象，`p1` 本身不是 const 限定类型，所以具有外部链接，放在头文件里就会重复定义。

## 命名空间与其他名字的链接（¶4）

¶4 无名命名空间，以及直接或间接声明在无名命名空间中的命名空间，具有内部链接；其他所有命名空间具有外部链接。

对于属于命名空间作用域、上面没有赋予内部链接、并且是以下之一的名字：

- **¶4.1** 变量；
- **¶4.2** 函数；
- **¶4.3** 具名类，或在 typedef 声明中定义、以该 typedef 名作为**用于链接的 typedef 名**的无名类（[[dcl.typedef]]）；
- **¶4.4** 具名枚举，或类似地有用于链接的 typedef 名的无名枚举；
- **¶4.5** 以某个枚举项作为用于链接的名字的无名枚举（[[dcl.enum]]）；
- **¶4.6** 模板；

其链接按以下顺序确定：

- **¶4.7** 若该实体是首次在友元声明中声明的函数或函数模板，该声明是定义，且外围类定义在 *export-declaration* 中，则其名字具有与外围类名字相同的链接（如果有）；
- **¶4.8** 否则，若该实体是在友元声明中声明的函数或函数模板，且一个对应的非友元声明可达，则链接由那个先前的声明确定；
- **¶4.9** 否则，若外围命名空间具有内部链接，名字具有内部链接；
- **¶4.10** 否则，若名字的声明附属于具名模块且未导出，名字具有模块链接；
- **¶4.11** 否则，名字具有外部链接。

无名命名空间里的一切都具有内部链接，根据就是 ¶4.9：无名命名空间本身具有内部链接，于是其中的变量、函数、类、模板都具有内部链接。要让某个东西只属于本 TU，无名命名空间是比 `static` 更通用的工具，因为 `static` 不能用于类型，无名命名空间可以。

```cpp run ok
namespace { int u = 0; struct Hidden { int z; }; }    // u、Hidden 都是内部链接（¶4.9）
namespace outer { namespace { namespace deep { int dv = 0; } } }  // deep 间接在无名命名空间中 → 内部链接
int main() { Hidden h{}; return u + outer::deep::dv + h.z; }
```

¶4.3 中用于链接的 typedef 名，处理的是 C 风格的 `typedef struct { ... } Point;`。无名类本来没有名字，也没有链接，无法在多个 TU 中认定为同一个类型；typedef 给了它一个用于链接的名字，于是它能像具名类一样在头文件中定义。从 C++20 起，为了让这个机制简单可靠，[[dcl.typedef]] 限制这种无名类只能是与 C 兼容的，不能有成员函数、基类、默认成员初始化器、lambda：

```cpp
typedef struct { int a; } P;                 // OK：P 是用于链接的 typedef 名
typedef struct { int b; void f() {} } Q;     // 非良构：有成员函数（Clang 只给出警告）
enum { red, green } e;                       // 无名枚举：以 red 作为用于链接的名字（¶4.5）
```

¶4.7–¶4.8 处理隐藏友元的链接：对于类内定义的友元函数，若类被导出，友元也随类获得外部链接，否则在模块中会得到模块链接。

## 类成员的链接（¶5）

¶5 此外，成员函数、静态数据成员、栖居于类作用域的具名类或枚举，以及在栖居于类作用域的 typedef 声明中定义、有用于链接的 typedef 名的无名类或枚举，其链接与所属类的名字的链接相同（如果有）。

所以，外部链接类的成员具有外部链接；无名命名空间中的类，其成员都具有内部链接；**局部类没有链接，其成员也没有链接**。局部类的成员函数无法在类外定义、局部类不能有静态数据成员（[[class.local]]），原因就在这里。

## 块作用域的 extern 声明（¶6）

¶6 例 1（加注）：

```cpp run ok
static void f();
extern "C" void h();
static int i = 0;               // #1
void q() {
  extern void f();              // 内部链接：重声明了上面的 static f
  extern void g();              // ::g，外部链接
  extern void h();              // C 语言链接
  int i;                        // #2：i 无链接，隐藏了 #1
  {
    extern void f();            // 内部链接
    extern int i;               // #3：内部链接！
  }
}
int main() { }
```

关键在 #3。#2 隐藏了 #1，在 #3 处按名字查找只能找到 #2（一个无链接的局部变量）。但 #3 是块作用域的 `extern` 声明，它的目标作用域是外围命名空间（[[basic.scope.scope#2]] 的 ¶2.10），与 #1 对应，目标作用域也相同；按 ¶8，它们声明同一个实体，于是 #3 重声明了 #1，获得内部链接。名字查找找不到 #1 并不影响同一实体的判定，因为 ¶8 依据的是对应关系和目标作用域，而不是查找。

## 无链接（¶7）

¶7 上述规则未涵盖的名字没有链接。此外，除非另有说明，在块作用域中声明的名字没有链接。

无链接的名字包括：局部变量（包括 `static` 局部变量）、函数形参、局部类、局部枚举、typedef 名、模板形参、枚举项（不在 ¶4 的列表中，跨 TU 时依靠所属的枚举类型来认定）、命名空间作用域中没有用于链接的名字的无名类……

注意，**`static` 局部变量没有链接**，尽管它有静态存储期。存储期与链接是两个互不相关的概念：

| | 静态存储期 | 自动存储期 |
|---|---|---|
| 外部链接 | 全局变量 | — |
| 内部链接 | `static` 全局变量、`const` 全局变量 | — |
| 无链接 | `static` 局部变量 | 普通局部变量 |

## 两个声明何时声明同一实体（¶8）

¶8 两个实体的声明在以下条件下声明**同一实体**（把无名类型的声明视为引入其用于链接的名字，如果有）：

- 它们对应（[[basic.scope.scope#4]]），
- 具有相同的目标作用域，且该作用域不是函数形参作用域或模板形参作用域，
- 两者都不是名字无关声明（`_`），

并且满足以下之一：

- **¶8.1** 它们出现在同一个 TU 中；或
- **¶8.2** 它们都声明类型别名或命名空间别名，且底层实体相同；或
- **¶8.3** 它们都声明具有模块链接或外部链接的名字，并附属于同一个模块。

注 3：在其他一些情况下，声明也声明同一实体（[[dcl.link]] 中跨命名空间的 `extern "C"`、[[temp.type]]、[[temp.spec.partial]]）。

这一条是同一实体这个概念的定义。有几点值得注意：

- 在同一 TU 内，只要对应、目标作用域相同，就是同一实体，与链接无关。所以 `static int s; extern int s;` 是同一个 `s`；局部的 `void f() { extern int x; }` 与全局的 `int x;` 是同一个 `x`。
- 跨 TU 时，需要外部链接或模块链接，并且附属于同一模块。内部链接的名字永远不会跨 TU；附属于不同模块的同名实体是不同的实体（这是模块所有权的基础）。
- 函数形参作用域、模板形参作用域被排除在外：`void f(int x); void f(int x);` 中的两个 `x` 不是同一实体，它们分属两个函数声明各自的形参作用域。

```cpp title="a.cpp"
int counter = 0;              // 外部链接，全局模块
static int hits = 0;          // 内部链接
namespace { int misses = 0; } // 内部链接
void bump() { ++counter; ++hits; ++misses; }
```

```cpp title="b.cpp"
extern int counter;           // 与 a.cpp 的 counter 是同一实体（¶8.3：外部链接、都附属于全局模块）
static int hits = 0;          // 与 a.cpp 的 hits 是不同实体（内部链接）——合法，各有一份
namespace { int misses = 0; } // 同上
void bump();
int main() { bump(); return counter - 1 + hits + misses; }  // counter == 1, hits == 0, misses == 0
```

## 内部链接声明不能跨 TU 冲突（¶9）

¶9 如果一个声明内部链接名字的声明 H 先于（precedes）另一个 TU U 中的声明 D，并且 H 若出现在 U 中就会与 D 声明同一实体，则程序非良构。注 4：这样的 H 只能出现在**头单元**（header unit）中。

背景是这样的：`import "header.h";` 导入的头单元是一个独立的 TU，但它的声明先于导入者中的代码。如果头单元里有 `static int helper();`，导入者又声明了 `int helper();`，在文本包含的方式下，二者是同一实体而链接冲突，属于错误；在头单元的方式下，它们分属不同 TU，本可以相安无事。¶9 把这种情况也判为非良构，使 `#include` 与 `import` 的行为保持一致。

## 附属与模块（¶10）

¶10 注 5：如果两个声明对应但附属于不同的模块，并且一个先于另一个，程序非良构（[[basic.scope.scope#6]] 的潜在冲突）。

例 2（判定已用本机 Clang 23 验证）：

```cpp title="decls.h"
int f();            // #1，附属于全局模块
int g();            // #2，附属于全局模块
```

```cpp title="M.cppm（模块 M 的接口）"
module;
#include "decls.h"
export module M;
export using ::f;   // OK：不声明实体，导出 #1
int g();            // error: 与 #2 对应，但附属于 M
export int h();     // #3
export int k();     // #4
```

```cpp title="other.cpp"
import M;
static int h();     // error: 与 #3 冲突
int k();            // error: 与 #4 冲突
```

由这些规则可知，一个实体的所有声明都附属于同一个模块，称该实体**附属于**（attached to）那个模块。

`int g();` 一行说明了模块的强所有权：在 `export module M;` 之后的声明附属于 M，即使它与全局模块中的某个声明完全相同，也是另一个实体（¶8.3 要求附属于同一模块）；而二者对应且一个先于另一个，于是发生冲突。想在模块里引用全局模块的 `g`，应该像 `f` 那样使用 using 声明。

!!! impl "模块链接在符号层面的样子"
    Clang 采用强所有权模型：附属于具名模块的实体，其修饰名中编码了模块名。本机实验如下：

    ```cpp
    export module M;
    const int k = 1;            // 模块接口中：不再自动 internal（¶3.2.1），具有模块链接
    int hidden() { return 2; }  // 模块链接
    export int api() { return hidden() + k; }   // 外部链接
    ```

    `nm` 显示的符号是 `__ZW1M1k`、`__ZW1M6hiddenv`、`__ZW1M3apiv`，连导出的 `api` 也带有 `W1M` 模块标记。这样，两个不同模块中的同名实体在链接层面也不会冲突，与 ¶8.3 的语义一致。（MSVC 的实现细节不同，这里不展开。）

## 同一实体的声明必须一致（¶11）

¶11 对实体 E 的任意两个声明：

| ¶ | 若一个声明 E 为…… | 则另一个必须…… |
|---|---|---|
| 11.1 | 变量或函数 | 声明为相同类型的变量或函数 |
| 11.2 | 枚举项 | 也是枚举项 |
| 11.3 | 命名空间 | 也是命名空间 |
| 11.4 | 类型 | 同一种类的类型（[[dcl.type.elab]]：class/struct 可互换，union、enum 不行） |
| 11.5 | 类模板 | 同种类、模板头等价（注 6：默认模板实参可以不同） |
| 11.6 | 函数模板、变量模板（或其偏特化） | 模板头与类型等价 |
| 11.7 | 别名模板 | 模板头与 *defining-type-id* 等价 |
| 11.8 | 概念 | 也是概念 |

类型在经过所有调整之后比较（类型别名替换为它们代表的类型）；数组对象的声明可以在是否给出主数组边界上不同（`extern int a[]; int a[10];`）。**如果两个声明彼此都不可达，不要求诊断**（{{ifndr}}）。

这条规则的跨 TU 部分，是一类常见的无声错误的来源：

```cpp title="a.cpp"
int config = 42;                 // 定义为 int
```

```cpp title="b.cpp"
extern double config;            // 声明为 double：同一实体（外部链接、全局模块），类型不同
double read() { return config; } // IFNDR：链接器只按名字（C++ 中变量名不编码类型）匹配，读出垃圾
```

C++ 函数的修饰名编码了形参类型，所以链接器把 `void f(int)` 与 `void f(double)` 当成不同的符号（结果是链接失败，而不是无声的错误）；但变量名和函数的返回类型通常不编码（在 Itanium ABI 中，普通函数的返回类型不进入修饰名），因此不同 TU 中的 `int g();` 与 `long g();` 可以链接成功，并产生未定义行为。

在同一 TU 内则一定能诊断。例 3：

```cpp error
int f(int x, int x);    // error: 两个 x 是不同实体（函数形参作用域被 ¶8 排除，它们潜在冲突）
void g();               // #1
void g(int);            // OK：与 #1 不对应，是不同实体（重载）
int g();                // error: 与 #1 对应 → 同一实体，但类型不同
void h();               // #2
namespace h {}          // error: 与 #2 同一实体，但不是函数
```

## 语言链接（¶12）

¶12 注 7：与非 C++ 声明的链接可以通过 *linkage-specification*（`extern "C"`）实现，见 [[dcl.link]]。语言链接（language linkage）与本节所说的链接是两个不同的维度：前者决定调用约定与名字修饰方式，后者决定能否跨 TU 指代。

## 声明命名实体（¶13）

¶13 在以下情况下，称声明 D **命名**（names）实体 E：

- **¶13.1** D 包含一个闭包类型为 E 的 *lambda-expression*；
- **¶13.2** D 包含一个分别表示或指称 E 的 *reflect-expression* 或 *splice-specifier* {{c++26}}；
- **¶13.3** D 是一个注入声明，其特征序列包含表示数据成员描述 (T, N, A, W, NUA, ANN) 的反射，且 T 是 E {{c++26}}；
- **¶13.4** E 不是函数或函数模板，且 D 包含指代 E 的 *id-expression*、*type-specifier*、*nested-name-specifier*、*template-name* 或 *concept-name*；
- **¶13.5** E 是函数或函数模板，且 D 包含一个命名 E 的表达式（[[basic.def.odr#4]]），或一个指代包含 E 的重载集的 *id-expression*。

注 8：实例化声明中的非依赖名不指代重载集（[[temp.res]]）。

这一条是为下面的暴露规则做准备：判断一个声明是否把 TU-local 实体泄漏出去，就是看它是否命名了这样的实体。¶13.5 中"指代包含 E 的重载集"意味着，即使重载决议最终没有选中某个内部链接的重载，只要它在重载集里，声明就命名了它，¶19 中的 `h(N::A{})` 就是这样的例子。

## 暴露与 TU-local 实体（¶14–¶16）{{c++20}}

### 问题的由来

在只有头文件的时候，头文件里的 inline 函数调用一个 `static` 函数，每个 TU 各有一份 `static` 函数，这样也能勉强工作（尽管严格说违反了 ODR，因为 inline 函数中的名字在不同 TU 中指代不同实体，见 [[basic.def.odr#16]]）。有了模块之后，模块接口只编译一次，导入者看到的是接口中 inline 函数的定义；如果它调用了接口里的 `static` 函数，导入者的 TU 里根本没有那个函数，既无法内联，也无法链接。

C++20 的解决方案（P1815，"Translation-unit-local entities"）是定义 **TU-local 实体**，并禁止模块接口中的非 TU-local 声明暴露它们。

### 暴露（¶14）

¶14 如果一个声明命名了一个 TU-local 实体（定义见下文），它就是一个**暴露**（exposure），但以下部分不计：

- **¶14.1** 非 inline 函数或函数模板的函数体（但对于声明返回类型使用占位符的函数，推导出的返回类型仍然计入）；
- **¶14.2** 变量或变量模板的初始化器（但变量的类型仍然计入）；
- **¶14.3** 类定义中的友元声明；
- **¶14.4** 对内部链接或无链接的、用常量表达式初始化的非 volatile const 对象或引用的、不构成 odr-use 的引用；

此外，定义一个初始化为 **TU-local 值**的 constexpr 变量，也是暴露。

这些例外准确地对应了导入者需要看到的内容：

- 非 inline 函数的函数体只在本 TU 编译，导入者只需要声明，所以函数体里可以随意使用 TU-local 实体。
- 导入者需要 inline 函数的函数体（为了内联和 ODR 合并），所以不能忽略它。
- 对于 `auto` 返回类型的函数，导入者需要知道推导出的类型，所以推导出的类型不能是 TU-local 的。
- 只读取值的常量（¶14.4），其值会直接代入，不需要实体本身，与 [[basic.def.odr#16]] 中 ¶16.5.1 的例外同理。

注 9：即使 inline 函数模板的某些显式特化可以在其他 TU 中使用，它本身仍可以是暴露。

### TU-local 实体（¶15）

¶15 满足以下条件之一的实体是 **TU-local** 的：

- **¶15.1** 类型、类型别名、命名空间、命名空间别名、函数、变量或模板，并且
    - **¶15.1.1** 其名字具有内部链接；或
    - **¶15.1.2** 没有具有链接的名字，并且在 TU-local 实体的定义之内被声明，或由其中的 *lambda-expression* 引入；
- **¶15.2** 在 *class-specifier*、函数体或初始化器之外定义的无名类型，或者由只用于声明 TU-local 实体的 *defining-type-specifier* 引入的无名类型；
- **¶15.3** TU-local 模板的特化；
- **¶15.4** 有任一 TU-local 模板实参的模板特化；
- **¶15.5** 其（可能实例化的）声明是暴露的模板特化。

注 10：特化可以由隐式实例化或显式实例化产生。

¶15.2 的意思是：命名空间作用域中 `static auto x = []{};` 的闭包类型，或 `static struct { } s;` 的无名类，只用于声明 TU-local 实体，所以本身也是 TU-local 的；而在函数体或类内部定义的无名类型，则跟随其外围实体。

### TU-local 值（¶16）

¶16 满足以下条件之一的值或对象是 **TU-local** 的：

- **¶16.1** 它是 TU-local 类型的；
- **¶16.2** 它是（或是指向）TU-local 函数，或与 TU-local 变量关联的对象；
- **¶16.3** 它是类或数组类型的对象，且其任一子对象、或其引用类型非静态数据成员所引用的任一对象或函数，是 TU-local 的且可用于常量表达式；
- **¶16.4** 它是一个反射值 {{c++26}}，表示：TU-local 的实体/值/对象；注解（[[dcl.attr.annotation]]）；D 或 B 为 TU-local 的直接基类关系 (D, B)；T 为 TU-local 的数据成员描述。

值也有 TU-local 之分，是因为导入者会使用 constexpr 变量的值（常量折叠、模板实参）。一个指向 `static` 函数的 constexpr 函数指针，其值就是那个函数的地址，导入者无法使用。¶16.4 把这个推理扩展到反射值：`constexpr auto r = ^^f;`（`f` 是 `static` 函数）的值表示一个 TU-local 实体，所以 `r` 不能出现在模块接口的非 TU-local 声明中。

## 违反的后果（¶17–¶18）

¶17 在模块接口单元（私有片段之外）或模块分区中，如果非 TU-local 实体的（可能是实例化产生的）声明或推导指引是一个暴露，程序非良构。在其他上下文中，这样的声明已弃用（[[depr.local]]）。

后半句很重要：在普通的非模块代码中，头文件里 inline 函数调用 `static` 函数的写法依然合法，只是已弃用。标准借此表明，这种写法在概念上是错误的。

¶18 如果一个 TU 中的声明命名了在另一个非头单元的 TU 中声明的 TU-local 实体，程序非良构。为模板特化实例化的声明，视为出现在特化的实例化点（[[temp.point]]）。

¶17 规定接口不能暴露 TU-local 实体，¶18 规定导入者不能使用它们。二者配合，覆盖了模板实例化这类在导入者的 TU 中、用接口里的定义产生的声明。

## 综合例子（¶19）

¶19 下面是标准中的大例子，逐行加注。TU #1 是模块 A 的接口：

```cpp title="TU #1：export module A;"
export module A;
static void f() {}
inline void it() { f(); }           // error: inline 函数体不被忽略 → 命名了 TU-local 的 f → 暴露
static inline void its() { f(); }   // OK：its 自己是 TU-local 的，¶17 只管非 TU-local 实体
template<int> void g() { its(); }   // OK：非 inline 函数模板的函数体被忽略（¶14.1）——但见 TU #2 中的 g<1>
template void g<0>();               // 显式实例化：g<0> 在本 TU 实例化

decltype(f) *fp;                    // error: 变量的类型不被忽略；decltype(f) 命名了 f（虽然 f 的类型 void() 本身不是 TU-local）
auto &fr = f;                       // OK：初始化器被忽略（¶14.2），fr 的类型是 void(&)()
constexpr auto &fr2 = fr;           // error: 定义 constexpr 变量，其值（引用 f）是 TU-local 值
constexpr static auto fp2 = fr;     // OK：fp2 是内部链接的，本身就是 TU-local

struct S { void (&ref)(); } s{f};               // OK：s 不是 constexpr，值是 TU-local 也无妨
constexpr extern struct W { S &s; } wrap{s};    // OK：wrap 的值引用 s，s 不是 TU-local；
                                                //   s.ref 引用 f，但 s 不可用于常量表达式，¶16.3 不适用

static auto x = []{f();};           // OK：x 是 TU-local（内部链接），lambda 闭包类型也是
auto x2 = x;                        // error: x2 的类型是 TU-local 的闭包类型
int y = ([]{f();}(),0);             // error: 这个闭包类型不是 TU-local 的（它出现在非 TU-local 变量 y 的初始化器中，
                                    //   ¶15.2 不适用），而它的定义（operator() 是 inline 的）命名了 f
int y2 = (x,0);                     // OK：初始化器被忽略

namespace N {
  struct A {};
  void adl(A);
  static void adl(int);
}
void adl(double);

inline void h(auto x) { adl(x); }   // OK：但某些特化是暴露（取决于 ADL 找到什么）

constexpr std::meta::info r1 = ^^g<0>;  // OK
namespace N2 {
  static constexpr std::meta::info r2 = ^^g<1>;     // OK：r2 是 TU-local
}
constexpr std::meta::info r3 = ^^f;                 // error: r3 的值是表示 TU-local 实体 f 的反射 → 暴露

constexpr auto ctx = std::meta::access_context::current();
constexpr std::meta::info r4 =
  std::meta::members_of(^^N2, ctx)[0];              // error: r4 的值表示 TU-local 的 N2::r2
```

TU #2 是模块 A 的实现单元：

```cpp title="TU #2：module A;"
module A;
void other() {
  g<0>();                           // OK：g<0> 已在 TU #1 显式实例化
  g<1>();                           // error: g<1> 在这里实例化，其定义调用 its——命名了另一个 TU 的 TU-local 实体（¶18）
  h(N::A{});                        // error: h<N::A> 的实例化中 adl(x) 的重载集（经 ADL）包含 TU-local 的 N::adl(int)
  h(0);                             // OK：实参为 int，ADL 不进入 N，只找到 ::adl(double)
  adl(N::A{});                      // OK：N::adl(int) 是另一个 TU 中内部链接的声明，这里的查找找不到它，选 N::adl(N::A)
  fr();                             // OK：调用 f（通过非 TU-local 的引用 fr）
  constexpr auto ptr = fr;          // error: fr 在这里不可用于常量表达式
}
```

有几点值得仔细体会：

- 对比 `it` 与 `its`：两者调用的是同一个函数。`it` 是外部（模块）链接的 inline 函数，导入者需要它的函数体，因此构成暴露；`its` 是 `static inline`，它本身就是 TU-local 的，不对外承诺任何东西。
- 通过 `fr` 间接使用 `f`：`auto &fr = f;` 合法（初始化器不计），在其他 TU 中通过 `fr` 调用 `f` 也合法，因为运行时通过引用间接调用不需要知道 `f` 的名字。但在别的 TU 中不能对 `fr` 做常量求值：`fr` 的初始化器是 TU-local 值，[[expr.const.init]] 规定这种变量在其他 TU 中不可用于常量表达式。
- 对比 `y` 与 `y2`：`y` 的初始化器里的 lambda 闭包类型不是 TU-local 的（它不只用于声明 TU-local 实体），而闭包的 `operator()` 是 inline 的，并且调用了 `f`，于是闭包类型的定义构成暴露；`y2` 的初始化器只用了已有的 `x`，不计入。

!!! impl "Clang 的实现状况"
    本机 Clang 23 对上面 TU #1 中的部分行给出 `-WTU-local-entity-exposure` 警告（例如 `it` 和 `auto x2 = x;`），而不是错误；`decltype(f) *fp;`、`fr2`、`y` 等行没有诊断。标准要求这些都是非良构的（需要诊断），所以截至写作时，Clang 的实现并不完整。

## 实现视角

!!! impl "链接在目标文件中的映射"
    在本机 Clang 23（Mach-O）上用 `nm` 观察的结果：

    | 声明 | 符号 | 说明 |
    |---|---|---|
    | `int use();` 的定义 | `T __Z3usev` | 大写 = 全局可见（外部链接） |
    | `static int s1 = 1;` | `d __ZL2s1` | 小写 = 局部符号；Itanium ABI 用 `L` 前缀标记内部链接 |
    | 无名命名空间中的 `hidden()` | `t __ZN12_GLOBAL__N_16hiddenEv` | `_GLOBAL__N_1` 是无名命名空间的修饰；局部符号 |
    | `extern const int z; const int z = 5;` | `S _z` | 外部链接常量（变量名在 C++ 中不加修饰时与 C 相同） |
    | `namespace { struct In { static int sm; }; }` 的成员 | `b __ZN12_GLOBAL__N_12In2smE` | ¶5：成员随类，内部链接 |
    | 模块 M 中未导出的 `hidden()` | `T __ZW1M6hiddenv` | 模块链接：全局可见，但修饰名含模块名 |

    还有一个有意思的现象：在命名空间作用域定义一个类型为无名命名空间中的类的变量（如 `Hidden h;`），按 ¶4，`h` 的名字仍具有外部链接；但 Clang 把它发射为局部符号，因为其他 TU 不可能写出它的类型，也就不可能合法地声明它。编译器在这里做的是一个程序无法观察到的优化。

## 历史与演进

!!! history "C++98 → C++26"
    - **C++98/03**：有外部链接、内部链接、无链接三种。命名空间作用域的 `static`（用于对象）在 C++03 中被弃用，推荐改用无名命名空间；无名命名空间的成员当时具有外部链接（只是名字唯一，别的 TU 写不出来）。
    - **C++11**：撤销对命名空间作用域 `static` 的弃用；无名命名空间及其成员改为内部链接；允许把局部类型和无名类型用作模板实参。
    - **C++17**：引入 inline 变量，`inline const` 变量具有外部链接（¶3.2.3）。
    - **C++20**：模块（P1103 合并的模块 TS）带来了模块链接、附属（attachment），模块接口中的 `const` 不再默认具有内部链接；P1815 引入 TU-local 实体与暴露；C++20 还限制了具有用于链接的 typedef 名的无名类的内容。
    - **C++23**：P1787R6 用对应关系加目标作用域重写了同一实体的判定（¶8）。
    - **C++26**：加入与反射相关的命名规则（¶13.2–¶13.3）与 TU-local 值（¶16.4）；名字无关声明被排除在同一实体之外。

## 陷阱

!!! pitfall "`const int*` 不是 const 变量"
    `const int* p = ...;` 在命名空间作用域具有外部链接，放在头文件里会导致重复定义。要内部链接，就写 `const int* const p`；要全程序只有一个，就写 `inline const int* p`。

!!! pitfall "`static` 局部变量有链接吗？"
    没有。静态存储期不等于内部链接。inline 函数中的 `static` 局部变量在全程序中只有一个，这是 ODR（[[basic.def.odr#18]]）的保证，而不是链接的效果。

!!! pitfall "跨 TU 的类型不一致不会报错"
    `int x;` 与另一个 TU 中的 `extern long x;` 是同一实体，但类型不同。这是 IFNDR，链接器不会发现。应始终让声明来自同一个头文件。

!!! pitfall "头文件中 inline 函数调用 static 函数"
    在非模块代码中，这种写法已弃用（¶17），而且严格说违反 ODR（inline 函数中的名字在各 TU 中指代不同实体，也不满足 [[basic.def.odr#16]] 中 ¶16.5.1 的例外）。应把 helper 也改为 inline，或放进 `detail` 命名空间并声明为 inline。

## 思考题

!!! question "思考题 1"
    下面各名字的链接是什么？

    ```cpp
    namespace { namespace X { int a; } }
    struct S { static int b; };
    const int c = 1;
    constexpr const char* d = "hi";
    void f() { static int e; struct L { void m(); }; }
    template<class T> const T g = T();
    ```

<details markdown="1">
<summary>答案</summary>

- `X`、`X::a`：内部链接（X 在无名命名空间中，¶4；a 由 ¶4.9 获得内部链接）。
- `S`、`S::b`：外部链接（¶4.3、¶5）。
- `c`：内部链接（¶3.2）。
- `d`：`constexpr const char*` 的类型是 `const char* const`，`constexpr` 使指针本身成为 const，于是 ¶3.2 适用，具有内部链接。
- `e`：无链接（块作用域，¶7）。
- `L`、`L::m`：无链接（局部类，¶7；按 ¶5，成员随类）。
- `g`：这是变量模板，¶3.2 只针对非模板变量，所以按 ¶4.6/¶4.11 具有外部链接（注 2：其 const 实例化也可以具有外部链接）。
</details>

!!! question "思考题 2"
    为什么 `static int s; void f() { int s; { extern int s; } }` 中最内层的 `extern int s;` 指的是全局的 `s`，而不是新声明一个外部链接的 `s`？

<details markdown="1">
<summary>答案</summary>

块作用域的 `extern` 声明以外围命名空间为目标作用域（[[basic.scope.scope#2]]）。它与命名空间作用域的 `static int s;` 对应（同名，都是变量），目标作用域相同，又在同一 TU 中，¶8.1 直接判定它们声明同一实体，于是它获得内部链接。中间的局部 `int s;` 只是在名字查找层面隐藏了全局 `s`，不影响同一实体的判定（这正是 ¶6 例 1 中的 #3）。
</details>

## 小结

| 主题 | 要点 |
|---|---|
| 四种链接 | 外部（跨 TU、跨模块）、模块（同模块）、内部（本 TU）、无（本作用域） |
| 内部链接 | 显式 `static`；非模板、非 volatile 的 const 变量（除非 extern/inline/模块接口/先前非内部声明）；匿名联合体成员；无名命名空间中的一切 |
| 模块链接 | 附属于具名模块且未导出 |
| 类成员 | 随类 |
| 同一实体 | 对应 + 同目标作用域（非形参/模板形参作用域）+（同 TU，或同底层实体的别名，或外部/模块链接且附属于同一模块） |
| 一致性 | 同一实体的声明类型必须相同；彼此不可达时 IFNDR |
| [[g:tu-local]] | 内部链接实体、其中定义的无链接实体、只用于 TU-local 的无名类型、相关的特化与值 |
| [[g:exposure|暴露]] | 命名 TU-local 实体的声明（忽略非 inline 函数体、初始化器、友元、只读常量）；模块接口中非良构，其他地方弃用 |
