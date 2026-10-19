---
title: 常量求值
summary: 第 7.7 节的总览：核心常量表达式、常量表达式、显然常量求值、常量初始化与立即函数各管什么；常量求值不做可选的复制消除，浮点结果可以与运行期不同；constexpr 从 C++11 到 C++26 怎样放宽。
status: done
covers: expr.const.general
since: c++11
papers: N2235, N3652, P0170R1, P0292R2, P1064R0, P1002R1, P1327R1, P1330R0, P1331R2, P0784R7, P0595R2, P1073R3, P1143R2, P1938R3, P2242R3, P2647R1, P2448R2, P2564R3, P2280R4, P2738R1, P2747R2, P3068, P2686, P2996R13, P3289, P2795R5
related: expr.const.core, expr.const.const, expr.const.init, expr.const.imm, expr.const.reflect, expr.const.defns, dcl.constexpr, dcl.constinit, stmt.if, basic.start.static, temp.arg.nontype, meta.const.eval, topics/compile-time-programming
tags: 常量求值, constexpr, consteval
updated: 2026-10-19
---

!!! tldr
    - 标准不正面规定什么是常量表达式，而是列出一张禁止清单：求值过程中没碰到清单上任何一项的表达式，就是核心常量表达式。
    - 是不是常量表达式是表达式的属性，在不在编译期求值是时机问题。只有显然常量求值的场合（数组边界、模板实参、`constexpr` 变量的初始化器等）把两者绑在一起。
    - 判断常量性时假定不做可选的复制消除，所以常量求值里 NRVO 一定不发生。
    - 同一个浮点表达式在编译期和运行期算出的结果是否相同，是未指定的。
    - 常量求值中出现核心语言的未定义行为，表达式就不是常量，编译器必须报错，这是语言里唯一强制检测 UB 的场合。

## 第 7.7 节的结构

有些语境要求一个常量表达式，比如数组边界、`case` 标签、模板实参、`static_assert` 的条件。另一些语境的语义取决于表达式是不是常量表达式，比如全局变量的初始化：是常量表达式就在程序启动前静态初始化，否则在运行时动态初始化。第 7.7 节定义这些概念，分为七个小节：

| 小节 | 内容 |
|---|---|
| [[expr.const.general]]（本页） | 文法 *constant-expression*、复制消除假定、浮点一致性 |
| [[expr.const.core]] | 核心常量表达式的禁止清单（UB、`reinterpret_cast`、调用非 constexpr 函数……）；constexpr-unknown |
| [[expr.const.const]] | 常量表达式、整型常量表达式、转换后的常量表达式 |
| [[expr.const.init]] | 常量初始化、可用于常量表达式的变量 |
| [[expr.const.imm]] | 立即函数（`consteval`）、立即调用、consteval 向上传播 |
| [[expr.const.reflect]] | {{c++26}} 反射：注入声明、求值上下文 |
| [[expr.const.defns]] | 显然常量求值、潜在常量求值、常量析构 |

## 几个概念的层次

**核心常量表达式**（[[g:core-constant-expression]]，[[expr.const.core#2]]）约束求值过程：按抽象机规则求值表达式 `E`，过程中没有做禁止清单上的任何事。清单包括调用非 constexpr 函数、`reinterpret_cast`、读取一个既不能用于常量表达式、生命期也不是在本次求值内开始的变量、产生未定义行为等。

**常量表达式**（[[g:constant-expression]]，[[expr.const.const#4]]）在此之上约束结果：结果必须能离开这次求值，里面没有悬空指针，也没有不确定值或错误值。

各种语境再附加自己的要求：

- **整型常量表达式**（[[expr.const.const#6]]）：位域宽度、`alignas` 等处使用。
- **转换后的常量表达式**（[[g:converted-constant-expression]]，[[expr.const.const#8]]）：数组边界、`case` 标签、非类型模板实参等处使用，只允许安全的隐式转换，禁止窄化。
- `static_assert` 和 `if constexpr` 的条件只要求按语境转换为 `bool` 后是常量表达式，C++23 起允许窄化，`static_assert(N % 4)` 合法（[[dcl.pre#13]]、[[stmt.if#2]]）。

另一条线回答何时求值：

- **显然常量求值**（[[g:manifestly-constant-evaluated]]，[[expr.const.defns#1]]）：语言要求必须在翻译期求值的表达式。`std::is_constant_evaluated()` 和 `if consteval` 观察的就是这个属性。
- **常量初始化**（[[g:constant-initialized]]，[[expr.const.init]]）：静态或线程存储期变量用常量表达式初始化时，在静态初始化阶段完成，不参与动态初始化的排序（[[basic.start.static#2]]）。
- **立即函数**（[[g:immediate-function]]，[[expr.const.imm]]）：每次调用都必须在编译期求值的函数，即 `consteval` 函数，以及因为调用了它而被迫变成立即函数的 constexpr 函数模板特化等。

## 文法与定义（¶1）

```text
constant-expression:
    conditional-expression
```

*constant-expression* 在文法上就是 *conditional-expression*，不包括赋值表达式和逗号表达式。所以 `case 1, 2:` 在文法上就不成立；逗号表达式要加括号，`int a[(1, 2)];` 才能通过文法，至于它是不是常量，再由语义规则判断。

¶1 定义常量表达式时加了一个前提：

!!! std
    Expressions that satisfy these requirements, assuming that copy elision is not performed, are called constant expressions.

### 属性与时机

注 1 说，某些常量表达式在翻译期求值，并不是全部。`int n = sq(3);` 里的 `sq(3)` 是常量表达式，但标准没要求它在编译期计算；`int a[sq(3)];` 里的 `sq(3)` 是数组边界，必须在编译期求值。

```cpp run ok
constexpr int sq(int x) { return x * x; }

int main() {
    int a[sq(3)];          // 数组边界：必须在翻译期求值
    int n = sq(3);         // 普通初始化：是常量表达式，何时求值由实现决定
    static_assert(sizeof a == 9 * sizeof(int));
    return n - 9;
}
```

### 不做可选的复制消除

运行期是否做 NRVO 这类可选的复制消除（[[class.copy.elision]]）由实现决定。如果常量性取决于这一点，同一段代码在不同编译器上就可能一边是常量、一边不是。所以第 1 段规定判断时假定不做复制消除，[[dcl.constexpr#4]] 也重申常量表达式中不做复制消除。本可以省掉的那次复制或移动在常量求值中一定会调用，它也必须是 constexpr 的。

```cpp run ok
struct C {
    int copies = 0;
    constexpr C() = default;
    constexpr C(const C& o) : copies(o.copies + 1) {}
};

constexpr C make() {
    C c;          // 具名局部变量
    return c;     // 运行期：NRVO 可做可不做；常量求值：一定不做
}

static_assert(make().copies == 1);   // 常量求值中一定复制一次

int main() {
    C rt = make();
    return rt.copies;                 // 0 或 1，取决于是否做 NRVO；本机 Clang -O0 为 0
}
```

C++17 起用 prvalue 初始化同类型对象时的强制消除不属于可选消除，在常量求值中照常发生。

## 浮点：编译期与运行期可以不一致（¶2）

¶2 是一条推荐实践：实现应当让浮点运算在翻译期和运行期给出一致的结果。注 2 补充，标准对浮点精度没有要求，所以同一个浮点表达式在两个时期的结果是否相同是**未指定**的。标准的例子：

```cpp unspecified
bool f() {
    char array[1 + int(1 + 0.2 - 0.1 - 0.1)];   // 必须在翻译期求值
    int size = 1 + int(1 + 0.2 - 0.1 - 0.1);    // 可能在运行期求值
    return sizeof(array) == size;               // true 还是 false：未指定
}
```

`1 + 0.2 - 0.1 - 0.1` 的结果是略小于 1 还是恰好 1，取决于中间结果的精度：x87 的 80 位扩展精度、`-ffast-math`、FMA 收缩都可能改变它。

!!! impl "实现视角"
    GCC 和 Clang 的常量折叠都按目标格式模拟 IEEE 舍入，在 x86-64 使用 SSE2 的默认选项下，编译期与运行期的结果通常一致。不一致主要出现在：32 位 x86 使用 x87 运算；开启了 `-ffast-math` 或 `-ffp-contract=fast`，运行期可能生成 FMA；运行期用 `fesetround` 改了舍入模式，而常量求值总是按默认的就近舍入。

## 常量求值是抽象机的一次执行

C++11 的 constexpr 函数体基本只能有一条 `return`，相当于一个纯函数式的子集。C++14 起思路变了：不再限制函数里能写什么，而是限制求值时能做什么。常量求值就是编译器在内部按抽象机规则执行这段代码，只要这次执行不碰运行期才存在的东西、不产生未定义行为、不把编译期分配的内存留到运行期，它就是合法的。

这带来两个结果。

第一，constexpr 函数是也能在编译期运行的函数，而不是只在编译期运行的函数。[[dcl.constexpr#4]] 规定，constexpr 函数的调用与等价的非 constexpr 函数的调用结果相同，区别只在于前者能出现在常量表达式中、常量求值中不做复制消除。同一份 `std::vector` 实现因此能在两个时期使用；只能在一个时期运行的代码，用 `if consteval` 分流。

第二，常量求值成了 UB 检测器。[[expr.const.core#2.8]] 规定，会产生未定义行为或错误行为的操作使表达式不是核心常量表达式，所以有符号溢出、越界访问、读未初始化对象、解引用悬空指针在常量求值中都必须报错：

```cpp error
#include <climits>
constexpr int add(int a, int b) { return a + b; }
int ok = add(INT_MAX, 1);                    // 运行期求值：UB，不要求诊断
constexpr int bad = add(INT_MAX, 1);         // error：常量求值中溢出，不是常量表达式
```

## 历史与演进

| 版本 | 变化 | 提案 |
|---|---|---|
| C++98 | 只有整型常量表达式：字面量、枚举量、用常量初始化的 `const` 整型变量、`sizeof`；不能调用函数 | — |
| C++11 | `constexpr` 变量与函数，函数体基本只能是一条 `return`；字面类型 | [[N2235]] |
| C++14 | constexpr 函数可以有局部变量、循环、分支，可以修改生命期始于本次求值的对象 | [[N3652]] |
| C++17 | constexpr lambda；`if constexpr` | [[P0170R1]]、[[P0292R2]] |
| C++20 | constexpr 虚函数、`try` 块、`dynamic_cast` 与多态 `typeid`、改变联合体活跃成员、平凡默认初始化；编译期 `new`/`delete`（必须在同一次求值内释放）；`std::is_constant_evaluated()`；`consteval`；`constinit` | [[P1064R0]]、[[P1002R1]]、[[P1327R1]]、[[P1330R0]]、[[P1331R2]]、[[P0784R7]]、[[P0595R2]]、[[P1073R3]]、[[P1143R2]] |
| C++23 | `if consteval`；constexpr 函数中可以有非字面类型变量、`goto`、标号；`static constexpr` 局部变量；取消至少存在一组常量实参的要求；consteval 向上传播；对未知引用的使用 | [[P1938R3]]、[[P2242R3]]、[[P2647R1]]、[[P2448R2]]、[[P2564R3]]、[[P2280R4]] |
| C++26 | 从 `void*` 的转换；placement new；抛出并捕获异常；constexpr 结构化绑定与对自动变量的 constexpr 引用；静态反射与 consteval 块；错误行为同样使表达式非常量 | [[P2738R1]]、[[P2747R2]]、[[P3068]]、[[P2686]]、[[P2996R13]]、[[P3289]]、[[P2795R5]] |

其中几处值得了解：

- C++20 的编译期分配要求在同一次求值内释放（[[expr.const.core#2.20]]）。这是 constexpr `std::vector`、`std::string` 的基础，也是至今不能声明一个非空的 `constexpr std::vector` 全局变量的原因。
- C++20 及以前，一个 constexpr 函数如果不存在任何能让调用成为常量表达式的实参，程序非良构、不要求诊断。这条规则难以检查，又和用 `std::is_constant_evaluated()` 分流的写法冲突，C++23 的 [[P2448R2]] 删掉了它。现在 [[dcl.constexpr#3]] 只要求非模板的 constexpr 函数不是协程。
- 在 C++20 中，以引用形参调用 `template<class T, size_t N> constexpr size_t size(T(&)[N])` 居然不是常量表达式，因为要读取引用本身。[[P2280R4]] 引入 constexpr-unknown（[[g:constexpr-unknown]]）修复了它，并作为缺陷报告追溯到之前的标准。

## 常见误解

!!! pitfall "以为 constexpr 就是在编译期计算"
    `constexpr int f(int);` 只说明 `f` 可以在常量表达式中调用。`int x = f(3);` 中的 `f(3)` 何时求值由实现决定，`-O0` 下通常是一次真实的调用。要强制编译期求值，可以把结果放进 `constexpr` 或 `constinit` 变量、模板实参、`static_assert`，或把 `f` 声明为 `consteval`。

!!! pitfall "以为常量表达式的值在编译期已知"
    `constexpr int* p = &global;` 是常量表达式，但 `p` 的数值在链接或加载之前无从知道。常量表达式的值可以是一个符号性的地址（[[expr.const.const]]）。

## 思考题

!!! question "思考题 1"
    下面的 `static_assert` 能通过吗？把复制构造函数改成非 constexpr 的会怎样？

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

能通过。`C{}` 是 prvalue，用它初始化形参 `c` 是强制消除，不调用复制构造函数。`return c;` 返回的是形参，形参不能做 NRVO；`C` 有用户声明的复制构造函数，没有移动构造函数，于是复制一次，`n` 变成 1。

复制构造函数改成非 constexpr 后，求值会调用非 constexpr 函数（[[expr.const.core#2.3]]），`static_assert` 的条件不是常量表达式，程序非良构。运行期这次复制会不会被优化掉无关紧要，第 1 段规定判断常量性时假定不做复制消除。
</details>

!!! question "思考题 2"
    `int a[(1, 2)];` 与 `int b[1, 2];` 有什么区别？

<details markdown="1">
<summary>答案</summary>

数组边界的文法是 *constant-expression*，即 *conditional-expression*。`1, 2` 是逗号表达式，不是 *conditional-expression*，所以 `int b[1, 2];` 是语法错误。`(1, 2)` 是带括号的初等表达式，文法上没问题，逗号表达式也不在禁止清单里，所以 `int a[(1, 2)];` 声明了 `int[2]`，编译器可能对没有效果的左操作数给出警告。
</details>

## 小结

| 概念 | 关注点 | 定义处 |
|---|---|---|
| 核心常量表达式 | 求值过程不碰禁止清单（含 UB） | [[expr.const.core#2]] |
| 常量表达式 | 结果能带出求值（无无效指针、无不确定值或错误值） | [[expr.const.const#4]] |
| 整型、转换后的常量表达式 | 语境附加的类型和转换约束 | [[expr.const.const#6]]、[[expr.const.const#8]] |
| 常量初始化 | 静态存储期变量是否在静态初始化阶段完成 | [[expr.const.init]] |
| 显然常量求值 | 语言是否要求在翻译期求值 | [[expr.const.defns#1]] |
| 立即函数 | 每次调用都必须在编译期求值 | [[expr.const.imm]] |
