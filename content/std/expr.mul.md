---
title: 乘性运算符
summary: "* / % 接受哪些操作数、结果是什么类型；整数除法向零截断、余数与被除数同号；除以零和 INT_MIN / -1 为什么是未定义行为。"
status: done
related: expr.arith.conv, conv.prom, expr.pre, basic.fundamental, expr.shift, expr.add, expr.const.core
tags: 算术, 整数, UB
updated: 2026-10-19
---

!!! tldr
    - `*`、`/`、`%` 从左往右结合，操作数先做常用算术转换，转换后的公共类型就是结果类型。`%` 只接受整数和无作用域枚举。
    - 两个 `unsigned short` 相乘实际是 `int` 乘法，乘积超出 `int` 范围就是未定义行为。
    - 整数除法向零截断，`-7 / 2 == -3`；余数与被除数同号，`-7 % 2 == -1`。
    - 除数为零是未定义行为，浮点除法也一样。
    - 商不可表示时 `/` 和 `%` 都是未定义行为，所以 `INT_MIN / -1` 和 `INT_MIN % -1` 都是 UB。

## 结合性（¶1）

¶1 `*`、`/`、`%` 处在同一优先级，从左往右结合：`a / b * c` 是 `(a / b) * c`。整数运算会截断，所以顺序会改变结果：

```cpp run title="mul-assoc.cpp" ok
int main() {
    int a = 7, b = 2, c = 3;
    int x = a / b * c;     // (7 / 2) * 3 = 3 * 3 = 9
    int y = a * c / b;     // (7 * 3) / 2 = 21 / 2 = 10
    return (x == 9 && y == 10) ? 0 : 1;
}
```

先乘后除保留的精度多，但中间结果更容易溢出。编译器不会替你重排，因为整数乘除不满足结合律，重排还可能改变是否溢出。

乘性表达式的操作数是 *pm-expression*，也就是成员指针表达式（[[expr.mptr.oper]]），所以 `a * s.*pm` 是 `a * (s.*pm)`。

## 操作数与结果类型（¶2）

```cpp title="mul-types.cpp" error
enum class Color { red, green };
enum E1 { e1 };
enum E2 { e2 };

auto a = 5.0 % 2;           // error: % 不接受浮点
auto b = Color::red * 2;    // error: 有作用域枚举不参与算术
auto c = e1 * e2;           // error: 两个不同的枚举类型
auto d = e1 * 2.0;          // error: 枚举与浮点混合
auto e = e1 * 2;            // OK：e1 先提升为 int
```

¶2 `*` 和 `/` 的操作数必须是算术类型或无作用域枚举类型；`%` 的操作数必须是整型或无作用域枚举类型，浮点取余要用 `std::fmod`。操作数先经过**常用算术转换**（usual arithmetic conversions，[[expr.arith.conv]]），把两边变成同一个类型，这个类型就是结果类型。

`c`、`d` 两行在 C++20/23 中只是弃用，C++26 由 [[P2864R2]] 改为非良构（[[diff.cpp23.expr]]）。

### 整数提升带来的溢出

常用算术转换的第一步是**整数提升**（[[conv.prom]]）：比 `int` 窄的类型，如 `char`、`short`、`unsigned short`、`bool`，只要 `int` 能表示它的全部值，就先变成 `int`。于是两个 `unsigned short` 相乘，执行的是有符号的 `int` 乘法：

```cpp run title="mul-promotion-ub.cpp" ub flags="-std=c++2c -O0 -fsanitize=undefined"
int main() {
    unsigned short a = 65535;
    unsigned short b = 65535;
    unsigned r = a * b;   // UB: a、b 提升为 int，65535 * 65535 超出 32 位 int
    return r == 0;
}
```

写代码的人以为这是无符号运算，结果会按模回绕，实际上是有符号溢出。UBSan 报告 `signed integer overflow: 65535 * 65535 cannot be represented in type 'int'`。修正方法是先转换一个操作数：`unsigned(a) * b`。`uint16_t`、`uint8_t` 在 32 位 `int` 的平台上都有同样的问题。

## 乘法与溢出（¶3）

¶3 只说二元 `*` 表示乘法。结果超出范围时怎么办，由 [[expr.pre#4]] 统一规定：`*`、`/`、`%` 以及 `+`、`-` 都是**算术表达式**，如果数学结果既不在结果类型的可表示范围内，也不是该类型拥有的 ±∞ 或 NaN，行为未定义。

- 有符号整数：超出范围就是 {{ub}}。C++20 规定有符号整数用二进制补码表示，但只定义了表示和转换，算术溢出仍然是 UB。
- 无符号整数：运算按模 2<sup>N</sup> 进行，结果总在范围内，不会溢出（[[basic.fundamental]]）。
- 遵循 IEC 60559（即 IEEE 754）的浮点类型：溢出得到 ±∞，这是该类型拥有的值，所以有定义。不过，有限操作数产生无穷或 NaN 的表达式不是核心常量表达式（[[expr.const.core]]）。

## 除法与取余（¶4）

### 除以零

!!! std
    If the second operand of / or % is zero, the behavior is undefined.

这条对浮点同样成立。[[expr.pre#4]] 的注 4 指出，对 IEC 60559 类型，除以零是算术表达式唯一的未定义行为。运行期实际得到的通常是硬件给出的 ∞ 或 NaN，但在常量求值中，任何 UB 都使表达式不再是常量表达式：

```cpp title="mul-div-zero-const.cpp" error
constexpr double x = 1.0 / 0.0;   // error: 不是常量表达式（除以零）
constexpr int    y = 5 % 0;       // error: 不是常量表达式（除以零）
```

`-fsanitize=undefined` 默认不检查浮点除以零，要另加 `-fsanitize=float-divide-by-zero`。标准说它是 UB，实现按 IEEE 给了它结果，sanitizer 的默认值反映的是后者。

### 向零截断与余数的符号

¶4 对整型操作数，`/` 得到代数商并丢弃小数部分，脚注称之为**向零截断**（[[g:truncation-toward-zero]]）：`-7 / 2` 是 `-3`，不是向下取整的 `-4`。

接着 ¶4 用一个恒等式定义 `%`：如果商 `a/b` 在结果类型中可表示，那么 `(a/b)*b + a%b == a`。由向零截断和这个恒等式可以推出，余数要么为零，要么与被除数 `a` 同号，与除数的符号无关：

```cpp run title="mul-sign.cpp" ok
static_assert( 7 /  2 ==  3 &&  7 %  2 ==  1);
static_assert(-7 /  2 == -3 && -7 %  2 == -1);   // 余数随被除数为负
static_assert( 7 / -2 == -3 &&  7 % -2 ==  1);   // 除数的符号不影响余数
static_assert(-7 / -2 ==  3 && -7 % -2 == -1);

int main() {}
```

所以用 `x % 2 == 1` 判断奇数，对负奇数不成立，应该写 `x % 2 != 0`。需要非负的模，比如环形缓冲区下标，要自己修正：`((a % n) + n) % n`。

C++ 不像 Python 那样让余数与除数同号，是因为 x86 的 `idiv`、ARM 的 `sdiv` 等除法指令都向零截断。语言直接映射硬件，有符号除法就只需一条指令。

!!! history "C++11 之前"
    C++98/03 只规定两个操作数都非负时余数非负，其他情况下余数的符号由实现定义，脚注建议向零截断。C99 把向零截断定为要求，C++11 跟进。当时的硬件几乎都向零截断，所以这次修改没有影响实际代码。

### 商不可表示：`INT_MIN / -1`

¶4 最后规定，商不可表示时 `a/b` 和 `a%b` 的行为都未定义。对二进制补码的 `int`，这只有一种情况：`INT_MIN / -1`，数学结果 2<sup>31</sup> 比 `INT_MAX` 大 1。

```cpp title="mul-intmin.cpp" error
#include <climits>

constexpr int q = INT_MIN / -1;   // error: 不是常量表达式（商不可表示）
constexpr int r = INT_MIN % -1;   // error: 不是常量表达式（同样是 UB）
```

`INT_MIN % -1` 的数学值是 0，完全可以表示，它也是 UB，原因在硬件。x86 的 `idiv` 同时算出商和余数，商溢出时触发与除以零相同的异常。如果标准要求 `INT_MIN % -1 == 0`，编译器就得在每个可能为 `-1` 的除数前插入分支；定为 UB 后，一条 `idiv` 就够了。

!!! impl "实现视角"
    - x86/x86-64：`idiv` 在除数为 0 或商溢出时触发 #DE，Linux 上表现为 `SIGFPE`，提示 "Floating point exception"，尽管与浮点无关。
    - AArch64：`sdiv` 不陷入，除以零得 0，`INT_MIN / -1` 得 `INT_MIN`。同一个 UB 程序在 ARM 上不崩溃，而是给出错误结果。
    - 除以常量：编译器把 `x / 10` 改写成乘以一个常数再移位，因为乘法比除法快得多。有符号数除以 2 的幂不能直接算术右移（右移向负无穷舍入，见 [[expr.shift]]），要先给负数加上 2<sup>k</sup> − 1 再移位，所以 `int` 的 `x / 2` 比 `unsigned` 的多几条指令。
    - UBSan：`signed-integer-overflow` 和 `integer-divide-by-zero` 包含在 `undefined` 中，`float-divide-by-zero` 要单独开启。

## 常见误解

!!! pitfall "`%` 是数学模运算"
    C++ 的 `%` 是截断取余，结果随被除数的符号。`-1 % 5 == -1`，不是 4。

!!! pitfall "C++20 的二进制补码让有符号溢出有定义了"
    C++20 规定的是有符号整数的表示和转换。算术溢出仍然是 UB，`INT_MIN / -1` 也仍然是 UB。

!!! pitfall "浮点除以零一定得到 ∞"
    那是 IEEE 754 的规定，不是 C++ 的。对 IEC 60559 类型，溢出到 ∞ 有定义，除以零却仍是 UB；在要求常量表达式的地方，它会让程序非良构。

## 思考题

!!! question "思考题 1"
    设 `int` 为 32 位。`long long x = INT_MIN;` 之后 `x / -1` 有定义吗？`INT_MIN / -1LL` 呢？`INT_MIN / -1u` 呢？

<details markdown="1">
<summary>答案</summary>

- `x / -1`：`-1` 经常用算术转换变为 `long long`，商 2<sup>31</sup> 在 `long long` 中可表示，有定义，结果是 2147483648。
- `INT_MIN / -1LL`：同理，`INT_MIN` 转换为 `long long`，有定义。
- `INT_MIN / -1u`：`-1u` 是值为 4294967295 的 `unsigned int`，常用算术转换把 `INT_MIN` 转成 `unsigned int` 的 2147483648，无符号除法得 0。有定义，但多半不是想要的结果。
</details>

!!! question "思考题 2"
    `short a = -32768; short b = -1; short c = a / b;` 有没有未定义行为？

<details markdown="1">
<summary>答案</summary>

除法本身没有。`a`、`b` 先提升为 `int`，`-32768 / -1` 得 `int` 的 32768，可以表示。之后把 32768 转回 `short` 是整数转换，C++20 起结果按模定义为 -32768（[[conv.integral]]），也不是 UB。
</details>

## 小结

| 情形 | 结果 | 依据 |
|---|---|---|
| `%` 用于浮点；有作用域枚举参与算术 | {{ill-formed}} | ¶2 |
| 不同枚举之间、枚举与浮点混合 | {{ill-formed}}（C++26；之前弃用） | ¶2、[[expr.arith.conv]] |
| 除数为零（整数或浮点） | {{ub}} | ¶4 |
| 整数除法 | 向零截断 | ¶4 |
| 余数的符号 | 与被除数相同 | ¶4 |
| `INT_MIN / -1`、`INT_MIN % -1` | {{ub}} | ¶4 |
| 有符号乘法溢出 | {{ub}} | [[expr.pre#4]] |
| IEC 60559 浮点溢出 | ±∞，有定义，但不是常量表达式 | [[expr.pre#4]] |
| 无符号乘法 | 模 2<sup>N</sup> | [[basic.fundamental]] |
