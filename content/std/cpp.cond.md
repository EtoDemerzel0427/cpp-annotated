---
title: 条件包含
summary: #if/#elif 的控制表达式如何求值（宏展开 → defined/__has_include/__has_embed/__has_cpp_attribute → 其余标识符变 0 → 以 intmax_t/uintmax_t 算术求值），#ifdef 家族（含 C++23 的 #elifdef/#elifndef），以及被跳过的组如何处理。
status: draft
related: cpp.pre, cpp.include, cpp.embed, cpp.predefined, expr.const, dcl.attr.grammar, lex.icon
tags: 预处理, 条件编译, 特性检测
updated: 2026-10-18
---

条件包含（*conditional inclusion*）就是 `#if` 家族：根据编译期条件决定哪些源码进入翻译单元。它是可移植代码、平台适配、特性检测的基础设施。

本节的难点不在语法，而在**控制表达式的求值模型**：它发生在阶段 4，那时还没有关键字、没有类型、没有声明——只有预处理记号和宏。于是 `#if sizeof(int) == 4` 不会做你以为的事，`#if new` 合法且为假，`#if -1 > 0u` 为真。下面逐段拆开。

前置知识：预处理记号与记号的区别（[[lex.pptoken]]）；整数常量表达式（[[expr.const]]）；指令的识别（[[cpp.pre]]）。

## 文法与可用的"运算符"（¶1）

控制表达式**应当是整数常量表达式**，但有两点例外：

1. 标识符（包括与关键字拼写相同的）按下文 ¶10 的方式解释（脚注 115：阶段 4 中所有标识符要么是宏名、要么不是——不存在关键字、枚举量之类）；
2. 可以包含四种"一元运算符表达式"：

| 表达式 | 形式 | 结果 | 引入 |
|---|---|---|---|
| *defined-macro-expression* | `defined X` 或 `defined ( X )` | 0 / 1 | C++98 |
| *has-include-expression* | `__has_include( <h> )`、`__has_include( "h" )` 或宏展开后形成的等价形式 | 0 / 1 | C++17 |
| *has-embed-expression* | `__has_embed( 资源 参数... )` | `__STDC_EMBED_NOT_FOUND__`/`_FOUND__`/`_EMPTY__`（0/1/2） | C++26 {{c++26}} |
| *has-attribute-expression* | `__has_cpp_attribute( 属性记号 )` | 0 或非零版本号 | C++20 |

¶1 末句：*defined-macro-expression* 不得出现在 `__has_include` 或 `__has_embed` 的括号里。

## defined（¶2）

`defined X` 的值为 1 当且仅当 `X` **当前**被定义为宏名：它是预定义宏，或者有一个或多个**活跃的宏定义**（[[cpp.import#5]]）——例如被 `#define` 过且之后没有 `#undef`。否则为 0。

"活跃的宏定义"这个措辞来自模块：通过 `import "h.h";` 导入的宏也算（[[cpp.import]]）。

```cpp run title="defined.cpp" ok
#define A
#define B 0
#if defined A && defined(B) && !defined C
static_assert(true);   // 被包含：B 虽然值为 0，但它是定义了的
#endif
int main() {}
```

`defined` 只关心"是否定义"，不关心值。这是 `#ifdef FEATURE` 和 `#if FEATURE` 的根本区别：前者在 `#define FEATURE 0` 时为真，后者为假。

## __has_include（¶3）

`__has_include( ... )` 把括号中的记号当作 `#include` 指令的 *pp-tokens* 去搜索（[[cpp.include]]），但**不再做宏展开**（展开已在 ¶9 完成过一次）；找到为 1，找不到为 0。若括号内的记号不是单个 *header-name*，也无法按 [[cpp.include#7]] 拼成一个 *header-name*，程序非良构。

```cpp run title="has-include.cpp" ok
#if __has_include(<version>)
#  include <version>
#endif
#define HDR "no_such_header.h"
#if __has_include(HDR)          // HDR 在 ¶9 中被展开为 "no_such_header.h"
#  error unexpected
#endif
int main() {}
```

注意 [[cpp.include#6]] 的注 1：如果找到了文件但实现**无法处理**它（比如它是个目录或权限不足），即使只是在 `__has_include` 里探测，程序也非良构——`__has_include` 回答的是"找得到吗"，不是"能用吗"。

!!! tip "__has_include 不能替代特性检测"
    `<optional>` 存在不代表 `std::optional` 可用：老版本标准库在 `-std=c++14` 下也可能提供 `<optional>` 但其内容被 `#if` 掉。标准例 1（¶14）的写法——先 `__has_include` 再检查 `__cpp_lib_optional`——才是稳妥的。在 C++20 之后，最好直接 `#include <version>` 再检查库特性宏。

## __has_embed（¶4）{{c++26}}

`__has_embed( 资源 参数... )` 把括号内的记号当作 `#embed` 指令的 *pp-tokens* 处理（[[cpp.embed]]），同样不再做宏展开。结果是三值的：

- ¶4.1 找到资源、所有参数都受支持、资源**非空** → `__STDC_EMBED_FOUND__`（1）；
- ¶4.2 否则，若找到、参数都受支持、资源**为空** → `__STDC_EMBED_EMPTY__`（2）；
- ¶4.3 否则 → `__STDC_EMBED_NOT_FOUND__`（0）。

注 1：不认识的参数**不会**导致非良构，只算"不受支持"，结果为 0。这让 `__has_embed` 同时充当了"实现支持这个 vendor 参数吗"的探测器。

"空"是按 *resource-count* 判断的，所以 `limit(0)` 会让任何存在的资源都被视为空（[[cpp.embed.param.if.empty]] 例 2）。

```cpp run title="has-embed.cpp" ok flags="-std=c++2c -Wno-c23-extensions"
#if __has_embed(__FILE__) != __STDC_EMBED_FOUND__
#  error "源文件自身应当可以被 embed"
#endif
#if __has_embed(__FILE__ limit(0)) != __STDC_EMBED_EMPTY__
#  error "limit(0) 使资源为空"
#endif
#if __has_embed(__FILE__ acme::frobnicate) != __STDC_EMBED_NOT_FOUND__
#  error "不认识的参数 → 不受支持 → 0"
#endif
#if __has_embed("no/such/resource") != __STDC_EMBED_NOT_FOUND__
#  error "找不到"
#endif
int main() {}
```

（这里 `__FILE__` 在 ¶9 中被展开为当前文件名的字符串字面量，然后作为 *header-name-tokens* 使用。Clang 23 在 C++ 模式下把 `#embed` 视为扩展，并对每次使用给出 `-Wc23-extensions` 警告，故示例关闭该警告。）

## __has_cpp_attribute（¶5–¶6）

`__has_cpp_attribute( pp-tokens )`：把 *pp-tokens* **宏展开后**解释为一个 *attribute-token*（`name` 或 `ns::name`）；实现支持该属性则替换为一个非零的、整数字面量形式的 *pp-number*，否则为 0。若 *pp-tokens* 不符合 *attribute-token* 的形式，非良构。

注意与 `__has_include`/`__has_embed` 的区别：这里的宏展开是**明文要求**的。所以 `#define NS gnu` 之后 `__has_cpp_attribute(NS::always_inline)` 检查的是 `gnu::always_inline`。

¶6：对本文档规定的属性，值是 0 还是表 21 中的值，由实现定义；对实现认识的其他属性，值由实现定义。注 2：可以期待"任何非零值都表示可用"。

表 21 的当前值：

| 属性 | 值 | 属性 | 值 |
|---|---|---|---|
| `assume` | `202207L` | `maybe_unused` | `201603L` |
| `deprecated` | `201309L` | `no_unique_address` | `201803L` |
| `fallthrough` | `201603L` | `nodiscard` | `201907L` |
| `indeterminate` | `202403L` | `noreturn` | `200809L` |
| `likely` | `201803L` | `unlikely` | `201803L` |

（当前草案的表中已经没有 `carries_dependency`，见 [[dcl.attr]]。）

为什么允许标准属性返回 0？因为"实现**认识**这个属性"和"实现**利用**这个属性"是两回事。比如 MSVC 认识 `[[no_unique_address]]` 但出于 ABI 原因不改变布局，于是报 0，让用户改用 `[[msvc::no_unique_address]]`。各属性小节中的推荐做法也是这个精神：例如实现不能发出弃用诊断时，`deprecated` 的值应为 0（[[dcl.attr.deprecated#4]]）；`fallthrough` 不能抑制贯穿警告时应为 0（[[dcl.attr.fallthrough#2]]）。

```cpp run title="has-attr.cpp" ok
#if __has_cpp_attribute(nodiscard) >= 201907L
#  define NODISCARD(msg) [[nodiscard(msg)]]   // C++20 起 nodiscard 可带理由
#elif __has_cpp_attribute(nodiscard)
#  define NODISCARD(msg) [[nodiscard]]
#else
#  define NODISCARD(msg)
#endif
NODISCARD("check the error") int f() { return 0; }
int main() { return f(); }
```

!!! impl "实测（Clang 23）"
    `__has_cpp_attribute(indeterminate)` 为 0（尚未实现），`assume` 为 `202207L`，`nodiscard` 为 `201907L`；`carries_dependency` 仍报 `200809L`（Clang 早于草案删除该属性的版本）；`gnu::always_inline`、`clang::fallthrough` 都为 1。

## 这三个名字是"伪宏"（¶7）

`#ifdef`、`#ifndef`、`#elifdef`、`#elifndef` 以及 `defined` 运算符应把 `__has_include`、`__has_embed`、`__has_cpp_attribute` **当作已定义的宏名**。这让代码可以先检测"编译器是否支持 `__has_include` 本身"：

```cpp run title="detect-has-include.cpp" ok
#if defined(__has_include)
#  if __has_include(<version>)
#    include <version>
#  endif
#endif
int main() {}
```

¶7 末句：这三个标识符不得出现在本节未提及的其他上下文。所以 `#define __has_include ...`、在普通代码里写 `__has_include(x)` 都是非良构的。

!!! pitfall "不要把它们写在同一个 #if 里"
    `#if defined(__has_include) && __has_include(<x>)` 在一个**不支持** `__has_include` 的老编译器上依然会失败：`&&` 右边的 `__has_include(<x>)` 照样要被切成记号、做宏替换，然后标识符 `__has_include` 变成 0，剩下 `0(<x>)`——语法错误。在老编译器上 `&&` 的短路不能救你，因为语法错误发生在求值之前。所以要像上例那样嵌套两层 `#if`。

## #if 与 #elif（¶8–¶11）

¶8：`#if` 和 `#elif` 检查控制常量表达式的值是否非零。求值流程分四步，这是本节最重要的部分：

```text
① 宏展开（defined 的操作数除外）                 ¶9
② 求值 defined / __has_include / __has_embed / __has_cpp_attribute   ¶10
③ 剩余标识符（含"关键字"）除 true/false 外 → 0    ¶10
④ 预处理记号 → 记号，按常量表达式规则求值，
   所有整数类型视作 intmax_t / uintmax_t          ¶11
```

### 第一步：宏展开（¶9）

¶9：求值前，控制表达式中的宏调用像普通文本一样被替换——**除了** `defined` 的操作数。

¶9 还规定了三种违规：

1. 在 `__has_embed(` 与配对的 `)` 之间做宏替换时，如果遇到被定义为宏的 `limit`、`prefix`、`suffix`、`if_empty`，非良构（与 [[cpp.pre#4]] 对应）。
2. 若替换**产生了** `defined` 记号：{{ifndr}}。
3. 若 `defined` 的用法在宏替换**之前**不符合两种形式之一：{{ifndr}}。

```cpp run title="defined-from-macro.cpp" ifndr
#define A
#define HAS_A defined(A)
#if HAS_A          // IFNDR：宏展开产生了 defined
#endif
int main() {}
```

为什么不直接规定行为？因为历史上各实现对此行为不一（例如宏展开中途产生的 `defined` 的操作数是否还会被展开），标准选择不去统一它。GCC、Clang 照常求值。C++23 及以前此处是 UB；当前草案改为 IFNDR，表示"违规，但不要求诊断"。Clang 给 `-Wexpansion-to-defined` 警告（其措辞仍然说 "has undefined behavior"）。

可移植的写法是让宏展开为 0/1：

```cpp run title="defined-portable.cpp" ok
#define A
#if defined(A)
#  define HAS_A 1
#else
#  define HAS_A 0
#endif
#if HAS_A
#endif
int main() {}
```

### 第二、三步：标识符变成 0（¶10）

¶10：所有宏替换和四种特殊表达式求值完成后，剩下的标识符——**包括拼写与关键字相同的**——除了 `true` 和 `false`，统统替换为 *pp-number* `0`；然后每个预处理记号被转换为记号。

```cpp run title="ident-zero.cpp" ok
#if new == 0 && sizeof == 0 && undefined_thing == 0
// 全部成立：阶段 4 没有关键字，它们都只是未定义为宏的标识符
#endif
#if true && !false
// true/false 是例外，保持布尔字面量的含义
#endif
int main() {}
```

这条规则最大的坑是：**拼错的宏名不会报错**。

```cpp
#if HAVE_THREDS     // 拼错了 → 0 → 静悄悄地选错分支
```

GCC/Clang 提供 `-Wundef` 来警告"未定义的标识符在 #if 中被当作 0"。

注 3：**替代记号**（`and`、`or`、`not`、`bitand` …，[[lex.digraph]]）不是标识符，即使它们全由字母组成，所以不会被替换为 0，而是正常地作为运算符：

```cpp run title="alt-tokens-in-if.cpp" ok
#if not 0 and (1 bitor 0)
// 成立：not、and、bitor 是运算符
#endif
int main() {}
```

!!! lawyer "sizeof 与类型转换在 #if 中"
    `#if sizeof(int) == 4` 中 `sizeof` 和 `int` 都变成 0，得到 `0(0) == 4`——`0(0)` 不是合法的表达式（不能"调用"一个整数），非良构。同理 `#if (long)1` 变成 `(0)1`，也是语法错误。阶段 4 完全没有类型。要在预处理期获知类型大小，只能依赖实现预定义的宏（如 GCC/Clang 的 `__SIZEOF_INT__`）或 `<climits>` 中的宏。

### 第四步：在 intmax_t / uintmax_t 中求值（¶11）

¶11：得到的记号构成控制常量表达式，按 [[expr.const]] 的规则求值，算术范围至少是 [[support.limits]] 规定的范围。在这次转换与求值中，**所有有符号整数类型和无符号整数类型分别如同具有与 `intmax_t` 和 `uintmax_t` 相同的表示**。

这句话的后果：

1. **字面量的类型变了**。注 4：在 `int` 为 16 位的实现上，`0x8000` 在 #if 中是**有符号正数**（`intmax_t` 装得下），而在阶段 7 是 `unsigned int`。
2. **所有运算都在最宽类型中进行**。没有 `int` 溢出，只有 `intmax_t` 溢出。
3. **通常算术转换照旧**：有符号与无符号混合时转为无符号，即 `uintmax_t`。

```cpp run title="if-arith.cpp"
#if -1 > 0u                         // -1 转为 uintmax_t，即最大值
// 成立！
#else
#  error "不会到这里"
#endif
#if 0xFFFFFFFFFFFFFFFF == -1        // 0xFFFF...(16 个 F) 装不进 intmax_t → uintmax_t
// 成立：-1 被转为 uintmax_t
#endif
#if (-1) >> 1 == -1                 // 有符号右移是算术移位（C++20 起有明确定义）
#endif
int main() {}
```

Clang 对前两个 `#if` 给出"converted from negative value to unsigned"警告（这是一个没有对应 `-W` 开关、无法单独关闭的警告，所以本例没有标"零警告"的 ok 判定），但程序良构，结果符合标准。

!!! ub "#if 中的溢出"
    `#if 0x7FFFFFFFFFFFFFFF + 1 > 0` 在 64 位 `intmax_t` 下有符号溢出。在常量表达式中，UB 使表达式不是核心常量表达式（[[expr.const]]），所以这个 `#if` 非良构。Clang 23 只给出 `integer overflow in preprocessor expression` **警告**，仍然取了一个值继续——警告也算诊断，所以这在形式上是符合标准的，但不要依赖它选择的分支。

    除以零同理：`#if 1/0` 非良构，Clang 报错 `division by zero in preprocessor expression`。但 `#if 1 || 1/0` 是合法的——`||` 的右操作数不求值，常量表达式规则只约束被求值的部分。

¶11 还规定：字符字面量按 [[lex.ccon]] 的规则解释（注 5：`#if` 中字面量的关联编码与普通表达式中**相同**）。所以 `#if 'A' == 65` 在 ASCII 兼容的普通字面量编码上为真，在 EBCDIC 上为假——但两种情况下它都与运行时 `'A' == 65` 的结果一致。C 标准在这里更宽松（允许 #if 中字符常量的值与执行时不同），C++ 则要求一致。

最后：每个 `bool` 类型的子表达式在继续处理前先做整数提升。所以 `#if true + true == 2` 为真。

!!! note "#if 中可以用的东西"
    凡是阶段 6 能变成整数字面量、字符字面量、`true`/`false` 的 *pp-number* 都可以用：二进制字面量 `0b101`、数字分隔符 `1'000`、后缀 `10z`、`u8'a'` 都行。浮点字面量和字符串字面量不行（不是整数常量表达式）。C++ 允许括号内的逗号运算符（`#if (1, 2)`），Clang 在 `-pedantic` 下对此提示，因为 C 不允许。

## #ifdef 家族（¶12）

`#ifdef X`、`#ifndef X`、`#elifdef X`、`#elifndef X` 分别等价于 `#if defined X`、`#if !defined X`、`#elif defined X`、`#elif !defined X`。

`#elifdef`/`#elifndef` 是 C++23 新增的（[[P2334R1]]，与 C23 同步）。它们填补了一个奇怪的空缺：`#if` 有 `#elif`，`#ifdef` 却没有对应的"否则如果已定义"。

```cpp run title="elifdef.cpp" ok std=c++23 flags="-std=c++23"
#define USE_EPOLL
#ifdef USE_IO_URING
#  define BACKEND 1
#elifdef USE_EPOLL
#  define BACKEND 2
#elifndef NO_SELECT
#  define BACKEND 3
#else
#  define BACKEND 0
#endif
static_assert(BACKEND == 2);
int main() {}
```

!!! pitfall "不认识 #elifdef 的旧编译器"
    对不支持 `#elifdef` 的实现而言，它只是一个条件支持的指令名。若前面的 `#ifdef` 为真，`#elifdef` 落在**被处理**的组里，实现必须报错——这还算好；若前面的 `#ifdef` 为**假**，`#elifdef` 落在被跳过的组里，按 [[cpp.pre#6]] 被静默忽略，于是它之后的内容被当作前一个组的一部分**继续跳过**，直到 `#else` 或 `#endif`——程序悄悄选错了分支。这就是为什么 Clang 在 C++20 模式下也识别 `#elifdef`（给 `-Wc++23-extensions` 警告），而不是把它当未知指令。

## 组的选择与跳过（¶13）

¶13 规定了 *if-section* 的执行模型：

1. 各指令的条件**按顺序**检查。条件为假（零）则跳过它控制的组。
2. 跳过时，指令只处理到**指令名**为止，以追踪嵌套层数；其余记号被忽略，组中其他记号也被忽略。
3. 只有**第一个**条件为真的组被处理；其后的组都被跳过，且它们的控制指令**按"位于被跳过的组中"来处理**——也就是说，后续 `#elif` 的表达式**不求值**。
4. 都不为真时，若有 `#else`，处理 `#else` 的组；否则一直跳到 `#endif`。

第 3 点的推论很实用：

```cpp run title="elif-not-evaluated.cpp" ok
#if 1
int x;
#elif 1/0          // 不求值：前面已有组被选中
#elif (            // 甚至不检查语法
#endif
int main() {}
```

脚注 116 提醒：文法上 `#else` 和 `#endif` 之后在换行前不能有任何预处理记号——但注释可以。所以 `#endif // FOO_H` 合法，而 `#endif FOO_H` 非良构（GCC/Clang 只给 `-Wextra-tokens` 警告，这同样算是诊断）。在**被跳过**的组里，`#endif FOO_H` 却是合法的（¶6 的宽松语法）——同一行代码，是否非良构取决于它所在的组是否被跳过。

## 标准例子（¶14–¶15）

¶14 的例 1 演示了"有则用之"的经典模式：先用 `__has_include` 检测 `<optional>`，再用 `__cpp_lib_optional` 确认版本，否则退回 `<experimental/optional>`，最后统一定义 `have_optional` 为 0 或 1。

¶15 的例 2 演示属性回退：

```cpp run title="attr-fallback.cpp" ok
#if __has_cpp_attribute(acme::deprecated)
#  define ATTR_DEPRECATED(msg) [[acme::deprecated(msg)]]
#else
#  define ATTR_DEPRECATED(msg) [[deprecated(msg)]]
#endif
ATTR_DEPRECATED("This function is deprecated") void anvil();
int main() {}
```

## 实现视角

!!! impl "预处理器怎么跳过一个组"
    跳过组时，Clang 进入"跳过模式"：词法分析器只寻找行首的 `#`，读取其后的指令名——`if`/`ifdef`/`ifndef` 使嵌套层加一，`endif` 使其减一，在最外层遇到 `elif`/`elifdef`/`elifndef`/`else`/`endif` 时才判断是否结束跳过——其余字符尽量不做完整的记号化。这就是为什么跳过组中孤立的 `'` 在 Clang 上不报错（见 [[cpp.pre]]）。

    GCC 和 Clang 都实现了**多重包含优化**：若一个头文件的全部内容都被 `#ifndef X / #define X / … / #endif` 包裹，预处理器记住 X，下次遇到 `#include` 同一个文件且 X 已定义时，连文件都不打开（见 [[cpp.include]]）。

## 历史与演进

!!! history
    - **C++98**：`#if`/`#ifdef`/`#ifndef`/`#elif`/`#else`/`#endif`、`defined`；`true`/`false` 不被替换为 0 是 C++ 相对 C 的差异。算术在 `long`/`unsigned long` 中进行。
    - **C++11**：与 C99 同步，算术改在 `intmax_t`/`uintmax_t` 中进行。
    - **C++17**：`__has_include`（[[P0061R1]]）。
    - **C++20**：`__has_cpp_attribute` 及特性测试宏进入标准正文（[[P0941R2]]，之前只是 SD-6 中的建议）。
    - **C++23**：`#elifdef`/`#elifndef`（[[P2334R1]]）。
    - **C++26**：`__has_embed`（[[P1967R14]]）{{c++26}}；宏展开产生 `defined`、`defined` 形式不符由 UB 改为 IFNDR。

## 思考题

!!! question "思考题 1"
    在 `intmax_t` 为 64 位的实现上，下面的 `#if` 选哪个分支？为什么与阶段 7 中同样的表达式结果不同？
    ```cpp
    #if 0x80000000 < 0
    A
    #else
    B
    #endif
    // 阶段 7：static_assert(!(0x80000000 < 0));
    ```

<details markdown="1">
<summary>展开查看答案与解析</summary>

选 B。在 #if 中，`0x80000000` 适合 `intmax_t`（64 位有符号），是正数，`< 0` 为假。

而在阶段 7（假设 `int` 为 32 位），十六进制字面量 `0x80000000` 不适合 `int`，按 [[lex.icon]] 的表选择 `unsigned int`。`unsigned int < int(0)` 中 0 转为 `unsigned`，`0x80000000u < 0u` 同样为假——这一例两边恰好一致。

真正不同的例子是 `-0x80000000 < 0`：#if 中它是 `-(intmax_t)0x80000000`，为负，结果**真**；阶段 7 中 `-0x80000000u` 是无符号的 `0x80000000u`，`< 0` 为**假**。这正是 ¶11 注 4 所说的现象：字面量在 #if 中有不同的类型。
</details>

!!! question "思考题 2"
    为什么 `__has_cpp_attribute` 明文要求对参数做宏展开，而 `__has_include` 却说"不再做进一步宏展开"？两者其实矛盾吗？

<details markdown="1">
<summary>展开查看答案与解析</summary>

不矛盾。按 ¶9，整个 `#if` 行（`defined` 的操作数除外）在求值前**已经**做过一次宏展开，`__has_include(HDR)` 中的 `HDR` 那时已被替换。¶3 的"no further macro expansion"是说：在把记号当作 `#include` 的 *pp-tokens* 时，不要按 [[cpp.include#7]] 再展开一遍——否则会展开两次。

`__has_cpp_attribute` 的 ¶5 说 "after macro expansion"，指的也是 ¶9 那一次展开，只是写明了而已。两者的效果是一样的：参数都恰好被展开一次。

细微的区别在于 *header-name*：若写 `__has_include(<foo.h>)`，`<foo.h>` 在阶段 3 就被识别为单个 *header-name* 记号（[[lex.pptoken#5.4.2.3]]），其中的 `foo` 即使是宏也不会被展开。
</details>

!!! question "思考题 3"
    ```cpp
    #define FOO 0
    #ifdef FOO
    #elifdef FOO
    #endif junk
    ```
    这段代码良构吗？

<details markdown="1">
<summary>展开查看答案与解析</summary>

非良构，问题出在最后一行。`#ifdef FOO` 为真，处理第一个（空）组；`#elifdef FOO` 及其组被跳过——按 ¶13，后续组的控制指令"按处于被跳过组中"处理，所以 `#elifdef` 无论如何都不会被求值。但 `#endif junk` 结束的是这个 *if-section* 本身，它并不在任何被跳过的组中，所以要遵守严格文法：*endif-line* 是 `# endif new-line`，后面不能有 `junk`。GCC/Clang 对此只给警告——警告就是标准要求的诊断。
</details>

## 小结

!!! summary
    - `#if` 求值四步：宏展开（`defined` 操作数除外）→ 求值 `defined`/`__has_include`/`__has_embed`/`__has_cpp_attribute` → 剩余标识符（含关键字，除 `true`/`false`）变 0 → 在 `intmax_t`/`uintmax_t` 中按常量表达式求值。
    - 拼错的宏名静默为 0；用 `-Wundef` 防身。
    - 宏展开产生 `defined`：IFNDR（C++23 前为 UB）。
    - `__has_embed` 三值：0 未找到/不支持，1 找到且非空，2 找到但为空。
    - `__has_cpp_attribute` 对标准属性可以返回 0（认识但不利用）。
    - 只有第一个为真的组被处理，其后的 `#elif` 不求值。
    - `#elifdef`/`#elifndef` 是 C++23 新增。
