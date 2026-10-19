---
title: asm 声明
summary: asm 声明把一段内容交给实现处理，通常用来嵌入汇编；它是有条件支持的，括号里写什么、是什么意思都由实现定义，常量求值中执行到它会使表达式不是常量表达式。
status: done
papers: P1668R1, P2361R6
related: dcl.pre, intro.compliance, expr.const.core, dcl.constexpr, dcl.attr.grammar
tags: 声明, 内联汇编, 有条件支持
updated: 2026-10-19
---

!!! tldr
    - `asm( ... );` 是有条件支持的：实现可以不支持它，但不支持时必须给出诊断。
    - 括号里允许写什么、写了是什么意思，全部由实现定义。GCC 和 Clang 的扩展汇编语法就属于这种实现定义的含义。
    - 它是块声明，可以写在命名空间作用域，也可以写在函数体里。
    - C++20 起 constexpr 函数里可以有 asm 声明，只要常量求值时不执行到它。

## 规则（¶1）

```cpp title="asm-basic.cpp" impl
asm(".globl my_marker_sym");      // 命名空间作用域：GCC/Clang 原样输出到汇编文件

int f(int x) {
    asm("nop");                    // 块作用域：一条声明语句
    return x;
}

int main() { return f(0); }
```

¶1 asm 声明的形式如下：

```text
asm-declaration:
    attribute-specifier-seq(opt) asm ( balanced-token-seq ) ;
```

*balanced-token-seq* 是括号配对的任意记号序列（[[dcl.attr.grammar]]）。标准对它的规定只有一句：

!!! std
    The `asm` declaration is conditionally-supported; any restrictions on the *balanced-token-seq* and its meaning are implementation-defined.

    asm 声明是有条件支持的；对平衡记号序列的任何限制以及它的含义都由实现定义。

[[g:conditionally-supported|有条件支持]]（conditionally-supported）的构造，实现可以不支持，但不支持时必须对使用它的程序给出诊断（[[intro.compliance]]）。实现定义（implementation-defined）的行为，实现必须在文档里写明 {{impl}}。所以标准完全没有规定 asm 声明与汇编器、寄存器或内存模型的关系。注 1 只说，它通常用来经由实现把信息传给汇编器。

开头的可选属性属于这条 asm 声明。本机 Clang 23 不接受这个位置的属性，`[[maybe_unused]] asm("nop");` 会报错。

*asm-declaration* 是一种块声明（[[dcl.pre]]），所以它可以出现在命名空间作用域（常说的顶层汇编），也可以作为声明语句出现在函数体里。

## 括号里写什么

C++23 及以前，括号里只能是一个字符串字面量；C++26 的不求值字符串提案（[[P2361R6]]）先把它改成了不求值字符串，当前草案又进一步放宽成平衡记号序列。这样，GCC 和 Clang 广泛使用的扩展汇编语法就成了实现定义的限制和含义，而不再是语法层面的扩展：

```cpp title="asm-extended.cpp" impl
int add_one(int x) {
    int r;
#if defined(__x86_64__)
    asm("leal 1(%1), %0" : "=r"(r) : "r"(x));     // 输出操作数 : 输入操作数
#elif defined(__aarch64__)
    asm("add %w0, %w1, #1" : "=r"(r) : "r"(x));
#else
    r = x + 1;
#endif
    return r;
}

void barrier() {
    asm volatile("" ::: "memory");                // 编译器屏障
}

int main() { barrier(); return add_one(41) - 42; }
```

`volatile`、`goto`、`inline` 这些修饰词，以及用 `:` 分隔的输出、输入和破坏列表，都是 GNU 的约定。字符串里的指令对 C++ 编译器基本不透明：GCC 只做操作数替换，不解析指令；Clang 的集成汇编器会在编译时检查语法。

## 常量求值中的 asm

按 [[expr.const.core#2]]，求值一个 asm 声明会使表达式不是核心常量表达式。关键在求值二字：C++20 起（[[P1668R1]]），constexpr 函数里可以有 asm 声明，只要常量求值时不执行到它。

```cpp title="asm-constexpr.cpp" error
constexpr int g(int x) {
    if consteval { return x; }
    else { asm("nop"); return x; }     // 常量求值时不会执行到这里
}
static_assert(g(3) == 3);              // OK

constexpr int h(bool b) {
    if (b) asm("nop");
    return 1;
}
static_assert(h(false) == 1);          // OK：没有求值 asm
static_assert(h(true) == 1);           // error: 求值了 asm 声明，不是常量表达式
```

C++20 之前，constexpr 函数体里根本不能出现 asm 声明，不论是否执行到。那时一个函数无法既在编译期可用、又在运行期使用硬件指令。现在可以用 `if consteval`（C++23）或 `std::is_constant_evaluated()` 分开两条路径。

## 实现视角

!!! impl "各编译器"
    - GCC 和 Clang 支持基本汇编 `asm("...")` 和扩展汇编 `asm("..." : 输出 : 输入 : 破坏)`。关键字还有 `__asm__` 这个拼写，在 `-std=c++XX` 这种非 GNU 模式下也能用。命名空间作用域里只能写基本汇编。
    - MSVC 不支持标准的 `asm` 关键字。它有自己的 `__asm { ... }` 块语法，而且只用于 32 位 x86；x64 和 ARM64 上没有内联汇编，只能用编译器内建函数（intrinsics）或单独的汇编文件。有条件支持正是为这种情况准备的。
    - 内联汇编对优化器是一个黑箱，编译器只能根据操作数约束和破坏列表推断它的效果。`asm volatile("" ::: "memory")` 不生成任何指令，但告诉编译器内存可能被改过，于是编译器不会跨过它重排内存访问。它是编译器屏障，不约束 CPU。

## 常见误解

!!! pitfall "编译器屏障能用来做线程同步"
    `asm volatile("" ::: "memory")` 只约束编译器，CPU 仍然可以重排内存访问。线程间同步要用 `std::atomic` 和 `std::atomic_thread_fence`（[[intro.races]]）。

!!! pitfall "能编译的 asm 就是可移植的"
    即使语法被接受，含义也完全由实现定义，换一个编译器或目标架构就可能意思不同，甚至不能编译。需要硬件特性时，优先用标准库（`<bit>`、`<atomic>`）或编译器内建函数。

## 思考题

!!! question "思考题"
    一个实现不支持 asm 声明。对下面的程序，它必须怎么做？

    ```cpp
    constexpr int f() { if consteval { return 1; } else { asm("nop"); return 0; } }
    int main() { return f(); }
    ```

<details markdown="1">
<summary>答案</summary>

必须给出诊断，之后可以拒绝编译。asm 声明是有条件支持的构造，实现不支持时，对使用了它的程序必须诊断（[[intro.compliance]]），不论这段代码会不会被执行。是否求值只影响常量求值的规则（[[expr.const.core#2]]），与是否支持无关。
</details>
