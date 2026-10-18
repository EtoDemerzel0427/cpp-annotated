---
title: 预处理记号与记号
summary: 预处理记号的种类、最长匹配（maximal munch）及其例外（原始字符串、<::、[::）、注释、头文件名、预处理数字、运算符与标点，以及阶段 6 之后的"记号"。
status: draft
covers: lex.comment, lex.header, lex.ppnumber, lex.operators, lex.token
related: lex.phases, lex.digraph, cpp.include, cpp.import, temp.names
tags: 词法, 预处理, maximal munch
updated: 2026-10-17
---

本页覆盖 5.4–5.8 与 5.10 共六个小节。它们共同回答：**阶段 3 怎样把字符流切成一个个预处理记号，阶段 6 又把它们变成什么**。核心是 [[lex.pptoken#5]] 的[[g:maximal-munch|**最长匹配**]]规则——几乎所有"词法谜题"都由它和它的几条例外解释。

| 小节 | 内容 |
|---|---|
| [[lex.comment]] | 两种注释，不嵌套 |
| [[lex.pptoken]] | 预处理记号的种类、空白、最长匹配 |
| [[lex.header]] | `<...>` 与 `"..."` 头文件名 |
| [[lex.ppnumber]] | 预处理数字：一个宽松得惊人的文法 |
| [[lex.operators]] | 运算符与标点表 |
| [[lex.token]] | 阶段 6 之后的记号 |

替代记号（`<%`、`and` 等）单独成页：[[lex.digraph]]。

## 注释（[[lex.comment]]）

¶1 `/*` 开始一个注释，以 `*/` 结束；这种注释**不嵌套**。`//` 开始一个注释，结束于下一个换行字符**之前**（换行本身不属于注释，因此 `//` 注释后面的换行依然能结束一条预处理指令）。注 1：在 `//` 注释中，`//`、`/*`、`*/` 没有特殊含义；在 `/*` 注释中，`//` 和 `/*` 也没有特殊含义。

```cpp run title="comments.cpp" ok
/* 外层 /* 这不是嵌套的开始 */
int a = 1;   // 上一行的 */ 已经结束了注释
// 这里的 /* 不开始任何东西
int b = 2;
int main() { return a + b - 3; }
```

"不嵌套"意味着不能用 `/* ... */` 注释掉一段本身含 `/* */` 的代码——这正是 `#if 0 ... #endif` 惯用法存在的原因。

注释与字面量互不干扰：字符串字面量里的 `//` 不是注释（阶段 3 在识别字符串字面量时会消耗它），注释里的 `"` 也不开始字符串。但要注意注释是在**预处理记号化**时识别的，所以 `'` 在 `#if 0` 块中可能引发问题（见 [[lex.phases]] 的陷阱）。

注释在阶段 3 被替换为一个空格（[[lex.phases]]），所以：

- 注释是记号的分隔符：`a/**/b` 是两个记号；
- 宏无法产生注释，也无法"吃掉"注释。

## 预处理记号（[[lex.pptoken]]）

### 种类（¶1）

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

¶1 预处理记号是翻译阶段 3–5 中语言的最小词法单元。最后一类"不能匹配其他类别的单个非空白字符"是一个兜底：它让预处理器可以搬运任意字符（例如传给宏后再字符串化），而不必在阶段 3 就拒绝。

但兜底有限制：如果 **`'`、`"`** 或**任何不在基本字符集中的字符**落入最后这一类，程序非良构。

!!! std
    If a U+0027 apostrophe, a U+0022 quotation mark, or any character not in the basic character set matches the last category, the program is ill-formed.

    游离的引号、以及非基本字符（如 `€`、`😀`），不能作为"其他单字符"预处理记号。

- 游离的 `'` 或 `"` 意味着字面量没有闭合。C++23 及以前，这种情况是 UB；C++26 的 [[P2621R2]] 改成了非良构。
- 非基本字符不能当作"其他字符"——它们要么是标识符的一部分（若有 XID 属性，见 [[lex.name]]），要么出现在字面量或注释里，否则非良构。
- 基本字符集里没有语法用途的字符（`@`、`` ` ``、`$`，以及游离的 `\`）可以作为单字符预处理记号存在，只要它们在阶段 6 之前消失（例如被字符串化）：

```cpp run title="stray.cpp" ok
#define S(x) #x
const char* at = S(@);    // OK：@ 是基本字符，作为单字符预处理记号被字符串化为 "@"
const char* bt = S(`);    // OK：同上
// const char* eu = S(€); // error：€ 不在基本字符集中
int main() { return at[0] == '@' && bt[0] == '`' ? 0 : 1; }
```

### 空白（¶2）

¶2 预处理记号之间可以用空白分隔：注释、或空白字符（空格、水平制表、换行、垂直制表、换页），或两者。注 1：在阶段 4 的某些场合，空白（或其缺失）不仅仅是分隔——例如函数式宏定义中宏名与 `(` 之间是否有空白、`#` 字符串化时记号之间是否有空白。空白只能作为头文件名的一部分或者字符/字符串字面量引号之间的内容出现在预处理记号**内部**。

### 能转换为记号的形式（¶3）

¶3 每个被转换为记号（[[lex.token]]）的预处理记号必须具有关键字、标识符、字面量、头文件名或运算符/标点的词法形式。于是：

- 一个不是合法 *integer-literal*/*floating-point-literal* 的 *pp-number*（如 `1.2.3`、`0xe+1`）在阶段 6 使程序非良构；
- 残留到阶段 6 的 `@`、`` ` ``、`\` 使程序非良构。

### import / module / export 占位记号（¶4）

¶4 *import-keyword* 由处理 import 指令（[[cpp.import]]）产生，*module-keyword* 由处理 module 指令（[[cpp.module]]）产生，*export-keyword* 由处理上述两种指令中的任一种产生。注 2：它们都**没有可观察的拼写**。

为什么需要这些"看不见的记号"？C++20 模块要求构建系统能在**不完整编译**的情况下扫描出依赖关系。于是 `import`/`module` 开头的行被设计成**预处理指令**：预处理器识别它们（因为其中可能导入宏），把开头的 `import`/`module`/`export` 换成这些特殊记号——这样它们就不再是指令，不会在阶段 4 末尾被删除（[[cpp.import]] 注 2），而后续阶段又能可靠地把它们与普通标识符 `import`、`module` 区分开。

```cpp run title="module-ident.cpp" ok
class module {};
module *m2;              // 不是 module 指令：module 后跟 *，是普通变量声明
class import {};
::import *p = nullptr;   // 加 :: 使 import 不在行首，于是它是普通标识符
int main() {}
```

（上例改编自 [[diff.cpp17.lex]]。若写成 `module m1;` 或 `import j1;`，它们会被当作模块声明 / 导入声明。）更多讨论见 [[lex.name]] 的"特殊含义标识符"一节。

## 最长匹配（¶5）

¶5 是本页的核心。设输入已被切分到某个字符，下一个预处理记号按以下优先顺序确定：

### ¶5.1　原始字符串优先

如果接下来的字符可能是原始字符串字面量的前缀加起始双引号（如 `R"`），则下一个预处理记号**必须**是原始字符串字面量。在原始字符串的起止双引号之间，阶段 2 的变换（行拼接）**被撤销**；撤销发生在识别任何 *d-char*、*r-char* 或分隔括号之前。原始字符串字面量定义为匹配

```
encoding-prefix(opt) R raw-string
```

模式的**最短**字符序列。

两个要点：

1. "必须是原始字符串"——即使 `R` 是一个宏名也不展开，因为阶段 3 的切分先于阶段 4 的宏展开。¶6 的例 1：

```cpp title="raw-macro.cpp" error
#define R "x"
const char* s = R"y";   // error：这是一个非良构的原始字符串，而不是 "x" "y"
```

`R"y";` 开始了一个原始字符串，`y";` 之后找不到 `(`（换行不能作为 *d-char*），于是非良构。C++03 的代码 `#define u8 "abc"` 后写 `u8"def"` 在 C++11 中改变了含义，也是同样的原因（[[diff.cpp03.lex]]）。

2. "最短序列"：原始字符串在第一个 `)` + 分隔符 + `"` 处结束，不贪婪地往后找。

### ¶5.2　`<::` 例外

否则，如果接下来三个字符是 `<::` 且第四个字符**既不是** `:` **也不是** `>`，则 `<` 单独作为一个预处理记号，而不是替代记号 `<:`（即 `[`）的第一个字符。

这条规则来自 C++11，修复的是：

```cpp run title="angle-colon.cpp" ok
#include <vector>
#include <string>
std::vector<::std::string> v;   // C++03 中 <: 是 [，于是成了 vector[:std::string>，编译失败
int main() {}
```

保留两个例外是为了不破坏已有的双字符组用法：`<::>` 仍是 `<:` `:>`（即 `[]`），`<:::` 仍是 `<:` `::`（即 `[::`）。

```cpp run title="angle-colon-2.cpp" ok
constexpr int n = 2;
int a<::> = {1, 2, 3};   // <: :>    即  int a[] = {1, 2, 3};
int b<:::n:>;            // <: :: n :>  即  int b[::n];
struct T {};
template<class> struct V {};
V<::T> v;                // < :: T >
static_assert(sizeof a / sizeof a[0] == 3 && sizeof b / sizeof b[0] == 2);
int main() {}
```

### ¶5.3　`[::` 与 `[:>` 例外 {{c++26}}

否则，如果接下来三个字符是 `[::` 且第四个字符不是 `:`，或者接下来三个字符是 `[:>`，则 `[` 单独作为一个预处理记号，而不是预处理记号 `[:` 的第一个字符。

C++26 的静态反射（[[P2996R13]]）引入了**拼接符**（splice）记号 `[:` 和 `:]`（如 `[:r:]`）。最长匹配会让 `a[::x]`（以全局限定名作下标）被切成 `a [: :x]`，破坏大量现有代码。这条例外保住了它们：

- `a[::n]` → `a` `[` `::` `n` `]`；
- `int x[:>` → `int x` `[` `:>`（`:>` 是 `]` 的双字符组），即 `int x[]`；
- 而 `[:::x:]`（第四个字符是 `:`）仍切成 `[:` `::` `x` `:]`，即拼接 `::x`。

注 3：`[:` 和 `:]` **不能**由双字符组构成——`<::` 不会变成 `[:`。

### ¶5.4　最长匹配

否则，下一个预处理记号是**能构成预处理记号的最长字符序列**，即使这会导致后续词法分析失败。

!!! std
    the next preprocessing token is the longest sequence of characters that could constitute a preprocessing token, even if that would cause further lexical analysis to fail

    贪婪，且不回溯：即使换一种切法能让程序合法，也不换。

这就是著名的 **maximal munch**。它让词法分析器是简单、无需回溯的确定性有限自动机，代价是若干反直觉的结果——¶7 和 ¶8 的两个例子：

```cpp title="munch.cpp" error
int f(int x, int y) {
  return x+++++y;    // 切成 x ++ ++ + y；x++ 是 prvalue，不能再 ++ ⇒ error
}
```

`x ++ + ++ y` 本来是合法的，但词法分析不会考虑它。

```cpp title="pp-number-munch.cpp" error
#define foo 1
int g() { return 0xe+foo; }   // error：0xe+foo 是一个 pp-number，不是 0xe + foo
```

`e+` 在 *pp-number* 文法里是指数部分（见下文 [[lex.ppnumber]]），于是 `0xe+foo` 整个是一个预处理数字——宏 `foo` 根本不会被看到（它不是独立的标识符记号）。阶段 6 中它不是合法的字面量，非良构。类似地，`1E1` 总是一个 pp-number，即使 `E` 是宏名。

最长匹配与模板：`>>` 总是被切成一个记号（右移），`vector<vector<int>>` 能工作，是因为**语法分析**（阶段 7）的 [[temp.names]] 规则把模板实参列表中第一个非嵌套的 `>>` 视为两个 `>`。这不是词法例外。

```cpp run title="shift.cpp" ok
#include <vector>
template<int N> struct Y {};
std::vector<std::vector<int>> v;   // >> 被语法规则拆分
Y<(8>>1)> y1;                      // 加括号后 >> 是嵌套的，仍是右移
// Y<8>>1> y2;                     // error：第一个 > 结束了实参列表
int main() {}
```

### ¶5.4.1–¶5.4.2　头文件名的例外

最长匹配本身还有两个限定：

- ¶5.4.1　能形成 *header-name* 时，**永远不**形成 *string-literal*。所以 `#include "a\n.h"` 中的 `\n` 不会被当作转义序列（头文件名里的 `\` 本身是有条件支持的，见下文 [[lex.header]] ¶2）。
- ¶5.4.2　*header-name* **只**在以下位置形成：
    - `#include` 或 `#embed` 指令中紧跟在 `include`/`embed` 预处理记号之后；
    - 位于逻辑源行开头的 `import` 预处理记号之后；
    - `#if`、`#elif` 或 `#embed` 指令中，紧跟在 `__has_include (` 或 `__has_embed (` 之后。

"紧跟"（immediately after）定义为：在同一逻辑源行上且中间没有其他预处理记号。

为什么要限制？因为 `<` … `>` 在普通代码中可以是小于和大于：`a<b>c` 不能被当作一个头文件名。只有在确知需要头文件名的上下文中才这样切。[[diff.cpp17.lex]] 记录了一个后果：

```cpp title="import-header.cpp" error
template<typename> class import {};
import<int> f();     // error：行首的 import 之后，<int> 被切成头文件名 ⇒ 这是 import 指令
::import<int> g();   // OK：import 不在行首
```

（实测 Clang 23 把第二行当作导入头文件 `<int>`，报"file not found"。）

`#embed`（[[cpp.embed]]）和 `__has_embed` 是 C++26 加入的 {{c++26}}。

## 头文件名（[[lex.header]]）

```
header-name:
    < h-char-sequence >
    " q-char-sequence "
h-char:  翻译字符集中除换行和 > 以外的任何成员
q-char:  翻译字符集中除换行和 " 以外的任何成员
```

¶1 两种形式中的字符序列都以**实现定义**的方式映射到头文件或外部源文件名（[[cpp.include]]）。注 1：头文件名预处理记号只出现在 `#include` 指令、`__has_include` 预处理表达式以及某些 `import` 之后。

¶2 在 *q-char-sequence* 或 *h-char-sequence* 中出现 `'`、`\`、`/*` 或 `//`，以及在 *h-char-sequence* 中出现 `"`，是**有条件支持**的，语义由实现定义。注 2：因此，看起来像转义序列的字符，可能导致错误、被解释为对应字符，或有完全不同的含义。

为什么要专门"降级"这些字符？

- `\`：Windows 路径 `#include "dir\file.h"`。头文件名不是字符串字面量，`\f` 不是换页符——但为了不强迫所有平台接受反斜杠路径，标准把它定为有条件支持。**可移植代码只用 `/`**，Windows 编译器也都接受 `/`。
- `'`：在 C++14 之前的预处理器里，`'` 可能被当作字符字面量的开始。
- `//`、`/*`：在 `<...>` 中，如果实现先识别注释再识别头文件名就会出问题。例如 `#include <a//b>`，Clang 把它当作文件名 `a//b`。

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

用自然语言说：以数字或"`.` + 数字"开头，之后可以跟任意多个**标识符字符**、`.`、`'`+数字或字母、以及 `e+` `e-` `E+` `E-` `p+` `p-` `P+` `P-`。

¶1 预处理数字在词法上包含所有 *integer-literal* 和 *floating-point-literal* 记号。¶2 预处理数字**没有类型或值**；只有成功转换为整数或浮点字面量记号之后才获得类型和值。

这个文法**故意**宽松：

1. 预处理器无须知道字面量的精确文法，也无须随新的后缀而修改——`123_km`、`1.0f16`、`0x1p-3`、`1'000'000uz` 都是一个 pp-number。
2. 宏可以通过 `##` 拼出数字，中间结果不必是合法字面量。

代价是一些"看起来分明是表达式"的东西被吞成一个记号：

| 源码 | 切分 | 结果 |
|---|---|---|
| `1.2.3` | 一个 pp-number | 阶段 6 非良构 |
| `0xe+1` | 一个 pp-number | 非良构（`0xe + 1` 才对） |
| `1e+foo` | 一个 pp-number | 非良构 |
| `1_km+2` | 一个 pp-number？ | 否：`_km` 之后的 `+` 前不是 `e`/`p`，切成 `1_km` `+` `2` |
| `1.e+5` | 一个 pp-number | 合法的浮点字面量 |
| `1_e+2` | 一个 pp-number | `_e` 末尾的 `e` 与 `+` 构成 `e sign`，于是整个吞掉 ⇒ 非良构 |

!!! history "pp-number 的两次扩展"
    - C++14 加入数字分隔符，pp-number 增加了 `' digit` 和 `' nondigit`。于是 `M(1'2,3'4, 5)` 在 C++11 中，`'2,3'` 是一个字符字面量（宏只收到两个实参），在 C++14 中则是三个实参（[[diff.cpp11.lex]]）。
    - C++17 加入十六进制浮点，pp-number 增加了 `p sign` 和 `P sign`。于是 `0p+0` 从三个记号变成一个（[[diff.cpp14.lex]]）。

!!! impl "Clang 的偏离"
    实测 Clang 23 只在数字以 `0x`/`0X` 开头时才把 `p+`/`p-` 并入预处理数字。[[diff.cpp14.lex]] 的例子 `#define F(a) b ## a` / `int b0p = F(0p+0);` 按标准是非良构的（`0p+0` 是一个 pp-number，`b ## 0p+0` 拼不出合法记号），Clang 却把 `0p+0` 切成三个记号并接受了它。

## 运算符与标点（[[lex.operators]]）

¶1 C++ 程序的词法表示包含若干预处理记号，它们用于预处理器的语法，或被转换为运算符和标点记号：

```
preprocessing-operator:  #  ##  %:  %:%:
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

每个 *operator-or-punctuator* 在阶段 6 被转换为**单个**记号。

几点说明：

- `#`、`##`（及双字符组 `%:`、`%:%:`）只是**预处理运算符**，不是 *operator-or-punctuator*；它们若残留到阶段 6（例如出现在普通代码中），无法转换为记号，程序非良构。
- `and`、`or` 等**是**运算符记号，而不是关键字或标识符（见 [[lex.digraph]]、[[lex.key#3]]）。
- 新成员：`<=>`（C++20）、`^^`、`[:`、`:]`（C++26 反射）{{c++26}}。

新记号的加入会改变最长匹配，从而破坏旧代码：

```cpp title="spaceship-break.cpp" error
namespace N {
  struct X {};
  bool operator<=(X, X);
  template<bool(X, X)> struct Y {};
  Y<operator<=> y;   // C++20 起 error：<=> 是一个记号；C++17 中是 operator<= 和 >
}
```

```cpp title="reflect-break.cpp" error
struct C { int operator^(int); };
int operator^(int (C::*p)(int), C);
int i = &C::operator^^C{};   // C++26 起 error：^^ 是一个记号；C++23 中是 ^ ^
```

这两个例子分别来自 [[diff.cpp17.lex]] 和 [[diff.cpp23.lex]]。（截至写作时，Clang 23 主线尚未实现 `^^` 记号。）

## 记号（[[lex.token]]）

```
token:
    identifier
    keyword
    literal
    header-name
    operator-or-punctuator
```

¶1 记号有六种：标识符、关键字、字面量、头文件名、运算符，以及其他分隔符。

文法只有五个分支，正文却说"六种"——"运算符"和"其他分隔符（标点）"在文法中合并成了 *operator-or-punctuator*。这句话是历史遗留，没有规范性后果。值得注意的是 *header-name* 也是记号：`import <vector>;` 中的头文件名会一直存活到阶段 7，被 [[module.import]] 的文法使用。

记号与预处理记号的对应：

| 预处理记号 | 阶段 6 后成为 |
|---|---|
| *identifier* | *identifier* 或 *keyword*（[[lex.key]]）；`and` 等成为 *operator-or-punctuator* |
| *pp-number* | *integer-literal*、*floating-point-literal* 或用户定义字面量；否则非良构 |
| 字符/字符串字面量 | *literal*（相邻字符串已在阶段 5 拼接） |
| *preprocessing-op-or-punc* | *operator-or-punctuator*；`#`、`##` 非良构 |
| *header-name* | *header-name* |
| import/module/export 占位 | *keyword*（[[lex.key]] 文法中的 *import-keyword* 等） |
| 其他单字符 | 非良构 |

## 陷阱

!!! pitfall "以为编译器会\"聪明地\"切分"
    `a+++b` 是 `a++ + b`；`a+++++b` 永远非良构；`a/ *p` 和 `a/*p` 完全不同（后者开始注释）。写复杂表达式时用空格分开。

!!! pitfall "pp-number 吞掉了宏"
    `#define E 10` 之后 `1E` … 不会展开 `E`；`0x1e+E` 也不会。凡是"数字后面紧跟字母"的位置，宏都看不见。

!!! pitfall "`#include` 中的反斜杠"
    `#include "sys\stat.h"` 是有条件支持的；可移植代码用 `/`。

## 思考题

!!! question "思考题 1"
    下列各行分别被切成哪些预处理记号？哪些最终良构？

    ```cpp
    a = b---c;     // (1)
    a = b-- - -c;  // (2)
    p = q->*r;     // (3)
    x = y/**/z;    // (4)
    n = 1.0e-3_m;  // (5)
    ```

<details markdown="1">
<summary>答案</summary>

1. `b -- - c`：最长匹配先吃 `--`，剩下 `-`。合法：`(b--) - c`。
2. `b -- - - c`：合法：`(b--) - (-c)`。
3. `q ->* r`：`->*` 是一个三字符记号，成员指针访问。
4. `y z`（注释变成空格）：语法错误，`x = y z;` 非良构。
5. `1.0e-3_m` 是一个 pp-number（`e-` 是指数，`_m` 是标识符字符），阶段 6 成为用户定义浮点字面量，需要有 `operator""_m` 声明。
</details>

!!! question "思考题 2"
    为什么 ¶5.3 只排除 `[::` 后面跟 `:` 的情况（`[:::`），而 ¶5.2 排除了 `<::` 后跟 `:` **或** `>` 的两种情况？

<details markdown="1">
<summary>答案</summary>

¶5.2 要保住的是**已有**的双字符组用法：`<::>` 是 `[]`，`<:::` 是 `[::`，二者都依赖于 `<:` 被识别为双字符组。¶5.3 要保住的则是**非拼接**的 `[::`（下标中的全局限定名），而 `[:::` 必须仍识别为 `[:` `::`——这是"拼接一个以 `::` 开头的名字"的合法写法，所以只能排除第四字符为 `:` 的情况。另外 `[:>` 被单独列出，是为了 `x[:>`（`:>` 是 `]` 的双字符组，整体即 `x[]`）这种写法：若按最长匹配切成 `[:` `>`，就会变成一个拼接的开始。
</details>

## 小结

!!! summary
    - 预处理记号有 12 类，最后一类"其他单字符"不能是 `'`、`"` 或非基本字符（C++26 前为 UB）。
    - 切分规则优先级：原始字符串 > `<::` 例外 > `[::`/`[:>` 例外（C++26）> 最长匹配（头文件名只在特定上下文形成）。
    - 最长匹配不回溯：`x+++++y`、`0xe+foo`、`1.2.3` 都因此失败；`>>` 的拆分是语法规则，不是词法规则。
    - pp-number 故意宽松，没有类型和值，直到阶段 6。
    - `/* */` 不嵌套；注释在阶段 3 变成一个空格。
    - 头文件名中的 `\`、`'`、`//`、`/*` 有条件支持。
