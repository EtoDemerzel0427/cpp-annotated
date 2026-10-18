---
title: 与 UAX #31 的一致性
summary: 附录 E 逐条对照 Unicode 标准附录 31 的要求 R1–R8：C++ 符合 R1（默认标识符，采用数学记号 profile 并额外允许 _ 开头，Medial 集为空）和 R4（以 NFC 判定等价），不作稳定性和不可变性保证，大小写敏感，其余要求不适用。附 Clang 23 实测的合法与非法标识符。
status: done
covers: *
papers: P1949R7
related: lex.name, lex.charset, lex.pptoken, diff.cpp20.lex, gram
tags: 标识符, Unicode, 附录
updated: 2026-10-18
---

附录 E [uaxid] 是**资料性**附录。规范性的标识符规则在 [[lex.name]]：标识符由什么字符组成、必须是 NFC。本附录回答的是另一个问题：用 Unicode 的标准术语来描述，C++ 的标识符规则符合 [[g:uax31]] 的哪些要求、不符合哪些、为什么。

读这一页之前最好先读 [[lex.name]]。本页不重复那里的文法讲解，重点放在 UAX #31 的各项要求本身，以及 C++ 在每一项上的选择。

## UAX #31 是什么

UAX #31（"Unicode Identifier and Pattern Syntax"）是 Unicode 标准的一个附录，面向所有需要"标识符"概念的系统：编程语言、配置格式、域名之外的各种命名。它不强制任何人使用，而是提供：

- 一个**默认的标识符语法**，基于 Unicode 字符数据库（UCD）中的字符属性定义，而不是列举码位；
- 一组**编号的要求**（R1、R1b、R2 … R8）。每条要求描述一种可选的做法。一个系统声称"符合 UAX #31"时，要说明它符合哪几条、以及具体怎样符合（例如用了哪个 profile）。

所以附录 E 的结构就是这份"符合性声明"：每个子条款对应 UAX #31 的一条要求，说明 C++ 是否采纳。

!!! history "C++23 之前：一张码位区间表"
    C++11 到 C++20 的附录 E 是"标识符中允许的通用字符名"：一张码位区间表（源自 C99 和 ISO/IEC TR 10176），外加一张"不能作首字符"的表。这张表很宽松，许多符号、emoji 都能出现在标识符中，且没有规范化要求。C++23 采纳 [[P1949R7]]，改为基于 XID 属性的 UAX #31 语法并要求 NFC，附录 E 也随之改写为现在的对照表。[[diff.cpp20.lex]] 记录了这一不兼容变化。

## 概述：C++ 符合 R1 和 R4（uaxid.general ¶1）

!!! std
    "this document conforms by meeting the requirements R1 "Default Identifiers" and R4 "Equivalent Normalized Identifiers" from UAX #31."

    C++ 符合 UAX #31 的 R1（默认标识符）和 R4（等价的规范化标识符）。

¶1 还说，下面列出的其他要求，要么是 C++ 没有选择的备选做法，要么不适用于 C++。整个附录可以浓缩成一张表：

| 要求 | 内容 | C++ 的立场 | 子条款 |
|---|---|---|---|
| R1 | 默认标识符语法 | **符合**：数学记号 profile + `_` 可作首字符，Medial 为空 | [uaxid.def.general] |
| R1b | 稳定标识符（一旦是标识符，以后永远是） | 不保证，仅限 UAX #31 对 XID 属性本身的稳定性保证 | [uaxid.def.stable] |
| R2 | 不可变标识符（标识符字符集永久固定） | 不保证：Unicode 新增文字后，标识符可用字符随之增加 | [uaxid.immutable] |
| R3 | Pattern_White_Space / Pattern_Syntax | 不声称符合 | [uaxid.pattern] |
| R4 | 规范化等价 | **符合**：要求标识符是 NFC | [uaxid.eqn] |
| R5 | 大小写不敏感等价 | 不适用：C++ 区分大小写 | [uaxid.eqci] |
| R6 | 过滤的规范化标识符 | 没有任何排除 | [uaxid.filter] |
| R7 | 过滤的大小写不敏感标识符 | 不适用 | [uaxid.filterci] |
| R8 | 话题标签（hashtag）标识符 | 不适用：C++ 没有 hashtag | [uaxid.hashtag] |

下面逐条解释。

## R1 默认标识符（uaxid.def.general）

### UAX #31 的默认语法

¶1 UAX #31 的默认语法是：

```text
<Identifier> := <Start> <Continue>* (<Medial> <Continue>+)*
```

- `<Start>`：具有 **XID_Start** 属性的字符；
- `<Continue>`：具有 **XID_Continue** 属性的字符；
- `<Medial>`：只允许出现在两个 continue 字符**之间**的字符。有的语言用它允许连字符（`foo-bar`）或撇号之类，不能出现在开头或结尾，也不能连续出现。

[[g:xid-start]] 这两个属性在 UCD 中有定义，大致是：

| 属性 | 大致包含 | 例子 |
|---|---|---|
| XID_Start | 各种文字的字母（Lu、Ll、Lt、Lm、Lo）、字母型数字（Nl） | `a`、`Ω`、`变`、`ア`、`ℌ` |
| XID_Continue | XID_Start，加上十进制数字（Nd）、组合标记（Mn、Mc）、连接标点（Pc，如 `_`） | `0`、`٣`、U+0301、`·`（U+00B7） |

两个属性的名字里的 **X** 表示它们是对 ID_Start / ID_Continue 的修正版，修正后在 NFKC 规范化下封闭：一个由 XID 字符组成的串，NFKC 规范化后仍然由 XID 字符组成。这对要求 NFKC 的语言有用；C++ 要求的是 NFC，但用 XID 属性也没有坏处。

注意 `_`（U+005F LOW LINE）的通用类别是 Pc（连接标点），它是 XID_Continue 却**不是** XID_Start。

### C++ 的选择

¶1 接着说明 C++ 在默认语法上做的三处调整：

1. **采用数学兼容记号 profile**（Mathematical Compatibility Notation profile）。这是 UAX #31 定义的标准 profile 之一，它把 ID_Compat_Math_Start（如 `∂`、`∇`、`∞`）加入起始字符，把 ID_Compat_Math_Continue（再加上上标、下标数字等，如 `²`、`₁`）加入后续字符。目的是让数学和物理代码能写 `∂x`、`x₁` 这样的名字。
2. **把 `_` 加入起始字符**。UAX #31 默认不允许 `_` 开头，但 C/C++ 一直允许 `_x`、`__func`，必须保留。
3. **Medial 集为空**。C++ 的 `-`、`'`、`.` 都是运算符或标点，不可能用作标识符中间的字符。

于是 C++ 的规则用 UAX #31 的记法写成：

```text
<Identifier> := <Start> <Continue>*
<Start>      := XID_Start + ID_Compat_Math_Start + U+005F
<Continue>   := <Start> + XID_Continue + ID_Compat_Math_Continue
```

¶2 指出，这在 C++ 文法中对应 [[lex.name]] 的 *identifier*、*identifier-start*、*identifier-continue*。其中 *nondigit*（26 个字母的大小写和 `_`）和 *digit* 两个备选项看起来是多余的，因为 ASCII 字母和数字本来就有 XID 属性。它们存在的意义是：没有 `_` 这个备选项，`_` 就不能开头。

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

以上全部良构。实测 Clang 23 都接受，但对 `∂`、`₁`、`²` 给出 "mathematical notation character … in an identifier is a Clang extension" 警告（`-Wmathematical-notation-identifier-extension`）：按当前草案这些字符是标准允许的，Clang 的诊断措辞还停留在只认 XID 的旧规则上。

```cpp error
int 1x;          // error: 数字不能开头（数字不是 XID_Start）
int ·y;          // error: U+00B7 不是 XID_Start，只能出现在后面
int 😀;          // error: emoji 既不是 XID_Start 也不是 XID_Continue
int a­b;    // error: U+00AD SOFT HYPHEN 是格式字符，不是 XID_Continue
int x⁠y;    // error: U+2060 WORD JOINER 同理
int ①;           // error: U+2460 CIRCLED DIGIT ONE 不是 XID_Start
```

Clang 23 对以上六行都报错。其中 emoji 和 `①` 根本不能开始一个标识符，于是被当作非法字符（"unexpected character"）；`·`、U+00AD、U+2060 则报 "not allowed in an identifier" 或 "not allowed at the start of an identifier"。

`ﬁ` 和 `fi` 是两个不同的变量，这一点值得留意。UAX #31 允许语言选择 NFC 或 NFKC 作为等价判定，NFKC 会把兼容字符（连字、全角字母、`ℌ`）折叠成普通字母。C++ 选了 NFC（见下文 R4），兼容字符保持原样，也就各自是不同的标识符。

!!! lawyer "零宽连接符 ZWJ / ZWNJ"
    U+200D ZERO WIDTH JOINER 和 U+200C ZERO WIDTH NON-JOINER 在某些文字（如波斯文、印地文）中是正确拼写所必需的。C++23 的附录 E 有一节 R1a（受限格式字符），说明 C++ 不允许它们出现在标识符中。当前草案的附录 E 已经没有这一节，R1 之后直接是 R1b；草案引用的 Unicode 版本是 15.1（[[intro.refs]]），而 Unicode 15.1 把这两个字符加入了 XID_Continue。

    实测与此一致：Clang 23 接受 `a<U+200D>b` 这样的标识符，只给出 "invisible in some environments" 的 `-Wunicode-zero-width` 警告；而基于 Unicode 15.0 数据的 Python 3.12 认为它不是合法标识符。

    它们看不见，两个外观相同的标识符可能一个含 ZWJ、一个不含，是不同的名字。这是 Clang 默认警告的原因。

## R1b 稳定标识符（uaxid.def.stable）

¶1 R1b 是一个可选保证：一个串一旦成为合法标识符，在 Unicode 以后的所有版本中都仍然是。

¶2 C++ **不作这个保证**，只在 UAX #31 本身保证 XID_Start 和 XID_Continue 属性稳定的范围内成立。

Unicode 的稳定性政策保证，一个字符一旦具有 XID_Start 或 XID_Continue 属性，以后的版本不会把它去掉（必要时通过 Other_ID_Start 等属性"兜住"）。所以对于只由 XID 字符组成的标识符，事实上是稳定的。C++ 不愿额外承诺的，是 XID 之外的部分：比如数学记号 profile 中的字符集合会不会变化，C++ 自己没有对它作承诺。

## R2 不可变标识符（uaxid.immutable）

¶1 R2 是另一种思路：把标识符允许的码位集合**永久固定**下来，以后 Unicode 新增字符也不改变。为了照顾未来，这类方案通常把大片尚未分配的码位也提前允许。

¶2 C++ **不选择**这种保证。随着 Unicode 加入新文字，这些文字里的字母可能获得 XID 属性，从而成为合法的标识符字符。换句话说，一个今天非良构的标识符，在实现升级到更新的 Unicode 数据后可能变为良构。

C++11–C++20 的码位区间表在精神上更接近 R2：它是一张固定的表，与 Unicode 版本无关。C++23 放弃了这种做法，换来的是"哪些字符算字母"由 Unicode 自己维护。

## R3 Pattern_White_Space 与 Pattern_Syntax（uaxid.pattern）

¶1 R3 关心的是形式语言如何描述和实现空白字符与有语法意义的字符：UAX #31 定义了两个稳定的字符属性 Pattern_White_Space 和 Pattern_Syntax，建议语言用它们来确定"哪些字符是空白、哪些可能用作运算符"，以便将来的语言扩展不会和标识符冲突。

¶2 C++ **不声称**符合这一要求。C++ 的空白字符和运算符/标点是在 [[lex.charset]]、[[lex.pptoken]]、[[lex.operators]] 中逐个列出的，没有用这两个属性来定义。

## R4 等价的规范化标识符（uaxid.eqn）

¶1 R4 要求实现说明标识符**如何比较、何时视为等价**。

¶2 C++ 要求标识符是 [[g:nfc]]（规范组合形式），因此在 NFC 下相同的标识符就是等价的。规范性规则在 [[lex.name#1]]：标识符不符合 NFC 时程序**非良构**。

!!! std
    "This document requires that identifiers be in Normalization Form C and therefore identifiers that compare the same under NFC are equivalent."

    C++ 要求标识符是 NFC，因此在 NFC 下相同的标识符是等价的。

注意 C++ 的做法：**不是**"编译器先把标识符规范化为 NFC 再比较"，而是"要求源代码中的标识符本身已经是 NFC，否则非良构"。结果是：在合法的程序中，两个标识符等价当且仅当它们的码位序列完全相同。编译器只需检查，不需改写，名字修饰和链接时也不会因为规范化而出现分歧。R4 的"NFC 下相同即等价"在这里是自然成立的，而不是一个需要编译器实现的比较算法。

```cpp
int Å = 1;      // Å：U+00C5，NFC
int Å = 2;     // error: A + U+030A 组合上圆圈，不是 NFC
int Å = 3;      // error: U+212B ANGSTROM SIGN，NFC 规范化后变成 U+00C5，本身不是 NFC
```

!!! impl "Clang 23 不检查 NFC"
    实测 Clang 23 以 `-std=c++2c -Wall -Wextra -pedantic` 编译上例，**不给出任何诊断**，并且把三行当作三个不同的变量（没有重定义错误）。按标准，后两行非良构，需要诊断。

    这意味着：两个在编辑器里看起来一模一样的 `Å`，可能被编译器当作两个名字。不要依赖编译器发现规范化问题，在编辑器或 CI 中统一把源文件规范化为 NFC。

## R5 等价的大小写不敏感标识符（uaxid.eqci）

¶1 C++ 认为大小写在标识符比较中有意义，不做任何大小写折叠（case folding）。所以这一要求不适用。`Value` 和 `value` 是两个名字（[[lex.name]] ¶1 注 2）。

## R6 过滤的规范化标识符（uaxid.filter）

¶1 如果某些字符被排除在规范化之外，R6 要求精确说明这些排除。

¶2 C++ **不作任何排除**：所有标识符字符都受 NFC 要求约束。

## R7 过滤的大小写不敏感标识符（uaxid.filterci）

¶1 C++ 标识符区分大小写，所以 R7（R5 的过滤版本）不适用。

## R8 话题标签标识符（uaxid.hashtag）

¶1 R8 针对的是社交媒体中 `#tag` 这类标识符的语法。C++ 没有 hashtag，所以不适用。（C++ 中的 `#` 是预处理指令的开头和字符串化运算符，与此无关。）

## C++ 在 UAX #31 之外的部分

附录 E 只讨论 UAX #31 的要求。几项与标识符有关、但不在 UAX #31 框架内的规则：

| 规则 | 出处 | 说明 |
|---|---|---|
| `_` 可作首字符 | [uaxid.def.general]、[[lex.name]] | 上文已述，是对 UAX #31 默认语法的扩充 |
| 保留的标识符 | [[lex.name#4]] | 含 `__`、`_` + 大写字母开头的名字保留给实现；全局命名空间中 `_` 开头的名字也保留 |
| 特殊含义标识符 | [[lex.name#2]] | `final`、`override`、`import`、`module`、`pre`、`post` |
| 关键字 | [[lex.key]] | 关键字不能用作标识符；这与 UAX #31 无关，UAX #31 只管字符层面 |
| `$` | [[lex.charset]] | 当前草案的基本字符集包含 `$`，但它既不是 *nondigit* 也没有 XID 属性，**不能**用于标识符 |
| 通用字符名 | [[lex.charset]] | 标识符中的字符可以写成 `é` 等形式，效果与直接写该字符相同 |

`$` 值得多说一句。GCC 和 Clang 都把标识符中的 `$` 作为扩展接受，这是为了兼容一些老系统（如 VMS）上的符号名。按标准它是非良构的：

```cpp error
int $x = 1;   // error（按标准）：$ 不是标识符字符
```

实测 Clang 23 默认接受，`-pedantic` 下给出 `'$' in identifier` 警告（`-Wdollar-in-identifier-extension`）；加 `-fno-dollars-in-identifiers` 后报错。

## 思考题

!!! question "1. 一个编译器把源文件中所有标识符先规范化为 NFC 再处理，从而把 `Å` 和 `Å` 当作同一个名字，并且不给诊断。它符合标准吗？"

<details markdown="1">
<summary>答案</summary>

不符合。[[lex.name#1]] 规定不是 NFC 的标识符使程序**非良构**，非良构的程序要求至少一条诊断（[[intro.compliance]]）。悄悄规范化而不诊断，违反了诊断要求。给出一条警告然后继续按规范化后的名字处理，则是允许的：诊断之后实现可以照常翻译。附录 E 中 R4 的"NFC 下相同即等价"并不授权实现去规范化，它只是从"标识符必须已经是 NFC"推出的结论。
</details>

!!! question "2. 某个字母在 Unicode 18 中新增并获得 XID_Start 属性。一个用 Unicode 15.1 数据的编译器拒绝含该字母的标识符，用 Unicode 18 数据的编译器接受它。哪个是对的？"

<details markdown="1">
<summary>答案</summary>

按当前草案，规范性引用的是 Unicode 15.1（[[intro.refs]]），所以拒绝是符合草案的。附录 E 的 R2 一节说明 C++ 不承诺标识符字符集不变：随着标准引用的 Unicode 版本更新，新字母可以成为合法的标识符字符。实践中编译器常常直接使用较新的 Unicode 数据，这种接受可以看作扩展。
</details>

!!! question "3. 为什么 C++ 选择 NFC 而不是 NFKC？"

<details markdown="1">
<summary>答案</summary>

附录本身没有给理由。从效果看：NFKC 会把兼容字符折叠（`ﬁ` → `fi`、`ℌ` → `H`、`x²` → `x2`），如果采用 NFKC 等价，`x²` 和 `x2` 就成了同一个名字，这和数学记号 profile 想表达的区别直接冲突。NFC 只合并"规范等价"（同一个字符的不同编码，如 `é` 的两种写法），不改变字符的视觉含义。
</details>

## 小结

!!! summary
    - 附录 E 是资料性的符合性声明：C++ 符合 UAX #31 的 **R1** 和 **R4**。
    - R1：`<Start> <Continue>*`，Start = XID_Start + ID_Compat_Math_Start + `_`，Continue = Start + XID_Continue + ID_Compat_Math_Continue，没有 Medial 字符。
    - R4：标识符必须是 NFC，否则非良构；所以等价就是码位相同。Clang 23 不检查 NFC。
    - 不保证稳定（R1b）和不可变（R2），不声称符合 R3；大小写敏感，R5、R7 不适用；R6 没有排除；R8 不适用。
    - C++23 前的附录 E 是一张码位区间表；当前草案已没有 C++23 附录 E 中的 R1a 一节，ZWJ/ZWNJ 按 Unicode 15.1 属于 XID_Continue。
    - `$` 不是标准的标识符字符，各编译器作为扩展接受。
