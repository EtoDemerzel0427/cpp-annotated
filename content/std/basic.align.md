---
title: 对齐
summary: 对齐是对象地址必须满足的整除约束；基本对齐不超过 max_align_t，超过者为扩展对齐（over-aligned）；alignof 查询、alignas 加强、C++17 起 new 支持 over-aligned 类型
status: done
papers: P0035R4
related: dcl.align, expr.alignof, basic.stc.dynamic.allocation, expr.new, intro.object
tags: 对齐, alignas, alignof
updated: 2026-10-17
---

**对齐**（alignment）回答的是一个类型的对象可以放在哪些地址上。在硬件层面，许多 CPU 读写未对齐的多字节数据要么更慢，要么直接触发总线错误，SIMD 指令（如要求 16/32/64 字节对齐的向量 load/store）更是如此。在语言层面，标准把这件事抽象成一个整数：类型 `T` 的对齐 `alignof(T)` 是 `A`，意思是 `T` 对象的地址必须是 `A` 的倍数。

本节规定对齐值是什么、哪些对齐值合法、哪些是基本对齐、哪些是扩展对齐，以及在不满足对齐的存储里创建对象的后果（UB）。具体的语法工具在别处：`alignof` 见 [[expr.alignof]]，`alignas` 见 [[dcl.align]]，动态分配的对齐保证见 [[basic.stc.dynamic.allocation]] 和 [[expr.new]]。

## 对齐要求（¶1）

!!! std
    An *alignment* is an implementation-defined integer value representing the number of bytes between successive addresses at which a given object can be allocated.

    对齐是一个实现定义的整数值，表示可以分配某个对象的相邻两个地址之间相隔的字节数。

- 每个对象类型都有对齐要求（[[basic.fundamental]]、[[basic.compound]]），对该类型的每个对象生效。
- 可以用 *alignment-specifier*（`alignas`）要求更严格的对齐，但不能放宽（[[dcl.align#5]]）。
- **在不满足类型对齐要求的存储中创建对象是 UB**。

最后一条是本节唯一的 UB，它约束的是创建对象这个动作，不论是定义、placement new，还是隐式对象创建（[[intro.object#13]]）。因此，对一个未对齐的指针做 `reinterpret_cast` 本身未必是 UB（结果未指定，见 [[expr.reinterpret.cast]]、[[expr.static.cast]]），但在那里 placement new 或隐式创建对象就是 UB。隐式对象创建只会选择能让程序有定义行为的对象集合；如果访问需要一个未对齐的对象，这样的集合就不存在，于是整个程序都是 UB。

```cpp run title="misaligned.cpp" ub
#include <new>
#include <cstddef>

int main() {
    alignas(int) unsigned char buf[sizeof(int) + 1];
    int* p = ::new (buf + 1) int(42);   // UB: buf + 1 不满足 int 的对齐要求（alignof(int) > 1 的平台上）
    return *p;
}
```

!!! note "UBSan 能检查出来"
    用 `-fsanitize=alignment`（包含在 `-fsanitize=undefined` 中）编译时，Clang 和 GCC 会在运行时检查对齐。x86 硬件容许普通标量的未对齐访问，所以这类 bug 在 x86 上常常不显现，到了 ARM 的某些指令上或者向量化之后才暴露出来。

## 基本对齐与完整对象/子对象的差异（¶2）

!!! std
    A *fundamental alignment* is represented by an alignment less than or equal to the greatest alignment supported by the implementation in all contexts, which is equal to `alignof(std::max_align_t)`.

    基本对齐是不超过实现在所有上下文中都支持的最大对齐的对齐值，该最大值等于 `alignof(std::max_align_t)`。

`std::max_align_t`（[[support.types]]）代表对齐要求最严格的标量类型；凡是不超过它的对齐，实现在任何地方（静态、栈、`malloc`、`new`）都必须支持。

¶2 后半段和例 1 讲了一个容易忽略的事实：**同一个类型作为完整对象和作为子对象时，对齐要求可能不同**。典型的情形是虚继承：

```cpp title="virtual-base-align.cpp" ok
struct B { long double d; };
struct D : virtual B { char c; };
// D 作为完整对象：包含自己的 B 子对象，必须按 long double 对齐。
// D 作为另一个也虚继承 B 的类的基类子对象时：B 子对象可能被放在别处共享，
// D 子对象本身可能只需按 vptr / char 对齐。
```

`alignof` 报告的总是完整对象情形下的对齐要求。

## 扩展对齐与 over-aligned 类型（¶3）

- **扩展对齐**（extended alignment）：大于 `alignof(std::max_align_t)` 的对齐。是否支持、在哪些上下文支持，由实现定义。
- 具有扩展对齐要求的类型叫 **over-aligned 类型**。注 1 指出，over-aligned 类型一定是或者包含一个施加了扩展对齐的类类型（比如某个成员用了 `alignas(64)`），因为标量类型的天然对齐都是基本对齐。
- **new-extended 对齐**：大于 `__STDCPP_DEFAULT_NEW_ALIGNMENT__`（[[cpp.predefined]]）的对齐。这是 `operator new(std::size_t)` 本身就保证的对齐；超过它时，*new-expression* 会改为调用带 `std::align_val_t` 参数的分配函数（[[expr.new]]）。

注意扩展对齐和 new-extended 对齐是**两个不同的阈值**：

| 平台（示例） | `alignof(std::max_align_t)` | `__STDCPP_DEFAULT_NEW_ALIGNMENT__` |
|---|---|---|
| x86-64 Linux（GCC/Clang, libstdc++） | 16 | 16 |
| arm64 macOS（Apple Clang/Homebrew Clang, libc++） | 8 | 16 |

（arm64 macOS 一行是本机实测值。）在后者上，`alignas(16)` 的类型是 over-aligned（超过 8），但不是 new-extended（不超过 16），`new` 用普通的 `operator new(size_t)` 就够了。

```cpp run title="over-aligned-new.cpp" ok
#include <cstdint>
#include <cstdio>
#include <cstddef>

struct alignas(64) CacheLine { int x; };    // over-aligned，且是 new-extended

int main() {
    std::printf("max_align_t=%zu default_new=%zu CacheLine=%zu\n",
                alignof(std::max_align_t),
                static_cast<std::size_t>(__STDCPP_DEFAULT_NEW_ALIGNMENT__),
                alignof(CacheLine));
    CacheLine* p = new CacheLine;            // C++17 起调用 operator new(size_t, align_val_t)
    bool ok = reinterpret_cast<std::uintptr_t>(p) % 64 == 0;
    delete p;                                // 调用对应的 operator delete(void*, size_t, align_val_t)
    return ok ? 0 : 1;
}
```

!!! history "C++17 之前的 over-aligned new"
    C++11 引入了 `alignas`，却没有让 `new` 理会它：`new CacheLine` 只调用 `operator new(size_t)`，后者只保证基本对齐，于是得到的指针很可能不是 64 字节对齐的，按 ¶1，在其上创建对象就是 UB。程序员只能自己用 `posix_memalign`/`_aligned_malloc` 加 placement new。[[P0035R4]]（C++17）引入了 `std::align_val_t`、对齐版本的分配/释放函数和 `__STDCPP_DEFAULT_NEW_ALIGNMENT__`，从此 `new` 对 over-aligned 类型也可以直接使用。见 [[basic.stc.dynamic.allocation#3]]。

## 对齐值的合法范围与次序（¶4–¶7）

- ¶4：对齐用 `std::size_t` 表示。合法的对齐值只有各基本类型的 `alignof` 值，再加上一个实现定义的（可以为空的）额外集合。**每个对齐值都必须是 2 的非负整数次幂**，所以 `alignas(3)` 是非良构的（[[dcl.align#2]]）。
- ¶5：对齐从弱到强（更严格）排序，数值越大越严格。满足某对齐要求的地址也满足任何更弱的合法对齐，这对 2 的幂是显然的（64 的倍数一定是 16 的倍数）。
- ¶6：完整类型的对齐要求可以用 `alignof` 查询（[[expr.alignof]]）。窄字符类型的对齐要求最弱（即 1），所以 `unsigned char` 数组可以用作任意对象的原始存储，再由 `alignas` 加强对齐（注 2）。
- ¶7：比较对齐就是比较数值。

```cpp run title="alignas-rules.cpp" error
struct alignas(8) S {};
struct alignas(1) U { S s; };   // error: 请求的对齐弱于不加 alignas 时的对齐（[dcl.align]/5）
alignas(3) int x;               // error: 3 不是合法的对齐值（不是 2 的幂）
alignas(int) alignas(64) unsigned char buf[256];   // OK: 取最严格者 64
```

¶8 是注：运行时可以用 `std::align`（[[ptr.align]]）在缓冲区里找一个对齐的位置；编译期用 `alignas` 显式对齐存储。

```cpp run title="std-align.cpp" ok
#include <memory>
#include <new>
#include <cstddef>

struct alignas(32) V { float f[8]; };

int main() {
    unsigned char arena[256];
    void* p = arena;
    std::size_t space = sizeof arena;
    if (std::align(alignof(V), sizeof(V), p, space)) {   // 把 p 调整到 32 字节对齐处
        V* v = ::new (p) V{};                             // OK: 存储满足对齐
        v->f[0] = 1.0f;
        v->~V();
    }
}
```

## 不支持的扩展对齐（¶9）

如果实现在某个特定上下文中不支持所请求的扩展对齐，程序**非良构**（必须诊断）。例如某个实现可能支持静态变量使用 `alignas(4096)`，却不支持自动变量这么做。标准把支持哪些对齐留给实现定义（¶3），但把不支持时必须报错写成了硬性要求，以免静默地给出一个不满足对齐的对象。

## 实现视角

!!! impl "实现视角"
    - x86-64 System V / Itanium ABI：`alignof(long double)` 为 16（x87 80 位扩展精度，按 16 字节存储），因而 `max_align_t` 对齐为 16。AArch64 macOS 上 `long double` 就是 `double`，`max_align_t` 对齐为 8，但 libc++/系统 `malloc` 仍保证 16 字节对齐，所以 `__STDCPP_DEFAULT_NEW_ALIGNMENT__` 为 16。MSVC x64 上 `alignof(std::max_align_t)` 为 8，`__STDCPP_DEFAULT_NEW_ALIGNMENT__` 为 16。
    - 对于栈上的 over-aligned 变量，编译器在函数序言中把栈指针按需要的对齐值下调（`and rsp, -64` 之类），通常还需要帧指针来访问参数。
    - 结构体布局中，每个成员按自身对齐放置（可能插入填充），整个结构体的对齐取成员中的最大者，`sizeof` 向上取整为对齐的倍数，这保证了数组中每个元素都对齐。
    - `#pragma pack` / `__attribute__((packed))` 是非标准扩展，会产生低于天然对齐的成员。对这种成员取地址，再解引用得到的指针，在严格对齐的硬件上可能崩溃，编译器通常会对此给出警告。

## 陷阱

!!! pitfall "用 `char` 缓冲区当存储却忘了 `alignas`"
    `unsigned char buf[sizeof(T)]` 的对齐只有 1。在其中 placement new 一个 `T` 之前，必须加上 `alignas(T)`。这是手写 small buffer / `optional` 时最常见的 bug，而且在 x86 上通常不会立刻崩溃。

!!! pitfall "以为 `malloc` 能满足任意对齐"
    `malloc` 只保证基本对齐（满足 `max_align_t` 的需要）。over-aligned 类型要用 `std::aligned_alloc`（注意其 size 须是 alignment 的整数倍）或 C++17 的对齐版 `operator new`。

!!! pitfall "`std::aligned_storage` 已被弃用"
    C++23 弃用了 `std::aligned_storage` / `std::aligned_union`，主要原因是它们容易误用，且无法为 `constexpr` 提供存储。应当直接写 `alignas(T) std::byte buf[sizeof(T)];`。

## 思考题

!!! question "思考题 1"
    `struct alignas(16) A { char c; };` 在 arm64 macOS 上是 over-aligned 类型吗？`new A` 调用哪个分配函数？

<details markdown="1">
<summary>答案</summary>

`alignof(std::max_align_t)` 为 8，16 > 8，所以 `A` 是 over-aligned 类型（扩展对齐）。但 16 不大于 `__STDCPP_DEFAULT_NEW_ALIGNMENT__`（16），所以它不是 new-extended 对齐；`new A` 调用普通的 `operator new(std::size_t)`，后者已保证 16 字节对齐（[[basic.stc.dynamic.allocation#3]] 的第 3.3 项）。在 x86-64 Linux 上，16 既不超过 `max_align_t` 对齐也不超过默认 new 对齐，`A` 甚至不是 over-aligned 类型。
</details>

!!! question "思考题 2"
    下面的 placement new 在 `alignof(int) == 4` 的平台上是否有 UB？

    ```cpp
    alignas(8) unsigned char buf[16];
    int* p = ::new (buf + 4) int(1);
    ```

<details markdown="1">
<summary>答案</summary>

没有。`buf` 按 8 字节对齐，`buf + 4` 是 4 的倍数，满足 `int` 的对齐。`buf+4` 虽然不满足 8 字节对齐，但 `int` 只需要 4（¶5：满足强对齐的地址也满足弱对齐）。另外，`buf` 是 `unsigned char` 数组，新对象完全落在其中，所以 `buf` 为该 `int` 提供存储（[[intro.object#3]]），`buf` 的生命周期不受影响。
</details>

## 小结

| 概念 | 定义 / 要点 |
|---|---|
| 对齐 | 对象地址必须是其倍数的整数；实现定义；必须是 2 的幂 |
| 基本对齐 | ≤ `alignof(std::max_align_t)`，处处支持 |
| 扩展对齐 / over-aligned | > `alignof(std::max_align_t)`；支持与否实现定义，不支持时非良构 |
| new-extended 对齐 | > `__STDCPP_DEFAULT_NEW_ALIGNMENT__`；`new` 改用 `align_val_t` 版本（C++17） |
| 最弱对齐 | 窄字符类型（1）；字节数组 + `alignas` = 通用原始存储 |
| UB | 在不满足对齐的存储中创建对象 |
