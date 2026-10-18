---
title: 表达式序言
summary: 什么是表达式；重载运算符与内置运算符的关系；算术表达式在数学结果不可表示时为 UB；实现何时可以重组运算；浮点的超额精度
status: draft
related: expr, intro.execution, expr.mul, over.match.oper, basic.fundamental, expr.const.core
tags: 表达式, UB, 运算符重载, 浮点
updated: 2026-10-17
---

[expr.pre] 是第 7 章的开场白。它很短，但其中有两处在 language lawyer 的日常讨论中经常被引用：

1. ¶4：如果算术表达式的数学结果不在类型可表示的范围内，行为未定义。"有符号整数溢出是 UB"这一说法就出自这里。
2. ¶2/¶3：重载运算符遵守内置运算符的语法与求值顺序，但内置运算符本身不能重新定义。

其余段落是注释（不具规范效力）或对实现自由度的说明（重组运算、超额精度）。本章的整体结构以及优先级如何从语法推导，见 [[expr]]。

## 什么是表达式（¶1）

¶1（注释）表达式是**运算符与操作数组成的序列，它规定了一项计算**；表达式可以产生一个值，也可以产生副作用（side effect）。

有两点值得强调：

- 这里说的是"可以"。表达式不一定有值（`void` 类型的函数调用、`throw` 表达式），也不一定有副作用（`1 + 2`）。
- 标准中的"表达式"指语法结构，值类别和类型都是表达式的静态性质（[[expr.prop]]）；求值（evaluation）则是运行时（或常量求值时）的动作，包括值计算（value computation）和副作用的发起（[[intro.execution]]）。

## 重载运算符：守语法与顺序，不守类型要求（¶2）

¶2（注释）运算符可以重载，即为类类型或枚举类型的操作数赋予含义。使用重载运算符时，表达式按 [[over.oper]] 变换为函数调用。要点如下：

| 方面 | 重载运算符的处理 |
|---|---|
| 语法（优先级、结合性、元数） | 与内置运算符完全相同 |
| 求值顺序 | 与内置运算符相同（[[over.match.oper#2]]） |
| 操作数的类型与值类别要求 | 由函数调用规则代替：看参数类型 |
| 运算符之间的关系（如 `++a` ≡ `a += 1`） | **不保证** |

求值顺序相同这一条是 C++17 的变化。在此之前，`a << b` 改写为 `operator<<(a, b)` 后，两个实参的求值顺序是未指定的，所以经典的 `std::cout << i++ << i++` 是 UB。从 C++17 起，内置 `<<` 规定左操作数先于右操作数求值，这一顺序也适用于重载版本。

```cpp run title="seq.cpp" ok
#include <iostream>

int main() {
    int i = 0;
    std::cout << i++ << ' ' << i++ << '\n';  // C++17 起保证输出 "0 1"
}
```

但要注意，顺序相同不等于短路行为相同。重载的 `&&`、`||` 是普通的函数调用，两个操作数**都会被求值**。

```cpp run title="no-short-circuit.cpp" ok
#include <cstdio>

struct B { bool v; };
B operator&&(B a, B b) { return {a.v && b.v}; }

B noisy(bool v) { std::puts("evaluated"); return {v}; }

int main() {
    B r = B{false} && noisy(true);   // 仍会打印 "evaluated"
    return r.v;
}
```

类型与值类别要求由函数调用规则代替，举例来说：内置 `=` 要求左操作数是可修改左值（[[expr.assign]]），而类的 `operator=` 是普通成员函数，所以 `std::string() = "x"` 是合法的。这里是在一个纯右值上调用成员函数，临时量被实质化（[[conv.rval]]）。

## 内置运算符不可改写，但参与重载决议（¶3）

¶3 [[expr.compound]] 描述的是运算符作用于未重载的类型时的效果。运算符重载**不得修改内置运算符的规则**，也就是说，不能为两个 `int` 重新定义 `+`。这一点由 [[over.oper]] 的要求保证：运算符函数至少要有一个参数是类类型或枚举类型（或其引用）。

```cpp error
int operator+(int, int);   // error: 运算符函数至少要有一个类或枚举类型的参数
```

不过内置运算符会**参与重载决议**。[[over.built]] 为每个运算符列出了一组假想的内置候选函数，例如 `int operator+(int, int)`。如果某个类类型的操作数能经用户定义转换变成 `int`，内置候选就可能胜出；这时先对操作数施行用户定义转换，再按 [[expr.compound]] 的内置规则继续。

```cpp ok
struct Meters {
    double v;
    operator double() const { return v; }   // 非 explicit 转换函数
};

double total(Meters a, Meters b) {
    return a + b;    // 选中内置候选 operator+(double, double)；
                     // 两个操作数先经 Meters::operator double() 转换
}
```

!!! note
    这也是给类加一个隐式 `operator bool` 会带来大量意外的原因：`a + b`、`a < 1` 等表达式都可能经由内置候选变得合法。C++11 引入 `explicit operator bool` 正是为了解决这个问题，它只在按语境转换为 bool 的场合起作用（[[conv#4]]）。

## 算术表达式的 UB（¶4）

¶4 是本节唯一一段分量较重的规范性文字。它先定义**算术表达式**（[[g:arithmetic-expression]]）：

- 一元 `+`、`-`（[[expr.unary.op]]），
- 加法、减法（[[expr.add]]），
- 乘法、除法、取余（[[expr.mul]]），

并且每个（可能经过转换的）操作数都是算术类型。由此可知：

- 指针算术 `p + 1` 不是算术表达式（操作数不全是算术类型），它的 UB 由 [[expr.add]] 单独规定。
- 移位 `<<`、`>>` 不在列表里，它的 UB（负数位移量、位移量 ≥ 宽度）由 [[expr.shift]] 规定。
- 复合赋值 `+=`、自增 `++` 等不在列表里，但它们是按算术表达式定义的（注 3），所以同样受本条约束。

然后是核心规则：

!!! std
    The behavior of evaluating an arithmetic expression is undefined if the mathematical result is neither in the range of representable values for its type nor a negative infinity, positive infinity, or NaN that is among the values of the type.

    若数学结果既不在该类型可表示值的范围内，也不是该类型所具有的 ±∞ 或 NaN，则求值行为未定义。

下面逐个类型看它的含义：

| 类型 | 数学结果 | 结论 |
|---|---|---|
| 有符号整数 | 超出 `[min, max]` | {{ub}}，即"有符号溢出是 UB" |
| 无符号整数 | 算术本身按模 2<sup>N</sup> 定义（[[basic.fundamental#2]]） | 结果总在范围内，不会溢出 |
| IEEE 754 浮点 | 可表示范围是整条扩展实数轴；溢出舍入为 ±∞，0/0 之外的非法运算得 NaN | 除以零之外都不是 UB（注 4） |
| 非 IEEE 浮点（理论上） | 溢出 | {{ub}} |
| 任意类型 | 除数为零 | {{ub}}（由 [[expr.mul#4]] 单独规定） |

```cpp run title="overflow.cpp" ub
#include <climits>
#include <cstdio>

int main(int argc, char**) {
    int big = INT_MAX - 1 + argc;    // argc == 1 时为 INT_MAX
    unsigned u = UINT_MAX;
    u = u + 1;                       // OK：无符号按模运算，u == 0
    int bad = big + 1;               // UB：数学结果 INT_MAX+1 不可表示
    int q = INT_MIN / -argc;         // UB：数学结果 2^31 不可表示（argc == 1）
    std::printf("%u %d %d\n", u, bad, q);
}
```

用 `-fsanitize=undefined` 运行时，UBSan 会在这两处 UB 分别报告 signed integer overflow 和 division overflow。

!!! ub "为什么有符号溢出是 UB 而不是回绕"
    从 C++20 起，有符号整数必须用二进制补码表示（[[basic.fundamental]]），但溢出**仍然是 UB**，这是有意保留的。理由是优化：编译器可以假设 `i + 1 > i` 恒为真，可以把 `int` 循环变量提升为 64 位索引而不必模拟 32 位回绕，还可以做强度削减与向量化。需要回绕语义时请用无符号类型；需要饱和语义时，可以用 C++26 `<numeric>` 中的 `std::add_sat` 等饱和算术函数。

### 注 4：IEEE 浮点与常量表达式

注 4 指出，如果操作数类型符合 ISO/IEC 60559（IEEE 754），**除以零是唯一会导致 UB 的算术表达式**；但有些在运行时定义良好的浮点表达式不是核心常量表达式。[[expr.const.core]] 把下列算术表达式排除在常量表达式之外：

- 所有操作数有限但结果非有限（溢出到 ∞）；
- 任一操作数是 signaling NaN；
- 没有操作数是 NaN 但结果是 NaN（如 `inf * 0`、`inf - inf`）。

换句话说，运行时可以得到 ∞ 和 NaN，但编译期不允许凭空产生它们；已有的 ∞ 和 quiet NaN 可以参与运算并传播。下面改编自标准的例子（标准用 `std::float32_t`，这里用 `double`，并假设它符合 IEEE binary64）：

```cpp
#include <limits>
constexpr double mx  = std::numeric_limits<double>::max();
constexpr double inf = std::numeric_limits<double>::infinity();
constexpr double nan = std::numeric_limits<double>::quiet_NaN();

constexpr double inf2 = inf * 2;   // OK：∞ 的传播
constexpr double nan2 = nan * 2;   // OK：NaN 的传播（标准如此；见下方实现说明）
constexpr double tiny = std::numeric_limits<double>::min() / mx;  // OK：下溢舍入为 0
constexpr double oflo = mx * 2;    // error: 有限操作数产生非有限结果（标准如此；见下方实现说明）
constexpr double udef = inf * 0;   // error: 无 NaN 操作数却产生 NaN
constexpr double div0 = mx / 0;    // error: 除以零是 UB
```

!!! impl "Clang 与标准例子的分歧"
    截至写作时，Clang 23 对上例的判断与标准有两处不同：它拒绝 `nan2`（把有 NaN 参与的运算一律视为非常量），却接受 `oflo`（允许常量求值中溢出到 ∞）。对 `udef` 与 `div0`，两者都拒绝。这是标准较新的措辞（把非有限结果的规则写进 [[expr.const.core]]）与实现之间的差距，编写编译期浮点代码时不要依赖这些边界情况。

¶4 的注 5 只是提醒：对除以零、以零为除数取余以及各种浮点异常的处理因机器而异，有时可以通过库函数调整（如 `<cfenv>` 的浮点环境）。

## 实现只能在真正满足结合律时重组（¶5）

¶5（注释）实现**只有在运算真正满足结合律或交换律时**，才能按数学规则重组运算。标准举的例子是：在溢出会触发异常的机器上，`a = a + 32760 + b + 5;` 必须按 `((a + 32760) + b) + 5` 计算，不能改写成 `(a + b) + 32765`，因为原表达式不溢出时，后者可能溢出。而在溢出会回绕、结果可逆的机器上，这些改写都是允许的。这正是 as-if 规则（[[intro.abstract]]）的体现：只要可观察行为不变，实现可以用任何方式计算。

脚注强调，实现永远不能假定重载运算符满足结合律或交换律。

对今天的读者来说，这一段最实用的推论是：浮点加法不满足结合律，所以编译器在默认模式下不能把 `(a + b) + c` 重排为 `a + (b + c)`，也不能自动向量化浮点归约。GCC/Clang 的 `-ffast-math`（具体是其中的 `-fassociative-math`）就是让编译器放弃这一保证。

```cpp run title="assoc.cpp" ok
#include <cstdio>
int main() {
    double a = 1e16, b = -1e16, c = 1.0;
    std::printf("%g %g\n", (a + b) + c, a + (b + c));  // 打印 "1 0"
}
```

## 浮点超额精度（¶6）

¶6 浮点操作数的值和浮点表达式的结果**可以用比类型要求更高的精度和范围表示**，类型并不因此改变。这是为 x87 这类寄存器为 80 位扩展精度的硬件准备的：`float` 运算可以在 80 位寄存器里完成，中间结果不必舍入到 `float`。

脚注补充说，强制转换和赋值仍然必须执行它们规定的转换。也就是说，在 `(float)x`、`static_cast<double>(e)` 或赋值给变量时，必须丢掉多余的精度。程序员可以借此强制舍入。

!!! impl "实现视角"
    - 现代 x86-64 默认用 SSE2 做标量浮点运算，`FLT_EVAL_METHOD` 为 0，基本不存在超额精度；32 位 x86 使用 x87 时，`FLT_EVAL_METHOD` 通常为 2。
    - GCC 在 x87 上默认并不严格遵守赋值时丢弃超额精度的要求，需要加 `-ffloat-store` 或 `-fexcess-precision=standard`。
    - 浮点收缩（contraction，把 `a * b + c` 融合成一条 FMA 指令）通常也被认为利用了这一自由度，Clang 用 `-ffp-contract=` 控制它。

## 历史与演进

!!! history
    - C++98–C++17：¶4 的措辞是"若在表达式求值过程中，结果在数学上未定义或不在其类型可表示值范围内，行为未定义"。这句话适用于一切表达式，范围宽泛而模糊（例如没有说清浮点 ∞ 的地位）。
    - C++17：[[P0145R3]] 细化了求值顺序，并规定重载运算符遵循对应内置运算符的定序规则，使 `std::cout << i++ << i++` 成为良定义。
    - C++20：有符号整数规定为二进制补码（[[P1236R1]]），但溢出仍是 UB。
    - 当前草案（C++26）：¶4 改写为只针对算术表达式的规则，明确了 ±∞ 和 NaN 的地位，并在 [[expr.const.core]] 中补上了非有限结果不是常量表达式的规则（注 4 的例子）。

## 陷阱

!!! pitfall "整型提升让无符号运算溢出"
    对于 `unsigned short a = 65535, b = 65535; auto c = a * b;`，两个操作数先经整型提升变为 `int`（[[conv.prom]]），乘积 4294836225 超出 32 位 `int` 的范围，**属于有符号溢出，是 UB**，尽管源代码里一个有符号类型都没写。改成 `1u * a * b` 才安全。

!!! pitfall "溢出检查被优化掉"
    对有符号的 `x`，`if (x + 1 < x) handle_overflow();` 毫无用处。溢出本身就是 UB，编译器可以假设它不会发生，从而把整个条件折叠为 `false`。正确的做法是先比较，如 `if (x == INT_MAX)`，或者使用 `__builtin_add_overflow` 或 C++26 的 `std::add_sat`。

## 思考题

!!! question "1. `-INT_MIN` 是 UB 吗？`0u - 1` 呢？"

<details markdown="1">
<summary>答案</summary>

`-INT_MIN` 是 UB。一元 `-` 是算术表达式（¶4.1），数学结果 2<sup>31</sup> 不能用 `int` 表示。（注意 `-2147483648` 本身也是一元负号作用于字面量 2147483648，而在 32 位 `int` 平台上，这个字面量的类型是 `long` 或 `long long`，所以这个表达式反而没有问题。）

`0u - 1` 是良定义的。寻常算术转换后，两个操作数都是 `unsigned`，无符号算术按模 2<sup>N</sup> 定义，结果是 `UINT_MAX`。
</details>

!!! question "2. 在一个所有浮点类型都符合 IEEE 754 的实现上，`double d = 1e308 * 10;` 在运行时是 UB 吗？写成 `constexpr double d = 1e308 * 10;` 呢？"

<details markdown="1">
<summary>答案</summary>

运行时不是 UB。IEEE 类型的值集包含 +∞，结果舍入到 +∞；按注 4，只有除以零是 UB。

写成 `constexpr` 时，按标准是非良构的。[[expr.const.core]] 规定，所有操作数有限而结果非有限的算术表达式不是核心常量表达式。（Clang 23 实际上接受这种写法，见上文的实现说明。）
</details>

!!! question "3. 为什么 `std::cout << f() << g();` 在 C++17 中保证先调用 `f` 再调用 `g`，而 `h(f(), g())` 不保证？"

<details markdown="1">
<summary>答案</summary>

`std::cout << f() << g()` 解析为 `(std::cout << f()) << g()`，改写为 `operator<<(operator<<(std::cout, f()), g())`。C++17 规定内置 `<<` 的左操作数先序于右操作数，而 [[over.match.oper#2]] 要求重载运算符的操作数按内置运算符规定的顺序定序，所以 `f()` 所在的左操作数（整个内层调用）先于 `g()` 求值。

`h(f(), g())` 是普通的函数调用。[[expr.call]] 只规定各实参的初始化之间**不确定定序**（indeterminately sequenced），没有规定先后。
</details>

## 小结

!!! summary
    - 重载运算符的语法和求值顺序与内置运算符相同，类型与值类别要求、运算符间的恒等式则不同；`&&`/`||`/`,` 重载后不短路（`,` 仍然左先于右）。
    - 内置运算符不能重新定义，但作为 [[over.built]] 的候选参与重载决议。
    - 算术表达式（一元 ±、加减乘除余）的数学结果不可表示即为 UB：有符号溢出是 UB，无符号按模运算不会溢出，IEEE 浮点只有除以零是 UB。
    - 常量求值更严格：不能凭空产生 ∞ 或 NaN。
    - 实现只能在运算真正满足结合律时重组；浮点可以有超额精度，但转换与赋值必须舍入。
