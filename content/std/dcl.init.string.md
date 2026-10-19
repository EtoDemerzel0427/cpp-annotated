---
title: 字符数组
summary: 用字符串字面量初始化字符数组：哪种数组配哪种字面量，末尾的空字符必须放得下（这一点与 C 不同），多出的元素清零。
status: done
covers: dcl.init.string
papers: P2513R4
related: dcl.init, dcl.init.aggr, dcl.init.list, lex.string, basic.fundamental, topics/initialization
tags: 初始化, 字符串, C 兼容性
updated: 2026-10-19
---

!!! tldr
    - 数组一般不能用另一个数组初始化，字符串字面量初始化字符数组是唯一的例外。
    - 元素类型要与字面量的编码前缀对应：`char` 配 `"…"`，`char8_t` 配 `u8"…"`，`wchar_t` 配 `L"…"`，依此类推；`char` 和 `unsigned char` 数组还可以用 `u8"…"`。
    - 字面量末尾隐含的 `'\0'` 也算一个初始化器，放不下就是非良构。C 允许丢掉它，C++ 不允许。
    - 数组比字面量长时，多出的元素清零；未知边界的数组从字面量取得长度，`'\0'` 计算在内。

## 哪种数组配哪种字面量（¶1）

```cpp run ok
char msg[] = "Syntax error on line %s\n";
static_assert(sizeof msg == 25);   // '\n' 是 1 个字符，再加末尾 '\0'

unsigned char bytes[] = "\xff\x01"; // '\xff' 经整数转换变成 255
char a[] = "a\0b";                  // 中间的 \0 照样复制
static_assert(sizeof a == 4);
char32_t cat[] = U"ab" U"cd";       // 拼接在翻译阶段完成，这里只有一个字面量
static_assert(sizeof cat / sizeof cat[0] == 5);
char s[] = {"abc"};                 // 外加一层花括号也可以
int main() { return bytes[0] == 255 ? 0 : 1; }
```

字符串字面量的类型是 `const char[N]` 这样的数组（[[lex.string]]），而 `int a[3] = b;` 这种用数组初始化数组的写法是非良构的。字符数组是唯一的例外，这一节专门规定它。

¶1 下列配对是允许的，字面量外面再加一层花括号也可以：

| 数组元素类型 | 可用的字面量 |
|---|---|
| 普通字符类型 `char`、`signed char`、`unsigned char` | 普通字符串字面量 `"…"` |
| `char8_t` | UTF-8 字面量 `u8"…"` |
| `char16_t` | UTF-16 字面量 `u"…"` |
| `char32_t` | UTF-32 字面量 `U"…"` |
| `wchar_t` | 宽字面量 `L"…"` |
| 另外：`char`、`unsigned char` | UTF-8 字面量 `u8"…"` |

字面量的各个字符，包括末尾隐含的 `'\0'`，依次初始化数组元素；类型不同时做整数转换（[[conv.integral]]），比如普通字面量里的 `char` 值转换成 `unsigned char`。

配对不上就是非良构。字面量之外的东西，包括指向字面量的指针，都不能初始化数组：

```cpp error
char8_t     e1[] = "abc";   // error: char8_t 数组要用 u8 字面量
wchar_t     e2[] = "abc";   // error
char16_t    e3[] = U"abc";  // error: UTF-32 字面量配不上 char16_t
signed char e4[] = u8"abc"; // error: u8 的额外许可没有 signed char
const char* p = "x";
char        e5[] = p;       // error: 不是字符串字面量
```

### `u8` 字面量与 `char` 数组

C++20 引入 `char8_t` 以后，`u8"…"` 的类型从 `const char[N]` 变成了 `const char8_t[N]`，大量 `char s[] = u8"…";` 形式的旧代码因此不能编译。[[P2513R4]] 作为对 C++20 的缺陷修复，恢复了用 `u8` 字面量初始化 `char` 和 `unsigned char` 数组，也就是表中最后一行。

这个许可只针对数组初始化。`const char* p = u8"abc";` 仍然非良构，因为它需要从 `const char8_t*` 到 `const char*` 的转换，而这种转换不存在。

`signed char` 不在许可之内。UTF-8 编码单元的取值是 0–255，`unsigned char` 能精确表示它们，`char` 是历来存放 UTF-8 的类型；`signed char` 两者都不是。

## 末尾的空字符必须放得下（¶2）

<div class="compare" markdown="1">

```cpp error
char cv[4] = "asdf";
// error: 5 个初始化器，
// 只有 4 个元素
```

```cpp ok
char cv[4] = {'a', 's', 'd', 'f'};
// OK: 逐字符列表，
// 不会追加 '\0'
```

</div>

¶2 初始化器不能多于数组元素。这里的初始化器包括末尾隐含的 `'\0'`，所以 `"asdf"` 需要 5 个元素。本机 Clang 23 的诊断写得很清楚：array size is 4 but initializer has size 5 (including the null terminating character)。

这是 C++ 与 C 之间一处有意的不兼容。C 允许 `char cv[4] = "asdf";`，结果是一个不以 `'\0'` 结尾的数组（C11 6.7.9/14：只有放得下或者数组大小未知时，才写入终止符）。C 用它表示定长、不带终止符的字段，但更多时候这是 bug：之后用 `strlen` 或 `printf("%s")` 读这个数组就会越界。C++ 把它变成了编译错误。

确实需要不带终止符的定长字符数组时，像右边那样写逐字符的花括号列表，或者用 `std::array<char, 4>`，意图更明确。

## 多出的元素清零（¶3）

```cpp run ok
#include <cassert>
int main() {
  char buf[8] = "ab";    // 'a', 'b', '\0'，然后 5 个 '\0'
  for (int i = 2; i < 8; ++i) assert(buf[i] == 0);
}
```

¶3 初始化器少于数组元素时，没有被显式初始化的元素一律零初始化（[[dcl.init#5]]）。这和聚合初始化里剩余元素从 `{}` 初始化（[[dcl.init.aggr#6]]）效果相同。

自动存储期的数组也是这样，所以 `char buf[4096] = "";` 会把整个缓冲区清零，编译器通常为此生成一次 `memset`。只想要一个空串而不在乎其余字节时，这是一笔不必要的开销。

## 未知边界与多维数组

未知边界的字符数组从字面量取得长度，`'\0'` 计算在内：`char s[] = "hi";` 的类型是 `char[3]`。依据是 [[dcl.init.aggr#11]]：数组的长度等于显式初始化的元素个数，而字符串字面量提供的初始化器个数是字符数加一。

多维字符数组可以用一组字面量初始化，每个字面量对应一行：

```cpp run ok
char grid[][4] = { "abc", "def", "ghi" };   // char[3][4]
static_assert(sizeof grid == 12);
char names[2][4] = { "abc", "de" };         // names[1] 是 'd','e','\0','\0'
int main() {}
```

每个 `"abc"` 是外层聚合初始化的一个子句。它不以 `{` 开头，但能直接初始化整行 `char[4]`，所以归属于这一行（[[dcl.init.aggr#15]]），这一行再按本节的规则从字面量初始化。

## 边界情况

!!! lawyer "圆括号里的字符串字面量"
    [[dcl.init#15]] 第 3 项的条件是初始化器是一个 *string-literal*。`char a[]("abc");` 的初始化器是带圆括号的表达式列表，`char a[] = ("abc");` 是带括号的字面量，它们是否满足这个条件，措辞并不明确。如果不满足，前者会落到第 5 项（数组的圆括号初始化），用 `"abc"` 去初始化第一个 `char` 元素，从而非良构。本机 Clang 23 两者都接受，并按字符串初始化处理，`sizeof a == 4`。可移植的写法是 `char a[] = "abc";`。

!!! lawyer "std::array 与字符串字面量"
    主流实现都接受 `std::array<char, 4> s = {"abc"};`：子句 `"abc"` 归属于 `std::array` 内部的 `char[4]` 成员，这个成员再按本节从字面量初始化。按 [[dcl.init.aggr#15]] 第 3 项的字面措辞，子句要能隐式转换为元素类型才直接归属于它，而数组类型谈不上隐式转换序列，所以这个结果从措辞上看并不显然，但它是实践中的共识。

!!! impl
    局部的 `char s[] = "hello";` 是栈上的数组，不是指向只读数据的指针。编译器生成从 `.rodata` 拷贝或用立即数写入的代码，所以 `s[0] = 'H';` 合法。与之对比，`const char* p = "hello";` 指向只读存储，`const_cast` 之后写入是 UB（[[lex.string]]）。

## 历史

!!! history
    - C++98 起，放不下末尾空字符就是非良构，与 C 不同。
    - C++11 加入 `char16_t`、`char32_t` 以及 `u""`、`U""`、`u8""` 字面量，当时 `u8""` 的类型是 `const char[N]`。
    - C++20 加入 `char8_t`，`u8""` 改为 `const char8_t[N]`；[[P2513R4]] 作为缺陷修复，恢复了 `char`、`unsigned char` 数组从 `u8` 字面量初始化。

## 思考题

!!! question "思考题"
    `char s[3] = {'a', 'b', 'c'};` 与 `char s[3] = "abc";` 哪个合法？`char t[] = {'a', 'b', 'c'};` 有多大？

<details markdown="1">
<summary>答案</summary>

前者合法：花括号列表恰好 3 个子句，走普通的聚合初始化，不追加 `'\0'`。后者非良构：字面量带着隐含的 `'\0'`，共 4 个初始化器（¶2）。

`t` 的大小是 3，同样没有空字符，对它调用 `strlen` 是 UB。
</details>
