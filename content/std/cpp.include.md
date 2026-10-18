---
title: 源文件包含
summary: #include 的两种形式如何映射为"头文件搜索"与"源文件搜索"（均由实现定义），宏形式的 #include 如何拼出 header-name，可移植文件名的最低保证、嵌套上限，以及 #include 何时可以被替换为 import；顺带讨论 include guard 与非标准的 #pragma once。
status: draft
related: cpp.pre, cpp.cond, lex.header, lex.separate, cpp.import, module.import, headers
tags: 预处理, 头文件, 模块
updated: 2026-10-18
---

`#include` 是 C/C++ 最古老、最"笨"的复用机制：把另一个文件的全部内容原样贴到这里。标准对它的规定少得惊人——**到哪里找、怎么找，几乎全部由实现定义**。这一节的价值在于弄清楚标准到底保证了什么（很少）、什么是工具链约定（很多），以及 C++20 模块怎样在不破坏它的前提下给它开了一道"后门"。

前置知识：*header-name* 的词法（[[lex.header]]）；什么时候 `<...>` 会被识别为 *header-name*（[[lex.pptoken#5]]）；预处理翻译单元（[[lex.separate]]）。

## 两种搜索（¶1–¶2）

当前草案用两个术语描述查找过程：

- [[g:header-search|头文件搜索]]（*header search*，¶1）：对一个字符序列，在"一系列位置"中查找**由该序列唯一标识的头文件**。这些位置怎么确定、头文件怎么标识，由实现定义。
- [[g:source-file-search|源文件搜索]]（*source file search*，¶2）：尝试找到由该字符序列**命名的源文件**，查找方式由实现定义。如果实现不支持对该序列做源文件搜索，或者搜索失败，结果就是**对同一序列做头文件搜索的结果**。

注意措辞上的区别：**头文件**（header）不一定是文件。标准库头文件 `<vector>` 只需要被"标识"，实现完全可以把它内置在编译器里。而**源文件**（source file）就是一个真正的文件。

## 两种直接形式（¶3–¶6）

¶3：`# include header-name new-line` 用 *header-name* 所标识的头文件或源文件的**全部内容**替换这条指令。

| 形式 | 搜索 | 出处 |
|---|---|---|
| `#include <h-char-sequence>` | 头文件搜索 | ¶4 |
| `#include "q-char-sequence"` | 源文件搜索；失败则退回头文件搜索 | ¶5（结合 ¶2） |

这就是"引号形式先在本地找，找不到再去系统路径找"这条民间规则的标准依据。用 Clang 实测：

```cpp
// 当前目录下有 myfile.h，命令行没有 -I.
#if __has_include("myfile.h")    // 1：源文件搜索在包含者所在目录找到了
#endif
#if __has_include(<myfile.h>)    // 0：头文件搜索只看 -I/-isystem/系统路径
#endif
```

¶6：若头文件搜索失败，或任一搜索找到了实现**无法处理**的头文件或源文件，程序非良构。注 1：即使只是在 `__has_include` 中，"找到但无法处理"也是非良构。

```cpp run title="missing.cpp" error
#include <no/such/header.h>   // error: 头文件搜索失败
int main() {}
```

!!! impl "实现定义的搜索顺序"
    GCC 和 Clang 的约定（具体以其文档为准）：
    
    - `"..."`：先在**包含者文件所在目录**找，再按 `-iquote` 目录、然后同 `<...>`。
    - `<...>`：依次是 `-I` 目录、`-isystem` 目录、系统目录。
    - MSVC 对 `"..."` 还会沿着"包含栈"逐层向上，在每个打开过的包含者的目录中查找。
    
    这些都是 ¶1–¶2 所说的"实现定义"。可移植代码不应依赖它们的细节。

## 宏形式（¶7）

¶7：若指令不匹配上述两种直接形式——即 `include` 后面不是一个 *header-name* 记号——那么 `include` 之后的记号**像普通文本一样做宏替换**。结果必须是 *header-name-tokens* 的形式，即：

- 一个 *plain-string-literal*（无前缀的字符串字面量），或
- `<` *h-pp-tokens* `>`（`<`，若干不是 `>` 的记号，`>`）。

然后实现尝试用这些记号的拼写及其间的空白拼出一个 *header-name*，**空白如何处理由实现定义**。成功则按直接形式处理；失败则 {{ifndr}}。

标准的例 1 是这种形式的典型用法：

```cpp
#if VERSION == 1
    #define INCFILE  "vers1.h"
#elif VERSION == 2
    #define INCFILE  "vers2.h"  // and so on
#else
    #define INCFILE  "versN.h"
#endif
#include INCFILE
```

更实用的例子是用字符串化拼出平台相关的路径：

```cpp
#define STR_(x) #x
#define STR(x) STR_(x)
#define PLATFORM linux
#include STR(platform/PLATFORM/config.h)   // → #include "platform/linux/config.h"
```

`<...>` 形式也可以由宏得到，此时 `<` 与 `>` 之间的记号在宏展开后**按拼写和空白**拼接：

```cpp
#define X myfile
#define Y h
#define HDR <X.Y>
#include HDR          // HDR → < myfile . h >（各记号）→ 拼成 <myfile.h>
```

!!! pitfall "空白是实现定义的"
    `#define SP < myfile.h >` 之后 `#include SP`，Clang 会尝试打开名为 ` myfile.h `（**首尾带空格**）的文件，并报 `-Wnonportable-include-path`。¶7 明确说空白处理由实现定义，所以别在 `<` 后、`>` 前留空格。

注 2：相邻的字符串字面量**不会**被拼接（拼接发生在阶段 6，见 [[lex.phases]]），所以展开为两个字符串字面量的 `#include` 不是合法指令：

```cpp
#define TWO "dir/" "file.h"
#include TWO      // 不构成单个 header-name：IFNDR（Clang 报 extra tokens，并去找 "dir/"）
```

!!! lawyer "ill-formed 还是 IFNDR？"
    ¶7 中有两个不同的失败点。宏替换的结果**不是** *header-name-tokens* 的形式——违反了"shall"，是普通的非良构，必须诊断。结果形式正确，但**拼不成**合法的 *header-name*——例如宏展开得到字符串字面量 `"a\"b"`，其拼写中含有 `"`，而 *q-char-sequence* 不能包含 `"`——这是 IFNDR。C++23 及以前，后者是 UB。

!!! lawyer "Clang 与 `#include EMPTY <X.Y>`"
    按 [[lex.pptoken#5.4.2.1]]，*header-name* 只在**紧跟** `include` 的位置才会被识别。所以 `#include EMPTY <X.Y>`（`EMPTY` 为空宏）中的 `<X.Y>` 不是 *header-name*，而是五个记号 `<` `X` `.` `Y` `>`，其中的 `X`、`Y` 应当被宏展开（[[cpp.embed.gen#14]] 的例 4 对 `#embed` 明确演示了这一点）。Clang 23 实测**不**展开 `X`、`Y`，而是去找字面上的 `X.Y`。这是 Clang 与草案的偏差，好在实践中几乎没人这样写。

## 可移植文件名（¶8）

¶8：实现必须为下面形式的序列提供**唯一映射**：一个或多个 *nondigit* 或 *digit*（[[lex.name]]），后跟 `.`，再跟**单个** *nondigit*；首字符不能是数字。实现**可以**忽略大小写的区别。

换言之，标准只保证 `foo.h`、`my_lib2.h` 这类"8.3 风格的退化版"能被区分。以下都**不**在保证之内：

- 目录分隔符 `/`（`#include "sys/types.h"`）——实践中 Windows 也接受 `/`，但标准不保证；
- 多字符扩展名 `.hpp`、无扩展名的 `<vector>`（标准库头文件另由 [[headers]] 保证）；
- 大小写敏感：`"Foo.h"` 和 `"foo.h"` 可能是同一个文件。

!!! pitfall "大小写"
    在 macOS（默认大小写不敏感的 APFS）和 Windows 上，`#include "Foo.h"` 能找到 `foo.h`；移到 Linux 就找不到了。Clang 提供 `-Wnonportable-include-path` 检测这种拼写与磁盘上真实名字不符的情况。

## 嵌套（¶9）

¶9：被 `#include` 读进来的文件里还可以有 `#include`，嵌套层数上限由实现定义（[[implimits]] 建议至少 256 层；条件包含的嵌套同样建议至少 256 层）。

```cpp title="self.h"
#include "self.h"     // 无条件自包含
```

Clang 在嵌套到上限时报 `#include nested too deeply`。

## #include 可以变成 import（¶10）

¶10：若 *header-name* 标识的头文件是一个**可导入头文件**（*importable header*，[[module.import]]），则**由实现定义**该 `#include` 是否被替换为如下形式的 import 指令：

```cpp
import header-name ; new-line
```

这是 C++20 模块与传统头文件之间的桥梁，称为 **include 翻译**（include translation）。可导入头文件包括标准库的 C++ 头文件（[[headers]]，C 兼容头文件 `<cstdio>` 等除外）以及实现定义的其他头文件。

效果：同一个头文件不再被反复解析，而是编译一次为**头文件单元**（header unit），每次 `#include` 都只是导入它。宏仍然会被导入（[[cpp.import]]），所以对大部分代码来说是透明的。但有两点区别：

1. 头文件单元是**独立翻译**的，它看不到包含者在 `#include` 之前定义的宏。依赖"先 `#define` 一个配置宏再 `#include`"的头文件（如 `<cassert>` 依赖 `NDEBUG`）就不适合作为可导入头文件——这也是 C 兼容头文件被排除在外的原因之一。
2. 在 *module-file* 的正文中，由 `#include` 改写产生的 import 是**非良构**的（[[cpp.import#2]]）。

## 标准的建议（¶11）

注 3 给出的可移植性建议：实现提供的头文件用 `<>`，实现控制范围之外的源文件用 `""`。

```cpp
#include <stdio.h>
#include <unistd.h>      // POSIX：由"实现"（广义的系统）提供
#include "usefullib.h"
#include "myprog.h"
```

## Include guard 与 #pragma once

标准对"同一文件被包含两次"**没有**任何特殊处理：第二次包含就是第二次粘贴。如果文件里有类定义，重复定义就违反了 ODR 中"一个翻译单元内至多一个定义"的规则（[[basic.def.odr]]）。

### 标准方案：include guard

```cpp title="widget.h"
#ifndef WIDGET_H
#define WIDGET_H
struct Widget { int x; };
#endif // WIDGET_H
```

完全由 [[cpp.cond]] 的机制实现，100% 可移植。代价：

- 宏名可能冲突（两个库都用 `UTILS_H`）；
- 宏名必须手工维护（复制文件后忘改）；
- 名字不能用保留标识符（`__WIDGET_H__`、`_WIDGET_H` 这类以双下划线或下划线加大写字母开头的名字是保留的，[[lex.name]]）。

### 非标准方案：#pragma once

```cpp title="widget.h"
#pragma once
struct Widget { int x; };
```

`#pragma once` **不在标准中**。按 [[cpp.pragma]]，它是一个实现定义的 pragma；不认识它的实现必须忽略它（然后你就得到了重复定义）。但事实上所有主流编译器都支持它。

它的难点在于"同一个文件"的判定：同一文件可能通过符号链接、硬链接、不同的相对路径、网络文件系统上的不同挂载点被访问到。各实现用 inode、文件内容或路径的不同组合判断，边缘情况下会出错。这也是它一直没有被标准化的主要原因之一——标准无法定义"同一个文件"。

!!! impl "多重包含优化"
    GCC 和 Clang 都能识别 include guard 的惯用形式（文件的第一个非注释记号是 `#ifndef X`，最后是配对的 `#endif`，之外别无他物），并记住 X。之后再遇到同一文件的 `#include` 时，若 X 仍已定义，**连文件都不打开**。所以在这两个编译器上，include guard 的性能与 `#pragma once` 相当。注意 `#if !defined(X)` 形式也能被识别，但 guard 外面哪怕多一个声明，优化就失效。

## 历史与演进

!!! history
    - **C++98**：两种形式、宏形式；可移植文件名只保证"一个或多个 *nondigit*，后跟 `.` 和单个 *nondigit*"。后来与 C99 同步，允许数字（首字符除外）。
    - **C++17**：`__has_include`（[[P0061R1]]）。
    - **C++20**：可导入头文件与 include 翻译（¶10，来自模块合并提案 [[P1103R3]]）。
    - **C++23 之后的措辞**：引入"头文件搜索 / 源文件搜索"两个术语重写 ¶1–¶6；把 ¶7 中"拼不成 header-name"由 UB 改为 IFNDR；明确"找到但无法处理"也是非良构。

## 思考题

!!! question "思考题 1"
    下面的 `#include` 是否可移植？按标准逐步分析。
    ```cpp
    #define LIB boost
    #define STR_(x) #x
    #define STR(x) STR_(x)
    #include STR(LIB/config.hpp)
    ```

<details markdown="1">
<summary>展开查看答案与解析</summary>

预处理层面是确定的：`include` 后不是 *header-name*，走 ¶7。`STR(LIB/config.hpp)` → 实参 `LIB/config.hpp` 先完全展开为 `boost/config.hpp`（[[cpp.subst#1]]），代入 `STR_(x)` 的 `x`，再由 `#` 字符串化为 `"boost/config.hpp"`（[[cpp.stringize]]）。结果是一个 *plain-string-literal*，构成 *header-name* `"boost/config.hpp"`，按 ¶5 做源文件搜索。

但文件名本身超出了 ¶8 的保证：含 `/`、扩展名有 3 个字符。所以"能否找到这个文件"不可移植——虽然实际上所有主流实现都能处理。

另一个隐患：如果某处 `#define config ...` 或 `#define hpp ...`，`STR` 的实参展开会把它们也替换掉。`linux` 在 GCC 的 GNU 模式下就是预定义为 1 的宏，`STR(linux/foo.h)` 在 `-std=gnu++20` 下会变成 `"1/foo.h"`——这是真实发生过的事故。
</details>

!!! question "思考题 2"
    `#include <vector>` 被实现替换为 `import <vector>;` 后，下面的程序行为会改变吗？
    ```cpp
    #define _GLIBCXX_DEBUG 1
    #include <vector>
    ```

<details markdown="1">
<summary>展开查看答案与解析</summary>

可能会。头文件单元是独立翻译的，导入它时，包含者此前定义的宏**不影响**它的内容。若 `<vector>` 被翻译为 import，那么 `_GLIBCXX_DEBUG` 不会让它切换到调试模式实现（导入的是按编译头文件单元时的宏环境编译出的版本）。这正是 ¶10 把替换与否定为"实现定义"、并且实现通常要求通过编译选项显式启用 include 翻译的原因。另外 `_GLIBCXX_DEBUG` 本身是保留标识符，用户定义它依赖于库的文档化许可。
</details>

## 小结

!!! summary
    - `<...>` 做**头文件搜索**；`"..."` 做**源文件搜索**，失败退回头文件搜索。位置与方式都由实现定义。
    - 宏形式：替换后必须是字符串字面量或 `<...>` 记号序列；拼接时空白处理由实现定义；拼不成 *header-name* 是 IFNDR。
    - 相邻字符串字面量不拼接，`#include "a" "b"` 无效。
    - 标准只保证 `字母数字串.单字母` 形式的文件名，大小写可以不区分。
    - 嵌套上限由实现定义。
    - 对可导入头文件，`#include` 可以由实现替换为 `import`。
    - Include guard 是标准方案；`#pragma once` 非标准但普遍支持，难点在"同一文件"的判定。
