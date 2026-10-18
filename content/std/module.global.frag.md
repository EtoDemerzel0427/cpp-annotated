---
title: 全局模块片段
summary: module; 之后、模块声明之前的全局模块片段——让模块单元能 #include 传统头文件；decl-reachable 关系的精确定义，以及哪些全局模块片段中的声明会被"丢弃"、丢弃意味着什么。
status: done
since: c++20
papers: P1103R3
related: module.unit, module.import, module.reach, module.context, basic.lookup.argdep, cpp.pre, basic.def.odr, temp.dep
tags: 模块, 全局模块片段, 可达性
updated: 2026-10-17
---

模块不可能凭空出现在一个没有模块的生态里。绝大多数库仍以头文件形式发布（包括 C 库、操作系统 API、第三方库），而模块单元又必须以 *module-declaration* 开头——如果直接在 `export module M;` 之后 `#include <windows.h>`，那几万个声明就会**附属于 M**，与其他 TU 中通过 `#include` 得到的同名实体发生附属冲突（[[basic.link#10]]）。

**全局模块片段**（global module fragment）就是为此设计的"前厅"：

```cpp
module;                  // 全局模块片段开始
#include <cstdio>        // 这里的声明附属于全局模块
#include "legacy.h"
export module M;         // 模块管辖范围开始
// ...
```

本节规定了它的语法和一个关键优化：全局模块片段中**未被模块使用的声明会被丢弃**，不会对导入者产生任何影响。为此标准定义了一个相当精细的关系——**decl-reachable**。

阅读前需要：[[module.unit]]（管辖范围、全局模块）、[[module.reach]]（可达性的基本概念）、[[basic.def.odr]]（"表达式命名函数"）、[[temp.dep]]（依赖调用）。

## 语法与用途（¶1）

```text
global-module-fragment:
    module-keyword ; declaration-seq(opt)
```

¶1 *global-module-fragment* 规定了一个模块单元的**全局模块片段**的内容。全局模块片段可用于提供**附属于全局模块**、并且**可在该模块单元中使用**的声明。

全局模块片段属于全局模块（[[module.unit#6]]），所以其中的声明附属于全局模块（[[module.unit#7]] ¶7.3：附属于它所在管辖范围对应的模块——全局模块）。它在 *module-declaration* 之前，因此**不在** M 的管辖范围中，`export` 不能出现在这里（[[module.interface#1]]）。

### 只能写预处理指令

[[cpp.pre#5]] 规定：在翻译阶段 4 开始时，*pp-global-module-fragment* 的组中**既不能有文本行，也不能有 `import` 指令**。也就是说，全局模块片段中只能写 `#include`、`#define`、`#if` 等预处理指令；声明只能通过 `#include` 进来。

```cpp title="ok.cppm" ok
module;
#define _GNU_SOURCE        // OK：预处理指令（常用来配置被包含的头文件）
#include <cstdio>          // OK
export module M;
```

```cpp title="bad.cppm" error
module;
void f();                  // error: 全局模块片段中出现文本行（[cpp.pre]/5）
import <vector>;           // error: 全局模块片段中出现 import 指令
export module M;
```

为什么这样限制？全局模块片段的本意是"兼容层"，只为 `#include` 服务。允许直接写声明，会鼓励人们把它当作"在模块里声明全局模块实体"的通用手段——那应该用 `extern "C++"`（[[module.unit#7]] ¶7.2.4）。禁止 `import` 则是因为导入应当写在模块管辖范围中（[[module.import#1]]），全局模块片段里导入的东西归属不清。

!!! impl "Clang 不诊断文本行"
    本机 Clang 23 对 `module; void f(); export module M;` 不给出任何诊断（即使开启 `-Wall -Wextra -pedantic`）。按 [[cpp.pre#5]]，这是一条可诊断规则，Clang 的行为不符合标准。写可移植代码时，全局模块片段中只放预处理指令。

## decl-reachable（¶2）

¶3 要求丢弃"未被使用"的全局模块片段声明。但"被使用"该怎么定义？对模板而言，一个依赖调用 `f(x)` 在定义时根本不知道会调用谁；一个 `inline` 函数的默认实参可能引用别的函数……¶2 给出了一个**保守的、可在定义时静态计算的**关系。

¶2 在同一 TU 中，声明 D 从声明 S [[g:decl-reachable|decl-reachable]]，若以下之一成立：

- **¶2.1** D 不声明函数或函数模板，且 S 中含有命名 D 的 *id-expression*、*namespace-name*、*type-name*、*template-name* 或 *concept-name*；
- **¶2.2** D 声明函数或函数模板，且该函数被 S 中出现的某个**表达式命名**（[[basic.def.odr]] 意义上的"命名"，即会参与重载决议并被选中）；
- **¶2.3** S 含有**依赖调用** E（[[temp.dep]]），且 D 被下面这种合成表达式的任何名字查找找到：把 E 中每个**类型依赖**的实参或操作数替换为"一个没有关联命名空间或关联实体的占位类型的值"；
    - Note 1：这包括考虑重写 `!=` 时对 `operator==` 的查找、考虑重写关系比较时对 `operator<=>` 的查找，以及考虑 `operator==` 能否作为重写目标时对 `operator!=` 的查找。
- **¶2.4** S 含有对某个包含 D 的重载集**取地址**的表达式（[[over.over]]），且目标类型是依赖的；
- **¶2.5** 存在一个**不是命名空间定义**的声明 M，M 从 S decl-reachable，并且：
    - **¶2.5.1** D 从 M decl-reachable（传递性）；
    - **¶2.5.2** D 与 M 声明同一实体，且 D 既不是友元声明，也不栖居于块作用域（同一实体的其他声明一并带上）；
    - **¶2.5.3** D 声明命名空间 N，而 M 是 N 的成员（外围命名空间被带上）；
    - **¶2.5.4** D 与 M 中一个声明类或类模板 C，另一个声明 C 的成员或友元；
    - **¶2.5.5** D 与 M 中一个声明枚举 E，另一个声明 E 的枚举项；
    - **¶2.5.6** D 声明函数或变量，而 M 在 D 中声明（脚注：声明可以出现在变量初始化器的 lambda 中）；
    - **¶2.5.7** D 与 M 中一个声明模板，另一个声明该模板的偏特化、显式特化，或隐式/显式实例化；
    - **¶2.5.8** M 声明类模板，D 是它的推导指引；
    - **¶2.5.9** D 与 M 中一个声明类或枚举类型，另一个为该类型引入用于链接的 typedef 名。

### 逐条理解

**¶2.1 与 ¶2.2：直接提及。** 非函数的东西（类型、变量、命名空间、模板、概念）只要被**写出名字**就算；函数则要求被**表达式命名**——也就是重载决议真的选中了它（或它是唯一候选）。为什么区别对待函数？因为写出函数名 `f` 时，名字查找可能找到一整个重载集，其中大部分重载并没有被用到；只把被选中的那个算作 decl-reachable，可以丢弃更多无用声明。

**¶2.3：依赖调用的保守估计。** 模板中的 `g(x)`（`x` 类型依赖）在定义时无法做重载决议。标准的做法是：把类型依赖的实参换成一个"什么都不关联"的占位类型的值，然后做**名字查找**（不做重载决议）——找到的所有声明都算 decl-reachable。关键在于"没有关联命名空间"：这个合成表达式的 ADL **只会**看非依赖实参带来的关联命名空间。所以：

- `f(x, 123)` 中若 `x` 的类型**非依赖**（如 `N::X x;`），ADL 会进入 `N`，`N::f` 被找到；
- `g((T(), x))` 中，逗号表达式 `(T(), x)` 是类型依赖的（`T` 可能重载了逗号运算符），被整体替换为占位值——ADL 不会进入 `N`，`N::g` **找不到**。

这正是 ¶5 例子中 `use_f` 与 `use_g` 的区别。

**¶2.4：依赖目标类型的取地址。** `static_cast<T>(&f)` 这类表达式在实例化前不知道选哪个重载，所以整个重载集都算。

**¶2.5：闭包规则。** 一旦某个声明 M 被认为 decl-reachable，与它"天然绑定"的声明也必须带上，否则 M 在导入者那里就是残缺的：

- 传递（¶2.5.1）：M 用到的东西也要保留。
- 同一实体的其他声明（¶2.5.2）：例如函数的前置声明与定义；但**友元声明**和**块作用域声明**除外——它们是"顺带"的重声明，没必要因此保留。
- 外围命名空间（¶2.5.3）：这就是例子中总说"`N` 和 `::` 是 decl-reachable 的"原因。
- 类与其成员/友元（¶2.5.4）、枚举与枚举项（¶2.5.5）：类型是一个整体。注意这是双向的："一个声明类，另一个声明成员"——从成员也能到达类。
- 函数/变量与其内部声明（¶2.5.6）：函数体内的局部类、变量初始化器中 lambda 里的声明。
- 模板与其特化/实例化（¶2.5.7）、类模板与推导指引（¶2.5.8）：特化是模板语义的一部分。
- 类型与其用于链接的 typedef 名（¶2.5.9）：`typedef struct { ... } P;` 中的无名类与 `P` 不可分。

注意 ¶2.5 要求 M **不是命名空间定义**。命名空间定义是一个"巨大的声明"：`namespace std { ... }` 这个声明本身**包含**了其中所有成员的声明和名字。如果允许 M 是命名空间定义，那么只要某个成员可达，经 ¶2.5.2（同一命名空间的其他定义）和 ¶2.5.1（从这些定义中"提及"的一切）就会把整个命名空间的内容都拉进来，丢弃机制就失效了。所以从成员只能单向走到外围命名空间的**声明**（¶2.5.3），而不能再从命名空间定义扩散出去。

### 实现可以选择的模糊地带（¶2.6–¶2.10）

在做上述判定时，以下各项**未指明**：

- **¶2.6** 对 *alias-declaration*、typedef、*using-declaration*、*namespace-alias-definition* 的引用，是否先被替换为它们所指名的声明；
- **¶2.7** 不表示依赖类型、且模板名是别名模板的 *simple-template-id*，是否先被替换为它所表示的类型；
- **¶2.8** 不表示依赖类型的 *decltype-specifier*，是否先被替换为它所表示的类型；
- **¶2.9** 非值依赖的常量表达式，是否先被替换为常量求值的结果；
- **¶2.10** 非依赖语境中的拼接表达式、拼接类型说明符等（[[basic.splice]]），是否先被替换为它所指代的构造。

为什么允许这些自由？编译器在构建 AST 时往往已经"看穿"了别名、`decltype`、常量表达式——Clang 中 `int a[size];` 的数组类型直接记录的是 `int[2]`，追溯到 `size` 的引用需要额外保留信息。标准不强迫实现保留这些信息，代价是：依赖这些边的 decl-reachable 判定在不同实现上可能不同。

## 丢弃（¶3）

¶3 模块单元的全局模块片段中的声明 D，若从该 TU 的 *translation-unit* 的 *declaration-seq* 中的**任何声明**都不是 decl-reachable 的，则 D 被[[g:discarded-declaration|丢弃]]（discarded）。

几个细节：

- "TU 的 *declaration-seq*"：在 *translation-unit* 的文法 `global-module-fragment(opt) module-declaration declaration-seq(opt) private-module-fragment(opt)` 中，这是 *module-declaration* 之后、私有模块片段之前的部分。全局模块片段内部的声明互相引用不算；**私有模块片段中的使用也不算**——但私有片段本来就对其他 TU 不可达，所以只被私有片段使用的东西被丢弃也无妨。
- 丢弃只发生在**模块单元**的全局模块片段中。普通 TU 没有全局模块片段，什么都不丢弃。
- 丢弃不影响**本 TU** 内对 D 的使用。被丢弃的声明在本模块单元里照常可用。

Note 2：被丢弃的声明**在该模块单元之外既不可达也不可见**，在实例化点（[[temp.point]]）位于该模块单元之外的模板实例化中也是如此——**即使**实例化语境（[[module.context]]）包含了该模块单元。

这一条与 [[basic.lookup.argdep#4]] 配合：依赖名的 ADL 会从实例化语境中的每个点做查找，但"忽略出现在其他 TU、附属于全局模块、且被丢弃或具有内部链接的声明"。

为什么要丢弃？

- **BMI 体积**：一个模块的全局模块片段可能 `#include` 了几十万行的系统头文件，而模块真正用到的只是其中一小部分。被丢弃的声明不必写进 BMI（或者至少不必让导入者看到）。
- **接口卫生**：不丢弃的话，导入者会"意外地"依赖于模块内部碰巧包含的头文件中的声明（例如通过 ADL 找到某个函数、通过可达性使某个类型完整）。一旦模块作者删掉某个 `#include`，导入者就可能编译失败。丢弃把模块的"有效接口"限定在模块真正用到的范围内。

## 例子

### 什么是 decl-reachable 的（¶4）

¶4 Example 1（加注；假定以下代码位于某模块接口单元的管辖范围，被引用的实体来自全局模块片段）：

```cpp
const int size = 2;
int ary1[size];                 // 未指明 size 是否从 ary1 decl-reachable（¶2.9：常量表达式可能已被求值为 2）
constexpr int identity(int x) { return x; }
int ary2[identity(2)];          // 未指明 identity 是否从 ary2 decl-reachable（同上）

template<typename> struct S;
template<typename, int> struct S2;
constexpr int g(int);

template<typename T, int N>
S<S2<T, g(N)>> f();             // S、S2、g 和 :: 都从 f decl-reachable
                                //  g(N) 是值依赖的，不会被替换；g 被表达式命名（¶2.2）

template<int N>
void h() noexcept(g(N) == N);   // g 和 :: 从 h decl-reachable（noexcept 说明符也是声明的一部分）
```

### 丢弃如何影响导入者（¶5）

¶5 Example 2（加注）：

```cpp title="foo.h"
namespace N {
  struct X {};
  int d();
  int e();
  inline int f(X, int = d()) { return e(); }
  int g(X);
  int h(X);
}
```

```cpp title="M.cppm（模块 M 的接口）"
module;
#include "foo.h"
export module M;
template<typename T> int use_f() {
  N::X x;                       // N::X、N 和 :: 从 use_f decl-reachable
  return f(x, 123);             // N::f 从 use_f decl-reachable（¶2.3：x 非依赖，ADL 进入 N）
                                // N::e 间接 decl-reachable：它从 N::f decl-reachable（¶2.5.1）
                                // N::d 也从 N::f decl-reachable（默认实参），
                                //   即使这次调用没有用到默认实参
}
template<typename T> int use_g() {
  N::X x;                       // N::X、N 和 :: 从 use_g decl-reachable
  return g((T(), x));           // N::g 不从 use_g decl-reachable：
                                //   (T(), x) 类型依赖，被替换为无关联命名空间的占位值
}
template<typename T> int use_h() {
  N::X x;                       // N::X、N 和 :: 从 use_h decl-reachable
  return h((T(), x));           // N::h 不从 use_h decl-reachable，但……
}
int k = use_h<int>();           // use_h<int> 从 k decl-reachable（¶2.5.7：实例化），
                                //   use_h<int> 中 h 被表达式命名（¶2.2），
                                //   所以 N::h 从 k decl-reachable
```

```cpp title="M-impl.cpp（模块 M 的实现单元）" error
module M;
int a = use_f<int>();           // OK
int b = use_g<int>();           // error: 没有可行的 g：
                                //   g 从 M 接口的管辖范围不是 decl-reachable 的，已被丢弃
int c = use_h<int>();           // OK：N::h 因 k 的存在而未被丢弃
```

为什么 `use_g<int>()` 在实现单元中失败？实例化 `use_g<int>` 时，`g((T(), x))` 是依赖调用，ADL 需要找 `N::g`。实例化点在实现单元中（不在接口单元里），按 Note 2，被丢弃的 `N::g` 在这里既不可达也不可见——即使实例化语境包含接口单元（[[module.context]]）。而 `N::h` 没有被丢弃，因为接口单元中的 `int k = use_h<int>();` 恰好"用到"了它。

这个例子也说明了丢弃的**脆弱性**：删除接口中看似无关的 `int k = use_h<int>();`，会让实现单元中的 `use_h<int>()` 编译失败。这是设计上的有意取舍——模块作者应当保证模板需要的东西是"显式被用到"的，或者干脆把它们导出。

!!! impl "Clang 的两种 BMI 与丢弃"
    本机 Clang 23 上：

    - 用 `--precompile` 生成的**完整 BMI**（full BMI）不实施丢弃：上例中 `use_g<int>()` 被接受，没有错误。
    - 用 `-c M.cppm -fmodule-output=M.pcm` 一步生成目标文件和 BMI 时，Clang 23 默认产出 **reduced BMI**（与显式加 `-fmodules-reduced-bmi` 的产物逐字节大小相同，本例 23748 字节，完整 BMI 为 30220 字节）。reduced BMI 实施丢弃：`use_g<int>()` 报 "use of undeclared identifier 'g'"，与标准一致。

    所以，同一份代码在不同的 Clang 构建方式下表现不同——又一个"不要依赖未被显式使用的全局模块片段声明"的理由。CMake 驱动 Clang 时使用的是 `-fmodule-output` 方式（见 [[toolchain/modules-in-practice]]）。

### 全局模块片段中的声明不会被导出

丢弃之外，还有一条更基本的规则：全局模块片段中的声明**不是被导出的**（不在任何 *export-declaration* 中），所以无论是否被丢弃，导入者的**名字查找**都找不到它们。丢弃只影响**可达性**以及依赖名的 ADL。

```cpp title="lib.h"
#pragma once
namespace lib {
  struct Used { int v = 1; };
  inline int helper(Used u) { return u.v; }
}
```

```cpp title="M.cppm"
module;
#include "lib.h"
export module M;
export lib::Used make() { return {}; }   // lib::Used 从 make decl-reachable，未被丢弃
```

```cpp title="user.cpp" error
import M;
int main() {
  auto u = make();       // OK：lib::Used 的定义可达（未丢弃）
  int a = u.v;           // OK：成员查找只需定义可达
  return helper(u);      // error: lib::helper 不可见——非依赖的 ADL 也只找"先于"此处的声明，
                         //   而 GMF 中的声明未导出；何况它还被丢弃了
}
```

想让导入者使用 `lib::helper`，要么在 M 中 `export using lib::helper;`（[[module.interface#5]]），要么让导入者自己 `#include "lib.h"` 或 `import "lib.h";`。

## 实现视角

!!! impl "全局模块片段与 ODR"
    全局模块片段中通过 `#include` 进来的 inline 函数、类定义等，与其他 TU 通过 `#include` 得到的同一实体，必须满足 ODR 的"多处定义一致"要求（[[basic.def.odr]]）。模块并没有让这些实体变成"模块私有"——它们仍附属于全局模块，仍是全程序共享的同一实体。一个常见问题是：模块 M 的全局模块片段在 `#define NDEBUG` 下包含了某个头文件，而另一个 TU 在没有 `NDEBUG` 的情况下包含了它，产生两份不同的 inline 函数定义——IFNDR，和传统头文件世界完全一样。

    编译器在导入多个 BMI 时，需要把各个 BMI 中同一个全局模块实体的定义**合并**，这时有机会发现头文件世界里发现不了的 ODR 违规。本机实验：模块 A 在全局模块片段中 `#define BIG` 后包含 `cfg.h`（`struct Cfg { long v; }`），模块 B 不定义 `BIG` 包含同一头文件（`struct Cfg { int v; }`）。在同时导入 A 和 B 的 TU 中访问 `Cfg` 的成员 `v`，Clang 23 报 "reference to 'v' is ambiguous"，并把两个版本的 `Cfg::v` 都列为候选——它没有静默选一个。按标准这是 IFNDR，所以这种诊断是额外的收获，而不是保证。

## 历史与演进

!!! history "C++20"
    - Modules TS 没有全局模块片段的显式语法；模块单元中位于 `module M;` 之前的内容默认属于全局模块。C++20 的 [[P1103R3]] 引入 `module;` 作为显式的开始标记，使"模块单元"可以通过第一行就被识别（这对依赖扫描至关重要）。
    - decl-reachable 与丢弃规则也来自 C++20 的合并提案，此后在多次缺陷修正中细化，例如 Note 1 中关于重写比较运算符候选的查找、¶2.10 关于反射拼接的未指明项（随 C++26 反射加入）。

## 陷阱

!!! pitfall "把 #include 写在模块声明之后"
    `export module M;` 之后的 `#include <string>` 使 `std::string` 等附属于 M，几乎必然导致与其他 TU 的附属冲突或重定义。`#include` 一律放在 `module;` 之后、`export module M;` 之前。

!!! pitfall "依赖全局模块片段中'碰巧'包含的头文件"
    导入者不能指望 M 的全局模块片段中的任何名字——它们不可见。导入者需要什么，自己 `#include` 或 `import`。

!!! pitfall "模板中的依赖调用找不到函数"
    如 ¶5 的 `use_g`：模块中导出的模板做依赖 ADL 调用，目标函数来自全局模块片段，却从未在模块管辖范围中被"非依赖地用到"——被丢弃，导入者实例化时失败。解决办法：在模块中显式 `using N::g;`（使其 decl-reachable），或者把模板改为非依赖地调用它。

## 思考题

!!! question "思考题 1"
    全局模块片段 `#include` 了 `struct P { int x; }; struct Q { P p; };`。模块管辖范围中只有 `export Q make();`。`P` 会被丢弃吗？

<details markdown="1">
<summary>答案</summary>

不会。`Q` 从 `make` decl-reachable（¶2.1，*type-name* 命名了 `Q`）。由 ¶2.5.4，`Q` 的成员 `p` 的声明从 `Q` decl-reachable；`p` 的声明中有 *type-name* `P`，由 ¶2.1 与 ¶2.5.1 的传递，`P` 也 decl-reachable。直觉上也必须如此：导入者使用 `Q` 需要知道 `Q` 的布局，进而需要 `P` 完整。
</details>

!!! question "思考题 2"
    为什么 ¶2.2 只把被**表达式命名**的函数算作 decl-reachable，而 ¶2.3 对依赖调用却把**名字查找找到的所有**声明都算上？

<details markdown="1">
<summary>答案</summary>

非依赖的调用在定义处就完成了重载决议，被选中的那个函数是确定的，其他重载不会在任何上下文中被这次调用用到，可以安全丢弃。依赖调用的重载决议推迟到实例化时，那时实参类型已知，可能选中名字查找找到的任何一个候选——在定义时无法排除，所以保守地全部保留（但仍不包括只有依赖 ADL 才能找到的候选，因为占位类型"无关联命名空间"——这部分被有意排除，由模块作者负责）。
</details>

## 小结

| 规则 | 段落 |
|---|---|
| `module;` 开启全局模块片段，其中声明附属于全局模块、可在本模块单元中使用 | ¶1 |
| 全局模块片段只能有预处理指令（不能有文本行和 `import`） | [[cpp.pre#5]] |
| decl-reachable：被提及（非函数）/ 被表达式命名（函数）/ 依赖调用的保守查找 / 依赖取地址 / 闭包规则 | ¶2 |
| 别名、`decltype`、常量表达式、拼接是否先被替换：未指明 | ¶2.6–¶2.10 |
| 不从管辖范围中任何声明 decl-reachable 的 GMF 声明被丢弃 | ¶3 |
| 被丢弃的声明在模块单元外不可达、不可见，在模块外实例化的模板中亦然 | ¶3 Note 2 |
