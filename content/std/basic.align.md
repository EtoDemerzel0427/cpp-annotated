---
title: 对齐
summary: 对齐是对象地址必须满足的整除要求；不超过 max_align_t 的是基本对齐，超过的是扩展对齐；在对齐不足的存储里创建对象是未定义行为。
status: done
papers: P0035R4, P1413R3
related: dcl.align, expr.alignof, basic.stc.dynamic.allocation, expr.new, intro.object
tags: 对齐, alignas, alignof
updated: 2026-10-19
---

!!! tldr
    - 类型 `T` 的对齐是 `alignof(T)`，`T` 对象的地址必须是它的倍数。对齐值总是 2 的幂。
    - 在不满足对齐要求的存储里创建对象是未定义行为，不论是用定义、placement new 还是隐式创建。
    - 不超过 `alignof(std::max_align_t)` 的对齐是基本对齐，处处都支持；超过的是扩展对齐，具有扩展对齐的类型叫 over-aligned 类型。
    - 超过 `__STDCPP_DEFAULT_NEW_ALIGNMENT__` 时，C++17 起 `new` 会调用带 `std::align_val_t` 的分配函数。这个阈值和 `max_align_t` 的对齐不一定相同。
    - 用作原始存储的字节数组要写 `alignas(T) std::byte buf[sizeof(T)];`，不要再用已弃用的 `std::aligned_storage`。

## 对齐要求（¶1）

```cpp run title="misaligned.cpp" ub
#include <new>

int main() {
    alignas(int) unsigned char buf[sizeof(int) + 1];
    int* p = ::new (buf + 1) int(42);   // UB: buf + 1 不满足 int 的对齐（alignof(int) > 1 时）
    return *p;
}
```

在 x86-64 和 Apple Silicon 上，这段代码通常照常运行，返回 42。但按标准，`buf + 1` 不是 `alignof(int)` 的倍数，在那里创建 `int` 对象就是未定义行为。

¶1 每个对象类型都有**对齐要求**（alignment requirement），限制该类型的对象可以放在哪些地址上（[[basic.fundamental]]、[[basic.compound]]）。**对齐**是一个实现定义的整数，表示可以放置某个对象的相邻两个地址之间相隔多少字节。说 `alignof(int)` 是 4，就是说 `int` 对象的地址必须是 4 的倍数。

可以用对齐说明符 `alignas` 要求更严格的对齐（[[dcl.align]]），但不能放宽。

!!! std
    Attempting to create an object in storage that does not meet the alignment requirements of the object's type is undefined behavior.

这条 UB 约束的是创建对象这个动作，包括定义、placement new 和隐式对象创建（[[intro.object#13]]）。单纯把未对齐的地址 `reinterpret_cast` 成 `int*` 不在其列（转换结果由 [[expr.reinterpret.cast]] 规定）。隐式对象创建只会创建能让程序有定义行为的对象；如果后续访问需要一个未对齐的对象，就不存在这样的选择，程序的行为是未定义的。

!!! note "UBSan 能查出来"
    用 `-fsanitize=alignment`（包含在 `-fsanitize=undefined` 里）编译上面的程序，本机 Clang 23 在读 `*p` 时报告 `load of misaligned address`。x86 硬件容许普通标量的未对齐访问，这类错误往往要到 ARM 的某些指令上或者向量化之后才暴露。

## 基本对齐（¶2）

¶2 **基本对齐**（fundamental alignment）是不超过实现在所有上下文中都支持的最大对齐的对齐，这个最大值等于 `alignof(std::max_align_t)`（[[support.types]]）。凡是基本对齐，静态变量、栈、`malloc`、`new` 都必须支持。

同一个类型作为完整对象和作为子对象时，对齐要求可能不同。例 1 是虚继承的情形：

```cpp
struct B { long double d; };
struct D : virtual B { char c; };
```

`D` 作为完整对象时含有自己的 `B` 子对象，必须按 `long double` 对齐。如果 `D` 是另一个也虚继承 `B` 的类的基类子对象，`B` 子对象可能放在别处共享，`D` 子对象的对齐要求就可以更低。`alignof` 给出的总是完整对象情形下的对齐。

## 扩展对齐与 over-aligned 类型（¶3）

¶3 大于 `alignof(std::max_align_t)` 的对齐是**扩展对齐**（extended alignment）。是否支持扩展对齐、在哪些上下文支持，由实现定义。具有扩展对齐要求的类型是 **over-aligned 类型**（over-aligned type）。

注 1 指出，over-aligned 类型一定是或者包含一个施加了扩展对齐的类类型，比如某个成员用了 `alignas(64)`。标量类型的对齐都是基本对齐。

大于 `__STDCPP_DEFAULT_NEW_ALIGNMENT__`（[[cpp.predefined]]）的对齐是 **new-extended 对齐**。`operator new(std::size_t)` 本身保证这个宏给出的对齐；类型的对齐超过它时，`new` 表达式改为调用带 `std::align_val_t` 实参的分配函数（[[expr.new]]）。

扩展对齐和 new-extended 对齐是两个不同的阈值：

| 平台 | `alignof(std::max_align_t)` | `__STDCPP_DEFAULT_NEW_ALIGNMENT__` |
|---|---|---|
| x86-64 Linux（GCC、Clang） | 16 | 16 |
| arm64 macOS（Clang、libc++，本机实测） | 8 | 16 |
| MSVC x64 | 8 | 16 |

在 arm64 macOS 上，`alignas(16)` 的类型超过了 8，是 over-aligned 类型；但没有超过 16，不是 new-extended 对齐，`new` 用普通的 `operator new(size_t)` 就够了。x86-64 上 `max_align_t` 的对齐是 16，因为 `long double` 是 80 位扩展精度，按 16 字节对齐；arm64 macOS 上 `long double` 就是 `double`。

```cpp run title="over-aligned-new.cpp" ok
#include <cstdint>
#include <cstdio>
#include <cstddef>

struct alignas(64) CacheLine { int x; };    // over-aligned，也是 new-extended

int main() {
    std::printf("max_align_t=%zu default_new=%zu CacheLine=%zu\n",
                alignof(std::max_align_t),
                static_cast<std::size_t>(__STDCPP_DEFAULT_NEW_ALIGNMENT__),
                alignof(CacheLine));
    CacheLine* p = new CacheLine;            // 调用 operator new(size_t, align_val_t)
    bool ok = reinterpret_cast<std::uintptr_t>(p) % 64 == 0;
    delete p;                                // 调用对应的带 align_val_t 的 operator delete
    return ok ? 0 : 1;
}
```

本机输出 `max_align_t=8 default_new=16 CacheLine=64`，返回值为 0。

!!! history "C++17 之前的 over-aligned new"
    C++11 引入了 `alignas`，但 `new CacheLine` 仍然只调用 `operator new(size_t)`，后者只保证基本对齐，得到的指针很可能不是 64 的倍数，在那里创建对象就是 UB。程序员只能用 `posix_memalign` 或 `_aligned_malloc` 加 placement new。C++17 的 [[P0035R4]] 加入了 `std::align_val_t`、对齐版本的分配和释放函数，以及 `__STDCPP_DEFAULT_NEW_ALIGNMENT__`，从此 over-aligned 类型可以直接 `new`（[[basic.stc.dynamic.allocation#3]]）。

## 对齐值（¶4–¶7）

¶4 对齐用 `std::size_t` 类型的值表示。合法的对齐值只有基本类型的 `alignof` 值，再加上一个实现定义的、可以为空的额外集合。每个对齐值都必须是 2 的非负整数次幂。

¶5 对齐从弱到强排列，数值越大越严格。满足某个对齐要求的地址也满足任何更弱的合法对齐，例如 64 的倍数一定是 16 的倍数。¶7 补充，比较对齐就是比较它们的数值。

¶6 完整类型的对齐要求可以用 `alignof` 查询（[[expr.alignof]]）。窄字符类型的对齐要求最弱，也就是 1。所以注 2 说，`unsigned char` 数组可以用作对齐的原始存储，再用 `alignas` 提高它的对齐。

```cpp run title="alignas-rules.cpp" error
struct alignas(8) S {};
struct alignas(1) U { S s; };   // error: 比不写 alignas 时的对齐（8）更弱
alignas(3) int x;               // error: 3 不是 2 的幂
alignas(int) alignas(64) unsigned char buf[256];   // OK：取最严格的 64
```

前两行违反的是 [[dcl.align]] 的规则，本机 Clang 23 分别报告 `requested alignment is less than minimum alignment` 和 `requested alignment is not a power of 2`。

¶8 是一个注：运行时可以用 `std::align`（[[ptr.align]]）在缓冲区里找一个对齐的位置。

```cpp run title="std-align.cpp" ok
#include <memory>
#include <new>
#include <cstddef>

struct alignas(32) V { float f[8]; };

int main() {
    unsigned char arena[256];
    void* p = arena;
    std::size_t space = sizeof arena;
    if (std::align(alignof(V), sizeof(V), p, space)) {   // 把 p 调整到 32 的倍数处
        V* v = ::new (p) V{};                             // OK：存储满足对齐
        v->f[0] = 1.0f;
        v->~V();
    }
}
```

## 不支持的扩展对齐（¶9）

¶9 如果实现在某个上下文中不支持所请求的扩展对齐，程序非良构，编译器必须诊断。例如一个实现可能允许静态变量使用 `alignas(4096)`，却不允许自动变量这样做。支持哪些对齐由实现决定（¶3），但不支持时必须报错，不能悄悄给出一个对齐不足的对象。

## 实现视角

!!! impl "对齐在代码生成中的样子"
    - 结构体的每个成员按自己的对齐放置，必要时插入填充；结构体的对齐取成员中的最大者，`sizeof` 向上取整到对齐的倍数，这样数组里的每个元素都是对齐的。
    - 栈上的 over-aligned 变量，编译器在函数开头把栈指针向下对齐（如 `and rsp, -64`），通常还需要一个帧指针来访问实参。
    - `#pragma pack` 和 `__attribute__((packed))` 是非标准扩展，会产生对齐低于自然对齐的成员。取这种成员的地址再解引用，在严格对齐的硬件上可能崩溃，编译器通常会给出警告。

## 常见误解

!!! pitfall "字节缓冲区不需要 `alignas`"
    `unsigned char buf[sizeof(T)]` 的对齐只有 1。在其中 placement new 一个 `T` 之前，必须加上 `alignas(T)`。这是手写小缓冲区或 `optional` 时最常见的错误，而且在 x86 上通常不会立刻出问题。

!!! pitfall "`malloc` 能满足任意对齐"
    `malloc` 只保证基本对齐。over-aligned 类型要用 `std::aligned_alloc`（它要求大小是对齐的整数倍），或者 C++17 的对齐版 `operator new`。

!!! pitfall "`std::aligned_storage` 是标准的对齐缓冲区"
    C++23 弃用了 `std::aligned_storage` 和 `std::aligned_union`（[[P1413R3]]）。它们容易用错：忘写 `::type` 时得到的是一个空类；成员 `type` 也不保证是 `unsigned char` 或 `std::byte` 数组，按 [[intro.object#3]] 不一定能为其中的对象提供存储；取用对象还需要 `reinterpret_cast`。应当直接写 `alignas(T) std::byte buf[sizeof(T)];`。

## 思考题

!!! question "思考题 1"
    `struct alignas(16) A { char c; };` 在 arm64 macOS 上是 over-aligned 类型吗？`new A` 调用哪个分配函数？

<details markdown="1">
<summary>答案</summary>

`alignof(std::max_align_t)` 是 8，16 大于 8，所以 `A` 是 over-aligned 类型。但 16 不大于 `__STDCPP_DEFAULT_NEW_ALIGNMENT__`（16），不是 new-extended 对齐，`new A` 调用普通的 `operator new(std::size_t)`，它已经保证 16 字节对齐（[[basic.stc.dynamic.allocation#3]] 的第 3.3 项）。本机替换全局 `operator new` 后观察到的正是这个版本。

在 x86-64 Linux 上，16 没有超过 `max_align_t` 的对齐，`A` 连 over-aligned 类型都不是。
</details>

!!! question "思考题 2"
    在 `alignof(int) == 4` 的平台上，下面的 placement new 是否有 UB？

    ```cpp
    alignas(8) unsigned char buf[16];
    int* p = ::new (buf + 4) int(1);
    ```

<details markdown="1">
<summary>答案</summary>

没有。`buf` 的地址是 8 的倍数，`buf + 4` 是 4 的倍数，满足 `int` 的对齐；它不满足 8 字节对齐，但 `int` 只需要 4。`buf` 是 `unsigned char` 数组，新对象完全落在其中，所以 `buf` 为这个 `int` 提供存储（[[intro.object#3]]），`buf` 自身的生命周期不受影响。
</details>
