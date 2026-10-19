---
title: 源文件包含
summary: "#include 的两种写法分别怎样查找文件，用宏拼出文件名的规则，标准保证可移植的文件名有多简单，以及 #include 什么时候可以变成 import。"
status: done
related: cpp.pre, cpp.cond, lex.header, lex.separate, cpp.import, module.import, headers
tags: 预处理, 头文件, 模块
updated: 2026-10-19
---

!!! tldr
    - `#include` 把另一个文件的全部内容原样放到指令所在的位置；到哪里找、怎么找，几乎都由实现决定。
    - `<...>` 做头文件搜索；`"..."` 先做源文件搜索，找不到再退回头文件搜索。这就是引号形式先找本地的依据。
    - `#include` 后面也可以是宏，展开结果必须是一个字符串字面量或 `<...>`；相邻的字符串字面量不会拼接。
    - 标准只保证 `foo.h` 这种字母数字加单字母扩展名的文件名可以区分，目录分隔符和大小写都不在保证之内。
    - 对可导入头文件（如标准库的 C++ 头文件），实现可以把 `#include` 换成 `import`。

`#include` 是 C 和 C++ 最古老的代码复用机制：用另一个文件的全部内容替换这条指令。它在翻译阶段 4 执行（[[lex.phases]]），被包含的文件同样经过阶段 1 到 4 的处理，然后与包含它的文件一起组成一个翻译单元（[[lex.separate]]）。

## 两种写法，两种搜索（¶1–¶6）

在当前目录放一个 `myfile.h`，命令行不加 `-I.`，用 Clang 测试：

```cpp
#if __has_include("myfile.h")    // 1：在包含者所在的目录找到了
#endif
#if __has_include(<myfile.h>)    // 0：尖括号形式只找 -I、-isystem 和系统目录
#endif
```

标准用两个术语描述查找过程：

- ¶1 **头文件搜索**（[[g:header-search|header search]]）：对一个字符序列，在一系列位置中查找由它唯一标识的头文件。查哪些位置、怎样标识，由实现定义。
- ¶2 **源文件搜索**（[[g:source-file-search|source file search]]）：尝试找到以这个字符序列命名的源文件，方式由实现定义。如果实现不支持这样的搜索，或者没有找到，结果就是对同一序列做头文件搜索的结果。

措辞上的区别是有意的：头文件不一定是文件。`<vector>` 只需要能被标识，实现完全可以把它内置在编译器里；源文件才是真正的文件。

¶3 `# include header-name` 用头文件名（[[lex.header]]）所标识的头文件或源文件的全部内容替换这条指令。两种写法对应两种搜索：

| 写法 | 搜索方式 | 条文 |
|---|---|---|
| `#include <h-char-sequence>` | 头文件搜索 | ¶4 |
| `#include "q-char-sequence"` | 源文件搜索，找不到再做头文件搜索 | ¶5、¶2 |

¶6 如果头文件搜索失败，或者找到的头文件或源文件实现无法处理（比如它是个目录），程序非良构。注 1 补充，即使只是在 `__has_include` 中探测（[[cpp.cond]]），找到了却无法处理也是非良构。

```cpp run title="missing.cpp" error
#include <no/such/header.h>   // error: 头文件搜索失败
int main() {}
```

¶11 的注 3 给出可移植的用法：实现提供的头文件用 `<>`，实现控制范围之外的源文件用 `""`。这里的实现是广义的，POSIX 的 `<unistd.h>` 也算。

!!! impl "GCC、Clang、MSVC 的搜索顺序"
    以下是常见约定，细节以各编译器文档为准：

    - `"..."`：先在包含者所在的目录找，再找 `-iquote` 指定的目录，然后与 `<...>` 相同。
    - `<...>`：依次查找 `-I` 目录、`-isystem` 目录、系统目录。
    - MSVC 对 `"..."` 还会沿包含栈逐层向上，在每个打开中的包含者的目录里查找。

    这些都是 ¶1、¶2 所说的实现定义行为，可移植代码不应依赖其细节。

## 用宏拼出文件名（¶7、¶12）

¶12 的标准例 1 按版本号选择头文件：

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

¶7 如果 `include` 后面不是一个头文件名记号，它后面的记号就像普通文本一样做宏替换。替换的结果必须是下面两种形式之一：

- 一个不带前缀的字符串字面量；
- `<`，若干个不是 `>` 的记号，`>`。

然后实现用这些记号的拼写及其间的空白拼出一个头文件名，空白怎样处理由实现定义。拼成了，就按前面的直接形式处理；拼不成，程序非良构，不要求诊断（IFNDR：编译器可以不报错，标准对整个程序不再有要求）。

实践中常用字符串化（[[cpp.stringize]]）拼出依赖配置的路径：

```cpp
#define STR_(x) #x
#define STR(x) STR_(x)
#define PLATFORM posix
#include STR(platform/PLATFORM/config.h)   // 即 #include "platform/posix/config.h"
```

尖括号形式也可以由宏得到。`<` 和 `>` 之间的记号先展开，再按拼写拼接：

```cpp
#define X myfile
#define Y h
#define HDR <X.Y>
#include HDR          // 展开为 < myfile . h > 五个记号，拼成 <myfile.h>
```

!!! pitfall "不要在尖括号里留空格"
    `#define SP < myfile.h >` 之后写 `#include SP`，Clang 会去找名为 ` myfile.h `（首尾带空格）的文件，并给出 `-Wnonportable-include-path` 警告。空白的处理由实现定义，所以 `<` 之后、`>` 之前不要留空格。

¶7 的注 2 提醒，相邻的字符串字面量在阶段 6 才拼接，这里不会拼接。展开成两个字符串字面量的 `#include` 不是合法的指令：

```cpp
#define TWO "dir/" "file.h"
#include TWO      // 非良构：不是单个字符串字面量
```

这个结果不符合 ¶7 要求的两种形式，违反的是普通的 shall 规则，必须诊断。Clang 给出 extra tokens 警告，然后去找名为 `dir/` 的文件。只有形式正确、却拼不出合法头文件名时才是 IFNDR，例如宏展开得到的字符串字面量 `"a\"b"`，它的拼写里含有 `"`，而引号形式的头文件名中不能出现 `"`。

!!! lawyer "Clang 与 `#include EMPTY <X.Y>`"
    头文件名记号只在紧跟 `include` 的位置才会形成（[[lex.pptoken#5.4.2.1]]）。所以 `#include EMPTY <X.Y>`（`EMPTY` 是空宏）中的 `<X.Y>` 不是头文件名，而是 `<` `X` `.` `Y` `>` 五个记号，其中的 `X`、`Y` 应当宏展开。[[cpp.embed.gen#14]] 的例 4 对 `#embed` 演示了同样的规则。Clang 23 实测不展开 `X`、`Y`，直接去找字面上的 `X.Y`，这与草案不符。实践中几乎没有人这样写。

## 可移植的文件名（¶8）

¶8 实现必须能唯一地映射这样的文件名：一个或多个字母、数字或下划线，后跟 `.` 和单个字母或下划线，首字符不能是数字。实现可以不区分大小写。

换句话说，标准只保证 `foo.h`、`my_lib2.h` 这种名字能被区分。下面这些都不在保证之内，虽然主流实现都支持：

- 目录分隔符，如 `#include "sys/types.h"`；
- 多字符扩展名 `.hpp`，以及没有扩展名的文件名（标准库头文件 `<vector>` 另由 [[headers]] 保证）；
- 大小写：`"Foo.h"` 和 `"foo.h"` 可能是同一个文件。

!!! pitfall "大小写"
    macOS 默认的文件系统和 Windows 不区分大小写，`#include "MyFile.h"` 能找到 `myfile.h`；换到 Linux 就找不到了。Clang 在这种情况下给出 `-Wnonportable-include-path` 警告，指出拼写与磁盘上的文件名不一致。

## 防止重复包含

标准对同一文件被包含两次不做任何特殊处理，第二次包含就是再粘贴一次。如果文件里有类定义，一个翻译单元里就出现了两个定义，违反 ODR（[[basic.def.odr]]）。

标准内的办法是 include guard，完全由 [[cpp.cond]] 的机制实现：

```cpp title="widget.h"
#ifndef WIDGET_H
#define WIDGET_H
struct Widget { int x; };
#endif // WIDGET_H
```

它的缺点是宏名可能冲突（两个库都用 `UTILS_H`），复制文件后容易忘记改名。另外 `__WIDGET_H__`、`_WIDGET_H` 这类以双下划线或下划线加大写字母开头的名字保留给实现（[[lex.name]]），不能用作 guard。

`#pragma once` 不在标准中。按 [[cpp.pragma]]，它是实现定义的 pragma，不认识它的实现必须忽略它，结果就是重复定义；不过所有主流编译器都支持它。它的难点在于判断两次包含的是不是同一个文件：同一文件可能经由符号链接、硬链接、不同的相对路径或网络文件系统的不同挂载点访问到。标准无法定义什么是同一个文件，这是它一直没有标准化的主要原因。

!!! impl "多重包含优化"
    GCC 和 Clang 能识别 include guard 的惯用形式：文件中第一个非注释的内容是 `#ifndef X`，最后是与之配对的 `#endif`，此外别无他物。编译器记住 `X`，之后再 `#include` 同一个文件时，只要 `X` 仍有定义，就不再打开它。所以在这两个编译器上，include guard 的性能与 `#pragma once` 相当。guard 外面只要多出一个声明，这个优化就失效。

## #include 可以变成 import（¶10）

¶10 如果头文件名标识的是一个**可导入头文件**（[[g:importable-header|importable header]]，[[module.import]]），由实现定义这条 `#include` 是否替换成 `import header-name;`。可导入头文件至少包括标准库的 C++ 头文件，`<cstdio>`、`<cassert>` 等 C 库头文件不在其中（[[headers]]）；其余由实现定义。

替换之后，头文件只编译一次，成为头文件单元（[[g:header-unit|header unit]]），之后每次 `#include` 都是导入它。头文件单元中定义的宏仍然会导入（[[cpp.import]]），所以大多数代码感觉不到差别。但有两点不同：

1. 头文件单元是独立翻译的，看不到包含者在 `#include` 之前定义的宏。依赖这类配置宏的头文件就不适合作为可导入头文件，例如 `<cassert>` 依赖 `NDEBUG`。
2. 处理模块单元（以 `module` 指令开头的文件，见 [[cpp.module]]）时，由 `#include` 替换得到的 import 是非良构的（[[cpp.import#2]]）。这条限制针对 `module` 指令之后的正文，不针对全局模块片段；正文里要用这类头文件，直接写 `import`。

<details class="fine" markdown="1"><summary>其余条文</summary>

¶9 被包含的文件中还可以有 `#include`，嵌套层数的上限由实现定义。[[implimits]] 建议至少支持 256 层。一个无条件包含自身的头文件会很快达到上限，Clang 报 `#include nested too deeply`。

</details>

## 历史与演进

!!! history
    - C++98 起就有两种写法和宏形式。可移植文件名最初只保证字母，C++11 起与 C99 同步，允许数字（首字符除外）。
    - C++17 加入 `__has_include`（[[P0061R1]]）。
    - C++20 随模块加入可导入头文件，以及把 `#include` 替换为 `import` 的许可（[[P1103R3]]）。
    - C++23 之后的新措辞引入了头文件搜索和源文件搜索这两个术语，重写了 ¶1–¶6；宏形式拼不出头文件名的情形由 UB 改为 IFNDR；明确了找到但无法处理也是非良构。

## 思考题

!!! question "思考题 1"
    下面的 `#include` 可移植吗？
    ```cpp
    #define LIB boost
    #define STR_(x) #x
    #define STR(x) STR_(x)
    #include STR(LIB/config.hpp)
    ```

<details markdown="1">
<summary>答案</summary>

预处理的结果是确定的。`include` 后面不是头文件名，按 ¶7 做宏替换：`STR` 的实参 `LIB/config.hpp` 先完全展开为 `boost/config.hpp`（[[cpp.subst#1]]），代入 `STR_`，再由 `#` 字符串化为 `"boost/config.hpp"`（[[cpp.stringize]]）。这是一个字符串字面量，构成头文件名，按 ¶5 做源文件搜索。

但文件名超出了 ¶8 的保证：含有 `/`，扩展名有三个字符。所以能否找到这个文件不可移植，尽管所有主流实现都能处理。

另一个隐患是实参里的单词会被宏展开。如果某处 `#define config ...`，路径就被改掉了。`linux` 在 GCC 的 GNU 模式（如 `-std=gnu++20`）下是预定义为 1 的宏，`STR(linux/foo.h)` 会变成 `"1/foo.h"`。
</details>

!!! question "思考题 2"
    如果实现把 `#include <vector>` 替换成 `import <vector>;`，下面的代码行为会变吗？
    ```cpp
    #define _GLIBCXX_DEBUG 1
    #include <vector>
    ```

<details markdown="1">
<summary>答案</summary>

可能会。头文件单元独立翻译，导入它时，包含者此前定义的宏不影响它的内容。所以 `_GLIBCXX_DEBUG` 不会再让 `<vector>` 切换到 libstdc++ 的调试实现，导入的是按编译头文件单元时的宏环境生成的版本。这也是 ¶10 把是否替换定为实现定义的原因之一，实现通常要求用编译选项显式开启这种替换。
</details>

## 小结

!!! summary
    - `<...>` 做头文件搜索；`"..."` 做源文件搜索，找不到再做头文件搜索。位置和方式都由实现定义。
    - 宏形式的展开结果必须是一个字符串字面量或 `<...>`；拼不成头文件名是 IFNDR；尖括号里的空白怎样处理由实现定义。
    - 标准只保证 `字母数字串.单字母` 形式的文件名，大小写可以不区分。
    - include guard 是标准内的办法；`#pragma once` 不是标准，难点在于判断两个路径是不是同一个文件。
    - 对可导入头文件，实现可以把 `#include` 替换为 `import`，此时包含者之前定义的宏不再影响头文件的内容。
