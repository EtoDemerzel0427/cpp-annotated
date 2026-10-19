---
title: 按位与、异或、或运算符
summary: & ^ | 接受整型和无作用域枚举，做常用算术转换后按二进制补码逐位运算，对任何输入都有定义；它们的优先级低于 ==，不短路，两个操作数的求值彼此无序。
status: done
covers: expr.bit.and, expr.xor, expr.or
papers: P0907R4, P1236R1, P2864R2
related: basic.fundamental, expr.arith.conv, expr.log.and, expr.shift, expr.unary.op, conv.prom, lex.digraph
tags: 位运算, 整数, 枚举
updated: 2026-10-19
---

!!! tldr
    - `&`、`^`、`|` 的操作数必须是整型或无作用域枚举，先做常用算术转换，再按二进制补码逐位运算。结果总能表示，不存在未定义行为。
    - 整数提升让 `bool`、`char`、`uint8_t` 的位运算结果都是 `int`，所以 `~std::uint8_t{0xF0}` 是 −241 而不是 `0x0F`。
    - 这三个运算符的优先级低于 `==`：`x & 1 == 0` 是 `x & (1 == 0)`。
    - 它们不短路，两个操作数都会求值，而且彼此无序；拿 `&` 代替 `&&` 时，右边不能依赖左边的检查。
    - 无作用域枚举做位运算得到整数；C++26 起不同枚举类型之间的位运算非良构。

[[expr.bit.and]]（`&`）、[[expr.xor]]（`^`）、[[expr.or]]（`|`）三节结构相同，各只有一段。

## 逐位运算（[[expr.bit.and#1]]、[[expr.xor#1]]、[[expr.or#1]]）

```cpp run title="bitwise-values.cpp" ok
static_assert((0b1100 & 0b1010) == 0b1000);
static_assert((0b1100 ^ 0b1010) == 0b0110);
static_assert((0b1100 | 0b1010) == 0b1110);
static_assert((-1 & 0xFF) == 255);    // -1 的所有位都是 1
static_assert((~0 ^ 5) == -6);        // ~0 是 -1，^ 翻转 5 的每一位
static_assert((-8 | 3) == -5);        // ...11111000 | 00000011 = ...11111011

int main() {}
```

¶1 三个运算符都从左往右结合，操作数必须是整型或无作用域枚举类型，先做常用算术转换（[[expr.arith.conv]]），把两边变成同一个类型。设转换后的操作数为 *x*、*y*，结果为 *r*，它们的 base-2 表示的第 *i* 位系数分别是 *x<sub>i</sub>*、*y<sub>i</sub>*、*r<sub>i</sub>*：

| 运算符 | *r<sub>i</sub>* 为 1 的条件 |
|---|---|
| `&` | *x<sub>i</sub>* 和 *y<sub>i</sub>* 都是 1 |
| `^` | *x<sub>i</sub>* 和 *y<sub>i</sub>* 恰有一个是 1 |
| `\|` | *x<sub>i</sub>* 和 *y<sub>i</sub>* 至少一个是 1 |

**base-2 表示**定义在 [[basic.fundamental]]：宽度为 *N* 的有符号整数，每个值 *x* 都唯一地写成 Σ *x<sub>i</sub>* 2<sup>i</sup>，其中最高位的权重是 −2<sup>N−1</sup>。这就是二进制补码，所以 `-1` 的每一位都是 1。

这个定义只依赖值，不依赖对象在内存里怎样存放。结果的每一位都是 0 或 1，总能在结果类型中表示，所以这三个运算符对任何输入都有定义。

!!! history "C++20 之前，负数的位运算依赖表示"
    C++17 及以前，有符号整数可以用二进制补码、反码（ones' complement）或原码（sign-magnitude）表示，位运算作用于值的表示。于是 `-1 & 0xFF` 在补码机器上是 255，在反码机器上是 254，在原码机器上是 1。C++20 的 [[P0907R4]]（Signed Integers are Two's Complement）把补码定为唯一的表示，措辞文件 [[P1236R1]] 把这三节改写成基于 base-2 系数的定义。

### 整数提升改变结果类型

常用算术转换的第一步是整数提升（[[conv.prom]]）：比 `int` 窄的类型先变成 `int`。所以 `bool`、`char`、`short` 的位运算结果都是 `int`：

```cpp run title="bitwise-types.cpp" ok
#include <type_traits>
#include <cstdint>

static_assert(std::is_same_v<decltype(true & false), int>);
static_assert(std::is_same_v<decltype(std::uint8_t{1} | std::uint8_t{2}), int>);

int main() {
    std::uint8_t a = 0xF0;
    auto b = ~a;                 // int，值为 -241，不是 0x0F
    std::uint8_t c = ~a;         // 截断后才得到 0x0F
    return (b == -241 && c == 0x0F) ? 0 : 1;
}
```

一元 `~` 不属于本节（见 [[expr.unary.op]]），但它和这里的位运算经常一起出现，遇到的是同一个整数提升问题。

## 优先级低于 `==`

```cpp run title="bitwise-precedence.cpp" ok
bool is_even_wrong(int x) { return x & 1 == 0; }    // x & (1 == 0)，即 x & 0，恒为 false
bool is_even_right(int x) { return (x & 1) == 0; }

int main() { return (!is_even_wrong(4) && is_even_right(4)) ? 0 : 1; }
```

C 语言早期没有 `&&` 和 `||`，`&` 和 `|` 兼任逻辑与、或，所以优先级放在比较运算符之下，`a == b & c == d` 才能按逻辑运算理解。后来加入了 `&&`、`||`，但为了兼容已有代码，`&` 和 `|` 的优先级没有调整。

完整的顺序是：`==`、`!=` 高于 `&`，`&` 高于 `^`，`^` 高于 `|`，`|` 高于 `&&`。`-Wall` 包含的 `-Wparentheses` 会对上面的写法给出警告 "& has lower precedence than ==; == will be evaluated first"。

## 不短路，两边无序

与 `&&`、`||`（[[expr.log.and]]）不同，`&`、`^`、`|` 总是求值两个操作数，而且标准没有给两个操作数规定任何先后，它们的求值是**无序**的（unsequenced，[[intro.execution#10]]）。对同一个变量的两次修改彼此无序，就是 UB：

```cpp title="bitwise-unsequenced.cpp" ub
int main() {
    int i = 0;
    int r = (i = 1) | (i = 2);   // UB: 对 i 的两次修改彼此无序
    return r;
}
```

有时人们有意用 `&` 组合两个 `bool`：没有分支，对难以预测的条件可能更快，代价是两边都要求值。如果右边依赖左边的检查，这样改写就会出错：

<div class="compare" markdown="1">

```cpp ok
struct S { int x; };
bool ok(S* p) {
  return p != nullptr
      && p->x > 0;
}
```

```cpp ub
struct S { int x; };
bool ok(S* p) {
  return (p != nullptr)
       & (p->x > 0);
}
// p 为空时仍然解引用：UB
```

</div>

## 枚举作为标志位

无作用域枚举可以直接做位运算，经整数提升后得到整数，结果不再是枚举类型，存回枚举变量需要显式转换。不同枚举类型之间的位运算在 C++20 被弃用，C++26 由 [[P2864R2]] 改为非良构：

```cpp title="bitwise-enum.cpp" error
enum Perm { read = 1, write = 2, exec = 4 };
enum Mode { text = 8 };

Perm p1 = read | write;                       // error: 结果是 int，不能隐式转回 Perm
Perm p2 = static_cast<Perm>(read | write);    // OK
auto x  = read | text;                        // error: 不同的枚举类型（C++26 起）
```

有作用域枚举（`enum class`）不能直接做位运算，需要自己重载 `operator|` 等运算符。这正是它的设计目的：哪些组合有意义，要由类型的作者显式声明。`std::byte`（[[cstddef.syn]]）就是一个只提供位运算的有作用域枚举。

`&`、`^`、`|` 还有替代记号 `bitand`、`xor`、`bitor`，复合赋值有 `and_eq`、`xor_eq`、`or_eq`（[[lex.digraph]]），它们与原记号完全等价。

!!! impl "实现视角"
    三个运算符直接对应 `and`、`eor`/`xor`、`orr`/`or` 指令，在主流架构上都是单周期操作。优化器广泛利用它们的代数性质，例如 `x & (x - 1)` 清除最低位的 1、`x ^ x` 为 0。C++20 的 `<bit>`（`std::popcount`、`std::countr_zero`、`std::has_single_bit` 等）为常见的位技巧提供了可移植、能映射到专用指令的接口。

## 常见误解

!!! pitfall "`x & mask == 0`"
    `==` 先结合，应写成 `(x & mask) == 0`。

!!! pitfall "`~u8` 还是 8 位"
    `~std::uint8_t{0xF0}` 是 `int` 值 −241，拿它与另一个 `uint8_t` 比较会出乎意料。

!!! pitfall "C++20 之前负数的位运算结果是确定的"
    C++17 及以前它依赖有符号整数的表示方式，只是主流平台都用补码，所以实际上没有差别。

## 思考题

!!! question "思考题"
    `int a = 3, b = 5; a ^= b ^= a ^= b;` 在 C++14 和 C++17 中是否有定义？结果是什么？

<details markdown="1">
<summary>答案</summary>

这是一行写成的异或交换。问题在于复合赋值的求值顺序（[[expr.assign]]），而不在 `^` 本身。

C++14：最外层的 `a ^= (...)` 要读取 `a`，右操作数里的 `a ^= b` 又修改了 `a`，两者之间没有先后关系，所以是 UB。Clang 在 `-std=c++14` 下警告 "unsequenced modification and access to 'a'"。

C++17 起，[[P0145R3]] 规定赋值的右操作数先于左操作数求值。于是从最内层依次执行：`a = 3^5 = 6`，`b = 5^6 = 3`，`a = 6^3 = 5`。结果 `a == 5`、`b == 3`，有定义。实际代码里当然应该写 `std::swap(a, b)`。
</details>

## 小结

| 方面 | `&` `^` `\|` |
|---|---|
| 操作数 | 整型或无作用域枚举，做常用算术转换 |
| 语义 | 按 base-2 表示（补码）逐位运算，C++20 起与表示无关 |
| UB | 没有，结果总能表示 |
| 求值 | 两边都求值，彼此无序，不短路 |
| 优先级 | 低于 `==`、`!=`；`&` 高于 `^` 高于 `\|` 高于 `&&` |
| 枚举 | 同一无作用域枚举可用，结果为整数；不同枚举混合 C++26 起非良构 |
