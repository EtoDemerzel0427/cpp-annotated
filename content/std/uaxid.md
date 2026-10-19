---
title: 与 UAX #31 的一致性
summary: 资料性附录 E 用 Unicode 标识符规范 UAX #31 的术语说明 C++ 标识符规则：符合 R1（默认标识符语法，加上数学记号和下划线）与 R4（标识符必须是 NFC），其余要求或不采用、或不适用。
status: done
covers: *
papers: P1949R7
related: lex.name, lex.charset, lex.pptoken, diff.cpp20.lex, intro.refs
tags: 标识符, Unicode, 附录
updated: 2026-10-19
---

!!! tldr
    - C++ 标识符由一个起始字符和若干后续字符组成，哪些字符可用由 Unicode 的 XID_Start、XID_Continue 属性决定，另外允许 `_` 开头和一些数学记号（`∂`、`x₁`）。
    - 标识符必须是 NFC 形式，否则程序非良构。所以两个标识符相同就是码位序列相同，`ﬁ` 和 `fi` 是两个不同的名字。
    - C++ 不保证标识符字符集永远不变：Unicode 加入新文字后，新的字母可以成为合法的标识符字符。
    - 标识符区分大小写；`$` 不是标准的标识符字符，GCC 和 Clang 把它作为扩展接受。
    - Clang 23 不检查 NFC，看起来相同、编码不同的两个 `Å` 会被当作两个变量。

```cpp run ok
int 变量 = 1;        // 汉字：XID_Start
int _tmp = 2;        // _ 可以开头：C++ 在 UAX #31 之外额外加入
int café = 3;        // é 是预组合字符 U+00E9，NFC
int x·y = 4;         // U+00B7 MIDDLE DOT：XID_Continue，但不是 XID_Start
int ﬁ = 5;           // U+FB01 连字：NFC 下不变，所以合法
int fi = 6;          // 与上一行是不同的名字（C++ 用 NFC，不用 NFKC）
int ∂f = 7;          // U+2202：ID_Compat_Math_Start
int x₁ = 8, x² = 9;  // 下标、上标数字：ID_Compat_Math_Continue
int main() {}
```

上面每一行都是良构的。汉字、带重音的字母、上标数字都能出现在 C++ 标识符里，但这不是随意的：规范性规则在 [[lex.name]]，它把标识符字符的范围交给了 Unicode 的字符属性。

本附录 E 是资料性的，不增加任何规则。它用 Unicode 标准附录 31（**UAX #31**，[[g:uax31]]，*Unicode Identifier and Pattern Syntax*）的术语，说明 C++ 的标识符规则符合其中哪些要求。UAX #31 是给编程语言、配置格式等需要标识符的系统用的参考规范，它定义了一个默认的标识符语法和一组编号的可选要求（R1、R1b、R2 … R8）。一个系统声称符合 UAX #31 时，要说明符合哪几条、怎样符合。

## 概述（[uaxid.general]）

!!! std
    In terms of UAX #31, this document conforms by meeting the requirements R1 "Default Identifiers" and R4 "Equivalent Normalized Identifiers" from UAX #31.

¶1 C++ 符合 R1 和 R4。其余要求要么是 C++ 没有采用的另一种做法，要么不适用于 C++。整个附录可以浓缩成一张表：

| 要求 | 内容 | C++ 的立场 |
|---|---|---|
| R1 | 默认标识符语法 | 符合：采用数学记号 profile，另加 `_` 作起始字符，Medial 集为空 |
| R1b | 稳定的标识符 | 只在 XID 属性本身稳定的范围内成立 |
| R2 | 不可变的标识符字符集 | 不采用，可用字符随 Unicode 版本增加 |
| R3 | 用 Pattern_White_Space、Pattern_Syntax 定义空白和语法字符 | 不声称符合 |
| R4 | 按规范化形式判定等价 | 符合：标识符必须是 NFC |
| R5、R7 | 大小写不敏感的等价 | 不适用，C++ 区分大小写 |
| R6 | 规范化时排除某些字符 | 不作任何排除 |
| R8 | hashtag 标识符 | 不适用 |

## R1 默认标识符（[uaxid.def.general]）

### UAX #31 的默认语法

¶1 UAX #31 基于 Unicode 字符数据库（UAX #44）中的字符属性定义默认语法：

```text
<Identifier> := <Start> <Continue>* (<Medial> <Continue>+)*
```

`<Start>` 是具有 **XID_Start** 属性的字符，`<Continue>` 是具有 **XID_Continue** 属性的字符（[[g:xid-start]]）。`<Medial>` 是只能出现在两个后续字符之间的字符，有的语言用它允许 `foo-bar` 中的连字符。

| 属性 | 大致包含 | 例子 |
|---|---|---|
| XID_Start | 各种文字的字母（通用类别 Lu、Ll、Lt、Lm、Lo）和字母型数字（Nl） | `a`、`Ω`、`变`、`ア` |
| XID_Continue | XID_Start，加上十进制数字（Nd）、组合标记（Mn、Mc）、连接标点（Pc） | `0`、`٣`、U+0301、`·`（U+00B7）、`_` |

名字里的 X 表示它们是 ID_Start、ID_Continue 的修正版，在 NFKC 规范化下封闭。`_`（U+005F）属于连接标点 Pc，所以它是 XID_Continue，却不是 XID_Start。

### C++ 的选择

¶1 接着说明 C++ 对默认语法做了三处调整：

1. 采用 UAX #31 定义的数学兼容记号 profile（Mathematical Compatibility Notation profile）。它把 ID_Compat_Math_Start（如 `∂`、`∇`、`∞`）加入起始字符，把 ID_Compat_Math_Continue（再加上上标、下标数字等，如 `²`、`₁`）加入后续字符，让数学和物理代码能写出 `∂f`、`x₁` 这样的名字。
2. 把 `_` 加入起始字符。C 和 C++ 一直允许 `_x` 这样的名字。
3. Medial 集为空。C++ 的 `-`、`'`、`.` 都是运算符或标点，不能出现在标识符中间。

用 UAX #31 的记法写出来就是：

```text
<Identifier> := <Start> <Continue>*
<Start>      := XID_Start + ID_Compat_Math_Start + U+005F
<Continue>   := <Start> + XID_Continue + ID_Compat_Math_Continue
```

¶2 这条规则在 C++ 文法中对应 [[lex.name]] 的 *identifier*、*identifier-start* 和 *identifier-continue*。

```cpp error
int 1x;          // error: 数字不能开头（数字不是 XID_Start）
int ·y;          // error: U+00B7 不是 XID_Start，只能出现在后面
int 😀;          // error: emoji 既不是 XID_Start 也不是 XID_Continue
int a­b;    // error: U+00AD SOFT HYPHEN 是格式字符，不是 XID_Continue
int x⁠y;    // error: U+2060 WORD JOINER 同理
int ①;           // error: U+2460 CIRCLED DIGIT ONE 不是 XID_Start
```

Clang 23 对这六行都报错。emoji 和 `①` 不能开始一个标识符，被当作非法字符（unexpected character）；`·`、U+00AD 和 U+2060 则报 not allowed at the start of an identifier 或 not allowed in an identifier。

开头的例子中，Clang 23 对 `∂`、`₁`、`²` 给出 `-Wmathematical-notation-identifier-extension` 警告，称其为 Clang 扩展。按当前草案这些字符是标准允许的，诊断的措辞仍停留在只认 XID 属性的旧规则上。

`ﬁ`（U+FB01 连字）和 `fi` 是两个不同的变量。NFKC 规范化会把连字、全角字母这类兼容字符折叠成普通字母，NFC 不会。C++ 选的是 NFC（见下文 R4），兼容字符保持原样，所以它们是不同的标识符。

!!! lawyer "零宽连接符 ZWJ 与 ZWNJ"
    U+200D ZERO WIDTH JOINER 和 U+200C ZERO WIDTH NON-JOINER 在波斯文、印地文等文字中是正确拼写所必需的。C++23 的附录 E 有一节 R1a，说明 C++ 不允许它们出现在标识符中。当前草案已经没有这一节：草案引用的 Unicode 版本是 15.1（[[intro.refs]]），而 Unicode 15.1 把这两个字符加入了 XID_Continue。

    Clang 23 接受 `a<U+200D>b` 这样的标识符，只给出 `-Wunicode-zero-width` 警告。这两个字符不可见，看起来相同的两个标识符可能一个含 ZWJ、一个不含，是两个不同的名字。

## R1b 稳定的标识符（[uaxid.def.stable]）

¶1 R1b 是一项可选保证：一个串一旦成为合法标识符，在 Unicode 以后的所有版本中都仍然是。

¶2 C++ 不作这项保证，只在 UAX #31 保证 XID_Start 和 XID_Continue 属性稳定的范围内成立。Unicode 的稳定性政策保证一个字符一旦具有这两个属性，以后就不会失去，所以只由 XID 字符组成的标识符事实上是稳定的。数学记号 profile 中的字符集合，C++ 没有作出承诺。

## R2 不可变的标识符（[uaxid.immutable]）

¶1 R2 是另一种思路：把标识符允许的码位集合永久固定，以后 Unicode 新增字符也不改变。

¶2 C++ 不采用这种做法。Unicode 加入新文字后，其中的字母可能获得 XID 属性，成为合法的标识符字符。一个今天非良构的标识符，在实现升级 Unicode 数据后可能变成良构的。

C++11 到 C++20 的附录 E 是一张固定的码位区间表，更接近 R2 的思路。表很宽松，许多符号和 emoji 都能用在标识符里，也没有规范化要求。C++23 采纳 [[P1949R7]]，改用基于 XID 属性的语法并要求 NFC，哪些字符算字母从此由 Unicode 维护。[[diff.cpp20.lex]] 记录了这项不兼容的变化。

## R3 Pattern_White_Space 与 Pattern_Syntax（[uaxid.pattern]）

¶1 UAX #31 建议形式语言用两个稳定的字符属性 Pattern_White_Space 和 Pattern_Syntax 来确定哪些字符是空白、哪些有语法意义，以便将来的语言扩展不会和标识符冲突。

¶2 C++ 不声称符合这项要求。C++ 的空白字符、运算符和标点在 [[lex.charset]]、[[lex.pptoken]]、[[lex.operators]] 中逐个列出。

## R4 等价的规范化标识符（[uaxid.eqn]）

```cpp
int Å = 1;      // Å：U+00C5，NFC
int Å = 2;     // error: A + U+030A 组合上圆圈，不是 NFC
int Å = 3;      // error: U+212B ANGSTROM SIGN，NFC 规范化后变成 U+00C5，本身不是 NFC
```

¶1 R4 要求实现说明标识符如何比较、何时视为等价。

¶2 C++ 要求标识符是 **NFC**（规范组合形式，[[g:nfc]]），所以在 NFC 下相同的标识符是等价的。规范性规则在 [[lex.name#1]]：标识符不是 NFC 时程序非良构。

C++ 的做法不是先把标识符规范化再比较，而是要求源代码中的标识符本身已经是 NFC。于是在良构的程序中，两个标识符等价当且仅当码位序列完全相同。编译器只需检查，不需改写，名字修饰和链接也不会因为规范化而产生分歧。

!!! impl "Clang 23 不检查 NFC"
    用 `-std=c++2c -Wall -Wextra -pedantic` 编译上例，Clang 23 不给任何诊断，并把三行当作三个不同的变量，也没有重定义错误。按标准，后两行非良构，需要诊断。

    所以不要依赖编译器发现规范化问题，应当在编辑器或 CI 中把源文件统一规范化为 NFC。

## 其余要求（R5–R8）

[uaxid.eqci] ¶1 C++ 在比较标识符时区分大小写，不做大小写折叠，所以 R5 不适用。`Value` 和 `value` 是两个名字。

[uaxid.filter] ¶1–¶2 如果规范化时排除了某些字符，R6 要求精确说明这些排除。C++ 不作任何排除，所有标识符字符都受 NFC 要求约束。

[uaxid.filterci] ¶1 R7 是 R5 的过滤版本，同样因为区分大小写而不适用。

[uaxid.hashtag] ¶1 R8 针对社交媒体中 `#tag` 这类标识符。C++ 没有 hashtag，所以不适用。

## UAX #31 之外的标识符规则

附录 E 只讨论 UAX #31 的要求，下面几条与标识符有关的规则在它的框架之外：

| 规则 | 出处 | 说明 |
|---|---|---|
| 保留的标识符 | [[lex.name#4]] | 含 `__` 或以 `_` 加大写字母开头的名字保留给实现；全局命名空间中以 `_` 开头的名字也保留 |
| 有特殊含义的标识符 | [[lex.name#2]] | `final`、`override`、`import`、`module`、`pre`、`post` 等 |
| 关键字 | [[lex.key]] | 关键字不能用作标识符 |
| 通用字符名 | [[lex.charset]] | 标识符中的字符可以写成 `\u00E9` 这样的形式，效果与直接写该字符相同 |
| `$` | [[lex.charset]] | 当前草案的基本字符集包含 `$`，但它没有 XID 属性，不能用于标识符 |

```cpp error
int $x = 1;  // error（按标准）：$ 不是标识符字符
```

GCC 和 Clang 都把标识符中的 `$` 作为扩展接受，以兼容一些老系统上的符号名。Clang 23 默认接受上例，`-pedantic` 下给出 `-Wdollar-in-identifier-extension` 警告，加上 `-fno-dollars-in-identifiers` 后报错。

## 思考题

!!! question "1. 一个编译器把所有标识符先规范化为 NFC 再处理，从而把 `Å` 和 `Å` 当作同一个名字，并且不给诊断。它符合标准吗？"

<details markdown="1">
<summary>答案</summary>

不符合。[[lex.name#1]] 规定不是 NFC 的标识符使程序非良构，而非良构的程序要求至少一条诊断（[[intro.compliance]]）。给出一条警告、再按规范化后的名字继续翻译是允许的。R4 的在 NFC 下相同即等价，是从标识符必须已经是 NFC 推出的结论，并不授权实现悄悄规范化。
</details>

!!! question "2. 某个字母在 Unicode 18 中新增并获得 XID_Start 属性。用 Unicode 15.1 数据的编译器拒绝含它的标识符，用 Unicode 18 数据的编译器接受。哪个对？"

<details markdown="1">
<summary>答案</summary>

都可以。草案规范性引用的是 Unicode 15.1（[[intro.refs]]），拒绝符合草案。但 [[intro.compliance#10]] 允许实现使用更新的 Unicode 版本（具体版本由实现定义），所以接受也是符合的。R2 一节说明 C++ 本来就不承诺标识符字符集不变。
</details>

!!! question "3. 为什么 C++ 选择 NFC 而不是 NFKC？"

<details markdown="1">
<summary>答案</summary>

附录没有给出理由。从效果看，NFKC 会折叠兼容字符：`ﬁ` 变成 `fi`，`x²` 变成 `x2`。如果采用 NFKC 等价，`x²` 和 `x2` 就是同一个名字，这和采用数学记号 profile 的目的相冲突。NFC 只合并规范等价的编码，比如 `é` 的预组合写法和 `e` 加组合重音的写法，不改变字符本身的含义。
</details>
