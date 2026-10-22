---
title: 字符串字面量
summary: 字符串字面量的类型与长度、原始字符串、相邻字符串的拼接、求值得到的字符串字面量对象（静态存储期、身份未指定、不可修改）及其内容，以及 C++26 只供编译器读取的不求值字符串。
status: done
covers: lex.string.uneval
papers: P2201R1, P2361R6, P0482R6
related: lex.ccon, lex.charset, lex.phases, lex.ext, intro.object, expr.prim.literal, dcl.pre
tags: 字面量, 字符串, 原始字符串, Unicode
updated: 2026-10-19
---

!!! tldr
    - `"abc"` 的类型是 `const char[4]`；数组长度是编码后的 code unit 个数加上结尾的空字符，不是字符个数。
    - 原始字符串 `R"(...)"` 里没有转义，换行和反斜杠都按原样保留；分隔符可以让内容里出现 `)"`。
    - 相邻的字符串字面量会被拼接，最多只能有一种编码前缀；每一段的转义序列各自解释，所以 `"\x41" "BC"` 是 `"ABC"`。
    - 字符串字面量求值得到一个静态存储期的数组对象。两次求值是否得到同一个对象是未指定的，修改它是未定义行为。
    - C++26 的不求值字符串用于 `static_assert` 消息、`[[deprecated]]` 理由、`extern "C"` 等处，不能带前缀，不能含数值转义。

字符串字面量和字符字面量（[[lex.ccon]]）共用编码前缀和转义序列，前缀的含义、转义序列的分类以及 **code unit**（某个字符类型的一个整数值，例如 UTF-8 的一个字节）这些概念，都在那一页讲过。

## 类型与长度（¶1、¶6）

```cpp run title="string-n.cpp" ok
static_assert(sizeof("abc") == 4);         // a、b、c、空字符
static_assert(sizeof(u8"\u00E9") == 3);    // é 在 UTF-8 中占 2 个 code unit
static_assert(sizeof(u"\U0001F600") == 3 * sizeof(char16_t));  // 代理对
static_assert(sizeof(U"\U0001F600") == 2 * sizeof(char32_t));
int main() {}
```

¶1 字符串字面量的类型是 n 个 const 字符组成的数组，字符类型由前缀决定。n 是对字面量求值得到的已编码 code unit 的个数，包括结尾的空字符。

| 前缀 | 种类 | 类型 | 关联编码 |
|---|---|---|---|
| 无 | 普通字符串字面量 | `const char[n]` | 普通字面量编码 |
| `L` | 宽字符串字面量 | `const wchar_t[n]` | 宽字面量编码 |
| `u8` | UTF-8 字符串字面量 | `const char8_t[n]` | UTF-8 |
| `u` | UTF-16 字符串字面量 | `const char16_t[n]` | UTF-16 |
| `U` | UTF-32 字符串字面量 | `const char32_t[n]` | UTF-32 |

¶6 普通字符串字面量和 UTF-8 字符串字面量合称**窄字符串字面量**（narrow string literal）。

数组元素是 const 的。C 中字符串字面量的类型是 `char[n]`，不过修改它同样是未定义行为。C++ 改成 const，是为了不让它被传给一个可能修改实参的重载（[[diff.lex]]）。C++98 为兼容 C 保留了从字符串字面量到 `char*` 的隐式转换，并标为弃用，C++11 删除了它。

```cpp title="string-const.cpp" error
char* p = "abc";          // error（C++11 起）：const char[4] 不能转换为 char*
const char* q = u8"abc";  // error（C++20 起）：u8 字符串是 const char8_t[4]
```

本机 Clang 23 对第一行只给出 `-Wwritable-strings` 警告，然后继续编译。警告也是诊断，所以这符合标准（[[intro.compliance]]）。第二行直接报错。

`u8"..."` 在 C++11 引入时的类型是 `const char[n]`，和普通字符串无法区分。C++20 引入 `char8_t`（[[P0482R6]]），它的类型变为 `const char8_t[n]`，于是 `std::string s = u8"text";` 这类代码不再能编译（[[diff.cpp17.lex]]）。

## 原始字符串（¶2–¶5）

```cpp run title="raw.cpp" ok
#include <cstring>
#include <cassert>
int main() {
  const char* re = R"(\d+\.\d+)";      // 不用把每个 \ 写成 \\
  assert(std::strcmp(re, "\\d+\\.\\d+") == 0);
  const char* s = R"x(a)"b)x";         // 内容含 )"，用分隔符 x
  assert(std::strcmp(s, "a)\"b") == 0);
}
```

¶2 前缀里带 `R` 的是**原始字符串字面量**（raw string literal）。它的形式是 `R"分隔符(内容)分隔符"`，结尾的分隔符必须与开头的相同，分隔符最多 16 个字符，可以为空。

原始字符串的内容按原样保留：

- 没有转义序列，`\` 就是反斜杠；
- 也不识别通用字符名，`\u0041` 就是 6 个字符；
- 可以跨行，源码里的换行就是内容里的换行（¶4 注 2）；
- 翻译阶段 2 的行拼接（行末反斜杠加换行被删除）在原始字符串里被撤销（[[lex.pptoken#5]]），所以行末的 `\` 和换行都会保留。

分隔符的作用是让内容可以包含 `)"`。字符串只在遇到 `)分隔符"` 时才结束，选一个内容里不会出现的分隔符即可。¶3 注 1 的例子 `R"delimiter((a|b))delimiter"` 等价于 `"(a|b)"`。

```cpp run title="raw-newline.cpp" ok
#include <cstring>
#include <cassert>
int main() {
  const char* p = R"(a\
b
c)";
  // 反斜杠和换行都保留：行拼接被撤销
  assert(std::strcmp(p, "a\\\nb\nc") == 0);
}
```

这个例子来自 ¶4 注 2，前提是续行的行首没有空白。原始字符串里的每个字符都计入内容，包括缩进，C++ 没有自动去除公共缩进的机制。

¶5 的例 1 展示了分隔符怎样决定结尾：

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

分隔符是 `a`，所以结束标记是 `)a"`。第二行的 `)` 后面是 `\`，不是 `a"`；第三行的 `a"` 前面隔着反斜杠和换行，行拼接已被撤销，它们是真实的字符，所以也不是 `)a"`。直到最后一行，字符串才结束。

分隔符不能含空格、圆括号、反斜杠、制表符、换页和换行：

```cpp title="raw-bad.cpp" error
const char* a = R"a b(x)a b";   // error: 空格不能作分隔符
const char* b =
  R"12345678901234567(x)12345678901234567";  // error: 超过 16 个字符
```

## 拼接（¶7–¶8）

### 公共编码前缀（¶7）

```cpp run title="concat-prefix.cpp" ok
#include <type_traits>
static_assert(std::is_same_v<decltype(u"a" "b"), const char16_t(&)[3]>);
static_assert(std::is_same_v<decltype("a" u8"b"), const char8_t(&)[3]>);
static_assert(std::is_same_v<decltype(LR"(a)" "b"), const wchar_t(&)[3]>);
int main() {}
```

¶7 一串相邻的字符串字面量中最多只能出现一种编码前缀，它就是这一串的**公共编码前缀**。注 3 说明，是否为原始字符串不影响公共前缀。所以无前缀的字符串可以和任何一种前缀的字符串拼接，结果采用那个前缀；两种不同的前缀拼接则非良构。

```cpp title="concat-conflict.cpp" error
auto c = L"a" U"b";    // error: 两种不同的编码前缀
auto d = u8"a" u"b";   // error
```

拼接发生在翻译阶段 5（[[lex.phases]]）：先确定公共前缀，把每个字符串字面量都看作带有这个前缀，再拼接。所以 `"é" u"x"` 中的 é 按 UTF-16 编码，而不是先按普通字面量编码成字节。

C++11 到 C++20 中，不同前缀的拼接是有条件支持的，主流实现都不支持。C++23 的 [[P2201R1]] 把它改为非良构（[[diff.cpp20.lex]]）。

### 每一段各自解释（¶8）

```cpp run title="concat-structure.cpp" ok
static_assert(sizeof("\xA" "B") == 3);       // '\xA'、'B'、空字符，不是 '\xAB'
static_assert(sizeof(R"(\u00)" "41") == 7);  // \ u 0 0 4 1 和空字符，不是 'A'
int main() {}
```

¶8 拼接时，各个字符串字面量内容的词法结构和分组保持不变。拼接不是把源码文本连起来再重新分析，而是把各段已经分析好的字符和转义序列首尾相接。

所以在 C++23 有 `\x{...}` 之前，`"\x41" "BC"` 是截断十六进制转义的标准写法。用宏也一样：`#define ESC "\x1B"` 之后，`ESC "c"` 是 ESC 加字母 c。

用户定义字符串字面量的拼接见 [[lex.ext#8]]。

## 字符串字面量对象（¶9）

¶9 对字符串字面量求值，得到一个静态存储期（[[basic.stc]]）的**字符串字面量对象**（string literal object）。

这里的措辞区分了源码中的记号和内存中的对象：`"abc"` 本身只是一个记号，每次对它求值，得到一个指代某个数组对象的左值（[[expr.prim.literal]]）。

### 身份未指定

注 4 说明，字符串字面量对象是**可能不唯一的对象**（potentially non-unique object，[[intro.object#9]]）：同一个字符串字面量多次求值，得到同一个对象还是不同的对象，是未指定的。

```cpp run title="string-identity.cpp" unspecified
#include <cstdio>
int main() {
  const char* a = "hello";
  const char* b = "hello";
  std::printf("%d\n", a == b);   // 1 或 0，未指定；本机输出 1
}
```

编译器可以让内容相同的字符串共享存储，也可以让 `"bc"` 是 `"abc"` 的尾部。[[intro.object#10]] 还允许两个不同的可能不唯一的对象有相同的地址，这是不同对象地址不同这条一般规则的例外。

因为身份不确定，指向字符串字面量对象的指针不能作模板实参（[[temp.arg.nontype]]），否则无法判断两个翻译单元中的 `X<"abc">` 是不是同一个特化。C++26 的 `std::define_static_string`（[[meta.define.static]]）返回指向模板参数对象的指针，可以用作模板实参，是替代方案之一。

### 修改是未定义行为

注 5 提醒，试图修改字符串字面量对象，行为未定义。规范依据是修改 const 对象为未定义行为（[[dcl.type.cv]]）。实际上字符串字面量通常放在只读段，修改会让程序崩溃。

```cpp title="string-modify.cpp" ub
int main() {
  char* p = const_cast<char*>("abc");
  p[0] = 'x';   // UB: 修改字符串字面量对象
}
```

本机运行时，程序因 SIGBUS 终止。

## 对象的内容（¶10）

¶10 字符串字面量对象的初始值是各部分对应的 code unit 序列，再加一个结尾的空字符。各部分按下面的规则得到。

### 连续的字符整体编码（¶10.1）

¶10.1 每一段连续的普通字符、简单转义和通用字符名，作为一个字符序列整体用关联编码编码。某个字符在关联编码中无法表示时，程序非良构；注 6 指出，Unicode 编码形式能表示所有字符。

和字符字面量不同，这里不要求每个字符只占一个 code unit。所以 `u8"é"` 合法，`u8'é'` 非良构。

整体编码对**有状态编码**也有意义。有状态编码用特殊的字节序列切换字符集，例如 ISO-2022-JP。标准建议实现让后一段从前一段结束时的状态开始编码；注 7 指出，这样得到的结果可能不同于逐个字符独立编码。

### 每个数值转义是一个 code unit（¶10.2）

¶10.2 每个数值转义贡献恰好一个 code unit。值的规则与字符字面量相同（[[lex.ccon]] ¶3.2）：在元素类型的范围内就取原值；无前缀或 `L` 前缀时，在对应无符号类型的范围内就按模回绕；否则非良构。

借助这条规则，可以在字符串中放入任意的 code unit，包括在 UTF-8、UTF-16 字符串中放入本身不合法的序列：

```cpp run title="numeric-in-string.cpp" ok
static_assert(sizeof(u8"\xFF") == 2);   // 一个值为 0xFF 的 code unit
static_assert(u"\xD800"[0] == 0xD800);  // 孤立的代理；写成 \uD800 则非良构
int main() {}
```

¶10.3 每个条件转义贡献一个由实现定义的 code unit 序列。

## 不求值字符串（[[lex.string.uneval]]）{{c++26}}

有些字符串只给编译器看，从不出现在程序的数据里，例如 `static_assert` 的消息。C++26 把这些位置的文法改成了**不求值字符串**（unevaluated string）。它在文法上就是一个字符串字面量，但规则不同：

```cpp title="uneval.cpp" error
static_assert(true, "\u00e9 \n ok");  // OK：通用字符名和简单转义可以用
static_assert(true, u8"x");           // error: 不能有编码前缀
static_assert(true, "\x41");          // error: 不能有数值转义
[[deprecated(L"w")]] void f();        // error: 不能有编码前缀
extern "\x43" void g();               // error: 即使 \x43 就是 'C'
```

¶1 不求值字符串不能有编码前缀。¶2 其中的通用字符名和简单转义被替换为它们表示的翻译字符集成员（即源码层面的 Unicode 字符）；含有数值转义或条件转义的不求值字符串非良构。¶3 它从不被求值，含义由所在的上下文决定。

使用不求值字符串的位置有：

| 上下文 | 例子 | 规则所在 |
|---|---|---|
| `static_assert` 的消息 | `static_assert(N > 0, "N 必须为正");` | [[dcl.pre]] |
| `[[deprecated]]`、`[[nodiscard]]` 的理由 | `[[deprecated("use g")]]` | [[dcl.attr.deprecated]]、[[dcl.attr.nodiscard]] |
| 删除函数的理由 | `void f() = delete("reason");` | [[dcl.fct.def.delete]] |
| 语言链接 | `extern "C"` | [[dcl.link]] |
| 字面量运算符 | `operator "" _x`（已弃用的写法） | [[over.literal]] |

这样规定的理由是这些字符串不需要编码。消息要按源码中的字符显示给用户，不应先按普通字面量编码（可能是 GBK 或 EBCDIC）转换成字节，再让编译器反过来解释。编码前缀不会改变任何东西，只会让人误以为有某种含义。数值转义如 `"\xC3\xA9"` 只有在某种编码下才对应 é，在不编码的场合不对应任何字符。

C++26 的 `static_assert` 消息还可以是一个常量表达式，只要它有 `.size()` 和 `.data()`（[[dcl.pre#12]]）。只有消息在文法上是一个字符串字面量时，它才按不求值字符串处理。

不求值字符串由 [[P2361R6]] 引入。此前这些位置使用普通的字符串字面量，前缀和数值转义在文法上都允许。本机 Clang 23 在 `-std=c++23` 下对带前缀的消息只给出 `-Winvalid-unevaluated-string` 警告，对数值转义则在各个模式下都报错。

## 常见误解

!!! pitfall "相同的字符串字面量地址相同"
    用 `==` 比较两个字符串字面量，或者拿 `const char*` 作 map 的键，都依赖未指定的行为。实际中编译器通常会合并相同的字符串，但标准不保证。

!!! pitfall "`sizeof` 得到的是字符个数"
    `sizeof(u8"é")` 是 3：两个 code unit 加空字符。数组长度按编码后的 code unit 计数。

## 思考题

!!! question "思考题 1"
    `sizeof(u8"a" "\u00e9" R"(\n)")` 是多少？

<details markdown="1">
<summary>答案</summary>

公共前缀是 `u8`。三段分别贡献：`a` 一个 code unit；é 在 UTF-8 中两个 code unit；原始字符串里的 `\` 和 `n` 是两个字符，两个 code unit。再加空字符，共 1 + 2 + 2 + 1 = 6，类型为 `const char8_t[6]`，`sizeof` 为 6。
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

`1` 或 `0`。同一个字符串字面量的两次求值是否得到同一个对象是未指定的（¶9 注 4）。实际中编译器会输出 `1`，本机 Clang 23 也是如此，但标准不保证。这是未指定行为而不是未定义行为，程序是良构的，只是有两种可能的结果。
</details>
