---
title: 按位与、异或、或运算符
summary: "& ^ | 的操作数要求与常用算术转换；C++20 起按二进制补码的“base-2 表示”逐位定义；优先级低于 == 的历史陷阱；不短路、操作数无序；枚举标志位与 C++26 对不同枚举混合运算的禁止"
status: done
covers: expr.bit.and, expr.xor, expr.or
papers: P0907R4, P1236R1, P2864R2
related: basic.fundamental, expr.arith.conv, expr.log.and, expr.shift, expr.unary.op, conv.prom, lex.digraph
tags: 位运算, 整数, 枚举
updated: 2026-10-17
---

[[expr.bit.and]]（`&`）、[[expr.xor]]（`^`）、[[expr.or]]（`|`）三节结构完全相同，各只有一段。它们的规范内容可以用一句话概括：**操作数为整型或无作用域枚举，做常用算术转换，然后按二进制位逐位运算**。值得注意的地方都在规则之外：

- C++20 之前标准没有规定有符号整数的表示，按位运算对负数的结果其实取决于实现；C++20 用 base-2 表示把它完全确定下来；
- 这三个运算符的优先级低于 `==`/`!=`，这是从 C 继承来的历史包袱；
- 它们与 `&&`/`||` 不同：不短路，两个操作数总是都求值，而且彼此无序；
- 无作用域枚举经常被当作标志位做 `|` 运算，C++26 起不同枚举类型之间的混合运算非良构。

## 规则（[[expr.bit.and#1]]、[[expr.xor#1]]、[[expr.or#1]]）

三个运算符都从左往右结合；操作数必须是整型或无作用域枚举类型，并进行常用算术转换（[[expr.arith.conv]]）。设转换后的操作数为 *x*、*y*，它们的 base-2 表示（[[basic.fundamental]]）的第 *i* 位系数为 *x<sub>i</sub>*、*y<sub>i</sub>*，结果 *r* 的第 *i* 位系数为：

| 运算符 | *r<sub>i</sub>* = 1 当且仅当 |
|---|---|
| `&` | *x<sub>i</sub>* 和 *y<sub>i</sub>* 都为 1 |
| `^` | *x<sub>i</sub>* 和 *y<sub>i</sub>* 恰有一个为 1 |
| `\|` | *x<sub>i</sub>* 和 *y<sub>i</sub>* 至少一个为 1 |

各节的注只是重申结果是按位与、异或、或函数。

### 什么是 base-2 表示

[[basic.fundamental]] 规定，宽度为 *N* 的有符号整数类型的取值范围是 −2<sup>N−1</sup> 到 2<sup>N−1</sup>−1，每个值 *x* 有唯一的 base-2 表示 Σ *x<sub>i</sub>* 2<sup>i</sup>，其中最高位的权重为 −2<sup>N−1</sup>，这就是二进制补码。因此 `-1` 的所有位都是 1，`-1 & 0xFF == 255`：

```cpp run title="bitwise-values.cpp" ok
static_assert((-1 & 0xFF) == 255);    // -1 的 base-2 表示全为 1
static_assert((~0 ^ 5) == -6);        // ~0 是 -1；-1 ^ 5 翻转 5 的各位
static_assert((-8 | 3) == -5);        // ...11111000 | 00000011 = ...11111011
static_assert((0b1100 & 0b1010) == 0b1000);
static_assert((0b1100 ^ 0b1010) == 0b0110);
static_assert((0b1100 | 0b1010) == 0b1110);

int main() {}
```

!!! history "C++20 之前：位运算对负数依赖表示"
    C++17 及以前，标准允许有符号整数采用二进制补码、反码（ones' complement）或原码（sign-magnitude）。位运算作用于对象的值表示，于是 `-1 & 0xFF` 在补码机器上是 255，在反码机器上是 254，在原码机器上是 1。[[P0907R4]]（Signed Integers are Two's Complement）及其措辞文件 [[P1236R1]] 在 C++20 中把补码定为唯一表示，并把这三节改写为基于 base-2 系数的定义。位运算从此不再依赖对象在内存中的表示，成为纯粹的数学定义。

### 类型：整数提升的影响

常用算术转换先做整数提升，所以 `bool`、`char`、`short` 的位运算结果都是 `int`：

```cpp run title="bitwise-types.cpp" ok
#include <type_traits>
#include <cstdint>

static_assert(std::is_same_v<decltype(true & false), int>);
static_assert(std::is_same_v<decltype(std::uint8_t{1} | std::uint8_t{2}), int>);

int main() {
    std::uint8_t a = 0xF0;
    auto b = ~a;                 // int，值为 -241（不是 0x0F！）
    std::uint8_t c = ~a;         // 截断后才得到 0x0F
    return (b == -241 && c == 0x0F) ? 0 : 1;
}
```

（`~` 是一元运算符，见 [[expr.unary.op]]，但它与本节的整数提升问题一起出现得最频繁。）

## 优先级陷阱

在 C 语言最初的设计中，`&` 和 `|` 同时承担逻辑与/或的角色，所以优先级被放在比较运算符之下，使 `if (a == b & c == d)` 能按逻辑运算理解。后来加入了 `&&`、`||`，但为了兼容已有代码，`&`、`|` 的优先级没有调整。结果是：

```cpp run title="bitwise-precedence.cpp" ok
bool is_even_wrong(int x) { return x & 1 == 0; }    // 解析为 x & (1 == 0)，即 x & 0，恒为 false
bool is_even_right(int x) { return (x & 1) == 0; }

int main() { return (!is_even_wrong(4) && is_even_right(4)) ? 0 : 1; }
```

Clang 与 GCC 的 `-Wparentheses`（包含在 `-Wall` 中）会给出警告 "& has lower precedence than ==; == will be evaluated first"。完整的优先级顺序是：`==`/`!=` > `&` > `^` > `|` > `&&` > `||`。

## 不短路，且操作数无序

与 `&&`、`||`（[[expr.log.and]]）不同：

- 两个操作数总是都求值；
- 两个操作数的求值**无序**（unsequenced，[[intro.execution#10]]），标准没有为这三个运算符规定任何顺序。

```cpp title="bitwise-unsequenced.cpp" ub
int main() {
    int i = 0;
    int r = (i = 1) | (i = 2);   // UB: 对 i 的两次修改彼此无序
    return r;
}
```

用 `&`/`|` 代替 `&&`/`||` 来组合 `bool` 有时是有意为之：它避免了分支（对不可预测的条件更快），代价是两边都要求值。但如果右边依赖左边的检查（如 `p != nullptr & p->ok`），就会出错。

## 枚举作为标志位

无作用域枚举可以直接做位运算（经整数提升后得到整数），但结果不再是枚举类型，存回枚举变量需要显式转换。不同枚举类型之间混合位运算在 C++20 被弃用，C++26 由 [[P2864R2]] 改为非良构：

```cpp title="bitwise-enum.cpp" error
enum Perm { read = 1, write = 2, exec = 4 };
enum Mode { text = 8 };

Perm p1 = read | write;                       // error: 结果是整数，不能隐式转回 Perm
Perm p2 = static_cast<Perm>(read | write);    // OK
auto x  = read | text;                        // error: 不同枚举类型（C++26 起）
```

有作用域枚举（`enum class`）根本不能做位运算，需要自己重载 `operator|` 等。这正是它的设计目的：标志位的组合要显式声明。`std::byte`（[[cstddef.syn]]）就是这样一个只提供位运算的有作用域枚举。

## 替代记号

`&`、`^`、`|` 分别有替代记号 `bitand`、`xor`、`bitor`（[[lex.digraph]]），复合赋值有 `and_eq`、`xor_eq`、`or_eq`。它们在预处理阶段就是同一个记号，与 ISO 646 的历史有关。

!!! impl "实现视角"
    三个运算符直接映射到 `and`/`xor`/`or` 指令，在所有主流架构上都是单周期操作，也不存在任何 UB。在 C++ 的整数运算中，对任何输入都有定义的只有少数几种（另外两种是无符号运算和 C++20 的左移）。优化器广泛利用位运算的代数性质，如 `x & (x - 1)` 清除最低位的 1、`x ^ x == 0`。C++20 的 `<bit>` 头文件（`std::popcount`、`std::countr_zero`、`std::has_single_bit` 等）为常见的位技巧提供了可移植且可映射到专用指令的接口。

## 陷阱

!!! pitfall "`x & mask == 0`"
    `==` 先结合。写 `(x & mask) == 0`。

!!! pitfall "以为 `~u8` 还是 8 位"
    `~std::uint8_t{0xF0}` 是 `int` 值 −241；与另一个 `uint8_t` 比较会出乎意料。

!!! pitfall "用 `&` 替代 `&&` 时依赖短路"
    `p & p->x` 两边都会求值，`p` 为空时解引用空指针。

!!! pitfall "以为 C++20 之前负数的位运算结果确定"
    C++17 及以前它依赖有符号整数的表示方式，只是实际上所有主流平台都采用补码。

## 思考题

!!! question "思考题"
    在 C++17 和 C++20 中，`int a = 3, b = 5; a ^= b ^= a ^= b;` 分别是否有定义？结果是什么？

<details markdown="1">
<summary>答案</summary>

这是异或交换的一行写法，它涉及的是复合赋值的求值顺序（[[expr.assign]]），而不是 `^` 本身。

- **C++11/14**：最外层 `a ^= (...)` 需要读取 `a`，而右操作数里的 `a ^= b` 修改了 `a`；两者之间没有顺序关系 → UB（Clang 在 `-std=c++14` 下警告 "unsequenced modification and access to 'a'"）。
- **C++17 起**：[[P0145R3]] 规定赋值的右操作数先于左操作数求值，复合赋值 `E1 op= E2` 中对 `E1` 的读取发生在两个操作数的值计算之后。于是从最内层开始依次执行：`a = 3^5 = 6`，`b = 5^6 = 3`，`a = 6^3 = 5`。结果 `a == 5, b == 3`，交换成功，行为有定义。

当然，`std::swap(a, b)` 永远是更好的写法。
</details>

## 小结

| 方面 | `&` `^` `\|` |
|---|---|
| 操作数 | 整型或无作用域枚举；常用算术转换 |
| 语义 | 按 base-2 表示（补码）逐位运算（C++20 起完全确定） |
| UB | 无（结果总能表示） |
| 求值 | 两边都求值，彼此无序（不短路） |
| 优先级 | 低于 `==`/`!=`；`&` > `^` > `\|` > `&&` |
| 枚举 | 同一无作用域枚举可用，结果为整数；不同枚举混合 C++26 非良构 |
