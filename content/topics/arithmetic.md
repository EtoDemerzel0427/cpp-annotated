---
title: 整数与浮点运算的陷阱
summary: 内置算术在运算前怎样悄悄改变操作数的类型，哪些越界是取模、哪些是 UB，标准对浮点保证了什么，以及 C++20 以来用来写对算术的库工具。
status: draft
order: 78
since: c++98
papers: P0907R4, P1236R1, P0586R2, P0543R3, P0476R2, P0330R8, P1227R2, P1467R9
related: conv.prom, conv.rank, expr.arith.conv, conv.integral, expr.pre, expr.mul, expr.shift, dcl.init.list, basic.fundamental, conv.fpint, utility.intcmp, numeric.sat, numerics.c.ckdint, bit.cast, expr.const.core, topics/undefined-behavior
tags: 整数, 浮点, 转换, 溢出, UB, 专题
updated: 2026-10-19
---

!!! tldr
    - 运算之前，比 `int` 窄的整数先提升为 `int`；两个操作数类型不同时，再按寻常算术转换统一类型，有符号和无符号混用时通常变成无符号。
    - 整数之间的转换总是取模（C++20 起包括有符号目标），而有符号算术溢出是 UB，优化器会据此删掉你写的溢出检查。
    - 除法向零截断，`INT_MIN / -1`、除以零、移位量为负或不小于宽度都是 UB；C++20 起左移负数有定义。
    - 浮点转整数时，截断后放不下就是 UB，`(unsigned)-1.0` 也算；NaN 与任何值都不相等，`-0.0 == 0.0`。
    - 需要正确的比较、饱和或溢出检测时，用 `std::cmp_less`、`std::in_range`、`std::saturating_add`、`ckd_add`，而不是自己拼表达式。

## 两个意外

```cpp run title="surprise.cpp" ok
#include <cstdio>
#include <vector>
int main() {
  std::vector<int> v;                  // 空
  if (v.size() - 1 >= 0)               // 永远为真
    std::puts("size() - 1 >= 0");
  std::printf("%zu\n", v.size() - 1);  // 18446744073709551615
  std::printf("%d\n", -1 < 1u);        // 0
}
```

`v.size()` 的类型是 `std::size_t`，一个无符号类型。`0 - 1` 在无符号类型里按模 2<sup>64</sup> 回绕成最大值，而无符号值总是 `>= 0`。`-1 < 1u` 中，`int` 和 `unsigned int` 要先统一成同一个类型才能比较，统一的结果是 `unsigned int`，`-1` 变成了 4294967295。

这两行都是良构、行为明确的代码，只是结果和数学直觉不一样。本机 Clang 23 在 `-Wall -Wextra` 下对这两行都没有警告：`>= 0` 恒真的诊断（`-Wtautological-unsigned-zero-compare`）要单独开启，`-Wsign-compare` 对常量操作数不报。

要读懂这类代码，需要知道一个内置算术表达式求值时依次发生什么：

1. 每个窄整数操作数做整型提升；
2. 两个操作数按寻常算术转换得到公共类型；
3. 在公共类型里做运算，结果可能溢出；
4. 结果赋给变量或传给函数时，再做一次转换。

下面按这个顺序讲。

## 整型提升：窄整数先变成 `int`

```cpp run title="promote.cpp" ok
#include <cstdint>
#include <cstdio>
#include <type_traits>
int main() {
  std::uint8_t a = 200, b = 100;
  auto s = a + b;                       // int，值 300
  static_assert(std::is_same_v<decltype(s), int>);
  static_assert(std::is_same_v<decltype(+'x'), int>);
  static_assert(std::is_same_v<decltype(true + true), int>);
  static_assert(std::is_same_v<decltype(-a), int>);

  std::uint8_t x = 0;
  std::printf("%d\n", ~x == 0xFF);                  // 0：~x 是 int，值为 -1
  std::printf("%d\n", (std::uint8_t)~x == 0xFF);    // 1
  std::printf("%d\n", s);                           // 300
}
```

内置算术运算符不在比 `int` 窄的类型上运算。整数类型的**整数转换等级**（[[g:integer-conversion-rank|integer conversion rank]]，下一节给出完整的表）低于 `int` 时，它的 prvalue 先转换成 `int`；如果 `int` 放不下它的所有值，就转换成 `unsigned int`（[[conv.prom#2]]）。这一步叫**整型提升**（[[g:integral-promotion|integral promotion]]）。`bool` 提升为 `int`，`false` 变 0，`true` 变 1（[[conv.prom#7]]）。

所以 `uint8_t + uint8_t` 的结果是 `int`，不会在 255 处回绕。`~x` 也是先提升再取反，得到 32 位的全 1，也就是 `int` 的 -1，和 `0xFF`（`int` 的 255）不相等。

提升发生在每个使用寻常算术转换的二元运算符、一元 `+ - ~` 和移位运算符的操作数上。它有一个后果最容易出事：无符号的窄类型会变成有符号的 `int`。

```cpp run title="ushort.cpp" ub
#include <cstdint>
#include <cstdio>
std::uint16_t mul(std::uint16_t a, std::uint16_t b) {
  return a * b;                // 两边都提升为 int
}
int main() {
  std::printf("%u\n", mul(65535, 65535));   // UB：int 溢出
}
```

两个操作数都是无符号的，乘法却在 `int` 里进行。65535 × 65535 = 4294836225 超过了 32 位 `int` 的最大值，这是有符号溢出。本机 UBSan 报告：

```text
ushort.cpp:4:12: runtime error: signed integer overflow: 65535 * 65535 cannot be represented in type 'int'
```

写成 `1u * a * b` 或先 `static_cast<unsigned>(a)` 就能让运算留在无符号类型里。

其余几种情形简要列出，细节见 [[conv.prom]] 的页面：

- `char16_t`、`char32_t`、`wchar_t`、`char8_t` 提升为能放下其底层类型全部值的第一个类型，依次尝试 `int`、`unsigned int`、`long`……（[[conv.prom#6]]）。
- 底层类型未固定的无作用域枚举，提升为能表示全部枚举值的第一个类型，依次尝试 `int`、`unsigned int`、`long`……（[[conv.prom#3]]）。
- 位域按自己的宽度提升（[[conv.prom#5]]）：`unsigned x : 4` 的所有值 `int` 都放得下，所以它提升为 `int`，`s.x - 1` 可以是负数。

```cpp ok
#include <type_traits>
struct S { unsigned small : 4; unsigned long long big : 40; };
constexpr S s{};
static_assert(std::is_same_v<decltype(s.small + 0), int>);  // 位域提升为 int
static_assert(s.small - 1 < 0);                             // 0 - 1 == -1
static_assert(std::is_same_v<decltype(s.big + 0), unsigned long long>);
constexpr unsigned u = 0;
static_assert(u - 1 > 0);                                   // 普通 unsigned：回绕
```

!!! pitfall "`char` 的符号由实现决定"
    `char` 和 `signed char`、`unsigned char` 是三个不同的类型，`char` 的底层类型是两者之一，由实现决定（[[basic.fundamental#7]]）。本机 macOS arm64 上 `char` 有符号，`char c = '\xE9';` 的值是 -23，`c == 0xE9` 恒为假（Clang 给出 `-Wtautological-constant-out-of-range-compare`）；以 aarch64 Linux 为目标时 Clang 预定义 `__CHAR_UNSIGNED__`，同样的代码得到 233。处理字节数据用 `unsigned char` 或 `std::byte`。

## 寻常算术转换：两个操作数取公共类型

`+ - * / % < == & | ^ ?:` 等运算符的两个操作数类型不同时，要先转换到一个公共类型，结果通常也是这个类型。这套规则叫**寻常算术转换**（[[g:usual-arithmetic-conversions|usual arithmetic conversions]]，[[expr.arith.conv]]）。对两个整数操作数，它先对两边做整型提升，得到 `T1`、`T2`，然后按顺序判断（[[expr.arith.conv#1.5]]）：

1. `T1`、`T2` 相同，就用它；
2. 同为有符号或同为无符号，用等级高的那个；
3. 一个有符号（记为 `S`），一个无符号（记为 `U`）时：
    - `U` 的等级不低于 `S`，用 `U`；
    - 否则，如果 `S` 能表示 `U` 的全部值，用 `S`；
    - 否则，用 `S` 对应的无符号类型。

等级由 [[conv.rank#1]] 规定，它只看类型，与位宽有关但不等于位宽：

| 等级（从高到低） | 有符号 | 无符号 | LP64 宽度 |
|---|---|---|---|
| 5 | `long long` | `unsigned long long` | 64 |
| 4 | `long` | `unsigned long` | 64 |
| 3 | `int` | `unsigned int` | 32 |
| 2 | `short` | `unsigned short` | 16 |
| 1 | `signed char` | `unsigned char` | 8 |
| 最低 | `bool` | | |

字符类型的等级等于它的底层类型；同宽度时标准整数类型的等级高于扩展整数类型。表中 LP64 是 64 位 Linux 和 macOS 的数据模型，`long` 和 `long long` 宽度相同但等级不同。

有符号和无符号混用时，第 3 步的三个分支都会出现，结果取决于平台：

```cpp ok
#include <type_traits>
using std::is_same_v;
static_assert(is_same_v<decltype(1 + 1u), unsigned>);
static_assert(is_same_v<decltype(1L + 1u), long>);                 // LP64
static_assert(is_same_v<decltype(1LL + 1UL), unsigned long long>); // LP64
static_assert(is_same_v<decltype((short)1 + (unsigned short)1), int>);
static_assert(-1L < 1u);       // 公共类型 long：真
static_assert(!(-1LL < 1UL));  // 公共类型 unsigned long long：假
static_assert(is_same_v<decltype(1 + 1.0f), float>);
static_assert(16777217 + 0.0f == 16777216.0f);
```

- `long` 与 `unsigned int`：`long` 等级更高，又能放下 `unsigned int` 的全部值，结果是 `long`，`-1L < 1u` 为真。在 `long` 只有 32 位的 Windows 上，`long` 放不下 `unsigned int` 的全部值，结果变成 `unsigned long`，同一个比较为假。
- `long long` 与 `unsigned long`：`long long` 等级更高，但在 LP64 上两者都是 64 位，放不下，结果是两者都没写的 `unsigned long long`。

有浮点操作数时规则简单得多：整数一律转换成浮点类型，即使会丢精度（[[expr.arith.conv#1.4.2]]）。`16777217 + 0.0f` 等于 `16777216.0f`，因为 `float` 只有 24 位有效数字。两个浮点类型取等级高的那个，扩展浮点类型的规则见后文。

完整的算法、枚举操作数的规则（C++26 起不同枚举之间的运算非良构）以及更多平台差异，见 [[expr.arith.conv]] 的页面。

## 整数转换：总是取模

```cpp run title="modular.cpp" ok
#include <cstdint>
#include <cstdio>
int main() {
  int big = 200, neg = -1;
  std::int8_t  a = big;             // 200 - 256 = -56
  std::uint8_t b = neg;             // -1 + 256 = 255
  unsigned     c = neg;             // 4294967295
  std::int32_t d = 3'000'000'000LL; // 3e9 - 2^32 = -1294967296
  std::printf("%d %d %u %d\n", a, b, c, d);
}
```

把一个整数转换成另一个整数类型时，结果是目标类型中与原值模 2<sup>N</sup> 同余的唯一值，N 是目标类型的**宽度**（[[g:integer-width|width]]，值表示的位数）（[[conv.integral#3]]）。对二进制补码来说，这就是保留低 N 位。

这条规则从 C++20 起也适用于有符号目标。C++20 之前，转换到有符号类型而值放不下时，结果由实现定义；[[P0907R4]] 和 [[P1236R1]] 规定有符号整数用二进制补码表示（[[basic.fundamental#3]]），转换随之定义为取模。

整数转换没有 UB，但常常不是你想要的。Clang 对常量（如上面的 `d`）给出 `-Wconstant-conversion`；对变量要开 `-Wconversion` 系列警告。运行时可以用 `-fsanitize=implicit-conversion` 抓值被改变的隐式转换，它检查的不是 UB，所以不在 `-fsanitize=undefined` 里：

```text
modular.cpp:5:20: runtime error: implicit conversion from type 'int' of value 200 (32-bit, signed) to type 'std::int8_t' (aka 'signed char') changed the value to -56 (8-bit, signed)
```

## 溢出：有符号是 UB，无符号回绕

两种整数在越界时的待遇完全不同：

- 无符号类型的算术按模 2<sup>N</sup> 进行，不存在溢出（[[basic.fundamental#2]]）。
- 有符号类型的算术，数学结果超出类型的表示范围时行为未定义（[[expr.pre#4]]）。

C++20 已经规定了二进制补码表示，有符号溢出仍然是 UB，这是有意保留的。编译器可以假设溢出不发生，并据此化简：

```cpp title="ovf.cpp"
bool next_is_bigger(int x)          { return x + 1 > x; }
bool next_is_bigger_u(unsigned x)   { return x + 1 > x; }
int  times2_div2(int x)             { return x * 2 / 2; }
unsigned times2_div2_u(unsigned x)  { return x * 2 / 2; }
```

本机 Clang 23 以 x86-64 为目标、`-O2` 编译的结果：

```text
_Z14next_is_biggeri:          # int：直接返回 true
        movb    $1, %al
        retq
_Z16next_is_bigger_uj:        # unsigned：x == UINT_MAX 时为假
        cmpl    $-1, %edi
        setne   %al
        retq
_Z11times2_div2i:             # int：直接返回 x
        movl    %edi, %eax
        retq
_Z13times2_div2_uj:           # unsigned：要丢掉回绕掉的最高位
        movl    %edi, %eax
        andl    $2147483647, %eax
        retq
```

`int` 版本里，`x + 1 > x` 被化简为 `true`，`x * 2 / 2` 被化简为 `x`，因为只有不溢出的执行才有定义。`unsigned` 版本必须保留回绕语义，多出了真正的比较和掩码。加上 `-fwrapv`（让有符号溢出按补码回绕）后，`next_is_bigger` 变成和 `x != INT_MAX` 等价的比较。

这种化简会让同一个程序在不同优化级别下给出不同结果：

```cpp run title="ovfrun.cpp" ub
#include <climits>
#include <cstdio>
int main(int argc, char**) {
  int x = INT_MAX - 1 + argc;   // 运行时才知道的 INT_MAX
  std::printf("%d\n", x + 1 > x);
}
```

本机 `-O0` 输出 0（硬件加法回绕成 `INT_MIN`），`-O2` 输出 1。UBSan 报告 `signed integer overflow: 2147483647 + 1 cannot be represented in type 'int'`。所以先算 `x + 1` 再判断它是否变小的溢出检查不起作用，应该在运算前比较，或者使用后文的 `ckd_add`。

浮点类型也受 [[expr.pre#4]] 约束，但符合 IEEE 754 的类型有 ±∞ 和 NaN，溢出的结果仍在类型的值里，因此不是 UB。按 [[expr.pre]] 的注 4，这时算术表达式唯一的 UB 是除以零，后文再讲。

## 除法、取余和移位

### 除法向零截断

```cpp run title="div.cpp" ok
#include <cstdio>
int floor_div(int a, int b) {           // 向负无穷取整
  int q = a / b, r = a % b;
  return (r != 0 && (r < 0) != (b < 0)) ? q - 1 : q;
}
int main() {
  std::printf("%d %d\n", 7 / 2, 7 % 2);       // 3 1
  std::printf("%d %d\n", -7 / 2, -7 % 2);     // -3 -1
  std::printf("%d %d\n", 7 / -2, 7 % -2);     // -3 1
  std::printf("%d %d\n", -7 >> 1, floor_div(-7, 2));  // -4 -4
  int n = -3;
  std::printf("%d\n", n % 2 == 1);            // 0：负奇数 % 2 是 -1
}
```

整数除法得到代数商并丢弃小数部分，也就是向零截断；`%` 由恒等式 `(a/b)*b + a%b == a` 定义（[[expr.mul#4]]）。两者合起来，余数要么为零，要么与被除数同号。判断奇数要写 `n % 2 != 0`；需要向下取整的除法或非负的模，要像上面的 `floor_div` 那样自己修正。

[[expr.mul#4]] 还规定了两种 UB：除数为零，以及商不能用结果类型表示。后者对二进制补码的 `int` 只有 `INT_MIN / -1` 一种情况，`INT_MIN % -1` 也一并是 UB。本机 arm64 上运行 `INT_MIN / -1` 得到 `INT_MIN`，不报错；x86-64 的 `idiv` 指令对此会触发硬件异常，在 Linux 上表现为 `SIGFPE`。更多细节见 [[expr.mul]] 的页面。

### 移位

```cpp run title="shift.cpp" ok
#include <cstdint>
#include <cstdio>
int main() {
  std::printf("%d\n", 1 << 31);          // C++20 起定义：-2147483648
  std::printf("%d\n", -1 << 3);          // C++20 起定义：-8
  std::printf("%d\n", -9 >> 1);          // -5：向负无穷取整
  std::uint8_t b = 0x81;
  std::printf("%d\n", b << 8);           // 33024：b 先提升为 int
}
```

移位不使用寻常算术转换：两个操作数各自做整型提升，结果类型是提升后的左操作数的类型（[[expr.shift#1]]）。所以 `uint8_t` 左移 8 位不会丢位；`1 << 40` 是 `int` 的移位，移位量超过了宽度，是 UB，要写成 `1LL << 40`。

C++20 起，移位的值完全按数学定义（[[expr.shift#2]]、[[expr.shift#3]]）：

- `E1 << E2` 是与 E1×2<sup>E2</sup> 模 2<sup>N</sup> 同余的值，N 是结果类型的宽度。所以 `1 << 31` 等于 `INT_MIN`，`-1 << 3` 等于 -8，都有定义。
- `E1 >> E2` 是 E1/2<sup>E2</sup> 向负无穷取整，对负数就是算术右移。

在此之前，左移负数是 UB，右移负数的结果由实现定义。本机 Clang 23 在 `-std=c++17` 下对 `-1 << 3` 仍然给出 `-Wshift-negative-value` 警告，在 `-std=c++2c` 下不再警告。

剩下的 UB 只与移位量有关：右操作数为负，或者不小于提升后左操作数的宽度（[[expr.shift#1]]）。

```cpp run title="shiftub.cpp" ub
#include <cstdint>
#include <cstdio>
int main(int argc, char**) {
  int n = 31 + argc;                     // 32
  std::uint32_t one = 1;
  std::printf("%u\n", one << n);         // UB：移位量等于宽度
  std::printf("%d\n", 1 >> -argc);       // UB：移位量为负
}
```

```text
shiftub.cpp:6:27: runtime error: shift exponent 32 is too large for 32-bit type 'std::uint32_t' (aka 'unsigned int')
shiftub.cpp:7:25: runtime error: shift exponent -1 is negative
```

不开 UBSan 时，本机第一行打印 1 而不是 0：arm64 和 x86-64 的移位指令都只取移位量的低 5 位，`1u << 32` 实际执行的是 `1u << 0`。这就是这种移位被定为 UB 的原因。需要按变量移位时，先检查 `n < 32`，或者用 `<bit>` 的 `std::rotl`、`std::rotr`，它们对任意移位量都有定义。

## 花括号初始化拒绝窄化

```cpp error
#include <cstdint>
#include <vector>
void f(double d, int i, long long ll) {
  int a = d;                    // OK：隐式截断
  int b{d};                     // error: 浮点到整数
  float c{d};                   // error: double 到 float，d 不是常量
  float c2{0.1};                // OK：常量，有限且不溢出（会舍入）
  std::int8_t e{i};             // error: int 到 int8_t
  std::int8_t e2{100};          // OK：常量且放得下
  std::int8_t e3{200};          // error: 常量但放不下
  unsigned u{-1};               // error
  double g{ll};                 // error: 整数到浮点
  double g2{1LL << 53};         // OK：常量，能精确往返
  std::vector<int> v{1, 2, d};  // error: 列表元素也检查
}
```

前面几节的转换在 `=` 初始化、赋值、函数传参时都会静默发生。列表初始化（`T x{...}`、`T x = {...}`）是例外：如果某个元素需要**窄化转换**（[[g:narrowing-conversion|narrowing conversion]]），程序非良构（[[dcl.init.list#3.9]]）。

窄化转换由 [[dcl.init.list#7]] 定义，大致是可能丢失信息的隐式转换：

| 转换 | 何时是窄化 |
|---|---|
| 浮点 → 整数 | 总是 |
| 浮点 → 等级更低的浮点 | 源不是常量表达式，或者常量的转换溢出 |
| 整数 → 浮点 | 源不是常量表达式，或者常量的值不能精确往返 |
| 整数 → 放不下全部值的整数 | 源不是常量表达式，或者常量提升后的值放不下 |
| 指针 → `bool` | 总是 |

常量的例外看的是实际的值：`int8_t e2{100}` 合法，`int8_t e3{200}` 非良构。`float c2{0.1}` 合法，因为常量转换只是舍入而没有溢出。

`int a = d;` 这样的截断，本机 Clang 23 在 `-Wall -Wextra` 下没有任何警告，要加 `-Wconversion`（其中的 `-Wfloat-conversion`）才会提示。在新代码中用花括号初始化算术变量，能把这一类错误变成编译错误。

## 安全的替代工具

前面的问题都有标准库的解法，它们的共同点是按数学值计算，而不是按 C 的转换规则：

```cpp run title="safe.cpp" ok
#include <climits>
#include <cstdint>
#include <cstdio>
#include <numeric>
#include <stdckdint.h>
#include <utility>
int main() {
  std::printf("%d %d\n", -1 < 1u, std::cmp_less(-1, 1u));  // 0 1
  std::printf("%d %d\n", std::in_range<std::uint8_t>(300),
                         std::in_range<std::uint8_t>(255)); // 0 1

  std::printf("%d\n", std::saturating_add(INT_MAX, 1));     // 2147483647
  std::printf("%u\n", std::saturating_sub(2u, 5u));         // 0
  std::printf("%d\n", std::saturating_cast<std::int8_t>(300)); // 127

  int r;
  if (ckd_mul(&r, 65535, 65535))   // 溢出时返回 true
    std::puts("overflow");
}
```

| 工具 | 头文件 | 版本 | 作用 |
|---|---|---|---|
| `std::cmp_equal`、`cmp_less` 等 6 个 | `<utility>` | C++20 | 按数学值比较两个整数，不受符号影响（[[utility.intcmp]]） |
| `std::in_range<R>(t)` | `<utility>` | C++20 | `t` 的值能否用 `R` 表示 |
| `std::saturating_add`、`_sub`、`_mul`、`_div` | `<numeric>` | C++26 | 越界时钳制到最大或最小值（[[numeric.sat.func]]） |
| `std::saturating_cast<R>(t)` | `<numeric>` | C++26 | 越界时钳制的整数转换（[[numeric.sat.cast]]） |
| `ckd_add`、`ckd_sub`、`ckd_mul` | `<stdckdint.h>` | C++26 | 按数学值计算，结果取模写回，返回是否溢出（[[numerics.c.ckdint]]） |

几个容易忽略的细节：

- 比较函数来自 [[P0586R2]]。它们只接受有符号或无符号整数类型，`char`、`bool`、`char8_t` 等字符类型不行（[[utility.intcmp#11]]），`std::cmp_less('a', 1)` 编译失败。
- 饱和函数来自 [[P0543R3]]，提案里的名字是 `add_sat`、`saturate_cast` 等，当前草案改成了 `saturating_add`、`saturating_cast`，本机 libc++ 提供的也是新名字。它们的两个形参类型相同，不做整型提升：`saturating_add<std::int8_t>(100, 100)` 是 127。详见 [[numeric.sat]] 的页面。
- `ckd_add` 等是 C23 的类型泛型宏在 C++ 中的对应物，名字在全局命名空间，三个操作数的类型彼此独立，不做寻常算术转换。详见 [[numerics.c]] 的页面。

## `size_t`、`ptrdiff_t` 与 `ssize`

标准库的大小用 `std::size_t`（无符号），两个指针或迭代器之差用 `std::ptrdiff_t`（有符号）。混用它们就回到了开头的问题：

```cpp
for (std::size_t i = v.size() - 1; i >= 0; --i) { }  // 死循环：i >= 0 恒真
for (int i = 0; i < v.size(); ++i) { }               // -Wsign-compare
```

本机 Clang 23 在 `-Wall -Wextra` 下只对第二行给出 `-Wsign-compare`，第一行的死循环没有警告。两种常见的改法：

```cpp run title="ssize.cpp" ok
#include <cstddef>
#include <cstdio>
#include <iterator>
#include <type_traits>
#include <vector>
int main() {
  std::vector<int> v{1, 2, 3};
  static_assert(std::is_same_v<decltype(std::ssize(v)), std::ptrdiff_t>);
  static_assert(std::is_same_v<decltype(3uz), std::size_t>);

  for (auto i = std::ssize(v) - 1; i >= 0; --i)   // 倒序，i 是有符号的
    std::printf("%d ", v[i]);
  for (std::size_t i = v.size(); i-- > 0; )        // 无符号：先比较再减
    std::printf("%d ", v[i]);
  std::puts("");
  for (auto i = 0uz; i < v.size(); ++i) { }        // uz：类型与 size() 一致
}
```

- C++20 的 `std::ssize(c)`（[[P1227R2]]）返回有符号的大小，类型是 `ptrdiff_t` 与 `c.size()` 对应的有符号类型中较宽的那个。
- C++23 的字面量后缀 `uz` 和 `z`（[[P0330R8]]）分别得到 `std::size_t` 和它对应的有符号类型，`auto i = 0uz` 不再与 `size()` 比较时混用符号。

## 浮点：标准保证了什么

标准对浮点的要求很少。`float`、`double`、`long double` 的值集依次包含，精度依次不低；除此之外，它们的表示和运算精度都由实现定义（[[basic.fundamental#12]]）。标准没有要求 IEEE 754（标准里写作 ISO/IEC 60559）。

实际的平台几乎都用 IEEE 754。程序可以通过 `std::numeric_limits<T>::is_iec559` 检查（[[numeric.limits.members#53]]），它为 `true` 时，`has_infinity`、`has_quiet_NaN` 等也必须为 `true`。依赖 IEEE 语义的代码可以写一行 `static_assert`：

```cpp run title="fp.cpp" ok
#include <bit>
#include <cfloat>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <limits>
int main() {
  static_assert(std::numeric_limits<double>::is_iec559);
  std::printf("%d\n", FLT_EVAL_METHOD);                       // 0
  std::printf("%#x\n", std::bit_cast<std::uint32_t>(1.0f));   // 0x3f800000
  std::printf("%#x\n", std::bit_cast<std::uint32_t>(-0.0f));  // 0x80000000

  double nz = -0.0;
  std::printf("%d %d\n", nz == 0.0, std::signbit(nz));        // 1 1

  double nan = std::numeric_limits<double>::quiet_NaN();
  std::printf("%d %d %d %d\n", nan == nan, nan != nan,
              nan < 1.0, nan >= 1.0);                          // 0 1 0 0
  std::printf("%.17g\n", 0.1 + 0.2);                           // 0.30000000000000004
}
```

`std::bit_cast<To>(from)`（C++20，[[P0476R2]]）把一个对象的位原样解释成另一个同样大小的可平凡复制类型（[[bit.cast]]），是查看浮点表示的正确方法；用 `reinterpret_cast` 或 `union` 读另一个类型的成员是 UB，见 [[topics/type-punning]]。上面的输出显示 `1.0f` 的 IEEE binary32 编码是 0x3f800000，`-0.0f` 只有符号位为 1。

### 超额精度与 `FLT_EVAL_METHOD`

[[expr.pre#6]] 允许浮点操作数和中间结果以比类型更高的精度和范围表示，类型不变；只有强制转换和赋值必须丢掉多余的精度。这是为 x87 的 80 位寄存器准备的。`<cfloat>` 的 `FLT_EVAL_METHOD`（[[cfloat.syn]]）报告实现的做法：0 表示按类型本身的精度计算。本机 arm64 是 0，现代 x86-64 默认使用 SSE2，通常也是 0；32 位 x86 使用 x87 时通常是 2，同一个表达式在两种平台上可能得到不同的结果。

把 `a * b + c` 融合成一条 FMA 指令也会改变舍入结果。Clang 用 `-ffp-contract=` 控制是否这样做，详见 [[expr.pre]] 的页面。

## NaN 与 -0.0

IEEE 754 的两个特殊值让浮点比较不再是全序：

- NaN 与任何值（包括自己）都无序：`==`、`<`、`>=` 都为假，只有 `!=` 为真。`x != x` 是判断 NaN 的传统写法，`std::isnan(x)` 更清楚。
- `-0.0 == 0.0` 为真，但两者的位不同，`std::signbit` 能区分，`1.0 / x` 在 IEEE 下得到的 ±∞ 也不同。

NaN 的这个性质会破坏标准算法的前提。`std::sort` 要求比较函数是严格弱序，含 NaN 的 `double` 序列用 `<` 排序违反这个前置条件，行为未定义。需要对任意浮点值排序时，用 C++20 的 `std::strong_order`，它给出 IEEE 754 的 totalOrder 全序，`-0.0` 排在 `0.0` 前，NaN 排在两端：

```cpp run title="total-order.cpp" ok
#include <algorithm>
#include <cmath>
#include <compare>
#include <cstdio>
#include <vector>
int main() {
  std::vector<double> v{3.0, NAN, 1.0, -0.0, 0.0, -INFINITY};
  std::ranges::sort(v, [](double a, double b) {
    return std::strong_order(a, b) < 0;
  });
  for (double d : v) std::printf("%g ", d);   // -inf -0 0 1 3 nan
}
```

!!! pitfall "IEEE 754 下除以零也是 UB"
    [[expr.mul#4]] 规定除数为零是 UB，不区分整数和浮点。IEEE 754 规定 `1.0 / 0.0` 得 +∞，按标准它仍是 UB；[[expr.pre]] 的注 4 明确说，对 IEEE 类型这是算术表达式唯一的 UB。本机运行得到 `inf`，`-fsanitize=undefined` 不报告，加 `-fsanitize=float-divide-by-zero` 才报 `division by zero`；`constexpr double x = 1.0 / 0.0;` 则被拒绝。需要无穷大时用 `std::numeric_limits<double>::infinity()`。

## 浮点与整数之间的转换

整数之间的转换总是取模，浮点到整数却不是：

```cpp run title="f2i.cpp" ub
#include <cstdio>
int main(int argc, char**) {
  double big = 3e9 * argc;
  double neg = -1.0 * argc;
  std::printf("%d\n", (int)big);        // UB：3e9 超出 int
  std::printf("%u\n", (unsigned)neg);   // UB：-1 超出 unsigned
  std::printf("%d\n", (int)-2.7);       // -2：向零截断，OK
}
```

浮点值转换成整数时先截断小数部分；截断后的值不能用目标类型表示，行为未定义（[[conv.fpint#1]]）。`(unsigned)-1.0` 也在其中：-1 不在 `unsigned` 的范围内，这里没有整数转换那样的取模。截断后在范围内的值没有问题，`(unsigned)-0.5` 截断为 0，合法。

本机 arm64 不开 sanitizer 时输出 2147483647 和 0，因为 `fcvtzs`、`fcvtzu` 指令会饱和；x86-64 的 `cvttsd2si` 对越界值给出 0x80000000。规则定为 UB，编译器就能直接使用硬件指令。`-fsanitize=float-cast-overflow`（包含在 `undefined` 中）报告：

```text
f2i.cpp:5:28: runtime error: 3e+09 is outside the range of representable values of type 'int'
f2i.cpp:6:33: runtime error: -1 is outside the range of representable values of type 'unsigned int'
```

反方向，整数转换成浮点时，值在范围内但不能精确表示，结果是相邻两个可表示值之一，选哪个由实现定义（[[conv.fpint#2]]）。`float f = 16777217;` 得到 16777216 或 16777218，常见的就近舍入得到前者。浮点之间从高精度转换到低精度遵循同样的规则（[[conv.double#2]]）。这些转换的其余细节见 [[conv]] 的页面。

## `-ffast-math`

`-ffast-math` 让编译器放弃 IEEE 754 的若干保证，以换取重排和向量化的自由。其中的 `-ffinite-math-only` 允许编译器假设没有 NaN 和无穷大，后果是检查 NaN 的代码失效：

```cpp title="fast.cpp"
#include <cmath>
bool is_nan(double x)  { return std::isnan(x); }
bool self_ne(double x) { return x != x; }
```

本机 Clang 23 加 `-O2 -ffast-math` 时，这两个函数都被编译成直接返回 0，传入 NaN 也一样，而且没有任何警告。另一个组成部分 `-fassociative-math` 允许按结合律重排浮点加法，求和结果会随优化而变化。

这个选项作用于整个翻译单元，并且会改变 `__FAST_MATH__` 等预定义宏。只在确认代码不依赖 NaN、无穷大、带符号零和精确舍入时使用；需要检查输入是否有 NaN 的代码，应放在不加这个选项编译的文件里。

## 编译期的浮点

常量求值不允许 UB（[[expr.const.core#2.8]]），这条规则把前面的越界情形都变成了编译错误：除以零、`INT_MIN / -1`、有符号溢出、越界移位、越界的浮点转整数。

浮点还有一条额外的规则。当前草案的 [[expr.const.core#2.9]] 规定，下面三种算术表达式不是核心常量表达式，尽管它们在 IEEE 754 下有确定的结果：

- 所有操作数都是有限值，结果却不是有限值（溢出到 ∞）；
- 有操作数是 signaling NaN；
- 没有操作数是 NaN，结果却是 NaN（如 `inf - inf`）。

换句话说，已有的 ∞ 和 quiet NaN 可以在编译期参与运算并传播，但不能凭空产生。

```cpp
#include <limits>
using L = std::numeric_limits<double>;
constexpr double inf  = L::infinity();       // OK
constexpr double nan  = L::quiet_NaN();      // OK
constexpr double inf2 = inf * 2;             // OK：操作数已是无穷
constexpr double nan2 = nan + 1;             // OK：传播 NaN（Clang 拒绝）
constexpr double tiny = L::min() / L::max(); // OK：下溢舍入为 0
constexpr double oflo = L::max() * 2;        // error: 有限操作数得到 ∞（Clang 接受）
constexpr double bad  = inf - inf;           // error: 无 NaN 操作数得到 NaN
constexpr int    trunc = (int)1e10;          // error: 转换后放不下，UB
static_assert(0.1 + 0.2 != 0.3);             // OK：编译期同样按 double 舍入
```

这段代码没有标判定，因为本机 Clang 23 在两处与当前草案不同：它拒绝 `nan2`，把产生 NaN 的运算一律视为非常量；又接受 `oflo`，允许常量求值溢出到 ∞。其余各行的行为与草案一致。这条规则是较新的措辞，写编译期浮点代码时不要依赖这些边界情况。

编译期的浮点运算按类型本身的精度舍入，`0.1 + 0.2 != 0.3` 在编译期同样成立。但如果运行时有超额精度或开了 `-ffast-math`，同一个表达式在编译期和运行时可能得到不同的结果。

## 扩展浮点类型 {{c++23}}

C++23 的 [[P1467R9]] 允许实现提供**扩展浮点类型**（[[g:extended-floating-point-type|extended floating-point type]]），并为常见格式规定了 `<stdfloat>` 中的标准名称（[[basic.extended.fp]]）：`std::float16_t`、`std::float32_t`、`std::float64_t`、`std::float128_t` 对应 IEEE 的 binary16/32/64/128，`std::bfloat16_t` 是机器学习常用的 8 位精度格式。它们全部是可选的，用 `__STDCPP_FLOAT16_T__` 等宏检测。

这些类型的转换和运算规则建立在**浮点转换等级**（[[g:floating-point-conversion-rank|floating-point conversion rank]]，[[conv.rank#2]]）上：值集是另一个类型真子集的类型等级更低；值集相同的类型等级相同，再用子等级区分，`std::floatN_t` 的子等级高于同等级的标准类型（[[conv.rank#3]]）。由此得出：

- 隐式转换只能到等级不低于源的类型（[[conv.double#1]]）。标准类型之间为了兼容 C 例外，`double` 仍可隐式转换为 `float`。
- 两个浮点操作数取等级高的类型；等级相同取子等级高的；等级不可比较时非良构（[[expr.arith.conv#1.4]]）。

```cpp
#include <stdfloat>
std::float16_t a = 1.0f16;                           // OK
std::float16_t b = 1.0;                              // error: double → float16_t 等级降低
std::float16_t c = static_cast<std::float16_t>(1.0); // OK：显式转换
auto d = std::float16_t(1) + 1.0f;                   // float
auto e = std::float32_t(1) + 1.0f;                   // std::float32_t：等级相同，子等级更高
auto f = std::bfloat16_t(1) + std::float16_t(1);     // error: 等级不可比较
```

这段代码没有标判定：本机 libc++ 没有提供 `<stdfloat>`，Clang 也没有定义 `__STDCPP_FLOAT16_T__` 等宏，无法在本地验证，结论直接来自上面引用的条文。`bfloat16` 的范围比 binary16 大、精度比它低，两者的值集互不包含，所以等级不可比较。

!!! impl "Clang 的 `_Float16` 不是扩展浮点类型"
    本机 Clang 23 支持 C 的 `_Float16`，但没有把它定义为标准意义上的扩展浮点类型（[[basic.fundamental#12]] 注 8 允许这样做）。它不遵守上面的规则：`_Float16 h = 1.0;` 能编译，`h + 1.0f` 的类型是 `float`。

## 常见误解

!!! pitfall "用无符号类型表示不会为负的量更安全"
    无符号类型不会溢出，但 `a - b` 在 `a < b` 时静默回绕成一个巨大的正数，`i >= 0` 恒真，与有符号值比较时对方也会被转换。下标和计数用有符号类型、只在与 `size()` 交互时转换，更不容易出错；需要位运算和取模语义时才用无符号类型。

!!! pitfall "`-fwrapv` 让有符号溢出合法"
    `-fwrapv` 让 Clang 和 GCC 按补码回绕，但程序按标准仍然有 UB，换一个编译器或去掉这个选项就会出问题。它适合给既有代码兜底，不能代替正确的溢出检查。

!!! pitfall "`std::abs` 的结果总是非负"
    整数版本的 `std::abs` 沿用 C 库的语义（[[c.math.abs#2]]），结果不能表示时行为未定义，所以 `std::abs(INT_MIN)` 是 UB。

## 思考题

!!! question "思考题 1"
    设 `unsigned short a = 1; int b = -2;`。`a + b > 0` 的值是什么？把 `a` 的类型换成 `unsigned int` 呢？

<details markdown="1">
<summary>答案</summary>

第一种情况为假。`unsigned short` 先提升为 `int`（[[conv.prom#2]]），两边都是 `int`，`1 + (-2) == -1`，`-1 > 0` 为假。

换成 `unsigned int` 后为真。`unsigned int` 与 `int` 等级相同，按 [[expr.arith.conv#1.5.3.1]] 公共类型是 `unsigned int`，`b` 转换成 4294967294，和是 4294967295，大于 0。同一个表达式的结果取决于操作数是否窄于 `int`。
</details>

!!! question "思考题 2"
    `std::int8_t x = 127; ++x;` 是 UB 吗？`int x = INT_MAX; ++x;` 呢？

<details markdown="1">
<summary>答案</summary>

第一个不是 UB。`++x` 等价于 `x += 1`，即 `x = x + 1`：`x` 先提升为 `int`，`127 + 1 == 128` 在 `int` 里没有溢出；赋值时 128 转换回 `int8_t`，按 [[conv.integral#3]] 取模得到 -128。C++20 起这个结果是确定的。

第二个是 UB。加法在 `int` 里进行，数学结果 2<sup>31</sup> 不能用 `int` 表示（[[expr.pre#4]]）。
</details>

!!! question "思考题 3"
    `double d = 4294967295.0;`。`(unsigned)d` 和 `(int)d` 中哪个有定义？`(unsigned)(long long)d` 呢？

<details markdown="1">
<summary>答案</summary>

`(unsigned)d` 有定义，结果是 4294967295，在 32 位 `unsigned` 的范围内。`(int)d` 是 UB，截断后的值超出 `int` 的范围（[[conv.fpint#1]]）。

`(unsigned)(long long)d` 有定义：浮点转 `long long` 在范围内，之后是整数之间的转换，总是取模。先转成足够宽的整数再转窄，是避开浮点转整数 UB 的常用办法，前提是第一步不越界。
</details>

## 小结

| 情形 | 判定 | 依据 |
|---|---|---|
| 窄整数参与运算 | 先提升为 `int`（可能因此有符号溢出） | [[conv.prom]] |
| 有符号与无符号混用 | 通常转为无符号，结果依赖平台 | [[expr.arith.conv]] |
| 整数转换越界 | 取模，C++20 起有定义 | [[conv.integral]] |
| 有符号算术溢出 | {{ub}} | [[expr.pre#4]] |
| 无符号算术越界 | 取模回绕 | [[basic.fundamental#2]] |
| 除以零、`INT_MIN / -1` | {{ub}}（浮点除以零也是） | [[expr.mul#4]] |
| 移位量为负或不小于宽度 | {{ub}} | [[expr.shift#1]] |
| 左移负数、右移负数 | C++20 起有定义 | [[expr.shift]] |
| 花括号初始化中的窄化 | {{ill-formed}} | [[dcl.init.list#3.9]] |
| 浮点转整数越界 | {{ub}} | [[conv.fpint#1]] |
| 整数转浮点不能精确表示 | 相邻值之一，{{impl}} | [[conv.fpint#2]] |
| 常量求值中凭空产生 ∞ 或 NaN | 不是常量表达式 | [[expr.const.core#2.9]] |
