---
title: 字符集与通用字符名
summary: 翻译字符集（源码里的"字符"是什么）、基本字符集与基本字面量字符集、code unit 与字面量编码，以及用 \u、\U、\u{}、\N{} 命名任意字符的通用字符名。
status: draft
covers: lex.charset, lex.universal.char
papers: P2314R4, P2071R2, P2290R3, P2558R2
related: lex.phases, lex.ccon, lex.string, lex.name, basic.fundamental
tags: Unicode, 编码, 字符集
updated: 2026-10-17
---

[[lex.char]] 分两小节：[[lex.charset]] 定义了标准里谈论"字符"时使用的全部词汇；[[lex.universal.char]] 定义了用纯 ASCII 写出任意 Unicode 字符的**通用字符名**（universal-character-name，UCN）。

这一节在 C++23 被彻底重写（[[P2314R4]]）。旧标准里有"基本源字符集"、"执行字符集"、"扩展源字符集"等一堆相互纠缠的概念，源码中的非 ASCII 字符要先在阶段 1 "转换成 UCN"再处理——这些都已不复存在。新模型非常清楚地把问题拆成两半：

1. **源码层面**：源码里的每个字符都是**翻译字符集**的一个元素，而翻译字符集**就是 Unicode**。
2. **运行时层面**：字符字面量和字符串字面量在运行时变成什么数值，由该字面量的**字面量编码**决定。

把这两者分开，是理解 C++ 字符处理的钥匙。

## 翻译字符集（[[lex.charset]] ¶1）

¶1 [[g:translation-character-set|翻译字符集]]（translation character set）由以下元素组成：

- ¶1.1　Unicode 码位空间中每个被分配了码位的抽象字符；
- ¶1.2　每个**未分配**给抽象字符的 Unicode 标量值，各对应一个不同的字符。

注 1 复习了 Unicode 的术语：码位（code point）是 `[0, 10FFFF]` 的整数；代理码位（surrogate）是 `[D800, DFFF]`；**标量值**（scalar value）是非代理的码位。

所以翻译字符集**恰好与 Unicode 标量值一一对应**——包括那些目前还没有分配字符的码位（¶1.2 的作用：让 `\u{E0080}` 这种未分配码位也能被命名，并且 Unicode 未来新增字符时 C++ 的规则无须修改）。代理码位**不是**翻译字符集的元素，所以 `\uD800` 永远非良构（见下文 [[lex.universal.char#2]]）。

阶段 1（[[lex.phases]]）把 UTF-8 输入解码成 Unicode 标量值，再映射为翻译字符集元素；其他编码的输入以实现定义的方式映射。于是从阶段 1 之后，编译器眼里**只有 Unicode**。

## 基本字符集（¶2）

¶2 [[g:basic-character-set|基本字符集]]（basic character set）是翻译字符集的子集，含 **99** 个字符（表 1）：

- 控制字符（4 个）：U+0009 水平制表、U+000B 垂直制表、U+000C 换页、U+000A 换行（new-line）；
- 空格 U+0020；
- 字母 `A`–`Z`、`a`–`z`（52 个）；
- 数字 `0`–`9`（10 个）；
- 标点（32 个）：`!` `"` `#` `$` `%` `&` `'` `(` `)` `*` `+` `,` `-` `.` `/` `:` `;` `<` `=` `>` `?` `@` `[` `\` `]` `^` `_` `` ` `` `{` `|` `}` `~`。

也就是：ASCII 的全部 95 个可打印字符，加上 4 个空白控制字符。

{{c++26}} `$`（U+0024）、`@`（U+0040）、`` ` ``（U+0060）是 C++26 通过 [[P2558R2]] 加入的；C++23 的基本字符集只有 96 个字符。加入它们**并不意味着**它们在语法中有用途（目前没有任何语法用到它们），影响在别处：

- 它们现在是"基本字符"，于是在字面量以外用 UCN 写它们非良构（[[lex.universal.char#1]]），例如标识符里写 `$`；
- 字面量编码必须把它们编码为单个 code unit（¶5）；
- 作为"不能构成其他预处理记号的单个字符"出现时，不再触发 [[lex.pptoken#1]] 中"非基本字符"那条非良构规则（但若残留到阶段 6，仍因不能转换为记号而非良构）。

注 2：表中的 Unicode 短名只是为了标识字符，数值本身在此没有别的含义——换言之，**标准并不要求 `'A'` 的值是 65**。

## 基本字面量字符集（¶3）

¶3 [[g:basic-literal-character-set|基本字面量字符集]]（basic literal character set）= 基本字符集 + 表 2 的 4 个控制字符：U+0000 空字符、U+0007 响铃（alert）、U+0008 退格、U+000D 回车。

为什么要多这 4 个？因为它们可以通过简单转义序列 `\0`（实际是八进制转义）、`\a`、`\b`、`\r` 出现在字面量中，必须保证所有编码都能表示它们。它们不在基本字符集里，是因为它们不应出现在源码的字面量之外（CR 在阶段 1 就被规范化掉了）。

## code unit 与字面量编码（¶4）

¶4 [[g:code-unit|code unit]] 是字符类型（[[basic.fundamental]]）的一个整数值。字符字面量（多字符字面量和不可编码的字符字面量除外）和字符串字面量中的字符，按照**编码前缀**（[[lex.ccon]]、[[lex.string]]）决定的方式被编码为一个或多个 code unit，这称为该字面量的[[g:literal-encoding|字面量编码]]（literal encoding）：

| 前缀 | 字面量编码 | code unit 类型 |
|---|---|---|
| 无 | **普通字面量编码**（ordinary literal encoding） | `char` |
| `L` | **宽字面量编码**（wide literal encoding） | `wchar_t` |
| `u8` | UTF-8 | `char8_t` |
| `u` | UTF-16 | `char16_t` |
| `U` | UTF-32 | `char32_t` |

注意"字面量编码"是**编译期**概念：它决定编译器把 `"é"` 放进目标文件时写入哪些字节。运行时程序处理文本所用的编码是**执行字符集**的事（与 locale 相关，见 [[character.seq]]），两者不必相同。比如 GCC 的 `-fexec-charset=` 和 MSVC 的 `/execution-charset:` 改变的是普通字面量编码，而不是程序运行时的 locale。

## 编码必须满足的约束（¶5）

¶5 是对**普通/宽字面量编码以及执行字符集的 locale 相关编码**提出的全部要求：

1. 基本字面量字符集的每个元素都编码为**单个**、**非负**、互不相同的 code unit；
2. U+0000 编码为 0，**其他任何**翻译字符集元素都不编码为值为 0 的 code unit；
3. 数字 `0`–`9` 的 code unit 值**连续递增**；
4. 除此以外，普通和宽字面量编码是**实现定义**的。

注 3 补充：基本字面量字符集之外的字符可以编码为多个 code unit，而这些 code unit 的值**可以**与某个基本字符的 code unit 相同。这为 Shift-JIS 这类编码留了余地（Shift-JIS 的第二字节可能等于 `\` 的值 0x5C——这就是著名的"表"字问题）。

这几条要求的推论：

```cpp run title="digits.cpp" ok
constexpr int digit_value(char c) { return c - '0'; }   // 可移植：数字保证连续
static_assert(digit_value('7') == 7);
// 但 'z' - 'a' == 25 不被保证：在 EBCDIC 中字母不连续
int main() {}
```

- `c - '0'` 是可移植的；`c - 'a'` 不是（EBCDIC 中 `i` 与 `j` 之间有空洞）。
- 普通字符串字面量的编码结果中不可能出现"意外的"零字节——所以 `strlen` 对任何（不含 `\0` 转义的）普通字符串字面量都按预期工作。
- 基本字面量字符的值是非负的，即使 `char` 是有符号的。所以 `'A'` 永远为正；但 `'é'` 在 `char` 上若能表示（如 Latin-1 编码下）则可能为负。

最后一句：对 UTF-8、UTF-16、UTF-32 字面量，实现**必须**按 Unicode 标准中相应编码形式编码每个字符的标量值。也就是 `u8`/`u`/`U` 字面量的内容是完全可移植的，而无前缀和 `L` 字面量不是。

!!! impl "实现视角"
    | 编译器 | 普通字面量编码（默认） | 宽字面量编码 | `wchar_t` |
    |---|---|---|---|
    | GCC / Clang（Linux、macOS） | UTF-8 | UTF-32 | 32 位 |
    | MSVC | 当前代码页（`/utf-8` 时为 UTF-8） | UTF-16 | 16 位 |

    MSVC 的宽字面量编码是 UTF-16，这意味着 `L'😀'`（需要代理对）无法放进单个 `wchar_t`，按 [[lex.ccon#3]] 是非良构的。

## 通用字符名（[[lex.universal.char]]）

### 文法

```
n-char:            翻译字符集中除 } 和换行外的任何成员
n-char-sequence:   n-char n-char-sequence(opt)
named-universal-character:  \N{ n-char-sequence }
hex-quad:          4 个 hexadecimal-digit
simple-hexadecimal-digit-sequence:  一个或多个 hexadecimal-digit
universal-character-name:
    \u hex-quad
    \U hex-quad hex-quad
    \u{ simple-hexadecimal-digit-sequence }
    named-universal-character
```

四种形式：

| 形式 | 例 | 引入 |
|---|---|---|
| `\uXXXX` | `\u03B1` | C++98 |
| `\UXXXXXXXX` | `\U0001F600` | C++98 |
| `\u{X...}` | `\u{1F600}`、`\u{3b1}` | C++23（[[P2290R3]]） |
| `\N{名字}` | `\N{GREEK SMALL LETTER ALPHA}` | C++23（[[P2071R2]]） |

`\u{...}` 称为**分隔形式**（delimited）：位数不固定，消除了"`\u` 必须恰好 4 位、`\U` 必须恰好 8 位"带来的麻烦。`\N{...}` 则让人可以写出可读的名字。

```cpp run title="ucn.cpp" ok
int \u03B1 = 1;                        // 标识符 α
int \U000003B2 = 2;                    // 标识符 β
int \u{3B3} = 3;                       // 标识符 γ（C++23）
int \N{GREEK SMALL LETTER DELTA} = 4;  // 标识符 δ（C++23）
static_assert(u8"\u{1F600}"[0] == 0xF0);          // 😀 的 UTF-8 首字节
static_assert(sizeof(u"\U0001F600") == 3 * sizeof(char16_t));  // 代理对 + 终止符
int main() { return α + β + γ + δ - 10; }  // UCN 与直接写字符完全等价
```

### 何时识别（回顾阶段 3）

UCN 在阶段 3 识别并替换为对应的翻译字符集元素（[[lex.phases]]），但在字符/字符串字面量的字符序列、原始字符串、头文件名内部除外。字面量里的 UCN 在字面量求值时才处理（[[lex.ccon#3]]、[[lex.string#10]]）。所以 `int \u03B1;` 与 `int α;` 声明的是**同一个**标识符。

### ¶1：字面量外不得命名基本字符或控制字符

¶1 UCN 让人能只用基本字符集命名翻译字符集中的任何元素。如果字符/字符串字面量（含用户定义字面量）的 *c-char-sequence*/*s-char-sequence* **之外**的 UCN 对应一个**控制字符**或**基本字符集中的字符**，程序非良构。

!!! std
    If a *universal-character-name* outside the *c-char-sequence* or *s-char-sequence* of a *character-literal* or *string-literal* [...] corresponds to a control character or to a character in the basic character set, the program is ill-formed.

    字面量外，UCN 不能用来写 ASCII 可打印字符或控制字符。

为什么？若允许 `\u0041` 在字面量外表示 `A`，那 `\u0023define` 是不是预处理指令？`i\u006Et x;` 里的 `i\u006Et` 是不是关键字 `int`？这些问题毫无意义，禁止掉最干净。

```cpp title="ucn-basic.cpp" error
int \u0041 = 1;            // error: U+0041 'A' 是基本字符
int \u0024x = 2;           // error: '$' 自 C++26 起是基本字符
int \u0009t = 3;           // error: 控制字符
const char* p = "\u0041";   // OK：字面量内部可以
```

注 1：原始字符串的 *r-char-sequence* 中形如 UCN 的字符序列**不构成** UCN——`R"(\u0041)"` 是 6 个字符。

### ¶2：数值形式必须是标量值

¶2 `\u`、`\U`、`\u{}` 形式的 UCN 指代"标量值等于其十六进制数字所表示的数"的那个字符；如果该数不是 Unicode 标量值（即是代理码位或大于 `0x10FFFF`），程序非良构。

```cpp title="ucn-range.cpp" error
char32_t a = U'\uD800';       // error: 代理码位不是标量值
char32_t b = U'\U00110000';   // error: 超出 10FFFF
```

这条规则让"用 `😀` 拼一个代理对"在 C++ 中不可能——UTF-16 代理对只能由编译器在编码 `u"..."` 时产生。（想要往 `char16_t` 数组里塞一个孤立代理，只能用数值转义 `u"\xD800"`，那是 code unit 而不是字符，见 [[lex.string#10]]。）

### ¶3：命名形式必须精确匹配

¶3 `\N{...}` 指代 Unicode 标准中名字（第 4.8 节 Name）**等于** *n-char-sequence* 的字符，或别名等于它的字符；否则程序非良构。注 2：别名列于 Unicode 字符数据库的 NameAliases.txt；所有名字和别名都没有首尾空格。

"等于"是逐字符相等：**不**做大小写折叠、不忽略空格或连字符（与 Unicode 的"宽松匹配"规则 UAX44-LM2 不同）。

```cpp run title="named.cpp" ok
static_assert(U'\N{LATIN CAPITAL LETTER A}' == U'A');
static_assert(U'\N{LINE FEED}' == U'\n');  // U+000A 没有正式名字，"LINE FEED" 是别名
static_assert(U'\N{LF}' == U'\n');         // 缩写别名也可以
// U'\N{latin capital letter a}'           // error: 大小写不匹配
// U'\N{LATIN CAPITAL LETTER  A}'          // error: 多了一个空格
int main() {}
```

!!! note "控制字符的名字"
    控制字符（如 U+000A）在 Unicode 中没有"名字"（Name 属性为空），只有别名。所以 `\N{LINE FEED}` 能用完全依赖于"别名也算"这一条。

!!! impl "实现视角"
    支持 `\N{...}` 意味着编译器要内置整个 Unicode 名字表（数万条）。Clang 和 GCC 都把它压缩存储在编译器二进制中。Clang 对拼写错误的名字会给出"is not a valid Unicode character name"的错误，并在可能时提示相近的名字。

## 历史与演进

!!! history
    - **C++98**：引入 `\u`/`\U`。阶段 1 把源码中所有非基本字符**转换为 UCN**，之后统一处理——一个与实际编译器完全不符的模型。C++98/03 在字面量**内部**也不允许 UCN 指代基本字符。
    - **C++11**：允许字面量内部的 UCN 指代基本字符和控制字符（`"A"` 合法），字面量外仍禁止；新增 `u8`/`u`/`U` 前缀。
    - **C++23**：[[P2314R4]] 重写字符集模型，引入"翻译字符集 = Unicode"与"字面量编码"；[[P2071R2]] 引入 `\N{}`；[[P2290R3]] 引入 `\u{}`（以及 `\x{}`、`\o{}`，见 [[lex.ccon]]）；[[P2295R6]] 要求支持 UTF-8 源文件。
    - **C++26**：[[P2558R2]] 把 `$`、`@`、`` ` `` 加入基本字符集（96 → 99）；[[P2621R2]] 使"行拼接形成 UCN"合法（此前为 UB）。

## 陷阱

!!! pitfall "以为字面量编码就是源文件编码"
    源文件是 GBK 编码、普通字面量编码是 UTF-8？完全可能：阶段 1 把 GBK 解码成 Unicode，求值字面量时再编码成 UTF-8。反之，源文件是 UTF-8 而 MSVC 按 GBK 代码页读取，才会出现乱码——问题出在阶段 1 的输入解码，而不是字面量编码。

!!! pitfall "用 UCN 绕过关键字或预处理"
    `\u0069f`（试图写 `if`）在字面量外直接非良构，而不是一个与 `if` 不同的标识符。

!!! pitfall "以为 `'A' == 65` 是标准保证"
    标准只保证数字连续、空字符为 0。`'A' == 65` 在 EBCDIC 实现（如 z/OS 上的 IBM 编译器）上不成立。`u8'A'`、`u'A'`、`U'A'` 的值才保证是 0x41。

## 思考题

!!! question "思考题 1"
    下面每一行（各自独立地放在命名空间作用域）是否良构？

    ```cpp
    int \u00C0 = 1;          // (a)
    int \u0040x = 2;         // (b)
    const char* s = "\u0040"; // (c)
    int \u{1F600} = 3;       // (d)
    auto r = R"(\u004)";     // (e)
    ```

<details markdown="1">
<summary>答案</summary>

- (a) 良构：U+00C0 `À` 不是基本字符，具有 XID_Start 属性，是合法的标识符首字符（且是 NFC）。
- (b) 非良构：`@` 自 C++26 起属于基本字符集，字面量外的 UCN 不得指代它。C++23 中它也非良构，但理由不同：`@` 不是基本字符，UCN 本身合法，但 `@` 没有 XID_Start 属性，只能成为"单个非基本字符"预处理记号，触发 [[lex.pptoken#1]]。
- (c) 良构：字面量内部允许 UCN 指代基本字符。
- (d) 非良构：😀 没有 XID_Start 属性，不能出现在标识符中。
- (e) 良构：原始字符串里没有 UCN，`\u004` 只是 5 个普通字符，不会因为"不完整的 UCN"报错。
</details>

!!! question "思考题 2"
    为什么 [[lex.universal.char#1]] 的禁止只针对"基本字符集和控制字符"，而不是"所有 ASCII 字符"？

<details markdown="1">
<summary>答案</summary>

因为这条规则要防的是"用 UCN 伪装成有语法意义的字符"：基本字符集正是 C++ 语法所使用的全部字符（控制字符则可能被当作空白）。基本字符集以外的字符在语法上本来就没有特殊含义，用 UCN 写它们不会改变任何记号的划分，因此无须禁止——它们是否能用在标识符中，交给 [[lex.name]] 的 XID 属性规则判断即可。
</details>

## 小结

!!! summary
    - 翻译字符集 = 所有 Unicode 标量值；源码从阶段 1 起只有 Unicode。
    - 基本字符集 99 个字符（C++26 加入 `$`、`@`、`` ` ``）；基本字面量字符集再加 NUL、BEL、BS、CR。
    - 字面量编码由前缀决定；`u8`/`u`/`U` 的编码固定为 UTF-x，无前缀和 `L` 由实现定义，但须满足"基本字符单 code unit 且非负、NUL 为 0、数字连续"。
    - UCN：`\uXXXX`、`\UXXXXXXXX`、`\u{...}`、`\N{...}`；字面量外不得指代基本字符或控制字符；数值必须是标量值；名字必须精确匹配名字或别名。
