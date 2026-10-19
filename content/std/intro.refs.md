---
title: 规范性引用文件
summary: C++ 标准没有写出、却必须遵守的那部分规则来自哪里：C 标准库来自 C23，浮点来自 IEEE 754，std::regex 的默认语法来自 ECMAScript，文件系统来自 POSIX，字符来自 Unicode。
status: done
related: intro.defs, intro.compliance, library.c, topics/how-to-read-the-standard
tags: 总则, C 兼容, Unicode
updated: 2026-10-18
---

!!! tldr
    - C++ 标准库建立在 C23（ISO/IEC 9899:2024）的标准库之上。`<cstdio>`、`<cmath>` 等头文件的含义由 C 标准规定，其中的未定义行为也一并带了过来。
    - 浮点算术引用的是 ISO/IEC 60559，也就是 IEEE 754。但 C++ 不要求 `float`、`double` 采用它，要用 `numeric_limits<T>::is_iec559` 查询。
    - `std::regex` 的默认语法是 1999 年的 ECMAScript 第 3 版；文件系统库和 POSIX 风格的正则语法按 POSIX 规定。
    - 标识符能用哪些字符、`std::format` 怎样估计宽度，按 Unicode 15.1，实现也可以用更新的版本。

## printf 的规则写在哪里

```cpp run ub
#include <cstdio>
int main() {
  long n = 42;
  std::printf("%d\n", n);   // UB: %d 要求 int，实参是 long
}
```

C++ 标准里找不到 `%d` 的含义。[[cstdio.syn]] 只说 `<cstdio>` 的内容和含义与 C 标准库头文件 `<stdio.h>` 相同，于是 C 标准对 `printf` 的全部规定都成了 C++ 的规定。C 标准说格式与实参类型不匹配是未定义行为，所以这段 C++ 代码也是。本机 Clang 23 对此给出 `-Wformat` 警告。

¶1 [intro.refs] 列出的就是这样的文件。正文引用它们的方式，使得它们的部分或全部内容成为本标准的要求。

!!! std
    The following documents are referred to in the text in such a way that some or all of their content constitutes requirements of this document.

## 引用了哪些文件

| 引用 | 对 C++ 程序员意味着什么 |
|---|---|
| ISO/IEC 9899:2024（C23） | C 标准库头文件（`<cstdio>`、`<cmath>`、`<cstring>` 等）的语义，库条款里大量 "See also: ISO/IEC 9899:2024" 都指向它 |
| ISO/IEC 60559:2020（IEEE 754） | `numeric_limits::is_iec559`；`std::float32_t`、`std::float64_t` 等扩展浮点类型的格式（[[basic.extended.fp]]） |
| ISO/IEC/IEEE 9945（POSIX，Issue 7 及两份勘误） | 文件系统库的语义（[[fs.conform.9945]]）；`std::regex` 的 basic、extended、awk、grep、egrep 语法；`std::errc` 的错误码 |
| ECMA-262 第 3 版（1999，ECMAScript） | `std::regex` 的默认语法，经过修改（[[re.grammar]]） |
| Unicode 15.1 | 字符集、标识符语法（Annex E [[uaxid]]）、字面量编码、`std::format` 的宽度估计 |
| ISO 8601-1:2019 | `<chrono>` 格式化中的日期表示和基于周的年份（[[time.format]]） |

下面的程序各用到了其中一项：

```cpp run ok
#include <chrono>
#include <cstdio>
#include <format>
#include <limits>
#include <regex>
int main() {
  // ISO/IEC 60559（IEEE 754）：double 是否采用它由实现报告
  std::printf("%d\n", std::numeric_limits<double>::is_iec559);   // 1

  // ISO 8601：%F 是日历日期，%G-W%V-%u 是基于周的年份、周数和星期
  // 输出 2027-01-01 = 2026-W53-5
  using namespace std::chrono;
  sys_days d = 2027y / January / 1;
  std::puts(std::format("{:%F} = {:%G-W%V-%u}", d, d).c_str());

  // ECMAScript 第 3 版：默认语法支持前瞻断言
  std::printf("%d\n", std::regex_search("ab", std::regex("a(?=b)")));  // 1

  // POSIX：同样的模式不是合法的扩展正则表达式（ERE）
  try { std::regex("a(?=b)", std::regex::extended); }
  catch (const std::regex_error&) { std::puts("not valid POSIX ERE"); }
}
```

本机 Clang 23 + libc++ 的输出与注释一致。2027 年 1 月 1 日是星期五，按 ISO 8601 的规则它属于 2026 年的第 53 周，这就是基于周的年份与日历年份的区别。

## 与 C 标准库的关系

C++ 引用 C 标准，主要是为了它的标准库（C 标准第 7 章）。C 的语言规则并不适用于 C++：引用的只是正文实际用到的那部分。而且这部分还要经过 C++ 的修改（[[library.c]]、[[diff.library]]）。例如 C 的 `strchr` 接受 `const char*`、返回 `char*`，C++ 的 `<cstring>` 则提供 const 正确的两个重载（[[cstring.syn]]）；C 的 `<tgmath.h>` 宏在 C++ 中由函数重载代替。

引用的 C 标准版本随 C++ 一起推进：C++98/03 引用 C90，C++11/14 引用 C99，C++17 引用 C11，C++20 和 C++23 引用 C17，当前草案引用 C23。每升级一次，C 库的一批变化就会带进 C++。

!!! pitfall "std::regex 就是 JavaScript 的正则"
    它基于 1999 年的 ECMAScript 第 3 版，并做过修改。后来 JavaScript 加入的命名捕获组、后行断言、`u` 标志等，`std::regex` 都不支持。

<details class="fine" markdown="1"><summary>其余条文</summary>

- 有日期的引用（如 ISO/IEC 9899:2024）只适用所引的那一版；无日期的引用适用最新版，包括所有修订。C++ 对实质性的技术文件几乎都带日期，这样 C 或 POSIX 出了新版，不会在 C++ 不知情的情况下改变 C++ 的要求。Unicode 虽然引用了具体版本，但 [[intro.compliance]] 的 ¶10 允许实现使用更新的版本。
- ISO/IEC 2382（信息技术词汇）和 ISO 80000-2:2019（数学符号）提供基础术语和数学记号，[[intro.defs]] 把它们的定义纳入标准词汇。
- POSIX 和 ECMAScript 的脚注是商标声明。
- 草案末尾的参考文献（Bibliography）列出了历届 C++ 标准、IANA 时区数据库等，它们只是参考资料，不构成要求。

</details>
