---
title: 模块
summary: 第 10 章导读：C++20 模块解决了 #include 的哪些问题，以及模块单元、分区、全局模块、附属、导出、可见与可达这些概念怎样配合。
status: done
since: c++20
papers: P1103R3, P1815R2, P2465R3
related: module.unit, module.interface, module.import, module.global.frag, module.private.frag, module.context, module.reach, basic.link, basic.def.odr, toolchain/modules-in-practice
tags: 导读, 模块
updated: 2026-10-19
---

!!! tldr
    - `#include` 是文本粘贴，带来三个问题：宏在头文件和使用者之间互相渗透，同一个头文件被每个源文件重复解析，所有库的名字挤在一起。模块分别回答了这三个问题。
    - 导入一个具名模块不会带进任何宏，导入者的宏也影响不到模块；只有头文件单元 `import "x.h";` 会带进宏。
    - 每个声明都附属于一个模块。两个模块里同名的非导出函数是两个不同的函数，不会在链接时冲突。
    - 导出决定名字能不能被导入者找到（可见），可达决定定义等语义信息能不能被用到。一个类型没有导出，仍然可以通过导出的别名来使用。
    - 模块不是命名空间：`export module foo;` 不会创建 `foo::`。

## 宏不再穿过边界

```cpp title="counter.cppm"
module;
#include <cstddef>
export module counter;
#define COUNTER_MAX 100            // 只在这个翻译单元里有效
export class Counter {
  std::size_t n = 0;
public:
  bool tick() { return ++n < COUNTER_MAX; }
  std::size_t value() const { return n; }
};
```

```cpp title="main.cpp" ok
#define value oops                 // 不影响 counter 模块里的 value
import counter;
#undef value
#ifdef COUNTER_MAX
#  error "macro leaked"            // 不会触发：具名模块不导出宏
#endif
int main() {
  Counter c;
  while (c.tick()) {}
  return c.value() == 100 ? 0 : 1;
}
```

本机 Clang 23 先把 `counter.cppm` 预编译成模块文件，再编译 `main.cpp`，程序正常返回 0。如果 `counter` 是一个用 `#include` 包含的头文件，结果完全不同：`main.cpp` 里的 `#define value oops` 会把头文件中的 `value()` 改名，头文件里的 `COUNTER_MAX` 也会泄漏到 `main.cpp`。

`#include` 是文本粘贴：预处理器把头文件的内容原样插到当前位置，编译器再把结果当作一个大源文件处理。头文件的含义因此依赖于包含它之前定义了哪些宏、包含的顺序如何。同一个头文件在两个翻译单元（单独编译的一个源文件，连同它包含的头文件）里，可能因为宏不同而展开成不同的代码，这是违反 ODR（同一实体的定义必须处处相同，[[basic.def.odr#16]]）最常见的来源。

模块切断了这条通道。模块单元单独翻译，导入者拿到的是它翻译好的结果，而不是源文本。按 [[module.import#5]] 注 4 和 [[module.import#7]] 注 6，导入具名模块不会让任何宏可用。需要宏的地方，比如配置开关和 `assert`，仍然可以用 `#include`，或者导入头文件单元 `import "config.h";`，它是唯一会带入宏的导入（[[cpp.import]]）。

## 每个模块只翻译一次

一个包含 `<vector>`、`<string>`、`<algorithm>` 的源文件，编译器要重新解析几万行标准库代码；一个项目有一千个源文件，就重复一千遍。预编译头缓解了这个问题，但它要求所有源文件共享同一段开头，语义上仍是文本包含。

模块接口单元只翻译一次，产出一个二进制模块接口文件（BMI；Clang 叫 `.pcm`，GCC 叫 `.gcm`，MSVC 叫 `.ifc`），导入者直接读取其中序列化好的声明。标准本身不提 BMI，只规定导入让哪些声明可以被找到、可以被用到。但模块的语义，不受导入者的宏影响、与导入顺序无关，正是为了让这种实现可行而设计的。实际的构建方式和效果见 [[toolchain/modules-in-practice]]。

## 名字归属于模块

```cpp title="M.cppm"
export module M;
int helper() { return 1; }          // 未导出
export int f() { return helper(); }
```

在头文件模型下，两个库各自定义一个 `int helper();`，链接时要么符号冲突，要么链接器悄悄选一个，程序违反 ODR 而且不要求诊断。

模块引入了**附属**（[[g:attached|attachment]]）：每个声明都附属于某个模块（[[module.unit#7]]），附属于不同模块的同名实体是不同的实体（[[basic.link#8]] 第 8.3 项）。上面的 `helper` 没有导出，它具有**模块链接**（[[g:module-linkage|module linkage]]），只有模块 `M` 的其他单元能用这个名字指代它。

Clang 和 GCC 把模块名编码进附属于具名模块的符号名。本机 Clang 23 编译上面的模块，`helper` 的符号是 `_ZW1M6helperv`，导出的 `f` 是 `_ZW1M1fv`，其中 `W1M` 表示模块 `M`。所以在链接器看来，另一个模块里的 `helper` 是另一个符号。

!!! note "模块不是什么"
    - 模块不是命名空间。`export module foo;` 不会创建 `foo::` 作用域，名字仍然在你写的命名空间里。模块管可见性和归属，命名空间管名字的作用域，两者互不相干。
    - 模块不是访问控制。未导出的声明，导入者用名字找不到，但它的定义仍可能起作用，例如通过导出的别名或函数的返回类型被用到（见下文的可达）。
    - 模块不规定文件名、目录结构或构建方式。`.cppm`、`.ixx` 这些扩展名都是工具链的约定。

## 模块单元的四种形态

```cpp title="geo.cppm"
export module geo;         // 主模块接口单元
export import :shapes;     // 接口分区必须由主接口单元导出
export double area_sum();
```

```cpp title="geo-shapes.cppm"
export module geo:shapes;  // 接口分区
export struct Circle { double r; };
```

```cpp title="geo-detail.cppm"
module geo:detail;         // 实现分区
constexpr double pi = 3.14159265358979;
```

```cpp title="geo.cpp"
module geo;                // 实现单元，隐式导入 geo
import :detail;            // 实现分区只在模块内部导入
double area_sum() { return pi * Circle{1}.r * Circle{1}.r; }
```

一个翻译单元如果以 `export module M;`、`module M;` 这样的**模块声明**开头（前面可以有全局模块片段），就是一个[[g:module-unit|模块单元]]，否则是普通的翻译单元。模块单元按两个维度分类（[[module.unit]]）：

| | 没有分区名 | 有分区名 `:P` |
|---|---|---|
| 接口单元 `export module …` | 主模块接口单元，每个模块恰好一个 | 接口分区，必须由主接口单元直接或间接地 `export import` |
| 实现单元 `module …` | 实现单元，隐式导入主接口单元，不能被导入 | 实现分区，模块内其他单元可以导入，不对外 |

同名的全部模块单元合起来叫做一个[[g:named-module|具名模块]]。不属于任何具名模块的部分组成[[g:global-module|全局模块]]：所有普通翻译单元，以及每个模块单元开头的全局模块片段。全局模块没有名字，也没有接口单元。头文件单元也是普通翻译单元，其中的声明附属于全局模块。

声明一般附属于它所在的那个模块。几类例外附属于全局模块：具有外部链接的命名空间、类型别名、命名空间别名，以及写在 `extern "C"`、`extern "C++"` 块里的声明（[[module.unit#7]]）。所以模块可以用 `extern "C++"` 块声明与旧代码共享的实体。

## 导出、可见与可达

```cpp title="A.cppm"
export module A;
struct X {};
export using Y = X;
```

```cpp title="use.cpp" error
import A;
Y y;   // OK：X 的定义可达
X x;   // error: X 不可见
```

这是 [[module.reach#6]] 的例子，本机 Clang 23 对第 3 行报 `unknown type name 'X'`。它说明模块里有两件不同的事：

- **可见**：名字查找能不能找到这个声明。标准的正式说法是声明先于（precedes）这个程序点（[[basic.lookup#2]]）。对导入者来说，只有导出的声明可见。`X` 没有导出，写出名字 `X` 就找不到。
- **可达**：声明带来的语义信息，例如类的定义、默认实参，在这一点能不能起作用（[[module.reach]]）。被导入的翻译单元里，未导出的声明一般也是可达的。`Y` 是 `X` 的别名，用 `Y` 声明变量时需要 `X` 的完整定义，而这个定义可达，所以 `Y y;` 合法。

**导出**（[[module.interface]]）就是用 `export` 修饰声明，让导入者能找到它。导出的名字永远不具有模块链接。**导入**（[[module.import]]）决定当前翻译单元导入哪些翻译单元，`export import` 会把导入关系传递给下游。

## 两个特殊片段

```cpp title="hello.cppm"
module;                    // 全局模块片段开始
#include <cstdio>          // 这里只能写预处理指令
export module hello;       // 从这里起是模块 hello 的范围
export void greet();
module :private;           // 私有模块片段
void greet() { std::puts("hi"); }
```

- **全局模块片段**（[[g:global-module-fragment|global module fragment]]，[[module.global.frag]]）：`module;` 与模块声明之间的部分，用来 `#include` 还没有模块化的头文件。其中的声明附属于全局模块，模块没有用到的那些会被丢弃。
- **私有模块片段**（[[g:private-module-fragment|private module fragment]]，[[module.private.frag]]）：`module :private;` 之后的部分对导入者不可达。它只能出现在主接口单元里，而且这个模块只能有这一个单元。它让单文件模块可以把实现和接口写在一起，同时保证这部分实现不会影响其他翻译单元的行为。

## 各节内容

| 节 | 条款 | 内容 |
|---|---|---|
| 10.1 | [[module.unit]] | 模块单元的种类，模块名的保留规则，模块的范围（purview），全局模块，声明附属于哪个模块 |
| 10.2 | [[module.interface]] | `export` 能写在哪里，哪些声明能导出，导出与链接的关系 |
| 10.3 | [[module.import]] | `import` 导入哪些翻译单元，分区和头文件单元，`export import` 的传递，禁止循环导入 |
| 10.4 | [[module.global.frag]] | 全局模块片段，哪些声明会被丢弃 |
| 10.5 | [[module.private.frag]] | 私有模块片段 |
| 10.6 | [[module.context]] | 模板跨模块实例化时到哪里查找名字 |
| 10.7 | [[module.reach]] | 哪些翻译单元、哪些声明可达，可达与可见的区别 |

模块的不少规则写在第 10 章以外：

| 主题 | 位置 |
|---|---|
| 模块链接，附属与同一实体的判定 | [[basic.link#4]]、[[basic.link#8]]、[[basic.link#10]] |
| TU-local 实体与暴露 | [[basic.link#14]]–[[basic.link#18]] |
| 附属于具名模块的 inline 函数和变量的定义位置 | [[dcl.inline#5]] |
| 具名模块里类内定义的成员函数不再隐式 inline | [[class.mfct#1]] |
| 名字查找中先于的定义 | [[basic.lookup#2]] |
| ADL 能找到导出但不可见的函数 | [[basic.lookup.argdep#4]] |
| 实例化点 | [[temp.point]] |
| `module`、`import`、`export` 作为预处理指令 | [[cpp.module]]、[[cpp.import]]、[[cpp.pre]] |
| 标准库模块 `std` 与 `std.compat` | [[std.modules]] |

## 历史与演进

!!! history
    - Modules TS 于 2018 年发布。在此之前，Clang 基于 module map 的头文件模块和 MSVC 的早期实现已经积累了经验。
    - C++20：[[P1103R3]] 把 Modules TS 与 Clang 一方的提案合并进标准，引入了全局模块片段、分区、头文件单元和宏的导入规则。随后的提案补上了细节：[[P1815R2]] 引入 TU-local 实体与暴露；[[P1779R3]] 规定具名模块里类内定义的成员函数不再隐式 inline；[[P1857R3]] 把 `module`、`import` 改成构建系统可以低成本扫描的预处理指令。
    - C++23：[[P2465R3]] 引入标准库模块 `std` 和 `std.compat`。[[P2615R1]] 作为缺陷报告收紧了 `export` 能修饰的声明，例如不能导出偏特化。
    - C++26：模块名不能再由宏展开得到（[[cpp.module]]）。
