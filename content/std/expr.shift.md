---
title: 移位运算符
summary: "<< 与 >> 的操作数各自整数提升、结果类型取左操作数；移位计数为负或不小于位宽是 UB；C++20 起左移按模 2^N 定义（负数左移不再 UB）、右移是向负无穷舍入的算术移位；C++17 起左操作数先求值"
status: done
papers: P0907R4, P1236R1, P0145R3
related: basic.fundamental, conv.prom, expr.mul, expr.arith.conv, over.match.oper, intro.execution
tags: 位运算, 整数, UB, 二进制补码
updated: 2026-10-17
---

移位运算符处在整数算术与位操作的交界处。与其他二元算术运算符相比，它有三个不同之处：

1. **两个操作数各自做整数提升，不做常用算术转换**，结果类型只取决于左操作数；
2. 移位计数有严格的范围：负数或不小于位宽就是 UB；
3. C++20 之前，负数左移是 UB，负数右移的结果由实现定义；C++20 规定有符号整数使用二进制补码之后，左移和右移的语义都完全确定下来。

另外，`<<`/`>>` 还是 iostream 的插入/提取运算符。C++17 为它加上了从左往右的求值顺序保证（¶4），`std::cout << f() << g()` 的输出顺序从此是确定的。

## 操作数、结果类型与 UB（¶1）

¶1 `<<` 和 `>>` 从左往右结合。操作数必须是整型或无作用域枚举类型的 prvalue，各自进行整数提升（[[conv.prom]]）；**结果类型是提升后的左操作数的类型**。

这与 `+`、`*` 等运算符使用的常用算术转换截然不同：右操作数的类型不影响结果类型。直观上这很合理，移位计数只是一个距离，`1 << 3LL` 没有理由变成 `long long`：

```cpp run title="shift-types.cpp" ok
#include <type_traits>

static_assert(std::is_same_v<decltype(1 << 2LL), int>);          // 右操作数不影响结果类型
static_assert(std::is_same_v<decltype(char(1) << 2), int>);      // char 提升为 int
static_assert(std::is_same_v<decltype(1u << 2), unsigned>);
static_assert(std::is_same_v<decltype(1LL << 2), long long>);
static_assert((char(1) << 20) == (1 << 20));                     // 提升后才移位，不会"丢在 char 里"

int main() {}
```

### 计数越界是 UB

!!! std
    The behavior is undefined if the right operand is negative, or greater than or equal to the width of the promoted left operand.

    右操作数为负，或大于等于提升后左操作数的位宽时，行为未定义。

这里的位宽（width）是 [[basic.fundamental]] 定义的值表示位数（不含填充位），32 位 `int` 的位宽是 32。因此：

```cpp title="shift-count-ub.cpp" error
constexpr int       a = 1 << 32;      // error: 计数等于 int 的位宽（UB，非常量）
constexpr int       b = 1 << 40LL;    // error: 结果类型仍是 int，计数 40 ≥ 32
constexpr long long c = 1 << 32;      // error: 左操作数是 int！赋给 long long 于事无补
constexpr int       d = 1 << -1;      // error: 负计数
```

```cpp title="shift-count-ok.cpp" ok
static_assert((1LL << 32) == 4294967296LL);   // OK: 左操作数是 long long，位宽 64
static_assert((1u << 31) == 2147483648u);     // OK
```

第三行是最常见的写法错误：想构造一个 64 位掩码，却写了 `1 << n`。应当写 `1LL << n` 或 `uint64_t{1} << n`。

!!! impl "为什么计数越界是 UB 而不是某个确定值？"
    因为不同硬件对过大的移位计数处理不同，标准无论规定哪一种结果，其余平台都要付出代价：

    - **x86/x86-64** 的变量移位（`shl`/`sar` 配合 `cl`）把计数按位宽取模（32 位操作取低 5 位、64 位取低 6 位），所以 `1 << 32` 在运行期得到 `1`；
    - **AArch64** 的 `lslv`/`asrv` 同样把计数对数据宽度取模，结果也是 `1`（本站在 arm64 上实测如此）；
    - **32 位 ARM** 的寄存器移位取计数的低 8 位，计数 32 时把值全部移出，结果是 `0`；
    - **SIMD** 指令（如 SSE2 的 `psllq`）在计数过大时通常得到 `0`。

    在同一台机器上，同一行 `x << n` 的标量代码和向量化代码甚至可能给出不同结果。把它定为 UB，编译器就可以直接发出一条移位指令。`-fsanitize=shift-exponent`（包含在 `-fsanitize=undefined` 中）会在运行期报告 "shift exponent 32 is too large for 32-bit type 'int'"。

## 左移的值（¶2）

!!! std
    The value of E1 << E2 is the unique value congruent to E1×2^E2 modulo 2^N, where N is the width of the type of the result.

    `E1 << E2` 的值是与 E1×2<sup>E2</sup> 模 2<sup>N</sup> 同余的唯一（可表示）值，N 是结果类型的位宽。

也就是说，**C++20 起，只要计数合法，左移永远有定义**。对无符号类型，这就是熟悉的高位丢弃；对有符号类型，它等价于按二进制补码的位模式左移、丢弃高位，再把结果按补码解释。负数左移、移进符号位、移出有效位，全都有定义：

```cpp run title="shift-left-cxx20.cpp" ok
#include <climits>

static_assert((-1 << 31) == INT_MIN);    // C++20 前：负数左移 UB
static_assert((3 << 31) == INT_MIN);     // C++20 前：结果连无符号类型都放不下，UB
static_assert((INT_MAX << 1) == -2);     // C++14–17：有定义（见下）；C++11：UB
static_assert((-8 << 1) == -16);

int main() {}
```

左移不是 [[expr.pre#4]] 所说的算术表达式（那里只列了一元正负、加减乘除取余），所以数学结果不可表示即为 UB 的通则不适用于它，左移的值完全由本段的模运算定义确定。这也意味着 `x << 1` 与 `x * 2` 在 C++20 中并不等价：后者溢出是 UB，前者不是。

!!! history "左移的三个时代"
    - **C++98/03**：措辞只描述了无符号类型（高位丢弃），没有说清有符号类型的情况。
    - **C++11**：若 `E1` 是有符号且非负、并且 E1×2<sup>E2</sup> 可以在结果类型中表示，结果就是它，否则是 UB。于是负数左移是 UB，移进符号位（如 `1 << 31`）也是 UB。
    - **C++14**：通过一个缺陷报告放宽为：若该值可在结果类型对应的无符号类型中表示，则把它转换为结果类型。于是 `1 << 31` 有定义（得到 `INT_MIN`，当时这一转换本身是实现定义的），`INT_MAX << 1` 也有定义；负数左移仍是 UB。
    - **C++20**：[[P0907R4]]（Signed Integers are Two's Complement）及其措辞文件 [[P1236R1]] 规定有符号整数使用二进制补码，并把左移改写成今天的模 2<sup>N</sup> 同余定义，负数左移从此有定义。

    用 `-std=c++17` 编译上面的例子，Clang 会对前两条断言报告 "left shift of negative value -1" 和 "signed left shift discards bits"。

## 右移的值（¶3）

!!! std
    The value of E1 >> E2 is E1/2^E2, rounded towards negative infinity.

    `E1 >> E2` 的值是 E1/2<sup>E2</sup>，向负无穷舍入。

注 2 指出，对有符号类型，这就是**算术右移**，即用符号位填充空出的高位。C++20 之前，负数右移的结果由实现定义（实现可以选择逻辑右移），尽管所有主流编译器早就采用算术右移。

向负无穷舍入与整数除法的向零截断（[[expr.mul#4]]）不同，对负奇数会差 1：

```cpp run title="shift-right.cpp" ok
static_assert((-7 >> 1) == -4);   // 向负无穷：floor(-3.5) = -4
static_assert((-7 / 2)  == -3);   // 向零：trunc(-3.5) = -3
static_assert((-1 >> 31) == -1);  // 算术右移：符号位填满，结果仍是 -1
static_assert(( 7 >> 1) ==  3);

int main() {}
```

因此编译器不能把有符号的 `x / 2` 直接编译成 `x >> 1`，必须先给负数加上偏置 1 再移位。如果你确定 `x` 非负，写成无符号类型或者直接用 `>>` 可以省掉这几条指令。

## 求值顺序（¶4）

!!! std
    The expression E1 is sequenced before the expression E2.

    `E1` 先于 `E2` 求值。

这是 C++17 由 [[P0145R3]] 加入的。它对内置移位意义不大（内置移位很少有副作用），真正受益的是重载的 `operator<<`：[[over.match.oper]] 规定，用运算符语法调用重载运算符时，操作数按内置运算符规定的顺序求值。于是：

```cpp run title="shift-iostream-order.cpp" ok
#include <iostream>

int counter = 0;
int next() { return ++counter; }

int main() {
    std::cout << next() << ' ' << next() << '\n';   // C++17 起保证输出 "1 2"
    int i = 0;
    std::cout << i++ << ' ' << i++ << '\n';         // C++17 起有定义，输出 "0 1"
}
```

在 C++14 中，`std::cout << next() << next()` 是一连串嵌套的函数调用 `operator<<(operator<<(cout, next()), next())`，两次 `next()` 的求值顺序是未指定的（从右往左求值实参的实现会输出 "2 1"）；`i++ << i++` 那个版本更是 UB。C++17 让运算符语法下的这些代码都符合直觉。但**只有运算符语法才有这个保证**，显式写成 `operator<<(operator<<(std::cout, f()), g())` 时，它就是普通函数调用，实参之间的顺序仍不确定（[[expr.call]]）。详见 [[topics/order-of-evaluation]]。

## 优先级陷阱

移位的优先级低于 `+`、`-`，高于关系运算符和位运算符 `&`、`^`、`|`：

```cpp run title="shift-precedence.cpp" ok
int main() {
    int n = 2;
    int a = 1 << n + 1;      // 1 << (n + 1) == 8，而不是 (1 << n) + 1 == 5
    int b = (1 << n) + 1;    // 5
    unsigned flags = 0b1010;
    bool c = flags & 1 << 3; // flags & (1 << 3)：这里恰好符合直觉
    return (a == 8 && b == 5 && c) ? 0 : 1;
}
```

Clang/GCC 的 `-Wshift-op-parentheses` / `-Wparentheses` 会对 `1 << n + 1` 给出加括号的建议。

## 陷阱

!!! pitfall "`1 << 40` 想得到 64 位结果"
    结果类型取左操作数：`1` 是 `int`，计数 40 ≥ 32，UB。写 `1LL << 40` 或 `std::uint64_t{1} << 40`。

!!! pitfall "以为 `x << n` 等价于 `x * 2^n`"
    C++20 起左移按模 2<sup>N</sup> 有定义，乘法溢出却是 UB，两者在溢出时一个有定义、一个没有。

!!! pitfall "以为右移等价于除以 2^n"
    右移向负无穷舍入，除法向零截断，负奇数时结果差 1。

!!! pitfall "旋转写成 `(x << n) | (x >> (32 - n))`"
    `n == 0` 时 `x >> 32` 是 UB。C++20 起用 `std::rotl` / `std::rotr`（`<bit>`），它们对任意计数都有定义。

## 思考题

!!! question "思考题 1"
    设 `int` 为 32 位。`unsigned short s = 0xFFFF; auto r = s << 16;` 的类型和值是什么？在 C++17 和 C++20 下有区别吗？

<details markdown="1">
<summary>答案</summary>

`s` 提升为 `int`（值 65535），结果类型 `int`。数学值 65535 × 2<sup>16</sup> = 0xFFFF0000 = 4294901760，超过 `INT_MAX`。

- **C++20**：取模 2<sup>32</sup> 同余的 `int` 值，即 −65536。有定义。
- **C++17**：`E1` 非负，0xFFFF0000 可以在 `unsigned int` 中表示，所以结果是该值转换为 `int`，而 C++17 中这一转换是实现定义的（在补码机器上得到 −65536）。有定义（实现定义的值）。
- 若是 `s << 17`：C++17 中 65535 × 2<sup>17</sup> 超出 `unsigned int` 范围 → UB；C++20 中有定义（−131072）。
</details>

!!! question "思考题 2"
    `bool b = true; auto r = b << 31;` 是否有定义？

<details markdown="1">
<summary>答案</summary>

`bool` 是整型，整数提升为 `int`（值 1），结果类型 `int`，计数 31 < 32 合法。C++20 中值为与 2<sup>31</sup> 模 2<sup>32</sup> 同余的 `int`，即 `INT_MIN`。有定义。（C++11 中移进符号位是 UB。）
</details>

## 小结

| 方面 | 规则 | 段落 |
|---|---|---|
| 转换 | 两操作数各自整数提升；结果类型 = 提升后的左操作数类型 | ¶1 |
| 计数为负或 ≥ 位宽 | {{ub}} | ¶1 |
| 左移的值 | 与 E1×2<sup>E2</sup> 模 2<sup>N</sup> 同余（C++20 起负数左移有定义） | ¶2 |
| 右移的值 | E1/2<sup>E2</sup> 向负无穷舍入（算术右移；C++20 前负数为实现定义） | ¶3 |
| 求值顺序 | `E1` 先于 `E2`（C++17），重载的 `<<` 同样适用 | ¶4 |
