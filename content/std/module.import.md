---
title: 导入声明
summary: import 能出现在哪里；导入模块、分区与头文件单元分别导入哪些翻译单元；export import 与模块内部的传递导入；头文件单元的身份、内部链接与宏；接口依赖与禁止循环；标准库模块 import std。
status: done
since: c++20
papers: P1103R3, P2465R3, P1857R3
related: module.unit, module.interface, module.reach, cpp.import, cpp.include, std.modules, headers, basic.lookup, toolchain/modules-in-practice
tags: 模块, 导入, 头文件单元
updated: 2026-10-17
---

`import` 是模块世界取代 `#include` 的机制。但两者本质不同：`#include` 把文本粘贴进来，`import` 则让另一组**已翻译**的 TU 中的声明对当前 TU "可见"或"可达"。本节精确规定一条 *module-import-declaration* 到底导入了**哪些 TU**——这个集合随后被 [[basic.lookup#2]]（名字查找）和 [[module.reach]]（可达性）使用。

阅读前需要：[[module.unit]]（模块单元、分区）、[[module.interface]]（导出）。

## 语法

```text
module-import-declaration:
    import-keyword module-name attribute-specifier-seq(opt) ;
    import-keyword module-partition attribute-specifier-seq(opt) ;
    import-keyword header-name attribute-specifier-seq(opt) ;
```

三种形式分别导入**具名模块**（`import M;`）、**本模块的分区**（`import :P;`）和**头文件单元**（`import <vector>;`、`import "config.h";`）。

和 `module` 一样，`import` 也不是关键字，而是**具有特殊含义的标识符**。预处理器在行首识别出 `import` 指令后，把它替换为特殊记号 *import-keyword*（[[cpp.import#3]]）；所以 `import` 声明必须独占一个"逻辑行"的开头，不能由宏展开产生。这一设计（[[P1857R3]]）让构建系统可以只做轻量级的预处理扫描，就找出一个文件的所有模块依赖，而不必完整解析 C++。

## 出现位置（¶1）

¶1 *module-import-declaration* 必须**栖居于全局命名空间作用域**。

在**模块单元**中，所有导入声明（以及导出导入声明的 `export import`）必须出现在 TU 的 *declaration-seq*（以及私有模块片段的 *declaration-seq*，如果有）中**所有其他声明之前**。可选的 *attribute-specifier-seq* 属于该导入声明。

为什么要求导入集中在开头？

- 构建系统扫描依赖时只需看文件头部；
- 编译器可以在处理任何声明之前就加载好所有 BMI，避免"同一个名字在导入前后含义不同"的复杂情形；
- 模块单元的接口依赖（¶10）一目了然。

注意这一条只约束**模块单元**。普通（非模块）TU 中，`import` 可以出现在其他声明之后——因为普通 TU 往往以 `#include` 开头，强制顺序会让迁移非常痛苦。

```cpp title="late.cppm" error
export module L;
int x;
import Q;           // error: 模块单元中的导入必须先于其他声明
```

```cpp title="late.cpp" ok
int x;
import Q;           // OK：非模块 TU 不受此约束
```

```cpp title="ns.cpp" error
namespace N {
  import Q;         // error: 导入声明必须栖居于全局命名空间作用域
}
```

!!! impl "本机诊断"
    Clang 23 对 `late.cppm` 报 "imports must immediately follow the module declaration"；对 `ns.cpp` 中的 `import` 则根本不当作导入（行首不是 `import`），报 "unknown type name 'import'"。

## 导入了什么（¶2–¶4）

¶2 导入声明**导入**一组 TU，具体是哪些由下面几段规定。

Note 1：被导入 TU 中**导出的**命名空间作用域声明，可以在导入它的 TU 中被名字查找找到；被导入 TU 中的声明在导入声明之后变得**可达**。

这句话浓缩了导入的两个效果：**可见**（只限导出的）和**可达**（所有的）。可见性的精确规则在 [[basic.lookup#2]]：一个声明 X **先于**程序点 P，若 P 跟在导入了 X 所在 TU 的导入声明之后，X 在该 TU 的 *module-declaration* 之后、私有模块片段之前，并且 X 被导出——或者两个 TU 属于同一模块且 X 不是内部链接的。

¶3 指定 *module-name* M 的导入声明，导入 M 的**所有模块接口单元**——主接口单元和所有接口分区。（由于接口分区必须被主接口单元导出，这与"导入主接口单元并传递"效果一致，但规定得更直接。）

¶4 指定 *module-partition* 的导入声明，只能出现在**某个模块 M 的模块单元中、*module-declaration* 之后**。它导入 M 的同名分区。

分区名是**相对于当前模块**的：在模块 M 中写 `import :P;` 就是导入 `M:P`。没有任何语法能导入其他模块的分区——这是"分区对外不可见"的语法保证。

## 头文件单元（¶5–¶6）

¶5 指定 *header-name* H 的导入声明，导入一个合成的**头文件单元**（header unit）：对 H 指名的源文件或头文件施加翻译阶段 1 到 7（[[lex.phases]]）得到的 TU。该文件不得含有 *module-declaration*。

Note 2：头文件单元是一个**独立的** TU，拥有独立的宏定义集合。头文件单元中的所有声明都**隐式导出**（[[module.interface#2]]），并**附属于全局模块**（[[module.unit#7]]）。

**可导入头文件**（importable header）是实现定义的一组头文件，其中**必须包含所有可导入的 C++ 库头文件**（[[headers#4]]：表 24 中的头文件，如 `<vector>`、`<string>`；**不**包括 `<cstdio>`、`<cassert>` 等 C 库设施头文件——它们是否可导入由实现定义）。H 必须指定一个可导入头文件。

头文件单元是"头文件"与"模块"之间的过渡形态：

| | `#include "h.h"` | `import "h.h";` | `import m;` |
|---|---|---|---|
| 翻译方式 | 文本粘贴到当前 TU | 独立 TU，翻译一次 | 独立 TU，翻译一次 |
| 当前 TU 的宏影响被导入内容 | 是 | **否**（独立宏环境） | 否 |
| 被导入内容的宏泄漏出来 | 是 | **是**（[[cpp.import]]） | 否 |
| 声明附属于 | 全局模块 | 全局模块 | 模块 m |
| 哪些声明可见 | 全部 | 全部（隐式导出） | 只有被导出的 |

**头文件单元的身份**（¶5.1–¶5.3）：给定两条导入头文件的声明，

- **¶5.1** 若它们的 *header-name* 标识**不同**的头文件或源文件（[[cpp.include]]），则导入**不同**的头文件单元；
- **¶5.2** 否则，若它们出现在**同一个 TU** 中，则导入**同一个**头文件单元；
- **¶5.3** 否则，**未指明**它们是否导入同一个头文件单元。

为什么 ¶5.3 是未指明？实现可能为不同的编译配置（不同的命令行宏、不同的语言模式）分别构建同一个头文件的 BMI，也可能全项目共享一份。标准允许两种做法。

Note 3 指出了后果：可导入头文件中具有**内部链接**的实体（`static` 函数、命名空间作用域的 `const` 变量）可能存在**多份拷贝**——就像 `#include` 时每个 TU 一份一样。

Note 4：导入 *header-name* 的导入声明也会被**预处理器**识别，导致头文件单元在其翻译阶段 4 结束时定义的宏变得可见（[[cpp.import]]）。**其他任何导入声明都不会使宏可见。**

¶6 头文件单元中允许声明具有内部链接的名字，尽管所有声明都被隐式导出（[[module.interface#3]] 正是为此留了例外）。Note 5：在多个 TU 中出现的定义（如 inline 函数）一般不能引用这类名字（[[basic.def.odr]]）。

头文件单元**不得**含有**非 inline** 的、外部链接的函数或变量的**定义**。理由：头文件单元可能在每个导入者处被看作"同一个"或"不同的"TU（¶5.3），一个非 inline 的定义就可能被链接进程序多次（违反 ODR），或者根本没有一个确定的目标文件来容纳它。能放进头文件单元的，正是能放进普通头文件而不违反 ODR 的东西。

```cpp title="cfg.h（可导入头文件）"
#pragma once
#define CFG_LEVEL 3
static int helper() { return CFG_LEVEL; }   // 内部链接：¶6 允许
inline int twice(int x) { return 2 * x; }   // inline：OK
// int bad() { return 0; }                  // 若取消注释：违反 ¶6
```

```cpp title="use.cpp" ok
import "cfg.h";                  // 宏 CFG_LEVEL 可见（头文件单元）
int main() { return twice(CFG_LEVEL) + helper(); }   // 2*3 + 3 = 9
```

```cpp title="N.cppm"
export module N;
import "cfg.h";
export int fromN() { return twice(1); }
```

```cpp title="use2.cpp" ok
import N;                        // 具名模块：不带宏，即使 N 导入了 cfg.h
#ifdef CFG_LEVEL
#error "不会触发"
#endif
int main() { return fromN(); }
```

!!! impl "头文件单元的实现状况"
    本机 Clang 23 可以用 `-fmodule-header=user -xc++-header cfg.h -o cfg.pcm` 构建用户头文件单元、`-fmodule-header=system -xc++-system-header vector` 构建系统头文件单元，再用 `-fmodule-file=cfg.pcm` 导入。上面两个例子都按预期运行（返回 9 和 2）。但每次导入都会给出警告 "the implementation of header units is in an experimental phase"。头文件单元需要构建系统为每个头文件决定"用哪组宏/选项编译"，这是它至今在各工具链中支持最弱的部分；本机的 CMake 3.29 的模块支持也只处理具名模块，不处理头文件单元。详见 [[toolchain/modules-in-practice]]。

### `#include` 可以被替换为 `import`

[[cpp.include#10]]：若 `#include` 指名的头文件是可导入头文件，**实现定义**是否把这条 `#include` 指令替换为 `import` 该头文件。这让编译器可以在不修改源码的情况下，把 `#include <vector>` 透明地变成 `import <vector>;`（MSVC 的"头文件单元自动翻译"就是这一机制的实现）。

由于头文件单元有独立的宏环境，这一替换可能改变程序的含义——如果你在 `#include <vector>` 之前定义了影响 `<vector>` 的宏（如某些库配置宏），替换后它们就不再生效了。这就是为什么标准只允许对"可导入"头文件做这种替换：可导入头文件被期望不依赖于包含者的宏状态。

## 传递导入（¶7）

¶7 当一条导入声明导入 TU T 时，它**也导入** T 中**被导出的导入声明**（`export import`）所导入的所有 TU；这些 TU 称为被 T **导出**（exported by T）。

此外，当模块 M 的某个模块单元中的导入声明导入 M 的另一个模块单元 U 时，它**还导入** U 的模块单元管辖范围中**未导出的导入声明**所导入的所有 TU。（脚注：这与被导入名字的查找规则一致。）

这些规则可能递归地导致更多 TU 被导入。

Note 6：这种间接导入**不会**使宏可用，因为 TU 是翻译阶段 7 的记号序列。宏只能通过**直接**导入头文件单元获得（[[cpp.import]]）。

两条规则对比：

| 导入者 | 被导入者 T 中的 `import X;` | 被导入者 T 中的 `export import X;` |
|---|---|---|
| 模块外的 TU | X **不**被导入（X 的接口单元仍**可达**，见 [[module.reach#1]]） | X 被导入 |
| 同一模块的另一个单元 | X 被导入（¶7 第二句） | X 被导入 |

第二句的道理：同一模块的各个单元本质上是"一个整体被拆成多个文件"，在主接口单元中 `import <string>;` 或 `import Q;` 之后，实现单元理应也能用这些名字，就像同一个文件里一样。

```cpp title="Q.cppm"
export module Q;
export int q() { return 4; }
```

```cpp title="M.cppm"
export module M;
import Q;                 // 非导出导入
export int m();
```

```cpp title="M.cpp" ok
module M;                 // 隐式 import M; 由 ¶7 第二句，也导入了 Q
int m() { return q(); }   // OK：q 可见
```

```cpp title="user.cpp" error
import M;                 // 只导入 M；Q 可达但未被导入
int main() { return m(); }
int z = q();              // error: q 不可见
```

而 `export import`（再导出）把一个模块的接口变成另一个模块接口的一部分：

```cpp title="R.cppm"
export module R;
export import Q;          // 导入 R 的人也导入 Q
```

```cpp title="user2.cpp" ok
import R;
int main() { return q(); }   // OK：Q 被 R 导出
```

!!! note "再导出与命名空间的组合"
    实践中，大型库常用一个"伞模块"（umbrella module）再导出所有子模块：`export module lib; export import lib.core; export import lib.io;`。由于模块名中的点没有语义（[[module.unit]]），这是让 `import lib;` 带入一切的唯一方式。

## 不能导出实现单元（¶8）

¶8 模块实现单元**不得被导出**。

能被导入的实现单元只有实现分区（普通实现单元没有名字可导入）。`export import :Part;` 若 `:Part` 是实现分区，就违反此规则——实现分区不能成为模块接口的一部分，因为它不能含有 `export` 声明，把它导出毫无意义且会混淆接口边界。

```cpp title="M-Part.cppm"
module M:Part;
```

```cpp title="M.cppm" error
export module M;
export import :Part;    // error: 被导出的分区 :Part 是实现单元
```

## 实现单元不能导入自己的模块（¶9）

¶9 模块 M 的、不是模块分区的实现单元，不得含有指名 M 的导入声明。

普通实现单元已经隐式导入了 M（[[module.unit#8]]），再写 `import M;` 是冗余的；而且这种写法容易让人误以为可以得到"导入者视角"，所以干脆禁止。

```cpp title="M.cpp" error
module M;
import M;               // error: 不能在自己的单元中导入 M
```

注意分区**可以**导入自己的模块（[[module.unit#8]] Example 2 的 TU #4 `module B:X2; import B;`），只要不形成循环。

## 接口依赖与禁止循环（¶10）

¶10 TU 对 TU U 有**接口依赖**（interface dependency），若它含有导入 U 的声明（包括 *module-declaration*——普通实现单元隐式导入主接口），或它对某个对 U 有接口依赖的 TU 有接口依赖（传递闭包）。

**TU 不得对自身有接口依赖。**

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
import M1;              // error: 循环接口依赖 M3 → M1 → M2 → M3
```

为什么禁止循环？导入需要被导入单元**已经被翻译**（实现上需要它的 BMI）。循环依赖意味着没有一个合法的编译顺序。这与 `#include` 不同——头文件循环包含可以靠 include guard 截断，因为那是文本层面的；模块之间没有"部分翻译"的概念。

这条规则以"可诊断"的形式写出，但实际上编译器单独翻译某个 TU 时未必能看到完整的环。实践中，构建系统在依赖扫描阶段发现环（本机 Clang 编译 `M3.cppm` 时，由于 `M1` 的 BMI 尚未生成，报的是 "module 'M1' not found"）。

如何打破环？典型做法是把相互依赖的部分提取到同一模块的分区中，或者把公共声明提取到第三个模块。注意 `extern "C++"` 的前置声明也可以跨模块"引用"一个附属于全局模块的实体，而不需要导入。

¶10 的"接口依赖"概念还被 [[module.reach#1]]（必然可达）和 [[lex.phases]]（实现定义是否需要依赖的模块单元和头文件单元的源码可用）使用。

## 标准库模块：`import std;`

C++23（[[P2465R3]]）起，标准库提供两个具名模块（[[std.modules]]）：

- **`std`**：导出 `namespace std` 中由可导入 C++ 库头文件（表 24）和 C 库设施的 C++ 头文件（表 25，`<cstdio>` 等）提供的声明，外加全局命名空间中的 `operator new`/`operator delete`。
- **`std.compat`**：导出 `std` 的全部内容，外加 C 库函数在全局命名空间中的版本（`::printf`、`::size_t` 等）。

要点：

- 标准**未指明**标准库的声明附属于哪个模块（[[std.modules#4]]）。实现必须保证混用 `#include <vector>` 与 `import std;` 不会导致附属冲突——常见做法是让标准库实体附属于**全局模块**（例如 libc++ 的 `std.cppm` 在全局模块片段中 `#include` 所有头文件，然后用 `export namespace std { using std::vector; ... }` 导出），所以同一个 `std::vector` 无论经由哪种途径到达都是同一实体（[[std.modules#5]]）。
- 和所有具名模块一样，`import std;` **不提供宏**：`assert`、`errno`、`offsetof`、`va_arg` 等需要另外 `#include <cassert>` 等（[[std.modules#6]] Note 2）。
- 由于 `std` 是保留名，用户不能自己写 `export module std;`（[[module.unit#1]]）。

```cpp title="hello.cpp" run ok
import std;
int main() {
  std::vector<int> v{3, 1, 2};
  std::ranges::sort(v);
  std::println("{}", v);         // [1, 2, 3]
#ifdef assert
  std::println("assert is a macro");
#else
  std::println("no assert macro");   // 实际输出这一行
#endif
}
```

!!! impl "本机构建 `import std;`"
    Homebrew 的 LLVM 在 `share/libc++/v1/std.cppm` 提供 `std` 模块的源码。本机：
    ```bash
    clang++ -std=c++2c -Wno-reserved-module-identifier --precompile \
        /opt/homebrew/opt/llvm/share/libc++/v1/std.cppm -o std.pcm
    clang++ -std=c++2c -fmodule-file=std=std.pcm hello.cpp std.pcm -o hello
    ```
    生成的 `std.pcm` 约 37 MB。编译上面的 `hello.cpp` 约 0.30 s，而用 `#include <vector>`/`<algorithm>`/`<print>` 的等价程序约 0.53 s（各测三次，仅前端 + 代码生成，`-O0`）。详细步骤见 [[toolchain/modules-in-practice]]。

## 历史与演进

!!! history "C++20 → C++23"
    - C++20 [[P1103R3]]：三种导入形式、头文件单元、`export import`、接口依赖。
    - C++20 [[P1857R3]]：把 `import`/`module`/`export` 开头的行规定为预处理指令，使依赖扫描可以只做预处理而不做完整解析；这也是为什么 `import` 必须位于行首、不能由宏生成。
    - C++20 规定所有 C++ 库头文件（不含 C 库包装头文件）都是可导入的；但 C++20 没有提供 `import std;`，这在当时被普遍认为是一大遗憾。
    - C++23 [[P2465R3]]：引入 `std` 与 `std.compat` 模块，libc++、libstdc++ 与 MSVC STL 现已都提供这两个模块（各自的构建方式不同）。

## 陷阱

!!! pitfall "以为 `import M;` 带入了 M 导入的所有东西"
    只有 `export import` 才传递可见性。M 中的普通 `import <string>;` 不会让导入 M 的人看到 `std::string` 这个名字——虽然 `std::string` 的定义是可达的（所以 M 导出的返回 `std::string` 的函数照样能用、能 `.size()`），但你不能自己写 `std::string s;`。

!!! pitfall "以为 `import std;` 提供 `assert`"
    不提供。`assert` 是宏。仍需 `#include <cassert>`。混用 `#include` 与 `import std;` 是被标准明确支持的（[[std.modules#4]] Note 1）。

!!! pitfall "在模块单元中把 `#include` 写在 `export module` 之后"
    `export module M; #include <vector>` 会把 `<vector>` 的全部声明**附属于 M**——它们成了 M 的模块链接实体，与其他 TU 中的 `std::vector` 冲突（[[basic.link#10]]）。`#include` 应放进全局模块片段（[[module.global.frag]]），或改用 `import`。

!!! pitfall "头文件单元中的非 inline 定义"
    把一个含有普通函数定义的项目头文件变成头文件单元，违反 ¶6。这样的头文件不应列为可导入头文件。

## 思考题

!!! question "思考题 1"
    模块 A 的接口单元写了 `import B;`（非导出），模块 B 导出了 `struct S { int x; };` 和 `S make();`。A 导出了 `export S getS() { return make(); }`。导入 A 的 TU 中，下面哪些行合法？

    ```cpp
    import A;
    auto s = getS();     // (1)
    int n = s.x;         // (2)
    S t;                 // (3)
    decltype(getS()) u;  // (4)
    ```

<details markdown="1">
<summary>答案</summary>

- (1) 合法：`getS` 被 A 导出。
- (2) 合法：`S` 的定义在 B 的接口单元中，B 的接口单元对当前 TU **必然可达**（当前 TU 对它有接口依赖，[[module.reach#1]]），所以 `S` 是完整类型，成员 `x` 可通过类成员查找找到。
- (3) 非良构：`S` 这个名字不可见——B 没有被当前 TU 导入（A 中是非导出导入，¶7）。
- (4) 合法：没有写出名字 `S`，`decltype` 得到的类型的定义可达。
</details>

!!! question "思考题 2"
    为什么 ¶7 的第二句（同模块内传递非导出导入）不会破坏 ¶10 的禁止循环规则？

<details markdown="1">
<summary>答案</summary>

¶7 第二句只是扩大了"被导入的 TU 集合"，它所导入的 TU 都是 U 已经导入的——U 能被翻译，说明这些 TU 都不依赖于 U。导入者 T 导入 U 时，T 对 U 有接口依赖，因此也（经由 U）对这些 TU 有接口依赖（¶10 的传递闭包）——第二句没有引入任何新的依赖**边**，只是让已有依赖中的名字可见。所以它不会制造新的环。
</details>

## 小结

| 规则 | 段落 |
|---|---|
| 导入声明栖居于全局命名空间作用域；模块单元中必须先于其他声明 | ¶1 |
| `import M;` 导入 M 的所有接口单元 | ¶3 |
| `import :P;` 只能在 M 的模块单元中，导入 M:P | ¶4 |
| `import <h>;`/`import "h";` 导入合成的头文件单元：独立宏环境、隐式导出、附属全局模块、带出宏 | ¶5 |
| 头文件单元身份：不同头 → 不同；同 TU → 相同；否则未指明 | ¶5.1–¶5.3 |
| 头文件单元可有内部链接名字，不可有非 inline 外部链接定义 | ¶6 |
| `export import` 传递；同模块单元之间非导出导入也传递；间接导入不带宏 | ¶7 |
| 实现单元不可被导出；普通实现单元不可导入自己的模块 | ¶8–¶9 |
| 接口依赖不得成环 | ¶10 |
