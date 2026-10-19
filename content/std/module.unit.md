---
title: 模块单元与模块范围
summary: 一个模块由哪些翻译单元组成（接口单元、实现单元、分区），模块名有哪些限制，以及每个声明附属于哪个模块。
status: done
since: c++20
papers: P1103R3
related: module, module.interface, module.import, module.global.frag, basic.link, cpp.module, history/modules, toolchain/modules-in-practice
tags: 模块, 附属, 分区
updated: 2026-10-19
---

!!! tldr
    - 以 `module` 声明开头的翻译单元是模块单元；同名的模块单元合起来就是一个具名模块，模块名里的点没有层次含义。
    - 带 `export` 的是接口单元，不带的是实现单元；带 `:名字` 的是分区。每个模块恰好有一个不带分区名的接口单元，即主接口单元。
    - 只有普通实现单元 `module M;` 会隐式导入主接口单元，分区不会，否则会形成导入环。
    - 每个声明都附属于一个模块：默认是它所在的模块，命名空间、别名和 `extern "C++"`/`extern "C"` 中的声明附属于全局模块。
    - 附属决定了两个声明是不是同一实体，也决定了符号修饰名。导出只改变链接，不改变附属。

## 一个模块由哪些文件组成

```cpp title="A.cppm（主接口单元）"
export module A;
export import :Foo;   // 主接口必须导出接口分区 A:Foo
export int baz();
```

```cpp title="A-Foo.cppm（接口分区）"
export module A:Foo;
import :Internals;    // 导入本模块的实现分区
export int foo() { return 2 * (bar() + 1); }
```

```cpp title="A-Internals.cppm（实现分区）"
module A:Internals;
int bar();            // 没有导出：只能在模块 A 内部使用
```

```cpp title="A.cpp（实现单元）"
module A;             // 隐式导入主接口，所以 baz 可见
import :Internals;
int bar() { return baz() - 10; }
int baz() { return 30; }
```

```cpp title="main.cpp" ok
import A;
int main() { return foo() + baz(); }   // 2*(20+1) + 30 = 72
```

这是标准 ¶4 的例子加上一个使用者。本机 Clang 23 按 `A-Internals → A-Foo → A → (A.cpp, main.cpp)` 的顺序编译、链接后，程序返回 72。在 `main.cpp` 里调用 `bar()` 会报 "use of undeclared identifier"：`bar` 没有导出，`main.cpp` 也不属于模块 A。

每个文件开头的那一行叫**模块声明**（*module-declaration*）：

```text
module-declaration:
    export-keyword(opt) module-keyword module-name module-partition(opt) attribute-specifier-seq(opt) ;
```

¶1 含有模块声明的翻译单元（TU，单独编译的一个源文件连同它包含的头文件，见 [[lex.phases]]）是[[g:module-unit|模块单元]]（module unit）。模块名相同的所有模块单元合起来叫**具名模块**（named module）。

标准里没有一个独立的模块对象，模块就是同名模块单元的集合。哪些文件一起编译、链接，由构建系统决定；标准只用几条不要求诊断的规则约束这个集合（见下文）。

¶2 模块声明以 `export` 开头的是**模块接口单元**（module interface unit），其余的是**模块实现单元**（module implementation unit）。¶3 模块声明带有 `:名字` 的是[[g:module-partition|模块分区]]（module partition）。两个维度组合出四种单元：

| 模块声明 | 种类 | 例子中的文件 | 能否被导入 |
|---|---|---|---|
| `export module A;` | 主模块接口单元 | `A.cppm` | 能：`import A;` |
| `export module A:Foo;` | 接口分区 | `A-Foo.cppm` | 只能在模块内：`import :Foo;` |
| `module A:Internals;` | 实现分区 | `A-Internals.cppm` | 只能在模块内：`import :Internals;` |
| `module A;` | 实现单元 | `A.cpp` | 不能（没有名字可导入） |

¶4 标准对这个例子的说明是：`A:Foo` 构成模块 A 接口的一部分，`A:Internals` 对 A 的外部接口没有贡献，`A.cpp` 没有分区名所以不能被导入。

!!! impl "实现分区的警告"
    Clang 23 对 `A-Foo.cppm` 里的 `import :Internals;` 给出警告 `-Wimport-implementation-partition-unit-in-interface-unit`："Names from A:Internals may not be reachable"。标准不要求这个警告。它提醒的是，导入者对实现分区的可达性是未指明的（[[module.reach#2]]），依赖其中的定义不可移植。

## 模块名

`module` 和 `import` 不是关键字。预处理器在行首识别出模块指令后，把 `export`、`module` 换成特殊记号 *export-keyword*、*module-keyword*（[[cpp.module#2]]），所以模块声明必须单独占据一行的开头，`int module = 0;` 仍然合法。

模块名中的点没有语义。`a.b` 只是一个带点的名字，与模块 `a` 没有父子关系：`import a;` 不会导入 `a.b`，`a.b` 也看不到 `a` 中未导出的东西。分区名同样可以带点（`:detail.io`），也没有层次。

模块名不能来自宏。名字中的标识符在预处理时不得是对象式宏，也不得后跟 `(`（[[cpp.module#1]]）。这样构建系统不必完整地复现所有宏定义，就能扫描出一个文件属于哪个模块。

¶1 对名字本身还有两条限制：

<div class="compare" markdown="1">

```cpp title="bad.cppm" error
export module my.import;
// error: import 不能
// 出现在模块名中
```

```cpp title="reserved.cppm" ifndr
export module std2.util;
// 保留名：std 后跟数字开头
// 不要求诊断
```

</div>

- `module` 和 `import` 不得作为模块名或分区名的组成部分，违反时必须诊断。以 `import` 开头的行会被当作导入指令，名字里出现这两个词会干扰扫描。
- 以 `std` 后跟零个或多个数字开头的名字（`std`、`std.core`、`std23.x`），以及含有保留标识符（[[lex.name]]，如 `__foo`、`_Foo`）的名字，都是保留的，不得用在模块声明中，不要求诊断。含保留标识符的名字留给实现，其余留给未来的标准（标准库已经占用了 `std` 和 `std.compat`，见 [[std.modules]]）。

`stdx` 不是保留名，因为 `x` 不是数字。

为什么保留名只是不要求诊断？标准库自己的 `std` 模块就是用 `export module std;` 写成的（libc++ 的 `std.cppm`、MSVC 的 `std.ixx`）。如果要求诊断，实现就得区分这一行是用户写的还是自己提供的，这超出了语言本身。

!!! impl "本机诊断"
    Clang 23 对 `std`、`std2.util`、`__impl` 只给出 `-Wreserved-module-identifier` 警告，对 `stdx` 不给任何诊断；对 `my.import`、`a.module` 报错 "is an invalid name for a module"。libc++ 的 `std.cppm` 因此需要加 `-Wno-reserved-module-identifier` 编译。

模块声明末尾可以带属性，它属于这个模块声明。标准没有定义可以用在这里的属性。

## 主接口单元与分区的约束（¶2–¶3）

¶2 一个具名模块必须恰好有一个不带分区名的接口单元，叫做[[g:primary-module-interface-unit|主模块接口单元]]（primary module interface unit）。¶3 同一模块不能有两个同名分区，所有接口分区都必须由主接口单元直接或间接地导出（`export import :Foo;`）。

这三条都是不要求诊断的（{{ifndr}}），因为编译器一次只看一个 TU，无法知道别处是否还有第二个 `export module M;`，也无法知道某个分区有没有被导出。这类错误只有构建系统有机会发现。

!!! impl "两个主接口单元"
    本机用 CMake 3.29 + Ninja 构建两个都写了 `export module M;` 的文件，Ninja 报告 `multiple rules generate CMakeFiles/dup.dir/M.pcm` 并停止。单独编译任何一个文件，Clang 都不会报错。

注 1 指出，分区只能被同一模块的其他单元导入，模块划分成哪些单元对模块外部不可见。`import :P;` 中的分区名总是相对于当前模块，没有语法能导入别的模块的分区。导入者只看到模块 A，不知道 `A:Foo` 的存在。

分区解决了两个问题：大模块的接口可以拆成多个文件；模块内部可以共享声明，而不必退回到内部头文件。两种分区的区别：

| | 接口分区 `export module M:P;` | 实现分区 `module M:P;` |
|---|---|---|
| 能否含 `export` 声明 | 能 | 不能（[[module.interface#1]]） |
| 主接口是否必须导出它 | 必须（¶3） | 不能导出（[[module.import#8]]） |
| 典型用途 | 把接口拆成多个文件 | 模块内部共享的声明 |
| 是否隐式导入主接口 | 否（¶8） | 否（¶8） |

主接口单元还有几处特殊地位：私有模块片段只能出现在它里面（[[module.private.frag]]）；它的末尾是模板实例化语境中的一个特殊点（[[module.context#3]]）。

## 实现单元隐式导入主接口（¶8）

¶8 既不带 `export` 也不带分区名的模块声明，也就是 `module M;`，隐式导入主模块接口单元，如同写了 `import M;`。

分区不这样做，因为主接口通常要导入分区。如果分区反过来隐式导入主接口，就形成了导入环，而导入环是禁止的（[[module.import#10]]）。标准的例 2：

```cpp title="B-Y.cppm"
module B:Y;               // 不隐式导入 B
int y();
```

```cpp title="B.cppm"
export module B;
import :Y;                // OK：没有形成环
int n = y();
```

```cpp title="B-X1.cppm" error
module B:X1;              // 不隐式导入 B
int &a = n;               // error: n 在这里不可见
```

```cpp title="B-X2.cppm" ok
module B:X2;
import B;                 // 分区可以显式导入主接口，只要 B 没有导入 B:X2
int &b = n;               // OK
```

```cpp title="B.cpp" ok
module B;                 // 隐式导入 B
int &c = n;               // OK
```

`n` 没有导出，`B:X2` 和 `B.cpp` 却能使用它：它们与 `B.cppm` 属于同一个模块，同一模块内未导出的名字在导入后也可见（[[basic.lookup#2]]）。本机 Clang 23 对这五个单元的判定与注释一致。

## 管辖范围与全局模块（¶5–¶6）

¶5 从模块声明开始到 TU 末尾的这段记号叫**模块单元管辖范围**（module unit purview）。模块 M 所有单元的管辖范围合起来，就是 M 的[[g:purview|管辖范围]]。

```cpp
module;                   // 全局模块片段：不在 M 的管辖范围中
#include <cstdio>
export module M;          // M 的管辖范围从这里开始
int f();
module :private;          // 私有模块片段：仍在管辖范围中
```

模块声明之前的全局模块片段（[[module.global.frag]]）不在 M 的管辖范围中；之后的私有模块片段在。很多规则以管辖范围为条件，例如 `export` 只能出现在接口单元的管辖范围中（[[module.interface#1]]），接口单元管辖范围中的 `const` 变量不再默认具有内部链接（[[basic.link#3]]）。

¶6 所有全局模块片段，加上所有不是模块单元的 TU，构成[[g:global-module|全局模块]]（global module）。这些地方的声明在全局模块的管辖范围中。注 2 补充，全局模块没有名字，没有接口单元，也不由任何模块声明引入。

这条定义让 C++20 之前的全部代码都有了归属：传统 `.cpp` 文件和它包含的头文件里的声明，都在全局模块中。头文件单元（[[module.import#5]]）不是模块单元，也属于全局模块。两个不相关的 TU 都写了 `int f();`，声明的是同一个 `f`，因为它们在同一个模块（全局模块）中，这正是向后兼容所需要的。

## 声明附属于哪个模块（¶7）

¶7 **模块**指具名模块或全局模块。每个声明都**附属于**（attached to）一个模块。附属决定了两个声明是否声明同一实体：两个具有外部链接或模块链接的声明，只有附属于同一模块时才可能是同一实体（[[basic.link#8]]）。

```cpp title="M.cppm" ok
export module M;
int f1() { return 1; }                 // 附属于 M，模块链接
export int f2() { return 2; }          // 附属于 M，外部链接
extern "C++" int f3() { return 3; }    // 附属于全局模块
extern "C++" { export int f4() { return 4; } }   // 附属于全局模块，且被导出
extern "C" int f5() { return 5; }      // 附属于全局模块，C 语言链接
namespace N { int g() { return 6; } }  // N 附属于全局模块，N::g 附属于 M
export struct S { friend int h(S) { return 7; } };   // h 附属于 M
export int use() { return f1() + N::g() + h(S{}); }
```

本机 Clang 23 编译这个接口单元，用 `nm` 查看目标文件（Mach-O，经 `llvm-cxxfilt` 解码）：

| 声明 | 符号 | 解码后 |
|---|---|---|
| `f1`（未导出） | `__ZW1M2f1v` | `f1@M()` |
| `f2`（导出） | `__ZW1M2f2v` | `f2@M()` |
| `f3`（`extern "C++"`） | `__Z2f3v` | `f3()` |
| `f4`（`extern "C++"`，导出） | `__Z2f4v` | `f4()` |
| `f5`（`extern "C"`） | `_f5` | |
| `N::g` | `__ZN1NW1M1gEv` | `N::g@M()` |
| 友元 `h` | `__ZW1M1hS_1S` | `h@M(S@M)` |

`f1` 和 `f2` 的符号都带 `W1M`：修饰名反映附属，不反映是否导出。`extern "C++"` 去掉了模块标记。命名空间 `N` 本身没有模块标记，它的成员 `g` 有。下面分三种情况说明这些结果。

### 默认：附属于所在的模块（¶7.3）

¶7.3 不属于下面两种特殊情况的声明，附属于它所在管辖范围对应的模块。`export module M;` 之后写的函数、类、变量、模板都附属于 M；全局模块片段和普通 TU 里写的，附属于全局模块。

导出与否不影响附属。`export int f2();` 和 `int f1();` 都附属于 M，区别只在链接：前者是外部链接，后者是模块链接（[[basic.link#4]]）。以为导出的东西属于全局，是常见的误解。

### 命名空间、别名与语言链接块附属于全局模块（¶7.2）

¶7.2 下面四种声明附属于全局模块：

- ¶7.2.1 声明具有外部链接的命名空间。命名空间是开放的，许多模块和普通代码都会向 `namespace std`、`namespace util` 添加成员。如果命名空间附属于某个模块，两个模块的 `namespace util` 就成了两个不同的命名空间。所以命名空间本身附属于全局模块，成员各按各的规则。无名命名空间具有内部链接，不在此列。
- ¶7.2.2、¶7.2.3 声明类型别名或命名空间别名。别名不引入新实体，两个模块为同一类型声明同名别名不应冲突（[[basic.link#8]] 的 ¶8.2）。
- ¶7.2.4 出现在语言链接规范（*linkage-specification*，即 `extern "C"` 或 `extern "C++"`，见 [[dcl.link]]）之内。

最后一种是在模块代码里显式选择全局模块的唯一手段。`extern "C"` 的理由很直接：C 函数没有模块的概念。`extern "C++"` 则是 C++20 为模块赋予的新用途，它用来声明头文件里也声明过的实体，或者在把代码库迁移到模块时保持符号名不变。

### 指名已有实体的友元（¶7.1）

¶7.1 非依赖的友元声明如果属于下面两种形式之一，就附属于被指名的那个实体所附属的模块：

- 指名函数，且声明符是限定名（`friend void ::g();`、`friend void N::g();`）或模板标识（`friend void g<>(int);`）；
- 指名类，且不是用既无限定也无模板实参的 `class X` 这种形式（例如 `friend X;`、`friend class N::X;`、`friend class Y<int>;`）。

这些形式必然指名一个已有的实体。如果没有 ¶7.1，在模块 M 里写 `friend void ::gfr();` 会按 ¶7.3 附属于 M，与 `::gfr` 原来的附属冲突，本应合法的代码就成了非良构。

```cpp title="M2.cppm" ok
module;
#include "gfr.h"               // void gfr();  附属于全局模块
export module M2;
export struct S {
  friend void ::gfr();         // ¶7.1：随 ::gfr 附属于全局模块
  friend void hid(S) {}        // ¶7.3：可能引入新函数，附属于 M2
};
```

非限定的 `friend void hid(S);` 和 `friend class X;` 可能引入新实体，按 ¶7.3 附属于当前模块。

### 附属冲突

两个对应的声明（同一作用域中同名、签名相同）附属于不同模块，且一个在另一个之前时，程序非良构（[[basic.scope.scope]]，[[basic.link#10]] 的注 5）。所以在模块中重声明一个全局模块的实体，这个声明也必须附属于全局模块：

<div class="compare" markdown="1">

```cpp title="M.cppm" error
module;
#include "decls.h"  // int g();
export module M;
int g();
// error: 与 decls.h 的 g 对应，
// 但附属于 M
```

```cpp title="M.cppm" ok
module;
#include "decls.h"  // int g();
export module M;
extern "C++" int g();
// OK：附属于全局模块，
// 是 decls.h 中 g 的重声明
```

</div>

Clang 23 对左边报 "declaration of 'g' in module M follows declaration in the global module"。

由这些规则可知，一个实体的所有声明都附属于同一个模块，于是可以说这个实体附属于那个模块（[[basic.link#10]]）。附属还有两个直接后果：

- 附属于具名模块的 inline 函数或变量，必须在声明它的定义域中定义（[[dcl.inline#5]]）。
- 附属于具名模块的类，类内定义的成员函数不是隐式 inline 的（[[class.mfct#1]]）。它在模块的目标文件里只有一份强定义，修改函数体不改变模块接口。

## 实现视角

!!! impl "模块单元与目标文件"
    - 每个模块单元仍然是一个独立的 TU，产出一个目标文件。可以被导入的单元（主接口、接口分区、实现分区）还要产出一个二进制模块接口（BMI，编译器缓存的接口信息）供导入者使用；普通实现单元不能被导入，不产出 BMI。各编译器的命令行见 [[toolchain/modules-in-practice]]。
    - Itanium ABI 用 `W <模块名>` 标记附属，带点的模块名逐段编码：本机 `export module a.b;` 中的 `f` 是 `__ZW1aW1b1fv`。这种修饰体现了强所有权（strong ownership）：附属于不同模块的同名实体是不同的符号。GCC 用同一套修饰，MSVC 有自己的方案。
    - 分区不出现在实体的修饰名中。在模块 `greet` 的分区 `:fmt` 里声明的 `greet::bracket`，符号与在主接口中声明时相同，所以把声明在分区之间挪动不改变 ABI。分区名只出现在模块初始化函数的符号里（如 `__ZGIW5greetWP3fmt`）。

## 历史与演进

!!! history
    - 模块单元、分区、全局模块与附属来自 C++20 的 [[P1103R3]]，它合并了 Modules TS 和另一份设计 ATOM（[[P0947R1]]），分区来自后者。设计上的来龙去脉见 [[history/modules]]。
    - 早期讨论过弱所有权：导出实体的符号不含模块名，与全局模块中的同名实体是同一个。C++20 采用强所有权，以 `extern "C++"` 作为显式的例外。
    - 模块名不能来自宏是 [[P3034R1]] 加入的，它在 2024 年作为缺陷报告通过，也适用于 C++20、C++23。

## 常见误解

!!! pitfall "模块名就是命名空间"
    `export module math; export int add(int, int);` 之后，导入者写的是 `add(1, 2)`，不是 `math::add(1, 2)`。需要命名空间就自己写 `export namespace math { ... }`。

!!! pitfall "实现单元可以被导入"
    普通实现单元 `module M;` 没有可以导入的名字。想在模块内部共享辅助声明，用实现分区 `module M:helpers;`。

!!! pitfall "在 `export module M;` 之后 `#include` 头文件"
    这样包含进来的声明全部附属于 M，与库中定义的同名实体不再是同一个实体，常见的结果是链接时找不到定义。`#include` 要放在全局模块片段里，或改用 `import`，见 [[module.global.frag]]。

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

- `<cstddef>` 中的声明在全局模块片段里，附属于全局模块（¶6、¶7.3）。
- `namespace util` 具有外部链接，附属于全局模块（¶7.2.1）。
- `util::index` 是类型别名，附属于全局模块（¶7.2.2）。
- `util::count` 附属于 M（¶7.3），没有导出，所以是模块链接。
- `util::version` 附属于 M，导出了，所以是外部链接。
- 无名命名空间具有内部链接，不适用 ¶7.2.1，按 ¶7.3 附属于 M；`secret` 也附属于 M，具有内部链接（[[basic.link#4]]）。
- `legacy` 在语言链接规范中，附属于全局模块（¶7.2.4），外部链接。
</details>

!!! question "思考题 2"
    `export module M;` 中的 `struct S { void f() {} };` 与普通头文件中同样的代码相比，`f` 有什么不同？这对二进制兼容性意味着什么？

<details markdown="1">
<summary>答案</summary>

在具名模块中，`S` 附属于 M，类内定义的 `f` 不是隐式 inline 的，[[class.mfct#1]] 只对附属于全局模块的成员函数规定隐式 inline。本机 `nm -m` 显示它是 M 目标文件里的一个 `external` 强定义（不是 `weak external`），导入者调用它是普通的外部调用。修改 `f` 的函数体只需重新编译 M 的目标文件。在头文件中，`f` 是 inline 的，函数体是每个包含者的一部分。在模块中确实需要 inline 时，显式写 `inline`。
</details>

## 小结

| 概念 | 定义 | 段落 |
|---|---|---|
| 模块单元、具名模块 | 含模块声明的 TU；同名模块单元的集合 | ¶1 |
| 保留模块名 | `std` 加数字开头，或含保留标识符；不要求诊断 | ¶1 |
| 接口单元、实现单元 | 模块声明是否以 `export` 开头 | ¶2 |
| 主模块接口单元 | 没有分区名的接口单元，恰好一个 | ¶2 |
| 分区 | 带 `:P`；不得重名；接口分区必须被导出 | ¶3 |
| 管辖范围 | 模块声明到 TU 末尾 | ¶5 |
| 全局模块 | 全局模块片段加上所有非模块 TU | ¶6 |
| 附属 | 指名已有实体的友元随被指名者；命名空间、别名、语言链接块随全局模块；其余随所在模块 | ¶7 |
| 隐式导入 | 只有 `module M;` 隐式导入主接口 | ¶8 |
