---
title: 规范性引用文件
summary: C++ 标准把 C 标准、POSIX、IEEE 754、Unicode、ECMAScript 等文件的部分内容"拉进来"作为自己的要求；这一节列出它们，并区分有日期和无日期引用。
status: done
related: intro.defs, intro.compliance, library.c, topics/how-to-read-the-standard
tags: 总则, C 兼容, Unicode
updated: 2026-10-17
---

第 2 章列出标准的**规范性引用文件**（normative references）。这一节很短，但它回答了一个重要问题：C++ 标准里有大量东西其实并没有在 C++ 标准里写出来——`printf` 的格式说明符、`<cmath>` 函数的语义、正则表达式的默认语法、什么是合法的 Unicode 标识符……它们的定义在哪里？答案是：在这里列出的文件里。

## "规范性引用"是什么意思（¶1）

¶1 下列文件在正文中以这样的方式被引用：它们的部分或全部内容**构成本文档的要求**。对有日期的引用，只适用所引用的那一版；对无日期的引用，适用最新版（包括所有修订）。

!!! std
    The following documents are referred to in the text in such a way that some or all of their content constitutes requirements of this document.

要点有三：

**1. 被引用的内容具有和标准正文同等的效力。** 当 [[cstdio.syn]] 说"`<cstdio>` 的内容和含义与 C 标准库头文件 `<stdio.h>` 相同"时，C 标准第 7.23 节关于 `printf` 的全部规定就成了 C++ 的要求——包括其中的未定义行为（例如格式说明符与实参类型不匹配是 UB）。

**2. 并非"整份文件都适用"。** "部分或全部内容"——只有正文实际引用到的那部分才构成要求。C++ 引用了 C 标准，但 C 的语言规则（比如 C 的隐式 `int`、VLA）当然不适用于 C++；适用的主要是 C 标准库（第 7 章），而且还要经过 C++ 的修改（[[library.c]]、[[diff.library]]）。

**3. 有日期 vs 无日期。** 例如引用 "ISO/IEC 9899:2024" 就是锁定 C23 这一版；引用 "ISO/IEC 2382"（没有年份）则自动跟随最新版。C++ 对实质性的技术引用几乎都带日期，这样 C 或 POSIX 的新版本不会在 C++ 标准不知情的情况下改变 C++ 的要求。Unicode 引用了具体版本，但 [[intro.compliance]] ¶10 额外允许实现使用更新的版本。

与之相对的是**参考文献**（Bibliography）：草案最后的参考文献列出了历届 C++ 标准、IANA 字符集与时区数据库、BLAS 相关论文等，它们是资料性的，不构成要求。

## 引用了哪些文件、各自用来做什么

| 引用 | 是什么 | C++ 用它来规定什么 |
|---|---|---|
| ISO/IEC 2382 | 信息技术词汇 | 基础术语（[[intro.defs]] ¶1） |
| ISO 8601-1:2019 | 日期和时间的表示 | `<chrono>` 格式化中基于周的年份等（[[time.format]]） |
| ISO/IEC 9899:2024 | C 编程语言（C23） | C 标准库头文件的内容与语义（`<cstdio>`、`<cmath>`、`<cstring>` …），大量"See also: ISO/IEC 9899:2024, 7.x" |
| ISO/IEC/IEEE 9945:2009 及两份技术勘误 | POSIX Base Specifications, Issue 7 | 文件系统库的语义（[[fs.conform.9945]]）、正则表达式的 basic/extended/awk/grep/egrep 语法、`errc` 错误码 |
| ISO/IEC 60559:2020 | 浮点算术（即 IEEE 754） | `numeric_limits::is_iec559`、扩展浮点类型 `std::float32_t` 等（[[basic.extended.fp]]） |
| ISO 80000-2:2019 | 数学符号与术语 | 数学术语和记号（[[intro.defs]] ¶1 把它的定义纳入标准词汇） |
| ECMA-262 第 3 版（1999） | ECMAScript 语言规范 | `std::regex` 的默认语法（修改过的 ECMAScript，[[re.grammar]]） |
| The Unicode Standard 15.1 | Unicode | 字符集、标识符语法（UAX #31，见 Annex E [[uaxid]]）、`std::format` 的宽度估计、字面量编码 |

```cpp run ok
#include <chrono>
#include <cstdio>
#include <format>
#include <limits>
#include <regex>
int main() {
  // ISO/IEC 60559（IEEE 754）：double 是否采用它由实现报告
  std::printf("double is IEC 60559: %d\n", std::numeric_limits<double>::is_iec559);
  // ISO 8601：%F 是日历日期，%G-W%V-%u 是"基于周的年 - 周 - 星期"
  using namespace std::chrono;
  sys_days d = 2027y / January / 1;
  std::puts(std::format("{:%F} = {:%G-W%V-%u}", d, d).c_str());   // 2027-01-01 = 2026-W53-5
  // ECMAScript 第 3 版：std::regex 的默认语法，支持前瞻断言
  std::printf("%d\n", std::regex_search("ab", std::regex("a(?=b)")));   // 1
  // POSIX：同样的模式在 extended（POSIX ERE）语法下非法
  try { std::regex("a(?=b)", std::regex::extended); }
  catch (const std::regex_error&) { std::puts("not valid POSIX ERE"); }
}
```

本机 Clang 23 + libc++ 上输出 `1`、`2027-01-01 = 2026-W53-5`、`1`、`not valid POSIX ERE`。2027 年 1 月 1 日是星期五，按 ISO 8601 的规则它属于 2026 年的第 53 周——这正是"基于周的年"与日历年的区别。

## 为什么要引用而不是照抄

- **C 兼容是 C++ 的立身之本。** C++ 标准库包含 C 标准库，并承诺与之兼容。如果照抄 C 的条文，两份文件迟早会出现差异；引用则保证"同一个 `printf`"。代价是 C++ 读者有时要去翻 C 标准才能得到完整答案。
- **专业领域交给专业标准。** 浮点运算的精确语义、Unicode 的字符属性、POSIX 文件系统的行为，都有各自的标准组织在维护。C++ 委员会不必（也没有能力）重新规定它们。
- **ISO 的规则。** ISO 的起草规则要求所有规范性引用集中列在"规范性引用文件"一章，并注明版本——所以 ECMAScript、Unicode 这类非 ISO 文件也要在这里列明出处和版本。

## 历史与演进

!!! history
    - C++ 引用的 C 标准版本随时间推进：C++98/03 引用 C90，C++11/14 引用 C99，C++17 引用 C11，C++20 和 C++23 引用 C17（ISO/IEC 9899:2018），当前草案引用 C23（ISO/IEC 9899:2024）。每次升级都意味着一批 C 库变化被带入 C++（例如 C23 的 `<stdbit.h>` 进入了 C++26 的头文件列表）。
    - Unicode 和 ISO 8601 的引用是随着 `char8_t`/Unicode 标识符和 `<chrono>` 日历、格式化等特性加入的；Unicode 引用的版本也在不断更新。
    - ECMAScript 的引用自 C++11 引入 `<regex>` 起就固定在 1999 年的第 3 版，因为 `std::regex` 的默认语法正是以它为基础修改而来。

## 陷阱

!!! pitfall "“C 标准里定义的行为在 C++ 里也一样”"
    只对被引用的部分成立，而且要经过 C++ 的修改。例如 C 的 `<string.h>` 中 `strchr` 接受 `const char*` 返回 `char*`，而 C++ 的 `<cstring>` 提供 `const` 正确的两个重载（[[cstring.syn]]）；C 的 `<tgmath.h>` 宏在 C++ 中由重载代替。C 的核心语言规则（如联合体的类型双关）则完全不适用。

!!! pitfall "“`std::regex` 就是 JavaScript 的正则”"
    它基于 1999 年的 ECMAScript 第 3 版，而且是"修改过的"（[[re.grammar]] 增加了一些 POSIX 风格的字符类等）。后来 JavaScript 正则新增的命名捕获组、后行断言、`u` 标志等，`std::regex` 都不支持。
