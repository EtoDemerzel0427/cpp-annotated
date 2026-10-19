---
title: 条件包含
summary: "#if 家族怎样决定哪些代码进入翻译单元：条件表达式在预处理阶段怎样求值，#ifdef 系列，__has_include 等特性检测运算符，以及被跳过的组怎样处理。"
status: done
related: cpp.pre, cpp.include, cpp.embed, cpp.predefined, expr.const, dcl.attr.grammar, lex.icon
tags: 预处理, 条件编译, 特性检测
updated: 2026-10-19
---

!!! tldr
    - `#ifdef X` 只看 `X` 是否被定义为宏，`#if X` 看它展开后的值；`#define X 0` 时两者结果相反。
    - `#if` 的条件在预处理阶段求值，那时没有关键字和类型：宏展开之后剩下的标识符一律变成 `0`，所以拼错的宏名不会报错，`sizeof` 也用不了。
    - 条件中的整数运算一律按 `intmax_t` / `uintmax_t` 进行，`#if -1 > 0u` 为真。
    - `__has_include`、`__has_cpp_attribute`、`__has_embed` 用来检测头文件、属性和资源是否可用；检测它们自身是否存在要用单独一层 `#if defined(...)`。
    - 只有第一个条件为真的组被处理，后面的 `#elif` 条件根本不求值；被跳过的组里只追踪指令的嵌套。

条件包含（conditional inclusion）就是 `#if` 家族：根据编译期条件决定哪些源码进入翻译单元。可移植代码、平台适配和特性检测都建立在它上面。

这些指令在翻译阶段 4 执行（[[lex.phases]]）。这时源码只是一串预处理记号（[[g:preprocessing-token]]，见 [[lex.pptoken]]），还没有关键字、类型和声明，只有宏名和非宏名。本页的大多数规则都源于这一点。

## #ifdef 与 #if（¶2、¶12）

```cpp run title="defined.cpp" ok
#define A
#define B 0
#if defined A && defined(B) && !defined C
static_assert(true);   // 被包含：B 的值是 0，但它是定义了的
#endif
#ifdef B
static_assert(true);   // 被包含
#endif
#if B
static_assert(false);  // 不被包含：B 展开为 0
#endif
int main() {}
```

¶2 `defined X` 和 `defined ( X )` 在 `X` 当前被定义为宏名时得 1，否则得 0。当前被定义指它是预定义宏，或者有活跃的宏定义（[[g:active-macro-definition]]）：通常是 `#define` 过且之后没有 `#undef`，用 `import` 导入头文件单元带进来的宏也算（[[cpp.import]]）。

`defined` 只关心宏是否存在，不关心它的值。这就是 `#ifdef FEATURE` 和 `#if FEATURE` 的区别：`#define FEATURE 0` 时前者为真，后者为假。

¶12 `#ifdef X`、`#ifndef X`、`#elifdef X`、`#elifndef X` 分别等价于 `#if defined X`、`#if !defined X`、`#elif defined X`、`#elif !defined X`。

`#elifdef` 和 `#elifndef` 是 C++23 新增的，与 C23 同步（[[P2334R1]]）。此前 `#if` 有对应的 `#elif`，`#ifdef` 却没有对应的 else-if 形式。

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
    对不支持 `#elifdef` 的实现来说，它只是一个不认识的指令名。如果前面的 `#ifdef` 为真，`#elifdef` 位于要处理的部分，编译器会报错，问题容易发现。如果前面的 `#ifdef` 为假，`#elifdef` 位于被跳过的组中，会被静默忽略（[[cpp.pre#6]]），于是它后面的代码被当作前一个组的一部分继续跳过，程序悄悄选错了分支。为此 Clang 在 C++20 模式下也识别 `#elifdef`，只给一条 `-Wc++23-extensions` 警告。

## #if 的条件怎样求值（¶1、¶8–¶11）

¶1 控制条件包含的表达式必须是整数常量表达式（[[expr.const]]），但有两点不同：其中的标识符按下文的方式处理，而且可以用 `defined` 以及后文介绍的 `__has_include`、`__has_embed`、`__has_cpp_attribute` 作为一元运算符。

¶8 `#if` 和 `#elif` 检查这个表达式的值是否非零。求值分四步：

1. 宏展开，`defined` 的操作数除外（¶9）；
2. 求出 `defined`、`__has_include`、`__has_embed`、`__has_cpp_attribute` 的值（¶10）；
3. 剩下的标识符，除 `true` 和 `false` 外，全部换成 `0`（¶10）；
4. 把预处理记号转换成记号，按常量表达式求值，所有整数类型都当作 `intmax_t` 或 `uintmax_t`（¶11）。

### 先做宏展开（¶9）

¶9 求值之前，条件中的宏调用像普通文本一样被替换，只有 `defined` 后面的宏名不展开。

如果宏展开的结果中出现了 `defined` 这个记号，或者 `defined` 的写法在宏替换之前不是 `defined X` 或 `defined ( X )` 这两种形式之一，程序非良构，不要求诊断（IFNDR：编译器可以不报错，标准对整个程序不再有任何要求）。

```cpp run title="defined-from-macro.cpp" ifndr
#define A
#define HAS_A defined(A)
#if HAS_A          // IFNDR：宏展开产生了 defined
#endif
int main() {}
```

标准不去规定这种写法的行为，是因为历史上各实现处理得不一样，例如展开中途产生的 `defined` 的操作数还要不要再展开。GCC 和 Clang 照常求值，Clang 给出 `-Wexpansion-to-defined` 警告（警告措辞仍说是 undefined behavior，C++23 及以前这里确实是 UB）。可移植的写法是让宏展开成 0 或 1：

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

¶9 还禁止一种情况：在 `__has_embed(` 与对应的 `)` 之间做宏替换时，遇到被定义为宏的 `limit`、`prefix`、`suffix` 或 `if_empty`，程序非良构。这和 [[cpp.pre#4]] 对 `#embed` 指令的要求一致。

### 剩下的标识符变成 0（¶10）

```cpp run title="ident-zero.cpp" ok
#if new == 0 && undefined_thing == 0
// 成立：阶段 4 没有关键字，new 只是一个不是宏的标识符
#endif
#if true && !false
// true 和 false 是例外，保持布尔字面量的含义
#endif
int main() {}
```

¶10 完成宏替换和四种特殊运算符的求值以后，剩下的标识符，包括拼写与关键字相同的，除 `true` 和 `false` 外一律换成 *pp-number* `0`，然后每个预处理记号转换成记号。脚注 115 说明了原因：在阶段 4，一个标识符要么是宏名，要么不是，不存在关键字、枚举量之类的分别。

这条规则带来的最常见问题是，拼错的宏名不会报错，只会悄悄地得到 0：

```cpp
#if HAVE_THREDS     // 拼错了，得 0，选错了分支
#endif
```

GCC 和 Clang 的 `-Wundef` 会在 `#if` 中出现未定义的标识符时给出警告。

¶10 的注 3 指出，`and`、`or`、`not`、`bitor` 这类替代记号（[[g:alternative-token]]，见 [[lex.digraph]]）虽然全由字母组成，却不是标识符，所以不会变成 0，照常作为运算符：

```cpp run title="alt-tokens-in-if.cpp" ok
#if not 0 and (1 bitor 0)
// 成立：not、and、bitor 是运算符
#endif
int main() {}
```

!!! lawyer "#if 里的 sizeof 和类型转换"
    `#if sizeof(int) == 4` 中，`sizeof` 和 `int` 都变成 0，得到 `0(0) == 4`，这不是合法的表达式，所以非良构。`#if (long)1` 变成 `(0)1`，同样是语法错误。要在预处理期获知类型大小，只能依靠实现预定义的宏（如 GCC 和 Clang 的 `__SIZEOF_INT__`）或 `<climits>` 中的宏。

### 在最宽的整数类型中计算（¶11）

```cpp run title="if-arith.cpp"
#if -1 > 0u                         // -1 转为 uintmax_t，即最大值
// 成立
#else
#  error "不会到这里"
#endif
#if 0xFFFFFFFFFFFFFFFF == -1        // 字面量装不进 intmax_t，是 uintmax_t
// 成立：-1 也被转为 uintmax_t
#endif
int main() {}
```

¶11 第四步得到的记号按常量表达式的规则求值，算术范围至少达到 [[support.limits]] 的要求。在这次转换和求值中，所有有符号整数类型都如同 `intmax_t`，所有无符号整数类型都如同 `uintmax_t`。这有三个后果：

1. 字面量的类型可能和普通代码里不同。注 4 举例：在 `int` 为 16 位的实现上，`0x8000` 在 `#if` 中是有符号的正数，而在阶段 7 的普通代码中是 `unsigned int`。
2. 所有运算都在最宽的类型中进行，不存在 `int` 溢出，只有 `intmax_t` 溢出。
3. 通常算术转换照常进行，有符号和无符号混合时转成 `uintmax_t`，所以 `#if -1 > 0u` 为真。

Clang 对上面两个 `#if` 都给出 converted from negative value to unsigned 警告。这条警告没有对应的 `-W` 开关，无法单独关闭，所以这个例子没有标判定；程序是良构的，结果符合标准。

!!! ub "#if 中的溢出与除以零"
    `#if 0x7FFFFFFFFFFFFFFF + 1 > 0` 在 64 位 `intmax_t` 下有符号溢出。溢出使表达式不再是常量表达式（[[expr.const]]），所以这个 `#if` 非良构。Clang 23 只给一条 integer overflow in preprocessor expression 警告，取某个值继续处理。警告也算诊断，形式上符合标准，但不要依赖它选的分支。

    `#if 1/0` 同理是非良构的，Clang 直接报错。而 `#if 1 || 1/0` 是合法的：`||` 的右操作数不求值，常量表达式的限制只针对被求值的部分。

¶11 还规定，字符字面量按 [[lex.ccon]] 的规则解释，注 5 补充说 `#if` 中字面量使用的编码与普通表达式相同。所以 `#if 'A' == 65` 的结果总与运行时 `'A' == 65` 一致：ASCII 兼容的编码下为真，EBCDIC 下为假。C 标准在这里更宽松，允许 `#if` 中字符常量的值与运行时不同。

最后，每个 `bool` 类型的子表达式在继续计算前先做整数提升，所以 `#if true + true == 2` 为真。

!!! note "#if 中能用的字面量"
    凡是在阶段 6 之后能成为整数字面量、字符字面量或 `true`/`false` 的 *pp-number* 都可以用：二进制字面量 `0b101`、数字分隔符 `1'000`、后缀 `10z`、`u8'a'` 都行。浮点字面量和字符串字面量不行，因为它们不能出现在整数常量表达式里。C++ 还允许括号内的逗号运算符（`#if (1, 2)`），C 不允许，所以 Clang 在 `-pedantic` 下对此给出提示。

## 特性检测（¶3–¶7、¶14–¶15）

### __has_include（¶3）

```cpp run title="has-optional.cpp" ok
#if __has_include(<optional>)
#  include <optional>
#  if __cpp_lib_optional >= 201603
#    define have_optional 1
#  endif
#elif __has_include(<experimental/optional>)
#  include <experimental/optional>
#  if __cpp_lib_experimental_optional >= 201411
#    define have_optional 1
#    define experimental_optional 1
#  endif
#endif
#ifndef have_optional
#  define have_optional 0
#endif
static_assert(have_optional == 1);
int main() {}
```

这是 ¶14 的标准例 1：有 `<optional>` 就用它，否则退回 `<experimental/optional>`，最后统一定义 `have_optional` 为 0 或 1。

¶3 `__has_include( ... )` 把括号里的记号当作 `#include` 指令的操作数去搜索文件（[[cpp.include]]），找到得 1，找不到得 0。这里不再做宏展开，因为 ¶9 已经展开过一次。括号中的记号必须是一个头文件名，或者能按 `#include` 的规则拼成一个头文件名，否则程序非良构。

```cpp run title="has-include.cpp" ok
#define HDR "no_such_header.h"
#if __has_include(HDR)          // HDR 在 ¶9 中被展开为 "no_such_header.h"
#  error "不应找到"
#endif
int main() {}
```

`__has_include` 回答的是能否找到，不是能否使用。[[cpp.include#6]] 的注 1 指出，如果找到了文件但实现无法处理它（比如它是个目录），即使只是在 `__has_include` 中探测，程序也非良构。

头文件存在也不代表其中的功能可用。老版本的标准库在 `-std=c++14` 下可能也提供 `<optional>`，但内容被 `#if` 去掉了。所以例 1 在找到头文件之后还要检查 `__cpp_lib_optional`。C++20 起更直接的做法是包含 `<version>`，再检查库特性测试宏（[[cpp.predefined]]）。

### __has_cpp_attribute（¶5–¶6）

```cpp run title="has-attr.cpp" ok
#if __has_cpp_attribute(nodiscard) >= 201907L
#  define NODISCARD(msg) [[nodiscard(msg)]]   // C++20 起 nodiscard 可以带理由
#elif __has_cpp_attribute(nodiscard)
#  define NODISCARD(msg) [[nodiscard]]
#else
#  define NODISCARD(msg)
#endif
NODISCARD("check the error") int f() { return 0; }
int main() { return f(); }
```

¶5 `__has_cpp_attribute( ... )` 把括号中的记号宏展开后解释为一个属性名（`name` 或 `ns::name`）。实现支持这个属性时，整个表达式换成一个非零的整数字面量，否则换成 0。括号中的内容不符合属性名的形式时，程序非良构。

¶6 对标准规定的属性，结果是 0 还是表 21 中的值，由实现定义。对实现认识的其他属性，值也由实现定义。注 2 说，可以认为任何非零值都表示该属性可用。

| 属性 | 值 | 属性 | 值 |
|---|---|---|---|
| `assume` | `202207L` | `maybe_unused` | `201603L` |
| `deprecated` | `201309L` | `no_unique_address` | `201803L` |
| `fallthrough` | `201603L` | `nodiscard` | `201907L` |
| `indeterminate` | `202403L` | `noreturn` | `200809L` |
| `likely` | `201803L` | `unlikely` | `201803L` |

表中已经没有 `carries_dependency`，这个属性已从当前草案中删除（[[dcl.attr]]）。

标准属性也允许报 0，是因为认识一个属性不等于会利用它。例如 MSVC 认识 `[[no_unique_address]]`，但出于 ABI 原因不改变布局，所以报 0，并提供 `[[msvc::no_unique_address]]`。各属性小节的推荐做法也是这个思路：实现不能发出弃用诊断时，`deprecated` 的值应为 0（[[dcl.attr.deprecated#4]]）；不能抑制贯穿警告时，`fallthrough` 的值应为 0（[[dcl.attr.fallthrough#2]]）。

¶15 的标准例 2 演示了有厂商属性就用、没有就退回标准属性：

```cpp run title="attr-fallback.cpp" ok
#if __has_cpp_attribute(acme::deprecated)
#  define ATTR_DEPRECATED(msg) [[acme::deprecated(msg)]]
#else
#  define ATTR_DEPRECATED(msg) [[deprecated(msg)]]
#endif
ATTR_DEPRECATED("This function is deprecated") void anvil();
int main() {}
```

!!! impl "Clang 23 的实际值"
    `__has_cpp_attribute(indeterminate)` 为 0（尚未实现），`assume` 为 `202207L`，`nodiscard` 为 `201907L`，`no_unique_address` 为 `201803L`。`carries_dependency` 仍报 `200809L`，因为 Clang 还没有跟进草案删除这个属性。厂商属性如 `gnu::always_inline` 报 1。

### __has_embed（¶4）{{c++26}}

`#embed` 指令把一个文件的字节作为逗号分隔的整数列表放进源码（[[cpp.embed]]），`__has_embed` 是它的探测版本。

```cpp run title="has-embed.cpp" ok
#if __has_embed(__FILE__) != __STDC_EMBED_FOUND__
#  error "源文件自身应当可以被 embed"
#endif
#if __has_embed(__FILE__ limit(0)) != __STDC_EMBED_EMPTY__
#  error "limit(0) 使资源为空"
#endif
#if __has_embed(__FILE__ acme::frobnicate) != __STDC_EMBED_NOT_FOUND__
#  error "不认识的参数算作不受支持"
#endif
int main() {}
```

¶4 `__has_embed( ... )` 把括号中的记号当作 `#embed` 指令的操作数处理，同样不再做宏展开。结果有三种：

- ¶4.1 找到资源、所有参数都受支持、资源非空：`__STDC_EMBED_FOUND__`（1）；
- ¶4.2 否则，找到资源、参数都受支持、资源为空：`__STDC_EMBED_EMPTY__`（2）；
- ¶4.3 否则：`__STDC_EMBED_NOT_FOUND__`（0）。

注 1 说明，不认识的参数不会使程序非良构，只算作不受支持，结果为 0。所以 `__has_embed` 也能用来探测实现是否支持某个厂商参数。资源是否为空按 `limit` 等参数作用后的字节数判断，所以 `limit(0)` 让任何存在的资源都算空（[[cpp.embed.param.if.empty]] 例 2）。

例子中的 `__FILE__` 在 ¶9 中展开为当前文件名的字符串字面量，再作为文件名使用。

### 它们本身算作已定义的宏（¶1、¶7）

¶7 `#ifdef`、`#ifndef`、`#elifdef`、`#elifndef` 和 `defined` 运算符把 `__has_include`、`__has_embed`、`__has_cpp_attribute` 当作已定义的宏名。于是可以先检测编译器是否支持这些运算符：

```cpp run title="detect-has-include.cpp" ok
#if defined(__has_include)
#  if __has_include(<version>)
#    include <version>
#  endif
#endif
int main() {}
```

¶7 还规定，这三个标识符不得出现在本条款没有提到的上下文中。所以 `#define __has_include ...` 或在普通代码里写 `__has_include(x)` 都是非良构的。¶1 最后一句另有一条限制：`defined` 不能写在 `__has_include` 或 `__has_embed` 的括号里。

!!! pitfall "检测和使用不能写在同一个 #if 里"
    `#if defined(__has_include) && __has_include(<x>)` 在不支持 `__has_include` 的老编译器上依然会出错。`&&` 右边照样要做宏替换，`__has_include` 作为普通标识符变成 0，剩下 `0(<x>)`，这是语法错误。短路求值帮不上忙，因为语法错误在求值之前就发生了。所以要像上例那样嵌套两层 `#if`。

## 选中一个组，跳过其余（¶13）

```cpp run title="elif-not-evaluated.cpp" ok
#if 1
int x;
#elif 1/0          // 不求值：前面已有组被选中
#elif (            // 连语法都不检查
#endif
int main() {}
```

¶13 一个 `#if` 结构中各指令的条件按顺序检查：

1. 条件为假（零）时，跳过它控制的组。
2. 只处理第一个条件为真的组。后面的组都被跳过，它们的控制指令也按位于被跳过的组中处理，所以后面的 `#elif` 条件不求值。
3. 所有条件都不为真时，如果有 `#else`，处理 `#else` 的组；否则一直跳到 `#endif`。

跳过一个组时，预处理器只读每条指令的指令名，用来追踪 `#if` 的嵌套层数；指令的其余部分和组里的其他记号都被忽略。

脚注 116 提醒，按文法，`#else` 和 `#endif` 之后、换行之前不能有预处理记号，但可以有注释。所以 `#endif // FOO_H` 合法，`#endif FOO_H` 非良构（GCC 和 Clang 只给 `-Wextra-tokens` 警告，这也算诊断）。但如果这行 `#endif` 本身位于一个被跳过的组中，它只被读到指令名为止，`FOO_H` 不会造成问题。同一行代码是否非良构，取决于它所在的组是否被跳过。

!!! impl "预处理器怎样跳过一个组"
    Clang 跳过一个组时，词法分析器只寻找行首的 `#` 并读取指令名：`if`、`ifdef`、`ifndef` 使嵌套层数加一，`endif` 使其减一，在最外层遇到 `elif`、`elifdef`、`elifndef`、`else`、`endif` 时才判断是否停止跳过。其余字符尽量不做完整的记号化，所以被跳过的组里孤立的 `'` 在 Clang 上不报错（见 [[cpp.pre]]）。

    GCC 和 Clang 都有多重包含优化：如果一个头文件的全部内容被 `#ifndef X` / `#define X` / … / `#endif` 包住，预处理器会记住 `X`，下次 `#include` 同一个文件时，只要 `X` 已定义就不再打开它（见 [[cpp.include]]）。

## 历史与演进

!!! history
    - C++98 就有 `#if`、`#ifdef`、`#ifndef`、`#elif`、`#else`、`#endif` 和 `defined`。`true` 和 `false` 不被换成 0 是 C++ 与 C 的一处差别。当时的算术在 `long` 和 `unsigned long` 中进行。
    - C++11 与 C99 同步，算术改在 `intmax_t` 和 `uintmax_t` 中进行。
    - C++17 加入 `__has_include`（[[P0061R1]]）。
    - C++20 把 `__has_cpp_attribute` 和特性测试宏写进标准正文（[[P0941R2]]），此前它们只是委员会的推荐做法。
    - C++23 加入 `#elifdef` 和 `#elifndef`（[[P2334R1]]）。
    - C++26 加入 `__has_embed`（[[P1967R14]]）；宏展开产生 `defined`、`defined` 形式不对这两种情况从 UB 改为 IFNDR。

## 思考题

!!! question "思考题 1"
    在 `intmax_t` 为 64 位、`int` 为 32 位的实现上，`#if -0x80000000 < 0` 成立吗？同样的表达式放进普通代码 `static_assert(-0x80000000 < 0);` 呢？

<details markdown="1">
<summary>答案</summary>

`#if` 中成立。按 ¶11，`0x80000000` 在 `#if` 中是 `intmax_t`，取负得到负数，`< 0` 为真。

普通代码中不成立。`0x80000000` 装不进 32 位 `int`，按 [[lex.icon]] 的规则，十六进制字面量接着尝试 `unsigned int`，于是它是 `unsigned int`。对它取负仍是无符号的 `0x80000000u`，`< 0` 为假，这个 `static_assert` 失败。这就是 ¶11 注 4 说的现象：同一个字面量在 `#if` 中可能有不同的类型。
</details>

!!! question "思考题 2"
    ¶5 说 `__has_cpp_attribute` 的参数要宏展开，¶3 却说 `__has_include` 的参数不再做宏展开。两者矛盾吗？

<details markdown="1">
<summary>答案</summary>

不矛盾。按 ¶9，整个 `#if` 行（`defined` 的操作数除外）在求值前已经展开过一次，`__has_include(HDR)` 中的 `HDR` 那时已被替换。¶3 说的不再展开，是指把记号当作 `#include` 的操作数时不要按 [[cpp.include#7]] 再展开一遍。¶5 的 after macro expansion 指的也是 ¶9 那一次展开。两者的参数都恰好展开一次。

一个细节是头文件名：`__has_include(<foo.h>)` 中的 `<foo.h>` 在阶段 3 就被识别成单个头文件名记号，其中的 `foo` 即使是宏也不会展开。
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
<summary>答案</summary>

非良构，问题在最后一行。`#ifdef FOO` 为真，处理第一个（空）组；`#elifdef FOO` 及其组被跳过。但 `#endif junk` 结束的是这个 `#if` 结构本身，它不在任何被跳过的组中，所以要遵守严格的文法：`#endif` 之后、换行之前不能有记号。GCC 和 Clang 只给警告，而警告就是标准要求的诊断。
</details>

## 小结

!!! summary
    - `#if` 求值四步：宏展开（`defined` 的操作数除外），求出 `defined` 和三个 `__has_*` 运算符，剩余标识符（除 `true`/`false`）变成 0，在 `intmax_t`/`uintmax_t` 中按常量表达式求值。
    - 拼错的宏名静默得 0，用 `-Wundef` 可以发现。
    - 宏展开产生 `defined` 是 IFNDR（C++23 及以前是 UB），应让宏展开成 0 或 1。
    - `__has_embed` 有三种结果：0 未找到或参数不受支持，1 找到且非空，2 找到但为空。
    - `__has_cpp_attribute` 对标准属性也可以报 0，表示认识但不利用。
    - 只有第一个条件为真的组被处理，其后的 `#elif` 不求值。
