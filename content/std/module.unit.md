---
title: 模块单元与模块范围
summary: 什么是模块单元、具名模块、接口单元与实现单元、模块分区；模块名的保留规则；模块单元的管辖范围（purview）与全局模块；一个声明附属于哪个模块。
status: done
since: c++20
papers: P1103R3
related: module, module.interface, module.import, module.global.frag, basic.link, cpp.module, toolchain/modules-in-practice
tags: 模块, 附属, 分区
updated: 2026-10-17
---

本节是整个模块章节的"定义页"：它规定了一个翻译单元如何宣布自己属于某个模块（*module-declaration*），一个模块由哪些单元组成、各自扮演什么角色，以及最关键的——**每个声明附属于哪个模块**（attachment）。附属关系是 [[basic.link]] 判定"两个声明是否声明同一实体"的输入之一，也是编译器决定符号修饰名的依据。

阅读前需要：[[lex.phases]]（翻译单元）、[[basic.link]]（链接、同一实体）。整章导读见 [[module]]。

## 模块声明的语法

```text
module-declaration:
    export-keyword(opt) module-keyword module-name module-partition(opt) attribute-specifier-seq(opt) ;
module-name:
    module-name-qualifier(opt) identifier
module-partition:
    : module-name-qualifier(opt) identifier
module-name-qualifier:
    identifier .
    module-name-qualifier identifier .
```

几个要点：

- `export-keyword`、`module-keyword` 不是普通的 `export`/`module` 关键字，而是预处理器在识别出模块指令后**替换**出来的特殊记号（[[cpp.module#2]]）。所以 `module` 必须位于行首、作为预处理指令出现；`module` 本身仍是**具有特殊含义的标识符**，不是关键字，`int module = 0;` 是合法的。
- 模块名中的 `.` **没有语义**。`export module a.b;` 中的 `a.b` 只是一个带点的名字，与模块 `a` 没有任何父子关系，导入 `a` 不会导入 `a.b`。点号只是约定俗成的层次命名方式。
- 分区名 `:part` 也可以带点（`:detail.io`），同样没有层次语义。
- 模块名和分区名中的标识符不能是宏（[[cpp.module#1]]）：模块名必须能被构建系统不做完整预处理地扫描出来。

## 模块单元、具名模块与模块名（¶1）

¶1 含有 *module-declaration* 的 TU 是[[g:module-unit|模块单元]]（module unit）。具有相同 *module-name* 的所有模块单元组成一个**具名模块**（named module）。

注意这个定义的方向：标准里没有一个"模块对象"可以独立存在，模块就是"同名模块单元的集合"。一个模块的边界由构建系统决定（哪些文件被一起编译、链接），标准只通过诸如 ¶2"恰好一个主接口单元"这样的 IFNDR 规则约束这个集合。

接下来是对模块名的限制：

- 标识符 `module` 和 `import` 不得出现在 *module-name* 或 *module-partition* 中。原因是解析歧义：`import` 打头的行会被识别为导入指令，名字里有它们会让扫描器无所适从。这是**可诊断**的规则。
- 以 `std` 后跟零个或多个数字的标识符**开头**的模块名（`std`、`std.core`、`std2`、`std23.x`），以及**包含**保留标识符（[[lex.name]]，如 `__foo`、`_Foo`）的模块名，都是**保留的**，不得出现在 *module-declaration* 中；{{ifndr}}。
    - 若保留模块名中有标识符是保留标识符，则该名字保留给**实现**使用（如编译器内部的 `__builtin_mod`）；
    - 否则保留给**未来标准化**（`std`、`std.compat` 就是这样被标准库占用的，见 [[std.modules]]）。
- 可选的 *attribute-specifier-seq* 属于该 *module-declaration*（标准没有定义任何可用于此处的属性，留给实现）。

```cpp title="reserved.cppm" ifndr
export module std2.util;   // 保留名（std 后跟数字开头），IFNDR
```

```cpp title="bad-name.cppm" error
export module my.import;   // error: import 不能出现在模块名中
```

!!! impl "Clang 的行为"
    本机 Clang 23：`export module std;`、`export module std2.util;`、`export module __impl;` 都只给出 `-Wreserved-module-identifier` 警告（IFNDR 不要求诊断，警告已经是额外的善意）；`export module my.import;` 是错误。libc++ 自己的 `std.cppm` 需要以 `-Wno-reserved-module-identifier` 编译。注意 `export module stdx;` **不是**保留名：`stdx` 不是"`std` 后跟零个或多个数字"。

!!! lawyer "为什么是 IFNDR 而不是可诊断？"
    标准库的模块 `std` 本身就是用 `export module std;` 写成的（libc++ 的 `std.cppm`、MSVC 的 `std.ixx`）。如果规定"必须诊断"，实现就得区分"这是用户写的还是我自己写的"——这种区分超出了语言本身。设成 IFNDR 让实现可以用编译选项或文件位置来决定是否放行。

## 接口单元与实现单元（¶2）

¶2 *module-declaration* 以 `export` 开头的模块单元是**模块接口单元**（module interface unit）；其他模块单元是**模块实现单元**（module implementation unit）。

一个具名模块必须**恰好有一个**不带分区名的接口单元，称为[[g:primary-module-interface-unit|主模块接口单元]]（primary module interface unit）；{{ifndr}}。

为什么是 IFNDR？编译器每次只看一个 TU，它无法知道别处是否还有第二个 `export module M;`，也无法知道是否根本没有。这类"模块整体"层面的错误只有构建系统或链接器能发现——而且未必能发现（两个主接口单元各自产出 BMI，导入者拿到哪个取决于构建配置）。

主接口单元的特殊地位：

- `import M;` 导入的是 M 的**所有接口单元**（[[module.import#3]]），但其他接口单元（接口分区）必须由主接口单元直接或间接导出（¶3），所以实际上"导入主接口单元"就带入了一切。
- 普通实现单元（`module M;`）隐式导入主接口单元（¶8）。
- 私有模块片段只能出现在主接口单元中（[[module.private.frag]]）。
- [[module.context#3]] 把"主模块接口单元的末尾"作为一个特殊的实例化语境点。

## 模块分区（¶3–¶4）

¶3 *module-declaration* 含有 *module-partition* 的模块单元是[[g:module-partition|模块分区]]（module partition）。约束：

- 一个具名模块不得包含两个同名分区；
- 模块的所有**接口分区**（即 `export module M:P;` 形式的单元）必须被主模块接口单元**直接或间接导出**（`export import :P;`）。

两条都是 {{ifndr}}，理由同上：编译器看不见整个模块。

Note 1：分区只能被**同一模块**的其他模块单元导入（`import :P;` 的语法只允许在模块单元中、且分区名隐含当前模块，见 [[module.import#4]]）。模块被划分成哪些单元，**对模块外部不可见**——导入者看到的只是"模块 M"，无从得知 `M:Foo` 的存在。实现上这体现为：分区里声明的实体，其修饰名里只有模块名，不含分区名（见下方"实现视角"）。

为什么需要分区？在没有分区的情况下，一个模块的接口只能写在一个文件里（主接口单元），大模块会很臃肿；而实现单元又不能被导入，无法在模块内部共享"内部头文件"。分区同时解决了两个问题：

| | 接口分区 `export module M:P;` | 实现分区 `module M:P;` |
|---|---|---|
| 是否接口单元 | 是 | 否 |
| 能否包含 `export` 声明 | 能 | 不能（[[module.interface#1]]） |
| 是否必须被主接口导出 | 必须（¶3，IFNDR） | 不能被导出（[[module.import#8]]） |
| 典型用途 | 把大模块的接口拆成多个文件 | 模块内部共享的声明（取代"内部头文件"） |
| 能否被模块外导入 | 不能（间接通过 `import M;` 带入） | 不能 |
| 是否隐式导入主接口 | 否（¶8） | 否（¶8） |

### 例子：一个四单元的模块（¶4）

¶4 Example 1（标准例子，加注）：

```cpp title="TU #1：A.cppm（主模块接口单元）"
export module A;
export import :Foo;   // 接口分区 A:Foo 必须被导出（¶3）
export int baz();
```

```cpp title="TU #2：A-Foo.cppm（接口分区）"
export module A:Foo;
import :Internals;    // 导入本模块的实现分区
export int foo() { return 2 * (bar() + 1); }
```

```cpp title="TU #3：A-Internals.cppm（实现分区）"
module A:Internals;
int bar();            // 模块链接：只能在模块 A 内部使用
```

```cpp title="TU #4：A.cpp（实现单元）"
module A;             // 隐式 import A;（¶8），所以 baz 可见
import :Internals;
int bar() { return baz() - 10; }
int baz() { return 30; }
```

```cpp title="main.cpp" ok
import A;
int main() { return foo() + baz(); }   // 2*(20+1) + 30 = 72
```

模块 A 包含四个 TU：

- **¶4.1** 主模块接口单元；
- **¶4.2** 模块分区 `A:Foo`，是模块接口单元，构成 A 的接口的一部分；
- **¶4.3** 模块分区 `A:Internals`，对 A 的外部接口没有贡献；
- **¶4.4** 提供 `bar` 和 `baz` 定义的模块实现单元，它没有分区名，所以**不能被导入**。

`main.cpp` 中的 `bar` 不可见：它没有被导出，且 `main.cpp` 不属于模块 A。

!!! impl "本机验证"
    这个例子在 Clang 23 上按 `A-Internals → A-Foo → A → (A.cpp, main.cpp)` 的顺序编译、链接后返回 72。Clang 对 TU #2 的 `import :Internals;` 给出警告 `-Wimport-implementation-partition-unit-in-interface-unit`："Names from A:Internals may not be reachable"——这不是标准的要求，而是 Clang 对一个可移植性风险的提醒：实现分区不是"必然可达"的（[[module.reach#1]]），导入者能否看到它的定义是未指明的。

## 管辖范围（¶5）

¶5 [[g:purview|模块单元管辖范围]]（module unit purview）是从 *module-declaration* 开始、到 TU 末尾为止的记号序列。具名模块 M 的**管辖范围**是 M 的所有模块单元的管辖范围的集合。

注意：

- 管辖范围**从 *module-declaration* 开始**，所以全局模块片段（`module;` 到 `export module M;` 之间）**不在** M 的管辖范围内——它属于全局模块（¶6）。
- 私有模块片段**在**管辖范围内（它在 *module-declaration* 之后）。私有片段中的声明仍然附属于 M。
- "在管辖范围中"是许多规则的触发条件：附属（¶7.3）、`export` 只能出现在接口单元的管辖范围中（[[module.interface#1]]）、模块接口中 `const` 变量不再默认内部链接（[[basic.link#3]] 的 ¶3.2.1）。

## 全局模块（¶6）

¶6 [[g:global-module|全局模块]]（global module）是所有**全局模块片段**和所有**非模块单元的 TU** 的集合。出现在这些地方的声明称为在全局模块的管辖范围中。

Note 2：全局模块没有名字、没有模块接口单元，也不由任何 *module-declaration* 引入。

这一定义让 C++20 之前的全部代码都有了一个模块归属：你写的每一个传统 `.cpp` 文件、每一个被 `#include` 的头文件（只要它被包含进非模块 TU 或全局模块片段），其中的声明都附属于全局模块。头文件单元（[[module.import#5]]）不是模块单元，所以它们也属于全局模块。

全局模块与具名模块的关键区别是：全局模块中的实体在**所有 TU 中共享**。两个不相关的 TU 都写了 `int f();`，它们声明的是同一个 `f`（附属于同一个模块——全局模块）。这正是向后兼容所需要的。

## 附属（¶7）

¶7 **模块**是具名模块或全局模块。声明按如下规则**附属于**（attached to）某个模块：

- **¶7.1** 若声明是**非依赖的友元声明**，并且
    - 指名一个函数，其 *declarator-id* 是 *qualified-id* 或 *template-id*；或
    - 指名一个类，且不是用"既无 *nested-name-specifier* 也无 *simple-template-id* 的 *elaborated-type-specifier*"来指名的，

  则它附属于**被指名的那个友元实体**所附属的模块（[[basic.link]]）。
- **¶7.2** 否则，若声明
    - **¶7.2.1** 声明具有外部链接的**命名空间**，
    - **¶7.2.2** 声明**类型别名**，
    - **¶7.2.3** 声明**命名空间别名**，或
    - **¶7.2.4** 出现在**语言链接规范**（*linkage-specification*，即 `extern "C"`/`extern "C++"`）之内，

  则它附属于**全局模块**。
- **¶7.3** 否则，声明附属于**它所在管辖范围对应的模块**。

### ¶7.3：默认规则

绝大多数声明落入 ¶7.3：在 `export module M;` 之后写的函数、类、变量、模板都附属于 M，无论是否导出。在全局模块片段或普通 TU 中写的，附属于全局模块。

**导出与否不影响附属。** `export int f();` 和 `int g();` 都附属于 M；区别只在链接（`f` 外部链接，`g` 模块链接，[[basic.link#4]]）。这一点常被误解为"导出的东西属于全局"。

### ¶7.2：为什么命名空间、别名、语言链接块附属于全局模块

- **命名空间（¶7.2.1）**：命名空间是开放的，许多模块和普通代码都会向 `namespace std`、`namespace boost` 中添加成员。如果命名空间本身附属于某个模块，那么两个模块的 `namespace util` 就成了两个不同的命名空间实体，无法共同扩展，也会与全局模块中的同名命名空间冲突（[[basic.link#10]] Note 5）。所以命名空间本身附属于全局模块，而**命名空间的成员**按各自规则附属。具有内部链接的命名空间（无名命名空间）不在此列——它只在一个 TU 中存在，按 ¶7.3 附属于当前模块。
- **类型别名、命名空间别名（¶7.2.2–¶7.2.3）**：别名不引入新实体，只是另一个名字。它附属于全局模块，使得不同模块对同一类型的同名别名（例如两个模块都写了 `using size_type = std::size_t;`）不会冲突——[[basic.link#8]] 的 ¶8.2 也规定声明同一底层实体的别名是"同一实体"。
- **语言链接规范（¶7.2.4）**：这是模块代码中**显式选择附属于全局模块**的唯一手段。`extern "C"` 显然：C 函数没有模块概念，必须与其他 TU 中的同名 C 函数是同一个。`extern "C++"` 是 C++20 为模块特意赋予的新含义——它让你在模块管辖范围中声明一个附属于全局模块的 C++ 实体，用于：
    - 与头文件中声明的实体对接（"我这里声明的就是那个头文件里的 `::g`"）；
    - 在模块中定义一个供非模块代码通过头文件声明来调用的函数；
    - 把一个代码库渐进迁移到模块时保持 ABI 不变（修饰名不含模块名）。

```cpp title="M.cppm" ok
export module M;
int f1() { return 1; }                 // 附属于 M，模块链接
export int f2() { return 2; }          // 附属于 M，外部链接
extern "C++" int f3() { return 3; }    // 附属于全局模块（¶7.2.4），外部链接
extern "C++" { export int f4() { return 4; } }   // 同上，且被导出
extern "C" int f5() { return 5; }      // 附属于全局模块，C 语言链接
namespace N { int g() { return 6; } }  // 命名空间 N 附属于全局模块；N::g 附属于 M
export struct S { friend int h(S) { return 7; } };   // h 附属于 M（¶7.3）
export int use() { return f1() + N::g() + h(S{}); }
```

用 `nm` 查看这个模块接口单元生成的目标文件（Clang 23，Mach-O，经 `llvm-cxxfilt` 解码）：

| 声明 | 原始符号 | 解码后 |
|---|---|---|
| `f1`（未导出） | `__ZW1M2f1v` | `f1@M()` |
| `f2`（导出） | `__ZW1M2f2v` | `f2@M()` |
| `f3`（`extern "C++"`） | `__Z2f3v` | `f3()` |
| `f4`（`extern "C++"` + 导出） | `__Z2f4v` | `f4()` |
| `f5`（`extern "C"`） | `_f5` | — |
| `N::g` | `__ZN1NW1M1gEv` | `N::g@M()` |
| 友元 `h` | `__ZW1M1hS_1S` | `h@M(S@M)` |

观察：导出与否不改变符号（`f1` 和 `f2` 都带 `W1M`）——修饰名反映的是**附属**而不是链接；`extern "C++"` 去掉了模块标记；命名空间 `N` 本身没有模块标记（它附属于全局模块），而成员 `g` 有。

### 附属冲突

由于"同一实体"要求附属于同一模块（[[basic.link#8]] 的 ¶8.3），在模块中重声明一个全局模块实体时，必须让它也附属于全局模块：

```cpp title="decls.h"
int f();
int g();
```

```cpp title="M.cppm" error
module;
#include "decls.h"
export module M;
export using ::f;      // OK：using 声明不声明实体，导出的是 decls.h 中的 f
int g();               // error: 与 decls.h 的 g 对应，但附属于 M（[basic.link]/10）
```

把最后一行改成 `extern "C++" int g();` 就合法了：它附属于全局模块，是 `decls.h` 中 `g` 的重声明。

### ¶7.1：友元的附属

友元声明有个特殊问题：`friend void f();` 既可能是在**引入**一个新函数（隐藏友元），也可能是在**指名**一个已有函数。¶7.1 区分了"必然指名已有实体"的形式：

- `friend void ::g();`、`friend void N::g();`（限定名）——必须找到已有声明；
- `friend void g<>(int);`（*template-id*）——指名已有模板的特化；
- `friend X;`、`friend class N::X;`、`friend class Y<int>;`——指名已有的类。

这些形式的友元声明附属于**被指名实体**所附属的模块。否则，在模块 M 中写 `friend void ::g();`（`::g` 来自全局模块片段）会按 ¶7.3 附属于 M，与 `::g` 的附属冲突，导致合法的代码变成非良构。

而 `friend void h(S);`（非限定名）和 `friend class X;`（既无限定也无模板实参的 *elaborated-type-specifier*）可能引入新实体，按 ¶7.3 附属于当前模块。

```cpp title="gfr.h"
void gfr();
```

```cpp title="M2.cppm" ok
module;
#include "gfr.h"               // 全局模块片段：gfr 附属于全局模块
export module M2;
export struct S {
  friend void ::gfr();         // ¶7.1：限定名友元，附属于 ::gfr 所附属的全局模块
  friend void hid(S) {}        // ¶7.3：可能引入新函数，附属于 M2
};
```

### 附属的后果：实体附属于模块

[[basic.link#10]] 的结论是：一个实体的所有声明都附属于同一个模块，于是可以说**实体**附属于那个模块。由此：

- 附属于具名模块 M 的 inline 函数/变量，必须在声明它的每个定义域中给出定义（[[dcl.inline#5]]）。
- 附属于具名模块的类，其类内定义的成员函数**不是**隐式 inline 的（[[class.mfct#1]]）——它在模块的目标文件中只有一份强定义，导入者调用它是普通的外部调用。这让修改成员函数体不会改变模块接口的 ABI。

## 隐式导入主接口单元（¶8）

¶8 既不含 `export` 也不含分区名的 *module-declaration*（即普通实现单元 `module M;`）**隐式导入**主模块接口单元，如同写了 `import M;`。

为什么只对普通实现单元这样做？

- 普通实现单元的典型用途就是"实现接口中声明的东西"，它总是需要主接口。
- 分区（无论接口还是实现）**不**隐式导入主接口，因为主接口通常要导入分区——如果分区反过来隐式导入主接口，就形成循环接口依赖（[[module.import#10]]）。

¶8 Example 2（加注）：

```cpp title="TU #1：B-Y.cppm"
module B:Y;                     // 不隐式导入 B
int y();
```

```cpp title="TU #2：B.cppm"
export module B;
import :Y;                      // OK：没有形成接口依赖环
int n = y();
```

```cpp title="TU #3：B-X1.cppm" error
module B:X1;                    // 不隐式导入 B
int &a = n;                     // error: n 在这里不可见
```

```cpp title="TU #4：B-X2.cppm" ok
module B:X2;                    // 不隐式导入 B
import B;                       // 分区可以显式导入主接口（只要不成环）
int &b = n;                     // OK
```

```cpp title="TU #5：B.cpp" ok
module B;                       // 隐式导入 B
int &c = n;                     // OK
```

注意 TU #4：分区 `B:X2` 显式导入了 B。这只在主接口单元 B 没有（直接或间接）导入 `B:X2` 时才合法，否则构成循环。注意 `n` 虽然没有导出，但 TU #4 和 TU #5 与 B 属于同一模块，模块链接的名字在同一模块的导入者中可见（[[basic.lookup#2]] 的 ¶2.3）。

## 实现视角

!!! impl "模块单元与目标文件"
    - 每个模块单元仍然是一个独立的 TU，产出一个目标文件。接口单元（含接口分区和实现分区）还额外产出一个 BMI 供导入者使用；普通实现单元不能被导入，所以不产出 BMI。
    - Clang 通过文件扩展名 `.cppm` 或 `-x c++-module` 识别模块接口单元；实现分区在 Clang 中也需要按"模块单元"编译以产出 BMI。各编译器的命令行细节见 [[toolchain/modules-in-practice]]。
    - **分区不出现在实体修饰名中**：在模块 `greet` 的分区 `:fmt` 中声明的 `greet::bracket`，符号是 `__ZN5greetW5greet7bracketE...`，与在主接口中声明没有区别。这与 Note 1"分区划分对外不可见"一致——把一个声明从一个分区挪到另一个分区，不改变 ABI。分区名只出现在**模块初始化函数**的符号中（如 `__ZGIW5greetWP3fmt`）。
    - Itanium ABI 的模块修饰：`W <模块名>` 标记附属，带点的模块名逐段编码（本机实测 `export module a.b;` 中的 `f` 为 `__ZW1aW1b1fv`）；分区用 `WP`。这种修饰体现的是"强所有权"（strong ownership）模型：附属于不同模块的同名实体是不同的符号。Itanium ABI 的这套修饰也被 GCC 采用；MSVC 有自己的方案。

## 历史与演进

!!! history "C++20 → 现在"
    - C++20 [[P1103R3]] 引入模块单元、分区、全局模块片段与附属的概念。Modules TS 时期并没有分区，也没有全局模块片段的显式语法（`module;`），这两者来自与 Clang 方面的提案合并。
    - "强所有权"与"弱所有权"之争：早期讨论中，模块中导出的实体是否应该与全局模块中的同名实体是同一个，一度存在分歧（弱所有权：导出实体的符号不含模块名）。现行标准的 [[basic.link#8]] ¶8.3 + ¶7 采用的是强所有权语义，`extern "C++"` 作为显式逃生口。
    - C++26：模块声明中的模块名不得由宏展开得到（[[cpp.module#1]]），以便构建系统做依赖扫描。

## 陷阱

!!! pitfall "模块名中的点不表示层次"
    `import a;` 不会导入 `a.b`，`a.b` 也不能访问 `a` 的模块链接实体——它们是两个毫不相干的模块。若想让 `a` 提供 `a.b` 的内容，需要在 `a` 中写 `export import a.b;`。

!!! pitfall "模块名不是命名空间"
    `export module math; export int add(int, int);` 之后，导入者写的是 `add(1, 2)`，不是 `math::add(1, 2)`。想要命名空间就自己写 `export namespace math { ... }`。

!!! pitfall "实现单元不能被导入"
    把公共辅助函数放进 `module M;` 的普通实现单元，然后期望其他单元 `import` 它——不行。普通实现单元没有名字可以导入。要共享就用实现分区 `module M:helpers;`。

!!! pitfall "同一模块有两个主接口单元"
    构建系统里两个文件都写了 `export module M;`（比如复制粘贴后忘了改名），这是 IFNDR，编译器不必报错。Clang 的单个 TU 视角无法发现它；依赖扫描之后构建系统才有机会发现：本机用 CMake 3.29 + Ninja 构建两个都声明 `export module M;` 的文件，Ninja 报告 `multiple rules generate CMakeFiles/dup.dir/M.pcm` 并停止。

## 思考题

!!! question "思考题 1"
    下面这个模块单元中，各声明附属于哪个模块？哪些名字有模块链接？

    ```cpp
    module;
    #include <cstddef>
    export module M;
    namespace util {
      using index = std::size_t;
      std::size_t count();
      export int version();
    }
    namespace { int secret; }
    extern "C++" void legacy();
    ```

<details markdown="1">
<summary>答案</summary>

- `<cstddef>` 中的声明：附属于全局模块（全局模块片段属于全局模块，¶6）。
- `namespace util`：命名空间有外部链接，附属于全局模块（¶7.2.1）。
- `util::index`：类型别名，附属于全局模块（¶7.2.2）；别名名字本身没有链接。
- `util::count`：附属于 M（¶7.3），未导出 → **模块链接**。
- `util::version`：附属于 M，导出 → 外部链接。
- 无名命名空间：内部链接，不满足 ¶7.2.1 → 附属于 M（¶7.3）；`secret` 也附属于 M，内部链接（[[basic.link#4]] ¶4.9）。
- `legacy`：在语言链接规范中 → 附属于全局模块（¶7.2.4），外部链接。
</details>

!!! question "思考题 2"
    为什么接口分区不隐式导入主接口单元，而普通实现单元却会？如果分区 `M:P` 也隐式导入 M，会发生什么？

<details markdown="1">
<summary>答案</summary>

接口分区必须被主接口单元（直接或间接）`export import`（¶3）。如果 `M:P` 隐式导入 M，那么 M → M:P → M 形成**接口依赖环**，违反 [[module.import#10]]，所有带接口分区的模块都将非良构。实现分区也常被主接口导入（用于内部实现细节），同理不能隐式导入。普通实现单元不能被任何单元导入（没有分区名就无法 `import`），所以它隐式导入主接口不会成环。
</details>

!!! question "思考题 3"
    `export module M;` 中 `struct S { void f() {} };` 的 `f` 与普通头文件中 `struct S { void f() {} };` 的 `f` 在 inline 性质上有什么不同？这对二进制兼容性意味着什么？

<details markdown="1">
<summary>答案</summary>

在具名模块中，`S` 附属于 M，类内定义的 `f` **不是**隐式 inline 的（[[class.mfct#1]] 只对附属于全局模块的成员函数规定隐式 inline）。所以 `f` 只在 M 的目标文件中有一个强定义（`nm -m` 显示为 `external` 而非 `weak external`），导入者对它的调用是普通外部调用。修改 `f` 的函数体只需重新编译模块 M 的目标文件，导入者无需重编（尽管构建系统未必能利用这一点）。在头文件中则 `f` 是 inline 的，函数体是每个包含者的一部分。若确实希望 inline，在模块中显式写 `inline`。
</details>

## 小结

| 概念 | 定义 | 段落 |
|---|---|---|
| 模块单元 | 含 *module-declaration* 的 TU | ¶1 |
| 具名模块 | 同名模块单元的集合 | ¶1 |
| 保留模块名 | `std`+数字开头、或含保留标识符；IFNDR | ¶1 |
| 接口单元 / 实现单元 | 有无 `export` | ¶2 |
| 主模块接口单元 | 无分区名的接口单元，恰好一个（IFNDR） | ¶2 |
| 分区 | 有 `:P`；不得重名；接口分区必须被导出（IFNDR） | ¶3 |
| 管辖范围 | *module-declaration* 到 TU 末尾 | ¶5 |
| 全局模块 | 全局模块片段 + 非模块 TU | ¶6 |
| 附属 | 指名已有实体的友元随被指名者；命名空间/别名/语言链接块 → 全局模块；其余随管辖范围 | ¶7 |
| 隐式导入 | 仅普通实现单元隐式导入主接口 | ¶8 |
