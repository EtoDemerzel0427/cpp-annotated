---
title: 预处理记号与记号
summary: 阶段 3 怎样把字符切成预处理记号：最长匹配及其例外（原始字符串、<::、[::），注释、头文件名、预处理数字、运算符与标点；以及阶段 6 把它们转换成的记号。
status: draft
covers: lex.comment, lex.header, lex.ppnumber, lex.operators, lex.token
related: lex.phases, lex.digraph, cpp.include, cpp.import, temp.names
tags: 词法, 预处理, maximal munch
updated: 2026-10-19
---

!!! tldr
    - 阶段 3 每次切出能构成预处理记号的最长字符序列，不回溯，所以 `x+++++y` 切成 `x ++ ++ + y`，编译失败。
    - 例外按顺序是：原始字符串优先；`<::` 中的 `<` 单独成记号；`[::` 和 `[:>` 中的 `[` 单独成记号（C++26）。头文件名只在 `#include` 等少数位置形成。
    - 预处理数字（pp-number）的文法故意很宽，`0xe+foo`、`1.2.3` 都是一个预处理数字，到阶段 6 才因为不是合法字面量而报错。
    - `/* */` 注释不嵌套；注释在阶段 3 变成一个空格。
    - 落单的 `'`、`"` 和基本字符集以外的字符不能单独成为预处理记号，否则程序非良构。

## 切分是贪婪的

```cpp title="munch.cpp" error
int f(int x, int y) {
  return x+++++y;    // 切成 x ++ ++ + y；x++ 是纯右值，不能再 ++
}
```

把它切成 `x ++ + ++ y` 本来是一个合法的表达式，但编译器不会这样切。阶段 3（[[lex.phases]]）从左到右扫描字符，每次切出能构成一个预处理记号的最长序列，切完就不回头。这条规则叫**最长匹配**（[[g:maximal-munch|maximal munch]]），本页的大部分内容是它和它的几条例外。

先看被切出来的东西是什么。

## 预处理记号的种类（[[lex.pptoken]] ¶1）

```
preprocessing-token:
    header-name
    import-keyword
    module-keyword
    export-keyword
    identifier
    pp-number
    character-literal
    user-defined-character-literal
    string-literal
    user-defined-string-literal
    preprocessing-op-or-punc
    each non-whitespace character that cannot be one of the above
```

¶1 **预处理记号**（[[g:preprocessing-token|preprocessing token]]）是翻译阶段 3 到 5 中最小的词法单位。它们是：头文件名，模块指令产生的三种占位记号，标识符，预处理数字，字符字面量和字符串字面量（都包括用户定义的形式），预处理运算符和标点，以及不属于以上各类的单个非空白字符。

最后一类是兜底：有了它，预处理器可以搬运任何字符，比如传给宏再字符串化，而不必在阶段 3 就拒绝。但兜底有限制：

!!! std
    If a U+0027 apostrophe, a U+0022 quotation mark, or any character not in the basic character set matches the last category, the program is ill-formed.

- 落单的 `'` 或 `"` 说明字面量没有闭合。C++23 及以前这是 UB，C++26 的 [[P2621R2]] 改成了非良构。
- 基本字符集（[[lex.charset]]）以外的字符，例如 `€`，要么属于某个标识符（有 XID 属性时，见 [[lex.name]]），要么出现在字面量或注释里，否则程序非良构。
- 基本字符集里没有语法用途的字符 `@`、`` ` ``、`$`，以及落单的 `\`，可以作为单字符的预处理记号存在，只要在阶段 6 之前消失，例如被字符串化：

```cpp run title="stray.cpp" ok
#define S(x) #x
const char* at = S(@);    // OK：@ 是基本字符，单独成记号，字符串化为 "@"
const char* bt = S(`);    // OK：同上
// const char* eu = S(€); // error: € 不在基本字符集中
int main() { return at[0] == '@' && bt[0] == '`' ? 0 : 1; }
```

### 空白与注释（¶2、[[lex.comment]]）

¶2 预处理记号之间可以用空白分隔。空白指注释，或者空格、水平制表、换行、垂直制表、换页这几个字符，或者两者都有。注 1 说，在阶段 4 的某些场合，有没有空白不只影响分隔，例如函数式宏的名字和 `(` 之间。空白只有作为头文件名的一部分、或者在字面量的引号之间，才能出现在一个预处理记号内部。

[[lex.comment]] ¶1 规定了两种注释。`/*` 开始的注释到 `*/` 结束，**不嵌套**；`//` 开始的注释到下一个换行之前结束，换行本身不属于注释，所以 `//` 注释后面的换行照样能结束一条预处理指令。注 1 说，`//` 注释里的 `//`、`/*`、`*/` 没有特殊含义，`/*` 注释里的 `//` 和 `/*` 也没有。

```cpp run title="comments.cpp" ok
/* 外层 /* 这不是嵌套的开始 */
int a = 1;   // 上一行的 */ 已经结束了注释
// 这里的 /* 不开始任何东西
int b = 2;
int main() { return a + b - 3; }
```

因为注释不嵌套，`/* ... */` 注释不掉一段本身含有 `/* */` 的代码，这就是 `#if 0 ... #endif` 惯用法的由来。字符串字面量里的 `//` 不是注释，因为切分字面量时它已经作为字面量的一部分被消耗掉了；注释里的 `"` 也不开始字符串。

注释在阶段 3 变成一个空格，所以 `a/**/b` 是两个记号，宏既不能产生注释，也不能吞掉注释（[[lex.phases]]）。

### 转换成记号的条件（¶3）

¶3 每个要转换成记号的预处理记号，都必须具有关键字、标识符、字面量、头文件名或运算符、标点的词法形式。所以不是合法字面量的预处理数字（例如 `1.2.3`），以及残留到阶段 6 的 `@`、`` ` ``、`\`，都使程序非良构。

### 模块指令的占位记号（¶4）

¶4 预处理 `import` 指令（[[cpp.import]]）时产生 *import-keyword*，预处理 `module` 指令（[[cpp.module]]）时产生 *module-keyword*，两种指令中的 `export` 产生 *export-keyword*。注 2：它们都没有可观察的拼写。

C++20 的模块要求构建系统不必完整编译就能扫描出依赖，所以以 `import`、`module`（可以带 `export`）开头的行被设计成预处理指令，预处理器能识别它们，也能处理导入的宏。识别之后，开头的 `import`、`module`、`export` 换成这些看不见的占位记号。这样它们不再是指令，不会在阶段 4 末尾被删除（[[cpp.import]] 的注 2），后续阶段也能把它们和名叫 `import`、`module` 的普通标识符区分开。

```cpp run title="module-ident.cpp" ok
class module {};
module *m2;              // 不是 module 指令：module 后面跟着 *
class import {};
::import *p = nullptr;   // import 不在行首，是普通标识符
int main() {}
```

这个例子改编自 [[diff.cpp17.lex]]。如果写成 `module m1;` 或 `import j1;`，它们就成了模块声明或导入声明。更多讨论见 [[lex.name]] 的特殊含义标识符一节。

## 最长匹配及其例外（¶5）

¶5 假设输入已经切分到某个字符，下一个预处理记号按下面的顺序确定。

### 原始字符串优先（¶5.1）

¶5.1 如果接下来的字符可能是原始字符串字面量的前缀加起始双引号，例如 `R"`，那么下一个预处理记号必须是原始字符串字面量。在原始字符串的两个双引号之间，阶段 2 做的行拼接要撤销，撤销发生在识别分隔符和内容之前。原始字符串字面量取匹配 `encoding-prefix(opt) R raw-string` 这一模式的**最短**字符序列。

由此有两点。第一，即使 `R` 是一个宏名也不会展开，因为切分（阶段 3）先于宏展开（阶段 4）。这是 ¶6 的例 1：

```cpp title="raw-macro.cpp" error
#define R "x"
const char* s = R"y";   // error: 这是一个非良构的原始字符串，而不是 "x" "y"
```

`R"y";` 开始了一个原始字符串，分隔符 `y";` 之后找不到 `(`，于是非良构。C++03 的代码如果先 `#define u8 "abc"` 再写 `u8"def"`，到 C++11 含义就变了，原因相同（[[diff.cpp03.lex]]）。

第二，匹配的是最短序列：原始字符串在第一个“`)` 加分隔符加 `"`”处结束，不会继续往后找。

### `<::` 的例外（¶5.2）

¶5.2 否则，如果接下来三个字符是 `<::`，而第四个字符既不是 `:` 也不是 `>`，那么 `<` 单独成为一个预处理记号，而不是替代记号 `<:`（即 `[`，见 [[lex.digraph]]）的第一个字符。

这条规则是 C++11 加的，修复的是下面这种写法：

```cpp run title="angle-colon.cpp" ok
#include <vector>
#include <string>
std::vector<::std::string> v;   // C++03 中 <: 是 [，成了 vector[:std::string>
int main() {}
```

留下两种例外，是为了不破坏已有的双字符组写法：`<::>` 仍是 `<:` `:>`（即 `[]`），`<:::` 仍是 `<:` `::`（即 `[::`）。

```cpp run title="angle-colon-2.cpp" ok
constexpr int n = 2;
int a<::> = {1, 2, 3};   // <: :>      即 int a[] = {1, 2, 3};
int b<:::n:>;            // <: :: n :> 即 int b[::n];
struct T {};
template<class> struct V {};
V<::T> v;                // < :: T >
static_assert(sizeof a / sizeof a[0] == 3 && sizeof b / sizeof b[0] == 2);
int main() {}
```

### `[::` 和 `[:>` 的例外（¶5.3）{{c++26}}

¶5.3 否则，如果接下来三个字符是 `[::` 而第四个字符不是 `:`，或者接下来三个字符是 `[:>`，那么 `[` 单独成为一个预处理记号，而不是记号 `[:` 的第一个字符。

C++26 的静态反射（[[P2996R13]]）引入了拼接记号 `[:` 和 `:]`，例如 `[:r:]`。按最长匹配，`a[::n]`（以全局限定名作下标）会切成 `a [: :n]`，大量现有代码会因此失效。这条例外保住了它们：

- `a[::n]` 切成 `a` `[` `::` `n` `]`；
- `int x[:>` 切成 `int x` `[` `:>`，`:>` 是 `]` 的双字符组，整体是 `int x[]`；
- `[:::x:]` 的第四个字符是 `:`，仍切成 `[:` `::` `x` `:]`，即拼接 `::x`。

注 3 说，`[:` 和 `:]` 不能用双字符组拼出来，`<::` 不会变成 `[:`。

### 最长匹配（¶5.4）

¶5.4 否则，下一个预处理记号是能构成预处理记号的最长字符序列，即使这会让后续的词法分析失败。

!!! std
    the next preprocessing token is the longest sequence of characters that could constitute a preprocessing token, even if that would cause further lexical analysis to fail

这让词法分析器成为一个简单、不回溯的自动机，代价是一些反直觉的结果。开头的 `x+++++y` 是 ¶8 的例 3。¶7 的例 2 是：

```cpp title="pp-number-munch.cpp" error
#define foo 1
int g() { return 0xe+foo; }   // error: 0xe+foo 是一个预处理数字，不是 0xe + foo
```

`e+` 在预处理数字的文法里是指数部分（见下文），所以 `0xe+foo` 整个是一个预处理数字。宏 `foo` 根本不会被看到，因为它不是一个单独的标识符记号。到阶段 6 它不是合法的字面量，程序非良构。同理，即使 `E` 是宏名，`1E1` 也总是一个预处理数字。

`>>` 总是切成一个记号。`vector<vector<int>>` 能编译，是因为阶段 7 的语法规则把模板实参列表里第一个不在括号内的 `>>` 当作两个 `>`（[[temp.names]]），这不是词法上的例外：

```cpp run title="shift.cpp" ok
#include <vector>
template<int N> struct Y {};
std::vector<std::vector<int>> v;   // >> 由语法规则拆开
Y<(8>>1)> y1;                      // 括号里的 >> 仍是右移
// Y<8>>1> y2;                     // error: 拆开后第一个 > 结束了实参列表
int main() {}
```

### 头文件名的两条限定（¶5.4.1、¶5.4.2）

最长匹配还有两条限定：

- ¶5.4.1 能形成头文件名时，就不形成字符串字面量。所以 `#include "a\n.h"` 中的 `\n` 不是转义序列（不过头文件名里的 `\` 是有条件支持的，见下文）。
- ¶5.4.2 头文件名只在三种位置形成：`#include`、`#embed` 指令中紧跟在 `include`、`embed` 之后；位于逻辑源行开头的 `import` 之后；`#if`、`#elif`、`#embed` 指令中紧跟在 `__has_include (` 或 `__has_embed (` 之后。紧跟的意思是在同一逻辑源行上，中间没有别的预处理记号。

限制位置是因为在普通代码里 `<` 和 `>` 是比较运算符，`a<b>c` 不能当作头文件名。[[diff.cpp17.lex]] 记录了这条规则的一个后果：

```cpp title="import-header.cpp" error
template<typename> class import {};
import<int> f();     // error: 行首的 import 之后，<int> 切成头文件名，这是一条 import 指令
::import<int> g();   // OK：import 不在行首
```

本机 Clang 23 把第二行当作导入头文件 `<int>`，报告 'int' file not found。`#embed` 和 `__has_embed` 是 C++26 加入的。

## 头文件名（[[lex.header]]）

```
header-name:
    < h-char-sequence >
    " q-char-sequence "
h-char:  除换行和 > 之外的任何字符
q-char:  除换行和 " 之外的任何字符
```

¶1 两种形式里的字符序列以实现定义的方式映射到头文件或外部源文件名（[[cpp.include]]）。注 1 说，头文件名只出现在 `#include` 指令、`__has_include` 表达式和某些 `import` 之后。

¶2 头文件名中出现 `'`、`\`、`/*` 或 `//`，以及 `<...>` 形式中出现 `"`，是有条件支持的，语义由实现定义。注 2 说，看起来像转义序列的写法，可能报错，可能被解释成对应的字符，也可能有完全不同的含义。

这几个字符各有原因。`\` 是 Windows 路径的分隔符，头文件名不是字符串字面量，`"dir\file.h"` 里的 `\f` 不是换页符，但标准不强迫所有平台接受反斜杠路径。`'` 在老的预处理器里可能被当成字符字面量的开头。`//` 和 `/*` 在实现先识别注释时会出问题；本机 Clang 23 对 `#include <a//b>` 找的是名为 `a//b` 的文件。可移植的代码只用 `/`，Windows 上的编译器也都接受它。

## 预处理数字（[[lex.ppnumber]]）

```
pp-number:
    digit
    . digit
    pp-number identifier-continue
    pp-number ' digit
    pp-number ' nondigit
    pp-number e sign
    pp-number E sign
    pp-number p sign
    pp-number P sign
    pp-number .
```

[[g:pp-number|预处理数字]]以数字或“`.` 加数字”开头，后面可以跟任意多个标识符字符、`.`、`'` 加数字或字母，以及 `e+`、`e-`、`E+`、`E-`、`p+`、`p-`、`P+`、`P-`。

¶1 预处理数字在词法上包括所有整数字面量和浮点字面量。¶2 预处理数字没有类型和值，成功转换成整数字面量或浮点字面量之后才有。

这个文法故意放宽。预处理器不必知道字面量的精确文法，也不必随着新后缀的出现而修改：`123_km`、`1.0f16`、`0x1p-3`、`1'000'000uz` 都是一个预处理数字。宏用 `##` 拼数字时，中间结果也不必是合法字面量。代价是一些看起来是表达式的写法会被整个吞掉：

| 源码 | 切分 | 结果 |
|---|---|---|
| `1.2.3` | 一个预处理数字 | 阶段 6 非良构 |
| `0xe+1` | 一个预处理数字 | 非良构，应写 `0xe + 1` |
| `1.e+5` | 一个预处理数字 | 合法的浮点字面量 |
| `1_km+2` | `1_km` `+` `2` | `+` 前面不是 `e` 或 `p`，不并入 |
| `1_e+2` | 一个预处理数字 | `_e` 末尾的 `e` 和 `+` 构成指数，整个被吞掉，非良构 |

!!! history "预处理数字的两次扩展"
    C++14 加入数字分隔符，预处理数字增加了 `' digit` 和 `' nondigit`。于是对 `M(1'2,3'4, 5)`，C++11 中 `'2,3'` 是一个字符字面量，宏只收到两个实参；C++14 中是三个实参（[[diff.cpp11.lex]]）。C++17 加入十六进制浮点字面量，预处理数字增加了 `p sign` 和 `P sign`，于是 `0p+0` 从三个记号变成一个（[[diff.cpp14.lex]]）。

!!! impl "Clang 的偏离"
    本机 Clang 23 只在数字以 `0x` 或 `0X` 开头时才把 `p+`、`p-` 并入预处理数字。[[diff.cpp14.lex]] 的例子 `#define F(a) b ## a` 加 `int b0p = F(0p+0);`，按标准 `0p+0` 是一个预处理数字，`b ## 0p+0` 拼不出合法记号，程序非良构；Clang 却把 `0p+0` 切成三个记号，接受了它。

## 运算符与标点（[[lex.operators]]）

¶1 有些预处理记号用于预处理器的语法，有些会转换成运算符和标点记号：

```
preprocessing-operator: one of
  #   ##  %:  %:%:
operator-or-punctuator: one of
  {   }   [   ]   (   )   [:  :]
  <%  %>  <:  :>  ;   :   ...
  ?   ::  .   .*  ->  ->* ^^  ~
  !   +   -   *   /   %   ^   &   |
  =   +=  -=  *=  /=  %=  ^=  &=  |=
  ==  !=  <   >   <=  >=  <=> &&  ||
  <<  >>  <<= >>= ++  --  ,
  and or  xor not bitand  bitor  compl
  and_eq  or_eq  xor_eq  not_eq
```

每个运算符或标点在阶段 6 转换成一个记号。

- `#`、`##` 和它们的双字符组 `%:`、`%:%:` 只是预处理运算符。它们残留到阶段 6（例如出现在普通代码里）就无法转换，程序非良构。
- `and`、`or` 等是运算符记号，既不是关键字也不是标识符（[[lex.digraph]]、[[lex.key#3]]）。
- 较新的成员有 `<=>`（C++20），以及反射用的 `^^`、`[:`、`:]`（C++26）。

加入新记号会改变最长匹配的结果，可能破坏旧代码。下面两个例子分别来自 [[diff.cpp17.lex]] 和 [[diff.cpp23.lex]]：

```cpp title="spaceship-break.cpp" error
namespace N {
  struct X {};
  bool operator<=(X, X);
  template<bool(X, X)> struct Y {};
  Y<operator<=> y;   // C++20 起 error: <=> 是一个记号；C++17 中是 operator<= 和 >
}
```

```cpp title="reflect-break.cpp" error
struct C { int operator^(int); };
int operator^(int (C::*p)(int), C);
int i = &C::operator^^C{};   // C++26 起 error: ^^ 是一个记号；C++23 中是 ^ ^
```

本机 Clang 23 还没有实现 `^^` 记号，所以第二个例子能通过编译。

## 记号（[[lex.token]]）

```
token:
    identifier
    keyword
    literal
    header-name
    operator-or-punctuator
```

¶1 正文说记号有六种：标识符、关键字、字面量、头文件名、运算符，以及其他分隔符。文法只有五个分支，是因为运算符和其他分隔符（标点）在文法里合成了一个 *operator-or-punctuator*。头文件名也是记号：`import <vector>;` 里的头文件名一直保留到阶段 7，供 [[module.import]] 的文法使用。

阶段 6 中预处理记号和记号的对应关系如下：

| 预处理记号 | 阶段 6 后成为 |
|---|---|
| 标识符 | 标识符或关键字（[[lex.key]]） |
| 预处理数字 | 整数字面量、浮点字面量或用户定义字面量；都不是则非良构 |
| 字符、字符串字面量 | 字面量（相邻的字符串已在阶段 5 拼接） |
| 预处理运算符或标点 | 运算符或标点；`#`、`##` 非良构 |
| 头文件名 | 头文件名 |
| 模块指令的占位记号 | 关键字（[[lex.key]] 文法中的 *import-keyword* 等） |
| 其他单个字符 | 非良构 |

## 常见误解

!!! pitfall "编译器会按意图切分"
    `a+++b` 是 `a++ + b`；`a+++++b` 永远非良构；`a/ *p` 是除法，`a/*p` 开始了一个注释。复杂的表达式用空格隔开。

!!! pitfall "数字后面的宏会展开"
    `#define E 10` 之后，`1E` 不会展开 `E`，`0x1e+E` 也不会。数字后面紧跟字母的地方，宏都看不见。

## 思考题

!!! question "思考题 1"
    下面各行切成哪些预处理记号？哪些最终良构？

    ```cpp
    a = b---c;     // (1)
    a = b-- - -c;  // (2)
    p = q->*r;     // (3)
    x = y/**/z;    // (4)
    n = 1.0e-3_m;  // (5)
    ```

<details markdown="1">
<summary>答案</summary>

1. `b -- - c`：最长匹配先切出 `--`，剩下 `-`。良构，即 `(b--) - c`。
2. `b -- - - c`：良构，即 `(b--) - (-c)`。
3. `q ->* r`：`->*` 是一个三字符的记号，表示通过成员指针访问。
4. `y z`：注释变成空格，`x = y z;` 是语法错误。
5. `1.0e-3_m` 是一个预处理数字（`e-` 是指数，`_m` 是标识符字符），阶段 6 成为用户定义的浮点字面量，需要声明了 `operator""_m`。
</details>

!!! question "思考题 2"
    为什么 ¶5.3 只排除 `[::` 后面跟 `:` 的情况，而 ¶5.2 排除了 `<::` 后面跟 `:` 或 `>` 两种情况？

<details markdown="1">
<summary>答案</summary>

¶5.2 要保住已有的双字符组写法：`<::>` 是 `[]`，`<:::` 是 `[::`，两者都要求 `<:` 被识别成双字符组。

¶5.3 要保住的是不表示拼接的 `[::`，即下标里的全局限定名。而 `[:::` 必须仍切成 `[:` `::`，因为拼接一个以 `::` 开头的名字就是这样写的，所以只能排除第四个字符为 `:` 的情况。`[:>` 单独列出，是为了 `x[:>` 这种写法：`:>` 是 `]` 的双字符组，整体是 `x[]`；如果切成 `[:` `>`，它就成了一次拼接的开头。
</details>
