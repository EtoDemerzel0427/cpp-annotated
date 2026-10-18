---
title: 寻常算术转换
summary: 二元算术、比较、位运算与条件运算符如何把两个算术/枚举操作数统一到一个公共类型：枚举的限制（C++26 起部分组合非良构）、浮点等级与子等级、整数的提升与有/无符号合并规则
status: draft
papers: P1120R0, P2864R2, P1467R9
related: conv.prom, conv.rank, conv.integral, expr.mul, expr.add, expr.rel, expr.eq, expr.spaceship, expr.cond, dcl.enum
tags: 转换, 整数, 浮点, 枚举, 陷阱
updated: 2026-10-17
---

`a + b` 中如果 `a` 是 `short`、`b` 是 `unsigned long`，结果是什么类型？`-1 < 0u` 为什么是 `false`？这些问题的答案都在这一节。**寻常算术转换**（[[g:usual-arithmetic-conversions]]）是一个固定的算法，它把两个算术或枚举类型的操作数转换到一个公共类型；对大多数运算符而言，这个类型同时也是结果类型。

引用它的运算符如下：

| 运算符 | 条款 | 备注 |
|---|---|---|
| `*` `/` `%` | [[expr.mul]] | |
| `+` `-` | [[expr.add]] | 一方是指针时不适用 |
| `<` `>` `<=` `>=` | [[expr.rel]] | 结果是 `bool`，公共类型只用于比较 |
| `==` `!=` | [[expr.eq]] | 同上 |
| `<=>` | [[expr.spaceship]] | 额外禁止窄化（整数 → 浮点除外） |
| `&` `^` `\|` | [[expr.bit.and]] 等 | |
| `?:` | [[expr.cond]] | 第二、第三操作数为算术或枚举类型时 |
| 复合赋值 `+=` 等 | [[expr.assign]] | 经由 `E1 = E1 op E2` 的等价定义 |

不使用它的有：移位运算 `<<`、`>>`（两个操作数各自做整型提升，结果类型是提升后的左操作数类型，[[expr.shift]]），一元运算符（只做整型提升），逻辑运算符（按语境转换为 `bool`）。

## 算法（¶1）

¶1 的算法分五步，下面逐条解释。

### 第 1 步：读值（¶1.1）

¶1.1 对两个操作数施行左值到右值转换（[[conv.lval]]），之后用得到的 prvalue 代替原操作数。

### 第 2 步：有作用域枚举（¶1.2）

¶1.2 如果任一操作数是有作用域枚举类型（[[dcl.enum]]），就不做任何转换；如果另一操作数的类型与之不同，表达式非良构。

所以 `Color::red == Color::green` 合法（类型相同，不转换），`Color::red == 0` 非良构。注意，类型相同只是让寻常算术转换这一步通过，具体运算符还有自己的要求。例如 [[expr.add]] 要求操作数是算术类型或无作用域枚举类型，所以 `Color::red + Color::red` 依然非良构。

### 第 3 步：枚举与另一枚举或浮点 {{c++26}}（¶1.3）

¶1.3 否则，如果一个操作数是枚举类型，另一个是不同的枚举类型或浮点类型，表达式**非良构**。

!!! std
    if one operand is of enumeration type and the other operand is of a different enumeration type or a floating-point type, the expression is ill-formed.

    若一个操作数为枚举类型，另一个为不同的枚举类型或浮点类型，则表达式非良构。

```cpp error
enum A { a1 };
enum B { b1 };

auto x1 = a1 + b1;        // error（C++26）：不同的枚举类型
bool x2 = a1 == b1;       // error（C++26）：比较也一样
auto x3 = a1 | b1;        // error（C++26）：位运算也一样
auto x4 = a1 + 1.0;       // error（C++26）：枚举与浮点
auto x5 = true ? a1 : b1; // error（C++26）：条件运算符也走寻常算术转换

auto ok1 = a1 + 1;        // OK：枚举与整数
auto ok2 = a1 | a1;       // OK：同一枚举类型（结果是 int）
auto ok3 = +a1 + +b1;     // OK：显式提升后都是 int
```

!!! history "从弃用到删除"
    - C++17 及之前：不同枚举之间、枚举与浮点之间的算术运算与比较都合法，枚举先经整型提升，然后照常转换。
    - C++20：[[P1120R0]] 弃用了这些用法（{{deprecated}}）。Clang 在 C++20 模式下对应的警告是 `-Wdeprecated-enum-enum-conversion`、`-Wdeprecated-enum-float-conversion`、`-Wdeprecated-enum-compare`。
    - C++26：[[P2864R2]] 删除了这些用法，它们成为非良构（{{removed:C++26}}）。Clang 23 在 `-std=c++2c` 下对上例全部报错。

    这样做的动机是：两个不相关枚举之间的运算几乎总是 bug（例如把 `FileMode` 与 `Permission` 按位或在一起），而枚举与浮点的混合运算没有合理的语义。确实需要时，用显式转换（`+e` 或 `static_cast<int>(e)`）就能表达意图。

    注意，同一枚举类型的两个操作数，以及枚举与整数的组合，都不受影响。所以用无作用域枚举做位标志（`flags | FLAG_A`）的老代码依然可以编译。

### 第 4 步：浮点（¶1.4）

¶1.4 否则，如果任一操作数是浮点类型：

- ¶1.4.1 两者类型相同：不再转换。
- ¶1.4.2 一个是非浮点类型（整数或无作用域枚举）：将它转换为另一个操作数的浮点类型。
- ¶1.4.3 两者的**浮点转换等级**（[[conv.rank#2]]）有序但不相等：等级低的转换为等级高的类型。
- ¶1.4.4 等级相等：**子等级**（subrank）低的转换为子等级高的类型。
- ¶1.4.5 否则（等级无序）：非良构。

对于只用 `float`、`double`、`long double` 的传统程序，这条规则就是向更宽的类型靠拢。后三条是 C++23 引入扩展浮点类型（[[P1467R9]]）时加入的：

| 操作数 | 结果类型 | 依据 |
|---|---|---|
| `float` + `double` | `double` | 等级 |
| `int` + `float` | `float` | ¶1.4.2，即使 `int` 的值不能被 `float` 精确表示 |
| `std::float16_t` + `float` | `float` | 等级（float16 的值集是 float 的真子集） |
| `std::float32_t` + `float`（值集相同） | `std::float32_t` | 等级相等，`std::floatN_t` 的子等级更高（[[conv.rank#3]]） |
| `std::float64_t` + `double`（值集相同） | `std::float64_t` | 同上 |
| `std::bfloat16_t` + `std::float16_t` | 非良构 | 一个范围更大，一个精度更高，值集互不包含，等级无序 |

```cpp
#include <stdfloat>   // 需要实现支持扩展浮点类型
auto a = std::float16_t(1) + 1.0f;     // float
auto b = std::float32_t(1) + 1.0f;     // std::float32_t
auto c = std::bfloat16_t(1) + std::float16_t(1);   // error: 等级无序
```

（截至写作时，本机的 libc++ 尚未提供 `<stdfloat>`，上例未能在本地验证；规则直接取自 [[conv.rank]] 与本节条文。）

!!! pitfall "`int` + `float` 会丢精度"
    ¶1.4.2 无条件地把整数转换为浮点类型，不管能否精确表示：`16777217 + 0.0f` 得到 `16777216.0f`。`long long` + `float` 的情况更糟，结果只有 24 位有效数字。

### 第 5 步：整数（¶1.5）

¶1.5 否则（两个操作数都是整数或无作用域枚举），两者都转换为公共类型 `C`。先对每个操作数做**整型提升**（[[conv.prom]]），得到类型 `T1`、`T2`（脚注：因此 `bool`、`char8_t`、`char16_t`、`char32_t`、`wchar_t` 和枚举类型的操作数都会转换为某个整数类型）。然后：

- ¶1.5.1 `T1`、`T2` 相同：`C` 就是这个类型。
- ¶1.5.2 同为有符号或同为无符号：`C` 是等级（[[conv.rank#1]]）较高的那个。
- ¶1.5.3 一个有符号（`S`），一个无符号（`U`）：
    - ¶1.5.3.1 如果 `U` 的等级 ≥ `S` 的等级，`C` 是 `U`。
    - ¶1.5.3.2 否则，如果 `S` 能表示 `U` 的全部值，`C` 是 `S`。
    - ¶1.5.3.3 否则，`C` 是 `S` 对应的无符号类型。

用流程图表示：

```text
             提升 → T1, T2
                  │
        相同？ ── 是 ──→ C = T1
                  │否
     同符号？ ── 是 ──→ C = 等级高者
                  │否（S 与 U）
 rank(U) ≥ rank(S)？ ── 是 ──→ C = U
                  │否
 S 能表示 U 全部值？── 是 ──→ C = S
                  │否
                  └──→ C = unsigned S
```

在典型的 LP64 平台（Linux/macOS 64 位：`int` 32 位，`long` 与 `long long` 64 位）上：

| 操作数 | 提升后 | 规则 | 结果类型 |
|---|---|---|---|
| `short` + `short` | `int`, `int` | ¶1.5.1 | `int` |
| `unsigned short` + `int` | `int`, `int` | ¶1.5.1 | `int` |
| `char` + `bool` | `int`, `int` | ¶1.5.1 | `int` |
| `int` + `long` | — | ¶1.5.2 | `long` |
| `int` + `unsigned` | — | ¶1.5.3.1 | `unsigned` |
| `long` + `unsigned` | — | ¶1.5.3.2（64 位 `long` 能表示所有 32 位 `unsigned`） | `long` |
| `long` + `unsigned long` | — | ¶1.5.3.1（等级相等） | `unsigned long` |
| `long long` + `unsigned long` | — | ¶1.5.3.3（见下文） | `unsigned long long` |
| `long` + `unsigned long long` | — | ¶1.5.3.1 | `unsigned long long` |

```cpp ok
#include <type_traits>
template<class A, class B> using R = decltype(A{} + B{});
static_assert(std::is_same_v<R<short, short>, int>);
static_assert(std::is_same_v<R<unsigned short, int>, int>);
static_assert(std::is_same_v<R<int, unsigned>, unsigned>);
static_assert(std::is_same_v<R<unsigned long, long long>, unsigned long long>);
#if __SIZEOF_LONG__ == 8 && __SIZEOF_INT__ == 4
static_assert(std::is_same_v<R<long, unsigned>, long>);   // LP64：¶1.5.3.2
#endif
```

只有当有符号类型的等级更高、却容纳不下无符号类型的全部值时，才会用到 ¶1.5.3.3。LP64 上的 `long long` 与 `unsigned long` 就是这样：`unsigned long` 的等级等于 `long`，低于 `long long`，所以 ¶1.5.3.1 不适用；两者都是 64 位，`long long` 不能表示 `unsigned long` 的全部值，¶1.5.3.2 也不适用。于是结果是 `long long` 对应的无符号类型 `unsigned long long`，两个 64 位类型相加，得到的是第三种类型。上面的 `static_assert` 验证了这一点。

## 有符号与无符号混合的陷阱

¶1.5.3.1 是 C/C++ 中最常引发 bug 的规则之一：**同等级时，有符号向无符号靠拢**。

```cpp run title="sign.cpp" ok
#include <cstdio>
#include <utility>
#include <vector>

int main() {
    std::printf("%d\n", -1 < 0u);                    // 0：-1 被转换为 UINT_MAX
    std::printf("%d\n", -1L < 0u);                   // LP64 上为 1（long 能表示所有 unsigned）
                                                     // Windows（LLP64，long 为 32 位）上为 0！
    std::printf("%d\n", -1 < (unsigned short)0);     // 1：unsigned short 先被提升为 int

    std::vector<int> v;
    std::printf("%zu\n", v.size() - 1);              // 18446744073709551615

    std::printf("%d\n", std::cmp_less(-1, 0u));      // 1：C++20 的安全比较
}
```

要点如下：

1. 结果依赖于平台。`-1L < 0u` 在 LP64 与 LLP64 上结果相反，因为 ¶1.5.3.2 取决于 `long` 能否表示所有 `unsigned` 值。
2. 窄的无符号类型反而不受影响。`unsigned short`、`unsigned char` 先提升为（有符号的）`int`，所以 `-1 < (unsigned short)0` 为真。
3. `size()` 返回无符号类型。`v` 为空时，`for (int i = 0; i < v.size() - 1; ++i)` 会循环约 2<sup>64</sup> 次（并在 `v[i]` 处产生 UB）。
4. 诊断：GCC 与 Clang 的 `-Wsign-compare`（包含在 `-Wall` 或 `-Wextra` 中）和 `-Wsign-conversion` 能发现大部分这类问题。
5. C++20 的工具：`<utility>` 中的 `std::cmp_less`、`std::cmp_equal` 等按数学值比较不同符号的整数；`std::in_range<T>(x)` 检查值能否用 `T` 表示。

!!! pitfall "无符号的窄类型也会触发有符号溢出"
    对于 `unsigned short a = 65535, b = 65535; a * b`，两个操作数先提升为 `int`，乘积 4 294 836 225 超出 32 位 `int` 的范围，**属于有符号溢出，是 UB**（[[expr.pre]]）。安全的写法是 `1u * a * b` 或 `static_cast<unsigned>(a) * b`。`uint8_t`、`uint16_t` 的运算也有同样的问题，加密和哈希代码中真实出现过这类 bug。

### 三路比较更严格

`<=>` 在寻常算术转换之后还有一条要求：如果需要窄化转换（整数 → 浮点除外），程序非良构（[[expr.spaceship]]）。因此有符号与无符号之间的三路比较会直接被拒绝，C++20 借此在新运算符上避开了这个老陷阱：

```cpp error
#include <compare>
auto f(int i, unsigned u)              { return i <=> u; }   // error: int → unsigned 是窄化
auto g(unsigned short a, int b)        { return a <=> b; }   // OK：提升后都是 int
auto h(long long a, unsigned b)        { return a <=> b; }   // OK：unsigned → long long 不窄化
```

## 实现视角

!!! impl
    - 寻常算术转换完全在编译期决定，不产生运行时检查。整型提升在机器层面通常就是零扩展（`movzx`/`uxtb`）或符号扩展（`movsx`/`sxtb`）；ARM64、x86-64 的 32 位运算指令本来就以寄存器为单位，`short` 运算先提升到 int 往往不需要额外的指令。
    - 由于 `int` 运算的溢出是 UB 而 `unsigned` 不是，同一个循环用 `int` 还是 `unsigned` 做索引，生成的代码可能不同：编译器可以把 `int i` 加宽为 64 位指针偏移，`unsigned i` 则必须保留 32 位回绕语义。
    - Clang 的枚举诊断：C++20 模式下是 `-Wdeprecated-enum-enum-conversion` 等警告；C++26 模式下变为错误（不同枚举之间的情形以 `-Wenum-enum-conversion` 的名义报告为错误）。

## 历史与演进

!!! history
    - C/C++98：整数部分的规则沿袭 C 的值保持（value-preserving）提升方案。ANSI C 在无符号保持与值保持之间选择了后者，所以 `unsigned short` 提升为 `int` 而不是 `unsigned int`。
    - C++11：加入 `long long`，规则改用等级重新表述（[[conv.rank]]），以容纳扩展整数类型。
    - C++20：弃用枚举与不同枚举、枚举与浮点的混合运算（[[P1120R0]]）；`<=>` 禁止窄化。
    - C++23：引入扩展浮点类型以及浮点转换等级、子等级（[[P1467R9]]），¶1.4 增加了等级无序时非良构的规则。
    - C++26：删除被弃用的枚举运算（[[P2864R2]]），¶1.3 成为非良构规则。

## 思考题

!!! question "1. 在 LP64 平台上，`unsigned long` 与 `long long` 相加的结果类型是什么？为什么既不是 `unsigned long` 也不是 `long long`？"

<details markdown="1">
<summary>答案</summary>

结果类型是 `unsigned long long`。整型提升后类型不变，两者符号不同：`U = unsigned long`，`S = long long`。`unsigned long` 的等级等于 `long` 的等级，低于 `long long`，所以 ¶1.5.3.1 不适用。64 位的 `long long` 不能表示 64 位 `unsigned long` 的全部值，所以 ¶1.5.3.2 也不适用。按 ¶1.5.3.3，取 `S` 对应的无符号类型 `unsigned long long`。
</details>

!!! question "2. `enum E { a }; enum F { b };` 中，`a == b` 在 C++26 中非良构。那 `a == +b` 呢？`static_cast<E>(b) == a` 呢？"

<details markdown="1">
<summary>答案</summary>

两者都良构。`+b` 是一元加，对 `b` 做整型提升，结果是 `int`，于是 `a == +b` 是枚举与整数的组合，不触发 ¶1.3。`static_cast<E>(b) == a` 的两个操作数都是同一枚举类型 `E`，也不触发 ¶1.3（两者提升为 `int` 后比较）。
</details>

!!! question "3. 为什么 `char c = 'a'; auto d = c + c;` 中 `d` 的类型是 `int`，而 `char` 是否有符号是实现定义的，这对结果类型有没有影响？"

<details markdown="1">
<summary>答案</summary>

`char` 的等级低于 `int`，并且在 `int` 宽于 8 位的平台上，无论 `char` 有无符号，`int` 都能表示 `char` 的全部值，所以按 [[conv.prom#2]] 总是提升为 `int`，再按 ¶1.5.1 得到 `int`。`char` 有无符号只影响值（例如 `'\xff'` 是 −1 还是 255），不影响结果类型。
</details>

## 小结

!!! summary
    1. 读值（左值到右值）。
    2. 有作用域枚举：不转换，类型必须相同。
    3. 枚举 + 不同枚举 / 浮点：C++26 起非良构（C++20 弃用）。
    4. 有浮点：整数转为浮点；先按等级，再按子等级；等级无序则非良构。
    5. 全是整数：先各自提升；类型相同则取该类型；同符号取等级高者；否则，无符号等级 ≥ 有符号时取无符号，有符号能容纳无符号全部值时取有符号，再否则取有符号类型对应的无符号类型。
    
    记住：**同等级时有符号向无符号靠拢**；窄的无符号类型会被提升为有符号 `int`；用 `std::cmp_less` 或 `<=>` 避开混合符号比较。
