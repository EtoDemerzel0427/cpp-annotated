---
title: asm 声明
summary: asm 声明是有条件支持的，括号内记号的限制和含义完全由实现定义；它是块声明，可以出现在命名空间作用域和函数体中；常量求值中求值它会使表达式非常量
status: done
papers: P1668R1
related: dcl.pre, intro.compliance, expr.const.core, dcl.constexpr, dcl.attr.grammar
tags: 声明, 内联汇编, 有条件支持
updated: 2026-10-17
---

[dcl.asm] 只有一段，是标准把整个特性交给实现处理的典型例子：

```text
asm-declaration:
    attribute-specifier-seq(opt) asm ( balanced-token-seq ) ;
```

## 规则（¶1）

¶1 说了四件事：

1. 形式依次是 `asm`、圆括号里的平衡记号序列（*balanced-token-seq*，即括号配对的任意记号序列，[[dcl.attr.grammar]] 中定义）和分号。
2. 它是**有条件支持**的（conditionally-supported，[[intro.compliance]]）。实现可以不支持它，但不支持时必须对使用它的程序给出诊断。
3. 对 *balanced-token-seq* 的任何限制及其含义都是**实现定义**的 {{impl}}。标准没有规定它与汇编器、寄存器、内存模型之间的任何关系。
4. 可选的 *attribute-specifier-seq* 属于这个 asm 声明。

注 1 指出，它通常用来经由实现把信息传递给汇编器。

!!! std
    The `asm` declaration is conditionally-supported; any restrictions on the *balanced-token-seq* and its meaning are implementation-defined.

    asm 声明是有条件支持的；对平衡记号序列的任何限制以及它的含义都由实现定义。

## 它在语法中的位置

*asm-declaration* 是一种块声明（*block-declaration*，[[dcl.pre]]），因此它既可以出现在命名空间作用域（即顶层汇编），也可以作为声明语句出现在函数体中：

```cpp title="asm-basic.cpp" impl
asm(".globl my_marker_sym");      // 命名空间作用域：GCC/Clang 原样输出到汇编文件

int f(int x) {
    asm("nop");                    // 块作用域：一条 asm 声明语句
    return x;
}

int main() { return f(0); }
```

既然它是声明，它就和其他声明一样受 [[dcl.pre]] 的约束，也可以带属性（尽管目前没有标准属性适用于它）。

## 括号里写什么由实现定义

当前草案的语法要求括号内是平衡记号序列；较早的标准只允许一个字符串字面量（C++23 中仍是如此）。换成平衡记号序列之后，GCC/Clang 广泛使用的扩展汇编语法也可以看作实现定义的限制与含义的一种，而不再是语法层面的扩展：

```cpp title="asm-extended.cpp" impl
int add_one(int x) {
    int r;
#if defined(__x86_64__)
    asm("leal 1(%1), %0" : "=r"(r) : "r"(x));        // GNU 扩展汇编：输出/输入操作数
#elif defined(__aarch64__)
    asm("add %w0, %w1, #1" : "=r"(r) : "r"(x));
#else
    r = x + 1;
#endif
    return r;
}

void barrier() {
    asm volatile("" ::: "memory");                   // 常见的"编译器屏障"惯用法
}

int main() { barrier(); return add_one(41) - 42; }
```

- `volatile`、`goto`、`inline` 等修饰词，`:` 分隔的输出、输入、破坏列表，都是 GNU 的约定。
- 字符串内容对 C++ 编译器来说基本是不透明的：GCC 不解析其中的指令（只做操作数替换），Clang 的集成汇编器则会在编译时检查语法。

## 与常量求值的交互

按 [[expr.const.core#2]] 第 2.33 项，求值一个 *asm-declaration* 会使表达式不是核心常量表达式。这里的关键词是“求值”：

- C++20 起（[[P1668R1]]），constexpr 函数中可以出现 asm 声明，只要常量求值时不执行到它；
- 典型用法是配合 `if consteval`（C++23）或 `std::is_constant_evaluated()`，让常量求值走纯 C++ 路径，运行期走内联汇编。

```cpp title="asm-constexpr.cpp" error
constexpr int g(int x) {
    if consteval { return x; }
    else { asm("nop"); return x; }     // OK: 常量求值时不会到这里
}
static_assert(g(3) == 3);              // OK

constexpr int h(bool b) {
    if (b) asm("nop");
    return 1;
}
static_assert(h(false) == 1);          // OK: 没有求值 asm
static_assert(h(true) == 1);           // error: 求值了 asm 声明，不是常量表达式
```

C++20 之前，constexpr 函数体中不得包含 asm 声明（这是针对函数定义的语法限制，不论是否执行到）。因此 `<bit>`、`<cmath>` 这类库无法在同一个函数里同时提供编译期可用的路径和运行期使用硬件指令的路径。

## 实现视角

!!! impl "各编译器"
    - GCC / Clang 支持基本汇编 `asm("...")` 和扩展汇编 `asm("..." : 输出 : 输入 : 破坏)`；关键字还有 `__asm__` 拼写，在 `-std=c++XX`（非 GNU 方言）下也可用。命名空间作用域的 asm 只能是基本汇编。
    - MSVC 不支持标准的 `asm` 关键字。它有自己的 `__asm { ... }` 块语法，且只在 32 位 x86 目标上可用；x64 和 ARM64 上不支持内联汇编，只能使用编译器内建函数（intrinsics）或单独的汇编文件。有条件支持这一类别正是为这种情况准备的。
    - 内联汇编对优化器来说是一个黑箱：编译器只能依据约束（操作数、破坏列表）推理它的效果。`asm volatile("" ::: "memory")` 不生成任何指令，但告诉编译器内存可能已被修改，从而阻止编译器跨越它重排内存访问。这是**编译器屏障**，不是 CPU 内存屏障。

## 陷阱

!!! pitfall "asm 不是可移植的 C++"
    即便语法被接受，其含义完全由实现定义；同一段代码在不同编译器、不同目标架构上可能语义迥异，甚至不能编译。需要可移植地使用硬件特性时，优先选择标准库（`<bit>`、`<atomic>`）或编译器内建函数。

!!! pitfall "编译器屏障不等于内存序"
    `asm volatile("" ::: "memory")` 只约束编译器，不约束 CPU。线程间同步请使用 `std::atomic` 与 `std::atomic_thread_fence`（[[intro.races]]）。

## 思考题

!!! question "思考题"
    一个实现不支持 `asm` 声明。遇到下面的程序，它必须怎么做？

    ```cpp
    constexpr int f() { if consteval { return 1; } else { asm("nop"); return 0; } }
    int main() { return f(); }
    ```

<details markdown="1">
<summary>答案</summary>

asm 声明是有条件支持的构造。按 [[intro.compliance]]，如果实现不支持某个有条件支持的构造，它必须对使用了该构造的程序给出诊断，即使这段代码在常量求值中永远不会执行，在运行期也可能执行不到。所以实现必须诊断（之后可以拒绝编译）。是否求值只影响常量求值规则（[[expr.const.core#2]]），与是否支持无关。
</details>

## 小结

!!! summary "要点"
    - `asm ( balanced-token-seq ) ;`：有条件支持，限制和含义全部实现定义。
    - 是块声明：可在命名空间作用域或函数体中出现；可带属性。
    - C++20 起可出现在 constexpr 函数中，但常量求值时求值它会使表达式非常量。
    - MSVC 的 x64/ARM64 目标不支持内联汇编；GCC/Clang 的扩展汇编语法在当前草案的语法下属于实现定义的含义。
