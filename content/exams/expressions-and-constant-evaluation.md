---
title: 第五卷 · 表达式、求值顺序与常量求值
summary: 25 道题，考查求值顺序、整数提升与算术转换、移位与越界转换、指针比较、条件运算符、lambda 捕获与闭包类型、结构化绑定，以及常量求值、立即函数与静态初始化顺序；重点是分清 UB、未指明行为和实现定义行为。
status: done
order: 5
tags: 求值顺序, 算术转换, UB, lambda, 结构化绑定, 常量求值, 考卷
updated: 2026-10-20
---

!!! tldr
    - 范围：[[intro.execution]] 的有序、不确定顺序与无序；整数提升、寻常算术转换、移位、除法、浮点与枚举转换；指针比较；条件运算符与逗号运算符的值类别；lambda 捕获、闭包类型、结构化绑定；[[expr.const]] 的核心常量表达式、`consteval` 与立即升级、`constinit`、`std::is_constant_evaluated`、编译期动态分配；跨翻译单元的动态初始化顺序。
    - 题型：判定题 15 道、选择题 7 道、简答题 3 道，难度大致递增。
    - 判定题按整个程序中最重的一项作答。除非题目另有说明，假定 `short` 为 16 位、`int` 为 32 位。
    - 建议用时 90 分钟。答完先自己写出条款号，再展开解析核对。

## 一、求值顺序

<div class="quiz" data-kind="verdict" data-answer="ok" markdown="1">

判定这个程序。

```cpp run
int main() {
    int i = 0;
    i = i++ + 1;
    return i;
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：良构，行为确定，`main` 返回 1。**

1. [[intro.execution#10]] 规定，同一内存位置上的一个副作用，如果和另一个副作用或一次取值无序，行为未定义。这里涉及 `i` 的副作用有两个：`i++` 的自增和 `=` 的写入。
2. [[expr.assign#1]] 规定赋值的右操作数先于左操作数求值，而赋值本身在两个操作数的值计算之后发生。按 [[intro.execution#8]] 末句，右操作数先于左操作数，意味着右操作数的全部值计算和副作用都在前。所以 `i++` 的自增先完成，然后才写入 `0 + 1`。
3. [[intro.execution#10]] 的例 3 就有这一行，注释是 the value of i is incremented。

选 `ub` 是 C++14 的答案。那时赋值的副作用只排在操作数的值计算之后，和 `i++` 的副作用之间没有顺序。C++17 通过 [[P0145R3]] 补上了右先左后的规则。

改一处就变成 UB：右操作数里再读一次 `i`。`+` 的两个操作数之间仍然无序，`i++` 的修改与另一边对 `i` 的读取冲突。

```cpp ub
int main() {
    int i = 0;
    i = i++ + i;
    return i;
}
```

更多例子见 [[topics/order-of-evaluation]]。

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="unspecified" markdown="1">

判定这个程序。

```cpp run
#include <cstdio>

void f(int a, int b) { std::printf("%d %d\n", a, b); }

int main() {
    int i = 0;
    f(i++, i++);
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：未指明行为。输出 `0 1` 或 `1 0`，不是 UB。**

1. [[expr.call#8]]：每个形参的初始化，连同其中的全部值计算和副作用，与其他形参的初始化是不确定顺序（indeterminately sequenced）的。
2. [[intro.execution#8]]：不确定顺序的两个求值一定是一先一后，只是未指明谁先，不会交错。
3. 两个 `i++` 因此不是无序的，[[intro.execution#10]] 的 UB 条件不成立。剩下的只是顺序未指明，属于 [[intro.abstract#3]] 所说的未指明行为。

本机 Clang 23 输出 `0 1`，同时给出 `-Wunsequenced` 警告（multiple unsequenced modifications）。按 C++17 起的规则，这个警告是误报：两次修改并非无序。C++14 中实参之间确实无序，那时这一行是 UB。

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="D" markdown="1">

下面四行分别单独出现在 `test` 中（`i` 的初值为 0）。哪一行有未定义行为？

```cpp
void f(int, int) {}

void test() {
    int i = 0;
    int a[4]{};
    a[i] = i++;                       // A
    i = (i++, i);                     // B
    f(i = 1, i = 2);                  // C
    (void)((i = 1, 0) + (i = 2, 0));  // D
}
```

- A. `a[i] = i++;`
- B. `i = (i++, i);`
- C. `f(i = 1, i = 2);`
- D. `(i = 1, 0) + (i = 2, 0)`

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：D。**

- D：逗号运算符只保证各自括号里左先右后（[[expr.comma#1]]）。`+` 的两个操作数之间无序（[[intro.execution#10]] 首句），于是两次对 `i` 的赋值彼此无序，是 UB。[[intro.execution#10]] 例 3 的 `(u.x = 1, 0) + (u.y = 2, 0)` 是同一个结构，那里两个联合体成员占用同一内存位置。
- A：[[expr.assign#1]] 右操作数先求值，`i++` 得 0，`i` 变为 1；然后求值左操作数 `a[1]`，写入 0。行为确定。
- B：逗号运算符让 `i++` 的副作用先于右边对 `i` 的读取（[[expr.comma#1]]），整个逗号表达式又是赋值的右操作数，先于赋值。结果 `i == 1`。
- C：实参初始化之间是不确定顺序（[[expr.call#8]]），不会交错，最终 `i` 是 1 还是 2 未指明，但不是 UB。

Clang 对 C 和 D 都给出 `-Wunsequenced`，其中 C 是误报。只看警告会把 C 也判成 UB。

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ok" markdown="1">

判定这个程序。

```cpp run
constexpr int f() {
    int i = 0;
    return i++ + i++;
}
static_assert(f() == 1);

int main() {}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：良构。**

1. `static_assert` 的条件是常量表达式，`f()` 作为核心常量表达式求值。
2. [[intro.execution#16]] 规定：作为核心常量表达式求值时，原本无序或不确定顺序的操作数和子表达式按词法顺序求值。所以左边的 `i++` 先完成（值 0，`i` 变为 1），再求右边的 `i++`（值 1），结果是 1。
3. 两次修改已经有了先后，[[intro.execution#10]] 的 UB 不出现，[[expr.const.core#2.8]] 也就没有要诊断的未定义操作。

容易选 `error`：一般情况下，常量求值遇到 UB 就不是常量表达式。但这里在常量求值中根本没有 UB。这条按词法顺序的规则是 C++23 之后的新措辞。

本机 Clang 23 接受这段代码，同时对 `return` 一行给出 `-Wunsequenced` 警告。警告是有道理的：同一个函数在运行期被调用时，[[intro.execution#16]] 不适用，`i++ + i++` 仍然是 UB。

```cpp ub
constexpr int f() {
    int i = 0;
    return i++ + i++;
}

int main() { return f(); }   // 不是显然常量求值的语境，按运行期规则求值
```

</details>
</div>

<div class="quiz" data-kind="open" markdown="1">

这个程序在 C++17 起返回什么？用 [[expr.assign]] 的规则一步步推出结果，并说明 C++14 中它为什么是 UB。

```cpp run
int main() {
    int x = 3, y = 5;
    x ^= y ^= x ^= y;
    return x * 10 + y;
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：返回 53，即 `x == 5`、`y == 3`。**

1. 赋值运算符从右向左结合（[[expr.assign#1]]），表达式是 `x ^= (y ^= (x ^= y))`。
2. 对最外层的 `^=`：右操作数 `y ^= (x ^= y)` 整体先于左操作数 `x` 求值，复合赋值本身又在两个操作数的值计算之后进行（[[expr.assign#1]]）。[[expr.assign#6]] 说 `E1 op= E2` 等价于 `E1 = E1 op E2`，只是 `E1` 只求值一次；复合赋值读取 `x` 的旧值发生在这一步，因此读到的是内层已经修改过的值。
3. 同样的道理逐层向内：
    - 最内层 `x ^= y`：`x = 3 ^ 5 = 6`；
    - 中间层 `y ^= 6`：`y = 5 ^ 6 = 3`；
    - 最外层 `x ^= 3`：`x = 6 ^ 3 = 5`。
4. 本机实测返回 53。

C++14 中赋值只规定了副作用在操作数的值计算之后，没有规定右操作数的副作用先于左操作数。两次对 `x` 的写入之间其实有先后（内层赋值的副作用先于内层的值计算，外层赋值又在它之后），出问题的是读取：最外层 `^=` 读取 `x` 的旧值，和最内层对 `x` 的修改彼此无序，按当时的 [[intro.execution]] 规则是 UB。C++17 的 [[P0145R3]] 给赋值加上右先左后，这一行才有了确定的结果。

</details>
</div>

## 二、整数提升、算术转换与越界

<div class="quiz" data-kind="choice" data-answer="B" markdown="1">

这个程序输出什么？

```cpp run
#include <cstdio>

int main() {
    unsigned short us = 1;
    std::printf("%d %d %d\n", -1 < 0u, -1 < us, us - 2 < 0);
}
```

- A. `0 0 0`
- B. `0 1 1`
- C. `1 1 1`
- D. `0 1 0`

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：B，输出 `0 1 1`。**

1. `-1 < 0u`：关系运算符对算术操作数做寻常算术转换（[[expr.rel#3]]）。`int` 与 `unsigned int` 等级相同，按 [[expr.arith.conv#1.5.3.1]] 共同类型是 `unsigned int`。`-1` 按 [[conv.integral#3]] 取模变成 `UINT_MAX`，比较结果为假。
2. `-1 < us`：先做整数提升。`int` 能表示 `unsigned short` 的全部值，`us` 提升为 `int`（[[conv.prom#2]]），于是是两个 `int` 比较，结果为真。
3. `us - 2 < 0`：`us` 同样提升为 `int`，`1 - 2` 得 `-1`，小于 0，结果为真。

第 2、3 项依赖各整数类型的宽度，宽度由实现定义（[[basic.fundamental#4]]）。在 `int` 只有 16 位的平台上，`int` 放不下 `unsigned short` 的全部值，`us` 会提升为 `unsigned int`，输出变成 `0 0 0`。本机 Clang 23 输出 `0 1 1`，并对第二项给出 `-Wtautological-constant-out-of-range-compare` 警告。

想要按数学意义比较有符号和无符号数，用 `std::cmp_less`，见 [[topics/arithmetic]]。

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ub" markdown="1">

判定这个程序。

```cpp run
unsigned mul(unsigned short a, unsigned short b) {
    return a * b;
}

int main() {
    return mul(65535, 65535) == 4294836225u;
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：未定义行为。**

1. `a` 和 `b` 都是 `unsigned short`，在 `*` 之前按 [[conv.prom#2]] 提升为 `int`（`int` 能表示 `unsigned short` 的全部值）。[[expr.mul#2]] 的寻常算术转换之后，乘法在 `int` 上进行。
2. 数学结果 4294836225 超出 `int` 的范围。[[expr.pre#4]]：算术表达式的数学结果不在结果类型的可表示范围内，行为未定义。
3. 返回类型是 `unsigned` 不影响结论，转换发生在乘法之后。

容易选 `ok`：两个操作数都是无符号类型，看起来应该按无符号取模。但取模只是整数转换的规则（[[conv.integral#3]]），而这次乘法根本不是在无符号类型上做的。

把函数改成 `constexpr` 并放进 `static_assert`，Clang 报告 value 4294836225 is outside the range of representable values of type 'int'；运行期 UBSan 报告 signed integer overflow。先把一个操作数转成 `unsigned` 就有定义了：

```cpp run ok
constexpr unsigned mul(unsigned short a, unsigned short b) {
    return 1u * a * b;
}
static_assert(mul(65535, 65535) == 4294836225u);

int main() {}
```

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="C" markdown="1">

下面四个声明中，哪一个是非良构的？

```cpp
#include <climits>

constexpr int a = -1 << 31;        // A
constexpr int b = 1 << 31;         // B
constexpr unsigned c = 1u << 32;   // C
constexpr int d = -8 >> 1;         // D
```

- A. `a`
- B. `b`
- C. `c`
- D. `d`

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：C。**

1. C：[[expr.shift#1]] 规定，右操作数为负，或者不小于提升后左操作数的宽度，行为未定义。`unsigned int` 宽 32 位，移 32 位就是 UB，与左操作数是否无符号无关。常量求值中的 UB 使表达式不是核心常量表达式（[[expr.const.core#2.8]]），`constexpr` 变量又必须可以常量初始化（[[dcl.constexpr#6]]），所以 `c` 的声明非良构。Clang 的说明是 shift count 32 >= width of type 'unsigned int'。
2. A 和 B：C++20 起，`E1 << E2` 的值是与 E1×2^E2 模 2^N 同余的唯一值（[[expr.shift#2]]），N 是结果类型的宽度。两者都得到 `INT_MIN`。移位不属于 [[expr.pre#4]] 列出的算术表达式，所以不存在溢出 UB。
3. D：[[expr.shift#3]] 规定 `E1 >> E2` 是 E1/2^E2 向负无穷取整，结果是 -4。

C++20 之前，A 是 UB（左移负数），D 的结果由实现定义。C++20 规定有符号整数采用二进制补码（[[P1236R1]]），移位规则随之改写。本机 Clang 23 在 `-pedantic` 下对 A、B、D 都不报警告：

```cpp run ok
#include <climits>

constexpr int a = -1 << 31;
constexpr int b = 1 << 31;
constexpr int d = -8 >> 1;
static_assert(a == INT_MIN && b == INT_MIN && d == -4);

int main() {}
```

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ub" markdown="1">

判定这个程序。

```cpp run
#include <climits>

int rem(int a, int b) { return a % b; }

int main() {
    return rem(INT_MIN, -1);
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：未定义行为。**

[[expr.mul#4]] 的最后一句：如果商 `a/b` 不能用结果类型表示，`a/b` 和 `a%b` 的行为都未定义。`INT_MIN / -1` 的数学结果是 2^31，`int` 放不下，所以 `INT_MIN % -1` 也是 UB。

容易选 `ok`：数学上余数是 0，完全可以表示。标准把两者绑在一起，是因为常见硬件用同一条除法指令同时算出商和余数，商溢出时指令本身就会出错，例如 x86 的 `idiv` 会触发异常。

本机 UBSan 报告 division of -2147483648 by -1 cannot be represented in type 'int'。放进 `static_assert` 时 Clang 拒绝，并说明 2147483648 超出 `int` 的范围。除数换成 1 就没有问题：

```cpp run ok
#include <climits>

constexpr int rem(int a, int b) { return a % b; }
static_assert(rem(INT_MIN, 1) == 0);

int main() {}
```

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ub" markdown="1">

判定这个程序。

```cpp run
unsigned to_u(double d) { return d; }

int main() {
    return to_u(-1.0) == 0xFFFFFFFFu;
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：未定义行为。**

1. `return d;` 把 `double` 隐式转换为 `unsigned`，这是浮点到整数的转换。[[conv.fpint#1]]：先截断小数部分，截断后的值不能用目标类型表示时，行为未定义。
2. `-1.0` 截断后是 -1，`unsigned` 表示不了。

容易选 `ok` 并以为结果是 `UINT_MAX`。取模规则只属于整数之间的转换（[[conv.integral#3]]），源类型是浮点时不适用。

边界在截断之后：`to_u(-0.5)` 截断得到 0，可以表示，结果有定义。

```cpp run ok
constexpr unsigned to_u(double d) { return d; }
static_assert(to_u(-0.5) == 0);

int main() {}
```

把 `to_u(-1.0)` 放进 `constexpr` 变量的初始化器，Clang 报告 value -1 is outside the range of representable values of type 'unsigned int'；运行期 UBSan 给出同样的诊断。

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ok" markdown="1">

判定这个程序。

```cpp run
enum E { A = 1, B = 4 };
enum G { M = -1, N = 1 };

constexpr E e = static_cast<E>(7);
constexpr G g = static_cast<G>(-2);

int main() { return int(e) + int(g); }
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：良构，`main` 返回 5。**

1. 两个枚举都没有固定的底层类型。[[dcl.enum#8]] 规定它们的值域是能表示全部枚举项的、宽度最小的假想整数类型的值域，枚举项本身之外的值也属于这个枚举。
2. `E` 的枚举项是 1 和 4，都非负，3 位无符号类型就够，值域是 0 到 7。
3. `G` 的枚举项是 -1 和 1，需要有符号类型，2 位二进制补码可以表示 -2 到 1，值域就是这四个值。
4. [[expr.static.cast#8]]：值在枚举的值域内就保持不变，否则行为未定义。7 和 -2 都在值域内，所以两个初始化都是常量表达式。

容易选 `error` 或 `ub`，理由是没有值为 7 或 -2 的枚举项。值域按位宽算，不按枚举项列举。

越出值域一位就是 UB，放在常量求值中就成为非良构。Clang 的说明是 integer value 8 is outside the valid range of values [0, 7] for the enumeration type 'E'：

```cpp error
enum E { A = 1, B = 4 };
enum G { M = -1, N = 1 };

constexpr E e = static_cast<E>(8);     // error: 超出 [0, 7]
constexpr G g = static_cast<G>(-3);    // error: 超出 [-2, 1]
```

如果写成 `enum E : int { ... }`，底层类型固定，值域就是 `int` 的全部值（[[dcl.enum#8]] 第一句）。

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

按当前草案判定这个程序。

```cpp run
enum Color { Red, Green };
enum Fruit { Apple, Banana };

int main() {
    return Red + Apple;
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：非良构。**

`+` 对两个操作数做寻常算术转换（[[expr.add]]）。[[expr.arith.conv#1.3]]：一个操作数是枚举类型，另一个是不同的枚举类型或浮点类型时，表达式非良构。

这种写法在 C++20 被弃用，C++26 通过 [[P2864R2]] 删除，现在是硬性错误。选 `ok` 是 C++17 及以前的答案，那时两个枚举都先提升为 `int`。本机 Clang 23 在 `-std=c++2c` 下报错 invalid arithmetic between different enumeration types，诊断组名是 `-Wenum-enum-conversion`，但在这个模式下默认就是错误。

规则只挡住枚举与另一种枚举、枚举与浮点的组合：

```cpp run ok
enum Color { Red, Green };
enum Fruit { Apple, Banana };

int a = Red + 1;         // 枚举与整数：提升后相加
int b = +Red + Apple;    // 一元 + 先做整数提升，左操作数已是 int

int main() { return a + b; }
```

一元 `+` 对枚举做整数提升（[[expr.unary.op#7]]），所以第二行是 `int` 加枚举，不受 1.3 限制。`Red == Apple` 和 `Red + 1.0` 同样非良构，相等运算符也做寻常算术转换（[[expr.eq#9]]）。

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="impl" markdown="1">

判定这个程序的返回值。

```cpp run
int main() {
    char c = 200;
    return c < 0;
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：实现定义行为。**

1. [[basic.fundamental#7]]：`char` 的底层类型是 `signed char` 还是 `unsigned char`，由实现选择。
2. `char c = 200;` 是从 `int` 到 `char` 的整数转换。[[conv.integral#3]] 规定结果是与 200 模 2^N 同余的唯一值。`char` 有符号时得到 -56，函数返回 1；无符号时得到 200，返回 0。
3. 转换本身不会是 UB。C++20 起整数转换对有符号目标类型也按取模定义。

容易选 `ub`，把这次转换当成有符号溢出。溢出 UB 只针对算术表达式的结果（[[expr.pre#4]]），这里没有算术运算。

本机（Apple arm64）上 `char` 有符号，程序返回 1，Clang 同时给出 changes value from 200 to -56 的警告；加 `-funsigned-char` 编译则返回 0。

</details>
</div>

## 三、指针比较、条件运算符、lambda 与结构化绑定

<div class="quiz" data-kind="open" markdown="1">

对下面四个比较，分别回答：运行期结果是真、假还是未指明？能否出现在常量表达式中？

```cpp
struct S {
    int x;
private:
    int y = 0;
public:
    constexpr bool f() const { return &x < &y; }
};

int a[2];
int b;

// (1) &a[0] < &a[1]
// (2) S{}.f()
// (3) &a[0] < &b
// (4) &a[2] == &b
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：(1) 真，常量；(2) 真，常量；(3) 未指明，不是常量；(4) 未指明，不是常量。**

1. 同一数组的不同元素，下标大的比较结果更大（[[expr.rel#4.1]]）。
2. 同一对象的不同非静态数据成员，后声明的更大（[[expr.rel#4.2]]），条件只有两条：成员都不是大小为零的子对象，类不是联合体。旧规则还要求两个成员的访问控制相同，C++23 通过 [[P1847R4]] 删掉了这个条件，所以结果确定为真，也可以出现在常量表达式中。本机 Clang 23 在常量求值中仍按旧规则处理，报告 comparison of address of fields 'x' and 'y' of 'S' with differing access specifiers (public vs private) has unspecified value，这是编译器尚未跟上当前草案。
3. `a` 与 `b` 是不相关的完整对象，[[expr.rel#4.3]] 不要求任何一个更大，[[expr.rel#5]] 规定这时 `<` 的结果未指明。未指明不是 UB，程序照常运行。但结果未指明的关系运算不是核心常量表达式（[[expr.const.core#2.28]]）。需要跨对象的全序时用 `std::less<int*>`。
4. `&a[2]` 是 `a` 的尾后指针，`&b` 指向另一个完整对象。[[expr.eq#4.1]] 规定这种情况下相等比较的结果未指明，因为 `b` 可能恰好紧挨在 `a` 之后。同样不能出现在常量表达式中。

对照：`&a[0] != &b` 是确定的真值，可以写进 `static_assert`。两个指针指向不同对象且都不是尾后指针时，按 [[expr.eq#4.3]] 比较为不等。

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="C" markdown="1">

哪一行非良构？

```cpp
void test(bool c) {
    int i = 0;
    long l = 0;
    (c ? i : i) = 1;        // A
    (c ? i : throw 0) = 2;  // B
    (c ? i : l) = 3;        // C
    (c, i) = 4;             // D
}
```

- A. 第 A 行
- B. 第 B 行
- C. 第 C 行
- D. 第 D 行

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：C。**

赋值要求左操作数是可修改的左值（[[expr.assign#1]]），所以问题变成每个表达式的值类别。

- A：第二、三操作数是同类型、同值类别的泛左值，结果是该类型的左值（[[expr.cond#5]]）。
- B：一个操作数是 *throw-expression* 时，结果取另一个操作数的类型和值类别（[[expr.cond#2.1]]），这里是 `int` 左值。
- C：`int` 与 `long` 类型不同，又都不是类类型，[[expr.cond#4]] 的转换尝试不适用，[[expr.cond#5]] 也不满足，于是落到 [[expr.cond#6]]，结果是纯右值；再按 [[expr.cond#7.2]] 做寻常算术转换，得到 `long` 纯右值。纯右值不能赋值。
- D：逗号表达式的值类别与右操作数相同（[[expr.comma#1]]），是 `int` 左值。Clang 对这一行只警告左操作数无效果。

容易误选 B，以为 `throw` 让整个表达式变成 `void` 或纯右值。[[expr.cond#2.1]] 正是为 `c ? x : throw e` 这种写法保留了左值性。

还有一种情况：如果第三操作数换成 `const int` 左值，[[expr.cond#4]] 会把 `i` 转成 `const int` 左值，结果是不可修改的左值，赋值同样非良构，只是原因不同。

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

判定这个程序。

```cpp run
int main() {
    int x = 0;
    auto l = [=] { return sizeof(x); };
    decltype(l) m;
    return m();
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：非良构。**

1. `sizeof` 的操作数是不求值操作数（[[expr.sizeof#1]]）。[[expr.prim.lambda.capture#7]] 只在表达式会被潜在求值时才隐式捕获，所以 `x` 没有被捕获，闭包对象里没有数据成员。
2. 但闭包类型有没有默认构造函数，不看捕获了什么，只看语法上有没有 *lambda-capture*。[[expr.prim.lambda.closure#17]]：有 *lambda-capture* 的 lambda，闭包类型没有默认构造函数，复制赋值运算符也是弃置的。`[=]` 是一个捕获默认符，算 *lambda-capture*。
3. 因此 `decltype(l) m;` 找不到默认构造函数。

容易选 `ok`，理由是什么都没捕获，闭包和 `[]` 一样是无状态的。去掉 `=` 就成立：C++20 起，没有 *lambda-capture* 的闭包类型可以默认构造和赋值（[[P0624R2]]）。

```cpp run ok
int main() {
    int x = 0;
    auto l = [] { return sizeof(x); };   // 不求值操作数中的 x 不需要捕获
    decltype(l) m;
    m = l;
    return m();
}
```

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

判定这个程序。

```cpp run
struct S {
    int a : 4;
    int b;
};

int sum() {
    S s{1, 2};
    auto [x, y] = s;
    return [&] { return x + y; }();
}

int main() { return sum(); }
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：非良构。**

1. C++20 起结构化绑定可以被 lambda 捕获：它属于 [[basic.pre#9]] 定义的局部实体（[[P1091R3]]、[[P1381R1]]）。
2. `S` 按数据成员绑定。[[dcl.struct.bind#8]]：`x` 是指代 `e.a` 的左值，`a` 是位域，所以这个左值也是位域。
3. `[&]` 使 `x` 和 `y` 都被隐式按引用捕获（[[expr.prim.lambda.capture#7]]、[[expr.prim.lambda.capture#12]]）。[[expr.prim.lambda.capture#12]] 末句：位域不得按引用捕获。

本机 Clang 23 拒绝这段代码，说明是 non-const reference cannot bind to bit-field 'a'。按复制捕获 `x`，或者只按引用捕获 `y`，都可以：

```cpp run ok
struct S {
    int a : 4;
    int b;
};

int sum() {
    S s{1, 2};
    auto [x, y] = s;
    return [=] { return x + y; }() + [&y] { return y; }();
}

int main() { return sum(); }   // 返回 5
```

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ub" markdown="1">

判定这个程序。

```cpp run
struct X {
    int v = 7;
    auto get() { return [=] { return v; }; }
};

int main() {
    auto l = X{}.get();
    return l();
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：未定义行为。**

1. 在成员函数里，`v` 指 `this->v`。[[expr.prim.lambda.capture#7]]：命名非静态成员的 *id-expression* 潜在引用 `*this`，于是 `*this` 被隐式捕获。
2. [[expr.prim.lambda.capture#10]] 的 10.1 明确把 `*this` 排除在按复制捕获之外，所以它是按引用捕获的（[[expr.prim.lambda.capture#12]]）：闭包里存的是 `this` 指针，不是 `v` 的副本。这种隐式捕获已被弃用（[[depr.capture.this#1]]），但程序仍然良构。
3. `X{}` 是临时对象，在完整表达式结束时销毁（[[class.temporary#4]]）。之后 `l()` 通过悬空的 `this` 访问 `v`，按 [[basic.life#7]] 的 7.2 是 UB。

容易选 `ok`，以为 `[=]` 复制了 `v`。本机 Clang 给出 implicit capture of 'this' with a capture default of '=' is deprecated 警告，ASan 报告 stack-use-after-scope。

改成按值捕获整个对象（C++17）或者只复制成员，都有定义：

```cpp run ok
struct X {
    int v = 7;
    auto get() { return [*this] { return v; }; }
};

int main() {
    auto l = X{}.get();
    return l();   // 返回 7
}
```

lambda 捕获的完整讲解见 [[topics/lambdas]]。

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="B" markdown="1">

这个程序输出什么？

```cpp run
#include <cstdio>
#include <tuple>

int main() {
    int i = 2;
    std::tuple<int, int&> t{1, i};
    auto [a, b] = t;
    a = 10;
    b = 20;
    std::printf("%d %d\n", std::get<0>(t), i);
}
```

- A. `10 20`
- B. `1 20`
- C. `1 2`
- D. `10 2`

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：B，输出 `1 20`。**

1. 没有引用限定符，[[dcl.struct.bind#1]] 引入一个隐藏变量 `e`，如同 `auto e = t;`。`e` 是 `t` 的副本，类型仍是 `std::tuple<int, int&>`：第一个元素是新的 `int`，第二个元素仍然引用 `i`。
2. `std::tuple` 是类元组类型，按 [[dcl.struct.bind#7]] 处理。`e` 不是左值引用，所以作为 xvalue 传给 `get`。
    - 第 0 个：T₀ 是 `int`，`get<0>` 返回 `int&&`，引入 `int&& r0` 绑定到 `e` 的第一个元素。`a` 指代这个对象，`a = 10` 改的是 `e`，不是 `t`。
    - 第 1 个：T₁ 是 `int&`，`get<1>` 返回 `int&`，是左值，引入 `int& r1` 绑定到 `i`。`b = 20` 改的就是 `i`。
3. 所以 `std::get<0>(t)` 仍是 1，`i` 变为 20。

A 错在以为结构化绑定直接绑定到 `t`，那要写 `auto& [a, b] = t;`。C 错在以为复制会切断引用成员与 `i` 的联系，而复制一个引用成员得到的仍是指向同一对象的引用。

[[dcl.struct.bind#7]] 还规定 `a`、`b` 的被引用类型分别是 T₀、T₁，所以 `decltype(a)` 是 `int`，`decltype(b)` 是 `int&`。

</details>
</div>

## 四、常量求值与静态初始化

<div class="quiz" data-kind="verdict" data-answer="ok" markdown="1">

判定这个程序。

```cpp run
#include <cstddef>

template <class T, std::size_t N>
constexpr std::size_t count(const T (&)[N]) { return N; }

void f(const int (&arr)[3]) {
    static_assert(count(arr) == 3);
}

int main() {}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：良构。**

1. `arr` 是函数形参，引用的对象在常量求值之外，也不能在常量表达式中使用。C++20 及以前，常量表达式中只要出现这样的引用就不是常量表达式，这段代码会被拒绝。
2. C++23 通过 [[P2280R4]] 改变了这一点。[[expr.const.core#9]]：常量求值中，生命周期不在这次求值内开始的引用，视为绑定到一个未指明的对象，这个对象的生命周期覆盖整个求值。
3. `count` 只把 `arr` 绑定到自己的形参，返回从类型推导出来的 `N`，从不读取元素的值，没有触发 [[expr.const.core#2.10]] 禁止的左值到右值转换。所以 `count(arr)` 是常量表达式。

标准在 [[expr.const.core#9]] 的例 7 里给了同样的写法（`use_array`）。本机 Clang 23 接受。

一旦真的读值就不行了。下面两处都被拒绝：第一处对不能在常量表达式中使用的对象做左值到右值转换；第二处读取了非 `constexpr` 指针变量 `p` 的值。

```cpp error
#include <cstddef>

template <class T, std::size_t N>
constexpr std::size_t count(const T (&)[N]) { return N; }

void f(const int (&arr)[3]) {
    static_assert(arr[0] == 0);       // error: 读取 arr[0]
}

void g(const int (&arr)[3]) {
    const int (*p)[3] = &arr;
    static_assert(count(*p) == 3);    // error: 读取 p
}
```

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="impl" markdown="1">

判定这个程序。

```cpp run
constexpr int f(int x) {
    [[assume(x > 0)]];
    return x;
}

constexpr int v = f(-1);

int main() { return v; }
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：实现定义行为。程序是否良构由实现决定。**

1. [[dcl.attr.assume#1]]：假设的表达式求值不为真时，求值这条假设具有 runtime-undefined behavior。
2. [[intro.defs]] 对这个术语的定义是：除了在常量求值中，它就是未定义行为；在常量求值中，是否因此把表达式视为非常量由实现定义，除此之外没有别的效果。
3. [[expr.const.core#3]] 写的是同一件事：表达式满足核心常量表达式的约束，但求值具有 runtime-undefined behavior 时，它是否是核心常量表达式由实现定义。
4. 如果实现认为 `f(-1)` 不是常量表达式，`v` 不能常量初始化，按 [[dcl.constexpr#6]] 非良构；如果认为是，`v` 的值是 -1，程序良构。

本机 Clang 23 选择前者，报告 assumption evaluated to false。看到编译器报错就选 `error`，忽略了另一种同样合规的实现。

常量求值中有三种不同的未定义操作，处理方式各不相同：

| 未定义操作的来源 | 是否核心常量表达式 | 条款 |
|---|---|---|
| 语言部分（第 4 到 15 章）的 UB，如 `x / 0` | 一定不是，必须诊断 | [[expr.const.core#2.8]] |
| runtime-undefined behavior，如假设不成立 | 由实现定义 | [[expr.const.core#3]] |
| 标准库部分规定的 UB | 未指明 | [[expr.const.core#4]] |

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="B" markdown="1">

下面标为 A 到 D 的四个函数定义中，哪一个使程序非良构？

```cpp
consteval int id(int x) { return x; }

template <class T>
constexpr int a(T t) { return id(t); }            // A
static_assert(a(3) == 3);

constexpr int b(int t) { return id(t); }          // B

auto c = [](int t) { return id(t); };             // C
static_assert(c(3) == 3);

constexpr int d(int t) {                          // D
    if consteval { return id(t); }
    return t;
}
```

- A. `a`
- B. `b`
- C. `c`
- D. `d`

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：B。**

1. 四段中 `id(t)` 的实参都是函数形参，值未知，所以 `id(t)` 不是常量表达式。
2. 不在立即函数语境中的 `id(t)` 是一次立即调用（[[expr.const.imm#1]]）。不是常量表达式的立即调用是立即升级表达式（[[expr.const.imm#2]] 的 2.2）。
3. [[expr.const.imm#3]] 末句：立即升级表达式只能出现在立即升级函数中。立即升级函数有三种：未声明 `consteval` 的 lambda 调用运算符、非用户提供的预置函数，以及由带 `constexpr` 的模板化实体实例化出来的函数。含有这种表达式的立即升级函数自己变成立即函数（[[expr.const.imm#4]] 的 4.2）。

逐项看：

- A：`a<int>` 由函数模板实例化而来，是立即升级函数，于是升级为立即函数。`static_assert` 的条件是显然常量求值的，处在立即函数语境中，`a(3)` 没有问题。
- B：`b` 是普通的非模板 `constexpr` 函数，不是立即升级函数，`id(t)` 出现在这里就非良构。Clang 报告 call to consteval function 'id' is not a constant expression。
- C：lambda 的调用运算符是立即升级函数，升级为立即函数，`c(3)` 在 `static_assert` 中是常量。
- D：`if consteval` 的复合语句是立即函数语境（[[expr.const.imm#1]] 的 1.3），其中的 `id(t)` 不是立即调用。`d` 仍是普通的 `constexpr` 函数，运行期也能调用。

这套立即升级规则来自 C++23 的 [[P2564R3]]。升级会沿调用链向外传播：A 中如果在 `main` 里写 `int n = 1; a(n);`，`a<int>` 已是立即函数，`a(n)` 是不是常量表达式的立即调用，而 `main` 不是立即升级函数，于是在调用处报错。Clang 的说明是 'a<int>' is an immediate function because its body contains a call to a consteval function 'id' and that call is not a constant expression。

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

判定这个程序。

```cpp run
#include <cstddef>
#include <vector>

constexpr std::size_t n = std::vector{1, 2, 3}.size();
constexpr std::vector<int> v{1, 2, 3};

int main() { return n + v.size(); }
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：非良构，问题在 `v`。**

1. 编译期允许动态分配，但分配必须是暂时的（transient）：[[expr.const.core#2.22]] 规定，调用 `std::allocator<T>::allocate` 时，除非分配的存储在同一次求值 E 内被释放，否则 E 不是核心常量表达式。`new` 表达式有对应的 [[expr.const.core#2.20]]。
2. `n` 的初始化器中，临时的 `vector` 在完整表达式结束时销毁，它分配的内存在这次求值内释放，所以 `n` 没有问题。
3. `v` 的初始化完成时内存仍未释放，这块分配要一直保留到运行期。初始化器不是常量表达式，`constexpr` 变量又必须可以常量初始化（[[dcl.constexpr#6]]），所以非良构。

本机 Clang 23 的说明是 pointer to subobject of heap-allocated object is not a constant expression，并指出分配发生在 `allocator.h` 中。

编译期动态分配由 C++20 的 [[P0784R7]] 引入。容易误以为既然 `std::vector` 的成员函数都是 `constexpr`，`constexpr std::vector` 变量就可以存在。需要把结果留到运行期时，可以在编译期算出大小，再复制到 `std::array` 中。在 libc++ 上，空的 `constexpr std::vector<int> v{};` 能通过编译，因为默认构造不分配内存。

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="A" markdown="1">

这个程序输出什么？

```cpp run
#include <cstdio>
#include <type_traits>

constexpr int f() {
    if constexpr (std::is_constant_evaluated()) return 1;
    else return 2;
}

constexpr int g() {
    if (std::is_constant_evaluated()) return 1;
    return 2;
}

int main() {
    int a = f();
    int b = g();
    const int c = g();
    std::printf("%d %d %d\n", a, b, c);
}
```

- A. `1 2 1`
- B. `1 2 2`
- C. `2 2 1`
- D. `1 1 1`

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：A，输出 `1 2 1`。**

`std::is_constant_evaluated()` 等价于 `if consteval { return true; } else { return false; }`（[[meta.const.eval#1]]），而 `if consteval` 只在显然常量求值（manifestly constant-evaluated）的语境中走第一个分支（[[stmt.if#5]]）。所以要逐个判断调用处是不是显然常量求值。

- `a`：`f` 里的 `std::is_constant_evaluated()` 是 `if constexpr` 的条件，这个条件本身就是显然常量求值的（[[expr.const.defns#1.2]]），永远为真。`f` 被编译成无条件返回 1，与调用处无关。Clang 对这一行警告 'std::is_constant_evaluated' will always evaluate to 'true' in a manifestly constant-evaluated expression。
- `b`：`int b` 不是 `const`，不是潜在常量变量（[[expr.const.init#6]]），不能在常量表达式中使用；它具有自动存储期，也谈不上常量初始化（[[basic.start.static#2]] 只针对静态和线程存储期）。[[expr.const.defns#1.6]] 的条件都不满足，`g()` 按运行期求值，返回 2。
- `c`：`const int` 是潜在常量变量。判断它能否常量初始化时，`std::is_constant_evaluated()` 取真（[[expr.const.init#4]] 注 1），`g()` 返回 1，是常量表达式，所以 `c` 是常量初始化的，可以在常量表达式中使用（[[expr.const.init#7]]）。于是它的初始化器是显然常量求值的（[[expr.const.defns#1.6]]），值是 1。

[[expr.const.defns#1]] 的例 1 有同样的对比：`const int n = std::is_constant_evaluated() ? 13 : 17;` 中 `n` 是 13，而同样写法的非 `const` 变量 `m` 可以是 13 也可以是 17。本机 `-O0` 和 `-O2` 都输出 `1 2 1`。

需要区分编译期和运行期分支时，C++23 起直接写 `if consteval`，就不会误写成 `if constexpr`。

</details>
</div>

<div class="quiz" data-kind="open" markdown="1">

两个翻译单元一起链接。(1) 按标准，`copy` 的值是什么？(2) 给出两种修改，使 `copy` 一定是 `"hello, world"`，并说明依据。

```cpp title="a.cpp"
#include <string>

std::string make_greeting() { return "hello, world"; }
std::string greeting = make_greeting();
```

```cpp title="b.cpp"
#include <string>

extern std::string greeting;
std::string copy = greeting;

int main() { return copy.size(); }
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：(1) 两个动态初始化的先后未指明；如果 `copy` 先初始化，就是未定义行为。(2) 见下文，例如改为常量初始化、改用函数内静态变量，或者改为头文件中的 inline 变量。**

(1) 分析：

1. `make_greeting` 不是 `constexpr`，`greeting` 不能常量初始化，只能先零初始化，再做动态初始化（[[basic.start.static#2]]）。`copy` 也是动态初始化。
2. 两者都不是 inline 变量，也不是模板特化，属于有序初始化（[[basic.start.dynamic#1]]）。但它们在不同的翻译单元里，彼此之间没有出现顺序（[[basic.start.dynamic#2]]）。程序不启动其他线程时，按 [[basic.start.dynamic#3]] 的 3.3，两个初始化是不确定顺序的。此外，初始化是否推迟到 `main` 之后，也由实现定义（[[basic.start.dynamic#5]]）。
3. 如果 `greeting` 先初始化，`copy` 得到 `"hello, world"`。如果 `copy` 先初始化，`std::string` 的复制构造函数会读取一个构造函数尚未运行、生命周期尚未开始的对象，按 [[basic.life#8]] 是 UB。
4. 实现执行的是可能执行之一（[[intro.abstract#6]]），所以不能依赖结果。本机按 `a.cpp b.cpp` 的顺序链接时返回 12，按 `b.cpp a.cpp` 的顺序链接时返回 0。

(2) 修改方法，任选两种：

- 改为常量初始化：例如在头文件中声明 `constexpr std::string_view greeting = "hello, world";`，`b.cpp` 改成直接初始化 `std::string copy(greeting);`（从 `string_view` 构造 `std::string` 的构造函数是 `explicit` 的，原来的 `= greeting` 写法不能编译）。常量初始化属于静态初始化，强先发生于任何动态初始化（[[basic.start.static#2]]）。想保留可变的全局变量，可以写 `constinit`：初始化不是常量初始化时，程序非良构（[[dcl.constinit#2]]），问题在编译期就会暴露。这要求初始化器是常量表达式，所以 `make_greeting()` 必须改成 `constexpr`。对 `std::string` 来说，能否通过还取决于标准库在常量求值中是否分配内存：分配的内存若没有在初始化内释放，初始化器就不是常量表达式（[[expr.const.core#2.22]]）。
- 改用函数内静态变量：`const std::string& greeting() { static const std::string s = make_greeting(); return s; }`。块作用域静态变量在控制流第一次经过声明时初始化（[[stmt.dcl#3]]），`copy = greeting()` 一定读到已初始化的对象。
- 改为 inline 变量：在头文件中写 `inline std::string greeting = make_greeting();`，`b.cpp` 在定义 `copy` 之前包含它。`greeting` 是部分有序初始化，`copy` 的每个定义之前都有 `greeting` 的定义，按 [[basic.start.dynamic#3]] 的 3.1，单线程时 `greeting` 的初始化先于 `copy`。本机按两种链接顺序都返回 12。

这个问题通常叫静态初始化顺序灾难，更多背景见 [[basic.start]] 和 [[topics/initialization]]。

</details>
</div>

## 考查条款一览

| 题号 | 考查点 | 条款 |
|---|---|---|
| 1 | 赋值的右先左后，`i = i++ + 1` | [[intro.execution#10]]、[[expr.assign#1]] |
| 2 | 实参之间不确定顺序 | [[expr.call#8]]、[[intro.execution#8]] |
| 3 | 无序与不确定顺序的区分 | [[intro.execution#10]]、[[expr.comma#1]]、[[expr.call#8]] |
| 4 | 常量求值按词法顺序 | [[intro.execution#16]]、[[expr.const.core#2.8]] |
| 5 | 复合赋值链的求值顺序 | [[expr.assign#1]]、[[expr.assign#6]] |
| 6 | 整数提升与寻常算术转换 | [[conv.prom#2]]、[[expr.arith.conv#1.5]]、[[conv.integral#3]] |
| 7 | 提升后的有符号溢出 | [[conv.prom#2]]、[[expr.pre#4]] |
| 8 | 移位的宽度限制与 C++20 语义 | [[expr.shift#1]]、[[expr.shift#2]]、[[expr.shift#3]] |
| 9 | `INT_MIN % -1` | [[expr.mul#4]] |
| 10 | 浮点到无符号整数的越界转换 | [[conv.fpint#1]] |
| 11 | 枚举的值域 | [[dcl.enum#8]]、[[expr.static.cast#8]] |
| 12 | 不同枚举之间的算术运算 | [[expr.arith.conv#1.3]] |
| 13 | `char` 的符号性 | [[basic.fundamental#7]]、[[conv.integral#3]] |
| 14 | 指针的关系与相等比较 | [[expr.rel#4]]、[[expr.rel#5]]、[[expr.eq#4]]、[[expr.const.core#2.28]] |
| 15 | 条件运算符与逗号运算符的值类别 | [[expr.cond#2]]、[[expr.cond#5]]、[[expr.cond#6]]、[[expr.comma#1]] |
| 16 | 有捕获默认符的闭包没有默认构造函数 | [[expr.prim.lambda.closure#17]]、[[expr.prim.lambda.capture#7]] |
| 17 | 位域结构化绑定不能按引用捕获 | [[dcl.struct.bind#8]]、[[expr.prim.lambda.capture#12]] |
| 18 | `[=]` 隐式按引用捕获 `this` | [[expr.prim.lambda.capture#10]]、[[depr.capture.this#1]]、[[basic.life#7]] |
| 19 | 类元组结构化绑定的绑定对象 | [[dcl.struct.bind#1]]、[[dcl.struct.bind#7]] |
| 20 | 常量求值中的未知引用 | [[expr.const.core#9]]、[[expr.const.core#2.10]] |
| 21 | runtime-undefined behavior 与常量求值 | [[dcl.attr.assume#1]]、[[expr.const.core#3]] |
| 22 | 立即调用与立即升级函数 | [[expr.const.imm#1]]、[[expr.const.imm#2]]、[[expr.const.imm#3]]、[[expr.const.imm#4]] |
| 23 | 编译期动态分配必须是暂时的 | [[expr.const.core#2.22]]、[[dcl.constexpr#6]] |
| 24 | `std::is_constant_evaluated` 与显然常量求值 | [[expr.const.defns#1]]、[[expr.const.init#7]]、[[meta.const.eval#1]] |
| 25 | 跨翻译单元的动态初始化顺序 | [[basic.start.dynamic#3]]、[[basic.start.static#2]]、[[basic.life#8]] |
