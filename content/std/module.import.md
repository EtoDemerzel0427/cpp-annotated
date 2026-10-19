---
title: 导入声明
summary: import 能写在哪里，导入一个模块、分区或头文件单元分别导入了哪些翻译单元，再导出与传递导入，以及导入关系不能成环。
status: done
since: c++20
papers: P1103R3, P1857R3, P2465R3
related: module.unit, module.interface, module.reach, cpp.import, cpp.include, std.modules, headers, basic.lookup, toolchain/modules-in-practice
tags: 模块, 导入, 头文件单元
updated: 2026-10-19
---

!!! tldr
    - `import M;` 导入模块 M 的全部接口单元：导出的名字变得可见，其中的所有声明变得可达。`import` 不粘贴文本，也不带入宏。
    - 模块 M 自己 `import Q;` 不会让 M 的导入者看到 Q 的名字；写成 `export import Q;` 才会。同一模块的各单元之间，普通导入也会传递。
    - `import <vector>;` 或 `import "x.h";` 导入头文件单元：头文件被单独翻译一次，所有声明隐式导出，它定义的宏也会带进来。
    - 模块单元中的导入必须写在所有其他声明之前；导入关系不能成环。
    - C++23 起有标准库模块：`import std;` 提供整个标准库的名字，但不提供 `assert` 之类的宏。

## import 与 #include 的区别

```cpp title="Q.cppm"
export module Q;
export int q() { return 4; }
```

```cpp title="M.cppm"
export module M;
import Q;                 // 不导出的导入
export int m();
```

```cpp title="M.cpp" ok
module M;                 // 隐式导入 M，也就间接导入了 Q
int m() { return q(); }   // OK：q 可见
```

```cpp title="user.cpp" error
import M;                 // 只导入 M
int main() { return m(); }
int z = q();              // error: q 不可见
```

`#include` 把头文件的文本粘贴进来，包含者能看到头文件包含的一切。`import` 则不同：它让另一组已经翻译好的 TU 中的声明对当前 TU 可见或可达，可见的只是它们导出的名字。`user.cpp` 导入了 M，M 导入了 Q，但 `user.cpp` 看不到 `q`。Clang 23 报 "declaration of 'q' must be imported from module 'Q' before it is required"。

一条导入声明**导入**（imports）哪些 TU，是 [module.import] 的主题。名字查找（[[basic.lookup#2]]）和可达性（[[module.reach]]）都以这个集合为基础。

导入声明有三种形式：

```text
module-import-declaration:
    import-keyword module-name attribute-specifier-seq(opt) ;
    import-keyword module-partition attribute-specifier-seq(opt) ;
    import-keyword header-name attribute-specifier-seq(opt) ;
```

它们分别导入具名模块（`import M;`）、本模块的分区（`import :P;`）和头文件单元（`import <vector>;`、`import "config.h";`）。

和 `module` 一样，`import` 不是关键字。预处理器在一行的开头识别出 `import` 指令后，把它换成特殊记号 *import-keyword*（[[cpp.import#3]]），所以导入声明必须位于一行的开头，不能由宏展开产生。这一设计来自 [[P1857R3]]，构建系统只需做预处理，就能找出一个文件的全部模块依赖。

## 导入写在哪里（¶1）

¶1 导入声明必须栖居于全局命名空间作用域。在模块单元中，所有导入声明（包括 `export import`）必须出现在其他所有声明之前；私有模块片段中的导入也必须写在该片段的最前面。

<div class="compare" markdown="1">

```cpp title="late.cppm" error
export module L;
int x;
import Q;
// error: 模块单元中的导入
// 必须先于其他声明
```

```cpp title="late.cpp" ok
int x;
import Q;
// OK：非模块 TU 不受此约束
int main() { return q() + x; }
```

</div>

导入集中在开头，构建系统扫描依赖时只需看文件头部，编译器也可以在处理任何声明之前加载好所有依赖，不会出现同一个名字在导入前后含义不同的情况。这条规则只约束模块单元：普通 TU 往往以一串 `#include` 开头，强制顺序会让迁移非常困难。

```cpp title="ns.cpp" error
namespace N {
  import Q;               // error: 导入声明必须栖居于全局命名空间作用域
}
```

Clang 23 对 `late.cppm` 报 "imports must immediately follow the module declaration"，对 `ns.cpp` 报 "import declaration can only appear at the top level"。

导入声明末尾可以带属性，它属于这条导入声明。

## 导入了哪些翻译单元（¶2–¶4）

¶2 导入声明导入一组 TU，具体是哪些由下面几段规定。注 1 说明了导入的两个效果：被导入 TU 中导出的命名空间作用域声明，在导入者中可以被名字查找找到；被导入 TU 中的所有声明，在导入声明之后对导入者可达。

¶3 `import M;` 导入 M 的所有模块接口单元，即主接口单元和所有接口分区。

¶4 `import :P;` 只能出现在某个模块 M 的模块单元中、模块声明之后，它导入 M 的分区 `M:P`。分区名总是相对于当前模块，没有任何语法能导入其他模块的分区，所以分区对模块外不可见。

## 传递导入（¶7）

¶7 导入 TU T 时，也一并导入 T 中被导出的导入声明（`export import`）所导入的所有 TU，这些 TU 叫做由 T **导出**（exported by T）。

此外，模块 M 的某个单元导入 M 的另一个单元 U 时，还会导入 U 的管辖范围中普通导入声明所导入的所有 TU。这些规则可以层层递推。

| 导入者 | 被导入的 T 中写了 `import X;` | 被导入的 T 中写了 `export import X;` |
|---|---|---|
| 模块外的 TU | 不导入 X（X 的接口单元仍然可达，见 [[module.reach#1]]） | 导入 X |
| 同一模块的另一个单元 | 导入 X | 导入 X |

开头的例子里，`M.cpp` 隐式导入了 M 的主接口单元（[[module.unit#8]]），按第二条规则也导入了 Q，所以能调用 `q()`。同一模块的各个单元本来就是把一个整体拆成了多个文件，主接口导入的东西，实现单元理应也能用。模块外的 `user.cpp` 则只导入了 M。

再导出把一个模块的接口变成另一个模块接口的一部分：

```cpp title="R.cppm"
export module R;
export import Q;          // 导入 R 的人也导入 Q
```

```cpp title="user2.cpp" ok
import R;
int main() { return q(); }   // OK：Q 由 R 导出
```

模块名中的点没有语义（[[module.unit]]），`import lib;` 不会导入 `lib.core`。要让 `import lib;` 带入所有子模块，就写一个伞模块（umbrella module）：`export module lib; export import lib.core; export import lib.io;`。

注 6 强调，这种间接导入不会带来宏。导入的 TU 是翻译阶段 7 的记号序列（[[lex.phases]]），宏在阶段 4 就已经处理完了。宏只能通过直接导入头文件单元获得。

## 头文件单元（¶5–¶6）

¶5 `import "h.h";` 导入一个合成的[[g:header-unit|头文件单元]]（header unit）：对 `h.h` 单独施加翻译阶段 1 到 7 得到的 TU。这个文件不得含有模块声明。

注 2 说明了头文件单元的性质：它是一个独立的 TU，有自己独立的一套宏定义；其中的所有声明都隐式导出（[[module.interface#2]]），并附属于全局模块（[[module.unit#7]]）。注 4 指出，预处理器也会识别这种导入，头文件单元在阶段 4 结束时定义的宏会对导入者可见（[[cpp.import]]）。其他导入都不会带来宏。

```cpp title="cfg.h（可导入头文件）"
#pragma once
#define CFG_LEVEL 3
static int helper() { return CFG_LEVEL; }   // 内部链接：¶6 允许
inline int twice(int x) { return 2 * x; }
```

```cpp title="use.cpp" ok
import "cfg.h";           // 宏 CFG_LEVEL 也可见
int main() { return twice(CFG_LEVEL) + helper(); }   // 2*3 + 3 = 9
```

```cpp title="N.cppm"
export module N;
import "cfg.h";
export int fromN() { return twice(1); }
```

```cpp title="use2.cpp" ok
import N;                 // 具名模块：不带宏，即使 N 导入了 cfg.h
#ifdef CFG_LEVEL
#error "不会触发"
#endif
int main() { return fromN(); }
```

三种引入方式的对比：

| | `#include "h.h"` | `import "h.h";` | `import m;` |
|---|---|---|---|
| 翻译方式 | 文本粘贴到当前 TU | 独立 TU，翻译一次 | 独立 TU，翻译一次 |
| 包含者的宏影响被引入的内容 | 是 | 否 | 否 |
| 被引入内容的宏带出来 | 是 | 是 | 否 |
| 声明附属于 | 全局模块 | 全局模块 | 模块 m |
| 哪些名字可见 | 全部 | 全部（隐式导出） | 只有被导出的 |

### 哪些头文件可以导入

¶5 能这样导入的必须是**可导入头文件**（importable header）。可导入头文件的集合由实现定义，但必须包含所有可导入的 C++ 库头文件，即 [[headers#4]] 表 24 中的 `<vector>`、`<string>` 等。`<cstdio>`、`<cassert>` 这类 C 库设施的头文件不在表 24 中，是否可导入由实现决定。

如果 `#include` 指名的是可导入头文件，实现可以把这条 `#include` 换成对应的 `import`，是否这样做由实现定义（[[cpp.include#10]]）。头文件单元有独立的宏环境，所以这种替换可能改变程序的含义：在 `#include <vector>` 之前定义的配置宏，替换后就不再影响 `<vector>`。因此可导入头文件应当不依赖于包含者的宏状态。

### 同一个头文件是不是同一个头文件单元

¶5 给定两条导入头文件的声明：

- ¶5.1 如果它们指名不同的头文件或源文件，导入的是不同的头文件单元；
- ¶5.2 否则，如果它们在同一个 TU 中，导入的是同一个头文件单元；
- ¶5.3 否则，是否为同一个头文件单元是未指明的。

¶5.3 留给实现选择：可以为不同的编译配置（不同的命令行宏、不同的语言模式）分别构建同一个头文件的头文件单元，也可以全项目共享一份。注 3 指出了后果：可导入头文件中具有内部链接的实体（`static` 函数、命名空间作用域的 `const` 变量）可能有多份，就像 `#include` 时每个 TU 各有一份一样。

### 头文件单元里能有什么（¶6）

¶6 头文件单元中可以声明具有内部链接的名字，尽管其中所有声明都被隐式导出（[[module.interface#3]] 为此留了例外）。注 5 提醒，在多个 TU 中出现的定义（例如 inline 函数）一般不能引用这类名字（[[basic.def.odr]]）。

头文件单元不得含有非 inline 的、具有外部链接的函数或变量的定义。由于 ¶5.3，各个导入者拿到的可能是同一个头文件单元，也可能是不同的，这样的定义可能被链接进程序多次，也可能找不到一个确定的目标文件来容纳它。能放进头文件单元的，恰好是能放进普通头文件而不违反 ODR 的东西。Clang 23 对 `int bad() { return 0; }` 报 "non-inline external definitions are not permitted in C++ header units"。

!!! impl "头文件单元的实现状况"
    本机 Clang 23 用 `-fmodule-header=user -xc++-header cfg.h -o cfg.pcm` 构建用户头文件单元（系统头文件用 `-fmodule-header=system -xc++-system-header vector`），再用 `-fmodule-file=cfg.pcm` 导入。上面两个例子分别返回 9 和 2，但每次导入都会警告 "the implementation of header units is in an experimental phase"。头文件单元要求构建系统为每个头文件决定用哪组宏和选项编译，这是它在各工具链中支持最弱的部分；本机 CMake 3.29 只支持具名模块，不支持头文件单元。见 [[toolchain/modules-in-practice]]。

## 不能导出实现分区（¶8）

¶8 模块实现单元不得被导出。能被导入的实现单元只有实现分区，所以这条规则禁止的是 `export import :Part;`，其中 `:Part` 是实现分区。实现分区不能含 `export` 声明，导出它没有意义，还会模糊接口的边界。

```cpp title="M-Part.cppm"
module M:Part;
```

```cpp title="M.cppm" error
export module M;
export import :Part;      // error: :Part 是实现单元
```

Clang 23 报 "module partition implementations cannot be exported"。

## 实现单元不能导入自己的模块（¶9）

¶9 模块 M 的实现单元如果不是分区，就不得导入 M。它已经隐式导入了 M（[[module.unit#8]]），再写一遍是冗余的。

```cpp title="M.cpp" error
module M;
import M;                 // error: 不能在自己的实现单元中导入 M
```

分区可以显式导入自己的模块，只要不形成环，见 [[module.unit#8]] 例 2 中的 `module B:X2; import B;`。

## 导入不能成环（¶10）

¶10 如果一个 TU 含有导入 U 的声明（模块声明也算，因为 `module M;` 隐式导入主接口），或者它对另一个对 U 有接口依赖的 TU 有接口依赖，就说它对 U 有[[g:interface-dependency|接口依赖]]（interface dependency）。TU 不得对自身有接口依赖。

```cpp title="M1.cppm"
export module M1;
import M2;
```

```cpp title="M2.cppm"
export module M2;
import M3;
```

```cpp title="M3.cppm" error
export module M3;
import M1;                // error: 循环接口依赖 M3 → M1 → M2 → M3
```

导入一个模块，要求它已经翻译好（实现上需要它的 BMI，即编译器缓存的接口信息）。有了环，就找不到合法的编译顺序。`#include` 的循环可以靠 include guard 截断，模块之间则没有翻译到一半的概念。

这条规则可诊断，但编译器单独翻译一个 TU 时看不到整个环。实践中由构建系统在依赖扫描阶段发现；本机直接编译 `M3.cppm`，Clang 报的是 "module 'M1' not found"，因为 M1 的 BMI 还不存在。打破环的常见做法是把相互依赖的部分挪进同一模块的分区，或者提取到第三个模块。

接口依赖的概念也用在 [[module.reach#1]]（必然可达的 TU）和 [[lex.phases]]（被依赖单元的源码是否需要可用由实现定义）中。

## 标准库模块：`import std;`

C++23 起，标准库提供两个具名模块（[[std.modules]]，[[P2465R3]]）：

- `std` 导出 `namespace std` 中由表 24 的 C++ 库头文件和表 25 的 C 库设施头文件（`<cstdio>` 等）提供的声明，外加全局命名空间中的 `operator new` 和 `operator delete`。
- `std.compat` 导出 `std` 的全部内容，外加 C 库函数在全局命名空间中的版本（`::printf`、`::size_t` 等）。

```cpp title="hello.cpp" ok
import std;
int main() {
  std::vector<int> v{3, 1, 2};
  std::ranges::sort(v);
  std::println("{}", v);              // [1, 2, 3]
#ifdef assert
  std::println("assert is a macro");
#else
  std::println("no assert macro");    // 实际输出这一行
#endif
}
```

和所有具名模块一样，`import std;` 不提供宏：`assert`、`errno`、`offsetof`、`va_arg` 仍然需要 `#include` 对应的头文件（[[std.modules#6]] 注 2）。

标准没有规定标准库的声明附属于哪个模块（[[std.modules#4]]），但要求混用 `#include <vector>` 与 `import std;` 不会造成附属冲突，`std::vector` 无论经由哪条途径得到都是同一个实体（[[std.modules#5]]）。常见做法是让标准库实体附属于全局模块：libc++ 的 `std.cppm` 在全局模块片段中包含所有头文件，再用 `export namespace std { using std::vector; ... }` 把名字导出。

!!! impl "本机构建 `import std;`"
    Homebrew 的 LLVM 在 `share/libc++/v1/std.cppm` 提供 `std` 模块的源码：
    ```bash
    clang++ -std=c++2c -Wno-reserved-module-identifier --precompile \
        /opt/homebrew/opt/llvm/share/libc++/v1/std.cppm -o std.pcm
    clang++ -std=c++2c -fmodule-file=std=std.pcm hello.cpp std.pcm -o hello
    ```
    生成的 `std.pcm` 约 37 MB。在本机 `-O0` 下只编译 `hello.cpp` 约需 0.33 s，而用 `#include <vector>`、`<algorithm>`、`<print>` 的等价程序约需 0.60 s（各测三次）。详细步骤见 [[toolchain/modules-in-practice]]。

## 历史与演进

!!! history
    - 三种导入形式、头文件单元、`export import` 和接口依赖来自 C++20 的 [[P1103R3]]。
    - [[P1857R3]] 把以 `import`、`module`、`export` 开头的行规定为预处理指令，依赖扫描因此只需预处理。这也是 `import` 必须位于行首、不能由宏生成的原因。
    - C++20 规定所有 C++ 库头文件都可导入，但没有提供 `import std;`。[[P2465R3]] 在 C++23 中加入了 `std` 和 `std.compat`。更多背景见 [[history/modules]]。

## 常见误解

!!! pitfall "`import M;` 带入了 M 导入的所有东西"
    只有 `export import` 传递名字。M 中普通的 `import <string>;` 不会让导入 M 的人看到 `std::string` 这个名字。`std::string` 的定义仍然可达，所以 M 导出的返回 `std::string` 的函数照样能用，返回值也能调用 `.size()`，但导入者自己不能写 `std::string s;`。

!!! pitfall "`import std;` 提供 `assert`"
    不提供。`assert` 是宏，仍需 `#include <cassert>`。标准明确支持混用 `#include` 与 `import std;`（[[std.modules#4]] 注 1）。

!!! pitfall "把含普通函数定义的头文件当作头文件单元导入"
    违反 ¶6。这样的头文件不应列为可导入头文件。

## 思考题

!!! question "思考题 1"
    模块 A 的接口单元写了 `import B;`（不导出），模块 B 导出了 `struct S { int x; };` 和 `S make();`，A 导出了 `export S getS() { return make(); }`。在导入 A 的 TU 中，下面哪些行合法？

    ```cpp
    import A;
    auto s = getS();     // (1)
    int n = s.x;         // (2)
    S t;                 // (3)
    decltype(getS()) u;  // (4)
    ```

<details markdown="1">
<summary>答案</summary>

- (1) 合法：`getS` 由 A 导出。
- (2) 合法：当前 TU 对 B 的接口单元有接口依赖，B 的接口单元对它必然可达（[[module.reach#1]]），所以 `S` 是完整类型，成员 `x` 可以通过类成员查找找到。
- (3) 非良构：名字 `S` 不可见，A 中的导入没有导出（¶7）。Clang 23 报 "declaration of 'S' must be imported from module 'B' before it is required"。
- (4) 合法：没有写出名字 `S`，`decltype` 得到的类型的定义可达。
</details>

!!! question "思考题 2"
    为什么 ¶7 的第二条规则（同一模块的单元之间普通导入也传递）不会制造新的导入环？

<details markdown="1">
<summary>答案</summary>

这条规则只扩大了被导入的 TU 集合，多导入的都是 U 已经导入的 TU。U 能被翻译，说明这些 TU 不依赖于 U。导入者 T 导入 U 时，按 ¶10 的传递定义，T 本来就经由 U 对这些 TU 有接口依赖。第二条规则没有加入新的依赖边，只是让已有依赖中的名字可见，所以不会产生新的环。
</details>
