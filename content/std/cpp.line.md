---
title: 行控制
summary: 预处理中的几条杂项指令：#line 改写报告的行号与文件名，#error 与 #warning 主动产生诊断，#pragma 交给实现决定，单独的 # 什么也不做，以及能由宏生成的 _Pragma 运算符。
status: done
covers: cpp.error, cpp.pragma, cpp.null, cpp.pragma.op
related: cpp.predefined, cpp.pre, cpp.rescan, support.srcloc, intro.compliance, lex.pptoken
tags: 预处理, 诊断, pragma
updated: 2026-10-19
---

!!! tldr
    - `#line 100 "x.y"` 让之后的 `__LINE__`、`__FILE__` 和 `std::source_location` 报告假定的行号和文件名，主要供代码生成工具指回原始文件。
    - `#error` 使程序非良构；`#warning`（C++23）只要求编译器给出一条诊断，程序仍然良构。
    - `#pragma` 的效果完全由实现定义，可以让实现不再符合标准；不认识的 pragma 被忽略，拼错了也不会报错。
    - 宏不能生成 `#pragma`，但可以生成 `_Pragma("...")`。`_Pragma` 去掉字符串的引号和 `\"`、`\\` 转义，再当作 `#pragma` 执行。

## #line：改写报告的位置 [cpp.line]

```cpp run title="line.cpp" ok
#include <source_location>
#line 100 "fake.cpp"
constexpr auto loc = std::source_location::current();
static_assert(loc.line() == 100);     // #line 之后的第一行就是 100
#define N 200
#define F "other.cpp"
#line N F                             // 先做宏替换，再按前两种形式处理
static_assert(__LINE__ == 200);
int main() {}
```

bison、flex、Qt 的 moc 这类工具把用户写的 `.y`、`.l` 等文件翻译成 `.cpp`，并在生成的代码里插入 `#line`。这样编译错误和调试信息指向的是原始文件里的行，而不是生成文件里的某一行。

`#line` 改的是**假定的**（presumed）行号和文件名。`__LINE__`、`__FILE__`（[[cpp.predefined]]）和 `std::source_location`（[[support.srcloc]]）报告的都是假定的位置，所以都受它影响。

### 三种形式（¶3–¶5）

¶3 `# line 数字序列` 让之后的源行如同从指定行号开始编号。数字按十进制解释，所以 `#line 010` 设置的是 10，不是八进制的 8，本机 Clang 23 对此会给出警告。超出 [1, 2147483647] 的值是**有条件支持**的：实现可以支持，不支持时必须诊断。C++23 及以前，这种情况是未定义行为。

¶4 `# line 数字序列 "文件名"` 在设置行号的同时，把假定的源文件名改为字符串的内容。

¶5 不符合以上两种形式的 `# line 记号...`，其中的记号先像普通文本一样做宏替换。替换后必须符合前两种形式之一，否则程序非良构。

¶1 文件名必须是不带前缀的字符串字面量。`#line 10 u8"x.cpp"` 非良构，本机 Clang 23 报 `invalid filename for #line directive`。

### 行号的定义（¶2）

¶2 当前源行的[[g:line-number|行号]]，是从文件开头处理到**当前预处理记号**为止，在翻译第 1 阶段读到或引入的换行符个数加一。

这句话有两层意思。第一，数的是物理行：第 2 阶段用反斜杠拼接的多行，每一行仍各占一个行号。第二，看的是当前记号所在的行，所以跨行宏调用中的 `__LINE__` 取它自己所在的那一行：

```cpp run title="line-in-invocation.cpp" ok
#define ID(x) x
int a = ID(
  __LINE__        // 第 3 行：结果是 3，不是 ID( 所在的第 2 行
);
int main() { return a == 3 ? 0 : 1; }
```

!!! lawyer "__LINE__ 写在替换列表里"
    `#define M() __LINE__` 之后，把 `M(` 写在第 3 行、`)` 写在第 4 行，`M()` 得到几？这里的当前预处理记号是定义处的 `__LINE__`、宏名还是闭合括号，标准没有更细的规定。本机 Clang 23 得到 4，即闭合括号所在的行。可移植的代码不应依赖跨行调用中 `__LINE__` 的精确值。

!!! impl "预处理输出里的 linemarker"
    `clang -E`、`gcc -E` 的输出里满是 `# 42 "file.cpp" 2` 这样的行，叫做 linemarker。它不是 `#line`：`#` 后面紧跟数字，不是任何指令名，按 [[cpp.pre#3]] 属于有条件支持的指令，含义由实现定义。GCC 和 Clang 用末尾的数字标志表示进入文件、返回文件、系统头文件等。`-P` 选项关闭这些行的输出。

## #error 与 #warning [cpp.error]

```cpp run title="warning.cpp" ok
#if __cplusplus < 202002L
#  error "需要 C++20"
#endif
#ifndef NDEBUG
#  warning "调试构建：性能数据不具代表性"
#endif
int main() {}
```

¶1 `#error` 使程序非良构，编译器必须拒绝它（[[intro.compliance]]）。`#warning` 只要求实现对这个翻译单元给出至少一条诊断，程序仍然良构，翻译照常进行。上面的程序在默认构建下编译成功，同时输出一条警告。

¶2 *Recommended practice*：两者产生的诊断信息应当包含指令里写的那些预处理记号。

`#warning` 是 C++23 加入的（[[P2437R1]]），与 C23 同步。GCC 和 Clang 早就把它作为扩展支持。

`#error` 最常见的用途是在条件编译中拒绝不支持的配置。它只能检查预处理期已知的东西，也就是宏的值（[[cpp.cond]]），检查 `sizeof`、类型性质要用 `static_assert`。

!!! pitfall "消息里的单引号"
    `#warning don't use this` 中的 `'` 不能和后面的字符组成字符字面量，只能单独成为一个记号。按 [[lex.pptoken#1]]，单独的 `'` 或 `"` 记号使程序非良构。于是这条本意只是告警的指令让程序非良构了。本机 Clang 23 只输出那条警告，照常编译，别的实现可能拒绝。把消息写成字符串字面量就没有这个问题：`#warning "don't use this"`。

## #pragma [cpp.pragma]

```cpp run title="pragma.cpp" ok
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wunused-variable"
int main() { int unused = 0; }
#pragma GCC diagnostic pop
```

¶1 `# pragma 记号...` 使实现以实现定义的方式行事。这种行为可以导致翻译失败，也可以让编译器或生成的程序以不符合标准的方式运行。实现不认识的 pragma 被忽略。

这给了实现很大的自由。`#pragma pack` 改变类的布局规则，`#pragma GCC optimize("fast-math")` 放宽浮点语义，都是标准允许的。标准对 pragma 的唯一约束就是不认识的要忽略。

- C++ 标准没有定义任何 pragma。C 标准定义了 `#pragma STDC FP_CONTRACT` 等 `STDC` 开头的 pragma，C++ 没有引入。`#pragma once` 也不是标准的（[[cpp.include]]）。
- 不认识就忽略，意味着 pragma 拼错了不会报错。GCC 和 Clang 的 `-Wunknown-pragmas`（包含在 `-Wall` 中）会对此给出警告。
- pragma 里的记号默认不做宏替换（[[cpp.pre#8]]），但实现可以对特定的 pragma 规定替换。例如 OpenMP 规范要求对 `#pragma omp` 后面的记号做宏替换。
- 不认识的 pragma 仍然是一条指令，所以出现在宏实参里依然非良构（[[cpp.replace.general#14]]）。

!!! impl "常见 pragma"
    | pragma | 作用 | 支持者 |
    |---|---|---|
    | `once` | 防止重复包含 | 全部主流 |
    | `pack(push, n)` / `pack(pop)` | 改变成员对齐 | 全部主流 |
    | `GCC diagnostic push/pop/ignored` | 局部开关警告 | GCC、Clang |
    | `clang diagnostic ...` | 同上 | Clang |
    | `warning(disable: 4996)` | 同上 | MSVC |
    | `push_macro("X")` / `pop_macro("X")` | 保存、恢复宏定义 | 全部主流 |
    | `omp parallel for` 等 | OpenMP | 开启 `-fopenmp` 时 |
    | `message("...")` | 编译时打印消息 | 全部主流 |

## 空指令 [cpp.null]

¶1 只有一个 `#` 的行没有任何效果。

```cpp
#
#  include <cstdio>
#
int main() {}
```

老代码有时用单独的 `#` 在指令块之间做视觉分隔，代码生成器也常常产生空指令。它是 [[cpp.pre]] 文法中正式的 `# new-line`，与 `#` 后面跟着非指令名的有条件支持的指令不是一回事。

## _Pragma 运算符 [cpp.pragma.op]

### 为什么需要它

宏展开的结果不会被当作指令（[[cpp.rescan#4]]），所以宏无法生成 `#pragma`。`_Pragma` 是一个运算符，不是指令：它可以出现在普通代码里，也可以由宏展开产生，在翻译第 4 阶段执行，效果与一条 `#pragma` 相同。它来自 C99，由 C++11 引入（[[N1653]]）。

```cpp run title="pragma-op.cpp" ok
#define DO_PRAGMA(x) _Pragma(#x)
#define DIAG_PUSH        DO_PRAGMA(GCC diagnostic push)
#define DIAG_IGNORE(w)   DO_PRAGMA(GCC diagnostic ignored w)
#define DIAG_POP         DO_PRAGMA(GCC diagnostic pop)

DIAG_PUSH
DIAG_IGNORE("-Wunused-variable")
int main() { int unused = 0; }
DIAG_POP
```

Boost、fmt、Abseil 等跨平台库里局部关闭警告的宏，基本都是这样写的。`DIAG_IGNORE("-Wunused-variable")` 中的字符串经 `#x` 变成 `"GCC diagnostic ignored \"-Wunused-variable\""`，`_Pragma` 再把它还原。

### 反字符串化（¶1）

¶1 `_Pragma ( 字符串字面量 )` 按以下步骤处理：

1. 对字符串字面量做[[g:destringize|反字符串化]]（destringize）：删除编码前缀（如果有），删除首尾的双引号，把每个 `\"` 换成 `"`，每个 `\\` 换成 `\`。
2. 得到的字符序列经过翻译第 3 阶段切成预处理记号，这些记号如同 `#pragma` 指令里的记号一样执行。
3. 原来的四个记号 `_Pragma`、`(`、字符串字面量、`)` 被删除。

只处理 `\"` 和 `\\`，其他转义序列如 `\n` 原样保留为两个字符。这正好是 `#` 字符串化（[[cpp.stringize#2]]）的逆运算：字符串化在字面量内部的 `"` 和 `\` 前加 `\`，反字符串化把它们去掉。所以 `_Pragma(#x)` 能准确还原 `x` 的记号。

¶2 的例子展示了这个往返过程：

```cpp
#pragma listing on "..\listing.dir"
// 等价于
_Pragma ( "listing on \"..\\listing.dir\"" )

// 由宏生成时效果也一样：
#define LISTING(x) PRAGMA(listing on #x)
#define PRAGMA(x) _Pragma(#x)
LISTING( ..\listing.dir )
```

`LISTING( ..\listing.dir )` 先得到 `PRAGMA(listing on "..\listing.dir")`。这里的 `#x` 字符串化时，`\` 在字面量之外，不加转义。`PRAGMA` 的 `#x` 再字符串化一次，这次 `"..\listing.dir"` 是一个字符串字面量，其中的 `"` 和 `\` 都要转义，得到 `"listing on \"..\\listing.dir\""`。最后 `_Pragma` 反字符串化，还原为 `listing on "..\listing.dir"`。本机 Clang 23 `-E` 输出 `#pragma listing on "..\listing.dir"`。

!!! pitfall "_Pragma 只接受一个字符串字面量"
    相邻字符串字面量在第 6 阶段才拼接，而 `_Pragma` 在第 4 阶段执行，所以 `_Pragma("GCC diagnostic " "push")` 不行，本机 Clang 23 报 `_Pragma takes a parenthesized string literal`。需要拼接时，在宏里用 `#` 把整个 pragma 内容一次字符串化。

!!! lawyer "_Pragma 何时执行"
    在普通代码中，`_Pragma` 在预处理器扫描到它时执行；在宏展开结果中，它在完全替换之后执行（[[cpp.rescan#4]]）。在 `#define` 的替换列表里，它既不展开也不执行，直到宏被使用。`_Pragma` 作为宏实参出现时，是在实参预先展开时执行，还是在外层宏完全替换之后执行，标准没有更细的说明，诊断类 pragma 的生效位置在不同编译器上可能与预期不符。稳妥的做法是让 `_Pragma` 直接写在宏的替换列表里，不要作为实参传入。

## 历史与演进

!!! history
    - C++98 的 `#line`、`#error`、`#pragma` 和空指令都与 C89 一致。
    - C++11 从 C99 引入 `_Pragma`（[[N1653]]）。
    - C++23 加入 `#warning`（[[P2437R1]]）。
    - C++23 之后的新措辞把 `#line` 超出 [1, 2147483647] 的情形从未定义行为改为有条件支持，并把行号精确定义为到当前预处理记号为止的物理行号。

## 思考题

!!! question "思考题 1"
    ```cpp
    #define STR(x) #x
    #define P(x) _Pragma(STR(x))
    P(message("hi"))
    ```
    这能工作吗？与 `#define P(x) _Pragma(#x)` 有区别吗？

<details markdown="1">
<summary>答案</summary>

能工作，这里两种写法结果相同。`P` 的形参 `x` 不是 `#` 的操作数，所以实参 `message("hi")` 先完全展开（没有变化），代入后得 `_Pragma(STR(message("hi")))`。再扫描时 `STR(...)` 展开为 `"message(\"hi\")"`，`_Pragma` 在完全替换之后执行，反字符串化得到 `message("hi")`。

实参里有宏时就有区别。设 `#define MSG "hi"`，`P(message(MSG))` 经 `STR` 间接字符串化，`MSG` 先被展开，pragma 收到 `message("hi")`；`_Pragma(#x)` 直接字符串化，pragma 收到 `message(MSG)`。pragma 自己是否再展开 `MSG` 由实现决定。Clang 的 `#pragma message` 恰好会展开它的参数，所以本机 Clang 23 对两种写法都打印 `hi`；对不展开参数的 pragma，两者的效果就不同了。
</details>

!!! question "思考题 2"
    `#line 0` 合法吗？`#line 2147483648` 呢？`#line 0x10` 呢？

<details markdown="1">
<summary>答案</summary>

`#line 0` 和 `#line 2147483648` 的数字都超出了 [1, 2147483647]，按 ¶3 是有条件支持的：实现可以支持，不支持就必须诊断。本机 Clang 23 都接受，对前者给出 `-Wgnu-zero-line-directive` 警告，对后者给出 `-Wpedantic` 警告。

`#line 0x10` 中的 `0x10` 不是数字序列，不符合 ¶3、¶4 的形式；按 ¶5 做宏替换后仍然不符合，所以非良构。本机 Clang 23 报错 `#line directive requires a simple digit sequence`。
</details>
