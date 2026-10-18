---
title: 分别翻译
summary: 源文件、预处理翻译单元与翻译单元的区别；为什么标准说源文件不一定是文件。
status: draft
related: lex.phases, basic.link, cpp.include, cpp.cond, module.unit
tags: 翻译单元, 编译模型
updated: 2026-10-17
---

C++ 的编译模型是**分别翻译**（separate translation）：程序拆成若干单元，各自独立地翻译，最后再链接到一起。[[lex.separate]] 只有一段，定义了这个模型中最基本的几个名词。这一节虽短，却是 ODR（[[basic.def.odr]]）、链接（[[basic.link]]）、模块（[[module]]）等所有跨 TU 规则的出发点。

## 源文件与预处理翻译单元（¶1）

¶1 程序的文本保存在本标准称为源文件（source file）的单元中。一个源文件，连同经由 `#include` 包含进来的所有头文件和源文件，

- 减去被条件包含指令（`#if`/`#ifdef`/…，[[cpp.cond]]）跳过的源行，
- 再按照有条件支持指令（*conditionally-supported-directive*，[[cpp.pre]]）和 pragma（[[cpp.pragma]]）的实现定义行为（若有）进行修改，

就是一个[[g:preprocessing-translation-unit|预处理翻译单元]]（preprocessing translation unit）。

!!! std
    A source file together with all the headers and source files included via the preprocessing directive `#include`, less any source lines skipped by any of the conditional inclusion preprocessing directives, [...] is called a *preprocessing translation unit*.

    预处理翻译单元 = 源文件 + 递归包含的内容 − 被条件编译跳过的行。

注意这几个名词处在不同的层次：

| 名词 | 何时存在 | 定义处 |
|---|---|---|
| 源文件（source file） | 输入 | [[lex.separate#1]] |
| 预处理翻译单元 | 阶段 1–4 处理的对象 | [[lex.separate#1]] |
| 翻译单元（translation unit） | 阶段 7 的记号序列 | [[lex.phases]] 阶段 7 |
| 翻译后的翻译单元（translated TU） | 阶段 8 的输入（通常对应目标文件） | [[lex.phases]] 阶段 8 |

"翻译单元"一词正式定义在 [[lex.phases]] 的阶段 7，那里说"这些记号构成一个翻译单元"。ODR 等规则说"在每个翻译单元中"时，指的就是这个记号层面的单元。

### 头文件与源文件

标准区分 *header*（头文件）和 *source file*（源文件）。

- `#include <...>` 搜索的是头文件，它可以根本不是文件，例如标准库头文件 `<vector>` 理论上可以内建在编译器里；
- `#include "..."` 先搜索源文件，失败后再当作 `<...>` 重试（[[cpp.include]]）。

因此 [[lex.header]] 把从头文件名到头文件或外部源文件名的映射定为实现定义。

## 注 1：分别翻译与链接

注 1：C++ 程序不必一次全部翻译。翻译单元可以分别翻译，之后再链接成可执行程序（[[basic.link]]）。

这句话看起来平淡，却是许多核心规则的动机：

- ODR 违规常常是 IFNDR（[[basic.def.odr]]），因为编译器每次只看到一个 TU，无法发现两个 TU 中同名内联函数的定义不一致。
- 内部链接（`static`、匿名命名空间）的作用是让同名实体在不同 TU 中互不干扰。
- 模板的定义必须在使用点可见（通常写在头文件里），因为实例化发生在使用它的 TU 的阶段 7。
- 静态初始化顺序问题：由于标准不规定 TU 之间的任何先后，不同 TU 中非局部变量的动态初始化顺序是不确定的（[[basic.start.dynamic]]）。

```cpp run title="a.cpp" ok
// a.cpp
int counter = 0;            // 外部链接：b.cpp 中的 extern 声明指向它
static int helper = 1;      // 内部链接：仅在 a.cpp 中可见
```

```cpp title="b.cpp" ok
// b.cpp
extern int counter;         // 引用 a.cpp 中的定义，在阶段 8 解析
static int helper = 2;      // 与 a.cpp 的 helper 是不同实体，互不冲突
int main() { return counter + helper - 2; }
```

## 注 2：一切都是概念性的

注 2：源文件、翻译单元和翻译后的翻译单元不一定以文件形式存储，它们和任何外部表示之间也不必一一对应。这里的描述只是概念性的，不规定任何具体实现。

所以下面这些做法都与标准相容：

- 从标准输入读取源码（`clang++ -x c++ -`）；
- Unity build（把多个 .cpp `#include` 进一个 .cpp）；注意这会把多个源文件合成一个 TU，改变内部链接名字之间的冲突关系，上例中的 `static int helper` 会变成重定义错误；
- 预编译头（PCH）、模块的二进制接口文件（BMI）；
- 链接期优化（LTO）：翻译后的 TU 以 IR 形式存储，直到阶段 8 才真正生成代码。

!!! impl "实现视角"
    在主流工具链中，最常见的对应关系是一次编译器调用（`-c`）处理一个 .cpp 并输出一个 .o，即一个 .cpp 对应一个预处理翻译单元、一个 TU、一个 .o。`-E` 的输出正好是预处理翻译单元经过阶段 4 之后的样子（带有 `# line` 标记）。不过上面已经看到，这种对应只是惯例。

## 与模块的关系

从 C++20 起，翻译单元可以是模块单元（module unit，[[module.unit]]）。模块单元依然是一个 TU，依然独立翻译；变化在于 TU 之间除了通过链接名字通信，还多了一种关系，即导入另一个 TU 的接口（[[module.import]]）。[[lex.phases]] 阶段 7 规定，被依赖的模块单元和头文件单元的源码是否必须可用，由实现定义。实践中，编译器读取的是它们预先编译出的接口文件。

## 思考题

!!! question "思考题"
    下面两个文件各自都是合法的 C++。把它们做成两个 TU 链接成程序，与做成 unity build（第三个文件依次 `#include "x.cpp"` 和 `#include "y.cpp"`）相比，结果有何不同？

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

作为两个 TU 时，每个 TU 有自己独立的匿名命名空间，两个 `f` 是不同实体，程序良构。作为 unity build 时，两个文件合并成一个预处理翻译单元，而同一 TU 中的匿名命名空间是同一个命名空间（[[namespace.unnamed]]），于是 `f` 定义了两次，违反 [[basic.def.odr]] 中一个 TU 内至多一个定义的规定，程序非良构（且必须诊断）。可见 **TU 的边界是有语义的**，不能随意改变。
</details>

## 小结

!!! summary
    - 源文件 +（递归）包含 − 被跳过的行 = **预处理翻译单元**；经阶段 1–6 后的记号序列 = **翻译单元**。
    - TU 分别翻译、在阶段 8 链接；这一模型是 ODR、链接属性、初始化顺序等规则的根本动机。
    - 这里的文件只是概念：标准不规定存储形式，PCH、unity build、LTO、模块 BMI 都在模型之内。
