---
title: 字符数组
summary: 用字符串字面量初始化字符数组：哪种数组配哪种字面量、空终止符必须放得下（与 C 不同）、剩余元素清零
status: draft
covers: dcl.init.string
papers: P2513R4
related: dcl.init, dcl.init.aggr, dcl.init.list, lex.string, basic.fundamental, topics/initialization
tags: 初始化, 字符串, C 兼容性
updated: 2026-10-17
---

字符串字面量的类型是 `const char[N]`（[[lex.string]]），而数组一般**不能**用另一个数组初始化（`int a[3] = b;` 非良构）。用字符串字面量初始化字符数组是这条规则的唯一例外，由本节单独规定——它在 [[dcl.init]] ¶15.3 的决策流程中排在类、数组等一般规则之前，在 [[dcl.init.list]] ¶3.3 中也有一个专门入口（`char s[] = {"abc"}`）。

本节只有三段，但包含了 C++ 与 C 最著名的不兼容之一。

## 哪种数组可以用哪种字面量初始化（¶1）

¶1 下列配对是允许的：

| 数组元素类型 | 可用的字面量 | 例子 |
|---|---|---|
| 普通字符类型 `char`、`signed char`、`unsigned char` | 普通字符串字面量 `"…"` | `unsigned char u[] = "abc";` |
| `char8_t` | UTF-8 字面量 `u8"…"` | `char8_t s[] = u8"abc";` |
| `char16_t` | UTF-16 字面量 `u"…"` | |
| `char32_t` | UTF-32 字面量 `U"…"` | |
| `wchar_t` | 宽字面量 `L"…"` | |
| **额外**：`char`、`unsigned char` | UTF-8 字面量 `u8"…"` | `char s[] = u8"abc";` |

以及以上任一字面量**外加一层花括号**：`char s[] = {"abc"};`。

字面量的各个字符（包括末尾隐含的 `'\0'`）依次初始化数组元素，必要时施行**整数转换**（[[conv.integral]]）——例如普通字面量初始化 `unsigned char` 数组时，`char` 值转换为 `unsigned char`。

```cpp run ok
char msg[] = "Syntax error on line %s\n";
static_assert(sizeof msg == 25);            // 24 个可见字符 + '\n' 算 1 个 + 末尾 '\0'

unsigned char bytes[] = "\xff\x01";         // 整数转换：'\xff' → 255
char a[] = "a\0b";                          // 内嵌的 \0 照样复制；sizeof a == 4
static_assert(sizeof a == 4);
char raw[] = R"(a\n)";                      // 原始字面量：a, \, n, \0
static_assert(sizeof raw == 4);
char32_t cat[] = U"ab" U"cd";               // 拼接在翻译阶段完成，这里只是一个字面量
static_assert(sizeof cat / sizeof cat[0] == 5);
int main() { return bytes[0] == 255 ? 0 : 1; }
```

### 不匹配的情形

```cpp
char8_t   e1[] = "abc";     // error: char8_t 数组只能用 u8 字面量
wchar_t   e2[] = "abc";     // error
char16_t  e3[] = U"abc";    // error: UTF-32 字面量不能初始化 char16_t 数组
signed char e4[] = u8"abc"; // error: u8 字面量的"额外"许可只给了 char 和 unsigned char
const char* p = "x";
char      e5[] = p;         // error: 不是字符串字面量，不能用指针（或另一个数组）初始化数组
```

### `u8` 字面量与 `char` 数组：C++20 的兼容性修补

C++20 引入 `char8_t` 后，`u8"…"` 的类型从 `const char[N]` 变成了 `const char8_t[N]`，这破坏了大量 `char s[] = u8"…";` 的现有代码。[[P2513R4]] 作为针对 C++20 的缺陷修复，恢复了"`u8` 字面量可以初始化 `char` 和 `unsigned char` 数组"这一许可（即表中"额外"那一行）。注意它**只**针对数组初始化：`const char* p = u8"abc";` 仍然非良构，因为那需要从 `const char8_t*` 到 `const char*` 的转换。

为什么偏偏是 `char` 和 `unsigned char`，没有 `signed char`？因为 UTF-8 编码单元是 0–255 的值；`unsigned char` 能精确表示它们，`char` 是历史上存放 UTF-8 的惯用类型，而 `signed char` 既不是惯用类型也无法表示大于 127 的编码单元。

## 空终止符必须放得下（¶2）

¶2 初始化器的个数不能多于数组元素的个数。"初始化器"包括末尾隐含的 `'\0'`：

```cpp
char cv[4] = "asdf";        // error: 没有空间放 '\0'
char ok[5] = "asdf";        // OK
```

这是 C++ 与 C 的一处有意的不兼容：C 允许 `char cv[4] = "asdf";`，结果是一个**不以 `'\0'` 结尾**的字符数组（C11 6.7.9/14：如果有空间，或者数组大小未知，才加上终止符）。这在 C 中是有意的特性（例如定长的、非空终止的字段），但更多时候是 bug——之后用 `strlen`/`printf("%s")` 读这个数组就会越界。C++ 选择把它变成编译错误。

!!! tip "需要非空终止的定长字符数组？"
    在 C++ 中用逐字符的花括号列表：`char tag[4] = {'a', 's', 'd', 'f'};`，或者 `std::array<char, 4>`。这样意图是显式的。

## 不足的元素清零（¶3）

¶3 若初始化器少于数组元素，未被显式初始化的元素被**零初始化**：

```cpp run ok
#include <cassert>
int main() {
  char buf[8] = "ab";       // 'a', 'b', '\0', 然后 5 个 '\0'
  for (int i = 2; i < 8; ++i) assert(buf[i] == 0);
}
```

这与聚合初始化"剩余元素从 `{}` 初始化"（[[dcl.init.aggr]] ¶6.2）效果相同。这一保证对**自动存储期**数组同样成立——`char buf[4096] = "";` 会把整个缓冲区清零，有时这是一个意料之外的性能开销（编译器会生成一次 `memset`）。

## 未知边界与多维数组

未知边界的字符数组从字符串字面量取得大小（包括 `'\0'`）——这由 [[dcl.init.aggr]] ¶11 与本节共同决定：字符串字面量提供的"初始化器"个数就是字符个数加一。

多维字符数组可以用一组字符串字面量初始化，每个字面量初始化一行；最外层的未知边界由行数决定：

```cpp run ok
char grid[][4] = { "abc", "def", "ghi" };   // char[3][4]
static_assert(sizeof grid == 12);
char names[2][4] = { "abc", "de" };         // names[1] = 'd','e','\0','\0'
int main() {}
```

这里每个 `"abc"` 是聚合初始化的一个子句，它以 `"` 而不是 `{` 开头，但它**归属**于整行 `char[4]`（[[dcl.init.aggr]] ¶15），于是该行由本节的规则从字符串字面量初始化。

## 边界情况

!!! lawyer "带括号的字符串字面量"
    [[dcl.init]] ¶15.3 的条件是"初始化器**是**一个 *string-literal*"。`char a[] = ("abc");`（带括号的字面量）和 `char a[]("abc");`（圆括号初始化器）严格来说是否满足这一条件，措辞并不完全清楚；若不满足，后者会落入 ¶15.5（数组的圆括号初始化），用 `"abc"` 去拷贝初始化第一个 `char` 元素，从而非良构。截至写作时 Clang 两者都接受、按字符串初始化处理。可移植代码请写 `char a[] = "abc";`。

!!! lawyer "`std::array<char, N>` 与字符串字面量"
    `std::array<char, 4> s = {"abc"};` 被主流实现接受：子句 `"abc"` 被视为归属于内部的 `char[4]` 成员，后者再按本节从字面量初始化。按 [[dcl.init.aggr]] ¶15.3 的字面措辞（"能形成到元素类型的隐式转换序列"），数组类型并没有隐式转换序列可言，所以这一行为在措辞上并不显然；但它是实践中的共识。

## 实现视角

!!! impl
    - 局部的 `char s[] = "hello";` 不是指向只读数据的指针，而是**栈上数组**，编译器会生成从 `.rodata` 中的字面量拷贝（或直接用立即数存储）的代码；所以 `s[0] = 'H';` 合法。对比 `const char* p = "hello";` 只是指向只读存储的指针，`const_cast` 后写入是 UB（[[lex.string]]）。
    - Clang 对 ¶2 违例的诊断为"initializer-string for char array is too long"，并附上数组大小与（含空终止符的）字面量大小。

## 历史与演进

!!! history
    - **C++98**：已经规定"没有空间放空终止符"是非良构的，与 C89/C99 不同。
    - **C++11**：新增 `char16_t`、`char32_t` 及 `u""`、`U""`、`u8""` 字面量；`u8""` 当时的类型是 `const char[N]`。
    - **C++20**：`char8_t`；`u8""` 变成 `const char8_t[N]`；[[P2513R4]]（作为 DR）恢复 `char`/`unsigned char` 数组从 `u8` 字面量初始化。

## 思考题

!!! question "`char s[3] = {'a', 'b', 'c'};` 与 `char s[3] = “abc”;` 哪个合法？`char s[] = {'a', 'b', 'c'};` 的大小是多少？"

<details markdown="1">
<summary>答案</summary>

前者合法：花括号列表恰好 3 个子句，走普通的聚合初始化，**不会**追加 `'\0'`。后者非良构：字符串字面量带有隐含的 `'\0'`，共 4 个初始化器（¶2）。`char s[] = {'a', 'b', 'c'};` 的大小是 3，同样没有空终止符——对它调用 `strlen` 是 UB。
</details>

## 小结

!!! summary
    - 字符串字面量是唯一可以"整体"初始化数组的东西；元素类型必须与字面量的编码前缀匹配（外加 `u8` → `char`/`unsigned char` 的兼容许可）。
    - 隐含的 `'\0'` 必须放得下，否则非良构——这与 C 不同。
    - 多余的元素零初始化；未知边界数组的大小包括 `'\0'`。
