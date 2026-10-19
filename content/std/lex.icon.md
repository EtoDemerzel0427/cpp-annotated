---
title: 整数字面量
summary: 整数字面量的四种进制、数字分隔符和 u/l/ll/z 后缀，以及它的类型怎样决定：取候选列表中第一个放得下其值的类型，而十进制与非十进制的候选列表不同。
status: done
papers: P0330R8, N3472, N3781
related: lex.literal, lex.ppnumber, basic.fundamental, conv.prom, expr.shift
tags: 字面量, 整数
updated: 2026-10-19
---

!!! tldr
    - 整数字面量有二、八、十、十六进制四种写法；以 `0` 开头的多位数是八进制，所以 `010 == 8`，`09` 非良构。
    - 字面量的类型是后缀对应的候选列表里第一个能表示其值的类型。
    - 不带 `u` 的十进制字面量总是有符号类型；十六进制、八进制、二进制字面量的候选在有符号与无符号之间交替，所以 `0x80000000` 是 `unsigned int`。
    - `-2147483648` 是对 `2147483648` 取负，类型不是 `int`，所以 `INT_MIN` 要写成 `(-2147483647 - 1)`。
    - C++23 的 `uz` 后缀给出 `std::size_t`，`z` 给出它对应的有符号类型。

## 四种写法

```cpp run title="icon-forms.cpp" ok
static_assert(12 == 014 && 12 == 0XC && 12 == 0b1100);
static_assert(1048576 == 1'048'576 && 1048576 == 0x10'0000
           && 1048576 == 0'004'000'000);   // 最后一个是八进制
static_assert(1'0'0 == 100);               // 分组方式随意
static_assert(0 == 00 && 010 == 8);
int main() {}
```

前缀决定进制：`0b` 或 `0B` 是二进制，`0x` 或 `0X` 是十六进制，以 `0` 开头的是八进制，以非零数字开头的是十进制。因为十进制字面量必须以非零数字开头，单独的 `0` 在文法上其实是八进制字面量，不过这没有任何实际影响。

数字之间可以插入单引号 `'` 作为**数字分隔符**，位置和分组方式都不受限制，但它只能出现在两个数字之间。

¶1 字面量的值按进制把数字序列解释为一个整数，词法上的第一个数字是最高位；前缀和分隔符不影响值。¶2 十六进制数字 `a`–`f`（或 `A`–`F`）表示 10 到 15。这时得到的是一个数学意义上的整数，还没有类型，也谈不上溢出。

```cpp title="icon-bad.cpp" error
int a = 09;      // error: 八进制中没有 9
int b = 0x'1;    // error: ' 不能紧跟前缀
int c = 0b;      // error: 0b 后至少要有一个二进制数字
int d = 1lL;     // error: ll 的两个字母必须同为大写或同为小写
int e = 1zl;     // error: z 不能和 l 组合
```

后缀有四种字母：`u` 表示无符号，`l` 表示 long，`ll` 表示 long long，`z` 表示 size_t 一族。`u` 可以与另外三种之一以任意顺序组合，大小写可以混用（`1Ul`、`1lU` 都合法），但 `ll` 的两个字母必须同为大写或同为小写。

## 字面量的类型（¶3）

¶3 整数字面量的类型，是下表中与其后缀对应的列表里第一个能表示其值的类型。

| 后缀 | 十进制字面量 | 二、八、十六进制字面量 |
|---|---|---|
| 无 | `int`、`long`、`long long` | `int`、`unsigned int`、`long`、`unsigned long`、`long long`、`unsigned long long` |
| `u` | `unsigned int`、`unsigned long`、`unsigned long long` | 同左 |
| `l` | `long`、`long long` | `long`、`unsigned long`、`long long`、`unsigned long long` |
| `u` + `l` | `unsigned long`、`unsigned long long` | 同左 |
| `ll` | `long long` | `long long`、`unsigned long long` |
| `u` + `ll` | `unsigned long long` | 同左 |
| `z` | `std::size_t` 对应的有符号类型 | `std::size_t` 对应的有符号类型、`std::size_t` |
| `u` + `z` | `std::size_t` | 同左 |

两列的差别是：不带 `u` 的十进制字面量的候选全是有符号类型，非十进制字面量的候选则有符号、无符号交替出现。

这样设计是因为两种写法的用途不同。十进制通常写的是数量，应当保持有符号。十六进制、八进制和二进制通常写的是位模式，例如掩码和标志。`0xFFFFFFFF` 的意图是 32 个 1，让它成为 `unsigned int` 正好符合这个意图；硬要保持有符号而把它放进 `long`，反而不合适。

下面的例子假设 LP64 平台（64 位 Linux 和 macOS：`int` 32 位，`long` 和 `long long` 都是 64 位）：

```cpp run title="icon-types.cpp" ok
#include <type_traits>
#include <cstddef>
template<class T, class U>
constexpr bool same = std::is_same_v<T, U>;
static_assert(same<decltype(2147483647), int>);
static_assert(same<decltype(2147483648), long>);       // 十进制：不试 unsigned
static_assert(same<decltype(0x7FFFFFFF), int>);
static_assert(same<decltype(0x80000000), unsigned>);   // 十六进制：先试 unsigned int
static_assert(same<decltype(0x100000000), long>);
static_assert(same<decltype(0x8000000000000000), unsigned long>);
static_assert(same<decltype(4294967296u), unsigned long>);
int main() {}
```

同一个数值换一种写法，类型就可能不同，比较的结果也会跟着变：

```cpp run title="sign-flip.cpp" ok
static_assert(-1 < 2147483648);      // long 之间比较：true
static_assert(!(-1 < 0x80000000));   // -1 转成 unsigned int 后是 4294967295：false
int main() {}
```

### 为什么 `-2147483648` 不是 `int`

字面量里没有负号（[[lex.literal]]），`-2147483648` 是对字面量 `2147483648` 取负。

1. `2147483648` 超出了 32 位 `int` 的范围，十进制无后缀的下一个候选是 `long`。
2. 在 LP64 平台上 `long` 是 64 位，所以字面量是 `long`，取负后得到 `long` 类型的 −2147483648。在 64 位 Windows 上 `long` 只有 32 位，结果是 `long long`。
3. C89 的十进制候选列表是 `int`、`long`、`unsigned long`。在 `long` 为 32 位的平台上，`2147483648` 会落进 `unsigned long`，取负后仍是正数 2147483648。

所以 `<climits>` 一般把 `INT_MIN` 定义成 `(-2147483647 - 1)`，两个 `int` 相减，结果是 `int`。

```cpp run title="neg-literal.cpp" ok
#include <climits>
#include <type_traits>
static_assert(!std::is_same_v<decltype(-2147483648), int>);
static_assert(std::is_same_v<decltype(INT_MIN), int>);
int main() {}
```

C++98 的十进制候选列表只有 `int` 和 `long`，超出 `long` 时行为未定义。C++11 为了与 C99 兼容加入了 `long long`，列表变成 `int`、`long`、`long long`。[[diff.cpp03.lex]] 记录了这个变化的后果：某些超出 `long` 的字面量，类型可能从无符号整数类型变成 `long long`。

### `z` 后缀 {{c++23}}

`uz`（或 `zu`）后缀给出 `std::size_t`，`z` 给出 `std::size_t` 对应的有符号整数类型，在主流平台上就是 `std::ptrdiff_t`（[[P0330R8]]）。它解决的是循环变量的类型问题：

```cpp run title="uz.cpp" ok
#include <vector>
int main() {
  std::vector<int> v{1, 2, 3};
  for (auto i = 0uz; i < v.size(); ++i) {}  // i 是 std::size_t
  // auto i = 0 会让 i 成为 int，
  // 与 v.size() 比较时触发 -Wsign-compare
}
```

`std::size_t` 本身是标准库中的类型别名（[[support.types.layout]]），这里词法规则直接引用了它，所以这类字面量的具体类型取决于实现选择的 `size_t`。

## 放不下的字面量（¶4）

¶4 如果字面量的值超出了候选列表里所有类型的范围，而某个**扩展整数类型**（实现自行提供的额外整数类型，见 [[basic.fundamental]]）能表示它，字面量可以具有那个扩展整数类型。列表全是有符号类型时，这个扩展类型也是有符号的；全是无符号类型时，它是无符号的；两者都有时可以是任一种。带 `z` 后缀的字面量不适用这条规则。

如果连扩展整数类型也放不下，程序非良构。注 2 特别指出，带 `z` 后缀的字面量放不进 `std::size_t` 时非良构。

```cpp title="icon-too-big.cpp" error
auto a = 18446744073709551616;  // error: 超出 64 位
auto b = 9223372036854775808;   // 十进制无后缀，long long 放不下：非良构
```

!!! impl "实现现状"
    主流实现都没有把 `__int128` 作为标准意义上的扩展整数类型，否则 `std::intmax_t` 就得扩到 128 位，破坏现有 ABI。所以 ¶4 的扩展整数类型分支实际上不会出现。

    对 `a`，本机 Clang 23 报错 "integer literal is too large to be represented in any integer type"。对 `b`，它只给出 `-Wimplicitly-unsigned-literal` 警告，把字面量当作 `unsigned long long` 继续编译。按标准 `b` 非良构，但警告已经满足了诊断要求，之后继续编译属于扩展（[[intro.compliance]]）。

    同样的原因，`LLONG_MIN` 不能写成 `-9223372036854775808`，`<climits>` 用的是 `(-LLONG_MAX - 1)`。

## 历史与演进

!!! history
    | 版本 | 变化 |
    |---|---|
    | C++98 | 八、十、十六进制；后缀 `u`、`l`；十进制无后缀的值超出 `long` 时行为未定义 |
    | C++11 | `long long` 与 `ll` 后缀；十进制无后缀列表只含有符号类型；扩展整数类型规则 |
    | C++14 | 二进制字面量 `0b`（[[N3472]]）；数字分隔符 `'`（[[N3781]]） |
    | C++23 | `z`、`uz` 后缀（[[P0330R8]]） |

    数字分隔符没有采用其他语言常用的 `_`，因为以 `_` 开头的后缀已经属于用户定义字面量：`1_000` 会被解析成字面量 `1` 加后缀 `_000`。选 `'` 的代价是宏实参的切分在少数情况下会变，[[diff.cpp11.lex]] 给了一个例子。

## 常见误解

!!! pitfall "前导零只是格式"
    `int month = 08;` 非良构，`int code = 010;` 的值是 8。从表格或配置文件里复制数字时要特别注意。

!!! pitfall "十六进制和十进制写法类型相同"
    `0xFFFFFFFF` 是 `unsigned int`，`4294967295` 在 LP64 上是 `long`。如果有 `f(int)`、`f(unsigned)`、`f(long)` 三个重载，它们会选中不同的函数，与负数比较的结果也相反。

!!! pitfall "`1 << 40` 能得到 2⁴⁰"
    `1` 是 `int`，移位的位数不小于 `int` 的宽度时行为未定义（[[expr.shift]]）。需要 64 位结果时写 `1ull << 40` 或 `std::uint64_t{1} << 40`。

## 思考题

!!! question "思考题 1"
    在 LP64 平台上，`0xFFFFFFFFFFFFFFFF`、`18446744073709551615u`、`-0x1` 的类型分别是什么？

<details markdown="1">
<summary>答案</summary>

- `0xFFFFFFFFFFFFFFFF`：非十进制无后缀，`int`、`unsigned int`、`long` 都放不下，`unsigned long` 正好放下，所以是 `unsigned long`。
- `18446744073709551615u`：`u` 后缀，`unsigned int` 放不下，`unsigned long` 放下，所以是 `unsigned long`。
- `-0x1`：`0x1` 是 `int`，取负后仍是 `int`，值为 −1。
</details>

!!! question "思考题 2"
    为什么带 `z` 后缀的字面量不适用 ¶4 的扩展整数类型规则？

<details markdown="1">
<summary>答案</summary>

`z` 和 `uz` 的用处就是得到 `size_t` 或它的有符号对应类型。如果值太大时悄悄换成更宽的扩展类型，`auto i = ...uz;` 就不再是 `size_t`，后缀失去了意义。所以标准让它直接非良构（注 2）。
</details>
