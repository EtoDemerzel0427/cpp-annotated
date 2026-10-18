---
title: 条件运算符
summary: "?: 的完整类型推导算法：void 与 throw 操作数、同类型 glvalue 保持左值性、类类型之间的双向隐式转换尝试、借助内置候选的重载决议、算术/指针/成员指针/nullptr 的公共类型；右结合与文法细节；GNU ?: 扩展；常见陷阱"
status: done
related: expr.throw, expr.arith.conv, expr.type, dcl.init.ref, over.best.ics, over.built, over.match.oper, basic.lval, expr.log.and, meta.trans.other, class.bit
tags: 条件运算符, 值类别, 类型推导, 隐式转换
updated: 2026-10-17
---

条件运算符 `c ? x : y` 是 C++ 唯一的三元运算符，看起来只是 `if`/`else` 的表达式版本。但 `if` 是语句，两个分支可以各干各的；`?:` 是**表达式**，它必须在**编译期**给出**一个**类型和**一个**值类别——而两个分支的类型和值类别可能完全不同。本节的绝大部分篇幅（¶2–¶7）都在回答这个问题：

> 给定第二、第三操作数，整个条件表达式是什么类型、什么值类别？

这个算法是标准中最精巧的"类型合并"规则之一，`std::common_type`（[[meta.trans.other]]）的默认实现就是借用它：`decltype(false ? std::declval<T>() : std::declval<U>())`。读懂它需要熟悉值类别（[[basic.lval]]）、引用绑定中的"直接绑定"（[[dcl.init.ref]]）、隐式转换序列（[[over.best.ics]]）和复合指针类型（[[expr.type]]）。

## 算法总览

先给出整体流程，后面逐段展开。设第二、第三操作数为 `E2`、`E3`（标准里在 ¶4 内部用 E1/E2 泛指"一个操作数与另一个"）：

| 步骤 | 条件 | 结果 | 段落 |
|---|---|---|---|
| 1 | 有 `void` 操作数 | 一个是 *throw-expression* → 取另一个的类型和值类别；两个都是 `void` → `void` prvalue；否则非良构 | ¶2 |
| 2 | 两个都是同值类别的 glvalue **位域**，类型只差 cv | 视为 cv 并集后的同一类型 | ¶3 |
| 3 | 类型不同，且有类类型；或两个同值类别 glvalue 只差 cv | **双向尝试**隐式转换：恰好一个方向可行则转换；两个都行或有歧义则非良构 | ¶4 |
| 4 | 两个同值类别、同类型的 glvalue | 结果就是该类型和值类别（**保持左值性**） | ¶5 |
| 5 | 否则结果是 **prvalue**；若类型不同且有类类型 | 用内置候选做**重载决议**确定转换 | ¶6 |
| 6 | 数组/函数退化后 | 同类型 → 该类型；算术/枚举 → 常用算术转换；指针/成员指针 → 复合指针类型；`nullptr` → `std::nullptr_t`；否则非良构 | ¶7 |

## 文法、结合性与求值（¶1）

```text
conditional-expression:
    logical-or-expression
    logical-or-expression ? expression : assignment-expression
```

几个文法细节：

- **右结合**：`a ? b : c ? d : e` 是 `a ? b : (c ? d : e)`，于是可以写出"if-else if 链"式的嵌套；
- **中间操作数是完整的 *expression***，可以包含逗号运算符和赋值而无需括号：`c ? x = 1, y : z` 中间是 `(x = 1, y)`；
- **第三操作数是 *assignment-expression***：`c ? a : b = 7` 解析为 `c ? a : (b = 7)`，而不是 `(c ? a : b) = 7`。这与 C 不同——C 的第三操作数是 *conditional-expression*，`c ? a : b = 7` 在 C 中会因"对非左值赋值"而出错。

```cpp run title="cond-grammar.cpp" ok
constexpr int sign(int n) { return n < 0 ? -1 : n == 0 ? 0 : 1; }   // 右结合
static_assert(sign(-5) == -1 && sign(0) == 0 && sign(9) == 1);

constexpr int f(bool c) {
    int a = 0, b = 0;
    c ? a : b = 7;            // 即 c ? a : (b = 7)：c 为真时什么也不赋值
    return a * 10 + b;
}
static_assert(f(true) == 0 && f(false) == 7);

constexpr int g(bool c) {
    int x = 0, y = 2, z = 3;
    int r = c ? x = 1, y : z; // 中间操作数是 (x = 1, y)
    return r * 10 + x;
}
static_assert(g(true) == 21 && g(false) == 30);

int main() {}
```

语义方面：

- 第一操作数**语境转换为 `bool`**（[[conv]]）；
- **只有**第二、第三操作数之一被求值；
- 第一操作数**先于**被选中的那个操作数求值（[[intro.execution]]）。

"只求值一个"对常量求值很重要：未被选中的分支即使含有非常量的东西（比如 *throw-expression*），也不影响常量性。C++11 的 constexpr 函数只能有一条 `return` 语句，当时的惯用法正是用 `?:` 加 `throw` 做参数检查：

```cpp run title="cond-constexpr-throw.cpp" ok
#include <stdexcept>

constexpr int checked(int n) {
    return n >= 0 ? n : throw std::invalid_argument("negative");
}
static_assert(checked(3) == 3);        // OK: throw 分支未被求值
// static_assert(checked(-1) == 0);    // error: 求值了 throw-expression，非常量

int main() {}
```

## `void` 操作数（¶2）

¶2 若第二或第三操作数的类型是 `void`，必须满足以下之一：

- ¶2.1 其中**恰好一个**是（可能带括号的）*throw-expression*（[[expr.throw]]）：结果的类型和值类别就是**另一个**操作数的；若另一个是位域，结果也是位域；
- ¶2.2 两个都是 `void` 类型：结果是 `void` prvalue（注 1：包括两个都是 *throw-expression* 的情形）。

```cpp run title="cond-void.cpp" ok
#include <type_traits>

int x = 0;
bool c = true;

static_assert(std::is_same_v<decltype((c ? x : throw 0)), int&>);   // lvalue：取 x 的
static_assert(std::is_same_v<decltype((c ? throw 0 : 1)), int>);    // prvalue：取 1 的
static_assert(std::is_same_v<decltype((c ? throw 0 : throw 1)), void>);
static_assert(std::is_same_v<decltype((c ? (void)x : (void)0)), void>);

int main() {
    (c ? x : throw 0) = 5;    // OK: 结果是 lvalue
    return x == 5 ? 0 : 1;
}
```

注意 ¶2.1 要求的是语法上的 *throw-expression*，而不是"任何 `void` 表达式"：

```cpp title="cond-void-bad.cpp" error
void log();
int f(bool c, int x) {
    return c ? x : log();          // error: 一边 void（不是 throw），一边 int
}
```

为什么 *throw-expression* 能"借用"另一边的类型？因为它永远不会正常产生值——走到 `throw` 分支，控制流就离开了表达式。所以整个表达式的类型只需要满足另一边即可。这让 `return ok ? value : throw error;` 这种写法自然成立。

## 位域（¶3）

¶3 若第二、第三操作数都是**同值类别**的 glvalue **位域**，类型分别为 *cv1* `T` 和 *cv2* `T`，则在本节余下部分把它们都视为 *cv* `T`，其中 *cv* 是 *cv1* 与 *cv2* 的并集。

这一段是为了让"两个只差 cv 的位域"走到 ¶5，得到一个**位域 lvalue**。如果没有它，¶4 会尝试把一个位域绑定到 `const T&`——而引用绑定到位域时并不直接绑定（会产生临时量），结果就会退化成 prvalue。

```cpp title="cond-bitfield.cpp" ok
struct BF { int b : 3; int c : 3; const int d : 3 = 0; };

void f(bool cond) {
    BF s{};
    (cond ? s.b : s.c) = 1;          // OK: 同类型同值类别，结果是位域 lvalue（¶5）
    (cond ? throw 1 : s.b) = 2;      // OK: ¶2.1，结果是位域 lvalue
    // &(cond ? s.b : s.c);          // error: 不能对位域取地址——结果确实是位域
}
```

!!! warning "编译器现状"
    对 `cond ? s.b : s.d`（`int` 位域与 `const int` 位域），按 ¶3 + ¶5 结果应是 `const int` 位域 **lvalue**；本站测试的 Clang 23 却给出 `int` **prvalue**（`decltype((cond ? s.b : s.d))` 为 `int`）。这说明 Clang 尚未实现 ¶3 这条较新的规则。

## 类类型与"只差 cv"的双向转换尝试（¶4）

¶4 是整个算法最复杂的一步。它的适用条件是：第二、第三操作数**类型不同**，并且

- 其中一个是（可能 cv 限定的）**类类型**，或者
- 两个是**同值类别**的 glvalue，类型**只差 cv 限定**。

此时，**尝试**从每个操作数构造一个到"与另一个操作数相关的目标类型"的**隐式转换序列**。注 2 说明：做这个**判定**时忽略访问控制、操作数是否为位域、转换函数是否被删除等性质——只看"在类型层面能不能转"。

### 目标类型的选择（¶4.1–¶4.3）

设要把操作数 `E1`（类型 `T1`）转换到与另一操作数 `E2`（类型 `T2`）相关的目标类型：

- ¶4.1 若 `E2` 是 **lvalue**：目标类型是"`T2` 的**左值引用**"，但只有当该引用会**直接绑定**（[[dcl.init.ref]]）到一个 glvalue 时，才算构造成功；
- ¶4.2 若 `E2` 是 **xvalue**：目标类型是"`T2` 的**右值引用**"，同样要求直接绑定；
- ¶4.3 若 `E2` 是 **prvalue**，或者上面两种都构造不出来**且**至少一个操作数是类类型：
    - ¶4.3.1 `T1` 与 `T2` 是同一类类型（忽略 cv）：若 `T2` 的 cv 限定**至少与** `T1` 一样多，目标是 `T2`；否则不构造；
    - ¶4.3.2 否则若 `T2` 是 `T1` 的**基类**：目标是 *cv1* `T2`（保留 `T1` 的 cv）；
    - ¶4.3.3 否则：目标是 `E2` 经左值到右值、数组到指针、函数到指针转换后会有的类型。

¶4.1/¶4.2 优先尝试"绑定为引用"，目的是**尽可能保持 glvalue**：如果一边能直接变成另一边的引用，结果就还能是左值/亡值。¶4.3 是退路：转换成另一边的**值**类型。

### 结果的判定（¶4.4–¶4.6）

对两个方向分别尝试后：

- ¶4.4 两个方向**都**能构造，或者能构造的那个是**有歧义的转换序列**：程序**非良构**；
- ¶4.5 两个方向都不能构造：操作数保持不变，进入后续检查；
- ¶4.6 **恰好一个**方向能构造：对那个操作数应用该转换，用转换后的操作数替代原操作数。注 3 提醒：即使能构造隐式转换序列，实际的转换仍可能非良构（例如所需构造函数是私有的）。

"恰好一个方向"是关键的设计决策：如果 `A` 能转成 `B`、`B` 也能转成 `A`，编译器没有理由偏向任何一边，于是要求程序员写清楚。

### 例子

```cpp run title="cond-class.cpp" ok
#include <type_traits>
#include <string>
#include <utility>

struct B {};
struct D : B {};
struct X { operator int() const { return 1; } };

bool c = true;
int a = 0, b = 0;
const int ca = 0;
D d; B bb;
std::string s;
X x;

// 只差 cv 的 lvalue：a → const int& 可直接绑定，反之不行（¶4.1、¶4.6）⇒ const int lvalue
static_assert(std::is_same_v<decltype((c ? a : ca)), const int&>);

// 派生与基类的 lvalue：d → B& 直接绑定；bb → D& 不行 ⇒ B lvalue
static_assert(std::is_same_v<decltype((c ? d : bb)), B&>);

// 派生类 prvalue 与基类 lvalue：D{} 不是 glvalue，¶4.1 失败；退到 ¶4.3.2，目标 B ⇒ 切片，B prvalue
static_assert(std::is_same_v<decltype((c ? D{} : bb)), B>);

// string lvalue 与字符串字面量：
//   s → const char* 不行；"x" → std::string& 不能直接绑定，¶4.3.3 目标 std::string 可行 ⇒ string prvalue
static_assert(std::is_same_v<decltype((c ? s : "x")), std::string>);

// 类与 int：x → int 可行（转换函数）；1 → X 不行 ⇒ int prvalue
static_assert(std::is_same_v<decltype((c ? x : 1)), int>);

// 两个 xvalue 同类型：¶5 ⇒ xvalue
static_assert(std::is_same_v<decltype((c ? std::move(a) : std::move(b))), int&&>);

int main() {}
```

```cpp title="cond-class-ambiguous.cpp" error
struct Q;
struct P { P(); P(const Q&); };
struct Q { Q(); Q(const P&); };

auto r = true ? P() : Q();   // error: P → Q 与 Q → P 都可行（¶4.4）
```

Clang 的诊断很直白："conditional expression is ambiguous; 'P' can be converted to 'Q' and vice versa"。

```cpp title="cond-class-access.cpp" error
struct Priv {
private:
    Priv(int);
};

void f(bool c, Priv& p) {
    auto x = c ? p : 1;      // error: 判定时忽略访问（注 2）⇒ 选择 1 → Priv；实际转换调用私有构造函数（注 3）
}
```

这个例子说明了注 2 与注 3 的配合：判定阶段"假装"可以访问，于是确定了转换方向；真正应用转换时再检查访问，结果非良构。这样设计是为了让访问控制**不影响**表达式的类型——访问控制在 C++ 中从不改变程序的含义，只决定程序是否良构。

## 同类型同值类别的 glvalue（¶5）

¶5 若第二、第三操作数（经过上述可能的转换后）是**同值类别**、**同类型**的 glvalue，结果就是该类型和值类别；若任一操作数是位域，结果是位域。

这是 C++ 与 C 的一个重要区别：**C++ 的条件表达式可以是左值**。

```cpp run title="cond-lvalue.cpp" ok
#include <algorithm>

int main() {
    int a = 1, b = 2;
    bool pick_a = false;
    (pick_a ? a : b) = 10;             // OK: 结果是 lvalue，赋值给 b
    int& bigger = a > b ? a : b;       // OK: 绑定到 lvalue
    ++(a < b ? a : b);                 // OK
    return (b == 10 && &bigger == &b && a == 2) ? 0 : 1;
}
```

`std::max` 返回 `const T&` 而不是直接写成 `?:` 表达式，但它的实现 `return (a < b) ? b : a;` 之所以能返回引用，正是依赖于 ¶5。

注意"同值类别"：一个 lvalue 与一个同类型的 xvalue 不满足 ¶5（且它们类型相同，不触发 ¶4），于是落入 ¶6，结果是 **prvalue**：

```cpp title="cond-mixed-category.cpp" ok
#include <type_traits>
#include <utility>

int a = 0, b = 0;
static_assert(std::is_same_v<decltype((true ? a : std::move(b))), int>);   // prvalue
```

对类类型而言，这意味着 `c ? obj : std::move(other)` 会产生一次**复制**（或移动）——一个容易被忽视的性能陷阱。

## 结果为 prvalue；借助重载决议（¶6）

¶6 否则结果是 **prvalue**。若第二、第三操作数类型不同，且其中有类类型，则用**重载决议**确定要应用的转换：候选是 [[over.built]] 中为 `?:` 虚构的内置候选函数（[[over.match.oper]]），形如

- 对每对提升后的算术类型 `L`、`R`：`LR operator?:(bool, L, R)`，其中 `LR` 是 `L`、`R` 经常用算术转换后的类型；
- 对每个指针、成员指针或有作用域枚举类型 `T`：`T operator?:(bool, T, T)`。

（这些候选不能被用户直接调用，`?:` 也不能被重载；它们只是借用重载决议的机制来挑选转换。）重载决议失败则非良构；否则应用选中的转换。

这一步处理的是"两个类都**不能**互相转换，但都能转成某个内置类型"的情形：

```cpp run title="cond-overload.cpp" ok
#include <type_traits>

struct A { operator int() const { return 1; } };
struct B { operator int() const { return 2; } };

// ¶4：A ↛ B，B ↛ A；¶6：重载决议选中 int operator?:(bool, int, int)
static_assert(std::is_same_v<decltype(true ? A{} : B{}), int>);

int main() { return (false ? A{} : B{}) == 2 ? 0 : 1; }
```

## 公共类型（¶7）

¶7 对第二、第三操作数进行数组到指针和函数到指针转换。此后必须满足以下之一：

- ¶7.1 **类型相同**：结果是该类型，并从被选中的操作数**复制初始化**。对类类型的 prvalue，这里适用保证复制消除（[[dcl.init]]）；对 lvalue 操作数则真的会复制；
- ¶7.2 都是**算术或枚举**类型：常用算术转换（[[expr.arith.conv]]），结果为转换后的类型；
- ¶7.3 至少一个是**指针**：左值到右值、指针、函数指针、限定转换，得到**复合指针类型**（[[expr.type]]）；
- ¶7.4 至少一个是**成员指针**：同理得到复合指针类型；
- ¶7.5 都是 `std::nullptr_t`，或一个是 `std::nullptr_t`、另一个是空指针常量：结果为 `std::nullptr_t`。

否则非良构。

```cpp run title="cond-common-type.cpp" ok
#include <type_traits>
#include <cstddef>
#include <climits>

bool c = true;
int i = 0; long l = 0;
struct S { int x; };
enum E { e };

static_assert(std::is_same_v<decltype((c ? i : l)), long>);                // ¶7.2
static_assert(std::is_same_v<decltype((c ? 'a' : 1)), int>);               // ¶7.2：char 提升
static_assert(std::is_same_v<decltype((c ? e : 1)), int>);                 // ¶7.2：枚举参与常用算术转换
static_assert(std::is_same_v<decltype((c ? "ab" : "cde")), const char*>);  // 数组退化 + ¶7.3
static_assert(std::is_same_v<decltype((c ? nullptr : &i)), int*>);        // ¶7.3
static_assert(std::is_same_v<decltype((c ? 0 : &i)), int*>);              // ¶7.3：空指针常量
static_assert(std::is_same_v<decltype((c ? &S::x : nullptr)), int S::*>); // ¶7.4
static_assert(std::is_same_v<decltype((c ? nullptr : 0)), std::nullptr_t>); // ¶7.5

static_assert((true ? -1 : 0u) == UINT_MAX);   // 陷阱：常用算术转换得到 unsigned

int main() {}
```

最后一行是一个经典陷阱：`cond ? -1 : 0u` 的类型是 `unsigned int`，于是 `-1` 变成了 `UINT_MAX`。

```cpp title="cond-common-type-bad.cpp" error
enum E1 { e1 };
enum E2 { e2 };

void f(bool c, int* pi, long* pl) {
    auto a = c ? pi : pl;    // error: int* 与 long* 没有复合指针类型
    auto b = c ? e1 : e2;    // error: 不同枚举类型（C++26 起非良构，之前弃用）
    auto d = c ? 1 : "x";    // error: int 与 const char* 无公共类型
}
```

## GNU 扩展：省略中间操作数

GCC 和 Clang 支持 `x ?: y`，含义是 `x ? x : y`，但 `x` 只求值一次。它**不是标准 C++**：

```cpp title="cond-gnu.cpp" ok
int f(int* p, int* fallback) {
    int* q = p ?: fallback;   // GNU 扩展；-pedantic 下 Clang 警告
    return *q;                // "use of GNU ?: conditional expression extension, omitting middle operand"
}
```

（本例在 Clang 中能编译，按标准却是语法错误；这里的 `ok` 判定只说明它在 GCC/Clang 下的表现。）可移植的写法是 `p ? p : fallback`，或者当 `p` 有副作用时先存入局部变量。

## 实现视角

!!! impl
    - 简单的条件表达式常被编译为**无分支**的条件传送（x86 `cmov`、ARM `csel`）：先算出两个值，再按条件选一个。只有当两个操作数都没有副作用、不会出错且代价低时，as-if 规则才允许这样做。对 `p ? *p : 0` 这类代码，编译器必须保证不会在 `p` 为空时提前解引用。
    - `std::common_type`、`std::common_reference`（[[meta.trans.other]]）都把 `?:` 的类型规则当作"类型合并"的基础。这也是为什么 ¶4 的细节（例如派生类 prvalue 与基类 lvalue 得到切片后的基类 prvalue）会影响到 Ranges 等库组件。
    - Clang 对歧义转换的诊断："conditional expression is ambiguous; 'P' can be converted to 'Q' and vice versa"；对 `void` 与非 `void` 混用："right operand to ? is void, but left operand is of type 'int'"。

## 历史与演进

!!! history
    - **C++98**：已经有 lvalue 结果、类类型双向转换尝试的规则，但措辞基于"左值/右值"二分。
    - **C++11**：引入 xvalue 后，¶4.2（目标为右值引用）加入；"直接绑定"的要求使得 xvalue 也能保持 glvalue 身份（`c ? std::move(a) : std::move(b)` 是 xvalue）。C++11 constexpr 函数只能有一条 `return`，`?:` + `throw` 成为编译期参数检查的标准写法。
    - **C++20/C++26**：不同枚举之间、枚举与浮点之间的常用算术转换先弃用（[[P1120R0]]）后非良构（[[P2864R2]]），¶7.2 随之收紧——[[diff.cpp23.expr]] 的例子正是 `true ? e : f`。
    - 较新的措辞中加入了 ¶3（只差 cv 的位域）以及注 2/注 3 对"判定时忽略访问、位域、删除"的澄清。

## 陷阱

!!! pitfall "`c ? -1 : 0u`"
    结果是 `unsigned`，`-1` 变成 `UINT_MAX`。

!!! pitfall "`c ? obj : std::move(other)` 不是引用"
    lvalue 与 xvalue 混合，结果是 prvalue，会复制/移动一次。

!!! pitfall "`c ? a : b = 7` 以为是给选中者赋值"
    第三操作数是 *assignment-expression*，它是 `c ? a : (b = 7)`。需要 `(c ? a : b) = 7`。

!!! pitfall "派生类 prvalue 与基类对象 → 切片"
    `c ? Derived{} : base_obj` 的结果是 `Base` prvalue，派生部分被切掉。

!!! pitfall "以为 `?:` 能像 `if` 一样让两边类型不同"
    两边必须能合并为一个类型。`c ? 1 : "x"` 非良构；需要 `std::variant` 或改写为 `if`。

## 思考题

!!! question "思考题 1"
    设 `struct B {}; struct D : B {}; const D cd; B b;`，`c ? cd : b` 的类型和值类别是什么？

<details markdown="1">
<summary>答案</summary>

类型不同且有类类型 → ¶4。

- `cd`（`const D` lvalue）→ 目标 `B&`（`b` 是 lvalue，¶4.1）：`B&` 不能绑定到 `const D`（会丢 const），不能直接绑定 → 失败；`b` 是 lvalue 不是 prvalue，但两个 ¶4.1 方向都失败且有类类型，于是走 ¶4.3：`T2 = B` 是 `T1 = const D` 的基类（¶4.3.2），目标为 *cv1* `B` = `const B` → 可以构造（复制构造切片）。
- `b`（`B` lvalue）→ 目标 `const D&`（¶4.1）：不能把 `B` 绑定为 `D` 的引用 → 失败；¶4.3：`D` 不是 `B` 的基类，¶4.3.3 目标 `D`：`B` → `D` 无转换 → 失败。

恰好一个方向成功（¶4.6）：`cd` 被转换为 `const B` prvalue。此时一边是 `const B` prvalue，一边是 `B` lvalue，类型（只差 cv）不同但不满足"同值类别的 glvalue"，¶5 不适用；¶6：结果为 prvalue，类型不同但……注意此时两个操作数的类型仍不同（`const B` vs `B`），有类类型，进行重载决议——内置候选中没有类类型参数，重载决议失败？

实际上，类类型 prvalue 的 cv 限定会在 [[expr.type]] 中被保留，而 Clang 和 GCC 都把这个表达式的结果定为 `const B`（或 `B`）prvalue。这个例子正好落在标准措辞的灰色地带：严格逐字阅读会得出"非良构"，主流实现则给出切片后的 `B` 类 prvalue。遇到这种情况，最好的答案是：**不要写这样的代码**，显式写出 `static_cast<const B&>(cd)`。
</details>

!!! question "思考题 2"
    为什么 ¶4 在两个方向都能转换时选择"非良构"，而不是像重载决议那样挑一个"更好"的？

<details markdown="1">
<summary>答案</summary>

因为这里没有一个自然的"更好"标准：重载决议比较的是**同一个实参**到**不同参数类型**的转换序列，而 `?:` 面对的是**两个不同的操作数**分别转向对方。比较"`A` → `B` 的转换"和"`B` → `A` 的转换"哪个更好没有意义——它们导致的结果类型完全不同（`A` 还是 `B`）。若随便选一个，程序员几乎不可能预测结果类型；要求恰好一个方向可行，保证了结果类型是唯一确定且显而易见的。真正需要时，程序员可以显式转换其中一个操作数。
</details>

## 小结

| 操作数情形 | 结果 |
|---|---|
| 一边 *throw-expression* | 另一边的类型和值类别 |
| 两边 `void` | `void` prvalue |
| 同类型同值类别 glvalue | 该类型和值类别（可以是 lvalue！） |
| 只差 cv 的 lvalue | cv 更多的那个类型的 lvalue |
| 派生/基类 lvalue | 基类 lvalue |
| 类类型可单向转换 | 转换后的类型 |
| 类类型双向可转换 | {{ill-formed}} |
| 类类型都能转到内置类型 | 重载决议选出的内置类型 prvalue |
| 算术/枚举 | 常用算术转换后的 prvalue |
| 指针/成员指针 | 复合指针类型 prvalue |
| `nullptr` 与空指针常量 | `std::nullptr_t` |
| lvalue 与 xvalue 同类型 | prvalue |
