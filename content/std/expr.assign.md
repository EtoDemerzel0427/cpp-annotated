---
title: 赋值与复合赋值运算符
summary: = 与 op= 要求可修改的左值、结果是左值；C++17 起右操作数先于左操作数求值；复合赋值等价于 E1 = E1 op E2 但 E1 只求值一次；还有位域、volatile、部分重叠和右侧花括号列表的规则。
status: done
papers: P0145R3, P1152R4, P2327R1, CWG2654
related: intro.execution, basic.lval, conv, class.copy.assign, over.assign, class.union, dcl.init.list, depr.volatile.type, expr.cond, expr.yield, expr.throw, basic.compound
tags: 赋值, 求值顺序, volatile, 位域, UB
updated: 2026-10-19
---

!!! tldr
    - 赋值的左操作数必须是可修改的左值；结果是指代左操作数的左值，所以 `(a = b) = c` 在 C++ 中合法。
    - C++17 起右操作数先于左操作数求值，`a[i] = i++` 和 `m[k] = m.size()` 从此有确定结果。
    - `E1 op= E2` 等价于 `E1 = E1 op E2`，只是 `E1` 只求值一次；中间的隐式转换不做窄化检查，`i /= 2.0` 会悄悄截断。
    - 赋值右侧可以是花括号列表：对标量它禁止窄化，对类类型它作为实参传给 `operator=`。
    - 从部分重叠的对象赋值是 UB；有符号位域装不下所赋的值时结果是实现定义的；使用 volatile 赋值的结果已被弃用。

## 文法：右结合，结果是左值（¶1）

```text
assignment-expression:
    conditional-expression
    yield-expression
    throw-expression
    logical-or-expression assignment-operator initializer-clause

assignment-operator: one of
    =  *=  /=  %=  +=  -=  >>=  <<=  &=  ^=  |=
```

*assignment-expression* 是表达式文法中仅次于逗号表达式的一级，`co_yield`（[[expr.yield]]）和 `throw`（[[expr.throw]]）也归在这里。从文法可以读出三点：

- 赋值右结合，`a = b = c` 是 `a = (b = c)`。
- 左操作数是 *logical-or-expression*，所以 `c ? a : b = 1` 只能解析为 `c ? a : (b = 1)`（[[expr.cond]]）。
- 右操作数是 *initializer-clause*，可以是表达式，也可以是花括号列表（见第 8 段）。

¶1 所有赋值运算符都要求左操作数是**可修改的左值**（[[g:modifiable-lvalue]]，类型既不是 const 限定、也不是函数类型的左值，[[basic.lval#10]]）。结果是左操作数类型的左值，指代左操作数；左操作数是位域时，结果也是位域。

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
    k = 1;          // error：const 对象不是可修改的左值
    arr = arr2;     // error：arr2 不能隐式转换为 int[2]（¶3）
    1 = k;          // error：左操作数不是左值
}
```

数组左值按定义是可修改的，数组不能赋值的原因在第 3 段：右操作数要先隐式转换为左操作数的类型，也就是要求 `int t[2] = arr2;` 良构，而数组不能用另一个数组表达式初始化。

在 C 中，赋值表达式的结果不是左值。C++ 让它成为左值，`operator=` 按惯例返回 `T&` 也是为了与内置赋值保持一致。

可修改的左值只是内置赋值的要求。类类型的赋值通常调用成员 `operator=`（[[class.copy.assign]]、[[over.assign]]），那只是一次成员函数调用，所以 `S() = s;` 对 prvalue 也合法，除非 `operator=` 带 `&` 限定。

## 求值顺序（¶1）

```cpp run title="assign-order.cpp" ok
#include <map>
#include <cstddef>

int main() {
    int i = 0;
    i = i++ + 1;         // 右边先完整求值（值 0 + 1，i 变为 1），再赋值 → i == 1
    int a[4]{};
    a[i] = i++;          // 先算右边 i++（值 1，i 变为 2），再算 a[i] → a[2] = 1
    std::map<int, std::size_t> m;
    m[0] = m.size();     // 先算 m.size()（0），再由 m[0] 插入 → m[0] == 0
    return (i == 2 && a[2] == 1 && m[0] == 0) ? 0 : 1;
}
```

¶1 对赋值规定了三层顺序：

1. 写入左操作数这个副作用，排在左右操作数的值计算之后、整个赋值表达式的值计算之前。
2. 右操作数**先于**（[[g:sequenced-before]]）左操作数求值。这一句由 C++17 的 [[P0145R3]] 加入。
3. 相对于一个顺序不确定的函数调用，复合赋值是一次不可分割的求值。注 1 解释说，函数调用不能插在复合赋值的读取和写回之间。

第 2 条让上例的三行在 C++17 中都有了确定结果。在 C++14 中，前两行是 UB（对 `i` 的修改和另一次访问之间没有顺序），第三行的结果未指定，可能是 1。Clang 的 `-Wunsequenced` 在 `-std=c++14` 下会对前两行报警，`-std=c++17` 下不报。

选择先右后左，是因为赋值的目标常常依赖右边的副作用，比如 `*p = alloc()`、`m[k] = compute()`；这也与链式赋值 `a = b = c` 的直觉一致：先把值算出来，再决定放到哪里。经由 [[over.match.oper]]，这个顺序同样适用于以运算符语法调用的重载 `operator=`。完整的讨论见 [[topics/order-of-evaluation]]。

第 3 条保证 `x += f()` 不会因为 `f` 内部修改了 `x` 而成为 UB：读取 `x`、相加、写回 `x` 整体在 `f()` 之前或之后，`f()` 不会插在中间。后缀 `++` 有同样的规定（[[expr.post.incr]]）。

## 简单赋值存入什么（¶2–¶3）

¶3 右操作数是表达式时，先隐式转换（[[conv]]）为左操作数的 cv 非限定类型。

¶2 设 `V` 是右操作数的结果，左操作数指代的对象被修改，新值是：

- ¶2.1 对象是整数类型时：与 `V` 同余的值（[[basic.fundamental]]），即按模 2<sup>N</sup> 存入；
- ¶2.2 左操作数是 volatile 限定的指针类型 `T` 的 glvalue，且 `V` 是在当前求值语境下无效的指针值（[[basic.compound]]）时：存入 `reinterpret_cast<T>(reinterpret_cast<std::uintptr_t>(V))`；
- ¶2.3 其他情况：`V`。

¶2.2 是 C++23 之后的新措辞，处理的是把一个已失效的指针（比如所指对象已经释放）写进 `volatile` 指针对象的情形。使用无效指针值通常是实现定义或未定义的（[[basic.compound#6]]），这里明确规定写入的是经过整数往返的地址值，把地址原样存进硬件寄存器或共享内存的代码因此有了可依赖的语义。

## 复合赋值（¶6）

```cpp run title="assign-compound.cpp" ok
int main() {
    char c = 'a';
    c += 1;            // c = c + 1：在 int 上运算，再转回 char
    short s = 300;
    s *= 2;            // int 运算得 600，再转回 short
    int i = 7;
    i /= 2.0;          // i = i / 2.0：double 运算得 3.5，转回 int 得 3
    int arr[4]{};
    int* p = arr;
    p += 3;            // 指针的 += 合法
    return (c == 'b' && s == 600 && i == 3 && p == arr + 3) ? 0 : 1;
}
```

¶6 [[g:compound-assignment|复合赋值]] `E1 op= E2` 的行为等价于 `E1 = E1 op E2`，区别只在于 `E1` 只求值一次。注 2 指出，`E1` 指代的对象仍然被访问两次，读一次、写一次。

- `+=` 和 `-=` 的 `E1` 可以是算术类型，或指向完整定义的对象类型的指针；
- 其他复合赋值的 `E1` 必须是算术类型。

```cpp title="assign-compound-bad.cpp" error
enum E { e0, e1 };

void f(int* p, E e) {
    p *= 2;        // error：除 += 和 -= 外，E1 必须是算术类型
    e |= e1;       // error：e | e1 的结果是 int，不能隐式转回 E
}
```

等价于 `E1 = E1 op E2`，意味着运算按 `op` 的规则做常用算术转换，结果再隐式转换回 `E1` 的类型。这一步是普通的隐式转换，不做窄化检查：`i /= 2.0` 悄悄截断成 3。只有写成 `i = {i / 2.0}`，花括号列表的窄化规则（第 8 段）才会拒绝它。

`E1` 只求值一次，在 `E1` 有副作用时才看得出来：`a[i++] += 1` 只让 `i` 自增一次。写成 `a[i++] = a[i++] + 1` 就是另一回事了：两个 `i++` 分属右操作数和左操作数，C++17 起先右后左，右边读 `a[0]`、左边写 `a[1]`，`i` 自增两次。它在 C++17 中有定义，但几乎不会是你想要的。

## 右侧的花括号列表（¶8）

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

¶8 花括号列表 `B` 可以出现在下面两种赋值的右侧：

- ¶8.1 对标量类型 `T` 的赋值：`B` 最多一个元素，`x = B` 的含义是 `x = t`，`t` 是虚构的临时变量 `T t = B;`。所以窄化转换被拒绝，空的 `{}` 得到值初始化的零。
- ¶8.2 对类类型对象的赋值：`B` 作为实参，传给重载决议选出的赋值运算符函数。

```cpp title="assign-braced-bad.cpp" error
void f() {
    int a = 0, b = 0;
    a = {1.5};       // error：窄化，T t = {1.5} 非良构
    a = {1, 2};      // error：标量最多一个元素
    a = {1} = b;     // error：花括号列表不能作为赋值的左操作数
}
```

!!! lawyer "复合赋值与花括号列表"
    文法允许 `x += {1}`，因为右操作数总是 *initializer-clause*。但第 8.1 项只定义了 `x = B` 的含义；按第 6 段把 `x += B` 展开成 `x = x + B`，而 `x + {1}` 本身不是合法表达式。这是措辞上的空白，本机 Clang 23 接受 `int a = 0; a += {1};`。

    标准例子还写了 `z += { 1, 2 }`，说它的含义是 `z.operator+=({1,2})`。按 [[complex.member.ops]] 的声明，这个调用其实匹配不上：`operator+=(const double&)` 不能由 `{1, 2}` 初始化，模板 `operator+=(const complex<X>&)` 又无法从花括号列表推导 `X`。libc++ 确实拒绝它。例子不具规范效力。

## 位域（¶4）

¶4 左操作数是位域、而位域无法表示所赋的值时，位域的结果值是实现定义的 {{impl}}。

```cpp run title="assign-bitfield.cpp" impl
#include <cstdio>

struct S { int b : 3; unsigned u : 3; };

int main() {
    S s{};
    s.b = 7;     // 实现定义：3 位有符号位域只能表示 -4..3，GCC、Clang 得到 -1
    s.u = 9;     // 无符号位域：按模 2^3 存入 1
    std::printf("%d %u\n", s.b, s.u);
}
```

无符号位域按模存入，结果由整数转换规则确定，不是实现定义的。只有有符号位域装不下时才适用第 4 段。Clang 对常量情形会给出 `-Wbitfield-constant-conversion` 警告。

## 使用 volatile 赋值的结果已被弃用（¶5）{{deprecated}}

¶5 左操作数是 volatile 限定类型的赋值被弃用，除非这个（可能带括号的）赋值是一个**弃值表达式**（[[g:discarded-value-expression]]，结果不被使用的表达式，如单独成句的表达式语句）或不求值操作数。换句话说，给 `volatile` 对象赋值本身没问题，被弃用的是使用这个赋值表达式的结果。

```cpp title="assign-volatile.cpp" ok
volatile int reg;
int x, y;

void f() {
    reg = x;         // OK：结果被丢弃
    y = reg;         // OK：这是对 y 的赋值，reg 只被读取
    reg += x;        // OK
    reg |= 0x1;      // OK
    y = reg = x;     // 弃用：使用了 volatile 赋值的结果
}
```

`y = reg = x` 把 `x` 写进 `reg`，再把赋值表达式的值写进 `y`。如果 `reg` 是硬件寄存器，读代码的人可能以为 `y` 的值来自重新读取 `reg`，而标准从未规定是否重读。Clang 对这一行的诊断是 `-Wdeprecated-volatile`。

!!! history "volatile 复合赋值的反复"
    C++20 的 [[P1152R4]] 弃用了一批 `volatile` 用法，其中包括对 `volatile` 对象的所有复合赋值，理由是读—改—写容易被误以为是原子的。嵌入式代码大量用 `REG |= BIT` 操作寄存器，厂商提供的 C 头文件也要能在 C++ 中编译，于是 [[P2327R1]] 撤销了按位复合赋值的弃用，[[CWG2654]] 又撤销了其余复合赋值的弃用。现在仍然弃用的是：使用 volatile 赋值的结果，`volatile` 对象的 `++` 和 `--`，`volatile` 形参和返回类型，`volatile` 结构化绑定（[[depr.volatile.type]]）。

## 部分重叠的对象（¶7）

¶7 存入一个对象的值，如果是从另一个与它存储有任何重叠的对象读出的，那么两者必须完全重叠并且类型相同，否则行为未定义 {{ub}}。注 3 说明，这只约束赋值左右两边之间的关系，不是一般的别名规则（后者见 [[basic.lval]]）。

这条规则给实现留出了自由：平凡类类型的赋值可以像 `memcpy` 那样按任意顺序、任意宽度搬运字节，而不必像 `memmove` 那样处理部分重叠。完全重叠（自赋值）没有问题，每个字节都复制到自己身上；部分重叠则可能读到已经被覆盖的字节。

部分重叠基本只能通过联合体产生：

```cpp title="assign-overlap.cpp" ub
struct A { int a, b; };
struct B { int pad; A in; };   // B::in 相对于联合体起始偏移 sizeof(int)
union U { A x; B y; };

int main() {
    U u{.x = {1, 2}};
    u.y.in = u.x;     // UB：源 u.x 与目标 u.y.in 部分重叠
    return u.y.in.a;
}
```

本机用 `-fsanitize=address` 运行这段代码，AddressSanitizer 报告 `memcpy-param-overlap`：Clang 正是把这次赋值编译成了 `memcpy`。正确的写法是先复制到临时对象：`A tmp = u.x; u.y.in = tmp;`。

!!! impl "实现视角"
    内置赋值编译为一条存储指令，必要时先做类型转换。对普通内存，复合赋值是读、改、写三步，不是原子操作；即使 x86 的 `add [mem], reg` 是一条指令，没有 `lock` 前缀也不保证原子性。需要原子性要用 `std::atomic`，它的 `+=` 是原子的读—改—写操作。

## 常见误解

!!! pitfall "以为 `x += 1` 是原子的"
    它是读—改—写，多线程下要用 `std::atomic`。

!!! pitfall "以为 `i = i++ + 1` 在 C++14 中也有定义"
    C++17 之前它是 UB。C++17 起有定义，但仍然难读，不要这样写。

## 思考题

!!! question "思考题 1"
    在 C++17 中，`int i = 0; i += i++;` 之后 `i` 是多少？

<details markdown="1">
<summary>答案</summary>

右操作数先求值：`i++` 的值是 0，副作用使 `i` 变为 1。然后复合赋值读取 `i`（现在是 1），加上右操作数的值 0，写回 1。结果 `i == 1`，有定义。在 C++14 中，`i++` 的副作用与复合赋值对 `i` 的读写之间没有顺序，是 UB。
</details>

!!! question "思考题 2"
    `struct S { int v; S& operator=(int x) { v = x; return *this; } }; S s; int i = 0; s = i++, i;` 之后 `s.v` 是多少？

<details markdown="1">
<summary>答案</summary>

逗号的优先级低于赋值，所以这是 `(s = i++), i;`。`s = i++` 调用 `s.operator=(i++)`，`i++` 的值是 0，所以 `s.v == 0`，之后求值并丢弃 `i`。想让 `s` 得到逗号表达式的值，要写 `s = (i++, i)`，此时 `s.v == 1`。
</details>

## 小结

| 方面 | 规则 | 段落 |
|---|---|---|
| 左操作数 | 可修改的左值 | ¶1 |
| 结果 | 左操作数类型的左值，位域保持位域 | ¶1 |
| 求值顺序 | 右先于左（C++17）；写入在两边值计算之后 | ¶1 |
| 复合赋值与函数调用 | 一次不可分割的求值 | ¶1 |
| 存入的值 | 整数类型按同余；volatile 指针存无效值时经 `uintptr_t` 往返 | ¶2 |
| 有符号位域装不下 | {{impl}} | ¶4 |
| 使用 volatile 赋值的结果 | {{deprecated}} | ¶5 |
| `E1 op= E2` | 等价于 `E1 = E1 op E2`，`E1` 只求值一次 | ¶6 |
| 部分重叠的赋值 | {{ub}} | ¶7 |
| 右侧花括号列表 | 标量：至多一个元素，禁止窄化；类：传给 `operator=` | ¶8 |
