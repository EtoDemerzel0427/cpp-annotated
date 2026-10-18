---
title: 整数字面量
summary: 二、八、十、十六进制整数字面量，数字分隔符，u/l/ll/z 后缀；类型由"能表示其值的第一个类型"决定——十进制与非十进制的候选列表不同，这是 -2147483648 之谜的根源。
status: draft
papers: P0330R8
related: lex.ppnumber, lex.literal, basic.fundamental, conv.prom, expr.unary.op
tags: 字面量, 整数
updated: 2026-10-17
---

[[lex.icon]] 规定整数字面量的形式、值和**类型**。前两者直观；第三者是本节的精华：字面量的类型不是简单的 `int`，而是一张查找表的结果，并且十进制和非十进制的查找表不同。很多关于有符号/无符号混用的诡异 bug 都源于此。

## 文法

```
integer-literal:
    binary-literal integer-suffix(opt)
    octal-literal integer-suffix(opt)
    decimal-literal integer-suffix(opt)
    hexadecimal-literal integer-suffix(opt)

binary-literal:       0b binary-digit | 0B binary-digit | binary-literal '(opt) binary-digit
octal-literal:        0 | octal-literal '(opt) octal-digit
decimal-literal:      nonzero-digit | decimal-literal '(opt) digit
hexadecimal-literal:  hexadecimal-prefix hexadecimal-digit-sequence
hexadecimal-prefix:   0x | 0X
hexadecimal-digit-sequence:
    hexadecimal-digit | hexadecimal-digit-sequence '(opt) hexadecimal-digit

integer-suffix:
    unsigned-suffix long-suffix(opt)       unsigned-suffix long-long-suffix(opt)
    unsigned-suffix size-suffix(opt)       long-suffix unsigned-suffix(opt)
    long-long-suffix unsigned-suffix(opt)  size-suffix unsigned-suffix(opt)
unsigned-suffix: u U      long-suffix: l L
long-long-suffix: ll LL   size-suffix: z Z
```

文法透露的几个细节：

- **`0` 是八进制字面量**。十进制字面量必须以非零数字开头，所以单独的 `0` 只能匹配 *octal-literal*。（这没有实际后果，零在任何进制下都是零，但这是经典的冷知识。）
- 以 `0` 开头的多位数是八进制：`010 == 8`，`09` 非良构。
- **数字分隔符** `'` 只能出现在**两个数字之间**：不能在开头、末尾、前缀之后紧跟（`0x'1` 非良构）、后缀之前，也不能连续出现。但除此之外不限制位置：`1'0'0` 合法，分组方式随意。
- 后缀：`u`、`l`、`ll`、`z` 可与 `u` 以任意顺序组合，大小写可以混用于 `u` 与 `l`（`1Ul`、`1lU`），但 `ll` 本身必须同为大写或同为小写：`1lL` 非良构。`z` 不能与 `l`/`ll` 组合。

```cpp run title="icon-forms.cpp" ok
static_assert(12 == 014 && 12 == 0XC && 12 == 0b1100);       // ¶2 的例子
static_assert(1048576 == 1'048'576 && 1048576 == 0X100000
           && 1048576 == 0x10'0000 && 1048576 == 0'004'000'000);   // 最后一个是八进制！
static_assert(1'0'0 == 100);                                   // 分组位置任意
static_assert(0 == 00 && 010 == 8);
int main() {}
```

```cpp title="icon-bad.cpp" error
int a = 09;      // error：八进制中没有 9
int b = 0x'1;    // error：' 不能紧跟前缀
int c = 1lL;     // error：ll 必须同大小写
int d = 1zl;     // error：z 不能与 l 组合
int e = 0b;      // error：0b 后至少一个二进制数字
```

## 值（¶1–¶2）

¶1 整数字面量中的数字序列按表 7 的基数 N（二进制 2、八进制 8、十进制 10、十六进制 16）解释为整数，**词法上第一个数字是最高位**。注 1：前缀和分隔用的单引号在确定值时被忽略。

¶2 十六进制数字 `a`–`f`、`A`–`F` 的值为 10–15。

注意值是一个**数学整数**——此时还没有任何类型，也不会"溢出"。类型在 ¶3 中根据这个值来选择。

## 类型（¶3）：查表

¶3 整数字面量的类型是表 8 中、与其后缀对应的列表里**第一个能表示其值的类型**。

| 后缀 | 十进制字面量 | 非十进制字面量（二/八/十六进制） |
|---|---|---|
| 无 | `int`、`long`、`long long` | `int`、`unsigned int`、`long`、`unsigned long`、`long long`、`unsigned long long` |
| `u` | `unsigned int`、`unsigned long`、`unsigned long long` | 同左 |
| `l` | `long`、`long long` | `long`、`unsigned long`、`long long`、`unsigned long long` |
| `u` + `l` | `unsigned long`、`unsigned long long` | 同左 |
| `ll` | `long long` | `long long`、`unsigned long long` |
| `u` + `ll` | `unsigned long long` | 同左 |
| `z` | `std::size_t` 对应的有符号类型 | `std::size_t` 对应的有符号类型、`std::size_t` |
| `u` + `z` | `std::size_t` | 同左 |

最重要的规律：**无 `u` 后缀的十进制字面量永远是有符号类型；非十进制字面量则会在有符号与无符号之间交替**。

为什么这样设计？十进制写法表达的通常是一个**数量**，应当保持有符号；十六进制/八进制/二进制写法表达的通常是一个**位模式**（掩码、地址、标志），`0xFFFFFFFF` 的意图就是"32 个 1"，如果硬塞进 `long` 去保持有符号，反而违背意图，于是允许它落在 `unsigned int` 上。

以 LP64 平台（Linux/macOS 64 位：`int` 32 位，`long` 和 `long long` 64 位）为例：

```cpp run title="icon-types.cpp" ok
#include <type_traits>
#include <cstddef>
template<class T, class U> constexpr bool same = std::is_same_v<T, U>;
static_assert(same<decltype(2147483647), int>);
static_assert(same<decltype(2147483648), long>);           // 十进制：跳过 unsigned
static_assert(same<decltype(0x7FFFFFFF), int>);
static_assert(same<decltype(0x80000000), unsigned>);       // 十六进制：先试 unsigned int
static_assert(same<decltype(0x100000000), long>);
static_assert(same<decltype(0x8000000000000000), unsigned long>);
static_assert(same<decltype(4294967296u), unsigned long>);
static_assert(same<decltype(1z), std::ptrdiff_t>);         // 在这些平台上 ptrdiff_t 是 size_t 的有符号对应类型
static_assert(same<decltype(0xFFFFFFFFFFFFFFFFz), std::size_t>);
int main() {}
```

### `-2147483648` 之谜

负号不是字面量的一部分（[[lex.literal]]）。`-2147483648` 是 `-(2147483648)`：

1. `2147483648` 超出 32 位 `int`；十进制无后缀的下一个候选是 `long`。
2. 在 LP64 上 `long` 是 64 位，于是类型是 `long`，取负后是 `long` 类型的 −2147483648。
3. 在 LLP64（64 位 Windows：`long` 也是 32 位）上它是 `long long`。
4. 在 **C89** 中，十进制无后缀字面量的候选列表是 `int`、`long`、`unsigned long`；在 32 位平台上 `2147483648` 落入 `unsigned long`，取负后是 **2147483648ul**——一个正数！C++98/03 的列表只有 `int`、`long`，超出 `long` 是未定义行为，而当时的编译器普遍沿用 C89 的做法，得到同样的结果。

所以 `<climits>` 的实现几乎都把 `INT_MIN` 写成 `(-2147483647 - 1)`：两个 `int` 字面量的运算，结果是 `int`。

```cpp run title="neg-literal.cpp" ok
#include <climits>
#include <type_traits>
static_assert(!std::is_same_v<decltype(-2147483648), int>);   // 不是 int！
static_assert(std::is_same_v<decltype(INT_MIN), int>);
static_assert(-1 < 2147483648);      // long 比较：true
static_assert(!(-1 < 0x80000000));   // -1 转换为 unsigned int 后是 4294967295：false！
int main() {}
```

最后两行展示了"十进制 vs 十六进制"的真实危害：同一个数值，写法不同，比较结果相反。

[[diff.cpp03.lex]] 记录了 C++11 的这一变化：为了与 C99 兼容，某些大于 `long` 能表示的字面量的类型从无符号整数类型变成了有符号的 `long long`。

### `z` 后缀 {{c++23}}

`z`/`Z` 给出 `std::size_t` 对应的有符号整数类型（实践中就是 `std::ptrdiff_t`），`uz`/`zu` 给出 `std::size_t`（[[P0330R8]]）。动机是循环变量的类型：

```cpp run title="uz.cpp" ok
#include <vector>
int main() {
  std::vector<int> v{1, 2, 3};
  for (auto i = 0uz; i < v.size(); ++i) {}   // i 是 std::size_t，没有符号比较警告
  // for (auto i = 0; i < v.size(); ++i)     // i 是 int，-Wsign-compare 警告
}
```

注意 `std::size_t` 本身是一个库 typedef（[[support.types.layout]]），但词法规则引用了它：字面量的类型依赖于实现选择的 `size_t`。

## 放不下怎么办（¶4）

¶4 除带 *size-suffix* 的字面量外，若字面量的值不能用其列表中的任何类型表示，而某个**扩展整数类型**（[[basic.fundamental]]）可以表示，则它**可以**具有该扩展整数类型。列表全为有符号类型时，该扩展类型是有符号的；全为无符号时是无符号的；有符号无符号都有时，两者皆可。若任何允许的类型都无法表示，程序**非良构**。注 2：带 `z` 后缀的字面量若不能用 `std::size_t` 表示则非良构。

```cpp title="icon-too-big.cpp" error
auto a = 18446744073709551616;    // error：超出所有标准整数类型（假设没有可用的扩展整数类型）
auto b = 9223372036854775808;     // 十进制、无后缀：int/long/long long 都放不下 ⇒ 非良构（或扩展有符号类型）
```

!!! impl "实现现状"
    - 主流实现都**不**把 `__int128` 当作标准意义上的扩展整数类型（否则 `std::intmax_t` 就必须至少 128 位，破坏 ABI），所以 ¶4 的"扩展整数类型"分支实际上从不触发。
    - 对 `9223372036854775808`，Clang 23 给出警告"integer literal is too large to be represented in a signed integer type, interpreting as unsigned"（`-Wimplicitly-unsigned-literal`）并把它当作 `unsigned long long`。按标准它是非良构的；给出警告已经满足"诊断"的要求，之后继续编译属于实现的扩展。GCC 有类似的行为。对 `18446744073709551616`，两者都直接报错。
    - 这也意味着 `-9223372036854775808` 不能写出 `LLONG_MIN`；`<climits>` 用 `(-LLONG_MAX - 1)`。

## 历史与演进

!!! history
    | 版本 | 变化 |
    |---|---|
    | C++98 | 八/十/十六进制；后缀 `u`、`l`；十进制无后缀列表为 `int`、`long`，放不下时为 UB |
    | C++11 | `long long` 与 `ll` 后缀；十进制列表不再包含无符号类型；引入扩展整数类型的规则 |
    | C++14 | 二进制字面量 `0b`（[[N3472]]）；数字分隔符 `'`（[[N3781]]） |
    | C++23 | `z`/`uz` 后缀（[[P0330R8]]） |

    数字分隔符选择 `'` 而不是 `_`（其他语言的常见选择），是因为 `_` 开头的后缀被用户定义字面量占用了：`1_000` 会被解析为字面量 `1` 加后缀 `_000`。代价是 [[diff.cpp11.lex]] 记录的宏实参切分变化。

## 陷阱

!!! pitfall "前导零"
    `int month = 08;` 非良构，`int code = 010;` 是 8。从配置或表格复制数字时尤其要小心。

!!! pitfall "以为十六进制字面量与十进制同类型"
    `0xFFFFFFFF` 是 `unsigned int`，`4294967295` 是 `long`（LP64）或 `long long`（LLP64）。重载 `f(int)`/`f(unsigned)`/`f(long)` 时它们会选中不同的函数；与负数比较时结果相反。

!!! pitfall "`1 << 31`"
    `1` 是 `int`。对 32 位 `int`，`1 << 31` 在 C++11 中是 UB（C++14 起不再是 UB，C++20 起结果明确为 `INT_MIN`，见 [[expr.shift]]）；`1 << 32` 始终是 UB。需要 64 位时写 `1ull << 40` 或 `std::uint64_t{1} << 40`。

## 思考题

!!! question "思考题 1"
    在 LP64 平台上，`decltype(0xFFFFFFFFFFFFFFFF)`、`decltype(18446744073709551615u)`、`decltype(-0x1)` 分别是什么？

<details markdown="1">
<summary>答案</summary>

- `0xFFFFFFFFFFFFFFFF`：非十进制无后缀，`int`、`unsigned int`、`long` 都放不下，`unsigned long`（64 位）恰好放下 ⇒ `unsigned long`。
- `18446744073709551615u`：`u` 后缀，`unsigned int` 放不下，`unsigned long` 放下 ⇒ `unsigned long`。
- `-0x1`：`0x1` 是 `int`，一元负号作用于 `int` ⇒ `int`，值 −1。
</details>

!!! question "思考题 2"
    为什么带 `z` 后缀的字面量不适用 ¶4 的扩展整数类型规则？

<details markdown="1">
<summary>答案</summary>

`z`/`uz` 的全部意义就是"得到 `size_t`（或其有符号对应类型）"。如果值太大时悄悄变成某个更宽的扩展类型，`auto i = ...uz;` 就不再是 `size_t`，违背了这个后缀的初衷。所以标准选择让它直接非良构（注 2）。
</details>

## 小结

!!! summary
    - 四种进制；`0` 开头为八进制（包括 `0` 本身）；`'` 只能在两个数字之间。
    - 值是数学整数；类型取后缀对应列表中第一个能表示该值的类型。
    - 十进制无 `u` 永远有符号；非十进制在有符号/无符号间交替。
    - `-2147483648` 是对 `2147483648` 取负，类型不是 `int`。
    - 放不下：可能是扩展整数类型（实际从不发生），否则非良构；Clang/GCC 对"刚好放进 unsigned long long"的十进制字面量只警告。
    - C++23 `z`/`uz` 给出 `size_t` 系列类型。
