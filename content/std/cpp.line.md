---
title: 行控制
summary: #line 如何改写"假定的"行号与文件名（及行号的精确定义），#error 与 C++23 的 #warning，实现定义的 #pragma，什么也不做的空指令 #，以及能由宏生成的 _Pragma 运算符和它的"反字符串化"规则。
status: draft
covers: cpp.error, cpp.pragma, cpp.null, cpp.pragma.op
related: cpp.predefined, cpp.pre, cpp.rescan, support.srcloc, intro.compliance, lex.pptoken
tags: 预处理, 诊断, pragma
updated: 2026-10-18
---

本页合并了第 15 章中五个短小的小节，它们都是"杂项"指令，但各有值得深究的细节：

| 小节 | 指令 | 一句话 |
|---|---|---|
| [[cpp.line]] | `#line` | 改写 `__LINE__`/`__FILE__` 所报告的位置 |
| [[cpp.error]] | `#error`、`#warning` {{c++23}} | 主动报错 / 主动告警 |
| [[cpp.pragma]] | `#pragma` | 实现定义的一切 |
| [[cpp.null]] | `#` | 什么也不做 |
| [[cpp.pragma.op]] | `_Pragma("...")` | 可以由宏生成的 `#pragma` |

## 行控制（cpp.line）

`#line` 主要服务于**生成代码**的工具：bison/yacc、flex、Qt 的 moc、各种模板引擎把用户写的 `.y`、`.l` 文件翻译成 `.cpp`，并在其中插入 `#line`，让编译错误和调试信息指回**原始文件**的原始行，而不是生成文件中的某一行。

### 字符串必须无前缀（¶1）

¶1：`#line` 中若有 *string-literal*，它必须是**字符串字面量**（*character string literal*，即无前缀的 *string-literal*，[[cpp.stringize#2]] 中定义）。`#line 10 u8"x.cpp"` 非良构；Clang 报 `invalid filename for #line directive`。

### 行号是什么（¶2）

¶2：当前源行的[[g:line-number|行号]]是当前**物理**源行的行号，即：处理源文件直到**当前预处理记号**为止，在阶段 1 中读到或引入的换行字符的个数加一。

两点值得注意：

1. **物理行**，不是逻辑行。行拼接（阶段 2 的反斜杠-换行）不影响计数：被拼接的每一行仍各占一个行号。
2. **"到当前预处理记号为止"**：对于跨行的宏调用，`__LINE__` 记号自己在哪一行，就是哪一行：

```cpp run title="line-in-invocation.cpp" ok
#define ID(x) x
int a = ID(
  __LINE__        // 这是第 3 行：结果为 3，而不是 ID( 所在的第 2 行
);
int main() { return a == 3 ? 0 : 1; }
```

!!! lawyer "__LINE__ 来自替换列表时"
    若 `__LINE__` 出现在某个宏的**替换列表**里，"当前预处理记号"是哪一个就不那么清楚了：是定义处的 `__LINE__`？宏名所在行？闭合括号所在行？标准没有更细的规定。Clang 23 实测：`#define M() __LINE__` 后，`M(` 写在第 7 行、`)` 写在第 8 行，结果是 8——Clang 取的是整个调用的**展开位置**，即闭合括号处。可移植代码不应依赖跨行调用中 `__LINE__` 的精确值。

### 三种形式（¶3–¶5）

- ¶3 `# line digit-sequence new-line`：此后的源行如同从指定行号开始。数字序列按**十进制**解释——`#line 010` 设置行号 10，不是八进制的 8（Clang 对此特意给出警告）。范围 `[1, 2147483647]` 之外的值是**有条件支持**的（C++23 及以前是 UB）。
- ¶4 `# line digit-sequence "s-char-sequence(opt)" new-line`：同时设置**假定的**（*presumed*）源文件名。
- ¶5 `# line pp-tokens new-line`（不匹配前两种）：其中的记号像普通文本一样做宏展开，展开后必须匹配前两种之一，否则非良构。

```cpp run title="line.cpp" ok
#include <source_location>
#line 100 "fake.cpp"
constexpr auto loc = std::source_location::current();
static_assert(loc.line() == 100);                      // #line 之后的第一行就是 100
#define N 200
#define F "other.cpp"
#line N F                                              // 宏形式
static_assert(__LINE__ == 200);
int main() {}
```

`std::source_location` 报告的同样是**假定的**行号和文件名（[[support.srcloc]] 引用 [[cpp.predefined]] 的定义），所以 `#line` 对它同样生效。

!!! impl "GNU linemarker"
    `clang -E`/`gcc -E` 的输出中满是 `# 42 "file.cpp" 2` 这样的行。它**不是** `#line`：`#` 后面紧跟的是一个 *pp-number*，不是任何指令名——按 [[cpp.pre#3]]，这是一个**条件支持的指令**，由 GCC 和 Clang 以实现定义的方式支持（尾部的数字标志表示"进入/返回文件""系统头文件"等）。`-P` 选项关闭这些标记的输出。

## 诊断指令（cpp.error）

¶1：

- `# error pp-tokens(opt) new-line` 使程序**非良构**。
- `# warning pp-tokens(opt) new-line` 要求实现为该预处理翻译单元产生**至少一条诊断消息**（[[intro.compliance]]）。

¶2 推荐做法：两者产生的诊断消息应当包含指定的预处理记号序列。

`#warning` 是 C++23 新增的（[[P2437R1]]，与 C23 同步），但 GCC、Clang 早就作为扩展支持它。它与 `#error` 的区别在于**不影响良构性**：程序仍然是良构的，翻译继续，只是必须有一条诊断。

```cpp run title="warning.cpp" ok std=c++23 flags="-std=c++23 -Wno-#warnings"
#if __cplusplus < 202002L
#  error "需要 C++20"
#endif
#ifndef NDEBUG
#  warning "调试构建：性能数据不具代表性"
#endif
int main() {}
```

（示例用 `-Wno-#warnings` 关闭了 Clang 对 `#warning` 的输出，以满足"零警告"——注意这在形式上让 Clang 不再满足"必须产生诊断"，这正是实现提供的非一致性开关。）

!!! pitfall "#error 和 #warning 的消息仍然要能切成预处理记号"
    `#warning don't use this` 里的 `'` 是一个孤立的单引号。按 [[lex.pptoken#2]]，单独的 `'` 落入"其他单个非空白字符"一类时程序**非良构**——于是一条本意只是告警的 `#warning` 让程序非良构了。Clang 23 对此**不诊断**，原样输出消息。可移植写法：把消息写成字符串字面量，`#warning "don't use this"`。（`#error` 反正已经非良构，影响不大；但若它位于**被处理**的组中、而你本意是"永远不会到这里"，也同理。）

`#error` 最常见的用途是在条件编译中拒绝不支持的配置；在 `static_assert` 出现之前，它也是唯一的"编译期断言"手段——但它只能检查预处理期可知的东西（宏），不能检查 `sizeof`、类型特征等（[[cpp.cond]]）。

## pragma 指令（cpp.pragma）

¶1：`# pragma pp-tokens(opt) new-line` 使实现以**实现定义**的方式行为。这种行为**可以**导致翻译失败，或导致翻译器或生成的程序以**不符合标准**的方式运行。实现**不认识**的 pragma 被**忽略**。

这一段给 pragma 开了极大的口子：一个 pragma 可以让编译器做任何事，包括违反标准（例如 `#pragma pack` 改变类布局的规则、`#pragma GCC optimize("fast-math")` 放松浮点语义）。标准对此唯一的约束是：**不认识就忽略**。

```cpp run title="pragma.cpp" ok
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wunused-variable"
int main() { int unused = 0; }
#pragma GCC diagnostic pop
```

几个要点：

- **C++ 标准没有定义任何 pragma。**（C 标准定义了 `#pragma STDC FP_CONTRACT` 等 `STDC` 前缀的 pragma；C++ 没有引入。）`#pragma once` 也不是标准的（[[cpp.include]]）。
- "不认识则忽略"意味着 pragma 拼错了**不会报错**。GCC/Clang 用 `-Wunknown-pragmas`（包含在 `-Wall` 中）提示。
- pragma 中的记号默认**不做宏展开**（[[cpp.pre#8]]）；但实现可以对特定 pragma 规定展开——例如 OpenMP 规范要求 `#pragma omp` 之后的记号做宏替换。
- 不认识的 pragma 被忽略，但它仍然是一条指令：宏实参中出现 `#pragma` 依然非良构（[[cpp.replace.general#14]]）。

!!! impl "常见 pragma"
    | pragma | 作用 | 支持者 |
    |---|---|---|
    | `once` | 防止重复包含 | 全部主流 |
    | `pack(push, n)` / `pack(pop)` | 改变成员对齐 | 全部主流 |
    | `GCC diagnostic push/pop/ignored` | 局部开关警告 | GCC、Clang |
    | `clang diagnostic ...` | 同上 | Clang |
    | `warning(disable: 4996)` | 同上 | MSVC |
    | `push_macro("X")` / `pop_macro("X")` | 保存/恢复宏定义 | 全部主流 |
    | `omp parallel for` 等 | OpenMP | 开启 `-fopenmp` 时 |
    | `message("...")` | 编译时打印消息 | 全部主流 |

## 空指令（cpp.null）

¶1：`# new-line` 没有任何效果。

它存在的理由主要是历史和美观：

```cpp
#
#  include <cstdio>
#
int main() {}
```

一些老代码用单独的 `#` 作为指令块之间的视觉分隔；代码生成器也常常产生空指令。注意它与 [[cpp.pre]] 中的"条件支持的指令"不同：后者是 `#` 后跟**非**指令名的东西，而空指令 `#` 后面什么都没有，它是标准的 *control-line*（[[cpp.pre]] 文法中的 `# new-line`）。

## _Pragma 运算符（cpp.pragma.op）

### 为什么需要它

宏不能生成指令（[[cpp.pre#2]]、[[cpp.rescan#4]]），所以下面的写法行不通：

```cpp
#define NO_WARN #pragma GCC diagnostic ignored "-Wunused"   // # 在函数式宏中要求后跟形参；在对象式宏中只是普通记号
```

`_Pragma` 是一个**运算符**，不是指令。它可以出现在普通文本中，也可以由宏展开产生，然后在阶段 4 中被执行，效果等同于一条 `#pragma`。它来自 C99，C++11 引入（[[N1653]]）。

### 反字符串化（¶1）

¶1：形如 `_Pragma ( string-literal )` 的一元运算符表达式按如下方式处理：

1. 对 *string-literal* 进行[[g:destringize|反字符串化]]（*destringize*）：删除编码前缀（若有）；删除首尾的双引号；把每个转义序列 `\"` 替换为 `"`，每个 `\\` 替换为 `\`。
2. 得到的字符序列经过**翻译阶段 3** 产生预处理记号，这些记号**如同** pragma 指令中的 *pp-tokens* 那样被执行。
3. 原来的四个预处理记号（`_Pragma`、`(`、字符串字面量、`)`）被删除。

只处理 `\"` 和 `\\`——其他转义序列（如 `\n`）**原样保留**为两个字符。这恰好是 `#` 字符串化（[[cpp.stringize#2]]）的逆运算：字符串化在字面量内部的 `"` 和 `\` 前加 `\`，反字符串化去掉它们。所以 `_Pragma(#x)` 能精确还原 `x` 的记号。

### 标准例子（¶2）

```cpp
#pragma listing on "..\listing.dir"
// 等价于
_Pragma ( "listing on \"..\\listing.dir\"" )
```

反字符串化：去掉外层引号，`\"` → `"`，`\\` → `\`，得到 `listing on "..\listing.dir"`，正是第一行 `#pragma` 后面的内容。

后一种形式无论是字面写出、还是由宏替换产生，处理方式都相同：

```cpp
#define LISTING(x) PRAGMA(listing on #x)
#define PRAGMA(x) _Pragma(#x)
LISTING( ..\listing.dir )
```

推演：`LISTING( ..\listing.dir )` → `PRAGMA(listing on "..\listing.dir")`（`#x` 字符串化，`\` 在字面量之外，不转义）。`PRAGMA` 的 `#x` 把 `listing on "..\listing.dir"` 字符串化：其中的字符串字面量 `"..\listing.dir"` 内部的 `"` 和 `\` 被转义，得到 `"listing on \"..\\listing.dir\""`。最后 `_Pragma` 反字符串化，还原为 `listing on "..\listing.dir"`。Clang 23 `-E` 输出 `#pragma listing on "..\listing.dir"`，与标准一致。

### 实用模式

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

这是几乎所有跨平台库（Boost、fmt、Abseil……）中"局部关闭警告"宏的标准实现方式。注意 `DIAG_IGNORE("-Wunused-variable")` 中的字符串经 `#x` 变成 `"\"-Wunused-variable\""`，再经 `_Pragma` 反字符串化还原为 `"-Wunused-variable"`。

!!! pitfall "_Pragma 只接受单个字符串字面量"
    相邻字符串字面量的拼接在阶段 6，而 `_Pragma` 在阶段 4 执行，所以 `_Pragma("GCC diagnostic " "push")` 不行——文法只允许一个 *string-literal*。Clang 报 `_Pragma takes a parenthesized string literal`。需要拼接时，用 `#` 在宏中一次性字符串化整个 pragma 内容。

!!! lawyer "_Pragma 何时执行"
    在普通文本中，`_Pragma` 在预处理器扫描到它时执行。在宏展开结果中，它在**完全宏替换之后**执行（[[cpp.rescan#4]]）。在指令中（例如 `#define X _Pragma("once")` 的替换列表里），记号不被展开也不被执行，直到 `X` 在文本中被展开。`_Pragma` 若作为宏**实参**出现，它是在实参预先展开时执行，还是在外层宏完全替换之后执行？标准没有更细的说明。实践中，诊断类 pragma 经由宏实参传递时，各编译器（尤其是 GCC 的较早版本）出现过生效位置与预期不符的问题；稳妥的做法是让 `_Pragma` 直接出现在宏的替换列表中，而不是作为实参传入。

## 历史与演进

!!! history
    - **C++98**：`#line`、`#error`、`#pragma`、空指令，与 C89 一致。
    - **C++11**：`_Pragma`（来自 C99，[[N1653]]）。
    - **C++23**：`#warning`（[[P2437R1]]）。
    - **当前草案**：`#line` 超出 `[1, 2147483647]` 的值由 UB 改为有条件支持；行号被精确定义为"到当前预处理记号为止"的物理行号。

## 思考题

!!! question "思考题 1"
    ```cpp
    #define STR(x) #x
    #define P(x) _Pragma(STR(x))
    P(message("hi"))
    ```
    这能工作吗？与 `#define P(x) _Pragma(#x)` 有区别吗？

<details markdown="1">
<summary>展开查看答案与解析</summary>

能工作，而且结果相同。`P` 的 `x` 不是 `#` 的操作数，所以实参 `message("hi")` 先完全展开（不变），代入后得 `_Pragma(STR(message("hi")))`。重新扫描时 `STR(...)` 被展开为 `"message(\"hi\")"`，于是 `_Pragma("message(\"hi\")")` 在完全替换之后被执行，反字符串化为 `message("hi")`。

区别出现在实参中有宏时：`#define MSG "hi"`，`P(message(MSG))` 经 `STR` 间接字符串化，`MSG` 会先被展开，得到 `message("hi")`；而 `_Pragma(#x)` 直接字符串化，得到 `message(MSG)`——pragma 收到的是未展开的 `MSG`。至于 pragma 自己会不会再展开 `MSG`，那是实现定义的：Clang 的 `#pragma message` 恰好会对其参数做宏展开，所以 Clang 23 对两种写法都打印 `hi`（`-E` 的输出也都是 `#pragma message("hi")`）；对不展开参数的 pragma，两者就不同了。
</details>

!!! question "思考题 2"
    `#line 0` 合法吗？`#line 2147483648` 呢？`#line 0x10` 呢？

<details markdown="1">
<summary>展开查看答案与解析</summary>

- `#line 0` 与 `#line 2147483648`：数字超出 `[1, 2147483647]`，按 ¶3 是**有条件支持**的——实现可以支持（赋予某种语义），不支持则必须诊断。Clang 23 对前者给 `-Wgnu-zero-line-directive`，对后者给 `-Wpedantic` 警告，都接受。
- `#line 0x10`：`0x10` 不是 *digit-sequence*（`x` 不是数字），不匹配 ¶3、¶4 的形式；按 ¶5 做宏展开后仍不匹配，非良构。
</details>

## 小结

!!! summary
    - `#line n "f"` 改写**假定**的行号与文件名，影响 `__LINE__`、`__FILE__`、`std::source_location`；行号按十进制解释，`[1, 2147483647]` 之外有条件支持；文件名不得带前缀。
    - 行号 = 到当前预处理记号为止的物理行号；跨行宏调用中的 `__LINE__` 取值不可完全依赖。
    - `#error` 使程序非良构；`#warning`（C++23）只要求一条诊断。消息仍需是合法的预处理记号，避免孤立的 `'`。
    - `#pragma` 行为实现定义，可以让实现不符合标准；不认识的 pragma 被忽略。C++ 没有标准 pragma。
    - `#` 单独一行是空指令。
    - `_Pragma("...")` 可以由宏产生：反字符串化（去前缀、去引号、`\"`→`"`、`\\`→`\`）后按 `#pragma` 执行；只接受单个字符串字面量。
