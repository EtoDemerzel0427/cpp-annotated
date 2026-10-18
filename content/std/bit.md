---
title: 位操作
summary: <bit>——bit_cast 按值表示逐位复制出新对象（取代 reinterpret_cast/union 类型双关），byteswap、2 的幂（has_single_bit/bit_ceil/bit_floor/bit_width）、移位 shl/shr、循环移位 rotl/rotr、计数 countl_zero/popcount 等、位置换 bit_reverse/bit_compress/bit_expand、endian；只接受无符号整数类型，整个头文件 freestanding
status: draft
covers: *
papers: P0476R2, P1272R4, P0553R4, P0556R3, P1956R1, P0463R1, P2795R5
related: bitset, stdbit.h.syn, basic.types, class.prop, basic.indet, basic.lval, expr.const.core, intro.object, expr.reinterpret.cast, class.union, expr.shift, basic.fundamental
tags: 标准库, bit_cast, 类型双关, 位运算, 字节序
updated: 2026-10-18
---

`<bit>` 把一批过去只能靠编译器内建函数（`__builtin_clz`、`__builtin_popcount`、`_byteswap_ulong`……）或手写位技巧实现的操作，变成了**可移植、`constexpr`、类型安全**的函数模板。它解决两类截然不同的问题：

1. **对象表示层面**：`bit_cast` 和 `byteswap`——把一个对象的比特原样搬到另一种类型里，或者把整数的字节倒过来。这一部分牵涉核心语言最微妙的规则：对象表示与值表示（[[basic.types]]）、平凡可复制（[[class.prop]]）、不确定值与错误值（[[basic.indet]]）、严格别名（[[basic.lval]]）、常量求值（[[expr.const.core]]）。
2. **数值层面**：2 的幂、移位、循环移位、前导/尾随零计数、置位计数、位置换——全部只对**无符号整数**的**值**做运算，与内存布局无关。

本节的子条款：

| 子条款 | 内容 |
|---|---|
| [bit.general] | 一句话总述 |
| [bit.syn] | `<bit>` 概要（全部 freestanding） |
| [bit.cast] | `bit_cast` |
| [bit.byteswap] | `byteswap` {{c++23}} |
| [bit.pow.two] | `has_single_bit`、`bit_ceil`、`bit_floor`、`bit_width` |
| [bit.shift] | `shl`、`shr`（新近加入草案） |
| [bit.rotate] | `rotl`、`rotr` |
| [bit.count] | `countl_zero`、`countl_one`、`countr_zero`、`countr_one`、`popcount` |
| [bit.permute] | `bit_reverse`、`bit_repeat`、`bit_compress`、`bit_expand`（新近加入草案） |
| [bit.endian] | `enum class endian` |

## 总述与概要（[bit.general]、[bit.syn]）

[bit.general] ¶1：`<bit>` 提供访问、操作、处理单个位和位序列的组件。概要第一行是 `// all freestanding`——整个头文件在独立实现（[[g:freestanding-implementation]]）中也必须提供，因为它不需要分配、异常或 I/O。对比 [[bitset]] 的 `<bitset>` 不是 freestanding。

几乎所有函数都是 `constexpr` 且 `noexcept`，只有两个例外不带 `noexcept`：`bit_ceil` 和 `bit_repeat`——恰好是两个带**前置条件**的函数（见下文）。这符合标准库的"Lakos 规则"惯例：有窄契约的函数不标 `noexcept`，给实现留出"违规时抛异常"的检查空间。libc++ 实际上给 `bit_ceil` 加了 `noexcept`（实现可以加强 `noexcept`）。

另一个贯穿全节的约定：除 `bit_cast`、`byteswap` 和 `shl`/`shr` 外，所有函数的 *Constraints* 都是"`T` 是**无符号整数类型**"（[[basic.fundamental]]，[[g:unsigned-integer-type]]）。这意味着 `bool`、`char`、`char8_t`、`wchar_t`、有符号整数、枚举**都不被接受**——且因为是 *Constraints*，不满足时函数不参与重载决议（SFINAE 友好），报错是"没有匹配的函数"：

```cpp run title="bit-unsigned-only.cpp" error
#include <bit>
auto a = std::popcount(-1);              // error: int 不是无符号整数类型
auto b = std::has_single_bit(true);      // error: bool 不是无符号整数类型
auto c = std::rotl('a', 1);              // error: char 也不是
```

排除有符号类型是刻意的：`countl_zero(-1)` 应该是多少？对有符号数，"最高位"是符号位，诸如"前导零个数"的含义依赖于表示——而无符号整数的值与其二进制表示是一一对应的。

---

## `bit_cast`（[bit.cast]）

### 动机：类型双关的合法出口

"把一个 `float` 的比特当成 `uint32_t` 来看"是底层代码的日常需求（解析浮点格式、哈希、序列化、SIMD）。C++20 之前常见三种写法，前两种都是错的：

| 写法 | 合法性 |
|---|---|
| `*reinterpret_cast<uint32_t*>(&f)` | {{ub}}：通过 `uint32_t` glvalue 访问 `float` 对象，`float` 对象不能经 `uint32_t` 类型访问（*type-accessible*，[[basic.lval#11]]），违反严格别名 |
| `union { float f; uint32_t u; }` 写 `f` 读 `u` | {{ub}}：读取非活跃成员（[[class.union]]），GCC/Clang 作为扩展支持，但常量求值中拒绝 |
| `std::memcpy(&u, &f, 4)` | 合法：平凡可复制类型的对象表示可以复制到另一个对象（[[basic.types]]） |
| `std::bit_cast<uint32_t>(f)` {{c++20}} | 合法，而且可以是常量表达式 |

```cpp run title="type-punning-ub.cpp" ub
#include <cstdint>
#include <cstdio>
float f = 1.0f;
int main() {
    std::uint32_t u = *reinterpret_cast<std::uint32_t*>(&f);   // UB: float 对象不能经 uint32_t glvalue 访问
    std::printf("%x\n", u);                                     // 通常"碰巧"打印 3f800000
}
```

`memcpy` 法的缺点是需要先有一个目标对象（`To` 必须可默认构造）、写起来啰嗦、不能在常量求值中用。`bit_cast`（[[P0476R2]]）就是把"memcpy 进一个新对象"包装成一个返回值的、可 `constexpr` 的函数。

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

### 约束（¶1）

!!! std
    Constraints: sizeof(To) == sizeof(From) is true; is_trivially_copyable_v<To> is true; and is_trivially_copyable_v<From> is true.

    三个条件都是 *Constraints*：不满足时 `bit_cast` 不参与重载决议，而不是 `static_assert` 硬错误。

- **大小相等**：`bit_cast` 不做截断也不做填充。想取 `double` 的低 32 位，先 `bit_cast<uint64_t>` 再移位。
- **双方都平凡可复制**（[[g:trivially-copyable-type]]，[[class.prop]]）：只有平凡可复制类型才有"对象表示复制过去就能得到同一个值"的保证（[[basic.types]]）。注意 `To` **不需要**可默认构造——这正是 `bit_cast` 胜过 `memcpy` 的地方之一，实现要靠编译器内建函数直接"凭空"造出 `To` 对象。

libc++ 的实现（`__bit/bit_cast.h`）只有一行：用 `requires` 子句表达三个约束，函数体是 `return __builtin_bit_cast(_ToType, __from);`。整个语义——包括常量求值中的所有检查——都在编译器内建 `__builtin_bit_cast` 里。GCC 和 MSVC 也提供同名内建。纯库代码**无法**实现 `constexpr` 的 `bit_cast`：常量求值中既不能 `reinterpret_cast`，也不能对不同类型的对象 `memcpy`。

```cpp run title="bit-cast-size.cpp" error
#include <bit>
auto d = std::bit_cast<long>(1);   // error: sizeof(long) != sizeof(int)，约束不满足，无匹配函数
```

### 返回值：逐位复制与隐式对象创建（¶3）

¶3 是整个 [bit] 中最精密的一段。拆开来读：

**① 结果是什么。** 返回一个 `To` 类型的对象，并**在结果中隐式创建嵌套对象**（[[intro.object]]，[[g:implicitly-create-objects]]）。例如 `To` 是一个含联合体成员的结构体时，联合体的哪个成员是活跃的，按隐式对象创建的规则"选一个能让程序有定义行为的"。

**② 比特如何对应。** 结果**值表示**（[[g:value-representation]]）的每一位等于 `from` 的**对象表示**（[[g:object-representation]]）的对应位。结果的填充位（[[g:padding-bits]]）是未指明的。结果及其中创建的每个平凡可复制对象都"获得所产生的值表示"（[[g:acquire-value-representation]]）；**若有任何这样的对象没有得到值，行为未定义**。

注意源和目标的不对称：读的是 `from` 的**对象表示**（包括填充位），写的是 `To` 的**值表示**。

**③ 不确定位与错误位。** 结果值表示中的一位是**不确定的**（*indeterminate*），若它：

- 对应 `from` 中**不属于值表示**的位（即 `from` 的填充位），或
- 对应的位所在的最小外围对象不在生存期内，或具有不确定值（[[basic.indet]]）。

一位是**错误的**（*erroneous*），若它对应的位所在的最小外围对象具有错误值（[[g:erroneous-value]]，例如未初始化的自动变量，C++26 起其读取是错误行为，[[P2795R5]]）。

**④ 后果。** 对结果中每个不确定或错误的位 b，取包含 b 的最小对象 u：

- （3.1）若 u 是**无符号普通字符类型**（`unsigned char`，以及 `char` 为无符号时的 `char`）或 `std::byte`：若其值表示中有任一位不确定，u 具有不确定值，否则具有错误值。——**不是 UB**，这正是字节类型的特权（与 [[basic.indet]] 中允许用 `unsigned char`/`std::byte` 搬运不确定值的规则一致）。
- （3.2）否则，若 b 不确定：**未定义行为**。
- （3.3）否则（b 是错误的）：**错误行为**（{{erroneous}}），结果如上所述。

最后一句：除此之外结果中不含任何不确定或错误的值。

!!! ub "带填充的结构体"
    `struct P { char c; int i; };` 在常见 ABI 上 `c` 后有 3 字节填充。`bit_cast<uint64_t>(P{1, 2})` 中，`uint64_t` 有 24 位来自 `P` 的填充，这些位不确定，u 是整个 `uint64_t`（不是字节类型），按 ¶3.2 是 {{ub}}。而 `bit_cast<std::array<unsigned char, 8>>(P{1, 2})` 是合法的：填充对应的那 3 个 `unsigned char` 元素各自具有不确定值，只要不去"使用"它们就没事。

常量求值严格执行这套规则——Clang 的诊断甚至直接复述了 ¶3.1：

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
    return bytes[1];              // 填充字节具有不确定值，读它 → 不是常量表达式
}
static_assert(padding_byte() == 0);                          // error

constexpr auto u = std::bit_cast<std::uint64_t>(P{1, 2});    // error: ¶3.2，UB
```

Clang 对最后一行的说明是 *indeterminate value can only initialize an object of type 'unsigned char' or 'std::byte'*。另外值得一提：即便是合法的 `bit_cast<std::array<unsigned char, 8>>(P{1, 2})`，也**不能**用来初始化一个 `constexpr` 变量——常量表达式的结果不允许含不确定值（[[expr.const]]），所以上面把它放在 `constexpr` 函数的局部变量里。

### 何时是常量表达式（¶2）

!!! std
    Constant When: Neither To nor From has constexpr-unknown representation ([expr.const.core]).

    *Constant When* 是 [[structure.specifications]] 新增的规格元素：列出调用成为常量子表达式（[[g:constant-subexpression]]）所需的条件。

**constexpr 未知表示**（[[g:constexpr-unknown-representation]]）在 [[expr.const.core#1]] 中定义：一个类型若是

- 联合体，
- `std::meta::info`，
- 指针或成员指针类型，
- volatile 限定的类型，
- 有引用类型非静态数据成员的类类型，
- 或有某个基类/非静态成员的类型具有 constexpr 未知表示，

则它具有 constexpr 未知表示。

道理各不相同：

- **指针**：常量求值器里的指针是"某个对象 + 偏移"的符号值，根本没有确定的地址比特——`bit_cast<uintptr_t>(&g)` 无法在编译期给出答案；反方向（整数→指针）更不可能。
- **联合体**：哪个成员活跃会影响哪些位是值表示；编译器无法在常量求值中合理地逐位处理。
- **volatile**：访问 volatile 对象本来就不能出现在常量表达式中。
- **引用成员**：本质上同指针。
- **`std::meta::info`**：反射值（C++26 反射）是编译器内部句柄，没有比特表示。

C++20 原来的写法是在 [bit.cast] 里直接列出"`To`、`From` 及其所有子对象类型都不是联合体、指针、成员指针、volatile、且无引用成员时，此函数为 `constexpr`"。现行草案把这份清单提升为核心语言概念 [[expr.const.core]]（因为指针比较等其他规则也要用到它），并加入了 `std::meta::info`。

```cpp run title="bit-cast-constexpr.cpp" error
#include <bit>
#include <cstdint>

struct S { int* p; };
union U { int i; float f; };
int g;

constexpr auto a = std::bit_cast<std::uintptr_t>(&g);          // error: From 是指针类型
constexpr auto b = std::bit_cast<std::uintptr_t>(S{nullptr});  // error: 成员是指针，S 也具有 constexpr 未知表示
constexpr auto c = std::bit_cast<int>(U{1});                   // error: From 是联合体
```

三者在**运行期**都完全合法——"不是常量表达式"只影响编译期求值。

!!! pitfall "bit_cast 不是 reinterpret_cast 的语法糖"
    `bit_cast` 永远返回一个**新对象**（按值），从不产生指向原对象的别名。`bit_cast<Header>(buffer)` 要求 `buffer` 是一个 `sizeof(Header)` 大的对象（如 `std::array<std::byte, N>`），而不是指针——`bit_cast<Header>(ptr)` 只会把**指针本身的 8 个字节**重新解释，几乎一定不是你想要的（并且 `sizeof` 不匹配时直接无法编译）。想要"把这块内存当作 `T` 对象来用"，那是 `std::start_lifetime_as`（[[obj.lifetime]]）的工作。

---

## `byteswap`（[bit.byteswap]）{{c++23}}

¶1–4：*Constraints* `T` 满足 `integral`（注意：这里接受**有符号**整数、`char` 乃至 `bool`）；*Mandates* `T` **没有填充位**（[[basic.types]]）；返回值的对象表示是 `value` 的对象表示的字节逆序。[[P1272R4]] 引入。

几点说明：

- 规格完全在**对象表示**层面描述，所以对有符号数也有明确定义：`byteswap(int16_t{0x0102}) == 0x0201`。
- *Mandates* 无填充位：若 `T` 有填充位，字节逆序可能把填充位搬进值表示，产生不确定值。违反 *Mandates* 是**非良构**（需要诊断）——libc++（`__bit/byteswap.h`）用 `static_assert(numeric_limits<T>::digits + is_signed == sizeof(T) * CHAR_BIT)` 检查，并对 `bool` 网开一面（其源码注释说现有实现都接受 `bool`，而单字节的恒等变换不会搬动任何位）。
- 单字节类型时就是恒等函数。
- 它与 [[bit.endian|endian]] 搭配用于网络字节序转换：`if constexpr (std::endian::native == std::endian::little) x = std::byteswap(x);`。
- 实现上 libc++ 优先用 `__builtin_bswapg`（泛型版本），否则按大小分派到 `__builtin_bswap16/32/64/128`，编译为单条 `bswap`/`rev` 指令。

---

## 2 的整数幂（[bit.pow.two]）

四个函数（[[P0556R3]] 引入，[[P1956R1]] 把原名 `ispow2`/`ceil2`/`floor2`/`log2p1` 改为现名），都要求 `T` 是无符号整数类型：

| 函数 | 段落 | 返回 | `x == 0` 时 |
|---|---|---|---|
| `has_single_bit(x)` | ¶1–2 | `x` 是否为 2 的整数幂（恰有一位为 1） | `false` |
| `bit_ceil(x)` | ¶3–8 | 不小于 `x` 的最小 2 的幂 N | `1`（2⁰ ≥ 0） |
| `bit_floor(x)` | ¶9–10 | 不大于 `x` 的最大 2 的幂 | `0` |
| `bit_width(x)` | ¶11–12 | `1 + floor(log2(x))`，即表示 `x` 所需的位数 | `0` |

改名的理由（P1956R1）：原名暗示"数学上的 log/ceil"，而 `log2p1` 尤其难懂；新名字强调它们是**位操作**。`bit_width` 与 `countl_zero` 的关系是 `bit_width(x) == numeric_limits<T>::digits - countl_zero(x)`。

### `bit_ceil` 的前置条件与常量求值（¶5、¶8）

`bit_ceil` 是本节唯一带普通前置条件的数值函数：

!!! std
    Preconditions: N is representable as a value of type T.

    Remarks: A function call expression that violates the precondition in the Preconditions: element is not a core constant expression.

- **运行期**：违反前置条件是 {{ub}}（这是普通的 *Preconditions*，不是硬化前置条件）。例如 `bit_ceil(uint8_t{129})` 应得 256，`uint8_t` 放不下。
- **常量求值**：¶8 的 *Remarks* 把"UB"升级为"不是核心常量表达式"——即编译器**必须**在常量求值中诊断，而不是给出一个任意值。这是标准库对"constexpr 函数中的前置条件违规"的一种标准写法，让 `static_assert(bit_ceil(...))` 永远不会悄悄得到错误答案。

libc++（`__bit/bit_ceil.h`）的实现：先算 `n = digits - countl_zero(x - 1)`，然后返回 `T{1} << n`；对窄于 `unsigned` 的类型先在 `unsigned` 中左移再右移回来，确保溢出时左移量 ≥ 32，从而在常量求值中触发"移位量越界"的诊断。运行期则用 `_LIBCPP_ASSERT_ARGUMENT_WITHIN_DOMAIN` 检查，该检查只在 extensive/debug 硬化模式下启用，fast 模式和非硬化模式不检查（实测本机非硬化时 `bit_ceil(0x80000001u)` 返回 1）。

```cpp run title="bit-ceil.cpp" error
#include <bit>
#include <cstdint>

static_assert(std::bit_ceil(5u) == 8u);
static_assert(std::bit_ceil(0u) == 1u);            // 0 的 bit_ceil 是 1
static_assert(std::bit_floor(0u) == 0u);
static_assert(std::bit_width(0u) == 0 && std::bit_width(8u) == 4);
static_assert(std::bit_ceil(std::uint8_t{128}) == 128);
constexpr auto x = std::bit_ceil(std::uint8_t{129});  // error: 256 无法用 uint8_t 表示，不是核心常量表达式
```

---

## 移位 `shl`/`shr`（[bit.shift]）

这是新近加入工作草案的一对函数，截至本文编写时 libc++ 尚未实现。它们解决的是内建移位运算符（[[expr.shift]]）的"雷区"：右操作数为负或不小于左操作数的位宽时是 {{ub}}，有符号数左移溢出也有一堆历史包袱。

¶1 给出一种"数学化"的规定方式：算术运算的结果 r 先在一个**范围足够大的假想整数类型**中表示，再 `static_cast<T>(r)` 转回 `T`（即按 2ⁿ 取模，[[conv.integral]]）。

- ¶2–3 `shl(x, s)`：返回 x × 2ˢ 向负无穷舍入后的值；
- ¶4–5 `shr(x, s)`：返回 x × 2⁻ˢ 向负无穷舍入后的值。
- *Constraints*：`T` 和 `S` 都是有符号或无符号整数类型——与本节其余函数不同，**接受有符号数**。

于是：`s` 为负时自然变成反方向移位；`s` 超过位宽时，`shl` 结果模 2ⁿ 后是 0，`shr` 对非负数是 0、对负数是 −1（向负无穷舍入，相当于算术右移）。没有任何 UB，`noexcept`，也没有前置条件。

---

## 循环移位 `rotl`/`rotr`（[bit.rotate]）

[[P0553R4]] 引入。¶1 令 N = `numeric_limits<T>::digits`。以 `rotl` 为例（¶3–4），令 r = `s % N`：

- r 为 0：返回 `x`；
- r 为正：`(x << r) | (x >> (N - r))`；
- r 为负：`rotr(x, -r)`。

`rotr` 对称（¶6–7）。要点：

- **`s` 是 `int` 且允许为负**：负的左旋等于右旋。由于 C++ 的 `%` 向零截断（[[expr.mul]]），`-33 % 32 == -1`，所以 `rotl(x, -33) == rotr(x, 1)`。
- **任意大的 `s` 都合法**：取模之后移位量总在 `(−N, N)` 内，且 r 为 0 时不做移位，避开了 `x >> N` 这个 UB。
- libc++（`__bit/rotate.h`）分别写了 `rotl` 和 `rotr` 两个完整函数体，注释说明这样更容易让编译器识别为 x86 的 `ROL`/`ROR` 指令。

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

---

## 计数（[bit.count]）

同样由 [[P0553R4]] 引入。N = `numeric_limits<T>::digits`：

| 函数 | 段落 | 返回 |
|---|---|---|
| `countl_zero(x)` | ¶2–3 | 从最高位起连续 0 的个数；`x == 0` 时为 N（注 1） |
| `countl_one(x)` | ¶4–5 | 从最高位起连续 1 的个数；`x` 为最大值时为 N（注 2） |
| `countr_zero(x)` | ¶6–7 | 从最低位起连续 0 的个数；`x == 0` 时为 N（注 3） |
| `countr_one(x)` | ¶8–9 | 从最低位起连续 1 的个数；`x` 为最大值时为 N（注 4） |
| `popcount(x)` | ¶10–11 | 值为 1 的位的个数 |

返回类型都是 `int`。四条注是**非规范性**的，但它们强调的事实由 *Returns* 直接推出：**输入为 0 时有完全定义的结果**。这是与 `__builtin_clz`/`__builtin_ctz` 最大的区别——后两者在输入为 0 时结果未定义，而 x86 的 `BSR`/`BSF` 指令在输入为 0 时目标寄存器内容也是未定义的。标准版本要么用 `LZCNT`/`TZCNT`（输入为 0 时返回位宽），要么多一次分支。libc++（`__bit/countl.h`、`__bit/popcount.h`）直接用带默认值的泛型内建 `__builtin_clzg(x, digits)` 和 `__builtin_popcountg(x)`。

---

## 位置换（[bit.permute]）

四个函数是新近加入工作草案的（[[P3104]]），截至本文编写时 libc++ 尚未实现（本机 `<bit>` 中没有这些名字，也没有对应的特性测试宏）。¶1 先定义记号：N 是位宽；αₙ 是 α 从低往高第 n 位；σ(α, n) = α 最低 n 位中 1 的个数。

| 函数 | 段落 | 含义 | 对应硬件 |
|---|---|---|---|
| `bit_reverse(x)` | ¶2–4 | 位序翻转：第 n 位移到第 N−1−n 位；自逆（注 1） | ARM `RBIT` |
| `bit_repeat(x, l)` | ¶5–10 | 取 `x` 的最低 `l` 位作为图样，重复铺满 N 位；例：`bit_repeat(uint32_t{0xc}, 4) == 0xcccccccc` | — |
| `bit_compress(x, m)` | ¶11–13 | 把 `x` 中 `m` 为 1 的那些位**依次收拢**到低端 | x86 BMI2 `PEXT` |
| `bit_expand(x, m)` | ¶14–16 | 逆操作：把 `x` 的低位依次**撒到** `m` 为 1 的位置上 | x86 BMI2 `PDEP` |

公式读法：compress(x, m) = Σ mₙ·xₙ·2^σ(m,n)——只有 mₙ = 1 的位参与，它被放到第 σ(m, n) 位，也就是"m 中位于它下方的 1 的个数"。例 2：`bit_compress(0bABCD, 0b0101) == 0b00BD`。expand 正好倒过来：第 n 位（若 mₙ = 1）取 x 的第 σ(m, n) 位。例 3：`bit_expand(0bABCD, 0b0101) == 0b0C0D`。

`bit_repeat` 是唯一带前置条件的：¶6 *Preconditions* `l > 0`；¶8 *Throws: Nothing*；¶9 与 `bit_ceil` 相同的 *Remarks*——违反前置条件的调用不是核心常量表达式。`l` 大于等于 N 时没有问题：公式中 n mod l = n，结果就是 `x` 本身。

在标准实现到来之前，可以按 ¶12 的公式手写一个可移植的 `bit_compress`：

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

---

## 字节序（[bit.endian]）

¶1 定义两种常见字节序：**大端**（[[g:big-endian]]）最高有效字节在前；**小端**（[[g:little-endian]]）最低有效字节在前。本子条款描述执行环境中**标量类型**的字节序。[[P0463R1]] 引入。

`enum class endian { little, big, native };` 三个枚举值都是"见下文"，¶2 只约束它们之间的**关系**：

- 若所有标量类型的大小都是 1 字节（例如某些 DSP 上 `CHAR_BIT == 32`、`sizeof(long) == 1`），则 `little`、`big`、`native` **三者相等**——字节序这个问题根本不存在。
- 否则 `little != big`。
- 所有标量类型都是大端 → `native == big`；都是小端 → `native == little`。
- 否则（**混合字节序**，[[g:mixed-endian]]）`native` **既不等于 `big` 也不等于 `little`**。

混合字节序不是理论上的稻草人：PDP-11 的 32 位整数是"两个小端 16 位字按大端排列"；某些 ARM 浮点格式中 `double` 的两半与整数字序不同。"所有标量类型"包括浮点和指针，所以只要有一种标量类型的字节序与其他不同，`native` 就不能声称是 `little` 或 `big`。

正确的做法是显式排除第三种情况，而不是写 `native == little ? ... : ...` 默认"不是小端就是大端"：

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

（注意：在非模板函数里，`if constexpr` 被弃置分支中的 `static_assert(false)` 仍然会被求值并失败——"弃置语句不实例化"只对模板内部有效，见 [[stmt.if]]——所以这里用一个普通的 `static_assert` 条件。）

libc++（`__bit/endian.h`）给 `little` 和 `big` 取了两个任意的不同值（`0xDEAD`、`0xFACE`），`native` 按目标平台宏取其一，否则取第三个值 `0xCAFE`——正好实现了 ¶2 的三种情况（"全部 1 字节"的情况 libc++ 不支持）。

---

## 历史

!!! history
    - C++20：`bit_cast`（[[P0476R2]]）、`endian`（[[P0463R1]]，最初放在 `<type_traits>`，后移入 `<bit>`）、`rotl`/`rotr`/计数函数（[[P0553R4]]）、2 的幂函数（[[P0556R3]]，并经 [[P1956R1]] 改名）。
    - C++23：`byteswap`（[[P1272R4]]）。
    - C++26：[[P2795R5]] 引入错误行为后，`bit_cast` 的 ¶3 增加了"错误位"及其处理规则；`<stdbit.h>` 以 C23 头文件的身份进入 C++（见 [[stdbit.h.syn]]）。
    - C++26 之后：`bit_cast` 的 constexpr 限制改用核心语言的"constexpr 未知表示"概念并以 *Constant When* 元素表述；新增 `shl`/`shr` 与位置换函数（[[P3104]]）。

## 思考题

!!! question "1"
    `struct A { std::uint16_t a; std::uint8_t b; };`（sizeof 为 4）。`std::bit_cast<std::uint32_t>(A{1, 2})` 在运行期的行为是什么？`std::bit_cast<std::array<std::byte, 4>>(A{1, 2})` 呢？若随后读取后者的 `[3]` 元素呢？

<details markdown="1">
<summary>展开查看答案与解析</summary>

`A` 的最后 1 个字节是填充，不属于 `A` 的值表示。按 [bit.cast] ¶3，`uint32_t` 结果中有 8 位对应 `from` 中不属于值表示的位，因此是不确定位；包含它们的最小对象是整个 `uint32_t`，不是字节类型，按 ¶3.2 行为未定义。

转成 `array<std::byte, 4>` 时，包含不确定位的最小对象是第 4 个 `std::byte` 元素，按 ¶3.1 它只是具有不确定值，`bit_cast` 本身行为良好。随后读取 `[3]`：对 `std::byte` 的左值到右值转换得到不确定值，按 [[basic.indet]] ¶2 的例外，仅当用于初始化另一个 `unsigned char`/`std::byte` 对象等少数情形才不是 UB；拿它做比较或算术则是 UB。
</details>

!!! question "2"
    为什么 `bit_ceil` 不标 `noexcept`、`bit_floor` 却标了？`bit_ceil` 的 *Remarks* 对 `constexpr` 用户意味着什么？

<details markdown="1">
<summary>展开查看答案与解析</summary>

`bit_floor` 对任何输入都有定义（宽契约），`bit_ceil` 有前置条件"结果可表示"（窄契约）。标准库惯例对窄契约函数不加 `noexcept`，以便实现可以在违规时抛异常进行检查（但实现可以加强为 `noexcept`，libc++ 就这么做了）。¶7 *Throws: Nothing* 表明符合前置条件时不会抛异常。

¶8 规定违反前置条件的调用不是核心常量表达式，因此在 `constexpr` 变量初始化、`static_assert`、模板实参等需要常量表达式的语境中，编译器必须报错，而不是静默给出 0 或 1 之类的结果。
</details>

!!! question "3"
    在一个 `char`、`short`、`int`、`long` 都是小端，但 `double` 的两个 32 位半字按大端排列的平台上，`std::endian::native` 等于什么？

<details markdown="1">
<summary>展开查看答案与解析</summary>

既不等于 `endian::little` 也不等于 `endian::big`（[bit.endian] ¶2 最后一句）：并非所有标量类型都是小端。`double` 是标量类型（[[basic.types]]），所以它的字节序也计入判断。此时 `little != big` 仍成立（并非所有标量类型都是 1 字节）。
</details>

## 小结

| 函数 | 类型要求 | 前置条件 / 特殊规则 |
|---|---|---|
| `bit_cast<To>(from)` | `sizeof` 相等，双方平凡可复制（*Constraints*） | 读 `from` 的对象表示写 `To` 的值表示；不确定位落在非字节对象上为 UB，错误位为 EB；*Constant When*：双方都无 constexpr 未知表示 |
| `byteswap` | `integral`（含有符号）；*Mandates* 无填充位 | 无 |
| `has_single_bit`/`bit_floor`/`bit_width` | 无符号整数 | 无；`x == 0` 有定义 |
| `bit_ceil` | 无符号整数 | 结果须可表示，违反为 UB，常量求值中非常量 |
| `shl`/`shr` | 有符号或无符号整数 | 无；负移位量、超大移位量都有定义；libc++ 未实现 |
| `rotl`/`rotr` | 无符号整数 | 无；`s` 可为负、可任意大 |
| `countl_*`/`countr_*`/`popcount` | 无符号整数 | 无；`x == 0` 返回 N |
| `bit_reverse`/`bit_compress`/`bit_expand` | 无符号整数 | 无；libc++ 未实现 |
| `bit_repeat` | 无符号整数 | `l > 0`，常量求值中违规非常量；libc++ 未实现 |
| `endian` | — | 全 1 字节时三值相等；混合字节序时 `native` 两不相等 |
