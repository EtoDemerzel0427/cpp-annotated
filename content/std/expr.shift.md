---
title: 移位运算符
summary: << 和 >> 的两个操作数各自做整数提升，结果类型取左操作数；移位计数为负或不小于位宽是未定义行为；C++20 起左移按模 2^N 定义，右移向负无穷舍入；C++17 起左操作数先求值。
status: done
papers: P0907R4, P1236R1, P0145R3
related: basic.fundamental, conv.prom, expr.mul, expr.arith.conv, over.match.oper, intro.execution
tags: 位运算, 整数, UB, 二进制补码
updated: 2026-10-19
---

!!! tldr
    - `<<` 和 `>>` 的两个操作数各自做整数提升，不做常用算术转换；结果类型就是提升后的左操作数类型，所以 `1 << 40LL` 仍是 `int`。
    - 移位计数为负，或不小于左操作数的位宽，是未定义行为。想要 64 位掩码要写 `1LL << n` 或 `std::uint64_t{1} << n`。
    - C++20 起，只要计数合法，左移总有定义：结果是与 E1×2<sup>E2</sup> 模 2<sup>N</sup> 同余的值，负数左移不再是 UB。
    - 右移向负无穷舍入，有符号数做算术右移，所以 `-7 >> 1 == -4`，而 `-7 / 2 == -3`。
    - C++17 起左操作数先于右操作数求值，`std::cout << f() << g()` 先调用 `f`。

## 结果类型取左操作数（¶1）

```cpp run title="shift-types.cpp" ok
#include <type_traits>

static_assert(std::is_same_v<decltype(1 << 2LL), int>);      // 右操作数不影响结果类型
static_assert(std::is_same_v<decltype(char(1) << 2), int>);  // char 提升为 int
static_assert(std::is_same_v<decltype(1u << 2), unsigned>);
static_assert(std::is_same_v<decltype(1LL << 2), long long>);
static_assert((char(1) << 20) == (1 << 20));                 // 先提升再移位

int main() {}
```

¶1 `<<` 和 `>>` 从左往右结合。操作数必须是整型或无作用域枚举类型的 prvalue，两边各自做整数提升（[[conv.prom]]），也就是把比 `int` 窄的类型变成 `int`。结果类型是提升后的左操作数的类型。

这与 `+`、`*` 不同。那些运算符做常用算术转换（[[expr.arith.conv]]），把两边统一成一个公共类型。移位计数只是一个距离，没有理由让 `1 << 3LL` 变成 `long long`。

### 计数越界是 UB

!!! std
    The behavior is undefined if the right operand is negative, or greater than or equal to the width of the promoted left operand.

右操作数为负，或者大于等于提升后左操作数的位宽，行为未定义。**位宽**（width）是值表示的位数，不含填充位（[[basic.fundamental]]），32 位 `int` 的位宽是 32。

<div class="compare" markdown="1">

```cpp ok
static_assert((1LL << 32)
              == 4294967296LL);
static_assert((1u << 31)
              == 2147483648u);
```

```cpp error
constexpr long long c = 1 << 32;
// error: 1 是 int，计数 32 越界；
// 结果赋给 long long 无济于事
```

</div>

右边是最常见的错误：想构造一个 64 位掩码，却写了 `1 << n`。左操作数 `1` 的类型是 `int`，结果类型也就是 `int`，赋值给什么类型都改变不了这一点。下面几种写法同样是 UB，在常量表达式中会被拒绝：

```cpp title="shift-count-ub.cpp" error
constexpr int a = 1 << 32;      // error: 计数等于 int 的位宽
constexpr int b = 1 << 40LL;    // error: 结果仍是 int，40 ≥ 32
constexpr int d = 1 << -1;      // error: 负计数
```

!!! impl "为什么不规定一个确定的结果"
    不同硬件对过大的计数处理不同，标准无论规定哪种结果，其余平台都要额外付出代价：

    - x86-64 和 AArch64 的变量移位指令把计数对位宽取模，所以运行期 `1 << 32` 得到 1。本机（arm64）实测如此。
    - 32 位 ARM 的寄存器移位取计数的低 8 位，计数 32 把值全部移出，得到 0。
    - SSE2 的 `psllq` 等 SIMD 指令在计数过大时得到 0。

    于是同一台机器上，同一行 `x << n` 的标量版本和向量化版本甚至可能结果不同。定为 UB 之后，编译器可以直接发出一条移位指令。`-fsanitize=shift-exponent`（包含在 `-fsanitize=undefined` 中）会在运行期报告 "shift exponent 32 is too large for 32-bit type 'int'"。

## 左移的值（¶2）

```cpp run title="shift-left-cxx20.cpp" ok
#include <climits>

static_assert((-1 << 31) == INT_MIN);    // C++17 中是 UB
static_assert((3 << 31) == INT_MIN);     // C++17 中是 UB
static_assert((INT_MAX << 1) == -2);
static_assert((-8 << 1) == -16);

int main() {}
```

¶2 `E1 << E2` 的值是与 E1×2<sup>E2</sup> 模 2<sup>N</sup> 同余的唯一可表示值，*N* 是结果类型的位宽。注 1 换了个说法：把 `E1` 左移 `E2` 位，空出的位补 0。

对无符号类型，这就是熟悉的高位丢弃。对有符号类型，它等价于把二进制补码的位模式左移、丢弃高位，再按补码解释。负数左移、移进符号位、移出有效位都有定义，只有计数本身受第 1 段限制。

左移不在 [[expr.pre#4]] 所说的算术表达式之列，所以数学结果不可表示即为 UB 的通则不适用。这也意味着 `x << 1` 与 `x * 2` 并不等价：`INT_MAX * 2` 是 UB，`INT_MAX << 1` 是 −2。

!!! history "左移的几次修改"
    - C++98/03 的措辞只描述了无符号类型的结果。
    - C++11 规定：`E1` 有符号且非负、并且 E1×2<sup>E2</sup> 能在结果类型中表示时，结果就是这个值，否则 UB。于是 `1 << 31` 也是 UB。
    - C++14 放宽为：这个值能在对应的无符号类型中表示时，转换为结果类型。`1 << 31` 和 `INT_MAX << 1` 从此有定义，负数左移仍是 UB。
    - C++20 的 [[P0907R4]] 规定有符号整数使用二进制补码，措辞文件 [[P1236R1]] 把左移改写成今天的模 2<sup>N</sup> 定义。

    用 `-std=c++17` 编译上面的例子，Clang 对前两条断言分别说明 "left shift of negative value -1" 和 "signed left shift discards bits"。

## 右移的值（¶3）

```cpp run title="shift-right.cpp" ok
static_assert((-7 >> 1) == -4);   // 向负无穷：floor(-3.5) = -4
static_assert((-7 / 2)  == -3);   // 整数除法向零：trunc(-3.5) = -3
static_assert((-1 >> 31) == -1);  // 空出的高位用符号位填充
static_assert(( 7 >> 1) ==  3);

int main() {}
```

¶3 `E1 >> E2` 的值是 E1/2<sup>E2</sup>，向负无穷舍入。注 2 指出，对有符号类型这就是**算术右移**（arithmetic right shift）：空出的高位用符号位填充。

整数除法向零截断（[[expr.mul#4]]），所以负奇数右移一位和除以 2 差 1。编译器不能把有符号的 `x / 2` 直接编译成 `x >> 1`，要先给负数加 1 再移位。如果确定 `x` 非负，用无符号类型可以省掉这几条指令。

C++20 之前，负数右移的结果由实现定义，实现也可以选择逻辑右移（高位补 0）。主流编译器一直都用算术右移，C++20 只是把它写进了标准。

## 求值顺序（¶4）

¶4 `E1` 先于 `E2` 求值。这条规则是 C++17 由 [[P0145R3]] 加入的。内置移位很少带副作用，真正受益的是重载的 `operator<<`：[[over.match.oper]] 规定，用运算符语法调用重载运算符时，操作数按对应内置运算符的顺序求值。

```cpp run title="shift-iostream-order.cpp" ok
#include <iostream>

int counter = 0;
int next() { return ++counter; }

int main() {
    std::cout << next() << ' ' << next() << '\n';   // 保证输出 1 2
    int i = 0;
    std::cout << i++ << ' ' << i++ << '\n';         // 保证输出 0 1
}
```

在 C++14 中，`std::cout << next() << next()` 相当于嵌套调用 `operator<<(operator<<(cout, next()), next())`，两次 `next()` 的先后是未指定的，有的实现会输出 `2 1`；`i++` 那一行更是 UB。

这个保证只对运算符语法成立。显式写成 `operator<<(operator<<(std::cout, f()), g())` 时它是普通函数调用，实参之间的顺序仍然未指定（[[expr.call]]）。更多讨论见 [[topics/order-of-evaluation]]。

## 优先级

移位的优先级低于 `+`、`-`，高于关系运算符和 `&`、`^`、`|`：

```cpp run title="shift-precedence.cpp" ok
int main() {
    int n = 2;
    int a = 1 << n + 1;      // 1 << (n + 1) == 8，而不是 (1 << n) + 1
    int b = (1 << n) + 1;    // 5
    unsigned flags = 0b1010;
    bool c = flags & 1 << 3; // flags & (1 << 3)
    return (a == 8 && b == 5 && c) ? 0 : 1;
}
```

Clang 对 `1 << n + 1` 给出 `-Wshift-op-parentheses` 警告，建议加括号。

## 常见误解

!!! pitfall "`x << n` 等于 `x * 2^n`"
    溢出时两者不同：C++20 起左移按模 2<sup>N</sup> 有定义，乘法溢出是 UB。

!!! pitfall "右移等于除以 2^n"
    右移向负无穷舍入，除法向零截断，负奇数时结果差 1。

!!! pitfall "旋转写成 `(x << n) | (x >> (32 - n))`"
    `n == 0` 时 `x >> 32` 是 UB。C++20 起用 `<bit>` 里的 `std::rotl`、`std::rotr`，它们对任意计数都有定义。

## 思考题

!!! question "思考题 1"
    设 `int` 为 32 位。`unsigned short s = 0xFFFF; auto r = s << 16;` 的类型和值是什么？C++17 和 C++20 有区别吗？

<details markdown="1">
<summary>答案</summary>

`s` 提升为 `int`，值 65535，结果类型是 `int`。数学值 65535 × 2<sup>16</sup> = 0xFFFF0000，超过 `INT_MAX`。

- C++20：结果是与它模 2<sup>32</sup> 同余的 `int` 值，即 −65536，有定义。
- C++17：`E1` 非负，0xFFFF0000 能在 `unsigned int` 中表示，所以结果是这个值转换为 `int`。当时这个转换由实现定义，补码机器上得到 −65536。
- 如果是 `s << 17`，数学值超出 `unsigned int` 的范围，C++17 中是 UB；C++20 中有定义，值为 −131072。
</details>

!!! question "思考题 2"
    `bool b = true; auto r = b << 31;` 有没有定义？

<details markdown="1">
<summary>答案</summary>

`bool` 是整型，提升为 `int`，值为 1，结果类型 `int`。计数 31 小于 32，合法。C++20 中结果是与 2<sup>31</sup> 模 2<sup>32</sup> 同余的 `int`，即 `INT_MIN`，有定义。按 C++11 的原始措辞，移进符号位是 UB。
</details>

## 小结

| 方面 | 规则 | 段落 |
|---|---|---|
| 转换与结果类型 | 两边各自整数提升；结果类型 = 提升后的左操作数类型 | ¶1 |
| 计数为负或 ≥ 位宽 | {{ub}} | ¶1 |
| 左移 | 与 E1×2<sup>E2</sup> 模 2<sup>N</sup> 同余（C++20 起负数左移有定义） | ¶2 |
| 右移 | E1/2<sup>E2</sup> 向负无穷舍入，即算术右移 | ¶3 |
| 求值顺序 | `E1` 先于 `E2`（C++17 起），重载的 `<<` 同样适用 | ¶4 |
