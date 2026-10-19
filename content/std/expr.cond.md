---
title: 条件运算符
summary: c ? x : y 的结果类型和值类别怎样从两个分支推出来：throw 分支、同类型左值、类类型之间的单向转换、算术与指针的公共类型。
status: done
related: expr.throw, expr.arith.conv, expr.type, dcl.init.ref, over.best.ics, over.built, over.match.oper, basic.lval, meta.trans.other, class.bit
tags: 条件运算符, 值类别, 类型推导, 隐式转换
updated: 2026-10-19
---

!!! tldr
    - `?:` 只求值被选中的分支，但整个表达式只有一个类型和一个值类别，编译期就要从两个分支推出来。
    - 两个分支是同类型、同值类别的 glvalue 时，结果仍是那个 glvalue，所以 `(c ? a : b) = 1` 合法；一边 lvalue、一边 xvalue 时结果退化为 prvalue。
    - 一边是 `throw` 表达式时，结果取另一边的类型和值类别。
    - 涉及类类型时，编译器尝试把每一边转换成另一边：恰好一个方向可行才良构，两个方向都可行就有歧义。
    - 其余情况结果是 prvalue：算术类型做常用算术转换（`c ? -1 : 0u` 是 `unsigned`），指针取复合指针类型。

## 一个表达式，两个分支

```cpp
int a = 1, b = 2;
(flag ? a : b) = 10;    // OK：给选中的那个变量赋值
auto x = flag ? 1 : "x"; // error：int 和 const char* 合并不出一个类型
```

`if` 是语句，两个分支可以各做各的事。`?:` 是表达式，编译器必须在不知道 `flag` 的值时就确定它的类型和值类别，所以标准用第 2–7 段定义了一套合并两个分支的算法。

先说明几个词。**值类别**（[[g:value-category]]）把表达式分成三种：**lvalue** 指代一个有身份的对象（变量名、`*p`）；**xvalue** 也指代对象，但这个对象的资源可以被拿走（`std::move(x)`）；**prvalue** 是一个纯粹的值（`1`、`a + b`、`T{}`）。lvalue 和 xvalue 合称 **glvalue**（[[basic.lval]]）。

下文用第二操作数、第三操作数指 `?` 和 `:` 后面的两个分支。算法按以下顺序检查，命中一条就不再往下：

| 步骤 | 情形 | 结果 | 段 |
|---|---|---|---|
| 1 | 有 `void` 分支 | 一边是 `throw` 表达式：取另一边；两边都是 `void`：`void` prvalue；否则非良构 | 2 |
| 2 | 两个只差 cv 的同值类别位域 | 视为同一类型 | 3 |
| 3 | 类型不同且有类类型，或两个同值类别 glvalue 只差 cv | 尝试双向隐式转换，恰好一个方向可行就做这个转换 | 4 |
| 4 | 同类型、同值类别的 glvalue | 结果就是这个类型和值类别 | 5 |
| 5 | 其余情况 | prvalue；有类类型时借内置候选做重载决议 | 6 |
| 6 | 数组、函数退化之后 | 同类型、常用算术转换、复合指针类型或 `std::nullptr_t` | 7 |

## 文法与求值（¶1）

```text
conditional-expression:
    logical-or-expression
    logical-or-expression ? expression : assignment-expression
```

¶1 第一操作数按语境转换为 `bool`（[[conv]]），先求值；然后只求值第二、第三操作数中被选中的一个。第一操作数先于被选中的操作数（[[intro.execution]]）。

文法决定了三处容易看错的地方：

- 条件运算符右结合，`a ? b : c ? d : e` 是 `a ? b : (c ? d : e)`，可以写成 if-else 链。
- 中间操作数是完整的 *expression*，可以含逗号：`c ? x = 1, y : z` 的中间部分是 `(x = 1, y)`。
- 第三操作数是 *assignment-expression*，所以 `c ? a : b = 7` 是 `c ? a : (b = 7)`。C 的第三操作数是 *conditional-expression*，同样的代码在 C 里是对非左值赋值的错误。

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

只求值一个分支，所以没被选中的分支不影响常量求值。C++11 的 constexpr 函数只能有一条 `return`，参数检查就靠 `?:` 加 `throw`：

```cpp run title="cond-constexpr-throw.cpp" ok
#include <stdexcept>

constexpr int checked(int n) {
    return n >= 0 ? n : throw std::invalid_argument("negative");
}
static_assert(checked(3) == 3);        // OK：throw 分支没有被求值
// static_assert(checked(-1) == 0);    // error：求值了 throw，不是常量表达式

int main() {}
```

## 同类型的 glvalue 保持左值性（¶5）

¶5 如果两个操作数（经过前面几步可能的转换后）是同类型、同值类别的 glvalue，结果就是这个类型和值类别。任一操作数是位域时，结果也是位域。

这是 C++ 与 C 的一个区别：C++ 的条件表达式可以是左值。

```cpp run title="cond-lvalue.cpp" ok
int main() {
    int a = 1, b = 2;
    bool pick_a = false;
    (pick_a ? a : b) = 10;             // OK：结果是 lvalue，赋值给 b
    int& bigger = a > b ? a : b;       // OK：绑定到 lvalue
    ++(a < b ? a : b);                 // OK
    return (b == 10 && &bigger == &b && a == 2) ? 0 : 1;
}
```

`std::max` 的典型实现 `return (a < b) ? b : a;` 能返回 `const T&`，靠的就是这一段。

同值类别这个条件要注意。一个 lvalue 和一个同类型的 xvalue 不满足第 5 段；因为类型相同，第 4 段也不适用，于是落到第 6 段，结果是 prvalue：

```cpp title="cond-mixed-category.cpp" ok
#include <type_traits>
#include <utility>

int a = 0, b = 0;
static_assert(std::is_same_v<decltype((true ? a : std::move(b))), int>);       // prvalue
static_assert(std::is_same_v<decltype((true ? std::move(a) : std::move(b))), int&&>); // xvalue
```

对类类型，`c ? obj : std::move(other)` 因此会多一次复制或移动。

## 算术、指针与 nullptr 的公共类型（¶7）

¶7 走到这一步时结果已经是 prvalue。先对两个操作数做数组到指针、函数到指针转换，然后必须满足以下之一，否则非良构：

- ¶7.1 类型相同：结果就是这个类型，从被选中的操作数复制初始化。
- ¶7.2 都是算术或枚举类型：做**常用算术转换**（[[g:usual-arithmetic-conversions]]，也就是 `a + b` 求公共类型的那套规则，[[expr.arith.conv]]）。
- ¶7.3 至少一个是指针：转换到两者的**复合指针类型**（[[g:composite-pointer-type]]，两个指针都能隐式转换到的那个指针类型，[[expr.type]]）。
- ¶7.4 至少一个是成员指针：同样取复合指针类型。
- ¶7.5 都是 `std::nullptr_t`，或一个是 `std::nullptr_t`、另一个是空指针常量：结果是 `std::nullptr_t`。

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
static_assert(std::is_same_v<decltype((c ? e : 1)), int>);                 // ¶7.2：枚举也参与
static_assert(std::is_same_v<decltype((c ? "ab" : "cde")), const char*>);  // 数组退化后 ¶7.3
static_assert(std::is_same_v<decltype((c ? nullptr : &i)), int*>);        // ¶7.3
static_assert(std::is_same_v<decltype((c ? 0 : &i)), int*>);              // ¶7.3：空指针常量
static_assert(std::is_same_v<decltype((c ? &S::x : nullptr)), int S::*>); // ¶7.4
static_assert(std::is_same_v<decltype((c ? nullptr : 0)), std::nullptr_t>); // ¶7.5

static_assert((true ? -1 : 0u) == UINT_MAX);   // 常用算术转换得到 unsigned

int main() {}
```

最后一行是常见的错误来源：`c ? -1 : 0u` 的类型是 `unsigned int`，`-1` 变成了 `UINT_MAX`。

```cpp title="cond-common-type-bad.cpp" error
enum E1 { e1 };
enum E2 { e2 };

void f(bool c, int* pi, long* pl) {
    auto a = c ? pi : pl;    // error：int* 与 long* 没有复合指针类型
    auto b = c ? e1 : e2;    // error：两个不同的枚举类型（C++26 起非良构）
    auto d = c ? 1 : "x";    // error：int 与 const char* 无公共类型
}
```

不同枚举类型之间的常用算术转换在 C++20 被弃用（[[P1120R0]]），C++26 改为非良构（[[P2864R2]]，见 [[diff.cpp23.expr]]）。

## `void` 分支与 `throw`（¶2）

¶2 第二或第三操作数是 `void` 类型时，必须满足以下之一：

- ¶2.1 恰好一个操作数是（可能带括号的）*throw-expression*（[[expr.throw]]）。结果的类型和值类别取另一个操作数的；另一个是位域时，结果也是位域。
- ¶2.2 两个都是 `void` 类型，结果是 `void` prvalue。注 1 指出，两个都是 *throw-expression* 也属于这种情形。

```cpp run title="cond-void.cpp" ok
#include <type_traits>

int x = 0;
bool c = true;

static_assert(std::is_same_v<decltype((c ? x : throw 0)), int&>);   // lvalue：取 x 的
static_assert(std::is_same_v<decltype((c ? throw 0 : 1)), int>);    // prvalue：取 1 的
static_assert(std::is_same_v<decltype((c ? throw 0 : throw 1)), void>);
static_assert(std::is_same_v<decltype((c ? (void)x : (void)0)), void>);

int main() {
    (c ? x : throw 0) = 5;    // OK：结果是 lvalue
    return x == 5 ? 0 : 1;
}
```

`throw` 分支能借用另一边的类型，是因为它永远不会正常产生值：一旦走到这个分支，控制就离开了整个表达式。第 2.1 项要求的是语法上的 *throw-expression*，普通的 `void` 函数调用不行：

```cpp title="cond-void-bad.cpp" error
void log();
int f(bool c, int x) {
    return c ? x : log();          // error：一边是 void（不是 throw），一边是 int
}
```

## 类类型：双向转换尝试（¶4）

```cpp
struct B {}; struct D : B {};
D d; B b;
c ? d : b;       // 类型是什么？
```

两个分支类型不同，`d` 可以当作 `B` 使用，`b` 却不能当作 `D`。第 4 段的做法是：从每一边出发，尝试构造一个到另一边相关类型的隐式转换序列（[[over.best.ics]]），看哪个方向能成。

¶4 适用于两种情形：两个操作数类型不同且至少一个是类类型；或者两个都是同值类别的 glvalue，类型只差 cv 限定（如 `int` 和 `const int` 的左值）。

### 目标类型（¶4.1–¶4.3）

设要把操作数 `E1`（类型 `T1`）转换向另一个操作数 `E2`（类型 `T2`）：

- ¶4.1 `E2` 是 lvalue：目标是 `T2&`，但只在这个引用能**直接绑定**（[[g:bind-directly]]，绑定到对象本身而不是一个临时量，[[dcl.init.ref]]）到一个 glvalue 时才算成功。
- ¶4.2 `E2` 是 xvalue：目标是 `T2&&`，同样要求直接绑定。
- ¶4.3 `E2` 是 prvalue，或者上面两种都构造不出来且至少一边是类类型时：
    - ¶4.3.1 `T1`、`T2` 是同一个类（忽略 cv）：`T2` 的 cv 至少和 `T1` 一样多，目标就是 `T2`；否则这个方向不构造。
    - ¶4.3.2 `T2` 是 `T1` 的基类：目标是带 `T1` 的 cv 的 `T2`。
    - ¶4.3.3 否则：目标是 `E2` 经左值到右值、数组到指针、函数到指针转换后的类型。

先尝试引用，是为了尽可能保留 glvalue：一边能直接变成另一边的引用，结果就还能是 lvalue 或 xvalue。第 4.3 项是退路，转换成另一边的值类型。

注 2 说明，判定能否构造时不考虑访问控制、操作数是不是位域、转换函数是否被删除，只看类型。

### 判定（¶4.4–¶4.6）

- ¶4.4 两个方向都能构造，或者能构造的那个是有歧义的转换序列：非良构。
- ¶4.5 两个方向都不能构造：操作数不变，交给后面的步骤。
- ¶4.6 恰好一个方向能构造：对那个操作数应用这个转换，之后用转换结果代替它。注 3 提醒，能构造出转换序列，不代表实际转换一定良构。

两个方向都可行时直接报错，是因为没有合理的偏好依据：`A → B` 和 `B → A` 会得到完全不同的结果类型，随便挑一个，读代码的人无法预测。

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

// 只差 cv 的 lvalue：a → const int& 能直接绑定，反之不行 ⇒ const int lvalue
static_assert(std::is_same_v<decltype((c ? a : ca)), const int&>);

// 派生类与基类的 lvalue：d → B& 直接绑定；bb → D& 不行 ⇒ B lvalue
static_assert(std::is_same_v<decltype((c ? d : bb)), B&>);

// 派生类 prvalue 与基类 lvalue：D{} → B& 不能绑定到 glvalue，退到 ¶4.3.2 目标 B ⇒ 切片，B prvalue
static_assert(std::is_same_v<decltype((c ? D{} : bb)), B>);

// string lvalue 与字符串字面量（const char[2] lvalue）：
//   s → const char(&)[2] 不行，退到 ¶4.3.3 的 const char* 也不行；
//   "x" → std::string& 不能直接绑定，退到 ¶4.3.3 的 std::string 可行 ⇒ string prvalue
static_assert(std::is_same_v<decltype((c ? s : "x")), std::string>);

// 类与 int：x → int 可行（转换函数）；1 → X 不行 ⇒ int prvalue
static_assert(std::is_same_v<decltype((c ? x : 1)), int>);

int main() {}
```

两个方向都可行时：

```cpp title="cond-class-ambiguous.cpp" error
struct Q;
struct P { P(); P(const Q&); };
struct Q { Q(); Q(const P&); };

auto r = true ? P() : Q();   // error：P → Q 与 Q → P 都可行（¶4.4）
```

Clang 的诊断是 "conditional expression is ambiguous; 'P' can be converted to 'Q' and vice versa"。

判定时忽略访问控制，实际转换时才检查：

```cpp title="cond-class-access.cpp" error
struct Priv {
private:
    Priv(int);
};

void f(bool c, Priv& p) {
    auto x = c ? p : 1;      // error：判定时选定 1 → Priv，实际转换要调用私有构造函数
}
```

这样设计，访问控制就不会改变表达式的类型。C++ 里访问控制从不改变程序的含义，只决定程序是否良构。

## 只差 cv 的位域（¶3）

¶3 如果两个操作数是同值类别的 glvalue 位域，类型分别是 *cv1* `T` 和 *cv2* `T`，那么在本节余下的步骤里，两者都视为 *cv* `T`，*cv* 是两者 cv 的并集。

没有这一段，两个只差 cv 的位域会进入第 4 段，尝试把一个位域绑定到 `const T&`。引用绑定到位域时会生成临时量，不是直接绑定，结果就退化成 prvalue。有了第 3 段，它们直接走到第 5 段，结果是位域 lvalue。

```cpp title="cond-bitfield.cpp" ok
struct BF { int b : 3; int c : 3; };

void f(bool cond) {
    BF s{};
    (cond ? s.b : s.c) = 1;          // OK：同类型同值类别，结果是位域 lvalue（¶5）
    (cond ? throw 1 : s.b) = 2;      // OK：¶2.1，结果是位域 lvalue
    // &(cond ? s.b : s.c);          // error：结果是位域，不能取地址
}
```

!!! warning "编译器现状"
    对一个 `int` 位域 `s.b` 和一个 `const int` 位域 `s.d`，按第 3、5 段，`cond ? s.b : s.d` 应是 `const int` 位域 lvalue。本机 Clang 23 给出的是 `int` prvalue（`decltype` 为 `int`），即尚未实现第 3 段。

## 借内置候选做重载决议（¶6）

¶6 前面都不适用时，结果是 prvalue。如果两个操作数类型不同且有类类型，就借用重载决议来挑转换：候选是 [[over.built]] 为 `?:` 虚构的**内置候选**（[[g:built-in-candidate]]），例如对每一对提升后的算术类型 `L`、`R` 有 `LR operator?:(bool, L, R)`，对每个指针、成员指针或有作用域枚举类型 `T` 有 `T operator?:(bool, T, T)`。重载决议失败则非良构。

`?:` 不能被用户重载，这些候选也不能直接调用，这里只是借用挑选转换的机制。它处理的情形是：两个类互相转换不了，但都能转成同一个内置类型。

```cpp run title="cond-overload.cpp" ok
#include <type_traits>

struct A { operator int() const { return 1; } };
struct B { operator int() const { return 2; } };

// ¶4：A 与 B 互相转换不了；¶6：重载决议选中 int operator?:(bool, int, int)
static_assert(std::is_same_v<decltype(true ? A{} : B{}), int>);

int main() { return (false ? A{} : B{}) == 2 ? 0 : 1; }
```

## 实现视角

!!! impl
    - 简单的条件表达式常被编译成无分支的条件传送（x86 的 `cmov`、AArch64 的 `csel`），即两个值都算出来再挑一个。as-if 规则只在两个分支都没有副作用、不会出错时允许这样做，所以 `p ? *p : 0` 不会在 `p` 为空时提前解引用。
    - `std::common_type` 的默认实现是 `decltype(false ? std::declval<T>() : std::declval<U>())`（[[meta.trans.other]]），`std::common_reference` 也建立在 `?:` 的规则上。所以第 4 段的细节，比如派生类 prvalue 与基类 lvalue 合并成切片后的基类 prvalue，也会影响 Ranges 这样的库组件。
    - GCC 和 Clang 支持省略中间操作数的扩展 `x ?: y`，含义是 `x ? x : y` 但 `x` 只求值一次。它不是标准 C++，`-pedantic` 下 Clang 会警告。

## 历史与演进

!!! history
    - C++98 已经有左值结果和类类型的双向转换尝试，措辞基于左值、右值二分。
    - C++11 引入 xvalue 后加入了第 4.2 项（目标为右值引用），两个 xvalue 分支的结果也能保持 xvalue。
    - 不同枚举之间、枚举与浮点之间的常用算术转换在 C++20 被弃用，C++26 改为非良构，第 7.2 项随之收紧。

## 常见误解

!!! pitfall "以为 `c ? a : b = 7` 给选中的那个赋值"
    第三操作数是 *assignment-expression*，所以它是 `c ? a : (b = 7)`。给选中的那个赋值要写 `(c ? a : b) = 7`。

!!! pitfall "以为 `c ? obj : std::move(other)` 是引用"
    lvalue 和 xvalue 混合，结果是 prvalue，会复制或移动一次。

!!! pitfall "以为 `?:` 能像 `if` 一样让两边类型不同"
    两边必须合并为一个类型。`c ? 1 : "x"` 非良构；确实需要两种类型时，用 `std::variant` 或改写成 `if`。

## 思考题

!!! question "思考题 1"
    设 `struct B {}; struct D : B {}; const D cd; B b;`，`c ? cd : b` 的类型和值类别是什么？

<details markdown="1">
<summary>答案</summary>

类型不同且有类类型，进入第 4 段。

- `cd`（`const D` lvalue）向 `b`（lvalue）：第 4.1 项的目标 `B&` 不能绑定到 `const D`，失败。退到第 4.3.2 项，`B` 是 `const D` 的基类，目标是 `const B`，可以构造（复制时切片）。
- `b`（`B` lvalue）向 `cd`：第 4.1 项的目标 `const D&` 不能绑定到 `B`，失败。第 4.3.3 项的目标是 `D`，`B` 转不成 `D`，也失败。

恰好一个方向成功（第 4.6 项），`cd` 变成 `const B` prvalue。现在一边是 `const B` prvalue，一边是 `B` lvalue：第 5 段不适用；第 6 段中两边类型仍然不同（类类型 prvalue 保留 cv），要借内置候选做重载决议，而 `B` 转不成任何算术、指针类型，重载决议失败。程序非良构，Clang 报 "incompatible operand types ('const D' and 'B')"。

对比一下：`b` 声明为 `const B` 时，`cd` → `const B&` 可以直接绑定，结果是 `const B` lvalue；`cd` 去掉 `const` 时，结果是 `B` lvalue。需要时显式写 `static_cast<const B&>(cd)`。
</details>

!!! question "思考题 2"
    两个方向都能转换时，第 4 段为什么判为非良构，而不像重载决议那样挑一个更好的？

<details markdown="1">
<summary>答案</summary>

重载决议比较的是同一个实参到不同形参类型的转换，有共同的比较基准。`?:` 面对的是两个操作数分别转向对方，`A → B` 和 `B → A` 的结果类型一个是 `B`、一个是 `A`，没有可比的标准。要求恰好一个方向可行，结果类型就唯一确定；真有需要时，程序员可以显式转换其中一边。
</details>

## 小结

| 两个分支 | 结果 |
|---|---|
| 一边是 `throw` | 另一边的类型和值类别 |
| 两边都是 `void` | `void` prvalue |
| 同类型、同值类别的 glvalue | 这个类型和值类别（可以是 lvalue） |
| 只差 cv 的 lvalue | cv 较多的类型的 lvalue |
| 派生类与基类的 lvalue | 基类 lvalue |
| 类类型只有一个方向能转换 | 转换后的类型 |
| 类类型两个方向都能转换 | {{ill-formed}} |
| 两个类都能转成某个内置类型 | 重载决议选出的类型，prvalue |
| 算术、枚举 | 常用算术转换后的类型，prvalue |
| 指针、成员指针 | 复合指针类型，prvalue |
| 同类型的 lvalue 与 xvalue | prvalue |
