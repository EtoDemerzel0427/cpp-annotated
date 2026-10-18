---
title: 常量求值
summary: 第 7.7 节总览：什么是常量表达式、核心常量表达式、显然常量求值、常量初始化与立即函数；以及 constexpr 从 C++11 到 C++26 的演进
status: done
covers: expr.const.general
since: c++11
papers: N2235, N3652, P0170R1, P0784R7, P1073R3, P1143R2, P0595R2, P1938R3, P2242R3, P2448R2, P2564R3, P2280R4, P2738R1, P2747R2, P3068, P2996R13
related: expr.const.core, expr.const.const, expr.const.init, expr.const.imm, expr.const.reflect, expr.const.defns, dcl.constexpr, dcl.constinit, stmt.if, topics/compile-time-programming
tags: 常量求值, constexpr, consteval
updated: 2026-10-17
---

[expr.const] 回答的是一个看似简单的问题：**哪些表达式可以在翻译期求值？** 数组长度、`case` 标签、模板实参、`static_assert` 的条件、`constexpr` 变量的初始化器……这些上下文都"要求"一个常量表达式；而另一些上下文（全局变量的初始化、`std::is_constant_evaluated()`）则会因为表达式"是不是常量表达式"而表现出不同的语义。

本节在 C++26 草案里被拆成七个小节。和多数条款"先给定义、再给规则"的写法不同，[expr.const] 是**排除式**定义：它不说"什么是常量表达式"，而是列出"什么会让一个表达式**不是**核心常量表达式"——只要求值过程中没有踩到这张黑名单，它就是核心常量表达式。理解这一点是读懂整节的钥匙。

| 小节 | stable name | 内容 |
|---|---|---|
| 7.7.1 | [[expr.const.general]] | 语法 *constant-expression*；常量表达式的总定义；浮点一致性 |
| 7.7.2 | [[expr.const.core]] | **核心常量表达式**的黑名单（UB、`reinterpret_cast`、非 constexpr 函数调用……）；constexpr-unknown |
| 7.7.3 | [[expr.const.const]] | **常量表达式**（结果必须"可以带出去"）；整型常量表达式；转换后的常量表达式；consteval-only 值 {{c++26}} |
| 7.7.4 | [[expr.const.init]] | 常量初始化、constexpr-representable {{c++26}}、"可用于常量表达式"的变量 |
| 7.7.5 | [[expr.const.imm]] | 立即函数（`consteval`）、立即调用、consteval 向上传播 |
| 7.7.6 | [[expr.const.reflect]] | {{c++26}} 反射：注入声明、求值点与求值上下文 |
| 7.7.7 | [[expr.const.defns]] | 显然常量求值、潜在常量求值、常量析构 |

## 三层概念：核心常量表达式 → 常量表达式 → 各种"常量表达式"变体

先建立直觉。标准里有一串层层收紧的概念：

1. **核心常量表达式**（core constant expression，[[expr.const.core#2]]）：按抽象机规则求值 `E`，过程中**没有**做任何黑名单上的事。这是关于**求值过程**的约束。
2. **常量表达式**（constant expression，[[expr.const.const#4]]）：核心常量表达式，并且**结果**可以离开这次求值——结果里没有悬空/无效指针、没有不确定值或错误值。这是关于**结果**的约束。
3. 在此之上，各个上下文还会加自己的要求：
   - **整型常量表达式**（[[expr.const.const#6]]）：位域长度、未固定底层类型的枚举初值、`alignas`；
   - **转换后的常量表达式**（converted constant expression，[[expr.const.const#8]]）：数组边界、`case` 标签、非类型模板实参……只允许"安全的"隐式转换（例如禁止窄化）；
   - **按语境转换为 bool 的常量表达式**（[[expr.const.const#9]]）：`noexcept(...)`、`explicit(...)`——同样禁止窄化；
   - `static_assert` 与 `if constexpr` 的条件则只要求"按语境转换为 bool 后是常量表达式"（C++23 起允许窄化，`static_assert(N % 4)` 合法），见 [[dcl.pre#13]]、[[stmt.if#2]]。

另一条线是关于**何时**求值：

- **显然常量求值**（manifestly constant-evaluated，[[expr.const.defns#1]]）：语言**规定**必须在翻译期求值的表达式。`std::is_constant_evaluated()` / `if consteval` 观察的就是这个属性。
- **常量初始化**（constant initialization，[[expr.const.init]] + [[basic.start.static#2]]）：静态/线程存储期变量如果是 constant-initialized 的，就在静态初始化阶段完成，不参与动态初始化顺序。
- **立即函数**（immediate function，[[expr.const.imm]]）：每次调用都**必须**产生常量的函数（`consteval`），以及因为调用了它们而被"感染"的 constexpr 模板。

!!! tip "一句话版本"
    核心常量表达式管"过程干不干净"，常量表达式管"结果能不能带走"，显然常量求值管"是不是非得在编译期算"。

## 语法与总定义（¶1）

```
constant-expression:
    conditional-expression
```

*constant-expression* 在语法上就是一个 *conditional-expression*——注意它**不包括**赋值表达式和逗号表达式。所以 `int a[x = 3];`、`case 1, 2:` 在语法层面就不是 *constant-expression*（逗号表达式需要加括号：`int a[(1, 2)];` 在语法上可以，但这时是否"常量"再由语义规则判定）。

¶1 的核心是这句：

!!! std
    Expressions that satisfy these requirements, assuming that copy elision is not performed, are called constant expressions.

    满足本节要求的表达式（在假定不进行复制消除的前提下）称为常量表达式。

三点值得细读：

- **"某些上下文要求……另一些上下文的语义取决于……"**。第一类如数组边界：不是常量表达式就是 ill-formed（或变成 VLA 扩展）；第二类如全局变量初始化：是常量表达式就做静态初始化，否则做动态初始化，**两者都合法但语义不同**。后一类是"程序行为随常量性而变"的根源，见 [[expr.const.init]] 和 [[expr.const.defns]]。
- **"假定不进行复制消除"**：复制消除在运行期是可选的（非强制情形），如果常量性取决于实现是否做了消除，结果就不可移植。所以标准规定常量求值中**不做**（非强制的）复制消除——[[dcl.constexpr#4]] 也重复了这一点。这意味着在常量求值中，NRVO 一定不发生，被省略的那次复制/移动构造一定会被调用（它必须是 constexpr 的）。
- 注 1 说"某些常量表达式在翻译期求值"——**某些**，而不是全部。一个常量表达式完全可以在运行期被求值（例如 `int x = 1 + 2;` 中的 `1 + 2`，标准没要求它在编译期算）。"是常量表达式"是**属性**，"在编译期求值"是**时机**，两者不是一回事。

```cpp run ok
constexpr int sq(int x) { return x * x; }

int main() {
    int a[sq(3)];          // 数组边界：要求常量表达式 → 必须在翻译期求值
    int n = sq(3);         // 普通初始化：sq(3) 是常量表达式，但何时求值由实现决定
    static_assert(sizeof a == 9 * sizeof(int));
    return n - 9;
}
```

### 复制消除与常量求值

```cpp run ok
struct C {
    int copies = 0;
    constexpr C() = default;
    constexpr C(const C& o) : copies(o.copies + 1) {}
};

constexpr C make() {
    C c;          // 具名局部变量
    return c;     // 运行期：NRVO 可做可不做；常量求值：保证不做
}

static_assert(make().copies == 1);   // 常量求值中一定发生一次复制

int main() {
    C rt = make();
    return rt.copies;                 // 0 或 1，取决于编译器是否做 NRVO（Clang/GCC -O0 通常为 0）
}
```

[[class.copy.elision]] 中的强制消除（用纯右值初始化同类型对象，C++17 起）不属于"复制消除"的可选部分，常量求值里同样发生。

## 浮点：编译期与运行期可以不一致（¶2）

¶2 是一条**推荐实践**（recommended practice，不具强制力）加一个注：

- 推荐：实现应让浮点运算在翻译期和运行期给出**一致**的结果。
- 注：由于标准对浮点精度不作要求，翻译期计算一个浮点表达式与运行期计算同一个表达式，**结果是否相同是未指定的**（unspecified）。

标准的例子改编如下：

```cpp unspecified
bool f() {
    char array[1 + int(1 + 0.2 - 0.1 - 0.1)];   // 必须在翻译期求值
    int size = 1 + int(1 + 0.2 - 0.1 - 0.1);    // 可能在运行期求值
    return sizeof(array) == size;               // true 还是 false：未指定
}
```

`1 + 0.2 - 0.1 - 0.1` 在 IEEE 754 双精度下是 `0.9999999999999999...` 还是 `1.0`，取决于中间结果的精度（x87 的 80 位扩展精度、`FLT_EVAL_METHOD`、`-ffast-math`、FMA 收缩……）。编译器的常量折叠器通常严格按源类型做 IEEE 运算，而运行期代码可能因为编译选项而不同。

!!! impl "实现视角"
    GCC 用自带的软件浮点（`real.cc`，数学库函数借助 MPFR）做常量折叠，Clang 用 LLVM 的 `APFloat`——两者都按目标格式模拟 IEEE 舍入，所以在 SSE2 的 x86-64 默认选项下，翻译期与运行期通常一致。不一致主要出现在：32 位 x86 + x87（`FLT_EVAL_METHOD == 2`）、开启 `-ffast-math` / `-ffp-contract=fast`（运行期可能生成 FMA）、或者运行期修改了舍入模式（`fesetround`——常量求值总是按默认的就近舍入）。

这也解释了为什么 C++20 之前浮点数不能作非类型模板参数：模板实参的同一性依赖于"值相等"，而浮点在翻译期的可重复性没有保证。C++20 允许浮点 NTTP 后，同一性按**值表示**比较（见 [[temp.type]]）。

## 为什么规则长成这样

### 设计目标 1：常量求值 = 抽象机的一次"干净"执行

C++11 最初的 `constexpr` 函数只允许一条 `return` 语句，本质上是一个"纯函数式子集"。从 C++14 起，标准换了思路：**不再限制函数能写什么，而是限制求值时能做什么**。常量求值就是"在编译器内部的一台抽象机上执行这段代码"，只要这次执行：

- 不触及运行期才存在的东西（非 constexpr 变量的值、I/O、`reinterpret_cast` 出来的地址……）；
- 不触发任何未定义行为；
- 不把编译期分配的内存泄漏到运行期；

它就是合法的常量求值。所以 [[expr.const.core#2]] 是一张**求值时**的黑名单，而 [[dcl.constexpr]] 对函数体的限制在 C++23 后几乎全被取消了。

### 设计目标 2：同一份代码，两种执行

`constexpr` 函数**不是**"编译期函数"，而是"**也能**在编译期运行的函数"。[[dcl.constexpr#4]] 明确说：constexpr 函数的调用与等价的非 constexpr 函数在同一语境下的调用结果相同，唯一区别是前者可以出现在常量表达式中、且常量求值中不做复制消除。这一设计让同一份 `std::vector`、`std::string` 实现同时服务两个世界。

代价是：当一段代码**只能**在编译期运行（`consteval`）或**只能**在运行期运行（调用 `memcpy`、内联汇编）时，需要 `if consteval` / `std::is_constant_evaluated()` 来分流——这又引出了"显然常量求值"的精确定义。

### 设计目标 3：常量求值是 UB 检测器

[[expr.const.core#2.8]] 规定：会产生未定义行为（或错误行为）的操作使表达式不是核心常量表达式。这使得**编译器必须在常量求值中诊断出核心语言的 UB**——有符号溢出、越界访问、读未初始化对象、悬空指针解引用……这是语言里唯一一个"UB 必须被检测"的场合。详见 [[expr.const.core]] 和专题 [[topics/compile-time-programming]]。

```cpp error
#include <climits>
constexpr int add(int a, int b) { return a + b; }
int ok = add(INT_MAX, 1);                    // 运行期：UB（编译器不必诊断）
constexpr int bad = add(INT_MAX, 1);         // error: 常量求值中溢出 → 不是常量表达式
```

## 历史与演进

!!! history "C++11 → C++26 时间线"
    下表只列与 [expr.const] 直接相关、且确定的里程碑。

| 版本 | 变化 | 提案 |
|---|---|---|
| C++98 | 只有"整型常量表达式"：字面量、枚举量、用常量初始化的 `const` 整型变量、`sizeof`；不能调用函数 | — |
| C++11 | 引入 `constexpr` 变量与函数（函数体基本只能是一条 `return`）、字面类型、"核心常量表达式"框架 | [[N2235]] |
| C++14 | 放宽 constexpr 函数：局部变量、循环、`if`/`switch`、修改生命期始于本次求值的对象；constexpr 成员函数不再隐式 `const` | [[N3652]] |
| C++17 | constexpr lambda（lambda 在满足条件时隐式 constexpr）；`if constexpr` | [[P0170R1]]、[[P0292R2]] |
| C++20 | constexpr 虚函数调用；`try` 块；`dynamic_cast` 与多态 `typeid`；改变联合体活跃成员；平凡默认初始化；**瞬时分配**（transient allocation，`new`/`delete` 与 `std::allocator`）；`std::is_constant_evaluated()`；`consteval`；`constinit` | [[P1064R0]]、[[P1002R1]]、[[P1327R1]]、[[P1330R0]]、[[P1331R2]]、[[P0784R7]]、[[P0595R2]]、[[P1073R3]]、[[P1143R2]] |
| C++23 | `if consteval`；constexpr 函数中可以出现非字面类型变量、`goto`、标号（只要不被求值）；constexpr 函数中的 `static constexpr` 变量；取消"至少存在一组实参使调用为常量表达式"的要求；consteval 向上传播；使用未知引用/指针（后两者作为 DR） | [[P1938R3]]、[[P2242R3]]、[[P2647R1]]、[[P2448R2]]、[[P2564R3]]、[[P2280R4]] |
| C++26 | 从 `void*` 的 constexpr 转换；constexpr placement new；常量求值中抛出异常；constexpr 结构化绑定与对自动变量的 constexpr 引用（constexpr-referenceable）；静态反射、consteval 块、注入声明；错误行为（erroneous behavior）同样使表达式非常量 | [[P2738R1]]、[[P2747R2]]、[[P3068]]、[[P2686]]、[[P2996R13]]、[[P3289]]、[[P2795R5]] |

几个值得强调的转折点：

- **C++14 的范式转换**：从"限制语法"到"限制求值"。C++11 要求 constexpr 函数体只有一条 `return`，于是人们用递归和三目运算符写出难以阅读的代码；C++14 后只要求求值时不碰黑名单。
- **C++20 的"瞬时分配"**：允许在常量求值中 `new`，但必须在**同一次**求值中 `delete`（[[expr.const.core#2.20]]）。这是 `constexpr std::vector` / `std::string` 的基础，也是"不能有 `constexpr std::vector` 全局变量"的原因（非瞬时分配，C++26 仍未解决）。
- **C++23 的 [[P2448R2]]**：C++20 及以前，"一个 constexpr 函数如果不存在任何实参能使其调用成为常量表达式，程序 IFNDR"。这条规则既难以检查，又和 `std::is_constant_evaluated()` 分流冲突，C++23 删掉了它。现在 [[dcl.constexpr#3]] 只要求非模板 constexpr 函数不是协程。
- **C++23/26 的 P2280**：`template<class T, size_t N> constexpr size_t size(T(&)[N])` 对一个引用参数调用时，C++20 中竟然不是常量表达式（因为要"读"引用本身）。[[P2280R4]] 引入"constexpr-unknown"的概念修复了它，作为 DR 应用于之前的标准。
- **C++26 的异常**：[[expr.const.core#2.24]] 允许常量求值中构造异常对象，只要它在同一次求值中被销毁（即被捕获并处理完）。在 C++23 及之前，任何 *throw-expression* 被求值都使表达式不是核心常量表达式。截至写作时 Clang（本站测试的版本）尚未实现这一点。

## 本节和其他条款的关系

- [[dcl.constexpr]]：`constexpr` / `consteval` 说明符本身——哪些声明可以加、constexpr 变量要满足什么（constant-initializable + 常量析构）。
- [[dcl.constinit]]：`constinit` 要求变量具有静态初始化。
- [[stmt.if]]：`if constexpr`（条件是显然常量求值的）与 `if consteval`。
- [[basic.start.static]]：常量初始化如何成为静态初始化的一部分。
- [[temp.arg.nontype]]：非类型模板实参是转换后的常量表达式。
- [[intro.execution]]：抽象机——常量求值"执行"的就是它。
- [[meta.const.eval]]：`std::is_constant_evaluated()`、`std::is_within_lifetime()`。

## 陷阱

!!! pitfall "constexpr ≠ 编译期"
    `constexpr int f(int);` 只是说 f **可以**在常量表达式中被调用。`int x = f(3);` 中 `f(3)` 是否在编译期求值，由实现决定（优化时多半会折叠，`-O0` 下通常是一次真实的调用）。要强制编译期求值，用 `constexpr`/`constinit` 变量、模板实参、`static_assert`，或把 f 声明为 `consteval`。

!!! pitfall "常量表达式不一定是编译期常量'值'"
    `constexpr int* p = &global;` 是常量表达式，但 `p` 的数值（地址）在链接/加载之前根本不知道。常量表达式的"值"可以是一个**符号性的**地址，见 [[expr.const.const]]。

!!! pitfall "浮点常量折叠与运行期结果可以不同"
    依赖"编译期算出的 `double` 与运行期逐位相同"的代码（例如用 `==` 比较两者）不可移植，见 ¶2。

## 思考题

!!! question "思考题 1"
    下面的 `static_assert` 能通过吗？如果把 `C(const C&)` 改成非 constexpr 的，会怎样？

    ```cpp
    struct C {
        int n = 0;
        constexpr C() = default;
        constexpr C(const C& o) : n(o.n + 1) {}
    };
    constexpr C id(C c) { return c; }
    static_assert(id(C{}).n == 1);
    ```

<details markdown="1">
<summary>答案</summary>

能通过。`C{}` 是纯右值，用它初始化形参 `c` 是**强制**复制消除（C++17 起），不调用复制构造函数；`return c;` 返回的是形参——形参不能做 NRVO，这里会进行一次复制（或移动；C 没有移动构造函数，于是用复制构造函数），`n` 变成 1。

如果复制构造函数不是 constexpr，`id(C{})` 的求值会调用非 constexpr 函数，命中 [[expr.const.core#2.3]]，`static_assert` 的条件不是常量表达式 → ill-formed。注意这与"运行期也许会被优化掉"无关：¶1 规定判断常量性时假定**不做**复制消除。
</details>

!!! question "思考题 2"
    `int a[(1, 2)];` 与 `int b[1, 2];` 有什么区别？

<details markdown="1">
<summary>答案</summary>

数组声明符里的边界是 *constant-expression*，即 *conditional-expression*。`1, 2` 是逗号表达式，不是 *conditional-expression*，所以 `int b[1, 2];` 是**语法错误**；`(1, 2)` 是带括号的 *primary-expression*，语法上没问题，且逗号表达式的求值不在黑名单里，所以 `int a[(1, 2)];` 声明了 `int[2]`（编译器可能对未使用的左操作数给出警告）。
</details>

## 小结

| 概念 | 关注点 | 定义处 |
|---|---|---|
| 核心常量表达式 | 求值过程不碰黑名单（含 UB） | [[expr.const.core#2]] |
| 常量表达式 | 结果可以带出求值（无无效指针、无不确定/错误值） | [[expr.const.const#4]] |
| 整型 / 转换后的常量表达式 | 上下文附加的类型与转换约束 | [[expr.const.const#6]]、[[expr.const.const#8]] |
| 常量初始化 | 静态存储期变量是否在静态初始化阶段完成 | [[expr.const.init]] |
| 显然常量求值 | 语言是否**要求**在翻译期求值 | [[expr.const.defns#1]] |
| 立即函数 | 每次调用都必须是常量 | [[expr.const.imm]] |

- 常量性是表达式的**属性**；编译期求值是**时机**。标准只在"显然常量求值"的场合把两者绑定。
- 常量求值不做非强制的复制消除；浮点结果在编译期与运行期可以不同（未指定）。
- constexpr 的历史是一部"从限制语法到限制求值"的历史，C++26 的黑名单已经比 C++11 的白名单宽松得多。

相关术语：[[g:core-constant-expression]]、[[g:constant-expression]]、[[g:converted-constant-expression]]、[[g:manifestly-constant-evaluated]]、[[g:constant-initialized]]、[[g:usable-in-constant-expressions]]、[[g:immediate-function]]、[[g:constexpr-unknown]]。
