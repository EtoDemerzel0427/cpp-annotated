---
title: 求值顺序
summary: "从 C++98 的序列点到 C++11 的 sequenced-before，再到 C++17 的 P0145：每个运算符的操作数是有序、无序还是不确定顺序；函数实参、链式调用、重载运算符、new、花括号初始化；i = i++ + 1 一类表达式在各版本中的判定；常量求值中的词法顺序"
status: draft
since: c++98
order: 35
papers: N2239, P0145R3
related: intro.execution, intro.races, expr.call, expr.sub, expr.assign, expr.shift, expr.mptr.oper, expr.log.and, expr.cond, expr.comma, over.match.oper, expr.new, dcl.init.list, expr.post.incr
tags: 求值顺序, 序列点, UB, 专题
updated: 2026-10-18
---

"C++ 中 `f(a(), b())` 先调用 `a` 还是 `b`？"——这个问题的正确回答在 C++ 历史上变过三次。本专题把散落在各运算符条款中的顺序规则汇总起来：规范性的定义在 [[intro.execution]]，每个运算符的具体规定在各自的条款里（链接见下表）。

先给结论：

- **C++17 起**，以下操作数是**从左往右**有序的：`&&`、`||`、`?:`、`,`（一直如此），以及 `<<`、`>>`、`.*`、`->*`、`[]`、`a.b`/`a->b` 的对象表达式、函数调用中"被调用者"相对于实参；**赋值**（含复合赋值）是**从右往左**：右操作数先于左操作数。
- 函数**实参之间**是**不确定顺序**（indeterminately sequenced）：一个实参的求值完整地在另一个之前或之后，不会交错，但哪个先是未指定的。
- 其余二元运算符（`+ - * / % < > <= >= == != <=> & ^ |`）的两个操作数**无序**（unsequenced）：对同一标量的两次修改、或修改与读取同时出现，就是 **UB**。
- 重载运算符用运算符语法调用时，遵循**内置运算符**的顺序。

## 一、三种关系：有序、不确定顺序、无序

[[intro.execution#8]] 定义了单线程内求值之间的三种关系：

| 关系 | 含义 | 两个副作用作用于同一标量时 |
|---|---|---|
| **A sequenced before B** | A 的执行在 B 之前完成 | 有定义 |
| **不确定顺序**（indeterminately sequenced） | A 在 B 之前或 B 在 A 之前，二者不重叠，但不知道是哪一种 | 结果**未指定**（不是 UB） |
| **无序**（unsequenced） | 没有顺序关系，执行可以**重叠** | **UB**（[[intro.execution#10]]） |

"重叠"是 UB 的根源：在 CPU 层面，`i++ + i++` 可能被编排成"读 i、读 i、写 i+1、写 i+1"，两次写交错，结果无意义；而在优化器层面，编译器可以**假设**无序的副作用作用于不同对象，并据此重排。

"一个求值"包括两部分：**值计算**（value computation，算出表达式的值，对 glvalue 来说是确定它指代哪个对象）和**副作用**（side effect，修改对象、访问 volatile、调用 I/O 等）。[[intro.execution#10]] 的 UB 条件是：对同一内存位置的**副作用**与另一个副作用、或与一个使用该对象值的值计算**无序**，且二者不是潜在并发的（并发的情形由 [[intro.races]] 的数据竞争规则管辖）。

此外有两条普适的规则：

- 运算符各操作数的**值计算**先于运算符结果的值计算（[[intro.execution#10]]）——这只说"先算出操作数的值"，不涉及副作用；
- 每个**完整表达式**的所有值计算和副作用，先于下一个完整表达式（[[intro.execution#9]]）——所以分号之间总是有序的。

## 二、总表（C++17 起）

| 构造 | 操作数之间的关系 | 引入版本 | 条款 |
|---|---|---|---|
| `a && b`、`a \|\| b` | `a` 先于 `b`（且 `b` 可能不求值） | C++98 | [[expr.log.and]] |
| `a ? b : c` | `a` 先于被选中的 `b` 或 `c` | C++98 | [[expr.cond]] |
| `a , b`（内置） | `a` 先于 `b` | C++98 | [[expr.comma]] |
| `a << b`、`a >> b` | `a` 先于 `b` | **C++17** | [[expr.shift#4]] |
| `a = b`、`a op= b` | `b` 先于 `a`；赋值在二者值计算之后 | **C++17** | [[expr.assign#1]] |
| `a.*b`、`a->*b` | `a` 先于 `b` | **C++17** | [[expr.mptr.oper#4]] |
| `a[b]` | `a` 先于 `b` | **C++17** | [[expr.sub#1]] |
| `f(a, b)` | `f`（后缀表达式）先于每个实参；实参之间**不确定顺序** | **C++17** | [[expr.call#8]] |
| `a.f(b)`、`p->f(b)` | 对象表达式 `a`/`p` 属于后缀表达式，先于 `b` | **C++17** | [[expr.call#8]] |
| `new T(a)` | 分配函数调用先于 `a`；初始化先于 `new` 表达式的值计算 | **C++17** | [[expr.new#25]] |
| `T{a, b}`、`{a, b}` | `a` 先于 `b`（花括号内从左往右） | C++11 | [[dcl.init.list]] |
| `a++`、`a--` | 值计算先于修改；对不确定顺序的函数调用是单次求值 | C++11 | [[expr.post.incr]] |
| `a + b`、`a * b`、`a < b`、`a == b`、`a & b`、`a <=> b` 等 | **无序** | — | [[intro.execution#10]] |
| 重载运算符（运算符语法） | 与对应内置运算符相同 | **C++17** | [[over.match.oper#2]] |
| 重载运算符（函数调用语法 `operator+(a, b)`） | 按函数调用：实参间不确定顺序 | — | [[expr.call]] |

另有一条保证函数调用"不交错"的规则（[[intro.execution#12]]）：对于任何**函数调用**、*await-expression* 或 *throw-expression* F，不在 F 内部的求值要么整体先于 F 内的所有求值，要么整体在其后。也就是说，**两个函数体的执行不会交错**——`f() + g()` 中 `f` 与 `g` 的调用是不确定顺序，而不是无序。这就是为什么把副作用"藏进函数"可以避免 UB（但不能避免未指定）。

## 三、历史：从序列点到 sequenced-before 到 P0145

### C++98/03：序列点

C++98 沿用 C 的**序列点**（sequence point）模型：在序列点处，之前的所有副作用都已完成、之后的都未开始。序列点出现在完整表达式末尾、`&&` `||` `?:` `,` 的第一个操作数之后、函数调用进入函数体之前和返回时。规则是："在两个相邻序列点之间，一个对象最多被修改一次，且读取旧值只能用于确定要存入的新值"。

这个模型有两个毛病：一是描述粗糙（"相邻序列点之间"在嵌套表达式中很难界定），二是**完全不适用于多线程**——序列点只描述单线程的执行。

### C++11：sequenced-before

C++11 为配合新的内存模型（[[intro.multithread]]），用 **sequenced-before** 关系重写了全部顺序规则（[[N2239]]，"A finer-grained alternative to sequence points"）。它是一个偏序关系，单线程的 sequenced-before 与线程间的 synchronizes-with 一起构成 happens-before（[[intro.races]]）。

改写基本保持了原有语义，但借机修复了一些角落。最著名的是 `i = ++i + 1`：前置 `++i` 被定义为 `i += 1`，而赋值的副作用被规定在操作数值计算之后，于是 `++i` 的副作用（作为其值计算的一部分）先于外层赋值——C++03 中是 UB，C++11 起有定义。

### C++17：P0145

[[P0145R3]]（Refining Expression Evaluation Order for Idiomatic C++）的动机来自真实代码。它的论文开头就引用了一个例子：Stroustrup《The C++ Programming Language》第 4 版中的一段代码，经过多位专家审阅，却在某些编译器上给出错误结果——标准在 [[expr.call]] 中把它收作例 4：

```cpp run title="p0145-replace.cpp" ok
#include <string>
#include <cassert>

int main() {
    std::string s = "but I have heard it works even if you don't believe in it";
    s.replace(0, 4, "").replace(s.find("even"), 4, "only").replace(s.find(" don't"), 6, "");
    assert(s == "I have heard it works only if you believe in it");   // C++17 起保证
}
```

问题在于：第二个 `replace` 的实参 `s.find("even")` 可能在第一个 `replace` **之前**求值——在 C++14 中，被调用的后缀表达式 `s.replace(0, 4, "").replace` 与实参 `s.find("even")` 之间**没有顺序**。于是 `find` 看到的是尚未删掉 "but " 的字符串，得到错误的位置。

P0145 的解决方案是给"程序员直觉上认为有顺序"的地方加上顺序：

1. 后缀表达式（包括链式调用中的前一次调用、`a.b` 的 `a`、`p->f` 的 `p`）先于函数实参；
2. `<<`、`>>` 左先右后（iostream 链）；
3. 赋值右先左后；
4. `.*`、`->*`、`[]` 左先右后；
5. 重载运算符遵循内置顺序。

函数**实参之间**原提案也希望从左往右，但委员会担心这会影响那些按 ABI 习惯从右往左压栈求值的实现的性能，最终只规定了"不确定顺序"——这比 C++14 的"无序、可交错"强，但仍不是固定顺序。

## 四、经典例子在各版本中的判定

| 代码 | C++03 | C++11/14 | C++17 起 |
|---|---|---|---|
| `i = ++i + 1;` | {{ub}} | OK | OK |
| `i = i++ + 1;` | {{ub}} | {{ub}} | OK（`i` 增加 1） |
| `i = i++ + i;` | {{ub}} | {{ub}} | {{ub}}（`+` 的两操作数无序） |
| `i++ + i++` | {{ub}} | {{ub}} | {{ub}} |
| `a[i] = i++;` | {{ub}} | {{ub}} | OK（右边先） |
| `f(i++, i++);` | {{ub}} | {{ub}} | {{unspec}}（不确定顺序） |
| `f(i++) + g(i++)` | {{ub}} | {{ub}} | {{ub}}（`i++` 不在函数体内，两者无序） |
| `std::cout << i << i++;` | {{ub}} | {{ub}} | OK（两次都输出旧值） |
| `m[k] = m.size();` | {{unspec}} | {{unspec}} | OK（先算 `size()`） |
| `x = (i++, i);` | OK | OK | OK |
| `a ^= b ^= a ^= b;` | {{ub}} | {{ub}} | OK（交换 `a`、`b`） |

```cpp run title="classic-cases.cpp" ok
#include <map>
#include <cstddef>

int main() {
    int i = 0;
    i = i++ + 1;            // C++17: i == 1
    int a[4]{};
    a[i] = i++;             // C++17: 先 i++（值 1，i 变 2），再 a[2] = 1
    std::map<int, std::size_t> m;
    m[7] = m.size();        // C++17: m[7] == 0
    int x = 3, y = 5;
    x ^= y ^= x ^= y;       // C++17: 交换
    return (i == 2 && a[2] == 1 && m[7] == 0 && x == 5 && y == 3) ? 0 : 1;
}
```

```cpp title="still-ub.cpp" ub
int g(int x) { return x; }

int main() {
    int i = 0;
    int a = i++ + i++;          // UB：+ 的操作数无序
    int b = (i = i++ + i);      // UB：i++ 的副作用与读取 i 无序（标准例子）
    int c = g(i++) + g(i++);    // UB：两个 i++ 位于不同的实参中，彼此无序
    return a + b + c;
}
```

`g(i++) + g(i++)` 值得多看一眼：函数调用"不交错"的保证只覆盖**函数体内**的求值；实参 `i++` 是在调用方求值的，它们属于 `+` 的两个操作数，因而彼此无序。Clang 对它报 "multiple unsequenced modifications to 'i'"。

## 五、函数调用

### 实参与被调用者

C++17 的 [[expr.call#8]]：

- 后缀表达式（"被调用的是谁"）先于每个实参和默认实参；
- 每个**形参的初始化**（包括其中所有的值计算和副作用）与其他形参的初始化**不确定顺序**；
- 这些都先于前置条件断言（C++26 契约）的求值，再先于函数体（[[intro.execution#11]]）。

两个重要后果：

**1. `p->f(std::move(p))` 在 C++17 中安全。**

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

C++14 中，形参的初始化（移走 `up`）可能发生在求值 `up->` 之前，于是对空指针调用成员函数——UB。

**2. `f(std::unique_ptr<T>(new T), g())` 不再泄漏。**

C++14 中实参的求值可以**交错**：先 `new T`，再调用 `g()`，最后才构造 `unique_ptr`——若 `g()` 抛出异常，`new` 出来的对象就泄漏了。这正是当年推荐 `std::make_unique` 的理由之一。C++17 规定每个形参的初始化是一个不可分割的整体，与其他形参不确定顺序，交错不再可能。（`make_unique` 仍然更好：更短、不重复类型名。）

### 实参之间的实际顺序

"不确定顺序"意味着不同实现、甚至同一实现在不同调用点可以不同。实践中，Clang 通常从左往右求值实参（本站测试 `show(next(), next())` 输出 `1 2`）；一些按调用约定从右往左准备实参的实现会得到相反的顺序。可移植的代码绝不能依赖它：

```cpp run title="arg-order.cpp" unspecified
#include <cstdio>

int n = 0;
int next() { return ++n; }
void show(int a, int b) { std::printf("%d %d\n", a, b); }

int main() {
    show(next(), next());   // 输出 "1 2" 或 "2 1"，未指定
}
```

## 六、重载运算符

[[over.match.oper#2]]：当运算符表示法被转换为函数调用时，**操作数按内置运算符规定的顺序求值**。[[expr.call]] 例 5 给出了对比：

```cpp run title="overloaded-order.cpp" ok
struct S { S(int) {} };
int operator<<(S, int) { return 0; }

int main() {
    int i, j;
    int x = S(i = 1) << (i = 2);             // 运算符语法：左先右后，i 最终为 2
    int y = operator<<(S(j = 1), j = 2);     // 函数调用语法：实参不确定顺序，j 是 1 还是 2 未指定
    (void)x; (void)y;
    return i == 2 ? 0 : 1;
}
```

这条规则同样适用于 `&&`、`||`、`,` 的重载：C++17 起它们的左操作数先于右操作数，但**短路**并没有恢复——两个操作数都会被求值（[[expr.log.and]]、[[expr.comma]]）。

## 七、其他语境

- **花括号初始化**：`{a, b, c}` 中各 *initializer-clause* 从左往右有序（[[dcl.init.list]]），**即使最终调用的是构造函数**。所以 `T{f(), g()}` 有确定顺序，而 `T(f(), g())` 没有。这是"想要顺序就用花括号"的惯用法来源。
- **`new` 表达式**：分配函数的调用先于 *new-initializer* 中的表达式（[[expr.new#25]]）。C++14 中 `new T(f())` 可能先调用 `f()` 再分配内存。
- **成员初始化**：按成员**声明**顺序，与 *mem-initializer* 的书写顺序无关（[[class.base.init]]）；这是语句级别的顺序，不属于表达式求值规则。
- **完整表达式之后的临时对象析构**：在完整表达式求值完毕后，按构造的逆序进行（[[class.temporary]]）。

## 八、常量求值中的顺序

[[intro.execution#16]]（C++23 之后的新措辞）规定：在作为核心常量表达式求值时，原本**无序**或**不确定顺序**的操作数和子表达式按**词法顺序**求值；函数调用中用到的默认实参，按"如同为对应形参提供了实参"的顺序求值。

这让常量求值的结果与实现无关：`constexpr` 函数里 `g(++i, ++i)` 在编译期总是得到"先左后右"的结果，不同编译器之间不会出现分歧。

```cpp run title="constexpr-lexical.cpp" ok
constexpr int g(int a, int b) { return a * 10 + b; }

constexpr int h() {
    int i = 0;
    return g(++i, ++i);     // 常量求值中按词法顺序：g(1, 2)
}
static_assert(h() == 12);

int main() {}
```

（Clang 对此仍给出 `-Wunsequenced` 警告"multiple unsequenced modifications"——对实参而言这其实是"不确定顺序"而非"无序"，警告措辞偏保守。）

!!! warning "常量求值不检测无序修改"
    [[expr.const.core]] 要求常量求值诊断核心语言 UB，但实践中主流编译器**不**检测"无序的副作用"这类 UB：`constexpr int f() { int i = 0; return i++ + i++; }` 在 Clang 23 中可以作为常量表达式求值（仅有 `-Wunsequenced` 警告）。结合 ¶16 的词法顺序规则，这类表达式在常量求值中的地位并不清晰——不要依赖它。

## 九、工具

- **Clang** `-Wunsequenced`（默认开启）、**GCC** `-Wsequence-point`（`-Wall` 包含）：检测同一完整表达式中对同一变量的无序修改。它们是语法层面的检测，只能发现变量名直接出现的情形，看不穿指针和引用。
- **UBSan** 不检测无序修改（运行期无法知道"本可以以另一种顺序执行"）。
- 最可靠的工具是写法：**一个完整表达式里，最多修改一个对象一次，并且不在同一表达式中再读它**——除非你能指出保证顺序的那条规则。

## 十、思考题

!!! question "思考题 1"
    `v[i] = v[j]++;`（`i == j`，`v` 为 `std::vector<int>`）在 C++14 和 C++17 中分别如何？

<details markdown="1">
<summary>答案</summary>

`v[i]` 与 `v[j]` 都是重载 `operator[]` 的调用，返回引用；`=` 与 `++` 都作用于 `int`（内置运算符）。

- **C++17**：赋值右先左后：先完整求值 `v[j]++`（得到旧值，元素自增），再求值 `v[i]`，再赋值。结果元素等于旧值——自增被覆盖。有定义。
- **C++14**：`v[j]++` 的副作用（修改元素）与赋值的副作用（修改同一元素）都在同一完整表达式中，赋值的副作用只保证在两边**值计算**之后；后缀 `++` 的**修改**不是其值计算的一部分，于是两次修改无序 → **UB**。
</details>

!!! question "思考题 2"
    为什么 C++17 只给 `<<`、`>>` 加了顺序，而没有给 `+`、`*` 加？

<details markdown="1">
<summary>答案</summary>

P0145 的原则是"在程序员已经把运算符当作**顺序操作**使用的地方给出顺序"：`<<`/`>>` 是 iostream 的链式输出/输入，赋值、`[]`、`.*`、成员调用链都有天然的"先定位、再操作"或"先算值、再存储"的含义。而 `+`、`*` 是数学运算，代码依赖其操作数顺序几乎总是 bug；保持无序还给优化器留出了重排、并行计算两个操作数的自由。此外，给所有运算符规定顺序会与已有实现（以及 C 语言）的行为产生大量分歧。
</details>

## 小结

- 判断一个表达式是否有定义，先找出所有**副作用**，再对每一对作用于同一对象的求值，问："有没有一条规则让它们有序？"——有，则有定义；只是不确定顺序，则结果未指定；什么规则都没有，则 UB。
- C++17 的顺序规则覆盖了几乎所有"看起来像顺序操作"的写法：链式调用、iostream、赋值、下标、成员指针、`new`。
- 仍然无序的：算术、比较、位运算的两个操作数；仍然只是不确定顺序的：函数实参之间。
- 想要确定顺序：拆成多条语句，或使用花括号初始化、逗号运算符、`&&`/`||`。
