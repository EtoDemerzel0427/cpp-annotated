---
title: 赋值与复合赋值运算符
summary: "= 与 op= 的左操作数要求、结果是左值；C++17 起右操作数先于左操作数求值；复合赋值相对函数调用是单次求值；位域溢出是实现定义；volatile 赋值的弃用史；重叠对象赋值的 UB；右侧的花括号初始化列表"
status: done
papers: P0145R3, P1152R4, P2327R1
related: intro.execution, basic.lval, conv, class.copy.assign, over.assign, class.union, dcl.init.list, depr.volatile.type, expr.cond, expr.yield, expr.throw, basic.compound
tags: 赋值, 求值顺序, volatile, 位域, UB
updated: 2026-10-18
---

赋值是最常用的运算符，规则却比看上去多：它是 C++ 中少数**右结合**的二元运算符；它的结果是**左值**（与 C 不同）；C++17 为它规定了**右先左后**的求值顺序；它与 `volatile`、位域、联合体、花括号初始化列表都有专门的交互规则。另外，本节的文法定义了 *assignment-expression*——整个表达式文法中逗号之下最"宽"的一级，*throw-expression*（[[expr.throw]]）和 *yield-expression*（[[expr.yield]]）都挂在这里。

类类型的赋值通常调用 `operator=`（[[class.copy.assign]]、[[over.assign]]），本节主要讲**内置**赋值；但 ¶1 的求值顺序经由 [[over.match.oper]] 同样适用于用运算符语法调用的重载 `operator=`。

## 文法、结果与求值顺序（¶1）

```text
assignment-expression:
    conditional-expression
    yield-expression
    throw-expression
    logical-or-expression assignment-operator initializer-clause

assignment-operator: one of
    =  *=  /=  %=  +=  -=  >>=  <<=  &=  ^=  |=
```

几个文法推论：

- 左操作数是 *logical-or-expression*：所以 `c ? a : b = 1` 不能解析为"对条件表达式赋值"，它是 `c ? a : (b = 1)`（[[expr.cond]]）；
- 右操作数是 *initializer-clause*：既可以是表达式，也可以是**花括号初始化列表**（¶8）；
- 右结合：`a = b = c` 是 `a = (b = c)`。

### 左操作数与结果

¶1 所有赋值运算符都要求左操作数是**可修改的左值**（modifiable lvalue，[[basic.lval]]）；结果是左操作数类型的**左值**，指代左操作数；若左操作数是位域，结果也是位域。

"结果是左值"是 C++ 区别于 C 的地方：在 C 中赋值表达式的值不是左值。于是在 C++ 中 `(a = b) = c` 合法，`++(a = b)` 合法——这也是 `operator=` 惯例返回 `T&` 的原因。

```cpp run title="assign-lvalue.cpp" ok
#include <type_traits>

int a, b, c;
static_assert(std::is_same_v<decltype(a = b), int&>);      // 结果是 int 左值
static_assert(std::is_same_v<decltype(a += 1.5), int&>);   // 复合赋值也一样

int main() {
    a = 1; b = 2; c = 3;
    (a = b) = c;          // OK：先 a = b，再对结果（即 a）赋值 c
    a = b = c;            // 右结合
    return (a == 3 && b == 3) ? 0 : 1;
}
```

```cpp title="assign-not-modifiable.cpp" error
void f() {
    const int k = 0;
    int arr[2], arr2[2];
    k = 1;          // error: const 对象不是可修改左值
    arr = arr2;     // error: 数组不是可修改左值
    1 = k;          // error: 左操作数不是左值
}
```

注意"可修改的左值"是**内置**赋值的要求。类类型的 prvalue 可以调用成员 `operator=`，因为那只是成员函数调用：`S() = s;` 合法（除非 `operator=` 带 `&` 限定）。

### 求值顺序

!!! std
    The right operand is sequenced before the left operand.

    右操作数先于左操作数求值。

¶1 规定了三层顺序：

1. **赋值这个副作用**排在左右两个操作数的**值计算之后**、整个赋值表达式的**值计算之前**（这一点自 C++11 起就有）；
2. **右操作数先于左操作数**——C++17 由 [[P0145R3]] 加入；
3. 对于与之**不确定顺序**的函数调用而言，复合赋值的操作是**单次求值**：注 1 解释，函数调用不能插入到复合赋值的"读取"与"写回"之间。

第 2 条让一批经典的"未定义行为"在 C++17 中变得有定义：

```cpp run title="assign-order.cpp" ok
#include <map>
#include <cstddef>

int main() {
    int i = 0;
    i = i++ + 1;         // C++17：右边先完整求值（i 变为 1，值 0 + 1），再赋值 → i == 1
    int a[4]{};
    a[i] = i++;          // C++17：先算右边 i++（得 1，i 变为 2），再算 a[i] → a[2] = 1
    std::map<int, std::size_t> m;
    m[0] = m.size();     // C++17：先算 m.size()（0），再 m[0] 插入 → m[0] == 0
    return (i == 2 && a[2] == 1 && m[0] == 0) ? 0 : 1;
}
```

在 C++11/14 中，前两行是 UB（对 `i` 的修改与另一次访问/修改无序），第三行的结果未指定（取决于 `m[0]` 的插入与 `m.size()` 谁先发生，可能得到 1）。Clang 的 `-Wunsequenced` 在 `-std=c++14` 下会对前两行报警，在 `-std=c++17` 下不报。

为什么选择"右先左后"而不是"左先右后"？因为赋值的"目标"往往依赖于右边的计算结果或副作用（如 `*p = alloc()`、`m[k] = compute()`），而且这与链式赋值 `a = b = c` 的直觉一致：先把值算出来，再决定放到哪里。完整的讨论见 [[topics/order-of-evaluation]]。

!!! lawyer "复合赋值是单次求值"
    `x += f()` 中，`f()` 与"读取 `x`—相加—写回 `x`"这一整个操作之间，不会出现 `f()` 恰好插在读和写之间的情况。即使 `f()` 内部修改了 `x`，也只可能整体在前或整体在后。这条规则在 C++11 引入 sequenced-before 模型时加入，用来保证 `x += f()` 不会因为 `f` 修改 `x` 而成为 UB。后缀 `++` 有同样的规定（[[expr.post.incr]]）。

## 简单赋值存入什么（¶2–¶3）

¶3 若右操作数是表达式，它被**隐式转换**（[[conv]]）为左操作数的 cv 非限定类型。

¶2 简单赋值中，设 `V` 是右操作数的结果，左操作数指代的对象被**修改**（[[intro.defs]] 中"访问"的定义），其值被替换为：

- ¶2.1 若对象是**整数类型**：与 `V` **同余**（[[basic.fundamental]]）的值——即按模 2<sup>N</sup> 存入；
- ¶2.2 若左操作数是 **volatile 限定**的指针类型 `T` 的 glvalue，且 `V` 是在当前求值语境下**无效**的指针值（[[basic.compound]]）：存入 `reinterpret_cast<T>(reinterpret_cast<std::uintptr_t>(V))`；
- ¶2.3 否则：`V`。

¶2.2 是 C++23 之后的新措辞，处理一个罕见但真实的情形：把一个已失效的指针（比如所指对象已被释放）写进一个 `volatile` 指针对象。[[basic.compound#6]] 规定使用无效指针值的大多数方式是实现定义或未定义的；这里明确规定，写入 `volatile` 对象的是"经整数往返后的指针"，从而让"把地址值原样存到硬件寄存器或共享内存"这类代码有可依赖的语义。

## 位域（¶4）

¶4 赋值给一个**无法表示**该值的位域时，位域的结果值是**实现定义**的 {{impl}}。

```cpp run title="assign-bitfield.cpp" impl
#include <cstdio>

struct S { int b : 3; unsigned u : 3; };

int main() {
    S s{};
    s.b = 7;     // 实现定义：3 位有符号位域只能表示 -4..3；GCC/Clang 得到 -1
    s.u = 9;     // 无符号位域：按模 2^3 存入 1（见 ¶2.1 与 [conv.integral]）
    std::printf("%d %u\n", s.b, s.u);
}
```

注意对**无符号**位域，值的转换由整型转换规则（按模）确定，不涉及实现定义；只有有符号位域装不下时才落到 ¶4。Clang 对常量情形会警告 "implicit truncation from 'int' to bit-field changes value from 7 to -1"。

## `volatile` 赋值的弃用（¶5）{{deprecated}}

¶5 左操作数为 **volatile 限定类型**的赋值是**弃用**的，**除非**这个（可能带括号的）赋值是一个**弃值表达式**（discarded-value expression）或**不求值操作数**。换句话说：对 `volatile` 对象赋值本身没问题，**使用这个赋值表达式的结果**才被弃用。

```cpp title="assign-volatile.cpp" ok
volatile int reg;
int x, y;

void f() {
    reg = x;         // OK: 结果被丢弃
    y = reg;         // OK: 这是对 y 的赋值，reg 只被读取
    reg += x;        // OK: 复合赋值作为弃值表达式（见下方历史）
    reg |= 0x1;      // OK
    y = reg = x;     // 弃用：使用了 volatile 赋值的结果
}
```

为什么？`y = reg = x` 的含义是"把 `x` 写入 `reg`，然后把**赋值表达式的值**写入 `y`"。对普通变量，这个值就是 `x` 转换后的值；但对 `volatile` 对象（可能是硬件寄存器），程序员可能以为会**重新读取** `reg`，而标准从未规定是否重读。这种歧义正是弃用的理由。Clang 的诊断是 "use of result of assignment to object of volatile-qualified type 'volatile int' is deprecated [-Wdeprecated-volatile]"。

!!! history "volatile 复合赋值的反复"
    - **C++20**：[[P1152R4]]（Deprecating volatile）弃用了一大批 `volatile` 用法，包括**所有**对 `volatile` 对象的复合赋值（`reg += x`），理由是复合赋值是"读—改—写"，程序员常误以为它是原子的。
    - **C++23**：[[P2327R1]] 撤销了对**按位**复合赋值（`|=`、`&=`、`^=`）的弃用——嵌入式代码大量用它们操作硬件寄存器，而且 C 语言头文件（厂商提供的寄存器定义）需要能在 C++ 中编译。
    - **之后**：当前草案的措辞只弃用"结果被使用的 volatile 赋值"，附录 [[depr.volatile.type]] 的例子中 `brachiosaur += neck;` 标注为 OK——也就是说，作为弃值表达式的**所有**复合赋值都不再弃用。这是 C++23 之后通过缺陷报告进一步放宽的结果。
    - 仍然弃用的还有 `volatile` 对象的 `++`/`--`、`volatile` 参数与返回类型、`volatile` 结构化绑定（[[depr.volatile.type]]）。

## 复合赋值（¶6）

¶6 [[g:compound-assignment|复合赋值]] `E1 op= E2` 的行为等价于 `E1 = E1 op E2`，**区别只在 `E1` 只求值一次**。注 2：`E1` 指代的对象被**访问两次**（读一次、写一次）。

- 对 `+=` 与 `-=`，`E1` 可以是**算术类型**或**指向完整定义对象类型的指针**；
- 其他复合赋值，`E1` 必须是**算术类型**。

"`E1` 只求值一次"在 `E1` 有副作用时很重要：`a[i++] += 1` 只自增一次 `i`，而 `a[i++] = a[i++] + 1` 则完全是另一回事：两个 `i++` 分别属于右操作数和左操作数，C++17 规定右先左后，所以它**有定义**——右边读 `a[0]`，左边写 `a[1]`，`i` 自增两次——但几乎不可能是你想要的；在 C++14 中它是 UB。

"等价于 `E1 = E1 op E2`"意味着中间结果按 `op` 的规则做常用算术转换，然后再隐式转换回 `E1` 的类型。所以：

```cpp run title="assign-compound.cpp" ok
int main() {
    char c = 'a';
    c += 1;            // 等价于 c = c + 1：int 运算再转回 char，没有窄化错误
    short s = 300;
    s *= 2;            // int 运算，结果 600 转回 short
    int i = 7;
    i /= 2.0;          // 等价于 i = i / 2.0：double 运算得 3.5，再转回 int 得 3
    int arr[4]{};
    int* p = arr;
    p += 3;            // 指针的 += 合法
    return (c == 'b' && s == 600 && i == 3 && p == arr + 3) ? 0 : 1;
}
```

```cpp title="assign-compound-bad.cpp" error
enum E { e0, e1 };

void f(int* p, E e) {
    p *= 2;        // error: 除 += 和 -= 外，E1 必须是算术类型
    e |= e1;       // error: 枚举不是算术类型（e | e1 的结果是 int，也不能隐式转回 E）
}
```

`i /= 2.0` 这一行展示了复合赋值的一个"窟窿"：直接写 `int i = i / 2.0` 或 `i = {i / 2.0}` 会被窄化规则拦下，复合赋值却静悄悄地截断。

## 重叠对象（¶7）

¶7 若被存入一个对象的值，是通过另一个与之存储**以任何方式重叠**的对象读出的，那么重叠必须是**完全重叠**，并且两个对象类型相同；否则行为未定义 {{ub}}。注 3 强调：这条限制只关于赋值**左右两边**之间的关系，不是关于一般别名的规则（后者见 [[basic.lval]]）。

这条规则存在的理由是**实现自由**：对一个结构体的平凡赋值，编译器希望直接按字节复制（等同于 `memcpy`，可以按任意顺序、任意宽度搬运），而不必像 `memmove` 那样处理源与目标部分重叠的情况。完全重叠（自赋值）没问题——每个字节复制到自己身上；部分重叠则可能读到已被覆盖的字节。

部分重叠几乎只能通过联合体产生：

```cpp title="assign-overlap.cpp" ub
struct A { int a, b; };
struct B { int pad; A in; };   // B::in 相对于联合体起始偏移 sizeof(int)
union U { A x; B y; };

int main() {
    U u{.x = {1, 2}};
    u.y.in = u.x;     // UB: 源 u.x 与目标 u.y.in 部分重叠（偏移不同）
    return u.y.in.a;
}
```

（这个赋值还会按 [[class.union]] 的规则隐式创建 `u.y` 并结束 `u.x` 的生命周期；正因为源和目标在同一块存储上"交接"，¶7 直接把它定为 UB。）正确的做法是先复制到临时对象：`A tmp = u.x; u.y.in = tmp;`。

## 右侧的花括号初始化列表（¶8）

¶8 花括号初始化列表 `B` 可以出现在以下赋值的右侧：

- ¶8.1 对**标量**类型 `T` 的赋值：`B` 最多只能有一个元素；`x = B` 的含义是 `x = t`，其中 `t` 是虚构的临时变量 `T t = B;`——因此**窄化转换会被拒绝**，空的 `{}` 给出值初始化的值（零）；
- ¶8.2 对**类类型**对象的赋值：`B` 作为实参传给重载决议选出的赋值运算符函数。

```cpp run title="assign-braced.cpp" ok
#include <complex>
#include <vector>

int main() {
    int a = 5, b = 0;
    a = {};                       // a = 0（值初始化）
    a = b = {1};                  // a = (b = 1)
    std::complex<double> z;
    z = {1, 2};                   // z.operator=({1, 2})
    std::vector<int> v;
    v = {1, 2, 3};                // vector::operator=(initializer_list<int>)
    return (a == 1 && z.imag() == 2 && v.size() == 3) ? 0 : 1;
}
```

```cpp title="assign-braced-bad.cpp" error
void f() {
    int a = 0, b = 0;
    a = {1.5};       // error: 窄化（T t = {1.5} 非良构）
    a = {1, 2};      // error: 标量最多一个元素
    a = {1} = b;     // error: 花括号列表不能作为赋值的左操作数（文法上不可能）
}
```

!!! lawyer "复合赋值与花括号列表"
    文法允许 `x += {1}`（右操作数总是 *initializer-clause*），¶8 的措辞是"an assignment to a scalar"，标准例子中也出现了 `z += { 1, 2 }`（含义为 `z.operator+=({1,2})`）。但对**标量**的复合赋值，¶8.1 只给出了 `x = B` 的含义，`x += B` 的含义要靠 ¶6 的"等价于 `x = x + B`"推出，而 `x + {1}` 本身不是合法表达式——这是一处措辞上的空白。Clang 接受 `int a; a += {1};`。
    
    另外，标准例子中的 `z += { 1, 2 }` 按 [[complex.member.ops]] 的声明其实无法匹配：`complex<double>` 的 `operator+=` 要么接受 `const double&`（`{1, 2}` 无法初始化 `double`），要么是模板 `operator+=(const complex<X>&)`（花括号列表无法推导 `X`）。libc++ 确实拒绝它。例子不具规范效力，但这提醒我们标准的例子也会出错。

## 实现视角

!!! impl
    - 内置赋值编译为一条存储指令（必要时先做类型转换）。复合赋值对普通内存是"读—改—写"三步，**不是原子操作**——即使在 x86 上 `add [mem], reg` 是一条指令，没有 `lock` 前缀时也不保证原子性。需要原子性请用 `std::atomic`（其 `+=` 是原子的 RMW）。
    - 平凡类类型的赋值通常编译为 `memcpy` 式的内联拷贝，这正是 ¶7 所保护的实现自由。
    - Clang 的 `-Wunsequenced` 能发现大部分违反 [[intro.execution#10]] 的代码；`-Wdeprecated-volatile` 报告 ¶5 的弃用；`-Wbitfield-constant-conversion` 报告位域截断。

## 陷阱

!!! pitfall "以为 `i /= 2.0` 会被窄化检查拦下"
    复合赋值等价于 `i = i / 2.0`，隐式转换静悄悄截断。

!!! pitfall "以为 `x += 1` 是原子的"
    它是读—改—写；多线程下用 `std::atomic`。

!!! pitfall "以为 C++14 中 `i = i++ + 1` 有定义"
    C++17 之前是 UB。C++17 起有定义，但仍然难读——别写。

!!! pitfall "`y = reg = x` 以为会重读硬件寄存器"
    标准不保证；而且这种写法已被弃用。

## 思考题

!!! question "思考题 1"
    在 C++17 中，`int i = 0; i += i++;` 的结果是什么？

<details markdown="1">
<summary>答案</summary>

右操作数先于左操作数求值：`i++` 的值是 0，副作用使 `i` 变为 1。然后复合赋值读取 `i`（现在是 1）、加上右操作数的值 0、写回 1。结果 `i == 1`，有定义。（在 C++14 中，`i++` 的副作用与复合赋值对 `i` 的读写无序 → UB。）
</details>

!!! question "思考题 2"
    `struct S { int v; S& operator=(int x) { v = x; return *this; } }; S s; int i = 0; s = i++, i;` 中，`s.v` 最后是多少？

<details markdown="1">
<summary>答案</summary>

逗号的优先级低于赋值，所以这是 `(s = i++), i;`。`s = i++` 调用 `s.operator=(i++)`，`i++` 的值是 0 → `s.v == 0`，随后求值并丢弃 `i`。若想让 `s` 得到逗号表达式的值，需写 `s = (i++, i)`，此时 `s.v == 1`。
</details>

## 小结

| 方面 | 规则 | 段落 |
|---|---|---|
| 左操作数 | 可修改左值 | ¶1 |
| 结果 | 左操作数类型的左值（位域保持位域） | ¶1 |
| 求值顺序 | 右先于左（C++17）；赋值在两边值计算之后 | ¶1 |
| 复合赋值 vs 函数调用 | 单次求值，不会被函数调用插入 | ¶1 |
| 存入的值 | 整数类型按同余；volatile 指针存无效值时经 `uintptr_t` 往返 | ¶2 |
| 位域装不下 | {{impl}} | ¶4 |
| 使用 volatile 赋值的结果 | {{deprecated}} | ¶5 |
| `E1 op= E2` | 等价于 `E1 = E1 op E2`，`E1` 只求值一次 | ¶6 |
| 部分重叠的赋值 | {{ub}} | ¶7 |
| 右侧花括号列表 | 标量：至多一个元素、禁止窄化；类：传给 `operator=` | ¶8 |
