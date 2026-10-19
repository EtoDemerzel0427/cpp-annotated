---
title: 分别翻译
summary: 源文件、预处理翻译单元和翻译单元分别指什么，以及程序为什么可以一个翻译单元一个翻译单元地编译、最后再链接。
status: done
related: lex.phases, basic.link, basic.def.odr, cpp.include, cpp.cond, module.unit
tags: 翻译单元, 编译模型
updated: 2026-10-19
---

!!! tldr
    - 一个源文件，加上它 `#include` 进来的全部内容，减去条件编译跳过的行，叫做预处理翻译单元。
    - 它经过预处理、转换成记号之后，这串记号叫做翻译单元（TU）。ODR、链接等规则说的“每个翻译单元”指的就是它。
    - 各个 TU 分别翻译，最后链接成程序。编译器一次只看一个 TU，所以跨 TU 的错误（例如 ODR 违规）大多不要求诊断。
    - 标准里的文件只是概念：从标准输入读源码、unity build、预编译头、LTO 都在这个模型之内。

## 源文件、预处理翻译单元、翻译单元

一个项目里通常有很多 `.cpp` 文件，每个文件 `#include` 若干头文件，各自编译成一个目标文件，再链接起来。标准用三个名词描述这个过程中的三样东西。

¶1 程序的文本保存在**源文件**（source file）里。一个源文件，连同经 `#include` 包含进来的所有头文件和源文件，减去被条件包含指令（`#if`、`#ifdef` 等，[[cpp.cond]]）跳过的行，再按实现对 pragma（[[cpp.pragma]]）和有条件支持的指令（[[cpp.pre]]）的处理加以修改，就是一个[[g:preprocessing-translation-unit|预处理翻译单元]]（preprocessing translation unit）。

预处理翻译单元经过翻译阶段 4（预处理）、5（字符串拼接）、6（转换成记号），得到一串记号。[[lex.phases]] 的阶段 7 说，这串记号构成一个**翻译单元**（translation unit，TU），并作为整体做语法和语义分析。ODR（[[basic.def.odr]]）等规则说“在每个翻译单元中”时，指的就是这个记号层面的单元。

| 名词 | 是什么 | 定义处 |
|---|---|---|
| 源文件 | 输入的程序文本 | ¶1 |
| 预处理翻译单元 | 源文件 + 递归包含的内容 − 跳过的行 | ¶1 |
| 翻译单元 | 阶段 6 产生、阶段 7 分析的记号序列 | [[lex.phases]] 阶段 7 |
| 翻译后的翻译单元 | 阶段 7 的产物、阶段 8 的输入，通常对应一个目标文件 | [[lex.phases]] 阶段 8 |

标准还区分头文件（header）和源文件。`#include <...>` 找的是头文件，它可以根本不是文件，例如 `<vector>` 理论上可以内建在编译器里；`#include "..."` 先找源文件，找不到再当作 `<...>` 重试（[[cpp.include]]）。头文件名怎样对应到头文件或文件，由实现定义（[[lex.header]]）。

## 分别翻译与链接

注 1 说，程序不必一次全部翻译：各个 TU 可以分别翻译，之后再链接成可执行程序（[[basic.link]]）。

```cpp title="a.cpp"
int counter = 0;         // 外部链接：b.cpp 里的 extern 声明指的就是它
static int helper = 1;   // 内部链接：只在 a.cpp 中可见
```

```cpp title="b.cpp"
extern int counter;      // 在阶段 8（链接）时与 a.cpp 的定义对上
static int helper = 2;   // 与 a.cpp 的 helper 是不同的实体
int main() { return counter + helper - 2; }
```

这两个文件分别编译、再链接，是良构的程序，返回 0。很多核心规则都是由分别翻译引出的：

- 同一个 inline 函数在两个 TU 里的定义不一致，违反 ODR，但不要求诊断（{{ifndr}}），因为编译器每次只看到一个 TU。
- `static` 和匿名命名空间给名字内部链接，让不同 TU 里的同名实体互不干扰。
- 模板的定义通常写在头文件里，因为实例化发生在使用它的那个 TU 中。
- 不同 TU 中非局部变量的动态初始化顺序不确定（[[basic.start.dynamic]]），因为 TU 之间没有先后。

TU 的边界有语义，不能随意改变。把上面两个文件合进一个 TU（例如 unity build，见下文），两个 `static int helper` 就成了同一作用域里的重定义，程序非良构。

## 文件只是概念

注 2 说，源文件、翻译单元和翻译后的翻译单元不一定以文件形式存储，也不必和任何外部表示一一对应；这里的描述只是概念性的。所以下面这些做法都与标准相容：

- 从标准输入读取源码，例如 `clang++ -x c++ -`；
- unity build：一个 `.cpp` 依次 `#include` 多个 `.cpp`，把它们合成一个 TU；
- 预编译头（PCH）和模块的编译产物（BMI）；
- 链接期优化（LTO）：翻译后的 TU 以中间表示保存，到链接时才生成机器码。

主流工具链的惯例是一次 `-c` 调用处理一个 `.cpp`、输出一个 `.o`，即一个源文件对应一个 TU、一个目标文件。`-E` 的输出就是预处理翻译单元经过阶段 4 之后的样子。

C++20 起，一个 TU 可以是模块单元（[[module.unit]]）。它仍然单独翻译，只是 TU 之间除了通过有链接的名字通信，还可以导入另一个 TU 的接口（[[module.import]]）。被导入单元的源码是否必须可用由实现定义（[[lex.phases]] 阶段 7），实践中编译器读取的是预先编译好的接口文件。

## 思考题

!!! question "思考题"
    下面两个文件各自都是合法的 C++。把它们作为两个 TU 链接成程序，与做成 unity build（第三个文件依次 `#include "x.cpp"` 和 `#include "y.cpp"`）相比，结果有什么不同？

    ```cpp
    // x.cpp
    namespace { int f() { return 1; } }
    int gx() { return f(); }
    // y.cpp
    namespace { int f() { return 2; } }
    int gy() { return f(); }
    ```

<details markdown="1">
<summary>答案</summary>

作为两个 TU 时，每个 TU 有自己的匿名命名空间，两个 `f` 是不同的实体，程序良构。

做成 unity build 后，两个文件属于同一个 TU，而同一个 TU 里的匿名命名空间是同一个命名空间（[[namespace.unnamed]]）。于是 `f` 在同一个 TU 中定义了两次，违反 [[basic.def.odr]]，程序非良构，编译器必须诊断。
</details>
