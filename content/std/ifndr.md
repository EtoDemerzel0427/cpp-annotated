---
title: 非良构，不要求诊断（Annex G）
summary: 附录 G 汇总了核心语言中全部 45 条不要求诊断的规则：这类错误为什么编译器可以不报，每一条的例子，以及 Clang 23 的实际表现。
status: draft
covers: *
related: ub, intro.compliance, intro.defs, basic.def.odr, temp.res, module.unit
tags: IFNDR, 附录, ODR, 模板, 模块, 链接
updated: 2026-10-19
---

!!! tldr
    - IFNDR 指程序违反了规则，但标准不要求编译器报告。这样的程序没有任何行为保证，即使出问题的代码从未执行。
    - 标准放弃诊断要求有四类原因：需要同时看到多个翻译单元、判断本身不可判定、名字保留给实现、各实现的解析器历史上做法不同。
    - 链接器只能抓住一部分：强符号重复定义、缺失的定义。inline 函数、模板实例化这类可以重复出现的实体，链接器任选一份，不比较内容。
    - 不要求诊断不等于禁止诊断。编译器看得见问题时常常会报，模块也把一部分跨翻译单元的错误变成了必须诊断。
    - 模板占 45 条中的 14 条，主要原因是模板在定义处和实例化处看到的声明可能不同。

## 一个不会报错的错误

下面两个源文件各自编译都没有问题，链接也没有任何提示：

```cpp title="tu1.cpp"
inline int f(int x, int y = 2);
inline int f(int x = 1, int y);     // 累积后：f(1, 2)
inline int f(int x, int y) { return x * 10 + y; }
int from1() { return f(); }
```

```cpp title="tu2.cpp" ifndr
#include <cstdio>
inline int f(int x = 3, int y = 4); // 累积后：f(3, 4)，与 tu1 不同
inline int f(int x, int y) { return x * 10 + y; }
int from1();
int main() { std::printf("%d %d\n", from1(), f()); }
```

本机 Clang 23 运行结果是 `12 34`：两个翻译单元各用各的默认实参。标准要求 inline 函数在各处累积的默认实参相同（[[dcl.fct.default#4]]），这个程序违反了规则，但编译器一次只编译一个翻译单元（一个源文件连同它包含的头文件），没有机会发现两边不一致。

这类规则在条文中注明 no diagnostic is required。违反它们的程序叫做**非良构、不要求诊断**（ill-formed, no diagnostic required），简称 **IFNDR**（[[g:ifndr]]）。按 [[intro.compliance.general#2.2]]，标准对这样的程序没有任何要求：编译器可以报错，也可以不报，生成的程序做什么都符合标准。

IFNDR 的后果比 UB 范围更大。UB 只让执行到它的那次运行失去保证；IFNDR 是程序文本的性质，整个程序失去保证，与有问题的代码是否执行无关。

## 附录 G 收录什么（G.1）[ifndr.general]

¶1 附录 G 收录第 4 章 [intro] 到第 15 章 [cpp] 中用下面三种说法标出的规则：no diagnostic is required、no diagnostic required、a diagnostic is required only if。

第三种说法表示规则有时要求诊断。例如 ODR 要求 inline 函数在各翻译单元中的定义相同；只有当实体附属于命名模块、并且前一个定义在后一个定义处可达时，才要求诊断（[[basic.def.odr#16]]）。这时编译器能从导入的模块中看到前一个定义。

每个条目有一个 `ifndr:` 前缀的 stable name、指向正文的链接、一段摘要和不求穷尽的例子。附录是资料性的，判定以正文为准；正文在每条规则后面用 `([ifndr:…])` 标注对应的条目。核心语言的 UB 有一个同样形式的附录 F，见 [[ub]]。

45 个条目的分布：[lex] 1、[basic] 9、[expr] 1、[stmt] 1、[dcl] 9、[module] 4、[class] 2、[over] 1、[temp] 14、[cpp] 3。

## 为什么不要求诊断

把 45 条放在一起看，原因可以归成四类：

| 类别 | 原因 | 典型条目 |
|---|---|---|
| 需要全程序视野 | 违规只在把多个翻译单元放在一起时才存在。编译器一次只看一个翻译单元，链接器只看到符号，看不到源代码 | ODR 的各条；语言链接、`alignas`、`[[noreturn]]`、`[[indeterminate]]`、默认实参、契约说明符跨翻译单元不一致；显式特化或偏特化在别处不可见；实例化点含义不同 |
| 不可判定或代价过高 | 判断两个表达式是否对所有模板实参都相等，或一条要求是否对所有实参都替换失败，一般情况下无法判定 | `temp.over.link.equiv.not.equiv`、`expr.prim.req.always.sub.fail`、约束满足结果随位置变化 |
| 保留给实现的名字 | 标准库头文件自己就要用这些名字，编译器难以区分用户代码和实现代码 | 保留标识符、保留模块名、保留的字面量后缀 |
| 实现的历史分歧 | 要求诊断会迫使某些实现重写解析器或名字查找 | 类作用域中名字含义改变、语句歧义消解时绑定不同、宏展开产生 `defined` |

### 工具能抓住多少

链接器是最后一道防线，而且很弱。非 inline 实体的重复定义会被报告为 `duplicate symbol`，缺失的定义会被报告为 `Undefined symbols`。但 inline 函数、模板实例化、虚表这类允许在多个目标文件中重复出现的实体，以 COMDAT（链接时去重的段）形式发出，链接器从中任选一份，不比较内容。ODR 违规在这里完全没有提示。

优化等级会影响能否发现问题。如果调用一个未定义函数的代码被优化删掉，链接就会成功（见 [G.3.2](#basic.def.odr.minimum.one.def)）。一个 inline 函数在一个翻译单元里被内联、在另一个里没有，程序会同时用到两个版本。

GCC 在 LTO 时可以用 `-Wodr` 比较各翻译单元中的类型和虚表定义（据 GCC 文档，本机没有 GCC，未验证）。Clang 在模块场景下会做 ODR 检查，`clang++ --help` 中有 `-fskip-odr-check-in-gmf` 之类的开关。对传统的头文件加多个源文件的构建方式，Clang 没有对应的跨翻译单元检查。

下面各条目中的观察都来自本机 Clang 23.1.3（arm64 macOS，Apple ld）。

## 第 [lex] 章：词法约定 {#lex}

### G.2.1 使用保留标识符 {#lex.name.reserved}

`ifndr:lex.name.reserved` · 正文 [[lex.name#4]]

含双下划线的标识符，以及以下划线加大写字母开头的标识符，在任何地方都保留给实现；以下划线开头的标识符在全局命名空间中保留。标准库头文件里到处是 `__x`、`_Tp` 这样的名字，编译器很难判断一个名字出自用户还是出自实现，所以不要求诊断。

```cpp ifndr
int _z;            // IFNDR：全局作用域中以 _ 开头

int main() {
  int __x = 0;     // IFNDR：以 __ 开头
  int _Y = 0;      // IFNDR：_ 后跟大写字母
  int x__y = 0;    // IFNDR：包含 __
  return __x + _Y + x__y + _z;
}
```

默认没有任何诊断，`-Wall -Wextra -pedantic` 也没有。显式打开 `-Wreserved-identifier` 后四处都有警告，例如 `identifier '_z' is reserved because it starts with '_' at global scope`。详见 [[lex.name]]。

## 第 [basic] 章：基础 {#basic}

### G.3.1 同一实体的声明互相矛盾且彼此不可达 {#basic.link.consistent.types}

`ifndr:basic.link.consistent.types` · 正文 [[basic.link#11]]

声明同一实体的多个声明必须一致：都声明变量则类型相同，都声明函数则类型相同，模板的模板头等价。如果两个声明彼此可达（在同一翻译单元中，或者经由 import），编译器看得见，必须诊断；只有互不可达时才是 IFNDR。

附录的例子是两个模块接口：

```cpp title="M.cppm"
export module M;
void g();                       // #1
void h();                       // #2
template <typename T> int j;    // #3
```

```cpp title="N.cppm"
export module N;
int g();                        // 与 #1 类型不同
namespace h {}                  // 与 #2 种类不同
template <int X> int j;         // 与 #3 模板头不等价
```

```cpp title="user.cpp" ifndr
import M;
import N;   // 附录：三对声明互相矛盾，IFNDR
```

!!! lawyer "附录的例子并不成立"
    按 [[basic.link#8]]，不同翻译单元中的两个声明要声明同一实体，必须都有模块链接或外部链接，并且附属于同一个模块（¶8.3）。`M` 中的 `g` 附属于模块 `M`，`N` 中的 `g` 附属于模块 `N`，它们本来就是两个实体。要让例子成立，这些声明应附属于全局模块，例如写在两个头文件里，由两个互不包含的翻译单元分别包含。

### G.3.2 odr-use 了没有定义的函数或变量 {#basic.def.odr.minimum.one.def}

`ifndr:basic.def.odr.minimum.one.def` · 正文 [[basic.def.odr#12]]

程序中每个被 [[g:odr-use]] 的函数或变量（不算被丢弃语句中的使用）必须至少有一个定义。定义可能在任何翻译单元里，编译器无法诊断；链接器通常能发现，前提是调用真的出现在目标代码中。

```cpp ifndr
int f();   // 从未定义

int main(int argc, char**) {
  if (argc > 100 && argc < 50) f();   // 永远不会执行，但 f 被 odr-use 了
}
```

`-O0` 下链接失败（`Undefined symbols for architecture arm64`）；`-O2` 下条件被折叠，调用被删除，链接成功。同一个非良构程序，换一个优化等级结果就不同，这正是标准无法要求诊断的原因。

附录的例子是只看一个翻译单元就能发现的特例：函数的类型涉及没有链接的局部类，它不可能在别处定义。Clang 对此直接报错：

```cpp error
auto f() {
  struct A {};
  return A{};
}
decltype(f()) g();
auto x = g();   // error（Clang 选择诊断）：g 不可能在任何翻译单元中定义
```

诊断原文是 `function 'g' is used but not defined in this translation unit, and cannot be defined in any other translation unit because its type does not have linkage`。

### G.3.3 一处用注入声明定义，另一处用普通定义 {#basic.def.odr.injected.match}

`ifndr:basic.def.odr.injected.match` · 正文 [[basic.def.odr#15]]

C++26 的静态反射可以在常量求值中用 `std::meta::define_aggregate` 等函数生成一个类的定义，这叫**注入声明**（injected declaration，[[expr.const.reflect]]）。如果一个翻译单元用注入声明定义了某个类，其他翻译单元中的定义也必须是特征序列相同的注入声明。

```cpp title="tu1.cpp"
#include <meta>
struct S;
consteval { std::meta::define_aggregate(^^S, {}); }   // #1：注入的定义
```

```cpp title="tu2.cpp" ifndr
struct S {};   // IFNDR：这里是普通定义，而 #1 是注入声明
```

Clang 23 还不支持静态反射，这个例子没有经过编译。

### G.3.4 普通函数或变量在多个翻译单元中有定义 {#basic.def.odr.maximum.one.def}

`ifndr:basic.def.odr.maximum.one.def` · 正文 [[basic.def.odr#16.1]]

这是 ODR 的基本要求：非 inline、非模板的函数和变量，整个程序只能有一个定义。附属于命名模块、且前一个定义可达时，必须诊断。

```cpp title="a.cpp"
int x = 1;
int f() { return 1; }
```

```cpp title="b.cpp" ifndr
int x = 2;              // IFNDR：x 的第二个定义
int f() { return 2; }   // IFNDR：f 的第二个定义
int main() {}
```

这一条链接器能抓住：`duplicate symbol '_x'`、`duplicate symbol 'f()'`。之所以仍然定为 IFNDR，是为了覆盖链接器看不到的情形，例如两份定义都被内联、没有发出符号。附录的例子用两个模块分区各自定义 `f()`，两份定义互不可达，同样是 IFNDR。

### G.3.5 允许多处定义的实体，各处定义不一致 {#basic.def.odr.definition.matches}

`ifndr:basic.def.odr.definition.matches` · 正文 [[basic.def.odr#16.2]]

inline 函数和变量、类、模板可以在多个翻译单元中各有一份定义，但各份定义必须相同：记号序列相同，名字查找到相同的实体，lambda 产生相同的闭包类型，等等（[[basic.def.odr#16]] 之后的一长串要求）。

```cpp title="tu1.cpp"
inline void f() {}          // #1
inline void g() {}          // #2
inline void h() {[]{}();}   // #3
namespace { int i = 0; }
inline void j() {++i;}      // #4
```

```cpp title="tu2.cpp" ifndr
inline void f() {}          // OK：与 #1 相同
inline void g() {;}         // IFNDR：记号序列与 #2 不同
inline void h() {[]{}();}   // IFNDR：闭包类型与 #3 中的不同
namespace { int i = 0; }
inline void j() {++i; }     // IFNDR：i 是另一个翻译单元的无名命名空间中的实体
```

`h` 和 `j` 的两份定义逐字相同，仍然违反 ODR。非模板 inline 函数中的每个 lambda 表达式都产生一个独有的闭包类型；无名命名空间里的 `i` 在每个翻译单元中是不同的实体。

链接没有任何诊断，链接器从各个 COMDAT 中任选一份。[[intro.compliance]] 有一个实测例子：同一 inline 函数在两个翻译单元中返回不同的值，`-O0` 下结果取决于链接顺序，`-O2` 下两个版本出现在同一次运行中。

### G.3.6 首个枚举量同名的无名枚举不是同一类型 {#basic.def.odr.unnamed.enum.same.type}

`ifndr:basic.def.odr.unnamed.enum.same.type` · 正文 [[basic.def.odr#20]]

没有名字、也没有用于链接的 typedef 名的枚举，在不同翻译单元之间靠第一个枚举量的名字认定是不是同一个类型。如果程序某处同时可达两个这样的定义，它们必须是同一类型。

```cpp title="a.h"
enum { a };
```

```cpp title="b.h"
enum { a, b };
```

```cpp title="main.cpp" ifndr
import "a.h";
import "b.h";
auto n = decltype(a)::b;   // IFNDR：两个首枚举量都叫 a 的无名枚举同时可达，却不是同一类型
```

### G.3.7 在契约断言的谓词中调用 va_start {#basic.contract.vastart.contract.predicate}

`ifndr:basic.contract.vastart.contract.predicate` · 正文 [[basic.contract.general#3]]

C++26 契约断言的谓词可能被求值零次、一次或多次，取决于求值语义（[[basic.contract.eval]]）。在其中调用 `va_start` 这类改变函数状态的宏没有意义。

```cpp ifndr
#include <cstdarg>

void f(int n, ...) {
  va_list args;
  contract_assert((va_start(args, n), true));   // IFNDR
}
```

Clang 23 还不支持契约，这个例子没有经过编译。

### G.3.8 在违反处理函数不可替换的平台上替换它 {#basic.contract.handler.replacing.nonreplaceable}

`ifndr:basic.contract.handler.replacing.nonreplaceable` · 正文 [[basic.contract.handler#3]]

契约的违反处理函数 `::handle_contract_violation` 能否被程序替换，由实现定义。在不能替换的平台上，写一个可以充当替换品的声明是 IFNDR。同一份代码在一个平台上合法、在另一个平台上非良构，所以不要求诊断。

```cpp ifndr
#include <contracts>
void handle_contract_violation(const std::contracts::contract_violation& violation);
// 若处理函数不可替换：IFNDR
```

### G.3.9 类中的名字在类完成后含义改变 {#class.member.lookup.name.refers.diff.decl}

`ifndr:class.member.lookup.name.refers.diff.decl` · 正文 [[class.member.lookup#6]]

在类定义中某处使用名字 N 时查找到的声明，必须与在类的完整类上下文（[[g:complete-class-context]]，例如成员函数体）中查找 N 的结果相同。否则同一个名字在类的前半段和后半段含义不同。检查这一点需要在类结束时把每个用过的名字重新查找一遍，所以不要求诊断。

```cpp ifndr
struct foo {};

struct bar {
  foo* m_foo;
  foo* foo() { return m_foo; }   // IFNDR：返回类型中的 foo 是 ::foo，
                                 // 但在 bar 的完整作用域中 foo 是成员函数 bar::foo
};
```

```cpp ifndr
struct B { static int f(); };

struct D : public B {
  using B::f;
  int g(decltype(f()) x) { return 0; }   // IFNDR：此处 f() 是 B::f()，类型 int，
  static float f();                       // 而在 D 的完整作用域中 f() 选 D::f()，类型 float
};
```

Clang 对两个例子都不诊断。GCC 对第一种情况报 changes meaning 错误（据 GCC 的已知行为，本机未验证），两个实现都符合标准。

## 第 [expr] 章：表达式 {#expr}

### G.4.1 一条要求对任何模板实参都替换失败 {#expr.prim.req.always.sub.fail}

`ifndr:expr.prim.req.always.sub.fail` · 正文 [[expr.prim.req.general#5]]

*requires* 表达式中的一条要求，如果无论模板实参是什么都会替换失败，程序 IFNDR。这和模板定义中不存在任何有效特化的规则（[[temp.res.general]]）是同一个思路：编译器可以提前报错，也可以不报。

```cpp ifndr
template <typename T> concept C = requires {
  new int[-(int)sizeof(T)];   // IFNDR：数组长度永远为负
};
```

Clang 不诊断，`static_assert(!C<int>)` 能通过：对具体的实参，替换失败只是让这条要求不满足。

## 第 [stmt] 章：语句 {#stmt}

### G.5.1 歧义消解前后，模板实参中的名字绑定不同 {#stmt.ambig.bound.diff.parse}

`ifndr:stmt.ambig.bound.diff.parse` · 正文 [[stmt.ambig#3]]

一条语句既可能是表达式语句又可能是声明时，编译器先按纯语法试探解析，确定是声明后再正式解析（[[stmt.ambig]]）。如果正式解析时，模板实参中的某个名字绑定到了正在解析的这个声明，而试探解析时它绑定到别处，程序 IFNDR。

```cpp ifndr
template <int N> struct A { const static int a = 20; };
template <> struct A<100> { using a = char; };

const int x = 10;

int main() {
  using T = const int;
  T(x)
  (100), (y)(A<x>::a);   // IFNDR：试探解析时 A<x> 中的 x 是全局的 x（10），
                         // 正式解析时它是本行刚声明的局部 x（100）
}
```

Clang 接受这段代码，只给出变量未使用的警告。

## 第 [dcl] 章：声明 {#dcl}

### G.6.1 constinit 不在初始化声明上 {#dcl.constinit.specifier.not.reachable}

`ifndr:dcl.constinit.specifier.not.reachable` · 正文 [[dcl.constinit#1]]

`constinit` 只要出现在一个变量的任何声明上，就必须出现在它的**初始化声明**（带初始化器的那个声明）上。编译器只有在初始化声明处才能检查初始化是不是常量初始化；另一个翻译单元里带 `constinit` 的 `extern` 声明，初始化声明那边看不到。

```cpp title="tu1.cpp"
int x = 5;   // x 的初始化声明，没有 constinit
```

```cpp title="tu2.cpp" ifndr
#include <cstdio>
extern constinit int x;   // IFNDR：带 constinit 的声明在初始化声明处不可达
int main() { std::printf("%d\n", x); }
```

编译和链接都没有诊断，程序打印 `5`。

### G.6.2 一处声明为 inline，另一处没有 {#dcl.inline.missing.on.definition}

`ifndr:dcl.inline.missing.on.definition` · 正文 [[dcl.inline#4]]

一个有外部链接或模块链接的函数或变量，如果在某个定义域（[[g:definition-domain]]，大致相当于一个翻译单元）中声明为 inline，那么在它出现的每个定义域的末尾，都必须能看到一个 inline 声明。

```cpp title="tu1.cpp"
inline int f();
int g() { return f(); }
```

```cpp title="tu2.cpp" ifndr
#include <cstdio>
int f() { return 17; }   // IFNDR：这个翻译单元的末尾看不到 f 的 inline 声明
int g();
int main() { std::printf("%d\n", g()); }
```

tu1 得到一条警告 `inline function 'f' is not defined [-Wundefined-inline]`。链接成功并打印 `17`：tu1 需要一个 `f` 符号，tu2 恰好提供了一个普通的强符号。

### G.6.3 inline 函数在各处累积的默认实参不同 {#dcl.fct.default.inline.same.defaults}

`ifndr:dcl.fct.default.inline.same.defaults` · 正文 [[dcl.fct.default#4]]

这就是页首的例子。默认实参由调用方在调用处代入，各翻译单元的默认实参不一致时，函数本身无从得知，所以程序打印 `12 34`。

### G.6.4 不同翻译单元中的首次声明契约说明符不同 {#dcl.contract.func.mismatched.contract.specifiers}

`ifndr:dcl.contract.func.mismatched.contract.specifiers` · 正文 [[dcl.contract.func#4]]

同一翻译单元中的重声明必须与可达的首次声明有相同的 `pre`、`post`，这一点可以诊断。不同翻译单元中各自的首次声明之间也必须一致，除非附属于命名模块，否则编译器无法检查。

```cpp title="tu1.cpp"
int f(int x) pre(x >= 0);   // IFNDR：另一处的首次声明没有 pre
int g(int x) pre(x == 0);   // IFNDR：与另一处的 pre 不同
int h(int x) pre(x <= 0);   // OK
```

```cpp title="tu2.cpp" ifndr
int f(int x);
int g(int x) pre(x != 0);
int h(int y) pre(y <= 0);   // OK：形参名不同不影响等价
```

Clang 23 还不支持契约，这个例子没有经过编译。

### G.6.5 可替换函数的替换品不合规 {#dcl.fct.def.replace.bad.replacement}

`ifndr:dcl.fct.def.replace.bad.replacement` · 正文 [[dcl.fct.def.replace#1]]

`operator new`、`operator delete`、契约违反处理函数等**可替换函数**（[[g:replaceable-function]]）可以由程序提供自己的定义。替换品不能是 inline，必须附属于全局模块，具有 C++ 语言链接，返回类型正确；如果标准库头文件中有对应声明，替换品必须是它的合法重声明。替换发生在链接层面，编译单个文件时未必看得到标准库的声明。

```cpp ifndr
#include <new>
#include <contracts>

extern "C"   // IFNDR：语言链接错误
inline       // IFNDR：inline
int          // IFNDR：返回类型错误
handle_contract_violation(const std::contracts::contract_violation&) {}

void* operator new(decltype(sizeof(0))) noexcept;   // IFNDR：异常说明与 <new> 中的声明不一致
```

包含了 `<new>` 时，`operator new` 那一行是同一翻译单元中的非法重声明，Clang 能诊断：`exception specification in declaration does not match previous declaration`。没有包含 `<new>` 时无从比较。

### G.6.6 互不可达的声明给出不同的语言链接 {#dcl.link.mismatched.language.linkage}

`ifndr:dcl.link.mismatched.language.linkage` · 正文 [[dcl.link#6]]

```cpp title="tu1.cpp"
extern "C" { void f() {} }
```

```cpp title="tu2.cpp" ifndr
extern "C++" { void f(); }   // IFNDR：与 tu1 的语言链接不同
int main() { f(); }
```

链接失败：`Undefined symbols … "f()"`。C 语言链接的 `f` 导出为 `_f`，C++ 语言链接的 `f()` 经过名字修饰成了 `__Z1fv`，两者对不上。问题只是被名字修饰顺带暴露出来；如果 `f` 从未被调用，就没有任何诊断。

### G.6.7 不同翻译单元中的对齐说明符不一致 {#dcl.align.diff.translation.units}

`ifndr:dcl.align.diff.translation.units` · 正文 [[dcl.align#6]]

如果定义声明带对齐说明符（`alignas`），其他声明要么指定等价的对齐，要么不写；如果任何一个声明带对齐说明符，每个定义声明都必须指定等价的对齐。跨翻译单元时不要求诊断。

```cpp title="tu1.cpp"
struct S { int x; } s, *p = &s;
```

```cpp title="tu2.cpp" ifndr
struct alignas(16) S;   // IFNDR：S 的定义没有 alignas(16)
extern S* p;
int main() { return p != nullptr; }
```

编译、链接、运行都没有诊断。tu2 会假定 `*p` 按 16 字节对齐，可能据此生成要求对齐的访问指令。

### G.6.8 `[[indeterminate]]` 在不同翻译单元中不一致 {#dcl.attr.indet.mismatched.declarations}

`ifndr:dcl.attr.indet.mismatched.declarations` · 正文 [[dcl.attr.indet#2]]

C++26 的 `[[indeterminate]]` 写在形参上，决定的是调用方如何处理未初始化的实参，读到的是错误值还是不确定值（[[basic.indet]]）。所以各处的首次声明必须一致。

```cpp title="tu1.cpp"
int h(int x [[indeterminate]]);   // IFNDR：与另一处的首次声明不一致
```

```cpp title="tu2.cpp" ifndr
int h(int x);                     // IFNDR
```

Clang 23 还不认识这个属性（`unknown attribute 'indeterminate' ignored`）。

### G.6.9 `[[noreturn]]` 在不同翻译单元中不一致 {#dcl.attr.noreturn.trans.unit.mismatch}

`ifndr:dcl.attr.noreturn.trans.unit.mismatch` · 正文 [[dcl.attr.noreturn#1]]

同一翻译单元内，只要任何一个声明带 `[[noreturn]]`，首次声明就必须带，这可以诊断。跨翻译单元时不要求诊断。

```cpp title="tu1.cpp"
[[noreturn]] void f() { throw 0; }
```

```cpp title="tu2.cpp" ifndr
void f();   // IFNDR：没有 [[noreturn]]
int main() { try { f(); } catch (int) { return 0; } }
```

这个例子没有诊断，正常运行。反过来更危险：如果 tu2 的声明带 `[[noreturn]]` 而定义实际会返回，tu2 中调用之后的代码可能被当作不可达而删掉。

## 第 [module] 章：模块 {#module}

### G.7.1 保留的模块名 {#module.unit.reserved.identifiers}

`ifndr:module.unit.reserved.identifiers` · 正文 [[module.unit#1]]

以 `std` 后跟零个或多个数字开头的模块名，以及含保留标识符的模块名，都保留给实现，不能出现在模块声明中。标准库自己要提供 `std` 和 `std.compat` 模块。

```cpp ifndr
export module std0;   // IFNDR：std 后跟数字
```

Clang 对此有默认开启的警告：`'std0' is a reserved name for a module [-Wreserved-module-identifier]`。附录例子里还有 `module module;`，但 [[module.unit#1]] 中禁止 `module`、`import` 作为模块名组成部分的那一句是要求诊断的。

### G.7.2 命名模块不是恰好一个主模块接口单元 {#module.unit.named.module.no.partition}

`ifndr:module.unit.named.module.no.partition` · 正文 [[module.unit#2]]

一个命名模块必须恰好有一个不带分区名的接口单元，叫做**主模块接口单元**（primary module interface unit）。各模块单元分别编译，没有哪一步能看到全部单元，所以不要求诊断。

```cpp title="a1.cppm"
export module A;
```

```cpp title="a2.cppm" ifndr
export module A;   // IFNDR：模块 A 的第二个主模块接口单元
```

附录的例子是 `module A;` 后跟 `export import :Internals;`。其中的 `export` 出现在模块实现单元里，违反的是 [[module.interface]] 中要求诊断的规则，没有很好地演示本条。

### G.7.3 接口分区没有被主模块接口单元导出 {#module.unit.unexported.module.partition}

`ifndr:module.unit.unexported.module.partition` · 正文 [[module.unit#3]]

模块中作为接口单元的每个分区，都必须被主模块接口单元直接或间接导出。同一段还规定一个模块不能有两个同名分区，同样不要求诊断。

```cpp title="M.cppm"
export module M;
export import :A;
```

```cpp title="M-A.cppm"
export module M:A;   // OK：被 M 直接导出
export import :B;
```

```cpp title="M-B.cppm"
export module M:B;   // OK：被 M 间接导出
```

```cpp title="M-C.cppm" ifndr
export module M:C;   // IFNDR：没有被 M 直接或间接导出
```

用 `--precompile` 分别编译这四个单元，Clang 没有任何诊断。

### G.7.4 有私有模块片段的模块还有其他模块单元 {#module.private.frag.other.module.units}

`ifndr:module.private.frag.other.module.units` · 正文 [[module.private.frag#1]]

私有模块片段（`module :private;`）用于把接口和实现写在同一个文件里，片段之后的内容对导入方不可达。所以带私有模块片段的模块单元必须是该模块唯一的单元。

```cpp title="M.cppm"
export module M;
module :private;
```

```cpp title="M-A.cppm" ifndr
module M:A;   // IFNDR：M 已有私有模块片段，不能再有其他模块单元
```

## 第 [class] 章：类 {#class}

### G.8.1 构造函数直接或间接委托给自己 {#class.base.init.delegate.itself}

`ifndr:class.base.init.delegate.itself` · 正文 [[class.base.init#6]]

委托构造形成环，运行时就是无限递归。环可能经过多个定义在不同翻译单元中的构造函数，所以不要求诊断。

```cpp ifndr
struct C {
  C(int) {}                // #1：非委托构造函数
  C() : C(42) {}           // #2：委托给 #1
  C(char c) : C(42.0) {}   // #3：IFNDR，与 #4 构成环
  C(double d) : C('a') {}  // #4：IFNDR，与 #3 构成环
};
```

构造函数都在类内定义时，Clang 能看到整个环并报错：`constructor for 'C' creates a delegation cycle [-Wdelegating-ctor-cycles]`。这条警告默认就是错误级别。不要求诊断并不妨碍实现在看得见的时候诊断。

### G.8.2 非纯虚函数没有定义 {#class.virtual.pure.or.defined}

`ifndr:class.virtual.pure.or.defined` · 正文 [[class.virtual#12]]

类中声明的虚函数必须有定义，或者声明为纯虚，或者两者都有。虚函数即使从未被调用也算被 odr-use，因为虚表要引用它，而它的定义可能在任何翻译单元中。

```cpp ifndr
class A {
  virtual void f();   // 既没有定义，也不是纯虚
};

int main() {
  A a;   // IFNDR
}
```

链接失败，但报的是 `Undefined symbols … "vtable for A"`，而不是缺少 `A::f`。Itanium ABI 把虚表放在定义关键函数（第一个非 inline、非纯虚的虚函数，这里是 `f`）的那个翻译单元里发出；`f` 没有定义，虚表也就没有人发出。

## 第 [over] 章：重载 {#over}

### G.9.1 字面量运算符使用保留的后缀 {#over.literal.reserved}

`ifndr:over.literal.reserved` · 正文 [[over.literal#1]]

不以下划线开头的字面量后缀保留给标准库（[[usrlit.suffix]]），例如 `s`、`h`、`i`、`if`。另外，如果字面量运算符写成 `operator"" _Bq`（引号和后缀之间有空格，这种写法已弃用），`_Bq` 是一个独立的标识符，而下划线加大写字母开头的标识符是保留的。

```cpp ifndr
double operator"" _Bq(long double);   // IFNDR：_Bq 是保留标识符（这种写法也已弃用）
double operator""_Bq(long double);    // OK：没有空格时 _Bq 是 ud-suffix，不受标识符保留规则约束
```

第一行只得到弃用警告：`identifier '_Bq' preceded by whitespace in a literal operator declaration is deprecated`。附录的另一个例子 `float operator ""E(const char*);`，Clang 当作错误处理（`invalid suffix on literal; C++11 requires a space between literal and identifier`），并附带警告 `user-defined literal suffixes not starting with '_' are reserved`。

## 第 [temp] 章：模板 {#templates}

模板占了 14 条，接近全部条目的三分之一。原因有两个。模板在定义处和实例化处分两个阶段处理，两处看到的声明可能不同；同一个特化又可能在多个翻译单元中各实例化一次，标准要求它们一致，却无从检查。

### G.10.1 隐式实例化时看不到模板定义 {#temp.pre.reach.def}

`ifndr:temp.pre.reach.def` · 正文 [[temp.pre#10]]

函数模板、类模板的成员函数、变量模板、类模板的静态数据成员，如果在某个定义域中被隐式实例化，它的定义必须在该定义域末尾可达，除非这个特化在某处被显式实例化。这就是模板通常写在头文件里的标准依据。

```cpp title="a.h"
template <typename T>
void f();
```

```cpp title="a.cpp" ifndr
#include "a.h"
int main() {
  f<int>();   // IFNDR：隐式实例化 f<int>，但定义不可达，也没有显式实例化
}
```

链接失败：`Undefined symbols … "void f<int>()"`。如果另一个翻译单元恰好写了 `template void f<int>();`，程序就合法。合法与否取决于别的翻译单元，所以这里只能是 IFNDR。

### G.10.2 模板模板形参实例化时，本应选中的偏特化不可达 {#temp.arg.template.sat.constraints}

`ifndr:temp.arg.template.sat.constraints` · 正文 [[temp.arg.template#2]]

```cpp ifndr
template <class T> struct A { int x; };

template <template <class U> class V> struct C {
  V<int> y;
  V<int*> z;
};

C<A> c;   // 此处实例化 A<int*>，用的是主模板

template <class T> struct A<T*> { long x; };   // IFNDR：如果可达，A<int*> 本应选中它
```

Clang 不诊断。

### G.10.3 结果取决于两个功能等价的原子约束是否等价 {#temp.constr.atomic.equiv.but.not.equiv}

`ifndr:temp.constr.atomic.equiv.but.not.equiv` · 正文 [[temp.constr.atomic#2]]

比较两个约束谁更严格时（包含关系，见 [[topics/concepts]]），原子约束按写法是否相同来判定是否**等价**，而不看语义。`2 * N` 和 `N * 2` 对所有 `N` 结果相同，叫做**功能等价**（[[g:functionally-equivalent]]），但它们不等价。如果重载决议的结果取决于这两者是否被视为等价，程序 IFNDR，因为判断任意两个表达式是否功能等价是不可判定的。

```cpp ifndr
template <int N> concept Add1 = true;

template <unsigned N> void f2() requires Add1<2 * N>;
template <unsigned N> int  f2() requires Add1<N * 2> && true;

void h2() {
  f2<0>();   // IFNDR：选哪个取决于 Add1<2 * N> 与 Add1<N * 2> 是否等价
}
```

Clang 不诊断，选中了返回 `int` 的第二个重载（`static_assert(__is_same(decltype(f2<0>()), int))` 通过）。

### G.10.4 同一约束在不同位置的满足结果不同 {#temp.constr.atomic.sat.result.diff}

`ifndr:temp.constr.atomic.sat.result.diff` · 正文 [[temp.constr.atomic#3]]

同一个原子约束、同一组模板实参，在程序不同位置检查时结果必须相同。最常见的违反方式是用概念检测类型是否完整，而两次检查之间类型被补全了。

```cpp ifndr
template <class T>
concept Complete = sizeof(T) == sizeof(T);

struct A;
static_assert(!Complete<A>);   // #1：A 不完整，不满足
struct A {};
static_assert(Complete<A>);    // IFNDR：满足结果与 #1 不同
```

Clang 缓存了第一次的满足结果，于是第二个 `static_assert` 失败（`static assertion failed`）。它报了错，但理由不对，只是沿用了旧答案。允许实现这样缓存，正是标准把这种程序定为 IFNDR 的原因。

### G.10.5 规范化时的代入产生无效类型或表达式 {#temp.constr.normal.invalid}

`ifndr:temp.constr.normal.invalid` · 正文 [[temp.constr.normal#1]]

**规范化**（normalization，[[g:normalization]]）把概念的使用展开成原子约束，并把实参代入每个原子约束的参数映射。如果代入产生了无效的类型或表达式，即使那个原子约束永远不会被求值，程序也是 IFNDR。

```cpp ifndr
template <typename T> concept A = T::value || true;
template <typename U> concept B = A<U*>;   // OK：映射 T ↦ U*
template <typename V> concept C = B<V&>;   // IFNDR：映射会形成 V&*（指向引用的指针）
```

只定义这三个概念时 Clang 不诊断；一旦使用 `C<int>`，就报错 `'type name' declared as a pointer to a reference of type 'V &'`。

附录条目在正文中挂在 ¶1.5.3.1（折叠表达式中概念模板形参包的展开）上，而这个例子演示的是 ¶1.4.2 中措辞相同的另一句规则。两处都是不要求诊断。

### G.10.6 本应使用的偏特化在使用处不可达 {#temp.spec.partial.general.partial.reachable}

`ifndr:temp.spec.partial.general.partial.reachable` · 正文 [[temp.spec.partial.general#1]]

```cpp ifndr
template <typename T> class X {
public:
  void foo() {}
};

template class X<void*>;   // IFNDR：显式实例化时，下面的偏特化还不可达

template <typename T> class X<T*> {
public:
  void baz();
};
```

Clang 不诊断。

### G.10.7 结果取决于两个功能等价的构造是否等价 {#temp.over.link.equiv.not.equiv}

`ifndr:temp.over.link.equiv.not.equiv` · 正文 [[temp.over.link#7]]

这是 [G.10.3](#temp.constr.atomic.equiv.but.not.equiv) 的一般形式。两个函数模板声明是同一个模板还是两个重载，按模板头和签名中的表达式是否等价来判定。`I+10` 和 `I+1+2+3+4` 功能等价，但不等价。

```cpp ifndr
template <int I> struct A {};

// IFNDR：两者功能等价但不等价
template <int I> void f(A<I>, A<I+10>);
template <int I> void f(A<I>, A<I+1+2+3+4>);
```

Clang 把它们当作两个不同的模板，声明本身不诊断。给出定义并调用 `f<0>(A<0>{}, A<10>{})` 时，报 `call to 'f' is ambiguous`。

### G.10.8 模板看不到的默认实参会改变结果 {#temp.res.general.default.but.not.found}

`ifndr:temp.res.general.default.but.not.found` · 正文 [[temp.res.general#2]]

模板中不依赖模板形参的名字，在模板定义处查找（[[g:two-phase-lookup]]）。如果模板定义之后又有一个声明给某个函数加上了默认实参，它在实例化点可达，但模板的查找看不到它；如果考虑它会改变结果，程序 IFNDR。

```cpp ifndr
#include <cstdio>

void f(long) { std::puts("f(long)"); }        // #1
void f(int, int) { std::puts("f(int,int)"); } // #2
template <typename T> void g(T t) { f(t); }
void f(int, int = 0);                          // #3：给 #2 加上默认实参

void h() { g(0); }   // IFNDR：考虑 #3 会选 f(int, int = 0)，模板的查找却选了 #1
```

Clang 不诊断，调用打印 `f(long)`。

### G.10.9 同一特化在不同实例化点含义不同 {#temp.point.diff.pt.diff.meaning}

`ifndr:temp.point.diff.pt.diff.meaning` · 正文 [[temp.point#7]]

一个特化可以在多个翻译单元中各有一个实例化点（[[g:point-of-instantiation]]），函数模板在同一翻译单元中还可能有多个。如果不同实例化点下它的含义不同，程序 IFNDR。典型例子是检测类型是否完整的 trait：

```cpp title="a.h"
#include <type_traits>

template <typename T, typename = void>
struct is_complete : std::false_type {};

template <typename T>
struct is_complete<T, std::void_t<decltype(sizeof(T))>> : std::true_type {};
```

```cpp title="a.cpp"
#include "a.h"
struct X;
bool in_a() { return is_complete<X>::value; }   // 在这里 X 不完整：false
```

```cpp title="b.cpp" ifndr
#include "a.h"
#include <cstdio>
struct X {};
bool in_a();
int main() {
  // IFNDR：is_complete<X> 在两个翻译单元中选中了不同的特化
  std::printf("a: %d, b: %d\n", in_a(), (int)is_complete<X>::value);
}
```

没有任何诊断，程序打印 `a: 0, b: 1`：同一个类型 `is_complete<X>` 在同一个程序里有两个不同的定义。所以检测类型是否完整的 trait 无法正确实现。

### G.10.10 考虑所有翻译单元后，依赖调用的结果会不同 {#temp.dep.candidate.different.lookup.different}

`ifndr:temp.dep.candidate.different.lookup.different` · 正文 [[temp.dep.candidate#1]]

依赖于模板形参的调用通过实参依赖查找（ADL，[[g:argument-dependent-lookup]]）在模板定义上下文和实例化上下文中寻找候选函数。如果把所有翻译单元中相关命名空间里具有外部链接的函数都算上，调用会变成非良构或者找到更好的匹配，程序 IFNDR。

```cpp title="tu1.cpp"
namespace A {
  struct S {};
  void f(S&, long x, int y);   // #3
  void g(S&, int x);           // #4
}
```

```cpp title="tu2.cpp" ifndr
namespace A {
  struct S {};
  void f(S&, int x, long y);   // #5
  void g(S&, long x);          // #6
}
template <typename T>
void h(T& t) {
  f(t, 1, 1);   // h<A::S> 中选 #5；考虑所有声明会产生歧义
  g(t, 1);      // h<A::S> 中选 #6；考虑所有声明会选 #4
}
```

### G.10.11 有显式实例化声明，却没有显式实例化定义 {#temp.explicit.decl.implicit.inst}

`ifndr:temp.explicit.decl.implicit.inst` · 正文 [[temp.explicit#12]]

**显式实例化声明**（`extern template`）告诉编译器不要在这里实例化，别处会提供。如果实体被以需要隐式实例化的方式使用，而整个程序中并没有显式实例化定义，程序 IFNDR。

```cpp ifndr
#include <vector>
#include <cstdio>

extern template class std::vector<int>;   // 显式实例化声明

int main() {
  std::printf("%zu\n", std::vector<int>().size());   // IFNDR：整个程序没有显式实例化定义
}
```

链接成功并打印 `0`。显式实例化声明不阻止 inline 函数的实例化（[[temp.explicit]]），而 libc++ 的 `vector` 成员几乎都是 inline 的，所以没有产生未定义的符号。换成成员函数在类外非 inline 定义的类模板，就会得到链接错误。

### G.10.12 使用处看不到显式特化的声明 {#temp.expl.spec.unreachable.declaration}

`ifndr:temp.expl.spec.unreachable.declaration` · 正文 [[temp.expl.spec#7]]

显式特化的声明必须在每个会引发隐式实例化的使用处可达，在每个这样的翻译单元中都是如此。否则一个翻译单元用特化、另一个用主模板，同一个 `S<int>` 有两种布局。

```cpp title="a.h"
template <typename T> struct S {};
```

```cpp title="tu2.cpp"
#include "a.h"
template <> struct S<int> { int oops; };   // #1
```

```cpp title="tu3.cpp" ifndr
#include "a.h"
S<int> s;   // IFNDR：#1 不可达，但它本应被选中
```

### G.10.13 显式特化被使用却没有定义 {#temp.expl.spec.missing.definition}

`ifndr:temp.expl.spec.missing.definition` · 正文 [[temp.expl.spec#7]]

声明了显式特化却没有定义，而这个特化又以需要隐式实例化的方式被使用（或者它是虚成员函数），程序 IFNDR。声明了显式特化之后，主模板的定义不会再被用来生成这个特化。

```cpp ifndr
template <typename T> int f(T&&) { return 0; }
template <> int f<int>(int&&);   // 只声明

int j = f(1);   // IFNDR：odr-use f<int>，但它没有定义
```

链接失败（`Undefined symbols`）。

### G.10.14 不同声明的替换顺序不同 {#temp.deduct.general.diff.order}

`ifndr:temp.deduct.general.diff.order` · 正文 [[temp.deduct.general#7]]

模板实参推导中的替换按词法顺序进行，遇到使推导失败的条件就停止。同一函数模板的两个声明如果写法不同（例如一个用前置返回类型，一个用尾置返回类型），替换时触发实例化的顺序就可能不同：一种顺序下是替换失败（SFINAE，[[g:sfinae]]），另一种顺序下是硬错误。

```cpp ifndr
template <class T> struct A { using X = typename T::X; };

template <class T> typename T::X h(typename A<T>::X);           // #1
template <class T> auto h(typename A<T>::X) -> typename T::X;   // 重声明 #2
template <class T> void h(...) {}

void x() {
  h<int>(0);   // IFNDR：按 #1 替换，T::X 先失败，不实例化 A<int>；
               // 按 #2 替换，先实例化 A<int>，那是一个硬错误
}
```

Clang 按 #2 的顺序处理，报硬错误 `type 'int' cannot be used prior to '::' because it has no members`，出自 `A<int>` 的实例化。

## 第 [cpp] 章：预处理指令 {#cpp}

### G.11.1 #if 中由宏展开产生 defined {#cpp.cond.defined.after.macro}

`ifndr:cpp.cond.defined.after.macro` · 正文 [[cpp.cond#9]]

`defined` 应该在宏展开之前识别。如果它是宏展开的产物，各个预处理器的历史行为不同（GCC 与 MSVC 就不一样），标准选择不作规定。

```cpp ifndr
#define X
#define D defined(X)
#if D        // IFNDR：defined 由宏替换产生
#endif
```

Clang 给出警告 `macro expansion producing 'defined' has undefined behavior [-Wexpansion-to-defined]`。警告文字沿用了 C 标准的说法（C 中这是 UB），C++ 现在把它定为 IFNDR。附录的例子是 `#define A defined` 后接 `#if A`，`defined` 后面什么也没有，Clang 直接报错 `macro name missing`。

### G.11.2 defined 的写法不完整 {#cpp.cond.defined.malformed}

`ifndr:cpp.cond.defined.malformed` · 正文 [[cpp.cond#9]]

`defined` 只有两种合法形式：`defined X` 和 `defined ( X )`，以宏替换之前的记号为准。

```cpp ifndr
#define A
#define B A)
#if defined ( B   // IFNDR：替换前 defined ( B 缺少右括号
#endif
```

Clang 报错 `missing ')' after 'defined'`。

### G.11.3 #include 宏替换后拼不成头文件名 {#cpp.include.malformed.headername}

`ifndr:cpp.include.malformed.headername` · 正文 [[cpp.include#7]]

`#include` 后面如果既不是 `<...>` 也不是 `"..."`，就先做宏替换，替换结果必须能拼成这两种形式之一，空白怎么处理由实现定义。拼不成则 IFNDR。

```cpp ifndr
#include “   // IFNDR：中文全角引号，不是两种合法形式之一
```

Clang 报错 `expected "FILENAME" or <FILENAME>`。

## 常见误解

!!! pitfall "能编译、能链接、能运行，所以程序没问题"
    IFNDR 程序的典型表现恰恰如此。[G.3.5](#basic.def.odr.definition.matches)、[G.6.3](#dcl.fct.default.inline.same.defaults)、[G.10.9](#temp.point.diff.pt.diff.meaning) 的例子都顺利编译、链接、运行，同一个程序里却同时存在同一个东西的两个版本。

!!! pitfall "IFNDR 就是编译器懒得报的非良构"
    后果完全不同。必须诊断的非良构程序至少会得到一条诊断；IFNDR 程序可以得到一个可执行文件，而标准对这个可执行文件的任何行为都没有要求，包括与违规代码无关的部分。

!!! pitfall "附录里的问题编译器都不会报"
    编译器看得见时常常会报：委托构造的环（[G.8.1](#class.base.init.delegate.itself)）、保留的模块名（[G.7.1](#module.unit.reserved.identifiers)）、预处理器的几条（G.11）。

!!! pitfall "每个翻译单元自己没问题就行"
    45 条中一大半涉及多个翻译单元。现实中 ODR 违规最常见的来源，是构建系统让不同的翻译单元使用不同的宏定义或编译选项，例如影响结构体布局或 inline 函数体的 `-D` 开关。

## 思考题

!!! question "思考题 1"
    为什么 inline 函数定义必须相同这条要求在头文件模型下是 IFNDR，而在模块中某些情况下必须诊断？提示：对比 [[basic.def.odr#16]] 中 a diagnostic is required only if 后面的条件。

<details markdown="1">
<summary>答案</summary>

[[basic.def.odr#16]] 只在实体附属于命名模块、且前一个定义在后一个定义处可达时要求诊断。这正是编译器能同时看到两份定义的情形：导入模块时，编译器读取被导入模块的 BMI（模块接口的编译产物），其中有前一个定义。头文件模型下，各翻译单元的编译互相独立，没有哪一步能同时看到两份定义，标准只能放弃诊断要求。模块的一个好处，就是把一部分 IFNDR 变成了必须诊断的错误。
</details>

!!! question "思考题 2"
    [G.10.4](#temp.constr.atomic.sat.result.diff) 中，Clang 让第二个 `static_assert` 失败了。`Complete<A>` 在 `A` 补全之后明明应该满足，这是否违反标准？

<details markdown="1">
<summary>答案</summary>

不违反。按 [[temp.constr.atomic#3]]，同一原子约束、同一组实参在程序不同位置的满足结果不同，程序 IFNDR，标准对实现没有任何要求，报错、不报错、给出任何结果都符合标准。Clang 缓存满足结果，是为了让约束检查的开销可控；标准把这种程序定为 IFNDR，正是为了允许这种缓存。
</details>

## 小结

| 问题 | 答案 |
|---|---|
| IFNDR 的后果 | 程序非良构，实现不受任何约束（[[intro.compliance.general#2.2]]），不需要执行到违规代码 |
| 附录 G 的地位 | 资料性，45 条，收录 no diagnostic (is) required 和 a diagnostic is required only if |
| 不要求诊断的原因 | 需要全程序视野、不可判定、保留名、实现的历史分歧 |
| 链接器能发现什么 | 强符号重复定义；缺失的定义（取决于优化）；语言链接不一致（取决于是否被调用） |
| 链接器发现不了什么 | inline 函数、模板、虚表等实体的定义不一致；默认实参不一致；实例化点含义不同 |
| 模块带来的改变 | 部分跨翻译单元的 IFNDR 在前一个定义可达时变为必须诊断 |
