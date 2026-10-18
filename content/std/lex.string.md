---
title: 字符串字面量
summary: 五种编码前缀、原始字符串、相邻字符串的拼接与公共前缀、字符串字面量对象（静态存储期、可能不唯一、不可修改）及其 code unit 序列的初始化规则；以及 C++26 的不求值字符串。
status: draft
covers: lex.string.uneval
papers: P2201R1, P2361R6, P0482R6
related: lex.ccon, lex.charset, lex.phases, lex.ext, intro.object, expr.prim.literal, dcl.pre
tags: 字面量, 字符串, 原始字符串, Unicode
updated: 2026-10-17
---

[[lex.string]] 是字面量各节中最长的一节。它要回答四个问题：

1. 形式：普通字符串与原始字符串是什么样子？（文法、¶2–¶5）
2. 类型：`"abc"` 的类型是什么，`n` 怎么算？（¶1、¶6）
3. 拼接：`"a" u"b"` 是什么？`"\xA" "B"` 呢？（¶7–¶8）
4. 对象：对字符串字面量求值得到什么对象，内容是什么？（¶9–¶10）

最后，[[lex.string.uneval]] 定义了 C++26 的[[g:unevaluated-string|**不求值字符串**]]，即出现在 `static_assert`、`[[deprecated]]`、`extern "C"` 等处、只供编译器读取的字符串。

字符字面量（[[lex.ccon]]）一页中关于编码前缀、转义序列的讨论在这里同样适用，本页不再重复。

## 文法

```
string-literal:
    encoding-prefix(opt) plain-string-literal
    encoding-prefix(opt) R raw-string
plain-string-literal:
    " s-char-sequence(opt) "
s-char:
    basic-s-char | escape-sequence | universal-character-name
basic-s-char:
    翻译字符集中除 "、\、换行 以外的任何成员
raw-string:
    " d-char-sequence(opt) ( r-char-sequence(opt) ) d-char-sequence(opt) "
r-char:
    翻译字符集中的任何成员，除了：) 后跟起始 d-char-sequence 再跟 "
d-char:
    基本字符集中除 空格 ( ) \ 水平制表 垂直制表 换页 换行 以外的任何成员
```

编码前缀与字符字面量相同：无、`L`、`u8`、`u`、`U`。原始字符串在前缀之后加 `R`：`R"..."`、`LR"..."`、`u8R"..."`、`uR"..."`、`UR"..."`。

## ¶1：种类与类型

¶1 字符串字面量的种类、类型和关联字符编码由编码前缀以及 *s-char*/*r-char* 序列决定（表 12），其中 **n 是对该字符串字面量求值所得的已编码 code unit 的个数**（含末尾的空字符）：

| 前缀 | 种类 | 类型 | 关联编码 | 例 |
|---|---|---|---|---|
| 无 | 普通字符串字面量 | `const char[n]` | 普通字面量编码 | `"ordinary"`、`R"(raw)"` |
| `L` | 宽字符串字面量 | `const wchar_t[n]` | 宽字面量编码 | `L"wide"`、`LR"w(raw)w"` |
| `u8` | UTF-8 字符串字面量 | `const char8_t[n]` | UTF-8 | `u8"UTF-8"`、`u8R"x(raw)x"` |
| `u` | UTF-16 字符串字面量 | `const char16_t[n]` | UTF-16 | `u"UTF-16"`、`uR"y(raw)y"` |
| `U` | UTF-32 字符串字面量 | `const char32_t[n]` | UTF-32 | `U"UTF-32"`、`UR"z(raw)z"` |

注意 n 是 code unit 数，而不是字符数：

```cpp run title="string-n.cpp" ok
static_assert(sizeof(u8"\u00E9") == 3);                        // é：2 个 UTF-8 code unit + NUL
static_assert(sizeof(u"\U0001F600") == 3 * sizeof(char16_t));  // 😀：代理对 + NUL
static_assert(sizeof(U"\U0001F600") == 2 * sizeof(char32_t));
int main() {}
```

数组元素是 `const` 的。在 C 中，字符串字面量的类型是 `char[n]`（但修改它仍是 UB）；C++ 从一开始就是 `const char[n]`。为了兼容 C，C++98 保留了一个到 `char*` 的隐式转换并将其弃用，C++11 删除了它（[[diff.lex]]）：

```cpp title="string-const.cpp" error
char* p = "abc";               // error（C++11 起）：const char[4] 不能转换为 char*
const char* q = u8"abc";       // error（C++20 起）：u8 字符串是 const char8_t[4]
```

（Clang 对第一行只给出 `-Wwritable-strings` 警告并继续编译，警告也是诊断，符合标准；对第二行则报错。）

¶6 普通字符串字面量和 UTF-8 字符串字面量合称**窄字符串字面量**（narrow string literal）。

!!! history "u8 字符串的类型变化"
    C++11 引入 `u8"..."` 时，它的类型是 `const char[n]`，与普通字符串无法区分，于是重载和模板都无法对确定是 UTF-8 的数据区别对待。C++20 引入 `char8_t`（[[P0482R6]]），`u8` 字符串的类型变为 `const char8_t[n]`。这使 `std::string s = u8"text";` 之类的代码无法编译（[[diff.cpp17.lex]]）。

## ¶2–¶5：原始字符串

¶2 前缀中带 `R` 的字符串字面量是[[g:raw-string-literal|**原始字符串字面量**]]（raw string literal）。*d-char-sequence* 用作分隔符；*raw-string* 结尾的 *d-char-sequence* 必须与开头的相同。*d-char-sequence* 最多 16 个字符。

原始字符串的设计目标是所见即所得：

- 没有转义序列，`\` 就是 `\`；
- 没有 UCN，`\u0041` 就是 6 个字符（[[lex.universal.char]] 注 1）；
- 可以跨行，换行就是换行；
- 行拼接被撤销（[[lex.pptoken#5]]），行末的 `\` 也是字面的 `\`；
- 只要分隔符选得好，内容可以包含任何字符序列，包括 `"` 和 `)`。

¶3 注 1：`(` 和 `)` 可以出现在原始字符串中，因此 `R"delimiter((a|b))delimiter"` 等价于 `"(a|b)"`。分隔符的作用正是让内容中出现 `)"` 时，字符串仍能正确结束：

```cpp run title="raw.cpp" ok
#include <cstring>
#include <cassert>
int main() {
  const char* m = R"delimiter((a|b))delimiter";
  assert(std::strcmp(m, "(a|b)") == 0);
  const char* s = R"x(a)"b)x";            // 内容含 )"，用分隔符 x 区分
  assert(std::strcmp(s, "a)\"b") == 0);
  const char* r = R"(x = "\"y\"")";       // ¶5 的第二个例子
  assert(std::strcmp(r, "x = \"\\\"y\\\"\"") == 0);
}
```

¶4 注 2：源文件中原始字符串里的换行，在结果中就是换行。假设下面例子中的行首没有空白，断言成立：

```cpp run title="raw-newline.cpp" ok
#include <cstring>
#include <cassert>
int main() {
  const char* p = R"(a\
b
c)";
  assert(std::strcmp(p, "a\\\nb\nc") == 0);   // 反斜杠 + 换行被保留：拼接被撤销
}
```

¶5 的例 1 更难一些：

```cpp run title="raw-tricky.cpp" ok
#include <cstring>
#include <cassert>
int main() {
  const char* q = R"a(
)\
a"
)a";
  assert(std::strcmp(q, "\n)\\\na\"\n") == 0);
}
```

分析如下：分隔符是 `a`，所以结束标记是 `)a"`。内容第二行的 `)\` 后面不是 `a"`；第三行开头的 `a"` 前面也不是 `)`，中间隔着 `\` 和换行，由于拼接已被撤销，它们是真实的字符。所以这两处都不构成结束，直到最后一行的 `)a"` 才结束。

*d-char* 不能包含空格、括号、反斜杠和控制字符：

```cpp title="raw-bad.cpp" error
const char* a = R"a b(x)a b";                          // error：空格不能作 d-char
const char* b = R"12345678901234567(x)12345678901234567";  // error：分隔符超过 16 个字符
```

为什么限制为 16 个字符？这样词法分析器只需一个固定大小的缓冲区来记住分隔符，而 16 个字符已足够构造出不会在内容中出现的分隔符。

## ¶7–¶8：拼接

### ¶7：公共编码前缀

¶7 任何相邻字符串字面量序列中，最多只能有一种编码前缀。如果有，这种前缀就是该序列的**公共编码前缀**。注 3：是否为原始字符串，不影响公共前缀的确定。

于是：

- 无前缀的字符串可以与任何一种前缀的字符串拼接，结果采用那个前缀；
- 两种不同前缀（如 `L"a" U"b"`、`u8"a" u"b"`）的字符串拼接，非良构。

```cpp run title="concat-prefix.cpp" ok
#include <type_traits>
static_assert(std::is_same_v<decltype(u"a" "b"), const char16_t(&)[3]>);   // u"ab"
static_assert(std::is_same_v<decltype("a" u8"b"), const char8_t(&)[3]>);   // u8"ab"
static_assert(std::is_same_v<decltype(LR"(a)" "b"), const wchar_t(&)[3]>); // 原始性不影响
int main() {}
```

```cpp title="concat-conflict.cpp" error
auto c = L"a" U"b";     // error：两个不同的编码前缀
auto d = u8"a" u"b";    // error
```

[[lex.phases]] 的阶段 5 说："每个字符串字面量都被视为具有该公共前缀，然后拼接。"注意顺序是先统一前缀，再编码。所以 `"é" u"x"` 中的 é 按 UTF-16 编码，而不是先按普通字面量编码成字节再拼接。

!!! history
    在 C++11 到 C++20 中，不同前缀的拼接是有条件支持的，行为由实现定义，但没有任何实现支持它。C++23 的 [[P2201R1]] 把它改为非良构（[[diff.cpp20.lex]]）。

### ¶8：拼接保留各自的词法结构

¶8 在阶段 5（[[lex.phases]]），相邻的字符串字面量被拼接，**各个字符串字面量内容的词法结构和分组保持不变**。

```cpp run title="concat-structure.cpp" ok
static_assert(sizeof("\xA" "B") == 3);         // 两个 code unit '\xA'、'B'（+ NUL），不是 '\xAB'
static_assert(sizeof(R"(\u00)" "41") == 7);    // \、u、0、0、4、1（+ NUL），不是 'A'
int main() {}
```

换句话说，拼接不是把源码文本连起来再重新分析，而是把已经分析好的字符和转义序列首尾相接。正因如此，在 C++23 之前，`"\x41" "BC"` 是截断十六进制转义的标准写法。

表 13 列出了合法的拼接：

| 源码 | 含义 | 源码 | 含义 | 源码 | 含义 |
|---|---|---|---|---|---|
| `u"a" u"b"` | `u"ab"` | `U"a" U"b"` | `U"ab"` | `L"a" L"b"` | `L"ab"` |
| `u"a" "b"` | `u"ab"` | `U"a" "b"` | `U"ab"` | `L"a" "b"` | `L"ab"` |
| `"a" u"b"` | `u"ab"` | `"a" U"b"` | `U"ab"` | `"a" L"b"` | `L"ab"` |

用户定义字符串字面量的拼接（`"a"_x "b"`）见 [[lex.ext#8]]。

## ¶9：字符串字面量对象

¶9 对字符串字面量求值，得到一个具有静态存储期（[[basic.stc]]）的[[g:string-literal-object|**字符串字面量对象**]]（string literal object）。

注 4：字符串字面量对象是可能不唯一的对象（potentially non-unique object，[[intro.object#9]]）。同一个字符串字面量多次求值，得到的是同一个对象还是不同对象，是**未指定**的。

注 5：试图修改字符串字面量对象，效果是**未定义**的。

这几句话包含三层意思。

(1) 字符串字面量是一个表达式，求值后才产生对象。当前草案的这一措辞比旧标准的"字符串字面量具有静态存储期"更准确：`"abc"` 本身是源码中的记号，不是对象；每次对它求值，得到一个指代某个对象的左值（[[expr.prim.literal]]）。

(2) 对象的身份是未指定的。内容相同的两个字符串字面量可以共享存储（即编译器的字符串合并），一个字符串甚至可以是另一个的尾部（`"abc"` 与 `"bc"`）；同一个字面量在循环中多次求值，也不保证每次得到同一地址（尽管实践中总是相同）。

```cpp run title="string-identity.cpp" unspecified
#include <cstdio>
int main() {
  const char* a = "hello";
  const char* b = "hello";
  std::printf("%d\n", a == b);   // 1 或 0，未指定；Clang 实测输出 1
}
```

[[intro.object#10]] 进一步规定，两个可能不唯一的对象即使并不相同，也可以有相同的地址（例如 `"x"` 与 initializer_list 的后备数组 `{'x'}`）。这是不同对象地址不同这条一般规则的例外。

(3) 修改是 UB。规范依据是 [[dcl.type.cv]]，即修改 const 对象是 UB；注 5 只是提醒。实践中，字符串字面量放在只读段，修改会导致段错误。

```cpp title="string-modify.cpp" ub
int main() {
  char* p = const_cast<char*>("abc");
  p[0] = 'x';                    // UB：修改字符串字面量对象
}
```

!!! lawyer "字符串字面量不能作为模板实参"
    指向字符串字面量对象（或其子对象）的指针不能作为非类型模板实参（[[temp.arg.nontype]]），因为对象的身份未指定：`T<"abc">` 在两个 TU 中是否是同一个特化，将无法确定。C++20 的类类型非类型模板参数，以及 C++26 的 `std::define_static_string`（[[meta.define.static]]，返回一个模板参数对象，它同样是可能不唯一的对象）提供了替代方案。

## ¶10：对象的内容

¶10 字符串字面量对象用以下 code unit 值序列初始化：字符串字面量中 *s-char* 序列（来自非原始字符串）和 *r-char* 序列（来自原始字符串）所对应的 code unit 值，再加一个终止的 U+0000 空字符。具体按以下规则依次确定。

### ¶10.1　字符：作为一个序列整体编码

每一段连续的 *basic-s-char*、*r-char*、*simple-escape-sequence*、*universal-character-name* 所表示的字符序列，用关联编码编码成 code unit 序列。如果某个字符在关联编码中没有表示，程序非良构。注 6：在任何 Unicode 编码形式中，都不存在没有表示的字符。

对于有状态编码（如 ISO-2022-JP，用转义序列切换字符集），推荐做法（should）是：实现从初始状态开始编码第一段，后续各段从前一段的最终状态开始。注 7：因此编码结果可能与逐字符独立编码的结果不同。

作为一个序列整体编码，这一表述有两个作用：一是有状态编码的状态得以延续；二是与字符字面量（[[lex.ccon#3]]）不同，这里不要求每个字符编码为单个 code unit，所以 `u8"é"` 合法，而 `u8'é'` 非良构。

### ¶10.2　数值转义：恰好一个 code unit

每个数值转义序列（[[lex.ccon]]）**贡献一个 code unit**，其值的规则与字符字面量相同：如果 v 在数组元素类型的范围内，值就是 v；否则，如果前缀缺省或为 `L`，且 v 在对应无符号类型的范围内，则按模 2^N 回绕；否则非良构。对有状态编码，这些序列不应影响编码状态。

借助这条规则，可以在字符串中嵌入任意字节，包括在 UTF-8/UTF-16 字符串中嵌入无效序列：

```cpp run title="numeric-in-string.cpp" ok
static_assert(sizeof(u8"\xFF") == 2);     // 一个值为 0xFF 的 code unit（不是有效的 UTF-8）+ NUL
static_assert(u"\xD800"[0] == 0xD800);    // 孤立的代理 code unit；用 UCN \uD800 写则非良构
int main() {}
```

### ¶10.3　条件转义

每个条件转义序列贡献一个由实现定义的 code unit 序列；对有状态编码，它对编码状态的影响也由实现定义。

## 不求值字符串（[[lex.string.uneval]]）{{c++26}}

```
unevaluated-string:
    string-literal
```

不求值字符串在文法上就是字符串字面量，但它出现在不会被求值、只供编译器读取的位置。使用它的上下文包括：

| 上下文 | 例 | 规则所在 |
|---|---|---|
| `static_assert` 的消息 | `static_assert(N > 0, "N must be positive");` | [[dcl.pre]] |
| `[[deprecated]]`、`[[nodiscard]]` 的原因 | `[[deprecated("use g")]]` | [[dcl.attr.deprecated]]、[[dcl.attr.nodiscard]] |
| 删除函数的原因 | `void f() = delete("reason");` | [[dcl.fct.def.delete]] |
| 语言链接 | `extern "C"` | [[dcl.link]] |
| 字面量运算符 | `operator "" _x`（已弃用形式） | [[over.literal]] |

¶1 不求值字符串不得有编码前缀。

¶2 其中的每个 UCN 和简单转义序列被替换为它所表示的翻译字符集成员。含有数值转义或条件转义的不求值字符串非良构。

¶3 不求值字符串从不被求值，其解释取决于它出现的上下文。

```cpp title="uneval.cpp" error
static_assert(true, "\u00e9 \n ok");   // OK：UCN 与简单转义被替换为字符
static_assert(true, u8"x");            // error：不得有编码前缀
static_assert(true, "\x41");           // error：数值转义
[[deprecated(L"w")]] void f();         // error
extern "\x43" void g();                // error：即使 \x43 恰好是 'C'
```

为什么要单独定义这个概念？

- 编码问题：`static_assert(false, "é")` 中的消息要显示给用户，应当按源码中的字符（翻译字符集，即 Unicode）来解释，而不是先按普通字面量编码（可能是 GBK、EBCDIC 等）编码成字节，再让编译器反向解释。所以在 ¶2 中，不求值字符串只是把转义替换为翻译字符集成员，并不编码。
- 前缀没有意义：`static_assert(false, L"x")` 中的 `L` 不会改变任何东西，却暗示了某种语义。禁止它可以消除困惑。
- 数值转义没有意义：`"\xC3\xA9"` 是两个 code unit 值，只有在某种编码下才是 é；在不进行编码的上下文中，它不对应任何字符。

!!! history
    不求值字符串由 [[P2361R6]] 引入 C++26。在 C++23 及以前，这些位置使用普通的 *string-literal*，前缀和数值转义在技术上都是允许的（各实现的处理不一）。Clang 在 C++23 模式下对带前缀的情况只给出警告（"encoding prefix … has no effect and is incompatible with c++2c"），对数值转义则在所有模式下都报错。

注意，C++26 的 `static_assert` 消息还可以是一个常量表达式（具有 `.size()` 和 `.data()` 的对象，[[dcl.pre#12]]）；只有当消息在文法上匹配 *unevaluated-string* 时，它才是不求值字符串。

## 陷阱

!!! pitfall "`\x` 拼接截断的反方向"
    `"\x41" "BC"` 是 `"ABC"`（各段独立分析）。宏展开也不影响这一点：`#define HEX "\x41"` 之后，`HEX "BC"` 同样是 `"ABC"`；而 `"\x41BC"` 直接非良构。

!!! pitfall "以为字符串字面量地址唯一"
    用 `const char*` 作为 map 的键，或用 `==` 比较字符串字面量，都依赖于未指定的行为。

!!! pitfall "原始字符串中的缩进"
    原始字符串中的每个字符都会计入内容，包括续行的缩进空白。C++ 没有其他一些语言那种去除公共缩进的机制。

## 思考题

!!! question "思考题 1"
    `sizeof(u8"a" "\u00e9" R"(\n)")` 是多少？

<details markdown="1">
<summary>答案</summary>

公共前缀为 `u8`。三段分别是：`a`（1 个 code unit）、`é`（UTF-8 下 2 个 code unit）、原始字符串中的 `\` 和 `n` 两个字符（2 个 code unit）；再加 NUL。共 1 + 2 + 2 + 1 = 6，类型为 `const char8_t[6]`，`sizeof` 为 6。
</details>

!!! question "思考题 2"
    下面的程序可能输出什么？

    ```cpp
    #include <cstdio>
    const char* f() { return "abc"; }
    int main() { std::printf("%d\n", f() == f()); }
    ```

<details markdown="1">
<summary>答案</summary>

`1` 或 `0`。同一个字符串字面量的两次求值是否得到同一对象，是未指定的（¶9 注 4）。实践中所有实现都输出 `1`（字面量对象放在只读段，每次求值得到同一地址），但标准不作保证。由于这是未指定行为而非未定义行为，程序本身是良构的，只是可能有两种结果。
</details>

## 小结

!!! summary
    - 类型为 `const charT[n]`，n 是编码后的 code unit 数加 1；`u8` 字符串自 C++20 起是 `const char8_t[n]`。
    - 原始字符串没有转义、没有 UCN，并撤销行拼接；分隔符至多 16 个字符。
    - 拼接时至多有一种编码前缀（C++23 起冲突即非良构）；各段的词法结构保持不变（`"\xA" "B"` 是两个 code unit）。
    - 求值得到具有静态存储期的字符串字面量对象，它是可能不唯一的对象：身份未指定，修改为 UB。
    - 初始化时，连续字符整体编码（不可表示则非良构）；每个数值转义贡献一个 code unit；条件转义由实现定义。
    - C++26 的不求值字符串不能有前缀，不能有数值或条件转义，只替换 UCN 和简单转义，不进行编码。
