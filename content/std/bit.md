---
title: 位操作
summary: 头文件 <bit>：用 bit_cast 合法地查看对象的比特，用 byteswap 翻转字节序，以及只接受无符号整数的 2 的幂、移位、循环移位、位计数、位置换函数和 endian 枚举。
status: draft
covers: *
papers: P0476R2, P1272R4, P0553R4, P0556R3, P1956R1, P0463R1, P2795R5, P3104
related: bitset, stdbit.h.syn, basic.types, class.prop, basic.indet, basic.lval, expr.const.core, intro.object, expr.reinterpret.cast, class.union, expr.shift, basic.fundamental
tags: 标准库, bit_cast, 类型双关, 位运算, 字节序
updated: 2026-10-19
---

!!! tldr
    - 想把 `float` 的比特当作 `uint32_t` 来看，`reinterpret_cast` 和联合体都是 UB，`std::bit_cast` 是合法且可以在编译期使用的做法。
    - `bit_cast` 要求两个类型大小相同、都平凡可复制。源对象的填充位落进非字节类型的结果里是 UB，落进 `unsigned char` 或 `std::byte` 里只是不确定值。
    - 2 的幂、循环移位、位计数、位置换函数只接受无符号整数类型，`bool`、`char`、有符号整数都会得到"没有匹配的函数"。
    - 这些函数对输入 0 和任意移位量都有定义，这是它们与 `__builtin_clz` 和内建移位运算符的主要区别。唯一的例外是 `bit_ceil` 的结果必须放得下。
    - `std::endian::native` 在混合字节序平台上既不等于 `little` 也不等于 `big`，判断字节序时要把这种情况排除掉。

整个 `<bit>` 头文件都是 freestanding 的（[bit.syn] 第一行注释 `// all freestanding`）：它不需要内存分配、异常或 I/O，内核和嵌入式代码也能用。几乎所有函数都是 `constexpr` 和 `noexcept`。

## 用 `bit_cast` 查看对象的比特 [bit.cast]

### 类型双关的三种旧写法

底层代码常要把一个 `float` 的比特当作整数来处理，例如解析浮点格式、计算哈希、做序列化。C++20 之前常见三种写法，只有第三种合法：

| 写法 | 结论 |
|---|---|
| `*reinterpret_cast<uint32_t*>(&f)` | {{ub}}：`float` 对象不能经 `uint32_t` 类型的 glvalue 访问（[[basic.lval#11]]），即违反严格别名规则 |
| `union { float f; uint32_t u; }`，写 `f` 读 `u` | {{ub}}：读取了非活跃成员（[[class.union]]）。GCC 和 Clang 作为扩展支持它，但在常量求值中会拒绝 |
| `std::memcpy(&u, &f, 4)` | 合法：平凡可复制类型的对象表示可以复制到另一个同类型对象中（[[basic.types]]） |

```cpp run title="type-punning-ub.cpp" ub
#include <cstdint>
#include <cstdio>
float f = 1.0f;
int main() {
    std::uint32_t u = *reinterpret_cast<std::uint32_t*>(&f);   // UB: 严格别名
    std::printf("%x\n", u);       // 本机打印 3f800000，但没有任何保证
}
```

`memcpy` 的写法正确，但要先有一个目标对象（所以目标类型必须能默认构造），而且不能用于常量求值。C++20 的 `bit_cast`（[[P0476R2]]）把"复制进一个新对象"包装成一个返回值的 `constexpr` 函数：

```cpp run title="bit-cast-basic.cpp" ok
#include <array>
#include <bit>
#include <cstdint>
#include <cstdio>
#include <cstring>

constexpr std::uint32_t bits_of(float f) { return std::bit_cast<std::uint32_t>(f); }
static_assert(bits_of(1.0f) == 0x3f80'0000);
static_assert(std::bit_cast<float>(0x4049'0fdbu) > 3.14f);

struct RGBA { std::uint8_t r, g, b, a; };
static_assert(std::bit_cast<std::array<std::uint8_t, 4>>(RGBA{1, 2, 3, 4})[2] == 3);

std::uint32_t via_memcpy(float f) {            // C++20 之前的标准写法
    std::uint32_t u;
    std::memcpy(&u, &f, sizeof u);
    return u;
}

int main() {
    float f = -0.0f;
    std::printf("%08x %08x\n", std::bit_cast<std::uint32_t>(f), via_memcpy(f));  // 80000000 80000000
}
```

### 约束：大小相同，双方平凡可复制（¶1）

¶1 `bit_cast<To>(from)` 有三条约束：`sizeof(To) == sizeof(From)`，`To` 和 `From` 都是**平凡可复制类型**（[[g:trivially-copyable-type]]，[[class.prop]]），即可以用逐字节复制来复制的类型。这些是 *Constraints*：不满足时 `bit_cast` 不参与重载决议，报错是"没有匹配的函数"。

大小必须相等，`bit_cast` 不做截断也不做填充。想取 `double` 的低 32 位，先 `bit_cast<uint64_t>` 再移位。`To` 不需要能默认构造，这一点比 `memcpy` 好。

```cpp run title="bit-cast-size.cpp" error
#include <bit>
auto d = std::bit_cast<long>(1);   // error: sizeof(long) != sizeof(int)，没有匹配的函数
```

纯库代码写不出 `constexpr` 的 `bit_cast`：常量求值中既不能用 `reinterpret_cast`，也不能对不同类型的对象做 `memcpy`。所以三大实现都依靠编译器内建函数，libc++ 的函数体只有一行 `return __builtin_bit_cast(_ToType, __from);`。

### 结果的每一位从哪里来（¶3）

¶3 规定了返回值：一个新的 `To` 对象，结果**值表示**（[[g:value-representation]]，参与表示值的那些位）的每一位等于 `from` 的**对象表示**（[[g:object-representation]]，对象占据的全部字节，包括填充）的对应位。注意两边不对称：读的是源对象的全部位，写的是目标的值位。目标自己的填充位是未指定的。

¶3 还规定 `bit_cast` 在结果中隐式创建嵌套对象（[[intro.object]]，[[g:implicitly-create-objects]]）。例如 `To` 含有联合体成员时，哪个成员活跃，按隐式对象创建的规则选一个能让程序有定义行为的。

源对象里有些位本身没有确定的值，¶3 把它们带进结果后分两类：

- 结果中的一位是**不确定的**（indeterminate），如果它对应 `from` 的填充位，或者对应的位所在的最小对象不在生存期内、或具有不确定值（[[basic.indet]]）。
- 一位是**错误的**（erroneous），如果对应的位所在的最小对象具有**错误值**（[[g:erroneous-value]]）。C++26 起，未初始化的自动变量具有错误值，读取它是错误行为而不是 UB（[[P2795R5]]）。

对每个这样的位，取结果中包含它的最小对象 u：

- ¶3.1 u 是 `unsigned char`、`std::byte`，或者底层类型为 `unsigned char` 的 `char` 时，u 只是具有不确定值或错误值，不是 UB。这与 [[basic.indet]] 允许用字节类型搬运不确定值的规则一致。
- ¶3.2 否则，这一位不确定时行为未定义。
- ¶3.3 否则（这一位是错误的），这是错误行为（{{erroneous}}）。

最常见的不确定位来自结构体的填充。`struct P { char c; int i; };` 在常见 ABI 上 `c` 之后有 3 个填充字节：

```cpp run title="bit-cast-padding.cpp" error
#include <array>
#include <bit>
#include <cstdint>

struct P { char c; int i; };      // 典型 ABI 上 c 之后有 3 字节填充
static_assert(sizeof(P) == 8);

constexpr int first_byte() {
    auto bytes = std::bit_cast<std::array<unsigned char, sizeof(P)>>(P{1, 2});
    return bytes[0];              // OK：c 对应的字节有确定值
}
static_assert(first_byte() == 1);

constexpr int padding_byte() {
    auto bytes = std::bit_cast<std::array<unsigned char, sizeof(P)>>(P{1, 2});
    return bytes[1];              // 填充字节具有不确定值，读它不是常量表达式
}
static_assert(padding_byte() == 0);                          // error

constexpr auto u = std::bit_cast<std::uint64_t>(P{1, 2});    // error: ¶3.2，UB
```

转成 `array<unsigned char, 8>` 本身是合法的，填充对应的 3 个元素各自具有不确定值，只要不读它们就没事。转成 `uint64_t` 时，24 个不确定位落在一个 `uint64_t` 里，按 ¶3.2 是 UB。常量求值会严格检查这套规则，本机 Clang 23 对最后一行的说明是 *indeterminate value can only initialize an object of type 'unsigned char' or 'std::byte'*。

合法的那个 `bit_cast<array<unsigned char, 8>>(P{1, 2})` 也不能用来初始化 `constexpr` 变量，因为常量表达式的结果不能含有不确定值（[[expr.const]]）。所以上面把它放在 `constexpr` 函数的局部变量里。

### 何时能在编译期求值（¶2）

```cpp run title="bit-cast-constexpr.cpp" error
#include <bit>
#include <cstdint>

struct S { int* p; };
union U { int i; float f; };
int g;

constexpr auto a = std::bit_cast<std::uintptr_t>(&g);          // error: From 是指针类型
constexpr auto b = std::bit_cast<std::uintptr_t>(S{nullptr});  // error: S 有指针成员
constexpr auto c = std::bit_cast<int>(U{1});                   // error: From 是联合体
```

这三行在运行期都合法，只是不能在编译期求值。¶2 用 *Constant When* 元素（[[structure.specifications]]）规定：调用要成为常量子表达式，`To` 和 `From` 都不能具有 **constexpr 未知表示**（[[g:constexpr-unknown-representation]]）。按 [[expr.const.core#1]]，下列类型具有 constexpr 未知表示：联合体、`std::meta::info`、指针和成员指针、volatile 限定的类型、有引用类型非静态数据成员的类，以及某个基类或非静态成员具有 constexpr 未知表示的类型。

原因各不相同。常量求值器里的指针是"某个对象加一个偏移"这样的符号值，没有确定的地址比特，引用成员同理。联合体的活跃成员决定哪些位是值位，求值器无法逐位处理。volatile 访问本来就不能出现在常量表达式里。`std::meta::info` 是编译器内部的反射句柄，没有比特表示。

!!! pitfall "bit_cast 不是 reinterpret_cast 的另一种写法"
    `bit_cast` 总是按值返回一个新对象，从不产生指向原对象的别名。`bit_cast<Header>(buffer)` 要求 `buffer` 本身是一个大小为 `sizeof(Header)` 的对象（如 `std::array<std::byte, N>`）。传一个指针进去，重新解释的是指针本身的 8 个字节。想把一块已有内存当作 `T` 对象使用，应该用 `std::start_lifetime_as`（[[obj.lifetime]]）。

## 翻转字节序 `byteswap` [bit.byteswap] {{c++23}}

¶1–¶4 `byteswap(value)` 返回一个对象，其对象表示是 `value` 的对象表示按字节逆序排列的结果（[[P1272R4]]）。

它的约束与本页其余数值函数不同：*Constraints* 是 `T` 满足 `integral`，所以有符号整数和 `char` 都可以用；另有 *Mandates*：`T` 没有填充位（[[basic.types]]），否则逆序可能把填充位搬进值位。违反 *Mandates* 是非良构的，必须诊断。

因为规定写在对象表示层面，有符号数的结果也完全确定：`byteswap(int16_t{0x0102}) == 0x0201`。单字节类型上它是恒等函数。和 `endian` 一起，它就是网络字节序转换的全部工具：

```cpp
if constexpr (std::endian::native == std::endian::little) x = std::byteswap(x);
```

{{impl}} libc++ 对 `bool` 网开一面（源码注释说现有实现都接受它，而单字节的恒等变换不会搬动任何位），其余类型按大小分派到 `__builtin_bswap16/32/64/128`，编译为单条 `bswap`（x86）或 `rev`（ARM）指令。

## 只接受无符号整数的数值函数

除 `bit_cast`、`byteswap`、`shl`、`shr` 外，本页所有函数的 *Constraints* 都是"`T` 是无符号整数类型"（[[basic.fundamental]]，[[g:unsigned-integer-type]]）。`bool`、`char`、`char8_t`、`wchar_t`、有符号整数和枚举都不在其中：

```cpp run title="bit-unsigned-only.cpp" error
#include <bit>
auto a = std::popcount(-1);              // error: int 不是无符号整数类型
auto b = std::has_single_bit(true);      // error: bool 不是无符号整数类型
auto c = std::rotl('a', 1);              // error: char 也不是
```

排除有符号类型是有意的。对有符号数，最高位是符号位，"前导零的个数"这类问题的答案依赖于表示方式；而无符号整数的值与它的二进制位一一对应，这些函数只对值做运算，与内存布局无关。

### 2 的整数幂 [bit.pow.two]

这四个函数由 [[P0556R3]] 引入，[[P1956R1]] 把原名 `ispow2`、`ceil2`、`floor2`、`log2p1` 改成了现在的名字，强调它们是位操作而不是数学函数。

| 函数 | 段落 | 返回 | `x == 0` 时 |
|---|---|---|---|
| `has_single_bit(x)` | ¶1–2 | `x` 是否是 2 的整数幂，即恰有一位为 1 | `false` |
| `bit_ceil(x)` | ¶3–8 | 不小于 `x` 的最小的 2 的幂 | `1` |
| `bit_floor(x)` | ¶9–10 | 不大于 `x` 的最大的 2 的幂 | `0` |
| `bit_width(x)` | ¶11–12 | 表示 `x` 所需的位数，即 1 + ⌊log₂x⌋ | `0` |

`bit_width(x)` 等于 `numeric_limits<T>::digits - countl_zero(x)`。

`bit_ceil` 是唯一可能失败的：`bit_ceil(uint8_t{129})` 应该是 256，`uint8_t` 放不下。

!!! std
    Preconditions: N is representable as a value of type T.

    Remarks: A function call expression that violates the precondition in the Preconditions: element is not a core constant expression.

¶5 在运行期违反这条前置条件是 {{ub}}。¶8 规定在常量求值中，违反前置条件的调用不是核心常量表达式，所以编译器必须报错，`static_assert(bit_ceil(...))` 不会悄悄得到一个错误的答案。

```cpp run title="bit-ceil.cpp" error
#include <bit>
#include <cstdint>

static_assert(std::bit_ceil(5u) == 8u);
static_assert(std::bit_ceil(0u) == 1u);            // 0 的 bit_ceil 是 1
static_assert(std::bit_floor(0u) == 0u);
static_assert(std::bit_width(0u) == 0 && std::bit_width(8u) == 4);
static_assert(std::bit_ceil(std::uint8_t{128}) == 128);
constexpr auto x = std::bit_ceil(std::uint8_t{129});  // error: 256 无法用 uint8_t 表示
```

`bit_ceil` 因此没有标 `noexcept`，`bit_floor` 标了。标准库的惯例是：带前置条件的函数（窄契约）不标 `noexcept`，给实现留下在违反时抛异常来检查的余地。实现可以自行加上 `noexcept`，libc++ 就给 `bit_ceil` 加了。本机 libc++ 在非加固模式下 `bit_ceil(0x80000001u)` 返回 1，不做任何检查。

### 循环移位 `rotl`、`rotr` [bit.rotate]

¶1–¶7 令 N 为 `T` 的位数，r 为 `s % N`。`rotl(x, s)` 在 r 为 0 时返回 `x`，r 为正时返回 `(x << r) | (x >> (N - r))`，r 为负时返回 `rotr(x, -r)`。`rotr` 与之对称（[[P0553R4]]）。

- `s` 是 `int`，可以为负，负的左旋就是右旋。`%` 向零截断（[[expr.mul]]），所以 `-33 % 32 == -1`，`rotl(x, -33) == rotr(x, 1)`。
- `s` 任意大都合法。取模后移位量总在 (−N, N) 之内，r 为 0 时不做移位，避开了 `x >> N` 这个 UB（[[expr.shift]]）。

```cpp run title="bit-ops.cpp" ok
#include <bit>
#include <cstdint>

static_assert(std::rotl(std::uint8_t{0b1000'0001}, 1)  == 0b0000'0011);
static_assert(std::rotl(std::uint8_t{0b1000'0001}, -1) == 0b1100'0000);  // 负数 = 反方向
static_assert(std::rotr(std::uint8_t{0b0000'0011}, 9)  == 0b1000'0001);  // 9 % 8 == 1
static_assert(std::rotl(1u, -33) == std::rotr(1u, 1));                    // -33 % 32 == -1
static_assert(std::countl_zero(std::uint16_t{1}) == 15);
static_assert(std::countr_zero(0u) == 32 && std::countl_one(~0u) == 32);
static_assert(std::popcount(0xF0F0u) == 8);
static_assert(std::has_single_bit(64u) && !std::has_single_bit(0u));
static_assert(std::byteswap(std::uint32_t{0x12345678}) == 0x78563412);
static_assert(std::byteswap(std::int16_t{0x0102}) == 0x0201);            // byteswap 接受有符号数

int main() {}
```

### 位计数 [bit.count]

同样由 [[P0553R4]] 引入。N 为 `T` 的位数，返回类型都是 `int`：

| 函数 | 段落 | 返回 |
|---|---|---|
| `countl_zero(x)` | ¶2–3 | 从最高位起连续 0 的个数；`x == 0` 时为 N |
| `countl_one(x)` | ¶4–5 | 从最高位起连续 1 的个数；`x` 为最大值时为 N |
| `countr_zero(x)` | ¶6–7 | 从最低位起连续 0 的个数；`x == 0` 时为 N |
| `countr_one(x)` | ¶8–9 | 从最低位起连续 1 的个数；`x` 为最大值时为 N |
| `popcount(x)` | ¶10–11 | 值为 1 的位的个数 |

表中"为 N"的情形写在四条注里，注不是规范性的，但这些结果可以直接从 *Returns* 推出。输入为 0 时有定义，这是与 `__builtin_clz`、`__builtin_ctz` 最大的区别：后两者对 0 的结果未定义，x86 的 `BSR`、`BSF` 指令对 0 也不给出确定结果。标准函数要么用 `LZCNT`、`TZCNT` 这类对 0 返回位宽的指令，要么多一次分支。

### 移位 `shl`、`shr` [bit.shift]

这一对函数是新近加入工作草案的，本机 libc++ 尚未实现。它们解决内建移位运算符（[[expr.shift]]）的问题：移位量为负或不小于位宽时是 {{ub}}。

¶1 先在一个范围足够大的假想整数类型里算出数学结果 r，再 `static_cast<T>(r)` 转回 `T`，也就是按 2ⁿ 取模（[[conv.integral]]）。¶3 `shl(x, s)` 返回 x×2ˢ 向负无穷舍入的结果，¶5 `shr(x, s)` 返回 x×2⁻ˢ 向负无穷舍入的结果。¶2、¶4 的约束是 `T` 和 `S` 为有符号或无符号整数类型，与本节其余函数不同，它们接受有符号数。

于是 `s` 为负时自然变成反方向移位。`s` 超过位宽时，`shl` 的结果取模后是 0；`shr` 对非负数得 0，对负数得 −1，相当于算术右移。两个函数都没有前置条件。

### 位置换 [bit.permute]

四个函数是新近加入工作草案的（[[P3104]]），本机 libc++ 尚未提供，也没有对应的特性测试宏。¶1 定义了记号：N 是位数，αₙ 是 α 从低往高的第 n 位，σ(α, n) 是 α 最低 n 位中 1 的个数。

| 函数 | 段落 | 含义 | 对应指令 |
|---|---|---|---|
| `bit_reverse(x)` | ¶2–4 | 位序翻转，第 n 位移到第 N−1−n 位；翻转两次得到原值 | ARM `RBIT` |
| `bit_repeat(x, l)` | ¶5–10 | 以 `x` 的最低 `l` 位为图样，重复铺满 N 位；`bit_repeat(uint32_t{0xc}, 4) == 0xcccccccc` | 无 |
| `bit_compress(x, m)` | ¶11–13 | 把 `x` 中 `m` 为 1 的那些位依次收拢到低端 | x86 BMI2 `PEXT` |
| `bit_expand(x, m)` | ¶14–16 | 逆操作，把 `x` 的低位依次放到 `m` 为 1 的位置上 | x86 BMI2 `PDEP` |

¶12 的公式是 compress(x, m) = Σ mₙ·xₙ·2^σ(m,n)：只有 mₙ = 1 的位参与，它被放到第 σ(m, n) 位，也就是 m 中位于它下方的 1 的个数。例 2 给出 `bit_compress(0bABCD, 0b0101) == 0b00BD`，例 3 给出 `bit_expand(0bABCD, 0b0101) == 0b0C0D`。

`bit_repeat` 有前置条件 `l > 0`（¶6），并且与 `bit_ceil` 一样，违反它的调用不是核心常量表达式（¶9）。`l` 不小于 N 时没有问题，公式里 n mod l = n，结果就是 `x`。

在标准库实现之前，可以按 ¶12 的公式手写一个可移植的版本：

```cpp run title="bit-compress-manual.cpp" ok
#include <bit>
#include <cstdint>

// 按 [bit.permute]/12 的公式实现 PEXT 语义
constexpr std::uint32_t compress(std::uint32_t x, std::uint32_t m) {
    std::uint32_t r = 0;
    for (int k = 0; m != 0; m &= m - 1, ++k)        // 依次取出 m 中最低的 1；k 即 σ(m, n)
        r |= ((x >> std::countr_zero(m)) & 1u) << k;
    return r;
}
static_assert(compress(0b1010, 0b0101) == 0b00);   // B=0, D=0
static_assert(compress(0b1011, 0b0101) == 0b01);   // B=0, D=1
static_assert(compress(0xABCD'1234, 0x0000'FF00) == 0x12);

int main() {}
```

## 字节序 [bit.endian]

¶1 **大端**（[[g:big-endian]]）把最高有效字节放在最前面，**小端**（[[g:little-endian]]）把最低有效字节放在最前面。这一节描述执行环境中标量类型的字节序（[[P0463R1]]）。

`enum class endian { little, big, native };` 三个枚举值都是"见下文"，¶2 只规定它们之间的关系：

- 所有标量类型的大小都是 1 字节时（例如 `CHAR_BIT == 32`、`sizeof(long) == 1` 的某些 DSP），三个值相等，字节序问题不存在。
- 否则 `little != big`。所有标量类型都是大端时 `native == big`，都是小端时 `native == little`。
- 否则平台是**混合字节序**的（[[g:mixed-endian]]），`native` 既不等于 `big` 也不等于 `little`。

混合字节序确实存在：PDP-11 的 32 位整数是两个小端 16 位字按大端排列；有些 ARM 浮点格式中 `double` 的两半与整数的字序不同。"所有标量类型"包括浮点和指针，只要有一种的字节序与其他不同，`native` 就不能等于 `little` 或 `big`。

所以不要写 `native == little ? ... : ...`，默认不是小端就是大端。正确的做法是先排除第三种情况：

```cpp run title="endian.cpp" ok
#include <bit>
#include <cstdint>

constexpr std::uint32_t to_big(std::uint32_t x) {
    static_assert(std::endian::native == std::endian::big ||
                  std::endian::native == std::endian::little,
                  "mixed-endian platform not supported");
    if constexpr (std::endian::native == std::endian::little) return std::byteswap(x);
    else return x;
}
static_assert(to_big(0x01020304) == 0x04030201 || std::endian::native == std::endian::big);

int main() {}
```

这里用的是普通的 `static_assert`，没有写成 `if constexpr` 第三个分支里的 `static_assert(false)`。在非模板函数里，被弃置的分支照样会检查，`static_assert(false)` 会直接失败（[[stmt.if]]）。

{{impl}} libc++ 给 `little` 和 `big` 取了两个任意的不同值 `0xDEAD` 和 `0xFACE`，`native` 按目标平台取其一，否则取第三个值 `0xCAFE`。所有标量都是 1 字节的情况 libc++ 不支持。

## 历史与演进

!!! history
    - C++20：`bit_cast`（[[P0476R2]]）、`endian`（[[P0463R1]]，最初放在 `<type_traits>`，后移入 `<bit>`）、循环移位和位计数（[[P0553R4]]）、2 的幂函数（[[P0556R3]]，经 [[P1956R1]] 改名）。
    - C++23：`byteswap`（[[P1272R4]]）。
    - C++26：引入错误行为后（[[P2795R5]]），`bit_cast` 的 ¶3 增加了错误位的规则。`<stdbit.h>` 作为 C23 头文件进入 C++（[[stdbit.h.syn]]）。
    - C++23 之后的新措辞：`bit_cast` 的编译期限制改用核心语言的 constexpr 未知表示概念，以 *Constant When* 表述；新增 `shl`、`shr` 和位置换函数（[[P3104]]）。

## 常见误解

!!! pitfall "`reinterpret_cast` 之后读一下，结果一直是对的，所以没问题"
    UB 的程序可以碰巧输出预期的结果。优化器依据严格别名规则假设 `float*` 和 `uint32_t*` 不指向同一个对象，代码稍一变化就可能读到旧值。本机 Clang 23 `-O2` 把 `bit_cast`、`memcpy` 和 `reinterpret_cast` 三种写法都编译成同一条 `fmov` 指令，没有性能理由使用 UB 的写法。

!!! pitfall "`countl_zero(0)` 和 `__builtin_clz(0)` 一样是未定义的"
    标准函数对 0 有定义，返回位宽 N。只有编译器内建函数才对 0 未定义。

## 思考题

!!! question "思考题 1"
    `struct A { std::uint16_t a; std::uint8_t b; };`（`sizeof` 为 4）。`std::bit_cast<std::uint32_t>(A{1, 2})` 在运行期的行为是什么？`std::bit_cast<std::array<std::byte, 4>>(A{1, 2})` 呢？随后读取后者的 `[3]` 元素呢？

<details markdown="1">
<summary>答案</summary>

`A` 的最后 1 个字节是填充，不属于 `A` 的值表示。按 [bit.cast] ¶3，`uint32_t` 结果中对应的 8 位是不确定的；包含它们的最小对象是整个 `uint32_t`，不是字节类型，按 ¶3.2 行为未定义。

转成 `array<std::byte, 4>` 时，包含不确定位的最小对象是第 4 个 `std::byte` 元素，按 ¶3.1 它只是具有不确定值，`bit_cast` 本身没有问题。随后读取 `[3]` 得到不确定值，按 [[basic.indet]] 只有用它初始化另一个 `unsigned char` 或 `std::byte` 对象等少数情形不是 UB；拿它做比较或算术则是 UB。
</details>

!!! question "思考题 2"
    在一个 `char`、`short`、`int`、`long` 都是小端，但 `double` 的两个 32 位半字按大端排列的平台上，`std::endian::native` 等于什么？

<details markdown="1">
<summary>答案</summary>

既不等于 `endian::little` 也不等于 `endian::big`（[bit.endian] ¶2 最后一句），因为并非所有标量类型都是小端。`double` 是标量类型（[[basic.types]]），它的字节序也计入判断。此时 `little != big` 仍然成立，因为并非所有标量类型都只有 1 字节。
</details>

## 小结

| 函数 | 类型要求 | 前置条件与特殊规则 |
|---|---|---|
| `bit_cast<To>(from)` | 大小相等，双方平凡可复制 | 不确定位落在非字节对象上为 UB，错误位为 EB；双方都没有 constexpr 未知表示时才能在编译期求值 |
| `byteswap` | `integral`（含有符号）；无填充位 | 无 |
| `has_single_bit`、`bit_floor`、`bit_width` | 无符号整数 | 无；`x == 0` 有定义 |
| `bit_ceil` | 无符号整数 | 结果必须可表示，违反为 UB，常量求值中报错 |
| `shl`、`shr` | 有符号或无符号整数 | 无；负的或超大的移位量都有定义；libc++ 未实现 |
| `rotl`、`rotr` | 无符号整数 | 无；`s` 可为负、可任意大 |
| `countl_*`、`countr_*`、`popcount` | 无符号整数 | 无；`x == 0` 时 `countl_zero`、`countr_zero` 返回位宽 |
| `bit_reverse`、`bit_compress`、`bit_expand` | 无符号整数 | 无；libc++ 未实现 |
| `bit_repeat` | 无符号整数 | `l > 0`，常量求值中违反时报错；libc++ 未实现 |
| `endian` | | 全部标量为 1 字节时三值相等；混合字节序时 `native` 与两者都不等 |
