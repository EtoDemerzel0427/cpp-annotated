---
title: 求值顺序
summary: 每个运算符的操作数之间是有序、不确定顺序还是无序，哪些写法因此是未定义行为，以及这些规则从序列点到 C++17 是怎样演变的。
status: draft
since: c++98
order: 35
papers: N2239, P0145R3
related: intro.execution, intro.races, expr.call, expr.sub, expr.assign, expr.shift, expr.mptr.oper, expr.log.and, expr.cond, expr.comma, over.match.oper, expr.new, dcl.init.list, expr.post.incr
tags: 求值顺序, 序列点, UB, 专题
updated: 2026-10-19
---

!!! tldr
    - 两个求值之间有三种关系：有序、不确定顺序（谁先未指定，但不交错）、无序（可以交错）。对同一个标量的两次修改，或者一次修改和一次读取，如果无序，就是 UB。
    - C++17 起，`<<`、`>>`、`[]`、`.*`、`->*`、成员调用的对象表达式都是左先右后，赋值是右先左后；`&&`、`||`、`?:`、`,` 一直是左先右后。
    - 函数实参之间是不确定顺序；`+`、`*`、`==` 等其余二元运算符的两个操作数仍然无序。
    - 用运算符语法调用重载运算符时，操作数按对应内置运算符的顺序求值。
    - 常量求值中，原本无序或不确定顺序的子表达式一律按词法顺序求值。

## 先看几个例子

```cpp run title="classic-cases.cpp" ok
#include <map>
#include <cstddef>

int main() {
    int i = 0;
    i = i++ + 1;            // C++17：i == 1
    int a[4]{};
    a[i] = i++;             // C++17：先求值 i++（值为 1，i 变为 2），再 a[2] = 1
    std::map<int, std::size_t> m;
    m[7] = m.size();        // C++17：先调用 size()，m[7] == 0
    int x = 3, y = 5;
    x ^= y ^= x ^= y;       // C++17：交换 x 和 y
    return (i == 2 && a[2] == 1 && m[7] == 0 && x == 5 && y == 3) ? 0 : 1;
}
```

```cpp title="still-ub.cpp" ub
int g(int x) { return x; }

int main() {
    int i = 0;
    int a = i++ + i++;          // UB：+ 的两个操作数无序
    int b = (i = i++ + i);      // UB：i++ 的修改与读取 i 无序（标准例子）
    int c = g(i++) + g(i++);    // UB：两个 i++ 分属 + 的两个操作数，彼此无序
    return a + b + c;
}
```

第一段里的每一行在 C++14 中都是 UB 或结果未指定，C++17 起都有定义。第二段在任何版本里都是 UB，本机 Clang 23 对三行都给出 `-Wunsequenced` 警告。区别在于哪条规则给两个求值规定了先后。

## 三种关系

一次**求值**包括两部分：**值计算**（value computation），即算出表达式的值，对 glvalue 来说是确定它指代哪个对象；以及**副作用**（side effect），即修改对象、访问 volatile 对象、调用 I/O 函数等。

[[intro.execution#8]] 定义了同一线程内两个求值之间的三种关系：

| 关系 | 含义 | 两者都作用于同一个标量时 |
|---|---|---|
| **先序于**（sequenced before） | A 执行完才开始 B | 有定义 |
| **不确定顺序**（indeterminately sequenced） | A 先或 B 先，二者不重叠，但未指定是哪种 | 结果未指定，不是 UB |
| **无序**（unsequenced） | 没有先后关系，执行可以重叠 | UB |

[[intro.execution#10]] 规定了 UB 的条件：对同一内存位置的副作用，与另一个副作用、或与一次使用该位置的值的值计算无序，并且二者不是潜在并发的（并发的情形由 [[intro.races]] 的数据竞争规则处理）。当前草案还把在同一位置开始或结束一个对象的生命周期也算进来。

重叠是 UB 的根源。在硬件层面，`i++ + i++` 可以被编排成读 i、读 i、写 i+1、写 i+1，两次写交错，结果没有意义。在优化器层面，编译器可以假设无序的副作用作用于不同对象，并据此重排代码。

另外有两条普遍适用的规则：

- 运算符各操作数的值计算先于运算符结果的值计算。这只说先算出操作数的值，不涉及操作数的副作用（[[intro.execution#10]]）。
- 一个完整表达式的全部值计算和副作用，都先于下一个完整表达式（[[intro.execution#9]]）。所以两条语句之间总是有序的。

### 函数调用不交错

按 [[intro.execution#12]]，对每一次函数调用（以及 *await-expression*、*throw-expression*）*F*，不在 *F* 内部的求值，要么整体先于 *F* 内部的全部求值，要么整体在其后。也就是说，两个函数体的执行不会交错：`f() + g()` 中两次调用是不确定顺序，而不是无序。

所以把副作用放进函数体里可以避免 UB，但结果仍可能未指定。注意实参是在调用方求值的，不在函数体内。`g(i++) + g(i++)` 中的两个 `i++` 分属 `+` 的两个操作数，彼此无序，这就是上面第二段代码第三行是 UB 的原因。

## 各运算符的规定（C++17 起）

| 构造 | 操作数之间的关系 | 自哪一版 | 条款 |
|---|---|---|---|
| `a && b`、`a \|\| b` | `a` 先于 `b`，`b` 可能不求值 | C++98 | [[expr.log.and]] |
| `a ? b : c` | `a` 先于被选中的 `b` 或 `c` | C++98 | [[expr.cond]] |
| `a , b`（内置） | `a` 先于 `b` | C++98 | [[expr.comma]] |
| `a << b`、`a >> b` | `a` 先于 `b` | C++17 | [[expr.shift#4]] |
| `a = b`、`a op= b` | `b` 先于 `a`；赋值本身在二者的值计算之后 | C++17 | [[expr.assign#1]] |
| `a.*b`、`a->*b` | `a` 先于 `b` | C++17 | [[expr.mptr.oper#4]] |
| `a[b]` | `a` 先于 `b`；多个下标实参之间不确定顺序 | C++17 | [[expr.sub#1]] |
| `f(a, b)` | `f` 先于每个实参；各形参的初始化之间不确定顺序 | C++17 | [[expr.call#8]] |
| `a.f(b)`、`p->f(b)` | 对象表达式属于后缀表达式，先于 `b` | C++17 | [[expr.call#8]] |
| `new T(a)` | 调用分配函数先于求值 `a` | C++17 | [[expr.new#25]] |
| `T{a, b}`、`{a, b}` | `a` 先于 `b` | C++11 | [[dcl.init.list#4]] |
| `a++`、`a--` | 值计算先于修改 | C++11 | [[expr.post.incr]] |
| `a + b`、`a * b`、`a < b`、`a == b`、`a & b`、`a <=> b` 等 | 无序 | | [[intro.execution#10]] |
| 重载运算符，运算符语法 | 与对应内置运算符相同 | C++17 | [[over.match.oper#2]] |
| 重载运算符，函数调用语法 `operator+(a, b)` | 按函数调用：实参之间不确定顺序 | | [[expr.call]] |

## 函数调用

### 被调用者与实参

按 [[expr.call#8]]，指明被调用函数的后缀表达式先于每个实参和默认实参。每个形参的初始化，连同其中所有的值计算和副作用，与其他形参的初始化不确定顺序。这些都先于前置条件断言的求值，再先于函数体（[[intro.execution#11]]）。

由此有两个实际的后果。第一，`p->f(std::move(p))` 在 C++17 中是安全的：

```cpp run title="move-self.cpp" ok
#include <memory>

struct Node {
    int v = 7;
    int consume(std::unique_ptr<Node> self) { return self->v; }
};

int main() {
    auto up = std::make_unique<Node>();
    int r = up->consume(std::move(up));   // 先求值 up->consume（读取 up），再用 up 初始化形参
    return (r == 7 && up == nullptr) ? 0 : 1;
}
```

C++14 中，形参的初始化（移走 `up`）可能发生在求值 `up->` 之前，结果是通过空指针调用成员函数。

第二，`f(std::unique_ptr<T>(new T), g())` 不再泄漏。C++14 中两个实参的求值可以交错：先 `new T`，再调用 `g()`，最后才构造 `unique_ptr`。如果 `g()` 抛出异常，`new` 出来的对象就泄漏了，这是当年推荐 `std::make_unique` 的理由之一。C++17 中每个形参的初始化是一个整体，交错不再可能。

### 实参之间的实际顺序

不确定顺序意味着不同实现，甚至同一实现在不同调用处，都可以有不同的顺序：

```cpp run title="arg-order.cpp" unspecified
#include <cstdio>

int n = 0;
int next() { return ++n; }
void show(int a, int b) { std::printf("%d %d\n", a, b); }

int main() {
    show(next(), next());   // 输出 "1 2" 或 "2 1"，未指定
}
```

本机 Clang 23 输出 `1 2`。一些按调用约定从右往左准备实参的实现会得到 `2 1`。可移植的代码不能依赖其中任何一种。

## 重载运算符

[[over.match.oper#2]] 规定，用运算符语法写出的重载运算符调用，操作数按内置运算符规定的顺序求值。下面改编自 [[expr.call]] 的例 5：

```cpp run title="overloaded-order.cpp" ok
struct S { S(int) {} };
int operator<<(S, int) { return 0; }

int main() {
    int i, j;
    int x = S(i = 1) << (i = 2);             // 运算符语法：左先右后，i 最终为 2
    int y = operator<<(S(j = 1), j = 2);     // 函数调用语法：j 是 1 还是 2 未指定
    (void)x; (void)y;
    return i == 2 ? 0 : 1;
}
```

本机 Clang 23 对第二行给出 `multiple unsequenced modifications to 'j'` 警告。这两个实参其实是不确定顺序而不是无序，警告偏保守。

这条规则同样适用于重载的 `&&`、`||` 和 `,`。C++17 起它们的左操作数先于右操作数，但重载的 `&&`、`||` 仍然没有短路，两个操作数都会被求值（[[expr.log.and]]、[[expr.comma]]）。

## 其他语境

- **花括号初始化**：花括号里的各个初始化子句从左往右有序（[[dcl.init.list#4]]），即使最终调用的是构造函数。所以 `T{f(), g()}` 有确定的顺序，`T(f(), g())` 没有。需要确定顺序时可以利用这一点。
- **new 表达式**：调用分配函数先于求值 *new-initializer* 里的表达式（[[expr.new#25]]）。C++14 中 `new T(f())` 可以先调用 `f()` 再分配内存。
- **成员初始化**：按成员的声明顺序进行，与 *mem-initializer* 的书写顺序无关（[[class.base.init]]）。这是构造函数的执行顺序，不属于表达式求值规则。
- **临时对象的析构**：在完整表达式求值完毕之后进行，通常按构造的逆序（[[class.temporary]]）。

## 常量求值中按词法顺序

[[intro.execution#16]] 规定，作为核心常量表达式求值时，原本无序或不确定顺序的操作数和子表达式一律按词法顺序求值。用到的默认实参，按照如同为对应形参写出了实参的顺序求值。这是 C++23 之后的新措辞。

```cpp run title="constexpr-lexical.cpp" ok
constexpr int g(int a, int b) { return a * 10 + b; }

constexpr int h() {
    int i = 0;
    return g(++i, ++i);         // 常量求值中按词法顺序：g(1, 2)
}
static_assert(h() == 12);

constexpr int f() {
    int i = 0;
    return i++ + i++;           // 常量求值中按词法顺序：0 + 1
}
static_assert(f() == 1);

int main() {}
```

这样编译期的结果就不依赖于实现。本机 Clang 23 接受这两个 `static_assert`，同时对两处 `return` 给出 `-Wunsequenced` 警告。注意 `f()` 只在常量求值中有定义；同一个函数在运行期被调用，`i++ + i++` 仍然是 UB。

## 历史：从序列点到 C++17

### C++98：序列点

C++98 沿用 C 的**序列点**（sequence point）模型。序列点处，之前的副作用都已完成，之后的都还没开始。序列点位于完整表达式末尾、`&&` `||` `?:` `,` 的第一个操作数之后、进入函数体之前等处。规则是：两个相邻序列点之间，一个对象最多被修改一次，而且读取旧值只能用于确定要存入的新值。

这个模型有两个问题。嵌套表达式里很难界定哪两个序列点相邻；而且它只描述单线程的执行，无法和多线程内存模型衔接。

### C++11：先序关系

C++11 为配合新的内存模型（[[intro.multithread]]），用先序关系重写了全部顺序规则（[[N2239]]）。单线程内的先序关系与线程间的同步关系一起，构成了 happens-before（[[intro.races]]）。

重写基本保持原有语义，也修复了一些角落。例如 `i = ++i + 1`：前置 `++i` 定义为 `i += 1`，赋值的修改又规定在操作数的值计算之后，于是 `++i` 的修改先于外层赋值。这在 C++03 中是 UB，C++11 起有定义。

### C++17：P0145

[[P0145R3]] 的动机例子来自一本广为流传的 C++ 教材，标准把它收作 [[expr.call]] 的例 4：

```cpp run title="p0145-replace.cpp" ok
#include <string>
#include <cassert>

int main() {
    std::string s = "but I have heard it works even if you don't believe in it";
    s.replace(0, 4, "").replace(s.find("even"), 4, "only").replace(s.find(" don't"), 6, "");
    assert(s == "I have heard it works only if you believe in it");   // C++17 起保证
}
```

C++14 中，后缀表达式 `s.replace(0, 4, "").replace` 与实参 `s.find("even")` 之间没有顺序。`find` 可能先执行，看到的是还没删掉 `but ` 的字符串，得到错误的位置。

P0145 在程序员直觉上认为有顺序的地方加上了顺序：后缀表达式先于实参（包括链式调用中的前一次调用）；`<<`、`>>` 左先右后，照顾 iostream 链；赋值右先左后；`.*`、`->*`、`[]` 左先右后；重载运算符遵循内置顺序。

实参之间本来也打算规定为从左往右，但考虑到有些实现按调用约定从右往左准备实参，最后只规定了不确定顺序。这比 C++14 的无序、可交错要强，但仍不是固定顺序。

### 各版本的判定

| 代码 | C++03 | C++11/14 | C++17 起 |
|---|---|---|---|
| `i = ++i + 1;` | {{ub}} | OK | OK |
| `i = i++ + 1;` | {{ub}} | {{ub}} | OK，`i` 增加 1 |
| `i = i++ + i;` | {{ub}} | {{ub}} | {{ub}}，`+` 的操作数无序 |
| `i++ + i++` | {{ub}} | {{ub}} | {{ub}} |
| `a[i] = i++;` | {{ub}} | {{ub}} | OK，右边先 |
| `f(i++, i++);` | {{ub}} | {{ub}} | {{unspec}}，不确定顺序 |
| `f(i++) + g(i++)` | {{ub}} | {{ub}} | {{ub}}，`i++` 不在函数体内 |
| `std::cout << i << i++;` | {{ub}} | {{ub}} | OK，两次都输出旧值 |
| `m[k] = m.size();` | {{unspec}} | {{unspec}} | OK，先调用 `size()` |
| `x = (i++, i);` | OK | OK | OK |
| `a ^= b ^= a ^= b;` | {{ub}} | {{ub}} | OK，交换 `a`、`b` |

## 工具

Clang 的 `-Wunsequenced`（默认开启）和 GCC 的 `-Wsequence-point`（`-Wall` 包含）检测同一个完整表达式里对同一变量的无序修改。它们在语法层面工作，只能发现变量名直接出现的情形，看不穿指针和引用。UBSan 不检测这类问题。

最可靠的办法是写法本身：一个完整表达式里，一个对象最多修改一次，并且不在同一表达式里再读它，除非能指出保证顺序的那条规则。需要顺序时，拆成多条语句，或者使用花括号初始化、逗号运算符、`&&`、`||`。

## 思考题

!!! question "思考题 1"
    `v[i] = v[j]++;`（`i == j`，`v` 是 `std::vector<int>`）在 C++14 和 C++17 中分别如何？

<details markdown="1">
<summary>答案</summary>

`v[i]` 和 `v[j]` 都是重载 `operator[]` 的调用，返回引用；`=` 和后缀 `++` 都是作用于 `int` 的内置运算符。

C++17 中赋值右先左后：先完整求值 `v[j]++`，得到旧值，元素自增；再求值 `v[i]`，再赋值。元素最终等于旧值，自增被覆盖，行为有定义。

C++14 中，赋值的修改只保证在两边的值计算之后，而后缀 `++` 的修改不属于它的值计算，于是对同一元素的两次修改无序，是 UB。
</details>

!!! question "思考题 2"
    为什么 C++17 给 `<<`、`>>` 规定了顺序，却没有给 `+`、`*` 规定？

<details markdown="1">
<summary>答案</summary>

P0145 只在程序员已经把运算符当作顺序操作使用的地方规定顺序。`<<`、`>>` 用于 iostream 的链式输入输出；赋值、`[]`、`.*`、成员调用链都有先定位、再操作的含义。`+`、`*` 是数学运算，依赖其操作数顺序的代码几乎总是错误，保持无序还给优化器留下了重排两个操作数的自由。
</details>
